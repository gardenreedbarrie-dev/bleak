/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Internal: per-player protocol slots, the outbox that is flushed on the world thread, intent
 * dispatch and the keystone run tracker. Your code uses BleakholdUi.h instead.
 */

#ifndef BLEAKHOLD_MGR_H
#define BLEAKHOLD_MGR_H

#include "BleakholdEndpoint.h"
#include "BleakholdUi.h"

#include <array>
#include <atomic>
#include <cstdint>
#include <functional>
#include <map>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>

class Player;

namespace Bleakhold
{
    struct Config
    {
        bool enable = true;
        bool debug = false;
        std::string realmName;
        std::string siteUrl;
        bool utcOffsetAuto = true;
        int32_t utcOffsetMin = 0;
        uint32_t minProto = 1;
        uint32_t dataVersion = 0;             // 0 = automatic (hash of the definitions)
        uint32_t featureBits = 0;
        uint32_t seasonId = 0;                // 0 = the bleakhold_season row with state 1
        std::size_t maxFrameBody = 1000;
        Proto::Limits limits;
        uint32_t heartbeatMs = 15000;
        bool serverPullTimer = false;
        bool colorTagsWithoutAddon = true;
        std::array<std::string, 9> tagColors{
            { "E5C07B", "FF9D3B", "6CC6D9", "9FD8E5", "F1D9A0", "C9A2F5", "B98CFF", "E0604A", "D8B98A" } };
        uint32_t tokenItemId = 0;
        uint32_t pointsPerToken = 0;
        uint32_t tokenPart = 1;
        uint32_t leaderboardPageSize = 10;
        uint32_t leaderboardMaxRows = 1000;
        bool emojiEnable = true;              // EMOJI (the catalogue is BleakholdEmoji.h)
        bool danceEnable = true;              // DANCE (the catalogue is BleakholdDance.h)
        bool caseEnable = true;               // CASEOPEN (feature bit 256 also needs a case, Data::HasCases)
        bool campEnable = true;               // CAMP, CAMPST, warmth and food XP (feature bit 512; BleakholdCamp.h)
        bool glideEnable = true;              // GLIDE (feature bit 1024)
        bool repairEnable = true;             // REPAIR for blacksmiths anywhere (feature bit 2048)
    };

    struct OutItem
    {
        enum class Kind : uint8_t { Addon, System, PullTimer };
        Kind kind = Kind::Addon;
        std::string text;
        uint64_t sender = 0;      // PullTimer: raw guid of the group leader
        uint8_t chatType = 0;     // PullTimer: CHAT_MSG_PARTY / CHAT_MSG_RAID / CHAT_MSG_WHISPER
    };

    struct PlayerSlot
    {
        Proto::Endpoint ep;
        uint32_t lowGuid = 0;
        std::string name;
        uint8_t classId = 0;

        // the last states pushed by your systems (answers GET without a provider)
        Opt<WeekState> week;
        Opt<EraState> era;
        Opt<TaskList> tasks;
        Opt<KeyState> key;
        Opt<BoardState> board;
        Opt<QueueState> queue;
        Opt<CollectionState> coll;
        Opt<LegacyIndex> lidx;
        Opt<SeasonState> season;
        Opt<RiftState> rift;
        Opt<bool> weeklyBonusDone;

        std::vector<OutItem> outbox;
    };

    struct KeyRun
    {
        Ui::KeyRunInfo info;
        KeyRunState state;
        std::vector<uint64_t> members;   // raw guids
        uint64_t leader = 0;
        uint8_t pullChatType = 0;
        uint64_t timerStartMs = 0;       // steady clock when state became Running
        uint32_t elapsedBaseMs = 0;      // elapsed at timerStartMs (KeyRunSync)
        uint64_t lastBeatMs = 0;
        uint64_t createdMs = 0;
    };

    class Mgr
    {
    public:
        static Mgr& Instance();

        // ---- configuration and lifecycle (world thread) ----
        void LoadConfig();
        // World thread only (the configuration is replaced there). Other threads use CfgCopy().
        Config const& Cfg() const { return _cfg; }
        Config CfgCopy();
        bool Enabled() const { return _enabled.load(); }
        bool Debug() const { return _debugOn.load(); }
        void SetDebug(bool on);
        void OnLogin(Player* player);
        void OnLogout(Player* player);
        void Update(uint32_t diff);
        void MarkWorldThread() { _worldThread = std::this_thread::get_id(); }

        // The chat hook: returns what OnPlayerCanUseChat must return.
        bool OnSelfWhisper(Player* player, std::string const& text);

        // ---- dispatch ----
        void SetHandler(IntentType type, Ui::IntentHandler h);
        void SetProvider(Topic topic, Ui::TopicProvider p);
        void SetDefaultHandler(IntentType type, Ui::IntentHandler h);
        void SetDefaultProvider(Topic topic, Ui::TopicProvider p);
        // LBQ of one board (Ui::OnBoardQuery): answers that board before the LBQ handler and the default
        void SetBoardHandler(Board board, Ui::IntentHandler h);
        // Ui::OnHello: every observer added runs after each valid HELLO, in the order added.
        void AddHelloObserver(std::function<void(Player*, Intent const&)> f)
        {
            std::lock_guard<std::recursive_mutex> guard(_lock);
            if (f)
                _helloObservers.push_back(std::move(f));
        }
        void Refresh(Player* player, Topic topic);
        void Refuse(Player* player, Intent const& intent, std::string_view code, std::string_view text);

        // ---- sending (any thread) ----
        // Updates the slot under the lock, then (if the client is ready) frames the payload built from the
        // next revision of `topic` (Topic::Count = unrevisioned) and queues it.
        void Push(Player* player, char const* op, Topic topic, std::function<void(PlayerSlot&)> const& update,
            std::function<std::string(uint32_t rev)> const& encode);
        void PushTo(uint64_t guid, char const* op, std::string const& payload);
        // Resends the remembered state of a topic; false when there is none (or the client is not ready).
        bool ResendCached(Player* player, Topic topic);
        Opt<bool> WeeklyBonusDone(Player* player);
        void ClearCaches(Topic topic);
        void TaskDelta(Player* player, uint32_t uid, uint32_t have, TaskState state);
        void LegacyDelta(Player* player, uint32_t itemId, bool collected);
        void SetWeeklyBonusDone(Player* player, bool done);
        bool HasAddon(Player* player);
        bool HasClientCap(Player* player, uint32_t cap);
        void QueueSystem(Player* player, std::string text);
        void Announce(Ui::AnnounceTag tag, std::string_view text, uint64_t onlyGuid = 0);
        // BleakholdUi.Case.Enable (the case list is empty to clients while it is off).
        bool CasesEnabled() const { return _cfg.caseEnable; }
        // HELLO feature bits a system turns on at runtime (Ui::SetFeature), on top of the configured ones (any thread).
        // A change sends a new HELLO to every ready client on the next world tick.
        void SetFeature(uint32_t feature, bool on);
        bool FeatureOn(uint32_t feature);
        // A new HELLO to every ready client on the next world tick (a per-player feature bit changed: BleakholdUi.Cafe.GmOnly).
        void RefreshHello();
        // Pushes the full DEF set to one player (answer to GET DEF,0) or to every ready player.
        void SendDefinitions(Player* player);
        void BroadcastDefinitions();
        // Runs `fn` for every player whose client is ready (world thread; no lock held during fn).
        void ForEachReadyPlayer(std::function<void(Player*)> const& fn);

        // ---- key run tracker (any thread) ----
        uint32_t RunStart(Ui::KeyRunInfo const& info, std::vector<Player*> const& members, Player* leader);
        void RunTimerStart(uint32_t runId);
        void RunBoss(uint32_t runId, uint32_t bossIndex);
        void RunForces(uint32_t runId, uint32_t cur, Opt<uint32_t> max);
        void RunDeath(uint32_t runId, uint32_t penaltySec);
        void RunCompleted(uint32_t runId, KeyRunEnd const& result);
        void RunAbandoned(uint32_t runId);
        void RunAddMember(uint32_t runId, Player* player);
        void RunRemoveMember(uint32_t runId, Player* player);
        void RunSync(uint32_t runId, KeyRunState const& st);
        Opt<uint32_t> RunOf(Player* player);
        bool SendRunTo(Player* player);   // GET MPLUS: MPS + MP if the player is in a run

        // ---- timers for the test command (world thread) ----
        void After(uint32_t ms, std::function<void()> fn);

        // ---- status ----
        struct Status
        {
            uint32_t online = 0, ready = 0, runs = 0;
            uint64_t received = 0, accepted = 0, refused = 0, dropped = 0, framesOut = 0, mutes = 0;
            std::array<uint64_t, static_cast<std::size_t>(DropReason::Count)> drops{};
        };
        Status GetStatus();
        Opt<Proto::EndpointStats> StatsOf(Player* player);

        uint32_t DataVersion() const { return _dataVer.load(); }
        void SetDataVersion(uint32_t v) { _dataVer = v; }
        static uint64_t NowMs();

    private:
        Mgr() = default;

        PlayerSlot* Slot(uint64_t guid);
        PlayerSlot* SlotFor(Player* player, bool create);
        void QueueFrames(uint64_t guid, PlayerSlot& slot, char const* op, std::string const& payload);
        void Dispatch(Player* player, Intent const& intent);
        void SendHello(Player* player);
        void FlushAll();
        bool OnWorldThread() const { return _worldThread == std::this_thread::get_id(); }

        // run helpers (lock held)
        KeyRunState RunSnapshot(KeyRun& run, uint64_t nowMs);
        void RunBroadcastLocked(KeyRun& run, uint64_t nowMs);
        void RunQueueStartLocked(KeyRun& run, uint64_t guid, uint64_t nowMs);
        void RunPullTimerLocked(KeyRun& run, uint32_t seconds);

        std::recursive_mutex _lock;
        Config _cfg;
        std::unordered_map<uint64_t, PlayerSlot> _slots;
        std::unordered_set<uint64_t> _dirty;
        std::vector<std::pair<uint8_t, std::string>> _announces;   // tag, text (onlyGuid = 0)
        std::map<uint32_t, KeyRun> _runs;
        uint32_t _nextRunId = 1;

        std::array<Ui::IntentHandler, static_cast<std::size_t>(IntentType::Count)> _handlers{};
        std::array<Ui::IntentHandler, static_cast<std::size_t>(IntentType::Count)> _defaultHandlers{};
        std::array<Ui::TopicProvider, static_cast<std::size_t>(Topic::Count)> _providers{};
        std::array<Ui::TopicProvider, static_cast<std::size_t>(Topic::Count)> _defaultProviders{};
        std::vector<std::function<void(Player*, Intent const&)>> _helloObservers;
        std::map<char, Ui::IntentHandler> _boardHandlers;   // by Board letter

        std::vector<std::pair<uint64_t, std::function<void()>>> _timers;
        std::thread::id _worldThread;
        std::atomic<uint32_t> _dataVer{ 1 };
        std::atomic<uint32_t> _runtimeFeatures{ 0 };
        std::atomic<bool> _enabled{ true };
        std::atomic<bool> _debugOn{ false };
        uint64_t _lastSweepMs = 0;
        uint64_t _droppedTotalLogged = 0;
    };

    // Debug line in the "module" log when BleakholdUi.Debug = 1.
    void DebugLog(std::string const& line);
}

#endif
