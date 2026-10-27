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
  `ERR`, `HELLO`, `PONG`, `CASES`, `CASE`, `UNBOX`, `CAMPST`, `ROYS`, `ROYM`, `ROYO`, `ROYK`, `ROYV`, `ROYE`, `BGANN`,
  `WMST`, `WPZ`, `WPCAP`, `WPMAP`, `WANTED`, `WPEV`, `ARENA`) are full states or events; each one stands alone.

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
| `QJOIN` | `kind, activityId, tier, roles, size` | join the queue. `kind`: `D` dungeon board, `R` Eclipse Rift, `B` Bleakhold Royale (section 17), `A` the 1v1 arena queue (section 20). `activityId`: dungeon id (0 for the Rift, the mode id, above 0, for Royale, 1 for the arena). `tier`: 0 Normal, 1 Veteran, 2 Elite, 3 Nightmare (always 0 for Royale; for the arena 0 skirmish, 1 rated). `roles`: bit mask 1 tank, 2 healer, 4 damage (ignored for Royale and the arena). `size`: wanted group size 1..5 (1 = enter alone, no matchmaking; always 1 for Royale and the arena) |
| `QLEAVE` | | leave the queue (the Royale queue when the player is in it, else the 1v1 arena queue when the player is in that one) |
| `QREPLY` | `proposalId, accept` | answer a group proposal or a Royale ready check (1 accept, 0 decline) |
| `KMODE` | `mode` | set the dungeon mode for the next instance: 0 Normal, 1 Heroic, 2 Mythic (replaces the Mythic choice in the portrait Dungeon Difficulty menu, which the addon leaves alone) |
| `KSTART` | | start the keystone (group leader, inside the dungeon) |
| `KCANCEL` | | cancel the start countdown (group leader) |
| `BCLAIM` | `bountyId` | claim today's bounty |
| `WEHANDIN` | | hand in spare war effort tokens (the server counts them) |
| `OUTFIT` | `setId` | save the unlocked outfit of a legacy set |
| `LBQ` | `board, seasonId, dungeonId, classId, page` | leaderboard page. `board`: `K` Mythic keys, `R` Eclipse Rift, `E` Raid Echoes, `F` server firsts, `A` arena (section 20: `seasonId` an arena season, `dungeonId` the bracket 1, 2, 3 or 5, never 0). 0 = all for `dungeonId`/`classId`. `page` from 1 |
| `PING` | `nonce` | answer with `PONG` |
| `EMOJI` | `emojiId` | show emoji `emojiId` above the player's head to everyone nearby (section 13). `emojiId`: 0..255, an index into the emoji catalogue, `Tools/EmojiForge/emojis.json` |
| `DANCE` | `danceId` | dance Bleakhold dance `danceId` until the player moves (section 14). `danceId`: 0..1023, an index into the dance catalogue, `Tools/DanceForge/dances.json` |
| `CASEOPEN` | `caseItemId, nonce` | open one case `caseItemId` from the player's bags (section 15); `nonce` (0..2147483647) comes back in `UNBOX` |
| `CAMP` | `act[, skill]` | camping (section 16). `act`: `M` make camp here, `O` place a camp object at the fire the player is at, `P` pack up the player's fire. `skill` (1..2147483647, a SkillLine id from `CAMPST` `place`) is sent with `O` and only with `O`: `CAMP M`, `CAMP O,164`, `CAMP P` |
| `GLIDE` | | Walk on Air, the High Elf glide: the player's fall becomes a glide they steer (section 16) |
| `REPAIR` | | repair everything the player wears and carries in the bags, for the normal cost (section 16) |
| `RDROP` | `x, y` | Bleakhold Royale: set the landing pin (section 17). Integer world yards, -17067..17067 each (they may be negative) |
| `RDEPLOY` | | Bleakhold Royale: open the parachute now (section 17) |
| `RSPEC` | `dir` | Bleakhold Royale spectators: watch another player (section 17). `dir`: 0 the killer (or the first player alive), 1 the next, 2 the previous |
| `WARMODE` | `on` | turn War Mode on (1) or off (0) (section 19) |

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
| `WMST` | | `WMST`; nothing while War Mode is off on the realm (section 19) |
| `WPZ` | | `WPZ` for the zone the player is in; nothing while World PvP is off (section 19) |
| `WPMAP` | | `WPMAP`; nothing while World PvP is off (section 19) |
| `WANTED` | | `WANTED` for the player's zone, to a War Mode player; nothing otherwise (section 19) |
| `ARENA` | | `ARENA` while feature bit 65536 is on; nothing otherwise (section 20) |

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
C> 1 GET x 1/1 WMST;WPZ;WPMAP;WANTED
C> 1 WARMODE y 1/1 1
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
  (section 18), 16384 War Mode live, 32768 World PvP objectives live (section 19; 32768 is only ever on together
  with 16384), 65536 arena seasons and the 1v1 ladder live (section 20).
- The server may send `HELLO` again at any time, without a client `HELLO`, when its feature bits change (Bleakhold
  Royale, War Mode and World PvP turn their bits on or off at runtime, the arena system 65536). The client reads it
  like an answer to its own.
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
13 to 19).

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
| `V` arena tier | `id, name, colorHex, text` (section 20) |
| `Q` arena reward | `id, seasonId, bracket, tierId, kind, entry, count, text` (section 20) |
| `Z` end | header only: `Z, dataVer` |

Send `DEF Z,<dataVer>` after the last kind: the client keeps the definitions for that `dataVer` only once
the set is complete. The client also stores the set of kinds it parsed (its DEF schema): a cache saved by an addon
that did not know some kinds (V and Q before section 20) is fetched again after an addon update even when `dataVer`
matches, and its `HELLO` then says `dataVer` 0.

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
`season`, `leaderboards`, `royale` (the Bleakhold Royale card, section 17), `arena` (the Arena page, section 20), or
empty.

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
- Kind `A` (the 1v1 arena queue) ends at `estWaitSec` and never has member records (section 20).

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

Page 1 should include ranks 1-3 (the podium). Up to 10 rows per page fit comfortably in a few frames. Board `A` (arena)
has rows and an `LBME` of its own, with more fields after `label` (section 20).

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
| `GET` | at most 8 records per message; each topic at most once per second (`ARENA` too; the addon asks for it at most every 30 s) |
| `LBQ` | 2 per second |
| `QJOIN`, `QLEAVE`, `QREPLY` | 1 per second each (every kind together, `QJOIN A` too) |
| `KSTART`, `KCANCEL`, `KMODE` | 1 per 2 s each |
| `TCLAIM`, `TREROLL`, `BCLAIM`, `OUTFIT`, `WEHANDIN` | 2 per second together; idempotent anyway |
| `EMOJI` | 1 per `BleakholdUi.Emoji.CooldownMs` (2.5 s); the addon waits 3.25 s itself |
| `DANCE` | 1 per `BleakholdUi.Dance.CooldownMs` (1 s); the addon waits 1.25 s itself |
| `CASEOPEN` | 1 per `BleakholdUi.Case.CooldownMs` (1 s); the addon waits for `UNBOX` or `ERR` (at most 5 s) |
| `CAMP` | 1 per `BleakholdUi.RateLimit.CampIntervalMs` (1 s), every `act` together |
| `GLIDE` | 1 per `BleakholdUi.RateLimit.GlideIntervalMs` (1 s); the glide itself has a 90 s cooldown (`ERR glide_cooldown`) |
| `REPAIR` | 1 per `BleakholdUi.RateLimit.RepairIntervalMs` (2 s) |
| `RDROP`, `RSPEC` | 1 each per `BleakholdUi.RateLimit.RoyaleIntervalMs` (0.5 s, so 2 per second); the addon waits 0.5 s itself |
| `RDEPLOY` | 1 per `BleakholdUi.RateLimit.RoyaleDeployIntervalMs` (1 s); over it, dropped silently (no `busy`) |
| `WARMODE` | 1 per `BleakholdUi.RateLimit.WarModeIntervalMs` (2 s); War Mode itself can only change once per 15 minutes (`ERR wm_cooldown`) |

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
| `[Season] ` | season and war effort news, arena seasons (section 20) |
| `[Queue] ` | a group search started (sent to the whole server) |
| `[Record] ` | a new run record |
| `[Case] ` | a rare reward from a case (section 15) |
| `[Royale] ` | Bleakhold Royale: the queue filling up, a winner (section 17) |
| `[War] ` | World PvP: a Front starts soon, starts, ends; to the players of a zone, its captures, Wanted players and bounties (section 19) |

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

**War Mode and World PvP.** `HELLO` (bits 16384, 32768) -> `WMST` -> `WARMODE 1` in an inn or a city -> `WMST` ->
entering a Front zone: `WPZ` -> at an outpost: `WPCAP` every second -> `WPEV` for captures, Wanted players, bounties
and rewards. The whole flow is in section 19 ("A Front").

**Arena.** `HELLO` (feature bit 65536) -> `ARENA` (and the client's `GET ARENA`); the Arena page: `GET ARENA` ->
`QJOIN A` -> `QUEUE` kind `A` state 1 -> the game's invite dialog -> `QUEUE` state 3 -> the match ends: `ARENA` (with
the match in `M`) and `QUEUE` state 0.
The arena leaderboard: `LBQ A` -> `LB` and `LBME`. Season changes: `ARENA` to everyone (section 20).

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

**Glide (Walk on Air).** `GLIDE` lets a player of a race in `BleakholdUi.Glide.Races` (22, the High Elf) turn a fall
into a glide they steer, every `BleakholdUi.Glide.Cooldown` (90 s; a relog does not reset it). It never flies and never
gains altitude:

- The server puts Walk on Air on the player (`BleakholdUi.Glide.Spell`, spell 100800: a feather fall aura for
  `BleakholdUi.Glide.Duration`, 10 s), a triggered cast: no reagent, no cost and no spell cooldown on the client.
- A fall at least 2.5 yd above the ground or the water becomes the glide: at once when the player is already falling,
  else the moment they go over a ledge (a `GLIDE` on the ground waits for one, and the wait counts toward the aura's
  10 s; a small hop does not use it up). The descent slows to the feather fall's 7 yd/s at most, and the server pushes
  the player forward along their facing at `BleakholdUi.Glide.ForwardSpeed` (12 yd/s; running is 7). The push has no
  upward part: when the glide starts the fall starts over from rest, later pushes keep the descent the player has
  built up since the push before (the server counts it from its own pushes, so latency never flattens the glide).
- Turning steers. A 3.3.5a client keeps the direction a fall started with, so the server pushes again along the new
  facing whenever the player turns 5 degrees or more (`BleakholdUi.Glide.Steer`; at most five pushes a second and 64
  per glide, never while rooted, stunned, feared, charmed or on a transport, and never less than 2.5 yd above the
  ground, where a push could reach the client after it lands).
- Landing, water, the end of the aura and coming onto a map without the glide (below; also after a `GLIDE` just
  before the port) end the glide.
  A landing takes no fall damage (the aura is still on when the server checks the fall), and the aura goes at once so
  it cannot soften a later fall. A landing before the client acked the last push (`CMSG_MOVE_KNOCK_BACK_ACK`) waits
  for it: the client carries out a push even after it landed, so the glide and its aura stay, with no more pushes,
  until the landing after the ack (1.5 s at most when no ack comes). When the aura runs out in the air, the player
  falls normally from there.
- With Slow Fall (130, the fallback below) a mage's own Slow Fall stays: `GLIDE` does not shorten one with more time
  left than a glide, and the end of a glide takes off only the Slow Fall `GLIDE` put on (not one the mage cast again).
- A gust of wind with a whoosh (`BleakholdUi.Glide.StartVisualKit`, SpellVisualKit 13709) plays when the glide starts;
  Walk on Air's own wings (spell visual 7370, the one of Magic Wings: wings at the head, no sound, no forced
  animation) show while it lasts, so the player keeps their own run, jump and fall animations.

There is no glide in a battleground or an arena, the Bleakhold Royale map included (section 17), nor in a dungeon or a
raid unless `BleakholdUi.Glide.Instances` is on (0 by default): there the steerable push would skip jump shortcuts
(Mythic+ routes and timers) and undo drop-off boss mechanics (knockbacks off a platform, the Lich King's edge), which
Slow Fall, with no control over the direction, never could. A glide running or waiting when the player comes onto
such a map (a teleport, a summon, an instance portal) ends there, and its aura goes with it. `CAMPST` `glide` is the
cooldown and `gliding` the glide that runs now.

Walk on Air is the module's own spell. The server has it from `data/sql/db-world/02_bleakhold_walk_on_air.sql`
(`spell_dbc`); the client needs the same row in its `Spell.dbc` (a patch MPQ) for the buff's name, icon
(Spell_Nature_EyeOfTheStorm), tooltip ("Glide through the air for 10 sec, steering your descent. Does not gain
altitude.": its `$d` is the row's duration) and wings. Without the client row the glide works the same, with no buff
shown; without the server row the server glides with Slow Fall (130) and logs it.

**mod-anticheat.** A glide is movement mod-anticheat (AnticheatMgr) accepts: the push only happens while the player
falls, its speed check skips a packet that follows a falling one and its teleport check a falling player (a glide
covers 6 yd between two packets, the check wants 50); there is no fly flag (the client's knockback even clears
`MOVEMENTFLAG_CAN_FLY`); the push never goes up, while the jump, gravity and ignore-z checks look for rising or level
movement in the air (and the jump and gravity checks skip a feather fall aura); the no-fall-damage check skips a
feather fall aura, and under it two packets never lie 14.57 yd apart in height; the climb, teleport-to-plane,
ignore-control and anti-swim checks skip falling packets. Its anti-knockback check reports a knockback whose ack
stands where the packet before it did, and the client acks a push at the same spot when it acks it in the same
millisecond as a facing change or the feather fall ack sent just before it: the push therefore leaves
`Player::CanKnockback` as it was (a client that ignored a glide's push would gain nothing). Its order-ack check is not
wired in.

### CAMPST (the player's camping state)

`state, settle, fire, mine, cd, warmth, xp, objs, place, glide, repair, fed, gliding`

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
- `gliding`: seconds left of the glide that runs now (Walk on Air, from `GLIDE` until it lands or runs out; also
  while it waits for a ledge); empty (left out) when there is none. Older clients read the fields before it.

The server sends `CAMPST` after `HELLO` when one of the three feature bits is on, for `GET CAMPST`, and whenever a
field changes other than by counting down: the player comes to a fire or leaves it, settles, an object is placed or
taken away, a fire goes out, a cooldown starts, the warmth starts or ends, `fed` or `xp` changes, the glide is used,
a glide starts or ends.
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
| the player is between maps | dropped silently |
| the player's race (the real one, also in a battleground) is not in `BleakholdUi.Glide.Races` | `ERR` `glide_race` |
| the player is in a battleground or an arena, or on a battleground map (Bleakhold Royale's included) | `ERR` `glide_here` |
| the player is in a dungeon or a raid and `BleakholdUi.Glide.Instances` is off (the default) | `ERR` `glide_here` |
| the player is dead | `ERR` `dead` |
| the player is mounted, on a vehicle or on a flight path | `ERR` `glide_mounted` |
| the player flies, can fly (a flight form, a flying mount's aura) or hovers | `ERR` `glide_flying` |
| the player swims or stands in water | `ERR` `glide_water` |
| the player is rooted, stunned, feared, confused, charmed or controls another unit | `ERR` `glide_rooted` |
| `BleakholdUi.Glide.RequireFalling` is on and the player is not in the air (falling or jumping) | `ERR` `glide_ground` |
| the player glided less than `BleakholdUi.Glide.Cooldown` (90 s) ago | `ERR` `glide_cooldown` |
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
| `glide_here` | in a battleground or an arena (Bleakhold Royale's map included), or in a dungeon or a raid (`BleakholdUi.Glide.Instances` off) |
| `glide_mounted` | mounted, on a vehicle or on a flight path |
| `glide_flying` | flying, able to fly or hovering |
| `glide_water` | in water |
| `glide_rooted` | rooted, stunned or not in control |
| `glide_ground` | not in the air while `BleakholdUi.Glide.RequireFalling` is on |
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
C> 1 GLIDE s 1/1
S> 1 CAMPST u 1/1 N,0,0,0,640,1500,15,,,90,0,1,10
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
| 2 drop | everyone falls from high above their pin and opens a parachute (by itself, or at once with `RDEPLOY`); the phase ends when the last player has landed (at most 30 s after the drop). A player who has landed already fights: the client shows the fight's storm timer from `me` 2 on |
| 3 fight | the storm circle closes in `stages` stages (six by default; the first one starts to move 2 minutes after the drop); outside it the storm hurts more with every stage. A late arrival drops on their own during this phase (`me` 1) |
| 4 overtime | the circle is gone and the storm keeps getting stronger |
| 5 victory | one player is left: the winner |
| 6 ended | the scoreboard; the players leave or are sent back |
| 7 cancelled | too few players arrived: everyone goes back to the front of the queue |

A player who would die is eliminated instead and becomes an invisible spectator on the same map: they can watch the
players still alive (`RSPEC`), queue again (`QJOIN B`) or leave. Until the match has a winner a spectator cannot
whisper players still in the fight, nor use guild, officer or channel chat. Logging out or leaving the battleground
while alive forfeits the match.

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
so is leaving the queue (`QLEAVE`, logging out) while the ready check is open, even after accepting it. A player who
declines cannot queue for 120 s. When enough players accept (`minPlayers`, 20), the match starts and
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
| too many players from the player's IP address are queued, on the loading screen into a match or playing | `ERR` `royale_ip` |
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
the next player alive, 2 to the previous one. The server sends `ROYS` with the new `watchName`. It works from the
elimination on (`me` 3): during the 3 s the eliminated player lies on the ground the choice is kept, and the camera
moves there when they become a spectator.

| Check | Answer |
|---|---|
| malformed (`dir` not 0, 1 or 2) | dropped silently (section 1) |
| the player's `RSPEC` rate (section 8; the same `dir` again is not a duplicate) | `ERR` `busy` |
| Bleakhold Royale is off | `ERR` `royale_off` |
| the player is not eliminated or spectating in a match (`me` 3) | `ERR` `royale_phase` |
| nobody is alive to watch | `ERR` `royale_nobody` |

`GET ROYS` is answered with `ROYS` then a full `ROYO`, `GET ROYM` with `ROYM`; nothing is sent to a player who is not
in a match. After a `/reload` in a match the client sends `GET ROYS;ROYM` once `HELLO` is answered.

### ROYS (the match as the player sees it)

`matchId, phase, phaseMsLeft, alive, total, me, kills, placement, pinX, pinY, stage, curX, curY, curR, nextX, nextY, nextR, shrinkStartMs, shrinkEndMs, dmgPermille, watchName, myX, myY, stages`

- `matchId`: the match; another id is another match.
- `phase`: the table above. `phaseMsLeft`: until the next phase (the countdown in phase 1; in phase 2 until the last
  player falling is put on the ground at the latest).
- `alive`: players still in the fight; `total`: players in the match (who dropped, or are in the lobby before it).
- `me`: 0 in the lobby, 1 dropping, 2 alive, 3 spectating, 4 left, 5 the winner.
- `kills`: the player's eliminations. `placement`: empty while the player is in the fight.
- `pinX`, `pinY`: the player's snapped landing pin; empty when none is set.
- `stage`: the storm stage, 1 to `stages` (0 before the first circle is shown); `stages` + 1 in overtime (phase 4).
- `curX`, `curY`, `curR`: the storm circle when the message was sent.
- `nextX`, `nextY`, `nextR`: the next circle; empty until it is shown.
- `shrinkStartMs`, `shrinkEndMs`: until the next shrink starts and ends. `shrinkStartMs` 0 and `shrinkEndMs` above 0:
  the circle is shrinking now, `cur` moves linearly to `next` over `shrinkEndMs`. Both empty: no shrink is planned.
- `dmgPermille`: the storm damage outside the circle now, in permille of maximum health per second.
- `watchName`: for a spectator, the player they watch; empty otherwise.
- `myX`, `myY`: the player's position (the map arrow when the client cannot place the player itself).
- `stages`: how many stages the storm has in this match (1 to 16, the server's `Storm.Stages`; six by default). A
  server that leaves it empty has six.

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
`ROYS` phase 1 and `ROYV R` (the first circle) -> phase 2: the drop, `RDEPLOY` -> everyone landed, phase 3:
`ROYV S` as the storm moves, `ROYV D`, `L`, `O` for supply drops, `ROYO` for orbs, `ROYK` for every elimination,
`ROYV N` -> eliminated: `ROYE`, then `ROYS` with `me` 3 and `RSPEC` -> one player left: `ROYV W`, `ROYS` phase 5 and
the winner's `ROYE` -> phase 6 -> back in the world: `QUEUE` state 0. A cancelled match: `ROYS` phase 7 and `QUEUE`
state 1 again.

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
| `royale_phase` | `RDROP` outside the lobby or after the pins locked; `RSPEC` from a player who is not eliminated or a spectator |
| `royale_nobody` | `RSPEC` with nobody alive to watch |
| `glide_here` | `GLIDE` in a battleground, an arena or on the Royale map (section 16) |

```
C> 1 QJOIN 7 1/1 B,901,0,4,1
S> 1 QUEUE f 1/1 4,1,B,901,0,1,12,,,,80,80,13,20,40,,,1
S> 1 QUEUE g 1/1 5,2,B,901,0,1,95,,412,15,80,80,24,20,40,0,24,1
C> 1 QREPLY 8 1/1 412,1
S> 1 QUEUE h 1/1 6,3,B,901,0,1,,,,,80,80,,20,40,,,2
S> 1 ROYM i 1/1 901,-1066,533,-1066,533,455,455,32,750,-267,-267;1,L,-266,-266,88,The Bleak Hold;2,L,120,80,62,Harrow Farm
S> 1 ROYS j 1/1 7001,1,45000,24,24,0,0,,,,0,-267,-267,1080,,,,,,0,,450,452,6
C> 1 RDROP 9 1/1 104,96
S> 1 ROYS k 1/1 7001,1,41000,24,24,0,0,,104,96,0,-267,-267,1080,,,,,,0,,450,452,6
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

## 19. World PvP and War Mode

**War Mode** is each character's own choice to fight other players in the open world. A character with War Mode on
is flagged for PvP everywhere except sanctuaries, earns more experience and honor there, can capture World PvP
objectives, and can become **Wanted**. **World PvP objectives** are outposts in a few open-world zones that the
factions capture and hold: rotating **Fronts** (an endgame Bleak Front at the level cap and a Levelling Front for a
level band), plus extra War Mode rewards on the stock objectives of Hellfire Peninsula, Nagrand, Terokkar Forest,
Zangarmarsh, the Eastern Plaguelands and Grizzly Hills (their native capture bars keep working).

The server decides everything: who may turn War Mode on or off, every kill and its reward, every capture, who is
Wanted, who may claim a bounty, and when a Front starts and ends. The client only asks: `WARMODE` (turn War Mode on or
off) and `GET` (`WMST`, `WPZ`, `WPMAP`, `WANTED`). Everything else it shows comes from the six server ops of this
section, all unrevisioned (section 5).

`HELLO` feature bit 16384 is on while War Mode is live, and bit 32768 while the objectives are live. The server turns
them on at runtime once its own checks pass and off when the feature is switched off; clients already connected get a
new `HELLO` (section 7). Bit 32768 is only ever on together with 16384 (only War Mode players capture). While bit
16384 is off the server answers `WARMODE` with `ERR` `wm_off` and sends none of these messages.

**Names** of characters are at most 48 bytes, names of objectives and zones at most 40. **Positions** on a map are
`u`, `v` in permille of the zone's world map: 0 left / top, 1000 right / bottom, the same frame as the client's
`GetPlayerMapPosition` (times 1000). They are empty for a zone without a world map of its own (old Mount Hyjal); the
client then lists the objectives without pins. **Times** count from the moment the message arrives; the client counts
them down itself. **Factions** are letters: `A` Alliance, `H` Horde, `N` neutral (objectives only); an empty field is
nobody.

### War Mode

**Turning it on or off** (`WARMODE on`: 1 on, 0 off; the War Board NPC's gossip and the `.warmode on|off` command run
the same checks for players without the addon), in this order:

| Check | Answer |
|---|---|
| malformed (`on` not 0 or 1) | dropped silently (section 1) |
| the same `on` as the player's last accepted `WARMODE`, within 1 s | dropped silently (section 8) |
| the player's `WARMODE` rate (section 8) | `ERR` `busy` |
| War Mode is off on the realm (no feature bit 16384) | `ERR` `wm_off` |
| the player already is in the state asked for | `WMST`; nothing changes (a repeated intent is never an error) |
| turning it on below the minimum level (the server's `MinLevel`, 20) | `ERR` `wm_level` |
| turning it on as a hardcore or Iron Man challenge character (a PvP death would end it for good) | `ERR` `wm_hardcore` |
| dead | `ERR` `dead` |
| in combat, or in PvP combat | `ERR` `in_combat` |
| in an instance, a battleground, an arena or Bleakhold Royale; on a taxi or flying; in GM mode | `ERR` `wm_busy` |
| not resting in an inn or a city | `ERR` `wm_place` |
| turning it off while Wanted | `ERR` `wm_wanted` |
| less than 15 minutes (the server's `ToggleCooldownSec`, 900 s) since the last change | `ERR` `wm_cooldown` (the text gives the seconds left) |

The level and the hardcore checks never refuse turning War Mode off (a player below a `MinLevel` raised since, or a
hardcore character, can always turn it off). On success the server sends `WMST` and a `TOAST`. **On**: the PvP flag is
set at once and kept on everywhere the core allows PvP (sanctuaries such as Dalaran and Shattrath still block it).
**Off**: War Mode and its bonuses end at once; the PvP flag fades after the core's usual 5 minutes, so turning it off is
never an escape from a fight. The choice is saved with the character. While War Mode is live the server ignores the
game's own `/pvp` toggle and tells the player to use War Mode instead.

**Fights.** This is a PvE realm: a War Mode player can attack only players who are flagged for PvP. A player without
War Mode who attacks or heals a War Mode player is flagged by the core for 5 minutes (an **aggressor**); the server
counts aggressors for nothing but honor.

**Bonuses** (open world only: Eastern Kingdoms, Kalimdor, Outland and Northrend, outside instances, battlegrounds and
arenas and outside the server's excluded zones, Wintergrasp and GM Island by default). All bonuses of this section add
up and the total is capped at +40% (the server's `BonusCapPct`):

| Bonus | Who | Default |
|---|---|---|
| War Mode | War Mode players: kill and quest XP (below the level cap) and honor from player kills | +10% XP, +10% honor; +0% Shards |
| Underdog | War Mode players of the outnumbered faction: the same, and Shards from War Mode sources | 0 to +20% |
| Dominion | every player of the faction that holds outposts of a Front zone, in that zone (War Mode or not), per outpost held | +3% XP, +3% reputation, +5% honor |
| Victor's Resolve | the War Mode players of the faction that won the last Front, for 2 hours, in the open world | +5% XP, +10% honor |

- **Underdog**: every minute the server counts the War Mode players in the open world (level 20 and up, not away, by
  their own faction, one per IP address), keeps hourly averages for 24 hours and blends them half and half with the
  count now. With `big` and `small` the two counts, the outnumbered faction gets `round(20 * (big + 2) / (small + 2) -
  20)` percent, at most 20, and nothing while fewer than 6 are counted in all. It is recalculated every 15 minutes.
- **Player kills** give experience below the level cap: twice the experience of a creature of the victim's level, to
  the player who dealt the killing blow (a pet's, a totem's or a damage over time's killing blow counts for its owner).
- **Shards** (at the level cap, while the Dungeon Journey is on) come from bounties, captures and Front victories.
- **Daily caps** (the day of the Dungeon Journey, which resets at the server's `DailyResetHour`): bonus honor at most
  30 times the honor of a same-level kill (3,720 at level 80), and 60 War Mode Shards. The honor the core gives on its
  own is never capped.

**Kills that count** (for the streak, bounties, the XP and the War Mode honor bonus): the victim has had War Mode on
for at least 10 minutes, is of the other faction, the kill is in the open world, the two players use different
accounts and different IP addresses, the victim is less than 8 levels below the killer and not grey to them, the
victim is not under respawn protection (below), and neither is grouped with a player of the other faction. A War Mode
player who kills an aggressor gets the honor bonus only (no streak, no XP).

**Diminishing returns**: honor and XP for killing players of the same account fall with every kill on the same day:
100%, 75%, 50%, 25%, then nothing. A kill worth nothing counts for nothing. A War Mode player killed by a player cannot
be killed for anything again for 60 s after resurrecting (the core's Honorless Target): no honor, streak, experience,
bounty or War Chest credit, and no bully verdict.

**Wanted**:

- **Streak** (`S`): 5 counted kills without dying, against at least 3 different accounts.
- **Bully** (`B`): killing a War Mode player 10 or more levels below who has had War Mode on for at least 10 minutes,
  unless that player struck first (hit the bully before the bully hit them, within the last 2 minutes; hitting back
  is not striking first). The kill pays nothing, and the bully is Wanted at once.
- A Wanted player is hunted for 15 minutes of open-world time (paused in sanctuaries, capitals, instances,
  battlegrounds, on a flight path and while logged out). Up to 3 Wanted players per zone are revealed to the enemy War
  Mode players of that zone, highest streak first, with their place on the map every 5 s (`WANTED`). A Wanted player
  cannot turn War Mode off.
- **Killed by enemy War Mode players**: the player who dealt the killing blow and the other enemy War Mode players who
  hurt the Wanted player in the last 30 s and are within 100 yards claim the bounty, at most 5 in all (the most recent
  first). A bounty is a counted kill: the killing blow claims only when its kill counts (with diminishing returns left),
  and every other claimant only when his own kill of the Wanted player would count (a bully, the same account or IP
  address, a group with the other faction or the level gap claims nothing). Each gets the whole bounty: honor
  `min(2 + 0.4 * (streak - 5), 8)` times the honor of a kill at the Wanted player's level (2 times for a bully below a
  streak of 5), and at the level cap `min(5 + (streak - 5), 15)` Shards (5 for a bully below a streak of 5).
- **Survived** the 15 minutes: a streak-Wanted player gets 2 times the honor of a kill and 5 Shards; a bully gets
  nothing. The streak starts again.
- **Any other death** (a creature, a fall, a player without War Mode) ends the hunt with no bounty.

### World PvP objectives

**Zones** (`kind`): `F` the endgame Bleak Front, `L` a Levelling Front, `S` a stock outdoor PvP zone, `W` Wintergrasp
(status only). The server's zones and outposts are data (its `bh_wpvp_zone` and `bh_wpvp_objective` tables); a
Front zone has up to 3 outposts.

**The schedule.** One endgame Front and one Levelling Front run at a time, each in its own rotation: 120 minutes
active, then 10 minutes of ceasefire, then the next zone of the rotation. The rotation takes only the zones that fit
the realm's level cap (a Front for level 80 waits until the cap is 80). A restart resumes the Front that should be
running. 15 minutes before a Front starts, when it starts and when it ends, every player with the addon gets `WPEV`
(`X`, `F`, `E`) and the realm a `[War]` line (section 10). During the ceasefire the outposts are frozen and neutral,
and nobody has Dominion.

**Capturing.** A player counts at an outpost while: War Mode has been on for at least 60 s, alive, not stealthed or
invisible, not flying or on a taxi, not away and not a GM, in the normal phase, within the zone's level band
(`levelMin`..`levelMax`) and within the outpost's radius (60 yards by default); at most 2 players per IP address count
at one outpost. Every second the bar moves by the difference between the two factions' counts, at most 5 (the server's
`MaxNet`): the side with more players pushes it. The bar runs from Horde full (-300) to Alliance full (+300) and the
outpost belongs to the side whose end it is in, beyond the neutral band (20%: 60 of 300). A lone player takes a
neutral outpost in 60 s and an enemy one in 6 minutes; 5 players or more take them in 12 s and 72 s.

`state` of an outpost (AzerothCore's own capture states): 0 neutral, 1 Alliance, 2 Horde, 3 neutral and the Alliance
is taking it, 4 neutral and the Horde is taking it, 5 the Alliance's but the Horde is taking it, 6 the Horde's but the
Alliance is taking it. Events (`WPEV`): `C` captured, `N` neutralised, `A` under attack (the holder's bar fell 10%
below full while the other side pushes; at most once a minute per outpost).

**Holding** (Fronts only):

- **Dominion**: one stack per outpost held, for every player of the holding faction in the zone (the bonuses above).
- **Supremacy**: holding every outpost of the zone adds +5% damage to creatures and -5% damage taken from creatures
  there. It never changes damage between players.
- Every 5 minutes the War Mode players of a holding faction in the zone (alive, not away, War Mode on for at least 5
  minutes) get a hold reward for each stack.

**Victory.** Each outpost held gives its faction 1 point per second. At the end of the Front the faction with more
points wins when its lead is at least 10% of all points; otherwise it is a draw. The winners' War Mode players get
Victor's Resolve for 2 hours. Every War Mode player who spent at least 10 minutes in the zone and took part (was at a
capture, made a counted kill there, or got 3 hold rewards) gets the **War Chest**; players who are offline at the end
get it at their next login within 7 days.

**Rewards** (HK is the honor of a kill at the player's level, 124 at level 80; honor follows the realm's honor rate):

| Source | Below the level cap | At the level cap | Limit |
|---|---|---|---|
| a capture (Front or stock objective; only for players who stood at the outpost for 20 of the last 60 s) | 4% of the level's XP and 0.5 HK | 1.5 HK and 2 Shards | once per outpost per player every 30 minutes |
| the first capture of the day | +10% of the level's XP | +2 HK and 10 Shards | once a day |
| a hold reward | 0.5% of the level's XP per stack | 0.2 HK per stack | the daily caps |
| a counted kill at an outpost the killer's faction holds | the kill's reward +50% | the same | diminishing returns |
| the War Chest of the winners | 10% of the level's XP | 4 HK and 10 Shards | once per Front |
| the War Chest of the losers or of a draw | half of that | half of that | once per Front |

### WMST (the player's War Mode)

`on, cooldownSec, block, minLevel, xpPct, honorPct, shardPct, underdogPct, underdogTeam, wmAlliance, wmHorde, streak, wantedState, wantedSec, bountyHonor, todayBonusHonor, bonusHonorCap, todayShards, shardsCap, bestStreak, kills, deaths`

- `on`: 1 War Mode on, 0 off. `cooldownSec`: until War Mode may be changed again (0: now).
- `block`: a reason the server would refuse a change now that the client cannot see itself: `wm_level` or `wm_hardcore`
  (only while off), `wm_wanted` (while on) or `wm_busy`; empty otherwise. The client greys its button itself while the
  player is not resting (`IsResting()`) or is in combat.
- `minLevel`: the level War Mode needs to be turned on (the client greys its button below it only while War Mode
  is off).
- `xpPct`, `honorPct`, `shardPct`: the base War Mode bonuses (`xpPct` 0 at the level cap).
- `underdogPct`, `underdogTeam`: the underdog bonus now and the faction that gets it (empty: none).
- `wmAlliance`, `wmHorde`: the War Mode players the underdog bonus counted (blended, one per IP address).
- `streak`: counted kills since the player last died. `wantedState`: 0 not Wanted, 1 Wanted for a streak, 2 Wanted as
  a bully. `wantedSec`: hunt time left. `bountyHonor`: the honor the player's bounty pays each claimant.
- `todayBonusHonor` of `bonusHonorCap`, `todayShards` of `shardsCap`: today's War Mode bonus honor and Shards.
- `bestStreak`, `kills`, `deaths`: the best streak, the counted kills and the deaths to players while in War Mode, all
  time.

Sent after `HELLO`, for `GET WMST`, after every `WARMODE`, and whenever one of its fields changes for another reason
(a kill, a streak, Wanted, a reward, the underdog bonus, the daily reset, a new level, entering or leaving an instance,
a battleground or a flight), at most once a second.

### WPZ (the zone the player is in)

First record: `zoneId, kind, state, secondsLeft, controlA, controlH, dominionTeam, dominionStacks, levelMin, levelMax`.
Then one record per outpost (at most 16): `O, objId, name, u, v, owner, slider, state`.

- `kind`: `F`, `L` or `S`; empty for a zone without objectives of its own (Wintergrasp too: it is only in `WPMAP`),
  and then nothing else follows `zoneId`; the client hides its Front display.
- `state`: 0 dormant (a Front zone whose turn it is not), 1 active, 2 ceasefire. `secondsLeft`: until the active phase
  or the ceasefire ends (0 for stock zones).
- `controlA`, `controlH`: the Front's points so far, in permille of all points (they add up to 1000 once anyone
  scored; empty outside a running Front).
- `dominionTeam`, `dominionStacks`: the player's faction and its Dominion stacks here (empty and 0 when it holds
  nothing).
- `levelMin`, `levelMax`: who may capture here (empty: anyone in War Mode).
- `owner`: `A`, `H` or `N`. `slider`: the bar, -1000 Horde full .. 1000 Alliance full. `state`: the capture states
  above.

Sent when the player enters or leaves a zone with objectives (the next second), when an outpost of the zone changes
owner or state, when the Front's phase changes (also when its turn ends: state 0 to the players still there), every
30 s while the player is in a zone with objectives, and for `GET WPZ`. Nothing is sent for a move between two zones
without objectives, so a `WPZ` without `kind` may be for a zone the player has left since.

### WPCAP (the capture bar)

`objId, slider, neutralPct, state, countA, countH, maxNet`

- `objId`: the outpost the player stands at; 0 when the player has just left it (the client hides the bar).
- `slider`: -1000 .. 1000 as in `WPZ`. `neutralPct`: the neutral band, a share of each half of the bar (20: the
  middle 20% of each side, -200 .. 200, is neutral).
- `countA`, `countH`: the players who count at the outpost now; `maxNet`: the most the difference can push.

Sent every second to the players inside an outpost's radius (only while World PvP is live), and once with `objId` 0
when they leave it.

### WPMAP (every Front and objective)

First record: `frontZone, frontState, secondsLeft, nextZone, nextStartsSec, levelZone, levelState, levelSecondsLeft`.
Then one record per zone (at most 32): `Z, zoneId, kind, heldA, heldH, neutral, levelMin, levelMax, state`, and one per
objective (at most 96): `P, zoneId, objId, owner, state`.

- `frontZone`, `frontState`, `secondsLeft`: the endgame Front now (0 when none fits the level cap), its state (0 1 2
  as in `WPZ`) and the seconds until its active phase or ceasefire ends. `nextZone`, `nextStartsSec`: the next
  endgame Front and the seconds until it starts.
- `levelZone`, `levelState`, `levelSecondsLeft`: the same for the Levelling Front.
- `Z`: `heldA`, `heldH`, `neutral`: outposts by owner (Wintergrasp: 1 for the defending faction); `state`: 1 a
  running Front, a stock zone or a Wintergrasp battle, 2 a Front in ceasefire, 0 otherwise.
- `P`: `owner` and `state` as in `WPZ`.

Sent for `GET WPMAP` and to every player with the addon when a Front starts, ends or goes into ceasefire.

### WANTED (Wanted players in the zone)

First record: `zoneId`. Then one record per revealed Wanted player (at most 3 per zone, at most 8 in the message):
`W, name, classId, team, streak, reason, bountyHonor, bountyShards, u, v, ageSec`.

- `reason`: `S` a streak, `B` a bully. `bountyHonor`, `bountyShards`: what each claimant gets.
- `u`, `v`: where the Wanted player is (the map pin). `ageSec`: since the player became Wanted.

Sent every 5 s to the enemy War Mode players in a zone while it has a revealed Wanted player, once with no `W` records
when the last one there stops being Wanted, and for `GET WANTED` (to War Mode players).

### WPEV (World PvP events)

The first field is the kind; the fields after it depend on it:

| `kind` | Fields | Meaning | Sent to |
|---|---|---|---|
| `C` | `zoneId, objId, team, name` | `team` captured the outpost `name` | the players in the zone |
| `N` | `zoneId, objId, team, name` | `team` neutralised it | the players in the zone |
| `A` | `zoneId, objId, team, name` | `team` is attacking it | the players in the zone |
| `F` | `zoneId, durationSec, name` | the Front in zone `name` started; it lasts `durationSec` | every player with the addon |
| `E` | `zoneId, winner, controlA, controlH` | the Front ended; `winner` empty for a draw; the points in permille | every player with the addon |
| `X` | `zoneId, startsInSec, name` | the next Front starts in `startsInSec` | every player with the addon |
| `W` | `name, classId, team, streak, reason` | `name` became Wanted (`reason` `S` or `B`) | the War Mode players in the zone |
| `B` | `killer, victim, honor, shards` | `killer` claimed the bounty on `victim` | the War Mode players in the zone |
| `S` | `name, honor, shards` | `name` survived the hunt | the War Mode players in the zone |
| `R` | `why, honor, xp, shards, drPermille` | the player's own reward: `why` `K` a kill, `C` a capture, `H` a hold reward, `B` a bounty, `S` surviving the hunt, `V` the War Chest; `drPermille` the diminishing-return factor applied (1000 full) | the player |

`R` shows what was paid, after the realm's honor rate, the daily caps and diminishing returns.

### Without the addon

`.warmode` shows the player's War Mode and `.warmode on|off` changes it; the War Board NPC offers the same in its
gossip. Captures, Wanted players, bounties and Front starts are also told in chat. The stock zones keep their native
capture bars.

### A Front

`HELLO` with bits 16384 and 32768 -> `WMST` -> `GET WMST;WPZ;WPMAP;WANTED` -> `WARMODE 1` (answered by `WMST`) ->
`WPEV X`, then `WPEV F` and `WPMAP` -> the player enters the Front zone: `WPZ` -> at an outpost: `WPCAP` every second,
`WPEV A`, `C` or `N` and a new `WPZ` when it changes hands, `WPEV R` for the capture reward -> kills: `WMST` with the
streak, `WPEV W` and `WANTED` every 5 s when someone becomes Wanted, `WPEV B` or `S` when the hunt ends -> `WPEV E`
and `WPMAP` at the end, `WPEV R` with the War Chest.

### Error codes

| Code | Meaning |
|---|---|
| `wm_off` | War Mode is off on this realm (no feature bit 16384) |
| `wm_level` | turning War Mode on below the level it needs |
| `wm_hardcore` | turning War Mode on as a hardcore or Iron Man challenge character |
| `wm_place` | not resting in an inn or a city |
| `wm_cooldown` | War Mode was changed less than 15 minutes ago (the text gives the seconds left) |
| `wm_wanted` | turning War Mode off while Wanted |
| `wm_busy` | in an instance, a battleground, an arena or Bleakhold Royale; on a taxi or flying; in GM mode |
| `dead`, `in_combat`, `busy` | the generic codes (dead; in combat; over the `WARMODE` rate, section 8) |

```
C> 1 GET 2a 1/1 WMST;WPZ;WPMAP;WANTED
S> 1 WMST 2b 1/1 0,0,,20,0,10,0,8,H,31,22,0,0,0,0,0,3720,0,60,7,118,96
C> 1 WARMODE 2c 1/1 1
S> 1 ERR 2d 1/1 WARMODE,2c,wm_place,War Mode can only be changed in an inn or a city.
C> 1 WARMODE 2e 1/1 1
S> 1 WMST 2f 1/1 1,900,,20,0,10,0,8,H,31,22,0,0,0,0,0,3720,0,60,7,118,96
S> 1 WPEV 2g 1/1 X,2817,900,Crystalsong Forest
S> 1 WPEV 2h 1/1 F,2817,7200,Crystalsong Forest
S> 1 WPMAP 2i 1/1 2817,1,4320,66,4920,267,1,4320;Z,2817,F,2,0,1,80,80,1;Z,267,L,1,1,1,20,35,1;Z,3483,S,2,1,0,,,1;Z,4197,W,0,1,0,,,0;P,2817,1,A,1;P,2817,2,N,6;P,2817,3,A,1;P,267,11,A,1;P,267,12,H,2;P,267,13,N,0
S> 1 WPZ 2j 1/1 2817,F,1,4320,620,380,A,2,80,80;O,1,Violet Stand,512,388,A,1000,1;O,2,Forlorn Woods,604,455,N,-120,6;O,3,Sunreaver Rise,701,512,A,800,1
S> 1 WPCAP 2k 1/1 2,-120,20,6,2,3,5
S> 1 WPEV 2l 1/1 A,2817,3,H,Sunreaver Rise
S> 1 WPEV 2m 1/1 C,2817,2,A,Forlorn Woods
S> 1 WPEV 2n 1/1 R,C,186,0,2,1000
S> 1 WMST 2o 1/1 1,512,,20,0,10,0,8,H,31,22,3,0,0,0,412,3720,6,60,7,121,96
S> 1 WPEV 2p 1/1 W,Garrick Stormwind,4,H,5,S
S> 1 WANTED 2q 1/1 2817;W,Garrick Stormwind,4,H,5,S,248,5,560,402,35
S> 1 WPEV 2r 1/1 B,Aldric,Garrick Stormwind,248,5
S> 1 WANTED 2s 1/1 2817
S> 1 WPEV 2t 1/1 S,Brenna,248,5
S> 1 WPEV 2u 1/1 N,2817,1,H,Violet Stand
S> 1 WPEV 2v 1/1 E,2817,A,640,360
S> 1 WPEV 2w 1/1 R,V,496,0,10,1000
S> 1 WPZ 2x 1/1 4395
C> 1 WARMODE 2y 1/1 0
S> 1 ERR 2z 1/1 WARMODE,2y,wm_cooldown,You can change War Mode again in 296 s.
```

The player looks at War Mode (off), turns it on outside an inn (refused), then inside one. A Front is announced in
Crystalsong Forest and starts. The player's faction holds two of its three outposts; at the third the Alliance pushes
the Horde's bar back through the neutral band (state 6) and captures it, paying the player 186 honor and 2 Shards.
After three counted kills, a Horde rogue becomes Wanted with a streak of 5 and a bounty of 248 honor and 5 Shards,
which Aldric claims; later another Wanted player survives the hunt. The Horde neutralises an outpost, the Alliance
wins the Front with 64% of the points and the player gets the War Chest. In Dalaran (no objectives) the Front display
hides, and turning War Mode off there is refused for another 296 s.

## 20. Arena seasons and the 1v1 ladder

Rated arena on Bleakhold runs in seasons: four ladders (1v1, 2v2, 3v3 and 5v5), each ranked on its own, end-of-season
rewards by tier, weekly rewards for rated wins, and a 1v1 queue the addon joins without a battlemaster. The server
decides everything: the season's dates and state, who is ranked, every cutoff, whether a match counted, who gets which
reward. The client shows what `ARENA`, `LB`/`LBME` board `A` and `DEF V`/`Q` tell it and sends only the player's
wishes: `GET ARENA`, `LBQ A`, `QJOIN A` and `QLEAVE`.

`HELLO` feature bit 65536 is on while the server's arena system runs (`Bleakhold.Arena.Enable = 1` and its startup
checks passed). The server turns it on and off at runtime; clients already connected get a new `HELLO` (section 7).
While the bit is off the server answers `QJOIN A` with `ERR` `arena_off`, and the client shows neither the Arena page nor
the Arena leaderboard. The 2v2, 3v3 and 5v5 teams are still made and managed in the game's own PvP window: the 3.3.5a
client has room for three arena teams only, so the 1v1 team never shows there.

**Seasons.** Arena seasons have their own numbers (1, 2, ...), separate from the content seasons of section 7 (`SEASON`,
`DEF S`) and from the core's arena season (the season vendors). A season is live for its weeks (12 by default), the last
7 days are its final week, and then rated arena closes until the next season starts (about 48 hours later). The
`state` of `ARENA`:

| `state` | | Rated arena |
|---|---|---|
| 0 none | no arena season has been scheduled | the realm's own setting |
| 1 live | the season runs | open |
| 2 final week | the last days of the season | open |
| 3 rated closed | the season ended: nobody can queue for rated arena; matches already running finish and count | closed |
| 4 final standings | the ladder is frozen; game masters review the results (about a day) before the rewards go out | closed |
| 5 rewards delivered | the rewards were handed out: online players get them at once, the others at their next login | closed |
| 6 upcoming | no season runs and the next one is scheduled | closed |

Skirmishes and the unrated 1v1 queue stay open in every state.

**Ladders.** Each bracket has its own ladder of the bracket's teams (a 1v1 team is one player) with at least
`Bleakhold.Arena.Ladder.MinGamesShown` (10) games this season, sorted by rating, then the team's matchmaking rating,
then season games, then the team id. The ladder of the current season is live (a few seconds old at most); a past
season's ladder is its final standings.

**Tiers.** The tiers (`DEF V`) are 1 Combatant, 2 Challenger, 3 Rival, 4 Duelist, 5 Gladiator, 6 Rank One and, in 1v1
only, 7 Class Champion. Only teams with enough season games for rewards (`Bleakhold.Arena.Eligible.MinGames.*`: 50 in
1v1, 30 in 2v2 and 3v3, 20 in 5v5) and no game master in the team count; `N` of the eligible teams decides the places of
each tier: `slots = max(ceil(N * topPermille / 1000), minSlots)`, rounded up, so a small ladder still has a Gladiator.
The slots never shrink toward a lower tier, never exceed `N`, and teams tied on rating with the last team inside a tier
are inside it too (Rank One is always the first team alone). A team gets the highest tier whose slots its place is in,
whose rating `floor` it has, and whose extra conditions it meets: Duelist and above need 10 games in the last 21 days,
Gladiator and Rank One need 50 season wins (75 in 1v1). A team that misses a condition gets the best lower tier it
meets, and nobody moves up into its place. The Class Champion of a class is its best ranked eligible 1v1 player, when
that player has 1700 rating and 75 wins (nobody moves up into the place). A 5v5 ladder with fewer than 10 eligible teams
gives Combatant only, and a ladder with fewer than 20 eligible teams gives no titles (a title reward pays its substitute
instead). The default cutoffs (the server's tables may differ, and `ARENA` `T` always says what they are now):

| Tier | 2v2 and 3v3: top, slots, floor | 1v1: top, slots, floor | 5v5: top, slots, floor |
|---|---|---|---|
| 6 Rank One | the first team, 2000 | the first player, 2000 | the first team, 1850 |
| 5 Gladiator | 0.5 %, 2, 2000 | 0.5 %, 3, 1950 | 0.5 %, 1, 1850 |
| 4 Duelist | 3 %, 4, 1800 | 3 %, 6, 1800 | 3 %, 2, 1700 |
| 3 Rival | 10 %, 0, 1650 | 10 %, 0, 1650 | 10 %, 0, 1550 |
| 2 Challenger | 35 %, 0, 1500 | 35 %, 0, 1500 | 35 %, 0, 1450 |
| 1 Combatant | every team, 1300 | every player, 1300 | every team, 1300 |

**Members.** In 2v2, 3v3 and 5v5 a member gets the team's tier when they are at the level cap, played at least 50 % of
the team's season games, and their personal rating is at most 150 below the team's rating. A member who played the
bracket's minimum games but misses the share or the rating gets Combatant at most. At most two characters of one account
get 1v1 rewards above Combatant (the best two). Each tier also gets the rewards of the tiers below it (`DEF Q`). A title
the character already has, a mount or item the account already got this season or the character already owns, pays the
reward's substitute (200 Dungeon Shards) instead. Currencies (Shards, honor) are paid in full for the character's best
bracket and at 50 % for each other bracket.

**Match verdicts.** A rated match the server judges to be traded does not count normally; `ARENA` `M` shows each
player the verdict of their last matches, so nobody loses or misses rating silently:

| `verdict` | `reason` | When |
|---|---|---|
| 0 counted | | a normal match |
| 1 reduced | `R` | the same two teams (or the same accounts) met for the 4th to 6th time within 24 hours: the winner gains half |
| 2 win not counted | `R` | ... for the 7th time or more |
| 2 win not counted | `I` | a winner and a loser play from the same network |
| 2 win not counted | `E` | the match ended within a minute of the gates opening and the losers did next to nothing |
| 2 win not counted | `S` | the match was over within 15 seconds of the gates opening |

A win that does not count gives the winners no rating, no matchmaking rating, no win and no game; the losers lose as
usual. At the end of the season the rewards of a team are held for a game master's review when, with at least 20 season
wins, at least 30 % of its wins came against the same opponents or at least 40 % of its rating gain came from reduced
wins, and those of a player with a same-network or low-effort match a game master has not cleared yet: the rewards wait
(`missingMask` 64, `F` `grant` 2) until the review releases or withholds them. Their place on the ladder stays.

### The 1v1 queue

`QJOIN A,1,tier,roles,size` joins the 1v1 arena queue: `activityId` is always 1, `tier` 0 for a skirmish (unrated) or 1
for rated, `size` always 1; `roles` (1..7) is ignored. Anything else is malformed and dropped. A rated join without a 1v1
team makes the team first, for `oneTeamCostCopper` (`ARENA` header; the addon asks the player to confirm a cost first).
A repeated `QJOIN A` while queued only sends `QUEUE` again. `QLEAVE` leaves the 1v1 queue (the Royale queue first, when
the player is in that one; section 17). The game's own invite dialog takes the player into the match.

`QJOIN A`, in this order:

| Check | Answer |
|---|---|
| malformed (for `A`: `activityId` not 1, `tier` not 0 or 1, `size` not 1) | dropped silently (section 1) |
| the player's `QJOIN` rate (section 8) | `ERR` `busy` |
| the arena system is off (no feature bit 65536), the 1v1 arena is off on the realm, or the UI queue is off | `ERR` `arena_off` (`unavailable` on a realm without the UI bridge) |
| the player is below the 1v1 level (80) | `ERR` `arena_level` |
| `tier` 1 and rated arena is closed (`state` 3 to 6, or 0 with the realm's rated arena closed) | `ERR` `arena_closed` (the text says when it opens again) |
| the player is in a group, an instance, a battleground or an arena, any battleground, arena, dungeon finder or Bleakhold Royale queue, or in combat | `ERR` `arena_busy` |
| the player has Deserter | `ERR` `arena_deserter` |
| the player's talents are not allowed in 1v1 (the realm's healer, tank or talent-tree rules) | `ERR` `arena_talents` |
| `tier` 1, no 1v1 team, and the player cannot pay for one | `ERR` `arena_gold` |
| `tier` 1, no 1v1 team, and it could not be made (or the realm makes none from the UI) | `ERR` `arena_team` |

`QUEUE` for kind `A` has the fields of section 7 up to `estWaitSec` and nothing after them:

- `state`: 0 not queued, 1 queued (also while the game's invite dialog is open), 3 in the match.
- `activityId` 1; `tier` 0 skirmish or 1 rated; `size` 1.
- `queuedSec`: time in the queue so far; `estWaitSec`: the server's average wait (empty when it has none).

### ARENA (the player's arena season)

First record: `seasonId, state, startEpoch, endEpoch, nextStartEpoch, ratedOpen, oneTeamCostCopper, seasonName`.

- `seasonId`: the season `state` is about (the current one, the last one in states 5, or the next one in state 6); 0
  with `state` 0.
- `startEpoch`, `endEpoch`: its start and end (Unix time). `nextStartEpoch`: when the next season starts, once it is
  scheduled.
- `ratedOpen`: 1 while rated arena games count.
- `oneTeamCostCopper`: what a 1v1 team costs (0 free); empty when the 1v1 queue is off.

Then records tagged by their first field:

- `S, id, name, state, startEpoch, endEpoch`: an arena season (`state` 0 past, 1 current, 2 upcoming), at most 24, for the
  season choice of the arena leaderboard.
- `B, bracket, hasTeam, rating, ladderRank, ladderSize, seasonGames, seasonWins, weekGames, weekWins, personalRating,
  recentGames, tierId, nextTierId, ratingToNext, missingMask, teamName`: the player in one bracket. Always sent for 1v1
  (with `hasTeam` 0 and nothing else when the player has no 1v1 team), for 2v2, 3v3 and 5v5 only when the player has a
  team. `ladderRank` of `ladderSize`: the place on the shown ladder (empty below its minimum games). `recentGames`: the
  team's rated games in the last 21 days. `tierId`: the tier the player would get if the season ended now (empty: none);
  `nextTierId` and `ratingToNext`: the tier above and the rating it takes now. `missingMask`, what keeps the player from
  the rewards of `tierId` or above: 1 too few season games, 2 too small a share of the team's games, 4 personal rating
  too far below the team's, 8 too few recent games (Duelist and above), 16 too few wins (Gladiator and Rank One), 32 not
  at the level cap, 64 rewards held for review, 128 the bracket gives no rewards beyond Combatant this season.
- `T, bracket, tierId, slots, cutRank, cutRating, floor`: the live cutoff of one tier of one bracket. `slots`: the places
  of the tier; `cutRank`, `cutRating`: the last team inside it now (empty: nobody); `floor`: the rating the tier needs
  anyway. What a tier takes now is the higher of `cutRating` and `floor`.
- `N, bracket, eligibleTeams, rewardsOpen, titlesOpen`: one bracket's ladder. `rewardsOpen` 0: too few teams, Combatant
  only; `titlesOpen` 0: too few teams for titles.
- `M, bracket, won, ratingChange, opponent, endEpoch, verdict, reason`: one of the player's last five rated matches,
  newest first (`verdict` and `reason` as above).
- `F, bracket, finalRank, finalRating, finalTierId, grant`: the player's final standing in one bracket, in states 4 and
  5 only. `grant`: 0 the rewards are coming, 1 delivered, 2 held for review.

The server sends `ARENA` after `HELLO` while feature bit 65536 is on, for `GET ARENA`, to every player of a rated match
after it ends, and to every player when the season's `state` changes. The client also sends `GET ARENA` after each
`HELLO` with the bit (a push made at login, before the client's `HELLO`, does not reach it, and `/reload` has none).
Cutoffs move with every match: the client asks with `GET ARENA` again (every 30 s at most) while it shows them.
Unrevisioned; the last one counts.

### LB and LBME, board A

`LBQ A,seasonId,bracket,classId,page`: `seasonId` an arena season (0 the current one), the bracket in `dungeonId` (1, 2,
3 or 5; never 0), `classId` the teams with a member of that class (0 all). The answer is `LB` with these rows:

`rank, bracket, rating, , lastGameEpoch, members (list of name~classId), teamName, seasonWins, seasonGames, tierId, flags`

- `rating` in the `value` field, `timeSec` empty, `lastGameEpoch` in `dateEpoch`, the team's name in `label`.
- `tierId`: the tier the team would get now (a past season: the tier it got), `flags`: 1 inactive (no game for 7 days),
  2 provisional (below the games the bracket needs for rewards), 4 final standings.

`LBME`: `A, rank, topPercent, rating, bracket, , barPermille, tierName, topPermille, tierId`: the player's own team in
that bracket. `topPermille` is the rank in permille of the ladder (`topPercent` is too coarse near the top: 4 of 1000 is
0.4 %); `barPermille`: the way from the floor of the team's tier to what the next tier takes now; `tierName` is in
`label`. Both are empty but `A` when the player has no team there.

### DEF V and Q

| Kind | Record |
|---|---|
| `V` arena tier | `id, name, colorHex, text` |
| `Q` arena reward | `id, seasonId, bracket, tierId, kind, entry, count, text` |

`Q` lists every end-of-season reward: `seasonId` 0 for every season (a row of one season replaces the row of the same
bracket, tier and kind of season 0), `kind` `T` a title (`entry` the achievement that grants it), `M` a mount (`entry` the
item), `I` an item, `X` the season set's looks (`entry` a look pack), `C` Dungeon Shards, `H` honor, `A` arena points,
`W` war effort, `F` a server first (section 7, `FIRSTS`); `count` the amount.

### Error codes

| Code | Meaning |
|---|---|
| `arena_off` | the arena system is off (no feature bit 65536), or the 1v1 arena or its UI queue is off on the realm |
| `arena_level` | below the 1v1 level |
| `arena_closed` | rated arena is closed (between seasons); the text says when it opens again |
| `arena_busy` | in a group, an instance, a battleground or arena, another queue (Bleakhold Royale's too) or in combat |
| `arena_deserter` | the player has Deserter |
| `arena_talents` | the player's talents are not allowed in 1v1 |
| `arena_team` | no 1v1 team, and none could be made |
| `arena_gold` | no 1v1 team, and not enough money for one |

```
C> 1 GET 1a 1/1 ARENA
S> 1 ARENA 2a 1/2 1,1,1793318400,1800576000,1800748800,1,0,Arena Season 1;S,1,Arena Season 1,1,1793318400,1800576000;S,2,Arena Season 2,2,1800748800,1808006400;B,1,1,1734,12,48,61,38,9,6,1734,14,3,4,66,0,Aldric;B,3,1,1912,4,22,44,30,12,8,1890,12,4,5,163,16,Ironvow Wardens
S> 1 ARENA 2a 2/2 ;T,3,6,1,1,2140,2000;T,3,5,2,2,2075,2000;T,3,4,4,4,1912,1800;T,3,3,4,4,1912,1650;T,3,2,8,8,1702,1500;T,3,1,22,22,1310,1300;N,1,48,1,1;N,3,22,1,1;M,1,1,14,Brenna,1793900000,0;M,1,0,-11,Corwin,1793899000,0;M,1,1,0,Dalia,1793898000,2,I;M,1,1,7,Eamon,1793897000,1,R
C> 1 LBQ 1d 1/1 A,0,3,0,1
S> 1 LB 2d 1/1 A,1,3,0,1,3;1,3,2140,,1793896400,Brenna~2:Corwin~5:Dalia~8,Dawnbreakers,61,70,6;2,3,2075,,1793890000,Eamon~11:Fenna~3:Garrick Stormwind~4,The Unbowed,55,68,5;3,3,1990,,1793200000,Hale~7:Isolde~9:Jorund~6,Ashen Pact,40,52,4,1
S> 1 LBME 2e 1/1 A,4,19,1912,3,,407,Duelist,182,4
S> 1 DEF 2f 1/1 V,7;1,Combatant,9D9D9D,Enough season games and 1300 rating.;5,Gladiator,FF8000,The top 0.5%25 of the ladder with 50 wins.
S> 1 DEF 2g 1/1 Q,7;101,0,3,2,T,2090,1,Challenger;105,1,3,5,M,30609,1,Swift Nether Drake;110,0,3,1,C,0,150,150 Dungeon Shards
C> 1 QJOIN 1b 1/1 A,1,1,4,1
S> 1 QUEUE 2i 1/1 7,1,A,1,1,1,8,95
C> 1 QJOIN 2j 1/1 A,1,1,4,1
S> 1 ERR 2k 1/1 QJOIN,2j,arena_closed,Rated arena opens again when Arena Season 2 starts.
S> 1 ARENA 2b 1/1 1,4,1793318400,1800576000,1800748800,0,0,Arena Season 1;B,1,1,1734,12,48,61,38,0,0,1734,14,3,4,66,64,Aldric;F,1,12,1734,3,2
```

The first `ARENA` is a live season: Aldric is 12th of 48 in 1v1 at 1734, on Rival pace, 66 rating short of Duelist; in
3v3 his team is the last Duelist (4th of 22) and would need 2075 for Gladiator, but has too few wins for it anyway
(`missingMask` 16). His match against Dalia did not count (the same network), the one against Eamon was a repeated
pairing (half the gain). The leaderboard shows 3v3 (the Ashen Pact has not played for a week), and the player's own team
4th, top 19 % (182 in permille). The `ERR` came when rated arena had closed; the last `ARENA` shows the final standings
with Aldric's 1v1 rewards held for review.
