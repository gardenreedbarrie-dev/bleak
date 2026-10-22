# Bleakhold client protocol, version 1

This is the message protocol between the Bleakhold server and the Bleakhold UI addon
(`Interface/AddOns/Bleakhold`). It runs over ordinary WoW 3.3.5a addon messages, so the client needs no
C++ change and a stock AzerothCore core can carry it with one server module.

Client reference implementation: `Interface/AddOns/Bleakhold/Comm.lua` (transport) and `State.lua`
(fields of every server message). Tests: `Tools/UiLint/tests/` (`Tools/UiLint/check.sh` runs them, and
checks that every example in this document parses).

## 1. Security model

The client sends **intents only**: what the player asked for ("claim task 103", "join the queue for
dungeon 189 on Elite", "start my keystone"). It never sends a result, score, timer, reward, loot,
currency amount, kill, completion or any other state.

The server must treat every client message as an untrusted request from a player who may have modified
the addon or typed `/run SendAddonMessage(...)`:

- Parse strictly. Drop anything that does not match this document exactly (unknown op, wrong field
  count, a field that is not a decimal integer where one is required, an out-of-range value, a bad
  frame header). Never reflect raw client text back to anyone.
- Check authority and state for every intent: the task uid belongs to this player and is claimable now;
  the proposal id is this player's open proposal; the player leads the group for `KSTART`/`KCANCEL`;
  the player holds a keystone and is inside the right instance; the bounty is today's and completed; the
  set's outfit is unlocked; and so on. An intent that fails a check changes nothing (answer with `ERR`).
- Make intents idempotent: a repeated `TCLAIM` must not pay twice, a repeated `QJOIN` must not queue
  twice.
- Enforce rate limits yourself (section 8). The client throttles too, but anyone can bypass that.
- Never accept the `BHs` (server) prefix from a client, and never forward client addon messages on the
  `BHs` prefix to anyone.
- `HELLO`'s `addonVer`, `dataVer` and `locale` are only hints for compatibility and language. Never base
  a permission or a reward on them.

Everything the UI shows comes from the server. The client can fake server messages to its own UI (it can
always draw what it likes on its own screen); that has no effect on the server or other players.

## 2. Transport

| Direction | How |
|---|---|
| client to server | `SendAddonMessage("BHc", body, "WHISPER", <own character name>)`. A whisper to yourself is the only addon channel that works solo: `PARTY` is dropped by the client when there is no group, `GUILD` needs a guild. |
| server to client | `SMSG_MESSAGECHAT`, type `CHAT_MSG_WHISPER`, language `LANG_ADDON` (-1), sender = receiver = the player, text `"BHs\t" .. body`. In AzerothCore: `ChatHandler::BuildChatPacket(data, CHAT_MSG_WHISPER, LANG_ADDON, player, player, "BHs\t" + body)` and `player->SendDirectMessage(&data)`. |

The client accepts a server frame only when the prefix is `BHs`, the channel is `WHISPER` and the sender
is the player's own name. Everything else is ignored.

**Receiving client messages (AzerothCore).** A self-whisper reaches `Player::Whisper`, which calls
`OnPlayerCanUseChat(player, CHAT_MSG_WHISPER, LANG_ADDON, msg, receiver)`. In that hook, when
`receiver == player` and `msg` starts with `"BHc\t"`: parse, rate-limit, act, and `return false` so the
whisper is not delivered back. When `msg` starts with `"BHs\t"`: `return false` (clients may not use the
server prefix). Do not use the `AzerothCore\t` prefix; the core reserves it.

**Before the player is in the world** the client sends nothing (`SendAddonMessage` needs an active
player); it sends its first `HELLO` on `PLAYER_ENTERING_WORLD`, and again after every `/reload`. Without
an answer it retries after 10, 30 and 90 seconds, then waits for the next login or `/reload`. Until the
server answers `HELLO`, the client sends nothing else: requests for data (`GET`) wait for the answer and
other intents are refused. Push nothing before the client's `HELLO`.

A character under the GM silence aura (1852) cannot whisper, not even to itself, so the protocol is
silent for that character until the aura ends.

## 3. Frames

```
body = VER SP OP SP SEQ SP PART "/" TOTAL [SP PAYLOAD]
```

| Field | Format |
|---|---|
| `VER` | protocol major version, decimal: `1` |
| `OP` | 2 to 8 uppercase ASCII letters (`TREROLL`, `KCANCEL` and `WEHANDIN` are 7 and 8) |
| `SEQ` | 1 to 6 base-36 digits (`0-9a-z`), a counter per direction, incremented once per message (not per part) and wrapping at 36^6 |
| `PART`/`TOTAL` | decimal 1..99, `PART <= TOTAL` |
| `SP` | exactly one space |
| `PAYLOAD` | optional; when empty the trailing space may be left out |

The client drops a server frame whose `VER` is not 1 (except `HELLO`, so it can learn that it is out of
date), a frame that does not match the header exactly, and any frame containing a NUL byte.

### Size limits

| | Limit | Why |
|---|---|---|
| client to server | whole message `"BHc\t" .. body` at most **255 bytes**, so `body` at most **251** | AzerothCore silently drops longer client chat (`ChatHandler.cpp`). |
| server to client | `body` at most **1000 bytes** per frame; the client drops longer frames | the stock 3.3.5a client copies addon text into 3000-byte stack buffers without a bound (the Bleakhold client bounds the copy); staying far below keeps every client safe. |
| reassembled server payload | at most 64 KiB, at most 99 parts | client memory guard. |

Client messages always fit in one frame (`1/1`). The server must reject a client frame with `TOTAL > 1`.

### Chunking (server to client)

Split a long payload into parts of at most 1000 bytes of body each. Prefer to cut right after a `;`
(record separator); never cut inside a `%XX` escape or inside a UTF-8 sequence. All parts of one message
share `OP` and `SEQ`; send them in order.

The client reassembles by `(OP, SEQ)`:

- duplicate parts are ignored;
- parts may arrive in any order;
- a part with a newer `SEQ` for the same `OP` replaces an unfinished buffer; a part with an older `SEQ`
  is ignored;
- a part whose `TOTAL` differs from the buffer's drops the buffer;
- an unfinished message is dropped 5 seconds after its first part, and the client then asks for that
  topic again with `GET`.

Example: a `BOARD` snapshot in three parts.

```
S> 1 BOARD 3k 1/3 4,1260,55,189,1,50 Shards,1;389,1,13,18,15,900,1,2400,Aldric,0
S> 1 BOARD 3k 2/3 ;36,1,15,21,3,,,,,0
S> 1 BOARD 3k 3/3 ;189,2,30,40,1,1500,0,3100,Brenna,0
```

## 4. Payload encoding

| Separator | Meaning |
|---|---|
| `;` | between records |
| `,` | between fields of a record |
| `:` | between items of a list field |
| `~` | between parts of one list item (a tuple, for example `name~classId`) |

Inside a value, these bytes are escaped as `%XX` (two uppercase hex digits): `%` `;` `,` `:` `~` `|`
and every byte below 0x20 plus 0x7F. `%00` (NUL) is never allowed; the client treats a malformed escape as
a missing value. Text is UTF-8; the client replaces invalid UTF-8 and control characters and shows `|`
literally (it can never start a colour, texture or link code).

Numbers are decimal integers with an optional minus sign. No decimals, exponents, hex, `nan` or `inf`:
the client treats those as missing. Booleans are `0`/`1`. An **empty field means missing**; the client
uses a default. Fields are positional and only ever appended in later versions: the client ignores extra
fields, extra records and unknown ops, so the server may add fields at the end at any time.

Records the client splits are capped (500 records per message, 40 fields, 64 list items) and every value is
clamped to a sane range, so garbage cannot break the UI. A message whose first record is a header (`LIDX`, a
`DEF` kind) therefore carries at most 499 entries after it. The server should still send clean data.

## 5. Revisions (snapshots and deltas)

These topics are revisioned. The first field of the first record of every message of the topic is `rev`.

| Topic | Snapshot op | Delta ops |
|---|---|---|
| WEEK | `WEEK` | |
| ERA | `ERA` | |
| TASKS | `TASKS` | `TASK` |
| KEY | `KEY` | |
| BOARD | `BOARD` | |
| QUEUE | `QUEUE` | |
| COLL | `COLL` | |
| LIDX | `LIDX` | `LCOL` |
| SEASON | `SEASON` | |

- Keep one `rev` counter per player and topic. Every snapshot or delta you send for a topic carries the
  next value (+1).
- A **snapshot** replaces the client's copy of the topic and sets its `rev`, whatever the old value
  (so a server restart may start again at 1). A snapshot without a valid `rev` is dropped.
- A **delta** is applied only if its `rev` is exactly the client's `rev + 1`. An older or equal `rev` is
  ignored as a duplicate. A gap, or a delta before any snapshot, makes the client send `GET <topic>`;
  answer with a snapshot.
- Unrevisioned ops (`MPS`, `MP`, `MPE`, `RIFT`, `RIFTE`, `SET`, `LB`, `LBME`, `FIRSTS`, `DEF`, `TOAST`,
  `ERR`, `HELLO`, `PONG`) are full states or events; each one stands alone.

Push a new snapshot or delta whenever something changes (task progress, queue state, keystone, run
events). The client also asks with `GET` when a window opens; answer every `GET` with the current
snapshot even if nothing changed.

## 6. Client to server: intents

Every field is a decimal integer, a one-letter enum or a short token (`[A-Za-z0-9_.-]`, used only by
`HELLO`). The client never sends free text.

| Op | Fields | Meaning |
|---|---|---|
| `HELLO` | `proto, addonVer, dataVer, locale` | handshake: protocol major (1), addon version token, the `dataVer` of the definitions the client has cached (0 = none), client locale (`enUS`, ...) |
| `GET` | records of `topic[,arg...]`, 1 to 8 records | send the current state of these topics |
| `TCLAIM` | `uid` | claim the reward of task `uid` |
| `TREROLL` | `uid` | replace task `uid` (a daily task that is still open); the server decides if it is free or what it costs |
| `QJOIN` | `kind, activityId, tier, roles, size` | join the queue. `kind`: `D` dungeon board, `R` Eclipse Rift. `activityId`: dungeon id (0 for the Rift). `tier`: 0 Normal, 1 Veteran, 2 Elite, 3 Nightmare. `roles`: bit mask 1 tank, 2 healer, 4 damage. `size`: wanted group size 1..5 (1 = enter alone, no matchmaking) |
| `QLEAVE` | | leave the queue |
| `QREPLY` | `proposalId, accept` | answer a group proposal (1 accept, 0 decline) |
| `KMODE` | `mode` | set the dungeon mode for the next instance: 0 Normal, 1 Heroic, 2 Mythic (replaces the Mythic choice in the portrait Dungeon Difficulty menu, which the addon leaves alone) |
| `KSTART` | | start the keystone (group leader, inside the dungeon) |
| `KCANCEL` | | cancel the start countdown (group leader) |
| `BCLAIM` | `bountyId` | claim today's bounty |
| `WEHANDIN` | | hand in spare war effort tokens (the server counts them) |
| `OUTFIT` | `setId` | save the unlocked outfit of a legacy set |
| `LBQ` | `board, seasonId, dungeonId, classId, page` | leaderboard page. `board`: `K` Mythic keys, `R` Eclipse Rift, `E` Raid Echoes, `F` server firsts. 0 = all for `dungeonId`/`classId`. `page` from 1 |
| `PING` | `nonce` | answer with `PONG` |

`GET` topics and what to send back:

| Topic | Args | Answer |
|---|---|---|
| `WEEK` `ERA` `TASKS` `KEY` `BOARD` `QUEUE` `COLL` `LIDX` `SEASON` `FIRSTS` | | the op of the same name |
| `MPLUS` | | `MPS` then `MP` if the player is in a key run (or its countdown); nothing otherwise |
| `RIFT` | | `RIFT` |
| `SET` | `tier, classId` | `SET` for that legacy tier and class |
| `DEF` | `0` (all kinds) | every `DEF` kind, then `DEF Z` |

Examples:

```
C> 1 HELLO 1 1/1 1,1.0.0,0,enUS
C> 1 GET 2 1/1 WEEK;ERA;TASKS;KEY;QUEUE;MPLUS;LIDX
C> 1 GET 3 1/1 SET,1,2
C> 1 TCLAIM 4 1/1 103
C> 1 TREROLL 5 1/1 101
C> 1 QJOIN 6 1/1 D,389,2,4,3
C> 1 QJOIN 7 1/1 R,0,0,4,1
C> 1 QREPLY 8 1/1 77,1
C> 1 QLEAVE 9 1/1
C> 1 KMODE a 1/1 2
C> 1 KSTART b 1/1
C> 1 KCANCEL c 1/1
C> 1 BCLAIM d 1/1 55
C> 1 WEHANDIN e 1/1
C> 1 OUTFIT f 1/1 201
C> 1 LBQ g 1/1 K,1,0,0,2
C> 1 PING h 1/1 12345
```

## 7. Server to client

Field lists are in order. "list" is a `:`-separated field; "tuple" items use `~`. Ids are the server's
own: dungeon ids are map ids, class ids are ChrClasses ids (1-9 and 11 for the stock classes; the server
may define more with `DEF X`), item ids are item template entries.

### HELLO (answer to the client's HELLO)

`proto, minProto, serverEpoch, utcOffsetMin, dataVer, featureBits, seasonId, dailyResetEpoch, weeklyResetEpoch, realmName, siteUrl`

- `minProto` higher than the client's protocol: the client shows "out of date" and sends nothing more.
- `serverEpoch`: server Unix time now; the client keeps the offset to its own clock. Countdowns run on the
  client's `GetTime()`.
- `utcOffsetMin`: realm time zone, for showing the weekly reset as realm time.
- `dataVer`: version of the server's definitions (section 7, `DEF`). When it differs from the client's
  cache the client sends `GET DEF,0`.
- `featureBits`: 1 Rift scoring live, 2 Shards live, 4 the server sends the DBM pull timer itself
  (section 9), 8 season live, 16 leaderboards live, 32 collections live.
- `dailyResetEpoch`/`weeklyResetEpoch`: the next resets (Unix time).
- `siteUrl`: shown for copying under the leaderboards (there is no web browser in game).

```
S> 1 HELLO 1 1/1 1,1,1792648725,60,7,58,1,1792674645,1792907925,Bleakhold,bleakhold.com
```

### PONG

`nonce, serverEpoch`

```
S> 1 PONG 2 1/1 12345,1792648730
```

### ERR (an intent was refused)

`op, seq, code, text` - the refused op, the client `SEQ` of that message, a machine code, a sentence for
the player (shown in the window and in the error frame).

```
S> 1 ERR 3 1/1 TCLAIM,4,not_claimable,That task cannot be claimed yet.
```

### DEF (definitions: names and texts)

The client has built-in fallback names, but the server is the source of truth. First record:
`kind, dataVer`. Following records depend on the kind:

| Kind | Record |
|---|---|
| `A` affix | `id, name, text` |
| `E` era | `id, name, text, legacyTier` |
| `T` task template | `id, title, text` |
| `B` weekly bonus | `id, title, text` |
| `C` journey chapter | `id, name, text` |
| `D` dungeon | `id, name, chapter, lvlMin, lvlMax, bosses (list, kill order), timeLimitSec (keys)` |
| `L` legacy tier | `id, label, raids, eraId, sources (list of dungeon ids), lvlMin, lvlMax, echoBoss, pieceTotal` |
| `S` season | `id, name, text, state (0 past, 1 current, 2 upcoming)` |
| `K` war effort rank | `id, name` |
| `W` season reward | `id, name, requirementText` |
| `M` mythic level | `level, text` (the Keys tab ladder; level 0 is Mythic 0) |
| `X` extra class | `id, name, token, colorHex, shortLabel` |
| `R` Rift boss | `id, name` |
| `Z` end | header only: `Z, dataVer` |

Send `DEF Z,<dataVer>` after the last kind: the client keeps the definitions for that `dataVer` only once
the set is complete.

```
S> 1 DEF 4 1/1 A,7;1,Fortified,Non-boss enemies have more health and hit harder.;3,Bolstering,When a non-boss enemy dies%2C its allies nearby grow stronger.
S> 1 DEF 5 1/1 D,7;602,Halls of Lightning,5,77,80,General Bjarngrim:Volkhan:Ionar:Loken,1800
S> 1 DEF 6 1/1 Z,7
```

### WEEK (revisioned)

`rev, keysTimed, raidEchoes, riftBestFloor, mythicCoins, mythicCoinsCap, shards`

```
S> 1 WEEK 7 1/1 1,4,1,18,2140,5500,1260
```

### ERA (revisioned)

`rev, eraId, nextEraId, affixIds (list), weeklyBonusId, weeklyBonusDone`

```
S> 1 ERA 8 1/1 1,7,3,1:3:4,1,0
```

### TASKS (revisioned snapshot) and TASK (delta)

First record: `rev, freeRerolls, rerollCost, rerollCurrency` (`G` copper, `C` Mythic Coins). Then one
record per task:

`uid, kind (D daily | W weekly), templateId, have, need, rewardKind, rewardAmount, rewardItemId, state, title, text, rewardText`

- `rewardKind`: `C` Mythic Coins, `S` Shards, `I` item (`rewardItemId`), `G` copper, `T` text only.
- `state`: 0 open, 1 done and claimable, 2 claimed. A task going from 0 to 1 shows the "task done"
  toast. A weekly task in state 1 gets a Claim button too.
- `title`, `text`, `rewardText` override the template and the generated reward text when not empty.

`TASK`: `rev, uid, have, state` (a delta for one task).

```
S> 1 TASKS 9 1/1 1,1,500000,G;101,D,1,0,1,C,20,,0;102,D,2,14,20,I,1,40752,0,,,1 Emblem of Heroism;103,D,3,5,5,C,20,,1;201,W,4,1,3,C,150,,0
S> 1 TASK a 1/1 2,102,20,1
```

### TOAST (show a toast)

`kind, title, subtitle, openTarget` - `kind`: `T` task, `Q` queue, `K` keystone, `R` record, `S` season,
`I` info. `openTarget` (window opened on click): `tasks`, `dungeons`, `keys`, `rift`, `collections`,
`season`, `leaderboards`, or empty.

```
S> 1 TOAST b 1/1 R,New record,Halls of Lightning +8 in 24%3A13,leaderboards
```

### KEY (revisioned)

`rev, dungeonId (0 = no keystone), level, affixIds (list), mode (0 Normal, 1 Heroic, 2 Mythic), weeklyBestLevel, weeklyBestDungeonId, cachesReady, cachesBanked (carried over), keystoneItemId, maxLevel, eraId, depleted`

`keystoneItemId` lets the item tooltip of the player's keystone show the dungeon, level and affixes.

```
S> 1 KEY c 1/1 1,602,8,1:3:4,2,9,599,1,2,900001,15,7,0
```

### BOARD (revisioned): the Dungeon Journey board

First record: `rev, shards, bountyId, bountyDungeonId, bountyState, bountyRewardText, firstRunBonus`

- `bountyState`: 0 no bounty, 1 open, 2 done and claimable (`BCLAIM bountyId`), 3 claimed.
- `firstRunBonus`: 1 while the player's first run of the day (double Shards) is still unused.

Then one record per dungeon:

`dungeonId, chapter, lvlMin, lvlMax, tierBits, bestScore, bestTier, recordScore, recordName, locked`

- `tierBits`: unlocked tiers, 1 Normal, 2 Veteran, 4 Elite, 8 Nightmare.
- `bestScore`/`bestTier`: the player's best run; `recordScore`/`recordName`: the server record.
- `locked`: 1 if the player cannot enter it yet.

(Example: section 3.)

### QUEUE (revisioned)

First record: `rev, state, kind, activityId, tier, size, queuedSec, estWaitSec, proposalId, timeoutSec, bandMin, bandMax`

- `state`: 0 not queued, 1 queued, 2 proposal (a group was found), 3 in the run.
- `bandMin`/`bandMax`: the level band the server matches within (shown as "Matching levels 23-28").
- `queuedSec` and `timeoutSec` count on locally from the moment the message arrives.

Then, for proposals, one record per member: `name, classId, role (1, 2 or 4), accepted (0 pending, 1 yes, 2 no), level`

```
S> 1 QUEUE d 1/1 2,1,D,389,2,3,30,300,,,13,18
S> 1 QUEUE e 1/1 3,2,D,389,2,3,40,,77,40,13,18;Tester,1,4,1,15;Brenna,2,2,0,16
```

### MPS, MP, MPE: a keystone run

`MPS` (run start, sent to every group member when the leader's `KSTART` is accepted; root the group and
start the countdown):
`runId, dungeonId, level, affixIds (list), eraId, countdownMs, timeLimitSec`

`MP` (the whole run state; send on every change and every 15 s as a heartbeat):
`runId, elapsedMs, timeLimitSec, deaths, deathPenaltySec, forcesCur, forcesMax, bossBits, bossKillSec (list), chestSec (list), state`

- `bossBits`: bit `i-1` set when boss `i` (kill order of `DEF D`) is dead; `bossKillSec[i]`: when.
- `chestSec`: optional time thresholds shown as ticks on the timer bar.
- `state`: 0 countdown, 1 running, 2 finished in time, 3 finished over time, 4 abandoned (also used to
  cancel a countdown).
- The tracker counts the time on locally from `elapsedMs` between messages.

`MPE` (run end): first record `runId, result (1 in time, 0 over time, 2 abandoned), timeMs, keyDelta, newDungeonId, newLevel, score`,
then one record per reward: `kind, amount, itemId, text` (kinds as for tasks).

```
S> 1 MPS f 1/1 7001,602,8,1:3:4,7,10000,1800
S> 1 MP g 1/1 7001,1122000,1800,2,10,64,100,1,300,1260:1440,1
S> 1 MPE h 1/1 7001,1,1453000,1,599,9,1840;T,1,,Spoils chest;C,150
```

### RIFT and RIFTE: Eclipse Rift

The Rift's points, rewards and scaling are still open on the server side. The client has no Rift rules:
it shows exactly the fields it gets and leaves empty ones out.

`RIFT`: `runId, state (0 no run, 1 running, 2 over), floor, bossId, bossName, elapsedMs, bestFloor, score, rank, deaths, groupSize`

`RIFTE` (run over): first record `runId, floorReached, timeMs, score, newBest, rank`, then reward records
`kind, amount, itemId, text`.

```
S> 1 RIFT i 1/1 8001,1,7,3,Echo of Nefarian,120000,18,,42,1,1
S> 1 RIFTE j 1/1 8001,9,180000,,0,;C,20
```

### COLL (revisioned): collection counts

`rev, transmogOwned, transmogTotal, laterAgesOwned, laterAgesTotal, legacySetsOwned, legacySetsTotal, tierHave (list), tierTotal (list)`

Mount and pet counts come from the client itself.

```
S> 1 COLL k 1/1 1,412,,0,3771,3,48,3:0:0:0:0:0:0,8:8:5:9:5:5:8
```

### SET: one legacy set (answer to `GET SET,tier,classId`)

`tier, setId, classId, name, collectedBits, outfitUnlocked, itemIds (list), sourceDungeonIds (list), lvlMin, lvlMax, echoBoss, note`

`collectedBits`: bit `i-1` set when the look of item `i` is collected. `outfitUnlocked`: 1 when `OUTFIT`
is allowed.

```
S> 1 SET l 1/1 1,201,1,Battlegear of Might,56,0,16866:16868:16865:16861:16863:16864:16867:16862,229:329:289:429:543,58,61,Ragnaros,
```

### LIDX (revisioned snapshot) and LCOL (delta): legacy item index

For the item tooltip ("Raid Legacy - <era> era", where it drops, look collected). First record: `rev`.
Then one record per legacy item: `itemId, tier, setId, collected`. `LCOL`: `rev, itemId, collected`.

```
S> 1 LIDX m 1/1 1;16864,1,201,1;16866,1,201,0
S> 1 LCOL n 1/1 2,16866,1
```

### SEASON (revisioned)

First record: `rev, seasonId, warEffortPermille, contributors, points, rankId, nextRankId, pointsToNextRank, warEffortTitle, warEffortText, spareTokens`.
Then records tagged by their first field:

- `P, name, permille`: a part of the war effort (up to three are shown);
- `R, rewardId, earned, stateText`: a season reward (`DEF W`), with the progress text ("7 / 20").

```
S> 1 SEASON o 1/1 1,1,620,1284,1240,2,3,260,Breach the Greymane Wall,Fill the bar together.,3;P,Materials,800;P,Bosses and Echoes,550;R,1,1,Earned;R,2,0,7 / 20
```

### LB, LBME, FIRSTS: leaderboards

`LB` (answer to `LBQ`): first record `board, seasonId, dungeonId, classId, page, pages`, then one record
per row: `rank, dungeonId, value, timeSec, dateEpoch, members (list of name~classId), label`.

| Board | `value` | `timeSec` | `label` |
|---|---|---|---|
| `K` Mythic keys | key level | time left (negative = over time) | |
| `R` Eclipse Rift | floor | run time | |
| `E` Raid Echoes | | kill time | boss name |

Page 1 should include ranks 1-3 (the podium). Up to 10 rows per page fit comfortably in a few frames.

`LBME`: the player's own best: `board, rank, topPercent, value, dungeonId, timeSec, barPermille, label`.

`FIRSTS` (answer to `GET FIRSTS` and `LBQ F,...`): one record per server first, newest first:
`kindKey, text, who, dateEpoch`.

```
S> 1 LB p 1/1 K,1,0,0,1,3;1,602,15,300,1792645125,Aldric~1:Brenna~2:Corwin~5:Dalia~8:Eamon~11,;2,599,14,200,1792641525,Fenna~3,
S> 1 LBME q 1/1 K,42,12,9,602,154,580,
S> 1 FIRSTS r 1/1 echo,Echo of Ragnaros defeated,Ironvow,1792562325;key,First timed +15,Dalia's group,1792216725
```

## 8. Rate limits the server must enforce

The client throttles itself (bursts of 6, then 4 messages per second; identical intents within 0.5 s
are sent once; a topic is requested at most every 3 s), but the server must not rely on that. The core
does not throttle addon messages for you (AzerothCore's addon flood check is not reached for
`LANG_ADDON`). Suggested limits per player:

| What | Limit |
|---|---|
| all `BHc` messages | token bucket of 10, refilled at 5 per second; drop the rest silently; after 200 drops in a minute ignore the player's `BHc` for 60 s and log it |
| `HELLO` | 1 per 5 s |
| `GET` | at most 8 records per message; each topic at most once per second |
| `LBQ` | 2 per second |
| `QJOIN`, `QLEAVE`, `QREPLY` | 1 per second each |
| `KSTART`, `KCANCEL`, `KMODE` | 1 per 2 s each |
| `TCLAIM`, `TREROLL`, `BCLAIM`, `OUTFIT`, `WEHANDIN` | 2 per second together; idempotent anyway |

Also bound the work a single message can cause (for example a `GET LIDX` answer is cached per player
rather than rebuilt on every request).

## 9. DBM pull timer (keystone countdown)

When a keystone starts, the countdown is shown by the addon. To give players with Deadly Boss Mods their
usual "Pull in" bar, the group leader's client sends DBM's own pull-timer addon message with prefix
`DBMv4-PT` and body `<seconds>` (for example `10`) on `PARTY` or `RAID`, and `0` when the countdown is
cancelled. A solo player with DBM loaded sends it to themselves as a whisper. This message is only for
DBM; the server relays it like any addon message and must not interpret it.

Alternatively the server can send it itself and set feature bit 4 in `HELLO`; the client then sends
nothing. Send `SMSG_MESSAGECHAT` with `CHAT_MSG_PARTY` (or `CHAT_MSG_RAID`), `LANG_ADDON`, the group
leader as sender and text `DBMv4-PT\t10` to every member (`DBMv4-PT\t0` cancels). DBM ignores pull
timers under 3 seconds and from senders without group rank, so use the leader as the sender.

## 10. Chat announcements

Server-wide announcements are plain `CHAT_MSG_SYSTEM` text starting with one of these tags (one space
after the tag). The addon colours the tag, keeps the rest (including real `|Hitem:` links) as sent, and
lets each chat window hide a tag (`/bh chat`):

| Tag | Use |
|---|---|
| `[Raid Legacy] ` | legacy set drops |
| `[Server First] ` | server firsts |
| `[Season] ` | season and war effort news |
| `[Queue] ` | a group search started (sent to the whole server) |
| `[Record] ` | a new run record |

Without the addon the lines are still readable as plain text.

## 11. Typical flows

**Login.** Client `HELLO` on entering the world; server `HELLO`; client `GET WEEK;ERA;TASKS;KEY;QUEUE;MPLUS;LIDX`
(and `GET DEF,0` if `dataVer` changed); server answers each. Windows ask for their own topics when opened
(`BOARD`, `COLL`, `SET`, `SEASON`, `FIRSTS`, `LBQ`).

**Task.** Progress: `TASK` deltas. Done: `TASK ...,1` (toast). Player clicks Claim: `TCLAIM uid`; server
checks, pays, sends `TASK ...,2` and the new `WEEK`.

**Queue.** `QJOIN` -> `QUEUE state 1` (with the level band) and a `[Queue]` announcement -> group found:
`QUEUE state 2` with members and `proposalId` -> `QREPLY` -> `QUEUE state 3` and teleport -> after the
run (exit portal back to the board) `QUEUE state 0` and a new `BOARD`.

**Keystone.** `KMODE 2`, enter the dungeon, leader `KSTART` -> server checks, roots the group, sends
`MPS` (countdown) and `MP state 0` to everyone (and the DBM message if feature bit 4) -> `MP state 1`
when the timer starts, then `MP` on every change -> end: `MP state 2/3`, `MPE`, new `KEY` and `WEEK`.
`KCANCEL` during the countdown -> `MP state 4`.

## 12. Versioning

Fields and ops are only ever added. A change that old clients cannot read raises the protocol major:
send `HELLO` with the new `proto` and a `minProto` above what old clients have; they stop sending and show
"out of date". Definitions change with `dataVer`.
