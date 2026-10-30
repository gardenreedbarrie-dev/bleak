-- The Rift page's stats and Enter button against the server's rules (Rift.lua; mod-bleakhold bh_rift.cpp RiftEnter,
-- bh_ui_bridge.cpp SyncRift): the bests come from BHMP U alone (RIFT's idle bestFloor is the best of any party size,
-- the bridge's RiftBestAny), and Enter greys with RiftEnter's own words while the player could not go in (level,
-- combat, death, a flight; a follower's single line), checked again every second while the page is open.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local U_OPEN = "U;24;18;12;9;20;80;1;0;50"

local function state(M, combat, dead, taxi)
    M.env.UnitAffectingCombat = function(u) return u == "player" and combat or false end
    M.env.UnitIsDeadOrGhost = function(u) return u == "player" and dead or false end
    M.env.UnitOnTaxi = function(u) return u == "player" and taxi or false end
end

test("rift page: before U no best is shown, RIFT's any-size best never stands in for Best Solo", function(M, ns)
    FX.connect(M, H)
    -- idle RIFT: bestFloor 20 is the best of any size (a group's floor 20 here), not a solo best
    H.send(M, "RIFT", { { 0, 0, "", "", "", "", 20, "", 42 } })
    ns.UI.Open("rift")
    M.Advance(0.3)
    local P = ns.Rift
    H.ok(not ns.Legacy.rift.known, "no U yet")
    for i, v in ipairs(P.bests) do
        H.eq(v:GetText(), "-", P.bests[i].label:GetText() .. " waits for U")
    end
    -- U: the bests by party size
    ns.Legacy.Receive("U;3;0;0;20;20;80;1;0;50")
    P:Refresh()
    H.eq(P.bests[1]:GetText(), "3", "Best Solo")
    H.eq(P.bests[2]:GetText(), "-", "Best Duo")
    H.eq(P.bests[4]:GetText(), "20", "Best Group")
end)

test("rift page: under the rift's level, in the server's words", function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 72
    ns.Legacy.Receive(U_OPEN)
    ns.UI.Open("rift")
    M.Advance(0.3)
    local P = ns.Rift
    H.eq(P.note:GetText(), "You need to be level 80.")
    H.ok(not P.enter:IsEnabled())
end)

test("rift page: the opener in combat, dead or on a flight: Enter greyed with RiftEnter's words", function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 80
    ns.Legacy.Receive(U_OPEN)
    ns.UI.Open("rift")
    M.Advance(0.3)
    local P = ns.Rift
    H.ok(P.enter:IsEnabled(), "free: Enter")
    local cases = {
        { { true, false, false }, "You are in combat." },
        { { false, true, false }, "You are dead." },
        { { false, false, true }, "You are busy (battleground or flight)." },
    }
    for _, c in ipairs(cases) do
        state(M, c[1][1], c[1][2], c[1][3])
        P:Refresh()
        H.eq(P.note:GetText(), c[2])
        H.ok(not P.enter:IsEnabled(), c[2] .. ": Enter greyed")
        H.ok(not P.dd:IsEnabled(), c[2] .. ": no start floor")
    end
    -- the same with a party, as its leader
    M.SetGroup("PARTY", 3, true)
    state(M, true, false, false)
    P:Refresh()
    H.eq(P.note:GetText(), "You are in combat.")
    state(M, false, false, false)
    P:Refresh()
    H.ok(P.enter:IsEnabled(), "free again")
end)

test("rift page: a follower who is dead, in combat or on a flight is told when it can follow", function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 80
    ns.Legacy.Receive(U_OPEN)
    M.SetGroup("PARTY", 3, false)
    ns.UI.Open("rift")
    M.Advance(0.3)
    local P = ns.Rift
    H.eq(P.enter.label:GetText(), "Follow your party")
    H.ok(P.enter:IsEnabled())
    for _, st in ipairs({ { true, false, false }, { false, true, false }, { false, false, true } }) do
        state(M, st[1], st[2], st[3])
        P:Refresh()
        -- never "Your party is in the rift": the client cannot tell (RiftEnter says that on its follow path only, and
        -- "Only your party leader can open the rift." with no pending floor), so the line holds either way
        H.eq(P.note:GetText(),
            "You can follow your party into the rift once you are alive, out of combat and not on a flight.")
        H.ok(not P.note:GetText():find("is in the rift", 1, true), "no claim that the party is inside")
        H.ok(not P.enter:IsEnabled(), "the follow is refused")
    end
end)

test("rift page: Enter is checked again every second while the page is open", function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 80
    ns.Legacy.Receive(U_OPEN)
    state(M, false, false, false)
    ns.UI.Open("rift")
    M.Advance(0.3)
    local P = ns.Rift
    H.ok(P.enter:IsEnabled())
    -- the fight starts: no STATE, no message, only the clock
    state(M, true, false, false)
    M.Advance(1.2)
    H.ok(not P.enter:IsEnabled(), "greyed within a second of the fight")
    H.eq(P.note:GetText(), "You are in combat.")
    state(M, false, false, false)
    M.Advance(1.2)
    H.ok(P.enter:IsEnabled(), "back once out of combat")
    H.eq(P.note:GetText(), "50 different floors are waiting.")
end)
