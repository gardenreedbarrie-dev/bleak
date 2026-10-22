-- Bleakhold glue: first and last names.
--
-- The server's mod-two-names accepts "First Last" character names. The client side needs no Wow.exe patch here:
-- ClientServices::CharacterValidateName leaves the check to the server (BLEAKHOLD(names)). This file splits the
-- stock name box into a First Name box and a Last Name box and joins the two for every stock call to
-- CreateCharacter (CharacterCreate_Okay and the paid-service confirmation both pass the first box's text). The
-- last name is optional, so single names keep working. With BLEAKHOLD_TWO_NAMES = false the stock box is kept.

local BH = BleakholdGlue

BH.NAME_BOX_WIDTH = 130
BH.NAME_BOX_GAP = 4
BH.NAME_PART_LETTERS = 12
-- 12 + space + 12, mod-two-names' default TwoNames.MaxNameLength.
BH.FULL_NAME_LETTERS = 25

local LAST_NAME_EDIT = "BleakholdLastNameEdit"

-- ------------------------------------------------------------------------------------------------- names

function BH.Trim(text)
    return (string.gsub(text or "", "^%s*(.-)%s*$", "%1"))
end

-- The first `letters` letters of `text` (UTF-8 aware, like the edit boxes' letter limit).
function BH.Utf8Truncate(text, letters)
    local out, count = {}, 0

    for char in string.gmatch(text, "[%z\1-\127\194-\244][\128-\191]*") do
        if count >= letters then
            break
        end

        count = count + 1
        out[count] = char
    end

    return table.concat(out)
end

-- "First Last" -> "First", "Last"; one word -> word, "". Extra words stay in the last name.
function BH.SplitName(name)
    name = BH.Trim(name)
    local first, last = string.match(name, "^(%S+)%s+(.+)$")

    if not first then
        return name, ""
    end

    return first, (string.gsub(last, "%s+", " "))
end

local function lastNameBox()
    local box = _G[LAST_NAME_EDIT]
    return box and box:IsShown() and box or nil
end

-- The name CreateCharacter should get for `name`: when `name` is the first name box's text, the last name box's
-- text is added after a space. Anything else is passed on unchanged.
function BH.FullName(name)
    local firstBox = CharacterCreateNameEdit
    local lastBox = lastNameBox()

    if type(name) ~= "string" or not firstBox or not lastBox then
        return name
    end

    local first = BH.Trim(name)
    local last = BH.Trim(lastBox:GetText())

    if first == "" or last == "" or first ~= BH.Trim(firstBox:GetText()) then
        return name
    end

    return first .. " " .. last
end

function BH.SetFullName(name)
    local firstBox = CharacterCreateNameEdit
    local lastBox = _G[LAST_NAME_EDIT]

    if not firstBox or not lastBox then
        return
    end

    local first, last = BH.SplitName(name)
    firstBox:SetText(first)
    lastBox:SetText(last)
end

-- --------------------------------------------------------------------------------------------- surnames

-- Random surnames for the Randomize name button: a start and an end joined into one word, themed by race.
BH.SURNAME_PARTS = {
    HUMAN = { { "Ash", "Black", "Bright", "Crown", "Fair", "Gold", "Iron", "Raven", "Red", "Silver", "Stone", "West" },
              { "brook", "crest", "field", "ford", "hall", "helm", "mere", "ridge", "shield", "vale", "ward", "wood" } },
    DWARF = { { "Anvil", "Bronze", "Coal", "Copper", "Deep", "Fire", "Flint", "Granite", "Iron", "Stone", "Thunder" },
              { "beard", "brew", "delver", "fist", "forge", "grip", "hammer", "helm", "mantle", "vein" } },
    GNOME = { { "Bolt", "Cog", "Copper", "Fizzle", "Gear", "Gizmo", "Quick", "Spark", "Spring", "Tinker", "Wobble" },
              { "bang", "blast", "fuse", "gauge", "lever", "socket", "spanner", "spin", "sprocket", "wick" } },
    NIGHTELF = { { "Dawn", "Dusk", "Feather", "Leaf", "Mist", "Moon", "Night", "Rain", "Shadow", "Star", "Whisper" },
                 { "bough", "breeze", "fall", "glade", "gleam", "runner", "shade", "song", "strider", "wind" } },
    DRAENEI = { { "Aegis", "Bright", "Crystal", "Dawn", "Light", "Prism", "Star", "Sun", "Vel", "Zhaar" },
                { "aan", "anor", "forge", "glow", "heart", "mend", "oran", "seeker", "vein", "ward" } },
    ORC = { { "Bitter", "Blood", "Bone", "Dire", "Doom", "Gore", "Grim", "Iron", "Rage", "Skull", "War" },
            { "axe", "blade", "fang", "fist", "hide", "howl", "jaw", "maw", "scar", "song", "tusk" } },
    SCOURGE = { { "Ashen", "Bitter", "Bleak", "Bone", "Cold", "Crypt", "Dread", "Gloom", "Grave", "Grim", "Hollow" },
                { "bane", "born", "chill", "mourn", "shade", "shroud", "veil", "walker", "ward", "wither" } },
    TAUREN = { { "Bright", "Cloud", "Dawn", "Earth", "Iron", "Mist", "Plains", "Rain", "Sky", "Stone", "Thunder" },
               { "caller", "chaser", "hoof", "horn", "mane", "runner", "strider", "totem", "walker" } },
    TROLL = { { "Blood", "Dark", "Hex", "Jungle", "Loa", "Shadow", "Skull", "Spirit", "Tide", "Venom", "Zan" },
              { "caller", "fang", "jin", "mask", "spear", "stalker", "tusk", "walker", "weaver", "zul" } },
    BLOODELF = { { "Blaze", "Blood", "Bright", "Dawn", "Ember", "Flame", "Gold", "Phoenix", "Spell", "Sun" },
                 { "blade", "bloom", "fall", "glow", "leaf", "reaver", "spire", "strider", "ward", "weaver" } },
    HIGHELF = { { "Dawn", "High", "Light", "Silver", "Sky", "Spring", "Star", "Sun", "Swift", "White" },
                { "arrow", "bough", "brook", "leaf", "runner", "song", "spire", "strider", "ward", "wind" } },
    EREDAR = { { "Argus", "Dusk", "Fel", "Iron", "Night", "Rune", "Shadow", "Sol", "Void", "Zhar" },
               { "aar", "anar", "binder", "brand", "forge", "horn", "mantle", "oth", "scorn", "vanar" } },
}

local function validSurname(name)
    return string.len(name) <= BH.NAME_PART_LETTERS and not string.find(string.lower(name), "(%a)%1%1")
end

-- The race file name of the race the screen shows ("HIGHELF"), or nil.
local function selectedRaceFile()
    if not GetSelectedRace or not GetAvailableRaces then
        return nil
    end

    local index = GetSelectedRace()
    local file = index and select((index - 1) * 3 + 2, GetAvailableRaces())
    return type(file) == "string" and string.upper(file) or nil
end

function BH.RandomSurname(raceFile, random)
    random = random or math.random
    local parts = BH.SURNAME_PARTS[raceFile or ""] or BH.SURNAME_PARTS.HUMAN

    for _ = 1, 20 do
        local name = parts[1][random(#parts[1])] .. parts[2][random(#parts[2])]

        if validSurname(name) then
            return name
        end
    end

    return parts[1][1] .. parts[2][1]
end

-- --------------------------------------------------------------------------------------------------- boxes

-- Moves every anchor of `frame` that is relative to `from` onto `to`.
local function retarget(frame, from, to)
    if not frame or not frame.GetNumPoints then
        return
    end

    local points = {}

    for i = 1, frame:GetNumPoints() do
        points[i] = { frame:GetPoint(i) }
    end

    local changed = false

    for _, p in ipairs(points) do
        if p[2] == from then
            p[2] = to
            changed = true
        end
    end

    if changed then
        frame:ClearAllPoints()

        for _, p in ipairs(points) do
            frame:SetPoint(p[1], p[2], p[3], p[4], p[5])
        end
    end
end

local function copyFont(target, source)
    local fontObject = source.GetFontObject and source:GetFontObject()

    if fontObject then
        target:SetFontObject(fontObject)
        return
    end

    local file, size, flags = source:GetFont()

    if file then
        target:SetFont(file, size, flags)
    end
end

local function copyBackdrop(target, source)
    local backdrop = source:GetBackdrop()

    if not backdrop then
        return
    end

    target:SetBackdrop(backdrop)

    local r, g, b, a = source:GetBackdropColor()

    if r then
        target:SetBackdropColor(r, g, b, a)
    end

    r, g, b, a = source:GetBackdropBorderColor()

    if r then
        target:SetBackdropBorderColor(r, g, b, a)
    end
end

local function callGlobal(name)
    local fn = _G[name]

    if type(fn) == "function" then
        fn()
    end
end

-- The first name box takes a whole name (typed with a space, or pasted): the first word stays, the rest moves to
-- the last name box. A single word is kept to NAME_PART_LETTERS letters. Setting the text runs OnTextChanged
-- again; `splitting` keeps those calls out.
local splitting = false

local function splitFirstName(box, lastBox, text)
    if string.find(text, "%s") then
        local first, rest = BH.SplitName(text)
        box:SetText(BH.Utf8Truncate(first, BH.NAME_PART_LETTERS))

        if rest ~= "" and BH.Trim(lastBox:GetText()) == "" then
            lastBox:SetText((string.gsub(rest, "%s", "")))
        end

        if first ~= "" then
            lastBox:SetFocus()
        end
    else
        local first = BH.Utf8Truncate(text, BH.NAME_PART_LETTERS)

        if first ~= text then
            box:SetText(first)
        end
    end
end

local function removeSpaces(box, text)
    if string.find(text, "%s") then
        box:SetText((string.gsub(text, "%s", "")))
    end
end

local function guarded(fn, ...)
    if splitting then
        return
    end

    splitting = true
    local ok, err = pcall(fn, ...)
    splitting = false

    if not ok then
        error(err, 0)
    end
end

local function onFirstNameChanged(box)
    local lastBox = _G[LAST_NAME_EDIT]

    if lastBox then
        guarded(splitFirstName, box, lastBox, box:GetText() or "")
    end
end

local function onLastNameChanged(box)
    guarded(removeSpaces, box, box:GetText() or "")
end

local function createLastNameBox()
    local firstBox = CharacterCreateNameEdit
    local parent = firstBox:GetParent()
    local point, relativeTo, relativePoint, x, y = firstBox:GetPoint(1)

    if not point then
        return false
    end

    -- Takes the stock box's place, so the pair is centred where the single box was.
    local anchor = CreateFrame("Frame", "BleakholdNameAnchor", parent)
    anchor:SetWidth(firstBox:GetWidth())
    anchor:SetHeight(firstBox:GetHeight())
    anchor:SetPoint(point, relativeTo or parent, relativePoint or point, x or 0, y or 0)

    -- Shown at the end of installTwoNames, once CreateCharacter passes its text on.
    local lastBox = CreateFrame("EditBox", LAST_NAME_EDIT, parent)
    lastBox:Hide()
    lastBox:SetAutoFocus(false)
    lastBox:SetMaxLetters(BH.NAME_PART_LETTERS)
    lastBox:SetWidth(BH.NAME_BOX_WIDTH)
    lastBox:SetHeight(firstBox:GetHeight())
    copyFont(lastBox, firstBox)
    copyBackdrop(lastBox, firstBox)
    lastBox:SetTextInsets(firstBox:GetTextInsets())

    -- Room for a whole pasted name; onFirstNameChanged splits it.
    firstBox:SetMaxLetters(BH.FULL_NAME_LETTERS)
    firstBox:SetWidth(BH.NAME_BOX_WIDTH)
    firstBox:ClearAllPoints()
    firstBox:SetPoint("RIGHT", anchor, "CENTER", -BH.NAME_BOX_GAP / 2, 0)
    lastBox:SetPoint("LEFT", anchor, "CENTER", BH.NAME_BOX_GAP / 2, 0)

    -- The stock Randomize name button hangs under the name box: keep it under the pair.
    retarget(CharacterCreateRandomName, firstBox, anchor)

    -- The stock label (text NAME) becomes "First Name"; the last name box gets the same label.
    local label = BH.FindRegions(firstBox, "FontString", NAME)[1]

    if label then
        label:SetText(BLEAKHOLD_FIRST_NAME)
        label:SetWidth(BH.NAME_BOX_WIDTH)

        local lastLabel = lastBox:CreateFontString(LAST_NAME_EDIT .. "Label", "BACKGROUND")
        copyFont(lastLabel, label)
        lastLabel:SetWidth(BH.NAME_BOX_WIDTH)
        lastLabel:SetHeight(label:GetHeight())

        local labelPoint, _, labelRelativePoint, labelX, labelY = label:GetPoint(1)

        if labelPoint then
            lastLabel:SetPoint(labelPoint, lastBox, labelRelativePoint, labelX, labelY)
        else
            lastLabel:SetPoint("BOTTOM", lastBox, "TOP", 0, 0)
        end

        lastLabel:SetText(BLEAKHOLD_LAST_NAME)
    end

    -- SetCharacterRace colours every frame in this list with the faction backdrop.
    if type(FRAMES_TO_BACKDROP_COLOR) == "table" then
        table.insert(FRAMES_TO_BACKDROP_COLOR, LAST_NAME_EDIT)
    end

    BH.HookScript(firstBox, "OnTabPressed", function()
        lastBox:SetFocus()
    end)
    BH.HookScript(firstBox, "OnTextChanged", onFirstNameChanged)
    BH.HookScript(firstBox, "OnShow", function()
        lastBox:Show()
    end)
    BH.HookScript(firstBox, "OnHide", function()
        lastBox:Hide()
    end)

    lastBox:SetScript("OnTabPressed", function()
        firstBox:SetFocus()
    end)
    lastBox:SetScript("OnEnterPressed", function()
        callGlobal("CharacterCreate_Okay")
    end)
    lastBox:SetScript("OnEscapePressed", function()
        callGlobal("CharacterCreate_Back")
    end)
    lastBox:SetScript("OnTextChanged", onLastNameChanged)

    return true
end

-- --------------------------------------------------------------------------------------------- install

local function installTwoNames()
    if not BLEAKHOLD_TWO_NAMES or not CharacterCreateNameEdit or _G[LAST_NAME_EDIT] then
        return
    end

    if not createLastNameBox() then
        return
    end

    -- Every stock caller passes the first box's text; FullName adds the last name. A failure in FullName must
    -- never stop the stock call.
    local stockCreateCharacter = CreateCharacter

    if type(stockCreateCharacter) == "function" then
        CreateCharacter = function(name, ...)
            local ok, full = pcall(BH.FullName, name)
            return stockCreateCharacter(ok and full or name, ...)
        end
    end

    -- A paid change starts from the character's own name; a new character from empty boxes.
    BH.WrapGlobal("CharacterCreate_OnShow", nil, function()
        if PAID_SERVICE_TYPE and type(PaidChange_GetName) == "function" then
            BH.SetFullName(PaidChange_GetName())
        else
            _G[LAST_NAME_EDIT]:SetText("")
        end
    end)

    BH.HookScript(CharacterCreateRandomName, "OnClick", function()
        _G[LAST_NAME_EDIT]:SetText(BH.RandomSurname(selectedRaceFile()))
    end)

    -- Renaming takes the whole name in one box.
    if CharacterRenameEditBox and CharacterRenameEditBox.SetMaxLetters then
        CharacterRenameEditBox:SetMaxLetters(BH.FULL_NAME_LETTERS)
    end

    if CharacterCreateNameEdit:IsShown() then
        _G[LAST_NAME_EDIT]:Show()
    end
end

BH.Try(installTwoNames)

BH.FlushLoadErrors("BleakholdNames.lua")
