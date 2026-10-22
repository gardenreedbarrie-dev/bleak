-- Bleakhold: Collections window. Tabs Transmog / Looks of Later Ages / Legacy Sets / Mounts / Pets.
-- Legacy Sets: eras rail, set pieces grid (hover = item tooltip, click = try on, shift-click = link),
-- where the set drops, and a DressUpModel preview. Collected state and the outfit unlock come from
-- the server (SET); Save outfit is an intent (OUTFIT) the server checks.
-- Defines the global ToggleCollectionsJournal (if nothing else did) so DragonUI's Pets & Mounts button
-- opens this window instead of its own.
local ADDON, ns = ...
local U, UI, Comm, Data = ns.U, ns.UI, ns.Comm, ns.Data
local C = UI.C
local S = ns.S

local floor, max, min = math.floor, math.max, math.min

local CO = {}
ns.Collections = CO

CO.W, CO.H = 940, 600
CO.tab = "legacy"
CO.tier = 1
CO.classIndex = 1
CO.search = ""

local win = UI.Window("BleakholdCollectionsFrame", CO.W, CO.H, "COLLECTIONS", "layers")
CO.frame = win

------------------------------------------------------------------------------------------------------
-- Header search
------------------------------------------------------------------------------------------------------
local search = CreateFrame("EditBox", "BleakholdCollectionsSearch", win.header)
search:SetSize(260, 26)
search:SetPoint("RIGHT", win.close, "LEFT", -14, 0)
search:SetFont(UI.FONT_BODY, 12, "")
search:SetTextColor(UI.Rgb(C.text))
search:SetAutoFocus(false)
search:SetMaxLetters(40)
search:SetTextInsets(24, 6, 0, 0)
UI.Backdrop(search, C.rail, C.chipBorder)
search.icon = UI.Glyph(search, "search", 14, C.dim)
search.icon:SetPoint("LEFT", search, "LEFT", 6, 0)
search.hint = UI.Text(search, 12, C.mute)
search.hint:SetPoint("LEFT", search, "LEFT", 24, 0)
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
-- Tabs
------------------------------------------------------------------------------------------------------
local tabBar = UI.Box(win.content, 10, 44, C.rail)
tabBar:SetPoint("TOPLEFT", win.content, "TOPLEFT", 0, 0)
tabBar:SetPoint("TOPRIGHT", win.content, "TOPRIGHT", 0, 0)
local tabDefs = {
    { key = "transmog", label = "Transmog" },
    { key = "later", label = "Looks of Later Ages" },
    { key = "legacy", label = "Legacy Sets" },
    { key = "mounts", label = "Mounts" },
    { key = "pets", label = "Pets" },
}
CO.tabs = {}
local tx = 16
for i, d in ipairs(tabDefs) do
    local w = (d.key == "later") and 210 or 140
    local b = UI.Button(tabBar, w, 30, d.label, "tab", 13)
    b:SetPoint("LEFT", tabBar, "LEFT", tx, 0)
    tx = tx + w + 6
    b.key = d.key
    b:SetScript("OnClick", function()
        CO.ShowTab(d.key)
    end)
    CO.tabs[i] = b
end

local body = CreateFrame("Frame", nil, win.content)
body:SetPoint("TOPLEFT", tabBar, "BOTTOMLEFT", 0, 0)
body:SetPoint("BOTTOMRIGHT", win.content, "BOTTOMRIGHT", 0, 0)
CO.body = body
local BW, BH = CO.W - 2, CO.H - 4 - 46 - 44 - 2

------------------------------------------------------------------------------------------------------
-- Legacy Sets
------------------------------------------------------------------------------------------------------
local legacy = CreateFrame("Frame", nil, body)
legacy:SetAllPoints(body)
CO.legacy = legacy

local RAIL = 230
local rail = UI.Box(legacy, RAIL, BH, "13161A")
rail:SetPoint("TOPLEFT", legacy, "TOPLEFT", 0, 0)
rail:SetPoint("BOTTOMLEFT", legacy, "BOTTOMLEFT", 0, 0)
rail.label = UI.Text(rail, 11, C.dim)
rail.label:SetPoint("TOPLEFT", rail, "TOPLEFT", 14, -12)
rail.label:SetText("ERAS")
rail.buttons = {}
for i = 1, 7 do
    local b = CreateFrame("Button", nil, rail)
    b:SetSize(RAIL - 20, 56)
    b:SetPoint("TOPLEFT", rail, "TOPLEFT", 10, -30 - (i - 1) * 62)
    UI.Backdrop(b, C.card, C.border)
    b.tier = UI.Text(b, 13, C.text)
    b.tier:SetPoint("TOPLEFT", b, "TOPLEFT", 10, -8)
    b.have = UI.Text(b, 11, C.dim, "body", "RIGHT")
    b.have:SetPoint("TOPRIGHT", b, "TOPRIGHT", -10, -9)
    b.raids = UI.Text(b, 11, C.mid)
    b.raids:SetPoint("TOPLEFT", b.tier, "BOTTOMLEFT", 0, -3)
    UI.OneLine(b.raids, RAIL - 40)
    b.bar = UI.Bar(b, RAIL - 40, 4, C.teal, C.bg)
    b.bar:SetPoint("BOTTOMLEFT", b, "BOTTOMLEFT", 10, 7)
    b:RegisterForClicks("LeftButtonUp")
    b:SetScript("OnClick", function(self)
        CO.SelectTier(self.tierId)
    end)
    rail.buttons[i] = b
end

local mainX = RAIL + 18
local MODEL_W = 230
local MAIN_W = BW - mainX - MODEL_W - 36
local mainF = CreateFrame("Frame", nil, legacy)
mainF:SetPoint("TOPLEFT", legacy, "TOPLEFT", mainX, -16)
mainF:SetSize(MAIN_W, BH - 32)

mainF.sub = UI.Text(mainF, 11, C.dim)
mainF.sub:SetPoint("TOPLEFT", mainF, "TOPLEFT", 0, 0)
mainF.name = UI.Text(mainF, 22, C.goldPale, "title")
mainF.name:SetPoint("TOPLEFT", mainF.sub, "BOTTOMLEFT", 0, -4)
UI.OneLine(mainF.name, MAIN_W)

-- Class selector: four round buttons and an overflow list ("+6" with the ten stock classes).
mainF.classes = {}
for i = 1, 4 do
    local b = CreateFrame("Button", nil, mainF)
    b:SetSize(36, 36)
    b:SetPoint("TOPLEFT", mainF, "TOPLEFT", (i - 1) * 42, -48)
    b.fill = UI.Disc(b, 36, C.card, "BACKGROUND")
    b.fill:SetPoint("CENTER")
    b.ring = b:CreateTexture(nil, "BORDER")
    b.ring:SetTexture(UI.ART .. "Ring")
    b.ring:SetAllPoints(b)
    b.text = UI.Text(b, 11, C.mid, "body", "CENTER")
    b.text:SetPoint("CENTER")
    b:RegisterForClicks("LeftButtonUp")
    mainF.classes[i] = b
end
mainF.more = UI.Dropdown(mainF, 64, function(value)
    CO.SelectClass(value)
end)
mainF.more:SetPoint("TOPLEFT", mainF, "TOPLEFT", 4 * 42 + 4, -53)

-- Pieces grid 4 x 2
local PIECE_W = floor((MAIN_W - 30) / 4)
mainF.pieces = {}
for i = 1, 8 do
    local p = CreateFrame("Button", nil, mainF)
    p:SetSize(PIECE_W, 104)
    p:SetPoint("TOPLEFT", mainF, "TOPLEFT", ((i - 1) % 4) * (PIECE_W + 10), -96 - floor((i - 1) / 4) * 112)
    UI.Backdrop(p, C.card, C.border)
    p.slot = CreateFrame("Frame", nil, p)
    p.slot:SetSize(46, 46)
    p.slot:SetPoint("TOP", p, "TOP", 0, -10)
    UI.Backdrop(p.slot, C.slotBg, C.purple)
    p.icon = p.slot:CreateTexture(nil, "ARTWORK")
    p.icon:SetPoint("TOPLEFT", p.slot, "TOPLEFT", 3, -3)
    p.icon:SetPoint("BOTTOMRIGHT", p.slot, "BOTTOMRIGHT", -3, 3)
    p.dash = p.slot:CreateTexture(nil, "OVERLAY")
    p.dash:SetTexture(UI.ART .. "Dashed")
    p.dash:SetAllPoints(p.slot)
    p.dash:SetVertexColor(UI.Rgb(C.chipBorder))
    p.name = UI.Text(p, 11, C.epic, "body", "CENTER")
    p.name:SetPoint("TOPLEFT", p, "TOPLEFT", 4, -62)
    p.name:SetPoint("TOPRIGHT", p, "TOPRIGHT", -4, -62)
    p.state = UI.Text(p, 10, C.mute, "body", "CENTER")
    p.state:SetPoint("BOTTOM", p, "BOTTOM", 0, 8)
    p:RegisterForClicks("LeftButtonUp")
    mainF.pieces[i] = p
end

-- Where it drops / at level 80
local drops = UI.Box(mainF, MAIN_W, 74, C.card, C.border)
drops:SetPoint("TOPLEFT", mainF, "TOPLEFT", 0, -324)
drops.label = UI.Text(drops, 11, C.dim)
drops.label:SetPoint("TOPLEFT", drops, "TOPLEFT", 12, -10)
drops.chips = {}
for i = 1, 8 do
    local c = UI.Pill(drops, "", C.chip, C.chipBorder, C.text, 11)
    c:Hide()
    drops.chips[i] = c
end
mainF.drops = drops
local at80 = UI.Box(mainF, MAIN_W, 58, C.eraBg, C.eraBorder)
at80:SetPoint("TOPLEFT", drops, "BOTTOMLEFT", 0, -8)
at80.label = UI.Text(at80, 11, C.dim)
at80.label:SetPoint("TOPLEFT", at80, "TOPLEFT", 12, -10)
at80.label:SetText("AT LEVEL 80")
at80.text = UI.Text(at80, 11, C.mid)
at80.text:SetPoint("TOPLEFT", at80.label, "BOTTOMLEFT", 0, -6)
UI.OneLine(at80.text, MAIN_W - 24)
at80.echo = UI.Text(at80, 12, C.orange, "body", "RIGHT")
at80.echo:SetPoint("TOPRIGHT", at80, "TOPRIGHT", -12, -9)
UI.OneLine(at80.echo, 200)
mainF.at80 = at80
mainF.note = UI.Text(mainF, 11, C.dim)
mainF.note:SetPoint("TOPLEFT", mainF, "TOPLEFT", 0, -306)
UI.OneLine(mainF.note, MAIN_W)
CO.main = mainF

-- Model column
local modelCol = CreateFrame("Frame", nil, legacy)
modelCol:SetSize(MODEL_W, BH - 32)
modelCol:SetPoint("TOPRIGHT", legacy, "TOPRIGHT", -18, -16)
local modelBox = UI.Box(modelCol, MODEL_W, BH - 150, "101216", C.border)
modelBox:SetPoint("TOP", modelCol, "TOP", 0, 0)
local model = CreateFrame("DressUpModel", "BleakholdCollectionsModel", modelBox)
model:SetPoint("TOPLEFT", modelBox, "TOPLEFT", 2, -2)
model:SetPoint("BOTTOMRIGHT", modelBox, "BOTTOMRIGHT", -2, 2)
model:EnableMouse(true)
model:EnableMouseWheel(true)
CO.model = model
modelCol.ring = UI.Ring(modelCol, 40, 5)
modelCol.ring:SetPoint("TOPLEFT", modelBox, "BOTTOMLEFT", 0, -12)
modelCol.count = UI.Text(modelCol, 14, C.text)
modelCol.count:SetPoint("TOPLEFT", modelCol.ring, "TOPRIGHT", 10, -4)
modelCol.hint = UI.Text(modelCol, 11, C.dim)
modelCol.hint:SetPoint("TOPLEFT", modelCol.count, "BOTTOMLEFT", 0, -3)
modelCol.preview = UI.Button(modelCol, (MODEL_W - 8) / 2, 34, "Preview", "gold", 13)
modelCol.preview:SetPoint("BOTTOMLEFT", modelCol, "BOTTOMLEFT", 0, 0)
modelCol.save = UI.Button(modelCol, (MODEL_W - 8) / 2, 34, "Save outfit", "dark", 13)
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
local summary = CreateFrame("Frame", nil, body)
summary:SetAllPoints(body)
summary.big = UI.Text(summary, 32, C.goldPale, "title", "CENTER")
summary.big:SetPoint("TOP", summary, "TOP", 0, -90)
summary.sub = UI.Text(summary, 14, C.mid, "body", "CENTER")
summary.sub:SetPoint("TOP", summary.big, "BOTTOM", 0, -10)
summary.text = UI.Text(summary, 12, C.dim, "body", "CENTER")
summary.text:SetPoint("TOP", summary.sub, "BOTTOM", 0, -14)
summary.text:SetWidth(520)
CO.summary = summary

local companions = CreateFrame("Frame", nil, body)
companions:SetAllPoints(body)
local compScroll = UI.Scroll(companions)
compScroll:SetPoint("TOPLEFT", companions, "TOPLEFT", 16, -14)
compScroll:SetSize(BW - 290, BH - 28)
compScroll.child:SetWidth(BW - 290)
companions.scroll = compScroll
companions.empty = UI.Text(companions, 13, C.dim, "body", "CENTER")
companions.empty:SetPoint("CENTER", compScroll, "CENTER")
local compRows = UI.Pool(function()
    local r = CreateFrame("Button", nil, compScroll.child)
    r:SetSize(BW - 300, 32)
    UI.Backdrop(r, C.card, C.border)
    r.icon = r:CreateTexture(nil, "ARTWORK")
    r.icon:SetSize(24, 24)
    r.icon:SetPoint("LEFT", r, "LEFT", 6, 0)
    r.name = UI.Text(r, 13, C.text)
    r.name:SetPoint("LEFT", r.icon, "RIGHT", 8, 0)
    r:RegisterForClicks("LeftButtonUp")
    return r
end)
local compModelBox = UI.Box(companions, 240, BH - 28, "101216", C.border)
compModelBox:SetPoint("TOPRIGHT", companions, "TOPRIGHT", -16, -14)
local compModel = CreateFrame("PlayerModel", "BleakholdCompanionModel", compModelBox)
compModel:SetPoint("TOPLEFT", compModelBox, "TOPLEFT", 2, -2)
compModel:SetPoint("BOTTOMRIGHT", compModelBox, "BOTTOMRIGHT", -2, 2)
companions.model = compModel
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
            b.text:SetText(cls.short)
            local on = i == CO.classIndex
            b.fill:SetVertexColor(UI.Rgb(on and C.active or C.card))
            b.ring:SetVertexColor(UI.Rgb(on and C.gold or C.chipBorder))
            UI.SetColor(b.text, on and C.goldLight or C.mid)
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
        mainF.more:SetLabel(list[CO.classIndex].short)
        mainF.more:SetStyle("tabOn")
    else
        mainF.more:SetLabel("+" .. #items)
        mainF.more:SetStyle("dark")
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
            local name = GetItemInfo(id)
            if not name then
                CO.RequestItem(id)
            end
            local have = ns.SetCollected(set, i)
            p.icon:SetTexture(GetItemIcon(id) or "Interface\\Icons\\INV_Misc_QuestionMark")
            p.icon:SetDesaturated(not have)
            UI.SetText(p.name, name or "Loading...")
            UI.SetColor(p.name, have and C.epic or C.purple)
            p.state:SetText(have and "Collected" or "Not collected")
            UI.SetColor(p.state, have and C.teal or C.mute)
            UI.Colors(p, have and C.setBg or C.card, have and C.setBorder or C.border)
            if have then
                UI.Colors(p.slot, C.slotBg, C.purple)
                p.dash:Hide()
            else
                UI.Colors(p.slot, C.rail, C.rail)
                p.dash:Show()
            end
            local hit = CO.search ~= "" and name and matches(name)
            if hit then
                UI.Colors(p, C.active, C.gold)
            end
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
    UI.SetText(mainF.sub, string.upper((t.label or ("Tier " .. CO.tier)) .. (eraName ~= "" and (" - " .. eraName .. " era") or "")))
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
    mainF.drops.label:SetText("DROPS IN" .. ((lvlMin and lvlMax) and (" (LEVELS " .. lvlMin .. "-" .. lvlMax .. ")") or ""))
    local sources = (set and #set.sources > 0) and set.sources or (t.sources or {})
    local shown = {}
    for i, c in ipairs(mainF.drops.chips) do
        local d = sources[i]
        if d then
            c:SetValue(ns.DungeonName(d))
            c:Show()
            shown[#shown + 1] = c
        else
            c:Hide()
        end
    end
    -- chips flow into two rows
    local x, y, maxW = 12, -26, MAIN_W - 12
    for _, c in ipairs(shown) do
        local w = c:GetWidth()
        if x + w > maxW and x > 12 then
            x, y = 12, y - 24
        end
        c:ClearAllPoints()
        c:SetPoint("TOPLEFT", mainF.drops, "TOPLEFT", x, y)
        x = x + w + 6
    end
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
    modelCol.ring:SetProgress(total > 0 and have / total or 0, C.teal)
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
    for i = 1, n do
        local creatureID, name, spellID, icon = GetCompanionInfo(kind, i)
        if name then
            local r = compRows:Acquire()
            r:ClearAllPoints()
            r:SetPoint("TOPLEFT", compScroll.child, "TOPLEFT", 0, -y)
            r.icon:SetTexture(icon or "Interface\\Icons\\INV_Misc_QuestionMark")
            UI.SetText(r.name, name)
            r:SetScript("OnClick", function()
                if creatureID then
                    compModel:SetCreature(creatureID)
                end
            end)
            y = y + 36
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

function CO.RefreshTabs()
    local coll = S.coll
    local counts = {
        transmog = coll and countText(coll.transmogOwned) or "",
        later = coll and countText(coll.laterOwned, coll.laterTotal) or "",
        legacy = coll and countText(coll.setsOwned, coll.setsTotal) or "",
        mounts = tostring(GetNumCompanions and GetNumCompanions("MOUNT") or 0),
        pets = tostring(GetNumCompanions and GetNumCompanions("CRITTER") or 0),
    }
    for i, b in ipairs(CO.tabs) do
        local d = tabDefs[i]
        local cnt = counts[d.key]
        b:SetLabel(d.label .. ((cnt and cnt ~= "") and ("  |cff8C877D" .. cnt .. "|r") or ""))
        b:SetStyle(CO.tab == d.key and "tabOn" or "tab")
    end
end

function CO.Refresh()
    if not win:IsShown() then
        return
    end
    CO.RefreshTabs()
    legacy:Hide()
    summary:Hide()
    companions:Hide()
    local coll = S.coll
    if CO.tab == "legacy" then
        legacy:Show()
        CO.RefreshLegacy()
    elseif CO.tab == "mounts" or CO.tab == "pets" then
        companions:Show()
        refreshCompanions(CO.tab == "mounts" and "MOUNT" or "CRITTER")
    elseif CO.tab == "transmog" then
        summary:Show()
        summary.big:SetText(coll and coll.transmogOwned and U.Commas(coll.transmogOwned) or "-")
        summary.sub:SetText("appearances collected for your account")
        summary.text:SetText("Looks you have earned can be applied at a transmogrifier.")
    else
        summary:Show()
        summary.big:SetText(coll and coll.laterOwned and countText(coll.laterOwned, coll.laterTotal) or "-")
        summary.sub:SetText("Looks of Later Ages collected")
        summary.text:SetText("Appearances from later expansions, earned on Bleakhold.")
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

-- DragonUI's Pets & Mounts window defers to a server collections window through this global.
if type(ToggleCollectionsJournal) ~= "function" then
    ToggleCollectionsJournal = function()
        open(nil, true)
    end
end
