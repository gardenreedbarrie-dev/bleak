-- Bleakhold: the café's barista bar, its timing bar and the key overrides (docs/BleakholdProtocol.md section 21).
-- The server decides the station the barista is at (CAFST station), every step, timer and grade; the bar only shows
-- what each key does there and sends the press: CTAKE at the counter, CSTEP elsewhere, CREL to release a timed step
-- (a priority send in the frame of the key press, Comm.PRIORITY). The look is the stock action bar's:
--   bar        a tooltip panel (UI.Box) with the station in gold and a hint on the right; eight named action slots
--              (BleakholdCafeStep1..8: UI-Quickslot2, ButtonHilight-Square, UI-Quickslot-Depress, the hotkey top right
--              in grey ARIALN, the action's name under the slot); the next step's slot glows (UI-ActionButton-Border,
--              gold, pulsing), a slot of no use now is greyed as the stock bars grey an unusable action, a wrong press
--              flashes UI-QuickslotRed, a running step lights CheckButtonHilight (above a tap's cooldown swipe) and
--              the hint names it with the seconds left
--   timing     the cast bar (UI.TimerBar) above the café bar while a timed step runs: the fill (a darker amber than the
--              cast bar's, so the zone stands out of it) and its spark move from the step's CAFEV S; the gold zone
--              (UI-StatusBar in bright gold with light top and bottom edges, between 2 px brackets and the word Gold),
--              the Good band either side of it in the stock green; on D the stock cast bar's flash and the grade, on I
--              red "Interrupted"
--   keys       SetOverrideBindingClick on keys 1-8 (option cafeKeys) while on shift, never in combat: combat ends the
--              shift (the server's rule) and gives the action bar back; only a fresh CAFST with onShift 1 binds again.
--              While CAFST warns that the shift will end (flag 8 outside the café, 64 mounted or in a form) the keys
--              are the action bar's too, so the player can undo it
--   release    a timed step's key releases it wherever the barista faces (the server keeps it running on a turn)
-- The stock player cast bar shows each step too: the server casts the step spells (100901-100926).
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S
local Cafe = ns.Cafe

local floor, max, min = math.floor, math.max, math.min
local sin, pi = math.sin, math.pi
local strformat = string.format

local Bar = {}
Cafe.Bar = Bar

Bar.W, Bar.H = 440, 108
Bar.SLOTS = 8
Bar.SLOT = 36
Bar.PITCH = 52
Bar.LEFT = 14
Bar.SLOT_TOP = -40
Bar.NAME_W = Bar.PITCH - 8  -- an action's name under its slot: 8 px clear of the next one's
Bar.NAME_H = 22             -- up to two lines of ARIALN 10 (2 px apart), centred
Bar.TIMER_W = 340
Bar.RUN_COLOR = { 0.75, 0.45, 0 }   -- the timer's fill while it runs: darker than the gold zone over it
Bar.GOOD_COLOR = { 0.1, 1, 0.1, 0.42 } -- the Good band (the stock green)
Bar.FLASH = 0.3            -- s of the red flash on a wrong press
Bar.RESULT = 0.6           -- s the timing bar shows the grade
Bar.PULSE = 1.2            -- s of one pulse of the next slot's glow
Bar.SOFT_GLOW = 0.25       -- the steady glow of a slot that may come next but is not the ticket's next step
Bar.STALE = 1.5            -- s after a step's end (durMs) its S stops counting as running (a lost D)
-- short station names for the slots away from the stations (48 px under a slot)
Bar.SHORT = Cafe.SHORT_STATION
Bar.QUICKSLOT_RED = "Interface\\Buttons\\UI-QuickslotRed"
Bar.GLOW = "Interface\\Buttons\\UI-ActionButton-Border"
Bar.DEPRESS = "Interface\\Buttons\\UI-Quickslot-Depress"
Bar.SPARK = "Interface\\CastingBar\\UI-CastingBar-Spark"
Bar.CAST_FLASH = "Interface\\CastingBar\\UI-CastingBar-Flash"

------------------------------------------------------------------------------------------------------
-- The step that runs now (CAFEV S, not yet ended by D, I, X, W or B)
------------------------------------------------------------------------------------------------------
function Bar.StepRunning()
    local cs = S.cafeStep
    if not cs or cs.event ~= "S" then
        return nil
    end
    local dur = (cs.durMs or 0) / 1000
    if GetTime() - (cs.recvAt or 0) > dur + Bar.STALE then
        return nil
    end
    return cs
end

function Bar.IsTimed(cs)
    if not cs then
        return false
    end
    if cs.goldLoMs and cs.goldHiMs then
        return true
    end
    local a = Cafe.Action(cs.actionId)
    return a and a.timed or false
end

-- From-memory mode (CAFST flag 2 and the option): the checklist hides what comes next, and so does the bar.
function Cafe.MemoryMode()
    local st = S.cafeState
    return st and bit.band(st.flags or 0, 2) ~= 0 and Cafe.Option("cafeMemory") and true or false
end

-- The action a ticket needs next.
function Bar.NextAction(t)
    local r = t and Cafe.Recipe(t.recipeId)
    local id = r and r.steps[t.nextStep]
    return id and Cafe.Action(id) or nil
end

-- The key that releases a running timed step: its action's slot at its station (DEF G key), wherever the barista
-- stands or faces now.
function Bar.ReleaseKey(cs)
    local a = cs and Cafe.Action(cs.actionId)
    return a and a.key and Cafe.SlotKey(a.key) or "?"
end

-- Bin (action 26) throws the drink in hand away; the server also ends the Perfect streak on it (and on a ruin), and
-- takes it at step 1 too, where nothing has been done yet: the bar offers it only once a step is done.
Bar.BIN_TIP = "Throw the drink away and start it again from step 1. Your Perfect streak ends."
Bar.BIN_EMPTY = "Nothing in your hands to bin."
function Bar.CanBin(t)
    return t ~= nil and (t.nextStep or 1) > 1
end

------------------------------------------------------------------------------------------------------
-- The bar
------------------------------------------------------------------------------------------------------
local f = CreateFrame("Frame", "BleakholdCafeBar", UIParent)
f:SetSize(Bar.W, Bar.H)
f:SetFrameStrata("MEDIUM")
UI.Backdrop(f, C.panel, C.border, nil, "panel")
f:Hide()
Bar.frame = f

f.title = UI.Heading(f, "", 14)
f.title:SetPoint("TOPLEFT", f, "TOPLEFT", 14, -10)
UI.OneLine(f.title, 170)
f.hint = UI.Text(f, 11, C.text, "body", "RIGHT")
f.hint:SetPoint("TOPRIGHT", f, "TOPRIGHT", -14, -11)
UI.OneLine(f.hint, 214)

Bar.buttons = {}

local function hideTip()
    if GameTooltip then
        GameTooltip:Hide()
    end
end

for i = 1, Bar.SLOTS do
    local b = CreateFrame("Button", "BleakholdCafeStep" .. i, f)
    b:SetSize(Bar.SLOT, Bar.SLOT)
    b:SetPoint("TOPLEFT", f, "TOPLEFT", Bar.LEFT + (i - 1) * Bar.PITCH, Bar.SLOT_TOP)
    -- a key fires on key down, as the stock action buttons do
    b:RegisterForClicks("LeftButtonDown")
    UI.SlotArt(b, Bar.SLOT, true)
    b.icon:SetPoint("CENTER", b, "CENTER", 0, 0)
    b:SetPushedTexture(Bar.DEPRESS)
    b:GetPushedTexture():SetAllPoints(b.icon)
    b.cd = CreateFrame("Cooldown", nil, b)
    b.cd:SetAllPoints(b.icon)
    -- above the cooldown's swipe: the glow, the red flash, the hotkey and the Next tag
    b.over = CreateFrame("Frame", nil, b)
    b.over:SetAllPoints(b)
    b.over:SetFrameLevel(b:GetFrameLevel() + 3)
    b.glow = b.over:CreateTexture(nil, "OVERLAY")
    b.glow:SetTexture(Bar.GLOW)
    b.glow:SetBlendMode("ADD")
    b.glow:SetSize(Bar.SLOT * 62 / 36, Bar.SLOT * 62 / 36)
    b.glow:SetPoint("CENTER", b.icon, "CENTER", 0, 0)
    b.glow:SetVertexColor(1, 0.82, 0)
    b.glow:Hide()
    b.red = b.over:CreateTexture(nil, "ARTWORK")
    b.red:SetTexture(Bar.QUICKSLOT_RED)
    b.red:SetBlendMode("ADD")
    b.red:SetSize(Bar.SLOT * 64 / 37, Bar.SLOT * 64 / 37)
    b.red:SetPoint("CENTER", b.icon, "CENTER", 0, -1)
    b.red:Hide()
    -- CheckButtonHilight (a running step, a station named away from the stations) above the cooldown's swipe, so a
    -- running tap reads lit through it: b:SetSlotChecked drives b.slotCheck, and SlotArt's own (under the swipe) stays
    -- hidden
    b.slotCheck:Hide()
    b.slotCheck = b.over:CreateTexture(nil, "ARTWORK")
    b.slotCheck:SetTexture(UI.STOCK.slotCheck)
    b.slotCheck:SetBlendMode("ADD")
    b.slotCheck:SetAllPoints(b.icon)
    b.slotCheck:Hide()
    b.hotkey = b.over:CreateFontString(nil, "OVERLAY")
    b.hotkey:SetFont(UI.FONT_NARROW, 12, "OUTLINE")
    b.hotkey:SetTextColor(0.6, 0.6, 0.6)
    b.hotkey:SetJustifyH("RIGHT")
    b.hotkey:SetPoint("TOPRIGHT", b, "TOPRIGHT", -1, -2)
    b.nextTag = UI.Text(b.over, 10, C.gold, "body", "CENTER")
    b.nextTag:SetPoint("BOTTOM", b, "TOP", 0, 3)
    b.nextTag:SetText("Next")
    b.nextTag:Hide()
    -- (ARIALN, the stock bars' narrow face) the whole name, in two centred lines when one is too short
    b.name = UI.Text(f, 10, C.text, "narrow", "CENTER")
    b.name:SetPoint("TOP", b, "BOTTOM", 0, -3)
    b.name:SetWidth(Bar.NAME_W)
    b.name:SetHeight(Bar.NAME_H)
    b.name:SetJustifyV("TOP")
    b.name:SetNonSpaceWrap(false)
    b.slot = i
    b:SetScript("OnClick", function()
        Cafe.Press(i)
    end)
    b:SetScript("OnEnter", function(self)
        if self.tip then
            UI.ShowTooltip(self, self.tip)
        end
    end)
    b:SetScript("OnLeave", hideTip)
    Bar.buttons[i] = b
end

-- what each slot does now: { kind = "station" | "take" | "serve" | "bin" | "action", station, action }
Bar.slots = {}

local function setSlot(b, d)
    Bar.slots[b.slot] = d
    if not d then
        b.icon:Hide()
        b.name:SetText("")
        b.tip = nil
        return
    end
    b.icon:SetTexture(UI.IconPath(d.icon) or UI.STOCK.question)
    b.icon:Show()
    UI.SetText(b.name, d.name or "")
    b.tip = d.tip
end

-- The slot's state: usable (full colour) or not (the stock unusable grey), the next step (glow, Next), running.
-- a danger pause (CAFE open 2): no slot is "next" while every press would be refused (Bar.Refresh sets it)
local pausedNow = false

-- soft: a dim, steady glow without the Next tag (Take Order while the active ticket's next step is elsewhere)
local function paintSlot(b, usable, isNext, checked, soft)
    isNext = isNext and not pausedNow
    soft = soft and not isNext and not pausedNow and true or false
    if usable then
        b.icon:SetVertexColor(1, 1, 1)
        b.icon:SetDesaturated(false)
    else
        b.icon:SetVertexColor(0.4, 0.4, 0.4)
        b.icon:SetDesaturated(true)
    end
    b.isNext = isNext and true or false
    b.softNext = soft
    if isNext then
        b.glow:Show()
        b.nextTag:Show()
    elseif soft then
        b.glow:SetAlpha(Bar.SOFT_GLOW)
        b.glow:Show()
        b.nextTag:Hide()
    else
        b.glow:Hide()
        b.nextTag:Hide()
    end
    b:SetSlotChecked(checked or (b.highlightUntil and GetTime() < b.highlightUntil) or false)
end

local relSent        -- the step (S.cafeStep) a release was sent for: one release per step

local function actionTip(a, key)
    local lines = { U.Safe(a.name) }
    lines[#lines + 1] = { Cafe.StationName(a.station), C.dim }
    if a.timed then
        local g = a.gold or { 0, 0 }
        lines[#lines + 1] = { "Timed: press again inside the gold (about " .. floor(g[1] / 10) .. "-" .. floor(g[2] / 10)
            .. "% of the bar).", C.mid, true }
    else
        lines[#lines + 1] = { "Takes " .. strformat("%.1f", (a.durMs or 0) / 1000) .. " s.", C.mid }
    end
    lines[#lines + 1] = { "Key: " .. key, C.mute }
    return lines
end

-- The hint while a tap step runs: its name and the seconds left ("Grind Beans... 0.9 s"; no seconds once they are up
-- and the D is still on its way).
function Bar.RunText(cs)
    local a = Cafe.Action(cs.actionId)
    local left = (cs.durMs or 0) / 1000 - (GetTime() - (cs.recvAt or 0))
    local name = (a and a.name or "Working") .. "..."
    if left > 0.05 then
        return name .. " " .. strformat("%.1f", left) .. " s"
    end
    return name
end

-- A running tap: its slot's cooldown swipe, from its CAFEV S (once per step).
local function swipe(b, cs)
    if b.cdFor ~= cs then
        b.cdFor = cs
        b.cd:SetCooldown(cs.recvAt, (cs.durMs or 0) / 1000)
    end
end

Bar.PAUSED_TEXT = "Paused: danger nearby"
Bar.BINNED_TEXT = "Binned: your Perfect streak ends"
Bar.MOUNTED_HINT = "Dismount and show yourself"

function Bar.Refresh()
    Bar.runHint = nil
    local on = Cafe.Enabled() and (Cafe.OnShift() or Cafe.editing)
    if not on then
        f:Hide()
        Bar.timing:Hide()
        return
    end
    f:Show()
    local st = S.cafeState or {}
    local station = st.station
    pausedNow = Cafe.Paused(st.cafeId)
    local t = Cafe.ActiveTicket()
    local nextAct = Bar.NextAction(t)
    local memory = Cafe.MemoryMode()
    local running = Bar.StepRunning()
    -- a timed step runs on while the barista turns away from its station (the server ends it only on walking off or
    -- moving): its station's slots and its release stay on the bar until its D or I
    local runAct = running and Bar.IsTimed(running) and Cafe.Action(running.actionId) or nil
    if runAct and runAct.station and station ~= runAct.station then
        station = runAct.station
    end
    local keys = {}
    for i = 1, Bar.SLOTS do
        keys[i] = Cafe.SlotKey(i)
        Bar.buttons[i].hotkey:SetText(keys[i])
    end
    local hint, hintColor = "", C.text
    if not station then
        f.title:SetText("Away from the stations")
        local want = (t and nextAct and nextAct.station) or "V"
        for i = 1, Bar.SLOTS do
            local b = Bar.buttons[i]
            local letter = i <= 7 and Cafe.STATION_ORDER[i] or nil
            if letter then
                setSlot(b, { kind = "station", station = letter, icon = Cafe.Icon("station", letter),
                    name = Bar.SHORT[letter] or Cafe.StationName(letter),
                    tip = { Cafe.StationName(letter), { "Walk to it to use its steps.", C.mid } } })
                paintSlot(b, true, letter == want and not memory, false)
            else
                setSlot(b, nil)
                paintSlot(b, false, false, false)
            end
        end
        -- from memory the next station is the challenge: a ticket's way stays unnamed (no ticket: the counter, to take one)
        if memory and t then
            hint = "Walk to a station"
        else
            hint = "Walk to the " .. Cafe.StationName(want)
        end
        hintColor = C.dim
    elseif station == "V" then
        f.title:SetText(Cafe.StationName("V"))
        local q = S.cafeQueue
        local free = false
        for _, r in ipairs(q and q.rows or {}) do
            if r.state == "W" and (r.needLevel or 0) == 0 then
                free = true
            end
        end
        local roomForMore = #Cafe.Tickets() < (st.maxTickets or 1)
        local serveNext = nextAct and nextAct.id == 25
        -- another order can be taken; it is the next thing to do only without a ticket (with one, the ticket's next
        -- step is: Take Order then glows dim and steady, with no Next tag, while the hint names that step)
        local takeAny = free and roomForMore and not (t and t.inHand)
        local takeNext = takeAny and not t
        setSlot(Bar.buttons[1], { kind = "take", icon = Cafe.Icon("action", 24), name = Cafe.ActionName(24),
            tip = { Cafe.ActionName(24), { "Take the next order you can make, or the one chosen in the queue.", C.mid, true },
                { "Key: " .. keys[1], C.mute } } })
        paintSlot(Bar.buttons[1], roomForMore and not running, takeNext and not running, false, takeAny and not running)
        local fam = t and Cafe.Icon("family", Cafe.Family(t.recipeId)) or Cafe.Icon("family", "C")
        setSlot(Bar.buttons[2], { kind = "serve", icon = fam, name = Cafe.ActionName(25),
            tip = { Cafe.ActionName(25), { "Hand the finished drink over: its last step.", C.mid, true },
                { "Key: " .. keys[2], C.mute } } })
        local serving = running and running.actionId == 25
        paintSlot(Bar.buttons[2], t ~= nil, serveNext and not memory and not running, serving)
        if serving and not Bar.IsTimed(running) then
            swipe(Bar.buttons[2], running)
        end
        setSlot(Bar.buttons[3], { kind = "bin", icon = Cafe.Icon("action", 26), name = Cafe.ActionName(26),
            tip = { Cafe.ActionName(26), { Bar.BIN_TIP, C.mid, true }, { "Key: " .. keys[3], C.mute } } })
        paintSlot(Bar.buttons[3], Bar.CanBin(t), false, false)
        for i = 4, Bar.SLOTS do
            setSlot(Bar.buttons[i], nil)
            paintSlot(Bar.buttons[i], false, false, false)
        end
        if running and not Bar.IsTimed(running) then
            hint = Bar.RunText(running)
            Bar.runHint = running
        elseif not t then
            hint = "Take an order [" .. keys[1] .. "]"
        elseif serveNext and not memory then
            hint = "Next: " .. Cafe.ActionName(25) .. " [" .. keys[2] .. "]"
        elseif nextAct and not memory then
            hint = "Walk to the " .. Cafe.StationName(nextAct.station)
            hintColor = C.dim
        elseif takeAny then
            hint = "Take another order [" .. keys[1] .. "]"
        end
    else
        f.title:SetText(Cafe.StationName(station))
        local actions = Cafe.ActionsAt(station)
        for i = 1, Bar.SLOTS do
            local b = Bar.buttons[i]
            local a = actions[i]
            if a then
                local icon = a.id == 25 and (t and Cafe.Icon("family", Cafe.Family(t.recipeId)) or Cafe.Icon("family", "C"))
                    or Cafe.Icon("action", a.id)
                setSlot(b, { kind = "action", action = a, icon = icon, name = a.name, tip = actionTip(a, keys[i]) })
                -- a running step lights its slot (CheckButtonHilight), a tap's swipe runs under that
                local isRunning = running and running.actionId == a.id
                paintSlot(b, t ~= nil, nextAct and nextAct.id == a.id and not memory and not running, isRunning)
                if isRunning and not Bar.IsTimed(running) then
                    swipe(b, running)
                end
            else
                setSlot(b, nil)
                paintSlot(b, false, false, false)
            end
        end
        if runAct then
            hint = relSent == running and "Released" or ("Release inside the gold [" .. Bar.ReleaseKey(running) .. "]")
        elseif running then
            -- a tap runs: its name and the seconds left (the next step is still this one until its D)
            hint = Bar.RunText(running)
            Bar.runHint = running
        elseif not t then
            hint = "Walk to the " .. Cafe.StationName("V")
            hintColor = C.dim
        elseif nextAct and not memory then
            if nextAct.station == station then
                local key
                for i, a in pairs(actions) do
                    if a.id == nextAct.id then
                        key = keys[i]
                    end
                end
                hint = "Next: " .. nextAct.name .. " [" .. (key or "?") .. "]"
            else
                hint = "Walk to the " .. Cafe.StationName(nextAct.station)
                hintColor = C.dim
            end
        end
    end
    -- at a station's work spot, not facing it (flag 32); a timed step running there keeps its release hint
    if bit.band(st.flags or 0, 32) ~= 0 and st.nearStation and not runAct then
        hint = "Turn to face the " .. Cafe.StationName(st.nearStation)
        hintColor = C.text
        Bar.runHint = nil
    end
    -- mounted, shapeshifted, stealthed or invisible (flag 64): every step is refused and the keys are the action
    -- bar's until it ends (the strip counts the warning down)
    if bit.band(st.flags or 0, 64) ~= 0 then
        hint, hintColor = Bar.MOUNTED_HINT, C.red
        Bar.runHint = nil
    end
    -- a danger pause refuses every step (ERR cafe_paused): the bar says so where the player looks
    if pausedNow then
        hint, hintColor = Bar.PAUSED_TEXT, C.red
        Bar.runHint = nil
    end
    f.hint:SetText(hint)
    UI.SetColor(f.hint, hintColor)
    Bar.UpdateTiming()
end

-- Away from the stations, a press names the station and lights its slot for a moment.
function Bar.Highlight(slot)
    local b = Bar.buttons[slot]
    if b then
        b.highlightUntil = GetTime() + 1.5
        b:SetSlotChecked(true)
    end
end

function Bar.Flash(slot)
    local b = Bar.buttons[slot]
    if b then
        b.flashUntil = GetTime() + Bar.FLASH
        b.red:Show()
    end
end

-- The glow pulses (0.35 to 0.8 over 1.2 s; steady with motion off), flashes and highlights run out, a running tap's
-- seconds count down in the hint, a step that ran out of time stops counting as running.
local acc, hintAcc = 0, 0
f:SetScript("OnUpdate", function(self, elapsed)
    local now = GetTime()
    local a = Cafe.Motion() and (0.35 + 0.45 * (0.5 + 0.5 * sin(now * 2 * pi / Bar.PULSE))) or 0.8
    for _, b in ipairs(Bar.buttons) do
        b.glow:SetAlpha(b.softNext and Bar.SOFT_GLOW or a)
        if b.flashUntil and now >= b.flashUntil then
            b.flashUntil = nil
            b.red:Hide()
        end
        if b.highlightUntil and now >= b.highlightUntil then
            b.highlightUntil = nil
            b:SetSlotChecked(false)
        end
    end
    hintAcc = hintAcc + (elapsed or 0)
    if Bar.runHint and hintAcc >= 0.1 then
        hintAcc = 0
        if Bar.StepRunning() == Bar.runHint then
            f.hint:SetText(Bar.RunText(Bar.runHint))
        end
    end
    acc = acc + (elapsed or 0)
    if acc >= 0.25 then
        acc = 0
        local cs = S.cafeStep
        if cs and cs.event == "S" and not Bar.StepRunning() and Bar.ranFor ~= cs then
            Bar.ranFor = cs
            Bar.Refresh()
        end
    end
end)

------------------------------------------------------------------------------------------------------
-- A press: the slot's job at this station (Cafe.Press is the bar's API; the buttons and the keys call it)
------------------------------------------------------------------------------------------------------
Bar.MOUNTED_TEXT = "Dismount and show yourself first."
Bar.BUSY_TEXT = "A step is running."

local function busy()
    Cafe.Notice(ns.ErrorText({ code = "cafe_busy", text = Bar.BUSY_TEXT }))
    return false
end

function Cafe.Press(slot)
    if not Cafe.OnShift() then
        return false
    end
    local st = S.cafeState
    -- mounted, shapeshifted, stealthed or invisible (CAFST flag 64): the server refuses every step (cafe_mounted); the
    -- keys are the action bar's again meanwhile, so only a click on the bar comes here
    if bit.band(st.flags or 0, 64) ~= 0 then
        Cafe.Notice(Bar.MOUNTED_TEXT)
        return false
    end
    local running = Bar.StepRunning()
    -- a running timed step's release, before anything about the station: the server keeps the step running while the
    -- barista turns (CAFST may already name no station), and grades a missing release Off
    if running and Bar.IsTimed(running) then
        local ra = Cafe.Action(running.actionId)
        if ra and ra.key == slot then
            if relSent == running then
                return false
            end
            -- the time since its CAFEV S arrived, measured here (the server takes it within its lag)
            local ms = U.Clamp(floor((GetTime() - running.recvAt) * 1000), 0, 60000)
            if Cafe.Send("CREL", running.ticketId, running.stepIndex, ms) then
                relSent = running
                Bar.Refresh()
                return true
            end
            return false
        end
    end
    local station = st.station
    if not station then
        local letter = slot <= 7 and Cafe.STATION_ORDER[slot] or nil
        if letter then
            Cafe.Notice("Walk to the " .. Cafe.StationName(letter) .. ".")
            Bar.Highlight(slot)
        end
        return false
    end
    -- paused: the server refuses every step (cafe_paused); say it here instead of asking
    if Cafe.Paused(st.cafeId) then
        Cafe.Notice(ns.ErrorText({ code = "cafe_paused", text = "Danger nearby: the caf\195\169 has paused." }))
        return false
    end
    if station == "V" then
        if slot ~= 1 and slot ~= 2 and slot ~= 3 then
            return false
        end
        -- a take would cancel the running Serve (the server interrupts a cast to take an order)
        if running then
            return busy()
        end
        if slot == 1 then
            return Cafe.Send("CTAKE", Cafe.SelectedOrder() or 0)
        end
        local t = Cafe.ActiveTicket()
        if not t then
            Cafe.Notice("No ticket: take an order first.")
            return false
        end
        if slot == 2 then
            return Cafe.Send("CSTEP", t.ticketId, t.nextStep, 25)
        end
        if not Bar.CanBin(t) then
            Cafe.Notice(Bar.BIN_EMPTY)
            return false
        end
        local done = (t.nextStep or 1) - 1
        if done >= 3 then
            local ticketId = t.ticketId
            Cafe.Confirm("bin", "Bin this drink? Its " .. done .. " finished steps are lost, and your Perfect streak "
                .. "ends.", function()
                -- the shift or the ticket may be gone by now; bin the ticket as it stands, not as it stood
                local now = Cafe.OnShift() and Cafe.Ticket(ticketId)
                if now and Bar.CanBin(now) then
                    Cafe.Send("CSTEP", now.ticketId, now.nextStep, 26)
                end
            end, "Bin")
            return false
        end
        return Cafe.Send("CSTEP", t.ticketId, t.nextStep, 26)
    end
    local a = Cafe.ActionsAt(station)[slot]
    if not a then
        return false
    end
    if running then
        -- (its release went out above; once released, the other keys stay quiet until its D)
        if relSent == running then
            return false
        end
        return busy()
    end
    local t = Cafe.ActiveTicket()
    if not t then
        Cafe.Notice("No ticket: take an order at the " .. Cafe.StationName("V") .. " first.")
        return false
    end
    return Cafe.Send("CSTEP", t.ticketId, t.nextStep, a.id)
end

------------------------------------------------------------------------------------------------------
-- The timing bar (BleakholdCafeTiming): the stock cast bar above the café bar while a timed step runs
------------------------------------------------------------------------------------------------------
local tm = CreateFrame("Frame", "BleakholdCafeTiming", f)
tm:SetSize(Bar.TIMER_W + 2 * UI.TIMER_OUT, 66)
tm:SetPoint("BOTTOM", f, "TOP", 0, 0)
tm:Hide()
Bar.timing = tm

local tb = UI.TimerBar(tm, Bar.TIMER_W, UI.BAR_GOLD)
tb:SetPoint("BOTTOM", tm, "BOTTOM", 0, 24)
tb.text:SetText("")
tm.bar = tb
-- layers (see the top of Widgets.lua): the fill; the zones and brackets on a child frame; the border; the spark; the
-- flash. The texts sit above the bar and the word Gold under it, clear of the zones.
tb.zones = CreateFrame("Frame", nil, tb)
tb.zones:SetAllPoints(tb)
tb.zones:SetFrameLevel(tb:GetFrameLevel() + 1)
tb.border:SetFrameLevel(tb:GetFrameLevel() + 2)
-- the Good band, either side of the gold (never under it): the stock green at 0.42, on the fill and off it
tb.good = {}
for i = 1, 2 do
    local t = tb.zones:CreateTexture(nil, "BACKGROUND")
    t:SetTexture(UI.STOCK.white)
    t:SetVertexColor(unpack(Bar.GOOD_COLOR))
    t:SetHeight(UI.TIMER_H)
    tb.good[i] = t
end
-- the gold zone: bright gold added over the darker fill (it lights up as the fill crosses it), its light top and bottom
-- edges in OVERLAY so it reads on the empty track too
tb.gold = tb.zones:CreateTexture(nil, "BORDER")
tb.gold:SetTexture(UI.STOCK.statusBar)
tb.gold:SetBlendMode("ADD")
tb.gold:SetVertexColor(1, 0.9, 0.3, 0.75)
tb.gold:SetHeight(UI.TIMER_H)
tb.goldEdges = {}
for i = 1, 2 do
    local t = tb.zones:CreateTexture(nil, "OVERLAY")
    t:SetTexture(UI.STOCK.white)
    t:SetVertexColor(1, 0.94, 0.6, 0.95)
    t:SetHeight(1)
    t:SetPoint("LEFT", tb.gold, i == 1 and "TOPLEFT" or "BOTTOMLEFT", 0, i == 1 and -0.5 or 0.5)
    t:SetPoint("RIGHT", tb.gold, i == 1 and "TOPRIGHT" or "BOTTOMRIGHT", 0, i == 1 and -0.5 or 0.5)
    tb.goldEdges[i] = t
end
-- the brackets: 2 px of gold on a black line, taller than the bar so they read on the fill and off it
tb.brackets, tb.bracketShadows = {}, {}
for i = 1, 2 do
    local sh = tb.zones:CreateTexture(nil, "ARTWORK")
    sh:SetTexture(UI.STOCK.white)
    sh:SetVertexColor(0, 0, 0, 0.85)
    sh:SetSize(4, UI.TIMER_H + 10)
    tb.bracketShadows[i] = sh
    local t = tb.zones:CreateTexture(nil, "OVERLAY")
    t:SetTexture(UI.STOCK.white)
    t:SetVertexColor(1, 0.82, 0, 1)
    t:SetSize(2, UI.TIMER_H + 8)
    t:SetPoint("CENTER", sh, "CENTER", 0, 0)
    tb.brackets[i] = t
end
tb.goldLabel = UI.Text(tb.zones, 10, C.gold, "body", "CENTER")
tb.goldLabel:SetText("Gold")
tb.sparkFrame = CreateFrame("Frame", nil, tb)
tb.sparkFrame:SetAllPoints(tb)
tb.sparkFrame:SetFrameLevel(tb:GetFrameLevel() + 3)
tb.spark = tb.sparkFrame:CreateTexture(nil, "OVERLAY")
tb.spark:SetTexture(Bar.SPARK)
tb.spark:SetBlendMode("ADD")
tb.spark:SetSize(32, 32)
tb.left = UI.Text(tb.sparkFrame, 12, C.text, "body", "LEFT")
tb.left:SetPoint("BOTTOMLEFT", tb, "TOPLEFT", 2, 13)
UI.OneLine(tb.left, Bar.TIMER_W * 0.6)
tb.right = UI.Text(tb.sparkFrame, 12, C.text, "body", "RIGHT")
tb.right:SetPoint("BOTTOMRIGHT", tb, "TOPRIGHT", -2, 13)
UI.OneLine(tb.right, Bar.TIMER_W * 0.38)
-- the stock cast bar's flash (its border's shape, in ADD), sliced like the border
tb.flashFrame = CreateFrame("Frame", nil, tb)
tb.flashFrame:SetPoint("TOPLEFT", tb.border, "TOPLEFT", 0, 0)
tb.flashFrame:SetPoint("BOTTOMRIGHT", tb.border, "BOTTOMRIGHT", 0, 0)
tb.flashFrame:SetFrameLevel(tb:GetFrameLevel() + 4)
tb.flash = {}
local FLASH_U = { 0, 0.15625, 0.84375, 1 }
for i = 1, 3 do
    local t = tb.flashFrame:CreateTexture(nil, "OVERLAY")
    t:SetTexture(Bar.CAST_FLASH)
    t:SetBlendMode("ADD")
    t:SetTexCoord(FLASH_U[i], FLASH_U[i + 1], 0.25, 0.75)
    tb.flash[i] = t
end
tb.flash[1]:SetWidth(40)
tb.flash[1]:SetPoint("TOPLEFT", tb.flashFrame, "TOPLEFT", 0, 0)
tb.flash[1]:SetPoint("BOTTOMLEFT", tb.flashFrame, "BOTTOMLEFT", 0, 0)
tb.flash[3]:SetWidth(40)
tb.flash[3]:SetPoint("TOPRIGHT", tb.flashFrame, "TOPRIGHT", 0, 0)
tb.flash[3]:SetPoint("BOTTOMRIGHT", tb.flashFrame, "BOTTOMRIGHT", 0, 0)
tb.flash[2]:SetPoint("TOPLEFT", tb.flash[1], "TOPRIGHT", 0, 0)
tb.flash[2]:SetPoint("BOTTOMRIGHT", tb.flash[3], "BOTTOMLEFT", 0, 0)
tb.flashFrame:Hide()

-- the run being shown: { step, phase = "run" | "done" | "stop", untilAt }
Bar.run = nil

local function zoneX(ms, dur)
    return Bar.TIMER_W * U.Clamp((ms or 0) / dur, 0, 1)
end

local function layoutZones(cs, dur)
    local lo, hi = cs.goldLoMs, cs.goldHiMs
    if not (lo and hi) then
        local a = Cafe.Action(cs.actionId)
        local g = a and a.gold or { 700, 850 }
        lo, hi = dur * g[1] / 1000, dur * g[2] / 1000
    end
    if hi < lo then
        lo, hi = hi, lo
    end
    local band = dur * 0.1
    local x1, x2 = zoneX(lo, dur), zoneX(hi, dur)
    local g1, g2 = zoneX(lo - band, dur), zoneX(hi + band, dur)
    tb.gold:ClearAllPoints()
    tb.gold:SetPoint("LEFT", tb, "LEFT", x1, 0)
    tb.gold:SetWidth(max(1, x2 - x1))
    tb.good[1]:ClearAllPoints()
    tb.good[1]:SetPoint("LEFT", tb, "LEFT", g1, 0)
    tb.good[1]:SetWidth(max(1, x1 - g1))
    tb.good[2]:ClearAllPoints()
    tb.good[2]:SetPoint("LEFT", tb, "LEFT", x2, 0)
    tb.good[2]:SetWidth(max(1, g2 - x2))
    tb.bracketShadows[1]:ClearAllPoints()
    tb.bracketShadows[1]:SetPoint("CENTER", tb, "LEFT", x1, 0)
    tb.bracketShadows[2]:ClearAllPoints()
    tb.bracketShadows[2]:SetPoint("CENTER", tb, "LEFT", x2, 0)
    tb.goldLabel:ClearAllPoints()
    tb.goldLabel:SetPoint("TOP", tb, "BOTTOMLEFT", (x1 + x2) / 2, -9)
    Bar.zone = { lo = lo, hi = hi, x1 = x1, x2 = x2 }
end

local function setZonesShown(on)
    for _, r in ipairs({ tb.gold, tb.good[1], tb.good[2], tb.goldEdges[1], tb.goldEdges[2], tb.brackets[1],
        tb.brackets[2], tb.bracketShadows[1], tb.bracketShadows[2], tb.goldLabel }) do
        if on then
            r:Show()
        else
            r:Hide()
        end
    end
end

-- Start (or redraw) the bar for a running timed step.
function Bar.StartTiming(cs)
    local dur = cs.durMs or 0
    if dur <= 0 then
        local a = Cafe.Action(cs.actionId)
        dur = a and a.durMs or 0
    end
    if dur <= 0 then
        return
    end
    Bar.run = { step = cs, phase = "run", dur = dur }
    tb:SetStatusBarColor(unpack(Bar.RUN_COLOR))
    layoutZones(cs, dur)
    setZonesShown(true)
    tb.flashFrame:Hide()
    tb.spark:Show()
    tb.left:Show()
    tb.right:Show()
    tb.text:SetText("")
    tm:SetAlpha(1)
    tm:Show()
    Bar.TickTiming()
end

-- The end of the step: the grade (D) or the interruption (I), shown 0.6 s like the stock cast bar.
function Bar.EndTiming(cs)
    local run = Bar.run
    if not run or run.phase ~= "run" then
        return
    end
    run.phase = "done"
    run.untilAt = GetTime() + Bar.RESULT
    tb.spark:Hide()
    tb.left:Hide()
    tb.right:Hide()
    tb:SetValue(1)
    if cs.event == "D" then
        local g = Cafe.GRADES[cs.grade or ""] or Cafe.GRADES.O
        if cs.grade == "P" or cs.grade == "G" then
            tb:SetStatusBarColor(0, 1, 0)
        else
            tb:SetStatusBarColor(1, 0, 0)
        end
        tb.text:SetText(g[1])
        tb.flashFrame:SetAlpha(1)
        tb.flashFrame:Show()
    else
        tb:SetStatusBarColor(1, 0, 0)
        tb.text:SetText("Interrupted")
        setZonesShown(false)
    end
end

function Bar.StopTiming()
    Bar.run = nil
    tm:Hide()
end

function Bar.TickTiming()
    local run = Bar.run
    if not run then
        return
    end
    local now = GetTime()
    if run.phase == "run" then
        local cs = run.step
        local p = U.Clamp((now - cs.recvAt) * 1000 / run.dur, 0, 1)
        tb:SetValue(p)
        tb.spark:ClearAllPoints()
        tb.spark:SetPoint("CENTER", tb, "LEFT", Bar.TIMER_W * p, 0)
        Bar.progress = p
        local a = Cafe.Action(cs.actionId)
        tb.left:SetText((a and a.name or "Step") .. " " .. floor(p * 100 + 0.5) .. "%")
        tb.right:SetText(relSent == cs and "Released" or ("Release [" .. Bar.ReleaseKey(cs) .. "]"))
        if not Bar.StepRunning() then
            Bar.StopTiming()
        end
    else
        local left = (run.untilAt or now) - now
        if left <= 0 then
            Bar.StopTiming()
            return
        end
        tm:SetAlpha(U.Clamp(left / Bar.RESULT * 1.5, 0, 1))
        tb.flashFrame:SetAlpha(U.Clamp(left / Bar.RESULT, 0, 1))
    end
end

-- keep the bar in step with the state: a timed step running shows it, anything else hides it (but a grade shown)
function Bar.UpdateTiming()
    local cs = Bar.StepRunning()
    if cs and Bar.IsTimed(cs) and Cafe.OnShift() then
        if not Bar.run or Bar.run.step ~= cs then
            Bar.StartTiming(cs)
        end
    elseif Bar.run and Bar.run.phase == "run" then
        Bar.StopTiming()
    end
end

local tick = 0
tm:SetScript("OnUpdate", function(self, elapsed)
    tick = tick + (elapsed or 0)
    if tick >= 0.016 then
        tick = 0
        Bar.TickTiming()
    end
end)

------------------------------------------------------------------------------------------------------
-- Step events (CAFEV): the bar's part (the RUINED banner and its sound are CafeHud.lua's)
------------------------------------------------------------------------------------------------------
local function slotOf(actionId)
    for i, d in pairs(Bar.slots) do
        if d and d.action and d.action.id == actionId then
            return i
        end
    end
end

ns.On("CAFE_STEP", function(cs)
    if not Cafe.OnShift() then
        return
    end
    if cs.event ~= "S" then
        relSent = nil
    end
    if cs.event == "S" then
        Bar.Refresh()
        if Bar.IsTimed(cs) then
            Bar.StartTiming(cs)
        end
        return
    end
    if Bar.run and Bar.run.phase == "run" and Bar.run.step.ticketId == cs.ticketId
        and Bar.run.step.stepIndex == cs.stepIndex and (cs.event == "D" or cs.event == "I") then
        Bar.EndTiming(cs)
    elseif cs.event == "X" or cs.event == "B" then
        Bar.StopTiming()
    end
    if cs.event == "I" then
        Cafe.Notice("Interrupted", 1, 0.1, 0.1)
    elseif cs.event == "W" then
        Cafe.Notice("Not that one")
        Bar.Flash(slotOf(cs.actionId) or 0)
    elseif cs.event == "X" then
        Bar.Flash(slotOf(cs.actionId) or 0)
    elseif cs.event == "B" then
        Cafe.Notice(Bar.BINNED_TEXT)
    end
    -- a tap's swipe stops with an interrupted or ruined step
    for _, b in ipairs(Bar.buttons) do
        if b.cdFor and (cs.event == "I" or cs.event == "X") then
            b.cd:SetCooldown(0, 0)
            b.cdFor = nil
        end
    end
    Bar.Refresh()
end)

------------------------------------------------------------------------------------------------------
-- Key overrides (owner BleakholdCafeBindings, never priority: AddicatUI's keypress module yields to them)
------------------------------------------------------------------------------------------------------
local owner = CreateFrame("Frame", "BleakholdCafeBindings", UIParent)
Bar.owner = owner
local bound = false
local combatEnded = false        -- combat ended the shift here; wait for a fresh CAFST

-- CAFST flag 8 (outside the café) or 64 (mounted, shapeshifted, stealthed or invisible): the shift ends in warnSec
-- unless the barista comes back or shows themself. Meanwhile keys 1-8 are the action bar's again, so the mount, the
-- form, the stealth or a vehicle's keys that undo it still work; the server sends CAFST again when the flags change.
function Bar.Warned()
    local st = S.cafeState
    return (st and bit.band(st.flags or 0, 8 + 64) ~= 0) and true or false
end

local function bind()
    if bound or combatEnded or not Cafe.OnShift() or InCombatLockdown() or Bar.Warned() then
        return
    end
    for i, key in ipairs(Cafe.Keys()) do
        SetOverrideBindingClick(owner, false, key, "BleakholdCafeStep" .. i, "LeftButton")
    end
    bound = true
end

local function unbind()
    if not bound or InCombatLockdown() then
        return
    end
    ClearOverrideBindings(owner)
    bound = false
end

function Bar.Bound()
    return bound
end

-- The bin question (Cafe.Confirm "bin") goes when the shift ends (CAFSUM, an off-shift CAFST) or combat starts, so a
-- stale Bin is never pressed.
function Bar.CloseBinDialog()
    Cafe.CloseConfirm("bin")
end

-- PLAYER_REGEN_DISABLED fires before the lockdown: the last moment the keys can be given back
ns.RegisterEvent("PLAYER_REGEN_DISABLED", function()
    combatEnded = true
    Bar.CloseBinDialog()
    Cafe.MarkShiftEndedLocally()
    unbind()
end)
-- never a bind here (a fresh CAFST does that); only keys left bound while the shift ended in combat come free
ns.RegisterEvent("PLAYER_REGEN_ENABLED", function()
    if bound and not Cafe.OnShift() then
        unbind()
    end
end)
ns.RegisterEvent("PLAYER_LEAVING_WORLD", function()
    unbind()
end)

ns.On("STATE", function(op)
    if op == "CAFST" then
        if Cafe.OnShift() then
            combatEnded = false
            if Bar.Warned() then
                unbind()
            else
                bind()
            end
        else
            Bar.CloseBinDialog()
            unbind()
        end
        Bar.Refresh()
    elseif op == "CAFSUM" then
        Bar.CloseBinDialog()
        unbind()
        Bar.Refresh()
    elseif op == "CAFT" or op == "CAFQ" or op == "DEF" or op == "CAFE" then
        -- CAFE: a danger pause or its end (open 2)
        Bar.Refresh()
    end
end)

ns.On("HELLO", function()
    if not Cafe.Enabled() then
        unbind()
    end
    Bar.Refresh()
end)

ns.On("CAFE_KEYS", function()
    unbind()
    bind()
    Bar.Refresh()
end)

ns.On("CAFE_RESET", function()
    unbind()
    combatEnded = false
    relSent = nil
    Bar.StopTiming()
    Bar.Refresh()
end)

ns.On("CAFE_SELECT", Bar.Refresh)

Cafe.Place(f, { point = "BOTTOM", x = 0, y = 240, mover = "bleakhold_cafe_bar", title = "Caf\195\169: barista bar",
    refresh = Bar.Refresh })
