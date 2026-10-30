-- The barbershop's selectors (Barber.lua): n/N, the mouse wheel, Shift-click, right-click, the skin selector following
-- CanAlterSkin(), and the Markings and Mark Colour selectors when the realm's tables have the marks
-- (Tools/RaceForge/README.md, "Bleakhold appearance data contract"). The barbershop here is a stand-in for
-- Blizzard_BarberShopUI's frames and functions, written for this test (not copied from Blizzard's files), over the
-- made-up option lists of Tools/UiLint/glue/customize_data.lua.
local D = host_loadfile(repo .. "/Tools/UiLint/glue/customize_data.lua")()

local function indexOf(list, v)
    for i, x in ipairs(list) do
        if x == v then return i end
    end
    return 0
end

-- A selector as BarberShopSelectorTemplate makes it: a 175 x 32 frame, its category (90 wide), Prev and Next whose
-- OnClick steps the style and updates the cost and the selector.
local function selector(M, name, parent, id, label)
    local E = M.env
    local sel = M.New("Frame", name, parent)
    sel:SetSize(175, 32)
    sel:SetID(id)
    local category = sel:CreateFontString(name .. "Category", "BACKGROUND")
    category:SetFont("Fonts\\FRIZQT__.TTF", 12)
    category:SetWidth(90)
    category:SetText(label)
    for _, side in ipairs({ { "Prev", 1 }, { "Next", nil } }) do
        local b = M.New("Button", name .. side[1], sel)
        b:SetSize(32, 32)
        b:SetScript("OnClick", function(self)
            local p = self:GetParent()
            E.SetNextBarberShopStyle(p:GetID(), side[2])
            E.PlaySound("UChatScrollButton")
            E.BarberShop_UpdateCost()
            E.BarberShop_UpdateSelector(p)
        end)
    end
    return sel
end

-- A player in the barber's chair. opts: race, sex (0/1), kind ("normal"/"deathknight"), stage (customize_data's),
-- face (the character's face, which the barbershop cannot change; default: the first face of the first skin), natives
-- (Bleakhold.exe's functions), canAlterSkin, template (CreateFrame knows BarberShopSelectorTemplate), names.
local function barber(M, opts)
    opts = opts or {}
    local E = M.env
    local race, sex, kind = opts.race or "NightElf", opts.sex or 1, opts.kind or "normal"
    local t = D.Tables(opts.stage or "stage2")[race][sex][kind]
    local face = opts.face
    if face == nil then
        for f = 0, t.numFaces - 1 do
            if t.fits[t.skins[1]][f] then face = f; break end
        end
    end
    -- the skin arrows (SetNextSkin with the face, then only skins with a BarberShopStyle row: all of them here)
    local lists = { t.hairStyles, t.hairColors, t.features, D.SkinWalk(t, face) }
    local K = { lists = lists, face = face, steps = 0, sets = 0, canAlterSkin = opts.canAlterSkin ~= false, toFour = 0,
                costs = 0 }
    -- the picker data of the made-up realm (a fresh copy), unless the test brings its own
    M.ns.BarberData = opts.data or host_loadfile(repo .. "/Tools/UiLint/glue/customize_data.lua")().barber
    K.look = opts.look or { lists[1][1], lists[2][1], lists[3][1], lists[4][1] }
    K.start = { K.look[1], K.look[2], K.look[3], K.look[4] }
    E.UnitRace = function() return race, race end
    E.UnitSex = function() return sex == 1 and 3 or 2 end
    E.UnitClass = function()
        if kind == "deathknight" then return "Death Knight", "DEATHKNIGHT" end
        return "Warrior", "WARRIOR"
    end
    E.GetBarberShopStyleInfo = function(id)
        if id < 1 or id > 4 or (id == 4 and not K.canAlterSkin) then return end
        local name = opts.names and opts.names(id, K.look[id]) or ("Style " .. K.look[id])
        local current = K.look[id] == K.start[id] and 1 or nil
        if not opts.natives then return name, nil, 100, current end
        return name, nil, 100, current, K.look[id], indexOf(lists[id], K.look[id]), #lists[id]
    end
    E.SetNextBarberShopStyle = function(id, backward)
        K.steps = K.steps + 1
        local list = lists[id]
        if not list or (id == 4 and not K.canAlterSkin) then return end
        local i = indexOf(list, K.look[id])
        K.look[id] = list[(i - 1 + (backward and -1 or 1)) % #list + 1]
    end
    E.CanAlterSkin = function() return K.canAlterSkin end
    if opts.natives then
        E.SetBarberShopStyleData = function(id, raw)
            K.sets = K.sets + 1
            if indexOf(lists[id] or {}, raw) == 0 then return false end
            K.look[id] = raw
            return true
        end
    end
    if opts.template then
        local create = E.CreateFrame
        E.CreateFrame = function(otype, name, parent, template, ...)
            if template == "BarberShopSelectorTemplate" then
                K.templated = (K.templated or 0) + 1
                return selector(M, name, parent, 0, "Hair Style")
            end
            return create(otype, name, parent, template, ...)
        end
    end

    -- Blizzard_BarberShopUI.xml: the frame (hidden until the chair), its four selectors (the fourth hidden), the money
    -- frame, the buttons, the banner
    local frame = M.New("Frame", "BarberShopFrame", E.UIParent)
    frame.__shown = false
    frame:SetSize(265, 319)
    local labels = { "Hair Style", "Hair Color", "Facial Style", "Skin Color" }
    local sels = {}
    for i = 1, 4 do
        sels[i] = selector(M, "BarberShopFrameSelector" .. i, frame, i, labels[i])
        if i == 1 then
            sels[i]:SetPoint("TOP", frame, "TOP", 2, -74)
        else
            sels[i]:SetPoint("TOPLEFT", sels[i - 1], "BOTTOMLEFT", 0, -1)
        end
    end
    sels[4].__shown = false
    local money = M.New("Frame", "BarberShopFrameMoneyFrame", frame)
    money:SetPoint("TOP", sels[3], "BOTTOM", 7, -10)
    local okay = M.New("Button", "BarberShopFrameOkayButton", frame)
    okay:SetPoint("RIGHT", sels[3], "BOTTOM", -2, -48)
    local banner = M.New("Frame", "BarberShopBannerFrame", E.UIParent)
    local caption = banner:CreateFontString("BarberShopBannerFrameCaption", "OVERLAY")
    caption:SetFont("Fonts\\FRIZQT__.TTF", 16)
    K.caption = caption
    E.BarberShop_UpdateCost = function() K.costs = K.costs + 1 end
    E.BarberShop_UpdateBanner = function(name) if name then caption:SetText(name) end end
    E.BarberShop_UpdateSelector = function(sel)
        local name = E.GetBarberShopStyleInfo(sel:GetID())
        E.BarberShop_UpdateBanner(name)
    end
    E.BarberShop_Update = function()
        for i = 4, 1, -1 do E.BarberShop_UpdateSelector(sels[i]) end
    end
    E.BarberShop_ToFourAttributeFormat = function()
        K.toFour = K.toFour + 1
        sels[2]:SetPoint("TOPLEFT", sels[1], "BOTTOMLEFT", 0, 3)
        sels[3]:SetPoint("TOPLEFT", sels[2], "BOTTOMLEFT", 0, 3)
        sels[4]:Show()
    end
    -- OnLoad: the four-attribute layout when the skin can change already
    if E.CanAlterSkin() then E.BarberShop_ToFourAttributeFormat() end
    M.addons.Blizzard_BarberShopUI = true
    M.FireEvent("ADDON_LOADED", "Blizzard_BarberShopUI")
    K.sels, K.frame = sels, frame
    return K, frame
end

local function sit(K)
    K.frame:Show()
end

local function count(sel)
    local text = sel.category:GetText() or ""
    local n, N = text:match("|cff%x%x%x%x%x%x(%d+)/(%d+)|r$")
    if n then return tonumber(n), tonumber(N) end
    N = text:match("|cff%x%x%x%x%x%x%-/(%d+)|r$")
    return nil, tonumber(N)
end

local function colour(sel)
    local hex = (sel.category:GetText() or ""):match("|cff(%x%x%x%x%x%x)[%-%d]+/%d+|r$")
    return hex
end

local function hexOf(c)
    return string.format("%02x%02x%02x", math.floor(c[1] * 255 + 0.5), math.floor(c[2] * 255 + 0.5),
        math.floor(c[3] * 255 + 0.5))
end

local function arrow(M, sel, dir)
    local b = dir > 0 and sel.next or sel.prev
    b:Click()
end

test("barber: without Bleakhold.exe's functions the names stay; the wheel and Shift-click step the stock way",
    function(M, ns)
    local K = barber(M, { natives = false, stage = "stage1" })
    local B = ns.Barber
    H.ok(B.installed, "installed on ADDON_LOADED")
    sit(K)
    for id = 1, 4 do
        H.eq(B.selectors[id].category:GetText(), ({ "Hair Style", "Hair Color", "Facial Style", "Skin Color" })[id],
            "selector " .. id .. " text unchanged")
    end
    H.ok(not M.env.BleakholdBarberMarks:IsShown(), "no mark panel")
    local steps = K.steps
    arrow(M, B.selectors[1], 1)
    H.eq(K.steps, steps + 1, "one stock step")
    H.eq(K.look[1], K.lists[1][2])
    M.Fire(B.selectors[1].frame, "OnMouseWheel", -1)
    H.eq(K.look[1], K.lists[1][3], "wheel down: next")
    M.Fire(B.selectors[1].frame, "OnMouseWheel", 1)
    H.eq(K.look[1], K.lists[1][2], "wheel up: back")
    M.shift = true
    arrow(M, B.selectors[2], 1)
    M.shift = false
    H.eq(K.look[2], K.lists[2][6], "Shift-click: five hair colours")
    local look = { K.look[1], K.look[2], K.look[3], K.look[4] }
    M.Fire(B.selectors[3].frame, "OnMouseUp", "RightButton")
    H.eq(K.look[3], look[3], "no random option without the count")
end)

test("barber: n/N on every selector follows the arrows; a Tauren steps every skin both ways", function(M, ns)
    local K = barber(M, { natives = true, stage = "stage1", race = "Tauren", sex = 0 })
    local B = ns.Barber
    sit(K)
    for id = 1, 4 do
        local n, N = count(B.selectors[id])
        H.eq(n, 1, "selector " .. id .. " starts at 1")
        H.eq(N, #K.lists[id], "selector " .. id .. " count")
        H.eq(B.selectors[id].category:GetWidth(), B.CATEGORY_WIDTH, "widened for the number")
    end
    H.eq(#K.lists[4], 36, "36 Tauren skins")
    for id = 1, 4 do
        local N = #K.lists[id]
        for dir = 1, -1, -2 do
            for k = 1, N do
                arrow(M, B.selectors[id], dir)
                local n, total = count(B.selectors[id])
                H.eq(total, N, "selector " .. id .. " count stays")
                H.eq(n, (dir * k) % N + 1, "selector " .. id .. " step " .. k .. " " .. dir)
                H.eq(n, indexOf(K.lists[id], K.look[id]), "the label is where the client is")
            end
        end
    end
    H.ok(not M.env.BleakholdBarberMarks:IsShown(), "stage 1: no mark panel (features = B)")
    H.eq(count(B.selectors[3]), 1, "Facial Style plain")
    -- Shift and the wheel
    M.shift = true
    arrow(M, B.selectors[4], 1)
    M.shift = false
    H.eq(count(B.selectors[4]), 6, "Shift-click: five skins on")
    M.Fire(B.selectors[4].frame, "OnMouseWheel", 1)
    H.eq(count(B.selectors[4]), 5, "wheel up: back one")
    -- right-click: a random skin, nothing else
    local look = { K.look[1], K.look[2], K.look[3], K.look[4] }
    local seen = {}
    for _ = 1, 20 do
        M.Fire(B.selectors[4].frame, "OnMouseUp", "RightButton")
        seen[K.look[4]] = true
        H.ok(K.look[1] == look[1] and K.look[2] == look[2] and K.look[3] == look[3], "only the skin changes")
    end
    local different = 0
    for _ in pairs(seen) do different = different + 1 end
    H.ok(different >= 5, "random skins: " .. different)
end)

test("barber: skin groups colour the skin's number when the data matches the tables", function(M, ns)
    local K = barber(M, { natives = true, stage = "stage1", race = "BloodElf", sex = 0 })
    local B = ns.Barber
    sit(K)
    K.look[4] = 40
    B.Refresh()
    H.eq(colour(B.selectors[4]), hexOf(B.COLORS.fel), "skin 40: fel")
    K.look[4] = 20
    B.Refresh()
    H.eq(colour(B.selectors[4]), hexOf(B.COLORS.marked), "skin 20: marked")
    K.look[4] = 2
    B.Refresh()
    H.eq(colour(B.selectors[4]), hexOf(B.COLORS.plain), "skin 2: plain")
    -- the Death Knight skins at the barbershop, for a Death Knight with one of their faces
    local K2 = barber(M, { natives = true, stage = "stage1", race = "Human", sex = 0, kind = "deathknight", face = 2 })
    K2.look[4] = 27
    B.Refresh()
    H.eq(colour(B.selectors[4]), hexOf(B.COLORS.deathknight), "a Death Knight skin")
end)

test("barber: a Death Knight's skins are the ones of its face; the skin groups follow", function(M, ns)
    -- Human male Death Knight: faces 1, 3-10 and 12-14 on the 12 normal skins, faces 0, 2 and 11 on skins 26-28
    local K = barber(M, { natives = true, stage = "stage2", race = "Human", sex = 0, kind = "deathknight",
                          face = 2 + 40 * 5 })
    local B = ns.Barber
    sit(K)
    H.eq(#K.lists[4], 3, "face 2 with eye 5: the three Death Knight skins")
    local n, N = count(B.selectors[4])
    H.ok(n == 1 and N == 3, "Skin Color 1/3: " .. tostring(n) .. "/" .. tostring(N))
    H.ok(B.state.fresh, "the skin walk is one of the data's")
    H.eq(colour(B.selectors[4]), hexOf(B.COLORS.deathknight), "in the class colour")
    for k = 1, 3 do
        arrow(M, B.selectors[4], 1)
        n, N = count(B.selectors[4])
        H.ok(N == 3 and n == k % 3 + 1, "step " .. k .. ": " .. tostring(n) .. "/" .. tostring(N))
        H.eq(colour(B.selectors[4]), hexOf(B.COLORS.deathknight), "still a Death Knight skin")
    end
    -- the same Death Knight with a face of the normal skins
    local K2 = barber(M, { natives = true, stage = "stage2", race = "Human", sex = 0, kind = "deathknight", face = 13 })
    sit(K2)
    B.Refresh()
    n, N = count(B.selectors[4])
    H.ok(n == 1 and N == 12, "face 13: the 12 normal skins: " .. tostring(n) .. "/" .. tostring(N))
    H.ok(B.state.fresh, "groups live")
    K2.look[4] = 5
    B.Refresh()
    H.eq(colour(B.selectors[4]), hexOf(B.COLORS.marked), "skin 5 is marked")
    -- a walk no face of the data has: plain, logged once
    K2.lists[4] = { 0, 1, 2, 3, 26 }
    K2.look[4] = 26
    B.Refresh()
    H.ok(not B.state.fresh and colour(B.selectors[4]) == hexOf(B.COLORS.plain), "an unknown walk: plain")
    local logged = 0
    for _, l in ipairs(B.log) do if l:find("no skin groups", 1, true) then logged = logged + 1 end end
    B.Refresh()
    local again = 0
    for _, l in ipairs(B.log) do if l:find("no skin groups", 1, true) then again = again + 1 end end
    H.ok(logged == 1 and again == 1, "logged once: " .. logged .. " " .. again)
    H.eq(ns.errors, 0, "no caught errors")
end)

test("barber: the marks: a Markings and a Mark Colour selector, Facial Style steps the base feature", function(M, ns)
    local Bn = D.SPEC.NightElf[1].B
    local data = D.barber.races.NightElf[1]
    local K = barber(M, { natives = true, stage = "stage2", race = "NightElf", sex = 1, names = function(id, raw)
        if id == 3 and raw >= Bn then
            local look = math.floor(raw / Bn)
            return data.designs[math.floor((look - 1) / 3) + 1] .. ", " .. data.colours[(look - 1) % 3 + 1]
        end
        return "Style " .. raw
    end })
    local B = ns.Barber
    sit(K)
    local panel = M.env.BleakholdBarberMarks
    H.ok(panel:IsShown(), "the mark panel shows")
    local p, rel, rp = panel:GetPoint(1)
    H.ok(p == "TOPRIGHT" and rel == K.frame and rp == "TOPLEFT", "left of the barbershop")
    H.eq(panel.__backdrop.edgeFile, "Interface\\Tooltips\\UI-Tooltip-Border", "the stock tooltip frame")
    local markings, colourSel = B.selectors[B.MARKINGS], B.selectors[B.MARK_COLOUR]
    H.eq(markings.frame:GetName(), "BleakholdBarberMarkings")
    H.ok(markings.category:GetText():find("^Markings"), "named Markings")
    H.ok(colourSel.category:GetText():find("^Mark Colour"), "named Mark Colour")
    H.eq(select(2, count(B.selectors[3])), Bn, "Facial Style: the base features: " .. tostring(select(2, count(B.selectors[3]))))
    local n, N = count(markings)
    H.ok(n == 1 and N == 5, "Markings 1/5")
    n, N = count(colourSel)
    H.ok(n == nil and N == 3 and not colourSel.next:IsEnabled(), "Mark Colour off without a design")
    arrow(M, markings, 1)
    H.eq(K.look[3], Bn, "design 1, colour 1, feature 0")
    H.eq(K.caption:GetText(), "Moonwell Sigils, Elune Blue", "the banner names the mark")
    H.eq(colour(markings), hexOf(B.COLORS.glowing), "a glowing mark")
    H.ok(colourSel.next:IsEnabled(), "the colour selector wakes")
    arrow(M, colourSel, -1)
    H.eq(K.look[3], 3 * Bn, "colour back to the paint")
    H.eq(K.caption:GetText(), "Moonwell Sigils, Midnight Ink", "the banner follows")
    H.eq(colour(colourSel), hexOf(B.COLORS.marked), "paint: a plain mark")
    arrow(M, B.selectors[3], 1)
    H.eq(K.look[3], 3 * Bn + 1, "Facial Style: the next base feature, the mark kept")
    arrow(M, B.selectors[3], -1)
    arrow(M, B.selectors[3], -1)
    H.eq(K.look[3], 3 * Bn + Bn - 1, "wraps inside the look")
    M.shift = true
    arrow(M, markings, 1)
    M.shift = false
    H.eq(math.floor(K.look[3] / Bn), 3, "Shift-click on Markings: five of five")
    M.Fire(markings.frame, "OnMouseWheel", -1)
    H.eq(math.floor(K.look[3] / Bn), 6, "wheel down: design 2 in the paint colour")
    -- walk every selector both ways: the label follows
    for _, id in ipairs({ 1, 2, 3, 4, B.MARKINGS, B.MARK_COLOUR }) do
        local sel = B.selectors[id]
        local n0, total = count(sel)
        for dir = 1, -1, -2 do
            for k = 1, total do
                arrow(M, sel, dir)
                local n1, t1 = count(sel)
                H.eq(t1, total, "selector " .. id .. " count stays")
                H.eq(n1, (n0 - 1 + dir * k) % total + 1, "selector " .. id .. " step " .. k)
            end
        end
    end
    -- right-click Markings: only the design
    local base = K.look[3] % Bn
    local designs = {}
    for _ = 1, 30 do
        M.Fire(markings.frame, "OnMouseUp", "RightButton")
        designs[math.floor((math.floor(K.look[3] / Bn) + 2) / 3)] = true
        H.eq(K.look[3] % Bn, base, "the base feature stays")
    end
    H.ok(designs[0] and designs[4], "random designs, none included")
    -- back to no markings: the banner says so
    while math.floor(K.look[3] / Bn) ~= 0 do arrow(M, markings, -1) end
    H.eq(K.caption:GetText(), "No markings")
    H.eq(ns.errors, 0, "no caught errors")
end)

test("barber: the skin selector follows CanAlterSkin() at every opening", function(M, ns)
    local K = barber(M, { natives = true, stage = "stage1", race = "Human", sex = 0, canAlterSkin = false })
    local B = ns.Barber
    H.ok(not K.sels[4]:IsShown(), "no skin selector at load")
    K.canAlterSkin = true
    sit(K)
    H.eq(K.toFour, 1, "the four-selector layout on opening")
    H.ok(K.sels[4]:IsShown(), "the skin selector shows")
    K.frame:Hide()
    K.canAlterSkin = false
    sit(K)
    H.ok(not K.sels[4]:IsShown(), "hidden again when the skin cannot change")
    local _, rel, _, _, y = K.sels[2]:GetPoint(1)
    H.ok(rel == K.sels[1] and y == -1, "the three-selector spacing back")
    _, rel = M.env.BarberShopFrameMoneyFrame:GetPoint(1)
    H.eq(rel, K.sels[3], "the money under the third selector")
    H.eq(select(2, count(B.selectors[4])), nil, "no number on a hidden skin selector")
end)

test("barber: data that does not match the tables gives plain selectors", function(M, ns)
    -- a data file whose B is off by one for Night Elf female
    local data = host_loadfile(repo .. "/Tools/UiLint/glue/customize_data.lua")().barber
    data.races.NightElf[1].B = 18
    data.races.NightElf[1].normal.features = 13 * 18
    local K = barber(M, { natives = true, stage = "stage2", race = "NightElf", sex = 1, data = data })
    local B = ns.Barber
    sit(K)
    H.ok(not M.env.BleakholdBarberMarks:IsShown(), "no mark panel")
    H.eq(select(2, count(B.selectors[3])), 13 * 19, "Facial Style: the plain n/N of the arrows")
    H.ok(B.log[1] and B.log[1]:find("no mark selectors", 1, true), "logged: " .. tostring(B.log[1]))
    -- the data and the tables agree on the counts but the client refuses a value: plain from then on
    ns.BarberData.races.NightElf[1].B = 19
    ns.BarberData.races.NightElf[1].normal.features = 13 * 19
    K.lists[3] = {}
    for v = 0, 13 * 19 - 1 do K.lists[3][#K.lists[3] + 1] = v == 19 and 1000 or v end
    B.Refresh()
    H.ok(M.env.BleakholdBarberMarks:IsShown(), "counts match: the panel shows")
    arrow(M, B.selectors[B.MARKINGS], 1)
    H.ok(not M.env.BleakholdBarberMarks:IsShown(), "the refused value hides it")
    H.ok(B.stale["NightElf:1:normal"], "marked stale")
end)

test("barber: the mark selectors come from the stock template when the barbershop has it", function(M, ns)
    local K = barber(M, { natives = true, stage = "stage2", template = true })
    local B = ns.Barber
    H.eq(K.templated, 2, "two selectors from BarberShopSelectorTemplate")
    H.eq(B.selectors[B.MARKINGS].frame:GetID(), B.MARKINGS, "with Bleakhold's ids")
    sit(K)
    H.ok(B.selectors[B.MARKINGS].category:GetText():find("^Markings"), "named")
    arrow(M, B.selectors[B.MARKINGS], 1)
    H.eq(math.floor(K.look[3] / D.SPEC.NightElf[1].B), 1, "and they step the marks")
end)
