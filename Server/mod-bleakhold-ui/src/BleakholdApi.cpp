/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Bleakhold::Ui (BleakholdUi.h): thin wrappers over the manager and the data store.
 */

#include "BleakholdUi.h"
#include "BleakholdData.h"
#include "BleakholdMgr.h"

#include "Player.h"

namespace Bleakhold::Ui
{
    namespace
    {
        Mgr& M() { return Mgr::Instance(); }
    }

    // ---- intents ----
    void OnIntent(IntentType type, IntentHandler handler) { M().SetHandler(type, std::move(handler)); }
    void Refuse(Player* player, Intent const& intent, std::string_view code, std::string_view text) { M().Refuse(player, intent, code, text); }
    void OnHello(std::function<void(Player*, Intent const&)> observer) { M().SetHelloObserver(std::move(observer)); }
    bool HasAddon(Player* player) { return M().HasAddon(player); }
    void SetFeature(uint32_t feature, bool on) { M().SetFeature(feature, on); }
    bool FeatureOn(uint32_t feature) { return M().FeatureOn(feature); }

    // ---- requests ----
    void OnRequest(Topic topic, TopicProvider provider) { M().SetProvider(topic, std::move(provider)); }
    void Refresh(Player* player, Topic topic) { M().Refresh(player, topic); }

    // ---- revisioned ----
    void SendWeek(Player* player, WeekState const& m)
    {
        M().Push(player, "WEEK", Topic::Week, [&](PlayerSlot& s) { s.week = m; }, [&](uint32_t rev) { return EncodeWeek(rev, m); });
    }

    void SendEra(Player* player, EraState const& m)
    {
        M().Push(player, "ERA", Topic::Era, [&](PlayerSlot& s) { s.era = m; }, [&](uint32_t rev) { return EncodeEra(rev, m); });
    }

    void SendTasks(Player* player, TaskList const& m)
    {
        M().Push(player, "TASKS", Topic::Tasks, [&](PlayerSlot& s) { s.tasks = m; }, [&](uint32_t rev) { return EncodeTasks(rev, m); });
    }

    void TaskProgress(Player* player, uint32_t uid, uint32_t have, TaskState state) { M().TaskDelta(player, uid, have, state); }

    void SendKeyState(Player* player, KeyState const& m)
    {
        M().Push(player, "KEY", Topic::Key, [&](PlayerSlot& s) { s.key = m; }, [&](uint32_t rev) { return EncodeKey(rev, m); });
    }

    void BoardSnapshot(Player* player, BoardState const& m)
    {
        M().Push(player, "BOARD", Topic::Board, [&](PlayerSlot& s) { s.board = m; }, [&](uint32_t rev) { return EncodeBoard(rev, m); });
    }

    void QueueStatus(Player* player, QueueState const& m)
    {
        M().Push(player, "QUEUE", Topic::Queue, [&](PlayerSlot& s) { s.queue = m; }, [&](uint32_t rev) { return EncodeQueue(rev, m); });
    }

    void SendCollections(Player* player, CollectionState const& m)
    {
        M().Push(player, "COLL", Topic::Coll, [&](PlayerSlot& s) { s.coll = m; }, [&](uint32_t rev) { return EncodeCollections(rev, m); });
    }

    void SendLegacyIndex(Player* player, LegacyIndex const& m)
    {
        M().Push(player, "LIDX", Topic::Lidx, [&](PlayerSlot& s) { s.lidx = m; }, [&](uint32_t rev) { return EncodeLegacyIndex(rev, m); });
    }

    void LegacyItemCollected(Player* player, uint32_t itemId, bool collected) { M().LegacyDelta(player, itemId, collected); }

    void SendSeason(Player* player, SeasonState const& m)
    {
        M().Push(player, "SEASON", Topic::Season, [&](PlayerSlot& s) { s.season = m; }, [&](uint32_t rev) { return EncodeSeason(rev, m); });
    }

    // ---- unrevisioned ----
    void SendLegacySet(Player* player, LegacySet const& m)
    {
        M().Push(player, "SET", Topic::Count, nullptr, [&](uint32_t) { return EncodeLegacySet(m); });
    }

    void SendCases(Player* player, CaseList const& m)
    {
        M().Push(player, "CASES", Topic::Count, nullptr, [&](uint32_t) { return EncodeCases(m); });
    }

    void SendCase(Player* player, CaseInfo const& m)
    {
        M().Push(player, "CASE", Topic::Count, nullptr, [&](uint32_t) { return EncodeCase(m); });
    }

    void SendUnbox(Player* player, Unbox const& m)
    {
        M().Push(player, "UNBOX", Topic::Count, nullptr, [&](uint32_t) { return EncodeUnbox(m); });
    }

    void SendCampState(Player* player, CampState const& m)
    {
        M().Push(player, "CAMPST", Topic::Count, nullptr, [&](uint32_t) { return EncodeCampState(m); });
    }

    // ---- Bleakhold Royale (section 17) ----
    namespace
    {
        // one payload to every player of a list (unrevisioned, nothing remembered)
        void PushAll(std::vector<Player*> const& players, char const* op, std::string const& payload)
        {
            for (Player* p : players)
                M().Push(p, op, Topic::Count, nullptr, [&](uint32_t) { return payload; });
        }
    }

    void SendRoyaleState(Player* player, RoyaleState const& m)
    {
        M().Push(player, "ROYS", Topic::Count, nullptr, [&](uint32_t) { return EncodeRoyaleState(m); });
    }

    void SendRoyaleMap(Player* player, RoyaleMap const& m)
    {
        M().Push(player, "ROYM", Topic::Count, nullptr, [&](uint32_t) { return EncodeRoyaleMap(m); });
    }

    void SendRoyaleMap(std::vector<Player*> const& players, RoyaleMap const& m)
    {
        PushAll(players, "ROYM", EncodeRoyaleMap(m));
    }

    void SendRoyaleObjects(Player* player, RoyaleObjects const& m)
    {
        M().Push(player, "ROYO", Topic::Count, nullptr, [&](uint32_t) { return EncodeRoyaleObjects(m); });
    }

    void SendRoyaleObjects(std::vector<Player*> const& players, RoyaleObjects const& m)
    {
        PushAll(players, "ROYO", EncodeRoyaleObjects(m));
    }

    void SendRoyaleKill(Player* player, RoyaleKill const& m)
    {
        M().Push(player, "ROYK", Topic::Count, nullptr, [&](uint32_t) { return EncodeRoyaleKill(m); });
    }

    void SendRoyaleKill(std::vector<Player*> const& players, RoyaleKill const& m)
    {
        PushAll(players, "ROYK", EncodeRoyaleKill(m));
    }

    void SendRoyaleEvent(Player* player, RoyaleEvent const& m)
    {
        M().Push(player, "ROYV", Topic::Count, nullptr, [&](uint32_t) { return EncodeRoyaleEvent(m); });
    }

    void SendRoyaleEvent(std::vector<Player*> const& players, RoyaleEvent const& m)
    {
        PushAll(players, "ROYV", EncodeRoyaleEvent(m));
    }

    void SendRoyaleResult(Player* player, RoyaleResult const& m)
    {
        M().Push(player, "ROYE", Topic::Count, nullptr, [&](uint32_t) { return EncodeRoyaleResult(m); });
    }

    // ---- the battleground kill announcer (section 18) ----
    void SendBgAnnounce(Player* player, BgAnnounce const& m)
    {
        if (BgAnnounceSendable(m))
            M().Push(player, "BGANN", Topic::Count, nullptr, [&](uint32_t) { return EncodeBgAnnounce(m); });
    }

    void SendBgAnnounce(std::vector<Player*> const& players, BgAnnounce const& m)
    {
        if (BgAnnounceSendable(m))
            PushAll(players, "BGANN", EncodeBgAnnounce(m));
    }

    void RiftStatus(Player* player, RiftState const& m)
    {
        M().Push(player, "RIFT", Topic::Count, [&](PlayerSlot& s) { s.rift = m; }, [&](uint32_t) { return EncodeRift(m); });
    }

    void RiftEnded(Player* player, RiftEnd const& m)
    {
        M().Push(player, "RIFTE", Topic::Count, nullptr, [&](uint32_t) { return EncodeRiftEnd(m); });
    }

    void SendLeaderboard(Player* player, Leaderboard const& m)
    {
        M().Push(player, "LB", Topic::Count, nullptr, [&](uint32_t) { return EncodeLeaderboard(m); });
    }

    void SendLeaderboardMe(Player* player, LeaderboardMe const& m)
    {
        M().Push(player, "LBME", Topic::Count, nullptr, [&](uint32_t) { return EncodeLeaderboardMe(m); });
    }

    void SendFirsts(Player* player, FirstsList const& m)
    {
        M().Push(player, "FIRSTS", Topic::Count, nullptr, [&](uint32_t) { return EncodeFirsts(m); });
    }

    void SendToast(Player* player, Bleakhold::Toast const& m)
    {
        M().Push(player, "TOAST", Topic::Count, nullptr, [&](uint32_t) { return EncodeToast(m); });
    }

    void SendKeyRunStart(Player* player, Bleakhold::KeyRunStart const& m)
    {
        M().Push(player, "MPS", Topic::Count, nullptr, [&](uint32_t) { return EncodeKeyRunStart(m); });
    }

    void SendKeyRunState(Player* player, KeyRunState const& m)
    {
        M().Push(player, "MP", Topic::Count, nullptr, [&](uint32_t) { return EncodeKeyRunState(m); });
    }

    void SendKeyRunEnd(Player* player, KeyRunEnd const& m)
    {
        M().Push(player, "MPE", Topic::Count, nullptr, [&](uint32_t) { return EncodeKeyRunEnd(m); });
    }

    // ---- run tracker ----
    uint32_t KeyRunStart(KeyRunInfo const& info, std::vector<Player*> const& members, Player* leader) { return M().RunStart(info, members, leader); }
    void KeyTimerStart(uint32_t runId) { M().RunTimerStart(runId); }
    void KeyBossKilled(uint32_t runId, uint32_t bossIndex) { M().RunBoss(runId, bossIndex); }
    void KeyEnemyForces(uint32_t runId, uint32_t current, Opt<uint32_t> max) { M().RunForces(runId, current, max); }
    void KeyDeath(uint32_t runId, uint32_t penaltySec) { M().RunDeath(runId, penaltySec); }
    void KeyCompleted(uint32_t runId, KeyRunEnd const& result) { M().RunCompleted(runId, result); }
    void KeyAbandoned(uint32_t runId) { M().RunAbandoned(runId); }
    void KeyRunAddMember(uint32_t runId, Player* player) { M().RunAddMember(runId, player); }
    void KeyRunRemoveMember(uint32_t runId, Player* player) { M().RunRemoveMember(runId, player); }
    void KeyRunSync(uint32_t runId, KeyRunState const& state) { M().RunSync(runId, state); }
    Opt<uint32_t> KeyRunOf(Player* player) { return M().RunOf(player); }

    // ---- announcements ----
    void Announce(AnnounceTag tag, std::string_view text) { M().Announce(tag, text); }

    void AnnounceTo(Player* player, AnnounceTag tag, std::string_view text)
    {
        if (player)
            M().Announce(tag, text, player->GetGUID().GetRawValue());
    }

    // ---- the module's own tables ----
    void RecordLeaderboardRun(LeaderboardEntry const& entry) { Data::Instance().RecordRun(entry); }

    bool RecordServerFirst(std::string_view firstId, std::string_view kindKey, std::string_view text, std::string_view who, bool announce)
    {
        if (!Data::Instance().RecordFirst(firstId, kindKey, text, who))
            return false;
        if (announce)
            M().Announce(AnnounceTag::ServerFirst, std::string(text) + (who.empty() ? "" : " - " + std::string(who)));
        return true;
    }

    void WarEffortAdd(Player* player, uint32_t partId, uint32_t points) { Data::Instance().WarEffortAdd(player, partId, points); }

    uint64_t WarEffortPoints(Player* player)
    {
        return player ? Data::Instance().WarEffortPoints(player->GetGUID().GetCounter()) : 0;
    }

    void SetWeeklyBonusDone(Player* player, bool done) { M().SetWeeklyBonusDone(player, done); }

    // ---- sources ----
    void OnDefinitionsLoaded(std::function<void(Definitions&)> editor) { Data::Instance().AddDefinitionsEditor(std::move(editor)); }

    void SetLegacyCollectionSource(std::function<bool(Player*, uint32_t)> itemCollected, std::function<bool(Player*, uint32_t)> outfitUnlocked)
    {
        Data::Instance().SetLegacySource(std::move(itemCollected), std::move(outfitUnlocked));
        M().ClearCaches(Topic::Lidx);
    }

    void SetSeasonRewardSource(std::function<bool(Player*, uint32_t, SeasonRewardState&)> source) { Data::Instance().SetSeasonRewardSource(std::move(source)); }
    void SetResetTimesSource(std::function<std::pair<uint32_t, uint32_t>()> source) { Data::Instance().SetResetSource(std::move(source)); }
    void SetCurrentSeason(uint32_t seasonId) { Data::Instance().SetSeasonOverride(seasonId); }
    uint32_t CurrentSeason() { return Data::Instance().CurrentSeason(); }
}
