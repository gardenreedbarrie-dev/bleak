/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The cafe (section 21): the interface between Cafe (BleakholdCafe.h: shifts, tickets, orders, rewards) and
 * CafeCrowd (BleakholdCafeCrowd.h: the cafe's creatures, seats, cups and house jobs). Frozen: both sides build on it
 * from the start, so it changes only by agreement of both.
 *
 * Cafe drives CafeCrowd from its world-thread tick (Cafe::Update) with plain values: a CafeSite when a cafe is
 * spawned, CrowdInputs every tick, and the order events below. CafeCrowd answers through CrowdSink, which Cafe
 * implements; it never takes Cafe's lock. Creatures and game objects are raw guids and spawn ids, resolved again on
 * every use. Lines and personas come from BleakholdCafeData.h; Cafe picks the text, CafeCrowd only says what it is
 * given (except the customers' own idle lines).
 *
 * Core-free except Position (Position.h, a plain value here).
 */

#ifndef BLEAKHOLD_CAFE_TYPES_H
#define BLEAKHOLD_CAFE_TYPES_H

#include "Position.h"

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace Bleakhold
{
    // A station's two work spots (side by side, 0.7 yd apart) and the station object a worker faces.
    struct StationSpots
    {
        char station = 0;                    // G E K C B S V
        std::array<Position, 2> spots;
        float objX = 0, objY = 0;
        uint16_t slot = 0;                   // its layout slot
    };

    // What CafeCrowd needs of a placed cafe (plain values, world positions).
    struct CafeSite
    {
        uint8_t cafeId = 0;
        uint32_t mapId = 0;
        uint32_t phaseMask = 1;              // PHASEMASK_NORMAL
        uint32_t team = 0;                   // TEAM_ALLIANCE or TEAM_HORDE
        Position anchor, orderSpot, pickupSpot, door;
        std::vector<Position> queueSlots;    // 8
        std::vector<Position> nodes;         // aisle graph nodes path_1..n (default 9, plus .cafe add path)
        struct Chair
        {
            uint16_t slot = 0;
            uint16_t table = 0;              // its table's slot
            Position seat;
            Position approach;               // the seat moved 0.7 yd away from its table
            uint8_t height = 0;              // the chair's Data1 (UNIT_STAND_STATE_SIT_LOW_CHAIR + height)
            uint8_t slots = 0;               // NPCs use only 1-slot seats
            uint64_t spawnId = 0;
        };
        std::vector<Chair> chairs;
        std::vector<Position> kegSpots;
        std::vector<Position> tableTops;
        struct Footprint { float x, y, halfW, halfD, o; };   // every piece's 2D box (manifest or cafe.json size)
        std::vector<Footprint> footprints;
        std::array<StationSpots, 7> stations;   // G E K C B S V
        struct Staff
        {
            std::string role;                // staff_owner, staff_head, staff_busser, staff_extra_1..3
            uint32_t entry = 0;
            uint64_t spawnId = 0;
            Position home;
        };
        std::vector<Staff> staff;
    };

    // Filled by Cafe each tick, one per cafe.
    struct CrowdInputs
    {
        uint8_t cafeId = 0;
        uint8_t open = 0;                    // 1 open, 2 paused (freeze), else everyone leaves and nothing spawns
        uint8_t baristas = 0;                // on shift at this cafe
        bool rush = false;
        uint8_t queueCap = 0;                // 6 or 8
        uint8_t queueLen = 0;                // orders in queue (player + npc, 'W' only)
        // any player (not GM-invisible) within Customer.NearPlayerRadius of the anchor
        bool playerNear = false;
        std::vector<uint64_t> queueOrder;    // creature guids in queue order (Cafe's view): Crowd moves them to slots
    };

    // A drink the house makes (the owner, then the head barista): its steps, walked and cast in order.
    struct HouseJob
    {
        uint32_t orderId = 0;
        bool playerOrder = false;            // player orders go before NPC orders
        bool front = false;                  // a takeover: the very front of the queue
        std::vector<uint8_t> actions;        // action ids; a repeated action is done again in place
        uint32_t minTotalMs = 0;             // HouseBaseSec + HousePerLineSec x lines; the waits are padded to it
    };

    // What .cafe status shows of a cafe's crowd.
    struct CrowdStatus
    {
        bool running = false;                // the cafe's engine exists (spawned, enabled, the feature on)
        uint32_t alive = 0;                  // customers on their way, in line, at the counter, seated or leaving
        std::vector<Position> isolated;      // aisle nodes with no clear edge to any other (spec 3.7.3)
    };

    // Implemented by Cafe; called by CafeCrowd from CafeCrowd::Update (world thread).
    struct CrowdSink
    {
        // A customer reached the queue: the order id, or 0 to refuse (it leaves).
        virtual uint32_t NpcArrived(uint8_t cafeId, uint8_t personaIdx, uint64_t creatureGuid, uint32_t groupId) = 0;
        virtual void NpcGone(uint32_t orderId) = 0;            // creature vanished (grid unload, error, stuck twice)
        virtual void HouseStepStarted(uint32_t orderId, uint8_t stepIndex, uint8_t actionId, uint32_t durMs,
                                      uint64_t workerGuid) = 0;   // for CAFO progress and CAFAT
        virtual void HouseDone(uint32_t orderId) = 0;
        virtual void CupTaken(uint32_t orderId) = 0;           // an NPC took its cup from the counter
        virtual void Delivered(uint32_t orderId) = 0;          // the busser reached a seated player
        virtual ~CrowdSink() = default;
    };

    class CafeCrowd
    {
    public:
        static CafeCrowd& Instance();
        void SetSink(CrowdSink*);
        void OnSiteSpawned(CafeSite const&);      // after Cafe spawned pieces + staff (staff spawnIds in site.staff)
        void OnSiteDespawned(uint8_t cafeId);     // despawn customers and cups, release seats, stop jobs
        void Update(uint32_t nowMs, std::vector<CrowdInputs> const&);

        // order events from Cafe
        void OrderTaken(uint32_t orderId, std::string const& orderLine);   // customer says it, walks to pickup
        void OrderReturned(uint32_t orderId);     // ticket went back to the queue: the customer stays at pickup
        void OrderServed(uint32_t orderId, char quality, std::string const& thanksLine, uint32_t cupItem,
                         uint32_t cupGo);
        void OrderFailed(uint32_t orderId, std::string const& complaintLine);   // walk out
        // ambient: the customer orders from the owner, who answers
        void HouseOrderTaken(uint32_t orderId, std::string const& orderLine, std::string const& ownerAnswer);

        // house and staff
        // FIFO: player orders before NPC orders; front = takeover
        void QueueHouseJob(uint8_t cafeId, HouseJob const&);
        void CancelHouseJob(uint32_t orderId);
        uint32_t HouseEtaSec(uint8_t cafeId, std::optional<uint32_t> orderId) const;   // for CAFE, CAFM, CAFO
        void PlaceCounterCup(uint8_t cafeId, uint32_t orderId, uint32_t cupGo);        // player order 'R'
        void RemoveCounterCup(uint32_t orderId);
        // the busser carries the cup to the seated player, then Delivered()
        void DeliverToSeat(uint8_t cafeId, uint32_t orderId, uint64_t playerGuid, uint32_t cupGo);
        void StaffSay(uint8_t cafeId, std::string const& role, std::string const& text, bool yell);
        bool SeatTakenByPlayer(uint8_t cafeId, uint16_t chairSlot) const;          // for Lingering Sip and seating
        // the chair slot the player sits in
        std::optional<uint16_t> PlayerSeat(uint8_t cafeId, uint64_t playerGuid) const;

        // GM commands (added after the freeze; neither side's other calls changed)
        // .cafe test customer: one customer now (personaIdx into CafeData::Personas, -1: the usual pick) within the
        // usual caps; the answer for the GM
        std::string SpawnNow(uint8_t cafeId, int personaIdx);
        CrowdStatus StatusOf(uint8_t cafeId) const;      // .cafe status

    private:
        CafeCrowd() = default;
        CafeCrowd(CafeCrowd const&) = delete;
        CafeCrowd& operator=(CafeCrowd const&) = delete;

        // The crowd's state (customers, seats, cups, staff, house jobs): defined in BleakholdCafeCrowd.h, one
        // instance, owned by BleakholdCafeCrowd.cpp, so this declaration never has to change for it.
        struct State;
        State& St() const;
    };
}

#endif
