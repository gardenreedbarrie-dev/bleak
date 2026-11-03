-- The café's barista bar (CafeBar.lua, section 21): the key overrides and combat, the slots at each station, CSTEP,
-- the release (CREL, a priority send) and the counter's slots.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local CAFE_BIT = { [6] = 131072 }

local function cafst(M, station, onShift, extra)
    local r = { 1, onShift == false and 0 or 1, 6, 1890, 1600, 2320, 120, 0, 0, 0, 0, 0, station or "", station or "", 3, 2,
        3600, 2 }
    for k, v in pairs(extra or {}) do
        r[k] = v
    end
    if onShift == false then
        r = { 0, 0, 6, 1890, 1600, 2320 }
    end
    H.send(M, "CAFST", { r, { "D", 210, 450, 450, 30000, 180000, 180, 400, 14 } })
end

local function ticket(M, nextStep, inHand)
    H.send(M, "CAFT", { { 41, 1209, 103, "P", "Brenna", 57000, 60000, nextStep or 2, inHand or 1, "",
        { { 1, "P" }, { 3, "N" }, { 6, "N" }, { 16, "N" }, { 25, "N" } }, 2100 } })
end

local function onShift(M, station)
    FX.connect(M, H, CAFE_BIT)
    cafst(M, station)
    M.Advance(0.3)
end

local function textColor(fs)
    local r, g, b = fs:GetTextColor()
    return string.format("%02X%02X%02X", math.floor(r * 255 + 0.5), math.floor(g * 255 + 0.5), math.floor(b * 255 + 0.5))
end

local function last(M)
    local list = H.intents(M)
    return list[#list]
end

local function errorsShown(M, text)
    local n = 0
    for _, c in ipairs(M.chat) do
        if c.frame == M.env.UIErrorsFrame and c.msg:find(text, 1, true) then
            n = n + 1
        end
    end
    return n
end

test("cafe bar: a shift binds the eight keys to the bar's buttons, never with priority", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    H.eq(M.OverrideAction("1"), nil, "nothing bound off shift")
    cafst(M, "V")
    for i = 1, 8 do
        local button, priority = M.OverrideButton(tostring(i))
        H.eq(button, "BleakholdCafeStep" .. i, "key " .. i)
        H.eq(priority, false, "never a priority binding (AddicatUI's keypress yields to it)")
    end
    H.ok(M.env.BleakholdCafeBar:IsShown(), "the bar shows on shift")
    H.eq(M.env.BleakholdCafeStep1.hotkey:GetText(), "1")
end)

test("cafe bar: combat gives the keys back before the lockdown and only a fresh CAFST binds again", function(M, ns)
    onShift(M, "V")
    H.ok(M.OverrideButton("1"), "bound")
    M.FireEvent("PLAYER_REGEN_DISABLED")
    M.combat = true
    H.eq(M.OverrideAction("1"), nil, "cleared before the lockdown (the stub fails in lockdown)")
    H.eq(ns.S.cafeState.onShift, false, "the shift is over here until the server says otherwise")
    H.ok(not M.env.BleakholdCafeBar:IsShown(), "the bar hides with it")
    M.combat = false
    M.FireEvent("PLAYER_REGEN_ENABLED")
    H.eq(M.OverrideAction("1"), nil, "no bind when combat ends")
    cafst(M, nil, false)
    H.eq(M.OverrideAction("1"), nil, "off shift: the keys stay free")
    cafst(M, "V")
    H.eq(M.OverrideButton("1"), "BleakholdCafeStep1", "a fresh shift binds again")
end)

test("cafe bar: at the espresso machine a key sends the step, a second press while it runs releases it", function(M, ns)
    onShift(M, "E")
    ticket(M, 2)
    M.Advance(0.3)
    local b = M.env.BleakholdCafeStep1
    H.eq(b.name:GetText(), "Pull Shot", "slot 1 at E")
    H.eq(M.env.BleakholdCafeStep4.name:GetText(), "Froth Foam")
    -- the whole name under each slot: up to two centred lines, 8 px clear of the next slot's
    local Bar = ns.Cafe.Bar
    H.eq(b.name:GetWidth(), Bar.PITCH - 8)
    H.eq(b.name:GetHeight(), Bar.NAME_H)
    H.ok(Bar.NAME_H >= 22 and M.env.BleakholdCafeBar:GetHeight() >= 4 - Bar.SLOT_TOP + Bar.SLOT + 3 + Bar.NAME_H,
        "the bar is tall enough for two lines")
    H.ok(b.isNext, "the next step's slot glows")
    H.eq(M.env.BleakholdCafeBar.title:GetText(), "Espresso Machine")
    H.contains(M.env.BleakholdCafeBar.hint:GetText(), "Next: Pull Shot [1]")
    b:Click()
    local it = last(M)
    H.eq(it.op, "CSTEP")
    H.eq(it.payload, "41,2,3")
    H.send(M, "CAFEV", { { 41, 2, 3, "S", 3000, 2160, 2610, "", 2 } })
    M.Advance(1.5, 1.5)
    b:Click()
    it = last(M)
    H.eq(it.op, "CREL")
    H.eq(it.payload, "41,2,1500", "the time since CAFEV S, measured here")
    H.ok(b.slotChecked, "a running timed step lights its slot")
    local n = #H.intents(M)
    M.Advance(0.2, 0.2)
    b:Click()
    H.eq(#H.intents(M), n, "one release per step")
    H.send(M, "CAFEV", { { 41, 2, 3, "D", 3000, 2160, 2610, "P", 3 } })
    ticket(M, 3)
    M.Advance(0.3)
    H.ok(M.env.BleakholdCafeStep4.isNext, "then Froth Foam")
    M.env.BleakholdCafeStep4:Click()
    H.eq(last(M).payload, "41,3,6")
end)

test("cafe bar: a running tap names itself in the hint with the seconds left and lights its slot", function(M, ns)
    onShift(M, "G")
    ticket(M, 1, 0)
    M.Advance(0.3)
    local bar, b = M.env.BleakholdCafeBar, M.env.BleakholdCafeStep1
    H.eq(bar.hint:GetText(), "Next: Grind Beans [1]")
    H.ok(b.isNext and not b.slotChecked, "the next step glows, nothing runs")
    b:Click()
    H.eq(last(M).payload, "41,1,1")
    H.send(M, "CAFEV", { { 41, 1, 1, "S", 1500, "", "", "", 1 } })
    M.Advance(0.6, 0.1)
    local hint = bar.hint:GetText()
    local left = tonumber(hint:match("^Grind Beans%.%.%. (%d%.%d) s$") or "")
    H.ok(left and left >= 0.8 and left <= 1.0, "the running step and its seconds left, not the Next line: " .. hint)
    H.eq(textColor(bar.hint), "FFFFFF")
    H.ok(b.slotChecked and b.slotCheck:IsShown(), "its slot lit (CheckButtonHilight)")
    H.ok(b.slotCheck:GetParent() == b.over and b.over:GetFrameLevel() > b.cd:GetFrameLevel(),
        "the light sits above the cooldown's swipe")
    H.ok(not b.isNext, "no Next glow while it runs")
    M.Advance(0.5, 0.1)
    local later = tonumber(bar.hint:GetText():match("(%d%.%d) s$") or "")
    H.ok(later and later < left, "the seconds count down")
    b:Click()
    H.ok(errorsShown(M, "A step is running.") >= 1, "a second press is refused")
    H.send(M, "CAFEV", { { 41, 1, 1, "D", 1500, "", "", "P", 2 } })
    ticket(M, 2, 0)
    M.Advance(0.3)
    H.eq(bar.hint:GetText(), "Walk to the Espresso Machine", "after its D: the next step's line")
    H.ok(not b.slotChecked, "the light goes with it")
end)

test("cafe bar: the same step is sent again after ERR cafe_station (never deduplicated)", function(M, ns)
    onShift(M, "E")
    ticket(M, 2)
    M.Advance(0.3)
    M.env.BleakholdCafeStep1:Click()
    M.Advance(0.3)
    H.send(M, "ERR", { { "CSTEP", ns.Comm.lastSeq, "cafe_station", "Walk to the Espresso Machine first." } })
    M.env.BleakholdCafeStep1:Click()
    M.Advance(0.1)
    H.eq(H.countIntents(M, "CSTEP"), 2, "both presses went out")
end)

test("cafe bar: a release goes out in the frame of the press, ahead of a full queue", function(M, ns)
    onShift(M, "E")
    ticket(M, 2)
    M.Advance(1)
    M.env.BleakholdCafeStep1:Click()
    H.send(M, "CAFEV", { { 41, 2, 3, "S", 3000, 2160, 2610, "", 2 } })
    -- empty the token bucket and queue six GETs behind it
    local C = ns.Comm
    for _, topic in ipairs({ "WEEK", "ERA", "TASKS", "KEY", "QUEUE", "MPLUS", "LIDX", "CASES", "CAMPST", "ROYS", "ARENA",
        "CAFE" }) do
        C.Send("GET", { topic })
    end
    local gets = H.countIntents(M, "GET")
    local sent = #M.sent
    M.env.BleakholdCafeStep1:Click()
    H.eq(#M.sent, sent + 1, "sent at once, without waiting for a token")
    H.eq(last(M).op, "CREL")
    H.eq(H.countIntents(M, "GET"), gets, "the queued GETs still wait")
    M.Advance(3)
    H.ok(H.countIntents(M, "GET") > gets, "and go out after it")
end)

test("cafe bar: away from every station the slots show the stations and a press sends nothing", function(M, ns)
    onShift(M, nil)
    ticket(M, 2)
    M.Advance(0.3)
    H.eq(M.env.BleakholdCafeStep1.name:GetText(), "Grinder")
    H.eq(M.env.BleakholdCafeStep7.name:GetText(), "Counter")
    H.ok(M.env.BleakholdCafeStep2.isNext, "the station of the next step glows (Pull Shot: the espresso machine)")
    local n = #H.intents(M)
    M.env.BleakholdCafeStep2:Click()
    M.Advance(0.3)
    H.eq(#H.intents(M), n, "nothing sent")
    H.eq(errorsShown(M, "Walk to the Espresso Machine."), 1)
    H.contains(M.env.BleakholdCafeBar.hint:GetText(), "Walk to the Espresso Machine")
end)

test("cafe bar: at the counter slot 1 takes the next order, or the one chosen in the queue", function(M, ns)
    onShift(M, "V")
    local ex = FX.examples(M)
    H.send(M, "CAFQ", ex.CAFQ)
    M.Advance(0.3)
    H.eq(M.env.BleakholdCafeStep1.name:GetText(), "Take Order")
    H.ok(M.env.BleakholdCafeStep1.isNext, "Take Order pulses while an order can be taken")
    M.env.BleakholdCafeStep1:Click()
    H.eq(last(M).op, "CTAKE")
    H.eq(last(M).payload, "0", "the best one I can make")
    M.Advance(0.7)
    ns.Cafe.SelectOrder(1209)
    M.env.BleakholdCafeStep1:Click()
    H.eq(last(M).payload, "1209")
    -- Serve and Bin need a ticket; Bin asks first once three steps are done
    M.Advance(0.7)
    H.send(M, "CAFT", { { 41, 1209, 103, "P", "Brenna", 57000, 60000, 5, 1, "",
        { { 1, "P" }, { 3, "P" }, { 6, "P" }, { 16, "P" }, { 25, "N" } }, 2100 } })
    M.Advance(0.3)
    H.ok(M.env.BleakholdCafeStep2.isNext, "Serve is next")
    M.env.BleakholdCafeStep2:Click()
    H.eq(last(M).payload, "41,5,25")
    M.Advance(0.3)
    local n = H.countIntents(M, "CSTEP")
    M.env.BleakholdCafeStep3:Click()
    H.eq(H.countIntents(M, "CSTEP"), n, "Bin waits for the confirm")
    local dlg = M.env.BleakholdCafeConfirm
    H.ok(dlg and dlg:IsShown(), "the confirm (the café's own)")
    dlg.ok:Click()
    H.eq(last(M).payload, "41,5,26")
end)

test("cafe bar: off shift the keys are free and the bar hides", function(M, ns)
    onShift(M, "V")
    H.ok(M.env.BleakholdCafeBar:IsShown())
    cafst(M, nil, false)
    H.eq(M.OverrideAction("1"), nil)
    H.ok(not M.env.BleakholdCafeBar:IsShown())
    -- and with the feature off on a new HELLO
    cafst(M, "V")
    H.ok(M.OverrideButton("1"))
    H.hello(M, {})
    H.eq(M.OverrideAction("1"), nil, "HELLO without the bit")
    H.ok(not M.env.BleakholdCafeBar:IsShown())
    H.eq(ns.Cafe.Press(1), false)
end)

test("cafe bar: the keys can be remapped; invalid keys are refused", function(M, ns)
    onShift(M, "V")
    M.env.SlashCmdList.BLEAKHOLD("cafe keys q,w,e,r,t,y,u,i")
    H.eq(M.OverrideButton("Q"), "BleakholdCafeStep1")
    H.eq(M.OverrideButton("I"), "BleakholdCafeStep8")
    H.eq(M.OverrideAction("1"), nil, "the old keys are free")
    H.eq(M.env.BleakholdCafeStep1.hotkey:GetText(), "Q")
    M.env.SlashCmdList.BLEAKHOLD("cafe keys 1,1,2,3,4,5,6,7")
    H.eq(M.OverrideButton("Q"), "BleakholdCafeStep1", "refused: the keys stay")
    M.env.SlashCmdList.BLEAKHOLD("cafe keys shift-1,shift-2,shift-3,shift-4,shift-5,shift-6,shift-7,shift-8")
    H.eq(M.OverrideButton("SHIFT-3"), "BleakholdCafeStep3")
    H.eq(M.env.BleakholdCafeStep3.hotkey:GetText(), "s-3")
end)

test("cafe bar: modifiers in any order bind in the client's ALT-CTRL-SHIFT- order", function(M, ns)
    local Cafe = ns.Cafe
    H.eq(Cafe.ValidKey("SHIFT-CTRL-1"), "CTRL-SHIFT-1")
    H.eq(Cafe.ValidKey("shift-alt-ctrl-q"), "ALT-CTRL-SHIFT-Q")
    H.eq(Cafe.ValidKey("CTRL-SHIFT-1"), "CTRL-SHIFT-1")
    H.eq(Cafe.ValidKey("SHIFT-SHIFT-1"), nil, "a modifier once")
    H.eq(Cafe.ParseKeys("SHIFT-CTRL-1,CTRL-SHIFT-1,3,4,5,6,7,8"), nil, "the same key twice, however it is written")
    onShift(M, "V")
    M.env.SlashCmdList.BLEAKHOLD("cafe keys SHIFT-CTRL-1,2,3,4,5,6,7,8")
    H.eq(M.OverrideButton("CTRL-SHIFT-1"), "BleakholdCafeStep1", "the binding the client looks the key press up by")
    H.eq(M.OverrideButton("SHIFT-CTRL-1"), nil)
end)

test("cafe bar: a tap shows a cooldown on its slot; W, I, X and B are told", function(M, ns)
    onShift(M, "G")
    ticket(M, 1, 0)
    M.Advance(0.3)
    M.env.BleakholdCafeStep1:Click()
    H.eq(last(M).payload, "41,1,1")
    H.send(M, "CAFEV", { { 41, 1, 1, "S", 1500, "", "", "", 1 } })
    H.ok(M.env.BleakholdCafeStep1.cdFor ~= nil, "the cooldown swipe runs")
    M.Advance(0.3)
    local n = #H.intents(M)
    M.env.BleakholdCafeStep2:Click()
    H.eq(#H.intents(M), n, "nothing else while a step runs")
    H.send(M, "CAFEV", { { 41, 1, 2, "W", "", "", "", "", 1 } })
    H.eq(errorsShown(M, "Not that one"), 1)
    H.send(M, "CAFEV", { { 41, 1, 1, "I", "", "", "", "", 1 } })
    H.eq(errorsShown(M, "Interrupted"), 1)
    H.send(M, "CAFEV", { { 41, 1, 2, "X", "", "", "", "", 1 } })
    H.ok(M.env.BleakholdCafeStep2.red:IsShown(), "the wrong slot flashes red")
    M.Advance(0.4)
    H.ok(not M.env.BleakholdCafeStep2.red:IsShown(), "for 0.3 s")
    H.send(M, "CAFEV", { { 41, 1, 26, "B", "", "", "", "", 1 } })
    H.eq(errorsShown(M, "Binned"), 1)
end)

test("cafe bar: a press right after a release or a bin uses CAFEV's nextStep before the CAFT comes", function(M, ns)
    onShift(M, "E")
    ticket(M, 2, 0)
    M.Advance(0.3)
    M.env.BleakholdCafeStep1:Click()
    H.eq(last(M).payload, "41,2,3")
    H.send(M, "CAFEV", { { 41, 2, 3, "S", 3000, 2160, 2610, "", 2 } })
    M.Advance(1.5, 0.5)
    M.env.BleakholdCafeStep1:Click()
    H.eq(last(M).op, "CREL")
    -- the D comes at once, the CAFT only with the next push: Froth Foam right away names step 3
    H.send(M, "CAFEV", { { 41, 2, 3, "D", 3000, 2160, 2610, "P", 3 } })
    local t = ns.Cafe.Ticket(41)
    H.eq(t.nextStep, 3, "the ticket takes the event's nextStep")
    H.eq(t.inHand, true, "the cup is in hand after a done step")
    H.eq(t.steps[2].grade, "P", "and the step's grade")
    M.Advance(0.05)
    M.env.BleakholdCafeStep4:Click()
    H.eq(last(M).payload, "41,3,6", "Froth Foam as step 3, not the stale 2")
    -- ruined: back at step 1, nothing in hand, every step undone
    H.send(M, "CAFEV", { { 41, 3, 6, "X", "", "", "", "", 1 } })
    H.eq(t.nextStep, 1)
    H.eq(t.inHand, false)
    for i, s in ipairs(t.steps) do
        H.eq(s.grade, "N", "step " .. i .. " undone")
    end
    -- the real CAFT overwrites it all
    ticket(M, 4, 1)
    H.eq(ns.Cafe.Ticket(41).nextStep, 4)
end)

test("cafe bar: from memory the bar names no next station, away or at the counter", function(M, ns)
    onShift(M, "")
    ticket(M, 2, 1)
    M.Advance(0.3)
    local bar = M.env.BleakholdCafeBar
    H.eq(bar.hint:GetText(), "Walk to the Espresso Machine", "the checklist's way")
    cafst(M, "", true, { [18] = 2 })
    ns.Cafe.SetOption("cafeMemory", true)
    M.Advance(0.3)
    H.eq(bar.hint:GetText(), "Walk to a station", "from memory: no station named")
    H.ok(not M.env.BleakholdCafeStep2.isNext, "and no station slot glows")
    -- at the counter with Serve next: no "Next: Serve"
    H.send(M, "CAFT", { { 41, 1209, 103, "P", "Brenna", 57000, 60000, 5, 1, "",
        { { 1, "P" }, { 3, "P" }, { 6, "P" }, { 16, "P" }, { 25, "N" } }, 2100 } })
    cafst(M, "V", true, { [18] = 2 })
    M.Advance(0.3)
    H.ok(not (bar.hint:GetText() or ""):find("Serve", 1, true), "no Serve hint: " .. tostring(bar.hint:GetText()))
    ns.Cafe.SetOption("cafeMemory", false)
    M.Advance(0.3)
    H.contains(bar.hint:GetText(), "Next: Serve", "with the checklist")
end)

test("cafe bar: a timed step's key releases it after the barista turned away from the station", function(M, ns)
    onShift(M, "E")
    ticket(M, 2)
    M.Advance(0.3)
    M.env.BleakholdCafeStep1:Click()
    H.send(M, "CAFEV", { { 41, 2, 3, "S", 3000, 2160, 2610, "", 2 } })
    M.Advance(0.5, 0.5)
    -- the barista turns (right mouse button, A/D): CAFST names no station, the server keeps the step running
    cafst(M, nil)
    M.Advance(1.8, 0.1)
    local bar = M.env.BleakholdCafeBar
    H.eq(bar.title:GetText(), "Espresso Machine", "the running step's station stays on the bar")
    H.eq(bar.hint:GetText(), "Release inside the gold [1]")
    H.eq(M.env.BleakholdCafeTiming.bar.right:GetText(), "Release [1]", "the timing bar knows its key")
    H.eq(M.env.BleakholdCafeStep1.name:GetText(), "Pull Shot")
    M.env.BleakholdCafeStep1:Click()
    local it = last(M)
    H.eq(it.op, "CREL", "the release goes out")
    H.eq(it.payload, "41,2,2300")
    H.eq(errorsShown(M, "Walk to the Grinder."), 0, "not a station press")
    -- its D: the bar is back to what CAFST says
    H.send(M, "CAFEV", { { 41, 2, 3, "D", 3000, 2160, 2610, "P", 3 } })
    M.Advance(0.3)
    H.eq(bar.title:GetText(), "Away from the stations")
end)

test("cafe bar: Bin is refused with nothing done, and every word of it says the streak ends", function(M, ns)
    onShift(M, "V")
    ticket(M, 1, 0)
    M.Advance(0.7)
    local bin = M.env.BleakholdCafeStep3
    local n = H.countIntents(M, "CSTEP")
    bin:Click()
    H.eq(H.countIntents(M, "CSTEP"), n, "no Bin at step 1 (the server would only end the streak)")
    H.eq(errorsShown(M, "Nothing in your hands to bin."), 1)
    H.ok(bin.icon:IsDesaturated(), "greyed while there is nothing to bin")
    M.Hover(bin)
    H.contains(table.concat(M.env.GameTooltip.__lines, "\n"), "Your Perfect streak ends.", "the tooltip says it")
    M.Hover(bin, false)
    -- two steps done: binned at once, and the notice says the streak ends
    ticket(M, 3, 1)
    M.Advance(0.7)
    H.ok(not bin.icon:IsDesaturated())
    bin:Click()
    H.eq(last(M).payload, "41,3,26")
    H.send(M, "CAFEV", { { 41, 3, 26, "B", "", "", "", "", 1 } })
    H.eq(errorsShown(M, "Binned: your Perfect streak ends"), 1)
    -- three done: the question names it too
    ticket(M, 4, 1)
    M.Advance(0.7)
    bin:Click()
    H.contains(M.env.BleakholdCafeConfirm.text:GetText(), "your Perfect streak ends")
end)

test("cafe bar: Take Order waits while Serve runs (a take would cancel the cast)", function(M, ns)
    onShift(M, "V")
    H.send(M, "CAFQ", FX.examples(M).CAFQ)
    H.send(M, "CAFT", { { 41, 1209, 103, "P", "Brenna", 57000, 60000, 5, 1, "",
        { { 1, "P" }, { 3, "P" }, { 6, "P" }, { 16, "P" }, { 25, "N" } }, 2100 } })
    M.Advance(0.7)
    M.env.BleakholdCafeStep2:Click()
    H.eq(last(M).payload, "41,5,25")
    H.send(M, "CAFEV", { { 41, 5, 25, "S", 1000, "", "", "", 5 } })
    M.Advance(0.7)
    local take = M.env.BleakholdCafeStep1
    H.ok(not take.isNext and take.icon:IsDesaturated(), "Take Order greyed while Serve runs")
    local n = H.countIntents(M, "CTAKE")
    take:Click()
    H.eq(H.countIntents(M, "CTAKE"), n, "no CTAKE")
    H.ok(errorsShown(M, "A step is running.") >= 1, "said instead")
end)

test("cafe bar: mounted or outside the café the keys are the action bar's until the warning ends", function(M, ns)
    onShift(M, "G")
    ticket(M, 1, 0)
    M.Advance(0.3)
    H.eq(M.OverrideButton("1"), "BleakholdCafeStep1")
    -- flag 64: mounted, shapeshifted, stealthed or invisible; the shift ends in warnSec unless undone
    cafst(M, "G", true, { [18] = 2 + 64, [19] = 10 })
    M.Advance(0.3)
    H.eq(M.OverrideAction("1"), nil, "key 1 is the action bar's again (the mount, the form, a vehicle's keys)")
    local n = H.countIntents(M, "CSTEP")
    M.env.BleakholdCafeStep1:Click()
    H.eq(H.countIntents(M, "CSTEP"), n, "no step the server would refuse (cafe_mounted)")
    H.eq(errorsShown(M, "Dismount and show yourself first."), 1)
    H.eq(M.env.BleakholdCafeBar.hint:GetText(), "Dismount and show yourself")
    cafst(M, "G", true, { [18] = 2 })
    M.Advance(0.3)
    H.eq(M.OverrideButton("1"), "BleakholdCafeStep1", "bound again once the warning is over")
    -- flag 8: outside the café
    cafst(M, nil, true, { [18] = 2 + 8, [19] = 20 })
    M.Advance(0.3)
    H.eq(M.OverrideAction("1"), nil, "outside the café: free too")
    cafst(M, nil, true, { [18] = 2 })
    M.Advance(0.3)
    H.eq(M.OverrideButton("1"), "BleakholdCafeStep1")
end)

test("cafe bar: with a ticket to make, Take Order glows dim and steady and the hint names the next step", function(M, ns)
    onShift(M, "V")
    H.send(M, "CAFQ", FX.examples(M).CAFQ)
    ticket(M, 1, 0)
    M.Advance(0.3)
    local take = M.env.BleakholdCafeStep1
    H.ok(not take.isNext and not take.nextTag:IsShown(), "no Next tag on Take Order")
    H.ok(take.softNext and take.glow:IsShown(), "a dim, steady glow: another order can be taken")
    H.eq(take.glow:GetAlpha(), ns.Cafe.Bar.SOFT_GLOW, "steady, not pulsing")
    H.eq(M.env.BleakholdCafeBar.hint:GetText(), "Walk to the Grinder", "the one next step")
    -- no ticket: Take Order is the next thing
    H.send(M, "CAFT", { { 0 } })
    M.Advance(0.3)
    H.ok(take.isNext and take.nextTag:IsShown(), "Take Order is next")
end)
