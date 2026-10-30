-- The toast's sub line in the alert's band (Toast.lua): 200 px, the font stepping 11 then 10, past which the client
-- cuts the line with "...". The lines the client writes itself must fit at 10 (SUB_FIXES, the task and group-found
-- toasts); a long reward name takes a shorter wording; the Rift's run-over toast moves its record into the kicker
-- (bh_ui_bridge_map.cpp RiftEndToast: "+72 Mythic Coins, a Rift Cache - new duo best"); its checkpoint line
-- (RiftClearedToast) and the "Eclipse Rift window" line are said shorter; its rewards too many for the band are said
-- shorter with every reward kept; any other server line too long is cut after its last whole clause and marked ", ..."
-- so it never reads as whole. The tooltip keeps the whole line.
local function toastFrame(M)
    return M.env.BleakholdToastFrame
end

local function size(fs)
    local _, px = fs:GetFont()
    return px
end

local function fitsBand(ns, s)
    return ns.Toast.SubFits(s)
end

local function serverToast(M, kind, title, sub, target)
    H.send(M, "TOAST", { { kind, title, sub, target } })
    M.Advance(0.5)
    return toastFrame(M)
end

local function tipLine(M, i)
    return (M.env.GameTooltip.__lines or {})[i]
end

test("toast fit: every sub line the client writes itself fits the band at the smallest size", function(M, ns)
    local T = ns.Toast
    H.eq(T.SUB_SIZES[#T.SUB_SIZES], 10)
    local n = 0
    for target, fixes in pairs(T.SUB_FIXES) do
        for from, to in pairs(fixes) do
            n = n + 1
            H.ok(fitsBand(ns, to), target .. ": '" .. to .. "' fits at 10 px")
            H.ok(not fitsBand(ns, from) or to ~= from, "a fix says it another way")
        end
    end
    H.ok(n >= 3, "the Keys window line, the checkpoint line, the Rift window line")
    H.ok(fitsBand(ns, T.TASK_SUB_SHORT), "the task toast's shortest wording")
    -- the group-found toast, as it is drawn
    ns.Fire("QUEUE_PROPOSAL", { kind = "D" })
    local f = toastFrame(M)
    H.eq(f.sub:GetText(), "Accept in Activities - Dungeons")
    H.ok(f.sub:GetStringWidth() <= T.TEXT_W, "the group-found line fits")
end)

test("toast fit: the keystone line names the page in a line that fits; its tooltip agrees", function(M, ns)
    H.hello(M)
    M.Advance(0.3)
    local f = serverToast(M, "K", "Keystone ready", "Press Start keystone in the Keys window", "keys")
    H.eq(f.sub:GetText(), "Start keystone on Mythic+ Dungeons")
    H.ok(f.sub:GetStringWidth() <= ns.Toast.TEXT_W, "whole on the alert")
    M.Hover(f)
    H.eq(tipLine(M, 2), "Start keystone on Mythic+ Dungeons", "the tooltip has the new name too")
end)

test("toast fit: a task with a long reward drops 'in Activities', then the name; the tooltip has it whole",
    function(M, ns)
    local T = ns.Toast
    local f = toastFrame(M)
    -- short: the whole line
    ns.Fire("TASK_DONE", { kind = "D", title = "Key sweeper", rewardKind = "C", rewardAmount = 20 })
    H.eq(f.sub:GetText(), "Claim 20 Mythic Coins in Activities")
    H.ok(f.sub:GetStringWidth() <= T.TEXT_W)
    M.Advance(T.SHOW_TIME + 0.1)
    -- a long item name: without "in Activities"
    ns.Fire("TASK_DONE", { kind = "W", title = "Rift diver", rewardText = "2x Mythical Cache of the Eclipse" })
    H.eq(f.kicker:GetText(), "Weekly Task Complete")
    H.eq(f.sub:GetText(), "Claim 2x Mythical Cache of the Eclipse")
    H.ok(f.sub:GetStringWidth() <= T.TEXT_W)
    M.Hover(f)
    H.eq(tipLine(M, 2), "Claim 2x Mythical Cache of the Eclipse in Activities", "the tooltip has the whole line")
    M.Hover(f, false)
    M.Advance(T.SHOW_TIME + 0.1)
    -- longer still: the short wording
    ns.Fire("TASK_DONE", { kind = "D", title = "Echo hunter",
        rewardText = "Mythical Cache of the Eclipse, Season Two" })
    H.eq(f.sub:GetText(), T.TASK_SUB_SHORT)
    H.ok(f.sub:GetStringWidth() <= T.TEXT_W)
end)

test("toast fit: the Rift's run-over record goes into the kicker, the rewards stay whole in the sub", function(M, ns)
    H.hello(M)
    M.Advance(0.3)
    local f = serverToast(M, "R", "Eclipse Rift over - floor 9 cleared",
        "+72 Mythic Coins, a Rift Cache - new duo best", "rift")
    H.eq(f.kicker:GetText(), "New Duo Best", "which record, readable")
    H.eq(f.sub:GetText(), "+72 Mythic Coins, a Rift Cache")
    H.eq(size(f.sub), 11, "fits at 11")
    M.Hover(f)
    H.eq(tipLine(M, 1), "Eclipse Rift over - floor 9 cleared")
    H.eq(tipLine(M, 2), "+72 Mythic Coins, a Rift Cache - new duo best", "the server's whole line")
    M.Hover(f, false)
    M.Advance(ns.Toast.SHOW_TIME + 0.1)
    -- a record and nothing else won: the kicker says it, no sub
    f = serverToast(M, "R", "Eclipse Rift over - floor 3 cleared", "New solo best", "rift")
    H.eq(f.kicker:GetText(), "New Solo Best")
    H.eq(f.sub:GetText(), "")
    H.eq(ns.Toast.RecordKicker("+5 Mythic Coins - new group best"), "New Group Best")
    H.eq(select(2, ns.Toast.RecordKicker("+5 Mythic Coins - new group best")), "+5 Mythic Coins")
    H.eq(ns.Toast.RecordKicker("Find and defeat Loken"), nil)
    M.Advance(ns.Toast.SHOW_TIME + 0.1)
    -- only the Rift's record toast: another kind keeps its kicker
    f = serverToast(M, "I", "Eclipse Rift over - floor 9 cleared", "+72 Mythic Coins, a Rift Cache - new duo best",
        "rift")
    H.eq(f.kicker:GetText(), "Bleakhold")
end)

test("toast fit: the checkpoint and Rift-window lines are said shorter; other long lines end at a whole clause",
    function(M, ns)
    local T = ns.Toast
    H.hello(M)
    M.Advance(0.3)
    local f = serverToast(M, "R", "New best: floor 10", "Checkpoint reached - step into the rift portal", "rift")
    H.eq(f.kicker:GetText(), "New Record")
    H.eq(f.sub:GetText(), "Checkpoint reached - take the portal")
    H.ok(f.sub:GetStringWidth() <= T.TEXT_W)
    M.Advance(T.SHOW_TIME + 0.1)
    f = serverToast(M, "I", "Eclipse Rift over - floor 4 cleared", "The run summary is in the Eclipse Rift window",
        "rift")
    H.eq(f.sub:GetText(), "The run summary is on the Rift page")
    M.Advance(T.SHOW_TIME + 0.1)
    -- three rewards: said shorter, the looks (the rarest, last) kept
    f = serverToast(M, "I", "Eclipse Rift over - floor 12 cleared",
        "+150 Mythic Coins, 2 Rift Caches, 3 Mythic-only looks", "rift")
    H.eq(f.sub:GetText(), "+150 Coins, 2 Caches, 3 Mythic looks", "every reward, shorter")
    H.ok(f.sub:GetStringWidth() <= T.TEXT_W)
    M.Hover(f)
    H.eq(tipLine(M, 2), "+150 Mythic Coins, 2 Rift Caches, 3 Mythic-only looks")
    M.Hover(f, false)
    M.Advance(T.SHOW_TIME + 0.1)
    -- the audit's case: a record with three rewards (floor 23, group best)
    f = serverToast(M, "R", "Eclipse Rift over - floor 23 cleared",
        "+150 Mythic Coins, 2 Rift Caches, 3 Mythic-only looks - new group best", "rift")
    H.eq(f.kicker:GetText(), "New Group Best")
    local drawn = f.sub:GetText()
    H.ok(drawn:find("3 ", 1, true) and drawn:find("look", 1, true), "the looks still show: " .. drawn)
    H.ok(drawn:find("150", 1, true) and drawn:find("2 ", 1, true), "and the coins and caches: " .. drawn)
    H.ok(f.sub:GetStringWidth() <= T.TEXT_W)
    M.Advance(T.SHOW_TIME + 0.1)
    -- the shortenings, step by step, every reward kept
    local alts = T.RiftRewardAlts("+150 Mythic Coins, a Rift Cache, a Mythic-only look")
    H.eq(alts[1], "+150 Coins, a Rift Cache, a Mythic-only look")
    H.eq(alts[2], "+150 Coins, a Cache, a Mythic-only look")
    H.eq(alts[3], "+150 Coins, a Cache, a Mythic look")
    H.eq(alts[4], "+150 Coins, a Cache, a look")
    H.eq(#T.RiftRewardAlts("Checkpoint reached - take the portal"), 0, "no reward named: no alts")
    -- another server line too long: cut after a whole clause and marked as cut, never silently
    local steps = "Find Loken in the Halls, then the Bridge of Storms, then the Vault"
    f = serverToast(M, "I", "Eclipse Rift - floor 7", steps, "rift")
    H.eq(f.sub:GetText(), "Find Loken in the Halls, ...", "the cut shows")
    H.ok(f.sub:GetStringWidth() <= T.TEXT_W)
    M.Hover(f)
    H.eq(tipLine(M, 2), steps)
    M.Hover(f, false)
    M.Advance(T.SHOW_TIME + 0.1)
    H.eq(T.Clause("Defeat the vault's guardians - then leave by the portal at the back"),
        "Defeat the vault's guardians - ...", "a ' - ' cut keeps its separator")
    for _, cut in ipairs({ T.Clause(steps), T.Clause("+150 Mythic Coins, 2 Rift Caches, 3 Mythic-only looks") }) do
        H.ok(cut:sub(-3) == T.CLAUSE_MARK and T.SubFits(cut), "marked, and fits with its mark: " .. cut)
    end
    -- no clause boundary (or none long enough): whole, for the client to cut
    local long = "Find and defeat Archimonde the Defiler of the Eclipse"
    f = serverToast(M, "I", "Eclipse Rift - floor 7", long, "rift")
    H.eq(f.sub:GetText(), long)
    H.eq(size(f.sub), 10)
    H.eq(T.Clause("Short - a very long tail that never fits the band at all"), nil,
        "a head under 10 bytes is no clause")
    H.eq(T.Clause(nil), nil)
end)

test("toast fit: a client's own long line is not cut at a clause (only the server's lines are)", function(M, ns)
    local T = ns.Toast
    local line = "+14  -  1810  -  Rank 9  -  Duelist pace  -  up to Duelist"
    T.Push({ kicker = "Arena", title = "Won 1v1", sub = line })
    H.eq(toastFrame(M).sub:GetText(), line, "whole, for the client to cut")
end)

test("toast fit: measuring a line leaves the toast showing as it is", function(M, ns)
    local T = ns.Toast
    T.Push({ kicker = "Bleakhold", title = "Shown", sub = "Find and defeat Loken" })
    local f = toastFrame(M)
    H.ok(not T.SubFits(string.rep("w", 80)))
    H.ok(T.SubFits("ok"))
    H.eq(f.sub:GetText(), "Find and defeat Loken")
    H.eq(size(f.sub), 11)
    H.ok(not f.measure:IsShown(), "the measuring line is never drawn")
end)
