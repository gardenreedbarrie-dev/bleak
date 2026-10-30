/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The cafe (section 21): the game side of the NPC crowd (spec 3.7). CafeCrowd itself is declared in
 * BleakholdCafeTypes.h (frozen); its behaviour is BleakholdCafeCrowdRules.h's Engine, one per placed cafe, which only
 * asks a CrowdRules::World for things. CrowdWorld is that World on a cafe's map, with AzerothCore calls; CrowdHooks
 * forwards the engine's hooks to Cafe's CrowdSink with the cafe's id. CafeCrowd::State (here, so the frozen class
 * never changes for it) holds the engines; BleakholdCafeCrowd.cpp owns its one instance.
 *
 * Threads: the world thread only. Update runs from Cafe::Update after the map threads joined; the order events come
 * from Cafe's tick, its intent handlers and commands. A call that arrives while Update runs (Cafe answering a hook) is
 * kept and made at the end of that Update, so it finds its order in whichever cafe has it.
 *
 * Creatures and game objects are raw guids (spawn ids for the staff and chairs), resolved again on every use: a grid
 * that unloads, a summon's 15-minute timer or a despawn leaves nothing dangling.
 */

#ifndef BLEAKHOLD_CAFE_CROWD_H
#define BLEAKHOLD_CAFE_CROWD_H

#include "BleakholdCafeCrowdRules.h"
#include "BleakholdCafeTypes.h"

#include <functional>
#include <map>
#include <memory>
#include <vector>

class Creature;
class Map;

namespace Bleakhold
{
    // CrowdRules::World on one cafe's map (map 0 or 1, a continent: its base map).
    class CrowdWorld final : public CrowdRules::World
    {
    public:
        explicit CrowdWorld(uint32_t mapId) : _mapId(mapId) {}

        uint64_t Summon(uint32_t entry, CrowdRules::Pose const& at, uint32_t display) override;
        bool Alive(uint64_t guid) override;
        bool Where(uint64_t guid, CrowdRules::Pose& out) override;
        bool Moving(uint64_t guid) override;
        void Walk(uint64_t guid, std::vector<CrowdRules::Vec3> const& points, bool run) override;
        void Stop(uint64_t guid) override;
        void Teleport(uint64_t guid, CrowdRules::Pose const& to) override;
        void Face(uint64_t guid, float o) override;
        void Despawn(uint64_t guid) override;
        void Say(uint64_t guid, std::string_view text, bool yell) override;
        void Emote(uint64_t guid, uint32_t emote) override;
        void EmoteState(uint64_t guid, uint32_t state) override;
        void Stand(uint64_t guid, uint8_t state) override;
        void Hold(uint64_t guid, uint32_t item) override;
        void Cast(uint64_t guid, uint32_t spell) override;
        void FinishChannel(uint64_t guid, uint32_t spell) override;
        uint64_t Staff(uint64_t spawnId) override;
        uint64_t PlaceGo(uint32_t entry, CrowdRules::Pose const& at, uint32_t lifetimeSec) override;
        void RemoveGo(uint64_t guid) override;
        void LockChair(uint64_t spawnId, bool locked) override;
        void Players(CrowdRules::Vec3 centre, float radius, std::vector<CrowdRules::PlayerNear>& out) override;

    private:
        Map* GetMap() const;
        Creature* Unit(uint64_t guid) const;   // in the world and alive, else nullptr

        uint32_t _mapId;
    };

    // CrowdRules::Hooks to Cafe's CrowdSink (none set yet: customers are refused, nothing else is told).
    class CrowdHooks final : public CrowdRules::Hooks
    {
    public:
        CrowdHooks(uint8_t cafeId, CrowdSink* const* sink) : _cafeId(cafeId), _sink(sink) {}

        uint32_t NpcArrived(uint8_t personaIdx, uint64_t creatureGuid, uint32_t groupId) override;
        void NpcGone(uint32_t orderId) override;
        void HouseStepStarted(uint32_t orderId, uint8_t stepIndex, uint8_t actionId, uint32_t durMs,
                              uint64_t workerGuid) override;
        void HouseDone(uint32_t orderId) override;
        void CupTaken(uint32_t orderId) override;
        void Delivered(uint32_t orderId) override;

    private:
        uint8_t _cafeId;
        CrowdSink* const* _sink;
    };

    struct CafeCrowd::State
    {
        struct Site
        {
            explicit Site(uint8_t cafeId, uint32_t mapId, CrowdSink* const* sink) : world(mapId), hooks(cafeId, sink) {}

            CrowdWorld world;
            CrowdHooks hooks;
            std::unique_ptr<CrowdRules::Engine> engine;   // after world and hooks: it holds references to them
        };

        CrowdSink* sink = nullptr;
        CrowdRules::Config cfg;
        bool cfgRead = false;
        uint32_t cfgReadMs = 0;                            // re-read quietly every CfgRefreshMs (.bleakhold reload)
        std::map<uint8_t, std::unique_ptr<Site>> sites;    // by cafe id
        std::map<uint8_t, CrowdRules::Tracks> tracks;      // the named personas' cooldowns, kept across a respawn
        uint32_t nextGroup = 1;                            // Rush group ids, unique across cafes and respawns
        bool inUpdate = false;
        std::vector<std::function<void()>> later;          // calls made while Update runs, made at its end
    };
}

#endif
