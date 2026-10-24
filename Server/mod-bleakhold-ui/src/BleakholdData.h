/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Internal: the module's own data and default answers, backed by its tables
 *   world DB:      definitions (bleakhold_affix ... bleakhold_rift_boss), bleakhold_week_schedule,
 *                  bleakhold_season, bleakhold_war_effort_part, bleakhold_war_effort_rank,
 *                  bleakhold_season_reward, bleakhold_legacy_set
 *   characters DB: bleakhold_leaderboard, bleakhold_server_first, bleakhold_war_effort
 * It never makes game rules up: what counts for the war effort, how a run scores and what a reward
 * needs come from your systems (BleakholdUi.h) or from rows you write.
 */

#ifndef BLEAKHOLD_DATA_H
#define BLEAKHOLD_DATA_H

#include "BleakholdUi.h"

#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

class Player;

namespace Bleakhold
{
    class Data
    {
    public:
        static Data& Instance();

        // Startup: world and characters tables. Reload: world tables only (and the definitions).
        void LoadAll();
        void ReloadWorld();

        // Installs the module's default providers and intent handlers.
        void RegisterDefaults();
        // Once per world tick (world thread): the dancers' loop kits and the week rollover of the default ERA.
        void Update(uint64_t nowMs);

        // ---- definitions ----
        std::shared_ptr<std::vector<std::string> const> DefinitionPayloads();
        Definitions DefinitionsCopy();
        void AddDefinitionsEditor(std::function<void(Definitions&)> editor);

        // ---- sources registered by your systems ----
        void SetLegacySource(std::function<bool(Player*, uint32_t)> item, std::function<bool(Player*, uint32_t)> outfit);
        void SetSeasonRewardSource(std::function<bool(Player*, uint32_t, SeasonRewardState&)> source);
        void SetResetSource(std::function<std::pair<uint32_t, uint32_t>()> source);
        void SetSeasonOverride(uint32_t seasonId);
        uint32_t CurrentSeason();
        std::pair<uint32_t, uint32_t> ResetTimes();

        // ---- default answers (world thread) ----
        Opt<EraState> DefaultEra(Opt<bool> weeklyBonusDone);
        Opt<SeasonState> DefaultSeason(Player* player);
        LegacySet DefaultSet(Player* player, uint32_t tier, uint32_t classId);
        LegacyIndex DefaultIndex(Player* player);
        FirstsList Firsts();
        void AnswerLeaderboard(Player* player, Intent const& intent);
        void HandIn(Player* player, Intent const& intent);
        void Emoji(Player* player, Intent const& intent);
        // DANCE: starts the dance (emote state and kit) and keeps sending the kit at every loop (section 14).
        void Dance(Player* player, Intent const& intent);

        // ---- cases (bleakhold_case, section 15) ----
        bool HasCases();
        CaseList CaseIds();
        Opt<CaseInfo> CaseFor(uint32_t caseItemId);
        // CASEOPEN: takes the case (and its key), rolls a reward by weight, gives it and answers UNBOX.
        void OpenCase(Player* player, Intent const& intent);

        // ---- the module's own records (any thread) ----
        void RecordRun(Ui::LeaderboardEntry const& entry);
        bool RecordFirst(std::string_view firstId, std::string_view kindKey, std::string_view text, std::string_view who);
        void WarEffortAdd(Player* player, uint32_t partId, uint32_t points);
        uint64_t WarEffortPoints(uint32_t lowGuid);
        // A character was deleted: AzerothCore can give its guid to a new character after a restart, so the guid
        // leaves the leaderboard rows (they keep the names) and its war effort points stay only in the totals.
        void ForgetCharacter(uint32_t lowGuid);

        struct Counts { std::size_t defs = 0, schedule = 0, seasons = 0, sets = 0, lbRows = 0, firsts = 0, weRows = 0, cases = 0; };
        Counts GetCounts();

    private:
        Data() = default;

        // Players dancing a Bleakhold dance (world thread only): the dance and when its next loop starts.
        struct Dancer { uint32_t danceId = 0; uint64_t nextLoopMs = 0; };
        std::unordered_map<uint64_t, Dancer> _dancers;
        void UpdateDancers(uint64_t nowMs);

        struct WeekRow { uint32_t startsAt = 0; uint32_t eraId = 0; std::vector<uint32_t> affixIds; Opt<uint32_t> bonusId; };
        struct SeasonRow { uint32_t id = 0; std::string name, text, weTitle, weText; uint8_t state = 2; };
        struct PartRow { uint32_t season = 0, part = 0; std::string name; uint64_t goal = 0; };
        struct RankRow { uint32_t id = 0; std::string name; Opt<uint64_t> minPoints; };   // no min_points: not assigned by points
        struct RewardRow { uint32_t id = 0, season = 0; std::string name, requirement; uint64_t pointsRequired = 0; };
        struct SetRow
        {
            uint32_t setId = 0, tier = 0, classId = 0;
            std::string name, echoBoss, note;
            std::vector<uint32_t> items, sources;
            Opt<uint32_t> lvlMin, lvlMax;
        };
        struct LbRow
        {
            uint32_t id = 0;
            char board = 'K';
            uint32_t season = 0, dungeon = 0, date = 0;
            Opt<int64_t> value, timeSec;
            std::string label, teamKey;
            std::vector<LeaderboardMember> members;
            std::vector<uint32_t> memberGuids;
        };
        struct FirstRow { std::string id, kind, text, who; uint32_t date = 0; };
        struct CaseRow
        {
            uint32_t itemId = 0;
            std::string title, text;
            uint32_t keyItemId = 0, keyCount = 0;
            uint8_t announceTier = 0;        // 0: never
            std::vector<uint32_t> items, counts, weights;
            std::vector<uint8_t> tiers;
        };

        void LoadWorldLocked();
        void LoadCharactersLocked();
        void RebuildDefinitions();
        int ScheduleIndexLocked(uint32_t now) const;
        uint32_t CurrentSeasonLocked() const;
        static bool Better(LbRow const& a, LbRow const& b);

        std::mutex _lock;

        // world tables
        Definitions _tableDefs;
        std::vector<WeekRow> _schedule;
        std::vector<SeasonRow> _seasons;
        std::vector<PartRow> _parts;
        std::vector<RankRow> _ranks;
        std::vector<RewardRow> _rewards;
        std::vector<SetRow> _sets;
        std::vector<CaseRow> _cases;

        // definitions after your editors, and their encoded DEF payloads
        std::vector<std::function<void(Definitions&)>> _editors;
        Definitions _defs;
        std::shared_ptr<std::vector<std::string> const> _defPayloads;

        // characters tables
        std::vector<LbRow> _lb;
        uint32_t _nextLbId = 1;
        bool _charactersLoaded = false;
        std::vector<FirstRow> _firsts;
        std::map<uint32_t, std::map<uint32_t, uint64_t>> _weTotals;                       // season -> part -> points
        std::map<uint32_t, std::unordered_map<uint32_t, uint64_t>> _wePlayers;           // season -> guid -> points

        // sources
        std::function<bool(Player*, uint32_t)> _itemCollected, _outfitUnlocked;
        std::function<bool(Player*, uint32_t, SeasonRewardState&)> _rewardSource;
        std::function<std::pair<uint32_t, uint32_t>()> _resetSource;
        uint32_t _seasonOverride = 0;

        int _lastScheduleIndex = -2;
        uint64_t _lastRolloverCheckMs = 0;
    };
}

#endif
