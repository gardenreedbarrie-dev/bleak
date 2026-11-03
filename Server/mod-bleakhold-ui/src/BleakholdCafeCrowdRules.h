/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The cafe (section 21): the NPC crowd's rules and its whole behaviour, with no AzerothCore, so the tests can run
 * it: spawn timing, the persona pick, the queue, the aisle graph and the legs over it, seats and keg spots, the
 * counter and table cups, the house workers' FIFO and its ETA, the busser and the stuck rule (spec 3.7). The staff
 * say Cafe's lines (StaffSay; their idle lines too), the customers their own. BleakholdCafeCrowd.cpp is the game
 * side: it turns Cafe's CafeSite into a Geometry, implements World with AzerothCore calls and forwards Hooks to
 * Cafe's CrowdSink.
 *
 * Engine runs one cafe from Cafe's world-thread tick. It only tells World what to do (summon, walk, say, sit, ...)
 * and polls it for arrival; every choice comes from the rules below, its own clock and its own seeded Rng, so a test
 * that drives it with a fake world sees the same crowd every run. The clock stops while the cafe is paused (open 2),
 * so every timer (sitting, house steps, the stuck rule, the next spawn) moves by the length of the pause.
 *
 * Events from Cafe (OrderTaken, OrderServed, ...) never call back into Cafe: only Update calls Hooks. An event that
 * arrives while Update runs (Cafe answering a hook) is kept and handled at the end of that Update, so a hook may
 * answer at once (NpcArrived, then HouseOrderTaken for the same customer) without seeing a half-done tick.
 *
 * Coordinates are world yards. In a cafe's own frame F is forward along the anchor's facing and L to its left
 * (spec 3.12.3). A footprint (Box) is halfD deep along its facing o and halfW wide across it, as the GameObject rows
 * of BleakholdCafeData.h give them.
 */

#ifndef BLEAKHOLD_CAFE_CROWD_RULES_H
#define BLEAKHOLD_CAFE_CROWD_RULES_H

#include "BleakholdCafeData.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <limits>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace Bleakhold::CrowdRules
{
    namespace Data = Bleakhold::CafeData;

    // Emotes (SharedDefines.h, enum Emote) and stand states (UnitDefines.h, UnitStandStateType). The game side checks
    // them against the core's enums with static_asserts.
    inline constexpr uint32_t EmoteTalk = 1;
    inline constexpr uint32_t EmoteBow = 2;
    inline constexpr uint32_t EmoteCheer = 4;
    inline constexpr uint32_t EmoteQuestion = 6;
    inline constexpr uint32_t EmoteLaugh = 11;
    inline constexpr uint32_t EmoteRude = 14;
    inline constexpr uint32_t EmotePoint = 25;
    inline constexpr uint32_t EmoteEatNoSheathe = 92;
    inline constexpr uint32_t EmoteYes = 273;
    inline constexpr uint32_t EmoteNo = 274;
    inline constexpr uint32_t EmoteLoot = 381;
    inline constexpr uint8_t StandStand = 0;
    inline constexpr uint8_t StandSitLowChair = 4;

    inline constexpr float AisleClearance = 0.8f;     // a customer's leg keeps this far from footprints and queue slots
    inline constexpr float WorkClearance = 0.3f;      // a staff leg behind the counter
    inline constexpr float MaxEdge = 8.5f;            // the longest straight leg between two points of a graph
    inline constexpr float ArriveYd = 0.4f;           // arrived: the spline is done and the creature this close
    inline constexpr float SeatPlayerYd = 0.6f;       // a sitting player this close to a seat has it
    inline constexpr float SpotPlayerYd = 0.6f;       // a player this close to a work spot stands on it
    inline constexpr float BehindYd = 0.6f;           // a worker whose station's spots are both taken stands here
    inline constexpr float PickupStepYd = 0.9f;       // customers waiting for drinks stand this far apart
    inline constexpr float NearCupYd = 0.5f;          // a customer this close to its cup takes it where it stands
    inline constexpr float WalkYdPerSec = 2.5f;       // speed_walk 1 (04_bleakhold_cafe_templates.sql)
    inline constexpr float RunYdPerSec = 7.0f;
    inline constexpr float PlayerScanYd = 30.0f;      // players the crowd looks at (seats, work spots, table service)
    inline constexpr uint32_t StuckBaseMs = 20000;    // no arrival this long after the leg's walking time: stuck
    inline constexpr uint32_t SummonMs = 900000;      // the summon's own safety timer: 15 minutes
    inline constexpr uint32_t FirstSpawnMs = 4000;    // a player comes near: the first customer after this
    inline constexpr uint32_t ResumeWalkMs = 2000;    // a walk that stopped short is sent again at most this often
    inline constexpr uint32_t CounterCupSec = 600;    // the lifetime of a cup on the counter (Cafe removes it first)
    inline constexpr uint32_t PlayerCupSec = 60;      // a seated player's table cup
    inline constexpr uint8_t MaxPickupWait = 8;       // places by the pickup spot

    // A deadline t has come at now (the same millisecond clock; safe across its wrap).
    inline bool Due(uint32_t now, uint32_t t)
    {
        return static_cast<int32_t>(now - t) >= 0;
    }

    // SplitMix64: small, fast and the same on every platform, so a seeded crowd repeats exactly.
    class Rng
    {
    public:
        explicit Rng(uint64_t seed = 1) : _s(seed) {}

        uint64_t Next()
        {
            uint64_t z = (_s += 0x9E3779B97F4A7C15ull);
            z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
            z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
            return z ^ (z >> 31);
        }

        // [0, n); 0 when n is 0.
        uint32_t Below(uint32_t n) { return n ? static_cast<uint32_t>(Next() % n) : 0; }
        // [lo, hi]
        uint32_t Range(uint32_t lo, uint32_t hi) { return hi <= lo ? lo : lo + Below(hi - lo + 1); }
        bool Chance(uint32_t pct) { return Below(100) < pct; }

    private:
        uint64_t _s;
    };

    // ---- geometry ----------------------------------------------------------------------------------------------

    struct Vec3
    {
        float x = 0, y = 0, z = 0;
    };

    struct Pose
    {
        float x = 0, y = 0, z = 0, o = 0;
        Vec3 At() const { return { x, y, z }; }
    };

    struct Box
    {
        float x = 0, y = 0, halfW = 0, halfD = 0, o = 0;
    };

    inline constexpr float Pi = 3.14159265358979f;

    inline float Norm(float o)
    {
        float const turn = 2 * Pi;
        o = std::fmod(o, turn);
        return o < 0 ? o + turn : o;
    }

    inline float Dist2d(Vec3 a, Vec3 b)
    {
        return std::hypot(a.x - b.x, a.y - b.y);
    }

    inline float AngleTo(Vec3 from, Vec3 to)
    {
        return Norm(std::atan2(to.y - from.y, to.x - from.x));
    }

    // from moved yd toward to (2D; a negative yd moves away), keeping from's height.
    inline Vec3 Toward(Vec3 from, Vec3 to, float yd)
    {
        float const d = Dist2d(from, to);
        if (d <= 0)
            return from;
        return { from.x + (to.x - from.x) / d * yd, from.y + (to.y - from.y) / d * yd, from.z };
    }

    // A point of a cafe's frame: f forward along the anchor's facing, l to its left, u up.
    inline Vec3 ToWorld(Pose const& anchor, float f, float l, float u = 0)
    {
        float const c = std::cos(anchor.o), s = std::sin(anchor.o);
        return { anchor.x + f * c - l * s, anchor.y + f * s + l * c, anchor.z + u };
    }

    // A point in a frame (f, l) of anchor.
    inline std::pair<float, float> ToFrame(Pose const& anchor, Vec3 p)
    {
        float const c = std::cos(anchor.o), s = std::sin(anchor.o), dx = p.x - anchor.x, dy = p.y - anchor.y;
        return { dx * c + dy * s, -dx * s + dy * c };
    }

    // (x, y) in a box's own frame: along its facing, then across.
    inline std::pair<float, float> BoxLocal(Box const& b, float x, float y)
    {
        float const c = std::cos(b.o), s = std::sin(b.o), dx = x - b.x, dy = y - b.y;
        return { dx * c + dy * s, -dx * s + dy * c };
    }

    inline float PointBoxDist(Vec3 p, Box const& b)
    {
        auto const [u, v] = BoxLocal(b, p.x, p.y);
        float const eu = std::max(std::fabs(u) - b.halfD, 0.0f), ev = std::max(std::fabs(v) - b.halfW, 0.0f);
        return std::hypot(eu, ev);
    }

    inline bool InsideBox(Vec3 p, Box const& b)
    {
        auto const [u, v] = BoxLocal(b, p.x, p.y);
        return std::fabs(u) < b.halfD && std::fabs(v) < b.halfW;
    }

    inline float PointSegDist(Vec3 p, Vec3 a, Vec3 b)
    {
        float const dx = b.x - a.x, dy = b.y - a.y, len2 = dx * dx + dy * dy;
        float t = len2 > 0 ? ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2 : 0.0f;
        t = std::clamp(t, 0.0f, 1.0f);
        return std::hypot(a.x + t * dx - p.x, a.y + t * dy - p.y);
    }

    // The 2D distance between the segment a-b and a box; 0 when the segment touches or enters it.
    inline float SegBoxDist(Vec3 a, Vec3 b, Box const& box)
    {
        auto const [au, av] = BoxLocal(box, a.x, a.y);
        auto const [bu, bv] = BoxLocal(box, b.x, b.y);
        // Liang-Barsky against the box's rectangle
        float t0 = 0, t1 = 1;
        float const du = bu - au, dv = bv - av;
        auto clip = [&t0, &t1](float p, float q) {
            if (p == 0)
                return q >= 0;
            float const r = q / p;
            if (p < 0)
            {
                if (r > t1)
                    return false;
                t0 = std::max(t0, r);
            }
            else
            {
                if (r < t0)
                    return false;
                t1 = std::min(t1, r);
            }
            return true;
        };
        if (clip(-du, au + box.halfD) && clip(du, box.halfD - au) && clip(-dv, av + box.halfW) &&
            clip(dv, box.halfW - av))
            return 0.0f;
        float d = std::min(PointBoxDist(a, box), PointBoxDist(b, box));
        float const c = std::cos(box.o), s = std::sin(box.o);
        for (float su : { -1.0f, 1.0f })
            for (float sv : { -1.0f, 1.0f })
            {
                float const u = su * box.halfD, v = sv * box.halfW;
                Vec3 const corner{ box.x + u * c - v * s, box.y + u * s + v * c, 0 };
                d = std::min(d, PointSegDist(corner, a, b));
            }
        return d;
    }

    // ---- the cafe as the crowd sees it -------------------------------------------------------------------------

    struct Chair
    {
        uint16_t slot = 0;
        uint16_t table = 0;          // its table's layout slot
        Pose seat;                   // seat 0 (a 1-slot chair's centre); o: the way the sitter faces (its table)
        Vec3 approach;               // the seat moved Data::ApproachYd away from its table
        uint8_t height = 0;          // the chair's Data1: a sitter's stand state is SIT_LOW_CHAIR + height
        uint8_t slots = 1;           // NPCs sit only on 1-slot seats
        uint64_t spawnId = 0;
        float size = 1.0f;           // the template's size: a bench's seats stand this far apart
        int box = -1;                // Finish: the footprint the seat stands in
        int tableTop = -1;           // Finish: its table in Geometry::tableTops
    };

    struct Keg
    {
        Vec3 spot;                   // where a customer stands to drink
        Vec3 approach;               // Finish: the spot moved Data::ApproachYd away from the keg table
        float facing = 0;            // Finish: toward the keg table
        int box = -1;                // Finish: the keg table's footprint
    };

    struct Station
    {
        char id = 0;
        std::array<Vec3, 2> spots{};
        Vec3 behind;                 // Finish: between the spots, BehindYd further from the station
        float objX = 0, objY = 0;
        uint16_t slot = 0;
    };

    struct StaffHome
    {
        std::string role;            // staff_owner, staff_head, staff_busser, staff_extra_1..3
        uint32_t entry = 0;
        uint64_t spawnId = 0;
        Pose home;
    };

    struct Geometry
    {
        uint8_t cafeId = 0;
        Pose anchor, orderSpot, pickupSpot, door;
        std::vector<Vec3> queue;     // queue_1..8; queue[0] is the front
        std::vector<Vec3> side;      // their side points (Finish fills them when missing)
        std::vector<Vec3> nodes;     // the aisle graph's nodes path_1..n
        std::vector<Chair> chairs;
        std::vector<Keg> kegs;
        std::vector<Vec3> tableTops; // where a cup stands on each table: z is the table's top
        std::vector<Box> boxes;      // every piece's footprint, floor decals left out
        std::array<Station, Data::StationCount> stations{};   // G E K C B S V
        std::vector<StaffHome> staff;
    };

    // The layout's side offset of queue slot i ([f, l] in the cafe's frame; spec 3.7.3: 1.5 yd toward the seating).
    inline std::pair<float, float> SideOffset(uint8_t cafeId, std::size_t i)
    {
        std::string const role = "queue_" + std::to_string(i + 1);
        for (Data::LayoutPiece const& p : Data::Layout)
            if (p.cafeId == cafeId && p.role == role)
                return { p.side[0], p.side[1] };
        return { 0.0f, -1.5f };
    }

    inline int NearestBox(std::vector<Box> const& boxes, Vec3 p, float within)
    {
        int best = -1;
        float bestD = within;
        for (std::size_t i = 0; i < boxes.size(); ++i)
        {
            float const d = Dist2d(p, { boxes[i].x, boxes[i].y, 0 });
            if (d <= bestD)
            {
                bestD = d;
                best = static_cast<int>(i);
            }
        }
        return best;
    }

    inline int NearestPoint(std::vector<Vec3> const& pts, Vec3 p)
    {
        int best = -1;
        float bestD = std::numeric_limits<float>::max();
        for (std::size_t i = 0; i < pts.size(); ++i)
        {
            float const d = Dist2d(p, pts[i]);
            if (d < bestD)
            {
                bestD = d;
                best = static_cast<int>(i);
            }
        }
        return best;
    }

    // The side points (spec 3.7.3): each queue slot moved SideYd off the queue line, perpendicular to it (the line
    // through its neighbours), toward the seating (the chairs' side of the line; with no chairs, the layout's side
    // offset). The layout's fixed offset [0, -1.5] is not perpendicular where the default line bends (queue_5..8), and
    // a step along it passes the next slot at 0.8 yd.
    inline constexpr float SideYd = 1.5f;

    inline std::vector<Vec3> SidePoints(Geometry const& g)
    {
        std::vector<Vec3> out;
        std::size_t const n = g.queue.size();
        float cx = 0, cy = 0;
        for (Chair const& c : g.chairs)
        {
            cx += c.seat.x;
            cy += c.seat.y;
        }
        bool const seating = !g.chairs.empty();
        if (seating)
        {
            cx /= float(g.chairs.size());
            cy /= float(g.chairs.size());
        }
        for (std::size_t i = 0; i < n; ++i)
        {
            Vec3 const at = g.queue[i];
            auto const [sf, sl] = SideOffset(g.cafeId, i);
            Vec3 const fixed = ToWorld({ at.x, at.y, at.z, g.anchor.o }, sf, sl);
            Vec3 const a = g.queue[i > 0 ? i - 1 : i];
            Vec3 const b = g.queue[i + 1 < n ? i + 1 : i];
            float dx = b.x - a.x, dy = b.y - a.y;
            float const len = std::hypot(dx, dy);
            if (len <= 0)
            {
                out.push_back(fixed);
                continue;
            }
            dx /= len;
            dy /= len;
            // the two perpendiculars; toward the seating, or the one nearer the layout's offset
            Vec3 const left{ at.x - dy * SideYd, at.y + dx * SideYd, at.z };
            Vec3 const right{ at.x + dy * SideYd, at.y - dx * SideYd, at.z };
            Vec3 const toward = seating ? Vec3{ cx, cy, at.z } : fixed;
            out.push_back(Dist2d(left, toward) < Dist2d(right, toward) ? left : right);
        }
        return out;
    }

    // What a Geometry derives from its placed points: side points, each chair's own footprint and table, each keg
    // spot's approach and facing, each station's behind point.
    inline void Finish(Geometry& g)
    {
        if (g.side.size() != g.queue.size())
            g.side = SidePoints(g);
        for (Chair& c : g.chairs)
        {
            c.box = -1;
            for (std::size_t i = 0; i < g.boxes.size(); ++i)
                if (InsideBox(c.seat.At(), g.boxes[i]))
                {
                    c.box = static_cast<int>(i);
                    break;
                }
            c.tableTop = NearestPoint(g.tableTops, c.seat.At());
        }
        for (Keg& k : g.kegs)
        {
            k.box = NearestBox(g.boxes, k.spot, 1.5f);
            if (k.box >= 0)
            {
                Vec3 const centre{ g.boxes[std::size_t(k.box)].x, g.boxes[std::size_t(k.box)].y, k.spot.z };
                k.facing = AngleTo(k.spot, centre);
                k.approach = Toward(k.spot, centre, -Data::ApproachYd);
            }
            else
            {
                k.facing = g.anchor.o;
                k.approach = k.spot;
            }
        }
        for (Station& s : g.stations)
        {
            Vec3 const mid{ (s.spots[0].x + s.spots[1].x) / 2, (s.spots[0].y + s.spots[1].y) / 2, s.spots[0].z };
            s.behind = Toward(mid, { s.objX, s.objY, mid.z }, -BehindYd);
        }
    }

    inline uint32_t RoleNumber(std::string_view role, std::string_view prefix)
    {
        if (role.substr(0, prefix.size()) != prefix)
            return 0;
        uint32_t n = 0;
        for (char ch : role.substr(prefix.size()))
        {
            if (ch < '0' || ch > '9')
                return 0;
            n = n * 10 + static_cast<uint32_t>(ch - '0');
        }
        return n;
    }

    // A piece's point [fwd, side] in its own frame (+X its front) to the world.
    inline Vec3 PieceToWorld(Vec3 piece, float pieceO, float fwd, float side)
    {
        float const c = std::cos(pieceO), s = std::sin(pieceO);
        return { piece.x + fwd * c - side * s, piece.y + fwd * s + side * c, piece.z };
    }

    // The default layout of a cafe (BleakholdCafeData.h) placed at anchor, as Cafe's site gives it after .cafe build
    // (the tests use this; the game builds its Geometry from the CafeSite).
    inline Geometry FromLayout(uint8_t cafeId, Pose const& anchor)
    {
        Geometry g;
        g.cafeId = cafeId;
        g.anchor = anchor;
        struct TableAt
        {
            uint16_t slot;
            Vec3 at;
        };
        std::vector<TableAt> tables;
        std::vector<Data::LayoutPiece const*> chairs;
        for (Data::LayoutPiece const& p : Data::Layout)
        {
            if (p.cafeId != cafeId)
                continue;
            Vec3 const at = ToWorld(anchor, p.f, p.l);
            float const o = Norm(anchor.o + p.turn);
            if (!p.creature && p.halfW > 0 && p.halfD > 0 && !p.decal)
                g.boxes.push_back({ at.x, at.y, p.halfW, p.halfD, o });
            if (p.role == "order_spot")
                g.orderSpot = { at.x, at.y, at.z, o };
            else if (p.role == "pickup_spot")
                g.pickupSpot = { at.x, at.y, at.z, o };
            else if (p.role == "door")
                g.door = { at.x, at.y, at.z, o };
            else if (uint32_t const q = RoleNumber(p.role, "queue_"))
            {
                if (g.queue.size() < q)
                    g.queue.resize(q);
                g.queue[q - 1] = at;
            }
            else if (uint32_t const n = RoleNumber(p.role, "path_"))
            {
                if (g.nodes.size() < n)
                    g.nodes.resize(n);
                g.nodes[n - 1] = at;
            }
            else if (RoleNumber(p.role, "table_"))
            {
                tables.push_back({ p.slot, at });
                g.tableTops.push_back({ at.x, at.y, anchor.z + p.topHeight });
            }
            else if (RoleNumber(p.role, "chair_"))
                chairs.push_back(&p);
            else if (RoleNumber(p.role, "kegtable_") && p.standCount)
                g.kegs.push_back({ PieceToWorld(at, o, p.stand[0], p.stand[1]), {}, 0, -1 });
            else if (p.station)
            {
                int const si = Data::StationIndex(p.station);
                if (si >= 0)
                {
                    Station& s = g.stations[std::size_t(si)];
                    s.id = p.station;
                    s.objX = at.x;
                    s.objY = at.y;
                    s.slot = p.slot;
                    for (std::size_t i = 0; i < 2; ++i)
                        s.spots[i] = PieceToWorld(at, o, p.work[i][0], p.work[i][1]);
                }
            }
            else if (p.creature)
                g.staff.push_back({ std::string(p.role), p.entry, 0, { at.x, at.y, at.z, o } });
        }
        for (Data::LayoutPiece const* p : chairs)
        {
            Chair c;
            c.slot = p->slot;
            c.table = p->link;
            Vec3 const at = ToWorld(anchor, p->f, p->l);
            float const o = Norm(anchor.o + p->turn);
            if (Data::GameObject const* go = Data::FindGameObject(p->entry))
            {
                c.height = go->seatHeight;
                c.slots = go->slots ? go->slots : 1;
                c.size = go->scale;
            }
            // seat 0 (the core's slot formula; the chair itself for one slot)
            float const rel = -c.size * float(c.slots - 1) / 2.0f;
            c.seat = { at.x + rel * std::cos(o + Pi / 2), at.y + rel * std::sin(o + Pi / 2), at.z, o };
            Vec3 table = at;
            for (TableAt const& t : tables)
                if (t.slot == p->link)
                    table = t.at;
            c.approach = Toward(c.seat.At(), table, -Data::ApproachYd);
            g.chairs.push_back(c);
        }
        Finish(g);
        return g;
    }

    // Whether p is on one of a chair's seats. GameObject::Use puts seat i of n at size * i - size * (n - 1) / 2 along
    // the chair's facing + pi/2 from the chair; Chair::seat is seat 0 (as Cafe's CafeSite gives it), so seat i is
    // size * i further along.
    inline bool OnSeat(Chair const& c, Vec3 p, float radius)
    {
        float const across = c.seat.o + Pi / 2;
        for (uint8_t i = 0; i < std::max<uint8_t>(c.slots, 1); ++i)
        {
            float const rel = c.size * float(i);
            Vec3 const seat{ c.seat.x + rel * std::cos(across), c.seat.y + rel * std::sin(across), c.seat.z };
            if (Dist2d(seat, p) <= radius)
                return true;
        }
        return false;
    }

    // The place k of the customers waiting for drinks: k 0 is the pickup spot, the others stand in two staggered
    // rows beside and behind it, away from the queue.
    inline Vec3 PickupWait(Geometry const& g, uint8_t k)
    {
        auto const [f0, l0] = ToFrame(g.anchor, g.pickupSpot.At());
        float const f = f0 - PickupStepYd * float(k % 2);
        float const l = l0 - PickupStepYd * float(k / 2) - PickupStepYd * 0.5f * float(k % 2);
        Vec3 v = ToWorld(g.anchor, f, l);
        v.z = g.pickupSpot.z;
        return v;
    }

    // Counter cup k on the counter top (spec 3.7.4: offset Data::CounterCupStepL along the counter each).
    inline Pose CounterCupPose(Geometry const& g, uint8_t k)
    {
        auto const [f0, l0] = ToFrame(g.anchor, g.pickupSpot.At());
        (void)f0;
        Vec3 const v = ToWorld(g.anchor, Data::CounterCupF, l0 + Data::CounterCupStepL * float(k));
        return { v.x, v.y, g.pickupSpot.z + Data::CounterCupU, g.anchor.o };
    }

    // Where a customer stands to take counter cup k: in front of it, at the pickup spot's distance from the counter.
    inline Vec3 CupFront(Geometry const& g, uint8_t k)
    {
        auto const [f0, l0] = ToFrame(g.anchor, g.pickupSpot.At());
        Vec3 v = ToWorld(g.anchor, f0, l0 + Data::CounterCupStepL * float(k));
        v.z = g.pickupSpot.z;
        return v;
    }

    // A seated customer's cup on its table: Data::TableCupYd from the table's centre toward the seat, on the top.
    inline Pose TableCupPose(Geometry const& g, Chair const& c)
    {
        if (c.tableTop < 0 || std::size_t(c.tableTop) >= g.tableTops.size())
            return { c.seat.x, c.seat.y, c.seat.z, c.seat.o };
        Vec3 const top = g.tableTops[std::size_t(c.tableTop)];
        Vec3 const at = Toward(top, c.seat.At(), Data::TableCupYd);
        return { at.x, at.y, top.z, c.seat.o };
    }

    // ---- the aisle graph and the legs over it (spec 3.7.3) -----------------------------------------------------

    // Whether the straight walk a -> b keeps `clearance` from every footprint. relaxA / relaxB: a (b) is an end of the
    // leg, not a graph node, and the footprints it stands next to (within the clearance, or the one given as ownA /
    // ownB: a chair by its approach point, the counter by the pickup spot) may be passed closer, but never entered,
    // unless the end stands inside it (a seat in its chair).
    inline bool SegmentClear(Vec3 a, Vec3 b, std::vector<Box> const& boxes, float clearance, bool relaxA, bool relaxB,
                             int ownA = -1, int ownB = -1)
    {
        for (std::size_t i = 0; i < boxes.size(); ++i)
        {
            Box const& box = boxes[i];
            float const d = SegBoxDist(a, b, box);
            if (d >= clearance)
                continue;
            bool const nearA = relaxA && (int(i) == ownA || PointBoxDist(a, box) < clearance);
            bool const nearB = relaxB && (int(i) == ownB || PointBoxDist(b, box) < clearance);
            if (!nearA && !nearB)
                return false;
            if (d > 0)
                continue;
            if ((nearA && InsideBox(a, box)) || (nearB && InsideBox(b, box)))
                continue;
            return false;
        }
        return true;
    }

    // Whether the walk a -> b keeps `clearance` from every occupied queue slot (the slots of the walker itself are not
    // in the list).
    inline bool BlockersClear(Vec3 a, Vec3 b, std::vector<Vec3> const& blockers, float clearance)
    {
        for (Vec3 const& c : blockers)
            if (PointSegDist(c, a, b) < clearance)
                return false;
        return true;
    }

    struct Graph
    {
        std::vector<Vec3> pts;       // the nodes; with a door, pts[0] is the door and pts[1] path_1
        std::vector<std::vector<std::pair<uint16_t, float>>> adj;
        bool hasDoor = false;
        float clearance = AisleClearance;
    };

    // Two nodes are joined when they are at most MaxEdge apart and the straight walk between them keeps the clearance
    // from every footprint; the door is joined to path_1 only, always (the GM places the door out of sight, so the way
    // to it is the GM's).
    inline Graph BuildGraph(std::vector<Vec3> const& nodes, std::optional<Vec3> door, std::vector<Box> const& boxes,
                            float clearance)
    {
        Graph g;
        g.hasDoor = door.has_value();
        g.clearance = clearance;
        if (door)
            g.pts.push_back(*door);
        g.pts.insert(g.pts.end(), nodes.begin(), nodes.end());
        g.adj.resize(g.pts.size());
        auto link = [&g](std::size_t i, std::size_t j) {
            float const d = Dist2d(g.pts[i], g.pts[j]);
            g.adj[i].push_back({ static_cast<uint16_t>(j), d });
            g.adj[j].push_back({ static_cast<uint16_t>(i), d });
        };
        std::size_t const first = door ? 1 : 0;
        if (door && g.pts.size() > 1)
            link(0, 1);
        for (std::size_t i = first; i < g.pts.size(); ++i)
            for (std::size_t j = i + 1; j < g.pts.size(); ++j)
                if (Dist2d(g.pts[i], g.pts[j]) <= MaxEdge &&
                    SegmentClear(g.pts[i], g.pts[j], boxes, clearance, false, false))
                    link(i, j);
        return g;
    }

    // The nodes no edge reaches (a .cafe status warning).
    inline std::vector<std::size_t> IsolatedNodes(Graph const& g)
    {
        std::vector<std::size_t> out;
        for (std::size_t i = 0; i < g.adj.size(); ++i)
            if (g.adj[i].empty())
                out.push_back(i);
        return out;
    }

    // Whether every node reaches every other.
    inline bool Connected(Graph const& g)
    {
        if (g.pts.empty())
            return true;
        std::vector<bool> seen(g.pts.size(), false);
        std::vector<std::size_t> todo{ 0 };
        seen[0] = true;
        while (!todo.empty())
        {
            std::size_t const i = todo.back();
            todo.pop_back();
            for (auto const& [j, d] : g.adj[i])
                if (!seen[j])
                {
                    seen[j] = true;
                    todo.push_back(j);
                }
        }
        return std::all_of(seen.begin(), seen.end(), [](bool b) { return b; });
    }

    struct Leg
    {
        std::vector<Vec3> points;    // the walk, from its start to its end
        bool ok = false;             // false: no clear way, and points is the straight line

        float Length() const
        {
            float l = 0;
            for (std::size_t i = 1; i < points.size(); ++i)
                l += Dist2d(points[i - 1], points[i]);
            return l;
        }
    };

    struct End
    {
        Vec3 p;
        int own = -1;                // a footprint this end stands next to whatever the distance (see SegmentClear)
        bool door = false;           // the graph's door node itself
    };

    // The shortest clear walk from -> to: straight, or over the graph's nodes. The first and the last segment may
    // pass closer to the footprints their end stands next to (SegmentClear); no segment passes an occupied queue slot.
    inline Leg Route(Graph const& g, End const& from, End const& to, std::vector<Box> const& boxes,
                     std::vector<Vec3> const& blockers = {})
    {
        float const clr = g.clearance;
        std::size_t const n = g.pts.size();
        std::size_t const s = from.door && g.hasDoor ? 0 : n;
        std::size_t const e = to.door && g.hasDoor ? 0 : n + 1;
        Leg leg;
        if (s == e)
        {
            leg.points = { from.p };
            leg.ok = true;
            return leg;
        }
        std::size_t const total = n + 2;
        auto pointOf = [&](std::size_t i) { return i == n ? from.p : i == n + 1 ? to.p : g.pts[i]; };
        std::vector<std::vector<std::pair<std::size_t, float>>> adj(total);
        for (std::size_t i = 0; i < n; ++i)
            for (auto const& [j, d] : g.adj[i])
                if ((g.hasDoor && (i == 0 || j == 0)) || BlockersClear(g.pts[i], g.pts[j], blockers, clr))
                    adj[i].push_back({ j, d });
        auto tie = [&](std::size_t a, std::size_t b, bool relaxA, bool relaxB, int ownA, int ownB) {
            Vec3 const pa = pointOf(a), pb = pointOf(b);
            float const d = Dist2d(pa, pb);
            if (d > MaxEdge || !SegmentClear(pa, pb, boxes, clr, relaxA, relaxB, ownA, ownB) ||
                !BlockersClear(pa, pb, blockers, clr))
                return;
            adj[a].push_back({ b, d });
            adj[b].push_back({ a, d });
        };
        std::size_t const firstNode = g.hasDoor ? 1 : 0;
        if (s == n)
            for (std::size_t v = firstNode; v < n; ++v)
                tie(n, v, true, false, from.own, -1);
        if (e == n + 1)
            for (std::size_t v = firstNode; v < n; ++v)
                tie(v, n + 1, false, true, -1, to.own);
        if (s == n && e == n + 1)
            tie(n, n + 1, true, true, from.own, to.own);
        std::vector<float> dist(total, std::numeric_limits<float>::max());
        std::vector<std::size_t> prev(total, total);
        std::vector<bool> done(total, false);
        dist[s] = 0;
        for (;;)
        {
            std::size_t u = total;
            for (std::size_t i = 0; i < total; ++i)
                if (!done[i] && dist[i] < std::numeric_limits<float>::max() && (u == total || dist[i] < dist[u]))
                    u = i;
            if (u == total || u == e)
                break;
            done[u] = true;
            for (auto const& [v, d] : adj[u])
                if (dist[u] + d < dist[v])
                {
                    dist[v] = dist[u] + d;
                    prev[v] = u;
                }
        }
        if (dist[e] == std::numeric_limits<float>::max())
        {
            leg.points = { from.p, to.p };
            return leg;
        }
        std::vector<Vec3> rev;
        for (std::size_t i = e; i != total; i = prev[i])
            rev.push_back(pointOf(i));
        leg.points.assign(rev.rbegin(), rev.rend());
        leg.ok = true;
        return leg;
    }

    // What is left of a walk that stopped at p: p, then the points after the segment p is nearest to.
    inline std::vector<Vec3> Remainder(std::vector<Vec3> const& points, Vec3 p)
    {
        std::vector<Vec3> out{ p };
        if (points.size() < 2)
        {
            if (!points.empty())
                out.push_back(points.back());
            return out;
        }
        std::size_t best = 1;
        float bestD = std::numeric_limits<float>::max();
        for (std::size_t i = 1; i < points.size(); ++i)
        {
            float const d = PointSegDist(p, points[i - 1], points[i]);
            if (d < bestD)
            {
                bestD = d;
                best = i;
            }
        }
        out.insert(out.end(), points.begin() + std::ptrdiff_t(best), points.end());
        return out;
    }

    // How long a leg may take before the customer counts as stuck: StuckBaseMs after its walking time and a half.
    inline uint32_t StuckLimitMs(float lengthYd, bool run)
    {
        float const speed = run ? RunYdPerSec : WalkYdPerSec;
        return StuckBaseMs + static_cast<uint32_t>(lengthYd / speed * 1500.0f);
    }

    // The worker graph: every station's spots and behind point and the house workers' homes, joined like the aisle
    // graph but with WorkClearance (the space behind the counter is narrow).
    inline Graph BuildWorkGraph(Geometry const& g)
    {
        std::vector<Vec3> pts;
        for (Station const& s : g.stations)
        {
            if (!s.id)
                continue;
            pts.push_back(s.spots[0]);
            pts.push_back(s.spots[1]);
            pts.push_back(s.behind);
        }
        for (StaffHome const& h : g.staff)
            if (h.role == "staff_owner" || h.role == "staff_head")
                pts.push_back(h.home.At());
        return BuildGraph(pts, std::nullopt, g.boxes, WorkClearance);
    }

    // ---- seats (spec 3.7.4) ------------------------------------------------------------------------------------

    enum class SeatKind : uint8_t
    {
        None,                        // nowhere free: leave at once, sipping
        Chair,
        Keg
    };

    struct SeatPick
    {
        SeatKind kind = SeatKind::None;
        int index = -1;
    };

    // The nearest 1-slot chair to `from` that is neither reserved nor taken by a player; else the nearest free keg
    // spot; else none.
    inline SeatPick PickSeat(Geometry const& g, Vec3 from, std::vector<bool> const& reserved,
                             std::vector<bool> const& playerTaken, std::vector<bool> const& kegTaken)
    {
        SeatPick pick;
        float best = std::numeric_limits<float>::max();
        for (std::size_t i = 0; i < g.chairs.size(); ++i)
        {
            if (g.chairs[i].slots != 1 || (i < reserved.size() && reserved[i]) ||
                (i < playerTaken.size() && playerTaken[i]))
                continue;
            float const d = Dist2d(from, g.chairs[i].seat.At());
            if (d < best)
            {
                best = d;
                pick = { SeatKind::Chair, static_cast<int>(i) };
            }
        }
        if (pick.kind == SeatKind::Chair)
            return pick;
        for (std::size_t i = 0; i < g.kegs.size(); ++i)
        {
            if (i < kegTaken.size() && kegTaken[i])
                continue;
            float const d = Dist2d(from, g.kegs[i].spot);
            if (d < best)
            {
                best = d;
                pick = { SeatKind::Keg, static_cast<int>(i) };
            }
        }
        return pick;
    }

    // ---- personas and spawning (spec 2.7, 3.7.2) ---------------------------------------------------------------

    struct PersonaTrack
    {
        uint8_t alive = 0;           // customers of this persona now (a Rush group counts its members)
        bool left = false;           // one has left since the server started
        uint32_t leftMs = 0;         // when the last one left
    };

    using Tracks = std::array<PersonaTrack, Data::Personas.size()>;

    inline bool HasLook(Data::Persona const& p)
    {
        return p.displayCount > 0 && p.displays[0] != 0;
    }

    // A named persona may come: enabled, with a look, none alive, its cooldown over, and no child during the Rush.
    inline bool NamedEligible(Data::Persona const& p, PersonaTrack const& t, uint32_t now, uint32_t cooldownMs,
                              bool rush)
    {
        return p.kind == Data::PersonaKind::Named && p.enabled && HasLook(p) && t.alive == 0 && !(rush && p.child) &&
               (!t.left || static_cast<uint32_t>(now - t.leftMs) >= cooldownMs);
    }

    struct Pick
    {
        int persona = -1;            // index into Data::Personas, or -1: nobody comes now
        uint8_t members = 0;         // 3 for a Rush group, else 1
    };

    // The persona of the next spawn: during the Rush a 25% chance of the cafe's Rush group when room >= 3 (free queue
    // slots and alive room); then half named (one of the eligible, uniformly), half generic (adults 4 : children 1,
    // no children during the Rush). Either half falls back to the other when it has nobody.
    inline Pick PickPersona(uint8_t cafeId, bool rush, uint8_t room, uint32_t now, uint32_t cooldownMs,
                            Tracks const& tracks, Rng& rng)
    {
        Pick pick;
        if (room == 0)
            return pick;
        std::vector<int> groups, named, adults, children;
        for (std::size_t i = 0; i < Data::Personas.size(); ++i)
        {
            Data::Persona const& p = Data::Personas[i];
            if (p.cafeId != cafeId || !p.enabled || !HasLook(p))
                continue;
            int const idx = static_cast<int>(i);
            switch (p.kind)
            {
                case Data::PersonaKind::Group:
                    if (tracks[i].alive == 0 && p.groupSize > 0)
                        groups.push_back(idx);
                    break;
                case Data::PersonaKind::Named:
                    if (NamedEligible(p, tracks[i], now, cooldownMs, rush))
                        named.push_back(idx);
                    break;
                case Data::PersonaKind::Generic:
                    adults.push_back(idx);
                    break;
                case Data::PersonaKind::Child:
                    if (!rush)
                        children.push_back(idx);
                    break;
            }
        }
        // the dice are always thrown in the same order, so a seed gives the same crowd whatever is eligible
        bool const groupRoll = rng.Chance(25);
        bool const namedRoll = rng.Chance(50);
        uint32_t const genericRoll = rng.Below(5);
        uint32_t const choice = rng.Below(1000);
        if (rush && room >= 3 && groupRoll && !groups.empty())
        {
            int const g = groups[choice % groups.size()];
            pick.persona = g;
            pick.members = std::min<uint8_t>(Data::Personas[std::size_t(g)].groupSize, 3);
            return pick;
        }
        auto generic = [&]() -> int {
            if (!children.empty() && (adults.empty() || genericRoll == 0))
                return children[choice % children.size()];
            if (!adults.empty())
                return adults[choice % adults.size()];
            return -1;
        };
        int chosen = -1;
        if (namedRoll && !named.empty())
            chosen = named[choice % named.size()];
        else
            chosen = generic();
        if (chosen < 0 && !named.empty())
            chosen = named[choice % named.size()];
        if (chosen >= 0)
        {
            pick.persona = chosen;
            pick.members = 1;
        }
        return pick;
    }

    struct Config
    {
        bool customers = true;                  // BleakholdUi.Cafe.Customer.Enable
        uint32_t intervalMs = 30000;            // Customer.IntervalSec
        uint32_t jitterMs = 8000;               // Customer.JitterSec
        uint32_t baristaFactorPct = 160;        // Customer.BaristaFactorPct
        uint8_t maxAlive = 6;                   // Customer.MaxAlive
        uint8_t rushMaxAlive = 8;               // Customer.RushMaxAlive
        uint8_t ambientMax = 2;                 // Customer.AmbientMax
        uint32_t sitMinMs = 40000;              // Customer.SitMinSec
        uint32_t sitMaxMs = 70000;              // Customer.SitMaxSec
        uint32_t drinkSpell = 0;                // Customer.DrinkSpell: 0 = the eat emote every 6-10 s
        uint32_t namedCooldownMs = 600000;      // Customer.NamedCooldownSec
        uint8_t houseWorkers = 2;               // Order.HouseWorkers (owner, then head barista)
        uint32_t houseBaseMs = 30000;           // Order.HouseBaseSec: for the ETA of an order not made yet
        uint32_t housePerLineMs = 5000;         // Order.HousePerLineSec
    };

    // One spawn every IntervalSec / BaristaFactor^(min(baristas, 4) - 1) +- jitter, x2 with nobody on shift (ambient),
    // / 2.5 during the Rush; never under 3 s.
    inline uint32_t ArrivalIntervalMs(Config const& c, uint8_t baristas, bool rush, int32_t jitterMs)
    {
        double base = double(c.intervalMs);
        if (baristas == 0)
            base *= 2.0;
        else
        {
            double const factor = double(std::max<uint32_t>(c.baristaFactorPct, 100)) / 100.0;
            base /= std::pow(factor, double(std::min<int>(baristas, 4) - 1));
        }
        double v = base + double(jitterMs);
        if (rush)
            v /= 2.5;
        return static_cast<uint32_t>(std::max(3000.0, std::round(v)));
    }

    // Customers alive at once (seated and leaving ones count): MaxAlive, RushMaxAlive during the Rush, and with nobody
    // on shift at most AmbientMax.
    inline uint8_t AliveCap(Config const& c, uint8_t baristas, bool rush)
    {
        uint8_t cap = rush ? c.rushMaxAlive : c.maxAlive;
        if (baristas == 0)
            cap = std::min(cap, c.ambientMax);
        return cap;
    }

    // ---- house jobs (spec 3.7.5) -------------------------------------------------------------------------------

    struct Job
    {
        uint32_t orderId = 0;
        bool playerOrder = false;    // player orders go before NPC orders
        bool front = false;          // a takeover: the very front (behind earlier takeovers)
        std::vector<uint8_t> actions;
        uint32_t minTotalMs = 0;     // HouseBaseSec + HousePerLineSec x lines
    };

    // A step's own time: a tap's duration, a timed step's gold centre (the house releases there).
    inline uint32_t StepMs(uint8_t action)
    {
        Data::Action const* a = Data::FindAction(action);
        if (!a)
            return 0;
        if (a->kind == 'H')
            return static_cast<uint32_t>(uint64_t(a->durMs) * (uint64_t(a->goldLo) + a->goldHi) / 2000);
        return a->durMs;
    }

    inline constexpr uint32_t HouseWalkMs = 2000;    // the ETA's guess for a walk to another station

    // What a job takes, for the ETA: its steps and walks, at least its minimum.
    inline uint32_t JobMs(Job const& j)
    {
        uint64_t sum = 0;
        char last = 0;
        for (uint8_t a : j.actions)
        {
            sum += StepMs(a);
            Data::Action const* act = Data::FindAction(a);
            char const st = act ? act->station : 0;
            if (st != last)
                sum += HouseWalkMs;
            last = st;
        }
        return static_cast<uint32_t>(std::max<uint64_t>(sum, j.minTotalMs));
    }

    // The padding: step i of n ends no earlier than jobStart + minTotal x (i + 1) / n, so the whole job lasts at least
    // minTotal, spread over its steps.
    inline uint32_t StepDeadline(uint32_t jobStart, uint32_t minTotalMs, std::size_t step, std::size_t steps)
    {
        if (steps == 0)
            return jobStart;
        return jobStart + static_cast<uint32_t>(uint64_t(minTotalMs) * (step + 1) / steps);
    }

    class HouseQueue
    {
    public:
        // Takeovers first (in their own order), then player orders, then NPC orders; FIFO inside each.
        void Add(Job job)
        {
            Remove(job.orderId);
            auto rank = [](Job const& j) { return j.front ? 0 : j.playerOrder ? 1 : 2; };
            int const r = rank(job);
            auto it = std::find_if(_q.begin(), _q.end(), [&](Job const& j) { return rank(j) > r; });
            _q.insert(it, std::move(job));
        }

        // A running job a worker had to drop (Order.HouseWorkers lowered): back at the front of its own kind, so it
        // is the next of them to be made.
        void PutBack(Job job)
        {
            Remove(job.orderId);
            auto rank = [](Job const& j) { return j.front ? 0 : j.playerOrder ? 1 : 2; };
            int const r = rank(job);
            auto it = std::find_if(_q.begin(), _q.end(), [&](Job const& j) { return rank(j) >= r; });
            _q.insert(it, std::move(job));
        }

        bool Remove(uint32_t orderId)
        {
            auto it = std::find_if(_q.begin(), _q.end(), [orderId](Job const& j) { return j.orderId == orderId; });
            if (it == _q.end())
                return false;
            _q.erase(it);
            return true;
        }

        std::optional<Job> Pop()
        {
            if (_q.empty())
                return std::nullopt;
            Job j = std::move(_q.front());
            _q.erase(_q.begin());
            return j;
        }

        std::vector<Job> const& Jobs() const { return _q; }
        bool Empty() const { return _q.empty(); }
        void Clear() { _q.clear(); }

    private:
        std::vector<Job> _q;
    };

    // The house ETA in seconds (CAFE, CAFM, CAFO): with W workers, the jobs ahead in the FIFO plus the remaining time
    // of the running jobs, divided by W and rounded up, plus the order's own job time. A running order: its remaining
    // time. No order, or one the house does not have: a new player order, which waits behind the takeovers and the
    // player orders only (newJobMs: its own time).
    inline uint32_t EtaSec(HouseQueue const& q, std::vector<std::pair<uint32_t, uint32_t>> const& running,
                           uint32_t workers, std::optional<uint32_t> orderId, uint32_t newJobMs)
    {
        workers = std::max<uint32_t>(workers, 1);
        uint64_t runningMs = 0;
        for (auto const& [id, remain] : running)
        {
            if (orderId && id == *orderId)
                return static_cast<uint32_t>((uint64_t(remain) + 999) / 1000);
            runningMs += remain;
        }
        bool queued = false;
        if (orderId)
            for (Job const& j : q.Jobs())
                if (j.orderId == *orderId)
                    queued = true;
        uint64_t aheadMs = 0;
        uint64_t ownMs = newJobMs;
        for (Job const& j : q.Jobs())
        {
            if (queued && j.orderId == *orderId)
            {
                ownMs = JobMs(j);
                break;
            }
            if (queued || j.front || j.playerOrder)
                aheadMs += JobMs(j);
        }
        uint64_t const wait = (aheadMs + runningMs + workers - 1) / workers;
        return static_cast<uint32_t>((wait + ownMs + 999) / 1000);
    }

    // The place a house worker works a station from: a work spot no player stands on (within SpotPlayerYd) and the
    // other worker does not use; both taken: 2, the station's behind point.
    inline int PickSpot(Station const& s, std::vector<Vec3> const& players, std::vector<Vec3> const& staffSpots)
    {
        for (int i = 0; i < 2; ++i)
        {
            Vec3 const spot = s.spots[std::size_t(i)];
            bool taken = false;
            for (Vec3 const& p : players)
                if (Dist2d(p, spot) <= SpotPlayerYd)
                    taken = true;
            for (Vec3 const& p : staffSpots)
                if (Dist2d(p, spot) <= 0.05f)
                    taken = true;
            if (!taken)
                return i;
        }
        return 2;
    }

    inline Vec3 SpotPoint(Station const& s, int spot)
    {
        return spot >= 0 && spot < 2 ? s.spots[std::size_t(spot)] : s.behind;
    }

    // ---- what the engine asks of the game, and tells Cafe ------------------------------------------------------

    struct PlayerNear
    {
        uint64_t guid = 0;
        Vec3 pos;
        bool sitting = false;        // a sit stand state (Unit::IsSitState)
    };

    // The game side (one cafe's map). Creatures and game objects are raw guids; a call on one that is gone does
    // nothing.
    class World
    {
    public:
        virtual ~World() = default;
        // a customer at `at` with that display (0: the template's); 0 when it failed
        virtual uint64_t Summon(uint32_t entry, Pose const& at, uint32_t display) = 0;
        virtual bool Alive(uint64_t guid) = 0;                 // in the world (a grid unload or its timer ends it)
        virtual bool Where(uint64_t guid, Pose& out) = 0;
        virtual bool Moving(uint64_t guid) = 0;                // its spline is not finalized
        // walks straight through points (after its own position), with no path finding; clears its emote state
        virtual void Walk(uint64_t guid, std::vector<Vec3> const& points, bool run) = 0;
        virtual void Stop(uint64_t guid) = 0;
        virtual void Teleport(uint64_t guid, Pose const& to) = 0;
        virtual void Face(uint64_t guid, float o) = 0;
        virtual void Despawn(uint64_t guid) = 0;
        virtual void Say(uint64_t guid, std::string_view text, bool yell) = 0;   // "emote:..." is a text emote
        virtual void Emote(uint64_t guid, uint32_t emote) = 0;                    // one-shot
        virtual void EmoteState(uint64_t guid, uint32_t state) = 0;               // a loop; 0 clears it
        virtual void Stand(uint64_t guid, uint8_t state) = 0;
        virtual void Hold(uint64_t guid, uint32_t item) = 0;                      // main hand; 0 empties it
        virtual void Cast(uint64_t guid, uint32_t spell) = 0;                     // cosmetic, never instant
        virtual void FinishChannel(uint64_t guid, uint32_t spell) = 0;            // ends it cleanly (no "Interrupted")
        virtual uint64_t Staff(uint64_t spawnId) = 0;          // a staff spawn's creature; 0 while its grid is unloaded
        virtual uint64_t PlaceGo(uint32_t entry, Pose const& at, uint32_t lifetimeSec) = 0;
        virtual void RemoveGo(uint64_t guid) = 0;
        virtual void LockChair(uint64_t spawnId, bool locked) = 0;                // GO_FLAG_NOT_SELECTABLE
        virtual void Players(Vec3 centre, float radius, std::vector<PlayerNear>& out) = 0;
    };

    // Cafe's side (its CrowdSink, bound to one cafe).
    class Hooks
    {
    public:
        virtual ~Hooks() = default;
        virtual uint32_t NpcArrived(uint8_t personaIdx, uint64_t creatureGuid, uint32_t groupId) = 0;
        virtual void NpcGone(uint32_t orderId) = 0;
        virtual void HouseStepStarted(uint32_t orderId, uint8_t stepIndex, uint8_t actionId, uint32_t durMs,
                                      uint64_t workerGuid) = 0;
        virtual void HouseDone(uint32_t orderId) = 0;
        virtual void CupTaken(uint32_t orderId) = 0;
        virtual void Delivered(uint32_t orderId) = 0;
    };

    struct Inputs
    {
        uint8_t open = 0;            // 1 open, 2 paused (freeze), else everyone leaves and nothing spawns
        uint8_t baristas = 0;
        bool rush = false;
        uint8_t queueCap = 6;
        uint8_t queueLen = 0;        // Cafe's 'W' orders, player and NPC
        bool playerNear = false;
        std::vector<uint64_t> queueOrder;   // the queued customers' guids in Cafe's order
    };

    // ---- the engine ------------------------------------------------------------------------------------------

    enum class Phase : uint8_t
    {
        Pending,                     // a Rush group's later member, not summoned yet
        WalkIn,                      // door -> its queue slot
        Queue,                       // in line (registered once Cafe gave it an order)
        Taken,                       // a barista took its order: it says it, then walks to the pickup spot
        ToOrder,                     // nobody on shift: to the order spot
        Ordering,                    // says its order to the owner, who answers
        ToPickup,
        Pickup,                      // waits for its drink
        ToCup,                       // steps in front of its cup on the counter
        TakeCup,
        ToSeat,                      // approach point, then the seat
        Seated,
        ToKeg,
        AtKeg,
        Complain,                    // says its complaint, then leaves
        Leaving,                     // to the door, where it vanishes
        Gone
    };

    // A walk in progress.
    struct Mover
    {
        std::vector<Vec3> route;     // from where it started to its end
        bool walking = false;
        bool run = false;
        uint32_t legStart = 0, legLimit = 0, resentAt = 0;
        uint8_t stuck = 0;           // times the stuck rule teleported it
    };

    enum class Move : uint8_t
    {
        Idle,                        // not walking
        Walking,
        Arrived,                     // reported once
        Stuck                        // no arrival within the leg's limit
    };

    struct Customer
    {
        uint32_t seq = 0;            // spawn order
        uint64_t guid = 0;
        int persona = -1;            // index into Data::Personas
        uint32_t display = 0;
        uint32_t groupId = 0;
        uint8_t member = 0;
        uint32_t summonAt = 0;
        Phase phase = Phase::Pending;
        uint8_t stage = 0;           // a step inside the phase (Queue: 1 = an ambient order, off to the order spot)
        // its order
        uint32_t orderId = 0;
        bool registered = false;     // NpcArrived answered
        bool live = false;           // Cafe holds its order: NpcGone when it vanishes before taking its cup
        bool lineSaid = false;
        bool served = false;
        char quality = 'G';
        std::string line, answer, thanks;
        uint32_t cupItem = 0, cupGo = 0;
        int cupK = -1;               // its cup's place on the counter
        // its places
        int slot = -1;               // the queue slot it heads for or stands at
        int pickupK = -1;            // its place by the pickup spot
        bool counter = false;        // it stands (or is about to) at standAt by the counter: nobody else goes there
        Vec3 standAt;
        int chair = -1, keg = -1;
        bool holding = false;
        uint64_t tableCup = 0;
        Mover mv;
        // timers (the engine's clock)
        uint32_t at = 0;             // the phase's next step
        uint32_t until = 0;          // seated or at a keg: when it gets up
        uint32_t nextSip = 0, nextIdle = 0;
        bool faceBack = false;       // an idle look round: face its way again at faceAt
        uint32_t faceAt = 0;
    };

    class Engine
    {
    public:
        struct CounterCup
        {
            uint32_t orderId = 0;    // 0: free
            uint64_t go = 0;
            uint32_t entry = 0;
            bool npc = false;        // an NPC's drink (it goes when the cafe closes); else a ready player order
        };

        Engine(Geometry geo, Config const& cfg, World& world, Hooks& hooks, uint64_t seed, uint32_t firstGroupId = 1)
            : _g(std::move(geo)), _cfg(cfg), _world(world), _hooks(hooks), _rng(seed),
              _nextGroup(firstGroupId ? firstGroupId : 1)
        {
            _aisles = BuildGraph(_g.nodes, _g.door.At(), _g.boxes, AisleClearance);
            _work = BuildWorkGraph(_g);
            _reserved.assign(_g.chairs.size(), false);
            _kegTaken.assign(_g.kegs.size(), false);
            for (std::size_t i = 0; i < _g.staff.size(); ++i)
            {
                std::string const& r = _g.staff[i].role;
                if (r == "staff_owner")
                    _workers[0].staff = int(i);
                else if (r == "staff_head")
                    _workers[1].staff = int(i);
                else if (r == "staff_busser")
                    _busser.staff = int(i);
            }
        }

        void Configure(Config const& cfg) { _cfg = cfg; }

        // A persona's cooldowns from an engine this one replaces (the site was spawned again).
        void Restore(Tracks const& tracks)
        {
            for (std::size_t i = 0; i < tracks.size(); ++i)
            {
                _tracks[i].left = tracks[i].left;
                _tracks[i].leftMs = tracks[i].leftMs;
            }
        }

        void Update(uint32_t now, Inputs const& in)
        {
            if (!_started)
            {
                _started = true;
                _lastNow = now;
                _clock = now;
                _nextSpawn = now + FirstSpawnMs;
                _relockAt = now;
                _busser.at = now + _rng.Range(3000, 8000);
                for (Delivery& d : _deliveries)
                    d.since = now;   // asked before the first tick: the clock starts now
            }
            uint32_t const dt = now - _lastNow;
            _lastNow = now;
            bool const paused = in.open == 2;
            if (!paused)
                _clock += dt;
            _in = in;
            _inUpdate = true;
            ScanPlayers();
            if (paused && !_paused)
                Freeze();
            else if (!paused && _paused)
                Thaw();
            _paused = paused;
            Vanished();
            if (!paused)
            {
                if (in.open != 1)
                    CloseOut();
                else
                    Spawn();
                std::vector<std::size_t> const line = AssignSlots();
                SummonPending();
                for (Customer& c : _customers)
                    Step(c);
                Register(line);
                for (Worker& w : _workers)
                    WorkerStep(w);
                BusserStep();
                Cups();
                if (Due(_clock, _relockAt))
                {
                    // a chair that came back from its spawn data (grid reload) lost the flag
                    _relockAt = _clock + 5000;
                    for (std::size_t i = 0; i < _reserved.size(); ++i)
                        if (_reserved[i])
                            _world.LockChair(_g.chairs[i].spawnId, true);
                }
            }
            _customers.erase(std::remove_if(_customers.begin(), _customers.end(),
                                 [](Customer const& c) { return c.phase == Phase::Gone; }), _customers.end());
            _inUpdate = false;
            std::vector<std::function<void()>> later;
            later.swap(_later);
            for (std::function<void()>& f : later)
                f();
        }

        // OnSiteDespawned: every customer and cup goes, seats are released, jobs stop. Nothing is reported to Cafe.
        void Despawn()
        {
            for (Customer& c : _customers)
            {
                if (c.guid)
                    _world.Despawn(c.guid);
                if (c.tableCup)
                    _world.RemoveGo(c.tableCup);
            }
            _customers.clear();
            for (CounterCup& cc : _counter)
                if (cc.go)
                    _world.RemoveGo(cc.go);
            _counter = {};
            for (LeftCup const& lc : _leftCups)
                _world.RemoveGo(lc.go);
            _leftCups.clear();
            for (PlayerCup const& pc : _playerCups)
                _world.RemoveGo(pc.go);
            _playerCups.clear();
            for (std::size_t i = 0; i < _reserved.size(); ++i)
                if (_reserved[i])
                    _world.LockChair(_g.chairs[i].spawnId, false);
            _reserved.assign(_g.chairs.size(), false);
            _kegTaken.assign(_g.kegs.size(), false);
            for (Worker& w : _workers)
            {
                if (w.guid && w.busy)
                    _world.EmoteState(w.guid, 0);
                Worker fresh;
                fresh.staff = w.staff;
                w = std::move(fresh);
            }
            if (_busser.guid && _busser.holding)
                _world.Hold(_busser.guid, 0);
            Busser fresh;
            fresh.staff = _busser.staff;
            _busser = std::move(fresh);
            _deliveries.clear();
            _house.Clear();
            _later.clear();
        }

        // Whether this cafe has the order: a customer's, a house job, a counter cup or a delivery.
        bool Owns(uint32_t orderId) const
        {
            if (!orderId)
                return false;
            for (Customer const& c : _customers)
                if (c.orderId == orderId)
                    return true;
            for (Job const& j : _house.Jobs())
                if (j.orderId == orderId)
                    return true;
            for (Worker const& w : _workers)
                if (w.busy && w.job.orderId == orderId)
                    return true;
            for (CounterCup const& cc : _counter)
                if (cc.orderId == orderId)
                    return true;
            for (Delivery const& d : _deliveries)
                if (d.orderId == orderId)
                    return true;
            return _busser.orderId == orderId;
        }

        // ---- events from Cafe (spec 3.7.1) ----

        // The customer says its order (once per order) and walks to the pickup spot; one stepping up the line says
        // it on the way and steps out once it stands in its slot.
        void OrderTaken(uint32_t orderId, std::string const& line)
        {
            if (Later([this, orderId, line] { OrderTaken(orderId, line); }))
                return;
            Customer* c = ByOrder(orderId);
            if (!c || !c->guid || (c->phase != Phase::Queue && c->phase != Phase::WalkIn))
                return;   // a returned order taken again: the customer waits at the pickup spot and says nothing
            bool const walking = c->mv.walking;
            if (!walking)
                FaceCounter(*c);
            if (!c->lineSaid && !line.empty())
            {
                _world.Say(c->guid, line, false);
                if (!walking)
                    _world.Emote(c->guid, EmoteTalk);
            }
            c->lineSaid = true;
            c->stage = 0;
            c->phase = Phase::Taken;
            c->at = _clock + 1500;
        }

        // The ticket went back to the queue: the customer stays where it is (at or on its way to the pickup spot).
        void OrderReturned(uint32_t orderId)
        {
            if (Later([this, orderId] { OrderReturned(orderId); }))
                return;
            if (Customer* c = ByOrder(orderId))
                c->lineSaid = true;
        }

        // The drink is on the counter: the customer steps to it, takes it, thanks, and goes to sit.
        void OrderServed(uint32_t orderId, char quality, std::string const& thanks, uint32_t cupItem, uint32_t cupGo)
        {
            if (Later([this, orderId, quality, thanks, cupItem, cupGo] {
                    OrderServed(orderId, quality, thanks, cupItem, cupGo);
                }))
                return;
            Customer* c = ByOrder(orderId);
            if (!c || !c->guid || c->served || c->phase >= Phase::TakeCup)
                return;
            c->served = true;
            c->quality = quality;
            c->thanks = thanks;
            c->cupItem = cupItem;
            c->cupGo = cupGo;
            c->cupK = CupPlaceFor(*c);
            if (c->cupK >= 0)
            {
                CounterCup& cc = _counter[std::size_t(c->cupK)];
                cc.orderId = orderId;
                cc.entry = cupGo;
                cc.npc = true;
                cc.go = cupGo ? _world.PlaceGo(cupGo, CounterCupPose(_g, uint8_t(c->cupK)), 120) : 0;
            }
            if (c->phase == Phase::Pickup || c->phase == Phase::Queue)
                GoToCup(*c);
            // taken (still in its slot), on its way to the pickup spot or ordering: it goes to the cup from there
        }

        // Patience ran out: the complaint, a NO or RUDE, and out.
        void OrderFailed(uint32_t orderId, std::string const& complaint)
        {
            if (Later([this, orderId, complaint] { OrderFailed(orderId, complaint); }))
                return;
            Customer* c = ByOrder(orderId);
            if (!c || c->phase >= Phase::TakeCup)
                return;
            c->live = false;
            if (!c->guid)
            {
                c->phase = Phase::Gone;
                return;
            }
            if (c->mv.walking && (c->phase == Phase::Queue || c->phase == Phase::WalkIn))
            {
                // stopped on its way up the line: it holds the slot it stands at until it leaves
                Halt(*c);
                int const near = NearestPoint(_g.queue, PoseOf(c->guid, SlotPoint(c->slot)).At());
                if (near >= 0)
                    c->slot = near;
            }
            else
                Halt(*c);
            if (!complaint.empty())
                _world.Say(c->guid, complaint, false);
            bool const child = c->persona >= 0 && Data::Personas[std::size_t(c->persona)].child;
            _world.Emote(c->guid, child || _rng.Chance(50) ? EmoteNo : EmoteRude);
            c->phase = Phase::Complain;
            c->at = _clock + 1800;
        }

        // Nobody on shift: the customer walks to the order spot, says its line, the owner answers, and it waits at the
        // pickup spot. A returned order the house takes over: the customer stays; the owner just answers.
        void HouseOrderTaken(uint32_t orderId, std::string const& line, std::string const& answer)
        {
            if (Later([this, orderId, line, answer] { HouseOrderTaken(orderId, line, answer); }))
                return;
            Customer* c = ByOrder(orderId);
            if (!c || !c->guid)
                return;
            c->line = line;
            c->answer = answer;
            if (c->phase == Phase::Queue || c->phase == Phase::WalkIn)
            {
                c->stage = 1;
                return;
            }
            if (!answer.empty() && c->phase >= Phase::ToPickup && c->phase <= Phase::Pickup)
                if (uint64_t const owner = StaffGuid("staff_owner"))
                    _world.Say(owner, answer, false);
        }

        void QueueHouseJob(Job const& job)
        {
            if (Later([this, job] { QueueHouseJob(job); }))
                return;
            for (Worker const& w : _workers)
                if (w.busy && w.job.orderId == job.orderId)
                    return;
            _house.Add(job);
        }

        void CancelHouseJob(uint32_t orderId)
        {
            if (Later([this, orderId] { CancelHouseJob(orderId); }))
                return;
            _house.Remove(orderId);
            for (Worker& w : _workers)
                if (w.busy && w.job.orderId == orderId)
                    StopJob(w);
        }

        uint32_t HouseEtaSec(std::optional<uint32_t> orderId) const
        {
            std::vector<std::pair<uint32_t, uint32_t>> running;
            uint32_t workers = 0;
            for (std::size_t i = 0; i < _workers.size(); ++i)
            {
                if (i >= _cfg.houseWorkers || _workers[i].staff < 0)
                    continue;
                ++workers;
                Worker const& w = _workers[i];
                if (w.busy)
                    running.push_back({ w.job.orderId, Due(_clock, w.estEnd) ? 1000u : w.estEnd - _clock });
            }
            uint32_t const lines = 5;   // an average drink's checklist
            return EtaSec(_house, running, workers, orderId, _cfg.houseBaseMs + _cfg.housePerLineMs * lines);
        }

        // A ready player order's cup on the counter (spec 3.7.4: the pickup spot, then 0.25 yd along it each, at most
        // Data::CounterCupMax).
        void PlaceCounterCup(uint32_t orderId, uint32_t cupGo)
        {
            if (Later([this, orderId, cupGo] { PlaceCounterCup(orderId, cupGo); }))
                return;
            for (CounterCup const& cc : _counter)
                if (cc.orderId == orderId)
                    return;
            int const k = FreeCounter();
            if (k < 0)
                return;
            CounterCup& cc = _counter[std::size_t(k)];
            cc.orderId = orderId;
            cc.entry = cupGo;
            cc.npc = false;
            cc.go = cupGo ? _world.PlaceGo(cupGo, CounterCupPose(_g, uint8_t(k)), CounterCupSec) : 0;
        }

        // Delivered at the counter or expired: the cup goes, and a busser bringing it stops.
        void RemoveCounterCup(uint32_t orderId)
        {
            if (Later([this, orderId] { RemoveCounterCup(orderId); }))
                return;
            for (CounterCup& cc : _counter)
                if (cc.orderId == orderId)
                {
                    if (cc.go)
                        _world.RemoveGo(cc.go);
                    cc = CounterCup{};
                }
            _deliveries.erase(std::remove_if(_deliveries.begin(), _deliveries.end(),
                                  [orderId](Delivery const& d) { return d.orderId == orderId; }), _deliveries.end());
            if (_busser.orderId == orderId)
                EndDelivery(false);
        }

        // Table service: the busser takes the counter cup to the seated player, then Delivered. Asked again for the
        // same order while it is under way: nothing.
        void DeliverToSeat(uint32_t orderId, uint64_t playerGuid, uint32_t cupGo)
        {
            if (Later([this, orderId, playerGuid, cupGo] { DeliverToSeat(orderId, playerGuid, cupGo); }))
                return;
            if (_busser.orderId == orderId)
                return;
            for (Delivery const& d : _deliveries)
                if (d.orderId == orderId)
                    return;
            _deliveries.push_back({ orderId, playerGuid, cupGo, _clock });
        }

        // A staff member says Cafe's line now (the staff's lines, idle ones too, are Cafe's: spec 3.7.1).
        void StaffSay(std::string_view role, std::string const& text, bool yell)
        {
            if (text.empty())
                return;
            if (uint64_t const guid = StaffGuid(role))
                _world.Say(guid, text, yell);
        }

        bool SeatTakenByPlayer(uint16_t chairSlot) const
        {
            for (std::size_t i = 0; i < _g.chairs.size(); ++i)
                if (_g.chairs[i].slot == chairSlot)
                    return PlayerOn(i);
            return false;
        }

        std::optional<uint16_t> PlayerSeat(uint64_t playerGuid) const
        {
            int const i = PlayerChair(playerGuid);
            if (i < 0)
                return std::nullopt;
            return _g.chairs[std::size_t(i)].slot;
        }

        // .cafe test customer: a customer of `persona` (an index into Data::Personas; a Rush group comes with its
        // members) now, or of the persona the normal rules pick (persona < 0), within the queue room and the alive cap
        // of the last tick. The spawn clock is left as it is.
        enum class SpawnNowResult : uint8_t { Spawned, Closed, Full, OtherCafe, Unavailable };
        SpawnNowResult SpawnNow(int persona)
        {
            if (_in.open != 1 || !_started)
                return SpawnNowResult::Closed;
            uint8_t const cap = AliveCap(_cfg, _in.baristas, _in.rush);
            int const freeSlots = int(_in.queueCap) - int(_in.queueLen) - WalkingIn();
            int const room = std::min(freeSlots, int(cap) - static_cast<int>(_customers.size()));
            if (room <= 0)
                return SpawnNowResult::Full;
            Pick pick;
            if (persona < 0)
                pick = PickPersona(_g.cafeId, _in.rush, uint8_t(std::min(room, 255)), _clock, _cfg.namedCooldownMs,
                                   Current(), _rng);
            else
            {
                if (std::size_t(persona) >= Data::Personas.size())
                    return SpawnNowResult::Unavailable;
                Data::Persona const& p = Data::Personas[std::size_t(persona)];
                if (p.cafeId != _g.cafeId)
                    return SpawnNowResult::OtherCafe;
                if (!p.enabled || !HasLook(p) || (p.kind == Data::PersonaKind::Group && !p.groupSize))
                    return SpawnNowResult::Unavailable;
                pick.persona = persona;
                pick.members = p.kind == Data::PersonaKind::Group ? std::min<uint8_t>(p.groupSize, 3) : 1;
            }
            if (pick.persona < 0)
                return SpawnNowResult::Unavailable;
            if (int(pick.members) > room)
                return SpawnNowResult::Full;
            AddCustomers(pick);
            return SpawnNowResult::Spawned;
        }

        // ---- views for the tests and status lines ----

        Geometry const& Site() const { return _g; }
        Graph const& Aisles() const { return _aisles; }
        Graph const& WorkGraph() const { return _work; }
        std::vector<Customer> const& Customers() const { return _customers; }
        HouseQueue const& HouseJobs() const { return _house; }
        uint32_t Clock() const { return _clock; }
        uint32_t NextSpawn() const { return _nextSpawn; }
        Tracks const& PersonaTracks() const { return _tracks; }
        std::array<CounterCup, Data::CounterCupMax> const& Counter() const { return _counter; }
        bool ChairReserved(std::size_t i) const { return i < _reserved.size() && _reserved[i]; }
        bool KegTaken(std::size_t i) const { return i < _kegTaken.size() && _kegTaken[i]; }
        uint32_t BusserOrder() const { return _busser.orderId; }
        std::size_t Alive() const { return _customers.size(); }

        // Customers on their way in or in line without an order yet (queueLen + this < queueCap to spawn).
        int WalkingIn() const
        {
            int n = 0;
            for (Customer const& c : _customers)
                if (c.phase == Phase::Pending || c.phase == Phase::WalkIn || (c.phase == Phase::Queue && !c.registered))
                    ++n;
            return n;
        }

        struct WorkerView
        {
            bool busy = false;
            uint32_t orderId = 0;
            std::size_t step = 0;
            int station = -1, spot = -1;
            uint64_t guid = 0;
        };

        WorkerView WorkerAt(std::size_t i) const
        {
            WorkerView v;
            if (i >= _workers.size())
                return v;
            Worker const& w = _workers[i];
            v.busy = w.busy;
            v.orderId = w.job.orderId;
            v.step = w.step;
            v.station = w.station;
            v.spot = w.spot;
            v.guid = w.guid;
            return v;
        }

    private:
        enum class WorkState : uint8_t
        {
            Home,
            Walk,
            Work,
            Return
        };

        struct Worker
        {
            int staff = -1;          // its index in Geometry::staff, -1: no such staff member
            uint64_t guid = 0;       // this tick's creature; 0: its grid is not loaded (the job runs on its timer)
            bool busy = false;
            Job job;
            std::size_t step = 0;
            WorkState state = WorkState::Home;
            uint32_t jobStart = 0, releaseAt = 0, stepEnd = 0, estEnd = 0;
            bool released = false;   // a timed step's channel ended at the gold centre
            int station = -1, spot = -1;
            Vec3 target;
            Mover mv;
        };

        enum class BusState : uint8_t
        {
            Home,
            ToTable,
            Wipe,
            Return,
            ToCup,
            TakeCup,
            Carry,
            Serve
        };

        struct Busser
        {
            int staff = -1;
            uint64_t guid = 0;
            BusState state = BusState::Home;
            uint32_t at = 0;
            std::size_t nextTable = 0;
            int tablesLeft = 0;
            int table = -1;
            Mover mv;
            uint32_t orderId = 0;    // the delivery under way
            uint64_t player = 0;
            uint32_t cupGo = 0;
            int chair = -1;
            int cupK = -1;
            bool holding = false;
        };

        struct Delivery
        {
            uint32_t orderId;
            uint64_t player;
            uint32_t cupGo;
            uint32_t since;
        };

        struct LeftCup
        {
            uint64_t go;
            uint32_t until;
        };

        struct PlayerCup
        {
            uint32_t orderId;
            uint64_t player;
            int chair;
            uint64_t go;
            uint32_t until;
        };

        // An event while Update runs waits for its end.
        template<class F>
        bool Later(F&& f)
        {
            if (!_inUpdate)
                return false;
            _later.emplace_back(std::forward<F>(f));
            return true;
        }

        Customer* ByOrder(uint32_t orderId)
        {
            if (!orderId)
                return nullptr;
            for (Customer& c : _customers)
                if (c.orderId == orderId && c.phase != Phase::Gone)
                    return &c;
            return nullptr;
        }

        uint64_t StaffGuid(std::string_view role)
        {
            for (StaffHome const& s : _g.staff)
                if (s.role == role && s.spawnId)
                    return _world.Staff(s.spawnId);
            return 0;
        }

        // ---- players ----

        void ScanPlayers()
        {
            _players.clear();
            bool const working = _workers[0].busy || _workers[1].busy || !_house.Empty();
            // a ready player order's cup on the counter: Cafe asks PlayerSeat for its table service
            bool const playerCupWaits = std::any_of(_counter.begin(), _counter.end(),
                [](CounterCup const& cc) { return cc.orderId && !cc.npc; });
            if (_in.playerNear || working || playerCupWaits || !_customers.empty() || !_playerCups.empty() ||
                !_deliveries.empty() || _busser.orderId)
                _world.Players(_g.anchor.At(), PlayerScanYd, _players);
        }

        bool PlayerOn(std::size_t chair) const
        {
            for (PlayerNear const& p : _players)
                if (p.sitting && OnSeat(_g.chairs[chair], p.pos, SeatPlayerYd))
                    return true;
            return false;
        }

        int PlayerChair(uint64_t guid) const
        {
            for (PlayerNear const& p : _players)
            {
                if (p.guid != guid || !p.sitting)
                    continue;
                for (std::size_t i = 0; i < _g.chairs.size(); ++i)
                    if (OnSeat(_g.chairs[i], p.pos, SeatPlayerYd))
                        return int(i);
            }
            return -1;
        }

        std::vector<bool> PlayerTaken() const
        {
            std::vector<bool> t(_g.chairs.size(), false);
            for (std::size_t i = 0; i < t.size(); ++i)
                t[i] = PlayerOn(i);
            return t;
        }

        std::vector<Vec3> PlayerSpots() const
        {
            std::vector<Vec3> out;
            for (PlayerNear const& p : _players)
                out.push_back(p.pos);
            return out;
        }

        // ---- motion ----

        void Go(uint64_t guid, Mover& m, std::vector<Vec3> points, bool run)
        {
            if (points.size() == 1)
                points.push_back(points.front());
            m.route = std::move(points);
            m.walking = !m.route.empty();
            m.run = run;
            m.legStart = _clock;
            Leg l;
            l.points = m.route;
            m.legLimit = StuckLimitMs(l.Length(), run);
            m.resentAt = _clock;
            if (guid && m.walking)
                _world.Walk(guid, std::vector<Vec3>(m.route.begin() + 1, m.route.end()), run);
        }

        // Arrival is polled (spec 3.7.3): the spline done and within ArriveYd of the end. A walk that stopped short
        // is sent again from where it stands; no arrival within the leg's limit is Stuck. A creature not in the world
        // (staff on a timer) arrives at once.
        Move Poll(uint64_t guid, Mover& m)
        {
            if (!m.walking)
                return Move::Idle;
            if (!guid)
            {
                m.walking = false;
                return Move::Arrived;
            }
            Pose p;
            if (!_world.Where(guid, p))
                return Move::Walking;
            if (!_world.Moving(guid))
            {
                if (Dist2d(p.At(), m.route.back()) <= ArriveYd)
                {
                    m.walking = false;
                    return Move::Arrived;
                }
                if (Due(_clock, m.resentAt + ResumeWalkMs))
                {
                    m.resentAt = _clock;
                    std::vector<Vec3> const rest = Remainder(m.route, p.At());
                    _world.Walk(guid, std::vector<Vec3>(rest.begin() + 1, rest.end()), m.run);
                }
            }
            if (Due(_clock, m.legStart + m.legLimit))
                return Move::Stuck;
            return Move::Walking;
        }

        // The stuck rule's teleport to the leg's end (NearTeleportTo), facing along its last segment.
        void Jump(uint64_t guid, Mover& m)
        {
            Vec3 const end = m.route.back();
            float const o = m.route.size() >= 2 ? AngleTo(m.route[m.route.size() - 2], end) : 0.0f;
            if (guid)
                _world.Teleport(guid, { end.x, end.y, end.z, o });
            m.walking = false;
            ++m.stuck;
        }

        // A customer's walk ended: true once. Stuck the first time: teleported to the leg's end; the second time: it
        // goes (NpcGone while Cafe holds its order).
        bool Arrived(Customer& c)
        {
            switch (Poll(c.guid, c.mv))
            {
                case Move::Arrived:
                    return true;
                case Move::Stuck:
                    if (c.mv.stuck == 0)
                    {
                        Jump(c.guid, c.mv);
                        return true;
                    }
                    Vanish(c, true);
                    return false;
                default:
                    return false;
            }
        }

        // A staff walk ended (stuck: teleported to its end).
        bool StaffArrived(uint64_t guid, Mover& m)
        {
            switch (Poll(guid, m))
            {
                case Move::Idle:
                case Move::Arrived:
                    return true;
                case Move::Stuck:
                    Jump(guid, m);
                    return true;
                default:
                    return false;
            }
        }

        void Halt(Customer& c)
        {
            if (c.mv.walking && c.guid)
                _world.Stop(c.guid);
            c.mv.walking = false;
        }

        Pose PoseOf(uint64_t guid, Vec3 fallback)
        {
            Pose p{ fallback.x, fallback.y, fallback.z, 0 };
            if (guid)
                _world.Where(guid, p);
            return p;
        }

        // The queue slots customers stand at (or walk along to) now, but `self`'s.
        std::vector<Vec3> Blockers(Customer const* self) const
        {
            std::vector<Vec3> out;
            for (Customer const& c : _customers)
                if (&c != self && (c.phase == Phase::Queue || Holds(c)) && c.slot >= 0 &&
                    std::size_t(c.slot) < _g.queue.size())
                    out.push_back(_g.queue[std::size_t(c.slot)]);
            return out;
        }

        // A customer's leg from where it stands: `prefix` first (the side step out of the line, the step out of a
        // chair), then the route from the last of them.
        Leg Plan(Vec3 from, std::vector<Vec3> const& prefix, End to, Customer const* self, int ownFrom = -1)
        {
            Vec3 const start = prefix.empty() ? from : prefix.back();
            Leg leg = Route(_aisles, End{ start, ownFrom, false }, to, _g.boxes, Blockers(self));
            std::vector<Vec3> pts{ from };
            pts.insert(pts.end(), prefix.begin(), prefix.end());
            pts.insert(pts.end(), leg.points.begin() + 1, leg.points.end());
            leg.points = std::move(pts);
            return leg;
        }

        void Walk(Customer& c, Leg const& leg, bool run = false)
        {
            Go(c.guid, c.mv, leg.points, run);
        }

        void FaceCounter(Customer& c)
        {
            if (c.guid)
                _world.Face(c.guid, _g.anchor.o);
        }

        Vec3 SlotPoint(int slot) const
        {
            if (_g.queue.empty())
                return _g.orderSpot.At();
            return _g.queue[std::size_t(std::clamp(slot, 0, int(_g.queue.size()) - 1))];
        }

        void FaceQueue(Customer& c)
        {
            if (!c.guid)
                return;
            Vec3 const ahead = c.slot > 0 ? SlotPoint(c.slot - 1) : _g.orderSpot.At();
            _world.Face(c.guid, AngleTo(SlotPoint(c.slot), ahead));
        }

        // ---- the customers ----

        int FreeCounter() const
        {
            for (std::size_t k = 0; k < _counter.size(); ++k)
                if (!_counter[k].orderId)
                    return int(k);
            return -1;
        }

        // Where a customer stands by the counter now, or is about to: its place by the pickup spot, its cup's front,
        // the order spot.
        std::optional<Vec3> StandPoint(Customer const& c) const
        {
            if (c.phase == Phase::ToOrder || c.phase == Phase::Ordering)
                return _g.orderSpot.At();
            if (c.counter)
                return c.standAt;
            return std::nullopt;
        }

        bool StandClear(Customer const& self, Vec3 p) const
        {
            for (Customer const& c : _customers)
                if (&c != &self)
                    if (std::optional<Vec3> const at = StandPoint(c); at && Dist2d(*at, p) < 0.6f)
                        return false;
            return true;
        }

        // An NPC's cup goes to the first free place on the counter whose front nobody else stands at or steps to
        // (customers are wider than the 0.25 yd between cups); -1: it takes its drink where it stands.
        int CupPlaceFor(Customer const& self) const
        {
            for (std::size_t k = 0; k < _counter.size(); ++k)
            {
                if (!_counter[k].orderId && StandClear(self, CupFront(_g, uint8_t(k))))
                    return int(k);
            }
            return -1;
        }

        // The first place by the pickup spot nobody has or stands at.
        int FreePickup(Customer const& self) const
        {
            for (int k = 0; k < MaxPickupWait; ++k)
            {
                bool used = false;
                for (Customer const& c : _customers)
                    if (&c != &self && c.pickupK == k)
                        used = true;
                if (!used && StandClear(self, PickupWait(_g, uint8_t(k))))
                    return k;
            }
            return MaxPickupWait - 1;
        }

        // The personas alive now, with the cooldowns of those that left.
        Tracks Current() const
        {
            Tracks t = _tracks;
            for (PersonaTrack& p : t)
                p.alive = 0;
            for (Customer const& c : _customers)
                if (c.persona >= 0 && c.phase != Phase::Gone)
                    ++t[std::size_t(c.persona)].alive;
            return t;
        }

        // Spec 3.7.2: open, a player near, room in the queue (queueLen + walking in < queueCap) and under the alive
        // cap; one spawn per interval. A Rush group takes three places at once; its members follow each other in.
        void Spawn()
        {
            if (!_cfg.customers || !_in.playerNear)
            {
                if (!Due(_nextSpawn, _clock + FirstSpawnMs))
                    _nextSpawn = _clock + FirstSpawnMs;
                return;
            }
            if (!Due(_clock, _nextSpawn))
                return;
            uint8_t const cap = AliveCap(_cfg, _in.baristas, _in.rush);
            int const alive = static_cast<int>(_customers.size());
            int const freeSlots = int(_in.queueCap) - int(_in.queueLen) - WalkingIn();
            int const room = std::min(freeSlots, int(cap) - alive);
            if (room <= 0)
            {
                _nextSpawn = _clock + 2000;   // look again soon: a customer leaving opens a place
                return;
            }
            Pick const pick = PickPersona(_g.cafeId, _in.rush, uint8_t(std::min(room, 255)), _clock,
                                          _cfg.namedCooldownMs, Current(), _rng);
            int32_t const jitter = int32_t(_rng.Range(0, 2 * _cfg.jitterMs)) - int32_t(_cfg.jitterMs);
            if (pick.persona < 0)
            {
                _nextSpawn = _clock + 5000;
                return;
            }
            _nextSpawn = _clock + ArrivalIntervalMs(_cfg, _in.baristas, _in.rush, jitter);
            AddCustomers(pick);
        }

        // The customers of a pick, out of the door from the next tick (a group's members 1.2 s apart).
        void AddCustomers(Pick const& pick)
        {
            Data::Persona const& p = Data::Personas[std::size_t(pick.persona)];
            uint32_t const groupId = pick.members > 1 ? _nextGroup++ : 0;
            for (uint8_t m = 0; m < pick.members; ++m)
            {
                Customer c;
                c.seq = _nextSeq++;
                c.persona = pick.persona;
                c.groupId = groupId;
                c.member = m;
                c.summonAt = _clock + 1200u * m;
                uint8_t const n = std::max<uint8_t>(p.displayCount, 1);
                c.display = p.kind == Data::PersonaKind::Named ? p.displays[0] : p.displays[_rng.Below(n)];
                _customers.push_back(std::move(c));
            }
        }

        // Out of the door, facing the way in, and over the graph to its slot (newcomers approach from the far end).
        void SummonPending()
        {
            for (Customer& c : _customers)
            {
                if (c.phase != Phase::Pending || !Due(_clock, c.summonAt))
                    continue;
                Data::Persona const& p = Data::Personas[std::size_t(c.persona)];
                Vec3 const first = _aisles.pts.size() > 1 ? _aisles.pts[1] : SlotPoint(0);
                Pose const at{ _g.door.x, _g.door.y, _g.door.z, AngleTo(_g.door.At(), first) };
                c.guid = _world.Summon(p.entry, at, c.display);
                if (!c.guid)
                {
                    c.phase = Phase::Gone;
                    continue;
                }
                c.phase = Phase::WalkIn;
                if (c.slot < 0)
                    c.slot = int(_g.queue.empty() ? 0 : _g.queue.size() - 1);
                Walk(c, Route(_aisles, End{ _g.door.At(), -1, true }, End{ SlotPoint(c.slot), -1, false }, _g.boxes,
                              Blockers(&c)));
            }
        }

        static bool InLine(Customer const& c)
        {
            return c.phase == Phase::Pending || c.phase == Phase::WalkIn || c.phase == Phase::Queue || Holds(c);
        }

        // Taken or complaining: it still stands in its slot (a second or two), and nobody moves into it before it
        // steps out.
        static bool Holds(Customer const& c)
        {
            return (c.phase == Phase::Taken || c.phase == Phase::Complain) && c.slot >= 0;
        }

        // The line: everyone in it in their current order (slot, then spawn order), with Cafe's order (queueOrder)
        // among the ones Cafe lists; each heads for the first slot after the one ahead of it (one still standing in its
        // slot, taken or complaining, keeps it). A newcomer keeps the slot it walks to until it stands there, then
        // moves up along the line, so nobody behind it is sent to that slot meanwhile; one in line moves up at once.
        std::vector<std::size_t> AssignSlots()
        {
            std::vector<std::size_t> line;
            for (std::size_t i = 0; i < _customers.size(); ++i)
                if (InLine(_customers[i]))
                    line.push_back(i);
            std::stable_sort(line.begin(), line.end(), [this](std::size_t a, std::size_t b) {
                Customer const& x = _customers[a];
                Customer const& y = _customers[b];
                int const sx = x.slot < 0 ? std::numeric_limits<int>::max() : x.slot;
                int const sy = y.slot < 0 ? std::numeric_limits<int>::max() : y.slot;
                return sx != sy ? sx < sy : x.seq < y.seq;
            });
            std::vector<std::size_t> places, listed;
            for (uint64_t guid : _in.queueOrder)
                for (std::size_t pos = 0; pos < line.size(); ++pos)
                {
                    Customer const& c = _customers[line[pos]];
                    if (c.guid == guid && c.registered &&
                        std::find(listed.begin(), listed.end(), line[pos]) == listed.end())
                        listed.push_back(line[pos]);
                }
            for (std::size_t pos = 0; pos < line.size(); ++pos)
                if (std::find(listed.begin(), listed.end(), line[pos]) != listed.end())
                    places.push_back(pos);
            for (std::size_t k = 0; k < places.size() && k < listed.size(); ++k)
                line[places[k]] = listed[k];
            int const last = std::max(int(_g.queue.size()) - 1, 0);
            int prev = -1;
            for (std::size_t pos = 0; pos < line.size(); ++pos)
            {
                Customer& c = _customers[line[pos]];
                if (Holds(c) || (c.phase == Phase::WalkIn && c.mv.walking))
                {
                    prev = std::max(prev, c.slot);
                    continue;
                }
                int const want = std::min(prev + 1, last);
                prev = want;
                if (c.slot == want)
                    continue;
                int const was = c.slot;
                c.slot = want;
                if (c.phase == Phase::Queue && c.guid)
                    Reslot(c, was);
            }
            return line;
        }

        // Along the queue line to its slot (spec 3.7.3: queue slot -> its new slot when the queue moves).
        void Reslot(Customer& c, int was)
        {
            Pose const p = PoseOf(c.guid, SlotPoint(was));
            int from = NearestPoint(_g.queue, p.At());
            if (from < 0)
                from = std::max(was, 0);
            Leg leg;
            leg.points.push_back(p.At());
            int const step = c.slot < from ? -1 : 1;
            for (int i = from + step; step < 0 ? i >= c.slot : i <= c.slot; i += step)
                leg.points.push_back(_g.queue[std::size_t(i)]);
            if (from == c.slot)
                leg.points.push_back(_g.queue[std::size_t(c.slot)]);
            leg.ok = true;
            Walk(c, leg);
        }

        // In line order: a customer at its slot registers (NpcArrived) once everyone ahead of it has, so Cafe's queue
        // is the line. Refused: it leaves.
        void Register(std::vector<std::size_t> const& line)
        {
            for (std::size_t idx : line)
            {
                Customer& c = _customers[idx];
                if (c.registered)
                    continue;
                if (c.phase != Phase::Queue || c.mv.walking || !c.guid)
                    break;
                c.registered = true;
                uint32_t const orderId = _hooks.NpcArrived(static_cast<uint8_t>(c.persona), c.guid, c.groupId);
                if (!orderId)
                {
                    Leave(c);
                    break;
                }
                c.orderId = orderId;
                c.live = true;
            }
        }

        void Step(Customer& c)
        {
            switch (c.phase)
            {
                case Phase::Pending:
                case Phase::Gone:
                    return;
                case Phase::WalkIn:
                    if (!Arrived(c))
                        return;
                    c.phase = Phase::Queue;
                    c.nextIdle = _clock + _rng.Range(5000, 12000);
                    if (Dist2d(c.mv.route.back(), SlotPoint(c.slot)) > ArriveYd)
                        Reslot(c, c.slot);   // its walk was cut short and the line moved up meanwhile
                    else
                        FaceQueue(c);
                    return;
                case Phase::Queue:
                    if (Arrived(c))
                        FaceQueue(c);
                    if (c.stage == 1 && !c.mv.walking && OrderSpotFree(c))
                    {
                        GoToOrder(c);
                        return;
                    }
                    Fidget(c);
                    return;
                case Phase::Taken:
                    if (c.mv.walking)
                    {
                        if (!Arrived(c))
                            return;
                        FaceCounter(c);
                    }
                    if (Due(_clock, c.at))
                        c.served ? GoToCup(c) : GoToPickup(c);
                    return;
                case Phase::ToOrder:
                    if (!Arrived(c))
                        return;
                    c.phase = Phase::Ordering;
                    c.stage = 0;
                    TurnTo(c.guid, _g.orderSpot.At(), StaffGuid("staff_owner"), _g.anchor.o);
                    // the owner looks up to answer, unless it is busy at a station
                    if (uint64_t const owner = StaffGuid("staff_owner"); owner && !_workers[0].busy)
                    {
                        Pose op;
                        if (_world.Where(owner, op))
                            _world.Face(owner, AngleTo(op.At(), _g.orderSpot.At()));
                    }
                    if (!c.lineSaid && !c.line.empty())
                    {
                        _world.Say(c.guid, c.line, false);
                        _world.Emote(c.guid, EmoteTalk);
                    }
                    c.lineSaid = true;
                    c.at = _clock + 1800;
                    return;
                case Phase::Ordering:
                    if (!Due(_clock, c.at))
                        return;
                    if (c.stage == 0)
                    {
                        uint64_t const owner = StaffGuid("staff_owner");
                        if (owner && !c.answer.empty())
                            _world.Say(owner, c.answer, false);
                        c.stage = 1;
                        c.at = _clock + 1500;
                        return;
                    }
                    // the owner faces the customers again (an idle one at home)
                    if (uint64_t const owner = StaffGuid("staff_owner");
                        owner && !_workers[0].busy && _workers[0].state == WorkState::Home && _workers[0].staff >= 0)
                        _world.Face(owner, _g.staff[std::size_t(_workers[0].staff)].home.o);
                    c.served ? GoToCup(c) : GoToPickup(c);
                    return;
                case Phase::ToPickup:
                    if (!Arrived(c))
                        return;
                    c.phase = Phase::Pickup;
                    FaceCounter(c);
                    c.nextIdle = _clock + _rng.Range(6000, 14000);
                    if (c.served)
                        GoToCup(c);
                    return;
                case Phase::Pickup:
                    Fidget(c);
                    return;
                case Phase::ToCup:
                    if (!Arrived(c))
                        return;
                    c.phase = Phase::TakeCup;
                    c.stage = 0;
                    FaceCounter(c);
                    c.at = _clock + 800;
                    return;
                case Phase::TakeCup:
                    if (!Due(_clock, c.at))
                        return;
                    if (c.stage == 0)
                        TakeCup(c);
                    else
                        GoSit(c);
                    return;
                case Phase::ToSeat:
                    if (Arrived(c))
                        Sit(c);
                    return;
                case Phase::Seated:
                    Sip(c);
                    if (Due(_clock, c.until))
                        Leave(c);
                    return;
                case Phase::ToKeg:
                    if (!Arrived(c))
                        return;
                    c.phase = Phase::AtKeg;
                    _world.Face(c.guid, _g.kegs[std::size_t(c.keg)].facing);
                    c.until = _clock + _rng.Range(_cfg.sitMinMs, std::max(_cfg.sitMinMs, _cfg.sitMaxMs));
                    c.nextSip = _clock + _rng.Range(1500, 3500);
                    c.nextIdle = _clock + _rng.Range(6000, 12000);
                    return;
                case Phase::AtKeg:
                    Fidget(c);
                    Sip(c);
                    if (Due(_clock, c.until))
                        Leave(c);
                    return;
                case Phase::Complain:
                    if (Due(_clock, c.at))
                        Leave(c);
                    return;
                case Phase::Leaving:
                    if (Arrived(c))
                        Vanish(c, true);
                    return;
            }
        }

        // guid at `at` turns toward `who` (when in the world), else to `fallback`.
        void TurnTo(uint64_t guid, Vec3 at, uint64_t who, float fallback)
        {
            Pose wp;
            if (who && _world.Where(who, wp))
                _world.Face(guid, AngleTo(at, wp.At()));
            else
                _world.Face(guid, fallback);
        }

        // Life while standing (in line, by the pickup spot, at a keg table): now and then a word with a neighbour, a
        // question or a point at the menu.
        void Fidget(Customer& c)
        {
            if (c.mv.walking || !c.guid)
                return;
            if (c.faceBack && Due(_clock, c.faceAt))
            {
                c.faceBack = false;
                if (c.phase == Phase::Queue)
                    FaceQueue(c);
                else if (c.phase == Phase::AtKeg)
                    _world.Face(c.guid, _g.kegs[std::size_t(c.keg)].facing);
                else
                    FaceCounter(c);
            }
            if (!Due(_clock, c.nextIdle))
                return;
            c.nextIdle = _clock + _rng.Range(7000, 15000);
            uint32_t const r = _rng.Below(100);
            Customer const* mate = Neighbour(c);
            if (mate && r < 30)
            {
                Pose mp, me;
                if (_world.Where(mate->guid, mp) && _world.Where(c.guid, me))
                {
                    _world.Face(c.guid, AngleTo(me.At(), mp.At()));
                    _world.Emote(c.guid, c.phase == Phase::AtKeg && r < 10 ? EmoteLaugh : EmoteTalk);
                    c.faceBack = true;
                    c.faceAt = _clock + 3000;
                }
            }
            else if (r < 42)
                _world.Emote(c.guid, c.phase == Phase::Queue ? EmoteQuestion : EmoteTalk);
            else if (r < 50 && c.phase == Phase::Queue)
                _world.Emote(c.guid, EmotePoint);
        }

        // Someone standing with c to chat with: the next one in line, or another one at the pickup spot or the kegs.
        Customer const* Neighbour(Customer const& c) const
        {
            for (Customer const& o : _customers)
            {
                if (&o == &c || !o.guid || o.mv.walking || o.phase != c.phase)
                    continue;
                if (c.phase == Phase::Queue && std::abs(o.slot - c.slot) != 1)
                    continue;
                return &o;
            }
            return nullptr;
        }

        bool OrderSpotFree(Customer const& self) const
        {
            for (Customer const& c : _customers)
                if (&c != &self && (c.phase == Phase::ToOrder || c.phase == Phase::Ordering))
                    return false;
            return true;
        }

        // Out of the line: the side step (spec 3.7.3), then on.
        std::vector<Vec3> OutOfLine(Customer const& c) const
        {
            if (c.slot >= 0 && std::size_t(c.slot) < _g.side.size())
                return { _g.side[std::size_t(c.slot)] };
            return {};
        }

        // From the front of the line straight on to the order spot; from further back by the side point.
        void GoToOrder(Customer& c)
        {
            Pose const p = PoseOf(c.guid, SlotPoint(c.slot));
            std::vector<Vec3> const prefix = c.slot == 0 ? std::vector<Vec3>{} : OutOfLine(c);
            c.stage = 0;
            c.phase = Phase::ToOrder;
            Walk(c, Plan(p.At(), prefix, End{ _g.orderSpot.At(), -1, false }, &c));
            c.slot = -1;
        }

        void GoToPickup(Customer& c)
        {
            Pose const p = PoseOf(c.guid, SlotPoint(c.slot));
            if (c.pickupK < 0)
                c.pickupK = FreePickup(c);
            std::vector<Vec3> const prefix = c.phase == Phase::Taken ? OutOfLine(c) : std::vector<Vec3>{};
            c.phase = Phase::ToPickup;
            c.slot = -1;
            c.counter = true;
            c.standAt = PickupWait(_g, uint8_t(c.pickupK));
            Walk(c, Plan(p.At(), prefix, End{ c.standAt, -1, false }, &c));
        }

        void GoToCup(Customer& c)
        {
            if (!c.guid)
                return;
            Pose const p = PoseOf(c.guid, _g.pickupSpot.At());
            Vec3 const front = c.cupK >= 0 ? CupFront(_g, uint8_t(c.cupK)) : p.At();
            std::vector<Vec3> const prefix =
                c.phase == Phase::Queue || c.phase == Phase::Taken ? OutOfLine(c) : std::vector<Vec3>{};
            c.slot = -1;
            c.counter = true;
            c.standAt = front;
            if (prefix.empty() && Dist2d(p.At(), front) <= NearCupYd)
            {
                Halt(c);
                c.standAt = p.At();
                c.phase = Phase::TakeCup;
                c.stage = 0;
                FaceCounter(c);
                c.at = _clock + 800;
                return;
            }
            c.phase = Phase::ToCup;
            Walk(c, Plan(p.At(), prefix, End{ front, -1, false }, &c));
        }

        static uint32_t ThanksEmote(char quality)
        {
            switch (quality)
            {
                case 'P':
                    return EmoteCheer;
                case 'G':
                    return EmoteBow;
                default:
                    return EmoteYes;
            }
        }

        // The counter cup goes, the drink is in its hand, Cafe hears CupTaken, and it thanks.
        void TakeCup(Customer& c)
        {
            if (c.cupK >= 0)
            {
                CounterCup& cc = _counter[std::size_t(c.cupK)];
                if (cc.orderId == c.orderId)
                {
                    if (cc.go)
                        _world.RemoveGo(cc.go);
                    cc = CounterCup{};
                }
                c.cupK = -1;
            }
            if (c.cupItem)
            {
                _world.Hold(c.guid, c.cupItem);
                c.holding = true;
            }
            c.live = false;
            _hooks.CupTaken(c.orderId);
            if (!c.thanks.empty())
                _world.Say(c.guid, c.thanks, false);
            _world.Emote(c.guid, ThanksEmote(c.quality));
            c.stage = 1;
            c.at = _clock + 1800;
        }

        // A chair (reserved at once and locked against players), else a keg spot, else out at once, sipping
        // (spec 3.7.4).
        void GoSit(Customer& c)
        {
            c.pickupK = -1;
            c.counter = false;
            Pose const p = PoseOf(c.guid, _g.pickupSpot.At());
            GoToPlace(c, p.At(), PickSeat(_g, _g.pickupSpot.At(), _reserved, PlayerTaken(), _kegTaken), {}, -1);
        }

        void GoToPlace(Customer& c, Vec3 from, SeatPick pick, std::vector<Vec3> const& prefix, int ownFrom)
        {
            if (pick.kind == SeatKind::Chair)
            {
                Chair const& ch = _g.chairs[std::size_t(pick.index)];
                _reserved[std::size_t(pick.index)] = true;
                _world.LockChair(ch.spawnId, true);
                c.chair = pick.index;
                c.phase = Phase::ToSeat;
                Leg leg = Plan(from, prefix, End{ ch.approach, ch.box, false }, &c, ownFrom);
                leg.points.push_back(ch.seat.At());
                Walk(c, leg);
                return;
            }
            if (pick.kind == SeatKind::Keg)
            {
                Keg const& k = _g.kegs[std::size_t(pick.index)];
                _kegTaken[std::size_t(pick.index)] = true;
                c.keg = pick.index;
                c.phase = Phase::ToKeg;
                Leg leg = Plan(from, prefix, End{ k.approach, k.box, false }, &c, ownFrom);
                leg.points.push_back(k.spot);
                Walk(c, leg);
                return;
            }
            Leave(c, prefix, ownFrom);
        }

        void ReleaseChair(Customer& c)
        {
            if (c.chair < 0)
                return;
            _reserved[std::size_t(c.chair)] = false;
            _world.LockChair(_g.chairs[std::size_t(c.chair)].spawnId, false);
            c.chair = -1;
        }

        void ReleaseKeg(Customer& c)
        {
            if (c.keg < 0)
                return;
            _kegTaken[std::size_t(c.keg)] = false;
            c.keg = -1;
        }

        // On the seat: a player who sits there anyway keeps it, and the customer steps out and tries another chair,
        // a keg spot, or leaves (spec 3.7.4). Else it sits: facing the table, the core's chair stand state, its cup
        // on the table beside it.
        void Sit(Customer& c)
        {
            std::size_t const i = std::size_t(c.chair);
            Chair const& ch = _g.chairs[i];
            if (PlayerOn(i))
            {
                ReleaseChair(c);
                std::vector<bool> reserved = _reserved;
                reserved[i] = true;
                SeatPick const pick = PickSeat(_g, ch.seat.At(), reserved, PlayerTaken(), _kegTaken);
                Pose const p = PoseOf(c.guid, ch.seat.At());
                GoToPlace(c, p.At(), pick, { ch.approach }, ch.box);
                return;
            }
            c.phase = Phase::Seated;
            _world.Face(c.guid, ch.seat.o);
            _world.Stand(c.guid, uint8_t(StandSitLowChair + ch.height));
            uint32_t const sitMs = _rng.Range(_cfg.sitMinMs, std::max(_cfg.sitMinMs, _cfg.sitMaxMs));
            c.until = _clock + sitMs;
            c.nextSip = _clock + _rng.Range(2000, 4000);
            if (c.cupGo)
                c.tableCup = _world.PlaceGo(c.cupGo, TableCupPose(_g, ch), sitMs / 1000 + 5);
        }

        void Sip(Customer& c)
        {
            if (!Due(_clock, c.nextSip))
                return;
            if (_cfg.drinkSpell)
            {
                _world.Cast(c.guid, _cfg.drinkSpell);
                c.nextSip = _clock + _rng.Range(25000, 30000);
            }
            else
            {
                _world.Emote(c.guid, EmoteEatNoSheathe);
                c.nextSip = _clock + _rng.Range(6000, 10000);
            }
        }

        // Out to the door: out of the line by its side point, out of a chair or away from a keg table by its approach
        // point (or the prefix given). A seated customer stands up first; its table cup stays a few seconds.
        void Leave(Customer& c, std::vector<Vec3> prefix = {}, int own = -1)
        {
            if (!c.guid)
            {
                c.phase = Phase::Gone;
                return;
            }
            Halt(c);
            Pose const p = PoseOf(c.guid, _g.door.At());
            if (prefix.empty())
            {
                if ((c.phase == Phase::Queue || c.phase == Phase::Taken || c.phase == Phase::Complain) && c.slot >= 0)
                    prefix = OutOfLine(c);
                else if (c.phase == Phase::Seated && c.chair >= 0)
                {
                    prefix = { _g.chairs[std::size_t(c.chair)].approach };
                    own = _g.chairs[std::size_t(c.chair)].box;
                }
                else if (c.phase == Phase::AtKeg && c.keg >= 0)
                {
                    prefix = { _g.kegs[std::size_t(c.keg)].approach };
                    own = _g.kegs[std::size_t(c.keg)].box;
                }
            }
            if (c.phase == Phase::Seated)
                _world.Stand(c.guid, StandStand);
            ReleaseChair(c);
            ReleaseKeg(c);
            if (c.tableCup)
            {
                _leftCups.push_back({ c.tableCup, _clock + 5000 });
                c.tableCup = 0;
            }
            DropCounterCup(c);
            c.pickupK = -1;
            c.counter = false;
            c.slot = -1;
            c.phase = Phase::Leaving;
            Walk(c, Plan(p.At(), prefix, End{ _g.door.At(), -1, true }, &c, own));
        }

        void DropCounterCup(Customer& c)
        {
            if (c.cupK < 0)
                return;
            CounterCup& cc = _counter[std::size_t(c.cupK)];
            if (cc.orderId == c.orderId)
            {
                if (cc.go)
                    _world.RemoveGo(cc.go);
                cc = CounterCup{};
            }
            c.cupK = -1;
        }

        // Gone from the world: at the door, stuck twice, or vanished (a grid unload, its 15-minute timer).
        void Vanish(Customer& c, bool despawn)
        {
            if (c.phase == Phase::Gone)
                return;
            if (despawn && c.guid)
                _world.Despawn(c.guid);
            if (c.live && c.orderId)
                _hooks.NpcGone(c.orderId);
            c.live = false;
            ReleaseChair(c);
            ReleaseKeg(c);
            if (c.tableCup)
                _leftCups.push_back({ c.tableCup, _clock });
            c.tableCup = 0;
            DropCounterCup(c);
            if (c.persona >= 0)
            {
                PersonaTrack& t = _tracks[std::size_t(c.persona)];
                t.left = true;
                t.leftMs = _clock;
            }
            c.counter = false;
            c.pickupK = -1;
            c.phase = Phase::Gone;
            c.mv.walking = false;
        }

        void Vanished()
        {
            for (Customer& c : _customers)
                if (c.guid && c.phase != Phase::Gone && !_world.Alive(c.guid))
                    Vanish(c, false);
        }

        // Not open (closed for safety, disabled, ...): everyone walks out, the NPC drinks on the counter go, and
        // nobody new comes. Cafe settles the orders itself, so no NpcGone follows.
        void CloseOut()
        {
            for (Customer& c : _customers)
            {
                if (c.phase == Phase::Pending)
                    c.phase = Phase::Gone;
                else if (c.phase != Phase::Leaving && c.phase != Phase::Gone)
                {
                    c.live = false;
                    Leave(c);
                }
            }
            for (CounterCup& cc : _counter)
                if (cc.npc && cc.orderId)
                {
                    if (cc.go)
                        _world.RemoveGo(cc.go);
                    cc = CounterCup{};
                }
            if (!Due(_nextSpawn, _clock + FirstSpawnMs))
                _nextSpawn = _clock + FirstSpawnMs;
        }

        // The pause: everyone stops where they are, and the clock stops with them.
        void Freeze()
        {
            for (Customer& c : _customers)
                if (c.mv.walking && c.guid)
                    _world.Stop(c.guid);
            for (Worker& w : _workers)
                if (w.mv.walking && w.guid)
                    _world.Stop(w.guid);
            if (_busser.mv.walking && _busser.guid)
                _world.Stop(_busser.guid);
        }

        void Thaw()
        {
            for (Customer& c : _customers)
                if (c.mv.walking)
                    Resume(c.guid, c.mv);
            for (Worker& w : _workers)
                if (w.mv.walking)
                    Resume(w.guid, w.mv);
            if (_busser.mv.walking)
                Resume(_busser.guid, _busser.mv);
        }

        void Resume(uint64_t guid, Mover& m)
        {
            Pose p;
            if (!guid || !_world.Where(guid, p))
                return;
            std::vector<Vec3> const rest = Remainder(m.route, p.At());
            m.resentAt = _clock;
            _world.Walk(guid, std::vector<Vec3>(rest.begin() + 1, rest.end()), m.run);
        }

        // ---- house workers (spec 3.7.5) ----

        void WorkerStep(Worker& w)
        {
            std::size_t const index = std::size_t(&w - _workers.data());
            if (w.staff < 0)
                return;
            StaffHome const& home = _g.staff[std::size_t(w.staff)];
            w.guid = home.spawnId ? _world.Staff(home.spawnId) : 0;
            if (index >= _cfg.houseWorkers)
            {
                if (w.busy)
                {
                    // Order.HouseWorkers was lowered: the job goes back to the queue (Cafe still holds the order), and
                    // the other worker makes it from its first step
                    Job back = w.job;
                    StopJob(w);
                    _house.PutBack(std::move(back));
                }
                return;
            }
            if (!w.busy)
            {
                if (_in.open == 1 && !_house.Empty())
                {
                    w.job = std::move(*_house.Pop());
                    w.busy = true;
                    w.step = 0;
                    w.station = -1;
                    w.spot = -1;
                    w.jobStart = _clock;
                    w.estEnd = _clock + JobMs(w.job);
                    if (w.mv.walking && w.guid)
                        _world.Stop(w.guid);
                    w.mv.walking = false;
                    BeginStep(w);
                    return;
                }
                if (w.state == WorkState::Return && StaffArrived(w.guid, w.mv))
                {
                    w.state = WorkState::Home;
                    if (w.guid)
                        _world.Face(w.guid, home.home.o);
                }
                return;
            }
            if (w.state == WorkState::Walk)
            {
                if (StaffArrived(w.guid, w.mv))
                    StartWork(w);
                return;
            }
            if (w.state != WorkState::Work)
                return;
            Data::Action const* a = Data::FindAction(w.job.actions[w.step]);
            if (a && a->kind == 'H' && !w.released && Due(_clock, w.releaseAt))
            {
                // the house releases a timed step at the gold centre
                w.released = true;
                if (w.guid)
                    _world.FinishChannel(w.guid, a->spell);
            }
            if (!Due(_clock, w.stepEnd))
                return;
            if (w.guid && a && a->emoteState)
                _world.EmoteState(w.guid, 0);
            if (++w.step < w.job.actions.size())
            {
                BeginStep(w);
                return;
            }
            uint32_t const done = w.job.orderId;
            w.busy = false;
            w.job = Job{};
            GoHome(w);
            _hooks.HouseDone(done);
        }

        // To the step's station: a spot no player stands on and the other worker does not use, else behind the
        // station; the same spot again for an action at the same station (repeated in place).
        void BeginStep(Worker& w)
        {
            Data::Action const* a = Data::FindAction(w.job.actions[w.step]);
            int const si = a ? Data::StationIndex(a->station) : -1;
            if (si < 0 || !_g.stations[std::size_t(si)].id)
            {
                w.station = -1;
                StartWork(w);
                return;
            }
            Station const& s = _g.stations[std::size_t(si)];
            std::vector<Vec3> staff;
            for (Worker const& o : _workers)
                if (&o != &w && o.busy && o.station == si)
                    staff.push_back(o.target);
            int spot = PickSpot(s, PlayerSpots(), staff);
            if (w.station == si && w.spot >= 0)
            {
                bool playerThere = false;
                for (PlayerNear const& p : _players)
                    if (Dist2d(p.pos, SpotPoint(s, w.spot)) <= SpotPlayerYd)
                        playerThere = true;
                if (!playerThere)
                    spot = w.spot;
            }
            w.station = si;
            w.spot = spot;
            w.target = SpotPoint(s, spot);
            Pose p;
            if (!w.guid || !_world.Where(w.guid, p) || Dist2d(p.At(), w.target) <= ArriveYd)
            {
                StartWork(w);
                return;
            }
            w.state = WorkState::Walk;
            Go(w.guid, w.mv, Route(_work, End{ p.At(), -1, false }, End{ w.target, -1, false }, _g.boxes).points,
               false);
        }

        // At the spot: face the station, the step's emote, its spell (the cast bar others see), then wait its time
        // (a timed step: the gold centre), padded so the job lasts at least minTotalMs.
        void StartWork(Worker& w)
        {
            uint8_t const action = w.job.actions[w.step];
            Data::Action const* a = Data::FindAction(action);
            w.state = WorkState::Work;
            w.released = false;
            if (w.guid && a)
            {
                if (w.station >= 0)
                {
                    Station const& s = _g.stations[std::size_t(w.station)];
                    _world.Face(w.guid, AngleTo(w.target, { s.objX, s.objY, 0 }));
                }
                if (a->emoteState)
                    _world.EmoteState(w.guid, a->emoteState);
                if (a->emoteOneShot)
                    _world.Emote(w.guid, a->emoteOneShot);
                _world.Cast(w.guid, a->spell);
            }
            uint32_t const own = StepMs(action);
            w.releaseAt = _clock + own;
            uint32_t const deadline = StepDeadline(w.jobStart, w.job.minTotalMs, w.step, w.job.actions.size());
            w.stepEnd = Due(_clock + own, deadline) ? _clock + own : deadline;
            _hooks.HouseStepStarted(w.job.orderId, static_cast<uint8_t>(w.step), action, w.stepEnd - _clock, w.guid);
        }

        void GoHome(Worker& w)
        {
            w.station = -1;
            w.spot = -1;
            StaffHome const& home = _g.staff[std::size_t(w.staff)];
            Pose p;
            if (!w.guid || !_world.Where(w.guid, p))
            {
                w.state = WorkState::Home;
                return;
            }
            w.state = WorkState::Return;
            Go(w.guid, w.mv, Route(_work, End{ p.At(), -1, false }, End{ home.home.At(), -1, false }, _g.boxes).points,
               false);
        }

        void StopJob(Worker& w)
        {
            if (w.guid && w.state == WorkState::Work && w.step < w.job.actions.size())
                if (Data::Action const* a = Data::FindAction(w.job.actions[w.step]))
                {
                    if (a->emoteState)
                        _world.EmoteState(w.guid, 0);
                    if (a->kind == 'H')
                        _world.FinishChannel(w.guid, a->spell);
                }
            if (w.mv.walking && w.guid)
                _world.Stop(w.guid);
            w.mv.walking = false;
            w.busy = false;
            w.job = Job{};
            GoHome(w);
        }

        // ---- the busser (spec 3.7.5) ----

        void BusserStep()
        {
            Busser& b = _busser;
            if (b.staff < 0)
            {
                TimerDeliveries();   // no busser in this layout: table service on a timer
                return;
            }
            StaffHome const& home = _g.staff[std::size_t(b.staff)];
            b.guid = home.spawnId ? _world.Staff(home.spawnId) : 0;
            if (!b.guid)
            {
                if (b.orderId)
                    EndDelivery(true);
                TimerDeliveries();
                return;
            }
            if (!b.orderId && !_deliveries.empty())
            {
                Delivery const d = _deliveries.front();
                _deliveries.erase(_deliveries.begin());
                StartDelivery(d);
                return;
            }
            switch (b.state)
            {
                case BusState::Home:
                    if (!Due(_clock, b.at) || _in.open != 1)
                        return;
                    b.tablesLeft = int(_g.tableTops.size());
                    NextTable();
                    return;
                case BusState::ToTable:
                    if (!StaffArrived(b.guid, b.mv))
                        return;
                    if (b.table >= 0)
                        _world.Face(b.guid, AngleTo(b.mv.route.back(), _g.tableTops[std::size_t(b.table)]));
                    _world.Emote(b.guid, EmoteLoot);
                    b.state = BusState::Wipe;
                    b.at = _clock + 3000;
                    return;
                case BusState::Wipe:
                    if (!Due(_clock, b.at))
                        return;
                    if (--b.tablesLeft > 0 && _in.open == 1)
                        NextTable();
                    else
                        BusserHome();
                    return;
                case BusState::Return:
                    if (!StaffArrived(b.guid, b.mv))
                        return;
                    _world.Face(b.guid, home.home.o);
                    b.state = BusState::Home;
                    b.at = _clock + _rng.Range(8000, 16000);
                    return;
                case BusState::ToCup:
                    if (!StaffArrived(b.guid, b.mv))
                        return;
                    _world.Face(b.guid, _g.anchor.o);
                    b.state = BusState::TakeCup;
                    b.at = _clock + 600;
                    return;
                case BusState::TakeCup:
                    if (Due(_clock, b.at))
                        PickUpForTable();
                    return;
                case BusState::Carry:
                    if (PlayerChair(b.player) != b.chair)
                    {
                        EndDelivery(true);   // the player stood up: back on the counter (the 15 yd pickup rule)
                        return;
                    }
                    if (StaffArrived(b.guid, b.mv))
                        ServeSeat();
                    return;
                case BusState::Serve:
                    if (!Due(_clock, b.at))
                        return;
                    b.orderId = 0;
                    BusserHome();
                    return;
            }
        }

        // The stock item a cup game object stands for (its first recipe at this cafe): what the busser carries.
        uint32_t CupItem(uint32_t cupGo) const
        {
            for (Data::Recipe const& r : Data::Recipes)
                if (r.cafeId == _g.cafeId && (r.tableCup == cupGo || r.tableCup + Data::StandInOffset == cupGo))
                    return r.cupItem;
            return 0;
        }

        // Off to the counter (running: it is an errand) for the order's cup.
        void StartDelivery(Delivery const& d)
        {
            Busser& b = _busser;
            if (b.mv.walking)
                _world.Stop(b.guid);
            b.orderId = d.orderId;
            b.player = d.player;
            b.cupGo = d.cupGo;
            b.cupK = -1;
            b.chair = -1;
            for (std::size_t k = 0; k < _counter.size(); ++k)
                if (_counter[k].orderId == d.orderId)
                    b.cupK = int(k);
            Vec3 const front = b.cupK >= 0 ? CupFront(_g, uint8_t(b.cupK)) : _g.pickupSpot.At();
            Pose p;
            _world.Where(b.guid, p);
            b.state = BusState::ToCup;
            Go(b.guid, b.mv, Route(_aisles, End{ p.At(), -1, false }, End{ front, -1, false }, _g.boxes,
                                   Blockers(nullptr)).points, true);
        }

        void PickUpForTable()
        {
            Busser& b = _busser;
            if (b.cupK >= 0 && _counter[std::size_t(b.cupK)].orderId == b.orderId)
            {
                CounterCup& cc = _counter[std::size_t(b.cupK)];
                if (cc.go)
                    _world.RemoveGo(cc.go);
                cc = CounterCup{};
            }
            b.cupK = -1;
            if (uint32_t const item = CupItem(b.cupGo))
            {
                _world.Hold(b.guid, item);
                b.holding = true;
            }
            b.chair = PlayerChair(b.player);
            if (b.chair < 0)
            {
                EndDelivery(true);
                return;
            }
            Chair const& ch = _g.chairs[std::size_t(b.chair)];
            Pose p;
            _world.Where(b.guid, p);
            b.state = BusState::Carry;
            Go(b.guid, b.mv, Route(_aisles, End{ p.At(), -1, false }, End{ ch.approach, ch.box, false }, _g.boxes,
                                   Blockers(nullptr)).points, true);
        }

        // At the player's chair: the cup goes on their table, Cafe hears Delivered (and says the table-service line
        // through StaffSay: only Cafe knows the drink's name).
        void ServeSeat()
        {
            Busser& b = _busser;
            Pose p;
            _world.Where(b.guid, p);
            Chair const& ch = _g.chairs[std::size_t(b.chair)];
            _world.Face(b.guid, AngleTo(p.At(), ch.seat.At()));
            if (b.holding)
                _world.Hold(b.guid, 0);
            b.holding = false;
            PlayerCupAt(b.orderId, b.player, b.chair, b.cupGo);
            uint32_t const order = b.orderId;
            b.state = BusState::Serve;
            b.at = _clock + 1500;
            _hooks.Delivered(order);
        }

        void PlayerCupAt(uint32_t orderId, uint64_t player, int chair, uint32_t cupGo)
        {
            if (!cupGo || chair < 0)
                return;
            uint64_t const go = _world.PlaceGo(cupGo, TableCupPose(_g, _g.chairs[std::size_t(chair)]), PlayerCupSec);
            if (go)
                _playerCups.push_back({ orderId, player, chair, go, _clock + PlayerCupSec * 1000 });
        }

        // A delivery that did not happen. putBack: the busser had taken the cup, so it goes back on the counter and
        // the order waits for the pickup rule (Cafe may ask again when the player sits down).
        void EndDelivery(bool putBack)
        {
            Busser& b = _busser;
            uint32_t const order = b.orderId;
            bool const hadCup = b.state == BusState::Carry || (b.state == BusState::TakeCup && b.cupK < 0);
            if (b.holding && b.guid)
                _world.Hold(b.guid, 0);
            b.holding = false;
            b.orderId = 0;
            b.player = 0;
            b.chair = -1;
            b.cupK = -1;
            if (putBack && hadCup && order)
                PlaceCounterCup(order, b.cupGo);
            if (b.guid)
                BusserHome();
            else
                b.state = BusState::Home;
        }

        // No busser in the world: a seated player gets the drink 3 s after Cafe asks; one who stood up does not.
        void TimerDeliveries()
        {
            for (auto it = _deliveries.begin(); it != _deliveries.end();)
            {
                if (!Due(_clock, it->since + 3000))
                {
                    ++it;
                    continue;
                }
                Delivery const d = *it;
                it = _deliveries.erase(it);
                int const chair = PlayerChair(d.player);
                if (chair < 0)
                    continue;
                for (CounterCup& cc : _counter)
                    if (cc.orderId == d.orderId)
                    {
                        if (cc.go)
                            _world.RemoveGo(cc.go);
                        cc = CounterCup{};
                    }
                PlayerCupAt(d.orderId, d.player, chair, d.cupGo);
                _hooks.Delivered(d.orderId);
            }
        }

        // The busser's round: each table in turn, standing where a free chair of it is, a wipe (ONESHOT_LOOT) and 3 s.
        void NextTable()
        {
            Busser& b = _busser;
            if (_g.tableTops.empty())
            {
                BusserHome();
                return;
            }
            std::size_t const t = b.nextTable % _g.tableTops.size();
            b.nextTable = t + 1;
            b.table = int(t);
            Pose p;
            _world.Where(b.guid, p);
            int best = -1;
            float bestD = std::numeric_limits<float>::max();
            for (std::size_t i = 0; i < _g.chairs.size(); ++i)
            {
                if (_g.chairs[i].tableTop != int(t) || _reserved[i] || PlayerOn(i))
                    continue;
                float const d = Dist2d(p.At(), _g.chairs[i].approach);
                if (d < bestD)
                {
                    bestD = d;
                    best = int(i);
                }
            }
            if (best < 0)
            {
                // every chair of it taken: on to the next table
                b.state = BusState::Wipe;
                b.at = _clock;
                return;
            }
            Chair const& ch = _g.chairs[std::size_t(best)];
            b.state = BusState::ToTable;
            Go(b.guid, b.mv, Route(_aisles, End{ p.At(), -1, false }, End{ ch.approach, ch.box, false }, _g.boxes,
                                   Blockers(nullptr)).points, false);
        }

        void BusserHome()
        {
            Busser& b = _busser;
            StaffHome const& home = _g.staff[std::size_t(b.staff)];
            Pose p;
            b.state = BusState::Return;
            if (!b.guid || !_world.Where(b.guid, p))
            {
                b.state = BusState::Home;
                b.at = _clock + 8000;
                return;
            }
            Go(b.guid, b.mv, Route(_aisles, End{ p.At(), -1, false }, End{ home.home.At(), -1, false }, _g.boxes,
                                   Blockers(nullptr)).points, false);
        }

        // ---- cups left on tables, and seated players' cups ----

        void Cups()
        {
            for (auto it = _leftCups.begin(); it != _leftCups.end();)
            {
                if (Due(_clock, it->until))
                {
                    _world.RemoveGo(it->go);
                    it = _leftCups.erase(it);
                }
                else
                    ++it;
            }
            for (auto it = _playerCups.begin(); it != _playerCups.end();)
            {
                if (Due(_clock, it->until) || PlayerChair(it->player) != it->chair)
                {
                    _world.RemoveGo(it->go);
                    it = _playerCups.erase(it);
                }
                else
                    ++it;
            }
        }

        Geometry _g;
        Config _cfg;
        World& _world;
        Hooks& _hooks;
        Rng _rng;
        Graph _aisles, _work;
        Inputs _in;
        bool _started = false, _paused = false, _inUpdate = false;
        uint32_t _lastNow = 0, _clock = 0, _nextSpawn = 0, _relockAt = 0;
        uint32_t _nextSeq = 1, _nextGroup = 1;
        std::vector<Customer> _customers;
        std::vector<bool> _reserved, _kegTaken;
        Tracks _tracks{};
        std::array<CounterCup, Data::CounterCupMax> _counter{};
        std::vector<LeftCup> _leftCups;
        std::vector<PlayerCup> _playerCups;
        std::vector<PlayerNear> _players;
        HouseQueue _house;
        std::array<Worker, 2> _workers{};
        Busser _busser;
        std::vector<Delivery> _deliveries;
        std::vector<std::function<void()>> _later;
    };
}

#endif
