/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Hooks: the self-whisper that carries client messages (section 2), the prefix guard on every other
 * addon channel, login/logout, configuration and the world tick; for camping (section 16) the XP bonus,
 * the end of camp rest when combat starts, the campfires that enter the world, the glide's movement and Walk on Air in
 * the spellbook (spell_bleakhold_walk_on_air); for the cafe (section 21) the shift hooks, the shake helper, tea
 * reputation, cast cancels of step spells, the .gobject guard and the gossip of the owners and head baristas.
 */

#include "BleakholdCafe.h"
#include "BleakholdCamp.h"
#include "BleakholdCodec.h"
#include "BleakholdData.h"
#include "BleakholdMgr.h"

#include "Creature.h"
#include "GameObject.h"
#include "PassiveAI.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SharedDefines.h"
#include "SpellInfo.h"
#include "SpellScript.h"
#include "SpellScriptLoader.h"

namespace
{
    using namespace Bleakhold;

    enum class Prefix : uint8_t { Other, Client, Server };

    // The addon prefix is everything before the first tab, as the client splits it.
    Prefix Classify(std::string const& msg)
    {
        std::string_view const text(msg);
        std::string_view const prefix = text.substr(0, text.find('\t'));
        if (prefix == Proto::ClientPrefix)
            return Prefix::Client;
        if (prefix == Proto::ServerPrefix)
            return Prefix::Server;
        return Prefix::Other;
    }

    class BleakholdPlayerScript : public PlayerScript
    {
    public:
        BleakholdPlayerScript() : PlayerScript("BleakholdPlayerScript", {
            PLAYERHOOK_ON_LOGIN,
            PLAYERHOOK_ON_LOGOUT,
            PLAYERHOOK_ON_DELETE_FROM_DB,
            PLAYERHOOK_CAN_PLAYER_USE_PRIVATE_CHAT,
            PLAYERHOOK_CAN_PLAYER_USE_GROUP_CHAT,
            PLAYERHOOK_CAN_PLAYER_USE_GUILD_CHAT,
            PLAYERHOOK_ON_GIVE_EXP,
            PLAYERHOOK_ON_PLAYER_ENTER_COMBAT,
        }) { }

        using PlayerScript::OnPlayerCanUseChat;

        void OnPlayerLogin(Player* player) override
        {
            Mgr::Instance().OnLogin(player);
            Camp::Instance().OnLogin(player);
        }

        void OnPlayerLogout(Player* player) override
        {
            Mgr::Instance().OnLogout(player);
            Camp::Instance().OnLogout(player);
        }

        // Campfire Warmth and Well Fed (section 16): one bonus, on kill and quest XP only, applied to the amount the core
        // and the modules before this one made (mod-bleakhold's leveling multipliers run first); it is never applied
        // anywhere else, and the core only uses up rested XP on top of it. Map thread.
        void OnPlayerGiveXP(Player* player, uint32& amount, Unit* /*victim*/, uint8 xpSource) override
        {
            if (!amount || (xpSource != XPSOURCE_KILL && xpSource != XPSOURCE_QUEST && xpSource != XPSOURCE_QUEST_DF))
                return;
            if (uint32 const pct = Camp::Instance().XpBonusPct(player))
                amount = CampRules::AddPct(amount, pct);
        }

        // rest lets a player log out in combat: camp rest ends the moment combat starts (map thread)
        void OnPlayerEnterCombat(Player* player, Unit* /*enemy*/) override
        {
            Camp::OnEnterCombat(player);
        }

        // every way a character is deleted for good (the client, the purge of old deleted characters, commands)
        void OnPlayerDeleteFromDB(CharacterDatabaseTransaction /*trans*/, uint32 guid) override
        {
            Data::Instance().ForgetCharacter(guid);
        }

        // Player::Whisper -> here for every whisper, addon whispers included.
        bool OnPlayerCanUseChat(Player* player, uint32 type, uint32 language, std::string& msg, Player* receiver) override
        {
            if (language != uint32(LANG_ADDON))
                return true;
            Prefix const p = Classify(msg);
            if (p == Prefix::Other)
                return true;
            if (p == Prefix::Server)
            {
                // a client may never use the server prefix, and it is never forwarded to anyone
                if (Mgr::Instance().Debug())
                    DebugLog("blocked a BHs addon whisper from " + player->GetName());
                if (receiver == player && Mgr::Instance().Enabled())
                    Mgr::Instance().OnSelfWhisper(player, msg);   // counted against the player's limits
                return false;
            }
            // BHc: only a whisper to yourself is a message to the server; it is never delivered to anyone
            if (type != CHAT_MSG_WHISPER || receiver != player || !Mgr::Instance().Enabled())
                return false;
            return Mgr::Instance().OnSelfWhisper(player, msg);
        }

        // PARTY, RAID, BATTLEGROUND: never relay the Bleakhold prefixes (DBM and other addons pass).
        bool OnPlayerCanUseChat(Player* /*player*/, uint32 /*type*/, uint32 language, std::string& msg, Group* /*group*/) override
        {
            return language != uint32(LANG_ADDON) || Classify(msg) == Prefix::Other;
        }

        bool OnPlayerCanUseChat(Player* /*player*/, uint32 /*type*/, uint32 language, std::string& msg, Guild* /*guild*/) override
        {
            return language != uint32(LANG_ADDON) || Classify(msg) == Prefix::Other;
        }
    };

    class BleakholdWorldScript : public WorldScript
    {
    public:
        BleakholdWorldScript() : WorldScript("BleakholdWorldScript", {
            WORLDHOOK_ON_AFTER_CONFIG_LOAD,
            WORLDHOOK_ON_STARTUP,
            WORLDHOOK_ON_UPDATE,
            WORLDHOOK_ON_SHUTDOWN,
        }) { }

        void OnAfterConfigLoad(bool /*reload*/) override
        {
            Mgr::Instance().LoadConfig();
        }

        void OnStartup() override
        {
            Mgr::Instance().MarkWorldThread();
            Data::Instance().LoadAll();
            Camp::Instance().OnStartup();
            Cafe::Instance().OnStartup();   // always (whatever Cafe.Enable says), so .bleakhold reload can enable it
            Config const& c = Mgr::Instance().Cfg();
            LOG_INFO("server.loading", ">> Bleakhold UI protocol {}: data version {}, feature bits {}, frames up to {} bytes",
                c.enable ? "enabled" : "DISABLED (BleakholdUi.Enable = 0)", Mgr::Instance().DataVersion(), c.featureBits, c.maxFrameBody);
        }

        void OnUpdate(uint32 diff) override
        {
            Mgr::Instance().Update(diff);
        }

        // after the world loop stopped (Main.cpp): the barista rows still in memory are saved at once
        void OnShutdown() override
        {
            Cafe::Instance().OnShutdown();
        }
    };

    // The cafe (section 21; BleakholdCafe.cpp). Registered whatever BleakholdUi.Cafe.Enable says, so the login cleanup
    // of the shift and speed auras always runs. Login, logout, map change and delete are world thread; the others
    // run on map threads and touch only the player and atomics (the cafe queues the rest for its tick).
    class BleakholdCafePlayerScript : public PlayerScript
    {
    public:
        BleakholdCafePlayerScript() : PlayerScript("BleakholdCafePlayerScript", {
            PLAYERHOOK_ON_LOGIN,
            PLAYERHOOK_ON_BEFORE_LOGOUT,
            PLAYERHOOK_ON_LOGOUT,
            PLAYERHOOK_ON_DELETE_FROM_DB,
            PLAYERHOOK_ON_MAP_CHANGED,
            PLAYERHOOK_ON_PLAYER_ENTER_COMBAT,
            PLAYERHOOK_ON_PLAYER_PVP_FLAG_CHANGE,
            PLAYERHOOK_ON_DUEL_REQUEST,
            PLAYERHOOK_ON_DUEL_START,
            PLAYERHOOK_ON_GIVE_REPUTATION,
        }) { }

        void OnPlayerLogin(Player* player) override
        {
            Cafe::Instance().OnLogin(player);
        }

        // before the character is saved (WorldSession::LogoutPlayer): the shift ends and its auras go here
        void OnPlayerBeforeLogout(Player* player) override
        {
            Cafe::Instance().OnBeforeLogout(player);
        }

        void OnPlayerLogout(Player* player) override
        {
            Cafe::Instance().OnLogout(player);
        }

        void OnPlayerDeleteFromDB(CharacterDatabaseTransaction /*trans*/, uint32 guid) override
        {
            Cafe::Instance().OnDeleteCharacter(guid);
        }

        void OnPlayerMapChanged(Player* player) override
        {
            Cafe::Instance().OnMapChanged(player);
        }

        void OnPlayerEnterCombat(Player* player, Unit* /*enemy*/) override
        {
            Cafe::Instance().OnEnterCombatMapThread(player);
        }

        void OnPlayerPVPFlagChange(Player* player, bool state) override
        {
            Cafe::Instance().OnPvpFlagMapThread(player, state);
        }

        void OnPlayerDuelRequest(Player* target, Player* challenger) override
        {
            Cafe::Instance().OnDuelMapThread(target, challenger);
        }

        void OnPlayerDuelStart(Player* player1, Player* player2) override
        {
            Cafe::Instance().OnDuelMapThread(player1, player2);
        }

        // Tea (section 21, Cafe.Buff.TeaRepPct): kill and quest reputation only, never on a battleground or arena
        // map or in a battlefield zone, never for Buff.TeaExcludeFactions. Map thread.
        void OnPlayerGiveReputation(Player* player, int32 factionID, float& amount, ReputationSource repSource) override
        {
            if (amount <= 0.0f || repSource == REPUTATION_SOURCE_SPELL || factionID <= 0)
                return;
            Cafe const& cafe = Cafe::Instance();
            uint32 const pct = cafe.TeaRepPct();
            if (!pct || !cafe.RewardPlaceOk(player) || cafe.TeaExcludesFaction(uint32(factionID)) || !cafe.HasTea(player))
                return;
            amount *= 1.0f + float(pct) / 100.0f;
        }
    };

    // A cancelled cast of a cafe step spell (the player moved, pressed Escape): the step's hold ends (map thread; the
    // cafe checks its atomic set of step spells and queues the rest for its tick).
    class BleakholdCafeSpellScript : public AllSpellScript
    {
    public:
        BleakholdCafeSpellScript() : AllSpellScript("BleakholdCafeSpellScript", { ALLSPELLHOOK_ON_CAST_CANCEL }) { }

        void OnSpellCastCancel(Spell* /*spell*/, Unit* caster, SpellInfo const* spellInfo, bool /*bySelf*/) override
        {
            if (caster && spellInfo && caster->IsPlayer())
                Cafe::Instance().OnSpellCancelMapThread(caster->GetGUID().GetCounter(), spellInfo->Id);
        }
    };

    // The .gobject move / turn guard on cafe pieces (section 3.12.1): GameObject::SaveToDB reports every save here;
    // the cafe only notes the spawn ids of its own pieces (map or world thread).
    class BleakholdCafeGoScript : public AllGameObjectScript
    {
    public:
        BleakholdCafeGoScript() : AllGameObjectScript("BleakholdCafeGoScript") { }

        void OnGameObjectSaveToDB(GameObject* go) override
        {
            Cafe::Instance().OnGoSavedToDbMapThread(go->GetSpawnId(), go->GetEntry());
        }
    };

    // The .npc guard on cafe creatures: Creature::SaveToDB (.npc set level / model / movetype / phase) reports every save
    // here; the cafe only notes its own entries (map or world thread) and removes the row on its tick.
    class BleakholdCafeCreatureScript : public AllCreatureScript
    {
    public:
        BleakholdCafeCreatureScript() : AllCreatureScript("BleakholdCafeCreatureScript") { }

        void OnCreatureSaveToDB(Creature* creature) override
        {
            Cafe::Instance().OnCreatureSavedToDbMapThread(creature->GetSpawnId(), creature->GetEntry());
        }
    };

    // The owners (npc_bh_cafe_owner) and the head baristas (npc_bh_cafe_staff): the gossip menu of section 3.14, and
    // NullCreatureAI so they never act on their own (the cafe's crowd moves them). GossipHello may run on a map
    // thread and builds the menu from the cafe's snapshot; GossipSelect runs on the world thread.
    template <char const* Name>
    class BleakholdCafeNpcScript : public CreatureScript
    {
    public:
        BleakholdCafeNpcScript() : CreatureScript(Name) { }

        bool OnGossipHello(Player* player, Creature* creature) override
        {
            Cafe::Instance().GossipHello(player, creature);
            return true;
        }

        bool OnGossipSelect(Player* player, Creature* creature, uint32 sender, uint32 action) override
        {
            Cafe::Instance().GossipSelect(player, creature, sender, action);
            return true;
        }

        CreatureAI* GetAI(Creature* creature) const override
        {
            return new NullCreatureAI(creature);
        }
    };

    constexpr char CafeOwnerScriptName[] = "npc_bh_cafe_owner";
    constexpr char CafeStaffScriptName[] = "npc_bh_cafe_staff";

    // The glide (section 16): every movement packet, after the core handled the fall (Player::HandleFall) and before it
    // moves the player there. Map threads; one atomic load while nobody glides.
    class BleakholdGlideScript : public MovementHandlerScript
    {
    public:
        BleakholdGlideScript() : MovementHandlerScript("BleakholdGlideScript", { MOVEMENTHOOK_ON_PLAYER_MOVE }) { }

        void OnPlayerMove(Player* player, MovementInfo movementInfo, uint32 opcode) override
        {
            Camp::Instance().OnPlayerMove(player, movementInfo, opcode);
        }
    };

    // Walk on Air in the spellbook (BleakholdUi.Glide.CastSpell, 100801; spell_script_names in
    // data/sql/db-world/02_bleakhold_walk_on_air.sql): the cast runs GLIDE's checks, in the air only, and fails with
    // the client's own cast result (no cooldown spent); the hit starts the module's glide, whose cooldown it shares.
    class spell_bleakhold_walk_on_air : public SpellScript
    {
        PrepareSpellScript(spell_bleakhold_walk_on_air);

        SpellCastResult CheckCast()
        {
            Player* player = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
            if (!player)
                return SPELL_FAILED_DONT_REPORT;
            return static_cast<SpellCastResult>(Camp::Instance().CheckGlideCast(player));
        }

        void HandleDummy(SpellEffIndex /*effIndex*/)
        {
            Player* player = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
            if (player && GetHitUnit() == player)
                Camp::Instance().OnGlideCast(player, GetSpellInfo()->Id, GetSpellInfo()->RecoveryTime);
        }

        void Register() override
        {
            OnCheckCast += SpellCheckCastFn(spell_bleakhold_walk_on_air::CheckCast);
            OnEffectHitTarget += SpellEffectFn(spell_bleakhold_walk_on_air::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
        }
    };

    // Camping (section 16): notes the Basic Campfires players light and the fires of BleakholdUi.Camp.ExtraFireEntries as
    // they enter the world (map threads; the check is a few integer compares for any other object).
    class BleakholdCampFireScript : public AllGameObjectScript
    {
    public:
        BleakholdCampFireScript() : AllGameObjectScript("BleakholdCampFireScript") { }

        void OnGameObjectAddWorld(GameObject* go) override
        {
            Camp::Instance().OnGameObjectAdded(go);
        }
    };
}

void AddBleakholdScripts()
{
    Bleakhold::Data::Instance().RegisterDefaults();
    new BleakholdPlayerScript();
    new BleakholdWorldScript();
    new BleakholdCampFireScript();
    new BleakholdGlideScript();
    RegisterSpellScript(spell_bleakhold_walk_on_air);
    new BleakholdCafePlayerScript();
    new BleakholdCafeSpellScript();
    new BleakholdCafeGoScript();
    new BleakholdCafeCreatureScript();
    new BleakholdCafeNpcScript<CafeOwnerScriptName>();
    new BleakholdCafeNpcScript<CafeStaffScriptName>();
}
