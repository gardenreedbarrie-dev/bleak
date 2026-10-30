/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Lock order: the Mgr lock may be held while taking this lock; this file never calls into the Mgr
 * (or your callbacks) while holding its own lock.
 */

#include "BleakholdData.h"
#include "BleakholdCafe.h"
#include "BleakholdCafeRules.h"
#include "BleakholdCamp.h"
#include "BleakholdCases.h"
#include "BleakholdCodec.h"
#include "BleakholdDance.h"
#include "BleakholdEmoji.h"
#include "BleakholdMgr.h"

#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Log.h"
#include "Item.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Random.h"
#include "World.h"

#include <algorithm>
#include <cctype>
#include <set>

namespace Bleakhold
{
    namespace
    {
        // "1, 3 4:5" -> {1, 3, 4, 5}: any non-digit separates.
        std::vector<uint32_t> IntList(std::string const& s)
        {
            std::vector<uint32_t> out;
            uint64_t v = 0;
            bool in = false;
            for (char c : s)
            {
                if (c >= '0' && c <= '9')
                {
                    v = v * 10 + static_cast<uint64_t>(c - '0');
                    if (v > 0xFFFFFFFFull)
                        v = 0xFFFFFFFFull;
                    in = true;
                }
                else if (in)
                {
                    out.push_back(static_cast<uint32_t>(v));
                    v = 0;
                    in = false;
                }
            }
            if (in)
                out.push_back(static_cast<uint32_t>(v));
            return out;
        }

        // "General Bjarngrim; Volkhan;Ionar" -> trimmed names
        std::vector<std::string> NameList(std::string const& s)
        {
            std::vector<std::string> out;
            std::size_t start = 0;
            while (start <= s.size())
            {
                std::size_t end = s.find(';', start);
                if (end == std::string::npos)
                    end = s.size();
                std::string item = s.substr(start, end - start);
                std::size_t a = 0;
                std::size_t b = item.size();
                while (a < b && std::isspace(static_cast<unsigned char>(item[a])))
                    ++a;
                while (b > a && std::isspace(static_cast<unsigned char>(item[b - 1])))
                    --b;
                if (b > a)
                    out.push_back(item.substr(a, b - a));
                start = end + 1;
            }
            return out;
        }

        template <typename T>
        Opt<T> OptField(Field const& f)
        {
            if (f.IsNull())
                return std::nullopt;
            return f.Get<T>();
        }

        Opt<uint32_t> OptU8(Field const& f)
        {
            if (f.IsNull())
                return std::nullopt;
            return static_cast<uint32_t>(f.Get<uint8>());
        }

        std::string SqlInt(Opt<int64_t> const& v)
        {
            return v ? std::to_string(*v) : std::string("NULL");
        }

        std::string Esc(std::string s)
        {
            CharacterDatabase.EscapeString(s);
            return s;
        }

        // server text for a stored record: valid UTF-8, one line
        std::string CleanLabel(std::string_view s, std::size_t maxBytes = 255)
        {
            std::string out = Proto::CleanText(s, maxBytes);
            for (char& c : out)
                if (static_cast<unsigned char>(c) < 0x20)
                    c = ' ';
            return out;
        }

        uint32_t NowEpoch()
        {
            return static_cast<uint32_t>(GameTime::GetGameTime().count());
        }
    }

    Data& Data::Instance()
    {
        static Data instance;
        return instance;
    }

    // =============================================================================================
    // Loading
    // =============================================================================================
    void Data::LoadAll()
    {
        {
            std::lock_guard<std::mutex> guard(_lock);
            LoadWorldLocked();
            LoadCharactersLocked();
        }
        RebuildDefinitions();
    }

    void Data::ReloadWorld()
    {
        {
            std::lock_guard<std::mutex> guard(_lock);
            LoadWorldLocked();
        }
        RebuildDefinitions();
    }

    void Data::LoadWorldLocked()
    {
        Definitions d;
        if (QueryResult r = WorldDatabase.Query("SELECT `id`, `name`, `description` FROM `bleakhold_affix` ORDER BY `id`"))
            do
            {
                Field* f = r->Fetch();
                d.affixes.push_back({ f[0].Get<uint32>(), f[1].Get<std::string>(), f[2].Get<std::string>() });
            } while (r->NextRow());
        if (QueryResult r = WorldDatabase.Query("SELECT `id`, `name`, `description`, `legacy_tier` FROM `bleakhold_era` ORDER BY `id`"))
            do
            {
                Field* f = r->Fetch();
                d.eras.push_back({ f[0].Get<uint32>(), f[1].Get<std::string>(), f[2].Get<std::string>(), OptField<uint32>(f[3]) });
            } while (r->NextRow());
        if (QueryResult r = WorldDatabase.Query("SELECT `id`, `title`, `description` FROM `bleakhold_task_template` ORDER BY `id`"))
            do
            {
                Field* f = r->Fetch();
                d.taskTemplates.push_back({ f[0].Get<uint32>(), f[1].Get<std::string>(), f[2].Get<std::string>() });
            } while (r->NextRow());
        if (QueryResult r = WorldDatabase.Query("SELECT `id`, `title`, `description` FROM `bleakhold_weekly_bonus` ORDER BY `id`"))
            do
            {
                Field* f = r->Fetch();
                d.weeklyBonuses.push_back({ f[0].Get<uint32>(), f[1].Get<std::string>(), f[2].Get<std::string>() });
            } while (r->NextRow());
        if (QueryResult r = WorldDatabase.Query("SELECT `id`, `name`, `description` FROM `bleakhold_chapter` ORDER BY `id`"))
            do
            {
                Field* f = r->Fetch();
                d.chapters.push_back({ f[0].Get<uint32>(), f[1].Get<std::string>(), f[2].Get<std::string>() });
            } while (r->NextRow());
        if (QueryResult r = WorldDatabase.Query("SELECT `map_id`, `name`, `chapter`, `level_min`, `level_max`, `bosses`, `time_limit_sec` "
                "FROM `bleakhold_dungeon` ORDER BY `chapter`, `level_min`, `map_id`"))
            do
            {
                Field* f = r->Fetch();
                DungeonDef e;
                e.id = f[0].Get<uint32>();
                e.name = f[1].Get<std::string>();
                e.chapter = OptField<uint32>(f[2]);
                e.lvlMin = OptU8(f[3]);
                e.lvlMax = OptU8(f[4]);
                e.bosses = NameList(f[5].Get<std::string>());
                e.timeLimitSec = OptField<uint32>(f[6]);
                d.dungeons.push_back(std::move(e));
            } while (r->NextRow());
        if (QueryResult r = WorldDatabase.Query("SELECT `id`, `label`, `raids`, `era_id`, `source_dungeons`, `level_min`, `level_max`, "
                "`echo_boss`, `piece_total` FROM `bleakhold_legacy_tier` ORDER BY `id`"))
            do
            {
                Field* f = r->Fetch();
                LegacyTierDef e;
                e.id = f[0].Get<uint32>();
                e.label = f[1].Get<std::string>();
                e.raids = f[2].Get<std::string>();
                e.eraId = OptField<uint32>(f[3]);
                e.sources = IntList(f[4].Get<std::string>());
                e.lvlMin = OptU8(f[5]);
                e.lvlMax = OptU8(f[6]);
                e.echoBoss = f[7].Get<std::string>();
                e.pieceTotal = OptU8(f[8]);
                d.legacyTiers.push_back(std::move(e));
            } while (r->NextRow());

        _seasons.clear();
        if (QueryResult r = WorldDatabase.Query("SELECT `id`, `name`, `description`, `state`, `war_effort_title`, `war_effort_text` "
                "FROM `bleakhold_season` ORDER BY `id`"))
            do
            {
                Field* f = r->Fetch();
                SeasonRow s;
                s.id = f[0].Get<uint32>();
                s.name = f[1].Get<std::string>();
                s.text = f[2].Get<std::string>();
                s.state = std::min<uint8>(f[3].Get<uint8>(), 2);
                s.weTitle = f[4].Get<std::string>();
                s.weText = f[5].Get<std::string>();
                _seasons.push_back(s);
                d.seasons.push_back({ s.id, s.name, s.text, static_cast<SeasonStateId>(s.state) });
            } while (r->NextRow());

        _ranks.clear();
        if (QueryResult r = WorldDatabase.Query("SELECT `id`, `name`, `min_points` FROM `bleakhold_war_effort_rank` ORDER BY `min_points`, `id`"))
            do
            {
                Field* f = r->Fetch();
                RankRow k{ f[0].Get<uint32>(), f[1].Get<std::string>(), OptField<uint64>(f[2]) };
                _ranks.push_back(k);
                d.ranks.push_back({ k.id, k.name });
            } while (r->NextRow());
        std::sort(d.ranks.begin(), d.ranks.end(), [](RankDef const& a, RankDef const& b) { return a.id < b.id; });

        _rewards.clear();
        if (QueryResult r = WorldDatabase.Query("SELECT `id`, `season_id`, `name`, `requirement_text`, `points_required` "
                "FROM `bleakhold_season_reward` ORDER BY `season_id`, `id`"))
            do
            {
                Field* f = r->Fetch();
                RewardRow w{ f[0].Get<uint32>(), f[1].Get<uint32>(), f[2].Get<std::string>(), f[3].Get<std::string>(), f[4].Get<uint64>() };
                _rewards.push_back(w);
                d.seasonRewards.push_back({ w.id, w.name, w.requirement });
            } while (r->NextRow());

        if (QueryResult r = WorldDatabase.Query("SELECT `level`, `description` FROM `bleakhold_mythic_level` ORDER BY `level`"))
            do
            {
                Field* f = r->Fetch();
                d.mythicLevels.push_back({ static_cast<uint32_t>(f[0].Get<uint8>()), f[1].Get<std::string>() });
            } while (r->NextRow());
        if (QueryResult r = WorldDatabase.Query("SELECT `id`, `name`, `token`, `color_hex`, `short_label` FROM `bleakhold_extra_class` ORDER BY `id`"))
            do
            {
                Field* f = r->Fetch();
                d.extraClasses.push_back({ static_cast<uint32_t>(f[0].Get<uint8>()), f[1].Get<std::string>(), f[2].Get<std::string>(),
                    f[3].Get<std::string>(), f[4].Get<std::string>() });
            } while (r->NextRow());
        if (QueryResult r = WorldDatabase.Query("SELECT `id`, `name` FROM `bleakhold_rift_boss` ORDER BY `id`"))
            do
            {
                Field* f = r->Fetch();
                d.riftBosses.push_back({ f[0].Get<uint32>(), f[1].Get<std::string>() });
            } while (r->NextRow());

        _schedule.clear();
        if (QueryResult r = WorldDatabase.Query("SELECT CAST(UNIX_TIMESTAMP(`starts_at`) AS UNSIGNED), `era_id`, `affix_ids`, `weekly_bonus_id` "
                "FROM `bleakhold_week_schedule` ORDER BY `starts_at`"))
            do
            {
                Field* f = r->Fetch();
                WeekRow w;
                w.startsAt = static_cast<uint32_t>(f[0].Get<uint64>());
                w.eraId = f[1].Get<uint32>();
                w.affixIds = IntList(f[2].Get<std::string>());
                w.bonusId = OptField<uint32>(f[3]);
                _schedule.push_back(std::move(w));
            } while (r->NextRow());

        _parts.clear();
        if (QueryResult r = WorldDatabase.Query("SELECT `season_id`, `part_id`, `name`, `goal_points` FROM `bleakhold_war_effort_part` "
                "ORDER BY `season_id`, `part_id`"))
            do
            {
                Field* f = r->Fetch();
                _parts.push_back({ f[0].Get<uint32>(), f[1].Get<uint32>(), f[2].Get<std::string>(), f[3].Get<uint64>() });
            } while (r->NextRow());

        _sets.clear();
        if (QueryResult r = WorldDatabase.Query("SELECT `set_id`, `tier`, `class_id`, `name`, `item_ids`, `source_dungeons`, `level_min`, "
                "`level_max`, `echo_boss`, `note` FROM `bleakhold_legacy_set` ORDER BY `tier`, `class_id`, `set_id`"))
            do
            {
                Field* f = r->Fetch();
                SetRow s;
                s.setId = f[0].Get<uint32>();
                s.tier = f[1].Get<uint8>();
                s.classId = f[2].Get<uint8>();
                s.name = f[3].Get<std::string>();
                s.items = IntList(f[4].Get<std::string>());
                s.sources = IntList(f[5].Get<std::string>());
                s.lvlMin = OptU8(f[6]);
                s.lvlMax = OptU8(f[7]);
                s.echoBoss = f[8].Get<std::string>();
                s.note = f[9].Get<std::string>();
                _sets.push_back(std::move(s));
            } while (r->NextRow());

        _tableDefs = std::move(d);
        _lastScheduleIndex = -2;
        LOG_INFO("server.loading", ">> Bleakhold: {} affixes, {} eras, {} task templates, {} dungeons, {} legacy tiers, {} seasons, "
            "{} schedule weeks, {} legacy sets", _tableDefs.affixes.size(), _tableDefs.eras.size(), _tableDefs.taskTemplates.size(),
            _tableDefs.dungeons.size(), _tableDefs.legacyTiers.size(), _seasons.size(), _schedule.size(), _sets.size());

        // cases (section 15): enabled cases with at least one reward whose item exists
        std::vector<CaseRow> cases;
        if (QueryResult r = WorldDatabase.Query("SELECT `item_id`, `title`, `description`, `key_item_id`, `key_count`, `announce_tier` "
                "FROM `bleakhold_case` WHERE `enabled` <> 0 ORDER BY `item_id`"))
            do
            {
                Field* f = r->Fetch();
                CaseRow c;
                c.itemId = f[0].Get<uint32>();
                c.title = f[1].Get<std::string>();
                c.text = f[2].Get<std::string>();
                c.keyItemId = f[3].Get<uint32>();
                c.keyCount = std::max<uint32>(1, f[4].Get<uint8>());
                c.announceTier = f[5].Get<uint8>();
                ItemTemplate const* proto = sObjectMgr->GetItemTemplate(c.itemId);
                if (!proto)
                {
                    LOG_ERROR("module", "[Bleakhold] bleakhold_case: item {} does not exist; case skipped", c.itemId);
                    continue;
                }
                // a bag or anything worn could be taken from an equipment slot (and a bag with what is in it)
                auto wearable = [](ItemTemplate const* t) {
                    return t->InventoryType != INVTYPE_NON_EQUIP || t->Class == ITEM_CLASS_CONTAINER || t->Class == ITEM_CLASS_QUIVER;
                };
                if (wearable(proto))
                {
                    LOG_ERROR("module", "[Bleakhold] bleakhold_case: item {} can be equipped or is a bag; case skipped", c.itemId);
                    continue;
                }
                if (c.title.empty())
                    c.title = proto->Name1;
                if (c.keyItemId)
                {
                    ItemTemplate const* key = sObjectMgr->GetItemTemplate(c.keyItemId);
                    if (!key || wearable(key) || c.keyItemId == c.itemId)
                    {
                        LOG_ERROR("module", "[Bleakhold] bleakhold_case {}: key item {} does not exist, can be equipped, is a bag or is "
                            "the case itself; case skipped", c.itemId, c.keyItemId);
                        continue;
                    }
                }
                if (cases.size() >= MaxCases)
                {
                    LOG_ERROR("module", "[Bleakhold] bleakhold_case: more than {} cases; case {} skipped", MaxCases, c.itemId);
                    continue;
                }
                cases.push_back(std::move(c));
            } while (r->NextRow());
        if (QueryResult r = WorldDatabase.Query("SELECT `case_item_id`, `item_id`, `count`, `weight`, `tier` FROM `bleakhold_case_reward` "
                "ORDER BY `case_item_id`, `sort`, `item_id`"))
            do
            {
                Field* f = r->Fetch();
                uint32 const caseId = f[0].Get<uint32>(), itemId = f[1].Get<uint32>(), weight = f[3].Get<uint32>();
                auto it = std::find_if(cases.begin(), cases.end(), [&](CaseRow const& c) { return c.itemId == caseId; });
                if (it == cases.end() || weight == 0)
                    continue;
                if (it->items.size() >= MaxCaseRewards)
                {
                    LOG_ERROR("module", "[Bleakhold] bleakhold_case {}: more than {} rewards; item {} skipped", caseId, MaxCaseRewards, itemId);
                    continue;
                }
                ItemTemplate const* proto = sObjectMgr->GetItemTemplate(itemId);
                if (!proto)
                {
                    LOG_ERROR("module", "[Bleakhold] bleakhold_case_reward: item {} (case {}) does not exist; reward skipped", itemId, caseId);
                    continue;
                }
                int32 const tier = f[4].Get<int8>();
                it->items.push_back(itemId);
                // at most a stack, and at most what a player may carry
                uint32 maxCount = std::max<uint32>(1, proto->GetMaxStackSize());
                if (proto->MaxCount > 0)
                    maxCount = std::min<uint32>(maxCount, uint32(proto->MaxCount));
                it->counts.push_back(std::clamp<uint32>(f[2].Get<uint16>(), 1, maxCount));
                it->weights.push_back(weight);
                it->tiers.push_back(uint8_t(tier < 0 ? std::min<uint32>(proto->Quality, 6) : std::min<int32>(tier, 6)));
            } while (r->NextRow());
        cases.erase(std::remove_if(cases.begin(), cases.end(), [](CaseRow const& c) {
            if (c.items.empty())
            {
                LOG_ERROR("module", "[Bleakhold] bleakhold_case {} has no reward; case skipped", c.itemId);
                return true;
            }
            // the roll draws a 32-bit number
            if (Cases::TotalWeight(c.weights) > 0xFFFFFFFFull)
            {
                LOG_ERROR("module", "[Bleakhold] bleakhold_case {}: the weights add up to more than 4294967295; case skipped", c.itemId);
                return true;
            }
            return false;
        }), cases.end());
        _cases = std::move(cases);
    }

    void Data::LoadCharactersLocked()
    {
        _lb.clear();
        _nextLbId = 1;
        if (QueryResult r = CharacterDatabase.Query("SELECT `id`, `board`, `season_id`, `dungeon_id`, `value`, `time_sec`, `date`, `label`, "
                "`team_key`, `members`, `member_guids` FROM `bleakhold_leaderboard`"))
            do
            {
                Field* f = r->Fetch();
                LbRow row;
                row.id = f[0].Get<uint32>();
                std::string const board = f[1].Get<std::string>();
                row.board = board.empty() ? 'K' : board[0];
                row.season = f[2].Get<uint32>();
                row.dungeon = f[3].Get<uint32>();
                row.value = OptField<int64>(f[4]);
                row.timeSec = OptField<int64>(f[5]);
                row.date = f[6].Get<uint32>();
                row.label = f[7].Get<std::string>();
                row.teamKey = f[8].Get<std::string>();
                // members: "Name~classId:Name~classId"
                std::string const members = f[9].Get<std::string>();
                std::size_t start = 0;
                while (start < members.size())
                {
                    std::size_t end = members.find(':', start);
                    if (end == std::string::npos)
                        end = members.size();
                    std::string const item = members.substr(start, end - start);
                    std::size_t const tilde = item.find('~');
                    LeaderboardMember m;
                    m.name = item.substr(0, tilde);
                    if (tilde != std::string::npos)
                    {
                        std::vector<uint32_t> cls = IntList(item.substr(tilde + 1));
                        if (!cls.empty())
                            m.classId = cls[0];
                    }
                    if (!m.name.empty())
                        row.members.push_back(std::move(m));
                    start = end + 1;
                }
                row.memberGuids = IntList(f[10].Get<std::string>());
                _nextLbId = std::max(_nextLbId, row.id + 1);
                _lb.push_back(std::move(row));
            } while (r->NextRow());

        _firsts.clear();
        if (QueryResult r = CharacterDatabase.Query("SELECT `first_id`, `kind_key`, `text`, `who`, `date` FROM `bleakhold_server_first` "
                "ORDER BY `date` DESC"))
            do
            {
                Field* f = r->Fetch();
                _firsts.push_back({ f[0].Get<std::string>(), f[1].Get<std::string>(), f[2].Get<std::string>(), f[3].Get<std::string>(),
                    f[4].Get<uint32>() });
            } while (r->NextRow());

        _weTotals.clear();
        _wePlayers.clear();
        std::size_t weRows = 0;
        if (QueryResult r = CharacterDatabase.Query("SELECT `season_id`, `guid`, `part_id`, `points` FROM `bleakhold_war_effort`"))
            do
            {
                Field* f = r->Fetch();
                uint32_t const season = f[0].Get<uint32>();
                uint32_t const guid = f[1].Get<uint32>();
                uint32_t const part = f[2].Get<uint32>();
                uint64_t const points = f[3].Get<uint64>();
                _weTotals[season][part] += points;
                if (guid)   // guid 0: points of deleted characters (ForgetCharacter), in the totals only
                    _wePlayers[season][guid] += points;
                ++weRows;
            } while (r->NextRow());

        _charactersLoaded = true;
        LOG_INFO("server.loading", ">> Bleakhold: {} leaderboard rows, {} server firsts, {} war effort rows", _lb.size(), _firsts.size(), weRows);
    }

    void Data::RebuildDefinitions()
    {
        // Your editors run without the lock (they are your code); the result is stored afterwards.
        Definitions d;
        std::vector<std::function<void(Definitions&)>> editors;
        {
            std::lock_guard<std::mutex> guard(_lock);
            d = _tableDefs;
            editors = _editors;
        }
        // the cafe's DEF H G F U (section 21) only with BleakholdUi.Cafe.Enable = 1: the version stays the same while off
        if (Cafe::Instance().DefinitionsOn())
            CafeRules::FillDefinitions(d);
        for (auto const& e : editors)
            e(d);
        Config const cfg = Mgr::Instance().CfgCopy();
        uint32_t const ver = cfg.dataVersion ? cfg.dataVersion : DefinitionsHash(d);
        auto payloads = std::make_shared<std::vector<std::string> const>(EncodeDefinitions(d, ver));
        {
            std::lock_guard<std::mutex> guard(_lock);
            _defs = std::move(d);
            _defPayloads = std::move(payloads);
        }
        Mgr::Instance().SetDataVersion(ver);
    }

    std::shared_ptr<std::vector<std::string> const> Data::DefinitionPayloads()
    {
        std::lock_guard<std::mutex> guard(_lock);
        return _defPayloads;
    }

    Definitions Data::DefinitionsCopy()
    {
        std::lock_guard<std::mutex> guard(_lock);
        return _defs;
    }

    void Data::AddDefinitionsEditor(std::function<void(Definitions&)> editor)
    {
        {
            std::lock_guard<std::mutex> guard(_lock);
            _editors.push_back(std::move(editor));
        }
        // editors registered after startup apply at once
        if (DefinitionPayloads())
            RebuildDefinitions();
    }

    Data::Counts Data::GetCounts()
    {
        std::lock_guard<std::mutex> guard(_lock);
        Counts c;
        c.defs = _defs.affixes.size() + _defs.eras.size() + _defs.taskTemplates.size() + _defs.weeklyBonuses.size() + _defs.chapters.size() +
            _defs.dungeons.size() + _defs.legacyTiers.size() + _defs.seasons.size() + _defs.ranks.size() + _defs.seasonRewards.size() +
            _defs.mythicLevels.size() + _defs.extraClasses.size() + _defs.riftBosses.size();
        c.schedule = _schedule.size();
        c.seasons = _seasons.size();
        c.sets = _sets.size();
        c.cases = _cases.size();
        c.lbRows = _lb.size();
        c.firsts = _firsts.size();
        for (auto const& [season, players] : _wePlayers)
            c.weRows += players.size();
        return c;
    }

    // =============================================================================================
    // Sources
    // =============================================================================================
    void Data::SetLegacySource(std::function<bool(Player*, uint32_t)> item, std::function<bool(Player*, uint32_t)> outfit)
    {
        std::lock_guard<std::mutex> guard(_lock);
        _itemCollected = std::move(item);
        _outfitUnlocked = std::move(outfit);
    }

    void Data::SetSeasonRewardSource(std::function<bool(Player*, uint32_t, SeasonRewardState&)> source)
    {
        std::lock_guard<std::mutex> guard(_lock);
        _rewardSource = std::move(source);
    }

    void Data::SetResetSource(std::function<std::pair<uint32_t, uint32_t>()> source)
    {
        std::lock_guard<std::mutex> guard(_lock);
        _resetSource = std::move(source);
    }

    void Data::SetSeasonOverride(uint32_t seasonId)
    {
        std::lock_guard<std::mutex> guard(_lock);
        _seasonOverride = seasonId;
    }

    uint32_t Data::CurrentSeasonLocked() const
    {
        if (_seasonOverride)
            return _seasonOverride;
        // the newest current season (highest id): a starting row that a module update put back as current
        // (01_bleakhold_world_seed.sql) does not replace the season you made current
        for (auto it = _seasons.rbegin(); it != _seasons.rend(); ++it)
            if (it->state == static_cast<uint8_t>(SeasonStateId::Current))
                return it->id;
        return 0;
    }

    uint32_t Data::CurrentSeason()
    {
        uint32_t const configured = Mgr::Instance().CfgCopy().seasonId;
        std::lock_guard<std::mutex> guard(_lock);
        if (!_seasonOverride && configured)
            return configured;
        return CurrentSeasonLocked();
    }

    std::pair<uint32_t, uint32_t> Data::ResetTimes()
    {
        std::function<std::pair<uint32_t, uint32_t>()> source;
        {
            std::lock_guard<std::mutex> guard(_lock);
            source = _resetSource;
        }
        if (source)
            return source();
        return { static_cast<uint32_t>(sWorld->GetNextDailyQuestsResetTime().count()),
            static_cast<uint32_t>(sWorld->GetNextWeeklyQuestsResetTime().count()) };
    }

    // =============================================================================================
    // Default answers
    // =============================================================================================
    int Data::ScheduleIndexLocked(uint32_t now) const
    {
        int idx = -1;
        for (std::size_t i = 0; i < _schedule.size(); ++i)
            if (_schedule[i].startsAt <= now)
                idx = static_cast<int>(i);
        return idx;
    }

    Opt<EraState> Data::DefaultEra(Opt<bool> weeklyBonusDone)
    {
        std::lock_guard<std::mutex> guard(_lock);
        int const idx = ScheduleIndexLocked(NowEpoch());
        if (idx < 0)
            return std::nullopt;
        WeekRow const& w = _schedule[static_cast<std::size_t>(idx)];
        EraState e;
        e.eraId = w.eraId;
        if (static_cast<std::size_t>(idx) + 1 < _schedule.size())
            e.nextEraId = _schedule[static_cast<std::size_t>(idx) + 1].eraId;
        e.affixIds = w.affixIds;
        e.weeklyBonusId = w.bonusId;
        e.weeklyBonusDone = weeklyBonusDone;
        return e;
    }

    void Data::Update(uint64_t nowMs)
    {
        UpdateDancers(nowMs);
        if (nowMs - _lastRolloverCheckMs < 60000)
            return;
        _lastRolloverCheckMs = nowMs;
        int idx;
        bool changed;
        {
            std::lock_guard<std::mutex> guard(_lock);
            idx = ScheduleIndexLocked(NowEpoch());
            changed = _lastScheduleIndex != -2 && idx != _lastScheduleIndex;
            _lastScheduleIndex = idx;
        }
        if (changed)
        {
            LOG_INFO("module", "[Bleakhold] a new week of bleakhold_week_schedule started; sending ERA to every player");
            Mgr::Instance().ForEachReadyPlayer([](Player* p) { Mgr::Instance().Refresh(p, Topic::Era); });
        }
    }

    Opt<SeasonState> Data::DefaultSeason(Player* player)
    {
        Config const cfg = Mgr::Instance().CfgCopy();
        uint32_t const season = CurrentSeason();
        if (!season || !player)
            return std::nullopt;
        SeasonState s;
        std::vector<uint32_t> rewardIds;
        std::vector<uint64_t> rewardNeeds;
        std::function<bool(Player*, uint32_t, SeasonRewardState&)> source;
        uint32_t const guid = player->GetGUID().GetCounter();
        {
            std::lock_guard<std::mutex> guard(_lock);
            s.seasonId = season;
            for (SeasonRow const& row : _seasons)
                if (row.id == season)
                {
                    s.warEffortTitle = row.weTitle;
                    s.warEffortText = row.weText;
                }
            auto const& totals = _weTotals[season];
            uint64_t goalSum = 0;
            uint64_t doneSum = 0;
            for (PartRow const& p : _parts)
            {
                if (p.season != season)
                    continue;
                auto it = totals.find(p.part);
                uint64_t const have = it == totals.end() ? 0 : it->second;
                SeasonPart part;
                part.name = p.name;
                if (p.goal)
                {
                    part.permille = static_cast<uint32_t>(std::min<uint64_t>(1000, have * 1000 / p.goal));
                    goalSum += p.goal;
                    doneSum += std::min(have, p.goal);
                }
                s.parts.push_back(std::move(part));
            }
            if (goalSum)
                s.warEffortPermille = static_cast<uint32_t>(std::min<uint64_t>(1000, doneSum * 1000 / goalSum));
            auto const& players = _wePlayers[season];
            uint32_t contributors = 0;
            for (auto const& [g, pts] : players)
                if (pts)
                    ++contributors;
            s.contributors = contributors;
            auto me = players.find(guid);
            uint64_t const points = me == players.end() ? 0 : me->second;
            s.points = static_cast<uint32_t>(std::min<uint64_t>(points, 0x7FFFFFFF));
            RankRow const* rank = nullptr;
            RankRow const* next = nullptr;
            for (RankRow const& k : _ranks)   // sorted by min_points (NULLs first, skipped)
            {
                if (!k.minPoints)
                    continue;
                if (*k.minPoints <= points)
                    rank = &k;
                else if (!next)
                    next = &k;
            }
            if (rank)
                s.rankId = rank->id;
            if (next)
            {
                s.nextRankId = next->id;
                s.pointsToNextRank = static_cast<uint32_t>(std::min<uint64_t>(*next->minPoints - points, 0x7FFFFFFF));
            }
            for (RewardRow const& w : _rewards)
                if (w.season == season)
                {
                    rewardIds.push_back(w.id);
                    rewardNeeds.push_back(w.pointsRequired);
                }
            source = _rewardSource;
        }
        if (cfg.tokenItemId)
            s.spareTokens = player->GetItemCount(cfg.tokenItemId);
        uint64_t const points = s.points.value_or(0);
        for (std::size_t i = 0; i < rewardIds.size(); ++i)
        {
            SeasonRewardState rs;
            rs.rewardId = rewardIds[i];
            if (source && source(player, rewardIds[i], rs))
            {
                rs.rewardId = rewardIds[i];
            }
            else if (rewardNeeds[i])
            {
                // a reward row with points_required is earned at that many war effort points
                rs.earned = points >= rewardNeeds[i];
                rs.stateText = *rs.earned ? "Earned" : std::to_string(points) + " / " + std::to_string(rewardNeeds[i]);
            }
            s.rewards.push_back(std::move(rs));
        }
        return s;
    }

    LegacySet Data::DefaultSet(Player* player, uint32_t tier, uint32_t classId)
    {
        LegacySet set;
        set.tier = tier;
        set.classId = classId;
        std::function<bool(Player*, uint32_t)> item;
        std::function<bool(Player*, uint32_t)> outfit;
        {
            std::lock_guard<std::mutex> guard(_lock);
            for (SetRow const& s : _sets)
            {
                if (s.tier != tier || s.classId != classId)
                    continue;
                set.setId = s.setId;
                set.name = s.name;
                set.itemIds = s.items;
                set.sourceDungeonIds = s.sources;
                set.lvlMin = s.lvlMin;
                set.lvlMax = s.lvlMax;
                set.echoBoss = s.echoBoss;
                set.note = s.note;
                break;
            }
            item = _itemCollected;
            outfit = _outfitUnlocked;
        }
        if (set.setId && item)
        {
            uint32_t bits = 0;
            for (std::size_t i = 0; i < set.itemIds.size() && i < 31; ++i)
                if (item(player, set.itemIds[i]))
                    bits |= 1u << i;
            set.collectedBits = bits;
        }
        if (set.setId && outfit)
            set.outfitUnlocked = outfit(player, *set.setId);
        return set;
    }

    LegacyIndex Data::DefaultIndex(Player* player)
    {
        LegacyIndex idx;
        std::function<bool(Player*, uint32_t)> item;
        {
            std::lock_guard<std::mutex> guard(_lock);
            std::set<uint32_t> seen;
            for (SetRow const& s : _sets)
                for (uint32_t id : s.items)
                    if (seen.insert(id).second)
                    {
                        LegacyIndexEntry e;
                        e.itemId = id;
                        e.tier = s.tier;
                        e.setId = s.setId;
                        idx.items.push_back(e);
                    }
            item = _itemCollected;
        }
        if (item)
            for (LegacyIndexEntry& e : idx.items)
                e.collected = item(player, e.itemId);
        return idx;
    }

    FirstsList Data::Firsts()
    {
        FirstsList list;
        std::lock_guard<std::mutex> guard(_lock);
        for (FirstRow const& f : _firsts)
        {
            if (list.entries.size() >= 50)
                break;
            list.entries.push_back({ f.kind, f.text, f.who, f.date });
        }
        return list;
    }

    // =============================================================================================
    // Leaderboards (the module's own rows)
    // =============================================================================================
    bool Data::Better(LbRow const& a, LbRow const& b)
    {
        auto valueDesc = [](Opt<int64_t> const& x, Opt<int64_t> const& y) -> int {
            int64_t const vx = x.value_or(INT64_MIN);
            int64_t const vy = y.value_or(INT64_MIN);
            return vx > vy ? 1 : (vx < vy ? -1 : 0);
        };
        auto timeAsc = [](Opt<int64_t> const& x, Opt<int64_t> const& y) -> int {
            int64_t const vx = x.value_or(INT64_MAX);
            int64_t const vy = y.value_or(INT64_MAX);
            return vx < vy ? 1 : (vx > vy ? -1 : 0);
        };
        int c = 0;
        switch (a.board)
        {
            case 'K':   // higher key, then more time left
                c = valueDesc(a.value, b.value);
                if (!c)
                    c = valueDesc(a.timeSec, b.timeSec);
                break;
            case 'R':   // higher floor, then faster
                c = valueDesc(a.value, b.value);
                if (!c)
                    c = timeAsc(a.timeSec, b.timeSec);
                break;
            default:    // E: faster kill
                c = timeAsc(a.timeSec, b.timeSec);
                break;
        }
        if (c)
            return c > 0;
        if (a.date != b.date)
            return a.date < b.date;   // the earlier run keeps the place
        return a.id < b.id;
    }

    void Data::AnswerLeaderboard(Player* player, Intent const& in)
    {
        if (in.board == Board::Firsts)
        {
            Ui::SendFirsts(player, Firsts());
            return;
        }
        if (in.board == Board::Arena)
        {
            // section 20: answered by the arena system's board handler (Ui::OnBoardQuery); without one, nothing ranks
            Leaderboard empty;
            empty.board = Board::Arena;
            empty.seasonId = in.seasonId;
            empty.dungeonId = in.dungeonId;
            empty.classId = in.classId;
            Ui::SendLeaderboard(player, empty);
            LeaderboardMe none;
            none.board = Board::Arena;
            Ui::SendLeaderboardMe(player, none);
            return;
        }
        Config const cfg = Mgr::Instance().CfgCopy();
        uint32_t const season = in.seasonId ? in.seasonId : CurrentSeason();
        uint32_t const guid = player->GetGUID().GetCounter();
        char const board = static_cast<char>(in.board);

        Leaderboard lb;
        lb.board = in.board;
        lb.seasonId = season;
        lb.dungeonId = in.dungeonId;
        lb.classId = in.classId;
        LeaderboardMe me;
        me.board = in.board;
        {
            std::lock_guard<std::mutex> guard(_lock);
            std::vector<LbRow const*> rows;
            for (LbRow const& r : _lb)
            {
                if (r.board != board || r.season != season)
                    continue;
                if (in.dungeonId && r.dungeon != in.dungeonId)
                    continue;
                if (in.classId)
                {
                    bool has = false;
                    for (LeaderboardMember const& m : r.members)
                        if (m.classId && *m.classId == in.classId)
                            has = true;
                    if (!has)
                        continue;
                }
                rows.push_back(&r);
            }
            std::sort(rows.begin(), rows.end(), [](LbRow const* a, LbRow const* b) { return Better(*a, *b); });
            uint32_t const pageSize = cfg.leaderboardPageSize;
            uint32_t const pages = std::max<uint32_t>(1, static_cast<uint32_t>((rows.size() + pageSize - 1) / pageSize));
            uint32_t const page = std::clamp<uint32_t>(in.page, 1, pages);
            lb.page = page;
            lb.pages = pages;
            for (std::size_t i = static_cast<std::size_t>(page - 1) * pageSize; i < rows.size() && lb.rows.size() < pageSize; ++i)
            {
                LbRow const& r = *rows[i];
                LeaderboardRow out;
                out.rank = static_cast<uint32_t>(i + 1);
                if (r.board == 'K' || r.dungeon)
                    out.dungeonId = r.dungeon;
                out.value = r.value;
                out.timeSec = r.timeSec;
                out.dateEpoch = r.date;
                out.members = r.members;
                out.label = r.label;
                lb.rows.push_back(std::move(out));
            }
            for (std::size_t i = 0; i < rows.size(); ++i)
            {
                LbRow const& r = *rows[i];
                if (std::find(r.memberGuids.begin(), r.memberGuids.end(), guid) == r.memberGuids.end())
                    continue;
                uint32_t const rank = static_cast<uint32_t>(i + 1);
                me.rank = rank;
                me.topPercent = std::max<uint32_t>(1, static_cast<uint32_t>((uint64_t(rank) * 100 + rows.size() - 1) / rows.size()));
                me.value = r.value;
                if (r.board == 'K' || r.dungeon)
                    me.dungeonId = r.dungeon;
                me.timeSec = r.timeSec;
                me.label = r.label;
                LbRow const& top = *rows[0];
                if (r.board == 'E')
                {
                    if (r.timeSec && top.timeSec && *r.timeSec > 0)
                        me.barPermille = static_cast<uint32_t>(std::clamp<int64_t>(*top.timeSec * 1000 / *r.timeSec, 0, 1000));
                }
                else if (r.value && top.value && *top.value > 0)
                    me.barPermille = static_cast<uint32_t>(std::clamp<int64_t>(*r.value * 1000 / *top.value, 0, 1000));
                break;
            }
        }
        Ui::SendLeaderboard(player, lb);
        Ui::SendLeaderboardMe(player, me);
    }

    void Data::RecordRun(Ui::LeaderboardEntry const& entry)
    {
        if (entry.board == Board::Firsts || entry.board == Board::Arena)   // arena ratings are not runs (section 20)
            return;
        Config const cfg = Mgr::Instance().CfgCopy();
        LbRow row;
        row.board = static_cast<char>(entry.board);
        row.season = entry.seasonId ? entry.seasonId : CurrentSeason();
        row.dungeon = entry.dungeonId;
        row.value = entry.value;
        row.timeSec = entry.timeSec;
        row.date = NowEpoch();
        row.label = CleanLabel(entry.label, 48);
        std::vector<uint32_t> guids;
        for (Player* p : entry.members)
        {
            if (!p)
                continue;
            LeaderboardMember m;
            m.name = p->GetName();
            m.classId = p->getClass();
            row.members.push_back(std::move(m));
            guids.push_back(p->GetGUID().GetCounter());
        }
        if (guids.empty())
            return;
        row.memberGuids = guids;
        std::sort(guids.begin(), guids.end());
        for (uint32_t g : guids)
            row.teamKey += (row.teamKey.empty() ? "" : "-") + std::to_string(g);

        std::string membersText;
        for (LeaderboardMember const& m : row.members)
        {
            if (!membersText.empty())
                membersText += ':';
            membersText += m.name + "~" + std::to_string(m.classId.value_or(0));
        }
        std::string guidText;
        for (uint32_t g : row.memberGuids)
            guidText += (guidText.empty() ? "" : ",") + std::to_string(g);

        std::vector<uint32_t> pruned;
        {
            std::lock_guard<std::mutex> guard(_lock);
            LbRow* existing = nullptr;
            for (LbRow& r : _lb)
                if (r.board == row.board && r.season == row.season && r.dungeon == row.dungeon && r.teamKey == row.teamKey &&
                    (row.board != 'E' || r.label == row.label))
                    existing = &r;
            if (existing)
            {
                // the group's best run stays; a worse one changes nothing
                if (!Better(row, *existing))
                    return;
                row.id = existing->id;
                *existing = row;
                CharacterDatabase.Execute("UPDATE `bleakhold_leaderboard` SET `value` = {}, `time_sec` = {}, `date` = {}, `label` = '{}', "
                    "`members` = '{}', `member_guids` = '{}' WHERE `id` = {}", SqlInt(row.value), SqlInt(row.timeSec), row.date, Esc(row.label),
                    Esc(membersText), Esc(guidText), row.id);
            }
            else
            {
                row.id = _nextLbId++;
                _lb.push_back(row);
                CharacterDatabase.Execute("INSERT INTO `bleakhold_leaderboard` (`id`, `board`, `season_id`, `dungeon_id`, `value`, `time_sec`, "
                    "`date`, `label`, `team_key`, `members`, `member_guids`) VALUES ({}, '{}', {}, {}, {}, {}, {}, '{}', '{}', '{}', '{}')",
                    row.id, std::string(1, row.board), row.season, row.dungeon, SqlInt(row.value), SqlInt(row.timeSec), row.date, Esc(row.label),
                    Esc(row.teamKey), Esc(membersText), Esc(guidText));
            }

            // keep at most BleakholdUi.Leaderboard.MaxRows rows per board, season and dungeon
            std::vector<LbRow const*> same;
            for (LbRow const& r : _lb)
                if (r.board == row.board && r.season == row.season && r.dungeon == row.dungeon)
                    same.push_back(&r);
            if (same.size() > cfg.leaderboardMaxRows)
            {
                std::sort(same.begin(), same.end(), [](LbRow const* a, LbRow const* b) { return Better(*a, *b); });
                for (std::size_t i = cfg.leaderboardMaxRows; i < same.size(); ++i)
                    pruned.push_back(same[i]->id);
                _lb.erase(std::remove_if(_lb.begin(), _lb.end(), [&](LbRow const& r) {
                    return std::find(pruned.begin(), pruned.end(), r.id) != pruned.end();
                }), _lb.end());
            }
        }
        for (uint32_t id : pruned)
            CharacterDatabase.Execute("DELETE FROM `bleakhold_leaderboard` WHERE `id` = {}", id);
    }

    bool Data::RecordFirst(std::string_view firstId, std::string_view kindKey, std::string_view text, std::string_view who)
    {
        if (firstId.empty() || firstId.size() > 64)
            return false;
        FirstRow row{ std::string(firstId), CleanLabel(kindKey, 16), CleanLabel(text, 120),
            CleanLabel(who, 80), NowEpoch() };
        {
            std::lock_guard<std::mutex> guard(_lock);
            for (FirstRow const& f : _firsts)
                if (f.id == row.id)
                    return false;
            _firsts.insert(_firsts.begin(), row);
        }
        CharacterDatabase.Execute("INSERT IGNORE INTO `bleakhold_server_first` (`first_id`, `kind_key`, `text`, `who`, `date`) "
            "VALUES ('{}', '{}', '{}', '{}', {})", Esc(row.id), Esc(row.kind), Esc(row.text), Esc(row.who), row.date);
        return true;
    }

    void Data::WarEffortAdd(Player* player, uint32_t partId, uint32_t points)
    {
        if (!player || !points)
            return;
        uint32_t const season = CurrentSeason();
        if (!season)
            return;
        uint32_t const guid = player->GetGUID().GetCounter();
        {
            std::lock_guard<std::mutex> guard(_lock);
            _weTotals[season][partId] += points;
            _wePlayers[season][guid] += points;
        }
        CharacterDatabase.Execute("INSERT INTO `bleakhold_war_effort` (`season_id`, `guid`, `part_id`, `points`) VALUES ({}, {}, {}, {}) "
            "ON DUPLICATE KEY UPDATE `points` = `points` + {}", season, guid, partId, points, points);
        Mgr::Instance().Refresh(player, Topic::Season);
    }

    uint64_t Data::WarEffortPoints(uint32_t lowGuid)
    {
        uint32_t const season = CurrentSeason();
        std::lock_guard<std::mutex> guard(_lock);
        auto s = _wePlayers.find(season);
        if (s == _wePlayers.end())
            return 0;
        auto p = s->second.find(lowGuid);
        return p == s->second.end() ? 0 : p->second;
    }

    void Data::ForgetCharacter(uint32_t lowGuid)
    {
        if (!lowGuid)
            return;
        bool loaded = false;
        {
            std::lock_guard<std::mutex> guard(_lock);
            loaded = _charactersLoaded;
            for (LbRow& r : _lb)
            {
                auto it = std::find(r.memberGuids.begin(), r.memberGuids.end(), lowGuid);
                if (it == r.memberGuids.end())
                    continue;
                r.memberGuids.erase(it);
                r.teamKey += "x";   // a team key is guids and '-': no later group matches this row any more
            }
            for (auto& [season, players] : _wePlayers)
                players.erase(lowGuid);
        }
        CharacterDatabaseTransaction trans = CharacterDatabase.BeginTransaction();
        // the same in the table: the guid leaves member_guids ("1,2,3"), the team key gets the mark
        trans->Append("UPDATE `bleakhold_leaderboard` SET `member_guids` = TRIM(BOTH ',' FROM REPLACE(CONCAT(',', "
            "`member_guids`, ','), ',{},', ',')), `team_key` = CONCAT(`team_key`, 'x') "
            "WHERE FIND_IN_SET('{}', `member_guids`)", lowGuid, lowGuid);
        // the war effort points move to guid 0, so the totals stay the same after a restart
        if (QueryResult r = CharacterDatabase.Query(
                "SELECT `season_id`, `part_id`, `points` FROM `bleakhold_war_effort` WHERE `guid` = {}", lowGuid))
            do
            {
                Field* f = r->Fetch();
                uint64_t const points = f[2].Get<uint64>();
                trans->Append("INSERT INTO `bleakhold_war_effort` (`season_id`, `guid`, `part_id`, `points`) "
                    "VALUES ({}, 0, {}, {}) ON DUPLICATE KEY UPDATE `points` = `points` + {}", f[0].Get<uint32>(),
                    f[1].Get<uint32>(), points, points);
            } while (r->NextRow());
        trans->Append("DELETE FROM `bleakhold_war_effort` WHERE `guid` = {}", lowGuid);
        // its own transaction (an error here never stops the character delete); before LoadAll (the startup purge
        // of old deleted characters) at once, so the load reads the result
        if (loaded)
            CharacterDatabase.CommitTransaction(trans);
        else
            CharacterDatabase.DirectCommitTransaction(trans);
    }

    void Data::HandIn(Player* player, Intent const& intent)
    {
        Config const cfg = Mgr::Instance().CfgCopy();
        if (!cfg.tokenItemId || !cfg.pointsPerToken)
        {
            Ui::Refuse(player, intent, "unavailable", "This is not available on this realm yet.");
            return;
        }
        if (!CurrentSeason())
        {
            Ui::Refuse(player, intent, "no_season", "There is no season running.");
            return;
        }
        uint32_t const count = player->GetItemCount(cfg.tokenItemId);
        if (!count)
        {
            Ui::Refuse(player, intent, "no_tokens", "You have no war effort tokens to hand in.");
            return;
        }
        // the tokens are destroyed before the points are added, in the same world tick: a repeated
        // WEHANDIN finds no tokens and pays nothing
        player->DestroyItemCount(cfg.tokenItemId, count, true);
        uint64_t const points = std::min<uint64_t>(uint64_t(count) * cfg.pointsPerToken, 0x7FFFFFFF);
        WarEffortAdd(player, cfg.tokenPart, static_cast<uint32_t>(points));
        Ui::Toast(player, ToastKind::Season, "Tokens handed in",
            std::to_string(count) + (count == 1 ? " token" : " tokens") + " added to the War Effort", "season");
    }

    static_assert(EmojiCatalogueCount <= Proto::MaxEmojis, "emoji catalogue (Tools/EmojiForge)");
    static_assert(Ui::EmojiKit(0) == Proto::EmojiKitBase, "Ui::EmojiKit (BleakholdUi.h) and the protocol agree");

    void Data::Emoji(Player* player, Intent const& intent)
    {
        // world thread (the chat hook); the cooldown (BleakholdUi.Emoji.CooldownMs) is the Endpoint's and
        // BleakholdUi.Emoji.Enable is Mgr::Dispatch's, so both also hold for a custom handler
        if (intent.emojiId >= EmojiCatalogueCount)
        {
            Ui::Refuse(player, intent, "unknown_emoji", "That emoji does not exist on this realm.");
            return;
        }
        if (!player->IsInWorld())
            return;
        // addon messages skip the core's mute check (ChatHandler.cpp), and an emoji is seen by others
        if (!player->CanSpeak())
        {
            Ui::Refuse(player, intent, "muted", "You cannot use emojis while muted.");
            return;
        }
        // SMSG_PLAY_SPELL_VISUAL to the player and every player who can see them (section 13)
        player->SendPlaySpellVisual(Ui::EmojiKit(intent.emojiId));
    }

    static_assert(DanceCatalogueCount <= Proto::MaxDances, "dance catalogue (Tools/DanceForge)");
    static_assert(Ui::DanceKit(0) == Proto::DanceKitBase, "Ui::DanceKit (BleakholdUi.h) and the protocol agree");

    void Data::Dance(Player* player, Intent const& intent)
    {
        // world thread (the chat hook); the cooldown (BleakholdUi.Dance.CooldownMs) is the Endpoint's and
        // BleakholdUi.Dance.Enable is Mgr::Dispatch's, so both also hold for a custom handler
        if (intent.danceId >= DanceCatalogueCount)
        {
            Ui::Refuse(player, intent, "unknown_dance", "That dance does not exist on this realm.");
            return;
        }
        if (!player->IsInWorld())
            return;
        if (!player->IsAlive())
        {
            Ui::Refuse(player, intent, "dead", "You cannot dance while dead.");
            return;
        }
        if (player->IsInCombat())
        {
            Ui::Refuse(player, intent, "in_combat", "You cannot dance in combat.");
            return;
        }
        if (player->IsMounted() || player->GetVehicle() || player->IsInFlight())
        {
            Ui::Refuse(player, intent, "mounted", "You cannot dance while mounted.");
            return;
        }
        if (player->isMoving() || player->IsFlying() || player->IsFalling() || player->IsInWater())
        {
            Ui::Refuse(player, intent, "moving", "Stand still on the ground to dance.");
            return;
        }
        if (player->IsNonMeleeSpellCast(false))
        {
            Ui::Refuse(player, intent, "casting", "You cannot dance while casting.");
            return;
        }
        if (!player->IsStandState())
            player->SetStandState(UNIT_STAND_STATE_STAND);
        // the stock dance for every client; the server clears it when the player moves, turns or dies
        // (MovementHandler.cpp, Unit::setDeathState), which also ends the Bleakhold dance
        player->SetEmoteState(EMOTE_STATE_DANCE);
        // SMSG_PLAY_SPELL_VISUAL to the player and every player who can see them: the Bleakhold clients play the
        // dance for as long as the emote state lasts (section 14)
        player->SendPlaySpellVisual(Ui::DanceKit(intent.danceId));
        Dancer& d = _dancers[player->GetGUID().GetRawValue()];
        d.danceId = intent.danceId;
        d.nextLoopMs = Mgr::NowMs() + DanceLoopMs[intent.danceId];
    }

    void Data::UpdateDancers(uint64_t nowMs)
    {
        // the kit again at the start of every loop, so a client that sees the dancer later joins in step
        for (auto it = _dancers.begin(); it != _dancers.end();)
        {
            Player* p = ObjectAccessor::FindPlayer(ObjectGuid(it->first));
            if (!p || !p->IsInWorld() || p->GetUInt32Value(UNIT_NPC_EMOTESTATE) != EMOTE_STATE_DANCE)
            {
                it = _dancers.erase(it);
                continue;
            }
            Dancer& d = it->second;
            if (nowMs >= d.nextLoopMs)
            {
                p->SendPlaySpellVisual(Ui::DanceKit(d.danceId));
                uint32_t const loop = std::max<uint32_t>(DanceLoopMs[d.danceId], 500);
                d.nextLoopMs += loop;
                if (d.nextLoopMs <= nowMs)
                    d.nextLoopMs = nowMs + loop;   // the world stalled: start counting loops again from now
            }
            ++it;
        }
    }

    // =============================================================================================
    // Cases (section 15)
    // =============================================================================================
    bool Data::HasCases()
    {
        std::lock_guard<std::mutex> guard(_lock);
        return !_cases.empty();
    }

    CaseList Data::CaseIds()
    {
        std::lock_guard<std::mutex> guard(_lock);
        CaseList out;
        for (CaseRow const& c : _cases)
            out.caseItemIds.push_back(c.itemId);
        return out;
    }

    Opt<CaseInfo> Data::CaseFor(uint32_t caseItemId)
    {
        std::lock_guard<std::mutex> guard(_lock);
        for (CaseRow const& c : _cases)
        {
            if (c.itemId != caseItemId)
                continue;
            CaseInfo info;
            info.caseItemId = c.itemId;
            info.title = c.title;
            info.text = c.text;
            info.keyItemId = c.keyItemId;
            info.keyCount = c.keyItemId ? c.keyCount : 0;
            std::vector<uint32_t> const chances = Cases::Chances(c.weights);
            for (std::size_t i = 0; i < c.items.size(); ++i)
                info.rewards.push_back({ c.items[i], c.counts[i], chances[i], c.tiers[i] });
            return info;
        }
        return std::nullopt;
    }

    void Data::OpenCase(Player* player, Intent const& intent)
    {
        // world thread (the chat hook); the cooldown (BleakholdUi.Case.CooldownMs) is the Endpoint's and
        // BleakholdUi.Case.Enable is Mgr::Dispatch's, so both also hold for a custom handler
        CaseRow c;
        bool any = false;
        {
            std::lock_guard<std::mutex> guard(_lock);
            any = !_cases.empty();
            for (CaseRow const& row : _cases)
                if (row.itemId == intent.caseItemId)
                    c = row;
        }
        if (!any)
        {
            Ui::Refuse(player, intent, "unavailable", "Cases are turned off on this realm.");
            return;
        }
        if (!c.itemId)
        {
            Ui::Refuse(player, intent, "unknown_case", "That is not a case.");
            return;
        }
        if (!player->IsInWorld())
            return;
        if (!player->HasItemCount(c.itemId, 1))
        {
            Ui::Refuse(player, intent, "no_case", "You have no such case in your bags.");
            return;
        }
        if (c.keyItemId && !player->HasItemCount(c.keyItemId, c.keyCount))
        {
            Ui::Refuse(player, intent, "no_key", "You need the case's key to open it.");
            return;
        }
        // Every reward must fit before the roll: a refusal that depended on the roll would let a player open again
        // and again until the reward they want comes up (a unique reward they own, a stack that fits, ...).
        for (std::size_t i = 0; i < c.items.size(); ++i)
        {
            ItemPosCountVec test;
            InventoryResult const room = player->CanStoreNewItem(NULL_BAG, NULL_SLOT, test, c.items[i], c.counts[i]);
            if (room == EQUIP_ERR_OK)
                continue;
            bool const unique = room == EQUIP_ERR_CANT_CARRY_MORE_OF_THIS || room == EQUIP_ERR_ITEM_MAX_LIMIT_CATEGORY_COUNT_EXCEEDED;
            Ui::Refuse(player, intent, "bags_full", unique
                ? "This case can give a reward you cannot carry more of. Your case was not used."
                : "Make room in your bags for any reward first. Your case was not used.");
            return;
        }
        uint64_t const total = Cases::TotalWeight(c.weights);   // at most 2^32 - 1 (the loader)
        std::size_t const index = Cases::Pick(c.weights, urand(0, uint32(total - 1)));
        if (index >= c.items.size())
            return;
        uint32_t const itemId = c.items[index], count = c.counts[index];
        ItemPosCountVec dest;
        if (player->CanStoreNewItem(NULL_BAG, NULL_SLOT, dest, itemId, count) != EQUIP_ERR_OK)
            return;   // checked just above
        // the case and its key go first, so a failure below can never hand out a reward for nothing
        player->DestroyItemCount(c.itemId, 1, true);
        if (c.keyItemId)
            player->DestroyItemCount(c.keyItemId, c.keyCount, true);
        Item* item = player->StoreNewItem(dest, itemId, true, Item::GenerateItemRandomPropertyId(itemId));
        if (!item)
        {
            LOG_ERROR("module", "[Bleakhold] case {}: could not give item {} x{} to {} ({}); the case and key are gone", c.itemId,
                itemId, count, player->GetName(), player->GetGUID().ToString());
            Ui::Refuse(player, intent, "failed", "The case opened but the reward could not be given. Tell a game master: it is logged.");
            return;
        }
        player->SendNewItem(item, count, true, false);
        LOG_INFO("module", "[Bleakhold] {} opened case {} and got {} x{}", player->GetName(), c.itemId, itemId, count);

        Unbox won;
        won.caseItemId = c.itemId;
        won.rewardIndex = uint32_t(index + 1);
        won.itemId = itemId;
        won.count = count;
        won.nonce = intent.caseNonce;
        Ui::SendUnbox(player, won);

        if (c.announceTier && c.tiers[index] >= c.announceTier)
        {
            ItemTemplate const* proto = sObjectMgr->GetItemTemplate(itemId);
            if (proto)
            {
                char color[9];
                std::snprintf(color, sizeof(color), "%08x", ItemQualityColors[std::min<uint32>(proto->Quality, MAX_ITEM_QUALITY - 1)]);
                std::string const link = "|c" + std::string(color) + "|Hitem:" + std::to_string(itemId) + ":0:0:0:0:0:" +
                    std::to_string(item->GetItemRandomPropertyId()) + ":" + std::to_string(item->GetItemSuffixFactor()) + ":0|h[" +
                    proto->Name1 + "]|h|r";
                Ui::Announce(Ui::AnnounceTag::Case, player->GetName() + " found " + link + " in " + c.title + "!");
            }
        }
    }

    // =============================================================================================
    // Default providers and handlers
    // =============================================================================================
    void Data::RegisterDefaults()
    {
        Mgr& m = Mgr::Instance();
        auto cached = [](Topic t) {
            return [t](Player* p, TopicRequest const&) { Mgr::Instance().ResendCached(p, t); };
        };
        for (Topic t : { Topic::Week, Topic::Tasks, Topic::Key, Topic::Board, Topic::Queue, Topic::Coll, Topic::Rift })
            m.SetDefaultProvider(t, cached(t));

        m.SetDefaultProvider(Topic::Era, [](Player* p, TopicRequest const&) {
            if (Mgr::Instance().ResendCached(p, Topic::Era))
                return;
            if (Opt<EraState> era = Data::Instance().DefaultEra(Mgr::Instance().WeeklyBonusDone(p)))
                Mgr::Instance().Push(p, "ERA", Topic::Era, nullptr, [&](uint32_t rev) { return EncodeEra(rev, *era); });
        });
        m.SetDefaultProvider(Topic::Season, [](Player* p, TopicRequest const&) {
            if (Mgr::Instance().ResendCached(p, Topic::Season))
                return;
            if (Opt<SeasonState> s = Data::Instance().DefaultSeason(p))
                Mgr::Instance().Push(p, "SEASON", Topic::Season, nullptr, [&](uint32_t rev) { return EncodeSeason(rev, *s); });
        });
        m.SetDefaultProvider(Topic::Lidx, [](Player* p, TopicRequest const&) {
            if (Mgr::Instance().ResendCached(p, Topic::Lidx))
                return;
            // built once per player and remembered (section 8: bound the work of one message)
            Ui::SendLegacyIndex(p, Data::Instance().DefaultIndex(p));
        });
        m.SetDefaultProvider(Topic::Set, [](Player* p, TopicRequest const& req) {
            Ui::SendLegacySet(p, Data::Instance().DefaultSet(p, req.arg1, req.arg2));
        });
        m.SetDefaultProvider(Topic::Firsts, [](Player* p, TopicRequest const&) { Ui::SendFirsts(p, Data::Instance().Firsts()); });
        m.SetDefaultProvider(Topic::Mplus, [](Player* p, TopicRequest const&) { Mgr::Instance().SendRunTo(p); });
        m.SetDefaultProvider(Topic::Def, [](Player* p, TopicRequest const&) { Mgr::Instance().SendDefinitions(p); });
        // with BleakholdUi.Case.Enable = 0 the list is empty, so the addon shows no case (section 15)
        m.SetDefaultProvider(Topic::Cases, [](Player* p, TopicRequest const&) {
            Ui::SendCases(p, Mgr::Instance().CasesEnabled() ? Data::Instance().CaseIds() : CaseList());
        });
        m.SetDefaultProvider(Topic::Case, [](Player* p, TopicRequest const& req) {
            if (!Mgr::Instance().CasesEnabled())
                return;
            if (Opt<CaseInfo> c = Data::Instance().CaseFor(req.arg1))
                Ui::SendCase(p, *c);
        });

        m.SetDefaultHandler(IntentType::LeaderboardQuery, [](Player* p, Intent const& in) { Data::Instance().AnswerLeaderboard(p, in); });
        m.SetDefaultHandler(IntentType::WarEffortHandIn, [](Player* p, Intent const& in) { Data::Instance().HandIn(p, in); });
        m.SetDefaultHandler(IntentType::Emoji, [](Player* p, Intent const& in) { Data::Instance().Emoji(p, in); });
        m.SetDefaultHandler(IntentType::Dance, [](Player* p, Intent const& in) { Data::Instance().Dance(p, in); });
        m.SetDefaultHandler(IntentType::CaseOpen, [](Player* p, Intent const& in) { Data::Instance().OpenCase(p, in); });

        // camping (section 16): BleakholdCamp.cpp
        m.SetDefaultProvider(Topic::CampState, [](Player* p, TopicRequest const&) { Camp::Instance().RequestState(p); });
        m.SetDefaultHandler(IntentType::Camp, [](Player* p, Intent const& in) { Camp::Instance().HandleCamp(p, in); });
        m.SetDefaultHandler(IntentType::Glide, [](Player* p, Intent const& in) { Camp::Instance().HandleGlide(p, in); });
        m.SetDefaultHandler(IntentType::Repair, [](Player* p, Intent const& in) { Camp::Instance().HandleRepair(p, in); });

        // the cafe (section 21): BleakholdCafe.cpp; Mgr refuses these with CafeErr::Off while FeatureFor is false
        m.SetDefaultHandler(IntentType::CafeShift, [](Player* p, Intent const& in) { Cafe::Instance().HandleShift(p, in); });
        m.SetDefaultHandler(IntentType::CafeTake, [](Player* p, Intent const& in) { Cafe::Instance().HandleTake(p, in); });
        m.SetDefaultHandler(IntentType::CafeStep, [](Player* p, Intent const& in) { Cafe::Instance().HandleStep(p, in); });
        m.SetDefaultHandler(IntentType::CafeRelease, [](Player* p, Intent const& in) { Cafe::Instance().HandleRelease(p, in); });
        m.SetDefaultHandler(IntentType::CafeOrder, [](Player* p, Intent const& in) { Cafe::Instance().HandleOrder(p, in); });
        m.SetDefaultHandler(IntentType::CafeCancel, [](Player* p, Intent const& in) { Cafe::Instance().HandleCancel(p, in); });
        m.SetDefaultHandler(IntentType::CafeStaff, [](Player* p, Intent const& in) { Cafe::Instance().HandleStaff(p, in); });
        for (Topic t : { Topic::CafeList, Topic::CafeState, Topic::CafeQueue, Topic::CafeTickets, Topic::CafeMenu,
                 Topic::CafeOrderState, Topic::CafeProfile, Topic::CafeBuffs })
            m.SetDefaultProvider(t, [](Player* p, TopicRequest const& req) { Cafe::Instance().Provide(p, req); });
        m.SetBoardHandler(Board::Cafe, [](Player* p, Intent const& in) { Cafe::Instance().AnswerBoard(p, in); });
        m.AddHelloObserver([](Player* p, Intent const&) { Cafe::Instance().OnHello(p); });
    }
}
