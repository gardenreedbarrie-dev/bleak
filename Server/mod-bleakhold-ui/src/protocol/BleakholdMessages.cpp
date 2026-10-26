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
#include <string_view>

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
        // Bleakhold Royale (section 17): the queue counts after bandMax, and no member records
        if (m.kind == QueueKind::Royale)
        {
            w.Opt(m.queued).Opt(m.minPlayers).Opt(m.maxPlayers).Opt(m.accepted).Opt(m.proposalSize)
                .Opt(m.matchesRunning);
            return w.Take();
        }
        // the 1v1 arena queue (section 20): no member records (the native invite dialog takes the player in)
        if (m.kind == QueueKind::Arena)
            return w.Take();
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

    std::string EncodeRoyaleState(RoyaleState const& m)
    {
        PayloadWriter w;
        w.Int(m.matchId).Int(Num(m.phase)).Int(m.phaseMsLeft).Int(m.alive).Int(m.total).Int(Num(m.me)).Int(m.kills)
            .Opt(m.placement).Opt(m.pinX).Opt(m.pinY).Int(m.stage).Int(m.curX).Int(m.curY).Int(m.curR).Opt(m.nextX)
            .Opt(m.nextY).Opt(m.nextR).Opt(m.shrinkStartMs).Opt(m.shrinkEndMs).Int(m.dmgPermille)
            .Text(m.watchName, RoyaleNameBytes).Opt(m.myX).Opt(m.myY).Opt(m.stages);
        return w.Take();
    }

    std::string EncodeRoyaleMap(RoyaleMap const& m)
    {
        PayloadWriter w;
        w.Int(m.mapId).Int(m.minX).Int(m.maxX).Int(m.minY).Int(m.maxY).Int(m.lobbyX).Int(m.lobbyY).Int(m.lobbyR)
            .Int(m.boundHalf).Int(m.centerX).Int(m.centerY);
        std::size_t n = 0;
        for (RoyalePoi const& p : m.pois)
        {
            if (n++ >= MaxRoyalePois)
                break;
            w.Record().Int(p.id).Char(Letter(p.kind)).Int(p.x).Int(p.y).Int(p.r).Text(p.name, 40);
        }
        return w.Take();
    }

    std::string EncodeRoyaleObjects(RoyaleObjects const& m)
    {
        PayloadWriter w;
        w.Int(m.matchId).Bool(m.full);
        std::size_t n = 0;
        for (RoyaleObject const& o : m.objects)
        {
            if (n++ >= MaxRoyaleObjects)
                break;
            w.Record().Int(o.objId).Char(Letter(o.kind)).Int(o.subtype).Int(o.x).Int(o.y).Int(Num(o.state))
                .Opt(o.msLeft);
        }
        return w.Take();
    }

    std::string EncodeRoyaleKill(RoyaleKill const& m)
    {
        PayloadWriter w;
        w.Text(m.killerName, RoyaleNameBytes).Opt(m.killerClassId).Text(m.victimName, RoyaleNameBytes)
            .Int(m.victimClassId).Char(Letter(m.cause)).Int(m.aliveAfter).Opt(m.killerKills);
        // `announce` (the 8th field) is superseded by BGANN (section 18): always empty, so it is left out
        return w.Take();
    }

    std::string EncodeRoyaleEvent(RoyaleEvent const& m)
    {
        PayloadWriter w;
        w.Char(Letter(m.kind)).Int(m.value).Opt(m.x).Opt(m.y).Opt(m.msLeft).Text(m.name, RoyaleNameBytes);
        return w.Take();
    }

    std::string EncodeRoyaleResult(RoyaleResult const& m)
    {
        PayloadWriter w;
        w.Int(m.matchId).Int(m.placement).Int(m.total).Int(m.kills).Int(m.damage).Int(m.healing).Int(m.survivedSec)
            .Text(m.winnerName, RoyaleNameBytes).Opt(m.winnerClassId).Opt(m.winnerKills).Bool(m.rewarded);
        WriteRewards(w, m.rewards);
        return w.Take();
    }

    char BgMultiLetter(BgMultiKill multi)
    {
        char const c = Letter(multi);
        return c != 0 && std::string_view("DTUR").find(c) != std::string_view::npos ? c : 0;
    }

    char BgStreakLetter(BgStreak streak)
    {
        char const c = Letter(streak);
        return c != 0 && std::string_view("FSOKNWMGH").find(c) != std::string_view::npos ? c : 0;
    }

    bool BgAnnounceSendable(BgAnnounce const& m)
    {
        return (BgMultiLetter(m.multi) || BgStreakLetter(m.streak))
            && !Proto::CleanText(m.killerName, BgNameBytes).empty() && !Proto::CleanText(m.victimName, BgNameBytes).empty();
    }

    std::string EncodeBgAnnounce(BgAnnounce const& m)
    {
        PayloadWriter w;
        w.Text(m.killerName, BgNameBytes).Int(m.killerClassId).Text(m.victimName, BgNameBytes).Int(m.victimClassId)
            .Char(BgMultiLetter(m.multi)).Char(BgStreakLetter(m.streak));
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
            // board A (section 20): season wins and games, tier, flags
            if (m.board == Board::Arena)
                w.Opt(r.seasonWins).Opt(r.seasonGames).Opt(r.tierId).Opt(r.flags);
        }
        return w.Take();
    }

    std::string EncodeLeaderboardMe(LeaderboardMe const& m)
    {
        PayloadWriter w;
        w.Char(Letter(m.board)).Opt(m.rank).Opt(m.topPercent).Opt(m.value).Opt(m.dungeonId).Opt(m.timeSec).Opt(m.barPermille)
            .Text(m.label, 48);
        if (m.board == Board::Arena)   // section 20
            w.Opt(m.topPermille).Opt(m.tierId);
        return w.Take();
    }

    std::string EncodeArena(ArenaState const& m)
    {
        PayloadWriter w;
        w.Int(m.seasonId).Int(Num(m.state)).Opt(m.startEpoch).Opt(m.endEpoch).Opt(m.nextStartEpoch).Bool(m.ratedOpen)
            .Opt(m.oneTeamCostCopper).Text(m.seasonName, ArenaNameBytes);
        std::size_t n = 0;
        for (ArenaSeasonInfo const& e : m.seasons)
        {
            if (n++ >= MaxArenaSeasons)
                break;
            w.Record().Char('S').Int(e.id).Text(e.name, ArenaNameBytes).Int(Num(e.state)).Opt(e.startEpoch).Opt(e.endEpoch);
        }
        n = 0;
        for (ArenaBracketState const& b : m.brackets)
        {
            if (!IsArenaBracket(b.bracket) || n++ >= 4)
                continue;
            w.Record().Char('B').Int(b.bracket).Bool(b.hasTeam).Opt(b.rating).Opt(b.ladderRank).Opt(b.ladderSize)
                .Opt(b.seasonGames).Opt(b.seasonWins).Opt(b.weekGames).Opt(b.weekWins).Opt(b.personalRating)
                .Opt(b.recentGames).Opt(b.tierId).Opt(b.nextTierId).Opt(b.ratingToNext).Int(b.missingMask & 0xFFu)
                .Text(b.teamName, ArenaNameBytes);
        }
        n = 0;
        for (ArenaCutoff const& c : m.cutoffs)
        {
            if (!IsArenaBracket(c.bracket) || n++ >= MaxArenaCutoffs)
                continue;
            w.Record().Char('T').Int(c.bracket).Int(c.tierId).Int(c.slots).Opt(c.cutRank).Opt(c.cutRating).Int(c.floor);
        }
        n = 0;
        for (ArenaLadderInfo const& l : m.ladders)
        {
            if (!IsArenaBracket(l.bracket) || n++ >= 4)
                continue;
            w.Record().Char('N').Int(l.bracket).Int(l.eligibleTeams).Bool(l.rewardsOpen).Bool(l.titlesOpen);
        }
        n = 0;
        for (ArenaMatch const& x : m.matches)
        {
            if (!IsArenaBracket(x.bracket) || n++ >= MaxArenaMatches)
                continue;
            w.Record().Char('M').Int(x.bracket).Bool(x.won).Int(x.ratingChange).Text(x.opponent, ArenaNameBytes)
                .Int(x.endEpoch).Int(Num(x.verdict)).Char(Letter(x.reason));
        }
        n = 0;
        for (ArenaFinal const& f : m.finals)
        {
            if (!IsArenaBracket(f.bracket) || n++ >= 4)
                continue;
            w.Record().Char('F').Int(f.bracket).Int(f.finalRank).Int(f.finalRating).Opt(f.finalTierId).Int(Num(f.grant));
        }
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
        kind('V', d.arenaTiers, [](PayloadWriter& w, ArenaTierDef const& e) {
            w.Int(e.id).Text(e.name, 30).Text(e.colorHex, 6).Text(e.text, 120);
        });
        kind('Q', d.arenaRewards, [](PayloadWriter& w, ArenaRewardDef const& e) {
            w.Int(e.id).Int(e.seasonId).Int(e.bracket).Int(e.tierId).Char(e.kind).Int(e.entry).Int(e.count).Text(e.text, 60);
        });
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
