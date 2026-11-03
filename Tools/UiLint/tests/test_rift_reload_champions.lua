-- A /reload in the middle of a +14 / +15 key (Legacy.lua): the server sends the run's S (with the Mythic Champions
-- needed) and its B (the boss roles) on entering the instance and at the start only (bh_mplus.cpp SendFullState), and
-- today's bleakserv does not answer the handshake's .act mplus with them either (bh_activities.cpp HandleMplus: W, L,
-- K, U and Z). So after a /reload only T comes (SyncLine, every 5 s), and Legacy keeps a partial run from it. The
-- champions needed then come from our protocol: the bridge's MPS lists the Mythic Champions affix (13) exactly when
-- the key has them (bh_ui_bridge.cpp ViewOf: run->champions), and the server's DEF A text of it says how many must
-- fall (bh_ui_bridge_map.cpp Affixes: Champions.Count, Champions.Required). The key tracker's champion line comes back
-- with it, so a key with every boss and the forces done never looks finished while it waits for a champion.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function bhmp(M, msg)
    M.FireEvent("CHAT_MSG_ADDON", "BHMP", msg, "WHISPER", M.playerName)
end

local CHAMP_TEXT = "From +14: 2 Mythic Champions (4x health) guard the dungeon; 1 must fall to finish the key."

-- the handshake's answers after a /reload in a +15 Halls of Lightning: DEF A, MPS with the bridge's affixes (the
-- week's four, then 13 and 14), MP with every boss down and the forces full
local function reloadInKey(M, level, affixes, defText, defName)
    M.inInstance, M.instanceType = true, "party"
    FX.connect(M, H)
    if defText then
        H.send(M, "DEF", { { "A", 1 }, { 13, defName or "Mythic Champions", defText } })
    end
    H.send(M, "MPS", { { 7001, 602, level, affixes, 7, 0, 1800 } })
    H.send(M, "MP", { { 7001, 1500000, 1800, 3, 15, 100, 100, 15, { 300, 600, 900, 1200 }, { 1260, 1440 }, 1 } })
end

test("reload champions: a partial +15 run needs the champions DEF A names, and the tracker shows them", function(M, ns)
    local L, T = ns.Legacy, ns.KeyTracker
    reloadInKey(M, 15, { 1, 3, 10, 8, 13, 14 }, CHAMP_TEXT)
    H.eq(L.Run(), nil, "no run before the first T")
    bhmp(M, "T;1500000;3;15;100;100;2;0;2")
    local run = L.Run()
    H.eq(run.partial, true, "no S since the /reload")
    H.eq(run.mode, L.MODE.KEY)
    H.eq(run.champsNeeded, 1, "Champions.Required from the server's DEF A text")
    local left, killed, needed = L.ChampionsLeft()
    H.eq(left, 1, "every boss and the forces done, and still a champion to slay")
    H.eq(killed, 0); H.eq(needed, 1)
    H.ok(T.LegacyRun(ns.S.mplus, T.MODE_KEY) == run, "the tracker takes the partial run")
    local t = M.env.BleakholdKeyTracker
    H.ok(t.champs:IsVisible(), "the champion line is back after the /reload")
    H.eq(t.champs.name:GetText(), "Mythic Champions 0/1")
    -- the champion falls (T's champions slain)
    bhmp(M, "T;1505000;3;15;100;100;2;1;2")
    H.eq(L.ChampionsLeft(), 0)
    H.eq(t.champs.name:GetText(), "Mythic Champions 1/1")
    H.eq(t.champs.state:GetText(), "done")
    -- the run's S (the next entry) replaces the partial run with the server's own count
    bhmp(M, "S;3;4;15;1800;1,3,10,8,13,14;1;1;Halls of Lightning")
    H.eq(L.Run().partial, nil)
    H.eq(L.Run().champsNeeded, 1)
end)

test("reload champions: Champions.Required above Champions.Count asks for the champions there are", function(M, ns)
    local L = ns.Legacy
    reloadInKey(M, 14, { 1, 3, 10, 8, 13, 14 },
        "From +14: 2 Mythic Champions (4x health) guard the dungeon; 3 must fall to finish the key.")
    bhmp(M, "T;1500000;3;15;100;100;2;0;2")
    H.eq(L.Run().champsNeeded, 2, "Start needs min(Required, the champions it placed)")
    H.eq(L.ChampionsRequired(), 2)
end)

test("reload champions: a key without the affix needs none; unknown without the server's DEF A", function(M, ns)
    local L = ns.Legacy
    -- a +10: MPS has no Mythic Champions, so none are needed (0), and no line shows
    reloadInKey(M, 10, { 1, 3, 10, 8 }, CHAMP_TEXT)
    bhmp(M, "T;1500000;3;15;100;100;2;0;2")
    H.eq(L.Run().champsNeeded, 0)
    H.eq(L.ChampionsLeft(), nil)
    H.ok(not M.env.BleakholdKeyTracker.champs:IsVisible())
    -- a +15 before the server's DEF A came (the built-in table has no id 13): unknown, never a made-up count
    bhmp(M, "X")
    ns.db.defs = {}
    H.eq(ns.Def("A", 13), nil)
    H.send(M, "MPS", { { 7002, 602, 15, { 1, 3, 10, 8, 13, 14 }, 7, 0, 1800 } })
    bhmp(M, "T;60000;0;0;10;100;1;0;2")
    H.eq(L.Run().partial, true)
    H.eq(L.Run().champsNeeded, nil)
    H.eq(L.ChampionsLeft(), nil)
    -- a DEF A 13 under another name is not the champions' text
    H.send(M, "DEF", { { "A", 2 }, { 13, "Something Else", "3 must fall" } })
    H.eq(L.ChampionsRequired(), nil)
    H.eq(L.Run().champsNeeded, nil)
    -- the server's own: known from the next look on
    H.send(M, "DEF", { { "A", 3 }, { 13, "Mythic Champions", CHAMP_TEXT } })
    H.eq(L.Run().champsNeeded, 1)
end)

test("reload champions: a Mythic 0 or a Rift floor after a /reload needs no champions", function(M, ns)
    local L = ns.Legacy
    M.inInstance, M.instanceType = true, "party"
    FX.connect(M, H)
    H.send(M, "DEF", { { "A", 1 }, { 13, "Mythic Champions", CHAMP_TEXT } })
    H.send(M, "MPS", { { 7003, 574, 0, {}, 7, 0, 0 } })
    bhmp(M, "T;60000;0;0;0;0;1;0;2")
    H.eq(L.Run().mode, L.MODE.MYTHIC0)
    H.eq(L.Run().champsNeeded, nil)
    H.eq(L.ChampionsLeft(), nil)
    bhmp(M, "X")
    ns.S.mplus = nil
    H.send(M, "RIFT", { { 8001, 1, 7, 3, "Echo of Nefarian", 120000, 18, "", 42, 3, 3 } })
    bhmp(M, "T;30000;1;0;0;0;0;0;2")
    H.eq(L.Run().mode, L.MODE.RIFT)
    H.eq(L.Run().champsNeeded, nil)
end)

local function said(M, msg)
    local n = 0
    for _, s in ipairs(M.said) do
        if s.chatType == "SAY" and s.msg == msg then
            n = n + 1
        end
    end
    return n
end

test("reload champions: the handshake still asks again (the week and keystone; the run's S once the server sends it)",
    function(M, ns)
    local L = ns.Legacy
    reloadInKey(M, 15, { 1, 3, 10, 8, 13, 14 }, CHAMP_TEXT)
    H.eq(said(M, ".act mplus"), 1, "W, L, K, U and Z come back today")
    -- what today's server sends for it: no S, so the partial run stays, its champions from MPS and DEF A
    for _, msg in ipairs({ "W;12;1,3,10,8;14;8;5", "K;602;15;1800;Halls of Lightning", "U;24;18;12;9;20;80;1;0;50",
        "Z;3", "T;1505000;3;15;100;100;2;0;2" }) do
        bhmp(M, msg)
    end
    H.eq(L.Run().partial, true)
    H.eq(L.ChampionsLeft(), 1)
    H.eq(L.BossRole(1), nil, "the boss roles come with B only")
end)
