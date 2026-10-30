-- The Rift page's run lines (Rift.lua RefreshRun): the last run's summary from RIFTE and the run in progress from RIFT,
-- as the bridge sends them (bh_ui_bridge_map.cpp RiftEndOf: floorReached is the deepest floor stood on, unset when
-- the run ended before its first floor; the reward texts name the party size of a new best; SyncRift: deaths are the
-- whole run's, Run::riftRunDeaths, which RiftSetupFloor carries on from floor to floor, as the Rift tracker counts).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function openRift(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.Legacy.Receive("U;24;18;12;9;20;80;1;0;50")
    ns.UI.Open("rift")
    M.Advance(0.3)
    return ns.Rift
end

local function lines(P)
    local out = {}
    for i, l in ipairs(P.runLines) do
        out[i] = l:GetText() or ""
    end
    return out
end

test("rift summary: no floor stood on is 'Run over', never 'Reached floor 0'", function(M, ns)
    local P = openRift(M, ns)
    -- an older server sends the floors cleared, so 0 when the run ended before its first boss
    H.send(M, "RIFTE", { { 8001, 0, 41000, "", 0, "" } })
    M.Advance(0.3)
    H.eq(P.runTitle:GetText(), "Your Last Run")
    H.eq(P.runLines[1]:GetText(), "Run over", "floor 0")
    -- bleakserv's RiftEndOf leaves it unset
    H.send(M, "RIFTE", { { 8002, "", 52000, "", 0, "" } })
    M.Advance(0.3)
    H.eq(P.runLines[1]:GetText(), "Run over", "no floor")
    H.contains(P.runLines[2]:GetText(), "Time 00:52")
    for _, l in ipairs(lines(P)) do
        H.ok(not l:find("floor 0", 1, true), "never floor 0: " .. l)
    end
end)

test("rift summary: the deepest floor stood on, as the chat's 'fell on floor 8'", function(M, ns)
    local P = openRift(M, ns)
    H.send(M, "RIFTE", { { 8001, 8, 912000, 1840, 0, 42 }, { "C", 72 } })
    M.Advance(0.3)
    H.eq(P.runLines[1]:GetText(), "Reached floor 8")
    H.eq(P.runLines[2]:GetText(), "Time 15:12  -  Score 1,840  -  Rank 42")
    H.eq(P.runLines[3]:GetText(), "|cffffd100+|r 72 Mythic Coins")
end)

test("rift summary: 'new best!' only when no reward line already names the best", function(M, ns)
    local P = openRift(M, ns)
    -- an older server: the flag alone
    H.send(M, "RIFTE", { { 8001, 8, 912000, "", 1, "" }, { "C", 72 } })
    M.Advance(0.3)
    H.eq(P.runLines[1]:GetText(), "Reached floor 8  -  new best!")
    -- bleakserv: "New best for a duo run" among the rewards says it (and for which size): not twice
    H.send(M, "RIFTE", { { 8002, 8, 912000, "", 1, "" }, { "C", 72 },
        { "T", 0, "", "1 Rift Cache (gear in your bags)" }, { "T", 0, "", "New best for a duo run" } })
    M.Advance(0.3)
    H.eq(P.runLines[1]:GetText(), "Reached floor 8")
    local all = table.concat(lines(P), "\n")
    H.contains(all, "|cffffd100+|r New best for a duo run", "the server's line names the size")
    local _, n = all:lower():gsub("new best", "")
    H.eq(n, 1, "the new best is said once: " .. all)
    -- no new best: no suffix, whatever the floor
    H.send(M, "RIFTE", { { 8003, 3, 100000, "", 0, "" } })
    M.Advance(0.3)
    H.eq(P.runLines[1]:GetText(), "Reached floor 3")
    -- a new best with no floor (cannot happen, but never "floor 0  -  new best!")
    H.eq(P.SummaryTitle({ floor = 0, newBest = true, rewards = {} }), "Run over  -  new best!")
end)

test("rift run: the deaths are the whole run's, carried on from floor to floor (as the tracker's)", function(M, ns)
    local P = openRift(M, ns)
    M.inInstance, M.instanceType = true, "party"
    H.send(M, "RIFT", { { 8001, 1, 7, 3, "Echo of Nefarian", 120000, 18, "", 42, 3, 3 } })
    M.Advance(0.3)
    H.eq(P.runTitle:GetText(), "Your Run")
    H.contains(P.runLines[2]:GetText(), "3 deaths")
    H.contains(P.runLines[2]:GetText(), "group of 3")
    -- floor 8: one more death, so 4 for the run (Run::riftRunDeaths never starts again on a floor)
    H.send(M, "RIFT", { { 8001, 1, 8, 4, "Ingvar the Plunderer", 180000, 18, "", 42, 4, 3 } })
    M.Advance(0.3)
    H.eq(P.runLines[1]:GetText(), "Floor 8  -  Ingvar the Plunderer")
    H.eq(P.runLines[2]:GetText(), "Time 03:00  -  4 deaths  -  group of 3")
    -- a run with one death in all
    H.send(M, "RIFT", { { 8002, 1, 2, 4, "Ingvar the Plunderer", 30000, 18, "", 42, 1, 1 } })
    M.Advance(0.3)
    H.contains(P.runLines[2]:GetText(), "1 death  -  solo")
    H.ok(not P.runLines[2]:GetText():find("1 deaths", 1, true), "one death")
    for _, l in ipairs(lines(P)) do
        H.ok(not l:find("on this floor", 1, true), "never the floor's: " .. l)
    end
end)
