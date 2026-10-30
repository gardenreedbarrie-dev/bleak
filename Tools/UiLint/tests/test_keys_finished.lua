-- Activities > Mythic+ Dungeons (Keys.lua): Start keystone in an instance whose run is over. The right-click and
-- StartRun refuse every start there until the dungeon is reset (bh_mplus_scripts.cpp KeyStartBlock / MythicRunText,
-- bh_mplus.cpp StartRun), so the hint says so in the server's words instead of pointing at the right-click.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local FINISHED_KEY = "Halls of Lightning +8 - finished. Reset the dungeon for another run."
local FINISHED_M0 = "Mythic 0: Halls of Lightning - finished. Reset the dungeon for another run."

local function open(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("keys")
    M.Advance(0.3)
    return ns.Keys
end

-- the leader of 5 inside Halls of Lightning
local function inside(M)
    M.inInstance, M.instanceType, M.zone = true, "party", "Halls of Lightning"
    M.SetGroup("PARTY", 5, true)
end

-- a loading screen: out of the instance (PLAYER_LEAVING_WORLD, then PLAYER_ENTERING_WORLD)
local function leave(M)
    M.FireEvent("PLAYER_LEAVING_WORLD")
    M.inInstance, M.instanceType, M.zone = false, "none", "The Storm Peaks"
    M.EnterWorld()
end

-- the owner's KEY: Halls of Lightning at `level`
local function key(M, rev, level)
    H.send(M, "KEY", { { rev, 602, level, { 1, 3, 4 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } })
end

test("keys finished: a key finished over time leaves no Start keystone in its instance, the server's text says why",
    function(M, ns)
    local P = open(M, ns)
    inside(M)
    key(M, 2, 8)
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    H.send(M, "MP", { { 7001, 60000, 1800, 0, 0, 10, 100, 0, "", "", 1 } })
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.StartBlock(), "A keystone run is under way.")
    -- over time: the final MP (state 3), the MPE, and Complete()'s new key, +7 in the same dungeon
    H.send(M, "MP", { { 7001, 1900000, 1800, 2, 10, 100, 100, 7, { 300, 900, 1500 }, "", 3 } })
    H.send(M, "MPE", { { 7001, 0, 1900000, -1, 602, 7, 0 } })
    key(M, 3, 7)
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.StartBlock(), FINISHED_KEY)
    H.ok(not P.start:IsEnabled())
    H.eq(P.startHint:GetText(), FINISHED_KEY, "never 'Right-click your keystone' here")
    -- out of the instance (it has to be left to be reset): the usual hint
    leave(M)
    P:Refresh()
    H.eq(P.startHint:GetText(), "Use your keystone inside Halls of Lightning.")
end)

test("keys finished: a Mythic 0 that dropped the first keystone blocks it until the dungeon is reset", function(M, ns)
    local P = open(M, ns)
    inside(M)
    H.send(M, "MPS", { { 7101, 602, 0, "", 7, 0, 0 } })
    H.send(M, "MP", { { 7101, 30000, 0, 0, 0, 0, 100, 0, "", "", 1 } })
    M.Advance(0.3)
    -- the final boss dies: Complete() drops the first keystone, Halls of Lightning +2
    H.send(M, "MP", { { 7101, 1200000, 0, 0, 0, 100, 100, 7, { 300, 900, 1200 }, "", 2 } })
    H.send(M, "MPE", { { 7101, 1, 1200000, 0, 602, 2, 0 } })
    key(M, 2, 2)
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.startHint:GetText(), FINISHED_M0)
    H.ok(not P.start:IsEnabled())
end)

test("keys finished: entering the finished instance again, the old S and T keep the block; a reset one lifts it",
    function(M, ns)
    local P = open(M, ns)
    key(M, 2, 7)
    -- back in the instance whose +8 is over: SendFullState sends S, the bosses and T with state 3 (ST_DONE)
    M.FireEvent("PLAYER_LEAVING_WORLD")
    inside(M)
    ns.Legacy.Receive("S;3;4;8;1800;1,3,4;0;1;Halls of Lightning")
    ns.Legacy.Receive("T;1900000;2;10;100;100;1;0;3")
    M.EnterWorld()
    P:Refresh()
    H.eq(P.startHint:GetText(), FINISHED_KEY)
    H.ok(not P.start:IsEnabled())
    -- a Mythic 0 finished there
    M.FireEvent("PLAYER_LEAVING_WORLD")
    ns.Legacy.Receive("S;2;4;0;0;;0;1;Halls of Lightning")
    ns.Legacy.Receive("T;1200000;0;0;100;100;1;0;3")
    M.EnterWorld()
    P:Refresh()
    H.eq(P.startHint:GetText(), FINISHED_M0)
    -- a reset instance: no Mythic run there (X), the right-click again
    M.FireEvent("PLAYER_LEAVING_WORLD")
    ns.Legacy.Receive("X")
    M.EnterWorld()
    P:Refresh()
    H.contains(P.startHint:GetText(), "Right-click your keystone")
end)

test("keys finished: a run still running here, or the ended run of another dungeon, is not called finished",
    function(M, ns)
    local P = open(M, ns)
    inside(M)
    key(M, 2, 8)
    -- the old T of a run still going on (state 2 RUNNING) is no finished run
    ns.Legacy.Receive("S;3;4;8;1800;1,3,4;0;1;Halls of Lightning")
    ns.Legacy.Receive("T;60000;0;0;10;100;1;0;2")
    P:Refresh()
    H.ok(P.StartBlock() ~= FINISHED_KEY)
    ns.Legacy.Receive("X")
    -- an ended MPE without its dungeon (no MPS seen, a /reload): nothing to tell the instance by
    H.send(M, "MPE", { { 7201, 1, 1453000, 1, 602, 9, 0 } })
    M.Advance(0.3)
    P:Refresh()
    H.contains(P.startHint:GetText(), "Right-click your keystone")
    -- a Deadmines key ended, the player now in Halls of Lightning: no block there
    H.send(M, "MPS", { { 7202, 36, 4, { 1 }, 7, 0, 1800 } })
    H.send(M, "MP", { { 7202, 1700000, 1800, 0, 0, 100, 100, 7, "", "", 2 } })
    H.send(M, "MPE", { { 7202, 1, 1700000, 1, 602, 8, 0 } })
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.FinishedBlock(), nil)
    H.contains(P.startHint:GetText(), "Right-click your keystone")
end)
