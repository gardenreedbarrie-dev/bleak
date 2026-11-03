-- Made-up appearance data for the customize tests, in the shape of the contract's picker data
-- (Tools/RaceForge/README.md, "Bleakhold appearance data contract", "Picker data"), and the client tables it describes:
-- the option rows a mock client walks at each stage of the realm's data. Numbers only, invented for the tests (the
-- names are the catalogue's, Tools/RaceForge/customize/catalogue.json); no game data. Pure Lua: the glue scenarios
-- (test_customize_glue.lua) and the addon's barber test (test_barber.lua) both load it.
--   local D = dofile("customize_data.lua")
--   D.glue, D.barber          the BleakholdCustomizeData and BarberData tables (the stage-2 view, as picker-data
--                             makes them from the tables below)
--   D.Tables(stage)           the client's tables: "stage2" (marks and eyes in the tables), "stage1" (package rows,
--                             no marks or eyes yet), "stage0" (today's realm: other counts)
--
-- The tables are shaped like the package's: a Death Knight's faces on the ordinary skins and the faces of the Death
-- Knight skins are different faces, so the face arrows reach both groups (from either kind of skin) and the skin
-- arrows reach only the skins of the current face's group. A face's colour count runs to the highest skin it has a row
-- at, whoever may pick that row, and the face arrows' loop (SetNextFace) starts at the last skin chosen: from some
-- skins it visits a few skins only (Human female, skin 18: its faces 10 and up are hidden rows, so from there the face
-- arrows reach those faces with eye colours only).
local D = {}

local function range(n, from)
    local t = {}
    for i = 0, n - 1 do t[#t + 1] = (from or 0) + i end
    return t
end

local function without(list, drop)
    local skip, out = {}, {}
    for _, v in ipairs(drop or {}) do skip[v] = true end
    for _, v in ipairs(list) do if not skip[v] then out[#out + 1] = v end end
    return out
end

local function concat(a, b)
    local out = {}
    for _, v in ipairs(a) do out[#out + 1] = v end
    for _, v in ipairs(b or {}) do out[#out + 1] = v end
    table.sort(out)
    return out
end

local function setOf(list)
    local out = {}
    for _, v in ipairs(list) do out[v] = true end
    return out
end

-- skins: normal skins (0..n-1 minus hidden ones, which keep their rows), dk: Death Knight-only skins, faces: base
-- faces (0..n-1 minus hidden) on the normal skins, dkFaces: the base faces of the Death Knight skins (a Death Knight has
-- the other faces on the normal skins), hidden: skin -> the base faces from this one up are hidden rows on it,
-- groups: raw skin -> group code (2 marked, 3 fel; DK skins 4).
local NAMES = {
    Human = { designs = { "Tidesage Knots", "Kirin Tor Wards", "Light's Oath", "Highland Woad" },
              colours = { "Arcane Violet", "Holy Gold", "Black Ink" }, eyes = { "Arcane Violet", "Holy Gold", "Tidal Teal" } },
    NightElf = { designs = { "Moonwell Sigils", "Cenarion Vines", "Sentinel Talon", "Starfall" },
                 colours = { "Elune Blue", "Moonwell Teal", "Midnight Ink" },
                 eyes = { "Moonlight Silver", "Druid Amber", "Dream Emerald" } },
    BloodElf = { designs = { "Sunstrider Filigree", "Sunwell Rays", "Fel Brand", "Phoenix War Paint" },
                 colours = { "Sunwell Gold", "Fel Green", "Phoenix Red" },
                 eyes = { "Sunwell Gold", "Phoenix Crimson", "Arcane Violet" } },
    HighElf = { designs = { "Silver Covenant Sigils", "Ley-Line Tracery", "Farstrider Marks", "Runestone Wards" },
                colours = { "Quel'dorei Blue", "Arcane Violet", "Silver Ink" },
                eyes = { "Starlight", "Arcane Violet", "Windrunner Teal" } },
    Tauren = { designs = { "Earthmother Paint", "Totemic Stripes", "Sunwalker Rays", "Thunder Lines" },
               colours = { "Sun Gold", "Spirit Teal", "Ochre" }, eyes = { "Sun Gold", "Moon Silver", "Spirit Teal" } },
}
local SPEC = {
    Human = {
        [0] = { B = 9, skins = without(range(13), { 7 }), dk = { 26, 27, 28 }, faces = range(15), dkFaces = { 0, 2, 11 },
                hairStyles = 17, hairColors = 20, groups = { [5] = 2, [9] = 2, [12] = 3 } },
        [1] = { B = 7, skins = range(19), dk = { 26, 27, 28 }, faces = without(range(18), { 4 }), dkFaces = { 0, 1, 3 },
                hidden = { [18] = 10 }, hairStyles = 24, hairColors = 20, groups = { [18] = 2 } },
    },
    NightElf = {
        [0] = { B = 6, skins = range(34), dk = { 38, 39, 40 }, faces = range(16), dkFaces = { 0, 5, 9 },
                hairStyles = 12, hairColors = 22, groups = { [30] = 3 } },
        [1] = { B = 19, skins = without(range(31), { 25 }), dk = { 35, 36, 37 }, faces = range(9), dkFaces = { 0, 4, 8 },
                hairStyles = 12, hairColors = 22, groups = { [12] = 2, [30] = 3 } },
    },
    BloodElf = {
        [0] = { B = 10, skins = range(51), dk = { 63, 64, 65 }, faces = range(15), dkFaces = { 0, 3, 8 },
                hairStyles = 16, hairColors = 24, groups = { [40] = 3, [41] = 3, [20] = 2 } },
        [1] = { B = 11, skins = range(53), dk = { 63, 64, 65 }, faces = range(15), dkFaces = { 0, 3, 8 },
                hairStyles = 19, hairColors = 24, groups = { [41] = 3, [30] = 2 } },
    },
    Tauren = {
        [0] = { B = 7, skins = range(36), dk = { 42, 43, 44 }, faces = range(5), dkFaces = { 0, 1, 2 },
                hairStyles = 13, hairColors = 3, groups = {} },
        [1] = { B = 5, skins = range(28), dk = { 42, 43, 44 }, faces = range(4), dkFaces = { 0, 1, 2 },
                hairStyles = 12, hairColors = 3, groups = {} },
    },
}
-- High Elf: Blood Elf's numbers (the rows are clones), its own catalogue names.
SPEC.HighElf = SPEC.BloodElf
D.SPEC, D.NAMES = SPEC, NAMES
D.RACES = { "Human", "NightElf", "BloodElf", "HighElf", "Tauren" }

local STRIDE, PER_DESIGN, LOOKS = 40, 3, 13
D.STRIDE, D.LOOKS = STRIDE, LOOKS
local EYES = { normal = { 1, 2, 3 }, deathknight = { 4, 5 } }

-- The base faces with a row on a skin, whoever may pick it.
local function rowsAt(spec, skin)
    return setOf(spec.dk)[skin] and spec.dkFaces or spec.faces
end

-- The base faces a kind may pick on a skin.
local function basesAt(spec, kind, skin)
    local bases
    if setOf(spec.dk)[skin] then
        bases = kind == "deathknight" and spec.dkFaces or {}
    else
        bases = kind == "deathknight" and without(spec.faces, spec.dkFaces) or spec.faces
    end
    local hidden = spec.hidden and spec.hidden[skin]
    if hidden then
        local out = {}
        for _, b in ipairs(bases) do if b < hidden then out[#out + 1] = b end end
        bases = out
    end
    return bases
end

-- The client's tables of a race and sex at a stage, for each kind ("normal", "deathknight"):
--   skins       the skins a player of that kind can pick (skin and underwear rows), ascending
--   fits        [skin][face] = true: the face rows that kind can pick on each of those skins
--   faceColors  [face] = the face variation's colour count (its highest skin with a row of any kind, plus one)
--   numFaces    the face variations (the highest raw face plus one), numSkins the skin colours
--   hairStyles, hairColors, features: the values those rows reach
local function tables(spec, stage)
    local out = {}
    local colours = {}
    local function row(v, skin) colours[v] = math.max(colours[v] or 0, skin + 1) end
    -- the skins with rows: the normal ones up to the highest (hidden ones too) and the Death Knight ones
    local present = range(spec.skins[#spec.skins] + 1)
    for _, s in ipairs(spec.dk) do present[#present + 1] = s end
    local numSkins = present[#present] + 1
    for _, s in ipairs(present) do
        for _, b in ipairs(rowsAt(spec, s)) do row(b, s) end
    end
    for _, kind in ipairs({ "normal", "deathknight" }) do
        local dk = kind == "deathknight"
        local t = { skins = dk and concat(spec.skins, spec.dk) or concat(spec.skins), fits = {}, numSkins = numSkins }
        -- the eye rows are copies of the face rows the kind may pick
        local eyes = stage == "stage2" and EYES[kind] or {}
        for _, s in ipairs(t.skins) do
            t.fits[s] = {}
            for _, b in ipairs(basesAt(spec, kind, s)) do
                t.fits[s][b] = true
                for _, e in ipairs(eyes) do
                    t.fits[s][b + STRIDE * e] = true
                    row(b + STRIDE * e, s)
                end
            end
        end
        t.hairStyles, t.hairColors = range(spec.hairStyles), range(spec.hairColors + (dk and 3 or 0))
        t.features = stage == "stage2" and range(LOOKS * spec.B) or range(spec.B)
        out[kind] = t
    end
    local numFaces = 0
    for v in pairs(colours) do numFaces = math.max(numFaces, v + 1) end
    for _, kind in ipairs({ "normal", "deathknight" }) do
        out[kind].faceColors, out[kind].numFaces = colours, numFaces
    end
    return out
end

-- picker-data's lists of the tables (Tools/RaceForge/rflib/picker.py, Walk).
local function faceFits(t, face, offset)
    local n = t.faceColors[face] or 0
    local i = 0
    while i < n do
        local skin = (i + offset) % n
        if t.fits[skin] and t.fits[skin][face] then return true end
        i = skin + 1
    end
    return false
end

local function sameList(a, b)
    if #a ~= #b then return false end
    for i = 1, #a do if a[i] ~= b[i] then return false end end
    return true
end

-- The distinct non-empty lists in key order and the list of each key, a number or { default = most common, ... }.
local function sets(values, keys)
    local out, of, uses = {}, {}, {}
    for _, key in ipairs(keys) do
        local list = values[key]
        if list and #list > 0 then
            local index
            for i, set in ipairs(out) do if sameList(set, list) then index = i end end
            if not index then out[#out + 1] = list; index = #out end
            of[key] = index
            uses[index] = (uses[index] or 0) + 1
        end
    end
    local default = 1
    for i, n in pairs(uses) do if n > (uses[default] or 0) or (n == uses[default] and i > default) then default = i end end
    if #out == 1 then return out, 1 end
    local count = { default = default }
    for key, index in pairs(of) do if index ~= default then count[key] = index end end
    return out, count
end

local function skinWalk(t, face, keep)
    local out = {}
    for s = 0, t.numSkins - 1 do
        if t.fits[s] and t.fits[s][face] and (keep == nil or keep(s)) then out[#out + 1] = s end
    end
    return out
end

local function faceWalk(t, offset)
    local out = {}
    for f = 0, t.numFaces - 1 do if faceFits(t, f, offset) then out[#out + 1] = f end end
    return out
end

local function view(spec, kind, barber)
    local t = tables(spec, "stage2")[kind]
    local v = { skins = {}, hairStyles = spec.hairStyles, hairColors = #t.hairColors, features = LOOKS * spec.B }
    local bySkin, byFace, skins = {}, {}, {}
    for f = 0, t.numFaces - 1 do byFace[f] = skinWalk(t, f) end
    local faces = range(t.numFaces)
    v.skinSets, v.skinSetOfFace = sets(byFace, faces)
    for _, set in ipairs(v.skinSets) do for _, s in ipairs(set) do skins[s] = true end end
    for s = 0, t.numSkins - 1 do if skins[s] then v.skins[#v.skins + 1] = s end end
    if barber then
        v.skinSetOfFace = nil
    else
        for s = 0, t.numSkins - 1 do bySkin[s] = faceWalk(t, s) end
        v.faceWalks, v.faceWalkOfSkin = sets(bySkin, range(t.numSkins))
    end
    return v
end

local function build(barber)
    local data = { version = 1, package = "9d082f467d2e", eyeStride = STRIDE, looksPerDesign = PER_DESIGN,
                   groups = { "plain", "marked", "fel", "deathknight" }, races = {} }
    for _, race in ipairs(D.RACES) do
        local names = NAMES[race]
        data.races[race] = {}
        for sex = 0, 1 do
            local spec = SPEC[race][sex]
            local groups = {}
            for _, s in ipairs(spec.skins) do groups[s] = spec.groups[s] or 1 end
            for _, s in ipairs(spec.dk) do groups[s] = 4 end
            local eyes = { names.eyes[1], names.eyes[2], names.eyes[3], "Blood Red", "Unholy Green" }
            data.races[race][sex] = { B = spec.B, looks = LOOKS, designs = names.designs, colours = names.colours,
                                      eyes = eyes, skinGroup = groups, normal = view(spec, "normal", barber),
                                      deathKnight = view(spec, "deathknight", barber) }
        end
    end
    return data
end
D.glue = build(false)
D.barber = build(true)

-- The client's tables at a stage, for customize_stock.lua's CZ.tables (or the barber mock): [race][sex][kind].
function D.Tables(stage)
    local out = {}
    for _, race in ipairs(D.RACES) do
        out[race] = {}
        for sex = 0, 1 do
            if stage == "stage0" then
                out[race][sex] = {}
                for _, kind in ipairs({ "normal", "deathknight" }) do
                    local t = { skins = range(10), fits = {}, faceColors = {}, numFaces = 12, numSkins = 10,
                                hairStyles = range(12), hairColors = range(10), features = range(5) }
                    for s = 0, 9 do t.fits[s] = setOf(range(12)) end
                    for f = 0, 11 do t.faceColors[f] = 10 end
                    out[race][sex][kind] = t
                end
            else
                out[race][sex] = tables(SPEC[race][sex], stage)
            end
        end
    end
    return out
end

-- The skins of a mock client's table that fit a face, ascending (what the skin arrows reach).
D.SkinWalk = skinWalk

return D
