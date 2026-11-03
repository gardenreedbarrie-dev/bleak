-- Stand-ins for the stock 3.3.5a character customization rows (CharacterCreate.xml's CharacterCustomizationFrameTemplate
-- rows 1-5 and CharCreateRandomizeButton, CharacterCreate.lua's customization functions, the creation tooltip), written
-- for these tests (not copied from Blizzard's files), and a model of the client's option lists behind the stock
-- CycleCharCustomization / RandomizeCharCustomization and Bleakhold.exe's GetCharCustomizationInfo,
-- SetCharCustomizationRaw, RandomizeCharCustomization(keepMask) and BleakholdCustomize_Log (the natives' contract:
-- WoW/Common/BleakholdCustomize.h). Loaded after stock.lua for every scenario; the Bleakhold functions exist only when
-- the scenario turns them on (MOCK.customize.natives), as on an exe that has them.
--   dofile("customize_stock.lua")(scenario)
return function(scenario)
    local Object = getmetatable(GlueParent)
    -- CSimpleFrame methods the mock does not keep yet.
    function Object:EnableMouse(on) self._mouse = on and true or false end
    function Object:IsMouseEnabled() return self._mouse ~= false and 1 or nil end
    function Object:EnableMouseWheel(on) self._wheel = on and true or false end
    function Object:IsMouseWheelEnabled() return self._wheel and 1 or nil end
    function Object:IsAutoFocus() return self._autoFocus ~= false and 1 or nil end

    local CZ = { natives = false, stage = "stage2", reloads = 0, cycles = 0, sets = {}, randomized = {}, log = {},
                 tables = {} }
    MOCK.customize = CZ
    MOCK.cvars = MOCK.cvars or {}
    MOCK.shift = false

    function IsShiftKeyDown() return MOCK.shift and 1 or nil end
    function GetCVar(name) return MOCK.cvars[name] end
    function SetCVar(name, value) if MOCK.cvars[name] ~= nil then MOCK.cvars[name] = tostring(value) end end

    -- classes: Warrior and Death Knight for every race
    CZ.classes = { { "Warrior", "WARRIOR" }, { "Death Knight", "DEATHKNIGHT" } }
    CZ.class = 1
    function GetAvailableClasses()
        local out = {}
        for _, c in ipairs(CZ.classes) do out[#out + 1] = c[1]; out[#out + 1] = c[2]; out[#out + 1] = 1 end
        return unpack(out)
    end
    function GetSelectedClass() local c = CZ.classes[CZ.class]; return c[1], c[2], CZ.class end
    function SetSelectedClass(i) CZ.class = i; CZ.reset() end
    function IsRaceClassValid() return true end

    -- ------------------------------------------------------------------------------------- the option lists

    -- CZ.tables[raceFile][sex 0/1][kind "normal"/"deathknight"] = customize_data.lua's tables: { skins = {...} (the
    -- skins the kind may pick), fits = { [skin] = { [face] = true } } (the face rows it may pick on each),
    -- faceColors = { [face] = n } (each face variation's colour count), numFaces, numSkins, hairStyles = {...},
    -- hairColors = {...}, features = {...} } (MOCK.customizeData builds them). Without a table the race has the plain
    -- tables below. The skin and face rows walk them as CharacterComponent.cpp's SetNextSkin and SetNextFace do: the
    -- skins that fit the current face, and the faces whose loop from the last chosen skin (m_prevSkinIndex) finds one.
    local function range(n, from)
        local t = {}
        for i = 0, n - 1 do t[#t + 1] = (from or 0) + i end
        return t
    end
    local function plain()
        local t = { skins = range(9), fits = {}, faceColors = {}, numFaces = 6, numSkins = 9, hairStyles = range(8),
                    hairColors = range(10), features = range(5) }
        for s = 0, 8 do
            t.fits[s] = {}
            for f = 0, 5 do t.fits[s][f] = true end
        end
        for f = 0, 5 do t.faceColors[f] = 9 end
        return t
    end
    local PLAIN = plain()

    function CZ.context()
        local r = MOCK.races.list and MOCK.races.list[MOCK.races.selected]
        local sex = MOCK.races.sex == 3 and 1 or 0
        return r and r.file or "Human", sex, CZ.classes[CZ.class][2] == "DEATHKNIGHT" and "deathknight" or "normal"
    end
    function CZ.lists()
        local file, sex, kind = CZ.context()
        local t = CZ.tables[file] and CZ.tables[file][sex] and CZ.tables[file][sex][kind]
        return t or PLAIN
    end
    CZ.look = { 0, 0, 0, 0, 0 }
    local ROWKEY = { "skins", "faces", "hairStyles", "hairColors", "features" }
    -- SkinFits: the skin and its underwear may be picked (fits has it) and so may the face on it.
    local function skinFits(t, skin, face) return t.fits[skin] ~= nil and t.fits[skin][face] == true end
    -- FaceFits: SetNextFace's inner loop, from colour offset `offset`; the skin it finds, or nil.
    function CZ.faceFits(face, offset, t)
        t = t or CZ.lists()
        local n = t.faceColors[face] or 0
        local i = 0
        while i < n do
            local skin = (i + offset) % n
            if skinFits(t, skin, face) then return skin end
            i = skin + 1
        end
        return nil
    end
    function CZ.list(row)
        local t = CZ.lists()
        local out = {}
        if row == 1 then
            for s = 0, t.numSkins - 1 do if skinFits(t, s, CZ.look[2]) then out[#out + 1] = s end end
            return out
        elseif row == 2 then
            for f = 0, t.numFaces - 1 do if CZ.faceFits(f, CZ.prevSkin or CZ.look[1], t) then out[#out + 1] = f end end
            return out
        end
        return t[ROWKEY[row]] or {}
    end
    local function indexOf(list, v) for i, x in ipairs(list) do if x == v then return i end end return 0 end
    -- A look at the first skin, a face on it, and the first value of the other rows (SetSelectedRace / Sex / Class,
    -- ResetCharCustomize).
    function CZ.reset()
        local t = CZ.lists()
        CZ.look[1] = t.skins[1] or 0
        CZ.prevSkin = CZ.look[1]
        local faces = {}
        for f = 0, t.numFaces - 1 do if skinFits(t, CZ.look[1], f) then faces[#faces + 1] = f end end
        CZ.look[2] = faces[1] or 0
        for row = 3, 5 do CZ.look[row] = CZ.list(row)[1] or 0 end
    end
    -- A skin set behind the rows' back keeps the face when it fits, else takes the first face that does.
    local function fitFace()
        local t = CZ.lists()
        if skinFits(t, CZ.look[1], CZ.look[2]) then return end
        for f = 0, t.numFaces - 1 do
            if skinFits(t, CZ.look[1], f) then CZ.look[2] = f; return end
        end
    end
    function CZ.setValue(row, value)
        CZ.look[row] = value
        if row == 1 then CZ.prevSkin = value; fitFace() end
        CZ.reloads = CZ.reloads + 1
    end
    -- A face reached by the face row: the skin the loop found when the current one does not fit it (the stock step and
    -- BleakholdCustomize::PlanStep); the face loop's start does not move.
    local function takeFace(face)
        if not skinFits(CZ.lists(), CZ.look[1], face) then
            CZ.look[1] = CZ.faceFits(face, CZ.prevSkin or CZ.look[1]) or CZ.look[1]
        end
        CZ.look[2] = face
        CZ.reloads = CZ.reloads + 1
    end
    -- The value one stock press reaches in an ascending list: the next one up (or down) from the current, wrapping.
    local function neighbour(list, current, forward)
        if #list == 0 then return nil end
        if forward then
            for _, v in ipairs(list) do if v > current then return v end end
            return list[1]
        end
        for i = #list, 1, -1 do if list[i] < current then return list[i] end end
        return list[#list]
    end

    -- the stock functions
    function CycleCharCustomization(row, delta)
        CZ.cycles = CZ.cycles + 1
        if delta == 0 then return end
        local v = neighbour(CZ.list(row), CZ.look[row], delta > 0)
        if v == nil or v == CZ.look[row] then return end
        if row == 2 then
            takeFace(v)
        else
            CZ.setValue(row, v)
        end
    end
    local function randomize(keep)
        keep = keep or 0
        CZ.randomized[#CZ.randomized + 1] = keep
        local function kept(row) return math.floor(keep / 2 ^ (row - 1)) % 2 == 1 end
        local t = CZ.lists()
        if not kept(1) then
            -- a rolled skin fits a kept face (the skin walk), else any skin the kind may pick
            local list = kept(2) and CZ.list(1) or t.skins
            if #list > 0 then CZ.look[1] = list[math.random(#list)] end
        end
        CZ.prevSkin = CZ.look[1]
        if not kept(2) then
            -- SetRandomFace: a face of the skin
            local faces = {}
            for f = 0, t.numFaces - 1 do if skinFits(t, CZ.look[1], f) then faces[#faces + 1] = f end end
            if #faces > 0 then CZ.look[2] = faces[math.random(#faces)] end
        end
        for row = 3, 5 do
            if not kept(row) then
                local list = CZ.list(row)
                if #list > 0 then CZ.look[row] = list[math.random(#list)] end
            end
        end
        fitFace()
        CZ.reloads = CZ.reloads + 1
    end
    function RandomizeCharCustomization(keep)
        if keep ~= nil and not CZ.natives then error("stock RandomizeCharCustomization takes no argument here", 2) end
        randomize(keep)
    end
    local stockSetRace, stockSetSex = SetSelectedRace, SetSelectedSex
    function SetSelectedRace(i) stockSetRace(i); CZ.reset() end
    function SetSelectedSex(s) stockSetSex(s); CZ.reset() end
    function ResetCharCustomize() CZ.reset() end
    function CustomizeExistingCharacter(id)
        local c = CZ.paidCharacter
        if c then
            MOCK.races.selected, MOCK.races.sex, CZ.class = c.race, c.sex, c.class
            for row = 1, 5 do CZ.look[row] = c.look[row] end
            CZ.prevSkin = CZ.look[1]
        end
    end

    -- Bleakhold.exe's functions
    function CZ.enableNatives(on)
        CZ.natives = on and true or false
        if on then
            GetCharCustomizationInfo = function(row)
                if type(row) ~= "number" or row < 1 or row > 5 then return end
                local list = CZ.list(row)
                if CZ.lie and CZ.lie[row] then return CZ.lie[row](list, CZ.look[row]) end
                return indexOf(list, CZ.look[row]), #list, CZ.look[row]
            end
            -- BleakholdCustomize::PlanJump: a value of the row's walk, with what one press landing on it does
            SetCharCustomizationRaw = function(row, raw)
                CZ.sets[#CZ.sets + 1] = { row, raw }
                if indexOf(CZ.list(row), raw) == 0 then return false end
                if row == 2 then takeFace(raw) else CZ.setValue(row, raw) end
                return true
            end
            BleakholdCustomize_Log = function(text) CZ.log[#CZ.log + 1] = text end
            MOCK.cvars.bleakCustomizeSelfTest = MOCK.cvars.bleakCustomizeSelfTest or "0"
        else
            GetCharCustomizationInfo, SetCharCustomizationRaw, BleakholdCustomize_Log = nil, nil, nil
        end
    end

    -- --------------------------------------------------------------------------------- the stock frames

    NUM_CHAR_CUSTOMIZATIONS = 5
    CHAR_CUSTOMIZATION1_DESC, CHAR_CUSTOMIZATION2_DESC = "Skin Color", "Face"
    HAIR_HAIR_STYLE, HAIR_HAIR_COLOR, FACIAL_HAIR_HAIR = "Hair Style", "Hair Color", "Facial Hair"
    PAID_CHARACTER_CUSTOMIZATION, PAID_RACE_CHANGE, PAID_FACTION_CHANGE = 1, 2, 3
    DEATH_KNIGHT = "Death Knight"
    GlueFontHighlightSmall = CreateFont("GlueFontHighlightSmall")
    GlueFontDisableSmall = CreateFont("GlueFontDisableSmall")
    CharacterCreateTooltipFont = CreateFont("CharacterCreateTooltipFont")
    for _, f in ipairs({ "LabelFrame" }) do MOCK.addFile("Interface\\Glues\\CharacterCreate\\CharacterCreate-" .. f) end
    for _, a in ipairs({ "Left", "Right" }) do
        for _, s in ipairs({ "Up", "Down", "Highlight" }) do MOCK.addFile("Interface\\Glues\\Common\\Glue-" .. a .. "Arrow-Button-" .. s) end
    end

    MOCK.templates.CharacterCustomizationFrameTemplate = function(f, name)
        f:SetSize(230, 32)
        local left = f:CreateTexture(name .. "Left", "BACKGROUND")
        left:SetTexture("Interface\\Glues\\CharacterCreate\\CharacterCreate-LabelFrame"); left:SetSize(25, 64)
        left:SetPoint("LEFT", f, "LEFT", -5, 0)
        local right = f:CreateTexture(name .. "Right", "BACKGROUND")
        right:SetTexture("Interface\\Glues\\CharacterCreate\\CharacterCreate-LabelFrame"); right:SetSize(25, 64)
        right:SetPoint("RIGHT", f, "RIGHT", -44, 0)
        local middle = f:CreateTexture(name .. "Middle", "BACKGROUND")
        middle:SetTexture("Interface\\Glues\\CharacterCreate\\CharacterCreate-LabelFrame"); middle:SetSize(40, 64)
        middle:SetPoint("LEFT", left, "RIGHT", 0, 0); middle:SetPoint("RIGHT", right, "LEFT", 0, 0)
        local text = f:CreateFontString(name .. "Text", "BACKGROUND")
        text:SetFontObject(GlueFontHighlightSmall)
        text:SetPoint("CENTER", middle, "CENTER", 0, 2)
        local r = CreateFrame("Button", name .. "RightButton", f); r:SetSize(32, 32); r:SetPoint("RIGHT", f, "RIGHT", 0, 0)
        r:SetNormalTexture("Interface\\Glues\\Common\\Glue-RightArrow-Button-Up")
        r:SetScript("OnClick", function(self) CharacterCustomization_Right(self:GetParent():GetID()) end)
        local l = CreateFrame("Button", name .. "LeftButton", f); l:SetSize(32, 32); l:SetPoint("RIGHT", r, "LEFT", 3, 0)
        l:SetNormalTexture("Interface\\Glues\\Common\\Glue-LeftArrow-Button-Up")
        l:SetScript("OnClick", function(self) CharacterCustomization_Left(self:GetParent():GetID()) end)
    end

    local config = CharacterCreateConfigurationFrame or CreateFrame("Frame", "CharacterCreateConfigurationFrame", CharacterCreate)
    config:SetSize(256, 758)
    config:SetPoint("TOPLEFT", CharacterCreate, "TOPLEFT", 9, -5)
    CharCreateRandomizeButton = CreateFrame("Button", "CharCreateRandomizeButton", config)
    CharCreateRandomizeButton:SetSize(146, 30)
    CharCreateRandomizeButton:SetPoint("BOTTOM", config, "BOTTOM", 0, 10)
    CharCreateRandomizeButton:SetScript("OnClick", function() CharacterCreate_Randomize() end)
    local below = CharCreateRandomizeButton
    for i = 5, 1, -1 do
        local row = CreateFrame("Frame", "CharacterCustomizationButtonFrame" .. i, config, "CharacterCustomizationFrameTemplate", i)
        if i == 5 then row:SetPoint("BOTTOM", below, "TOP", -6, 3) else row:SetPoint("BOTTOM", below, "TOP", 0, 0) end
        below = row
    end
    for i = 1, 2 do _G["CharacterCustomizationButtonFrame" .. i .. "Text"]:SetText(_G["CHAR_CUSTOMIZATION" .. i .. "_DESC"]) end

    CharacterCreateTooltip = CreateFrame("Frame", "CharacterCreateTooltip", GlueParent)
    CharacterCreateTooltip._shown = false
    function GlueTooltip_SetOwner(owner, tooltip) tooltip = tooltip or CharacterCreateTooltip; tooltip.owner = owner end
    function GlueTooltip_SetText(text, tooltip) tooltip = tooltip or CharacterCreateTooltip; tooltip._text = text; tooltip:Show() end

    -- CharacterCreate.lua (behaviour of the stock functions)
    function CharacterCustomization_Left(id) PlaySound("gsCharacterCreationLook"); CycleCharCustomization(id, -1) end
    function CharacterCustomization_Right(id) PlaySound("gsCharacterCreationLook"); CycleCharCustomization(id, 1) end
    function CharacterCreate_Randomize() PlaySound("gsCharacterCreationLook"); RandomizeCharCustomization() end
    function CharacterCreate_UpdateHairCustomization()
        CharacterCustomizationButtonFrame3Text:SetText(_G["HAIR_" .. GetHairCustomization() .. "_STYLE"])
        CharacterCustomizationButtonFrame4Text:SetText(_G["HAIR_" .. GetHairCustomization() .. "_COLOR"])
        CharacterCustomizationButtonFrame5Text:SetText(_G["FACIAL_HAIR_" .. GetFacialHairCustomization()])
    end
    function SetCharacterClass(id) CharacterCreate.selectedClass = id end
    function CharacterClass_OnClick(id)
        PlaySound("gsCharacterCreationClass")
        local _, _, current = GetSelectedClass()
        if current ~= id and IsRaceClassValid(GetSelectedRace(), id) then
            SetSelectedClass(id); SetCharacterClass(id); SetCharacterRace(GetSelectedRace()); CharacterChangeFixup()
        end
    end
    local stockOnShow = CharacterCreate_OnShow
    function CharacterCreate_OnShow()
        if PAID_SERVICE_TYPE then CustomizeExistingCharacter(PAID_SERVICE_CHARACTER_ID) end
        stockOnShow()
        CharacterCreate_UpdateHairCustomization()
    end
    local stockGender = SetCharacterGender
    function SetCharacterGender(sex) stockGender(sex); CharacterCreate_UpdateHairCustomization(); CharacterChangeFixup() end

    if scenario and scenario:find("^picker") and not scenario:find("stock") then CZ.enableNatives(true) end
end
