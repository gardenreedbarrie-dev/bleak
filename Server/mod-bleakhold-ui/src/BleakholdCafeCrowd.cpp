/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The cafe (section 21): CafeCrowd (BleakholdCafeTypes.h) on BleakholdCafeCrowdRules.h's engines. See
 * BleakholdCafeCrowd.h for the threads.
 *
 * Walking: every leg is a straight walk between points the layout keeps clear (spec 3.7.3). MotionMaster::MovePoint
 * cannot do that: PointMovementGenerator calls MoveSplineInit::MoveTo(x, y, z, generatePath = true) even when asked
 * not to generate a path, so a navmesh that knows nothing of the cafe's props would bend the leg. MoveSplinePath with
 * three or more points uses MoveSplineInit::MovebyPath (a linear spline, no path finding), and walks the whole leg
 * without stopping at its nodes; a two-point leg gets its midpoint added for that (EscortMovementGenerator sends two
 * points through MoveTo with path finding as well).
 */

#include "BleakholdCafeCrowd.h"

#include "CellImpl.h"
#include "Config.h"
#include "Creature.h"
#include "GameObject.h"
#include "GameTime.h"
#include "GridNotifiers.h"
#include "Log.h"
#include "Map.h"
#include "MapMgr.h"
#include "MotionMaster.h"
#include "MoveSpline.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "SharedDefines.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "TemporarySummon.h"

#include <algorithm>
#include <cmath>

namespace Bleakhold
{
    namespace
    {
        static_assert(CrowdRules::EmoteTalk == EMOTE_ONESHOT_TALK, "SharedDefines.h");
        static_assert(CrowdRules::EmoteBow == EMOTE_ONESHOT_BOW, "SharedDefines.h");
        static_assert(CrowdRules::EmoteCheer == EMOTE_ONESHOT_CHEER, "SharedDefines.h");
        static_assert(CrowdRules::EmoteQuestion == EMOTE_ONESHOT_QUESTION, "SharedDefines.h");
        static_assert(CrowdRules::EmoteLaugh == EMOTE_ONESHOT_LAUGH, "SharedDefines.h");
        static_assert(CrowdRules::EmoteRude == EMOTE_ONESHOT_RUDE, "SharedDefines.h");
        static_assert(CrowdRules::EmotePoint == EMOTE_ONESHOT_POINT, "SharedDefines.h");
        static_assert(CrowdRules::EmoteEatNoSheathe == EMOTE_ONESHOT_EAT_NO_SHEATHE, "SharedDefines.h");
        static_assert(CrowdRules::EmoteYes == EMOTE_ONESHOT_YES, "SharedDefines.h");
        static_assert(CrowdRules::EmoteNo == EMOTE_ONESHOT_NO, "SharedDefines.h");
        static_assert(CrowdRules::EmoteLoot == EMOTE_ONESHOT_LOOT, "SharedDefines.h");
        static_assert(CrowdRules::StandStand == UNIT_STAND_STATE_STAND, "UnitDefines.h");
        static_assert(CrowdRules::StandSitLowChair == UNIT_STAND_STATE_SIT_LOW_CHAIR, "UnitDefines.h");

        constexpr uint32_t CfgRefreshMs = 60000;
        constexpr uint32_t GroupIdsPerSite = 1000000;
        constexpr float MinWalkYd = 0.05f;              // points closer than this to the one before are left out

        // The flags of a step's cosmetic cast (spec 3.6): never TRIGGERED_FULL_MASK, which casts instantly.
        constexpr TriggerCastFlags StepCastFlags = TriggerCastFlags(TRIGGERED_IGNORE_GCD |
            TRIGGERED_IGNORE_SPELL_AND_CATEGORY_CD | TRIGGERED_IGNORE_POWER_AND_REAGENT_COST |
            TRIGGERED_IGNORE_SET_FACING | TRIGGERED_DONT_REPORT_CAST_ERROR);

        CrowdRules::Vec3 V(Position const& p)
        {
            return { p.GetPositionX(), p.GetPositionY(), p.GetPositionZ() };
        }

        CrowdRules::Pose P(Position const& p)
        {
            return { p.GetPositionX(), p.GetPositionY(), p.GetPositionZ(), p.GetOrientation() };
        }

        // A key of the BLEAKHOLD CAFE block, clamped; out of range: LOG_ERROR and the default (spec 3.11).
        uint32_t Read(char const* key, uint32_t def, uint32_t lo, uint32_t hi, bool logs)
        {
            uint32_t const v = sConfigMgr->GetOption<uint32_t>(key, def, logs);
            if (v >= lo && v <= hi)
                return v;
            if (logs)
                LOG_ERROR("module", "[Bleakhold] {} = {} is not in {}..{}, using default {}", key, v, lo, hi, def);
            return def;
        }

        CrowdRules::Config ReadConfig(bool logs)
        {
            CrowdRules::Config c;
            c.customers = sConfigMgr->GetOption<bool>("BleakholdUi.Cafe.Customer.Enable", true, logs);
            c.intervalMs = Read("BleakholdUi.Cafe.Customer.IntervalSec", 30, 5, 600, logs) * 1000;
            c.jitterMs = std::min(Read("BleakholdUi.Cafe.Customer.JitterSec", 8, 0, 300, logs) * 1000, c.intervalMs);
            c.baristaFactorPct = Read("BleakholdUi.Cafe.Customer.BaristaFactorPct", 160, 100, 400, logs);
            c.maxAlive = uint8_t(Read("BleakholdUi.Cafe.Customer.MaxAlive", 6, 0, 12, logs));
            c.rushMaxAlive = uint8_t(Read("BleakholdUi.Cafe.Customer.RushMaxAlive", 8, 0, 16, logs));
            c.ambientMax = uint8_t(Read("BleakholdUi.Cafe.Customer.AmbientMax", 2, 0, 8, logs));
            c.sitMinMs = Read("BleakholdUi.Cafe.Customer.SitMinSec", 40, 5, 600, logs) * 1000;
            c.sitMaxMs = std::max(Read("BleakholdUi.Cafe.Customer.SitMaxSec", 70, 5, 600, logs) * 1000, c.sitMinMs);
            c.namedCooldownMs = Read("BleakholdUi.Cafe.Customer.NamedCooldownSec", 600, 0, 86400, logs) * 1000;
            c.houseWorkers = uint8_t(Read("BleakholdUi.Cafe.Order.HouseWorkers", 2, 1, 2, logs));
            c.houseBaseMs = Read("BleakholdUi.Cafe.Order.HouseBaseSec", 30, 0, 600, logs) * 1000;
            c.housePerLineMs = Read("BleakholdUi.Cafe.Order.HousePerLineSec", 5, 0, 120, logs) * 1000;
            c.drinkSpell = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Cafe.Customer.DrinkSpell", 0, logs);
            if (c.drinkSpell && !sSpellMgr->GetSpellInfo(c.drinkSpell))
            {
                if (logs)
                    LOG_ERROR("module", "[Bleakhold] BleakholdUi.Cafe.Customer.DrinkSpell {} is not a spell, using "
                        "the eat emote", c.drinkSpell);
                c.drinkSpell = 0;
            }
            return c;
        }

        // Cafe's CafeSite as the engine's Geometry (plain values). A chair's size is its template's (a bench's seats
        // stand that far apart, GameObject::Use).
        CrowdRules::Geometry FromSite(CafeSite const& s)
        {
            CrowdRules::Geometry g;
            g.cafeId = s.cafeId;
            g.anchor = P(s.anchor);
            g.orderSpot = P(s.orderSpot);
            g.pickupSpot = P(s.pickupSpot);
            g.door = P(s.door);
            for (Position const& q : s.queueSlots)
                g.queue.push_back(V(q));
            for (Position const& n : s.nodes)
                g.nodes.push_back(V(n));
            for (CafeSite::Chair const& c : s.chairs)
            {
                CrowdRules::Chair ch;
                ch.slot = c.slot;
                ch.table = c.table;
                ch.seat = P(c.seat);
                ch.approach = V(c.approach);
                ch.height = c.height;
                ch.slots = std::max<uint8_t>(c.slots, 1);
                ch.spawnId = c.spawnId;
                if (GameObjectData const* data = sObjectMgr->GetGameObjectData(ObjectGuid::LowType(c.spawnId)))
                    if (GameObjectTemplate const* t = sObjectMgr->GetGameObjectTemplate(data->id))
                        ch.size = t->size;
                g.chairs.push_back(ch);
            }
            for (Position const& k : s.kegSpots)
            {
                CrowdRules::Keg keg;
                keg.spot = V(k);
                g.kegs.push_back(keg);
            }
            for (Position const& t : s.tableTops)
                g.tableTops.push_back(V(t));
            for (CafeSite::Footprint const& f : s.footprints)
                g.boxes.push_back({ f.x, f.y, f.halfW, f.halfD, f.o });
            for (std::size_t i = 0; i < s.stations.size() && i < g.stations.size(); ++i)
            {
                StationSpots const& st = s.stations[i];
                CrowdRules::Station& out = g.stations[i];
                out.id = st.station;
                out.spots = { V(st.spots[0]), V(st.spots[1]) };
                out.objX = st.objX;
                out.objY = st.objY;
                out.slot = st.slot;
            }
            for (CafeSite::Staff const& m : s.staff)
                g.staff.push_back({ m.role, m.entry, m.spawnId, P(m.home) });
            CrowdRules::Finish(g);
            return g;
        }

        CrowdRules::Inputs ToInputs(CrowdInputs const& in)
        {
            CrowdRules::Inputs out;
            out.open = in.open;
            out.baristas = in.baristas;
            out.rush = in.rush;
            out.queueCap = in.queueCap;
            out.queueLen = in.queueLen;
            out.playerNear = in.playerNear;
            out.queueOrder = in.queueOrder;
            return out;
        }

        CrowdRules::Job ToJob(HouseJob const& j)
        {
            CrowdRules::Job out;
            out.orderId = j.orderId;
            out.playerOrder = j.playerOrder;
            out.front = j.front;
            out.actions = j.actions;
            out.minTotalMs = j.minTotalMs;
            return out;
        }

        // The players near a cafe (Cell::VisitObjects with a plain point: the cafe's anchor is no WorldObject).
        struct PlayerScan
        {
            float x, y, z, r2;
            std::vector<CrowdRules::PlayerNear>& out;

            void Visit(PlayerMapType& m)
            {
                for (PlayerMapType::iterator it = m.begin(); it != m.end(); ++it)
                {
                    Player* p = it->GetSource();
                    if (!p || !p->IsInWorld() || !p->IsAlive() || !p->InSamePhase(PHASEMASK_NORMAL))
                        continue;
                    float const dx = p->GetPositionX() - x, dy = p->GetPositionY() - y;
                    if (dx * dx + dy * dy > r2)
                        continue;
                    CrowdRules::PlayerNear n;
                    n.guid = p->GetGUID().GetRawValue();
                    n.pos = { p->GetPositionX(), p->GetPositionY(), p->GetPositionZ() };
                    n.sitting = p->IsSitState();
                    out.push_back(n);
                }
            }

            template<class NOT_INTERESTED>
            void Visit(GridRefMgr<NOT_INTERESTED>&) {}
        };
    }

    // ---- CrowdWorld ----------------------------------------------------------------------------------------------

    Map* CrowdWorld::GetMap() const
    {
        return sMapMgr->FindBaseNonInstanceMap(_mapId);
    }

    Creature* CrowdWorld::Unit(uint64_t guid) const
    {
        if (!guid)
            return nullptr;
        Map* map = GetMap();
        Creature* c = map ? map->GetCreature(ObjectGuid(guid)) : nullptr;
        return c && c->IsInWorld() && c->IsAlive() ? c : nullptr;
    }

    // A temp summon with a 15-minute duration: TempSummon::InitStats makes the default MANUAL_DESPAWN a
    // TEMPSUMMON_TIMED_DESPAWN (TemporarySummon.cpp:212-213), the safety timer; with no summoner its phase is
    // PHASEMASK_NORMAL. A generic customer's look is one of its persona's displays (the template holds four at most).
    uint64_t CrowdWorld::Summon(uint32_t entry, CrowdRules::Pose const& at, uint32_t display)
    {
        Map* map = GetMap();
        if (!map)
            return 0;
        TempSummon* s = map->SummonCreature(entry, Position(at.x, at.y, at.z, at.o), nullptr, CrowdRules::SummonMs);
        if (!s)
            return 0;
        if (display)
        {
            s->SetDisplayId(display);
            s->SetNativeDisplayId(display);
        }
        s->SetReactState(REACT_PASSIVE);
        s->SetWalk(true);
        return s->GetGUID().GetRawValue();
    }

    bool CrowdWorld::Alive(uint64_t guid)
    {
        return Unit(guid) != nullptr;
    }

    bool CrowdWorld::Where(uint64_t guid, CrowdRules::Pose& out)
    {
        Creature* c = Unit(guid);
        if (!c)
            return false;
        out = { c->GetPositionX(), c->GetPositionY(), c->GetPositionZ(), c->GetOrientation() };
        return true;
    }

    bool CrowdWorld::Moving(uint64_t guid)
    {
        Creature* c = Unit(guid);
        return c && c->movespline && !c->movespline->Finalized();
    }

    void CrowdWorld::Walk(uint64_t guid, std::vector<CrowdRules::Vec3> const& points, bool run)
    {
        Creature* c = Unit(guid);
        if (!c)
            return;
        // creatures keep an emote state while walking, and a sitter must stand first
        c->SetEmoteState(EMOTE_ONESHOT_NONE);
        if (c->IsSitState())
            c->SetStandState(UNIT_STAND_STATE_STAND);
        Movement::PointsArray path;
        path.emplace_back(c->GetPositionX(), c->GetPositionY(), c->GetPositionZ());
        for (CrowdRules::Vec3 const& p : points)
        {
            G3D::Vector3 const& last = path.back();
            if (std::hypot(p.x - last.x, p.y - last.y) < MinWalkYd && std::fabs(p.z - last.z) < MinWalkYd)
                continue;
            path.emplace_back(p.x, p.y, p.z);
        }
        if (path.size() < 2)
            return;   // already there: the engine sees the arrival
        if (path.size() == 2)
            path.insert(path.begin() + 1, (path[0] + path[1]) * 0.5f);
        c->GetMotionMaster()->MoveSplinePath(&path, run ? FORCED_MOVEMENT_RUN : FORCED_MOVEMENT_WALK);
    }

    void CrowdWorld::Stop(uint64_t guid)
    {
        if (Creature* c = Unit(guid))
        {
            c->GetMotionMaster()->Clear(false);
            c->StopMoving();
        }
    }

    void CrowdWorld::Teleport(uint64_t guid, CrowdRules::Pose const& to)
    {
        if (Creature* c = Unit(guid))
            c->NearTeleportTo(to.x, to.y, to.z, to.o);
    }

    void CrowdWorld::Face(uint64_t guid, float o)
    {
        if (Creature* c = Unit(guid))
            c->SetFacingTo(o);
    }

    void CrowdWorld::Despawn(uint64_t guid)
    {
        if (Creature* c = Unit(guid))
            c->DespawnOrUnsummon();
    }

    // All speech is LANG_UNIVERSAL (spec 3.7.5). "emote:leaves a coin..." is a text emote; the client puts the
    // speaker's name for the %s of CHAT_MSG_MONSTER_EMOTE.
    void CrowdWorld::Say(uint64_t guid, std::string_view text, bool yell)
    {
        Creature* c = Unit(guid);
        if (!c || text.empty())
            return;
        constexpr std::string_view EmotePrefix = "emote:";
        if (text.substr(0, EmotePrefix.size()) == EmotePrefix)
        {
            std::string_view rest = text.substr(EmotePrefix.size());
            while (!rest.empty() && rest.front() == ' ')
                rest.remove_prefix(1);
            c->TextEmote("%s " + std::string(rest));
            return;
        }
        if (yell)
            c->Yell(text, LANG_UNIVERSAL);
        else
            c->Say(text, LANG_UNIVERSAL);
    }

    void CrowdWorld::Emote(uint64_t guid, uint32_t emote)
    {
        if (Creature* c = Unit(guid))
            c->HandleEmoteCommand(emote);
    }

    void CrowdWorld::EmoteState(uint64_t guid, uint32_t state)
    {
        if (Creature* c = Unit(guid))
            c->SetEmoteState(static_cast<::Emote>(state));
    }

    void CrowdWorld::Stand(uint64_t guid, uint8_t state)
    {
        if (Creature* c = Unit(guid))
            c->SetStandState(state);
    }

    // The cup in hand: main hand (virtual item slot 0) shows a stock item (2703, 2705, 2718, 13612, 13861).
    void CrowdWorld::Hold(uint64_t guid, uint32_t item)
    {
        if (Creature* c = Unit(guid))
            c->SetVirtualItem(0, item);
    }

    // A house step's spell (the cast bar players see on their target frame) or Customer.DrinkSpell. A spell the
    // server does not have (no spell_dbc rows yet) is not cast: Cafe's startup check reports it.
    void CrowdWorld::Cast(uint64_t guid, uint32_t spell)
    {
        Creature* c = Unit(guid);
        if (!c || !sSpellMgr->GetSpellInfo(spell))
            return;
        if (c->IsNonMeleeSpellCast(false))
            c->InterruptNonMeleeSpells(false);
        c->CastSpell(c, spell, StepCastFlags);
    }

    // Unit::FinishSpell: SendChannelUpdate(0) and finish(true), no Spell::cancel, so nobody sees "Interrupted"
    // (spec 0.3 #9).
    void CrowdWorld::FinishChannel(uint64_t guid, uint32_t spell)
    {
        Creature* c = Unit(guid);
        if (!c)
            return;
        if (Spell* s = c->GetCurrentSpell(CURRENT_CHANNELED_SPELL); s && s->m_spellInfo && s->m_spellInfo->Id == spell)
            c->FinishSpell(CURRENT_CHANNELED_SPELL, true);
    }

    uint64_t CrowdWorld::Staff(uint64_t spawnId)
    {
        Map* map = GetMap();
        if (!map || !spawnId)
            return 0;
        auto const bounds = map->GetCreatureBySpawnIdStore().equal_range(ObjectGuid::LowType(spawnId));
        for (auto it = bounds.first; it != bounds.second; ++it)
            if (Creature* c = it->second; c && c->IsInWorld() && c->IsAlive())
                return c->GetGUID().GetRawValue();
        return 0;
    }

    // A cup: a temporary object that goes by itself after lifetimeSec (Map::SummonGameObject's respawn time with no
    // spawn by default); the engine removes it sooner.
    uint64_t CrowdWorld::PlaceGo(uint32_t entry, CrowdRules::Pose const& at, uint32_t lifetimeSec)
    {
        Map* map = GetMap();
        if (!map || !entry)
            return 0;
        GameObject* go = map->SummonGameObject(entry, at.x, at.y, at.z, at.o, 0.0f, 0.0f, std::sin(at.o / 2),
                                               std::cos(at.o / 2), lifetimeSec, false);
        return go ? go->GetGUID().GetRawValue() : 0;
    }

    void CrowdWorld::RemoveGo(uint64_t guid)
    {
        Map* map = GetMap();
        if (!map || !guid)
            return;
        if (GameObject* go = map->GetGameObject(ObjectGuid(guid)))
        {
            go->SetRespawnTime(0);
            go->Delete();
        }
    }

    // A reserved chair is not selectable, so no player sits in it while its customer walks over (spec 3.7.4).
    void CrowdWorld::LockChair(uint64_t spawnId, bool locked)
    {
        Map* map = GetMap();
        if (!map || !spawnId)
            return;
        auto const bounds = map->GetGameObjectBySpawnIdStore().equal_range(ObjectGuid::LowType(spawnId));
        for (auto it = bounds.first; it != bounds.second; ++it)
        {
            GameObject* go = it->second;
            if (!go || go->HasGameObjectFlag(GO_FLAG_NOT_SELECTABLE) == locked)
                continue;
            if (locked)
                go->SetGameObjectFlag(GO_FLAG_NOT_SELECTABLE);
            else
                go->RemoveGameObjectFlag(GO_FLAG_NOT_SELECTABLE);
        }
    }

    void CrowdWorld::Players(CrowdRules::Vec3 centre, float radius, std::vector<CrowdRules::PlayerNear>& out)
    {
        Map* map = GetMap();
        if (!map)
            return;
        PlayerScan scan{ centre.x, centre.y, centre.z, radius * radius, out };
        Cell::VisitObjects(centre.x, centre.y, map, scan, radius);
    }

    // ---- CrowdHooks ----------------------------------------------------------------------------------------------

    uint32_t CrowdHooks::NpcArrived(uint8_t personaIdx, uint64_t creatureGuid, uint32_t groupId)
    {
        return *_sink ? (*_sink)->NpcArrived(_cafeId, personaIdx, creatureGuid, groupId) : 0;
    }

    void CrowdHooks::NpcGone(uint32_t orderId)
    {
        if (*_sink)
            (*_sink)->NpcGone(orderId);
    }

    void CrowdHooks::HouseStepStarted(uint32_t orderId, uint8_t stepIndex, uint8_t actionId, uint32_t durMs,
                                      uint64_t workerGuid)
    {
        if (*_sink)
            (*_sink)->HouseStepStarted(orderId, stepIndex, actionId, durMs, workerGuid);
    }

    void CrowdHooks::HouseDone(uint32_t orderId)
    {
        if (*_sink)
            (*_sink)->HouseDone(orderId);
    }

    void CrowdHooks::CupTaken(uint32_t orderId)
    {
        if (*_sink)
            (*_sink)->CupTaken(orderId);
    }

    void CrowdHooks::Delivered(uint32_t orderId)
    {
        if (*_sink)
            (*_sink)->Delivered(orderId);
    }

    // ---- CafeCrowd -----------------------------------------------------------------------------------------------

    CafeCrowd& CafeCrowd::Instance()
    {
        static CafeCrowd instance;
        return instance;
    }

    CafeCrowd::State& CafeCrowd::St() const
    {
        static State state;
        return state;
    }

    void CafeCrowd::SetSink(CrowdSink* sink)
    {
        St().sink = sink;
    }

    // A site placed (again): its engine starts fresh, the named personas' cooldowns carry over. The config is read
    // here (with its error lines) and quietly every minute after, so .bleakhold reload reaches the crowd.
    void CafeCrowd::OnSiteSpawned(CafeSite const& site)
    {
        State& st = St();
        if (st.inUpdate)
        {
            st.later.push_back([this, site] { OnSiteSpawned(site); });
            return;
        }
        st.cfg = ReadConfig(true);
        st.cfgRead = true;
        st.cfgReadMs = static_cast<uint32_t>(GameTime::GetGameTimeMS().count());
        OnSiteDespawned(site.cafeId);
        auto s = std::make_unique<State::Site>(site.cafeId, site.mapId, &st.sink);
        uint64_t const seed = uint64_t(GameTime::GetGameTimeMS().count()) * 0x9E3779B97F4A7C15ull ^ site.cafeId;
        s->engine = std::make_unique<CrowdRules::Engine>(FromSite(site), st.cfg, s->world, s->hooks, seed,
                                                         st.nextGroup);
        st.nextGroup += GroupIdsPerSite;
        if (auto t = st.tracks.find(site.cafeId); t != st.tracks.end())
            s->engine->Restore(t->second);
        CrowdRules::Graph const& aisles = s->engine->Aisles();
        std::vector<std::size_t> const isolated = CrowdRules::IsolatedNodes(aisles);
        if (!isolated.empty())
            LOG_ERROR("module", "[Bleakhold] Cafe {}: {} aisle node(s) reach no other (path_{}): move them or add a "
                "path node between (.cafe status)", site.cafeId, isolated.size(), isolated.front());
        st.sites[site.cafeId] = std::move(s);
    }

    // Customers and cups go, seats are released, house jobs stop; Cafe is told nothing (it runs the close path).
    void CafeCrowd::OnSiteDespawned(uint8_t cafeId)
    {
        State& st = St();
        if (st.inUpdate)
        {
            st.later.push_back([this, cafeId] { OnSiteDespawned(cafeId); });
            return;
        }
        auto it = st.sites.find(cafeId);
        if (it == st.sites.end())
            return;
        it->second->engine->Despawn();
        st.tracks[cafeId] = it->second->engine->PersonaTracks();
        st.sites.erase(it);
    }

    void CafeCrowd::Update(uint32_t nowMs, std::vector<CrowdInputs> const& inputs)
    {
        State& st = St();
        bool refresh = false;
        if (!st.cfgRead || static_cast<uint32_t>(nowMs - st.cfgReadMs) >= CfgRefreshMs)
        {
            st.cfg = ReadConfig(!st.cfgRead);
            st.cfgRead = true;
            st.cfgReadMs = nowMs;
            refresh = true;
        }
        st.inUpdate = true;
        for (auto& [cafeId, site] : st.sites)
        {
            if (refresh)
                site->engine->Configure(st.cfg);
            CrowdRules::Inputs in;   // no inputs for a cafe: it is not open
            for (CrowdInputs const& i : inputs)
                if (i.cafeId == cafeId)
                    in = ToInputs(i);
            site->engine->Update(nowMs, in);
        }
        st.inUpdate = false;
        std::vector<std::function<void()>> later;
        later.swap(st.later);
        for (std::function<void()>& f : later)
            f();
    }

    // The order events go to the cafe whose engine has the order (a customer's, a house job, a counter cup or a
    // delivery).

    void CafeCrowd::OrderTaken(uint32_t orderId, std::string const& orderLine)
    {
        State& st = St();
        if (st.inUpdate)
        {
            st.later.push_back([this, orderId, orderLine] { OrderTaken(orderId, orderLine); });
            return;
        }
        for (auto& [id, site] : st.sites)
            if (site->engine->Owns(orderId))
                site->engine->OrderTaken(orderId, orderLine);
    }

    void CafeCrowd::OrderReturned(uint32_t orderId)
    {
        State& st = St();
        if (st.inUpdate)
        {
            st.later.push_back([this, orderId] { OrderReturned(orderId); });
            return;
        }
        for (auto& [id, site] : st.sites)
            if (site->engine->Owns(orderId))
                site->engine->OrderReturned(orderId);
    }

    void CafeCrowd::OrderServed(uint32_t orderId, char quality, std::string const& thanksLine, uint32_t cupItem,
                                uint32_t cupGo)
    {
        State& st = St();
        if (st.inUpdate)
        {
            st.later.push_back([this, orderId, quality, thanksLine, cupItem, cupGo] {
                OrderServed(orderId, quality, thanksLine, cupItem, cupGo);
            });
            return;
        }
        for (auto& [id, site] : st.sites)
            if (site->engine->Owns(orderId))
                site->engine->OrderServed(orderId, quality, thanksLine, cupItem, cupGo);
    }

    void CafeCrowd::OrderFailed(uint32_t orderId, std::string const& complaintLine)
    {
        State& st = St();
        if (st.inUpdate)
        {
            st.later.push_back([this, orderId, complaintLine] { OrderFailed(orderId, complaintLine); });
            return;
        }
        for (auto& [id, site] : st.sites)
            if (site->engine->Owns(orderId))
                site->engine->OrderFailed(orderId, complaintLine);
    }

    void CafeCrowd::HouseOrderTaken(uint32_t orderId, std::string const& orderLine, std::string const& ownerAnswer)
    {
        State& st = St();
        if (st.inUpdate)
        {
            st.later.push_back([this, orderId, orderLine, ownerAnswer] {
                HouseOrderTaken(orderId, orderLine, ownerAnswer);
            });
            return;
        }
        for (auto& [id, site] : st.sites)
            if (site->engine->Owns(orderId))
                site->engine->HouseOrderTaken(orderId, orderLine, ownerAnswer);
    }

    void CafeCrowd::QueueHouseJob(uint8_t cafeId, HouseJob const& job)
    {
        State& st = St();
        if (st.inUpdate)
        {
            st.later.push_back([this, cafeId, job] { QueueHouseJob(cafeId, job); });
            return;
        }
        if (auto it = st.sites.find(cafeId); it != st.sites.end())
            it->second->engine->QueueHouseJob(ToJob(job));
    }

    void CafeCrowd::CancelHouseJob(uint32_t orderId)
    {
        State& st = St();
        if (st.inUpdate)
        {
            st.later.push_back([this, orderId] { CancelHouseJob(orderId); });
            return;
        }
        for (auto& [id, site] : st.sites)
            if (site->engine->Owns(orderId))
                site->engine->CancelHouseJob(orderId);
    }

    // With no site (or before the first tick): a new order's own time, from the config.
    uint32_t CafeCrowd::HouseEtaSec(uint8_t cafeId, std::optional<uint32_t> orderId) const
    {
        State& st = St();
        if (auto it = st.sites.find(cafeId); it != st.sites.end())
            return it->second->engine->HouseEtaSec(orderId);
        return (st.cfg.houseBaseMs + st.cfg.housePerLineMs * 5 + 999) / 1000;
    }

    void CafeCrowd::PlaceCounterCup(uint8_t cafeId, uint32_t orderId, uint32_t cupGo)
    {
        State& st = St();
        if (st.inUpdate)
        {
            st.later.push_back([this, cafeId, orderId, cupGo] { PlaceCounterCup(cafeId, orderId, cupGo); });
            return;
        }
        if (auto it = st.sites.find(cafeId); it != st.sites.end())
            it->second->engine->PlaceCounterCup(orderId, cupGo);
    }

    void CafeCrowd::RemoveCounterCup(uint32_t orderId)
    {
        State& st = St();
        if (st.inUpdate)
        {
            st.later.push_back([this, orderId] { RemoveCounterCup(orderId); });
            return;
        }
        for (auto& [id, site] : st.sites)
            if (site->engine->Owns(orderId))
                site->engine->RemoveCounterCup(orderId);
    }

    void CafeCrowd::DeliverToSeat(uint8_t cafeId, uint32_t orderId, uint64_t playerGuid, uint32_t cupGo)
    {
        State& st = St();
        if (st.inUpdate)
        {
            st.later.push_back([this, cafeId, orderId, playerGuid, cupGo] {
                DeliverToSeat(cafeId, orderId, playerGuid, cupGo);
            });
            return;
        }
        if (auto it = st.sites.find(cafeId); it != st.sites.end())
            it->second->engine->DeliverToSeat(orderId, playerGuid, cupGo);
    }

    // Said at once (speech changes no crowd state, so it need not wait for the end of a tick).
    void CafeCrowd::StaffSay(uint8_t cafeId, std::string const& role, std::string const& text, bool yell)
    {
        State& st = St();
        if (auto it = st.sites.find(cafeId); it != st.sites.end())
            it->second->engine->StaffSay(role, text, yell);
    }

    bool CafeCrowd::SeatTakenByPlayer(uint8_t cafeId, uint16_t chairSlot) const
    {
        State& st = St();
        auto it = st.sites.find(cafeId);
        return it != st.sites.end() && it->second->engine->SeatTakenByPlayer(chairSlot);
    }

    std::optional<uint16_t> CafeCrowd::PlayerSeat(uint8_t cafeId, uint64_t playerGuid) const
    {
        State& st = St();
        auto it = st.sites.find(cafeId);
        if (it == st.sites.end())
            return std::nullopt;
        return it->second->engine->PlayerSeat(playerGuid);
    }

    std::string CafeCrowd::SpawnNow(uint8_t cafeId, int personaIdx)
    {
        State& st = St();
        auto it = st.sites.find(cafeId);
        if (it == st.sites.end() || st.inUpdate)
            return "That cafe has no crowd running (built, enabled, and BleakholdUi.Cafe.Enable = 1?).";
        using R = CrowdRules::Engine::SpawnNowResult;
        switch (it->second->engine->SpawnNow(personaIdx))
        {
            case R::Spawned:
                return "A customer walks in from the door marker.";
            case R::Closed:
                return "The cafe is not open (paused, closed for safety, or not ticked yet).";
            case R::Full:
                return "No room: the queue or the customer cap is full (Customer.MaxAlive, QueueCap).";
            case R::OtherCafe:
                return "That persona belongs to the other cafe.";
            default:
                return "That persona cannot come (disabled, no display, or nobody eligible now).";
        }
    }

    CrowdStatus CafeCrowd::StatusOf(uint8_t cafeId) const
    {
        CrowdStatus out;
        State& st = St();
        auto it = st.sites.find(cafeId);
        if (it == st.sites.end())
            return out;
        CrowdRules::Engine const& e = *it->second->engine;
        out.running = true;
        out.alive = static_cast<uint32_t>(e.Alive());
        CrowdRules::Graph const& aisles = e.Aisles();
        for (std::size_t i : CrowdRules::IsolatedNodes(aisles))
            if (i < aisles.pts.size())
                out.isolated.push_back(Position(aisles.pts[i].x, aisles.pts[i].y, aisles.pts[i].z));
        return out;
    }
}
