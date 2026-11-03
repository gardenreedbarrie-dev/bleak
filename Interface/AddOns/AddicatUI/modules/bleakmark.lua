-- Bleakhold UI - the BLEAKHOLD mark under the minimap and the "made by Addicated" line under the game menu (Esc).
-- UI by Addicated. Ported from the Bleakhold UI addon (BleakholdUI.lua).
-- The mark shows while profile.minimap.bleakhold_mark is on (Options > Minimap, /bhui mark). It takes a band right
-- under the map; minimap.lua puts the durability figure below that band (Band), and the mark itself drops below a
-- capture bar while one shows there (SetCaptureBar).
local addon = select(2, ...)
local L = addon.L
local WC = addon.WindowChrome

local BleakMark = {}
addon.BleakMark = BleakMark

local GOLD = WC and WC.GOLD or { 0.90, 0.80, 0.50 }
local CREDIT = WC and WC.CREDIT or "Bleakhold UI  -  made by Addicated"
local MARK_W, MARK_H, MARK_Y = 110, 14, -6
-- minimap.lua centres a capture bar 20 below the map and moves the durability figure 30 down for it
local CAPTURE_DROP = 30
-- what the mark keeps clear under the map, in Minimap units: its height, its gap and a little air
local BAND = MARK_H - MARK_Y + 4

local mark, menuCredit
local underCaptureBar = false

local function wanted()
    local cfg = addon.db and addon.db.profile and addon.db.profile.minimap
    return not (cfg and cfg.bleakhold_mark == false)
end

-- the band (Minimap units) the shown mark takes under the map; 0 when it is off
function BleakMark.Band()
    if mark and mark:IsShown() then return BAND end
    return 0
end

local function place()
    if not mark then return end
    mark:ClearAllPoints()
    mark:SetPoint("TOP", Minimap, "BOTTOM", 0, MARK_Y - (underCaptureBar and CAPTURE_DROP or 0))
end

function BleakMark.SetCaptureBar(shown)
    underCaptureBar = shown and true or false
    place()
end

local function makeMark()
    if mark or not Minimap then return end
    mark = CreateFrame("Frame", "AddicatUIBleakholdMark", Minimap)
    mark:SetSize(MARK_W, MARK_H)
    mark:SetFrameLevel(Minimap:GetFrameLevel() + 5)
    mark.text = mark:CreateFontString(nil, "OVERLAY")
    mark.text:SetFont("Fonts\\MORPHEUS.ttf", 12, "OUTLINE")
    mark.text:SetTextColor(GOLD[1], GOLD[2], GOLD[3])
    mark.text:SetPoint("CENTER")
    mark.text:SetText("BLEAKHOLD")
    mark:EnableMouse(true)
    mark:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
        GameTooltip:AddLine("Bleakhold", GOLD[1], GOLD[2], GOLD[3])
        GameTooltip:AddLine("UI by Addicated", 1, 1, 1)
        GameTooltip:AddLine(L["/bhui for the interface options"], 0.6, 0.6, 0.6)
        GameTooltip:Show()
    end)
    mark:SetScript("OnLeave", function() GameTooltip:Hide() end)
    place()
end

-- show or hide the mark as the option says, and move the durability figure with it
function BleakMark.Refresh()
    makeMark()
    if not mark then return end
    if wanted() then mark:Show() else mark:Hide() end
    place()
    local mm = addon.MinimapModule
    if mm and mm.ApplyDurabilityPosition then mm.ApplyDurabilityPosition() end
end

-- the credit hangs under the game menu's bottom edge, outside its border, so the buttons gamemenu.lua and the addon
-- manager add (each growing the frame) and the theme's dressing never cover it
local function makeCredit()
    local menu = _G.GameMenuFrame
    if menuCredit or not menu then return end
    menuCredit = menu:CreateFontString("AddicatUIBleakholdMenuCredit", "OVERLAY", "GameFontDisableSmall")
    menuCredit:SetPoint("BOTTOM", menu, "BOTTOM", 0, -16)
    menuCredit:SetText(CREDIT)
    menuCredit:SetTextColor(GOLD[1], GOLD[2], GOLD[3], 0.85)
end

-- a hand-installed copy of the old Bleakhold UI addon draws the same two; keep one of each
local function hideOldCopies()
    for _, name in ipairs({ "BleakholdUIMark", "BleakholdUIMenuCredit" }) do
        local old = _G[name]
        if old and old.Hide then old:Hide() end
    end
end

local loginWatcher = CreateFrame("Frame")
loginWatcher:RegisterEvent("PLAYER_LOGIN")
loginWatcher:RegisterEvent("PLAYER_ENTERING_WORLD")
loginWatcher:SetScript("OnEvent", function(self, event)
    if event == "PLAYER_LOGIN" then
        BleakMark.Refresh()
        makeCredit()
    else
        self:UnregisterEvent("PLAYER_ENTERING_WORLD")
    end
    hideOldCopies()
end)
