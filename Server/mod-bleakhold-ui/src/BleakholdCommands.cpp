/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * GM commands:
 *   .bleakhold status                       protocol counters, data version, loaded rows
 *   .bleakhold reload                       re-read mod_bleakhold_ui.conf and the world tables (admin)
 *   .bleakhold debug on|off                 log every accepted intent and every drop reason (admin)
 *   .bleakhold announce <tag> <text>        tag: legacy, first, season, queue, record (admin)
 *   .bleakhold player                       counters of the selected player (or yourself)
 *   .bleakhold test <what>                  push sample data to the selected player (or yourself):
 *        all week era tasks taskdone key board queue run rift collections season leaderboard firsts toast announce defs
 * The test data is only shown in that player's own UI (and remembered until they log out).
 */

#include "BleakholdData.h"
#include "BleakholdMgr.h"
#include "BleakholdUi.h"

#include "Chat.h"
#include "ChatCommand.h"
#include "Config.h"
#include "GameTime.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "ScriptMgr.h"

using namespace Acore::ChatCommands;

namespace
{
    using namespace Bleakhold;

    Player* Target(ChatHandler* handler)
    {
        Player* p = handler->getSelectedPlayerOrSelf();
        if (!p)
        {
            handler->SendSysMessage("Bleakhold: select a player or run the command in game.");
            return nullptr;
        }
        if (!Ui::HasAddon(p))
        {
            handler->PSendSysMessage("Bleakhold: {} has no Bleakhold UI running (no HELLO received this session).", p->GetName());
            return nullptr;
        }
        return p;
    }

    void TestWeek(Player* p)
    {
        WeekState w;
        w.keysTimed = 4; w.raidEchoes = 1; w.riftBestFloor = 18; w.mythicCoins = 2140; w.mythicCoinsCap = 5500; w.shards = 1260;
        Ui::SendWeek(p, w);
    }

    void TestEra(Player* p)
    {
        EraState e;
        e.eraId = 7; e.nextEraId = 3; e.affixIds = { 1, 3, 4 }; e.weeklyBonusId = 1; e.weeklyBonusDone = false;
        Ui::SendEra(p, e);
    }

    void TestTasks(Player* p)
    {
        TaskList t;
        t.freeRerolls = 1; t.rerollCost = 500000; t.rerollCurrency = Currency::Copper;
        auto task = [](uint32_t uid, TaskKind kind, uint32_t tpl, uint32_t have, uint32_t need, RewardKind rk, uint32_t amount,
                        Opt<uint32_t> item, TaskState st, std::string rewardText = {}) {
            Task x;
            x.uid = uid; x.kind = kind; x.templateId = tpl; x.have = have; x.need = need; x.rewardKind = rk; x.rewardAmount = amount;
            x.rewardItemId = item; x.state = st; x.rewardText = std::move(rewardText);
            return x;
        };
        t.tasks.push_back(task(101, TaskKind::Daily, 1, 0, 1, RewardKind::MythicCoins, 20, std::nullopt, TaskState::Open));
        t.tasks.push_back(task(102, TaskKind::Daily, 2, 14, 20, RewardKind::Item, 1, 40752u, TaskState::Open, "1 Emblem of Heroism"));
        t.tasks.push_back(task(103, TaskKind::Daily, 3, 5, 5, RewardKind::MythicCoins, 20, std::nullopt, TaskState::Claimable));
        t.tasks.push_back(task(201, TaskKind::Weekly, 4, 1, 3, RewardKind::MythicCoins, 150, std::nullopt, TaskState::Open));
        t.tasks.push_back(task(202, TaskKind::Weekly, 5, 1, 2, RewardKind::Text, 0, std::nullopt, TaskState::Open, "Legacy Cache"));
        Ui::SendTasks(p, t);
    }

    void TestKey(Player* p)
    {
        KeyState k;
        k.dungeonId = 602; k.level = 8; k.affixIds = { 1, 3, 4 }; k.mode = 2; k.weeklyBestLevel = 9; k.weeklyBestDungeonId = 599;
        k.cachesReady = 1; k.cachesBanked = 2; k.maxLevel = 15; k.eraId = 7; k.depleted = false;
        Ui::SendKeyState(p, k);
    }

    void TestBoard(Player* p)
    {
        BoardState b;
        b.shards = 1260; b.bountyId = 55; b.bountyDungeonId = 189; b.bountyState = BountyState::Claimable; b.bountyRewardText = "50 Shards";
        b.firstRunBonus = true;
        auto d = [](uint32_t id, uint32_t ch, uint32_t lo, uint32_t hi, uint32_t bits, Opt<uint32_t> best, Opt<uint32_t> bestTier,
                     Opt<uint32_t> record, std::string recName, bool locked) {
            BoardDungeon x;
            x.dungeonId = id; x.chapter = ch; x.lvlMin = lo; x.lvlMax = hi; x.tierBits = bits; x.bestScore = best; x.bestTier = bestTier;
            x.recordScore = record; x.recordName = std::move(recName); x.locked = locked;
            return x;
        };
        b.dungeons.push_back(d(389, 1, 13, 18, 15, 900u, 1u, 2400u, "Aldric", false));
        b.dungeons.push_back(d(36, 1, 15, 21, 3, std::nullopt, std::nullopt, std::nullopt, "", false));
        b.dungeons.push_back(d(189, 2, 30, 40, 1, 1500u, 0u, 3100u, "Brenna", false));
        b.dungeons.push_back(d(602, 5, 77, 80, 1, std::nullopt, std::nullopt, std::nullopt, "", p->GetLevel() < 77));
        Ui::BoardSnapshot(p, b);
    }

    void TestQueue(Player* p)
    {
        QueueState q;
        q.state = QueueStateId::Proposal; q.kind = QueueKind::Dungeon; q.activityId = 389; q.tier = 2; q.size = 3; q.queuedSec = 40;
        q.proposalId = 77; q.timeoutSec = 40; q.bandMin = 13; q.bandMax = 18;
        QueueMember me;
        me.name = p->GetName(); me.classId = p->getClass(); me.role = RoleDamage; me.accepted = ProposalAnswer::Accepted; me.level = p->GetLevel();
        QueueMember other;
        other.name = "Brenna"; other.classId = 2; other.role = RoleHealer; other.accepted = ProposalAnswer::Pending; other.level = 16;
        q.members = { me, other };
        Ui::QueueStatus(p, q);
    }

    void TestRun(Player* p)
    {
        Ui::KeyRunInfo info;
        info.dungeonId = 602; info.level = 8; info.affixIds = { 1, 3, 4 }; info.eraId = 7; info.countdownMs = 10000;
        info.timeLimitSec = 1800; info.forcesMax = 100; info.chestSec = { 1260, 1440 };
        uint32_t const run = Ui::KeyRunStart(info, { p });
        Mgr& m = Mgr::Instance();
        m.After(10000, [run]() { Ui::KeyTimerStart(run); });
        for (uint32_t i = 1; i <= 4; ++i)
        {
            m.After(10000 + i * 4000, [run, i]() {
                Ui::KeyEnemyForces(run, i * 25);
                Ui::KeyBossKilled(run, i);
            });
        }
        m.After(16000, [run]() { Ui::KeyDeath(run, 5); });
        m.After(28000, [run]() {
            KeyRunEnd end;
            end.result = KeyRunResultId::InTime; end.timeMs = 18000; end.keyDelta = 1; end.newDungeonId = 599; end.newLevel = 9; end.score = 1840;
            Reward chest; chest.kind = RewardKind::Text; chest.amount = 1; chest.text = "Spoils chest (test)";
            Reward coins; coins.kind = RewardKind::MythicCoins; coins.amount = 150;
            end.rewards = { chest, coins };
            Ui::KeyCompleted(run, end);
        });
    }

    void TestRift(Player* p)
    {
        RiftState r;
        r.runId = 8001; r.state = RiftStateId::Running; r.floor = 7; r.bossId = 3; r.bossName = "Echo of Nefarian"; r.elapsedMs = 120000;
        r.bestFloor = 18; r.rank = 42; r.deaths = 1; r.groupSize = 1;
        Ui::RiftStatus(p, r);
        uint64_t const guid = p->GetGUID().GetRawValue();
        Mgr::Instance().After(10000, [guid]() {
            Player* pl = ObjectAccessor::FindConnectedPlayer(ObjectGuid(guid));
            if (!pl)
                return;
            RiftState over;
            over.runId = 8001; over.state = RiftStateId::Over; over.floor = 9; over.bestFloor = 18; over.rank = 42; over.groupSize = 1;
            Ui::RiftStatus(pl, over);
            RiftEnd e;
            e.runId = 8001; e.floorReached = 9; e.timeMs = 180000; e.newBest = false;
            Reward coins; coins.kind = RewardKind::MythicCoins; coins.amount = 20;
            e.rewards = { coins };
            Ui::RiftEnded(pl, e);
        });
    }

    void TestCollections(Player* p)
    {
        CollectionState c;
        c.transmogOwned = 412; c.laterAgesOwned = 0; c.laterAgesTotal = 3771; c.legacySetsOwned = 3; c.legacySetsTotal = 48;
        c.tierHave = { 3, 0, 0, 0, 0, 0, 0 }; c.tierTotal = { 8, 8, 5, 9, 5, 5, 8 };
        Ui::SendCollections(p, c);
    }

    void TestSeason(Player* p)
    {
        SeasonState s;
        s.seasonId = 1; s.warEffortPermille = 620; s.contributors = 1284; s.points = 1240; s.rankId = 2; s.nextRankId = 3; s.pointsToNextRank = 260;
        s.warEffortTitle = "Breach the Greymane Wall"; s.warEffortText = "Fill the bar together."; s.spareTokens = 3;
        s.parts = { { "Materials", 800u }, { "Bosses and Echoes", 550u }, { "Keys in time", 510u } };
        SeasonRewardState a; a.rewardId = 1; a.earned = true; a.stateText = "Earned";
        SeasonRewardState b; b.rewardId = 2; b.earned = false; b.stateText = "7 / 20";
        s.rewards = { a, b };
        Ui::SendSeason(p, s);
    }

    void TestLeaderboard(Player* p)
    {
        uint32_t const now = static_cast<uint32_t>(GameTime::GetGameTime().count());
        Leaderboard lb;
        lb.board = Board::Keys; lb.seasonId = 1; lb.dungeonId = 0; lb.classId = 0; lb.page = 1; lb.pages = 1;
        LeaderboardRow r1;
        r1.rank = 1; r1.dungeonId = 602; r1.value = 15; r1.timeSec = 300; r1.dateEpoch = now - 3600;
        r1.members = { { "Aldric", 1u }, { "Brenna", 2u }, { "Corwin", 5u }, { "Dalia", 8u }, { "Eamon", 11u } };
        LeaderboardRow r2;
        r2.rank = 2; r2.dungeonId = 599; r2.value = 14; r2.timeSec = -20; r2.dateEpoch = now - 7200;
        r2.members = { { p->GetName(), static_cast<uint32_t>(p->getClass()) } };
        lb.rows = { r1, r2 };
        Ui::SendLeaderboard(p, lb);
        LeaderboardMe me;
        me.board = Board::Keys; me.rank = 2; me.topPercent = 100; me.value = 14; me.dungeonId = 599; me.timeSec = -20; me.barPermille = 933;
        Ui::SendLeaderboardMe(p, me);
    }

    void TestFirsts(Player* p)
    {
        uint32_t const now = static_cast<uint32_t>(GameTime::GetGameTime().count());
        FirstsList f;
        f.entries = { { "echo", "Echo of Ragnaros defeated (test)", "Ironvow", now - 86400 }, { "key", "First timed +15 (test)", "Dalia's group", now - 5 * 86400 } };
        Ui::SendFirsts(p, f);
    }

    void TestToast(Player* p)
    {
        Ui::Toast(p, ToastKind::Record, "New record (test)", "Halls of Lightning +8 in 24:13", "leaderboards");
    }

    void TestAnnounce(Player* p)
    {
        Ui::AnnounceTo(p, Ui::AnnounceTag::RaidLegacy, p->GetName() + " found [Belt of Might] (test)");
        Ui::AnnounceTo(p, Ui::AnnounceTag::ServerFirst, "Echo of Ragnaros defeated by Ironvow (test)");
        Ui::AnnounceTo(p, Ui::AnnounceTag::Season, "War Effort reached 62% (test)");
        Ui::AnnounceTo(p, Ui::AnnounceTag::Queue, p->GetName() + " is looking for a group: Ragefire Chasm (test)");
        Ui::AnnounceTo(p, Ui::AnnounceTag::Record, "Halls of Lightning +8 timed in 24:13 (test)");
    }
}

class bleakhold_commandscript : public CommandScript
{
public:
    bleakhold_commandscript() : CommandScript("bleakhold_commandscript") { }

    ChatCommandTable GetCommands() const override
    {
        static ChatCommandTable bleakholdTable =
        {
            { "status",   HandleStatus,   SEC_GAMEMASTER,    Console::Yes },
            { "reload",   HandleReload,   SEC_ADMINISTRATOR, Console::Yes },
            { "debug",    HandleDebug,    SEC_ADMINISTRATOR, Console::Yes },
            { "announce", HandleAnnounce, SEC_ADMINISTRATOR, Console::Yes },
            { "player",   HandlePlayer,   SEC_GAMEMASTER,    Console::No },
            { "test",     HandleTest,     SEC_GAMEMASTER,    Console::No },
        };
        static ChatCommandTable commandTable =
        {
            { "bleakhold", bleakholdTable },
        };
        return commandTable;
    }

    static bool HandleStatus(ChatHandler* handler)
    {
        Mgr& m = Mgr::Instance();
        Mgr::Status const st = m.GetStatus();
        Data::Counts const c = Data::Instance().GetCounts();
        handler->PSendSysMessage("Bleakhold: {}, protocol 1, data version {}, season {}, feature bits {}",
            m.Cfg().enable ? "enabled" : "disabled", m.DataVersion(), Ui::CurrentSeason(), m.Cfg().featureBits);
        handler->PSendSysMessage("Players: {} tracked, {} with the UI running; key runs: {}", st.online, st.ready, st.runs);
        handler->PSendSysMessage("Messages: {} received, {} accepted, {} refused (busy), {} dropped, {} frames sent, {} flood mutes",
            st.received, st.accepted, st.refused, st.dropped, st.framesOut, st.mutes);
        std::string drops;
        for (std::size_t i = 1; i < st.drops.size(); ++i)
            if (st.drops[i])
                drops += std::string(drops.empty() ? "" : ", ") + DropReasonName(static_cast<DropReason>(i)) + " " + std::to_string(st.drops[i]);
        if (!drops.empty())
            handler->PSendSysMessage("Drops: {}", drops);
        handler->PSendSysMessage("Tables: {} definitions, {} schedule weeks, {} seasons, {} legacy sets, {} leaderboard rows, {} server firsts, {} war effort contributors",
            c.defs, c.schedule, c.seasons, c.sets, c.lbRows, c.firsts, c.weRows);
        return true;
    }

    static bool HandleReload(ChatHandler* handler)
    {
        uint32_t const before = Mgr::Instance().DataVersion();
        if (!sConfigMgr->Reload())
            handler->SendSysMessage("Bleakhold: could not re-read the configuration files; keeping the current settings.");
        Mgr::Instance().LoadConfig();
        Data::Instance().ReloadWorld();
        uint32_t const after = Mgr::Instance().DataVersion();
        if (after != before)
            Mgr::Instance().BroadcastDefinitions();
        else
            Mgr::Instance().ClearCaches(Topic::Lidx);
        Mgr::Instance().ForEachReadyPlayer([](Player* p) {
            Mgr::Instance().Refresh(p, Topic::Era);
            Mgr::Instance().Refresh(p, Topic::Season);
            Mgr::Instance().Refresh(p, Topic::Cases);   // the case list may have changed (section 15)
        });
        handler->PSendSysMessage("Bleakhold: configuration and world tables reloaded; data version {} -> {}.", before, after);
        return true;
    }

    static bool HandleDebug(ChatHandler* handler, std::string_view state)
    {
        if (state != "on" && state != "off")
        {
            handler->SendSysMessage("Usage: .bleakhold debug on|off");
            return true;
        }
        Mgr::Instance().SetDebug(state == "on");
        handler->PSendSysMessage("Bleakhold: debug logging {} (\"module\" logger).", state);
        return true;
    }

    static bool HandleAnnounce(ChatHandler* handler, std::string_view tag, Tail text)
    {
        Ui::AnnounceTag t;
        if (tag == "legacy")
            t = Ui::AnnounceTag::RaidLegacy;
        else if (tag == "first")
            t = Ui::AnnounceTag::ServerFirst;
        else if (tag == "season")
            t = Ui::AnnounceTag::Season;
        else if (tag == "queue")
            t = Ui::AnnounceTag::Queue;
        else if (tag == "record")
            t = Ui::AnnounceTag::Record;
        else
        {
            handler->SendSysMessage("Usage: .bleakhold announce legacy|first|season|queue|record <text>");
            return true;
        }
        if (text.empty())
        {
            handler->SendSysMessage("Usage: .bleakhold announce legacy|first|season|queue|record <text>");
            return true;
        }
        Ui::Announce(t, text);
        return true;
    }

    static bool HandlePlayer(ChatHandler* handler)
    {
        Player* p = handler->getSelectedPlayerOrSelf();
        if (!p)
            return false;
        Opt<Proto::EndpointStats> st = Mgr::Instance().StatsOf(p);
        if (!st)
        {
            handler->PSendSysMessage("Bleakhold: nothing tracked for {}.", p->GetName());
            return true;
        }
        handler->PSendSysMessage("Bleakhold {}: UI {}, {} received, {} accepted, {} refused, {} messages / {} frames sent, {} mutes",
            p->GetName(), Ui::HasAddon(p) ? "running" : "not running", st->received, st->accepted, st->refused, st->messagesOut,
            st->framesOut, st->mutes);
        std::string drops;
        for (std::size_t i = 1; i < st->dropped.size(); ++i)
            if (st->dropped[i])
                drops += std::string(drops.empty() ? "" : ", ") + DropReasonName(static_cast<DropReason>(i)) + " " + std::to_string(st->dropped[i]);
        if (!drops.empty())
            handler->PSendSysMessage("Drops: {}", drops);
        return true;
    }

    static bool HandleTest(ChatHandler* handler, std::string_view what)
    {
        Player* p = Target(handler);
        if (!p)
            return true;
        bool const all = what == "all";
        bool any = false;
        auto run = [&](std::string_view name, void (*fn)(Player*), bool inAll = true) {
            if (what == name || (all && inAll))
            {
                fn(p);
                any = true;
            }
        };
        run("week", TestWeek);
        run("era", TestEra);
        run("tasks", TestTasks);
        run("key", TestKey);
        run("board", TestBoard);
        run("queue", TestQueue, false);
        run("collections", TestCollections);
        run("season", TestSeason);
        run("leaderboard", TestLeaderboard);
        run("firsts", TestFirsts);
        run("toast", TestToast);
        run("announce", TestAnnounce, false);
        run("run", TestRun, false);
        run("rift", TestRift, false);
        if (what == "taskdone")
        {
            Ui::TaskProgress(p, 102, 20, TaskState::Claimable);
            any = true;
        }
        if (what == "defs")
        {
            Mgr::Instance().SendDefinitions(p);
            any = true;
        }
        if (!any)
        {
            handler->SendSysMessage("Usage: .bleakhold test all|week|era|tasks|taskdone|key|board|queue|run|rift|collections|season|leaderboard|firsts|toast|announce|defs");
            return true;
        }
        handler->PSendSysMessage("Bleakhold: sent test data ({}) to {}.", what, p->GetName());
        return true;
    }
};

void AddBleakholdCommandScripts()
{
    new bleakhold_commandscript();
}
