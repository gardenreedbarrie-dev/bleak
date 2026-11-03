-- The appearance rows' self-test (bleakCustomizeSelfTest 2: every race, sex and class) on the shipped
-- BleakholdCustomizeData.lua, with a mock client (customize_stock.lua) whose skin and face rows walk the realm's
-- stage-2 tables as the client's arrows do. The tables come from the repository's numbers of the pinned package
-- (Tools/RaceForge/tests/test_picker_data.py writes them from picker.stage_two with its own transliteration of the
-- client's rules, not from the data file), so a data file that lists other walks than the arrows make fails here.
--   wowlua customize_realdata.lua <this folder> <Interface/Bleakhold/Glue> <tables.lua>
-- tables.lua returns a list of { race, sex, kind ("normal"/"deathknight"), numFaces, numSkins, skins, fits,
-- faceColors } (customize_stock.lua's CZ.tables form). Exit code 0 = every check passed.
local HARNESS, GLUE, TABLES = arg[1], arg[2], arg[3]
local function dofile(path) return assert(host_loadfile(path))() end

dofile(HARNESS .. "/mock.lua")
MOCK.addFile("Fonts\\FRIZQT__.TTF")
MOCK.addFile("Fonts\\MORPHEUS.TTF")
dofile(HARNESS .. "/stock.lua")
dofile(HARNESS .. "/customize_stock.lua")("picker-realdata")

local toc = assert(host_readfile(GLUE .. "/BleakholdGlue.toc"))

for line in toc:gmatch("[^\r\n]+") do
    if line:sub(1, 1) ~= "#" and line:find("%S") then
        dofile(GLUE .. "/" .. line:gsub("%s+$", ""))
    end
end

local data = BleakholdCustomizeData
local C, CZ = BleakholdGlue.Customize, MOCK.customize
local failures, checks = 0, 0

local function check(cond, msg)
    checks = checks + 1

    if not cond then
        failures = failures + 1
        print("  FAIL: " .. msg)
    end
end

local function range(n)
    local t = {}

    for i = 0, (n or 0) - 1 do
        t[#t + 1] = i
    end

    return t
end

-- the hair rows do not depend on the skin and face: the data's counts at the first hair colour
local races, tables, seen = {}, {}, {}

for _, t in ipairs(dofile(TABLES)) do
    local view = data.races[t.race][t.sex][t.kind == "deathknight" and "deathKnight" or "normal"]
    t.hairStyles = range(C.CountOf(view.hairStyles, 0))
    t.hairColors = range(C.CountOf(view.hairColors, 0))
    t.features = range(C.CountOf(view.features, 0))
    tables[t.race] = tables[t.race] or {}
    tables[t.race][t.sex] = tables[t.race][t.sex] or {}
    tables[t.race][t.sex][t.kind] = t

    if not seen[t.race] then
        seen[t.race] = true
        races[#races + 1] = { name = t.race, file = t.race, faction = "Alliance" }
    end
end

table.sort(races, function(a, b) return a.file < b.file end)
MOCK.setRaces(races)
CZ.tables = tables
MOCK.cvars.bleakCustomizeSelfTest = "2"
SetGlueScreen("charcreate")

-- 1. the self-test: every row of every race, sex and class follows its arrows, and every one has the Eyes row
local contexts = #races * 2 * #CZ.classes
local ok, eyes = 0, 0

for _, line in ipairs(C.selfTestLog) do
    if line:find(" OK (", 1, true) then
        ok = ok + 1
    end

    if line:find(": eyes OK", 1, true) then
        eyes = eyes + 1
    end

    check(not line:find("MISMATCH", 1, true), line)
end

check(C.selfTestLog[#C.selfTestLog] == "done: every row OK",
      "the self-test ends OK: " .. tostring(C.selfTestLog[#C.selfTestLog]))
check(ok == contexts * 8, string.format("%d rows OK of %d", ok, contexts * 8))
check(eyes == contexts, string.format("the Eyes row in %d of %d races, sexes and classes", eyes, contexts))
check(#BLEAKHOLD_GLUE_ERRORS == 0, "no caught errors: " .. table.concat(BLEAKHOLD_GLUE_ERRORS, " | "))

-- 2. every race, sex and class: skin groups and eyes at the start; a Death Knight whose race has Death Knight skins
-- reaches them with the face arrows (a face of those skins brings one), where the skin is in the class colour, the
-- eyes stay and the skin arrows keep to those skins
local deathKnights = 0

for r = 1, #races do
    for _, sex in ipairs({ SEX_MALE or 2, SEX_FEMALE or 3 }) do
        for class = 1, #CZ.classes do
            SetSelectedRace(r)
            SetSelectedSex(sex)
            SetSelectedClass(class)
            local s = C.Read()
            check(s.fresh and s.eyes, tostring(s.key) .. ": skin groups and eyes at the start")
            local group = type(s.entry) == "table" and s.entry.skinGroup or {}
            local hasDk = false

            for _, code in pairs(group) do
                hasDk = hasDk or code == 4
            end

            if s.dk and hasDk then
                deathKnights = deathKnights + 1
                local hit

                for _ = 1, 2 * s.rows[C.FACE].count do
                    C.Step(C.FACE, 1)
                    local now = C.Read()

                    if group[now.rows[C.SKIN].raw] == 4 then
                        hit = now
                        break
                    end
                end

                check(hit and hit.fresh and hit.eyes, s.key .. ": the face arrows reach a Death Knight skin, with skin "
                    .. "groups and eyes")

                if hit then
                    local _, _, colour = C.Label(hit, C.SKIN)
                    check(colour == "deathknight", s.key .. ": the Death Knight skin in the class colour: "
                        .. tostring(colour))
                    C.Step(C.SKIN, 1)
                    local after = C.Read()
                    check(after.fresh and after.eyes and group[after.rows[C.SKIN].raw] == 4,
                          s.key .. ": a skin step keeps to the Death Knight skins")
                end
            end
        end
    end
end

check(deathKnights > 0, "some race has Death Knight skins")
print(string.format("customize-realdata       %d races, %d contexts, %d rows OK, Death Knight skins in %d races and "
    .. "sexes: %d checks, %d failed", #races, contexts, ok, deathKnights, checks, failures))

if failures > 0 then
    host_exit(1)
end
