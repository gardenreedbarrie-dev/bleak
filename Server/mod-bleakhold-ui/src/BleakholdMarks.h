/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Glowing marks (section 22): a mark (design and colour) and an eye colour are a cosmetic of their own, apart from
 * the character tables (the realm's CharSections are an HD pack). Marks keeps the configuration (BleakholdUi.Marks.*),
 * the catalogue (bleakhold_mark_catalogue, written by bleakserv's deploy/marks/build-marks.sh), the choice of every
 * online character (bleakhold_marks), MARKSET with its gold and cooldown, and the lists: every client with the feature
 * bit gets the marks of every online player (MARKS after HELLO, a MARK delta on a change, a login and a logout). The
 * client turns them into texture paths and hands them to Bleakhold.exe by player GUID. The rules are
 * BleakholdMarksRules.h (tested core-free).
 *
 * Threads: everything runs on the world thread (intents, GETs, HELLO observers, login, logout, delete, the tick,
 * .bleakhold reload). FeatureFor reads atomics and the character's session only. No Ui::Send* is called while _lock
 * is held.
 *
 * Off by default (BleakholdUi.Marks.Enable = 0, GmOnly = 1): the tables are still made and the catalogue read at
 * startup, so .bleakhold reload can turn it on; while it is off (or no race-sex is offered) nobody gets the bit,
 * MARKSET gets ERR marks_off (Mgr::Dispatch), nothing is listed and DEF N is left out.
 */

#ifndef BLEAKHOLD_MARKS_H
#define BLEAKHOLD_MARKS_H

#include "BleakholdMarksRules.h"
#include "BleakholdMessages.h"

#include <atomic>
#include <cstdint>
#include <mutex>
#include <unordered_map>
#include <utility>
#include <vector>

class Player;

namespace Bleakhold
{
    class Marks
    {
    public:
        static Marks& Instance();

        // ---- lifecycle (world thread) ----
        void LoadConfig();                         // from Mgr::LoadConfig, outside the Mgr lock
        void OnStartup();                          // from BleakholdWorldScript::OnStartup, before Data::LoadAll
        void LoadCatalogue();                      // from Data::LoadAll and Data::ReloadWorld, before the definitions
        void FillDefinitions(Definitions& defs);   // DEF N (Data::RebuildDefinitions), with BleakholdUi.Marks.Enable
        void Update(uint64_t nowMs);               // from Mgr::Update: the deltas of the tick, a changed feature
        bool FeatureFor(Player* player) const;     // Enable, a race-sex offered, not GmOnly or a game master
        static bool IsMarksTopic(Topic topic) { return topic == Topic::MarksList || topic == Topic::MarksMe; }

        // ---- protocol (world thread; registered in Data::RegisterDefaults) ----
        void HandleSet(Player* player, Intent const& intent);       // MARKSET
        void Provide(Player* player, TopicRequest const& request);  // GET MARKS, MARKME
        void OnHello(Player* player);              // MARKME, then a full MARKS list

        // ---- hooks (world thread) ----
        void OnLogin(Player* player);              // the row; a MARK to everyone else when the player has an entry
        void OnLogout(Player* player);             // a removal MARK when they had one
        void OnDeleteCharacter(uint32_t lowGuid);  // the row goes

        // ---- status (.bleakhold status) ----
        struct Status { bool enable = false, gmOnly = true; std::size_t offered = 0, rows = 0, goodRows = 0, online = 0, listed = 0; };
        Status GetStatus();

    private:
        Marks() = default;

        struct Online
        {
            uint32_t race = 0, sex = 0, classId = 0;
            bool gameMaster = false;
            MarksRules::Stored stored;
            uint32_t listId = 0;               // the last MARKS list sent to this player
        };

        Online& OnlineOf(Player* player);      // loads the row the first time (lock held)
        MarksRules::Choice AppliedLocked(Online const& o) const;
        bool OwnerFeatureLocked(Online const& o) const;
        MarkEntry EntryLocked(uint32_t lowGuid, Online const& o) const;
        bool ListedLocked(uint32_t lowGuid, Online const& o) const;
        MarkMe MarkMeLocked(Online const& o, uint32_t now) const;
        void SendMarkMe(Player* player);
        void SendList(Player* player);
        void QueueDelta(uint32_t lowGuid, bool login);
        void EnsureTables();
        void FeatureMayHaveChanged();          // lock held: a new HELLO and new lists on the next tick when it did
        void Save(Player* player, uint32_t lowGuid, MarksRules::Stored const& row, uint32_t price);

        mutable std::mutex _lock;
        MarksRules::Settings _cfg;
        MarksRules::Catalogue _cat;
        std::unordered_map<uint32_t, Online> _online;     // by GUID counter
        std::unordered_map<uint32_t, bool> _deltas;       // GUID counter -> it is a login (not sent to that player)
        std::unordered_map<uint32_t, std::pair<uint32_t, uint32_t>> _gone;   // logged out this tick: race, sex
        bool _startupDone = false;
        bool _tablesDone = false;
        bool _resendPending = false;           // MARKME and a full list to everyone with the bit on the next tick
        bool _helloPending = false;            // a new HELLO first (the bit may have changed for someone)
        std::atomic<bool> _featureOn{ false }; // Enable and a race-sex offered
        std::atomic<bool> _gmOnly{ true };
        bool _lastFeatureOn = false, _lastGmOnly = true;
    };
}

#endif
