-- Bleakhold UI - WoW's own talent window, the way Bleakhold chose it. UI by Addicated.
-- Ported from the Bleakhold UI addon (BleakholdUI.lua, its talent and glyph panels). While AddicatUI's all-trees
-- talent window (the "talents" module) is off - the default - WoW's PlayerTalentFrame is the talent window, one tree
-- at a time, and this file dresses it:
--   * the nodes: "rank/max" under each icon, a green glow while a point can go in now, gold once maxed, no glow while
--     locked; the tree's name and its points big at the top;
--   * the spec panel at the window's right: 1st / 2nd / 3rd tree and Glyphs as big buttons on the tree's own
--     background art, "UI by Addicated" at its foot; WoW's bottom tabs hide behind it (pet talents keep them);
--   * the glyph page: each socket's glyph name under it and a hint line, or (talents.glyph_list) a list of the six
--     sockets over the page: click to place (over a glyph only after WoW's "existing glyph will be lost" question),
--     Shift + right-click to remove, Shift-click to link.
-- Decided at login, like the talents module itself (load-once): switching windows takes a /reload (Options > Panels
-- > Talents, /bhui talents). A hand-installed copy of the old Bleakhold UI addon draws the same panels; while it is
-- loaded this file leaves them to it rather than drawing everything twice.
local addon = select(2, ...)
local L = addon.L
local WC = addon.WindowChrome

local Classic = {}
addon.ClassicTalents = Classic

local GOLD = WC and WC.GOLD or { 0.90, 0.80, 0.50 }
local CREDIT = "UI by Addicated"
local TOOLTIP_BG = "Interface\\Tooltips\\UI-Tooltip-Background"
local TOOLTIP_EDGE = "Interface\\Tooltips\\UI-Tooltip-Border"
local QUESTION = "Interface\\Icons\\INV_Misc_QuestionMark"
local MAX_NODES = 40

local active                                  -- decided at PLAYER_LOGIN

-- WoW's window while AddicatUI's is off (read at login; the talents module is load-once)
function Classic.Wanted()
    return not addon:IsModuleEnabled("talents")
end

function Classic.Active()
    return active and true or false
end

local function profile()
    local p = addon.db and addon.db.profile
    return p and p.talents
end

-- the optional list view over WoW's round glyph page
function Classic.GlyphList()
    local t = profile()
    return t and t.glyph_list == true or false
end

local function backdrop(frame, edgeSize, inset)
    frame:SetBackdrop({ bgFile = TOOLTIP_BG, edgeFile = TOOLTIP_EDGE, tile = true, tileSize = 16, edgeSize = edgeSize,
        insets = { left = inset, right = inset, top = inset, bottom = inset } })
end

-- ------------------------------------------------------------------ the talent window: nodes and the spec panel
local SP, HEAD
local glyphView                                  -- the glyph page's view, below

local function selectedTab()
    return PanelTemplates_GetSelectedTab and PanelTemplates_GetSelectedTab(PlayerTalentFrame)
end

-- talent nodes on WoW's own buttons: "rank/max" under each icon, green glow = learnable now, gold = maxed, no glow =
-- locked; the tree's name and points big at the top. The fields (bhGlow, bhRank) are the old addon's names, so a
-- node it dressed already is not dressed twice.
local function styleTalents()
    if not PlayerTalentFrame then return end
    local tab = selectedTab()
    local pet = PlayerTalentFrame.pet and true or false
    if not HEAD then
        HEAD = PlayerTalentFrame:CreateFontString(nil, "OVERLAY")
        HEAD:SetFont("Fonts\\MORPHEUS.ttf", 22, "OUTLINE")
        HEAD:SetPoint("TOP", PlayerTalentFrame, "TOP", 10, -46)
    end
    if pet or not tab or tab > 3 then HEAD:Hide() else HEAD:Show() end
    local group = PlayerTalentFrame.talentGroup
    local preview = GetCVarBool and GetCVarBool("previewTalents")
    local name, _, spent, _, previewSpent = GetTalentTabInfo(tab or 1, false, pet, group)
    if preview and previewSpent then spent = (spent or 0) + previewSpent end
    spent = spent or 0
    if not pet and tab and tab <= 3 then
        HEAD:SetText("|cffe6cc80" .. string.upper(name or "") .. "|r   |cff40ff40" .. spent .. "|r")
    end
    local unspent = (GetUnspentTalentPoints and GetUnspentTalentPoints(false, pet, group)) or 0
    local editable = pet or group == nil or group == GetActiveTalentGroup()
    for i = 1, MAX_NODES do
        local b = _G["PlayerTalentFrameTalent" .. i]
        if not b then break end
        if not b.bhGlow then
            b.bhGlow = b:CreateTexture(nil, "OVERLAY")
            b.bhGlow:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
            b.bhGlow:SetBlendMode("ADD")
            b.bhGlow:SetPoint("CENTER", b, "CENTER", 0, 0)
            b.bhGlow:SetSize((b:GetWidth() or 37) * 1.85, (b:GetHeight() or 37) * 1.85)
            b.bhRank = b:CreateFontString(nil, "OVERLAY")
            b.bhRank:SetFont(STANDARD_TEXT_FONT or "Fonts\\FRIZQT__.TTF", 11, "OUTLINE")
            b.bhRank:SetPoint("TOP", b, "BOTTOM", 0, 1)
            local n = b:GetName()
            -- WoW's small corner counter: the rank under the icon replaces it
            if n and _G[n .. "Rank"] then _G[n .. "Rank"]:SetAlpha(0) end
            if n and _G[n .. "RankBorder"] then _G[n .. "RankBorder"]:SetAlpha(0) end
        end
        if b:IsShown() and tab and tab <= 3 then
            local _, _, tier, _, rank, maxRank, _, meets, previewRank = GetTalentInfo(tab, b:GetID(), false, pet, group)
            if preview and previewRank then rank = previewRank end
            rank, maxRank, tier = rank or 0, maxRank or 1, tier or 1
            b.bhRank:SetText(rank .. "/" .. maxRank)
            local tierOk = spent >= (tier - 1) * 5
            if rank >= maxRank then
                b.bhGlow:SetVertexColor(1, 0.82, 0)
                b.bhGlow:Show()
                b.bhRank:SetTextColor(1, 0.82, 0)
            elseif editable and meets and tierOk and unspent > 0 then
                b.bhGlow:SetVertexColor(0.2, 1, 0.2)
                b.bhGlow:Show()
                b.bhRank:SetTextColor(0.25, 1, 0.25)
            elseif rank > 0 then
                b.bhGlow:Hide()
                b.bhRank:SetTextColor(0.25, 1, 0.25)
            else
                b.bhGlow:Hide()
                b.bhRank:SetTextColor(0.55, 0.55, 0.55)
            end
            b.bhRank:Show()
        else
            b.bhGlow:Hide()
            b.bhRank:Hide()
        end
    end
end

local function refreshSpecs()
    if not SP or not PlayerTalentFrame then return end
    styleTalents()
    local pet = PlayerTalentFrame.pet and true or false
    for i = 1, 4 do                                           -- the bottom tabs: hidden, the panel replaces them
        local tab = _G["PlayerTalentFrameTab" .. i]
        if tab then
            tab:SetAlpha(pet and 1 or 0)
            tab:EnableMouse(pet)
        end
    end
    if pet then                                               -- pet talents: WoW's own tabs
        SP:Hide()
        return
    end
    SP:Show()
    local group = PlayerTalentFrame.talentGroup
    local sel = selectedTab()
    for i = 1, 4 do
        local b = SP.buttons[i]
        local tab = _G["PlayerTalentFrameTab" .. i]
        if i <= 3 then
            local name, icon, points, background = GetTalentTabInfo(i, false, false, group)
            b.icon:SetTexture(icon or QUESTION)
            if background and background ~= "" then
                b.art:SetTexture("Interface\\TalentFrame\\" .. background .. "-TopLeft")
                b.art:Show()
            else
                b.art:Hide()
            end
            b.name:SetText(name or "")
            b.sub:SetText(string.format(L["%d points"], points or 0))
            if name then b:Show() else b:Hide() end
        else
            if tab and tab:IsShown() then b:Show() else b:Hide() end   -- Glyphs (from level 15)
        end
        if sel == i then
            b:SetBackdropBorderColor(1, 0.82, 0, 1)
        else
            b:SetBackdropBorderColor(0.4, 0.4, 0.4, 1)
        end
    end
end
Classic.Refresh = refreshSpecs

local function specPanel()
    if SP or not PlayerTalentFrame then return end
    SP = CreateFrame("Frame", "AddicatUI_TalentSpecPanel", PlayerTalentFrame)
    SP:SetSize(178, 286)
    -- clear of WoW's dual-spec and pet-talent tabs (PlayerSpecTab1-3 at TOPRIGHT -32, art out to +29)
    SP:SetPoint("TOPLEFT", PlayerTalentFrame, "TOPRIGHT", 30, -40)
    backdrop(SP, 16, 4)
    SP:SetBackdropColor(0.03, 0.03, 0.05, 0.92)
    SP:SetBackdropBorderColor(0.55, 0.55, 0.55, 1)
    SP.title = SP:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    SP.title:SetPoint("TOP", 0, -10)
    SP.title:SetText(L["Specializations"])
    SP.buttons = {}
    local labels = { L["1st"], L["2nd"], L["3rd"] }
    for i = 1, 4 do
        local b = CreateFrame("Button", nil, SP)
        b:SetSize(158, 54)
        b:SetPoint("TOP", SP, "TOP", 0, -30 - (i - 1) * 58)
        backdrop(b, 12, 3)
        b:SetBackdropColor(0.10, 0.10, 0.14, 0.95)
        -- the tree's own background art (WoW's talent backgrounds), darkened towards the text
        b.art = b:CreateTexture(nil, "BORDER")
        b.art:SetPoint("TOPLEFT", 3, -3)
        b.art:SetPoint("BOTTOMRIGHT", -3, 3)
        b.art:SetTexCoord(0.05, 0.95, 0.30, 0.62)
        b.art:SetAlpha(0.75)
        b.shade = b:CreateTexture(nil, "ARTWORK")
        b.shade:SetPoint("TOPLEFT", 3, -3)
        b.shade:SetPoint("BOTTOMRIGHT", -3, 3)
        b.shade:SetTexture(0, 0, 0, 1)
        b.shade:SetGradientAlpha("HORIZONTAL", 0, 0, 0, 0.85, 0, 0, 0, 0.15)
        b.icon = b:CreateTexture(nil, "OVERLAY")
        b.icon:SetSize(36, 36)
        b.icon:SetPoint("LEFT", 8, 0)
        b.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
        b.name = b:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
        b.name:SetPoint("TOPLEFT", b.icon, "TOPRIGHT", 8, -1)
        b.name:SetWidth(100)
        b.name:SetJustifyH("LEFT")
        b.sub = b:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        b.sub:SetPoint("BOTTOMLEFT", b.icon, "BOTTOMRIGHT", 8, 2)
        b:SetHighlightTexture("Interface\\Buttons\\UI-Listbox-Highlight2")
        if i <= 3 then
            b.tag = b:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
            b.tag:SetPoint("TOPRIGHT", -7, -5)
            b.tag:SetText(labels[i])
        else
            b.icon:SetTexture("Interface\\Icons\\INV_Inscription_Tradeskill01")
            b.art:SetTexture("Interface\\Spellbook\\UI-GlyphFrame")
            b.art:SetTexCoord(0.10, 0.70, 0.30, 0.50)
            b.name:SetText(L["Glyphs"])
            b.sub:SetText(L["major and minor"])
        end
        b:SetScript("OnClick", function()
            local tab = _G["PlayerTalentFrameTab" .. i]
            if tab and tab:IsShown() then tab:Click() end         -- WoW's own tab: everything else stays WoW's
            refreshSpecs()
        end)
        SP.buttons[i] = b
    end
    SP.credit = SP:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    SP.credit:SetPoint("BOTTOM", 0, 9)
    SP.credit:SetText(CREDIT)
    SP.credit:SetTextColor(GOLD[1], GOLD[2], GOLD[3], 0.85)
    PlayerTalentFrame:HookScript("OnShow", refreshSpecs)
    -- Every redraw of WoW's window goes through PlayerTalentFrame_Refresh, called by name: its OnShow, the dual-spec
    -- and pet tabs (PlayerSpecTab_OnClick), its bottom tabs, the talent and pet events and preview points. Its hook
    -- runs once TalentFrame_Update has laid the buttons out for the spec now shown. A spec tab click fires no event
    -- and leaves a shown GlyphFrame shown (no OnShow), so the glyph page is redrawn from here as well.
    if PlayerTalentFrame_Refresh then
        hooksecurefunc("PlayerTalentFrame_Refresh", function()
            refreshSpecs()
            if GlyphFrame and GlyphFrame:IsShown() then glyphView() end
        end)
    end
    -- The window calls the copy of PlayerTalentFrame_Update its OnLoad stored (self.updateFunction), never this
    -- global: by name it runs only on PLAYER_LEVEL_UP (the Glyphs tab from level 15).
    if PlayerTalentFrame_Update then hooksecurefunc("PlayerTalentFrame_Update", refreshSpecs) end
    refreshSpecs()
end

-- ------------------------------------------------------------------ the glyph page (WoW's own, Blizzard_GlyphUI)
-- WoW's glyph API: GetGlyphSocketInfo / GlyphMatchesSocket / PlaceGlyphInSocket, its CONFIRM_REMOVE_GLYPH and
-- CONFIRM_GLYPH_PLACEMENT popups (FrameXML StaticPopup.lua, always loaded), GetGlyphLink and GameTooltip:SetGlyph.
-- Sockets 1 4 6 are major, 2 3 5 minor (3.3.5), unlocked at these levels:
local GLYPH_LEVEL = { 15, 15, 50, 30, 70, 80 }
local MAJOR, MINOR = { 1, 4, 6 }, { 2, 3, 5 }
local CLASS_GLYPH = { DEATHKNIGHT = "DeathKnight", DRUID = "Druid", HUNTER = "Hunter", MAGE = "Mage",
    PALADIN = "Paladin", PRIEST = "Priest", ROGUE = "Rogue", SHAMAN = "Shaman", WARLOCK = "Warlock",
    WARRIOR = "Warrior" }
local GLYPH_EVENTS = { "GLYPH_ADDED", "GLYPH_REMOVED", "GLYPH_UPDATED", "GLYPH_ENABLED", "GLYPH_DISABLED",
    "PLAYER_LEVEL_UP", "ACTIVE_TALENT_GROUP_CHANGED" }
local GL, LABELS
-- the list's place on GlyphFrame (buildGlyphList) and its rows: two headings and six rows fit its 368 px height
local GLYPH_LIST_INSET = { left = 18, top = -66, right = -38, bottom = 78 }
local GLYPH_ROW_H, GLYPH_ROW_STEP = 44, 47

local function glyphGroup()
    return (PlayerTalentFrame and PlayerTalentFrame.talentGroup) or GetActiveTalentGroup()
end

local function glyphIcon(major)
    local _, class = UnitClass("player")
    return "Interface\\Icons\\INV_Glyph_" .. (major and "Major" or "Minor") .. (CLASS_GLYPH[class or ""] or "Warrior")
end

local function refreshGlyphs()
    if not GL or not GL:IsVisible() then return end
    local group = glyphGroup()
    local activeGroup = group == GetActiveTalentGroup()
    local targeting = SpellIsTargeting and SpellIsTargeting()
    for _, row in ipairs(GL.rows) do
        local enabled, _, spellID, icon = GetGlyphSocketInfo(row.id, group)
        local major = row.major
        row.spellID = (enabled and spellID and spellID > 0) and spellID or nil
        row.glow:Hide()
        if not enabled then
            row.icon:SetTexture("Interface\\LFGFrame\\UI-LFG-ICON-LOCK")
            row.icon:SetDesaturated(nil)
            row.name:SetText(major and L["Major socket"] or L["Minor socket"])
            row.name:SetTextColor(0.5, 0.5, 0.5)
            row.sub:SetText(string.format(L["Unlocks at level %d"], GLYPH_LEVEL[row.id]))
        elseif row.spellID then
            row.icon:SetTexture(icon or glyphIcon(major))
            row.icon:SetDesaturated(nil)
            row.name:SetText(GetSpellInfo(row.spellID) or L["Glyph"])
            if major then row.name:SetTextColor(1, 0.82, 0) else row.name:SetTextColor(0.55, 0.78, 1) end
            row.sub:SetText(activeGroup and L["Shift + right-click to remove"] or L["Other specialization"])
        else
            row.icon:SetTexture(glyphIcon(major))
            row.icon:SetDesaturated(1)
            row.name:SetText(major and L["Empty major socket"] or L["Empty minor socket"])
            row.name:SetTextColor(0.8, 0.8, 0.8)
            row.sub:SetText(L["Use a glyph from your bags, then click here"])
        end
        if targeting and enabled and activeGroup and GlyphMatchesSocket(row.id) then row.glow:Show() end
    end
end

local function glyphRow(parent, id, major, y)
    local r = CreateFrame("Button", nil, parent)
    r.id, r.major = id, major
    r:SetHeight(GLYPH_ROW_H)
    r:SetPoint("TOPLEFT", parent, "TOPLEFT", 10, y)
    r:SetPoint("TOPRIGHT", parent, "TOPRIGHT", -10, y)
    backdrop(r, 12, 3)
    r:SetBackdropColor(0.07, 0.07, 0.10, 0.92)
    if major then r:SetBackdropBorderColor(0.60, 0.50, 0.25, 1) else r:SetBackdropBorderColor(0.30, 0.42, 0.60, 1) end
    r.icon = r:CreateTexture(nil, "ARTWORK")
    r.icon:SetSize(36, 36)
    r.icon:SetPoint("LEFT", 8, 0)
    r.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    r.name = r:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    r.name:SetPoint("TOPLEFT", r.icon, "TOPRIGHT", 10, -2)
    r.name:SetPoint("RIGHT", r, "RIGHT", -10, 0)
    r.name:SetJustifyH("LEFT")
    r.sub = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    r.sub:SetPoint("BOTTOMLEFT", r.icon, "BOTTOMRIGHT", 10, 2)
    r.glow = r:CreateTexture(nil, "OVERLAY")
    r.glow:SetTexture("Interface\\Buttons\\CheckButtonHilight")
    r.glow:SetBlendMode("ADD")
    r.glow:SetAllPoints(r)
    r.glow:Hide()
    r:SetHighlightTexture("Interface\\Buttons\\UI-Listbox-Highlight2")
    r:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    -- WoW's own socket click (GlyphFrameGlyph_OnClick): what the socket holds is read now, for the spec shown now,
    -- never from the row as last drawn, so a popup names the glyph its button acts on
    r:SetScript("OnClick", function(self, button)
        local group = glyphGroup()
        local enabled, _, held = GetGlyphSocketInfo(self.id, group)
        if not (enabled and held and held > 0) then held = nil end
        if IsModifiedClick("CHATLINK") and held then
            local link = GetGlyphLink(self.id, group)
            if link then ChatEdit_InsertLink(link) end
        elseif group ~= GetActiveTalentGroup() then              -- the other specialization: look, don't touch
        elseif button == "RightButton" then
            if IsShiftKeyDown() and held then
                local dialog = StaticPopup_Show("CONFIRM_REMOVE_GLYPH", GetSpellInfo(held))
                if dialog then dialog.data = self.id end
            end
        elseif GlyphMatchesSocket(self.id) then
            if held then                                          -- inscribing over a glyph destroys it: ask first
                local dialog = StaticPopup_Show("CONFIRM_GLYPH_PLACEMENT", self.id)
                if dialog then dialog.data = self.id end
            else
                PlaceGlyphInSocket(self.id)
            end
        end
        refreshGlyphs()
    end)
    r:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetGlyph(self.id, glyphGroup())
        GameTooltip:Show()
    end)
    r:SetScript("OnLeave", function() GameTooltip:Hide() end)
    return r
end

-- names under WoW's own sockets on its round glyph page (the default)
local function refreshGlyphLabels()
    if not LABELS or not GlyphFrame or not GlyphFrame:IsVisible() then return end
    local group = glyphGroup()
    for id = 1, 6 do
        local l = LABELS[id]
        if l then
            local enabled, glyphType, spellID = GetGlyphSocketInfo(id, group)
            local major = glyphType == 1 or (glyphType == nil and (id == 1 or id == 4 or id == 6))
            if not enabled then
                l:SetText(string.format(L["Level %d"], GLYPH_LEVEL[id]))
                l:SetTextColor(0.6, 0.6, 0.6)
            elseif spellID and spellID > 0 then
                l:SetText((string.gsub(GetSpellInfo(spellID) or L["Glyph"], "^Glyph of ", "")))
                if major then l:SetTextColor(1, 0.82, 0) else l:SetTextColor(0.55, 0.78, 1) end
            else
                l:SetText(major and L["Empty major"] or L["Empty minor"])
                l:SetTextColor(0.85, 0.85, 0.85)
            end
        end
    end
end
Classic.RefreshGlyphLabels = refreshGlyphLabels

-- the list view, built the first time it is wanted. GlyphFrame spans the whole 384 x 512 talent window; the list
-- stays inside the window's art (it ends 30 px from the right and 70 from the bottom, GlyphFrame's HitRectInsets) and
-- below the portrait and the title row, so the window's close button and title stay clickable over it.
local function buildGlyphList()
    GL = CreateFrame("Frame", "AddicatUI_GlyphList", GlyphFrame)
    GL:SetPoint("TOPLEFT", GlyphFrame, "TOPLEFT", GLYPH_LIST_INSET.left, GLYPH_LIST_INSET.top)
    GL:SetPoint("BOTTOMRIGHT", GlyphFrame, "BOTTOMRIGHT", GLYPH_LIST_INSET.right, GLYPH_LIST_INSET.bottom)
    GL:SetFrameLevel(GlyphFrame:GetFrameLevel() + 20)
    GL:EnableMouse(true)                                       -- WoW's sockets underneath are not clickable through it
    GL:SetBackdrop({ bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background-Dark", edgeFile = TOOLTIP_EDGE,
        tile = true, tileSize = 32, edgeSize = 14, insets = { left = 3, right = 3, top = 3, bottom = 3 } })
    GL:SetBackdropColor(0, 0, 0, 0.96)
    GL:SetBackdropBorderColor(0.45, 0.40, 0.30, 1)
    GL.rows = {}
    local y = -8
    local function header(text, r, g, b)
        local h = GL:CreateFontString(nil, "OVERLAY", "GameFontNormal")
        h:SetPoint("TOPLEFT", 14, y)
        h:SetText(text)
        h:SetTextColor(r, g, b)
        y = y - 18
    end
    header(L["Major Glyphs"], 1, 0.82, 0)
    for _, id in ipairs(MAJOR) do
        GL.rows[#GL.rows + 1] = glyphRow(GL, id, true, y)
        y = y - GLYPH_ROW_STEP
    end
    y = y - 4
    header(L["Minor Glyphs"], 0.55, 0.78, 1)
    for _, id in ipairs(MINOR) do
        GL.rows[#GL.rows + 1] = glyphRow(GL, id, false, y)
        y = y - GLYPH_ROW_STEP
    end
    GL.hint = GL:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    GL.hint:SetPoint("BOTTOMLEFT", 10, 8)
    GL.hint:SetPoint("BOTTOMRIGHT", -10, 8)
    GL.hint:SetJustifyH("CENTER")
    GL.hint:SetText(L["Click a glyph in your bags, then the socket"] .. "   -   " .. CREDIT)
    for _, e in ipairs(GLYPH_EVENTS) do pcall(GL.RegisterEvent, GL, e) end
    pcall(GL.RegisterEvent, GL, "USE_GLYPH")
    GL:SetScript("OnEvent", refreshGlyphs)
    GL:SetScript("OnShow", refreshGlyphs)
    local acc = 0
    GL:SetScript("OnUpdate", function(self, dt)                -- the socket glow while a glyph is on the cursor
        acc = acc + dt
        if acc < 0.25 then return end
        acc = 0
        local targeting = SpellIsTargeting and SpellIsTargeting()
        if targeting or self.glowing then refreshGlyphs() end
        self.glowing = targeting
    end)
end

-- the list over the page while talents.glyph_list is on, WoW's round page with the names otherwise
function glyphView()
    if not GlyphFrame then return end
    local list = Classic.GlyphList()
    if list and not GL then buildGlyphList() end
    if GL then
        if list then GL:Show() else GL:Hide() end
    end
    if list then refreshGlyphs() else refreshGlyphLabels() end
end
Classic.RefreshGlyphs = glyphView

local function glyphPanel()
    if LABELS or not GlyphFrame then return end
    LABELS = {}
    for id = 1, 6 do
        local s = _G["GlyphFrameGlyph" .. id]
        if s then
            local l = GlyphFrame:CreateFontString(nil, "OVERLAY")
            l:SetFont(STANDARD_TEXT_FONT or "Fonts\\FRIZQT__.TTF", 11, "OUTLINE")
            l:SetPoint("TOP", s, "BOTTOM", 0, -1)
            l:SetWidth(120)
            l:SetJustifyH("CENTER")
            LABELS[id] = l
        end
    end
    local hint = GlyphFrame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    hint:SetPoint("BOTTOM", GlyphFrame, "BOTTOM", -8, 58)
    hint:SetText(L["Use a glyph from your bags, then click a socket.  Shift + right-click removes."])
    LABELS.hint = hint
    local f = CreateFrame("Frame", nil, GlyphFrame)
    for _, e in ipairs(GLYPH_EVENTS) do pcall(f.RegisterEvent, f, e) end
    f:SetScript("OnEvent", refreshGlyphLabels)
    GlyphFrame:HookScript("OnShow", glyphView)
    -- WoW redraws its sockets through GlyphFrame_Update, called by name: on show, USE_GLYPH, a level up, and on every
    -- spec or tab refresh of the talent window while the page stays shown (PlayerTalentFrame_ShowGlyphFrame)
    if GlyphFrame_Update then hooksecurefunc("GlyphFrame_Update", glyphView) end
    glyphView()
end

-- ------------------------------------------------------------------ when it runs
local function build()
    if not active then return end
    if PlayerTalentFrame then specPanel() end
    if GlyphFrame then glyphPanel() end
end

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function(self, event, name)
    if event == "PLAYER_LOGIN" then
        -- the old Bleakhold UI addon draws all of this itself while it is still installed
        active = Classic.Wanted() and not (IsAddOnLoaded and IsAddOnLoaded("BleakholdUI"))
        self:UnregisterEvent("PLAYER_LOGIN")
        if not active then return end
        for _, e in ipairs({ "ADDON_LOADED", "PLAYER_TALENT_UPDATE", "CHARACTER_POINTS_CHANGED",
            "ACTIVE_TALENT_GROUP_CHANGED" }) do
            self:RegisterEvent(e)
        end
        build()
    elseif event == "ADDON_LOADED" then
        if name == "Blizzard_TalentUI" or name == "Blizzard_GlyphUI" then build() end
    else
        refreshSpecs()                                       -- talent points or the specialization changed
    end
end)

-- /bhui talents: the window choice is core/commands.lua's; the glyph page's view is this file's
local B = addon.BleakholdCommands
if B and B.Register then
    local chooseWindow = B.handlers and B.handlers.talents
    B.Register("talents", function(arg)
        local view = arg:match("^glyphs%s*(.*)$")
        if view then
            local t = profile()
            if not t or (view ~= "list" and view ~= "round") then
                B.Say(B.usage.talents)
                return
            end
            t.glyph_list = view == "list"
            glyphView()
            B.Say(t.glyph_list and L["glyph page: the list of sockets."]
                or L["glyph page: WoW's round page with names."])
        elseif chooseWindow then
            chooseWindow(arg)
        end
    end, L["/bhui talents blizzard | addicatui | glyphs round | glyphs list - the talent window and its glyph page"])
end
