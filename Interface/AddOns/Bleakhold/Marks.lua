-- Bleakhold: glowing marks (docs/BleakholdProtocol.md, section 22). A mark and an eye colour are a cosmetic of their
-- own: the server stores every character's choice and sends the choices of every online player; this file turns each
-- choice into two texture paths (DEF N, State.lua) and hands them to Bleakhold.exe by player GUID, which pastes and
-- glows them on that player's body as it would a mark of the character tables (WoW/Source/Ui/BleakholdMarks.h).
--   ns.Marks       the paths, the player's body and GUID, the natives (BleakholdMarks_*), the sync, the preview of the
--                  Markings window (MarksWindow.lua) and its MARKSET gate
--   MARKS          the full list, in pages: collected per listId, then it replaces the whole map (S.marks, and the
--                  exe's through BeginSync / Set / EndSync); MARK deltas that arrive meanwhile wait for it
--   MARK           a delta (design 0, colour 0, eye 0 removes the entry)
--   MARKME         the player's own state (S.markMe): the choice, the price, the cooldown, the changes, offered
--   /bh marks      the window; others on|off (the option marksOthers); status
--   demo mode      Marks.DemoRespond answers MARKSET and GET MARKS / MARKME for /bh demo (Demo.lua)
-- Feature 262144: without it nothing of this shows, and the exe's map is emptied. Without the natives (a stock or an
-- older client) nothing is called: the lists are still kept and the window still changes the choice on the server.
local ADDON, ns = ...
local U, Comm = ns.U, ns.Comm
local S = ns.S

local floor, max, min = math.floor, math.max, math.min

local Marks = {}
ns.Marks = Marks

local INT32 = 2147483647
Marks.MAX_PAGE = 400            -- records in one MARKS page
Marks.MAX_PAGES = 5
Marks.MAX_TOTAL = 2000          -- BleakholdUi.Marks.MaxListEntries at most
Marks.MAX_DELTA = 50            -- records in one MARK
Marks.MAX_KEPT = 500            -- MARK records kept while a list is being collected
Marks.LIST_TIMEOUT = 10         -- seconds from a list's first page until an incomplete list is dropped
Marks.ASK_EVERY = 30            -- GET MARKS after a dropped list at most this often
Marks.GAP = 2.25                -- MARKSET at most this often (the server: one per 2 s)
Marks.PENDING_WAIT = 10         -- seconds a MARKSET waits for its answer before the window gives it back

-- The realm's race ids by ChrRaces clientFileString (section 1), for a body whose DEF N has not arrived yet.
Marks.RACE_IDS = { Human = 1, Orc = 2, Dwarf = 3, NightElf = 4, Scourge = 5, Tauren = 6, Gnome = 7, Troll = 8,
    BloodElf = 10, Draenei = 11, HighElf = 15, Eredar = 19 }
Marks.SEX_DIR = { [0] = "Male", [1] = "Female" }

Marks.stats = { sets = 0, failed = 0, syncs = 0 }

------------------------------------------------------------------------------------------------------
-- Option, feature, natives
------------------------------------------------------------------------------------------------------
function Marks.Available()
    return Comm.HasFeature(Comm.FEATURE.MARKS)
end

-- marksOthers (default on): off shows only the player's own marks
function Marks.Others()
    local v = ns.db.options.marksOthers
    if type(v) ~= "boolean" then
        return true
    end
    return v
end

function Marks.SetOthers(on)
    ns.db.options.marksOthers = on and true or false
    Marks.Sync()
end

-- Bleakhold.exe with the GUID map (BleakholdMarks_*, WoW/Source/Ui/BleakholdMarks.cpp)
function Marks.HasNatives()
    return BleakholdMarks_Set ~= nil and BleakholdMarks_Clear ~= nil and BleakholdMarks_BeginSync ~= nil
        and BleakholdMarks_EndSync ~= nil
end

------------------------------------------------------------------------------------------------------
-- Paths (section 1) from DEF N
------------------------------------------------------------------------------------------------------
function Marks.Def(raceId, sex)
    if type(raceId) ~= "number" or (sex ~= 0 and sex ~= 1) then
        return nil
    end
    return ns.Def("N", raceId * 2 + sex)
end

-- Character\BleakholdMarks\<RaceFile>\<Male|Female>\<DesignKey>_<ColourKey>.blp, or nil
function Marks.Path(raceId, sex, design, colour)
    local d = Marks.Def(raceId, sex)
    local ds, cs = d and d.designs[design], d and d.colours[colour]
    if not (ds and cs) then
        return nil
    end
    return "Character\\BleakholdMarks\\" .. d.raceFile .. "\\" .. Marks.SEX_DIR[sex] .. "\\" .. ds.key .. "_" .. cs.key
        .. ".blp"
end

-- Character\BleakholdEyes\<RaceFile>\<Male|Female>\Eye_<EyeKey>.blp, or nil
function Marks.EyePath(raceId, sex, eye)
    local d = Marks.Def(raceId, sex)
    local e = d and d.eyes[eye]
    if not e then
        return nil
    end
    return "Character\\BleakholdEyes\\" .. d.raceFile .. "\\" .. Marks.SEX_DIR[sex] .. "\\Eye_" .. e.key .. ".blp"
end

-- The two paths of an entry (either may be nil: none chosen, or not in the catalogue this client has).
function Marks.EntryPaths(e)
    if not e then
        return nil, nil
    end
    local mark = (e.design or 0) > 0 and Marks.Path(e.race, e.sex, e.design, e.colour) or nil
    local eye = (e.eye or 0) > 0 and Marks.EyePath(e.race, e.sex, e.eye) or nil
    return mark, eye
end

------------------------------------------------------------------------------------------------------
-- The player
------------------------------------------------------------------------------------------------------
-- The player's GUID counter (3.3.5a player GUIDs are 0x00000000xxxxxxxx), as the lists name players.
function Marks.PlayerGuid()
    local g = UnitGUID and UnitGUID("player")
    if type(g) ~= "string" or #g < 8 then
        return nil
    end
    local n = tonumber(g:sub(-8), 16)
    if n and n > 0 then
        return n
    end
    return nil
end

function Marks.IsDeathKnight()
    local _, token = UnitClass("player")
    return token == "DEATHKNIGHT"
end

-- The player's race id, sex (0, 1) and DEF N (nil when the catalogue has no such race-sex): the DEF whose race file
-- is UnitRace's, else the player's own list entry, else the realm's race ids.
function Marks.PlayerBody()
    local _, file = UnitRace("player")
    local sex = UnitSex and UnitSex("player") == 3 and 1 or 0
    for _, id in ipairs(ns.DefIds("N")) do
        local d = ns.Def("N", id)
        if d and d.sex == sex and file and d.raceFile:lower() == tostring(file):lower() then
            return d.raceId, sex, d
        end
    end
    local own = Marks.PlayerGuid() and S.marks[Marks.PlayerGuid()]
    local raceId = (own and own.race) or (file and Marks.RACE_IDS[file])
    return raceId, sex, raceId and Marks.Def(raceId, sex) or nil
end

------------------------------------------------------------------------------------------------------
-- The exe's map
------------------------------------------------------------------------------------------------------
Marks.preview = nil       -- { design, colour, eye } while the window previews a pick on the player

local function native(fn, ...)
    if not fn then
        return nil
    end
    return fn(...)
end

local function setNative(guid, mark, eye)
    if not mark and not eye then
        native(BleakholdMarks_Clear, guid)
        return true
    end
    local ok = native(BleakholdMarks_Set, guid, mark, eye)
    Marks.stats.sets = Marks.stats.sets + 1
    if not ok then
        Marks.stats.failed = Marks.stats.failed + 1
    end
    return ok
end

-- What the exe should show on guid: the preview on the player, else the applied entry (nil, nil: nothing).
local function wanted(guid, own)
    if guid == own and Marks.preview then
        local p = Marks.preview
        local race, sex = Marks.PlayerBody()
        return Marks.EntryPaths({ race = race, sex = sex, design = p.design, colour = p.colour, eye = p.eye })
    end
    if guid ~= own and not Marks.Others() then
        return nil, nil
    end
    return Marks.EntryPaths(S.marks[guid])
end

-- Apply one GUID (a delta, a preview): Set, or Clear when it shows nothing.
function Marks.ApplyGuid(guid)
    if not (Marks.HasNatives() and Marks.Available()) or not guid then
        return
    end
    local mark, eye = wanted(guid, Marks.PlayerGuid())
    setNative(guid, mark, eye)
end

-- Replace the exe's whole map with S.marks (and the preview): entries whose paths do not build (no DEF yet) are kept
-- in S.marks only, so a DEF arriving later syncs again.
function Marks.Sync()
    if not (Marks.HasNatives() and Marks.Available()) then
        return
    end
    Marks.stats.syncs = Marks.stats.syncs + 1
    local own = Marks.PlayerGuid()
    BleakholdMarks_BeginSync()
    for guid in pairs(S.marks) do
        if guid ~= own then
            local mark, eye = wanted(guid, own)
            if mark or eye then
                setNative(guid, mark, eye)
            end
        end
    end
    if own then
        local mark, eye = wanted(own, own)
        if mark or eye then
            setNative(own, mark, eye)
        end
    end
    BleakholdMarks_EndSync()
end

-- Empty the exe's map (HELLO without the bit, leaving demo mode).
function Marks.ClearNatives()
    if BleakholdMarks_ClearAll then
        BleakholdMarks_ClearAll()
    end
end

------------------------------------------------------------------------------------------------------
-- The preview (the Markings window, the player only)
------------------------------------------------------------------------------------------------------
function Marks.Preview(design, colour, eye)
    Marks.preview = { design = design or 0, colour = colour or 0, eye = eye or 0 }
    Marks.ApplyGuid(Marks.PlayerGuid())
end

-- Back to the player's applied entry (Cancel, closing the window, an ERR, the server's own MARK).
function Marks.EndPreview()
    if not Marks.preview then
        return
    end
    Marks.preview = nil
    Marks.ApplyGuid(Marks.PlayerGuid())
end

------------------------------------------------------------------------------------------------------
-- Receiving
------------------------------------------------------------------------------------------------------
-- A field strictly in [lo, hi] (U.Int clamps; a record out of range is skipped instead).
local function num(raw, lo, hi)
    local v = U.Int(raw, nil)
    if v and v >= lo and v <= hi then
        return v
    end
    return nil
end

-- guid, race, sex, design, colour, eye -> an entry, or nil for a malformed record
function Marks.ParseEntry(f)
    local guid, race, sex = num(f[1], 1, 4294967295), num(f[2], 1, 255), num(f[3], 0, 1)
    local design, colour, eye = num(f[4], 0, 4), num(f[5], 0, 3), num(f[6], 0, 5)
    if not (guid and race and sex and design and colour and eye) or (design == 0) ~= (colour == 0) then
        return nil
    end
    return { guid = guid, race = race, sex = sex, design = design, colour = colour, eye = eye }
end

local function isNone(e)
    return e.design == 0 and e.eye == 0
end

-- One delta entry into S.marks (and the exe's map). The player's own ends a preview: the server's state wins.
local function applyDelta(e)
    if isNone(e) then
        S.marks[e.guid] = nil
    else
        S.marks[e.guid] = { race = e.race, sex = e.sex, design = e.design, colour = e.colour, eye = e.eye }
    end
    local own = Marks.PlayerGuid()
    if e.guid == own and Marks.preview then
        Marks.preview = nil
        ns.Fire("MARKS_OWN")
    end
    Marks.ApplyGuid(e.guid)
end

local lastAsk
local function askAgain()
    if not Marks.Available() then
        return
    end
    local now = GetTime()
    if lastAsk and now - lastAsk < Marks.ASK_EVERY then
        return
    end
    lastAsk = now
    Comm.Refresh("MARKS")
end

local function finishList(buf)
    S.marksBuffer = nil
    local list = {}
    for guid, e in pairs(buf.entries) do
        list[guid] = e
    end
    S.marks = list
    for _, e in ipairs(buf.deltas) do
        if isNone(e) then
            S.marks[e.guid] = nil
        else
            S.marks[e.guid] = { race = e.race, sex = e.sex, design = e.design, colour = e.colour, eye = e.eye }
        end
        if e.guid == Marks.PlayerGuid() and Marks.preview then
            Marks.preview = nil
            ns.Fire("MARKS_OWN")
        end
    end
    Marks.Sync()
    ns.Fire("STATE", "MARKS")
end

Comm.Handle("MARKS", function(r)
    local h = r[1]
    local listId, page = num(h[1], 1, INT32), num(h[2], 1, Marks.MAX_PAGES)
    local pages, total = num(h[3], 1, Marks.MAX_PAGES), num(h[4], 0, Marks.MAX_TOTAL)
    if not (listId and page and pages and total) or page > pages then
        return
    end
    local buf = S.marksBuffer
    if buf and (buf.listId ~= listId or buf.pages ~= pages) then
        buf = nil
    end
    if not buf then
        buf = { listId = listId, pages = pages, got = {}, have = 0, entries = {}, count = 0, deltas = {},
            startedAt = GetTime() }
        S.marksBuffer = buf
        ns.After(Marks.LIST_TIMEOUT, function()
            if S.marksBuffer == buf then
                S.marksBuffer = nil
                askAgain()
            end
        end)
    end
    if buf.got[page] then
        return
    end
    buf.got[page] = true
    buf.have = buf.have + 1
    for i = 2, min(#r, Marks.MAX_PAGE + 1) do
        local e = Marks.ParseEntry(r[i])
        if e and not isNone(e) and (buf.entries[e.guid] or buf.count < Marks.MAX_TOTAL) then
            if not buf.entries[e.guid] then
                buf.count = buf.count + 1
            end
            buf.entries[e.guid] = { race = e.race, sex = e.sex, design = e.design, colour = e.colour, eye = e.eye }
        end
    end
    if buf.have == buf.pages then
        finishList(buf)
    end
end)

Comm.Handle("MARK", function(r)
    local buf = S.marksBuffer
    local applied = false
    for i = 1, min(#r, Marks.MAX_DELTA) do
        local e = Marks.ParseEntry(r[i])
        if e then
            if buf then
                if #buf.deltas < Marks.MAX_KEPT then
                    buf.deltas[#buf.deltas + 1] = e
                end
            else
                applyDelta(e)
                applied = true
            end
        end
    end
    if applied then
        ns.Fire("STATE", "MARKS")
    end
end)

Comm.Handle("MARKME", function(r)
    local f = r[1]
    local design, colour = num(f[1], 0, 4) or 0, num(f[2], 0, 3) or 0
    if (design == 0) ~= (colour == 0) then
        design, colour = 0, 0
    end
    S.markMe = {
        design = design, colour = colour, eye = num(f[3], 0, 5) or 0, price = num(f[4], 0, INT32) or 0,
        cooldownSec = num(f[5], 0, INT32) or 0, changes = num(f[6], 0, INT32) or 0, offered = num(f[7], 0, 1) or 0,
        recvAt = GetTime(),
    }
    ns.Fire("STATE", "MARKME")
end)

-- Seconds until the next change is allowed (0: now), counted down since MARKME arrived.
function Marks.CooldownLeft()
    local m = S.markMe
    if not m then
        return 0
    end
    return max(0, m.cooldownSec - (GetTime() - (m.recvAt or GetTime())))
end

-- A DEF set that arrives after the list (the first login with a new dataVer) builds the paths it lacked.
local syncQueued = false
ns.On("STATE", function(topic)
    if topic ~= "DEF" or syncQueued or not (Marks.HasNatives() and Marks.Available()) then
        return
    end
    if not next(S.marks) and not Marks.preview then
        return
    end
    syncQueued = true
    ns.After(0, function()
        syncQueued = false
        Marks.Sync()
    end)
end)

-- Without the bit (marks off, GmOnly for another player, a reload of the realm's conf): nothing stays on anyone.
ns.On("HELLO", function()
    if Marks.Available() then
        return
    end
    Marks.preview = nil
    S.marks = {}
    S.markMe = nil
    S.marksBuffer = nil
    Marks.ClearNatives()
    ns.Fire("STATE", "MARKS")
end)

-- forget everything (leaving or entering demo mode): the exe's map goes with the state it was built from
function Marks.Reset()
    Marks.preview = nil
    lastAsk = nil
    Marks.ResetGate()
    S.marks, S.markMe, S.marksBuffer = {}, nil, nil
    Marks.ClearNatives()
end

------------------------------------------------------------------------------------------------------
-- Sending (MARKSET), one per Marks.GAP
------------------------------------------------------------------------------------------------------
local nextAt

function Marks.ResetGate()
    nextAt = nil
end

function Marks.GateLeft()
    return nextAt and max(0, nextAt - GetTime()) or 0
end

-- true when sent; false, why ("offline", "wait", "refused")
function Marks.Send(design, colour, eye, maxCopper)
    if Comm.outdated or (not Comm.ready and not Comm.demo) then
        return false, "offline"
    end
    if Marks.GateLeft() > 0 then
        return false, "wait"
    end
    local ok = Comm.Send("MARKSET", design, colour, eye, maxCopper)
    if not ok then
        return false, "refused"
    end
    nextAt = GetTime() + Marks.GAP
    return true
end

ns.On("ERR", function(e)
    if e and e.op == "MARKSET" and e.code == "busy" then
        nextAt = GetTime() + Marks.GAP
    end
end)

------------------------------------------------------------------------------------------------------
-- /bh marks
------------------------------------------------------------------------------------------------------
local function count(t)
    local n = 0
    for _ in pairs(t or {}) do
        n = n + 1
    end
    return n
end

function Marks.Command(args)
    args = strtrim and strtrim(args or "") or (args or "")
    local cmd, rest = args:match("^(%S*)%s*(.-)$")
    cmd, rest = (cmd or ""):lower(), (rest or ""):lower()
    if cmd == "" then
        if not Marks.Available() then
            ns.Print("glowing marks are not on for you on this realm.")
            return
        end
        ns.UI.Open("markings", true)
    elseif cmd == "others" then
        local v
        if rest == "on" or rest == "1" then
            v = true
        elseif rest == "off" or rest == "0" then
            v = false
        else
            v = not Marks.Others()
        end
        Marks.SetOthers(v)
        ns.Print("other players' marks: " .. (v and "shown" or "hidden"))
    elseif cmd == "status" then
        local line = "glowing marks: " .. (Marks.Available() and "on" or "off") .. ", " .. count(S.marks)
            .. " players listed, others " .. (Marks.Others() and "shown" or "hidden")
        if BleakholdMarks_Count then
            local n, cap = BleakholdMarks_Count()
            line = line .. ", client " .. tostring(n or 0) .. " of " .. tostring(cap or 0)
        else
            line = line .. ", client: no glow (needs the current Bleakhold client)"
        end
        ns.Print(line)
    else
        ns.Print("usage: /bh marks [others on|off | status]")
    end
end

ns.AddCommand("marks", "glowing marks: /bh marks [others on|off | status]", Marks.Command)

------------------------------------------------------------------------------------------------------
-- Demo mode (/bh demo): a free first change and two other players with marks; MARKSET answered with MARK + MARKME.
-- The catalogue of the demo is the player's own race-sex and the two others', with the protocol document's names.
------------------------------------------------------------------------------------------------------
local demo
Marks.DEMO_DESIGNS = { { "MoonwellSigils", "Moonwell Sigils" }, { "CenarionVines", "Cenarion Vines" },
    { "SentinelTalon", "Sentinel Talon" }, { "Starfall", "Starfall" } }
Marks.DEMO_COLOURS = { { "EluneBlue", "Elune Blue", "5FB4FF", 1 }, { "MoonwellTeal", "Moonwell Teal", "3FE0C5", 1 },
    { "MidnightInk", "Midnight Ink", "2A2350", 0 } }
Marks.DEMO_EYES = { { "MoonlightSilver", "Moonlight Silver", "CFE3FF", 0 },
    { "DruidAmber", "Druid Amber", "FFB43A", 0 }, { "DreamEmerald", "Dream Emerald", "4CFF8A", 0 },
    { "BloodRed", "Blood Red", "FF1E1E", 1 }, { "UnholyGreen", "Unholy Green", "7CFF3A", 1 } }
Marks.DEMO_OTHERS = { { 1201, 4, 1, 4, 1, 2 }, { 1377, 10, 0, 3, 3, 0 } }

local function demoPush(op, records)
    if ns.Demo and Comm.demo then
        ns.Demo.Push(op, records)
    end
end

local function demoDefs()
    local race, sex = Marks.PlayerBody()
    local files = {}
    for file, id in pairs(Marks.RACE_IDS) do
        files[id] = file
    end
    local bodies = { { race or 1, sex or 0 } }
    for _, o in ipairs(Marks.DEMO_OTHERS) do
        bodies[#bodies + 1] = { o[2], o[3] }
    end
    local recs = { { "N", 1 } }
    for _, b in ipairs(bodies) do
        local designs, colours, eyes = {}, {}, {}
        for i, d in ipairs(Marks.DEMO_DESIGNS) do designs[i] = { i, d[1], d[2] } end
        for i, c in ipairs(Marks.DEMO_COLOURS) do colours[i] = { i, c[1], c[2], c[3], c[4] } end
        for i, e in ipairs(Marks.DEMO_EYES) do eyes[i] = { i, e[1], e[2], e[3], e[4] } end
        recs[#recs + 1] = { b[1] * 2 + b[2], b[1], b[2], files[b[1]] or "Human", designs, colours, eyes }
    end
    demoPush("DEF", recs)
end

local function demoMe()
    local price = demo.changes == 0 and 0 or 100000
    demoPush("MARKME", { { demo.design, demo.colour, demo.eye, price, demo.cooldown, demo.changes, 1 } })
end

local function demoList()
    demo.listId = demo.listId + 1
    local recs = { { demo.listId, 1, 1, 0 } }
    for _, o in ipairs(Marks.DEMO_OTHERS) do
        recs[#recs + 1] = o
    end
    local own = Marks.PlayerGuid()
    local race, sex = Marks.PlayerBody()
    if own and (demo.design > 0 or demo.eye > 0) then
        recs[#recs + 1] = { own, race or 1, sex or 0, demo.design, demo.colour, demo.eye }
    end
    recs[1][4] = #recs - 1
    demoPush("MARKS", recs)
end

function Marks.DemoReset()
    demo = { design = 0, colour = 0, eye = 0, changes = 0, cooldown = 0, listId = 0 }
end

-- true when the op is answered here (GETs are passed on for their other topics)
function Marks.DemoRespond(op, recs)
    if not demo then
        Marks.DemoReset()
    end
    if op == "HELLO" then
        -- the server sends MARKME and the list after a HELLO with the bit
        Marks.DemoReset()
        ns.After(0.1, function()
            if Comm.demo and Marks.Available() then
                demoDefs()
                demoMe()
                demoList()
            end
        end)
        return false
    elseif op == "GET" then
        for _, r in ipairs(recs) do
            if r[1] == "MARKME" then
                demoDefs()
                demoMe()
            elseif r[1] == "MARKS" then
                demoList()
            end
        end
        return false
    elseif op == "MARKSET" then
        local f = recs[1] or {}
        local d, c, e = tonumber(f[1]) or 0, tonumber(f[2]) or 0, tonumber(f[3]) or 0
        if d == demo.design and c == demo.colour and e == demo.eye then
            demoPush("ERR", { { "MARKSET", Comm.lastSeq or "", "marks_same", "That is how you look already." } })
            return true
        end
        demo.design, demo.colour, demo.eye = d, c, e
        demo.changes = demo.changes + 1
        demoMe()
        local own = Marks.PlayerGuid()
        local race, sex = Marks.PlayerBody()
        if own then
            demoPush("MARK", { { own, race or 1, sex or 0, d, c, e } })
        end
        return true
    end
    return false
end
