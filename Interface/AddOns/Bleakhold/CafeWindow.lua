-- Bleakhold: the café's windows (docs/BleakholdProtocol.md, section 21), in the stock World of Warcraft look of the
-- other Bleakhold windows (Widgets.lua: the dialog frame with a ring portrait, the options frame's tabs on a tooltip
-- panel, red panel buttons, quest-log rows, the achievement progress bar):
--   BleakholdCafeFrame        the café window, five tabs:
--                               Shift        your barista level and XP, today's capped XP, tips and points, the
--                                            Morning Rush, who is on shift, the café's espresso machine as a 3D
--                                            model (only with patch-4; else its seven stations in a ring), and
--                                            Start shift / End shift (CSHIFT)
--                               Recipes      the café's drinks as cards: the family icon, tier stars, the price,
--                                            the buff, the steps as icons, a lock below the barista level
--                               Leaderboard  the weekly Best Barista board of either café (LBQ C), this week or the
--                                            last, the podium as medals, your row pinned under the table
--                               Rewards      the barista level ladder, the three aprons on your own model, the two
--                                            titles and your lifetime numbers (CAFP)
--                               How it works four short sections
--   BleakholdCafeSummary      the card shown when a shift ends (CAFSUM; after the fight or the death that ended it),
--                             with the Staff Drink choice (CSTAFF)
--   BleakholdCafeModelViewer  /bh cafe model <name>: a developer's viewer for the café's M2 models (position, scale
--                             and facing to copy into ModelForge's modelFrame)
-- Openers (UI.Open): cafe (toggle; the last tab), cafeshift, caferecipes, cafeboard, caferewards, cafehelp.
-- The windows only read S.cafe* (State.lua) and ns.Cafe (Cafe.lua), and send through ns.Cafe.Send (its per-op
-- gates), except LBQ, an ordinary board request.
-- ns.CafeKit holds what this file and CafeMenu.lua share: the pieces the widget kit has no match for, built from
-- stock textures (tier stars from the raid star, the LFG lock, the faction emblem, segmented red buttons, the tab
-- strip on its panel, step icons with a stack count), and the texts both windows use.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S
local D = ns.CafeData

local floor, ceil, max, min = math.floor, math.ceil, math.max, math.min

local K = {}
ns.CafeKit = K

local CW = {}
ns.CafeWindow = CW

-- The café's helpers and state queries (Cafe.lua, loaded before this file).
local Cafe = ns.Cafe
K.Cafe = Cafe

K.SERVE = 25                    -- the Serve action: every recipe's last step
K.FAMILY_ORDER = { "C", "T", "M" }
K.FAMILY_NAMES = Cafe.FAMILY_NAMES          -- the singular, as a row's tag (Cafe.lua: the plural on tabs and filters)

------------------------------------------------------------------------------------------------------
-- Shared pieces (stock textures, no art of our own)
------------------------------------------------------------------------------------------------------
K.STAR = "Interface\\TargetingFrame\\UI-RaidTargetingIcon_1"
K.LOCK = "Interface\\LFGFrame\\UI-LFG-ICON-LOCK"
K.LOCK_TC = { 0, 0.71875, 0, 0.875 }
K.EMBLEM = { A = "Interface\\TargetingFrame\\UI-PVP-Alliance", H = "Interface\\TargetingFrame\\UI-PVP-Horde" }
K.EMBLEM_TC = { 0, 0.625, 0, 0.625 }
K.NAME_FRAME = "Interface\\QuestFrame\\UI-QuestItemNameFrame"

local function shown(f, on)
    if on then
        f:Show()
    else
        f:Hide()
    end
end

local function hideTip()
    if GameTooltip then
        GameTooltip:Hide()
    end
end
K.HideTip = hideTip

-- A tooltip on any frame: f.tip is a function answering UI.ShowTooltip lines (or nil for none).
function K.Tip(f)
    f:EnableMouse(true)
    f:SetScript("OnEnter", function(self)
        local lines = self.tip and self.tip(self)
        if lines then
            UI.ShowTooltip(self, lines)
        end
    end)
    f:SetScript("OnLeave", hideTip)
    return f
end

-- The drink's tier as up to five raid stars (TargetingFrame\UI-RaidTargetingIcon_1), size px each; f:SetCount(n).
function K.Stars(parent, size)
    local f = CreateFrame("Frame", nil, parent)
    f:SetSize(5 * (size + 1), size)
    f.stars = {}
    for i = 1, 5 do
        local t = f:CreateTexture(nil, "ARTWORK")
        t:SetTexture(K.STAR)
        t:SetSize(size, size)
        t:SetPoint("LEFT", f, "LEFT", (i - 1) * (size + 1), 0)
        f.stars[i] = t
    end
    function f:SetCount(n)
        n = U.Clamp(n or 0, 0, 5)
        for i, t in ipairs(self.stars) do
            if i <= n then t:Show() else t:Hide() end
        end
        self:SetWidth(max(1, n * (size + 1)))
        self.count = n
    end
    f:SetCount(0)
    return f
end

-- The LFG lock (LFGFrame\UI-LFG-ICON-LOCK with its stock texcoords).
function K.Lock(parent, size, layer)
    local t = parent:CreateTexture(nil, layer or "OVERLAY")
    t:SetTexture(K.LOCK)
    t:SetTexCoord(K.LOCK_TC[1], K.LOCK_TC[2], K.LOCK_TC[3], K.LOCK_TC[4])
    t:SetSize(size * 0.82, size)
    return t
end

-- The faction emblem of the target frame (UI-PVP-Alliance / -Horde, the emblem's corner of the file).
function K.Emblem(parent, size, layer)
    local t = parent:CreateTexture(nil, layer or "ARTWORK")
    t:SetSize(size, size)
    t:SetTexCoord(K.EMBLEM_TC[1], K.EMBLEM_TC[2], K.EMBLEM_TC[3], K.EMBLEM_TC[4])
    function t:SetTeam(team)
        self:SetTexture(K.EMBLEM[team] or K.EMBLEM.A)
    end
    t:SetTeam("A")
    return t
end

-- Segmented choices as the stock frames make them: red buttons side by side, the chosen one held down (tabOn).
-- defs: { { value =, label = }, ... }; onSelect(value) runs on a click. g:Select(value) marks one (no callback);
-- g.buttons, g.value.
function K.Segmented(parent, defs, w, h, onSelect, gap)
    local g = { buttons = {} }
    for i, d in ipairs(defs) do
        local b = UI.Button(parent, w, h or 22, d.label, "tab")
        b.value = d.value
        if i > 1 then
            b:SetPoint("LEFT", g.buttons[i - 1], "RIGHT", gap or 2, 0)
        end
        b:SetScript("OnClick", function(self)
            if PlaySound then
                PlaySound("igMainMenuOptionCheckBoxOn")
            end
            g:Select(self.value)
            if onSelect then
                onSelect(self.value)
            end
        end)
        g.buttons[i] = b
    end
    function g:Select(value)
        self.value = value
        for _, b in ipairs(self.buttons) do
            b:SetStyle(b.value == value and "tabOn" or "tab")
        end
    end
    return g
end

-- The options frame's tabs standing on a tooltip panel (Collections.lua's strip): returns the body panel and the
-- tab buttons (b.key); onSelect(key) runs on a click, with the stock tab sound.
-- The art (128 x 32) is see-through above its top 7 rows and outside its rims, which run 11 px in from each side: a
-- tab is TAB_H tall, so the art draws near its own 32 rows and a closed tab reads 24 tall as the stock tabs do, and as
-- wide as its label with 12 px of air between the label and each rim (PanelTemplates_TabResize), at least TAB_MIN;
-- the tabs overlap by their see-through flanks.
K.TAB_H, K.TAB_PAD, K.TAB_MIN, K.TAB_OVERLAP = 31, 48, 80, 8
K.STRIP_H = K.TAB_H - 2         -- the strip above the body: the tabs stand 2 px into its top edge

function K.TabWidth(b)
    return max(K.TAB_MIN, ceil((b.label:GetStringWidth() or 0) + K.TAB_PAD))
end

function K.TabStrip(win, defs, onSelect)
    local cw, ch = UI.ContentSize(win:GetWidth(), win:GetHeight())
    local body = UI.Box(win.content, cw, ch - K.STRIP_H, C.panel, C.border, nil, "panel")
    body:SetPoint("TOPLEFT", win.content, "TOPLEFT", 0, -K.STRIP_H)
    body:SetPoint("BOTTOMRIGHT", win.content, "BOTTOMRIGHT", 0, 0)
    local bar = CreateFrame("Frame", nil, win.content)
    bar:SetPoint("TOPLEFT", win.content, "TOPLEFT", 0, 0)
    bar:SetPoint("BOTTOMRIGHT", body, "TOPRIGHT", 0, 0)
    bar:SetFrameLevel(body:GetFrameLevel() + 5)
    local tabs = {}
    local x = 8
    for i, d in ipairs(defs) do
        local b = UI.Button(bar, 100, K.TAB_H, d.label, "strip")
        b.key = d.key
        b:SetScript("OnClick", function()
            if PlaySound then
                PlaySound("igCharacterInfoTab")
            end
            onSelect(d.key)
        end)
        local tw = K.TabWidth(b)
        b:SetWidth(tw)
        b:SetPoint("BOTTOMLEFT", body, "TOPLEFT", x, -2)
        x = x + tw - K.TAB_OVERLAP
        tabs[i] = b
    end
    return body, tabs, cw, ch - K.STRIP_H
end

-- Two amounts as the stock money frames show them, "3[g] / 18[g]" (Cafe.MoneyFrame: each amount white with its
-- coin), centred on its anchor; f:Set(a, b) lays it out.
function K.MoneyPair(parent, size)
    local f = CreateFrame("Frame", nil, parent)
    f:SetSize(1, (size or 10) + 2)
    f.a = Cafe.MoneyFrame(f, size or 10)
    f.slash = UI.Text(f, size or 10, C.text)
    f.slash:SetText("/")
    f.b = Cafe.MoneyFrame(f, size or 10)
    function f:Set(a, b)
        self.a:SetCopper(a or 0)
        self.b:SetCopper(b or 0)
        local wa, ws = self.a:GetWidth() or 0, ceil(self.slash:GetStringWidth() or 4)
        self.a:ClearAllPoints()
        self.a:SetPoint("LEFT", self, "LEFT", 0, 0)
        self.slash:ClearAllPoints()
        self.slash:SetPoint("LEFT", self, "LEFT", wa + 5, 0)
        self.b:ClearAllPoints()
        self.b:SetPoint("LEFT", self, "LEFT", wa + 5 + ws + 5, 0)
        self:SetWidth(max(1, wa + ws + 10 + (self.b:GetWidth() or 0)))
    end
    f:Set(0, 0)
    return f
end

-- A drink's name in the stock item-quality colour of its tier, as merchant and quest frames name items: tier 1
-- common (white), 2 uncommon (green), 3 rare (blue), 4 epic (purple), 5 legendary (orange).
function K.TierColor(tier)
    return UI.QUALITY[U.Clamp(tier or 1, 1, 5)] or C.text
end

-- Consecutive equal actions as one line: { { actionId =, count = }, ... } (spec 2.5 "Lines").
function K.StepGroups(steps)
    local out = {}
    for _, id in ipairs(steps or {}) do
        local last = out[#out]
        if last and last.actionId == id then
            last.count = last.count + 1
        else
            out[#out + 1] = { actionId = id, count = 1 }
        end
    end
    return out
end

-- The action's name at this café (DEF G hordeName at The Grinding Tusk).
function K.ActionName(a, cafeId)
    if not a then
        return "?"
    end
    if cafeId == 2 and a.hordeName and a.hordeName ~= "" then
        return a.hordeName
    end
    return a.name or "?"
end

-- The icon of a step: Serve shows the drink's family.
function K.StepIcon(actionId, family)
    if actionId == K.SERVE then
        return Cafe.Icon("family", family or "C")
    end
    return Cafe.Icon("action", actionId)
end

-- What a family's buff does, for the menu and the recipe cards (spec 4.6 texts). Coffee and tea work only where the
-- server's RewardPlaceOk holds: no battleground or arena map, no battlefield zone such as Wintergrasp.
K.BUFF_SHORT = { C = "+5% XP", T = "+5% reputation", M = "+15% run speed in cities" }
K.BUFF_LONG = {
    C = "+5% XP from kills and quests. Counts as Well Fed (does not add to food). Not in battlegrounds, arenas or "
        .. "Wintergrasp.",
    T = "+5% reputation from kills and quests. Not in battlegrounds, arenas or Wintergrasp.",
    M = "+15% run speed while resting in a city or inn, out of combat and not flagged.",
}
function K.BuffLine(r)
    if not r then
        return ""
    end
    local parts = { K.BUFF_SHORT[r.family] or "", (r.buffMin or 30) .. " min" }
    if r.family == "C" then
        parts[#parts + 1] = "counts as Well Fed"
    end
    return table.concat(parts, " · ")
end

-- A step's tooltip lines: the action, its station, and how to do it.
function K.StepTip(actionId, count, cafeId)
    local a = Cafe.Action(actionId)
    local st = a and Cafe.Station(a.station)
    local lines = { U.Safe(K.ActionName(a, cafeId)) .. ((count or 1) > 1 and (" ×" .. count) or "") }
    if st then
        -- the player's own key for that slot (/bh cafe keys), as the bar and the ticket name it
        local key = a.key and (" [" .. Cafe.SlotKey(a.key) .. "]") or ""
        lines[#lines + 1] = { U.Safe(st.name or "") .. key, C.dim }
    end
    if a and a.kind == "H" then
        lines[#lines + 1] = { "Timed: press the key again inside the gold.", C.text, true }
    end
    return lines
end

-- A small square step icon with its count in the corner (a stack count) and its tooltip.
function K.StepIconFrame(parent, size)
    local f = UI.Icon(parent, size)
    f.count = f:CreateFontString(nil, "OVERLAY")
    f.count:SetFont(UI.FONT_BODY, 10, "OUTLINE")
    f.count:SetTextColor(1, 1, 1)
    f.count:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", 1, 0)
    K.Tip(f)
    function f:SetStep(actionId, count, family, cafeId)
        self:SetIcon(K.StepIcon(actionId, family))
        self.count:SetText((count or 1) > 1 and ("×" .. count) or "")
        self.tip = function()
            return K.StepTip(actionId, count, cafeId)
        end
    end
    return f
end

-- The player's class colour (RAID_CLASS_COLORS), for their own row.
function K.PlayerColor()
    local _, token = UnitClass("player")
    local rc = token and RAID_CLASS_COLORS and RAID_CLASS_COLORS[token]
    if rc then
        return string.format("%02X%02X%02X", (rc.r or 1) * 255, (rc.g or 1) * 255, (rc.b or 1) * 255)
    end
    return C.text
end

-- The barista's current level (CAFST, else CAFP, else 1).
function K.BaristaLevel()
    return (S.cafeState and S.cafeState.level) or (S.cafeProfile and S.cafeProfile.level) or 1
end

-- "1,890 / 2,320" and 0..1 of a barista level (total XP, as CAFST and CAFP send it); the top level is full.
function K.LevelProgress(t)
    if not t or not t.xp then
        return 0, ""
    end
    if not t.nextLevelXp or t.nextLevelXp <= (t.levelXp or 0) then
        return 1, U.Commas(t.xp) .. " XP"
    end
    local p = (t.xp - (t.levelXp or 0)) / (t.nextLevelXp - (t.levelXp or 0))
    return U.Clamp(p, 0, 1), U.Commas(t.xp) .. " / " .. U.Commas(t.nextLevelXp)
end

-- The café's open state as words (CAFE open), and whether it is a warning.
K.OPEN_TEXT = { [0] = "Closed", [1] = "Open", [2] = "Danger nearby: the café has paused", [3] = "Not open yet",
    [4] = "Closed for safety" }

-- "m:ss" (no hours) for short countdowns, rounded up as the stock timers count.
function K.Short(sec)
    sec = max(0, ceil((sec or 0) - 1e-6))
    return string.format("%d:%02d", floor(sec / 60), sec % 60)
end

-- The Morning Rush as a line: CAFST R while on shift (its served counts), else the café's CAFE row.
function K.RushText(cafeId)
    local st = S.cafeState
    local r = st and st.onShift and st.cafeId == cafeId and st.rush or nil
    local row = S.cafes and S.cafes[cafeId]
    local src = r or row
    if not src or not src.rushState or src.rushState == 0 then
        return "No Morning Rush right now.", false
    end
    local left = Cafe.RushLeft(src, cafeId) or 0
    if src.rushState == 1 then
        return "Starts in " .. K.Short(left), false
    end
    local txt = "Live: " .. K.Short(left) .. " left"
    if r and r.rushGoal and r.rushGoal > 0 then
        txt = txt .. " · " .. (r.rushServed or 0) .. "/" .. r.rushGoal .. " served"
    end
    return txt, true
end

------------------------------------------------------------------------------------------------------
-- The café window
------------------------------------------------------------------------------------------------------
CW.W, CW.H = 860, 585
CW.tab = "shift"
CW.PAD = 18

local win = UI.Window("BleakholdCafeFrame", CW.W, CW.H, "Café", "Achievement_Profession_ChefHat")
CW.frame = win

-- the café's name with its faction emblem, at the left of the title bar
local kicker = CreateFrame("Frame", nil, win.header)
kicker:SetSize(260, 26)
kicker:SetPoint("LEFT", win.bar, "LEFT", 8, 0)
kicker.emblem = K.Emblem(kicker, 22)
kicker.emblem:SetPoint("LEFT", kicker, "LEFT", 0, 0)
kicker.name = UI.Text(kicker, 12, C.text)
kicker.name:SetPoint("LEFT", kicker.emblem, "RIGHT", 4, 0)
UI.OneLine(kicker.name, 220)
CW.kicker = kicker

-- Order a Drink: the customer's way to the menu from this window (the minimap cup, the key binding and /bh cafe open
-- it); in the title bar left of the close button, as the Activities window's Leave dungeon. Off shift only: a barista
-- on shift does not order (cafe_shift).
local orderBtn = UI.Button(win.header, 110, 22, "Order a Drink", "red", 12)
orderBtn:SetPoint("RIGHT", win.close, "LEFT", -2, 0)
orderBtn:SetFrameLevel(win.close:GetFrameLevel())
orderBtn:SetScript("OnClick", function()
    -- the menu takes this window's place (both stand in the middle of the screen)
    win:Hide()
    UI.Open("cafemenu")
end)
orderBtn.tooltip = function()
    return { "Order a Drink", { "The caf\195\169's menu: choose a drink and a tip, then order within 40 yards of the "
        .. "caf\195\169.", C.mid, true } }
end
orderBtn:Hide()
CW.orderBtn = orderBtn

CW.TABS = {
    { key = "shift", label = "Shift" },
    { key = "recipes", label = "Recipes" },
    { key = "board", label = "Leaderboard" },
    { key = "rewards", label = "Rewards" },
    { key = "help", label = "How It Works" },
}
local body, tabs, BW, BH = K.TabStrip(win, CW.TABS, function(key)
    CW.ShowTab(key)
end)
CW.body, CW.tabs, CW.BW, CW.BH = body, tabs, BW, BH
CW.pages = {}

local function newPage(key)
    local p = CreateFrame("Frame", nil, body)
    p:SetAllPoints(body)
    p:Hide()
    p.key = key
    CW.pages[key] = p
    return p
end

-- the café the window shows: the player's own (the team's café), or the one on shift
function CW.CafeId()
    return Cafe.OnShift() and Cafe.CafeId() or Cafe.MyCafe()
end

------------------------------------------------------------------------------------------------------
-- Shift
------------------------------------------------------------------------------------------------------
local PAD = CW.PAD
local shift = newPage("shift")
CW.shift = shift
local LEFT_W = 370

shift.badge = UI.Badge(shift, 64, "INV_Chest_Cloth_21")
shift.badge:SetPoint("TOPLEFT", shift, "TOPLEFT", PAD - 2, -16)
shift.level = UI.Text(shift, 22, C.gold)
shift.level:SetPoint("TOPLEFT", shift, "TOPLEFT", PAD + 78, -20)
UI.OneLine(shift.level, LEFT_W - 80)
shift.levelNote = UI.Text(shift, 11, C.dim)
shift.levelNote:SetPoint("TOPLEFT", shift.level, "BOTTOMLEFT", 0, -2)
UI.OneLine(shift.levelNote, LEFT_W - 80)
shift.xp = UI.Bar(shift, LEFT_W - 90, 14)
shift.xp:SetPoint("TOPLEFT", shift, "TOPLEFT", PAD + 83, -66)

shift.today = UI.Heading(shift, "Today")
shift.today:SetPoint("TOPLEFT", shift, "TOPLEFT", PAD, -102)
shift.rows = {}
local TODAY = {
    { key = "xp", label = "Barista XP" },
    { key = "tips", label = "NPC tips (daily cap)" },
    { key = "points", label = "Café Points" },
}
for i, d in ipairs(TODAY) do
    local y = -126 - (i - 1) * 40
    local r = {}
    r.label = UI.Label(shift, d.label, 12)
    r.label:SetPoint("TOPLEFT", shift, "TOPLEFT", PAD, y)
    r.note = UI.Text(shift, 11, C.dim, "body", "RIGHT")
    r.note:SetPoint("TOPRIGHT", shift, "TOPLEFT", PAD + LEFT_W, y)
    UI.OneLine(r.note, 220)
    -- money bars are gold, the others the achievement green
    r.bar = UI.Bar(shift, LEFT_W - 10, 14, d.key == "tips" and C.gold or nil)
    r.bar:SetPoint("TOPLEFT", shift, "TOPLEFT", PAD + 5, y - 19)
    shift.rows[d.key] = r
end
-- the tips in coins, inside their bar
shift.rows.tips.money = K.MoneyPair(shift.rows.tips.bar.border, 10)
shift.rows.tips.money:SetPoint("CENTER", shift.rows.tips.bar, "CENTER", 0, 0)

shift.rushHead = UI.Heading(shift, "Morning Rush")
shift.rushHead:SetPoint("TOPLEFT", shift, "TOPLEFT", PAD, -254)
shift.rush = UI.Text(shift, 12, C.text)
shift.rush:SetPoint("TOPLEFT", shift.rushHead, "BOTTOMLEFT", 0, -6)
UI.OneLine(shift.rush, LEFT_W)
shift.crew = UI.Text(shift, 12, C.text)
shift.crew:SetPoint("TOPLEFT", shift.rush, "BOTTOMLEFT", 0, -6)
UI.OneLine(shift.crew, LEFT_W)

-- the hero machine: a Model in a dark box (patch-4), else the seven stations in a ring on the same box. The box fills
-- the page's right side from the top down to just above the Start Shift row (CW.BUTTON_Y and the button's height,
-- then CW.STAGE_GAP), beside the whole left column.
CW.BUTTON_Y, CW.BUTTON_H, CW.STAGE_GAP = 18, 22, 12
CW.MODEL_W = 400
CW.MODEL_H = BH - 16 - CW.BUTTON_Y - CW.BUTTON_H - CW.STAGE_GAP
local stage = UI.Box(shift, CW.MODEL_W, CW.MODEL_H, C.card, C.border, nil, "edge")
stage:SetPoint("TOPRIGHT", shift, "TOPRIGHT", -PAD + 2, -16)
shift.stage = stage
local model = CreateFrame("Model", "BleakholdCafeModel", stage)
model:SetPoint("TOPLEFT", stage, "TOPLEFT", 1, -1)
model:SetPoint("BOTTOMRIGHT", stage, "BOTTOMRIGHT", -1, 1)
model:EnableMouse(true)
model:Hide()
shift.model = model
-- the labels over the model: a child frame one level up, so the model never covers them
local caption = CreateFrame("Frame", nil, stage)
caption:SetAllPoints(stage)
caption:SetFrameLevel(model:GetFrameLevel() + 1)
caption.name = UI.Text(caption, 13, C.gold)
caption.name:SetPoint("BOTTOMLEFT", caption, "BOTTOMLEFT", 12, 26)
caption.kind = UI.Text(caption, 11, C.dim)
caption.kind:SetPoint("BOTTOMLEFT", caption, "BOTTOMLEFT", 12, 10)
caption.hint = UI.Text(caption, 10, C.mute, "body", "RIGHT")
caption.hint:SetPoint("BOTTOMRIGHT", caption, "BOTTOMRIGHT", -10, 10)
caption.hint:SetText("Drag to turn")
shift.caption = caption

-- slow spin, drag to turn (Collections' model controls)
CW.SPIN = 0.25
model:SetScript("OnMouseDown", function(self)
    self.turning = true
    self.lastX = GetCursorPosition()
end)
model:SetScript("OnMouseUp", function(self)
    self.turning = false
end)
model:SetScript("OnUpdate", function(self, elapsed)
    if self.turning then
        local x = GetCursorPosition()
        if x and self.lastX then
            self:SetFacing((self:GetFacing() or 0) + (x - self.lastX) * 0.02)
            self.lastX = x
        end
    elseif Cafe.Option("cafeMotion") ~= false then
        self:SetFacing((self:GetFacing() or 0) + (elapsed or 0) * CW.SPIN)
    end
end)

local ring = CreateFrame("Frame", nil, stage)
ring:SetAllPoints(stage)
ring:Hide()
ring.title = UI.Text(ring, 14, C.gold, "body", "CENTER")
ring.title:SetPoint("CENTER", ring, "CENTER", 0, 8)
ring.sub = UI.Text(ring, 11, C.dim, "body", "CENTER")
ring.sub:SetPoint("TOP", ring.title, "BOTTOM", 0, -4)
ring.sub:SetText("Seven stations")
ring.note = UI.Text(ring, 10, C.mute, "body", "CENTER")
ring.note:SetPoint("BOTTOM", ring, "BOTTOM", 0, 8)
ring.note:SetText("The 3D view comes with the latest Bleakhold client.")
ring.stations = {}
-- the ring's radii: as wide as the box allows with the names, and as tall as the box less the note under it
CW.RING_RX, CW.RING_RY = 140, floor(CW.MODEL_H / 2) - 60
for i, letter in ipairs(D.stationOrder) do
    local a = (i - 1) / #D.stationOrder * 2 * math.pi
    local x, y = floor(math.sin(a) * CW.RING_RX + 0.5), floor(math.cos(a) * CW.RING_RY + 0.5)
    local s = UI.Icon(ring, 32, Cafe.Icon("station", letter))
    s:SetPoint("CENTER", ring, "CENTER", x, y + 14)
    s.name = UI.Text(ring, 10, C.text, "body", "CENTER")
    s.name:SetPoint("TOP", s, "BOTTOM", 0, -2)
    UI.OneLine(s.name, 110)
    s.letter = letter
    K.Tip(s)
    ring.stations[i] = s
end
shift.ring = ring

shift.rulesHead = UI.Heading(shift, "Before You Start")
shift.rulesHead:SetPoint("TOPLEFT", shift, "TOPLEFT", PAD, -334)
CW.RULES = {
    "Stand at a station and press its key; the bar shows what each key does.",
    "Timed steps: press again inside the gold.",
    "Combat ends the shift and gives you your action bar back.",
}
-- the rules stay in the left column, beside the box: a long one wraps under its own text, each follows the last
CW.RULE_W = LEFT_W - 18
shift.rules = {}
for i, text in ipairs(CW.RULES) do
    local t = UI.Para(shift, 12, C.text, CW.RULE_W)
    t:SetSpacing(2)
    if i == 1 then
        t:SetPoint("TOPLEFT", shift, "TOPLEFT", PAD + 18, -358)
    else
        t:SetPoint("TOPLEFT", shift.rules[i - 1], "BOTTOMLEFT", 0, -7)
    end
    t:SetText(text)
    local n = UI.Text(shift, 12, C.gold)
    n:SetPoint("TOPLEFT", t, "TOPLEFT", -18, 0)
    n:SetText(i .. ".")
    t.num = n
    shift.rules[i] = t
end

shift.button = UI.Button(shift, 200, CW.BUTTON_H, "Start Shift", "red")
shift.button:SetPoint("BOTTOMLEFT", shift, "BOTTOMLEFT", PAD, CW.BUTTON_Y)
shift.button:SetScript("OnClick", function()
    if Cafe.OnShift() then
        Cafe.EndShift()
    else
        Cafe.StartShift()
    end
end)
-- today's Staff Drink while it can still be claimed (CAFST flag 16), also after its shift's card was closed
shift.claim = UI.Button(shift, 160, CW.BUTTON_H, "Claim Staff Drink", "red")
shift.claim:SetPoint("LEFT", shift.button, "RIGHT", 10, 0)
shift.claim:SetScript("OnClick", function()
    CW.OpenStaffClaim()
end)
shift.claim.tooltip = function()
    return { "Staff Drink", { "A free drink of your choice after a shift, once a day.", C.mid, true } }
end
shift.claim:Hide()
shift.note = UI.Text(shift, 12, C.dim)
shift.note:SetPoint("LEFT", shift.button, "RIGHT", 14, 0)
UI.OneLine(shift.note, BW - 2 * PAD - 220)


function CW.ShowModel(cafeId)
    local m = D.models and D.models[cafeId]
    local present = Cafe.PatchPresent() and m ~= nil
    if present then
        model:Show()
        ring:Hide()
        caption:Show()
        if model.path ~= m.path then
            model:SetModel(m.path)
            model.path = m.path
            local p = m.position or { 0, 0, 0 }
            model:SetPosition(p[1] or 0, p[2] or 0, p[3] or 0)
            model:SetModelScale(m.scale or 1)
            model:SetFacing(m.facing or 0)
        end
        local st = Cafe.Station("E")
        caption.name:SetText(U.Safe(st and st.names and st.names[cafeId] or (st and st.name) or ""))
        caption.kind:SetText(U.Safe(st and st.name or ""))
    else
        model:Hide()
        caption:Hide()
        ring:Show()
        local cafe = Cafe.Cafe(cafeId)
        UI.SetText(ring.title, cafe and cafe.name or "Café")
        for _, s in ipairs(ring.stations) do
            local st = Cafe.Station(s.letter)
            s:SetIcon(Cafe.Icon("station", s.letter))
            UI.SetText(s.name, st and st.name or s.letter)
            s.tip = function()
                local lines = { U.Safe(st and st.name or s.letter) }
                if st and st.names and st.names[cafeId] then
                    lines[#lines + 1] = { U.Safe(st.names[cafeId]), C.dim }
                end
                return lines
            end
        end
    end
    shift.modelShown = present
end

-- Off shift and Tired (CAFST flag 4): rewards stay halved until tiredSec more rest; said before a shift starts.
function CW.TiredNote(st)
    if not st or st.onShift or bit.band(st.flags or 0, 4) == 0 or Cafe.Rested(st) then
        return nil
    end
    local left = Cafe.Left(st, "tiredSec")
    if left and left > 0 then
        return "Tired: barista XP and Caf\195\169 Points are halved for " .. U.Clock(ceil(left)) .. " more rest"
    end
    return "Tired: barista XP and Caf\195\169 Points are halved"
end

function shift:Refresh()
    local cafeId = CW.CafeId()
    local cafe = Cafe.Cafe(cafeId)
    local st = S.cafeState
    local onShift = Cafe.OnShift()

    if st and st.level then
        shift.level:SetText("Barista " .. st.level)
        local p, txt = K.LevelProgress(st)
        shift.xp:SetProgress(p, txt)
        if st.nextLevelXp and st.nextLevelXp > st.xp then
            shift.levelNote:SetText(U.Commas(st.nextLevelXp - st.xp) .. " XP to level " .. (st.level + 1))
        else
            shift.levelNote:SetText("The highest barista level")
        end
    else
        shift.level:SetText("Barista")
        shift.levelNote:SetText(Comm.ready and "Not a barista yet" or "Waiting for the server...")
        shift.xp:SetProgress(0, "")
    end

    local day = st and st.day
    local rows = shift.rows
    if day then
        -- dayXp is credited XP: the half band adds at most floor(dayXpHalf / 2) (Cafe.DayXpBands)
        local xp, full, halfCredit = Cafe.DayXpBands(day)
        if xp < full or full <= 0 then
            rows.xp.bar:SetProgress(full > 0 and xp / full or 0, U.Commas(xp) .. " / " .. U.Commas(full))
            rows.xp.note:SetText(halfCredit > 0 and ("then up to +" .. U.Commas(halfCredit) .. " at half rate") or "")
        elseif xp < full + halfCredit then
            rows.xp.bar:SetProgress(1, U.Commas(full) .. " / " .. U.Commas(full))
            rows.xp.note:SetText("+" .. U.Commas(xp - full) .. " of " .. U.Commas(halfCredit) .. " at half rate")
        else
            rows.xp.bar:SetProgress(1, U.Commas(full) .. " / " .. U.Commas(full))
            rows.xp.note:SetText("Daily XP cap reached")
        end
        local cap = day.dayTipsCapCopper or 0
        rows.tips.bar:SetProgress(cap > 0 and (day.dayTipsCopper or 0) / cap or 0, "")
        rows.tips.money:Set(day.dayTipsCopper or 0, cap)
        rows.tips.money:Show()
        rows.tips.note:SetText("")
        local pcap = day.dayPointsCap or 0
        rows.points.bar:SetProgress(pcap > 0 and (day.dayPoints or 0) / pcap or 0,
            U.Commas(day.dayPoints or 0) .. " / " .. U.Commas(pcap))
        local n = day.dayDrinks
        rows.points.note:SetText(n and (n .. (n == 1 and " drink today" or " drinks today")) or "")
    else
        for _, r in pairs(rows) do
            r.bar:SetProgress(0, "")
            r.note:SetText("")
        end
        rows.tips.money:Hide()
    end

    local rush, live = K.RushText(cafeId)
    shift.rush:SetText(rush)
    UI.SetColor(shift.rush, live and C.orange or C.text)
    local row = S.cafes and S.cafes[cafeId]
    if row then
        local n = (onShift and S.cafeQueue and S.cafeQueue.baristas) or row.baristas or 0
        local crew = "On shift now: " .. n .. (n == 1 and " barista" or " baristas")
        local q = row.queueLen or 0
        crew = crew .. " · " .. q .. (q == 1 and " order" or " orders") .. " in the queue"
        shift.crew:SetText(crew)
    else
        shift.crew:SetText("")
    end

    CW.ShowModel(cafeId)

    -- Start shift / End shift, and why it cannot start now
    local open = row and row.open
    local note, noteColor = "", C.dim
    if onShift then
        shift.tiredShown = false
        shift.button:SetLabel("End Shift")
        shift.button:SetActive(true)
        note = "On shift at " .. U.Safe(cafe and cafe.name or "the café")
        if st and st.shiftSec then
            note = note .. " · " .. U.Clock(st.shiftSec + GetTime() - (st.recvAt or GetTime()))
        end
    else
        shift.button:SetLabel("Start Shift")
        local blocked = open ~= nil and open ~= 1
        shift.button:SetActive(Comm.ready and not blocked)
        local tired = CW.TiredNote(st)
        shift.tiredShown = tired ~= nil
        if blocked then
            note, noteColor = K.OPEN_TEXT[open] or "Closed", open == 2 and C.red or C.dim
        elseif tired then
            note, noteColor = tired, C.orange
        elseif cafe and not Cafe.InCafeCity(cafeId) then
            note = "Go to " .. U.Safe(cafe and cafe.name or "the café") .. " to start."
        elseif cafe and cafe.ownerName then
            note = "Or talk to " .. U.Safe(cafe.ownerName) .. " at the counter."
        end
    end
    local claim = not onShift and st ~= nil and bit.band(st.flags or 0, 16) ~= 0
    shown(shift.claim, claim)
    shift.note:ClearAllPoints()
    shift.note:SetPoint("LEFT", claim and shift.claim or shift.button, "RIGHT", 14, 0)
    UI.OneLine(shift.note, BW - 2 * PAD - 220 - (claim and 170 or 0))
    shift.note:SetText(note)
    UI.SetColor(shift.note, noteColor)
end

-- the Rush countdown ticks while the page is open
shift.elapsed = 0
shift:SetScript("OnUpdate", function(self, elapsed)
    self.elapsed = self.elapsed + (elapsed or 0)
    if self.elapsed >= 1 then
        self.elapsed = 0
        local rush, live = K.RushText(CW.CafeId())
        self.rush:SetText(rush)
        UI.SetColor(self.rush, live and C.orange or C.text)
        -- the shift's clock, and the Tired rest running down off shift (once more as it ends: the note goes)
        if Cafe.OnShift() or CW.TiredNote(S.cafeState) or self.tiredShown then
            self:Refresh()
        end
    end
end)

------------------------------------------------------------------------------------------------------
-- Recipes
------------------------------------------------------------------------------------------------------
local recipes = newPage("recipes")
CW.recipes = recipes
recipes.family = "all"
recipes.filter = K.Segmented(recipes, {
    { value = "all", label = "All" }, { value = "C", label = "Coffee" }, { value = "T", label = "Tea" },
    { value = "M", label = Cafe.FAMILY_PLURAL.M },
}, 96, 22, function(value)
    recipes.family = value
    recipes:Refresh()
end)
recipes.filter.buttons[1]:SetPoint("TOPLEFT", recipes, "TOPLEFT", PAD, -14)
recipes.summary = UI.Text(recipes, 11, C.dim, "body", "RIGHT")
recipes.summary:SetPoint("TOPRIGHT", recipes, "TOPRIGHT", -PAD, -20)
UI.OneLine(recipes.summary, 360)

-- three rows of cards in view (a whole number of rows: the list scrolls by rows)
CW.CARD_W, CW.CARD_H, CW.CARD_GAP = 252, 128, 12
recipes.scroll = UI.Scroll(recipes)
recipes.scroll:SetPoint("TOPLEFT", recipes, "TOPLEFT", PAD - 4, -48)
recipes.scroll:SetSize(BW - PAD - 4, 3 * (CW.CARD_H + CW.CARD_GAP))
CW.CARD_STEPS = 8

local function recipeCard()
    local card = CreateFrame("Frame", nil, recipes.scroll.child)
    card:SetSize(CW.CARD_W, CW.CARD_H)
    UI.Backdrop(card, C.card, C.border, nil, "edge")
    card.item = UI.ItemButton(card, 36)
    card.item:SetPoint("TOPLEFT", card, "TOPLEFT", 10, -10)
    card.name = UI.Text(card, 13, C.gold)
    card.name:SetPoint("TOPLEFT", card, "TOPLEFT", 56, -10)
    UI.OneLine(card.name, CW.CARD_W - 64)
    card.stars = K.Stars(card, 12)
    card.stars:SetPoint("TOPLEFT", card, "TOPLEFT", 56, -29)
    card.lock = K.Lock(card, 14)
    card.lock:SetPoint("TOPLEFT", card, "TOPLEFT", 128, -28)
    card.need = UI.Text(card, 11, C.red)
    card.need:SetPoint("LEFT", card.lock, "RIGHT", 3, 0)
    UI.OneLine(card.need, 104)
    card.money = Cafe.MoneyFrame(card, 11)
    card.money:SetPoint("TOPLEFT", card, "TOPLEFT", 56, -47)
    card.info = UI.Text(card, 11, C.dim)
    card.info:SetPoint("LEFT", card.money, "RIGHT", 6, 0)
    UI.OneLine(card.info, 120)
    card.buff = UI.Text(card, 11, C.teal)
    card.buff:SetPoint("TOPLEFT", card, "TOPLEFT", 10, -66)
    UI.OneLine(card.buff, CW.CARD_W - 20)
    -- the quest log's title highlight under the cursor (the card's own tooltip names the drink)
    card.glow = card:CreateTexture(nil, "HIGHLIGHT")
    card.glow:SetTexture(UI.STOCK.rowHighlight)
    card.glow:SetBlendMode("ADD")
    card.glow:SetPoint("TOPLEFT", card, "TOPLEFT", 1, -1)
    card.glow:SetPoint("BOTTOMRIGHT", card, "BOTTOMRIGHT", -1, 1)
    card.glow:SetAlpha(0.3)
    card.steps = {}
    for i = 1, CW.CARD_STEPS do
        local s = K.StepIconFrame(card, 22)
        s:SetPoint("BOTTOMLEFT", card, "BOTTOMLEFT", 10 + (i - 1) * 28, 10)
        card.steps[i] = s
    end
    -- the card's own tooltip: the flavour text and the unlock (the step icons have theirs)
    K.Tip(card)
    return card
end
recipes.cards = UI.Pool(recipeCard)

function recipes:Refresh()
    local cafeId = CW.CafeId()
    local level = K.BaristaLevel()
    self.filter:Select(self.family)
    self.cards:ReleaseAll()
    local list = {}
    local total, open = 0, 0
    for _, f in ipairs(K.FAMILY_ORDER) do
        for _, r in ipairs(Cafe.Recipes(cafeId, f)) do
            total = total + 1
            if (r.unlock or 1) <= level then
                open = open + 1
            end
            if self.family == "all" or self.family == f then
                list[#list + 1] = r
            end
        end
    end
    self.summary:SetText(open .. " of " .. total .. " recipes unlocked at barista level " .. level)
    for i, r in ipairs(list) do
        local card = self.cards:Acquire()
        local col, row = (i - 1) % 3, floor((i - 1) / 3)
        card:ClearAllPoints()
        card:SetPoint("TOPLEFT", self.scroll.child, "TOPLEFT", col * (CW.CARD_W + CW.CARD_GAP),
            -row * (CW.CARD_H + CW.CARD_GAP))
        local locked = (r.unlock or 1) > level
        card.recipe = r
        card.locked = locked
        card.item:SetIcon(Cafe.Icon("family", r.family))
        card.item:SetCollected(not locked)
        UI.SetText(card.name, r.name)
        UI.SetColor(card.name, K.TierColor(r.tier))
        card.stars:SetCount(r.tier)
        if locked then
            card.lock:Show()
            card.need:SetText("Barista level " .. (r.unlock or 1))
            card.need:Show()
        else
            card.lock:Hide()
            card.need:Hide()
        end
        card.money:SetCopper(Cafe.Price(r.id))
        card.info:SetText("· " .. U.Safe(Cafe.FamilyName(r.family)))
        card.buff:SetText(K.BuffLine(r))
        local groups = K.StepGroups(r.steps)
        for j, s in ipairs(card.steps) do
            local g = groups[j]
            if g then
                s:SetStep(g.actionId, g.count, r.family, cafeId)
                s.icon:SetDesaturated(locked)
                s:Show()
            else
                s:Hide()
            end
        end
        card.tip = function(c)
            local rr = c.recipe
            local lines = { U.Safe(rr.name) }
            if rr.text then
                lines[#lines + 1] = { U.Safe(rr.text), C.text, true }
            end
            lines[#lines + 1] = { K.BUFF_LONG[rr.family] or "", C.teal, true }
            if c.locked then
                lines[#lines + 1] = { "Unlocks at barista level " .. (rr.unlock or 1) .. ".", C.red }
            end
            return lines
        end
    end
    local rows = ceil(#list / 3)
    self.scroll:SetContentHeight(max(0, rows * (CW.CARD_H + CW.CARD_GAP) - CW.CARD_GAP))
    self.scroll:SetStep(CW.CARD_H + CW.CARD_GAP)
end

------------------------------------------------------------------------------------------------------
-- Leaderboard (board C: one café's week)
------------------------------------------------------------------------------------------------------
local board = newPage("board")
CW.board = board
board.cafeId = nil
board.week = 0          -- 0 this week, else CAFP's week id - 1
board.page = 1
CW.BOARD_ROWS = 10
CW.BOARD_ROW_H = 26

local cityDefs = {}
for id = 1, 2 do
    local cafe = D.cafes[id]
    cityDefs[id] = { value = id, label = cafe and cafe.name or ("Café " .. id) }
end
board.city = K.Segmented(board, cityDefs, 150, 22, function(value)
    board.cafeId = value
    board.page = 1
    CW.QueryBoard()
    board:Refresh()
end)
board.city.buttons[1]:SetPoint("TOPLEFT", board, "TOPLEFT", PAD, -14)
board.weekSel = K.Segmented(board, { { value = "this", label = "This Week" }, { value = "last", label = "Last Week" } },
    100, 22, function(value)
        local W = S.cafeProfile and S.cafeProfile.week
        board.week = (value == "last" and W and W.weekId and W.weekId > 1) and (W.weekId - 1) or 0
        board.page = 1
        CW.QueryBoard()
        board:Refresh()
    end)
board.weekSel.buttons[1]:SetPoint("LEFT", board.city.buttons[2], "RIGHT", 24, 0)

local TABLE_W = 540
local tbl = UI.Box(board, TABLE_W, BH - 60, C.card, C.border, nil, "edge")
tbl:SetPoint("TOPLEFT", board, "TOPLEFT", PAD - 4, -46)
board.table = tbl
CW.BOARD_COLS = { { "Rank", 58 }, { "Name", 196 }, { "Points", 90 }, { "Drinks", 100 }, { "Perfect", 94 } }
local header = CreateFrame("Frame", nil, tbl)
header:SetPoint("TOPLEFT", tbl, "TOPLEFT", 1, -1)
header:SetSize(TABLE_W - 2, 24)
header.cols = {}
do
    local x = 0
    for i, c in ipairs(CW.BOARD_COLS) do
        local h = UI.ColumnHeader(header, i == #CW.BOARD_COLS and (TABLE_W - 2 - x) or c[2], c[1])
        h:SetPoint("TOPLEFT", header, "TOPLEFT", x, 0)
        header.cols[i] = h
        x = x + c[2]
    end
end
board.header = header

local MEDAL_ICONS = { "Achievement_Arena_2v2_7", "Achievement_Arena_2v2_3", "Achievement_Arena_2v2_1" }

local function boardRow(parent)
    local r = CreateFrame("Button", nil, parent)
    r:SetSize(TABLE_W - 2, CW.BOARD_ROW_H)
    r:SetHighlightTexture(UI.STOCK.rowHighlight, "ADD")
    r.cells = {}
    local x = 0
    for i, c in ipairs(CW.BOARD_COLS) do
        local fs = UI.Text(r, 12, i == 3 and C.gold or C.text)
        fs:SetPoint("LEFT", r, "LEFT", x + 10, 0)
        UI.OneLine(fs, c[2] - 14)
        r.cells[i] = fs
        x = x + c[2]
    end
    -- the podium's medals as the Leaderboards window shows them: the arena achievements' gold, silver and bronze axes,
    -- with the place in the corner as a stack count
    r.medal = UI.Icon(r, 22, MEDAL_ICONS[1])
    r.medal.rank = r.medal:CreateFontString(nil, "OVERLAY")
    r.medal.rank:SetFont(UI.FONT_BODY, 11, "OUTLINE")
    r.medal.rank:SetTextColor(1, 1, 1)
    r.medal.rank:SetPoint("BOTTOMRIGHT", r.medal, "BOTTOMRIGHT", 0, 1)
    function r.medal:SetRank(n)
        self:SetIcon(MEDAL_ICONS[n] or MEDAL_ICONS[#MEDAL_ICONS])
        self.rank:SetText(n and tostring(n) or "")
    end
    r.medal:SetPoint("LEFT", r, "LEFT", 6, -1)
    r.medal:Hide()
    r:SetScript("OnEnter", function(self)
        if self.tipLines then
            UI.ShowTooltip(self, self.tipLines)
        end
    end)
    r:SetScript("OnLeave", hideTip)
    return r
end
tbl.rows = {}
for i = 1, CW.BOARD_ROWS do
    local r = boardRow(tbl)
    r:SetPoint("TOPLEFT", header, "BOTTOMLEFT", 0, -2 - (i - 1) * CW.BOARD_ROW_H)
    tbl.rows[i] = r
end
tbl.empty = UI.Text(tbl, 13, C.dim, "body", "CENTER")
tbl.empty:SetPoint("CENTER", tbl, "CENTER", 0, 20)
-- the player's own row, pinned under the table behind a faint rule
tbl.rule = tbl:CreateTexture(nil, "ARTWORK")
tbl.rule:SetTexture(1, 1, 1, 0.12)
tbl.rule:SetHeight(1)
tbl.rule:SetPoint("BOTTOMLEFT", tbl, "BOTTOMLEFT", 6, 72)
tbl.rule:SetPoint("BOTTOMRIGHT", tbl, "BOTTOMRIGHT", -6, 72)
tbl.me = boardRow(tbl)
tbl.me:SetPoint("BOTTOMLEFT", tbl, "BOTTOMLEFT", 1, 42)
tbl.next = UI.PageButton(tbl, "Next")
tbl.next:SetPoint("BOTTOMRIGHT", tbl, "BOTTOMRIGHT", -6, 4)
tbl.pageText = UI.Text(tbl, 12, C.text, "body", "CENTER")
tbl.pageText:SetPoint("RIGHT", tbl.next, "LEFT", -4, 0)
tbl.pageText:SetWidth(90)
tbl.prev = UI.PageButton(tbl, "Prev")
tbl.prev:SetPoint("RIGHT", tbl.pageText, "LEFT", -4, 0)
tbl.prev:SetScript("OnClick", function()
    if board.page > 1 then
        board.page = board.page - 1
        CW.QueryBoard()
    end
end)
tbl.next:SetScript("OnClick", function()
    local lb = CW.BoardData()
    if lb and board.page < (lb.pages or 1) then
        board.page = board.page + 1
        CW.QueryBoard()
    end
end)
tbl.rule2 = UI.Text(tbl, 11, C.dim)
tbl.rule2:SetPoint("BOTTOMLEFT", tbl, "BOTTOMLEFT", 10, 14)
UI.OneLine(tbl.rule2, 300)
tbl.rule2:SetText("Needs 50 drinks on 3 days of the week")

-- the aside: your week and last week's Best Barista
local ASIDE_W = BW - TABLE_W - 2 * PAD - 6
local aside = UI.Box(board, ASIDE_W, BH - 60, C.card, C.border, nil, "edge")
aside:SetPoint("TOPRIGHT", board, "TOPRIGHT", -PAD + 4, -46)
board.aside = aside
aside.label = UI.Label(aside, "Your Week", 12)
aside.label:SetPoint("TOPLEFT", aside, "TOPLEFT", 14, -14)
aside.value = UI.Text(aside, 22, C.gold)
aside.value:SetPoint("TOPLEFT", aside.label, "BOTTOMLEFT", 0, -6)
UI.OneLine(aside.value, ASIDE_W - 28)
aside.detail = UI.Text(aside, 12, C.text)
aside.detail:SetPoint("TOPLEFT", aside.value, "BOTTOMLEFT", 0, -4)
UI.OneLine(aside.detail, ASIDE_W - 28)
aside.bar = UI.Bar(aside, ASIDE_W - 38, 14)
aside.bar:SetPoint("TOPLEFT", aside.detail, "BOTTOMLEFT", 5, -10)
aside.days = UI.Text(aside, 11, C.dim)
UI.OneLine(aside.days, ASIDE_W - 28)
aside.state = UI.Text(aside, 11, C.teal)
UI.OneLine(aside.state, ASIDE_W - 28)

-- The lines under the rank: the bar (this week's board only), the days worked (CAFP W, this week only) and the
-- state, each under the last one shown, so a hidden one leaves no gap; last week's Best Barista follows them.
CW.ASIDE_LAST_GAP = 34
function CW.StackAside(showBar, showDays, showState)
    local function under(fs)
        fs:ClearAllPoints()
        if showBar then
            fs:SetPoint("TOPLEFT", aside.bar, "BOTTOMLEFT", -5, -9)
        else
            fs:SetPoint("TOPLEFT", aside.detail, "BOTTOMLEFT", 0, -8)
        end
    end
    if showBar then
        aside.bar:Show()
    else
        aside.bar:Hide()
    end
    under(aside.days)
    if showDays then
        aside.days:Show()
        aside.state:ClearAllPoints()
        aside.state:SetPoint("TOPLEFT", aside.days, "BOTTOMLEFT", 0, -4)
    else
        aside.days:Hide()
        under(aside.state)
    end
    if showState then
        aside.state:Show()
    else
        aside.state:Hide()
    end
    local last = (showState and aside.state) or (showDays and aside.days) or nil
    aside.lastLabel:ClearAllPoints()
    if last then
        aside.lastLabel:SetPoint("TOPLEFT", last, "BOTTOMLEFT", 0, -CW.ASIDE_LAST_GAP)
    elseif showBar then
        aside.lastLabel:SetPoint("TOPLEFT", aside.bar, "BOTTOMLEFT", -5, -CW.ASIDE_LAST_GAP)
    else
        aside.lastLabel:SetPoint("TOPLEFT", aside.detail, "BOTTOMLEFT", 0, -CW.ASIDE_LAST_GAP)
    end
end
aside.lastLabel = UI.Label(aside, "Last Week", 12)
CW.StackAside(true, true, true)
aside.crown = UI.Icon(aside, 30, "INV_Crown_01")
aside.crown:SetPoint("TOPLEFT", aside.lastLabel, "BOTTOMLEFT", 0, -8)
aside.lastName = UI.Text(aside, 13, C.text)
aside.lastName:SetPoint("TOPLEFT", aside.crown, "TOPRIGHT", 8, -1)
UI.OneLine(aside.lastName, ASIDE_W - 66)
aside.lastPoints = UI.Text(aside, 11, C.dim)
aside.lastPoints:SetPoint("TOPLEFT", aside.lastName, "BOTTOMLEFT", 0, -3)
UI.OneLine(aside.lastPoints, ASIDE_W - 66)
aside.pay = UI.Para(aside, 11, C.dim, ASIDE_W - 28)
aside.pay:SetPoint("BOTTOMLEFT", aside, "BOTTOMLEFT", 14, 14)
aside.pay:SetText("The top ten of each café are paid by mail at the weekly reset: 50g for the Best Barista, then 30g, "
    .. "20g and 5g.")

-- the board request of the shown café and week
function CW.QueryBoard()
    board.cafeId = board.cafeId or Cafe.MyCafe()
    Comm.Send("LBQ", "C", board.week or 0, board.cafeId, 0, board.page or 1)
end

-- S.lb.C when it answers the shown request: the shown café, and the week (this week's answer names its real week id)
function CW.BoardData()
    local lb = S.lb and S.lb.C
    if not lb or lb.dungeonId ~= board.cafeId then
        return nil
    end
    local W = S.cafeProfile and S.cafeProfile.week
    if board.week and board.week > 0 then
        return lb.seasonId == board.week and lb or nil
    end
    if W and W.weekId and lb.seasonId ~= 0 and lb.seasonId ~= W.weekId then
        return nil
    end
    return lb
end

local function boardName(row)
    local m = row.members and row.members[1]
    if not m then
        return "-"
    end
    return U.Color(ns.ClassColor(m.classId), U.Safe(m.name))
end

local function perfectText(permille)
    return permille and (floor(permille / 10 + 0.5) .. "%") or "-"
end

local function fillRow(r, rank, name, points, drinks, perfect, tip)
    if rank and rank <= 3 then
        r.medal:SetRank(rank)
        r.medal:Show()
        r.cells[1]:SetText("")
    else
        r.medal:Hide()
        r.cells[1]:SetText(rank and tostring(rank) or "-")
    end
    r.cells[2]:SetText(name)
    r.cells[3]:SetText(points)
    r.cells[4]:SetText(drinks)
    r.cells[5]:SetText(perfect)
    r.tipLines = tip
end

function board:Refresh()
    self.cafeId = self.cafeId or Cafe.MyCafe()
    self.city:Select(self.cafeId)
    self.weekSel:Select((self.week or 0) > 0 and "last" or "this")
    local W = S.cafeProfile and S.cafeProfile.week
    self.weekSel.buttons[2]:SetActive(W ~= nil and W.weekId ~= nil and W.weekId > 1)
    local lb = CW.BoardData()
    local list = lb and lb.rows or {}
    for i, r in ipairs(tbl.rows) do
        local row = list[i]
        if row then
            local tip = { "Rank " .. row.rank .. "  -  " .. U.Commas(row.value or 0) .. " points",
                { boardName(row), C.text },
                { U.Safe(row.label or "") .. " · " .. perfectText(row.timeSec) .. " Perfect", C.dim } }
            if row.date then
                tip[#tip + 1] = { "Last drink " .. (U.Date("%d %b %H:%M", row.date) or "-"), C.dim }
            end
            fillRow(r, row.rank, boardName(row), U.Commas(row.value or 0), U.Safe(row.label or "-"),
                perfectText(row.timeSec), tip)
            r:Show()
        else
            r:Hide()
        end
    end
    if #list == 0 then
        tbl.empty:SetText((lb and "Nobody is ranked yet this week.")
            or (Comm.ready and "Asking the server..." or "Waiting for the server..."))
        tbl.empty:Show()
    else
        tbl.empty:Hide()
    end
    local pages = lb and lb.pages or 1
    tbl.pageText:SetText("Page " .. (lb and lb.page or self.page or 1) .. " / " .. pages)
    tbl.prev:SetActive((self.page or 1) > 1)
    tbl.next:SetActive((self.page or 1) < pages)

    -- your row: LBME C for the shown café
    local me = S.lbme and S.lbme.C
    local mine = me and me.dungeonId == self.cafeId and (me.value or me.rank) and me or nil
    local name = U.Color(K.PlayerColor(), U.Safe(ns.PlayerName() or "You"))
    if mine then
        local top = mine.topPercent and (" · top " .. mine.topPercent .. "%") or ""
        local tip = { "Your place", { "Rank " .. (mine.rank or "-") .. top, C.text } }
        fillRow(tbl.me, mine.rank, name, U.Commas(mine.value or 0), U.Safe(mine.label or "-"),
            perfectText(mine.timeSec), tip)
    else
        fillRow(tbl.me, nil, name, "-", "-", "-",
            { "Your place", { "Not ranked: 50 drinks on 3 days of the week.", C.dim } })
    end

    -- your week at the shown café: this week from CAFP W, with the bar (LBME: your points against the first's); last
    -- week from LBME, which comes with that week's board (CAFP has no days worked for it)
    local lastWeek = (self.week or 0) > 0
    aside.label:SetLabel(lastWeek and "Your Last Week" or "Your Week")
    if lastWeek then
        local m = lb and mine
        if m and m.value then
            aside.value:SetText(U.Commas(m.value) .. " points")
            aside.detail:SetText("Rank " .. (m.rank or "-") .. " · " .. U.Safe(m.label or "-") .. " · "
                .. perfectText(m.timeSec) .. " Perfect")
            aside.state:SetText("On the board")
            UI.SetColor(aside.state, C.teal)
        else
            aside.value:SetText("0 points")
            aside.detail:SetText(lb and "Not ranked that week." or "Asking the server...")
            aside.state:SetText("")
        end
        CW.StackAside(false, false, m and m.value ~= nil)
    elseif W and W.cafeId == self.cafeId then
        aside.value:SetText(U.Commas(W.points or 0) .. " points")
        aside.detail:SetText((W.rank and ("Rank " .. W.rank) or "Not ranked yet") .. " · " .. (W.drinks or 0)
            .. " drinks · " .. perfectText(W.perfectPermille) .. " Perfect")
        local bar = mine and mine.barPermille
        if bar then
            aside.bar:SetProgress(bar / 1000, floor(bar / 10) .. "% of the first")
        end
        aside.days:SetText("Days worked: " .. (W.days or 0) .. " (3 needed)")
        local eligible = W.eligible and W.eligible ~= 0
        aside.state:SetText(eligible and "On the board" or "Needs 50 drinks on 3 days of the week")
        UI.SetColor(aside.state, eligible and C.teal or C.dim)
        CW.StackAside(bar ~= nil, true, true)
    else
        aside.value:SetText("0 points")
        aside.detail:SetText("You have not worked here this week.")
        aside.state:SetText("")
        CW.StackAside(false, false, false)
    end
    local last = S.cafeProfile and S.cafeProfile.last and S.cafeProfile.last[self.cafeId]
    if last and last.winnerName then
        UI.SetText(aside.lastName, last.winnerName)
        aside.lastPoints:SetText(U.Commas(last.points or 0) .. " points · Best Barista")
        aside.crown.icon:SetDesaturated(false)
    else
        aside.lastName:SetText("No winner yet")
        aside.lastPoints:SetText("")
        aside.crown.icon:SetDesaturated(true)
    end
end

------------------------------------------------------------------------------------------------------
-- Rewards
------------------------------------------------------------------------------------------------------
local rewards = newPage("rewards")
CW.rewards = rewards
CW.LEVEL_ICONS = { "INV_Drink_15", "INV_Misc_Food_31", "INV_Drink_23", "INV_Misc_Note_02", "INV_Chest_Cloth_21",
    "Spell_Holy_MindVision", "INV_Drink_17", "INV_Misc_Note_03", "INV_Misc_Coin_01", "INV_Chest_Cloth_30" }
-- the aprons: { the item at each café, the rewards bit, how it is earned }
CW.APRONS = {
    { items = { 909380, 909381 }, bit = 1, name = "Apprentice's Apron", need = "At barista level 5" },
    { items = { 909382, 909383 }, bit = 2, name = "Master Barista's Apron", need = "At barista level 10" },
    { items = { 909384, 909384 }, bit = 4, name = "Golden Apron", need = "Best Barista of a week" },
}
CW.TITLES = {
    { bit = 8, name = "%s the Barista", need = "At barista level 10" },
    { bit = 16, name = "%s, Café Legend", need = "3 weekly wins" },
}

rewards.head = UI.Heading(rewards, "Barista Levels")
rewards.head:SetPoint("TOPLEFT", rewards, "TOPLEFT", PAD, -16)
local NODES = 10
local nodeW = floor((BW - 2 * PAD) / NODES)
local function nodeX(i)
    return PAD + nodeW * (i - 0.5)
end
local RING, RING_Y = 40, -44
rewards.bar = UI.Bar(rewards, nodeX(NODES) - nodeX(1), 14)
rewards.bar:SetPoint("TOPLEFT", rewards, "TOPLEFT", nodeX(1), RING_Y - RING / 2 + 7)
rewards.nodes = {}
for i = 1, NODES do
    local n = CreateFrame("Frame", nil, rewards)
    n:SetSize(nodeW, 80)
    n:SetPoint("TOP", rewards, "TOPLEFT", nodeX(i), RING_Y)
    n:SetFrameLevel(rewards.bar:GetFrameLevel() + 3)
    n.badge = UI.Badge(n, RING, CW.LEVEL_ICONS[i])
    n.badge:SetPoint("TOP", n, "TOP", 0, 0)
    n.check = UI.Check(n.badge, 18)
    n.check:SetPoint("TOPRIGHT", n.badge, "TOPRIGHT", 3, 3)
    n.check:Hide()
    n.label = UI.Text(n, 11, C.text, "body", "CENTER")
    n.label:SetPoint("TOP", n.badge, "BOTTOM", 0, -4)
    n.label:SetText("Level " .. i)
    n.level = i
    K.Tip(n)
    rewards.nodes[i] = n
end

rewards.apronHead = UI.Heading(rewards, "Aprons")
rewards.apronHead:SetPoint("TOPLEFT", rewards, "TOPLEFT", PAD, -140)
CW.APRON_W, CW.APRON_H = 160, 220
rewards.aprons = {}
for i, a in ipairs(CW.APRONS) do
    local box = UI.Box(rewards, CW.APRON_W, CW.APRON_H, C.card, C.border, nil, "edge")
    box:SetPoint("TOPLEFT", rewards, "TOPLEFT", PAD + (i - 1) * (CW.APRON_W + 12), -164)
    box.model = CreateFrame("DressUpModel", nil, box)
    box.model:SetPoint("TOPLEFT", box, "TOPLEFT", 1, -1)
    box.model:SetPoint("BOTTOMRIGHT", box, "BOTTOMRIGHT", -1, 1)
    box.name = UI.Text(rewards, 12, C.gold, "body", "CENTER")
    box.name:SetPoint("TOP", box, "BOTTOM", 0, -6)
    UI.OneLine(box.name, CW.APRON_W)
    box.name:SetText(a.name)
    box.state = UI.Text(rewards, 11, C.dim, "body", "CENTER")
    box.state:SetPoint("TOP", box.name, "BOTTOM", 0, -2)
    UI.OneLine(box.state, CW.APRON_W)
    box.def = a
    rewards.aprons[i] = box
end

local SIDE_X = PAD + 3 * (CW.APRON_W + 12) + 14
local SIDE_W = BW - SIDE_X - PAD
rewards.titleHead = UI.Heading(rewards, "Titles")
rewards.titleHead:SetPoint("TOPLEFT", rewards, "TOPLEFT", SIDE_X, -140)
rewards.titles = {}
for i, t in ipairs(CW.TITLES) do
    local r = CreateFrame("Frame", nil, rewards)
    r:SetSize(SIDE_W, 34)
    r:SetPoint("TOPLEFT", rewards, "TOPLEFT", SIDE_X, -164 - (i - 1) * 40)
    r.icon = UI.Icon(r, 30, "INV_Crown_01")
    r.icon:SetPoint("LEFT", r, "LEFT", 0, 0)
    r.name = UI.Text(r, 12, C.text)
    r.name:SetPoint("TOPLEFT", r.icon, "TOPRIGHT", 8, -1)
    UI.OneLine(r.name, SIDE_W - 40)
    r.state = UI.Text(r, 11, C.dim)
    r.state:SetPoint("TOPLEFT", r.name, "BOTTOMLEFT", 0, -3)
    UI.OneLine(r.state, SIDE_W - 40)
    r.def = t
    rewards.titles[i] = r
end
rewards.lifeHead = UI.Heading(rewards, "Lifetime")
rewards.lifeHead:SetPoint("TOPLEFT", rewards, "TOPLEFT", SIDE_X, -258)
-- From memory is counted by the addon (Cafe.MemoryDrinks: the server cannot see the mode), and its label says so
CW.LIFETIME = { "Drinks", "Perfect", "Best streak", "Fastest drink", "From memory (addon)", "Weekly wins" }
rewards.life = {}
for i, label in ipairs(CW.LIFETIME) do
    local lv = UI.LabelValue(rewards, label, "-", 12)
    lv:SetPoint("TOPLEFT", rewards, "TOPLEFT", SIDE_X, -282 - (i - 1) * 20)
    UI.OneLine(lv, SIDE_W)
    rewards.life[i] = lv
end
-- From memory: what it counts and, once it is open to the player (CAFST flag 2, barista level 6), how to turn it on
rewards.memoryHit = K.Tip(CreateFrame("Frame", nil, rewards))
rewards.memoryHit:SetPoint("TOPLEFT", rewards.life[5], "TOPLEFT", 0, 2)
rewards.memoryHit:SetSize(SIDE_W, 18)
rewards.memoryHit.tip = function()
    local st = S.cafeState
    local lines = { "From memory", { "Drinks made with the ticket's steps hidden.", C.text, true },
        { "Counted by your Bleakhold addon on this character: the realm cannot see whether the steps were hidden.",
            C.dim, true } }
    if st and (bit.band(st.flags or 0, 2) ~= 0 or (st.level or 0) >= 6) then
        lines[#lines + 1] = { "Turn it on with /bh cafe memory.", C.teal, true }
    else
        lines[#lines + 1] = { "Opens at barista level 6.", C.dim, true }
    end
    return lines
end

local function hasBit(v, b)
    return bit.band(v or 0, b) ~= 0
end

-- an apron whose item was not in the client's cache yet is tried on again once it is
rewards.elapsed = 0
rewards:SetScript("OnUpdate", function(self, elapsed)
    self.elapsed = self.elapsed + (elapsed or 0)
    if self.elapsed < 1 then
        return
    end
    self.elapsed = 0
    for _, box in ipairs(self.aprons) do
        if not box.dressed and box.item and ns.Collections and ns.Collections.RequestItem
            and ns.Collections.RequestItem(box.item) then
            box.model:SetUnit("player")
            box.model:Undress()
            box.model:TryOn(box.item)
            box.dressed = true
        end
    end
end)

function rewards:Refresh()
    local P = S.cafeProfile
    local level = (P and P.level) or K.BaristaLevel()
    local cafeId = Cafe.MyCafe()
    for i, n in ipairs(self.nodes) do
        local reached = level >= i
        n.badge:SetLocked(not reached)
        if reached then n.check:Show() else n.check:Hide() end
        UI.SetColor(n.label, reached and C.text or C.dim)
        n.tip = function()
            local L = Cafe.Level(i)
            local lines = { "Barista level " .. i }
            if L and L.text then
                lines[#lines + 1] = { U.Safe(L.text), C.text, true }
            end
            if L and L.xp then
                lines[#lines + 1] = { U.Commas(L.xp) .. " XP in total", C.dim }
            end
            lines[#lines + 1] = reached and { "Reached", C.teal } or { "Not reached yet", C.dim }
            return lines
        end
    end
    local p = 0
    if level > 1 then
        p = (level - 1) / (NODES - 1)
    end
    self.bar:SetProgress(p)

    local rw = P and P.rewards or 0
    for _, box in ipairs(self.aprons) do
        local item = box.def.items[cafeId] or box.def.items[1]
        if box.item ~= item or not box.dressed then
            box.item = item
            box.model:SetUnit("player")
            box.model:Undress()
            -- the item must be in the client's cache before TryOn shows it (Collections asks the server)
            local ready = not (ns.Collections and ns.Collections.RequestItem) or ns.Collections.RequestItem(item)
            box.model:TryOn(item)
            box.dressed = ready and true or false
        end
        local earned = hasBit(rw, box.def.bit)
        box.state:SetText(earned and "Earned" or box.def.need)
        UI.SetColor(box.state, earned and C.teal or C.dim)
    end
    for _, r in ipairs(self.titles) do
        local earned = hasBit(rw, r.def.bit)
        r.name:SetText(string.format(r.def.name, U.Safe(ns.PlayerName() or "You")))
        r.icon.icon:SetDesaturated(not earned)
        local need = r.def.need
        if r.def.bit == 16 then
            need = need .. ": " .. min(3, P and P.weeklyWins or 0) .. "/3"
        end
        r.state:SetText(earned and "Earned" or need)
        UI.SetColor(r.state, earned and C.teal or C.dim)
    end
    local life = self.life
    if P then
        life[1]:SetValue(U.Commas(P.drinks or 0))
        life[2]:SetValue((P.drinks or 0) > 0 and (floor((P.perfects or 0) * 100 / P.drinks + 0.5) .. "%") or "-")
        life[3]:SetValue(P.bestStreak and P.bestStreak > 0 and ("×" .. P.bestStreak) or "-")
        life[4]:SetValue(P.fastestMs and (string.format("%.1f s", P.fastestMs / 1000)) or "-")
        life[6]:SetValue(tostring(P.weeklyWins or 0))
    else
        for _, lv in ipairs(life) do
            lv:SetValue("-")
        end
    end
    -- the addon's own count (CAFP memoryDrinks is never counted by the realm)
    life[5]:SetValue(U.Commas(Cafe.MemoryDrinks()))
end

------------------------------------------------------------------------------------------------------
-- How it works
------------------------------------------------------------------------------------------------------
local help = newPage("help")
CW.help = help
help.scroll = UI.Scroll(help)
help.scroll:SetPoint("TOPLEFT", help, "TOPLEFT", PAD, -16)
help.scroll:SetSize(BW - PAD - 8, BH - 28)
-- the sections; {full} {half} are today's daily XP from CAFST D (450 and 450 by default), {keys} the café keys
-- (/bh cafe keys)
CW.HELP = {
    { "Shifts", "Talk to the café's owner, or press Start Shift on the Shift tab while you are at the café. A shift "
        .. "needs character level 10 and lasts as long as you like: it ends when you press End Shift, walk away from "
        .. "the café, enter combat, die, mount, go AFK, or stay idle for two minutes while holding a ticket (five "
        .. "without one). {keys} press the barista bar only while you are on shift; your action bar is never changed, "
        .. "and combat gives the keys back at once." },
    { "Stations and Keys", "The café has seven stations: the Grinder, the Espresso Machine, the Kettle, the Cold Box, "
        .. "the Blender, the Syrup Shelf and the Serving Counter. Walk to a station and face it, and the barista bar "
        .. "shows what each key does there. Take an order at the counter, make the drink step by step from its "
        .. "ticket, then serve it at the counter. A wrong step ruins the drink and the ticket starts again from step 1; "
        .. "Bin throws a drink away on purpose. Both end your Perfect streak. A player's order goes to the house after "
        .. "a second ruin, and you get nothing for it." },
    { "Quality and Patience", "Taps finish on their own. A timed step fills a bar: press its key again inside the "
        .. "gold for Perfect, close to it for Good, anywhere else for Off. A drink with every timed step Perfect, "
        .. "served with a quarter of the customer's patience left, is Perfect; one with no Off step is Good; the "
        .. "rest are Sloppy. Patience shows green, then yellow, then red, always with the seconds left: when it runs "
        .. "out the customer leaves, and a player's order goes to the house (the owner finishes it for them). Walking "
        .. "away during a step only interrupts that step." },
    { "Rewards and Caps", "Drinks give barista XP, tips and Café Points. Each day the first {full} XP count in "
        .. "full and the next {half} at half rate; tips and points have a daily cap too. After 60 minutes on shift "
        .. "without a 15-minute break you are Tired: barista XP and Café Points are halved (tips are not) until you "
        .. "have rested 15 minutes off shift. Barista levels unlock "
        .. "recipes, more tickets at once, two aprons and the title \"the Barista\". Baristas with 50 drinks on 3 "
        .. "days of the week are ranked on the Leaderboard, and the top ten of each café are paid by mail at the "
        .. "weekly reset." },
    { "Ordering a Drink", "Talk to {owner}, or press Order a Drink at the top of this window (or type /bh cafe menu), "
        .. "choose a drink and a tip, and press Order within 40 yards of the café. A barista on shift or the house makes it; your order shows at "
        .. "the top of the screen. When it is ready, walk to the counter or sit at a café table to pick it up before "
        .. "its time runs out. Each drink is an out-of-combat buff for 30 minutes or more." },
    { "Options", "/bh cafe keys 1,2,3,4,5,6,7,8: the eight keys of the barista bar (SHIFT-, CTRL- or ALT- in front "
        .. "work too). /bh cafe scale 0.8 to 1.4: the size of the café's panels. /bh cafe sound and /bh cafe motion "
        .. "turn the sounds and the moving effects on or off. /bh cafe memory: from barista level 6, hide the "
        .. "ticket's steps and make drinks from memory. /bh cafe autoselect: a newly taken ticket becomes the one "
        .. "your keys work on (unless a drink is in your hands). /bh cafe menu opens the menu; "
        .. "/bh cafe on its own opens this window." },
}
-- each section: its icon on the left (a ring portrait, as the Activities pages head theirs), the gold heading and the
-- text beside it, in a column as wide as the old pages' descriptions allow for four sections
CW.HELP_ICONS = { "INV_Chest_Cloth_21", "INV_Gizmo_01", "Spell_Holy_BorrowedTime", "INV_Misc_Coin_01", "INV_Drink_15",
    "INV_Misc_Gear_01" }
CW.HELP_TEXT_W = 600
help.sections = {}
for i, s in ipairs(CW.HELP) do
    local icon = UI.Badge(help.scroll.child, 44, CW.HELP_ICONS[i])
    local h = UI.Heading(help.scroll.child, s[1])
    local p = UI.Para(help.scroll.child, 12, C.text, CW.HELP_TEXT_W)
    help.sections[i] = { icon = icon, head = h, text = p, body = s[2] }
end

-- "Keys 1 to 8" with the default keys, else the player's own (/bh cafe keys)
function CW.KeysText()
    local keys = Cafe.Keys()
    if table.concat(keys, ",") == Cafe.DEFAULTS.cafeKeys then
        return "Keys 1 to 8"
    end
    return "Your café keys (" .. table.concat(keys, ", ") .. ")"
end

function help:Refresh()
    local day = S.cafeState and S.cafeState.day
    local full, half = day and day.dayXpFull or 450, day and day.dayXpHalf or 450
    local keys = CW.KeysText()
    local cafe = Cafe.Cafe(CW.CafeId())
    local owner = U.Safe(cafe and cafe.ownerName or "the caf\195\169's owner")
    local y = 4
    for _, s in ipairs(self.sections) do
        s.icon:ClearAllPoints()
        s.icon:SetPoint("TOPLEFT", self.scroll.child, "TOPLEFT", 4, -y)
        s.head:ClearAllPoints()
        s.head:SetPoint("TOPLEFT", self.scroll.child, "TOPLEFT", 70, -y - 2)
        s.text:ClearAllPoints()
        s.text:SetPoint("TOPLEFT", s.head, "BOTTOMLEFT", 0, -6)
        s.text:SetText((s.body:gsub("{full}", U.Commas(full)):gsub("{half}", U.Commas(half))
            :gsub("{keys}", function() return keys end):gsub("{owner}", function() return owner end)))
        y = y + max(52, 14 + 6 + ceil(s.text:GetStringHeight() or 40)) + 20
    end
    self.scroll:SetContentHeight(y)
end

------------------------------------------------------------------------------------------------------
-- Tabs, opening, refresh
------------------------------------------------------------------------------------------------------
function CW.ShowTab(key)
    if not CW.pages[key] then
        key = "shift"
    end
    CW.tab = key
    for _, b in ipairs(tabs) do
        b:SetStyle(b.key == key and "stripOn" or "strip")
    end
    for k, p in pairs(CW.pages) do
        if k == key then p:Show() else p:Hide() end
    end
    if key == "board" then
        board.cafeId = board.cafeId or Cafe.MyCafe()
        Comm.Refresh("CAFP")
        CW.QueryBoard()
    elseif key == "rewards" then
        Comm.Refresh("CAFP")
    end
    CW.Refresh()
end

function CW.Refresh()
    if not win:IsShown() then
        return
    end
    local cafe = Cafe.Cafe(CW.CafeId())
    UI.SetText(kicker.name, cafe and cafe.name or "")
    kicker.emblem:SetTeam(cafe and cafe.team or "A")
    if Cafe.Enabled() and not Cafe.OnShift() then
        orderBtn:Show()
    else
        orderBtn:Hide()
    end
    local p = CW.pages[CW.tab]
    if p and p.Refresh then
        p:Refresh()
    end
end

function win:OnOpen()
    Comm.Refresh("CAFST")
    Comm.Refresh("CAFE")
    Comm.Refresh("CAFP")
    CW.ShowTab(CW.tab)
end

CW.REFRESH_ON = { CAFE = true, CAFST = true, CAFQ = true, CAFP = true, LB = true, LBME = true, DEF = true, CAFM = true }
ns.On("STATE", function(topic)
    if CW.REFRESH_ON[topic] then
        CW.Refresh()
    end
end)

-- the café's windows exist only while the realm's café runs for this player (HELLO feature bit 131072)
ns.On("HELLO", function()
    if not Cafe.Enabled() then
        win:Hide()
        if CW.summary then
            CW.summary:Hide()
        end
    end
end)

local function opener(tab)
    return function(toggle)
        if not Cafe.Enabled() then
            ns.Print("The café is not open on this realm right now.")
            return
        end
        if toggle and win:IsShown() and (tab == nil or CW.tab == tab) then
            win:Hide()
            return
        end
        CW.tab = tab or CW.tab
        if win:IsShown() then
            CW.ShowTab(CW.tab)
        else
            win:Show()
        end
    end
end
UI.RegisterOpener("cafe", opener(nil))
UI.RegisterOpener("cafeshift", opener("shift"))
UI.RegisterOpener("caferecipes", opener("recipes"))
UI.RegisterOpener("cafeboard", opener("board"))
UI.RegisterOpener("caferewards", opener("rewards"))
UI.RegisterOpener("cafehelp", opener("help"))

------------------------------------------------------------------------------------------------------
-- The shift summary card (CAFSUM)
------------------------------------------------------------------------------------------------------
-- As tall as what it shows (CW.SummaryHeight): the reason, the stats in two columns, the daily cap's line when XP went
-- over it, the Staff Drink when there is one, then Close.
CW.SUM_W = 380
CW.SUM_ROW_Y, CW.SUM_ROW_H = 32, 20     -- the stats' first row and their pitch
-- (numbers after the operator: the client's Lua 5.1.1 compiles `3 * x` as `x * x` in a chunk of over 255 constants)
CW.SUM_STATS_BOTTOM = CW.SUM_ROW_Y + CW.SUM_ROW_H * 3 + 15
CW.SUM_CAP_GAP, CW.SUM_CAP_H = 10, 14
CW.SUM_STAFF_GAP = 16
CW.SUM_CLOSE_GAP, CW.SUM_CLOSE_H = 20, 22
CW.SUM_CHOICE_Y, CW.SUM_CHOICE_H, CW.SUM_CHOICE_PITCH = 42, 41, 44
CW.SUM_STAFF_H = CW.SUM_CHOICE_Y + #K.FAMILY_ORDER * CW.SUM_CHOICE_PITCH - (CW.SUM_CHOICE_PITCH - CW.SUM_CHOICE_H)

-- the card's height with the cap line and the Staff Drink shown or not; noStats: only the Staff Drink (the Shift tab's
-- Claim Staff Drink with no shift summary here, after a /reload)
CW.SUM_BARE_Y = 26
function CW.SummaryHeight(cap, staffShown, noStats)
    local y = noStats and (CW.SUM_BARE_Y - CW.SUM_STAFF_GAP) or CW.SUM_STATS_BOTTOM
    if cap then
        y = y + CW.SUM_CAP_GAP + CW.SUM_CAP_H
    end
    if staffShown then
        y = y + CW.SUM_STAFF_GAP + CW.SUM_STAFF_H
    end
    local i = UI.WINDOW_INSETS
    return i.top + y + CW.SUM_CLOSE_GAP + CW.SUM_CLOSE_H + 2 + i.bottom
end

local sum = UI.Window("BleakholdCafeSummary", CW.SUM_W, CW.SummaryHeight(true, false), "Shift Complete",
    "INV_Chest_Cloth_21")
sum:SetFrameStrata("DIALOG")
CW.summary = sum
local SW = UI.ContentSize(CW.SUM_W, CW.SummaryHeight(true, false))
CW.REASONS = {
    E = "You ended your shift.", C = "Combat ended your shift.", A = "You went away, so the shift ended.",
    I = "You were idle for too long.", W = "You walked away from the café.",
    D = "You died, logged out or left the map.", M = "You were mounted, shapeshifted or hidden for too long.",
    X = "The café closed.", O = "The café was turned off.",
}
sum.reason = UI.Text(sum.content, 12, C.text, "body", "CENTER")
sum.reason:SetPoint("TOP", sum.content, "TOP", 0, -6)
UI.OneLine(sum.reason, SW - 8)
-- (Earned: the NPCs' tips and the pay of players' orders, the strip's number; the Shift tab's tips row is the NPC tips)
CW.SUM_LINES = { "Shift", "Drinks", "Perfect", "Best streak", "Earned", "Barista XP", "Café Points" }
sum.lines = {}
for i, label in ipairs(CW.SUM_LINES) do
    local col, row = (i <= 4) and 0 or 1, (i <= 4) and (i - 1) or (i - 5)
    local lv = UI.LabelValue(sum.content, label, "-", 12)
    lv:SetPoint("TOPLEFT", sum.content, "TOPLEFT", 12 + col * floor(SW / 2), -CW.SUM_ROW_Y - row * CW.SUM_ROW_H)
    UI.OneLine(lv, floor(SW / 2) - 16)
    sum.lines[i] = lv
end
-- the tips in coins after their label (the stock money frame)
sum.tips = Cafe.MoneyFrame(sum.content, 12)
sum.cap = UI.Text(sum.content, 11, C.dim, "body", "CENTER")
sum.cap:SetPoint("TOP", sum.content, "TOP", 0, -(CW.SUM_STATS_BOTTOM + CW.SUM_CAP_GAP))
UI.OneLine(sum.cap, SW - 8)

-- The Staff Drink: the quest reward choice (QuestItemTemplate: the icon, UI-QuestItemNameFrame beside it with the
-- name in white; UI-QuestItemHighlight under the cursor and on the chosen one), one full-width row per family, so
-- every name fits on one line, with the family in grey at its end. The plate and the highlight are cut in three,
-- their rounded ends at their own width and the middle stretched: the plate's art fills x 11-117 and y 11-53 of its
-- 128 x 64 file; the highlight's rims (icon x 9-44, name x 49-152, y 7-45 of 256 x 64) keep the stock offsets on a
-- row of 147 (QuestInfoItemHighlight at -8, 7) and its name rim ends 2 px inside the plate.
K.QUEST_HIGHLIGHT = "Interface\\QuestFrame\\UI-QuestItemHighlight"
K.PLATE_U, K.PLATE_V = { 11 / 128, 23 / 128, 105 / 128, 117 / 128 }, { 11 / 64, 53 / 64 }
K.HIGHLIGHT_U, K.HIGHLIGHT_V = { 0, 70 / 256, 130 / 256, 160 / 256 }, { 0, 1 }

-- three textures of file on parent's layer: the ends capL and capR wide, the middle stretched between them
function K.Slices(parent, layer, file, u, v, capL, capR, blend)
    local t = {}
    for i = 1, 3 do
        t[i] = parent:CreateTexture(nil, layer)
        t[i]:SetTexture(file)
        t[i]:SetTexCoord(u[i], u[i + 1], v[1], v[2])
        if blend then
            t[i]:SetBlendMode(blend)
        end
    end
    t[1]:SetWidth(capL)
    t[3]:SetWidth(capR)
    t[2]:SetPoint("TOPLEFT", t[1], "TOPRIGHT", 0, 0)
    t[2]:SetPoint("BOTTOMRIGHT", t[3], "BOTTOMLEFT", 0, 0)
    return t
end

-- the highlight's three slices on b's row, 64 tall from 7 px above it to its right end + 6
local function questHighlight(parent, b, layer)
    local t = K.Slices(parent, layer, K.QUEST_HIGHLIGHT, K.HIGHLIGHT_U, K.HIGHLIGHT_V, 70, 30, "ADD")
    t[1]:SetHeight(64)
    t[1]:SetPoint("TOPLEFT", b, "TOPLEFT", -8, 7)
    t[3]:SetHeight(64)
    t[3]:SetPoint("TOPRIGHT", b, "TOPRIGHT", 6, 7)
    return t
end

local staff = CreateFrame("Frame", nil, sum.content)
staff:SetSize(SW, CW.SUM_STAFF_H)
staff:SetPoint("TOP", sum.content, "TOP", 0, -(CW.SUM_STATS_BOTTOM + CW.SUM_STAFF_GAP))
staff.head = UI.Heading(staff, "Staff Drink: Choose One", 13)
staff.head:SetPoint("TOPLEFT", staff, "TOPLEFT", 12, 0)
staff.note = UI.Text(staff, 11, C.dim)
staff.note:SetPoint("TOPLEFT", staff.head, "BOTTOMLEFT", 0, -3)
UI.OneLine(staff.note, SW - 24)
staff.note:SetText("A free drink of your choice, once a day.")
staff.choices = {}
local CHOICE_W = SW - 24
for i, f in ipairs(K.FAMILY_ORDER) do
    local b = CreateFrame("Button", nil, staff)
    b:SetSize(CHOICE_W, CW.SUM_CHOICE_H)
    b:SetPoint("TOPLEFT", staff, "TOPLEFT", 12, -CW.SUM_CHOICE_Y - (i - 1) * CW.SUM_CHOICE_PITCH)
    b.icon = b:CreateTexture(nil, "ARTWORK")
    b.icon:SetSize(39, 39)
    b.icon:SetPoint("TOPLEFT", b, "TOPLEFT", 0, 0)
    -- the plate, 42 tall round the icon's middle, from 1 px right of the icon to the row's end
    b.plate = K.Slices(b, "BORDER", K.NAME_FRAME, K.PLATE_U, K.PLATE_V, 12, 12)
    b.plate[1]:SetHeight(42)
    b.plate[1]:SetPoint("TOPLEFT", b, "TOPLEFT", 40, 1)
    b.plate[3]:SetHeight(42)
    b.plate[3]:SetPoint("TOPRIGHT", b, "TOPRIGHT", 0, 1)
    b.name = UI.Text(b, 12, C.text)
    b.name:SetPoint("LEFT", b.plate[1], "LEFT", 10, 0)
    UI.OneLine(b.name, CHOICE_W - 40 - 110)
    b.tag = UI.Text(b, 11, C.dim, "body", "RIGHT")
    b.tag:SetPoint("RIGHT", b.plate[3], "RIGHT", -10, 0)
    UI.OneLine(b.tag, 80)
    b.tag:SetText(K.FAMILY_NAMES[f] or "")
    b.glow = questHighlight(b, b, "HIGHLIGHT")
    -- the chosen one: the same rims on a frame above the row, so they also light the icon's edge
    b.chosen = CreateFrame("Frame", nil, b)
    b.chosen:SetAllPoints(b)
    b.chosen.parts = questHighlight(b.chosen, b, "OVERLAY")
    b.chosen:Hide()
    function b:SetSlotChecked(on)
        if on then self.chosen:Show() else self.chosen:Hide() end
    end
    b.family = f
    b:RegisterForClicks("LeftButtonUp")
    b:SetScript("OnClick", function(self)
        if sum.claimed or sum.pending then
            return
        end
        local id, family = Cafe.StaffRecipe(self.family), self.family
        -- right after End Shift the shared CSHIFT/CSTAFF gate is still shut: the choice shows as asked at once and goes
        -- out when the gate opens (dropped if it was given back meanwhile)
        if id and Cafe.SendWhenReady("CSTAFF", { id }, function()
            return sum.pending == family
        end, function()
            if sum.pending == family then
                sum.pending, sum.pendingToken = nil, nil
                CW.RefreshSummary()
            end
        end) then
            CW.StaffPending(family)
        end
    end)
    b:SetScript("OnEnter", function(self)
        local r = Cafe.StaffRecipe(self.family) and Cafe.Recipe(Cafe.StaffRecipe(self.family))
        UI.ShowTooltip(self, { U.Safe(r and r.name or K.FAMILY_NAMES[self.family]),
            { K.BUFF_LONG[self.family] or "", C.text, true } })
    end)
    b:SetScript("OnLeave", hideTip)
    staff.choices[i] = b
end
sum.staff = staff
sum.ok = UI.Button(sum.content, 110, 22, "Close", "red")
sum.ok:SetPoint("BOTTOM", sum.content, "BOTTOM", 0, 2)
sum.ok:SetScript("OnClick", function()
    sum:Hide()
end)

-- The Staff Drink is claimed only once the server says so: CSTAFF sent makes the choice pending (the others off, "Asking
-- for your drink..."); a CAFST with flag 16 cleared or a CAFBF with that family's timer up confirms it; ERR CSTAFF (or
-- no answer in CW.STAFF_WAIT s) gives the choice back.
CW.STAFF_WAIT = 10
CW.STAFF_KEYS = { C = "coffeeSec", T = "teaSec", M = "shakeSec" }
local function buffLeft(family)
    local b = S.cafeBuffs
    return b and Cafe.Left(b, CW.STAFF_KEYS[family] or "") or 0
end

function CW.StaffPending(family)
    sum.pending, sum.pendingLeft = family, buffLeft(family)
    local token = {}
    sum.pendingToken = token
    ns.After(CW.STAFF_WAIT, function()
        if sum.pendingToken == token and sum.pending then
            sum.pending = nil
            CW.RefreshSummary()
        end
    end)
    CW.RefreshSummary()
end

function CW.StaffConfirm()
    if sum.pending then
        sum.claimed, sum.pending, sum.pendingToken = sum.pending, nil, nil
        CW.RefreshSummary()
    end
end

ns.On("ERR", function(e)
    if e and e.op == "CSTAFF" and sum.pending then
        sum.pending, sum.pendingToken = nil, nil
        CW.RefreshSummary()
    end
end)

ns.On("STATE", function(topic)
    if not sum.pending then
        return
    end
    if topic == "CAFST" and S.cafeState and not hasBit(S.cafeState.flags, 16) then
        CW.StaffConfirm()
    elseif topic == "CAFBF" and buffLeft(sum.pending) > (sum.pendingLeft or 0) + 5 then
        CW.StaffConfirm()
    end
end)

-- the Shift tab's Claim Staff Drink: the card again, with the last summary or only the choice
function CW.OpenStaffClaim()
    sum.claimed = nil
    if sum:IsShown() then
        CW.RefreshSummary()
    else
        sum:Show()
    end
end

function CW.RefreshSummary()
    local s = S.cafeSummary
    local bare = s == nil
    if bare and not (S.cafeState and hasBit(S.cafeState.flags, 16)) and not sum.claimed and not sum.pending then
        return
    end
    s = s or {}
    if sum.title then
        sum.title:SetText(bare and "Staff Drink" or "Shift Complete")
    end
    for _, lv in ipairs(sum.lines) do
        shown(lv, not bare)
    end
    shown(sum.tips, not bare)
    if bare then
        sum.reason:SetText("Your Staff Drink for today is waiting.")
        UI.SetColor(sum.reason, C.text)
    else
        sum.reason:SetText(CW.REASONS[s.reason] or "Your shift ended.")
        UI.SetColor(sum.reason, (s.reason == "E") and C.text or C.orange)
    end
    local drinks = s.drinks or 0
    local L = sum.lines
    L[1]:SetValue(U.Clock(s.shiftSec or 0))
    L[2]:SetValue(tostring(drinks))
    local perfects = s.perfects or 0
    L[3]:SetValue(drinks > 0 and (perfects .. " (" .. floor(perfects * 100 / drinks + 0.5) .. "%)") or "-")
    L[4]:SetValue((s.bestStreak or 0) > 0 and ("×" .. s.bestStreak) or "-")
    -- the coins need their |T codes: set the value text directly (LabelValue escapes '|')
    L[5]:SetValue("")
    sum.tips:SetCopper(s.tipsCopper or 0)
    sum.tips:ClearAllPoints()
    sum.tips:SetPoint("LEFT", L[5], "LEFT", ceil(L[5]:GetStringWidth() or 30) + 2, 0)
    L[6]:SetValue("+" .. U.Commas(s.xp or 0))
    L[7]:SetValue(U.Commas(s.points or 0))
    local capped = not bare and (s.xpLost or 0) > 0
    if capped then
        sum.cap:SetText(U.Commas(s.xpLost) .. " XP went over the daily cap.")
        sum.cap:Show()
    else
        sum.cap:SetText("")
        sum.cap:Hide()
    end
    local can = s.staffDrink == 1 or (S.cafeState and hasBit(S.cafeState.flags, 16)) or sum.claimed or sum.pending
    can = can and true or false
    -- the Staff Drink under the cap line or straight under the stats (under the reason with no stats); the card ends
    -- under the last one shown
    local above = bare and (CW.SUM_BARE_Y - CW.SUM_STAFF_GAP)
        or (CW.SUM_STATS_BOTTOM + (capped and (CW.SUM_CAP_GAP + CW.SUM_CAP_H) or 0))
    staff:ClearAllPoints()
    staff:SetPoint("TOP", sum.content, "TOP", 0, -(above + CW.SUM_STAFF_GAP))
    sum:SetHeight(CW.SummaryHeight(capped, can, bare))
    if can then
        staff:Show()
        for _, b in ipairs(staff.choices) do
            local id = Cafe.StaffRecipe(b.family)
            local r = id and Cafe.Recipe(id)
            b.icon:SetTexture(UI.IconPath(Cafe.Icon("family", b.family)))
            UI.SetText(b.name, r and r.name or K.FAMILY_NAMES[b.family])
            local picked = sum.claimed or sum.pending
            local chosen = picked == b.family
            b:SetSlotChecked(chosen)
            b.icon:SetDesaturated(picked ~= nil and not chosen)
            if id and not picked then b:Enable() else b:Disable() end
        end
        if sum.claimed then
            staff.note:SetText("Enjoy your Staff Drink.")
        elseif sum.pending then
            staff.note:SetText("Asking for your Staff Drink...")
        else
            staff.note:SetText("A free drink of your choice, once a day.")
        end
    else
        staff:Hide()
    end
end

function sum:OnOpen()
    CW.RefreshSummary()
end

-- The card waits out a fight or a death: combat ends the shift (CAFSUM C comes about 100 ms after
-- PLAYER_REGEN_DISABLED), and a card in the screen's middle, on the dialog strata and taking clicks, would cover the
-- character, the target and the Release Spirit popup. A chat line says at once why the shift ended; the card opens on
-- PLAYER_REGEN_ENABLED, or PLAYER_ALIVE / PLAYER_UNGHOST out of combat, while that summary is still the last one.
local fighting = false
function CW.SummaryBlocked()
    if fighting or (InCombatLockdown and InCombatLockdown())
        or (UnitAffectingCombat and UnitAffectingCombat("player")) then
        return true
    end
    return (UnitIsDeadOrGhost and UnitIsDeadOrGhost("player")) and true or false
end

function CW.ShowSummary()
    if sum:IsShown() then
        CW.RefreshSummary()
    else
        sum:Show()
    end
end

ns.On("CAFE_SUMMARY", function(s)
    if not Cafe.Enabled() then
        return
    end
    sum.claimed, sum.pending, sum.pendingToken = nil, nil, nil
    if CW.SummaryBlocked() then
        sum.deferred = S.cafeSummary
        sum:Hide()
        local why = s and CW.REASONS[s.reason] or "Your shift ended."
        local dead = UnitIsDeadOrGhost and UnitIsDeadOrGhost("player")
        ns.Print("caf\195\169: " .. why .. " Your shift's summary opens "
            .. (dead and "when you are alive again." or "after the fight."))
        return
    end
    sum.deferred = nil
    CW.ShowSummary()
end)

function CW.ShowDeferredSummary()
    if sum.deferred and not CW.SummaryBlocked() then
        local s = sum.deferred
        sum.deferred = nil
        if s == S.cafeSummary and Cafe.Enabled() then
            CW.ShowSummary()
        end
    end
end

ns.RegisterEvent("PLAYER_REGEN_DISABLED", function()
    fighting = true
end)
ns.RegisterEvent("PLAYER_REGEN_ENABLED", function()
    fighting = false
    CW.ShowDeferredSummary()
end)
ns.RegisterEvent("PLAYER_ALIVE", CW.ShowDeferredSummary)
ns.RegisterEvent("PLAYER_UNGHOST", CW.ShowDeferredSummary)
ns.On("STATE", function(topic)
    if topic == "CAFST" and sum:IsShown() then
        CW.RefreshSummary()
    end
end)

------------------------------------------------------------------------------------------------------
-- /bh cafe model <name>: the café's M2 files in a Model frame, for checking ModelForge's modelFrame values
------------------------------------------------------------------------------------------------------
-- the names of spec 5.8 (World\Bleakhold\Cafe\<name>\BH_Cafe_<name>.m2) and the test cube
CW.MODEL_NAMES = {
    "EspressoSW", "EspressoOrg", "GrinderSW", "GrinderOrg", "BlenderSW", "BlenderOrg", "KettleStoveSW",
    "KettleStoveOrg", "ColdBoxSW", "ColdBoxOrg", "SyrupRackSW", "SyrupRackOrg", "CounterSW", "CounterOrg",
    "BackBarSW", "BackBarOrg", "ParasolSW", "ParasolOrg", "ChalkboardSW", "ChalkboardOrg", "CupSW", "MugOrg",
    "ShakeGlass", "TipJar", "Cube",
}
-- the viewer's box is the Shift tab's box, size for size, so the modelFrame values it prints frame the hero machine
-- there exactly as they did here; the window grows with it
CW.MV_W, CW.MV_H = 520, CW.MODEL_H + 200
CW.MV_STEP = { pos = 0.1, scale = 0.1, facing = 0.2 }
local mv
local mvKnown = {}
for _, n in ipairs(CW.MODEL_NAMES) do
    mvKnown[n:lower()] = n
end

function CW.ModelPath(name)
    return "World\\Bleakhold\\Cafe\\" .. name .. "\\BH_Cafe_" .. name .. ".m2"
end

local function mvLine()
    local x, y, z = mv.model:GetPosition()
    return string.format("position {%.2f, %.2f, %.2f} scale %.2f facing %.2f", x or 0, y or 0, z or 0,
        mv.scale or 1, mv.model:GetFacing() or 0)
end

local function mvUpdate(print)
    mv.line:SetText(mvLine())
    if print then
        ns.Print(mv.name .. ": " .. mvLine())
    end
end

local function mvBuild()
    mv = UI.Window("BleakholdCafeModelViewer", CW.MV_W, CW.MV_H, "Café Model", "INV_Misc_Gear_01")
    local MW = UI.ContentSize(CW.MV_W, CW.MV_H)
    local BOX_H = CW.MODEL_H
    mv.box = UI.Box(mv.content, CW.MODEL_W, BOX_H, C.card, C.border, nil, "edge")
    mv.box:SetPoint("TOP", mv.content, "TOP", 0, 0)
    mv.model = CreateFrame("Model", "BleakholdCafeModelView", mv.box)
    mv.model:SetPoint("TOPLEFT", mv.box, "TOPLEFT", 1, -1)
    mv.model:SetPoint("BOTTOMRIGHT", mv.box, "BOTTOMRIGHT", -1, 1)
    mv.model:EnableMouse(true)
    mv.model:EnableMouseWheel(true)
    mv.model:SetScript("OnMouseDown", function(self)
        self.turning = true
        self.lastX = GetCursorPosition()
    end)
    mv.model:SetScript("OnMouseUp", function(self)
        self.turning = false
        mvUpdate(true)
    end)
    mv.model:SetScript("OnUpdate", function(self)
        if self.turning then
            local x = GetCursorPosition()
            if x and self.lastX then
                self:SetFacing((self:GetFacing() or 0) + (x - self.lastX) * 0.02)
                self.lastX = x
                mvUpdate(false)
            end
        end
    end)
    mv.model:SetScript("OnMouseWheel", function(self, delta)
        local x, y, z = self:GetPosition()
        self:SetPosition((x or 0) + (delta or 0) * CW.MV_STEP.pos, y or 0, z or 0)
        mvUpdate(true)
    end)
    -- the controls: small red buttons, two rows
    mv.buttons = {}
    local function control(label, x, y, fn)
        local b = UI.Button(mv.content, 34, 20, label, "ghost")
        b:SetPoint("TOPLEFT", mv.content, "TOPLEFT", x, y)
        b:SetScript("OnClick", function()
            fn()
            mvUpdate(true)
        end)
        mv.buttons[#mv.buttons + 1] = b
        return b
    end
    local function nudge(axis, d)
        return function()
            local p = { mv.model:GetPosition() }
            p[axis] = (p[axis] or 0) + d
            mv.model:SetPosition(p[1] or 0, p[2] or 0, p[3] or 0)
        end
    end
    local axes = { "X", "Y", "Z" }
    for i, a in ipairs(axes) do
        local x = (i - 1) * 120
        local l = UI.Label(mv.content, a, 12)
        l:SetPoint("TOPLEFT", mv.content, "TOPLEFT", x + 4, -BOX_H - 16)
        control("-", x + 22, -BOX_H - 12, nudge(i, -CW.MV_STEP.pos))
        control("+", x + 58, -BOX_H - 12, nudge(i, CW.MV_STEP.pos))
    end
    local ls = UI.Label(mv.content, "Scale", 12)
    ls:SetPoint("TOPLEFT", mv.content, "TOPLEFT", 4, -BOX_H - 44)
    control("-", 52, -BOX_H - 40, function()
        mv.scale = max(0.05, (mv.scale or 1) - CW.MV_STEP.scale)
        mv.model:SetModelScale(mv.scale)
    end)
    control("+", 88, -BOX_H - 40, function()
        mv.scale = (mv.scale or 1) + CW.MV_STEP.scale
        mv.model:SetModelScale(mv.scale)
    end)
    local lf = UI.Label(mv.content, "Facing", 12)
    lf:SetPoint("TOPLEFT", mv.content, "TOPLEFT", 136, -BOX_H - 44)
    control("-", 190, -BOX_H - 40, function()
        mv.model:SetFacing((mv.model:GetFacing() or 0) - CW.MV_STEP.facing)
    end)
    control("+", 226, -BOX_H - 40, function()
        mv.model:SetFacing((mv.model:GetFacing() or 0) + CW.MV_STEP.facing)
    end)
    mv.reset = UI.Button(mv.content, 90, 22, "Reset", "red")
    mv.reset:SetPoint("TOPRIGHT", mv.content, "TOPRIGHT", 0, -BOX_H - 39)
    mv.reset:SetScript("OnClick", function()
        CW.LoadModel(mv.name)
        mvUpdate(true)
    end)
    mv.line = UI.Text(mv.content, 12, C.text)
    mv.line:SetPoint("TOPLEFT", mv.content, "TOPLEFT", 4, -BOX_H - 76)
    UI.OneLine(mv.line, MW - 8)
    mv.path = UI.Text(mv.content, 10, C.dim)
    mv.path:SetPoint("TOPLEFT", mv.line, "BOTTOMLEFT", 0, -4)
    UI.OneLine(mv.path, MW - 8)
    mv.hint = UI.Para(mv.content, 10, C.mute, MW - 8)
    mv.hint:SetPoint("TOPLEFT", mv.path, "BOTTOMLEFT", 0, -6)
    mv.hint:SetText("Nothing showing? The café models come with patch-4 (or the test patch): check the name and that "
        .. "the patch is installed. Drag to turn, the mouse wheel to zoom.")
    CW.modelViewer = mv
end

-- Load a model by name, from CafeData's view of it when it has one (the hero machines), else a neutral view.
function CW.LoadModel(name)
    local m
    for _, v in pairs(D.models or {}) do
        if v.name == name then
            m = v
        end
    end
    mv.name = name
    mv.model:SetModel(CW.ModelPath(name))
    local p = (m and m.position) or { 0, 0, 0 }
    mv.model:SetPosition(p[1] or 0, p[2] or 0, p[3] or 0)
    mv.scale = (m and m.scale) or 1
    mv.model:SetModelScale(mv.scale)
    mv.model:SetFacing((m and m.facing) or 0)
    UI.SetText(mv.title, "Café Model: " .. name)
    mv.path:SetText(U.Safe(CW.ModelPath(name)))
    mvUpdate(false)
end

-- /bh cafe model <name>: Cafe.lua's slash fires CAFE_MODEL with the name. Returns true, or false and why.
function CW.ShowModelViewer(name)
    local key = type(name) == "string" and name:match("^%s*(%S+)%s*$")
    local real = key and mvKnown[key:lower()]
    if not real then
        ns.Print("Usage: /bh cafe model <name>, one of: " .. table.concat(CW.MODEL_NAMES, ", "))
        return false, "unknown"
    end
    if not mv then
        mvBuild()
    end
    CW.LoadModel(real)
    mv:Show()
    ns.Print(real .. ": " .. mvLine())
    return true
end

ns.On("CAFE_MODEL", function(name)
    CW.ShowModelViewer(name)
end)
