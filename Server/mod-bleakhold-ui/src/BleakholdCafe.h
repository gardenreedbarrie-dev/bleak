/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The cafe (section 21): The Lion's Roast in Stormwind and The Grinding Tusk in Orgrimmar. Cafe owns every game rule
 * and all the state: the placed cafes and their pieces, barista shifts, tickets and steps, NPC and player orders, the
 * money of player orders, rewards, the Morning Rush, the danger pause and the weekly board. CafeCrowd
 * (BleakholdCafeCrowd.h) owns the cafe's creatures and is driven from Cafe::Update through BleakholdCafeTypes.h.
 * The rules and formulas are BleakholdCafeRules.h (tested core-free); the catalogue is the generated
 * BleakholdCafeData.h.
 *
 * Files: BleakholdCafe.cpp (config, lifecycle, the tick, shifts, steps, orders, rewards, Rush, danger, protocol,
 * gossip, hooks), BleakholdCafeStore.cpp (the database: tables, barista, day and week rows, order rows with their
 * money, mail, the weekly payout, the board) and BleakholdCafeSite.cpp (placement: .cafe build and the other GM
 * commands, spawning the pieces and the staff, the CafeSite the crowd gets).
 *
 * Threads: everything runs on the world thread (the tick after the map threads joined, intents, GETs, commands, gossip
 * selections, login and logout) except the hooks marked "map thread": they touch only atomics, the player they were
 * called for and the event queue (_eventLock), which the next tick drains. GossipHello may run on a map thread and
 * reads only the gossip snapshot (_snapLock). No Ui::Send* is called while either lock is held. Creatures, game
 * objects and players are kept as raw guids or spawn ids and found again on every use.
 *
 * Off by default (BleakholdUi.Cafe.Enable = 0, GmOnly = 1, UseNewArt = 0): OnStartup still checks the templates and
 * spells and spawns the furniture of placed cafes, so .bleakhold reload can turn it on; while it is off nothing is
 * sent, no staff or customer spawns and every cafe intent gets ERR cafe_off (Mgr::Dispatch). The login cleanup of the
 * never-saved auras runs either way.
 */

#ifndef BLEAKHOLD_CAFE_H
#define BLEAKHOLD_CAFE_H

#include "BleakholdCafeRules.h"
#include "BleakholdCafeTypes.h"
#include "BleakholdMessages.h"

#include "DatabaseEnvFwd.h"

#include <array>
#include <atomic>
#include <cstdint>
#include <functional>
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

class Creature;
class GameObject;
class Map;
class Player;

namespace Bleakhold
{
    // BleakholdUi.Cafe.* (section 3.11), clamped.
    struct CafeConfig
    {
        bool enable = false;
        bool useNewArt = false;
        bool gmOnly = true;
        uint32_t minLevel = 10;
        float shiftRadius = 30;
        uint32_t leaveWarnSec = 10;
        float stationRadius = 1.5f;
        float stationLeaveRadius = 2.0f;
        float stationArcDeg = 120;
        uint32_t tickMs = 250;
        uint32_t stateGapMs = 250;
        uint32_t idleTicketSec = 120, idleSec = 300;
        uint32_t maxBaristasPerIp = 2;
        uint32_t maxBaristas = 4;
        uint32_t warnSec = 5;
        uint32_t latencyCompMaxMs = 400;
        uint32_t releaseSlackMs = 150;
        uint32_t goodPadPermille = 100;
        uint32_t goldShiftPermille = 50;
        // customers
        bool customers = true;
        uint32_t queueCap = 6, rushQueueCap = 8;
        float nearPlayerRadius = 60;
        uint32_t queuePatienceSec = 60;
        uint32_t drinkPatienceSec = 30, perLineSec = 6;
        // player orders
        bool orders = true;
        uint32_t maxOrdersPerDay = 12;
        float orderRadius = 40;
        uint32_t takeTimeoutSec = 25;
        uint32_t maxPendingPerCafe = 6;
        uint32_t maxRuins = 2;
        uint32_t houseBaseSec = 30, housePerLineSec = 5;
        float pickupRadius = 15;
        uint32_t pickupSec = 180;
        uint32_t baristaSharePct = 60;
        uint32_t pairBoostPerDay = 3;
        uint32_t priceMinCopper = 200, priceLevelFloorPct = 10;
        // caps
        uint32_t xpDailyFull = 450, xpDailyHalf = 450;
        uint32_t tipDailyBaseCopper = 5000, tipDailyPerLevelCopper = 2500;
        uint32_t pointsDailyCap = 400, pointsRushExtra = 100;
        uint32_t tiredAfterMin = 60, tiredRestMin = 15, tiredPct = 50;
        // buffs
        uint32_t coffeeXpPct = 5, teaRepPct = 5;
        std::vector<uint32_t> teaExcludeFactions{ 509, 510, 729, 730, 889, 890 };
        uint32_t buffMaxMin = 60;
        // the Morning Rush
        bool rush = true;
        std::vector<uint32_t> rushTimes{ 8 * 3600 };   // seconds of the day, realm local time
        uint32_t rushMinutes = 20, rushWarnMinutes = 5, rushGoal = 60, rushSurvivorMin = 5, rushSurvivorXp = 50;
        // the weekly board
        bool weekly = true;
        uint32_t weeklyMinDrinks = 50, weeklyMinDays = 3;
        std::vector<uint32_t> weeklyRewardCopper{ 500000, 300000, 200000, 50000, 50000, 50000, 50000, 50000, 50000, 50000 };
        uint32_t titleBaristaId = 190, titleLegendId = 191, titleLegendWins = 3;
        uint32_t dailyResetHour = 6, weeklyResetWeekday = 3;
        // danger
        float hostileNearRadius = 15, hostileRadius = 40, hostileDz = 5;
        uint32_t confirmSec = 5, resumeSec = 20, pauseMaxSec = 90, reopenSec = 120;
        // bot hints
        uint32_t botMinDrinks = 200, botPerfectPermille = 980, botSdMs = 30;
        bool overheadKits = false;
    };

    class Cafe : public CrowdSink
    {
    public:
        static Cafe& Instance();

        // ---- lifecycle (world thread) ----
        void LoadConfig();                         // from Mgr::LoadConfig, outside the Mgr lock
        void OnStartup();                          // from BleakholdWorldScript::OnStartup after Data::LoadAll
        void OnShutdown();                         // barista and day rows saved at once; orders settle at the next start
        void Update(uint64_t nowMs);               // from Mgr::Update; ticks every Cafe.TickMs
        bool Enabled() const { return _enabled.load(); }   // the feature on and the startup checks passed
        bool FeatureFor(Player* player) const;     // Enabled() and (not GmOnly or a game master): HELLO bit, Dispatch
        bool DefinitionsOn() const { return _cfgEnable.load(); }   // DEF H G F U (BleakholdUi.Cafe.Enable)
        static bool IsCafeIntent(IntentType type);
        static bool IsCafeTopic(Topic topic);

        // ---- protocol (world thread; registered in Data::RegisterDefaults) ----
        void HandleShift(Player* player, Intent const& intent);     // CSHIFT
        void HandleTake(Player* player, Intent const& intent);      // CTAKE
        void HandleStep(Player* player, Intent const& intent);      // CSTEP
        void HandleRelease(Player* player, Intent const& intent);   // CREL
        void HandleOrder(Player* player, Intent const& intent);     // CORDER
        void HandleCancel(Player* player, Intent const& intent);    // CCANCEL
        void HandleStaff(Player* player, Intent const& intent);     // CSTAFF
        void Provide(Player* player, TopicRequest const& request);  // GET CAFE CAFST CAFQ CAFT CAFM CAFO CAFP CAFBF
        void AnswerBoard(Player* player, Intent const& intent);     // LBQ C (Ui::OnBoardQuery(Board::Cafe))
        void OnHello(Player* player);              // CAFE, CAFBF, and CAFST/CAFT/CAFQ on shift, CAFO with an order

        // ---- gossip (the owners and the head baristas) ----
        void GossipHello(Player* player, Creature* creature);       // may run on a map thread: reads the snapshot
        void GossipSelect(Player* player, Creature* creature, uint32_t sender, uint32_t action);   // world thread

        // ---- hooks ----
        void OnLogin(Player* player);              // world thread: strips 100900/100936 (always), then the checks
        void OnBeforeLogout(Player* player);       // world thread, before SaveToDB: the shift ends, auras stripped
        void OnLogout(Player* player);
        void OnMapChanged(Player* player);
        void OnDeleteCharacter(uint32_t lowGuid);
        void OnEnterCombatMapThread(Player* player);         // map thread: the speed helper goes, the shift ends next tick
        void OnPvpFlagMapThread(Player* player, bool on);    // map thread
        void OnDuelMapThread(Player* a, Player* b);          // map thread: both players' speed helpers go
        void OnSpellCancelMapThread(uint32_t lowGuid, uint32_t spellId);   // map thread: queued for the step timers
        void OnGoSavedToDbMapThread(uint32_t spawnId, uint32_t entry);     // map or world thread: the .gobject guard
        void OnCreatureSavedToDbMapThread(uint32_t spawnId, uint32_t entry);   // map or world thread: the .npc guard

        // ---- reward queries of the map-thread hooks (atomics and the player's auras) ----
        bool HasCoffee(Player* player) const;
        bool HasTea(Player* player) const;
        uint32_t CoffeeXpPct() const;              // 0 when off
        uint32_t TeaRepPct() const;
        bool RewardPlaceOk(Player* player) const;  // no battleground or arena map, no battlefield zone
        bool TeaExcludesFaction(uint32_t faction) const;

        // ---- GM commands (BleakholdCommands.cpp; world thread). `gm` is null on the console. ----
        using Reply = std::function<void(std::string const&)>;
        static uint8_t CafeIdOf(std::string_view city);      // sw 1, org 2, else 0
        void CmdBuild(Player* gm, uint8_t cafeId, bool force, Reply const& say);
        void CmdList(uint8_t cafeId, Reply const& say);
        void CmdShow(Player* gm, uint8_t cafeId, bool show, Reply const& say);
        void CmdNear(Player* gm, uint8_t cafeId, Reply const& say);
        void CmdHere(Player* gm, uint8_t cafeId, std::optional<uint16_t> slot, Reply const& say);
        void CmdNudge(Player* gm, uint8_t cafeId, std::optional<uint16_t> slot, float fwd, float left, float up,
            float turnDeg, Reply const& say);
        void CmdTurn(Player* gm, uint8_t cafeId, std::optional<uint16_t> slot, float deg, Reply const& say);
        void CmdUndo(Player* gm, uint8_t cafeId, Reply const& say);
        void CmdRotate(Player* gm, uint8_t cafeId, float deg, Reply const& say);
        void CmdShift(Player* gm, uint8_t cafeId, float fwd, float left, float up, Reply const& say);
        void CmdSnap(Player* gm, uint8_t cafeId, std::optional<uint16_t> slot, Reply const& say);
        void CmdAdd(Player* gm, uint8_t cafeId, std::string_view role, uint32_t entry, Reply const& say);
        void CmdRemove(Player* gm, uint8_t cafeId, uint16_t slot, Reply const& say);
        void CmdEnable(Player* gm, uint8_t cafeId, bool on, Reply const& say);
        void CmdReload(Player* gm, Reply const& say);
        void CmdStatus(Reply const& say);
        void CmdFlags(uint32_t days, Reply const& say);
        void CmdTestCustomer(Player* gm, uint8_t cafeId, uint32_t persona, Reply const& say);
        void CmdTestRush(Player* gm, uint8_t cafeId, uint32_t minutes, Reply const& say);
        void CmdTestWeekly(Player* gm, bool dry, Reply const& say);
        void CmdBarista(Player* gm, std::string const& name, std::string_view what, uint32_t n, Reply const& say);

        // ---- CrowdSink (called by CafeCrowd::Update, world thread) ----
        uint32_t NpcArrived(uint8_t cafeId, uint8_t personaIdx, uint64_t creatureGuid, uint32_t groupId) override;
        void NpcGone(uint32_t orderId) override;
        void HouseStepStarted(uint32_t orderId, uint8_t stepIndex, uint8_t actionId, uint32_t durMs,
            uint64_t workerGuid) override;
        void HouseDone(uint32_t orderId) override;
        void CupTaken(uint32_t orderId) override;
        void Delivered(uint32_t orderId) override;

    private:
        Cafe() = default;
        Cafe(Cafe const&) = delete;
        Cafe& operator=(Cafe const&) = delete;

        // ---------------------------------------------------------------------------------------------------------
        // Runtime data (section 3.3)
        // ---------------------------------------------------------------------------------------------------------
        struct Piece
        {
            uint16_t slot = 0;
            std::string role;
            uint32_t entry = 0;                  // the new-art entry (the stand-in is entry + 30); 0 for a marker
            uint16_t link = 0;
            float f = 0, l = 0, u = 0, turn = 0;
            float x = 0, y = 0, z = 0, o = 0;
            bool snap = true, enabled = true;
            uint32_t spawnId = 0;                // runtime spawn (AddGOData / AddCreData); 0: not spawned
            uint32_t spawnedEntry = 0;
            bool creature = false;
            bool hasPrev = false;                // .cafe undo
            float pf = 0, pl = 0, pu = 0, pturn = 0;
        };

        struct Step
        {
            bool active = false;
            uint8_t index = 0;                   // 0-based
            uint8_t action = 0;
            bool timed = false;
            uint64_t startMs = 0;
            uint32_t durMs = 0, goldLoMs = 0, goldHiMs = 0;
            bool expectCancel = false;
            float spotX = 0, spotY = 0;          // where it started (a step is aborted 2 yd from there)
            uint16_t emoteState = 0;
        };

        struct Ticket
        {
            uint32_t id = 0;
            uint32_t orderId = 0;
            uint16_t recipeId = 0;
            uint8_t next = 0;                    // index into the steps (0-based)
            std::array<char, 12> grades{};       // 'N' none, 'P', 'G', 'O'
            Step step;
            uint64_t takenMs = 0;
            uint8_t ruins = 0;
            bool tutorial = false;               // the barista's first drink: a wrong step costs nothing
        };

        struct Order
        {
            uint32_t id = 0;
            uint8_t cafeId = 0;
            char kind = 'N';                     // N npc, P player, G npc of a Rush group
            uint16_t recipeId = 0;
            uint64_t customerGuid = 0;           // raw: the creature (N, G) or the player (P)
            uint32_t customerLow = 0, customerAccount = 0;
            std::string customerIp;
            int personaIdx = -1;
            uint8_t member = 0;                  // a group member's place in its group
            uint32_t groupId = 0;
            std::string customer;
            uint64_t createdMs = 0, patienceEndMs = 0;
            uint32_t patienceMaxMs = 0;
            bool queuePhase = true;
            char state = 'W';                    // W waiting, T taken, H the house makes it, R ready (player orders)
            bool takeover = false;               // H after a barista failed it (CAFO F): CCANCEL allowed
            bool ambient = false;                // an NPC order the house makes: never times out
            uint64_t baristaGuid = 0;
            uint32_t baristaLow = 0;
            std::string baristaName;
            uint32_t ticketId = 0;
            uint32_t price = 0, tip = 0;
            uint8_t sharePct = 60;               // Order.BaristaSharePct when it was paid (its row's share_pct)
            uint64_t takeDeadlineMs = 0;         // a waiting player order goes to the house then
            uint64_t readyUntilMs = 0;
            uint32_t readyUntilEpoch = 0;
            char quality = 'G';                  // of a served drink (the house makes Good drinks)
            bool rushServed = false;
            std::string orderLine;
            bool lineSaid = false;
            bool houseLineSaid = false;          // the house worker said it makes this player order (its first step)
            bool returned = false;
            // the house making it (CAFO progress, CAFAT)
            uint8_t houseStep = 0, houseSteps = 0;
            uint8_t houseAction = 0;
            uint64_t houseStepMs = 0;
            uint32_t houseStepDurMs = 0;
            uint64_t houseStartMs = 0;
            uint32_t houseTotalMs = 0;
            std::string houseWorker;
            bool deliverSent = false;            // the busser carries it to the seated customer
            bool viaGossip = false;              // ordered without the addon: status lines as system messages
            bool cupOnCounter = false;
        };

        struct Shift
        {
            uint64_t guid = 0;
            uint32_t low = 0, account = 0;
            std::string ip, name;
            uint8_t cafeId = 0;
            uint32_t startSec = 0;
            uint64_t startMs = 0, lastActionMs = 0, lastTiredMs = 0;
            CafeRules::ShiftTimers timers;
            char station = 0, nearStation = 0;
            uint8_t spot = 0;
            uint16_t nearDm = 0;
            bool facingHint = false;
            uint32_t warnFlags = 0;
            std::optional<uint32_t> warnSec;
            std::vector<Ticket> tickets;
            uint16_t lastRecipe = 0;
            uint8_t inARow = 0;
            uint32_t drinks = 0, perfects = 0, tips = 0, xp = 0, xpLost = 0, points = 0, streak = 0, bestStreak = 0;
            uint32_t rushServed = 0;
            std::vector<int32_t> releaseOffsets;
            bool endPending = false;
            char endReason = 0;
        };

        struct DayRow
        {
            uint32_t dayId = 0;
            uint8_t cafeId = 0;
            uint32_t xpFull = 0, xpHalf = 0, tips = 0, points = 0, drinks = 0, perfects = 0, ordersPlaced = 0;
            uint32_t rushServed = 0;
            bool dirty = false;
        };

        struct WeekRowRt
        {
            uint32_t weekId = 0;
            uint8_t cafeId = 0;
            uint32_t points = 0, drinks = 0, perfects = 0, scoreAt = 0;
            uint8_t daysMask = 0;
            bool dirty = false;
        };

        struct Barista
        {
            uint32_t low = 0, account = 0;
            std::string name;
            uint8_t classId = 0;
            uint8_t level = 1;
            uint32_t xp = 0, drinks = 0, perfects = 0, memoryDrinks = 0, bestStreak = 0, fastestMs = 0, weeklyWins = 0;
            uint32_t flags = 0, crownUntil = 0, staffDay = 0;
            CafeRules::TiredRow tired;
            DayRow day;
            WeekRowRt week;
            bool staffOffer = false;             // a Staff Drink may be claimed today (offered at shift end)
            bool dirty = false;
            bool exists = false;                 // has a row in the table
            uint64_t lastSaveMs = 0;
            uint64_t expireMs = 0;               // forgotten then after a logout (0 while online)
        };

        struct AtBarRow { std::string name; uint8_t action = 0; uint64_t startMs = 0; uint32_t durMs = 0; bool timed = false;
                          uint8_t stepIndex = 1, stepCount = 1; };

        struct CafeRt
        {
            uint8_t id = 0;
            bool placed = false, enabled = false, spawned = false, crowdSpawned = false;
            uint8_t open = 3;                    // 0 off, 1 open, 2 paused, 3 not open, 4 closed for safety
            uint32_t map = 0, zone = 0;
            CafeRules::Pose anchor;
            uint16_t layoutVer = 1;
            std::string placedBy;
            uint32_t placedAt = 0;
            std::map<uint16_t, Piece> pieces;    // by slot
            uint16_t lastChanged = 0;            // .cafe undo
            CafeSite site;
            std::vector<uint32_t> queue;         // order ids in queue order (player orders first)
            // danger
            CafeRules::Danger danger;
            std::unordered_map<uint64_t, uint64_t> hostileSince;   // raw player guid -> since (ms)
            bool pauseLineSaid = false;
            // the Rush
            uint8_t rushState = 0;               // 0 none, 1 soon, 2 live
            int64_t rushWindow = 0;              // the local start of the window last warned or run
            uint64_t rushEndMs = 0;              // live: the end (moves by the length of a pause)
            uint32_t rushGoal = 0, rushSurvivorMin = 0, rushServed = 0;
            uint32_t rushDayId = 0;              // a day with a Rush: the points cap is higher
            std::vector<std::pair<uint64_t, uint32_t>> rushShouts;   // (when, staff entry): the staff's Rush lines
            // speech and spawns
            uint64_t nextIdleMs = 0, lastStaffLineMs = 0;
            // bystanders
            std::unordered_set<uint64_t> atSeen;
            bool atDirty = false;
            uint64_t atSentMs = 0;
            // CAFE
            uint32_t sentKey = 0;
            uint32_t sentQueueLen = 0;
            uint32_t servedToday = 0;
            uint32_t servedTodayDay = 0;
        };

        // per player: which states are due and when each was sent (unrevisioned, "the last one counts")
        enum ViewBit : uint8_t { VState = 1, VQueue = 2, VTickets = 4, VOrder = 8, VBuffs = 16 };
        struct View
        {
            uint8_t dirty = 0;
            std::array<uint64_t, 5> sentMs{};
            uint64_t buffsSentMs = 0;
        };

        struct Event
        {
            enum class Kind : uint8_t { Combat, SpellCancel, GoSaved, CreatureSaved, ShiftOffered };
            Kind kind = Kind::Combat;
            uint32_t a = 0, b = 0;
        };

        struct GossipSnap
        {
            std::array<uint8_t, 3> open{};       // by cafe id
            std::unordered_set<uint64_t> onShift;
            bool enabled = false;
            bool gmOnly = true;
        };

        struct BoardCache { uint64_t atMs = 0; std::vector<CafeRules::WeekRow> ranked; };

        // ---------------------------------------------------------------------------------------------------------
        // BleakholdCafe.cpp
        // ---------------------------------------------------------------------------------------------------------
        void RecomputeEnabled();
        bool ValidateStartup();
        void DrainEvents(uint64_t nowMs);
        void TickShifts(uint64_t nowMs);
        void TickSteps(uint64_t nowMs);
        void TickOrders(uint64_t nowMs);
        void TickCafes(uint64_t nowMs);
        void TickCrowd(uint64_t nowMs);
        void TickAuras(uint64_t nowMs);
        void FlushViews(uint64_t nowMs);
        void TickSpeech(CafeRt& c, uint64_t nowMs);
        void TickDanger(CafeRt& c, uint64_t nowMs);
        void TickRush(uint64_t nowMs);
        void StartRushLines(CafeRt& c, uint64_t nowMs);
        void TickPeriods(uint64_t nowMs);
        void PayMissedWeeks();
        void TickLingers(uint64_t nowMs);
        void FreezeFor(CafeRt& c, uint64_t dtMs);

        CafeRt* CafeOf(uint8_t id);
        CafeRt const* CafeOf(uint8_t id) const;
        Shift* ShiftOf(Player* player);
        Shift* ShiftOf(uint64_t guid);
        Order* OrderOf(uint32_t id);
        Order* PendingOrderOf(uint32_t lowGuid);
        Ticket* TicketOf(Shift& s, uint32_t ticketId);
        uint8_t TeamCafe(Player* player) const;   // 1 Alliance, 2 Horde
        uint8_t BaristasAt(uint8_t cafeId) const;
        uint8_t MaxBaristaLevelAt(uint8_t cafeId);
        bool InRange(Player* player, CafeRt const& c, float radius) const;
        bool Hidden(Player* player) const;        // mounted, vehicle, taxi, a form (no stance), stealth, invisible
        bool RushLive(uint8_t cafeId) const;
        uint8_t QueueCap(uint8_t cafeId) const;
        uint32_t QueueLen(uint8_t cafeId) const;
        uint32_t PendingPlayerOrders(uint8_t cafeId) const;
        void Refuse(Player* player, Intent const& intent, Refusal const& r);
        void Refuse(Player* player, Intent const& intent, std::string_view code, std::string_view text);
        void Tell(Player* player, std::string const& text);   // a system message (players without the addon)
        uint32_t DayId();
        uint32_t WeekId();
        uint32_t NowSec() const;
        static uint32_t Random(uint32_t below);
        void Say(uint8_t cafeId, std::string_view role, uint32_t entry, std::string_view key, std::string const& fill = {});
        void AnnounceCafe(std::string const& text);   // [Cafe] to everyone, or under GmOnly to those with the bit
        void CrowdCall(std::function<void()> call);

        // shifts
        std::optional<Refusal> ShiftCheck(Player* player, uint8_t cafeId, std::string& text);
        bool StartShift(Player* player, uint8_t cafeId, Intent const* intent);
        void EndShift(Shift& s, char reason, uint64_t nowMs);
        void EndShiftsAt(uint8_t cafeId, char reason);
        void UpdateStation(Player* player, Shift& s, uint64_t nowMs);
        std::vector<CafeRules::SpotRef> SpotsOf(CafeRt const& c) const;
        void StartStep(Player* player, Shift& s, Ticket& t, uint8_t action, uint64_t nowMs);
        void CompleteStep(Player* player, Shift& s, Ticket& t, char grade, uint64_t nowMs);
        void AbortStep(Player* player, Shift& s, Ticket& t, bool interruptSpell);
        void SendStepEvent(Player* player, Ticket const& t, uint8_t stepIndex, uint8_t action, CafeStepEventKind kind,
            std::optional<uint32_t> durMs, char grade, Step const* step = nullptr);
        void Serve(Player* player, Shift& s, Ticket& t, uint64_t nowMs);
        void CloseTicketLeft(Shift& s, Ticket& t, std::string const& line, bool penalty, uint64_t nowMs);
        void ReturnTickets(Shift& s, uint64_t nowMs);
        void RemoveTicket(Shift& s, uint32_t ticketId);

        // orders
        uint32_t NewOrderId() { return _nextOrderId++; }
        void QueueOrder(CafeRt& c, Order& o, bool front);
        void Unqueue(Order const& o);
        void RemoveOrder(uint32_t id);
        void HouseTakes(Order& o, bool takeover, uint64_t nowMs);
        void OrderReady(Order& o, uint64_t nowMs);
        void Deliver(Order& o, Player* customer);
        void ExpirePickup(Order& o);
        void RefundAll(Order& o, std::string_view why);
        void ClosePath(CafeRt& c, char shiftReason);
        void DropLeftovers(Order& o, std::string const& ticketLine);   // ticket, house job, counter cup (no money)
        HouseJob HouseJobOf(Order const& o) const;
        void DropNpcOrders(CafeRt& c);
        std::string OrderLineOf(Order const& o) const;
        std::string ThanksOf(Order const& o) const;
        std::string ComplaintOf(Order const& o) const;
        std::string DrinkName(uint16_t recipeId) const;

        // rewards
        void GrantDrink(Player* player, uint16_t recipeId, bool perfect, bool rush, uint32_t minutesOverride = 0);
        void GrantLevelRewards(Player* player, Barista& b, bool announce);
        void GiveItem(Player* player, uint32_t lowGuid, uint32_t itemId, uint8_t cafeId, std::string_view why);
        void AddBaristaXp(Player* player, Barista& b, uint32_t xp, bool& levelUp);
        uint32_t AuraLeftMs(Player* player, uint32_t spellId) const;

        // views
        void MarkView(uint64_t guid, uint8_t bits);
        void MarkCafeBaristas(uint8_t cafeId, uint8_t bits);
        void MarkCafeList() { _cafeListDirty = true; }
        CafeList BuildCafeList();
        CafeState BuildState(Player* player);
        CafeQueue BuildQueue(uint8_t cafeId, Player* receiver);
        CafeTickets BuildTickets(Player* player);
        CafeMenu BuildMenu(Player* player, uint8_t cafeId);
        CafeOrderState BuildOrder(Player* player);
        CafeProfile BuildProfile(Player* player);
        CafeBuffs BuildBuffs(Player* player);
        CafeAtBar BuildAtBar(CafeRt const& c, uint64_t nowMs);
        void SendAtBar(CafeRt& c, uint64_t nowMs, bool newcomersOnly);
        void SendOrderState(Order const& o, std::optional<CafeOrderStateId> state = std::nullopt);
        void UpdateSnapshot();

        // ---------------------------------------------------------------------------------------------------------
        // BleakholdCafeStore.cpp
        // ---------------------------------------------------------------------------------------------------------
        void EnsureTables();
        void SeedOrderIds();
        void SettleLeftoverOrders();
        void LoadSites();
        bool SaveCafeRow(CafeRt const& c);
        bool SavePieceRows(CafeRt const& c, std::vector<uint16_t> const& slots);
        bool DeletePieceRow(uint8_t cafeId, uint16_t slot);
        bool DeleteSiteRows(uint8_t cafeId);
        Barista& BaristaOf(Player* player);
        Barista* LoadedBarista(uint32_t lowGuid);
        void LoadBaristaRow(Barista& b);
        void RollDay(Barista& b);
        void SaveBarista(Barista& b, bool sync = false);
        void SaveDayWeek(Barista& b);
        void FlushDb(uint64_t nowMs, bool all);
        bool PayOrder(Player* player, Order const& o);
        void SaveOrderState(Order const& o);
        void PayWage(Order& o, Player* barista, uint32_t wage);
        void RefundOrder(Order const& o, uint32_t amount, std::string_view why);
        void DeleteOrderRow(uint32_t orderId);
        void MailMoney(uint32_t lowGuid, uint8_t cafeId, uint32_t copper, std::string const& subject, std::string const& body,
            CharacterDatabaseTransaction* trans);
        std::vector<CafeRules::WeekRow> WeekRows(uint32_t weekId, uint8_t cafeId);
        std::vector<CafeRules::WeekRow> const& BoardRows(uint32_t weekId, uint8_t cafeId);
        void WeeklyPayout(uint32_t weekId, bool dry, Reply const* say);
        void LoadLastWinners();
        void FlagShift(Shift const& s, Barista const& b);

        // ---------------------------------------------------------------------------------------------------------
        // BleakholdCafeSite.cpp
        // ---------------------------------------------------------------------------------------------------------
        Map* MapOf(CafeRt const& c) const;
        void Recompute(CafeRt& c, Piece& p);           // world position from f/l/u/turn (and the ground snap)
        float FloorZ(CafeRt const& c, Piece const& p) const;
        void SpawnSite(CafeRt& c);
        void DespawnSite(CafeRt& c);
        void SpawnPiece(CafeRt& c, Piece& p);
        void DespawnPiece(CafeRt& c, Piece& p);
        void SpawnStaff(CafeRt& c);
        void DespawnStaff(CafeRt& c);
        void BuildSite(CafeRt& c);                     // the CafeSite of the crowd
        void SiteChanged(CafeRt& c);                   // respawn the crowd's view after a layout change
        GameObject* PieceObject(CafeRt const& c, Piece const& p) const;
        Piece* PieceOf(CafeRt& c, std::string_view role);
        Piece* NearestPiece(CafeRt& c, Player* gm);
        std::optional<Piece*> PickPiece(CafeRt& c, Player* gm, std::optional<uint16_t> slot, Reply const& say);
        bool CheckGm(Player* gm, CafeRt const& c, Reply const& say);
        void GuardSavedGo(uint32_t spawnId);
        void GuardSavedCreature(uint32_t spawnId, uint32_t entry);
        void AnchorMoved(CafeRt& c, Player* gm, std::string const& what, Reply const& say);
        std::string PieceLine(CafeRt const& c, Piece const& p) const;
        void Log(Player* gm, std::string const& what);

        // ---------------------------------------------------------------------------------------------------------
        // State
        // ---------------------------------------------------------------------------------------------------------
        CafeConfig _cfg;
        std::atomic<bool> _enabled{ false };           // Enable and _startupOk
        std::atomic<bool> _cfgEnable{ false };
        std::atomic<bool> _gmOnly{ true };
        std::atomic<uint32_t> _coffeePct{ 0 }, _teaPct{ 0 };
        static constexpr std::size_t MaxExcluded = 32;
        std::array<std::atomic<uint32_t>, MaxExcluded> _teaExcluded{};
        std::atomic<uint32_t> _teaExcludedCount{ 0 };
        bool _startupDone = false;
        bool _startupOk = false;
        bool _newArtOk = false;                        // UseNewArt and every new-art display is on the server
        bool _titlesOk = true;
        bool _wasEnabled = false;

        std::array<CafeRt, 2> _cafes;
        std::map<uint32_t, Order> _orders;
        std::unordered_map<uint64_t, Shift> _shifts;   // by raw player guid
        std::unordered_map<uint32_t, Barista> _baristas;   // by low guid
        std::unordered_map<uint64_t, View> _views;
        std::map<std::pair<uint32_t, uint32_t>, uint32_t> _pairs;   // (barista, customer) -> drinks today
        std::unordered_set<uint32_t> _shakePlayers;    // low guids with the shake buff or its helper
        std::unordered_set<uint32_t> _buffPlayers;     // low guids with a cafe buff (CAFBF every 60 s)
        std::map<std::pair<uint32_t, uint8_t>, BoardCache> _boards;   // this week and the last only
        std::vector<CafeRules::WeekRow> _boardOther;   // the answer for any other week (not kept)
        std::vector<CafeLastWinner> _lastWinners;
        std::vector<std::function<void()>> _crowdCalls;   // crowd calls made from a CrowdSink callback, run after it
        struct GuardCheck { uint64_t atMs = 0; uint32_t spawnId = 0; bool creature = false; };
        std::vector<GuardCheck> _guardChecks;          // the .gobject and .npc guards' re-check of their DELETE
        std::unordered_map<uint32_t, CafeRules::Linger> _lingers;   // low guid -> the last drink (Lingering Sip)
        bool _tellRefusals = false;                    // HandleOrder from the gossip without the addon: refusals as
                                                       // system messages too (ERR never reaches such a client)
        uint32_t _startSec = 0;                        // OnStartup: a crashed shift's break counts from here
        bool _inCrowdUpdate = false;
        bool _cafeListDirty = false;
        uint64_t _cafeListSentMs = 0;
        uint32_t _nextOrderId = 1;
        uint32_t _nextTicketId = 1;
        uint64_t _lastTickMs = 0, _lastSecondMs = 0, _lastPeriodMs = 0, _lastMinuteMs = 0;
        uint32_t _dayId = 0, _weekId = 0;
        uint64_t _epochMs = 0;                         // the crowd's clock starts here (32 bits of ms)
        bool _resetFallbackLogged = false;

        std::mutex _eventLock;
        std::vector<Event> _events;

        mutable std::mutex _snapLock;
        GossipSnap _snap;
    };
}

#endif
