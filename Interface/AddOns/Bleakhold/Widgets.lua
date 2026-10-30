-- Bleakhold: shared UI primitives in the stock World of Warcraft 3.3.5a look (the old BleakholdActivities window),
-- built from the client's own interface art on textures and backdrops, never from FrameXML templates (taint; the
-- test mock refuses them):
--   windows    DialogFrame\UI-DialogBox-Background-Dark + -Border, a dark title bar with the title centred in gold,
--              a ring portrait (an Interface\Icons picture in Minimap\MiniMap-TrackingBorder), the panel close button
--   panels     Tooltips\UI-Tooltip-Background + -Border; small boxes and rows a dark fill with a 1 px edge
--   buttons    the red panel button (Buttons\UI-Panel-Button-*, three slices), held down when selected; the options
--              frame's top tabs for tab strips; small red buttons for minor actions; the StaticPopup button; the
--              spellbook's page arrows
--   bars       the achievement progress bar (TargetingFrame\UI-StatusBar in AchievementFrame's border, the count
--              inside); the character frame's scroll bar; the options slider
--   state      the nav row's blue gradient for the chosen card or row (UI.Select); a check and "Complete" for done;
--              a desaturated icon for locked; the stock indicator balls and radio buttons for small marks
--   dropdowns  dressed like UIDropDownMenu (label frame, arrow, tooltip list, highlight, check), our own frames
--   dialogs    the StaticPopup look (UI-DialogBox-Background, white text, dialog buttons, the input box border)
--   text       Fonts\FRIZQT__.TTF in the stock text colours (gold 1,0.82,0; white; grey; green; red; quality);
--              headings Title Case gold (UI.Heading), stat labels gold 12 (UI.Label), wrapped descriptions with
--              leading (UI.Para), table headers WhoFrameColumnHeaderTemplate (UI.ColumnHeader); never boxed text, never
--              all-caps captions
-- The procedural Art\ textures stay only where stock art has no match: White (solids), Disc (the Royale map's and
-- minimap's pins, RoyaleMap.lua and RoyaleMinimap.lua), Glyphs (map pins and the glyph marks, UI.SetGlyph) and Emotes
-- (the emote glyphs, UI.SetEmoteGlyph).
-- Draw layers: the client does not draw the textures of one layer in the order they were made. CRenderBatch::Finish
-- sorts each layer's meshes by texture (qsort, not stable; Engine/Source/Frame/CRenderBatch.cpp), and a backdrop's
-- fill is a texture of its frame's BACKGROUND layer (its edge pieces are BORDER). So two textures that overlap and must
-- stack in a given order never share a layer: the higher one goes in a higher layer, or on a child frame.
local ADDON, ns = ...
local U = ns.U

local floor, ceil, max, min = math.floor, math.ceil, math.max, math.min

local UI = {}
ns.UI = UI

UI.ART = "Interface\\AddOns\\Bleakhold\\Art\\"
UI.WHITE = UI.ART .. "White"
UI.FONT_BODY = "Fonts\\FRIZQT__.TTF"
UI.FONT_TITLE = "Fonts\\MORPHEUS.TTF"
UI.FONT_NARROW = "Fonts\\ARIALN.TTF"

-- Stock interface art (in every client's MPQs, never in this repository).
local STOCK = {
    white = "Interface\\Buttons\\WHITE8X8",
    dialogBg = "Interface\\DialogFrame\\UI-DialogBox-Background",
    dialogBgDark = "Interface\\DialogFrame\\UI-DialogBox-Background-Dark",
    dialogBorder = "Interface\\DialogFrame\\UI-DialogBox-Border",
    tooltipBg = "Interface\\Tooltips\\UI-Tooltip-Background",
    tooltipBorder = "Interface\\Tooltips\\UI-Tooltip-Border",
    panelButton = "Interface\\Buttons\\UI-Panel-Button-",
    dialogButton = "Interface\\Buttons\\UI-DialogBox-Button-",
    close = "Interface\\Buttons\\UI-Panel-MinimizeButton-",
    tabActive = "Interface\\OptionsFrame\\UI-OptionsFrame-ActiveTab",
    tabInactive = "Interface\\OptionsFrame\\UI-OptionsFrame-InActiveTab",
    tabHighlight = "Interface\\PaperDollInfoFrame\\UI-Character-Tab-Highlight",
    rowHighlight = "Interface\\QuestFrame\\UI-QuestTitleHighlight",
    check = "Interface\\Buttons\\UI-CheckBox-Check",
    checkBox = "Interface\\Buttons\\UI-CheckBox-",
    ring = "Interface\\Minimap\\MiniMap-TrackingBorder",
    ringBg = "Interface\\Minimap\\UI-Minimap-Background",
    statusBar = "Interface\\TargetingFrame\\UI-StatusBar",
    progressBorder = "Interface\\AchievementFrame\\UI-Achievement-ProgressBar-Border",
    castBorder = "Interface\\CastingBar\\UI-CastingBar-Border",
    knob = "Interface\\Buttons\\UI-ScrollBar-Knob",
    scrollTrack = "Interface\\PaperDollInfoFrame\\UI-Character-ScrollBar",
    sliderBg = "Interface\\Buttons\\UI-SliderBar-Background",
    sliderBorder = "Interface\\Buttons\\UI-SliderBar-Border",
    sliderThumb = "Interface\\Buttons\\UI-SliderBar-Button-Horizontal",
    page = "Interface\\Buttons\\UI-SpellbookIcon-",
    indicator = "Interface\\COMMON\\Indicator-",
    radio = "Interface\\Buttons\\UI-RadioButton",
    classes = "Interface\\TargetingFrame\\UI-Classes-Circles",
    quickslot = "Interface\\Buttons\\UI-Quickslot2",
    quickslotEmpty = "Interface\\Buttons\\UI-Quickslot",
    slotGlow = "Interface\\Buttons\\ButtonHilight-Square",
    slotCheck = "Interface\\Buttons\\CheckButtonHilight",
    alertBg = "Interface\\AchievementFrame\\UI-Achievement-Alert-Background",
    alertIconFrame = "Interface\\AchievementFrame\\UI-Achievement-IconFrame",
    labelFrame = "Interface\\Glues\\CharacterCreate\\CharacterCreate-LabelFrame",
    arrow = "Interface\\ChatFrame\\UI-ChatIcon-ScrollDown-",
    arrowHighlight = "Interface\\Buttons\\UI-Common-MouseHilight",
    input = "Interface\\Common\\Common-Input-Border",
    columnTabs = "Interface\\FriendsFrame\\WhoFrame-ColumnTabs",
    icons = "Interface\\Icons\\",
    question = "Interface\\Icons\\INV_Misc_QuestionMark",
}
UI.STOCK = STOCK

-- Stock colours: FrameXML's NORMAL_FONT_COLOR (gold 1,0.82,0), HIGHLIGHT (white), GRAY (0.5), GREEN (0.1,1,0.1),
-- RED (1,0.1,0.1), ORANGE (1,0.5,0.25), the epic quality colour, and the dark tints and grey edges of the old window's
-- panels (0.02,0.02,0.04 and 0.45,0.45,0.5). The keys are the ones the pages use: gold, goldLight and goldPale are
-- all text gold, teal (the old accent for done and good) is the stock green, mid is body white, dim the secondary
-- grey, mute the stock grey.
local C = {
    -- text
    gold = "FFD100", goldLight = "FFD100", goldPale = "FFD100", goldDark = "C4A300",
    text = "FFFFFF", mid = "FFFFFF", dim = "BFBFBF", mute = "808080",
    teal = "1AFF1A", red = "FF1A1A", orange = "FF8040", purple = "A335EE", epic = "A335EE",
    silver = "C8C8C8", bronze = "C88A50",
    -- panel and fill tints
    bg = "050505", panel = "05050A", header = "000000", card = "0A0A10", rail = "05050A", deep = "000000",
    zebra = "101016", chip = "0D0D12",
    -- the selected row of the old window: a dark blue fill with a light blue edge (UI.Select paints it)
    active = "1F3D7A", select = "73ADFF",
    -- the achievement progress bar's green (currency bars are gold)
    bar = "009900",
    -- edges
    border = "737380", strong = "8C8C99", chipBorder = "4D4D59", eraBorder = "8C7A4D", setBorder = "6B4F99",
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

-- The Interface\Icons picture that stands for a glyph on a ring portrait (windows, badges, nav rows). Glyphs with no
-- picture (arrows, close, dot, info) keep the glyph.
UI.GLYPH_ICONS = {
    star = "Achievement_General", layers = "INV_Chest_Cloth_17", banner = "INV_BannerPVP_02",
    trophy = "INV_Misc_Trophy_Argent", dungeon = "Achievement_Dungeon_ClassicDungeonMaster", key = "INV_Misc_Key_15",
    rift = "Ability_Druid_EclipseOrange", tasks = "INV_Misc_Note_01", check = "Achievement_Quests_Completed_08",
    clock = "Spell_Holy_BorrowedTime", flame = "Spell_Fire_Fire", shield = "INV_Shield_06", reward = "INV_Misc_Bag_10",
    search = "INV_Misc_Spyglass_02", legacy = "INV_Misc_Book_09", shirt = "INV_Shirt_White_01",
    mount = "Ability_Mount_RidingHorse", skull = "INV_Misc_Bone_HumanSkull_01", group = "INV_Misc_GroupNeedMore",
    solo = "INV_Misc_GroupLooking", hourglass = "Spell_Nature_TimeStop", chest = "INV_Box_02", sword = "INV_Sword_04",
    bounty = "Ability_Rogue_FindWeakness", shards = "INV_Enchant_ShardBrilliantLarge",
}

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

-- The looks a frame's backdrop can take:
--   panel    the tooltip frame (the old window's panels), tinted dark, grey edge
--   edge     a dark fill with a 1 px edge (rows, chips, slots: a 16 px tooltip edge spoils a small box)
--   fill     a plain fill, no edge
--   window   the dialog frame of the windows (UI-DialogBox-Background-Dark)
--   popup    the StaticPopup frame (UI-DialogBox-Background)
--   list     the tooltip frame on an opaque fill, for dropdown lists (UI-Tooltip-Background itself is 91% opaque, and
--            text under an open list would show through its rows)
local BACKDROPS = {
    panel = { bgFile = STOCK.tooltipBg, edgeFile = STOCK.tooltipBorder, tile = true, tileSize = 16, edgeSize = 16,
        insets = { left = 4, right = 4, top = 4, bottom = 4 } },
    edge = { bgFile = STOCK.white, edgeFile = STOCK.white, edgeSize = 1,
        insets = { left = 1, right = 1, top = 1, bottom = 1 } },
    fill = { bgFile = STOCK.white, insets = { left = 0, right = 0, top = 0, bottom = 0 } },
    window = { bgFile = STOCK.dialogBgDark, edgeFile = STOCK.dialogBorder, tile = true, tileSize = 32, edgeSize = 32,
        insets = { left = 11, right = 12, top = 12, bottom = 11 } },
    popup = { bgFile = STOCK.dialogBg, edgeFile = STOCK.dialogBorder, tile = true, tileSize = 32, edgeSize = 32,
        insets = { left = 11, right = 12, top = 12, bottom = 11 } },
    list = { bgFile = STOCK.white, edgeFile = STOCK.tooltipBorder, tile = true, tileSize = 16, edgeSize = 16,
        insets = { left = 4, right = 4, top = 4, bottom = 4 } },
}
UI.BACKDROPS = BACKDROPS
-- edge only, for frames laid over something (the bar border)
local OUTLINE = { edgeFile = STOCK.white, edgeSize = 1 }

-- A bordered frame under this many pixels on a side gets the 1 px edge instead of the tooltip edge.
UI.SMALL_BOX = 40

local function backdropKind(f, border, kind)
    if kind and BACKDROPS[kind] then
        return kind
    end
    if not border then
        return "fill"
    end
    local w, h = f:GetWidth() or 0, f:GetHeight() or 0
    if (w > 0 and w < UI.SMALL_BOX) or (h > 0 and h < UI.SMALL_BOX) then
        return "edge"
    end
    return "panel"
end

-- Panels are a little see-through, like the tooltip, and so are the small boxes (the old rows' fill at 0.9); the other
-- looks are opaque unless the caller says.
local function backdropAlpha(kind, alpha)
    if alpha then
        return alpha
    end
    return (kind == "panel" or kind == "edge") and 0.9 or 1
end

-- A small box is drawn as the old window's rows (old :263, :305, :414): a 0.04,0.04,0.06 fill and a 0.25,0.25,0.3
-- edge (#40404D, as the reference's rows). The panel greys are meant for the 16 px tooltip edge and are about twice
-- as bright on a 1 px line, so on an "edge" box they draw as the row edge, and the dark panel tints as the row fill.
local ROW_EDGE, ROW_FILL = "40404D", "0A0A0F"
UI.ROW_EDGE, UI.ROW_FILL = ROW_EDGE, ROW_FILL
local GREY_EDGES = { [C.border] = true, [C.strong] = true, [C.chipBorder] = true }
local DARK_FILLS = { [C.card] = true, [C.chip] = true, [C.panel] = true, [C.bg] = true, [C.rail] = true }
local function rowLook(kind, bg, border)
    if kind == "edge" then
        if bg and DARK_FILLS[bg] then
            bg = ROW_FILL
        end
        if border and GREY_EDGES[border] then
            border = ROW_EDGE
        end
    end
    return bg, border
end

-- Edge colours that used to carry a state (done, warning, rarity, era): the stock frames keep their grey edge and
-- show state with a mark instead (a check, "Complete", a desaturated icon); a gold edge was the old "chosen" or
-- "first" mark.
local STATE_EDGES = {}
for _, k in ipairs({ "teal", "orange", "purple", "eraBorder", "setBorder", "red", "goldDark", "select" }) do
    STATE_EDGES[C[k]] = true
end

-- bg / border: hex colours (no border: a plain fill); kind: one of UI.BACKDROPS to choose the look (see above). A
-- state colour on the edge is drawn in the panel grey (see STATE_EDGES); a small box in the row colours (rowLook).
function UI.Backdrop(f, bg, border, alpha, kind)
    kind = backdropKind(f, border, kind)
    f:SetBackdrop(BACKDROPS[kind])
    f.backdropKind = kind
    if border and border ~= bg and (STATE_EDGES[border] or border == C.gold) then
        border = C.border
    end
    bg, border = rowLook(kind, bg, border)
    if bg then
        f:SetBackdropColor(UI.Rgb(bg, backdropAlpha(kind, alpha)))
    else
        f:SetBackdropColor(0, 0, 0, 0)
    end
    if border then
        f:SetBackdropBorderColor(UI.Rgb(border))
    end
end

-- The one selection look of the old window (its nav row), for any chosen card or row: a blue gradient fading to the
-- right and a light blue 1 px edge, inside the frame's backdrop border (which stays the panel grey).
-- The gradient is in BORDER: in BACKGROUND it would share the layer with the backdrop's own fill, and the client sorts
-- a layer by texture (see the top of this file), so the fill could cover it. It sits inside the backdrop's insets (1 px
-- for the small boxes, 4 for the tooltip frame), clear of the edge pieces that share BORDER with it; row content is in
-- ARTWORK and above it. The edge is a child frame, above everything of f's own. An empty slot's art (UI.SlotArt
-- f.slotBg, BORDER too) is hidden while f is chosen, so the gradient never has to stack with it in one layer.
UI.SELECT_LAYER = "BORDER"
function UI.SelectInset(kind)
    local bd = BACKDROPS[kind or ""]
    return max(1, bd and bd.insets and bd.insets.left or 0)
end
function UI.Select(f, on)
    local s = f.selectArt
    if not s then
        if not on then
            return
        end
        local inset = UI.SelectInset(f.backdropKind)
        local edgeInset = f.backdropKind == "panel" and 4 or 0
        s = {}
        s.bg = f:CreateTexture(nil, UI.SELECT_LAYER)
        s.bg:SetTexture(STOCK.white)
        s.bg:SetPoint("TOPLEFT", f, "TOPLEFT", inset, -inset)
        s.bg:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -inset, inset)
        s.bg:SetGradientAlpha("HORIZONTAL", 0.16, 0.32, 0.65, 0.95, 0.05, 0.12, 0.3, 0.15)
        s.edge = CreateFrame("Frame", nil, f)
        s.edge:SetPoint("TOPLEFT", f, "TOPLEFT", edgeInset, -edgeInset)
        s.edge:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -edgeInset, edgeInset)
        s.edge:SetBackdrop(OUTLINE)
        s.edge:SetBackdropBorderColor(0.45, 0.68, 1, 1)
        f.selectArt = s
    end
    if on then
        s.bg:Show()
        s.edge:Show()
    else
        s.bg:Hide()
        s.edge:Hide()
    end
    if f.slotBg then
        if on then
            f.slotBg:Hide()
        else
            f.slotBg:Show()
        end
    end
    f.selected = on and true or false
end

-- Recolour a frame that already has its backdrop (no new backdrop textures). The old "chosen" colours (the blue fill
-- C.active, or a gold edge on a dark card) become UI.Select's look; state colours on edges become the panel grey.
function UI.Colors(f, bg, border, alpha)
    if f.backdropKind then
        local chosen = bg == C.active or (border == C.gold and bg ~= C.gold and bg ~= C.goldDark)
        UI.Select(f, chosen)
        if bg == C.active then
            bg = C.card
        end
        if border and border ~= bg and (chosen or STATE_EDGES[border]) then
            border = C.border
        end
    end
    border = border or bg or C.border
    bg, border = rowLook(f.backdropKind, bg, border)
    if bg then
        f:SetBackdropColor(UI.Rgb(bg, backdropAlpha(f.backdropKind, alpha)))
    else
        f:SetBackdropColor(0, 0, 0, 0)
    end
    f:SetBackdropBorderColor(UI.Rgb(border))
end

function UI.Box(parent, w, h, bg, border, alpha, kind)
    local f = CreateFrame("Frame", nil, parent)
    if w and h then
        f:SetSize(w, h)
    end
    UI.Backdrop(f, bg, border, alpha, kind)
    return f
end

function UI.Solid(parent, color, layer, alpha)
    local t = parent:CreateTexture(nil, layer or "BACKGROUND")
    t:SetTexture(UI.WHITE)
    t:SetVertexColor(UI.Rgb(color, alpha))
    return t
end

-- Friz Quadrata everywhere, as the client's own frames; Morpheus only where WoW uses it (font "morpheus").
local FONTS = { body = UI.FONT_BODY, title = UI.FONT_BODY, narrow = UI.FONT_NARROW, morpheus = UI.FONT_TITLE }

function UI.Text(parent, size, color, font, justify, layer)
    local fs = parent:CreateFontString(nil, layer or "OVERLAY")
    fs:SetFont(FONTS[font or "body"] or UI.FONT_BODY, size or 12, "")
    fs:SetTextColor(UI.Rgb(color or C.text))
    fs:SetJustifyH(justify or "LEFT")
    fs:SetShadowOffset(1, -1)
    fs:SetShadowColor(0, 0, 0, 1)
    -- a little leading, so wrapped lines do not touch (one line is unchanged); UI.Para sets the old window's 3
    fs:SetSpacing(2)
    return fs
end

-- A wrapped description as the old window wrote them (p.desc:SetSpacing(3), old :180, :367, :439): w wide, 3 px
-- between lines, from the top down.
function UI.Para(parent, size, color, width)
    local fs = UI.Text(parent, size or 12, color or C.text)
    if width then
        fs:SetWidth(width)
    end
    fs:SetSpacing(3)
    fs:SetJustifyV("TOP")
    return fs
end

-- The stock frames write titles and labels in Title Case: an all-caps text ("WAR FRONT") becomes "War Front"; mixed
-- case ("PvP", "Mythic+ Dungeons") is kept. Toast.TitleCase is the same rule.
function UI.TitleCase(s)
    s = tostring(s or "")
    if s == "" or s ~= s:upper() or not s:find("%a") then
        return s
    end
    return (s:lower():gsub("(%a)([%w']*)", function(first, rest)
        return first:upper() .. rest
    end))
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

-- A section heading as the stock frames write them: Title Case, gold, FRIZQT 14 by default, with the text shadow.
function UI.Heading(parent, text, size)
    local fs = UI.Text(parent, size or 14, C.gold)
    if text then
        fs:SetText(text)
    end
    return fs
end

-- A stat label as the old window's (old :185 "Board changes in"): gold FRIZQT 12 with the shadow, in Title Case (an
-- all-caps text becomes Title Case, UI.TitleCase). fs:SetLabel(text) changes it (server text is escaped).
local function setLabelText(self, s)
    self:SetText(U.Safe(UI.TitleCase(s)))
end
function UI.Label(parent, text, size)
    local fs = UI.Text(parent, size or 12, C.gold)
    fs.SetLabel = setLabelText
    if text then
        fs:SetLabel(text)
    end
    return fs
end

-- A table's column header as WhoFrameColumnHeaderTemplate: FriendsFrame\WhoFrame-ColumnTabs in three slices (a 5 px
-- left cap, the middle stretched, a 4 px right cap; 24 tall) with the label in GameFontHighlightSmall (white 10) 8 px
-- in from the left. Headers stand side by side, each as wide as its column. f.label; f:SetLabel(text).
local COLUMN_U = { 0, 0.078125, 0.90625, 0.96875 }
local function setColumnLabel(self, s)
    self.label:SetText(U.Safe(UI.TitleCase(s)))
end
function UI.ColumnHeader(parent, w, text)
    local f = CreateFrame("Frame", nil, parent)
    f:SetSize(w, 24)
    f.slices = {}
    for i = 1, 3 do
        local t = f:CreateTexture(nil, "BACKGROUND")
        t:SetTexture(STOCK.columnTabs)
        t:SetTexCoord(COLUMN_U[i], COLUMN_U[i + 1], 0, 0.75)
        t:SetHeight(24)
        f.slices[i] = t
    end
    local l, m, r = f.slices[1], f.slices[2], f.slices[3]
    l:SetWidth(5)
    l:SetPoint("TOPLEFT", f, "TOPLEFT", 0, 0)
    r:SetWidth(4)
    r:SetPoint("TOPRIGHT", f, "TOPRIGHT", 0, 0)
    m:SetPoint("TOPLEFT", l, "TOPRIGHT", 0, 0)
    m:SetPoint("TOPRIGHT", r, "TOPLEFT", 0, 0)
    f.label = UI.Text(f, 10, C.text)
    f.label:SetPoint("LEFT", f, "LEFT", 8, 0)
    UI.OneLine(f.label, max(1, w - 12))
    f.SetLabel = setColumnLabel
    f:SetLabel(text)
    return f
end

-- A gold label and a white value on one line ("Daily reset: 7 h 11 min"), the stat look of the old window.
-- Returns the FontString; fs:SetValue(value) and fs:SetLabel(label) change either part (server text is escaped).
function UI.LabelValue(parent, label, value, size)
    local fs = UI.Text(parent, size or 11, C.text)
    fs.labelText, fs.valueText = label or "", value or ""
    local function paint(self)
        local l = U.Safe(self.labelText)
        self:SetText((l ~= "" and ("|cffffd100" .. l .. ":|r ") or "") .. U.Safe(self.valueText))
    end
    function fs:SetValue(v)
        self.valueText = v ~= nil and tostring(v) or ""
        paint(self)
    end
    function fs:SetLabel(l)
        self.labelText = l ~= nil and tostring(l) or ""
        paint(self)
    end
    paint(fs)
    return fs
end

-- The stock check (UI-CheckBox-Check) that marks done or earned, 20 px.
function UI.Check(parent, size, layer)
    local t = parent:CreateTexture(nil, layer or "OVERLAY")
    t:SetTexture(STOCK.check)
    t:SetSize(size or 20, size or 20)
    return t
end

-- A child frame one level above f and over all of it (f.marks, made once), for marks that sit on f's ring or border:
-- one layer is not drawn in creation order (the top of this file), so a mark in the ring's own layer can go under it.
function UI.Marks(f)
    if not f.marks then
        local m = CreateFrame("Frame", nil, f)
        m:SetAllPoints(f)
        m:SetFrameLevel(f:GetFrameLevel() + 1)
        f.marks = m
    end
    return f.marks
end

-- A check button as OptionsCheckButtonTemplate: UI-CheckBox-Up, -Down while pressed, -Highlight in ADD under the
-- cursor, -Check while checked (-Check-Disabled while checked and disabled), size x size (default 24), its label
-- (b.label) in gold 12 to the right and part of the hit area. b:SetActive(on) enables it and greys the label when off.
-- The caller's OnClick writes the setting and sets SetChecked from it (the client has already flipped the check).
function UI.CheckButton(parent, label, size)
    size = size or 24
    local b = CreateFrame("CheckButton", nil, parent)
    b:SetSize(size, size)
    b:SetNormalTexture(STOCK.checkBox .. "Up")
    b:SetPushedTexture(STOCK.checkBox .. "Down")
    b:SetHighlightTexture(STOCK.checkBox .. "Highlight", "ADD")
    b:SetCheckedTexture(STOCK.checkBox .. "Check")
    b:SetDisabledCheckedTexture(STOCK.checkBox .. "Check-Disabled")
    b.label = UI.Text(b, 12, C.gold)
    b.label:SetPoint("LEFT", b, "RIGHT", 2, 1)
    b.label:SetText(label or "")
    b:SetHitRectInsets(0, -(ceil(b.label:GetStringWidth() or 0) + 4), 0, 0)
    function b:SetActive(on)
        if on then
            self:Enable()
        else
            self:Disable()
        end
        UI.SetColor(self.label, on and C.gold or C.mute)
    end
    return b
end

------------------------------------------------------------------------------------------------------
-- Icons and glyphs
------------------------------------------------------------------------------------------------------
-- left, right, top, bottom of cell i (0-based) of an 8 x 4 atlas.
local function cellCoords(i)
    local c, r = i % 8, floor(i / 8)
    return c / 8, (c + 1) / 8, r / 4, (r + 1) / 4
end

local iconProbe, probeWorks
local iconPaths = {}

-- The file of an icon the client really has, for a glyph name (UI.GLYPH_ICONS), an icon name (INV_Misc_Bag_10) or a
-- path (Interface\Icons\..., any stock file). SetTexture answers nil for a missing file, silently, and then the
-- question mark stands in, as in the old addon: never an empty ring. A glyph with no picture answers nil.
function UI.IconPath(name)
    if type(name) ~= "string" or name == "" then
        return nil
    end
    local path = name
    if not name:find("\\", 1, true) then
        if UI.GLYPH_ICONS[name] then
            path = STOCK.icons .. UI.GLYPH_ICONS[name]
        elseif GLYPH_INDEX[name] then
            return nil
        else
            path = STOCK.icons .. name
        end
    end
    local known = iconPaths[path]
    if known then
        return known
    end
    if not iconProbe then
        iconProbe = UIParent:CreateTexture(nil, "BACKGROUND")
        iconProbe:Hide()
        -- only trust the probe when it finds a file that surely exists
        probeWorks = iconProbe:SetTexture(STOCK.question) and true or false
    end
    known = (not probeWorks or iconProbe:SetTexture(path)) and path or STOCK.question
    iconPaths[path] = known
    return known
end

-- The texture and texcoords of a glyph, for frames that draw it themselves (AddicatUI's micro menu).
function UI.GlyphArt(name)
    return UI.ART .. "Glyphs", cellCoords(GLYPH_INDEX[name] or GLYPH_INDEX.dot)
end

function UI.EmoteGlyphArt(name)
    return UI.ART .. "Emotes", cellCoords(EMOTE_INDEX[name] or EMOTE_INDEX.music)
end

-- A glyph on a texture. On a ring portrait (a badge, a window, a nav row) the glyph's icon shows instead, when it
-- has one.
function UI.SetGlyph(t, name)
    if t.isPortrait then
        local path = UI.IconPath(name)
        if path then
            t.showsIcon = true
            SetPortraitToTexture(t, path)
            t:SetTexCoord(0, 1, 0, 1)
            t:SetVertexColor(1, 1, 1)
            return
        end
        t.showsIcon = nil
    end
    t:SetTexture(UI.ART .. "Glyphs")
    t:SetTexCoord(cellCoords(GLYPH_INDEX[name] or GLYPH_INDEX.dot))
end

-- An emote glyph; unknown names show the music note.
function UI.SetEmoteGlyph(t, name)
    t:SetTexture(UI.ART .. "Emotes")
    t:SetTexCoord(cellCoords(EMOTE_INDEX[name] or EMOTE_INDEX.music))
end

-- A square icon as the client draws item and spell icons: the picture cropped (0.07-0.93) in a 1 px black edge.
-- Returns the frame; .icon is the texture. icon: anything UI.IconPath takes.
function UI.Icon(parent, size, icon)
    local f = CreateFrame("Frame", nil, parent)
    f:SetSize(size, size)
    f:SetBackdrop(OUTLINE)
    f:SetBackdropBorderColor(0, 0, 0, 1)
    f.icon = f:CreateTexture(nil, "ARTWORK")
    f.icon:SetPoint("TOPLEFT", f, "TOPLEFT", 1, -1)
    f.icon:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -1, 1)
    f.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    function f:SetIcon(name)
        self.icon:SetTexture(UI.IconPath(name) or STOCK.question)
    end
    f:SetIcon(icon)
    return f
end

-- A ring portrait as the old addon's ringIcon: the picture cut round by SetPortraitToTexture, inside
-- MiniMap-TrackingBorder drawn 1.7 times the size from the top left (its ring fills the texture's top left 38 of 64
-- pixels), over the minimap button's dark disc. A portrait keeps its icon's colours: a caller's tint (meant for a
-- glyph) does not recolour it.
local function portrait(t)
    t.isPortrait = true
    local setColor = t.SetVertexColor
    t.SetVertexColor = function(self, r, g, b, a)
        if self.showsIcon then
            setColor(self, 1, 1, 1, a)
        else
            setColor(self, r, g, b, a)
        end
    end
end

-- Size (or size again) a ring portrait: the frame, its dark disc, the picture and the ring keep their proportions.
function UI.SizeRing(f, size)
    f:SetSize(size, size)
    f.fill:SetSize(size * 0.8, size * 0.8)
    f.fill:ClearAllPoints()
    f.fill:SetPoint("CENTER", f, "TOPLEFT", size * 0.52, -size * 0.5)
    f.icon:SetSize(size * 0.62, size * 0.62)
    f.icon:ClearAllPoints()
    f.icon:SetPoint("TOPLEFT", f, "TOPLEFT", size * 0.2, -size * 0.18)
    f.ring:SetSize(size * 1.7, size * 1.7)
    f.ringSize = size
end

local function ringFrame(parent, size)
    local f = CreateFrame("Frame", nil, parent)
    f.fill = f:CreateTexture(nil, "BACKGROUND")
    f.fill:SetTexture(STOCK.ringBg)
    f.icon = f:CreateTexture(nil, "ARTWORK")
    portrait(f.icon)
    f.ring = f:CreateTexture(nil, "OVERLAY")
    f.ring:SetTexture(STOCK.ring)
    f.ring:SetPoint("TOPLEFT", f, "TOPLEFT", 0, 0)
    UI.SizeRing(f, size)
    return f
end

-- Show a glyph's icon (or an icon name or path) in a ring portrait; a glyph with no icon shows the glyph, tinted.
local function setRingIcon(f, icon, glyphColor)
    if not icon then
        f.icon:Hide()
        return
    end
    UI.SetGlyph(f.icon, icon)
    if not f.icon.showsIcon then
        f.icon:SetVertexColor(UI.Rgb(glyphColor or C.gold))
    end
    f.icon:Show()
end

-- A ring portrait with a glyph's icon (orbs, page heads). fill tints the dark disc behind the picture (seen
-- only without a glyph, where callers draw their own mark), ring tints the gold ring (gold: as the art is; a state
-- colour such as green is ignored: the ring stays gold), glyphColor the glyph of a glyph without an icon. .fill, .ring,
-- .glyph (the picture; UI.SetGlyph changes it), .icon. f:SetLocked(on) greys the picture (locked or not earned).
function UI.Badge(parent, size, glyph, fill, ring, glyphColor)
    local f = ringFrame(parent, size)
    if fill and fill ~= C.chip then
        f.fill:SetVertexColor(UI.Rgb(fill))
    end
    if ring and ring ~= C.gold and not STATE_EDGES[ring] then
        f.ring:SetVertexColor(UI.Rgb(ring))
    end
    setRingIcon(f, glyph, glyphColor)
    if glyph then
        f.glyph = f.icon
    end
    function f:SetIcon(icon)
        setRingIcon(self, icon, glyphColor)
        self.glyph = icon and self.icon or nil
    end
    function f:SetLocked(on)
        self.icon:SetDesaturated(on and true or false)
        self.icon:SetAlpha(on and 0.75 or 1)
    end
    return f
end

-- The stock indicator balls (COMMON\Indicator-*) for small status marks: "yellow", "green", "red", "gray", or a kit
-- colour (gold and orange are yellow, the greens green, red red, the rest grey). t:SetState(state) changes it.
local INDICATORS = { yellow = "Yellow", green = "Green", red = "Red", gray = "Gray" }
local function indicatorOf(state)
    if INDICATORS[state] then
        return INDICATORS[state]
    elseif state == C.gold or state == C.orange or state == C.goldDark then
        return "Yellow"
    elseif state == C.teal or state == C.bar then
        return "Green"
    elseif state == C.red then
        return "Red"
    end
    return "Gray"
end
function UI.StatusDot(parent, size, state, layer)
    local t = parent:CreateTexture(nil, layer or "ARTWORK")
    t:SetSize(size or 14, size or 14)
    function t:SetState(s)
        self:SetTexture(STOCK.indicator .. indicatorOf(s))
    end
    t:SetState(state)
    return t
end

-- The stock radio button (UI-RadioButton): its ring (the first cell) with the gold dot (the second cell, the checked
-- texture) over it while checked. t is the ring, t.dot the dot; t:SetChecked(on).
function UI.Radio(parent, size, checked, layer)
    local t = parent:CreateTexture(nil, layer or "ARTWORK")
    t:SetTexture(STOCK.radio)
    t:SetSize(size or 16, size or 16)
    t:SetTexCoord(0, 0.25, 0, 1)
    t.dot = parent:CreateTexture(nil, "OVERLAY")
    t.dot:SetTexture(STOCK.radio)
    t.dot:SetTexCoord(0.25, 0.5, 0, 1)
    t.dot:SetAllPoints(t)
    function t:SetChecked(on)
        if on then
            self.dot:Show()
        else
            self.dot:Hide()
        end
        self.checked = on and true or false
    end
    t:SetChecked(checked)
    return t
end

-- The class circles (TargetingFrame\UI-Classes-Circles) on FrameXML's CLASS_ICON_TCOORDS grid; kept here, as the
-- global is not one the lint knows.
UI.CLASS_TCOORDS = {
    WARRIOR = { 0, 0.25, 0, 0.25 }, MAGE = { 0.25, 0.5, 0, 0.25 }, ROGUE = { 0.5, 0.75, 0, 0.25 },
    DRUID = { 0.75, 1, 0, 0.25 }, HUNTER = { 0, 0.25, 0.25, 0.5 }, SHAMAN = { 0.25, 0.5, 0.25, 0.5 },
    PRIEST = { 0.5, 0.75, 0.25, 0.5 }, WARLOCK = { 0.75, 1, 0.25, 0.5 }, PALADIN = { 0, 0.25, 0.5, 0.75 },
    DEATHKNIGHT = { 0.25, 0.5, 0.5, 0.75 },
}

-- A class as a ring portrait of its class circle. f:SetClass(token) (WARRIOR, ...; an unknown class shows the
-- question mark), f:SetChosen(on): the chosen class in full colour, the others desaturated.
function UI.ClassPortrait(parent, size, class)
    local f = ringFrame(parent, size)
    f.icon.isPortrait = nil
    function f:SetClass(token)
        local tc = token and UI.CLASS_TCOORDS[token]
        self.class = token
        if tc then
            self.icon:SetTexture(STOCK.classes)
            self.icon:SetTexCoord(tc[1], tc[2], tc[3], tc[4])
        else
            SetPortraitToTexture(self.icon, STOCK.question)
            self.icon:SetTexCoord(0, 1, 0, 1)
        end
        self.icon:Show()
    end
    function f:SetChosen(on)
        self.icon:SetDesaturated(not on)
        self.ring:SetDesaturated(not on)
        self.chosen = on and true or false
    end
    f:SetClass(class)
    f:SetChosen(true)
    return f
end

-- An item as ItemButtonTemplate draws it: the full icon with UI-Quickslot2 (the slot's border) centred over it.
-- f.icon is the texture; f:SetIcon(icon) takes anything UI.IconPath takes; f:SetCollected(on) greys a missing one.
function UI.ItemButton(parent, size, icon)
    local f = CreateFrame("Frame", nil, parent)
    size = size or 36
    f:SetSize(size, size)
    f.icon = f:CreateTexture(nil, "ARTWORK")
    f.icon:SetAllPoints(f)
    f.border = f:CreateTexture(nil, "OVERLAY")
    f.border:SetTexture(STOCK.quickslot)
    f.border:SetSize(size * 64 / 37, size * 64 / 37)
    f.border:SetPoint("CENTER", f, "CENTER", 0, -1)
    function f:SetIcon(name)
        self.icon:SetTexture(UI.IconPath(name) or STOCK.question)
    end
    function f:SetCollected(on)
        self.icon:SetDesaturated(not on)
        self.icon:SetAlpha(on and 1 or 0.7)
    end
    f:SetIcon(icon)
    return f
end

-- An action or item slot drawn on button b's own layers (ActionButtonTemplate's art, so b's mouse-over light works):
-- b.icon (ARTWORK, size x size; the caller places it), UI-Quickslot2 round it (b.slotBorder), ButtonHilight-Square under
-- the cursor (b.slotGlow, ADD), CheckButtonHilight on the chosen one (b:SetSlotChecked(on); b.slotCheck). empty: the
-- empty action slot (UI-Quickslot) behind the icon (b.slotBg), for glyph marks and empty slots: in BORDER, above the
-- fill of a backdrop b may have (BACKGROUND; one layer is not drawn in creation order, see the top of this file).
function UI.SlotArt(b, size, empty)
    local frame = size * 64 / 37
    b.icon = b:CreateTexture(nil, "ARTWORK")
    b.icon:SetSize(size, size)
    local function around(layer, file)
        local t = b:CreateTexture(nil, layer)
        t:SetTexture(file)
        t:SetSize(frame, frame)
        t:SetPoint("CENTER", b.icon, "CENTER", 0, -1)
        return t
    end
    if empty then
        b.slotBg = around("BORDER", STOCK.quickslotEmpty)
    end
    b.slotBorder = around("OVERLAY", STOCK.quickslot)
    b.slotGlow = b:CreateTexture(nil, "HIGHLIGHT")
    b.slotGlow:SetTexture(STOCK.slotGlow)
    b.slotGlow:SetBlendMode("ADD")
    b.slotGlow:SetAllPoints(b.icon)
    b.slotCheck = b:CreateTexture(nil, "OVERLAY")
    b.slotCheck:SetTexture(STOCK.slotCheck)
    b.slotCheck:SetBlendMode("ADD")
    b.slotCheck:SetAllPoints(b.icon)
    b.slotCheck:Hide()
    function b:SetSlotChecked(on)
        if on then
            self.slotCheck:Show()
        else
            self.slotCheck:Hide()
        end
        self.slotChecked = on and true or false
    end
    return b.icon
end

-- The affixes' icons, by name (the old addon's choices), and the keystone levels the 1st..4th affix starts at.
UI.AFFIX_ICONS = {
    fortified = "Ability_Warrior_ShieldWall", tyrannical = "Ability_Warrior_Rampage",
    bolstering = "Ability_Warrior_BattleShout", raging = "Ability_Druid_ChallangingRoar",
    sanguine = "Spell_Shadow_BloodBoil", bursting = "Spell_Shadow_PlagueCloud", inspiring = "Spell_Holy_PrayerOfSpirit",
    necrotic = "Spell_Shadow_CreepingPlague", grievous = "Ability_Backstab", volcanic = "Spell_Fire_Volcano",
    explosive = "Spell_Fire_SelfDestruct", quaking = "Spell_Nature_Earthquake", avenger = "Ability_Warrior_RallyingCry",
    ["true sight"] = "Spell_Shadow_DetectInvisibility", resistant = "Spell_Frost_WizardMark",
    ["pack tactics"] = "Ability_Hunter_Pet_Wolf",
}
UI.AFFIX_LEVELS = { 2, 4, 7, 10 }

-- An affix as the old window showed it: its spell icon with the keystone level it starts at (+2) in the bottom right
-- corner, and a tooltip. f:SetAffix(name, level, text).
function UI.AffixIcon(parent, size)
    local f = UI.Icon(parent, size or 26)
    f.level = f:CreateFontString(nil, "OVERLAY")
    f.level:SetFont(UI.FONT_BODY, 10, "OUTLINE")
    f.level:SetTextColor(1, 1, 1)
    f.level:SetJustifyH("RIGHT")
    f.level:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -1, 1)
    f:EnableMouse(true)
    function f:SetAffix(name, level, text)
        local key = type(name) == "string" and name:lower() or ""
        self:SetIcon(UI.AFFIX_ICONS[key] or "INV_Misc_QuestionMark")
        self.level:SetText(level and ("+" .. level) or "")
        local lines = { U.Safe(name or "") }
        if text and text ~= "" then
            lines[#lines + 1] = U.Safe(text)
        end
        if level then
            lines[#lines + 1] = { "From keystone level +" .. level .. ".", C.dim }
        end
        self.tipLines = lines
    end
    f:SetScript("OnEnter", function(self)
        UI.ShowTooltip(self, self.tipLines)
    end)
    f:SetScript("OnLeave", function()
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    return f
end

-- A reward as quest rewards show it: a small icon and the name in its quality colour. f:SetReward(kind, amount,
-- itemId, text) takes a task's reward (ns.RewardText's arguments); the frame is as wide as icon and name.
UI.REWARD_ICONS = { C = "INV_Misc_Coin_17", S = "INV_Enchant_ShardBrilliantLarge", G = "INV_Misc_Coin_01",
    H = "INV_BannerPVP_02" }
local REWARD_COLORS = { C = C.epic }
UI.QUALITY = { [0] = "9D9D9D", "FFFFFF", "1EFF00", "0070DD", "A335EE", "FF8000", "E6CC80" }
function UI.Reward(parent, size, textSize)
    size = size or 16
    local f = CreateFrame("Frame", nil, parent)
    f:SetSize(size, size)
    f.icon = UI.Icon(f, size)
    f.icon:SetPoint("LEFT", f, "LEFT", 0, 0)
    f.text = UI.Text(f, textSize or 11, C.text)
    f.text:SetPoint("LEFT", f.icon, "RIGHT", 4, 0)
    function f:SetReward(kind, amount, itemId, text)
        local icon, color = UI.REWARD_ICONS[kind], REWARD_COLORS[kind] or C.text
        if kind == "I" and itemId then
            local _, _, quality, _, _, _, _, _, _, tex = GetItemInfo(itemId)
            icon = tex or (GetItemIcon and GetItemIcon(itemId))
            color = UI.QUALITY[quality or 1] or C.text
        end
        self.icon:SetIcon(icon or "INV_Misc_Bag_10")
        self.icon.icon:SetDesaturated(false)
        UI.SetColor(self.text, color)
        UI.SetText(self.text, ns.RewardText(kind, amount, itemId, text))
        self:SetWidth(size + 4 + floor((self.text:GetStringWidth() or 0) + 0.5))
    end
    return f
end

------------------------------------------------------------------------------------------------------
-- Buttons
------------------------------------------------------------------------------------------------------
-- Every style keeps the label (b.label), b:SetLabel, b:SetStyle, b:SetActive and b.tooltip. Looks:
--   panel   the red panel button (GameFontNormal, 12; 10 under 20 px), drawn at most 22 px tall however tall the
--           button; "tabOn" holds it down with its highlight locked on (the chosen one of 2-4 choices, lit as
--           FrameXML lights a selected button), "disabled" greys it; "ghost" is the small
--           one (20 px, a 10 px label) for minor actions
--   tab     the options frame's top tab for tab strips ("strip", "stripOn"), 24 tall, sitting on the panel under it:
--           the open tab drops 3 px so its legs cover the panel's top edge
--   text    a plain text button with the quest-title highlight ("link"; list rows use "row")
--   dialog  the StaticPopup button ("dialog")
--   row     a list row: highlight, and a check on the chosen row ("row", "rowOn")
--   field   the dropdown's label frame and arrow (UI.Dropdown)
-- Labels are gold, white under the cursor, grey when disabled; a held or chosen one is white. A label never wraps:
-- a button too narrow for its label grows to fit it (PanelTemplates_TabResize does the same for tabs).
local STYLES = {
    red = { art = "panel" }, gold = { art = "panel" }, teal = { art = "panel" }, green = { art = "panel" },
    dark = { art = "panel" }, disabled = { art = "panel", off = true },
    tab = { art = "panel" }, tabOn = { art = "panel", on = true },
    strip = { art = "tab" }, stripOn = { art = "tab", on = true },
    ghost = { art = "panel", small = true }, link = { art = "text" }, dialog = { art = "dialog" },
    row = { art = "row" }, rowOn = { art = "row", on = true },
    field = { art = "field" },
}
UI.STYLES = STYLES

local GOLD = { 1, 0.82, 0 }
local WHITE = { 1, 1, 1 }
local GREY = { 0.5, 0.5, 0.5 }
local NAV_TEXT = { 0.92, 0.88, 0.78 }

-- Lay the three slices over the button: the full height, or a fixed height h centred on it; dy moves them down.
local function placeSlices(t, b, h, dy)
    dy = dy or 0
    for i = 1, 3 do
        t[i]:ClearAllPoints()
    end
    if h then
        t[1]:SetPoint("LEFT", b, "LEFT", 0, -dy)
        t[3]:SetPoint("RIGHT", b, "RIGHT", 0, -dy)
        for i = 1, 3 do
            t[i]:SetHeight(h)
        end
        t[2]:SetPoint("LEFT", t[1], "RIGHT", 0, 0)
        t[2]:SetPoint("RIGHT", t[3], "LEFT", 0, 0)
    else
        t[1]:SetPoint("TOPLEFT", b, "TOPLEFT", 0, -dy)
        t[1]:SetPoint("BOTTOMLEFT", b, "BOTTOMLEFT", 0, -dy)
        t[3]:SetPoint("TOPRIGHT", b, "TOPRIGHT", 0, -dy)
        t[3]:SetPoint("BOTTOMRIGHT", b, "BOTTOMRIGHT", 0, -dy)
        t[2]:SetPoint("TOPLEFT", t[1], "TOPRIGHT", 0, 0)
        t[2]:SetPoint("BOTTOMRIGHT", t[3], "BOTTOMLEFT", 0, 0)
    end
end

-- three textures side by side over the button: fixed caps, the middle stretched between them
local function threeSlices(b, layer, blend)
    local t = {}
    for i = 1, 3 do
        t[i] = b:CreateTexture(nil, layer)
        if blend then
            t[i]:SetBlendMode(blend)
        end
    end
    placeSlices(t, b)
    return t
end

-- file on the three slices with U cuts u (four numbers) and V from v1 to v2 (v1 > v2 turns it upside down)
local function paintSlices(t, file, u, v1, v2, capW)
    for i = 1, 3 do
        t[i]:SetTexture(file)
        t[i]:SetTexCoord(u[i], u[i + 1], v1, v2)
        t[i]:Show()
    end
    t[1]:SetWidth(capW)
    t[3]:SetWidth(capW)
end

-- the caps' width: the stock size, or half a narrower button (a button laid out by its anchors has no width yet, and
-- gets its caps on the next paint)
local function capWidth(w, size)
    if not w or w <= 0 then
        return size
    end
    return min(size, floor(w / 2))
end

local function hideAll(t)
    if t then
        for _, x in ipairs(t) do
            x:Hide()
        end
    end
end

local PANEL_U = { 0, 0.09375, 0.53125, 0.625 }
local TAB_U = { 0, 0.15625, 0.84375, 1 }
local FIELD_U = { 0.1015625, 0.1953125, 0.8046875, 0.8984375 }

-- The art of each look, made the first time a button needs it.
local ART = {}

-- The art's own height is 22 px: a taller button draws it 22 tall in its middle (the small one 20), never a fat
-- lozenge.
local PANEL_H, PANEL_SMALL_H = 22, 20

function ART.panel(b)
    local a = { body = threeSlices(b, "BACKGROUND"), glow = threeSlices(b, "HIGHLIGHT", "ADD") }
    function a.paint(state, w, _, small)
        local cap = capWidth(w, 12)
        local bh = b:GetHeight() or 0
        local h = small and bh > PANEL_SMALL_H and PANEL_SMALL_H or (bh > 24 and PANEL_H) or nil
        if h ~= a.h then
            a.h = h
            placeSlices(a.body, b, h)
            placeSlices(a.glow, b, h)
        end
        paintSlices(a.body, STOCK.panelButton .. state, PANEL_U, 0, 0.6875, cap)
        paintSlices(a.glow, STOCK.panelButton .. "Highlight", PANEL_U, 0, 0.6875, cap)
    end
    function a.hide()
        hideAll(a.body)
        hideAll(a.glow)
    end
    return a
end

-- OptionsFrameTabButtonTemplate: the art is open at the bottom and see-through inside; the open tab is drawn 3 px
-- lower, so its legs run over the top edge of the panel the strip sits on. Tabs of a strip share one bottom line.
local TAB_DROP = 3

function ART.tab(b)
    local a = { body = threeSlices(b, "BACKGROUND") }
    a.glow = b:CreateTexture(nil, "HIGHLIGHT")
    a.glow:SetTexture(STOCK.tabHighlight)
    a.glow:SetBlendMode("ADD")
    a.glow:SetHeight(b:GetHeight() or 24)
    a.glow:SetPoint("LEFT", b, "LEFT", 10, -4)
    a.glow:SetPoint("RIGHT", b, "RIGHT", -10, -4)
    function a.paint(state, w, on)
        local cap = capWidth(w, 20)
        local dy = on and TAB_DROP or 0
        if dy ~= a.dy then
            a.dy = dy
            placeSlices(a.body, b, nil, dy)
        end
        paintSlices(a.body, on and STOCK.tabActive or STOCK.tabInactive, TAB_U, 0, 1, cap)
        for i = 1, 3 do
            a.body[i]:SetDesaturated(state == "Disabled")
        end
        if on then
            a.glow:Hide()
        else
            a.glow:Show()
        end
    end
    function a.hide()
        hideAll(a.body)
        a.glow:Hide()
    end
    return a
end

function ART.dialog(b)
    local a = {}
    a.body = b:CreateTexture(nil, "BACKGROUND")
    a.body:SetAllPoints(b)
    a.glow = b:CreateTexture(nil, "HIGHLIGHT")
    a.glow:SetAllPoints(b)
    a.glow:SetTexture(STOCK.dialogButton .. "Highlight")
    a.glow:SetBlendMode("ADD")
    a.glow:SetTexCoord(0, 1, 0, 0.71875)
    function a.paint(state)
        a.body:SetTexture(STOCK.dialogButton .. state)
        a.body:SetTexCoord(0, 1, 0, 0.71875)
        a.body:Show()
        a.glow:Show()
    end
    function a.hide()
        a.body:Hide()
        a.glow:Hide()
    end
    return a
end

-- the quest log's title highlight under the cursor (text buttons and list rows); rows also carry the check
local function highlightArt(b, alpha)
    local glow = b:CreateTexture(nil, "HIGHLIGHT")
    glow:SetTexture(STOCK.rowHighlight)
    glow:SetBlendMode("ADD")
    glow:SetAllPoints(b)
    glow:SetAlpha(alpha)
    return glow
end

function ART.text(b)
    local a = { glow = highlightArt(b, 0.7) }
    function a.paint()
        a.glow:Show()
    end
    function a.hide()
        a.glow:Hide()
    end
    return a
end

function ART.row(b)
    local a = { glow = highlightArt(b, 1) }
    a.check = b:CreateTexture(nil, "OVERLAY")
    a.check:SetTexture(STOCK.check)
    a.check:SetSize(16, 16)
    a.check:SetPoint("LEFT", b, "LEFT", 2, 0)
    function a.paint(_, _, on)
        a.glow:Show()
        if on then
            a.check:Show()
        else
            a.check:Hide()
        end
    end
    function a.hide()
        a.glow:Hide()
        a.check:Hide()
    end
    return a
end

-- UIDropDownMenuTemplate's frame: the label frame's art at its own 33 px (V 15-48 of the 64 px file), centred on the
-- 26 px field and standing over it as the stock one does (never squashed), and the 24 x 24 arrow button at the right.
local FIELD_ART_H = 33

function ART.field(b)
    local a = { body = threeSlices(b, "BACKGROUND") }
    placeSlices(a.body, b, FIELD_ART_H)
    a.arrow = b:CreateTexture(nil, "ARTWORK")
    a.arrow:SetSize(24, 24)
    a.arrow:SetPoint("RIGHT", b, "RIGHT", -2, 0)
    a.glow = b:CreateTexture(nil, "HIGHLIGHT")
    a.glow:SetTexture(STOCK.arrowHighlight)
    a.glow:SetBlendMode("ADD")
    a.glow:SetAllPoints(a.arrow)
    b.arrow = a.arrow
    function a.paint(state, w)
        paintSlices(a.body, STOCK.labelFrame, FIELD_U, 0.234375, 0.75, capWidth(w, 12))
        a.arrow:SetTexture(STOCK.arrow .. state)
        a.arrow:Show()
        a.glow:Show()
    end
    function a.hide()
        hideAll(a.body)
        a.arrow:Hide()
        a.glow:Hide()
    end
    return a
end

-- The old window's nav row: a dark gradient (blue when chosen, with a light blue 1 px edge), a faint line under it,
-- a faint white highlight; the ring portrait is added by UI.IconButton.
function ART.nav(b)
    local a = {}
    a.bg = b:CreateTexture(nil, "BACKGROUND")
    a.bg:SetAllPoints(b)
    a.bg:SetTexture(STOCK.white)
    a.edge = CreateFrame("Frame", nil, b)
    a.edge:SetAllPoints(b)
    a.edge:SetBackdrop(OUTLINE)
    a.edge:SetBackdropBorderColor(0.45, 0.68, 1, 1)
    a.line = b:CreateTexture(nil, "ARTWORK")
    a.line:SetTexture(1, 1, 1, 0.08)
    a.line:SetHeight(1)
    a.line:SetPoint("BOTTOMLEFT", b, "BOTTOMLEFT", 0, 0)
    a.line:SetPoint("BOTTOMRIGHT", b, "BOTTOMRIGHT", 0, 0)
    a.glow = b:CreateTexture(nil, "HIGHLIGHT")
    a.glow:SetAllPoints(b)
    a.glow:SetTexture(1, 1, 1, 0.05)
    function a.paint(_, _, on)
        if on then
            a.bg:SetGradientAlpha("HORIZONTAL", 0.16, 0.32, 0.65, 0.95, 0.05, 0.12, 0.3, 0.15)
            a.edge:Show()
        else
            a.bg:SetGradientAlpha("HORIZONTAL", 0.09, 0.1, 0.13, 0.85, 0.04, 0.04, 0.06, 0.2)
            a.edge:Hide()
        end
        a.bg:Show()
        a.line:Show()
        a.glow:Show()
    end
    function a.hide()
        a.bg:Hide()
        a.edge:Hide()
        a.line:Hide()
        a.glow:Hide()
    end
    return a
end

local function styleOf(b)
    return STYLES[b.style] or STYLES.dark
end

-- The label's size for a look: GameFontNormal (12) on the panel button, 10 on one under 20 px and on the small one,
-- 10 on tabs; the caller's size elsewhere (nav rows, list rows, fields, text buttons).
local function labelSize(b, look, st)
    local size = b.labelSize or 12
    if look == "panel" then
        if st.small or (b:GetHeight() or 0) < 20 then
            return 10
        end
        return min(size, 12)
    elseif look == "tab" then
        return 10
    elseif look == "dialog" then
        return min(size, 12)
    end
    return size
end

-- Where the label sits: tabs centre it under their rim (4 px low), the other looks keep their anchors.
local function placeLabel(b, look)
    local tab = look == "tab"
    if b.labelOnTab == tab then
        return
    end
    if tab or b.labelOnTab ~= nil then
        local inset = tab and 10 or 6
        local dy = tab and -4 or 0
        b.label:ClearAllPoints()
        b.label:SetPoint("LEFT", b, "LEFT", inset, dy)
        b.label:SetPoint("RIGHT", b, "RIGHT", -inset, dy)
    end
    b.labelOnTab = tab
end

-- A label never wraps; a panel button, a tab or a dialog button too narrow for its label (it would be cut) grows to
-- fit it with room on both sides: { the label's insets, the padding it grows to }.
local GROW = { panel = { 12, 24 }, tab = { 20, 32 }, dialog = { 12, 24 } }
local function fitLabel(b, look)
    UI.OneLine(b.label, max(1, (b:GetWidth() or 0) - 12))
    local pad = GROW[look]
    if pad then
        local tw = b.label:GetStringWidth() or 0
        if tw + pad[1] > (b:GetWidth() or 0) then
            b:SetWidth(ceil(tw + pad[2]))
        end
    end
end

local function applyStyle(b)
    local st = styleOf(b)
    local look = b.kind or st.art
    local off = b.enabled == false or st.off
    local on = st.on
    if b.kind == "nav" then
        on = b.style == "tabOn"
    end
    b.arts = b.arts or {}
    for name, a in pairs(b.arts) do
        if name ~= look then
            a.hide()
        end
    end
    local size = labelSize(b, look, st)
    if size ~= b.fontSize then
        b.fontSize = size
        b.label:SetFont(UI.FONT_BODY, size, "")
        fitLabel(b, look)
    end
    if look ~= b.look then
        b.look = look
        placeLabel(b, look)
        fitLabel(b, look)
    end
    local a = b.arts[look]
    if not a then
        a = ART[look](b)
        b.arts[look] = a
    end
    local state = off and "Disabled" or ((b.pressed or (on and look == "panel")) and "Down" or "Up")
    a.paint(state, b:GetWidth() or 0, on, st.small)
    -- the chosen one of a set is held down AND lit (FrameXML's selected button: LockHighlight), so it reads as the
    -- brightest of its row, never as the disabled-looking dark one
    if look == "panel" and on and not off then
        b:LockHighlight()
        b.highlightLocked = true
    elseif b.highlightLocked then
        b:UnlockHighlight()
        b.highlightLocked = nil
    end
    local color
    if off then
        color = GREY
    elseif b.hovered or b.pressed then
        color = WHITE
    elseif look == "nav" then
        color = on and GOLD or NAV_TEXT
    elseif look == "row" or look == "field" then
        color = WHITE
    else
        color = on and WHITE or GOLD
    end
    b.label:SetTextColor(color[1], color[2], color[3])
    if b.icon then
        b.icon:SetVertexColor(color[1], color[2], color[3])
    end
end

local function newButton(parent, w, h, label, style, size, kind)
    local b = CreateFrame("Button", nil, parent)
    -- CSimpleButton runs no OnEnter/OnLeave on a disabled button by default; a greyed button's tooltip says why it
    -- is greyed (Leave dungeon, Set difficulty: Mythic), so the motion scripts stay on (OnMouseDown checks enabled)
    b:SetMotionScriptsWhileDisabled(true)
    b:SetSize(w, h)
    b.style = style or "dark"
    b.kind = kind
    b.enabled = true
    b.labelSize = size or 12
    b.label = UI.Text(b, size or 12, C.gold, "body", "CENTER")
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
        self.hovered, self.pressed = false, false
        applyStyle(self)
        if self.tooltip and GameTooltip then
            GameTooltip:Hide()
        end
    end)
    b:SetScript("OnMouseDown", function(self)
        if self.enabled then
            self.pressed = true
            applyStyle(self)
        end
    end)
    b:SetScript("OnMouseUp", function(self)
        if self.pressed then
            self.pressed = false
            applyStyle(self)
        end
    end)
    function b:SetLabel(text)
        self.label:SetText(text or "")
        fitLabel(self, self.look)
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
            self.pressed = false
            self:Disable()
        end
        applyStyle(self)
    end
    applyStyle(b)
    return b
end

function UI.Button(parent, w, h, label, style, size)
    return newButton(parent, w, h, label, style, size)
end

-- A navigation row of the old window: a ring portrait of the glyph's icon (or an icon name or path) with the label
-- beside it; a button under 120 wide stacks the label under the ring. Style "tabOn" marks the open page.
function UI.IconButton(parent, w, h, glyph, label, style)
    local wide = w >= 120
    local b = newButton(parent, w, h, label, style or "tab", wide and 13 or 11, "nav")
    local size = wide and min(50, h - 12) or max(16, min(h - 24, w - 24, 50))
    b.ring = ringFrame(b, size)
    setRingIcon(b.ring, glyph)
    b.icon = b.ring.icon
    b.label:ClearAllPoints()
    if not label or label == "" then
        b.ring:SetPoint("CENTER", b, "CENTER", 0, 0)
    elseif wide then
        b.ring:SetPoint("LEFT", b, "LEFT", 6, -2)
        b.label:SetPoint("LEFT", b, "LEFT", size + 16, 0)
        b.label:SetPoint("RIGHT", b, "RIGHT", -6, 0)
        b.label:SetJustifyH("LEFT")
        -- a row laid out again at another height (Activities' nav fits every entry): the ring follows, the label
        -- stays beside it
        function b:SetRingSize(s)
            UI.SizeRing(self.ring, s)
            self.label:ClearAllPoints()
            self.label:SetPoint("LEFT", self, "LEFT", s + 16, 0)
            self.label:SetPoint("RIGHT", self, "RIGHT", -6, 0)
        end
    else
        b.ring:SetPoint("TOP", b, "TOP", 0, -4)
        b.label:SetPoint("BOTTOM", b, "BOTTOM", 0, 5)
    end
    function b:SetIcon(icon)
        setRingIcon(self.ring, icon)
    end
    applyStyle(b)
    return b
end

-- The panel close button (UIPanelCloseButton's art), 32 x 32.
function UI.CloseButton(parent, onClick)
    local b = CreateFrame("Button", nil, parent)
    b:SetSize(32, 32)
    b:SetNormalTexture(STOCK.close .. "Up")
    b:SetPushedTexture(STOCK.close .. "Down")
    b:SetDisabledTexture(STOCK.close .. "Disabled")
    b:SetHighlightTexture(STOCK.close .. "Highlight", "ADD")
    b:RegisterForClicks("LeftButtonUp")
    b:SetScript("OnClick", onClick)
    b.enabled = true
    function b:SetActive(on)
        self.enabled = on and true or false
        if on then
            self:Enable()
        else
            self:Disable()
        end
    end
    return b
end

------------------------------------------------------------------------------------------------------
-- Tags and bars
------------------------------------------------------------------------------------------------------
-- A short text tag (resets, counts, states): plain FRIZQT text in the caller's colour, never boxed (the stock frames
-- do not box text). f:SetValue(s) sets the text (escaped); f:SetValue(value, label) writes a gold label and a white
-- value ("Daily reset: 7 h 11 min"). The frame is as wide as its text, so UI.Row lays tags out with their gap.
function UI.Pill(parent, text, color, size)
    local f = CreateFrame("Frame", nil, parent)
    size = size or 11
    f:SetHeight(size + 4)
    f.text = UI.Text(f, size, color or C.text, "body", "LEFT")
    f.text:SetPoint("LEFT", f, "LEFT", 0, 0)
    function f:SetValue(s, label)
        if label and label ~= "" then
            self.text:SetText("|cffffd100" .. U.Safe(label) .. ":|r " .. U.Safe(s))
        else
            UI.SetText(self.text, s)
        end
        self:SetWidth(max(1, ceil(self.text:GetStringWidth() or 0)))
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

-- The achievement frame's progress bar: the UI-StatusBar fill (achievement green by default; the old neon green maps
-- to the achievement green; the text golds map to the cast bar's gold, as text gold on the bar's grey ramp turns to
-- mustard) on black at half alpha, in UI-Achievement-ProgressBar-Border (5 px of rim around the bar), with the count in
-- the middle (f.text, "14 / 20" or "80%"; empty by default). At least 14 px tall: a caller asking for less gets 14.
-- bg is kept for the callers. f:SetProgress(p, text) sets 0..1 and the text.
UI.BAR_MIN_H = 14
-- CastingBarFrame's start-cast colour (1.0, 0.7, 0.0)
UI.BAR_GOLD = "FFB300"
local BAR_COLORS = { [C.teal] = C.bar, [C.gold] = UI.BAR_GOLD, [C.goldLight] = UI.BAR_GOLD, [C.goldDark] = UI.BAR_GOLD }
local BAR_BORDER_U = { 0, 0.0625, 0.8125, 0.875 }
function UI.Bar(parent, w, h, color, bg)
    local f = CreateFrame("StatusBar", nil, parent)
    f:SetSize(w, max(UI.BAR_MIN_H, h or 0))
    f:SetStatusBarTexture(STOCK.statusBar)
    color = BAR_COLORS[color or C.teal] or color
    f:SetStatusBarColor(UI.Rgb(color))
    f:SetMinMaxValues(0, 1)
    f:SetValue(0)
    f.bg = f:CreateTexture(nil, "BACKGROUND")
    f.bg:SetTexture(0, 0, 0, 0.5)
    f.bg:SetAllPoints(f)
    -- the rim: a child frame above the fill, so it covers the fill's ends as the achievement bar does
    f.border = CreateFrame("Frame", nil, f)
    f.border:SetPoint("TOPLEFT", f, "TOPLEFT", -5, 5)
    f.border:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", 5, -5)
    f.border.parts = {}
    for i = 1, 3 do
        local t = f.border:CreateTexture(nil, "OVERLAY")
        t:SetTexture(STOCK.progressBorder)
        t:SetTexCoord(BAR_BORDER_U[i], BAR_BORDER_U[i + 1], 0, 0.75)
        f.border.parts[i] = t
    end
    local l, m, r = f.border.parts[1], f.border.parts[2], f.border.parts[3]
    l:SetWidth(16)
    l:SetPoint("TOPLEFT", f.border, "TOPLEFT", 0, 0)
    l:SetPoint("BOTTOMLEFT", f.border, "BOTTOMLEFT", 0, 0)
    r:SetWidth(16)
    r:SetPoint("TOPRIGHT", f.border, "TOPRIGHT", 0, 0)
    r:SetPoint("BOTTOMRIGHT", f.border, "BOTTOMRIGHT", 0, 0)
    m:SetPoint("TOPLEFT", l, "TOPRIGHT", 0, 0)
    m:SetPoint("BOTTOMRIGHT", r, "BOTTOMLEFT", 0, 0)
    f.text = f.border:CreateFontString(nil, "OVERLAY")
    f.text:SetFont(UI.FONT_BODY, 10, "")
    f.text:SetTextColor(1, 1, 1)
    f.text:SetShadowOffset(1, -1)
    f.text:SetShadowColor(0, 0, 0, 1)
    f.text:SetJustifyH("CENTER")
    f.text:SetPoint("CENTER", f, "CENTER", 0, 0)
    function f:SetProgress(p, text)
        self:SetValue(U.Clamp(p or 0, 0, 1))
        if text ~= nil then
            self.text:SetText(text)
        end
    end
    return f
end

-- A timer bar on the HUD as MirrorTimerTemplate draws it (the breath bar; CastingBarFrame looks the same): a StatusBar
-- 13 tall with the UI-StatusBar fill (the cast bar's gold by default; the text golds map to it as on UI.Bar) on black
-- at half alpha, CastingBar\UI-CastingBar-Border round it, and the label in GameFontHighlight (white 12) in its middle
-- (f.text). The border's art is made for a 195 px bar: its studded ends keep their size (40 px slices, 31 px of them
-- outside the bar) and its middle stretches to the bar's width; it reaches 11 px above the bar and 8 px under it.
-- f.border is the frame above the fill that holds the three slices (f.border.parts) and the text; f:SetProgress(p,
-- text) sets 0..1 and the text.
UI.TIMER_H = 13
UI.TIMER_OUT = 31
local TIMER_BORDER_U = { 0, 0.15625, 0.84375, 1 }
function UI.TimerBar(parent, w, color)
    local f = CreateFrame("StatusBar", nil, parent)
    f:SetSize(w, UI.TIMER_H)
    f:SetStatusBarTexture(STOCK.statusBar)
    color = BAR_COLORS[color or UI.BAR_GOLD] or color or UI.BAR_GOLD
    f:SetStatusBarColor(UI.Rgb(color))
    f:SetMinMaxValues(0, 1)
    f:SetValue(0)
    f.bg = f:CreateTexture(nil, "BACKGROUND")
    f.bg:SetTexture(0, 0, 0, 0.5)
    f.bg:SetAllPoints(f)
    f.border = CreateFrame("Frame", nil, f)
    f.border:SetPoint("TOPLEFT", f, "TOPLEFT", -UI.TIMER_OUT, 11)
    f.border:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", UI.TIMER_OUT, -8)
    f.border.parts = {}
    for i = 1, 3 do
        local t = f.border:CreateTexture(nil, "OVERLAY")
        t:SetTexture(STOCK.castBorder)
        t:SetTexCoord(TIMER_BORDER_U[i], TIMER_BORDER_U[i + 1], 0.25, 0.75)
        f.border.parts[i] = t
    end
    local l, m, r = f.border.parts[1], f.border.parts[2], f.border.parts[3]
    l:SetWidth(40)
    l:SetPoint("TOPLEFT", f.border, "TOPLEFT", 0, 0)
    l:SetPoint("BOTTOMLEFT", f.border, "BOTTOMLEFT", 0, 0)
    r:SetWidth(40)
    r:SetPoint("TOPRIGHT", f.border, "TOPRIGHT", 0, 0)
    r:SetPoint("BOTTOMRIGHT", f.border, "BOTTOMRIGHT", 0, 0)
    m:SetPoint("TOPLEFT", l, "TOPRIGHT", 0, 0)
    m:SetPoint("BOTTOMRIGHT", r, "BOTTOMLEFT", 0, 0)
    f.text = UI.Text(f.border, 12, C.text, "body", "CENTER")
    f.text:SetPoint("CENTER", f, "CENTER", 0, 1)
    function f:SetProgress(p, text)
        self:SetValue(U.Clamp(p or 0, 0, 1))
        if text ~= nil then
            self.text:SetText(text)
        end
    end
    return f
end

------------------------------------------------------------------------------------------------------
-- Tooltips
------------------------------------------------------------------------------------------------------
-- lines: { title, { text, colorHex, wrap }, ... } (server text must already be passed through U.Safe); the title in
-- gold and plain lines in white, as the old addon's tooltips
-- tip: the tooltip to fill, GameTooltip by default (the world map's pins pass WorldMapTooltip)
function UI.ShowTooltip(owner, lines, tip)
    tip = tip or GameTooltip
    if not tip or type(lines) ~= "table" then
        return
    end
    tip:SetOwner(owner, "ANCHOR_RIGHT")
    for i, line in ipairs(lines) do
        if type(line) == "string" then
            if i == 1 then
                tip:AddLine(line, GOLD[1], GOLD[2], GOLD[3])
            else
                tip:AddLine(line, 1, 1, 1, true)
            end
        elseif type(line) == "table" then
            local r, g, b = UI.Rgb(line[2] or C.mid)
            tip:AddLine(line[1] or "", r, g, b, line[3] and true or false)
        end
    end
    tip:Show()
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

-- Where the top edge of `region` sits, as a SetPoint against UIParent from the nearest third of the screen
-- (left, middle or right): a frame that grows downwards keeps its top, and a spot near a screen edge stays
-- there at another resolution. Returns point, relPoint, x, y (whole pixels), or nil before it has a place.
function UI.TopAnchorOf(region)
    local l, r, t = region:GetLeft(), region:GetRight(), region:GetTop()
    local ul, ur, ut = UIParent:GetLeft(), UIParent:GetRight(), UIParent:GetTop()
    if not (l and r and t and ul and ur and ut) or ur <= ul then
        return nil
    end
    local ratio = (region:GetEffectiveScale() or 1) / (UIParent:GetEffectiveScale() or 1)
    l, r, t = l * ratio, r * ratio, t * ratio
    local third = (ur - ul) / 3
    local cx = (l + r) / 2
    local point, x
    if cx < ul + third then
        point, x = "TOPLEFT", l - ul
    elseif cx > ur - third then
        point, x = "TOPRIGHT", r - ur
    else
        point, x = "TOP", cx - (ul + ur) / 2
    end
    return point, point, floor(x + 0.5), floor(t - ut + 0.5)
end

-- Frames other addons may move for Bleakhold (AddicatUI's editor mode, Integration.lua). Bleakhold keeps
-- the saved position: a mover moves its frame and stores the spot in BleakholdCharDB itself.
--   name, title, frame          unique key, label, the frame the editor outlines
--   begin(), finish()           editor opened (show the frame, sample content when idle) / closed
--   move(region, done)          follow `region` (a UIParent child over the frame); done = dropped, save it
--   reset(), isDefault()        forget the saved spot / true when there is none
--   visible()                   false keeps the frame out of the editor
ns.Movers = {}

function UI.AddMover(m)
    ns.Movers[#ns.Movers + 1] = m
    return m
end

UI.windows = {}

-- Saved positions load with the addon's saved variables (after the files ran): place windows then.
ns.On("DB_READY", function()
    for _, w in pairs(UI.windows) do
        UI.RestorePosition(w)
    end
end)

-- Where a window's content sits inside its frame: within the dialog border, under the title bar.
UI.WINDOW_INSETS = { left = 14, right = 14, top = 44, bottom = 14 }

-- The content size of a window of w x h.
function UI.ContentSize(w, h)
    local i = UI.WINDOW_INSETS
    return w - i.left - i.right, h - i.top - i.bottom
end

-- A Bleakhold window in the old window's chrome: the dialog frame, a dark title bar with the title centred in gold,
-- a ring portrait top left (glyph: a glyph name, an icon name or an Interface\Icons path; f:SetIcon changes it), the
-- panel close button top right. f.header covers the title bar: it drags the window, and callers hang small widgets
-- there; f.content is the area inside (UI.ContentSize). ESC closes it (UISpecialFrames); it remembers its position
-- and shrinks to fit a short screen. opts.openSound / opts.closeSound: the sounds (default igCharacterInfoOpen/Close).
function UI.Window(name, w, h, title, glyph, opts)
    opts = opts or {}
    local f = CreateFrame("Frame", name, UIParent)
    f:SetSize(w, h)
    f:SetFrameStrata("HIGH")
    f:SetToplevel(true)
    f:EnableMouse(true)
    f:SetBackdrop(BACKDROPS.window)
    f.backdropKind = "window"
    f:Hide()

    f.bar = f:CreateTexture(nil, "ARTWORK")
    f.bar:SetTexture(0, 0, 0, 0.55)
    f.bar:SetPoint("TOPLEFT", f, "TOPLEFT", 64, -12)
    f.bar:SetPoint("TOPRIGHT", f, "TOPRIGHT", -12, -12)
    f.bar:SetHeight(26)

    local header = CreateFrame("Frame", nil, f)
    header:SetPoint("TOPLEFT", f, "TOPLEFT", 12, -8)
    header:SetPoint("TOPRIGHT", f, "TOPRIGHT", -12, -8)
    header:SetHeight(34)
    f.header = header

    f.title = UI.Text(header, 14, C.gold, "body", "CENTER")
    f.title:SetPoint("CENTER", f.bar, "CENTER", 0, 0)
    UI.SetText(f.title, title or "")

    f.portrait = ringFrame(f, 62)
    f.portrait:SetPoint("TOPLEFT", f, "TOPLEFT", -6, 8)
    f.portrait:SetFrameLevel(f:GetFrameLevel() + 5)
    f.badge = f.portrait
    function f:SetIcon(icon)
        setRingIcon(self.portrait, icon or "star")
    end
    f:SetIcon(glyph)

    f.close = UI.CloseButton(f, function()
        f:Hide()
    end)
    f.close:SetPoint("TOPRIGHT", f, "TOPRIGHT", -4, -4)
    f.close:SetFrameLevel(f:GetFrameLevel() + 6)

    local inset = UI.WINDOW_INSETS
    f.content = CreateFrame("Frame", nil, f)
    f.content:SetPoint("TOPLEFT", f, "TOPLEFT", inset.left, -inset.top)
    f.content:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -inset.right, inset.bottom)

    f.openSound = opts.openSound or "igCharacterInfoOpen"
    f.closeSound = opts.closeSound or "igCharacterInfoClose"

    UI.MakeMovable(f, header)
    UI.RestorePosition(f)
    if UISpecialFrames then
        table.insert(UISpecialFrames, name)
    end
    f:SetScript("OnShow", function(self)
        -- shrink to fit a short screen, or a narrow one (a 4:3 or 5:4 screen is 1024 or 960 UI units wide)
        local ph = UIParent and UIParent:GetHeight() or 768
        local pw = UIParent and UIParent:GetWidth() or 1024
        local s = 1
        if ph and ph > 0 and h > ph - 40 then
            s = (ph - 40) / h
        end
        if pw and pw > 0 and w > pw - 40 then
            s = min(s, (pw - 40) / w)
        end
        self:SetScale(max(0.5, s))
        if PlaySound then
            PlaySound(self.openSound)
        end
        if self.OnOpen then
            ns.SafeCall(self.OnOpen, self)
        end
    end)
    f:SetScript("OnHide", function(self)
        if PlaySound then
            PlaySound(self.closeSound)
        end
        if self.OnClose then
            ns.SafeCall(self.OnClose, self)
        end
    end)
    UI.windows[name] = f
    return f
end

------------------------------------------------------------------------------------------------------
-- Scroll area (mouse wheel and a slim stock scroll bar, no FrameXML template)
------------------------------------------------------------------------------------------------------
local SCROLL_W, SCROLL_STEP = 16, 40
UI.SCROLL_W = SCROLL_W

-- one of the scroll bar's arrow buttons (UIPanelScrollUpButtonTemplate's art, 16 x 16)
local function scrollArrow(sf, dir)
    local b = CreateFrame("Button", nil, sf)
    b:SetSize(SCROLL_W, SCROLL_W)
    local file = "Interface\\Buttons\\UI-ScrollBar-Scroll" .. dir .. "Button-"
    b:SetNormalTexture(file .. "Up")
    b:SetPushedTexture(file .. "Down")
    b:SetDisabledTexture(file .. "Disabled")
    b:SetHighlightTexture(file .. "Highlight", "ADD")
    local states = { b:GetNormalTexture(), b:GetPushedTexture(), b:GetDisabledTexture(), b:GetHighlightTexture() }
    for _, t in ipairs(states) do
        t:SetTexCoord(0.2, 0.8, 0.25, 0.75)
    end
    b:RegisterForClicks("LeftButtonUp")
    return b
end

-- The character frame's scroll bar inside the right edge (16 px): the arrow buttons and, between them, the knob
-- (UI-ScrollBar-Knob on a Slider, so it drags too) in the stock track (UI-Character-ScrollBar: its top cap round the
-- up arrow, the rail, the bottom cap round the down arrow, 31 wide); it shows only while the content is taller than
-- the frame. Keep list content 20 px clear of the right edge. It scrolls 40 px a notch; a list of rows calls
-- sf:SetStep(rowH) to scroll by whole rows. sf.bar is the slider, sf.thumb its knob, sf.up / sf.down the arrows,
-- sf.track the track's three pieces.
function UI.Scroll(parent)
    local sf = CreateFrame("ScrollFrame", nil, parent)
    local child = CreateFrame("Frame", nil, sf)
    child:SetSize(10, 10)
    sf:SetScrollChild(child)
    sf.child = child
    sf.contentHeight = 0
    local up, down = scrollArrow(sf, "Up"), scrollArrow(sf, "Down")
    up:SetPoint("TOPRIGHT", sf, "TOPRIGHT", 0, 0)
    down:SetPoint("BOTTOMRIGHT", sf, "BOTTOMRIGHT", 0, 0)
    local bar = CreateFrame("Slider", nil, sf)
    bar:SetOrientation("VERTICAL")
    bar:SetWidth(SCROLL_W)
    bar:SetPoint("TOP", up, "BOTTOM", 0, -1)
    bar:SetPoint("BOTTOM", down, "TOP", 0, 1)
    bar:EnableMouse(true)
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(0)
    -- the track: the left column's top cap (24 px) and rail, the right column's rail end and bottom cap (24 px)
    local track = {}
    for i = 1, 3 do
        track[i] = sf:CreateTexture(nil, "BACKGROUND")
        track[i]:SetTexture(STOCK.scrollTrack)
        track[i]:SetWidth(31)
    end
    track[1]:SetTexCoord(0, 0.484375, 0, 0.09375)
    track[1]:SetHeight(24)
    track[1]:SetPoint("TOP", up, "TOP", 0, 5)
    track[3]:SetTexCoord(0.515625, 1, 0.3203125, 0.4140625)
    track[3]:SetHeight(24)
    track[3]:SetPoint("BOTTOM", down, "BOTTOM", 0, -2)
    track[2]:SetTexCoord(0, 0.484375, 0.09375, 1)
    track[2]:SetPoint("TOP", track[1], "BOTTOM", 0, 0)
    track[2]:SetPoint("BOTTOM", track[3], "TOP", 0, 0)
    bar:SetThumbTexture(STOCK.knob)
    local thumb = bar:GetThumbTexture()
    thumb:SetSize(SCROLL_W, 24)
    thumb:SetTexCoord(0.2, 0.8, 0.125, 0.875)
    sf.bar, sf.thumb, sf.up, sf.down, sf.track = bar, thumb, up, down, track
    local parts = { bar, thumb, up, down, track[1], track[2], track[3] }
    local function show(on)
        for _, p in ipairs(parts) do
            if on then
                p:Show()
            else
                p:Hide()
            end
        end
    end
    show(false)
    local function update(self)
        local h = self:GetHeight() or 0
        local total = self.contentHeight or 0
        local range = max(0, total - h)
        if range <= 0 or h <= 0 then
            show(false)
            return
        end
        local cur = U.Clamp(self:GetVerticalScroll() or 0, 0, range)
        bar.updating = true
        bar:SetHeight(max(1, h - 2 * SCROLL_W - 2))
        bar:SetMinMaxValues(0, range)
        bar:SetValue(cur)
        bar.updating = nil
        if cur > 0 then
            up:Enable()
        else
            up:Disable()
        end
        if cur < range then
            down:Enable()
        else
            down:Disable()
        end
        show(true)
    end
    -- a list of rows scrolls by whole rows (SetStep): the offset is a multiple of the row, except the very end
    local function snap(self, v, range)
        local step = self.rowStep
        if step and v < range then
            v = min(range, floor(v / step + 0.5) * step)
        end
        return U.Clamp(v, 0, range)
    end
    local function scrollBy(self, delta)
        local range = max(0, (self.contentHeight or 0) - (self:GetHeight() or 0))
        local v = (self:GetVerticalScroll() or 0) - (delta or 0) * (self.rowStep or SCROLL_STEP)
        self:SetVerticalScroll(snap(self, U.Clamp(v, 0, range), range))
        update(self)
    end
    bar:SetScript("OnValueChanged", function(self, value)
        if self.updating then
            return
        end
        local range = max(0, (sf.contentHeight or 0) - (sf:GetHeight() or 0))
        sf:SetVerticalScroll(snap(sf, U.Clamp(value or 0, 0, range), range))
        update(sf)
    end)
    up:SetScript("OnClick", function()
        scrollBy(sf, 1)
    end)
    down:SetScript("OnClick", function()
        scrollBy(sf, -1)
    end)
    sf:EnableMouseWheel(true)
    sf:SetScript("OnMouseWheel", scrollBy)
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
    -- A list of rows rowH tall, as FauxScrollFrame shows them: the wheel and the arrows move one row, and the offset
    -- stays on whole rows. Size the viewport to a whole number of rows (N * rowH), so no part of a row shows.
    function sf:SetStep(rowH)
        self.rowStep = (rowH and rowH > 0) and rowH or nil
        local range = max(0, (self.contentHeight or 0) - (self:GetHeight() or 0))
        self:SetVerticalScroll(snap(self, U.Clamp(self:GetVerticalScroll() or 0, 0, range), range))
        update(self)
    end
    return sf
end

------------------------------------------------------------------------------------------------------
-- Slider and page arrows
------------------------------------------------------------------------------------------------------
-- A horizontal slider in OptionsSliderTemplate's look: the slider bar backdrop, the stock thumb, a gold title above,
-- the value in white beside the title, and optional low / high labels under the ends. s.title, s.value, s.low,
-- s.high are FontStrings; the caller sets min, max, step, value and OnValueChanged as on any Slider.
local SLIDER_BACKDROP = { bgFile = STOCK.sliderBg, edgeFile = STOCK.sliderBorder, tile = true, tileSize = 8,
    edgeSize = 8,
    insets = { left = 3, right = 3, top = 6, bottom = 6 } }
function UI.Slider(parent, w, title, low, high)
    local s = CreateFrame("Slider", nil, parent)
    s:SetOrientation("HORIZONTAL")
    s:SetSize(w or 144, 17)
    s:SetHitRectInsets(0, 0, -10, -10)
    s:SetBackdrop(SLIDER_BACKDROP)
    s:SetThumbTexture(STOCK.sliderThumb)
    s.thumb = s:GetThumbTexture()
    s.thumb:SetSize(32, 32)
    s:EnableMouse(true)
    s.title = UI.Text(s, 10, C.gold, "body", "CENTER")
    s.title:SetPoint("BOTTOM", s, "TOP", 0, 2)
    s.title:SetText(title or "")
    s.value = UI.Text(s, 10, C.text, "body", "LEFT")
    s.value:SetPoint("LEFT", s.title, "RIGHT", 6, 0)
    s.low = UI.Text(s, 10, C.text, "body", "LEFT")
    s.low:SetPoint("TOPLEFT", s, "BOTTOMLEFT", 2, 3)
    s.low:SetText(low or "")
    s.high = UI.Text(s, 10, C.text, "body", "RIGHT")
    s.high:SetPoint("TOPRIGHT", s, "BOTTOMRIGHT", -2, 3)
    s.high:SetText(high or "")
    return s
end

-- The spellbook's round page arrows (UI-SpellbookIcon-PrevPage / -NextPage), 32 x 32, with the mouse-over light;
-- the Disabled art shows at the ends (b:SetActive(false)). which: "Prev" or "Next".
function UI.PageButton(parent, which, onClick)
    local b = CreateFrame("Button", nil, parent)
    b:SetSize(32, 32)
    which = which == "Prev" and "Prev" or "Next"
    local file = STOCK.page .. which .. "Page-"
    b:SetNormalTexture(file .. "Up")
    b:SetPushedTexture(file .. "Down")
    b:SetDisabledTexture(file .. "Disabled")
    b:SetHighlightTexture(STOCK.arrowHighlight, "ADD")
    b:RegisterForClicks("LeftButtonUp")
    if onClick then
        b:SetScript("OnClick", onClick)
    end
    b.enabled = true
    function b:SetActive(on)
        self.enabled = on and true or false
        if on then
            self:Enable()
        else
            self:Disable()
        end
    end
    return b
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
-- Dropdown list (own frames dressed like UIDropDownMenu: UIDropDownMenu itself would taint)
------------------------------------------------------------------------------------------------------
local openMenu
-- UIDropDownMenu's list rows: 16 tall, GameFontHighlightSmall (10), the check 16 x 16 at the left
local ROW_H, ROW_TEXT = 16, 10
UI.DROPDOWN_ROW_H = ROW_H

-- b.label shows the chosen item as UIDropDownMenuTemplate does (GameFontHighlightSmall, white 10, right-justified
-- just left of the arrow); b.arrow is the arrow; the list (b.menu) is a tooltip frame of rows with the quest-title
-- highlight and a check on the chosen one. Items: { value, text, tip }; tip (UI.ShowTooltip lines, optional) is the
-- row's tooltip.
function UI.Dropdown(parent, w, onSelect)
    local b = UI.Button(parent, w, 26, "", "field", ROW_TEXT)
    b.label:ClearAllPoints()
    b.label:SetPoint("LEFT", b, "LEFT", 14, 1)
    b.label:SetPoint("RIGHT", b.arrow, "LEFT", -4, 1)
    b.label:SetJustifyH("RIGHT")
    b.items = {}
    b.value = nil
    local menu = CreateFrame("Frame", nil, UIParent)
    menu:SetFrameStrata("FULLSCREEN_DIALOG")
    menu:SetClampedToScreen(true)
    -- opaque, so nothing under the list shows through its rows
    UI.Backdrop(menu, C.deep, C.strong, 1, "list")
    menu:Hide()
    menu:EnableMouse(true)
    b.menu = menu
    local rows = UI.Pool(function()
        local r = UI.Button(menu, w - 16, ROW_H, "", "row", ROW_TEXT)
        r.label:ClearAllPoints()
        r.label:SetPoint("LEFT", r, "LEFT", 20, 0)
        r.label:SetPoint("RIGHT", r, "RIGHT", -4, 0)
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
        if PlaySound then
            PlaySound("igMainMenuOptionCheckBoxOn")
        end
        rows:ReleaseAll()
        local y, widest = -8, 0
        local shown = {}
        for _, it in ipairs(self.items) do
            local r = rows:Acquire()
            r:SetLabel(it.text)
            widest = max(widest, r.label:GetStringWidth() or 0)
            shown[#shown + 1] = r
            r:SetStyle(it.value == self.value and "rowOn" or "row")
            r.tooltip = it.tip and function()
                return it.tip
            end or nil
            r:ClearAllPoints()
            r:SetPoint("TOPLEFT", menu, "TOPLEFT", 8, y)
            r:SetScript("OnClick", function()
                self:Close()
                self:SetValue(it.value)
            end)
            y = y - ROW_H
        end
        -- as UIDropDownMenu, the list is as wide as its widest entry (never narrower than the box): the row label
        -- starts 20 px in (after the check) and ends 4 px short, and the list has 8 px of frame on each side
        local mw = max(w, ceil(widest) + 20 + 4 + 16)
        for i = 1, #shown do
            shown[i]:SetWidth(mw - 16)
            UI.OneLine(shown[i].label, mw - 16 - 20 - 4)
        end
        menu:SetSize(mw, -y + 8)
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
-- Small dialogs: confirm, copy-to-clipboard (no LaunchURL in game) and a short text, in the StaticPopup look
------------------------------------------------------------------------------------------------------
local dialog

-- the input box's border (InputBoxTemplate: Common-Input-Border, 8 px caps, a little wider than the box on the left)
local function inputBorder(e)
    local t = {}
    for i = 1, 3 do
        t[i] = e:CreateTexture(nil, "BACKGROUND")
        t[i]:SetTexture(STOCK.input)
        t[i]:SetHeight(20)
    end
    t[1]:SetWidth(8)
    t[1]:SetTexCoord(0, 0.0625, 0, 0.625)
    t[1]:SetPoint("LEFT", e, "LEFT", -5, 0)
    t[3]:SetWidth(8)
    t[3]:SetTexCoord(0.9375, 1, 0, 0.625)
    t[3]:SetPoint("RIGHT", e, "RIGHT", 0, 0)
    t[2]:SetTexCoord(0.0625, 0.9375, 0, 0.625)
    t[2]:SetPoint("LEFT", t[1], "RIGHT", 0, 0)
    t[2]:SetPoint("RIGHT", t[3], "LEFT", 0, 0)
    return t
end
-- for other edit boxes (the Collections search): InputBoxTemplate's border on EditBox e, 20 px tall
UI.InputBorder = inputBorder

local function getDialog()
    if dialog then
        return dialog
    end
    local d = CreateFrame("Frame", "BleakholdDialog", UIParent)
    d:SetSize(340, 136)
    d:SetPoint("CENTER", UIParent, "CENTER", 0, 120)
    d:SetFrameStrata("DIALOG")
    d:SetToplevel(true)
    d:EnableMouse(true)
    d:SetBackdrop(BACKDROPS.popup)
    d.backdropKind = "popup"
    d.text = UI.Text(d, 13, C.text, "body", "CENTER")
    d.text:SetPoint("TOPLEFT", d, "TOPLEFT", 20, -20)
    d.text:SetPoint("TOPRIGHT", d, "TOPRIGHT", -20, -20)
    d.edit = CreateFrame("EditBox", nil, d)
    d.edit:SetSize(260, 20)
    d.edit:SetPoint("TOP", d.text, "BOTTOM", 3, -12)
    d.edit:SetFont(UI.FONT_BODY, 13, "")
    d.edit:SetTextColor(UI.Rgb(C.text))
    d.edit:SetAutoFocus(false)
    d.edit:SetTextInsets(0, 6, 0, 0)
    d.edit.border = inputBorder(d.edit)
    d.edit:SetScript("OnEscapePressed", function()
        d:Hide()
    end)
    d.edit:SetScript("OnEditFocusGained", function(self)
        self:HighlightText()
    end)
    d.ok = UI.Button(d, 128, 21, "Accept", "dialog")
    d.ok:SetPoint("BOTTOMRIGHT", d, "BOTTOM", -6, 16)
    d.cancel = UI.Button(d, 128, 21, "Cancel", "dialog")
    d.cancel:SetPoint("BOTTOMLEFT", d, "BOTTOM", 6, 16)
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

-- StaticPopup_Resize: as tall as the text, the input box when it shows, and the buttons
local function fitDialog(d)
    local th = d.text:GetStringHeight() or 13
    d:SetHeight(max(100, floor(20 + th + 14 + (d.edit:IsShown() and 32 or 0) + 21 + 18 + 0.5)))
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
    d.cancel:SetPoint("BOTTOMLEFT", d, "BOTTOM", 6, 16)
    fitDialog(d)
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
    d.cancel:SetPoint("BOTTOM", d, "BOTTOM", 0, 16)
    d.edit:Show()
    d.edit:SetText(value or "")
    fitDialog(d)
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
    d.cancel:SetPoint("BOTTOMLEFT", d, "BOTTOM", 6, 16)
    fitDialog(d)
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
