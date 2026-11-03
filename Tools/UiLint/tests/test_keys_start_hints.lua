-- Activities > Mythic+ Dungeons (Keys.lua): Start keystone's hint where the server refuses the keystone, and the season
-- bests after a key ends.
-- An Eclipse Rift floor is built inside a season dungeon (bh_rift.cpp RiftSetupFloor: MODE_RIFT on that instance's
-- BHMP run): the keystone's OnUse and the Font of Power (bh_mplus_scripts.cpp KeyStartBlock) refuse every run there
-- but a fresh Mythic 0. Map.dbc names some wings with their hub ("Auchindoun: Shadow Labyrinth"), the key dungeon only
-- with the wing's. The server sends no L when a run ends (Complete: E, then the bridge's KEY and WEEK).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local ALREADY_RAN = "This instance already had a run. Leave, reset the dungeon and enter again."

local function open(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("keys")
    M.Advance(0.3)
    return ns.Keys
end

-- the leader of 5 inside `zone`, Normal difficulty
local function inside(M, zone)
    M.inInstance, M.instanceType, M.zone = true, "party", zone
    M.SetGroup("PARTY", 5, true)
end

local function bhmp(M, msg)
    M.FireEvent("CHAT_MSG_ADDON", "BHMP", msg, "WHISPER", M.playerName)
end

local function asked(M, from)
    local n = 0
    for i = from + 1, #M.said do
        if M.said[i].msg == ".act mplus" then
            n = n + 1
        end
    end
    return n
end

test("keys hints: a Rift floor in the key's own dungeon refuses the keystone in the server's words", function(M, ns)
    local P = open(M, ns)
    -- the +8 Halls of Lightning key (FX.all's KEY), the player on a Rift floor built in Halls of Lightning
    inside(M, "Halls of Lightning")
    P:Refresh()
    H.contains(P.startHint:GetText(), "Right-click your keystone", "no run here: the right-click is next")
    -- the floor's SendRiftState: S;4 (MODE_RIFT), its boss, RiftSync (state 2 RUNNING)
    bhmp(M, "S;4;4;3;0;;0;0;Eclipse Rift - Halls of Lightning")
    bhmp(M, "B;1;3;0;Loken")
    bhmp(M, "T;60000;0;0;0;0;0;0;2")
    H.send(M, "QUEUE", { { 9, 3, "R", 0, 0, 1, 0 } })
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.StartBlock(), ALREADY_RAN)
    H.ok(not P.start:IsEnabled())
    H.eq(P.startHint:GetText(), ALREADY_RAN, "never 'Right-click your keystone' on a Rift floor")
    -- the floor cleared (state 3): still no keystone there
    bhmp(M, "T;600000;0;0;0;0;0;0;3")
    P:Refresh()
    H.eq(P.startHint:GetText(), ALREADY_RAN)
    -- no S seen (a /reload), only U's floor: the floor alone tells it
    bhmp(M, "X")
    bhmp(M, "U;24;18;12;9;20;80;1;7;50")
    H.ok(ns.Rift.RunFloor() ~= nil, "U's floor")
    P:Refresh()
    H.eq(P.startHint:GetText(), ALREADY_RAN)
    -- a floor in another dungeon: where to use the key, as the server's map check says first
    M.zone = "The Deadmines"
    P:Refresh()
    H.eq(P.startHint:GetText(), "Use your keystone inside Halls of Lightning.")
    -- out of the rift (X, the open world): the usual hint
    bhmp(M, "X")
    M.inInstance, M.instanceType, M.zone = false, "none", "The Storm Peaks"
    P:Refresh()
    H.eq(P.startHint:GetText(), "Use your keystone inside Halls of Lightning.")
end)

test("keys hints: a wing Map.dbc names with its hub is the key's dungeon", function(M, ns)
    local P = open(M, ns)
    -- a Shadow Labyrinth +5 (555), the player inside it
    H.send(M, "KEY", { { 2, 555, 5, { 1, 3, 4 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    inside(M, "Auchindoun: Shadow Labyrinth")
    H.ok(P.InKeyDungeon("Shadow Labyrinth"))
    P:Refresh()
    H.contains(P.startHint:GetText(), "Right-click your keystone", "never 'Use your keystone inside' it")
    -- Heroic there: the server's Normal-only refusal, before the right-click
    M.env.GetInstanceInfo = function()
        return M.zone, M.instanceType, 2, "Heroic", 5, 0, nil
    end
    P:Refresh()
    H.eq(P.startHint:GetText(), P.NORMAL_ONLY)
    M.env.GetInstanceInfo = function()
        return M.zone, M.instanceType, 1, "Normal", 5, 0, nil
    end
    -- the other hubbed wings, and the matches that held before
    for keyName, here in pairs({
        ["The Steamvault"] = "Coilfang: The Steamvault",
        ["Hellfire Ramparts"] = "Hellfire Citadel: Ramparts",
        ["The Shattered Halls"] = "Hellfire Citadel: The Shattered Halls",
        ["Scarlet Monastery: Armory"] = "Scarlet Monastery",
        ["Lower Blackrock Spire"] = "Blackrock Spire",
        ["Halls of Lightning"] = "Halls of Lightning",
    }) do
        M.zone = here
        H.ok(P.InKeyDungeon(keyName), keyName .. " in " .. here)
    end
    -- another wing of the same hub, or a dungeon whose name holds the key's, is not it
    for keyName, here in pairs({
        ["Shadow Labyrinth"] = "Auchindoun: Sethekk Halls",
        ["Halls of Stone"] = "Halls of Lightning",
        ["Stratholme"] = "The Culling of Stratholme",
    }) do
        M.zone = here
        H.ok(not P.InKeyDungeon(keyName), keyName .. " not in " .. here)
    end
    -- outside it: where to go
    M.zone = "Auchindoun: Sethekk Halls"
    P:Refresh()
    H.eq(P.startHint:GetText(), "Use your keystone inside Shadow Labyrinth.")
end)

test("keys hints: a key that ends asks for the season bests again, even within the request limit", function(M, ns)
    local P = open(M, ns)
    inside(M, "Halls of Lightning")
    -- the season list of the last .act mplus: Halls of Lightning best +11
    ns.Legacy.Request(true)
    bhmp(M, "L;602;1800;11;Halls of Lightning")
    bhmp(M, "L;599;1800;9;Halls of Stone")
    M.Advance(0.3)
    local function best(name)
        P:Refresh()
        for _, r in ipairs(P.rows) do
            if r.d and r.d.name == name then
                return r.best:GetText()
            end
        end
    end
    H.eq(best("Halls of Lightning"), "+11")
    local said = #M.said
    H.eq(ns.Legacy.Request(), false, "a plain request within the limit is skipped")
    -- +12 timed there: Complete's MP and MPE, the bridge's KEY; no L
    H.send(M, "MPS", { { 7001, 602, 12, { 1, 3, 4 }, 7, 10000, 1800 } })
    H.send(M, "MP", { { 7001, 1500000, 1800, 2, 10, 100, 100, 7, { 300, 900, 1500 }, "", 2 } })
    H.send(M, "MPE", { { 7001, 1, 1500000, 2, 602, 12, 0 } })
    M.Advance(0.3)
    H.eq(P.endedRun, 7001)
    H.eq(asked(M, said), 1, "MPE asks for L again")
    -- the answer's L moves the Halls of Lightning row
    bhmp(M, "L;602;1800;12;Halls of Lightning")
    bhmp(M, "L;599;1800;9;Halls of Stone")
    M.Advance(0.3)
    H.eq(best("Halls of Lightning"), "+12")
    H.eq(best("Halls of Stone"), "+9")
end)
