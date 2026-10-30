-- Bleakhold glue: first and last names.
--
-- The server's mod-two-names accepts "First Last" character names. The client side needs no Wow.exe patch here:
-- ClientServices::CharacterValidateName leaves the check to the server (BLEAKHOLD(names)). On the stock character
-- creation screen this file splits the stock name box into a First Name box and a Last Name box and joins the two
-- for every stock call to CreateCharacter (CharacterCreate_Okay and the paid-service confirmation both pass the
-- first box's text). The last name is optional, so single names keep working. With BLEAKHOLD_TWO_NAMES = false the
-- stock box is kept.
--
-- A realm patch can bring a character creation screen of its own that already has a first and a last name box (a
-- two-names screen): Bleakhold then adds no box, moves and restyles none of the screen's, and leaves the name its
-- code builds alone. The choice is made when the screen first shows (after the screen's own OnShow, so a box it
-- makes there counts too); BleakholdGlue.namesPath says which way it went ("bleakhold", "realm", "kept", "off"),
-- BleakholdGlue.namesWhy why, and BLEAKHOLD_GLUE_LOG keeps the line.

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

-- The character's own name while the name is locked (a paid customization, BH.NameLocked), else nil.
local function lockedName()
    if not BH.NameLocked() or type(PaidChange_GetName) ~= "function" then
        return nil
    end

    local name = PaidChange_GetName()
    return type(name) == "string" and name ~= "" and name or nil
end

-- The name CreateCharacter should get for `name`: when `name` is the first name box's text, the last name box's
-- text is added after a space. Anything else is passed on unchanged. While the name is locked it is the character's
-- own name.
function BH.FullName(name)
    local firstBox = CharacterCreateNameEdit
    local lastBox = lastNameBox()
    local locked = type(name) == "string" and lockedName()

    if locked then
        return locked
    end

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

-- ------------------------------------------------------------------------------------- the screen's own boxes

-- Words that name a second name box or its label, compared without case, spaces or punctuation ("Last Name",
-- "CharacterCreateLastNameEdit", "CC_Surname_Box", "First and last name, 2-12 letters each").
BH.SECOND_NAME_WORDS = { "lastname", "surname", "secondname", "familyname", "nachname" }

local function squash(text)
    return (string.gsub(string.lower(tostring(text or "")), "[^%w]", ""))
end

local function saysSecondName(text)
    local squashed = squash(text)

    for _, word in ipairs(BH.SECOND_NAME_WORDS) do
        if string.find(squashed, word, 1, true) then
            return true
        end
    end

    return false
end

-- The widget type of a frame or region, nil for anything else (any table of _G: nothing it does may stop the check).
local function objectType(object)
    if type(object) ~= "table" then
        return nil
    end

    local ok, kind = pcall(function()
        return type(object.GetObjectType) == "function" and object:GetObjectType() or nil
    end)
    return ok and kind or nil
end

local function isOurs(object)
    return object ~= nil and (object == _G[LAST_NAME_EDIT] or object == _G[LAST_NAME_EDIT .. "Label"])
end

-- Why the character creation screen already has a second name box of its own (a realm patch's two-names screen), as
-- a short text, or nil for the stock screen. A realm's frame names are not known here, so any of these tells:
--   1. an edit box among CharacterCreate's frames (at any depth) other than the stock name box and Bleakhold's;
--   2. an edit box anywhere whose global name says last name, surname, second or family name;
--   3. a text among CharacterCreate's frames that says so ("Last Name", "First and last name, ...").
function BH.ScreenSecondNameBox()
    local stockBox = CharacterCreateNameEdit
    local seen, label = {}, nil

    local function walk(frame, depth)
        if seen[frame] or depth > 16 then
            return nil
        end

        seen[frame] = true

        if frame ~= stockBox and not isOurs(frame) and objectType(frame) == "EditBox" then
            return "edit box " .. tostring(frame:GetName() or "(no name)")
        end

        if not label and type(frame.GetRegions) == "function" then
            for _, region in ipairs({ frame:GetRegions() }) do
                if not isOurs(region) and objectType(region) == "FontString" and saysSecondName(region:GetText()) then
                    label = "text \"" .. tostring(region:GetText()) .. "\""
                    break
                end
            end
        end

        if type(frame.GetChildren) == "function" then
            for _, child in ipairs({ frame:GetChildren() }) do
                local found = walk(child, depth + 1)

                if found then
                    return found
                end
            end
        end

        return nil
    end

    local screen = CharacterCreate or (stockBox and stockBox:GetParent())
    local found = screen and walk(screen, 0)

    if found then
        return found
    end

    for name, value in pairs(_G) do
        if type(name) == "string" and value ~= stockBox and not isOurs(value) and saysSecondName(name)
            and objectType(value) == "EditBox" then
            return "edit box " .. name
        end
    end

    return label
end

-- --------------------------------------------------------------------------------------------- install

local function setPath(path, why)
    BH.namesPath = path
    BH.namesWhy = why
    BH.Log("names: " .. path .. (why and (" (" .. why .. ")") or ""))
end

-- Bleakhold's boxes, once: the last name box, CreateCharacter passing "First Last", the Randomize surname.
local function installOurs()
    if not createLastNameBox() then
        return false
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

    BH.HookScript(CharacterCreateRandomName, "OnClick", function()
        _G[LAST_NAME_EDIT]:SetText(BH.RandomSurname(selectedRaceFile()))
    end)

    if CharacterCreateNameEdit:IsShown() then
        _G[LAST_NAME_EDIT]:Show()
    end

    return true
end

-- A paid change starts from the character's own name; a new character from empty boxes.
local function resetOurs()
    if PAID_SERVICE_TYPE and type(PaidChange_GetName) == "function" then
        BH.SetFullName(PaidChange_GetName())
    else
        _G[LAST_NAME_EDIT]:SetText("")
    end
end

-- Every show of the screen, after its own OnShow: the first one decides (the screen's boxes exist by then, also one
-- its OnShow makes), the later ones only reset Bleakhold's boxes.
local function onScreenShown()
    if BH.namesPath == "waiting" then
        setPath("deciding")
        local why = BH.ScreenSecondNameBox()

        if why then
            setPath("realm", "the screen has its own second name box: " .. why .. "; Bleakhold adds none")
        elseif installOurs() then
            setPath("bleakhold", "stock screen: Bleakhold's First Name and Last Name boxes")
        else
            setPath("kept", "the name box has no anchor to take: the single stock box stays")
        end
    end

    if BH.namesPath == "bleakhold" then
        resetOurs()
    end
end

local function installTwoNames()
    if not BLEAKHOLD_TWO_NAMES then
        setPath("off", "BLEAKHOLD_TWO_NAMES is off: the stock name box")
        return
    end

    if not CharacterCreateNameEdit then
        setPath("kept", "no CharacterCreateNameEdit on this screen")
        return
    end

    -- Renaming takes the whole name in one box (on any screen: the server takes "First Last").
    if CharacterRenameEditBox and CharacterRenameEditBox.SetMaxLetters and CharacterRenameEditBox.GetMaxLetters then
        local letters = CharacterRenameEditBox:GetMaxLetters() or 0

        if letters > 0 and letters < BH.FULL_NAME_LETTERS then
            CharacterRenameEditBox:SetMaxLetters(BH.FULL_NAME_LETTERS)
        end
    end

    setPath("waiting")
    BH.HookScript(CharacterCreate or CharacterCreateNameEdit:GetParent(), "OnShow", onScreenShown)

    -- Shown already (never at login, but a reload of the glue on that screen): decide now.
    local screen = CharacterCreate or CharacterCreateNameEdit:GetParent()

    if screen and screen.IsVisible and screen:IsVisible() then
        onScreenShown()
    end
end

BH.Try(installTwoNames)

-- ----------------------------------------------------------------------------------- paid customization

-- A paid customization (PAID_CHARACTER_CUSTOMIZATION, the Appearance Artist's change at login) keeps the name: the
-- server refuses a new one there (mod-bleakhold, Bleakhold.Appearance.AllowNameChange). With
-- BLEAKHOLD_LOCK_CUSTOMIZE_NAME the name boxes are greyed out, take neither the focus nor typing, the Randomize name
-- button is hidden under a short note, and CreateCharacter gets the character's own name, which the client sends
-- without a name check (CCharacterCreation::CreateCharacter). A race or faction change is left as it is.
function BH.NameLocked()
    return BLEAKHOLD_LOCK_CUSTOMIZE_NAME ~= false and PAID_SERVICE_TYPE ~= nil
        and PAID_SERVICE_TYPE == (PAID_CHARACTER_CUSTOMIZATION or 1)
end

local LOCK_NOTE = "BleakholdNameLockedNote"

local function lockedBoxes()
    local boxes = { CharacterCreateNameEdit }
    local lastBox = _G[LAST_NAME_EDIT]

    if lastBox then
        boxes[#boxes + 1] = lastBox
    end

    return boxes
end

local function onLockedFocus(box)
    if box.bleakholdLocked then
        box:ClearFocus()
    end
end

-- Typing (userInput) puts the name back; the screen's own SetText (the paid name on the next show) is let through.
local function onLockedText(box, userInput)
    local text = box.bleakholdLocked

    if userInput and text and box:GetText() ~= text then
        box:SetText(text)
    end
end

local function lockBox(box)
    if not box.bleakholdUnlocked then
        local r, g, b, a = box:GetTextColor()
        box.bleakholdUnlocked = { alpha = box:GetAlpha(), color = { r, g, b, a },
                                  autoFocus = box.IsAutoFocus and box:IsAutoFocus() }
        BH.HookScript(box, "OnEditFocusGained", onLockedFocus)
        BH.HookScript(box, "OnTextChanged", onLockedText)
    end

    box.bleakholdLocked = box:GetText() or ""
    box:ClearFocus()
    box:SetAutoFocus(false)
    box:EnableMouse(false)
    box:SetTextColor(0.5, 0.5, 0.5)
    box:SetAlpha(0.6)
end

local function unlockBox(box)
    local saved = box.bleakholdUnlocked

    if not saved or not box.bleakholdLocked then
        return
    end

    box.bleakholdLocked = nil
    box:EnableMouse(true)
    box:SetAlpha(saved.alpha or 1)

    if saved.color[1] then
        box:SetTextColor(saved.color[1], saved.color[2], saved.color[3], saved.color[4])
    end

    if saved.autoFocus ~= nil then
        box:SetAutoFocus(saved.autoFocus and true or false)
    end
end

local function lockNote()
    local note = _G[LOCK_NOTE]

    if not note then
        local holder = _G[LAST_NAME_EDIT] and BleakholdNameAnchor or CharacterCreateNameEdit
        note = CharacterCreateNameEdit:GetParent():CreateFontString(LOCK_NOTE, "OVERLAY")
        note:SetFontObject(GlueFontDisableSmall or GlueFontHighlightSmall or GlueEditBoxFont)
        note:SetTextColor(0.6, 0.6, 0.6)
        note:SetPoint("TOP", holder, "BOTTOM", 0, -2)
        note:SetText(BLEAKHOLD_CUSTOMIZE_NAME_LOCKED)
    end

    return note
end

-- Every show of the screen, after the names have been set: lock them on a paid customization, unlock otherwise.
function BH.ApplyNameLock()
    if not CharacterCreateNameEdit then
        return
    end

    local random = CharacterCreateRandomName

    if BH.NameLocked() then
        local name = lockedName()

        if name and BH.namesPath == "bleakhold" then
            BH.SetFullName(name)
        end

        for _, box in ipairs(lockedBoxes()) do
            lockBox(box)
        end

        if random then
            random.bleakholdWasShown = random.bleakholdWasShown or (random:IsShown() and true or false)
            random:Hide()
        end

        lockNote():Show()
        BH.nameLocked = true
    elseif BH.nameLocked then
        for _, box in ipairs(lockedBoxes()) do
            unlockBox(box)
        end

        if random and random.bleakholdWasShown then
            random:Show()
        end

        if random then
            random.bleakholdWasShown = nil
        end

        lockNote():Hide()
        BH.nameLocked = nil
    end
end

if CharacterCreateNameEdit then
    BH.HookScript(CharacterCreate or CharacterCreateNameEdit:GetParent(), "OnShow", BH.ApplyNameLock)
end

BH.FlushLoadErrors("BleakholdNames.lua")
