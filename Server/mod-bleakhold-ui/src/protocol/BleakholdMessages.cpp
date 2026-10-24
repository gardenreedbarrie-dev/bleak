/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Text lengths and list sizes are the ones the client keeps (Interface/AddOns/Bleakhold/State.lua and
 * the 500-record cap of Comm.SplitRecords): anything longer would be cut by the client anyway, so it is
 * cut here and never takes frame space.
 */

#include "BleakholdMessages.h"
#include "BleakholdCodec.h"

#include <algorithm>

namespace Bleakhold
{
    using Proto::PayloadWriter;

    namespace
    {
        // The client splits at most 500 records per message (Comm.SplitRecords); with the first record
        // being the header, 499 entries is all a list message can carry.
        constexpr std::size_t MaxRecordsAfterHeader = 499;

        char C(char v) { return v; }
        template <typename E>
        char Letter(E e) { return static_cast<char>(e); }
        template <typename E>
        int64_t Num(E e) { return static_cast<int64_t>(e); }

        void WriteRewards(PayloadWriter& w, std::vector<Reward> const& rewards)
        {
            std::size_t n = 0;
            for (Reward const& r : rewards)
            {
                if (n++ >= 20)
                    break;
                w.Record().Char(Letter(r.kind)).Opt(r.amount).Opt(r.itemId).Text(r.text, 60);
            }
        }
    }

    std::string EncodeHello(HelloReply const& m)
    {
        PayloadWriter w;
        w.Int(m.proto).Int(m.minProto).Int(m.serverEpoch).Int(m.utcOffsetMin).Int(m.dataVer).Int(m.featureBits)
            .Opt(m.seasonId).Opt(m.dailyResetEpoch).Opt(m.weeklyResetEpoch).Text(m.realmName, 48).Text(m.siteUrl, 80);
        return w.Take();
    }

    std::string EncodePong(Pong const& m)
    {
        PayloadWriter w;
        w.Int(m.nonce).Int(m.serverEpoch);
        return w.Take();
    }

    std::string EncodeError(ErrorReply const& m)
    {
        PayloadWriter w;
        // op and seq are rebuilt from the parsed intent, never copied from client text
        w.Text(IntentOpName(m.op), 8).Text(Proto::Base36(m.seq), 8).Text(m.code, 24).Text(m.text, 160);
        return w.Take();
    }

    std::string EncodeToast(Toast const& m)
    {
        PayloadWriter w;
        w.Char(Letter(m.kind)).Text(m.title, 60).Text(m.subtitle, 100).Text(m.openTarget, 16);
        return w.Take();
    }

    std::string EncodeWeek(uint32_t rev, WeekState const& m)
    {
        PayloadWriter w;
        w.Int(rev).Opt(m.keysTimed).Opt(m.raidEchoes).Opt(m.riftBestFloor).Opt(m.mythicCoins).Opt(m.mythicCoinsCap).Opt(m.shards);
        return w.Take();
    }

    std::string EncodeEra(uint32_t rev, EraState const& m)
    {
        PayloadWriter w;
        w.Int(rev).Opt(m.eraId).Opt(m.nextEraId).Ints(m.affixIds, 6).Opt(m.weeklyBonusId).Opt(m.weeklyBonusDone);
        return w.Take();
    }

    std::string EncodeTasks(uint32_t rev, TaskList const& m)
    {
        PayloadWriter w;
        w.Int(rev).Opt(m.freeRerolls).Opt(m.rerollCost).Char(Letter(m.rerollCurrency));
        std::size_t n = 0;
        for (Task const& t : m.tasks)
        {
            if (n++ >= 24)
                break;
            w.Record().Int(t.uid).Char(Letter(t.kind)).Opt(t.templateId).Int(t.have).Int(t.need).Char(Letter(t.rewardKind))
                .Opt(t.rewardAmount).Opt(t.rewardItemId).Int(Num(t.state)).Text(t.title, 48).Text(t.text, 200).Text(t.rewardText, 60);
        }
        return w.Take();
    }

    std::string EncodeTaskDelta(uint32_t rev, uint32_t uid, uint32_t have, TaskState state)
    {
        PayloadWriter w;
        w.Int(rev).Int(uid).Int(have).Int(Num(state));
        return w.Take();
    }

    std::string EncodeKey(uint32_t rev, KeyState const& m)
    {
        PayloadWriter w;
        w.Int(rev).Int(m.dungeonId).Opt(m.level).Ints(m.affixIds, 6).Opt(m.mode).Opt(m.weeklyBestLevel).Opt(m.weeklyBestDungeonId)
            .Opt(m.cachesReady).Opt(m.cachesBanked).Opt(m.keystoneItemId).Opt(m.maxLevel).Opt(m.eraId).Opt(m.depleted);
        return w.Take();
    }

    std::string EncodeBoard(uint32_t rev, BoardState const& m)
    {
        PayloadWriter w;
        w.Int(rev).Opt(m.shards).Opt(m.bountyId).Opt(m.bountyDungeonId).Int(Num(m.bountyState)).Text(m.bountyRewardText, 60).Opt(m.firstRunBonus);
        std::size_t n = 0;
        for (BoardDungeon const& d : m.dungeons)
        {
            if (n++ >= 120)
                break;
            w.Record().Int(d.dungeonId).Opt(d.chapter).Opt(d.lvlMin).Opt(d.lvlMax).Opt(d.tierBits).Opt(d.bestScore).Opt(d.bestTier)
                .Opt(d.recordScore).Text(d.recordName, 24).Opt(d.locked);
        }
        return w.Take();
    }

    std::string EncodeQueue(uint32_t rev, QueueState const& m)
    {
        PayloadWriter w;
        w.Int(rev).Int(Num(m.state)).Char(Letter(m.kind)).Opt(m.activityId).Opt(m.tier).Opt(m.size).Opt(m.queuedSec).Opt(m.estWaitSec)
            .Opt(m.proposalId).Opt(m.timeoutSec).Opt(m.bandMin).Opt(m.bandMax);
        std::size_t n = 0;
        for (QueueMember const& q : m.members)
        {
            if (n++ >= 40)
                break;
            w.Record().Text(q.name, 24).Opt(q.classId).Opt(q.role).Int(Num(q.accepted)).Opt(q.level);
        }
        return w.Take();
    }

    std::string EncodeKeyRunStart(KeyRunStart const& m)
    {
        PayloadWriter w;
        w.Int(m.runId).Int(m.dungeonId).Opt(m.level).Ints(m.affixIds, 6).Opt(m.eraId).Opt(m.countdownMs).Opt(m.timeLimitSec);
        return w.Take();
    }

    std::string EncodeKeyRunState(KeyRunState const& m)
    {
        PayloadWriter w;
        w.Int(m.runId).Int(m.elapsedMs).Opt(m.timeLimitSec).Int(m.deaths).Int(m.deathPenaltySec).Int(m.forcesCur).Int(m.forcesMax)
            .Int(m.bossBits).Ints(m.bossKillSec, 16).Ints(m.chestSec, 4).Int(Num(m.state));
        return w.Take();
    }

    std::string EncodeKeyRunEnd(KeyRunEnd const& m)
    {
        PayloadWriter w;
        w.Int(m.runId).Int(Num(m.result)).Opt(m.timeMs).Opt(m.keyDelta).Opt(m.newDungeonId).Opt(m.newLevel).Opt(m.score);
        WriteRewards(w, m.rewards);
        return w.Take();
    }

    std::string EncodeRift(RiftState const& m)
    {
        PayloadWriter w;
        w.Opt(m.runId).Int(Num(m.state)).Opt(m.floor).Opt(m.bossId).Text(m.bossName, 48).Opt(m.elapsedMs).Opt(m.bestFloor)
            .Opt(m.score).Opt(m.rank).Opt(m.deaths).Opt(m.groupSize);
        return w.Take();
    }

    std::string EncodeRiftEnd(RiftEnd const& m)
    {
        PayloadWriter w;
        w.Opt(m.runId).Opt(m.floorReached).Opt(m.timeMs).Opt(m.score).Opt(m.newBest).Opt(m.rank);
        WriteRewards(w, m.rewards);
        return w.Take();
    }

    std::string EncodeCollections(uint32_t rev, CollectionState const& m)
    {
        PayloadWriter w;
        w.Int(rev).Opt(m.transmogOwned).Opt(m.transmogTotal).Opt(m.laterAgesOwned).Opt(m.laterAgesTotal).Opt(m.legacySetsOwned)
            .Opt(m.legacySetsTotal).Ints(m.tierHave, 16).Ints(m.tierTotal, 16);
        return w.Take();
    }

    std::string EncodeLegacySet(LegacySet const& m)
    {
        PayloadWriter w;
        w.Int(m.tier).Opt(m.setId).Int(m.classId).Text(m.name, 60).Opt(m.collectedBits).Opt(m.outfitUnlocked).Ints(m.itemIds, 12)
            .Ints(m.sourceDungeonIds, 12).Opt(m.lvlMin).Opt(m.lvlMax).Text(m.echoBoss, 48).Text(m.note, 120);
        return w.Take();
    }

    std::string EncodeLegacyIndex(uint32_t rev, LegacyIndex const& m)
    {
        PayloadWriter w;
        w.Int(rev);
        std::size_t n = 0;
        for (LegacyIndexEntry const& e : m.items)
        {
            if (n++ >= MaxRecordsAfterHeader)
                break;
            w.Record().Int(e.itemId).Opt(e.tier).Opt(e.setId).Opt(e.collected);
        }
        return w.Take();
    }

    std::string EncodeLegacyCollected(uint32_t rev, uint32_t itemId, bool collected)
    {
        PayloadWriter w;
        w.Int(rev).Int(itemId).Bool(collected);
        return w.Take();
    }

    std::string EncodeCases(CaseList const& m)
    {
        PayloadWriter w;
        std::size_t n = 0;
        for (uint32_t id : m.caseItemIds)
        {
            if (n++ >= MaxCases)
                break;
            if (n > 1)
                w.Record();
            w.Int(id);
        }
        return w.Take();
    }

    std::string EncodeCase(CaseInfo const& m)
    {
        PayloadWriter w;
        w.Int(m.caseItemId).Text(m.title, 60).Text(m.text, 120);
        if (m.keyItemId)
            w.Int(m.keyItemId).Int(std::max<uint32_t>(1, m.keyCount));
        else
            w.Empty().Empty();
        std::size_t n = 0;
        for (CaseReward const& r : m.rewards)
        {
            if (n++ >= MaxCaseRewards)
                break;
            w.Record().Int(r.itemId).Int(std::max<uint32_t>(1, r.count)).Int(std::min<uint32_t>(r.chance, 10000))
                .Int(std::min<uint8_t>(r.tier, 6));
        }
        return w.Take();
    }

    std::string EncodeUnbox(Unbox const& m)
    {
        PayloadWriter w;
        w.Int(m.caseItemId).Int(m.rewardIndex).Int(m.itemId).Int(std::max<uint32_t>(1, m.count)).Int(m.nonce);
        return w.Take();
    }

    std::string EncodeCampState(CampState const& m)
    {
        auto tier = [](uint8_t t) { return static_cast<int64_t>(std::clamp<uint8_t>(t, 1, 3)); };
        std::vector<std::vector<std::string>> objects;
        for (CampObjectInfo const& o : m.objects)
            objects.push_back({ PayloadWriter::TuplePart(o.skill), PayloadWriter::TuplePart(tier(o.tier)), PayloadWriter::TuplePart(o.mine ? 1 : 0) });
        std::vector<std::vector<std::string>> place;
        for (CampPlace const& p : m.place)
            place.push_back({ PayloadWriter::TuplePart(p.skill), PayloadWriter::TuplePart(tier(p.tier)) });
        PayloadWriter w;
        w.Char(Letter(m.state)).Int(m.state == CampStateId::Resting ? m.settleSec : 0).Int(m.fireSec).Bool(m.mine).Int(m.cooldownSec)
            .Int(m.warmthSec).Int(m.xpPct).Tuples(objects, MaxCampObjects).Tuples(place, MaxCampPlaces).Opt(m.glideSec).Bool(m.repair)
            .Bool(m.fed);
        return w.Take();
    }

    std::string EncodeSeason(uint32_t rev, SeasonState const& m)
    {
        PayloadWriter w;
        w.Int(rev).Opt(m.seasonId).Opt(m.warEffortPermille).Opt(m.contributors).Opt(m.points).Opt(m.rankId).Opt(m.nextRankId)
            .Opt(m.pointsToNextRank).Text(m.warEffortTitle, 60).Text(m.warEffortText, 200).Opt(m.spareTokens);
        std::size_t n = 0;
        for (SeasonPart const& p : m.parts)
        {
            if (n++ >= 6)
                break;
            w.Record().Char('P').Text(p.name, 40).Opt(p.permille);
        }
        n = 0;
        for (SeasonRewardState const& r : m.rewards)
        {
            if (n++ >= 8)
                break;
            w.Record().Char('R').Int(r.rewardId).Opt(r.earned).Text(r.stateText, 40);
        }
        return w.Take();
    }

    std::string EncodeLeaderboard(Leaderboard const& m)
    {
        PayloadWriter w;
        w.Char(Letter(m.board)).Opt(m.seasonId).Opt(m.dungeonId).Opt(m.classId).Int(m.page).Int(m.pages);
        std::size_t n = 0;
        for (LeaderboardRow const& r : m.rows)
        {
            if (n++ >= 50)
                break;
            std::vector<std::vector<std::string>> members;
            for (LeaderboardMember const& mem : r.members)
            {
                if (members.size() >= 10)
                    break;
                members.push_back({ PayloadWriter::TuplePart(mem.name, 24),
                    mem.classId ? PayloadWriter::TuplePart(static_cast<int64_t>(*mem.classId)) : std::string() });
            }
            w.Record().Int(r.rank).Opt(r.dungeonId).Opt(r.value).Opt(r.timeSec).Opt(r.dateEpoch).Tuples(members).Text(r.label, 48);
        }
        return w.Take();
    }

    std::string EncodeLeaderboardMe(LeaderboardMe const& m)
    {
        PayloadWriter w;
        w.Char(Letter(m.board)).Opt(m.rank).Opt(m.topPercent).Opt(m.value).Opt(m.dungeonId).Opt(m.timeSec).Opt(m.barPermille)
            .Text(m.label, 48);
        return w.Take();
    }

    std::string EncodeFirsts(FirstsList const& m)
    {
        PayloadWriter w;
        std::size_t n = 0;
        for (ServerFirst const& f : m.entries)
        {
            if (n++ >= 50)
                break;
            w.Record().Text(f.kindKey, 16).Text(f.text, 120).Text(f.who, 80).Opt(f.dateEpoch);
        }
        return w.Take();
    }

    std::vector<std::string> EncodeDefinitions(Definitions const& d, uint32_t dataVer)
    {
        std::vector<std::string> out;
        auto kind = [&](char k, auto const& list, auto writeOne) {
            if (list.empty())
                return;
            PayloadWriter w;
            w.Char(C(k)).Int(dataVer);
            std::size_t n = 0;
            for (auto const& e : list)
            {
                if (n++ >= MaxRecordsAfterHeader)
                    break;
                w.Record();
                writeOne(w, e);
            }
            out.push_back(w.Take());
        };
        kind('A', d.affixes, [](PayloadWriter& w, AffixDef const& e) { w.Int(e.id).Text(e.name, 40).Text(e.text, 200); });
        kind('E', d.eras, [](PayloadWriter& w, EraDef const& e) { w.Int(e.id).Text(e.name, 48).Text(e.text, 200).Opt(e.legacyTier); });
        kind('T', d.taskTemplates, [](PayloadWriter& w, TaskTemplateDef const& e) { w.Int(e.id).Text(e.title, 48).Text(e.text, 200); });
        kind('B', d.weeklyBonuses, [](PayloadWriter& w, WeeklyBonusDef const& e) { w.Int(e.id).Text(e.title, 48).Text(e.text, 200); });
        kind('C', d.chapters, [](PayloadWriter& w, ChapterDef const& e) { w.Int(e.id).Text(e.name, 60).Text(e.text, 200); });
        kind('D', d.dungeons, [](PayloadWriter& w, DungeonDef const& e) {
            w.Int(e.id).Text(e.name, 48).Opt(e.chapter).Opt(e.lvlMin).Opt(e.lvlMax).Texts(e.bosses, 12, 40).Opt(e.timeLimitSec);
        });
        kind('L', d.legacyTiers, [](PayloadWriter& w, LegacyTierDef const& e) {
            w.Int(e.id).Text(e.label, 24).Text(e.raids, 80).Opt(e.eraId).Ints(e.sources, 12).Opt(e.lvlMin).Opt(e.lvlMax)
                .Text(e.echoBoss, 48).Opt(e.pieceTotal);
        });
        kind('S', d.seasons, [](PayloadWriter& w, SeasonDef const& e) { w.Int(e.id).Text(e.name, 60).Text(e.text, 200).Int(Num(e.state)); });
        kind('K', d.ranks, [](PayloadWriter& w, RankDef const& e) { w.Int(e.id).Text(e.name, 48); });
        kind('W', d.seasonRewards, [](PayloadWriter& w, SeasonRewardDef const& e) { w.Int(e.id).Text(e.name, 40).Text(e.requirementText, 120); });
        kind('M', d.mythicLevels, [](PayloadWriter& w, MythicLevelDef const& e) { w.Int(e.level).Text(e.text, 200); });
        kind('X', d.extraClasses, [](PayloadWriter& w, ExtraClassDef const& e) {
            w.Int(e.id).Text(e.name, 24).Text(e.token, 24).Text(e.colorHex, 6).Text(e.shortLabel, 4);
        });
        kind('R', d.riftBosses, [](PayloadWriter& w, RiftBossDef const& e) { w.Int(e.id).Text(e.name, 48); });
        PayloadWriter z;
        z.Char('Z').Int(dataVer);
        out.push_back(z.Take());
        return out;
    }

    uint32_t DefinitionsHash(Definitions const& d)
    {
        // FNV-1a over the encoded definitions written with a fixed placeholder version.
        uint64_t h = 1469598103934665603ull;
        for (std::string const& p : EncodeDefinitions(d, 0))
        {
            for (char ch : p)
            {
                h ^= static_cast<unsigned char>(ch);
                h *= 1099511628211ull;
            }
            h ^= 0xFF;
            h *= 1099511628211ull;
        }
        uint32_t v = static_cast<uint32_t>((h ^ (h >> 31)) & 0x7FFFFFFFu);
        return v ? v : 1;
    }
}
