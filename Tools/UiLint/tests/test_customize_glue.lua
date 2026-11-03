-- The appearance rows of character creation and of the paid customization screen (Interface/Bleakhold/Glue/
-- BleakholdCustomize.lua, the name lock in BleakholdNames.lua) and the picker data they read (Tools/RaceForge/README.md,
-- "Bleakhold appearance data contract", "Picker data").
--
-- This file runs in two harnesses:
--   * the glue scenarios (Tools/UiLint/glue/run.sh, scenarios picker-*): tests.lua loads it after the glue TOC and
--     calls the function it returns, on the mock of the glue API with the stock rows and the option lists of
--     Tools/UiLint/glue/customize_stock.lua and the made-up data of customize_data.lua;
--   * the addon's Lua tests (Tools/UiLint/testrunner.lua): there it checks the shipped data files
--     (BleakholdCustomizeData.lua, BarberData.lua) and the made-up data against the contract's shape.

-- --------------------------------------------------------------------------------------------- the shape

local SEXES = { [0] = true, [1] = true }

local function isInt(v, lo, hi)
    return type(v) == "number" and v == math.floor(v) and v >= lo and v <= hi
end

local function ascending(list, lo, hi)
    if type(list) ~= "table" then
        return false
    end

    local last = -1

    for i, v in ipairs(list) do
        if not isInt(v, lo, hi) or v <= last then
            return false
        end

        last = v
    end

    return #list > 0
end

local function isCount(v)
    if type(v) == "number" then
        return isInt(v, 0, 256)
    end

    if type(v) ~= "table" or not isInt(v.default, 0, 256) then
        return false
    end

    for k, n in pairs(v) do
        if k ~= "default" and not (isInt(k, 0, 255) and isInt(n, 0, 256)) then
            return false
        end
    end

    return true
end

-- Problems of a picker data table (barber: BarberData.lua's flavour, no face walks), as a list of texts.
local function contractProblems(data, barber)
    local out = {}

    local function bad(fmt, ...)
        out[#out + 1] = string.format(fmt, ...)
    end

    if type(data) ~= "table" then
        bad("not a table")
        return out
    end

    if data.version ~= 1 then bad("version %s", tostring(data.version)) end
    if data.eyeStride ~= 40 then bad("eyeStride %s", tostring(data.eyeStride)) end
    if data.looksPerDesign ~= 3 then bad("looksPerDesign %s", tostring(data.looksPerDesign)) end
    local groups = data.groups

    if type(groups) ~= "table" or groups[1] ~= "plain" or groups[2] ~= "marked" or groups[3] ~= "fel"
        or groups[4] ~= "deathknight" then
        bad("groups are not plain, marked, fel, deathknight")
        groups = {}
    end

    if type(data.races) ~= "table" then
        bad("no races table")
        return out
    end

    for race, sexes in pairs(data.races) do
        if type(race) ~= "string" or not race:find("^%u%a+$") then bad("race key %s", tostring(race)) end

        for sex, e in pairs(type(sexes) == "table" and sexes or {}) do
            local where = tostring(race) .. " " .. tostring(sex)

            if not SEXES[sex] or type(e) ~= "table" then
                bad("%s: the sex is 0 or 1 and its block a table", where)
            else
                if not isInt(e.B, 1, 255) then bad("%s: B %s", where, tostring(e.B)) end
                if e.looks ~= 1 and e.looks ~= 13 then bad("%s: looks %s", where, tostring(e.looks)) end

                if e.looks == 13 then
                    if type(e.designs) ~= "table" or #e.designs ~= 4 then bad("%s: 4 designs", where) end
                    if type(e.colours) ~= "table" or #e.colours ~= 3 then bad("%s: 3 colours", where) end
                    if type(e.eyes) ~= "table" or #e.eyes < 1 or #e.eyes > 5 then bad("%s: eyes 1-5", where) end
                    if isInt(e.B, 1, 255) and 13 * e.B - 1 > 255 then bad("%s: 13 * B - 1 above 255", where) end
                end

                if type(e.skinGroup) ~= "table" then bad("%s: no skinGroup", where) end

                for _, kind in ipairs({ "normal", "deathKnight" }) do
                    local v = e[kind]
                    local at = where .. " " .. kind

                    if type(v) ~= "table" then
                        bad("%s: missing", at)
                    else
                        if not ascending(v.skins, 0, 255) then bad("%s: skins are not ascending raw values", at) end

                        for _, s in ipairs(type(v.skins) == "table" and v.skins or {}) do
                            local code = type(e.skinGroup) == "table" and e.skinGroup[s]
                            if not (isInt(code, 1, #groups) or #groups == 0) then bad("%s: skin %d has no group", at, s) end
                        end

                        -- the skin walks: one list per group of faces, every listed skin in one of them
                        local inSets = {}

                        if type(v.skinSets) ~= "table" or #v.skinSets == 0 then
                            bad("%s: no skinSets", at)
                        else
                            for i, set in ipairs(v.skinSets) do
                                if not ascending(set, 0, 255) then bad("%s: skin set %d not ascending", at, i) end
                                for _, sk in ipairs(type(set) == "table" and set or {}) do inSets[sk] = true end
                            end
                        end

                        for _, sk in ipairs(type(v.skins) == "table" and v.skins or {}) do
                            if not inSets[sk] then bad("%s: skin %d is in no skin set", at, sk) end
                        end

                        local function listOf(sets, count, key)
                            local i = type(count) == "number" and count
                                or type(count) == "table" and (count[key] or count.default)
                            return type(sets) == "table" and isInt(i, 1, #sets) and sets[i]
                        end

                        if barber then
                            if v.faceWalks ~= nil or v.skinSetOfFace ~= nil then
                                bad("%s: the barbershop has no face walks and cannot read the face", at)
                            end
                        else
                            if not isCount(v.skinSetOfFace) or not listOf(v.skinSets, v.skinSetOfFace, 0) then
                                bad("%s: skinSetOfFace does not name a skin set", at)
                            end

                            if type(v.faceWalks) ~= "table" or #v.faceWalks == 0 then
                                bad("%s: no faceWalks", at)
                            else
                                for i, walk in ipairs(v.faceWalks) do
                                    if not ascending(walk, 0, 255) then bad("%s: face walk %d not ascending", at, i) end
                                    for _, f in ipairs(type(walk) == "table" and walk or {}) do
                                        if math.floor(f / 40) > 5 then bad("%s: face %d has eye above 5", at, f) end
                                        if not listOf(v.skinSets, v.skinSetOfFace, f) then
                                            bad("%s: face %d has no skin set", at, f)
                                        end
                                    end
                                end
                            end

                            for _, sk in ipairs(type(v.skins) == "table" and v.skins or {}) do
                                if not (isCount(v.faceWalkOfSkin) and listOf(v.faceWalks, v.faceWalkOfSkin, sk)) then
                                    bad("%s: skin %d has no face walk", at, sk)
                                end
                            end
                        end

                        for _, key in ipairs({ "hairStyles", "hairColors", "features" }) do
                            if not isCount(v[key]) then bad("%s: %s is not a count", at, key) end
                        end

                        local features = type(v.features) == "table" and v.features.default or v.features

                        if isInt(e.B, 1, 255) and type(e.looks) == "number" and features ~= e.looks * e.B then
                            bad("%s: features %s is not looks * B", at, tostring(features))
                        end
                    end
                end
            end
        end
    end

    return out
end

-- The glue's and the barber's files describe the same races the same way where both have them.
local function agreementProblems(glue, barberData)
    local out = {}

    for _, key in ipairs({ "version", "eyeStride", "looksPerDesign" }) do
        if glue[key] ~= barberData[key] then out[#out + 1] = key .. " differs" end
    end

    for race, sexes in pairs(glue.races or {}) do
        for sex, e in pairs(sexes) do
            local b = barberData.races and barberData.races[race] and barberData.races[race][sex]

            if b then
                if b.B ~= e.B or b.looks ~= e.looks then out[#out + 1] = race .. " " .. sex .. ": B or looks differ" end

                for _, list in ipairs({ "designs", "colours" }) do
                    for i, name in ipairs(e[list] or {}) do
                        if (b[list] or {})[i] ~= name then out[#out + 1] = race .. " " .. sex .. ": " .. list .. " differ" end
                    end
                end
            end
        end
    end

    return out
end

-- ------------------------------------------------------------------------------- the addon's Lua tests

if MOCK == nil then
    local D = host_loadfile(repo .. "/Tools/UiLint/glue/customize_data.lua")()

    local function shipped()
        local env = {}
        local chunk = assert(host_loadfile(repo .. "/Interface/Bleakhold/Glue/BleakholdCustomizeData.lua"))
        setfenv(chunk, env)
        chunk()
        return env.BleakholdCustomizeData
    end

    test("customize data: the shipped picker data files have the contract's shape", function(M, ns)
        local glue = shipped()
        local problems = contractProblems(glue, false)
        H.ok(#problems == 0, "BleakholdCustomizeData.lua: " .. table.concat(problems, "; "))
        problems = contractProblems(ns.BarberData, true)
        H.ok(#problems == 0, "BarberData.lua: " .. table.concat(problems, "; "))
        problems = agreementProblems(glue, ns.BarberData)
        H.ok(#problems == 0, "the two files agree: " .. table.concat(problems, "; "))
    end)

    test("customize data: the tests' made-up data has the contract's shape, and the checks catch a broken file",
        function(M, ns)
        H.eq(#contractProblems(D.glue, false), 0, "made-up glue data: " .. table.concat(contractProblems(D.glue), "; "))
        H.eq(#contractProblems(D.barber, true), 0, "made-up barber data")
        H.eq(#agreementProblems(D.glue, D.barber), 0, "they agree")
        H.ok(#contractProblems(D.barber, false) > 0, "barber data has no face walks, so it is not glue data")
        H.ok(#contractProblems(D.glue, true) > 0, "glue data has face walks, so it is not barber data")
        H.ok(#contractProblems({ version = 2 }, false) > 0, "a later version is refused")
        local broken = host_loadfile(repo .. "/Tools/UiLint/glue/customize_data.lua")().glue
        broken.races.Human[0].normal.features = 100
        broken.races.Human[1].normal.skins = { 3, 2 }
        broken.races.NightElf[1].B = 30
        local problems = contractProblems(broken, false)
        H.ok(#problems >= 3, "three faults found: " .. table.concat(problems, "; "))
    end)

    return
end

-- ------------------------------------------------------------------------------------- the glue scenarios

return function(ctx)
    local check, SCENARIO, HARNESS = ctx.check, ctx.scenario, ctx.harness
    local D = assert(host_loadfile(HARNESS .. "/customize_data.lua"))()
    local C = BleakholdGlue.Customize
    local CZ = MOCK.customize

    check(C ~= nil and C.installed, "the rows are installed")
    check(#contractProblems(D.glue, false) == 0, "the made-up data has the contract's shape")

    local RACES = { { name = "Human", file = "Human", faction = "Alliance" },
                    { name = "Night Elf", file = "NightElf", faction = "Alliance" },
                    { name = "Blood Elf", file = "BloodElf", faction = "Horde" },
                    { name = "High Elf", file = "HighElf", faction = "Alliance" },
                    { name = "Tauren", file = "Tauren", faction = "Horde" } }
    MOCK.setRaces(RACES)

    local function deepCopy(t)
        if type(t) ~= "table" then return t end
        local r = {}
        for k, v in pairs(t) do r[k] = deepCopy(v) end
        return r
    end

    local function indexOf(list, v)
        for i, x in ipairs(list) do if x == v then return i end end
        return 0
    end

    local function countText(i)
        local r = C.rows[i]
        return r and r.count:IsShown() and r.count:GetText() or nil
    end
    local function click(i, dir)
        local r = C.rows[i]
        local b = dir > 0 and r.right or r.left
        b:Click()
    end
    local function wheel(i, delta) C.rows[i].frame:_fire("OnMouseWheel", delta) end
    local function rightClick(i) C.rows[i].frame:_fire("OnMouseUp", "RightButton") end
    local function shown(i) return C.rows[i] and C.rows[i].frame:IsShown() ~= nil end
    local function colourOf(i) local r, g, b = C.rows[i].count:GetTextColor(); return { r, g, b } end
    local function sameColour(a, b) return math.abs(a[1] - b[1]) < 0.01 and math.abs(a[2] - b[2]) < 0.01 and math.abs(a[3] - b[3]) < 0.01 end
    -- the native position of a stock row, from the mock client's lists
    local function nativePos(row) return indexOf(CZ.list(row), CZ.look[row]), #CZ.list(row) end
    local function noErrors(when)
        check(#BLEAKHOLD_GLUE_ERRORS == 0, when .. ": no caught errors: " .. table.concat(BLEAKHOLD_GLUE_ERRORS, " | "))
    end
    local function logHas(text)
        for _, l in ipairs(C.log) do if l:find(text, 1, true) then return true end end
        return false
    end

    -- Every stock row of every decorated frame: the stock look (template, arrows), plus the Bleakhold parts.
    local function checkDecorated()
        for i = 1, 5 do
            local r = C.rows[i]
            check(r ~= nil and r.frame == _G["CharacterCustomizationButtonFrame" .. i], "row " .. i .. " decorated")
            check(r.frame._wheel == true, "row " .. i .. " takes the mouse wheel")
            check(r.lock:GetObjectType() == "CheckButton" and r.lock:GetNormalTexture():GetTexture()
                  == "Interface\\Buttons\\UI-CheckBox-Up", "row " .. i .. " lock is a stock check box")
        end
    end

    -- Walks every shown row forward then back through its right and left arrows and checks the label each time: one
    -- step moves n by one, wrapping at N, and N does not change (the label equals what the arrows reach).
    local function walkAll(label)
        local bad = 0
        for i = 1, 8 do
            if shown(i) and countText(i) and C.rows[i].right:IsEnabled() then
                local n0, N = countText(i):match("^(%d+)/(%d+)$")
                n0, N = tonumber(n0), tonumber(N)
                for dir = 1, -1, -2 do
                    for k = 1, N do
                        click(i, dir)
                        local n, M = (countText(i) or ""):match("^(%d+)/(%d+)$")
                        local want = (n0 - 1 + dir * k) % N + 1
                        if tonumber(M) ~= N or tonumber(n) ~= want then
                            bad = bad + 1
                            check(false, string.format("%s: row %d step %d %s: %s, want %d/%d", label, i, k,
                                dir > 0 and "right" or "left", tostring(countText(i)), want, N))
                            break
                        end
                        if i <= 5 and not (i == 2 and C.state.eyes) and not (i == 5 and C.state.marks) then
                            local p, c = nativePos(i)
                            if p ~= tonumber(n) or c ~= N then
                                bad = bad + 1
                                check(false, string.format("%s: row %d shows %s, the client is at %d/%d", label, i,
                                    tostring(countText(i)), p, c))
                                break
                            end
                        end
                    end
                end
            end
        end
        return bad
    end

    local function showScreen()
        SetGlueScreen("login")
        SetGlueScreen("charcreate")
    end

    -- ------------------------------------------------------------------------ an exe without the functions

    if SCENARIO == "picker-stock" then
        check(not C.HasNatives(), "no Bleakhold glue functions")
        CZ.tables = D.Tables("stage2")
        BleakholdCustomizeData = D.glue
        showScreen()
        checkDecorated()
        for i = 1, 8 do
            check(countText(i) == nil, "no number on row " .. i)
            check(not C.rows[i].lock:IsShown(), "no lock on row " .. i)
        end
        for i = 6, 8 do check(not shown(i), "no added row " .. i) end
        local skin = CZ.look[1]
        local sounds = #MOCK.sounds
        click(1, 1)
        check(CZ.look[1] == CZ.list(1)[indexOf(CZ.list(1), skin) + 1], "the arrow steps the skin through the stock call")
        check(#MOCK.sounds == sounds + 1 and MOCK.sounds[#MOCK.sounds] == "gsCharacterCreationLook", "with the stock sound")
        local cycles = CZ.cycles
        wheel(3, -1)
        check(CZ.cycles == cycles + 1 and CZ.look[3] == CZ.list(3)[2], "wheel down: the next hair style")
        wheel(3, 1)
        check(CZ.look[3] == CZ.list(3)[1], "wheel up: back")
        MOCK.shift = true
        cycles = CZ.cycles
        click(4, 1)
        MOCK.shift = false
        check(CZ.cycles == cycles + 5 and CZ.look[4] == CZ.list(4)[6], "Shift-click: five steps")
        local randomized = #CZ.randomized
        CharCreateRandomizeButton:Click()
        check(#CZ.randomized == randomized + 1 and CZ.randomized[#CZ.randomized] == 0, "Randomize: the stock call, no mask")
        local look = deepCopy(CZ.look)
        rightClick(2)
        check(CZ.look[2] == look[2] and #CZ.randomized == randomized + 1, "right-click does nothing without the functions")
        CZ.look[5] = CZ.list(5)[1]
        click(5, -1)
        check(CZ.look[5] == CZ.list(5)[#CZ.list(5)], "features left wraps to the last one")
        noErrors("stock exe")
        return
    end

    -- ------------------------------------------------------------------- the functions, no picker data yet

    if SCENARIO == "picker-plain" then
        check(C.HasNatives(), "the Bleakhold glue functions")
        showScreen()
        checkDecorated()
        local expect = { "1/9", "1/6", "1/8", "1/10", "1/5" }
        for i = 1, 5 do
            check(countText(i) == expect[i], "row " .. i .. ": " .. tostring(countText(i)))
            check(sameColour(colourOf(i), C.COLORS.plain), "row " .. i .. " plain white")
            check(C.rows[i].lock:IsShown() and not C.rows[i].lock:GetChecked(), "row " .. i .. " lock shown, open")
        end
        for i = 6, 8 do check(not shown(i), "no added row " .. i .. " without data") end
        local text = CharacterCustomizationButtonFrame1Text
        local _, rel, _, x = text:GetPoint(1)
        check(rel == CharacterCustomizationButtonFrame1Middle and x == -12, "the name moves left of the number")
        check(walkAll("plain") == 0, "every row's label follows its arrows")
        -- Shift-click and the wheel
        MOCK.shift = true
        click(1, 1)
        MOCK.shift = false
        check(countText(1) == "6/9", "Shift-click: five skins on: " .. tostring(countText(1)))
        wheel(1, 1)
        check(countText(1) == "5/9", "wheel up: one back: " .. tostring(countText(1)))
        wheel(2, -1)
        check(countText(2) == "2/6", "wheel down on the face: " .. tostring(countText(2)))
        -- locks and Randomize
        C.rows[1].lock:Click()
        C.rows[3].lock:Click()
        check(C.locks[1] and C.locks[3], "rows 1 and 3 locked")
        local look = deepCopy(CZ.look)
        for _ = 1, 5 do
            CharCreateRandomizeButton:Click()
            check(CZ.randomized[#CZ.randomized] == 1 + 4, "Randomize keeps the locked rows (mask 5)")
            check(CZ.look[1] == look[1] and CZ.look[3] == look[3], "skin and hair style kept")
        end
        C.rows[1].lock:Click()
        C.rows[3].lock:Click()
        CharCreateRandomizeButton:Click()
        check(CZ.randomized[#CZ.randomized] == 0, "all open: the stock randomize (no mask)")
        rightClick(2)
        check(CZ.randomized[#CZ.randomized] == 31 - 2, "right-click on the face rolls only the face")
        rightClick(5)
        check(CZ.randomized[#CZ.randomized] == 31 - 16, "right-click on the features rolls only the features")
        local p, n = nativePos(5)
        check(countText(5) == p .. "/" .. n, "the label follows a randomize")
        -- behind the rows' back: the poll notices
        CZ.look[4] = CZ.list(4)[3]
        BleakholdCustomizePoll:_fire("OnUpdate", 1)
        check(countText(4) == "3/10", "the poll reads a change made elsewhere: " .. tostring(countText(4)))
        -- tooltip
        C.rows[3].frame:_fire("OnEnter")
        check(CharacterCreateTooltip:IsShown() and CharacterCreateTooltip._text:find("Mouse wheel", 1, true),
              "the row's tooltip has the hints")
        C.rows[3].frame:_fire("OnLeave")
        check(not CharacterCreateTooltip:IsShown(), "and hides")
        -- an off-list value: no number to show
        CZ.look[3] = 99
        C.Refresh()
        check(countText(3) == "-/8", "a value off the list: -/N: " .. tostring(countText(3)))
        noErrors("plain")
        return
    end

    -- ---------------------------------------------------------------------------------- with picker data

    BleakholdCustomizeData = deepCopy(D.glue)
    local stage = SCENARIO == "picker-stage0" and "stage0" or SCENARIO == "picker-stage1" and "stage1" or "stage2"
    CZ.tables = D.Tables(stage)

    if SCENARIO == "picker-stage0" or SCENARIO == "picker-stage1" then
        showScreen()
        for i = 6, 8 do check(not shown(i), stage .. ": no added row " .. i) end
        for _, r in ipairs({ 1, 2, 3 }) do
            SetSelectedRace(r)
            SetCharacterRace(r)
            local list = CZ.list(1)
            check(countText(1) == "1/" .. #list, stage .. ": skins n/N of the arrows: " .. tostring(countText(1)))
            check(countText(5) == "1/" .. #CZ.list(5), stage .. ": features n/N")
            check(walkAll(stage .. " race " .. r) == 0, stage .. ": labels follow the arrows")
        end
        if stage == "stage1" then
            check(not logHas("no Eyes row") and not logHas("no mark rows"), "stage 1 is expected: nothing logged")
            -- Blood Elf male, skin 40 is fel in the data: its number is fel green
            SetSelectedRace(3)
            SetSelectedSex(2)
            SetCharacterRace(3)
            CZ.setValue(1, 40)
            C.Refresh()
            check(sameColour(colourOf(1), C.COLORS.fel), "a fel skin's number is fel green")
            CZ.setValue(1, 20)
            C.Refresh()
            check(sameColour(colourOf(1), C.COLORS.marked), "a marked skin's number is gold")
            CZ.setValue(1, 1)
            C.Refresh()
            check(sameColour(colourOf(1), C.COLORS.plain), "a plain skin's number is white")
        else
            check(logHas("no skin groups"), "today's tables: the skin count mismatch is logged")
            check(logHas("no Eyes row") and logHas("no mark rows"), "and the face and features ones")
            SetSelectedRace(3)
            SetCharacterRace(3)
            CZ.setValue(1, 5)
            C.Refresh()
            check(sameColour(colourOf(1), C.COLORS.plain), "no groups on a data mismatch")
        end
        noErrors(stage)
        return
    end

    -- stage 2: marks and eyes in the tables
    local stride = D.STRIDE

    local function eyeOf() return math.floor(CZ.look[2] / stride) end
    local function baseOf() return CZ.look[2] % stride end
    local function lookOf(B) return math.floor(CZ.look[5] / B) end

    if SCENARIO == "picker-marks" then
        SetSelectedRace(2)
        SetSelectedSex(3) -- Night Elf female, B 19
        showScreen()
        local B = D.SPEC.NightElf[1].B
        check(C.state.eyes and C.state.marks, "eyes and marks are live")
        for i = 6, 8 do check(shown(i), "added row " .. i .. " shown") end
        check(BleakholdCustomizeEyesText:GetText() == "Eyes" and BleakholdCustomizeMarkingsText:GetText() == "Markings"
              and BleakholdCustomizeMarkColourText:GetText() == "Mark Colour", "their names")
        local p, rel, rp, x, y = BleakholdCustomizeMarkColour:GetPoint(1)
        check(p == "BOTTOMLEFT" and rel == CharacterCustomizationButtonFrame5 and rp == "BOTTOMRIGHT" and x == 24 and y == 0,
              "the added column starts right of the Features row")
        p, rel = BleakholdCustomizeEyes:GetPoint(1)
        check(p == "BOTTOM" and rel == BleakholdCustomizeMarkings, "Eyes on top of Markings")
        check(BleakholdCustomizeEyesLeftButton ~= nil and BleakholdCustomizeEyes:GetID() == 6, "the stock row template")
        check(countText(2) == "1/9", "Face: the base faces only: " .. tostring(countText(2)))
        check(countText(5) == "1/" .. B, "Features: the base features only: " .. tostring(countText(5)))
        check(countText(6) == "1/4", "Eyes: race default and three colours: " .. tostring(countText(6)))
        check(countText(7) == "1/5", "Markings: none and four designs")
        check(countText(8) == "-/3" and not C.rows[8].right:IsEnabled(), "Mark Colour off without a design")
        check(C.rows[6].lock:GetChecked() and C.rows[7].lock:GetChecked() and C.rows[8].lock:GetChecked(),
              "the added rows start locked")
        -- eyes
        click(6, 1)
        check(eyeOf() == 1 and baseOf() == 0 and countText(6) == "2/4", "Eyes right: the first eye colour, same face")
        check(sameColour(colourOf(6), C.COLORS.glowing), "a glowing eye")
        check(countText(2) == "1/9", "the Face row keeps its place")
        click(2, 1)
        check(baseOf() == 1 and eyeOf() == 1 and countText(2) == "2/9", "Face right: the next face, the eyes kept")
        click(2, -1)
        click(2, -1)
        check(baseOf() == 8 and eyeOf() == 1 and countText(2) == "9/9", "Face left wraps, the eyes kept")
        C.rows[6].frame:_fire("OnEnter")
        check(CharacterCreateTooltip._text:find("Moonlight Silver", 1, true), "the eye's name in the tooltip")
        C.rows[6].frame:_fire("OnLeave")
        -- markings
        click(7, 1)
        check(lookOf(B) == 1 and CZ.look[5] % B == 0, "Markings right: design 1 in colour 1")
        check(countText(7) == "2/5" and countText(8) == "1/3" and C.rows[8].right:IsEnabled(), "the colour row wakes")
        check(sameColour(colourOf(7), C.COLORS.glowing), "a glowing mark")
        C.rows[7].frame:_fire("OnEnter")
        check(CharacterCreateTooltip._text:find("Moonwell Sigils", 1, true), "the design's name in the tooltip")
        click(8, 1)
        click(8, 1)
        check(lookOf(B) == 3 and countText(8) == "3/3", "Mark Colour to the paint colour")
        check(sameColour(colourOf(8), C.COLORS.marked), "paint is a plain mark (gold), not glowing")
        C.rows[8].frame:_fire("OnEnter")
        check(CharacterCreateTooltip._text:find("Midnight Ink (paint)", 1, true), "the colour and its kind in the tooltip")
        click(8, 1)
        check(lookOf(B) == 1, "Mark Colour wraps")
        click(7, 1)
        check(lookOf(B) == 4, "the next design keeps the colour (look 3 * (2 - 1) + 1)")
        click(5, 1)
        check(CZ.look[5] == 4 * B + 1 and countText(5) == "2/" .. B, "Features right: the next base, the mark kept")
        click(5, -1)
        click(5, -1)
        check(CZ.look[5] == 4 * B + B - 1, "Features left wraps inside the look")
        MOCK.shift = true
        click(7, 1)
        MOCK.shift = false
        check(lookOf(B) == 4, "Shift-click on Markings: five of five, the same design")
        click(7, -1)
        click(7, -1)
        check(lookOf(B) == 0 and countText(7) == "1/5" and countText(8) == "-/3", "back to no markings")
        click(7, 1)
        check(lookOf(B) == 1, "a design again starts from the last colour (1)")
        click(8, -1)
        click(7, -1)
        click(7, 1)
        check(lookOf(B) == 3, "the last colour is remembered (3)")
        -- the wheel on an added row
        wheel(6, -1)
        check(eyeOf() == 2, "wheel down on Eyes: the next eye")
        -- Randomize: eyes and marks locked by default
        local eye, look = eyeOf(), lookOf(B)
        for _ = 1, 8 do
            CharCreateRandomizeButton:Click()
            check(eyeOf() == eye and lookOf(B) == look, "Randomize keeps the eyes and the mark")
        end
        check(CZ.randomized[#CZ.randomized] == 0, "the stock rows all rolled")
        local seen = {}
        C.rows[6].lock:Click()
        check(not C.locks[6], "Eyes unlocked")
        for _ = 1, 30 do
            CharCreateRandomizeButton:Click()
            seen[eyeOf()] = true
            check(lookOf(B) == look, "the mark stays locked")
        end
        check(seen[0] and seen[1] and seen[2] and seen[3] and not seen[4], "unlocked eyes roll among 0-3")
        C.rows[6].lock:Click()
        -- right-click: only that row
        local before = deepCopy(CZ.look)
        local designs = {}
        for _ = 1, 30 do
            rightClick(7)
            designs[math.floor((lookOf(B) + 2) / 3)] = true
            check(CZ.look[1] == before[1] and CZ.look[2] == before[2] and CZ.look[3] == before[3]
                  and CZ.look[4] == before[4] and CZ.look[5] % B == before[5] % B, "right-click Markings: only the design")
        end
        check(designs[0] and designs[1] and designs[4], "the design rolls, none included")
        rightClick(2)
        check(CZ.randomized[#CZ.randomized] == 29 and eyeOf() == math.floor(before[2] / stride),
              "right-click Face: a new face, the eyes kept")
        -- every race, sex and class: the labels follow the arrows
        for r = 1, #RACES do
            for _, sex in ipairs({ 2, 3 }) do
                for class = 1, 2 do
                    SetSelectedRace(r)
                    SetSelectedSex(sex)
                    SetSelectedClass(class)
                    C.Refresh()
                    local label = RACES[r].file .. " " .. sex .. " " .. class
                    check(C.state.eyes and C.state.marks, label .. ": eyes and marks live")
                    check(walkAll(label) == 0, label .. ": every row's label follows its arrows")
                end
            end
        end
        -- no room on the right: the column goes left
        MOCK.cpp.screenWidth = 400
        C.LayoutVirtual()
        p, rel, rp = BleakholdCustomizeMarkColour:GetPoint(1)
        check(p == "BOTTOMRIGHT" and rp == "BOTTOMLEFT", "a narrow screen: the column left of the rows")
        MOCK.cpp.screenWidth = 1365.33
        noErrors("marks")
        return
    end

    if SCENARIO == "picker-dk" then
        -- Human male Death Knight: on the normal skins faces 1, 3-10 and 12-14, on the Death Knight skins 26-28 faces
        -- 0, 2 and 11 (the package's shape). The face arrows reach both groups from any skin; the skin arrows only the
        -- skins of the current face's group.
        SetSelectedRace(1)
        SetSelectedSex(2)
        SetSelectedClass(2)
        showScreen()
        check(C.state.dk and C.state.eyes and C.state.marks, "a Death Knight with eyes and marks")
        check(CZ.look[1] == 0 and CZ.look[2] == 1, "skin 0, face 1")
        local _, faces = GetCharCustomizationInfo(2)
        check(faces == 45 and #C.state.faceWalk == 45, "the face walk: 15 faces with eyes 0, 4 and 5 on both kinds of "
              .. "skin, not the 36 of skin 0: " .. tostring(faces))
        check(countText(2) == "2/15", "Face: every base face the arrows reach: " .. tostring(countText(2)))
        check(countText(6) == "1/3", "Eyes: frost blue and the two Death Knight eyes: " .. tostring(countText(6)))
        check(countText(1) == "1/12" and C.state.fresh, "Skin: the 12 normal skins of face 1, groups live: "
              .. tostring(countText(1)))
        check(sameColour(colourOf(1), C.COLORS.plain), "a normal skin's number is plain")
        click(6, 1)
        check(eyeOf() == 4, "the first one is eye 4 (Blood Red)")
        C.rows[6].frame:_fire("OnEnter")
        check(CharacterCreateTooltip._text:find("Blood Red", 1, true), "named Blood Red")
        C.rows[6].frame:_fire("OnLeave")
        -- Face left: face 0 is a Death Knight skin's face, so the jump brings skin 26 and keeps the eye
        click(2, -1)
        check(CZ.look[1] == 26 and CZ.look[2] == stride * 4, "Face left: face 0 with eye 4 on skin 26: "
              .. CZ.look[1] .. " " .. CZ.look[2])
        check(countText(2) == "1/15" and countText(6) == "2/3", "the Face and Eyes rows follow: "
              .. tostring(countText(2)) .. " " .. tostring(countText(6)))
        check(countText(1) == "1/3" and C.state.fresh, "Skin: the three Death Knight skins of face 0: "
              .. tostring(countText(1)))
        check(sameColour(colourOf(1), C.COLORS.deathknight), "a Death Knight skin's number in the class colour")
        C.rows[1].frame:_fire("OnEnter")
        check(CharacterCreateTooltip._text:find("Death Knight", 1, true), "the skin's tooltip names the group")
        C.rows[1].frame:_fire("OnLeave")
        click(1, 1)
        check(CZ.look[1] == 27 and countText(1) == "2/3" and sameColour(colourOf(1), C.COLORS.deathknight),
              "Skin right: skin 27, still a Death Knight skin")
        click(2, 1)
        check(CZ.look[2] == 1 + stride * 4 and CZ.look[1] == 1, "Face right: face 1 with eye 4 brings a normal skin: "
              .. CZ.look[1] .. " " .. CZ.look[2])
        check(countText(1) == "2/12" and sameColour(colourOf(1), C.COLORS.plain), "the normal skins again: "
              .. tostring(countText(1)))
        -- a Death Knight skin set behind the rows' back with one of its faces
        CZ.setValue(1, 26)
        CZ.setValue(2, 2 + stride * 5)
        C.Refresh()
        check(countText(2) == "3/15" and countText(6) == "3/3", "DK skin 26, face 2 with eye 5: "
              .. tostring(countText(2)) .. " " .. tostring(countText(6)))
        click(2, 1)
        check(CZ.look[2] == 3 + stride * 5 and CZ.look[1] == 0, "Face right from face 2: face 3 with eye 5, on the "
              .. "first normal skin of the face loop: " .. CZ.look[1] .. " " .. CZ.look[2])
        check(walkAll("dk") == 0, "every row follows its arrows")

        -- Human female Death Knight from skin 18: her faces 10 and up are hidden rows on it, so the face loop from
        -- there reaches them with eye colours only, and the walk is not the one of the other skins
        SetSelectedRace(1)
        SetSelectedSex(3)
        SetSelectedClass(2)
        C.Refresh()
        check(CZ.look[1] == 0 and CZ.look[2] == 2 and C.state.eyes, "Human female Death Knight on skin 0, face 2")
        check(#C.state.faceWalk == 51 and countText(2) == "3/17", "from skin 0: 51 faces, 17 base faces: "
              .. tostring(countText(2)))
        click(1, -1)
        check(CZ.look[1] == 18 and CZ.prevSkin == 18, "Skin left wraps to skin 18, the face loop's start")
        local _, fromHere = GetCharCustomizationInfo(2)
        check(fromHere == 43 and C.state.eyes and #C.state.faceWalk == 43, "the walk from skin 18: 43 faces: "
              .. tostring(fromHere))
        check(countText(2) == "3/17", "still 17 base faces (faces 10-17 with their eyes): " .. tostring(countText(2)))
        click(2, -1)
        check(CZ.look[1] == 27 and CZ.look[2] == 1 and CZ.prevSkin == 18, "Face left: face 1 brings Death Knight skin 27; "
              .. "the loop still starts at 18: " .. CZ.look[1] .. " " .. CZ.look[2])
        check(C.state.eyes and #C.state.faceWalk == 43, "the walk of skin 18, found by its count: eyes stay")
        check(countText(2) == "2/17" and countText(1) == "2/3", "Face 2/17, Skin 2/3: " .. tostring(countText(2)) .. " "
              .. tostring(countText(1)))
        check(sameColour(colourOf(1), C.COLORS.deathknight), "a Death Knight skin")
        click(2, 1)
        check(CZ.look[1] == 18 and CZ.look[2] == 2, "Face right: face 2, back on skin 18")
        for _ = 1, 6 do click(2, 1) end
        check(CZ.look[2] == 9, "on to face 9 (3, 5-9; 3 by way of a Death Knight skin): " .. CZ.look[2])
        click(2, 1)
        check(CZ.look[2] == 10 + stride * 4 and eyeOf() == 4, "face 10 is in the walk with eyes 4 and 5 only: the "
              .. "first of them: " .. CZ.look[2])
        check(countText(6) == "1/2" and not C.stale["Human:1:deathknight"], "Eyes 1/2, the data still matches: "
              .. tostring(countText(6)))
        check(walkAll("dk from skin 18") == 0, "every row follows its arrows")

        SetSelectedSex(2)
        SetSelectedClass(1)
        C.Refresh()
        check(countText(6) == "1/4", "a Warrior again: four eyes")

        -- C.FaceWalk on its own: the current skin's walk first, else the one walk that fits, else none
        local view = { faceWalks = { { 0, 1, 2 }, { 0, 1, 3 }, { 0, 1, 4 } }, faceWalkOfSkin = { default = 1, [5] = 2 } }
        local function info(pos, raw) return { pos = pos, count = 3, raw = raw } end
        check(C.FaceWalk(view, info(2, 1), 9) == view.faceWalks[1], "the current skin's walk")
        check(C.FaceWalk(view, info(2, 1), 5) == view.faceWalks[2], "skin 5's own walk")
        check(C.FaceWalk(view, info(3, 3), 9) == view.faceWalks[2], "the one walk with face 3 third")
        check(C.FaceWalk(view, info(3, 5), 9) == nil, "no walk has face 5")
        check(C.FaceWalk(view, { pos = 2, count = 4, raw = 1 }, 9) == nil, "no walk has four faces")
        check(C.FaceWalk(view, info(0, 9), 9) == nil, "a face off the walk")
        view.faceWalkOfSkin = 7
        check(C.FaceWalk(view, info(2, 1), 9) == nil, "three walks fit and the skin names none: none is taken")
        noErrors("dk")
        return
    end

    if SCENARIO == "picker-stale" then
        -- the data says Night Elf female has B 18 (the tables 19): no mark rows; a face set off by one value: no eyes
        BleakholdCustomizeData.races.NightElf[1].B = 18
        BleakholdCustomizeData.races.NightElf[1].normal.features = 13 * 18
        SetSelectedRace(2)
        SetSelectedSex(3)
        showScreen()
        check(C.state.eyes and not C.state.marks, "eyes live, no marks with B wrong")
        check(not shown(7) and not shown(8) and shown(6), "only the Eyes row added")
        check(countText(5) == "1/" .. 13 * 19, "Features: the plain n/N of the arrows: " .. tostring(countText(5)))
        check(logHas("no mark rows"), "the mismatch is logged")
        check(walkAll("stale features") == 0, "plain features follow the arrows")
        -- the data and the tables have the same counts but not the same values: the first step finds out
        local set = BleakholdCustomizeData.races.NightElf[1].normal.faceWalks[1]
        set[#set] = 8 + stride * 4 -- 8 + 120 becomes eye 4 of face 8, which a Night Elf who is not a Death Knight lacks
        CZ.setValue(2, 8 + stride * 2)
        C.Refresh()
        click(6, 1)
        check(C.stale["NightElf:1:normal"], "a value the client refuses marks the data stale")
        check(logHas("did not take"), "and logs it")
        check(not shown(6) and countText(2) and countText(2):match("^%d+/36$"), "plain rows from then on: "
              .. tostring(countText(2)))
        check(walkAll("stale") == 0, "the plain rows follow the arrows")
        noErrors("stale")
        return
    end

    if SCENARIO == "picker-paid" then
        PAID_SERVICE_TYPE, PAID_SERVICE_CHARACTER_ID = PAID_CHARACTER_CUSTOMIZATION, 2
        MOCK.paidName = "Christopher Ravencrest"
        local B = D.SPEC.BloodElf[1].B
        CZ.paidCharacter = { race = 3, sex = 3, class = 1, look = { 41, 3 + stride * 2, 4, 5, (3 * (2 - 1) + 3) * B + 2 } }
        showScreen()
        check(GetSelectedRace() == 3 and C.state.eyes and C.state.marks, "the Blood Elf's own look, eyes and marks live")
        check(countText(2) == "4/15" and countText(6) == "3/4", "face 3 with eye 2: " .. tostring(countText(2)))
        check(countText(7) == "3/5" and countText(8) == "3/3", "design 2 in its paint colour")
        check(sameColour(colourOf(1), C.COLORS.fel), "skin 41 is fel")
        -- the name is locked
        local first, last = CharacterCreateNameEdit, BleakholdLastNameEdit
        check(first:GetText() == "Christopher" and last:GetText() == "Ravencrest", "the character's name in the boxes")
        check(first._mouse == false and last._mouse == false and first:GetAlpha() < 1 and last:GetAlpha() < 1,
              "both boxes greyed and closed to the mouse")
        check(select(1, first:GetTextColor()) == 0.5, "grey text")
        check(MOCK.focus() ~= first and MOCK.focus() ~= last, "neither box has the focus")
        first:SetFocus()
        check(MOCK.focus() ~= first, "a locked box gives the focus back")
        MOCK.type(last, "Smith")
        check(last:GetText() == "Ravencrest", "typing is undone")
        check(not CharacterCreateRandomName:IsShown() and BleakholdNameLockedNote:IsShown(), "no Randomize name, a note")
        click(6, 1)
        CharacterCreate_Okay()
        GlueDialog_OnClick(1)
        check(MOCK.created[#MOCK.created] == "Christopher Ravencrest", "the confirmation sends the own name: "
              .. tostring(MOCK.created[#MOCK.created]))
        -- a new character afterwards: open again
        PAID_SERVICE_TYPE = nil
        showScreen()
        check(first._mouse == true and first:GetAlpha() == 1 and select(1, first:GetTextColor()) == 1, "unlocked again")
        check(CharacterCreateRandomName:IsShown() and not BleakholdNameLockedNote:IsShown(), "Randomize name back")
        MOCK.type(first, "Arthas")
        check(first:GetText() == "Arthas", "typing works")
        -- with the lock switched off
        BLEAKHOLD_LOCK_CUSTOMIZE_NAME = false
        PAID_SERVICE_TYPE = PAID_CHARACTER_CUSTOMIZATION
        showScreen()
        check(first._mouse ~= false and first:GetAlpha() == 1, "BLEAKHOLD_LOCK_CUSTOMIZE_NAME false: no lock")
        noErrors("paid")
        return
    end

    if SCENARIO:find("^picker%-selftest") then
        local all = SCENARIO == "picker-selftest-all"
        MOCK.cvars.bleakCustomizeSelfTest = all and "2" or "1"
        if SCENARIO == "picker-selftest-bad" then
            -- a client that miscounts its hair styles
            CZ.lie = { [3] = function(list, v) local i = indexOf(list, v); return i, #list + 1, v end }
        end
        SetSelectedRace(3)
        SetSelectedSex(3)
        showScreen()
        local lines = C.selfTestLog
        local okLines, bad = 0, 0
        for _, l in ipairs(lines) do
            if l:find(" OK (", 1, true) then okLines = okLines + 1 end
            if l:find("MISMATCH", 1, true) then bad = bad + 1 end
        end
        check(#CZ.log > 0 and CZ.log[#CZ.log]:find("self-test: done", 1, true), "the result reaches BleakholdCustomize_Log")
        if SCENARIO == "picker-selftest-bad" then
            check(bad == 1 and lines[#lines]:find("1 row(s) with a mismatch", 1, true), "the miscounted row is reported: "
                  .. table.concat(lines, " | "))
            local found = false
            for _, l in ipairs(lines) do if l:find("hair style MISMATCH", 1, true) then found = true end end
            check(found, "as the hair style row")
        elseif all then
            check(bad == 0 and okLines == #RACES * 2 * 2 * 8, "every race, sex and class: 8 rows OK each: " .. okLines)
            check(GetSelectedRace() == 3 and GetSelectedSex() == 3 and select(3, GetSelectedClass()) == 1,
                  "the screen's race, sex and class back")
        else
            check(bad == 0 and okLines == 8 and lines[#lines]:find("every row OK", 1, true), "8 rows OK: "
                  .. table.concat(lines, " | "))
        end
        local look = deepCopy(CZ.look)
        MOCK.cvars.bleakCustomizeSelfTest = "0"
        showScreen()
        check(#C.selfTestLog == #lines, "off: no new run")
        noErrors("self-test")
        return
    end

    error("unknown picker scenario " .. SCENARIO)
end
