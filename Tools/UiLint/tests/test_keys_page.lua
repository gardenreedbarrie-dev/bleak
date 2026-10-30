-- Activities > Mythic+ Dungeons (Keys.lua) against the server's rules (mod-bleakhold bh_mplus.cpp, bh_ui_bridge.cpp):
-- the keystone during a key run (the owner's own run, a party member in someone else's), Start keystone in a fresh
-- Mythic 0 and on a Heroic instance, the members StartRun names, and the Mythical Caches as an allowance.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

-- bh_mplus.cpp OpenSocket: the keystone opened the start of a +8 Halls of Lightning, the group seen inside (G)
local SOCKET = "O;602;8;1800;10;8;8;1,3,4;Halls of Lightning"
local ALL_INSIDE = "G;Me:1:1:1:1|Ann:2:1:0:1|Bo:5:1:0:1|Cy:8:1:0:1|Di:4:1:0:1"

local function tipText(lines)
    local out = {}
    for _, l in ipairs(lines) do
        out[#out + 1] = type(l) == "table" and l[1] or l
    end
    return table.concat(out, "\n")
end

local function open(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("keys")
    M.Advance(0.3)
    return ns.Keys
end

-- the instance's difficulty (GetInstanceInfo's third value; a 5-player dungeon: 1 Normal, 2 Heroic)
local function instanceDifficulty(M, d)
    M.env.GetInstanceInfo = function()
        return M.zone, M.instanceType, d, d == 2 and "Heroic" or "Normal", 5, 0, nil
    end
end

-- the leader of 5 inside Halls of Lightning
local function inside(M)
    M.inInstance, M.instanceType, M.zone = true, "party", "Halls of Lightning"
    M.SetGroup("PARTY", 5, true)
end

------------------------------------------------------------------------------------------------------
-- The keystone during a key run
------------------------------------------------------------------------------------------------------
test("keys page: the owner's run shows its key and what the run makes of it", function(M, ns)
    local P = open(M, ns)
    -- KEY 602/8 and MPS 602/8: the bridge sends the run's own key while the owner's run is active (BuildKey)
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.keyText:GetText(), "|cffa335ee+8|r  Halls of Lightning", "no 'run under way' squeezed into the title")
    H.eq(P.keySub:GetText(), "Run under way: in time +9 to +11 in a new dungeon, over time +7 here.")
    -- Complete(): at most KEY maxLevel in time, never under +1 over time
    H.send(M, "KEY", { { 2, 602, 14, { 1, 3, 4 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    H.send(M, "MPS", { { 7002, 602, 14, { 1, 3, 4 }, 7, 10000, 1800 } })
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.keySub:GetText(), "Run under way: in time +15 in a new dungeon, over time +13 here.")
    H.send(M, "KEY", { { 3, 602, 13, { 1, 3, 4 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    H.send(M, "MPS", { { 7003, 602, 13, { 1, 3, 4 }, 7, 10000, 1800 } })
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.keySub:GetText(), "Run under way: in time +14 to +15 in a new dungeon, over time +12 here.")
    H.send(M, "KEY", { { 4, 602, 1, { 1 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    H.send(M, "MPS", { { 7004, 602, 1, { 1 }, 7, 10000, 1800 } })
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.keySub:GetText(), "Run under way: in time +2 to +4 in a new dungeon, over time +1 here.")
    -- the note fits the page: two lines of the sub text, not one cut line
    H.ok(P.keySub:GetHeight() >= 2 * 11, "two lines")
    -- the run ends (MPE): the key's own text again
    H.send(M, "MPE", { { 7004, 1, 1453000, 2, 599, 3, 1840 } })
    H.send(M, "KEY", { { 5, 599, 3, { 1 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    P:Refresh()
    H.contains(P.keySub:GetText(), "right-click the key inside the dungeon")
end)

test("keys page: a party member in the leader's run sees their own keystone, unchanged", function(M, ns)
    local P = open(M, ns)
    -- the member's own Deadmines +3; the leader's Halls of Lightning +8 under way
    H.send(M, "KEY", { { 2, 36, 3, { 1, 3 }, 0, 0, "", 40, 0, 900001, 15, 7, 0 } })
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    H.send(M, "MP", { { 7001, 60000, 1800, 0, 0, 10, 100, 0, "", "", 1 } })
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.keyText:GetText(), "|cffa335ee+3|r  The Deadmines", "their own key, not the run's")
    H.eq(P.keySub:GetText(), "In a keystone run that is not yours: your keystone does not change.")
    H.eq(ns.Keys.OwnRun(), nil)
    -- the leader's countdown is not "your keystone's"
    H.send(M, "MPS", { { 7002, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    M.Advance(0.3)
    H.eq(P.StartBlock(), "A keystone countdown is running.")
    -- the owner (KEY 602/8) in the same countdown
    H.send(M, "KEY", { { 3, 602, 8, { 1, 3, 4 }, 0, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    H.eq(P.StartBlock(), "Your keystone's countdown is running.")
end)

-- the old K (Legacy.lua) of a Halls of Lightning key at `level`: SendKey's stored key (bh_mplus.cpp)
local function oldK(ns, level)
    ns.Legacy.Receive("K;4;" .. level .. ";1800;Halls of Lightning")
end

test("keys page: whose run it is comes from the keys the server sends, not from who leads", function(M, ns)
    local P = open(M, ns)
    -- the leader's Halls of Lightning +8 under way; this player a member, not the leader
    M.SetGroup("PARTY", 5, false)
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    H.send(M, "MP", { { 7001, 60000, 1800, 0, 0, 10, 100, 0, "", "", 1 } })
    -- KEY at the run's level: the bridge sends the run's own key to its owner only (BuildKey), so this is the owner,
    -- who does not lead now
    H.send(M, "KEY", { { 2, 602, 8, { 1, 3, 4 }, 2, 9, 599, 40, 0, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.RunOwnership(), "own")
    H.eq(ns.Keys.OwnRun(), ns.S.mplus, "the owner's run, whoever leads")
    H.eq(P.keySub:GetText(), "Run under way: in time +9 to +11 in a new dungeon, over time +7 here.")
    -- the owner's old K is a level lower (StartRun stored it so): the same
    oldK(ns, 7)
    P:Refresh()
    H.eq(P.RunOwnership(), "own", "K lowered by StartRun")
    -- a member whose own key is the same: their K is not lowered, so not the run
    oldK(ns, 8)
    P:Refresh()
    H.eq(P.RunOwnership(), "other")
    H.eq(ns.Keys.OwnRun(), nil)
    H.eq(P.keyText:GetText(), "|cffa335ee+8|r  Halls of Lightning", "their own key, unchanged")
    H.eq(P.keySub:GetText(), P.OTHER_RUN)
    -- at +1 StartRun leaves the stored key at +1 (max(1, level - 1)): K says nothing there
    H.send(M, "MPS", { { 7002, 602, 1, { 1 }, 7, 10000, 1800 } })
    H.send(M, "KEY", { { 3, 602, 1, { 1 }, 2, 9, 599, 40, 0, 900001, 15, 7, 0 } })
    oldK(ns, 1)
    M.Advance(0.3)
    H.eq(P.RunOwnership(), "own", "+1: the run's key")
    -- one level lower, not leading: a member's own key today, or an older server's owner who passed the lead
    H.send(M, "MPS", { { 7003, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    H.send(M, "KEY", { { 4, 602, 7, { 1, 3, 4 }, 2, 9, 599, 40, 0, 900001, 15, 7, 1 } })
    oldK(ns, 7)
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.RunOwnership(), "unsure")
    H.eq(ns.Keys.OwnRun(), nil)
    H.eq(P.keyText:GetText(), "|cffa335ee+7|r  Halls of Lightning  |cff808080(depleted)|r", "their own key as it is")
    H.eq(P.keySub:GetText(), "A keystone run is under way.", "nothing said about the key either way")
    H.ok(not P.keySub:GetText():find("does not change", 1, true))
    -- the leader with it: an older server's stored key, the owner's run at the run's level
    M.SetGroup("PARTY", 5, true)
    P:Refresh()
    H.eq(ns.Keys.OwnRun(), ns.S.mplus, "the leader's own run")
    H.eq(P.keyText:GetText(), "|cffa335ee+8|r  Halls of Lightning", "the run's level, no depleted mark")
    H.eq(P.keySub:GetText(), "Run under way: in time +9 to +11 in a new dungeon, over time +7 here.")
    M.SetGroup("RAID", 5, true)
    H.ok(ns.Keys.OwnRun() ~= nil, "raid leader")
    M.SetGroup("RAID", 5, false)
    H.eq(ns.Keys.OwnRun(), nil, "raid member")
    M.SetGroup(nil)
    H.ok(ns.Keys.OwnRun() ~= nil, "solo")
    -- a level the owner's key never has (neither the run's nor one lower): surely not the run
    M.SetGroup("PARTY", 5, false)
    H.send(M, "KEY", { { 5, 602, 5, { 1, 3, 4 }, 2, 9, 599, 40, 0, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.RunOwnership(), "other")
    H.eq(P.keySub:GetText(), P.OTHER_RUN)
end)

test("keys page: the owner who passes the lead in the middle of the run keeps it; the new leader does not get it",
    function(M, ns)
    local P = open(M, ns)
    inside(M)
    -- Ann leads and starts her Halls of Lightning +8: the run's own key (BuildKey), her K lowered by StartRun
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    H.send(M, "MP", { { 7001, 60000, 1800, 0, 0, 10, 100, 0, "", "", 1 } })
    oldK(ns, 7)
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.keySub:GetText(), "Run under way: in time +9 to +11 in a new dungeon, over time +7 here.")
    -- she passes the lead to the tank (or goes offline and AzerothCore hands it on): still her run
    M.SetGroup("PARTY", 5, false)
    P:Refresh()
    H.eq(ns.Keys.OwnRun(), ns.S.mplus)
    H.eq(P.keyText:GetText(), "|cffa335ee+8|r  Halls of Lightning")
    H.eq(P.keySub:GetText(), "Run under way: in time +9 to +11 in a new dungeon, over time +7 here.")
    H.ok(not P.keySub:GetText():find("not yours", 1, true), "never 'not yours' to the owner")
    -- the new leader holds Halls of Lightning +8 of their own (K not lowered): surely not their run
    M.SetGroup("PARTY", 5, true)
    H.send(M, "KEY", { { 3, 602, 8, { 1, 3, 4 }, 2, 9, 599, 40, 0, 900001, 15, 7, 0 } })
    oldK(ns, 8)
    M.Advance(0.3)
    P:Refresh()
    H.eq(ns.Keys.OwnRun(), nil)
    H.eq(P.keySub:GetText(), P.OTHER_RUN)
    H.eq(P.StartBlock(), "A keystone run is under way.")
end)

test("keys page: a new leader whose own key is one level under the run, held from before it started, is not told it is "
    .. "theirs", function(M, ns)
    local P = open(M, ns)
    inside(M)
    M.SetGroup("PARTY", 5, false)
    -- Bo's own Halls of Lightning +7, from long before Ann starts her +8
    H.send(M, "KEY", { { 2, 602, 7, { 1, 3, 4 }, 2, 9, 599, 40, 0, 900001, 15, 7, 0 } })
    M.Advance(60)
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    M.Advance(0.3)
    -- the lead goes to Bo in the middle of the run
    M.SetGroup("PARTY", 5, true)
    P:Refresh()
    H.eq(P.RunOwnership(), "other", "the KEY did not change when the run started: a member's own")
    H.eq(ns.Keys.OwnRun(), nil)
    H.eq(P.keyText:GetText(), "|cffa335ee+7|r  Halls of Lightning", "their own key, not the run's +8")
    H.eq(P.keySub:GetText(), P.OTHER_RUN)
    H.eq(P.RunBlock(), "A keystone countdown is running.", "not 'your keystone's'")
    -- a later MPS (entering again) does not undo it
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 0, 1800 } })
    M.Advance(0.3)
    H.eq(P.RunOwnership(), "other")
end)

test("keys page: an older server's owner, whose KEY falls a level as the run starts, keeps the run without the lead",
    function(M, ns)
    local P = open(M, ns)
    inside(M)
    M.Advance(60)
    -- before BuildKey sent the run's own key: StartRun stores the key one lower and the bridge sends it at once
    H.send(M, "KEY", { { 2, 602, 7, { 1, 3, 4 }, 2, 9, 599, 40, 0, 900001, 15, 7, 0 } })
    M.Advance(0.5)
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    M.Advance(0.3)
    M.SetGroup("PARTY", 5, false)
    P:Refresh()
    H.eq(P.RunOwnership(), "own", "fallen from +8 as the run started")
    H.eq(P.keyText:GetText(), "|cffa335ee+8|r  Halls of Lightning")
    H.eq(P.keySub:GetText(), "Run under way: in time +9 to +11 in a new dungeon, over time +7 here.")
    -- the KEY after the MPS works the same; a run whose start was not seen falls back on the lead
    H.send(M, "MPE", { { 7001, 0, 1900000, -1, 602, 7, 0 } })
    H.send(M, "KEY", { { 3, 602, 8, { 1, 3, 4 }, 2, 9, 599, 40, 0, 900001, 15, 7, 0 } })
    M.Advance(60)
    H.send(M, "MPS", { { 7002, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    M.Advance(1)
    H.send(M, "KEY", { { 4, 602, 7, { 1, 3, 4 }, 2, 9, 599, 40, 0, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    H.eq(P.RunOwnership(), "own", "the KEY fell just after the MPS")
    H.send(M, "MPS", { { 7003, 602, 8, { 1, 3, 4 }, 7, 0, 1800 } })
    M.Advance(0.3)
    H.eq(P.RunOwnership(), "unsure", "a run in progress whose start was not seen, without the lead")
    H.eq(P.keySub:GetText(), P.RUN_UNSURE)
    M.SetGroup("PARTY", 5, true)
    H.eq(P.RunOwnership(), "own", "with the lead: the run, as before")
end)

------------------------------------------------------------------------------------------------------
-- Start keystone: a fresh Mythic 0, Heroic, the members StartRun names
------------------------------------------------------------------------------------------------------
test("keys page: a Mythic 0 started on entry still takes the keystone until a boss dies", function(M, ns)
    local P = open(M, ns)
    inside(M)
    -- Mythic mode: StartAutoMythic starts the Mythic 0 on entry, no countdown (MPS level 0, MP state 1)
    H.send(M, "MPS", { { 7101, 602, 0, "", 7, 0, 1800 } })
    H.send(M, "MP", { { 7101, 30000, 1800, 0, 0, 0, 100, 0, "", "", 1 } })
    M.Advance(0.3)
    -- the keystone right-clicked inside, all 5 there: StartRun's fromMythic0
    ns.Legacy.Receive(ALL_INSIDE)
    ns.Legacy.Receive(SOCKET)
    P:Refresh()
    H.eq(P.StartBlock(), nil)
    H.ok(P.start:IsEnabled(), "Start keystone in a fresh Mythic 0")
    H.eq(P.startHint:GetText(), "")
    -- a boss is dead: the server's StartRun text
    H.send(M, "MP", { { 7101, 90000, 1800, 0, 0, 20, 100, 1, { 80 }, "", 1 } })
    M.Advance(0.3)
    P:Refresh()
    H.ok(not P.start:IsEnabled())
    H.eq(P.startHint:GetText(), "A boss is already dead in this Mythic 0. Reset the dungeon to insert a keystone.")
    -- a Mythic 0 counting down (started at the Font of Power): MythicRunText
    H.send(M, "MPS", { { 7102, 602, 0, "", 7, 10000, 1800 } })
    M.Advance(0.3)
    P:Refresh()
    H.ok(not P.start:IsEnabled())
    H.eq(P.startHint:GetText(), "Mythic 0: Halls of Lightning - in progress.")
end)

test("keys page: a Heroic instance refuses the keystone with the server's text", function(M, ns)
    local P = open(M, ns)
    inside(M)
    instanceDifficulty(M, 2)
    P:Refresh()
    H.ok(not P.start:IsEnabled())
    H.eq(P.startHint:GetText(), "Mythic 0 and keystones run on Normal difficulty. Set your dungeon difficulty to "
        .. "Normal, leave and enter again.")
    H.contains(tipText(P.start.tooltip()), "Normal or Mythic dungeon mode, not Heroic.")
    -- Normal again: the next step is the right-click
    instanceDifficulty(M, 1)
    P:Refresh()
    H.contains(P.startHint:GetText(), "Right-click your keystone")
    -- another dungeon on Heroic: where to use the key comes first
    instanceDifficulty(M, 2)
    M.zone = "The Deadmines"
    P:Refresh()
    H.eq(P.startHint:GetText(), "Use your keystone inside Halls of Lightning.")
end)

test("keys page: Heroic set outside the dungeon: Start keystone says to set Normal or Mythic before entering",
    function(M, ns)
    local P = open(M, ns)
    M.SetGroup("PARTY", 5, true)
    -- KEY mode 1: the group's dungeon difficulty is Heroic (bh_ui_bridge_map.cpp KeyMode); the leader is outside
    H.send(M, "KEY", { { 2, 602, 8, { 1, 3, 4 }, 1, 9, 599, 40, 0, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    P:Refresh()
    H.ok(not P.start:IsEnabled())
    H.eq(P.startHint:GetText(), "Set the dungeon difficulty to Normal or Mythic before you enter Halls of Lightning: "
        .. "keystones do not run on Heroic.")
    H.eq(P.diff:GetText(), "Dungeon difficulty: " .. ns.Legacy.DifficultyName(2, true))
    -- Normal or Mythic: where to use the key
    for _, mode in ipairs({ 0, 2 }) do
        H.send(M, "KEY", { { 3 + mode, 602, 8, { 1, 3, 4 }, mode, 9, 599, 40, 0, 900001, 15, 7, 0 } })
        M.Advance(0.3)
        P:Refresh()
        H.eq(P.startHint:GetText(), "Use your keystone inside Halls of Lightning.", "mode " .. mode)
    end
    -- a member cannot start the key at all (nor change the difficulty): that comes first
    H.send(M, "KEY", { { 9, 602, 8, { 1, 3, 4 }, 1, 9, 599, 40, 0, 900001, 15, 7, 0 } })
    M.SetGroup("PARTY", 5, false)
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.startHint:GetText(), "Only the group leader can start the keystone.")
end)

test("keys page: only the leader of a party or a raid sets the difficulty", function(M, ns)
    local P = open(M, ns)
    for _, g in ipairs({ { "PARTY", true, nil }, { "RAID", true, nil }, { nil, false, nil },
        { "PARTY", false, "Only the group leader can change the dungeon difficulty." },
        { "RAID", false, "Only the group leader can change the dungeon difficulty." } }) do
        M.SetGroup(g[1], 5, g[2])
        H.eq(P.DifficultyBlock(), g[3], tostring(g[1]) .. " " .. tostring(g[2]))
    end
end)

test("keys page: StartRun's members below the level or in combat, of those inside", function(M, ns)
    local P = open(M, ns)
    inside(M)
    local names = { party1 = "Ann", party2 = "Bo", party3 = "Cy", party4 = "Di" }
    local levels, combat = {}, {}
    M.env.UnitName = function(unit)
        if unit == "player" then return M.playerName end
        return names[unit]
    end
    M.env.UnitLevel = function(unit)
        if unit == "player" then return M.playerLevel end
        return levels[unit] or 80
    end
    M.env.UnitAffectingCombat = function(unit) return combat[unit] and 1 or nil end
    -- Cy is outside: OpenSocket's G says so
    ns.Legacy.Receive("G;Me:1:1:1:1|Ann:2:1:0:1|Bo:5:1:0:1|Cy:8:0:0:1|Di:4:1:0:1")
    ns.Legacy.Receive(SOCKET)
    levels.party1 = 70
    P:Refresh()
    H.eq(P.startHint:GetText(), "Ann is below level 80.")
    levels.party1 = nil
    combat.party2 = true
    P:Refresh()
    H.eq(P.startHint:GetText(), "Bo is in combat.")
    combat.party2, combat.party3 = nil, true
    P:Refresh()
    H.eq(P.startHint:GetText(), "", "Cy was not inside at the right-click: not Cy's combat, and no count (StartRun's)")
    H.ok(P.start:IsEnabled())
    combat.player = true
    P:Refresh()
    H.eq(P.startHint:GetText(), M.playerName .. " is in combat.", "the leader too")
end)

------------------------------------------------------------------------------------------------------
-- The Mythical Caches: an allowance the runs spend
------------------------------------------------------------------------------------------------------
test("keys page: the caches stat explains the allowance on hover", function(M, ns)
    local P = open(M, ns)
    -- KEY: 42 left, 2 carried over (banked = bank - weeklyCap: 40 a week)
    H.send(M, "KEY", { { 2, 602, 8, { 1, 3, 4 }, 2, 9, 599, 42, 2, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    H.eq(P.caches:GetText(), "42 left, 2 carried over")
    H.ok(P.cachesTip:IsShown())
    M.Hover(P.cachesTip)
    local t = table.concat(M.env.GameTooltip.__lines, "\n")
    H.contains(t, "Mythical Caches")
    H.contains(t, "Cache rewards you have left. Each finished key uses 1 to 3 (by the time left; 1 over time or in a "
        .. "Mythic 0) and every 5th Eclipse Rift floor uses 1; the gear goes straight into your bags.")
    H.contains(t, "40 more every week; unused ones carry over.")
    H.contains(t, "2 of them carried over from earlier weeks.")
    H.ok(not t:find("None left", 1, true))
    M.Hover(P.cachesTip, false)
    -- nothing carried over: the weekly amount is not known
    H.send(M, "KEY", { { 3, 602, 8, { 1, 3, 4 }, 2, 9, 599, 40, 0, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    t = tipText(P.CachesTooltip())
    H.contains(t, "More come every week; unused ones carry over.")
    H.ok(not t:find("carried over from", 1, true))
    -- none left
    H.send(M, "KEY", { { 4, 602, 8, { 1, 3, 4 }, 2, 9, 599, 0, 0, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    H.eq(P.caches:GetText(), "0 left")
    local lines = P.CachesTooltip()
    H.eq(lines[#lines][1], "None left: runs give no cache gear until more come at the weekly reset.")
    H.eq(lines[#lines][2], ns.UI.C.orange)
end)

test("keys page: the caches tooltip never claims a weekly amount of 0 or less", function(M, ns)
    local P = open(M, ns)
    -- all of them carried over (a realm with WeeklyCacheCap 0: M::Caches gives banked == ready)
    H.send(M, "KEY", { { 2, 602, 8, { 1, 3, 4 }, 2, 9, 599, 5, 5, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    H.eq(P.caches:GetText(), "5 left, 5 carried over")
    local t = tipText(P.CachesTooltip())
    H.contains(t, "More come every week; unused ones carry over.")
    H.ok(not t:find("0 more every week", 1, true), "no weekly amount of 0")
    H.contains(t, "All of them carried over from earlier weeks.")
    -- more carried over than left (the demo's KEY: 1 and 2): no negative weekly amount, no count over what is left
    H.send(M, "KEY", { { 3, 602, 8, { 1, 3, 4 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    t = tipText(P.CachesTooltip())
    H.ok(not t:find("-1 more", 1, true), "no negative weekly amount")
    H.ok(not t:find("2 of them", 1, true), "not more carried over than left")
    H.contains(t, "More come every week; unused ones carry over.")
    H.contains(t, "All of them carried over from earlier weeks.")
    -- none left: nothing to have carried over
    H.send(M, "KEY", { { 4, 602, 8, { 1, 3, 4 }, 2, 9, 599, 0, 3, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    t = tipText(P.CachesTooltip())
    H.ok(not t:find("carried over from", 1, true))
    H.contains(t, "None left")
end)

test("keys page: the demo's own sample run is the player's (its fixed sample K is not the server's)", function(M, ns)
    M.playerLevel = 80
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1.5)
    ns.UI.Open("keys")
    M.Advance(0.3)
    local P = ns.Keys
    H.eq(ns.Legacy.mplus.key.level, 8, "the demo's K: the key at +8, never lowered")
    P.start:Click()
    M.Advance(0.3)
    H.ok(ns.S.mplus and ns.S.mplus.level == 8, "the sample run")
    H.eq(P.RunOwnership(), "own")
    H.eq(P.keySub:GetText(), "Run under way: in time +9 to +11 in a new dungeon, over time +7 here.")
end)
