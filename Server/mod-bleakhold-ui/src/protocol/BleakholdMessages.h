/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Data of every server-to-client message (section 7) and its payload encoder. No AzerothCore
 * dependency: these are plain structs your systems fill in, and Encode*() turns them into payloads.
 *
 * Conventions:
 *  - Fields are in the order of the document.
 *  - An unset Opt<> field, an empty string or an empty list is sent as an empty field: "missing",
 *    the client shows its default (or leaves the line out).
 *  - Texts are cleaned (valid UTF-8, no NUL) and cut to the length the client keeps.
 *  - Revisioned messages take their `rev` from the module; you never set it.
 */

#ifndef BLEAKHOLD_MESSAGES_H
#define BLEAKHOLD_MESSAGES_H

#include "BleakholdIntent.h"

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace Bleakhold
{
    template <typename T>
    using Opt = std::optional<T>;

    // ---------------------------------------------------------------------------------------------
    // Shared enums
    // ---------------------------------------------------------------------------------------------
    enum class RewardKind : char { MythicCoins = 'C', Shards = 'S', Item = 'I', Copper = 'G', Text = 'T' };
    enum class Currency : char { Copper = 'G', MythicCoins = 'C' };
    enum class TaskKind : char { Daily = 'D', Weekly = 'W' };
    enum class TaskState : uint8_t { Open = 0, Claimable = 1, Claimed = 2 };
    enum class ToastKind : char { Task = 'T', Queue = 'Q', Keystone = 'K', Record = 'R', Season = 'S', Info = 'I' };
    enum class KeyModeId : uint8_t { Normal = 0, Heroic = 1, Mythic = 2 };
    enum class QueueStateId : uint8_t { NotQueued = 0, Queued = 1, Proposal = 2, InRun = 3 };
    enum class ProposalAnswer : uint8_t { Pending = 0, Accepted = 1, Declined = 2 };
    enum class KeyRunStateId : uint8_t { Countdown = 0, Running = 1, FinishedInTime = 2, FinishedOverTime = 3, Abandoned = 4 };
    enum class KeyRunResultId : uint8_t { OverTime = 0, InTime = 1, Abandoned = 2 };
    enum class RiftStateId : uint8_t { NoRun = 0, Running = 1, Over = 2 };
    enum class BountyState : uint8_t { None = 0, Open = 1, Claimable = 2, Claimed = 3 };
    enum class SeasonStateId : uint8_t { Past = 0, Current = 1, Upcoming = 2 };

    // HELLO feature bits.
    enum FeatureBits : uint32_t
    {
        FeatureRiftScoring = 1,
        FeatureShards = 2,
        FeatureServerPullTimer = 4,   // the server sends the DBM pull timer itself (section 9)
        FeatureSeason = 8,
        FeatureLeaderboards = 16,
        FeatureCollections = 32,
        FeatureEmoji = 64,            // emoji bubbles (EMOJI, section 13)
        FeatureDance = 128,           // Bleakhold dances (DANCE, section 14)
        FeatureCases = 256,           // cases (CASEOPEN, section 15)
    };

    // One reward line of MPE / RIFTE.
    struct Reward
    {
        RewardKind kind = RewardKind::Text;
        Opt<uint32_t> amount;
        Opt<uint32_t> itemId;
        std::string text;            // overrides the generated reward text when not empty
    };

    // ---------------------------------------------------------------------------------------------
    // HELLO, PONG, ERR, TOAST
    // ---------------------------------------------------------------------------------------------
    struct HelloReply
    {
        uint32_t proto = 1;
        uint32_t minProto = 1;
        uint32_t serverEpoch = 0;
        int32_t utcOffsetMin = 0;
        uint32_t dataVer = 0;
        uint32_t featureBits = 0;
        Opt<uint32_t> seasonId;
        Opt<uint32_t> dailyResetEpoch;
        Opt<uint32_t> weeklyResetEpoch;
        std::string realmName;
        std::string siteUrl;
    };

    struct Pong
    {
        uint32_t nonce = 0;
        uint32_t serverEpoch = 0;
    };

    struct ErrorReply
    {
        IntentType op = IntentType::Count;  // the refused op
        uint32_t seq = 0;                   // its client SEQ
        std::string code;                   // machine code, e.g. "not_claimable"
        std::string text;                   // sentence for the player
    };

    struct Toast
    {
        ToastKind kind = ToastKind::Info;
        std::string title;
        std::string subtitle;
        std::string openTarget;   // tasks, dungeons, keys, rift, collections, season, leaderboards or empty
    };

    // ---------------------------------------------------------------------------------------------
    // DEF: definitions (names and texts). The module loads them from the world database; your code can
    // add to them (Ui::OnDefinitionsLoaded).
    // ---------------------------------------------------------------------------------------------
    struct AffixDef { uint32_t id = 0; std::string name, text; };
    struct EraDef { uint32_t id = 0; std::string name, text; Opt<uint32_t> legacyTier; };
    struct TaskTemplateDef { uint32_t id = 0; std::string title, text; };
    struct WeeklyBonusDef { uint32_t id = 0; std::string title, text; };
    struct ChapterDef { uint32_t id = 0; std::string name, text; };
    struct DungeonDef
    {
        uint32_t id = 0;                     // map id
        std::string name;
        Opt<uint32_t> chapter, lvlMin, lvlMax;
        std::vector<std::string> bosses;     // kill order (bit i-1 of MP bossBits is boss i)
        Opt<uint32_t> timeLimitSec;          // keystone timer
    };
    struct LegacyTierDef
    {
        uint32_t id = 0;
        std::string label, raids;
        Opt<uint32_t> eraId;
        std::vector<uint32_t> sources;       // dungeon ids
        Opt<uint32_t> lvlMin, lvlMax;
        std::string echoBoss;
        Opt<uint32_t> pieceTotal;
    };
    struct SeasonDef { uint32_t id = 0; std::string name, text; SeasonStateId state = SeasonStateId::Upcoming; };
    struct RankDef { uint32_t id = 0; std::string name; };
    struct SeasonRewardDef { uint32_t id = 0; std::string name, requirementText; };
    struct MythicLevelDef { uint32_t level = 0; std::string text; };
    struct ExtraClassDef { uint32_t id = 0; std::string name, token, colorHex, shortLabel; };
    struct RiftBossDef { uint32_t id = 0; std::string name; };

    struct Definitions
    {
        std::vector<AffixDef> affixes;              // A
        std::vector<EraDef> eras;                   // E
        std::vector<TaskTemplateDef> taskTemplates; // T
        std::vector<WeeklyBonusDef> weeklyBonuses;  // B
        std::vector<ChapterDef> chapters;           // C
        std::vector<DungeonDef> dungeons;           // D
        std::vector<LegacyTierDef> legacyTiers;     // L
        std::vector<SeasonDef> seasons;             // S
        std::vector<RankDef> ranks;                 // K
        std::vector<SeasonRewardDef> seasonRewards; // W
        std::vector<MythicLevelDef> mythicLevels;   // M
        std::vector<ExtraClassDef> extraClasses;    // X
        std::vector<RiftBossDef> riftBosses;        // R
    };

    // ---------------------------------------------------------------------------------------------
    // Revisioned snapshots
    // ---------------------------------------------------------------------------------------------
    struct WeekState
    {
        Opt<uint32_t> keysTimed, raidEchoes, riftBestFloor, mythicCoins, mythicCoinsCap, shards;
    };

    struct EraState
    {
        Opt<uint32_t> eraId, nextEraId;
        std::vector<uint32_t> affixIds;
        Opt<uint32_t> weeklyBonusId;
        Opt<bool> weeklyBonusDone;
    };

    struct Task
    {
        uint32_t uid = 0;                    // your id; TCLAIM / TREROLL carry it back
        TaskKind kind = TaskKind::Daily;
        Opt<uint32_t> templateId;            // DEF T
        uint32_t have = 0;
        uint32_t need = 1;
        RewardKind rewardKind = RewardKind::Text;
        Opt<uint32_t> rewardAmount;
        Opt<uint32_t> rewardItemId;
        TaskState state = TaskState::Open;
        std::string title, text, rewardText; // override the template / generated text when not empty
    };

    struct TaskList
    {
        Opt<uint32_t> freeRerolls;
        Opt<uint32_t> rerollCost;
        Currency rerollCurrency = Currency::Copper;
        std::vector<Task> tasks;
    };

    struct KeyState
    {
        uint32_t dungeonId = 0;              // 0 = no keystone
        Opt<uint32_t> level;
        std::vector<uint32_t> affixIds;
        Opt<uint32_t> mode;                  // KeyModeId
        Opt<uint32_t> weeklyBestLevel, weeklyBestDungeonId, cachesReady, cachesBanked, keystoneItemId, maxLevel, eraId;
        Opt<bool> depleted;
    };

    struct BoardDungeon
    {
        uint32_t dungeonId = 0;
        Opt<uint32_t> chapter, lvlMin, lvlMax;
        Opt<uint32_t> tierBits;              // 1 Normal, 2 Veteran, 4 Elite, 8 Nightmare
        Opt<uint32_t> bestScore, bestTier, recordScore;
        std::string recordName;
        Opt<bool> locked;
    };

    struct BoardState
    {
        Opt<uint32_t> shards, bountyId, bountyDungeonId;
        BountyState bountyState = BountyState::None;
        std::string bountyRewardText;
        Opt<bool> firstRunBonus;
        std::vector<BoardDungeon> dungeons;
    };

    struct QueueMember
    {
        std::string name;
        Opt<uint32_t> classId;
        Opt<uint32_t> role;                  // RoleMask: 1, 2 or 4
        ProposalAnswer accepted = ProposalAnswer::Pending;
        Opt<uint32_t> level;
    };

    struct QueueState
    {
        QueueStateId state = QueueStateId::NotQueued;
        QueueKind kind = QueueKind::Dungeon;
        Opt<uint32_t> activityId, tier, size, queuedSec, estWaitSec, proposalId, timeoutSec, bandMin, bandMax;
        std::vector<QueueMember> members;    // for proposals
    };

    struct CollectionState
    {
        Opt<uint32_t> transmogOwned, transmogTotal, laterAgesOwned, laterAgesTotal, legacySetsOwned, legacySetsTotal;
        std::vector<uint32_t> tierHave, tierTotal;
    };

    struct LegacyIndexEntry
    {
        uint32_t itemId = 0;
        Opt<uint32_t> tier, setId;
        Opt<bool> collected;
    };

    struct LegacyIndex
    {
        std::vector<LegacyIndexEntry> items;   // the client reads at most 499 (500 records per message)
    };

    struct SeasonPart { std::string name; Opt<uint32_t> permille; };
    struct SeasonRewardState { uint32_t rewardId = 0; Opt<bool> earned; std::string stateText; };

    struct SeasonState
    {
        Opt<uint32_t> seasonId, warEffortPermille, contributors, points, rankId, nextRankId, pointsToNextRank;
        std::string warEffortTitle, warEffortText;
        Opt<uint32_t> spareTokens;
        std::vector<SeasonPart> parts;               // up to three are shown
        std::vector<SeasonRewardState> rewards;
    };

    // ---------------------------------------------------------------------------------------------
    // Unrevisioned states and events
    // ---------------------------------------------------------------------------------------------
    struct KeyRunStart   // MPS
    {
        uint32_t runId = 0;
        uint32_t dungeonId = 0;
        Opt<uint32_t> level;
        std::vector<uint32_t> affixIds;
        Opt<uint32_t> eraId;
        Opt<uint32_t> countdownMs;
        Opt<uint32_t> timeLimitSec;
    };

    struct KeyRunState   // MP
    {
        uint32_t runId = 0;
        uint32_t elapsedMs = 0;
        Opt<uint32_t> timeLimitSec;
        uint32_t deaths = 0;
        uint32_t deathPenaltySec = 0;
        uint32_t forcesCur = 0;
        uint32_t forcesMax = 0;
        uint32_t bossBits = 0;
        std::vector<uint32_t> bossKillSec;   // index i-1 = boss i
        std::vector<uint32_t> chestSec;      // optional timer ticks
        KeyRunStateId state = KeyRunStateId::Countdown;
    };

    struct KeyRunEnd     // MPE
    {
        uint32_t runId = 0;
        KeyRunResultId result = KeyRunResultId::OverTime;
        Opt<uint32_t> timeMs;
        Opt<int32_t> keyDelta;
        Opt<uint32_t> newDungeonId, newLevel, score;
        std::vector<Reward> rewards;
    };

    struct RiftState     // RIFT
    {
        Opt<uint32_t> runId;
        RiftStateId state = RiftStateId::NoRun;
        Opt<uint32_t> floor, bossId;
        std::string bossName;
        Opt<uint32_t> elapsedMs, bestFloor, score, rank, deaths, groupSize;
    };

    struct RiftEnd       // RIFTE
    {
        Opt<uint32_t> runId, floorReached, timeMs, score;
        Opt<bool> newBest;
        Opt<uint32_t> rank;
        std::vector<Reward> rewards;
    };

    struct LegacySet     // SET
    {
        uint32_t tier = 0;
        Opt<uint32_t> setId;
        uint32_t classId = 0;
        std::string name;
        Opt<uint32_t> collectedBits;         // bit i-1: look of item i collected
        Opt<bool> outfitUnlocked;
        std::vector<uint32_t> itemIds;
        std::vector<uint32_t> sourceDungeonIds;
        Opt<uint32_t> lvlMin, lvlMax;
        std::string echoBoss, note;
    };

    struct LeaderboardMember { std::string name; Opt<uint32_t> classId; };

    struct LeaderboardRow
    {
        uint32_t rank = 0;
        Opt<uint32_t> dungeonId;
        Opt<int64_t> value;                  // K: key level, R: floor, E: empty
        Opt<int64_t> timeSec;                // K: time left (negative = over time), R: run time, E: kill time
        Opt<uint32_t> dateEpoch;
        std::vector<LeaderboardMember> members;
        std::string label;                   // E: boss name
    };

    struct Leaderboard   // LB
    {
        Board board = Board::Keys;
        Opt<uint32_t> seasonId, dungeonId, classId;
        uint32_t page = 1;
        uint32_t pages = 1;
        std::vector<LeaderboardRow> rows;
    };

    struct LeaderboardMe // LBME
    {
        Board board = Board::Keys;
        Opt<uint32_t> rank, topPercent;
        Opt<int64_t> value;
        Opt<uint32_t> dungeonId;
        Opt<int64_t> timeSec;
        Opt<uint32_t> barPermille;
        std::string label;
    };

    struct ServerFirst { std::string kindKey, text, who; Opt<uint32_t> dateEpoch; };
    struct FirstsList { std::vector<ServerFirst> entries; };  // newest first

    // CASES, CASE, UNBOX (section 15)
    inline constexpr std::size_t MaxCases = 200;
    inline constexpr std::size_t MaxCaseRewards = 60;
    struct CaseList { std::vector<uint32_t> caseItemIds; };
    struct CaseReward
    {
        uint32_t itemId = 0;
        uint32_t count = 1;
        uint32_t chance = 0;                 // in 1/10000
        uint8_t tier = 0;                    // card colour, 0 poor .. 6 artifact
    };
    struct CaseInfo
    {
        uint32_t caseItemId = 0;
        std::string title, text;
        uint32_t keyItemId = 0;              // 0: no key
        uint32_t keyCount = 0;
        std::vector<CaseReward> rewards;     // display order
    };
    struct Unbox { uint32_t caseItemId = 0, rewardIndex = 0, itemId = 0, count = 1, nonce = 0; };   // rewardIndex from 1

    // ---------------------------------------------------------------------------------------------
    // Encoders: payload of each op (without frame header). `rev` is the revision of the topic.
    // ---------------------------------------------------------------------------------------------
    std::string EncodeHello(HelloReply const& m);
    std::string EncodePong(Pong const& m);
    std::string EncodeError(ErrorReply const& m);
    std::string EncodeToast(Toast const& m);
    std::string EncodeWeek(uint32_t rev, WeekState const& m);
    std::string EncodeEra(uint32_t rev, EraState const& m);
    std::string EncodeTasks(uint32_t rev, TaskList const& m);
    std::string EncodeTaskDelta(uint32_t rev, uint32_t uid, uint32_t have, TaskState state);
    std::string EncodeKey(uint32_t rev, KeyState const& m);
    std::string EncodeBoard(uint32_t rev, BoardState const& m);
    std::string EncodeQueue(uint32_t rev, QueueState const& m);
    std::string EncodeKeyRunStart(KeyRunStart const& m);
    std::string EncodeKeyRunState(KeyRunState const& m);
    std::string EncodeKeyRunEnd(KeyRunEnd const& m);
    std::string EncodeRift(RiftState const& m);
    std::string EncodeRiftEnd(RiftEnd const& m);
    std::string EncodeCollections(uint32_t rev, CollectionState const& m);
    std::string EncodeLegacySet(LegacySet const& m);
    std::string EncodeLegacyIndex(uint32_t rev, LegacyIndex const& m);
    std::string EncodeLegacyCollected(uint32_t rev, uint32_t itemId, bool collected);
    std::string EncodeSeason(uint32_t rev, SeasonState const& m);
    std::string EncodeLeaderboard(Leaderboard const& m);
    std::string EncodeLeaderboardMe(LeaderboardMe const& m);
    std::string EncodeFirsts(FirstsList const& m);
    std::string EncodeCases(CaseList const& m);
    std::string EncodeCase(CaseInfo const& m);
    std::string EncodeUnbox(Unbox const& m);

    // DEF: one payload per non-empty kind, in a fixed order, followed by "Z,<dataVer>".
    std::vector<std::string> EncodeDefinitions(Definitions const& d, uint32_t dataVer);

    // A stable 31-bit, never-zero version of a definition set (used when BleakholdUi.DataVersion = 0).
    uint32_t DefinitionsHash(Definitions const& d);
}

#endif
