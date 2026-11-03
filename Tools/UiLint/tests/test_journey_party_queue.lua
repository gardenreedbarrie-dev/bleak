-- The Dungeon Journey's custom run and queue panel (Dungeons.lua) against the bridge (mod-bleakhold bh_ui_bridge.cpp
-- OnQueueJoin): Enter Dungeon's size is the party the bridge counts (PartyOf: online and in the world), so the run
-- starts (StartNow) instead of queueing; Find Group keeps the whole party (JoinLobby's seats count offline members).
-- The old H's queued count is a snapshot from the last .act journey (no H when others join or the player leaves):
-- never shown beside QUEUE, and dropped once QUEUE says the queue is over.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function feed(ns, list)
    for _, msg in ipairs(list) do
        ns.Legacy.Receive(msg)
    end
end

local BOARD = {
    "H;3600;0;0;0;1",
    "J;1001;36;0;0;1;15;0;82;845;3;120;The Deadmines;",
    "J;1002;33;1;2;1;18;0;0;0;0;160;Shadowfang Keep;Bolstering",
}

-- BOARD: one dungeon open at Normal and Veteran (Shadowfang Keep, 18-25)
local CUSTOM_BOARD = {
    { 1, 1260, 0, 0, 0, "", 1 },
    { 33, 1, 18, 25, 3, 64, 1, 88, "Dalia", 0 },
}

-- party members `offline` (a set of unit ids) are offline; the rest online
local function offline(M, set)
    M.env.UnitIsConnected = function(unit)
        if set[unit] then
            return nil
        end
        local n = tonumber(tostring(unit):match("^party(%d)$") or "")
        if unit == "player" or (n and n <= M.party) then
            return 1
        end
    end
end

local function openCustom(M, ns)
    FX.connect(M, H)
    M.playerLevel = 23
    feed(ns, BOARD)
    H.send(M, "BOARD", CUSTOM_BOARD)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    return ns.Dungeons, ns.Dungeons.customBox
end

test("journey: Enter Dungeon with an offline member sends the online party, so the run starts; Find Group the whole",
    function(M, ns)
    local P, cr = openCustom(M, ns)
    -- a party of 3, one offline: the bridge's partySize is 2, so size 2 is "complete as asked" (StartNow)
    M.SetGroup("PARTY", 3, true)
    offline(M, { party2 = true })
    P:Refresh()
    H.eq(P.PartySize(), 3, "the party")
    H.eq(P.OnlinePartySize(), 2, "the members the bridge counts")
    H.ok(cr.enter:IsEnabled())
    cr.enter:Click()
    H.eq(H.lastIntent(M, "QJOIN").payload, "D,33,0,4,2", "the online party: the run starts, no queue")
    H.ok(cr.find:IsEnabled(), "3 of 5 seats taken: a group to find")
    cr.find:Click()
    H.eq(H.lastIntent(M, "QJOIN").payload, "D,33,0,4,5", "find a group of five")
    -- 5 with one offline: JoinLobby's seats count all 5, so no one to find; Enter Dungeon takes the 4 online
    M.SetGroup("PARTY", 5, true)
    offline(M, { party4 = true })
    P:Refresh()
    H.ok(cr.enter:IsEnabled() and not cr.find:IsEnabled(), "a full party has no one to find")
    cr.enter:Click()
    H.eq(H.lastIntent(M, "QJOIN").payload, "D,33,0,4,4", "the 4 online")
    -- everyone online: the whole party
    offline(M, {})
    M.Advance(2)
    cr.enter:Click()
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "QJOIN").payload, "D,33,0,4,5")
end)

test("journey: H's queued count is not shown beside QUEUE; a finished QUEUE drops H's queued run", function(M, ns)
    M.playerLevel = 23
    feed(ns, BOARD)
    feed(ns, { "H;3600;1002;1;0;1" })
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local P = ns.Dungeons
    local q = P.queue
    -- the old H alone (a realm without our protocol): its count is all there is
    H.eq(P.queueStat:GetText(), "|cff1aff1aqueued|r (1)")
    H.eq(q.band:GetText(), "1 of 5 players")
    FX.connect(M, H)
    -- QUEUE: three more joined since (chat says 4/5), and no H came; H's 1 is not shown as the queue's count
    H.send(M, "QUEUE", { { 2, 1, "D", 33, 1, 5, 20, 100, "", "", 18, 25 } })
    M.Advance(0.3)
    H.eq(P.queueStat:GetText(), "|cff1aff1aqueued|r", "no count from H")
    H.eq(q.band:GetText(), "Levels 18-25", "the band alone")
    -- Leave queue: QUEUE state 0 ends H's queued run with it
    q.leave:Click()
    H.ok(H.lastIntent(M, "QLEAVE"))
    H.send(M, "QUEUE", { { 3, 0 } })
    M.Advance(0.3)
    H.ok(not q:IsShown())
    H.eq(ns.Legacy.journey.queuedKey, 0, "H's queued run is over")
    H.eq(ns.Legacy.journey.queuedPlayers, 0)
    -- a custom run of another dungeon (QJOIN D sends no H): nothing of the old queue under its name
    H.send(M, "QUEUE", { { 4, 1, "D", 36, 0, 5, 0, 300, "", "", 15, 21 } })
    M.Advance(0.3)
    H.eq(P.queueStat:GetText(), "|cff1aff1aqueued|r")
    H.eq(q.band:GetText(), "Levels 15-21")
    -- another kind's queue ends it too
    feed(ns, { "H;3600;1002;2;0;1" })
    H.send(M, "QUEUE", { { 5, 1, "B", 901, 0, 1, 12, "", "", "", 80, 80, 13, 20, 40, "", "", 1 } })
    M.Advance(0.3)
    H.eq(ns.Legacy.journey.queuedKey, 0, "a Royale queue is no Journey queue")
end)
