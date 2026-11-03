-- Bleakhold glue: character creation and selection for the Bleakhold races.
--
-- High Elf (Alliance, ChrRaces clientFileString "HighElf") and Eredar (Horde, "Eredar"), found by file name
-- whatever their race ids (22 and 23 after RaceForge's build, 15 and 19 on the Bleakhold realm), borrow the
-- Blood Elf and Draenei art until they have their own; the client finds them by file name too and shows them
-- in the Blood Elf and Draenei background scenes (WoW/Common/BleakholdRaces.h). The stock CharacterCreate.lua
-- knows ten race buttons (MAX_RACES = 10, "Too many races!" beyond that) and looks race icons up by file name,
-- so this file raises MAX_RACES and adds the missing buttons and icons.
--
-- Where the buttons go depends on the screen. Race button i shows race i, and the client lists every Alliance race
-- before every Horde race (CCharacterCreation::Initialize). On the stock screen (the two columns of five of the stock
-- CharacterCreate.xml, recognised by their anchors) every button is laid out again as an Alliance column and a Horde
-- column, for any race count; with the stock ten races that is the stock layout. A realm patch may bring a character
-- creation screen of its own, with other anchors, sizes, scales and button templates: there no button that screen
-- placed is ever moved. Only the buttons it lacks are added, each continuing the column of its faction's last button
-- with that column's step and scale, and an added button the screen's own code places is left where that code put it.

local BH = BleakholdGlue

-- Bleakhold race file name -> the stock race whose icon, scene lighting and ambience it uses.
BH.RACE_PROXIES = { HIGHELF = "BLOODELF", EREDAR = "DRAENEI" }
BH.MIN_RACE_BUTTONS = 12
-- On a screen of a realm patch: the space under a faction's only button before the one added below it, in UI units.
BH.CUSTOM_RACE_GAP = 8

local RACE_BUTTON = "CharacterCreateRaceButton"
local RACE_BUTTON_TEMPLATE = "CharacterCreateRaceButtonTemplate"

-- The stock screen (3.3.x CharacterCreate.xml): button 1 at TOP -50,-61 of its parent, button 6 at TOP 50,-61, each
-- other one 21 units under the one before. A screen is the stock one when each of its ten buttons sits there, under
-- the one before it or at its row's place from the parent's top, to within `tolerance` UI units, and it has no
-- eleventh button of its own.
local STOCK = { x = 50, y = -61, gap = 21, rows = 5, tolerance = 3 }

-- The stock screen's columns, read back from its buttons.
local layout = {
    alliance = { point = "TOP", relativePoint = "TOP", x = -50, y = -61 },
    horde = { point = "TOP", relativePoint = "TOP", x = 50, y = -61 },
    gap = 21,
    stockRows = 5,
    -- How much lower than the stock five rows a longer column may reach, in UI units (the gender buttons
    -- start well below the stock column).
    extraHeight = 20,
}

local buttons = {
    kind = nil, -- "stock" or "custom": decided from the screen's own buttons before this file adds any
    created = {}, -- [button] = true: the buttons this file made
    -- [button] = its anchors as this file last set them, or as it was made with (a template's or its OnLoad's), on
    -- a screen of a realm patch
    placed = {},
    adopted = {}, -- [button] = true: a button this file made that the screen's own code has placed since
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

-- --------------------------------------------------------------------------------------------- anchors

-- obj:method(...) when obj has it; nothing when it has not or the call fails (for the optional parts of a copy).
local function call(object, method, ...)
    local fn = object and object[method]

    if type(fn) == "function" then
        local ok, a, b, c, d, e, f, g, h = pcall(fn, object, ...)

        if ok then
            return a, b, c, d, e, f, g, h
        end
    end
end

local function raceButton(index)
    local button = _G[RACE_BUTTON .. index]
    return type(button) == "table" and type(button.GetPoint) == "function" and button or nil
end

-- A region's anchors, { point, relativeTo, relativePoint, x, y } each, as GetPoint lists them (relativeTo nil: the
-- screen).
local function anchorsOf(region)
    local out = {}

    for i = 1, call(region, "GetNumPoints") or 0 do
        local point, relativeTo, relativePoint, x, y = region:GetPoint(i)

        if type(relativeTo) == "number" then
            -- an absolute point: GetPoint gives point, x, y
            relativeTo, relativePoint, x, y = nil, point, relativeTo, relativePoint
        end

        if type(point) == "string" then
            out[#out + 1] = { point, relativeTo, relativePoint or point, x or 0, y or 0 }
        end
    end

    return out
end

local function sameAnchors(a, b)
    if #a ~= #b then
        return false
    end

    for i = 1, #a do
        local p, q = a[i], b[i]

        if p[1] ~= q[1] or p[2] ~= q[2] or p[3] ~= q[3] or math.abs(p[4] - q[4]) > 0.05
            or math.abs(p[5] - q[5]) > 0.05 then
            return false
        end
    end

    return true
end

-- Anchors a region as `anchors` say, moved by dx, dy, with `from` (when given) replaced by `to`.
local function setAnchors(region, anchors, dx, dy, from, to)
    region:ClearAllPoints()

    for _, a in ipairs(anchors) do
        local relativeTo = a[2]

        if from ~= nil and relativeTo == from then
            relativeTo = to
        end

        region:SetPoint(a[1], relativeTo, a[3], a[4] + dx, a[5] + dy)
    end
end

-- ------------------------------------------------------------------------------------------ stock screen

local function near(value, target)
    return type(value) == "number" and math.abs(value - target) <= STOCK.tolerance
end

local function onlyAnchor(button)
    local anchors = anchorsOf(button)
    return #anchors == 1 and anchors[1] or nil
end

local BELOW = { TOP = "BOTTOM", TOPLEFT = "BOTTOMLEFT", TOPRIGHT = "BOTTOMRIGHT" }

-- Button `row` of a stock column: TOP of the parent at the column's x and the row's height or, below the first row,
-- STOCK.gap under the button before it.
local function inStockPlace(button, parent, x, row, pitch, previous)
    local a = onlyAnchor(button)

    if not a or button:GetParent() ~= parent then
        return false
    end

    if a[2] == parent and a[1] == "TOP" and a[3] == "TOP" and near(a[4], x)
        and near(a[5], STOCK.y - (row - 1) * pitch) then
        return true
    end

    return row > 1 and previous ~= nil and a[2] == previous and BELOW[a[1]] == a[3] and near(a[4], 0)
        and near(a[5], -STOCK.gap)
end

local function isStockScreen()
    local first = raceButton(1)

    if not first or raceButton(STOCK.rows * 2 + 1) then
        return false
    end

    local parent = first:GetParent()
    local pitch = first:GetHeight() + STOCK.gap

    for column, x in ipairs({ -STOCK.x, STOCK.x }) do
        for row = 1, STOCK.rows do
            local index = (column - 1) * STOCK.rows + row
            local button = raceButton(index)

            if not button or not inStockPlace(button, parent, x, row, pitch, raceButton(index - 1)) then
                return false
            end
        end
    end

    return true
end

local function readStockLayout()
    local first = raceButton(1)

    for key, index in pairs({ alliance = 1, horde = STOCK.rows + 1 }) do
        local a = onlyAnchor(raceButton(index))
        layout[key] = { point = a[1], relativePoint = a[3], x = a[4], y = a[5] }
    end

    local a, b = onlyAnchor(first), onlyAnchor(raceButton(2))
    layout.gap = b[2] == first and -b[5] or (a[5] - b[5]) - first:GetHeight()
end

-- "stock" or "custom", decided once from the screen's buttons (nil until it has a race button 1).
local function screenKind()
    if not buttons.kind and raceButton(1) then
        buttons.kind = isStockScreen() and "stock" or "custom"

        if buttons.kind == "stock" then
            readStockLayout()
        end
    end

    return buttons.kind
end

function BH.RaceScreenKind()
    return screenKind()
end

-- ------------------------------------------------------------------------------------------- new buttons

local STATE_TEXTURES = { "Normal", "Pushed", "Disabled", "Highlight", "Checked", "DisabledChecked" }
local BUTTON_SCRIPTS = { "OnClick", "OnDoubleClick", "OnEnter", "OnLeave", "OnMouseDown", "OnMouseUp", "OnShow",
                         "OnHide" }
-- The scripts of a child frame copied with it (a frame type without one of them just has none to copy).
local FRAME_SCRIPTS = { "OnShow", "OnHide", "OnUpdate", "OnEnter", "OnLeave", "OnMouseDown", "OnMouseUp", "OnClick",
                        "OnSizeChanged" }
-- How deep under a race button its child frames are copied.
local MAX_PART_DEPTH = 4

-- The part of a region's name after its button's ("CharacterCreateRaceButton1Portrait" -> "Portrait"); nil for a
-- name that only begins like it ("CharacterCreateRaceButton10..." is not a part of button 1).
local function suffixOf(region, owner)
    local name, prefix = call(region, "GetName"), owner:GetName()

    if type(name) == "string" and prefix and #name > #prefix and string.sub(name, 1, #prefix) == prefix then
        local suffix = string.sub(name, #prefix + 1)

        if not string.find(suffix, "^%d") then
            return suffix
        end
    end
end

local function isRaceButton(frame)
    local name = call(frame, "GetName")
    return type(name) == "string" and string.find(name, "^" .. RACE_BUTTON .. "%d+$") ~= nil
end

local function belongsTo(region, owner)
    for _ = 1, 8 do
        if region == nil or type(region) ~= "table" then
            return false
        end

        if region == owner then
            return true
        end

        region = call(region, "GetParent")
    end

    return false
end

-- The values of frame:method() (GetRegions, GetChildren) as a list; empty when the call fails.
local function listOf(frame, method)
    local ok, list = pcall(function()
        return { frame[method](frame) }
    end)

    return ok and list or {}
end

-- Gives `frame` the scale of `like`: anchor offsets and sizes count in a frame's own scale.
local function matchScale(frame, like)
    local scale = call(like, "GetScale")

    if type(scale) == "number" and scale > 0 and scale ~= call(frame, "GetScale") then
        call(frame, "SetScale", scale)
    end
end

local function copyScripts(from, to, scripts)
    for _, script in ipairs(scripts) do
        local fn = call(from, "GetScript", script)

        if fn and not call(to, "GetScript", script) then
            call(to, "SetScript", script, fn)
        end
    end
end

local function copyLook(from, to)
    if from:GetObjectType() == "Texture" then
        local file = call(from, "GetTexture")

        if type(file) == "string" then
            call(to, "SetTexture", file)
        end

        local ulx, uly, llx, lly, urx, ury, lrx, lry = call(from, "GetTexCoord")

        if lry then
            call(to, "SetTexCoord", ulx, uly, llx, lly, urx, ury, lrx, lry)
        end

        local blend = call(from, "GetBlendMode")

        if blend then
            call(to, "SetBlendMode", blend)
        end

        local r, g, b, a = call(from, "GetVertexColor")

        if r then
            call(to, "SetVertexColor", r, g, b, a)
        end
    else
        local font = call(from, "GetFontObject")

        if font then
            call(to, "SetFontObject", font)
        end

        local file, size, flags = call(from, "GetFont")

        if file then
            call(to, "SetFont", file, size, flags)
        end

        local justify = call(from, "GetJustifyH")

        if justify then
            call(to, "SetJustifyH", justify)
        end

        local r, g, b, a = call(from, "GetTextColor")

        if r then
            call(to, "SetTextColor", r, g, b, a)
        end
    end

    call(to, "SetWidth", call(from, "GetWidth") or 0)
    call(to, "SetHeight", call(from, "GetHeight") or 0)
    call(to, "SetAlpha", call(from, "GetAlpha") or 1)

    if not call(from, "IsShown") then
        call(to, "Hide")
    end
end

-- A child frame's size, alpha, scale, level above its parent, model file, shown state and scripts (these last, so
-- that hiding the copy runs none of them).
local function copyFrameLook(from, to)
    call(to, "SetWidth", call(from, "GetWidth") or 0)
    call(to, "SetHeight", call(from, "GetHeight") or 0)
    call(to, "SetAlpha", call(from, "GetAlpha") or 1)
    matchScale(to, from)

    local level, base = call(from, "GetFrameLevel"), call(call(from, "GetParent"), "GetFrameLevel")
    local own = call(call(to, "GetParent"), "GetFrameLevel")

    if level and base and own then
        call(to, "SetFrameLevel", own + level - base)
    end

    local model = call(from, "GetModel")

    if type(model) == "string" and model ~= "" then
        call(to, "SetModel", model)
    end

    if not call(from, "IsShown") then
        call(to, "Hide")
    end

    copyScripts(from, to, FRAME_SCRIPTS)
end

-- Gives a button this file made the size of `model` (a race button of the screen) and every part of it that it lacks,
-- so that the screen's code finds on it what it finds on its own buttons: each region and child frame named after its
-- button, by the same suffix (<name>Text, <name>NormalTexture, <name>Portrait, <name>Selection, <name>SelectionGlow,
-- ...), and each state texture. With `whole` (the button is a plain CheckButton: no template made it) also the
-- unnamed regions and child frames, the font objects and the scripts, which find their race by the button's id. A
-- child frame this file makes gets all of its model's parts, named and unnamed; one the button's template made, only
-- the named parts it lacks. Frames the screen has only parented to the model (named otherwise) are not copied.
local function mirrorButton(button, model, whole)
    local name = button:GetName()
    local map = { [model] = button } -- a part of the model -> the button's own part of that name, or its copy
    local made = {} -- { part of the model, its new copy }
    local copyParts

    -- A texture or font string of the model on `owner` (the button, or its copy of the region's frame).
    local function copyRegion(region, owner, always, wholeOwner)
        if map[region] then
            return map[region]
        end

        local suffix = suffixOf(region, model)

        if suffix and _G[name .. suffix] ~= nil then
            map[region] = _G[name .. suffix]
            return map[region]
        end

        if not suffix and not wholeOwner and not always then
            return nil
        end

        local kind = region:GetObjectType()
        local regionName = suffix and name .. suffix or nil
        local copy

        if kind == "Texture" then
            copy = owner:CreateTexture(regionName, call(region, "GetDrawLayer"))
        elseif kind == "FontString" then
            copy = owner:CreateFontString(regionName, call(region, "GetDrawLayer"))
        else
            return nil
        end

        copyLook(region, copy)
        map[region] = copy
        made[#made + 1] = { region, copy }
        return copy
    end

    local function copyFrame(frame, owner, wholeOwner, depth)
        if map[frame] or isRaceButton(frame) or buttons.created[frame] then
            return
        end

        local suffix = suffixOf(frame, model)
        local existing = suffix and _G[name .. suffix]

        if type(existing) == "table" then
            -- made by the button's template: only the named parts it lacks
            map[frame] = existing
            copyParts(frame, existing, false, depth + 1)
            return
        end

        if not suffix and (not wholeOwner or call(frame, "GetName") ~= nil) then
            return
        end

        local frameName = suffix and name .. suffix or nil
        local ok, copy = pcall(CreateFrame, call(frame, "GetObjectType") or "Frame", frameName, owner)

        if not ok or not copy then
            ok, copy = pcall(CreateFrame, "Frame", frameName, owner)

            if not ok or not copy then
                return
            end
        end

        map[frame] = copy
        made[#made + 1] = { frame, copy }
        copyParts(frame, copy, true, depth + 1)
        copyFrameLook(frame, copy)
    end

    copyParts = function(from, to, wholePart, depth)
        if depth > MAX_PART_DEPTH then
            return
        end

        for _, region in ipairs(listOf(from, "GetRegions")) do
            if type(region) == "table" and region.GetObjectType then
                copyRegion(region, to, false, wholePart)
            end
        end

        for _, child in ipairs(listOf(from, "GetChildren")) do
            if type(child) == "table" and child.GetObjectType then
                copyFrame(child, to, wholePart, depth)
            end
        end
    end

    for _, state in ipairs(STATE_TEXTURES) do
        local texture = call(model, "Get" .. state .. "Texture")
        local own = call(button, "Get" .. state .. "Texture")

        if texture and own then
            map[texture] = own
        elseif texture then
            local copy = copyRegion(texture, button, true, whole)

            if copy and state == "Highlight" then
                call(button, "SetHighlightTexture", copy, call(texture, "GetBlendMode"))
            elseif copy then
                call(button, "Set" .. state .. "Texture", copy)
            end
        end
    end

    copyParts(model, button, whole, 1)

    for _, pair in ipairs(made) do
        local from, to = pair[1], pair[2]
        to:ClearAllPoints()

        for _, a in ipairs(anchorsOf(from)) do
            local relativeTo = a[2]

            if map[relativeTo] then
                relativeTo = map[relativeTo]
            elseif belongsTo(relativeTo, model) then
                relativeTo = button
            end

            call(to, "SetPoint", a[1], relativeTo, a[3], a[4], a[5])
        end
    end

    call(button, "SetWidth", call(model, "GetWidth") or 0)
    call(button, "SetHeight", call(model, "GetHeight") or 0)

    if whole then
        for _, kind in ipairs({ "Normal", "Highlight", "Disabled" }) do
            local font = call(model, "Get" .. kind .. "FontObject")

            if font then
                call(button, "Set" .. kind .. "FontObject", font)
            end
        end

        local text = call(model, "GetFontString")

        if text and map[text] then
            call(button, "SetFontString", map[text])
        end

        copyScripts(model, button, BUTTON_SCRIPTS)
    end
end

-- A race button like the screen's own: from the stock template when the screen has it, else a plain CheckButton;
-- on a screen of a realm patch (or without the template) given what it lacks of `model` (mirrorButton), and the
-- model's scale. CreateFrame is given its id, so that the template's OnLoad already finds it. On a screen of a realm
-- patch the anchors it was made with (a template's, or its OnLoad's) count as this file's: only other anchors set
-- later show that the screen's own code placed it.
local function createButton(index, parent, model)
    local name = RACE_BUTTON .. index
    local ok, button = pcall(CreateFrame, "CheckButton", name, parent, RACE_BUTTON_TEMPLATE, index)
    local fromTemplate = ok and button ~= nil

    if not fromTemplate then
        ok, button = pcall(CreateFrame, "CheckButton", name, parent, nil, index)

        if not ok or not button then
            return nil
        end
    end

    buttons.created[button] = true

    if not fromTemplate or buttons.kind ~= "stock" then
        BH.Try(mirrorButton, button, model, not fromTemplate)
    end

    button:SetID(index)
    matchScale(button, model)
    button:Hide()

    if buttons.kind ~= "stock" then
        buttons.placed[button] = anchorsOf(button)
    end

    return button
end

-- Makes sure race buttons 1..count exist (the stock XML has ten) and MAX_RACES covers them.
function BH.EnsureRaceButtons(count)
    local first = raceButton(1)

    if not first then
        return
    end

    screenKind()
    count = math.max(count or 0, BH.MIN_RACE_BUTTONS)
    local parent = first:GetParent()

    for i = 1, count do
        if not raceButton(i) and not createButton(i, parent, first) then
            return
        end

        if (MAX_RACES or 0) < i then
            MAX_RACES = i
        end
    end
end

-- ---------------------------------------------------------------------------------------------- layout

local function factionOf(index)
    local _, faction = GetFactionForRace(index)
    return faction == "Horde" and "Horde" or "Alliance"
end

local function placeColumn(column, indices, pitch)
    for row, index in ipairs(indices) do
        local button = raceButton(index)

        if button then
            local parent = button:GetParent()
            button:ClearAllPoints()
            button:SetPoint(column.point, parent, column.relativePoint, column.x, column.y - (row - 1) * pitch)
        end
    end
end

-- The stock screen: Alliance races in the left column, Horde races in the right one, in GetAvailableRaces order. The
-- buttons this file made take button 1's scale, as the offsets are in each button's own scale.
local function layoutStock(numRaces)
    local alliance, horde = {}, {}
    local first = raceButton(1)

    for i = 1, numRaces do
        if factionOf(i) == "Horde" then
            horde[#horde + 1] = i
        else
            alliance[#alliance + 1] = i
        end

        local button = raceButton(i)

        if button and buttons.created[button] then
            matchScale(button, first)
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

local function heightOf(button)
    local height = button:GetHeight() or 0

    if height <= 0 then
        local top, bottom = call(button, "GetTop"), call(button, "GetBottom")
        height = top and bottom and top - bottom or 0
    end

    return height
end

-- dx, dy when they are a step along a column or a row of buttons like `last`; nil when the step is nothing or a jump
-- from one column to another (a button's width across and its height down at once).
local function alongColumn(last, dx, dy)
    local width, height = math.max(last:GetWidth() or 0, 1), math.max(heightOf(last), 1)

    if math.abs(dx) + math.abs(dy) < 1 or (math.abs(dx) >= width and math.abs(dy) >= height) then
        return nil
    end

    return dx, dy
end

-- The step from `previous` to `last`, two buttons of a column anchored alike (to the same regions at the same points),
-- as a move of last's anchors; nil when they are not anchored alike or the step is not along a column (alongColumn).
local function offsetStep(previous, last)
    local a, b = anchorsOf(previous), anchorsOf(last)

    if #a == 0 or #a ~= #b then
        return nil
    end

    local dx, dy = b[1][4] - a[1][4], b[1][5] - a[1][5]

    for i = 1, #a do
        if a[i][1] ~= b[i][1] or a[i][2] ~= b[i][2] or a[i][3] ~= b[i][3]
            or math.abs(b[i][4] - a[i][4] - dx) > 0.05 or math.abs(b[i][5] - a[i][5] - dy) > 0.05 then
            return nil
        end
    end

    return alongColumn(last, dx, dy)
end

local POINT_X = { TOPLEFT = 0, LEFT = 0, BOTTOMLEFT = 0, TOP = 0.5, CENTER = 0.5, BOTTOM = 0.5, TOPRIGHT = 1, RIGHT = 1,
                  BOTTOMRIGHT = 1 }
local POINT_Y = { TOPLEFT = 1, TOP = 1, TOPRIGHT = 1, LEFT = 0.5, CENTER = 0.5, RIGHT = 0.5, BOTTOMLEFT = 0, BOTTOM = 0,
                  BOTTOMRIGHT = 0 }

-- Where `point` of a laid-out frame is on the screen, in screen units (GetRect counts in the frame's own scale); nil
-- while the frame has no place.
local function pointOnScreen(frame, point)
    local left, bottom, width, height = call(frame, "GetRect")
    local scale = call(frame, "GetEffectiveScale") or 1

    if type(left) ~= "number" or type(bottom) ~= "number" or type(width) ~= "number" or type(height) ~= "number" then
        return nil
    end

    return (left + width * (POINT_X[point] or 0)) * scale, (bottom + height * (POINT_Y[point] or 1)) * scale
end

-- The step from `previous` to `last` where the layout put them (buttons anchored each to a region of its own: a slot
-- or a row frame), in last's own units: how far last's first anchor point is from the same point of previous. nil
-- when either has no place yet or the step is not along a column (alongColumn).
local function measuredStep(previous, last, point)
    local px, py = pointOnScreen(previous, point)
    local lx, ly = pointOnScreen(last, point)
    local scale = call(last, "GetEffectiveScale") or 1

    if not px or not lx or type(scale) ~= "number" or scale <= 0 then
        return nil
    end

    return alongColumn(last, (lx - px) / scale, (ly - py) / scale)
end

local function chainedTo(previous, last)
    for _, a in ipairs(anchorsOf(last)) do
        if a[2] == previous then
            return true
        end
    end

    return false
end

-- Puts `adding` (buttons this file made, in race order) after the last button of `column` (the screen's own buttons
-- of one faction, in race order), with last's parent and scale, continuing that column with its step: under the
-- button before, as the column's last button hangs under its predecessor; at the step between the column's last two
-- buttons, as a move of last's anchors when those two are anchored alike, else as the distance the layout put
-- between them (each one anchored to the button before at that distance, by last's anchor points); only a column of
-- one (or two the layout has not placed yet) goes on the last button's height and BH.CUSTOM_RACE_GAP lower each.
local function continueColumn(column, adding)
    local last = column[#column]
    local previous = column[#column - 1]
    local anchors = anchorsOf(last)
    local parent = last:GetParent()
    local mode, dx, dy

    if previous and chainedTo(previous, last) then
        mode, dx, dy = "chain", 0, 0
    elseif previous then
        dx, dy = offsetStep(previous, last)
        mode = dx and "offsets"

        if not mode then
            dx, dy = measuredStep(previous, last, anchors[1][1])
            mode = dx and "measured"
        end
    end

    if not mode then
        mode, dx, dy = "offsets", 0, -(heightOf(last) + BH.CUSTOM_RACE_GAP)
    end

    local before = last

    for k, button in ipairs(adding) do
        if parent and button:GetParent() ~= parent then
            call(button, "SetParent", parent)
        end

        matchScale(button, last)

        if mode == "chain" then
            setAnchors(button, anchors, 0, 0, previous, before)
        elseif mode == "measured" then
            button:ClearAllPoints()

            for _, a in ipairs(anchors) do
                button:SetPoint(a[1], before, a[1], dx, dy)
            end
        else
            setAnchors(button, anchors, k * dx, k * dy)
        end

        buttons.placed[button] = anchorsOf(button)
        before = button
    end
end

-- A screen of a realm patch: its own buttons stay; each button this file made continues its faction's column.
local function layoutCustom(numRaces)
    local own, all, adding = {}, {}, {}

    for i = 1, numRaces do
        local button = raceButton(i)

        if button then
            local faction = factionOf(i)

            if buttons.created[button] then
                local now = anchorsOf(button)

                if #now == 0 then
                    -- nothing places it (any more): this file does
                    buttons.adopted[button] = nil
                elseif not buttons.adopted[button] and not sameAnchors(buttons.placed[button] or {}, now) then
                    -- The screen's code placed it since: other anchors than the ones it was made with or that this
                    -- file set last.
                    buttons.adopted[button] = true
                end
            end

            if buttons.created[button] and not buttons.adopted[button] then
                adding[faction] = adding[faction] or {}
                table.insert(adding[faction], button)
            elseif #anchorsOf(button) > 0 then
                own[faction] = own[faction] or {}
                table.insert(own[faction], button)
                all[#all + 1] = button
            end
        end
    end

    for faction, list in pairs(adding) do
        -- A faction without a button of the screen's own continues the screen's last column.
        local column = own[faction] or all

        if #column > 0 then
            continueColumn(column, list)
        end
    end
end

local function raceCount()
    if CharacterCreate and type(CharacterCreate.numRaces) == "number" and CharacterCreate.numRaces > 0 then
        return CharacterCreate.numRaces
    end

    return select("#", GetAvailableRaces()) / 3
end

-- Places the race buttons for numRaces races (default: the screen's count, else GetAvailableRaces's).
function BH.LayoutRaceButtons(numRaces)
    numRaces = numRaces or raceCount()

    if not raceButton(1) or not numRaces or numRaces < 1 then
        return
    end

    if screenKind() == "stock" then
        layoutStock(numRaces)
    else
        layoutCustom(numRaces)
    end
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
BH.Try(BH.EnsureRaceButtons, MAX_RACES)

-- CharacterCreate_OnShow and SetCharacterGender call CharacterCreateEnumerateRaces(GetAvailableRaces()) by
-- name. Buttons are added before the stock code checks the count, and placed after it has filled them.
BH.WrapGlobal("CharacterCreateEnumerateRaces",
    function(...)
        BH.EnsureRaceButtons(select("#", ...) / 3)
        BH.EnsureRaceStrings(...)
    end,
    function(...)
        BH.LayoutRaceButtons(select("#", ...) / 3)
    end)

-- A screen of a realm patch may list the races in a function of its own: place the added buttons after it shows too.
if CharacterCreate then
    BH.HookScript(CharacterCreate, "OnShow", function()
        BH.EnsureRaceButtons(raceCount())
        BH.LayoutRaceButtons()
    end)
end

BH.FlushLoadErrors("BleakholdCharacterCreate.lua")
