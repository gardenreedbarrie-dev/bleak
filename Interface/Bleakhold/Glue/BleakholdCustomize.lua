-- Bleakhold glue: the appearance rows of character creation and of the paid customization screen (the Appearance
-- Artist's change at login is the same CharacterCreate frame with PAID_SERVICE_TYPE set).
--
-- The stock rows CharacterCustomizationButtonFrame1..5 (skin, face, hair style, hair colour, features) stay as they are
-- and get, all in the stock look:
--   * "n/N" beside the row's name, coloured by the option's group (plain, marked, fel, Death Knight, glowing);
--   * the mouse wheel steps the row (wheel down: next), Shift-click on an arrow steps 5 at a time;
--   * a right-click on the row rolls only that row, and a lock (a small check box on the plate's left end) keeps
--     the row as it is when Randomize rolls the others.
-- When the realm's tables have the Bleakhold marks and eyes (Tools/RaceForge/README.md, "Bleakhold appearance data
-- contract": face = base + 40 * eye, features = look * B + base) and the client's walks match the generated data file
-- (BleakholdCustomizeData.lua: the face walk from each start skin, the skin walk with each face), three rows are added
-- beside them: Eyes, Markings and Mark Colour. The Face and Features rows then step the base face and the base feature
-- only, and the added rows step the eye, the design and the colour, each keeping the rest. Randomize leaves eyes and
-- markings alone unless their own row is unlocked or right-clicked. When the walks do not match (today's tables, an
-- older data file), the rows show the plain n/N of what the arrows reach and nothing is added.
--
-- Bleakhold.exe's glue functions (WoW/Source/Glue/CharacterCreation_Scripts.cpp), each checked before use; without
-- them (an older exe) only the mouse wheel and Shift-click are added, both through the stock CycleCharCustomization:
--   GetCharCustomizationInfo(row) -> position (1-based, in the order the arrows walk; 0 when the current value is off
--     that list), count, raw value; row 1-5
--   SetCharCustomizationRaw(row, raw): selects that raw value when the row's list has it (read back to confirm)
--   RandomizeCharCustomization([keepMask]): bit row - 1 set keeps that row
-- The console variable bleakCustomizeSelfTest (registered by the exe; 1: the screen's race, sex and class, 2: every
-- race, sex and class) walks every row through the arrows' own path when the screen shows and logs each row as OK or
-- with its mismatch: to BleakholdGlue.Customize.log, and to Logs\BleakholdCustomize.log through
-- BleakholdCustomize_Log(text) when the exe has that function.

local BH = BleakholdGlue
local C = {}
BH.Customize = C

C.SKIN, C.FACE, C.HAIR_STYLE, C.HAIR_COLOR, C.FEATURES = 1, 2, 3, 4, 5
C.EYES, C.MARKINGS, C.MARK_COLOUR = 6, 7, 8
C.STOCK_ROWS = 5
C.SHIFT_STEP = 5
C.ROW_PREFIX = "CharacterCustomizationButtonFrame"
C.ROW_TEMPLATE = "CharacterCustomizationFrameTemplate"
-- Space between the stock rows and the added column, in UI units.
C.COLUMN_GAP = 24
-- How often the rows are read again while the screen shows (the stock code changes them behind the UI's back:
-- a class or sex change, a skin step that has to change the face), in seconds.
C.POLL = 0.25
C.SELF_TEST_CVAR = "bleakCustomizeSelfTest"

-- The colour of a row's number by the option's group (the curation's skin groups; marks and eyes that glow).
C.COLORS = {
    plain = { 1, 1, 1 },
    marked = { 1, 0.82, 0 },
    fel = { 0.45, 1, 0.2 },
    deathknight = { 0.77, 0.12, 0.23 },
    glowing = { 0.4, 0.85, 1 },
}

-- The rows Bleakhold adds: their frame name, label and the native row they are part of.
C.VIRTUAL = {
    [6] = { key = "Eyes", physical = 2, label = function() return BLEAKHOLD_CUSTOMIZE_EYES end },
    [7] = { key = "Markings", physical = 5, label = function() return BLEAKHOLD_CUSTOMIZE_MARKINGS end },
    [8] = { key = "MarkColour", physical = 5, label = function() return BLEAKHOLD_CUSTOMIZE_MARK_COLOUR end },
}

-- Locks for this session (glue has no saved variables). The added rows start locked: Randomize leaves eyes and
-- markings alone until their lock is cleared.
C.locks = { [6] = true, [7] = true, [8] = true }
-- race:sex:kind -> true once the data and the tables were found to disagree (plain rows from then on).
C.stale = {}
C.logged = {}
C.rows = {}
C.selfTestLog = {}

local floor, abs = math.floor, math.abs

-- ------------------------------------------------------------------------------------------------- logging

-- The rows' own log (BleakholdGlue.Customize.log, oldest first), also in Logs\BleakholdCustomize.log when the exe has
-- BleakholdCustomize_Log. Kept out of BLEAKHOLD_GLUE_LOG, which holds the screens' path decisions.
C.log = {}

function C.Log(text)
    text = "customize: " .. tostring(text)
    C.log[#C.log + 1] = text

    if type(BleakholdCustomize_Log) == "function" then
        pcall(BleakholdCustomize_Log, text)
    end
end

local function logOnce(key, text)
    if not C.logged[key] then
        C.logged[key] = true
        C.Log(text)
    end
end

-- -------------------------------------------------------------------------------------------- the natives

function C.HasNatives()
    return type(GetCharCustomizationInfo) == "function" and type(SetCharCustomizationRaw) == "function"
end

-- position, count, raw of a stock row, or nil.
function C.NativeInfo(row)
    if type(GetCharCustomizationInfo) ~= "function" then
        return nil
    end

    local ok, pos, count, raw = pcall(GetCharCustomizationInfo, row)

    if ok and type(pos) == "number" and type(count) == "number" and type(raw) == "number" and count > 0 then
        return pos, count, raw
    end

    return nil
end

local function cycle(row, delta)
    local step = delta > 0 and 1 or -1

    for _ = 1, abs(delta) do
        CycleCharCustomization(row, step)
    end
end

-- Selects `raw` on a stock row and reads it back. A value the client does not take means the data file and the
-- tables disagree: that race, sex and class falls back to plain rows for the rest of the session.
function C.SetRaw(row, raw, state)
    pcall(SetCharCustomizationRaw, row, raw)
    local _, _, now = C.NativeInfo(row)

    if now == raw then
        return true
    end

    if state and state.key then
        C.stale[state.key] = true
    end

    C.Log(string.format("%s: row %d did not take %d (it has %s); the data does not match the tables, plain rows "
        .. "from now on", state and state.key or "?", row, raw, tostring(now)))
    return false
end

-- ---------------------------------------------------------------------------------------------- the data

-- The screen's race file (ChrRaces clientFileString), sex as in the DBCs (0 male, 1 female) and whether the class is
-- a Death Knight.
function C.Context()
    local raceFile, sex, dk

    if type(GetNameForRace) == "function" then
        local ok, _, file = pcall(GetNameForRace)
        raceFile = ok and file or nil
    end

    if type(GetSelectedSex) == "function" then
        sex = GetSelectedSex() == (SEX_FEMALE or 3) and 1 or 0
    end

    if type(GetSelectedClass) == "function" then
        local ok, _, classFile = pcall(GetSelectedClass)
        dk = ok and classFile == "DEATHKNIGHT"
    end

    return raceFile, sex, dk and true or false
end

-- The data file's block of a race and sex, or nil.
function C.Entry(raceFile, sex)
    local data = BleakholdCustomizeData

    if type(data) ~= "table" or data.version ~= 1 or type(data.races) ~= "table" or type(raceFile) ~= "string" then
        return nil
    end

    local race = data.races[raceFile]

    if race == nil then
        local wanted = string.lower(raceFile)

        for key, value in pairs(data.races) do
            if type(key) == "string" and string.lower(key) == wanted then
                race = value
                break
            end
        end
    end

    local entry = type(race) == "table" and race[sex] or nil
    return type(entry) == "table" and entry or nil
end

-- A count of the data file: a number, or { default = n, [raw] = m }.
function C.CountOf(value, key)
    if type(value) == "number" then
        return value
    end

    if type(value) == "table" then
        return tonumber(key ~= nil and value[key]) or tonumber(value.default)
    end

    return nil
end

local function contains(list, value)
    for _, v in ipairs(list) do
        if v == value then
            return true
        end
    end

    return false
end

local function indexOf(list, value)
    for i, v in ipairs(list) do
        if v == value then
            return i
        end
    end

    return nil
end

-- The base faces of a face set (ascending) and the eyes a base has in it (ascending, 0 first).
function C.FaceBases(set, stride)
    local seen, out = {}, {}

    for _, v in ipairs(set) do
        local base = v % stride

        if not seen[base] then
            seen[base] = true
            out[#out + 1] = base
        end
    end

    table.sort(out)
    return out
end

function C.EyesOf(set, stride, base)
    local out = {}

    for _, v in ipairs(set) do
        if v % stride == base then
            out[#out + 1] = floor(v / stride)
        end
    end

    table.sort(out)
    return out
end

-- Whether a list of the data (raw values, ascending) is the walk a native row reports: as many values, and the row's
-- raw value at the row's place.
function C.Fits(list, r)
    return type(list) == "table" and type(r) == "table" and #list == r.count and r.pos > 0 and list[r.pos] == r.raw
end

-- The face arrows' walk (raw faces, ascending) the native Face row is on. CycleCharCustomization starts the face loop
-- at the last skin chosen with the skin row (m_prevSkinIndex), which the glue cannot read: it is the current skin
-- unless a face step changed the skin since, so the current skin's walk comes first, then the one walk of the data
-- that fits. nil when none fits or more than one does.
function C.FaceWalk(view, face, skinRaw)
    local walks = view.faceWalks

    if type(walks) ~= "table" or type(face) ~= "table" then
        return nil
    end

    local own = walks[C.CountOf(view.faceWalkOfSkin, skinRaw) or -1]

    if C.Fits(own, face) then
        return own
    end

    local found

    for _, walk in ipairs(walks) do
        if C.Fits(walk, face) then
            if found then
                return nil
            end

            found = walk
        end
    end

    return found
end

-- The skin arrows' walk (raw skins, ascending) with a face: the skins that fit it.
function C.SkinWalk(view, faceRaw)
    if type(view.skinSets) ~= "table" or faceRaw == nil then
        return nil
    end

    local set = view.skinSets[C.CountOf(view.skinSetOfFace, faceRaw) or -1]
    return type(set) == "table" and set or nil
end

-- look = looksPerDesign * (design - 1) + colour; look 0 is no mark.
function C.LookOf(design, colour, perDesign)
    if not design or design == 0 then
        return 0
    end

    return perDesign * (design - 1) + colour
end

function C.DesignOf(look, perDesign)
    if look == 0 then
        return 0, nil
    end

    return floor((look - 1) / perDesign) + 1, (look - 1) % perDesign + 1
end

-- Whether mark colour `colour` glows: the data's colourGlows when it has one, otherwise every colour but the last
-- (the contract: colour 3 is the race's paint colour and never has a _Glow file).
function C.ColourGlows(entry, colour)
    if type(entry.colourGlows) == "table" and entry.colourGlows[colour] ~= nil then
        return entry.colourGlows[colour] and true or false
    end

    return colour ~= nil and type(entry.colours) == "table" and colour < #entry.colours
end

-- ------------------------------------------------------------------------------------------------- state

-- Everything the rows show, from the natives and the data file:
--   natives, rows[1..5] = { pos, count, raw }, raceFile, sex, dk, key, entry, view,
--   fresh (the skin walk is the data's: groups apply; skinWalk), eyes (the Eyes row is live: faceWalk, stride,
--   faceBase, eye),
--   marks (the mark rows are live: B, looks, perDesign, featureBase, look, design, colour)
function C.Read()
    local s = { natives = C.HasNatives(), rows = {} }

    if not s.natives then
        return s
    end

    for row = 1, C.STOCK_ROWS do
        local pos, count, raw = C.NativeInfo(row)

        if pos then
            s.rows[row] = { pos = pos, count = count, raw = raw }
        end
    end

    s.raceFile, s.sex, s.dk = C.Context()
    local entry = C.Entry(s.raceFile, s.sex)
    local view = entry and (s.dk and entry.deathKnight or entry.normal)

    if type(view) ~= "table" then
        return s
    end

    s.key = tostring(s.raceFile) .. ":" .. tostring(s.sex) .. ":" .. (s.dk and "deathknight" or "normal")
    s.entry, s.view = entry, view

    if C.stale[s.key] then
        return s
    end

    local data = BleakholdCustomizeData
    local skin, face, features = s.rows[C.SKIN], s.rows[C.FACE], s.rows[C.FEATURES]

    -- Skin groups: the skin arrows reach the skins that fit the current face (a Death Knight face keeps to the Death
    -- Knight skins, the others to the rest).
    if skin and face then
        local set = C.SkinWalk(view, face.raw)

        if C.Fits(set, skin) then
            s.fresh, s.skinWalk = true, set
        else
            logOnce(s.key .. ":skins:" .. skin.count, string.format("%s: %d skins with face %d (now %d), the data has "
                .. "%s: no skin groups", s.key, skin.count, face.raw, skin.raw, set and #set or "none"))
        end
    end

    -- Eyes: the face walk holds every raw face the arrows reach (on every skin) once the eye rows are in the tables.
    local stride = tonumber(data.eyeStride) or 40
    s.stride = stride

    if face and skin and type(view.faceWalks) == "table" then
        local walk = C.FaceWalk(view, face, skin.raw)

        if walk and walk[#walk] >= stride then
            s.eyes, s.faceWalk = true, walk
            s.faceBase, s.eye = face.raw % stride, floor(face.raw / stride)
        elseif not walk then
            local own = view.faceWalks[C.CountOf(view.faceWalkOfSkin, skin.raw) or -1]
            local below = 0

            for _, v in ipairs(type(own) == "table" and own or {}) do
                if v < stride then
                    below = below + 1
                end
            end

            -- the same walk without its eye values: the tables have no eye rows yet (stage 1), as expected
            if face.count ~= below then
                logOnce(s.key .. ":faces:" .. face.count, string.format("%s: %d faces from skin %d, the data has %s "
                    .. "(%d without eye colours): no Eyes row", s.key, face.count, skin.raw,
                    type(own) == "table" and #own or "none", below))
            end
        end
    end

    -- Marks: looks * B features once the mark rows are in the tables, B before.
    local B, looks = tonumber(entry.B), tonumber(entry.looks) or 1
    local perDesign = tonumber(data.looksPerDesign) or 3
    local designs, colours = entry.designs, entry.colours

    if features and B and B > 0 and looks > 1 and type(designs) == "table" and type(colours) == "table"
        and #colours == perDesign and looks == 1 + #designs * perDesign then
        local hairColor = s.rows[C.HAIR_COLOR] and s.rows[C.HAIR_COLOR].raw
        local expected = C.CountOf(view.features, hairColor)

        local all = looks * B

        if features.count == all and (expected == nil or expected == features.count) and features.raw < all then
            s.marks, s.B, s.looks, s.perDesign = true, B, looks, perDesign
            s.featureBase, s.look = features.raw % B, floor(features.raw / B)
            s.design, s.colour = C.DesignOf(s.look, perDesign)
        elseif features.count ~= B then
            logOnce(s.key .. ":features:" .. features.count, string.format("%s: %d features, the data has %s "
                .. "(B %d): no mark rows", s.key, features.count, tostring(expected), B))
        end
    end

    return s
end

-- What a row shows: position, count, group (a key of C.COLORS), active (false: greyed, its arrows off); nil when
-- the row has nothing to show.
function C.Label(s, row)
    local r = s.rows[row]

    if row == C.SKIN and r then
        local group = "plain"

        if s.fresh and type(s.entry.skinGroup) == "table" then
            local groups = BleakholdCustomizeData.groups
            local code = s.entry.skinGroup[r.raw]
            group = type(groups) == "table" and groups[code] or "plain"
        end

        return r.pos, r.count, C.COLORS[group] and group or "plain", true
    elseif row == C.FACE and r then
        if s.eyes then
            local bases = C.FaceBases(s.faceWalk, s.stride)
            return indexOf(bases, s.faceBase) or 1, #bases, "plain", true
        end

        return r.pos, r.count, "plain", true
    elseif row == C.FEATURES and r then
        if s.marks then
            return s.featureBase + 1, s.B, "plain", true
        end

        return r.pos, r.count, "plain", true
    elseif row == C.EYES and s.eyes then
        local eyes = C.EyesOf(s.faceWalk, s.stride, s.faceBase)
        return indexOf(eyes, s.eye) or 1, #eyes, s.eye > 0 and "glowing" or "plain", true
    elseif row == C.MARKINGS and s.marks then
        local group = s.design == 0 and "plain" or (C.ColourGlows(s.entry, s.colour) and "glowing" or "marked")
        return s.design + 1, #s.entry.designs + 1, group, true
    elseif row == C.MARK_COLOUR and s.marks then
        if s.design == 0 then
            return nil, #s.entry.colours, "plain", false
        end

        return s.colour, #s.entry.colours, C.ColourGlows(s.entry, s.colour) and "glowing" or "marked", true
    elseif r then
        return r.pos, r.count, "plain", true
    end

    return nil
end

-- The name of the option a row shows, for its tooltip (nil: none).
function C.OptionName(s, row)
    if row == C.SKIN and s.fresh then
        local groups = BleakholdCustomizeData.groups
        local group = type(groups) == "table" and groups[s.entry.skinGroup and s.entry.skinGroup[s.rows[1].raw]]
        local names = { marked = BLEAKHOLD_CUSTOMIZE_GROUP_MARKED, fel = BLEAKHOLD_CUSTOMIZE_GROUP_FEL,
                        deathknight = DEATH_KNIGHT or "Death Knight" }
        return names[group]
    elseif row == C.EYES and s.eyes then
        if s.eye == 0 then
            return BLEAKHOLD_CUSTOMIZE_DEFAULT_EYES
        end

        return type(s.entry.eyes) == "table" and s.entry.eyes[s.eye] or nil
    elseif row == C.MARKINGS and s.marks then
        return s.design == 0 and BLEAKHOLD_CUSTOMIZE_NO_MARKINGS or s.entry.designs[s.design]
    elseif row == C.MARK_COLOUR and s.marks and s.design > 0 then
        local name = s.entry.colours[s.colour]

        if name then
            local kind = C.ColourGlows(s.entry, s.colour) and BLEAKHOLD_CUSTOMIZE_GLOWING or BLEAKHOLD_CUSTOMIZE_PAINT
            return name .. " (" .. kind .. ")"
        end
    end

    return nil
end

-- ------------------------------------------------------------------------------------------------ stepping

local function wrap(index, delta, count)
    return (index - 1 + delta) % count + 1
end

-- The colour a design takes when it is picked from no markings: the last one used, else the first.
C.lastColour = 1

-- Steps a row by `delta` (±1, ±5) through what the arrows reach: the stock rows through CycleCharCustomization, the
-- Face and Features rows (when the added rows are live) and the added rows through the raw value they lead to.
function C.Step(row, delta)
    local s = C.Read()

    if row <= C.STOCK_ROWS and not (row == C.FACE and s.eyes) and not (row == C.FEATURES and s.marks) then
        cycle(row, delta)
        return true
    end

    local target, physical

    if row == C.FACE or row == C.EYES then
        if not s.eyes then
            return false
        end

        physical = C.FACE
        local base, eye = s.faceBase, s.eye

        if row == C.FACE then
            local bases = C.FaceBases(s.faceWalk, s.stride)
            base = bases[wrap(indexOf(bases, base) or 1, delta, #bases)]

            -- an eye the new base does not have in the walk (a face hidden for one of them, or a Death Knight face
            -- that brings its own skin): the race's own eyes, else the base's first one. The jump may change the skin,
            -- as the stock arrow landing on that face does.
            local eyes = C.EyesOf(s.faceWalk, s.stride, base)

            if not contains(eyes, eye) then
                eye = eyes[1]
            end
        else
            local eyes = C.EyesOf(s.faceWalk, s.stride, base)
            eye = eyes[wrap(indexOf(eyes, eye) or 1, delta, #eyes)]
        end

        target = base + s.stride * eye
    else
        if not s.marks then
            return false
        end

        physical = C.FEATURES
        local base, design, colour = s.featureBase, s.design, s.colour

        if row == C.FEATURES then
            base = wrap(base + 1, delta, s.B) - 1
        elseif row == C.MARKINGS then
            design = wrap(design + 1, delta, #s.entry.designs + 1) - 1
            colour = colour or C.lastColour
        else
            if design == 0 then
                return false
            end

            colour = wrap(colour, delta, #s.entry.colours)
        end

        if colour then
            C.lastColour = colour
        end

        target = C.LookOf(design, colour, s.perDesign) * s.B + base
    end

    if target == s.rows[physical].raw then
        return true
    end

    return C.SetRaw(physical, target, s)
end

local function shiftDown()
    return type(IsShiftKeyDown) == "function" and IsShiftKeyDown() and true or false
end

-- An arrow of row `id` (dir -1 or 1), the mouse wheel and the replaced CharacterCustomization_Left/Right. `stock` is
-- the stock function of that arrow: a plain step of a stock row goes through it unchanged.
function C.Arrow(id, dir, stock, steps)
    id = tonumber(id) or 0
    steps = steps or (shiftDown() and C.SHIFT_STEP or 1)
    local s = C.Read()
    local plain = id >= 1 and id <= C.STOCK_ROWS and not (id == C.FACE and s.eyes)
        and not (id == C.FEATURES and s.marks)

    if plain and stock then
        stock(id)

        if steps > 1 then
            BH.Try(cycle, id, dir * (steps - 1))
        end
    elseif id >= 1 then
        if type(PlaySound) == "function" then
            PlaySound("gsCharacterCreationLook")
        end

        local ok, done = pcall(C.Step, id, dir * steps)

        -- the data turned out not to match: the stock step still happens
        if (not ok or not done) and id <= C.STOCK_ROWS then
            if not ok then
                BH.Try(error, done, 0)
            end

            cycle(id, dir)
        end
    end

    C.Refresh()
end

-- Randomize (onlyRow nil: the Randomize button, every unlocked row; onlyRow: a right-click on that row, only it).
function C.Randomize(onlyRow)
    local before = C.Read()

    if not before.natives then
        if not onlyRow then
            RandomizeCharCustomization()
        end

        return
    end

    local function rolled(row)
        if onlyRow then
            return onlyRow == row
        end

        return not C.locks[row]
    end

    local keep = 0

    for row = 1, C.STOCK_ROWS do
        if not rolled(row) then
            keep = keep + 2 ^ (row - 1)
        end
    end

    if keep ~= 31 then
        RandomizeCharCustomization(keep)
    end

    local after = C.Read()

    if after.eyes then
        local eyes = C.EyesOf(after.faceWalk, after.stride, after.faceBase)
        local eye = after.eye

        if rolled(C.EYES) then
            eye = eyes[math.random(#eyes)]
        elseif before.eyes then
            eye = before.eye
        end

        -- an eye the new face does not have in the walk: the one it came with
        if not contains(eyes, eye) then
            eye = after.eye
        end

        if eye ~= after.eye then
            C.SetRaw(C.FACE, after.faceBase + after.stride * eye, after)
        end
    end

    after = C.Read()

    if after.marks then
        local design, colour = after.design, after.colour

        if before.marks then
            design, colour = before.design, before.colour
        end

        if rolled(C.MARKINGS) then
            design = math.random(0, #after.entry.designs)
        end

        if rolled(C.MARK_COLOUR) then
            colour = math.random(#after.entry.colours)
        elseif not colour then
            colour = C.lastColour
        end

        C.lastColour = colour

        local look = C.LookOf(design, colour, after.perDesign)

        if look ~= after.look then
            C.SetRaw(C.FEATURES, look * after.B + after.featureBase, after)
        end
    end
end

-- -------------------------------------------------------------------------------------------------- frames

local function copyFont(target, source)
    local fontObject = source and source.GetFontObject and source:GetFontObject()

    if fontObject then
        target:SetFontObject(fontObject)
        return
    end

    local file, size, flags

    if source and source.GetFont then
        file, size, flags = source:GetFont()
    end

    if file and size then
        target:SetFont(file, size, flags)
    elseif GlueFontHighlightSmall then
        target:SetFontObject(GlueFontHighlightSmall)
    end
end

-- The creation screen's own tooltip (GlueTooltip_SetOwner / GlueTooltip_SetText of the stock glue).
function C.Tooltip(owner, text)
    local tooltip = CharacterCreateTooltip

    if tooltip and type(GlueTooltip_SetOwner) == "function" and type(GlueTooltip_SetText) == "function" then
        GlueTooltip_SetOwner(owner, tooltip, -3, -5)
        GlueTooltip_SetText(text, tooltip)
    end
end

local function showTooltip(frame)
    local row = frame:GetID()
    local text = _G[frame:GetName() .. "Text"]
    local lines = { text and text:GetText() or "" }
    local s = C.state or C.Read()
    local name = C.OptionName(s, row)

    if name then
        lines[#lines + 1] = name
    end

    lines[#lines + 1] = BLEAKHOLD_CUSTOMIZE_HINT

    C.Tooltip(frame, table.concat(lines, "\n"))
end

local function hideTooltip()
    if CharacterCreateTooltip then
        CharacterCreateTooltip:Hide()
    end
end

local function stockArrow(dir)
    return dir < 0 and C.stockLeft or C.stockRight
end

-- Wheel, right-click, tooltip, the number and the lock of one row (stock or added).
local function decorateRow(frame, row)
    local name = frame:GetName()
    local text = _G[name .. "Text"]
    local count = frame:CreateFontString(name .. "BleakholdCount", "OVERLAY")
    copyFont(count, text)
    count:SetJustifyH("RIGHT")
    local middle = _G[name .. "Middle"]

    if middle then
        count:SetPoint("RIGHT", middle, "RIGHT", 4, 2)
    else
        count:SetPoint("RIGHT", frame, "RIGHT", -60, 2)
    end

    count:Hide()

    local lock = CreateFrame("CheckButton", name .. "BleakholdLock", frame)
    -- on the label plate's left end (the plate's art starts about 11 units into the row)
    lock:SetWidth(16)
    lock:SetHeight(16)
    lock:SetPoint("LEFT", frame, "LEFT", 12, 1)
    lock:SetNormalTexture("Interface\\Buttons\\UI-CheckBox-Up")
    lock:SetCheckedTexture("Interface\\Buttons\\UI-CheckBox-Check")
    lock:SetHighlightTexture("Interface\\Buttons\\UI-CheckBox-Highlight", "ADD")
    lock:SetChecked(C.locks[row] and 1 or nil)
    lock:Hide()
    lock:SetScript("OnClick", function(self)
        C.locks[row] = self:GetChecked() and true or nil

        if type(PlaySound) == "function" then
            PlaySound(C.locks[row] and "igMainMenuOptionCheckBoxOn" or "igMainMenuOptionCheckBoxOff")
        end
    end)
    lock:SetScript("OnEnter", function(self)
        C.Tooltip(self, BLEAKHOLD_CUSTOMIZE_LOCK)
    end)
    lock:SetScript("OnLeave", hideTooltip)

    frame:EnableMouse(true)

    if frame.EnableMouseWheel then
        frame:EnableMouseWheel(true)
    end

    BH.HookScript(frame, "OnMouseWheel", function(self, delta)
        local dir = (tonumber(delta) or 0) > 0 and -1 or 1
        C.Arrow(row, dir, row <= C.STOCK_ROWS and stockArrow(dir) or nil)
    end)
    BH.HookScript(frame, "OnMouseUp", function(self, button)
        if button == "RightButton" and C.HasNatives() then
            if type(PlaySound) == "function" then
                PlaySound("gsCharacterCreationLook")
            end

            C.Randomize(row)
            C.Refresh()
        end
    end)
    BH.HookScript(frame, "OnEnter", showTooltip)
    BH.HookScript(frame, "OnLeave", hideTooltip)

    local points = {}

    if text then
        for i = 1, text:GetNumPoints() do
            points[i] = { text:GetPoint(i) }
        end
    end

    C.rows[row] = { frame = frame, text = text, count = count, lock = lock, textPoints = points, middle = middle,
                    left = _G[name .. "LeftButton"], right = _G[name .. "RightButton"] }
end

-- The stock template's look, for a screen without CharacterCustomizationFrameTemplate.
local LABEL_FRAME = "Interface\\Glues\\CharacterCreate\\CharacterCreate-LabelFrame"

local function buildRow(name, parent, id)
    local f = CreateFrame("Frame", name, parent, nil, id)
    f:SetWidth(230)
    f:SetHeight(32)
    local left = f:CreateTexture(name .. "Left", "BACKGROUND")
    left:SetTexture(LABEL_FRAME)
    left:SetWidth(25)
    left:SetHeight(64)
    left:SetPoint("LEFT", f, "LEFT", -5, 0)
    left:SetTexCoord(0, 0.1953125, 0, 1)
    local right = f:CreateTexture(name .. "Right", "BACKGROUND")
    right:SetTexture(LABEL_FRAME)
    right:SetWidth(25)
    right:SetHeight(64)
    right:SetPoint("RIGHT", f, "RIGHT", -44, 0)
    right:SetTexCoord(0.8046875, 1, 0, 1)
    local middle = f:CreateTexture(name .. "Middle", "BACKGROUND")
    middle:SetTexture(LABEL_FRAME)
    middle:SetWidth(40)
    middle:SetHeight(64)
    middle:SetPoint("LEFT", left, "RIGHT", 0, 0)
    middle:SetPoint("RIGHT", right, "LEFT", 0, 0)
    middle:SetTexCoord(0.1953125, 0.8046875, 0, 1)
    local text = f:CreateFontString(name .. "Text", "BACKGROUND")

    if GlueFontHighlightSmall then
        text:SetFontObject(GlueFontHighlightSmall)
    end

    text:SetPoint("CENTER", middle, "CENTER", 0, 2)

    local function arrow(suffix, file, dir)
        local b = CreateFrame("Button", name .. suffix, f)
        b:SetWidth(32)
        b:SetHeight(32)
        b:SetNormalTexture("Interface\\Glues\\Common\\Glue-" .. file .. "-Button-Up")
        b:SetPushedTexture("Interface\\Glues\\Common\\Glue-" .. file .. "-Button-Down")
        b:SetHighlightTexture("Interface\\Glues\\Common\\Glue-" .. file .. "-Button-Highlight", "ADD")
        b:SetScript("OnClick", function()
            C.Arrow(id, dir)
        end)
        return b
    end

    local nextButton = arrow("RightButton", "RightArrow", 1)
    nextButton:SetPoint("RIGHT", f, "RIGHT", 0, 0)
    local prevButton = arrow("LeftButton", "LeftArrow", -1)
    prevButton:SetPoint("RIGHT", nextButton, "LEFT", 3, 0)
    return f
end

local function createVirtualRow(id, parent)
    local spec = C.VIRTUAL[id]
    local name = "BleakholdCustomize" .. spec.key
    local ok, f = pcall(CreateFrame, "Frame", name, parent, C.ROW_TEMPLATE, id)

    if not ok or not f then
        f = buildRow(name, parent, id)
    end

    f:SetID(id)
    f:Hide()
    local text = _G[name .. "Text"]

    if text then
        text:SetText(spec.label())
    end

    decorateRow(f, id)
end

-- Places the shown added rows as a column beside the stock rows, from the Features row up (the column goes left of
-- the rows when the screen has no room on their right).
function C.LayoutVirtual()
    local anchor = C.rows[C.FEATURES] and C.rows[C.FEATURES].frame

    if not anchor then
        return
    end

    local right = anchor.GetRight and anchor:GetRight()
    local screen = type(GetScreenWidth) == "function" and GetScreenWidth() or nil
    local width = C.rows[C.EYES] and C.rows[C.EYES].frame:GetWidth() or 230
    local onRight = not (right and screen and right + C.COLUMN_GAP + width > screen)
    local below = nil

    for _, id in ipairs({ C.MARK_COLOUR, C.MARKINGS, C.EYES }) do
        local row = C.rows[id]

        if row and row.frame:IsShown() then
            row.frame:ClearAllPoints()

            if below then
                row.frame:SetPoint("BOTTOM", below, "TOP", 0, 0)
            elseif onRight then
                row.frame:SetPoint("BOTTOMLEFT", anchor, "BOTTOMRIGHT", C.COLUMN_GAP, 0)
            else
                row.frame:SetPoint("BOTTOMRIGHT", anchor, "BOTTOMLEFT", -C.COLUMN_GAP, 0)
            end

            below = row.frame
        end
    end
end

local function setArrows(row, on)
    for _, b in ipairs({ row.left, row.right }) do
        if b then
            if on then
                b:Enable()
            else
                b:Disable()
            end
        end
    end
end

-- Puts the state into the rows.
function C.Refresh()
    local s = C.Read()
    C.state = s
    local layout = false

    for id = 1, 8 do
        local row = C.rows[id]

        if row then
            local virtual = id > C.STOCK_ROWS

            if virtual then
                local live = (id == C.EYES and s.eyes) or (id ~= C.EYES and s.marks)

                if live and not row.frame:IsShown() then
                    row.frame:Show()
                    layout = true
                elseif not live and row.frame:IsShown() then
                    row.frame:Hide()
                    layout = true
                end
            end

            local pos, count, group, active = C.Label(s, id)

            if count and s.natives then
                row.count:SetText((pos and pos > 0) and (pos .. "/" .. count) or ("-/" .. count))
                local color = C.COLORS[group] or C.COLORS.plain

                if active then
                    row.count:SetTextColor(color[1], color[2], color[3])
                else
                    row.count:SetTextColor(0.5, 0.5, 0.5)
                end

                row.count:Show()

                if row.text and not row.shifted then
                    row.shifted = true
                    row.text:ClearAllPoints()
                    row.text:SetPoint("CENTER", row.middle or row.frame, "CENTER", -12, 2)
                end
            else
                row.count:Hide()

                if row.text and row.shifted then
                    row.shifted = nil
                    row.text:ClearAllPoints()

                    for _, p in ipairs(row.textPoints) do
                        row.text:SetPoint(p[1], p[2], p[3], p[4], p[5])
                    end
                end
            end

            if virtual then
                setArrows(row, active ~= false)
            end

            if s.natives then
                row.lock:SetChecked(C.locks[id] and 1 or nil)
                row.lock:Show()
            else
                row.lock:Hide()
            end
        end
    end

    if layout then
        C.LayoutVirtual()
    end

    C.snapshot = C.Snapshot()
end

-- The raw values and the context, to notice changes made behind the rows' back.
function C.Snapshot()
    local parts = {}

    for row = 1, C.STOCK_ROWS do
        local pos, count, raw = C.NativeInfo(row)
        parts[#parts + 1] = tostring(pos) .. "/" .. tostring(count) .. "/" .. tostring(raw)
    end

    local raceFile, sex, dk = C.Context()
    parts[#parts + 1] = tostring(raceFile) .. tostring(sex) .. tostring(dk)
    return table.concat(parts, ",")
end

-- ------------------------------------------------------------------------------------------------ self-test

local ROW_NAMES = { "skin", "face", "hair style", "hair colour", "features", "eyes", "markings", "mark colour" }

local function selfTestLine(text)
    C.selfTestLog[#C.selfTestLog + 1] = text
    C.Log("self-test: " .. text)
end

-- Walks every row of the current race, sex and class forward and back through the arrows' own path (C.Step, as
-- CharacterCustomization_Left/Right and the wheel take it) and checks that the label follows the arrows: one step
-- moves n by one (wrapping at N), N stays, N steps come back to the start, and a stock row with data reaches the
-- data's raw values in the data's order. Returns the number of mismatches.
function C.SelfTestContext()
    local start = C.Read()
    local label = string.format("%s %s%s", tostring(start.raceFile), start.sex == 1 and "female" or "male",
        start.dk and " death knight" or "")
    local raws = {}

    for row = 1, C.STOCK_ROWS do
        raws[row] = start.rows[row] and start.rows[row].raw
    end

    local bad = 0

    for row = 1, 8 do
        local s = C.Read()

        -- the colour row needs a design to step
        if row == C.MARK_COLOUR and s.marks and s.design == 0 then
            C.Step(C.MARKINGS, 1)
            s = C.Read()
        end

        local pos, count, _, active = C.Label(s, row)

        if pos and count and active ~= false then
            local problem
            local first = pos

            for dir = 1, -1, -2 do
                for k = 1, count do
                    C.Step(row, dir)
                    local now = C.Read()
                    local p, n = C.Label(now, row)
                    local want = wrap(first, dir * k, count)

                    if n ~= count then
                        problem = string.format("step %d of %d: the count became %s", k, count, tostring(n))
                    elseif p ~= want then
                        problem = string.format("step %d of %d %s: the label says %s, the arrows reached %d", k, count,
                            dir > 0 and "forward" or "back", tostring(p), want)
                    elseif row == C.SKIN and now.fresh and now.skinWalk[p] ~= now.rows[1].raw then
                        problem = string.format("skin %d/%d is raw %d, the data says %s", p, n, now.rows[1].raw,
                            tostring(now.skinWalk[p]))
                    end

                    if problem then
                        break
                    end
                end

                if problem then
                    break
                end

                local back = C.Read()
                local p = C.Label(back, row)

                if p ~= first then
                    problem = string.format("%d steps %s ended at %s, not %d", count, dir > 0 and "forward" or "back",
                        tostring(p), first)
                    break
                end
            end

            if problem then
                bad = bad + 1
                selfTestLine(string.format("%s: %s MISMATCH: %s", label, ROW_NAMES[row], problem))
            else
                selfTestLine(string.format("%s: %s OK (%d)", label, ROW_NAMES[row], count))
            end

            -- back where it started for the next row; twice, as the skin can be set only once the face fits it
            for _ = 1, 2 do
                for r = 1, C.STOCK_ROWS do
                    if raws[r] ~= nil then
                        pcall(SetCharCustomizationRaw, r, raws[r])
                    end
                end
            end
        end
    end

    return bad
end

-- bleakCustomizeSelfTest 1: the screen's race, sex and class; 2: every race, sex and class (not on a paid change).
function C.SelfTest(all)
    C.selfTestLog = {}

    if not C.HasNatives() then
        selfTestLine("the exe has no GetCharCustomizationInfo / SetCharCustomizationRaw: nothing to check")
        return 0
    end

    local bad = 0

    if not all or PAID_SERVICE_TYPE or type(SetSelectedRace) ~= "function" or type(GetAvailableRaces) ~= "function" then
        bad = C.SelfTestContext()
    else
        local race, sex = GetSelectedRace(), GetSelectedSex()
        local _, _, class = GetSelectedClass()
        local races = select("#", GetAvailableRaces()) / 3

        for r = 1, races do
            for _, x in ipairs({ SEX_MALE or 2, SEX_FEMALE or 3 }) do
                SetSelectedRace(r)
                SetSelectedSex(x)
                local classes = select("#", GetAvailableClasses()) / 3

                for c = 1, classes do
                    if type(IsRaceClassValid) ~= "function" or IsRaceClassValid(r, c) then
                        SetSelectedClass(c)
                        bad = bad + C.SelfTestContext()
                    end
                end
            end
        end

        SetSelectedRace(race)
        SetSelectedSex(sex)

        if class then
            SetSelectedClass(class)
        end

        -- the stock screen's own labels and buttons for the restored race, sex and class
        if type(SetCharacterGender) == "function" then
            BH.Try(SetCharacterGender, sex)
        end
    end

    selfTestLine(bad == 0 and "done: every row OK" or string.format("done: %d row(s) with a mismatch", bad))
    return bad
end

function C.MaybeSelfTest()
    local value = type(GetCVar) == "function" and tonumber(GetCVar(C.SELF_TEST_CVAR) or "0") or 0

    if value and value > 0 then
        C.SelfTest(value >= 2)
        C.Refresh()
    end
end

-- -------------------------------------------------------------------------------------------------- install

function C.OnShow()
    C.lastColour = 1
    C.Refresh()
    C.LayoutVirtual()
    BH.Try(C.MaybeSelfTest)
end

local function install()
    if not CharacterCreate then
        C.Log("no CharacterCreate frame: rows left as they are")
        return
    end

    local parent

    for row = 1, C.STOCK_ROWS do
        local frame = _G[C.ROW_PREFIX .. row]

        if frame and frame.GetName then
            BH.Try(decorateRow, frame, row)
            parent = parent or frame:GetParent()
        end
    end

    if C.rows[C.FEATURES] then
        for id = 6, 8 do
            BH.Try(createVirtualRow, id, C.rows[C.FEATURES].frame:GetParent() or parent)
        end
    end

    -- The arrows call these by name (CharacterCreate.xml); the added rows' arrows too (same template).
    C.stockLeft, C.stockRight = CharacterCustomization_Left, CharacterCustomization_Right

    if type(C.stockLeft) == "function" and type(C.stockRight) == "function" then
        CharacterCustomization_Left = function(id)
            C.Arrow(id, -1, C.stockLeft)
        end
        CharacterCustomization_Right = function(id)
            C.Arrow(id, 1, C.stockRight)
        end
    end

    C.stockRandomize = CharacterCreate_Randomize

    if type(C.stockRandomize) == "function" then
        CharacterCreate_Randomize = function(...)
            if not C.HasNatives() then
                C.stockRandomize(...)
                C.Refresh()
                return
            end

            if type(PlaySound) == "function" then
                PlaySound("gsCharacterCreationLook")
            end

            local ok = BH.Try(C.Randomize)

            if not ok then
                RandomizeCharCustomization()
            end

            C.Refresh()
        end
    end

    -- Everything that can change the rows' lists or values.
    for _, name in ipairs({ "CharacterCreate_UpdateHairCustomization", "SetCharacterRace", "SetCharacterGender",
                            "SetCharacterClass", "CharacterChangeFixup", "CharacterRace_OnClick",
                            "CharacterClass_OnClick" }) do
        BH.WrapGlobal(name, nil, function()
            C.Refresh()
        end)
    end

    BH.HookScript(CharacterCreate, "OnShow", C.OnShow)

    -- A light poll while the screen shows: the frame only updates while its parent is visible.
    local poll = CreateFrame("Frame", "BleakholdCustomizePoll", CharacterCreate)
    local elapsedTotal = 0
    poll:SetScript("OnUpdate", function(_, elapsed)
        elapsedTotal = elapsedTotal + (elapsed or 0)

        if elapsedTotal >= C.POLL then
            elapsedTotal = 0

            if C.HasNatives() and C.Snapshot() ~= C.snapshot then
                BH.Try(C.Refresh)
            end
        end
    end)

    C.installed = true
    C.Log("rows installed: " .. (C.HasNatives() and "with the Bleakhold glue functions" or "wheel and Shift-click only "
        .. "(this exe has no GetCharCustomizationInfo)"))
end

BH.Try(install)

BH.FlushLoadErrors("BleakholdCustomize.lua")
