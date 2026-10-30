-- The server's legacy Activities messages (Legacy.lua): the BHMP addon messages the old BleakholdActivities window
-- read, which every player still gets (mod-bleakhold BHMP::Mgr::SendAddon: a whisper to oneself in LANG_ADDON, prefix
-- "BHMP", ';' between the fields), and the old chat commands. Each message below is built the way its server sender
-- builds it (bh_activities.cpp SendJourney, bh_mplus.cpp SendKey / SendWeek / SendDungeonList / SendDifficulty,
-- bh_rift.cpp SendRiftInfo, bh_leveling.cpp's RIDE and A) and read field by field as the old handlers did
-- (old BleakholdActivities.lua :474-511).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function bhmp(M, msg, sender, channel)
    M.FireEvent("CHAT_MSG_ADDON", "BHMP", msg, channel or "WHISPER", sender or M.playerName)
end

local function saidSay(M)
    local out = {}
    for _, s in ipairs(M.said) do
        if s.chatType == "SAY" then out[#out + 1] = s.msg end
    end
    return out
end

test("legacy H and J: the Journey board, its rotation clock and every offer field", function(M, ns)
    local L = ns.Legacy
    H.ok(not L.journey.known, "nothing before the first H")
    -- SendJourney: H;<seconds to rotation>;<queued key>;<players queued>;<first run done>;1
    bhmp(M, "H;3600;1002;3;1;1")
    local j = L.journey
    H.ok(j.known and j.on, "the board is on")
    H.eq(j.queuedKey, 1002)
    H.eq(j.queuedPlayers, 3)
    H.eq(j.firstDone, true)
    H.eq(L.BoardChangesIn(), 3600, "the rotation clock")
    M.Advance(60)
    H.eq(L.BoardChangesIn(), 3540, "counts down with the game clock")
    -- J;key;dungeon;tier;mods;chapter;minLevel;status;best;time;runs;reward;name;modNames
    bhmp(M, "J;1003;189;2;5;2;30;0;64;1310;4;240;Scarlet Monastery;Bolstering, Sanguine")
    bhmp(M, "J;1004;209;0;0;3;42;1;0;0;0;300;Zul'Farrak;")
    H.eq(#j.offers, 2)
    local o = j.offers[1]
    H.eq(o.key, 1003); H.eq(o.dungeon, 189); H.eq(o.tier, 2); H.eq(o.mods, 5); H.eq(o.chapter, 2)
    H.eq(o.minLevel, 30); H.eq(o.status, 0); H.eq(o.best, 64); H.eq(o.time, 1310); H.eq(o.runs, 4)
    H.eq(o.reward, 240); H.eq(o.name, "Scarlet Monastery"); H.eq(o.modNames, "Bolstering, Sanguine")
    H.eq(j.byKey[1004].status, 1, "locked: level")
    H.eq(j.byKey[1004].modNames, "", "no modifiers")
    H.eq(L.TIERS[o.tier].name, "Elite")
    -- the same offer again changes it in place; a new H starts a new board
    bhmp(M, "J;1003;189;2;5;2;30;0;71;1200;5;240;Scarlet Monastery;Bolstering, Sanguine")
    H.eq(#j.offers, 2)
    H.eq(j.byKey[1003].best, 71)
    bhmp(M, "H;0;0;0;0;0")
    H.eq(#j.offers, 0, "the board is cleared")
    H.ok(not j.on, "the Journey is closed (the server's disabled board)")
    H.eq(L.BoardChangesIn(), nil, "no clock")
end)

test("legacy K, W, L, Z: the keystone, the week's affixes, the season list and the difficulty", function(M, ns)
    local L = ns.Legacy
    local m = L.mplus
    -- SendKey: K;<dungeon id>;<level>;<timer s>;<name>, or K;0
    bhmp(M, "K;575;7;1800;Utgarde Pinnacle")
    H.ok(m.keyKnown)
    H.eq(m.key.id, 575); H.eq(m.key.level, 7); H.eq(m.key.timer, 1800); H.eq(m.key.name, "Utgarde Pinnacle")
    bhmp(M, "K;0")
    H.eq(m.key, nil, "no keystone")
    -- SendWeek: W;<week>;a1,a2,a3,a4;<champions from>;<hp % per level>;<damage % per level>
    bhmp(M, "W;12;1,3,10,8;10;8;5")
    H.eq(m.week.index, 12)
    H.eq(table.concat(m.week.affixes, ","), "1,3,10,8")
    H.eq(m.week.champMinLevel, 10); H.eq(m.week.hpPerLevel, 8); H.eq(m.week.dmgPerLevel, 5)
    -- SendDungeonList: L;<id>;<timer>;<best level>;<name>, one per season dungeon, again on every .act mplus
    bhmp(M, "L;289;1800;12;Scholomance")
    bhmp(M, "L;229;1500;0;Lower Blackrock Spire")
    H.eq(#m.list, 2)
    H.eq(m.list[1].id, 289); H.eq(m.list[1].timer, 1800); H.eq(m.list[1].best, 12); H.eq(m.list[1].name, "Scholomance")
    bhmp(M, "L;289;1800;13;Scholomance")
    H.eq(#m.list, 2, "the same dungeon is updated, not added")
    H.eq(m.byId[289].best, 13)
    H.eq(ns.Legacy.SeasonDungeons(), m.list, "the pages read the season list")
    -- SendDifficulty: Z;3 when the leader chose Mythic, else Z;0 (never 1 or 2)
    bhmp(M, "Z;3")
    H.eq(m.z, 3)
    H.eq(L.Difficulty(), 3)
    H.eq(L.DifficultyName(), "Mythic")
    bhmp(M, "Z;0")
    H.eq(L.Difficulty(), 1, "Z;0 is Normal")
    -- the old :348 raised on M.diff 0 (concatenation binds before 'or'): every value names a difficulty
    for _, n in ipairs({ 0, 1, 2, 3, 4 }) do
        H.ok(type(L.DifficultyName(n)) == "string", "a name for " .. n)
    end
    H.eq(L.DifficultyName(2, true), "|cff40C0FFHeroic|r", "the old page's Heroic blue")
end)

test("legacy: Heroic shows although Z is only ever 0 or 3 (KEY.mode from our protocol, else the client's)",
    function(M, ns)
    local L = ns.Legacy
    FX.connect(M, H)
    bhmp(M, "Z;0")
    H.eq(L.Difficulty(), 1)
    M.env.GetDungeonDifficulty = function() return 2 end
    H.eq(L.Difficulty(), 2, "the client's 5-player Heroic")
    -- KEY field 5 is the mode: 0 normal, 1 heroic, 2 mythic
    H.send(M, "KEY", { { 1, 602, 8, { 1, 3, 4 }, 1, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    M.env.GetDungeonDifficulty = function() return 1 end
    bhmp(M, "Z;0")
    H.eq(L.Difficulty(), 2, "KEY says Heroic")
    H.eq(L.DifficultyName(), "Heroic")
    H.send(M, "KEY", { { 1, 602, 8, { 1, 3, 4 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    H.eq(L.Difficulty(), 3, "KEY says Mythic")
end)

test("legacy U: the Eclipse Rift's bests by group size, checkpoint, level, state and floors", function(M, ns)
    local L = ns.Legacy
    -- SendRiftInfo: U;solo;duo;trio;group;checkpoint;minLevel;on;floor now;floor count
    bhmp(M, "U;24;18;12;9;20;80;1;0;50")
    local r = L.rift
    H.ok(r.known)
    H.eq(table.concat(r.best, ","), "24,18,12,9")
    H.eq(r.checkpoint, 20); H.eq(r.minLevel, 80); H.eq(r.on, true); H.eq(r.inFloor, 0); H.eq(r.floors, 50)
    bhmp(M, "U;24;18;12;9;20;80;0;7;50")
    H.eq(r.on, false, "closed")
    H.eq(r.inFloor, 7, "in a run, on floor 7")
end)

test("legacy RIDE: the riding offer as the stock dialog; Buy says .ride", function(M, ns)
    FX.connect(M, H)
    M.env.GetCoinTextureString = function(c) return math.floor(c / 10000) .. "g" end
    bhmp(M, "RIDE;350000")
    local p = M.popups[#M.popups]
    H.ok(p and p.which == "BLEAKHOLD_RIDE", "the dialog shows")
    H.contains(p.text, "You can ride now!")
    H.contains(p.text, "(60% speed)")
    H.contains(p.text, "35g")
    H.eq(M.env.StaticPopupDialogs.BLEAKHOLD_RIDE.button1, "Buy")
    local before = #saidSay(M)
    M.StaticPopupClick("BLEAKHOLD_RIDE", 1)
    local said = saidSay(M)
    H.eq(#said, before + 1, table.concat(said, "|"))
    H.eq(said[#said], ".ride")
    -- "Later" says nothing
    bhmp(M, "RIDE;350000")
    M.StaticPopupClick("BLEAKHOLD_RIDE", 2)
    H.eq(#saidSay(M), before + 1)
end)

local RIDE_SOUND = "Sound\\Spells\\ReputationLevelUp.wav"
local function soundsOf(M, path)
    local n = 0
    for _, f in ipairs(M.soundFiles) do
        if f == path then n = n + 1 end
    end
    return n
end

test("legacy RIDE: the level-up sound once, also while the old addon (which plays it too) is still loaded",
    function(M, ns)
    FX.connect(M, H)
    bhmp(M, "RIDE;350000")
    H.eq(soundsOf(M, RIDE_SOUND), 1, "ours")
    -- 'Not now' on the old addons' question: its unnamed frame still reads RIDE and plays the sound (old :505-508)
    M.addons.BleakholdActivities = true
    bhmp(M, "RIDE;350000")
    H.eq(soundsOf(M, RIDE_SOUND), 1, "the old addon's alone, not twice on top of each other")
    H.ok(M.popups[#M.popups].which == "BLEAKHOLD_RIDE", "the dialog all the same")
end)

test("legacy O and X: the keystone's start, the end of a run (no new U comes then)", function(M, ns)
    FX.connect(M, H)
    local L = ns.Legacy
    bhmp(M, "U;24;18;12;9;20;80;1;7;50")
    H.eq(L.rift.inFloor, 7)
    bhmp(M, "O;602;8;1800;10;8;8;1,3,4;Halls of Lightning")
    H.ok(L.SocketArmed(), "the keystone opened the start")
    H.eq(L.mplus.socket.dungeon, 602)
    H.eq(L.mplus.socket.name, "Halls of Lightning")
    bhmp(M, "X")
    H.eq(L.rift.inFloor, 0, "out of the floor")
    H.ok(not L.SocketArmed(), "out of the keystone's dungeon")
    H.eq(L.Receive("X;junk;more"), "X", "extra fields on a tag that has none")
    -- a loading screen ends the start too (a new instance)
    bhmp(M, "O;602;8;1800;10;8;8;1,3,4;Halls of Lightning")
    M.FireEvent("PLAYER_ENTERING_WORLD")
    H.ok(not L.SocketArmed())
    -- leaving the rift asks for U again once the player is out
    local n = #saidSay(M)
    L.RiftLeave()
    H.eq(saidSay(M)[n + 1], ".rift leave")
    M.Advance(L.LEAVE_REFRESH + 0.1)
    H.eq(saidSay(M)[n + 3], ".act mplus", "U asked again: " .. table.concat(saidSay(M), "|", n + 1))
    -- a party member follows the party's rift (no floor: the follow path)
    L.RiftFollow()
    local said = saidSay(M)
    H.eq(said[#said], ".rift enter")
end)

test("legacy A: A;journey opens Activities on the Dungeon Journey; a page that does not exist opens nothing",
    function(M, ns)
    bhmp(M, "A;nonsense")
    H.ok(not M.env.BleakholdActivitiesFrame:IsShown(), "nothing for an unknown page")
    bhmp(M, "A;journey")
    H.ok(M.env.BleakholdActivitiesFrame:IsShown(), "opens")
    H.eq(ns.Activities.current, "dungeons", "on the Dungeon Journey (the old page name)")
    M.env.BleakholdActivitiesFrame:Hide()
    bhmp(M, "A;mplus")
    H.eq(ns.Activities.current, "keys")
end)

test("legacy: only the server's whisper to this character counts", function(M, ns)
    local L = ns.Legacy
    bhmp(M, "A;journey", "Mallory")
    bhmp(M, "RIDE;10000", "Mallory")
    bhmp(M, "K;575;7;1800;Utgarde Pinnacle", M.playerName, "PARTY")
    M.FireEvent("CHAT_MSG_ADDON", "BHMPX", "K;575;7;1800;Utgarde Pinnacle", "WHISPER", M.playerName)
    H.ok(not M.env.BleakholdActivitiesFrame:IsShown(), "another player cannot open windows")
    H.eq(#M.popups, 0, "or offer a mount")
    H.ok(not L.mplus.keyKnown, "a party message or another prefix is not the server's")
    H.ok(not L.seen)
    -- tags of the keystone HUD and the rest are our protocol's (bridge): left alone
    H.eq(L.Receive("S;1;2;3"), nil)
    H.eq(L.Receive("T;1;2;3"), nil)
    H.eq(L.Receive(""), nil)
    H.eq(L.Receive(string.rep("x", 2000)), nil, "too long")
end)

test("legacy: fields are checked (numbers clamped, names cleaned, extra ';' kept in the last field)", function(M, ns)
    local L = ns.Legacy
    bhmp(M, "H;-5;abc;999;7;1")
    H.eq(L.journey.rotAt, 0, "a negative rotation is no clock")
    H.eq(L.journey.queuedKey, 0)
    H.eq(L.journey.queuedPlayers, 99)
    bhmp(M, "J;1;2;9;0;1;400;8;250;1;1;1;Bad|Name\1;a;b;c")
    local o = L.journey.offers[1]
    H.eq(o.tier, 3, "tier clamped to Nightmare")
    H.eq(o.minLevel, 255); H.eq(o.status, 3); H.eq(o.best, 100)
    H.ok(not o.name:find("\1", 1, true), "no control bytes")
    H.eq(o.modNames, "a;b;c", "the free text keeps its ';'")
    bhmp(M, "J;0;2;0;0;1;1;0;0;0;0;0;No key;")
    H.eq(#L.journey.offers, 1, "an offer without a key is dropped")
    bhmp(M, "W;1;1,2,3,4,5,6;10;8;5")
    H.eq(#L.mplus.week.affixes, 4, "four affixes at most")
    bhmp(M, "K;575")
    H.eq(L.mplus.key.level, 0, "missing fields read as 0")
    H.eq(L.mplus.key.name, "")
end)

test("legacy commands: only on a Bleakhold server, never in demo mode, the board asked at most every 5 s",
    function(M, ns)
    local L = ns.Legacy
    -- not connected: a '.' line would be said aloud on any other server
    H.eq(L.Request(true), false)
    H.eq(L.StartJourney(1003, "queue"), false)
    H.eq(#saidSay(M), 0)
    FX.connect(M, H)
    H.eq(L.Request(), true)
    local said = saidSay(M)
    H.eq(said[1], ".act journey")
    H.eq(said[2], ".act mplus")
    H.eq(L.Request(), false, "again at once: throttled")
    M.Advance(L.REQUEST_EVERY + 0.1)
    H.eq(L.Request(), true)
    -- the old window's actions, word for word
    L.StartJourney(1003, "queue")
    L.StartJourney(1004, "solo")
    L.RiftEnter(21)
    L.RiftLeave()
    L.LeaveDungeon()
    said = saidSay(M)
    H.eq(table.concat(said, "|", #said - 4), ".act start 1003 queue|.act start 1004 solo|.rift enter 21|.rift leave|.mplus leave")
    H.eq(L.StartJourney(0, "solo"), false, "no key, nothing said")
    -- the difficulty goes through our KMODE while the protocol is up (the server confirms it with KEY)
    L.SetDifficulty(2)
    H.eq(H.lastIntent(M, "KMODE").payload, "1")
    -- demo mode: nothing reaches the server
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    local n = #saidSay(M)
    H.eq(L.Request(true), false)
    L.StartJourney(1003, "solo")
    H.eq(#saidSay(M), n)
end)

test("legacy: without our protocol the old commands do it (a BHMP message proves a Bleakhold server)", function(M, ns)
    local L = ns.Legacy
    bhmp(M, "Z;0")
    H.ok(L.seen and L.CanCommand())
    L.SetDifficulty(3)
    local said = saidSay(M)
    H.eq(said[#said], ".mplus difficulty mythic")
    L.SetDifficulty(2)
    H.eq(saidSay(M)[#saidSay(M)], ".mplus difficulty heroic")
    H.eq(L.SetDifficulty(7), false)
end)

test("legacy: an outdated client still uses the old commands (the OUTDATED answer proves a Bleakhold server)",
    function(M, ns)
    local L = ns.Legacy
    FX.connect(M, H, { [2] = ns.PROTO + 1 })
    H.ok(ns.Comm.outdated and not ns.Comm.ready, "the handshake says the client is too old")
    H.ok(L.CanCommand(), "the old commands are allowed")
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local said = saidSay(M)
    H.eq(said[1], ".act journey", table.concat(said, "|"))
    H.eq(said[2], ".act mplus")
    H.eq(ns.Dungeons.WaitText(), "Loading the board...")
end)

test("legacy: OUTDATED while the window is open asks for the old pages' data", function(M, ns)
    ns.UI.Open("keys")
    M.Advance(0.3)
    H.eq(#saidSay(M), 0, "nothing said before the server answers")
    FX.connect(M, H, { [2] = ns.PROTO + 1 })
    local said = saidSay(M)
    H.eq(said[1], ".act journey", table.concat(said, "|"))
end)

test("legacy demo: /bh demo fills the board, the keystone, the season list and the Rift", function(M, ns)
    local L = ns.Legacy
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    H.ok(#L.journey.offers >= 6, "a board")
    H.ok(L.mplus.key and L.mplus.key.level > 0, "a keystone")
    H.ok(#L.mplus.list >= 12, "the season dungeons")
    H.ok(L.rift.known and L.rift.best[1] > 0, "the Rift")
    M.env.SlashCmdList.BLEAKHOLD("demo off")
    H.eq(#L.journey.offers, 0, "leaving demo mode forgets it")
end)

test("legacy: a burst of messages refreshes the open page once, after the burst", function(M, ns)
    FX.connect(M, H)
    ns.UI.Open("heroic")
    M.Advance(0.3)
    local P = ns.Heroic
    local n = 0
    local refresh = P.Refresh
    P.Refresh = function(self) n = n + 1; return refresh(self) end
    for i = 1, 12 do
        bhmp(M, "L;" .. (200 + i) .. ";1800;" .. i .. ";Dungeon " .. i)
    end
    H.eq(n, 0, "not once per message")
    M.Advance(0.3)
    H.eq(n, 1, "once after the burst")
    H.ok(P.tiles[12]:IsShown(), "and the page shows them")
end)
