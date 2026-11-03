/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Glowing marks (section 22): configuration, the tables, the catalogue, the online characters' choices, MARKSET and
 * its money, the lists and the hooks. See BleakholdMarks.h for the threads; the rules are BleakholdMarksRules.h.
 *
 * Money: a paid change takes the copper from the purse and writes the purse (SaveGoldToDB) and the bleakhold_marks row
 * in one CharacterDatabase transaction (the cafe's pattern), so a crash never charges for a change the database lost.
 *
 * Lock order: _lock is a leaf lock; nothing is sent and no Mgr or Data function is called while it is held.
 */

#include "BleakholdMarks.h"
#include "BleakholdMgr.h"
#include "BleakholdUi.h"

#include "Config.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Log.h"
#include "Player.h"
#include "SharedDefines.h"
#include "WorldSession.h"

#include <algorithm>

namespace Bleakhold
{
    namespace R = MarksRules;

    namespace
    {
        constexpr std::size_t MaxProblemLines = 40;   // catalogue rows logged one by one, the rest counted

        uint32_t Low(Player const* p) { return p->GetGUID().GetCounter(); }
        uint32_t NowSec() { return static_cast<uint32_t>(GameTime::GetGameTime().count()); }

        bool IsGameMaster(Player* p)
        {
            WorldSession* session = p->GetSession();
            return session && session->GetSecurity() >= SEC_GAMEMASTER;
        }

        uint32_t U32(char const* key, uint32_t def, uint32_t lo, uint32_t hi)
        {
            uint32_t const v = sConfigMgr->GetOption<uint32_t>(key, def);
            if (v < lo || v > hi)
            {
                LOG_ERROR("module", "[Bleakhold] {} = {} is outside {}..{}; using default {}", key, v, lo, hi, def);
                return def;
            }
            return v;
        }

        bool SameSettings(R::Settings const& a, R::Settings const& b)
        {
            return a.enable == b.enable && a.gmOnly == b.gmOnly && a.priceCopper == b.priceCopper &&
                a.firstFree == b.firstFree && a.cooldownHours == b.cooldownHours && a.maxListEntries == b.maxListEntries;
        }
    }

    Marks& Marks::Instance()
    {
        static Marks instance;
        return instance;
    }

    // =============================================================================================================
    // Configuration, tables and the catalogue
    // =============================================================================================================
    void Marks::LoadConfig()
    {
        R::Settings s;
        s.enable = sConfigMgr->GetOption<bool>("BleakholdUi.Marks.Enable", false);
        s.gmOnly = sConfigMgr->GetOption<bool>("BleakholdUi.Marks.GmOnly", true);
        s.priceCopper = U32("BleakholdUi.Marks.Price", 100000, 0, R::MaxPriceCopper);
        s.firstFree = sConfigMgr->GetOption<bool>("BleakholdUi.Marks.FirstFree", true);
        s.cooldownHours = U32("BleakholdUi.Marks.CooldownHours", 1, 0, R::MaxCooldownHours);
        s.maxListEntries = U32("BleakholdUi.Marks.MaxListEntries", static_cast<uint32_t>(MaxMarkListEntries), 1,
            static_cast<uint32_t>(MaxMarkListEntries));
        s = R::Clamped(s);

        std::lock_guard<std::mutex> guard(_lock);
        bool const changed = !SameSettings(s, _cfg);
        _cfg = s;
        _gmOnly = s.gmOnly;
        _featureOn = s.enable && _cat.Offered() > 0;
        if (_startupDone && changed)
            FeatureMayHaveChanged();
    }

    void Marks::EnsureTables()
    {
        if (_tablesDone)
            return;
        for (std::string_view sql : R::WorldTablesSql)
            WorldDatabase.DirectExecute(sql);
        for (std::string_view sql : R::CharacterTablesSql)
            CharacterDatabase.DirectExecute(sql);
        _tablesDone = true;
    }

    void Marks::OnStartup()
    {
        std::lock_guard<std::mutex> guard(_lock);
        EnsureTables();
        _startupDone = true;
    }

    void Marks::LoadCatalogue()
    {
        {
            std::lock_guard<std::mutex> guard(_lock);
            EnsureTables();
        }
        std::vector<R::CatalogueRow> rows;
        if (QueryResult r = WorldDatabase.Query("SELECT `race`, `sex`, `kind`, `design`, `colour`, `race_file`, `design_key`, "
            "`design_name`, `colour_key`, `colour_name`, `hex`, `glow`, `dk_only`, `texture` FROM `bleakhold_mark_catalogue`"))
        {
            do
            {
                Field* f = r->Fetch();
                R::CatalogueRow row;
                row.race = f[0].Get<uint8>();
                row.sex = f[1].Get<uint8>();
                std::string const kind = f[2].Get<std::string>();
                row.kind = kind.size() == 1 ? kind[0] : '?';
                row.design = f[3].Get<uint8>();
                row.colour = f[4].Get<uint8>();
                row.raceFile = f[5].Get<std::string>();
                row.designKey = f[6].Get<std::string>();
                row.designName = f[7].Get<std::string>();
                row.colourKey = f[8].Get<std::string>();
                row.colourName = f[9].Get<std::string>();
                row.hex = f[10].Get<std::string>();
                row.glow = f[11].Get<uint8>();
                row.dkOnly = f[12].Get<uint8>();
                row.texture = f[13].Get<std::string>();
                rows.push_back(std::move(row));
            } while (r->NextRow());
        }
        R::Catalogue cat = R::BuildCatalogue(rows);
        for (std::size_t i = 0; i < cat.problems.size() && i < MaxProblemLines; ++i)
            LOG_ERROR("module", "[Bleakhold] bleakhold_mark_catalogue: {}", cat.problems[i]);
        if (cat.problems.size() > MaxProblemLines)
            LOG_ERROR("module", "[Bleakhold] bleakhold_mark_catalogue: {} more problems", cat.problems.size() - MaxProblemLines);
        LOG_INFO("server.loading", ">> Bleakhold glowing marks: {} catalogue rows ({} used), {} race-sexes offered", cat.rows,
            cat.goodRows, cat.Offered());

        std::lock_guard<std::mutex> guard(_lock);
        bool const changed = !(cat == _cat);
        _cat = std::move(cat);
        _featureOn = _cfg.enable && _cat.Offered() > 0;
        if (_startupDone && changed)
            FeatureMayHaveChanged();
    }

    void Marks::FillDefinitions(Definitions& defs)
    {
        std::lock_guard<std::mutex> guard(_lock);
        // with BleakholdUi.Marks.Enable = 0 DEF N is left out: the data version stays the same while it is off
        if (_cfg.enable)
            R::FillDefinitions(_cat, defs);
    }

    // A change of the configuration or the catalogue: everyone with the bit gets MARKME and a new list on the next tick
    // (the applied choices, who is listed and the prices may all have changed), after a new HELLO when the bit itself
    // may have changed for someone.
    void Marks::FeatureMayHaveChanged()
    {
        bool const on = _featureOn.load();
        if (on != _lastFeatureOn || (on && _cfg.gmOnly != _lastGmOnly))
            _helloPending = true;
        _lastFeatureOn = on;
        _lastGmOnly = _cfg.gmOnly;
        _resendPending = true;
    }

    bool Marks::FeatureFor(Player* player) const
    {
        if (!player || !_featureOn.load())
            return false;
        return !_gmOnly.load() || IsGameMaster(player);
    }

    // =============================================================================================================
    // The online characters
    // =============================================================================================================
    Marks::Online& Marks::OnlineOf(Player* player)
    {
        uint32_t const low = Low(player);
        auto it = _online.find(low);
        if (it != _online.end())
            return it->second;
        Online o;
        o.race = player->getRace(true);
        o.sex = player->getGender();
        o.classId = player->getClass();
        o.gameMaster = IsGameMaster(player);
        EnsureTables();
        if (QueryResult r = CharacterDatabase.Query("SELECT `design`, `colour`, `eye`, `changes`, `changed_at`, `paid_total` "
            "FROM `bleakhold_marks` WHERE `guid` = {}", low))
        {
            Field* f = r->Fetch();
            o.stored.choice.design = f[0].Get<uint8>();
            o.stored.choice.colour = f[1].Get<uint8>();
            o.stored.choice.eye = f[2].Get<uint8>();
            o.stored.changes = f[3].Get<uint32>();
            o.stored.changedAt = f[4].Get<uint32>();
            o.stored.paidTotal = f[5].Get<uint32>();
        }
        return _online.emplace(low, o).first->second;
    }

    R::Choice Marks::AppliedLocked(Online const& o) const
    {
        return R::Applied(_cat, o.race, o.sex, o.classId, o.stored.choice);
    }

    bool Marks::OwnerFeatureLocked(Online const& o) const
    {
        return _featureOn.load() && (!_cfg.gmOnly || o.gameMaster);
    }

    MarkEntry Marks::EntryLocked(uint32_t lowGuid, Online const& o) const
    {
        return R::EntryOf(lowGuid, o.race, o.sex, AppliedLocked(o));
    }

    bool Marks::ListedLocked(uint32_t lowGuid, Online const& o) const
    {
        return R::Listed(OwnerFeatureLocked(o), EntryLocked(lowGuid, o));
    }

    MarkMe Marks::MarkMeLocked(Online const& o, uint32_t now) const
    {
        R::Choice const applied = AppliedLocked(o);
        MarkMe m;
        m.design = applied.design;
        m.colour = applied.colour;
        m.eye = applied.eye;
        m.priceCopper = R::PriceNow(_cfg, o.stored.changes);
        m.cooldownSec = R::CooldownLeft(_cfg, o.stored.changedAt, now);
        m.changes = o.stored.changes;
        m.offered = _cat.Find(o.race, o.sex) != nullptr;
        return m;
    }

    void Marks::QueueDelta(uint32_t lowGuid, bool login)
    {
        auto [it, inserted] = _deltas.emplace(lowGuid, login);
        if (!inserted)
            it->second = it->second && login;
    }

    void Marks::OnLogin(Player* player)
    {
        if (!player)
            return;
        std::lock_guard<std::mutex> guard(_lock);
        uint32_t const low = Low(player);
        _online.erase(low);   // race, sex and class as the character logs in now; the row read again
        Online const& o = OnlineOf(player);
        // everyone else sees the newcomer's marks; the newcomer gets the full list after HELLO
        if (ListedLocked(low, o))
            QueueDelta(low, true);
    }

    void Marks::OnLogout(Player* player)
    {
        if (!player)
            return;
        std::lock_guard<std::mutex> guard(_lock);
        uint32_t const low = Low(player);
        auto it = _online.find(low);
        if (it == _online.end())
            return;
        if (ListedLocked(low, it->second))
        {
            QueueDelta(low, false);
            _gone[low] = { it->second.race, it->second.sex };   // the removal record names the body it had
        }
        _online.erase(it);
    }

    void Marks::OnDeleteCharacter(uint32_t lowGuid)
    {
        if (!lowGuid)
            return;
        std::lock_guard<std::mutex> guard(_lock);
        if (!_startupDone)
        {
            // the purge of old deleted characters runs before OnStartup (World.cpp): the table may be new
            EnsureTables();
            CharacterDatabase.DirectExecute("DELETE FROM `bleakhold_marks` WHERE `guid` = {}", lowGuid);
            return;
        }
        CharacterDatabase.Execute("DELETE FROM `bleakhold_marks` WHERE `guid` = {}", lowGuid);
        _online.erase(lowGuid);
    }

    // =============================================================================================================
    // Messages
    // =============================================================================================================
    void Marks::SendMarkMe(Player* player)
    {
        if (!FeatureFor(player))
            return;
        MarkMe m;
        {
            std::lock_guard<std::mutex> guard(_lock);
            m = MarkMeLocked(OnlineOf(player), NowSec());
        }
        Ui::SendMarkMe(player, m);
    }

    void Marks::SendList(Player* player)
    {
        if (!FeatureFor(player))
            return;
        MarksList list;
        uint32_t maxEntries = 0;
        {
            std::lock_guard<std::mutex> guard(_lock);
            Online& me = OnlineOf(player);
            me.listId = me.listId >= static_cast<uint32_t>(Proto::Int32Max) ? 1 : me.listId + 1;
            list.listId = me.listId;
            for (auto const& [low, o] : _online)
                if (ListedLocked(low, o))
                    list.entries.push_back(EntryLocked(low, o));
            maxEntries = _cfg.maxListEntries;
        }
        if (std::size_t const left = Ui::SendMarksList(player, list, maxEntries))
            LOG_INFO("module", "[Bleakhold] Glowing marks: the list for {} left out {} of {} entries "
                "(BleakholdUi.Marks.MaxListEntries {})", player->GetName(), left, list.entries.size(), maxEntries);
    }

    void Marks::OnHello(Player* player)
    {
        if (!FeatureFor(player))
            return;
        SendMarkMe(player);
        SendList(player);
    }

    void Marks::Provide(Player* player, TopicRequest const& request)
    {
        // nothing while the bit is off for the player (Mgr::Dispatch skips these topics too)
        if (!FeatureFor(player))
            return;
        if (request.topic == Topic::MarksMe)
            SendMarkMe(player);
        else if (request.topic == Topic::MarksList)
            SendList(player);
    }

    // =============================================================================================================
    // MARKSET
    // =============================================================================================================
    void Marks::Save(Player* player, uint32_t lowGuid, R::Stored const& row, uint32_t price)
    {
        CharacterDatabaseTransaction t = CharacterDatabase.BeginTransaction();
        if (price)
            player->SaveGoldToDB(t);
        t->Append("INSERT INTO `bleakhold_marks` (`guid`, `design`, `colour`, `eye`, `changes`, `changed_at`, `paid_total`) "
            "VALUES ({}, {}, {}, {}, {}, {}, {}) ON DUPLICATE KEY UPDATE `design` = VALUES(`design`), `colour` = "
            "VALUES(`colour`), `eye` = VALUES(`eye`), `changes` = VALUES(`changes`), `changed_at` = VALUES(`changed_at`), "
            "`paid_total` = VALUES(`paid_total`)", lowGuid, uint32_t(row.choice.design), uint32_t(row.choice.colour),
            uint32_t(row.choice.eye), row.changes, row.changedAt, row.paidTotal);
        CharacterDatabase.CommitTransaction(t);
    }

    void Marks::HandleSet(Player* player, Intent const& intent)
    {
        if (!player)
            return;
        uint32_t const low = Low(player);
        R::SetInput in;
        in.feature = FeatureFor(player);
        in.alive = player->IsAlive();
        in.inCombat = player->IsInCombat();
        in.wanted = R::Choice{ intent.markDesign, intent.markColour, intent.markEye };
        in.maxCopper = intent.maxCopper;
        in.money = player->GetMoney();
        in.now = NowSec();
        R::SetResult res;
        R::Stored next;
        {
            std::lock_guard<std::mutex> guard(_lock);
            Online const& o = OnlineOf(player);
            in.race = o.race;
            in.sex = o.sex;
            in.classId = o.classId;
            in.stored = o.stored.choice;
            in.changes = o.stored.changes;
            in.changedAt = o.stored.changedAt;
            res = R::CheckSet(_cat, _cfg, in);
            if (res.verdict == R::Verdict::Ok)
                next = R::Accept(o.stored, in.wanted, res.price, in.now);
        }
        if (res.verdict != R::Verdict::Ok)
        {
            Refusal const refusal = R::RefusalOf(res.verdict);
            if (res.verdict == R::Verdict::Cooldown)
                Ui::Refuse(player, intent, refusal.code, R::CooldownText(res.cooldownSec));
            else
                Ui::Refuse(player, intent, refusal);
            if (R::MarkMeFollows(res.verdict))
                SendMarkMe(player);
            return;
        }
        // the money (checked above) leaves the purse; the purse and the row are saved together
        if (res.price && !player->ModifyMoney(-static_cast<int32_t>(res.price), false))
        {
            Ui::Refuse(player, intent, MarksErr::Failed);
            return;
        }
        Save(player, low, next, res.price);
        {
            std::lock_guard<std::mutex> guard(_lock);
            OnlineOf(player).stored = next;
            QueueDelta(low, false);
        }
        if (Mgr::Instance().Debug())
            DebugLog("glowing marks: " + player->GetName() + " now " + std::to_string(next.choice.design) + "," +
                std::to_string(next.choice.colour) + "," + std::to_string(next.choice.eye) + " for " +
                std::to_string(res.price) + "c (change " + std::to_string(next.changes) + ")");
        SendMarkMe(player);
    }

    // =============================================================================================================
    // The tick: the deltas of this tick go out together; a changed configuration or catalogue sends new lists
    // =============================================================================================================
    void Marks::Update(uint64_t /*nowMs*/)
    {
        std::vector<MarkEntry> entries;
        std::vector<uint32_t> logins;
        bool resend = false;
        bool hello = false;
        {
            std::lock_guard<std::mutex> guard(_lock);
            if (_deltas.empty() && !_resendPending)
                return;
            for (auto const& [low, login] : _deltas)
            {
                auto it = _online.find(low);
                if (it != _online.end() && ListedLocked(low, it->second))
                    entries.push_back(EntryLocked(low, it->second));
                else
                {
                    // a removal: design, colour and eye 0, with the body the player had (or has)
                    MarkEntry e;
                    e.guid = low;
                    auto gone = _gone.find(low);
                    if (it != _online.end())
                        e = R::EntryOf(low, it->second.race, it->second.sex, R::Choice{});
                    else if (gone != _gone.end())
                        e = R::EntryOf(low, gone->second.first, gone->second.second, R::Choice{});
                    if (MarkEntryValid(e))
                        entries.push_back(e);
                }
                if (login)
                    logins.push_back(low);
            }
            _deltas.clear();
            _gone.clear();
            resend = _resendPending;
            hello = _helloPending;
            _resendPending = _helloPending = false;
        }

        if (!entries.empty())
        {
            std::sort(entries.begin(), entries.end(), [](MarkEntry const& a, MarkEntry const& b) { return a.guid < b.guid; });
            Mgr::Instance().ForEachReadyPlayer([&](Player* p) {
                if (!FeatureFor(p))
                    return;
                uint32_t const me = Low(p);
                // the one logging in gets the full list after HELLO, not their own login record
                if (std::find(logins.begin(), logins.end(), me) == logins.end())
                {
                    Ui::SendMarks(p, entries);
                    return;
                }
                std::vector<MarkEntry> others;
                for (MarkEntry const& e : entries)
                    if (e.guid != me)
                        others.push_back(e);
                Ui::SendMarks(p, others);
            });
        }

        if (resend)
        {
            // the HELLO first (its bit), then MARKME and the list: the timers run in the order they were added
            if (hello)
                Mgr::Instance().RefreshHello();
            Mgr::Instance().After(0, []() {
                Mgr::Instance().ForEachReadyPlayer([](Player* p) { Marks::Instance().OnHello(p); });
            });
        }
    }

    Marks::Status Marks::GetStatus()
    {
        std::lock_guard<std::mutex> guard(_lock);
        Status s;
        s.enable = _cfg.enable;
        s.gmOnly = _cfg.gmOnly;
        s.offered = _cat.Offered();
        s.rows = _cat.rows;
        s.goodRows = _cat.goodRows;
        s.online = _online.size();
        for (auto const& [low, o] : _online)
            if (ListedLocked(low, o))
                ++s.listed;
        return s;
    }
}
