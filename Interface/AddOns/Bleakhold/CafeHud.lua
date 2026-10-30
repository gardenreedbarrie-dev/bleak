-- Bleakhold: the café's HUD panels besides the barista bar (docs/BleakholdProtocol.md section 21). Every number is
-- server state (S.cafe*); the timers only count down between messages (Cafe.Left, Cafe.LeftMs). The stock look:
--   strip      BleakholdCafeStrip, top centre while on shift: the battleground score line (no panel, shadowed text,
--              the faction's WorldStateFrame icon with the café's name as its tooltip), the shift's numbers, the
--              barista level on a slim bar, End Shift, about 530 wide (clear of the target frame); under it the
--              warnings in red, today's XP in gold once past the full rate, the daily tip and points caps once
--              reached, the Morning Rush in orange (BleakholdCafeRush) and the patch notice (the first minute only)
--   ticket     BleakholdCafeTicket, left: the quest tracker (no panel, a gold title, objective lines 16 px apart): the
--              customer, the drink with its tier as raid stars after its name, the order line, patience on a cast bar,
--              "Steps 1 / 5" over a slim gold bar, the steps as objectives (ReadyCheck-Ready and the grade when done;
--              the next one white behind the dropdown menu's arrow, the others 0.8 grey behind a dash; a running tap
--              fills a slim green bar under its row), the tip; tabs for 2-3 tickets; with none, a gold "No ticket"
--              title and its objective line
--   queue      BleakholdCafeQueue, right: a tooltip panel listing the orders like the Who list (rows with the row
--              highlight, the chosen one in UI.Select's blue); a click takes the order at the counter, else chooses it
--   result     BleakholdCafeResult, centre: the raid warning's big outlined word, raid stars, a sub line; sounds
--   buffs      BleakholdCafeBuffs, top: the café's buffs as the stock BuffFrame shows buffs (in the capitals), under
--              the strip or the order chip while one shows (unless moved)
--   order      BleakholdCafeOrderChip, top: a customer's order (CAFO) on a small tooltip panel, Cancel in red
--   at the bar BleakholdCafeAtBar, right: who works at the bar, each step on the target frame's small cast bar
-- Money on the panels is drawn as the stock SmallMoneyFrame (Cafe.MoneyFrame); state is never colour alone.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S
local Cafe = ns.Cafe

local floor, ceil, max, min = math.floor, math.ceil, math.max, math.min

local Hud = {}
Cafe.Hud = Hud

Hud.STAR = "Interface\\TargetingFrame\\UI-RaidTargetingIcons"   -- cell 1: the star
Hud.READY = "Interface\\RaidFrame\\ReadyCheck-Ready"
Hud.HIGHLIGHT = "Interface\\QuestFrame\\UI-QuestTitleHighlight"
Hud.ARROW = "Interface\\ChatFrame\\ChatFrameExpandArrow"      -- UIDropDownMenu's submenu arrow: the next step
Hud.LOCK = "Interface\\LFGFrame\\UI-LFG-ICON-LOCK"
Hud.SMALL_BORDER = "Interface\\CastingBar\\UI-CastingBar-Border-Small"
Hud.SPARK = "Interface\\CastingBar\\UI-CastingBar-Spark"
Hud.FACTION = { [1] = "Interface\\WorldStateFrame\\AllianceIcon", [2] = "Interface\\WorldStateFrame\\HordeIcon" }
Hud.OBJECTIVE = "CCCCCC"           -- WatchFrame's objective lines (0.8 grey)
Hud.LINE_H = 16                    -- WATCHFRAME_LINEHEIGHT
Hud.GRADE_COLORS = { P = C.gold, G = C.teal, O = C.orange }
Hud.RESULT_IN, Hud.RESULT_HOLD, Hud.RESULT_OUT = 0.15, 1.5, 0.35

local DOT, TIMES = Cafe.DOT, Cafe.TIMES

local function hideTip()
    if GameTooltip then
        GameTooltip:Hide()
    end
end

local function shown(f, on)
    if on then
        f:Show()
    else
        f:Hide()
    end
end

local function gold(s)
    return "|cffffd100" .. s .. "|r"
end

-- raid star textures (UI-RaidTargetingIcons cell 1) for a tier or a grade
local function stars(parent, n, size, layer)
    local list = {}
    for i = 1, n do
        local t = parent:CreateTexture(nil, layer or "ARTWORK")
        t:SetTexture(Hud.STAR)
        t:SetTexCoord(0, 0.25, 0, 0.25)
        t:SetSize(size, size)
        t:Hide()
        list[i] = t
    end
    return list
end

-- A slim bar (the stock UI-StatusBar fill on black, a 1 px black edge): the strip's level bar, the queue's patience.
local function slimBar(parent, w, h)
    local b = CreateFrame("StatusBar", nil, parent)
    b:SetSize(w, h)
    b:SetStatusBarTexture(UI.STOCK.statusBar)
    b:SetMinMaxValues(0, 1)
    b:SetValue(0)
    b.bg = b:CreateTexture(nil, "BACKGROUND")
    b.bg:SetTexture(0, 0, 0, 0.6)
    b.bg:SetAllPoints(b)
    b.edge = CreateFrame("Frame", nil, b)
    b.edge:SetPoint("TOPLEFT", b, "TOPLEFT", -1, 1)
    b.edge:SetPoint("BOTTOMRIGHT", b, "BOTTOMRIGHT", 1, -1)
    b.edge:SetBackdrop({ edgeFile = UI.STOCK.white, edgeSize = 1 })
    b.edge:SetBackdropBorderColor(0, 0, 0, 1)
    return b
end
Hud.SlimBar = slimBar

-- The target frame's spell bar (TargetFrameSpellBar): the fill in CastingBar\UI-CastingBar-Border-Small, drawn at
-- 49/64 of its size as the stock one (its hole is the bar; the ends keep their size, the middle stretches), the spark
-- at the fill's head.
local SMALL_K = 49 / 64
local SMALL_U = { 0, 48 / 256, 208 / 256, 1 }
local function smallCastBar(parent, w)
    local b = CreateFrame("StatusBar", nil, parent)
    b:SetSize(w, 8)
    b:SetStatusBarTexture(UI.STOCK.statusBar)
    b:SetMinMaxValues(0, 1)
    b:SetValue(0)
    b.bg = b:CreateTexture(nil, "BACKGROUND")
    b.bg:SetTexture(0, 0, 0, 0.5)
    b.bg:SetAllPoints(b)
    b.border = CreateFrame("Frame", nil, b)
    b.border:SetPoint("TOPLEFT", b, "TOPLEFT", -floor(34 * SMALL_K + 0.5), floor(26 * SMALL_K + 0.5) - 1)
    b.border:SetPoint("BOTTOMRIGHT", b, "BOTTOMRIGHT", floor(34 * SMALL_K + 0.5), -floor(25 * SMALL_K + 0.5) + 1)
    b.border.parts = {}
    for i = 1, 3 do
        local t = b.border:CreateTexture(nil, "OVERLAY")
        t:SetTexture(Hud.SMALL_BORDER)
        t:SetTexCoord(SMALL_U[i], SMALL_U[i + 1], 0, 1)
        b.border.parts[i] = t
    end
    local l, m, r = b.border.parts[1], b.border.parts[2], b.border.parts[3]
    l:SetWidth(floor(48 * SMALL_K + 0.5))
    l:SetPoint("TOPLEFT", b.border, "TOPLEFT", 0, 0)
    l:SetPoint("BOTTOMLEFT", b.border, "BOTTOMLEFT", 0, 0)
    r:SetWidth(floor(48 * SMALL_K + 0.5))
    r:SetPoint("TOPRIGHT", b.border, "TOPRIGHT", 0, 0)
    r:SetPoint("BOTTOMRIGHT", b.border, "BOTTOMRIGHT", 0, 0)
    m:SetPoint("TOPLEFT", l, "TOPRIGHT", 0, 0)
    m:SetPoint("BOTTOMRIGHT", r, "BOTTOMLEFT", 0, 0)
    b.spark = b.border:CreateTexture(nil, "ARTWORK")
    b.spark:SetTexture(Hud.SPARK)
    b.spark:SetBlendMode("ADD")
    b.spark:SetSize(16, 20)
    function b:SetFill(p)
        p = U.Clamp(p or 0, 0, 1)
        self:SetValue(p)
        self.spark:ClearAllPoints()
        self.spark:SetPoint("CENTER", self, "LEFT", self:GetWidth() * p, 0)
        shown(self.spark, p > 0 and p < 1)
    end
    return b
end
Hud.SmallCastBar = smallCastBar

local function fullRow(labelText, value)
    return gold(labelText) .. " " .. value
end

------------------------------------------------------------------------------------------------------
-- 1. The top strip (BleakholdCafeStrip): on shift only
------------------------------------------------------------------------------------------------------
local strip = CreateFrame("Frame", "BleakholdCafeStrip", UIParent)
strip:SetSize(640, 32)
strip:SetFrameStrata("MEDIUM")
strip:Hide()
Hud.strip = strip

strip.icon = strip:CreateTexture(nil, "ARTWORK")
strip.icon:SetSize(32, 32)
-- the café's name is the faction icon's tooltip, not a word on the strip: the line stays about 560 wide, centred
-- between the target frame and the minimap (Hud.STRIP_MAX_W)
strip.name = UI.Text(strip, 14, C.gold)
strip.name:Hide()
strip.iconHit = CreateFrame("Frame", nil, strip)
strip.iconHit:SetAllPoints(strip.icon)
strip.iconHit:EnableMouse(true)
strip.iconHit:SetScript("OnEnter", function(self)
    UI.ShowTooltip(self, { Cafe.CafeName(Cafe.CafeId()), { "You are on shift here.", C.text } })
end)
strip.iconHit:SetScript("OnLeave", hideTip)
strip.stats = {}
for _, key in ipairs({ "shift", "drinks", "streak", "tips", "xp", "level" }) do
    strip.stats[key] = UI.Text(strip, 12, C.text)
end
strip.tips = Cafe.MoneyFrame(strip, 12)
-- "Earned": this shift's money, the NPCs' tips and the pay of players' orders (their wage and tip); the Shift tab's
-- today row counts only the NPC tips, which have the daily cap
strip.tipsHit = CreateFrame("Frame", nil, strip)
strip.tipsHit:EnableMouse(true)
strip.tipsHit:SetScript("OnEnter", function(self)
    UI.ShowTooltip(self, Hud.EarnedTooltip(S.cafeState))
end)
strip.tipsHit:SetScript("OnLeave", hideTip)
strip.levelBar = slimBar(strip, 74, 5)
strip.levelBar:SetStatusBarColor(0.58, 0, 0.55)       -- the stock XP bar's purple
strip.levelHit = CreateFrame("Frame", nil, strip)
strip.levelHit:EnableMouse(true)
strip.levelHit:SetScript("OnEnter", function(self)
    local st = S.cafeState
    if not st then
        return
    end
    local lines = { "Barista level " .. st.level }
    if st.nextLevelXp then
        lines[#lines + 1] = { U.Commas(st.xp) .. " / " .. U.Commas(st.nextLevelXp), C.text }
        lines[#lines + 1] = { U.Commas(max(0, st.nextLevelXp - st.xp)) .. " XP to level " .. (st.level + 1), C.dim }
    else
        lines[#lines + 1] = { U.Commas(st.xp) .. " XP: the highest barista level", C.text }
    end
    -- today's XP against the daily cap (also the XP number's tooltip)
    lines[#lines + 1] = { "Today: " .. Hud.DayXpText(st.day or {}), C.dim }
    UI.ShowTooltip(self, lines)
end)
strip.levelHit:SetScript("OnLeave", hideTip)
-- the XP: this shift's on the strip, today's (the daily cap) in its tooltip
strip.xpHit = CreateFrame("Frame", nil, strip)
strip.xpHit:EnableMouse(true)
strip.xpHit:SetScript("OnEnter", function(self)
    UI.ShowTooltip(self, Hud.XpTooltip(S.cafeState))
end)
strip.xpHit:SetScript("OnLeave", hideTip)
strip.endBtn = UI.Button(strip, 84, 20, "End Shift", "ghost", 10)
strip.endBtn:SetScript("OnClick", function()
    Cafe.EndShift()
end)
strip.endBtn.tooltip = function()
    return { "End Shift", { "Your shift's summary opens; your action bar keys come back.", C.mid, true } }
end
strip.warn = UI.Text(strip, 12, C.red, "body", "CENTER")
strip.dayXp = UI.Text(strip, 12, C.gold, "body", "CENTER")
strip.caps = UI.Text(strip, 12, C.gold, "body", "CENTER")
strip.rush = CreateFrame("Frame", "BleakholdCafeRush", strip)
strip.rush:SetSize(400, 16)
strip.rush.text = UI.Text(strip.rush, 12, C.orange, "body", "CENTER")
strip.rush.text:SetPoint("CENTER", strip.rush, "CENTER", 0, 0)
strip.notice = UI.Text(strip, 11, C.dim, "body", "CENTER")

Hud.PATCH_TEXT = "Update your Bleakhold client to see the new caf\195\169 art."
Hud.PATCH_HOLD = 60                -- s the strip shows it, from the first time the strip shows with patch-4 missing
local patchPrinted = false
local patchShownAt

-- Is any café open with patch-4 missing? Printed once in chat; on the strip only for the first minute of the session's
-- first shift, then never again this session (it cannot be acted on mid-shift, and the line would stay all shift).
local function patchNotice()
    if Cafe.PatchPresent() then
        return nil
    end
    for _, c in pairs(S.cafes or {}) do
        if c.open == 1 then
            if not patchPrinted then
                patchPrinted = true
                ns.Print(Hud.PATCH_TEXT)
            end
            patchShownAt = patchShownAt or GetTime()
            if GetTime() - patchShownAt < Hud.PATCH_HOLD then
                return Hud.PATCH_TEXT
            end
            return nil
        end
    end
end

-- Tired (CAFST flag 4): the server halves barista XP and Café Points (XpForDrink, PointsForDrink), never the tips.
-- tiredSec is the work left before it on shift, and while Tired the rest off shift it still needs (that one runs down
-- only off shift, so on shift it is shown as sent).
Hud.TIRED_TEXT = "Tired: barista XP and Caf\195\169 Points halved"
Hud.TIRED_WARN = 300               -- s of work left before Tired when the strip starts counting it down
function Hud.TiredLine(st)
    local flags = st.flags or 0
    if Cafe.Rested(st) then
        return nil
    end
    if bit.band(flags, 4) ~= 0 then
        local rest = st.tiredSec
        if rest and rest > 0 then
            if not st.onShift then
                rest = Cafe.Left(st, "tiredSec")
            end
            return Hud.TIRED_TEXT .. " (" .. U.Clock(ceil(rest)) .. " rest off shift)"
        end
        return Hud.TIRED_TEXT
    end
    if st.onShift then
        local left = Cafe.Left(st, "tiredSec")
        if left and left < Hud.TIRED_WARN then
            return "Tired in " .. U.Clock(ceil(left))
        end
    end
end

-- the warning lines under the strip (red): danger, outside the café, mounted, tired
function Hud.Warnings()
    local st = S.cafeState or {}
    local lines = {}
    local c = S.cafes[st.cafeId or 0]
    if c and c.open == 2 then
        lines[#lines + 1] = "Danger nearby: the caf\195\169 has paused"
    end
    local flags = st.flags or 0
    local warn = Cafe.Left(st, "warnSec")
    if bit.band(flags, 8) ~= 0 then
        lines[#lines + 1] = "Return to the caf\195\169: " .. ceil(warn or 0)
    end
    if bit.band(flags, 64) ~= 0 then
        lines[#lines + 1] = "Dismount and show yourself: " .. ceil(warn or 0)
    end
    local tired = Hud.TiredLine(st)
    if tired then
        lines[#lines + 1] = tired
    end
    return lines
end

-- the Morning Rush line: the shift's R record, else the café's CAFE row
function Hud.RushLine()
    local st = S.cafeState or {}
    local r = st.rush
    if r and r.rushState > 0 then
        local sec = ceil(Cafe.RushLeft(r, st.cafeId) or 0)
        if r.rushState == 2 then
            return "Morning Rush" .. DOT .. U.Clock(sec) .. " left" .. DOT .. r.rushServed .. "/" .. r.rushGoal .. " served"
        end
        return "Morning Rush in " .. U.Clock(sec)
    end
    local c = S.cafes[Cafe.CafeId()]
    if c and c.rushState > 0 then
        return Cafe.RushText(c.rushState, Cafe.RushLeft(c, c.cafeId))
    end
end

-- Today's XP as the café window's Shift tab counts it. dayXp is the XP credited (section 21): the first dayXpFull XP
-- earned count in full, the next dayXpHalf at half, so the half band adds at most floor(dayXpHalf / 2) and a capped day
-- ends at dayXpFull + that (Cafe.DayXpBands).
function Hud.DayXpText(day)
    local xp, full, halfCredit = Cafe.DayXpBands(day)
    if xp < full or (full == 0 and halfCredit == 0) then
        return xp .. "/" .. full .. " today"
    elseif xp < full + halfCredit then
        return full .. "/" .. full .. DOT .. "+" .. (xp - full) .. "/" .. halfCredit .. " half rate"
    end
    return "Daily XP cap reached"
end

-- The strip's XP: this shift's. Today's (Hud.DayXpText) is its tooltip while it counts in full, and a line under the
-- strip once it is past the full rate or at the cap (Hud.DayXpLine), so the strip itself stays one short line.
function Hud.XpStatText(st)
    return "+" .. (st.shiftXp or 0)
end

function Hud.DayXpLine(st)
    local xp, full, halfCredit = Cafe.DayXpBands(st.day)
    if (full > 0 or halfCredit > 0) and xp >= full then
        if xp >= full + halfCredit then
            return Hud.DayXpText(st.day) .. ": no more barista XP today"
        end
        return "Barista XP today: " .. Hud.DayXpText(st.day)
    end
end

-- The daily caps besides XP, once reached (CAFST D): the NPC tips (dayTipsCapCopper) and the Café Points of the weekly
-- board (dayPointsCap). Every drink after that adds nothing to them, so the strip says it under itself.
function Hud.TipCapReached(day)
    local cap = day and day.dayTipsCapCopper or 0
    return cap > 0 and (day.dayTipsCopper or 0) >= cap
end

function Hud.PointsCapReached(day)
    local cap = day and day.dayPointsCap or 0
    return cap > 0 and (day.dayPoints or 0) >= cap
end

function Hud.DayCapsLine(st)
    local day = st and st.day
    local parts = {}
    if Hud.TipCapReached(day) then
        parts[#parts + 1] = "Daily tip cap reached"
    end
    if Hud.PointsCapReached(day) then
        parts[#parts + 1] = "Caf\195\169 Points today: " .. U.Commas(day.dayPoints) .. "/" .. U.Commas(day.dayPointsCap)
            .. ": no more points today"
    end
    if #parts > 0 then
        return table.concat(parts, DOT)
    end
end

Hud.EARNED = "Earned"
function Hud.EarnedTooltip(st)
    st = st or {}
    local day = st.day or {}
    local lines = { "Earned this shift", { Cafe.MoneyPlain(st.tipsCopper or 0), C.text },
        { "NPC tips, and for a player's order your wage and their tip.", C.dim, true } }
    local cap = day.dayTipsCapCopper or 0
    if cap > 0 then
        lines[#lines + 1] = { "NPC tips today: " .. Cafe.MoneyPlain(day.dayTipsCopper or 0) .. " / " .. Cafe.MoneyPlain(cap)
            .. " (the daily cap)", C.dim, true }
    end
    return lines
end

function Hud.XpTooltip(st)
    st = st or {}
    local day = st.day or {}
    local lines = { "Barista XP", { "+" .. (st.shiftXp or 0) .. " this shift", C.text } }
    lines[#lines + 1] = { "Today: " .. Hud.DayXpText(day), C.text }
    local _, full, halfCredit = Cafe.DayXpBands(day)
    if full > 0 then
        lines[#lines + 1] = { "Each day the first " .. full .. " XP count in full, then up to +" .. halfCredit
            .. " more at half rate.", C.dim, true }
    end
    return lines
end

Hud.STRIP_GAP = 11                 -- between the strip's numbers (11: "Earned" fits the 600)
Hud.STRIP_MAX_W = 600              -- the spec's strip: clear of the target frame and the minimap at 1080p

function Hud.RefreshStrip()
    local on = Cafe.Enabled() and (Cafe.OnShift() or Cafe.editing)
    shown(strip, on)
    if not on then
        Hud.AnchorBuffs()
        return
    end
    local st = S.cafeState or { level = 1, xp = 0, levelXp = 0, day = {} }
    local cafeId = Cafe.CafeId()
    strip.icon:SetTexture(Hud.FACTION[cafeId] or Hud.FACTION[1])
    UI.SetText(strip.name, Cafe.CafeName(cafeId))
    local s = strip.stats
    local shiftSec = Cafe.Left(st, "shiftSec") and (st.shiftSec + (GetTime() - st.recvAt)) or 0
    s.shift:SetText(fullRow("Shift", U.Clock(shiftSec)))
    s.drinks:SetText(fullRow("Drinks", tostring(st.drinks or 0)))
    s.streak:SetText(fullRow("Streak", TIMES .. (st.streak or 0)))
    s.tips:SetText(gold(Hud.EARNED))
    strip.tips:SetCopper(st.tipsCopper or 0)
    s.xp:SetText(fullRow("XP", Hud.XpStatText(st)))
    s.level:SetText(fullRow("Barista", tostring(st.level or 1)))
    local lo, hi = st.levelXp or 0, st.nextLevelXp
    strip.levelBar:SetValue(hi and hi > lo and U.Clamp((st.xp - lo) / (hi - lo), 0, 1) or 1)
    -- one line, centred: the faction icon (the café's name on hover), the numbers, End Shift
    local items = { { strip.icon, 32 } }
    for _, key in ipairs({ "shift", "drinks", "streak", "tips", "xp", "level" }) do
        items[#items + 1] = { s[key], ceil(s[key]:GetStringWidth() or 0), key }
        if key == "tips" then
            items[#items + 1] = { strip.tips, strip.tips:GetWidth(), "money" }
        end
    end
    items[#items + 1] = { strip.endBtn, 84 }
    -- every text on the strip's middle line (one baseline); the level bar hangs under "Barista 6", inside the strip
    local x = 0
    for i, it in ipairs(items) do
        local gap = (i == 1 and 0) or (it[3] == "money" and 4) or (i == 2 and 6) or Hud.STRIP_GAP
        x = x + gap
        it[1]:ClearAllPoints()
        it[1]:SetPoint("LEFT", strip, "LEFT", x, 0)
        it.x = x
        x = x + it[2]
        if it[3] == "level" then
            strip.levelBar:ClearAllPoints()
            strip.levelBar:SetPoint("TOPLEFT", it[1], "BOTTOMLEFT", 0, -2)
            strip.levelBar:SetWidth(max(40, it[2]))
            strip.levelHit:ClearAllPoints()
            strip.levelHit:SetPoint("TOPLEFT", it[1], "TOPLEFT", -2, 3)
            strip.levelHit:SetPoint("BOTTOMRIGHT", strip.levelBar, "BOTTOMRIGHT", 2, -3)
        elseif it[3] == "xp" then
            strip.xpHit:ClearAllPoints()
            strip.xpHit:SetPoint("TOPLEFT", it[1], "TOPLEFT", -2, 3)
            strip.xpHit:SetPoint("BOTTOMRIGHT", it[1], "BOTTOMRIGHT", 2, -3)
        elseif it[3] == "money" then
            strip.tipsHit:ClearAllPoints()
            strip.tipsHit:SetPoint("TOPLEFT", s.tips, "TOPLEFT", -2, 3)
            strip.tipsHit:SetPoint("BOTTOMRIGHT", it[1], "BOTTOMRIGHT", 2, -3)
        end
    end
    strip:SetWidth(max(200, x))
    -- the lines under it (strip.blockH: from the strip's top to the last line's foot, where the buffs go under it)
    local y = -36
    local warns = Hud.Warnings()
    strip.warn:SetText(table.concat(warns, DOT))
    strip.warn:ClearAllPoints()
    strip.warn:SetPoint("TOP", strip, "TOP", 0, y)
    shown(strip.warn, #warns > 0)
    if #warns > 0 then
        y = y - 16
    end
    local dayXp = Hud.DayXpLine(st)
    strip.dayXp:SetText(dayXp or "")
    strip.dayXp:ClearAllPoints()
    strip.dayXp:SetPoint("TOP", strip, "TOP", 0, y)
    shown(strip.dayXp, dayXp ~= nil)
    if dayXp then
        y = y - 16
    end
    local caps = Hud.DayCapsLine(st)
    strip.caps:SetText(caps or "")
    strip.caps:ClearAllPoints()
    strip.caps:SetPoint("TOP", strip, "TOP", 0, y)
    shown(strip.caps, caps ~= nil)
    if caps then
        y = y - 16
    end
    local rush = Hud.RushLine()
    strip.rush.text:SetText(rush or "")
    strip.rush:ClearAllPoints()
    strip.rush:SetPoint("TOP", strip, "TOP", 0, y)
    shown(strip.rush, rush ~= nil)
    if rush then
        y = y - 16
    end
    local notice = patchNotice()
    strip.notice:SetText(notice or "")
    strip.notice:ClearAllPoints()
    strip.notice:SetPoint("TOP", strip, "TOP", 0, y)
    shown(strip.notice, notice ~= nil)
    if notice then
        y = y - 16
    end
    strip.blockH = y < -36 and (-y - 2) or strip:GetHeight()
    Hud.AnchorBuffs()
end

------------------------------------------------------------------------------------------------------
-- 2. The ticket (BleakholdCafeTicket): the quest tracker's look
------------------------------------------------------------------------------------------------------
Hud.TICKET_W = 280
Hud.TICKET_BAR_X = 12 + 9                         -- the cast bar's studs line up with the text (as the key tracker)
local TW = Hud.TICKET_W
Hud.TICKET_ROW_W = TW - 12 - Hud.TICKET_BAR_X     -- a step row (at x 12) ends where the bars above it end
Hud.ROW_TEXT_X = 16                               -- a row's name (and its sub line) after the mark
Hud.RUN_BAND = 8                                  -- under a running tap's row: 2 px, its 4 px bar, 2 px
Hud.RUN_COLOR = "00FF00"                          -- the stock channel bar's green

local tk = CreateFrame("Frame", "BleakholdCafeTicket", UIParent)
tk:SetSize(TW, 200)
tk:SetFrameStrata("MEDIUM")
tk:Hide()
Hud.ticket = tk

tk.tabs = {}
for i = 1, 3 do
    local b = UI.Button(tk, 70, 20, "#" .. i, "tab", 10)
    b:SetPoint("TOPLEFT", tk, "TOPLEFT", 10 + (i - 1) * 74, -2)
    b:SetScript("OnClick", function(self)
        if self.ticketId and not Cafe.SelectTicket(self.ticketId) then
            Cafe.Notice(ns.ErrorText({ code = "cafe_hands", text = "Finish or bin the drink in your hands first." }))
        end
        Hud.RefreshTicket()
    end)
    b:Hide()
    tk.tabs[i] = b
end
tk.kicker = UI.Text(tk, 10, C.dim)
UI.OneLine(tk.kicker, TW - 24)
tk.customer = UI.Text(tk, 12, C.text)
UI.OneLine(tk.customer, TW - 24)
tk.drink = UI.Text(tk, 14, C.gold)
tk.stars = stars(tk, 5, 12)
tk.line = UI.Para(tk, 11, C.text, TW - 24)
tk.line:SetHeight(28)
tk.patience = UI.TimerBar(tk, TW - 2 * Hud.TICKET_BAR_X, "00FF00")
tk.patience.text:SetFont(UI.FONT_BODY, 10, "")
-- the drink's progress: an objective line "Steps 1 / 5" over a slim gold bar (the ticket's one ornate frame is patience's)
tk.stepsLabel = UI.Text(tk, 11, Hud.OBJECTIVE)
tk.stepsLabel:SetText("Steps")
tk.progress = slimBar(tk, TW - 2 * Hud.TICKET_BAR_X, 5)
tk.progress:SetStatusBarColor(UI.Rgb(UI.BAR_GOLD))
tk.progress.text = UI.Text(tk, 11, C.text, "body", "RIGHT")
tk.progress.text:SetPoint("BOTTOMRIGHT", tk.progress, "TOPRIGHT", 0, 3)
tk.stepsLabel:SetPoint("BOTTOMLEFT", tk.progress, "TOPLEFT", 0, 3)
function tk.progress:SetProgress(p, text)
    self:SetValue(U.Clamp(p or 0, 0, 1))
    self.text:SetText(text or "")
end
tk.footLabel = UI.Text(tk, 11, C.text)
tk.footMoney = Cafe.MoneyFrame(tk, 11)
tk.footNext = UI.Text(tk, 11, C.text)
-- no ticket: the tracker's anatomy, a gold title and an objective line under it
tk.emptyTitle = UI.Text(tk, 13, C.gold)
tk.emptyTitle:SetText("No ticket")
tk.emptyDash = UI.Text(tk, 12, Hud.OBJECTIVE)
tk.emptyDash:SetText("-")
tk.empty = UI.Para(tk, 12, Hud.OBJECTIVE, TW - 24 - 14)

tk.rowPool = UI.Pool(function()
    local r = CreateFrame("Frame", nil, tk)
    r:SetSize(Hud.TICKET_ROW_W, Hud.LINE_H)
    r.mark = r:CreateTexture(nil, "ARTWORK")
    r.mark:SetTexture(Hud.READY)
    r.mark:SetSize(12, 12)
    r.mark:SetPoint("TOPLEFT", r, "TOPLEFT", 0, -2)
    -- the next step: the dropdown menu's gold arrow where the dash is, and white text
    r.arrow = r:CreateTexture(nil, "ARTWORK")
    r.arrow:SetTexture(Hud.ARROW)
    r.arrow:SetSize(12, 12)
    r.arrow:SetPoint("TOPLEFT", r, "TOPLEFT", 0, -2)
    r.dash = UI.Text(r, 12, Hud.OBJECTIVE)
    r.dash:SetPoint("TOPLEFT", r, "TOPLEFT", 2, -1)
    r.dash:SetText("-")
    r.name = UI.Text(r, 12, Hud.OBJECTIVE)
    r.name:SetPoint("TOPLEFT", r, "TOPLEFT", Hud.ROW_TEXT_X, -1)
    UI.OneLine(r.name, 150)
    r.where = UI.Text(r, 11, C.mute, "body", "RIGHT")
    r.where:SetPoint("TOPRIGHT", r, "TOPRIGHT", 0, -2)
    UI.OneLine(r.where, 90)
    r.sub = UI.Text(r, 10, C.gold)
    r.sub:SetPoint("TOPLEFT", r, "TOPLEFT", Hud.ROW_TEXT_X, -16)
    return r
end)

-- the running tap's progress (CAFEV S to its end) in a band under its row while it runs, as the objective tracker's
-- progress bars; a timed step has the timing bar over the café bar instead
tk.stepBar = slimBar(tk, Hud.TICKET_ROW_W - Hud.ROW_TEXT_X, 4)
tk.stepBar:SetStatusBarColor(UI.Rgb(Hud.RUN_COLOR))
tk.stepBar:Hide()
function tk.stepBar:Fill()
    local cs = self.step
    local dur = cs and (cs.durMs or 0) / 1000 or 0
    self:SetValue(dur > 0 and U.Clamp((GetTime() - (cs.recvAt or 0)) / dur, 0, 1) or 1)
end

-- The steps as checklist lines: consecutive equal actions merge into one ("Scoop Ice Cream x2", 1/2).
function Hud.StepGroups(t)
    local out = {}
    for i, s in ipairs(t and t.steps or {}) do
        local g = out[#out]
        if g and g.actionId == s.actionId then
            g.last, g.count = i, g.count + 1
            g.grades[#g.grades + 1] = s.grade
        else
            out[#out + 1] = { actionId = s.actionId, first = i, last = i, count = 1, grades = { s.grade } }
        end
    end
    local nextStep = t and t.nextStep or 1
    for _, g in ipairs(out) do
        g.done = max(0, min(g.count, nextStep - g.first))
        if g.last < nextStep then
            g.state = "done"
        elseif g.first <= nextStep then
            g.state = "next"
        else
            g.state = "pending"
        end
    end
    return out
end

local function gradeLetters(grades, n)
    local parts = {}
    for i = 1, n do
        local g = grades[i]
        if Hud.GRADE_COLORS[g] then
            parts[#parts + 1] = "|cff" .. Hud.GRADE_COLORS[g] .. g .. "|r"
        end
    end
    return table.concat(parts)
end

function Hud.RefreshTicket()
    local on = Cafe.Enabled() and (Cafe.OnShift() or Cafe.editing)
    shown(tk, on)
    if not on then
        return
    end
    local list = Cafe.Tickets()
    local t = Cafe.ActiveTicket()
    local y = -4
    -- tabs (2-3 tickets)
    for i, b in ipairs(tk.tabs) do
        local tt = list[i]
        if tt and #list >= 2 then
            b.ticketId = tt.ticketId
            b:SetLabel(tt.inHand and "In hand" or ("#" .. i))
            b:SetStyle(t and tt.ticketId == t.ticketId and "tabOn" or "tab")
            b:Show()
        else
            b.ticketId = nil
            b:Hide()
        end
    end
    if #list >= 2 then
        y = y - 24
    end
    tk.rowPool:ReleaseAll()
    tk.stepBar:Hide()
    tk.stepBar.step = nil
    local parts = { tk.kicker, tk.customer, tk.drink, tk.line, tk.patience, tk.stepsLabel, tk.progress,
        tk.progress.text, tk.footLabel, tk.footMoney, tk.footNext }
    local emptyParts = { tk.emptyTitle, tk.emptyDash, tk.empty }
    if not t then
        for _, p in ipairs(parts) do
            p:Hide()
        end
        for _, s in ipairs(tk.stars) do
            s:Hide()
        end
        tk.emptyTitle:ClearAllPoints()
        tk.emptyTitle:SetPoint("TOPLEFT", tk, "TOPLEFT", 12, y)
        y = y - 18
        tk.emptyDash:ClearAllPoints()
        tk.emptyDash:SetPoint("TOPLEFT", tk, "TOPLEFT", 14, y)
        tk.empty:ClearAllPoints()
        tk.empty:SetPoint("TOPLEFT", tk, "TOPLEFT", 12 + 16, y)
        -- the key only at the counter: away from the stations the bar's slots name the stations (slot 7 the counter)
        local st = S.cafeState
        if st and st.station == "V" then
            tk.empty:SetText("Take the next order [" .. Cafe.SlotKey(1) .. "]")
        else
            tk.empty:SetText("Walk to the Serving Counter to take an order.")
        end
        for _, p in ipairs(emptyParts) do
            p:Show()
        end
        tk:SetHeight(-y + 20)
        return
    end
    for _, p in ipairs(emptyParts) do
        p:Hide()
    end
    for _, p in ipairs(parts) do
        p:Show()
    end
    local r = Cafe.Recipe(t.recipeId)
    local kind = t.kind == "P" and "Player" or (t.kind == "G" and "Group" or "Customer")
    tk.kicker:SetText("Order #" .. (t.orderId or t.ticketId) .. DOT .. kind)
    tk.kicker:ClearAllPoints()
    tk.kicker:SetPoint("TOPLEFT", tk, "TOPLEFT", 12, y)
    y = y - 14
    UI.SetText(tk.customer, t.customer or kind)
    tk.customer:ClearAllPoints()
    tk.customer:SetPoint("TOPLEFT", tk, "TOPLEFT", 12, y)
    y = y - 16
    -- the drink, cut short only where its tier's stars need the room; the stars follow its last letter
    local tier = min(#tk.stars, r and r.tier or 0)
    UI.SetText(tk.drink, r and r.name or "A drink")
    local room = TW - 24 - (tier > 0 and (4 + tier * 13) or 0)
    UI.OneLine(tk.drink, max(40, min(ceil(Cafe.FullWidth(tk.drink)) + 2, room)))
    tk.drink:ClearAllPoints()
    tk.drink:SetPoint("TOPLEFT", tk, "TOPLEFT", 12, y)
    for i, s in ipairs(tk.stars) do
        s:ClearAllPoints()
        s:SetPoint("LEFT", tk.drink, "RIGHT", 2 + (i - 1) * 13, 0)
        shown(s, i <= tier)
    end
    y = y - 18
    if t.orderLine and t.orderLine ~= "" then
        UI.SetText(tk.line, "\"" .. t.orderLine .. "\"")
        tk.line:ClearAllPoints()
        tk.line:SetPoint("TOPLEFT", tk, "TOPLEFT", 12, y)
        -- one line or two (at most), counted on the whole text: the box from the last ticket is let go first
        local lines = min(2, max(1, ceil(Cafe.FullWidth(tk.line) / (TW - 24))))
        tk.line:SetWidth(TW - 24)
        tk.line:SetHeight(lines * 14)
        y = y - lines * 14 - 4
    else
        tk.line:Hide()
    end
    -- patience: a cast bar coloured as the health bar, the seconds in it
    y = y - 12
    tk.patience:ClearAllPoints()
    tk.patience:SetPoint("TOPLEFT", tk, "TOPLEFT", Hud.TICKET_BAR_X, y)
    Hud.TickTicket()
    y = y - UI.TIMER_H - 14
    -- steps: "Steps 1 / 5" over the drink's progress, then the checklist
    local done, total = max(0, (t.nextStep or 1) - 1), #(t.steps or {})
    y = y - 16
    tk.progress:ClearAllPoints()
    tk.progress:SetPoint("TOPLEFT", tk, "TOPLEFT", Hud.TICKET_BAR_X, y)
    tk.progress:SetProgress(total > 0 and done / total or 0, done .. " / " .. total)
    y = y - 5 - 9
    local memory = Cafe.MemoryMode()
    local nextStation
    local run = Cafe.Bar and Cafe.Bar.StepRunning()
    -- the timed step running on this ticket: its row prints the step's own gold zone (CAFEV S moves it by up to 5%)
    local timedRun = run and run.ticketId == t.ticketId and Cafe.Bar.IsTimed(run) and run or nil
    if run and (run.ticketId ~= t.ticketId or Cafe.Bar.IsTimed(run)) then
        run = nil
    end
    for _, g in ipairs(Hud.StepGroups(t)) do
        local row = tk.rowPool:Acquire()
        local a = Cafe.Action(g.actionId)
        local name = a and a.name or "?"
        if g.count > 1 then
            name = name .. " " .. TIMES .. g.count
            if g.state == "next" then
                name = name .. " (" .. g.done .. "/" .. g.count .. ")"
            end
        end
        local hidden = memory and g.state ~= "done"
        local where = a and (Cafe.ShortStation(a.station) .. " [" .. Cafe.SlotKey(a.key or 1) .. "]") or ""
        row.mark:Hide()
        row.arrow:Hide()
        row.dash:Hide()
        if g.state == "done" then
            row.mark:Show()
            UI.SetText(row.name, name)
            row.name:SetText(U.Safe(name) .. " " .. gradeLetters(g.grades, g.count))
            UI.SetColor(row.name, C.mute)
            UI.SetColor(row.where, C.mute)
        elseif g.state == "next" then
            row.arrow:Show()
            UI.SetText(row.name, hidden and "? ? ?" or name)
            UI.SetColor(row.name, C.text)
            UI.SetColor(row.where, C.dim)
            nextStation = a and a.station
        else
            row.dash:Show()
            UI.SetText(row.name, hidden and "? ? ?" or name)
            UI.SetColor(row.name, Hud.OBJECTIVE)
            UI.SetColor(row.where, C.mute)
        end
        UI.SetText(row.where, hidden and "" or where)
        -- the name runs up to 8 short of the station and its key
        local whereW = hidden and 0 or ceil(row.where:GetStringWidth() or 0)
        UI.OneLine(row.name, max(60, Hud.TICKET_ROW_W - Hud.ROW_TEXT_X - whereW - 8))
        local h = Hud.LINE_H
        if a and a.timed and not hidden and a.gold then
            row.sub:SetText(Hud.GoldText(a, g.state == "next" and timedRun, g))
            -- the step about to be done in full gold (its window is the number to keep in mind), the later ones in
            -- the darker gold, the done ones grey
            UI.SetColor(row.sub, (g.state == "done" and C.mute) or (g.state == "next" and C.gold) or C.goldDark)
            row.sub:Show()
            h = h + 12
        else
            row.sub:Hide()
        end
        if g.state == "next" and run and run.stepIndex >= g.first and run.stepIndex <= g.last then
            tk.stepBar:ClearAllPoints()
            tk.stepBar:SetPoint("TOPLEFT", row, "TOPLEFT", Hud.ROW_TEXT_X, -h - 2)
            tk.stepBar.step = run
            tk.stepBar:Fill()
            tk.stepBar:Show()
            h = h + Hud.RUN_BAND
        end
        row:SetHeight(h)
        row.group = g
        row:ClearAllPoints()
        row:SetPoint("TOPLEFT", tk, "TOPLEFT", 12, y)
        y = y - h
    end
    -- the tip (or a player's order's pay) and where the next step is; after the daily tip cap an NPC tips nothing, and
    -- the station goes to a line of its own
    y = y - 6
    local label, copper = Hud.TicketMoney(t, S.cafeState and S.cafeState.day)
    tk.footLabel:SetText(label)
    tk.footLabel:ClearAllPoints()
    tk.footLabel:SetPoint("TOPLEFT", tk, "TOPLEFT", 12, y)
    tk.footMoney:SetCopper(copper or 0)
    tk.footMoney:ClearAllPoints()
    tk.footMoney:SetPoint("LEFT", tk.footLabel, "RIGHT", 4, 0)
    shown(tk.footMoney, copper ~= nil)
    if nextStation and not memory then
        tk.footNext:SetText((copper and DOT:sub(2) or "") .. "Next: " .. Cafe.StationName(nextStation))
        tk.footNext:Show()
    else
        tk.footNext:SetText("")
    end
    tk.footNext:ClearAllPoints()
    if copper then
        tk.footNext:SetPoint("LEFT", tk.footMoney, "RIGHT", 2, 0)
    elseif tk.footNext:GetText() ~= "" then
        y = y - 16
        tk.footNext:SetPoint("TOPLEFT", tk, "TOPLEFT", 12, y)
    end
    y = y - 18
    tk:SetHeight(-y + 4)
end

-- The ticket's money line: an NPC's tip as much as today's tip cap still allows (the server pays CapAdd(tip, today,
-- cap)), or for a player's order the pay (CAFT tipHintCopper: the barista's wage and the customer's tip, section 21).
-- Returns the label and the copper, or the label alone when nothing more is paid today.
Hud.CAPPED_TIP = "Tip: none (daily tip cap reached)"
function Hud.TicketMoney(t, day)
    local hint = t and t.tipHintCopper or 0
    if t and t.kind == "P" then
        return "Pay: about", hint
    end
    local cap = day and day.dayTipsCapCopper or 0
    if cap > 0 then
        local room = max(0, cap - (day.dayTipsCopper or 0))
        if room <= 0 then
            return Hud.CAPPED_TIP, nil
        end
        hint = min(hint, room)
    end
    return "Tip: about", hint
end

-- A timed step's gold zone on its row: the zone of the step running now, from its CAFEV S (the server moves each by up
-- to 5%); the others' are the action's (DEF G or CafeData), so only "about".
function Hud.GoldText(a, cs, g)
    if cs and g and cs.stepIndex >= g.first and cs.stepIndex <= g.last and cs.goldLoMs and cs.goldHiMs
        and (cs.durMs or 0) > 0 then
        return "Gold " .. floor(cs.goldLoMs * 100 / cs.durMs) .. "-" .. floor(cs.goldHiMs * 100 / cs.durMs) .. "%"
    end
    return "Gold about " .. floor(a.gold[1] / 10) .. "-" .. floor(a.gold[2] / 10) .. "%"
end

-- patience counts down between CAFT messages
function Hud.TickTicket()
    local t = Cafe.ActiveTicket()
    if not t or not tk:IsShown() then
        return
    end
    -- the café's clocks stand still while it is paused (CAFE open 2): the frozen seconds, greyed
    local cafeId = Cafe.CafeId()
    local paused = Cafe.Paused(cafeId)
    local leftMs = Cafe.LeftMs(t, "patienceMs", cafeId) or 0
    local frac = (t.patienceMaxMs or 0) > 0 and leftMs / t.patienceMaxMs or 0
    tk.patience:SetStatusBarColor(UI.Rgb(paused and C.dim or Cafe.PatienceColor(frac)))
    tk.patience:SetProgress(frac, ceil(leftMs / 1000) .. " s" .. (paused and " (paused)" or ""))
    Hud.patienceColor = Cafe.PatienceColor(frac)
    local cs = tk.stepBar.step
    if cs then
        if Cafe.Bar.StepRunning() ~= cs then
            -- it ran out without its D: lay the rows out again without the band
            Hud.RefreshTicket()
        else
            tk.stepBar:Fill()
        end
    end
end

------------------------------------------------------------------------------------------------------
-- 3. The queue (BleakholdCafeQueue): on shift
------------------------------------------------------------------------------------------------------
Hud.QUEUE_W = 250
Hud.QUEUE_ROW = 46                 -- a row with a tag line (Player, Group, Level 9, Taken by)
Hud.QUEUE_ROW_SHORT = 34           -- a row of a name and a drink only
local QW = Hud.QUEUE_W
Hud.QUEUE_TEXT_X = 34              -- the name, the drink and the tag line, after the icon
Hud.QUEUE_SECS_R = QW - 16 - 4     -- the seconds' right edge in a row

local qf = CreateFrame("Frame", "BleakholdCafeQueue", UIParent)
qf:SetSize(QW, 60)
qf:SetFrameStrata("MEDIUM")
UI.Backdrop(qf, C.panel, C.border, nil, "panel")
qf:Hide()
Hud.queue = qf
qf.header = UI.Text(qf, 13, C.gold)
qf.header:SetPoint("TOPLEFT", qf, "TOPLEFT", 12, -10)
UI.OneLine(qf.header, QW - 24)
qf.empty = UI.Text(qf, 11, C.dim)
qf.empty:SetPoint("TOPLEFT", qf, "TOPLEFT", 12, -30)
qf.empty:SetText("Nobody is waiting.")

local function queueTip(row)
    local d = row.data
    if not d then
        return
    end
    local r = Cafe.Recipe(d.recipeId)
    local lines = { U.Safe(d.customer or "Customer") }
    lines[#lines + 1] = { U.Safe(r and r.name or "A drink"), C.gold }
    if r then
        local names = {}
        for _, g in ipairs(Hud.StepGroups({ steps = (function()
            local s = {}
            for i, a in ipairs(r.steps) do
                s[i] = { actionId = a, grade = "N" }
            end
            return s
        end)(), nextStep = 1 })) do
            local a = Cafe.Action(g.actionId)
            names[#names + 1] = (a and a.name or "?") .. (g.count > 1 and (" " .. TIMES .. g.count) or "")
        end
        lines[#lines + 1] = { table.concat(names, ", "), C.mid, true }
    end
    if d.kind == "P" then
        -- CAFQ has no price (it depends on the customer's level): the ticket's tipHintCopper shows it once taken
        lines[#lines + 1] = { "A player's order: a wage and their tip for you.", C.teal, true }
    end
    if d.needLevel and d.needLevel > 0 then
        lines[#lines + 1] = { "Needs barista level " .. d.needLevel .. ".", C.red }
    elseif d.state == "T" then
        lines[#lines + 1] = { "Taken by " .. U.Safe(d.takenBy or "a barista"), C.dim }
    elseif d.state == "H" then
        lines[#lines + 1] = { "The house is making it.", C.dim }
    else
        local at = S.cafeState and S.cafeState.station == "V"
        lines[#lines + 1] = { at and "Click to take this order." or "Click to choose it for Take Order at the counter.", C.mute,
            true }
    end
    UI.ShowTooltip(row, lines)
end

-- (rows stay as they are while in use: a CAFQ or CAFST mid-click never hides the row under the mouse, Cafe.StablePool)
qf.pool = Cafe.StablePool(function()
    local r = CreateFrame("Button", nil, qf)
    r:SetSize(QW - 16, Hud.QUEUE_ROW)
    r:RegisterForClicks("LeftButtonUp")
    r:SetHighlightTexture(Hud.HIGHLIGHT, "ADD")
    r.icon = UI.Icon(r, 24)
    r.icon:SetPoint("TOPLEFT", r, "TOPLEFT", 4, -4)
    r.customer = UI.Text(r, 12, C.text)
    r.customer:SetPoint("TOPLEFT", r, "TOPLEFT", Hud.QUEUE_TEXT_X, -3)
    UI.OneLine(r.customer, 110)
    r.drink = UI.Text(r, 11, C.gold)
    r.drink:SetPoint("TOPLEFT", r, "TOPLEFT", Hud.QUEUE_TEXT_X, -18)
    UI.OneLine(r.drink, 130)
    r.markIcon = r:CreateTexture(nil, "ARTWORK")
    r.markIcon:SetSize(12, 12)
    r.markIcon:SetPoint("TOPLEFT", r, "TOPLEFT", 34, -32)
    r.mark = UI.Text(r, 10, C.dim)
    r.mark:SetPoint("LEFT", r.markIcon, "RIGHT", 3, 0)
    r.secs = UI.Text(r, 11, C.text, "body", "RIGHT")
    r.secs:SetPoint("TOPRIGHT", r, "TOPLEFT", Hud.QUEUE_SECS_R, -4)
    r.bar = slimBar(r, 50, 5)
    r.bar:SetPoint("TOPRIGHT", r, "TOPRIGHT", -4, -20)
    -- the order under the mouse when the button went down: a refresh before the mouse-up may have moved another order
    -- into this row, and the click is for the one pressed (when it still waits)
    r:SetScript("OnMouseDown", function(self)
        self.pressedId = self.data and self.data.orderId
    end)
    r:SetScript("OnHide", function(self)
        self.pressedId = nil
    end)
    r:SetScript("OnClick", function(self)
        local d = self.data
        local pressed = self.pressedId
        self.pressedId = nil
        if pressed and d and d.orderId ~= pressed then
            d = nil
            for _, row in ipairs(S.cafeQueue and S.cafeQueue.rows or {}) do
                if row.orderId == pressed then
                    d = row
                end
            end
        end
        if not d then
            return
        end
        if d.state ~= "W" then
            return
        end
        if d.needLevel and d.needLevel > 0 then
            Cafe.Notice("That drink needs barista level " .. d.needLevel .. ".")
            return
        end
        if S.cafeState and S.cafeState.station == "V" then
            Cafe.Send("CTAKE", d.orderId)
        elseif Cafe.SelectedOrder() == d.orderId then
            Cafe.SelectOrder(nil)
        else
            Cafe.SelectOrder(d.orderId)
        end
        Hud.RefreshQueue()
    end)
    r:SetScript("OnEnter", queueTip)
    r:SetScript("OnLeave", hideTip)
    return r
end)

function Hud.RefreshQueue()
    local on = Cafe.Enabled() and (Cafe.OnShift() or Cafe.editing)
    shown(qf, on)
    if not on then
        return
    end
    local q = S.cafeQueue
    local head = "Queue"
    if q then
        head = "Queue " .. q.count .. "/" .. q.cap .. DOT .. q.baristas .. (q.baristas == 1 and " barista" or " baristas")
        if (q.more or 0) > 0 then
            head = head .. DOT .. "+" .. q.more .. " more"
        end
        if Cafe.Paused(q.cafeId) then
            head = head .. " (paused)"
        end
    end
    qf.header:SetText(head)
    qf.pool:Begin()
    local rows = q and q.rows or {}
    local sel = Cafe.SelectedOrder()
    local y = -30
    for _, d in ipairs(rows) do
        local r = qf.pool:Acquire()
        r.data = d
        r:ClearAllPoints()
        r:SetPoint("TOPLEFT", qf, "TOPLEFT", 8, y)
        local rec = Cafe.Recipe(d.recipeId)
        r.icon:SetIcon(Cafe.RecipeIcon(d.recipeId))
        UI.SetText(r.customer, d.customer or "Customer")
        -- the name runs up to 6 short of the seconds, measured at their longest (the row's full patience), so the cut
        -- never moves while they count down
        r.secs:SetText(d.state == "H" and "" or (ceil((d.patienceMaxMs or 0) / 1000) .. " s"))
        local secsW = d.state == "H" and 0 or ceil(r.secs:GetStringWidth() or 0)
        UI.OneLine(r.customer, max(60, Hud.QUEUE_SECS_R - secsW - 6 - Hud.QUEUE_TEXT_X))
        UI.SetText(r.drink, rec and rec.name or "A drink")
        r.markIcon:Show()
        r.mark:SetTextColor(UI.Rgb(C.dim))
        local mark, icon = "", nil
        if d.needLevel and d.needLevel > 0 then
            icon, mark = Hud.LOCK, "Level " .. d.needLevel
            r.mark:SetTextColor(UI.Rgb(C.red))
        elseif d.state == "T" then
            mark = "Taken by " .. (d.takenBy or "a barista")
        elseif d.state == "H" then
            mark = "The house"
        elseif d.kind == "P" then
            icon, mark = UI.IconPath("INV_Misc_Coin_01"), "Player"
        elseif d.kind == "G" then
            icon, mark = UI.IconPath(Cafe.ICONS.reward.group), "Group"
        end
        if icon then
            r.markIcon:SetTexture(icon)
            r.markIcon:SetTexCoord(icon == Hud.LOCK and 0 or 0.07, icon == Hud.LOCK and 1 or 0.93,
                icon == Hud.LOCK and 0 or 0.07, icon == Hud.LOCK and 1 or 0.93)
            r.mark:ClearAllPoints()
            r.mark:SetPoint("LEFT", r.markIcon, "RIGHT", 3, 0)
        else
            r.markIcon:Hide()
            r.mark:ClearAllPoints()
            r.mark:SetPoint("TOPLEFT", r, "TOPLEFT", 34, -32)
        end
        UI.SetText(r.mark, mark)
        shown(r.mark, mark ~= "")
        r:SetAlpha(d.state == "T" and 0.5 or 1)
        -- each row as tall as its lines: a row without a tag line leaves no empty band
        local h = mark ~= "" and Hud.QUEUE_ROW or Hud.QUEUE_ROW_SHORT
        r:SetHeight(h)
        UI.Select(r, sel == d.orderId)
        -- a tooltip on show follows the row's new order
        Cafe.RetipIfOwned(r, queueTip)
        y = y - h
    end
    qf.pool:Finish()
    shown(qf.empty, #rows == 0)
    if #rows == 0 then
        y = y - 18
    end
    qf:SetHeight(-y + 10)
    Hud.TickQueue()
end

function Hud.TickQueue()
    if not qf:IsShown() then
        return
    end
    for i = 1, qf.pool.used do
        local r = qf.pool.items[i]
        local d = r.data
        if d then
            local q = S.cafeQueue
            local paused = q and Cafe.Paused(q.cafeId)
            local leftMs = max(0, (d.patienceMs or 0) - Cafe.Elapsed(q and q.recvAt, q and q.cafeId) * 1000)
            if d.state == "H" then
                r.secs:SetText("")
                r.bar:Hide()
            else
                local frac = (d.patienceMaxMs or 0) > 0 and leftMs / d.patienceMaxMs or 0
                r.secs:SetText(ceil(leftMs / 1000) .. " s")
                r.secs:SetTextColor(UI.Rgb(paused and C.dim or C.text))
                r.bar:SetStatusBarColor(UI.Rgb(paused and C.dim or Cafe.PatienceColor(frac)))
                r.bar:SetValue(U.Clamp(frac, 0, 1))
                r.bar:Show()
            end
        end
    end
end

------------------------------------------------------------------------------------------------------
-- 4. The result banner (BleakholdCafeResult): the raid warning's word, raid stars, a sub line
------------------------------------------------------------------------------------------------------
local rs = CreateFrame("Frame", "BleakholdCafeResult", UIParent)
rs:SetSize(440, 96)
rs:SetFrameStrata("HIGH")
rs:EnableMouse(false)
rs:Hide()
Hud.result = rs
rs.word = rs:CreateFontString(nil, "OVERLAY")
rs.word:SetFont(UI.FONT_BODY, 32, "THICKOUTLINE")
rs.word:SetJustifyH("CENTER")
rs.word:SetPoint("TOP", rs, "TOP", 0, -8)
rs.stars = stars(rs, 3, 20, "OVERLAY")
-- the sub line: the text before the tip (rs.sub), the tip in coins as the strip and the ticket draw money (rs.money),
-- the text after it (rs.sub2); the three centred together
rs.sub = UI.Text(rs, 14, C.text, "body", "LEFT")
rs.money = Cafe.MoneyFrame(rs, 14)
rs.sub2 = UI.Text(rs, 14, C.text, "body", "LEFT")
Hud.SUB_Y = -76                    -- the sub line's middle, from the banner's top, under the stars
Hud.SUB_Y_BARE = -52               -- with no stars (Ruined!, Customer Left): right under the word
Hud.NOTE_PITCH = 18                -- the note lines under the sub line (what a ruin costs, a cap reached)
rs.notes = {}
for i = 1, 2 do
    rs.notes[i] = UI.Text(rs, 12, C.dim, "body", "CENTER")
    rs.notes[i]:Hide()
end

Hud.STARS = { P = 3, G = 2, S = 1 }
Hud.SOUNDS = { P = "igQuestListComplete", G = "igCharacterInfoOpen", R = "igQuestLogAbandonQuest",
    L = "igQuestLogAbandonQuest" }
Hud.LEVEL_UP_SOUND = "LEVELUPSOUND"   -- SoundEntries' level-up jingle (PlaySound ignores an unknown name)

-- The sub line, centred: pre, then copper in coins (none when nil or 0), then post; its middle at y (Hud.SUB_Y).
function Hud.SetSubLine(pre, copper, post, y)
    pre, post = pre or "", post or ""
    y = y or Hud.SUB_Y
    local coins = (copper or 0) > 0
    rs.sub:SetText(pre)
    rs.sub2:SetText(coins and post or "")
    shown(rs.money, coins)
    shown(rs.sub2, coins and post ~= "")
    local w1 = pre ~= "" and ceil(rs.sub:GetStringWidth() or 0) or 0
    local wm, w2 = 0, 0
    if coins then
        rs.money:SetCopper(copper)
        wm = rs.money:GetWidth()
        w2 = post ~= "" and ceil(rs.sub2:GetStringWidth() or 0) or 0
    end
    local gap1 = (w1 > 0 and coins) and 1 or 0
    local gap2 = (coins and w2 > 0) and 4 or 0
    local x = -floor((w1 + gap1 + wm + gap2 + w2) / 2 + 0.5)
    rs.sub:ClearAllPoints()
    rs.sub:SetPoint("LEFT", rs, "TOP", x, y)
    rs.money:ClearAllPoints()
    rs.money:SetPoint("LEFT", rs, "TOP", x + w1 + gap1, y)
    rs.sub2:ClearAllPoints()
    rs.sub2:SetPoint("LEFT", rs, "TOP", x + w1 + gap1 + wm + gap2, y)
end

-- Show the banner: word in its colour, n stars, the sub line (text, or text, a tip in copper and the text after it),
-- and up to two note lines under it (notes: a list of { text, color } or strings).
function Hud.Banner(word, color, n, sub, copper, post, notes)
    rs.word:SetText(word)
    rs.word:SetTextColor(UI.Rgb(color))
    for i, s in ipairs(rs.stars) do
        s:ClearAllPoints()
        s:SetPoint("TOP", rs, "TOP", (i - (n + 1) / 2) * 24, -44)
        shown(s, i <= n)
    end
    local subY = n > 0 and Hud.SUB_Y or Hud.SUB_Y_BARE
    Hud.SetSubLine(sub, copper, post, subY)
    for i, fs in ipairs(rs.notes) do
        local note = notes and notes[i]
        local text = type(note) == "table" and note[1] or note
        if text and text ~= "" then
            fs:SetText(text)
            UI.SetColor(fs, type(note) == "table" and note[2] or C.dim)
            fs:ClearAllPoints()
            fs:SetPoint("CENTER", rs, "TOP", 0, subY - i * Hud.NOTE_PITCH)
            fs:Show()
        else
            fs:SetText("")
            fs:Hide()
        end
    end
    rs.shownAt = GetTime()
    rs:SetAlpha(Cafe.Motion() and 0 or 1)
    rs:Show()
    Hud.TickBanner()
end

function Hud.TickBanner()
    if not rs:IsShown() or not rs.shownAt then
        return
    end
    local t = GetTime() - rs.shownAt
    local base = Cafe.Option("cafeScale")
    if t >= Hud.RESULT_IN + Hud.RESULT_HOLD + Hud.RESULT_OUT then
        rs:Hide()
        rs:SetScale(base)
        return
    end
    local a
    if t < Hud.RESULT_IN then
        a = t / Hud.RESULT_IN
    elseif t < Hud.RESULT_IN + Hud.RESULT_HOLD then
        a = 1
    else
        a = 1 - (t - Hud.RESULT_IN - Hud.RESULT_HOLD) / Hud.RESULT_OUT
    end
    rs:SetAlpha(U.Clamp(a, 0, 1))
    -- the pop as it comes in (none with motion off)
    if Cafe.Motion() and t < Hud.RESULT_IN then
        rs:SetScale(base * (1 + 0.25 * (1 - t / Hud.RESULT_IN)))
    else
        rs:SetScale(base)
    end
end

-- a level-up comes with the server's TOAST (target cafe); the client's own only when that one does not come
local lastCafeToast = -100
-- [ticketId] = the ruins (CAFEV X) of that ticket this shift
local ruins = {}
Hud.ruins = ruins
ns.On("TOAST", function(d)
    if d and d.target == "cafe" then
        lastCafeToast = GetTime()
    end
end)

-- A ticket closed as L (CAFRES): an NPC's complaint is speech, in quotes. A player's order has no speech, only the
-- server's system line, and there L also means the house took the order over (the barista was too slow or ruined it
-- twice: the customer still waits and the owner finishes it), it was cancelled, or the customer is gone. The ticket is
-- still in S.cafeTickets when its CAFRES comes (CAFT follows); its kind tells which.
Hud.LEFT_WORDS = { taken = { "Taken Over", C.orange }, cancelled = { "Order Cancelled", C.mute } }
-- the server's own lines on a ticket it closes (the customer gone, the order cancelled, the café closing): plain text,
-- never in quotes as a customer's words
Hud.SYSTEM_LINES = { ["The customer has gone."] = true, ["The order was cancelled."] = true }
function Hud.LeftText(res)
    local word, color = Cafe.QualityText("L")
    local line = res.line ~= "" and res.line or nil
    local t = Cafe.Ticket(res.ticketId)
    if not (t and t.kind == "P") then
        if line and not Hud.SYSTEM_LINES[line] then
            return word, color, "\"" .. U.Safe(line) .. "\""
        end
        return word, color, line and U.Safe(line) or "The customer has gone."
    end
    local low = (line or ""):lower()
    if low:find("house", 1, true) then
        local cafe = Cafe.Cafe(Cafe.CafeId())
        local customer = res.customer ~= "" and res.customer or t.customer
        local w = Hud.LEFT_WORDS.taken
        return w[1], w[2], U.Safe(cafe and cafe.ownerName or "The owner") .. " is finishing "
            .. (customer and customer ~= "" and (U.Safe(customer) .. "'s") or "the") .. " order."
    elseif low:find("cancel", 1, true) then
        local w = Hud.LEFT_WORDS.cancelled
        return w[1], w[2], line and U.Safe(line) or "The order was cancelled."
    end
    return word, color, line and U.Safe(line) or "The customer has gone."
end

-- The XP of a drink result (CAFRES xp, xpCapped: what the cap took). In the half-rate band the server credits half of
-- what the drink earned (the other half, give or take the odd point it rounds over the day, is xpCapped): "+13 XP (half
-- rate)". A drink the cap cut deeper names the cut; one that earned nothing more reads "Daily XP cap reached".
function Hud.ResultXpText(xp, capped)
    xp, capped = xp or 0, capped or 0
    if xp > 0 and capped > 0 then
        if capped <= xp + 1 then
            return "+" .. xp .. " XP (half rate)"
        end
        return "+" .. xp .. " XP (-" .. capped .. " from the daily cap)"
    elseif xp > 0 then
        return "+" .. xp .. " XP"
    elseif capped > 0 then
        return "Daily XP cap reached"
    end
end

ns.On("CAFE_RESULT", function(res)
    if not Cafe.Enabled() then
        return
    end
    local word, color = Cafe.QualityText(res.quality)
    -- before and after the money ("+27 XP · +", the coins, "tip · +22 pts · Streak ×4"); the money in coins, as on the
    -- strip. A player's order pays the barista's wage and the customer's tip together: "pay", never "tip".
    local pre, post, notes = {}, {}, {}
    local tip = res.quality ~= "L" and (res.tipCopper or 0) > 0 and res.tipCopper or nil
    local t = Cafe.Ticket(res.ticketId)
    local player = t and t.kind == "P"
    if res.quality == "L" then
        word, color, pre[1] = Hud.LeftText(res)
        ruins[res.ticketId or 0] = nil
    else
        local xpText = Hud.ResultXpText(res.xp, res.xpCapped)
        if xpText then
            pre[#pre + 1] = xpText
        end
        if tip then
            post[1] = player and "pay" or "tip"
        end
    end
    local after = tip and post or pre
    if res.quality ~= "L" and (res.points or 0) > 0 then
        after[#after + 1] = "+" .. U.Commas(res.points) .. " pts"
    end
    if (res.streak or 0) > 0 and res.quality == "P" then
        after[#after + 1] = "Streak " .. TIMES .. res.streak
    end
    if res.levelUp == 1 then
        after[#after + 1] = "Barista level " .. (res.level or "up") .. "!"
    end
    -- what a cap took: no NPC tip, no points (today's caps, CAFST D)
    if res.quality ~= "L" then
        local day = S.cafeState and S.cafeState.day
        if not tip and not player and Hud.TipCapReached(day) then
            notes[#notes + 1] = "No tip: the daily tip cap is reached"
        end
        if (res.points or 0) == 0 and Hud.PointsCapReached(day) then
            notes[#notes + 1] = "No Caf\195\169 Points: today's cap is reached"
        end
    end
    local preText = table.concat(pre, DOT)
    if tip then
        preText = (preText ~= "" and (preText .. DOT) or "") .. "+"
    end
    Hud.Banner(word .. ((res.quality == "P" or res.quality == "R") and "!" or ""), color, Hud.STARS[res.quality] or 0,
        preText, tip, table.concat(post, DOT), notes)
    if Hud.SOUNDS[res.quality] then
        Cafe.Sound(Hud.SOUNDS[res.quality])
    end
    if res.levelUp == 1 then
        Cafe.Sound(Hud.LEVEL_UP_SOUND)
        local at = GetTime()
        ns.After(1.5, function()
            if lastCafeToast < at - 1.5 and ns.Toast then
                ns.Toast.Push({ kicker = "Bleakhold", title = "Barista level " .. (res.level or ""), target = "cafe" })
            end
        end)
    end
end)

-- A ruin (CAFEV X) sends the drink back to step 1 and ends the Perfect streak. A player's order goes to the house on its
-- second ruin (Order.MaxRuins, 2 by default: the ticket then closes as Taken Over, no XP, no pay), so its first ruin
-- says so; the ruins are counted here per ticket.
Hud.RUINED_SUB = "Wrong step: the drink starts again from step 1."
Hud.STREAK_ENDS = "Your Perfect streak ends."
function Hud.RuinedNotes(t, n)
    local notes = { Hud.STREAK_ENDS }
    if t and t.kind == "P" and n == 1 then
        local cafe = Cafe.Cafe(Cafe.CafeId())
        notes[2] = { "One more ruin and " .. U.Safe(cafe and cafe.ownerName or "the owner") .. " takes this order over.",
            C.orange }
    end
    return notes
end

ns.On("CAFE_STEP", function(cs)
    if cs.event == "X" and Cafe.OnShift() then
        local id = cs.ticketId or 0
        ruins[id] = (ruins[id] or 0) + 1
        Hud.Banner("Ruined!", C.red, 0, Hud.RUINED_SUB, nil, nil, Hud.RuinedNotes(Cafe.Ticket(id), ruins[id]))
        Cafe.Sound("igQuestLogAbandonQuest")
    end
end)

------------------------------------------------------------------------------------------------------
-- 5. The buff chips (BleakholdCafeBuffs): as the stock BuffFrame, in Stormwind and Orgrimmar
------------------------------------------------------------------------------------------------------
local bf = CreateFrame("Frame", "BleakholdCafeBuffs", UIParent)
bf:SetSize(200, 52)
bf:SetFrameStrata("MEDIUM")
bf:Hide()
Hud.buffs = bf
Hud.BUFFS = {
    { key = "coffeeSec", family = "C" }, { key = "teaSec", family = "T" }, { key = "shakeSec", family = "M" },
}
-- (coffee and tea both work only where the server's RewardPlaceOk holds: no battleground, arena or battlefield zone)
Hud.BUFF_TEXT = {
    C = "+5% XP from kills and quests. Counts as Well Fed (does not add to food). Not in battlegrounds, arenas or "
        .. "Wintergrasp.",
    T = "+5% reputation from kills and quests. Not in battlegrounds, arenas or Wintergrasp.",
    M = "+15% run speed while resting in a city or inn, out of combat and not flagged.",
}
bf.chips = {}
for i, d in ipairs(Hud.BUFFS) do
    local c = CreateFrame("Frame", nil, bf)
    c:SetSize(60, 52)
    c:EnableMouse(true)
    c.icon = c:CreateTexture(nil, "ARTWORK")
    c.icon:SetSize(30, 30)
    c.icon:SetPoint("TOP", c, "TOP", 0, 0)
    c.time = UI.Text(c, 10, C.gold, "body", "CENTER")
    c.time:SetPoint("TOP", c.icon, "BOTTOM", 0, -2)
    c.extra = UI.Text(c, 10, C.teal, "body", "CENTER")
    c.extra:SetPoint("TOP", c.time, "BOTTOM", 0, -1)
    c.def = d
    c:SetScript("OnEnter", function(self)
        local fam = self.def.family
        local fd = ns.CafeData.families[fam] or {}
        local lines = { (fd.buff or Cafe.FamilyName(fam)) .. " (" .. Cafe.FamilyName(fam):lower() .. ")" }
        local b = S.cafeBuffs
        if fam == "C" and b and b.coffeeCounts == 0 then
            lines[#lines + 1] = { Cafe.NoEffectText("C") .. ".", C.red, true }
        else
            lines[#lines + 1] = { Hud.BUFF_TEXT[fam], C.text, true }
        end
        if fam == "M" and b then
            lines[#lines + 1] = b.shakeActive == 1 and { "Speed on", C.teal } or { "Speed off here", C.mute }
        end
        local left = Cafe.Left(b, self.def.key)
        if left then
            lines[#lines + 1] = { U.Clock(left) .. " left", C.dim }
        end
        UI.ShowTooltip(self, lines)
    end)
    c:SetScript("OnLeave", hideTip)
    c:Hide()
    bf.chips[i] = c
end

local inCombat = false
ns.RegisterEvent("PLAYER_REGEN_DISABLED", function()
    inCombat = true
    Hud.RefreshBuffs()
end)
ns.RegisterEvent("PLAYER_REGEN_ENABLED", function()
    inCombat = false
    Hud.RefreshBuffs()
end)

-- in Stormwind or Orgrimmar, whatever the client's language (Cafe.InCafeCity)
function Hud.InCity()
    return Cafe.InCafeCity(nil)
end

-- Unless moved, the buffs sit 6 under whatever shows at the top: the strip with its lines (warnings, the Rush, the
-- patch notice; strip.blockH), else the order chip; with neither, at TOP 0,-36.
Hud.BUFFS_GAP = 6
function Hud.BuffsAnchor(f)
    if strip:IsShown() then
        f:SetPoint("TOP", strip, "TOP", 0, -((strip.blockH or strip:GetHeight()) + Hud.BUFFS_GAP))
        return true
    elseif Hud.chip and Hud.chip:IsShown() then
        f:SetPoint("TOP", Hud.chip, "BOTTOM", 0, -Hud.BUFFS_GAP)
        return true
    end
end

function Hud.AnchorBuffs()
    local p = Hud.buffsPlace
    if p and bf:IsShown() and not p.Saved() then
        p.Anchor()
    end
end

local function cafeWindowOpen()
    local w, m = UI.windows.BleakholdCafeFrame, UI.windows.BleakholdCafeMenu
    return (w and w.IsVisible and w:IsVisible()) or (m and m.IsVisible and m:IsVisible()) or false
end

function Hud.RefreshBuffs()
    local b = S.cafeBuffs
    -- the live state too: after a /reload in combat no PLAYER_REGEN_DISABLED comes
    local fighting = inCombat or (UnitAffectingCombat and UnitAffectingCombat("player")) and true or false
    local on = Cafe.Enabled() and ((b ~= nil and not fighting and (Hud.InCity() or cafeWindowOpen())) or Cafe.editing)
    shown(bf, on and true or false)
    if not on then
        return
    end
    local x = 0
    for _, c in ipairs(bf.chips) do
        local left = Cafe.Left(b, c.def.key)
        if left and left > 0 then
            c.icon:SetTexture(Cafe.IconPath("family", c.def.family))
            c.time:SetText(Cafe.ShortTime(left))
            if c.def.family == "M" then
                if b.shakeActive == 1 then
                    c.extra:SetText("Speed on")
                    UI.SetColor(c.extra, C.teal)
                else
                    c.extra:SetText("Speed off here")
                    UI.SetColor(c.extra, C.mute)
                end
                c.extra:Show()
            else
                c.extra:Hide()
            end
            c.icon:SetDesaturated(c.def.family == "C" and b.coffeeCounts == 0)
            c:ClearAllPoints()
            c:SetPoint("TOPLEFT", bf, "TOPLEFT", x, 0)
            x = x + 64
            c:Show()
        else
            c:Hide()
        end
    end
    bf:SetWidth(max(60, x - 4))
    Hud.AnchorBuffs()
end

------------------------------------------------------------------------------------------------------
-- 6. The order chip (BleakholdCafeOrderChip): a customer's order, at the strip's spot
------------------------------------------------------------------------------------------------------
Hud.CHIP_W = 340
Hud.CHIP_H = 50
Hud.CHIP_H_MADE = 74               -- with the cast bar: its frame 8 clear of the bottom edge, as the icon's margin
Hud.CHIP_TEXT_X, Hud.CHIP_TEXT_W = 46, 284
Hud.CHIP_STUD = UI.TIMER_OUT - 20  -- how far the cast bar frame's studs reach out of the bar
local oc = CreateFrame("Frame", "BleakholdCafeOrderChip", UIParent)
oc:SetSize(Hud.CHIP_W, Hud.CHIP_H)
oc:SetFrameStrata("MEDIUM")
UI.Backdrop(oc, C.panel, C.border, nil, "panel")
oc:EnableMouse(true)
oc:Hide()
Hud.chip = oc
oc.icon = UI.Icon(oc, 28)
oc.icon:SetPoint("TOPLEFT", oc, "TOPLEFT", 10, -10)
oc.name = UI.Text(oc, 12, C.gold)
oc.name:SetPoint("TOPLEFT", oc, "TOPLEFT", Hud.CHIP_TEXT_X, -9)
UI.OneLine(oc.name, 186)
oc.status = UI.Text(oc, 11, C.text)
oc.status:SetPoint("TOPLEFT", oc, "TOPLEFT", Hud.CHIP_TEXT_X, -25)
UI.OneLine(oc.status, Hud.CHIP_TEXT_W)
-- ready (R): how to pick it up, a line under the status
Hud.CHIP_H_HINT = 62
oc.hint = UI.Text(oc, 10, C.teal)
oc.hint:SetPoint("TOPLEFT", oc, "TOPLEFT", Hud.CHIP_TEXT_X, -40)
UI.OneLine(oc.hint, Hud.CHIP_TEXT_W)
oc.hint:Hide()
-- the steps on a cast bar across the text column: its studs end where the status line's room ends, either side.
-- (The field before the number: this late in the file the client's Lua gets "2 * Hud.CHIP_STUD" wrong, as
-- CHIP_STUD * CHIP_STUD, once a field name's constant no longer fits an RK operand.)
oc.bar = UI.TimerBar(oc, Hud.CHIP_TEXT_W - Hud.CHIP_STUD * 2, UI.BAR_GOLD)
oc.bar:SetPoint("TOPLEFT", oc, "TOPLEFT", Hud.CHIP_TEXT_X + Hud.CHIP_STUD, -46)
oc.bar.text:SetFont(UI.FONT_BODY, 10, "")
oc.cancel = UI.Button(oc, 90, 20, "Cancel Order", "red", 10)
oc.cancel:SetPoint("TOPRIGHT", oc, "TOPRIGHT", -8, -8)
oc.cancel:SetScript("OnClick", function()
    Cafe.CancelOrder()
end)
oc.cancel.tooltip = function()
    return { "Cancel Order", { "Your money comes back in full.", C.mid } }
end
oc:SetScript("OnMouseUp", function()
    UI.Open("cafemenu")
end)
Hud.PICKUP_HINT = "Walk to the counter or sit at a caf\195\169 table to pick it up."
oc:SetScript("OnEnter", function(self)
    local lines = { "Your caf\195\169 order" }
    local o = S.cafeOrder
    if o and Cafe.Paused(o.cafeId) then
        if o.state == "R" then
            lines[#lines + 1] = { "Danger nearby: the caf\195\169 has paused, but your pickup's time keeps running.",
                C.red, true }
        else
            lines[#lines + 1] = { "Danger nearby: the caf\195\169 has paused, and its clocks stand still.", C.red,
                true }
        end
    end
    lines[#lines + 1] = { "Click to open the menu.", C.mute }
    UI.ShowTooltip(self, lines)
end)
oc:SetScript("OnLeave", hideTip)

Hud.ORDER_DONE_HOLD = 3          -- s "Delivered!" stays
Hud.ORDER_END_HOLD = 5           -- s a cancelled or expired order's line stays
local readySoundFor

function Hud.OrderStatus(o)
    local s = o.state
    -- the house's clock stands still while the café is paused (CAFE open 2); the pickup's runs on, as the server's
    local paused = Cafe.OrderPausedText(o)
    if s == "Q" then
        return "In queue #" .. (o.position or 1)
    elseif s == "M" then
        return "Being made by " .. U.Safe(o.barista or "a barista") .. " (" .. o.nextStep .. "/" .. o.stepCount .. ")"
    elseif s == "H" then
        return "The house is making it (~" .. ceil(Cafe.OrderLeft(o) or 0) .. " s)" .. paused
    elseif s == "F" then
        local cafe = Cafe.Cafe(o.cafeId)
        return "Taking too long: " .. U.Safe(cafe and cafe.owner or "the owner") .. " is finishing it"
    elseif s == "R" then
        return "Ready at the counter" .. DOT .. U.Clock(ceil(Cafe.OrderLeft(o) or 0))
    elseif s == "D" then
        return "Delivered!"
    elseif s == "X" then
        return "Order cancelled: your money is back."
    elseif s == "E" then
        return "Not picked up in time: the house's share came back."
    end
    return ""
end

function Hud.RefreshChip()
    local o = S.cafeOrder
    local on = Cafe.Enabled() and not Cafe.OnShift() and o ~= nil
    if on and (o.state == "D" or o.state == "X" or o.state == "E") then
        local hold = o.state == "D" and Hud.ORDER_DONE_HOLD or Hud.ORDER_END_HOLD
        on = GetTime() - o.recvAt < hold
    end
    if Cafe.editing and Cafe.Enabled() and not Cafe.OnShift() then
        on = true
    end
    shown(oc, on and true or false)
    if not on then
        Hud.AnchorBuffs()
        return
    end
    if not o then
        oc.name:SetText("Your caf\195\169 order")
        oc.status:SetText("No order")
        oc.bar:Hide()
        oc.hint:Hide()
        oc.cancel:Hide()
        oc:SetHeight(Hud.CHIP_H)
        Hud.AnchorBuffs()
        return
    end
    oc.icon:SetIcon(Cafe.RecipeIcon(o.recipeId))
    UI.SetText(oc.name, Cafe.RecipeName(o.recipeId))
    oc.status:SetText(Hud.OrderStatus(o))
    UI.SetColor(oc.status, (o.state == "R" or o.state == "D") and C.teal or ((o.state == "X" or o.state == "E") and C.dim
        or C.text))
    oc.hint:Hide()
    if o.state == "M" and o.stepCount > 0 then
        oc.bar:SetProgress(o.nextStep / o.stepCount, o.nextStep .. " / " .. o.stepCount)
        oc.bar:Show()
        oc:SetHeight(Hud.CHIP_H_MADE)
    elseif o.state == "R" then
        oc.bar:Hide()
        oc.hint:SetText(Hud.PICKUP_HINT)
        oc.hint:Show()
        oc:SetHeight(Hud.CHIP_H_HINT)
    else
        oc.bar:Hide()
        oc:SetHeight(Hud.CHIP_H)
    end
    shown(oc.cancel, o.state == "Q" or o.state == "F")
    if o.state == "R" and readySoundFor ~= o.orderId then
        readySoundFor = o.orderId
        Cafe.Sound("igQuestListComplete")
    end
    Hud.AnchorBuffs()
end

------------------------------------------------------------------------------------------------------
-- 7. At the bar (BleakholdCafeAtBar): who works at the bar near the player (the player's own row aside)
------------------------------------------------------------------------------------------------------
Hud.AT_W, Hud.AT_ROW = 280, 20
Hud.AT_TEXT_X = 20                 -- the name starts after the 16 px icon
Hud.AT_BAR_X = 178                 -- the bar's left
Hud.AT_ACTION_R = Hud.AT_BAR_X - 14 -- the action's column ends here, clear of the bar's border (its studs reach left)
Hud.AT_GAP = 8                     -- at least this between the name and the action
local ab = CreateFrame("Frame", "BleakholdCafeAtBar", UIParent)
ab:SetSize(Hud.AT_W, 40)
ab:SetFrameStrata("MEDIUM")
ab:Hide()
Hud.atbar = ab
ab.title = UI.Text(ab, 12, C.gold)
ab.title:SetPoint("TOPLEFT", ab, "TOPLEFT", 0, 0)
ab.title:SetText("At the bar")
ab.rows = {}
for i = 1, 6 do
    local r = CreateFrame("Frame", nil, ab)
    r:SetSize(Hud.AT_W, Hud.AT_ROW)
    r:SetPoint("TOPLEFT", ab, "TOPLEFT", 0, -16 - (i - 1) * Hud.AT_ROW)
    r.icon = UI.Icon(r, 16)
    r.icon:SetPoint("LEFT", r, "LEFT", 0, 0)
    -- the name (cut when long), then the action in its own column against the bar, always in full
    r.who = UI.Text(r, 11, C.text)
    r.who:SetPoint("LEFT", r, "LEFT", Hud.AT_TEXT_X, 0)
    UI.OneLine(r.who, 80)
    r.text = UI.Text(r, 11, Hud.OBJECTIVE, "body", "RIGHT")
    r.text:SetPoint("RIGHT", r, "LEFT", Hud.AT_ACTION_R, 0)
    r.bar = smallCastBar(r, 72)
    r.bar:SetPoint("LEFT", r, "LEFT", Hud.AT_BAR_X, 0)
    r.count = UI.Text(r, 10, C.dim, "body", "RIGHT")
    r.count:SetPoint("RIGHT", r, "RIGHT", 0, 0)
    r:Hide()
    ab.rows[i] = r
end

-- The action keeps its whole width (cut only if it alone cannot fit); the name gets the rest, at least 40.
function Hud.LayoutAtBarRow(r, name, action)
    local room = Hud.AT_ACTION_R - Hud.AT_TEXT_X
    UI.SetText(r.text, action)
    -- measured whole (the row's last action left its box on it)
    local aw = min(ceil(Cafe.FullWidth(r.text)) + 1, room - 40 - Hud.AT_GAP)
    UI.OneLine(r.text, aw)
    UI.SetText(r.who, name)
    UI.OneLine(r.who, room - aw - Hud.AT_GAP)
end

-- the list near the player: their café's, else any café's
local function atBarData()
    local mine = S.cafeAtBar[Cafe.MyCafe()]
    if mine then
        return mine
    end
    for _, a in pairs(S.cafeAtBar) do
        return a
    end
end

-- The server sends CAFAT only within 30 yd: a player who walks away never gets the "cafeId, 0" that clears the list, so
-- a row ends here once its step is surely over (a timed step's bar runs out at durMs + 300 ms at the latest).
Hud.AT_EXPIRE_MS = 1000
function Hud.AtBarLive(d, a, now)
    local ran = (d.startedAgoMs or 0) + ((now or GetTime()) - (a and a.recvAt or now or GetTime())) * 1000
    return ran <= (d.durMs or 0) + Hud.AT_EXPIRE_MS
end

function Hud.AtBarRows()
    local a = atBarData()
    local me = ns.PlayerName()
    local now = GetTime()
    local out = {}
    for _, r in ipairs(a and a.rows or {}) do
        if r.name ~= me and Hud.AtBarLive(r, a, now) then
            out[#out + 1] = r
        end
    end
    return out, a
end

-- For bystanders and customers (spec 4.6 item 8): a barista on shift has the queue there, and the list would sit on it.
function Hud.RefreshAtBar()
    local rows, a = Hud.AtBarRows()
    local on = Cafe.Enabled() and a ~= nil and not Cafe.OnShift()
    if on and #rows == 0 then
        -- it hides a second after the last one ends
        on = GetTime() - (a.recvAt or 0) < 1
    end
    if Cafe.editing and Cafe.Enabled() then
        on = true
    end
    shown(ab, on and true or false)
    if not on then
        return
    end
    for i, r in ipairs(ab.rows) do
        local d = rows[i]
        if d then
            r.data = d
            local act = Cafe.Action(d.actionId)
            r.icon:SetIcon(Cafe.Icon("action", d.actionId))
            Hud.LayoutAtBarRow(r, d.name or "?", act and act.name or "a step")
            if d.kind == "H" then
                r.bar:SetStatusBarColor(0, 1, 0)
            else
                r.bar:SetStatusBarColor(1, 0.7, 0)
            end
            r.count:SetText(d.stepIndex and d.stepCount and (d.stepIndex .. "/" .. d.stepCount) or "")
            r:Show()
        else
            r.data = nil
            r:Hide()
        end
    end
    ab:SetHeight(16 + max(1, #rows) * Hud.AT_ROW)
    Hud.TickAtBar()
end

function Hud.TickAtBar()
    if not ab:IsShown() then
        return
    end
    local a = atBarData()
    local now = GetTime()
    for _, r in ipairs(ab.rows) do
        local d = r.data
        if d and r:IsShown() then
            local ran = (d.startedAgoMs or 0) + (now - (a and a.recvAt or now)) * 1000
            r.bar:SetFill((d.durMs or 0) > 0 and ran / d.durMs or 1)
        end
    end
end

------------------------------------------------------------------------------------------------------
-- Wiring: state messages, the ticker (timers between messages), placement
------------------------------------------------------------------------------------------------------
function Hud.Refresh()
    Hud.RefreshStrip()
    Hud.RefreshTicket()
    Hud.RefreshQueue()
    Hud.RefreshBuffs()
    Hud.RefreshChip()
    Hud.RefreshAtBar()
    if not Cafe.Enabled() then
        rs:Hide()
    end
end

local REFRESH = {
    -- a pause or a resume (open 2) greys or frees the ticket's, the queue's and the order chip's clocks
    CAFE = { Hud.RefreshStrip, Hud.RefreshTicket, Hud.RefreshQueue, Hud.RefreshChip },
    -- on or off shift: the at-the-bar list is for bystanders and customers only
    CAFST = { Hud.RefreshStrip, Hud.RefreshTicket, Hud.RefreshQueue, Hud.RefreshChip, Hud.RefreshAtBar },
    CAFQ = { Hud.RefreshQueue, Hud.RefreshTicket }, CAFT = { Hud.RefreshTicket }, CAFEV = { Hud.RefreshTicket },
    CAFO = { Hud.RefreshChip }, CAFBF = { Hud.RefreshBuffs }, CAFAT = { Hud.RefreshAtBar },
    CAFSUM = { Hud.RefreshStrip, Hud.RefreshTicket, Hud.RefreshQueue }, DEF = { Hud.Refresh },
}
ns.On("STATE", function(op)
    local list = REFRESH[op]
    if list then
        for _, fn in ipairs(list) do
            fn()
        end
    end
end)
-- a ticket gone (served, left, taken over) or the shift over: its ruins are forgotten
ns.On("STATE", function(op)
    if op == "CAFT" then
        for id in pairs(ruins) do
            if not Cafe.Ticket(id) then
                ruins[id] = nil
            end
        end
    elseif op == "CAFSUM" then
        wipe(ruins)
    end
end)
ns.On("HELLO", Hud.Refresh)
ns.On("CAFE_RESET", function()
    wipe(ruins)
    Hud.Refresh()
end)
ns.On("CAFE_SELECT", function()
    Hud.RefreshQueue()
    Hud.RefreshTicket()
end)
-- a new zone or map: the list is of a bar far away now
ns.RegisterEvent("ZONE_CHANGED_NEW_AREA", function()
    if next(S.cafeAtBar) then
        wipe(S.cafeAtBar)
        Hud.RefreshAtBar()
    end
    Hud.RefreshBuffs()
end)
ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    -- a loading screen (a map change, or a /reload in combat: no PLAYER_REGEN_DISABLED comes then)
    inCombat = (UnitAffectingCombat and UnitAffectingCombat("player")) and true or false
    if next(S.cafeAtBar) then
        wipe(S.cafeAtBar)
        Hud.RefreshAtBar()
    end
    Hud.RefreshBuffs()
end)

-- the clocks, bars and fades between messages
ns.Every(0.1, function()
    if not Cafe.Enabled() then
        if strip:IsShown() or tk:IsShown() or qf:IsShown() or bf:IsShown() or oc:IsShown() or ab:IsShown() then
            Hud.Refresh()
        end
        return
    end
    Hud.TickBanner()
    Hud.TickTicket()
    Hud.TickQueue()
    Hud.TickAtBar()
    -- the clocks and the hide-after timers of the strip, the order chip and the at-the-bar list: a few times a second
    Hud.ticks = (Hud.ticks or 0) + 1
    if Hud.ticks % 2 == 0 then
        if strip:IsShown() then
            Hud.RefreshStrip()
        end
        if oc:IsShown() or S.cafeOrder then
            Hud.RefreshChip()
        end
        if ab:IsShown() then
            Hud.RefreshAtBar()
        end
    end
    if Hud.ticks % 5 == 0 then
        Hud.RefreshBuffs()
    end
end)

Cafe.Place(strip, { point = "TOP", x = 0, y = -64, mover = "bleakhold_cafe_strip", title = "Caf\195\169: shift strip",
    refresh = Hud.RefreshStrip })
-- In a party the stock party frames (TOPLEFT 10,-160) and AddicatUI's (10,-200, down to about -560) fill the left edge
-- where the ticket and the at-the-bar list stand: their default spots move right of that column (Hud.PARTY_X) while
-- the player is in a party (not a raid: the raid frames are the player's to place).
Hud.LEFT_X, Hud.PARTY_X = 40, 230
function Hud.InParty()
    local party = GetNumPartyMembers and GetNumPartyMembers() or 0
    local raid = GetNumRaidMembers and GetNumRaidMembers() or 0
    return party > 0 and raid == 0
end

function Hud.LeftX()
    return Hud.InParty() and Hud.PARTY_X or Hud.LEFT_X
end

Hud.ticketPlace = Cafe.Place(tk, { point = "LEFT", x = Hud.LEFT_X, y = 60, mover = "bleakhold_cafe_ticket",
    title = "Caf\195\169: ticket", refresh = Hud.RefreshTicket, anchor = function(f)
        f:SetPoint("LEFT", UIParent, "LEFT", Hud.LeftX(), 60)
        return true
    end })
Cafe.Place(qf, { point = "RIGHT", x = -40, y = 40, mover = "bleakhold_cafe_queue", title = "Caf\195\169: queue",
    refresh = Hud.RefreshQueue })
Cafe.Place(rs, { point = "CENTER", x = 0, y = 150, mover = "bleakhold_cafe_result", title = "Caf\195\169: drink result" })
Hud.buffsPlace = Cafe.Place(bf, { point = "TOP", x = 0, y = -36, anchor = Hud.BuffsAnchor,
    mover = "bleakhold_cafe_buffs", title = "Caf\195\169: buffs", refresh = Hud.RefreshBuffs })
Cafe.Place(oc, { point = "TOP", x = 0, y = -64, mover = "bleakhold_cafe_order", title = "Caf\195\169: your order",
    refresh = Hud.RefreshChip })
-- the list: on the left, clear of the stock quest tracker (WatchFrame, under the minimap at the right edge), where the
-- ticket stands on shift (the list is never shown then); its top stays put as rows come and go (six rows centre it
-- about 60 under the screen's middle, the spec's LEFT 40,-60)
Hud.atbarPlace = Cafe.Place(ab, { point = "TOPLEFT", relPoint = "LEFT", x = Hud.LEFT_X, y = 8,
    mover = "bleakhold_cafe_atbar", title = "Caf\195\169: at the bar", refresh = Hud.RefreshAtBar, anchor = function(f)
        f:SetPoint("TOPLEFT", UIParent, "LEFT", Hud.LeftX(), 8)
        return true
    end })
-- joining or leaving a party moves the two (unless the player placed them)
local function partyChanged()
    Hud.ticketPlace.Anchor()
    Hud.atbarPlace.Anchor()
end
ns.RegisterEvent("PARTY_MEMBERS_CHANGED", partyChanged)
ns.RegisterEvent("RAID_ROSTER_UPDATE", partyChanged)
-- the queue's panel drags (like the camp frame); the ticket and the at-the-bar list stay click-through over the world, as
-- the stock quest tracker, and move with the editor's movers
UI.MakeMovable(qf)
