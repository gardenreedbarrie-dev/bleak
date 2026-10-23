-- Bleakhold: shared UI primitives (3.3.5a API only: backdrops, textures tinted with SetVertexColor,
-- solid colours through the White texture, no templates from FrameXML).
local ADDON, ns = ...
local U = ns.U

local floor, ceil, max, min, cos, sin, pi = math.floor, math.ceil, math.max, math.min, math.cos, math.sin, math.pi

local UI = {}
ns.UI = UI

UI.ART = "Interface\\AddOns\\Bleakhold\\Art\\"
UI.WHITE = UI.ART .. "White"
UI.FONT_BODY = "Fonts\\FRIZQT__.TTF"
UI.FONT_TITLE = "Fonts\\MORPHEUS.TTF"
UI.FONT_NARROW = "Fonts\\ARIALN.TTF"

-- Palette of the Bleakhold designs.
local C = {
    bg = "0B0C0F", panel = "15181D", header = "1B1F25", card = "1B1F25", rail = "111317", border = "2E333B",
    strong = "4A4F57", chip = "23272E", chipBorder = "3A3F47", gold = "C9A25A", goldLight = "E5C07B",
    goldPale = "F1D9A0", goldDark = "8A6A35", teal = "6CC6D9", text = "ECE7DD", dim = "B8B2A6", mid = "CFC8BB",
    mute = "8C877D", purple = "B57EDC", epic = "C9A2F5", eraBg = "1E1A24", eraBorder = "5A4A2C", active = "2A2232",
    orange = "FF9D3B", red = "E5604F", silver = "C8CDD3", bronze = "D19A6C", track = "2A2F37", deep = "0F1114",
    zebra = "191C21", setBg = "1F1B26", setBorder = "4E3F66", slotBg = "2B2336",
}
UI.C = C

-- Glyph atlas cells, same order as GLYPHS in Tools/UiLint/make_art.py (8 x 4 cells).
UI.GLYPHS = {
    "star", "layers", "banner", "trophy", "dungeon", "key", "rift", "tasks",
    "check", "clock", "close", "flame", "shield", "reward", "search", "legacy",
    "shirt", "mount", "skull", "left", "right", "group", "solo", "hourglass",
    "chest", "sword", "dot", "down", "up", "info", "bounty", "shards",
}
local GLYPH_INDEX = {}
for i, name in ipairs(UI.GLYPHS) do
    GLYPH_INDEX[name] = i - 1
end

-- Emote atlas cells, same order as EMOTE_GLYPHS in Tools/UiLint/make_art.py (8 x 4 cells).
UI.EMOTE_GLYPHS = {
    "dance", "wave", "bow", "cheer", "clap", "laugh", "flex", "kiss",
    "cry", "chicken", "beg", "roar", "rude", "salute", "shy", "point",
    "talk", "shout", "question", "kneel", "sit", "sleep", "eat", "train",
    "yes", "no", "music", "wheel", "sparkle", "stand", "plus", "shrug",
}
local EMOTE_INDEX = {}
for i, name in ipairs(UI.EMOTE_GLYPHS) do
    EMOTE_INDEX[name] = i - 1
end
UI.EMOTE_INDEX = EMOTE_INDEX

------------------------------------------------------------------------------------------------------
-- Basics
------------------------------------------------------------------------------------------------------
function UI.Rgb(hex, alpha)
    local r, g, b = U.Hex(hex)
    return r, g, b, alpha or 1
end

local BACKDROP = { bgFile = UI.WHITE, edgeFile = UI.WHITE, edgeSize = 1, insets = { left = 1, right = 1, top = 1, bottom = 1 } }
local BACKDROP_NOEDGE = { bgFile = UI.WHITE, insets = { left = 0, right = 0, top = 0, bottom = 0 } }

function UI.Backdrop(f, bg, border, alpha)
    f:SetBackdrop(border and BACKDROP or BACKDROP_NOEDGE)
    if bg then
        f:SetBackdropColor(UI.Rgb(bg, alpha or 1))
    else
        f:SetBackdropColor(0, 0, 0, 0)
    end
    if border then
        f:SetBackdropBorderColor(UI.Rgb(border))
    end
end

-- Recolour a frame that already has the bordered backdrop (no new backdrop textures).
function UI.Colors(f, bg, border, alpha)
    if bg then
        f:SetBackdropColor(UI.Rgb(bg, alpha or 1))
    else
        f:SetBackdropColor(0, 0, 0, 0)
    end
    f:SetBackdropBorderColor(UI.Rgb(border or bg or C.border))
end

function UI.Box(parent, w, h, bg, border, alpha)
    local f = CreateFrame("Frame", nil, parent)
    if w and h then
        f:SetSize(w, h)
    end
    UI.Backdrop(f, bg, border, alpha)
    return f
end

function UI.Solid(parent, color, layer, alpha)
    local t = parent:CreateTexture(nil, layer or "BACKGROUND")
    t:SetTexture(UI.WHITE)
    t:SetVertexColor(UI.Rgb(color, alpha))
    return t
end

local FONTS = { body = UI.FONT_BODY, title = UI.FONT_TITLE, narrow = UI.FONT_NARROW }

function UI.Text(parent, size, color, font, justify, layer)
    local fs = parent:CreateFontString(nil, layer or "OVERLAY")
    fs:SetFont(FONTS[font or "body"] or UI.FONT_BODY, size or 12, "")
    fs:SetTextColor(UI.Rgb(color or C.text))
    fs:SetJustifyH(justify or "LEFT")
    fs:SetShadowOffset(1, -1)
    fs:SetShadowColor(0, 0, 0, 0.85)
    return fs
end

-- A single line of at most w pixels: longer text is cut with "..." by the client instead of wrapping.
function UI.OneLine(fs, w)
    local _, size = fs:GetFont()
    fs:SetWidth(w)
    fs:SetHeight((size or 12) + 3)
    fs:SetNonSpaceWrap(false)
    return fs
end

-- Set server text on a FontString ('|' doubled so it cannot inject escape codes).
function UI.SetText(fs, s)
    fs:SetText(U.Safe(s))
end

function UI.SetColor(fs, hex)
    fs:SetTextColor(UI.Rgb(hex))
end

function UI.SetGlyph(t, name)
    local i = GLYPH_INDEX[name] or GLYPH_INDEX.dot
    local c, r = i % 8, floor(i / 8)
    t:SetTexture(UI.ART .. "Glyphs")
    t:SetTexCoord(c / 8, (c + 1) / 8, r / 4, (r + 1) / 4)
end

-- An emote glyph; unknown names show the music note.
function UI.SetEmoteGlyph(t, name)
    local i = EMOTE_INDEX[name] or EMOTE_INDEX.music
    local c, r = i % 8, floor(i / 8)
    t:SetTexture(UI.ART .. "Emotes")
    t:SetTexCoord(c / 8, (c + 1) / 8, r / 4, (r + 1) / 4)
end

function UI.Glyph(parent, name, size, color, layer)
    local t = parent:CreateTexture(nil, layer or "OVERLAY")
    UI.SetGlyph(t, name)
    t:SetSize(size, size)
    t:SetVertexColor(UI.Rgb(color or C.goldLight))
    return t
end

function UI.Disc(parent, size, color, layer, alpha)
    local t = parent:CreateTexture(nil, layer or "ARTWORK")
    t:SetTexture(UI.ART .. "Disc")
    t:SetSize(size, size)
    t:SetVertexColor(UI.Rgb(color, alpha))
    return t
end

-- Round badge: dark disc, gold ring, glyph (orbs, window icons, medals).
function UI.Badge(parent, size, glyph, fill, ring, glyphColor)
    local f = CreateFrame("Frame", nil, parent)
    f:SetSize(size, size)
    f.fill = UI.Disc(f, size, fill or C.chip, "BACKGROUND")
    f.fill:SetPoint("CENTER")
    f.ring = f:CreateTexture(nil, "BORDER")
    f.ring:SetTexture(UI.ART .. "Ring")
    f.ring:SetAllPoints(f)
    f.ring:SetVertexColor(UI.Rgb(ring or C.gold))
    if glyph then
        f.glyph = UI.Glyph(f, glyph, floor(size * 0.56), glyphColor or C.goldLight, "ARTWORK")
        f.glyph:SetPoint("CENTER")
    end
    return f
end

------------------------------------------------------------------------------------------------------
-- Buttons
------------------------------------------------------------------------------------------------------
local STYLES = {
    gold = { bg = C.gold, border = C.gold, fg = C.bg, hover = C.goldLight },
    teal = { bg = C.teal, border = C.teal, fg = C.bg, hover = "8FD6E4" },
    green = { bg = "3C8D3F", border = "5DB660", fg = "F2F7EE", hover = "8FE08F" },
    ghost = { bg = nil, border = C.chipBorder, fg = C.goldLight, hover = C.gold },
    dark = { bg = C.chip, border = C.chipBorder, fg = C.text, hover = C.gold },
    tab = { bg = nil, border = C.border, fg = C.mid, hover = C.gold },
    tabOn = { bg = C.active, border = C.gold, fg = C.goldLight, hover = C.goldLight },
    disabled = { bg = C.chip, border = C.chipBorder, fg = C.mute, hover = C.chipBorder },
}
UI.STYLES = STYLES

local function applyStyle(b)
    local st = STYLES[b.enabled == false and "disabled" or b.style] or STYLES.dark
    UI.Colors(b, st.bg, b.hovered and st.hover or st.border)
    b.label:SetTextColor(UI.Rgb(st.fg))
    if b.icon then
        b.icon:SetVertexColor(UI.Rgb(st.fg))
    end
end

function UI.Button(parent, w, h, label, style, size)
    local b = CreateFrame("Button", nil, parent)
    b:SetSize(w, h)
    b.style = style or "dark"
    b.enabled = true
    b:SetBackdrop(BACKDROP)
    b.label = UI.Text(b, size or 13, C.text, "body", "CENTER")
    b.label:SetPoint("LEFT", b, "LEFT", 6, 0)
    b.label:SetPoint("RIGHT", b, "RIGHT", -6, 0)
    b.label:SetText(label or "")
    b:RegisterForClicks("LeftButtonUp")
    b:SetScript("OnEnter", function(self)
        self.hovered = true
        applyStyle(self)
        if self.tooltip then
            UI.ShowTooltip(self, self.tooltip())
        end
    end)
    b:SetScript("OnLeave", function(self)
        self.hovered = false
        applyStyle(self)
        if self.tooltip and GameTooltip then
            GameTooltip:Hide()
        end
    end)
    function b:SetLabel(text)
        self.label:SetText(text or "")
    end
    function b:SetStyle(st)
        self.style = st
        applyStyle(self)
    end
    function b:SetActive(on)
        self.enabled = on and true or false
        if on then
            self:Enable()
        else
            self:Disable()
        end
        applyStyle(self)
    end
    applyStyle(b)
    return b
end

-- Button with a glyph above or left of the label (nav rail, toolbar).
function UI.IconButton(parent, w, h, glyph, label, style)
    local b = UI.Button(parent, w, h, label, style or "tab", 11)
    b.icon = UI.Glyph(b, glyph, 22, C.dim)
    if label and label ~= "" then
        b.icon:SetPoint("TOP", b, "TOP", 0, -8)
        b.label:ClearAllPoints()
        b.label:SetPoint("BOTTOM", b, "BOTTOM", 0, 7)
    else
        b.icon:SetPoint("CENTER")
    end
    applyStyle(b)
    return b
end

function UI.CloseButton(parent, onClick)
    local b = UI.Button(parent, 30, 30, "", "dark")
    b.icon = UI.Glyph(b, "close", 14, C.text)
    b.icon:SetPoint("CENTER")
    b:SetScript("OnClick", onClick)
    return b
end

------------------------------------------------------------------------------------------------------
-- Pills, bars, rings
------------------------------------------------------------------------------------------------------
function UI.Pill(parent, text, bg, border, color, size)
    local f = CreateFrame("Frame", nil, parent)
    f:SetHeight((size or 12) + 10)
    f.text = UI.Text(f, size or 12, color or C.text, "body", "CENTER")
    f.text:SetPoint("CENTER")
    UI.Backdrop(f, bg or C.active, border or C.eraBorder)
    function f:SetValue(s)
        UI.SetText(self.text, s)
        self:SetWidth(max(24, floor(self.text:GetStringWidth() + 20)))
    end
    f:SetValue(text or "")
    f:EnableMouse(true)
    f:SetScript("OnEnter", function(self)
        if self.tooltip then
            UI.ShowTooltip(self, self.tooltip())
        end
    end)
    f:SetScript("OnLeave", function()
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    return f
end

-- Lay out frames left to right (or right to left) from an anchor point.
function UI.Row(frames, anchor, point, relPoint, x, y, gap, rightToLeft)
    local prev
    for _, f in ipairs(frames) do
        f:ClearAllPoints()
        if not prev then
            f:SetPoint(point, anchor, relPoint, x, y)
        elseif rightToLeft then
            f:SetPoint("RIGHT", prev, "LEFT", -gap, 0)
        else
            f:SetPoint("LEFT", prev, "RIGHT", gap, 0)
        end
        prev = f
    end
end

function UI.Bar(parent, w, h, color, bg)
    local f = CreateFrame("StatusBar", nil, parent)
    f:SetSize(w, h)
    f:SetStatusBarTexture(UI.WHITE)
    f:SetStatusBarColor(UI.Rgb(color or C.gold))
    f:SetMinMaxValues(0, 1)
    f:SetValue(0)
    f.bg = UI.Solid(f, bg or C.deep, "BACKGROUND")
    f.bg:SetAllPoints(f)
    function f:SetProgress(p)
        self:SetValue(U.Clamp(p or 0, 0, 1))
    end
    return f
end

-- Progress ring drawn as overlapping dots (3.3.5a has no texture masks outside the Minimap).
function UI.Ring(parent, size, thickness, count)
    local f = CreateFrame("Frame", nil, parent)
    f:SetSize(size, size)
    local radius = (size - thickness) / 2
    count = count or max(24, ceil(2 * pi * radius / (thickness * 0.55)))
    f.dots = {}
    for i = 1, count do
        local t = f:CreateTexture(nil, "ARTWORK")
        t:SetTexture(UI.ART .. "Disc")
        t:SetSize(thickness, thickness)
        local a = pi / 2 - (i - 0.5) / count * 2 * pi
        t:SetPoint("CENTER", f, "CENTER", radius * cos(a), radius * sin(a))
        f.dots[i] = t
    end
    f.label = UI.Text(f, max(9, floor(size * 0.24)), C.text, "body", "CENTER")
    f.label:SetPoint("CENTER")
    function f:SetProgress(p, color, track)
        p = U.Clamp(p or 0, 0, 1)
        local lr, lg, lb = U.Hex(color or C.gold)
        local tr, tg, tb = U.Hex(track or C.track)
        local n = #self.dots
        for i = 1, n do
            if (i - 0.5) / n <= p then
                self.dots[i]:SetVertexColor(lr, lg, lb, 1)
            else
                self.dots[i]:SetVertexColor(tr, tg, tb, 1)
            end
        end
    end
    f:SetProgress(0)
    return f
end

------------------------------------------------------------------------------------------------------
-- Tooltips
------------------------------------------------------------------------------------------------------
-- lines: { title, { text, colorHex, wrap }, ... } (server text must already be passed through U.Safe)
function UI.ShowTooltip(owner, lines)
    if not GameTooltip or type(lines) ~= "table" then
        return
    end
    GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
    for i, line in ipairs(lines) do
        if type(line) == "string" then
            if i == 1 then
                GameTooltip:AddLine(line, UI.Rgb(C.goldPale))
            else
                GameTooltip:AddLine(line, 0.85, 0.82, 0.76, true)
            end
        elseif type(line) == "table" then
            local r, g, b = UI.Rgb(line[2] or C.mid)
            GameTooltip:AddLine(line[1] or "", r, g, b, line[3] and true or false)
        end
    end
    GameTooltip:Show()
end

------------------------------------------------------------------------------------------------------
-- Windows
------------------------------------------------------------------------------------------------------
local function savePosition(f)
    local point, _, relPoint, x, y = f:GetPoint(1)
    if point then
        ns.cdb.windows[f:GetName()] = { point = point, relPoint = relPoint, x = floor((x or 0) + 0.5), y = floor((y or 0) + 0.5) }
    end
end

function UI.RestorePosition(f, defPoint, defX, defY)
    local pos = ns.cdb.windows[f:GetName()]
    f:ClearAllPoints()
    if type(pos) == "table" and type(pos.point) == "string" and type(pos.x) == "number" and type(pos.y) == "number" then
        f:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, pos.x, pos.y)
    else
        f:SetPoint(defPoint or "CENTER", UIParent, defPoint or "CENTER", defX or 0, defY or 20)
    end
end

function UI.MakeMovable(f, handle)
    f:SetMovable(true)
    f:SetClampedToScreen(true)
    handle = handle or f
    handle:EnableMouse(true)
    handle:RegisterForDrag("LeftButton")
    handle:SetScript("OnDragStart", function()
        f:StartMoving()
    end)
    handle:SetScript("OnDragStop", function()
        f:StopMovingOrSizing()
        savePosition(f)
    end)
end

UI.windows = {}

-- Saved positions load with the addon's saved variables (after the files ran): place windows then.
ns.On("DB_READY", function()
    for _, w in pairs(UI.windows) do
        UI.RestorePosition(w)
    end
end)

-- A Bleakhold window: panel, gold top line, header with badge, title and close button. ESC closes
-- it (UISpecialFrames); it can be dragged by the header and remembers its position.
function UI.Window(name, w, h, title, glyph)
    local f = CreateFrame("Frame", name, UIParent)
    f:SetSize(w, h)
    f:SetFrameStrata("HIGH")
    f:SetToplevel(true)
    f:EnableMouse(true)
    UI.Backdrop(f, C.panel, C.strong, 0.98)
    f:Hide()

    local top = UI.Solid(f, C.gold, "BORDER")
    top:SetPoint("TOPLEFT", f, "TOPLEFT", 1, -1)
    top:SetPoint("TOPRIGHT", f, "TOPRIGHT", -1, -1)
    top:SetHeight(3)

    local header = CreateFrame("Frame", nil, f)
    header:SetPoint("TOPLEFT", f, "TOPLEFT", 1, -4)
    header:SetPoint("TOPRIGHT", f, "TOPRIGHT", -1, -4)
    header:SetHeight(46)
    UI.Backdrop(header, C.header)
    local line = UI.Solid(header, C.border, "BORDER")
    line:SetPoint("BOTTOMLEFT")
    line:SetPoint("BOTTOMRIGHT")
    line:SetHeight(1)
    f.header = header

    f.badge = UI.Badge(header, 30, glyph or "star", C.chip, C.gold)
    f.badge:SetPoint("LEFT", header, "LEFT", 12, 0)
    f.title = UI.Text(header, 18, C.goldLight, "title")
    f.title:SetPoint("LEFT", f.badge, "RIGHT", 10, 0)
    UI.SetText(f.title, title or "")

    f.close = UI.CloseButton(header, function()
        f:Hide()
    end)
    f.close:SetPoint("RIGHT", header, "RIGHT", -10, 0)

    f.content = CreateFrame("Frame", nil, f)
    f.content:SetPoint("TOPLEFT", header, "BOTTOMLEFT", 0, 0)
    f.content:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -1, 1)

    UI.MakeMovable(f, header)
    UI.RestorePosition(f)
    if UISpecialFrames then
        table.insert(UISpecialFrames, name)
    end
    f:SetScript("OnShow", function(self)
        local ph = UIParent and UIParent:GetHeight() or 768
        if ph and ph > 0 and h > ph - 40 then
            self:SetScale(max(0.5, (ph - 40) / h))
        else
            self:SetScale(1)
        end
        if PlaySound then
            PlaySound("igCharacterInfoOpen")
        end
        if self.OnOpen then
            ns.SafeCall(self.OnOpen, self)
        end
    end)
    f:SetScript("OnHide", function(self)
        if PlaySound then
            PlaySound("igCharacterInfoClose")
        end
        if self.OnClose then
            ns.SafeCall(self.OnClose, self)
        end
    end)
    UI.windows[name] = f
    return f
end

------------------------------------------------------------------------------------------------------
-- Scroll area (mouse wheel and a thin thumb, no FrameXML template)
------------------------------------------------------------------------------------------------------
function UI.Scroll(parent)
    local sf = CreateFrame("ScrollFrame", nil, parent)
    local child = CreateFrame("Frame", nil, sf)
    child:SetSize(10, 10)
    sf:SetScrollChild(child)
    sf.child = child
    sf.contentHeight = 0
    local thumb = UI.Solid(sf, C.chipBorder, "OVERLAY")
    thumb:SetWidth(3)
    thumb:Hide()
    sf.thumb = thumb
    local function update(self)
        local h = self:GetHeight() or 0
        local total = self.contentHeight or 0
        local range = max(0, total - h)
        local cur = U.Clamp(self:GetVerticalScroll() or 0, 0, range)
        if range <= 0 or h <= 0 then
            thumb:Hide()
            return
        end
        local th = max(16, h * h / total)
        thumb:SetHeight(th)
        thumb:ClearAllPoints()
        thumb:SetPoint("TOPRIGHT", self, "TOPRIGHT", -1, -((h - th) * cur / range))
        thumb:Show()
    end
    sf:EnableMouseWheel(true)
    sf:SetScript("OnMouseWheel", function(self, delta)
        local h = self:GetHeight() or 0
        local range = max(0, (self.contentHeight or 0) - h)
        local cur = U.Clamp((self:GetVerticalScroll() or 0) - (delta or 0) * 40, 0, range)
        self:SetVerticalScroll(cur)
        update(self)
    end)
    function sf:SetContentHeight(height)
        self.contentHeight = height or 0
        child:SetHeight(max(1, self.contentHeight))
        child:SetWidth(max(1, self:GetWidth() or 1))
        local range = max(0, self.contentHeight - (self:GetHeight() or 0))
        if (self:GetVerticalScroll() or 0) > range then
            self:SetVerticalScroll(range)
        end
        update(self)
    end
    return sf
end

------------------------------------------------------------------------------------------------------
-- Object pools for list rows
------------------------------------------------------------------------------------------------------
function UI.Pool(factory)
    local pool = { items = {}, used = 0 }
    function pool:Acquire()
        self.used = self.used + 1
        local item = self.items[self.used]
        if not item then
            item = factory(self.used)
            self.items[self.used] = item
        end
        item:Show()
        return item
    end
    function pool:ReleaseAll()
        for i = 1, #self.items do
            self.items[i]:Hide()
        end
        self.used = 0
    end
    return pool
end

------------------------------------------------------------------------------------------------------
-- Dropdown list (own frame: UIDropDownMenu is avoided to keep clear of FrameXML taint)
------------------------------------------------------------------------------------------------------
local openMenu

function UI.Dropdown(parent, w, onSelect)
    local b = UI.Button(parent, w, 26, "", "dark", 12)
    b.label:SetJustifyH("LEFT")
    b.arrow = UI.Glyph(b, "down", 12, C.dim)
    b.arrow:SetPoint("RIGHT", b, "RIGHT", -6, 0)
    b.items = {}
    b.value = nil
    local menu = CreateFrame("Frame", nil, UIParent)
    menu:SetFrameStrata("FULLSCREEN_DIALOG")
    UI.Backdrop(menu, C.rail, C.chipBorder, 0.98)
    menu:Hide()
    menu:EnableMouse(true)
    b.menu = menu
    local rows = UI.Pool(function()
        local r = UI.Button(menu, w - 4, 22, "", "tab", 12)
        r.label:SetJustifyH("LEFT")
        return r
    end)
    function b:SetItems(items)
        self.items = items or {}
    end
    function b:SetValue(value, silent)
        self.value = value
        for _, it in ipairs(self.items) do
            if it.value == value then
                self.label:SetText(it.text)
            end
        end
        if not silent and onSelect then
            onSelect(value)
        end
    end
    function b:Close()
        menu:Hide()
        if openMenu == menu then
            openMenu = nil
        end
    end
    b:SetScript("OnClick", function(self)
        if menu:IsShown() then
            self:Close()
            return
        end
        if openMenu then
            openMenu:Hide()
        end
        rows:ReleaseAll()
        local y = -2
        for _, it in ipairs(self.items) do
            local r = rows:Acquire()
            r:SetLabel(it.text)
            r:SetStyle(it.value == self.value and "tabOn" or "tab")
            r:ClearAllPoints()
            r:SetPoint("TOPLEFT", menu, "TOPLEFT", 2, y)
            r:SetScript("OnClick", function()
                self:Close()
                self:SetValue(it.value)
            end)
            y = y - 23
        end
        menu:SetSize(w, -y + 2)
        menu:ClearAllPoints()
        menu:SetPoint("TOPLEFT", self, "BOTTOMLEFT", 0, -2)
        menu:Show()
        openMenu = menu
    end)
    b:SetScript("OnHide", function(self)
        self:Close()
    end)
    return b
end

------------------------------------------------------------------------------------------------------
-- Small dialogs: confirm and copy-to-clipboard (no LaunchURL in game)
------------------------------------------------------------------------------------------------------
local dialog

local function getDialog()
    if dialog then
        return dialog
    end
    local d = CreateFrame("Frame", "BleakholdDialog", UIParent)
    d:SetSize(360, 150)
    d:SetPoint("CENTER", UIParent, "CENTER", 0, 120)
    d:SetFrameStrata("DIALOG")
    d:SetToplevel(true)
    d:EnableMouse(true)
    UI.Backdrop(d, C.panel, C.gold, 0.98)
    d.text = UI.Text(d, 13, C.text, "body", "CENTER")
    d.text:SetPoint("TOPLEFT", d, "TOPLEFT", 16, -18)
    d.text:SetPoint("TOPRIGHT", d, "TOPRIGHT", -16, -18)
    d.edit = CreateFrame("EditBox", nil, d)
    d.edit:SetSize(300, 24)
    d.edit:SetPoint("CENTER", d, "CENTER", 0, 0)
    d.edit:SetFont(UI.FONT_BODY, 13, "")
    d.edit:SetTextColor(UI.Rgb(C.text))
    d.edit:SetAutoFocus(false)
    d.edit:SetTextInsets(6, 6, 0, 0)
    UI.Backdrop(d.edit, C.rail, C.chipBorder)
    d.edit:SetScript("OnEscapePressed", function()
        d:Hide()
    end)
    d.edit:SetScript("OnEditFocusGained", function(self)
        self:HighlightText()
    end)
    d.ok = UI.Button(d, 130, 30, "Accept", "gold")
    d.ok:SetPoint("BOTTOMRIGHT", d, "BOTTOM", -6, 14)
    d.cancel = UI.Button(d, 130, 30, "Cancel", "dark")
    d.cancel:SetPoint("BOTTOMLEFT", d, "BOTTOM", 6, 14)
    d.cancel:SetScript("OnClick", function()
        d:Hide()
    end)
    d:Hide()
    if UISpecialFrames then
        table.insert(UISpecialFrames, "BleakholdDialog")
    end
    dialog = d
    return d
end

-- Ask before an intent that costs something (reroll with a price, hand-in): the server still checks.
function UI.Confirm(text, onAccept, acceptLabel)
    local d = getDialog()
    UI.SetText(d.text, text)
    d.edit:Hide()
    d.ok:Show()
    d.ok:SetLabel(acceptLabel or "Accept")
    d.ok:SetScript("OnClick", function()
        d:Hide()
        if onAccept then
            ns.SafeCall(onAccept)
        end
    end)
    d.cancel:SetLabel("Cancel")
    d.cancel:ClearAllPoints()
    d.cancel:SetPoint("BOTTOMLEFT", d, "BOTTOM", 6, 14)
    d:Show()
    return d
end

function UI.CopyBox(text, value)
    local d = getDialog()
    UI.SetText(d.text, text)
    d.edit:SetScript("OnEnterPressed", nil)
    d.edit:SetMaxLetters(0)
    d.ok:Hide()
    d.cancel:SetLabel("Close")
    d.cancel:ClearAllPoints()
    d.cancel:SetPoint("BOTTOM", d, "BOTTOM", 0, 14)
    d.edit:Show()
    d.edit:SetText(value or "")
    d:Show()
    d.edit:SetFocus()
    d.edit:HighlightText()
    return d
end

-- Ask for a short text (an outfit's name): Enter or the accept button hands it to onAccept, trimmed and
-- non-empty.
function UI.Prompt(text, value, onAccept, acceptLabel, maxLetters)
    local d = getDialog()
    UI.SetText(d.text, text)
    local function accept()
        local v = (d.edit:GetText() or ""):match("^%s*(.-)%s*$")
        if v == "" then
            return
        end
        d:Hide()
        if onAccept then
            ns.SafeCall(onAccept, v)
        end
    end
    d.edit:Show()
    d.edit:SetMaxLetters(maxLetters or 0)
    d.edit:SetText(value or "")
    d.edit:SetScript("OnEnterPressed", accept)
    d.ok:Show()
    d.ok:SetLabel(acceptLabel or "Accept")
    d.ok:SetScript("OnClick", accept)
    d.cancel:SetLabel("Cancel")
    d.cancel:ClearAllPoints()
    d.cancel:SetPoint("BOTTOMLEFT", d, "BOTTOM", 6, 14)
    d:Show()
    d.edit:SetFocus()
    return d
end

------------------------------------------------------------------------------------------------------
-- Open windows by key (slash commands, orbs, toasts, key bindings)
------------------------------------------------------------------------------------------------------
UI.openers = {}

function UI.RegisterOpener(key, fn)
    UI.openers[key] = fn
end

function UI.Open(key, toggle)
    local fn = UI.openers[key]
    if fn then
        ns.SafeCall(fn, toggle)
        return true
    end
    return false
end

-- Key binding entry point (Bindings.xml).
function BleakholdToggle(key)
    UI.Open(key or "activities", true)
end
