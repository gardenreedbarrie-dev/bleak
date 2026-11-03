/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The cafe (section 21): every rule and formula that needs no AzerothCore, so tests/cpp/bh_cafe.cpp can check them
 * (grades, quality, XP, points, tips, prices, patience, buffs, the milkshake speed rule, the weekly ranking, Tired,
 * money, the danger pause, the Rush clock, placement maths and the station a barista is at). The game side is
 * BleakholdCafe.cpp; the catalogue is the generated BleakholdCafeData.h. Times are milliseconds unless a name says
 * otherwise; random numbers come in as arguments.
 */

#ifndef BLEAKHOLD_CAFE_RULES_H
#define BLEAKHOLD_CAFE_RULES_H

#include "BleakholdCafeData.h"
#include "BleakholdMessages.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace Bleakhold::CafeRules
{
    namespace D = CafeData;

    inline constexpr float Pi = 3.14159265358979323846f;
    inline constexpr float TwoPi = 2.0f * Pi;

    // =============================================================================================================
    // Catalogue helpers
    // =============================================================================================================
    // The checklist lines of a step list: consecutive equal actions merge into one line ("Scoop Ice Cream x2").
    inline uint8_t CountLines(uint8_t const* steps, std::size_t count)
    {
        uint8_t lines = 0;
        for (std::size_t i = 0; i < count; ++i)
            if (i == 0 || steps[i] != steps[i - 1])
                ++lines;
        return lines;
    }

    inline bool IsTimed(uint8_t actionId)
    {
        D::Action const* a = D::FindAction(actionId);
        return a && a->kind == 'H';
    }

    // The barista level of a total XP (1..10).
    inline uint8_t LevelOf(uint32_t totalXp)
    {
        uint8_t level = 1;
        for (D::Level const& l : D::Levels)
            if (totalXp >= l.xp)
                level = l.level;
        return level;
    }

    inline uint32_t LevelXp(uint8_t level)
    {
        D::Level const* l = D::FindLevel(level);
        return l ? l->xp : 0;
    }

    // The total XP of the next level; nothing at the top level.
    inline std::optional<uint32_t> NextLevelXp(uint8_t level)
    {
        if (D::Level const* l = D::FindLevel(static_cast<uint8_t>(level + 1)))
            return l->xp;
        return std::nullopt;
    }

    // The realm's "First Master Barista" (section 3.9.5): recorded for good and announced to every player, so only at a
    // natural level 10 (not .cafe barista, not a login catch-up) while the cafe is open to everyone, and never for a
    // game master's account. GmOnly testing on the live realm must not claim it, nor show the hidden cafe to everyone.
    inline bool ServerFirstCounts(bool naturalLevelUp, bool gmOnly, bool gameMaster)
    {
        return naturalLevelUp && !gmOnly && !gameMaster;
    }

    // The head barista's tutorial lines (section 2.2): the shot line at the barista's first Pull Shot, the steam line
    // at the first Steam Milk, once each per barista (bits of bleakhold_cafe_barista.flags, next to 32 tutorial done).
    // They follow the barista, not the tutorial ticket: a first drink of tea has neither step, a black coffee no steam.
    inline constexpr uint32_t FlagShotLineSaid = 64, FlagSteamLineSaid = 128;
    inline constexpr uint8_t ActionPullShot = 3, ActionSteamMilk = 5;
    inline std::string_view TutorialLine(uint8_t action, uint32_t& flags)
    {
        bool const shot = action == ActionPullShot;
        uint32_t const bit = shot ? FlagShotLineSaid : FlagSteamLineSaid;
        if ((!shot && action != ActionSteamMilk) || (flags & bit))
            return {};
        flags |= bit;
        return shot ? "tutorialShot" : "tutorialSteam";
    }

    inline uint8_t Tickets(uint8_t level)
    {
        D::Level const* l = D::FindLevel(level);
        return l ? l->tickets : 1;
    }

    inline bool Unlocked(uint8_t level, D::Recipe const& r) { return level >= r.unlock; }

    inline D::Tier const* TierOf(uint8_t tier)
    {
        for (D::Tier const& t : D::Tiers)
            if (t.tier == tier)
                return &t;
        return nullptr;
    }

    // The stand-in template of a piece when the new art is off or its display is missing; furniture and markers
    // have none and keep their entry.
    inline uint32_t PieceEntry(uint32_t entry, bool newArt)
    {
        if (newArt)
            return entry;
        D::GameObject const* go = D::FindGameObject(entry);
        return go && go->standIn ? go->standIn : entry;
    }

    // The catalogue row of a cafe template entry: its own, or for a stand-in (new-art entry + StandInOffset, which
    // has no row of its own) the row of the piece it stands in for (its footprint). nullptr: not a cafe template.
    // A stand-in placed as decor keeps its entry, so PieceEntry spawns it whatever UseNewArt says (V21b).
    inline D::GameObject const* CatalogueGo(uint32_t entry)
    {
        if (D::GameObject const* go = D::FindGameObject(entry))
            return go;
        if (entry < D::GameObjectFirst + D::StandInOffset)
            return nullptr;
        D::GameObject const* art = D::FindGameObject(entry - D::StandInOffset);
        return art && art->standIn == entry ? art : nullptr;
    }

    // "{drink}" -> the drink's name, "{n}" -> a level.
    inline std::string Fill(std::string_view text, std::string_view key, std::string_view value)
    {
        std::string out(text);
        for (std::size_t at = out.find(key); at != std::string::npos; at = out.find(key, at + value.size()))
            out.replace(at, key.size(), value);
        return out;
    }

    // =============================================================================================================
    // Steps: the gold zone, the grade and the release time
    // =============================================================================================================
    inline constexpr uint32_t GoldMinPermille = 50;     // a shifted gold zone stays inside 5%..95% of the bar
    inline constexpr uint32_t GoldMaxPermille = 950;
    inline constexpr uint32_t AutoReleaseMs = 300;      // a timed step not released by durMs + this is Off
    inline constexpr uint32_t MinLagMs = 100;

    struct GoldZone { uint32_t lo = 0, hi = 0; };       // permille of the bar

    // The random shift of a gold zone, a whole permille in [-max, +max]; `random` is any 32-bit random number.
    inline int32_t GoldShift(uint32_t random, uint32_t maxShiftPermille)
    {
        uint32_t const span = 2 * maxShiftPermille + 1;
        return static_cast<int32_t>(random % span) - static_cast<int32_t>(maxShiftPermille);
    }

    // The gold zone moved by `shift` permille, kept inside [GoldMinPermille, GoldMaxPermille] with its width.
    inline GoldZone ShiftGold(uint32_t lo, uint32_t hi, int32_t shift)
    {
        if (hi < lo)
            std::swap(lo, hi);
        uint32_t const width = std::min(hi - lo, GoldMaxPermille - GoldMinPermille);
        int64_t moved = static_cast<int64_t>(lo) + shift;
        moved = std::clamp<int64_t>(moved, GoldMinPermille, static_cast<int64_t>(GoldMaxPermille - width));
        GoldZone z;
        z.lo = static_cast<uint32_t>(moved);
        z.hi = z.lo + width;
        return z;
    }

    inline uint32_t PermilleOf(uint32_t durMs, uint32_t permille)
    {
        return static_cast<uint32_t>(uint64_t(durMs) * permille / 1000);
    }

    // P inside [goldLoMs, goldHiMs] (both edges included), G within padPermille of the bar around it, else O; a release
    // at or after the end of the bar is always O.
    inline char Grade(uint32_t elapsedMs, uint32_t durMs, uint32_t goldLoMs, uint32_t goldHiMs, uint32_t padPermille)
    {
        if (elapsedMs >= durMs)
            return 'O';
        if (elapsedMs >= goldLoMs && elapsedMs <= goldHiMs)
            return 'P';
        uint32_t const pad = PermilleOf(durMs, padPermille);
        uint32_t const lo = goldLoMs > pad ? goldLoMs - pad : 0;
        if (elapsedMs >= lo && elapsedMs <= goldHiMs + pad)
            return 'G';
        return 'O';
    }

    // The time a release counts at: what the client measured, but never later than the server saw it and never more
    // than lag earlier, lag = clamp(latency + slack, 100, maxLag).
    inline uint32_t ReleaseElapsed(uint32_t clientMs, uint32_t serverElapsedMs, uint32_t latencyMs, uint32_t slackMs,
        uint32_t maxLagMs)
    {
        uint32_t const top = std::max(MinLagMs, maxLagMs);
        uint32_t const lag = static_cast<uint32_t>(std::clamp<uint64_t>(uint64_t(latencyMs) + slackMs, MinLagMs, top));
        uint32_t const earliest = serverElapsedMs > lag ? serverElapsedMs - lag : 0;
        return std::clamp(clientMs, earliest, serverElapsedMs);
    }

    // The release offset from the gold centre (bot hints).
    inline int32_t ReleaseOffset(uint32_t elapsedMs, uint32_t goldLoMs, uint32_t goldHiMs)
    {
        int64_t const centre = (int64_t(goldLoMs) + int64_t(goldHiMs)) / 2;
        return static_cast<int32_t>(int64_t(elapsedMs) - centre);
    }

    // =============================================================================================================
    // Quality, XP, points, tips
    // =============================================================================================================
    // The drink: P when every timed step is P and at least 25% of the patience is left, S with any Off step, else G.
    // Taps are recorded as P, so they never lower it.
    inline char Quality(uint8_t const* steps, char const* grades, std::size_t count, uint32_t patienceLeftPermille)
    {
        bool allPerfect = true;
        for (std::size_t i = 0; i < count; ++i)
        {
            if (grades[i] == 'O')
                return 'S';
            if (IsTimed(steps[i]) && grades[i] != 'P')
                allPerfect = false;
        }
        return allPerfect && patienceLeftPermille >= 250 ? 'P' : 'G';
    }

    inline uint32_t QualityTenths(char quality)      // Q of XP and points, x10
    {
        switch (quality)
        {
            case 'P': return 15;
            case 'G': return 10;
            case 'S': return 5;
            default: return 0;
        }
    }

    inline uint32_t TipQualityTenths(char quality)   // Qt of tips, x10
    {
        switch (quality)
        {
            case 'P': return 15;
            case 'G': return 10;
            case 'S': return 4;
            default: return 0;
        }
    }

    // The streak multiplier K, in hundredths: 1 + 0.05 x (streak - 1), at most 1.25 (streak 0 or 1: 1.0).
    inline uint32_t StreakHundredths(uint32_t streak)
    {
        if (streak <= 1)
            return 100;
        return std::min<uint32_t>(125, 100 + 5 * (streak - 1));
    }

    // The same recipe again: the 4th in a row counts 75%, the 5th and later 50%.
    inline uint32_t RepeatPct(uint32_t inARow)
    {
        if (inARow <= 3)
            return 100;
        return inARow == 4 ? 75 : 50;
    }

    // The player-order boost: the first `perDay` drinks of a (barista, customer) pair a day.
    inline bool PairBoost(uint32_t servedBefore, uint32_t perDay) { return servedBefore < perDay; }

    struct DrinkFacts
    {
        uint8_t tier = 1;
        char quality = 'G';
        uint32_t patienceLeftPermille = 0;
        uint32_t streak = 0;             // consecutive Perfect drinks, this one included (0 when not Perfect)
        bool pairBoost = false;          // a player order within the pair's first PairBoostPerDay
        bool rush = false;
        bool tired = false;
        uint32_t tiredPct = 50;          // BleakholdUi.Cafe.Tired.Pct
        uint32_t inARow = 1;             // this recipe in a row, this one included
    };

    // XP = floor(base x Q x S x K x P x R x T x Rep), before the daily cap.
    inline uint32_t XpForDrink(DrinkFacts const& f)
    {
        D::Tier const* t = TierOf(f.tier);
        if (!t)
            return 0;
        uint64_t v = t->xp;
        v *= QualityTenths(f.quality);                           // /10
        v *= f.patienceLeftPermille >= 500 ? 12u : 10u;          // /10
        v *= StreakHundredths(f.streak);                         // /100
        v *= f.pairBoost ? 15u : 10u;                            // /10
        v *= f.rush ? 125u : 100u;                               // /100
        v *= f.tired ? std::min<uint32_t>(f.tiredPct, 100) : 100u;   // /100
        v *= RepeatPct(f.inARow);                                // /100
        return static_cast<uint32_t>(v / 100000000000ull);
    }

    // Points = round(base x Q x S x R x T): no streak, pair or repeat factor, so trading orders cannot inflate them.
    inline uint32_t PointsForDrink(DrinkFacts const& f)
    {
        D::Tier const* t = TierOf(f.tier);
        if (!t)
            return 0;
        uint64_t v = t->xp;
        v *= QualityTenths(f.quality);
        v *= f.patienceLeftPermille >= 500 ? 12u : 10u;
        v *= f.rush ? 125u : 100u;
        v *= f.tired ? std::min<uint32_t>(f.tiredPct, 100) : 100u;
        return static_cast<uint32_t>((v + 500000) / 1000000);
    }

    // The daily XP cap: the first fullCap XP earned in a day count fully, the next halfCap count half, then nothing.
    struct XpCredit
    {
        uint32_t credited = 0;           // added to the barista
        uint32_t cut = 0;                // what the cap took (CAFRES xpCapped)
        uint32_t fullUsed = 0, halfUsed = 0;   // the day row after this drink (XP earned in each band)
    };
    inline XpCredit CreditXp(uint32_t earned, uint32_t fullUsed, uint32_t halfUsed, uint32_t fullCap, uint32_t halfCap)
    {
        XpCredit c;
        c.fullUsed = std::min(fullUsed, fullCap);
        c.halfUsed = std::min(halfUsed, halfCap);
        uint32_t const inFull = std::min(earned, fullCap - c.fullUsed);
        uint32_t const inHalf = std::min(earned - inFull, halfCap - c.halfUsed);
        // half of every XP earned in the half band, counted over the whole day so no half point is lost
        uint32_t const halfBefore = c.halfUsed / 2;
        c.fullUsed += inFull;
        c.halfUsed += inHalf;
        c.credited = inFull + (c.halfUsed / 2 - halfBefore);
        c.cut = earned - c.credited;
        return c;
    }

    inline uint32_t PointsCap(uint32_t cap, uint32_t rushExtra, bool rushDay) { return cap + (rushDay ? rushExtra : 0); }

    inline uint32_t CapAdd(uint32_t amount, uint32_t used, uint32_t cap)
    {
        return used >= cap ? 0 : std::min(amount, cap - used);
    }

    // Tip = floor(tierTip x Qt x tip% x max(0.15, level/80) x Rush 1.5 x Regulars 1.1 at barista level 9+).
    inline uint32_t TipForDrink(uint8_t tier, char quality, uint32_t personaTipPct, uint32_t charLevel, bool rush,
        uint8_t baristaLevel)
    {
        D::Tier const* t = TierOf(tier);
        if (!t)
            return 0;
        uint64_t v = t->tip;
        v *= TipQualityTenths(quality);                          // /10
        v *= personaTipPct;                                      // /100
        v *= std::max<uint64_t>(1500, uint64_t(charLevel) * 125);   // level/80 in 1/10000 (/10000)
        v *= rush ? 15u : 10u;                                   // /10
        v *= baristaLevel >= 9 ? 11u : 10u;                      // /10
        return static_cast<uint32_t>(v / 1000000000ull);
    }

    // The NPC tips a barista may earn a day: base + perLevel x character level.
    inline uint32_t TipCap(uint32_t baseCopper, uint32_t perLevelCopper, uint32_t charLevel)
    {
        return static_cast<uint32_t>(std::min<uint64_t>(uint64_t(baseCopper) + uint64_t(perLevelCopper) * charLevel,
            0xFFFFFFFFull));
    }

    // A player's price: max(minCopper, price80 x max(floorPct/100, level/80) rounded up to whole silver).
    inline uint32_t PriceCopper(uint32_t price80, uint32_t charLevel, uint32_t minCopper, uint32_t floorPct)
    {
        // price80 x m / 8000 with m = max(floorPct x 80, level x 100), rounded up to 100
        uint64_t const m = std::max<uint64_t>(uint64_t(floorPct) * 80, uint64_t(charLevel) * 100);
        uint64_t const scaled = uint64_t(price80) * m;
        uint64_t const silver = (scaled + 799999) / 800000;
        return static_cast<uint32_t>(std::max<uint64_t>(minCopper, std::min<uint64_t>(silver * 100, 0xFFFFFFFFull)));
    }

    inline uint32_t TipCopper(uint32_t price, uint32_t tipPct) { return static_cast<uint32_t>(uint64_t(price) * tipPct / 100); }

    // =============================================================================================================
    // Patience, arrivals, house time
    // =============================================================================================================
    inline uint32_t RushPatience(uint64_t ms, bool rush) { return static_cast<uint32_t>(rush ? ms * 85 / 100 : ms); }

    // In the queue: queueSec x persona%.
    inline uint32_t QueuePatienceMs(uint32_t queueSec, uint32_t personaPct, bool rush)
    {
        return RushPatience(uint64_t(queueSec) * 1000 * personaPct / 100, rush);
    }

    // After the order is taken: (baseSec + perLineSec x lines) x persona%.
    inline uint32_t DrinkPatienceMs(uint32_t baseSec, uint32_t perLineSec, uint32_t lines, uint32_t personaPct, bool rush)
    {
        uint64_t const sec = uint64_t(baseSec) + uint64_t(perLineSec) * lines;
        return RushPatience(sec * 1000 * personaPct / 100, rush);
    }

    // The patience left in permille of its phase (for Quality and S).
    inline uint32_t PatienceLeftPermille(uint64_t nowMs, uint64_t endMs, uint32_t maxMs)
    {
        if (!maxMs || nowMs >= endMs)
            return 0;
        return static_cast<uint32_t>(std::min<uint64_t>(1000, (endMs - nowMs) * 1000 / maxMs));
    }

    // The time between two NPC customers: IntervalSec / (factor ^ (min(baristas, 4) - 1)), twice as long with nobody on
    // shift (ambient customers), divided by 2.5 during the Rush. The crowd adds its own jitter.
    inline uint32_t ArrivalIntervalMs(uint32_t intervalSec, uint32_t factorPct, uint32_t baristas, bool rush)
    {
        uint64_t ms = uint64_t(intervalSec) * 1000;
        if (baristas == 0)
            ms *= 2;
        else
            for (uint32_t i = 1; i < std::min<uint32_t>(baristas, 4); ++i)
                ms = ms * 100 / std::max<uint32_t>(factorPct, 100);
        if (rush)
            ms = ms * 2 / 5;
        return static_cast<uint32_t>(std::min<uint64_t>(ms, 0xFFFFFFFFull));
    }

    // How long the house takes at least: base + perLine x lines (seconds).
    inline uint32_t HouseMinTotalMs(uint32_t baseSec, uint32_t perLineSec, uint32_t lines)
    {
        return static_cast<uint32_t>((uint64_t(baseSec) + uint64_t(perLineSec) * lines) * 1000);
    }

    // A waiting NPC order the house makes: at once with nobody on shift, or when it is the first waiting order of the
    // queue (taken and house orders stay in the queue until their drink is ready), has waited TakeTimeoutSec and no
    // barista on shift has the level for it.
    inline bool NpcHouseDue(uint8_t baristas, bool firstWaiting, uint64_t waitedMs, uint32_t takeTimeoutMs,
        uint8_t maxBaristaLevel, uint8_t unlock)
    {
        if (!baristas)
            return true;
        return firstWaiting && waitedMs >= takeTimeoutMs && maxBaristaLevel < unlock;
    }

    // The first order of a queue still waiting ('W'); 0 for none. `stateOf` gives an order's state (0: gone).
    template <typename StateOf>
    uint32_t FirstWaiting(std::vector<uint32_t> const& queue, StateOf&& stateOf)
    {
        for (uint32_t id : queue)
            if (stateOf(id) == 'W')
                return id;
        return 0;
    }

    // CAFE (section 21): a change of open, the baristas, the Rush or the house's time is sent within CafeListMinGapMs;
    // the queue's length alone at most every CafeListQueueGapMs.
    inline constexpr uint64_t CafeListMinGapMs = 500;
    inline constexpr uint64_t CafeListQueueGapMs = 5000;
    inline bool CafeListMark(bool keyChanged, bool queueLenChanged, uint64_t sinceSentMs)
    {
        return keyChanged || (queueLenChanged && sinceSentMs >= CafeListQueueGapMs);
    }

    // =============================================================================================================
    // Buffs
    // =============================================================================================================
    inline constexpr uint32_t BuffBonusMin = 10;    // a Perfect drink, the Rush, a Lingering Sip

    // The buff of a drink: the tier's base, +10 for Perfect, +10 during the Rush, +10 for a Lingering Sip, at most max.
    inline uint32_t BuffMinutes(uint8_t tier, bool perfect, bool rush, bool linger, uint32_t maxMin)
    {
        D::Tier const* t = TierOf(tier);
        uint32_t const m = (t ? t->buffMin : 30) + (perfect ? BuffBonusMin : 0) + (rush ? BuffBonusMin : 0) +
            (linger ? BuffBonusMin : 0);
        return std::min(m, maxMin);
    }

    // The same family again keeps the longer of what is left and the new drink.
    inline uint32_t MergeBuffMs(uint32_t remainingMs, uint32_t newMs) { return std::max(remainingMs, newMs); }

    // A Lingering Sip: +10 minutes on the drink's buff, within the cap.
    inline uint32_t LingerMs(uint32_t remainingMs, uint32_t maxMin)
    {
        uint64_t const cap = uint64_t(maxMin) * 60000;
        return static_cast<uint32_t>(std::min<uint64_t>(uint64_t(remainingMs) + BuffBonusMin * 60000ull, cap));
    }

    // Lingering Sip (section 3.9.4): sit down in a cafe chair within 120 s of receiving a drink and stay seated 60 s,
    // once per drink. Standing up starts the 60 s again, if the 120 s still allow sitting down.
    inline constexpr uint64_t LingerSitWithinMs = 120000;
    inline constexpr uint64_t LingerSeatedMs = 60000;
    struct Linger
    {
        uint32_t spell = 0;                  // the drink's family buff
        uint64_t receivedMs = 0;
        uint64_t seatedSinceMs = 0;          // 0: not seated
    };
    enum class LingerStep : uint8_t { Wait, Grant, Drop };
    // The 1 s pass: Grant once (the record goes), Drop when it can no longer happen.
    inline LingerStep LingerTick(Linger& l, bool seated, uint64_t nowMs)
    {
        if (!seated)
        {
            l.seatedSinceMs = 0;
            return nowMs - l.receivedMs > LingerSitWithinMs ? LingerStep::Drop : LingerStep::Wait;
        }
        if (!l.seatedSinceMs)
        {
            if (nowMs - l.receivedMs > LingerSitWithinMs)
                return LingerStep::Drop;
            l.seatedSinceMs = nowMs;
        }
        return nowMs - l.seatedSinceMs >= LingerSeatedMs ? LingerStep::Grant : LingerStep::Wait;
    }

    // What the milkshake's hidden speed helper needs: the visible buff, a city or inn (never the camp's faction-area
    // bit), peace and the open world.
    struct ShakeFacts
    {
        bool featureOn = true;           // BleakholdUi.Cafe.Enable and the startup checks
        bool visibleBuff = false;        // Sugar Rush / Stampede Sprint
        bool restCity = false, restTavern = false;
        bool inCombat = false, pvp = false, ffaPvp = false, duel = false;
        bool mounted = false, vehicle = false, flight = false;
        bool worldMap = true, alive = true;
    };
    inline bool ShakeActive(ShakeFacts const& f)
    {
        return f.featureOn && f.visibleBuff && (f.restCity || f.restTavern) && !f.inCombat && !f.pvp && !f.ffaPvp &&
            !f.duel && !f.mounted && !f.vehicle && !f.flight && f.worldMap && f.alive;
    }

    enum class HelperAction : uint8_t { None, Add, Remove, Follow };
    // What the 1 s pass does with the helper: add it (active, missing), take it away (inactive, present), or give it the
    // visible buff's time when that changed (a merged drink).
    inline HelperAction ShakeHelper(bool active, bool helperPresent, uint32_t helperMs, uint32_t visibleMs)
    {
        if (active && !helperPresent)
            return HelperAction::Add;
        if (!active && helperPresent)
            return HelperAction::Remove;
        if (active && helperPresent && (helperMs + 1500 < visibleMs || helperMs > visibleMs + 1500))
            return HelperAction::Follow;
        return HelperAction::None;
    }

    // No cafe reward on battleground or arena maps or in a battlefield zone (Wintergrasp).
    inline bool RewardPlaceOk(bool battlegroundOrArena, bool battlefieldZone)
    {
        return !battlegroundOrArena && !battlefieldZone;
    }

    // "509, 510,729" -> {509, 510, 729}: any non-digit separates.
    inline std::vector<uint32_t> ParseIds(std::string_view s)
    {
        std::vector<uint32_t> out;
        uint64_t v = 0;
        bool in = false;
        for (char c : s)
        {
            if (c >= '0' && c <= '9')
            {
                v = std::min<uint64_t>(v * 10 + static_cast<uint64_t>(c - '0'), 0xFFFFFFFFull);
                in = true;
            }
            else if (in)
            {
                out.push_back(static_cast<uint32_t>(v));
                v = 0;
                in = false;
            }
        }
        if (in)
            out.push_back(static_cast<uint32_t>(v));
        return out;
    }

    inline bool TeaExcludesFaction(std::vector<uint32_t> const& excluded, uint32_t faction)
    {
        return std::find(excluded.begin(), excluded.end(), faction) != excluded.end();
    }

    // =============================================================================================================
    // Days, weeks, the weekly ranking
    // =============================================================================================================
    // The id of the period that ends at the next reset (monotonic).
    inline uint32_t PeriodId(uint32_t nextResetEpoch, uint32_t periodSec) { return periodSec ? nextResetEpoch / periodSec : 0; }
    inline constexpr uint32_t DaySec = 86400;
    inline constexpr uint32_t WeekSec = 604800;

    // The day's bit in a week's days_mask: seven consecutive day ids have seven different bits.
    inline uint8_t DayBit(uint32_t dayId) { return static_cast<uint8_t>(1u << (dayId % 7)); }

    inline uint32_t Bits(uint32_t mask)
    {
        uint32_t n = 0;
        for (; mask; mask &= mask - 1)
            ++n;
        return n;
    }

    // The fallback reset when the realm gives none: the next `hour` o'clock (local seconds of the day given), and the
    // next `weekday` (0 Sunday) at that hour.
    inline uint32_t FallbackDailyReset(uint32_t nowEpoch, int32_t utcOffsetSec, uint32_t hour)
    {
        int64_t const local = int64_t(nowEpoch) + utcOffsetSec;
        int64_t const dayStart = local - ((local % DaySec) + DaySec) % DaySec;
        int64_t next = dayStart + int64_t(std::min<uint32_t>(hour, 23)) * 3600;
        if (next <= local)
            next += DaySec;
        return static_cast<uint32_t>(std::max<int64_t>(0, next - utcOffsetSec));
    }

    inline uint32_t FallbackWeeklyReset(uint32_t nowEpoch, int32_t utcOffsetSec, uint32_t hour, uint32_t weekday)
    {
        uint32_t next = FallbackDailyReset(nowEpoch, utcOffsetSec, hour);
        // 1970-01-01 was a Thursday (4)
        for (int i = 0; i < 7; ++i)
        {
            int64_t const local = int64_t(next) + utcOffsetSec;
            uint32_t const wd = static_cast<uint32_t>(((local / DaySec) % 7 + 4) % 7);
            if (wd == weekday % 7)
                break;
            next += DaySec;
        }
        return next;
    }

    struct WeekRow
    {
        uint32_t guid = 0;
        uint8_t cafeId = 0;
        std::string name;
        uint8_t classId = 0;
        uint32_t points = 0, drinks = 0, perfects = 0;
        uint8_t daysMask = 0;
        uint32_t scoreAt = 0;            // when the points last rose
    };

    inline uint32_t PerfectPermille(uint32_t perfects, uint32_t drinks)
    {
        return drinks ? static_cast<uint32_t>(std::min<uint64_t>(1000, uint64_t(perfects) * 1000 / drinks)) : 0;
    }

    inline bool WeeklyEligible(WeekRow const& r, uint32_t minDrinks, uint32_t minDays)
    {
        return r.drinks >= minDrinks && Bits(r.daysMask) >= minDays;
    }

    // Best Barista: the eligible rows by points, then Perfect rate, then who got there first, then guid.
    inline std::vector<WeekRow> WeeklyRank(std::vector<WeekRow> rows, uint32_t minDrinks, uint32_t minDays)
    {
        rows.erase(std::remove_if(rows.begin(), rows.end(),
            [&](WeekRow const& r) { return !WeeklyEligible(r, minDrinks, minDays); }), rows.end());
        std::sort(rows.begin(), rows.end(), [](WeekRow const& a, WeekRow const& b) {
            if (a.points != b.points)
                return a.points > b.points;
            uint32_t const pa = PerfectPermille(a.perfects, a.drinks);
            uint32_t const pb = PerfectPermille(b.perfects, b.drinks);
            if (pa != pb)
                return pa > pb;
            if (a.scoreAt != b.scoreAt)
                return a.scoreAt < b.scoreAt;
            return a.guid < b.guid;
        });
        return rows;
    }

    // The weekly reward of a rank (from 1): the list of BleakholdUi.Cafe.Weekly.RewardCopper, 0 past its end.
    inline uint32_t Payout(uint32_t rank, std::vector<uint32_t> const& rewards)
    {
        return rank >= 1 && rank <= rewards.size() ? rewards[rank - 1] : 0;
    }

    // The ended weeks still to pay at startup or when the feature comes on: a week can end while the server is down
    // (the realm's reset source counts from the wall clock, so the startup already sees the next week). Every week
    // before `current`, at most `maxAgeWeeks` back, with board rows and no payout row (`paid`: the weeks paid at both
    // cafes), oldest first. Week ids may skip one at the year's end, so this never assumes current - 1.
    inline constexpr uint32_t MissedWeeksMax = 4;
    inline std::vector<uint32_t> WeeksToPay(std::vector<uint32_t> weeksWithRows, std::vector<uint32_t> const& paid,
        uint32_t current, uint32_t maxAgeWeeks = MissedWeeksMax)
    {
        std::sort(weeksWithRows.begin(), weeksWithRows.end());
        weeksWithRows.erase(std::unique(weeksWithRows.begin(), weeksWithRows.end()), weeksWithRows.end());
        std::vector<uint32_t> out;
        for (uint32_t w : weeksWithRows)
            if (w && w < current && current - w <= maxAgeWeeks && std::find(paid.begin(), paid.end(), w) == paid.end())
                out.push_back(w);
        return out;
    }

    // LBQ C is cached for this week and the last (the two the client asks for); any other week is read uncached, so
    // the cache cannot grow with the week ids a client makes up.
    inline bool BoardCached(uint32_t weekId, uint32_t currentWeek)
    {
        return weekId == currentWeek || (currentWeek && weekId == currentWeek - 1);
    }

    // =============================================================================================================
    // Tired (rewards x Tired.Pct after AfterMin on shift without a RestMin break)
    // =============================================================================================================
    struct TiredRow { uint32_t accumSec = 0; uint32_t offSince = 0; };   // bleakhold_cafe_barista: shift_accum_sec,
                                                                       // off_shift_since (0 while on shift)
    inline bool Rested(TiredRow const& t, uint32_t nowSec, uint32_t restMin)
    {
        return t.offSince && nowSec >= t.offSince && nowSec - t.offSince >= restMin * 60;
    }

    inline bool IsTired(TiredRow const& t, uint32_t nowSec, uint32_t afterMin, uint32_t restMin)
    {
        return t.accumSec >= afterMin * 60 && !Rested(t, nowSec, restMin);
    }

    // A row read from the table: off_shift_since 0 with time on shift is a shift the last run never ended (a crash,
    // a kill); no shift of this run is live when a row is read, so the break counts from `sinceSec` (the startup).
    inline TiredRow TiredLoaded(TiredRow t, uint32_t sinceSec)
    {
        if (!t.offSince && t.accumSec)
            t.offSince = sinceSec;
        return t;
    }

    // A shift starts: a long enough break clears the time on shift.
    inline TiredRow TiredOnShiftStart(TiredRow t, uint32_t nowSec, uint32_t restMin)
    {
        if (Rested(t, nowSec, restMin))
            t.accumSec = 0;
        t.offSince = 0;
        return t;
    }

    // CAFST tiredSec: on shift, the seconds before Tired; while Tired, the break still needed.
    inline std::optional<uint32_t> TiredSec(TiredRow const& t, uint32_t nowSec, bool onShift, uint32_t afterMin,
        uint32_t restMin)
    {
        if (IsTired(t, nowSec, afterMin, restMin))
        {
            if (onShift || !t.offSince)
                return restMin * 60;
            uint32_t const off = nowSec - t.offSince;
            return off >= restMin * 60 ? 0 : restMin * 60 - off;
        }
        if (!onShift)
            return std::nullopt;
        return afterMin * 60 - std::min(t.accumSec, afterMin * 60);
    }

    // =============================================================================================================
    // Money (D13): every path splits what the customer paid into the barista's wage, the house and a refund
    // =============================================================================================================
    struct Money
    {
        uint32_t paid = 0;               // price + tip
        uint32_t barista = 0;            // the wage: floor(price x share/100) + tip
        uint32_t house = 0;              // kept by the house (a gold sink)
        uint32_t refunded = 0;
    };

    inline uint32_t WageCopper(uint32_t price, uint32_t tip, uint32_t sharePct)
    {
        return static_cast<uint32_t>(uint64_t(price) * std::min<uint32_t>(sharePct, 100) / 100 + tip);
    }

    // The refund of an expired pickup: the house share of the price.
    inline uint32_t HouseShareCopper(uint32_t price, uint32_t sharePct)
    {
        return static_cast<uint32_t>(uint64_t(price) * (100 - std::min<uint32_t>(sharePct, 100)) / 100);
    }

    enum class OrderEnd : uint8_t
    {
        ServedDelivered,     // a barista made it, the customer picked it up
        ServedExpired,       // a barista made it, the pickup ran out: the house share back
        HouseDelivered,      // the house made it (nobody is paid)
        HouseExpired,        // the house made it, the pickup ran out: the house share back
        Cancelled,           // CCANCEL (W, or H after a takeover), the cafe closed, the feature turned off: all back
        StartupOpen,         // found at startup in W, T or H: all back
        StartupReadyPaid,    // found at startup in R with a barista paid: the house share back
        StartupReadyHouse,   // found at startup in R made by the house: all back
    };

    inline Money SettleOrder(OrderEnd end, uint32_t price, uint32_t tip, uint32_t sharePct)
    {
        Money m;
        m.paid = price + tip;
        switch (end)
        {
            case OrderEnd::ServedDelivered:
                m.barista = WageCopper(price, tip, sharePct);
                break;
            case OrderEnd::ServedExpired:
            case OrderEnd::StartupReadyPaid:
                m.barista = WageCopper(price, tip, sharePct);
                m.refunded = HouseShareCopper(price, sharePct);
                break;
            case OrderEnd::HouseDelivered:
                break;
            case OrderEnd::HouseExpired:
                m.refunded = HouseShareCopper(price, sharePct);
                break;
            case OrderEnd::Cancelled:
            case OrderEnd::StartupOpen:
            case OrderEnd::StartupReadyHouse:
                m.refunded = m.paid;
                break;
        }
        m.house = m.paid - m.barista - m.refunded;
        return m;
    }

    // The startup settlement of a stored order row: state W T H R, and whether a barista was paid (barista_guid).
    // Turning the feature off settles a ready order the same way (the house share back, or all of a house-made drink).
    inline OrderEnd StartupEnd(char state, bool baristaPaid)
    {
        if (state == 'R')
            return baristaPaid ? OrderEnd::StartupReadyPaid : OrderEnd::StartupReadyHouse;
        return OrderEnd::StartupOpen;
    }

    // What has to go with an order besides its money when it ends early (refund, cancel, a customer gone, a deleted
    // character): the barista's ticket ('T'), the house job ('H'), the cup waiting on the counter ('R').
    enum OrderLeftovers : uint8_t { LeftTicket = 1, LeftHouseJob = 2, LeftCounterCup = 4 };
    inline uint8_t OrderLeftoversOf(char state, bool cupOnCounter)
    {
        switch (state)
        {
            case 'T': return LeftTicket;
            case 'H': return LeftHouseJob;
            case 'R': return cupOnCounter ? LeftCounterCup : 0;
            default: return 0;
        }
    }

    // After the crowd's site was spawned again (a layout change): its house jobs, counter cups and deliveries are
    // gone, so every player order the house was making is queued again, and every ready one gets its cup back.
    enum class Respawned : uint8_t { Nothing, RequeueHouseJob, PlaceCup };
    inline Respawned AfterRespawn(char kind, char state, bool cupOnCounter)
    {
        if (kind != 'P')
            return Respawned::Nothing;   // NPC orders leave with their customers
        if (state == 'H')
            return Respawned::RequeueHouseJob;
        if (state == 'R' && cupOnCounter)
            return Respawned::PlaceCup;
        return Respawned::Nothing;
    }

    // A player order goes to the house when its drink patience ran out or its ticket was ruined MaxRuins times.
    inline bool TakeoverDue(uint64_t nowMs, uint64_t patienceEndMs, uint32_t ruins, uint32_t maxRuins)
    {
        return nowMs >= patienceEndMs || ruins >= maxRuins;
    }

    // CCANCEL: while waiting, or while the house finishes it after a barista's failure.
    inline bool CancelAllowed(char state, bool takeover) { return state == 'W' || (state == 'H' && takeover); }

    // =============================================================================================================
    // Danger: the pause and the close
    // =============================================================================================================
    struct HostileFacts
    {
        bool otherTeam = false, pvp = false, alive = false, gm = false, spectator = false;
        bool stealth = false, invisible = false, los = false, inCombat = false;
        float dist2d = 0, dz = 0;
    };

    // A player of the other team, PvP-flagged, alive, no GM, seen (no stealth or invisibility), at the counter's height
    // and in its line of sight, and near it or fighting within the wider radius.
    inline bool HostileQualifies(HostileFacts const& f, float nearRadius, float radius, float maxDz)
    {
        if (!f.otherTeam || !f.pvp || !f.alive || f.gm || f.spectator || f.stealth || f.invisible || !f.los)
            return false;
        if (std::fabs(f.dz) > maxDz)
            return false;
        return f.dist2d <= nearRadius || (f.inCombat && f.dist2d <= radius);
    }

    struct DangerTimes { uint32_t confirmMs = 5000, resumeMs = 20000, pauseMaxMs = 90000, reopenMs = 120000; };
    struct Danger
    {
        uint8_t open = 1;                // 1 open, 2 paused, 4 closed
        uint64_t lastHostileMs = 0;
        uint64_t pauseSinceMs = 0;
    };
    enum class DangerEvent : uint8_t { None, Paused, Resumed, Closed, Reopened };

    // One check (every second). `confirmed`: a qualifying hostile has qualified for ConfirmSec in a row; `present`: one
    // qualifies now (it keeps a pause or a close going).
    inline DangerEvent DangerStep(Danger& d, bool confirmed, bool present, uint64_t nowMs, DangerTimes const& t)
    {
        if (present || confirmed)
            d.lastHostileMs = nowMs;
        switch (d.open)
        {
            case 1:
                if (confirmed)
                {
                    d.open = 2;
                    d.pauseSinceMs = nowMs;
                    return DangerEvent::Paused;
                }
                return DangerEvent::None;
            case 2:
                if (nowMs - d.pauseSinceMs >= t.pauseMaxMs)
                {
                    d.open = 4;
                    return DangerEvent::Closed;
                }
                if (nowMs - d.lastHostileMs >= t.resumeMs)
                {
                    d.open = 1;
                    return DangerEvent::Resumed;
                }
                return DangerEvent::None;
            case 4:
                if (nowMs - d.lastHostileMs >= t.reopenMs)
                {
                    d.open = 1;
                    return DangerEvent::Reopened;
                }
                return DangerEvent::None;
            default:
                return DangerEvent::None;
        }
    }

    // =============================================================================================================
    // The Morning Rush
    // =============================================================================================================
    // "08:00, 17:30" -> seconds of the day; a bad entry is left out.
    inline std::vector<uint32_t> ParseRushTimes(std::string_view s)
    {
        std::vector<uint32_t> out;
        std::size_t start = 0;
        while (start <= s.size())
        {
            std::size_t end = s.find(',', start);
            if (end == std::string_view::npos)
                end = s.size();
            std::string_view item = s.substr(start, end - start);
            while (!item.empty() && item.front() == ' ')
                item.remove_prefix(1);
            while (!item.empty() && item.back() == ' ')
                item.remove_suffix(1);
            std::size_t const colon = item.find(':');
            if (colon != std::string_view::npos && colon >= 1 && colon <= 2 && item.size() == colon + 3)
            {
                uint32_t h = 0, m = 0;
                bool ok = true;
                for (std::size_t i = 0; i < item.size(); ++i)
                {
                    if (i == colon)
                        continue;
                    char const c = item[i];
                    if (c < '0' || c > '9')
                        ok = false;
                    else if (i < colon)
                        h = h * 10 + static_cast<uint32_t>(c - '0');
                    else
                        m = m * 10 + static_cast<uint32_t>(c - '0');
                }
                if (ok && h < 24 && m < 60)
                    out.push_back(h * 3600 + m * 60);
            }
            start = end + 1;
        }
        std::sort(out.begin(), out.end());
        out.erase(std::unique(out.begin(), out.end()), out.end());
        return out;
    }

    struct RushClock
    {
        uint8_t state = 0;               // 0 none, 1 soon, 2 live
        uint32_t secTo = 0;              // to the start (soon) or the end (live)
        int64_t startLocal = 0;          // the window's start (local seconds since the epoch)
    };

    // Where the local clock is against the Rush windows (each `minutes` long from a time of `times`, warned
    // `warnMinutes` before); a window that crosses midnight counts too.
    inline RushClock RushAt(int64_t localEpoch, std::vector<uint32_t> const& times, uint32_t minutes, uint32_t warnMinutes)
    {
        RushClock c;
        int64_t const dayStart = localEpoch - ((localEpoch % DaySec) + DaySec) % DaySec;
        int64_t const len = int64_t(minutes) * 60;
        int64_t const warn = int64_t(warnMinutes) * 60;
        for (int day = -1; day <= 1; ++day)
            for (uint32_t t : times)
            {
                int64_t const start = dayStart + int64_t(day) * DaySec + t;
                if (localEpoch >= start && localEpoch < start + len)
                    return { 2, static_cast<uint32_t>(start + len - localEpoch), start };
                if (localEpoch >= start - warn && localEpoch < start && c.state == 0)
                    c = { 1, static_cast<uint32_t>(start - localEpoch), start };
            }
        return c;
    }

    // One cafe's step of the Rush in the 1 s pass. A live Rush ends at its end whatever Rush.Enable says (a test Rush,
    // or Rush.Enable turned off during one); the warning and new windows need Rush.Enable. `window`: the start of the
    // window this cafe warned about or ran last.
    enum class RushMove : uint8_t { None, End, Soon, Start, Calm };
    inline RushMove RushNext(uint8_t state, bool rushOn, RushClock const& clock, int64_t window, uint64_t nowMs,
        uint64_t endMs)
    {
        if (state == 2)
            return nowMs >= endMs ? RushMove::End : RushMove::None;
        if (!rushOn)
            return state == 1 ? RushMove::Calm : RushMove::None;
        if (clock.state == 1 && window != clock.startLocal)
            return state != 1 ? RushMove::Soon : RushMove::None;
        if (clock.state == 2 && window != clock.startLocal)
            return RushMove::Start;
        if (clock.state == 0 && state == 1)
            return RushMove::Calm;
        return RushMove::None;
    }

    // BleakholdUi.Cafe.Enable 1 -> 0: no TickRush runs while the feature is off, so a live Rush would stay live and
    // end (with its rivalry line) at the first tick after a re-enable hours later. It goes silently instead, as a
    // restart forgets it: a re-enable inside its window starts it again late (RushResume), any later one finds nothing.
    inline void RushSilentReset(uint8_t& state, int64_t& window)
    {
        state = 0;
        window = 0;
    }

    // A restart inside a Rush window: resume it for the minutes left with the goal (and Rush Survivor's minimum) scaled
    // down, or skip it with fewer than 5 minutes left.
    struct RushResumePlan { bool resume = false; uint32_t minutesLeft = 0, goal = 0, survivorMin = 0; };
    inline RushResumePlan RushResume(uint32_t secLeft, uint32_t minutes, uint32_t goal, uint32_t survivorMin)
    {
        RushResumePlan p;
        p.minutesLeft = secLeft / 60;
        if (secLeft < 300 || !minutes)
            return p;
        p.resume = true;
        uint32_t const left = std::min(p.minutesLeft, minutes);
        p.goal = static_cast<uint32_t>((uint64_t(goal) * left + minutes - 1) / minutes);
        p.survivorMin = std::max<uint32_t>(1, static_cast<uint32_t>((uint64_t(survivorMin) * left + minutes - 1) / minutes));
        return p;
    }

    // =============================================================================================================
    // Shifts: what the 250 ms tick ends or warns about
    // =============================================================================================================
    // A shapeshift form hides the player (no shift, no order taken or step worked while in one), except a stance: a
    // form with SHAPESHIFT_FLAG_STANCE in SpellShapeshiftForm.dbc (UnitDefines.h), which the core itself treats as the
    // normal form (Unit::IsInDisallowedMountForm, SpellInfo::CheckShapeshift). Every warrior is always in one (Battle,
    // Defensive or Berserker Stance, forms 17-19). A form the store does not know hides, as the core's check does.
    inline constexpr uint32_t ShapeshiftFlagStance = 0x1;
    inline bool FormHides(uint8_t form, bool formKnown, uint32_t formFlags)
    {
        return form != 0 && (!formKnown || !(formFlags & ShapeshiftFlagStance));
    }

    struct ShiftFacts
    {
        bool feature = true;             // the cafe is open to this player (FeatureFor): GmOnly turned on ends the
                                         // shift of everyone else, whose every cafe intent is refused with cafe_off
        bool alive = true;
        bool inCombat = false;           // the map-thread hook ends the shift at once while On Shift is on; this
                                         // catches it once the player cancelled the aura
        bool hidden = false;             // mounted, on a vehicle or taxi, in a form (not a stance: FormHides),
                                         // stealthed or invisible
        bool afk = false;
        bool sameMap = true;
        float anchorDist = 0;            // 2D yards from the cafe anchor
        bool holdsTicket = false;
        uint64_t lastActionMs = 0;
    };
    struct ShiftLimits
    {
        uint32_t warnMs = 5000;          // Cafe.WarnSec
        float radius = 30;               // Cafe.ShiftRadius
        uint32_t leaveWarnMs = 10000;    // Cafe.LeaveWarnSec
        uint32_t idleTicketMs = 120000;  // Cafe.IdleTicketSec
        uint32_t idleMs = 300000;        // Cafe.IdleSec
    };
    struct ShiftTimers { uint64_t hiddenSinceMs = 0, outsideSinceMs = 0; };
    struct ShiftVerdict
    {
        char end = 0;                    // CafeShiftEnd letter, 0: the shift goes on
        uint32_t flags = 0;              // CafeFlagHidden, CafeFlagOutside
        std::optional<uint32_t> warnSec; // until a warning ends the shift
    };

    inline ShiftVerdict ShiftTick(ShiftFacts const& f, ShiftTimers& t, uint64_t nowMs, ShiftLimits const& l)
    {
        ShiftVerdict v;
        if (!f.feature)
        {
            v.end = 'O';
            return v;
        }
        if (!f.alive || !f.sameMap)
        {
            v.end = 'D';
            return v;
        }
        if (f.inCombat)
        {
            v.end = 'C';
            return v;
        }
        if (f.afk)
        {
            v.end = 'A';
            return v;
        }
        uint32_t const idle = f.holdsTicket ? l.idleTicketMs : l.idleMs;
        if (nowMs >= f.lastActionMs && nowMs - f.lastActionMs >= idle)
        {
            v.end = 'I';
            return v;
        }
        auto warn = [&](uint64_t& since, uint32_t ms, uint32_t flag, char reason) {
            if (!since)
                since = nowMs;
            if (nowMs - since >= ms)
            {
                v.end = reason;
                return;
            }
            v.flags |= flag;
            uint32_t const left = static_cast<uint32_t>((since + ms - nowMs + 999) / 1000);
            v.warnSec = v.warnSec ? std::min(*v.warnSec, left) : left;
        };
        if (f.hidden)
            warn(t.hiddenSinceMs, l.warnMs, CafeFlagHidden, 'M');
        else
            t.hiddenSinceMs = 0;
        if (v.end)
            return v;
        if (f.anchorDist > l.radius)
            warn(t.outsideSinceMs, l.leaveWarnMs, CafeFlagOutside, 'W');
        else
            t.outsideSinceMs = 0;
        return v;
    }

    // =============================================================================================================
    // Placement: the cafe frame (F along the anchor's facing, L to its left, U up)
    // =============================================================================================================
    struct Pose { float x = 0, y = 0, z = 0, o = 0; };

    inline float Norm(float o)
    {
        float r = std::fmod(o, TwoPi);
        if (r < 0)
            r += TwoPi;
        return r >= TwoPi ? 0.0f : r;
    }

    // An angle in (-pi, pi].
    inline float Signed(float o)
    {
        float r = Norm(o);
        return r > Pi ? r - TwoPi : r;
    }

    inline Pose ToWorld(Pose const& a, float f, float l, float u, float turn)
    {
        float const c = std::cos(a.o);
        float const s = std::sin(a.o);
        return { a.x + f * c - l * s, a.y + f * s + l * c, a.z + u, Norm(a.o + turn) };
    }

    struct Local { float f = 0, l = 0, u = 0, turn = 0; };

    // The inverse of ToWorld (".cafe here" keeps f/l/u/turn in step with the world position).
    inline Local ToLocal(Pose const& a, Pose const& p)
    {
        float const c = std::cos(a.o);
        float const s = std::sin(a.o);
        float const dx = p.x - a.x;
        float const dy = p.y - a.y;
        return { dx * c + dy * s, -dx * s + dy * c, p.z - a.z, Signed(p.o - a.o) };
    }

    // The core's chair slot positions (GameObject::Use, GAMEOBJECT_TYPE_CHAIR): slot i of n sits size x i - size x (n -
    // 1) / 2 along the chair's orientation + pi/2.
    inline Pose ChairSlot(Pose const& chair, float size, uint32_t slot, uint32_t slots)
    {
        uint32_t const n = slots ? slots : 1;
        float const rel = size * static_cast<float>(slot) - size * static_cast<float>(n - 1) / 2.0f;
        float const ortho = chair.o + Pi * 0.5f;
        return { chair.x + rel * std::cos(ortho), chair.y + rel * std::sin(ortho), chair.z, chair.o };
    }

    // The ground snap of a piece: the ground when it is valid, within 2.5 yd of the height asked for and seen from the
    // anchor; else the height asked for. `askedZ` is the anchor's height plus the piece's u: u is 0 for the layout's
    // pieces (.cafe build) and after .cafe snap of one piece, the GM's own height after .cafe here or .cafe add, so a
    // piece out of the anchor's sight (the door marker) stands where the GM stood, not at the anchor's height.
    inline constexpr float SnapMaxDz = 2.5f;
    inline float SnapZ(bool groundValid, float ground, float askedZ, bool los)
    {
        return groundValid && los && std::fabs(ground - askedZ) <= SnapMaxDz ? ground : askedZ;
    }

    // The floor under a piece (its work spots stand on it): a snap piece stands on it (SnapZ); any other piece is
    // raised by u above it.
    inline float PieceFloorZ(bool snap, float z, float u) { return snap ? z : z - std::max(0.0f, u); }

    // A station's work spot: `fwd` and `side` yards in the piece's own frame (+X its front), on the floor.
    inline Pose WorkSpot(Pose const& piece, float floorZ, float fwd, float side)
    {
        Pose p = ToWorld(piece, fwd, side, 0, 0);
        p.z = floorZ;
        return p;
    }

    // =============================================================================================================
    // Stations: where a barista is (section 3.5)
    // =============================================================================================================
    struct SpotRef
    {
        char station = 0;
        uint8_t spot = 0;                // 0 or 1
        float x = 0, y = 0, z = 0;
        float objX = 0, objY = 0;        // the station object the barista must face
    };

    struct StationHit
    {
        char station = 0;                // at this station (0: none)
        uint8_t spot = 0;                // which of its spots
        char nearStation = 0;            // the nearest spot's station (or the one faced away from)
        float nearDist = 0;              // 2D yards to it
        bool facingHint = false;         // at nearStation's spot but not facing it
    };

    // The core's Position::HasInArc for a point: the angle to it from the facing, in [-arc/2, arc/2].
    inline bool HasInArc(float arcRad, float px, float py, float po, float tx, float ty)
    {
        if (px == tx && py == ty)
            return true;
        float const arc = arcRad >= TwoPi ? TwoPi : Norm(arcRad);
        float const angle = Signed(std::atan2(ty - py, tx - px) - po);
        return angle >= -arc / 2.0f && angle <= arc / 2.0f;
    }

    inline StationHit StationAt(float px, float py, float pz, float po, std::vector<SpotRef> const& spots, float radius,
        float arcDeg, float maxDz = 2.0f)
    {
        StationHit h;
        float best = -1, bestHint = -1, nearest = -1;
        char hint = 0;
        float const arc = arcDeg >= 360.0f ? TwoPi : arcDeg * Pi / 180.0f;
        for (SpotRef const& s : spots)
        {
            float const d = std::hypot(s.x - px, s.y - py);
            if (nearest < 0 || d < nearest)
            {
                nearest = d;
                h.nearStation = s.station;
                h.nearDist = d;
            }
            if (d > radius || std::fabs(s.z - pz) > maxDz)
                continue;
            if (arcDeg >= 360.0f || HasInArc(arc, px, py, po, s.objX, s.objY))
            {
                if (best < 0 || d < best)
                {
                    best = d;
                    h.station = s.station;
                    h.spot = s.spot;
                }
            }
            else if (bestHint < 0 || d < bestHint)
            {
                bestHint = d;
                hint = s.station;
            }
        }
        if (!h.station && hint)
        {
            h.facingHint = true;
            h.nearStation = hint;
            h.nearDist = bestHint;
        }
        return h;
    }

    // CAFST nearDm: decimetres, capped.
    inline uint32_t NearDm(float yards)
    {
        if (!(yards > 0))
            return 0;
        return static_cast<uint32_t>(std::min(std::lround(yards * 10.0f), long(MaxCafeNearDm)));
    }

    // =============================================================================================================
    // Customers: the drink an NPC orders and what it says
    // =============================================================================================================
    // Section 2.7: a group member orders its favourite; otherwise 60% a favourite at least one barista on shift has unlocked,
    // else any recipe one of them has unlocked, and with nobody on shift a level-1 recipe. `maxLevel` is the highest
    // barista level on shift (0: nobody); `roll` 0..99 and `pick` are random numbers. The archetype number n.
    inline uint8_t PickRecipeN(D::Persona const& p, uint8_t memberIndex, uint8_t maxLevel, uint32_t roll, uint32_t pick)
    {
        uint8_t const cafe = p.cafeId;
        auto recipe = [&](uint8_t n) { return D::FindRecipe(D::RecipeId(cafe, n)); };
        if (p.kind == D::PersonaKind::Group && p.favCount)
            return p.fav[memberIndex % p.favCount];
        std::vector<uint8_t> pool;
        if (maxLevel == 0)
        {
            for (D::Recipe const& r : D::Recipes)
                if (r.cafeId == cafe && r.unlock <= 1)
                    pool.push_back(r.n);
        }
        else
        {
            if (roll < 60)
                for (uint8_t i = 0; i < p.favCount; ++i)
                    if (D::Recipe const* r = recipe(p.fav[i]); r && r->unlock <= maxLevel)
                        pool.push_back(r->n);
            if (pool.empty())
                for (D::Recipe const& r : D::Recipes)
                    if (r.cafeId == cafe && r.unlock <= maxLevel)
                        pool.push_back(r.n);
        }
        return pool.empty() ? 1 : pool[pick % pool.size()];
    }

    // A line of a pool (A, H or K) and kind (O order, T thanks, C complaint); `pick` is a random number.
    inline std::string_view PoolLine(char pool, char kind, uint32_t pick)
    {
        uint32_t count = 0;
        for (D::PoolLine const& l : D::PoolLines)
            if (l.pool == pool && l.kind == kind)
                ++count;
        if (!count)
            return {};
        uint32_t want = pick % count;
        for (D::PoolLine const& l : D::PoolLines)
            if (l.pool == pool && l.kind == kind && want-- == 0)
                return l.text;
        return {};
    }

    // What a customer says when its order is taken: a named persona's own line only for its first favourite, the
    // first member of a group its group's line; every other order a pool line with the drink's name.
    inline std::string OrderLine(D::Persona const& p, uint8_t n, uint8_t memberIndex, std::string_view drink,
        char adultPool, uint32_t pick)
    {
        bool const own = !p.order.empty() &&
            ((p.kind == D::PersonaKind::Named && p.favCount && p.fav[0] == n) ||
             (p.kind == D::PersonaKind::Group && memberIndex == 0));
        if (own)
            return std::string(p.order);
        char const pool = p.pool != '-' ? p.pool : (p.child ? 'K' : adultPool);
        return Fill(PoolLine(pool, 'O', pick), "{drink}", drink);
    }

    inline std::string ThanksLine(D::Persona const& p, char adultPool, uint32_t pick)
    {
        if (!p.thanks.empty())
            return std::string(p.thanks);
        return std::string(PoolLine(p.pool != '-' ? p.pool : (p.child ? 'K' : adultPool), 'T', pick));
    }

    inline std::string ComplaintLine(D::Persona const& p, char adultPool, uint32_t pick)
    {
        if (!p.complaint.empty())
            return std::string(p.complaint);
        return std::string(PoolLine(p.pool != '-' ? p.pool : (p.child ? 'K' : adultPool), 'C', pick));
    }

    // A staff line by key ("idle" has several; `pick` chooses), empty when the staff member has none.
    inline std::string_view StaffLine(uint32_t entry, std::string_view key, uint32_t pick, bool* yell = nullptr)
    {
        uint32_t count = 0;
        for (D::StaffLine const& l : D::StaffLines)
            if (l.entry == entry && l.key == key)
                ++count;
        if (!count)
            return {};
        uint32_t want = pick % count;
        for (D::StaffLine const& l : D::StaffLines)
            if (l.entry == entry && l.key == key && want-- == 0)
            {
                if (yell)
                    *yell = l.yell;
                return l.text;
            }
        return {};
    }

    // The line of the house worker who starts a player's drink (the owner, or the head barista while she is busy):
    // its own "takeover" line for a takeover when it has one, else its own "houseOrder" line.
    inline std::string_view HouseLineKey(uint32_t workerEntry, bool takeover)
    {
        return takeover && !StaffLine(workerEntry, "takeover", 0).empty() ? "takeover" : "houseOrder";
    }

    // The staff who shout during the Rush (their "rush" line), in staff order, and when each says it: a few seconds
    // after the owner's yell, one after the other.
    inline std::vector<D::StaffMember const*> RushShouters(uint8_t cafeId)
    {
        std::vector<D::StaffMember const*> out;
        for (D::StaffMember const& s : D::Staff)
            if (s.cafeId == cafeId && !StaffLine(s.entry, "rush", 0).empty())
                out.push_back(&s);
        return out;
    }
    inline constexpr uint32_t RushShoutFirstMs = 4000, RushShoutGapMs = 3500;
    inline uint32_t RushShoutDelayMs(std::size_t i) { return RushShoutFirstMs + RushShoutGapMs * static_cast<uint32_t>(i); }

    // =============================================================================================================
    // Bot hints
    // =============================================================================================================
    inline uint32_t StdDevMs(std::vector<int32_t> const& v)
    {
        if (v.size() < 2)
            return 0;
        double mean = 0;
        for (int32_t x : v)
            mean += x;
        mean /= static_cast<double>(v.size());
        double sum = 0;
        for (int32_t x : v)
            sum += (x - mean) * (x - mean);
        return static_cast<uint32_t>(std::lround(std::sqrt(sum / static_cast<double>(v.size()))));
    }

    // A shift (with the day's drinks) worth a GM's look: many drinks, almost all Perfect, releases too even.
    inline bool BotFlag(uint32_t drinks, uint32_t perfects, std::vector<int32_t> const& offsets, uint32_t minDrinks,
        uint32_t perfectPermille, uint32_t sdMs)
    {
        return drinks >= minDrinks && drinks > 0 && PerfectPermille(perfects, drinks) >= perfectPermille &&
            offsets.size() >= 2 && StdDevMs(offsets) < sdMs;
    }

    // =============================================================================================================
    // The tables (section 3.10): the text of data/sql/db-world/03_bleakhold_cafe_tables.sql and
    // data/sql/db-characters/01_bleakhold_cafe_characters.sql, run again at startup (CREATE TABLE IF NOT EXISTS) so a
    // realm that missed the module SQL still works; bh_cafe checks both files hold these statements.
    // =============================================================================================================
    inline constexpr std::array<std::string_view, 2> WorldTablesSql = { {
        "CREATE TABLE IF NOT EXISTS `bleakhold_cafe` (\n"
        "  `id`         TINYINT UNSIGNED  NOT NULL COMMENT '1 The Lion''s Roast (Stormwind), 2 The Grinding Tusk (Orgrimmar)',\n"
        "  `map`        SMALLINT UNSIGNED NOT NULL,\n"
        "  `zone`       SMALLINT UNSIGNED NOT NULL,\n"
        "  `x` FLOAT NOT NULL, `y` FLOAT NOT NULL, `z` FLOAT NOT NULL, `o` FLOAT NOT NULL COMMENT 'anchor: where a customer orders, facing the counter',\n"
        "  `layout_ver` SMALLINT UNSIGNED NOT NULL DEFAULT 1,\n"
        "  `enabled`    TINYINT UNSIGNED  NOT NULL DEFAULT 0,\n"
        "  `placed_by`  VARCHAR(30)       NOT NULL DEFAULT '' COMMENT 'the GM''s name (two names fit: up to 30 characters)',\n"
        "  `placed_at`  INT UNSIGNED      NOT NULL DEFAULT 0,\n"
        "  PRIMARY KEY (`id`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS `bleakhold_cafe_piece` (\n"
        "  `cafe_id` TINYINT UNSIGNED  NOT NULL,\n"
        "  `slot`    SMALLINT UNSIGNED NOT NULL COMMENT 'layout slot; 200+ for pieces added with .cafe add',\n"
        "  `role`    VARCHAR(24)       NOT NULL COMMENT 'station_E, counter, backbar, chair_1, table_1, queue_3, door, path_1, staff_owner, decor, ...',\n"
        "  `entry`   INT UNSIGNED      NOT NULL DEFAULT 0 COMMENT 'gameobject or creature entry (new-art entry; the stand-in is entry+30); 0 for markers',\n"
        "  `link`    SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'chair or parasol: its table slot; on-counter piece: its counter or back bar slot',\n"
        "  `f` FLOAT NOT NULL, `l` FLOAT NOT NULL, `u` FLOAT NOT NULL, `turn` FLOAT NOT NULL COMMENT 'relative to the anchor: forward, left, up (yards), turn (radians)',\n"
        "  `x` FLOAT NOT NULL, `y` FLOAT NOT NULL, `z` FLOAT NOT NULL, `o` FLOAT NOT NULL COMMENT 'world position, kept in step with f/l/u/turn',\n"
        "  `snap`    TINYINT UNSIGNED  NOT NULL DEFAULT 1,\n"
        "  `enabled` TINYINT UNSIGNED  NOT NULL DEFAULT 1,\n"
        "  PRIMARY KEY (`cafe_id`, `slot`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    } };

    inline constexpr std::array<std::string_view, 6> CharacterTablesSql = { {
        "CREATE TABLE IF NOT EXISTS `bleakhold_cafe_barista` (\n"
        "  `guid` INT UNSIGNED NOT NULL, `account` INT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `level` TINYINT UNSIGNED NOT NULL DEFAULT 1, `xp` INT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `drinks` INT UNSIGNED NOT NULL DEFAULT 0, `perfects` INT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `memory_drinks` INT UNSIGNED NOT NULL DEFAULT 0, `best_streak` SMALLINT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `fastest_ms` INT UNSIGNED NOT NULL DEFAULT 0, `weekly_wins` SMALLINT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `flags` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '1 apprentice apron, 2 master apron, 4 golden apron, 8 title barista, 16 title legend, 32 tutorial done, 64/128 shot/steam lines heard',\n"
        "  `crown_until` INT UNSIGNED NOT NULL DEFAULT 0, `staff_day` INT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `shift_accum_sec` INT UNSIGNED NOT NULL DEFAULT 0, `off_shift_since` INT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  PRIMARY KEY (`guid`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS `bleakhold_cafe_day` (\n"
        "  `day_id` INT UNSIGNED NOT NULL, `guid` INT UNSIGNED NOT NULL, `cafe_id` TINYINT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `xp_full` SMALLINT UNSIGNED NOT NULL DEFAULT 0, `xp_half` SMALLINT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `tips` INT UNSIGNED NOT NULL DEFAULT 0, `points` SMALLINT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `drinks` SMALLINT UNSIGNED NOT NULL DEFAULT 0, `perfects` SMALLINT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `orders_placed` TINYINT UNSIGNED NOT NULL DEFAULT 0, `rush_served` SMALLINT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  PRIMARY KEY (`day_id`, `guid`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS `bleakhold_cafe_week` (\n"
        "  `week_id` INT UNSIGNED NOT NULL, `guid` INT UNSIGNED NOT NULL, `cafe_id` TINYINT UNSIGNED NOT NULL,\n"
        "  `name` VARCHAR(30) NOT NULL DEFAULT '' COMMENT 'two names fit (mod-two-names: up to 30 characters)', `class` TINYINT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `points` INT UNSIGNED NOT NULL DEFAULT 0, `drinks` INT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `perfects` INT UNSIGNED NOT NULL DEFAULT 0, `days_mask` TINYINT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `score_at` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'when points last rose (tie-break)',\n"
        "  PRIMARY KEY (`week_id`, `guid`), KEY `idx_board` (`week_id`, `cafe_id`, `points`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS `bleakhold_cafe_payout` (\n"
        "  `week_id` INT UNSIGNED NOT NULL, `cafe_id` TINYINT UNSIGNED NOT NULL, `paid_at` INT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  PRIMARY KEY (`week_id`, `cafe_id`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS `bleakhold_cafe_order` (\n"
        "  `id` INT UNSIGNED NOT NULL COMMENT 'module counter, seeded with MAX(id)+1 at startup', `cafe_id` TINYINT UNSIGNED NOT NULL,\n"
        "  `customer_guid` INT UNSIGNED NOT NULL, `customer_account` INT UNSIGNED NOT NULL,\n"
        "  `recipe_id` SMALLINT UNSIGNED NOT NULL, `price` INT UNSIGNED NOT NULL, `tip` INT UNSIGNED NOT NULL,\n"
        "  `state` CHAR(1) NOT NULL DEFAULT 'W' COMMENT 'W T H R; written in the same transaction as every money move', `barista_guid` INT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `created` INT UNSIGNED NOT NULL, `ready_until` INT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `share_pct` TINYINT UNSIGNED NOT NULL DEFAULT 60 COMMENT 'Order.BaristaSharePct when it was paid: every split of this order uses it',\n"
        "  PRIMARY KEY (`id`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
        "CREATE TABLE IF NOT EXISTS `bleakhold_cafe_flag` (\n"
        "  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT, `guid` INT UNSIGNED NOT NULL, `at` INT UNSIGNED NOT NULL,\n"
        "  `drinks` INT UNSIGNED NOT NULL, `perfect_permille` SMALLINT UNSIGNED NOT NULL, `release_sd_ms` SMALLINT UNSIGNED NOT NULL,\n"
        "  PRIMARY KEY (`id`), KEY `idx_guid` (`guid`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    } };

    // A column added to a table after its first release: a table made by an earlier copy of the module SQL gets it
    // at startup (CREATE TABLE IF NOT EXISTS leaves an old table as it is). `alter` holds the CREATE's column text.
    struct AddedColumn { std::string_view table, column, alter; };
    inline constexpr std::array<AddedColumn, 1> CharacterAddedColumns = { {
        { "bleakhold_cafe_order", "share_pct",
          "ALTER TABLE `bleakhold_cafe_order` ADD COLUMN `share_pct` TINYINT UNSIGNED NOT NULL DEFAULT 60 COMMENT "
          "'Order.BaristaSharePct when it was paid: every split of this order uses it' AFTER `ready_until`" },
    } };

    // A name column made wider after its first release: this realm's characters can have two-part names of up to 30
    // characters (mod-two-names widens characters.name to VARCHAR(30)), and a strict-mode MySQL refuses a longer value
    // outright (ERROR 1406), so the row would never be written. A table made by an earlier copy of the module SQL is
    // widened at startup when its column holds fewer than `chars` characters. `modify` holds the CREATE's column text.
    struct WidenedColumn { std::string_view table, column; uint32_t chars; std::string_view modify; };
    inline constexpr uint32_t NameColumnChars = 30;
    inline constexpr std::array<WidenedColumn, 1> WorldWidenedColumns = { {
        { "bleakhold_cafe", "placed_by", NameColumnChars,
          "ALTER TABLE `bleakhold_cafe` MODIFY COLUMN `placed_by` VARCHAR(30) NOT NULL DEFAULT '' COMMENT "
          "'the GM''s name (two names fit: up to 30 characters)'" },
    } };
    inline constexpr std::array<WidenedColumn, 1> CharacterWidenedColumns = { {
        { "bleakhold_cafe_week", "name", NameColumnChars,
          "ALTER TABLE `bleakhold_cafe_week` MODIFY COLUMN `name` VARCHAR(30) NOT NULL DEFAULT '' COMMENT "
          "'two names fit (mod-two-names: up to 30 characters)'" },
    } };

    // A name as the name columns hold it: whole UTF-8 characters, at most `chars` of them. Never a byte cut, which can
    // leave half a character that MySQL refuses (ERROR 1366), and so the whole row.
    inline std::string NameForColumn(std::string_view name, std::size_t chars = NameColumnChars)
    {
        std::size_t i = 0;
        for (std::size_t n = 0; i < name.size() && n < chars; ++n)
        {
            ++i;
            while (i < name.size() && (static_cast<unsigned char>(name[i]) & 0xC0) == 0x80)
                ++i;
        }
        return std::string(name.substr(0, i));
    }

    // =============================================================================================================
    // DEF H, G, F and U (section 21) from the catalogue
    // =============================================================================================================
    inline void FillDefinitions(Definitions& d)
    {
        for (D::Cafe const& c : D::Cafes)
        {
            CafeDef h;
            h.id = c.id;
            h.name = std::string(c.name);
            h.cityKey = std::string(c.cityKey);
            h.team = c.team;
            h.zoneId = c.zone;
            h.mapId = c.map;
            if (D::StaffMember const* owner = D::FindStaff(c.owner))
                h.ownerName = std::string(owner->name);
            h.tagline = std::string(c.tagline);
            h.colorHex = std::string(c.trim);
            d.cafes.push_back(std::move(h));
        }
        for (D::Action const& a : D::Actions)
        {
            CafeActionDef g;
            g.id = a.id;
            g.station = a.station;
            g.key = a.key;
            g.kind = a.kind;
            g.durMs = a.durMs;
            if (a.kind == 'H')
            {
                g.goldLoPermille = a.goldLo;
                g.goldHiPermille = a.goldHi;
            }
            g.name = std::string(a.name);
            g.hordeName = std::string(a.hordeName);
            g.spellId = a.spell;
            d.cafeActions.push_back(std::move(g));
        }
        for (D::Recipe const& r : D::Recipes)
        {
            CafeRecipeDef f;
            f.id = r.id;
            f.cafeId = r.cafeId;
            f.archetype = r.n;
            f.family = r.family;
            f.tier = r.tier;
            f.unlockLevel = r.unlock;
            if (D::Tier const* t = TierOf(r.tier))
            {
                f.price80Copper = t->price80;
                f.buffMin = t->buffMin;
            }
            for (uint8_t i = 0; i < r.stepCount; ++i)
                f.steps.push_back(r.steps[i]);
            f.name = std::string(r.name);
            f.text = std::string(r.text);
            d.cafeRecipes.push_back(std::move(f));
        }
        for (D::Level const& l : D::Levels)
            d.cafeLevels.push_back({ l.level, l.xp, std::string(l.text) });
    }
}

#endif
