-- Bleakhold: the barbershop's selectors (Blizzard_BarberShopUI, loaded on demand when the player sits in a barber's
-- chair), in the stock look:
--   * "n/N" after each selector's name, coloured by the option's group (plain, marked, fel, Death Knight, glowing);
--   * the mouse wheel steps a selector (wheel down: next), Shift-click on an arrow steps 5 at a time, and a right-click
--     on a selector picks a random option of it;
--   * the skin selector follows CanAlterSkin() each time the barbershop opens (the stock code decides it once, at
--     load).
-- When the realm's tables have the Bleakhold marks (Tools/RaceForge/README.md, "Bleakhold appearance data contract":
-- features = look * B + base) and the client's counts match BarberData.lua, a small panel beside the barbershop adds
-- Markings and Mark Colour selectors; Facial Style then steps the base feature only and the banner names the mark
-- ("Moonwell Sigils, Elune Blue"). The barbershop cannot change faces, so eyes stay on the customize screen.
--
-- Bleakhold.exe's barbershop functions (WoW/Source/Ui/BarberShop_Scripts.cpp), each checked before use; without them
-- only the wheel, Shift-click and the skin selector fix are added:
--   GetBarberShopStyleInfo(type) returns 5-7: raw value, position (1-based, the arrows' order), count
--   SetBarberShopStyleData(type, raw): selects that raw value when the selector's list has it (read back to confirm)
local ADDON, ns = ...

local B = {}
ns.Barber = B

-- Selector ids as GetBarberShopStyleInfo numbers them; 5 and 6 are Bleakhold's.
B.HAIR_STYLE, B.HAIR_COLOR, B.FEATURES, B.SKIN = 1, 2, 3, 4
B.MARKINGS, B.MARK_COLOUR = 5, 6
B.SHIFT_STEP = 5
-- The category text is widened from the stock 90 to hold the number.
B.CATEGORY_WIDTH = 124

B.COLORS = {
    plain = { 1, 1, 1 },
    marked = { 1, 0.82, 0 },
    fel = { 0.45, 1, 0.2 },
    deathknight = { 0.77, 0.12, 0.23 },
    glowing = { 0.4, 0.85, 1 },
}

B.TEXT = {
    markings = "Markings",
    markColour = "Mark Colour",
    noMarkings = "No markings",
    skin = "Skin Color",
}

B.selectors = {}
B.stale = {}
B.log = {}
B.lastColour = 1

local floor, abs = math.floor, math.abs

local function log(text)
    B.log[#B.log + 1] = tostring(text)
end

-- ------------------------------------------------------------------------------------------------- natives

function B.HasNatives()
    return type(_G.SetBarberShopStyleData) == "function"
end

-- position, count, raw, name of a stock selector, or nil (no Bleakhold.exe, or the selector is off: skin without
-- CanAlterSkin).
function B.Info(id)
    local ok, name, _, _, _, raw, pos, count = pcall(GetBarberShopStyleInfo, id)

    if ok and type(raw) == "number" and type(pos) == "number" and type(count) == "number" and count > 0 then
        return pos, count, raw, name
    end

    return nil
end

local function stockCall(name, ...)
    local fn = _G[name]

    if type(fn) == "function" then
        return fn(...)
    end
end

local function selectorFrame(id)
    return _G["BarberShopFrameSelector" .. id]
end

-- One stock step of a selector, as its arrow does it.
local function stockStep(id, dir)
    SetNextBarberShopStyle(id, dir < 0 and 1 or nil)
end

local function afterStep(id)
    stockCall("BarberShop_UpdateCost")

    local frame = selectorFrame(id)

    if frame then
        stockCall("BarberShop_UpdateSelector", frame)
    end
end

-- ---------------------------------------------------------------------------------------------------- data

function B.Context()
    local _, raceFile = UnitRace("player")
    local sex = UnitSex("player") == 3 and 1 or 0
    local _, classFile = UnitClass("player")
    return raceFile, sex, classFile == "DEATHKNIGHT"
end

function B.Entry(raceFile, sex)
    local data = ns.BarberData

    if type(data) ~= "table" or data.version ~= 1 or type(data.races) ~= "table" or type(raceFile) ~= "string" then
        return nil
    end

    local race = data.races[raceFile]

    if race == nil then
        for key, value in pairs(data.races) do
            if type(key) == "string" and strlower(key) == strlower(raceFile) then
                race = value
                break
            end
        end
    end

    local entry = type(race) == "table" and race[sex] or nil
    return type(entry) == "table" and entry or nil
end

local function countOf(value, key)
    if type(value) == "number" then
        return value
    end

    if type(value) == "table" then
        return tonumber(key ~= nil and value[key]) or tonumber(value.default)
    end
end

local function colourGlows(entry, colour)
    if type(entry.colourGlows) == "table" and entry.colourGlows[colour] ~= nil then
        return entry.colourGlows[colour] and true or false
    end

    return colour ~= nil and colour < #entry.colours
end

function B.LookOf(design, colour, perDesign)
    if not design or design == 0 then
        return 0
    end

    return perDesign * (design - 1) + colour
end

-- The data's skin walk the native skin selector is on, or nil. The skin arrows reach the skins that fit the
-- character's face and have a BarberShopStyle row; the barbershop cannot change the face, and no function tells the UI
-- which face it is, so the data lists one walk per group of faces (skinSets) and the selector's walk must be one of
-- them: as many skins, and the previewed skin at its place.
function B.SkinWalk(view, skin)
    if type(view.skinSets) ~= "table" then
        return nil
    end

    for _, set in ipairs(view.skinSets) do
        if type(set) == "table" and #set == skin.count and skin.pos > 0 and set[skin.pos] == skin.raw then
            return set
        end
    end

    return nil
end

-- The selectors' state: natives, rows[1..4] = { pos, count, raw, name }, key, entry, view, fresh (the skin walk is one
-- of the data's: groups apply), marks (B, looks, perDesign, featureBase, look, design, colour).
function B.Read()
    local s = { natives = B.HasNatives(), rows = {} }

    if not s.natives then
        return s
    end

    for id = 1, 4 do
        local pos, count, raw, name = B.Info(id)

        if pos then
            s.rows[id] = { pos = pos, count = count, raw = raw, name = name }
        end
    end

    s.raceFile, s.sex, s.dk = B.Context()
    local entry = B.Entry(s.raceFile, s.sex)
    local view = entry and (s.dk and entry.deathKnight or entry.normal)

    if type(view) ~= "table" then
        return s
    end

    s.key = tostring(s.raceFile) .. ":" .. tostring(s.sex) .. ":" .. (s.dk and "deathknight" or "normal")
    s.entry, s.view = entry, view

    if B.stale[s.key] then
        return s
    end

    local skin, features = s.rows[B.SKIN], s.rows[B.FEATURES]

    if skin and B.SkinWalk(view, skin) then
        s.fresh = true
    elseif skin and not B.stale[s.key .. ":skins"] then
        B.stale[s.key .. ":skins"] = true
        log(string.format("%s: %d skins (now %d), no skin walk of the data has them: no skin groups", s.key,
            skin.count, skin.raw))
    end

    local data = ns.BarberData
    local Bn, looks = tonumber(entry.B), tonumber(entry.looks) or 1
    local perDesign = tonumber(data.looksPerDesign) or 3

    if features and Bn and Bn > 0 and looks > 1 and type(entry.designs) == "table" and type(entry.colours) == "table"
        and #entry.colours == perDesign and looks == 1 + #entry.designs * perDesign then
        local hairColor = s.rows[B.HAIR_COLOR] and s.rows[B.HAIR_COLOR].raw
        local expected = countOf(view.features, hairColor)

        local all = looks * Bn

        if features.count == all and (expected == nil or expected == features.count) and features.raw < all then
            s.marks, s.B, s.looks, s.perDesign = true, Bn, looks, perDesign
            s.featureBase, s.look = features.raw % Bn, floor(features.raw / Bn)

            if s.look == 0 then
                s.design = 0
            else
                s.design, s.colour = floor((s.look - 1) / perDesign) + 1, (s.look - 1) % perDesign + 1
            end
        elseif features.count ~= Bn and not B.stale[s.key .. ":logged"] then
            B.stale[s.key .. ":logged"] = true
            log(string.format("%s: %d features, the data has %s (B %d): no mark selectors", s.key, features.count,
                tostring(expected), Bn))
        end
    end

    return s
end

-- position, count, group, active of a selector (nil: nothing to show).
function B.Label(s, id)
    local r = s.rows[id]

    if id == B.SKIN and r then
        local group = "plain"

        if s.fresh and type(s.entry.skinGroup) == "table" then
            local groups = ns.BarberData.groups
            group = type(groups) == "table" and groups[s.entry.skinGroup[r.raw]] or "plain"
        end

        return r.pos, r.count, B.COLORS[group] and group or "plain", true
    elseif id == B.FEATURES and r and s.marks then
        return s.featureBase + 1, s.B, "plain", true
    elseif id == B.MARKINGS and s.marks then
        local group = s.design == 0 and "plain" or (colourGlows(s.entry, s.colour) and "glowing" or "marked")
        return s.design + 1, #s.entry.designs + 1, group, true
    elseif id == B.MARK_COLOUR and s.marks then
        if s.design == 0 then
            return nil, #s.entry.colours, "plain", false
        end

        return s.colour, #s.entry.colours, colourGlows(s.entry, s.colour) and "glowing" or "marked", true
    elseif r then
        return r.pos, r.count, "plain", true
    end
end

-- The banner's text for the marks: "Moonwell Sigils, Elune Blue", or "No markings".
function B.MarkName(s)
    if not s.marks then
        return nil
    end

    if s.design == 0 then
        return B.TEXT.noMarkings
    end

    return tostring(s.entry.designs[s.design]) .. ", " .. tostring(s.entry.colours[s.colour])
end

-- ----------------------------------------------------------------------------------------------- stepping

local function wrap(index, delta, count)
    return (index - 1 + delta) % count + 1
end

-- Selects a features value and reads it back; a value the client does not take marks the data stale.
local function setFeatures(raw, s)
    pcall(_G.SetBarberShopStyleData, B.FEATURES, raw)
    local _, _, now = B.Info(B.FEATURES)

    if now == raw then
        return true
    end

    B.stale[s.key] = true
    log(string.format("%s: features did not take %d (they have %s); plain selectors from now on", s.key, raw,
        tostring(now)))
    return false
end

local function isPlain(s, id)
    return id >= 1 and id <= 4 and not (id == B.FEATURES and s.marks)
end

-- Steps a selector by `delta`; the stock selectors through SetNextBarberShopStyle, Facial Style (with the marks live)
-- and the mark selectors through the raw value they lead to.
function B.Step(id, delta)
    local s = B.Read()

    if isPlain(s, id) then
        for _ = 1, abs(delta) do
            stockStep(id, delta)
        end

        afterStep(id)
        return true
    end

    if not s.marks then
        return false
    end

    local base, design, colour = s.featureBase, s.design, s.colour

    if id == B.FEATURES then
        base = wrap(base + 1, delta, s.B) - 1
    elseif id == B.MARKINGS then
        design = wrap(design + 1, delta, #s.entry.designs + 1) - 1
        colour = colour or B.lastColour
    else
        if design == 0 then
            return false
        end

        colour = wrap(colour, delta, #s.entry.colours)
    end

    if colour then
        B.lastColour = colour
    end

    local raw = B.LookOf(design, colour, s.perDesign) * s.B + base
    local done = raw == s.rows[B.FEATURES].raw or setFeatures(raw, s)
    afterStep(B.FEATURES)

    if id ~= B.FEATURES then
        stockCall("BarberShop_UpdateBanner", B.MarkName(B.Read()))
    end

    return done
end

local function shiftDown()
    return IsShiftKeyDown and IsShiftKeyDown() and true or false
end

-- An arrow (dir -1 or 1) or the wheel. `stock` runs the arrow's own OnClick for a plain single step.
function B.Arrow(id, dir, stock)
    local steps = shiftDown() and B.SHIFT_STEP or 1
    local s = B.Read()

    if isPlain(s, id) and stock then
        stock()

        for _ = 2, steps do
            stockStep(id, dir)
        end

        if steps > 1 then
            afterStep(id)
        end
    else
        if PlaySound then
            PlaySound("UChatScrollButton")
        end

        if not B.Step(id, dir * steps) and id <= 4 then
            stockStep(id, dir)
            afterStep(id)
        end
    end

    B.Refresh()
end

-- A random option of one selector.
function B.Random(id)
    local s = B.Read()

    if not s.natives then
        return
    end

    if isPlain(s, id) then
        local r = s.rows[id]

        if r and r.count > 1 then
            B.Step(id, math.random(1, r.count - 1))
        end
    elseif s.marks then
        local base, design, colour = s.featureBase, s.design, s.colour or B.lastColour

        if id == B.FEATURES then
            base = math.random(0, s.B - 1)
        elseif id == B.MARKINGS then
            design = math.random(0, #s.entry.designs)
        elseif design > 0 then
            colour = math.random(1, #s.entry.colours)
        end

        B.lastColour = colour
        local raw = B.LookOf(design, colour, s.perDesign) * s.B + base

        if raw ~= s.rows[B.FEATURES].raw then
            setFeatures(raw, s)
        end

        afterStep(B.FEATURES)

        if id ~= B.FEATURES then
            stockCall("BarberShop_UpdateBanner", B.MarkName(B.Read()))
        end
    end

    if PlaySound then
        PlaySound("UChatScrollButton")
    end

    B.Refresh()
end

-- -------------------------------------------------------------------------------------------------- frames

local function colourCode(c)
    return string.format("|cff%02x%02x%02x", floor(c[1] * 255 + 0.5), floor(c[2] * 255 + 0.5), floor(c[3] * 255 + 0.5))
end

-- Puts the state into the selectors.
function B.Refresh()
    local s = B.Read()
    B.state = s

    for id, sel in pairs(B.selectors) do
        local pos, count, group, active = B.Label(s, id)
        local text = sel.base or ""

        if count and s.natives then
            local c = active and (B.COLORS[group] or B.COLORS.plain) or { 0.5, 0.5, 0.5 }
            local number = (pos and pos > 0) and (pos .. "/" .. count) or ("-/" .. count)
            text = text .. "  " .. colourCode(c) .. number .. "|r"
            sel.category:SetWidth(B.CATEGORY_WIDTH)
        else
            sel.category:SetWidth(sel.stockWidth or 90)
        end

        sel.category:SetText(text)

        if id >= B.MARKINGS then
            for _, b in ipairs({ sel.prev, sel.next }) do
                if b then
                    if active ~= false then
                        b:Enable()
                    else
                        b:Disable()
                    end
                end
            end
        end
    end

    local panel = B.panel

    if panel then
        if s.marks then
            panel:Show()
        else
            panel:Hide()
        end
    end

    -- package skin rows without a name would leave the banner empty
    if s.rows[B.SKIN] and (s.rows[B.SKIN].name == nil or s.rows[B.SKIN].name == "") and B.lastStepped == B.SKIN then
        stockCall("BarberShop_UpdateBanner", (_G.SKIN_COLOR or B.TEXT.skin) .. " " .. s.rows[B.SKIN].pos)
    end
end

local function decorate(sel, id)
    local name = sel:GetName()
    local category = _G[name .. "Category"]
    local entry = { frame = sel, category = category, base = category and category:GetText() or "",
                    stockWidth = category and category:GetWidth(), prev = _G[name .. "Prev"],
                    next = _G[name .. "Next"] }
    B.selectors[id] = entry

    for _, arrow in ipairs({ { entry.prev, -1 }, { entry.next, 1 } }) do
        local button, dir = arrow[1], arrow[2]

        if button then
            local stock = button:GetScript("OnClick")
            button:SetScript("OnClick", function(self, ...)
                local args = { ... }
                B.lastStepped = id
                B.Arrow(id, dir, stock and id <= 4 and function()
                    stock(self, unpack(args))
                end or nil)
            end)
        end
    end

    sel:EnableMouse(true)
    sel:EnableMouseWheel(true)
    sel:SetScript("OnMouseWheel", function(_, delta)
        B.lastStepped = id
        B.Arrow(id, (tonumber(delta) or 0) > 0 and -1 or 1)
    end)
    sel:SetScript("OnMouseUp", function(_, button)
        if button == "RightButton" then
            B.lastStepped = id
            B.Random(id)
        end
    end)
end

-- A selector in the stock look, from the stock template when it is there.
local function buildSelector(name, parent, id, label)
    local ok, sel = pcall(CreateFrame, "Frame", name, parent, "BarberShopSelectorTemplate")

    if not ok or not sel then
        sel = CreateFrame("Frame", name, parent)
        sel:SetWidth(175)
        sel:SetHeight(32)
        -- GameFontNormal's look
        local category = sel:CreateFontString(name .. "Category", "BACKGROUND")
        category:SetFont("Fonts\\FRIZQT__.TTF", 12)
        category:SetTextColor(1, 0.82, 0)
        category:SetWidth(90)
        category:SetHeight(14)
        category:SetPoint("CENTER", sel, "CENTER", 0, 0)

        local function arrow(suffix, file, point, relativePoint, x)
            local b = CreateFrame("Button", name .. suffix, sel)
            b:SetWidth(32)
            b:SetHeight(32)
            b:SetPoint(point, category, relativePoint, x, 0)
            b:SetNormalTexture("Interface\\Buttons\\UI-SpellbookIcon-" .. file .. "Page-Up")
            b:SetPushedTexture("Interface\\Buttons\\UI-SpellbookIcon-" .. file .. "Page-Down")
            b:SetDisabledTexture("Interface\\Buttons\\UI-SpellbookIcon-" .. file .. "Page-Disabled")
            b:SetHighlightTexture("Interface\\Buttons\\UI-Common-MouseHilight", "ADD")
            return b
        end

        arrow("Prev", "Prev", "RIGHT", "LEFT", -5)
        arrow("Next", "Next", "LEFT", "RIGHT", 5)
    end

    sel:SetID(id)
    _G[name .. "Category"]:SetText(label)
    return sel
end

-- The skin selector as CanAlterSkin() says now (the stock code decides once, at load).
function B.FixSkinSelector()
    local four = selectorFrame(4)

    if not four then
        return
    end

    if CanAlterSkin() then
        if not four:IsShown() then
            stockCall("BarberShop_ToFourAttributeFormat")
        end
    elseif four:IsShown() then
        four:Hide()
        local one, two, three = selectorFrame(1), selectorFrame(2), selectorFrame(3)
        two:ClearAllPoints()
        two:SetPoint("TOPLEFT", one, "BOTTOMLEFT", 0, -1)
        three:ClearAllPoints()
        three:SetPoint("TOPLEFT", two, "BOTTOMLEFT", 0, -1)
        local money, okay = _G.BarberShopFrameMoneyFrame, _G.BarberShopFrameOkayButton

        if money then
            money:ClearAllPoints()
            money:SetPoint("TOP", three, "BOTTOM", 7, -10)
        end

        if okay then
            okay:ClearAllPoints()
            okay:SetPoint("RIGHT", three, "BOTTOM", -2, -48)
        end
    end
end

function B.Install()
    local frame = _G.BarberShopFrame

    if B.installed or not frame then
        return
    end

    B.installed = true

    for id = 1, 4 do
        local sel = selectorFrame(id)

        if sel then
            decorate(sel, id)
        end
    end

    -- the mark selectors: a tooltip-framed panel to the left of the barbershop
    local panel = CreateFrame("Frame", "BleakholdBarberMarks", frame)
    panel:SetWidth(214)
    panel:SetHeight(84)
    panel:SetPoint("TOPRIGHT", frame, "TOPLEFT", -4, -60)
    panel:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
                        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border", tile = true, tileSize = 16, edgeSize = 16,
                        insets = { left = 4, right = 4, top = 4, bottom = 4 } })
    panel:SetBackdropColor(0, 0, 0, 0.85)
    panel:SetBackdropBorderColor(1, 0.82, 0)
    panel:Hide()
    B.panel = panel

    local markings = buildSelector("BleakholdBarberMarkings", panel, B.MARKINGS, B.TEXT.markings)
    markings:SetPoint("TOP", panel, "TOP", 0, -10)
    decorate(markings, B.MARKINGS)
    local colour = buildSelector("BleakholdBarberMarkColour", panel, B.MARK_COLOUR, B.TEXT.markColour)
    colour:SetPoint("TOPLEFT", markings, "BOTTOMLEFT", 0, -1)
    decorate(colour, B.MARK_COLOUR)

    frame:HookScript("OnShow", function()
        ns.SafeCall(B.FixSkinSelector)
        B.lastColour = 1
        ns.SafeCall(B.Refresh)
    end)

    for _, name in ipairs({ "BarberShop_UpdateCost", "BarberShop_Update" }) do
        if type(_G[name]) == "function" then
            hooksecurefunc(name, function()
                ns.SafeCall(B.Refresh)
            end)
        end
    end

    if frame:IsShown() then
        B.FixSkinSelector()
    end

    B.Refresh()
end

ns.RegisterEvent("ADDON_LOADED", function(_, name)
    if name == "Blizzard_BarberShopUI" then
        B.Install()
    end
end)

-- loaded before this addon (a reload in the chair)
if IsAddOnLoaded("Blizzard_BarberShopUI") then
    ns.SafeCall(B.Install)
end
