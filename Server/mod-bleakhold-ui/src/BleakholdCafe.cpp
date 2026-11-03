/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The cafe (section 21): configuration, startup, the tick, shifts, steps, orders, rewards, the Rush, the danger pause,
 * the protocol handlers and providers, gossip and the hooks. See BleakholdCafe.h for the threads.
 *
 * Lock order: the Mgr lock is never held when this file runs (handlers, providers and the tick are called without it);
 * _eventLock and _snapLock are leaf locks, and nothing is sent while one of them is held.
 */

#include "BleakholdCafe.h"
#include "BleakholdData.h"
#include "BleakholdMgr.h"
#include "BleakholdUi.h"

#include "BattlefieldMgr.h"
#include "Chat.h"
#include "Config.h"
#include "Creature.h"
#include "DBCStores.h"
#include "GameObject.h"
#include "GameTime.h"
#include "Item.h"
#include "Log.h"
#include "Map.h"
#include "MapMgr.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Random.h"
#include "ScriptedGossip.h"
#include "SharedDefines.h"
#include "Spell.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "World.h"
#include "WorldSession.h"
#include "WorldSessionMgr.h"

#include <algorithm>
#include <cmath>
#include <ctime>

namespace Bleakhold
{
    namespace D = CafeData;
    namespace R = CafeRules;

    namespace
    {
        uint64_t Raw(Player const* p) { return p->GetGUID().GetRawValue(); }
        uint32_t Low(Player const* p) { return p->GetGUID().GetCounter(); }

        // A step spell is cosmetic: never instant (no TRIGGERED_CAST_DIRECTLY), no cooldown, cost or facing change.
        constexpr TriggerCastFlags StepCastFlags = TriggerCastFlags(TRIGGERED_IGNORE_GCD |
            TRIGGERED_IGNORE_SPELL_AND_CATEGORY_CD | TRIGGERED_IGNORE_POWER_AND_REAGENT_COST |
            TRIGGERED_IGNORE_SET_FACING | TRIGGERED_DONT_REPORT_CAST_ERROR);

        constexpr uint64_t SecondMs = 1000;
        constexpr uint64_t PeriodCheckMs = 10000;
        constexpr uint64_t BuffResyncMs = 60000;
        constexpr uint64_t QueueMinGapMs = 500;
        constexpr uint64_t NpcCupWaitMs = 120000;     // an NPC that never takes its cup is dropped then
        constexpr uint64_t BaristaForgetMs = 600000;  // a barista row is kept this long after a logout
        constexpr float AtBarRadius = 30.0f;
        constexpr float IdleLineRadius = 30.0f;
        constexpr float LevelUpLineRadius = 20.0f;
        constexpr uint32_t StaffLineGapMs = 60000;
        constexpr uint32_t StaffDrinkMin = 30;        // the Staff Drink's buff, minutes
        constexpr uint32_t StaffDrinkLevel = 7;
        constexpr uint32_t StaffDrinkShiftDrinks = 10;
        constexpr uint32_t MemoryLevel = 6;
        constexpr uint32_t FlagTutorialDone = 32;     // bleakhold_cafe_barista.flags

        // every player on a map (the world thread: the map threads are done); `fn` returns false to stop
        template <typename Fn>
        void ForPlayersOn(Map* map, Fn&& fn)
        {
            if (!map)
                return;
            Map::PlayerList const& players = map->GetPlayers();
            for (Map::PlayerList::const_iterator itr = players.begin(); itr != players.end(); ++itr)
                if (Player* p = itr->GetSource())
                    if (!fn(p))
                        return;
        }

        bool IsStepSpell(uint32_t spellId)
        {
            return spellId > D::SpellStepBase && spellId <= D::SpellStepBase + D::Actions.size();
        }

        int32_t LocalUtcOffsetSec()
        {
            std::time_t const now = std::time(nullptr);
            std::tm local{};
            std::tm utc{};
#ifdef _WIN32
            localtime_s(&local, &now);
            gmtime_s(&utc, &now);
#else
            localtime_r(&now, &local);
            gmtime_r(&now, &utc);
#endif
            utc.tm_isdst = local.tm_isdst;
            return static_cast<int32_t>(std::difftime(std::mktime(&local), std::mktime(&utc)));
        }

        std::string Copper(uint32_t c)
        {
            std::string out;
            if (c >= 10000)
                out += std::to_string(c / 10000) + "g ";
            if (c >= 100)
                out += std::to_string(c / 100 % 100) + "s ";
            out += std::to_string(c % 100) + "c";
            return out;
        }

        // config readers: a value outside its range is logged and replaced by the default
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

        float F32(char const* key, float def, float lo, float hi)
        {
            float const v = sConfigMgr->GetOption<float>(key, def);
            if (!std::isfinite(v) || v < lo || v > hi)
            {
                LOG_ERROR("module", "[Bleakhold] {} = {} is outside {}..{}; using default {}", key, v, lo, hi, def);
                return def;
            }
            return v;
        }

        std::vector<uint32_t> IdList(char const* key, char const* def)
        {
            return R::ParseIds(sConfigMgr->GetOption<std::string>(key, def));
        }

        D::Cafe const& CafeInfo(uint8_t id) { return D::Cafes[id == 2 ? 1 : 0]; }

        std::string StationText(char station)
        {
            D::Station const* s = D::FindStation(station);
            return "Walk to the " + std::string(s ? s->name : "right station") + " first.";
        }

        bool OwnRecipe(uint8_t cafeId, uint16_t recipeId)
        {
            D::Recipe const* r = D::FindRecipe(recipeId);
            return r && r->cafeId == cafeId;
        }

        uint32_t FamilySpell(D::Cafe const& c, char family)
        {
            switch (family)
            {
                case 'C': return c.buffCoffee;
                case 'T': return c.buffTea;
                default: return c.buffShake;
            }
        }
    }

    Cafe& Cafe::Instance()
    {
        static Cafe instance;
        return instance;
    }

    bool Cafe::IsCafeIntent(IntentType type)
    {
        switch (type)
        {
            case IntentType::CafeShift:
            case IntentType::CafeTake:
            case IntentType::CafeStep:
            case IntentType::CafeRelease:
            case IntentType::CafeOrder:
            case IntentType::CafeCancel:
            case IntentType::CafeStaff:
                return true;
            default:
                return false;
        }
    }

    bool Cafe::IsCafeTopic(Topic topic)
    {
        switch (topic)
        {
            case Topic::CafeList:
            case Topic::CafeState:
            case Topic::CafeQueue:
            case Topic::CafeTickets:
            case Topic::CafeMenu:
            case Topic::CafeOrderState:
            case Topic::CafeProfile:
            case Topic::CafeBuffs:
                return true;
            default:
                return false;
        }
    }

    bool Cafe::FeatureFor(Player* player) const
    {
        if (!player || !Enabled())
            return false;
        if (!_gmOnly.load())
            return true;
        WorldSession* session = player->GetSession();
        return session && session->GetSecurity() >= SEC_GAMEMASTER;
    }

    // =============================================================================================================
    // Configuration and lifecycle
    // =============================================================================================================
    void Cafe::LoadConfig()
    {
        CafeConfig c;
        c.enable = sConfigMgr->GetOption<bool>("BleakholdUi.Cafe.Enable", false);
        c.useNewArt = sConfigMgr->GetOption<bool>("BleakholdUi.Cafe.UseNewArt", false);
        c.gmOnly = sConfigMgr->GetOption<bool>("BleakholdUi.Cafe.GmOnly", true);
        c.minLevel = U32("BleakholdUi.Cafe.MinLevel", 10, 1, 80);
        c.shiftRadius = F32("BleakholdUi.Cafe.ShiftRadius", 30.0f, 10.0f, 60.0f);
        c.leaveWarnSec = U32("BleakholdUi.Cafe.LeaveWarnSec", 10, 1, 60);
        c.stationRadius = F32("BleakholdUi.Cafe.StationRadius", 1.5f, 0.8f, 3.0f);
        c.stationLeaveRadius = F32("BleakholdUi.Cafe.StationLeaveRadius", 2.0f, 0.8f, 6.0f);
        if (c.stationLeaveRadius < c.stationRadius)
        {
            LOG_ERROR("module", "[Bleakhold] BleakholdUi.Cafe.StationLeaveRadius must be at least StationRadius; using {}",
                c.stationRadius);
            c.stationLeaveRadius = c.stationRadius;
        }
        c.stationArcDeg = F32("BleakholdUi.Cafe.StationArcDeg", 120.0f, 30.0f, 360.0f);
        c.tickMs = U32("BleakholdUi.Cafe.TickMs", 250, 100, 1000);
        c.stateGapMs = U32("BleakholdUi.Cafe.StateGapMs", 250, 100, 2000);
        c.idleTicketSec = U32("BleakholdUi.Cafe.IdleTicketSec", 120, 10, 3600);
        c.idleSec = U32("BleakholdUi.Cafe.IdleSec", 300, 10, 3600);
        c.maxBaristasPerIp = U32("BleakholdUi.Cafe.MaxBaristasPerIp", 2, 1, 10);
        c.maxBaristas = U32("BleakholdUi.Cafe.MaxBaristas", 4, 1, 8);
        c.warnSec = U32("BleakholdUi.Cafe.WarnSec", 5, 1, 30);
        c.latencyCompMaxMs = U32("BleakholdUi.Cafe.LatencyCompMaxMs", 400, 100, 1000);
        c.releaseSlackMs = U32("BleakholdUi.Cafe.ReleaseSlackMs", 150, 0, 400);
        c.goodPadPermille = U32("BleakholdUi.Cafe.GoodPadPermille", 100, 0, 300);
        c.goldShiftPermille = U32("BleakholdUi.Cafe.GoldShiftPermille", 50, 0, 150);

        c.customers = sConfigMgr->GetOption<bool>("BleakholdUi.Cafe.Customer.Enable", true);
        c.queueCap = U32("BleakholdUi.Cafe.Customer.QueueCap", 6, 1, 8);
        c.rushQueueCap = U32("BleakholdUi.Cafe.Customer.RushQueueCap", 8, 1, 8);
        c.nearPlayerRadius = F32("BleakholdUi.Cafe.Customer.NearPlayerRadius", 60.0f, 10.0f, 200.0f);
        c.queuePatienceSec = U32("BleakholdUi.Cafe.Customer.QueuePatienceSec", 60, 10, 600);
        c.drinkPatienceSec = U32("BleakholdUi.Cafe.Customer.DrinkPatienceSec", 30, 5, 600);
        c.perLineSec = U32("BleakholdUi.Cafe.Customer.PerLineSec", 6, 0, 60);

        c.orders = sConfigMgr->GetOption<bool>("BleakholdUi.Cafe.Order.Enable", true);
        c.maxOrdersPerDay = U32("BleakholdUi.Cafe.Order.MaxPerDay", 12, 1, 255);
        c.orderRadius = F32("BleakholdUi.Cafe.Order.OrderRadius", 40.0f, 5.0f, 200.0f);
        c.takeTimeoutSec = U32("BleakholdUi.Cafe.Order.TakeTimeoutSec", 25, 5, 600);
        c.maxPendingPerCafe = U32("BleakholdUi.Cafe.Order.MaxPendingPerCafe", 6, 1, 20);
        c.maxRuins = U32("BleakholdUi.Cafe.Order.MaxRuins", 2, 1, 5);
        U32("BleakholdUi.Cafe.Order.HouseWorkers", 2, 1, 2);   // read by the crowd; checked here for the log
        c.houseBaseSec = U32("BleakholdUi.Cafe.Order.HouseBaseSec", 30, 0, 600);
        c.housePerLineSec = U32("BleakholdUi.Cafe.Order.HousePerLineSec", 5, 0, 120);
        c.pickupRadius = F32("BleakholdUi.Cafe.Order.PickupRadius", 15.0f, 2.0f, 60.0f);
        c.pickupSec = U32("BleakholdUi.Cafe.Order.PickupSec", 180, 30, 3600);
        c.baristaSharePct = U32("BleakholdUi.Cafe.Order.BaristaSharePct", 60, 0, 100);
        c.pairBoostPerDay = U32("BleakholdUi.Cafe.Order.PairBoostPerDay", 3, 0, 100);
        c.priceMinCopper = U32("BleakholdUi.Cafe.Price.MinCopper", 200, 0, 1000000);
        c.priceLevelFloorPct = U32("BleakholdUi.Cafe.Price.LevelFloorPct", 10, 0, 100);

        c.xpDailyFull = U32("BleakholdUi.Cafe.Xp.DailyFull", 450, 0, 100000);
        c.xpDailyHalf = U32("BleakholdUi.Cafe.Xp.DailyHalf", 450, 0, 100000);
        c.tipDailyBaseCopper = U32("BleakholdUi.Cafe.Tip.DailyBaseCopper", 5000, 0, 100000000);
        c.tipDailyPerLevelCopper = U32("BleakholdUi.Cafe.Tip.DailyPerLevelCopper", 2500, 0, 1000000);
        c.pointsDailyCap = U32("BleakholdUi.Cafe.Points.DailyCap", 400, 0, 100000);
        c.pointsRushExtra = U32("BleakholdUi.Cafe.Points.RushExtra", 100, 0, 100000);
        c.tiredAfterMin = U32("BleakholdUi.Cafe.Tired.AfterMin", 60, 1, 1440);
        c.tiredRestMin = U32("BleakholdUi.Cafe.Tired.RestMin", 15, 1, 1440);
        c.tiredPct = U32("BleakholdUi.Cafe.Tired.Pct", 50, 0, 100);

        c.coffeeXpPct = U32("BleakholdUi.Cafe.Buff.CoffeeXpPct", 5, 0, 100);
        c.teaRepPct = U32("BleakholdUi.Cafe.Buff.TeaRepPct", 5, 0, 100);
        c.teaExcludeFactions = IdList("BleakholdUi.Cafe.Buff.TeaExcludeFactions", "509,510,729,730,889,890");
        c.buffMaxMin = U32("BleakholdUi.Cafe.Buff.MaxMin", 60, 10, 600);

        c.rush = sConfigMgr->GetOption<bool>("BleakholdUi.Cafe.Rush.Enable", true);
        std::string const times = sConfigMgr->GetOption<std::string>("BleakholdUi.Cafe.Rush.Times", "08:00");
        c.rushTimes = R::ParseRushTimes(times);
        if (c.rushTimes.empty() && c.rush)
        {
            LOG_ERROR("module", "[Bleakhold] BleakholdUi.Cafe.Rush.Times \"{}\" has no HH:MM time; using default 08:00", times);
            c.rushTimes = { 8 * 3600 };
        }
        c.rushMinutes = U32("BleakholdUi.Cafe.Rush.Minutes", 20, 1, 240);
        c.rushWarnMinutes = U32("BleakholdUi.Cafe.Rush.WarnMinutes", 5, 0, 120);
        c.rushGoal = U32("BleakholdUi.Cafe.Rush.Goal", 60, 1, 10000);
        c.rushSurvivorMin = U32("BleakholdUi.Cafe.Rush.SurvivorMin", 5, 1, 1000);
        c.rushSurvivorXp = U32("BleakholdUi.Cafe.Rush.SurvivorXp", 50, 0, 10000);

        c.weekly = sConfigMgr->GetOption<bool>("BleakholdUi.Cafe.Weekly.Enable", true);
        c.weeklyMinDrinks = U32("BleakholdUi.Cafe.Weekly.MinDrinks", 50, 0, 100000);
        c.weeklyMinDays = U32("BleakholdUi.Cafe.Weekly.MinDays", 3, 0, 7);
        c.weeklyRewardCopper = IdList("BleakholdUi.Cafe.Weekly.RewardCopper",
            "500000,300000,200000,50000,50000,50000,50000,50000,50000,50000");
        c.titleBaristaId = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Cafe.Title.BaristaId", 190);
        c.titleLegendId = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Cafe.Title.LegendId", 191);
        c.titleLegendWins = U32("BleakholdUi.Cafe.Title.LegendWins", 3, 1, 1000);
        c.dailyResetHour = U32("BleakholdUi.Cafe.DailyResetHour", 6, 0, 23);
        c.weeklyResetWeekday = U32("BleakholdUi.Cafe.WeeklyResetWeekday", 3, 0, 6);

        c.hostileNearRadius = F32("BleakholdUi.Cafe.Close.HostileNearRadius", 15.0f, 0.0f, 100.0f);
        c.hostileRadius = F32("BleakholdUi.Cafe.Close.HostileRadius", 40.0f, 0.0f, 100.0f);
        c.hostileDz = F32("BleakholdUi.Cafe.Close.HostileDz", 5.0f, 0.0f, 100.0f);
        c.confirmSec = U32("BleakholdUi.Cafe.Close.ConfirmSec", 5, 0, 600);
        c.resumeSec = U32("BleakholdUi.Cafe.Close.ResumeSec", 20, 1, 3600);
        c.pauseMaxSec = U32("BleakholdUi.Cafe.Close.PauseMaxSec", 90, 1, 3600);
        c.reopenSec = U32("BleakholdUi.Cafe.Close.ReopenSec", 120, 1, 3600);

        c.botMinDrinks = U32("BleakholdUi.Cafe.Bot.MinDrinks", 200, 1, 100000);
        c.botPerfectPermille = U32("BleakholdUi.Cafe.Bot.PerfectPermille", 980, 0, 1000);
        c.botSdMs = U32("BleakholdUi.Cafe.Bot.SdMs", 30, 0, 10000);
        c.overheadKits = sConfigMgr->GetOption<bool>("BleakholdUi.Cafe.OverheadKits", false);

        bool const gmOnlyChanged = _gmOnly.load() != c.gmOnly;
        _cfg = c;
        _cfgEnable = c.enable;
        _gmOnly = c.gmOnly;
        _coffeePct = c.coffeeXpPct;
        _teaPct = c.teaRepPct;
        _teaExcludedCount = 0;
        std::size_t const n = std::min(c.teaExcludeFactions.size(), MaxExcluded);
        for (std::size_t i = 0; i < n; ++i)
            _teaExcluded[i] = c.teaExcludeFactions[i];
        _teaExcludedCount = static_cast<uint32_t>(n);

        if (!_startupDone)
            return;
        bool const wasOn = Enabled();
        RecomputeEnabled();
        // GmOnly decides the bit per player: a change needs a new HELLO for everyone (SetFeature only sends one on a
        // change of the bit itself). A barista who lost the bit has the shift ended 'O' by the next TickShifts.
        if (gmOnlyChanged && wasOn && Enabled())
            Mgr::Instance().RefreshHello();
    }

    void Cafe::RecomputeEnabled()
    {
        bool const on = _cfg.enable && _startupOk;
        bool const was = _enabled.exchange(on);
        if (was && !on)
        {
            for (CafeRt& c : _cafes)
            {
                ClosePath(c, 'O');
                // ready player orders: settled as at a restart (the house share back, or all of a house-made drink)
                std::vector<uint32_t> ready;
                for (auto const& [id, o] : _orders)
                    if (o.cafeId == c.id && o.kind == 'P' && o.state == 'R')
                        ready.push_back(id);
                for (uint32_t id : ready)
                {
                    Order* o = OrderOf(id);
                    if (!o)
                        continue;
                    R::Money const m = R::SettleOrder(R::StartupEnd('R', o->baristaLow != 0), o->price, o->tip,
                        o->sharePct);
                    RefundOrder(*o, m.refunded, "the cafe turned off");
                    SendOrderState(*o, CafeOrderStateId::Cancelled);
                    if (o->viaGossip)
                        if (Player* cu = ObjectAccessor::FindConnectedPlayer(ObjectGuid(o->customerGuid)))
                            Tell(cu, "The caf\xC3\xA9 has closed; " + Copper(m.refunded) + " of your order were refunded.");
                    DropLeftovers(*o, std::string());
                    RemoveOrder(id);
                }
                if (c.crowdSpawned)
                {
                    CafeCrowd::Instance().OnSiteDespawned(c.id);
                    c.crowdSpawned = false;
                }
                DespawnStaff(c);
                c.open = 0;
                // no TickRush runs while off: a live Rush goes silently, as at a restart (a re-enable inside its window
                // resumes it with the goal scaled down; later, nothing ends and no rivalry line goes out)
                R::RushSilentReset(c.rushState, c.rushWindow);
                c.rushShouts.clear();
            }
            _orders.clear();
            Ui::SetFeature(FeatureCafe, false);
            LOG_INFO("module", "[Bleakhold] Cafe: turned off (BleakholdUi.Cafe.Enable = 0); shifts ended, orders refunded");
        }
        else if (!was && on)
        {
            for (CafeRt& c : _cafes)
            {
                c.open = c.placed && c.enabled ? 1 : 3;
                if (c.placed && c.enabled)
                {
                    SpawnStaff(c);
                    BuildSite(c);
                    CafeCrowd::Instance().OnSiteSpawned(c.site);
                    c.crowdSpawned = true;
                }
            }
            Ui::SetFeature(FeatureCafe, true);
            LOG_INFO("module", "[Bleakhold] Cafe: on ({}{})", _cfg.gmOnly ? "game masters only" : "everyone",
                _cfg.useNewArt && _newArtOk ? ", new art" : ", stand-ins");
            PayMissedWeeks();
        }
        else if (!on && _cfg.enable && !_startupOk)
            LOG_ERROR("module", "[Bleakhold] Cafe: BleakholdUi.Cafe.Enable = 1 but the startup checks failed (see above); "
                "the cafe stays off");
        MarkCafeList();
        UpdateSnapshot();
    }

    bool Cafe::ValidateStartup()
    {
        bool ok = true;
        auto missing = [&](std::string const& what, std::string const& hint) {
            LOG_ERROR("module", "[Bleakhold] Cafe: {} missing: {}", what, hint);
            ok = false;
        };
        // after data/sql/uninstall/cafe_uninstall.sql the module files are applied already: its header says how to
        // reinstall
        std::string const templates = "apply data/sql/db-world/04_bleakhold_cafe_templates.sql (module SQL; after "
            "cafe_uninstall.sql, see its reinstall note)";
        for (D::GameObject const& g : D::GameObjects)
        {
            if (!sObjectMgr->GetGameObjectTemplate(g.entry))
                missing("gameobject_template " + std::to_string(g.entry), templates);
            if (g.standIn && !sObjectMgr->GetGameObjectTemplate(g.standIn))
                missing("gameobject_template " + std::to_string(g.standIn) + " (stand-in)", templates);
        }
        for (D::StaffMember const& s : D::Staff)
            if (!sObjectMgr->GetCreatureTemplate(s.entry))
                missing("creature_template " + std::to_string(s.entry), templates);
        for (D::Persona const& p : D::Personas)
            if (!sObjectMgr->GetCreatureTemplate(p.entry))
                missing("creature_template " + std::to_string(p.entry), templates);
        for (D::Item const& i : D::Items)
            if (!sObjectMgr->GetItemTemplate(i.entry))
                missing("item_template " + std::to_string(i.entry), templates);

        std::string const spells = "the cafe spells come from CafeForge (cafeforge.py sql) on the server (after "
            "cafe_uninstall.sql, see its reinstall note)";
        std::vector<uint32_t> ids{ D::SpellOnShift, D::SpellSprint, D::SpellTired, D::SpellBestBarista };
        for (D::Action const& a : D::Actions)
            ids.push_back(a.spell);
        for (D::Cafe const& c : D::Cafes)
            for (uint32_t s : { c.buffCoffee, c.buffTea, c.buffShake })
                ids.push_back(s);
        for (uint32_t id : ids)
            if (!sSpellMgr->GetSpellInfo(id))
                missing("spell " + std::to_string(id), spells);
        for (uint32_t id : D::NeverSavedSpells)
            if (SpellInfo const* info = sSpellMgr->GetSpellInfo(id); info && !info->HasAttribute(SPELL_ATTR0_CU_AURA_CANNOT_BE_SAVED))
                missing("spell_custom_attr " + std::to_string(id) + " (SPELL_ATTR0_CU_AURA_CANNOT_BE_SAVED)", templates);

        _titlesOk = true;
        for (uint32_t t : { _cfg.titleBaristaId, _cfg.titleLegendId })
            if (t && !sCharTitlesStore.LookupEntry(t))
            {
                LOG_ERROR("module", "[Bleakhold] Cafe: CharTitles {} missing (chartitles_dbc from CafeForge); titles are "
                    "granted at a later login", t);
                _titlesOk = false;
            }

        _newArtOk = true;
        for (D::GameObject const& g : D::GameObjects)
            if (g.standIn && !sGameObjectDisplayInfoStore.LookupEntry(g.display))
                _newArtOk = false;
        if (!_newArtOk && _cfg.useNewArt)
            LOG_ERROR("module", "[Bleakhold] Cafe: GameObjectDisplayInfo {}-{} missing (gameobjectdisplayinfo_dbc from "
                "CafeForge); the cafes use the stand-ins", D::DisplayFirst, D::DisplayLast);
        return ok;
    }

    void Cafe::OnStartup()
    {
        _epochMs = Mgr::NowMs();
        _startSec = NowSec();
        for (std::size_t i = 0; i < _cafes.size(); ++i)
            _cafes[i].id = static_cast<uint8_t>(i + 1);
        CafeCrowd::Instance().SetSink(this);
        EnsureTables();
        _startupOk = ValidateStartup();
        SeedOrderIds();
        SettleLeftoverOrders();
        _dayId = DayId();
        _weekId = WeekId();
        LoadSites();
        LoadLastWinners();
        _startupDone = true;
        RecomputeEnabled();
        // the deploy runbook (bleakserv deploy/README.md, deploy/cafe/build-cafe.sh) greps for this exact text
        LOG_INFO("server.loading", ">> [Bleakhold] Cafe: startup checks {} ({}, {} placed)", _startupOk ? "passed" :
            "FAILED", _cfg.enable ? "enabled" : "off (BleakholdUi.Cafe.Enable = 0)",
            (_cafes[0].placed ? 1 : 0) + (_cafes[1].placed ? 1 : 0));
    }

    void Cafe::OnShutdown()
    {
        if (!_startupDone)
            return;
        for (auto& [low, b] : _baristas)
            SaveBarista(b, true);
    }

    uint32_t Cafe::NowSec() const { return static_cast<uint32_t>(GameTime::GetGameTime().count()); }

    uint32_t Cafe::Random(uint32_t below) { return below ? urand(0, below - 1) : 0; }

    uint32_t Cafe::DayId()
    {
        uint32_t daily = Data::Instance().ResetTimes().first;
        if (!daily)
        {
            if (!_resetFallbackLogged)
                LOG_ERROR("module", "[Bleakhold] Cafe: the realm gives no daily reset; using BleakholdUi.Cafe.DailyResetHour");
            _resetFallbackLogged = true;
            daily = R::FallbackDailyReset(NowSec(), LocalUtcOffsetSec(), _cfg.dailyResetHour);
        }
        return R::PeriodId(daily, R::DaySec);
    }

    uint32_t Cafe::WeekId()
    {
        uint32_t weekly = Data::Instance().ResetTimes().second;
        if (!weekly)
            weekly = R::FallbackWeeklyReset(NowSec(), LocalUtcOffsetSec(), _cfg.dailyResetHour, _cfg.weeklyResetWeekday);
        return R::PeriodId(weekly, R::WeekSec);
    }

    // =============================================================================================================
    // Small helpers
    // =============================================================================================================
    Cafe::CafeRt* Cafe::CafeOf(uint8_t id) { return id >= 1 && id <= _cafes.size() ? &_cafes[id - 1] : nullptr; }
    Cafe::CafeRt const* Cafe::CafeOf(uint8_t id) const { return id >= 1 && id <= _cafes.size() ? &_cafes[id - 1] : nullptr; }

    Cafe::Shift* Cafe::ShiftOf(Player* player) { return player ? ShiftOf(Raw(player)) : nullptr; }

    Cafe::Shift* Cafe::ShiftOf(uint64_t guid)
    {
        auto it = _shifts.find(guid);
        return it == _shifts.end() ? nullptr : &it->second;
    }

    Cafe::Order* Cafe::OrderOf(uint32_t id)
    {
        auto it = _orders.find(id);
        return it == _orders.end() ? nullptr : &it->second;
    }

    Cafe::Order* Cafe::PendingOrderOf(uint32_t lowGuid)
    {
        for (auto& [id, o] : _orders)
            if (o.kind == 'P' && o.customerLow == lowGuid)
                return &o;
        return nullptr;
    }

    Cafe::Ticket* Cafe::TicketOf(Shift& s, uint32_t ticketId)
    {
        for (Ticket& t : s.tickets)
            if (t.id == ticketId)
                return &t;
        return nullptr;
    }

    uint8_t Cafe::TeamCafe(Player* player) const { return player->GetTeamId() == TEAM_ALLIANCE ? 1 : 2; }

    uint8_t Cafe::BaristasAt(uint8_t cafeId) const
    {
        uint8_t n = 0;
        for (auto const& [g, s] : _shifts)
            if (s.cafeId == cafeId)
                ++n;
        return n;
    }

    uint8_t Cafe::MaxBaristaLevelAt(uint8_t cafeId)
    {
        uint8_t best = 0;
        for (auto const& [g, s] : _shifts)
            if (s.cafeId == cafeId)
                if (Barista* b = LoadedBarista(s.low))
                    best = std::max(best, b->level);
        return best;
    }

    bool Cafe::InRange(Player* player, CafeRt const& c, float radius) const
    {
        return player && c.placed && player->IsInWorld() && player->GetMapId() == c.map &&
            player->GetExactDist2d(c.anchor.x, c.anchor.y) <= radius;
    }

    static_assert(R::ShapeshiftFlagStance == static_cast<uint32_t>(SHAPESHIFT_FLAG_STANCE),
        "the rules' stance flag is the core's");

    bool Cafe::Hidden(Player* player) const
    {
        // a warrior's stance is a form too (UNIT_FIELD_BYTES_2 byte 3), but no disguise: only a form without
        // SHAPESHIFT_FLAG_STANCE hides, as for mounting (Unit::IsInDisallowedMountForm)
        bool shifted = false;
        if (ShapeshiftForm const form = player->GetShapeshiftForm())
        {
            SpellShapeshiftFormEntry const* entry = sSpellShapeshiftFormStore.LookupEntry(form);
            shifted = R::FormHides(static_cast<uint8_t>(form), entry != nullptr, entry ? entry->flags1 : 0u);
        }
        return player->IsMounted() || player->GetVehicle() || player->IsInFlight() || shifted ||
            player->HasStealthAura() || player->HasInvisibilityAura();
    }

    bool Cafe::RushLive(uint8_t cafeId) const
    {
        CafeRt const* c = CafeOf(cafeId);
        return c && c->rushState == 2;
    }

    uint8_t Cafe::QueueCap(uint8_t cafeId) const
    {
        return static_cast<uint8_t>(RushLive(cafeId) ? _cfg.rushQueueCap : _cfg.queueCap);
    }

    uint32_t Cafe::QueueLen(uint8_t cafeId) const
    {
        uint32_t n = 0;
        for (auto const& [id, o] : _orders)
            if (o.cafeId == cafeId && o.state == 'W')
                ++n;
        return n;
    }

    uint32_t Cafe::PendingPlayerOrders(uint8_t cafeId) const
    {
        uint32_t n = 0;
        for (auto const& [id, o] : _orders)
            if (o.cafeId == cafeId && o.kind == 'P' && (o.state == 'W' || o.state == 'T' || o.state == 'H'))
                ++n;
        return n;
    }

    void Cafe::Refuse(Player* player, Intent const& intent, Refusal const& r)
    {
        Refuse(player, intent, r.code, r.text);
    }

    void Cafe::Refuse(Player* player, Intent const& intent, std::string_view code, std::string_view text)
    {
        Ui::Refuse(player, intent, code, text);
        if (_tellRefusals)
            Tell(player, std::string(text));
    }

    void Cafe::Tell(Player* player, std::string const& text)
    {
        if (player)
            Mgr::Instance().QueueSystem(player, text);
    }

    std::string Cafe::DrinkName(uint16_t recipeId) const
    {
        D::Recipe const* r = D::FindRecipe(recipeId);
        return r ? std::string(r->name) : std::string("drink");
    }

    // A staff line by key, said by the cafe's staff member of that role (the crowd speaks; Cafe picks the text).
    void Cafe::Say(uint8_t cafeId, std::string_view role, uint32_t entry, std::string_view key, std::string const& fill)
    {
        bool yell = false;
        std::string_view const line = R::StaffLine(entry, key, Random(1000), &yell);
        if (line.empty())
            return;
        std::string text = R::Fill(line, "{drink}", fill);
        text = R::Fill(text, "{n}", fill);
        std::string const r(role);
        CrowdCall([cafeId, r, text, yell]() { CafeCrowd::Instance().StaffSay(cafeId, r, text, yell); });
        if (CafeRt* c = CafeOf(cafeId))
            c->lastStaffLineMs = Mgr::NowMs();
    }

    // The realm-wide [Cafe] lines (the Rush warning, the rivalry, Best Barista of the week). Under GmOnly the cafe is
    // only theirs (section 3.13.1: nobody else sees the bit), so only the players with the bit read them.
    void Cafe::AnnounceCafe(std::string const& text)
    {
        if (!_gmOnly.load())
        {
            Ui::Announce(Ui::AnnounceTag::Cafe, text);
            return;
        }
        for (auto const& [id, session] : sWorldSessionMgr->GetAllSessions())
            if (Player* p = session ? session->GetPlayer() : nullptr; p && p->IsInWorld() && FeatureFor(p))
                Ui::AnnounceTo(p, Ui::AnnounceTag::Cafe, text);
    }

    // A call into the crowd: made at once, or after CafeCrowd::Update when it comes from one of the crowd's own callbacks
    // (CrowdSink), so the crowd never changes its customers while it walks them.
    void Cafe::CrowdCall(std::function<void()> call)
    {
        if (_inCrowdUpdate)
            _crowdCalls.push_back(std::move(call));
        else
            call();
    }

    // =============================================================================================================
    // The tick (section 3.2.4)
    // =============================================================================================================
    void Cafe::Update(uint64_t nowMs)
    {
        if (!_startupDone)
            return;
        if (_lastTickMs && nowMs - _lastTickMs < _cfg.tickMs)
            return;
        uint64_t const dt = _lastTickMs ? nowMs - _lastTickMs : 0;
        _lastTickMs = nowMs;

        DrainEvents(nowMs);
        bool const on = Enabled();
        if (on)
        {
            for (CafeRt& c : _cafes)
                if (c.open == 2)
                    FreezeFor(c, dt);
            TickShifts(nowMs);
            TickSteps(nowMs);
            TickOrders(nowMs);
            TickCafes(nowMs);
            TickCrowd(nowMs);
        }
        if (nowMs - _lastSecondMs >= SecondMs)
        {
            _lastSecondMs = nowMs;
            TickAuras(nowMs);
        }
        if (on)
            FlushViews(nowMs);
        FlushDb(nowMs, false);
        for (auto it = _guardChecks.begin(); it != _guardChecks.end();)
        {
            if (nowMs < it->atMs)
            {
                ++it;
                continue;
            }
            GuardCheck const check = *it;
            it = _guardChecks.erase(it);
            // more than one world database worker may have run the .gobject / .npc save after our delete: delete again
            std::string_view const table = check.creature ? "creature" : "gameobject";
            if (WorldDatabase.Query("SELECT 1 FROM `{}` WHERE `guid` = {}", table, check.spawnId))
            {
                WorldDatabaseTransaction t = WorldDatabase.BeginTransaction();
                t->Append("DELETE FROM `{}` WHERE `guid` = {}", table, check.spawnId);
                t->Append("DELETE FROM `{}_addon` WHERE `guid` = {}", table, check.spawnId);
                WorldDatabase.CommitTransaction(t);
                LOG_INFO("module", "[Bleakhold] Cafe: the {} row {} of a cafe spawn was back; deleted again", table,
                    check.spawnId);
            }
        }
        UpdateSnapshot();
    }

    // A danger pause freezes the cafe's clocks: every end time moves by the time paused.
    void Cafe::FreezeFor(CafeRt& c, uint64_t dtMs)
    {
        if (!dtMs)
            return;
        for (auto& [id, o] : _orders)
        {
            if (o.cafeId != c.id)
                continue;
            if (o.patienceEndMs)
                o.patienceEndMs += dtMs;
            if (o.takeDeadlineMs)
                o.takeDeadlineMs += dtMs;
        }
        for (auto& [g, s] : _shifts)
            if (s.cafeId == c.id)
                s.lastActionMs += dtMs;
        if (c.rushState == 2)
            c.rushEndMs += dtMs;
    }

    void Cafe::DrainEvents(uint64_t nowMs)
    {
        std::vector<Event> events;
        {
            std::lock_guard<std::mutex> guard(_eventLock);
            events.swap(_events);
        }
        for (Event const& e : events)
        {
            switch (e.kind)
            {
                case Event::Kind::Combat:
                {
                    Player* p = ObjectAccessor::FindPlayerByLowGUID(e.a);
                    if (Shift* s = p ? ShiftOf(p) : nullptr)
                        EndShift(*s, static_cast<char>(CafeShiftEnd::Combat), nowMs);
                    break;
                }
                case Event::Kind::SpellCancel:
                {
                    Player* p = ObjectAccessor::FindPlayerByLowGUID(e.a);
                    Shift* s = p ? ShiftOf(p) : nullptr;
                    if (!s)
                        break;
                    for (Ticket& t : s->tickets)
                    {
                        if (!t.step.active || t.step.expectCancel || D::SpellStepBase + t.step.action != e.b)
                            continue;
                        // the core cancelled the step's spell (movement, an interrupt): the step stops, no penalty
                        AbortStep(p, *s, t, false);
                    }
                    break;
                }
                case Event::Kind::GoSaved:
                    GuardSavedGo(e.a);
                    break;
                case Event::Kind::CreatureSaved:
                    GuardSavedCreature(e.a, e.b);
                    break;
                case Event::Kind::ShiftOffered:
                {
                    // the owner offers an apron to a player who opened her gossip, at most one staff line a minute
                    CafeRt* c = CafeOf(static_cast<uint8_t>(e.a));
                    Player* p = ObjectAccessor::FindPlayerByLowGUID(e.b);
                    if (c && p && Enabled() && c->open == 1 && !ShiftOf(p) &&
                        nowMs - c->lastStaffLineMs >= StaffLineGapMs)
                        Say(c->id, "staff_owner", CafeInfo(c->id).owner, "shiftOffered");
                    break;
                }
            }
        }
    }

    // =============================================================================================================
    // Shifts (section 3.4.1)
    // =============================================================================================================
    std::vector<R::SpotRef> Cafe::SpotsOf(CafeRt const& c) const
    {
        std::vector<R::SpotRef> out;
        for (StationSpots const& st : c.site.stations)
        {
            if (!st.station)
                continue;
            for (uint8_t i = 0; i < st.spots.size(); ++i)
                out.push_back({ st.station, i, st.spots[i].GetPositionX(), st.spots[i].GetPositionY(),
                    st.spots[i].GetPositionZ(), st.objX, st.objY });
        }
        return out;
    }

    void Cafe::UpdateStation(Player* player, Shift& s, uint64_t nowMs)
    {
        CafeRt const* c = CafeOf(s.cafeId);
        if (!c)
            return;
        R::StationHit const h = R::StationAt(player->GetPositionX(), player->GetPositionY(), player->GetPositionZ(),
            player->GetOrientation(), SpotsOf(*c), _cfg.stationRadius, _cfg.stationArcDeg);
        uint16_t const dm = static_cast<uint16_t>(R::NearDm(h.nearDist));
        bool const changed = h.station != s.station || h.facingHint != s.facingHint || h.nearStation != s.nearStation ||
            std::abs(int(dm) - int(s.nearDm)) >= 10;
        s.station = h.station;
        s.spot = h.spot;
        s.facingHint = h.facingHint;
        s.nearStation = h.nearStation;
        if (changed)
        {
            s.nearDm = dm;
            MarkView(s.guid, VState);
        }
        // a running step stops when the barista walks away from the spot it started on (turning is fine)
        for (Ticket& t : s.tickets)
            if (t.step.active && std::hypot(player->GetPositionX() - t.step.spotX, player->GetPositionY() - t.step.spotY) >
                _cfg.stationLeaveRadius)
                AbortStep(player, s, t, true);
        (void)nowMs;
    }

    void Cafe::TickShifts(uint64_t nowMs)
    {
        std::vector<std::pair<uint64_t, char>> ends;
        R::ShiftLimits l;
        l.warnMs = _cfg.warnSec * 1000;
        l.radius = _cfg.shiftRadius;
        l.leaveWarnMs = _cfg.leaveWarnSec * 1000;
        l.idleTicketMs = _cfg.idleTicketSec * 1000;
        l.idleMs = _cfg.idleSec * 1000;
        for (auto& [guid, s] : _shifts)
        {
            Player* p = ObjectAccessor::FindConnectedPlayer(ObjectGuid(guid));
            CafeRt* c = CafeOf(s.cafeId);
            if (!p || !p->IsInWorld())
            {
                ends.emplace_back(guid, static_cast<char>(CafeShiftEnd::Died));
                continue;
            }
            if (!c || !c->placed || c->open == 4 || c->open == 3)
            {
                ends.emplace_back(guid, static_cast<char>(CafeShiftEnd::Closed));
                continue;
            }
            R::ShiftFacts f;
            f.feature = FeatureFor(p);
            f.alive = p->IsAlive();
            f.inCombat = p->IsInCombat();
            f.hidden = Hidden(p);
            f.afk = p->isAFK();
            f.sameMap = p->GetMapId() == c->map;
            f.anchorDist = p->GetExactDist2d(c->anchor.x, c->anchor.y);
            f.holdsTicket = !s.tickets.empty();
            f.lastActionMs = s.lastActionMs;
            R::ShiftVerdict const v = R::ShiftTick(f, s.timers, nowMs, l);
            if (v.end)
            {
                ends.emplace_back(guid, v.end);
                continue;
            }
            if (v.flags != s.warnFlags || v.warnSec != s.warnSec)
            {
                s.warnFlags = v.flags;
                s.warnSec = v.warnSec;
                MarkView(guid, VState);
            }
            UpdateStation(p, s, nowMs);
            // the core clears a loop emote on every movement or turning packet: set it again while standing still
            for (Ticket const& t : s.tickets)
                if (t.step.active && t.step.emoteState && !p->isMoving() &&
                    p->GetUInt32Value(UNIT_NPC_EMOTESTATE) != t.step.emoteState)
                    p->SetEmoteState(Emote(t.step.emoteState));
            // Tired: the time on shift is kept in the barista row
            if (nowMs - s.lastTiredMs >= SecondMs)
            {
                uint32_t const sec = static_cast<uint32_t>((nowMs - s.lastTiredMs) / 1000);
                s.lastTiredMs += uint64_t(sec) * 1000;
                if (Barista* b = LoadedBarista(s.low))
                {
                    bool const before = R::IsTired(b->tired, NowSec(), _cfg.tiredAfterMin, _cfg.tiredRestMin);
                    b->tired.accumSec += sec;
                    b->dirty = true;
                    if (R::IsTired(b->tired, NowSec(), _cfg.tiredAfterMin, _cfg.tiredRestMin) != before)
                        MarkView(guid, VState);
                }
            }
        }
        for (auto const& [g, reason] : ends)
            if (Shift* s = ShiftOf(g))
                EndShift(*s, reason, nowMs);
    }

    std::optional<Refusal> Cafe::ShiftCheck(Player* player, uint8_t cafeId, std::string& text)
    {
        CafeRt* c = CafeOf(cafeId);
        text.clear();
        if (!c || !c->placed || !Enabled())
            return CafeErr::Closed;
        if (c->open == 2)
            return CafeErr::Paused;
        if (c->open != 1)
            return CafeErr::Closed;
        // section 2.11, in its order
        if (player->GetLevel() < _cfg.minLevel)
        {
            text = "You need level " + std::to_string(_cfg.minLevel) + " to work a shift.";
            return CafeErr::Level;
        }
        if (!InRange(player, *c, _cfg.shiftRadius))
            return CafeErr::Where;
        if (!player->IsAlive())
            return CafeErr::Dead;
        if (player->IsInCombat())
            return CafeErr::Combat;
        if (Hidden(player))
            return CafeErr::Mounted;
        if (player->isAFK())
            return CafeErr::Afk;
        if (TeamCafe(player) != cafeId)
            return CafeErr::Faction;
        WorldSession* session = player->GetSession();
        uint32_t const account = session ? session->GetAccountId() : 0;
        std::string const ip = session ? session->GetRemoteAddress() : std::string();
        uint32_t sameIp = 0;
        for (auto const& [g, s] : _shifts)
        {
            if (s.account == account)
                return CafeErr::Account;
            if (s.cafeId == cafeId && !ip.empty() && s.ip == ip)
                ++sameIp;
        }
        if (sameIp >= _cfg.maxBaristasPerIp)
            return CafeErr::Account;
        if (PendingOrderOf(Low(player)))
            return CafeErr::Order;
        if (BaristasAt(cafeId) >= _cfg.maxBaristas)
            return CafeErr::BarFull;
        return std::nullopt;
    }

    bool Cafe::StartShift(Player* player, uint8_t cafeId, Intent const* intent)
    {
        std::string text;
        if (std::optional<Refusal> r = ShiftCheck(player, cafeId, text))
        {
            std::string const sentence = text.empty() ? std::string(r->text) : text;
            if (intent)
                Refuse(player, *intent, r->code, sentence);
            else
            {
                Tell(player, sentence);
                Intent fake;
                fake.type = IntentType::CafeShift;
                Ui::Refuse(player, fake, r->code, sentence);
            }
            return false;
        }
        uint64_t const now = Mgr::NowMs();
        Barista& b = BaristaOf(player);
        b.tired = R::TiredOnShiftStart(b.tired, NowSec(), _cfg.tiredRestMin);
        b.dirty = true;
        b.staffOffer = false;
        Shift s;
        s.guid = Raw(player);
        s.low = Low(player);
        WorldSession* session = player->GetSession();
        s.account = session ? session->GetAccountId() : 0;
        s.ip = session ? session->GetRemoteAddress() : std::string();
        s.name = player->GetName();
        s.cafeId = cafeId;
        s.startSec = NowSec();
        s.startMs = now;
        s.lastActionMs = now;
        s.lastTiredMs = now;
        _shifts[s.guid] = s;
        player->AddAura(D::SpellOnShift, player);
        player->SetSheath(SHEATH_STATE_UNARMED);
        UpdateStation(player, _shifts[s.guid], now);
        MarkView(s.guid, VState | VQueue | VTickets);
        MarkCafeList();
        D::Cafe const& cd = CafeInfo(cafeId);
        Say(cafeId, "staff_owner", cd.owner, "shiftStart");
        LOG_INFO("module", "[Bleakhold] Cafe: {} starts a shift at {} (barista level {})", s.name, cd.name, b.level);
        return true;
    }

    void Cafe::ReturnTickets(Shift& s, uint64_t nowMs)
    {
        CafeRt* c = CafeOf(s.cafeId);
        for (Ticket& t : s.tickets)
        {
            Order* o = OrderOf(t.orderId);
            if (!o || !c)
                continue;
            o->state = 'W';
            o->baristaGuid = 0;
            o->baristaLow = 0;
            o->baristaName.clear();
            o->ticketId = 0;
            o->returned = true;
            Unqueue(*o);
            QueueOrder(*c, *o, true);
            if (o->kind == 'P')
            {
                // a player order gets a new take timer, and the house takes it after that
                o->takeDeadlineMs = nowMs + uint64_t(_cfg.takeTimeoutSec) * 1000;
                SaveOrderState(*o);
                SendOrderState(*o);
            }
            else
            {
                uint32_t const id = o->id;
                CrowdCall([id]() { CafeCrowd::Instance().OrderReturned(id); });
            }
        }
        s.tickets.clear();
        MarkCafeBaristas(s.cafeId, VQueue);
    }

    void Cafe::EndShift(Shift& s, char reason, uint64_t nowMs)
    {
        Player* p = ObjectAccessor::FindConnectedPlayer(ObjectGuid(s.guid));
        for (Ticket& t : s.tickets)
            if (t.step.active)
                AbortStep(p, s, t, p != nullptr);
        ReturnTickets(s, nowMs);
        uint8_t const cafeId = s.cafeId;
        Barista* b = LoadedBarista(s.low);
        CafeSummary sum;
        sum.cafeId = cafeId;
        sum.reason = static_cast<CafeShiftEnd>(reason);
        sum.shiftSec = NowSec() - s.startSec;
        sum.drinks = s.drinks;
        sum.perfects = s.perfects;
        sum.tipsCopper = s.tips;
        sum.xp = s.xp;
        sum.xpLost = s.xpLost;
        sum.points = s.points;
        sum.bestStreak = s.bestStreak;
        if (b)
        {
            b->tired.offSince = NowSec();
            b->staffOffer = b->level >= StaffDrinkLevel && s.drinks >= StaffDrinkShiftDrinks && b->staffDay != _dayId;
            sum.staffDrink = b->staffOffer;
            b->dirty = true;
            FlagShift(s, *b);
        }
        if (p)
        {
            p->RemoveAurasDueToSpell(D::SpellOnShift);
            p->SetEmoteState(EMOTE_ONESHOT_NONE);
            Ui::SendCafeSummary(p, sum);
        }
        LOG_INFO("module", "[Bleakhold] Cafe: {} ends a shift at {} ({}): {} s, {} drinks, {} Perfect, {} tips, {} XP "
            "({} lost to the cap), {} points, best streak {}", s.name, CafeInfo(cafeId).name, reason, sum.shiftSec,
            s.drinks, s.perfects, Copper(s.tips), s.xp, s.xpLost, s.points, s.bestStreak);
        uint64_t const guid = s.guid;
        _shifts.erase(guid);
        if (b)
            SaveBarista(*b);
        if (p)
        {
            MarkView(guid, VState | VTickets);
            if (reason == static_cast<char>(CafeShiftEnd::Player) || reason == static_cast<char>(CafeShiftEnd::Idle))
                Say(cafeId, "staff_owner", CafeInfo(cafeId).owner, "shiftEnd");
        }
        MarkCafeBaristas(cafeId, VQueue);
        MarkCafeList();
    }

    void Cafe::EndShiftsAt(uint8_t cafeId, char reason)
    {
        std::vector<uint64_t> guids;
        for (auto const& [g, s] : _shifts)
            if (s.cafeId == cafeId)
                guids.push_back(g);
        uint64_t const now = Mgr::NowMs();
        for (uint64_t g : guids)
            if (Shift* s = ShiftOf(g))
                EndShift(*s, reason, now);
    }

    // =============================================================================================================
    // Steps (sections 3.4.2 and 3.6)
    // =============================================================================================================
    void Cafe::SendStepEvent(Player* player, Ticket const& t, uint8_t stepIndex, uint8_t action, CafeStepEventKind kind,
        std::optional<uint32_t> durMs, char grade, Step const* step)
    {
        if (!player)
            return;
        CafeStepEvent e;
        e.ticketId = t.id;
        e.stepIndex = stepIndex;
        e.actionId = action;
        e.event = kind;
        e.durMs = durMs;
        if (step && step->timed)
        {
            e.goldLoMs = step->goldLoMs;
            e.goldHiMs = step->goldHiMs;
        }
        e.grade = grade == 'P' ? CafeGrade::Perfect : grade == 'G' ? CafeGrade::Good : grade == 'O' ? CafeGrade::Off :
            CafeGrade::None;
        e.nextStep = t.next + 1u;
        Ui::SendCafeStep(player, e);
    }

    void Cafe::StartStep(Player* player, Shift& s, Ticket& t, uint8_t action, uint64_t nowMs)
    {
        D::Action const* a = D::FindAction(action);
        if (!a)
            return;
        player->SetSheath(SHEATH_STATE_UNARMED);
        if (player->IsNonMeleeSpellCast(false, false, true))
            player->InterruptNonMeleeSpells(false);
        Step st;
        st.active = true;
        st.index = t.next;
        st.action = action;
        st.timed = a->kind == 'H';
        st.startMs = nowMs;
        st.durMs = a->durMs;
        st.spotX = player->GetPositionX();
        st.spotY = player->GetPositionY();
        if (st.timed)
        {
            R::GoldZone const z = R::ShiftGold(a->goldLo, a->goldHi, R::GoldShift(urand(0, 0x7FFFFFFF), _cfg.goldShiftPermille));
            st.goldLoMs = R::PermilleOf(a->durMs, z.lo);
            st.goldHiMs = R::PermilleOf(a->durMs, z.hi);
        }
        if (a->emoteState)
        {
            player->SetEmoteState(Emote(a->emoteState));
            st.emoteState = a->emoteState;
        }
        else if (a->emoteOneShot)
            player->HandleEmoteCommand(a->emoteOneShot);
        t.step = st;
        player->CastSpell(player, a->spell, StepCastFlags);
        s.lastActionMs = nowMs;
        SendStepEvent(player, t, uint8_t(t.next + 1), action, CafeStepEventKind::Started, a->durMs, 'N', &t.step);
        if (CafeRt* c = CafeOf(s.cafeId))
            c->atDirty = true;
        // the head barista's tutorial lines: at the barista's first Pull Shot and first Steam Milk, once each (the
        // barista row keeps them), not only on the tutorial ticket, whose drink may have neither step
        if (Barista* b = LoadedBarista(s.low))
        {
            std::string_view const key = R::TutorialLine(action, b->flags);
            if (!key.empty())
            {
                b->dirty = true;
                Say(s.cafeId, "staff_head", CafeInfo(s.cafeId).head, key);
            }
        }
        if (_cfg.overheadKits)
            player->SendPlaySpellVisual(920000 + action);
        LOG_DEBUG("module", "[Bleakhold] Cafe: {} starts {} on ticket {} (step {})", s.name, a->name, t.id, t.next + 1);
    }

    void Cafe::CompleteStep(Player* player, Shift& s, Ticket& t, char grade, uint64_t nowMs)
    {
        if (!t.step.active)
            return;
        Step const st = t.step;
        uint32_t const spell = D::SpellStepBase + st.action;
        if (player && st.timed)
        {
            // the channel ends cleanly: no "Interrupted" for the others and no cancel hook (Unit::FinishSpell)
            if (Spell* sp = player->GetCurrentSpell(CURRENT_CHANNELED_SPELL); sp && sp->m_spellInfo->Id == spell)
                player->FinishSpell(CURRENT_CHANNELED_SPELL, true);
            player->RemoveAurasDueToSpell(spell);
        }
        if (player && st.emoteState)
            player->SetEmoteState(EMOTE_ONESHOT_NONE);
        t.grades[st.index] = grade;
        t.step = Step();
        t.next = static_cast<uint8_t>(st.index + 1);
        SendStepEvent(player, t, uint8_t(st.index + 1), st.action, CafeStepEventKind::Done, st.durMs, grade, &st);
        if (CafeRt* c = CafeOf(s.cafeId))
            c->atDirty = true;
        if (player && _cfg.overheadKits)
            player->SendPlaySpellVisual(920000);
        D::Recipe const* r = D::FindRecipe(t.recipeId);
        if (player && r && st.action == D::ActionServe && t.next >= r->stepCount)
        {
            Serve(player, s, t, nowMs);
            return;
        }
        MarkView(s.guid, VTickets);
        if (Order* o = OrderOf(t.orderId); o && o->kind == 'P')
            SendOrderState(*o);
    }

    void Cafe::AbortStep(Player* player, Shift& s, Ticket& t, bool interruptSpell)
    {
        if (!t.step.active)
            return;
        Step const st = t.step;
        t.step.expectCancel = true;
        uint32_t const spell = D::SpellStepBase + st.action;
        if (player)
        {
            if (interruptSpell)
                for (CurrentSpellTypes type : { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
                    if (Spell* sp = player->GetCurrentSpell(type); sp && sp->m_spellInfo->Id == spell)
                        player->InterruptSpell(type, true, true, false);   // "Interrupted" is right for an abort
            if (st.emoteState)
                player->SetEmoteState(EMOTE_ONESHOT_NONE);
            player->RemoveAurasDueToSpell(spell);
        }
        t.step = Step();
        SendStepEvent(player, t, uint8_t(st.index + 1), st.action, CafeStepEventKind::Interrupted, std::nullopt, 'N');
        if (CafeRt* c = CafeOf(s.cafeId))
            c->atDirty = true;
        MarkView(s.guid, VTickets);
    }

    void Cafe::TickSteps(uint64_t nowMs)
    {
        for (auto& [guid, s] : _shifts)
        {
            Player* p = ObjectAccessor::FindConnectedPlayer(ObjectGuid(guid));
            if (!p)
                continue;
            std::vector<uint32_t> ids;
            for (Ticket const& t : s.tickets)
                if (t.step.active)
                    ids.push_back(t.id);
            for (uint32_t id : ids)
            {
                Ticket* t = TicketOf(s, id);
                if (!t || !t->step.active)
                    continue;
                uint64_t const elapsed = nowMs - t->step.startMs;
                if (!t->step.timed && elapsed >= t->step.durMs)
                    CompleteStep(p, s, *t, 'P', nowMs);   // taps are recorded as P: neutral
                else if (t->step.timed && elapsed >= uint64_t(t->step.durMs) + R::AutoReleaseMs)
                    CompleteStep(p, s, *t, 'O', nowMs);   // never released: the bar ran out
            }
        }
    }

    void Cafe::RemoveTicket(Shift& s, uint32_t ticketId)
    {
        s.tickets.erase(std::remove_if(s.tickets.begin(), s.tickets.end(), [&](Ticket const& t) { return t.id == ticketId; }),
            s.tickets.end());
        MarkView(s.guid, VTickets | VState);
    }

    // The customer gave up, left or the house took the order over: the barista's ticket closes as Left.
    void Cafe::CloseTicketLeft(Shift& s, Ticket& t, std::string const& line, bool penalty, uint64_t nowMs)
    {
        Player* p = ObjectAccessor::FindConnectedPlayer(ObjectGuid(s.guid));
        if (t.step.active)
            AbortStep(p, s, t, p != nullptr);
        Barista* b = LoadedBarista(s.low);
        CafeResult res;
        res.ticketId = t.id;
        res.recipeId = t.recipeId;
        res.quality = CafeQuality::Left;
        res.line = line;
        if (Order const* o = OrderOf(t.orderId))
            res.customer = o->customer;
        if (penalty)
            s.streak = 0;
        res.streak = s.streak;
        res.level = b ? b->level : 1;
        if (p)
            Ui::SendCafeResult(p, res);
        uint32_t const id = t.id;
        RemoveTicket(s, id);
        (void)nowMs;
    }

    // =============================================================================================================
    // Serving (section 3.4.3)
    // =============================================================================================================
    void Cafe::Serve(Player* player, Shift& s, Ticket& t, uint64_t nowMs)
    {
        Order* o = OrderOf(t.orderId);
        D::Recipe const* r = D::FindRecipe(t.recipeId);
        CafeRt* c = CafeOf(s.cafeId);
        if (!o || !r || !c)
        {
            RemoveTicket(s, t.id);
            return;
        }
        Barista& b = BaristaOf(player);
        uint32_t const left = R::PatienceLeftPermille(nowMs, o->patienceEndMs, o->patienceMaxMs);
        char const quality = R::Quality(r->steps.data(), t.grades.data(), r->stepCount, left);
        bool const rush = RushLive(s.cafeId);
        bool const tired = R::IsTired(b.tired, NowSec(), _cfg.tiredAfterMin, _cfg.tiredRestMin);

        // streak and repeats
        if (quality == 'P')
            ++s.streak;
        else
            s.streak = 0;
        s.bestStreak = std::max(s.bestStreak, s.streak);
        b.bestStreak = std::max(b.bestStreak, s.streak);
        s.inARow = s.lastRecipe == t.recipeId ? static_cast<uint8_t>(std::min(s.inARow + 1, 99)) : 1;
        s.lastRecipe = t.recipeId;

        RollDay(b);
        bool pairBoost = false;
        if (o->kind == 'P')
        {
            uint32_t& n = _pairs[{ b.low, o->customerLow }];
            pairBoost = R::PairBoost(n, _cfg.pairBoostPerDay);
            ++n;
        }
        R::DrinkFacts f;
        f.tier = r->tier;
        f.quality = quality;
        f.patienceLeftPermille = left;
        f.streak = quality == 'P' ? s.streak : 0;
        f.pairBoost = pairBoost;
        f.rush = rush;
        f.tired = tired;
        f.tiredPct = _cfg.tiredPct;
        f.inARow = s.inARow;
        uint32_t const earned = R::XpForDrink(f);
        R::XpCredit const credit = R::CreditXp(earned, b.day.xpFull, b.day.xpHalf, _cfg.xpDailyFull, _cfg.xpDailyHalf);
        b.day.xpFull = credit.fullUsed;
        b.day.xpHalf = credit.halfUsed;
        uint32_t const pointsCap = R::PointsCap(_cfg.pointsDailyCap, _cfg.pointsRushExtra, c->rushDayId == _dayId);
        uint32_t const points = R::CapAdd(R::PointsForDrink(f), b.day.points, pointsCap);
        b.day.points += points;

        // money: an NPC's tip, or the wage of a player order (one transaction with the order row, D13)
        uint32_t earnedCopper = 0;
        if (o->kind == 'P')
        {
            earnedCopper = R::WageCopper(o->price, o->tip, o->sharePct);
            PayWage(*o, player, earnedCopper);
        }
        else if (o->personaIdx >= 0)
        {
            D::Persona const& per = D::Personas[static_cast<std::size_t>(o->personaIdx)];
            uint32_t const tip = R::TipForDrink(r->tier, quality, per.tipPct, player->GetLevel(), rush, b.level);
            uint32_t const cap = R::TipCap(_cfg.tipDailyBaseCopper, _cfg.tipDailyPerLevelCopper, player->GetLevel());
            earnedCopper = R::CapAdd(tip, b.day.tips, cap);
            if (earnedCopper && player->ModifyMoney(static_cast<int32_t>(earnedCopper), false))
                b.day.tips += earnedCopper;
            else
                earnedCopper = 0;
        }

        // the barista's records
        bool levelUp = false;
        AddBaristaXp(player, b, credit.credited, levelUp);
        ++b.drinks;
        ++b.day.drinks;
        b.day.cafeId = s.cafeId;
        if (quality == 'P')
        {
            ++b.perfects;
            ++b.day.perfects;
        }
        uint32_t const madeMs = static_cast<uint32_t>(std::min<uint64_t>(nowMs - t.takenMs, 0xFFFFFFFFull));
        if (!b.fastestMs || madeMs < b.fastestMs)
            b.fastestMs = madeMs;
        if (t.tutorial)
            b.flags |= FlagTutorialDone;
        // this week's board
        if (b.week.weekId != _weekId)
        {
            b.week = WeekRowRt();
            b.week.weekId = _weekId;
        }
        b.week.cafeId = s.cafeId;
        ++b.week.drinks;
        if (quality == 'P')
            ++b.week.perfects;
        if (points)
        {
            b.week.points += points;
            b.week.scoreAt = NowSec();
        }
        b.week.daysMask = static_cast<uint8_t>(b.week.daysMask | R::DayBit(_dayId));
        b.week.dirty = true;
        b.day.dirty = true;
        b.dirty = true;
        ++s.drinks;
        if (quality == 'P')
            ++s.perfects;
        s.tips += earnedCopper;
        s.xp += credit.credited;
        s.xpLost += credit.cut;
        s.points += points;
        if (rush)
        {
            ++s.rushServed;
            ++b.day.rushServed;
            ++c->rushServed;
        }
        if (c->servedTodayDay != _dayId)
        {
            c->servedTodayDay = _dayId;
            c->servedToday = 0;
        }
        ++c->servedToday;

        std::string const thanks = ThanksOf(*o);
        CafeResult res;
        res.ticketId = t.id;
        res.recipeId = t.recipeId;
        res.quality = static_cast<CafeQuality>(quality);
        res.xp = credit.credited;
        res.tipCopper = earnedCopper;
        res.points = points;
        res.streak = s.streak;
        res.levelUp = levelUp;
        res.level = b.level;
        res.customer = o->customer;
        res.line = o->kind == 'P' ? std::string() : thanks;
        res.xpCapped = credit.cut;
        Ui::SendCafeResult(player, res);
        if (_cfg.overheadKits)
            player->SendPlaySpellVisual(920064 + (quality == 'P' ? 0u : quality == 'G' ? 1u : 2u));
        LOG_DEBUG("module", "[Bleakhold] Cafe: {} served {} ({}) to {}: {} XP, {} points, {}c", s.name, r->name, quality,
            o->customer, credit.credited, points, earnedCopper);

        o->quality = quality;
        o->rushServed = rush;
        uint32_t const orderId = o->id;
        uint32_t const ticketId = t.id;
        RemoveTicket(s, ticketId);
        if (o->kind == 'P')
            OrderReady(*o, nowMs);
        else
        {
            // the cup appears on the counter; the customer takes it (CupTaken), says thanks and sits
            o->state = 'R';
            o->readyUntilMs = nowMs + NpcCupWaitMs;
            Unqueue(*o);
            uint32_t const cupGo = R::PieceEntry(r->tableCup, _cfg.useNewArt && _newArtOk);
            uint32_t const cupItem = r->cupItem;
            char const q = quality;
            CrowdCall([orderId, q, thanks, cupItem, cupGo]() {
                CafeCrowd::Instance().OrderServed(orderId, q, thanks, cupItem, cupGo);
            });
        }
        if (levelUp)
        {
            GrantLevelRewards(player, b, true);
            D::Level const* lv = D::FindLevel(b.level);
            Ui::Toast(player, ToastKind::Info, "Barista level " + std::to_string(b.level), lv ? std::string(lv->text) : "",
                "cafe");
            D::Cafe const& cd = CafeInfo(s.cafeId);
            for (auto const& st : c->site.staff)
                if (st.role == "staff_head" && player->GetExactDist2d(st.home.GetPositionX(), st.home.GetPositionY()) <=
                    LevelUpLineRadius)
                    Say(s.cafeId, "staff_head", cd.head, "levelUp", std::to_string(b.level));
        }
        MarkView(s.guid, VState | VTickets);
        MarkCafeBaristas(s.cafeId, VQueue);
        SaveDayWeek(b);
    }

    void Cafe::AddBaristaXp(Player* player, Barista& b, uint32_t xp, bool& levelUp)
    {
        uint8_t const before = b.level;
        b.xp = static_cast<uint32_t>(std::min<uint64_t>(uint64_t(b.xp) + xp, 0xFFFFFFFFull));
        b.level = R::LevelOf(b.xp);
        levelUp = b.level > before;
        if (levelUp)
            LOG_INFO("module", "[Bleakhold] Cafe: {} reaches barista level {}", player ? player->GetName() : b.name, b.level);
        b.dirty = true;
    }

    // =============================================================================================================
    // Orders (sections 3.4.4 and 3.4.5)
    // =============================================================================================================
    void Cafe::QueueOrder(CafeRt& c, Order& o, bool front)
    {
        auto& q = c.queue;
        q.erase(std::remove(q.begin(), q.end(), o.id), q.end());
        if (front)
        {
            q.insert(q.begin(), o.id);
            return;
        }
        if (o.kind == 'P')
        {
            // behind the earlier player orders, before every NPC order
            auto it = q.begin();
            while (it != q.end())
            {
                Order const* other = OrderOf(*it);
                if (!other || other->kind != 'P')
                    break;
                ++it;
            }
            q.insert(it, o.id);
            return;
        }
        q.push_back(o.id);
    }

    void Cafe::Unqueue(Order const& o)
    {
        if (CafeRt* c = CafeOf(o.cafeId))
            c->queue.erase(std::remove(c->queue.begin(), c->queue.end(), o.id), c->queue.end());
    }

    void Cafe::RemoveOrder(uint32_t id)
    {
        Order* o = OrderOf(id);
        if (!o)
            return;
        Unqueue(*o);
        uint8_t const cafeId = o->cafeId;
        _orders.erase(id);
        MarkCafeBaristas(cafeId, VQueue);
    }

    std::string Cafe::OrderLineOf(Order const& o) const
    {
        return o.orderLine;
    }

    std::string Cafe::ThanksOf(Order const& o) const
    {
        if (o.personaIdx < 0 || static_cast<std::size_t>(o.personaIdx) >= D::Personas.size())
            return {};
        return R::ThanksLine(D::Personas[static_cast<std::size_t>(o.personaIdx)], CafeInfo(o.cafeId).linePool, Random(1000));
    }

    std::string Cafe::ComplaintOf(Order const& o) const
    {
        if (o.personaIdx < 0 || static_cast<std::size_t>(o.personaIdx) >= D::Personas.size())
            return {};
        return R::ComplaintLine(D::Personas[static_cast<std::size_t>(o.personaIdx)], CafeInfo(o.cafeId).linePool,
            Random(1000));
    }

    // The house (the owner, then the head barista) makes it: an ambient NPC order, a player order nobody took, or a
    // takeover after a barista failed a player order.
    void Cafe::HouseTakes(Order& o, bool takeover, uint64_t nowMs)
    {
        D::Recipe const* r = D::FindRecipe(o.recipeId);
        if (!r)
            return;
        o.state = 'H';
        o.takeover = takeover;
        o.ambient = o.kind != 'P';
        o.houseStartMs = nowMs;
        o.houseSteps = r->stepCount;
        o.houseStep = 0;
        o.houseTotalMs = R::HouseMinTotalMs(_cfg.houseBaseSec, _cfg.housePerLineSec, r->lines);
        HouseJob const job = HouseJobOf(o);
        uint8_t const cafeId = o.cafeId;
        D::Cafe const& cd = CafeInfo(cafeId);
        uint32_t const id = o.id;
        std::vector<std::function<void()>> calls;
        calls.push_back([cafeId, job]() { CafeCrowd::Instance().QueueHouseJob(cafeId, job); });
        if (o.kind == 'P')
        {
            SaveOrderState(o);
            SendOrderState(o);
            // the worker who starts it says its line (HouseStepStarted): the owner, or the head barista
            if (o.viaGossip)
                if (Player* cu = ObjectAccessor::FindConnectedPlayer(ObjectGuid(o.customerGuid)))
                    Tell(cu, "The house is making your " + DrinkName(o.recipeId) + ".");
        }
        else
        {
            bool yell = false;
            std::string const answer(R::StaffLine(cd.owner, "ambientAnswer", Random(1000), &yell));
            std::string const line = o.orderLine;
            o.lineSaid = true;
            calls.push_back([id, line, answer]() { CafeCrowd::Instance().HouseOrderTaken(id, line, answer); });
        }
        for (auto& call : calls)
            CrowdCall(std::move(call));
        MarkCafeBaristas(cafeId, VQueue);
    }

    // The crowd's job for an order the house makes (a takeover goes to the very front).
    HouseJob Cafe::HouseJobOf(Order const& o) const
    {
        HouseJob job;
        job.orderId = o.id;
        job.playerOrder = o.kind == 'P';
        job.front = o.takeover;
        if (D::Recipe const* r = D::FindRecipe(o.recipeId))
            for (uint8_t i = 0; i < r->stepCount; ++i)
                job.actions.push_back(r->steps[i]);
        job.minTotalMs = o.houseTotalMs;
        return job;
    }

    // A player order is made: it waits on the counter for PickupSec.
    void Cafe::OrderReady(Order& o, uint64_t nowMs)
    {
        o.state = 'R';
        o.readyUntilMs = nowMs + uint64_t(_cfg.pickupSec) * 1000;
        o.readyUntilEpoch = NowSec() + _cfg.pickupSec;
        Unqueue(o);
        if (o.baristaLow == 0)
            SaveOrderState(o);   // a barista's drink was written with the wage (PayWage)
        D::Recipe const* r = D::FindRecipe(o.recipeId);
        uint32_t const cupGo = r ? R::PieceEntry(r->tableCup, _cfg.useNewArt && _newArtOk) : 0;
        uint32_t const id = o.id;
        uint8_t const cafeId = o.cafeId;
        o.cupOnCounter = true;
        CrowdCall([cafeId, id, cupGo]() { CafeCrowd::Instance().PlaceCounterCup(cafeId, id, cupGo); });
        SendOrderState(o);
        if (o.viaGossip)
            if (Player* cu = ObjectAccessor::FindConnectedPlayer(ObjectGuid(o.customerGuid)))
                Tell(cu, "Your " + DrinkName(o.recipeId) + " is ready at the counter.");
        MarkCafeBaristas(cafeId, VQueue);
    }

    void Cafe::Deliver(Order& o, Player* customer)
    {
        uint32_t const id = o.id;
        if (customer)
        {
            GrantDrink(customer, o.recipeId, o.quality == 'P', o.rushServed);
            SendOrderState(o, CafeOrderStateId::Delivered);
            if (o.viaGossip)
                Tell(customer, "Enjoy your " + DrinkName(o.recipeId) + "!");
        }
        DeleteOrderRow(id);
        if (o.cupOnCounter)
        {
            CrowdCall([id]() { CafeCrowd::Instance().RemoveCounterCup(id); });
        }
        if (!o.deliverSent)
            if (CafeRt* c = CafeOf(o.cafeId))
            {
                std::string const owner = "staff_owner";
                uint8_t const cafeId = c->id;
                CrowdCall([cafeId, owner]() { CafeCrowd::Instance().StaffSay(cafeId, owner, "Enjoy!", false); });
            }
        LOG_INFO("module", "[Bleakhold] Cafe: order {} delivered to {}", id, o.customer);
        RemoveOrder(id);
    }

    void Cafe::ExpirePickup(Order& o)
    {
        uint32_t const id = o.id;
        R::Money const m = R::SettleOrder(o.baristaLow ? R::OrderEnd::ServedExpired : R::OrderEnd::HouseExpired, o.price,
            o.tip, o.sharePct);
        RefundOrder(o, m.refunded, "expired");
        SendOrderState(o, CafeOrderStateId::Expired);
        if (o.cupOnCounter)
        {
            CrowdCall([id]() { CafeCrowd::Instance().RemoveCounterCup(id); });
        }
        if (o.viaGossip)
            if (Player* cu = ObjectAccessor::FindConnectedPlayer(ObjectGuid(o.customerGuid)))
                Tell(cu, "Your " + DrinkName(o.recipeId) + " went cold on the counter; " + Copper(m.refunded) +
                    " were refunded.");
        RemoveOrder(id);
    }

    // A full refund (CCANCEL, the close path, the feature off): the barista's ticket closes without a penalty and the
    // house stops.
    void Cafe::RefundAll(Order& o, std::string_view why)
    {
        uint32_t const id = o.id;
        DropLeftovers(o, "The order was cancelled.");
        RefundOrder(o, o.price + o.tip, why);
        SendOrderState(o, CafeOrderStateId::Cancelled);
        if (o.viaGossip)
            if (Player* cu = ObjectAccessor::FindConnectedPlayer(ObjectGuid(o.customerGuid)))
                Tell(cu, "Your order was cancelled; " + Copper(o.price + o.tip) + " were refunded.");
        RemoveOrder(id);
    }

    // What goes with an order that ends early besides its money: the barista's ticket closes as Left (no penalty),
    // the house stops, the cup on the counter goes.
    void Cafe::DropLeftovers(Order& o, std::string const& ticketLine)
    {
        uint32_t const id = o.id;
        uint8_t const left = R::OrderLeftoversOf(o.state, o.cupOnCounter);
        if (left & R::LeftTicket)
            if (Shift* s = ShiftOf(o.baristaGuid))
                if (Ticket* t = TicketOf(*s, o.ticketId))
                    CloseTicketLeft(*s, *t, ticketLine, false, Mgr::NowMs());
        if (left & R::LeftHouseJob)
            CrowdCall([id]() { CafeCrowd::Instance().CancelHouseJob(id); });
        if (left & R::LeftCounterCup)
        {
            o.cupOnCounter = false;
            CrowdCall([id]() { CafeCrowd::Instance().RemoveCounterCup(id); });
        }
    }

    void Cafe::DropNpcOrders(CafeRt& c)
    {
        std::vector<uint32_t> ids;
        for (auto const& [id, o] : _orders)
            if (o.cafeId == c.id && o.kind != 'P')
                ids.push_back(id);
        for (uint32_t id : ids)
        {
            Order* o = OrderOf(id);
            if (!o)
                continue;
            DropLeftovers(*o, "The customer has gone.");
            RemoveOrder(id);
        }
    }

    // Section 3.4.6: shifts end without a penalty, every pending player order is refunded in full, the NPC orders go
    // (their customers leave), the house stops. The caller then does its own work.
    void Cafe::ClosePath(CafeRt& c, char shiftReason)
    {
        std::vector<uint32_t> refund;
        for (auto const& [id, o] : _orders)
            if (o.cafeId == c.id && o.kind == 'P' && (o.state == 'W' || o.state == 'T' || o.state == 'H'))
                refund.push_back(id);
        for (uint32_t id : refund)
            if (Order* o = OrderOf(id))
                RefundAll(*o, "the cafe closed");
        DropNpcOrders(c);
        EndShiftsAt(c.id, shiftReason);
        c.atDirty = true;
        MarkCafeList();
    }

    void Cafe::TickOrders(uint64_t nowMs)
    {
        std::vector<uint32_t> ids;
        ids.reserve(_orders.size());
        for (auto const& [id, o] : _orders)
            ids.push_back(id);
        for (uint32_t id : ids)
        {
            Order* o = OrderOf(id);
            if (!o)
                continue;
            CafeRt* c = CafeOf(o->cafeId);
            if (!c)
                continue;
            if (c->open == 2 && o->state != 'R')
                continue;   // paused: frozen (FreezeFor moved the end times)
            switch (o->state)
            {
                case 'W':
                    if (o->kind == 'P')
                    {
                        if (!BaristasAt(o->cafeId) || nowMs >= o->takeDeadlineMs)
                            HouseTakes(*o, false, nowMs);
                    }
                    else if (!o->ambient && nowMs >= o->patienceEndMs)
                    {
                        std::string const line = ComplaintOf(*o);
                        CrowdCall([id, line]() { CafeCrowd::Instance().OrderFailed(id, line); });
                        RemoveOrder(id);
                    }
                    else if (D::Recipe const* r = D::FindRecipe(o->recipeId))
                    {
                        // nobody on shift (the last barista left; a returned ticket): the house makes it now. Else the
                        // first waiting order (taken and house orders stay in the queue) that waited TakeTimeoutSec and
                        // no barista on shift can make.
                        uint32_t const first = R::FirstWaiting(c->queue, [this](uint32_t q) {
                            Order const* x = OrderOf(q);
                            return x ? x->state : char(0);
                        });
                        if (R::NpcHouseDue(BaristasAt(o->cafeId), first == id, nowMs - o->createdMs,
                            _cfg.takeTimeoutSec * 1000, MaxBaristaLevelAt(o->cafeId), r->unlock))
                            HouseTakes(*o, false, nowMs);
                    }
                    break;
                case 'T':
                {
                    Shift* s = ShiftOf(o->baristaGuid);
                    Ticket* t = s ? TicketOf(*s, o->ticketId) : nullptr;
                    if (!s || !t)
                    {
                        // the barista is gone without returning it: back to the queue
                        o->state = 'W';
                        o->ticketId = 0;
                        o->baristaGuid = 0;
                        o->baristaLow = 0;
                        QueueOrder(*c, *o, true);
                        o->takeDeadlineMs = nowMs + uint64_t(_cfg.takeTimeoutSec) * 1000;
                        break;
                    }
                    if (o->kind == 'P')
                    {
                        if (R::TakeoverDue(nowMs, o->patienceEndMs, t->ruins, _cfg.maxRuins))
                        {
                            CloseTicketLeft(*s, *t, "Too slow: the house is finishing it.", true, nowMs);
                            o->ticketId = 0;
                            o->baristaGuid = 0;
                            o->baristaLow = 0;
                            o->baristaName.clear();
                            HouseTakes(*o, true, nowMs);
                        }
                    }
                    else if (nowMs >= o->patienceEndMs)
                    {
                        std::string const line = ComplaintOf(*o);
                        CloseTicketLeft(*s, *t, line, true, nowMs);
                        CrowdCall([id, line]() { CafeCrowd::Instance().OrderFailed(id, line); });
                        RemoveOrder(id);
                    }
                    break;
                }
                case 'R':
                {
                    if (o->kind != 'P')
                    {
                        if (nowMs >= o->readyUntilMs)
                            RemoveOrder(id);   // the customer never took its cup
                        break;
                    }
                    if (nowMs >= o->readyUntilMs)
                    {
                        ExpirePickup(*o);
                        break;
                    }
                    Player* cu = ObjectAccessor::FindConnectedPlayer(ObjectGuid(o->customerGuid));
                    if (!cu || !cu->IsInWorld() || !cu->IsAlive() || cu->GetMapId() != c->map)
                        break;
                    // seated at a cafe table: table service wins (the busser brings it, then Delivered), even though
                    // every chair is inside PickupRadius; the 15 yd rule is for a customer on their feet
                    if (c->crowdSpawned && CafeCrowd::Instance().PlayerSeat(c->id, o->customerGuid))
                    {
                        if (!o->deliverSent)
                        {
                            o->deliverSent = true;
                            D::Recipe const* r = D::FindRecipe(o->recipeId);
                            uint32_t const cupGo = r ? R::PieceEntry(r->tableCup, _cfg.useNewArt && _newArtOk) : 0;
                            uint8_t const cafeId = c->id;
                            uint64_t const guid = o->customerGuid;
                            CrowdCall([cafeId, id, guid, cupGo]() {
                                CafeCrowd::Instance().DeliverToSeat(cafeId, id, guid, cupGo);
                            });
                        }
                        break;
                    }
                    // on their feet: a delivery under way stops by itself (the busser puts the cup back), so sitting
                    // down again asks for a new one
                    o->deliverSent = false;
                    Position const& pick = c->site.pickupSpot;
                    if (cu->GetExactDist2d(pick.GetPositionX(), pick.GetPositionY()) <= _cfg.pickupRadius)
                        Deliver(*o, cu);
                    break;
                }
                default:
                    break;
            }
        }
    }

    // =============================================================================================================
    // Cafes: speech, danger, the Rush, days and weeks
    // =============================================================================================================
    void Cafe::TickCafes(uint64_t nowMs)
    {
        bool const second = nowMs - _lastSecondMs >= SecondMs;
        for (CafeRt& c : _cafes)
        {
            if (!c.placed || !c.enabled)
                continue;
            if (second)
                TickDanger(c, nowMs);
            TickSpeech(c, nowMs);
            // CAFE: a change of open, baristas, the Rush or the house's time; the queue length alone at most every 5 s
            // (orders never mark it themselves; FlushViews notes the length it sent)
            uint32_t const eta = c.crowdSpawned ? CafeCrowd::Instance().HouseEtaSec(c.id, std::nullopt) : 0;
            uint32_t const key = uint32_t(c.open) | (uint32_t(BaristasAt(c.id)) << 4) | (uint32_t(c.rushState) << 8) |
                (std::min<uint32_t>(eta / 15, 255) << 16);
            bool const keyChanged = key != c.sentKey;
            c.sentKey = key;
            if (R::CafeListMark(keyChanged, QueueLen(c.id) != c.sentQueueLen, nowMs - _cafeListSentMs))
                MarkCafeList();
            // the house's running steps for the bystanders' strip: a step whose time is over leaves the list
            for (auto const& [id, o] : _orders)
                if (o.cafeId == c.id && o.state == 'H' && o.houseStepMs &&
                    nowMs >= o.houseStepMs + o.houseStepDurMs && nowMs < o.houseStepMs + o.houseStepDurMs + _cfg.tickMs)
                    c.atDirty = true;
        }
        if (second)
            TickRush(nowMs);
        if (nowMs - _lastPeriodMs >= PeriodCheckMs)
        {
            _lastPeriodMs = nowMs;
            TickPeriods(nowMs);
        }
    }

    void Cafe::TickSpeech(CafeRt& c, uint64_t nowMs)
    {
        if (c.open != 1)
            return;
        if (!c.nextIdleMs)
            c.nextIdleMs = nowMs + 240000 + Random(180000);
        if (nowMs < c.nextIdleMs || nowMs - c.lastStaffLineMs < StaffLineGapMs)
            return;
        c.nextIdleMs = nowMs + 240000 + Random(180000);
        // only while a player is near
        Map* map = MapOf(c);
        if (!map)
            return;
        bool near = false;
        ForPlayersOn(map, [&](Player* p) {
            near = p->GetExactDist2d(c.anchor.x, c.anchor.y) <= IdleLineRadius;
            return !near;
        });
        if (!near)
            return;
        std::vector<D::StaffMember const*> talkers;
        for (D::StaffMember const& s : D::Staff)
            if (s.cafeId == c.id && !R::StaffLine(s.entry, "idle", 0).empty())
                talkers.push_back(&s);
        if (talkers.empty())
            return;
        D::StaffMember const* who = talkers[Random(static_cast<uint32_t>(talkers.size()))];
        Say(c.id, who->role, who->entry, "idle");
    }

    void Cafe::TickDanger(CafeRt& c, uint64_t nowMs)
    {
        Map* map = MapOf(c);
        Piece const* counter = nullptr;
        for (auto const& [slot, p] : c.pieces)
            if (p.role == "counter")
                counter = &p;
        if (!map || !counter)
            return;
        GameObject* counterGo = PieceObject(c, *counter);
        bool confirmed = false;
        bool present = false;
        std::unordered_set<uint64_t> seen;
        uint32_t const confirmMs = _cfg.confirmSec * 1000;
        ForPlayersOn(map, [&](Player* p) {
            if (!p->IsInWorld())
                return true;
            float const d = p->GetExactDist2d(counter->x, counter->y);
            if (d > _cfg.hostileRadius)
                return true;
            R::HostileFacts f;
            f.otherTeam = TeamCafe(p) != c.id;
            f.pvp = p->IsPvP() || p->IsFFAPvP();
            f.alive = p->IsAlive();
            f.gm = p->IsGameMaster();
            f.spectator = p->IsSpectator();
            f.stealth = p->HasStealthAura();
            f.invisible = p->HasInvisibilityAura();
            f.inCombat = p->IsInCombat();
            f.dist2d = d;
            f.dz = p->GetPositionZ() - counter->z;
            // line of sight last: it is the only costly test
            f.los = f.otherTeam && f.pvp && (counterGo ? counterGo->IsWithinLOSInMap(p) :
                p->IsWithinLOS(counter->x, counter->y, counter->z + 1.0f));
            if (!R::HostileQualifies(f, _cfg.hostileNearRadius, _cfg.hostileRadius, _cfg.hostileDz))
                return true;
            uint64_t const g = Raw(p);
            seen.insert(g);
            auto const it = c.hostileSince.emplace(g, nowMs).first;
            present = true;
            if (nowMs - it->second >= confirmMs)
                confirmed = true;
            return true;
        });
        for (auto it = c.hostileSince.begin(); it != c.hostileSince.end();)
            it = seen.count(it->first) ? std::next(it) : c.hostileSince.erase(it);
        if (c.open != 1 && c.open != 2 && c.open != 4)
            return;
        c.danger.open = c.open;
        R::DangerTimes t;
        t.confirmMs = confirmMs;
        t.resumeMs = _cfg.resumeSec * 1000;
        t.pauseMaxMs = _cfg.pauseMaxSec * 1000;
        t.reopenMs = _cfg.reopenSec * 1000;
        switch (R::DangerStep(c.danger, confirmed, present, nowMs, t))
        {
            case R::DangerEvent::Paused:
            {
                c.open = 2;
                // running steps stop without a penalty; tickets stay
                for (auto& [g, s] : _shifts)
                {
                    if (s.cafeId != c.id)
                        continue;
                    Player* p = ObjectAccessor::FindConnectedPlayer(ObjectGuid(g));
                    for (Ticket& tk : s.tickets)
                        if (tk.step.active)
                            AbortStep(p, s, tk, p != nullptr);
                    MarkView(g, VState);
                }
                if (!c.pauseLineSaid)
                {
                    c.pauseLineSaid = true;
                    Say(c.id, "staff_owner", CafeInfo(c.id).owner, "dangerPause");
                }
                LOG_INFO("module", "[Bleakhold] Cafe: {} paused (danger nearby)", CafeInfo(c.id).name);
                break;
            }
            case R::DangerEvent::Resumed:
                c.open = 1;
                c.pauseLineSaid = false;
                LOG_INFO("module", "[Bleakhold] Cafe: {} open again", CafeInfo(c.id).name);
                break;
            case R::DangerEvent::Closed:
                c.open = 4;
                ClosePath(c, static_cast<char>(CafeShiftEnd::Closed));
                LOG_INFO("module", "[Bleakhold] Cafe: {} closed for safety", CafeInfo(c.id).name);
                break;
            case R::DangerEvent::Reopened:
                c.open = 1;
                c.pauseLineSaid = false;
                LOG_INFO("module", "[Bleakhold] Cafe: {} reopens", CafeInfo(c.id).name);
                break;
            default:
                return;
        }
        MarkCafeList();
        MarkCafeBaristas(c.id, VState | VQueue);
    }

    void Cafe::TickRush(uint64_t nowMs)
    {
        int64_t const local = int64_t(NowSec()) + LocalUtcOffsetSec();
        R::RushClock const clock = R::RushAt(local, _cfg.rushTimes, _cfg.rushMinutes, _cfg.rushWarnMinutes);
        bool announcedSoon = false;
        std::vector<CafeRt*> ended;
        for (CafeRt& c : _cafes)
        {
            if (!c.placed || !c.enabled)
            {
                // a closed cafe has no Rush (its shifts ended with the close)
                c.rushState = 0;
                c.rushShouts.clear();
                continue;
            }
            // the staff's own Rush lines, a few seconds after the owner's yell
            for (auto it = c.rushShouts.begin(); it != c.rushShouts.end();)
            {
                if (nowMs < it->first)
                {
                    ++it;
                    continue;
                }
                if (c.rushState == 2)
                    if (D::StaffMember const* st = D::FindStaff(it->second))
                        Say(c.id, st->role, st->entry, "rush");
                it = c.rushShouts.erase(it);
            }
            // a live Rush ends at its end whatever Rush.Enable says now (a test Rush, a reload during one)
            switch (R::RushNext(c.rushState, _cfg.rush, clock, c.rushWindow, nowMs, c.rushEndMs))
            {
                case R::RushMove::End:
                    c.rushState = 0;
                    c.rushShouts.clear();
                    ended.push_back(&c);
                    MarkCafeList();
                    MarkCafeBaristas(c.id, VState);
                    break;
                case R::RushMove::Soon:
                    c.rushState = 1;
                    MarkCafeList();
                    MarkCafeBaristas(c.id, VState);
                    announcedSoon = true;
                    break;
                case R::RushMove::Start:
                {
                    c.rushWindow = clock.startLocal;
                    R::RushResumePlan const* resumePlan = nullptr;
                    R::RushResumePlan plan;
                    uint32_t const full = _cfg.rushMinutes * 60;
                    bool const late = clock.secTo + 5 < full;   // the window started before we saw it: a restart
                    if (late)
                    {
                        plan = R::RushResume(clock.secTo, _cfg.rushMinutes, _cfg.rushGoal, _cfg.rushSurvivorMin);
                        resumePlan = &plan;
                        LOG_INFO("module", "[Bleakhold] Cafe: {} is inside a Rush window ({} min left): {}",
                            CafeInfo(c.id).name, plan.minutesLeft, plan.resume ? "resumed with goal " +
                            std::to_string(plan.goal) : std::string("skipped"));
                        if (!plan.resume)
                        {
                            c.rushState = 0;
                            break;
                        }
                    }
                    c.rushState = 2;
                    c.rushEndMs = nowMs + uint64_t(clock.secTo) * 1000;
                    c.rushGoal = resumePlan ? plan.goal : _cfg.rushGoal;
                    c.rushSurvivorMin = resumePlan ? plan.survivorMin : _cfg.rushSurvivorMin;
                    c.rushServed = 0;
                    c.rushDayId = _dayId;
                    StartRushLines(c, nowMs);
                    MarkCafeList();
                    MarkCafeBaristas(c.id, VState);
                    break;
                }
                case R::RushMove::Calm:
                    c.rushState = 0;
                    MarkCafeList();
                    MarkCafeBaristas(c.id, VState);
                    break;
                default:
                    break;
            }
        }
        if (announcedSoon)
            AnnounceCafe("The Morning Rush starts in " + std::to_string(_cfg.rushWarnMinutes) +
                " minutes at The Lion's Roast (Stormwind) and The Grinding Tusk (Orgrimmar)!");
        if (ended.empty())
            return;
        // Rush Survivor: every barista of a cafe that met its goal and served enough during it (outside the cap)
        for (CafeRt* c : ended)
        {
            bool const met = c->rushServed >= c->rushGoal;
            LOG_INFO("module", "[Bleakhold] Cafe: the Rush at {} ends: {} of {} served", CafeInfo(c->id).name, c->rushServed,
                c->rushGoal);
            for (auto& [g, s] : _shifts)
            {
                if (s.cafeId != c->id)
                    continue;
                uint32_t const mine = s.rushServed;
                s.rushServed = 0;
                if (!met || mine < c->rushSurvivorMin || !_cfg.rushSurvivorXp)
                    continue;
                Player* p = ObjectAccessor::FindConnectedPlayer(ObjectGuid(g));
                Barista* b = LoadedBarista(s.low);
                if (!p || !b)
                    continue;
                bool levelUp = false;
                AddBaristaXp(p, *b, _cfg.rushSurvivorXp, levelUp);
                Ui::Toast(p, ToastKind::Info, "Rush Survivor", "+" + std::to_string(_cfg.rushSurvivorXp) + " barista XP", "cafe");
                if (levelUp)
                    GrantLevelRewards(p, *b, true);
                MarkView(g, VState);
            }
        }
        // the rivalry line, once both cafes' Rush is over
        CafeRt const& a = _cafes[0];
        CafeRt const& h = _cafes[1];
        if (a.rushState == 2 || h.rushState == 2)
            return;
        if (!(a.placed && a.enabled && h.placed && h.enabled))
            return;
        std::string line;
        if (a.rushServed == h.rushServed)
            line = "The Lion's Roast and The Grinding Tusk tied at " + std::to_string(a.rushServed) + " this morning!";
        else
        {
            bool const tuskWins = h.rushServed > a.rushServed;
            line = std::string(tuskWins ? "The Grinding Tusk out-brewed The Lion's Roast" : "The Lion's Roast out-brewed The Grinding Tusk") +
                " this morning, " + std::to_string(std::max(a.rushServed, h.rushServed)) + " to " +
                std::to_string(std::min(a.rushServed, h.rushServed)) + "!";
        }
        AnnounceCafe(line);
    }

    // The Rush goes live: the owner yells now, the staff with a Rush line shout a few seconds later, one by one.
    void Cafe::StartRushLines(CafeRt& c, uint64_t nowMs)
    {
        Say(c.id, "staff_owner", CafeInfo(c.id).owner, "rushStart");
        c.rushShouts.clear();
        std::vector<D::StaffMember const*> const shouters = R::RushShouters(c.id);
        for (std::size_t i = 0; i < shouters.size(); ++i)
            c.rushShouts.emplace_back(nowMs + R::RushShoutDelayMs(i), shouters[i]->entry);
    }

    void Cafe::TickPeriods(uint64_t nowMs)
    {
        uint32_t const day = DayId();
        uint32_t const week = WeekId();
        if (day != _dayId)
        {
            _dayId = day;
            _pairs.clear();
            for (auto& [low, b] : _baristas)
                RollDay(b);
            LOG_INFO("module", "[Bleakhold] Cafe: a new day ({})", day);
        }
        if (week != _weekId)
        {
            uint32_t const ended = _weekId;
            _weekId = week;
            if (_cfg.weekly && ended)
                WeeklyPayout(ended, false, nullptr);
            _boards.clear();
            LoadLastWinners();
        }
        // forget barista rows of players who logged out long ago
        for (auto it = _baristas.begin(); it != _baristas.end();)
        {
            if (it->second.expireMs && nowMs >= it->second.expireMs)
            {
                SaveBarista(it->second);
                it = _baristas.erase(it);
            }
            else
                ++it;
        }
    }

    // Section 3.9.7: a week that ended while the server was down is paid at the next start (TickPeriods only sees a week
    // change while it runs). WeeklyPayout's payout row keeps every week and cafe to one payout.
    void Cafe::PayMissedWeeks()
    {
        if (!_cfg.weekly || !_weekId)
            return;
        std::vector<uint32_t> weeks, paid;
        uint32_t const oldest = _weekId > R::MissedWeeksMax ? _weekId - R::MissedWeeksMax : 1;
        if (QueryResult r = CharacterDatabase.Query("SELECT DISTINCT `week_id` FROM `bleakhold_cafe_week` WHERE "
            "`week_id` >= {} AND `week_id` < {}", oldest, _weekId))
            do
                weeks.push_back((*r)[0].Get<uint32>());
            while (r->NextRow());
        if (QueryResult r = CharacterDatabase.Query("SELECT `week_id` FROM `bleakhold_cafe_payout` WHERE `week_id` >= {} "
            "AND `week_id` < {} GROUP BY `week_id` HAVING COUNT(*) >= 2", oldest, _weekId))
            do
                paid.push_back((*r)[0].Get<uint32>());
            while (r->NextRow());
        std::vector<uint32_t> const due = R::WeeksToPay(std::move(weeks), paid, _weekId);
        for (uint32_t w : due)
        {
            LOG_INFO("module", "[Bleakhold] Cafe: week {} ended while the server was down; paying it now", w);
            WeeklyPayout(w, false, nullptr);
        }
        if (!due.empty())
        {
            _boards.clear();
            LoadLastWinners();
        }
    }

    // =============================================================================================================
    // The crowd (section 3.7.1)
    // =============================================================================================================
    void Cafe::TickCrowd(uint64_t nowMs)
    {
        std::vector<CrowdInputs> inputs;
        for (CafeRt& c : _cafes)
        {
            if (!c.crowdSpawned)
                continue;
            CrowdInputs in;
            in.cafeId = c.id;
            in.open = c.open;
            in.baristas = BaristasAt(c.id);
            in.rush = c.rushState == 2;
            in.queueCap = QueueCap(c.id);
            in.queueLen = static_cast<uint8_t>(std::min<uint32_t>(QueueLen(c.id), 255));
            // whatever Customer.Enable says (the crowd checks it before it spawns anyone): the flag also keeps the
            // crowd's player scan running, which PlayerSeat (the Lingering Sip, table service) reads
            in.playerNear = false;
            ForPlayersOn(MapOf(c), [&](Player* p) {
                if (!p->IsInWorld() || !p->isGMVisible())
                    return true;
                if (_cfg.gmOnly && !FeatureFor(p))
                    return true;   // GmOnly: customers come only for a game master (nobody else can order)
                in.playerNear = p->GetExactDist2d(c.anchor.x, c.anchor.y) <= _cfg.nearPlayerRadius;
                return !in.playerNear;
            });
            for (uint32_t id : c.queue)
                if (Order const* o = OrderOf(id); o && o->kind != 'P' && o->state == 'W')
                    in.queueOrder.push_back(o->customerGuid);
            inputs.push_back(std::move(in));
        }
        _inCrowdUpdate = true;
        CafeCrowd::Instance().Update(static_cast<uint32_t>(nowMs - _epochMs), inputs);
        _inCrowdUpdate = false;
        // what the sink callbacks asked of the crowd runs now, outside its own update
        std::vector<std::function<void()>> calls;
        calls.swap(_crowdCalls);
        for (auto& call : calls)
            call();
    }

    uint32_t Cafe::NpcArrived(uint8_t cafeId, uint8_t personaIdx, uint64_t creatureGuid, uint32_t groupId)
    {
        CafeRt* c = CafeOf(cafeId);
        if (!c || !Enabled() || c->open != 1 || personaIdx >= D::Personas.size() || !_cfg.customers)
            return 0;
        D::Persona const& p = D::Personas[personaIdx];
        if (p.cafeId != cafeId || QueueLen(cafeId) >= QueueCap(cafeId))
            return 0;
        uint64_t const now = Mgr::NowMs();
        Order o;
        o.id = NewOrderId();
        o.cafeId = cafeId;
        o.kind = groupId ? 'G' : 'N';
        o.groupId = groupId;
        if (groupId)
            for (auto const& [id, other] : _orders)
                if (other.groupId == groupId && other.cafeId == cafeId)
                    ++o.member;
        o.customerGuid = creatureGuid;
        o.personaIdx = personaIdx;
        o.customer = std::string(p.name);
        uint8_t const n = R::PickRecipeN(p, o.member, MaxBaristaLevelAt(cafeId), Random(100), Random(100000));
        o.recipeId = D::RecipeId(cafeId, n);
        o.createdMs = now;
        o.patienceMaxMs = R::QueuePatienceMs(_cfg.queuePatienceSec, p.patiencePct, RushLive(cafeId));
        o.patienceEndMs = now + o.patienceMaxMs;
        o.orderLine = R::OrderLine(p, n, o.member, DrinkName(o.recipeId), CafeInfo(cafeId).linePool, Random(100000));
        uint32_t const id = o.id;
        _orders[id] = o;
        Order& stored = _orders[id];
        QueueOrder(*c, stored, false);
        // nobody on shift: the customer orders from the owner, and the house makes it (it never times out)
        if (!BaristasAt(cafeId))
            HouseTakes(stored, false, now);
        MarkCafeBaristas(cafeId, VQueue);
        return id;
    }

    void Cafe::NpcGone(uint32_t orderId)
    {
        Order* o = OrderOf(orderId);
        if (!o || o->kind == 'P')
            return;
        DropLeftovers(*o, "The customer has gone.");
        RemoveOrder(orderId);
    }

    void Cafe::HouseStepStarted(uint32_t orderId, uint8_t stepIndex, uint8_t actionId, uint32_t durMs, uint64_t workerGuid)
    {
        Order* o = OrderOf(orderId);
        if (!o)
            return;
        o->houseStep = stepIndex;
        o->houseAction = actionId;
        o->houseStepMs = Mgr::NowMs();
        o->houseStepDurMs = durMs;
        D::StaffMember const* st = D::FindStaff(ObjectGuid(workerGuid).GetEntry());
        o->houseWorker = st ? std::string(st->name) : std::string("The house");
        // a player's drink: the worker who starts it says so with its own line, once (a re-queued job starts again)
        if (o->kind == 'P' && st && !o->houseLineSaid)
        {
            o->houseLineSaid = true;
            Say(o->cafeId, st->role, st->entry, R::HouseLineKey(st->entry, o->takeover));
        }
        if (CafeRt* c = CafeOf(o->cafeId))
            c->atDirty = true;
        if (o->kind == 'P')
            SendOrderState(*o);
    }

    void Cafe::HouseDone(uint32_t orderId)
    {
        Order* o = OrderOf(orderId);
        if (!o || o->state != 'H')
            return;
        uint64_t const now = Mgr::NowMs();
        o->houseStepMs = 0;
        o->quality = 'G';
        o->rushServed = RushLive(o->cafeId);
        if (CafeRt* c = CafeOf(o->cafeId))
        {
            c->atDirty = true;
            if (c->servedTodayDay != _dayId)
            {
                c->servedTodayDay = _dayId;
                c->servedToday = 0;
            }
            ++c->servedToday;
        }
        if (o->kind == 'P')
        {
            OrderReady(*o, now);
            return;
        }
        // an ambient NPC order: served Good, no rewards to anybody
        D::Recipe const* r = D::FindRecipe(o->recipeId);
        o->state = 'R';
        o->readyUntilMs = now + NpcCupWaitMs;
        Unqueue(*o);
        uint32_t const cupGo = r ? R::PieceEntry(r->tableCup, _cfg.useNewArt && _newArtOk) : 0;
        uint32_t const cupItem = r ? r->cupItem : 0;
        std::string const thanks = ThanksOf(*o);
        uint32_t const id = orderId;
        CrowdCall([id, thanks, cupItem, cupGo]() { CafeCrowd::Instance().OrderServed(id, 'G', thanks, cupItem, cupGo); });
        MarkCafeBaristas(o->cafeId, VQueue);
    }

    void Cafe::CupTaken(uint32_t orderId)
    {
        Order* o = OrderOf(orderId);
        if (o && o->kind != 'P')
            RemoveOrder(orderId);
    }

    void Cafe::Delivered(uint32_t orderId)
    {
        Order* o = OrderOf(orderId);
        if (!o || o->kind != 'P' || o->state != 'R')
            return;
        Player* cu = ObjectAccessor::FindConnectedPlayer(ObjectGuid(o->customerGuid));
        if (!cu)
        {
            o->deliverSent = false;   // the pickup rule again (or the expiry refund)
            return;
        }
        // the busser's table-service line (section 2.2; only Cafe knows the drink's name), then the drink
        Say(o->cafeId, "staff_busser", CafeInfo(o->cafeId).busser, "tableService", DrinkName(o->recipeId));
        Deliver(*o, cu);
    }

    // =============================================================================================================
    // Rewards (section 3.9)
    // =============================================================================================================
    uint32_t Cafe::AuraLeftMs(Player* player, uint32_t spellId) const
    {
        if (Aura* a = player->GetAura(spellId))
            return a->GetDuration() > 0 ? static_cast<uint32_t>(a->GetDuration()) : 0;
        return 0;
    }

    void Cafe::GrantDrink(Player* player, uint16_t recipeId, bool perfect, bool rush, uint32_t minutesOverride)
    {
        D::Recipe const* r = D::FindRecipe(recipeId);
        if (!r || !player)
            return;
        // the team's cafe gives its own buffs
        uint32_t const spell = FamilySpell(CafeInfo(TeamCafe(player)), r->family);
        uint32_t const minutes = minutesOverride ? minutesOverride : R::BuffMinutes(r->tier, perfect, rush, false, _cfg.buffMaxMin);
        uint32_t newMs = minutes * 60000;
        if (Aura* a = player->GetAura(spell))
        {
            newMs = R::MergeBuffMs(a->GetDuration() > 0 ? static_cast<uint32_t>(a->GetDuration()) : 0, newMs);
            a->SetMaxDuration(static_cast<int32_t>(newMs));
            a->SetDuration(static_cast<int32_t>(newMs));
        }
        else if (Aura* added = player->AddAura(spell, player))
        {
            added->SetMaxDuration(static_cast<int32_t>(newMs));
            added->SetDuration(static_cast<int32_t>(newMs));
        }
        if (r->family == 'M')
        {
            if (Aura* helper = player->GetAura(D::SpellSprint))
            {
                helper->SetMaxDuration(static_cast<int32_t>(newMs));
                helper->SetDuration(static_cast<int32_t>(newMs));
            }
            _shakePlayers.insert(Low(player));
        }
        _buffPlayers.insert(Low(player));
        // Lingering Sip (section 3.9.4): this drink may still earn its +10 minutes at a cafe table
        R::Linger& l = _lingers[Low(player)];
        l = R::Linger();
        l.spell = spell;
        l.receivedMs = Mgr::NowMs();
        MarkView(Raw(player), VBuffs);
    }

    // The 1 s pass of Lingering Sip: seated in a cafe chair within 120 s of the drink and for 60 s, the drink's buff
    // gets +10 minutes within Buff.MaxMin, once.
    void Cafe::TickLingers(uint64_t nowMs)
    {
        for (auto it = _lingers.begin(); it != _lingers.end();)
        {
            Player* p = ObjectAccessor::FindPlayerByLowGUID(it->first);
            Aura* buff = p && p->IsInWorld() ? p->GetAura(it->second.spell) : nullptr;
            if (!buff)
            {
                it = _lingers.erase(it);
                continue;
            }
            uint64_t const guid = Raw(p);
            bool seated = false;
            for (CafeRt const& c : _cafes)
                seated = seated || (c.crowdSpawned && p->GetMapId() == c.map && CafeCrowd::Instance().PlayerSeat(c.id, guid));
            R::LingerStep const step = R::LingerTick(it->second, seated, nowMs);
            if (step == R::LingerStep::Wait)
            {
                ++it;
                continue;
            }
            if (step == R::LingerStep::Grant)
            {
                uint32_t const left = buff->GetDuration() > 0 ? static_cast<uint32_t>(buff->GetDuration()) : 0;
                int32_t const ms = static_cast<int32_t>(R::LingerMs(left, _cfg.buffMaxMin));
                buff->SetMaxDuration(ms);
                buff->SetDuration(ms);
                if (it->second.spell == D::Cafes[0].buffShake || it->second.spell == D::Cafes[1].buffShake)
                    if (Aura* helper = p->GetAura(D::SpellSprint))
                    {
                        helper->SetMaxDuration(ms);
                        helper->SetDuration(ms);
                    }
                MarkView(guid, VBuffs);   // CAFBF shows the longer buff
                LOG_DEBUG("module", "[Bleakhold] Cafe: {} lingers at a cafe table: buff {} now {} min", p->GetName(),
                    it->second.spell, ms / 60000);
            }
            it = _lingers.erase(it);
        }
    }

    void Cafe::GiveItem(Player* player, uint32_t lowGuid, uint32_t itemId, uint8_t cafeId, std::string_view why)
    {
        if (!itemId)
            return;
        if (player && player->HasItemCount(itemId, 1, true))
            return;
        if (player)
        {
            ItemPosCountVec dest;
            if (player->CanStoreNewItem(NULL_BAG, NULL_SLOT, dest, itemId, 1) == EQUIP_ERR_OK)
                if (Item* item = player->StoreNewItem(dest, itemId, true))
                {
                    player->SendNewItem(item, 1, true, false);
                    return;
                }
        }
        // bags full or offline: by mail from the owner
        CharacterDatabaseTransaction trans = CharacterDatabase.BeginTransaction();
        MailDraft draft(std::string(CafeInfo(cafeId).name) + ": " + std::string(why), "Well earned. Wear it with pride.");
        if (Item* item = Item::CreateItem(itemId, 1))
        {
            item->SaveToDB(trans);
            draft.AddItem(item);
        }
        draft.SendMailTo(trans, MailReceiver(player, lowGuid), MailSender(MAIL_CREATURE, CafeInfo(cafeId).owner),
            MAIL_CHECK_MASK_NONE);
        CharacterDatabase.CommitTransaction(trans);
    }

    // Section 3.9.5: at a level-up, and at login for whatever the flags say is still missing.
    void Cafe::GrantLevelRewards(Player* player, Barista& b, bool announce)
    {
        if (!player)
            return;
        uint8_t const cafeId = TeamCafe(player);
        D::Cafe const& cd = CafeInfo(cafeId);
        if (b.level >= 5 && !(b.flags & CafeRewardApprentice))
        {
            GiveItem(player, b.low, cd.apronApprentice, cafeId, "your apron");
            b.flags |= CafeRewardApprentice;
            b.dirty = true;
        }
        if (b.level >= 10 && !(b.flags & CafeRewardMaster))
        {
            GiveItem(player, b.low, cd.apronMaster, cafeId, "your apron");
            b.flags |= CafeRewardMaster;
            b.dirty = true;
            // the apron stays; the realm's first is left to the first player who gets there with the cafe open to all
            WorldSession const* session = player->GetSession();
            bool const gameMaster = session && session->GetSecurity() >= SEC_GAMEMASTER;
            if (R::ServerFirstCounts(announce, _gmOnly.load(), gameMaster))
                Ui::RecordServerFirst(cd.serverFirstKey, "cafe", cd.serverFirstText, player->GetName(), true);
        }
        auto title = [&](uint32_t id, uint32_t flag) {
            if (!id || (b.flags & flag))
                return;
            if (CharTitlesEntry const* t = sCharTitlesStore.LookupEntry(id))
            {
                if (!player->HasTitle(t))
                    player->SetTitle(t);
                b.flags |= flag;
                b.dirty = true;
            }
        };
        if (b.level >= 10)
            title(_cfg.titleBaristaId, CafeRewardTitle);
        if (b.weeklyWins >= _cfg.titleLegendWins)
            title(_cfg.titleLegendId, CafeRewardLegend);
    }

    void Cafe::TickAuras(uint64_t nowMs)
    {
        bool const on = Enabled();
        // the milkshake's speed helper: only while the rule holds, never longer than the visible buff
        for (auto it = _shakePlayers.begin(); it != _shakePlayers.end();)
        {
            Player* p = ObjectAccessor::FindPlayerByLowGUID(*it);
            if (!p || !p->IsInWorld())
            {
                ++it;
                continue;
            }
            uint32_t const visible = std::max(AuraLeftMs(p, D::Cafes[0].buffShake), AuraLeftMs(p, D::Cafes[1].buffShake));
            bool const hasVisible = p->HasAura(D::Cafes[0].buffShake) || p->HasAura(D::Cafes[1].buffShake);
            Aura* helper = p->GetAura(D::SpellSprint);
            R::ShakeFacts f;
            f.featureOn = on;
            f.visibleBuff = hasVisible;
            f.restCity = p->HasRestFlag(REST_FLAG_IN_CITY);
            f.restTavern = p->HasRestFlag(REST_FLAG_IN_TAVERN);
            f.inCombat = p->IsInCombat();
            f.pvp = p->IsPvP();
            f.ffaPvp = p->IsFFAPvP();
            f.duel = p->duel != nullptr;
            f.mounted = p->IsMounted();
            f.vehicle = p->GetVehicle() != nullptr;
            f.flight = p->IsInFlight();
            f.worldMap = p->GetMap() && p->GetMap()->IsWorldMap();
            f.alive = p->IsAlive();
            bool const active = R::ShakeActive(f);
            uint32_t const helperMs = helper && helper->GetDuration() > 0 ? static_cast<uint32_t>(helper->GetDuration()) : 0;
            switch (R::ShakeHelper(active, helper != nullptr, helperMs, visible))
            {
                case R::HelperAction::Add:
                    if (Aura* a = p->AddAura(D::SpellSprint, p))
                    {
                        a->SetMaxDuration(static_cast<int32_t>(visible));
                        a->SetDuration(static_cast<int32_t>(visible));
                    }
                    MarkView(Raw(p), VBuffs);
                    break;
                case R::HelperAction::Remove:
                    p->RemoveAurasDueToSpell(D::SpellSprint);
                    MarkView(Raw(p), VBuffs);
                    break;
                case R::HelperAction::Follow:
                    helper->SetMaxDuration(static_cast<int32_t>(visible));
                    helper->SetDuration(static_cast<int32_t>(visible));
                    break;
                default:
                    break;
            }
            if (!hasVisible && !p->HasAura(D::SpellSprint))
                it = _shakePlayers.erase(it);
            else
                ++it;
        }
        if (!on)
            return;
        TickLingers(nowMs);
        // Tired (from the barista row) and the Best Barista crown, re-applied to the living
        for (auto& [low, b] : _baristas)
        {
            if (b.expireMs)
                continue;
            Player* p = ObjectAccessor::FindPlayerByLowGUID(low);
            if (!p || !p->IsInWorld() || !p->IsAlive())
                continue;
            bool const tired = R::IsTired(b.tired, NowSec(), _cfg.tiredAfterMin, _cfg.tiredRestMin);
            if (tired && !p->HasAura(D::SpellTired))
                p->AddAura(D::SpellTired, p);
            else if (!tired && p->HasAura(D::SpellTired))
                p->RemoveAurasDueToSpell(D::SpellTired);
            if (b.crownUntil > NowSec() && !p->HasAura(D::SpellBestBarista))
                if (Aura* a = p->AddAura(D::SpellBestBarista, p))
                {
                    int32_t const ms = static_cast<int32_t>(std::min<uint64_t>(uint64_t(b.crownUntil - NowSec()) * 1000, 0x7FFFFFFF));
                    a->SetMaxDuration(ms);
                    a->SetDuration(ms);
                }
        }
        // CAFBF every 60 s while a cafe buff runs (the client's timers resync)
        for (auto it = _buffPlayers.begin(); it != _buffPlayers.end();)
        {
            Player* p = ObjectAccessor::FindPlayerByLowGUID(*it);
            if (!p)
            {
                it = _buffPlayers.erase(it);
                continue;
            }
            bool any = false;
            for (D::Cafe const& cd : D::Cafes)
                for (uint32_t s : { cd.buffCoffee, cd.buffTea, cd.buffShake })
                    any = any || p->HasAura(s);
            View& v = _views[Raw(p)];
            if (any && nowMs - v.buffsSentMs >= BuffResyncMs)
                v.dirty |= VBuffs;
            if (!any)
            {
                v.dirty |= VBuffs;
                it = _buffPlayers.erase(it);
            }
            else
                ++it;
        }
        // bystanders who walked up to a bar get its current strip
        for (CafeRt& c : _cafes)
            if (c.crowdSpawned)
                SendAtBar(c, nowMs, true);
    }

    bool Cafe::HasCoffee(Player* player) const
    {
        return player && (player->HasAura(D::Cafes[0].buffCoffee) || player->HasAura(D::Cafes[1].buffCoffee));
    }

    bool Cafe::HasTea(Player* player) const
    {
        return player && (player->HasAura(D::Cafes[0].buffTea) || player->HasAura(D::Cafes[1].buffTea));
    }

    uint32_t Cafe::CoffeeXpPct() const { return Enabled() ? _coffeePct.load() : 0; }
    uint32_t Cafe::TeaRepPct() const { return Enabled() ? _teaPct.load() : 0; }

    bool Cafe::RewardPlaceOk(Player* player) const
    {
        if (!player || !player->GetMap())
            return false;
        return R::RewardPlaceOk(player->GetMap()->IsBattlegroundOrArena(),
            sBattlefieldMgr->GetBattlefieldToZoneId(player->GetZoneId()) != nullptr);
    }

    bool Cafe::TeaExcludesFaction(uint32_t faction) const
    {
        uint32_t const n = std::min<uint32_t>(_teaExcludedCount.load(), MaxExcluded);
        for (uint32_t i = 0; i < n; ++i)
            if (_teaExcluded[i].load() == faction)
                return true;
        return false;
    }

    // =============================================================================================================
    // Protocol: intents (section 21)
    // =============================================================================================================
    void Cafe::HandleShift(Player* player, Intent const& in)
    {
        if (in.cafeOn)
        {
            if (ShiftOf(player))
                return Refuse(player, in, CafeErr::Account.code, "You are already working a shift.");
            StartShift(player, in.cafeId, &in);
            return;
        }
        Shift* s = ShiftOf(player);
        if (!s || s->cafeId != in.cafeId)
            return Refuse(player, in, CafeErr::Shift);
        EndShift(*s, static_cast<char>(CafeShiftEnd::Player), Mgr::NowMs());
    }

    void Cafe::HandleTake(Player* player, Intent const& in)
    {
        Shift* s = ShiftOf(player);
        if (!s)
            return Refuse(player, in, CafeErr::Shift);
        CafeRt* c = CafeOf(s->cafeId);
        if (!c || c->open == 2)
            return Refuse(player, in, CafeErr::Paused);
        if (Hidden(player))
            return Refuse(player, in, CafeErr::Mounted);
        uint64_t const now = Mgr::NowMs();
        UpdateStation(player, *s, now);
        if (s->station != 'V')
            return Refuse(player, in, CafeErr::Station.code, StationText('V'));
        Barista& b = BaristaOf(player);
        if (s->tickets.size() >= R::Tickets(b.level))
            return Refuse(player, in, CafeErr::Full);
        WorldSession* session = player->GetSession();
        std::string const ip = session ? session->GetRemoteAddress() : std::string();
        auto self = [&](Order const& o) {
            return o.kind == 'P' && (o.customerAccount == s->account || (!ip.empty() && o.customerIp == ip));
        };
        Order* o = nullptr;
        if (in.orderId)
        {
            o = OrderOf(in.orderId);
            if (!o || o->cafeId != s->cafeId || o->state != 'W')
                return Refuse(player, in, CafeErr::Taken);
            if (self(*o))
                return Refuse(player, in, CafeErr::Self);
            D::Recipe const* r = D::FindRecipe(o->recipeId);
            if (r && !R::Unlocked(b.level, *r))
                return Refuse(player, in, CafeErr::Locked.code,
                    "You need barista level " + std::to_string(r->unlock) + " for that drink.");
        }
        else
        {
            // the best I can make: the oldest player order, then the queue front
            for (uint32_t id : c->queue)
            {
                Order* cand = OrderOf(id);
                if (!cand || cand->state != 'W' || self(*cand))
                    continue;
                D::Recipe const* r = D::FindRecipe(cand->recipeId);
                if (!r || !R::Unlocked(b.level, *r))
                    continue;
                o = cand;
                break;
            }
            if (!o)
                return Refuse(player, in, CafeErr::Taken);
        }
        D::Recipe const* r = D::FindRecipe(o->recipeId);
        if (!r)
            return Refuse(player, in, CafeErr::Taken);
        // Take Order: a short visible cast at the counter
        if (player->IsNonMeleeSpellCast(false, false, true))
            player->InterruptNonMeleeSpells(false);
        player->SetSheath(SHEATH_STATE_UNARMED);
        if (D::Action const* take = D::FindAction(D::ActionTakeOrder))
        {
            player->HandleEmoteCommand(take->emoteOneShot);
            player->CastSpell(player, take->spell, StepCastFlags);
        }
        Ticket t;
        t.id = _nextTicketId++;
        t.orderId = o->id;
        t.recipeId = o->recipeId;
        t.grades.fill('N');
        t.takenMs = now;
        t.tutorial = !(b.flags & FlagTutorialDone);
        s->tickets.push_back(t);
        s->lastActionMs = now;
        o->state = 'T';
        o->ticketId = t.id;
        o->baristaGuid = s->guid;
        o->baristaLow = s->low;
        o->baristaName = s->name;
        o->queuePhase = false;
        uint32_t const pct = o->personaIdx >= 0 ? D::Personas[static_cast<std::size_t>(o->personaIdx)].patiencePct : 100;
        o->patienceMaxMs = R::DrinkPatienceMs(_cfg.drinkPatienceSec, _cfg.perLineSec, r->lines, pct, RushLive(s->cafeId));
        o->patienceEndMs = now + o->patienceMaxMs;
        if (o->kind == 'P')
        {
            SaveOrderState(*o);
            SendOrderState(*o);
            if (o->viaGossip)
                if (Player* cu = ObjectAccessor::FindConnectedPlayer(ObjectGuid(o->customerGuid)))
                    Tell(cu, s->name + " is making your " + DrinkName(o->recipeId) + ".");
        }
        else if (!o->lineSaid)
        {
            // the customer says its order now and walks to the pickup spot (a returned order does not repeat it)
            o->lineSaid = true;
            uint32_t const id = o->id;
            std::string const line = o->orderLine;
            CrowdCall([id, line]() { CafeCrowd::Instance().OrderTaken(id, line); });
        }
        MarkView(s->guid, VTickets | VState);
        MarkCafeBaristas(s->cafeId, VQueue);
        if (c)
            c->atDirty = true;
    }

    void Cafe::HandleStep(Player* player, Intent const& in)
    {
        Shift* s = ShiftOf(player);
        if (!s)
            return Refuse(player, in, CafeErr::Shift);
        if (!player->IsAlive())
            return Refuse(player, in, CafeErr::Dead);
        CafeRt* c = CafeOf(s->cafeId);
        if (!c || c->open == 2)
            return Refuse(player, in, CafeErr::Paused);
        if (Hidden(player))
            return Refuse(player, in, CafeErr::Mounted);
        Ticket* t = TicketOf(*s, in.ticketId);
        D::Recipe const* r = t ? D::FindRecipe(t->recipeId) : nullptr;
        D::Action const* a = D::FindAction(in.actionId);
        if (!t || !r || !a || in.stepIndex != t->next + 1u || t->next >= r->stepCount)
        {
            MarkView(s->guid, VTickets);   // CAFT follows: the client was out of step
            return Refuse(player, in, CafeErr::Ticket);
        }
        for (Ticket const& other : s->tickets)
            if (other.step.active)
                return Refuse(player, in, CafeErr::Busy);
        for (Ticket const& other : s->tickets)
            if (other.id != t->id && other.next > 0)
                return Refuse(player, in, CafeErr::Hands);
        uint64_t const now = Mgr::NowMs();
        UpdateStation(player, *s, now);
        if (s->station != a->station)
            return Refuse(player, in, CafeErr::Station.code, StationText(a->station));
        s->lastActionMs = now;
        if (in.actionId == D::ActionBin)
        {
            // the cup goes in the bin: back to step 1, the streak breaks
            player->HandleEmoteCommand(a->emoteOneShot);
            player->CastSpell(player, a->spell, StepCastFlags);
            t->next = 0;
            t->grades.fill('N');
            s->streak = 0;
            SendStepEvent(player, *t, in.stepIndex, in.actionId, CafeStepEventKind::Binned, std::nullopt, 'N');
            MarkView(s->guid, VTickets | VState);
            return;
        }
        if (in.actionId != r->steps[t->next])
        {
            if (t->tutorial)
            {
                SendStepEvent(player, *t, in.stepIndex, in.actionId, CafeStepEventKind::TutorialWrong, std::nullopt, 'N');
                return;
            }
            // RUINED: the cup is binned and the ticket starts again; the patience keeps running
            t->next = 0;
            t->grades.fill('N');
            ++t->ruins;
            s->streak = 0;
            SendStepEvent(player, *t, in.stepIndex, in.actionId, CafeStepEventKind::Wrong, std::nullopt, 'N');
            MarkView(s->guid, VTickets | VState);
            if (Order* o = OrderOf(t->orderId); o && o->kind == 'P')
                SendOrderState(*o);
            return;
        }
        StartStep(player, *s, *t, in.actionId, now);
        MarkView(s->guid, VTickets);
    }

    void Cafe::HandleRelease(Player* player, Intent const& in)
    {
        Shift* s = ShiftOf(player);
        if (!s)
            return Refuse(player, in, CafeErr::Shift);
        Ticket* t = TicketOf(*s, in.ticketId);
        if (!t || !t->step.active || !t->step.timed || in.stepIndex != t->step.index + 1u)
            return Refuse(player, in, CafeErr::Ticket);
        uint64_t const now = Mgr::NowMs();
        uint32_t const serverElapsed = static_cast<uint32_t>(std::min<uint64_t>(now - t->step.startMs, 0xFFFFFFFFull));
        WorldSession* session = player->GetSession();
        uint32_t const latency = session ? session->GetLatency() : 0;
        uint32_t const elapsed = R::ReleaseElapsed(in.clientMs, serverElapsed, latency, _cfg.releaseSlackMs,
            _cfg.latencyCompMaxMs);
        char const grade = R::Grade(elapsed, t->step.durMs, t->step.goldLoMs, t->step.goldHiMs, _cfg.goodPadPermille);
        if (s->releaseOffsets.size() < 4096)
            s->releaseOffsets.push_back(R::ReleaseOffset(elapsed, t->step.goldLoMs, t->step.goldHiMs));
        s->lastActionMs = now;
        CompleteStep(player, *s, *t, grade, now);
    }

    void Cafe::HandleOrder(Player* player, Intent const& in)
    {
        // section 3.8.1, in its order (1, the feature, is Mgr::Dispatch's)
        CafeRt* c = CafeOf(in.cafeId);
        if (!c || !c->placed || !_cfg.orders)
            return Refuse(player, in, CafeErr::Closed);
        if (c->open == 2)
            return Refuse(player, in, CafeErr::Paused);
        if (c->open != 1)
            return Refuse(player, in, CafeErr::Closed);
        if (TeamCafe(player) != c->id)
            return Refuse(player, in, CafeErr::Faction);
        if (!player->IsInWorld() || !player->IsAlive())
            return Refuse(player, in, CafeErr::Dead);
        if (player->IsInCombat())
            return Refuse(player, in, CafeErr::Combat);
        if (!InRange(player, *c, _cfg.orderRadius))
            return Refuse(player, in, CafeErr::Where);
        if (ShiftOf(player))
            return Refuse(player, in, CafeErr::ShiftOrder);
        if (PendingOrderOf(Low(player)))
            return Refuse(player, in, CafeErr::Order);
        Barista& b = BaristaOf(player);
        RollDay(b);
        if (b.day.ordersPlaced >= _cfg.maxOrdersPerDay)
            return Refuse(player, in, CafeErr::Order.code, "You have ordered " + std::to_string(_cfg.maxOrdersPerDay) +
                " drinks today. Come back tomorrow.");
        if (PendingPlayerOrders(c->id) >= _cfg.maxPendingPerCafe)
            return Refuse(player, in, CafeErr::Cap);
        if (!OwnRecipe(c->id, in.recipeId))
            return Refuse(player, in, CafeErr::Ticket);
        if (!IsCafeTipPct(in.tipPct))
            return;   // the parser never lets one through
        D::Recipe const* r = D::FindRecipe(in.recipeId);
        D::Tier const* tier = r ? R::TierOf(r->tier) : nullptr;
        if (!tier)
            return Refuse(player, in, CafeErr::Ticket);
        uint32_t const price = R::PriceCopper(tier->price80, player->GetLevel(), _cfg.priceMinCopper, _cfg.priceLevelFloorPct);
        uint32_t const tip = R::TipCopper(price, in.tipPct);
        if (!player->HasEnoughMoney(price + tip))
            return Refuse(player, in, CafeErr::Gold);
        uint64_t const now = Mgr::NowMs();
        Order o;
        o.id = NewOrderId();
        o.cafeId = c->id;
        o.kind = 'P';
        o.recipeId = in.recipeId;
        o.customerGuid = Raw(player);
        o.customerLow = Low(player);
        WorldSession* session = player->GetSession();
        o.customerAccount = session ? session->GetAccountId() : 0;
        o.customerIp = session ? session->GetRemoteAddress() : std::string();
        o.customer = player->GetName();
        o.createdMs = now;
        o.price = price;
        o.tip = tip;
        o.sharePct = static_cast<uint8_t>(std::min<uint32_t>(_cfg.baristaSharePct, 100));   // every split of it uses this
        o.takeDeadlineMs = now + uint64_t(_cfg.takeTimeoutSec) * 1000;
        o.patienceMaxMs = _cfg.takeTimeoutSec * 1000;
        o.patienceEndMs = o.takeDeadlineMs;
        o.viaGossip = in.seq == 0 && !Ui::HasClientCap(player, ClientCapCafeUi);
        if (!PayOrder(player, o))
            return Refuse(player, in, CafeErr::Gold);
        ++b.day.ordersPlaced;
        b.day.dirty = true;
        b.dirty = true;
        uint32_t const id = o.id;
        _orders[id] = o;
        Order& stored = _orders[id];
        QueueOrder(*c, stored, false);
        LOG_INFO("module", "[Bleakhold] Cafe money: order {}: {} paid {}c (price {}c, tip {}c) at {}", id, o.customer,
            price + tip, price, tip, CafeInfo(c->id).name);
        SendOrderState(stored);
        if (stored.viaGossip)
            Tell(player, "Your " + DrinkName(o.recipeId) + " is in the queue.");
        if (!BaristasAt(c->id))
            HouseTakes(stored, false, now);
        MarkCafeBaristas(c->id, VQueue);
    }

    void Cafe::HandleCancel(Player* player, Intent const& in)
    {
        Order* o = OrderOf(in.orderId);
        if (!o || o->kind != 'P' || o->customerLow != Low(player))
            return Refuse(player, in, CafeErr::Taken);
        if (!R::CancelAllowed(o->state, o->takeover))
            return Refuse(player, in, CafeErr::Taken.code, "A barista is making it now; it can no longer be cancelled.");
        LOG_INFO("module", "[Bleakhold] Cafe money: order {} cancelled by {}: {}c refunded", o->id, o->customer,
            o->price + o->tip);
        RefundAll(*o, "cancelled");
    }

    void Cafe::HandleStaff(Player* player, Intent const& in)
    {
        Barista& b = BaristaOf(player);
        D::Recipe const* r = D::FindRecipe(in.recipeId);
        if (!b.staffOffer || b.staffDay == _dayId || b.level < StaffDrinkLevel || !r || r->cafeId != TeamCafe(player) ||
            !R::Unlocked(b.level, *r) || ShiftOf(player))
            return Refuse(player, in, CafeErr::Staff);
        b.staffOffer = false;
        b.staffDay = _dayId;
        b.dirty = true;
        GrantDrink(player, r->id, false, false, StaffDrinkMin);
        MarkView(Raw(player), VState);
        SaveBarista(b);
    }

    // =============================================================================================================
    // Protocol: GET and the views (section 3.13.4)
    // =============================================================================================================
    void Cafe::Provide(Player* player, TopicRequest const& req)
    {
        if (!FeatureFor(player))
            return;
        switch (req.topic)
        {
            case Topic::CafeList:
                Ui::SendCafeList(player, BuildCafeList());
                break;
            case Topic::CafeState:
                Ui::SendCafeState(player, BuildState(player));
                break;
            case Topic::CafeQueue:
            {
                uint8_t cafeId = 0;
                if (Shift* s = ShiftOf(player))
                    cafeId = s->cafeId;
                else
                    for (CafeRt const& c : _cafes)
                        if (InRange(player, c, _cfg.orderRadius))
                            cafeId = c.id;
                if (cafeId)
                    Ui::SendCafeQueue(player, BuildQueue(cafeId, player));
                break;
            }
            case Topic::CafeTickets:
                if (ShiftOf(player))
                    Ui::SendCafeTickets(player, BuildTickets(player));
                break;
            case Topic::CafeMenu:
                if (req.arg1 == TeamCafe(player))
                    Ui::SendCafeMenu(player, BuildMenu(player, static_cast<uint8_t>(req.arg1)));
                break;
            case Topic::CafeOrderState:
                Ui::SendCafeOrder(player, BuildOrder(player));
                break;
            case Topic::CafeProfile:
                Ui::SendCafeProfile(player, BuildProfile(player));
                break;
            case Topic::CafeBuffs:
                Ui::SendCafeBuffs(player, BuildBuffs(player));
                break;
            default:
                break;
        }
    }

    void Cafe::OnHello(Player* player)
    {
        if (!FeatureFor(player))
            return;
        Ui::SendCafeList(player, BuildCafeList());
        Ui::SendCafeBuffs(player, BuildBuffs(player));
        if (Shift* s = ShiftOf(player))
        {
            Ui::SendCafeState(player, BuildState(player));
            Ui::SendCafeTickets(player, BuildTickets(player));
            Ui::SendCafeQueue(player, BuildQueue(s->cafeId, player));
        }
        if (PendingOrderOf(Low(player)))
            Ui::SendCafeOrder(player, BuildOrder(player));
    }

    void Cafe::MarkView(uint64_t guid, uint8_t bits)
    {
        _views[guid].dirty |= bits;
    }

    void Cafe::MarkCafeBaristas(uint8_t cafeId, uint8_t bits)
    {
        for (auto const& [g, s] : _shifts)
            if (s.cafeId == cafeId)
                MarkView(g, bits);
    }

    CafeList Cafe::BuildCafeList()
    {
        CafeList list;
        uint32_t const now = NowSec();
        int64_t const local = int64_t(now) + LocalUtcOffsetSec();
        R::RushClock const clock = R::RushAt(local, _cfg.rushTimes, _cfg.rushMinutes, _cfg.rushWarnMinutes);
        for (CafeRt const& c : _cafes)
        {
            CafeListRow row;
            row.cafeId = c.id;
            row.open = Enabled() ? static_cast<CafeOpen>(c.placed && c.enabled ? c.open : 3) : CafeOpen::Off;
            row.baristas = BaristasAt(c.id);
            row.queueLen = QueueLen(c.id);
            row.rushState = static_cast<CafeRushState>(c.rushState);
            if (c.rushState == 2)
            {
                uint64_t const nowMs = Mgr::NowMs();
                row.rushSec = c.rushEndMs > nowMs ? static_cast<uint32_t>((c.rushEndMs - nowMs + 999) / 1000) : 0;
            }
            else if (c.rushState == 1)
                row.rushSec = clock.state == 1 ? clock.secTo : 0;
            row.houseEtaSec = c.crowdSpawned ? CafeCrowd::Instance().HouseEtaSec(c.id, std::nullopt) : 0;
            list.rows.push_back(row);
        }
        return list;
    }

    CafeState Cafe::BuildState(Player* player)
    {
        CafeState st;
        Barista& b = BaristaOf(player);
        RollDay(b);
        uint32_t const now = NowSec();
        st.level = b.level;
        st.xp = b.xp;
        st.levelXp = R::LevelXp(b.level);
        st.nextLevelXp = R::NextLevelXp(b.level);
        st.maxTickets = R::Tickets(b.level);
        Shift* s = ShiftOf(player);
        bool const tired = R::IsTired(b.tired, now, _cfg.tiredAfterMin, _cfg.tiredRestMin);
        uint32_t flags = 0;
        if (!(b.flags & FlagTutorialDone))
            flags |= CafeFlagTutorial;
        if (b.level >= MemoryLevel)
            flags |= CafeFlagMemory;
        if (tired)
            flags |= CafeFlagTired;
        if (b.staffOffer && b.staffDay != _dayId && b.level >= StaffDrinkLevel)
            flags |= CafeFlagStaffDrink;
        st.tiredSec = R::TiredSec(b.tired, now, s != nullptr, _cfg.tiredAfterMin, _cfg.tiredRestMin);
        if (s)
        {
            st.cafeId = s->cafeId;
            st.onShift = true;
            st.shiftSec = now - s->startSec;
            st.drinks = s->drinks;
            st.perfects = s->perfects;
            st.streak = s->streak;
            st.tipsCopper = s->tips;
            st.shiftXp = s->xp;
            st.station = s->station;
            st.nearStation = s->nearStation;
            st.nearDm = s->nearStation ? s->nearDm : 0;
            flags |= s->warnFlags;
            if (s->facingHint)
                flags |= CafeFlagFacing;
            st.warnSec = s->warnSec;
            if (CafeRt const* c = CafeOf(s->cafeId))
            {
                CafeRush rush;
                rush.rushState = static_cast<CafeRushState>(c->rushState);
                if (c->rushState == 2)
                {
                    uint64_t const nowMs = Mgr::NowMs();
                    rush.rushSec = c->rushEndMs > nowMs ? static_cast<uint32_t>((c->rushEndMs - nowMs + 999) / 1000) : 0;
                }
                else if (c->rushState == 1)
                {
                    R::RushClock const clock = R::RushAt(int64_t(now) + LocalUtcOffsetSec(), _cfg.rushTimes,
                        _cfg.rushMinutes, _cfg.rushWarnMinutes);
                    rush.rushSec = clock.state == 1 ? clock.secTo : 0;
                }
                rush.rushServed = c->rushServed;
                rush.rushGoal = c->rushState == 2 ? c->rushGoal : _cfg.rushGoal;
                rush.myRushServed = s->rushServed;
                st.rush = rush;
            }
        }
        st.flags = flags;
        st.day.dayXpFull = _cfg.xpDailyFull;
        st.day.dayXpHalf = _cfg.xpDailyHalf;
        st.day.dayXp = std::min(b.day.xpFull, _cfg.xpDailyFull) + std::min(b.day.xpHalf, _cfg.xpDailyHalf) / 2;
        st.day.dayTipsCopper = b.day.tips;
        st.day.dayTipsCapCopper = R::TipCap(_cfg.tipDailyBaseCopper, _cfg.tipDailyPerLevelCopper, player->GetLevel());
        st.day.dayPoints = b.day.points;
        uint8_t const cafeId = s ? s->cafeId : TeamCafe(player);
        CafeRt const* c = CafeOf(cafeId);
        st.day.dayPointsCap = R::PointsCap(_cfg.pointsDailyCap, _cfg.pointsRushExtra, c && c->rushDayId == _dayId);
        st.day.dayDrinks = b.day.drinks;
        return st;
    }

    CafeQueue Cafe::BuildQueue(uint8_t cafeId, Player* receiver)
    {
        CafeQueue q;
        CafeRt const* c = CafeOf(cafeId);
        q.cafeId = cafeId;
        q.cap = QueueCap(cafeId);
        q.baristas = BaristasAt(cafeId);
        if (!c)
            return q;
        uint64_t const now = Mgr::NowMs();
        Shift* s = receiver ? ShiftOf(receiver) : nullptr;
        uint8_t const level = s ? BaristaOf(receiver).level : 0;
        for (uint32_t id : c->queue)
        {
            Order const* o = OrderOf(id);
            if (!o || o->state == 'R')
                continue;
            if (o->state == 'W')
                ++q.count;
            CafeQueueRow row;
            row.orderId = o->id;
            row.kind = static_cast<CafeOrderKind>(o->kind);
            row.recipeId = o->recipeId;
            row.customer = o->customer;
            if (o->state != 'H')
            {
                row.patienceMs = o->patienceEndMs > now ? static_cast<uint32_t>(o->patienceEndMs - now) : 0;
                row.patienceMaxMs = o->patienceMaxMs;
            }
            row.state = static_cast<CafeQueueState>(o->state);
            row.takenBy = o->state == 'T' ? o->baristaName : o->state == 'H' ? o->houseWorker : std::string();
            if (s)
                if (D::Recipe const* r = D::FindRecipe(o->recipeId); r && !R::Unlocked(level, *r))
                    row.needLevel = r->unlock;
            if (o->groupId)
                row.group = o->groupId;
            q.rows.push_back(row);
        }
        return q;
    }

    CafeTickets Cafe::BuildTickets(Player* player)
    {
        CafeTickets out;
        Shift* s = ShiftOf(player);
        if (!s)
            return out;
        Barista& b = BaristaOf(player);
        uint64_t const now = Mgr::NowMs();
        for (Ticket const& t : s->tickets)
        {
            Order const* o = OrderOf(t.orderId);
            D::Recipe const* r = D::FindRecipe(t.recipeId);
            if (!o || !r)
                continue;
            CafeTicket ct;
            ct.ticketId = t.id;
            ct.orderId = o->id;
            ct.recipeId = t.recipeId;
            ct.kind = static_cast<CafeOrderKind>(o->kind);
            ct.customer = o->customer;
            ct.patienceMs = o->patienceEndMs > now ? static_cast<uint32_t>(o->patienceEndMs - now) : 0;
            ct.patienceMaxMs = o->patienceMaxMs;
            ct.nextStep = t.next + 1u;
            ct.inHand = t.next > 0;
            ct.orderLine = o->kind == 'P' ? std::string() : o->orderLine;
            for (uint8_t i = 0; i < r->stepCount; ++i)
            {
                char const g = t.grades[i];
                ct.steps.push_back({ r->steps[i], g == 'P' ? CafeGrade::Perfect : g == 'G' ? CafeGrade::Good :
                    g == 'O' ? CafeGrade::Off : CafeGrade::None });
            }
            if (o->kind == 'P')
                ct.tipHintCopper = R::WageCopper(o->price, o->tip, o->sharePct);
            else if (o->personaIdx >= 0)
                ct.tipHintCopper = R::TipForDrink(r->tier, 'G', D::Personas[static_cast<std::size_t>(o->personaIdx)].tipPct,
                    player->GetLevel(), RushLive(s->cafeId), b.level);
            out.tickets.push_back(std::move(ct));
        }
        return out;
    }

    CafeMenu Cafe::BuildMenu(Player* player, uint8_t cafeId)
    {
        CafeMenu m;
        CafeRt const* c = CafeOf(cafeId);
        m.cafeId = cafeId;
        if (!c)
            return m;
        Barista& b = BaristaOf(player);
        RollDay(b);
        m.open = static_cast<CafeOpen>(c->placed && c->enabled ? c->open : 3);
        m.baristas = BaristasAt(cafeId);
        m.houseEtaSec = c->crowdSpawned ? CafeCrowd::Instance().HouseEtaSec(cafeId, std::nullopt) : 0;
        if (Order const* o = PendingOrderOf(Low(player)))
            m.pendingOrderId = o->id;
        m.ordersToday = b.day.ordersPlaced;
        m.ordersCap = _cfg.maxOrdersPerDay;
        std::string_view reason;
        if (!c->placed || !_cfg.orders || c->open == 3 || c->open == 4)
            reason = CafeErr::Closed.code;
        else if (c->open == 2)
            reason = CafeErr::Paused.code;
        else if (TeamCafe(player) != cafeId)
            reason = CafeErr::Faction.code;
        else if (ShiftOf(player))
            reason = CafeErr::ShiftOrder.code;
        else if (m.pendingOrderId || m.ordersToday >= m.ordersCap)
            reason = CafeErr::Order.code;
        else if (PendingPlayerOrders(cafeId) >= _cfg.maxPendingPerCafe)
            reason = CafeErr::Cap.code;
        m.canOrder = reason.empty();
        m.reason = std::string(reason);
        uint8_t const maxLevel = MaxBaristaLevelAt(cafeId);
        bool const coffeeCounts = CoffeeXpPct() > 0 && player->GetLevel() < sWorld->getIntConfig(CONFIG_MAX_PLAYER_LEVEL) &&
            !player->HasPlayerFlag(PLAYER_FLAGS_NO_XP_GAIN);
        for (D::Recipe const& r : D::Recipes)
        {
            if (r.cafeId != cafeId)
                continue;
            D::Tier const* tier = R::TierOf(r.tier);
            CafeMenuRow row;
            row.recipeId = r.id;
            row.priceCopper = tier ? R::PriceCopper(tier->price80, player->GetLevel(), _cfg.priceMinCopper,
                _cfg.priceLevelFloorPct) : 0;
            row.byBarista = maxLevel >= r.unlock;
            row.effective = r.family == 'C' ? coffeeCounts : r.family == 'T' ? TeaRepPct() > 0 : true;
            m.rows.push_back(row);
        }
        return m;
    }

    CafeOrderState Cafe::BuildOrder(Player* player)
    {
        CafeOrderState st;
        Order const* o = PendingOrderOf(Low(player));
        if (!o)
            return st;
        uint64_t const now = Mgr::NowMs();
        D::Recipe const* r = D::FindRecipe(o->recipeId);
        st.orderId = o->id;
        st.cafeId = o->cafeId;
        st.recipeId = o->recipeId;
        st.priceCopper = o->price;
        st.tipCopper = o->tip;
        st.stepCount = r ? r->stepCount : 0;
        switch (o->state)
        {
            case 'W':
            {
                st.state = CafeOrderStateId::Queued;
                uint32_t pos = 0;
                if (CafeRt const* c = CafeOf(o->cafeId))
                    for (uint32_t id : c->queue)
                    {
                        Order const* x = OrderOf(id);
                        if (x && x->state == 'W')
                            ++pos;
                        if (id == o->id)
                            break;
                    }
                st.position = pos;
                break;
            }
            case 'T':
            {
                st.state = CafeOrderStateId::Making;
                st.barista = o->baristaName;
                if (Shift* s = ShiftOf(o->baristaGuid))
                    if (Ticket* t = TicketOf(*s, o->ticketId))
                        st.nextStep = t->next;
                break;
            }
            case 'H':
            {
                st.state = o->takeover ? CafeOrderStateId::Finishing : CafeOrderStateId::House;
                st.nextStep = o->houseStep;
                if (CafeRt const* c = CafeOf(o->cafeId); c && c->crowdSpawned)
                    st.leftSec = CafeCrowd::Instance().HouseEtaSec(o->cafeId, o->id);
                break;
            }
            case 'R':
                st.state = CafeOrderStateId::Ready;
                st.nextStep = st.stepCount;
                st.leftSec = o->readyUntilMs > now ? static_cast<uint32_t>((o->readyUntilMs - now) / 1000) : 0;
                break;
            default:
                break;
        }
        return st;
    }

    void Cafe::SendOrderState(Order const& o, std::optional<CafeOrderStateId> state)
    {
        Player* cu = ObjectAccessor::FindConnectedPlayer(ObjectGuid(o.customerGuid));
        if (!cu || o.kind != 'P')
            return;
        if (!state)
        {
            MarkView(o.customerGuid, VOrder);
            return;
        }
        // a final state: sent now, the order is about to go
        CafeOrderState st;
        st.orderId = o.id;
        st.cafeId = o.cafeId;
        st.recipeId = o.recipeId;
        st.state = *state;
        D::Recipe const* r = D::FindRecipe(o.recipeId);
        st.stepCount = r ? r->stepCount : 0;
        st.priceCopper = o.price;
        st.tipCopper = o.tip;
        Ui::SendCafeOrder(cu, st);
    }

    CafeProfile Cafe::BuildProfile(Player* player)
    {
        CafeProfile p;
        Barista& b = BaristaOf(player);
        p.level = b.level;
        p.xp = b.xp;
        p.levelXp = R::LevelXp(b.level);
        p.nextLevelXp = R::NextLevelXp(b.level);
        p.drinks = b.drinks;
        p.perfects = b.perfects;
        p.memoryDrinks = b.memoryDrinks;
        p.bestStreak = b.bestStreak;
        if (b.fastestMs)
            p.fastestMs = b.fastestMs;
        p.weeklyWins = b.weeklyWins;
        p.rewards = b.flags & 31u;
        uint8_t const cafeId = TeamCafe(player);
        CafeWeek w;
        w.weekId = _weekId;
        w.cafeId = cafeId;
        if (b.week.weekId == _weekId)
        {
            w.points = b.week.points;
            w.drinks = b.week.drinks;
            w.perfectPermille = R::PerfectPermille(b.week.perfects, b.week.drinks);
            w.days = R::Bits(b.week.daysMask);
            R::WeekRow row;
            row.drinks = b.week.drinks;
            row.daysMask = b.week.daysMask;
            w.eligible = R::WeeklyEligible(row, _cfg.weeklyMinDrinks, _cfg.weeklyMinDays);
            if (w.eligible)
            {
                std::vector<R::WeekRow> const& board = BoardRows(_weekId, cafeId);
                for (std::size_t i = 0; i < board.size(); ++i)
                    if (board[i].guid == b.low)
                        w.rank = static_cast<uint32_t>(i + 1);
            }
        }
        p.week = w;
        p.lastWinners = _lastWinners;
        return p;
    }

    CafeBuffs Cafe::BuildBuffs(Player* player)
    {
        CafeBuffs f;
        auto left = [&](uint32_t a, uint32_t b) -> Opt<uint32_t> {
            uint32_t const ms = std::max(AuraLeftMs(player, a), AuraLeftMs(player, b));
            if (!player->HasAura(a) && !player->HasAura(b))
                return std::nullopt;
            return (ms + 999) / 1000;
        };
        f.coffeeSec = left(D::Cafes[0].buffCoffee, D::Cafes[1].buffCoffee);
        f.teaSec = left(D::Cafes[0].buffTea, D::Cafes[1].buffTea);
        f.shakeSec = left(D::Cafes[0].buffShake, D::Cafes[1].buffShake);
        f.shakeActive = player->HasAura(D::SpellSprint);
        f.coffeeCounts = CoffeeXpPct() > 0 && player->GetLevel() < sWorld->getIntConfig(CONFIG_MAX_PLAYER_LEVEL) &&
            !player->HasPlayerFlag(PLAYER_FLAGS_NO_XP_GAIN);
        return f;
    }

    CafeAtBar Cafe::BuildAtBar(CafeRt const& c, uint64_t nowMs)
    {
        CafeAtBar bar;
        bar.cafeId = c.id;
        for (auto const& [g, s] : _shifts)
        {
            if (s.cafeId != c.id)
                continue;
            for (Ticket const& t : s.tickets)
            {
                if (!t.step.active)
                    continue;
                D::Recipe const* r = D::FindRecipe(t.recipeId);
                CafeAtBarRow row;
                row.name = s.name;
                row.actionId = t.step.action;
                row.startedAgoMs = static_cast<uint32_t>(std::min<uint64_t>(nowMs - t.step.startMs, 600000));
                row.durMs = t.step.durMs;
                row.kind = t.step.timed ? CafeStepKind::Timed : CafeStepKind::Tap;
                row.stepIndex = t.step.index + 1u;
                row.stepCount = r ? r->stepCount : 1;
                bar.rows.push_back(row);
            }
        }
        for (auto const& [id, o] : _orders)
        {
            if (o.cafeId != c.id || o.state != 'H' || !o.houseStepMs || nowMs >= o.houseStepMs + o.houseStepDurMs)
                continue;
            D::Action const* a = D::FindAction(o.houseAction);
            CafeAtBarRow row;
            row.name = o.houseWorker;
            row.actionId = o.houseAction;
            row.startedAgoMs = static_cast<uint32_t>(nowMs - o.houseStepMs);
            row.durMs = o.houseStepDurMs;
            row.kind = a && a->kind == 'H' ? CafeStepKind::Timed : CafeStepKind::Tap;
            row.stepIndex = o.houseStep + 1u;
            row.stepCount = o.houseSteps;
            bar.rows.push_back(row);
        }
        if (bar.rows.size() > MaxCafeAtRows)
            bar.rows.resize(MaxCafeAtRows);
        return bar;
    }

    // CAFAT to the players with the bit near the bar: everyone on a change, or (the 1 s pass) only those who never had
    // this cafe's strip; players who walked away are forgotten.
    void Cafe::SendAtBar(CafeRt& c, uint64_t nowMs, bool newcomersOnly)
    {
        Map* map = MapOf(c);
        if (!map)
            return;
        std::vector<Player*> to;
        std::unordered_set<uint64_t> inRange;
        ForPlayersOn(map, [&](Player* p) {
            if (!p->IsInWorld() || p->GetExactDist2d(c.anchor.x, c.anchor.y) > AtBarRadius || !FeatureFor(p))
                return true;
            uint64_t const g = Raw(p);
            inRange.insert(g);
            if (!newcomersOnly || !c.atSeen.count(g))
                to.push_back(p);
            return true;
        });
        for (auto it = c.atSeen.begin(); it != c.atSeen.end();)
            it = inRange.count(*it) ? std::next(it) : c.atSeen.erase(it);
        if (to.empty())
            return;
        CafeAtBar const bar = BuildAtBar(c, nowMs);
        if (newcomersOnly && bar.rows.empty())
            return;   // nothing runs: nothing to show yet
        for (Player* p : to)
            c.atSeen.insert(Raw(p));
        Ui::SendCafeAtBar(to, bar);
    }

    void Cafe::FlushViews(uint64_t nowMs)
    {
        // CAFE to every ready player with the bit
        if (_cafeListDirty && nowMs - _cafeListSentMs >= R::CafeListMinGapMs)
        {
            _cafeListDirty = false;
            _cafeListSentMs = nowMs;
            CafeList const list = BuildCafeList();
            for (CafeListRow const& row : list.rows)
                if (CafeRt* c = CafeOf(row.cafeId))
                    c->sentQueueLen = row.queueLen;
            std::vector<Player*> to;
            Mgr::Instance().ForEachReadyPlayer([&](Player* p) {
                if (FeatureFor(p))
                    to.push_back(p);
            });
            if (!to.empty())
                Ui::SendCafeList(to, list);
        }
        // CAFAT on a change, at most every StateGapMs
        for (CafeRt& c : _cafes)
            if (c.atDirty && nowMs - c.atSentMs >= _cfg.stateGapMs)
            {
                c.atDirty = false;
                c.atSentMs = nowMs;
                SendAtBar(c, nowMs, false);
            }
        // per player: CAFST CAFQ CAFT CAFO CAFBF when changed, at most StateGapMs apart (CAFQ 500 ms)
        for (auto it = _views.begin(); it != _views.end();)
        {
            View& v = it->second;
            if (!v.dirty)
            {
                ++it;
                continue;
            }
            Player* p = ObjectAccessor::FindConnectedPlayer(ObjectGuid(it->first));
            if (!p)
            {
                it = _views.erase(it);
                continue;
            }
            if (!FeatureFor(p) || !Ui::HasAddon(p))
            {
                v.dirty = 0;
                ++it;
                continue;
            }
            auto due = [&](uint8_t bit, std::size_t slot, uint64_t gap) {
                if (!(v.dirty & bit) || nowMs - v.sentMs[slot] < gap)
                    return false;
                v.dirty = static_cast<uint8_t>(v.dirty & ~bit);
                v.sentMs[slot] = nowMs;
                return true;
            };
            Shift* s = ShiftOf(p);
            if (due(VState, 0, _cfg.stateGapMs))
                Ui::SendCafeState(p, BuildState(p));
            if (due(VQueue, 1, std::max<uint64_t>(_cfg.stateGapMs, QueueMinGapMs)) && s)
                Ui::SendCafeQueue(p, BuildQueue(s->cafeId, p));
            if (due(VTickets, 2, _cfg.stateGapMs))
                Ui::SendCafeTickets(p, BuildTickets(p));
            if (due(VOrder, 3, _cfg.stateGapMs))
                Ui::SendCafeOrder(p, BuildOrder(p));
            if (due(VBuffs, 4, _cfg.stateGapMs))
            {
                Ui::SendCafeBuffs(p, BuildBuffs(p));
                v.buffsSentMs = nowMs;
            }
            ++it;
        }
    }

    void Cafe::UpdateSnapshot()
    {
        GossipSnap snap;
        for (CafeRt const& c : _cafes)
            if (c.id < snap.open.size())
                snap.open[c.id] = Enabled() ? (c.placed && c.enabled ? c.open : 3) : 0;
        for (auto const& [g, s] : _shifts)
            snap.onShift.insert(g);
        snap.enabled = Enabled();
        snap.gmOnly = _gmOnly.load();
        std::lock_guard<std::mutex> guard(_snapLock);
        _snap = std::move(snap);
    }

    // =============================================================================================================
    // LBQ C (the weekly board)
    // =============================================================================================================
    void Cafe::AnswerBoard(Player* player, Intent const& in)
    {
        // the board is a cafe intent too: off, or GmOnly for a player without the bit, is cafe_off (Mgr::Dispatch's
        // gate covers the seven C intents only)
        if (!FeatureFor(player))
            return Refuse(player, in, CafeErr::Off);
        uint32_t const weekId = in.seasonId ? in.seasonId : _weekId;
        uint8_t const cafeId = static_cast<uint8_t>(in.dungeonId);
        std::vector<R::WeekRow> const& rows = BoardRows(weekId, cafeId);
        uint32_t const pageSize = Mgr::Instance().Cfg().leaderboardPageSize;
        uint32_t const pages = std::max<uint32_t>(1, static_cast<uint32_t>((rows.size() + pageSize - 1) / pageSize));
        uint32_t const page = std::clamp<uint32_t>(in.page, 1, pages);
        Leaderboard lb;
        lb.board = Bleakhold::Board::Cafe;
        lb.seasonId = weekId;
        lb.dungeonId = cafeId;
        lb.classId = 0;
        lb.page = page;
        lb.pages = pages;
        for (std::size_t i = std::size_t(page - 1) * pageSize; i < rows.size() && i < std::size_t(page) * pageSize; ++i)
        {
            R::WeekRow const& r = rows[i];
            LeaderboardRow row;
            row.rank = static_cast<uint32_t>(i + 1);
            row.dungeonId = cafeId;
            row.value = r.points;
            row.timeSec = R::PerfectPermille(r.perfects, r.drinks);
            row.dateEpoch = r.scoreAt;
            row.members.push_back({ r.name, uint32_t(r.classId) });
            row.label = std::to_string(r.drinks) + " drinks";
            lb.rows.push_back(std::move(row));
        }
        Ui::SendLeaderboard(player, lb);
        LeaderboardMe me;
        me.board = Bleakhold::Board::Cafe;
        uint32_t const low = Low(player);
        for (std::size_t i = 0; i < rows.size(); ++i)
        {
            if (rows[i].guid != low)
                continue;
            R::WeekRow const& r = rows[i];
            me.rank = static_cast<uint32_t>(i + 1);
            me.topPercent = static_cast<uint32_t>(((i + 1) * 100 + rows.size() - 1) / rows.size());
            me.value = r.points;
            me.dungeonId = cafeId;
            me.timeSec = R::PerfectPermille(r.perfects, r.drinks);
            me.barPermille = rows[0].points ? std::min<uint32_t>(1000, static_cast<uint32_t>(uint64_t(r.points) * 1000 /
                rows[0].points)) : 0;
            me.label = std::to_string(r.drinks) + " drinks";
        }
        Ui::SendLeaderboardMe(player, me);
    }

    // =============================================================================================================
    // Gossip (section 3.14)
    // =============================================================================================================
    namespace
    {
        enum GossipAction : uint32_t
        {
            ActStart = 1, ActEnd = 2, ActMenu = 3, ActBoard = 4, ActHelp = 5, ActRecipes = 6
        };
        constexpr uint32_t SenderMain = 1;
        constexpr uint32_t SenderRecipe = 100;   // + n
    }

    void Cafe::GossipHello(Player* player, Creature* creature)
    {
        if (!player || !creature)
            return;
        D::StaffMember const* st = D::FindStaff(creature->GetEntry());
        if (!st)
            return;
        D::Cafe const& cd = CafeInfo(st->cafeId);
        GossipSnap snap;
        {
            std::lock_guard<std::mutex> guard(_snapLock);
            snap = _snap;
        }
        ClearGossipMenuFor(player);
        if (TeamCafe(player) != st->cafeId)
        {
            SendGossipMenuFor(player, cd.textRefuse, creature);
            return;
        }
        WorldSession* session = player->GetSession();
        bool const feature = snap.enabled && (!snap.gmOnly || (session && session->GetSecurity() >= SEC_GAMEMASTER));
        if (feature && st->house == 1)
        {
            if (snap.onShift.count(Raw(player)))
                AddGossipItemFor(player, GOSSIP_ICON_CHAT, "I'll end my shift.", SenderMain, ActEnd);
            else
            {
                AddGossipItemFor(player, GOSSIP_ICON_CHAT, "I'd like to work a barista shift.", SenderMain, ActStart);
                // her "shift offered" line: said by the next tick (Say talks to the crowd, a world-thread object)
                std::lock_guard<std::mutex> guard(_eventLock);
                _events.push_back({ Event::Kind::ShiftOffered, st->cafeId, Low(player) });
            }
            AddGossipItemFor(player, GOSSIP_ICON_VENDOR, "What's on the menu?", SenderMain, ActMenu);
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Show me the caf\xC3\xA9 rankings.", SenderMain, ActBoard);
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "How does this work?", SenderMain, ActHelp);
        }
        else if (feature && st->house == 2)
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Tell me about the recipes.", SenderMain, ActRecipes);
        SendGossipMenuFor(player, cd.textGreeting, creature);
    }

    void Cafe::GossipSelect(Player* player, Creature* creature, uint32_t sender, uint32_t action)
    {
        if (!player || !creature)
            return;
        D::StaffMember const* st = D::FindStaff(creature->GetEntry());
        if (!st || TeamCafe(player) != st->cafeId || !FeatureFor(player))
        {
            CloseGossipMenuFor(player);
            return;
        }
        uint8_t const cafeId = st->cafeId;
        D::Cafe const& cd = CafeInfo(cafeId);
        // the windows (CAFUI) and the barista bar need the cafe's part of the addon (HELLO caps); an addon without it,
        // or none, gets the gossip pages and system messages
        bool const cafeUi = Ui::HasClientCap(player, ClientCapCafeUi);
        ClearGossipMenuFor(player);
        if (sender > SenderRecipe && sender <= SenderRecipe + 19)
        {
            // a drink ordered without the cafe's UI: the same as CORDER with no tip
            CloseGossipMenuFor(player);
            Intent in;
            in.type = IntentType::CafeOrder;
            in.cafeId = cafeId;
            in.recipeId = static_cast<uint16_t>(action);
            in.tipPct = 0;
            in.seq = 0;
            // without the cafe's UI nothing shows an ERR: every refusal of HandleOrder is a system message too
            _tellRefusals = !cafeUi;
            HandleOrder(player, in);
            _tellRefusals = false;
            return;
        }
        switch (action)
        {
            case ActStart:
                if (!cafeUi)
                {
                    Tell(player, "A shift needs the caf\xC3\xA9 part of the Bleakhold UI: its barista bar is how you "
                        "work the stations.");
                    CloseGossipMenuFor(player);
                    return;
                }
                CloseGossipMenuFor(player);
                if (StartShift(player, cafeId, nullptr))
                    Ui::SendCafeOpenUi(player, CafeUiShift, cafeId);
                return;
            case ActEnd:
                CloseGossipMenuFor(player);
                if (Shift* s = ShiftOf(player))
                    EndShift(*s, static_cast<char>(CafeShiftEnd::Player), Mgr::NowMs());
                return;
            case ActMenu:
                if (cafeUi)
                {
                    CloseGossipMenuFor(player);
                    Ui::SendCafeOpenUi(player, CafeUiMenu, cafeId);
                    return;
                }
                for (D::Recipe const& r : D::Recipes)
                {
                    if (r.cafeId != cafeId)
                        continue;
                    D::Tier const* tier = R::TierOf(r.tier);
                    uint32_t const price = tier ? R::PriceCopper(tier->price80, player->GetLevel(), _cfg.priceMinCopper,
                        _cfg.priceLevelFloorPct) : 0;
                    std::string const name(r.name);
                    AddGossipItemFor(player, GOSSIP_ICON_VENDOR, name + " (" + Copper(price) + ")", SenderRecipe + r.n, r.id,
                        "Order " + name + "?", price, false);
                }
                SendGossipMenuFor(player, cd.textMenu, creature);
                return;
            case ActBoard:
            {
                CloseGossipMenuFor(player);
                if (cafeUi)
                {
                    Ui::SendCafeOpenUi(player, CafeUiBoard, cafeId);
                    return;
                }
                std::vector<R::WeekRow> const& rows = BoardRows(_weekId, cafeId);
                if (rows.empty())
                {
                    Tell(player, "Nobody is on this week's board at " + std::string(cd.name) + " yet.");
                    return;
                }
                for (std::size_t i = 0; i < rows.size() && i < 3; ++i)
                    Tell(player, std::to_string(i + 1) + ". " + rows[i].name + ": " + std::to_string(rows[i].points) +
                        " points, " + std::to_string(rows[i].drinks) + " drinks");
                return;
            }
            case ActHelp:
                if (cafeUi)
                {
                    CloseGossipMenuFor(player);
                    Ui::SendCafeOpenUi(player, CafeUiHelp, cafeId);
                    return;
                }
                SendGossipMenuFor(player, cd.textHelp, creature);
                return;
            case ActRecipes:
            {
                CloseGossipMenuFor(player);
                if (cafeUi)
                {
                    Ui::SendCafeOpenUi(player, CafeUiHelp, cafeId);
                    return;
                }
                Barista& b = BaristaOf(player);
                for (D::Recipe const& r : D::Recipes)
                {
                    if (r.cafeId != cafeId || !R::Unlocked(b.level, r))
                        continue;
                    std::string line = std::string(r.name) + ":";
                    for (uint8_t i = 0; i < r.stepCount; ++i)
                        if (D::Action const* a = D::FindAction(r.steps[i]))
                            line += std::string(i ? ", " : " ") + std::string(cafeId == 2 && !a->hordeName.empty() ?
                                a->hordeName : a->name);
                    Tell(player, line);
                }
                return;
            }
            default:
                CloseGossipMenuFor(player);
                return;
        }
    }

    // =============================================================================================================
    // Hooks
    // =============================================================================================================
    void Cafe::OnLogin(Player* player)
    {
        if (!player)
            return;
        // never kept over a logout, whatever BleakholdUi.Cafe.Enable says (they are never saved either)
        player->RemoveAurasDueToSpell(D::SpellOnShift);
        player->RemoveAurasDueToSpell(D::SpellSprint);
        if (player->HasAura(D::Cafes[0].buffShake) || player->HasAura(D::Cafes[1].buffShake))
            _shakePlayers.insert(Low(player));
        if (!Enabled())
            return;
        for (D::Cafe const& cd : D::Cafes)
            for (uint32_t s : { cd.buffCoffee, cd.buffTea, cd.buffShake })
                if (player->HasAura(s))
                    _buffPlayers.insert(Low(player));
        Barista& b = BaristaOf(player);
        b.expireMs = 0;
        if (b.exists)
            GrantLevelRewards(player, b, false);
    }

    void Cafe::OnBeforeLogout(Player* player)
    {
        if (!player)
            return;
        if (Shift* s = ShiftOf(player))
            EndShift(*s, static_cast<char>(CafeShiftEnd::Died), Mgr::NowMs());
        player->RemoveAurasDueToSpell(D::SpellOnShift);
        player->RemoveAurasDueToSpell(D::SpellSprint);
        player->RemoveAurasDueToSpell(D::SpellTired);
    }

    void Cafe::OnLogout(Player* player)
    {
        if (!player)
            return;
        uint32_t const low = Low(player);
        if (Barista* b = LoadedBarista(low))
        {
            SaveBarista(*b);
            b->expireMs = Mgr::NowMs() + BaristaForgetMs;
        }
        _views.erase(Raw(player));
        _buffPlayers.erase(low);
        _lingers.erase(low);
        for (CafeRt& c : _cafes)
            c.atSeen.erase(Raw(player));
    }

    void Cafe::OnMapChanged(Player* player)
    {
        if (Shift* s = ShiftOf(player))
            EndShift(*s, static_cast<char>(CafeShiftEnd::Died), Mgr::NowMs());
    }

    void Cafe::OnEnterCombatMapThread(Player* player)
    {
        if (!player)
            return;
        player->RemoveAurasDueToSpell(D::SpellSprint);
        if (!Enabled() || !player->HasAura(D::SpellOnShift))
            return;
        std::lock_guard<std::mutex> guard(_eventLock);
        _events.push_back({ Event::Kind::Combat, Low(player), 0 });
    }

    void Cafe::OnPvpFlagMapThread(Player* player, bool on)
    {
        if (player && on)
            player->RemoveAurasDueToSpell(D::SpellSprint);
    }

    void Cafe::OnDuelMapThread(Player* a, Player* b)
    {
        if (a)
            a->RemoveAurasDueToSpell(D::SpellSprint);
        if (b)
            b->RemoveAurasDueToSpell(D::SpellSprint);
    }

    void Cafe::OnSpellCancelMapThread(uint32_t lowGuid, uint32_t spellId)
    {
        if (!IsStepSpell(spellId) || !Enabled())
            return;
        std::lock_guard<std::mutex> guard(_eventLock);
        _events.push_back({ Event::Kind::SpellCancel, lowGuid, spellId });
    }

    void Cafe::OnGoSavedToDbMapThread(uint32_t spawnId, uint32_t entry)
    {
        if (entry < D::GameObjectFirst || entry > D::GameObjectLast)
            return;
        std::lock_guard<std::mutex> guard(_eventLock);
        _events.push_back({ Event::Kind::GoSaved, spawnId, entry });
    }

    void Cafe::OnCreatureSavedToDbMapThread(uint32_t spawnId, uint32_t entry)
    {
        if (entry < D::CreatureFirst || entry > D::CreatureLast || !spawnId)
            return;
        std::lock_guard<std::mutex> guard(_eventLock);
        _events.push_back({ Event::Kind::CreatureSaved, spawnId, entry });
    }

    void Cafe::OnDeleteCharacter(uint32_t lowGuid)
    {
        if (!lowGuid)
            return;
        CharacterDatabaseTransaction t = CharacterDatabase.BeginTransaction();
        t->Append("DELETE FROM `bleakhold_cafe_barista` WHERE `guid` = {}", lowGuid);
        t->Append("DELETE FROM `bleakhold_cafe_day` WHERE `guid` = {}", lowGuid);
        t->Append("DELETE FROM `bleakhold_cafe_flag` WHERE `guid` = {}", lowGuid);
        t->Append("DELETE FROM `bleakhold_cafe_week` WHERE `guid` = {}", lowGuid);   // no payout to a deleted character
        t->Append("DELETE FROM `bleakhold_cafe_order` WHERE `customer_guid` = {}", lowGuid);
        if (!_startupDone)
        {
            // the purge of old deleted characters runs before OnStartup (World.cpp:952): the tables may be new, and
            // the leftover orders read at startup must not see this character's rows any more
            EnsureTables();
            CharacterDatabase.DirectCommitTransaction(t);
            return;
        }
        CharacterDatabase.CommitTransaction(t);
        std::vector<uint32_t> gone;
        for (auto const& [id, o] : _orders)
            if (o.kind == 'P' && o.customerLow == lowGuid)
                gone.push_back(id);
        for (uint32_t id : gone)
        {
            LOG_INFO("module", "[Bleakhold] Cafe money: order {} dropped, its character {} was deleted", id, lowGuid);
            // the barista's ticket (it would hold a ticket slot), the house job and the counter cup's place go too
            if (Order* o = OrderOf(id))
                DropLeftovers(*o, "The customer has gone.");
            RemoveOrder(id);
        }
        _lingers.erase(lowGuid);
        _baristas.erase(lowGuid);
        _boards.clear();
    }
}
