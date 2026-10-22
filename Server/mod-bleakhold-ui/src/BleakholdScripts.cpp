/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Hooks: the self-whisper that carries client messages (section 2), the prefix guard on every other
 * addon channel, login/logout, configuration and the world tick.
 */

#include "BleakholdCodec.h"
#include "BleakholdData.h"
#include "BleakholdMgr.h"

#include "Player.h"
#include "ScriptMgr.h"
#include "SharedDefines.h"

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
            PLAYERHOOK_CAN_PLAYER_USE_PRIVATE_CHAT,
            PLAYERHOOK_CAN_PLAYER_USE_GROUP_CHAT,
            PLAYERHOOK_CAN_PLAYER_USE_GUILD_CHAT,
        }) { }

        using PlayerScript::OnPlayerCanUseChat;

        void OnPlayerLogin(Player* player) override
        {
            Mgr::Instance().OnLogin(player);
        }

        void OnPlayerLogout(Player* player) override
        {
            Mgr::Instance().OnLogout(player);
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
        }) { }

        void OnAfterConfigLoad(bool /*reload*/) override
        {
            Mgr::Instance().LoadConfig();
        }

        void OnStartup() override
        {
            Mgr::Instance().MarkWorldThread();
            Data::Instance().LoadAll();
            Config const& c = Mgr::Instance().Cfg();
            LOG_INFO("server.loading", ">> Bleakhold UI protocol {}: data version {}, feature bits {}, frames up to {} bytes",
                c.enable ? "enabled" : "DISABLED (BleakholdUi.Enable = 0)", Mgr::Instance().DataVersion(), c.featureBits, c.maxFrameBody);
        }

        void OnUpdate(uint32 diff) override
        {
            Mgr::Instance().Update(diff);
        }
    };
}

void AddBleakholdScripts()
{
    Bleakhold::Data::Instance().RegisterDefaults();
    new BleakholdPlayerScript();
    new BleakholdWorldScript();
}
