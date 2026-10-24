/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * ================================================================================================
 *  Public API: the only header your own systems need.   #include "BleakholdUi.h"
 * ================================================================================================
 *
 * The module owns the protocol (parsing, rate limits, handshake, revisions, chunking, escaping).
 * Your systems only do two things:
 *
 *   1. PUSH state when it changes, with one function per server message:
 *          Bleakhold::KeyState ks;
 *          ks.dungeonId = 602; ks.level = 8; ks.affixIds = { 1, 3, 4 }; ks.mode = 2;
 *          Bleakhold::Ui::SendKeyState(player, ks);
 *      The module remembers the last state you pushed and answers the client's GET requests with it,
 *      so pushing on change is all most systems need.
 *
 *   2. HANDLE the player's intents (what the player asked for):
 *          Bleakhold::Ui::OnIntent(Bleakhold::IntentType::TaskClaim, [](Player* p, Bleakhold::Intent const& in) {
 *              if (!MyTasks::CanClaim(p, in.taskUid))
 *                  return Bleakhold::Ui::Refuse(p, in, "not_claimable", "That task cannot be claimed yet.");
 *              MyTasks::Claim(p, in.taskUid);   // your code checks, pays once, and pushes the new state
 *          });
 *      Intents are untrusted requests: check authority and state in your handler, make it idempotent
 *      (a repeated claim must not pay twice), and answer a refusal with Refuse(). The module already
 *      dropped malformed and rate-limited messages, checked the group leader for KSTART/KCANCEL and
 *      refused EMOJI while BleakholdUi.Emoji.Enable = 0.
 *
 *   3. Bleakhold Royale (docs/BleakholdProtocol.md section 17) is wired the same way:
 *          Ui::SetFeature(FeatureRoyale, true);                 // once the mode is set up (HELLO bit 4096)
 *          Ui::OnIntent(IntentType::RoyaleDrop, [](Player* p, Intent const& in) { ... in.dropX, in.dropY ... });
 *          Ui::OnRequest(Topic::RoyaleState, [](Player* p, TopicRequest const&) { Ui::SendRoyaleState(p, ...); });
 *      QJOIN kind B arrives at your QJOIN handler (intent.queueKind == QueueKind::Royale). While the feature bit is
 *      off the module answers QJOIN B, RDROP and RSPEC with ERR royale_off and drops RDEPLOY, whoever handles them.
 *
 * Threading: every function here may be called from any thread (map update threads included). The
 * module queues the frames and sends them from the world thread. Your handlers and providers are
 * always called on the world thread, never while the module holds a lock.
 *
 * Nothing is sent to a player whose client has not sent HELLO (players without the addon); pushed
 * states are still remembered and served once the client asks.
 */

#ifndef BLEAKHOLD_UI_H
#define BLEAKHOLD_UI_H

#include "BleakholdEmoji.h"
#include "BleakholdMessages.h"

#include <functional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

class Player;

namespace Bleakhold::Ui
{
    // =============================================================================================
    // Intents (client to server)
    // =============================================================================================

    // Your handler for one intent op. Registering replaces the module's default for that op.
    //   Defaults: TCLAIM TREROLL QJOIN QLEAVE QREPLY KMODE KSTART KCANCEL BCLAIM OUTFIT -> ERR "unavailable";
    //   WEHANDIN -> token hand-in from mod_bleakhold_ui.conf (BleakholdUi.WarEffort.*), else "unavailable";
    //   LBQ -> the module's own leaderboard tables; EMOJI -> emoji bubble (BleakholdUi.Emoji.*);
    //   DANCE -> Bleakhold dance (BleakholdUi.Dance.*); CASEOPEN -> the module's cases (bleakhold_case,
    //   BleakholdUi.Case.*); CAMP GLIDE REPAIR -> the module's camping (BleakholdUi.Camp.*, Glide.*, Repair.*).
    //   BleakholdUi.Camp.Enable, Glide.Enable and Repair.Enable hold for your handler too (ERR camp_off, glide_off,
    //   repair_off).
    //   RDROP RSPEC -> ERR "unavailable"; RDEPLOY -> nothing (it is never answered, not even with ERR busy over its
    //   rate limit). While FeatureRoyale is off (SetFeature below) QJOIN with kind B, RDROP and RSPEC get
    //   ERR royale_off and RDEPLOY is dropped, also with your handler.
    //   HELLO, GET and PING are handled by the module.
    using IntentHandler = std::function<void(Player* player, Intent const& intent)>;
    void OnIntent(IntentType type, IntentHandler handler);

    // The SMSG_PLAY_SPELL_VISUAL kit that shows emoji `emojiId` (< EmojiCatalogueCount, BleakholdEmoji.h)
    // over a unit: unit->SendPlaySpellVisual(Ui::EmojiKit(id)) (EMOJI, docs/BleakholdProtocol.md section 13).
    inline constexpr uint32_t EmojiKit(uint32_t emojiId) { return 900000 + emojiId; }

    // The SMSG_PLAY_SPELL_VISUAL kit that plays dance `danceId` (< DanceCatalogueCount, BleakholdDance.h) on a unit
    // whose emote state is EMOTE_STATE_DANCE (DANCE, docs/BleakholdProtocol.md section 14).
    inline constexpr uint32_t DanceKit(uint32_t danceId) { return 910000 + danceId; }

    // Answer a refused intent with ERR. code: a short machine code ("not_claimable"); text: a sentence
    // for the player. Never put client-supplied text in either.
    void Refuse(Player* player, Intent const& intent, std::string_view code, std::string_view text);
    // The same with a code of the protocol and its default sentence (RoyaleErr::Phase, ... in BleakholdMessages.h).
    inline void Refuse(Player* player, Intent const& intent, Refusal const& refusal)
    {
        Refuse(player, intent, refusal.code, refusal.text);
    }

    // Called after every valid HELLO (login or /reload), after the module answered it. Optional.
    void OnHello(std::function<void(Player* player, Intent const& hello)> observer);

    // True when this player's client completed the handshake (has the Bleakhold addon running).
    bool HasAddon(Player* player);

    // HELLO feature bits (FeatureBits in BleakholdMessages.h) that your system turns on at runtime, on top of the
    // ones mod_bleakhold_ui.conf sets: SetFeature(FeatureRoyale, true) once Bleakhold Royale validated its data,
    // false when it turns off. false only withdraws an earlier true; it never hides a bit the configuration sets.
    // Clients already connected get a new HELLO with the new bits. Any thread.
    void SetFeature(uint32_t feature, bool on);
    // Whether HELLO announces the bit now (configured, runtime or, for FeatureCases, a case exists). Any thread.
    bool FeatureOn(uint32_t feature);

    // =============================================================================================
    // Topic requests (GET)
    // =============================================================================================

    // Your provider for a GET topic. It should push the current state with the matching Send function
    // (or send nothing if there is none). Registering replaces the module's default for the topic:
    //   WEEK TASKS KEY BOARD QUEUE COLL RIFT -> the last state you pushed;
    //   ERA -> bleakhold_week_schedule; SEASON -> bleakhold_season + war effort tables;
    //   SET, LIDX -> bleakhold_legacy_set; FIRSTS -> bleakhold_server_first; MPLUS -> the run tracker;
    //   DEF -> the definition tables; CAMPST -> the module's camping state; ROYS ROYM -> nothing. Example:
    //     Ui::OnRequest(Topic::Week, [](Player* p, TopicRequest const&) { Ui::SendWeek(p, MySeason::Week(p)); });
    using TopicProvider = std::function<void(Player* player, TopicRequest const& request)>;
    void OnRequest(Topic topic, TopicProvider provider);

    // Run the topic's provider (yours or the default) as if the client had asked.
    void Refresh(Player* player, Topic topic);

    // =============================================================================================
    // Revisioned snapshots and deltas (one function per server message). Push on every change.
    // =============================================================================================
    void SendWeek(Player* player, WeekState const& week);             // WEEK
    void SendEra(Player* player, EraState const& era);                // ERA
    void SendTasks(Player* player, TaskList const& tasks);            // TASKS
    // TASK delta for one task (0 -> 1 shows the "task done" toast). Also updates the remembered TASKS.
    void TaskProgress(Player* player, uint32_t uid, uint32_t have, TaskState state);
    void SendKeyState(Player* player, KeyState const& key);           // KEY
    void BoardSnapshot(Player* player, BoardState const& board);      // BOARD
    void QueueStatus(Player* player, QueueState const& queue);        // QUEUE
    void SendCollections(Player* player, CollectionState const& coll);// COLL
    void SendLegacyIndex(Player* player, LegacyIndex const& index);   // LIDX
    // LCOL delta: the look of a legacy item was collected (or lost). Updates the remembered LIDX.
    void LegacyItemCollected(Player* player, uint32_t itemId, bool collected);
    void SendSeason(Player* player, SeasonState const& season);       // SEASON

    // =============================================================================================
    // Unrevisioned states and events
    // =============================================================================================
    void SendLegacySet(Player* player, LegacySet const& set);         // SET (answer to GET SET,tier,class)
    void SendCases(Player* player, CaseList const& cases);            // CASES (section 15)
    void SendCase(Player* player, CaseInfo const& info);              // CASE (answer to GET CASE,item)
    void SendUnbox(Player* player, Unbox const& won);                // UNBOX (answer to CASEOPEN)
    void SendCampState(Player* player, CampState const& camp);        // CAMPST (section 16; the module sends it itself)
    void RiftStatus(Player* player, RiftState const& rift);           // RIFT (remembered for GET RIFT)
    void RiftEnded(Player* player, RiftEnd const& summary);           // RIFTE
    void SendLeaderboard(Player* player, Leaderboard const& page);    // LB
    void SendLeaderboardMe(Player* player, LeaderboardMe const& me);  // LBME
    void SendFirsts(Player* player, FirstsList const& firsts);        // FIRSTS
    void SendToast(Player* player, Toast const& toast);               // TOAST
    inline void Toast(Player* player, ToastKind kind, std::string title, std::string subtitle = {}, std::string openTarget = {})
    {
        SendToast(player, Bleakhold::Toast{ kind, std::move(title), std::move(subtitle), std::move(openTarget) });
    }
    // Bleakhold Royale (section 17), all unrevisioned and never remembered: answer GET ROYS with SendRoyaleState then
    // a full SendRoyaleObjects, and GET ROYM with SendRoyaleMap, from your own match state. The list versions send
    // the same message to every player of a match (encoded once).
    void SendRoyaleState(Player* player, RoyaleState const& state);   // ROYS (per player: me, kills, pin, watch)
    void SendRoyaleMap(Player* player, RoyaleMap const& map);         // ROYM
    void SendRoyaleMap(std::vector<Player*> const& players, RoyaleMap const& map);
    void SendRoyaleObjects(Player* player, RoyaleObjects const& objects);   // ROYO
    void SendRoyaleObjects(std::vector<Player*> const& players, RoyaleObjects const& objects);
    void SendRoyaleKill(Player* player, RoyaleKill const& kill);      // ROYK
    void SendRoyaleKill(std::vector<Player*> const& players, RoyaleKill const& kill);
    void SendRoyaleEvent(Player* player, RoyaleEvent const& event);   // ROYV
    void SendRoyaleEvent(std::vector<Player*> const& players, RoyaleEvent const& event);
    void SendRoyaleResult(Player* player, RoyaleResult const& result);   // ROYE (the player's own result)
    // Low-level keystone run messages for one player. Prefer the run tracker below.
    void SendKeyRunStart(Player* player, Bleakhold::KeyRunStart const& start);   // MPS
    void SendKeyRunState(Player* player, KeyRunState const& state);   // MP
    void SendKeyRunEnd(Player* player, KeyRunEnd const& end);         // MPE

    // =============================================================================================
    // Keystone run tracker: keeps the MP state of a run, sends it to every member on each change and
    // every BleakholdUi.KeyRun.HeartbeatSec as a heartbeat, and answers GET MPLUS (after a /reload).
    // Your Mythic+ system decides everything (timer, penalties, completion); the tracker only reports.
    // =============================================================================================
    struct KeyRunInfo
    {
        uint32_t runId = 0;                  // 0 = the module picks one (returned)
        uint32_t dungeonId = 0;              // map id
        uint32_t level = 0;
        std::vector<uint32_t> affixIds;
        Opt<uint32_t> eraId;
        uint32_t countdownMs = 10000;        // shown by the client (and the DBM pull timer)
        uint32_t timeLimitSec = 0;
        uint32_t forcesMax = 100;
        std::vector<uint32_t> chestSec;      // optional ticks on the timer bar, e.g. { 1260, 1440 }
    };

    // MPS + MP(countdown) to every member; root the group yourself. `leader` is the sender of the DBM
    // pull timer when BleakholdUi.KeyRun.ServerPullTimer = 1 (defaults to the first member).
    uint32_t KeyRunStart(KeyRunInfo const& info, std::vector<Player*> const& members, Player* leader = nullptr);
    void KeyTimerStart(uint32_t runId);                                   // countdown over: MP state 1
    void KeyBossKilled(uint32_t runId, uint32_t bossIndex);               // 1-based kill order of DEF D
    void KeyEnemyForces(uint32_t runId, uint32_t current, Opt<uint32_t> max = std::nullopt);
    void KeyDeath(uint32_t runId, uint32_t penaltySec);                   // one death, plus the penalty you apply
    void KeyCompleted(uint32_t runId, KeyRunEnd const& result);           // MP state 2/3, then MPE; run closed
    void KeyAbandoned(uint32_t runId);                                    // MP state 4 (also cancels a countdown); run closed
    void KeyRunAddMember(uint32_t runId, Player* player);                 // late joiner: gets MPS + MP
    void KeyRunRemoveMember(uint32_t runId, Player* player);
    // Replace the tracked state (for example your timer paused); runId and the member list are kept.
    void KeyRunSync(uint32_t runId, KeyRunState const& state);
    Opt<uint32_t> KeyRunOf(Player* player);                               // the run this player is in

    // =============================================================================================
    // Server-wide chat announcements (CHAT_MSG_SYSTEM with a tag the addon colours and can hide)
    // =============================================================================================
    enum class AnnounceTag : uint8_t { RaidLegacy, ServerFirst, Season, Queue, Record, Case, Royale };
    // To every online player. `text` is server text and may contain real |Hitem:...|h links.
    void Announce(AnnounceTag tag, std::string_view text);
    void AnnounceTo(Player* player, AnnounceTag tag, std::string_view text);

    // =============================================================================================
    // The module's own tables (characters database): leaderboards, server firsts, war effort
    // =============================================================================================
    struct LeaderboardEntry
    {
        Board board = Board::Keys;           // K, R or E
        uint32_t seasonId = 0;               // 0 = the current season
        uint32_t dungeonId = 0;              // K: map id, R: 0, E: what you group Echo kills by (0 = all)
        Opt<int64_t> value;                  // K: key level, R: floor
        Opt<int64_t> timeSec;                // K: time left (negative = over time), R: run time, E: kill time
        std::string label;                   // E: boss name
        std::vector<Player*> members;        // the group (names and classes are stored)
    };
    // Stores a finished run; the module's LB/LBME answers rank from these rows (best row per group).
    void RecordLeaderboardRun(LeaderboardEntry const& entry);

    // Stores a server first once per firstId (returns false if it already exists) and announces it
    // with [Server First] unless announce = false. kindKey: echo, key, rift, ... (shown by FIRSTS).
    bool RecordServerFirst(std::string_view firstId, std::string_view kindKey, std::string_view text,
        std::string_view who, bool announce = true);

    // Adds war effort points of the current season (your systems decide when and how many).
    void WarEffortAdd(Player* player, uint32_t partId, uint32_t points);
    uint64_t WarEffortPoints(Player* player);

    // Weekly bonus state for the default ERA answer.
    void SetWeeklyBonusDone(Player* player, bool done);

    // =============================================================================================
    // Sources for the module's defaults (all optional)
    // =============================================================================================
    // Called after the definition tables are loaded (startup and .bleakhold reload): add or change
    // entries from your systems; the module recomputes dataVer.
    void OnDefinitionsLoaded(std::function<void(Definitions& defs)> editor);

    // Legacy collections: whether the look of an item is collected / a set's outfit is unlocked.
    // Without them the default SET/LIDX answers leave those fields empty.
    void SetLegacyCollectionSource(std::function<bool(Player*, uint32_t itemId)> itemCollected,
        std::function<bool(Player*, uint32_t setId)> outfitUnlocked = {});

    // Season rewards: fill `out` (earned, stateText) for a reward of the current season and return true.
    void SetSeasonRewardSource(std::function<bool(Player*, uint32_t rewardId, SeasonRewardState& out)> source);

    // Next daily and weekly reset (Unix time) for HELLO. Default: the core's quest reset times.
    void SetResetTimesSource(std::function<std::pair<uint32_t, uint32_t>()> source);

    // Season id for HELLO, SEASON and the leaderboards. Default: BleakholdUi.Season.Id, else the
    // bleakhold_season row with state 1.
    void SetCurrentSeason(uint32_t seasonId);
    uint32_t CurrentSeason();
}

#endif
