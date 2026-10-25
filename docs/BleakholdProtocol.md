# Bleakhold client protocol, version 1

This is the message protocol between the Bleakhold server and the Bleakhold UI addon
(`Interface/AddOns/Bleakhold`). It runs over ordinary WoW 3.3.5a addon messages, so the client needs no
C++ change (except emoji bubbles, section 13, which only the Bleakhold client draws) and a stock
AzerothCore core can carry it with one server module.

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
  `ERR`, `HELLO`, `PONG`, `CASES`, `CASE`, `UNBOX`, `CAMPST`, `ROYS`, `ROYM`, `ROYO`, `ROYK`, `ROYV`, `ROYE`) are
  full states or events; each one stands alone.

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
| `QJOIN` | `kind, activityId, tier, roles, size` | join the queue. `kind`: `D` dungeon board, `R` Eclipse Rift, `B` Bleakhold Royale (section 17). `activityId`: dungeon id (0 for the Rift, the mode id, above 0, for Royale). `tier`: 0 Normal, 1 Veteran, 2 Elite, 3 Nightmare (always 0 for Royale). `roles`: bit mask 1 tank, 2 healer, 4 damage (ignored for Royale). `size`: wanted group size 1..5 (1 = enter alone, no matchmaking; always 1 for Royale) |
| `QLEAVE` | | leave the queue (the Royale queue when the player is in it) |
| `QREPLY` | `proposalId, accept` | answer a group proposal or a Royale ready check (1 accept, 0 decline) |
| `KMODE` | `mode` | set the dungeon mode for the next instance: 0 Normal, 1 Heroic, 2 Mythic (replaces the Mythic choice in the portrait Dungeon Difficulty menu, which the addon leaves alone) |
| `KSTART` | | start the keystone (group leader, inside the dungeon) |
| `KCANCEL` | | cancel the start countdown (group leader) |
| `BCLAIM` | `bountyId` | claim today's bounty |
| `WEHANDIN` | | hand in spare war effort tokens (the server counts them) |
| `OUTFIT` | `setId` | save the unlocked outfit of a legacy set |
| `LBQ` | `board, seasonId, dungeonId, classId, page` | leaderboard page. `board`: `K` Mythic keys, `R` Eclipse Rift, `E` Raid Echoes, `F` server firsts. 0 = all for `dungeonId`/`classId`. `page` from 1 |
| `PING` | `nonce` | answer with `PONG` |
| `EMOJI` | `emojiId` | show emoji `emojiId` above the player's head to everyone nearby (section 13). `emojiId`: 0..255, an index into the emoji catalogue, `Tools/EmojiForge/emojis.json` |
| `DANCE` | `danceId` | dance Bleakhold dance `danceId` until the player moves (section 14). `danceId`: 0..1023, an index into the dance catalogue, `Tools/DanceForge/dances.json` |
| `CASEOPEN` | `caseItemId, nonce` | open one case `caseItemId` from the player's bags (section 15); `nonce` (0..2147483647) comes back in `UNBOX` |
| `CAMP` | `act[, skill]` | camping (section 16). `act`: `M` make camp here, `O` place a camp object at the fire the player is at, `P` pack up the player's fire. `skill` (1..2147483647, a SkillLine id from `CAMPST` `place`) is sent with `O` and only with `O`: `CAMP M`, `CAMP O,164`, `CAMP P` |
| `GLIDE` | | start the glide, a short slow fall (High Elves; section 16) |
| `REPAIR` | | repair everything the player wears and carries in the bags, for the normal cost (section 16) |
| `RDROP` | `x, y` | Bleakhold Royale: set the landing pin (section 17). Integer world yards, -17067..17067 each (they may be negative) |
| `RDEPLOY` | | Bleakhold Royale: open the parachute now (section 17) |
| `RSPEC` | `dir` | Bleakhold Royale spectators: watch another player (section 17). `dir`: 0 the killer (or the first player alive), 1 the next, 2 the previous |

`GET` topics and what to send back:

| Topic | Args | Answer |
|---|---|---|
| `WEEK` `ERA` `TASKS` `KEY` `BOARD` `QUEUE` `COLL` `LIDX` `SEASON` `FIRSTS` | | the op of the same name |
| `MPLUS` | | `MPS` then `MP` if the player is in a key run (or its countdown); nothing otherwise |
| `RIFT` | | `RIFT` |
| `SET` | `tier, classId` | `SET` for that legacy tier and class |
| `DEF` | `0` (all kinds) | every `DEF` kind, then `DEF Z` |
| `CASES` | | `CASES` (section 15) |
| `CASE` | `caseItemId` | `CASE` for that case; nothing when it is not one (section 15) |
| `CAMPST` | | `CAMPST` (section 16) |
| `ROYS` | | `ROYS` then a full `ROYO` while the player is in a Bleakhold Royale match; nothing otherwise (section 17) |
| `ROYM` | | `ROYM` while the player is in a Bleakhold Royale match; nothing otherwise (section 17) |

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
C> 1 EMOJI i 1/1 7
C> 1 DANCE j 1/1 5
C> 1 GET k 1/1 CASES;CASE,990001
C> 1 CASEOPEN l 1/1 990001,7
C> 1 GET m 1/1 CAMPST
C> 1 CAMP n 1/1 M
C> 1 CAMP o 1/1 O,164
C> 1 CAMP p 1/1 P
C> 1 GLIDE q 1/1
C> 1 REPAIR r 1/1
C> 1 GET s 1/1 ROYS;ROYM
C> 1 QJOIN t 1/1 B,901,0,4,1
C> 1 RDROP u 1/1 -412,96
C> 1 RDEPLOY v 1/1
C> 1 RSPEC w 1/1 2
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
  (section 9), 8 season live, 16 leaderboards live, 32 collections live, 64 emoji bubbles live (section 13),
  128 dances live (section 14), 256 cases live (section 15), 512 camping live (campfires, camp objects, warmth,
  the food XP bonus, repair at a camp anvil; section 16), 1024 the High Elf glide live, 2048 blacksmiths repair
  anywhere (section 16), 4096 Bleakhold Royale live (section 17), 8192 the battleground kill announcer live
  (section 18).
- The server may send `HELLO` again at any time, without a client `HELLO`, when its feature bits change (Bleakhold
  Royale turns 4096 on or off at runtime). The client reads it like an answer to its own.
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
the player (shown in the window and in the error frame). `busy` (over an op's rate limit, section 8) can answer
any action intent except `RDEPLOY`, which is never answered; the other codes are listed with each feature (sections
13 to 17).

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
`season`, `leaderboards`, `royale` (the Bleakhold Royale card, section 17), or empty.

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
- Kind `B` (Bleakhold Royale) appends `queued, minPlayers, maxPlayers, accepted, proposalSize, matchesRunning` after
  `bandMax` and never has member records (section 17).

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
| `EMOJI` | 1 per `BleakholdUi.Emoji.CooldownMs` (2.5 s); the addon waits 3.25 s itself |
| `DANCE` | 1 per `BleakholdUi.Dance.CooldownMs` (1 s); the addon waits 1.25 s itself |
| `CASEOPEN` | 1 per `BleakholdUi.Case.CooldownMs` (1 s); the addon waits for `UNBOX` or `ERR` (at most 5 s) |
| `CAMP` | 1 per `BleakholdUi.RateLimit.CampIntervalMs` (1 s), every `act` together |
| `GLIDE` | 1 per `BleakholdUi.RateLimit.GlideIntervalMs` (1 s); the glide itself has a 120 s cooldown (`ERR glide_cooldown`) |
| `REPAIR` | 1 per `BleakholdUi.RateLimit.RepairIntervalMs` (2 s) |
| `RDROP`, `RSPEC` | 1 each per `BleakholdUi.RateLimit.RoyaleIntervalMs` (0.5 s, so 2 per second); the addon waits 0.5 s itself |
| `RDEPLOY` | 1 per `BleakholdUi.RateLimit.RoyaleDeployIntervalMs` (1 s); over it, dropped silently (no `busy`) |

The server drops an action intent that repeats the player's last accepted one of the same op (same fields) within
`BleakholdUi.RateLimit.DuplicateWindowMs` (1 s), except `RSPEC`: "next" twice is two steps.

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
| `[Case] ` | a rare reward from a case (section 15) |
| `[Royale] ` | Bleakhold Royale: the queue filling up, a winner (section 17) |

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

**Bleakhold Royale.** `QJOIN B` -> `QUEUE` state 1 -> ready check (`QUEUE` state 2, `QREPLY`) -> the match: `ROYM`,
`ROYS`, `ROYO`, `ROYK`, `ROYV` -> `ROYE` -> `QUEUE` state 0. The whole flow is in section 17 ("A match").

## 12. Versioning

Fields and ops are only ever added. A change that old clients cannot read raises the protocol major:
send `HELLO` with the new `proto` and a `minProto` above what old clients have; they stop sending and show
"out of date". Definitions change with `dataVer`.

## 13. Emoji bubbles

`EMOJI emojiId` asks the server to show emoji `emojiId` above the player's head for a few seconds, to the
player and everyone nearby. The ids index the emoji catalogue, `Tools/EmojiForge/emojis.json`; the addon
(`EmojiData.lua`) and the module (`src/BleakholdEmoji.h`) get their copies from it, and the client ships
the art as `Interface\Bleakhold\Emoji\EmojiNNN.blp`. Ids go on the wire and saved emote wheels hold the
emoji keys, so the catalogue is append-only: an id or a key is never renumbered, reused or removed.

The server checks, in this order:

| Check | Answer |
|---|---|
| malformed, or `emojiId` above 255 | dropped silently (section 1) |
| the same `emojiId` as the player's last accepted `EMOJI`, within 1 s | dropped silently |
| the player's cooldown (`BleakholdUi.Emoji.CooldownMs`, section 8) has not run out | `ERR` `busy` |
| emoji bubbles are off on the realm (`BleakholdUi.Emoji.Enable = 0`, no feature bit 64) | `ERR` `unavailable` |
| `emojiId` is not in the catalogue | `ERR` `unknown_emoji` |
| the player is not in the world | dropped silently |
| the player is muted (addon messages skip the core's mute check) | `ERR` `muted` |

The module makes the first four checks whoever handles `EMOJI`; a server that replaces the module's handler
(`Ui::OnIntent(IntentType::Emoji, ...)`) keeps the last three itself.

A refused (`busy`) or duplicate `EMOJI` counts as a drop toward the flood limit of section 8, which then
ignores all of the player's `BHc` messages for a while. That is why the addon waits longer than the
server between two emojis.

When every check passes, the server broadcasts `SMSG_PLAY_SPELL_VISUAL` (the guid of the player, kit
`900000 + emojiId`) to the player and everyone who can see them (AzerothCore:
`player->SendPlaySpellVisual(900000 + emojiId)`, which already respects phases, stealth and GM
invisibility).

The Bleakhold client draws kits 900000 to 900255 as an emoji bubble over the unit the guid names, instead
of looking them up in `SpellVisualKit.dbc`; a stock client finds no such kit and ignores the packet. Any
unit can carry the kit, so a server script can show an emoji over a creature too
(`creature->SendPlaySpellVisual(900000 + emojiId)`). This is the one part of the protocol that needs the
Bleakhold client. Like chat from them, the Bleakhold client does not draw emoji bubbles from players on the
viewer's ignore list.

## 14. Dances

`DANCE danceId` asks the server to start Bleakhold dance `danceId` on the player. The ids index the dance
catalogue, `Tools/DanceForge/dances.json`; the addon (`DanceData.lua`) and the module (`src/BleakholdDance.h`) get
their copies from it, and the client ships the clips in `Interface\Bleakhold\Dances\Dances.bdc`. Ids go on the
wire, saved emote wheels hold `dance:<key>` and music files are named after the key, so the catalogue is
append-only: an id or a key is never renumbered, reused or removed.

The server checks, in this order:

| Check | Answer |
|---|---|
| malformed, or `danceId` above 1023 | dropped silently (section 1) |
| the same `danceId` as the player's last accepted `DANCE`, within 1 s | dropped silently |
| the player's cooldown (`BleakholdUi.Dance.CooldownMs`, section 8) has not run out | `ERR` `busy` |
| dances are off on the realm (`BleakholdUi.Dance.Enable = 0`, no feature bit 128) | `ERR` `unavailable` |
| `danceId` is not in the catalogue | `ERR` `unknown_dance` |
| the player is not in the world | dropped silently |
| the player is dead | `ERR` `dead` |
| the player is in combat | `ERR` `in_combat` |
| the player is mounted, on a vehicle or on a flight path | `ERR` `mounted` |
| the player moves, flies, falls or swims | `ERR` `moving` |
| the player casts a spell | `ERR` `casting` |

The module makes the first four checks whoever handles `DANCE`; a server that replaces the module's handler
(`Ui::OnIntent(IntentType::Dance, ...)`) keeps the others itself.

When every check passes, the server stands the player up, sets their emote state to `EMOTE_STATE_DANCE` (10) and
broadcasts `SMSG_PLAY_SPELL_VISUAL` (the guid of the player, kit `910000 + danceId`) to the player and everyone
who can see them (AzerothCore: `player->SetEmoteState(EMOTE_STATE_DANCE)` and
`player->SendPlaySpellVisual(910000 + danceId)`). While the emote state lasts, the server sends the kit again at
the start of every loop of the dance (`DanceLoopMs` in `src/BleakholdDance.h`), so a client that sees the dancer
later starts the dance in step. The core clears the emote state when the player moves, turns or dies, which ends
the dance; the server then stops sending the kit.

A stock client sees the stock dance (the emote state) and ignores the unknown kit. The Bleakhold client plays clip
`danceId` on the unit the guid names for as long as its emote state is `EMOTE_STATE_DANCE` (from a kit that came
first it waits 2.5 s for the state), keeps a dance that is already in step when the loop kit comes, and plays the
dance's music at the unit when `Interface\Bleakhold\Dances\Music\<key>.mp3` (or `.ogg`, `.wav`) exists.
Like chat from them, the Bleakhold client does not show dances of players on the viewer's ignore list. Any unit
can carry the kit, so a server script can make a creature dance too (`creature->SetEmoteState(EMOTE_STATE_DANCE)`
and `creature->SendPlaySpellVisual(910000 + danceId)`, again every loop).

## 15. Cases

A case is an item that holds one of several rewards. Right-clicking one in the bags opens the case window
(the addon knows the case items from `CASES`), which shows every reward the case can give and its chance;
Unlock sends `CASEOPEN caseItemId,nonce`. The server decides everything: it checks the case and its key, rolls the
reward by weight, takes the case (and the key), gives the reward and answers `UNBOX`. The window's spinning
reel only shows where the roll already landed. A case item needs no spell or loot of its own; a stock client
just cannot open it.

`CASES`: one record per case, `caseItemId` (at most 200). Sent for `GET CASES`, and again whenever the list
changes (a reload).

`CASE` (answer to `GET CASE,caseItemId`): the first record is the case, the others its rewards in display
order (at most 60).

`caseItemId, title, text, keyItemId, keyCount`, then per reward `itemId, count, chance, tier`

- `title`: the window's title (the case item's name when the server leaves it empty); `text`: one line under it.
- `keyItemId`, `keyCount`: an item the player needs (and loses) to open the case; empty or 0 for none.
- `chance`: the reward's chance in 1/10000 (`1200` is 12 %); the chances add up to 10000 give or take rounding.
- `tier`: the colour of the reward's card, 0 (poor) to 6 (artifact) like item quality; usually the item's quality,
  but a server may mark a jackpot higher.

`UNBOX` (answer to `CASEOPEN`): `caseItemId, rewardIndex, itemId, count, nonce`. `rewardIndex` is the reward's
position in `CASE`, from 1; `nonce` is the request's. The reward is already in the player's bags when it arrives.
A client that shows a different list (the server reloaded its cases) knows the reward by `itemId`.

`CASES` is empty while `BleakholdUi.Case.Enable = 0`, and the server answers no `GET CASE` then.

The server checks `CASEOPEN`, in this order:

| Check | Answer |
|---|---|
| malformed | dropped silently (section 1) |
| the same `caseItemId,nonce` as the player's last accepted `CASEOPEN`, within 1 s | dropped silently |
| the player's cooldown (`BleakholdUi.Case.CooldownMs`, section 8) has not run out | `ERR` `busy` |
| cases are off on the realm (`BleakholdUi.Case.Enable = 0`, or no case: no feature bit 256) | `ERR` `unavailable` |
| `caseItemId` is not a case | `ERR` `unknown_case` |
| the player is not in the world | dropped silently |
| the player has no such case in the bags | `ERR` `no_case` |
| the case needs a key the player does not have | `ERR` `no_key` |
| any reward the case can give would not fit in the bags (no room, or a unique reward the player has); the case stays | `ERR` `bags_full` |

Every reward must fit before the roll: a refusal that depended on the roll would let a player open the case
again and again until the reward they want comes up. When every check passes, the server rolls the reward, takes
one case and the key from the bags, adds the reward (with the usual "You receive item" message) and sends `UNBOX`
(or, should the core refuse the item after all, `ERR` `failed`, logged for a game master). A reward whose tier is at least the case's announce tier is
told to the realm with a `[Case]` line (section 10).

```
C> 1 GET k 1/1 CASES;CASE,990001
S> 1 CASES 4 1/1 990001;990002
S> 1 CASE 5 1/1 990001,Glaive Case,Unlock it to receive one of the items below.;32837,1,1200,4;32838,1,400,5
C> 1 CASEOPEN l 1/1 990001,7
S> 1 UNBOX 6 1/1 990001,2,32838,1,7
```

## 16. Camping

Camping lets a player make camp in the wild, rest by any lit campfire as at an inn, and set up camp objects of their
professions that buff everyone who settles at the fire. It also carries two small extras: blacksmiths repair anywhere,
and High Elves glide. Each part has its own `HELLO` feature bit and switch: 512 camping (`BleakholdUi.Camp.Enable`),
1024 glide (`BleakholdUi.Glide.Enable`), 2048 field repair (`BleakholdUi.Repair.Enable`). The server decides
everything; `CAMPST` tells the client what it decided, and the client counts its timers down itself.

**Fires.** `CAMP M` lights a camp fire a step in front of the player (`BleakholdUi.Camp.FireEntry`, a WotLK bonfire
that is also a cooking fire) that goes out by itself after `BleakholdUi.Camp.FireDuration` (900 s), also when its
maker logs out. A player has one camp fire: a new one puts out the old one. Every lit fire counts, not just camp
fires: the Basic Campfires players light with cooking (spell 818, game object 29784; not its world spawns) and the
entries of `BleakholdUi.Camp.ExtraFireEntries`. Fires count only on the continents, never in a dungeon, raid,
battleground or arena.

**Resting and settling.** A player is *at a fire* within `BleakholdUi.Camp.Radius` (10 yd) of a lit fire on the same
map and phase, alive, out of combat, not on a flight path or a vehicle, not in a free-for-all PvP area (a world arena
such as Gurubashi) and not between maps. A player at a fire
rests (`R`): rested XP builds up as at an inn, and a logout there counts as an inn logout. Leaving the radius, combat,
death or the fire going out ends that rest at once. Other rest is never touched: inn and city rest go on, and a player
who already rests some other way (a guild house) keeps that rest and gets no camp rest on top. After
`BleakholdUi.Camp.SettleTime` (60 s) at the same fire the player settles (`C`): they get the buff of every camp object
at that fire (for `BleakholdUi.Camp.BuffDuration`, 3600 s, unless the spell is passive or permanent) and Campfire
Warmth for `BleakholdUi.Camp.WarmthDuration` (1800 s). Combat or another fire starts the settle time over. Settling
again starts the warmth and the buffs over; they never add up, and a profession's buff never replaces a higher tier
of the same profession's buff the player already has. A camp object placed at a fire gives its buff at once to the
players already settled there.

**Camp objects.** `CAMP O,skill` places a camp object of the profession `skill` (a SkillLine id) at the fire the
player is at. A fire holds three, one per player. The player places the highest tier their skill reaches
(`BleakholdUi.Camp.TierSkill`: 75, 225, 375 for tiers 1, 2, 3); objects stand around the fire and last as long as it
(objects at a fire that never goes out last `BleakholdUi.Camp.FireDuration`). `CAMP P` puts out the player's fire with
its objects: the fire they stand at when it is theirs (a camp fire, or a Basic Campfire they lit), else their camp
fire wherever it is. Camp objects are decoration: none is a crafting station tied to a place. Only the common stations
of `BleakholdUi.Camp.AllowedFocusIds` (anvil, forge, cooking fire) work at a camp for recipes that need one; the server
refuses any other spell focus as a camp object or camp fire at startup. The professions and their default objects
(`BleakholdUi.Camp.Profession.<Name>` sets the objects and buffs):

| `skill` | Profession | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|---|
| 171 | Alchemy | Apothecary Vials and Bottles | Alchemist's Table | Alchemy set (Apothecary Table, Round) |
| 164 | Blacksmithing | Anvil | Forge | The Great Anvil |
| 333 | Enchanting | Blue Ground Rune | Night Elf Moon Crystal | Rune Circle |
| 202 | Engineering | Lunchbox Tools | Gnome Terminal | Toshley's Turbo Tesla Turret |
| 182 | Herbalism | Small Basket | Herb pile | Large herb pile |
| 773 | Inscription | Rolled Scroll | Open Book | Apothecary Bookcase |
| 755 | Jewelcrafting | Jewelcraft Grinder | Glowy Gem | Twilight Crystal Base |
| 165 | Leatherworking | Leather Shirt on a stand | Meat Rack | Hanging Cloak |
| 186 | Mining | Rock Rubble | Bar stack | Goblin Smelting Pot |
| 393 | Skinning | Fresh Carcass | Skin pile | High Quality Fur |
| 197 | Tailoring | Rug | Clothesline | Dress form (Armor Stand) |
| 185 | Cooking | Cookpot | Potbelly Stove | Clay Oven |
| 129 | First Aid | Bandage Crates | Bandage pile | Hospital Bed |
| 356 | Fishing | Water Bucket | Fish of the Day | Rowboat |

A Blacksmithing object of tier 2 or 3 is a camp anvil: anyone at that fire may `REPAIR`.

**XP bonus.** While Campfire Warmth lasts the player gets `BleakholdUi.Camp.WarmthXpPct` (10) % more XP from kills
and quests, and while they have a Well Fed buff (any food buff; also anywhere else) `BleakholdUi.Camp.FoodXpPct` (5) %.
Together they are at most `BleakholdUi.Camp.MaxXpPct` (25) %. The bonus is added once, to the XP after the core's and
the other modules' own multipliers, and players at the level cap get nothing.

**Field repair.** `REPAIR` repairs everything the player wears and carries in the bags (not the bank) for the normal
repair cost (with the realm's `Rate.RepairCost`; blacksmiths pay `BleakholdUi.Repair.BlacksmithDiscountPct`, 10 %,
less). It is allowed for a blacksmith with at least `BleakholdUi.Repair.MinSkill` (75) skill anywhere (feature 2048)
and for anyone at a fire with a camp anvil (feature 512). It is all or nothing: a player who cannot pay for all of it
pays nothing. The result is a `TOAST` (kind `I`).

**Glide.** `GLIDE` gives a player of a race in `BleakholdUi.Glide.Races` (22, the High Elf) a slow fall for
`BleakholdUi.Glide.Duration` (10 s), every `BleakholdUi.Glide.Cooldown` (120 s), standing or falling. It is a triggered
cast of `BleakholdUi.Glide.Spell` (Slow Fall): no reagent and no spell cooldown on the client. There is no glide in a
battleground or an arena, the Bleakhold Royale map included (section 17).

### CAMPST (the player's camping state)

`state, settle, fire, mine, cd, warmth, xp, objs, place, glide, repair, fed`

- `state`: `N` not at a fire, `R` at a fire (resting; the settle time runs), `C` camping (settled).
- `settle`: seconds until the player settles (only with `R`, else 0).
- `fire`: seconds until the fire the player is at goes out; 0 when not at a fire or at a fire that never goes out.
- `mine`: `1` if that fire is the player's own (they may pack it up), else `0`.
- `cd`: seconds until the player may make camp again (0 = now).
- `warmth`: seconds of Campfire Warmth left (0 = none).
- `xp`: the player's XP bonus now in percent (warmth and Well Fed together, at most `BleakholdUi.Camp.MaxXpPct`;
  0 at the level cap).
- `objs` (list): the camp objects at this fire, `skill~tier~mine` (`mine` 1 for the player's own object).
- `place` (list): what the player may place here now, `skill~tier`: each of their professions that reaches tier 1,
  at the highest tier they reach. Empty when they are not at a fire, the fire holds three objects or they already
  placed one there.
- `glide`: seconds until the player may glide again (0 = now); empty when they cannot glide (race, or gliding off).
- `repair`: `1` when the player qualifies for `REPAIR` (a blacksmith anywhere, or at a fire with a camp anvil), else
  `0`. `REPAIR` still refuses a dead player or one in combat.
- `fed`: `1` while the player has a Well Fed buff (the food XP bonus), else `0`.

The server sends `CAMPST` after `HELLO` when one of the three feature bits is on, for `GET CAMPST`, and whenever a
field changes other than by counting down: the player comes to a fire or leaves it, settles, an object is placed or
taken away, a fire goes out, a cooldown starts, the warmth starts or ends, `fed` or `xp` changes, the glide is used.
It sends at most one `CAMPST` per second to a player (a later change waits for the second to pass).

### Checks

Every `CAMP`, whatever its `act`:

| Check | Answer |
|---|---|
| malformed (`act` not `M`, `O` or `P`; `skill` missing with `O` or given with `M` or `P`) | dropped silently (section 1) |
| the same `act` (and `skill`) as the player's last accepted `CAMP`, within 1 s | dropped silently |
| the player's `CAMP` rate (`BleakholdUi.RateLimit.CampIntervalMs`, section 8) | `ERR` `busy` |
| camping is off on the realm (`BleakholdUi.Camp.Enable = 0`, no feature bit 512) | `ERR` `camp_off` |
| the player is not in the world | dropped silently |

Then `CAMP M`, in this order:

| Check | Answer |
|---|---|
| the player is dead | `ERR` `camp_dead` |
| the player is in combat | `ERR` `camp_combat` |
| the player is mounted, on a vehicle or a flight path, flying, falling or on a ship | `ERR` `camp_mounted` |
| the player swims or stands in water | `ERR` `camp_water` |
| the player is below `BleakholdUi.Camp.MinLevel` (5) | `ERR` `camp_level` |
| the player is in a dungeon, raid, battleground or arena (a world arena such as Gurubashi too) | `ERR` `camp_instance` |
| the player is in a capital city or a sanctuary | `ERR` `camp_city` |
| the player is indoors | `ERR` `camp_indoors` |
| the player made camp less than `BleakholdUi.Camp.Cooldown` (900 s) ago (a relog does not reset it) | `ERR` `camp_cooldown` |
| the fire could not be made (logged for a game master) | `ERR` `failed` |

`CAMP O,skill`:

| Check | Answer |
|---|---|
| the player is dead | `ERR` `camp_dead` |
| the player is in combat | `ERR` `camp_combat` |
| the player is not at a fire | `ERR` `camp_nofire` |
| the player already placed an object at this fire | `ERR` `camp_placed` |
| the fire already holds three objects | `ERR` `camp_full` |
| `skill` is not a profession with camp objects | `ERR` `camp_skill` |
| the player's skill in it is below tier 1 (or they do not have it) | `ERR` `camp_skill` |
| the object could not be made (logged) | `ERR` `failed` |

`CAMP P`:

| Check | Answer |
|---|---|
| the player has no fire to put out (neither the fire they stand at nor a camp fire elsewhere is theirs) | `ERR` `camp_nofire` |

`GLIDE`:

| Check | Answer |
|---|---|
| malformed (any field) | dropped silently (section 1) |
| a `GLIDE` accepted within the last second | dropped silently |
| the player's `GLIDE` rate (`BleakholdUi.RateLimit.GlideIntervalMs`, section 8) | `ERR` `busy` |
| gliding is off on the realm (`BleakholdUi.Glide.Enable = 0`, no feature bit 1024) | `ERR` `glide_off` |
| the player is not in the world | dropped silently |
| the player's race (the real one, also in a battleground) is not in `BleakholdUi.Glide.Races` | `ERR` `glide_race` |
| the player is in a battleground or an arena, or on a battleground map (Bleakhold Royale's included) | `ERR` `glide_here` |
| the player is dead | `ERR` `dead` |
| the player glided less than `BleakholdUi.Glide.Cooldown` (120 s) ago | `ERR` `glide_cooldown` |
| the aura did not land (logged) | `ERR` `failed` |

`REPAIR`:

| Check | Answer |
|---|---|
| malformed (any field) | dropped silently (section 1) |
| a `REPAIR` accepted within the last second | dropped silently |
| the player's `REPAIR` rate (`BleakholdUi.RateLimit.RepairIntervalMs`, section 8) | `ERR` `busy` |
| field repair and camping are both off (`BleakholdUi.Repair.Enable = 0` and `BleakholdUi.Camp.Enable = 0`) | `ERR` `repair_off` |
| the player is not in the world | dropped silently |
| the player is dead | `ERR` `dead` |
| the player is in combat | `ERR` `in_combat` |
| neither a blacksmith with `BleakholdUi.Repair.MinSkill` (feature 2048) nor at a fire with a camp anvil (feature 512) | `ERR` `repair_skill` |
| nothing needs repairing | `TOAST` (kind `I`) "Nothing needs repairing." |
| the player cannot pay for the whole repair | `ERR` `repair_gold` |

When every check passes the server repairs everything and sends a `TOAST` (kind `I`) with the cost.

The module makes the rate, duplicate and on/off checks whoever handles `CAMP`, `GLIDE` and `REPAIR`; a server that
replaces a handler (`Ui::OnIntent(IntentType::Camp, ...)`) keeps the others itself.

Error codes of this section:

| Code | Meaning |
|---|---|
| `camp_off` | camping is off on the realm |
| `camp_dead` | dead |
| `camp_combat` | in combat |
| `camp_mounted` | mounted, on a vehicle, a flight path or a ship, flying or falling |
| `camp_water` | in water |
| `camp_level` | below the level to make camp |
| `camp_instance` | in a dungeon, raid, battleground or arena |
| `camp_city` | in a capital city or a sanctuary |
| `camp_indoors` | indoors |
| `camp_cooldown` | made camp not long ago |
| `camp_nofire` | not at a fire (`O`), or no fire of one's own to pack up (`P`) |
| `camp_full` | the fire already holds three camp objects |
| `camp_placed` | already placed an object at this fire |
| `camp_skill` | not a profession with camp objects, or the skill is too low |
| `glide_off` | gliding is off on the realm |
| `glide_race` | the player's race cannot glide |
| `glide_here` | in a battleground or an arena (Bleakhold Royale's map included) |
| `glide_cooldown` | glided not long ago |
| `repair_off` | field repair (and camping) is off on the realm |
| `repair_skill` | neither a blacksmith with enough skill nor at a camp anvil |
| `repair_gold` | not enough money for the whole repair |
| `dead`, `in_combat` | `GLIDE` while dead; `REPAIR` while dead or in combat |
| `failed` | the server could not make the fire, the object or the glide (logged) |

```
C> 1 GET m 1/1 CAMPST
S> 1 CAMPST 7 1/1 N,0,0,0,640,1500,15,,,95,0,1
C> 1 CAMP n 1/1 M
S> 1 CAMPST 8 1/1 R,60,900,1,900,0,5,,164~2:197~3,0,1,1
C> 1 CAMP o 1/1 O,164
S> 1 CAMPST 9 1/1 C,0,700,1,880,1800,15,164~2~1:171~1~0,,0,1,1
C> 1 CAMP p 1/1 P
C> 1 GLIDE q 1/1
S> 1 ERR s 1/1 GLIDE,q,glide_cooldown,You can glide again in 95 s.
C> 1 REPAIR r 1/1
S> 1 ERR t 1/1 REPAIR,r,repair_gold,You cannot pay for the repair (2g 10s 0c).
```

## 17. Bleakhold Royale

Bleakhold Royale is a solo free-for-all battle royale: 20 to 40 players at level 80 on their own battleground map,
one life each, and the last player standing wins. The server decides everything: who may queue, the ready check,
where a landing pin really lands, the storm, the loot, every elimination and every reward. The client shows the state
it gets and sends only the player's wishes: join or leave the queue (`QJOIN B`, `QLEAVE`), answer the ready check
(`QREPLY`), set a landing pin (`RDROP`), open the parachute (`RDEPLOY`) and switch the spectator camera (`RSPEC`).

`HELLO` feature bit 4096 is on while the mode is live. The server turns it on at runtime once its own data checks
pass, and off again when the mode is switched off; clients already connected get a new `HELLO` (section 7). While the
bit is off the server answers `QJOIN B`, `RDROP` and `RSPEC` with `ERR` `royale_off` and drops `RDEPLOY`.

**The match.** `phase` (in `ROYS`):

| `phase` | |
|---|---|
| 0 arriving | players arrive in the lobby, The Overlook, a mesa in a corner of the map. A warm-up brawl: damage is on, nobody dies. Landing pins can be set. |
| 1 countdown | the big countdown; the first storm circle is shown 15 s before the drop, and the pins lock 3 s before it |
| 2 drop | everyone falls from high above their pin and opens a parachute (by itself, or at once with `RDEPLOY`) |
| 3 fight | the storm circle closes in six stages; outside it the storm hurts more with every stage |
| 4 overtime | the circle is gone and the storm keeps getting stronger |
| 5 victory | one player is left: the winner |
| 6 ended | the scoreboard; the players leave or are sent back |
| 7 cancelled | too few players arrived: everyone goes back to the front of the queue |

A player who would die is eliminated instead and becomes an invisible spectator on the same map: they can watch the
players still alive (`RSPEC`), queue again (`QJOIN B`) or leave. Logging out or leaving the battleground while alive
forfeits the match.

**Positions** are integer world yards of the Royale map (X points north, Y west, as `.gps` shows them). The client
draws its island map from `ROYM`'s frame: `u = (maxY - y) / (maxY - minY)`, `v = (maxX - x) / (maxX - minX)` (north
up, west left). **Times** in `ROYS`, `ROYO` and `ROYV` count from the moment the message arrives, like `QUEUE`
`timeoutSec`; the client counts them down itself. **Names** of characters are at most 48 bytes (two-word names fit),
names of places at most 40.

### The queue

`QJOIN B,activityId,0,roles,1`: `activityId` is the mode id (the server's `Bleakhold.Royale.ActivityId`, 901),
`tier` 0 and `size` 1; `roles` (1..7) is ignored. A repeated `QJOIN B` only sends `QUEUE` again. `QLEAVE` leaves the
Royale queue (outside it, it does what it does for the other queues). `QREPLY proposalId,accept` answers the ready
check when `proposalId` is the player's open Royale proposal; no answer before `timeoutSec` runs out is a decline, and
a player who declines cannot queue for 120 s. When enough players accept (`minPlayers`, 20), the match starts and
everyone who accepted is taken there.

`QUEUE` for kind `B` has the fields of section 7, then `queued, minPlayers, maxPlayers, accepted, proposalSize,
matchesRunning`:

- `state`: 0 not queued, 1 queued, 2 ready check (with `proposalId` and `timeoutSec`), 3 in a match.
- `activityId`: the mode id; `tier` 0; `size` 1; `bandMin`/`bandMax`: the level band (80, 80).
- `queued`: players in the Royale queue now. `minPlayers`/`maxPlayers`: how many a match needs and how many it takes
  (20 and 40).
- `accepted`, `proposalSize`: during a ready check, how many accepted so far and how many it went to.
- `matchesRunning`: matches being played now.
- No member records.

`QJOIN B`, in this order:

| Check | Answer |
|---|---|
| malformed (for `B`: `activityId` 0, `tier` not 0 or `size` not 1) | dropped silently (section 1) |
| the player's `QJOIN` rate (section 8) | `ERR` `busy` |
| Bleakhold Royale is off (no feature bit 4096), or `activityId` is not the mode id | `ERR` `royale_off` |
| the player is not level 80 | `ERR` `royale_level` |
| the player is in a group | `ERR` `royale_grouped` |
| the player is in an instance, a battleground (a Royale spectator excepted), an arena, another queue, the Dungeon Journey lobby or a Rift run, on a transport, or in GM mode | `ERR` `royale_busy` |
| the player has Deserter | `ERR` `royale_deserter` |
| the player is dead | `ERR` `dead` |
| fewer than 6 free bag slots | `ERR` `royale_bags` |
| too many players from the player's IP address are queued or playing | `ERR` `royale_ip` |
| the player declined a ready check less than 120 s ago | `ERR` `royale_lockout` (the text gives the seconds left) |

A spectator's `QJOIN B` leaves the match and queues again. `QREPLY` without an open proposal of that id: `ERR`
`no_proposal`.

### Intents of the match

`RDROP x,y` sets the player's landing pin. `x` and `y` are integer world yards, -17067..17067 each, and may be
negative. The server snaps the pin to a valid point (inside the playable square, away from the lobby, not in water,
not on a cliff; a random landmark when nothing near fits) and sends `ROYS` with the snapped `pinX, pinY`. A player
without a pin drops at a random landmark.

| Check | Answer |
|---|---|
| malformed (not two integers in -17067..17067) | dropped silently (section 1) |
| the same `x,y` as the player's last accepted `RDROP`, within 1 s | dropped silently |
| the player's `RDROP` rate (section 8) | `ERR` `busy` |
| Bleakhold Royale is off | `ERR` `royale_off` |
| the player is not in the lobby of a match (phase 0 or 1), or the pins are locked (the last 3 s) | `ERR` `royale_phase` |

`RDEPLOY` opens the parachute at once. It is never answered, not even over its rate limit (section 8): it is dropped
silently unless the player is falling from the drop, has not opened the parachute yet and fell for at least 0.5 s.
Without it the parachute opens by itself (2.5 s into the fall, or 70 yd above the ground).

`RSPEC dir` moves a spectator's camera: `dir` 0 to the player who eliminated them (or the first player alive), 1 to
the next player alive, 2 to the previous one. The server sends `ROYS` with the new `watchName`.

| Check | Answer |
|---|---|
| malformed (`dir` not 0, 1 or 2) | dropped silently (section 1) |
| the player's `RSPEC` rate (section 8; the same `dir` again is not a duplicate) | `ERR` `busy` |
| Bleakhold Royale is off | `ERR` `royale_off` |
| the player is not a spectator in a match | `ERR` `royale_phase` |
| nobody is alive to watch | `ERR` `royale_nobody` |

`GET ROYS` is answered with `ROYS` then a full `ROYO`, `GET ROYM` with `ROYM`; nothing is sent to a player who is not
in a match. After a `/reload` in a match the client sends `GET ROYS;ROYM` once `HELLO` is answered.

### ROYS (the match as the player sees it)

`matchId, phase, phaseMsLeft, alive, total, me, kills, placement, pinX, pinY, stage, curX, curY, curR, nextX, nextY, nextR, shrinkStartMs, shrinkEndMs, dmgPermille, watchName, myX, myY`

- `matchId`: the match; another id is another match.
- `phase`: the table above. `phaseMsLeft`: until the next phase (the countdown in phase 1).
- `alive`: players still in the fight; `total`: players in the match (who dropped, or are in the lobby before it).
- `me`: 0 in the lobby, 1 dropping, 2 alive, 3 spectating, 4 left, 5 the winner.
- `kills`: the player's eliminations. `placement`: empty while the player is in the fight.
- `pinX`, `pinY`: the player's snapped landing pin; empty when none is set.
- `stage`: the storm stage, 1 to 6 (0 before the first circle is shown).
- `curX`, `curY`, `curR`: the storm circle when the message was sent.
- `nextX`, `nextY`, `nextR`: the next circle; empty until it is shown.
- `shrinkStartMs`, `shrinkEndMs`: until the next shrink starts and ends. `shrinkStartMs` 0 and `shrinkEndMs` above 0:
  the circle is shrinking now, `cur` moves linearly to `next` over `shrinkEndMs`. Both empty: no shrink is planned.
- `dmgPermille`: the storm damage outside the circle now, in permille of maximum health per second.
- `watchName`: for a spectator, the player they watch; empty otherwise.
- `myX`, `myY`: the player's position (the map arrow when the client cannot place the player itself).

The server sends `ROYS` when the player arrives, on every change of `phase`, `stage` or `me`, after `RDROP` and
`RSPEC`, every 5 s, and for `GET ROYS`.

### ROYM (the island map)

First record: `mapId, minX, maxX, minY, maxY, lobbyX, lobbyY, lobbyR, boundHalf, centerX, centerY`. Then one record
per place (at most 64): `id, kind, x, y, r, name`.

- `minX`..`maxY`: the frame of the map picture. `lobbyX`, `lobbyY`, `lobbyR`: the lobby, which players in the fight may
  not enter. `boundHalf`: half the side of the playable square around `centerX`, `centerY`.
- `kind`: `L` landmark, `C` crossing (a bridge or a ford), `Y` the lobby. `r`: the radius of the place in yards.
- Crate spots and the sites where the last circle may end are never sent.

Sent when the player arrives and for `GET ROYM`.

### ROYO (orbs and supply drops)

First record: `matchId, full`. Then one record per object (at most 64): `objId, kind, subtype, x, y, state, msLeft`.

- `full`: 1 replaces every object the client knows; 0 updates only the objects listed.
- `kind`: `S` Shadow Sight orb (stealth is no cover for a while), `B` buff orb, `D` supply drop. `subtype`: for `B`
  1 speed, 2 restoration, 3 berserk; 0 otherwise.
- `state`: 0 hidden (appears in `msLeft`, when given), 1 ready, 2 taken (back in `msLeft`), 3 incoming (lands in
  `msLeft`), 4 opened.

Sent full for `GET ROYS`, and with the objects that changed whenever one does.

### ROYK (the kill feed)

`killerName, killerClassId, victimName, victimClassId, cause, aliveAfter, killerKills, announce`

- `cause`: `P` a player, `S` the storm (the killer is filled in when someone gets the credit), `F` a fall or the
  world, `L` left the match, `A` eliminated for being away.
- `killerName` and `killerClassId` are empty when nobody gets the credit. `killerKills`: the killer's eliminations
  in this match, this one included. `aliveAfter`: players left in the fight.
- `announce`: **superseded** by the battleground kill announcer (`BGANN`, section 18), which also covers Bleakhold
  Royale. The server sends it empty and the addon ignores it, so no announcer line plays twice. (It used to carry
  `F` `D` `T` `M` `R` `G`.) Knockdowns in the lobby brawl are not eliminations: they send no `ROYK` and never count.

Sent to every player of the match, spectators included.

### ROYV (match events)

`kind, value, x, y, msLeft, name`

| `kind` | Meaning |
|---|---|
| `R` | the next circle is shown; `value` = its stage |
| `S` | the storm moves; `value` = the stage |
| `D` | a supply drop is coming down at `x`, `y`; it lands in `msLeft` |
| `L` | the supply drop at `x`, `y` landed |
| `O` | the supply drop at `x`, `y` was opened |
| `N` | `value` players are left (10, 5, 2) |
| `W` | the match has a winner: `name`, with `value` eliminations |

Sent to every player of the match.

### ROYE (the player's result)

First record: `matchId, placement, total, kills, damage, healing, survivedSec, winnerName, winnerClassId, winnerKills, rewarded`.
Then one record per reward: `kind, amount, itemId, text`, with the kinds of `MPE` (section 7) and `H` honor.

- `placement` of `total`; `damage` and `healing` the player did to and for players; `survivedSec` from the landing.
- `winnerName`, `winnerClassId`, `winnerKills`: empty while the match goes on.
- `rewarded`: 1 when the player earned the rewards (they did not quit and took part), else 0 and no reward records.

Sent when the player is eliminated or wins. The server may send it again when the match ends, with the winner filled
in; the last one counts.

### A match

`QJOIN B` -> `QUEUE` state 1 -> 20 players or more: `QUEUE` state 2 with `proposalId` and `timeoutSec` 15 ->
`QREPLY` -> `QUEUE` state 3 and the teleport -> `ROYM` and `ROYS` (phase 0) -> `RDROP` (answered by `ROYS`) ->
`ROYS` phase 1 and `ROYV R` (the first circle) -> phase 2: the drop, `RDEPLOY` -> phase 3: `ROYV S` as the storm
moves, `ROYV D`, `L`, `O` for supply drops, `ROYO` for orbs, `ROYK` for every elimination, `ROYV N` -> eliminated:
`ROYE`, then `ROYS` with `me` 3 and `RSPEC` -> one player left: `ROYV W`, `ROYS` phase 5 and the winner's `ROYE` ->
phase 6 -> back in the world: `QUEUE` state 0. A cancelled match: `ROYS` phase 7 and `QUEUE` state 1 again.

The realm hears about the mode on `[Royale]` lines (section 10): when the queue fills up, and for every winner.

### Error codes

| Code | Meaning |
|---|---|
| `royale_off` | Bleakhold Royale is off, or not set up correctly (no feature bit 4096), or `activityId` is not the mode id |
| `royale_level` | not level 80 |
| `royale_grouped` | in a group |
| `royale_busy` | in an instance, a battleground, an arena, another queue, the Dungeon Journey lobby or a Rift run; on a transport; in GM mode |
| `royale_deserter` | the player has Deserter |
| `royale_bags` | fewer than 6 free bag slots |
| `royale_ip` | too many players from the player's IP address |
| `royale_lockout` | declined a ready check not long ago (the text gives the seconds left) |
| `dead`, `in_combat` | the generic codes (`QJOIN B` while dead; any Royale intent the server refuses in combat) |
| `no_proposal` | `QREPLY` with no open proposal of that id |
| `royale_phase` | `RDROP` outside the lobby or after the pins locked; `RSPEC` from a player who is not a spectator |
| `royale_nobody` | `RSPEC` with nobody alive to watch |
| `glide_here` | `GLIDE` in a battleground, an arena or on the Royale map (section 16) |

```
C> 1 QJOIN 7 1/1 B,901,0,4,1
S> 1 QUEUE f 1/1 4,1,B,901,0,1,12,,,,80,80,13,20,40,,,1
S> 1 QUEUE g 1/1 5,2,B,901,0,1,95,,412,15,80,80,24,20,40,0,24,1
C> 1 QREPLY 8 1/1 412,1
S> 1 QUEUE h 1/1 6,3,B,901,0,1,,,,,80,80,,20,40,,,2
S> 1 ROYM i 1/1 901,-1066,533,-1066,533,455,455,32,750,-267,-267;1,L,-266,-266,88,The Bleak Hold;2,L,120,80,62,Harrow Farm
S> 1 ROYS j 1/1 7001,1,45000,24,24,0,0,,,,0,-267,-267,1080,,,,,,0,,450,452
C> 1 RDROP 9 1/1 104,96
S> 1 ROYS k 1/1 7001,1,41000,24,24,0,0,,104,96,0,-267,-267,1080,,,,,,0,,450,452
C> 1 RDEPLOY a 1/1
S> 1 ROYO l 1/1 7001,1;1,S,0,-266,-266,0,90000;2,S,0,-712,48,0,90000;3,B,1,120,80,1
S> 1 ROYV m 1/1 D,0,-80,-180,20000
S> 1 ROYK n 1/1 Aldric,1,Brenna,8,P,23,1
S> 1 BGANN u 1/1 Aldric,1,Brenna,8,,F
S> 1 ROYE o 1/1 7001,12,24,1,18400,0,214,,,,1;H,70,,Placement;H,25,,1 elimination;S,5,,Placement
C> 1 RSPEC b 1/1 1
S> 1 ROYV p 1/1 W,7,,,,Dalia
C> 1 GLIDE c 1/1
S> 1 ERR q 1/1 GLIDE,c,glide_here,You cannot glide here.
```

## 18. Battleground kill announcer

A DotA-style kill announcer for every battleground: Warsong Gulch, Arathi Basin, Alterac Valley, Eye of the Storm,
Strand of the Ancients, Isle of Conquest and Bleakhold Royale (section 17). Never in an arena or the open world. The
server keeps the score and tells every player of the battleground about each kill worth announcing with `BGANN`; the
client shows a big banner in the middle of the screen ("Aldric: DOUBLE KILL") and plays the voice line.

`HELLO` feature bit 8192 is on while the server's announcer is enabled. The client plays `BGANN` only with that bit,
only inside a battleground and never in an arena.

**Rules** (all on the server):

- Only kills of players count, credited to the player who dealt the killing blow; a pet's, a totem's or a damage over
  time's killing blow counts for its owner. Kills of creatures never count, nor a player killing themselves (a fall,
  the environment) or a player of their own team.
- **First blood** (`F`): the first credited kill in each battleground instance.
- **Kill streak**: the killer's kills since they last died; any death (by a player, a creature, a fall) starts the
  count again. In Bleakhold Royale a player has one life, so the streak is all their eliminations; there an
  elimination by a player, or by the storm or a fall with a credited killer, counts, a forfeit (`L`) or an AFK
  elimination (`A`) does not. Each kill that reaches a step is announced: 3 `S` killing spree, 4 `O` dominating,
  5 `K` mega kill, 6 `N` unstoppable, 7 `W` wicked sick, 8 `M` monster kill, 9 `G` godlike, 10 and every further
  kill `H` holy shit.
- **Multi-kill**: kills by the same player with at most 18 seconds (the server's `MultiKillWindowSec`) between one
  kill and the next. 2 `D` double kill, 3 `T` triple kill, 4 `U` ultra kill, 5 and every further kill in the chain
  `R` rampage. The killer's death does not end a chain; 18 seconds without a kill do.
- One kill can carry a multi-kill code and a streak code (or first blood). A kill with neither sends nothing.

### BGANN (an announced kill)

`killerName, killerClassId, victimName, victimClassId, multi, streak`

- `killerName`, `victimName`: character names, at most 48 bytes. `killerClassId`, `victimClassId`: ChrClasses ids.
- `multi`: `D` `T` `U` `R`, or empty.
- `streak`: `F` first blood or `S` `O` `K` `N` `W` `M` `G` `H`, or empty (as the last field it may be left out,
  section 4). At least one of `multi` and `streak` is set.

Sent to every player in the battleground (Bleakhold Royale's spectators included), once per kill, at the moment of
the kill. Unrevisioned; there is nothing to `GET`.

**The client** plays the multi-kill line first and then the streak (or first blood) line, one after the other, each
with its banner. A voice line cannot be stopped or turned down on 3.3.5a, so lines never overlap: each waits until the
one before it has finished. When lines pile up the client keeps at most two waiting and drops the lowest ones (a
higher streak or multi-kill ranks above a lower one; first blood ranks lowest). Settings: announcer Off, Male (the
default) or Female, and volume Normal or Quiet.

```
S> 1 BGANN v 1/1 Aldric,1,Brenna,8,,F
S> 1 BGANN w 1/1 Aldric,1,Corwin,5,D
S> 1 BGANN x 1/1 Aldric,1,Dalia,11,T,S
S> 1 BGANN y 1/1 Garrick Stormwind,4,Aldric,1,,O
S> 1 BGANN z 1/1 Eamon,9,Fenna,3,R,H
```

The first is first blood, the second Aldric's second kill within 18 s (a double kill; his streak of 2 has no step), the
third a triple kill that is also his third kill without dying (killing spree). Then Garrick Stormwind ends Aldric's
streak with his fourth kill since he last died (dominating), and Eamon's fifth kill in one chain is a rampage on his
tenth or later kill without dying.
