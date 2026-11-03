-- Glowing marks (Marks.lua, MarksWindow.lua, docs/BleakholdProtocol.md section 22): DEF N and the texture paths, the
-- paged MARKS list, MARK deltas, MARKME, the natives of Bleakhold.exe (BleakholdMarks_*, a mock here that keeps its own
-- map and logs every call), the option marksOthers, the feature bit, and the Markings window with its preview. Every
-- message goes through the real receive path (Comm -> State / Marks), every intent is read back from what was sent.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local MARKS_BIT = { [6] = 262144 }
local OWN = 1313                    -- the player's GUID counter (UnitGUID 0x0000000000000521)

-- The natives as WoW/Source/Ui/BleakholdMarks.h describes them: a map guid -> { mark, eye }, Set with both none is a
-- Clear, BeginSync marks every entry stale, Set or Clear unmarks one, EndSync removes the stale ones. log keeps every
-- call as "Name guid mark eye".
local function natives(M)
    local N = { map = {}, stale = {}, log = {} }
    local function key(g)
        if type(g) == "string" then
            return tonumber(g:sub(3), 16)
        end
        return g
    end
    local function note(...)
        local parts = {}
        for i = 1, select("#", ...) do parts[i] = tostring((select(i, ...))) end
        N.log[#N.log + 1] = table.concat(parts, " ")
    end
    local E = M.env
    E.BleakholdMarks_Set = function(guid, mark, eye)
        note("Set", guid, mark, eye)
        local g = key(guid)
        if not g or g < 1 or g > 4294967295 then return false, 0 end
        if mark == "" then mark = nil end
        if eye == "" then eye = nil end
        if mark and not mark:find("^Character\\BleakholdMarks\\") then return false, 0 end
        if eye and not eye:find("^Character\\BleakholdEyes\\") then return false, 0 end
        N.stale[g] = nil
        if not mark and not eye then
            N.map[g] = nil
            return true, 0
        end
        N.map[g] = { mark = mark, eye = eye }
        return true, 1
    end
    E.BleakholdMarks_Clear = function(guid)
        note("Clear", guid)
        local g = key(guid)
        local had = N.map[g] ~= nil
        N.map[g], N.stale[g] = nil, nil
        return had, had and 1 or 0
    end
    E.BleakholdMarks_ClearAll = function()
        note("ClearAll")
        local n = 0
        for _ in pairs(N.map) do n = n + 1 end
        N.map, N.stale = {}, {}
        return n
    end
    E.BleakholdMarks_Get = function(guid)
        local e = N.map[key(guid)]
        if e then return e.mark, e.eye end
    end
    E.BleakholdMarks_Count = function()
        local n = 0
        for _ in pairs(N.map) do n = n + 1 end
        return n, 4096
    end
    E.BleakholdMarks_BeginSync = function()
        note("BeginSync")
        local n = 0
        for g in pairs(N.map) do
            N.stale[g] = true
            n = n + 1
        end
        return n
    end
    E.BleakholdMarks_EndSync = function()
        note("EndSync")
        local n = 0
        for g in pairs(N.stale) do
            N.map[g] = nil
            n = n + 1
        end
        N.stale = {}
        return n
    end
    function N.count(name)
        local n = 0
        for _, l in ipairs(N.log) do
            if l:match("^%S+") == name then n = n + 1 end
        end
        return n
    end
    function N.size()
        local n = 0
        for _ in pairs(N.map) do n = n + 1 end
        return n
    end
    return N
end

-- the player: a Night Elf woman (a Death Knight when dk), with copper money
local function player(M, opts)
    opts = opts or {}
    local E = M.env
    E.UnitGUID = function(unit) if unit == "player" then return "0x0000000000000521" end end
    E.UnitRace = function(unit) if unit == "player" then return "Night Elf", "NightElf" end end
    E.UnitSex = function(unit) if unit == "player" then return 3 end end
    E.UnitClass = function(unit)
        if unit == "player" then
            if opts.dk then return "Death Knight", "DEATHKNIGHT" end
            return "Druid", "DRUID"
        end
    end
    M.money = opts.money or 500000
    E.GetMoney = function() return M.money end
end

-- DEF N of the protocol document: the Night Elf woman (id 9), a Blood Elf man (id 20) and a Tauren woman (id 13)
local DESIGNS = { { 1, "MoonwellSigils", "Moonwell Sigils" }, { 2, "CenarionVines", "Cenarion Vines" },
    { 3, "SentinelTalon", "Sentinel Talon" }, { 4, "Starfall", "Starfall" } }
local COLOURS = { { 1, "EluneBlue", "Elune Blue", "5FB4FF", 1 }, { 2, "MoonwellTeal", "Moonwell Teal", "3FE0C5", 1 },
    { 3, "MidnightInk", "Midnight Ink", "2A2350", 0 } }
local EYES = { { 1, "MoonlightSilver", "Moonlight Silver", "CFE3FF", 0 },
    { 2, "DruidAmber", "Druid Amber", "FFB43A", 0 },
    { 3, "DreamEmerald", "Dream Emerald", "4CFF8A", 0 }, { 4, "BloodRed", "Blood Red", "FF1E1E", 1 },
    { 5, "UnholyGreen", "Unholy Green", "7CFF3A", 1 } }

local function defs(M)
    H.send(M, "DEF", { { "N", 9 }, { 9, 4, 1, "NightElf", DESIGNS, COLOURS, EYES },
        { 20, 10, 0, "BloodElf", DESIGNS, COLOURS, { EYES[1], EYES[2] } },
        { 13, 6, 1, "Tauren", DESIGNS, COLOURS, {} } })
end

local function connect(M, opts)
    player(M, opts)
    FX.connect(M, H, MARKS_BIT)
    defs(M)
end

local NE_MARK = "Character\\BleakholdMarks\\NightElf\\Female\\"
local NE_EYE = "Character\\BleakholdEyes\\NightElf\\Female\\"

local function gets(M, topic)
    local n = 0
    for _, it in ipairs(H.intents(M)) do
        if it.op == "GET" then
            for _, rec in ipairs(it.records) do
                if rec[1] == topic then n = n + 1 end
            end
        end
    end
    return n
end

------------------------------------------------------------------------------------------------------
-- DEF N and the paths
------------------------------------------------------------------------------------------------------
test("marks: DEF N parses into designs, colours and eyes, and the paths follow section 1", function(M, ns)
    connect(M)
    local d = ns.Def("N", 9)
    H.ok(d, "the Night Elf woman")
    H.eq(d.raceId, 4)
    H.eq(d.sex, 1)
    H.eq(d.raceFile, "NightElf")
    H.eq(d.designs[4].key, "Starfall")
    H.eq(d.designs[2].name, "Cenarion Vines")
    H.eq(d.colours[1].hex, "5FB4FF")
    H.eq(d.colours[1].glow, true)
    H.eq(d.colours[3].glow, false, "the paint does not glow")
    H.eq(d.eyes[2].key, "DruidAmber")
    H.eq(d.eyes[2].dkOnly, false)
    H.eq(d.eyes[5].dkOnly, true)
    H.eq(ns.Def("N", 13).eyes[1], nil, "a model without eye sprites")
    H.eq(ns.DEF_SCHEMA, 4)
    local Mk = ns.Marks
    H.eq(Mk.Path(4, 1, 4, 1), NE_MARK .. "Starfall_EluneBlue.blp")
    H.eq(Mk.EyePath(4, 1, 2), NE_EYE .. "Eye_DruidAmber.blp")
    H.eq(Mk.Path(10, 0, 3, 3), "Character\\BleakholdMarks\\BloodElf\\Male\\SentinelTalon_MidnightInk.blp")
    H.eq(Mk.EyePath(10, 0, 4), nil, "an eye the race-sex has no sprite for")
    H.eq(Mk.Path(4, 1, 5, 1), nil, "a design out of range")
    H.eq(Mk.Path(7, 0, 1, 1), nil, "a race-sex without DEF N")
    H.eq(Mk.Path(4, 1, 0, 0), nil, "no design")
    H.eq(Mk.PlayerGuid(), OWN)
    local race, sex, def = Mk.PlayerBody()
    H.eq(race, 4)
    H.eq(sex, 1)
    H.eq(def, d)
end)

test("marks: a malformed DEF N is dropped whole; the longest path stays under the exe's 120 bytes", function(M, ns)
    connect(M)
    H.send(M, "DEF", { { "N", 9 },
        { 22, 11, 0, "Draenei", { DESIGNS[1], DESIGNS[2], DESIGNS[3] }, COLOURS, EYES },        -- three designs
        { 23, 11, 1, "Dra enei", DESIGNS, COLOURS, EYES },                                      -- a bad race file
        { 30, 11, 1, "Draenei", DESIGNS, COLOURS, EYES },                               -- id is not 2 * race + sex
        { 2, 1, 0, "Human", { { 1, "Bad Key", "x" }, DESIGNS[2], DESIGNS[3], DESIGNS[4] }, COLOURS, EYES },
        { 38, 19, 0, "Eredar", DESIGNS, COLOURS, { { 1, "Good", "Good" }, { 2, "Bad.Key", "Bad" } } } })
    H.eq(ns.Def("N", 22), nil)
    H.eq(ns.Def("N", 23), nil)
    H.eq(ns.Def("N", 30), nil)
    H.eq(ns.Def("N", 2), nil, "a key that cannot go into a path")
    local e = ns.Def("N", 38)
    H.ok(e and e.eyes[1] and not e.eyes[2], "an eye with a bad key is left out")
    local long = string.rep("A", 32)
    H.send(M, "DEF", { { "N", 9 }, { 38, 19, 0, "Eredar", { { 1, long, "x" }, DESIGNS[2], DESIGNS[3], DESIGNS[4] },
        { { 1, long, "y", "FFFFFF", 1 }, COLOURS[2], COLOURS[3] }, {} } })
    local p = ns.Marks.Path(19, 0, 1, 1)
    H.ok(p and #p + 5 <= 127 and #p <= 120, "within the exe's path limit: " .. #p)
    -- a key or race file past its length is malformed, never cut to fit (the cut path would name no file)
    H.send(M, "DEF", { { "N", 9 }, { 2, 1, 0, "Human", { { 1, long .. "B", "x" }, DESIGNS[2], DESIGNS[3], DESIGNS[4] },
        COLOURS, EYES }, { 4, 2, 0, string.rep("O", 17), DESIGNS, COLOURS, EYES } })
    H.eq(ns.Def("N", 2), nil, "a 33-byte key")
    H.eq(ns.Def("N", 4), nil, "a 17-byte race file")
end)

------------------------------------------------------------------------------------------------------
-- The list
------------------------------------------------------------------------------------------------------
local function entry(guid, race, sex, d, c, e) return { guid, race, sex, d, c, e } end

test("marks: a three-page list assembled out of order replaces the map through BeginSync / Set / EndSync",
    function(M, ns)
    local N = natives(M)
    connect(M)
    N.map[999] = { mark = NE_MARK .. "Starfall_EluneBlue.blp" }    -- left over from an earlier list
    local p1, p2, p3 = { { 7, 1, 3, 4 } }, { { 7, 2, 3, 4 } }, { { 7, 3, 3, 4 } }
    p1[2] = entry(1201, 4, 1, 4, 1, 2)
    p2[2] = entry(1377, 10, 0, 3, 3, 0)
    p2[3] = entry(OWN, 4, 1, 1, 2, 0)
    p3[2] = entry(1502, 6, 1, 0, 0, 2)                              -- an eye only (the Tauren has no sprites)
    H.send(M, "MARKS", p3)
    H.send(M, "MARKS", p1)
    H.eq(next(ns.S.marks), nil, "nothing applied before every page is in")
    H.ok(ns.S.marksBuffer and ns.S.marksBuffer.listId == 7, "being collected")
    H.eq(N.count("BeginSync"), 0)
    H.send(M, "MARKS", p2)
    H.eq(ns.S.marksBuffer, nil, "complete")
    H.eq(ns.S.marks[1201].design, 4)
    H.eq(ns.S.marks[1201].eye, 2)
    H.eq(ns.S.marks[1377].race, 10)
    H.eq(ns.S.marks[1502].eye, 2)
    H.eq(N.count("BeginSync"), 1)
    H.eq(N.count("EndSync"), 1)
    H.eq(N.log[1], "BeginSync")
    H.eq(N.log[#N.log], "EndSync")
    H.eq(N.map[1201].mark, NE_MARK .. "Starfall_EluneBlue.blp")
    H.eq(N.map[1201].eye, NE_EYE .. "Eye_DruidAmber.blp")
    H.eq(N.map[1377].mark, "Character\\BleakholdMarks\\BloodElf\\Male\\SentinelTalon_MidnightInk.blp")
    H.eq(N.map[1377].eye, nil)
    H.eq(N.map[OWN].mark, NE_MARK .. "MoonwellSigils_MoonwellTeal.blp")
    H.eq(N.map[1502], nil, "an eye the catalogue has no sprite for: kept in S.marks only")
    H.eq(N.map[999], nil, "the entry the new list does not have is gone")
    H.eq(N.size(), 3)
end)

test("marks: a page of another listId restarts the list; duplicates, bad records and records past 400 are skipped",
    function(M, ns)
    local N = natives(M)
    connect(M)
    H.send(M, "MARKS", { { 4, 1, 2, 2 }, entry(1201, 4, 1, 4, 1, 2) })
    H.send(M, "MARKS", { { 5, 1, 1, 1 }, entry(1377, 10, 0, 3, 3, 0) })
    H.eq(ns.S.marks[1201], nil, "the old list was dropped")
    H.eq(ns.S.marks[1377].design, 3)
    H.send(M, "MARKS", { { 4, 2, 2, 2 }, entry(1201, 4, 1, 4, 1, 2) })
    H.eq(ns.S.marks[1201], nil, "a late page of the old list starts a buffer of its own, never completed")
    -- bad records: out of range, design without colour, garbage; then 401 records on one page
    local page = { { 9, 1, 1, 2000 }, entry(1, 4, 1, 5, 1, 0), entry(2, 4, 1, 1, 0, 0), entry(3, 4, 1, 0, 1, 0),
        entry(4, 4, 2, 1, 1, 0), entry(0, 4, 1, 1, 1, 0), entry(5, 4, 1, 1, 1, 6), { "x", 4, 1, 1, 1, 0 },
        entry(6, 4, 1, 0, 0, 0) }
    while #page < 401 do
        page[#page + 1] = entry(1000 + #page, 4, 1, 1, 1, 0)
    end
    page[#page + 1] = entry(50000, 4, 1, 1, 1, 0)                  -- record 401
    H.send(M, "MARKS", page)
    local n = 0
    for g in pairs(ns.S.marks) do
        n = n + 1
        H.ok(g >= 1009, "only the valid records: " .. g)
    end
    H.eq(n, 392, "400 records read, 8 of them bad")
    H.eq(ns.S.marks[50000], nil, "the 401st record of a page is skipped")
    H.send(M, "MARKS", { { 10, 1, 1, 0 } })
    H.eq(next(ns.S.marks), nil, "an empty list (header only) empties the map")
    H.eq(N.size(), 0)
end)

test("marks: MARK deltas wait for a list being collected and apply in order right after it", function(M, ns)
    local N = natives(M)
    connect(M)
    H.send(M, "MARKS", { { 2, 1, 2, 3 }, entry(1201, 4, 1, 1, 1, 0) })
    H.send(M, "MARK", { entry(1201, 4, 1, 4, 1, 2), entry(1377, 10, 0, 0, 0, 0) })
    H.send(M, "MARK", { entry(1201, 4, 1, 2, 3, 0) })
    H.eq(next(ns.S.marks), nil, "kept, not applied")
    H.send(M, "MARKS", { { 2, 2, 2, 3 }, entry(1377, 10, 0, 3, 3, 0), entry(1502, 6, 1, 0, 0, 2) })
    H.eq(ns.S.marks[1201].design, 2, "the deltas in order after the list")
    H.eq(ns.S.marks[1201].colour, 3)
    H.eq(ns.S.marks[1377], nil, "the removal delta took the list's entry away")
    H.eq(N.map[1201].mark, NE_MARK .. "CenarionVines_MidnightInk.blp")
    H.eq(N.map[1377], nil)
    H.eq(N.count("BeginSync"), 1, "one sync for the list and its deltas")
    -- a delta outside a list: Set, and a removal: Clear
    H.send(M, "MARK", { entry(1377, 10, 0, 1, 2, 1) })
    H.eq(N.map[1377].eye, "Character\\BleakholdEyes\\BloodElf\\Male\\Eye_MoonlightSilver.blp")
    H.send(M, "MARK", { entry(1201, 4, 1, 0, 0, 0) })
    H.eq(ns.S.marks[1201], nil)
    H.eq(N.map[1201], nil)
    H.eq(N.log[#N.log], "Clear 1201")
    -- at most 50 records of one MARK
    local big = {}
    for i = 1, 60 do big[i] = entry(3000 + i, 4, 1, 1, 1, 0) end
    H.send(M, "MARK", big)
    H.ok(ns.S.marks[3050] and not ns.S.marks[3051], "50 records")
end)

test("marks: a list incomplete 10 s after its first page is dropped with its deltas and asked for again, once per 30 s",
    function(M, ns)
    natives(M)
    connect(M)
    M.Advance(1)
    H.eq(gets(M, "MARKS"), 0, "the server sends the list after HELLO; the client does not ask")
    H.send(M, "MARKS", { { 3, 1, 2, 1 }, entry(1201, 4, 1, 1, 1, 0) })
    H.send(M, "MARK", { entry(1377, 10, 0, 3, 3, 0) })
    M.Advance(9)
    H.ok(ns.S.marksBuffer, "still waiting at 9 s")
    M.Advance(1.5)
    H.eq(ns.S.marksBuffer, nil, "dropped")
    H.eq(ns.S.marks[1377], nil, "its kept delta went with it")
    H.eq(gets(M, "MARKS"), 1, "GET MARKS")
    H.send(M, "MARKS", { { 4, 1, 2, 1 }, entry(1201, 4, 1, 1, 1, 0) })
    M.Advance(10.5)
    H.eq(gets(M, "MARKS"), 1, "not again within 30 s")
    M.Advance(20)
    H.send(M, "MARKS", { { 5, 1, 2, 1 }, entry(1201, 4, 1, 1, 1, 0) })
    M.Advance(10.5)
    H.eq(gets(M, "MARKS"), 2, "again after 30 s")
end)

test("marks: a DEF arriving after the list builds the paths it lacked", function(M, ns)
    local N = natives(M)
    player(M)
    FX.connect(M, H, MARKS_BIT)
    H.send(M, "MARKS", { { 1, 1, 1, 2 }, entry(1201, 4, 1, 4, 1, 2), entry(OWN, 4, 1, 1, 1, 0) })
    H.eq(N.size(), 0, "no DEF N yet: nothing to paste")
    H.ok(ns.S.marks[1201], "but kept")
    defs(M)
    M.Advance(0.1)
    H.eq(N.map[1201].mark, NE_MARK .. "Starfall_EluneBlue.blp")
    H.eq(N.map[OWN].mark, NE_MARK .. "MoonwellSigils_EluneBlue.blp")
end)

test("marks: with marksOthers off only the player's own entry is applied; switching re-syncs", function(M, ns)
    local N = natives(M)
    connect(M)
    M.env.SlashCmdList.BLEAKHOLD("marks others off")
    H.eq(ns.db.options.marksOthers, false)
    H.send(M, "MARKS", { { 1, 1, 1, 2 }, entry(1201, 4, 1, 4, 1, 2), entry(OWN, 4, 1, 1, 1, 0) })
    H.eq(N.map[1201], nil, "others hidden")
    H.ok(N.map[OWN], "the player's own")
    H.send(M, "MARK", { entry(1377, 10, 0, 3, 3, 0) })
    H.eq(N.map[1377], nil, "a delta of another player is not applied either")
    H.ok(ns.S.marks[1377], "but kept")
    M.env.SlashCmdList.BLEAKHOLD("marks others on")
    H.ok(N.map[1201] and N.map[1377] and N.map[OWN], "on again: everyone")
    M.env.SlashCmdList.BLEAKHOLD("marks others off")
    H.eq(N.size(), 1, "off again: the sync keeps only the player")
    M.env.SlashCmdList.BLEAKHOLD("marks status")
    H.contains(M.chat[#M.chat].msg, "3 players listed")
    H.contains(M.chat[#M.chat].msg, "client 1 of 4096")
    -- the window's check box is the same option
    H.send(M, "MARKME", { { 1, 1, 0, 100000, 0, 1, 1 } })
    ns.UI.Open("markings")
    local box = ns.MarksWindow.others
    H.ok(not box:GetChecked(), "off, as the option")
    box:SetChecked(true)           -- the client flips the check before OnClick
    box:Click()
    H.eq(ns.db.options.marksOthers, true)
    H.eq(N.size(), 3, "everyone again")
end)

test("marks: a HELLO without the bit clears everything; without the bit the lists apply nothing", function(M, ns)
    local N = natives(M)
    connect(M)
    H.send(M, "MARKS", { { 1, 1, 1, 1 }, entry(1201, 4, 1, 4, 1, 2) })
    H.send(M, "MARKME", { { 4, 1, 2, 100000, 0, 1, 1 } })
    H.eq(N.size(), 1)
    FX.connect(M, H)
    H.eq(N.log[#N.log], "ClearAll")
    H.eq(N.size(), 0)
    H.eq(next(ns.S.marks), nil, "S.marks emptied")
    H.eq(ns.S.markMe, nil)
    H.ok(not ns.Marks.Available())
    local calls = #N.log
    H.send(M, "MARK", { entry(1377, 10, 0, 3, 3, 0) })
    H.eq(#N.log, calls, "no native call while the bit is off")
    ns.UI.Open("markings")
    H.ok(not M.env.BleakholdMarkingsFrame:IsShown(), "the window does not open")
end)

test("marks: without the natives (a stock client) nothing is called and nothing breaks", function(M, ns)
    connect(M)
    H.ok(not ns.Marks.HasNatives())
    H.send(M, "MARKS", { { 1, 1, 1, 2 }, entry(1201, 4, 1, 4, 1, 2), entry(OWN, 4, 1, 1, 1, 0) })
    H.send(M, "MARK", { entry(1201, 4, 1, 0, 0, 0) })
    H.eq(ns.S.marks[OWN].design, 1, "the lists are kept")
    H.send(M, "MARKME", { { 1, 1, 0, 0, 0, 0, 1 } })
    ns.UI.Open("markings")
    local W = ns.MarksWindow
    W.designRows[3]:Click()
    H.contains(W.note:GetText(), "needs the current Bleakhold client")
    H.ok(W.accept:IsEnabled(), "Accept still works")
    W.accept:Click()
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "MARKSET").payload, "3,1,0,0", "the first change is free")
    M.env.SlashCmdList.BLEAKHOLD("marks status")
    H.contains(M.chat[#M.chat].msg, "needs the current Bleakhold client")
end)

------------------------------------------------------------------------------------------------------
-- MARKME and the window
------------------------------------------------------------------------------------------------------
local function openWindow(M, ns, me)
    H.send(M, "MARKME", { me or { 0, 0, 0, 100000, 0, 1, 1 } })
    ns.UI.Open("markings")
    M.Advance(0.1)
    return ns.MarksWindow
end

test("marks: MARKME parses the player's state; the cooldown counts down", function(M, ns)
    connect(M)
    H.send(M, "MARKME", { { 4, 1, 2, 100000, 3600, 1, 1 } })
    local m = ns.S.markMe
    H.eq(m.design, 4)
    H.eq(m.colour, 1)
    H.eq(m.eye, 2)
    H.eq(m.price, 100000)
    H.eq(m.cooldownSec, 3600)
    H.eq(m.changes, 1)
    H.eq(m.offered, 1)
    M.Advance(600)
    H.ok(math.abs(ns.Marks.CooldownLeft() - 3000) < 1, "counted down")
    H.send(M, "MARKME", { { 2, 0, 9, -5, "x", "", "" } })
    H.eq(ns.S.markMe.design, 0, "a design without colour reads as none")
    H.eq(ns.S.markMe.eye, 0)
    H.eq(ns.S.markMe.price, 0)
    H.eq(ns.S.markMe.offered, 0)
end)

test("marks window: the race-sex's designs, colours and eyes; picks preview on the player; Cancel and close revert",
    function(M, ns)
    local N = natives(M)
    connect(M)
    H.send(M, "MARKS", { { 1, 1, 1, 2 }, entry(1201, 4, 1, 4, 1, 2), entry(OWN, 4, 1, 1, 1, 0) })
    local before = #M.sent
    local W = openWindow(M, ns, { 1, 1, 0, 100000, 0, 1, 1 })
    H.ok(M.env.BleakholdMarkingsFrame:IsShown())
    H.ok(#M.sent > before and gets(M, "MARKME") == 1, "GET MARKME when shown")
    H.eq(W.model.__unit, "player")
    H.eq(W.designRows[4].label:GetText(), "Starfall")
    H.eq(W.colourRows[2].label:GetText(), "Moonwell Teal")
    H.eq(W.colourRows[3].tag:GetText(), "paint")
    H.eq(W.colourRows[1].tag:GetText(), "glows")
    H.eq(W.designRows[1].style, "rowOn", "the applied choice")
    H.ok(W.eyeRows[3]:IsShown() and not W.eyeRows[4]:IsShown() and not W.eyeRows[5]:IsShown(),
        "Blood Red and Unholy Green are for Death Knights")
    H.ok(not W.accept:IsEnabled(), "nothing picked yet: the same as now")
    local calls = #N.log
    W.designRows[4]:Click()
    H.eq(N.log[calls + 1], "Set " .. OWN .. " " .. NE_MARK .. "Starfall_EluneBlue.blp nil", "the preview on the player")
    W.colourRows[2]:Click()
    W.eyeRows[3]:Click()
    H.eq(N.map[OWN].mark, NE_MARK .. "Starfall_MoonwellTeal.blp")
    H.eq(N.map[OWN].eye, NE_EYE .. "Eye_DreamEmerald.blp")
    H.eq(N.map[1201].mark, NE_MARK .. "Starfall_EluneBlue.blp", "nobody else is previewed")
    for i = calls + 1, #N.log do
        local l = N.log[i]
        H.ok(l:find(" " .. OWN .. " ", 1, true) or l:find(" " .. OWN .. "$"), "only the player: " .. l)
    end
    H.ok(W.accept:IsEnabled())
    W.cancel:Click()
    H.ok(not M.env.BleakholdMarkingsFrame:IsShown())
    H.eq(N.map[OWN].mark, NE_MARK .. "MoonwellSigils_EluneBlue.blp", "Cancel puts the applied entry back")
    H.eq(N.map[OWN].eye, nil)
    H.eq(ns.Marks.preview, nil)
    -- the close button, and a player without an entry: Clear
    H.send(M, "MARK", { entry(OWN, 4, 1, 0, 0, 0) })
    W = openWindow(M, ns, { 0, 0, 0, 100000, 0, 1, 1 })
    W.eyeRows[1]:Click()
    H.eq(N.map[OWN].eye, NE_EYE .. "Eye_MoonlightSilver.blp")
    M.env.BleakholdMarkingsFrame.close:Click()
    H.eq(N.map[OWN], nil, "closing clears the preview of a player without marks")
    H.eq(N.log[#N.log], "Clear " .. OWN)
end)

test("marks window: Accept sends MARKSET design, colour, eye and the price shown; the own MARK ends the preview",
    function(M, ns)
    local N = natives(M)
    connect(M)
    local W = openWindow(M, ns, { 0, 0, 0, 100000, 0, 1, 1 })
    H.ok(W.free:IsShown() and not W.money:IsShown(), "no marks at all: free")
    W.designRows[4]:Click()
    H.ok(W.money:IsShown() and W.money.copper == 100000, "the price")
    W.eyeRows[2]:Click()
    W.accept:Click()
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "MARKSET").payload, "4,1,2,100000")
    H.ok(not W.accept:IsEnabled(), "waiting for the answer")
    H.contains(W.note:GetText(), "Changing your markings")
    H.send(M, "MARKME", { { 4, 1, 2, 100000, 3600, 2, 1 } })
    H.send(M, "MARK", { entry(OWN, 4, 1, 4, 1, 2) })
    H.eq(ns.Marks.preview, nil, "the server's state")
    H.eq(N.map[OWN].mark, NE_MARK .. "Starfall_EluneBlue.blp")
    H.eq(W.pick.design, 4)
    H.eq(W.cooldown:GetText(), "Next change in 60 min")
    H.ok(not W.accept:IsEnabled(), "the same as now, and the cooldown")
    W.designRows[0]:Click()
    W.eyeRows[0]:Click()
    H.ok(W.free:IsShown() and not W.money:IsShown(), "none at all is free")
    H.ok(not W.accept:IsEnabled(), "the cooldown")
    M.Advance(3601)
    H.eq(W.cooldown:GetText(), "")
    H.ok(W.accept:IsEnabled(), "after the cooldown")
    W.accept:Click()
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "MARKSET").payload, "0,0,0,0", "a change to nothing is free")
end)

test("marks window: Accept is greyed while not offered, without the gold, and for the same choice", function(M, ns)
    natives(M)
    connect(M)
    M.money = 5000
    local W = openWindow(M, ns, { 0, 0, 0, 100000, 0, 1, 1 })
    W.designRows[2]:Click()
    H.ok(not W.accept:IsEnabled(), "not enough gold")
    H.contains(W.note:GetText(), "You need 10g")
    W.designRows[0]:Click()
    H.ok(not W.accept:IsEnabled(), "the same as now")
    H.send(M, "MARKME", { { 0, 0, 0, 0, 0, 0, 1 } })
    W.designRows[2]:Click()
    H.ok(W.free:IsShown(), "the first change is free")
    H.ok(W.accept:IsEnabled(), "free: no gold needed")
    H.send(M, "MARKME", { { 0, 0, 0, 0, 0, 0, 0 } })
    W.designRows[2]:Click()
    H.ok(not W.accept:IsEnabled(), "not offered")
    H.contains(W.note:GetText(), "not made for this body yet")
    H.ok(not W.designRows[2]:IsShown(), "no designs then")
end)

test("marks window: an ERR for MARKSET gives the pick back and says why; a Death Knight sees Blood Red", function(M, ns)
    local N = natives(M)
    connect(M, { dk = true })
    local W = openWindow(M, ns, { 0, 0, 0, 100000, 0, 1, 1 })
    H.ok(W.eyeRows[4]:IsShown() and W.eyeRows[5]:IsShown(), "the Death Knight eyes")
    W.eyeRows[4]:Click()
    H.eq(N.map[OWN].eye, NE_EYE .. "Eye_BloodRed.blp")
    W.accept:Click()
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "MARKSET").payload, "0,0,4,100000")
    H.send(M, "ERR", { { "MARKSET", ns.Comm.lastSeq, "marks_price", "The price changed." } })
    H.send(M, "MARKME", { { 0, 0, 0, 150000, 0, 1, 1 } })
    H.eq(N.map[OWN], nil, "the preview reverted")
    H.eq(W.pick.eye, 0)
    H.contains(W.note:GetText(), "The price changed.")
    W.eyeRows[5]:Click()
    H.eq(W.money.copper, 150000, "the new price")
    H.eq(W.note:GetText():find("price changed", 1, true), nil, "a new pick clears the message")
    -- right after the answer the gate (2.25 s) is still shut: the pick goes out when it opens; no answer within 10 s
    -- gives it back
    W.accept:Click()
    M.Advance(2.5)
    H.eq(H.countIntents(M, "MARKSET"), 2, "sent once the gate opened")
    H.eq(H.lastIntent(M, "MARKSET").payload, "0,0,5,150000")
    M.Advance(10.5)
    H.contains(W.note:GetText(), "did not answer")
    H.eq(W.pick.eye, 0, "the pick given back")
    H.eq(N.map[OWN], nil, "and its preview")
end)

test("marks: /bh marks toggles the window; the launcher lists Markings only with the bit", function(M, ns)
    player(M)
    local spec = ns.Integration.LauncherSpec()
    local e
    for _, x in ipairs(spec.entries) do
        if x.key == "markings" then e = x end
    end
    H.ok(e, "a launcher entry")
    H.eq(e.binding, nil)
    H.ok(not e.shown(), "not before the server says so")
    M.env.SlashCmdList.BLEAKHOLD("marks")
    H.ok(not M.env.BleakholdMarkingsFrame:IsShown())
    FX.connect(M, H, MARKS_BIT)
    H.ok(e.shown())
    M.env.SlashCmdList.BLEAKHOLD("marks")
    H.ok(M.env.BleakholdMarkingsFrame:IsShown(), "/bh marks opens it")
    H.ok(e.isOpen())
    M.env.SlashCmdList.BLEAKHOLD("marks")
    H.ok(not M.env.BleakholdMarkingsFrame:IsShown(), "and closes it")
    e.open()
    H.ok(M.env.BleakholdMarkingsFrame:IsShown(), "the launcher opens it")
    FX.connect(M, H)
    H.ok(not M.env.BleakholdMarkingsFrame:IsShown(), "a HELLO without the bit closes it")
end)

test("marks: the demo answers MARKME, the list and MARKSET (MARK + MARKME), and leaving it clears the client's map",
    function(M, ns)
    local N = natives(M)
    player(M)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    H.ok(ns.Marks.Available(), "the demo HELLO has the bit")
    H.ok(ns.S.markMe and ns.S.markMe.price == 0, "a free first change")
    H.ok(ns.S.marks[1201] and ns.S.marks[1377], "two other players")
    H.ok(N.map[1201], "applied")
    ns.UI.Open("markings")
    M.Advance(0.5)
    local W = ns.MarksWindow
    W.designRows[1]:Click()
    W.accept:Click()
    M.Advance(1)
    H.eq(ns.S.marks[OWN].design, 1, "the demo's MARK")
    H.eq(ns.S.markMe.changes, 1, "and its MARKME")
    H.eq(N.map[OWN].mark, NE_MARK .. "MoonwellSigils_EluneBlue.blp")
    H.eq(H.countIntents(M, "MARKSET"), 0, "nothing sent to the server")
    M.env.SlashCmdList.BLEAKHOLD("demo off")
    H.eq(N.size(), 0, "the demo's marks leave with it")
    H.eq(next(ns.S.marks), nil)
end)
