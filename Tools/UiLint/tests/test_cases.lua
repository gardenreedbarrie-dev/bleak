-- Cases (section 15): the case list and the tooltip line, right-click in the bags, the case window (rewards
-- with chances, Unlock, the reel spinning until UNBOX and stopping on the reward, skipping, errors, keys).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local CASE_BIT = { [6] = 256 }

local function setup(M, counts)
    counts = counts or { [990001] = 3 }
    M.env.GetItemCount = function(id) return counts[id] or 0 end
    M.env.GetContainerNumSlots = function(bag) return bag == 0 and 16 or 0 end
    M.env.GetContainerItemID = function(bag, slot)
        if bag == 0 and slot == 5 and (counts[990001] or 0) > 0 then
            return 990001
        end
        return bag == 0 and slot == 1 and 6948 or nil   -- the hearthstone
    end
    M.items[32837] = { name = "Gold Glaive" }
    M.items[32838] = { name = "Rainbow Glaive" }
    M.items[990001] = { name = "Glaive Case" }
    return counts
end

local function caseDef(M, extra)
    local head = { 990001, "Glaive Case", "Unlock it to receive one of the items below.", "", "" }
    for k, v in pairs(extra or {}) do head[k] = v end
    H.send(M, "CASE", { head, { 32837, 1, 1200, 4 }, { 32838, 2, 400, 5 } })
end

local function intents(M, op)
    local out = {}
    for _, it in ipairs(H.intents(M)) do
        if it.op == op then
            out[#out + 1] = table.concat(it.fields, ",")
        end
    end
    return out
end

local function gets(M)
    local out = {}
    for _, it in ipairs(H.intents(M)) do
        if it.op == "GET" then
            out[#out + 1] = table.concat(it.fields, ",")
        end
    end
    return table.concat(out, ";")
end

local function open(M, ns)
    setup(M)
    FX.connect(M, H, CASE_BIT)
    H.send(M, "CASES", { { 990001 }, { 990002 } })
    M.env.UseContainerItem(0, 5)
    return ns.Cases, ns.Cases.frame
end

test("cases: the list after HELLO, the tooltip line and right-click in the bags", function(M, ns)
    setup(M)
    FX.connect(M, H, CASE_BIT)
    M.Advance(1)
    H.contains(gets(M), "CASES", "GET CASES with feature bit 256")
    H.send(M, "CASES", { { 990001 }, { 990002 } })
    H.ok(ns.S.cases[990001] and ns.S.cases[990002], "two cases")
    local lines = ns.Tooltip.Lines(990001)
    H.contains(lines[#lines][1], "right-click", "case items say how to open them")
    M.env.UseContainerItem(0, 1)
    H.ok(not ns.Cases.frame:IsShown(), "other items do not open it")
    M.env.UseContainerItem(0, 5)
    H.ok(ns.Cases.frame:IsShown(), "a case opens the window")
    M.Advance(0.5)
    H.contains(gets(M), "CASE,990001", "and asks what it holds")
end)

test("cases: no feature bit, no list", function(M, ns)
    setup(M)
    FX.connect(M, H)
    M.Advance(1)
    H.ok(not gets(M):find("CASES", 1, true), "no GET CASES")
    M.env.UseContainerItem(0, 5)
    H.ok(not ns.Cases.frame:IsShown())
    M.env.SlashCmdList.BLEAKHOLD("case")
    local said = false
    for _, c in ipairs(M.chat) do
        said = said or tostring(c.msg):find("no cases", 1, true) ~= nil
    end
    H.ok(said, "/bh case explains")
end)

test("cases: the window shows the rewards and their chances", function(M, ns)
    local CA, f = open(M, ns)
    H.eq(f.text:GetText(), "Loading the case...")
    H.ok(not f.unlock.enabled, "nothing to unlock before the case arrives")
    caseDef(M)
    H.eq(f.title:GetText(), "GLAIVE CASE")
    H.eq(f.count:GetText(), "3 in your bags")
    H.eq(f.text:GetText(), "Unlock it to receive one of the items below.")
    local cards = CA.gridCards.items
    H.eq(CA.gridCards.used, 2, "two rewards")
    H.eq(cards[1].chance:GetText(), "12%")
    H.eq(cards[2].chance:GetText(), "4%")
    H.eq(cards[2].name:GetText(), "Rainbow Glaive x2")
    H.ok(f.unlock.enabled, "Unlock is live")
    H.ok(CA.cards[1]:IsShown(), "the reel shows cards")
end)

test("cases: Unlock spins, UNBOX stops the reel on the reward", function(M, ns)
    local CA, f = open(M, ns)
    caseDef(M)
    f.unlock:Click()
    H.eq(table.concat(intents(M, "CASEOPEN"), ";"), "990001", "CASEOPEN sent")
    H.eq(CA.phase, "wait")
    H.ok(not f.unlock.enabled, "one at a time")
    local o = CA.offset
    M.Advance(0.5)
    H.ok(CA.offset > o + 500, "spinning while the server answers")
    H.send(M, "UNBOX", { { 990001, 2, 32838, 2 } })
    H.eq(CA.phase, "stop")
    local target = CA.target
    H.ok(target > CA.MarkerIndex() + 10, "the reward lands a good way ahead")
    H.eq(CA.reel[target], 2, "the reward's card is on the reel")
    M.Advance(3)
    H.eq(CA.phase, "stop", "still slowing down")
    M.Advance(4)
    H.eq(CA.phase, "won")
    H.eq(CA.MarkerIndex(), target, "the marker stops on the reward")
    H.contains(f.result:GetText(), "Rainbow Glaive")
    H.contains(f.result:GetText(), "x2")
    H.eq(f.unlock.label:GetText(), "UNLOCK ANOTHER")
    H.ok(f.unlock.enabled)
    -- the next one spins on from here
    M.Advance(1.3)
    f.unlock:Click()
    H.eq(#intents(M, "CASEOPEN"), 2)
    H.send(M, "UNBOX", { { 990001, 1, 32837, 1 } })
    CA.cards[1]:Click()
    H.eq(CA.phase, "won", "a click on the reel skips to the end")
    H.eq(CA.reel[CA.MarkerIndex()], 1)
end)

test("cases: refusals, no answer, and answers out of turn", function(M, ns)
    local CA, f = open(M, ns)
    caseDef(M)
    H.send(M, "UNBOX", { { 990001, 1, 32837, 1 } })
    H.eq(CA.phase, "idle", "an UNBOX nobody waits for is ignored")
    f.unlock:Click()
    H.send(M, "ERR", { { "CASEOPEN", "1", "bags_full", "Make room in your bags first." } })
    H.eq(CA.phase, "idle")
    H.contains(f.result:GetText(), "Make room in your bags first.")
    M.Advance(1.3)
    f.unlock:Click()
    M.Advance(5.5)
    H.eq(CA.phase, "idle")
    H.contains(f.result:GetText(), "did not answer")
    M.Advance(1.3)
    f.unlock:Click()
    H.send(M, "UNBOX", { { 990002, 1, 32837, 1 } })
    H.eq(CA.phase, "wait", "another case's answer is not ours")
    H.send(M, "UNBOX", { { 990001, 9, 32837, 1 } })
    H.eq(CA.phase, "idle", "a reward the case does not list: no show")
    for _, rec in ipairs({ { { "" } }, { { 990001 } }, { { "x", "y" } }, { { 990001, 0, 1, 1 } } }) do
        H.send(M, "UNBOX", rec)
        H.send(M, "CASE", rec)
    end
end)

test("cases: a key, an empty bag and /bh case", function(M, ns)
    local counts = setup(M, { [990001] = 1 })
    FX.connect(M, H, CASE_BIT)
    H.send(M, "CASES", { { 990001 } })
    M.env.SlashCmdList.BLEAKHOLD("case")
    local CA, f = ns.Cases, ns.Cases.frame
    H.ok(f:IsShown(), "/bh case opens the first case in the bags")
    caseDef(M, { [4] = 990010, [5] = 2 })
    H.ok(not f.unlock.enabled, "no key")
    H.contains(f.need:GetText(), "Needs 2 x")
    counts[990010] = 2
    M.FireEvent("BAG_UPDATE", 0)
    H.ok(f.unlock.enabled, "with the keys")
    counts[990001] = 0
    M.FireEvent("BAG_UPDATE", 0)
    H.ok(not f.unlock.enabled)
    H.contains(f.result:GetText(), "no such case")
end)
