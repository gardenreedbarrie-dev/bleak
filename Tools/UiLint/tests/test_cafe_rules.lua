-- The café's client as the server's rules have it (section 21): today's XP is credited XP (the half band adds at most
-- half), the pickup's clock runs through a danger pause, Tired halves XP and points only, a click refused by its send
-- gate still counts, the summary card waits out the fight that ended the shift, the café's questions use its own
-- frame, the bar names a pause, the "at the bar" list is for bystanders, and the words match across windows.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local CAFE_BIT = { [6] = 131072 }
local DOT = " \194\183 "

-- CAFST on shift (extra fields by index), today's record, the Rush
local function cafst(M, extra, day)
    local r = { 1, 1, 6, 1890, 1600, 2320, 760, 14, 9, 4, 10600, 212, "E", "E", 3, 2, 3600, 0 }
    for k, v in pairs(extra or {}) do
        r[k] = v
    end
    H.send(M, "CAFST", { r, day or { "D", 210, 450, 450, 30000, 180000, 180, 400, 14 }, { "R", 1, 180, 0, 60, 0 } })
end

local function offShift(M, level, flags, tiredSec)
    H.send(M, "CAFST", { { 0, 0, level or 6, 1890, 1600, 2320, "", "", "", "", "", "", "", "", "", "", tiredSec or "",
        flags or "" }, { "D", 210, 450, 450, 30000, 180000, 180, 400, 14 } })
    M.Advance(0.1)
end

local function cafes(M, open1, rushState, rushSec)
    H.send(M, "CAFE", { { 1, open1 or 1, 1, 2, rushState or 1, rushSec or 180, 45 }, { 2, 1, 0, 0, 1, 180, 60 } })
end

local function connect(M)
    FX.connect(M, H, CAFE_BIT)
    cafes(M)
    M.Advance(0.2)
end

local function onShift(M, extra, day)
    connect(M)
    cafst(M, extra, day)
    M.Advance(0.3)
end

local function ticket(M, kind, customer, nextStep)
    H.send(M, "CAFT", { { 41, 1209, 103, kind or "P", customer or "Brenna", 57000, 60000, nextStep or 2, 1,
        kind == "N" and "One latte, please." or "", { { 1, "P" }, { 3, "N" }, { 6, "N" }, { 16, "N" }, { 25, "N" } },
        2100 } })
end

local function printed(M, text, frame)
    local n = 0
    for _, c in ipairs(M.chat) do
        if (frame == nil or c.frame == frame) and tostring(c.msg):find(text, 1, true) then
            n = n + 1
        end
    end
    return n
end

local function count(M, op, from)
    local n = 0
    for _, it in ipairs(H.intents(M, from)) do
        if it.op == op then
            n = n + 1
        end
    end
    return n
end

local function textColor(fs)
    local r, g, b = fs:GetTextColor()
    return string.format("%02X%02X%02X", math.floor(r * 255 + 0.5), math.floor(g * 255 + 0.5),
        math.floor(b * 255 + 0.5))
end

test("cafe rules: the pickup's clock runs on through a pause; only a live Rush stands still", function(M, ns)
    connect(M)
    offShift(M)
    local Cafe = ns.Cafe
    H.send(M, "CAFO", { { 1210, 1, 103, "R", "", "", 5, 5, 120, 5300, 530 } })
    M.Advance(1, 0.5)
    local chip = M.env.BleakholdCafeOrderChip
    H.contains(chip.status:GetText(), "Ready at the counter" .. DOT .. "01:59")
    -- danger at the counter: the Rush is only coming (rushState 1, wall-clock time on the server)
    cafes(M, 2, 1, 600)
    M.Advance(60, 0.5)
    local o = ns.S.cafeOrder
    H.ok(math.abs(Cafe.OrderLeft(o) - 59) < 0.6, "the pickup ran on: " .. Cafe.OrderLeft(o))
    H.ok(not chip.status:GetText():find("paused", 1, true), "no (paused) on the pickup: " .. chip.status:GetText())
    H.contains(chip.status:GetText(), "00:59")
    H.ok(math.abs(Cafe.RushLeft(ns.S.cafes[1], 1) - 540) < 0.6, "a coming Rush keeps counting")
    M.Hover(chip)
    H.contains(M.env.GameTooltip.__lines[2], "your pickup's time keeps running")
    M.Hover(chip, false)
    -- the menu's line says the same
    H.ok(not ns.CafeMenu.ORDER_STATE.R(o):find("paused", 1, true), "the menu's pickup line")
    -- the resume pushes nothing back: the CAFO E would come when the chip says it does
    cafes(M, 1, 1, 540)
    M.Advance(1, 0.5)
    H.ok(math.abs(Cafe.OrderLeft(o) - 58) < 0.6, "not pushed back by the paused span: " .. Cafe.OrderLeft(o))
    -- a live Rush and the house stand still
    H.send(M, "CAFO", { { 1210, 1, 103, "H", "", "", 2, 5, 40, 5300, 530 } })
    cafes(M, 2, 2, 300)
    M.Advance(30, 0.5)
    H.ok(math.abs(Cafe.RushLeft(ns.S.cafes[1], 1) - 300) < 0.01, "a live Rush stood still")
    H.ok(math.abs(Cafe.OrderLeft(ns.S.cafeOrder) - 40) < 0.01, "the house's clock stood still")
    H.contains(chip.status:GetText(), "(paused)", "the house's line says so")
end)

test("cafe rules: a drink in the half-rate band shows the XP it still earned", function(M, ns)
    onShift(M)
    ticket(M)
    M.Advance(0.2)
    local rs = M.env.BleakholdCafeResult
    local hud = ns.Cafe.Hud
    -- 26 XP earned in the half band: 13 credited, 13 taken
    H.send(M, "CAFRES", { { 41, 103, "G", 13, 600, 12, 0, 0, 6, "Brenna", "", 13 } })
    H.eq(rs.sub:GetText(), "+13 XP (half rate)" .. DOT .. "+", "the XP and the half rate, then the tip")
    H.eq(rs.money.copper, 600)
    -- the odd point the server rounds over the day
    H.eq(hud.ResultXpText(13, 14), "+13 XP (half rate)")
    -- a drink that ran into the cap: the cut named
    H.eq(hud.ResultXpText(3, 23), "+3 XP (-23 from the daily cap)")
    -- nothing more today
    H.send(M, "CAFRES", { { 41, 103, "G", 0, 0, 12, 0, 0, 6, "Brenna", "", 20 } })
    H.eq(rs.sub:GetText(), "Daily XP cap reached" .. DOT .. "+12 pts", "the cap, and the points it still earned")
    H.eq(hud.ResultXpText(27, 0), "+27 XP")
    H.eq(hud.ResultXpText(0, 0), nil)
end)

test("cafe rules: a player's order the house takes over is not a customer who left", function(M, ns)
    onShift(M)
    ticket(M, "P", "Brenna")
    M.Advance(0.2)
    local rs = M.env.BleakholdCafeResult
    H.send(M, "CAFRES", { { 41, 103, "L", 0, 0, 0, 0, 0, 6, "Brenna", "Too slow: the house is finishing it.", 0 } })
    H.eq(rs.word:GetText(), "Taken Over")
    H.eq(rs.sub:GetText(), "Rosalind Thornbury is finishing Brenna's order.", "a system line, never quoted")
    -- the customer of a player's order who is gone: unquoted too
    ticket(M, "P", "Brenna")
    M.Advance(0.2)
    H.send(M, "CAFRES", { { 41, 103, "L", 0, 0, 0, 0, 0, 6, "Brenna", "The customer has gone.", 0 } })
    H.eq(rs.word:GetText(), "Customer Left")
    H.eq(rs.sub:GetText(), "The customer has gone.")
    -- an NPC's complaint is speech
    ticket(M, "N", "Sergeant Corwin Ashgrove")
    M.Advance(0.2)
    H.send(M, "CAFRES", { { 41, 103, "L", 0, 0, 0, 0, 0, 6, "Sergeant Corwin Ashgrove",
        "Too slow. I'll find coffee elsewhere.", 0 } })
    H.eq(rs.word:GetText(), "Customer Left")
    H.eq(rs.sub:GetText(), "\"Too slow. I'll find coffee elsewhere.\"")
end)

test("cafe rules: Tired names what is halved, warns before it, and the Shift tab says how long to rest", function(M, ns)
    onShift(M, { [17] = 240 })
    local st = M.env.BleakholdCafeStrip
    H.contains(st.warn:GetText(), "Tired in 04:00", "five minutes before it: a countdown")
    M.Advance(30, 0.5)
    H.contains(st.warn:GetText(), "Tired in 03:30")
    cafst(M, { [17] = 900, [18] = 4 })
    M.Advance(0.3)
    H.contains(st.warn:GetText(), "Tired: barista XP and Caf\195\169 Points halved (15:00 rest off shift)")
    H.ok(not st.warn:GetText():find("rewards", 1, true), "never all rewards: tips are full")
    -- hours of work left: no line
    cafst(M, { [17] = 3000 })
    M.Advance(0.3)
    H.ok(not st.warn:IsShown(), "nothing to warn about")
    -- off shift, Tired: the Shift tab says it before Start Shift
    offShift(M, 6, 4, 600)
    ns.UI.Open("cafeshift")
    M.Advance(0.2)
    local sh = ns.CafeWindow.shift
    H.eq(sh.note:GetText(), "Tired: barista XP and Caf\195\169 Points are halved for 10:00 more rest")
    H.eq(textColor(sh.note), ns.UI.C.orange:upper(), "in orange")
    M.Advance(60, 0.5)
    H.contains(sh.note:GetText(), "09:00 more rest", "it runs down off shift")
    ns.UI.Open("cafehelp")
    M.Advance(0.2)
    H.contains(ns.CafeWindow.help.sections[4].text:GetText(), "Tired: barista XP and Caf\195\169 Points are halved")
end)

test("cafe rules: a Staff Drink chosen right after End Shift shows as asked, sent when the gate opens", function(M, ns)
    onShift(M)
    M.env.BleakholdCafeStrip.endBtn:Click()
    H.eq(H.lastIntent(M, "CSHIFT").payload, "1,0")
    -- a second End Shift inside the gate: told, not silent
    M.env.BleakholdCafeStrip.endBtn:Click()
    H.eq(count(M, "CSHIFT"), 1, "one CSHIFT")
    H.eq(printed(M, "One moment...", M.env.UIErrorsFrame), 1, "the refused click says so")
    M.Advance(0.2)
    H.send(M, "CAFSUM", { { 1, "E", 1840, 14, 9, 10600, 212, 0, 190, 4, 1 } })
    offShift(M, 7, 16)
    M.Advance(0.7)
    local s = M.env.BleakholdCafeSummary
    H.ok(s:IsShown(), "the card")
    local c = s.staff.choices
    c[1]:Click()
    M.Advance(0.1)
    H.eq(count(M, "CSTAFF"), 0, "the shared gate is still shut")
    H.ok(c[1].chosen:IsShown(), "but the choice shows at once")
    H.eq(s.staff.note:GetText(), "Asking for your Staff Drink...")
    H.ok(not c[2]:IsEnabled(), "the others wait")
    M.Advance(1.5, 0.1)
    H.eq(count(M, "CSTAFF"), 1, "sent once the gate opened")
    offShift(M, 7, "")
    H.eq(s.staff.note:GetText(), "Enjoy your Staff Drink.", "confirmed")
end)

test("cafe rules: Cancel right after Order goes out when the gate opens, unless the order moved on", function(M, ns)
    connect(M)
    offShift(M)
    ns.Cafe.Send("CORDER", 1, 103, 10)
    H.send(M, "CAFO", { { 1210, 1, 103, "Q", 1, "", 0, 5, "", 5300, 530 } })
    M.Advance(0.3)
    local chip = M.env.BleakholdCafeOrderChip
    H.ok(chip.cancel:IsShown(), "Cancel on the chip")
    chip.cancel:Click()
    H.eq(count(M, "CCANCEL"), 0, "not yet: CORDER's gate")
    H.eq(printed(M, "One moment...", M.env.UIErrorsFrame), 1, "told it is coming")
    M.Advance(2.5, 0.1)
    H.eq(H.lastIntent(M, "CCANCEL").payload, "1210", "sent when the gate opened")
    -- a cancel that waits while the order is taken: dropped
    M.Advance(3)
    H.send(M, "CAFO", { { 1211, 1, 103, "Q", 1, "", 0, 5, "", 5300, 530 } })
    ns.Cafe.Send("CORDER", 1, 103, 0)
    M.Advance(0.1)
    chip.cancel:Click()
    H.send(M, "CAFO", { { 1211, 1, 103, "M", "", "Aldric", 1, 5, "", 5300, 530 } })
    M.Advance(2.5, 0.1)
    H.eq(count(M, "CCANCEL"), 1, "no cancel for an order being made")
end)

test("cafe rules: the shift summary waits out the fight or the death that ended the shift", function(M, ns)
    onShift(M)
    local s = M.env.BleakholdCafeSummary
    M.SetCombat(true)
    H.send(M, "CAFSUM", { { 1, "C", 1840, 14, 9, 10600, 212, 0, 190, 4, 1 } })
    H.send(M, "CAFST", { { 0, 0, 6, 1890, 1600, 2320 }, { "D", 210, 450, 450, 30000, 180000, 180, 400, 14 } })
    M.Advance(0.3)
    H.ok(not s:IsShown(), "no card in the fight")
    H.eq(printed(M, "Combat ended your shift. Your shift's summary opens after the fight."), 1, "told at once")
    M.Advance(5)
    H.ok(not s:IsShown(), "still fighting")
    M.SetCombat(false)
    M.Advance(0.1)
    H.ok(s:IsShown(), "after the fight")
    H.eq(s.reason:GetText(), "Combat ended your shift.")
    s:Hide()
    -- died on shift: after the Release Spirit popup, once alive
    cafst(M)
    M.Advance(0.3)
    M.dead = true
    H.send(M, "CAFSUM", { { 1, "D", 600, 3, 1, 900, 40, 0, 30, 1, 0 } })
    M.Advance(0.3)
    H.ok(not s:IsShown(), "not over the Release Spirit popup")
    H.eq(printed(M, "opens when you are alive again"), 1)
    M.FireEvent("PLAYER_ALIVE")
    M.Advance(0.1)
    H.ok(not s:IsShown(), "a ghost is still dead")
    M.dead = false
    M.FireEvent("PLAYER_UNGHOST")
    M.Advance(0.1)
    H.ok(s:IsShown(), "back on their feet")
    H.eq(s.reason:GetText(), "You died, logged out or left the map.")
end)

test("cafe rules: the Bin question is the café's own, goes with the shift; a late Bin sends nothing", function(M, ns)
    onShift(M, { [13] = "V", [14] = "V" })
    ticket(M, "P", "Brenna", 5)
    M.Advance(0.3)
    local n = count(M, "CSTEP")
    M.env.BleakholdCafeStep3:Click()
    local d = M.env.BleakholdCafeConfirm
    H.ok(d and d:IsShown(), "the café's confirmation")
    H.ok(not (M.env.BleakholdDialog and M.env.BleakholdDialog:IsShown()), "not the kit's shared dialog")
    -- the ticket is gone before the answer (the customer left): Bin sends nothing
    H.send(M, "CAFT", { { 0 } })
    M.Advance(0.2)
    d.ok:Click()
    H.eq(count(M, "CSTEP"), n, "no CSTEP for a ticket that is gone")
    -- the shift ends while it asks: it goes
    ticket(M, "P", "Brenna", 5)
    M.Advance(0.3)
    M.env.BleakholdCafeStep3:Click()
    H.ok(d:IsShown())
    H.send(M, "CAFSUM", { { 1, "I", 600, 3, 1, 900, 40, 0, 30, 1, 0 } })
    M.Advance(0.1)
    H.ok(not d:IsShown(), "gone with the shift")
    -- combat while it asks: it goes at once
    cafst(M, { [13] = "V", [14] = "V" })
    ticket(M, "P", "Brenna", 5)
    M.Advance(0.3)
    M.env.BleakholdCafeStep3:Click()
    H.ok(d:IsShown())
    M.SetCombat(true)
    H.ok(not d:IsShown(), "gone when the fight starts")
    H.eq(count(M, "CSTEP"), n, "never sent")
    -- another window's question on the kit's dialog is never closed by the café
    M.SetCombat(false)
    local kit = ns.UI.Confirm("Reroll?", function() end)
    cafst(M, { [13] = "V", [14] = "V" })
    M.Advance(0.1)
    H.send(M, "CAFSUM", { { 1, "E", 600, 3, 1, 900, 40, 0, 30, 1, 0 } })
    M.Advance(0.1)
    H.ok(kit:IsShown(), "the kit's dialog left alone")
end)

test("cafe rules: in a danger pause the bar says so and lights no next slot; a press sends nothing", function(M, ns)
    onShift(M)
    ticket(M, "P", "Brenna", 2)
    M.Advance(0.3)
    local bar = M.env.BleakholdCafeBar
    H.ok(M.env.BleakholdCafeStep1.isNext, "Pull Shot is next")
    H.contains(bar.hint:GetText(), "Next: Pull Shot [1]")
    cafes(M, 2)
    M.Advance(0.3)
    for i = 1, 8 do
        H.ok(not M.env["BleakholdCafeStep" .. i].isNext, "slot " .. i .. " not next")
    end
    H.eq(bar.hint:GetText(), "Paused: danger nearby")
    H.eq(textColor(bar.hint), ns.UI.C.red:upper(), "in red")
    local n = count(M, "CSTEP")
    M.env.BleakholdCafeStep1:Click()
    H.eq(count(M, "CSTEP"), n, "nothing sent")
    H.eq(printed(M, "paused", M.env.UIErrorsFrame), 1, "told why")
    cafes(M, 1)
    M.Advance(0.3)
    H.ok(M.env.BleakholdCafeStep1.isNext, "next again after the resume")
    H.contains(bar.hint:GetText(), "Next: Pull Shot [1]")
end)

test("cafe rules: the at-the-bar list is for bystanders, on the left clear of the quest tracker", function(M, ns)
    connect(M)
    offShift(M)
    local ex = FX.examples(M)
    H.send(M, "CAFAT", ex.CAFAT)
    M.Advance(0.3)
    local ab = M.env.BleakholdCafeAtBar
    H.ok(ab:IsShown(), "a bystander sees it")
    local p, rel, rp, x, y = ab:GetPoint(1)
    H.eq(p .. ">" .. rp, "TOPLEFT>LEFT", "on the left, its top fixed")
    H.ok(rel == M.env.UIParent and x == 40 and y == 8, "40 in, 8 over the middle")
    -- on shift the queue is there: the list is not
    cafst(M)
    M.Advance(0.3)
    H.ok(not ab:IsShown(), "hidden for a barista on shift")
    H.send(M, "CAFAT", ex.CAFAT)
    M.Advance(0.3)
    H.ok(not ab:IsShown(), "and stays hidden")
end)

test("cafe rules: from memory is counted by the addon; below level 6 the command says when it opens", function(M, ns)
    connect(M)
    offShift(M, 3)
    M.env.SlashCmdList.BLEAKHOLD("cafe memory on")
    H.eq(printed(M, "From memory opens at barista level 6; it turns on then."), 1)
    -- level 6 (flag 2) with the option on: a served drink counts, a ruined one does not
    cafst(M, { [18] = 2 })
    ticket(M)
    M.Advance(0.3)
    H.ok(ns.Cafe.MemoryMode(), "from memory now")
    H.send(M, "CAFRES", { { 41, 103, "P", 27, 1400, 22, 4, 0, 6, "Brenna", "", 0 } })
    H.send(M, "CAFRES", { { 41, 103, "S", 5, 0, 2, 0, 0, 6, "Brenna", "", 0 } })
    H.send(M, "CAFRES", { { 41, 103, "R", 0, 0, 0, 0, 0, 6, "Brenna", "", 0 } })
    H.eq(ns.Cafe.MemoryDrinks(), 2, "two served from memory")
    M.env.SlashCmdList.BLEAKHOLD("cafe memory off")
    H.send(M, "CAFRES", { { 41, 103, "G", 12, 0, 12, 0, 0, 6, "Brenna", "", 0 } })
    H.eq(ns.Cafe.MemoryDrinks(), 2, "not with the steps shown")
    H.send(M, "CAFP", { { 6, 1890, 1600, 2320, 412, 300, 0, 14, 5100, 0, 1 } })
    ns.UI.Open("caferewards")
    M.Advance(0.2)
    local rw = ns.CafeWindow.rewards
    H.contains(rw.life[5]:GetText(), "From memory (addon)", "labelled as the addon's count")
    H.contains(rw.life[5]:GetText(), "2", "the addon's count, not CAFP's 0")
    M.Hover(rw.memoryHit)
    H.contains(M.env.GameTooltip.__lines[3], "Counted by your Bleakhold addon")
end)

test("cafe rules: recipe tooltips name the player's keys; one name for shakes; autoselect explained", function(M, ns)
    connect(M)
    offShift(M)
    local K = ns.CafeKit
    H.eq(K.StepTip(3)[2][1], "Espresso Machine [1]")
    M.env.SlashCmdList.BLEAKHOLD("cafe keys q,w,e,r,t,y,u,i")
    H.eq(K.StepTip(3)[2][1], "Espresso Machine [Q]", "the remapped key, as the bar and the ticket show it")
    ns.UI.Open("caferecipes")
    M.Advance(0.2)
    H.eq(ns.CafeWindow.recipes.filter.buttons[4].label:GetText(), "Shakes", "the filter: the tabs' plural")
    H.eq(ns.CafeMenu.TABS[3].label, "Shakes", "the menu's tab")
    ns.UI.Open("cafehelp")
    M.Advance(0.2)
    local opts = ns.CafeWindow.help.sections[6].text:GetText()
    H.contains(opts, "a newly taken ticket becomes the one your keys work on (unless a drink is in your hands)")
end)
