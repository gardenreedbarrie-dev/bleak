-- Bleakhold UI - the PvP window (H): PvP and Battlegrounds tabs, and the battlemaster's window, in AddicatUI's look.
-- UI by Addicated. Ported from the Bleakhold UI addon's PvP.lua.
-- WoW's own frames stay (PVPParentFrame, PVPFrame, PVPBattlegroundFrame, BattlefieldFrame): their code, events,
-- queueing and team details work as before. New: AddicatUI's metal window, marble inset and red buttons, honor and
-- arena points in the band under the title, the arena teams as cards, and the battleground list as rows on each
-- battleground's own art (WoW's PvpBg pictures) with the queue state on the row.
-- Needs the window chrome (utils/window_chrome.lua); turning the "pvpframe" module off gives WoW's windows back.
local addon = select(2, ...)
local L = addon.L
local WC = addon.WindowChrome

local PvPFrameSkin = { initialized = false, applied = false }

if addon.RegisterModule then
    addon:RegisterModule("pvpframe", PvPFrameSkin, L["PvP Window"],
        L["Retail-style PvP and battleground windows: team cards, battlegrounds on their own art"], {
            lifecyclePrefix = "PvPFrameSkin",
            loadOnce = true,
        })
end

local W, H = 338, 496
local INSET_TOP, INSET_BOTTOM = 60, 26
local ROW_H, ROW_GAP = 24, 3
local MAX_ROWS = 10
local ART = {
    [1] = "Interface\\PVPFrame\\PvpBg-AlteracValley", [2] = "Interface\\PVPFrame\\PvpBg-WarsongGulch",
    [3] = "Interface\\PVPFrame\\PvpBg-ArathiBasin", [7] = "Interface\\PVPFrame\\PvpBg-EyeOfTheStorm",
    [9] = "Interface\\PVPFrame\\PvpBg-StrandOfTheAncients", [30] = "Interface\\PVPFrame\\PvpBg-IsleOfConquest",
    [32] = "Interface\\PVPFrame\\PvpRandomBg",
}
local RANDOM_ART = "Interface\\PVPFrame\\PvpRandomBg"

local built
local inset, bgRows, bgList = nil, {}, nil

local function on() return addon:IsModuleEnabled("pvpframe") end

local function lift(frame, base)
    for _, c in ipairs({ frame:GetChildren() }) do
        if c:GetFrameLevel() <= base then c:SetFrameLevel(base + 1) end
        lift(c, c:GetFrameLevel())
    end
end
local function findText(frame, text)
    for _, r in ipairs({ frame:GetRegions() }) do
        if r:GetObjectType() == "FontString" and r:GetText() == text then return r end
    end
end
local function at(region, point, rel, relPoint, x, y)
    region:ClearAllPoints()
    region:SetPoint(point, rel, relPoint, x, y)
end
local function hideMouse(frame)
    if not frame then return end
    frame:SetAlpha(0)
    frame:EnableMouse(false)
    if frame.EnableMouseWheel then frame:EnableMouseWheel(false) end
    for _, c in ipairs({ frame:GetChildren() }) do hideMouse(c) end
end

-- the info pane (battleground text on its picture), shared by the PvP window and the battlemaster window
local function dressInfo(scrollFrame, art, host, top, bottom)
    if art then
        art:ClearAllPoints()
        art:SetPoint("TOPLEFT", host, "TOPLEFT", 3, top)
        art:SetPoint("BOTTOMRIGHT", host, "BOTTOMRIGHT", -3, bottom)
        art:SetTexCoord(0, 0.6504, 0, 0.9414)
        art:Show()
    end
    if scrollFrame then
        scrollFrame:ClearAllPoints()
        scrollFrame:SetPoint("TOPLEFT", host, "TOPLEFT", 6, top - 4)
        scrollFrame:SetPoint("BOTTOMLEFT", host, "BOTTOMLEFT", 6, bottom + 4)
        scrollFrame.defaultWidth = 290
        scrollFrame:SetWidth(290)
        WC.scrollBar(scrollFrame, host, -top - 3, -6, bottom + 1, true)
        WC.placeScrollBar(scrollFrame, host, -top - 3, -6, bottom + 1)
    end
end

-- ------------------------------------------------------------------ the PvP tab
local function buildPvPTab(p)
    local f = PVPFrame
    WC.stripTextures(f, { [PVPFramePortrait] = true, [PVPFrameBlackFilter] = true })
    local title = findText(f, PLAYER_V_PLAYER)
    if title then WC.title(f, title, p) end
    WC.portrait(p, PVPFramePortrait)

    -- honor and arena points in the band under the title
    at(PVPFrameHonor, "TOPLEFT", p, "TOPLEFT", 62, -30)
    at(PVPFrameArena, "TOPLEFT", p, "TOPLEFT", 196, -30)

    -- the kills table at the top of the inset
    at(PVPHonor, "TOPLEFT", inset, "TOPLEFT", 6, -12)
    local div = f:CreateTexture(nil, "ARTWORK")
    div:SetTexture(1, 0.82, 0, 0.22)
    div:SetHeight(1)
    div:SetPoint("TOPLEFT", inset, "TOPLEFT", 10, -84)
    div:SetPoint("TOPRIGHT", inset, "TOPRIGHT", -10, -84)
    local head = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    head:SetPoint("TOPLEFT", inset, "TOPLEFT", 12, -94)
    head:SetText(ARENA_TEAMS or "Arena Teams")
    f.bhArenaHead = head
    at(PVPFrameToggleButton, "TOPRIGHT", inset, "TOPRIGHT", -10, -93)

    -- the three team cards
    for i = 1, 3 do
        local card, std = _G["PVPTeam" .. i], _G["PVPTeam" .. i .. "Standard"]
        at(card, "TOPLEFT", inset, "TOPLEFT", 40, -112 - (i - 1) * 98)
        at(std, "LEFT", card, "LEFT", -33, 0)
        local hl = _G["PVPTeam" .. i .. "Highlight"]
        if hl and hl.SetBackdropBorderColor then hl:SetBackdropBorderColor(1, 0.82, 0) end
    end
    -- off-season cover over the arena part
    at(PVPFrameBlackFilter, "TOPLEFT", inset, "TOPLEFT", 3, -110)
    PVPFrameBlackFilter:SetPoint("BOTTOMRIGHT", inset, "BOTTOMRIGHT", -3, 3)
    at(PVPFrameOffSeason, "TOPLEFT", inset, "TOPLEFT", 3, -110)
    PVPFrameOffSeason:SetPoint("BOTTOMRIGHT", inset, "BOTTOMRIGHT", -3, 3)

    -- the team roster pops out to the right of the window
    at(PVPTeamDetails, "TOPLEFT", p, "TOPRIGHT", 4, -24)
end

-- ------------------------------------------------------------------ the Battlegrounds tab: rows on each BG's art
local function statusOf(name)
    for i = 1, (MAX_BATTLEFIELD_QUEUES or 2) do
        local status, mapName = GetBattlefieldStatus(i)
        if status and status ~= "none" and mapName == name then return status end
    end
end

local function refreshBG()
    if not built or not bgList or not PVPBattlegroundFrame:IsVisible() then return end
    local n, shown = GetNumBattlegroundTypes() or 0, 0
    local selected = PVPBattlegroundFrame.selectedBG
    local faction = UnitFactionGroup("player") or "Alliance"
    for i = 1, n do
        local name, canEnter, isHoliday, isRandom, id = GetBattlegroundInfo(i)
        if name and canEnter and shown < MAX_ROWS then
            shown = shown + 1
            local r = bgRows[shown]
            r.bg = i
            r.art:SetTexture(ART[id] or (isRandom and RANDOM_ART) or RANDOM_ART)
            r.art:SetTexCoord(0.02, 0.63, 0.36, 0.36 + 0.61 * ROW_H / 333)
            r.name:SetText(name)
            r.tag:SetText(isHoliday and ("|cff40ff40" .. (BATTLEGROUND_HOLIDAY or "Holiday") .. "|r") or "")
            local st = statusOf(name)
            if st == "queued" then
                r.status:SetTexture("Interface\\PVPFrame\\PVP-Currency-" .. faction)
                r.status:SetTexCoord(0, 1, 0, 1)
                r.status:Show()
                r.statusTip = BATTLEFIELD_QUEUE_STATUS
            elseif st == "confirm" then
                r.status:SetTexture("Interface\\CharacterFrame\\UI-StateIcon")
                r.status:SetTexCoord(0.45, 0.95, 0.0, 0.5)
                r.status:Show()
                r.statusTip = BATTLEFIELD_CONFIRM_STATUS
            else
                r.status:Hide()
                r.statusTip = nil
            end
            if i == selected then
                r.sel:Show()
                r.name:SetTextColor(1, 1, 1)
                r.art:SetAlpha(0.95)
            else
                r.sel:Hide()
                r.name:SetTextColor(1, 0.82, 0)
                r.art:SetAlpha(0.55)
            end
            r:Show()
        end
    end
    for i = shown + 1, MAX_ROWS do bgRows[i]:Hide() end
    bgList.count = shown
    -- the info pane starts under the last row
    local top = -(8 + shown * (ROW_H + ROW_GAP) + 4)
    dressInfo(PVPBattlegroundFrameInfoScrollFrame, PVPBattlegroundFrameBGTex, inset, top, 3)
    WC.topLayers(PVPParentFrame)
end
PvPFrameSkin.RefreshBattlegrounds = refreshBG

local function selectBG(index)
    if not index then return end
    if PVPBattlegroundFrame.selectedBG ~= index then
        PVPBattlegroundFrame.selectedBG = index
        PVPBattleground_ResetInfo()
        PVPBattleground_UpdateJoinButton()
    end
    PlaySound("igMainMenuOptionCheckBoxOn")
    refreshBG()
end

local function newBGRow(i, parent)
    local r = CreateFrame("Button", nil, parent)
    r:SetHeight(ROW_H)
    r:SetPoint("TOPLEFT", inset, "TOPLEFT", 6, -8 - (i - 1) * (ROW_H + ROW_GAP))
    r:SetPoint("TOPRIGHT", inset, "TOPRIGHT", -6, -8 - (i - 1) * (ROW_H + ROW_GAP))
    r.art = r:CreateTexture(nil, "BACKGROUND")
    r.art:SetAllPoints(r)
    r.shade = r:CreateTexture(nil, "BORDER")
    r.shade:SetAllPoints(r)
    r.shade:SetTexture(0, 0, 0, 1)
    r.shade:SetGradientAlpha("HORIZONTAL", 0, 0, 0, 0.80, 0, 0, 0, 0.15)
    r.edge = r:CreateTexture(nil, "BORDER", nil, 1)
    r.edge:SetTexture(0.55, 0.46, 0.26, 0.9)
    r.edge:SetHeight(1)
    r.edge:SetPoint("BOTTOMLEFT", r, "BOTTOMLEFT")
    r.edge:SetPoint("BOTTOMRIGHT", r, "BOTTOMRIGHT")
    r.sel = r:CreateTexture(nil, "ARTWORK")
    if not WC.atlas(r.sel, "questlog-quest-glow-yellow") then r.sel:SetTexture(1, 0.82, 0, 0.18) end
    r.sel:SetAllPoints(r)
    r.sel:SetBlendMode("ADD")
    r.sel:Hide()
    local hl = r:CreateTexture(nil, "HIGHLIGHT")
    hl:SetTexture("Interface\\Buttons\\UI-Listbox-Highlight2")
    hl:SetBlendMode("ADD")
    hl:SetVertexColor(1, 0.82, 0, 0.6)
    hl:SetAllPoints(r)
    r.name = r:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    r.name:SetPoint("LEFT", r, "LEFT", 10, 0)
    r.name:SetJustifyH("LEFT")
    r.tag = r:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    r.tag:SetPoint("LEFT", r.name, "RIGHT", 6, 0)
    r.tag:SetJustifyH("LEFT")
    r.status = r:CreateTexture(nil, "OVERLAY")
    r.status:SetSize(22, 22)
    r.status:SetPoint("RIGHT", r, "RIGHT", -4, 0)
    r.status:Hide()
    r:SetScript("OnClick", function(self) selectBG(self.bg) end)
    r:SetScript("OnEnter", function(self)
        if self.statusTip then
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetText(self.statusTip, nil, nil, nil, nil, 1)
            GameTooltip:Show()
        end
    end)
    r:SetScript("OnLeave", function() GameTooltip:Hide() end)
    r:Hide()
    return r
end

local function buildBGTab(p)
    local f = PVPBattlegroundFrame
    WC.stripTextures(f, { [PVPBattlegroundFramePortrait] = true, [PVPBattlegroundFrameBGTex] = true })
    f:ClearAllPoints()
    f:SetAllPoints(p)
    f:SetHitRectInsets(0, 0, 0, 0)
    WC.title(f, PVPBattlegroundFrameFrameLabel, p)
    WC.portrait(p, PVPBattlegroundFramePortrait)
    PVPBattlegroundFrameNameHeader:Hide()
    at(WintergraspTimer, "TOPRIGHT", p, "TOPRIGHT", -10, -26)
    -- WoW's own list stays for its code, invisible
    for i = 1, (NUM_DISPLAYED_BATTLEGROUNDS or 5) do hideMouse(_G["BattlegroundType" .. i]) end
    hideMouse(PVPBattlegroundFrameTypeScrollFrame)
    bgList = CreateFrame("Frame", nil, f)
    bgList:SetAllPoints(inset)
    for i = 1, MAX_ROWS do bgRows[i] = newBGRow(i, bgList) end
    -- buttons
    for _, b in ipairs({ PVPBattlegroundFrameGroupJoinButton, PVPBattlegroundFrameJoinButton,
        PVPBattlegroundFrameCancelButton }) do
        WC.redButton(b)
        b:SetHeight(22)
    end
    at(PVPBattlegroundFrameGroupJoinButton, "BOTTOMLEFT", p, "BOTTOMLEFT", 4, 2)
    PVPBattlegroundFrameGroupJoinButton:SetWidth(124)
    at(PVPBattlegroundFrameJoinButton, "LEFT", PVPBattlegroundFrameGroupJoinButton, "RIGHT", 2, 0)
    PVPBattlegroundFrameJoinButton:SetWidth(110)
    at(PVPBattlegroundFrameCancelButton, "BOTTOMRIGHT", p, "BOTTOMRIGHT", -8, 2)
    PVPBattlegroundFrameCancelButton:SetWidth(86)
    dressInfo(PVPBattlegroundFrameInfoScrollFrame, PVPBattlegroundFrameBGTex, inset, -200, 3)
    hooksecurefunc("PVPBattleground_UpdateBattlegrounds", refreshBG)
    hooksecurefunc("PVPBattleground_UpdateQueueStatus", refreshBG)
    hooksecurefunc("PVPBattleground_UpdateInfo", refreshBG)
    f:HookScript("OnShow", refreshBG)
end

-- ------------------------------------------------------------------ the tabs under the window
local function placeTabs(p)
    local t1, t2 = PVPParentFrameTab1, PVPParentFrameTab2
    local CP = addon.CharacterPanel
    if CP and CP.ReskinTab then
        for _, t in ipairs({ t1, t2 }) do
            pcall(CP.ReskinTab, t)
            -- WoW resizes a tab on every show (PanelTemplates_TabResize); AddicatUI then re-applies ours through this
            t._duiRelayout = function() pcall(CP.ReskinTab, t) end
        end
    end
    at(t1, "TOPLEFT", p, "BOTTOMLEFT", 11, 2)
    at(t2, "TOPLEFT", t1, "TOPRIGHT", 1, 0)
end

-- ------------------------------------------------------------------ the battlemaster's window
local function buildBattlemaster()
    local f = BattlefieldFrame
    if not f then return end
    local art
    for _, r in ipairs({ f:GetRegions() }) do
        if r:GetObjectType() == "Texture" and r:GetTexture()
            and string.find(string.lower(r:GetTexture()), "pvprandombg", 1, true) then
            art = r
        end
    end
    WC.stripTextures(f, { [BattlefieldFramePortrait] = true, [art or BattlefieldFramePortrait] = true })
    WC.dressWindow(f, W, H)
    f:SetAttribute("UIPanelLayout-xoffset", 6)
    WC.portrait(f, BattlefieldFramePortrait)
    WC.title(f, BattlefieldFrameFrameLabel)
    WC.closeButton(BattlefieldFrameCloseButton, f)
    if BattlefieldFrameNameHeader then BattlefieldFrameNameHeader:Hide() end
    local ins = WC.inset(f)
    ins:SetPoint("TOPLEFT", f, "TOPLEFT", 4, -INSET_TOP)
    ins:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -6, INSET_BOTTOM)
    f.bhInset = ins
    -- the instance list on top, the battleground's text on its picture below
    local rowH = BattlefieldZone1:GetHeight() > 0 and BattlefieldZone1:GetHeight() or 16
    at(BattlefieldZone1, "TOPLEFT", ins, "TOPLEFT", 8, -8)
    for i = 1, 5 do
        local b = _G["BattlefieldZone" .. i]
        if b then b:SetWidth(290) end
    end
    at(BattlefieldListScrollFrame, "TOPLEFT", BattlefieldZone1, "TOPLEFT", 0, 0)
    BattlefieldListScrollFrame:SetPoint("BOTTOMRIGHT", BattlefieldZone5, "BOTTOMRIGHT", 0, -4)
    WC.stripTextures(BattlefieldListScrollFrame)
    WC.scrollBar(BattlefieldListScrollFrame, ins, 2, -6, 410 - 8 - 5 * rowH - 18, true)
    local div = ins:CreateTexture(nil, "ARTWORK")
    div:SetTexture(1, 0.82, 0, 0.22)
    div:SetHeight(1)
    div:SetPoint("TOPLEFT", ins, "TOPLEFT", 8, -(16 + 5 * rowH))
    div:SetPoint("TOPRIGHT", ins, "TOPRIGHT", -8, -(16 + 5 * rowH))
    if art then
        art:SetParent(ins)
        art:SetDrawLayer("BORDER", -7)
    end
    dressInfo(BattlefieldFrameInfoScrollFrame, art, ins, -(22 + 5 * rowH), 3)
    for _, b in ipairs({ BattlefieldFrameGroupJoinButton, BattlefieldFrameJoinButton, BattlefieldFrameCancelButton }) do
        WC.redButton(b)
        b:SetHeight(22)
    end
    at(BattlefieldFrameGroupJoinButton, "BOTTOMLEFT", f, "BOTTOMLEFT", 4, 2)
    BattlefieldFrameGroupJoinButton:SetWidth(124)
    at(BattlefieldFrameJoinButton, "LEFT", BattlefieldFrameGroupJoinButton, "RIGHT", 2, 0)
    BattlefieldFrameJoinButton:SetWidth(110)
    at(BattlefieldFrameCancelButton, "BOTTOMRIGHT", f, "BOTTOMRIGHT", -8, 2)
    BattlefieldFrameCancelButton:SetWidth(86)
    local base = f:GetFrameLevel()
    ins:SetFrameLevel(base + 1)
    for _, c in ipairs({ f:GetChildren() }) do
        if c ~= ins and c ~= f.bhBorder and c:GetFrameLevel() <= base + 1 then
            c:SetFrameLevel(base + 3)
            lift(c, base + 3)
        end
    end
    WC.topLayers(f)
    f:HookScript("OnShow", function() WC.topLayers(f) end)
    -- the battleground's own picture when its name is known from the PvP list (else WoW's random-battleground art)
    if art and BattlefieldFrame_Update then
        hooksecurefunc("BattlefieldFrame_Update", function()
            local mapName = GetBattlefieldInfo()
            local file = RANDOM_ART
            for i = 1, (GetNumBattlegroundTypes() or 0) do
                local name, _, _, _, id = GetBattlegroundInfo(i)
                if name and name == mapName and ART[id] then file = ART[id] end
            end
            art:SetTexture(file)
            art:SetTexCoord(0, 0.6504, 0, 0.9414)
        end)
    end
end

-- ------------------------------------------------------------------ build
local function build()
    if built or not on() or not (WC and WC.chrome()) then return end
    if not (PVPParentFrame and PVPFrame and PVPBattlegroundFrame and PVPTeam1 and PVPHonor
        and PVPBattleground_ResetInfo) then
        return
    end
    built = true
    PvPFrameSkin.initialized = true
    local p = PVPParentFrame
    WC.dressWindow(p, W, H)
    p:SetAttribute("UIPanelLayout-xoffset", 6)
    WC.closeButton(PVPParentFrameCloseButton, p)
    inset = WC.inset(p)
    inset:SetPoint("TOPLEFT", p, "TOPLEFT", 4, -INSET_TOP)
    inset:SetPoint("BOTTOMRIGHT", p, "BOTTOMRIGHT", -6, INSET_BOTTOM)
    buildPvPTab(p)
    buildBGTab(p)
    placeTabs(p)
    -- levels: the inset under both tabs' content, the metal frame over everything
    local base = p:GetFrameLevel()
    inset:SetFrameLevel(base + 1)
    for _, c in ipairs({ PVPFrame, PVPBattlegroundFrame }) do
        c:SetFrameLevel(base + 3)
        lift(c, base + 3)
    end
    WC.topLayers(p)
    p:HookScript("OnShow", function() WC.topLayers(p) end)
    local ok, err = pcall(buildBattlemaster)
    if not ok then addon:Print(L["Battlemaster window skin skipped:"] .. " " .. tostring(err)) end
end

function addon.ApplyPvPFrameSkinSystem()
    if built or not on() then return end
    PvPFrameSkin.applied = true
    local ok, err = pcall(build)
    if not ok then
        built = true
        addon:Print(L["PvP window skin skipped:"] .. " " .. tostring(err))
    end
end

function addon.RestorePvPFrameSkinSystem()
    PvPFrameSkin.applied = false
end

local loginWatcher = CreateFrame("Frame")
loginWatcher:RegisterEvent("PLAYER_LOGIN")
loginWatcher:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    addon.ApplyPvPFrameSkinSystem()
end)
