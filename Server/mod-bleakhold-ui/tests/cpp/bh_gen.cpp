// mod-bleakhold-ui tests: frames for every server message, produced by the module's own encoders and
// Endpoint (handshake, revisions, SEQ, chunking), written as a Lua data file for the addon's parser.
//
//   bh_gen <maxBody> <out.lua>
//
// tests/lua/test_server_frames.lua feeds the frames through Comm.lua/State.lua and checks every
// value below. Keep the two files in step.
//
// SPDX-License-Identifier: GPL-2.0-or-later

#include "BleakholdCodec.h"
#include "BleakholdEndpoint.h"
#include "BleakholdMessages.h"

#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

using namespace Bleakhold;
using namespace Bleakhold::Proto;

namespace
{
    std::size_t g_maxBody = 1000;
    Endpoint g_ep;
    std::vector<std::string> g_frames;

    void Send(char const* op, std::string const& payload)
    {
        std::vector<std::string> f = g_ep.Frame(op, payload, g_maxBody);
        if (f.empty())
        {
            std::fprintf(stderr, "bh_gen: %s could not be framed (%zu bytes)\n", op, payload.size());
            std::exit(1);
        }
        for (std::string& s : f)
        {
            if (s.size() > 4 + MaxServerBody)
            {
                std::fprintf(stderr, "bh_gen: frame over the limit\n");
                std::exit(1);
            }
            g_frames.push_back(std::move(s));
        }
    }

    // the module's Push(): next revision of the topic, then frame
    template <typename F>
    void SendRev(char const* op, Topic topic, F encode)
    {
        uint32_t const rev = g_ep.NextRev(topic);
        Send(op, encode(rev));
        if (std::string(op) != "TASK" && std::string(op) != "LCOL")
            g_ep.MarkSnapshot(topic);
    }

    std::string LuaString(std::string const& s)
    {
        std::string out = "\"";
        for (unsigned char c : s)
        {
            if (c == '\\' || c == '"')
            {
                out += '\\';
                out += static_cast<char>(c);
            }
            else if (c < 0x20 || c >= 0x7F)
            {
                char buf[8];
                std::snprintf(buf, sizeof(buf), "\\%03u", c);
                out += buf;
            }
            else
                out += static_cast<char>(c);
        }
        return out + "\"";
    }

    Definitions Defs()
    {
        Definitions d;
        d.affixes = {
            { 1, "Fortified", "Non-boss enemies have more health and hit harder." },
            { 3, "Bolstering", "When a non-boss enemy dies, its allies nearby grow stronger." },
            { 4, "Volcanic; 100% |cffff0000red|r", "Plumes: of flame~erupt, under %s players." },
            { 9, "Br\xC3\xBBlant", "UTF-8 \xE2\x82\xAC text and a bad byte \xFF here." },
        };
        d.eras = { { 7, "The Black Temple", "Tier 6 tokens drop.", 7u }, { 3, "Ahn'Qiraj", "Tier 2.5 tokens drop.", 3u } };
        d.taskTemplates = { { 1, "Heroic hero", "Clear any heroic dungeon." }, { 2, "Key sweeper", "Defeat 20 enemies, inside a key." } };
        d.weeklyBonuses = { { 1, "First Raid Lord Echo", "Your first Raid Echo kill drops an era token." } };
        d.chapters = { { 5, "Chapter V - Northrend", "The last road north." } };
        for (uint32_t i = 0; i < 25; ++i)
        {
            DungeonDef x;
            x.id = 1000 + i;
            x.name = "Dungeon " + std::to_string(i) + ", the long name";
            x.chapter = 1 + i % 5;
            x.lvlMin = 10 + i;
            x.lvlMax = 15 + i;
            x.bosses = { "Boss: one", "Boss~two", "Boss;three", "Boss %four" };
            x.timeLimitSec = 1800;
            d.dungeons.push_back(x);
        }
        DungeonDef hol;
        hol.id = 602; hol.name = "Halls of Lightning"; hol.chapter = 5; hol.lvlMin = 77; hol.lvlMax = 80;
        hol.bosses = { "General Bjarngrim", "Volkhan", "Ionar", "Loken" }; hol.timeLimitSec = 1800;
        d.dungeons.push_back(hol);
        LegacyTierDef t1;
        t1.id = 1; t1.label = "Tier 1"; t1.raids = "Molten Core, Zul'Gurub"; t1.eraId = 1; t1.sources = { 229, 329, 289, 429, 543 };
        t1.lvlMin = 58; t1.lvlMax = 61; t1.echoBoss = "Ragnaros"; t1.pieceTotal = 8;
        d.legacyTiers = { t1 };
        d.seasons = { { 1, "Season 1 - Bleak Dawn", "Naxxramas, the Bleakhold raid", SeasonStateId::Current },
            { 2, "Season 2", "Gilneas", SeasonStateId::Upcoming } };
        d.ranks = { { 2, "Sergeant of the Wall" } };
        d.seasonRewards = { { 1, "Title", "\"of the Bleak Dawn\" at 500 points" } };
        d.mythicLevels = { { 0, "Where every keystone begins." }, { 15, "The highest keystone level." } };
        d.extraClasses = { { 12, "Gravewarden", "GRAVEWARDEN", "7FBF7F", "GRV" } };
        d.riftBosses = { { 3, "Echo of Nefarian" } };
        return d;
    }
}

int main(int argc, char** argv)
{
    if (argc < 3)
    {
        std::fprintf(stderr, "usage: bh_gen <maxBody> <out.lua>\n");
        return 2;
    }
    g_maxBody = static_cast<std::size_t>(std::stoul(argv[1]));

    // the client's HELLO opens the session (nothing may be pushed before it)
    Intent hello;
    ReceiveResult r = g_ep.Receive("BHc\t1 HELLO 1 1/1 1,1.0.0,0,enUS", 1000, hello);
    if (r.verdict != Verdict::Accepted || !g_ep.Ready())
    {
        std::fprintf(stderr, "bh_gen: HELLO not accepted\n");
        return 1;
    }

    HelloReply h;
    h.proto = 1; h.minProto = 1; h.serverEpoch = 1792648725; h.utcOffsetMin = -300; h.dataVer = 4242;
    h.featureBits = FeatureSeason | FeatureLeaderboards | FeatureServerPullTimer; h.seasonId = 1;
    h.dailyResetEpoch = 1792674645; h.weeklyResetEpoch = 1792907925; h.realmName = "Bleak;hold|Realm"; h.siteUrl = "bleakhold.com/a,b";
    Send("HELLO", EncodeHello(h));

    for (std::string const& p : EncodeDefinitions(Defs(), 4242))
        Send("DEF", p);

    {
        WeekState w;
        w.keysTimed = 1; w.mythicCoins = 10;
        SendRev("WEEK", Topic::Week, [&](uint32_t rev) { return EncodeWeek(rev, w); });
        w.keysTimed = 4; w.raidEchoes = 1; w.riftBestFloor = 18; w.mythicCoins = 2140; w.mythicCoinsCap = 5500; w.shards = 1260;
        SendRev("WEEK", Topic::Week, [&](uint32_t rev) { return EncodeWeek(rev, w); });
    }
    {
        EraState e;
        e.eraId = 7; e.nextEraId = 3; e.affixIds = { 1, 3, 4 }; e.weeklyBonusId = 1; e.weeklyBonusDone = true;
        SendRev("ERA", Topic::Era, [&](uint32_t rev) { return EncodeEra(rev, e); });
    }
    {
        TaskList t;
        t.freeRerolls = 1; t.rerollCost = 500000; t.rerollCurrency = Currency::MythicCoins;
        auto task = [](uint32_t uid, TaskKind k, uint32_t tpl, uint32_t have, uint32_t need, RewardKind rk, uint32_t amount, Opt<uint32_t> item,
                        TaskState st, std::string title = {}, std::string text = {}, std::string rt = {}) {
            Task x;
            x.uid = uid; x.kind = k; x.templateId = tpl; x.have = have; x.need = need; x.rewardKind = rk; x.rewardAmount = amount;
            x.rewardItemId = item; x.state = st; x.title = std::move(title); x.text = std::move(text); x.rewardText = std::move(rt);
            return x;
        };
        t.tasks = {
            task(101, TaskKind::Daily, 1, 0, 1, RewardKind::MythicCoins, 20, std::nullopt, TaskState::Open),
            task(102, TaskKind::Daily, 2, 14, 20, RewardKind::Item, 1, 40752u, TaskState::Open, "", "", "1 Emblem of Heroism"),
            task(103, TaskKind::Daily, 3, 5, 5, RewardKind::Shards, 3, std::nullopt, TaskState::Claimable),
            task(201, TaskKind::Weekly, 4, 1, 3, RewardKind::Copper, 1234567, std::nullopt, TaskState::Open,
                "Echoes; of, the: era~", "Clear 3 keys | 100% in time", "Legacy Cache (Tier 6)"),
            task(202, TaskKind::Weekly, 5, 2, 2, RewardKind::Text, 0, std::nullopt, TaskState::Claimed),
        };
        SendRev("TASKS", Topic::Tasks, [&](uint32_t rev) { return EncodeTasks(rev, t); });
        // TaskProgress(): a delta with the next revision once the snapshot is out
        SendRev("TASK", Topic::Tasks, [&](uint32_t rev) { return EncodeTaskDelta(rev, 102, 20, TaskState::Claimable); });
    }
    {
        KeyState k;
        k.dungeonId = 602; k.level = 8; k.affixIds = { 1, 3, 4 }; k.mode = 2; k.weeklyBestLevel = 9; k.weeklyBestDungeonId = 599;
        k.cachesReady = 1; k.cachesBanked = 2; k.keystoneItemId = 900001; k.maxLevel = 20; k.eraId = 7; k.depleted = true;
        SendRev("KEY", Topic::Key, [&](uint32_t rev) { return EncodeKey(rev, k); });
    }
    {
        BoardState b;
        b.shards = 1260; b.bountyId = 55; b.bountyDungeonId = 189; b.bountyState = BountyState::Claimable;
        b.bountyRewardText = "50 Shards, doubled"; b.firstRunBonus = true;
        for (uint32_t i = 0; i < 100; ++i)
        {
            BoardDungeon x;
            x.dungeonId = 2000 + i; x.chapter = 1 + i % 5; x.lvlMin = 10 + i % 60; x.lvlMax = 15 + i % 60; x.tierBits = 15;
            if (i % 3)
            {
                x.bestScore = i * 10; x.bestTier = i % 4;
            }
            x.recordScore = 9000 + i; x.recordName = (i % 2) ? "Br\xC3\xA9nna%" : "Aldric";
            x.locked = i % 7 == 0;
            b.dungeons.push_back(x);
        }
        SendRev("BOARD", Topic::Board, [&](uint32_t rev) { return EncodeBoard(rev, b); });
    }
    {
        QueueState q;
        q.state = QueueStateId::Proposal; q.kind = QueueKind::Rift; q.activityId = 0; q.tier = 0; q.size = 5; q.queuedSec = 40;
        q.proposalId = 77; q.timeoutSec = 40; q.bandMin = 23; q.bandMax = 28;
        QueueMember a; a.name = "Tester"; a.classId = 1; a.role = RoleTank; a.accepted = ProposalAnswer::Accepted; a.level = 25;
        QueueMember b; b.name = "Br\xC3\xA9nna"; b.classId = 2; b.role = RoleHealer; b.accepted = ProposalAnswer::Declined; b.level = 26;
        QueueMember c; c.name = "Corwin"; c.classId = 12; c.role = RoleDamage; c.level = 24;
        q.members = { a, b, c };
        SendRev("QUEUE", Topic::Queue, [&](uint32_t rev) { return EncodeQueue(rev, q); });
    }
    {
        KeyRunStart s;
        s.runId = 7001; s.dungeonId = 602; s.level = 8; s.affixIds = { 1, 3, 4 }; s.eraId = 7; s.countdownMs = 10000; s.timeLimitSec = 1800;
        Send("MPS", EncodeKeyRunStart(s));
        KeyRunState m;
        m.runId = 7001; m.timeLimitSec = 1800; m.forcesMax = 100; m.chestSec = { 1260, 1440 }; m.state = KeyRunStateId::Countdown;
        Send("MP", EncodeKeyRunState(m));
        m.state = KeyRunStateId::Running; m.elapsedMs = 1122000; m.deaths = 2; m.deathPenaltySec = 10; m.forcesCur = 64;
        m.bossBits = 1 | 4; m.bossKillSec = { 300, 0, 900 };
        Send("MP", EncodeKeyRunState(m));
        KeyRunEnd e;
        e.runId = 7001; e.result = KeyRunResultId::InTime; e.timeMs = 1453000; e.keyDelta = -2; e.newDungeonId = 599; e.newLevel = 6; e.score = 1840;
        Reward chest; chest.kind = RewardKind::Text; chest.amount = 1; chest.text = "Spoils chest, in your bags";
        Reward coins; coins.kind = RewardKind::MythicCoins; coins.amount = 150;
        Reward item; item.kind = RewardKind::Item; item.amount = 2; item.itemId = 40752;
        e.rewards = { chest, coins, item };
        Send("MPE", EncodeKeyRunEnd(e));
    }
    {
        RiftState rf;
        rf.runId = 8001; rf.state = RiftStateId::Running; rf.floor = 7; rf.bossId = 3; rf.bossName = "Echo of Nefarian"; rf.elapsedMs = 120000;
        rf.bestFloor = 18; rf.rank = 42; rf.deaths = 1; rf.groupSize = 5;
        Send("RIFT", EncodeRift(rf));
        RiftEnd e;
        e.runId = 8001; e.floorReached = 21; e.timeMs = 180000; e.score = 777; e.newBest = true; e.rank = 3;
        Reward coins; coins.kind = RewardKind::MythicCoins; coins.amount = 20;
        e.rewards = { coins };
        Send("RIFTE", EncodeRiftEnd(e));
    }
    {
        CollectionState c;
        c.transmogOwned = 412; c.laterAgesOwned = 0; c.laterAgesTotal = 3771; c.legacySetsOwned = 3; c.legacySetsTotal = 48;
        c.tierHave = { 3, 0, 0, 0, 0, 0, 0 }; c.tierTotal = { 8, 8, 5, 9, 5, 5, 8 };
        SendRev("COLL", Topic::Coll, [&](uint32_t rev) { return EncodeCollections(rev, c); });
    }
    {
        LegacySet s;
        s.tier = 1; s.setId = 201; s.classId = 1; s.name = "Battlegear of Might"; s.collectedBits = 56; s.outfitUnlocked = false;
        s.itemIds = { 16866, 16868, 16865, 16861, 16863, 16864, 16867, 16862 }; s.sourceDungeonIds = { 229, 329, 289, 429, 543 };
        s.lvlMin = 58; s.lvlMax = 61; s.echoBoss = "Ragnaros"; s.note = "Drops in keys: and the Rift.";
        Send("SET", EncodeLegacySet(s));
    }
    {
        LegacyIndex idx;
        for (uint32_t i = 0; i < 1500; ++i)
        {
            LegacyIndexEntry e;
            e.itemId = 30000 + i; e.tier = 1 + i % 7; e.setId = 200 + i / 8; e.collected = i % 2 == 0;
            idx.items.push_back(e);
        }
        SendRev("LIDX", Topic::Lidx, [&](uint32_t rev) { return EncodeLegacyIndex(rev, idx); });
        SendRev("LCOL", Topic::Lidx, [&](uint32_t rev) { return EncodeLegacyCollected(rev, 30001, true); });
    }
    {
        SeasonState s;
        s.seasonId = 1; s.warEffortPermille = 620; s.contributors = 1284; s.points = 1240; s.rankId = 2; s.nextRankId = 3; s.pointsToNextRank = 260;
        s.warEffortTitle = "Breach the Greymane Wall"; s.warEffortText = "Fill the bar together; 100% opens it."; s.spareTokens = 3;
        s.parts = { { "Materials", 800u }, { "Bosses, Echoes", 550u }, { "Keys in time", 510u } };
        SeasonRewardState a; a.rewardId = 1; a.earned = true; a.stateText = "Earned";
        SeasonRewardState b; b.rewardId = 2; b.earned = false; b.stateText = "7 / 20";
        s.rewards = { a, b };
        SendRev("SEASON", Topic::Season, [&](uint32_t rev) { return EncodeSeason(rev, s); });
    }
    {
        for (Board board : { Board::Keys, Board::Rift, Board::RaidEchoes })
        {
            Leaderboard lb;
            lb.board = board; lb.seasonId = 1; lb.dungeonId = 0; lb.classId = 0; lb.page = 2; lb.pages = 7;
            for (uint32_t i = 0; i < 10; ++i)
            {
                LeaderboardRow row;
                row.rank = 11 + i;
                if (board == Board::Keys)
                {
                    row.dungeonId = 602; row.value = 15 - i / 2; row.timeSec = 300 - int64_t(i) * 60;
                }
                else if (board == Board::Rift)
                {
                    row.value = 30 - i; row.timeSec = 1500 + i * 40;
                }
                else
                {
                    row.timeSec = 140 + i * 9; row.label = "Echo of Ragnaros";
                }
                row.dateEpoch = 1792645125 - i * 3600;
                for (uint32_t k = 0; k < (i % 2 ? 1u : 5u); ++k)
                    row.members.push_back({ k == 0 ? "Br\xC3\xA9nna" : "Member" + std::to_string(k), 1 + k });
                lb.rows.push_back(row);
            }
            Send("LB", EncodeLeaderboard(lb));
            LeaderboardMe me;
            me.board = board; me.rank = 42; me.topPercent = 12; me.value = board == Board::RaidEchoes ? Opt<int64_t>() : Opt<int64_t>(9);
            me.dungeonId = board == Board::Keys ? Opt<uint32_t>(602) : Opt<uint32_t>(); me.timeSec = -154; me.barPermille = 580;
            me.label = board == Board::RaidEchoes ? "Echo of Ragnaros" : "";
            Send("LBME", EncodeLeaderboardMe(me));
        }
        FirstsList f;
        f.entries = { { "echo", "Echo of Ragnaros defeated", "Ironvow (Aldric, Br\xC3\xA9nna)", 1792562325u },
            { "key", "First timed +15", "Dalia's group", 1792216725u } };
        Send("FIRSTS", EncodeFirsts(f));
    }
    Send("TOAST", EncodeToast({ ToastKind::Record, "New record", "Halls of Lightning +8 in 24:13", "leaderboards" }));
    {
        ErrorReply e;
        e.op = IntentType::TaskClaim; e.seq = 46; e.code = "not_claimable"; e.text = "That task cannot be claimed yet, sorry.";
        Send("ERR", EncodeError(e));
    }
    Send("PONG", EncodePong({ 12345, 1792648790 }));

    std::ofstream out(argv[2], std::ios::binary);
    out << "-- generated by Server/mod-bleakhold-ui/tests/cpp/bh_gen.cpp (maxBody " << g_maxBody << "). Do not edit.\n";
    out << "return {\n  maxBody = " << g_maxBody << ",\n  revs = { WEEK = " << g_ep.Rev(Topic::Week) << ", ERA = " << g_ep.Rev(Topic::Era)
        << ", TASKS = " << g_ep.Rev(Topic::Tasks) << ", KEY = " << g_ep.Rev(Topic::Key) << ", BOARD = " << g_ep.Rev(Topic::Board)
        << ", QUEUE = " << g_ep.Rev(Topic::Queue) << ", COLL = " << g_ep.Rev(Topic::Coll) << ", LIDX = " << g_ep.Rev(Topic::Lidx)
        << ", SEASON = " << g_ep.Rev(Topic::Season) << " },\n  messages = " << g_ep.Stats().messagesOut << ",\n  frames = {\n";
    for (std::string const& f : g_frames)
        out << "    " << LuaString(f) << ",\n";
    out << "  },\n}\n";
    std::printf("bh_gen: %zu frames for %llu messages (max body %zu) -> %s\n", g_frames.size(),
        static_cast<unsigned long long>(g_ep.Stats().messagesOut), g_maxBody, argv[2]);
    return 0;
}
