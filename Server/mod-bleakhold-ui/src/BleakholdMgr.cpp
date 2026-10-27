/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "BleakholdMgr.h"
#include "BleakholdCamp.h"
#include "BleakholdCodec.h"
#include "BleakholdData.h"
#include "BleakholdEmoji.h"

#include "Chat.h"
#include "Config.h"
#include "GameTime.h"
#include "Group.h"
#include "Log.h"
#include "ObjectAccessor.h"
#include "ObjectGuid.h"
#include "Player.h"
#include "Realm.h"
#include "SharedDefines.h"
#include "World.h"
#include "WorldPacket.h"
#include "WorldSession.h"
#include "WorldSessionMgr.h"

#include <algorithm>
#include <chrono>
#include <ctime>

namespace Bleakhold
{
    namespace
    {
        constexpr char const* TagNames[] = {
            "Raid Legacy", "Server First", "Season", "Queue", "Record", "Case", "Royale",
        };
        constexpr std::size_t TagCount = sizeof(TagNames) / sizeof(TagNames[0]);
        constexpr uint64_t RunMaxAgeMs = 6ull * 3600 * 1000;
        constexpr uint64_t SweepIntervalMs = 60000;

        char const* const TextUnavailable = "This is not available on this realm yet.";
        char const* const TextBusy = "You are doing that too often. Wait a moment and try again.";
        char const* const TextNotLeader = "Only the group leader can do that.";
        char const* const TextEmojiOff = "Emojis are turned off on this realm.";
        char const* const TextDanceOff = "Dances are turned off on this realm.";
        char const* const TextCaseOff = "Cases are turned off on this realm.";
        char const* const TextCampOff = "Camping is turned off on this realm.";
        char const* const TextGlideOff = "Gliding is turned off on this realm.";
        char const* const TextRepairOff = "Field repair is turned off on this realm.";

        bool IsHex6(std::string const& s)
        {
            if (s.size() != 6)
                return false;
            for (char c : s)
                if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f')))
                    return false;
            return true;
        }

        int32_t LocalUtcOffsetMinutes()
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
            // mktime treats both as local time; their difference is the offset
            utc.tm_isdst = local.tm_isdst;
            double const diff = std::difftime(std::mktime(&local), std::mktime(&utc));
            return static_cast<int32_t>(diff / 60.0);
        }

        std::string OneLine(std::string_view text)
        {
            std::string out(text);
            for (char& c : out)
                if (c == '\n' || c == '\r' || c == '\0')
                    c = ' ';
            return out;
        }
    }

    void DebugLog(std::string const& line)
    {
        if (Mgr::Instance().Debug())
            LOG_INFO("module", "[Bleakhold] {}", line);
    }

    Mgr& Mgr::Instance()
    {
        static Mgr instance;
        return instance;
    }

    uint64_t Mgr::NowMs()
    {
        return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count());
    }

    // =============================================================================================
    // Configuration and lifecycle
    // =============================================================================================
    void Mgr::LoadConfig()
    {
        Config c;
        c.enable = sConfigMgr->GetOption<bool>("BleakholdUi.Enable", true);
        c.debug = sConfigMgr->GetOption<bool>("BleakholdUi.Debug", false);
        c.realmName = sConfigMgr->GetOption<std::string>("BleakholdUi.RealmName", "");
        c.siteUrl = sConfigMgr->GetOption<std::string>("BleakholdUi.SiteUrl", "");
        int32_t const offset = sConfigMgr->GetOption<int32_t>("BleakholdUi.UtcOffsetMinutes", -10000);
        c.utcOffsetAuto = offset < -1440 || offset > 1440;
        c.utcOffsetMin = c.utcOffsetAuto ? 0 : offset;
        c.minProto = std::max<uint32_t>(1, sConfigMgr->GetOption<uint32_t>("BleakholdUi.MinProtocol", 1));
        c.dataVersion = sConfigMgr->GetOption<uint32_t>("BleakholdUi.DataVersion", 0);
        c.seasonId = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Season.Id", 0);

        uint32_t bits = 0;
        if (sConfigMgr->GetOption<bool>("BleakholdUi.Feature.RiftScoring", false))
            bits |= FeatureRiftScoring;
        if (sConfigMgr->GetOption<bool>("BleakholdUi.Feature.Shards", false))
            bits |= FeatureShards;
        if (sConfigMgr->GetOption<bool>("BleakholdUi.Feature.Season", true))
            bits |= FeatureSeason;
        if (sConfigMgr->GetOption<bool>("BleakholdUi.Feature.Leaderboards", true))
            bits |= FeatureLeaderboards;
        if (sConfigMgr->GetOption<bool>("BleakholdUi.Feature.Collections", false))
            bits |= FeatureCollections;
        c.emojiEnable = sConfigMgr->GetOption<bool>("BleakholdUi.Emoji.Enable", true);
        if (c.emojiEnable)
            bits |= FeatureEmoji;  // the catalogue is never empty (static_assert in BleakholdEmoji.h)
        c.danceEnable = sConfigMgr->GetOption<bool>("BleakholdUi.Dance.Enable", true);
        if (c.danceEnable)
            bits |= FeatureDance;  // the catalogue is never empty (static_assert in BleakholdDance.h)
        // FeatureCases also needs a case in bleakhold_case: SendHello adds it
        c.caseEnable = sConfigMgr->GetOption<bool>("BleakholdUi.Case.Enable", true);
        // camping (section 16): the rest of BleakholdUi.Camp.*, Glide.* and Repair.* is Camp::LoadConfig's
        c.campEnable = sConfigMgr->GetOption<bool>("BleakholdUi.Camp.Enable", true);
        if (c.campEnable)
            bits |= FeatureCamp;
        c.glideEnable = sConfigMgr->GetOption<bool>("BleakholdUi.Glide.Enable", true);
        if (c.glideEnable)
            bits |= FeatureGlide;
        c.repairEnable = sConfigMgr->GetOption<bool>("BleakholdUi.Repair.Enable", true);
        if (c.repairEnable)
            bits |= FeatureFieldRepair;
        c.serverPullTimer = sConfigMgr->GetOption<bool>("BleakholdUi.KeyRun.ServerPullTimer", false);
        if (c.serverPullTimer)
            bits |= FeatureServerPullTimer;
        c.featureBits = bits;

        uint32_t const body = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Frame.MaxBody", 1000);
        c.maxFrameBody = std::clamp<std::size_t>(body, Proto::MinServerBody, Proto::MaxServerBody);

        Proto::Limits& l = c.limits;
        l.burst = std::max(1.0f, sConfigMgr->GetOption<float>("BleakholdUi.RateLimit.Burst", 10.0f));
        l.perSecond = std::max(0.1f, sConfigMgr->GetOption<float>("BleakholdUi.RateLimit.PerSecond", 5.0f));
        l.floodDrops = sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.FloodDrops", 200);
        l.floodWindowMs = 1000 * std::max<uint32_t>(1, sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.FloodWindowSec", 60));
        l.floodMuteMs = 1000 * sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.FloodMuteSec", 60);
        l.helloIntervalMs = sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.HelloIntervalMs", 5000);
        l.getTopicIntervalMs = sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.GetTopicIntervalMs", 1000);
        l.heavyTopicIntervalMs = sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.HeavyTopicIntervalMs", 5000);
        l.leaderboardPerSecond = std::max(0.1f, sConfigMgr->GetOption<float>("BleakholdUi.RateLimit.LeaderboardPerSecond", 2.0f));
        l.queueIntervalMs = sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.QueueIntervalMs", 1000);
        l.keyIntervalMs = sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.KeyIntervalMs", 2000);
        l.claimPerSecond = std::max(0.1f, sConfigMgr->GetOption<float>("BleakholdUi.RateLimit.ClaimPerSecond", 2.0f));
        l.duplicateWindowMs = sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.DuplicateWindowMs", 1000);
        l.emojiIntervalMs = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Emoji.CooldownMs", 2500);
        l.danceIntervalMs = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Dance.CooldownMs", 1000);
        l.caseIntervalMs = sConfigMgr->GetOption<uint32_t>("BleakholdUi.Case.CooldownMs", 1000);
        l.campIntervalMs = sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.CampIntervalMs", 1000);
        l.glideIntervalMs = sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.GlideIntervalMs", 1000);
        l.repairIntervalMs = sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.RepairIntervalMs", 2000);
        l.royaleIntervalMs = sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.RoyaleIntervalMs", 500);
        l.royaleDeployIntervalMs =
            sConfigMgr->GetOption<uint32_t>("BleakholdUi.RateLimit.RoyaleDeployIntervalMs", 1000);

        c.heartbeatMs = 1000 * std::max<uint32_t>(1, sConfigMgr->GetOption<uint32_t>("BleakholdUi.KeyRun.HeartbeatSec", 15));
        c.colorTagsWithoutAddon = sConfigMgr->GetOption<bool>("BleakholdUi.Announce.ColorTagsWithoutAddon", true);
        char const* const colorKeys[] = { "RaidLegacy", "ServerFirst", "Season", "Queue", "Record", "Case", "Royale" };
        static_assert(sizeof(colorKeys) / sizeof(colorKeys[0]) == TagCount, "one colour per tag");
        static_assert(std::tuple_size_v<decltype(c.tagColors)> == TagCount, "one default colour per tag");
        for (std::size_t i = 0; i < c.tagColors.size(); ++i)
        {
            std::string const v = sConfigMgr->GetOption<std::string>(std::string("BleakholdUi.Announce.Color.") + colorKeys[i], c.tagColors[i]);
            if (IsHex6(v))
                c.tagColors[i] = v;
            else
                LOG_ERROR("module", "[Bleakhold] BleakholdUi.Announce.Color.{} must be 6 hex digits (RRGGBB); using {}", colorKeys[i], c.tagColors[i]);
        }
        c.tokenItemId = sConfigMgr->GetOption<uint32_t>("BleakholdUi.WarEffort.TokenItemId", 0);
        c.pointsPerToken = sConfigMgr->GetOption<uint32_t>("BleakholdUi.WarEffort.PointsPerToken", 0);
        c.tokenPart = sConfigMgr->GetOption<uint32_t>("BleakholdUi.WarEffort.TokenPart", 1);
        // page 1 holds the podium (ranks 1-3)
        c.leaderboardPageSize = std::clamp<uint32_t>(sConfigMgr->GetOption<uint32_t>("BleakholdUi.Leaderboard.PageSize", 10), 3, 50);
        c.leaderboardMaxRows = std::max<uint32_t>(10, sConfigMgr->GetOption<uint32_t>("BleakholdUi.Leaderboard.MaxRows", 1000));

        {
            std::lock_guard<std::recursive_mutex> guard(_lock);
            _cfg = c;
            _enabled = c.enable;
            _debugOn = c.debug;
            for (auto& [guid, slot] : _slots)
                slot.ep.SetLimits(_cfg.limits);
        }
        Camp::Instance().LoadConfig();   // never under the Mgr lock (lock order: Camp, then Mgr)
    }

    Config Mgr::CfgCopy()
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        return _cfg;
    }

    void Mgr::SetDebug(bool on)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        _cfg.debug = on;
        _debugOn = on;
    }

    PlayerSlot* Mgr::Slot(uint64_t guid)
    {
        auto it = _slots.find(guid);
        return it == _slots.end() ? nullptr : &it->second;
    }

    PlayerSlot* Mgr::SlotFor(Player* player, bool create)
    {
        if (!player)
            return nullptr;
        uint64_t const guid = player->GetGUID().GetRawValue();
        auto it = _slots.find(guid);
        if (it != _slots.end())
            return &it->second;
        if (!create)
            return nullptr;
        PlayerSlot& s = _slots[guid];
        s.ep.SetLimits(_cfg.limits);
        s.lowGuid = player->GetGUID().GetCounter();
        s.name = player->GetName();
        s.classId = player->getClass();
        return &s;
    }

    void Mgr::OnLogin(Player* player)
    {
        if (!player)
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        uint64_t const guid = player->GetGUID().GetRawValue();
        // A slot created earlier in this login by another system's push keeps what it remembered;
        // anything older belongs to a previous session.
        auto it = _slots.find(guid);
        if (it != _slots.end() && it->second.ep.Ready())
            _slots.erase(it);
        SlotFor(player, true);
    }

    void Mgr::OnLogout(Player* player)
    {
        if (!player)
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        uint64_t const guid = player->GetGUID().GetRawValue();
        _slots.erase(guid);
        _dirty.erase(guid);
    }

    // =============================================================================================
    // Receiving
    // =============================================================================================
    bool Mgr::OnSelfWhisper(Player* player, std::string const& text)
    {
        Intent intent;
        Proto::ReceiveResult res;
        std::string who;
        {
            std::lock_guard<std::recursive_mutex> guard(_lock);
            PlayerSlot* s = SlotFor(player, true);
            res = s->ep.Receive(text, NowMs(), intent);
            who = s->name;
        }
        if (res.verdict == Proto::Verdict::NotOurs)
            return true;
        if (res.muteStarted)
            LOG_WARN("module", "[Bleakhold] {} ({}) sent too many invalid or excess addon messages; ignoring their Bleakhold messages for {} s",
                who, player->GetGUID().ToString(), _cfg.limits.floodMuteMs / 1000);

        switch (res.verdict)
        {
            case Proto::Verdict::Dropped:
                if (Debug() && res.reason != DropReason::Muted)
                    DebugLog("dropped a message from " + who + ": " + DropReasonName(res.reason));
                break;
            case Proto::Verdict::Refused:
                DebugLog("refused " + std::string(IntentOpName(intent.type)) + " from " + who + ": rate limit");
                // RDEPLOY is never answered (section 17): a deploy key pressed again too soon is only dropped
                if (intent.type != IntentType::RoyaleDeploy)
                    Refuse(player, intent, "busy", TextBusy);
                break;
            case Proto::Verdict::Accepted:
                if (Debug())
                    DebugLog(who + " > " + EncodeIntentBody(intent));
                Dispatch(player, intent);
                break;
            default:
                break;
        }
        if (OnWorldThread())
            FlushAll();
        // the message never reaches anyone: it was for the server
        return false;
    }

    void Mgr::SetHandler(IntentType type, Ui::IntentHandler h)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        if (type < IntentType::Count)
            _handlers[static_cast<std::size_t>(type)] = std::move(h);
    }

    void Mgr::SetDefaultHandler(IntentType type, Ui::IntentHandler h)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        if (type < IntentType::Count)
            _defaultHandlers[static_cast<std::size_t>(type)] = std::move(h);
    }

    void Mgr::SetProvider(Topic topic, Ui::TopicProvider p)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        if (topic < Topic::Count)
            _providers[static_cast<std::size_t>(topic)] = std::move(p);
    }

    void Mgr::SetDefaultProvider(Topic topic, Ui::TopicProvider p)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        if (topic < Topic::Count)
            _defaultProviders[static_cast<std::size_t>(topic)] = std::move(p);
    }

    void Mgr::SetBoardHandler(Board board, Ui::IntentHandler h)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        _boardHandlers[static_cast<char>(board)] = std::move(h);
    }

    void Mgr::Dispatch(Player* player, Intent const& intent)
    {
        switch (intent.type)
        {
            case IntentType::Hello:
            {
                SendHello(player);
                // the camping state follows HELLO when a camping feature is on (section 16)
                if (_cfg.featureBits & (FeatureCamp | FeatureGlide | FeatureFieldRepair))
                    Refresh(player, Topic::CampState);
                // ARENA follows HELLO while the arena system runs (section 20; the login push came before HELLO)
                if (FeatureOn(FeatureArena))
                    Refresh(player, Topic::Arena);
                std::function<void(Player*, Intent const&)> observer;
                {
                    std::lock_guard<std::recursive_mutex> guard(_lock);
                    observer = _helloObserver;
                }
                if (observer)
                    observer(player, intent);
                return;
            }
            case IntentType::Ping:
            {
                Pong p;
                p.nonce = intent.nonce;
                p.serverEpoch = static_cast<uint32_t>(GameTime::GetGameTime().count());
                PushTo(player->GetGUID().GetRawValue(), "PONG", EncodePong(p));
                return;
            }
            case IntentType::Get:
            {
                for (TopicRequest const& req : intent.topics)
                {
                    Ui::TopicProvider provider;
                    {
                        std::lock_guard<std::recursive_mutex> guard(_lock);
                        std::size_t const i = static_cast<std::size_t>(req.topic);
                        provider = _providers[i] ? _providers[i] : _defaultProviders[i];
                    }
                    if (provider)
                        provider(player, req);
                }
                return;
            }
            default:
                break;
        }

        // KSTART and KCANCEL come from the group leader only (section 1).
        if (intent.type == IntentType::KeyStart || intent.type == IntentType::KeyCancel)
        {
            if (Group* group = player->GetGroup())
            {
                if (!group->IsLeader(player->GetGUID()))
                {
                    Refuse(player, intent, "not_leader", TextNotLeader);
                    return;
                }
            }
        }

        // BleakholdUi.Emoji.Enable holds for a custom EMOJI handler too (section 13).
        if (intent.type == IntentType::Emoji && !_cfg.emojiEnable)
        {
            Refuse(player, intent, "unavailable", TextEmojiOff);
            return;
        }

        // BleakholdUi.Dance.Enable holds for a custom DANCE handler too (section 14).
        if (intent.type == IntentType::Dance && !_cfg.danceEnable)
        {
            Refuse(player, intent, "unavailable", TextDanceOff);
            return;
        }

        // BleakholdUi.Case.Enable holds for a custom CASEOPEN handler too (section 15).
        if (intent.type == IntentType::CaseOpen && !_cfg.caseEnable)
        {
            Refuse(player, intent, "unavailable", TextCaseOff);
            return;
        }

        // BleakholdUi.Camp.Enable, Glide.Enable and Repair.Enable hold for custom handlers too (section 16). REPAIR is also
        // camping's (a camp anvil), so it is off only when both are.
        if (intent.type == IntentType::Camp && !_cfg.campEnable)
        {
            Refuse(player, intent, "camp_off", TextCampOff);
            return;
        }
        if (intent.type == IntentType::Glide && !_cfg.glideEnable)
        {
            Refuse(player, intent, "glide_off", TextGlideOff);
            return;
        }
        if (intent.type == IntentType::Repair && !_cfg.repairEnable && !_cfg.campEnable)
        {
            Refuse(player, intent, "repair_off", TextRepairOff);
            return;
        }

        // Bleakhold Royale (section 17) is open only while its system has turned feature bit 4096 on (Ui::SetFeature):
        // QJOIN B, RDROP and RSPEC get ERR royale_off, RDEPLOY is dropped, whoever handles them.
        bool const royale = (intent.type == IntentType::QueueJoin && intent.queueKind == QueueKind::Royale) ||
            intent.type == IntentType::RoyaleDrop || intent.type == IntentType::RoyaleDeploy ||
            intent.type == IntentType::RoyaleSpectate;
        if (royale && !FeatureOn(FeatureRoyale))
        {
            if (intent.type != IntentType::RoyaleDeploy)
                Refuse(player, intent, RoyaleErr::Off.code, RoyaleErr::Off.text);
            return;
        }

        // The 1v1 arena queue (section 20) is open only while its system has turned feature bit 65536 on.
        if (intent.type == IntentType::QueueJoin && intent.queueKind == QueueKind::Arena && !FeatureOn(FeatureArena))
        {
            Refuse(player, intent, ArenaErr::Off.code, ArenaErr::Off.text);
            return;
        }

        Ui::IntentHandler handler;
        {
            std::lock_guard<std::recursive_mutex> guard(_lock);
            std::size_t const i = static_cast<std::size_t>(intent.type);
            handler = _handlers[i] ? _handlers[i] : _defaultHandlers[i];
            // a board's own LBQ handler (Ui::OnBoardQuery) comes first
            if (intent.type == IntentType::LeaderboardQuery)
            {
                auto it = _boardHandlers.find(static_cast<char>(intent.board));
                if (it != _boardHandlers.end() && it->second)
                    handler = it->second;
            }
        }
        if (handler)
            handler(player, intent);
        else if (intent.type != IntentType::RoyaleDeploy)   // RDEPLOY is never answered (section 17)
            Refuse(player, intent, "unavailable", TextUnavailable);
    }

    void Mgr::SendHello(Player* player)
    {
        // Data first: never hold the Mgr lock while taking the Data lock.
        uint32_t const season = Data::Instance().CurrentSeason();
        std::pair<uint32_t, uint32_t> const resets = Data::Instance().ResetTimes();
        bool const cases = _cfg.caseEnable && Data::Instance().HasCases();

        HelloReply h;
        h.proto = Proto::ProtocolVersion;
        h.minProto = _cfg.minProto;
        h.serverEpoch = static_cast<uint32_t>(GameTime::GetGameTime().count());
        h.utcOffsetMin = _cfg.utcOffsetAuto ? LocalUtcOffsetMinutes() : _cfg.utcOffsetMin;
        h.dataVer = DataVersion();
        h.featureBits = _cfg.featureBits | (cases ? static_cast<uint32_t>(FeatureCases) : 0u) | _runtimeFeatures.load();
        if (season)
            h.seasonId = season;
        if (resets.first)
            h.dailyResetEpoch = resets.first;
        if (resets.second)
            h.weeklyResetEpoch = resets.second;
        h.realmName = _cfg.realmName.empty() ? realm.Name : _cfg.realmName;
        h.siteUrl = _cfg.siteUrl;
        PushTo(player->GetGUID().GetRawValue(), "HELLO", EncodeHello(h));
    }

    void Mgr::SetFeature(uint32_t feature, bool on)
    {
        uint32_t const before = on ? _runtimeFeatures.fetch_or(feature) : _runtimeFeatures.fetch_and(~feature);
        uint32_t const after = on ? (before | feature) : (before & ~feature);
        if (before == after)
            return;
        // clients learn feature bits from HELLO: tell the ones already connected (world thread)
        After(0, [this]() { ForEachReadyPlayer([this](Player* p) { SendHello(p); }); });
    }

    bool Mgr::FeatureOn(uint32_t feature)
    {
        if (_runtimeFeatures.load() & feature)
            return true;
        uint32_t bits = 0;
        bool caseEnable = false;
        {
            std::lock_guard<std::recursive_mutex> guard(_lock);
            bits = _cfg.featureBits;
            caseEnable = _cfg.caseEnable;
        }
        if (bits & feature)
            return true;
        // as SendHello: the case bit also needs a case (never take the Data lock under the Mgr lock)
        return (feature & FeatureCases) && caseEnable && Data::Instance().HasCases();
    }

    void Mgr::Refresh(Player* player, Topic topic)
    {
        if (!player || topic >= Topic::Count || topic == Topic::Set || topic == Topic::Case)
            return;
        if (!OnWorldThread())
        {
            // providers run on the world thread: do it on the next tick
            uint64_t const guid = player->GetGUID().GetRawValue();
            After(0, [this, guid, topic]() {
                if (Player* p = ObjectAccessor::FindConnectedPlayer(ObjectGuid(guid)))
                    Refresh(p, topic);
            });
            return;
        }
        if (!HasAddon(player))
            return;
        Ui::TopicProvider provider;
        {
            std::lock_guard<std::recursive_mutex> guard(_lock);
            std::size_t const i = static_cast<std::size_t>(topic);
            provider = _providers[i] ? _providers[i] : _defaultProviders[i];
        }
        TopicRequest req;
        req.topic = topic;
        if (provider)
            provider(player, req);
    }

    void Mgr::Refuse(Player* player, Intent const& intent, std::string_view code, std::string_view text)
    {
        if (!player)
            return;
        ErrorReply e;
        e.op = intent.type;
        e.seq = intent.seq;
        e.code = std::string(code);
        e.text = std::string(text);
        PushTo(player->GetGUID().GetRawValue(), "ERR", EncodeError(e));
    }

    // =============================================================================================
    // Sending
    // =============================================================================================
    void Mgr::QueueFrames(uint64_t guid, PlayerSlot& slot, char const* op, std::string const& payload)
    {
        std::vector<std::string> frames = slot.ep.Frame(op, payload, _cfg.maxFrameBody);
        if (frames.empty())
        {
            LOG_ERROR("module", "[Bleakhold] {} message for {} is too large to send ({} bytes); dropped", op, slot.name, payload.size());
            return;
        }
        for (std::string& f : frames)
        {
            OutItem item;
            item.kind = OutItem::Kind::Addon;
            item.text = std::move(f);
            slot.outbox.push_back(std::move(item));
        }
        _dirty.insert(guid);
    }

    void Mgr::Push(Player* player, char const* op, Topic topic, std::function<void(PlayerSlot&)> const& update,
        std::function<std::string(uint32_t rev)> const& encode)
    {
        if (!player || !Enabled())
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        PlayerSlot* s = SlotFor(player, true);
        if (update)
            update(*s);
        if (!s->ep.Ready())
            return;
        bool const revisioned = topic < Topic::Count && IsRevisioned(topic);
        uint32_t const rev = revisioned ? s->ep.NextRev(topic) : 0;
        QueueFrames(player->GetGUID().GetRawValue(), *s, op, encode(rev));
        if (revisioned)
            s->ep.MarkSnapshot(topic);
    }

    void Mgr::PushTo(uint64_t guid, char const* op, std::string const& payload)
    {
        if (!Enabled())
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        PlayerSlot* s = Slot(guid);
        if (!s || !s->ep.Ready())
            return;
        QueueFrames(guid, *s, op, payload);
    }

    bool Mgr::ResendCached(Player* player, Topic topic)
    {
        if (!player || !Enabled())
            return false;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        PlayerSlot* s = SlotFor(player, false);
        if (!s || !s->ep.Ready())
            return false;
        uint64_t const guid = player->GetGUID().GetRawValue();
        auto snap = [&](char const* op, auto encode) {
            uint32_t const rev = s->ep.NextRev(topic);
            QueueFrames(guid, *s, op, encode(rev));
            s->ep.MarkSnapshot(topic);
            return true;
        };
        switch (topic)
        {
            case Topic::Week: return s->week && snap("WEEK", [&](uint32_t r) { return EncodeWeek(r, *s->week); });
            case Topic::Era: return s->era && snap("ERA", [&](uint32_t r) { return EncodeEra(r, *s->era); });
            case Topic::Tasks: return s->tasks && snap("TASKS", [&](uint32_t r) { return EncodeTasks(r, *s->tasks); });
            case Topic::Key: return s->key && snap("KEY", [&](uint32_t r) { return EncodeKey(r, *s->key); });
            case Topic::Board: return s->board && snap("BOARD", [&](uint32_t r) { return EncodeBoard(r, *s->board); });
            case Topic::Queue: return s->queue && snap("QUEUE", [&](uint32_t r) { return EncodeQueue(r, *s->queue); });
            case Topic::Coll: return s->coll && snap("COLL", [&](uint32_t r) { return EncodeCollections(r, *s->coll); });
            case Topic::Lidx: return s->lidx && snap("LIDX", [&](uint32_t r) { return EncodeLegacyIndex(r, *s->lidx); });
            case Topic::Season: return s->season && snap("SEASON", [&](uint32_t r) { return EncodeSeason(r, *s->season); });
            case Topic::Rift:
                if (!s->rift)
                    return false;
                QueueFrames(guid, *s, "RIFT", EncodeRift(*s->rift));
                return true;
            default:
                return false;
        }
    }

    Opt<bool> Mgr::WeeklyBonusDone(Player* player)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        PlayerSlot* s = SlotFor(player, false);
        return s ? s->weeklyBonusDone : std::nullopt;
    }

    void Mgr::ClearCaches(Topic topic)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        for (auto& [guid, slot] : _slots)
        {
            if (topic == Topic::Lidx)
                slot.lidx.reset();
        }
    }

    void Mgr::TaskDelta(Player* player, uint32_t uid, uint32_t have, TaskState state)
    {
        if (!player || !Enabled())
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        PlayerSlot* s = SlotFor(player, true);
        if (s->tasks)
            for (Task& t : s->tasks->tasks)
                if (t.uid == uid)
                {
                    t.have = have;
                    t.state = state;
                }
        if (!s->ep.Ready())
            return;
        uint64_t const guid = player->GetGUID().GetRawValue();
        if (s->ep.HasSnapshot(Topic::Tasks))
            QueueFrames(guid, *s, "TASK", EncodeTaskDelta(s->ep.NextRev(Topic::Tasks), uid, have, state));
        else if (s->tasks)
        {
            QueueFrames(guid, *s, "TASKS", EncodeTasks(s->ep.NextRev(Topic::Tasks), *s->tasks));
            s->ep.MarkSnapshot(Topic::Tasks);
        }
    }

    void Mgr::LegacyDelta(Player* player, uint32_t itemId, bool collected)
    {
        if (!player || !Enabled())
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        PlayerSlot* s = SlotFor(player, true);
        if (s->lidx)
        {
            bool found = false;
            for (LegacyIndexEntry& e : s->lidx->items)
                if (e.itemId == itemId)
                {
                    e.collected = collected;
                    found = true;
                }
            if (!found)
            {
                LegacyIndexEntry e;
                e.itemId = itemId;
                e.collected = collected;
                s->lidx->items.push_back(e);
            }
        }
        if (!s->ep.Ready())
            return;
        uint64_t const guid = player->GetGUID().GetRawValue();
        if (s->ep.HasSnapshot(Topic::Lidx))
            QueueFrames(guid, *s, "LCOL", EncodeLegacyCollected(s->ep.NextRev(Topic::Lidx), itemId, collected));
        else if (s->lidx)
        {
            QueueFrames(guid, *s, "LIDX", EncodeLegacyIndex(s->ep.NextRev(Topic::Lidx), *s->lidx));
            s->ep.MarkSnapshot(Topic::Lidx);
        }
    }

    void Mgr::SetWeeklyBonusDone(Player* player, bool done)
    {
        if (!player)
            return;
        {
            std::lock_guard<std::recursive_mutex> guard(_lock);
            PlayerSlot* s = SlotFor(player, true);
            s->weeklyBonusDone = done;
            if (s->era)
                s->era->weeklyBonusDone = done;
        }
        Refresh(player, Topic::Era);
    }

    bool Mgr::HasAddon(Player* player)
    {
        if (!player)
            return false;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        PlayerSlot* s = SlotFor(player, false);
        return s && s->ep.Ready();
    }

    void Mgr::QueueSystem(Player* player, std::string text)
    {
        if (!player)
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        PlayerSlot* s = SlotFor(player, true);
        OutItem item;
        item.kind = OutItem::Kind::System;
        item.text = std::move(text);
        s->outbox.push_back(std::move(item));
        _dirty.insert(player->GetGUID().GetRawValue());
    }

    void Mgr::Announce(Ui::AnnounceTag tag, std::string_view text, uint64_t onlyGuid)
    {
        if (!Enabled())
            return;
        uint8_t const t = static_cast<uint8_t>(tag);
        if (t >= TagCount)
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        if (onlyGuid)
        {
            PlayerSlot* s = Slot(onlyGuid);
            if (!s)
                return;
            bool const plain = s->ep.Ready() || !_cfg.colorTagsWithoutAddon;
            OutItem item;
            item.kind = OutItem::Kind::System;
            item.text = plain ? "[" + std::string(TagNames[t]) + "] " + OneLine(text)
                              : "|cff" + _cfg.tagColors[t] + "[" + TagNames[t] + "]|r " + OneLine(text);
            s->outbox.push_back(std::move(item));
            _dirty.insert(onlyGuid);
            return;
        }
        _announces.emplace_back(t, OneLine(text));
    }

    void Mgr::SendDefinitions(Player* player)
    {
        if (!player)
            return;
        std::shared_ptr<std::vector<std::string> const> payloads = Data::Instance().DefinitionPayloads();
        if (!payloads)
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        PlayerSlot* s = SlotFor(player, false);
        if (!s || !s->ep.Ready())
            return;
        for (std::string const& p : *payloads)
            QueueFrames(player->GetGUID().GetRawValue(), *s, "DEF", p);
    }

    void Mgr::BroadcastDefinitions()
    {
        std::shared_ptr<std::vector<std::string> const> payloads = Data::Instance().DefinitionPayloads();
        if (!payloads)
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        for (auto& [guid, slot] : _slots)
        {
            if (!slot.ep.Ready())
                continue;
            slot.lidx.reset();   // rebuilt from the new tables on the next GET LIDX
            for (std::string const& p : *payloads)
                QueueFrames(guid, slot, "DEF", p);
        }
    }

    void Mgr::ForEachReadyPlayer(std::function<void(Player*)> const& fn)
    {
        std::vector<uint64_t> guids;
        {
            std::lock_guard<std::recursive_mutex> guard(_lock);
            for (auto const& [guid, slot] : _slots)
                if (slot.ep.Ready())
                    guids.push_back(guid);
        }
        for (uint64_t g : guids)
            if (Player* p = ObjectAccessor::FindConnectedPlayer(ObjectGuid(g)))
                fn(p);
    }

    void Mgr::FlushAll()
    {
        std::vector<std::pair<uint64_t, std::vector<OutItem>>> work;
        std::vector<std::pair<uint8_t, std::string>> announces;
        std::unordered_set<uint64_t> ready;
        {
            std::lock_guard<std::recursive_mutex> guard(_lock);
            for (uint64_t g : _dirty)
            {
                PlayerSlot* s = Slot(g);
                if (s && !s->outbox.empty())
                {
                    work.emplace_back(g, std::move(s->outbox));
                    s->outbox.clear();
                }
            }
            _dirty.clear();
            announces.swap(_announces);
            if (!announces.empty())
                for (auto const& [guid, slot] : _slots)
                    if (slot.ep.Ready())
                        ready.insert(guid);
        }

        for (auto& [g, items] : work)
        {
            Player* p = ObjectAccessor::FindConnectedPlayer(ObjectGuid(g));
            if (!p || !p->GetSession())
                continue;
            for (OutItem const& item : items)
            {
                switch (item.kind)
                {
                    case OutItem::Kind::Addon:
                    {
                        // SMSG_MESSAGECHAT, CHAT_MSG_WHISPER, LANG_ADDON, sender = receiver = the player.
                        // The GUID overload keeps it a plain player whisper (no GM chat tag or packet).
                        WorldPacket data;
                        ChatHandler::BuildChatPacket(data, CHAT_MSG_WHISPER, LANG_ADDON, p->GetGUID(), p->GetGUID(), item.text, 0);
                        p->SendDirectMessage(&data);
                        break;
                    }
                    case OutItem::Kind::PullTimer:
                    {
                        ChatMsg const type = ChatMsg(item.chatType);
                        WorldPacket data;
                        ChatHandler::BuildChatPacket(data, type, LANG_ADDON, ObjectGuid(item.sender),
                            type == CHAT_MSG_WHISPER ? p->GetGUID() : ObjectGuid::Empty, item.text, 0);
                        p->SendDirectMessage(&data);
                        break;
                    }
                    case OutItem::Kind::System:
                        ChatHandler(p->GetSession()).SendSysMessage(item.text);
                        break;
                }
            }
        }

        if (!announces.empty())
        {
            for (auto const& [id, session] : sWorldSessionMgr->GetAllSessions())
            {
                Player* p = session ? session->GetPlayer() : nullptr;
                if (!p || !p->IsInWorld())
                    continue;
                bool const plain = ready.count(p->GetGUID().GetRawValue()) || !_cfg.colorTagsWithoutAddon;
                ChatHandler handler(session);
                for (auto const& [t, text] : announces)
                {
                    if (plain)
                        handler.SendSysMessage("[" + std::string(TagNames[t]) + "] " + text);
                    else
                        handler.SendSysMessage("|cff" + _cfg.tagColors[t] + "[" + TagNames[t] + "]|r " + text);
                }
            }
        }
    }

    void Mgr::After(uint32_t ms, std::function<void()> fn)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        _timers.emplace_back(NowMs() + ms, std::move(fn));
    }

    void Mgr::Update(uint32_t /*diff*/)
    {
        MarkWorldThread();
        uint64_t const now = NowMs();

        std::vector<std::function<void()>> due;
        {
            std::lock_guard<std::recursive_mutex> guard(_lock);
            for (auto it = _timers.begin(); it != _timers.end();)
            {
                if (it->first <= now)
                {
                    due.push_back(std::move(it->second));
                    it = _timers.erase(it);
                }
                else
                    ++it;
            }

            for (auto it = _runs.begin(); it != _runs.end();)
            {
                KeyRun& run = it->second;
                if (now - run.createdMs > RunMaxAgeMs)
                {
                    it = _runs.erase(it);
                    continue;
                }
                bool const live = run.state.state == KeyRunStateId::Countdown || run.state.state == KeyRunStateId::Running;
                if (live && now - run.lastBeatMs >= _cfg.heartbeatMs)
                    RunBroadcastLocked(run, now);
                ++it;
            }
        }
        for (std::function<void()>& fn : due)
            fn();

        if (now - _lastSweepMs >= SweepIntervalMs)
        {
            _lastSweepMs = now;
            std::vector<uint64_t> guids;
            {
                std::lock_guard<std::recursive_mutex> guard(_lock);
                for (auto const& [guid, slot] : _slots)
                    guids.push_back(guid);
            }
            for (uint64_t g : guids)
            {
                if (!ObjectAccessor::FindConnectedPlayer(ObjectGuid(g)))
                {
                    std::lock_guard<std::recursive_mutex> guard(_lock);
                    _slots.erase(g);
                    _dirty.erase(g);
                }
            }
        }

        Data::Instance().Update(now);
        Camp::Instance().Update(now);
        FlushAll();
    }

    Mgr::Status Mgr::GetStatus()
    {
        Status st;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        st.online = static_cast<uint32_t>(_slots.size());
        st.runs = static_cast<uint32_t>(_runs.size());
        for (auto const& [guid, slot] : _slots)
        {
            Proto::EndpointStats const& e = slot.ep.Stats();
            if (slot.ep.Ready())
                ++st.ready;
            st.received += e.received;
            st.accepted += e.accepted;
            st.refused += e.refused;
            st.framesOut += e.framesOut;
            st.mutes += e.mutes;
            for (std::size_t i = 0; i < e.dropped.size(); ++i)
            {
                st.drops[i] += e.dropped[i];
                st.dropped += e.dropped[i];
            }
        }
        return st;
    }

    Opt<Proto::EndpointStats> Mgr::StatsOf(Player* player)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        PlayerSlot* s = SlotFor(player, false);
        if (!s)
            return std::nullopt;
        return s->ep.Stats();
    }

    // =============================================================================================
    // Keystone run tracker
    // =============================================================================================
    KeyRunState Mgr::RunSnapshot(KeyRun& run, uint64_t nowMs)
    {
        KeyRunState st = run.state;
        if (st.state == KeyRunStateId::Running)
        {
            uint64_t const e = static_cast<uint64_t>(run.elapsedBaseMs) + (nowMs - run.timerStartMs);
            st.elapsedMs = static_cast<uint32_t>(std::min<uint64_t>(e, 864000000ull));
        }
        return st;
    }

    void Mgr::RunBroadcastLocked(KeyRun& run, uint64_t nowMs)
    {
        std::string const payload = EncodeKeyRunState(RunSnapshot(run, nowMs));
        for (uint64_t g : run.members)
        {
            PlayerSlot* s = Slot(g);
            if (s && s->ep.Ready())
                QueueFrames(g, *s, "MP", payload);
        }
        run.lastBeatMs = nowMs;
    }

    void Mgr::RunQueueStartLocked(KeyRun& run, uint64_t guid, uint64_t nowMs)
    {
        PlayerSlot* s = Slot(guid);
        if (!s || !s->ep.Ready())
            return;
        KeyRunStart start;
        start.runId = run.info.runId;
        start.dungeonId = run.info.dungeonId;
        start.level = run.info.level;
        start.affixIds = run.info.affixIds;
        start.eraId = run.info.eraId;
        // a late joiner or a /reload sees what is left of the countdown (0 once the timer runs)
        uint32_t left = 0;
        if (run.state.state == KeyRunStateId::Countdown)
        {
            uint64_t const since = nowMs - run.createdMs;
            left = since < run.info.countdownMs ? static_cast<uint32_t>(run.info.countdownMs - since) : 0;
        }
        start.countdownMs = left;
        start.timeLimitSec = run.info.timeLimitSec;
        QueueFrames(guid, *s, "MPS", EncodeKeyRunStart(start));
        QueueFrames(guid, *s, "MP", EncodeKeyRunState(RunSnapshot(run, nowMs)));
    }

    void Mgr::RunPullTimerLocked(KeyRun& run, uint32_t seconds)
    {
        if (!_cfg.serverPullTimer)
            return;
        for (uint64_t g : run.members)
        {
            PlayerSlot* s = Slot(g);
            if (!s)
                continue;
            OutItem item;
            item.kind = OutItem::Kind::PullTimer;
            item.text = "DBMv4-PT\t" + std::to_string(seconds);
            item.chatType = run.pullChatType;
            item.sender = run.pullChatType == CHAT_MSG_WHISPER ? g : run.leader;
            s->outbox.push_back(std::move(item));
            _dirty.insert(g);
        }
    }

    uint32_t Mgr::RunStart(Ui::KeyRunInfo const& info, std::vector<Player*> const& members, Player* leader)
    {
        if (!Enabled() || members.empty())
            return 0;
        Player* lead = leader ? leader : members.front();
        uint8_t chatType = CHAT_MSG_WHISPER;
        if (Group* g = lead ? lead->GetGroup() : nullptr)
            chatType = g->isRaidGroup() ? CHAT_MSG_RAID : CHAT_MSG_PARTY;

        std::lock_guard<std::recursive_mutex> guard(_lock);
        uint64_t const now = NowMs();
        uint32_t runId = info.runId;
        if (!runId)
        {
            while (_runs.count(_nextRunId) || _nextRunId == 0)
                ++_nextRunId;
            runId = _nextRunId++;
        }
        KeyRun& run = _runs[runId];
        run = KeyRun();
        run.info = info;
        run.info.runId = runId;
        run.state.runId = runId;
        run.state.timeLimitSec = info.timeLimitSec;
        run.state.forcesMax = info.forcesMax;
        run.state.chestSec = info.chestSec;
        run.state.state = KeyRunStateId::Countdown;
        run.leader = lead ? lead->GetGUID().GetRawValue() : 0;
        run.pullChatType = chatType;
        run.createdMs = now;
        run.lastBeatMs = now;
        for (Player* m : members)
        {
            if (!m)
                continue;
            SlotFor(m, true);
            uint64_t const g = m->GetGUID().GetRawValue();
            if (std::find(run.members.begin(), run.members.end(), g) == run.members.end())
                run.members.push_back(g);
        }
        for (uint64_t g : run.members)
            RunQueueStartLocked(run, g, now);
        uint32_t const secs = (info.countdownMs + 500) / 1000;
        if (secs >= 3)
            RunPullTimerLocked(run, secs);
        return runId;
    }

    void Mgr::RunTimerStart(uint32_t runId)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        auto it = _runs.find(runId);
        if (it == _runs.end())
            return;
        uint64_t const now = NowMs();
        KeyRun& run = it->second;
        run.state.state = KeyRunStateId::Running;
        run.timerStartMs = now;
        run.elapsedBaseMs = 0;
        RunBroadcastLocked(run, now);
    }

    void Mgr::RunBoss(uint32_t runId, uint32_t bossIndex)
    {
        if (bossIndex < 1 || bossIndex > 31)
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        auto it = _runs.find(runId);
        if (it == _runs.end())
            return;
        uint64_t const now = NowMs();
        KeyRun& run = it->second;
        KeyRunState const snap = RunSnapshot(run, now);
        run.state.bossBits |= 1u << (bossIndex - 1);
        if (run.state.bossKillSec.size() < bossIndex)
            run.state.bossKillSec.resize(bossIndex, 0);
        run.state.bossKillSec[bossIndex - 1] = snap.elapsedMs / 1000;
        RunBroadcastLocked(run, now);
    }

    void Mgr::RunForces(uint32_t runId, uint32_t cur, Opt<uint32_t> max)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        auto it = _runs.find(runId);
        if (it == _runs.end())
            return;
        it->second.state.forcesCur = cur;
        if (max)
            it->second.state.forcesMax = *max;
        RunBroadcastLocked(it->second, NowMs());
    }

    void Mgr::RunDeath(uint32_t runId, uint32_t penaltySec)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        auto it = _runs.find(runId);
        if (it == _runs.end())
            return;
        ++it->second.state.deaths;
        it->second.state.deathPenaltySec += penaltySec;
        RunBroadcastLocked(it->second, NowMs());
    }

    void Mgr::RunCompleted(uint32_t runId, KeyRunEnd const& result)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        auto it = _runs.find(runId);
        if (it == _runs.end())
            return;
        uint64_t const now = NowMs();
        KeyRun& run = it->second;
        KeyRunState st = RunSnapshot(run, now);
        st.state = result.result == KeyRunResultId::InTime ? KeyRunStateId::FinishedInTime
            : result.result == KeyRunResultId::Abandoned ? KeyRunStateId::Abandoned : KeyRunStateId::FinishedOverTime;
        if (result.timeMs)
            st.elapsedMs = *result.timeMs;
        run.state = st;
        RunBroadcastLocked(run, now);
        KeyRunEnd end = result;
        end.runId = runId;
        std::string const payload = EncodeKeyRunEnd(end);
        for (uint64_t g : run.members)
        {
            PlayerSlot* s = Slot(g);
            if (s && s->ep.Ready())
                QueueFrames(g, *s, "MPE", payload);
        }
        _runs.erase(it);
    }

    void Mgr::RunAbandoned(uint32_t runId)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        auto it = _runs.find(runId);
        if (it == _runs.end())
            return;
        uint64_t const now = NowMs();
        KeyRun& run = it->second;
        bool const wasCountdown = run.state.state == KeyRunStateId::Countdown;
        KeyRunState st = RunSnapshot(run, now);
        st.state = KeyRunStateId::Abandoned;
        run.state = st;
        RunBroadcastLocked(run, now);
        if (wasCountdown)
            RunPullTimerLocked(run, 0);
        _runs.erase(it);
    }

    void Mgr::RunAddMember(uint32_t runId, Player* player)
    {
        if (!player)
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        auto it = _runs.find(runId);
        if (it == _runs.end())
            return;
        SlotFor(player, true);
        uint64_t const g = player->GetGUID().GetRawValue();
        KeyRun& run = it->second;
        if (std::find(run.members.begin(), run.members.end(), g) == run.members.end())
            run.members.push_back(g);
        RunQueueStartLocked(run, g, NowMs());
    }

    void Mgr::RunRemoveMember(uint32_t runId, Player* player)
    {
        if (!player)
            return;
        std::lock_guard<std::recursive_mutex> guard(_lock);
        auto it = _runs.find(runId);
        if (it == _runs.end())
            return;
        uint64_t const g = player->GetGUID().GetRawValue();
        auto& m = it->second.members;
        m.erase(std::remove(m.begin(), m.end(), g), m.end());
    }

    void Mgr::RunSync(uint32_t runId, KeyRunState const& st)
    {
        std::lock_guard<std::recursive_mutex> guard(_lock);
        auto it = _runs.find(runId);
        if (it == _runs.end())
            return;
        uint64_t const now = NowMs();
        KeyRun& run = it->second;
        run.state = st;
        run.state.runId = runId;
        if (st.state == KeyRunStateId::Running)
        {
            run.timerStartMs = now;
            run.elapsedBaseMs = st.elapsedMs;
        }
        RunBroadcastLocked(run, now);
    }

    Opt<uint32_t> Mgr::RunOf(Player* player)
    {
        if (!player)
            return std::nullopt;
        uint64_t const g = player->GetGUID().GetRawValue();
        std::lock_guard<std::recursive_mutex> guard(_lock);
        for (auto const& [id, run] : _runs)
            if (std::find(run.members.begin(), run.members.end(), g) != run.members.end())
                return id;
        return std::nullopt;
    }

    bool Mgr::SendRunTo(Player* player)
    {
        if (!player)
            return false;
        uint64_t const g = player->GetGUID().GetRawValue();
        std::lock_guard<std::recursive_mutex> guard(_lock);
        for (auto& [id, run] : _runs)
        {
            if (std::find(run.members.begin(), run.members.end(), g) != run.members.end())
            {
                RunQueueStartLocked(run, g, NowMs());
                return true;
            }
        }
        return false;
    }
}
