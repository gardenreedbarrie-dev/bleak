local addon = select(2, ...)
local L = addon.L

-- ============================================================================
-- BLEAKHOLD THEME FOR ADDICATUI
-- Dresses AddicatUI in the look of the Bleakhold addon (Bleakhold/Widgets.lua):
-- dark slate surfaces, muted gold borders, flat 1 px panels, the client's fonts.
--   * Chrome tinting (unit frames, bars, micro menu, minimap, bag slots, cast,
--     XP and rep bars, buff borders) is darkmode.lua's walker run with the
--     tints below; it reads them through addon.BleakTheme.
--   * This file covers what that walker does not: tooltips, dropdown menus,
--     the game menu, loot rolls, AddicatUI's retail panels and bag windows,
--     chat backgrounds and nameplate borders, plus the font switch.
-- Icons, portraits and health, mana and class colours are never touched.
-- Everything is applied on load, creation hooks and events; no OnUpdate.
-- ============================================================================

local ThemeModule = {
    initialized = false,
    applied = false,
    hooks = {},
    gen = 0, -- bumped on every apply/restore so recycled nameplates can tell they are stale
}

-- ============================================================================
-- PALETTE
-- ============================================================================

local function Rgb(hex)
    return { tonumber(hex:sub(1, 2), 16) / 255, tonumber(hex:sub(3, 4), 16) / 255, tonumber(hex:sub(5, 6), 16) / 255 }
end

-- The Bleakhold addon's palette (local C in Bleakhold/Widgets.lua), as 0-1 RGB.
local C = {
    bg = Rgb("0B0C0F"), panel = Rgb("15181D"), header = Rgb("1B1F25"), rail = Rgb("111317"),
    border = Rgb("2E333B"), strong = Rgb("4A4F57"), chipBorder = Rgb("3A3F47"),
    gold = Rgb("C9A25A"), goldLight = Rgb("E5C07B"), goldDark = Rgb("8A6A35"), text = Rgb("ECE7DD"),
}

-- Vertex colours darkmode.lua multiplies onto the chrome art. That art is mostly grey-silver
-- metal, so a warm multiplier turns it muted gold, and a dark cool one turns plates slate.
local TINTS = {
    chrome = { 0.80, 0.67, 0.45 }, -- borders, rings, bar, minimap and cast bar frames
    unitframe = { 0.74, 0.62, 0.42 }, -- unit frame borders, whose art is brighter than the rest
    button = { 0.62, 0.52, 0.36 }, -- action button frames: a step darker so the icons lead
    surface = { 0.20, 0.22, 0.26 }, -- backgrounds, slots, micro button plates
    aura = { 0.69, 0.56, 0.31 }, -- buff borders are a white mask, so this colour shows as is
}

local WHITE = "Interface\\Buttons\\WHITE8X8"
local FLAT = {
    bgFile = WHITE, edgeFile = WHITE, tile = false, tileSize = 0, edgeSize = 1,
    insets = { left = 1, right = 1, top = 1, bottom = 1 },
}
local WHITE_RGB = { 1, 1, 1 }

local TOOLTIP_ALPHA = 0.95
local MENU_ALPHA = 0.98

-- ============================================================================
-- CONFIGURATION
-- ============================================================================

local function GetStyle()
    local cfg = addon:GetModuleConfig("theme")
    if cfg and cfg.style == "classic" then
        return "classic"
    end
    return "bleakhold"
end

local function IsActive()
    return GetStyle() == "bleakhold"
end

addon.BleakTheme = { palette = C, tints = TINTS, IsActive = IsActive }
addon.IsBleakTheme = IsActive
addon.GetUITheme = GetStyle

local function SyncFonts()
    if addon.Fonts and addon.Fonts.SetStyle then
        addon.Fonts.SetStyle(GetStyle())
    end
end

-- Runs right after AceDB loads a profile (login and every switch), before RefreshConfig builds
-- anything, so the cooldown and other text created during init already gets the theme's faces.
if addon.ApplyDatabaseMigrations then
    hooksecurefunc(addon, "ApplyDatabaseMigrations", SyncFonts)
end

-- ============================================================================
-- BACKDROP DRESSING
-- ============================================================================

-- frame -> its backdrop and colours before we dressed it, for the restore
local dressed = {}

local function Dress(frame, bg, bgAlpha, border)
    if not dressed[frame] then
        local orig = { backdrop = frame:GetBackdrop() }
        if orig.backdrop then
            orig.r, orig.g, orig.b, orig.a = frame:GetBackdropColor()
            orig.br, orig.bg, orig.bb, orig.ba = frame:GetBackdropBorderColor()
        end
        dressed[frame] = orig
    end
    frame.__bleakDressing = true
    frame:SetBackdrop(FLAT)
    frame:SetBackdropColor(bg[1], bg[2], bg[3], bgAlpha or 1)
    frame:SetBackdropBorderColor(border[1], border[2], border[3], 1)
    frame.__bleakDressing = nil
end

local function Undress(frame)
    local orig = dressed[frame]
    if not orig then return end
    dressed[frame] = nil
    frame.__bleakDressing = true
    frame:SetBackdrop(orig.backdrop)
    if orig.backdrop then
        frame:SetBackdropColor(orig.r or 1, orig.g or 1, orig.b or 1, orig.a or 1)
        frame:SetBackdropBorderColor(orig.br or 1, orig.bg or 1, orig.bb or 1, orig.ba or 1)
    end
    frame.__bleakDressing = nil
end

-- ============================================================================
-- TOOLTIPS
-- ============================================================================

local TOOLTIPS = {
    "GameTooltip", "ItemRefTooltip", "WorldMapTooltip", "SmallTextTooltip", "FriendsTooltip",
    "ShoppingTooltip1", "ShoppingTooltip2", "ShoppingTooltip3",
    "ItemRefShoppingTooltip1", "ItemRefShoppingTooltip2", "ItemRefShoppingTooltip3",
    "WorldMapCompareTooltip1", "WorldMapCompareTooltip2", "WorldMapCompareTooltip3",
}

local abs = math.abs

local function IsDefaultTooltipBorder(r, g, b)
    local d = TOOLTIP_DEFAULT_COLOR
    local dr, dg, db = d and d.r or 1, d and d.g or 1, d and d.b or 1
    return r and abs(r - dr) < 0.01 and abs(g - dg) < 0.01 and abs(b - db) < 0.01
end

local function IsDefaultTooltipBackground(r, g, b)
    local d = TOOLTIP_DEFAULT_BACKGROUND_COLOR
    local dr, dg, db = d and d.r or 0.09, d and d.g or 0.09, d and d.b or 0.19
    return r and abs(r - dr) < 0.01 and abs(g - dg) < 0.01 and abs(b - db) < 0.01
end

-- Blizzard puts its default colours back on every hide; swap only those for ours as they land,
-- so class-coloured borders (tooltip module) and other addons' colours still come through.
local function OnTooltipBorderColor(self, r, g, b)
    if self.__bleakDressing or not ThemeModule.applied or not IsDefaultTooltipBorder(r, g, b) then return end
    self.__bleakDressing = true
    self:SetBackdropBorderColor(C.goldDark[1], C.goldDark[2], C.goldDark[3], 1)
    self.__bleakDressing = nil
end

local function OnTooltipBackdropColor(self, r, g, b)
    if self.__bleakDressing or not ThemeModule.applied or not IsDefaultTooltipBackground(r, g, b) then return end
    self.__bleakDressing = true
    self:SetBackdropColor(C.bg[1], C.bg[2], C.bg[3], TOOLTIP_ALPHA)
    self.__bleakDressing = nil
end

local function DressTooltips()
    for i = 1, #TOOLTIPS do
        local tip = _G[TOOLTIPS[i]]
        if tip and tip.SetBackdrop then
            if not tip.__bleakGuarded then
                hooksecurefunc(tip, "SetBackdropBorderColor", OnTooltipBorderColor)
                hooksecurefunc(tip, "SetBackdropColor", OnTooltipBackdropColor)
                tip.__bleakGuarded = true
            end
            Dress(tip, C.bg, TOOLTIP_ALPHA, C.goldDark)
        end
    end
end

local function UndressTooltips()
    for i = 1, #TOOLTIPS do
        local tip = _G[TOOLTIPS[i]]
        if tip then
            Undress(tip)
        end
    end
end

-- ============================================================================
-- DROPDOWN MENUS
-- ============================================================================

-- UIDropDownMenu colours these once on load, so dressing them once holds.
local function ForEachDropDownBackdrop(fn)
    for level = 1, UIDROPDOWNMENU_MAXLEVELS or 2 do
        local backdrop = _G["DropDownList" .. level .. "Backdrop"]
        if backdrop then fn(backdrop) end
        local menuBackdrop = _G["DropDownList" .. level .. "MenuBackdrop"]
        if menuBackdrop then fn(menuBackdrop) end
    end
end

local function DressDropDown(frame)
    Dress(frame, C.rail, MENU_ALPHA, C.chipBorder)
end

-- ============================================================================
-- GAME MENU
-- ============================================================================

-- Bleakhold window look: flat panel, gold line along the top, title in the title face.
local function FindGameMenuTitle(menu)
    for _, region in ipairs({ menu:GetRegions() }) do
        if region.GetObjectType and region:GetObjectType() == "FontString" then
            return region
        end
    end
    return nil
end

local function DressGameMenu()
    local menu = _G.GameMenuFrame
    if not menu or not menu.SetBackdrop then return end
    Dress(menu, C.panel, MENU_ALPHA, C.strong)

    local art = ThemeModule.gameMenuArt
    if not art then
        art = {}
        art.top = menu:CreateTexture(nil, "BORDER")
        art.top:SetTexture(WHITE)
        art.top:SetVertexColor(C.gold[1], C.gold[2], C.gold[3], 1)
        art.top:SetPoint("TOPLEFT", menu, "TOPLEFT", 1, -1)
        art.top:SetPoint("TOPRIGHT", menu, "TOPRIGHT", -1, -1)
        art.top:SetHeight(3)
        art.title = FindGameMenuTitle(menu)
        if art.title then
            art.titleFont = { art.title:GetFont() }
            art.titleColor = { art.title:GetTextColor() }
            art.titlePoint = { art.title:GetPoint(1) }
        end
        ThemeModule.gameMenuArt = art
    end
    art.top:Show()

    local header = _G.GameMenuFrameHeader
    if header then header:Hide() end

    local title = art.title
    if title and art.titlePoint[1] then
        local fonts = addon.Fonts
        title:ClearAllPoints()
        title:SetPoint("TOP", menu, "TOP", 0, -9)
        title:SetFont(fonts and fonts.TITLE or art.titleFont[1], 15, "")
        title:SetTextColor(C.goldLight[1], C.goldLight[2], C.goldLight[3], 1)
    end
end

local function UndressGameMenu()
    local menu = _G.GameMenuFrame
    if not menu then return end
    Undress(menu)
    local art = ThemeModule.gameMenuArt
    if not art then return end
    art.top:Hide()
    local header = _G.GameMenuFrameHeader
    if header then header:Show() end
    local title = art.title
    if title and art.titlePoint[1] then
        local p = art.titlePoint
        title:ClearAllPoints()
        title:SetPoint(p[1], p[2], p[3], p[4], p[5])
        if art.titleFont[1] then
            title:SetFont(art.titleFont[1], art.titleFont[2], art.titleFont[3])
        end
        local c = art.titleColor
        title:SetTextColor(c[1] or 1, c[2] or 0.82, c[3] or 0, c[4] or 1)
    end
end

-- ============================================================================
-- LOOT ROLLS
-- ============================================================================

local NUM_LOOT_ROLL_FRAMES = 4

local function DressLootRoll(frame)
    if not ThemeModule.applied then return end
    local name = frame:GetName()
    local decoration = _G[name .. "Decoration"]
    local bindOnPickup = decoration and decoration:IsShown()
    Dress(frame, C.panel, MENU_ALPHA, bindOnPickup and C.gold or C.strong)
    local corner = _G[name .. "Corner"]
    if corner then corner:Hide() end
end

-- GroupLootFrame_OnShow sets a fresh dialog backdrop on every roll, so dress after it each time;
-- that fresh backdrop (gold for bind-on-pickup) is the one a restore must put back.
local function OnLootRollShow(frame)
    dressed[frame] = nil
    DressLootRoll(frame)
end

local function ForEachLootRoll(fn)
    for i = 1, NUM_GROUP_LOOT_FRAMES or NUM_LOOT_ROLL_FRAMES do
        local frame = _G["GroupLootFrame" .. i]
        if frame then fn(frame) end
    end
end

local function UndressLootRoll(frame)
    Undress(frame)
    local corner = _G[frame:GetName() .. "Corner"]
    if corner then corner:Show() end
end

-- ============================================================================
-- RETAIL PANELS AND BAG WINDOWS (tinted through darkmode.lua's registered chrome)
-- ============================================================================

-- Containers dressed by AddicatUI_NineSlice: loot, character, spellbook, talents, map...
local panels = setmetatable({}, { __mode = "k" })
local EDGE_PIECES = {
    "TopLeftCorner", "TopRightCorner", "BottomLeftCorner", "BottomRightCorner",
    "TopEdge", "BottomEdge", "LeftEdge", "RightEdge",
}
local BAG_EDGES = { "topLeft", "topRight", "bottomLeft", "bottomRight", "top", "bottom", "left", "right" }
local MAX_CONTAINER_FRAMES = 13

local chromeList, surfaceList = {}, {}

local function CollectChrome()
    wipe(chromeList)
    if not IsActive() then return chromeList end
    for container in pairs(panels) do
        for i = 1, #EDGE_PIECES do
            local piece = container[EDGE_PIECES[i]]
            if piece then chromeList[#chromeList + 1] = piece end
        end
    end
    for i = 1, MAX_CONTAINER_FRAMES do
        local frame = _G["ContainerFrame" .. i]
        local chrome = frame and frame._addicatuiBagChrome
        if chrome then
            for j = 1, #BAG_EDGES do
                local piece = chrome[BAG_EDGES[j]]
                if piece then chromeList[#chromeList + 1] = piece end
            end
        end
    end
    return chromeList
end

local function CollectSurfaces()
    wipe(surfaceList)
    if not IsActive() then return surfaceList end
    for container in pairs(panels) do
        if container.Center then surfaceList[#surfaceList + 1] = container.Center end
    end
    for i = 1, MAX_CONTAINER_FRAMES do
        local frame = _G["ContainerFrame" .. i]
        local chrome = frame and frame._addicatuiBagChrome
        if chrome and chrome.background then surfaceList[#surfaceList + 1] = chrome.background end
    end
    return surfaceList
end

local function RefreshPanelChrome()
    if IsActive() and addon.RefreshDarkModeChrome then
        addon.RefreshDarkModeChrome()
    end
end

if addon.RegisterDarkModeChrome then
    addon.RegisterDarkModeChrome(CollectChrome)
    addon.RegisterDarkModeChrome(CollectSurfaces, "surface")
end

-- Panels are built lazily (first open), so follow every layout as it is applied.
if _G.AddicatUI_NineSlice and _G.AddicatUI_NineSlice.ApplyLayout then
    hooksecurefunc(_G.AddicatUI_NineSlice, "ApplyLayout", function(container)
        if container then
            panels[container] = true
            RefreshPanelChrome()
        end
    end)
end

-- ============================================================================
-- CHAT
-- ============================================================================

-- Stock chat backgrounds keep the colour the player picked; only Blizzard's default black
-- (the GetChatWindowInfo colour) is swapped for the panel slate.
local function PaintChatWindow(frame, r, g, b)
    local name = frame:GetName()
    if not name or not CHAT_FRAME_TEXTURES then return end
    for _, suffix in pairs(CHAT_FRAME_TEXTURES) do
        local object = _G[name .. suffix]
        local kind = object and object.GetObjectType and object:GetObjectType()
        if kind == "Texture" then
            object:SetVertexColor(r, g, b)
        elseif kind == "Button" then
            local normal, highlight = object:GetNormalTexture(), object:GetHighlightTexture()
            local pushed = object:GetPushedTexture()
            if normal then normal:SetVertexColor(r, g, b) end
            if highlight then highlight:SetVertexColor(r, g, b) end
            if pushed then pushed:SetVertexColor(r, g, b) end
        end
    end
end

local function IsDefaultChatColor(r, g, b)
    return r and r < 0.01 and g < 0.01 and b < 0.01
end

local function OnChatWindowColor(frame, r, g, b)
    if ThemeModule.applied and frame and IsDefaultChatColor(r, g, b) then
        PaintChatWindow(frame, C.panel[1], C.panel[2], C.panel[3])
    end
end

local function ForEachChatWindow(fn)
    for i = 1, NUM_CHAT_WINDOWS or 10 do
        local frame = _G["ChatFrame" .. i]
        if frame then fn(frame, i) end
    end
end

local function DressStockChat(frame, i)
    local _, _, r, g, b = GetChatWindowInfo(i)
    if IsDefaultChatColor(r, g, b) then
        PaintChatWindow(frame, C.panel[1], C.panel[2], C.panel[3])
    end
end

local function UndressStockChat(frame, i)
    local _, _, r, g, b = GetChatWindowInfo(i)
    if r then
        PaintChatWindow(frame, r, g, b)
    end
end

-- Chat Mods' own background and edit box skins: palette colours, the style's own opacity.
local function RecolourChatBackdrop(frame)
    if not frame or not frame:GetBackdrop() then return end
    local _, _, _, a = frame:GetBackdropColor()
    local _, _, _, ba = frame:GetBackdropBorderColor()
    frame:SetBackdropColor(C.bg[1], C.bg[2], C.bg[3], a or 0.85)
    if ba and ba > 0 then
        frame:SetBackdropBorderColor(C.goldDark[1], C.goldDark[2], C.goldDark[3], ba)
    end
end

local function DressChatmods()
    if not ThemeModule.applied then return end
    ForEachChatWindow(function(frame, i)
        RecolourChatBackdrop(frame._addicatUIBgFrame)
        RecolourChatBackdrop(_G["ChatFrame" .. i .. "EditBox"])
    end)
end

local function UndressChatmods()
    if addon.ApplyChatStyle then addon.ApplyChatStyle() end
    if addon.ApplyEditboxStyle then addon.ApplyEditboxStyle() end
end

-- ============================================================================
-- NAMEPLATES (retail skin chrome)
-- ============================================================================

-- Runs after the RetailChrome widget's Sync; the generation and tank flags keep it to one write
-- per plate per change. The tank border keeps Blizzard's yellow while it is lit.
local function TintPlate(plateData)
    if not plateData or not ThemeModule.initialized then return end
    local tank = plateData._tankBorderOn and true or false
    if plateData._bleakGen == ThemeModule.gen and plateData._bleakTank == tank then return end
    plateData._bleakGen, plateData._bleakTank = ThemeModule.gen, tank

    local A = addon.Nameplates and addon.Nameplates.atlas
    if not A or not A.SetSliceVertexColor then return end
    local rim = ThemeModule.applied and TINTS.chrome or WHITE_RGB
    local selected = ThemeModule.applied and C.goldLight or WHITE_RGB
    if not tank then
        A.SetSliceVertexColor(plateData._retailBg, rim[1], rim[2], rim[3], 1)
    end
    A.SetSliceVertexColor(plateData._retailPoBg, rim[1], rim[2], rim[3], 1)
    A.SetSliceVertexColor(plateData._retailCastFrame, rim[1], rim[2], rim[3], 1)
    A.SetSliceVertexColor(plateData._retailSelected, selected[1], selected[2], selected[3], 1)
end

local function TintAllPlates()
    local NP = addon.Nameplates
    local plates = NP and NP.module and NP.module.plates
    if not plates then return end
    for _, plateData in pairs(plates) do
        TintPlate(plateData)
    end
end

-- ============================================================================
-- HOOKS (installed once, at login, after every module has installed its own)
-- ============================================================================

local function InstallHooks()
    if ThemeModule.hooks.installed then return end
    ThemeModule.hooks.installed = true

    ForEachLootRoll(function(frame)
        frame:HookScript("OnShow", OnLootRollShow)
    end)

    -- bags_skin builds a bag's chrome in its own hook on this; ours runs after it.
    if ContainerFrame_GenerateFrame then
        hooksecurefunc("ContainerFrame_GenerateFrame", RefreshPanelChrome)
    end

    if FCF_SetWindowColor then
        hooksecurefunc("FCF_SetWindowColor", OnChatWindowColor)
    end
    -- The options panel and the module registry reach Chat Mods through these exports.
    for _, fnName in ipairs({ "ApplyChatStyle", "ApplyEditboxStyle", "ApplyChatModsSystem" }) do
        if type(addon[fnName]) == "function" then
            hooksecurefunc(addon, fnName, DressChatmods)
        end
    end

    local NP = addon.Nameplates
    local chrome = NP and NP.widgets and NP.widgets.Get and NP.widgets.Get("RetailChrome")
    if chrome and chrome.Sync then
        hooksecurefunc(chrome, "Sync", TintPlate)
    end
end

-- ============================================================================
-- APPLY / RESTORE SYSTEM
-- ============================================================================

local function ApplySkins()
    ThemeModule.applied = true
    ThemeModule.initialized = true
    ThemeModule.gen = ThemeModule.gen + 1

    DressTooltips()
    ForEachDropDownBackdrop(DressDropDown)
    DressGameMenu()
    ForEachLootRoll(function(frame)
        if frame:IsShown() then DressLootRoll(frame) end
    end)
    ForEachChatWindow(DressStockChat)
    DressChatmods()
    TintAllPlates()
    RefreshPanelChrome()
end

local function RestoreSkins()
    if not ThemeModule.applied then return end
    ThemeModule.applied = false
    ThemeModule.gen = ThemeModule.gen + 1

    UndressTooltips()
    ForEachDropDownBackdrop(Undress)
    UndressGameMenu()
    ForEachLootRoll(UndressLootRoll)
    ForEachChatWindow(UndressStockChat)
    UndressChatmods()
    TintAllPlates()
end

local loggedIn = false
local lastStyle = nil

-- Registry refresh (login, profile switch) and the options dropdown both land here.
local function RefreshTheme()
    local style = GetStyle()
    if loggedIn then
        if style == "bleakhold" then
            ApplySkins()
            -- Chat Mods recolours its frames from its own profile callback, which may run after us.
            addon:After(0.2, DressChatmods)
        else
            RestoreSkins()
        end
        if lastStyle and lastStyle ~= style and addon.RefreshDarkModeForTheme then
            addon.RefreshDarkModeForTheme()
        end
    end
    lastStyle = style
end

-- Switch the theme at runtime; fonts reach text built from now on (all of it after a /reload).
function addon.SetUITheme(style)
    if style ~= "classic" then
        style = "bleakhold"
    end
    local modules = addon.db and addon.db.profile and addon.db.profile.modules
    if not modules then return end
    if type(modules.theme) ~= "table" then
        modules.theme = {}
    end
    modules.theme.style = style
    SyncFonts()
    RefreshTheme()
end

if addon.RegisterModule then
    addon:RegisterModule("theme", ThemeModule,
        L["Interface Theme"],
        L["Bleakhold's dark slate and gold look for AddicatUI"],
        {
            isEnabled = IsActive,
            lifecycle = { refresh = RefreshTheme, restore = RefreshTheme },
        })
end

-- ============================================================================
-- INITIALIZATION
-- ============================================================================

local eventFrame = CreateFrame("Frame")
eventFrame:RegisterEvent("PLAYER_LOGIN")
eventFrame:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    loggedIn = true
    InstallHooks()
    RefreshTheme()
end)
