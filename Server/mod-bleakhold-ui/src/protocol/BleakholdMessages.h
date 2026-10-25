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
    // H honor: Bleakhold Royale results (ROYE, section 17) only
    enum class RewardKind : char { MythicCoins = 'C', Shards = 'S', Item = 'I', Copper = 'G', Text = 'T', Honor = 'H' };
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
        FeatureCamp = 512,            // camping: campfire, camp objects, warmth, food XP, repair at a camp anvil (section 16)
        FeatureGlide = 1024,          // the High Elf glide (GLIDE, section 16)
        FeatureFieldRepair = 2048,    // blacksmiths repair anywhere (REPAIR, section 16)
        FeatureRoyale = 4096,         // Bleakhold Royale is live (section 17); set at runtime with Ui::SetFeature
        FeatureBgAnnouncer = 8192,    // the battleground kill announcer is live (BGANN, section 18); Ui::SetFeature
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
        std::string openTarget;   // tasks, dungeons, keys, rift, collections, season, leaderboards, royale or empty
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
        // kind B (Bleakhold Royale, section 17) only, appended after bandMax: players in the queue, the players a
        // match needs and takes, how many accepted the open ready check and how many it went to, matches running
        Opt<uint32_t> queued, minPlayers, maxPlayers, accepted, proposalSize, matchesRunning;
        std::vector<QueueMember> members;    // for proposals (never for Royale)
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

    // CAMPST (section 16): the player's camping state. Timers are seconds left; the client counts them down.
    enum class CampStateId : char { None = 'N', Resting = 'R', Camping = 'C' };
    inline constexpr std::size_t MaxCampObjects = 8;   // list items sent (a fire holds at most 3)
    inline constexpr std::size_t MaxCampPlaces = 16;
    struct CampObjectInfo { uint32_t skill = 0; uint8_t tier = 1; bool mine = false; };   // tier 1..3
    struct CampPlace { uint32_t skill = 0; uint8_t tier = 1; };
    struct CampState
    {
        CampStateId state = CampStateId::None;   // N not at a fire, R resting there (settling), C camping (settled)
        uint32_t settleSec = 0;                  // until settled; sent only with R
        uint32_t fireSec = 0;                    // until the fire goes out (0: none, or a fire that never does)
        bool mine = false;                       // the fire is the player's own
        uint32_t cooldownSec = 0;                // until the player may make camp again
        uint32_t warmthSec = 0;                  // Campfire Warmth left
        uint32_t xpPct = 0;                      // the XP bonus now (warmth + Well Fed)
        std::vector<CampObjectInfo> objects;     // at this fire
        std::vector<CampPlace> place;            // what the player may place here now
        Opt<uint32_t> glideSec;                  // glide cooldown; empty: the player cannot glide
        bool repair = false;                     // REPAIR is allowed right now
        bool fed = false;                        // a Well Fed buff (the food XP bonus) is active
    };

    // ---------------------------------------------------------------------------------------------
    // Bleakhold Royale (section 17): ROYS ROYM ROYO ROYK ROYV ROYE, all unrevisioned. Positions are integer world
    // yards; times (phaseMsLeft, shrinkStartMs, shrinkEndMs, msLeft) count from the moment the message arrives.
    // ---------------------------------------------------------------------------------------------
    enum class RoyalePhase : uint8_t
    {
        Arriving = 0, Countdown = 1, Drop = 2, Fight = 3, Overtime = 4, Victory = 5, Ended = 6, Cancelled = 7
    };
    enum class RoyaleMe : uint8_t { Lobby = 0, Dropping = 1, Alive = 2, Spectating = 3, Left = 4, Winner = 5 };
    enum class RoyalePoiKind : char { Landmark = 'L', Crossing = 'C', Lobby = 'Y' };
    enum class RoyaleObjectKind : char { ShadowSight = 'S', Buff = 'B', Supply = 'D' };
    enum class RoyaleBuff : uint8_t { None = 0, Speed = 1, Restoration = 2, Berserk = 3 };   // ROYO subtype of a B
    enum class RoyaleObjectState : uint8_t { Hidden = 0, Ready = 1, Taken = 2, Incoming = 3, Opened = 4 };
    // ROYK cause: killed by a player, the storm (killer filled when credited), a fall or the environment, left
    // the match, eliminated for being AFK
    enum class RoyaleCause : char { Player = 'P', Storm = 'S', Fall = 'F', Left = 'L', Afk = 'A' };
    // ROYK announce: superseded by BGANN (section 18). Kept so older callers still compile; EncodeRoyaleKill ignores it
    // and always leaves the field empty, and the addon ignores the field, so no line plays twice.
    enum class RoyaleAnnounce : char
    {
        None = 0, FirstBlood = 'F', DoubleKill = 'D', TripleKill = 'T', MonsterKill = 'M', Rampage = 'R', Godlike = 'G'
    };
    // ROYV kind: circle revealed (value = stage), storm moving (stage), supply incoming, landed, opened, players
    // left (value 10, 5 or 2), winner (value = kills, name)
    enum class RoyaleEventKind : char
    {
        Revealed = 'R', StormMoving = 'S', SupplyIncoming = 'D', SupplyLanded = 'L', SupplyOpened = 'O',
        PlayersLeft = 'N', Winner = 'W'
    };
    inline constexpr std::size_t MaxRoyalePois = 64;      // ROYM records after the header
    inline constexpr std::size_t MaxRoyaleObjects = 64;   // ROYO records after the header
    inline constexpr std::size_t RoyaleNameBytes = 48;    // character names (two-word names fit)

    struct RoyaleState   // ROYS: the match as this player sees it
    {
        uint32_t matchId = 0;
        RoyalePhase phase = RoyalePhase::Arriving;
        uint32_t phaseMsLeft = 0;            // until the next phase (0: none planned)
        uint32_t alive = 0;
        uint32_t total = 0;                  // players who dropped (or are in the lobby before the drop)
        RoyaleMe me = RoyaleMe::Lobby;
        uint32_t kills = 0;
        Opt<uint32_t> placement;             // once eliminated or the winner
        Opt<int32_t> pinX, pinY;             // the snapped landing pin (empty: none set)
        uint32_t stage = 0;                  // storm stage, 0 before stage 1
        int32_t curX = 0, curY = 0;          // the storm circle now
        uint32_t curR = 0;
        Opt<int32_t> nextX, nextY;           // the next circle, once revealed
        Opt<uint32_t> nextR;
        // shrinkStartMs 0 and shrinkEndMs > 0: cur moves linearly to next over shrinkEndMs; both empty: no shrink
        Opt<uint32_t> shrinkStartMs, shrinkEndMs;
        uint32_t dmgPermille = 0;            // storm damage outside the circle now, permille of max health per second
        std::string watchName;               // spectators: the player they watch
        Opt<int32_t> myX, myY;               // the player's position (the client's map fallback)
        Opt<uint32_t> stages;                // the storm's stage count (1..16); stage stages + 1 is overtime
    };
    // RoyaleState::stages (ROYS field 24) exists: a server module may fill it.
#define BLEAKHOLD_UI_ROYALE_STAGES 1

    struct RoyalePoi
    {
        uint32_t id = 0;
        RoyalePoiKind kind = RoyalePoiKind::Landmark;
        int32_t x = 0, y = 0;
        uint32_t r = 0;
        std::string name;
    };
    struct RoyaleMap     // ROYM: the island map (crate spots and final sites are never sent)
    {
        uint32_t mapId = 0;
        int32_t minX = 0, maxX = 0, minY = 0, maxY = 0;   // the map texture's frame
        int32_t lobbyX = 0, lobbyY = 0;
        uint32_t lobbyR = 0;
        uint32_t boundHalf = 0;                            // half size of the playable square around the centre
        int32_t centerX = 0, centerY = 0;
        std::vector<RoyalePoi> pois;
    };

    struct RoyaleObject
    {
        uint32_t objId = 0;
        RoyaleObjectKind kind = RoyaleObjectKind::ShadowSight;
        uint32_t subtype = 0;                // RoyaleBuff for kind B, else 0
        int32_t x = 0, y = 0;
        RoyaleObjectState state = RoyaleObjectState::Hidden;
        Opt<uint32_t> msLeft;                // Taken: respawn in; Incoming: lands in; Hidden: appears in
    };
    struct RoyaleObjects // ROYO: orbs and supply drops
    {
        uint32_t matchId = 0;
        bool full = false;                   // true: replaces every object the client knows
        std::vector<RoyaleObject> objects;
    };

    struct RoyaleKill    // ROYK: one line of the kill feed
    {
        std::string killerName;              // empty: nobody (the storm, a fall, ...)
        Opt<uint32_t> killerClassId;
        std::string victimName;
        uint32_t victimClassId = 0;
        RoyaleCause cause = RoyaleCause::Player;
        uint32_t aliveAfter = 0;
        Opt<uint32_t> killerKills;           // the killer's eliminations in this match, this one included
        // Superseded by BGANN (section 18): ignored, the field is always sent empty.
        RoyaleAnnounce announce = RoyaleAnnounce::None;
    };

    struct RoyaleEvent   // ROYV
    {
        RoyaleEventKind kind = RoyaleEventKind::Revealed;
        uint32_t value = 0;
        Opt<int32_t> x, y;
        Opt<uint32_t> msLeft;
        std::string name;
    };

    struct RoyaleResult  // ROYE: the player's own result
    {
        uint32_t matchId = 0;
        uint32_t placement = 0;
        uint32_t total = 0;
        uint32_t kills = 0;
        uint32_t damage = 0;
        uint32_t healing = 0;
        uint32_t survivedSec = 0;
        std::string winnerName;              // empty while the match goes on
        Opt<uint32_t> winnerClassId, winnerKills;
        bool rewarded = false;               // the player passed the reward rules
        std::vector<Reward> rewards;         // kinds as for MPE, plus H honor
    };

    // ---------------------------------------------------------------------------------------------
    // The battleground kill announcer (section 18): BGANN, unrevisioned, to every player of a battleground (Warsong
    // Gulch to Isle of Conquest and Bleakhold Royale; never an arena or the open world). The server keeps the streaks
    // and multi-kills; one kill may carry a multi-kill code and a streak (or first blood) code, and the client plays
    // the multi-kill first. BLEAKHOLD_UI_BG_ANNOUNCE tells a server module that this API exists.
    // ---------------------------------------------------------------------------------------------
#define BLEAKHOLD_UI_BG_ANNOUNCE 1
    // multi: kills by the same player with at most the server's window (18 s) between consecutive kills
    enum class BgMultiKill : char { None = 0, Double = 'D', Triple = 'T', Ultra = 'U', Rampage = 'R' };
    // streak: F the battleground's first credited kill, else the killer's kills since they last died (in Bleakhold
    // Royale, one life: all of them) S 3, O 4, K 5, N 6, W 7, M 8, G 9, H 10 and every further kill
    enum class BgStreak : char
    {
        None = 0, FirstBlood = 'F', KillingSpree = 'S', Dominating = 'O', MegaKill = 'K', Unstoppable = 'N',
        WickedSick = 'W', MonsterKill = 'M', Godlike = 'G', HolyShit = 'H'
    };
    inline constexpr std::size_t BgNameBytes = 48;        // character names (two-word names fit)

    struct BgAnnounce    // BGANN: one announced kill
    {
        std::string killerName;
        uint32_t killerClassId = 0;
        std::string victimName;
        uint32_t victimClassId = 0;
        BgMultiKill multi = BgMultiKill::None;
        BgStreak streak = BgStreak::None;
    };
    // The codes as written: one of the letters above, else 0 (an empty field).
    char BgMultiLetter(BgMultiKill multi);
    char BgStreakLetter(BgStreak streak);
    // Worth sending: both names clean to something and at least one valid code. Ui::SendBgAnnounce sends nothing
    // otherwise.
    bool BgAnnounceSendable(BgAnnounce const& m);

    // ERR codes of Bleakhold Royale (section 17) with a default sentence; Ui::Refuse(player, intent, refusal) sends
    // one. `dead` and `in_combat` are the generic codes. royale_lockout should carry the seconds left: send it with
    // Ui::Refuse(player, intent, RoyaleErr::Lockout.code, "<your sentence with the seconds>").
    struct Refusal { char const* code; char const* text; };
    namespace RoyaleErr
    {
        inline constexpr Refusal Off{ "royale_off", "Bleakhold Royale is not open right now." };
        inline constexpr Refusal Level{ "royale_level", "You must be level 80 to join Bleakhold Royale." };
        inline constexpr Refusal Grouped{ "royale_grouped", "Bleakhold Royale is solo: leave your group first." };
        inline constexpr Refusal Busy{ "royale_busy", "You cannot join Bleakhold Royale from where you are now." };
        inline constexpr Refusal Deserter{ "royale_deserter", "You cannot join while you are a deserter." };
        inline constexpr Refusal Bags{ "royale_bags", "Make room in your bags first." };
        inline constexpr Refusal Ip{ "royale_ip", "Too many players from your connection are in Bleakhold Royale." };
        inline constexpr Refusal Lockout{ "royale_lockout", "You declined a match: you can queue again soon." };
        inline constexpr Refusal NoProposal{ "no_proposal", "There is no match waiting for your answer." };
        inline constexpr Refusal Phase{ "royale_phase", "You cannot do that now." };
        inline constexpr Refusal Nobody{ "royale_nobody", "There is nobody left to watch." };
        inline constexpr Refusal GlideHere{ "glide_here", "You cannot glide here." };
    }

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
    std::string EncodeCampState(CampState const& m);
    std::string EncodeRoyaleState(RoyaleState const& m);     // ROYS
    std::string EncodeRoyaleMap(RoyaleMap const& m);         // ROYM
    std::string EncodeRoyaleObjects(RoyaleObjects const& m); // ROYO
    std::string EncodeRoyaleKill(RoyaleKill const& m);       // ROYK
    std::string EncodeRoyaleEvent(RoyaleEvent const& m);     // ROYV
    std::string EncodeRoyaleResult(RoyaleResult const& m);   // ROYE
    std::string EncodeBgAnnounce(BgAnnounce const& m);       // BGANN

    // DEF: one payload per non-empty kind, in a fixed order, followed by "Z,<dataVer>".
    std::vector<std::string> EncodeDefinitions(Definitions const& d, uint32_t dataVer);

    // A stable 31-bit, never-zero version of a definition set (used when BleakholdUi.DataVersion = 0).
    uint32_t DefinitionsHash(Definitions const& d);
}

#endif
