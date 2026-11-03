// mod-bleakhold-ui tests: the cafe's rules (section 21, src/BleakholdCafeRules.h) against the generated catalogue
// (src/BleakholdCafeData.h), and the catalogue against the numbers of the design and the examples of
// docs/BleakholdProtocol.md section 21.
//
//   bh_cafe <repo root>
//
// SPDX-License-Identifier: GPL-2.0-or-later

#include "bh_check.h"

#include "BleakholdCafeData.h"
#include "BleakholdCafeRules.h"
#include "BleakholdCampRules.h"
#include "BleakholdCodec.h"
#include "BleakholdMessages.h"

#include <cmath>
#include <map>
#include <set>

using namespace Bleakhold;
namespace D = Bleakhold::CafeData;
namespace R = Bleakhold::CafeRules;

static std::string g_repo;

namespace
{
    bool Near(float a, float b, float eps = 0.001f) { return std::fabs(a - b) <= eps; }

    D::Recipe const& Rec(uint16_t id)
    {
        D::Recipe const* r = D::FindRecipe(id);
        if (!r)
        {
            std::fprintf(stderr, "no recipe %u\n", id);
            std::exit(2);
        }
        return *r;
    }

    D::Persona const& Per(uint32_t entry)
    {
        D::Persona const* p = D::FindPersona(entry);
        if (!p)
        {
            std::fprintf(stderr, "no persona %u\n", entry);
            std::exit(2);
        }
        return *p;
    }

    D::LayoutPiece const* Piece(uint8_t cafe, uint16_t slot)
    {
        for (D::LayoutPiece const& p : D::Layout)
            if (p.cafeId == cafe && p.slot == slot)
                return &p;
        return nullptr;
    }

    // the default layout's work spots of a cafe, built as the server builds them (anchor at the origin facing +X)
    std::vector<R::SpotRef> DefaultSpots(uint8_t cafe, R::Pose anchor = {})
    {
        std::vector<R::SpotRef> out;
        for (D::LayoutPiece const& p : D::Layout)
        {
            if (p.cafeId != cafe || !p.station)
                continue;
            R::Pose const piece = R::ToWorld(anchor, p.f, p.l, p.u, p.turn);
            for (uint8_t i = 0; i < p.workCount; ++i)
            {
                R::Pose const s = R::WorkSpot(piece, anchor.z, p.work[i][0], p.work[i][1]);
                out.push_back({ p.station, i, s.x, s.y, s.z, piece.x, piece.y });
            }
        }
        return out;
    }

    std::vector<std::string> Split(std::string const& s, char sep)
    {
        std::vector<std::string> out;
        std::size_t start = 0;
        while (true)
        {
            std::size_t const p = s.find(sep, start);
            if (p == std::string::npos)
            {
                out.push_back(s.substr(start));
                return out;
            }
            out.push_back(s.substr(start, p - start));
            start = p + 1;
        }
    }

    // the payload of the document's example "S> 1 <op> <seq> 1/1 <payload>"
    std::string DocPayload(std::string const& doc, std::string const& op, std::string const& seq)
    {
        std::string const head = "S> 1 " + op + " " + seq + " 1/1 ";
        std::size_t const at = doc.find(head);
        if (at == std::string::npos)
            return {};
        std::size_t const end = doc.find('\n', at);
        return doc.substr(at + head.size(), end - at - head.size());
    }
}

// =================================================================================================================
// The catalogue (section 2)
// =================================================================================================================
TEST("catalogue: 26 actions, 38 recipes, every step valid, a timed step, Serve last")
{
    CHECK_EQN(D::Actions.size(), 26u);
    CHECK_EQN(D::Recipes.size(), 38u);
    for (std::size_t i = 0; i < D::Actions.size(); ++i)
    {
        CHECK_EQN(D::Actions[i].id, i + 1);
        CHECK_EQN(D::Actions[i].spell, D::SpellStepBase + D::Actions[i].id);
        CHECK(D::FindStation(D::Actions[i].station) != nullptr);
    }
    for (D::Recipe const& r : D::Recipes)
    {
        CHECK(r.stepCount >= 4 && r.stepCount <= D::MaxSteps);
        bool timed = false;
        for (uint8_t i = 0; i < r.stepCount; ++i)
        {
            CHECK(D::FindAction(r.steps[i]) != nullptr);
            CHECK(r.steps[i] != D::ActionTakeOrder && r.steps[i] != D::ActionBin);
            timed = timed || R::IsTimed(r.steps[i]);
        }
        CHECK_MSG(timed, std::string(r.name));
        CHECK_EQN(r.steps[r.stepCount - 1], D::ActionServe);
        CHECK_EQN(R::CountLines(r.steps.data(), r.stepCount), r.lines);
        CHECK_EQN(r.id, D::RecipeId(r.cafeId, r.n));
    }
    // the same tier, unlock and steps in both cafes
    for (uint8_t n = 1; n <= 19; ++n)
    {
        D::Recipe const& a = Rec(D::RecipeId(1, n));
        D::Recipe const& b = Rec(D::RecipeId(2, n));
        CHECK_EQN(a.tier, b.tier);
        CHECK_EQN(a.unlock, b.unlock);
        CHECK(a.steps == b.steps);
        CHECK(a.family == b.family);
    }
}

TEST("catalogue: lines merge equal neighbours")
{
    uint8_t const m6[] = { 11, 11, 11, 18, 20, 15, 23, 25 };
    CHECK_EQN(R::CountLines(m6, 8), 6u);
    uint8_t const c4[] = { 1, 3, 3, 19, 25 };
    CHECK_EQN(R::CountLines(c4, 5), 4u);
    uint8_t const abab[] = { 1, 3, 1, 3 };
    CHECK_EQN(R::CountLines(abab, 4), 4u);
    CHECK_EQN(R::CountLines(abab, 0), 0u);
}

TEST("catalogue: unlock levels, tiers and prices per section 2.5 and 2.8")
{
    // n: tier, unlock
    std::map<uint8_t, std::pair<uint8_t, uint8_t>> const want = {
        { 1, { 1, 1 } }, { 2, { 1, 1 } }, { 3, { 2, 2 } }, { 4, { 2, 3 } }, { 5, { 3, 4 } }, { 6, { 3, 5 } }, { 7, { 5, 9 } },
        { 8, { 1, 1 } }, { 9, { 1, 1 } }, { 10, { 2, 3 } }, { 11, { 3, 5 } }, { 12, { 3, 6 } }, { 13, { 4, 8 } },
        { 14, { 1, 2 } }, { 15, { 2, 2 } }, { 16, { 3, 4 } }, { 17, { 3, 6 } }, { 18, { 4, 7 } }, { 19, { 5, 10 } },
    };
    for (auto const& [n, tu] : want)
    {
        CHECK_EQN(Rec(D::RecipeId(1, n)).tier, tu.first);
        CHECK_EQN(Rec(D::RecipeId(1, n)).unlock, tu.second);
    }
    uint32_t const price[] = { 4000, 6000, 9000, 12000, 18000 };
    uint32_t const buff[] = { 30, 35, 40, 45, 50 };
    uint32_t const xp[] = { 8, 12, 18, 25, 35 };
    uint32_t const tip[] = { 400, 600, 900, 1300, 1800 };
    for (uint8_t t = 1; t <= 5; ++t)
    {
        D::Tier const* tier = R::TierOf(t);
        CHECK(tier != nullptr);
        CHECK_EQN(tier->price80, price[t - 1]);
        CHECK_EQN(tier->buffMin, buff[t - 1]);
        CHECK_EQN(tier->xp, xp[t - 1]);
        CHECK_EQN(tier->tip, tip[t - 1]);
    }
    uint32_t const total[] = { 0, 120, 320, 620, 1040, 1600, 2320, 3220, 4320, 5640 };
    uint8_t const tickets[] = { 1, 1, 1, 2, 2, 2, 2, 3, 3, 3 };
    for (uint8_t l = 1; l <= 10; ++l)
    {
        CHECK_EQN(R::LevelXp(l), total[l - 1]);
        CHECK_EQN(R::Tickets(l), tickets[l - 1]);
    }
    // every level unlocks something new and level 1 makes four drinks
    uint32_t level1 = 0;
    for (D::Recipe const& r : D::Recipes)
        if (r.cafeId == 1 && r.unlock == 1)
            ++level1;
    CHECK_EQN(level1, 4u);
}

TEST("catalogue: every gold zone is at least 375 ms wide and stays so after any shift")
{
    for (D::Action const& a : D::Actions)
    {
        if (a.kind != 'H')
        {
            CHECK_EQN(a.goldLo, 0u);
            continue;
        }
        CHECK(a.goldLo < a.goldHi);
        CHECK_MSG(R::PermilleOf(a.durMs, a.goldHi) - R::PermilleOf(a.durMs, a.goldLo) >= 375, std::string(a.name));
        for (int32_t s : { -50, -1, 0, 1, 50 })
        {
            R::GoldZone const z = R::ShiftGold(a.goldLo, a.goldHi, s);
            CHECK_EQN(z.hi - z.lo, uint32_t(a.goldHi - a.goldLo));
            CHECK(R::PermilleOf(a.durMs, z.hi) - R::PermilleOf(a.durMs, z.lo) >= 374);
        }
    }
}

TEST("catalogue: the default layout's station spots (both cafes)")
{
    for (uint8_t cafe : { uint8_t(1), uint8_t(2) })
    {
        std::vector<R::SpotRef> const spots = DefaultSpots(cafe);
        CHECK_EQN(spots.size(), 14u);
        std::map<char, std::vector<R::SpotRef>> by;
        for (R::SpotRef const& s : spots)
            by[s.station].push_back(s);
        CHECK_EQN(by.size(), 7u);
        for (auto const& [st, list] : by)
        {
            CHECK_EQN(list.size(), 2u);
            // the two spots of a station are 0.7 yd apart, side by side
            CHECK(Near(std::hypot(list[0].x - list[1].x, list[0].y - list[1].y), 0.7f, 0.01f));
        }
        for (auto const& [a, la] : by)
            for (auto const& [b, lb] : by)
            {
                if (a >= b)
                    continue;
                // first spots >= 2.0 yd apart, any spots of different stations >= 1.2 yd
                CHECK_MSG(std::hypot(la[0].x - lb[0].x, la[0].y - lb[0].y) >= 2.0f - 0.001f, std::string(1, a) + b);
                for (R::SpotRef const& x : la)
                    for (R::SpotRef const& y : lb)
                        CHECK_MSG(std::hypot(x.x - y.x, x.y - y.y) >= 1.2f - 0.001f, std::string(1, a) + b);
            }
        // the values of the section 3.12.3 table: the counter's spots at (1.6, +-0.35), the kettle's at (2.4 +- 0.35, 4.4)
        CHECK(Near(by['V'][0].x, 1.6f) && Near(std::fabs(by['V'][0].y), 0.35f));
        CHECK(Near(by['K'][0].y, 4.4f) && Near(std::fabs(by['K'][0].x - 2.4f), 0.35f));
        CHECK(Near(by['C'][0].y, -4.4f));
        CHECK(Near(by['E'][0].x, 4.0f) && Near(by['G'][0].x, 4.0f) && Near(by['S'][0].x, 4.0f));
        CHECK(Near(by['B'][0].x, 1.6f) && Near(std::fabs(by['B'][0].y + 2.0f), 0.35f));
        // a barista at each spot facing the station is at that station
        for (R::SpotRef const& s : spots)
        {
            float const face = std::atan2(s.objY - s.y, s.objX - s.x);
            R::StationHit const h = R::StationAt(s.x, s.y, 0.0f, face, spots, 1.5f, 120.0f);
            CHECK_MSG(h.station == s.station && h.spot == s.spot, std::string(1, s.station));
            CHECK(!h.facingHint);
        }
    }
}

TEST("catalogue: the door is out of sight distance, staff homes and markers")
{
    for (uint8_t cafe : { uint8_t(1), uint8_t(2) })
    {
        D::LayoutPiece const* door = Piece(cafe, 20);
        CHECK(door && door->role == "door");
        CHECK(std::hypot(door->f, door->l) >= 25.0f);
        D::LayoutPiece const* counter = Piece(cafe, 1);
        CHECK(counter && counter->station == 'V' && counter->role == "counter");
        CHECK(Piece(cafe, 10) && Piece(cafe, 10)->role == "order_spot");
        CHECK(Piece(cafe, 11) && Piece(cafe, 11)->role == "pickup_spot");
        for (uint16_t q = 12; q <= 19; ++q)
            CHECK(Piece(cafe, q) && Piece(cafe, q)->role == "queue_" + std::to_string(q - 11));
        D::Cafe const* c = D::FindCafe(cafe);
        CHECK(c != nullptr);
        bool owner = false;
        for (D::LayoutPiece const& p : D::Layout)
            if (p.cafeId == cafe && p.role == "staff_owner")
                owner = p.creature && p.entry == c->owner;
        CHECK(owner);
    }
}

// =================================================================================================================
// Steps
// =================================================================================================================
TEST("Grade: inclusive gold edges, the Good pad, Off, the end of the bar")
{
    // Pull Shot: 3000 ms, gold 2100..2550, pad 10% = 300 ms
    CHECK(R::Grade(2100, 3000, 2100, 2550, 100) == 'P');
    CHECK(R::Grade(2550, 3000, 2100, 2550, 100) == 'P');
    CHECK(R::Grade(2099, 3000, 2100, 2550, 100) == 'G');
    CHECK(R::Grade(2551, 3000, 2100, 2550, 100) == 'G');
    CHECK(R::Grade(1800, 3000, 2100, 2550, 100) == 'G');
    CHECK(R::Grade(2850, 3000, 2100, 2550, 100) == 'G');
    CHECK(R::Grade(1799, 3000, 2100, 2550, 100) == 'O');
    CHECK(R::Grade(2851, 3000, 2100, 2550, 100) == 'O');
    CHECK(R::Grade(0, 3000, 2100, 2550, 100) == 'O');
    CHECK(R::Grade(3000, 3000, 2100, 2550, 100) == 'O');
    CHECK(R::Grade(3300, 3000, 2100, 2550, 100) == 'O');
    // no pad: only the gold
    CHECK(R::Grade(2099, 3000, 2100, 2550, 0) == 'O');
    // a pad below 0 stays at 0; a zone at the end of the bar is still Off at 100%
    CHECK(R::Grade(0, 2000, 100, 900, 100) == 'G');
    CHECK(R::Grade(1999, 2000, 1500, 1900, 100) == 'G');
    CHECK(R::Grade(2000, 2000, 1500, 1900, 100) == 'O');
}

TEST("ReleaseElapsed: the CREL clamp")
{
    // lag = clamp(latency + slack, 100, max): 80 + 150 = 230
    CHECK_EQN(R::ReleaseElapsed(2380, 2500, 80, 150, 400), 2380u);   // what the client saw
    CHECK_EQN(R::ReleaseElapsed(2600, 2500, 80, 150, 400), 2500u);   // never later than the server saw it
    CHECK_EQN(R::ReleaseElapsed(1000, 2500, 80, 150, 400), 2270u);   // never more than lag earlier
    CHECK_EQN(R::ReleaseElapsed(0, 2500, 900, 150, 400), 2100u);     // lag at most LatencyCompMaxMs
    CHECK_EQN(R::ReleaseElapsed(0, 2500, 0, 0, 400), 2400u);         // lag at least 100
    CHECK_EQN(R::ReleaseElapsed(0, 50, 0, 0, 400), 0u);              // never below 0
    CHECK_EQN(R::ReleaseElapsed(30, 50, 0, 0, 400), 30u);
    CHECK_EQN(R::ReleaseElapsed(0, 2500, 0, 0, 50), 2400u);          // a max below 100 counts as 100
}

TEST("ShiftGold: stays inside 5%..95% and keeps its width; the random shift")
{
    R::GoldZone z = R::ShiftGold(700, 850, 50);
    CHECK_EQN(z.lo, 750u);
    CHECK_EQN(z.hi, 900u);
    z = R::ShiftGold(700, 850, 150);
    CHECK_EQN(z.lo, 800u);
    CHECK_EQN(z.hi, 950u);
    z = R::ShiftGold(350, 500, -400);
    CHECK_EQN(z.lo, 50u);
    CHECK_EQN(z.hi, 200u);
    z = R::ShiftGold(900, 980, 0);   // a zone past 95% is moved back in
    CHECK_EQN(z.lo, 870u);
    CHECK_EQN(z.hi, 950u);
    z = R::ShiftGold(850, 700, 0);   // swapped bounds
    CHECK_EQN(z.lo, 700u);
    CHECK_EQN(z.hi, 850u);
    z = R::ShiftGold(0, 1000, 0);    // wider than the window: cut to 900
    CHECK_EQN(z.lo, 50u);
    CHECK_EQN(z.hi, 950u);
    std::set<int32_t> seen;
    for (uint32_t r = 0; r < 1000; ++r)
    {
        int32_t const s = R::GoldShift(r, 50);
        CHECK(s >= -50 && s <= 50);
        seen.insert(s);
    }
    CHECK_EQN(seen.size(), 101u);
    CHECK_EQN(R::GoldShift(12345, 0), 0);
    // the document's example: Pull Shot moved +20, Froth Foam -20
    CHECK_EQN(R::PermilleOf(3000, R::ShiftGold(700, 850, 20).lo), 2160u);
    CHECK_EQN(R::PermilleOf(3000, R::ShiftGold(700, 850, 20).hi), 2610u);
    CHECK_EQN(R::PermilleOf(2000, R::ShiftGold(400, 600, -20).lo), 760u);
    CHECK_EQN(R::PermilleOf(2000, R::ShiftGold(400, 600, -20).hi), 1160u);
}

TEST("ReleaseOffset: from the gold centre")
{
    CHECK_EQN(R::ReleaseOffset(2385, 2160, 2610), 0);
    CHECK_EQN(R::ReleaseOffset(2300, 2160, 2610), -85);
    CHECK_EQN(R::ReleaseOffset(2500, 2160, 2610), 115);
}

// =================================================================================================================
// Quality, XP, points, tips
// =================================================================================================================
TEST("Quality: every combination, the 25% patience rule, taps never lower it")
{
    D::Recipe const& c3 = Rec(103);   // 1, 3, 6, 16, 25: two timed steps (3, 6)
    auto q = [&](char a, char b, uint32_t left) {
        char g[12] = { 'P', a, b, 'P', 'P' };
        return R::Quality(c3.steps.data(), g, c3.stepCount, left);
    };
    for (char a : { 'P', 'G', 'O' })
        for (char b : { 'P', 'G', 'O' })
            for (uint32_t left : { 0u, 249u, 250u, 1000u })
            {
                char const got = q(a, b, left);
                char want = (a == 'O' || b == 'O') ? 'S' : (a == 'P' && b == 'P' && left >= 250 ? 'P' : 'G');
                CHECK_MSG(got == want, std::string(1, a) + b + " " + std::to_string(left));
            }
    // taps (recorded as P, or not even recorded) never lower a drink: only an Off step makes it Sloppy
    char tapsN[12] = { 'N', 'P', 'P', 'N', 'N' };
    CHECK(R::Quality(c3.steps.data(), tapsN, c3.stepCount, 600) == 'P');
    char tapsG[12] = { 'G', 'P', 'P', 'G', 'G' };
    CHECK(R::Quality(c3.steps.data(), tapsG, c3.stepCount, 600) == 'P');
}

TEST("XpForDrink: exact numbers")
{
    auto xp = [](uint8_t tier, char q, uint32_t left, uint32_t streak, bool pair, bool rush, bool tired, uint32_t row) {
        R::DrinkFacts f;
        f.tier = tier; f.quality = q; f.patienceLeftPermille = left; f.streak = streak; f.pairBoost = pair; f.rush = rush;
        f.tired = tired; f.inARow = row;
        return R::XpForDrink(f);
    };
    CHECK_EQN(xp(1, 'P', 600, 1, false, false, false, 1), 14u);     // 8 x 1.5 x 1.2 (the walkthrough)
    CHECK_EQN(xp(1, 'G', 400, 0, false, false, false, 1), 8u);
    CHECK_EQN(xp(1, 'S', 400, 0, false, false, false, 1), 4u);
    CHECK_EQN(xp(1, 'R', 900, 0, false, false, false, 1), 0u);
    CHECK_EQN(xp(1, 'L', 900, 0, false, false, false, 1), 0u);
    CHECK_EQN(xp(2, 'P', 600, 1, true, false, false, 1), 32u);      // 12 x 1.5 x 1.2 x 1.5 (CAFRES 4p of the document)
    CHECK_EQN(xp(5, 'P', 600, 6, false, false, false, 1), 78u);     // 35 x 1.5 x 1.2 x 1.25 = 78.75
    CHECK_EQN(xp(5, 'P', 600, 20, false, false, false, 1), 78u);    // the streak stops at 1.25
    CHECK_EQN(xp(3, 'P', 500, 3, false, true, false, 1), 44u);      // 18 x 1.5 x 1.2 x 1.1 x 1.25 = 44.55
    CHECK_EQN(xp(3, 'G', 499, 0, false, true, true, 1), 11u);       // 18 x 1.25 x 0.5 = 11.25
    CHECK_EQN(xp(4, 'G', 800, 0, false, false, false, 4), 22u);     // 25 x 1.2 x 0.75 = 22.5
    CHECK_EQN(xp(4, 'G', 800, 0, false, false, false, 5), 15u);     // 25 x 1.2 x 0.5
    CHECK_EQN(xp(4, 'G', 800, 0, false, false, false, 9), 15u);     // the floor is 0.5
    CHECK_EQN(xp(2, 'G', 800, 0, false, false, false, 3), 14u);     // the third in a row still counts fully
    CHECK_EQN(xp(9, 'G', 800, 0, false, false, false, 1), 0u);      // no such tier
}

TEST("CreditXp: the daily cap, split across the full and half bands")
{
    R::XpCredit c = R::CreditXp(14, 0, 0, 450, 450);
    CHECK_EQN(c.credited, 14u);
    CHECK_EQN(c.cut, 0u);
    CHECK_EQN(c.fullUsed, 14u);
    c = R::CreditXp(20, 440, 0, 450, 450);           // 10 full + 10 half (= 5)
    CHECK_EQN(c.credited, 15u);
    CHECK_EQN(c.cut, 5u);
    CHECK_EQN(c.fullUsed, 450u);
    CHECK_EQN(c.halfUsed, 10u);
    c = R::CreditXp(7, 450, 10, 450, 450);           // half of 7 over the day: (17 / 2) - (10 / 2) = 3
    CHECK_EQN(c.credited, 3u);
    CHECK_EQN(c.cut, 4u);
    c = R::CreditXp(1, 450, 17, 450, 450);           // the next one makes the pair whole: 9 - 8 = 1
    CHECK_EQN(c.credited, 1u);
    CHECK_EQN(c.cut, 0u);
    c = R::CreditXp(30, 450, 440, 450, 450);         // 10 half (5), then nothing
    CHECK_EQN(c.credited, 5u);
    CHECK_EQN(c.cut, 25u);
    CHECK_EQN(c.halfUsed, 450u);
    c = R::CreditXp(30, 450, 450, 450, 450);
    CHECK_EQN(c.credited, 0u);
    CHECK_EQN(c.cut, 30u);
    // a whole day: at most 450 + 225 credited
    uint32_t full = 0, half = 0, total = 0;
    for (int i = 0; i < 200; ++i)
    {
        R::XpCredit const d = R::CreditXp(13, full, half, 450, 450);
        full = d.fullUsed;
        half = d.halfUsed;
        total += d.credited;
        CHECK_EQN(d.credited + d.cut, 13u);
    }
    CHECK_EQN(total, 675u);
    // a lowered cap: the day row above it counts as full
    c = R::CreditXp(10, 600, 0, 450, 450);
    CHECK_EQN(c.credited, 5u);
    CHECK_EQN(c.fullUsed, 450u);
}

TEST("Points: no streak, pair or repeat factor; the daily cap with and without the Rush")
{
    R::DrinkFacts f;
    f.tier = 2; f.quality = 'P'; f.patienceLeftPermille = 600; f.streak = 5; f.pairBoost = true; f.inARow = 6;
    CHECK_EQN(R::PointsForDrink(f), 22u);            // 12 x 1.5 x 1.2 = 21.6 (CAFRES 4p of the document)
    f.rush = true;
    CHECK_EQN(R::PointsForDrink(f), 27u);            // x 1.25 = 27
    f.tired = true;
    CHECK_EQN(R::PointsForDrink(f), 14u);            // x 0.5 = 13.5, rounded
    f = {};
    f.tier = 1; f.quality = 'S'; f.patienceLeftPermille = 100;
    CHECK_EQN(R::PointsForDrink(f), 4u);
    CHECK_EQN(R::PointsCap(400, 100, false), 400u);
    CHECK_EQN(R::PointsCap(400, 100, true), 500u);
    CHECK_EQN(R::CapAdd(22, 390, 400), 10u);
    CHECK_EQN(R::CapAdd(22, 400, 400), 0u);
    CHECK_EQN(R::CapAdd(22, 450, 400), 0u);
    CHECK_EQN(R::CapAdd(22, 0, 400), 22u);
}

TEST("Tip: the formula and the daily cap")
{
    CHECK_EQN(R::TipForDrink(1, 'P', 100, 34, false, 1), 255u);   // 4s x 1.5 x 34/80 (the walkthrough)
    CHECK_EQN(R::TipForDrink(1, 'G', 100, 80, false, 1), 400u);
    CHECK_EQN(R::TipForDrink(1, 'S', 100, 80, false, 1), 160u);
    CHECK_EQN(R::TipForDrink(1, 'L', 100, 80, false, 1), 0u);
    CHECK_EQN(R::TipForDrink(1, 'G', 100, 1, false, 1), 60u);     // at least 15% of the level-80 tip
    CHECK_EQN(R::TipForDrink(1, 'G', 100, 12, false, 1), 60u);
    CHECK_EQN(R::TipForDrink(5, 'P', 180, 80, true, 9), 8019u);   // 18s x 1.5 x 1.8 x 1.5 x 1.1 = 80s 19c
    CHECK_EQN(R::TipForDrink(5, 'P', 180, 80, true, 8), 7290u);
    CHECK_EQN(R::TipForDrink(2, 'G', 30, 40, false, 1), 90u);     // a child's 30%
    CHECK_EQN(R::TipCap(5000, 2500, 80), 205000u);                // 20g 50s at level 80
    CHECK_EQN(R::TipCap(5000, 2500, 10), 30000u);
}

TEST("PriceCopper: levels 1, 10, 40, 70, 80; the minimum; whole silver")
{
    CHECK_EQN(R::PriceCopper(4000, 1, 200, 10), 400u);       // the 10% floor
    CHECK_EQN(R::PriceCopper(4000, 10, 200, 10), 500u);      // 1/8
    CHECK_EQN(R::PriceCopper(4000, 40, 200, 10), 2000u);
    CHECK_EQN(R::PriceCopper(6000, 40, 200, 10), 3000u);
    CHECK_EQN(R::PriceCopper(18000, 40, 200, 10), 9000u);
    CHECK_EQN(R::PriceCopper(4000, 80, 200, 10), 4000u);
    CHECK_EQN(R::PriceCopper(6000, 44, 200, 10), 3300u);     // 33s (the walkthrough's cappuccino)
    // the document's menu at level 70: 7/8, rounded up to whole silver
    CHECK_EQN(R::PriceCopper(4000, 70, 200, 10), 3500u);
    CHECK_EQN(R::PriceCopper(6000, 70, 200, 10), 5300u);
    CHECK_EQN(R::PriceCopper(18000, 70, 200, 10), 15800u);
    CHECK_EQN(R::PriceCopper(1000, 1, 200, 10), 200u);       // the minimum
    CHECK_EQN(R::PriceCopper(4000, 1, 200, 0), 200u);        // no floor: 50 c, then the minimum
    CHECK_EQN(R::PriceCopper(4100, 13, 0, 10), 700u);        // 666.25 -> 7s
    CHECK_EQN(R::TipCopper(5300, 10), 530u);
    CHECK_EQN(R::TipCopper(333, 25), 83u);
    CHECK_EQN(R::TipCopper(333, 0), 0u);
}

TEST("RepeatPct, PairBoost, StreakHundredths")
{
    CHECK_EQN(R::RepeatPct(1), 100u);
    CHECK_EQN(R::RepeatPct(3), 100u);
    CHECK_EQN(R::RepeatPct(4), 75u);
    CHECK_EQN(R::RepeatPct(5), 50u);
    CHECK_EQN(R::RepeatPct(50), 50u);
    CHECK(R::PairBoost(0, 3));
    CHECK(R::PairBoost(2, 3));
    CHECK(!R::PairBoost(3, 3));
    CHECK(!R::PairBoost(0, 0));
    CHECK_EQN(R::StreakHundredths(0), 100u);
    CHECK_EQN(R::StreakHundredths(1), 100u);
    CHECK_EQN(R::StreakHundredths(2), 105u);
    CHECK_EQN(R::StreakHundredths(6), 125u);
    CHECK_EQN(R::StreakHundredths(7), 125u);
}

// =================================================================================================================
// Patience, arrivals, house
// =================================================================================================================
TEST("PatienceMs: queue and drink phases, the Rush")
{
    CHECK_EQN(R::QueuePatienceMs(60, 100, false), 60000u);
    CHECK_EQN(R::QueuePatienceMs(60, 80, false), 48000u);    // CAFQ 4e of the document: Corwin
    CHECK_EQN(R::QueuePatienceMs(60, 140, true), 71400u);    // 84 s x 0.85
    CHECK_EQN(R::DrinkPatienceMs(30, 6, 4, 80, false), 43200u);   // CAFT 4f: Corwin's Cathedral Black
    CHECK_EQN(R::DrinkPatienceMs(30, 6, 5, 100, false), 60000u);  // CAFT 4f: Brenna's cappuccino (the generic 100%)
    CHECK_EQN(R::DrinkPatienceMs(30, 6, 6, 100, true), 56100u);
    CHECK_EQN(R::PatienceLeftPermille(1000, 31000, 60000), 500u);
    CHECK_EQN(R::PatienceLeftPermille(31000, 31000, 60000), 0u);
    CHECK_EQN(R::PatienceLeftPermille(40000, 31000, 60000), 0u);
    CHECK_EQN(R::PatienceLeftPermille(0, 90000, 60000), 1000u);
    CHECK_EQN(R::PatienceLeftPermille(0, 90000, 0), 0u);
}

TEST("ArrivalIntervalMs: 0 to 5 baristas and the Rush")
{
    CHECK_EQN(R::ArrivalIntervalMs(30, 160, 0, false), 60000u);   // ambient: x2
    CHECK_EQN(R::ArrivalIntervalMs(30, 160, 1, false), 30000u);
    CHECK_EQN(R::ArrivalIntervalMs(30, 160, 2, false), 18750u);   // / 1.6
    CHECK_EQN(R::ArrivalIntervalMs(30, 160, 3, false), 11718u);   // / 2.56
    CHECK_EQN(R::ArrivalIntervalMs(30, 160, 4, false), 7323u);    // / 4.096
    CHECK_EQN(R::ArrivalIntervalMs(30, 160, 5, false), 7323u);    // no faster past 4
    CHECK_EQN(R::ArrivalIntervalMs(30, 160, 1, true), 12000u);    // / 2.5
    CHECK_EQN(R::ArrivalIntervalMs(30, 160, 0, true), 24000u);
    CHECK_EQN(R::ArrivalIntervalMs(30, 100, 4, false), 30000u);
    CHECK_EQN(R::ArrivalIntervalMs(30, 50, 4, false), 30000u);    // a factor below 100% never slows it down
    CHECK_EQN(R::HouseMinTotalMs(30, 5, 4), 50000u);
}

// =================================================================================================================
// Buffs and rewards
// =================================================================================================================
TEST("BuffMinutes and the merge rule; the Lingering Sip")
{
    CHECK_EQN(R::BuffMinutes(1, false, false, false, 60), 30u);
    CHECK_EQN(R::BuffMinutes(1, true, false, false, 60), 40u);
    CHECK_EQN(R::BuffMinutes(3, true, true, false, 60), 60u);
    CHECK_EQN(R::BuffMinutes(5, true, true, true, 60), 60u);      // capped
    CHECK_EQN(R::BuffMinutes(5, false, false, false, 60), 50u);
    CHECK_EQN(R::BuffMinutes(5, false, false, false, 45), 45u);
    CHECK_EQN(R::MergeBuffMs(10 * 60000, 30 * 60000), 30u * 60000);
    CHECK_EQN(R::MergeBuffMs(50 * 60000, 30 * 60000), 50u * 60000);
    CHECK_EQN(R::LingerMs(30 * 60000, 60), 40u * 60000);
    CHECK_EQN(R::LingerMs(55 * 60000, 60), 60u * 60000);
}

TEST("ShakeActive: the truth table")
{
    R::ShakeFacts on;
    on.visibleBuff = true;
    on.restCity = true;
    CHECK(R::ShakeActive(on));
    R::ShakeFacts f = on;
    f.restCity = false;
    CHECK(!R::ShakeActive(f));                      // not resting (the camp's faction-area bit alone is not rest)
    f.restTavern = true;
    CHECK(R::ShakeActive(f));                       // an inn
    auto off = [&](bool R::ShakeFacts::*field, bool value) {
        R::ShakeFacts g = on;
        g.*field = value;
        return !R::ShakeActive(g);
    };
    CHECK(off(&R::ShakeFacts::visibleBuff, false)); // Sugar Rush cancelled by right-click: the helper must go
    CHECK(off(&R::ShakeFacts::featureOn, false));   // the feature off: a helper carried in is removed
    CHECK(off(&R::ShakeFacts::inCombat, true));
    CHECK(off(&R::ShakeFacts::pvp, true));
    CHECK(off(&R::ShakeFacts::ffaPvp, true));
    CHECK(off(&R::ShakeFacts::duel, true));         // a duel requested or running
    CHECK(off(&R::ShakeFacts::mounted, true));
    CHECK(off(&R::ShakeFacts::vehicle, true));
    CHECK(off(&R::ShakeFacts::flight, true));
    CHECK(off(&R::ShakeFacts::worldMap, false));
    CHECK(off(&R::ShakeFacts::alive, false));
    // the helper follows: added when missing, removed when the rule says off, given the buff's time after a merge
    CHECK(R::ShakeHelper(true, false, 0, 600000) == R::HelperAction::Add);
    CHECK(R::ShakeHelper(false, true, 500000, 600000) == R::HelperAction::Remove);
    CHECK(R::ShakeHelper(false, false, 0, 0) == R::HelperAction::None);
    CHECK(R::ShakeHelper(true, true, 600000, 600500) == R::HelperAction::None);
    CHECK(R::ShakeHelper(true, true, 300000, 2400000) == R::HelperAction::Follow);   // the visible buff was merged
    CHECK(R::ShakeHelper(true, true, 2400000, 300000) == R::HelperAction::Follow);
}

TEST("BonusPctWithCoffee: food or coffee, never both")
{
    CHECK_EQN(CampRules::BonusPctWithCoffee(false, 10, true, 5, false, 5, 25), 5u);   // food only
    CHECK_EQN(CampRules::BonusPctWithCoffee(false, 10, false, 5, true, 5, 25), 5u);   // coffee only
    CHECK_EQN(CampRules::BonusPctWithCoffee(false, 10, true, 5, true, 5, 25), 5u);    // both: 5, not 10
    CHECK_EQN(CampRules::BonusPctWithCoffee(true, 10, true, 5, true, 5, 25), 15u);    // warmth plus both
    CHECK_EQN(CampRules::BonusPctWithCoffee(true, 10, false, 0, true, 5, 25), 15u);   // camping's food off, coffee on
    CHECK_EQN(CampRules::BonusPctWithCoffee(true, 20, true, 8, true, 9, 25), 25u);    // the cap
    CHECK_EQN(CampRules::BonusPctWithCoffee(false, 10, false, 5, false, 5, 25), 0u);
    CHECK_EQN(CampRules::BonusPctWithCoffee(false, 0, true, 5, true, 7, 25), 7u);     // the better of the two
    // the camp's own rule is unchanged
    CHECK_EQN(CampRules::BonusPct(true, true, 10, 5, 25), 15u);
}

TEST("RewardPlaceOk and TeaExcludesFaction")
{
    CHECK(R::RewardPlaceOk(false, false));
    CHECK(!R::RewardPlaceOk(true, false));
    CHECK(!R::RewardPlaceOk(false, true));          // Wintergrasp
    std::vector<uint32_t> const pvp = R::ParseIds("509,510,729,730,889,890");
    CHECK_EQN(pvp.size(), 6u);
    for (uint32_t f : { 509u, 510u, 729u, 730u, 889u, 890u })
        CHECK(R::TeaExcludesFaction(pvp, f));
    CHECK(!R::TeaExcludesFaction(pvp, 72));         // Stormwind
    CHECK(!R::TeaExcludesFaction({}, 509));
    CHECK_EQN(R::ParseIds(" 1, 2;3  44 ").size(), 4u);
    CHECK_EQN(R::ParseIds("").size(), 0u);
    CHECK_EQN(R::ParseIds("99999999999")[0], 0xFFFFFFFFu);
}

// =================================================================================================================
// Days, weeks, the weekly board
// =================================================================================================================
TEST("PeriodId, DayBit and the fallback resets")
{
    CHECK_EQN(R::PeriodId(1793923200, R::DaySec), 20763u);
    CHECK_EQN(R::PeriodId(1793923200 + 86399, R::DaySec), 20763u);
    CHECK_EQN(R::PeriodId(1793923200, R::WeekSec), 2966u);
    CHECK_EQN(R::PeriodId(5, 0), 0u);
    std::set<uint8_t> bits;
    for (uint32_t d = 20760; d < 20767; ++d)
        bits.insert(R::DayBit(d));
    CHECK_EQN(bits.size(), 7u);
    CHECK_EQN(R::Bits(0x7F), 7u);
    CHECK_EQN(R::Bits(0x15), 3u);
    // 2026-10-28 (a Wednesday) 12:00 UTC; the reset at 06:00 UTC is tomorrow's, the weekly one next Wednesday
    uint32_t const now = 1793188800;
    uint32_t const daily = R::FallbackDailyReset(now, 0, 6);
    CHECK_EQN(daily, 1793253600u);
    CHECK(daily > now && daily - now <= 86400);
    uint32_t const weekly = R::FallbackWeeklyReset(now, 0, 6, 3);
    CHECK_EQN(weekly, 1793253600u + 6 * 86400);
    // before 06:00 it is today's
    CHECK_EQN(R::FallbackDailyReset(1793145600 + 3600, 0, 6), 1793145600u + 6 * 3600);
    // a time zone: 06:00 in UTC+2 is 04:00 UTC
    CHECK_EQN(R::FallbackDailyReset(now, 7200, 6), 1793246400u);
}

TEST("WeeklyRank: eligibility and the tie-breaks; Payout")
{
    auto row = [](uint32_t guid, uint32_t points, uint32_t drinks, uint32_t perfects, uint8_t days, uint32_t at) {
        R::WeekRow r;
        r.guid = guid; r.points = points; r.drinks = drinks; r.perfects = perfects; r.daysMask = days; r.scoreAt = at;
        return r;
    };
    std::vector<R::WeekRow> rows = {
        row(1, 2310, 142, 115, 0x1F, 900),
        row(2, 1830, 96, 76, 0x0F, 800),
        row(3, 1830, 96, 80, 0x07, 950),    // same points, better Perfect rate: before 2
        row(4, 1830, 96, 76, 0x07, 700),    // same points and rate as 2, earlier: before 2
        row(5, 5000, 49, 49, 0x7F, 100),    // too few drinks
        row(6, 5000, 300, 290, 0x03, 100),  // too few days
        row(7, 1830, 96, 76, 0x07, 700),    // all equal to 4: the guid decides
    };
    std::vector<R::WeekRow> const ranked = R::WeeklyRank(rows, 50, 3);
    CHECK_EQN(ranked.size(), 5u);
    uint32_t const order[] = { 1, 3, 4, 7, 2 };
    for (std::size_t i = 0; i < ranked.size() && i < 5; ++i)
        CHECK_EQN(ranked[i].guid, order[i]);
    CHECK(R::WeeklyEligible(rows[0], 50, 3));
    CHECK(!R::WeeklyEligible(rows[4], 50, 3));
    CHECK(!R::WeeklyEligible(rows[5], 50, 3));
    CHECK_EQN(R::PerfectPermille(115, 142), 809u);
    CHECK_EQN(R::PerfectPermille(1, 0), 0u);
    std::vector<uint32_t> const rewards = R::ParseIds("500000,300000,200000,50000,50000,50000,50000,50000,50000,50000");
    CHECK_EQN(R::Payout(1, rewards), 500000u);
    CHECK_EQN(R::Payout(3, rewards), 200000u);
    CHECK_EQN(R::Payout(10, rewards), 50000u);
    CHECK_EQN(R::Payout(11, rewards), 0u);
    CHECK_EQN(R::Payout(0, rewards), 0u);
}

// =================================================================================================================
// Tired
// =================================================================================================================
TEST("Tired: an hour on shift, a quarter-hour break; it survives death and relog (the row holds it)")
{
    uint32_t const t0 = 1000000;
    R::TiredRow row;
    row = R::TiredOnShiftStart(row, t0, 15);
    CHECK(!R::IsTired(row, t0, 60, 15));
    CHECK_EQN(*R::TiredSec(row, t0, true, 60, 15), 3600u);
    row.accumSec = 3599;
    CHECK(!R::IsTired(row, t0, 60, 15));
    CHECK_EQN(*R::TiredSec(row, t0, true, 60, 15), 1u);
    row.accumSec = 3600;
    CHECK(R::IsTired(row, t0, 60, 15));
    CHECK_EQN(*R::TiredSec(row, t0, true, 60, 15), 900u);   // on shift: the whole break is still needed
    // the shift ends; 10 minutes off is not enough
    row.offSince = t0;
    CHECK(R::IsTired(row, t0 + 600, 60, 15));
    CHECK_EQN(*R::TiredSec(row, t0 + 600, false, 60, 15), 300u);
    // a new shift after 10 minutes keeps the hour (and Tired)
    R::TiredRow early = R::TiredOnShiftStart(row, t0 + 600, 15);
    CHECK_EQN(early.accumSec, 3600u);
    CHECK_EQN(early.offSince, 0u);
    CHECK(R::IsTired(early, t0 + 700, 60, 15));
    // 15 minutes off: rested, and a new shift starts from zero
    CHECK(!R::IsTired(row, t0 + 900, 60, 15));
    CHECK(!R::TiredSec(row, t0 + 900, false, 60, 15));
    R::TiredRow rested = R::TiredOnShiftStart(row, t0 + 900, 15);
    CHECK_EQN(rested.accumSec, 0u);
    // a short break inside the hour does not reset the time either
    R::TiredRow part;
    part.accumSec = 1800;
    part.offSince = t0;
    part = R::TiredOnShiftStart(part, t0 + 60, 15);
    CHECK_EQN(part.accumSec, 1800u);
    // the test settings of the integration plan: Tired.AfterMin = 2
    R::TiredRow quick;
    quick.accumSec = 120;
    CHECK(R::IsTired(quick, t0, 2, 15));
}

// =================================================================================================================
// Money (section 3.8.6)
// =================================================================================================================
TEST("SettleOrder: the money invariant for every live path and every startup settlement")
{
    std::vector<std::pair<uint32_t, uint32_t>> const orders = {
        { 5300, 530 }, { 3000, 300 }, { 333, 83 }, { 200, 0 }, { 15800, 7900 }, { 1, 0 }, { 99999, 49999 },
    };
    R::OrderEnd const ends[] = {
        R::OrderEnd::ServedDelivered, R::OrderEnd::ServedExpired, R::OrderEnd::HouseDelivered, R::OrderEnd::HouseExpired,
        R::OrderEnd::Cancelled, R::OrderEnd::StartupOpen, R::OrderEnd::StartupReadyPaid, R::OrderEnd::StartupReadyHouse,
    };
    for (uint32_t share : { 0u, 40u, 60u, 100u })
        for (auto const& [price, tip] : orders)
            for (R::OrderEnd e : ends)
            {
                R::Money const m = R::SettleOrder(e, price, tip, share);
                CHECK_EQN(m.paid, price + tip);
                CHECK_EQN(uint64_t(m.barista) + m.house + m.refunded, uint64_t(m.paid));
                CHECK(m.refunded <= m.paid);
                CHECK(m.barista <= m.paid);
            }
    // the numbers: a 30s cappuccino with a 3s tip, 60% to the barista
    R::Money m = R::SettleOrder(R::OrderEnd::ServedDelivered, 3000, 300, 60);
    CHECK_EQN(m.barista, 2100u);                   // CAFRES 4p of the document
    CHECK_EQN(m.house, 1200u);
    CHECK_EQN(m.refunded, 0u);
    m = R::SettleOrder(R::OrderEnd::ServedExpired, 3000, 300, 60);
    CHECK_EQN(m.refunded, 1200u);                  // the house share, 40% of the price
    CHECK_EQN(m.house, 0u);
    m = R::SettleOrder(R::OrderEnd::HouseExpired, 3000, 300, 60);
    CHECK_EQN(m.refunded, 1200u);
    CHECK_EQN(m.barista, 0u);
    CHECK_EQN(m.house, 2100u);                     // the barista's share and the tip stay sunk
    m = R::SettleOrder(R::OrderEnd::HouseDelivered, 3000, 300, 60);
    CHECK_EQN(m.house, 3300u);
    m = R::SettleOrder(R::OrderEnd::Cancelled, 3000, 300, 60);
    CHECK_EQN(m.refunded, 3300u);
    // startup: what the table says decides
    CHECK(R::StartupEnd('W', false) == R::OrderEnd::StartupOpen);
    CHECK(R::StartupEnd('T', false) == R::OrderEnd::StartupOpen);
    CHECK(R::StartupEnd('H', false) == R::OrderEnd::StartupOpen);
    CHECK(R::StartupEnd('R', true) == R::OrderEnd::StartupReadyPaid);
    CHECK(R::StartupEnd('R', false) == R::OrderEnd::StartupReadyHouse);
    // a crash after the wage was committed (R with a barista): the customer gets the house share, never the wage again
    m = R::SettleOrder(R::StartupEnd('R', true), 3000, 300, 60);
    CHECK_EQN(m.refunded + m.barista + m.house, 3300u);
    CHECK_EQN(m.refunded, 1200u);
    // odd prices: never a copper from nothing
    m = R::SettleOrder(R::OrderEnd::ServedExpired, 333, 83, 60);
    CHECK_EQN(m.barista, 282u);                    // 199 + 83
    CHECK_EQN(m.refunded, 133u);
    CHECK_EQN(m.house, 1u);
    CHECK_EQN(R::WageCopper(3000, 300, 150), 3300u);   // a share above 100 counts as 100
}

TEST("TakeoverDue and CancelAllowed")
{
    CHECK(!R::TakeoverDue(1000, 2000, 0, 2));
    CHECK(R::TakeoverDue(2000, 2000, 0, 2));        // the drink patience ran out
    CHECK(R::TakeoverDue(1000, 2000, 2, 2));        // ruined twice
    CHECK(!R::TakeoverDue(1000, 2000, 1, 2));
    CHECK(R::CancelAllowed('W', false));
    CHECK(R::CancelAllowed('H', true));
    CHECK(!R::CancelAllowed('H', false));           // the house makes it anyway: no refund
    CHECK(!R::CancelAllowed('T', false));
    CHECK(!R::CancelAllowed('R', false));
}

// =================================================================================================================
// Danger (section 3.4.6)
// =================================================================================================================
TEST("HostileQualifies: stealth, invisibility, height, line of sight, the radii")
{
    R::HostileFacts h;
    h.otherTeam = true; h.pvp = true; h.alive = true; h.los = true; h.dist2d = 10; h.dz = 0;
    CHECK(R::HostileQualifies(h, 15, 40, 5));
    auto no = [&](void (*change)(R::HostileFacts&)) {
        R::HostileFacts g = h;
        change(g);
        return !R::HostileQualifies(g, 15, 40, 5);
    };
    CHECK(no([](R::HostileFacts& g) { g.otherTeam = false; }));
    CHECK(no([](R::HostileFacts& g) { g.pvp = false; }));
    CHECK(no([](R::HostileFacts& g) { g.alive = false; }));
    CHECK(no([](R::HostileFacts& g) { g.gm = true; }));
    CHECK(no([](R::HostileFacts& g) { g.spectator = true; }));
    CHECK(no([](R::HostileFacts& g) { g.stealth = true; }));      // a stealthed rogue at the counter
    CHECK(no([](R::HostileFacts& g) { g.invisible = true; }));
    CHECK(no([](R::HostileFacts& g) { g.los = false; }));
    CHECK(no([](R::HostileFacts& g) { g.dz = 10; }));             // on a roof above
    CHECK(no([](R::HostileFacts& g) { g.dz = -5.5f; }));
    CHECK(no([](R::HostileFacts& g) { g.dist2d = 20; }));         // past the near radius, not fighting
    R::HostileFacts fight = h;
    fight.dist2d = 35;
    fight.inCombat = true;
    CHECK(R::HostileQualifies(fight, 15, 40, 5));                 // fighting within 40 yd
    fight.dist2d = 41;
    CHECK(!R::HostileQualifies(fight, 15, 40, 5));
    R::HostileFacts edge = h;
    edge.dist2d = 15;
    edge.dz = 5;
    CHECK(R::HostileQualifies(edge, 15, 40, 5));
}

TEST("DangerStep: pause, resume 20 s after, close after 90 s, reopen 120 s after")
{
    R::DangerTimes const t;
    R::Danger d;
    // a hostile appears; confirmed after 5 s (the caller's per-player clock)
    CHECK(R::DangerStep(d, false, true, 1000, t) == R::DangerEvent::None);
    CHECK_EQN(d.open, 1u);
    CHECK(R::DangerStep(d, true, true, 6000, t) == R::DangerEvent::Paused);
    CHECK_EQN(d.open, 2u);
    // it leaves at 10 s; 19 s later still paused, 20 s later open again
    CHECK(R::DangerStep(d, false, true, 10000, t) == R::DangerEvent::None);
    CHECK(R::DangerStep(d, false, false, 29000, t) == R::DangerEvent::None);
    CHECK(R::DangerStep(d, false, false, 30000, t) == R::DangerEvent::Resumed);
    CHECK_EQN(d.open, 1u);
    // one who stays: the pause lasts 90 s and becomes a close
    CHECK(R::DangerStep(d, true, true, 100000, t) == R::DangerEvent::Paused);
    for (uint64_t now = 101000; now < 190000; now += 1000)
        CHECK(R::DangerStep(d, true, true, now, t) == R::DangerEvent::None);
    CHECK(R::DangerStep(d, true, true, 190000, t) == R::DangerEvent::Closed);
    CHECK_EQN(d.open, 4u);
    // closed while they stay; 120 s after the last one is gone it reopens
    CHECK(R::DangerStep(d, false, true, 200000, t) == R::DangerEvent::None);
    CHECK(R::DangerStep(d, false, false, 319000, t) == R::DangerEvent::None);
    CHECK(R::DangerStep(d, false, false, 320000, t) == R::DangerEvent::Reopened);
    CHECK_EQN(d.open, 1u);
    // an unconfirmed hostile never starts a pause
    R::Danger e;
    for (uint64_t now = 0; now < 60000; now += 1000)
        CHECK(R::DangerStep(e, false, true, now, t) == R::DangerEvent::None);
    CHECK_EQN(e.open, 1u);
}

// =================================================================================================================
// The Morning Rush
// =================================================================================================================
TEST("ParseRushTimes and RushAt: soon, live, none, across midnight")
{
    std::vector<uint32_t> const times = R::ParseRushTimes("08:00, 17:30,bad,25:00,7:5,9:05");
    CHECK_EQN(times.size(), 3u);
    CHECK_EQN(times[0], 8u * 3600);
    CHECK_EQN(times[1], 9u * 3600 + 300);
    CHECK_EQN(times[2], 17u * 3600 + 1800);
    CHECK_EQN(R::ParseRushTimes("").size(), 0u);
    std::vector<uint32_t> const eight = { 8 * 3600 };
    int64_t const day = 20000ll * 86400;
    R::RushClock c = R::RushAt(day + 7 * 3600 + 54 * 60, eight, 20, 5);
    CHECK_EQN(c.state, 0u);
    c = R::RushAt(day + 7 * 3600 + 57 * 60, eight, 20, 5);
    CHECK_EQN(c.state, 1u);
    CHECK_EQN(c.secTo, 180u);                        // CAFE 4a of the document: 180 s to the Rush
    c = R::RushAt(day + 8 * 3600, eight, 20, 5);
    CHECK_EQN(c.state, 2u);
    CHECK_EQN(c.secTo, 1200u);
    CHECK_EQN(c.startLocal, day + 8 * 3600);
    c = R::RushAt(day + 8 * 3600 + 1199, eight, 20, 5);
    CHECK_EQN(c.state, 2u);
    CHECK_EQN(c.secTo, 1u);
    c = R::RushAt(day + 8 * 3600 + 1200, eight, 20, 5);
    CHECK_EQN(c.state, 0u);
    std::vector<uint32_t> const late = { 23 * 3600 + 50 * 60 };
    c = R::RushAt(day + 86400 + 300, late, 20, 5);   // 00:05 the next day: still live
    CHECK_EQN(c.state, 2u);
    CHECK_EQN(c.secTo, 300u);
    c = R::RushAt(day + 86400 - 21 * 60, late, 20, 5);   // 23:39: not yet soon
    CHECK_EQN(c.state, 0u);
    c = R::RushAt(day + 86400 - 11 * 60, late, 20, 5);   // 23:49: soon
    CHECK_EQN(c.state, 1u);
    CHECK_EQN(c.secTo, 60u);
    c = R::RushAt(day + 86400 - 21 * 60, late, 20, 5);
    CHECK_EQN(c.state, 0u);
}

TEST("RushResume: the goal scaled after a restart, or skipped with < 5 min left")
{
    R::RushResumePlan p = R::RushResume(12 * 60, 20, 60, 5);
    CHECK(p.resume);
    CHECK_EQN(p.minutesLeft, 12u);
    CHECK_EQN(p.goal, 36u);
    CHECK_EQN(p.survivorMin, 3u);
    p = R::RushResume(7 * 60 + 30, 20, 60, 5);
    CHECK(p.resume);
    CHECK_EQN(p.goal, 21u);                          // ceil(60 x 7 / 20)
    CHECK_EQN(p.survivorMin, 2u);                    // ceil(5 x 7 / 20)
    p = R::RushResume(5 * 60, 20, 60, 1);
    CHECK(p.resume);
    CHECK_EQN(p.survivorMin, 1u);                    // at least 1
    p = R::RushResume(299, 20, 60, 5);
    CHECK(!p.resume);
    p = R::RushResume(20 * 60, 20, 60, 5);
    CHECK_EQN(p.goal, 60u);
    p = R::RushResume(600, 0, 60, 5);
    CHECK(!p.resume);
}

// =================================================================================================================
// Shifts
// =================================================================================================================
TEST("ShiftTick: death, AFK, idle, the mounted and radius warnings")
{
    R::ShiftLimits const l;
    R::ShiftTimers t;
    R::ShiftFacts f;
    f.lastActionMs = 1000;
    CHECK(R::ShiftTick(f, t, 2000, l).end == 0);
    R::ShiftFacts dead = f;
    dead.alive = false;
    CHECK(R::ShiftTick(dead, t, 2000, l).end == 'D');
    R::ShiftFacts away = f;
    away.sameMap = false;
    CHECK(R::ShiftTick(away, t, 2000, l).end == 'D');
    R::ShiftFacts afk = f;
    afk.afk = true;
    CHECK(R::ShiftTick(afk, t, 2000, l).end == 'A');
    // idle: 300 s without any action, 120 s with a ticket
    CHECK(R::ShiftTick(f, t, 1000 + 299999, l).end == 0);
    CHECK(R::ShiftTick(f, t, 1000 + 300000, l).end == 'I');
    R::ShiftFacts holding = f;
    holding.holdsTicket = true;
    CHECK(R::ShiftTick(holding, t, 1000 + 119999, l).end == 0);
    CHECK(R::ShiftTick(holding, t, 1000 + 120000, l).end == 'I');
    // mounted: warned (flag 64, 5 s), ended after 5 s; getting down clears it
    R::ShiftFacts mounted = f;
    mounted.hidden = true;
    R::ShiftVerdict v = R::ShiftTick(mounted, t, 10000, l);
    CHECK(v.end == 0);
    CHECK_EQN(v.flags, uint32_t(CafeFlagHidden));
    CHECK(v.warnSec && *v.warnSec == 5);
    v = R::ShiftTick(mounted, t, 12500, l);
    CHECK(v.warnSec && *v.warnSec == 3);
    v = R::ShiftTick(f, t, 13000, l);
    CHECK(v.end == 0 && v.flags == 0 && !v.warnSec);
    CHECK_EQN(t.hiddenSinceMs, 0u);
    R::ShiftTick(mounted, t, 20000, l);
    CHECK(R::ShiftTick(mounted, t, 25000, l).end == 'M');
    // outside 30 yd: warned (flag 8, 10 s), ended after 10 s
    R::ShiftTimers t2;
    R::ShiftFacts far = f;
    far.anchorDist = 31;
    v = R::ShiftTick(far, t2, 10000, l);
    CHECK(v.end == 0 && v.flags == uint32_t(CafeFlagOutside) && v.warnSec && *v.warnSec == 10);
    CHECK(R::ShiftTick(far, t2, 19999, l).end == 0);
    CHECK(R::ShiftTick(far, t2, 20000, l).end == 'W');
    // both at once: the nearer end is shown
    R::ShiftTimers t3;
    R::ShiftFacts both = far;
    both.hidden = true;
    v = R::ShiftTick(both, t3, 10000, l);
    CHECK_EQN(v.flags, uint32_t(CafeFlagHidden | CafeFlagOutside));
    CHECK(v.warnSec && *v.warnSec == 5);
}

// =================================================================================================================
// Placement
// =================================================================================================================
TEST("ToWorld and ToLocal: the formula and the inverse")
{
    R::Pose const a{ 100.0f, 200.0f, 50.0f, 0.0f };
    R::Pose p = R::ToWorld(a, 2.0f, 1.0f, 0.5f, R::Pi);
    CHECK(Near(p.x, 102.0f) && Near(p.y, 201.0f) && Near(p.z, 50.5f) && Near(p.o, R::Pi));
    R::Pose const b{ 0.0f, 0.0f, 0.0f, R::Pi / 2.0f };   // facing +Y: forward is +Y, left is -X
    p = R::ToWorld(b, 2.0f, 1.0f, 0.0f, 0.0f);
    CHECK(Near(p.x, -1.0f) && Near(p.y, 2.0f));
    // the inverse for random poses (".cafe here" keeps f/l/u/turn consistent)
    for (int i = 0; i < 50; ++i)
    {
        R::Pose const an{ float(i * 13 % 97) - 40.0f, float(i * 29 % 89) - 30.0f, float(i % 7), float(i) * 0.37f };
        float const f = float(i % 11) - 5.0f, l = float(i % 5) - 2.5f, u = float(i % 3) * 0.5f;
        float const turn = R::Signed(float(i) * 0.91f);
        R::Pose const w = R::ToWorld(an, f, l, u, turn);
        R::Local const back = R::ToLocal(an, w);
        CHECK(Near(back.f, f, 0.002f) && Near(back.l, l, 0.002f) && Near(back.u, u, 0.002f));
        CHECK(Near(R::Signed(back.turn - turn), 0.0f, 0.002f));
    }
    CHECK(Near(R::Norm(-0.5f), R::TwoPi - 0.5f));
    CHECK(Near(R::Norm(7.0f), 7.0f - R::TwoPi));
    CHECK(R::Norm(R::TwoPi) < R::TwoPi);
    CHECK(Near(R::Signed(R::Pi + 0.5f), -R::Pi + 0.5f));
}

TEST("ChairSlot: the core's slot formula")
{
    R::Pose const chair{ 10.0f, 20.0f, 5.0f, 0.0f };
    R::Pose s = R::ChairSlot(chair, 1.0f, 0, 1);
    CHECK(Near(s.x, 10.0f) && Near(s.y, 20.0f) && Near(s.o, 0.0f));
    // a 2-slot bench of size 0.68 facing +X: slots along +Y at -0.34 and +0.34
    s = R::ChairSlot(chair, 0.68f, 0, 2);
    CHECK(Near(s.x, 10.0f) && Near(s.y, 19.66f));
    s = R::ChairSlot(chair, 0.68f, 1, 2);
    CHECK(Near(s.x, 10.0f) && Near(s.y, 20.34f));
    R::Pose const turned{ 0.0f, 0.0f, 0.0f, R::Pi / 2.0f };
    s = R::ChairSlot(turned, 1.0f, 0, 3);           // along -X: at x = +1, 0, -1
    CHECK(Near(s.x, 1.0f) && Near(s.y, 0.0f, 0.001f));
    s = R::ChairSlot(turned, 1.0f, 2, 3);
    CHECK(Near(s.x, -1.0f));
    s = R::ChairSlot(chair, 1.0f, 0, 0);            // a broken row counts one slot
    CHECK(Near(s.y, 20.0f));
}

TEST("SnapZ: the ground when valid, near the anchor and seen")
{
    CHECK(Near(R::SnapZ(true, 51.0f, 50.0f, true), 51.0f));
    CHECK(Near(R::SnapZ(true, 52.5f, 50.0f, true), 52.5f));
    CHECK(Near(R::SnapZ(true, 52.6f, 50.0f, true), 50.0f));   // a roof or a cellar
    CHECK(Near(R::SnapZ(true, 51.0f, 50.0f, false), 50.0f));  // behind a wall
    CHECK(Near(R::SnapZ(false, 51.0f, 50.0f, true), 50.0f));
}

TEST("PieceEntry: new art, the stand-in, furniture")
{
    CHECK_EQN(R::PieceEntry(909300, true), 909300u);
    CHECK_EQN(R::PieceEntry(909300, false), 909330u);
    CHECK_EQN(R::PieceEntry(909323, false), 909353u);
    CHECK_EQN(R::PieceEntry(909360, false), 909360u);   // a chair has no stand-in
    CHECK_EQN(R::PieceEntry(1, false), 1u);
    for (D::GameObject const& g : D::GameObjects)
        if (g.standIn)
            CHECK_EQN(g.standIn, g.entry + D::StandInOffset);
}

// =================================================================================================================
// Stations (section 3.5)
// =================================================================================================================
TEST("StationAt: distance, height, arc, nearest wins, both spots, the facing hint")
{
    // two stations: G with spots at (0,0) and (0.7,0), its object at (0.35, 1); E at (2,0) and (2.7,0), object (2.35,1)
    std::vector<R::SpotRef> const spots = {
        { 'G', 0, 0.0f, 0.0f, 0.0f, 0.35f, 1.0f }, { 'G', 1, 0.7f, 0.0f, 0.0f, 0.35f, 1.0f },
        { 'E', 0, 2.0f, 0.0f, 0.0f, 2.35f, 1.0f }, { 'E', 1, 2.7f, 0.0f, 0.0f, 2.35f, 1.0f },
    };
    float const up = R::Pi / 2.0f;   // facing +Y
    R::StationHit h = R::StationAt(0.0f, 0.0f, 0.0f, up, spots, 1.5f, 120.0f);
    CHECK(h.station == 'G' && h.spot == 0);
    h = R::StationAt(0.7f, 0.1f, 0.0f, up, spots, 1.5f, 120.0f);
    CHECK(h.station == 'G' && h.spot == 1);             // the second spot
    h = R::StationAt(1.3f, 0.0f, 0.0f, up, spots, 1.5f, 120.0f);
    CHECK(h.station == 'G' && h.spot == 1);             // 0.6 to G's second spot, 0.7 to E's first: the nearest wins
    h = R::StationAt(1.45f, 0.0f, 0.0f, up, spots, 1.5f, 120.0f);
    CHECK(h.station == 'E' && h.spot == 0);             // 0.75 against 0.55
    // too far, too high
    h = R::StationAt(0.0f, -1.6f, 0.0f, up, spots, 1.5f, 120.0f);
    CHECK(h.station == 0 && !h.facingHint);
    CHECK(h.nearStation == 'G' && Near(h.nearDist, 1.6f));
    h = R::StationAt(0.0f, 0.0f, 2.5f, up, spots, 1.5f, 120.0f);
    CHECK(h.station == 0);
    h = R::StationAt(0.0f, 0.0f, 2.0f, up, spots, 1.5f, 120.0f);
    CHECK(h.station == 'G');                            // |dz| 2 is still in
    // facing away: the facing hint
    h = R::StationAt(0.0f, 0.0f, 0.0f, -up, spots, 1.5f, 120.0f);
    CHECK(h.station == 0 && h.facingHint && h.nearStation == 'G');
    // the arc is +-60 degrees around the object: 55 degrees off is in, 65 off is out (one spot alone)
    std::vector<R::SpotRef> const one = { spots[0] };
    float const toObj = std::atan2(1.0f, 0.35f);
    h = R::StationAt(0.0f, 0.0f, 0.0f, toObj + 55.0f * R::Pi / 180.0f, one, 1.5f, 120.0f);
    CHECK(h.station == 'G');
    h = R::StationAt(0.0f, 0.0f, 0.0f, toObj - 55.0f * R::Pi / 180.0f, one, 1.5f, 120.0f);
    CHECK(h.station == 'G');
    h = R::StationAt(0.0f, 0.0f, 0.0f, toObj + 65.0f * R::Pi / 180.0f, one, 1.5f, 120.0f);
    CHECK(h.station == 0 && h.facingHint);
    h = R::StationAt(0.0f, 0.0f, 0.0f, toObj - 61.0f * R::Pi / 180.0f, one, 1.5f, 120.0f);
    CHECK(h.station == 0 && h.facingHint);
    // a 360 arc never asks for the facing
    h = R::StationAt(0.0f, 0.0f, 0.0f, -up, spots, 1.5f, 360.0f);
    CHECK(h.station == 'G');
    // nothing at all
    h = R::StationAt(0.0f, 0.0f, 0.0f, up, {}, 1.5f, 120.0f);
    CHECK(h.station == 0 && h.nearStation == 0);
    // CAFST nearDm
    CHECK_EQN(R::NearDm(0.0f), 0u);
    CHECK_EQN(R::NearDm(0.34f), 3u);
    CHECK_EQN(R::NearDm(12.0f), 120u);
    CHECK_EQN(R::NearDm(30.0f), 255u);
    CHECK(R::HasInArc(1.0f, 5.0f, 5.0f, 0.0f, 5.0f, 5.0f));   // the same point is always in
}

TEST("StationAt on the default layout turned and moved (the anchor anywhere)")
{
    R::Pose const anchor{ -8800.0f, 640.0f, 95.0f, 2.3f };
    std::vector<R::SpotRef> const spots = DefaultSpots(1, anchor);
    for (R::SpotRef const& s : spots)
    {
        float const face = std::atan2(s.objY - s.y, s.objX - s.x);
        R::StationHit const h = R::StationAt(s.x, s.y, anchor.z + 0.5f, face, spots, 1.5f, 120.0f);
        CHECK_MSG(h.station == s.station, std::string(1, s.station));
    }
    // the customer's order spot (the anchor, facing the counter) is no station
    R::StationHit const h = R::StationAt(anchor.x, anchor.y, anchor.z, anchor.o, spots, 1.5f, 120.0f);
    CHECK(h.station == 0);
}

// =================================================================================================================
// Customers
// =================================================================================================================
TEST("PickRecipeN: favourites, unlocks, nobody on shift, groups")
{
    D::Persona const& corwin = Per(909320);   // C1, C4 (C4 needs level 3)
    // nobody on shift: a level-1 recipe
    for (uint32_t pick = 0; pick < 20; ++pick)
    {
        uint8_t const n = R::PickRecipeN(corwin, 0, 0, 10, pick);
        CHECK(Rec(D::RecipeId(1, n)).unlock == 1);
    }
    // a level-1 barista: a favourite it has (C1) 60% of the time
    CHECK_EQN(R::PickRecipeN(corwin, 0, 1, 0, 0), 1u);
    CHECK_EQN(R::PickRecipeN(corwin, 0, 1, 59, 1), 1u);
    // level 3: both favourites
    std::set<uint8_t> favs;
    for (uint32_t pick = 0; pick < 10; ++pick)
        favs.insert(R::PickRecipeN(corwin, 0, 3, 30, pick));
    CHECK(favs == std::set<uint8_t>({ 1, 4 }));
    // the other 40%: anything unlocked at that level
    std::set<uint8_t> any;
    for (uint32_t pick = 0; pick < 40; ++pick)
    {
        uint8_t const n = R::PickRecipeN(corwin, 0, 2, 60, pick);
        CHECK(Rec(D::RecipeId(1, n)).unlock <= 2);
        any.insert(n);
    }
    CHECK_EQN(any.size(), 7u);                       // C1 C2 C3 T1 T2 M1 M2
    // a favourite nobody has unlocked falls back to the unlocked recipes
    D::Persona const& legend = Per(909324);   // C7 (9), T6 (8)
    uint8_t const n = R::PickRecipeN(legend, 0, 5, 0, 3);
    CHECK(Rec(D::RecipeId(1, n)).unlock <= 5);
    // a group member orders its own favourite whatever the levels
    D::Persona const& watch = Per(909341);    // C1, C1, C2
    CHECK_EQN(R::PickRecipeN(watch, 0, 0, 99, 7), 1u);
    CHECK_EQN(R::PickRecipeN(watch, 2, 0, 99, 7), 2u);
    D::Persona const& guards = Per(909374);
    CHECK_EQN(R::PickRecipeN(guards, 1, 10, 0, 0), 4u);
    // a generic citizen (no favourites) at level 10: any recipe of its cafe
    D::Persona const& citizen = Per(909372);
    std::set<uint8_t> all;
    for (uint32_t pick = 0; pick < 100; ++pick)
        all.insert(R::PickRecipeN(citizen, 0, 10, 0, pick));
    CHECK_EQN(all.size(), 19u);
}

TEST("Lines: own order line only for the first favourite; pools with the drink's name; staff lines")
{
    D::Persona const& corwin = Per(909320);
    CHECK_EQ(R::OrderLine(corwin, 1, 0, "Cathedral Black", 'A', 0), "Cathedral Black. No sugar, no chatter, no delay.");
    std::string const other = R::OrderLine(corwin, 4, 0, "Lionheart Double", 'A', 0);
    CHECK_EQ(other, "One Lionheart Double, please.");
    CHECK_EQ(R::ThanksLine(corwin, 'A', 5), "Hot and bitter. Like my shift.");
    CHECK_EQ(R::ComplaintLine(corwin, 'A', 5), "I've stood shorter watches on the wall. I'm off.");
    D::Persona const& citizen = Per(909372);   // pool H
    CHECK_EQ(R::OrderLine(citizen, 1, 0, "Grunt's Black", 'H', 1), "A Grunt's Black, and make it strong.");
    CHECK(!R::ThanksLine(citizen, 'H', 0).empty());
    CHECK(!R::ComplaintLine(citizen, 'H', 2).empty());
    D::Persona const& child = Per(909343);     // pool K
    CHECK_EQ(R::OrderLine(child, 14, 0, "Vanilla Lion Cub", 'A', 1), "A Vanilla Lion Cub! I saved my coppers!");
    D::Persona const& watch = Per(909341);
    CHECK_EQ(R::OrderLine(watch, 1, 0, "Cathedral Black", 'A', 0), std::string(watch.order));
    CHECK(R::OrderLine(watch, 1, 1, "Cathedral Black", 'A', 0).find("Cathedral Black") != std::string::npos);
    CHECK_EQ(std::string(R::PoolLine('A', 'O', 4)), "One {drink}, please.");     // wraps
    CHECK_EQ(std::string(R::PoolLine('Z', 'O', 0)), "");
    CHECK_EQ(R::Fill("Level {n} already? {n}!", "{n}", "5"), "Level 5 already? 5!");
    CHECK_EQ(R::Fill("no key", "{drink}", "x"), "no key");
    bool yell = false;
    CHECK_EQ(std::string(R::StaffLine(909300, "rushStart", 0, &yell)),
        "The bells are ringing eight! Here comes the Morning Rush, everyone to the bar!");
    CHECK(yell);
    CHECK(!R::StaffLine(909300, "idle", 0).empty());
    CHECK(R::StaffLine(909300, "idle", 0) != R::StaffLine(909300, "idle", 1));
    CHECK(R::StaffLine(909303, "shiftStart", 0).empty());
    // every cafe's owner has the lines the engine says
    for (D::Cafe const& c : D::Cafes)
        for (char const* key : { "shiftStart", "shiftEnd", "houseOrder", "ambientAnswer", "takeover", "dangerPause",
                                 "rushStart", "refuse" })
            CHECK_MSG(!R::StaffLine(c.owner, key, 0).empty(), std::string(c.name) + " " + key);
    for (D::Cafe const& c : D::Cafes)
        CHECK(!R::StaffLine(c.head, "levelUp", 0).empty());
}

// =================================================================================================================
// Bot hints
// =================================================================================================================
TEST("BotFlag and the release spread")
{
    std::vector<int32_t> even(250, 5);
    even[0] = 0;
    CHECK(R::BotFlag(250, 248, even, 200, 980, 30));
    CHECK(!R::BotFlag(199, 199, even, 200, 980, 30));           // too few drinks
    CHECK(!R::BotFlag(250, 240, even, 200, 980, 30));           // 96% Perfect
    std::vector<int32_t> human;
    for (int i = 0; i < 250; ++i)
        human.push_back((i * 37) % 160 - 80);
    CHECK(!R::BotFlag(250, 250, human, 200, 980, 30));          // a human's spread
    CHECK(!R::BotFlag(250, 250, {}, 200, 980, 30));
    CHECK_EQN(R::StdDevMs({ 10, 10, 10 }), 0u);
    CHECK_EQN(R::StdDevMs({ -10, 10 }), 10u);
    CHECK_EQN(R::StdDevMs({ 5 }), 0u);
}

// =================================================================================================================
// Levels
// =================================================================================================================
TEST("LevelOf and NextLevelXp")
{
    CHECK_EQN(R::LevelOf(0), 1u);
    CHECK_EQN(R::LevelOf(119), 1u);
    CHECK_EQN(R::LevelOf(120), 2u);
    CHECK_EQN(R::LevelOf(1890), 6u);                 // CAFST 4b of the document: 1890 XP is level 6 (1600..2320)
    CHECK_EQN(R::LevelOf(5640), 10u);
    CHECK_EQN(R::LevelOf(99999), 10u);
    CHECK_EQN(*R::NextLevelXp(6), 2320u);
    CHECK(!R::NextLevelXp(10));
    CHECK_EQN(R::LevelXp(6), 1600u);
    CHECK_EQN(R::LevelXp(11), 0u);
    CHECK(R::Unlocked(9, Rec(107)));
    CHECK(!R::Unlocked(8, Rec(107)));
}

// =================================================================================================================
// DEF H G F U and the document
// =================================================================================================================
TEST("FillDefinitions: DEF H G F U as the document shows them")
{
    Definitions d;
    R::FillDefinitions(d);
    CHECK_EQN(d.cafes.size(), 2u);
    CHECK_EQN(d.cafeActions.size(), 26u);
    CHECK_EQN(d.cafeRecipes.size(), 38u);
    CHECK_EQN(d.cafeLevels.size(), 10u);
    std::vector<std::string> const payloads = EncodeDefinitions(d, 8);
    std::map<char, std::string> byKind;
    for (std::string const& p : payloads)
        if (!p.empty())
            byKind[p[0]] = p;
    CHECK(byKind.count('H') && byKind.count('G') && byKind.count('F') && byKind.count('U') && byKind.count('Z'));
    std::string const doc = bhtest::ReadFile(g_repo + "/docs/BleakholdProtocol.md");
    // H: both cafes, exactly
    CHECK_EQ(byKind['H'], DocPayload(doc, "DEF", "50"));
    // G, F, U: every record of the document's (shortened) examples is one of ours
    for (auto const& [seq, kind] : std::vector<std::pair<std::string, char>>{ { "51", 'G' }, { "52", 'F' }, { "53", 'U' } })
    {
        std::string const example = DocPayload(doc, "DEF", seq);
        CHECK_MSG(!example.empty(), "DEF " + seq);
        std::vector<std::string> const want = Split(example, ';');
        std::vector<std::string> const have = Split(byKind[kind], ';');
        CHECK_EQ(want[0], have[0]);
        std::set<std::string> const ours(have.begin() + 1, have.end());
        for (std::size_t i = 1; i < want.size(); ++i)
            CHECK_MSG(ours.count(want[i]) == 1, want[i]);
    }
}

TEST("The document's cafe numbers come from these rules")
{
    std::string const doc = bhtest::ReadFile(g_repo + "/docs/BleakholdProtocol.md");
    // CAFM 4t: a level-70 menu
    std::vector<std::string> const menu = Split(DocPayload(doc, "CAFM", "4t"), ';');
    CHECK(menu.size() >= 4);
    for (std::size_t i = 1; i < menu.size(); ++i)
    {
        std::vector<std::string> const f = Split(menu[i], ',');
        D::Recipe const& r = Rec(static_cast<uint16_t>(std::stoul(f[0])));
        CHECK_EQ(std::to_string(R::PriceCopper(R::TierOf(r.tier)->price80, 70, 200, 10)), f[1]);
    }
    // CAFO 4w: the tip of 10%
    std::vector<std::string> const order = Split(DocPayload(doc, "CAFO", "4w"), ',');
    CHECK(order.size() >= 11);
    if (order.size() >= 11)
        CHECK_EQ(std::to_string(R::TipCopper(static_cast<uint32_t>(std::stoul(order[9])), 10)), order[10]);
}

TEST("The module SQL holds the tables the cafe creates at startup, and the uninstall drops them all")
{
    std::string const mod = g_repo + "/Server/mod-bleakhold-ui";
    std::string const world = bhtest::ReadFile(mod + "/data/sql/db-world/03_bleakhold_cafe_tables.sql");
    std::string const chars = bhtest::ReadFile(mod + "/data/sql/db-characters/01_bleakhold_cafe_characters.sql");
    std::string const uninstall = bhtest::ReadFile(mod + "/data/sql/uninstall/cafe_uninstall.sql");
    auto tableOf = [](std::string_view sql) {
        std::size_t const a = sql.find('`') + 1;
        return std::string(sql.substr(a, sql.find('`', a) - a));
    };
    for (std::string_view sql : R::WorldTablesSql)
    {
        CHECK_MSG(world.find(std::string(sql) + ";\n") != std::string::npos, tableOf(sql));
        CHECK_MSG(uninstall.find("DROP TABLE IF EXISTS `" + tableOf(sql) + "`;") != std::string::npos, tableOf(sql));
    }
    for (std::string_view sql : R::CharacterTablesSql)
    {
        CHECK_MSG(chars.find(std::string(sql) + ";\n") != std::string::npos, tableOf(sql));
        CHECK_MSG(uninstall.find("DROP TABLE IF EXISTS `" + tableOf(sql) + "`;") != std::string::npos, tableOf(sql));
    }
    CHECK_EQN(R::WorldTablesSql.size() + R::CharacterTablesSql.size(), 8u);
}

TEST("Every cafe key the server reads is in the config file, and the cafe ships off")
{
    std::string const mod = g_repo + "/Server/mod-bleakhold-ui";
    std::string const conf = bhtest::ReadFile(mod + "/conf/mod_bleakhold_ui.conf.dist");
    std::size_t keys = 0;
    for (char const* file : { "/src/BleakholdCafe.cpp", "/src/BleakholdCafeCrowd.cpp", "/src/BleakholdMgr.cpp" })
    {
        std::string const src = bhtest::ReadFile(mod + file);
        for (std::size_t at = src.find("\"BleakholdUi.Cafe."); at != std::string::npos;
             at = src.find("\"BleakholdUi.Cafe.", at + 1))
        {
            std::string const key = src.substr(at + 1, src.find('"', at + 1) - at - 1);
            CHECK_MSG(conf.find("\n" + key + " = ") != std::string::npos, key);
            ++keys;
        }
        for (std::size_t at = src.find("\"BleakholdUi.RateLimit.Cafe"); at != std::string::npos;
             at = src.find("\"BleakholdUi.RateLimit.Cafe", at + 1))
        {
            std::string const key = src.substr(at + 1, src.find('"', at + 1) - at - 1);
            CHECK_MSG(conf.find("\n" + key + " = ") != std::string::npos, key);
        }
    }
    CHECK(keys >= 90);
    CHECK(conf.find("\nBleakholdUi.Cafe.Enable = 0\n") != std::string::npos);
    CHECK(conf.find("\nBleakholdUi.Cafe.GmOnly = 1\n") != std::string::npos);
    CHECK(conf.find("\nBleakholdUi.Cafe.UseNewArt = 0\n") != std::string::npos);
    CHECK(conf.find("\nBleakholdUi.Announce.Color.Cafe = \"D8B98A\"\n") != std::string::npos);
}

TEST("The cafe's intents, topics, board, hello and hooks are wired")
{
    std::string const mod = g_repo + "/Server/mod-bleakhold-ui/src";
    std::string const data = bhtest::ReadFile(mod + "/BleakholdData.cpp");
    for (char const* name : { "CafeShift", "CafeTake", "CafeStep", "CafeRelease", "CafeOrder", "CafeCancel", "CafeStaff" })
        CHECK_MSG(data.find(std::string("SetDefaultHandler(IntentType::") + name + ",") != std::string::npos, name);
    for (char const* name : { "CafeList", "CafeState", "CafeQueue", "CafeTickets", "CafeMenu", "CafeOrderState",
             "CafeProfile", "CafeBuffs" })
        CHECK_MSG(data.find(std::string("Topic::") + name) != std::string::npos, name);
    CHECK(data.find("SetBoardHandler(Board::Cafe,") != std::string::npos);
    CHECK(data.find("Cafe::Instance().OnHello(p)") != std::string::npos);
    CHECK(data.find("CafeRules::FillDefinitions(d)") != std::string::npos);
    std::string const scripts = bhtest::ReadFile(mod + "/BleakholdScripts.cpp");
    for (char const* line : { "new BleakholdCafePlayerScript();", "new BleakholdCafeSpellScript();",
             "new BleakholdCafeGoScript();", "new BleakholdCafeCreatureScript();", "Cafe::Instance().OnStartup();",
             "Cafe::Instance().OnShutdown();",
             "\"npc_bh_cafe_owner\"", "\"npc_bh_cafe_staff\"" })
        CHECK_MSG(scripts.find(line) != std::string::npos, line);
    // the templates name the same scripts
    std::string const templates = bhtest::ReadFile(g_repo +
        "/Server/mod-bleakhold-ui/data/sql/db-world/04_bleakhold_cafe_templates.sql");
    CHECK(templates.find("'npc_bh_cafe_owner'") != std::string::npos);
    CHECK(templates.find("'npc_bh_cafe_staff'") != std::string::npos);
}

// =================================================================================================================
// Round-1 review fixes: each test fails on the code before its fix
// =================================================================================================================
TEST("CatalogueGo: a stand-in is a cafe template (decor), with its piece's footprint, and keeps its entry")
{
    for (D::GameObject const& g : D::GameObjects)
    {
        CHECK(R::CatalogueGo(g.entry) == &g);
        if (!g.standIn)
            continue;
        CHECK_MSG(D::FindGameObject(g.standIn) == nullptr, std::to_string(g.standIn));   // no row of its own
        CHECK_MSG(R::CatalogueGo(g.standIn) == &g, std::to_string(g.standIn));
        // a stand-in placed as decor spawns as itself with the new art on and off (V21b)
        CHECK_EQN(R::PieceEntry(g.standIn, true), g.standIn);
        CHECK_EQN(R::PieceEntry(g.standIn, false), g.standIn);
    }
    CHECK(R::CatalogueGo(909348) != nullptr);
    CHECK(R::CatalogueGo(909299) == nullptr);
    CHECK(R::CatalogueGo(909329) == nullptr);   // 909299 + 30: no piece below the block
    CHECK(R::CatalogueGo(909354) == nullptr);   // 909324 has no row
    CHECK(R::CatalogueGo(0) == nullptr);
}

TEST("LingerTick: seated within 120 s, for 60 s, once; standing up restarts the 60 s")
{
    R::Linger l;
    l.spell = 100930;
    l.receivedMs = 1000;
    CHECK(R::LingerTick(l, false, 1000 + 30000) == R::LingerStep::Wait);
    CHECK(R::LingerTick(l, true, 1000 + 30000) == R::LingerStep::Wait);    // sits down at 30 s
    CHECK(R::LingerTick(l, true, 1000 + 89999) == R::LingerStep::Wait);
    CHECK(R::LingerTick(l, true, 1000 + 90000) == R::LingerStep::Grant);   // 60 s seated
    // stood up after 40 s, sat down again at 100 s: the 60 s count from then
    R::Linger m;
    m.receivedMs = 0;
    CHECK(R::LingerTick(m, true, 10000) == R::LingerStep::Wait);
    CHECK(R::LingerTick(m, false, 50000) == R::LingerStep::Wait);
    CHECK(R::LingerTick(m, true, 100000) == R::LingerStep::Wait);
    CHECK(R::LingerTick(m, true, 159999) == R::LingerStep::Wait);
    CHECK(R::LingerTick(m, true, 160000) == R::LingerStep::Grant);
    // never seated in time, or first seated after 120 s
    R::Linger late;
    CHECK(R::LingerTick(late, false, 120000) == R::LingerStep::Wait);
    CHECK(R::LingerTick(late, false, 120001) == R::LingerStep::Drop);
    R::Linger lateSit;
    CHECK(R::LingerTick(lateSit, true, 120001) == R::LingerStep::Drop);
    // the bonus within Buff.MaxMin
    CHECK_EQN(R::LingerMs(40 * 60000, 60), 50u * 60000);
    CHECK_EQN(R::LingerMs(55 * 60000, 60), 60u * 60000);
}

TEST("TiredLoaded: a shift a crash never ended rests from the startup; a normal row is left alone")
{
    uint32_t const start = 2000000;
    R::TiredRow crashed;
    crashed.accumSec = 70 * 60;   // saved every second while on shift: off_shift_since 0
    // before the fix the row stayed Tired forever (Rested needs offSince) and the next shift kept the 70 min
    CHECK(R::IsTired(crashed, start + 10 * 3600, 60, 15));
    R::TiredRow const loaded = R::TiredLoaded(crashed, start);
    CHECK_EQN(loaded.offSince, start);
    CHECK(R::IsTired(loaded, start + 14 * 60, 60, 15));
    CHECK(!R::IsTired(loaded, start + 15 * 60, 60, 15));
    CHECK_EQN(R::TiredOnShiftStart(loaded, start + 15 * 60, 15).accumSec, 0u);
    R::TiredRow normal;
    normal.accumSec = 600;
    normal.offSince = start - 100;
    CHECK_EQN(R::TiredLoaded(normal, start).offSince, start - 100);
    R::TiredRow fresh;
    CHECK_EQN(R::TiredLoaded(fresh, start).offSince, 0u);   // never worked: nothing to rest from
}

TEST("OrderLeftoversOf and AfterRespawn: tickets, house jobs and counter cups never outlive their order")
{
    CHECK_EQN(R::OrderLeftoversOf('W', false), 0);
    CHECK_EQN(R::OrderLeftoversOf('T', false), uint8_t(R::LeftTicket));   // a deleted customer's ticket closes
    CHECK_EQN(R::OrderLeftoversOf('H', false), uint8_t(R::LeftHouseJob));
    CHECK_EQN(R::OrderLeftoversOf('R', true), uint8_t(R::LeftCounterCup));   // its counter place is freed
    CHECK_EQN(R::OrderLeftoversOf('R', false), 0);
    CHECK(R::AfterRespawn('P', 'H', false) == R::Respawned::RequeueHouseJob);   // was 'H' forever after a nudge
    CHECK(R::AfterRespawn('P', 'R', true) == R::Respawned::PlaceCup);
    CHECK(R::AfterRespawn('P', 'R', false) == R::Respawned::Nothing);
    CHECK(R::AfterRespawn('P', 'W', false) == R::Respawned::Nothing);
    CHECK(R::AfterRespawn('P', 'T', false) == R::Respawned::Nothing);
    CHECK(R::AfterRespawn('N', 'H', false) == R::Respawned::Nothing);   // NPC orders leave with their customers
    CHECK(R::AfterRespawn('G', 'R', true) == R::Respawned::Nothing);
}

TEST("ShiftTick: combat ends the shift even without the On Shift aura")
{
    R::ShiftLimits const l;
    R::ShiftTimers t;
    R::ShiftFacts f;
    f.lastActionMs = 1000;
    f.inCombat = true;
    CHECK(R::ShiftTick(f, t, 2000, l).end == 'C');
    CHECK(R::ShiftTick(f, t, 2000, l).end == static_cast<char>(CafeShiftEnd::Combat));
    f.inCombat = false;
    CHECK(R::ShiftTick(f, t, 2000, l).end == 0);
}

TEST("RushNext: a live Rush ends with Rush.Enable off; warnings and new windows need it on")
{
    R::RushClock none, soon, live;
    soon.state = 1;
    soon.startLocal = 5000;
    live.state = 2;
    live.startLocal = 5000;
    // live: ends at its end time whatever Rush.Enable says (a test Rush, a reload during one)
    CHECK(R::RushNext(2, false, none, 0, 10000, 9000) == R::RushMove::End);
    CHECK(R::RushNext(2, false, live, 5000, 10000, 9000) == R::RushMove::End);
    CHECK(R::RushNext(2, true, live, 5000, 8000, 9000) == R::RushMove::None);
    CHECK(R::RushNext(2, false, none, 0, 8000, 9000) == R::RushMove::None);
    // off: a warning that was showing goes, and nothing new starts
    CHECK(R::RushNext(1, false, soon, 0, 0, 0) == R::RushMove::Calm);
    CHECK(R::RushNext(0, false, soon, 0, 0, 0) == R::RushMove::None);
    CHECK(R::RushNext(0, false, live, 0, 0, 0) == R::RushMove::None);
    // on: soon, start, once per window, calm when the clock says none
    CHECK(R::RushNext(0, true, soon, 0, 0, 0) == R::RushMove::Soon);
    CHECK(R::RushNext(1, true, soon, 0, 0, 0) == R::RushMove::None);
    CHECK(R::RushNext(1, true, live, 0, 0, 0) == R::RushMove::Start);
    CHECK(R::RushNext(0, true, live, 5000, 0, 0) == R::RushMove::None);   // this window already ran
    CHECK(R::RushNext(1, true, none, 0, 0, 0) == R::RushMove::Calm);
    CHECK(R::RushNext(0, true, none, 0, 0, 0) == R::RushMove::None);
}

TEST("RushShouters and the table-service lines: Pip, Nixxi and Tavi have lines the server says")
{
    std::vector<D::StaffMember const*> const sw = R::RushShouters(1);
    std::vector<D::StaffMember const*> const org = R::RushShouters(2);
    CHECK_EQN(sw.size(), std::size_t(1));
    CHECK_EQN(org.size(), std::size_t(2));
    if (sw.size() == 1)
        CHECK_EQN(sw[0]->entry, 909302u);
    if (org.size() == 2)
    {
        CHECK_EQN(org[0]->entry, 909307u);
        CHECK_EQN(org[1]->entry, 909309u);
    }
    // after the owner's yell, one after the other, all within the first quarter-minute
    CHECK(R::RushShoutDelayMs(0) > 0);
    CHECK(R::RushShoutDelayMs(1) > R::RushShoutDelayMs(0));
    CHECK(R::RushShoutDelayMs(1) < 15000);
    for (D::Cafe const& c : D::Cafes)
    {
        std::string_view const line = R::StaffLine(c.busser, "tableService", 0);
        CHECK_MSG(line.find("{drink}") != std::string_view::npos, std::string(c.name));
        D::StaffMember const* busser = D::FindStaff(c.busser);
        CHECK(busser && busser->role == "staff_busser");
    }
    std::string const src = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafe.cpp");
    CHECK(src.find("\"staff_busser\", CafeInfo(o->cafeId).busser, \"tableService\"") != std::string::npos);
    CHECK(src.find("Say(c.id, st->role, st->entry, \"rush\")") != std::string::npos);
}

TEST("WeeksToPay: a week that ended while the server was down is paid at the next start, once")
{
    using V = std::vector<uint32_t>;
    CHECK(R::WeeksToPay({ 10, 11, 12, 12 }, {}, 13) == (V{ 10, 11, 12 }));
    CHECK(R::WeeksToPay({ 10, 11, 12 }, { 10, 11 }, 13) == V{ 12 });
    CHECK(R::WeeksToPay({ 12, 13 }, {}, 13) == V{ 12 });   // never the running week
    CHECK(R::WeeksToPay({ 12 }, { 12 }, 13).empty());
    CHECK(R::WeeksToPay({ 8, 9 }, {}, 13) == V{ 9 });      // at most MissedWeeksMax back
    CHECK(R::WeeksToPay({ 0, 3 }, {}, 3).empty());
    CHECK(R::WeeksToPay({ 11 }, {}, 13) == V{ 11 });       // a skipped id at the year's end: still found
}

TEST("BoardCached: LBQ C caches this week and the last only")
{
    CHECK(R::BoardCached(50, 50));
    CHECK(R::BoardCached(49, 50));
    CHECK(!R::BoardCached(48, 50));
    CHECK(!R::BoardCached(51, 50));
    CHECK(!R::BoardCached(2147483647u, 50));
    CHECK(R::BoardCached(0, 0));
    std::string const src = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafe.cpp");
    std::size_t const at = src.find("void Cafe::AnswerBoard(");
    CHECK(at != std::string::npos);
    if (at != std::string::npos)
        CHECK(src.find("if (!FeatureFor(player))", at) < src.find("BoardRows(", at));   // gated before the query
}

TEST("NpcHouseDue and FirstWaiting: nobody on shift hands every waiting order over; a taken order at the front "
     "does not block the rule")
{
    std::map<uint32_t, char> state = { { 2, 'T' }, { 1, 'H' }, { 3, 'W' }, { 4, 'W' } };
    std::vector<uint32_t> const queue = { 2, 1, 3, 4 };
    auto stateOf = [&](uint32_t id) { auto it = state.find(id); return it == state.end() ? char(0) : it->second; };
    CHECK_EQN(R::FirstWaiting(queue, stateOf), 3u);
    CHECK_EQN(R::FirstWaiting(std::vector<uint32_t>{ 2, 1 }, stateOf), 0u);
    CHECK_EQN(R::FirstWaiting(std::vector<uint32_t>{ 9, 4 }, stateOf), 4u);   // a gone order is skipped
    // nobody on shift: every waiting order, at once (the house's two workers share them)
    CHECK(R::NpcHouseDue(0, false, 0, 25000, 0, 1));
    CHECK(R::NpcHouseDue(0, true, 0, 25000, 0, 1));
    // a barista on shift: the first waiting order after 25 s, when none on shift has its level
    CHECK(R::NpcHouseDue(1, true, 25000, 25000, 2, 3));
    CHECK(!R::NpcHouseDue(1, true, 24999, 25000, 2, 3));
    CHECK(!R::NpcHouseDue(1, true, 25000, 25000, 3, 3));
    CHECK(!R::NpcHouseDue(1, false, 60000, 25000, 2, 3));
}

TEST("CafeListMark: the key at once, the queue length alone at most every 5 s")
{
    CHECK(R::CafeListMark(true, false, 0));
    CHECK(R::CafeListMark(true, true, 0));
    CHECK(!R::CafeListMark(false, true, 4999));
    CHECK(R::CafeListMark(false, true, 5000));
    CHECK(!R::CafeListMark(false, false, 60000));
    CHECK_EQN(R::CafeListMinGapMs, uint64_t(500));
    CHECK_EQN(R::CafeListQueueGapMs, uint64_t(5000));
    std::string const doc = bhtest::ReadFile(g_repo + "/docs/BleakholdProtocol.md");
    CHECK(doc.find("a change of `queueLen` alone is sent at most every 5 s") != std::string::npos);
}

TEST("Money: an order keeps the share it was paid at (share_pct), so a reload of BaristaSharePct creates no gold")
{
    uint32_t const price = 10000, tip = 0;
    // the wage at 60 and the house share at 60: never more than was paid
    R::Money const atPay = R::SettleOrder(R::OrderEnd::StartupReadyPaid, price, tip, 60);
    CHECK_EQN(atPay.barista + atPay.refunded + atPay.house, atPay.paid);
    CHECK(atPay.barista + atPay.refunded <= price);
    // mixing the shares (the bug): 6000 + 8000 for 10000 paid
    CHECK(R::WageCopper(price, tip, 60) + R::HouseShareCopper(price, 20) > price);
    // the turn-off path settles a ready order as a restart: all of a house-made drink, the house share of a paid one
    CHECK_EQN(R::SettleOrder(R::StartupEnd('R', false), 3000, 300, 60).refunded, 3300u);
    CHECK_EQN(R::SettleOrder(R::StartupEnd('R', true), 3000, 300, 60).refunded, 1200u);
    // the column is in the table, and an older table gets it at startup with the same text
    std::string const create(R::CharacterTablesSql[4]);
    CHECK(create.find("CREATE TABLE IF NOT EXISTS `bleakhold_cafe_order`") != std::string::npos);
    CHECK(create.find("`share_pct` TINYINT UNSIGNED NOT NULL DEFAULT 60") != std::string::npos);
    for (R::AddedColumn const& c : R::CharacterAddedColumns)
    {
        std::string const alter(c.alter);
        std::size_t const def = alter.find("`" + std::string(c.column) + "`");
        std::size_t const after = alter.find(" AFTER ");
        CHECK(def != std::string::npos && after != std::string::npos);
        if (def != std::string::npos && after != std::string::npos)
            CHECK_MSG(create.find(alter.substr(def, after - def)) != std::string::npos, std::string(c.column));
    }
    std::string const store = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafeStore.cpp");
    CHECK(store.find("_cfg.baristaSharePct") == std::string::npos);   // every split uses the order's own share
}

TEST("Startup, staff despawn, announcements: the texts and calls the runbook and the core need")
{
    std::string const mod = g_repo + "/Server/mod-bleakhold-ui/src";
    std::string const cafe = bhtest::ReadFile(mod + "/BleakholdCafe.cpp");
    // the deploy runbook greps docker logs for "Cafe: startup checks passed" (grep -E 'Cafe', case-sensitive)
    CHECK(cafe.find("\">> [Bleakhold] Cafe: startup checks {} (") != std::string::npos);
    // Respawn.ForceCompatibilityMode = 1: DespawnOrUnsummon on a staff spawn whose data is deleted crashes
    std::string const site = bhtest::ReadFile(mod + "/BleakholdCafeSite.cpp");
    CHECK(site.find("->DespawnOrUnsummon(") == std::string::npos);
    CHECK(site.find("cr->AddObjectToRemoveList();") != std::string::npos);
    // GmOnly: the realm-wide [Cafe] lines go through AnnounceCafe only
    std::string const store = bhtest::ReadFile(mod + "/BleakholdCafeStore.cpp");
    std::size_t direct = 0;
    for (std::size_t at = cafe.find("Ui::Announce(Ui::AnnounceTag::Cafe"); at != std::string::npos;
         at = cafe.find("Ui::Announce(Ui::AnnounceTag::Cafe", at + 1))
        ++direct;
    CHECK_EQN(direct, std::size_t(1));   // the one inside AnnounceCafe
    CHECK(store.find("Ui::Announce(") == std::string::npos);
}

// =================================================================================================================
// Round-2 review fixes: each test fails on the code before its fix
// =================================================================================================================
namespace
{
    // the body of `name` in a source file: from its definition to the next definition at the same indent
    std::string Body(std::string const& src, std::string const& name)
    {
        std::size_t const at = src.find(name);
        if (at == std::string::npos)
            return {};
        std::size_t const end = src.find("\n    }\n", at);
        return src.substr(at, end == std::string::npos ? std::string::npos : end - at);
    }

    std::string Squeeze(std::string_view s)
    {
        std::string out;
        for (char c : s)
            if (!(c == ' ' && !out.empty() && out.back() == ' '))
                out.push_back(c);
        return out;
    }
}

TEST("ServerFirstCounts: only a natural level 10 with the cafe open to everyone, never a game master's")
{
    CHECK(R::ServerFirstCounts(true, false, false));
    CHECK(!R::ServerFirstCounts(true, true, false));     // GmOnly testing on the live realm
    CHECK(!R::ServerFirstCounts(true, false, true));     // a game master after launch
    CHECK(!R::ServerFirstCounts(false, false, false));   // .cafe barista, a login catch-up
    std::string const cafe = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafe.cpp");
    std::string const grant = Body(cafe, "void Cafe::GrantLevelRewards(");
    std::size_t const gate = grant.find("R::ServerFirstCounts(announce, _gmOnly.load(), gameMaster)");
    std::size_t const record = grant.find("Ui::RecordServerFirst(");
    CHECK(gate != std::string::npos && record != std::string::npos && gate < record);
    CHECK(grant.find("CafeRewardMaster;") < gate);       // the apron and its flag come first, whatever the gate says
}

TEST("Name columns hold two-part names (mod-two-names: 30 characters); NameForColumn never cuts a character")
{
    std::string const week(R::CharacterTablesSql[2]);
    std::string const cafe(R::WorldTablesSql[0]);
    CHECK(week.find("`name` VARCHAR(30) NOT NULL") != std::string::npos);
    CHECK(cafe.find("`placed_by`  VARCHAR(30)") != std::string::npos);
    CHECK(week.find("VARCHAR(12)") == std::string::npos && cafe.find("VARCHAR(12)") == std::string::npos);
    // an older table is widened at startup with the CREATE's own column text
    auto widened = [](R::WidenedColumn const& c, std::string const& create) {
        std::string const alter(c.modify);
        std::size_t const def = alter.find("`" + std::string(c.column) + "`");
        CHECK_MSG(def != std::string::npos && Squeeze(create).find(alter.substr(def)) != std::string::npos,
            std::string(c.column));
        CHECK_EQN(c.chars, R::NameColumnChars);
        CHECK(alter.find("VARCHAR(" + std::to_string(c.chars) + ")") != std::string::npos);
    };
    for (R::WidenedColumn const& c : R::WorldWidenedColumns)
        widened(c, cafe);
    for (R::WidenedColumn const& c : R::CharacterWidenedColumns)
        widened(c, week);
    CHECK_EQ(R::NameForColumn("Arthas Menethil"), "Arthas Menethil");
    CHECK_EQ(R::NameForColumn("Arthas Ment\xC3\xA9"), "Arthas Ment\xC3\xA9");   // 13 bytes, 12 characters: whole
    CHECK_EQ(R::NameForColumn("Arthas Ment\xC3\xA9", 12), "Arthas Ment\xC3\xA9");
    CHECK_EQ(R::NameForColumn("Arthas Ment\xC3\xA9", 11), "Arthas Ment");
    std::string const longName(31, 'a');
    CHECK_EQN(R::NameForColumn(longName).size(), std::size_t(30));
    std::string const accented = std::string(29, 'a') + "\xC3\xA9\xC3\xA9";   // 31 characters, 33 bytes
    CHECK_EQ(R::NameForColumn(accented), std::string(29, 'a') + "\xC3\xA9");
    CHECK_EQ(R::NameForColumn(""), "");
    // the callers: no byte cut left, the week row's name goes through it
    std::string const mod = g_repo + "/Server/mod-bleakhold-ui/src";
    std::string const site = bhtest::ReadFile(mod + "/BleakholdCafeSite.cpp");
    std::string const store = bhtest::ReadFile(mod + "/BleakholdCafeStore.cpp");
    CHECK(site.find("substr(0, 12)") == std::string::npos);
    CHECK(site.find("c->placedBy = R::NameForColumn(gm->GetName());") != std::string::npos);
    CHECK(store.find("Esc(R::NameForColumn(b.name))") != std::string::npos);
    CHECK(store.find("R::WorldWidenedColumns") != std::string::npos);
    CHECK(store.find("R::CharacterWidenedColumns") != std::string::npos);
}

TEST("The uninstall uses the core's creature.id (2026_06_16_00 renamed id1): mysql stops at the first error")
{
    std::string const uninstall = bhtest::ReadFile(g_repo +
        "/Server/mod-bleakhold-ui/data/sql/uninstall/cafe_uninstall.sql");
    CHECK(uninstall.find("`id1`") == std::string::npos);
    CHECK(uninstall.find("WHERE c.`id` BETWEEN 909300 AND 909379;") != std::string::npos);
    CHECK(uninstall.find("DELETE FROM `creature` WHERE `id` BETWEEN 909300 AND 909379;") != std::string::npos);
}

TEST("RushSilentReset: Enable 1 -> 0 forgets a live Rush, so a re-enable later ends nothing and says nothing")
{
    R::RushClock none, live;
    live.state = 2;
    live.startLocal = 5000;
    uint8_t state = 2;
    int64_t window = 5000;
    uint64_t const endMs = 9000;
    // the bug: a live Rush left at state 2 ends at the first tick after the re-enable, hours later
    CHECK(R::RushNext(state, true, none, window, endMs + 30ull * 3600 * 1000, endMs) == R::RushMove::End);
    CHECK(R::RushNext(state, false, none, window, endMs + 30ull * 3600 * 1000, endMs) == R::RushMove::End);
    R::RushSilentReset(state, window);
    CHECK_EQN(state, uint8_t(0));
    CHECK_EQN(window, int64_t(0));
    CHECK(R::RushNext(state, true, none, window, endMs + 30ull * 3600 * 1000, endMs) == R::RushMove::None);
    // a re-enable inside the same window starts it again (late: TickRush resumes it with the goal scaled down)
    CHECK(R::RushNext(state, true, live, window, 0, 0) == R::RushMove::Start);
    std::string const cafe = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafe.cpp");
    std::string const recompute = Body(cafe, "void Cafe::RecomputeEnabled()");
    std::size_t const off = recompute.find("if (was && !on)");
    std::size_t const reset = recompute.find("R::RushSilentReset(c.rushState, c.rushWindow);");
    std::size_t const on = recompute.find("else if (!was && on)");
    CHECK(off != std::string::npos && reset != std::string::npos && on != std::string::npos);
    CHECK(off < reset && reset < on);
    CHECK(recompute.find("c.rushShouts.clear();") < on);
}

TEST("ShiftTick: a barista the cafe is no longer open to (GmOnly turned on) is ended 'O' before anything else")
{
    R::ShiftLimits const l;
    R::ShiftTimers t;
    R::ShiftFacts f;
    f.lastActionMs = 1000;
    CHECK(R::ShiftTick(f, t, 2000, l).end == 0);
    R::ShiftFacts off = f;
    off.feature = false;
    CHECK(R::ShiftTick(off, t, 2000, l).end == static_cast<char>(CafeShiftEnd::FeatureOff));
    off.alive = false;
    off.inCombat = true;
    CHECK(R::ShiftTick(off, t, 2000, l).end == 'O');
    std::string const cafe = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafe.cpp");
    CHECK(Body(cafe, "void Cafe::TickShifts(").find("f.feature = FeatureFor(p);") != std::string::npos);
}

TEST("TutorialLine: a first drink of tea says nothing; the first C2 after it says both lines, once each")
{
    uint32_t flags = 0;
    D::Recipe const& t1 = Rec(108);
    D::Recipe const& c1 = Rec(101);
    D::Recipe const& c2 = Rec(102);
    for (uint8_t i = 0; i < t1.stepCount; ++i)
        CHECK(R::TutorialLine(t1.steps[i], flags).empty());   // T1: neither Pull Shot nor Steam Milk
    std::vector<std::string> said;
    for (uint8_t i = 0; i < c2.stepCount; ++i)
        if (std::string_view const key = R::TutorialLine(c2.steps[i], flags); !key.empty())
            said.emplace_back(key);
    CHECK((said == std::vector<std::string>{ "tutorialShot", "tutorialSteam" }));
    for (D::Recipe const* r : { &c1, &c2 })                   // never again for this barista
        for (uint8_t i = 0; i < r->stepCount; ++i)
            CHECK(R::TutorialLine(r->steps[i], flags).empty());
    // a black coffee first: the shot line now, the steam line at the first Steam Milk later
    uint32_t other = 0;
    CHECK_EQ(R::TutorialLine(R::ActionPullShot, other), "tutorialShot");
    CHECK(R::TutorialLine(4, other).empty());
    CHECK_EQ(R::TutorialLine(R::ActionSteamMilk, other), "tutorialSteam");
    // the bits sit beside 32 (tutorial done) and outside the CAFP rewards (flags & 31)
    CHECK_EQN((R::FlagShotLineSaid | R::FlagSteamLineSaid) & 63u, 0u);
    CHECK(D::FindAction(R::ActionPullShot) && D::FindAction(R::ActionPullShot)->name == "Pull Shot");
    CHECK(D::FindAction(R::ActionSteamMilk) && D::FindAction(R::ActionSteamMilk)->name == "Steam Milk");
    for (D::Cafe const& c : D::Cafes)
        for (char const* key : { "tutorialShot", "tutorialSteam" })
            CHECK_MSG(!R::StaffLine(c.head, key, 0).empty(), key);
    std::string const cafe = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafe.cpp");
    std::string const start = Body(cafe, "void Cafe::StartStep(");
    CHECK(start.find("R::TutorialLine(action, b->flags)") != std::string::npos);
    CHECK(start.find("if (t.tutorial)") == std::string::npos);
}

TEST("House lines: the worker who starts a player's drink says its own; the owner offers a shift at her gossip")
{
    D::Cafe const& sw = D::Cafes[0];
    D::Cafe const& org = D::Cafes[1];
    for (D::Cafe const* c : { &sw, &org })
    {
        CHECK_EQ(R::HouseLineKey(c->owner, false), "houseOrder");
        CHECK_EQ(R::HouseLineKey(c->owner, true), "takeover");
        CHECK_EQ(R::HouseLineKey(c->head, false), "houseOrder");
        CHECK_EQ(R::HouseLineKey(c->head, true), "houseOrder");   // the head barista has no takeover line
        CHECK(!R::StaffLine(c->head, "houseOrder", 0).empty());
        CHECK(!R::StaffLine(c->owner, "shiftOffered", 0).empty());
    }
    CHECK_EQ(R::StaffLine(sw.head, R::HouseLineKey(sw.head, false), 0),
        "Rosalind's busy, so you've got me. One moment.");
    std::string const cafe = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafe.cpp");
    // the line is said where the worker is known, not by the owner at the take
    CHECK(Body(cafe, "void Cafe::HouseTakes(").find("\"houseOrder\"") == std::string::npos);
    std::string const started = Body(cafe, "void Cafe::HouseStepStarted(");
    CHECK(started.find("Say(o->cafeId, st->role, st->entry, R::HouseLineKey(st->entry, o->takeover));") !=
        std::string::npos);
    CHECK(started.find("!o->houseLineSaid") != std::string::npos);
    // the gossip queues the owner's offer for the next tick, which says it
    CHECK(Body(cafe, "void Cafe::GossipHello(").find("Event::Kind::ShiftOffered") != std::string::npos);
    CHECK(Body(cafe, "void Cafe::DrainEvents(").find("\"shiftOffered\"") != std::string::npos);
}

TEST("TickCrowd: playerNear (and with it the crowd's player scan) does not depend on Customer.Enable")
{
    std::string const cafe = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafe.cpp");
    std::string const tick = Body(cafe, "void Cafe::TickCrowd(");
    std::size_t const near = tick.find("in.playerNear = false;");
    std::size_t const scan = tick.find("ForPlayersOn(MapOf(c)", near);
    CHECK(near != std::string::npos && scan != std::string::npos);
    CHECK(tick.substr(near, scan - near).find("_cfg.customers") == std::string::npos);
}

TEST("The document's CSHIFT 1 refusals are the server's, in its order; CSHIFT 0 off shift is refused cafe_shift")
{
    std::string const doc = bhtest::ReadFile(g_repo + "/docs/BleakholdProtocol.md");
    std::size_t const from = doc.find("`CSHIFT 1`: ");
    std::size_t const to = doc.find("`CSHIFT 0`", from);
    CHECK(from != std::string::npos && to != std::string::npos);
    auto firstSeen = [](std::vector<std::string> const& codes) {
        std::vector<std::string> out;
        for (std::string const& c : codes)
            if (std::find(out.begin(), out.end(), c) == out.end())
                out.push_back(c);
        return out;
    };
    std::vector<std::string> docCodes;
    for (std::size_t at = doc.find('`', from + 12); at != std::string::npos && at < to; at = doc.find('`', at + 1))
    {
        std::size_t const end = doc.find('`', at + 1);
        docCodes.push_back(doc.substr(at + 1, end - at - 1));
        at = end;
    }
    // the server: HandleShift's "already on a shift", then ShiftCheck's returns in order
    std::map<std::string, std::string> const codeOf = { { "Closed", CafeErr::Closed.code },
        { "Paused", CafeErr::Paused.code }, { "Level", CafeErr::Level.code }, { "Where", CafeErr::Where.code },
        { "Dead", CafeErr::Dead.code }, { "Combat", CafeErr::Combat.code }, { "Mounted", CafeErr::Mounted.code },
        { "Afk", CafeErr::Afk.code }, { "Faction", CafeErr::Faction.code }, { "Account", CafeErr::Account.code },
        { "Order", CafeErr::Order.code }, { "BarFull", CafeErr::BarFull.code } };
    std::string const cafe = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafe.cpp");
    std::string const handle = Body(cafe, "void Cafe::HandleShift(");
    CHECK(handle.find("CafeErr::Account.code") < handle.find("StartShift("));
    std::vector<std::string> serverCodes = { CafeErr::Account.code };
    std::string const check = Body(cafe, "std::optional<Refusal> Cafe::ShiftCheck(");
    for (std::size_t at = check.find("return CafeErr::"); at != std::string::npos;
         at = check.find("return CafeErr::", at + 1))
    {
        std::size_t const name = at + 16;
        std::string const id = check.substr(name, check.find(';', name) - name);
        CHECK_MSG(codeOf.count(id) == 1, id);
        if (codeOf.count(id))
            serverCodes.push_back(codeOf.at(id));
    }
    CHECK_EQN(serverCodes.size(), std::size_t(15));
    std::vector<std::string> const want = firstSeen(serverCodes);
    std::vector<std::string> const have = firstSeen(docCodes);
    CHECK_EQN(have.size(), want.size());
    for (std::size_t i = 0; i < std::min(have.size(), want.size()); ++i)
        CHECK_EQ(have[i], want[i]);
    // CSHIFT 0 without a shift at that cafe
    CHECK(handle.find("if (!s || s->cafeId != in.cafeId)\n            return Refuse(player, in, CafeErr::Shift);") !=
        std::string::npos);
    std::string const after = doc.substr(to, doc.find("\n\n", to) - to);
    CHECK(after.find("`cafe_shift`") != std::string::npos);
    CHECK(doc.find("off shift does nothing") == std::string::npos);
    CHECK(doc.find("| `cafe_shift` | not on shift (`CTAKE`, `CSTEP`, `CREL`; `CSHIFT 0` at that caf\xC3\xA9)") !=
        std::string::npos);
}

TEST("The Staff Drink's level text says what the server counts: a shift of 10 drinks, once a day")
{
    D::Level const* seven = D::FindLevel(7);
    CHECK(seven != nullptr);
    if (seven)
        CHECK(seven->text.find("after a shift of 10 drinks, once a day") != std::string_view::npos);
    std::string const cafe = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafe.cpp");
    CHECK(cafe.find("constexpr uint32_t StaffDrinkLevel = 7;") != std::string::npos);
    CHECK(cafe.find("constexpr uint32_t StaffDrinkShiftDrinks = 10;") != std::string::npos);
    CHECK(cafe.find("s.drinks >= StaffDrinkShiftDrinks") != std::string::npos);   // the ended shift's drinks
}

TEST(".cafe barista takes a two-part name in quotes (QuotedString), and the config texts say what the code does")
{
    std::string const mod = g_repo + "/Server/mod-bleakhold-ui";
    std::string const commands = bhtest::ReadFile(mod + "/src/BleakholdCommands.cpp");
    CHECK(commands.find("HandleCafeBarista(ChatHandler* handler, QuotedString quoted, std::string_view what,") !=
        std::string::npos);
    CHECK(commands.find("HandleCafeBarista(ChatHandler* handler, std::string name") == std::string::npos);
    std::string const conf = bhtest::ReadFile(mod + "/conf/mod_bleakhold_ui.conf.dist");
    for (char const* wrong : { "minutes on shift in a Rush", "guests who only sit and chat",
             "a ticket without a step for this long goes back to the queue", "base plus per barista" })
        CHECK_MSG(conf.find(wrong) == std::string::npos, wrong);
    for (char const* right : { "drinks a barista serves during a Rush that meets its",
             "customers at once while nobody is on shift; they order", "character level",
             "a shift that holds a ticket ends after this many seconds without an" })
        CHECK_MSG(conf.find(right) != std::string::npos, right);
}

// =================================================================================================================
// Round-3 review fixes: each test fails on the code before its fix
// =================================================================================================================
TEST("FormHides: a warrior's stance is no disguise; druid forms, Ghost Wolf and unknown forms hide")
{
    CHECK(!R::FormHides(0, false, 0));                                 // FORM_NONE
    for (uint8_t stance : { uint8_t(17), uint8_t(18), uint8_t(19) })   // Battle, Defensive, Berserker Stance
        CHECK(!R::FormHides(stance, true, R::ShapeshiftFlagStance));
    CHECK(!R::FormHides(28, true, R::ShapeshiftFlagStance | 0x40));    // a stance with other flags
    CHECK(R::FormHides(1, true, 0));                                   // Cat Form
    CHECK(R::FormHides(5, true, 0x40));                                // Bear Form, flags without the stance bit
    CHECK(R::FormHides(16, true, 0));                                  // Ghost Wolf
    CHECK(R::FormHides(99, false, 0));                                 // a form the store does not know
    // the core-side check asks the form's flags: no blanket "!= FORM_NONE" any more (it refused every warrior)
    std::string const cafe = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafe.cpp");
    std::string const hidden = Body(cafe, "bool Cafe::Hidden(Player* player) const");
    CHECK(!hidden.empty());
    CHECK(hidden.find("!= FORM_NONE") == std::string::npos);
    CHECK(hidden.find("sSpellShapeshiftFormStore.LookupEntry(form)") != std::string::npos);
    CHECK(hidden.find("R::FormHides(") != std::string::npos);
    CHECK(cafe.find("static_assert(R::ShapeshiftFlagStance == static_cast<uint32_t>(SHAPESHIFT_FLAG_STANCE)") !=
        std::string::npos);
}

TEST("SnapZ: a piece the anchor cannot see stays at the height asked for, the GM's after .cafe here or add")
{
    // the finding's case: the anchor at z 97, the GM 26 yd away behind a building, ground valid, no line of sight
    R::Pose const anchor{ 100.0f, 200.0f, 97.0f, 0.0f };
    for (float gmZ : { 95.5f, 98.5f })
    {
        R::Pose const gm{ 74.0f, 210.0f, gmZ, 1.0f };
        R::Local const l = R::ToLocal(anchor, gm);
        R::Pose const w = R::ToWorld(anchor, l.f, l.l, l.u, l.turn);
        CHECK(Near(w.z, gmZ));
        CHECK(Near(R::SnapZ(true, gmZ, anchor.z + l.u, false), gmZ));     // was anchor.z (97) + 0
        CHECK(Near(R::SnapZ(false, 0.0f, anchor.z + l.u, true), gmZ));    // no ground found: where the GM stood
        CHECK(Near(R::SnapZ(true, gmZ + 0.1f, anchor.z + l.u, true), gmZ + 0.1f));   // seen: on the ground there
    }
    // a layout piece (u 0) snaps around the anchor's height, as before
    CHECK(Near(R::SnapZ(true, 98.0f, 97.0f + 0.0f, true), 98.0f));
    CHECK(Near(R::SnapZ(true, 98.0f, 97.0f + 0.0f, false), 97.0f));
    // a snap piece stands on its floor; a raised piece (on a counter, u above 0) does not
    CHECK(Near(R::PieceFloorZ(true, 95.5f, -1.5f), 95.5f));
    CHECK(Near(R::PieceFloorZ(true, 98.5f, 1.5f), 98.5f));
    CHECK(Near(R::PieceFloorZ(false, 98.05f, 1.05f), 97.0f));
    std::string const site = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafeSite.cpp");
    std::string const recompute = Body(site, "void Cafe::Recompute(CafeRt& c, Piece& p)");
    CHECK(recompute.find("p.z = R::SnapZ(valid, ground, c.anchor.z + p.u, los);") != std::string::npos);
    CHECK(recompute.find("los) + p.u") == std::string::npos);
    std::string const here = Body(site, "void Cafe::CmdHere(");
    CHECK(here.find("p.u = l.u;") != std::string::npos);
    CHECK(here.find("p.snap ? 0.0f") == std::string::npos);
    std::string const add = Body(site, "void Cafe::CmdAdd(");
    CHECK(add.find("p.u = l.u;") != std::string::npos);
    CHECK(add.find("p.u = 0;") == std::string::npos);
    CHECK(Body(site, "float Cafe::FloorZ(").find("R::PieceFloorZ(p.snap, p.z, p.u)") != std::string::npos);
}

TEST("The cafe's gossip opens windows only for a client whose HELLO named the cafe's UI (caps bit 1)")
{
    CHECK_EQN(static_cast<uint32_t>(ClientCapCafeUi), 1u);
    std::string const cafe = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafe.cpp");
    std::string const select = Body(cafe, "void Cafe::GossipSelect(");
    CHECK(!select.empty());
    CHECK(select.find("bool const cafeUi = Ui::HasClientCap(player, ClientCapCafeUi);") != std::string::npos);
    CHECK(select.find("Ui::HasAddon") == std::string::npos);   // any addon is not the cafe's UI
    CHECK(select.find("if (addon)") == std::string::npos);
    CHECK(select.find("_tellRefusals = !cafeUi;") != std::string::npos);
    // ActStart: no shift (and no CAFUI shift) without the cafe's UI
    std::size_t const start = select.find("case ActStart:");
    std::size_t const refuse = select.find("if (!cafeUi)", start);
    std::size_t const shift = select.find("StartShift(player, cafeId, nullptr)", start);
    CHECK(start != std::string::npos && refuse != std::string::npos && shift != std::string::npos && refuse < shift);
    // every other CAFUI of the gossip (menu, board, help, recipes) sits right behind an "if (cafeUi)"
    std::size_t opens = 0;
    for (std::size_t at = select.find("Ui::SendCafeOpenUi("); at != std::string::npos;
         at = select.find("Ui::SendCafeOpenUi(", at + 1))
    {
        ++opens;
        if (at > start && at < shift + 200)
            continue;   // ActStart's, after the refusal above
        std::size_t const gate = select.rfind("if (cafeUi)", at);
        CHECK(gate != std::string::npos && at - gate < 200);
    }
    CHECK_EQN(opens, std::size_t(5));
    // an order made through the gossip gets its status lines in chat unless the cafe's UI shows them
    CHECK(cafe.find("o.viaGossip = in.seq == 0 && !Ui::HasClientCap(player, ClientCapCafeUi);") != std::string::npos);
    std::string const doc = bhtest::ReadFile(g_repo + "/docs/BleakholdProtocol.md");
    CHECK(doc.find("| `HELLO` | `proto, addonVer, dataVer, locale[, caps]` |") != std::string::npos);
    CHECK(doc.find("players whose `HELLO` named the café's UI (`caps` bit 1) get the window") != std::string::npos);
}

TEST("CAFO nextStep is documented as the steps done (CAFT's is the next step from 1), as BuildOrder sends it")
{
    std::string const doc = bhtest::ReadFile(g_repo + "/docs/BleakholdProtocol.md");
    std::size_t const cafo = doc.find("### CAFO (the player's order)");
    std::size_t const next = doc.find("### CAFP", cafo);
    CHECK(cafo != std::string::npos && next != std::string::npos);
    std::string const section = doc.substr(cafo, next - cafo);
    CHECK(Squeeze(section).find("- `nextStep`: the steps done so far, 0 to `stepCount`") != std::string::npos);
    CHECK(section.find("`stepCount` for `R`") != std::string::npos);
    std::string const cafe = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCafe.cpp");
    std::string const build = Body(cafe, "CafeOrderState Cafe::BuildOrder(Player* player)");
    CHECK(build.find("st.nextStep = t->next;") != std::string::npos);          // 0-based: the steps done
    CHECK(build.find("st.nextStep = o->houseStep;") != std::string::npos);     // the house's 0-based step
    CHECK(build.find("st.nextStep = st.stepCount;") != std::string::npos);     // R
    CHECK(cafe.find("ct.nextStep = t.next + 1u;") != std::string::npos);       // CAFT: the next step from 1
}

TEST("CAMPST fed counts the cafe's coffee: the document says so, the camp UI never says food alone")
{
    std::string const doc = bhtest::ReadFile(g_repo + "/docs/BleakholdProtocol.md");
    CHECK(doc.find("- `fed`: `1` while the player has a Well Fed buff (the food XP bonus) or a café coffee") !=
        std::string::npos);
    CHECK(doc.find("(the food XP bonus), else `0`.") == std::string::npos);
    std::string const camp = bhtest::ReadFile(g_repo + "/Interface/AddOns/Bleakhold/Camp.lua");
    CHECK(camp.find("\"Well fed: bonus XP from food\"") == std::string::npos);
    std::string const server = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdCamp.cpp");
    CHECK(server.find("s.fed = Cafe::Instance().HasCoffee(player);") != std::string::npos);
}

TEST("The uninstall says the module SQL is not applied again, and how to reinstall")
{
    std::string const uninstall = bhtest::ReadFile(g_repo +
        "/Server/mod-bleakhold-ui/data/sql/uninstall/cafe_uninstall.sql");
    CHECK(uninstall.find("run again at the next update") == std::string::npos);
    CHECK(uninstall.find("never runs an applied file again while its content is unchanged") != std::string::npos);
    CHECK(uninstall.find("creates the cafe's tables again, empty") != std::string::npos);
    for (char const* file : { "'03_bleakhold_cafe_tables.sql'", "'04_bleakhold_cafe_templates.sql'",
             "'01_bleakhold_cafe_characters.sql'" })
        CHECK_MSG(uninstall.find(file) != std::string::npos, file);
    CHECK(uninstall.find("DELETE FROM `updates` WHERE `name` IN (") != std::string::npos);
    // the reinstall lines are a note: the file itself never touches `updates`
    std::size_t const part1 = uninstall.find("-- Part 1: the world database");
    CHECK(part1 != std::string::npos && uninstall.find("`updates`", part1) == std::string::npos);
}

int main(int argc, char** argv)
{
    if (argc < 2)
    {
        std::fprintf(stderr, "usage: bh_cafe <repo root>\n");
        return 2;
    }
    g_repo = argv[1];
    return bhtest::RunAll();
}
