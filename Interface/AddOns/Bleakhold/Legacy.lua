-- Bleakhold: the server's legacy Activities messages (ns.Legacy). The old BleakholdActivities addon read them, and the
-- server still sends them to every player (mod-bleakhold BHMP::Mgr::SendAddon, bh_mplus.cpp: a whisper to oneself
-- in LANG_ADDON, so CHAT_MSG_ADDON with prefix "BHMP" and ';'-separated fields). They carry what our own protocol
-- does not: the Journey board's offers and rotation, the best keystone per dungeon, the Eclipse Rift's bests by group
-- size, checkpoint and floor count, the riding offer and the first-login "open Activities". The old addon's chat
-- commands still do the old actions (.act, .rift, .mplus, .ride: SEC_PLAYER commands said in /say, which the server
-- takes as commands and never repeats).
--
-- Messages (fields after the tag; old handlers BleakholdActivities.lua :474-511, senders in mod-bleakhold):
--   H  rotation seconds, queued offer key, players queued, first run done (0/1), Journey on (0/1)  bh_activities.cpp:47-54
--      (it starts a new board: the J offers follow)
--   J  key, dungeon, tier (0 Normal .. 3 Nightmare), modifier bits, chapter, min level, status (0 open, 1 level,
--      2 chapter, 3 tier), best score %, best time s, runs, reward Shards, name, modifier names        bh_activities.cpp:62-65
--   K  dungeon id, level, timer s, name; or "K;0" for no keystone                                      bh_mplus.cpp:973-984
--   W  week index, "a1,a2,a3,a4" affix ids, champions/boons from level, hp % per level, damage % per level   :986-991
--   L  dungeon id, timer s, best keystone level, name (one per season dungeon)                        bh_mplus.cpp:993-998
--   U  best floor solo, duo, trio, group, checkpoint, min level, Rift on (0/1), floor now (0 outside), floor count
--                                                                                                       bh_rift.cpp:180-190
--   Z  3 when the group leader chose Mythic, else 0 (the server never sends 1 or 2)                    bh_mplus.cpp:866-869
--   RIDE  price in copper: the riding offer popup                                                       bh_leveling.cpp:236
--   A  page: open Activities there (A;journey at the first login at Journey level)                     bh_leveling.cpp:254
--   G  the group as OpenSocket sees it, just before O: "name:class:inside:leader:alive|..." (inside 1: in the
--      key's instance)                                                                   bh_mplus.cpp:1199-1217
--   O  dungeon id, level, timer s, hp %, damage %, damage %, affix ids, name: the keystone (or the Font of Power)
--      opened the start in its dungeon; Start keystone (KSTART) works for 300 s there    bh_mplus.cpp:1204 OpenSocket
--   X  no run here: on leaving a keystone dungeon (a Rift floor too), on .rift leave and a collapse
--                                                      bh_mplus_scripts.cpp:286, bh_rift.cpp:1082 RiftLeave, :345
--   S  the run the player is in, on entering its instance and at the run's start only (SendFullState; SendRiftState
--      for a Rift floor; never after a /reload, and not for .act mplus either: HandleMplus, bh_activities.cpp:137,
--      sends W, L, K, U and Z only): mode (2 Mythic 0, 3 keystone, 4 Eclipse Rift floor), dungeon
--      (mod-bleakhold's own bh_mp_dungeon id, which our protocol never carries: the bridge sends MplusUiId of it, the
--      map id or 100000 + the own id), level (a Rift floor: the floor), time limit s (0 untimed), affix ids, Mythic
--      Champions needed, enemy forces (0/1), name; then one B per boss and a T
--                                                                      bh_mplus.cpp:1261-1282, bh_rift.cpp:342-353
--   B  boss index (1..), role (1 shown, 2 extra: never blocks the end, 3 final), done (0/1), name     bh_mplus.cpp:1276
--   D  boss index: that boss died                                                       bh_mplus.cpp:2503, bh_rift.cpp
--   T  elapsed ms, deaths, death penalty s, forces done, forces needed, battle res charges, Mythic Champions slain,
--      state (0 idle, 1 countdown, 2 running, 3 done); every 5 s, on each change and on a battle res (a Rift floor's T
--      sends zeros but for elapsed, deaths and state); with no S since a /reload it keeps a partial run (H.T)
--                                                              bh_mplus.cpp:1254 SyncLine, bh_mplus_scripts.cpp:628
--   E  result, time, limit, old level, new level, caches, coins, 1, name: the run is over         bh_mplus.cpp:2665
--   Y  affix id, stacks on this player (6 Bursting, 8 Necrotic, 9 Grievous, 18 Pack Tactics: allies over 10 yd away);
--      0: gone (Necrotic at 1, 4, ... 43 stacks only, never at its cap of 45)  bh_mplus.cpp:2090-2225, scripts:542
--   V  boon (1 Power, 2 Vigor, 3 Warding), seconds: the group's Mythical Boon; V;0;0 when it fades  bh_mplus.cpp:2191
--      (only when it is claimed: not again on entering the instance, so a /reload or a corpse run loses it here while
--      the server keeps it)
--   Q  ms: the ground quakes under this player in that time                                       bh_mplus.cpp:2292
-- The other BHMP tags (C, M, N, R) are left to our own protocol (MPS's countdown, the toasts).
--
-- State: L.journey, L.mplus, L.rift (see below); ns.Fire("LEGACY", tag) after each message for the pages, or
-- ns.Fire("LEGACY_RUN", tag) for the run's (L.RUN_TAGS: the key tracker's, a T every 5 s); X and a Rift floor's S
-- fire both.
local ADDON, ns = ...
local U, Comm = ns.U, ns.Comm

local floor = math.floor

local L = {}
ns.Legacy = L

L.PREFIX = "BHMP"
L.REQUEST_EVERY = 5     -- seconds between two board requests (.act journey / .act mplus)
local INT = 2147483647

-- The Journey's tiers as the old window coloured them (old :17).
L.TIERS = { [0] = { name = "Normal", color = "FFFFFF" }, [1] = { name = "Veteran", color = "1FFF00" },
    [2] = { name = "Elite", color = "338CFF" }, [3] = { name = "Nightmare", color = "BF4DFF" } }
L.DIFFICULTIES = { [1] = "Normal", [2] = "Heroic", [3] = "Mythic" }
L.DIFFICULTY_COLORS = { [1] = "FFFFFF", [2] = "40C0FF", [3] = "A335EE" }

-- The run's mode, state and boss roles as S, T and B send them (bh_mplus.h Mode, State, BossRole).
L.MODE = { HEROIC = 1, MYTHIC0 = 2, KEY = 3, RIFT = 4 }
L.STATE = { IDLE = 0, COUNTDOWN = 1, RUNNING = 2, DONE = 3 }
L.ROLE = { SHOWN = 1, EXTRA = 2, FINAL = 3 }

-- The affixes Y counts on the player, in the server's ids (bh_mplus.h Affix, not our protocol's DEF A ids), with
-- their names (bh_mplus.cpp AffixName) and effects in the server's numbers (bh_mplus.cpp AffixNotices; Necrotic
-- -2% healing taken a stack up to 90%, Bursting 1.5% of the health a second a stack, Grievous 1% every 3 s a stack
-- below 90% health, Pack Tactics -5% damage done (at most -50%) and +5% taken a far ally).
L.STACK_AFFIXES = { 6, 8, 9, 18 }
-- Necrotic stops at 45 stacks, and the server sends its count at 1, 4, 7, ... only (bh_mplus_scripts.cpp: necro % 3
-- == 1), so it can trail by 2: its last count below the cap is 43, and a player at the cap is never told 44 or 45.
L.NECROTIC_MAX = 45
L.NECROTIC_LAST = L.NECROTIC_MAX - 2
L.STACKS = {
    [6] = { name = "Bursting", effect = function(n)
        return floor(n * 3 / 2) .. (n % 2 == 1 and ".5" or "") .. "% of your health each second"
    end },
    [8] = { name = "Necrotic", effect = function(n)
        -- Y comes at 43, never at the cap: the player may be at 45 (-90%) by now, and no Y will say so
        if n == L.NECROTIC_LAST then
            return "-" .. 2 * n .. "% to -" .. 2 * L.NECROTIC_MAX .. "% healing taken"
        end
        return "-" .. math.min(2 * L.NECROTIC_MAX, 2 * n) .. "% healing taken"
    end },
    [9] = { name = "Grievous", effect = function(n)
        return n .. "% health every 3 sec - heal above 90%"
    end },
    [18] = { name = "Pack Tactics", effect = function(n)
        return n .. (n == 1 and " ally" or " allies") .. " over 10 yd away (-" .. math.min(50, 5 * n) .. "% damage, +"
            .. 5 * n .. "% taken)"
    end },
}
-- The Mythical Boons (bh_mplus.cpp: the server's claim line), two minutes for the whole group.
L.BOONS = { [1] = { name = "Boon of Power", effect = "+15% damage" },
    [2] = { name = "Boon of Vigor", effect = "+15% healing" },
    [3] = { name = "Boon of Warding", effect = "-10% damage taken" } }

local function newAffix()
    return { stacks = {}, boon = 0, boonUntil = 0, quakeAt = 0 }
end

local function reset()
    -- the Journey board: offers in the server's order; rotAt is GetTime() when the board changes (0: unknown)
    L.journey = { offers = {}, byKey = {}, rotAt = 0, queuedKey = 0, queuedPlayers = 0, firstDone = false, on = true,
        known = false }
    -- Mythic+: key = { id, level, timer, name } or nil; week.affixes = { ids }; list = season dungeons in the server's
    -- order { id, timer, best, name }; z = the last Z (0 or 3); socket = { at, dungeon, level, name } from O while the
    -- keystone has opened the start (L.SocketArmed), else nil; group = the last G's members { name, class, inside,
    -- leader, alive } (kept with the socket: gone when it goes)
    -- run = the run the player is in (S, B, D, T; nil outside one, see H.S; partial from T alone, see H.T); affix =
    -- the player's affix stacks, boon and next quake (Y, V, Q)
    L.mplus = { key = nil, keyKnown = false, week = { index = 0, affixes = {}, champMinLevel = 0, hpPerLevel = 0,
        dmgPerLevel = 0 }, list = {}, byId = {}, z = 0, socket = nil, group = nil, run = nil, affix = newAffix() }
    -- the Eclipse Rift: best[1..4] = solo, duo, trio, group
    L.rift = { best = { 0, 0, 0, 0 }, checkpoint = 0, minLevel = 80, on = true, inFloor = 0, floors = 0, known = false }
    L.seen = false
    L.demoFed = false
end
reset()
L.Reset = reset

------------------------------------------------------------------------------------------------------
-- Parsing
------------------------------------------------------------------------------------------------------
local function int(v, lo, hi)
    return U.Int(v, 0, lo or 0, hi or INT)
end

-- Server text for a FontString: no control bytes, valid UTF-8, at most maxLen bytes (default 80; UI.SetText escapes
-- '|').
local function text(v, maxLen)
    if type(v) ~= "string" or v == "" then
        return ""
    end
    local s = v:gsub("%c", " ")
    return U.CutUtf8(U.CleanUtf8(s), maxLen or 80)
end
L.Text = text

-- How many fields each tag has; extra ';' are kept in the last field (a free text).
L.FIELDS = { H = 5, J = 13, K = 4, W = 5, L = 4, U = 9, Z = 1, RIDE = 1, A = 1, G = 1, O = 8, X = 0, S = 8, B = 4,
    D = 1, T = 8, E = 9, Y = 2, V = 2, Q = 1 }

function L.Split(msg)
    local parts = {}
    for f in (msg .. ";"):gmatch("([^;]*);") do
        parts[#parts + 1] = f
        if #parts > 64 then
            break
        end
    end
    local tag = table.remove(parts, 1)
    local n = L.FIELDS[tag]
    if n and n > 0 and #parts > n then
        parts[n] = table.concat(parts, ";", n)
        for i = #parts, n + 1, -1 do
            parts[i] = nil
        end
    end
    return tag, parts
end

local H = {}
L.handlers = H

function H.H(f)
    local j = L.journey
    j.offers, j.byKey = {}, {}
    local rot = int(f[1])
    j.rotAt = rot > 0 and (GetTime() + rot) or 0
    j.queuedKey = int(f[2])
    j.queuedPlayers = int(f[3], 0, 99)
    j.firstDone = f[4] == "1"
    j.on = f[5] ~= "0"
    j.known = true
end

function H.J(f)
    local j = L.journey
    local o = {
        key = int(f[1]), dungeon = int(f[2]), tier = int(f[3], 0, 3), mods = int(f[4]), chapter = int(f[5], 0, 99),
        minLevel = int(f[6], 0, 255), status = int(f[7], 0, 3), best = int(f[8], 0, 100), time = int(f[9]),
        runs = int(f[10]), reward = int(f[11]), name = text(f[12]), modNames = text(f[13], 200),
    }
    if o.key == 0 or #j.offers >= 64 then
        return
    end
    local old = j.byKey[o.key]
    if old then
        for k, v in pairs(o) do
            old[k] = v
        end
    else
        j.offers[#j.offers + 1] = o
        j.byKey[o.key] = o
    end
end

function H.K(f)
    local m = L.mplus
    m.keyKnown = true
    local id = int(f[1])
    if id == 0 then
        m.key = nil
    else
        m.key = { id = id, level = int(f[2], 0, 99), timer = int(f[3]), name = text(f[4]) }
    end
end

function H.W(f)
    local w = { index = int(f[1]), affixes = {}, champMinLevel = int(f[3], 0, 99), hpPerLevel = int(f[4], 0, 1000),
        dmgPerLevel = int(f[5], 0, 1000) }
    for a in (f[2] or ""):gmatch("%d+") do
        if #w.affixes < 4 then
            w.affixes[#w.affixes + 1] = tonumber(a)
        end
    end
    L.mplus.week = w
end

function H.L(f)
    local m = L.mplus
    local id = int(f[1])
    if id == 0 then
        return
    end
    local d = m.byId[id]
    if d then
        d.timer, d.best = int(f[2]), int(f[3], 0, 99)
        local name = text(f[4])
        if name ~= "" then
            d.name = name
        end
    elseif #m.list < 64 then
        d = { id = id, timer = int(f[2]), best = int(f[3], 0, 99), name = text(f[4]) }
        m.list[#m.list + 1] = d
        m.byId[id] = d
    end
end

function H.U(f)
    local r = L.rift
    r.best = { int(f[1], 0, 9999), int(f[2], 0, 9999), int(f[3], 0, 9999), int(f[4], 0, 9999) }
    r.checkpoint = int(f[5], 0, 9999)
    r.minLevel = int(f[6], 0, 255)
    r.on = f[7] == "1"
    r.inFloor = int(f[8], 0, 9999)
    r.floors = int(f[9], 0, 9999)
    r.known = true
end

function H.Z(f)
    L.mplus.z = int(f[1], 0, 3)
end

function H.RIDE(f)
    L.ShowRide(int(f[1]))
end

function H.A(f)
    local page = text(f[1]):lower()
    if page ~= "" then
        ns.Fire("LEGACY_OPEN", page)
    end
end

-- G: the group when the keystone opened the start (OpenSocket sends it just before O): who is inside the instance.
function H.G(f)
    local group = {}
    for member in (text(f[1], 1000) .. "|"):gmatch("([^|]*)|") do
        local name, class, inside, leader, alive = member:match("^([^:]*):(%d*):(%d*):(%d*):(%d*)$")
        if name and name ~= "" and #group < 40 then
            group[#group + 1] = { name = name, class = int(class, 0, 99), inside = inside == "1",
                leader = leader == "1", alive = alive == "1" }
        end
    end
    L.mplus.group = group
end

-- How many of the group were inside the key's instance when the keystone opened the start (the last G), or nil.
function L.GroupInside()
    local g = L.mplus.group
    if not g then
        return nil
    end
    local n = 0
    for _, m in ipairs(g) do
        if m.inside then
            n = n + 1
        end
    end
    return n
end

-- O: the keystone (or the Font of Power) opened the start in its dungeon (OpenSocket). Start keystone works there for
-- L.SOCKET_SECONDS (L.SocketArmed).
function H.O(f)
    L.mplus.socket = { at = GetTime(), dungeon = int(f[1]), level = int(f[2], 0, 99), name = text(f[8]) }
end

-- The run and the affix state end together: out of the instance (X), on a loading screen, after E (the run only).
local function clearRun()
    local had = L.mplus.run ~= nil or next(L.mplus.affix.stacks) ~= nil or L.mplus.affix.boon ~= 0
    L.mplus.run = nil
    L.mplus.affix = newAffix()
    return had
end

-- X: no run where the player is now (out of a keystone dungeon or a Rift floor; out of the rift by .rift leave or a
-- collapse; or SendFullState: in a keystone dungeon without a Mythic run). U's floor is over: the server sends no new U
-- then, and a player who only went one floor deeper gets the new floor's S;4 next. The keystone's start is gone too.
function H.X()
    L.rift.inFloor = 0
    L.mplus.socket = nil
    L.mplus.group = nil
    clearRun()
end

-- Our protocol's id (DEF D) of the Mythic+ dungeon named name, or nil. S carries mod-bleakhold's own dungeon id, which
-- the bridge never sends as is (MplusUiId: the map id, or 100000 + the own id for a second wing), but DEF D names a
-- key dungeon with the module's own name (bh_ui_bridge_map.cpp DungeonDefs), as S does: a single key dungeon (one
-- with a time limit) of that name answers; none or two, nil.
function L.KeyDungeonId(name)
    if type(name) ~= "string" or name == "" then
        return nil
    end
    local found
    for _, id in ipairs(ns.DefIds("D")) do
        local d = ns.Def("D", id)
        if type(d) == "table" and (tonumber(d.timeLimitSec) or 0) > 0 and text(d.name) == name then
            if found then
                return nil
            end
            found = id
        end
    end
    return found
end

-- S: the run the player is in, sent on entering its instance and at its start only (SendFullState, SendRiftState),
-- then a B per boss and a T: a new L.mplus.run = { mode, ownDungeon (S's id: mod-bleakhold's own), dungeon (our
-- protocol's, L.KeyDungeonId; nil for a Rift floor or when unknown), level, timer, affixes, champsNeeded, hasForces,
-- name, bosses = { [i] = { role, done, name } }, and from T: elapsed (ms), deaths, penalty, forcesDone, forcesNeeded,
-- bres, champsKilled, state; at = GetTime() of the last S or T }. A Rift floor's (mode 4: S;4;dungeon;floor;...) is
-- also the floor the player has just entered (L.rift.inFloor). A /reload is no entry: no S comes then (and no B, Y
-- or V) until the player leaves and enters again, so the run's T alone keeps a partial run meanwhile (H.T, L.Run).
-- The handshake asks again (.act mplus), but today's bleakserv answers that with W, L, K, U and Z only; the run's S,
-- B and T come back there only once its HandleMplus also calls SendFullState (asked of the server side).
function H.S(f)
    local mode = int(f[1], 0, 4)
    local name = text(f[8])
    local run = { mode = mode, ownDungeon = int(f[2]), level = int(f[3], 0, 9999), timer = int(f[4]), affixes = {},
        champsNeeded = int(f[6], 0, 99), hasForces = f[7] == "1", name = name, bosses = {}, at = GetTime() }
    if mode == L.MODE.MYTHIC0 or mode == L.MODE.KEY then
        run.dungeon = L.KeyDungeonId(name)
    end
    for a in (f[5] or ""):gmatch("%d+") do
        if #run.affixes < 8 then
            run.affixes[#run.affixes + 1] = tonumber(a)
        end
    end
    L.mplus.run = run
    if mode == L.MODE.RIFT and run.level > 0 then
        L.rift.inFloor = run.level
    end
end

-- B: one boss of the run (index from 1, in the dungeon's kill order).
function H.B(f)
    local run, i = L.mplus.run, int(f[1], 0, 64)
    if not run or i == 0 then
        return
    end
    run.bosses[i] = { role = int(f[2], 0, 3), done = f[3] == "1", name = text(f[4]) }
end

-- D: that boss died.
function H.D(f)
    local run, i = L.mplus.run, int(f[1], 0, 64)
    if not run or i == 0 then
        return
    end
    local b = run.bosses[i]
    if b then
        b.done = true
    else
        run.bosses[i] = { role = 0, done = true, name = "" }
    end
end

-- The mode of a partial run (T alone), from our protocol: MPS's key (a level) or Mythic 0 (no level and untimed, as the
-- key tracker tells them apart), else a Rift floor while RIFT runs; 0 while unknown (MP before its MPS, nothing yet).
local function partialMode()
    local st = ns.S
    local m = st and st.mplus
    if m and not m.result and m.state ~= 4 then
        if (m.level or 0) > 0 then
            return L.MODE.KEY
        end
        return (m.timeLimitSec or 0) == 0 and L.MODE.MYTHIC0 or 0
    end
    local rf = st and st.rift
    if rf and rf.state == 1 then
        return L.MODE.RIFT
    end
    return 0
end

-- How many Mythic Champions a key with champions must see fall, from the server's DEF A text of the affix
-- (bh_ui_bridge_map.cpp Affixes: "From +14: 2 Mythic Champions (4x health) guard the dungeon; 1 must fall to finish
-- the key.", Champions.Count and Champions.Required): Required, at most Count (Start needs min(Required, the
-- champions it placed): fewer only in a dungeon short of trash to make champions of). nil without that text (the
-- built-in DEF A has no id 13, so only the server's counts, and only under its own name).
L.CHAMPIONS = 13
L.CHAMPIONS_NAME = "Mythic Champions"
function L.ChampionsRequired()
    local d = ns.Def("A", L.CHAMPIONS)
    if type(d) ~= "table" or d.name ~= L.CHAMPIONS_NAME or type(d.text) ~= "string" then
        return nil
    end
    local need = tonumber(d.text:match("(%d+) must fall"))
    if not need or need <= 0 then
        return nil
    end
    local count = tonumber(d.text:match("(%d+) Mythic Champions"))
    if count and count > 0 and count < need then
        need = count
    end
    return math.min(need, 99)
end

-- The champions a partial key run needs (no S since a /reload): the bridge's MPS lists the Mythic Champions affix
-- exactly when the key has them (bh_ui_bridge.cpp ViewOf: run->champions, from Champions.MinLevel), so a key whose
-- MPS has it needs L.ChampionsRequired(), one without it none (0); nil for any other mode or while unknown.
local function partialChampions(mode)
    local m = ns.S and ns.S.mplus
    if mode ~= L.MODE.KEY or not m or type(m.affixes) ~= "table" then
        return nil
    end
    for _, id in ipairs(m.affixes) do
        if id == L.CHAMPIONS then
            return L.ChampionsRequired()
        end
    end
    return 0
end

-- A partial run's mode and champions needed, as our protocol has them now.
function L.FillPartial(run)
    run.mode = partialMode()
    run.champsNeeded = partialChampions(run.mode)
end

-- T: the run's counters (SyncLine; RiftSync on a Rift floor). With no S (a /reload in the middle of a run: the
-- server sends S on entering and at the start only) a T of a run counting down or running starts a partial run =
-- { partial = true, mode and champsNeeded (partialMode, partialChampions: again on every L.Run()), bosses = {},
-- affixes = {}, name = "" } with T's counters: the battle res charges and the champions slain come back, the
-- champions needed come from our protocol (L.ChampionsRequired), while the boss roles, the level and the dungeon stay
-- unknown (nil) until an S replaces it.
function H.T(f)
    local run = L.mplus.run
    local state = int(f[8], 0, 3)
    if not run then
        if state ~= L.STATE.COUNTDOWN and state ~= L.STATE.RUNNING then
            return
        end
        run = { partial = true, bosses = {}, affixes = {}, name = "" }
        L.mplus.run = run
    end
    run.elapsed, run.deaths, run.penalty = int(f[1]), int(f[2], 0, 9999), int(f[3])
    run.forcesDone, run.forcesNeeded = int(f[4]), int(f[5])
    run.bres, run.champsKilled, run.state = int(f[6], 0, 99), int(f[7], 0, 99), state
    run.at = GetTime()
    if run.partial then
        L.FillPartial(run)
    end
end

-- E: the run is over (Complete): the tracker has MPE for the result.
function H.E()
    L.mplus.run = nil
end

-- Y: an affix's stacks on this player; 0 takes it away. Necrotic is sent at 1, 4, 7, ... 43 stacks only
-- (scripts:541), so it may be up to 2 behind, and its cap (45) never comes: L.STACKS[8] says so at 43.
function H.Y(f)
    local id = int(f[1], 0, 99)
    if L.STACKS[id] then
        local n = int(f[2], 0, 255)
        L.mplus.affix.stacks[id] = n > 0 and n or nil
    end
end

-- V: the group's Mythical Boon for that many seconds; V;0;0 when it fades (or the run ends).
function H.V(f)
    local a, boon, sec = L.mplus.affix, int(f[1], 0, 3), int(f[2], 0, 3600)
    if boon == 0 or sec == 0 then
        a.boon, a.boonUntil = 0, 0
    else
        a.boon, a.boonUntil = boon, GetTime() + sec
    end
end

-- Q: the ground quakes under this player in that many ms (Quaking).
function H.Q(f)
    L.mplus.affix.quakeAt = GetTime() + int(f[1], 0, 60000) / 1000
end

-- Tags read only in part: the message is ours when this says so. An S comes for a Mythic run (2 Mythic 0, 3 keystone)
-- or a Rift floor (4), never for a Heroic (1); a T always has its 8 fields.
L.ACCEPT = {
    S = function(f)
        return f[1] == "2" or f[1] == "3" or f[1] == "4"
    end,
    T = function(f)
        return #f >= 8
    end,
}

-- The run's tags: LEGACY_RUN instead of LEGACY, so the pages do not redraw on every T; X and a Rift floor's S
-- (the Rift page shows the floor now) fire both.
L.RUN_TAGS = { S = true, B = true, D = true, T = true, E = true, Y = true, V = true, Q = true, X = true }
local function pagesToo(tag, f)
    return tag == "X" or (tag == "S" and f[1] == "4")
end

-- One BHMP message (without the prefix). Answers the tag when it was one of ours.
function L.Receive(msg)
    if type(msg) ~= "string" or msg == "" or #msg > 1024 then
        return nil
    end
    local tag, fields = L.Split(msg)
    local h = H[tag]
    if not h or (L.ACCEPT[tag] and not L.ACCEPT[tag](fields)) then
        return nil
    end
    L.seen = true
    h(fields)
    local run = L.RUN_TAGS[tag]
    if not run or pagesToo(tag, fields) then
        ns.Fire("LEGACY", tag)
    end
    if run then
        ns.Fire("LEGACY_RUN", tag)
    end
    return tag
end

local function fromSelf(channel, sender)
    if channel ~= "WHISPER" or type(sender) ~= "string" then
        return false
    end
    return (sender:match("^([^%-]+)") or sender) == ns.PlayerName()
end

-- Only the server's own whisper to this character counts: another player cannot open windows or offer a mount.
ns.RegisterEvent("CHAT_MSG_ADDON", function(event, prefix, msg, channel, sender)
    if prefix ~= L.PREFIX or Comm.demo or not fromSelf(channel, sender) then
        return
    end
    L.Receive(msg)
end)

------------------------------------------------------------------------------------------------------
-- What the pages read
------------------------------------------------------------------------------------------------------
-- The dungeon difficulty, 1 Normal, 2 Heroic, 3 Mythic. Z says Mythic or not (it is never 2), so Heroic comes from our
-- own KEY (its mode 0..2) when the server sent one, else from the client's dungeon difficulty (Heroic is the game's
-- own 5-player Heroic: .mplus difficulty heroic sets it).
function L.Difficulty()
    local key = ns.S and ns.S.key
    if key and key.mode then
        return key.mode + 1
    end
    if L.mplus.z == 3 then
        return 3
    end
    local d = GetDungeonDifficulty and GetDungeonDifficulty()
    if d == 2 then
        return 2
    end
    return 1
end

-- "Normal", "Heroic" or "Mythic"; colored with the stock colours when color is set (old :348 and :429, without the
-- concatenation-before-or slip of :348).
function L.DifficultyName(n, color)
    n = n or L.Difficulty()
    local name = L.DIFFICULTIES[n] or L.DIFFICULTIES[1]
    if color and n ~= 1 then
        return "|cff" .. L.DIFFICULTY_COLORS[n] .. name .. "|r"
    end
    return name
end

-- The season's Mythic+ dungeons in the server's order: the L list ({ id, timer, best, name }), else (no BHMP yet) the
-- DEF D dungeons with a time limit (the key dungeons, bh_ui_bridge_map.cpp), best unknown (0).
function L.SeasonDungeons()
    if #L.mplus.list > 0 then
        return L.mplus.list
    end
    local out = {}
    for _, id in ipairs(ns.DefIds("D")) do
        local d = ns.Def("D", id)
        if d and (d.timeLimitSec or 0) > 0 and #out < 64 then
            out[#out + 1] = { id = id, timer = d.timeLimitSec, best = 0, name = d.name or ns.DungeonName(id) }
        end
    end
    return out
end

-- Whether the keystone has opened the start here (O), so the server takes Start keystone: TakePendingSocket wants
-- the same instance within 300 s. Gone on X (out of the dungeon), on a loading screen, once the countdown starts
-- (MPS) and after L.SOCKET_SECONDS.
L.SOCKET_SECONDS = 300
function L.SocketArmed()
    local s = L.mplus.socket
    if not s then
        return false
    end
    if GetTime() - s.at > L.SOCKET_SECONDS then
        L.mplus.socket = nil
        return false
    end
    return true
end

ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    L.mplus.socket = nil
    L.mplus.group = nil
end)
ns.On("MPLUS_START", function()
    L.mplus.socket = nil
end)

-- A loading screen ends the run's state (the server's X may be lost with a logout). On PLAYER_LEAVING_WORLD, not on
-- PLAYER_ENTERING_WORLD: the new instance's S, B and T come once the client has answered the new world
-- (OnPlayerEnterAll, SendFullState), which can be before the loading screen is gone.
ns.RegisterEvent("PLAYER_LEAVING_WORLD", function()
    if clearRun() then
        ns.Fire("LEGACY_RUN", "PLAYER_LEAVING_WORLD")
    end
end)

-- The run the player is in (L.mplus.run, from S; a partial one from T alone, its mode and champions needed as our
-- protocol has them now: L.FillPartial), or nil.
function L.Run()
    local run = L.mplus.run
    if run and run.partial then
        L.FillPartial(run)
    end
    return run
end

-- Mythic Champions still to slay before the key can end (CheckComplete waits for them after the last boss), then
-- the slain and the needed; nil when the run needs none (a key below Champions.MinLevel, Mythic 0, a Rift floor) or
-- it is unknown (a partial run without the server's DEF A of the affix).
function L.ChampionsLeft()
    local run = L.Run()
    if not run or (run.champsNeeded or 0) <= 0 then
        return nil
    end
    local killed = run.champsKilled or 0
    return math.max(0, run.champsNeeded - killed), killed, run.champsNeeded
end

-- Battle resurrection charges left in a Mythic run (Mythic 0 or a key, counting down or running: bh_mplus_bres), once
-- its first T came; nil otherwise (a Rift floor has none).
function L.BattleRes()
    local run = L.Run()
    if not run or (run.mode ~= L.MODE.MYTHIC0 and run.mode ~= L.MODE.KEY) or not run.bres
        or (run.state ~= L.STATE.COUNTDOWN and run.state ~= L.STATE.RUNNING) then
        return nil
    end
    return run.bres
end

-- Boss i's role (L.ROLE: 1 shown, 2 extra, 3 final; 0 unknown), or nil without that boss.
function L.BossRole(i)
    local run = L.Run()
    local b = run and run.bosses[i]
    return b and b.role or nil
end

-- Whether boss i does not block the end (CheckComplete): Mythic 0 ends with the final boss, so every other one is
-- optional; a key never waits for an extra boss. nil when unknown.
function L.BossOptional(i)
    local run = L.Run()
    local b = run and run.bosses[i]
    if not b or b.role == 0 then
        return nil
    end
    if run.mode == L.MODE.MYTHIC0 then
        return b.role ~= L.ROLE.FINAL
    end
    if run.mode == L.MODE.KEY then
        return b.role == L.ROLE.EXTRA
    end
    return false
end

-- The affixes stacked on the player now, in L.STACK_AFFIXES order: { id, stacks, name, effect } (the effect in the
-- server's numbers).
function L.AffixStacks()
    local out = {}
    for _, id in ipairs(L.STACK_AFFIXES) do
        local n = L.mplus.affix.stacks[id]
        if n and n > 0 then
            local a = L.STACKS[id]
            out[#out + 1] = { id = id, stacks = n, name = a.name, effect = a.effect(n) }
        end
    end
    return out
end

-- The group's Mythical Boon: { id, name, effect, left = seconds } while it lasts, else nil.
function L.Boon()
    local a = L.mplus.affix
    local b = L.BOONS[a.boon]
    if not b then
        return nil
    end
    local left = a.boonUntil - GetTime()
    if left <= 0 then
        a.boon, a.boonUntil = 0, 0
        return nil
    end
    return { id = a.boon, name = b.name, effect = b.effect, left = left }
end

-- Seconds until the quake the server announced (Q), or nil when none is coming.
function L.QuakeIn()
    local left = L.mplus.affix.quakeAt - GetTime()
    if left <= 0 then
        return nil
    end
    return left
end

-- Seconds until the Journey board changes, or nil when unknown.
function L.BoardChangesIn()
    local at = L.journey.rotAt
    if not at or at <= 0 then
        return nil
    end
    return math.max(0, floor(at - GetTime()))
end

------------------------------------------------------------------------------------------------------
-- The old commands
------------------------------------------------------------------------------------------------------
-- Commands go out only on a Bleakhold server (our handshake answered, or refused as too old - only Bleakhold says
-- that -, or a BHMP message came): anywhere else a '.' line would be said aloud. Never in demo mode.
function L.CanCommand()
    if Comm.demo then
        return false
    end
    return (Comm.ready or Comm.outdated or L.seen) and true or false
end

function L.Cmd(line)
    if not L.CanCommand() then
        return false
    end
    SendChatMessage(line, "SAY")
    return true
end

-- Ask for the board, the keystone, the season list, the Rift and the difficulty (the old window did on every open);
-- at most every L.REQUEST_EVERY seconds unless forced.
local lastRequest = -1e9
function L.Request(force)
    if not force and GetTime() - lastRequest < L.REQUEST_EVERY then
        return false
    end
    if not L.CanCommand() then
        return false
    end
    lastRequest = GetTime()
    L.Cmd(".act journey")
    L.Cmd(".act mplus")
    return true
end

-- A board offer: alone ("solo") or through the Journey's group queue ("queue").
function L.StartJourney(key, how)
    key = tonumber(key)
    if not key or key <= 0 then
        return false
    end
    return L.Cmd(".act start " .. floor(key) .. " " .. (how == "queue" and "queue" or "solo"))
end

function L.RiftEnter(floorNo)
    return L.Cmd(".rift enter " .. math.max(1, floor(tonumber(floorNo) or 1)))
end

-- A party member follows the rift the party leader opened (RiftEnter's follow path, which takes no floor); with
-- nothing to follow the server answers "Only your party leader can open the rift."
function L.RiftFollow()
    return L.Cmd(".rift enter")
end

-- Out of the rift; the server answers with X only, so U is asked again once the player is out (L.LEAVE_REFRESH s).
L.LEAVE_REFRESH = 2
function L.RiftLeave()
    if not L.Cmd(".rift leave") then
        return false
    end
    ns.After(L.LEAVE_REFRESH, function()
        L.Request(true)
    end)
    return true
end

-- The dungeon difficulty for the group (1 Normal, 2 Heroic, 3 Mythic; the party leader, outside dungeons): our KMODE
-- (0..2) while the protocol is up, which the server confirms with a new KEY (its mode), else the old command.
local DIFF_WORDS = { [1] = "normal", [2] = "heroic", [3] = "mythic" }
function L.SetDifficulty(n)
    local w = DIFF_WORDS[n]
    if not w then
        return false
    end
    if Comm.ready then
        Comm.Send("KMODE", n - 1)
        return true
    end
    return L.Cmd(".mplus difficulty " .. w)
end

function L.LeaveDungeon()
    return L.Cmd(".mplus leave")
end

------------------------------------------------------------------------------------------------------
-- Popups (the stock dialog; the old addon's names, so a copy of it still installed shows one dialog, not two)
------------------------------------------------------------------------------------------------------
L.RIDE_TEXT = "You can ride now!\n\nApprentice Riding (60%% speed) and your first mount for %s?"
-- Where Leave dungeon takes the player, as the server's LeaveDungeon does it (bh_leave.cpp): an Eclipse Rift floor
-- leaves the rift (RiftLeave, back to Dalaran); a Dungeon Journey run goes back to the Dungeon Board (or the spot) it
-- was started from; any other dungeon, outside its entrance. The client cannot tell a Journey run from a plain one.
L.LEAVE_TEXT = "Leave this dungeon?\nA Dungeon Journey run takes you back to where you started it; any other "
    .. "dungeon, outside its entrance."
L.LEAVE_RIFT_TEXT = "Leave the Eclipse Rift and return to Dalaran?"
function L.LeaveText()
    local rift = ns.Rift
    if rift and rift.RunFloor and rift.RunFloor() then
        return L.LEAVE_RIFT_TEXT
    end
    return L.LEAVE_TEXT
end

function L.InstallDialogs()
    StaticPopupDialogs.BLEAKHOLD_RIDE = {
        text = L.RIDE_TEXT, button1 = "Buy", button2 = "Later", timeout = 0, whileDead = 1, hideOnEscape = 1,
        preferredIndex = 3,
        OnAccept = function()
            L.Cmd(".ride")
        end,
    }
    StaticPopupDialogs.BLEAKHOLD_LEAVE_DUNGEON = {
        text = "%s", button1 = "Yes", button2 = "No", timeout = 0, whileDead = 1, hideOnEscape = 1,
        preferredIndex = 3,
        OnAccept = function()
            L.LeaveDungeon()
        end,
        -- the Leave dungeon button closes Activities before asking; No (or Escape) brings it back on its page
        OnCancel = function()
            local A = ns.Activities
            if A and A.OpenPage then
                A.OpenPage(A.current or "group")
            end
        end,
    }
end
L.InstallDialogs()

function L.Money(copper)
    if GetCoinTextureString then
        local s = GetCoinTextureString(copper)
        if type(s) == "string" and s ~= "" then
            return s
        end
    end
    return floor(copper / 10000) .. " gold"
end

-- The old BleakholdActivities, still loaded ("Not now" in OldAddons.lua), reads RIDE as well and plays the same sound
-- (old :505-508): the sound once, from it then. StaticPopup_Show reuses the shown dialog, so it shows once either way.
function L.ShowRide(price)
    local oldPlays = IsAddOnLoaded and IsAddOnLoaded("BleakholdActivities")
    if PlaySoundFile and not oldPlays then
        PlaySoundFile("Sound\\Spells\\ReputationLevelUp.wav")
    end
    return StaticPopup_Show("BLEAKHOLD_RIDE", L.Money(price or 0))
end

function L.ConfirmLeave()
    return StaticPopup_Show("BLEAKHOLD_LEAVE_DUNGEON", L.LeaveText())
end

------------------------------------------------------------------------------------------------------
-- Demo mode (/bh demo): a board, a keystone, the season list and the Rift, through the same parser
------------------------------------------------------------------------------------------------------
L.DEMO = {
    "H;5400;0;0;0;1",
    "J;1001;36;0;0;1;15;0;82;845;3;120;The Deadmines;",
    "J;1002;33;1;2;1;18;0;0;0;0;160;Shadowfang Keep;Bolstering",
    "J;1003;189;2;5;2;30;0;64;1310;1;240;Scarlet Monastery;Bolstering, Sanguine",
    "J;1004;209;0;0;3;42;1;0;0;0;300;Zul'Farrak;",
    "J;1005;230;3;8;3;50;3;0;0;0;380;Blackrock Depths;Raging",
    "J;1006;329;1;0;3;56;2;0;0;0;420;Stratholme;",
    "J;1007;575;2;1;5;78;1;0;0;0;600;Utgarde Pinnacle;Fortified",
    "J;1008;602;3;3;5;77;1;0;0;0;640;Halls of Lightning;Fortified, Bolstering",
    "K;602;8;1800;Halls of Lightning",
    "W;12;1,3,10,8;10;8;5",
    "L;189;1800;9;Scarlet Monastery: Armory",
    "L;190;1800;0;Scarlet Monastery: Cathedral",
    "L;329;1800;7;Stratholme: Main Gate",
    "L;330;1800;0;Stratholme: Service Entrance",
    "L;289;1800;12;Scholomance",
    "L;230;1800;4;Blackrock Depths: Upper City",
    "L;229;1800;0;Lower Blackrock Spire",
    "L;429;1800;0;Dire Maul: West",
    "L;209;1800;6;Zul'Farrak",
    "L;555;1800;0;Shadow Labyrinth",
    "L;575;1800;8;Utgarde Pinnacle",
    "L;602;1800;11;Halls of Lightning",
    "U;24;18;12;9;20;80;1;0;50",
    "Z;3",
}

function L.DemoFeed()
    for _, msg in ipairs(L.DEMO) do
        L.Receive(msg)
    end
    L.demoFed = true
end

-- /bh demo resets the state and says hello: the sample board comes with it; leaving demo mode forgets it.
local resetState = ns.ResetState
ns.ResetState = function(...)
    resetState(...)
    reset()
end

-- The handshake is up (once a login or /reload): in a dungeon with no run from S (a /reload is no map entry, so the
-- server sent none), ask for the state again. .act mplus brings the week (W), the season list, the keystone, U (the
-- Rift floor now) and Z back; it does not bring the run's S, B and T until bleakserv's HandleMplus sends SendFullState
-- too (bh_activities.cpp:137: not yet). Meanwhile the run's T keeps a partial run (H.T) with the champions needed
-- from MPS and DEF A, and the boss roles unknown. Unforced: Activities' own HELLO request a moment before counts.
ns.On("HELLO", function()
    if Comm.demo then
        if not L.demoFed then
            L.DemoFeed()
        end
        return
    end
    local inside, kind = IsInInstance()
    local run = L.mplus.run
    if inside and kind == "party" and not (run and not run.partial) then
        L.Request()
    end
end)
