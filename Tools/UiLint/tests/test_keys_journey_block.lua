-- Start keystone inside a Dungeon Journey run in the key's own dungeon (Keys.lua P.StartBlock): the bridge sends
-- QUEUE state 3 kind D there (bh_ui_bridge.cpp BuildOwnQueue), and the keystone's right-click, the Font of Power and
-- StartRun all refuse it (bh_mplus_scripts.cpp KeyStartBlock, bh_mplus.cpp StartRun: "A Dungeon Journey run is active
-- in this instance."), so the hint says that rather than to right-click the keystone.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function open(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("keys")
    M.Advance(0.3)
    return ns.Keys
end

test("keys page: a Dungeon Journey run in the key's dungeon refuses Start keystone with the server's text",
    function(M, ns)
    local P = open(M, ns)
    -- the leader of 5 in Halls of Lightning, the +8 Halls of Lightning key in the bag (FX.all's KEY)
    M.inInstance, M.instanceType, M.zone = true, "party", "Halls of Lightning"
    M.SetGroup("PARTY", 5, true)
    P:Refresh()
    H.contains(P.startHint:GetText(), "Right-click your keystone", "no Journey run: the right-click is next")
    -- queued from Today's Board into the same map: BuildOwnQueue's QueueInRun (Dungeon, tier 1, 5 players)
    H.send(M, "QUEUE", { { 9, 3, "D", 602, 1, 5, 0 } })
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.StartBlock(), "A Dungeon Journey run is active in this instance.")
    H.ok(not P.start:IsEnabled())
    H.eq(P.startHint:GetText(), "A Dungeon Journey run is active in this instance.")
    -- a Heroic instance: the server checks the difficulty first, and so does the page
    M.env.GetInstanceInfo = function()
        return M.zone, M.instanceType, 2, "Heroic", 5, 0, nil
    end
    P:Refresh()
    H.eq(P.StartBlock(), P.NORMAL_ONLY)
    M.env.GetInstanceInfo = function()
        return M.zone, M.instanceType, 1, "Normal", 5, 0, nil
    end
    -- an Eclipse Rift run (kind R) is not a Journey run: the keystone's own rules
    H.send(M, "QUEUE", { { 10, 3, "R", 0, 0, 5, 0 } })
    M.Advance(0.3)
    P:Refresh()
    H.contains(P.startHint:GetText(), "Right-click your keystone")
    -- the Journey run in another dungeon: where to use the key comes first, as the server says it
    H.send(M, "QUEUE", { { 11, 3, "D", 36, 1, 5, 0 } })
    M.zone = "The Deadmines"
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.startHint:GetText(), "Use your keystone inside Halls of Lightning.")
    -- out of the Journey instance: QUEUE state 0, the keystone's own rules again
    M.zone = "Halls of Lightning"
    H.send(M, "QUEUE", { { 12, 0 } })
    M.Advance(0.3)
    P:Refresh()
    H.contains(P.startHint:GetText(), "Right-click your keystone")
end)
