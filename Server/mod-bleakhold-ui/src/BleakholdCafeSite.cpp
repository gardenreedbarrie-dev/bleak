/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The cafe (section 21): placement (section 3.12). .cafe build writes the whole default layout relative to the GM's
 * position and facing into bleakhold_cafe / bleakhold_cafe_piece; every piece spawns as runtime spawn data
 * (ObjectMgr::AddGOData / AddCreData, the World PvP outpost pattern), so no gameobject or creature rows are ever
 * written. The other commands fine-tune one piece or the whole cafe; .gobject move on a cafe piece is undone.
 */

#include "BleakholdCafe.h"
#include "BleakholdMgr.h"
#include "BleakholdUi.h"

#include "CharacterCache.h"
#include "Chat.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameObject.h"
#include "GameTime.h"
#include "GridTerrainData.h"
#include "Log.h"
#include "Map.h"
#include "MapMgr.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "WorldSession.h"
#include "WorldSessionMgr.h"

#include <algorithm>
#include <cmath>
#include <list>

namespace Bleakhold
{
    namespace D = CafeData;
    namespace R = CafeRules;

    namespace
    {
        constexpr uint16_t FirstAddedSlot = 200;
        constexpr uint32_t MarkerSec = 120;
        constexpr float SnapProbeUp = 2.0f;
        constexpr float SnapSearch = 6.0f;
        constexpr float DoorWarnYd = 20.0f;

        float Deg(float rad) { return rad * 180.0f / R::Pi; }
        float Rad(float deg) { return deg * R::Pi / 180.0f; }

        D::Cafe const& Info(uint8_t id) { return D::Cafes[id == 2 ? 1 : 0]; }

        D::LayoutPiece const* LayoutOf(uint8_t cafeId, uint16_t slot)
        {
            for (D::LayoutPiece const& p : D::Layout)
                if (p.cafeId == cafeId && p.slot == slot)
                    return &p;
            return nullptr;
        }

        D::LayoutPiece const* FirstLayoutRole(uint8_t cafeId, std::string_view prefix)
        {
            for (D::LayoutPiece const& p : D::Layout)
                if (p.cafeId == cafeId && p.role.substr(0, prefix.size()) == prefix)
                    return &p;
            return nullptr;
        }

        bool StartsWith(std::string const& s, std::string_view prefix) { return s.rfind(prefix, 0) == 0; }

        // the roles a GM may move but never remove: the stations, the counter and back bar, the markers, the staff
        bool Fixed(std::string const& role)
        {
            return StartsWith(role, "station_") || role == "counter" || role == "backbar" || role == "order_spot" ||
                role == "pickup_spot" || role == "door" || StartsWith(role, "queue_") || StartsWith(role, "path_") ||
                StartsWith(role, "staff_");
        }

        std::string Fmt(float v)
        {
            char buf[32];
            std::snprintf(buf, sizeof(buf), "%.2f", v);
            return buf;
        }

        uint32_t AddedEntry(uint8_t cafeId, std::string_view role)
        {
            bool const sw = cafeId == 1;
            if (role == "chair")
                return sw ? 909360 : 909371;
            if (role == "table")
                return sw ? 909362 : 909372;
            if (role == "kegtable")
                return sw ? 909367 : 909377;
            if (role == "parasol")
                return sw ? 909316 : 909317;
            return 0;
        }
    }

    uint8_t Cafe::CafeIdOf(std::string_view city)
    {
        for (D::Cafe const& c : D::Cafes)
            if (c.cityKey == city)
                return c.id;
        return 0;
    }

    Map* Cafe::MapOf(CafeRt const& c) const
    {
        return c.placed ? sMapMgr->FindBaseMap(c.map) : nullptr;
    }

    void Cafe::Log(Player* gm, std::string const& what)
    {
        LOG_INFO("module", "[Bleakhold] Cafe: {} {}", gm ? gm->GetName() : std::string("console"), what);
    }

    // =============================================================================================================
    // Positions
    // =============================================================================================================
    float Cafe::FloorZ(CafeRt const& c, Piece const& p) const
    {
        if (p.link)
        {
            auto it = c.pieces.find(p.link);
            if (it != c.pieces.end())
                return it->second.z;
        }
        return R::PieceFloorZ(p.snap, p.z, p.u);
    }

    // The world position from f/l/u/turn (section 3.12.2): on-counter pieces sit on their parent's top, snap pieces on the
    // ground when it is near the height asked for (the anchor's plus u) and seen from the anchor, else at that height.
    void Cafe::Recompute(CafeRt& c, Piece& p)
    {
        R::Pose const w = R::ToWorld(c.anchor, p.f, p.l, p.u, p.turn);
        p.x = w.x;
        p.y = w.y;
        p.o = w.o;
        p.z = w.z;
        if (p.link)
        {
            auto it = c.pieces.find(p.link);
            if (it != c.pieces.end())
                p.z = it->second.z + p.u;
            return;
        }
        if (!p.snap)
            return;
        Map* map = sMapMgr->FindBaseMap(c.map);
        if (!map)
            return;
        float const ground = map->GetHeight(PHASEMASK_NORMAL, w.x, w.y, c.anchor.z + p.u + SnapProbeUp, true, SnapSearch);
        bool const valid = ground > INVALID_HEIGHT;
        bool const los = valid && map->isInLineOfSight(c.anchor.x, c.anchor.y, c.anchor.z + SnapProbeUp, w.x, w.y,
            ground + SnapProbeUp, PHASEMASK_NORMAL, LINEOFSIGHT_ALL_CHECKS, VMAP::ModelIgnoreFlags::Nothing);
        p.z = R::SnapZ(valid, ground, c.anchor.z + p.u, los);
    }

    // =============================================================================================================
    // Spawning
    // =============================================================================================================
    GameObject* Cafe::PieceObject(CafeRt const& c, Piece const& p) const
    {
        Map* map = MapOf(c);
        if (!map || !p.spawnId || p.creature)
            return nullptr;
        auto bounds = map->GetGameObjectBySpawnIdStore().equal_range(p.spawnId);
        return bounds.first == bounds.second ? nullptr : bounds.first->second;
    }

    void Cafe::SpawnPiece(CafeRt& c, Piece& p)
    {
        if (p.spawnId || !p.enabled || !p.entry || p.creature)
            return;
        uint32_t const entry = R::PieceEntry(p.entry, _cfg.useNewArt && _newArtOk);
        float const half = p.o / 2.0f;
        p.spawnId = sObjectMgr->AddGOData(entry, c.map, p.x, p.y, p.z, p.o, 0, 0.0f, 0.0f, std::sin(half), std::cos(half));
        p.spawnedEntry = entry;
        if (!p.spawnId)
            LOG_ERROR("module", "[Bleakhold] Cafe: piece {} ({}) of {} could not be spawned (gameobject_template {})", p.slot,
                p.role, Info(c.id).name, entry);
    }

    void Cafe::DespawnPiece(CafeRt& c, Piece& p)
    {
        if (!p.spawnId)
            return;
        if (Map* map = sMapMgr->FindBaseMap(c.map))
        {
            if (p.creature)
            {
                // the OPvPCapturePoint::DelCreature way: DespawnOrUnsummon would leave a dead copy in the world with
                // Respawn.ForceCompatibilityMode = 1 (Creature::RemoveCorpse), which respawns from the creature
                // data deleted below (a null CreatureData in Creature::Respawn)
                auto bounds = map->GetCreatureBySpawnIdStore().equal_range(p.spawnId);
                for (auto itr = bounds.first; itr != bounds.second;)
                {
                    Creature* cr = itr->second;
                    ++itr;
                    cr->SetRespawnTime(0);
                    cr->RemoveCorpse();
                    cr->AddObjectToRemoveList();
                }
            }
            else
            {
                auto bounds = map->GetGameObjectBySpawnIdStore().equal_range(p.spawnId);
                for (auto itr = bounds.first; itr != bounds.second;)
                {
                    GameObject* go = itr->second;
                    ++itr;
                    go->SetRespawnTime(0);
                    go->Delete();
                }
            }
        }
        if (p.creature)
            sObjectMgr->DeleteCreatureData(p.spawnId);
        else
            sObjectMgr->DeleteGOData(p.spawnId);
        p.spawnId = 0;
        p.spawnedEntry = 0;
    }

    void Cafe::SpawnStaff(CafeRt& c)
    {
        for (auto& [slot, p] : c.pieces)
        {
            if (!p.creature || p.spawnId || !p.enabled || !p.entry)
                continue;
            p.spawnId = sObjectMgr->AddCreData(p.entry, c.map, p.x, p.y, p.z, p.o, 0);
            p.spawnedEntry = p.entry;
            if (!p.spawnId)
                LOG_ERROR("module", "[Bleakhold] Cafe: staff {} of {} could not be spawned (creature_template {})", p.role,
                    Info(c.id).name, p.entry);
        }
    }

    void Cafe::DespawnStaff(CafeRt& c)
    {
        for (auto& [slot, p] : c.pieces)
            if (p.creature)
                DespawnPiece(c, p);
    }

    void Cafe::SpawnSite(CafeRt& c)
    {
        for (auto& [slot, p] : c.pieces)
            SpawnPiece(c, p);
        if (Enabled() && c.enabled)
            SpawnStaff(c);
        c.spawned = true;
    }

    void Cafe::DespawnSite(CafeRt& c)
    {
        if (c.crowdSpawned)
        {
            CafeCrowd::Instance().OnSiteDespawned(c.id);
            c.crowdSpawned = false;
        }
        for (auto& [slot, p] : c.pieces)
            DespawnPiece(c, p);
        c.spawned = false;
    }

    // The CafeSite of the crowd (BleakholdCafeTypes.h), from the pieces as they stand now.
    void Cafe::BuildSite(CafeRt& c)
    {
        CafeSite s;
        s.cafeId = c.id;
        s.mapId = c.map;
        s.phaseMask = PHASEMASK_NORMAL;
        s.team = c.id == 1 ? TEAM_ALLIANCE : TEAM_HORDE;
        s.anchor = Position(c.anchor.x, c.anchor.y, c.anchor.z, c.anchor.o);
        std::map<std::string, Position> queue;
        D::LayoutPiece const* kegDefault = FirstLayoutRole(c.id, "kegtable");
        for (auto const& [slot, p] : c.pieces)
        {
            if (!p.enabled)
                continue;
            Position const pos(p.x, p.y, p.z, p.o);
            D::LayoutPiece const* lay = LayoutOf(c.id, slot);
            D::GameObject const* go = p.entry && !p.creature ? R::CatalogueGo(p.entry) : nullptr;
            if (p.role == "order_spot")
                s.orderSpot = pos;
            else if (p.role == "pickup_spot")
                s.pickupSpot = pos;
            else if (p.role == "door")
                s.door = pos;
            else if (StartsWith(p.role, "queue_"))
                queue[p.role] = pos;
            else if (StartsWith(p.role, "path"))
                s.nodes.push_back(pos);
            else if (StartsWith(p.role, "chair") && go)
            {
                CafeSite::Chair ch;
                ch.slot = slot;
                ch.table = p.link;
                R::Pose const seat = R::ChairSlot({ p.x, p.y, p.z, p.o }, go->scale, 0, go->slots);
                ch.seat = Position(seat.x, seat.y, seat.z, seat.o);
                // a chair faces its table: away from it is behind the seat
                ch.approach = Position(seat.x - D::ApproachYd * std::cos(seat.o), seat.y - D::ApproachYd * std::sin(seat.o),
                    seat.z, seat.o);
                ch.height = go->seatHeight;
                ch.slots = go->slots;
                ch.spawnId = p.spawnId;
                s.chairs.push_back(ch);
            }
            else if (StartsWith(p.role, "kegtable"))
            {
                D::LayoutPiece const* stand = lay && lay->standCount ? lay : kegDefault;
                if (stand && stand->standCount)
                {
                    R::Pose const sp = R::ToWorld({ p.x, p.y, p.z, p.o }, stand->stand[0], stand->stand[1], 0, 0);
                    s.kegSpots.push_back(Position(sp.x, sp.y, p.z, sp.o));
                }
            }
            else if (StartsWith(p.role, "table") && go)
                s.tableTops.push_back(Position(p.x, p.y, p.z + go->topHeight, p.o));
            if (StartsWith(p.role, "staff_"))
                s.staff.push_back({ p.role, p.entry, p.spawnId, pos });
            // the footprint of every solid piece (rugs are floor decals)
            float halfW = 0, halfD = 0;
            bool decal = false;
            if (lay && lay->entry == p.entry)
            {
                halfW = lay->halfW;
                halfD = lay->halfD;
                decal = lay->decal;
            }
            else if (go)
            {
                halfW = go->halfW;
                halfD = go->halfD;
                decal = go->decal;
            }
            if (!decal && halfW > 0 && halfD > 0)
                s.footprints.push_back({ p.x, p.y, halfW, halfD, p.o });
            // a station's two work spots, in its own frame (a nudged station keeps them)
            if (lay && lay->station)
            {
                int const idx = D::StationIndex(lay->station);
                if (idx >= 0)
                {
                    StationSpots& st = s.stations[static_cast<std::size_t>(idx)];
                    st.station = lay->station;
                    st.slot = slot;
                    st.objX = p.x;
                    st.objY = p.y;
                    float const floor = FloorZ(c, p);
                    for (uint8_t i = 0; i < lay->workCount && i < st.spots.size(); ++i)
                    {
                        R::Pose const w = R::WorkSpot({ p.x, p.y, p.z, p.o }, floor, lay->work[i][0], lay->work[i][1]);
                        st.spots[i] = Position(w.x, w.y, w.z, w.o);
                    }
                }
            }
        }
        for (uint16_t q = 1; q <= 8; ++q)
        {
            auto it = queue.find("queue_" + std::to_string(q));
            if (it != queue.end())
                s.queueSlots.push_back(it->second);
        }
        c.site = std::move(s);
    }

    // After a layout change: the crowd gets the new site (its customers leave, the NPC orders go with them). The new
    // engine starts empty, so the player orders it held come back: the house makes its jobs again from the first step,
    // and the ready ones get their counter cup (table service is asked again when the customer is seated).
    void Cafe::SiteChanged(CafeRt& c)
    {
        BuildSite(c);
        if (!c.crowdSpawned)
            return;
        DropNpcOrders(c);
        CafeCrowd::Instance().OnSiteDespawned(c.id);
        CafeCrowd::Instance().OnSiteSpawned(c.site);
        uint64_t const now = Mgr::NowMs();
        for (uint32_t id : std::vector<uint32_t>(c.queue))   // the house's player orders in their queue order
        {
            Order* o = OrderOf(id);
            if (!o || R::AfterRespawn(o->kind, o->state, o->cupOnCounter) != R::Respawned::RequeueHouseJob)
                continue;
            o->houseStep = 0;
            o->houseStepMs = 0;
            o->houseStartMs = now;
            HouseJob const job = HouseJobOf(*o);
            uint8_t const cafeId = c.id;
            CrowdCall([cafeId, job]() { CafeCrowd::Instance().QueueHouseJob(cafeId, job); });
            SendOrderState(*o);
        }
        for (auto& [id, o] : _orders)
        {
            if (o.cafeId != c.id || o.kind != 'P' || o.state != 'R')
                continue;
            o.deliverSent = false;
            if (R::AfterRespawn(o.kind, o.state, o.cupOnCounter) != R::Respawned::PlaceCup)
                continue;
            D::Recipe const* r = D::FindRecipe(o.recipeId);
            uint32_t const cupGo = r ? R::PieceEntry(r->tableCup, _cfg.useNewArt && _newArtOk) : 0;
            uint8_t const cafeId = c.id;
            uint32_t const orderId = id;
            CrowdCall([cafeId, orderId, cupGo]() { CafeCrowd::Instance().PlaceCounterCup(cafeId, orderId, cupGo); });
        }
        c.atDirty = true;
    }

    // =============================================================================================================
    // GM commands (section 3.12.1)
    // =============================================================================================================
    bool Cafe::CheckGm(Player* gm, CafeRt const& c, Reply const& say)
    {
        D::Cafe const& cd = Info(c.id);
        if (!gm || !gm->IsInWorld())
        {
            say("Use this in game, standing where a customer orders, facing the counter spot.");
            return false;
        }
        if (gm->GetTransport())
        {
            say("Get off the transport first.");
            return false;
        }
        if (gm->GetPhaseMask() != PHASEMASK_NORMAL)
        {
            say("You are in another phase; use the normal phase.");
            return false;
        }
        if (gm->GetMapId() != cd.map || gm->GetZoneId() != cd.zone)
        {
            say(std::string(cd.name) + " goes in " + std::string(cd.cityName) + " (map " + std::to_string(cd.map) + ", zone " +
                std::to_string(cd.zone) + "); you are on map " + std::to_string(gm->GetMapId()) + ", zone " +
                std::to_string(gm->GetZoneId()) + ".");
            return false;
        }
        if (!gm->GetMap() || !gm->GetMap()->IsWorldMap() || gm->GetMap()->Instanceable())
        {
            say("Cafes are placed on the open-world continents only.");
            return false;
        }
        return true;
    }

    std::string Cafe::PieceLine(CafeRt const& c, Piece const& p) const
    {
        (void)c;
        return "#" + std::to_string(p.slot) + " " + p.role + (p.entry ? " " + std::to_string(p.entry) : std::string()) +
            " f " + Fmt(p.f) + " l " + Fmt(p.l) + " u " + Fmt(p.u) + " turn " + Fmt(Deg(p.turn)) + " at " + Fmt(p.x) + " " +
            Fmt(p.y) + " " + Fmt(p.z) + (p.entry ? (p.spawnId ? " spawned" : " not spawned") : " (marker)") +
            (p.enabled ? "" : " (disabled)");
    }

    void Cafe::CmdBuild(Player* gm, uint8_t cafeId, bool force, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !CheckGm(gm, *c, say))
            return;
        D::Cafe const& cd = Info(cafeId);
        bool const exists = c->placed || WorldDatabase.Query("SELECT 1 FROM `bleakhold_cafe` WHERE `id` = {}", cafeId);
        if (exists && !force)
        {
            say(std::string(cd.name) + " is built already. .cafe build " + std::string(cd.cityKey) +
                " force removes it and builds it again here.");
            return;
        }
        if (exists)
        {
            ClosePath(*c, static_cast<char>(CafeShiftEnd::Closed));
            DespawnSite(*c);
            if (!DeleteSiteRows(cafeId))
            {
                say("The old rows could not be removed (see the sql.sql log); nothing was built.");
                return;
            }
        }
        c->pieces.clear();
        c->placed = false;
        c->map = gm->GetMapId();
        c->zone = cd.zone;
        c->anchor = { gm->GetPositionX(), gm->GetPositionY(), gm->GetPositionZ(), gm->GetOrientation() };
        c->layoutVer = 1;
        c->enabled = false;
        c->placedBy = R::NameForColumn(gm->GetName());   // a two-part or accented name stays whole
        c->placedAt = NowSec();
        // slot order: a piece's parent (counter, back bar, table) always has a lower slot
        for (D::LayoutPiece const& l : D::Layout)
        {
            if (l.cafeId != cafeId)
                continue;
            Piece p;
            p.slot = l.slot;
            p.role = std::string(l.role);
            p.entry = l.entry;
            p.link = l.link;
            p.f = l.f;
            p.l = l.l;
            p.u = l.u;
            p.turn = l.turn;
            p.snap = l.snap;
            p.enabled = true;
            p.creature = l.creature;
            c->pieces[p.slot] = p;
        }
        for (auto& [slot, p] : c->pieces)
            Recompute(*c, p);
        // one transaction, committed at once, then read back: a mismatch is an error and nothing spawns
        WorldDatabaseTransaction t = WorldDatabase.BeginTransaction();
        std::string by = c->placedBy;
        WorldDatabase.EscapeString(by);
        t->Append("INSERT INTO `bleakhold_cafe` (`id`, `map`, `zone`, `x`, `y`, `z`, `o`, `layout_ver`, `enabled`, `placed_by`, "
            "`placed_at`) VALUES ({}, {}, {}, {}, {}, {}, {}, {}, 0, '{}', {})", cafeId, c->map, c->zone, c->anchor.x,
            c->anchor.y, c->anchor.z, c->anchor.o, c->layoutVer, by, c->placedAt);
        for (auto const& [slot, p] : c->pieces)
            t->Append("INSERT INTO `bleakhold_cafe_piece` (`cafe_id`, `slot`, `role`, `entry`, `link`, `f`, `l`, `u`, `turn`, "
                "`x`, `y`, `z`, `o`, `snap`, `enabled`) VALUES ({}, {}, '{}', {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, 1)",
                cafeId, slot, p.role, p.entry, p.link, p.f, p.l, p.u, p.turn, p.x, p.y, p.z, p.o, p.snap ? 1 : 0);
        WorldDatabase.DirectCommitTransaction(t);
        QueryResult n = WorldDatabase.Query("SELECT COUNT(*) FROM `bleakhold_cafe_piece` WHERE `cafe_id` = {}", cafeId);
        bool const ok = WorldDatabase.Query("SELECT 1 FROM `bleakhold_cafe` WHERE `id` = {}", cafeId) && n &&
            (*n)[0].Get<uint64>() == c->pieces.size();
        if (!ok)
        {
            LOG_ERROR("module", "[Bleakhold] Cafe: the rows of {} did not read back after .cafe build", cd.name);
            say("The cafe could not be saved (see the sql.sql log); nothing was spawned.");
            c->pieces.clear();
            DeleteSiteRows(cafeId);
            return;
        }
        c->placed = true;
        c->open = 3;
        SpawnSite(*c);
        BuildSite(*c);
        MarkCafeList();
        Log(gm, "build " + std::string(cd.cityKey) + (force ? " force" : "") + " at " + Fmt(c->anchor.x) + " " +
            Fmt(c->anchor.y) + " " + Fmt(c->anchor.z) + " o " + Fmt(c->anchor.o));
        say(std::string(cd.name) + " is built: " + std::to_string(c->pieces.size()) + " pieces. Now check with .cafe show " +
            std::string(cd.cityKey) + ", fine-tune with .cafe nudge, then .cafe enable " + std::string(cd.cityKey) + " 1.");
    }

    void Cafe::CmdList(uint8_t cafeId, Reply const& say)
    {
        for (CafeRt& c : _cafes)
        {
            if (cafeId && c.id != cafeId)
                continue;
            D::Cafe const& cd = Info(c.id);
            if (!c.placed)
            {
                say(std::string(cd.name) + ": not built (.cafe build " + std::string(cd.cityKey) + ").");
                continue;
            }
            say(std::string(cd.name) + ": anchor " + Fmt(c.anchor.x) + " " + Fmt(c.anchor.y) + " " + Fmt(c.anchor.z) + " o " +
                Fmt(Deg(c.anchor.o)) + " on map " + std::to_string(c.map) + ", " + std::to_string(c.pieces.size()) + " pieces");
            for (auto const& [slot, p] : c.pieces)
                say(PieceLine(c, p));
        }
    }

    void Cafe::CmdShow(Player* gm, uint8_t cafeId, bool show, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !c->placed)
            return say("That cafe is not built.");
        if (!gm || !gm->IsInWorld() || gm->GetMapId() != c->map)
            return say("Stand in the cafe's city to see its markers.");
        Map* map = gm->GetMap();
        if (!show)
        {
            uint32_t removed = 0;
            for (uint32_t entry : { D::MarkerStationSpot, D::MarkerQueue, D::MarkerPath, D::MarkerOther })
            {
                std::list<GameObject*> list;
                gm->GetGameObjectListWithEntryInGrid(list, entry, 80.0f);
                for (GameObject* go : list)
                {
                    if (go->GetSpawnId())
                        continue;   // never a spawned piece
                    go->SetRespawnTime(0);
                    go->Delete();
                    ++removed;
                }
            }
            return say(std::to_string(removed) + " markers removed.");
        }
        auto mark = [&](uint32_t entry, float x, float y, float z, float o) {
            map->SummonGameObject(entry, x, y, z, o, 0.0f, 0.0f, std::sin(o / 2.0f), std::cos(o / 2.0f), MarkerSec);
        };
        uint32_t count = 0;
        for (auto const& [slot, p] : c->pieces)
        {
            D::LayoutPiece const* lay = LayoutOf(c->id, slot);
            bool const marker = !p.entry && !p.creature;
            if (marker)
            {
                uint32_t const entry = StartsWith(p.role, "queue_") || p.role == "order_spot" || p.role == "pickup_spot" ?
                    D::MarkerQueue : (StartsWith(p.role, "path") || p.role == "door") ? D::MarkerPath : D::MarkerOther;
                mark(entry, p.x, p.y, p.z, p.o);
                say(PieceLine(*c, p));
                ++count;
            }
            if (lay && lay->station)
                for (uint8_t i = 0; i < lay->workCount; ++i)
                {
                    R::Pose const w = R::WorkSpot({ p.x, p.y, p.z, p.o }, FloorZ(*c, p), lay->work[i][0], lay->work[i][1]);
                    mark(D::MarkerStationSpot, w.x, w.y, w.z, w.o);
                    say("#" + std::to_string(slot) + " " + p.role + " work spot " + std::to_string(i + 1) + " at " + Fmt(w.x) +
                        " " + Fmt(w.y) + " " + Fmt(w.z));
                    ++count;
                }
        }
        for (CafeSite::Chair const& ch : c->site.chairs)
        {
            mark(D::MarkerPath, ch.seat.GetPositionX(), ch.seat.GetPositionY(), ch.seat.GetPositionZ(), ch.seat.GetOrientation());
            ++count;
        }
        if (std::hypot(c->site.door.GetPositionX() - c->anchor.x, c->site.door.GetPositionY() - c->anchor.y) < DoorWarnYd)
            say("Warning: the door marker is within 20 yd of the anchor; move it out of sight with .cafe here " +
                std::string(Info(c->id).cityKey) + " 20.");
        say(std::to_string(count) + " markers for 120 s (.cafe hide " + std::string(Info(c->id).cityKey) + " removes them).");
    }

    void Cafe::CmdNear(Player* gm, uint8_t cafeId, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !c->placed || !gm)
            return say("That cafe is not built.");
        std::vector<std::pair<float, Piece const*>> near;
        for (auto const& [slot, p] : c->pieces)
            near.emplace_back(gm->GetExactDist(p.x, p.y, p.z), &p);
        std::sort(near.begin(), near.end(), [](auto const& a, auto const& b) { return a.first < b.first; });
        for (std::size_t i = 0; i < near.size() && i < 3; ++i)
            say(Fmt(near[i].first) + " yd: " + PieceLine(*c, *near[i].second));
    }

    Cafe::Piece* Cafe::PieceOf(CafeRt& c, std::string_view role)
    {
        for (auto& [slot, p] : c.pieces)
            if (p.role == role)
                return &p;
        return nullptr;
    }

    Cafe::Piece* Cafe::NearestPiece(CafeRt& c, Player* gm)
    {
        Piece* best = nullptr;
        float bestD = 0;
        for (auto& [slot, p] : c.pieces)
        {
            float const d = gm->GetExactDist(p.x, p.y, p.z);
            if (!best || d < bestD)
            {
                best = &p;
                bestD = d;
            }
        }
        return best;
    }

    std::optional<Cafe::Piece*> Cafe::PickPiece(CafeRt& c, Player* gm, std::optional<uint16_t> slot, Reply const& say)
    {
        if (!c.placed)
        {
            say("That cafe is not built.");
            return std::nullopt;
        }
        if (slot && *slot)
        {
            auto it = c.pieces.find(*slot);
            if (it == c.pieces.end())
            {
                say("There is no slot " + std::to_string(*slot) + " (.cafe list).");
                return std::nullopt;
            }
            return &it->second;
        }
        if (!gm)
        {
            say("Name the slot on the console.");
            return std::nullopt;
        }
        Piece* p = NearestPiece(c, gm);
        if (!p)
        {
            say("No piece near you.");
            return std::nullopt;
        }
        return p;
    }

    // One piece moved: its row, its spawn, the pieces on top of it, the crowd's site; a running step at a moved station
    // stops (no penalty).
    namespace
    {
        void KeepPrev(Cafe const&, float& pf, float& pl, float& pu, float& pt, bool& has, float f, float l, float u, float t)
        {
            pf = f;
            pl = l;
            pu = u;
            pt = t;
            has = true;
        }
    }

    void Cafe::CmdHere(Player* gm, uint8_t cafeId, std::optional<uint16_t> slot, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !gm || !gm->IsInWorld() || gm->GetMapId() != c->map)
            return say("Stand in the cafe's city, where the piece should go.");
        std::optional<Piece*> picked = PickPiece(*c, gm, slot, say);
        if (!picked)
            return;
        Piece& p = **picked;
        KeepPrev(*this, p.pf, p.pl, p.pu, p.pturn, p.hasPrev, p.f, p.l, p.u, p.turn);
        R::Local const l = R::ToLocal(c->anchor, { gm->GetPositionX(), gm->GetPositionY(), gm->GetPositionZ(),
            gm->GetOrientation() });
        p.f = l.f;
        p.l = l.l;
        p.turn = l.turn;
        if (!p.link)
            p.u = l.u;   // the GM's height: a snap piece stands on the ground found near it, or there when none is seen
        c->lastChanged = p.slot;
        AnchorMoved(*c, gm, "here " + std::string(Info(cafeId).cityKey) + " " + std::to_string(p.slot), say);
    }

    void Cafe::CmdNudge(Player* gm, uint8_t cafeId, std::optional<uint16_t> slot, float fwd, float left, float up,
        float turnDeg, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c)
            return;
        std::optional<Piece*> picked = PickPiece(*c, gm, slot, say);
        if (!picked)
            return;
        Piece& p = **picked;
        KeepPrev(*this, p.pf, p.pl, p.pu, p.pturn, p.hasPrev, p.f, p.l, p.u, p.turn);
        p.f += fwd;
        p.l += left;
        p.u += up;
        p.turn = R::Signed(p.turn + Rad(turnDeg));
        c->lastChanged = p.slot;
        AnchorMoved(*c, gm, "nudge " + std::string(Info(cafeId).cityKey) + " " + std::to_string(p.slot) + " " + Fmt(fwd) + " " +
            Fmt(left) + " " + Fmt(up) + " " + Fmt(turnDeg), say);
    }

    void Cafe::CmdTurn(Player* gm, uint8_t cafeId, std::optional<uint16_t> slot, float deg, Reply const& say)
    {
        CmdNudge(gm, cafeId, slot, 0, 0, 0, deg, say);
    }

    void Cafe::CmdUndo(Player* gm, uint8_t cafeId, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !c->placed)
            return say("That cafe is not built.");
        auto it = c->pieces.find(c->lastChanged);
        if (it == c->pieces.end() || !it->second.hasPrev)
            return say("Nothing to undo.");
        Piece& p = it->second;
        std::swap(p.f, p.pf);
        std::swap(p.l, p.pl);
        std::swap(p.u, p.pu);
        std::swap(p.turn, p.pturn);
        AnchorMoved(*c, gm, "undo " + std::string(Info(cafeId).cityKey) + " " + std::to_string(p.slot), say);
    }

    // Recomputes every piece from f/l/u/turn after the anchor or a piece changed, writes the rows that moved and
    // respawns those pieces.
    void Cafe::AnchorMoved(CafeRt& c, Player* gm, std::string const& what, Reply const& say)
    {
        std::vector<uint16_t> moved;
        std::set<char> stations;
        for (auto& [slot, p] : c.pieces)
        {
            float const ox = p.x, oy = p.y, oz = p.z, oo = p.o;
            Recompute(c, p);
            if (ox == p.x && oy == p.y && oz == p.z && oo == p.o && slot != c.lastChanged)
                continue;
            moved.push_back(slot);
            if (D::LayoutPiece const* lay = LayoutOf(c.id, slot); lay && lay->station)
                stations.insert(lay->station);
            if (p.spawnId)
            {
                DespawnPiece(c, p);
                if (p.creature)
                {
                    if (Enabled() && c.enabled)
                        SpawnStaff(c);
                }
                else
                    SpawnPiece(c, p);
            }
        }
        if (!SavePieceRows(c, moved))
            say("Some rows could not be written (see the sql.sql log); .cafe reload shows what the table holds.");
        // a running step at a moved station stops, without a penalty
        for (auto& [g, s] : _shifts)
        {
            if (s.cafeId != c.id)
                continue;
            Player* p = ObjectAccessor::FindConnectedPlayer(ObjectGuid(g));
            for (Ticket& t : s.tickets)
                if (t.step.active)
                    if (D::Action const* a = D::FindAction(t.step.action); a && stations.count(a->station))
                        AbortStep(p, s, t, p != nullptr);
        }
        SiteChanged(c);
        Log(gm, what);
        say(std::to_string(moved.size()) + " piece(s) moved. .cafe undo " + std::string(Info(c.id).cityKey) +
            " puts the last one back.");
    }

    void Cafe::CmdRotate(Player* gm, uint8_t cafeId, float deg, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !c->placed)
            return say("That cafe is not built.");
        ClosePath(*c, static_cast<char>(CafeShiftEnd::Closed));
        c->anchor.o = R::Norm(c->anchor.o + Rad(deg));
        if (!SaveCafeRow(*c))
            return say("The cafe row could not be written (see the sql.sql log).");
        c->lastChanged = 0;
        AnchorMoved(*c, gm, "rotate " + std::string(Info(cafeId).cityKey) + " " + Fmt(deg), say);
    }

    void Cafe::CmdShift(Player* gm, uint8_t cafeId, float fwd, float left, float up, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !c->placed)
            return say("That cafe is not built.");
        ClosePath(*c, static_cast<char>(CafeShiftEnd::Closed));
        R::Pose const a = R::ToWorld(c->anchor, fwd, left, up, 0);
        c->anchor = { a.x, a.y, a.z, c->anchor.o };
        if (!SaveCafeRow(*c))
            return say("The cafe row could not be written (see the sql.sql log).");
        c->lastChanged = 0;
        AnchorMoved(*c, gm, "shift " + std::string(Info(cafeId).cityKey) + " " + Fmt(fwd) + " " + Fmt(left) + " " + Fmt(up), say);
    }

    void Cafe::CmdSnap(Player* gm, uint8_t cafeId, std::optional<uint16_t> slot, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !c->placed)
            return say("That cafe is not built.");
        if (slot && *slot)
        {
            auto it = c->pieces.find(*slot);
            if (it == c->pieces.end())
                return say("There is no slot " + std::to_string(*slot) + ".");
            KeepPrev(*this, it->second.pf, it->second.pl, it->second.pu, it->second.pturn, it->second.hasPrev, it->second.f,
                it->second.l, it->second.u, it->second.turn);
            it->second.snap = true;
            if (!it->second.link)
                it->second.u = 0;   // snapped as .cafe build does, around the anchor's height (.cafe undo goes back)
            c->lastChanged = *slot;
        }
        else
            c->lastChanged = 0;
        AnchorMoved(*c, gm, "snap " + std::string(Info(cafeId).cityKey) + (slot ? " " + std::to_string(*slot) : std::string()),
            say);
    }

    void Cafe::CmdAdd(Player* gm, uint8_t cafeId, std::string_view role, uint32_t entry, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !c->placed)
            return say("That cafe is not built.");
        if (!gm || !gm->IsInWorld() || gm->GetMapId() != c->map)
            return say("Stand in the cafe's city, where the piece should go.");
        if (role != "chair" && role != "table" && role != "decor" && role != "kegtable" && role != "parasol" && role != "path")
            return say("Roles: chair, table, decor, kegtable, parasol, path.");
        if (role == "decor")
        {
            // any cafe template: new art, furniture, a marker, or a stand-in (new-art entry + 30), which keeps its
            // entry and so spawns as itself whatever UseNewArt says (V21b)
            if (entry < D::GameObjectFirst || entry > D::GameObjectLast || !R::CatalogueGo(entry))
                return say("decor takes a cafe gameobject entry (909300-909379), for example a stand-in to look at.");
        }
        else if (role != "path")
            entry = AddedEntry(cafeId, role);
        else
            entry = 0;
        uint16_t slot = FirstAddedSlot;
        for (auto const& [s, p] : c->pieces)
            if (s >= slot)
                slot = static_cast<uint16_t>(s + 1);
        Piece p;
        p.slot = slot;
        p.role = std::string(role);
        p.entry = entry;
        R::Local const l = R::ToLocal(c->anchor, { gm->GetPositionX(), gm->GetPositionY(), gm->GetPositionZ(),
            gm->GetOrientation() });
        p.f = l.f;
        p.l = l.l;
        p.u = l.u;   // the GM's height, as .cafe here: the ground found near it, or there when none is seen
        p.turn = l.turn;
        p.snap = true;
        c->pieces[slot] = p;
        Recompute(*c, c->pieces[slot]);
        if (!SavePieceRows(*c, { slot }))
        {
            c->pieces.erase(slot);
            return say("The piece could not be saved (see the sql.sql log).");
        }
        SpawnPiece(*c, c->pieces[slot]);
        SiteChanged(*c);
        Log(gm, "add " + std::string(Info(cafeId).cityKey) + " " + std::string(role) + " " + std::to_string(entry) +
            " as slot " + std::to_string(slot));
        say("Added " + PieceLine(*c, c->pieces[slot]) + ".");
    }

    void Cafe::CmdRemove(Player* gm, uint8_t cafeId, uint16_t slot, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !c->placed)
            return say("That cafe is not built.");
        auto it = c->pieces.find(slot);
        if (it == c->pieces.end())
            return say("There is no slot " + std::to_string(slot) + ".");
        if (Fixed(it->second.role) && slot < FirstAddedSlot)
            return say("A station, the counter, the back bar, a marker or the staff can only be moved, never removed.");
        for (auto const& [s, p] : c->pieces)
            if (p.link == slot)
                return say("Slot " + std::to_string(s) + " stands on it; remove that first.");
        if (!DeletePieceRow(cafeId, slot))
            return say("The row could not be deleted (see the sql.sql log).");
        DespawnPiece(*c, it->second);
        c->pieces.erase(it);
        SiteChanged(*c);
        Log(gm, "remove " + std::string(Info(cafeId).cityKey) + " " + std::to_string(slot));
        say("Slot " + std::to_string(slot) + " removed.");
    }

    void Cafe::CmdEnable(Player* gm, uint8_t cafeId, bool on, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !c->placed)
            return say("That cafe is not built.");
        if (c->enabled == on)
            return say(std::string(Info(cafeId).name) + (on ? " is open already." : " is closed already."));
        if (!on)
        {
            ClosePath(*c, static_cast<char>(CafeShiftEnd::Closed));
            if (c->crowdSpawned)
            {
                CafeCrowd::Instance().OnSiteDespawned(c->id);
                c->crowdSpawned = false;
            }
            DespawnStaff(*c);
        }
        c->enabled = on;
        if (!SaveCafeRow(*c))
        {
            c->enabled = !on;
            return say("The cafe row could not be written (see the sql.sql log).");
        }
        c->open = on ? 1 : 3;
        c->danger = R::Danger();
        if (on && Enabled())
        {
            SpawnStaff(*c);
            BuildSite(*c);
            CafeCrowd::Instance().OnSiteSpawned(c->site);
            c->crowdSpawned = true;
        }
        MarkCafeList();
        Log(gm, "enable " + std::string(Info(cafeId).cityKey) + " " + (on ? "1" : "0"));
        say(std::string(Info(cafeId).name) + (on ? " is open." : " is closed.") +
            " Players see the cafe when BleakholdUi.Cafe.Enable = 1" + (Enabled() ? " (it is)." : " (it is not yet)."));
    }

    void Cafe::CmdReload(Player* gm, Reply const& say)
    {
        for (CafeRt& c : _cafes)
        {
            ClosePath(c, static_cast<char>(CafeShiftEnd::Closed));
            DespawnSite(c);
        }
        LoadSites();
        for (CafeRt& c : _cafes)
        {
            c.open = Enabled() ? (c.placed && c.enabled ? 1 : 3) : 0;
            c.danger = R::Danger();
            if (Enabled() && c.placed && c.enabled)
            {
                BuildSite(c);
                CafeCrowd::Instance().OnSiteSpawned(c.site);
                c.crowdSpawned = true;
            }
        }
        MarkCafeList();
        Log(gm, "reload");
        say("Cafes reloaded from bleakhold_cafe and bleakhold_cafe_piece.");
    }

    void Cafe::CmdStatus(Reply const& say)
    {
        static char const* const OpenText[] = { "off", "open", "paused (danger nearby)", "not open", "closed for safety" };
        say(std::string("Cafe: ") + (Enabled() ? "on" : "off") + " (Enable " + (_cfg.enable ? "1" : "0") + ", startup checks " +
            (_startupOk ? "passed" : "failed") + ", " + (_cfg.gmOnly ? "game masters only" : "everyone") + ", " +
            (_cfg.useNewArt && _newArtOk ? "new art" : "stand-ins") + (_cfg.useNewArt && !_newArtOk ? " (displays missing)" : "") +
            ")");
        for (CafeRt& c : _cafes)
        {
            D::Cafe const& cd = Info(c.id);
            if (!c.placed)
            {
                say(std::string(cd.name) + ": not built.");
                continue;
            }
            uint32_t byState[4] = { 0, 0, 0, 0 };
            for (auto const& [id, o] : _orders)
                if (o.cafeId == c.id && o.kind == 'P')
                    ++byState[o.state == 'W' ? 0 : o.state == 'T' ? 1 : o.state == 'H' ? 2 : 3];
            say(std::string(cd.name) + ": " + (c.enabled ? "enabled" : "disabled") + ", " + OpenText[std::min<uint8_t>(c.open, 4)] +
                ", " + std::to_string(BaristasAt(c.id)) + " baristas, queue " + std::to_string(QueueLen(c.id)) + "/" +
                std::to_string(QueueCap(c.id)) + ", player orders W " + std::to_string(byState[0]) + " T " +
                std::to_string(byState[1]) + " H " + std::to_string(byState[2]) + " R " + std::to_string(byState[3]) +
                ", Rush " + (c.rushState == 2 ? "live (" + std::to_string(c.rushServed) + "/" + std::to_string(c.rushGoal) + ")" :
                c.rushState == 1 ? std::string("soon") : std::string("none")) + ", " +
                std::to_string(c.servedTodayDay == _dayId ? c.servedToday : 0) + " served today");
            CrowdStatus const crowd = CafeCrowd::Instance().StatusOf(c.id);
            say("  Customers alive: " + (crowd.running ? std::to_string(crowd.alive) : std::string("no crowd running")));
            float const door = std::hypot(c.site.door.GetPositionX() - c.anchor.x, c.site.door.GetPositionY() - c.anchor.y);
            if (door < DoorWarnYd)
                say("  Warning: the door marker is " + Fmt(door) + " yd from the anchor; customers should appear out of sight.");
            if (c.site.nodes.empty())
                say("  Warning: no aisle nodes (path markers).");
            for (Position const& n : crowd.isolated)
                say("  Warning: the aisle node at " + Fmt(n.GetPositionX()) + " " + Fmt(n.GetPositionY()) + " " +
                    Fmt(n.GetPositionZ()) + " reaches no other; move it (.cafe here) or add a path node between "
                    "(.cafe add " + std::string(cd.cityKey) + " path).");
        }
    }

    void Cafe::CmdFlags(uint32_t days, Reply const& say)
    {
        uint32_t const since = NowSec() - std::min<uint32_t>(days ? days : 7, 365) * 86400;
        QueryResult r = CharacterDatabase.Query("SELECT f.`guid`, IFNULL(c.`name`, ''), f.`at`, f.`drinks`, "
            "f.`perfect_permille`, f.`release_sd_ms` FROM `bleakhold_cafe_flag` f LEFT JOIN `characters` c ON c.`guid` = "
            "f.`guid` WHERE f.`at` >= {} ORDER BY f.`at` DESC LIMIT 50", since);
        if (!r)
            return say("No bot hints in that time.");
        do
        {
            Field* f = r->Fetch();
            say(f[1].Get<std::string>() + " (" + std::to_string(f[0].Get<uint32>()) + "): " + std::to_string(f[3].Get<uint32>()) +
                " drinks, " + std::to_string(f[4].Get<uint16>()) + " permille Perfect, releases within " +
                std::to_string(f[5].Get<uint16>()) + " ms, " + std::to_string((NowSec() - f[2].Get<uint32>()) / 3600) + " h ago");
        } while (r->NextRow());
    }

    // .cafe test customer <city> [persona]: the persona by creature entry (909320...) or by its number among the
    // cafe's personas (1...); none: the usual pick. The usual caps hold (Customer.MaxAlive, the queue).
    void Cafe::CmdTestCustomer(Player* gm, uint8_t cafeId, uint32_t persona, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !c->crowdSpawned)
            return say("That cafe has no crowd running (built, enabled, and BleakholdUi.Cafe.Enable = 1?).");
        if (!_cfg.customers)
            return say("BleakholdUi.Cafe.Customer.Enable = 0: the cafe turns every customer away.");
        int idx = -1;
        if (persona)
        {
            uint32_t n = 0;
            for (std::size_t i = 0; i < D::Personas.size() && idx < 0; ++i)
                if (D::Personas[i].entry == persona || (D::Personas[i].cafeId == cafeId && ++n == persona))
                    idx = static_cast<int>(i);
            if (idx < 0)
                return say("No persona " + std::to_string(persona) + ": give a creature entry or 1-" + std::to_string(n) +
                    " for " + std::string(Info(cafeId).name) + ".");
        }
        Log(gm, "test customer " + std::string(Info(cafeId).cityKey) + (idx >= 0 ? " " +
            std::string(D::Personas[std::size_t(idx)].name) : std::string()));
        say(CafeCrowd::Instance().SpawnNow(cafeId, idx));
    }

    void Cafe::CmdTestRush(Player* gm, uint8_t cafeId, uint32_t minutes, Reply const& say)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !c->placed || !c->enabled)
            return say("That cafe is not open.");
        uint32_t const m = std::clamp<uint32_t>(minutes ? minutes : 2, 1, 240);
        R::RushResumePlan const plan = R::RushResume(std::max<uint32_t>(m * 60, 300), _cfg.rushMinutes, _cfg.rushGoal,
            _cfg.rushSurvivorMin);
        c->rushState = 2;
        c->rushEndMs = Mgr::NowMs() + uint64_t(m) * 60000;
        c->rushGoal = std::max<uint32_t>(1, plan.goal * m / std::max<uint32_t>(plan.minutesLeft, 1));
        c->rushSurvivorMin = std::max<uint32_t>(1, plan.survivorMin * m / std::max<uint32_t>(plan.minutesLeft, 1));
        c->rushServed = 0;
        c->rushDayId = _dayId;
        StartRushLines(*c, Mgr::NowMs());
        MarkCafeList();
        MarkCafeBaristas(c->id, VState);
        Log(gm, "test rush " + std::string(Info(cafeId).cityKey) + " " + std::to_string(m));
        say("A test Rush runs at " + std::string(Info(cafeId).name) + " for " + std::to_string(m) + " min, goal " +
            std::to_string(c->rushGoal) + ".");
    }

    void Cafe::CmdTestWeekly(Player* gm, bool dry, Reply const& say)
    {
        Log(gm, std::string("test weekly") + (dry ? " dry" : ""));
        for (auto& [low, b] : _baristas)
            SaveDayWeek(b);
        WeeklyPayout(_weekId, dry, &say);
        if (!dry)
            _boards.clear();
    }

    void Cafe::CmdBarista(Player* gm, std::string const& name, std::string_view what, uint32_t n, Reply const& say)
    {
        ObjectGuid const guid = sCharacterCache->GetCharacterGuidByName(name);
        if (guid.IsEmpty())
            return say("No character named " + name + ".");
        uint32_t const low = guid.GetCounter();
        Player* p = ObjectAccessor::FindConnectedPlayer(guid);
        Barista* b = p ? &BaristaOf(p) : LoadedBarista(low);
        Barista offline;
        if (!b)
        {
            offline.low = low;
            offline.name = name;
            LoadBaristaRow(offline);
            b = &offline;
        }
        if (what == "level")
        {
            uint8_t const level = static_cast<uint8_t>(std::clamp<uint32_t>(n, 1, D::Levels.size()));
            b->xp = R::LevelXp(level);
        }
        else if (what == "xp")
            b->xp = n;
        else if (what == "reset")
        {
            // progress and reward flags go; items stay where they are
            b->xp = 0;
            b->flags = 0;
            b->staffOffer = false;
        }
        else
            return say("Usage: .cafe barista <name> level <1-10> | xp <n> | reset (two names in quotes: "
                "\"First Last\")");
        b->level = R::LevelOf(b->xp);
        b->dirty = true;
        SaveBarista(*b, true);
        if (p)
        {
            GrantLevelRewards(p, *b, false);
            MarkView(p->GetGUID().GetRawValue(), VState);
        }
        Log(gm, "barista " + name + " " + std::string(what) + " " + std::to_string(n));
        say(name + " is barista level " + std::to_string(b->level) + " (" + std::to_string(b->xp) + " XP).");
    }

    // =============================================================================================================
    // The .gobject guard (section 3.12.1)
    // =============================================================================================================
    void Cafe::GuardSavedGo(uint32_t spawnId)
    {
        for (CafeRt& c : _cafes)
            for (auto& [slot, p] : c.pieces)
            {
                if (p.creature || p.spawnId != spawnId)
                    continue;
                // GameObject::SaveToDB queued its DELETE + INSERT already: ours runs after it (one world worker)
                WorldDatabaseTransaction t = WorldDatabase.BeginTransaction();
                t->Append("DELETE FROM `gameobject` WHERE `guid` = {}", spawnId);
                t->Append("DELETE FROM `gameobject_addon` WHERE `guid` = {}", spawnId);
                WorldDatabase.CommitTransaction(t);
                _guardChecks.push_back({ Mgr::NowMs() + 10000, spawnId, false });
                // the piece goes back to its .cafe position (and the in-memory spawn data the move changed)
                DespawnPiece(c, p);
                SpawnPiece(c, p);
                SiteChanged(c);   // a new spawn id: the crowd's chairs must know it
                LOG_INFO("module", "[Bleakhold] Cafe: a .gobject change of piece {} ({}) of {} was undone", slot, p.role,
                    Info(c.id).name);
                std::string const text = "Caf\xC3\xA9 pieces are placed with .cafe; that .gobject change was undone. Use "
                    ".cafe here/nudge.";
                for (auto const& [id, session] : sWorldSessionMgr->GetAllSessions())
                    if (session && session->GetPlayer() && session->GetSecurity() >= SEC_ADMINISTRATOR)
                        ChatHandler(session).SendSysMessage(text);
                return;
            }
    }

    // The .npc guard: a cafe creature (the staff are AddCreData spawns, the customers temp summons) is never a row of
    // `creature`. Creature::SaveToDB (.npc set level / model / movetype / phase ...) wrote one with its spawn id, which
    // the next start would load as a second, permanent copy: the row goes (and once more 10 s later), and a staff
    // member goes back to its .cafe spawn.
    void Cafe::GuardSavedCreature(uint32_t spawnId, uint32_t entry)
    {
        WorldDatabaseTransaction t = WorldDatabase.BeginTransaction();
        t->Append("DELETE FROM `creature` WHERE `guid` = {}", spawnId);
        t->Append("DELETE FROM `creature_addon` WHERE `guid` = {}", spawnId);
        WorldDatabase.CommitTransaction(t);
        _guardChecks.push_back({ Mgr::NowMs() + 10000, spawnId, true });
        LOG_INFO("module", "[Bleakhold] Cafe: the creature row {} (entry {}) a .npc command saved was deleted", spawnId,
            entry);
        for (CafeRt& c : _cafes)
            for (auto& [slot, p] : c.pieces)
            {
                if (!p.creature || p.spawnId != spawnId)
                    continue;
                DespawnPiece(c, p);
                if (Enabled() && c.enabled)
                    SpawnStaff(c);
                SiteChanged(c);   // a new spawn id: the crowd's staff must know it
                LOG_INFO("module", "[Bleakhold] Cafe: a .npc change of {} of {} was undone", p.role, Info(c.id).name);
                std::string const text = "Caf\xC3\xA9 staff are placed with .cafe; that .npc change was undone (it "
                    "would have saved a second copy). Use .cafe here/nudge.";
                for (auto const& [id, session] : sWorldSessionMgr->GetAllSessions())
                    if (session && session->GetPlayer() && session->GetSecurity() >= SEC_ADMINISTRATOR)
                        ChatHandler(session).SendSysMessage(text);
                return;
            }
    }
}
