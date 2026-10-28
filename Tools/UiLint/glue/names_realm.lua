-- Stand-ins for a realm patch's own two-names character creation screen (a CharacterCreate.xml and .lua of its own
-- with a first and a last name box, like the Bleakhold realm's Patch-R.MPQ), written for this test. tests.lua picks
-- one by scenario name and runs its setup() after stock.lua, before the Bleakhold glue loads (the realm's XML makes
-- its frames at load), or on the screen's first show for the late one (its OnShow makes the box).
--
-- Each entry says what the test expects: why (a pattern BleakholdGlue.namesWhy must match) and last() (the screen's
-- own second name box, which its own CharacterCreate_Okay joins to the first).

MOCK.nameGlues = {}

-- The screen's own CharacterCreate_Okay: "First Last" from its two boxes (one word when the last is empty), the way
-- a two-names screen hands the name to the server.
local function realmOkay(lastBox)
    function CharacterCreate_Okay()
        local first = (string.gsub(CharacterCreateNameEdit:GetText(), "^%s*(.-)%s*$", "%1"))
        local last = (string.gsub(lastBox():GetText(), "^%s*(.-)%s*$", "%1"))
        CreateCharacter(last ~= "" and (first .. " " .. last) or first)
        PlaySound("gsCharacterCreationCreateChar")
    end
end

-- The stock box becomes the screen's First Name box, left of centre, with a label of its own.
local function relabelFirst()
    local box = CharacterCreateNameEdit
    box:ClearAllPoints()
    box:SetPoint("BOTTOMRIGHT", CharacterCreate, "BOTTOM", -60, 55)
    box:SetWidth(150)
    local label = select(1, box:GetRegions())
    label:SetText("First Name")
end

-- A second name box: the stock box's look, right of the first, Tab between the two.
local function secondBox(name, parent, labelText)
    local box = CreateFrame("EditBox", name, parent)
    box:SetSize(150, 40)
    box:SetPoint("LEFT", CharacterCreateNameEdit, "RIGHT", 120, 0)
    box:SetMaxLetters(12)
    box:SetFontObject(GlueEditBoxFont)
    box:SetBackdrop(CharacterCreateNameEdit:GetBackdrop())
    if labelText then
        local label = box:CreateFontString(nil, "BACKGROUND")
        label:SetFontObject(GlueFontNormalLarge)
        label:SetText(labelText)
        label:SetPoint("BOTTOM", box, "TOP", 0, -23)
    end
    box:SetScript("OnEnterPressed", function() CharacterCreate_Okay() end)
    return box
end

local function hint(text)
    local h = CharacterCreate:CreateFontString(nil, "ARTWORK")
    h:SetText(text)
    h:SetPoint("TOP", CharacterCreateNameEdit, "BOTTOM", 60, -2)
end

-- The usual shape: CharacterCreateLastNameEdit under CharacterCreate, labelled, with the screen's hint line.
MOCK.nameGlues["names-realm"] = {
    why = "edit box CharacterCreateLastNameEdit",
    last = function() return CharacterCreateLastNameEdit end,
    setup = function()
        relabelFirst()
        secondBox("CharacterCreateLastNameEdit", CharacterCreate, "Last Name")
        hint("First and last name, 2-12 letters each")
        realmOkay(function() return CharacterCreateLastNameEdit end)
    end,
}

-- A box whose name says nothing (CCField2), in a holder frame of the screen, without a label: found as an edit box of
-- the screen's own.
MOCK.nameGlues["names-realm-odd"] = {
    why = "edit box CCField2",
    last = function() return CCField2 end,
    setup = function()
        relabelFirst()
        local holder = CreateFrame("Frame", "CCNameHolder", CharacterCreate)
        holder:SetAllPoints(CharacterCreate)
        secondBox("CCField2", holder)
        realmOkay(function() return CCField2 end)
    end,
}

-- An unnamed box inside an unnamed frame of the screen.
MOCK.nameGlues["names-realm-unnamed"] = {
    why = "edit box %(no name%)",
    setup = function()
        relabelFirst()
        local holder = CreateFrame("Frame", nil, CharacterCreate)
        local box = secondBox(nil, holder)
        MOCK.realmUnnamedBox = box
        realmOkay(function() return MOCK.realmUnnamedBox end)
    end,
    last = function() return MOCK.realmUnnamedBox end,
}

-- The box hangs from GlueParent, not from the screen: its name gives it away (any case, with underscores).
MOCK.nameGlues["names-realm-outside"] = {
    why = "edit box TwoNames_SURNAME_Box",
    last = function() return TwoNames_SURNAME_Box end,
    setup = function()
        relabelFirst()
        secondBox("TwoNames_SURNAME_Box", GlueParent)
        realmOkay(function() return TwoNames_SURNAME_Box end)
    end,
}

-- Outside the screen and under a name that says nothing: only the screen's hint line tells.
MOCK.nameGlues["names-realm-hint"] = {
    why = "text \"First and last name, 2%-12 letters each\"",
    last = function() return BHTwoBox end,
    setup = function()
        relabelFirst()
        secondBox("BHTwoBox", GlueParent)
        hint("First and last name, 2-12 letters each")
        realmOkay(function() return BHTwoBox end)
    end,
}

-- The screen's OnShow makes its last name box the first time it shows.
MOCK.nameGlues["names-realm-late"] = {
    why = "edit box CharacterCreateSurnameEdit", late = true,
    last = function() return CharacterCreateSurnameEdit end,
    setup = function()
        relabelFirst()
        local stockOnShow = CharacterCreate_OnShow
        function CharacterCreate_OnShow()
            stockOnShow()
            if not CharacterCreateSurnameEdit then
                secondBox("CharacterCreateSurnameEdit", CharacterCreate, "Surname")
            end
        end
        realmOkay(function() return CharacterCreateSurnameEdit end)
    end,
}
