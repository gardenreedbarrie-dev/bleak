-- Bleakhold: Animations tab of the Collections window and the emote wheel.
-- The tab lists every animation the character can play (search, category filter, pages of 14), previews
-- the selected one on the player model, plays it, and edits the emote wheel: four pages of eight slots,
-- saved per character. The wheel opens with its key binding (Ctrl+G by default): hold the key, point at
-- a slot and release to play it; a short tap leaves the wheel open for clicking.
-- Built-in animations are the client's own emotes (DoEmote); the list is data (Data.emotes), so more
-- dances can be added the same way.
local ADDON, ns = ...
local U, UI, Data = ns.U, ns.UI, ns.Data
local C = UI.C

local floor, max, min, sqrt, atan2, deg = math.floor, math.max, math.min, math.sqrt, math.atan2, math.deg

local A = {}
ns.Animations = A

A.GRID_COLS, A.GRID_ROWS = 2, 7
A.PAGE_SIZE = A.GRID_COLS * A.GRID_ROWS
A.WHEEL_SLOTS = 8
A.WHEEL_PAGES = 4
A.TAP_SECONDS = 0.25      -- a key press shorter than this leaves the wheel open for clicking
A.DEAD_ZONE = 40          -- cursor distance from the wheel centre below which no slot is chosen
A.BINDING = "BLEAKHOLD_EMOTEWHEEL"
A.DEFAULT_KEY = "CTRL-G"

A.page = 1
A.filter = "all"
A.wheelPage = 1

------------------------------------------------------------------------------------------------------
-- Catalogue
------------------------------------------------------------------------------------------------------
local byKey = {}
for _, e in ipairs(Data.emotes) do
    byKey[e.key] = e
end

function A.List()
    return Data.emotes
end

function A.Get(key)
    return key and byKey[key]
end

local categoryLabel = {}
for _, c in ipairs(Data.animationCategories) do
    categoryLabel[c.key] = c.label
end

function A.CategoryLabel(cat)
    return categoryLabel[cat] or "Animations"
end

-- Is `key` on any wheel page?
function A.OnWheel(key)
    local wheel = ns.cdb.wheel
    if type(wheel) ~= "table" then
        return false
    end
    for p = 1, A.WHEEL_PAGES do
        local page = wheel[p]
        for s = 1, A.WHEEL_SLOTS do
            if page and page[s] == key then
                return true
            end
        end
    end
    return false
end

-- Entries matching the search text (name or command) and the category filter.
function A.Filtered(search, filter)
    search = string.lower(search or "")
    filter = filter or "all"
    local out = {}
    for _, e in ipairs(A.List()) do
        local okCat = filter == "all" or e.cat == filter or (filter == "wheel" and A.OnWheel(e.key))
        local okText = search == "" or string.find(string.lower(e.name), search, 1, true)
            or string.find(e.cmd, search, 1, true)
        if okCat and okText then
            out[#out + 1] = e
        end
    end
    return out
end

------------------------------------------------------------------------------------------------------
-- Wheel storage (BleakholdCharDB.wheel = { [page] = { [slot] = key } })
------------------------------------------------------------------------------------------------------
-- Rebuilds the saved wheel from whatever is stored: unknown keys and malformed pages are dropped, a
-- missing wheel becomes the default one.
function A.EnsureWheel()
    local saved = ns.cdb.wheel
    local wheel = {}
    for p = 1, A.WHEEL_PAGES do
        wheel[p] = {}
        local src = type(saved) == "table" and saved[p] or nil
        if type(saved) ~= "table" then
            src = Data.defaultWheel[p]
        end
        if type(src) == "table" then
            for s = 1, A.WHEEL_SLOTS do
                local key = src[s]
                if type(key) == "string" and byKey[key] then
                    wheel[p][s] = key
                end
            end
        end
    end
    ns.cdb.wheel = wheel
    return wheel
end

function A.WheelEntry(page, slot)
    local wheel = ns.cdb.wheel
    local p = type(wheel) == "table" and wheel[page]
    return p and A.Get(p[slot]) or nil
end

function A.SetWheelSlot(page, slot, key)
    if page < 1 or page > A.WHEEL_PAGES or slot < 1 or slot > A.WHEEL_SLOTS then
        return false
    end
    if key ~= nil and not byKey[key] then
        return false
    end
    local wheel = type(ns.cdb.wheel) == "table" and ns.cdb.wheel or A.EnsureWheel()
    wheel[page] = wheel[page] or {}
    wheel[page][slot] = key
    ns.Fire("WHEEL")
    return true
end

-- Puts `key` in the first empty slot, starting on the wheel page shown in the editor. Returns page, slot
-- (or the slot it already has), or nil when the wheel is full.
function A.AddToWheel(key)
    if not byKey[key] then
        return nil
    end
    for p = 1, A.WHEEL_PAGES do
        for s = 1, A.WHEEL_SLOTS do
            local e = A.WheelEntry(p, s)
            if e and e.key == key then
                return p, s, true
            end
        end
    end
    for i = 0, A.WHEEL_PAGES - 1 do
        local p = (A.wheelPage - 1 + i) % A.WHEEL_PAGES + 1
        for s = 1, A.WHEEL_SLOTS do
            if not A.WheelEntry(p, s) then
                A.SetWheelSlot(p, s, key)
                return p, s
            end
        end
    end
    return nil
end

ns.On("DB_READY", function()
    A.EnsureWheel()
end)

------------------------------------------------------------------------------------------------------
-- Playing
------------------------------------------------------------------------------------------------------
function A.Perform(entry)
    if type(entry) == "string" then
        entry = A.Get(entry)
    end
    if not entry or not entry.token or not DoEmote then
        return false
    end
    DoEmote(entry.token)
    return true
end

------------------------------------------------------------------------------------------------------
-- The Animations tab (built inside the Collections window)
------------------------------------------------------------------------------------------------------
local CO = ns.Collections
local body = CO.body
local BH = CO.BH

local tab = CreateFrame("Frame", nil, body)
tab:SetAllPoints(body)
tab:Hide()
A.tab = tab

local LEFT, TOP = 16, 14
local ENTRY_W, ENTRY_H, ENTRY_GAP = 270, 52, 6
local GRID_W = A.GRID_COLS * ENTRY_W + (A.GRID_COLS - 1) * 10
local RIGHT_X = LEFT + GRID_W + 18
local RIGHT_W = CO.W - 2 - RIGHT_X - 16

-- Header row: count and category filter.
tab.count = UI.Text(tab, 12, C.dim)
tab.count:SetPoint("TOPLEFT", tab, "TOPLEFT", LEFT, -TOP - 6)
local filterItems = { { value = "all", text = "All animations" } }
for _, c in ipairs(Data.animationCategories) do
    filterItems[#filterItems + 1] = { value = c.key, text = c.label }
end
filterItems[#filterItems + 1] = { value = "wheel", text = "On the wheel" }
tab.filter = UI.Dropdown(tab, 150, function(value)
    A.filter = value
    A.page = 1
    A.Refresh()
end)
tab.filter:SetItems(filterItems)
tab.filter:SetValue("all", true)
tab.filter:SetPoint("TOPRIGHT", tab, "TOPLEFT", LEFT + GRID_W, -TOP)

-- Grid of entries.
local function entryTooltip(self)
    local e = self.entry
    if e then
        UI.ShowTooltip(self, { e.name, { e.cmd .. "  -  " .. A.CategoryLabel(e.cat), C.dim },
            "Click: preview. Double-click: play. Drag onto the wheel, or right-click to add it." })
    end
end

local function hideTooltip()
    if GameTooltip then
        GameTooltip:Hide()
    end
end

tab.entries = {}
for i = 1, A.PAGE_SIZE do
    local b = CreateFrame("Button", nil, tab)
    b:SetSize(ENTRY_W, ENTRY_H)
    local col, row = (i - 1) % A.GRID_COLS, floor((i - 1) / A.GRID_COLS)
    b:SetPoint("TOPLEFT", tab, "TOPLEFT", LEFT + col * (ENTRY_W + 10), -TOP - 34 - row * (ENTRY_H + ENTRY_GAP))
    UI.Backdrop(b, C.card, C.border)
    b.badge = UI.Badge(b, 40, nil, C.chip, C.goldDark)
    b.badge:SetPoint("LEFT", b, "LEFT", 6, 0)
    b.icon = b.badge:CreateTexture(nil, "ARTWORK")
    b.icon:SetSize(26, 26)
    b.icon:SetPoint("CENTER", b.badge, "CENTER", 0, 0)
    b.name = UI.Text(b, 13, C.text)
    b.name:SetPoint("TOPLEFT", b, "TOPLEFT", 54, -10)
    UI.OneLine(b.name, ENTRY_W - 80)
    b.cmd = UI.Text(b, 11, C.mute)
    b.cmd:SetPoint("TOPLEFT", b.name, "BOTTOMLEFT", 0, -3)
    UI.OneLine(b.cmd, ENTRY_W - 80)
    b.mark = b:CreateTexture(nil, "OVERLAY")
    b.mark:SetSize(14, 14)
    b.mark:SetPoint("TOPRIGHT", b, "TOPRIGHT", -8, -8)
    UI.SetEmoteGlyph(b.mark, "wheel")
    b.mark:SetVertexColor(UI.Rgb(C.teal))
    b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    b:RegisterForDrag("LeftButton")
    b:SetScript("OnClick", function(self, button)
        if not self.entry then
            return
        end
        if button == "RightButton" then
            A.AddToWheel(self.entry.key)
        else
            A.Select(self.entry)
        end
    end)
    b:SetScript("OnDoubleClick", function(self)
        if self.entry then
            A.Select(self.entry)
            A.Perform(self.entry)
        end
    end)
    b:SetScript("OnDragStart", function(self)
        A.BeginDrag(self.entry)
    end)
    b:SetScript("OnDragStop", function()
        A.EndDrag()
    end)
    b:SetScript("OnEnter", entryTooltip)
    b:SetScript("OnLeave", hideTooltip)
    tab.entries[i] = b
end

-- Pager.
tab.prev = UI.Button(tab, 28, 24, "", "dark")
tab.prev.icon = UI.Glyph(tab.prev, "left", 14, C.text)
tab.prev.icon:SetPoint("CENTER")
tab.next = UI.Button(tab, 28, 24, "", "dark")
tab.next.icon = UI.Glyph(tab.next, "right", 14, C.text)
tab.next.icon:SetPoint("CENTER")
tab.pageText = UI.Text(tab, 12, C.mid, "body", "CENTER")
tab.pageText:SetWidth(110)
local pagerY = -TOP - 34 - A.GRID_ROWS * (ENTRY_H + ENTRY_GAP) - 4
tab.pageText:SetPoint("TOP", tab, "TOPLEFT", LEFT + GRID_W / 2, pagerY - 5)
tab.prev:SetPoint("TOPRIGHT", tab, "TOPLEFT", LEFT + GRID_W / 2 - 58, pagerY)
tab.next:SetPoint("TOPLEFT", tab, "TOPLEFT", LEFT + GRID_W / 2 + 58, pagerY)
tab.prev:SetScript("OnClick", function()
    A.SetPage(A.page - 1)
end)
tab.next:SetScript("OnClick", function()
    A.SetPage(A.page + 1)
end)
tab.empty = UI.Text(tab, 13, C.dim, "body", "CENTER")
tab.empty:SetPoint("TOP", tab, "TOPLEFT", LEFT + GRID_W / 2, -TOP - 140)
tab.empty:SetText("Nothing matches the search.")

-- Right column: preview, buttons, wheel editor.
local right = CreateFrame("Frame", nil, tab)
right:SetSize(RIGHT_W, BH - 2 * TOP)
right:SetPoint("TOPLEFT", tab, "TOPLEFT", RIGHT_X, -TOP)
tab.right = right

-- Fixed rows of the right column (y from its top).
local MODEL_H = 168
local Y_NAME, Y_CMD, Y_BUTTONS, Y_WHEEL_LABEL = -(MODEL_H + 10), -(MODEL_H + 35), -(MODEL_H + 55), -(MODEL_H + 97)
local EDIT_RADIUS, EDIT_SLOT = 62, 34
local editCenterY = Y_WHEEL_LABEL - 20 - EDIT_RADIUS - EDIT_SLOT / 2

local modelBox = UI.Box(right, RIGHT_W, MODEL_H, "101216", C.border)
modelBox:SetPoint("TOPLEFT", right, "TOPLEFT", 0, 0)
local model = CreateFrame("PlayerModel", "BleakholdAnimationModel", modelBox)
model:SetPoint("TOPLEFT", modelBox, "TOPLEFT", 2, -2)
model:SetPoint("BOTTOMRIGHT", modelBox, "BOTTOMRIGHT", -2, 2)
model:EnableMouse(true)
model:SetScript("OnMouseDown", function(self)
    self.turning = true
    self.lastX = GetCursorPosition()
end)
model:SetScript("OnMouseUp", function(self)
    self.turning = false
end)
model:SetScript("OnUpdate", function(self)
    if self.turning then
        local x = GetCursorPosition()
        if x and self.lastX then
            self:SetFacing((self:GetFacing() or 0) + (x - self.lastX) * 0.02)
            self.lastX = x
        end
    end
end)
A.model = model

right.name = UI.Text(right, 18, C.goldPale, "title")
right.name:SetPoint("TOPLEFT", right, "TOPLEFT", 0, Y_NAME)
UI.OneLine(right.name, RIGHT_W)
right.cmd = UI.Text(right, 11, C.dim)
right.cmd:SetPoint("TOPLEFT", right, "TOPLEFT", 0, Y_CMD)
UI.OneLine(right.cmd, RIGHT_W)
right.play = UI.Button(right, (RIGHT_W - 8) / 2, 30, "Play", "gold", 13)
right.play:SetPoint("TOPLEFT", right, "TOPLEFT", 0, Y_BUTTONS)
right.add = UI.Button(right, (RIGHT_W - 8) / 2, 30, "Add to Wheel", "dark", 13)
right.add:SetPoint("TOPRIGHT", right, "TOPRIGHT", 0, Y_BUTTONS)
right.play:SetScript("OnClick", function()
    A.Perform(A.selected)
end)
right.add:SetScript("OnClick", function()
    if A.selected then
        A.AddToWheel(A.selected.key)
    end
end)

right.wheelLabel = UI.Text(right, 11, C.dim)
right.wheelLabel:SetPoint("TOPLEFT", right, "TOPLEFT", 0, Y_WHEEL_LABEL)
right.wheelLabel:SetText("EMOTE WHEEL")

local editor = CreateFrame("Frame", nil, right)
editor:SetSize(2 * (EDIT_RADIUS + EDIT_SLOT), 2 * (EDIT_RADIUS + EDIT_SLOT))
editor:SetPoint("CENTER", right, "TOPLEFT", RIGHT_W / 2, editCenterY)
editor.ring = editor:CreateTexture(nil, "BACKGROUND")
editor.ring:SetTexture(UI.ART .. "Ring")
editor.ring:SetSize(2 * EDIT_RADIUS, 2 * EDIT_RADIUS)
editor.ring:SetPoint("CENTER")
editor.ring:SetVertexColor(UI.Rgb(C.border))
editor.pageText = UI.Text(editor, 13, C.mid, "body", "CENTER")
editor.pageText:SetPoint("CENTER", editor, "CENTER", 0, 0)
right.editor = editor

-- Slot positions: slot 1 at the top, then clockwise.
local function slotOffset(slot, radius)
    local a = math.rad(90 - (slot - 1) * 360 / A.WHEEL_SLOTS)
    return math.cos(a) * radius, math.sin(a) * radius
end
A.SlotOffset = slotOffset

editor.slots = {}
for s = 1, A.WHEEL_SLOTS do
    local b = CreateFrame("Button", nil, editor)
    b:SetSize(EDIT_SLOT, EDIT_SLOT)
    local x, y = slotOffset(s, EDIT_RADIUS)
    b:SetPoint("CENTER", editor, "CENTER", x, y)
    b.badge = UI.Badge(b, EDIT_SLOT, nil, C.chip, C.goldDark)
    b.badge:SetAllPoints(b)
    b.icon = b.badge:CreateTexture(nil, "ARTWORK")
    b.icon:SetSize(22, 22)
    b.icon:SetPoint("CENTER", b.badge, "CENTER", 0, 0)
    b.slot = s
    b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    b:SetScript("OnClick", function(self, button)
        local e = A.WheelEntry(A.wheelPage, self.slot)
        if button == "RightButton" then
            A.SetWheelSlot(A.wheelPage, self.slot, nil)
        elseif e then
            A.Select(e)
        elseif A.selected then
            A.SetWheelSlot(A.wheelPage, self.slot, A.selected.key)
        end
    end)
    b:SetScript("OnEnter", function(self)
        local e = A.WheelEntry(A.wheelPage, self.slot)
        if e then
            UI.ShowTooltip(self, { e.name, { e.cmd, C.dim }, "Click: preview. Right-click: empty the slot." })
        else
            UI.ShowTooltip(self, { "Empty slot", "Drag an animation here, or click to put the selected one in it." })
        end
    end)
    b:SetScript("OnLeave", hideTooltip)
    editor.slots[s] = b
end
editor.prev = UI.Button(right, 24, 24, "", "dark")
editor.prev.icon = UI.Glyph(editor.prev, "left", 12, C.text)
editor.prev.icon:SetPoint("CENTER")
editor.prev:SetPoint("CENTER", right, "TOPLEFT", 14, editCenterY)
editor.next = UI.Button(right, 24, 24, "", "dark")
editor.next.icon = UI.Glyph(editor.next, "right", 12, C.text)
editor.next.icon:SetPoint("CENTER")
editor.next:SetPoint("CENTER", right, "TOPLEFT", RIGHT_W - 14, editCenterY)
editor.prev:SetScript("OnClick", function()
    A.SetWheelPage(A.wheelPage - 1)
end)
editor.next:SetScript("OnClick", function()
    A.SetWheelPage(A.wheelPage + 1)
end)

right.hint = UI.Text(right, 11, C.mute, "body", "CENTER")
right.hint:SetPoint("BOTTOM", right, "BOTTOM", 0, 0)
right.hint:SetWidth(RIGHT_W)

-- Drag and drop onto the wheel editor: an icon follows the cursor; releasing over a slot fills it.
local dragIcon = CreateFrame("Frame", "BleakholdAnimationDrag", UIParent)
dragIcon:SetSize(36, 36)
dragIcon:SetFrameStrata("TOOLTIP")
dragIcon:Hide()
dragIcon.badge = UI.Badge(dragIcon, 36, nil, C.chip, C.gold)
dragIcon.badge:SetAllPoints(dragIcon)
dragIcon.icon = dragIcon.badge:CreateTexture(nil, "ARTWORK")
dragIcon.icon:SetSize(24, 24)
dragIcon.icon:SetPoint("CENTER", dragIcon.badge, "CENTER", 0, 0)
dragIcon:SetScript("OnUpdate", function(self)
    local x, y = GetCursorPosition()
    local s = UIParent:GetEffectiveScale()
    self:ClearAllPoints()
    self:SetPoint("CENTER", UIParent, "BOTTOMLEFT", x / s, y / s)
end)

function A.BeginDrag(entry)
    if not entry then
        return
    end
    A.dragging = entry
    UI.SetEmoteGlyph(dragIcon.icon, entry.glyph)
    dragIcon.icon:SetVertexColor(UI.Rgb(C.goldLight))
    dragIcon:Show()
end

function A.EndDrag()
    local entry = A.dragging
    A.dragging = nil
    dragIcon:Hide()
    if not entry then
        return
    end
    for s, b in ipairs(editor.slots) do
        if b:IsVisible() and b:IsMouseOver() then
            A.SetWheelSlot(A.wheelPage, s, entry.key)
            return
        end
    end
end

------------------------------------------------------------------------------------------------------
-- Tab logic
------------------------------------------------------------------------------------------------------
local function setIcon(texture, entry, color)
    UI.SetEmoteGlyph(texture, entry and entry.glyph or "plus")
    texture:SetVertexColor(UI.Rgb(color or (entry and C.goldLight or C.mute)))
end

function A.Pages(count)
    return max(1, floor((count + A.PAGE_SIZE - 1) / A.PAGE_SIZE))
end

function A.SetPage(page)
    local list = A.Filtered(CO.search, A.filter)
    A.page = U.Clamp(page, 1, A.Pages(#list))
    A.Refresh()
end

function A.SetWheelPage(page)
    A.wheelPage = (page - 1) % A.WHEEL_PAGES + 1
    A.Refresh()
end

-- The model is loaded after SetUnit returns, so the sequence is set again once it has had time to load.
local previewTimer

function A.Preview(entry)
    model:SetUnit("player")
    model:SetFacing(0)
    if not entry then
        return
    end
    local anim = U.Clamp(entry.anim or 0, 0, 505)
    model:SetSequence(anim)
    ns.Cancel(previewTimer)
    previewTimer = ns.After(0.3, function()
        if A.selected == entry then
            model:SetSequence(anim)
        end
    end)
end

function A.Select(entry)
    A.selected = entry
    A.Preview(entry)
    A.Refresh()
end

function A.RefreshWheelEditor()
    for s, b in ipairs(editor.slots) do
        local e = A.WheelEntry(A.wheelPage, s)
        setIcon(b.icon, e)
        local on = e and A.selected and e.key == A.selected.key
        b.badge.ring:SetVertexColor(UI.Rgb(on and C.gold or (e and C.goldDark or C.chipBorder)))
    end
    editor.pageText:SetText(A.wheelPage .. " / " .. A.WHEEL_PAGES)
end

function A.KeyText()
    local key = GetBindingKey and GetBindingKey(A.BINDING)
    return key
end

function A.Refresh()
    if not tab:IsShown() then
        return
    end
    local list = A.Filtered(CO.search, A.filter)
    local pages = A.Pages(#list)
    A.page = U.Clamp(A.page, 1, pages)
    local total = #A.List()
    tab.count:SetText(string.upper(A.CategoryLabel(A.filter ~= "all" and A.filter ~= "wheel" and A.filter or nil))
        .. "  |cffECE7DD" .. #list .. "|r of " .. total)
    local first = (A.page - 1) * A.PAGE_SIZE
    for i, b in ipairs(tab.entries) do
        local e = list[first + i]
        b.entry = e
        if e then
            setIcon(b.icon, e)
            UI.SetText(b.name, e.name)
            UI.SetText(b.cmd, e.cmd)
            local sel = A.selected and A.selected.key == e.key
            UI.Colors(b, sel and C.active or C.card, sel and C.gold or C.border)
            UI.SetColor(b.name, sel and C.goldPale or C.text)
            if A.OnWheel(e.key) then
                b.mark:Show()
            else
                b.mark:Hide()
            end
            b:Show()
        else
            b:Hide()
        end
    end
    if #list == 0 then
        tab.empty:Show()
    else
        tab.empty:Hide()
    end
    tab.pageText:SetText("Page " .. A.page .. " / " .. pages)
    tab.prev:SetActive(A.page > 1)
    tab.next:SetActive(A.page < pages)

    local sel = A.selected
    if sel then
        UI.SetText(right.name, sel.name)
        UI.SetText(right.cmd, sel.cmd .. "  -  " .. A.CategoryLabel(sel.cat) .. (sel.text and ("  -  " .. sel.text) or ""))
    else
        right.name:SetText("Animations")
        right.cmd:SetText("Pick an animation to preview it.")
    end
    right.play:SetActive(sel ~= nil)
    right.add:SetActive(sel ~= nil and not A.OnWheel(sel.key))
    A.RefreshWheelEditor()
    local key = A.KeyText()
    right.hint:SetText(key and ("Hold " .. key .. " in the game to use the wheel.")
        or "Bind a key to the emote wheel in Key Bindings, Bleakhold.")
end

-- Called by the Collections window when the tab is shown.
function A.ShowTab()
    tab:Show()
    if not A.selected then
        A.selected = A.List()[1]
        A.Preview(A.selected)
    end
    A.Refresh()
end

function A.HideTab()
    tab:Hide()
    A.EndDrag()
end

ns.On("WHEEL", function()
    A.Refresh()
    if A.wheel and A.wheel:IsShown() then
        A.RefreshWheel(true)
    end
end)

------------------------------------------------------------------------------------------------------
-- The emote wheel
------------------------------------------------------------------------------------------------------
local WHEEL_SIZE, WHEEL_RADIUS, WHEEL_SLOT = 330, 118, 58

local wheel = CreateFrame("Frame", "BleakholdEmoteWheelFrame", UIParent)
wheel:SetSize(WHEEL_SIZE, WHEEL_SIZE)
wheel:SetFrameStrata("DIALOG")
wheel:SetClampedToScreen(true)
wheel:EnableMouse(true)
wheel:EnableMouseWheel(true)
wheel:Hide()
A.wheel = wheel
UISpecialFrames[#UISpecialFrames + 1] = "BleakholdEmoteWheelFrame"

wheel.bg = UI.Disc(wheel, WHEEL_SIZE, C.bg, "BACKGROUND", 0.82)
wheel.bg:SetPoint("CENTER")
wheel.ring = wheel:CreateTexture(nil, "BORDER")
wheel.ring:SetTexture(UI.ART .. "Ring")
wheel.ring:SetSize(WHEEL_SIZE, WHEEL_SIZE)
wheel.ring:SetPoint("CENTER")
wheel.ring:SetVertexColor(UI.Rgb(C.goldDark))
wheel.inner = wheel:CreateTexture(nil, "BORDER")
wheel.inner:SetTexture(UI.ART .. "Ring")
wheel.inner:SetSize(2 * A.DEAD_ZONE + 40, 2 * A.DEAD_ZONE + 40)
wheel.inner:SetPoint("CENTER")
wheel.inner:SetVertexColor(UI.Rgb(C.border))
wheel.title = UI.Text(wheel, 15, C.goldPale, "title", "CENTER")
wheel.title:SetPoint("CENTER", wheel, "CENTER", 0, 8)
wheel.title:SetWidth(110)
wheel.pageText = UI.Text(wheel, 11, C.dim, "body", "CENTER")
wheel.pageText:SetPoint("TOP", wheel.title, "BOTTOM", 0, -4)
wheel.hint = UI.Text(wheel, 11, C.mid, "body", "CENTER")
wheel.hint:SetPoint("TOP", wheel, "BOTTOM", 0, -6)
wheel.hint:SetWidth(WHEEL_SIZE + 80)
wheel.hint:SetText("Release or click to play  -  Mouse wheel: next page  -  Right-click: close")

wheel.slots = {}
for s = 1, A.WHEEL_SLOTS do
    local f = CreateFrame("Frame", nil, wheel)
    f:SetSize(WHEEL_SLOT, WHEEL_SLOT)
    local x, y = slotOffset(s, WHEEL_RADIUS)
    f:SetPoint("CENTER", wheel, "CENTER", x, y)
    f.badge = UI.Badge(f, WHEEL_SLOT, nil, C.chip, C.goldDark)
    f.badge:SetAllPoints(f)
    f.icon = f.badge:CreateTexture(nil, "ARTWORK")
    f.icon:SetSize(36, 36)
    f.icon:SetPoint("CENTER", f.badge, "CENTER", 0, 0)
    f.name = UI.Text(f, 11, C.text, "body", "CENTER")
    f.name:SetPoint("TOP", f, "BOTTOM", 0, -2)
    UI.OneLine(f.name, 90)
    wheel.slots[s] = f
end

-- The slot the cursor points at (direction from the centre, outside the dead zone), or nil.
function A.HoveredSlot()
    local x, y = GetCursorPosition()
    local scale = wheel:GetEffectiveScale()
    local cx, cy = wheel:GetCenter()
    if not x or not cx or not scale or scale <= 0 then
        return nil
    end
    local dx, dy = x / scale - cx, y / scale - cy
    if sqrt(dx * dx + dy * dy) < A.DEAD_ZONE then
        return nil
    end
    local clockwise = (90 - deg(atan2(dy, dx))) % 360
    return floor((clockwise + 180 / A.WHEEL_SLOTS) / (360 / A.WHEEL_SLOTS)) % A.WHEEL_SLOTS + 1
end

-- Runs every frame while the wheel is open; redraws only when the hovered slot or the page changed.
local drawn = {}

function A.RefreshWheel(force)
    local hovered = A.HoveredSlot()
    local hoveredEntry = hovered and A.WheelEntry(A.wheelPage, hovered)
    if not hoveredEntry then
        hovered = nil
    end
    A.hovered = hovered
    if not force and drawn.hovered == hovered and drawn.page == A.wheelPage then
        return
    end
    drawn.hovered, drawn.page = hovered, A.wheelPage
    for s, f in ipairs(wheel.slots) do
        local e = A.WheelEntry(A.wheelPage, s)
        local on = hoveredEntry and s == hovered
        setIcon(f.icon, e, on and C.goldPale or nil)
        f.badge.fill:SetVertexColor(UI.Rgb(on and C.active or C.chip))
        f.badge.ring:SetVertexColor(UI.Rgb(on and C.gold or (e and C.goldDark or C.chipBorder)))
        UI.SetText(f.name, e and e.name or "")
        UI.SetColor(f.name, on and C.goldPale or C.mid)
    end
    UI.SetText(wheel.title, hoveredEntry and hoveredEntry.name or "Emotes")
    wheel.pageText:SetText("Page " .. A.wheelPage .. " / " .. A.WHEEL_PAGES)
end

local function placeAtCursor()
    local x, y = GetCursorPosition()
    local s = UIParent:GetEffectiveScale()
    wheel:ClearAllPoints()
    if x and s and s > 0 then
        wheel:SetPoint("CENTER", UIParent, "BOTTOMLEFT", x / s, y / s)
    else
        wheel:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
    end
end

function A.OpenWheel(held)
    A.wheelHeld = held and true or false
    A.wheelOpenedAt = GetTime()
    placeAtCursor()
    wheel:Show()
    A.RefreshWheel(true)
end

function A.CloseWheel()
    A.wheelHeld = false
    wheel:Hide()
end

-- Plays the slot the cursor points at, then closes. Returns the entry played.
function A.ReleaseWheel()
    A.RefreshWheel()
    local entry = A.hovered and A.WheelEntry(A.wheelPage, A.hovered)
    A.CloseWheel()
    if entry then
        A.Perform(entry)
    end
    return entry
end

-- Key binding: hold to choose and release to play; a short tap keeps the wheel open for clicking, and
-- pressing the key again closes it.
function A.WheelKey(keystate)
    if keystate == "up" then
        if not wheel:IsShown() or not A.wheelHeld then
            return
        end
        A.wheelHeld = false
        A.RefreshWheel()
        if GetTime() - (A.wheelOpenedAt or 0) < A.TAP_SECONDS and not A.hovered then
            return
        end
        A.ReleaseWheel()
        return
    end
    if wheel:IsShown() then
        A.CloseWheel()
    else
        A.OpenWheel(true)
    end
end

function BleakholdEmoteWheel(keystate)
    ns.SafeCall(A.WheelKey, keystate)
end

wheel:SetScript("OnUpdate", function()
    A.RefreshWheel()
end)
wheel:SetScript("OnMouseUp", function(self, button)
    if button == "RightButton" then
        A.CloseWheel()
    else
        A.ReleaseWheel()
    end
end)
wheel:SetScript("OnMouseWheel", function(self, delta)
    A.wheelPage = ((A.wheelPage - 1) + (delta and delta < 0 and 1 or -1)) % A.WHEEL_PAGES + 1
    A.RefreshWheel(true)
end)
wheel:SetScript("OnHide", function()
    A.wheelHeld = false
end)

------------------------------------------------------------------------------------------------------
-- Default key: Ctrl+G, once per account, only when neither the key nor the action is bound yet.
------------------------------------------------------------------------------------------------------
function A.OfferDefaultKey()
    local opts = ns.db.options
    if opts.wheelKeyOffered or not SetBinding or not GetBindingAction then
        return
    end
    if InCombatLockdown and InCombatLockdown() then
        return
    end
    opts.wheelKeyOffered = true
    if GetBindingKey(A.BINDING) then
        return
    end
    local current = GetBindingAction(A.DEFAULT_KEY)
    if current == nil or current == "" then
        if SetBinding(A.DEFAULT_KEY, A.BINDING) and SaveBindings and GetCurrentBindingSet then
            SaveBindings(GetCurrentBindingSet())
        end
    else
        ns.Print("Emote wheel: " .. A.DEFAULT_KEY .. " is taken; bind a key in Key Bindings, Bleakhold.")
    end
end

-- After entering the world the saved key bindings are in place.
ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    ns.After(1, A.OfferDefaultKey)
end)

------------------------------------------------------------------------------------------------------
-- Commands and openers
------------------------------------------------------------------------------------------------------
UI.RegisterOpener("animations", function(toggle)
    if toggle and CO.frame:IsShown() and CO.tab == "animations" then
        CO.frame:Hide()
        return
    end
    CO.ShowTab("animations")
end)

ns.AddCommand("animations", "open the Animations collection", function()
    UI.Open("animations", true)
end)

ns.AddCommand("wheel", "open the emote wheel", function()
    if wheel:IsShown() then
        A.CloseWheel()
    else
        A.OpenWheel(false)
    end
end)

ns.AddCommand("emote", "play an animation: /bh emote <name>", function(args)
    local want = string.lower(strtrim and strtrim(args or "") or (args or "")):gsub("^/", "")
    for _, e in ipairs(A.List()) do
        if e.key == want or string.lower(e.name) == want or e.cmd == "/" .. want then
            A.Perform(e)
            return
        end
    end
    ns.Print("usage: /bh emote <name>, for example /bh emote dance")
end)
