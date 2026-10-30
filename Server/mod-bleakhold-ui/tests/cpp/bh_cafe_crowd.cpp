// mod-bleakhold-ui tests: the cafe's NPC crowd (spec 3.7, 3.16.2) against src/BleakholdCafeCrowdRules.h and the
// generated src/BleakholdCafeData.h, with no AzerothCore: a fake world walks the creatures in straight lines at their
// speed, a fake Cafe answers the crowd's hooks. Every check is deterministic (seeded).
//
//   bh_cafe_crowd [repo]      (the repo argument of run_tests.sh is accepted and not needed)
// SPDX-License-Identifier: GPL-2.0-or-later

#include "bh_check.h"

#include "../../src/BleakholdCafeCrowdRules.h"

#include <cmath>
#include <functional>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using namespace Bleakhold::CrowdRules;

namespace
{
    // A rotated, raised anchor, so nothing passes by being axis-aligned at the origin.
    Pose const Anchor{ 1630.25f, -4420.5f, 18.75f, 0.7f };
    Pose const Straight{ 0.0f, 0.0f, 0.0f, 0.0f };

    std::string Num(float v)
    {
        std::ostringstream s;
        s << v;
        return s.str();
    }

    // A point in the cafe's frame (spec 3.12.3's F, L).
    std::pair<float, float> FL(Pose const& anchor, Vec3 p)
    {
        return ToFrame(anchor, p);
    }

    bool Near(float a, float b, float eps = 0.01f)
    {
        return std::fabs(a - b) <= eps;
    }

    // ---- an independent leg check (sampled, not the header's segment maths) ----

    float BoxDistance(Vec3 p, Box const& b)
    {
        double const c = std::cos(double(b.o)), s = std::sin(double(b.o));
        double const dx = double(p.x) - b.x, dy = double(p.y) - b.y;
        double const u = dx * c + dy * s, v = -dx * s + dy * c;
        double const eu = std::max(std::fabs(u) - b.halfD, 0.0), ev = std::max(std::fabs(v) - b.halfW, 0.0);
        return float(std::sqrt(eu * eu + ev * ev));
    }

    bool Inside(Vec3 p, Box const& b)
    {
        double const c = std::cos(double(b.o)), s = std::sin(double(b.o));
        double const dx = double(p.x) - b.x, dy = double(p.y) - b.y;
        double const u = dx * c + dy * s, v = -dx * s + dy * c;
        return std::fabs(u) < b.halfD && std::fabs(v) < b.halfW;
    }

    struct LegRules
    {
        std::vector<Box> boxes;
        std::vector<Vec3> nodes;     // graph nodes: segments between two of them are held to the full clearance
        float clearance = AisleClearance;
        std::vector<std::pair<Vec3, int>> own;   // an end point and the footprint it belongs to (approach points)
        bool doorEdge = false;       // nodes[0] (the door) to nodes[1] (path_1) is the GM's: not checked
    };

    LegRules AisleRules(Geometry const& g)
    {
        LegRules r;
        r.boxes = g.boxes;
        r.nodes.push_back(g.door.At());
        r.nodes.insert(r.nodes.end(), g.nodes.begin(), g.nodes.end());
        r.doorEdge = true;
        for (Chair const& c : g.chairs)
            r.own.push_back({ c.approach, c.box });
        for (Keg const& k : g.kegs)
            r.own.push_back({ k.approach, k.box });
        return r;
    }

    LegRules WorkRules(Geometry const& g)
    {
        LegRules r;
        r.boxes = g.boxes;
        r.clearance = WorkClearance;
        for (Station const& s : g.stations)
        {
            r.nodes.push_back(s.spots[0]);
            r.nodes.push_back(s.spots[1]);
            r.nodes.push_back(s.behind);
        }
        for (StaffHome const& h : g.staff)
            if (h.role == "staff_owner" || h.role == "staff_head")
                r.nodes.push_back(h.home.At());
        return r;
    }

    bool IsNode(LegRules const& r, Vec3 p)
    {
        for (Vec3 const& n : r.nodes)
            if (Dist2d(n, p) < 1e-3f)
                return true;
        return false;
    }

    // Spec 3.7.3: a segment keeps the clearance from every footprint; one with an end that is not a graph node may
    // pass closer to the footprints that end stands next to (within the clearance, or its own: a chair by its approach
    // point), but never enters one unless the end stands inside it (a seat in its chair). Empty: fine.
    std::string LegProblem(std::vector<Vec3> const& pts, LegRules const& r)
    {
        for (std::size_t i = 1; i < pts.size(); ++i)
        {
            Vec3 const a = pts[i - 1], b = pts[i];
            if (r.doorEdge && r.nodes.size() > 1 &&
                ((Dist2d(a, r.nodes[0]) < 1e-3f && Dist2d(b, r.nodes[1]) < 1e-3f) ||
                 (Dist2d(b, r.nodes[0]) < 1e-3f && Dist2d(a, r.nodes[1]) < 1e-3f)))
                continue;
            float const len = Dist2d(a, b);
            int const samples = std::max(2, int(len / 0.01f));
            for (std::size_t k = 0; k < r.boxes.size(); ++k)
            {
                Box const& box = r.boxes[k];
                auto ownOf = [&](Vec3 p) {
                    if (IsNode(r, p))
                        return false;
                    if (BoxDistance(p, box) < r.clearance)
                        return true;
                    for (auto const& [q, bi] : r.own)
                        if (bi == int(k) && Dist2d(q, p) < 1e-3f)
                            return true;
                    return false;
                };
                bool const relaxA = ownOf(a), relaxB = ownOf(b);
                bool const inEnd = (relaxA && Inside(a, box)) || (relaxB && Inside(b, box));
                float minD = 1e9f;
                bool entered = false;
                for (int s = 0; s <= samples; ++s)
                {
                    float const t = float(s) / float(samples);
                    Vec3 const p{ a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, 0 };
                    minD = std::min(minD, BoxDistance(p, box));
                    if (Inside(p, box))
                        entered = true;
                }
                if (minD >= r.clearance - 0.02f)
                    continue;
                if (!relaxA && !relaxB)
                    return "segment " + std::to_string(i) + " passes footprint " + std::to_string(k) + " at " +
                           Num(minD) + " yd";
                if (entered && !inEnd)
                    return "segment " + std::to_string(i) + " enters footprint " + std::to_string(k);
            }
        }
        return "";
    }

    // No segment within the clearance of an occupied queue slot.
    std::string SlotProblem(std::vector<Vec3> const& pts, std::vector<Vec3> const& occupied, float clearance)
    {
        for (std::size_t i = 1; i < pts.size(); ++i)
            for (Vec3 const& q : occupied)
                if (PointSegDist(q, pts[i - 1], pts[i]) < clearance - 1e-3f)
                    return "segment " + std::to_string(i) + " passes an occupied slot at " +
                           Num(PointSegDist(q, pts[i - 1], pts[i])) + " yd";
        return "";
    }

    // ---- a fake world ----

    class FakeWorld : public World
    {
    public:
        struct Unit
        {
            uint32_t entry = 0;
            Pose pose;
            uint32_t display = 0;
            std::vector<Vec3> path;
            float speed = WalkYdPerSec;
            bool alive = true;
            bool frozen = false;     // ignores walks (the stuck tests)
            bool customer = false;
            uint8_t stand = 0;
            uint32_t hold = 0;
            uint32_t emoteState = 0;
        };

        struct Go
        {
            uint32_t entry;
            Pose at;
            uint32_t lifetimeSec;
        };

        struct WalkRec
        {
            uint64_t guid;
            std::vector<Vec3> pts;   // from where it stood
            bool run;
        };

        std::map<uint64_t, Unit> units;
        std::map<uint64_t, Go> gos;
        std::map<uint64_t, uint64_t> staff;      // spawn id -> guid
        std::map<uint64_t, bool> locked;         // chair spawn id -> GO_FLAG_NOT_SELECTABLE
        std::vector<PlayerNear> players;
        std::vector<WalkRec> walks;
        std::vector<std::pair<uint64_t, std::string>> says;
        std::vector<std::pair<uint64_t, uint32_t>> emotes, casts, finished, states, stands, holds;
        std::vector<uint64_t> teleports, despawned, removedGos;
        std::function<void(WalkRec const&)> onWalk;
        uint64_t next = 0x1000;
        bool failSummon = false;

        uint64_t Summon(uint32_t entry, Pose const& at, uint32_t display) override
        {
            if (failSummon)
                return 0;
            uint64_t const g = ++next;
            Unit u;
            u.entry = entry;
            u.pose = at;
            u.display = display;
            u.customer = true;
            units[g] = u;
            return g;
        }

        bool Alive(uint64_t g) override
        {
            auto it = units.find(g);
            return it != units.end() && it->second.alive;
        }

        bool Where(uint64_t g, Pose& out) override
        {
            if (!Alive(g))
                return false;
            out = units[g].pose;
            return true;
        }

        bool Moving(uint64_t g) override { return Alive(g) && !units[g].path.empty(); }

        void Walk(uint64_t g, std::vector<Vec3> const& pts, bool run) override
        {
            if (!Alive(g))
                return;
            Unit& u = units[g];
            WalkRec r{ g, { u.pose.At() }, run };
            r.pts.insert(r.pts.end(), pts.begin(), pts.end());
            if (onWalk)
                onWalk(r);
            walks.push_back(r);
            u.emoteState = 0;
            if (u.frozen)
                return;
            u.path = pts;
            u.speed = run ? RunYdPerSec : WalkYdPerSec;
        }

        void Stop(uint64_t g) override
        {
            if (Alive(g))
                units[g].path.clear();
        }

        void Teleport(uint64_t g, Pose const& to) override
        {
            if (!Alive(g))
                return;
            units[g].pose = to;
            units[g].path.clear();
            teleports.push_back(g);
        }

        void Face(uint64_t g, float o) override
        {
            if (Alive(g))
                units[g].pose.o = o;
        }

        void Despawn(uint64_t g) override
        {
            if (!Alive(g))
                return;
            units[g].alive = false;
            despawned.push_back(g);
        }

        void Say(uint64_t g, std::string_view text, bool) override { says.push_back({ g, std::string(text) }); }
        void Emote(uint64_t g, uint32_t e) override { emotes.push_back({ g, e }); }

        void EmoteState(uint64_t g, uint32_t s) override
        {
            states.push_back({ g, s });
            if (Alive(g))
                units[g].emoteState = s;
        }

        void Stand(uint64_t g, uint8_t s) override
        {
            stands.push_back({ g, s });
            if (Alive(g))
                units[g].stand = s;
        }

        void Hold(uint64_t g, uint32_t item) override
        {
            holds.push_back({ g, item });
            if (Alive(g))
                units[g].hold = item;
        }

        void Cast(uint64_t g, uint32_t spell) override { casts.push_back({ g, spell }); }
        void FinishChannel(uint64_t g, uint32_t spell) override { finished.push_back({ g, spell }); }

        uint64_t Staff(uint64_t spawnId) override
        {
            auto it = staff.find(spawnId);
            return it != staff.end() && Alive(it->second) ? it->second : 0;
        }

        uint64_t PlaceGo(uint32_t entry, Pose const& at, uint32_t lifetimeSec) override
        {
            uint64_t const g = ++next;
            gos[g] = { entry, at, lifetimeSec };
            return g;
        }

        void RemoveGo(uint64_t g) override
        {
            if (gos.erase(g))
                removedGos.push_back(g);
        }

        void LockChair(uint64_t spawnId, bool l) override { locked[spawnId] = l; }

        void Players(Vec3 centre, float radius, std::vector<PlayerNear>& out) override
        {
            for (PlayerNear const& p : players)
                if (Dist2d(p.pos, centre) <= radius)
                    out.push_back(p);
        }

        void Advance(uint32_t ms)
        {
            for (auto& [g, u] : units)
            {
                if (!u.alive)
                    continue;
                float left = u.speed * float(ms) / 1000.0f;
                while (left > 0 && !u.path.empty())
                {
                    Vec3 const t = u.path.front();
                    float const d = Dist2d(u.pose.At(), t);
                    if (d > 1e-4f)
                        u.pose.o = AngleTo(u.pose.At(), t);
                    if (d <= left)
                    {
                        u.pose.x = t.x;
                        u.pose.y = t.y;
                        u.pose.z = t.z;
                        left -= d;
                        u.path.erase(u.path.begin());
                    }
                    else
                    {
                        u.pose.x += (t.x - u.pose.x) / d * left;
                        u.pose.y += (t.y - u.pose.y) / d * left;
                        left = 0;
                    }
                }
            }
        }

        std::size_t SaysOf(uint64_t g, std::string const& text) const
        {
            std::size_t n = 0;
            for (auto const& [who, t] : says)
                if (who == g && t == text)
                    ++n;
            return n;
        }

        std::size_t EmotesOf(uint64_t g, uint32_t e) const
        {
            std::size_t n = 0;
            for (auto const& [who, x] : emotes)
                if (who == g && x == e)
                    ++n;
            return n;
        }
    };

    // ---- a fake Cafe: orders 'W' in a queue, then whatever the test does with them ----

    class FakeCafe : public Hooks
    {
    public:
        struct Order
        {
            uint32_t id;
            uint64_t guid;
            uint8_t persona;
            uint32_t group;
            char state;              // W waiting, T taken, H house, S served, X failed
            uint32_t since;
        };

        struct StepRec
        {
            uint32_t order;
            uint8_t step;
            uint8_t action;
            uint32_t dur;
            uint64_t worker;
            uint32_t at;
        };

        std::vector<Order> orders;
        std::vector<uint32_t> queue;             // 'W' order ids, in Cafe's order
        uint32_t nextId = 500;
        bool refuse = false;
        std::vector<uint32_t> gone, done, cups, delivered;
        std::vector<StepRec> steps;
        std::function<void(Order&)> onArrived;
        std::function<void(uint32_t)> onDone;
        uint32_t const* clock = nullptr;

        uint32_t NpcArrived(uint8_t persona, uint64_t guid, uint32_t group) override
        {
            if (refuse)
                return 0;
            orders.push_back({ nextId++, guid, persona, group, 'W', clock ? *clock : 0 });
            queue.push_back(orders.back().id);
            if (onArrived)
                onArrived(orders.back());
            return orders.back().id;
        }

        void NpcGone(uint32_t id) override
        {
            gone.push_back(id);
            Unqueue(id);
        }

        void HouseStepStarted(uint32_t order, uint8_t step, uint8_t action, uint32_t dur, uint64_t worker) override
        {
            steps.push_back({ order, step, action, dur, worker, clock ? *clock : 0 });
        }

        void HouseDone(uint32_t id) override
        {
            done.push_back(id);
            if (onDone)
                onDone(id);
        }

        void CupTaken(uint32_t id) override { cups.push_back(id); }
        void Delivered(uint32_t id) override { delivered.push_back(id); }

        Order* Find(uint32_t id)
        {
            for (Order& o : orders)
                if (o.id == id)
                    return &o;
            return nullptr;
        }

        void Unqueue(uint32_t id)
        {
            queue.erase(std::remove(queue.begin(), queue.end(), id), queue.end());
        }

        std::vector<uint64_t> QueueGuids()
        {
            std::vector<uint64_t> out;
            for (uint32_t id : queue)
                if (Order* o = Find(id))
                    out.push_back(o->guid);
            return out;
        }
    };

    Config Quick()
    {
        Config c;
        c.sitMinMs = 40000;
        c.sitMaxMs = 70000;
        return c;
    }

    // One cafe: its default layout at an anchor, the staff in the fake world at their homes, the engine.
    struct Sim
    {
        Geometry geo;
        FakeWorld world;
        FakeCafe cafe;
        Inputs in;
        uint32_t now = 4000000000u;      // near the clock's wrap: every timer must be wrap-safe
        std::unique_ptr<Engine> engine;
        std::map<std::string, uint64_t> staffGuid;
        Config cfg;

        Sim(uint8_t cafeId, uint64_t seed, Config config = Quick(), Pose anchor = Anchor) : cfg(config)
        {
            geo = FromLayout(cafeId, anchor);
            uint64_t spawn = 7000;
            for (StaffHome& s : geo.staff)
            {
                s.spawnId = ++spawn;
                uint64_t const g = ++world.next;
                FakeWorld::Unit u;
                u.entry = s.entry;
                u.pose = s.home;
                world.units[g] = u;
                world.staff[s.spawnId] = g;
                staffGuid[s.role] = g;
            }
            for (std::size_t i = 0; i < geo.chairs.size(); ++i)
                geo.chairs[i].spawnId = 8000 + i;
            cafe.clock = &now;
            engine = std::make_unique<Engine>(geo, cfg, world, cafe, seed);
            in.open = 1;
            in.baristas = 1;
            in.queueCap = 6;
            in.playerNear = true;
        }

        void Tick(int n = 1)
        {
            for (int i = 0; i < n; ++i)
            {
                world.Advance(250);
                now += 250;
                in.queueOrder = cafe.QueueGuids();
                in.queueLen = uint8_t(cafe.queue.size());
                engine->Update(now, in);
            }
        }

        bool Until(std::function<bool()> const& done, int maxTicks = 4000)
        {
            for (int i = 0; i < maxTicks; ++i)
            {
                if (done())
                    return true;
                Tick();
            }
            return done();
        }

        Customer const* ByGuid(uint64_t g) const
        {
            for (Customer const& c : engine->Customers())
                if (c.guid == g)
                    return &c;
            return nullptr;
        }

        Customer const* ByOrder(uint32_t id) const
        {
            for (Customer const& c : engine->Customers())
                if (c.orderId == id)
                    return &c;
            return nullptr;
        }

        Phase PhaseOf(uint64_t g) const
        {
            Customer const* c = ByGuid(g);
            return c ? c->phase : Phase::Gone;
        }

        Vec3 At(uint64_t g) { return world.units[g].pose.At(); }

        // Stops new arrivals (the tests that follow one customer); players may still be near.
        void NoMore()
        {
            cfg.customers = false;
            engine->Configure(cfg);
        }

        // A player standing (or sitting) at p.
        void PlayerAt(uint64_t guid, Vec3 p, bool sitting)
        {
            for (PlayerNear& q : world.players)
                if (q.guid == guid)
                {
                    q.pos = p;
                    q.sitting = sitting;
                    return;
                }
            world.players.push_back({ guid, p, sitting });
        }

        // Cafe takes an order (a barista at the counter).
        void Take(uint32_t id, std::string const& line = "One Cathedral Black, please.")
        {
            cafe.Unqueue(id);
            if (FakeCafe::Order* o = cafe.Find(id))
                o->state = 'T';
            engine->OrderTaken(id, line);
        }

        void Serve(uint32_t id, char q = 'P')
        {
            if (FakeCafe::Order* o = cafe.Find(id))
                o->state = 'S';
            engine->OrderServed(id, q, "Hot and bitter. Like my shift.", 2705, 909350);
        }

        // The first customer registered with Cafe: its order.
        FakeCafe::Order* FirstOrder() { return cafe.orders.empty() ? nullptr : &cafe.orders.front(); }
    };

    std::size_t CafeCount(uint8_t cafeId)
    {
        std::size_t n = 0;
        for (Bleakhold::CafeData::LayoutPiece const& p : Bleakhold::CafeData::Layout)
            n += p.cafeId == cafeId;
        return n;
    }
}

// ---- the layout as the crowd sees it ----

TEST("crowd: the default layout of both cafes as a Geometry")
{
    for (uint8_t cafe : { uint8_t(1), uint8_t(2) })
    {
        CHECK(CafeCount(cafe) > 50);
        Geometry const g = FromLayout(cafe, Anchor);
        CHECK_EQN(g.queue.size(), 8u);
        CHECK_EQN(g.side.size(), 8u);
        CHECK_EQN(g.nodes.size(), 9u);
        CHECK_EQN(g.chairs.size(), 12u);
        CHECK_EQN(g.kegs.size(), 2u);
        CHECK_EQN(g.tableTops.size(), 4u);
        CHECK_EQN(g.staff.size(), cafe == 1 ? 4u : 6u);
        for (std::size_t i = 0; i < g.stations.size(); ++i)
            CHECK_EQN(g.stations[i].id, Bleakhold::CafeData::Stations[i].id);
        // spec 3.12.3, in the cafe's frame
        auto [pf, pl] = FL(Anchor, g.pickupSpot.At());
        CHECK(Near(pf, 0) && Near(pl, -1.6f));
        auto [df, dl] = FL(Anchor, g.door.At());
        CHECK(Near(df, -24) && Near(dl, 10));
        Station const& e = g.stations[std::size_t(Bleakhold::CafeData::StationIndex('E'))];
        auto [e0f, e0l] = FL(Anchor, e.spots[0]);
        auto [e1f, e1l] = FL(Anchor, e.spots[1]);
        CHECK(Near(e0f, 4.0f) && Near(e1f, 4.0f) && Near(std::fabs(e0l), 0.35f) && Near(e0l, -e1l));
        Station const& v = g.stations[std::size_t(Bleakhold::CafeData::StationIndex('V'))];
        auto [v0f, v0l] = FL(Anchor, v.spots[0]);
        CHECK(Near(v0f, 1.6f) && Near(std::fabs(v0l), 0.35f));
        Station const& k = g.stations[std::size_t(Bleakhold::CafeData::StationIndex('K'))];
        auto [k0f, k0l] = FL(Anchor, k.spots[0]);
        CHECK(Near(k0l, 4.4f) && (Near(k0f, 2.05f) || Near(k0f, 2.75f)));
        Station const& c = g.stations[std::size_t(Bleakhold::CafeData::StationIndex('C'))];
        auto [c0f, c0l] = FL(Anchor, c.spots[0]);
        CHECK(Near(c0l, -4.4f) && (Near(c0f, 2.05f) || Near(c0f, 2.75f)));
        for (Station const& s : g.stations)
        {
            CHECK(Near(Dist2d(s.spots[0], s.spots[1]), 0.7f));
            Vec3 const mid{ (s.spots[0].x + s.spots[1].x) / 2, (s.spots[0].y + s.spots[1].y) / 2, 0 };
            Vec3 const obj{ s.objX, s.objY, 0 };
            CHECK(Near(Dist2d(s.behind, obj), Dist2d(mid, obj) + BehindYd));
        }
        for (Chair const& ch : g.chairs)
        {
            CHECK(ch.box >= 0 && InsideBox(ch.seat.At(), g.boxes[std::size_t(ch.box)]));
            CHECK(ch.tableTop >= 0);
            CHECK_EQN(ch.slots, 1);
            CHECK_EQN(ch.height, 1);
            Vec3 const top = g.tableTops[std::size_t(ch.tableTop)];
            CHECK(Near(Dist2d(ch.approach, top), Dist2d(ch.seat.At(), top) + Bleakhold::CafeData::ApproachYd));
            CHECK(Near(Dist2d(ch.seat.At(), top), 1.1f));
            // a sitter faces its table
            CHECK(Near(std::cos(ch.seat.o - AngleTo(ch.seat.At(), top)), 1.0f));
        }
        auto [a1f, a1l] = FL(Anchor, g.chairs[0].approach);
        CHECK(Near(a1f, -2.2f) && Near(a1l, -5.5f));
        for (Keg const& kg : g.kegs)
        {
            CHECK(kg.box >= 0);
            auto [kf, kl] = FL(Anchor, kg.spot);
            CHECK(Near(kf, -14.8f) && (Near(kl, -5.5f) || Near(kl, -11.5f)));
            Vec3 const centre{ g.boxes[std::size_t(kg.box)].x, g.boxes[std::size_t(kg.box)].y, 0 };
            CHECK(Near(Dist2d(kg.approach, centre), Dist2d(kg.spot, centre) + Bleakhold::CafeData::ApproachYd));
            CHECK(Near(std::cos(kg.facing - AngleTo(kg.spot, centre)), 1.0f));
        }
        // side points: 1.5 yd off the line, perpendicular to it, toward the seating
        float cx = 0, cy = 0;
        for (Chair const& ch : g.chairs)
        {
            cx += ch.seat.x / 12;
            cy += ch.seat.y / 12;
        }
        for (std::size_t i = 0; i < g.queue.size(); ++i)
        {
            CHECK(Near(Dist2d(g.side[i], g.queue[i]), SideYd));
            CHECK(Dist2d(g.side[i], { cx, cy, 0 }) < Dist2d(g.queue[i], { cx, cy, 0 }));
            Vec3 const a = g.queue[i > 0 ? i - 1 : i], b = g.queue[i + 1 < g.queue.size() ? i + 1 : i];
            float const dot = (b.x - a.x) * (g.side[i].x - g.queue[i].x) + (b.y - a.y) * (g.side[i].y - g.queue[i].y);
            CHECK(Near(dot, 0.0f, 1e-3f));
        }
        for (Box const& b : g.boxes)
            CHECK(b.halfW > 0 && b.halfD > 0);
    }
}

TEST("crowd: the aisle graph of both cafes is connected and keeps 0.8 yd from every footprint")
{
    for (uint8_t cafe : { uint8_t(1), uint8_t(2) })
        for (Pose const& anchor : { Anchor, Straight })
        {
            Geometry const g = FromLayout(cafe, anchor);
            Graph const gr = BuildGraph(g.nodes, g.door.At(), g.boxes, AisleClearance);
            CHECK(Connected(gr));
            CHECK(IsolatedNodes(gr).empty());
            CHECK_EQN(gr.adj[0].size(), 1u);
            CHECK_EQN(gr.adj[0].front().first, 1u);
            LegRules const r = AisleRules(g);
            for (std::size_t i = 0; i < gr.pts.size(); ++i)
                for (auto const& [j, d] : gr.adj[i])
                {
                    CHECK(d <= MaxEdge || i == 0 || j == 0);
                    std::string const p = LegProblem({ gr.pts[i], gr.pts[j] }, r);
                    CHECK_MSG(p.empty(), "cafe " + std::to_string(cafe) + " edge " + std::to_string(i) + "-" +
                                             std::to_string(j) + ": " + p);
                }
            // path_1..9 are joined into the aisles the spec draws (3.12.3: door side, front, middle, back)
            CHECK(gr.adj.size() == 10u);
        }
}

TEST("crowd: every chair, keg spot and queue slot is reachable from the pickup spot and from the door")
{
    for (uint8_t cafe : { uint8_t(1), uint8_t(2) })
    {
        Geometry const g = FromLayout(cafe, Anchor);
        Graph const gr = BuildGraph(g.nodes, g.door.At(), g.boxes, AisleClearance);
        LegRules const r = AisleRules(g);
        std::vector<End> starts{ End{ g.pickupSpot.At(), -1, false }, End{ g.door.At(), -1, true } };
        for (End const& from : starts)
        {
            std::string const where = std::string(from.door ? "door" : "pickup") + " cafe " + std::to_string(cafe);
            for (Chair const& ch : g.chairs)
            {
                Leg leg = Route(gr, from, End{ ch.approach, ch.box, false }, g.boxes);
                CHECK_MSG(leg.ok, where + " -> chair " + std::to_string(ch.slot));
                CHECK(Dist2d(leg.points.back(), ch.approach) < 1e-4f);
                leg.points.push_back(ch.seat.At());
                std::string const p = LegProblem(leg.points, r);
                CHECK_MSG(p.empty(), where + " -> chair " + std::to_string(ch.slot) + ": " + p);
            }
            for (Keg const& k : g.kegs)
            {
                Leg leg = Route(gr, from, End{ k.approach, k.box, false }, g.boxes);
                CHECK_MSG(leg.ok, where + " -> keg");
                leg.points.push_back(k.spot);
                std::string const p = LegProblem(leg.points, r);
                CHECK_MSG(p.empty(), where + " -> keg: " + p);
            }
            for (std::size_t q = 0; q < g.queue.size(); ++q)
            {
                Leg const leg = Route(gr, from, End{ g.queue[q], -1, false }, g.boxes);
                CHECK_MSG(leg.ok, where + " -> queue " + std::to_string(q + 1));
                std::string const p = LegProblem(leg.points, r);
                CHECK_MSG(p.empty(), where + " -> queue " + std::to_string(q + 1) + ": " + p);
            }
        }
        // the places by the pickup spot, the order spot and every cup front
        for (uint8_t k = 0; k < MaxPickupWait; ++k)
        {
            Leg const leg = Route(gr, End{ g.door.At(), -1, true }, End{ PickupWait(g, k), -1, false }, g.boxes);
            CHECK_MSG(leg.ok && LegProblem(leg.points, r).empty(), "pickup place " + std::to_string(k));
        }
        Leg const order = Route(gr, End{ g.door.At(), -1, true }, End{ g.orderSpot.At(), -1, false }, g.boxes);
        CHECK(order.ok && LegProblem(order.points, r).empty());
    }
}

TEST("crowd: leg plans for every transition keep clear of footprints and occupied queue slots")
{
    for (uint8_t cafe : { uint8_t(1), uint8_t(2) })
    {
        Geometry const g = FromLayout(cafe, Anchor);
        Graph const gr = BuildGraph(g.nodes, g.door.At(), g.boxes, AisleClearance);
        LegRules const r = AisleRules(g);
        std::string const at = "cafe " + std::to_string(cafe) + " ";
        // door -> the queue tail k, with the slots ahead of it taken (newcomers come from the far end)
        for (std::size_t k = 0; k < g.queue.size(); ++k)
        {
            std::vector<Vec3> const ahead(g.queue.begin(), g.queue.begin() + std::ptrdiff_t(k));
            Leg const leg = Route(gr, End{ g.door.At(), -1, true }, End{ g.queue[k], -1, false }, g.boxes, ahead);
            CHECK_MSG(leg.ok, at + "door -> tail " + std::to_string(k + 1));
            CHECK_MSG(LegProblem(leg.points, r).empty(), at + "door -> tail: " + LegProblem(leg.points, r));
            std::string const slots = SlotProblem(leg.points, ahead, AisleClearance);
            CHECK_MSG(slots.empty(), at + "door -> tail " + std::to_string(k + 1) + ": " + slots);
        }
        // queue slot k -> its side point -> the pickup spot, the order spot or the door, every other slot taken
        for (std::size_t k = 0; k < g.queue.size(); ++k)
        {
            std::vector<Vec3> others;
            for (std::size_t j = 0; j < g.queue.size(); ++j)
                if (j != k)
                    others.push_back(g.queue[j]);
            std::vector<End> const ends{ End{ g.pickupSpot.At(), -1, false }, End{ g.door.At(), -1, true },
                                         End{ PickupWait(g, 3), -1, false } };
            for (End const& to : ends)
            {
                Leg leg = Route(gr, End{ g.side[k], -1, false }, to, g.boxes, others);
                CHECK_MSG(leg.ok, at + "queue " + std::to_string(k + 1) + " -> side -> on");
                leg.points.insert(leg.points.begin(), g.queue[k]);
                CHECK_MSG(LegProblem(leg.points, r).empty(), at + "out of line: " + LegProblem(leg.points, r));
                std::string const slots = SlotProblem(leg.points, others, AisleClearance);
                CHECK_MSG(slots.empty(), at + "queue " + std::to_string(k + 1) + " out: " + slots);
            }
        }
        // pickup -> every seat; seat -> its approach point -> the door; the same for the keg spots
        for (Chair const& ch : g.chairs)
        {
            Leg in = Route(gr, End{ g.pickupSpot.At(), -1, false }, End{ ch.approach, ch.box, false }, g.boxes);
            in.points.push_back(ch.seat.At());
            CHECK(in.ok && LegProblem(in.points, r).empty());
            Leg out = Route(gr, End{ ch.approach, ch.box, false }, End{ g.door.At(), -1, true }, g.boxes);
            out.points.insert(out.points.begin(), ch.seat.At());
            CHECK_MSG(out.ok && LegProblem(out.points, r).empty(), at + "seat out: " + LegProblem(out.points, r));
            CHECK(Dist2d(out.points[1], ch.approach) < 1e-4f);
        }
        for (Keg const& k : g.kegs)
        {
            Leg out = Route(gr, End{ k.approach, k.box, false }, End{ g.door.At(), -1, true }, g.boxes);
            out.points.insert(out.points.begin(), k.spot);
            CHECK(out.ok && LegProblem(out.points, r).empty());
        }
        // a straight leg needs no graph; an impossible one says so and is the straight line
        Leg const direct = Route(gr, End{ g.queue[1], -1, false }, End{ g.queue[0], -1, false }, g.boxes);
        CHECK(direct.ok && direct.points.size() == 2);
        Geometry walled = g;
        walled.boxes.push_back({ g.pickupSpot.x, g.pickupSpot.y, 40.0f, 40.0f, 0.0f });
        Graph const wg = BuildGraph(walled.nodes, walled.door.At(), walled.boxes, AisleClearance);
        Leg const none = Route(wg, End{ walled.door.At(), -1, true }, End{ walled.chairs[0].approach, -1, false },
                               walled.boxes);
        CHECK(!none.ok && none.points.size() == 2);
    }
}

TEST("crowd: a node added with .cafe add path joins the graph; a far one is isolated")
{
    Geometry g = FromLayout(1, Anchor);
    g.nodes.push_back(ToWorld(Anchor, -14.0f, 0.5f));
    Graph const gr = BuildGraph(g.nodes, g.door.At(), g.boxes, AisleClearance);
    CHECK(!gr.adj.back().empty());
    CHECK(Connected(gr));
    g.nodes.push_back(ToWorld(Anchor, -60.0f, 40.0f));
    Graph const far = BuildGraph(g.nodes, g.door.At(), g.boxes, AisleClearance);
    std::vector<std::size_t> const iso = IsolatedNodes(far);
    CHECK_EQN(iso.size(), 1u);
    CHECK(!iso.empty() && iso.front() == far.pts.size() - 1);
    CHECK(!Connected(far));
}

TEST("crowd: the staff's work graph joins every work spot and both homes")
{
    for (uint8_t cafe : { uint8_t(1), uint8_t(2) })
    {
        Geometry const g = FromLayout(cafe, Anchor);
        Graph const wg = BuildWorkGraph(g);
        CHECK_EQN(wg.pts.size(), 7u * 3u + 2u);
        CHECK(Connected(wg));
        LegRules const r = WorkRules(g);
        for (std::size_t i = 0; i < wg.pts.size(); ++i)
            for (auto const& [j, d] : wg.adj[i])
                CHECK_MSG(LegProblem({ wg.pts[i], wg.pts[j] }, r).empty(), LegProblem({ wg.pts[i], wg.pts[j] }, r));
        // no staff home or spot inside a footprint
        for (Vec3 const& p : wg.pts)
            for (Box const& b : g.boxes)
                CHECK(BoxDistance(p, b) >= WorkClearance);
    }
}

// ---- personas and spawning ----

TEST("crowd: persona eligibility and the named cooldown")
{
    namespace D = Bleakhold::CafeData;
    D::Persona const& corwin = D::Personas[std::size_t(D::PersonaIndex(909320))];
    D::Persona const& wendel = D::Personas[std::size_t(D::PersonaIndex(909327))];
    D::Persona const& mazreth = D::Personas[std::size_t(D::PersonaIndex(909367))];
    D::Persona const& citizen = D::Personas[std::size_t(D::PersonaIndex(909342))];
    PersonaTrack t;
    uint32_t const now = 50000000;
    CHECK(NamedEligible(corwin, t, now, 600000, false));
    CHECK(NamedEligible(corwin, t, now, 600000, true));
    t.alive = 1;
    CHECK(!NamedEligible(corwin, t, now, 600000, false));
    t.alive = 0;
    t.left = true;
    t.leftMs = now - 599999;
    CHECK(!NamedEligible(corwin, t, now, 600000, false));
    t.leftMs = now - 600000;
    CHECK(NamedEligible(corwin, t, now, 600000, false));
    // wrap-safe
    t.leftMs = 4294967000u;
    CHECK(!NamedEligible(corwin, t, 1000, 600000, false));
    CHECK(NamedEligible(corwin, t, 600000, 600000, false));
    PersonaTrack fresh;
    CHECK(NamedEligible(wendel, fresh, now, 600000, false));
    CHECK(!NamedEligible(wendel, fresh, now, 600000, true));   // a child: never in the Rush
    CHECK(!HasLook(mazreth));
    CHECK(!NamedEligible(mazreth, fresh, now, 600000, false));   // disabled, display 0
    CHECK(!NamedEligible(citizen, fresh, now, 600000, false));   // generic: not a named persona
}

TEST("crowd: persona pick: half named, children never in the Rush, groups need three places")
{
    namespace D = Bleakhold::CafeData;
    for (uint8_t cafe : { uint8_t(1), uint8_t(2) })
    {
        Tracks none{};
        int named = 0, children = 0, groups = 0, total = 0;
        Rng rng(77 + cafe);
        for (int i = 0; i < 4000; ++i)
        {
            Pick const p = PickPersona(cafe, false, 8, 1000000, 600000, none, rng);
            CHECK(p.persona >= 0);
            if (p.persona < 0)
                continue;
            D::Persona const& per = D::Personas[std::size_t(p.persona)];
            CHECK_EQN(per.cafeId, cafe);
            CHECK(per.enabled && HasLook(per));
            CHECK(per.kind != D::PersonaKind::Group);
            ++total;
            named += per.kind == D::PersonaKind::Named;
            children += per.child;
        }
        CHECK_MSG(named > total * 45 / 100 && named < total * 55 / 100,
                  std::to_string(named) + "/" + std::to_string(total));
        CHECK(children > 0);
        Rng rush(5 + cafe);
        for (int i = 0; i < 4000; ++i)
        {
            Pick const p = PickPersona(cafe, true, 8, 1000000, 600000, none, rush);
            if (p.persona < 0)
                continue;
            D::Persona const& per = D::Personas[std::size_t(p.persona)];
            CHECK(!per.child);
            if (per.kind == D::PersonaKind::Group)
            {
                ++groups;
                CHECK_EQN(p.members, 3);
                CHECK_EQN(per.groupSize, 3);
            }
            else
                CHECK_EQN(p.members, 1);
        }
        CHECK_MSG(groups > 800 && groups < 1200, std::to_string(groups));   // 25% of 4000
        Rng tight(9);
        for (int i = 0; i < 2000; ++i)
        {
            Pick const p = PickPersona(cafe, true, 2, 1000000, 600000, none, tight);
            CHECK(p.persona >= 0 && D::Personas[std::size_t(p.persona)].kind != D::PersonaKind::Group);
        }
        CHECK(PickPersona(cafe, true, 0, 1000000, 600000, none, tight).persona < 0);
        // every named persona alive: the generic ones still come
        Tracks busy{};
        for (std::size_t i = 0; i < D::Personas.size(); ++i)
            if (D::Personas[i].kind == D::PersonaKind::Named)
                busy[i].alive = 1;
        for (int i = 0; i < 200; ++i)
        {
            Pick const p = PickPersona(cafe, false, 8, 1000000, 600000, busy, tight);
            CHECK(p.persona >= 0 && D::Personas[std::size_t(p.persona)].kind != D::PersonaKind::Named);
        }
        // a group with a member alive does not come again
        Tracks grouped{};
        for (std::size_t i = 0; i < D::Personas.size(); ++i)
            if (D::Personas[i].kind == D::PersonaKind::Group)
                grouped[i].alive = 1;
        for (int i = 0; i < 400; ++i)
            CHECK(PickPersona(cafe, true, 8, 1000000, 600000, grouped, tight).members == 1);
    }
}

TEST("crowd: the spawn interval with 0 to 5 baristas and the Rush; alive caps")
{
    Config c;
    CHECK_EQN(ArrivalIntervalMs(c, 0, false, 0), 60000u);
    CHECK_EQN(ArrivalIntervalMs(c, 1, false, 0), 30000u);
    CHECK_EQN(ArrivalIntervalMs(c, 2, false, 0), 18750u);
    CHECK_EQN(ArrivalIntervalMs(c, 3, false, 0), 11719u);
    CHECK_EQN(ArrivalIntervalMs(c, 4, false, 0), 7324u);
    CHECK_EQN(ArrivalIntervalMs(c, 5, false, 0), 7324u);
    CHECK_EQN(ArrivalIntervalMs(c, 1, true, 0), 12000u);
    CHECK_EQN(ArrivalIntervalMs(c, 2, true, 0), 7500u);
    CHECK_EQN(ArrivalIntervalMs(c, 1, false, 8000), 38000u);
    CHECK_EQN(ArrivalIntervalMs(c, 1, false, -8000), 22000u);
    CHECK_EQN(ArrivalIntervalMs(c, 4, true, -8000), 3000u);   // never under 3 s
    CHECK_EQN(AliveCap(c, 1, false), 6);
    CHECK_EQN(AliveCap(c, 1, true), 8);
    CHECK_EQN(AliveCap(c, 0, false), 2);
    CHECK_EQN(AliveCap(c, 0, true), 2);
}

TEST("crowd: customers spawn only when open, near a player, under the caps")
{
    Sim s(1, 11);
    s.in.playerNear = false;
    s.Tick(200);
    CHECK_EQN(s.engine->Alive(), 0u);
    s.in.playerNear = true;
    s.Tick(20);                                        // the first customer 4 s after a player came
    CHECK(s.engine->Alive() >= 1u);
    s.Tick(4 * 60 * 30);                               // half an hour with nobody serving: the queue fills
    CHECK(s.engine->Alive() <= 6u);
    CHECK(int(s.cafe.queue.size()) + s.engine->WalkingIn() <= 6);
    s.in.baristas = 0;                                 // ambient: at most 2 alive
    Sim a(2, 12);
    a.in.baristas = 0;
    a.Tick(4 * 60 * 20);
    CHECK(a.engine->Alive() <= 2u);
    Sim off(1, 13);
    off.in.open = 3;
    off.Tick(400);
    CHECK_EQN(off.engine->Alive(), 0u);
    Config cfg = Quick();
    cfg.customers = false;
    Sim disabled(1, 14, cfg);
    disabled.Tick(400);
    CHECK_EQN(disabled.engine->Alive(), 0u);
}

// ---- seats ----

TEST("crowd: seat choice: nearest free 1-slot chair, player-occupied, reserved, keg fallback, none")
{
    Geometry g = FromLayout(1, Anchor);
    std::size_t const n = g.chairs.size();
    std::vector<bool> reserved(n, false), taken(n, false), kegs(g.kegs.size(), false);
    SeatPick p = PickSeat(g, g.pickupSpot.At(), reserved, taken, kegs);
    CHECK(p.kind == SeatKind::Chair);
    CHECK_EQN(g.chairs[std::size_t(p.index)].slot, 34);      // chair_1, at table_1 by the pickup side
    reserved[std::size_t(p.index)] = true;
    p = PickSeat(g, g.pickupSpot.At(), reserved, taken, kegs);
    CHECK_EQN(g.chairs[std::size_t(p.index)].slot, 35);
    taken[std::size_t(p.index)] = true;                      // a player sits there
    p = PickSeat(g, g.pickupSpot.At(), reserved, taken, kegs);
    CHECK_EQN(g.chairs[std::size_t(p.index)].slot, 38);      // chair_5 (table_3) is nearer than chair_3
    for (std::size_t i = 0; i < n; ++i)
        reserved[i] = true;
    p = PickSeat(g, g.pickupSpot.At(), reserved, taken, kegs);
    CHECK(p.kind == SeatKind::Keg && p.index == 0);
    kegs[0] = true;
    p = PickSeat(g, g.pickupSpot.At(), reserved, taken, kegs);
    CHECK(p.kind == SeatKind::Keg && p.index == 1);
    kegs[1] = true;
    p = PickSeat(g, g.pickupSpot.At(), reserved, taken, kegs);
    CHECK(p.kind == SeatKind::None && p.index == -1);
    // a bench (2 slots) is for players only
    Geometry b = g;
    for (Chair& c : b.chairs)
        c.slots = 2;
    std::vector<bool> freeSeats(n, false);
    std::vector<bool> freeKegs(b.kegs.size(), false);
    CHECK(PickSeat(b, b.pickupSpot.At(), freeSeats, freeSeats, freeKegs).kind == SeatKind::Keg);
}

TEST("crowd: OnSeat follows the core's chair slot formula (GameObject::Use), from seat 0")
{
    Chair c;
    c.seat = { 10, 20, 0, 0 };                           // seat 0, facing +x: the seats go along +y
    c.slots = 2;
    c.size = 1.0f;
    CHECK(OnSeat(c, { 10, 20, 0 }, 0.1f));
    CHECK(OnSeat(c, { 10, 21, 0 }, 0.1f));
    CHECK(!OnSeat(c, { 10, 20.5f, 0 }, 0.3f));
    CHECK(!OnSeat(c, { 10, 19, 0 }, 0.3f));
    c.slots = 3;
    c.size = 0.68f;
    CHECK(OnSeat(c, { 10, 20.68f, 0 }, 0.05f));
    CHECK(OnSeat(c, { 10, 21.36f, 0 }, 0.05f));
    CHECK(!OnSeat(c, { 10, 19.32f, 0 }, 0.05f));
    c.slots = 1;
    c.seat.o = 1.0f;
    CHECK(OnSeat(c, { 10.3f, 20.3f, 0 }, 0.6f));
    CHECK(!OnSeat(c, { 11, 20, 0 }, 0.6f));
    // FromLayout gives seat 0 the same way Cafe's site does (a 1-slot chair: the chair itself)
    Geometry const g = FromLayout(1, Anchor);
    auto [f, l] = FL(Anchor, g.chairs[0].seat.At());
    CHECK(Near(f, -2.9f) && Near(l, -5.5f));
}

// ---- house jobs ----

TEST("crowd: house FIFO: takeovers first, then player orders, then NPC orders")
{
    HouseQueue q;
    q.Add({ 1, false, false, { 1, 3, 4, 25 }, 50000 });
    q.Add({ 2, true, false, { 1, 3, 4, 25 }, 50000 });
    q.Add({ 3, false, false, { 1, 3, 4, 25 }, 50000 });
    q.Add({ 4, true, false, { 1, 3, 4, 25 }, 50000 });
    q.Add({ 5, true, true, { 1, 3, 4, 25 }, 50000 });
    q.Add({ 6, true, true, { 1, 3, 4, 25 }, 50000 });
    std::vector<uint32_t> order;
    for (Job const& j : q.Jobs())
        order.push_back(j.orderId);
    CHECK((order == std::vector<uint32_t>{ 5, 6, 2, 4, 1, 3 }));
    CHECK(q.Remove(4));
    CHECK(!q.Remove(4));
    q.Add({ 3, true, true, { 1 }, 1000 });          // queued again as a takeover: moves to the front group
    order.clear();
    for (Job const& j : q.Jobs())
        order.push_back(j.orderId);
    CHECK((order == std::vector<uint32_t>{ 5, 6, 3, 2, 1 }));
    CHECK_EQN(q.Pop()->orderId, 5u);
    CHECK_EQN(q.Jobs().size(), 4u);
}

TEST("crowd: house ETA with two workers, running jobs and the order's own time")
{
    // step times: Grind 1500, Pull Shot gold centre 2325, Hot Water 1000, Serve 1000
    CHECK_EQN(StepMs(1), 1500u);
    CHECK_EQN(StepMs(3), 2325u);
    CHECK_EQN(StepMs(5), 1812u);
    CHECK_EQN(StepMs(25), 1000u);
    Job const c1{ 7, false, false, { 1, 3, 4, 25 }, 0 };
    CHECK_EQN(JobMs(c1), 1500u + 2325u + 1000u + 1000u + 3u * HouseWalkMs);   // G, E (twice), V
    Job const padded{ 8, false, false, { 1, 3, 4, 25 }, 50000 };
    CHECK_EQN(JobMs(padded), 50000u);
    HouseQueue q;
    q.Add({ 10, true, false, { 1, 3, 4, 25 }, 50000 });
    q.Add({ 11, false, false, { 1, 3, 4, 25 }, 40000 });
    q.Add({ 12, false, false, { 1, 3, 4, 25 }, 45000 });
    std::vector<std::pair<uint32_t, uint32_t>> const running{ { 20, 10000 }, { 21, 20000 } };
    // a new player order: (player jobs ahead 50 s + running 30 s) / 2 = 40 s, + its own 55 s
    CHECK_EQN(EtaSec(q, running, 2, std::nullopt, 55000), 95u);
    // NPC order 12: (50 + 40 + 30) / 2 = 60 s + 45 s
    CHECK_EQN(EtaSec(q, running, 2, 12u, 55000), 105u);
    CHECK_EQN(EtaSec(q, running, 2, 10u, 55000), 15u + 50u);
    // a running order: its remaining time
    CHECK_EQN(EtaSec(q, running, 2, 21u, 55000), 20u);
    // one worker: everything ahead in a row
    CHECK_EQN(EtaSec(q, running, 1, 11u, 55000), 50u + 30u + 40u);
    HouseQueue empty;
    CHECK_EQN(EtaSec(empty, {}, 2, std::nullopt, 55000), 55u);
    CHECK_EQN(EtaSec(empty, {}, 0, std::nullopt, 1), 1u);     // rounded up, never zero workers
    // the padding spreads the minimum over the steps
    CHECK_EQN(StepDeadline(1000, 50000, 0, 4), 13500u);
    CHECK_EQN(StepDeadline(1000, 50000, 3, 4), 51000u);
    CHECK_EQN(StepDeadline(1000, 50000, 0, 0), 1000u);
}

TEST("crowd: spot choice: a free work spot, else the other, else behind the station")
{
    Geometry const g = FromLayout(1, Anchor);
    Station const& s = g.stations[0];
    CHECK_EQN(PickSpot(s, {}, {}), 0);
    CHECK_EQN(PickSpot(s, { s.spots[0] }, {}), 1);
    Vec3 const close = Toward(s.spots[0], s.spots[1], -0.5f);
    CHECK_EQN(PickSpot(s, { close }, {}), 1);              // within 0.6 yd
    Vec3 const away = Toward(s.spots[0], s.spots[1], -0.7f);
    CHECK_EQN(PickSpot(s, { away }, {}), 0);
    CHECK_EQN(PickSpot(s, { s.spots[0], s.spots[1] }, {}), 2);
    CHECK_EQN(PickSpot(s, {}, { s.spots[0] }), 1);          // the other worker's
    CHECK_EQN(PickSpot(s, { s.spots[1] }, { s.spots[0] }), 2);
    CHECK(Dist2d(SpotPoint(s, 2), s.behind) < 1e-6f);
}

TEST("crowd: a house job: the owner walks the stations, casts each step, pads to the minimum, then goes home")
{
    Sim s(1, 21);
    s.NoMore();
    s.Tick(4);
    uint64_t const owner = s.staffGuid["staff_owner"];
    Vec3 const home = s.At(owner);
    // a player stands on the grinder's first spot
    Station const& grinder = s.geo.stations[std::size_t(Bleakhold::CafeData::StationIndex('G'))];
    s.PlayerAt(42, grinder.spots[0], false);
    Job job{ 900, true, false, { 1, 3, 3, 19, 25 }, 55000 };
    s.engine->QueueHouseJob(job);
    uint32_t const start = s.now;
    CHECK(s.Until([&] { return !s.cafe.done.empty(); }, 4 * 120));
    uint32_t const took = s.now - start;
    CHECK_MSG(took >= 55000 && took < 75000, std::to_string(took));
    CHECK_EQN(s.cafe.steps.size(), 5u);
    for (std::size_t i = 0; i < s.cafe.steps.size(); ++i)
    {
        FakeCafe::StepRec const& r = s.cafe.steps[i];
        CHECK_EQN(r.order, 900u);
        CHECK_EQN(r.step, uint8_t(i));
        CHECK_EQN(r.action, job.actions[i]);
        CHECK_EQN(r.worker, owner);
        CHECK(r.dur >= StepMs(r.action));
    }
    // each step's spell, cast by the owner, in order
    std::vector<uint32_t> spells;
    for (auto const& [g, sp] : s.world.casts)
        if (g == owner)
            spells.push_back(sp);
    CHECK((spells == std::vector<uint32_t>{ 100901, 100903, 100903, 100919, 100925 }));
    // the two Pull Shots end at the gold centre, cleanly
    std::size_t shotEnds = 0;
    for (auto const& [g, sp] : s.world.finished)
        shotEnds += g == owner && sp == 100903;
    CHECK(shotEnds >= 2);
    CHECK_EQN(s.engine->WorkerAt(0).busy, false);
    // it worked the grinder from its free spot, and repeated the Pull Shot in place
    bool grinderSecond = false;
    for (FakeWorld::WalkRec const& w : s.world.walks)
        if (w.guid == owner && Dist2d(w.pts.back(), grinder.spots[1]) < 1e-3f)
            grinderSecond = true;
    CHECK(grinderSecond);
    // every staff walk stays in the work graph's clearance
    LegRules const r = WorkRules(s.geo);
    for (FakeWorld::WalkRec const& w : s.world.walks)
        if (w.guid == owner)
            CHECK_MSG(LegProblem(w.pts, r).empty(), LegProblem(w.pts, r));
    CHECK(s.Until([&] { return Dist2d(s.At(owner), home) < 0.05f && !s.world.Moving(owner); }, 200));
    // the emote states it set were all cleared
    CHECK_EQN(s.world.units[owner].emoteState, 0u);
}

TEST("crowd: two house workers make two drinks at once; the third waits; ETA and cancel")
{
    Sim s(2, 22);
    s.NoMore();
    s.Tick(4);
    for (uint32_t id : { 901u, 902u, 903u })
        s.engine->QueueHouseJob({ id, false, false, { 7, 9, 14, 25 }, 50000 });
    s.Tick(2);
    CHECK(s.engine->WorkerAt(0).busy && s.engine->WorkerAt(1).busy);
    CHECK_EQN(s.engine->WorkerAt(0).orderId, 901u);
    CHECK_EQN(s.engine->WorkerAt(1).orderId, 902u);
    CHECK_EQN(s.engine->HouseJobs().Jobs().size(), 1u);
    // 903 waits for one of the two: (running ~50 s + ~50 s) / 2 + its own 50 s
    uint32_t const eta = s.engine->HouseEtaSec(903u);
    CHECK_MSG(eta >= 95 && eta <= 101, std::to_string(eta));
    CHECK(s.engine->HouseEtaSec(901u) <= 50);
    CHECK(s.engine->Owns(903) && s.engine->Owns(901) && !s.engine->Owns(999));
    s.engine->CancelHouseJob(902);
    CHECK(!s.engine->WorkerAt(1).busy);
    s.Tick(1);
    CHECK_EQN(s.engine->WorkerAt(1).orderId, 903u);    // the head barista took the next one
    CHECK(s.Until([&] { return s.cafe.done.size() == 2; }, 4 * 90));
    CHECK((s.cafe.done == std::vector<uint32_t>{ 901, 903 }) || (s.cafe.done == std::vector<uint32_t>{ 903, 901 }));
    // one worker configured: the head barista stays home
    Config one = Quick();
    one.houseWorkers = 1;
    Sim t(1, 23, one);
    t.NoMore();
    t.engine->QueueHouseJob({ 1, false, false, { 1, 3, 4, 25 }, 30000 });
    t.engine->QueueHouseJob({ 2, false, false, { 1, 3, 4, 25 }, 30000 });
    t.Tick(2);
    CHECK(t.engine->WorkerAt(0).busy && !t.engine->WorkerAt(1).busy);
}

TEST("crowd: a house worker whose grid is not loaded makes the drink on its timer")
{
    Sim s(1, 24);
    s.NoMore();
    s.world.units[s.staffGuid["staff_owner"]].alive = false;
    s.world.units[s.staffGuid["staff_head"]].alive = false;
    s.engine->QueueHouseJob({ 77, true, false, { 1, 3, 4, 25 }, 30000 });
    uint32_t const start = s.now;
    CHECK(s.Until([&] { return !s.cafe.done.empty(); }, 4 * 60));
    CHECK(s.now - start >= 30000);
    CHECK_EQN(s.cafe.steps.size(), 4u);
    for (FakeCafe::StepRec const& r : s.cafe.steps)
        CHECK_EQN(r.worker, 0u);
}

// ---- a customer's visit ----

TEST("crowd: a customer's whole visit: in, queue, order, pickup, cup, seat, sips, out")
{
    Sim s(1, 31);
    LegRules const rules = AisleRules(s.geo);
    CHECK(s.Until([&] { return s.engine->Alive() == 1; }, 40));
    s.NoMore();
    uint64_t const guid = s.engine->Customers().front().guid;
    CHECK(guid != 0);
    Pose const door = s.world.units[guid].pose;
    CHECK(Dist2d(door.At(), s.geo.door.At()) < 1e-3f);
    // it walks to the queue's front and registers there
    CHECK(s.Until([&] { return !s.cafe.orders.empty(); }, 4 * 30));
    FakeCafe::Order const order = *s.FirstOrder();
    CHECK_EQN(order.guid, guid);
    CHECK_EQN(order.persona, uint8_t(s.ByGuid(guid)->persona));
    CHECK_EQN(order.group, 0u);
    CHECK(Dist2d(s.At(guid), s.geo.queue[0]) <= ArriveYd);
    CHECK(s.PhaseOf(guid) == Phase::Queue);
    // a barista takes it: the line once, then to the pickup spot by the side point
    s.Take(order.id);
    CHECK_EQN(s.world.SaysOf(guid, "One Cathedral Black, please."), 1u);
    CHECK(s.Until([&] { return s.PhaseOf(guid) == Phase::Pickup; }, 4 * 20));
    CHECK(Dist2d(s.At(guid), s.geo.pickupSpot.At()) <= ArriveYd);
    bool side = false;
    for (FakeWorld::WalkRec const& w : s.world.walks)
        if (w.guid == guid && w.pts.size() > 1 && Dist2d(w.pts[1], s.geo.side[0]) < 1e-3f)
            side = true;
    CHECK(side);
    // served: the cup on the counter, taken, thanks with an emote, CupTaken
    s.Serve(order.id, 'P');
    CHECK_EQN(s.world.gos.size(), 1u);
    Pose const cup = s.world.gos.begin()->second.at;
    auto [cf, cl] = FL(Anchor, cup.At());
    CHECK(Near(cf, Bleakhold::CafeData::CounterCupF) && Near(cl, -1.6f) &&
          Near(cup.z, s.geo.pickupSpot.z + Bleakhold::CafeData::CounterCupU));
    CHECK(s.Until([&] { return !s.cafe.cups.empty(); }, 4 * 10));
    CHECK_EQN(s.cafe.cups.front(), order.id);
    CHECK(s.world.gos.empty());
    CHECK_EQN(s.world.units[guid].hold, 2705u);
    CHECK_EQN(s.world.SaysOf(guid, "Hot and bitter. Like my shift."), 1u);
    CHECK_EQN(s.world.EmotesOf(guid, EmoteCheer), 1u);
    // to the nearest chair, reserved and locked at once
    CHECK(s.Until([&] { return s.PhaseOf(guid) == Phase::ToSeat; }, 20));
    Customer const* c = s.ByGuid(guid);
    CHECK(c && c->chair == 0);
    CHECK(s.engine->ChairReserved(0));
    CHECK(s.world.locked[s.geo.chairs[0].spawnId]);
    CHECK(s.Until([&] { return s.PhaseOf(guid) == Phase::Seated; }, 4 * 20));
    CHECK(Dist2d(s.At(guid), s.geo.chairs[0].seat.At()) <= ArriveYd);
    CHECK_EQN(s.world.units[guid].stand, uint8_t(StandSitLowChair + 1));
    CHECK(Near(std::cos(s.world.units[guid].pose.o - s.geo.chairs[0].seat.o), 1.0f));
    // its cup on the table beside it
    CHECK_EQN(s.world.gos.size(), 1u);
    FakeWorld::Go const tableCup = s.world.gos.begin()->second;
    CHECK_EQN(tableCup.entry, 909350u);
    Vec3 const top = s.geo.tableTops[std::size_t(s.geo.chairs[0].tableTop)];
    CHECK(Near(Dist2d(tableCup.at.At(), top), Bleakhold::CafeData::TableCupYd) && Near(tableCup.at.z, top.z));
    CHECK(Dist2d(tableCup.at.At(), s.geo.chairs[0].seat.At()) < Dist2d(top, s.geo.chairs[0].seat.At()));
    uint32_t const sat = s.now;
    // sipping every 6-10 s for 40-70 s, then up and out
    CHECK(s.Until([&] { return s.PhaseOf(guid) == Phase::Leaving; }, 4 * 80));
    uint32_t const sitMs = s.now - sat;
    CHECK_MSG(sitMs >= 40000 && sitMs <= 70500, std::to_string(sitMs));
    std::size_t const sips = s.world.EmotesOf(guid, EmoteEatNoSheathe);
    CHECK_MSG(sips >= 4 && sips <= 12, std::to_string(sips));
    CHECK_EQN(s.world.units[guid].stand, StandStand);
    CHECK(!s.engine->ChairReserved(0));
    CHECK(!s.world.locked[s.geo.chairs[0].spawnId]);
    CHECK(s.Until([&] { return s.ByGuid(guid) == nullptr; }, 4 * 40));
    CHECK(!s.world.Alive(guid));
    CHECK(Dist2d(s.At(guid), s.geo.door.At()) <= ArriveYd);
    CHECK(s.cafe.gone.empty());
    CHECK(s.world.teleports.empty());
    s.Tick(30);
    CHECK(s.world.gos.empty());                    // the table cup ran out after it left
    // the named cooldown starts when it is gone
    CHECK(s.engine->PersonaTracks()[std::size_t(order.persona)].left);
    // every walk of the visit keeps to the aisle rules
    for (FakeWorld::WalkRec const& w : s.world.walks)
        if (w.guid == guid)
            CHECK_MSG(LegProblem(w.pts, rules).empty(), LegProblem(w.pts, rules));
}

TEST("crowd: nobody on shift: the customer orders from the owner, who makes the drink")
{
    Sim s(2, 32);
    s.in.baristas = 0;
    uint64_t const owner = s.staffGuid["staff_owner"];
    // Cafe makes every NPC order ambient at once, from inside NpcArrived (the events wait for the end of the tick)
    s.cafe.onArrived = [&](FakeCafe::Order& o) {
        o.state = 'H';
        s.cafe.Unqueue(o.id);
        s.engine->HouseOrderTaken(o.id, "Grunt's Black. Hot. Now.", "Coming. Don't rush me.");
        s.engine->QueueHouseJob({ o.id, false, false, { 1, 3, 4, 25 }, 50000 });
    };
    s.cafe.onDone = [&](uint32_t id) { s.engine->OrderServed(id, 'G', "Strong! Strength and honor.", 2703, 909351); };
    CHECK(s.Until([&] { return !s.cafe.orders.empty(); }, 4 * 60));
    s.NoMore();
    FakeCafe::Order const o = s.cafe.orders.front();
    CHECK(s.Until([&] { return s.PhaseOf(o.guid) == Phase::Ordering; }, 4 * 20));
    CHECK(Dist2d(s.At(o.guid), s.geo.orderSpot.At()) <= ArriveYd);
    s.Tick(12);
    CHECK_EQN(s.world.SaysOf(o.guid, "Grunt's Black. Hot. Now."), 1u);
    CHECK_EQN(s.world.SaysOf(owner, "Coming. Don't rush me."), 1u);
    // the owner said it facing the customer, who faced the owner
    CHECK(s.Until([&] { return s.PhaseOf(o.guid) == Phase::Pickup; }, 4 * 20));
    CHECK(s.engine->WorkerAt(0).busy);
    CHECK(s.Until([&] { return !s.cafe.done.empty(); }, 4 * 80));
    CHECK(s.Until([&] { return !s.cafe.cups.empty(); }, 4 * 20));
    CHECK_EQN(s.world.units[o.guid].hold, 2703u);
    CHECK_EQN(s.world.EmotesOf(o.guid, EmoteBow), 1u);
    CHECK(s.Until([&] { return s.ByGuid(o.guid) == nullptr; }, 4 * 160));
    CHECK(s.cafe.gone.empty());
}

TEST("crowd: the line moves up along the queue line and Cafe's order is the line")
{
    Sim s(1, 33);
    s.in.baristas = 4;                                 // a spawn every ~7 s
    CHECK(s.Until([&] { return s.cafe.orders.size() >= 3; }, 4 * 90));
    s.NoMore();
    s.Tick(40);
    // registered in line order: each at the slot of its place
    std::vector<uint64_t> const q = s.cafe.QueueGuids();
    CHECK(q.size() >= 3);
    for (std::size_t i = 0; i < q.size(); ++i)
    {
        Customer const* c = s.ByGuid(q[i]);
        CHECK(c && c->slot == int(i));
    }
    std::size_t const walksBefore = s.world.walks.size();
    // the front is taken: the rest move up one slot each, along the line
    s.Take(s.cafe.queue.front());
    s.Tick(3);
    for (std::size_t i = 1; i < q.size(); ++i)
        CHECK(s.ByGuid(q[i])->slot == int(i));        // the taken one still stands there: nobody moves in yet
    s.Tick(8);
    for (std::size_t i = 1; i < q.size(); ++i)
        CHECK(s.ByGuid(q[i])->slot == int(i) - 1);
    for (std::size_t w = walksBefore; w < s.world.walks.size(); ++w)
    {
        FakeWorld::WalkRec const& r = s.world.walks[w];
        if (std::find(q.begin() + 1, q.end(), r.guid) == q.end())
            continue;                                    // the taken one, or a newcomer still walking in
        for (std::size_t i = 1; i < r.pts.size(); ++i)
        {
            bool onLine = false;
            for (Vec3 const& slot : s.geo.queue)
                onLine = onLine || Dist2d(slot, r.pts[i]) < 1e-3f;
            CHECK(onLine);
        }
    }
    s.Tick(30);
    for (std::size_t i = 1; i < q.size(); ++i)
        CHECK(Dist2d(s.At(q[i]), s.geo.queue[i - 1]) <= ArriveYd);
}

TEST("crowd: a newcomer keeps the slot it walks to, so nobody behind it is sent there")
{
    Sim s(1, 35);
    s.in.baristas = 4;
    s.in.rush = true;                                  // spawns every few seconds, groups of three
    auto walkingIn = [&] {
        std::size_t n = 0;
        for (Customer const& c : s.engine->Customers())
            n += c.phase == Phase::WalkIn && c.mv.walking;
        return n;
    };
    CHECK(s.Until([&] { return !s.cafe.orders.empty() && walkingIn() >= 2; }, 4 * 180));
    // the front gives up and steps out while the others walk in: the line moves up
    FakeCafe::Order const o = s.cafe.orders.front();
    s.cafe.Unqueue(o.id);
    s.engine->OrderFailed(o.id, "");
    std::map<uint64_t, int> walkSlot;
    std::size_t walkers = 0;
    for (int t = 0; t < 4 * 40; ++t)
    {
        s.Tick();
        std::vector<std::pair<uint64_t, Vec3>> targets;   // where each one in line stands, or ends its walk
        for (Customer const& c : s.engine->Customers())
        {
            bool const walkIn = c.phase == Phase::WalkIn && c.mv.walking;
            if (walkIn)
            {
                auto const [it, first] = walkSlot.emplace(c.guid, c.slot);
                walkers += first;
                CHECK_MSG(it->second == c.slot, "a newcomer's slot changed on its way in");
                CHECK(c.slot >= 0 && Dist2d(c.mv.route.back(), s.geo.queue[std::size_t(c.slot)]) < 1e-3f);
            }
            if (walkIn || c.phase == Phase::Queue || c.phase == Phase::Taken || c.phase == Phase::Complain)
                targets.emplace_back(c.guid, c.mv.walking ? c.mv.route.back() : s.At(c.guid));
        }
        for (std::size_t a = 0; a < targets.size(); ++a)
            for (std::size_t b = a + 1; b < targets.size(); ++b)
                CHECK_MSG(Dist2d(targets[a].second, targets[b].second) > ArriveYd,
                          "two customers head for one spot: " + std::to_string(targets[a].first) + " and " +
                              std::to_string(targets[b].first));
    }
    CHECK(walkers >= 2);
    // and then the line moved up: whoever stands in it stands at the slot of its place
    s.NoMore();
    s.Tick(4 * 20);
    std::set<int> slots;
    for (Customer const& c : s.engine->Customers())
        if (c.phase == Phase::Queue && !c.mv.walking)
        {
            CHECK(slots.insert(c.slot).second);
            CHECK(Dist2d(s.At(c.guid), s.geo.queue[std::size_t(c.slot)]) <= ArriveYd);
        }
}

TEST("crowd: patience runs out: the complaint, NO or RUDE, and out by the side point")
{
    Sim s(1, 34);
    CHECK(s.Until([&] { return !s.cafe.orders.empty(); }, 4 * 60));
    s.NoMore();
    FakeCafe::Order const o = s.cafe.orders.front();
    s.cafe.Unqueue(o.id);
    s.engine->OrderFailed(o.id, "I've stood shorter watches on the wall. I'm off.");
    CHECK_EQN(s.world.SaysOf(o.guid, "I've stood shorter watches on the wall. I'm off."), 1u);
    CHECK(s.world.EmotesOf(o.guid, EmoteNo) + s.world.EmotesOf(o.guid, EmoteRude) == 1u);
    CHECK(s.PhaseOf(o.guid) == Phase::Complain);
    CHECK(s.Until([&] { return s.PhaseOf(o.guid) == Phase::Leaving; }, 20));
    FakeWorld::WalkRec const* out = nullptr;
    for (FakeWorld::WalkRec const& w : s.world.walks)
        if (w.guid == o.guid)
            out = &w;
    CHECK(out && out->pts.size() > 1 && Dist2d(out->pts[1], s.geo.side[0]) < 1e-3f);
    CHECK(s.Until([&] { return s.ByGuid(o.guid) == nullptr; }, 4 * 60));
    CHECK(s.cafe.gone.empty());
    CHECK(s.cafe.cups.empty());
    // a failed order after its cup is taken changes nothing; an unknown order neither
    s.engine->OrderFailed(12345, "x");
    s.engine->OrderServed(12345, 'P', "x", 1, 1);
    CHECK(s.world.gos.empty());
}

TEST("crowd: refused by Cafe: the customer leaves")
{
    Sim s(1, 35);
    s.cafe.refuse = true;
    CHECK(s.Until([&] {
        for (Customer const& c : s.engine->Customers())
            if (c.phase == Phase::Leaving)
                return true;
        return false;
    }, 4 * 60));
    s.NoMore();
    CHECK(s.Until([&] { return s.engine->Alive() == 0; }, 4 * 60));
    CHECK(s.cafe.gone.empty());
}

TEST("crowd: a player in the chosen chair: the customer steps out and sits elsewhere; no seat: a keg spot")
{
    Sim s(1, 36);
    CHECK(s.Until([&] { return !s.cafe.orders.empty(); }, 4 * 60));
    s.NoMore();
    FakeCafe::Order const o = s.cafe.orders.front();
    s.Take(o.id);
    CHECK(s.Until([&] { return s.PhaseOf(o.guid) == Phase::Pickup; }, 4 * 20));
    s.Serve(o.id);
    CHECK(s.Until([&] { return s.PhaseOf(o.guid) == Phase::ToSeat; }, 4 * 10));
    CHECK_EQN(s.ByGuid(o.guid)->chair, 0);
    // a player sits down in it while the customer walks over (they were there first)
    s.PlayerAt(4242, s.geo.chairs[0].seat.At(), true);
    CHECK(s.engine->SeatTakenByPlayer(34) == false);   // the scan runs on the next tick
    s.Tick(1);
    CHECK(s.engine->SeatTakenByPlayer(34));
    CHECK(s.engine->PlayerSeat(4242) == std::optional<uint16_t>(34));
    CHECK(!s.engine->PlayerSeat(4243));
    CHECK(s.Until([&] {
        Customer const* c = s.ByGuid(o.guid);
        return c && c->chair != 0 && c->phase == Phase::ToSeat;
    }, 4 * 20));
    int const other = s.ByGuid(o.guid)->chair;
    CHECK(other == 1);
    CHECK(!s.engine->ChairReserved(0));
    CHECK(s.Until([&] { return s.PhaseOf(o.guid) == Phase::Seated; }, 4 * 20));
    CHECK(Dist2d(s.At(o.guid), s.geo.chairs[1].seat.At()) <= ArriveYd);
    LegRules const r = AisleRules(s.geo);
    for (FakeWorld::WalkRec const& w : s.world.walks)
        if (w.guid == o.guid)
            CHECK_MSG(LegProblem(w.pts, r).empty(), LegProblem(w.pts, r));
    // every chair taken by players: the next customer stands at a keg table
    Sim k(1, 37);
    for (std::size_t i = 0; i < k.geo.chairs.size(); ++i)
        k.PlayerAt(100 + i, k.geo.chairs[i].seat.At(), true);
    CHECK(k.Until([&] { return !k.cafe.orders.empty(); }, 4 * 60));
    k.NoMore();
    FakeCafe::Order const ko = k.cafe.orders.front();
    k.Take(ko.id);
    CHECK(k.Until([&] { return k.PhaseOf(ko.guid) == Phase::Pickup; }, 4 * 20));
    k.Serve(ko.id);
    CHECK(k.Until([&] { return k.PhaseOf(ko.guid) == Phase::AtKeg; }, 4 * 40));
    CHECK(Dist2d(k.At(ko.guid), k.geo.kegs[0].spot) <= ArriveYd);
    CHECK(k.engine->KegTaken(0));
    CHECK(Near(std::cos(k.world.units[ko.guid].pose.o - k.geo.kegs[0].facing), 1.0f));
    CHECK(k.Until([&] { return k.ByGuid(ko.guid) == nullptr; }, 4 * 120));
    CHECK(!k.engine->KegTaken(0));
    // and with the kegs taken too: out at once, sipping
    Sim n(1, 38);
    for (std::size_t i = 0; i < n.geo.chairs.size(); ++i)
        n.PlayerAt(100 + i, n.geo.chairs[i].seat.At(), true);
    CHECK(n.Until([&] { return !n.cafe.orders.empty(); }, 4 * 60));
    n.NoMore();
    FakeCafe::Order const no = n.cafe.orders.front();
    n.Take(no.id);
    CHECK(n.Until([&] { return n.PhaseOf(no.guid) == Phase::Pickup; }, 4 * 20));
    n.Serve(no.id);
    CHECK(n.Until([&] { return n.PhaseOf(no.guid) == Phase::ToKeg; }, 4 * 10));
}

TEST("crowd: a Rush group comes in together, in consecutive slots, and registers in member order")
{
    bool seen = false;
    for (uint64_t seed = 1; seed < 60 && !seen; ++seed)
    {
        Sim s(1, seed);
        s.in.rush = true;
        s.in.queueCap = 8;
        s.in.baristas = 2;
        bool group = false;
        for (int i = 0; i < 4 * 120 && !group; ++i)
        {
            s.Tick();
            for (Customer const& c : s.engine->Customers())
                group = group || c.groupId != 0;
        }
        if (!group)
            continue;
        seen = true;
        std::vector<Customer> members;
        for (Customer const& c : s.engine->Customers())
            if (c.groupId)
                members.push_back(c);
        CHECK_EQN(members.size(), 3u);
        uint32_t const gid = members.front().groupId;
        for (Customer const& m : members)
            CHECK_EQN(m.groupId, gid);
        CHECK(Bleakhold::CafeData::Personas[std::size_t(members[0].persona)].kind ==
              Bleakhold::CafeData::PersonaKind::Group);
        CHECK(members[1].slot == members[0].slot + 1 && members[2].slot == members[1].slot + 1);
        // they follow each other out of the door
        CHECK(members[0].phase != Phase::Pending);
        s.NoMore();
        CHECK(s.Until([&] {
            std::size_t n = 0;
            for (FakeCafe::Order const& o : s.cafe.orders)
                n += o.group == gid;
            return n == 3;
        }, 4 * 60));
        std::vector<uint8_t> order;
        std::vector<int> slots;
        for (FakeCafe::Order const& o : s.cafe.orders)
            if (o.group == gid)
            {
                order.push_back(s.ByGuid(o.guid)->member);
                slots.push_back(s.ByGuid(o.guid)->slot);
            }
        CHECK((order == std::vector<uint8_t>{ 0, 1, 2 }));
        CHECK(slots[1] == slots[0] + 1 && slots[2] == slots[1] + 1);
    }
    CHECK(seen);
}

// ---- stuck, vanished, pause, close ----

TEST("crowd: stuck: teleported to the leg's end, then gone the second time (NpcGone)")
{
    Sim s(1, 41);
    CHECK(s.Until([&] { return !s.cafe.orders.empty(); }, 4 * 60));
    s.NoMore();
    FakeCafe::Order const o = s.cafe.orders.front();
    s.world.units[o.guid].frozen = true;               // it will not walk any more
    s.Take(o.id);
    CHECK(s.Until([&] { return !s.world.teleports.empty(); }, 4 * 60));
    CHECK_EQN(s.world.teleports.front(), o.guid);
    // the leg's end: its place by the pickup spot
    CHECK(Dist2d(s.At(o.guid), s.geo.pickupSpot.At()) < 1e-3f);
    CHECK(s.PhaseOf(o.guid) == Phase::Pickup);
    CHECK(s.cafe.gone.empty());
    s.Serve(o.id);
    // the cup is in front of it: it takes it where it stands, then is stuck on its way to the chair
    CHECK(s.Until([&] { return !s.cafe.cups.empty(); }, 4 * 10));
    CHECK(s.Until([&] { return s.ByGuid(o.guid) == nullptr; }, 4 * 120));
    CHECK(!s.world.Alive(o.guid));
    CHECK_EQN(s.world.teleports.size(), 1u);
    CHECK(s.cafe.gone.empty());                          // its cup was taken: Cafe has nothing left to close
    CHECK(!s.engine->ChairReserved(0));
    // stuck twice while Cafe still holds the order: it goes, and Cafe hears NpcGone
    Sim t(1, 42);
    t.in.baristas = 4;
    CHECK(t.Until([&] { return t.cafe.orders.size() >= 2; }, 4 * 90));
    t.NoMore();
    t.Tick(40);
    FakeCafe::Order const front = t.cafe.orders[0];
    FakeCafe::Order const second = t.cafe.orders[1];
    t.world.units[second.guid].frozen = true;
    t.Take(front.id);                                    // the line moves up: the second one cannot
    CHECK(t.Until([&] { return t.world.teleports.size() == 1; }, 4 * 60));
    CHECK_EQN(t.world.teleports.front(), second.guid);
    CHECK(Dist2d(t.At(second.guid), t.geo.queue[0]) < 1e-3f);
    CHECK(t.cafe.gone.empty());
    t.Take(second.id);
    CHECK(t.Until([&] { return !t.cafe.gone.empty(); }, 4 * 60));
    CHECK((t.cafe.gone == std::vector<uint32_t>{ second.id }));
    CHECK(!t.world.Alive(second.guid));
    CHECK(t.ByGuid(second.guid) == nullptr);
}

TEST("crowd: a customer that vanishes (grid unload): NpcGone, and its chair is free again")
{
    Sim s(1, 43);
    CHECK(s.Until([&] { return !s.cafe.orders.empty(); }, 4 * 60));
    s.NoMore();
    FakeCafe::Order const o = s.cafe.orders.front();
    s.world.units[o.guid].alive = false;
    s.Tick(1);
    CHECK((s.cafe.gone == std::vector<uint32_t>{ o.id }));
    CHECK(s.ByGuid(o.guid) == nullptr);
    // seated, after its cup: the chair and the table cup are released, no NpcGone
    Sim t(1, 44);
    CHECK(t.Until([&] { return !t.cafe.orders.empty(); }, 4 * 60));
    t.NoMore();
    FakeCafe::Order const q = t.cafe.orders.front();
    t.Take(q.id);
    CHECK(t.Until([&] { return t.PhaseOf(q.guid) == Phase::Pickup; }, 4 * 20));
    t.Serve(q.id);
    CHECK(t.Until([&] { return t.PhaseOf(q.guid) == Phase::Seated; }, 4 * 30));
    CHECK(t.engine->ChairReserved(0));
    t.world.units[q.guid].alive = false;
    t.Tick(2);
    CHECK(t.cafe.gone.empty());
    CHECK(!t.engine->ChairReserved(0));
    CHECK(!t.world.locked[t.geo.chairs[0].spawnId]);
    CHECK(t.world.gos.empty());
}

TEST("crowd: the pause freezes everyone and every timer")
{
    Sim s(1, 45);
    CHECK(s.Until([&] { return !s.cafe.orders.empty(); }, 4 * 60));
    s.NoMore();
    FakeCafe::Order const o = s.cafe.orders.front();
    s.Take(o.id);
    s.Tick(8);                                           // on its way to the pickup spot
    CHECK(s.PhaseOf(o.guid) == Phase::ToPickup);
    s.in.open = 2;
    s.Tick(1);
    Vec3 const stopped = s.At(o.guid);
    CHECK(!s.world.Moving(o.guid));
    uint32_t const clock = s.engine->Clock();
    s.Tick(4 * 90);                                      // a minute and a half of danger
    CHECK(Dist2d(s.At(o.guid), stopped) < 1e-4f);
    CHECK_EQN(s.engine->Clock(), clock);
    CHECK(s.world.teleports.empty());                    // the stuck timer did not run
    CHECK_EQN(s.engine->Alive(), 1u);                    // nothing spawned
    s.in.open = 1;
    s.Tick(1);
    CHECK(s.world.Moving(o.guid));                       // it walks on from where it stood
    CHECK(s.Until([&] { return s.PhaseOf(o.guid) == Phase::Pickup; }, 4 * 20));
    s.Serve(o.id);
    CHECK(s.Until([&] { return s.PhaseOf(o.guid) == Phase::Seated; }, 4 * 30));
    uint32_t const until = s.ByGuid(o.guid)->until;
    s.in.open = 2;
    s.Tick(4 * 120);
    CHECK(s.PhaseOf(o.guid) == Phase::Seated);
    s.in.open = 1;
    s.Tick(1);
    CHECK_EQN(s.ByGuid(o.guid)->until, until);           // the engine's clock: the sit time is not used up
    CHECK(s.Until([&] { return s.PhaseOf(o.guid) == Phase::Leaving; }, 4 * 80));
}

TEST("crowd: closed: everyone walks out, the NPC cups go, nobody comes; a player's cup stays")
{
    Sim s(1, 46);
    s.in.baristas = 4;
    CHECK(s.Until([&] { return s.cafe.orders.size() >= 2; }, 4 * 90));
    FakeCafe::Order const a = s.cafe.orders[0];
    s.Take(a.id);
    CHECK(s.Until([&] { return s.PhaseOf(a.guid) == Phase::Pickup; }, 4 * 20));
    s.Serve(a.id);                                       // its cup is on the counter now
    s.engine->PlaceCounterCup(800, 909350);              // and a ready player order's
    CHECK_EQN(s.world.gos.size(), 2u);
    s.in.open = 4;
    s.Tick(1);
    for (Customer const& c : s.engine->Customers())
        CHECK(c.phase == Phase::Leaving || c.phase == Phase::Gone);
    CHECK_EQN(s.world.gos.size(), 1u);                   // the player's cup is Cafe's to refund and remove
    CHECK(s.engine->Owns(800));
    CHECK(s.Until([&] { return s.engine->Alive() == 0; }, 4 * 90));
    s.Tick(4 * 120);
    CHECK_EQN(s.engine->Alive(), 0u);
    CHECK(s.cafe.gone.empty());
    s.engine->RemoveCounterCup(800);
    CHECK(s.world.gos.empty());
    // the site goes: everything is removed, nothing reported
    Sim d(1, 47);
    CHECK(d.Until([&] { return d.engine->Alive() >= 1; }, 4 * 60));
    d.engine->PlaceCounterCup(801, 909350);
    d.engine->QueueHouseJob({ 802, true, false, { 1, 3, 4, 25 }, 30000 });
    d.Tick(2);
    d.engine->Despawn();
    CHECK_EQN(d.engine->Alive(), 0u);
    CHECK(d.world.gos.empty());
    CHECK(!d.engine->Owns(801) && !d.engine->Owns(802));
    CHECK(d.cafe.gone.empty());
}

// ---- cups and table service ----

TEST("crowd: counter cups share the pickup spot, 0.25 yd apart along the counter, at most 6")
{
    Sim s(1, 51);
    s.NoMore();
    for (uint32_t id = 1; id <= 7; ++id)
        s.engine->PlaceCounterCup(id, 909350);
    CHECK_EQN(s.world.gos.size(), 6u);
    std::vector<float> ls;
    for (auto const& [g, go] : s.world.gos)
    {
        auto [f, l] = FL(Anchor, go.at.At());
        CHECK(Near(f, Bleakhold::CafeData::CounterCupF));
        ls.push_back(l);
        CHECK_EQN(go.lifetimeSec, CounterCupSec);
    }
    std::sort(ls.begin(), ls.end());
    for (std::size_t i = 0; i < ls.size(); ++i)
        CHECK(Near(ls[i], -1.6f + 0.25f * float(i)));
    CHECK(!s.engine->Owns(7));
    s.engine->PlaceCounterCup(3, 909350);                // again: nothing
    CHECK_EQN(s.world.gos.size(), 6u);
    s.engine->RemoveCounterCup(2);
    CHECK_EQN(s.world.gos.size(), 5u);
    s.engine->PlaceCounterCup(7, 909350);                // takes the freed place
    CHECK_EQN(s.world.gos.size(), 6u);
    CHECK(s.engine->Counter()[1].orderId == 7);
}

TEST("crowd: table service: the busser runs the cup to the seated player, then Delivered")
{
    Sim s(1, 52);
    s.NoMore();
    uint64_t const busser = s.staffGuid["staff_busser"];
    Chair const& chair = s.geo.chairs[5];
    s.PlayerAt(9001, chair.seat.At(), true);
    s.in.playerNear = true;
    s.in.open = 1;
    s.engine->PlaceCounterCup(700, 909350);
    s.engine->DeliverToSeat(700, 9001, 909350);
    s.engine->DeliverToSeat(700, 9001, 909350);          // asked twice: one delivery
    s.Tick(1);
    CHECK_EQN(s.engine->BusserOrder(), 700u);
    CHECK(s.world.walks.back().guid == busser && s.world.walks.back().run);
    CHECK(s.Until([&] { return s.world.gos.empty() || s.world.units[busser].hold != 0; }, 4 * 20));
    CHECK(s.Until([&] { return !s.cafe.delivered.empty(); }, 4 * 20));
    CHECK((s.cafe.delivered == std::vector<uint32_t>{ 700 }));
    CHECK(Dist2d(s.At(busser), chair.approach) <= ArriveYd);
    CHECK_EQN(s.world.units[busser].hold, 0u);
    // the player's cup on their table; it goes when they stand up
    CHECK_EQN(s.world.gos.size(), 1u);
    CHECK_EQN(s.world.gos.begin()->second.lifetimeSec, PlayerCupSec);
    s.PlayerAt(9001, chair.approach, false);
    s.Tick(2);
    CHECK(s.world.gos.empty());
    LegRules const r = AisleRules(s.geo);
    for (FakeWorld::WalkRec const& w : s.world.walks)
        if (w.guid == busser)
            CHECK_MSG(LegProblem(w.pts, r).empty(), LegProblem(w.pts, r));
}

TEST("crowd: table service: the player stands up on the way, and the cup goes back on the counter")
{
    Sim s(2, 53);
    s.NoMore();
    uint64_t const busser = s.staffGuid["staff_busser"];
    Chair const& chair = s.geo.chairs[11];
    s.PlayerAt(9002, chair.seat.At(), true);
    s.engine->PlaceCounterCup(710, 909351);
    s.engine->DeliverToSeat(710, 9002, 909351);
    CHECK(s.Until([&] { return s.world.units[busser].hold != 0; }, 4 * 20));
    CHECK_EQN(s.world.units[busser].hold, 2703u);        // the Orgrimmar mug
    CHECK(s.world.gos.empty());
    s.PlayerAt(9002, chair.approach, false);
    s.Tick(2);
    CHECK(s.cafe.delivered.empty());
    CHECK_EQN(s.world.units[busser].hold, 0u);
    CHECK_EQN(s.world.gos.size(), 1u);                   // back on the counter for the 15 yd pickup rule
    CHECK(s.engine->Owns(710));
    CHECK_EQN(s.engine->BusserOrder(), 0u);
    // Cafe removes it (picked up at the counter): gone
    s.engine->RemoveCounterCup(710);
    CHECK(s.world.gos.empty());
    // no busser in the world: delivered on a timer to a seated player
    Sim t(1, 54);
    t.NoMore();
    t.world.units[t.staffGuid["staff_busser"]].alive = false;
    t.PlayerAt(9003, t.geo.chairs[2].seat.At(), true);
    t.engine->PlaceCounterCup(720, 909350);
    t.engine->DeliverToSeat(720, 9003, 909350);
    CHECK(t.Until([&] { return !t.cafe.delivered.empty(); }, 4 * 10));
    CHECK_EQN(t.world.gos.size(), 1u);                   // the counter cup went, the table cup came
    auto [f, l] = FL(Anchor, t.world.gos.begin()->second.at.At());
    CHECK(f < -2.0f);
}

TEST("crowd: the busser's round: each table, a wipe, then home")
{
    Sim s(1, 55);
    uint64_t const busser = s.staffGuid["staff_busser"];
    s.world.players.push_back({ 1, s.geo.anchor.At(), false });
    s.Tick(4 * 120);
    CHECK(s.world.EmotesOf(busser, EmoteLoot) >= 4);
    LegRules const r = AisleRules(s.geo);
    for (FakeWorld::WalkRec const& w : s.world.walks)
        if (w.guid == busser)
            CHECK_MSG(LegProblem(w.pts, r).empty(), LegProblem(w.pts, r));
}

// ---- speech ----

TEST("crowd: the staff say Cafe's lines only (StaffSay); the crowd says the customers' and the owner's answer")
{
    Sim s(2, 61);
    s.NoMore();
    s.world.players.push_back({ 1, s.geo.anchor.At(), false });
    s.in.rush = true;
    s.Tick(4 * 600);                                   // ten minutes with a player near, a Rush on
    for (auto const& [g, t] : s.world.says)
        for (auto const& [role, sg] : s.staffGuid)
            CHECK_MSG(g != sg, role + " said " + t);     // idle lines and Rush shouts are Cafe's (spec 3.7.1)
    std::string const rushLine = "Out of the way, out of the way! Hot cups for the Horde!";
    s.engine->StaffSay("staff_busser", rushLine, false);
    CHECK_EQN(s.world.SaysOf(s.staffGuid["staff_busser"], rushLine), 1u);
    s.engine->StaffSay("staff_owner", "Coming. Don't rush me.", false);
    CHECK_EQN(s.world.SaysOf(s.staffGuid["staff_owner"], "Coming. Don't rush me."), 1u);
    std::size_t const before = s.world.says.size();
    s.engine->StaffSay("staff_nobody", "x", false);
    s.engine->StaffSay("staff_owner", "", false);
    CHECK_EQN(s.world.says.size(), before);
    // the staff member's grid is not loaded: nothing
    s.world.units[s.staffGuid["staff_head"]].alive = false;
    s.engine->StaffSay("staff_head", "Grukka's busy. I'll brew it. Stand back.", false);
    CHECK_EQN(s.world.says.size(), before);
}

// ---- a busy day ----

namespace
{
    // An automatic Cafe for the long runs: baristas take the front order after 3 s and serve it 9 s later; with
    // nobody on shift every order is the house's; now and then an order runs out of patience.
    struct AutoCafe
    {
        Sim& s;
        Rng rng;
        std::map<uint32_t, uint32_t> takenAt;

        AutoCafe(Sim& sim, uint64_t seed) : s(sim), rng(seed)
        {
            s.cafe.onArrived = [this](FakeCafe::Order& o) {
                if (s.in.baristas == 0)
                {
                    o.state = 'H';
                    s.cafe.Unqueue(o.id);
                    s.engine->HouseOrderTaken(o.id, "One, please.", "Coming right up, love.");
                    s.engine->QueueHouseJob({ o.id, false, false, { 7, 8, 16, 25 }, 30000 });
                }
            };
            s.cafe.onDone = [this](uint32_t id) { s.engine->OrderServed(id, 'G', "Thanks.", 2705, 909350); };
        }

        void Step()
        {
            if (s.in.baristas && !s.cafe.queue.empty() && takenAt.size() < 3)
            {
                FakeCafe::Order* o = s.cafe.Find(s.cafe.queue.front());
                if (o && s.now - o->since >= 3000)
                {
                    if (rng.Chance(10))
                    {
                        s.cafe.Unqueue(o->id);
                        o->state = 'X';
                        s.engine->OrderFailed(o->id, "Forget it.");
                    }
                    else
                    {
                        s.Take(o->id, "One, please.");
                        takenAt[o->id] = s.now;
                    }
                }
            }
            for (auto it = takenAt.begin(); it != takenAt.end();)
                if (s.now - it->second >= 9000)
                {
                    s.Serve(it->first, rng.Chance(50) ? 'P' : 'G');
                    it = takenAt.erase(it);
                }
                else
                    ++it;
        }
    };

    struct DayResult
    {
        std::size_t visits = 0, cupsTaken = 0, walks = 0, says = 0;
        std::size_t seated = 0, keg = 0, grouped = 0;   // customer-ticks in each state
        std::string digest;
    };

    DayResult BusyDay(uint8_t cafe, uint64_t seed, uint8_t baristas, bool rush, int minutes)
    {
        DayResult out;
        Sim s(cafe, seed);
        s.in.baristas = baristas;
        s.in.rush = rush;
        s.in.queueCap = rush ? 8 : 6;
        s.world.players.push_back({ 1, ToWorld(Anchor, -3.0f, 6.0f), false });
        AutoCafe autoCafe(s, seed * 31 + 7);
        LegRules const rules = AisleRules(s.geo);
        LegRules const work = WorkRules(s.geo);
        std::set<uint64_t> staff;
        for (auto const& [role, g] : s.staffGuid)
            staff.insert(g);
        // at each walk: the queue slots customers stand still at, but the walker's own
        s.world.onWalk = [&](FakeWorld::WalkRec const& w) {
            bool const isStaff = staff.count(w.guid) != 0;
            bool const isWorker = w.guid == s.staffGuid["staff_owner"] || w.guid == s.staffGuid["staff_head"];
            std::string const p = LegProblem(w.pts, isWorker ? work : rules);
            CHECK_MSG(p.empty(), "cafe " + std::to_string(cafe) + " seed " + std::to_string(seed) + ": " + p);
            if (isStaff)
                return;
            std::vector<Vec3> occupied;
            for (auto const& [g, u] : s.world.units)
            {
                if (g == w.guid || !u.alive || !u.customer || !u.path.empty())
                    continue;
                // in line and standing (a newcomer that has just arrived moves up in this same tick)
                Customer const* other = s.ByGuid(g);
                if (!other || (other->phase != Phase::Queue && other->phase != Phase::Taken &&
                               other->phase != Phase::Complain))
                    continue;
                for (Vec3 const& q : s.geo.queue)
                    if (Dist2d(u.pose.At(), q) < 0.05f)
                        occupied.push_back(q);
            }
            // a re-slot walks along the line through the slots others are leaving: only the ones still standing count
            std::string q = SlotProblem(w.pts, occupied, AisleClearance);
            if (!q.empty())
            {
                std::ostringstream m;
                Customer const* me = s.ByGuid(w.guid);
                m << " walker phase " << (me ? int(me->phase) : -1) << " slot " << (me ? me->slot : -9) << " pts";
                for (Vec3 const& wp : w.pts)
                {
                    auto [f, l] = FL(Anchor, wp);
                    m << " (" << f << "," << l << ")";
                }
                for (Customer const& c : s.engine->Customers())
                {
                    if (!c.guid || c.guid == w.guid)
                        continue;
                    auto [f, l] = FL(Anchor, s.At(c.guid));
                    m << " | other phase " << int(c.phase) << " slot " << c.slot << " at (" << f << "," << l << ")"
                      << (s.world.Moving(c.guid) ? " moving" : "");
                }
                q += m.str();
            }
            CHECK_MSG(q.empty(), "cafe " + std::to_string(cafe) + " seed " + std::to_string(seed) + ": " + q);
        };
        uint8_t const cap = AliveCap(Quick(), baristas, rush);
        for (int t = 0; t < minutes * 240; ++t)
        {
            autoCafe.Step();
            s.Tick();
            CHECK(s.engine->Alive() <= cap);
            // a chair reserved by one customer at most, and locked exactly while reserved
            std::map<int, int> chairs;
            for (Customer const& c : s.engine->Customers())
                if (c.chair >= 0)
                    ++chairs[c.chair];
            for (auto const& [ch, n] : chairs)
                CHECK(n == 1 && s.engine->ChairReserved(std::size_t(ch)));
            for (std::size_t i = 0; i < s.geo.chairs.size(); ++i)
                CHECK(s.engine->ChairReserved(i) == (s.world.locked[s.geo.chairs[i].spawnId]));
            // nobody stands on another, or inside a piece (but a sitter in its chair)
            std::vector<std::pair<uint64_t, Vec3>> standing;
            for (Customer const& c : s.engine->Customers())
                if (c.guid && s.world.Alive(c.guid) && !s.world.Moving(c.guid) && c.phase != Phase::Leaving)
                    standing.push_back({ c.guid, s.At(c.guid) });
            for (std::size_t i = 0; i < standing.size(); ++i)
                for (std::size_t j = i + 1; j < standing.size(); ++j)
                    if (Dist2d(standing[i].second, standing[j].second) <= 0.3f)
                    {
                        Customer const* x = s.ByGuid(standing[i].first);
                        Customer const* y = s.ByGuid(standing[j].first);
                        auto [f, l] = FL(Anchor, standing[i].second);
                        CHECK_MSG(false, "two customers on one spot, cafe " + std::to_string(cafe) + " seed " +
                                             std::to_string(seed) + " t " + std::to_string(t) + " at (" + Num(f) +
                                             "," + Num(l) + ") phases " + std::to_string(int(x->phase)) + "/" +
                                             std::to_string(int(y->phase)) + " slots " + std::to_string(x->slot) +
                                             "/" + std::to_string(y->slot) + " pickup " +
                                             std::to_string(x->pickupK) + "/" + std::to_string(y->pickupK) +
                                             " cupK " + std::to_string(x->cupK) + "/" + std::to_string(y->cupK));
                    }
            for (auto const& [g, p] : standing)
            {
                Customer const* c = s.ByGuid(g);
                for (std::size_t b = 0; b < s.geo.boxes.size(); ++b)
                    if (Inside(p, s.geo.boxes[b]))
                        CHECK_MSG(c && c->phase == Phase::Seated && c->chair >= 0 &&
                                      s.geo.chairs[std::size_t(c->chair)].box == int(b),
                                  "a customer stands inside footprint " + std::to_string(b));
            }
            for (Customer const& c : s.engine->Customers())
            {
                out.seated += c.phase == Phase::Seated;
                out.keg += c.phase == Phase::AtKeg;
                out.grouped += c.groupId != 0;
            }
        }
        // close: everyone leaves, every cup goes
        s.in.open = 4;
        CHECK(s.Until([&] { return s.engine->Alive() == 0; }, 4 * 120));
        s.Tick(40);
        CHECK(s.world.gos.empty());
        CHECK(s.cafe.gone.empty());
        CHECK(s.world.teleports.empty());
        out.visits = s.cafe.orders.size();
        out.cupsTaken = s.cafe.cups.size();
        out.walks = s.world.walks.size();
        out.says = s.world.says.size();
        std::ostringstream d;
        for (auto const& [g, t] : s.world.says)
            d << g << ':' << t << '|';
        for (FakeWorld::WalkRec const& w : s.world.walks)
            d << w.guid << '@' << w.pts.back().x << ',' << w.pts.back().y << '|';
        out.digest = d.str();
        return out;
    }
}

TEST("crowd: twenty busy minutes in both cities: every walk clear, caps kept, everyone leaves")
{
    for (uint8_t cafe : { uint8_t(1), uint8_t(2) })
    {
        DayResult const a = BusyDay(cafe, 100 + cafe, 2, false, 20);
        CHECK_MSG(a.visits >= 30, std::to_string(a.visits));
        CHECK(a.cupsTaken >= a.visits / 2);
        CHECK(a.seated > 0);
        DayResult const r = BusyDay(cafe, 200 + cafe, 4, true, 10);
        CHECK_MSG(r.visits >= 30, std::to_string(r.visits));
        CHECK(r.grouped > 0);
        DayResult const h = BusyDay(cafe, 300 + cafe, 0, false, 15);
        CHECK_MSG(h.visits >= 8, std::to_string(h.visits));
        CHECK(h.cupsTaken >= h.visits - 2);
        std::printf("  cafe %u: %zu/%zu/%zu visits (2 baristas, Rush with 4, house), %zu/%zu/%zu cups, "
                    "seated %zu, at kegs %zu, group %zu customer-ticks\n",
                    unsigned(cafe), a.visits, r.visits, h.visits, a.cupsTaken, r.cupsTaken, h.cupsTaken,
                    a.seated + r.seated + h.seated, a.keg + r.keg + h.keg, r.grouped);
    }
}

TEST("crowd: the same seed gives the same crowd")
{
    DayResult const a = BusyDay(1, 4242, 2, false, 6);
    DayResult const b = BusyDay(1, 4242, 2, false, 6);
    CHECK(a.digest == b.digest);
    CHECK(!a.digest.empty());
    DayResult const c = BusyDay(1, 4243, 2, false, 6);
    CHECK(a.digest != c.digest);
}

// ---- round-1 review fixes ----

TEST("crowd: Order.HouseWorkers lowered: the head barista's running job goes back to the queue and is made")
{
    Sim s(2, 61);
    s.NoMore();
    s.Tick(4);
    s.engine->QueueHouseJob({ 901, true, false, { 7, 9, 14, 25 }, 50000 });
    s.engine->QueueHouseJob({ 902, true, false, { 7, 9, 14, 25 }, 50000 });
    s.Tick(2);
    CHECK(s.engine->WorkerAt(0).busy && s.engine->WorkerAt(1).busy);
    CHECK_EQN(s.engine->WorkerAt(1).orderId, 902u);
    Config one = s.cfg;
    one.houseWorkers = 1;
    s.engine->Configure(one);
    s.Tick(1);
    CHECK(!s.engine->WorkerAt(1).busy);
    CHECK(s.engine->Owns(902));                          // before the fix: dropped, and Cafe kept it 'H' forever
    CHECK(!s.engine->HouseJobs().Empty() && s.engine->HouseJobs().Jobs().front().orderId == 902u);
    CHECK(s.Until([&] { return s.cafe.done.size() == 2; }, 4 * 200));
    CHECK((s.cafe.done == std::vector<uint32_t>{ 901, 902 }));
    // the second drink started again from its first step, on the owner
    bool restarted = false;
    for (FakeCafe::StepRec const& r : s.cafe.steps)
        if (r.order == 902 && r.step == 0 && r.worker == s.staffGuid["staff_owner"])
            restarted = true;
    CHECK(restarted);
}

TEST("crowd: PutBack: a dropped job goes to the front of its own kind")
{
    HouseQueue q;
    q.Add({ 1, false, false, { 1 }, 1000 });
    q.Add({ 2, true, false, { 1 }, 1000 });
    q.Add({ 3, true, true, { 1 }, 1000 });
    q.PutBack({ 4, true, false, { 1 }, 1000 });       // a player order: after the takeovers, before order 2
    q.PutBack({ 5, false, false, { 1 }, 1000 });      // an NPC order: before order 1
    std::vector<uint32_t> order;
    for (Job const& j : q.Jobs())
        order.push_back(j.orderId);
    CHECK((order == std::vector<uint32_t>{ 3, 4, 2, 5, 1 }));
}

TEST("crowd: a site spawned again: the house jobs and counter cups Cafe queues again are made and placed")
{
    Sim s(1, 62);
    s.NoMore();
    s.Tick(4);
    s.engine->QueueHouseJob({ 903, true, false, { 1, 3, 4, 25 }, 30000 });
    s.engine->PlaceCounterCup(904, 909350);
    s.Tick(8);
    CHECK(s.engine->Owns(903) && s.engine->Owns(904));
    // a layout change: the old engine goes (it tells Cafe nothing), a new one starts empty
    s.engine->Despawn();
    s.engine = std::make_unique<Engine>(s.geo, s.cfg, s.world, s.cafe, 63);
    CHECK(!s.engine->Owns(903) && !s.engine->Owns(904));
    // Cafe::SiteChanged queues what it still holds
    s.engine->QueueHouseJob({ 903, true, false, { 1, 3, 4, 25 }, 30000 });
    s.engine->PlaceCounterCup(904, 909350);
    CHECK(s.engine->Owns(903) && s.engine->Owns(904));
    CHECK(s.Until([&] { return !s.cafe.done.empty(); }, 4 * 200));
    CHECK((s.cafe.done == std::vector<uint32_t>{ 903 }));
    std::size_t cups = 0;
    for (auto const& cc : s.engine->Counter())
        cups += cc.orderId == 904;
    CHECK_EQN(cups, std::size_t(1));
}

TEST("crowd: a ready player cup on the counter keeps the player scan running, so a seated customer is seen")
{
    Sim s(1, 64);
    s.NoMore();
    s.in.playerNear = false;                             // the near flag is for spawning only
    Chair const& chair = s.geo.chairs[2];
    s.PlayerAt(9002, chair.seat.At(), true);
    s.Tick(2);
    CHECK(!s.engine->PlayerSeat(9002));                  // nothing to look for yet
    s.engine->PlaceCounterCup(905, 909350);
    s.Tick(1);
    CHECK(s.engine->PlayerSeat(9002) && *s.engine->PlayerSeat(9002) == chair.slot);
}

// Round-2 review fix: Cafe sends playerNear whatever Customer.Enable says (it used to send false with customers off).
TEST("crowd: Customer.Enable = 0: a player near spawns nobody, yet keeps the scan, so a Lingering Sip seat is seen")
{
    Sim s(1, 66);
    s.NoMore();                                          // Customer.Enable = 0
    s.in.baristas = 0;
    s.in.playerNear = true;
    s.engine->PlaceCounterCup(905, 909350);
    s.Tick(2);
    s.engine->RemoveCounterCup(905);                     // the player picked the order up at the counter
    Chair const& chair = s.geo.chairs[2];
    s.PlayerAt(9002, chair.seat.At(), true);
    int seen = 0;
    for (int i = 0; i < 280; ++i)                        // 70 s: the Lingering Sip needs 60 s seated
    {
        s.Tick(1);
        seen += s.engine->PlayerSeat(9002) && *s.engine->PlayerSeat(9002) == chair.slot;
    }
    CHECK_EQN(seen, 280);
    CHECK_EQN(s.engine->Alive(), std::size_t(0));        // nobody spawned
    // the flag false (the old Cafe side): nothing keeps the scan running, the seat is never seen
    s.in.playerNear = false;
    s.Tick(1);
    CHECK(!s.engine->PlayerSeat(9002));
}

TEST("crowd: SpawnNow (.cafe test customer): a chosen persona now, within the caps")
{
    Sim s(1, 65);
    CHECK(s.engine->SpawnNow(-1) == Engine::SpawnNowResult::Closed);   // before the first tick
    s.NoMore();
    s.Tick(1);
    int sw = -1, org = -1, group = -1;
    for (std::size_t i = 0; i < Bleakhold::CafeData::Personas.size(); ++i)
    {
        Bleakhold::CafeData::Persona const& p = Bleakhold::CafeData::Personas[i];
        if (!p.enabled || !HasLook(p))
            continue;
        if (p.cafeId == 1 && p.kind == Bleakhold::CafeData::PersonaKind::Named && sw < 0)
            sw = int(i);
        if (p.cafeId == 2 && org < 0)
            org = int(i);
        if (p.cafeId == 1 && p.kind == Bleakhold::CafeData::PersonaKind::Group && group < 0)
            group = int(i);
    }
    CHECK(sw >= 0 && org >= 0);
    CHECK(s.engine->SpawnNow(org) == Engine::SpawnNowResult::OtherCafe);
    CHECK(s.engine->SpawnNow(int(Bleakhold::CafeData::Personas.size())) == Engine::SpawnNowResult::Unavailable);
    CHECK(s.engine->SpawnNow(sw) == Engine::SpawnNowResult::Spawned);
    CHECK_EQN(s.engine->Alive(), 1u);
    s.Tick(2);
    CHECK(s.engine->Customers().front().persona == sw && s.engine->Customers().front().guid != 0);
    if (group >= 0)
    {
        CHECK(s.engine->SpawnNow(group) == Engine::SpawnNowResult::Spawned);
        CHECK_EQN(s.engine->Alive(), 4u);               // a Rush group comes with its members
    }
    // the caps hold: a full queue refuses
    s.in.queueCap = uint8_t(s.cafe.queue.size() + s.engine->WalkingIn());
    s.Tick(1);
    CHECK(s.engine->SpawnNow(-1) == Engine::SpawnNowResult::Full);
    s.in.open = 2;
    s.Tick(1);
    CHECK(s.engine->SpawnNow(-1) == Engine::SpawnNowResult::Closed);
}

int main(int, char**)
{
    return bhtest::RunAll();
}
