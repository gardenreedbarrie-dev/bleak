# mod-bleakhold-ui

The server half of the Bleakhold UI: an [AzerothCore](https://www.azerothcore.org) module that talks to
the Bleakhold interface built into the Bleakhold client (`Interface/AddOns/Bleakhold`).

The client and the server talk with small hidden addon messages (the protocol is in
`docs/BleakholdProtocol.md` of this repository). This module does all of the protocol work for you:

- it reads what players' clients ask for (open a board, join a queue, claim a task, start a key...),
  checks every message strictly, and throws away anything malformed, oversized or too frequent;
- it answers the handshake, keeps the revision counters, and splits and escapes long answers;
- it gives your own systems (Mythic+ keystones, Dungeon Journey, Eclipse Rift, daily and weekly tasks,
  seasons) a small C++ interface: one function per thing the UI shows, and one hook per button;
- it has its own tables for the parts that need no custom system (definitions, week schedule, season
  and war effort, legacy sets, leaderboards, server firsts) and a GM command to test everything;
- it runs a few features entirely on its own: emoji bubbles, dances, cases and camping (campfires, camp
  objects, the warmth and food XP bonus, field repair and the High Elf glide).

It never invents game rules: what a key scores, what the war effort counts, what a task pays, how the
Rift scales is decided by your systems or by rows you write.

**Where to change it:** this folder in the Bleakhold client repository (`Server/mod-bleakhold-ui`) is the
module's only source, so the client and the server always speak the same protocol. The Bleakhold server
repository copies it to its `modules/mod-bleakhold-ui` every hour, without `tests/`
(`.github/workflows/sync-bleakhold-ui.yml` there; the Actions tab runs it at once). A change made in the
server's copy is overwritten by the next sync.

---

## 1. Install

You need an AzerothCore source checkout that you build yourself (current `master`), with the normal
build tools for your system ([AzerothCore install guide](https://www.azerothcore.org/wiki/installation)).

**Step 1. Put the module into AzerothCore's `modules` folder.** The folder must be called
`mod-bleakhold-ui`.

Linux / macOS:

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/SatyPardus/wowdecomp.git bleakhold-src
git -C bleakhold-src sparse-checkout set Server/mod-bleakhold-ui
cp -r bleakhold-src/Server/mod-bleakhold-ui azerothcore-wotlk/modules/mod-bleakhold-ui
```

Windows: download this repository, then copy the folder `Server\mod-bleakhold-ui` into
`azerothcore-wotlk\modules\` (so you have `azerothcore-wotlk\modules\mod-bleakhold-ui\src\...`).

(Use the address of the Bleakhold repository you got the client from if it is not the one above.)

**Step 2. Re-run CMake and build**, exactly as you built AzerothCore before (same options). CMake finds
new modules only when it runs again. Keep the default `-DMODULES=static`.

```bash
cd azerothcore-wotlk/build
cmake ..            # with the options you always use
make -j$(nproc)     # or: cmake --build . --config Release
make install        # if you install your server
```

You should see `mod-bleakhold-ui` in CMake's list of modules.

**Step 3. Database.** The module has two SQL folders:

| Folder | Database | What it creates |
|---|---|---|
| `data/sql/db-world/` | world (`acore_world`) | the definition tables, with the UI's own names and texts filled in, and the case tables (empty) |
| `data/sql/db-characters/` | characters (`acore_characters`) | leaderboards, server firsts, war effort points |

Nothing to do if your `worldserver.conf` has `Updates.EnableDatabases = 7` (the default): the
worldserver applies them itself at the next start. Otherwise import the files by hand, in name order,
into those databases (HeidiSQL: File > Run SQL file). The files can be run again safely; rows you edited
are kept. Rows you delete come back when a module update changes a starting-rows file, so to retire a starting
row, change it instead (for a season, set `state` to 0) or set `BleakholdUi.Season.Id`.

**Step 4. Configuration.** The build installs `mod_bleakhold_ui.conf.dist` next to your other module
configs (Linux: `etc/modules/`, Windows: `configs/modules/`). Copy it to `mod_bleakhold_ui.conf` in the same
folder. Everything works with the defaults; the file explains each option.

Also check that `worldserver.conf` has `AddonChannel = 1` (the default): addon messages, and with them the
whole UI, are switched off otherwise.

**Step 5. Start the worldserver.** The log shows a line like

```
>> Bleakhold UI protocol enabled: data version 1234567, feature bits 24, frames up to 1000 bytes
```

Log in with the Bleakhold client (GM account) and type `.bleakhold status`, then `.bleakhold test all`:
the Activities, Season and Leaderboards windows fill with sample data. `.bleakhold test run` plays a
short sample keystone run with the countdown and the key tracker.

To change names, texts, the week schedule or seasons later: edit the `bleakhold_*` rows, then type
`.bleakhold reload` in game. Players' UIs update by themselves.

---

## 2. What works out of the box, and what needs your systems

| UI part | Out of the box | Needs your system |
|---|---|---|
| Connection, error messages, spam protection | everything | |
| Names and texts (affixes, eras, dungeons and bosses, tasks, chapters, legacy tiers, seasons, ranks, rewards, Mythic levels, extra classes, Rift bosses) | `bleakhold_*` world tables (filled with the UI's built-in texts) | optional: add from your code (`OnDefinitionsLoaded`) |
| Era and affixes of the week | `bleakhold_week_schedule` (empty: add your weeks) | or your Mythic+ rotation |
| Season window: season, war effort bar, contributors, points, ranks | `bleakhold_season`, `bleakhold_war_effort_part`, `bleakhold_war_effort_rank` | the **points** (`WarEffortAdd`); reward states (`SetSeasonRewardSource`) |
| "Hand in" tokens button | config `BleakholdUi.WarEffort.*` (item and points per token) | or your own handler |
| Leaderboards (keys, Rift, Raid Echoes) and your own rank | module tables, paging, filters | the runs (`RecordLeaderboardRun`) |
| Server firsts | module table + `[Server First]` announcement | the events (`RecordServerFirst`) |
| Legacy set window and item tooltips | `bleakhold_legacy_set` (one example row) | "collected" state (`SetLegacyCollectionSource`), the outfit button |
| Chat tags `[Queue]` `[Record]` `[Raid Legacy]` `[Server First]` `[Season]` | `Announce()` and `.bleakhold announce` | when to announce |
| Keystone timer, bosses, deaths, enemy forces, end screen | the run tracker (heartbeats, `/reload` recovery, DBM pull timer) | the events of your Mythic+ system |
| Keystone, key mode, weekly best | | `SendKeyState`, `KMODE`/`KSTART`/`KCANCEL` handlers |
| Dungeon Journey board, bounty, queue and group proposals | | `BoardSnapshot`, `QueueStatus`, `QJOIN`/`QLEAVE`/`QREPLY`/`BCLAIM` handlers |
| Eclipse Rift | | `RiftStatus`, `RiftEnded`, `QJOIN` with kind `R` |
| Bleakhold Royale (protocol section 17) | the protocol: `QJOIN` kind `B`, `RDROP`/`RDEPLOY`/`RSPEC` with their rate limits, `GET ROYS`/`ROYM`, the `ROYS ROYM ROYO ROYK ROYV ROYE` encoders, `[Royale]` chat tag; `ERR royale_off` while feature bit 4096 is off; no `GLIDE` in battlegrounds | the match (mod-bleakhold): `SetFeature(FeatureRoyale, true)`, the handlers and providers, the `SendRoyale*` pushes |
| Daily and weekly tasks, Mythic Coins, Shards | | `SendTasks`, `TaskProgress`, `SendWeek`, `TCLAIM`/`TREROLL` handlers |
| Collections counts | | `SendCollections` |
| Emoji bubbles (Animations tab, emote wheel, `/bh emoji`) | everything: the module checks `EMOJI` and shows the emoji over the player's head to everyone nearby; config `BleakholdUi.Emoji.*` | nothing (players need the Bleakhold client to see the bubbles) |
| Dances (Animations tab, emote wheel, `/bh dance`, each dance's own command) | everything: the module checks `DANCE`, starts the stock dance (emote state) and tells everyone nearby which Bleakhold dance it is, again at every loop; config `BleakholdUi.Dance.*` | nothing (players need the Bleakhold client to see the dances; stock clients see the stock dance) |
| Camping (Make camp button and `/camp`, the Camp frame at a fire, camp objects, Pack up, Repair and `/repair`, the High Elf glide) | everything: the module lights the camp fire (`CAMP M`, a script-free bonfire that goes out by itself), counts every lit fire (camp fires, Basic Campfires players light, `BleakholdUi.Camp.ExtraFireEntries`), lets players rest there like at an inn, settles them after a minute (camp object buffs, Campfire Warmth), places and removes camp objects (`CAMP O`, `CAMP P`), adds the warmth and Well Fed XP bonus, repairs (`REPAIR`), glides (`GLIDE`) and keeps the client's `CAMPST` up to date; config `BleakholdUi.Camp.*`, `Glide.*`, `Repair.*` | nothing. Check the default buff spells in game once (`BleakholdUi.Camp.Profession.*`, `Glide.Spell`: they were chosen without the client's Spell.dbc) |
| Cases (right-click a case item: the case window with its rewards and chances, Unlock and the reel) | everything: the module answers `GET CASES` / `GET CASE`, checks `CASEOPEN` (the case, its key, bag room), rolls the reward by weight, swaps the case for it, answers `UNBOX` and announces rare rewards (`[Case]`); config `BleakholdUi.Case.*` | the cases: rows in `bleakhold_case` and `bleakhold_case_reward` (see `data/sql/db-world/02_bleakhold_case_tables.sql`), and the case items themselves (any item, no spell needed) |

Buttons whose system is not connected yet answer the player with "This is not available on this realm
yet." Set `BleakholdUi.Feature.*` in the config when a system goes live (the UI hides what is not).

---

## 3. Connecting your systems (for your developer)

Everything is in one header, `src/BleakholdUi.h`, namespace `Bleakhold::Ui`. Include it from your own
module (all modules are built into one library, so the include path is already set):

```cpp
#include "BleakholdUi.h"
using namespace Bleakhold;
```

Two rules cover everything:

1. **Push state when it changes**, with the matching `Send...` function. The module remembers the last
   state per player and answers the client's requests with it, so you do not have to answer requests.
   Pushing before the player's UI has connected is fine (it is remembered, not sent).
2. **Handle intents.** A handler receives what the player asked for. It is an untrusted request: check
   that the player may do it right now, make it idempotent (a second claim must not pay twice), and
   answer refusals with `Ui::Refuse(player, intent, "code", "Sentence for the player.")`.

All functions can be called from any thread (map scripts included). Your handlers run on the world
thread. Register handlers once at startup, for example in your script loader:

```cpp
void AddMySystemsScripts()
{
    Ui::OnIntent(IntentType::TaskClaim, &MyTasks::OnClaim);
    // ...
}
```

### 3.1 Daily and weekly tasks, Mythic Coins, Shards

```cpp
// Send the whole task list on login, after a reset, and whenever the list changes.
void MyTasks::SendAll(Player* p)
{
    TaskList list;
    list.freeRerolls = FreeRerollsLeft(p);
    list.rerollCost = 500000;                       // copper
    list.rerollCurrency = Currency::Copper;
    for (MyTask const& t : TasksOf(p))
    {
        Task x;
        x.uid = t.id;                               // your id: TCLAIM / TREROLL bring it back
        x.kind = t.weekly ? TaskKind::Weekly : TaskKind::Daily;
        x.templateId = t.templateId;                // name/text from bleakhold_task_template
        x.have = t.progress;
        x.need = t.goal;
        x.rewardKind = RewardKind::MythicCoins;
        x.rewardAmount = t.coins;
        x.state = t.claimed ? TaskState::Claimed : (t.progress >= t.goal ? TaskState::Claimable : TaskState::Open);
        list.tasks.push_back(x);
    }
    Ui::SendTasks(p, list);
}

// Progress of one task (shows the "task done" toast when it becomes claimable).
Ui::TaskProgress(player, task.id, task.progress, task.progress >= task.goal ? TaskState::Claimable : TaskState::Open);

// The Claim button.
Ui::OnIntent(IntentType::TaskClaim, [](Player* p, Intent const& in) {
    MyTask* t = MyTasks::Find(p, in.taskUid);
    if (!t || t->claimed || t->progress < t->goal)
        return Ui::Refuse(p, in, "not_claimable", "That task cannot be claimed yet.");
    t->claimed = true;                              // mark first, then pay: a repeat finds it claimed
    MyTasks::Pay(p, *t);
    Ui::TaskProgress(p, t->id, t->progress, TaskState::Claimed);
    MySeason::SendWeek(p);                          // coins changed
});
Ui::OnIntent(IntentType::TaskReroll, [](Player* p, Intent const& in) { /* check, replace, then MyTasks::SendAll(p) */ });

// Weekly counters (Activities header).
WeekState w;
w.keysTimed = 4; w.raidEchoes = 1; w.riftBestFloor = 18; w.mythicCoins = 2140; w.mythicCoinsCap = 5500; w.shards = 1260;
Ui::SendWeek(player, w);
```

### 3.2 Mythic+ keystones

```cpp
// The player's keystone (bag, login, after a run, after KMODE).
KeyState k;
k.dungeonId = 602; k.level = 8; k.affixIds = { 1, 3, 4 }; k.mode = 2;      // 0 Normal, 1 Heroic, 2 Mythic
k.weeklyBestLevel = 9; k.weeklyBestDungeonId = 599; k.keystoneItemId = 900001; k.maxLevel = 15;
Ui::SendKeyState(player, k);

Ui::OnIntent(IntentType::KeyMode, [](Player* p, Intent const& in) { MyMythic::SetMode(p, in.mode); /* + SendKeyState */ });

// KSTART: the module already checked that the player leads the group (or is alone).
Ui::OnIntent(IntentType::KeyStart, [](Player* p, Intent const& in) {
    if (!MyMythic::CanStart(p))                     // keystone, inside the dungeon, nobody in combat...
        return Ui::Refuse(p, in, "cannot_start", "Everyone must be inside the dungeon.");
    Ui::KeyRunInfo info;
    info.dungeonId = p->GetMapId(); info.level = 8; info.affixIds = { 1, 3, 4 };
    info.countdownMs = 10000; info.timeLimitSec = 1800; info.forcesMax = 100; info.chestSec = { 1260, 1440 };
    uint32 runId = Ui::KeyRunStart(info, MyMythic::GroupMembersInside(p), p);   // countdown on every client
    MyMythic::BeginCountdown(p, runId);             // root the group, start your timer
});
Ui::OnIntent(IntentType::KeyCancel, [](Player* p, Intent const& in) {
    if (uint32 run = MyMythic::CountdownOf(p))
        Ui::KeyAbandoned(run);                      // also cancels the DBM bar
});

// Then, from your Mythic+ code (map threads are fine):
Ui::KeyTimerStart(runId);                           // countdown over
Ui::KeyBossKilled(runId, 2);                        // second boss in the order of bleakhold_dungeon.bosses
Ui::KeyEnemyForces(runId, 64);                      // of forcesMax
Ui::KeyDeath(runId, 5);                             // one death and the penalty you apply (seconds)

KeyRunEnd end;
end.result = KeyRunResultId::InTime; end.timeMs = 1453000; end.keyDelta = 1; end.newDungeonId = 599; end.newLevel = 9;
Reward chest; chest.kind = RewardKind::Text; chest.text = "Spoils chest"; end.rewards.push_back(chest);
Ui::KeyCompleted(runId, end);                       // end screen; then send the new KeyState and WeekState

// Leaderboard and announcements.
Ui::LeaderboardEntry e;
e.board = Board::Keys; e.dungeonId = 602; e.value = 8; e.timeSec = 1800 - 1453; e.members = groupPlayers;
Ui::RecordLeaderboardRun(e);
Ui::Announce(Ui::AnnounceTag::Record, "Halls of Lightning +8 timed in 24:13 by Aldric's group");
Ui::RecordServerFirst("key-15-timed", "key", "First timed +15", "Dalia's group");   // once ever, announced
```

The tracker sends the run state on every event and every 15 s, answers a `/reload` in the middle of a run,
and (with `BleakholdUi.KeyRun.ServerPullTimer = 1`) sends the DBM pull timer from the leader.

### 3.3 Dungeon Journey board, bounty and queue

```cpp
BoardState b;
b.shards = 1260; b.bountyId = 55; b.bountyDungeonId = 189; b.bountyState = BountyState::Claimable;
b.bountyRewardText = "50 Shards"; b.firstRunBonus = true;
BoardDungeon d;
d.dungeonId = 389; d.tierBits = 1 | 2 | 4;          // Normal, Veteran, Elite unlocked
d.bestScore = 900; d.bestTier = 1; d.recordScore = 2400; d.recordName = "Aldric"; d.locked = false;
b.dungeons.push_back(d);                            // chapter/levels come from bleakhold_dungeon if left empty
Ui::BoardSnapshot(player, b);

Ui::OnIntent(IntentType::BountyClaim, [](Player* p, Intent const& in) { /* in.bountyId: today's? completed? not claimed? */ });

Ui::OnIntent(IntentType::QueueJoin, [](Player* p, Intent const& in) {
    // in.queueKind (Dungeon / Rift), in.activityId (map id, 0 for the Rift), in.tier (0-3),
    // in.roles (RoleTank | RoleHealer | RoleDamage), in.groupSize (1 = enter alone)
    if (MyQueue::IsQueued(p))
        return;                                     // idempotent: already queued, nothing to do
    MyQueue::Join(p, in);
    QueueState q;
    q.state = QueueStateId::Queued; q.kind = in.queueKind; q.activityId = in.activityId; q.tier = in.tier;
    q.size = in.groupSize; q.estWaitSec = 300; q.bandMin = 13; q.bandMax = 18;
    Ui::QueueStatus(p, q);
    Ui::Announce(Ui::AnnounceTag::Queue, p->GetName() + " is looking for a group: Ragefire Chasm");
});
Ui::OnIntent(IntentType::QueueLeave, [](Player* p, Intent const&) { MyQueue::Leave(p); /* + QueueStatus state 0 */ });
Ui::OnIntent(IntentType::QueueReply, [](Player* p, Intent const& in) { MyQueue::Answer(p, in.proposalId, in.accept); });
// A group was found: QueueStatus with state Proposal, proposalId, timeoutSec and one QueueMember per player.
```

### 3.4 Eclipse Rift

```cpp
RiftState r;
r.runId = 8001; r.state = RiftStateId::Running; r.floor = 7; r.bossId = 3; r.elapsedMs = 120000;
r.bestFloor = 18; r.groupSize = 1;                  // leave score/rank empty until your scoring exists
Ui::RiftStatus(player, r);

RiftEnd e;
e.runId = 8001; e.floorReached = 9; e.timeMs = 180000; e.newBest = false;
Ui::RiftEnded(player, e);
// Joining the Rift arrives as QueueJoin with in.queueKind == QueueKind::Rift.
```

### 3.5 Season and war effort

```cpp
// Your systems decide what counts and how much (bleakhold_war_effort_part.part_id):
Ui::WarEffortAdd(player, 1, 25);                    // e.g. 25 points to "Materials"

// Reward states for bleakhold_season_reward rows without points_required:
Ui::SetSeasonRewardSource([](Player* p, uint32 rewardId, SeasonRewardState& out) {
    if (rewardId != 2) return false;
    uint32 n = MyMythic::TimedKeysOfLevel(p, 10);
    out.earned = n >= 20; out.stateText = std::to_string(n) + " / 20";
    return true;
});
```

### 3.6 Collections and legacy sets

```cpp
Ui::SetLegacyCollectionSource(
    [](Player* p, uint32 itemId) { return MyTransmog::HasLook(p, itemId); },
    [](Player* p, uint32 setId) { return MyTransmog::SetComplete(p, setId); });
Ui::LegacyItemCollected(player, 16866, true);       // when a look is collected (tooltip updates)
Ui::OnIntent(IntentType::Outfit, [](Player* p, Intent const& in) { /* in.setId: unlocked? save the outfit */ });

CollectionState c;
c.transmogOwned = 412; c.legacySetsOwned = 3; c.legacySetsTotal = 48;
c.tierHave = { 3, 0, 0, 0, 0, 0, 0 }; c.tierTotal = { 8, 8, 5, 9, 5, 5, 8 };
Ui::SendCollections(player, c);
```

### 3.7 Everything else

```cpp
Ui::Toast(player, ToastKind::Record, "New record", "Halls of Lightning +8 in 24:13", "leaderboards");
Ui::Announce(Ui::AnnounceTag::RaidLegacy, "Aldric found " + itemLink);   // real |Hitem:..|h links are kept
Ui::OnRequest(Topic::Week, [](Player* p, TopicRequest const&) { MySeason::SendWeek(p); });  // compute on request instead
Ui::OnDefinitionsLoaded([](Definitions& d) { /* add dungeons, affixes... from your own tables */ });
Ui::SetResetTimesSource([] { return std::make_pair(MyTasks::NextDaily(), MyTasks::NextWeekly()); });
bool hasUi = Ui::HasAddon(player);
// Emoji bubbles work out of the box (BleakholdUi.Emoji.*). The module applies the cooldown and
// BleakholdUi.Emoji.Enable before any handler. Your own handler replaces the rest of the module's
// (Data::Emoji in src/BleakholdData.cpp), so keep its checks: the id is in the catalogue (BleakholdEmoji.h,
// included by BleakholdUi.h), the player is in the world and not muted (the core's Player.h).
Ui::OnIntent(IntentType::Emoji, [](Player* p, Intent const& in) {
    if (in.emojiId >= EmojiCatalogueCount || !p->IsInWorld() || !p->CanSpeak() || MyArena::InMatch(p))
        return Ui::Refuse(p, in, "unavailable", "You cannot use emojis here.");
    p->SendPlaySpellVisual(Ui::EmojiKit(in.emojiId));
});
// Dances work out of the box too (BleakholdUi.Dance.*); a handler of your own keeps the checks of Data::Dance
// (catalogue, alive, not in combat, mounted, moving or casting), sets EMOTE_STATE_DANCE and sends
// Ui::DanceKit(in.danceId). The module's loop kits (section 14) only follow its own handler's dancers.
```

### 3.8 Function reference

| Server message | Function | Remembered for the client's requests |
|---|---|---|
| WEEK | `SendWeek(player, WeekState)` | yes |
| ERA | `SendEra(player, EraState)` (default: `bleakhold_week_schedule`; `SetWeeklyBonusDone`) | yes |
| TASKS / TASK | `SendTasks(player, TaskList)` / `TaskProgress(player, uid, have, state)` | yes |
| KEY | `SendKeyState(player, KeyState)` | yes |
| BOARD | `BoardSnapshot(player, BoardState)` | yes |
| QUEUE | `QueueStatus(player, QueueState)` | yes |
| MPS / MP / MPE | `KeyRunStart`, `KeyTimerStart`, `KeyBossKilled`, `KeyEnemyForces`, `KeyDeath`, `KeyCompleted`, `KeyAbandoned`, `KeyRunAddMember`, `KeyRunSync` (or the low-level `SendKeyRunStart/State/End`) | the run tracker |
| RIFT / RIFTE | `RiftStatus(player, RiftState)` / `RiftEnded(player, RiftEnd)` | RIFT: yes |
| COLL | `SendCollections(player, CollectionState)` | yes |
| SET | `SendLegacySet(player, LegacySet)` (default: `bleakhold_legacy_set`) | |
| LIDX / LCOL | `SendLegacyIndex(player, LegacyIndex)` / `LegacyItemCollected(player, itemId, collected)` | yes |
| SEASON | `SendSeason(player, SeasonState)` (default: season tables + `WarEffortAdd`) | yes |
| LB / LBME | `SendLeaderboard`, `SendLeaderboardMe` (default: `RecordLeaderboardRun` rows) | |
| FIRSTS | `SendFirsts(player, FirstsList)` (default: `RecordServerFirst`) | |
| TOAST | `SendToast(player, Toast)` / `Toast(player, kind, title, subtitle, target)` | |
| ERR | `Refuse(player, intent, code, text)` | |
| DEF, HELLO, PONG | automatic | |
| CAMPST | automatic (the module's camping); `SendCampState(player, CampState)` for a replacement | |
| ROYS / ROYM / ROYO / ROYK / ROYV / ROYE | `SendRoyaleState`, `SendRoyaleMap`, `SendRoyaleObjects`, `SendRoyaleKill`, `SendRoyaleEvent` (the last four also for a list of players), `SendRoyaleResult` | |

Intents (`Ui::OnIntent(IntentType::..., handler)`): `TaskClaim` (`in.taskUid`), `TaskReroll` (`in.taskUid`),
`QueueJoin` (`in.queueKind, activityId, tier, roles, groupSize`), `QueueLeave`, `QueueReply`
(`in.proposalId, in.accept`), `KeyMode` (`in.mode`), `KeyStart`, `KeyCancel`, `BountyClaim` (`in.bountyId`),
`WarEffortHandIn`, `Outfit` (`in.setId`), `LeaderboardQuery` (`in.board, seasonId, dungeonId, classId, page`),
`Emoji` (`in.emojiId`), `Dance` (`in.danceId`), `CaseOpen` (`in.caseItemId, in.caseNonce`), `Camp` (`in.campAct`:
`CampAct::Make`, `Object` with `in.campSkill`, `Pack`), `Glide`, `Repair`, `RoyaleDrop` (`in.dropX, in.dropY`),
`RoyaleDeploy`, `RoyaleSpectate` (`in.spectateDir`). Runtime feature bits: `SetFeature(bit, on)`, `FeatureOn(bit)`.

---

## 4. GM commands

| Command | Who | What |
|---|---|---|
| `.bleakhold status` | GM | players with the UI, message counters, drop reasons, loaded rows |
| `.bleakhold player` | GM | counters of the selected player |
| `.bleakhold camp [show]` | GM | camping state of the selected player (or you): the fire, objects, cooldowns, warmth, XP bonus, Well Fed, glide, repair, the resting flag; and how many fires the realm tracks |
| `.bleakhold camp reset` | GM | clears the selected player's make-camp and glide cooldowns |
| `.bleakhold camp fire` | GM | lights a camp fire for the selected player where they stand (no rules, no cooldown) |
| `.bleakhold test <what>` | GM | sample data to the selected player (or you): `all`, `week`, `era`, `tasks`, `taskdone`, `key`, `board`, `queue`, `run`, `rift`, `collections`, `season`, `leaderboard`, `firsts`, `toast`, `announce`, `defs`, `camp` |
| `.bleakhold reload` | admin | re-read `mod_bleakhold_ui.conf` and the world tables; players get the changes |
| `.bleakhold announce <tag> <text>` | admin | tag: `legacy`, `first`, `season`, `queue`, `record` |
| `.bleakhold debug on\|off` | admin | log every message and every drop reason |

---

## 5. Security

- The client only sends requests ("intents"); every message is checked against the protocol document
  exactly and dropped if anything is off. Client text is never shown to anyone.
- Every player has a message budget (10 at once, 5 per second) and per-button limits; after 200 bad
  or excess messages in a minute the player's UI messages are ignored for a minute and it is logged.
- Players can never send the server's prefix (`BHs`), and the module never relays UI messages to other
  players.
- The module checks the group leader for keystone start/cancel. Everything else (may this player claim
  this task now?) is your handler's job; refuse with `Ui::Refuse`.
- Camping checks everything on the server: no camp in combat, water, the air, cities, dungeons, raids,
  battlegrounds or arenas; fires only count on the continents; camp rest ends the moment combat starts
  (rest allows a logout in combat) and never ends inn, city or guild house rest; the warmth and food bonus is
  added once (after the other modules' XP multipliers, at most `BleakholdUi.Camp.MaxXpPct`); cooldowns
  survive a relog; a repair is all or nothing.
- Camp objects and camp fires are decoration: the module refuses at startup any that has a script, AI or
  trap, or is a crafting station tied to a place (a spell focus outside `BleakholdUi.Camp.AllowedFocusIds`,
  by default anvil, forge and cooking fire), so no Alchemy Lab or Mana Loom can be carried into the field.

## 6. Tests

`tests/run_tests.sh` (Linux, clang or gcc, python3) checks the protocol code against every example in
`docs/BleakholdProtocol.md`, runs the module's messages through the client's real Lua code, runs every
message the client sends through the module's parser, and fuzzes the parser under AddressSanitizer.

## 7. License

GPL-2.0-or-later, like AzerothCore. See `LICENSE`.
