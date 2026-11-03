-- Stand-ins for a realm patch's own character creation screen (a CharacterCreate.xml and .lua of its own, loaded in
-- place of the stock ones), written for this test: other button sizes, anchors, templates and code than the stock
-- screen's. tests.lua picks one by scenario name before stock.lua runs; stock.lua calls its buttons() where the
-- stock screen makes its ten race buttons and its scripts() after the stock functions.
--
-- Each entry also says what the test expects: kind (what BleakholdGlue.RaceScreenKind() must say), count (the
-- screen's own buttons), keepsOwn (none of them may move), left (buttons of the Alliance column left of every Horde
-- button), column (the Horde column, top to bottom: one step between each), added (the anchor each added button
-- must get, relative regions by name, or a list of such anchors), scale (every button's), parts (the added buttons
-- have the screen's named parts; whole: every part, as they are plain CheckButtons), idAtLoad (the template's OnLoad
-- saw each added button's id).

MOCK.raceGlues = {}
local PREFIX = "CharacterCreateRaceButton"

local function headers()
    local alliance = CreateFrame("Frame", "BleakTestAllianceHeader", CharacterCreate)
    alliance:SetSize(220, 48)
    alliance:SetPoint("TOPLEFT", CharacterCreate, "TOPLEFT", 28, -36)
    local horde = CreateFrame("Frame", "BleakTestHordeHeader", CharacterCreate)
    horde:SetSize(220, 48)
    horde:SetPoint("TOPRIGHT", CharacterCreate, "TOPRIGHT", -28, -36)
    return alliance, horde
end

-- The screen's XML redefines the stock template under its stock name with big round portraits. With `placeById` its
-- OnLoad also places the button by its id (a template with anchors of its own).
local function portraitTemplate(size, placeById)
    MOCK.templates.CharacterCreateRaceButtonTemplate = function(b, name)
        b:SetSize(size, size)
        if placeById then
            b.idAtLoad = b:GetID()
            b:SetPoint("TOP", b:GetParent(), "TOP", 0, -40 * b:GetID())
        end
        b:SetNormalTexture("Interface\\Glues\\CharacterCreate\\UI-CharacterCreate-Races")
        b:SetPushedTexture("Interface\\Glues\\CharacterCreate\\UI-CharacterCreate-Races")
        _G[name .. "NormalTexture"] = b:GetNormalTexture()
        _G[name .. "PushedTexture"] = b:GetPushedTexture()
        _G[name .. "Text"] = b:CreateFontString(name .. "Text", "ARTWORK")
        b:SetScript("OnClick", function(self) if self.enable then CharacterRace_OnClick(self, self:GetID()) end end)
    end
end

-- One of the screen's own buttons (its XML's anchors replace any its template gave it).
local function button(i, parent, template)
    local b = CreateFrame("CheckButton", PREFIX .. i, parent, template or "CharacterCreateRaceButtonTemplate")
    b:SetID(i)
    b:ClearAllPoints()
    b.screenMade = true
    return b
end

-- Alliance buttons hang from the left header and each under the one before it (TOPLEFT), Horde buttons from the
-- right header (TOPRIGHT): the layout of the owner's screenshot, in `alliance` + `horde` buttons.
local function chainColumns(alliance, horde, step, template)
    local left, right = headers()
    for i = 1, alliance + horde do
        local b = button(i, CharacterCreate, template)
        if i == 1 then b:SetPoint("TOPLEFT", left, "BOTTOMLEFT", 10, -12)
        elseif i == alliance + 1 then b:SetPoint("TOPRIGHT", right, "BOTTOMRIGHT", -10, -12)
        elseif i <= alliance then b:SetPoint("TOPLEFT", _G[PREFIX .. (i - 1)], "BOTTOMLEFT", 0, -step)
        else b:SetPoint("TOPRIGHT", _G[PREFIX .. (i - 1)], "BOTTOMRIGHT", 0, -step) end
    end
end

MOCK.raceGlues["custom-chain"] = {
    kind = "custom", count = 10, keepsOwn = true, left = { 1, 2, 3, 4, 5 }, column = { 7, 8, 9, 10, 11, 12 },
    added = { [11] = { "TOPRIGHT", PREFIX .. "10", "BOTTOMRIGHT", 0, -14 },
              [12] = { "TOPRIGHT", PREFIX .. "11", "BOTTOMRIGHT", 0, -14 } },
    buttons = function()
        portraitTemplate(64)
        chainColumns(5, 5, 14)
    end,
}

-- The template places each button by its id in its OnLoad: the added buttons come with anchors of their own.
MOCK.raceGlues["custom-tplanchor"] = {
    kind = "custom", count = 10, keepsOwn = true, left = { 1, 2, 3, 4, 5 }, column = { 7, 8, 9, 10, 11, 12 },
    idAtLoad = true,
    added = { [11] = { "TOPRIGHT", PREFIX .. "10", "BOTTOMRIGHT", 0, -14 },
              [12] = { "TOPRIGHT", PREFIX .. "11", "BOTTOMRIGHT", 0, -14 } },
    buttons = function()
        portraitTemplate(64, true)
        chainColumns(5, 5, 14)
    end,
}

-- Every button anchored TOP to its header's BOTTOM, row by row: what the old layout code put all in one column.
-- With `scale`, the screen's OnLoad enlarges each of its buttons (for i = 1, MAX_RACES while that is still ten).
local function offsetColumns(scale)
    portraitTemplate(64)
    local left, right = headers()
    for i = 1, 10 do
        local b = button(i, CharacterCreate)
        local row = (i - 1) % 5
        b:SetPoint("TOP", i <= 5 and left or right, "BOTTOM", 0, -12 - row * 76)
    end
    for i = 1, MAX_RACES do
        if scale then _G[PREFIX .. i]:SetScale(scale) end
    end
end
MOCK.raceGlues["custom-offsets"] = {
    kind = "custom", count = 10, keepsOwn = true, left = { 1, 2, 3, 4, 5 }, column = { 7, 8, 9, 10, 11, 12 },
    added = { [11] = { "TOP", "BleakTestHordeHeader", "BOTTOM", 0, -12 - 5 * 76 },
              [12] = { "TOP", "BleakTestHordeHeader", "BOTTOM", 0, -12 - 6 * 76 } },
    buttons = function() offsetColumns() end,
}
MOCK.raceGlues["custom-scaled"] = {
    kind = "custom", count = 10, keepsOwn = true, left = { 1, 2, 3, 4, 5 }, column = { 7, 8, 9, 10, 11, 12 },
    scale = 1.6,
    added = { [11] = { "TOP", "BleakTestHordeHeader", "BOTTOM", 0, -12 - 5 * 76 },
              [12] = { "TOP", "BleakTestHordeHeader", "BOTTOM", 0, -12 - 6 * 76 } },
    buttons = function() offsetColumns(1.6) end,
}

-- Each button fills a slot frame of the screen (SetAllPoints); the slots hang from the headers, each 14 under the one
-- before: the step is the slots', not the buttons' own anchors'.
MOCK.raceGlues["custom-slots"] = {
    kind = "custom", count = 10, keepsOwn = true, left = { 1, 2, 3, 4, 5 }, column = { 7, 8, 9, 10, 11, 12 },
    added = { [11] = { { "TOPLEFT", PREFIX .. "10", "TOPLEFT", 0, -78 },
                       { "BOTTOMRIGHT", PREFIX .. "10", "BOTTOMRIGHT", 0, -78 } },
              [12] = { { "TOPLEFT", PREFIX .. "11", "TOPLEFT", 0, -78 },
                       { "BOTTOMRIGHT", PREFIX .. "11", "BOTTOMRIGHT", 0, -78 } } },
    buttons = function()
        portraitTemplate(64)
        local left, right = headers()
        for i = 1, 10 do
            local slot = CreateFrame("Frame", "BleakTestSlot" .. i, CharacterCreate)
            slot:SetSize(64, 64)
            local point = i <= 5 and "TOPLEFT" or "TOPRIGHT"
            local below = i <= 5 and "BOTTOMLEFT" or "BOTTOMRIGHT"
            if i == 1 or i == 6 then slot:SetPoint(point, i == 1 and left or right, below, i == 1 and 10 or -10, -12)
            else slot:SetPoint(point, _G["BleakTestSlot" .. (i - 1)], below, 0, -14) end
            button(i, CharacterCreate):SetAllPoints(slot)
        end
    end,
}

-- Each button anchored TOP to a row frame of its own; the rows hang from the headers 78 apart.
MOCK.raceGlues["custom-rows"] = {
    kind = "custom", count = 10, keepsOwn = true, left = { 1, 2, 3, 4, 5 }, column = { 7, 8, 9, 10, 11, 12 },
    added = { [11] = { "TOP", PREFIX .. "10", "TOP", 0, -78 }, [12] = { "TOP", PREFIX .. "11", "TOP", 0, -78 } },
    buttons = function()
        portraitTemplate(64)
        local left, right = headers()
        for i = 1, 10 do
            local row = CreateFrame("Frame", "BleakTestRow" .. i, CharacterCreate)
            row:SetSize(220, 64)
            row:SetPoint("TOP", i <= 5 and left or right, "BOTTOM", 0, -12 - ((i - 1) % 5) * 78)
            button(i, CharacterCreate):SetPoint("TOP", row, "TOP", 0, 0)
        end
    end,
}

-- The stock template and parent, anchored TOP to the parent as the stock buttons 1 and 6 are, at other offsets.
MOCK.raceGlues["custom-parent"] = {
    kind = "custom", count = 10, keepsOwn = true, left = { 1, 2, 3, 4, 5 }, column = { 7, 8, 9, 10, 11, 12 },
    added = { [11] = { "TOP", "CharacterCreateRaceFrame", "TOP", 60, -40 - 5 * 50 },
              [12] = { "TOP", "CharacterCreateRaceFrame", "TOP", 60, -40 - 6 * 50 } },
    buttons = function(raceFrame)
        for i = 1, 10 do
            local b = button(i, raceFrame)
            local row = (i - 1) % 5
            b:SetPoint("TOP", raceFrame, "TOP", i <= 5 and -60 or 60, -40 - row * 50)
        end
    end,
}

-- Six Alliance buttons and one Horde button: the Horde column has a single button to continue from.
MOCK.raceGlues["custom-seven"] = {
    kind = "custom", count = 7, keepsOwn = true, left = { 1, 2, 3, 4, 5, 6 }, column = { 7, 8, 9, 10, 11, 12 },
    added = { [8] = { "TOPRIGHT", "BleakTestHordeHeader", "BOTTOMRIGHT", -10, -12 - 1 * 72 },
              [12] = { "TOPRIGHT", "BleakTestHordeHeader", "BOTTOMRIGHT", -10, -12 - 5 * 72 } },
    buttons = function()
        portraitTemplate(64)
        chainColumns(6, 1, 14)
    end,
}

-- Twelve buttons already: nothing to add, nothing to place.
MOCK.raceGlues["custom-full"] = {
    kind = "custom", count = 12, keepsOwn = true, left = { 1, 2, 3, 4, 5, 6 }, column = { 7, 8, 9, 10, 11, 12 },
    added = {},
    buttons = function()
        portraitTemplate(64)
        chainColumns(6, 6, 14)
    end,
}

-- A template of the screen's own with parts its code finds by name (regions, and child frames with regions of their
-- own: a selection ring frame, a portrait model), unnamed parts, and that code. In custom-template the stock template
-- is gone (the added buttons are plain CheckButtons); in custom-template-stock it is still there, but the screen's
-- buttons are made from its own.
local function portraitScreen(keepStockTemplate)
    if not keepStockTemplate then MOCK.templates.CharacterCreateRaceButtonTemplate = nil end
    MOCK.addFile("Interface\\Glues\\BleakTest\\Ring")
    MOCK.addFile("Interface\\Glues\\BleakTest\\Glow")
    MOCK.addFile("Interface\\Glues\\BleakTest\\Hover")
    for _, file in ipairs({ "Human", "Dwarf", "NightElf", "Gnome", "Draenei", "HighElf", "Orc", "Scourge", "Tauren",
                            "Troll", "BloodElf", "Eredar" }) do
        MOCK.addFile("Interface\\Glues\\BleakTest\\Portraits\\" .. file)
    end
    MOCK.templates.BleakTestPortraitTemplate = function(b, name)
        b:SetSize(72, 72)
        local portrait = b:CreateTexture(name .. "Portrait", "ARTWORK")
        portrait:SetSize(64, 64)
        portrait:SetPoint("CENTER", b, "CENTER", 0, 0)
        local ring = b:CreateTexture(name .. "Ring", "OVERLAY")
        ring:SetTexture("Interface\\Glues\\BleakTest\\Ring")
        ring:SetSize(84, 84)
        ring:SetPoint("CENTER", portrait, "CENTER", 0, 0)
        local glow = b:CreateTexture(nil, "BACKGROUND")
        glow:SetTexture("Interface\\Glues\\BleakTest\\Glow")
        glow:SetAllPoints(b)
        local label = b:CreateFontString(name .. "Name", "ARTWORK")
        label:SetPoint("TOP", b, "BOTTOM", 0, -2)
        -- <Frames>: a selection ring with a glow of its own, a model over the portrait, an unnamed sparkle frame
        local selection = CreateFrame("Frame", name .. "Selection", b)
        selection:SetSize(90, 90)
        selection:SetPoint("CENTER", portrait, "CENTER", 0, 0)
        selection:SetFrameLevel(b:GetFrameLevel() + 2)
        local selectionGlow = selection:CreateTexture(name .. "SelectionGlow", "OVERLAY")
        selectionGlow:SetTexture("Interface\\Glues\\BleakTest\\Glow")
        selectionGlow:SetAllPoints(selection)
        selection:Hide()
        local model = CreateFrame("Model", name .. "Model", b)
        model:SetAllPoints(portrait)
        local sparkle = CreateFrame("Frame", nil, b)
        sparkle:SetSize(16, 16)
        sparkle:SetPoint("TOPRIGHT", ring, "TOPRIGHT", 0, 0)
        local spark = sparkle:CreateTexture(nil, "OVERLAY")
        spark:SetTexture("Interface\\Glues\\BleakTest\\Glow")
        spark:SetAllPoints(sparkle)
        b:SetHighlightTexture("Interface\\Glues\\BleakTest\\Hover", "ADD")
        b:SetScript("OnClick", function(self) if self.enable then CharacterRace_OnClick(self, self:GetID()) end end)
    end
    chainColumns(5, 5, 16, "BleakTestPortraitTemplate")
end

local function portraitScripts()
    function CharacterCreateEnumerateRaces(...)
        CharacterCreate.numRaces = select("#", ...) / 3
        if CharacterCreate.numRaces > MAX_RACES then message("Too many races!  Update MAX_RACES"); return end
        local index = 1
        for i = 1, select("#", ...), 3 do
            local b = _G[PREFIX .. index]
            local file = select(i + 1, ...)
            _G[b:GetName() .. "Portrait"]:SetTexture("Interface\\Glues\\BleakTest\\Portraits\\" .. file)
            _G[b:GetName() .. "Model"]:SetModel("Character\\" .. file .. "\\Portrait.m2")
            _G[b:GetName() .. "Name"]:SetText(select(i, ...))
            b.enable = select(i + 2, ...) == 1
            b.name = select(i, ...)
            b:Show()
            index = index + 1
        end
        for i = CharacterCreate.numRaces + 1, MAX_RACES do _G[PREFIX .. i]:Hide() end
    end
    function SetCharacterRace(id)
        CharacterCreate.selectedRace = id
        for i = 1, CharacterCreate.numRaces do
            _G[PREFIX .. i]:SetChecked(i == id and 1 or 0)
            _G[PREFIX .. i .. "Ring"]:SetVertexColor(1, i == id and 0.8 or 1, 1)
            local selection = _G[PREFIX .. i .. "Selection"]
            if i == id then selection:Show() else selection:Hide() end
            _G[PREFIX .. i .. "SelectionGlow"]:SetVertexColor(1, 0.8, 0.2)
        end
        local race, fileString = GetNameForRace()
        CharacterCreateRaceLabel:SetText(race)
        local text = GetFlavorText("RACE_INFO_" .. string.upper(fileString), GetSelectedSex())
        CharacterCreateRaceText:SetText(text .. "|n|n")
        SetBackgroundModel(CharacterCreate, GetCreateBackgroundModel())
    end
end

MOCK.raceGlues["custom-template"] = {
    kind = "custom", count = 10, keepsOwn = true, left = { 1, 2, 3, 4, 5 }, column = { 7, 8, 9, 10, 11, 12 },
    parts = { whole = true },
    added = { [11] = { "TOPRIGHT", PREFIX .. "10", "BOTTOMRIGHT", 0, -16 },
              [12] = { "TOPRIGHT", PREFIX .. "11", "BOTTOMRIGHT", 0, -16 } },
    buttons = function() portraitScreen(false) end,
    scripts = portraitScripts,
}
MOCK.raceGlues["custom-template-stock"] = {
    kind = "custom", count = 10, keepsOwn = true, left = { 1, 2, 3, 4, 5 }, column = { 7, 8, 9, 10, 11, 12 },
    parts = { whole = false },
    added = { [11] = { "TOPRIGHT", PREFIX .. "10", "BOTTOMRIGHT", 0, -16 },
              [12] = { "TOPRIGHT", PREFIX .. "11", "BOTTOMRIGHT", 0, -16 } },
    buttons = function() portraitScreen(true) end,
    scripts = portraitScripts,
}

-- The screen's own code lays every shown button out by faction each time it lists the races (the buttons added for
-- it too): Alliance from the left header, Horde from the right one, 72 apart.
local function ownLayoutAnchor(i)
    local _, faction = GetFactionForRace(i)
    local row = 0
    for j = 1, i do if select(2, GetFactionForRace(j)) == faction then row = row + 1 end end
    if faction == "Horde" then
        return { "TOPRIGHT", "BleakTestHordeHeader", "BOTTOMRIGHT", -10, -12 - (row - 1) * 72 }
    end
    return { "TOPLEFT", "BleakTestAllianceHeader", "BOTTOMLEFT", 10, -12 - (row - 1) * 72 }
end
MOCK.raceGlues["custom-ownlayout"] = {
    kind = "custom", count = 10, keepsOwn = false, left = { 1, 2, 3, 4, 5, 6 }, column = { 7, 8, 9, 10, 11, 12 },
    ownLayout = ownLayoutAnchor,
    added = {},
    buttons = function()
        portraitTemplate(64)
        chainColumns(5, 5, 14)
    end,
    scripts = function()
        local stockEnumerate = CharacterCreateEnumerateRaces
        function CharacterCreateEnumerateRaces(...)
            stockEnumerate(...)
            for i = 1, CharacterCreate.numRaces do
                local b, a = _G[PREFIX .. i], ownLayoutAnchor(i)
                b:ClearAllPoints()
                b:SetPoint(a[1], _G[a[2]], a[3], a[4], a[5])
            end
        end
    end,
}

-- The stock layout, nudged by a unit or so (rounding, or a patch that moves it a little): still the stock screen.
MOCK.raceGlues["races12-nudged"] = {
    kind = "stock", count = 10, keepsOwn = false, left = { 1, 2, 3, 4, 5, 6 }, column = { 7, 8, 9, 10, 11, 12 },
    added = {}, x = { Alliance = -51, Horde = 51.5 }, y = -60, gap = 21.5,
    buttons = function(raceFrame)
        for i = 1, 10 do
            local b = button(i, raceFrame)
            if i == 1 then b:SetPoint("TOP", raceFrame, "TOP", -51, -60)
            elseif i == 6 then b:SetPoint("TOP", raceFrame, "TOP", 51.5, -60)
            else b:SetPoint("TOPLEFT", _G[PREFIX .. (i - 1)], "BOTTOMLEFT", 0.5, -21.5) end
        end
    end,
}

-- The stock layout with every button enlarged (the screen's OnLoad scales its ten buttons): still the stock screen,
-- and the added buttons take the same scale.
MOCK.raceGlues["races12-scaled"] = {
    kind = "stock", count = 10, keepsOwn = false, left = { 1, 2, 3, 4, 5, 6 }, column = { 7, 8, 9, 10, 11, 12 },
    added = {}, x = { Alliance = -50, Horde = 50 }, y = -61, gap = 21, scale = 1.25,
    buttons = function(raceFrame)
        for i = 1, 10 do
            local b = button(i, raceFrame)
            if i == 1 then b:SetPoint("TOP", raceFrame, "TOP", -50, -61)
            elseif i == 6 then b:SetPoint("TOP", raceFrame, "TOP", 50, -61)
            else b:SetPoint("TOPLEFT", _G[PREFIX .. (i - 1)], "BOTTOMLEFT", 0, -21) end
        end
        for i = 1, MAX_RACES do _G[PREFIX .. i]:SetScale(1.25) end
    end,
}
