-- Bleakhold glue: character creation and selection for the Bleakhold races.
--
-- High Elf (Alliance, ChrRaces clientFileString "HighElf") and Eredar (Horde, "Eredar"), found by file name
-- whatever their race ids (22 and 23 after RaceForge's build, 15 and 19 on the Bleakhold realm), borrow the
-- Blood Elf and Draenei art until they have their own; the client finds them by file name too and shows them
-- in the Blood Elf and Draenei background scenes (WoW/Common/BleakholdRaces.h). The stock CharacterCreate.lua
-- knows ten race buttons (MAX_RACES = 10, "Too many races!" beyond that) and looks race icons up by file name,
-- so this file raises MAX_RACES, adds the buttons and icons, and lays the buttons out as an Alliance column and
-- a Horde column for any race count. With the stock ten races the stock layout is kept.

local BH = BleakholdGlue

-- Bleakhold race file name -> the stock race whose icon, scene lighting and ambience it uses.
BH.RACE_PROXIES = { HIGHELF = "BLOODELF", EREDAR = "DRAENEI" }
BH.MIN_RACE_BUTTONS = 12

local RACE_BUTTON = "CharacterCreateRaceButton"
local RACE_BUTTON_TEMPLATE = "CharacterCreateRaceButtonTemplate"

-- Stock layout (3.3.x CharacterCreate.xml): button 1 at TOP -50,-61, button 6 at TOP 50,-61, each following
-- button 21 units under the one before. Read back from the frames when they are there.
local layout = {
    alliance = { point = "TOP", relativePoint = "TOP", x = -50, y = -61 },
    horde = { point = "TOP", relativePoint = "TOP", x = 50, y = -61 },
    gap = 21,
    stockRows = 5,
    -- How much lower than the stock five rows a longer column may reach, in UI units (the gender buttons
    -- start well below the stock column).
    extraHeight = 20,
}

-- ------------------------------------------------------------------------------------------- race data

local function copyCoords(coords)
    return { coords[1], coords[2], coords[3], coords[4] }
end

local function addRaceTables()
    if type(RACE_ICON_TCOORDS) == "table" then
        for race, proxy in pairs(BH.RACE_PROXIES) do
            for _, sex in ipairs({ "MALE", "FEMALE" }) do
                local source = rawget(RACE_ICON_TCOORDS, proxy .. "_" .. sex)

                if source and not rawget(RACE_ICON_TCOORDS, race .. "_" .. sex) then
                    RACE_ICON_TCOORDS[race .. "_" .. sex] = copyCoords(source)
                end
            end
        end

        -- A race the table does not know (data newer than this file) gets the human icon instead of a
        -- Lua error in CharacterCreateEnumerateRaces.
        if not getmetatable(RACE_ICON_TCOORDS) then
            setmetatable(RACE_ICON_TCOORDS, {
                __index = function(t, key)
                    if type(key) == "string" and string.find(key, "_FEMALE$") then
                        return rawget(t, "HUMAN_FEMALE")
                    end

                    return rawget(t, "HUMAN_MALE")
                end,
            })
        end
    end

    -- Scene tables from GlueParent.lua are keyed by the upper-case scene name. The client hands the
    -- Bleakhold races the proxy race's scene, but alias them in case the data names a scene of their own.
    for _, name in ipairs({ "GlueAmbienceTracks", "RaceLights", "CharModelFogInfo", "CharModelGlowInfo" }) do
        local t = _G[name]

        if type(t) == "table" then
            for race, proxy in pairs(BH.RACE_PROXIES) do
                if t[race] == nil and t[proxy] ~= nil then
                    t[race] = t[proxy]
                end
            end
        end
    end

end

-- ---------------------------------------------------------------------------------------------- buttons

local function readStockLayout()
    local first = _G[RACE_BUTTON .. "1"]
    local second = _G[RACE_BUTTON .. "2"]
    local sixth = _G[RACE_BUTTON .. "6"]

    if first and first.GetPoint then
        local point, _, relativePoint, x, y = first:GetPoint(1)

        if point and x and y then
            layout.alliance = { point = point, relativePoint = relativePoint or point, x = x, y = y }
        end
    end

    if sixth and sixth.GetPoint then
        local point, relativeTo, relativePoint, x, y = sixth:GetPoint(1)

        if point and x and y and relativeTo ~= _G[RACE_BUTTON .. "5"] then
            layout.horde = { point = point, relativePoint = relativePoint or point, x = x, y = y }
        end
    end

    if second and second.GetPoint then
        local _, _, _, _, y = second:GetPoint(1)

        if y and y < 0 then
            layout.gap = -y
        end
    end
end

-- Makes sure race buttons 1..count exist (the stock XML has ten) and MAX_RACES covers them.
function BH.EnsureRaceButtons(count)
    local first = _G[RACE_BUTTON .. "1"]

    if not first then
        return
    end

    count = math.max(count or 0, BH.MIN_RACE_BUTTONS)
    local parent = first:GetParent()

    for i = 1, count do
        if not _G[RACE_BUTTON .. i] then
            local ok, button = pcall(CreateFrame, "CheckButton", RACE_BUTTON .. i, parent, RACE_BUTTON_TEMPLATE)

            if not ok or not button then
                return
            end

            button:SetID(i)
            button:Hide()
        end

        if (MAX_RACES or 0) < i then
            MAX_RACES = i
        end
    end
end

local function placeColumn(column, indices, pitch)
    for row, index in ipairs(indices) do
        local button = _G[RACE_BUTTON .. index]

        if button then
            local parent = button:GetParent()
            button:ClearAllPoints()
            button:SetPoint(column.point, parent, column.relativePoint, column.x, column.y - (row - 1) * pitch)
        end
    end
end

-- Alliance races in the left column, Horde races in the right one, in GetAvailableRaces order.
function BH.LayoutRaceButtons()
    local numRaces = CharacterCreate and CharacterCreate.numRaces or 0
    local first = _G[RACE_BUTTON .. "1"]

    if not first or numRaces < 1 then
        return
    end

    local alliance, horde = {}, {}

    for i = 1, numRaces do
        local _, faction = GetFactionForRace(i)

        if faction == "Horde" then
            horde[#horde + 1] = i
        else
            alliance[#alliance + 1] = i
        end
    end

    local rows = math.max(#alliance, #horde)
    local stockPitch = first:GetHeight() + layout.gap
    local pitch = stockPitch

    if rows > layout.stockRows then
        pitch = math.min(stockPitch, (stockPitch * (layout.stockRows - 1) + layout.extraHeight) / (rows - 1))
    end

    placeColumn(layout.alliance, alliance, pitch)
    placeColumn(layout.horde, horde, pitch)
end

-- SetCharacterRace concatenates RACE_INFO_<FILE> with no nil check, so a race this file does not know (newer
-- data) gets an empty description instead of a Lua error. Arguments: GetAvailableRaces() triples.
function BH.EnsureRaceStrings(...)
    for i = 2, select("#", ...), 3 do
        local file = select(i, ...)

        if type(file) == "string" then
            local key = "RACE_INFO_" .. string.upper(file)

            -- GetFlavorText falls back from an empty text to the other sex's, so both must exist.
            if _G[key] == nil then
                _G[key] = ""

                if _G[key .. "_FEMALE"] == nil then
                    _G[key .. "_FEMALE"] = ""
                end
            end
        end
    end
end

-- --------------------------------------------------------------------------------------------- install

BH.Try(addRaceTables)
BH.Try(BH.EnsureRaceStrings, "", "HighElf", 1, "", "Eredar", 1)
BH.Try(readStockLayout)
BH.Try(BH.EnsureRaceButtons, MAX_RACES)

-- CharacterCreate_OnShow and SetCharacterGender call CharacterCreateEnumerateRaces(GetAvailableRaces()) by
-- name. Buttons are added before the stock code checks the count, and laid out after it has filled them.
BH.WrapGlobal("CharacterCreateEnumerateRaces",
    function(...)
        BH.EnsureRaceButtons(select("#", ...) / 3)
        BH.EnsureRaceStrings(...)
    end,
    function()
        BH.LayoutRaceButtons()
    end)

BH.FlushLoadErrors("BleakholdCharacterCreate.lua")
