/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Camping (section 16). See BleakholdCamp.h for the threads and the rest mechanics.
 *
 * Lock order: Camp::_lock, then the Mgr lock (Ui::SendCampState) and the timer or new-fire locks; nothing here is called
 * by the Mgr while it holds its own lock.
 */

#include "BleakholdCamp.h"
#include "BleakholdMgr.h"
#include "BleakholdUi.h"

#include "CellImpl.h"
#include "Config.h"
#include "DBCStores.h"
#include "GameObject.h"
#include "GameTime.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "GridTerrainData.h"
#include "Item.h"
#include "Log.h"
#include "Map.h"
#include "MapMgr.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "World.h"

#include <algorithm>
#include <cmath>

namespace Bleakhold
{
    namespace
    {
        constexpr uint64_t TickMs = 500;                // fires, rest, settling and CAMPST changes
        constexpr uint64_t PurgeMs = 60000;
        constexpr uint64_t MinStateGapMs = 1000;        // CAMPST at most once per second per player
        constexpr uint32_t WellFedGroup = 1001;         // spell_group "Well Fed" (every food buff)
        constexpr uint32_t BasicCampfire = 29784;       // the fire of cooking spell 818
        constexpr uint32_t CozyFireTrap = 31442;        // its linked trap (Cozy Fire, a small buff)
        constexpr float FireDistance = 1.5f;            // the camp fire stands this far in front of its maker
        constexpr float ObjectDistance = 2.6f;          // camp objects stand around the fire at this distance

        uint64_t NowSec() { return static_cast<uint64_t>(GameTime::GetGameTime().count()); }
        uint64_t Raw(Player const* p) { return p->GetGUID().GetRawValue(); }
        uint32_t Low(Player const* p) { return p->GetGUID().GetCounter(); }

        std::string Minutes(uint32_t sec)
        {
            uint32_t const m = (sec + 59) / 60;
            return std::to_string(m) + (m == 1 ? " minute" : " minutes");
        }

        char const* const TextDead = "You cannot do that while dead.";
        char const* const TextCombat = "You cannot do that in combat.";
        char const* const TextFailed = "That did not work. Try again in a moment.";

        // A camp fire or camp object must be harmless decoration: a generic object or a spell focus, no script, no AI and
        // no linked trap (but the Basic Campfire's own Cozy Fire trap), and no crafting station tied to a place (a
        // focus outside BleakholdUi.Camp.AllowedFocusIds: Spell::CheckSpellFocus accepts any spawned focus object, camp
        // objects included).
        bool SafeTemplate(uint32_t entry, std::vector<uint32_t> const& allowedFoci, std::string& why)
        {
            GameObjectTemplate const* t = sObjectMgr->GetGameObjectTemplate(entry);
            if (!t)
            {
                why = "does not exist";
                return false;
            }
            if (t->type != GAMEOBJECT_TYPE_GENERIC && t->type != GAMEOBJECT_TYPE_SPELL_FOCUS)
            {
                why = "is not a generic object or a spell focus (type " + std::to_string(t->type) + ")";
                return false;
            }
            if (t->ScriptId || !t->AIName.empty())
            {
                why = "has a script";
                return false;
            }
            if (t->type == GAMEOBJECT_TYPE_SPELL_FOCUS && t->spellFocus.linkedTrapId && t->spellFocus.linkedTrapId != CozyFireTrap)
            {
                why = "has a linked trap";
                return false;
            }
            if (t->type == GAMEOBJECT_TYPE_SPELL_FOCUS && !CampRules::FocusAllowed(t->spellFocus.focusId, allowedFoci))
            {
                why = "is a crafting station tied to a place (spell focus " + std::to_string(t->spellFocus.focusId) +
                    ", not in BleakholdUi.Camp.AllowedFocusIds)";
                return false;
            }
            return true;
        }

        // Any of the core's rest bits (inn, city, faction rest area; the camp uses the last one).
        bool AnyRestBit(Player* p)
        {
            return p->HasRestFlag(REST_FLAG_IN_TAVERN) || p->HasRestFlag(REST_FLAG_IN_CITY) ||
                p->HasRestFlag(REST_FLAG_IN_FACTION_AREA);
        }

        // The repair cost of everything DurabilityRepairAll repairs (equipped, backpack, bags), the same formula as
        // Player::DurabilityRepair, so a player who can pay it is never charged for only part of the repair.
        uint64_t RepairCost(Player* player, float costMod)
        {
            uint64_t total = 0;
            auto add = [&](uint8_t bag, uint8_t slot) {
                Item* item = player->GetItemByPos(bag, slot);
                if (!item)
                    return;
                uint32_t const maxDurability = item->GetUInt32Value(ITEM_FIELD_MAXDURABILITY);
                uint32_t const curDurability = item->GetUInt32Value(ITEM_FIELD_DURABILITY);
                if (!maxDurability || curDurability >= maxDurability)
                    return;
                ItemTemplate const* proto = item->GetTemplate();
                DurabilityCostsEntry const* dcost = sDurabilityCostsStore.LookupEntry(proto->ItemLevel);
                DurabilityQualityEntry const* dquality = sDurabilityQualityStore.LookupEntry((proto->Quality + 1) * 2);
                if (!dcost || !dquality)
                    return;
                uint32_t const multiplier = dcost->multiplier[ItemSubClassToDurabilityMultiplierId(proto->Class, proto->SubClass)];
                uint32_t costs = uint32_t((maxDurability - curDurability) * multiplier * double(dquality->quality_mod));
                costs = uint32_t(costs * costMod * sWorld->getRate(RATE_REPAIRCOST));
                total += costs ? costs : 1;
            };
            for (uint8_t i = EQUIPMENT_SLOT_START; i < INVENTORY_SLOT_ITEM_END; ++i)
                add(INVENTORY_SLOT_BAG_0, i);
            for (uint8_t bag = INVENTORY_SLOT_BAG_START; bag < INVENTORY_SLOT_BAG_END; ++bag)
                for (uint8_t i = 0; i < MAX_BAG_SIZE; ++i)
                    add(bag, i);
            return total;
        }

        bool ReachesOthers(SpellEffectInfo const& e)
        {
            return e.TargetA.IsArea() || e.TargetB.IsArea() || e.ChainTarget > 1;
        }

        // A spell that does nothing when it lands: no script (spell_script_names), no linked spell, and only dummy
        // auras on one unit. 23770 "Sayge's Carnie Buff", the marker every Sayge's fortune triggers, is one (and the
        // core never casts it: Spell::EffectTriggerSpell skips it).
        bool InertMarker(uint32_t spellId)
        {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
            if (!info)
                return false;
            SpellScriptsBounds const scripts = sObjectMgr->GetSpellScriptsBounds(spellId);
            if (scripts.first != scripts.second)
                return false;
            int32_t const id = static_cast<int32_t>(spellId);
            for (int32_t link : { id, -id, id + SPELL_LINK_HIT, id + SPELL_LINK_AURA, -(id + SPELL_LINK_AURA) })
                if (sSpellMgr->GetSpellLinked(link))
                    return false;
            for (SpellEffectInfo const& e : info->Effects)
            {
                if (!e.IsEffect())
                    continue;
                if (!e.IsEffect(SPELL_EFFECT_APPLY_AURA) || e.ApplyAuraName != SPELL_AURA_DUMMY || e.TriggerSpell ||
                    ReachesOthers(e))
                    return false;
            }
            return true;
        }

        // A spell the camp may cast on a player (CampRules::CheckBuff): it exists, raises no XP itself, reaches nobody
        // else and does the player no harm.
        bool SafeSpell(uint32_t spellId, std::string& why)
        {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
            if (!info)
            {
                why = "does not exist";
                return false;
            }
            CampRules::BuffEffects effects;
            for (uint8_t i = 0; i < MAX_SPELL_EFFECTS && i < effects.size(); ++i)
            {
                SpellEffectInfo const& e = info->Effects[i];
                CampRules::BuffEffect& f = effects[i];
                f.present = e.IsEffect();
                if (!f.present)
                    continue;
                f.changesXp = e.IsAura(SPELL_AURA_MOD_XP_PCT) || e.IsAura(SPELL_AURA_MOD_XP_QUEST_PCT);
                f.areaAura = e.IsAreaAuraEffect();
                f.reachesOthers = ReachesOthers(e);
                f.positive = info->IsPositiveEffect(i);
                f.inertTrigger = e.IsEffect(SPELL_EFFECT_TRIGGER_SPELL) && e.TriggerSpell != spellId &&
                    InertMarker(e.TriggerSpell);
            }
            CampRules::BuffProblem const problem = CampRules::CheckBuff(effects);
            if (problem != CampRules::BuffProblem::None)
            {
                why = CampRules::BuffProblemText(problem);
                return false;
            }
            return true;
        }

        bool CanRestAtFire(Player* p)
        {
            return p->IsInWorld() && p->IsAlive() && !p->IsInCombat() && !p->IsInFlight() && !p->IsBeingTeleported() &&
                !p->GetVehicle() && p->GetMap()->IsWorldMap() && !p->InBattleground() && !p->InArena() && !p->pvpInfo.IsInFFAPvPArea;
        }
    }

    Camp& Camp::Instance()
    {
        static Camp instance;
        return instance;
    }

    // =============================================================================================
    // Configuration
    // =============================================================================================
    void Camp::LoadConfig()
    {
        CampConfig c;
        c.campOn = sConfigMgr->GetOption<bool>("BleakholdUi.Camp.Enable", true);
        c.glideOn = sConfigMgr->GetOption<bool>("BleakholdUi.Glide.Enable", true);
        c.repairOn = sConfigMgr->GetOption<bool>("BleakholdUi.Repair.Enable", true);
        c.minLevel = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Camp.MinLevel", 5);
        c.cooldownSec = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Camp.Cooldown", 900);
        c.fireSec = std::clamp<uint32_t>(sConfigMgr->GetOption<uint32_t>("BleakholdUi.Camp.FireDuration", 900), 10, 86400);
        c.fireEntry = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Camp.FireEntry", 194300);
        c.extraFireEntries = CampRules::ParseIds(sConfigMgr->GetOption<std::string>("BleakholdUi.Camp.ExtraFireEntries", ""));
        c.extraFireEntries.erase(std::remove(c.extraFireEntries.begin(), c.extraFireEntries.end(), 0u), c.extraFireEntries.end());
        if (c.extraFireEntries.size() > MaxHookEntries - 1)
        {
            LOG_ERROR("module", "[Bleakhold] BleakholdUi.Camp.ExtraFireEntries holds more than {} entries; the rest are ignored", MaxHookEntries - 1);
            c.extraFireEntries.resize(MaxHookEntries - 1);
        }
        c.allowedFocusIds = CampRules::ParseIds(sConfigMgr->GetOption<std::string>("BleakholdUi.Camp.AllowedFocusIds",
            std::string(CampRules::DefaultAllowedFocusIds)));
        c.radius = std::clamp(sConfigMgr->GetOption<float>("BleakholdUi.Camp.Radius", 10.0f), 2.0f, 30.0f);
        c.settleSec = std::min<uint32_t>(sConfigMgr->GetOption<uint32_t>("BleakholdUi.Camp.SettleTime", 60), 3600);
        c.buffSec = std::clamp<uint32_t>(sConfigMgr->GetOption<uint32_t>("BleakholdUi.Camp.BuffDuration", 3600), 1, 86400);
        c.warmthSec = std::clamp<uint32_t>(sConfigMgr->GetOption<uint32_t>("BleakholdUi.Camp.WarmthDuration", 1800), 1, 86400);
        c.warmthXpPct = std::min<uint32_t>(sConfigMgr->GetOption<uint32_t>("BleakholdUi.Camp.WarmthXpPct", 10), 100);
        c.warmthSpell = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Camp.WarmthSpell", 0);
        c.foodXpPct = std::min<uint32_t>(sConfigMgr->GetOption<uint32_t>("BleakholdUi.Camp.FoodXpPct", 5), 100);
        c.maxXpPct = std::min<uint32_t>(sConfigMgr->GetOption<uint32_t>("BleakholdUi.Camp.MaxXpPct", 25), 100);
        std::string const tiers = sConfigMgr->GetOption<std::string>("BleakholdUi.Camp.TierSkill", "75,225,375");
        if (std::optional<CampRules::Tiers> t = CampRules::ParseTiers(tiers))
            c.tierSkill = *t;
        else
            LOG_ERROR("module", "[Bleakhold] BleakholdUi.Camp.TierSkill must be three increasing skill values (\"75,225,375\"), not \"{}\"; using 75,225,375", tiers);
        for (CampRules::Profession const& def : CampRules::DefaultProfessions)
        {
            std::string const defText = std::to_string(def.objects[0]) + "," + std::to_string(def.objects[1]) + "," + std::to_string(def.objects[2]) +
                "," + std::to_string(def.buffs[0]) + "," + std::to_string(def.buffs[1]) + "," + std::to_string(def.buffs[2]);
            std::string const key = std::string("BleakholdUi.Camp.Profession.") + def.key;
            std::string const text = sConfigMgr->GetOption<std::string>(key, defText);
            std::vector<uint32_t> const ids = CampRules::ParseIds(text);
            CampRules::Profession p = def;
            if (ids.size() == 1 && ids[0] == 0)
                continue;   // "0": this profession has no camp objects
            if (ids.size() == 6)
            {
                p.objects = { ids[0], ids[1], ids[2] };
                p.buffs = { ids[3], ids[4], ids[5] };
            }
            else
                LOG_ERROR("module", "[Bleakhold] {} must be six ids (three objects, three buffs) or 0, not \"{}\"; using {}", key, text, defText);
            c.professions.push_back(p);
        }
        c.repairMinSkill = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Repair.MinSkill", 75);
        c.repairDiscountPct = std::min<uint32_t>(sConfigMgr->GetOption<uint32_t>("BleakholdUi.Repair.BlacksmithDiscountPct", 10), 100);
        c.glideRaces = CampRules::ParseIds(sConfigMgr->GetOption<std::string>("BleakholdUi.Glide.Races", "22"));
        c.glideCooldownSec = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Glide.Cooldown", 120);
        c.glideSec = std::clamp<uint32_t>(sConfigMgr->GetOption<uint32_t>("BleakholdUi.Glide.Duration", 10), 1, 600);
        c.glideSpell = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Glide.Spell", 130);

        std::lock_guard<std::recursive_mutex> guard(_lock);
        _cfg = c;
        if (_worldLoaded)
            Validate();
        _xpWarmth = _cfg.warmthXpPct;
        _xpFood = _cfg.foodXpPct;
        _xpMax = _cfg.maxXpPct;
        _xpOn = _cfg.campOn;
        // the entries OnGameObjectAdded notes: player-made Basic Campfires and the extra entries
        std::vector<uint32_t> hook{ BasicCampfire };
        hook.insert(hook.end(), _cfg.extraFireEntries.begin(), _cfg.extraFireEntries.end());
        _hookCount = 0;
        for (std::size_t i = 0; i < hook.size() && i < MaxHookEntries; ++i)
            _hookEntries[i] = hook[i];
        _hookCount = static_cast<uint32_t>(std::min(hook.size(), MaxHookEntries));
    }

    void Camp::OnStartup()
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        _worldLoaded = true;
        Validate();
    }

    void Camp::Validate()
    {
        std::string why;
        if (_cfg.fireEntry != BasicCampfire && !SafeTemplate(_cfg.fireEntry, _cfg.allowedFocusIds, why))
        {
            LOG_ERROR("module", "[Bleakhold] BleakholdUi.Camp.FireEntry {} {}; camp fires use the Basic Campfire ({}) instead", _cfg.fireEntry, why, BasicCampfire);
            _cfg.fireEntry = BasicCampfire;
        }
        if (_cfg.fireEntry == BasicCampfire && !sObjectMgr->GetGameObjectTemplate(BasicCampfire))
        {
            LOG_ERROR("module", "[Bleakhold] gameobject_template {} (Basic Campfire) is missing; CAMP M cannot light a fire", BasicCampfire);
            _cfg.fireEntry = 0;
        }
        std::vector<uint32_t> extras;
        for (uint32_t e : _cfg.extraFireEntries)
        {
            if (sObjectMgr->GetGameObjectTemplate(e))
                extras.push_back(e);
            else
                LOG_ERROR("module", "[Bleakhold] BleakholdUi.Camp.ExtraFireEntries: gameobject_template {} does not exist; ignored", e);
        }
        _cfg.extraFireEntries = extras;
        for (CampRules::Profession& p : _cfg.professions)
        {
            for (uint8_t t = 0; t < CampRules::TierCount; ++t)
            {
                if (p.objects[t] && !SafeTemplate(p.objects[t], _cfg.allowedFocusIds, why))
                {
                    LOG_ERROR("module", "[Bleakhold] BleakholdUi.Camp.Profession.{}: tier {} object {} {}; that tier has no camp object", p.key, t + 1, p.objects[t], why);
                    p.objects[t] = 0;
                }
                if (p.buffs[t] && !SafeSpell(p.buffs[t], why))
                {
                    LOG_ERROR("module", "[Bleakhold] BleakholdUi.Camp.Profession.{}: tier {} buff spell {} {}; that object gives no buff", p.key, t + 1, p.buffs[t], why);
                    p.buffs[t] = 0;
                }
            }
        }
        if (_cfg.glideSpell && !SafeSpell(_cfg.glideSpell, why))
        {
            LOG_ERROR("module", "[Bleakhold] BleakholdUi.Glide.Spell {} {}; gliding is off", _cfg.glideSpell, why);
            _cfg.glideSpell = 0;
        }
        if (_cfg.warmthSpell && !SafeSpell(_cfg.warmthSpell, why))
        {
            LOG_ERROR("module", "[Bleakhold] BleakholdUi.Camp.WarmthSpell {} {}; no warmth aura is shown", _cfg.warmthSpell, why);
            _cfg.warmthSpell = 0;
        }
    }

    CampRules::Profession const* Camp::ProfessionOf(uint32_t skill) const
    {
        for (CampRules::Profession const& p : _cfg.professions)
            if (p.skill == skill)
                return &p;
        return nullptr;
    }

    // The highest tier the player's skill reaches that has an object (0: none).
    uint8_t Camp::PlaceableTier(Player* player, CampRules::Profession const& prof) const
    {
        if (!player->HasSkill(prof.skill))
            return 0;
        uint8_t tier = CampRules::TierFor(player->GetSkillValue(prof.skill), _cfg.tierSkill);
        while (tier > 0 && !prof.objects[tier - 1])
            --tier;
        return tier;
    }

    bool Camp::CanGlide(Player* player) const
    {
        if (!_cfg.glideOn || !_cfg.glideSpell)
            return false;
        uint32_t const race = player->getRace(true);
        return std::find(_cfg.glideRaces.begin(), _cfg.glideRaces.end(), race) != _cfg.glideRaces.end();
    }

    bool Camp::AnvilAt(Fire const& fire)
    {
        for (CampObject const& o : fire.objects)
            if (o.skill == CampRules::SkillBlacksmithing && o.tier >= CampRules::AnvilTier)
                return true;
        return false;
    }

    Camp::Timers Camp::TimersOf(uint32_t lowGuid)
    {
        std::lock_guard<std::mutex> guard(_timerLock);
        auto it = _timers.find(lowGuid);
        return it == _timers.end() ? Timers() : it->second;
    }

    // =============================================================================================
    // Rest
    // =============================================================================================
    bool Camp::InFactionRestArea(Player* player)
    {
        AreaTableEntry const* area = sAreaTableStore.LookupEntry(player->GetAreaId());
        uint32_t const flag = player->GetTeamId(true) == TEAM_ALLIANCE ? AREA_FLAG_REST_ZONE_ALLIANCE : AREA_FLAG_REST_ZONE_HORDE;
        return area && (area->flags & flag);
    }

    // Camp rest ends (leaving the fire, combat): only the camp's bit goes; inn and city rest stay (the core keeps
    // RESTING while another bit is set), and rest without any bit (mod-guildhouse) never got the camp's bit (Update,
    // step 2).
    void Camp::EndCampRest(Player* player)
    {
        if (player->HasRestFlag(REST_FLAG_IN_FACTION_AREA) && !InFactionRestArea(player))
            player->RemoveRestFlag(REST_FLAG_IN_FACTION_AREA);
    }

    void Camp::OnEnterCombat(Player* player)
    {
        if (player)
            EndCampRest(player);
    }

    void Camp::OnLogin(Player* player)
    {
        if (!player)
            return;
        // A logout at a fire saves PLAYER_FLAGS_RESTING (so it counts as an inn logout), and the login restores the flag
        // from the characters table without any rest bit: RESTING would then stay on for good (instant logout, logout in
        // combat, inn-rate rest at every later logout). The core has already set the inn, city and faction area bits
        // here (UpdateZone runs before OnPlayerLogin), so RESTING without any of them is that leftover. (mod-guildhouse,
        // which also rests without a bit, registers after this module and sets its rest again in its own login hook.)
        if (player->HasPlayerFlag(PLAYER_FLAGS_RESTING) && !AnyRestBit(player))
            player->RemoveRestState();
        std::lock_guard<std::recursive_mutex> guard(_lock);
        _campers.erase(Raw(player));
    }

    void Camp::OnLogout(Player* player)
    {
        if (!player)
            return;
        // The character was saved already (WorldSession::LogoutPlayer saves before this hook), with the camp rest bit if
        // the player was at a fire (never for a player who rested without a bit: they had no camp bit to save). Fires
        // and objects stay until they go out; the timers stay so a relog resets nothing.
        std::lock_guard<std::recursive_mutex> guard(_lock);
        _campers.erase(Raw(player));
    }

    // =============================================================================================
    // XP and food
    // =============================================================================================
    bool Camp::IsWellFed(Player* player)
    {
        for (auto const& [spellId, app] : player->GetAppliedAuras())
            if (sSpellMgr->IsSpellMemberOfSpellGroup(spellId, SpellGroup(WellFedGroup)))
                return true;
        return false;
    }

    uint32_t Camp::XpBonusPct(Player* player)
    {
        if (!player || !_xpOn.load())
            return 0;
        // nothing at the level cap (no XP to add to), nor for a character that turned XP off
        if (player->GetLevel() >= sWorld->getIntConfig(CONFIG_MAX_PLAYER_LEVEL) || player->HasPlayerFlag(PLAYER_FLAGS_NO_XP_GAIN))
            return 0;
        bool warm = false;
        {
            std::lock_guard<std::mutex> guard(_timerLock);
            auto it = _timers.find(Low(player));
            warm = it != _timers.end() && it->second.warmthEnd > NowSec();
        }
        uint32_t const food = _xpFood.load();
        bool const fed = food > 0 && IsWellFed(player);
        return CampRules::BonusPct(warm, fed, _xpWarmth.load(), food, _xpMax.load());
    }

    // =============================================================================================
    // Fires
    // =============================================================================================
    void Camp::OnGameObjectAdded(GameObject* go)
    {
        if (!go)
            return;
        uint32_t const entry = go->GetEntry();
        uint32_t const n = _hookCount.load();
        bool match = false;
        for (uint32_t i = 0; i < n && i < MaxHookEntries && !match; ++i)
            match = _hookEntries[i].load() == entry;
        if (!match)
            return;
        // a Basic Campfire counts only when a player made it (the world spawns in Outland do not); fires count only on
        // the continents (no dungeon, raid, battleground or arena)
        bool const permanent = go->GetSpawnId() != 0;
        if ((entry == BasicCampfire && permanent) || !go->GetMap() || !go->GetMap()->IsWorldMap())
            return;
        NewFire f;
        f.guid = go->GetGUID().GetRawValue();
        f.mapId = go->GetMapId();
        f.entry = entry;
        f.permanent = permanent;
        f.owner = go->GetOwnerGUID().GetRawValue();
        f.x = go->GetPositionX();
        f.y = go->GetPositionY();
        f.z = go->GetPositionZ();
        f.o = go->GetOrientation();
        std::lock_guard<std::mutex> guard(_newLock);
        if (_newFires.size() < 4096)
            _newFires.push_back(f);
    }

    void Camp::DrainNewFires()
    {
        std::vector<NewFire> list;
        {
            std::lock_guard<std::mutex> guard(_newLock);
            list.swap(_newFires);
        }
        for (NewFire const& n : list)
        {
            if (_fires.count(n.guid))
                continue;   // a camp fire of our own, registered when it was made
            Fire& f = _fires[n.guid];
            f.guid = n.guid;
            f.mapId = n.mapId;
            f.entry = n.entry;
            f.permanent = n.permanent;
            f.owner = n.owner;
            f.x = n.x;
            f.y = n.y;
            f.z = n.z;
            f.o = n.o;
        }
    }

    GameObject* Camp::Resolve(Fire const& fire, Map** mapOut)
    {
        Map* map = sMapMgr->FindBaseNonInstanceMap(fire.mapId);
        if (mapOut)
            *mapOut = map;
        return map ? map->GetGameObject(ObjectGuid(fire.guid)) : nullptr;
    }

    void Camp::RemoveFire(uint64_t fireGuid, bool despawnFire)
    {
        auto it = _fires.find(fireGuid);
        if (it == _fires.end())
            return;
        Map* map = nullptr;
        GameObject* go = Resolve(it->second, &map);
        if (map)
        {
            for (CampObject const& o : it->second.objects)
            {
                if (GameObject* obj = map->GetGameObject(ObjectGuid(o.guid)))
                {
                    obj->SetRespawnTime(0);
                    obj->Delete();
                }
            }
        }
        if (despawnFire && go && !it->second.permanent)
        {
            go->SetRespawnTime(0);
            go->Delete();
        }
        _fires.erase(it);
    }

    // The fire the player is at, checked again now (the tick may be half a second old). Nothing when the player cannot
    // rest at a fire (dead, in combat, ...).
    Camp::Fire* Camp::FireOf(Player* player, GameObject** goOut)
    {
        auto c = _campers.find(Raw(player));
        if (c == _campers.end() || !c->second.fire)
            return nullptr;
        auto f = _fires.find(c->second.fire);
        if (f == _fires.end())
            return nullptr;
        GameObject* go = Resolve(f->second);
        if (!go || !go->isSpawned() || !CanRestAtFire(player) || !player->IsWithinDistInMap(go, _cfg.radius))
            return nullptr;
        if (!f->second.permanent && go->GetRespawnTime() <= static_cast<time_t>(NowSec()))
            return nullptr;
        if (goOut)
            *goOut = go;
        return &f->second;
    }

    GameObject* Camp::SummonFire(Player* player, uint32_t lifetimeSec)
    {
        if (!_cfg.fireEntry)
            return nullptr;
        Map* map = player->GetMap();
        float const o = player->GetOrientation();
        float x = player->GetPositionX() + std::cos(o) * FireDistance;
        float y = player->GetPositionY() + std::sin(o) * FireDistance;
        float z = player->GetPositionZ();
        float const ground = map->GetHeight(player->GetPhaseMask(), x, y, z + 2.0f, true, 6.0f);
        if (ground > INVALID_HEIGHT && std::fabs(ground - z) <= 2.5f && player->IsWithinLOS(x, y, ground + 1.0f))
            z = ground;
        else
        {
            // a wall, a ledge or a slope in front: the fire goes at the player's feet
            x = player->GetPositionX();
            y = player->GetPositionY();
        }
        GameObject* go = map->SummonGameObject(_cfg.fireEntry, x, y, z, o, 0.0f, 0.0f, 0.0f, 0.0f, lifetimeSec, false);
        if (!go)
            return nullptr;
        // no owner: the fire must outlive its maker's logout (a player-owned object goes with its owner) and goes out by
        // itself after lifetimeSec
        if (go->GetPhaseMask() != player->GetPhaseMask())
            go->SetPhaseMask(player->GetPhaseMask(), true);
        Fire& f = _fires[go->GetGUID().GetRawValue()];
        f = Fire();
        f.guid = go->GetGUID().GetRawValue();
        f.mapId = map->GetId();
        f.entry = _cfg.fireEntry;
        f.ours = true;
        f.permanent = false;
        f.owner = Raw(player);
        f.x = x;
        f.y = y;
        f.z = z;
        f.o = o;
        return go;
    }

    bool Camp::InCityOrSanctuary(Player* player)
    {
        if (player->HasRestFlag(REST_FLAG_IN_CITY))
            return true;
        for (uint32_t id : { player->GetZoneId(), player->GetAreaId() })
        {
            AreaTableEntry const* a = sAreaTableStore.LookupEntry(id);
            if (a && ((a->flags & (AREA_FLAG_CAPITAL | AREA_FLAG_SLAVE_CAPITAL)) || a->IsSanctuary()))
                return true;
        }
        return false;
    }

    // =============================================================================================
    // Intents
    // =============================================================================================
    void Camp::HandleCamp(Player* player, Intent const& intent)
    {
        // world thread (the chat hook); the rate limit is the Endpoint's and BleakholdUi.Camp.Enable is Mgr::Dispatch's
        std::lock_guard<std::recursive_mutex> guard(_lock);
        if (!_cfg.campOn)
        {
            Ui::Refuse(player, intent, "camp_off", "Camping is turned off on this realm.");
            return;
        }
        switch (intent.campAct)
        {
            case CampAct::Make: MakeCamp(player, intent); break;
            case CampAct::Object: PlaceObject(player, intent); break;
            case CampAct::Pack: PackUp(player, intent); break;
        }
    }

    void Camp::MakeCamp(Player* player, Intent const& intent)
    {
        if (!player->IsInWorld())
            return;
        if (!player->IsAlive())
            return Ui::Refuse(player, intent, "camp_dead", "You cannot make camp while dead.");
        if (player->IsInCombat())
            return Ui::Refuse(player, intent, "camp_combat", "You cannot make camp in combat.");
        if (player->IsMounted() || player->GetVehicle() || player->IsInFlight() || player->IsFlying() || player->IsFalling() ||
            player->GetTransport())
            return Ui::Refuse(player, intent, "camp_mounted", "Stand on solid ground to make camp: not mounted, flying, falling, on a vehicle or a ship.");
        if (player->isSwimming() || player->IsInWater())
            return Ui::Refuse(player, intent, "camp_water", "You cannot make camp in water.");
        if (player->GetLevel() < _cfg.minLevel)
            return Ui::Refuse(player, intent, "camp_level", "You can make camp from level " + std::to_string(_cfg.minLevel) + ".");
        if (!player->GetMap()->IsWorldMap() || player->InBattleground() || player->InArena() || player->pvpInfo.IsInFFAPvPArea)
            return Ui::Refuse(player, intent, "camp_instance", "You cannot make camp in a dungeon, raid, battleground or arena.");
        if (InCityOrSanctuary(player))
            return Ui::Refuse(player, intent, "camp_city", "You cannot make camp in a city or a sanctuary.");
        if (!player->IsOutdoors())
            return Ui::Refuse(player, intent, "camp_indoors", "You can only make camp outdoors.");
        uint64_t const now = NowSec();
        Timers const t = TimersOf(Low(player));
        if (t.campReadyAt > now)
            return Ui::Refuse(player, intent, "camp_cooldown", "You made camp not long ago. You can make camp again in " +
                Minutes(CampRules::SecondsLeft(t.campReadyAt, now)) + ".");

        // one camp fire per player: the old one goes out with its objects
        std::vector<uint64_t> old;
        for (auto const& [guid, f] : _fires)
            if (f.ours && f.owner == Raw(player))
                old.push_back(guid);
        for (uint64_t g : old)
            RemoveFire(g, true);

        GameObject* go = SummonFire(player, _cfg.fireSec);
        if (!go)
        {
            LOG_ERROR("module", "[Bleakhold] {} could not light a camp fire (gameobject_template {})", player->GetName(), _cfg.fireEntry);
            return Ui::Refuse(player, intent, "failed", TextFailed);
        }
        {
            std::lock_guard<std::mutex> tg(_timerLock);
            _timers[Low(player)].campReadyAt = now + _cfg.cooldownSec;
        }
        _campers[Raw(player)].want = true;
        DebugLog(player->GetName() + " made camp (" + go->GetGUID().ToString() + ")");
    }

    void Camp::PlaceObject(Player* player, Intent const& intent)
    {
        if (!player->IsInWorld())
            return;
        if (!player->IsAlive())
            return Ui::Refuse(player, intent, "camp_dead", TextDead);
        if (player->IsInCombat())
            return Ui::Refuse(player, intent, "camp_combat", TextCombat);
        GameObject* fireGo = nullptr;
        Fire* fire = FireOf(player, &fireGo);
        if (!fire || !fireGo)
            return Ui::Refuse(player, intent, "camp_nofire", "You are not at a campfire.");
        uint64_t const me = Raw(player);
        for (CampObject const& o : fire->objects)
            if (o.owner == me)
                return Ui::Refuse(player, intent, "camp_placed", "You already placed an object at this fire.");
        if (fire->objects.size() >= CampRules::MaxObjectsPerFire)
            return Ui::Refuse(player, intent, "camp_full", "This fire already has three camp objects.");
        CampRules::Profession const* prof = ProfessionOf(intent.campSkill);
        if (!prof)
            return Ui::Refuse(player, intent, "camp_skill", "That profession has no camp object.");
        uint8_t const tier = PlaceableTier(player, *prof);
        if (!tier)
            return Ui::Refuse(player, intent, "camp_skill", "Your skill in that profession is too low for a camp object (" +
                std::to_string(_cfg.tierSkill[0]) + " needed).");

        uint64_t const now = NowSec();
        uint32_t lifetime = fire->permanent ? _cfg.fireSec : CampRules::SecondsLeft(static_cast<uint64_t>(fireGo->GetRespawnTime()), now);
        if (!lifetime)
            return Ui::Refuse(player, intent, "camp_nofire", "This fire is going out.");
        uint8_t slot = 0;
        while (slot < CampRules::MaxObjectsPerFire &&
            std::any_of(fire->objects.begin(), fire->objects.end(), [slot](CampObject const& o) { return o.slot == slot; }))
            ++slot;
        if (slot >= CampRules::MaxObjectsPerFire)
            return Ui::Refuse(player, intent, "camp_full", "This fire already has three camp objects.");

        Map* map = fireGo->GetMap();
        CampRules::Offset const off = CampRules::SlotOffset(slot, fire->o, ObjectDistance);
        float const x = fire->x + off.x;
        float const y = fire->y + off.y;
        float z = fire->z;
        float const ground = map->GetHeight(fireGo->GetPhaseMask(), x, y, fire->z + 2.0f, true, 6.0f);
        if (ground > INVALID_HEIGHT && std::fabs(ground - fire->z) <= 3.0f)
            z = ground;
        uint32_t const entry = prof->objects[tier - 1];
        GameObject* obj = map->SummonGameObject(entry, x, y, z, off.angle, 0.0f, 0.0f, 0.0f, 0.0f, lifetime, false);
        if (!obj)
        {
            LOG_ERROR("module", "[Bleakhold] {} could not place camp object {} (gameobject_template {})", player->GetName(), prof->key, entry);
            return Ui::Refuse(player, intent, "failed", TextFailed);
        }
        if (obj->GetPhaseMask() != fireGo->GetPhaseMask())
            obj->SetPhaseMask(fireGo->GetPhaseMask(), true);
        CampObject o;
        o.guid = obj->GetGUID().GetRawValue();
        o.skill = prof->skill;
        o.tier = tier;
        o.buff = prof->buffs[tier - 1];
        o.owner = me;
        o.slot = slot;
        fire->objects.push_back(o);
        DebugLog(player->GetName() + " placed " + prof->key + " tier " + std::to_string(tier) + " at " + ObjectGuid(fire->guid).ToString());

        // everyone already settled at this fire gets the new buff at once
        for (auto& [guid, c] : _campers)
        {
            if (c.fire != fire->guid)
                continue;
            c.want = true;
            if (c.settled && o.buff)
                if (Player* p = ObjectAccessor::FindPlayer(ObjectGuid(guid)))
                    ApplyObjectBuff(p, o.skill, o.tier, o.buff);
        }
    }

    void Camp::PackUp(Player* player, Intent const& intent)
    {
        if (!player->IsInWorld())
            return;
        uint64_t const me = Raw(player);
        uint64_t target = 0;
        // the fire the player stands at, if it is theirs (a camp fire or a Basic Campfire they lit) ...
        if (Fire* at = FireOf(player))
            if (at->owner == me && !at->permanent)
                target = at->guid;
        // ... else their camp fire, wherever it is
        if (!target)
            for (auto const& [guid, f] : _fires)
                if (f.ours && f.owner == me)
                    target = guid;
        if (!target)
            return Ui::Refuse(player, intent, "camp_nofire", "You have no campfire to pack up.");
        for (auto& [guid, c] : _campers)
            if (c.fire == target)
                c.want = true;
        RemoveFire(target, true);
        _campers[me].want = true;
        DebugLog(player->GetName() + " packed up " + ObjectGuid(target).ToString());
    }

    void Camp::HandleGlide(Player* player, Intent const& intent)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        if (!_cfg.glideOn || !_cfg.glideSpell)
            return Ui::Refuse(player, intent, "glide_off", "Gliding is turned off on this realm.");
        if (!player->IsInWorld())
            return;
        if (!CanGlide(player))
            return Ui::Refuse(player, intent, "glide_race", "Your people cannot glide.");
        // no glide in battlegrounds and arenas, Bleakhold Royale's map included (a battleground map: its players
        // drop with their own slow fall, section 17)
        if (player->InBattleground() || player->InArena() || player->GetMap()->IsBattlegroundOrArena())
            return Ui::Refuse(player, intent, RoyaleErr::GlideHere);
        if (!player->IsAlive())
            return Ui::Refuse(player, intent, "dead", TextDead);
        uint64_t const now = NowSec();
        Timers const t = TimersOf(Low(player));
        if (t.glideReadyAt > now)
            return Ui::Refuse(player, intent, "glide_cooldown", "You can glide again in " +
                std::to_string(CampRules::SecondsLeft(t.glideReadyAt, now)) + " s.");
        ApplyAura(player, _cfg.glideSpell, _cfg.glideSec);
        if (!player->HasAura(_cfg.glideSpell))
        {
            LOG_ERROR("module", "[Bleakhold] {} could not glide: spell {} did not land (BleakholdUi.Glide.Spell)", player->GetName(), _cfg.glideSpell);
            return Ui::Refuse(player, intent, "failed", TextFailed);
        }
        {
            std::lock_guard<std::mutex> tg(_timerLock);
            _timers[Low(player)].glideReadyAt = now + _cfg.glideCooldownSec;
        }
        _campers[Raw(player)].want = true;
    }

    void Camp::HandleRepair(Player* player, Intent const& intent)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        if (!_cfg.repairOn && !_cfg.campOn)
            return Ui::Refuse(player, intent, "repair_off", "Field repair is turned off on this realm.");
        if (!player->IsInWorld())
            return;
        if (!player->IsAlive())
            return Ui::Refuse(player, intent, "dead", TextDead);
        if (player->IsInCombat())
            return Ui::Refuse(player, intent, "in_combat", "You cannot repair in combat.");
        uint32_t const smith = player->HasSkill(CampRules::SkillBlacksmithing) ? player->GetSkillValue(CampRules::SkillBlacksmithing) : 0;
        Fire* fire = _cfg.campOn ? FireOf(player) : nullptr;
        if (!CampRules::RepairAllowed(_cfg.repairOn, smith, _cfg.repairMinSkill, _cfg.campOn, fire && AnvilAt(*fire)))
        {
            std::string text = _cfg.campOn ? "Repair at a campfire with an anvil" : "You cannot repair here";
            if (_cfg.repairOn)
                text += (_cfg.campOn ? ", or learn Blacksmithing " : ": you need Blacksmithing ") + std::to_string(std::max<uint32_t>(1, _cfg.repairMinSkill));
            return Ui::Refuse(player, intent, "repair_skill", text + ".");
        }
        float const costMod = CampRules::RepairCostMod(smith > 0, _cfg.repairDiscountPct);
        uint64_t const cost = RepairCost(player, costMod);
        if (!cost)
        {
            Ui::Toast(player, ToastKind::Info, "Repair", "Nothing needs repairing.");
            return;
        }
        if (cost > 0xFFFFFFFFull || !player->HasEnoughMoney(static_cast<uint32_t>(cost)))
            return Ui::Refuse(player, intent, "repair_gold", "You cannot pay for the repair (" +
                CampRules::MoneyText(static_cast<uint32_t>(std::min<uint64_t>(cost, 0xFFFFFFFFull))) + ").");
        // DurabilityRepairAll returns the cost only when a guild bank pays: the toast shows the money that went
        uint32_t const before = player->GetMoney();
        player->DurabilityRepairAll(true, costMod, false);
        uint32_t const paid = CampRules::MoneySpent(before, player->GetMoney());
        Ui::Toast(player, ToastKind::Info, "Repaired", "Everything repaired for " + CampRules::MoneyText(paid) + ".");
    }

    // =============================================================================================
    // Settling and buffs
    // =============================================================================================
    void Camp::ApplyAura(Player* player, uint32_t spellId, uint32_t seconds)
    {
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!info)
            return;
        // triggered: no reagent, no cast time, no cooldown (none is recorded either)
        player->CastSpell(player, spellId, true);
        // the spell's own duration is replaced unless it is a passive or a permanent aura
        if (Aura* aura = player->GetAura(spellId, player->GetGUID()))
        {
            if (!aura->IsPassive() && !aura->IsPermanent() && aura->GetMaxDuration() > 0)
            {
                int32_t const ms = static_cast<int32_t>(std::min<uint32_t>(seconds, 86400) * 1000);
                aura->SetMaxDuration(ms);
                aura->SetDuration(ms);
            }
        }
    }

    void Camp::ApplyObjectBuff(Player* player, uint32_t skill, uint8_t tier, uint32_t buff)
    {
        if (!buff)
            return;
        // one buff per profession: a higher tier already on the player stays (never a downgrade), a lower one is replaced
        if (CampRules::Profession const* prof = ProfessionOf(skill))
        {
            for (uint8_t t = tier; t < CampRules::TierCount; ++t)
                if (prof->buffs[t] && prof->buffs[t] != buff && player->HasAura(prof->buffs[t], player->GetGUID()))
                    return;
            for (uint8_t t = 0; t + 1 < tier; ++t)
                if (prof->buffs[t] && prof->buffs[t] != buff)
                    player->RemoveAurasDueToSpell(prof->buffs[t], player->GetGUID());
        }
        ApplyAura(player, buff, _cfg.buffSec);
    }

    void Camp::Settle(Player* player, Fire const& fire)
    {
        for (CampObject const& o : fire.objects)
            ApplyObjectBuff(player, o.skill, o.tier, o.buff);
        {
            // a refresh: the warmth starts over, it never adds up
            std::lock_guard<std::mutex> tg(_timerLock);
            _timers[Low(player)].warmthEnd = NowSec() + _cfg.warmthSec;
        }
        if (_cfg.warmthSpell)
            ApplyAura(player, _cfg.warmthSpell, _cfg.warmthSec);
        DebugLog(player->GetName() + " settled at " + ObjectGuid(fire.guid).ToString());
    }

    // =============================================================================================
    // CAMPST
    // =============================================================================================
    CampState Camp::StateOf(Player* player)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        CampState s;
        if (!player)
            return s;
        uint64_t const now = NowSec();
        uint64_t const me = Raw(player);
        GameObject* go = nullptr;
        Fire* fire = _cfg.campOn ? FireOf(player, &go) : nullptr;
        auto c = _campers.find(me);
        if (fire && go && c != _campers.end())
        {
            Camper const& cp = c->second;
            s.state = cp.settled ? CampStateId::Camping : CampStateId::Resting;
            if (!cp.settled)
            {
                uint64_t const since = Mgr::NowMs() - cp.arrivedMs;
                uint64_t const need = uint64_t(_cfg.settleSec) * 1000;
                s.settleSec = since >= need ? 0 : static_cast<uint32_t>((need - since + 999) / 1000);
            }
            s.fireSec = fire->permanent ? 0 : CampRules::SecondsLeft(static_cast<uint64_t>(go->GetRespawnTime()), now);
            s.mine = fire->owner == me;
            bool placed = false;
            for (CampObject const& o : fire->objects)
            {
                s.objects.push_back({ o.skill, o.tier, o.owner == me });
                placed = placed || o.owner == me;
            }
            if (!placed && fire->objects.size() < CampRules::MaxObjectsPerFire)
                for (CampRules::Profession const& p : _cfg.professions)
                    if (uint8_t const tier = PlaceableTier(player, p))
                        s.place.push_back({ p.skill, tier });
        }
        Timers const t = TimersOf(Low(player));
        if (_cfg.campOn)
        {
            s.cooldownSec = CampRules::SecondsLeft(t.campReadyAt, now);
            s.warmthSec = CampRules::SecondsLeft(t.warmthEnd, now);
            s.fed = IsWellFed(player);
        }
        s.xpPct = XpBonusPct(player);
        if (CanGlide(player))
            s.glideSec = CampRules::SecondsLeft(t.glideReadyAt, now);
        uint32_t const smith = player->HasSkill(CampRules::SkillBlacksmithing) ? player->GetSkillValue(CampRules::SkillBlacksmithing) : 0;
        s.repair = CampRules::RepairAllowed(_cfg.repairOn, smith, _cfg.repairMinSkill, _cfg.campOn, fire && AnvilAt(*fire));
        return s;
    }

    void Camp::SendState(Player* player, Camper& camper, uint64_t nowMs)
    {
        CampState const st = StateOf(player);
        if (camper.hasSent && !camper.want && !CampRules::Changed(camper.sent, st))
            return;
        if (camper.hasSent && nowMs - camper.sentMs < MinStateGapMs)
        {
            camper.want = true;   // the next tick after the second is over
            return;
        }
        Ui::SendCampState(player, st);
        camper.sent = st;
        camper.hasSent = true;
        camper.want = false;
        camper.sentMs = nowMs;
    }

    void Camp::RequestState(Player* player)
    {
        if (!player)
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        Camper& c = _campers[Raw(player)];
        c.want = true;
        SendState(player, c, Mgr::NowMs());
    }

    // =============================================================================================
    // The tick
    // =============================================================================================
    void Camp::Update(uint64_t nowMs)
    {
        if (nowMs - _lastTickMs < TickMs)
            return;
        _lastTickMs = nowMs;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        DrainNewFires();
        uint64_t const now = NowSec();

        // 1. who is at which fire: the one they were at, else their own, else the nearest
        struct Best { uint64_t fire = 0; float dist = 0; int rank = 0; };
        std::unordered_map<uint64_t, Best> best;
        std::vector<uint64_t> gone;
        for (auto& [guid, fire] : _fires)
        {
            Map* map = nullptr;
            GameObject* go = Resolve(fire, &map);
            if (!go)
            {
                gone.push_back(guid);
                continue;
            }
            fire.objects.erase(std::remove_if(fire.objects.begin(), fire.objects.end(),
                [map](CampObject const& o) { return !map->GetGameObject(ObjectGuid(o.guid)); }), fire.objects.end());
            if (!_cfg.campOn || !go->isSpawned() || (!fire.permanent && go->GetRespawnTime() <= static_cast<time_t>(now)))
                continue;
            std::vector<Player*> players;
            Acore::AnyPlayerInObjectRangeCheck check(go, _cfg.radius, true, false);
            Acore::PlayerListSearcher<Acore::AnyPlayerInObjectRangeCheck> searcher(go, players, check);
            Cell::VisitObjects(go, searcher, _cfg.radius);
            for (Player* p : players)
            {
                if (!CanRestAtFire(p))
                    continue;
                uint64_t const pg = Raw(p);
                auto c = _campers.find(pg);
                int const rank = c != _campers.end() && c->second.fire == guid ? 0 : (fire.owner == pg ? 1 : 2);
                float const d = p->GetDistance(go);
                auto b = best.find(pg);
                if (b == best.end() || rank < b->second.rank || (rank == b->second.rank && d < b->second.dist))
                    best[pg] = { guid, d, rank };
            }
        }
        for (uint64_t g : gone)
            RemoveFire(g, false);   // gone already (went out, despawned, grid unloaded): its objects go too

        // 2. arrivals, rest and settling
        for (auto const& [pg, b] : best)
        {
            Player* p = ObjectAccessor::FindPlayer(ObjectGuid(pg));
            if (!p)
                continue;
            Camper& c = _campers[pg];
            if (c.fire != b.fire)
            {
                c.fire = b.fire;
                c.arrivedMs = nowMs;
                c.settled = false;
                c.want = true;
            }
            // re-asserted every tick: the core clears the bit on an area change. Not while the player rests without any
            // rest bit (mod-guildhouse's SetRestState): taking the bit off later would end that rest as well.
            if (!p->HasRestFlag(REST_FLAG_IN_FACTION_AREA) &&
                CampRules::MaySetCampRestBit(p->HasPlayerFlag(PLAYER_FLAGS_RESTING), AnyRestBit(p)))
                p->SetRestFlag(REST_FLAG_IN_FACTION_AREA);
            if (!c.settled && nowMs - c.arrivedMs >= uint64_t(_cfg.settleSec) * 1000)
            {
                c.settled = true;
                c.want = true;
                auto f = _fires.find(b.fire);
                if (f != _fires.end())
                    Settle(p, f->second);
            }
        }

        // 3. departures (left the radius, combat, death, the fire went out, a teleport)
        for (auto it = _campers.begin(); it != _campers.end();)
        {
            Camper& c = it->second;
            if (c.fire && !best.count(it->first))
            {
                Player* p = ObjectAccessor::FindConnectedPlayer(ObjectGuid(it->first));
                if (!p)
                {
                    it = _campers.erase(it);
                    continue;
                }
                // a player between maps gets the core's area update on arrival, which clears the bit
                if (p->IsInWorld())
                    EndCampRest(p);
                c.fire = 0;
                c.settled = false;
                c.want = true;
            }
            if (!c.fire && !c.hasSent && !c.want)
            {
                it = _campers.erase(it);   // nothing to remember (no fire, no Bleakhold UI)
                continue;
            }
            ++it;
        }

        // 4. CAMPST to the players with the Bleakhold UI: on every change, at most once per second
        if (_cfg.campOn || _cfg.glideOn || _cfg.repairOn)
            Mgr::Instance().ForEachReadyPlayer([&](Player* p) { SendState(p, _campers[Raw(p)], nowMs); });

        // 5. forget expired timers and campers who are gone
        if (nowMs - _lastPurgeMs >= PurgeMs)
        {
            _lastPurgeMs = nowMs;
            {
                std::lock_guard<std::mutex> tg(_timerLock);
                for (auto it = _timers.begin(); it != _timers.end();)
                {
                    Timers const& t = it->second;
                    if (t.campReadyAt <= now && t.warmthEnd <= now && t.glideReadyAt <= now)
                        it = _timers.erase(it);
                    else
                        ++it;
                }
            }
            for (auto it = _campers.begin(); it != _campers.end();)
            {
                if (!ObjectAccessor::FindConnectedPlayer(ObjectGuid(it->first)))
                    it = _campers.erase(it);
                else
                    ++it;
            }
        }
    }

    // =============================================================================================
    // GM command
    // =============================================================================================
    std::vector<std::string> Camp::Describe(Player* player)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        std::vector<std::string> out;
        CampState const s = StateOf(player);
        char const* state = s.state == CampStateId::Camping ? "camping (settled)" : (s.state == CampStateId::Resting ? "resting at a fire" : "not at a fire");
        out.push_back("Camp " + player->GetName() + ": " + state + (s.state == CampStateId::Resting ? ", settled in " + std::to_string(s.settleSec) + " s" : "") +
            (s.fireSec ? ", fire out in " + std::to_string(s.fireSec) + " s" : "") + (s.mine ? " (own fire)" : ""));
        std::string objs;
        for (CampObjectInfo const& o : s.objects)
            objs += (objs.empty() ? "" : ", ") + std::to_string(o.skill) + " tier " + std::to_string(o.tier) + (o.mine ? " (theirs)" : "");
        std::string place;
        for (CampPlace const& p : s.place)
            place += (place.empty() ? "" : ", ") + std::to_string(p.skill) + " tier " + std::to_string(p.tier);
        out.push_back("Objects: " + (objs.empty() ? std::string("none") : objs) + "; may place: " + (place.empty() ? std::string("nothing") : place));
        out.push_back("Make camp in " + std::to_string(s.cooldownSec) + " s; warmth " + std::to_string(s.warmthSec) + " s; XP bonus " +
            std::to_string(s.xpPct) + "%; Well Fed " + (s.fed ? "yes" : "no") + "; glide " + (s.glideSec ? "in " + std::to_string(*s.glideSec) + " s" : "no") +
            "; repair " + (s.repair ? "yes" : "no") + "; resting flag " + (player->HasPlayerFlag(PLAYER_FLAGS_RESTING) ? "on" : "off"));
        uint64_t const me = Raw(player);
        for (auto const& [guid, f] : _fires)
            if (f.ours && f.owner == me)
                out.push_back("Their camp fire: " + ObjectGuid(guid).ToString() + " on map " + std::to_string(f.mapId) + " with " +
                    std::to_string(f.objects.size()) + " objects");
        return out;
    }

    void Camp::ResetCooldowns(Player* player)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        {
            std::lock_guard<std::mutex> tg(_timerLock);
            auto it = _timers.find(Low(player));
            if (it != _timers.end())
            {
                it->second.campReadyAt = 0;
                it->second.glideReadyAt = 0;
            }
        }
        _campers[Raw(player)].want = true;
    }

    bool Camp::SpawnFireFor(Player* player, std::string& error)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        if (!player->IsInWorld() || !player->GetMap()->IsWorldMap())
        {
            error = "camp fires only count on the continents (not in a dungeon, raid, battleground or arena)";
            return false;
        }
        std::vector<uint64_t> old;
        for (auto const& [guid, f] : _fires)
            if (f.ours && f.owner == Raw(player))
                old.push_back(guid);
        for (uint64_t g : old)
            RemoveFire(g, true);
        if (!SummonFire(player, _cfg.fireSec))
        {
            error = "the fire could not be summoned (gameobject_template " + std::to_string(_cfg.fireEntry) + ")";
            return false;
        }
        _campers[Raw(player)].want = true;
        return true;
    }

    Camp::Counts Camp::GetCounts()
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        Counts n;
        n.fires = _fires.size();
        for (auto const& [guid, f] : _fires)
            n.objects += f.objects.size();
        for (auto const& [guid, c] : _campers)
            if (c.fire)
                ++n.atFire;
        return n;
    }
}
