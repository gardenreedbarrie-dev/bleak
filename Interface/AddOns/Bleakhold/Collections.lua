-- Bleakhold: Collections window. Tabs Transmog (built by Transmog.lua) / Looks of Later Ages / Legacy Sets /
-- Mounts / Pets / Animations (built by Animations.lua).
-- Legacy Sets: eras rail, set pieces grid (hover = item tooltip, click = try on, shift-click = link),
-- where the set drops, and a DressUpModel preview. Collected state and the outfit unlock come from
-- the server (SET); Save outfit is an intent (OUTFIT) the server checks.
-- Without AddicatUI or DragonUI, defines the global ToggleCollectionsJournal (if nothing else did) for addons
-- that open a server's collections window through it.
local ADDON, ns = ...
local U, UI, Comm, Data = ns.U, ns.UI, ns.Comm, ns.Data
local C = UI.C
local S = ns.S

local floor, ceil, max, min = math.floor, math.ceil, math.max, math.min

local CO = {}
ns.Collections = CO

CO.W, CO.H = 940, 600
CO.tab = "legacy"
CO.tier = 1
CO.classIndex = 1
CO.search = ""

local win = UI.Window("BleakholdCollectionsFrame", CO.W, CO.H, "Collections", "layers")
local CW, CH = UI.ContentSize(CO.W, CO.H)
CO.frame = win

------------------------------------------------------------------------------------------------------
-- Header search: InputBoxTemplate's look in the title bar, left of the close button
------------------------------------------------------------------------------------------------------
local search = CreateFrame("EditBox", "BleakholdCollectionsSearch", win.header)
search:SetSize(220, 20)
search:SetPoint("RIGHT", win.bar, "RIGHT", -34, 0)
search:SetFont(UI.FONT_BODY, 12, "")
search:SetTextColor(UI.Rgb(C.text))
search:SetAutoFocus(false)
search:SetMaxLetters(40)
search:SetTextInsets(16, 6, 0, 0)
search.border = UI.InputBorder(search)
-- the magnifier: the minimap tracking button's own (Minimap\Tracking\None), as 3.3.5a has no search icon
search.icon = search:CreateTexture(nil, "OVERLAY")
search.icon:SetTexture("Interface\\Minimap\\Tracking\\None")
search.icon:SetSize(14, 14)
search.icon:SetPoint("LEFT", search, "LEFT", -1, 0)
search.hint = UI.Text(search, 11, C.mute)
search.hint:SetPoint("LEFT", search, "LEFT", 16, 0)
search.hint:SetText("Search sets, pieces, dungeons")
search:SetScript("OnEscapePressed", function(self)
    self:ClearFocus()
end)
search:SetScript("OnEnterPressed", function(self)
    self:ClearFocus()
end)
search:SetScript("OnTextChanged", function(self)
    CO.search = string.lower(self:GetText() or "")
    if CO.search == "" then
        search.hint:Show()
    else
        search.hint:Hide()
    end
    CO.Refresh()
end)
CO.searchBox = search

------------------------------------------------------------------------------------------------------
-- Tabs: the options frame's top tabs standing on the body, a tooltip panel (InterfaceOptionsFrame's look)
------------------------------------------------------------------------------------------------------
CO.STRIP_H = 24
local body = UI.Box(win.content, CW, CH - CO.STRIP_H, C.panel, C.border, nil, "panel")
body:SetPoint("TOPLEFT", win.content, "TOPLEFT", 0, -CO.STRIP_H)
body:SetPoint("BOTTOMRIGHT", win.content, "BOTTOMRIGHT", 0, 0)
CO.body = body
local BW, BH = CW, CH - CO.STRIP_H
CO.BW, CO.BH = BW, BH

-- above the body, so the open tab's legs cover the panel's top edge
local tabBar = CreateFrame("Frame", nil, win.content)
tabBar:SetPoint("TOPLEFT", win.content, "TOPLEFT", 0, 0)
tabBar:SetPoint("BOTTOMRIGHT", body, "TOPRIGHT", 0, 0)
tabBar:SetFrameLevel(body:GetFrameLevel() + 5)
local tabDefs = {
    { key = "transmog", label = "Transmog" },
    { key = "later", label = "Looks of Later Ages" },
    { key = "legacy", label = "Legacy Sets" },
    { key = "mounts", label = "Mounts" },
    { key = "pets", label = "Pets" },
    { key = "animations", label = "Animations" },
}
CO.tabs = {}
for i, d in ipairs(tabDefs) do
    local b = UI.Button(tabBar, 100, 24, d.label, "strip")
    b.key = d.key
    b:SetScript("OnClick", function()
        if PlaySound then
            PlaySound("igCharacterInfoTab")
        end
        CO.ShowTab(d.key)
    end)
    CO.tabs[i] = b
end

-- Each tab is as wide as its label (PanelTemplates_TabResize: the label and 16 px each side); the tabs overlap by
-- their art's see-through flanks, from 8 px in on the panel's top edge.
CO.TAB_OVERLAP, CO.TAB_MIN, CO.TAB_PAD = 8, 64, 32
function CO.LayoutTabs()
    local x = 8
    for _, b in ipairs(CO.tabs) do
        local w = max(CO.TAB_MIN, ceil((b.label:GetStringWidth() or 0) + CO.TAB_PAD))
        b:SetWidth(w)
        b:ClearAllPoints()
        b:SetPoint("BOTTOMLEFT", body, "TOPLEFT", x, -2)
        x = x + w - CO.TAB_OVERLAP
    end
    CO.tabsRight = x + CO.TAB_OVERLAP
end
CO.LayoutTabs()

------------------------------------------------------------------------------------------------------
-- Legacy Sets: the eras on the left, the set's pieces in the middle, the model on the right
------------------------------------------------------------------------------------------------------
local legacy = CreateFrame("Frame", nil, body)
legacy:SetAllPoints(body)
CO.legacy = legacy

local PAD = 14
local RAIL = 210
local ERA_H, ERA_STEP = 60, 66
local rail = CreateFrame("Frame", nil, legacy)
rail:SetPoint("TOPLEFT", legacy, "TOPLEFT", PAD, -12)
rail:SetSize(RAIL, BH - 24)
rail.label = UI.Heading(rail, "Eras")
rail.label:SetPoint("TOPLEFT", rail, "TOPLEFT", 2, 0)
rail.buttons = {}
for i = 1, 7 do
    local b = CreateFrame("Button", nil, rail)
    b:SetSize(RAIL, ERA_H)
    b:SetPoint("TOPLEFT", rail, "TOPLEFT", 0, -24 - (i - 1) * ERA_STEP)
    -- the old window's row: a dark fill with a 1 px edge; the chosen era in its nav row blue (UI.Select)
    UI.Backdrop(b, C.card, C.border, nil, "edge")
    b.glow = b:CreateTexture(nil, "HIGHLIGHT")
    b.glow:SetTexture(UI.STOCK.rowHighlight)
    b.glow:SetBlendMode("ADD")
    b.glow:SetPoint("TOPLEFT", b, "TOPLEFT", 1, -1)
    b.glow:SetPoint("BOTTOMRIGHT", b, "BOTTOMRIGHT", -1, 1)
    b.glow:SetAlpha(0.35)
    b.tier = UI.Text(b, 13, C.text)
    b.tier:SetPoint("TOPLEFT", b, "TOPLEFT", 10, -7)
    b.raids = UI.Text(b, 11, C.dim)
    b.raids:SetPoint("TOPLEFT", b.tier, "BOTTOMLEFT", 0, -2)
    UI.OneLine(b.raids, RAIL - 20)
    -- the achievement progress bar with the count in it ("3 / 8")
    b.bar = UI.Bar(b, RAIL - 30, 14)
    b.bar:SetPoint("BOTTOMLEFT", b, "BOTTOMLEFT", 15, 8)
    b.have = b.bar.text
    b:RegisterForClicks("LeftButtonUp")
    b:SetScript("OnClick", function(self)
        CO.SelectTier(self.tierId)
    end)
    rail.buttons[i] = b
end
CO.rail = rail

-- a faint rule between the eras and the set, as the old window's nav rows end
local rule = legacy:CreateTexture(nil, "ARTWORK")
rule:SetTexture(1, 1, 1, 0.08)
rule:SetWidth(1)
rule:SetPoint("TOPLEFT", legacy, "TOPLEFT", PAD + RAIL + 12, -12)
rule:SetPoint("BOTTOMLEFT", legacy, "BOTTOMLEFT", PAD + RAIL + 12, 12)

local mainX = PAD + RAIL + 26
local MODEL_W = 220
local MAIN_W = BW - mainX - MODEL_W - PAD - 22
local mainF = CreateFrame("Frame", nil, legacy)
mainF:SetPoint("TOPLEFT", legacy, "TOPLEFT", mainX, -14)
mainF:SetSize(MAIN_W, BH - 28)

mainF.sub = UI.Text(mainF, 11, C.dim)
mainF.sub:SetPoint("TOPLEFT", mainF, "TOPLEFT", 0, 0)
mainF.name = UI.Text(mainF, 22, C.gold, "title")
mainF.name:SetPoint("TOPLEFT", mainF.sub, "BOTTOMLEFT", 0, -4)
UI.OneLine(mainF.name, MAIN_W)

-- Class selector: four class circles as ring portraits (the chosen one in colour) and a dropdown of the others.
mainF.classes = {}
for i = 1, 4 do
    local b = CreateFrame("Button", nil, mainF)
    b:SetSize(36, 36)
    b:SetPoint("TOPLEFT", mainF, "TOPLEFT", (i - 1) * 44, -50)
    b.portrait = UI.ClassPortrait(b, 36)
    b.portrait:SetPoint("TOPLEFT", b, "TOPLEFT", 0, 0)
    -- the minimap button's light round the ring under the cursor
    b.glow = b:CreateTexture(nil, "HIGHLIGHT")
    b.glow:SetTexture(UI.STOCK.arrowHighlight)
    b.glow:SetBlendMode("ADD")
    b.glow:SetSize(44, 44)
    b.glow:SetPoint("CENTER", b, "CENTER", 1, 0)
    b:RegisterForClicks("LeftButtonUp")
    mainF.classes[i] = b
end
mainF.more = UI.Dropdown(mainF, 120, function(value)
    CO.SelectClass(value)
end)
mainF.more:SetPoint("TOPLEFT", mainF, "TOPLEFT", 4 * 44 + 6, -55)

-- The pieces: two columns of item slots (ItemButtonTemplate's art) with the name in the item's quality colour,
-- as quest rewards list items.
CO.PIECE_W = floor((MAIN_W - 12) / 2)
local PIECE_H, PIECE_STEP = 40, 46
mainF.pieces = {}
for i = 1, 8 do
    local p = CreateFrame("Button", nil, mainF)
    p:SetSize(CO.PIECE_W, PIECE_H)
    p:SetPoint("TOPLEFT", mainF, "TOPLEFT", ((i - 1) % 2) * (CO.PIECE_W + 12), -100 - floor((i - 1) / 2) * PIECE_STEP)
    UI.SlotArt(p, 36)
    p.icon:SetPoint("LEFT", p, "LEFT", 2, 0)
    p.name = UI.Text(p, 12, C.epic)
    p.name:SetPoint("TOPLEFT", p.icon, "TOPRIGHT", 10, -3)
    UI.OneLine(p.name, CO.PIECE_W - 52)
    p.state = UI.Text(p, 11, C.mute)
    p.state:SetPoint("TOPLEFT", p.name, "BOTTOMLEFT", 0, -3)
    p:RegisterForClicks("LeftButtonUp")
    mainF.pieces[i] = p
end
mainF.note = UI.Text(mainF, 11, C.dim)
mainF.note:SetPoint("TOPLEFT", mainF, "TOPLEFT", 0, -100 - 4 * PIECE_STEP - 2)
UI.OneLine(mainF.note, MAIN_W)

-- Where it drops, and the era's week at level 80: gold headings with the text under them (the old page anatomy).
local drops = CreateFrame("Frame", nil, mainF)
drops:SetSize(MAIN_W, 64)
drops:SetPoint("TOPLEFT", mainF, "TOPLEFT", 0, -308)
drops.label = UI.Heading(drops)
drops.label:SetPoint("TOPLEFT", drops, "TOPLEFT", 0, 0)
drops.text = UI.Para(drops, 12, C.text, MAIN_W)
drops.text:SetPoint("TOPLEFT", drops.label, "BOTTOMLEFT", 0, -6)
mainF.drops = drops
local at80 = CreateFrame("Frame", nil, mainF)
at80:SetSize(MAIN_W, 60)
at80:SetPoint("TOPLEFT", drops, "BOTTOMLEFT", 0, -8)
at80.label = UI.Heading(at80, "At Level 80")
at80.label:SetPoint("TOPLEFT", at80, "TOPLEFT", 0, 0)
at80.echo = UI.Text(at80, 12, C.gold, "body", "RIGHT")
at80.echo:SetPoint("TOPRIGHT", at80, "TOPRIGHT", 0, -1)
UI.OneLine(at80.echo, 200)
at80.text = UI.Para(at80, 12, C.text, MAIN_W)
at80.text:SetPoint("TOPLEFT", at80.label, "BOTTOMLEFT", 0, -6)
mainF.at80 = at80
CO.main = mainF

-- Model column
local modelCol = CreateFrame("Frame", nil, legacy)
modelCol:SetSize(MODEL_W, BH - 28)
modelCol:SetPoint("TOPRIGHT", legacy, "TOPRIGHT", -PAD - 2, -14)
local modelBox = UI.Box(modelCol, MODEL_W, BH - 150, C.card, C.border, nil, "edge")
modelBox:SetPoint("TOP", modelCol, "TOP", 0, 0)
local model = CreateFrame("DressUpModel", "BleakholdCollectionsModel", modelBox)
model:SetPoint("TOPLEFT", modelBox, "TOPLEFT", 1, -1)
model:SetPoint("BOTTOMRIGHT", modelBox, "BOTTOMRIGHT", -1, 1)
model:EnableMouse(true)
model:EnableMouseWheel(true)
CO.model = model
modelCol.count = UI.Text(modelCol, 13, C.text)
modelCol.count:SetPoint("TOPLEFT", modelBox, "BOTTOMLEFT", 0, -10)
-- the set's pieces as the achievement frame's progress bar, "3 / 8" inside
modelCol.bar = UI.Bar(modelCol, MODEL_W - 10, 14)
modelCol.bar:SetPoint("TOPLEFT", modelCol.count, "BOTTOMLEFT", 5, -12)
modelCol.hint = UI.Text(modelCol, 11, C.dim)
modelCol.hint:SetPoint("TOPLEFT", modelCol.bar, "BOTTOMLEFT", -5, -10)
modelCol.preview = UI.Button(modelCol, (MODEL_W - 8) / 2, 24, "Preview", "gold")
modelCol.preview:SetPoint("BOTTOMLEFT", modelCol, "BOTTOMLEFT", 0, 0)
modelCol.save = UI.Button(modelCol, (MODEL_W - 8) / 2, 24, "Save Outfit", "dark")
modelCol.save:SetPoint("BOTTOMRIGHT", modelCol, "BOTTOMRIGHT", 0, 0)
CO.modelCol = modelCol

-- Model controls: drag to turn, wheel to zoom (3.3.5a Model API: SetFacing/SetPosition).
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
model:SetScript("OnMouseWheel", function(self, delta)
    local x, y, z = self:GetPosition()
    self:SetPosition(U.Clamp((x or 0) + (delta or 0) * 0.3, -1, 3), y or 0, z or 0)
end)

------------------------------------------------------------------------------------------------------
-- Other tabs
------------------------------------------------------------------------------------------------------
-- Looks of Later Ages: the old page anatomy (gold title, white description, a gold stat label and its value, the
-- page's picture on the right fading into the dark, as Activities.lua draws it).
local summary = CreateFrame("Frame", nil, body)
summary:SetAllPoints(body)
-- the picture 5 px inside the panel's edge, in the old crop's shape (Activities' A.ART_W x A.ART_H, fitted to this
-- shorter body): the Journal's Utgarde Pinnacle, else the stock LFG one (JournalArt.lua), else none (dark panel)
CO.ART_H = BH - 10
CO.ART_W = floor(CO.ART_H * 390 / 423)
CO.ART_KEY = "UTGARDEPINNACLE"
summary.art = summary:CreateTexture(nil, "BACKGROUND")
summary.art:SetPoint("TOPRIGHT", summary, "TOPRIGHT", -5, -5)
summary.art:SetSize(CO.ART_W, CO.ART_H)
summary.art:SetVertexColor(0.85, 0.82, 0.8)
-- a 260 px fade from the panel's dark over its left part, and the same dark, solid, left of it (Activities.lua)
summary.fade = summary:CreateTexture(nil, "BORDER")
summary.fade:SetTexture(UI.STOCK.white)
summary.fade:SetPoint("TOPLEFT", summary.art, "TOPLEFT", 0, 0)
summary.fade:SetPoint("BOTTOMLEFT", summary.art, "BOTTOMLEFT", 0, 0)
summary.fade:SetWidth(260)
summary.fade:SetGradientAlpha("HORIZONTAL", 0.02, 0.02, 0.04, 1, 0.02, 0.02, 0.04, 0)
summary.shade = summary:CreateTexture(nil, "BORDER")
summary.shade:SetTexture(UI.STOCK.white)
summary.shade:SetPoint("TOPLEFT", summary, "TOPLEFT", 5, -5)
summary.shade:SetPoint("BOTTOMRIGHT", summary.fade, "BOTTOMLEFT", 0, 0)
summary.shade:SetVertexColor(0.02, 0.02, 0.04, 1)
summary.title = UI.Text(summary, 22, C.gold, "title")
summary.title:SetPoint("TOPLEFT", summary, "TOPLEFT", 24, -22)
summary.title:SetText("Looks of Later Ages")
summary.text = UI.Para(summary, 12, C.text, 390)
summary.text:SetPoint("TOPLEFT", summary.title, "BOTTOMLEFT", 0, -10)
-- the looks themselves are browsed in the Transmog tab
summary.browse = UI.Button(summary, 200, 26, "Browse them in Transmog", "red", 12)
summary.browse:SetPoint("TOPLEFT", summary.text, "BOTTOMLEFT", 0, -18)
summary.browse:SetScript("OnClick", function()
    CO.ShowTab("transmog")
end)
summary.sub = UI.Label(summary)
summary.sub:SetPoint("TOPRIGHT", summary, "TOPRIGHT", -28, -26)
summary.big = UI.Text(summary, 22, C.text, "body", "RIGHT")
summary.big:SetFont(UI.FONT_BODY, 22, "OUTLINE")
summary.big:SetPoint("TOPRIGHT", summary.sub, "BOTTOMRIGHT", 0, -6)
summary.bar = UI.Bar(summary, 240, 14)
summary.bar:SetPoint("TOPRIGHT", summary.big, "BOTTOMRIGHT", -5, -14)
-- Your Collection: every tab's count as a stat sheet under the button, in the dark left of the picture (a gold label,
-- the white value ending at x 330 of the panel, and a bar under it where the server sends a total); CO.Refresh fills it
-- and stacks the rows: 30 apart, 44 under a row with a bar
CO.STAT_STEP, CO.STAT_STEP_BAR = 30, 44
local STAT_RIGHT = 306      -- from the label's left edge (x 24) to x 330
summary.heading = UI.Heading(summary, "Your Collection", 14)
summary.heading:SetPoint("TOPLEFT", summary.browse, "BOTTOMLEFT", 0, -28)
summary.stats = {}
for i, d in ipairs(tabDefs) do
    local st = { key = d.key }
    st.label = UI.Label(summary, d.label)
    st.label:SetPoint("TOPLEFT", summary.heading, "BOTTOMLEFT", 0, -14 - (i - 1) * CO.STAT_STEP)
    st.value = UI.Text(summary, 12, C.text, "body", "RIGHT")
    st.value:SetPoint("TOPRIGHT", st.label, "TOPLEFT", STAT_RIGHT, 0)
    st.bar = UI.Bar(summary, 200, 10)
    st.bar:SetPoint("TOPRIGHT", st.value, "BOTTOMRIGHT", -5, -6)
    summary.stats[i] = st
end
CO.summary = summary

-- Mounts and Pets, as the character frame's companion page: a list of rows (the spell in an action slot and its
-- name), and on the right the model of the one picked, its name in gold and the red Summon / Dismiss button.
local companions = CreateFrame("Frame", nil, body)
companions:SetAllPoints(body)
local COMP_ROW, COMP_STEP, COMP_SLOT = 36, 40, 28
local compScroll = UI.Scroll(companions)
compScroll:SetPoint("TOPLEFT", companions, "TOPLEFT", PAD, -14)
compScroll:SetSize(BW - 290, floor((BH - 28) / COMP_STEP) * COMP_STEP)
compScroll.child:SetWidth(BW - 290)
compScroll:SetStep(COMP_STEP)
companions.scroll = compScroll
companions.empty = UI.Text(companions, 13, C.dim, "body", "CENTER")
companions.empty:SetPoint("CENTER", compScroll, "CENTER")
local compRows = UI.Pool(function()
    local r = CreateFrame("Button", nil, compScroll.child)
    r:SetSize(BW - 290 - 22, COMP_ROW)
    UI.Backdrop(r, C.card, C.border, nil, "edge")
    -- the companion's spell in an action slot; the slot lights under the cursor
    UI.SlotArt(r, COMP_SLOT)
    r.icon:SetPoint("LEFT", r, "LEFT", 6, 0)
    r.name = UI.Text(r, 13, C.text)
    r.name:SetPoint("LEFT", r.icon, "RIGHT", 10, 0)
    UI.OneLine(r.name, BW - 290 - 22 - COMP_SLOT - 30)
    r:RegisterForClicks("LeftButtonUp")
    return r
end)
local compModelBox = UI.Box(companions, 240, BH - 28 - 72, C.card, C.border, nil, "edge")
compModelBox:SetPoint("TOPRIGHT", companions, "TOPRIGHT", -PAD - 2, -14)
local compModel = CreateFrame("PlayerModel", "BleakholdCompanionModel", compModelBox)
compModel:SetPoint("TOPLEFT", compModelBox, "TOPLEFT", 1, -1)
compModel:SetPoint("BOTTOMRIGHT", compModelBox, "BOTTOMRIGHT", -1, 1)
companions.model = compModel
companions.picked = UI.Text(companions, 14, C.gold, "body", "CENTER")
companions.picked:SetPoint("TOP", compModelBox, "BOTTOM", 0, -12)
UI.OneLine(companions.picked, 236)
-- CompanionSummonButton: Summon the picked one, or Dismiss it while it is out
companions.summon = UI.Button(companions, 120, 22, "Summon", "gold")
companions.summon:SetPoint("TOP", companions.picked, "BOTTOM", 0, -12)
companions.summon:SetScript("OnClick", function()
    local kind, i = CO.companionKind, CO.companionIndex
    if not (kind and i) then
        return
    end
    local _, _, _, _, active = GetCompanionInfo(kind, i)
    if active then
        if DismissCompanion then
            DismissCompanion(kind)
        end
    elseif CallCompanion then
        CallCompanion(kind, i)
    end
end)
CO.companions = companions

------------------------------------------------------------------------------------------------------
-- Item cache: TryOn and GetItemInfo need the item in the client cache, and 3.3.5a has no
-- GET_ITEM_INFO_RECEIVED event. A hidden tooltip asks the server for each item; a timer polls.
------------------------------------------------------------------------------------------------------
local scan = CreateFrame("GameTooltip", "BleakholdScanTooltip", UIParent, "GameTooltipTemplate")
scan:Hide()
local waiting = {}

function CO.RequestItem(id)
    if not id or GetItemInfo(id) then
        return true
    end
    if not waiting[id] then
        waiting[id] = GetTime()
        scan:SetOwner(UIParent, "ANCHOR_NONE")
        scan:SetHyperlink("item:" .. id)
        scan:Hide()
    end
    return false
end

ns.Every(0.5, function()
    local any, ready = false, false
    for id, t in pairs(waiting) do
        any = true
        if GetItemInfo(id) then
            waiting[id] = nil
            ready = true
        elseif GetTime() - t > 15 then
            waiting[id] = nil
        end
    end
    if ready and win:IsShown() then
        CO.Refresh()
        if CO.wantPreview then
            CO.Preview()
        end
    end
end)

------------------------------------------------------------------------------------------------------
-- Logic
------------------------------------------------------------------------------------------------------
local function classes()
    return ns.Classes()
end

local function currentClass()
    local list = classes()
    return list[CO.classIndex] or list[1]
end

local function currentSet()
    local cls = currentClass()
    return cls and S.sets[ns.SetKey(CO.tier, cls.id)]
end

function CO.RequestSet()
    local cls = currentClass()
    if cls then
        Comm.Get("SET", CO.tier, cls.id)
    end
end

function CO.SelectTier(tier)
    if not tier then
        return
    end
    CO.tier = tier
    CO.RequestSet()
    CO.Refresh()
    CO.Preview()
end

function CO.SelectClass(index)
    local list = classes()
    if not list[index] then
        return
    end
    CO.classIndex = index
    CO.RequestSet()
    CO.Refresh()
    CO.Preview()
end

function CO.Preview()
    local set = currentSet()
    CO.wantPreview = false
    model:SetUnit("player")
    model:Undress()
    if not set then
        return
    end
    for _, id in ipairs(set.items) do
        if CO.RequestItem(id) then
            model:TryOn(id)
        else
            CO.wantPreview = true
        end
    end
end
modelCol.preview:SetScript("OnClick", CO.Preview)
modelCol.save:SetScript("OnClick", function()
    local set = currentSet()
    if set and set.outfitUnlocked and set.setId then
        Comm.Send("OUTFIT", set.setId)
    end
end)

local function matches(text)
    if CO.search == "" then
        return true
    end
    return type(text) == "string" and string.find(string.lower(text), CO.search, 1, true) ~= nil
end

local function tierMatches(id)
    if CO.search == "" then
        return true
    end
    local t = ns.Def("L", id) or {}
    if matches(t.label) or matches(t.raids) or matches(t.echoBoss) or matches(ns.DefName("E", t.eraId)) then
        return true
    end
    for _, d in ipairs(t.sources or {}) do
        if matches(ns.DungeonName(d)) then
            return true
        end
    end
    for key, set in pairs(S.sets) do
        if set.tier == id then
            if matches(set.name) then
                return true
            end
            for _, item in ipairs(set.items) do
                if matches(GetItemInfo(item)) then
                    return true
                end
            end
        end
    end
    return false
end

local function refreshRail()
    local ids = ns.DefIds("L")
    local coll = S.coll
    local slot = 0
    for _, id in ipairs(ids) do
        if tierMatches(id) and slot < #rail.buttons then
            slot = slot + 1
            local b = rail.buttons[slot]
            local t = ns.Def("L", id) or {}
            b.tierId = id
            UI.SetText(b.tier, t.label or ("Tier " .. id))
            UI.SetColor(b.tier, id == CO.tier and C.goldPale or C.text)
            UI.SetText(b.raids, t.raids or "")
            local have = coll and coll.tierHave[id] or 0
            local total = (coll and coll.tierTotal[id]) or t.total or 0
            b.have:SetText(have .. " / " .. total)
            b.bar:SetProgress(total > 0 and have / total or 0)
            UI.Colors(b, id == CO.tier and C.active or C.card, id == CO.tier and C.gold or C.border)
            b:Show()
        end
    end
    for i = slot + 1, #rail.buttons do
        rail.buttons[i]:Hide()
    end
end

local function refreshClasses()
    local list = classes()
    for i, b in ipairs(mainF.classes) do
        local cls = list[i]
        if cls then
            local on = i == CO.classIndex
            b.portrait:SetClass(cls.token)
            b.portrait:SetChosen(on)
            b:SetScript("OnClick", function()
                CO.SelectClass(i)
            end)
            b:SetScript("OnEnter", function(self)
                UI.ShowTooltip(self, { cls.name })
            end)
            b:SetScript("OnLeave", function()
                if GameTooltip then GameTooltip:Hide() end
            end)
            b:Show()
        else
            b:Hide()
        end
    end
    local items = {}
    for i = 5, #list do
        items[#items + 1] = { value = i, text = list[i].name }
    end
    mainF.more:SetItems(items)
    if CO.classIndex >= 5 and list[CO.classIndex] then
        mainF.more:SetLabel(list[CO.classIndex].name)
    else
        mainF.more:SetLabel("+" .. #items .. " more")
    end
    if #items == 0 then
        mainF.more:Hide()
    else
        mainF.more:Show()
    end
end

local function refreshPieces(set)
    for i, p in ipairs(mainF.pieces) do
        local id = set and set.items[i]
        if id then
            local name, _, quality = GetItemInfo(id)
            if not name then
                CO.RequestItem(id)
            end
            local have = ns.SetCollected(set, i)
            -- a piece not collected yet: its icon greyed, as a missing item; the name keeps its quality colour
            p.icon:SetTexture(GetItemIcon(id) or "Interface\\Icons\\INV_Misc_QuestionMark")
            p.icon:SetDesaturated(not have)
            p.icon:SetAlpha(have and 1 or 0.7)
            UI.SetText(p.name, name or "Loading...")
            UI.SetColor(p.name, UI.QUALITY[quality or 4] or C.epic)
            p.state:SetText(have and "Collected" or "Not collected")
            UI.SetColor(p.state, have and C.teal or C.mute)
            -- a piece the search found is lit as a checked slot
            p:SetSlotChecked(CO.search ~= "" and name and matches(name))
            p:SetScript("OnEnter", function(self)
                if GameTooltip then
                    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
                    GameTooltip:SetHyperlink("item:" .. id)
                    GameTooltip:Show()
                end
            end)
            p:SetScript("OnLeave", function()
                if GameTooltip then GameTooltip:Hide() end
            end)
            p:SetScript("OnClick", function()
                local _, link = GetItemInfo(id)
                if IsShiftKeyDown() and link and ChatEdit_InsertLink then
                    ChatEdit_InsertLink(link)
                elseif CO.RequestItem(id) then
                    model:TryOn(id)
                end
            end)
            p:Show()
        else
            p:Hide()
        end
    end
end

function CO.RefreshLegacy()
    refreshRail()
    refreshClasses()
    local t = ns.Def("L", CO.tier) or {}
    local eraName = ns.DefName("E", t.eraId, "")
    UI.SetText(mainF.sub, (t.label or ("Tier " .. CO.tier)) .. (eraName ~= "" and (" - " .. eraName .. " era") or ""))
    local set = currentSet()
    local cls = currentClass()
    if set then
        UI.SetText(mainF.name, set.name or ("Tier " .. CO.tier .. " " .. (cls and cls.name or "")))
    else
        mainF.name:SetText(Comm.ready and "Loading set..." or "Waiting for the server")
    end
    refreshPieces(set)

    -- drops / level 80
    local lvlMin = (set and set.lvlMin) or t.lvlMin
    local lvlMax = (set and set.lvlMax) or t.lvlMax
    mainF.drops.label:SetText("Drops In" .. ((lvlMin and lvlMax) and (" (Levels " .. lvlMin .. "-" .. lvlMax .. ")") or ""))
    local sources = (set and #set.sources > 0) and set.sources or (t.sources or {})
    local names = {}
    for i = 1, min(#sources, 8) do
        names[i] = ns.DungeonName(sources[i])
    end
    UI.SetText(mainF.drops.text, #names > 0 and table.concat(names, ", ") or "-")
    UI.SetText(mainF.at80.text, "Keys and Rift floors in the " .. (eraName ~= "" and eraName or "matching") .. " week.")
    local echo = (set and set.echoBoss) or t.echoBoss
    UI.SetText(mainF.at80.echo, echo and ("Raid Echo: " .. echo) or "")
    UI.SetText(mainF.note, set and set.note or "")

    -- collected ring
    local have, total = 0, set and #set.items or 0
    if set then
        for i = 1, total do
            if ns.SetCollected(set, i) then
                have = have + 1
            end
        end
    end
    modelCol.bar:SetProgress(total > 0 and have / total or 0, have .. " / " .. total)
    modelCol.count:SetText(have .. " of " .. total .. " collected")
    local unlocked = set and set.outfitUnlocked
    modelCol.hint:SetText(unlocked and "Outfit unlocked" or "Complete it to unlock the outfit")
    modelCol.save:SetActive(unlocked and true or false)
    modelCol.save:SetStyle(unlocked and "gold" or "dark")
end

local function refreshCompanions(kind)
    compRows:ReleaseAll()
    local n = GetNumCompanions and GetNumCompanions(kind) or 0
    local y = 0
    -- the one the model shows: the first of the list until another is clicked
    local picked, pickedIndex
    for i = 1, n do
        local id = GetCompanionInfo(kind, i)
        if id and (id == CO.companionPicked or not picked) then
            picked, pickedIndex = id, i
        end
    end
    if picked and picked ~= CO.companionPicked then
        CO.companionPicked = picked
        compModel:SetCreature(picked)
    end
    CO.companionKind, CO.companionIndex = kind, pickedIndex
    if pickedIndex then
        local _, pickedName, _, _, active = GetCompanionInfo(kind, pickedIndex)
        UI.SetText(companions.picked, pickedName or "")
        companions.summon:SetLabel(active and "Dismiss" or "Summon")
        companions.summon:SetActive(CallCompanion ~= nil)
        companions.picked:Show()
        companions.summon:Show()
    else
        companions.picked:Hide()
        companions.summon:Hide()
    end
    for i = 1, n do
        local creatureID, name, spellID, icon = GetCompanionInfo(kind, i)
        if name then
            local r = compRows:Acquire()
            r:ClearAllPoints()
            r:SetPoint("TOPLEFT", compScroll.child, "TOPLEFT", 0, -y)
            r.icon:SetTexture(UI.IconPath(icon) or UI.STOCK.question)
            UI.SetText(r.name, name)
            UI.Select(r, creatureID ~= nil and creatureID == CO.companionPicked)
            r:SetScript("OnClick", function()
                if creatureID then
                    CO.companionPicked = creatureID
                    compModel:SetCreature(creatureID)
                    CO.Refresh()
                end
            end)
            y = y + COMP_STEP
        end
    end
    compScroll:SetContentHeight(y)
    if n == 0 then
        companions.empty:SetText(kind == "MOUNT" and "No mounts yet." or "No pets yet.")
        companions.empty:Show()
    else
        companions.empty:Hide()
    end
end

local function countText(n, total)
    if not n then
        return ""
    end
    return U.Commas(n) .. (total and (" / " .. U.Commas(total)) or "")
end

-- Each tab's { owned, total }, nil where unknown (the game keeps no total of mounts, pets or animations).
local function collectionCounts()
    local coll = S.coll or {}
    return {
        transmog = { coll.transmogOwned, coll.transmogTotal },
        later = { coll.laterOwned, coll.laterTotal },
        legacy = { coll.setsOwned, coll.setsTotal },
        mounts = { GetNumCompanions and GetNumCompanions("MOUNT") or 0 },
        pets = { GetNumCompanions and GetNumCompanions("CRITTER") or 0 },
        animations = { ns.Animations and #ns.Animations.List() or nil },
    }
end

function CO.RefreshTabs()
    local counts = collectionCounts()
    for i, b in ipairs(CO.tabs) do
        local d = tabDefs[i]
        local c = counts[d.key]
        -- the Transmog tab names only what is owned
        local cnt = countText(c[1], d.key ~= "transmog" and c[2] or nil)
        b:SetLabel(d.label .. (cnt ~= "" and (" (" .. cnt .. ")") or ""))
        b:SetStyle(CO.tab == d.key and "stripOn" or "strip")
    end
    CO.LayoutTabs()
end

function CO.Refresh()
    if not win:IsShown() then
        return
    end
    CO.RefreshTabs()
    legacy:Hide()
    summary:Hide()
    companions:Hide()
    local A, TM = ns.Animations, ns.Transmog
    if A and CO.tab ~= "animations" then
        A.HideTab()
    end
    if TM and CO.tab ~= "transmog" then
        TM.HideTab()
    end
    local hints = { animations = "Search dances and emotes", transmog = "Search looks by item name" }
    search.hint:SetText(hints[CO.tab] or "Search sets, pieces, dungeons")
    local coll = S.coll
    if CO.tab == "animations" and A then
        A.ShowTab()
    elseif CO.tab == "transmog" and TM then
        TM.ShowTab()
    elseif CO.tab == "legacy" then
        legacy:Show()
        CO.RefreshLegacy()
    elseif CO.tab == "mounts" or CO.tab == "pets" then
        companions:Show()
        refreshCompanions(CO.tab == "mounts" and "MOUNT" or "CRITTER")
    else
        summary:Show()
        if ns.Journal.Set(summary.art, CO.ART_KEY, "bg", CO.ART_W, CO.ART_H) then
            summary.fade:Show()
            summary.shade:Show()
        else
            summary.fade:Hide()
            summary.shade:Hide()
        end
        summary.big:SetText(coll and coll.laterOwned and countText(coll.laterOwned, coll.laterTotal) or "-")
        summary.sub:SetLabel("Collected")
        local owned, total = coll and coll.laterOwned, coll and coll.laterTotal
        summary.bar:SetProgress((owned and total and total > 0) and owned / total or 0,
            (owned and total and total > 0) and (floor(owned / total * 100 + 0.5) .. "%") or "")
        summary.text:SetText("Appearances from later expansions, earned on Bleakhold.")
        local counts, y = collectionCounts(), -14
        for _, st in ipairs(summary.stats) do
            local c = counts[st.key]
            st.label:ClearAllPoints()
            st.label:SetPoint("TOPLEFT", summary.heading, "BOTTOMLEFT", 0, y)
            st.value:SetText(c[1] and countText(c[1], c[2]) or "-")
            if c[1] and c[2] and c[2] > 0 then
                st.bar:SetProgress(c[1] / c[2])
                st.bar:Show()
                y = y - CO.STAT_STEP_BAR
            else
                st.bar:Hide()
                y = y - CO.STAT_STEP
            end
        end
    end
end

function CO.ShowTab(key)
    CO.tab = key
    if not win:IsShown() then
        win:Show()
    end
    CO.Refresh()
end

function win:OnOpen()
    Comm.Refresh("COLL")
    -- start on the player's own class
    local _, token = UnitClass("player")
    if token and not CO.classChosen then
        for i, c in ipairs(classes()) do
            if c.token == token then
                CO.classIndex = i
            end
        end
        CO.classChosen = true
    end
    CO.RequestSet()
    CO.Refresh()
    CO.Preview()
end

ns.On("STATE", function(topic)
    if win:IsShown() and (topic == "COLL" or topic == "SET" or topic == "DEF" or topic == "LIDX") then
        CO.Refresh()
        if topic == "SET" then
            CO.Preview()
        end
    end
end)

-- a companion summoned, dismissed or learned: Summon / Dismiss and the list follow. COMPANION_UPDATE also fires for
-- other players' companions nearby, often, so one refresh at most every 0.2 s, and only while the list shows.
local function companionsShown()
    return win:IsShown() and (CO.tab == "mounts" or CO.tab == "pets")
end
local companionTimer
ns.RegisterEvent("COMPANION_UPDATE", function()
    if companionTimer or not companionsShown() then
        return
    end
    companionTimer = ns.After(0.2, function()
        companionTimer = nil
        if companionsShown() then
            CO.Refresh()
        end
    end)
end)

local function open(tab, toggle)
    if toggle and win:IsShown() and (not tab or tab == CO.tab) then
        win:Hide()
        return
    end
    if tab then
        CO.tab = tab
    end
    if win:IsShown() then
        CO.Refresh()
    else
        win:Show()
    end
end

UI.RegisterOpener("collections", function(toggle) open(nil, toggle) end)
UI.RegisterOpener("collections-legacy", function(toggle) open("legacy", toggle) end)
ns.AddCommand("collections", "open Collections", function() open(nil, true) end)

-- AddicatUI's and DragonUI's Pets & Mounts button opens a server's collections window through this global when
-- one exists. Their own journal summons, dismisses and picks a random mount, which this window does not, so with
-- either loaded (both load before Bleakhold) the global stays theirs to leave undefined; Collections stays on the
-- Bleakhold button, /bh collections and its key binding.
local function journalAddonLoaded()
    return IsAddOnLoaded and (IsAddOnLoaded("AddicatUI") or IsAddOnLoaded("DragonUI")) and true or false
end

if type(ToggleCollectionsJournal) ~= "function" and not journalAddonLoaded() then
    ToggleCollectionsJournal = function()
        open(nil, true)
    end
end
