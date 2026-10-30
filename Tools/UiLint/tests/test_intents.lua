-- Security principle: the client only ever sends intents. Every client message must be one of the
-- documented intent ops with integer / enum / short-token fields; no results, scores, rewards, loot or
-- state, and no free text.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

-- Independent schema (docs/BleakholdProtocol.md, "Client to server").
local INT = "^%d+$"
local SCHEMA = {
    HELLO = { INT, "^[%w_%.%-]+$", INT, "^%a%a%a%a$" },
    TCLAIM = { INT }, TREROLL = { INT },
    QJOIN = { "^[DRBA]$", INT, "^%d$", "^[1-7]$", "^[1-5]$" },
    QLEAVE = {}, QREPLY = { INT, "^[01]$" },
    KMODE = { "^[012]$" }, KSTART = {}, KCANCEL = {},
    BCLAIM = { INT }, WEHANDIN = {}, OUTFIT = { INT },
    LBQ = { "^[KREFA]$", INT, INT, INT, INT },
    PING = { INT },
    EMOJI = { "^%d%d?%d?$" },
    RDROP = { "^%-?%d+$", "^%-?%d+$" }, RDEPLOY = {}, RSPEC = { "^[012]$" },
    WARMODE = { "^[01]$" },
}
local TOPICS = { WEEK = 0, ERA = 0, TASKS = 0, KEY = 0, BOARD = 0, QUEUE = 0, MPLUS = 0, RIFT = 0, COLL = 0, SET = 2,
    LIDX = 0, SEASON = 0, FIRSTS = 0, DEF = 1, ROYS = 0, ROYM = 0, WMST = 0, WPZ = 0, WPMAP = 0, WANTED = 0, ARENA = 0 }

local function checkBody(body)
    H.ok(#body <= 251, "body over 251 bytes: " .. #body)
    local ver, op, seq, part, total, rest = body:match("^(%d+) (%u+) (%w+) (%d+)/(%d+)(.*)$")
    H.ok(ver == "1", "bad frame: " .. body)
    H.ok(part == "1" and total == "1", "client messages are never chunked: " .. body)
    local payload = rest:sub(2)
    H.ok(not payload:find("[^%w_%.%-,;]"), "only integers, enums and tokens: " .. body)
    if op == "GET" then
        local n = 0
        for rec in (payload .. ";"):gmatch("([^;]*);") do
            n = n + 1
            local fields = {}
            for f in (rec .. ","):gmatch("([^,]*),") do fields[#fields + 1] = f end
            H.ok(TOPICS[fields[1]], "GET of an unknown topic: " .. body)
            H.ok(#fields - 1 <= TOPICS[fields[1]], "too many GET args: " .. body)
            for i = 2, #fields do H.ok(fields[i]:match(INT), "GET arg not an integer: " .. body) end
        end
        H.ok(n >= 1 and n <= 8, "GET record count: " .. body)
        return op
    end
    local schema = SCHEMA[op]
    H.ok(schema, "not an intent op: " .. op)
    local fields = {}
    if payload ~= "" then
        for f in (payload .. ","):gmatch("([^,]*),") do fields[#fields + 1] = f end
    end
    H.eq(#fields, #schema, "field count of " .. op)
    for i, pat in ipairs(schema) do
        H.ok(fields[i]:match(pat), op .. " field " .. i .. " = " .. tostring(fields[i]))
    end
    return op
end

local function clickAll(M, root)
    local clicked = 0
    for _, b in ipairs(M.Clickables(root)) do
        if b:IsVisible() and b:IsEnabled() and b.__scripts.OnClick then
            b:Click()
            clicked = clicked + 1
            -- accept any confirmation it opened
            local d = M.env.BleakholdDialog
            if d and d:IsShown() and d.ok:IsShown() then
                d.ok:Click()
            end
            M.Advance(0.2)
        end
    end
    return clicked
end

test("Comm.Send refuses anything that is not an intent", function(M, ns)
    local C = ns.Comm
    H.hello(M)
    for _, op in ipairs({ "SCORE", "RESULT", "LOOT", "REWARD", "MPE", "TASK", "TASKS", "KEY", "SETSTATE", "HELLOS", "" }) do
        H.eq(C.Send(op, 1), false, "refused " .. op)
    end
    H.eq(C.Send("TCLAIM", "12; GIVE 999"), false, "free text in an int field")
    H.eq(C.Send("TCLAIM", 1.5), false, "non-integer")
    H.eq(C.Send("TCLAIM", -1), false, "out of range")
    H.eq(C.Send("TCLAIM"), false, "missing field")
    H.eq(C.Send("TCLAIM", 1, 2), false, "extra field")
    H.eq(C.Send("QJOIN", "X", 1, 0, 4, 5), false, "bad enum")
    H.eq(C.Send("QJOIN", "D", 1, 0, 4, 9), false, "group size over 5")
    H.eq(C.Send("HELLO", 1, "1.0 beta", 0, "enUS"), false, "token with a space")
    H.eq(C.Send("GET", { "WEEK", "x" }), false, "GET arg not an integer")
    H.eq(C.Send("GET", { "SECRETS" }), false, "unknown topic")
    H.ok(C.stats.refused >= 14)
end)

-- The requests mod-transmog-plus understands (TransmogAddonProtocol.cpp, Dispatch).
local TRANSMOG_COMMANDS = {
    GetTransmogStatus = true, GetCollectionStatus = true, GetAvailableTransmogs = true, Apply = true, Remove = true,
    RemoveAll = true, CalculateCost = true, RequestPortable = true, GetSources = true, GetMissing = true,
    GetOutfits = true, SaveOutfit = true, DeleteOutfit = true, GetIllusions = true, ApplyIllusion = true,
    GetBackpacks = true, ApplyBackpack = true, GetForms = true, ApplyForm = true,
}

test("SendAddonMessage is only called by Comm (BHc), Countdown (DBM pull timer) and Transmog", function(M, ns)
    for _, file in ipairs(M.loaded) do
        local text = host_readfile(addonDir .. "/" .. file):gsub("%-%-[^\n]*", "")
        local n = 0
        for _ in text:gmatch("SendAddonMessage%(") do n = n + 1 end
        if file == "Comm.lua" then
            H.eq(n, 1, "Comm.lua sends in one place")
            H.contains(text, 'SendAddonMessage(Comm.PREFIX_OUT, body, "WHISPER", ns.PlayerName())')
        elseif file == "Transmog.lua" then
            H.eq(n, 1, "Transmog.lua sends in one place")
            H.contains(text, 'SendAddonMessage(prefix, msg, "WHISPER", me)')
        elseif file == "Countdown.lua" then
            for line in text:gmatch("[^\n]*SendAddonMessage%([^\n]*") do
                H.contains(line, "CD.DBM_PREFIX", "Countdown only sends the DBM prefix")
            end
        else
            H.eq(n, 0, file .. " must not call SendAddonMessage")
        end
    end
end)

test("clicking every button of every window sends only valid intents (live mode)", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    local start = #M.sent
    local roots = {}
    for _, k in ipairs({ "tasks", "dungeons", "keys", "rift", "heroic", "group" }) do
        -- Start keystone is for inside the keystone's dungeon with a group of 5, once the keystone opened the start
        -- (BHMP O)
        M.inInstance, M.instanceType = k == "keys" or nil, k == "keys" and "party" or nil
        M.SetGroup(k == "keys" and "PARTY" or "NONE", k == "keys" and 5 or 1, k == "keys")
        if k == "keys" then
            M.zone = "Halls of Lightning"
            ns.Legacy.Receive("O;602;8;1800;10;8;8;1,3,4;Halls of Lightning")
        end
        ns.UI.Open(k)
        M.Advance(0.3)
        clickAll(M, ns.Activities.pages[k])
    end
    M.inInstance, M.instanceType = nil, nil
    -- queued: the Dungeon Journey's queue panel has Leave queue
    ns.UI.Open("dungeons")
    clickAll(M, ns.Dungeons.queue)
    H.send(M, "QUEUE", FX.examples(M).QUEUE)
    clickAll(M, ns.Dungeons.queue)
    for _, k in ipairs({ "collections", "season", "leaderboards" }) do
        ns.UI.Open(k)
        M.Advance(0.3)
        clickAll(M, ns.UI.windows[({ collections = "BleakholdCollectionsFrame", season = "BleakholdSeasonFrame", leaderboards = "BleakholdLeaderboardsFrame" })[k]].content)
    end
    M.Advance(10)
    local ops, n = {}, 0
    for i = start + 1, #M.sent do
        local s = M.sent[i]
        if s.prefix == "BHc" then
            local op = checkBody(s.msg)
            ops[op] = true
            n = n + 1
            H.eq(s.channel, "WHISPER")
            H.eq(s.target, M.playerName)
        elseif s.prefix == "transmog" then
            H.eq(s.channel, "WHISPER")
            H.eq(s.target, M.playerName)
            H.ok(TRANSMOG_COMMANDS[s.msg:match("^(%a+)") or ""], "a mod-transmog-plus request: " .. s.msg)
            H.ok(#s.msg + #s.prefix + 1 <= 255, "within the addon message limit")
        elseif s.prefix == "BHMOG" then
            H.eq(s.channel, "WHISPER")
            H.eq(s.target, M.playerName)
            H.eq(s.msg, "B?", "mod-bleakhold: only the coin balance is asked for")
        else
            H.eq(s.prefix, "DBMv4-PT", "unexpected addon prefix " .. s.prefix)
        end
    end
    H.ok(n >= 10, "a good number of intents were exercised: " .. n)
    -- (the Dungeon Journey starts board runs with the server's own commands, .act start, and custom runs with QJOIN D;
    -- QREPLY is the Royale page's (its own tests), BCLAIM the server refuses: no page offers it)
    for _, want in ipairs({ "TCLAIM", "TREROLL", "QJOIN", "QLEAVE", "KMODE", "KSTART", "WEHANDIN", "LBQ", "GET" }) do
        H.ok(ops[want], want .. " was sent by some button")
    end
end)

test("clicking every button of the Arena page and the Arena leaderboard sends only valid intents", function(M, ns)
    FX.connect(M, H, { [6] = 65536 })
    local now = M.env.time()
    H.send(M, "ARENA", { { 1, 1, now - 86400, now + 86400 * 30, "", 1, 100000, "Arena Season 1" },
        { "S", 1, "Arena Season 1", 1, now - 86400, now + 86400 * 30 }, { "B", 1, 0 },
        { "B", 3, 1, 1912, 4, 22, 44, 30, 12, 8, 1890, 12, 4, 5, 163, 16, "Ironvow Wardens" },
        { "T", 3, 4, 4, 4, 1912, 1800 }, { "N", 3, 22, 1, 1 }, { "M", 3, 1, 14, "Brenna", now - 60, 2, "I" } })
    local start = #M.sent
    ns.UI.Open("arena")
    M.Advance(0.3)
    H.ok(clickAll(M, ns.Arena.page) >= 10, "the page's buttons")
    H.send(M, "QUEUE", { { 9, 1, "A", 1, 1, 1, 5, "" } })
    clickAll(M, ns.Arena.page)
    ns.UI.Open("leaderboards-arena")
    M.Advance(0.3)
    clickAll(M, ns.UI.windows.BleakholdLeaderboardsFrame.content)
    M.Advance(5)
    local ops = {}
    for i = start + 1, #M.sent do
        local s = M.sent[i]
        if s.prefix == "BHc" then
            ops[checkBody(s.msg)] = true
        end
    end
    for _, want in ipairs({ "QJOIN", "QLEAVE", "LBQ", "GET" }) do
        H.ok(ops[want], want .. " was sent by some button")
    end
    local qjoin = {}
    for _, it in ipairs(H.intents(M, start + 1)) do
        if it.op == "QJOIN" then qjoin[#qjoin + 1] = it.payload end
        if it.op == "LBQ" and it.payload:find("^A,") then
            H.ok(it.payload:match("^A,%d+,[1235],%d+,%d+$"), "LBQ A with a bracket: " .. it.payload)
        end
    end
    for _, p in ipairs(qjoin) do
        H.ok(p == "A,1,1,4,1" or p == "A,1,0,4,1", "QJOIN A only: " .. p)
    end
end)

test("demo mode routes intents locally and sends nothing to the server", function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    local start = #M.sent
    -- Comm.log keeps the last 60 messages only, and the demo's War Mode and Arena pushes fill it: count the intents
    -- with Comm.stats.sent and check the ones still in the log
    local sentStart = ns.Comm.stats.sent
    local t0 = M.env.GetTime()
    for _, k in ipairs({ "tasks", "dungeons", "keys", "rift" }) do
        ns.UI.Open(k)
        M.Advance(0.3)
        clickAll(M, ns.Activities.pages[k])
    end
    ns.UI.Open("season")
    clickAll(M, ns.UI.windows.BleakholdSeasonFrame.content)
    M.Advance(40)
    H.eq(#M.sent, start, "no SendAddonMessage in demo mode")
    for _, e in ipairs(ns.Comm.log) do
        if e.dir == ">" and e.t >= t0 then
            checkBody(e.body)
        end
    end
    local out = ns.Comm.stats.sent - sentStart
    H.ok(out > 5, "intents went to the demo responder: " .. out)
end)

test("intent fields are ids the server gave us, never values we computed", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("tasks")
    M.Advance(0.3)
    local card = ns.Activities.tasksPage.cards[3]
    H.ok(card.claim:IsShown(), "claim shown for the claimable task")
    card.claim:Click()
    local it = H.lastIntent(M, "TCLAIM")
    H.eq(it.payload, "103", "TCLAIM carries only the server's task uid")
    H.eq(ns.S.tasks.byUid[103].state, 1, "claiming does not change local state; the server answers")
    H.eq(ns.S.week.coins, 2140, "coins unchanged until the server says so")
end)

test("War Mode (section 19): the page, the orb and the confirmation send only WARMODE 0 or 1 and GETs", function(M, ns)
    M.env.IsResting = function() return 1 end
    FX.connect(M, H, { [6] = 16384 + 32768 })
    local start = #M.sent
    H.send(M, "WMST", { { 0, 0, "", 20, 0, 10, 0, 0, "", 0, 0, 0, 0, 0, 0, 0, 3720, 0, 60, 0, 0, 0 } })
    ns.UI.Open("warmode")
    M.Advance(0.3)
    clickAll(M, ns.WarMode.page)
    M.Advance(2.2)
    H.send(M, "WMST", { { 1, 0, "", 20, 0, 10, 0, 0, "", 0, 0, 0, 0, 0, 0, 0, 3720, 0, 60, 0, 0, 0 } })
    clickAll(M, ns.WarMode.page)
    M.env.BleakholdOrb_warmode:Click()
    M.Advance(10)
    local ops = {}
    for i = start + 1, #M.sent do
        local s = M.sent[i]
        if s.prefix == "BHc" then
            local op = checkBody(s.msg)
            ops[#ops + 1] = op == "WARMODE" and s.msg:match(" (%d)$") or op
        end
    end
    H.contains(table.concat(ops, " "), "1", "WARMODE 1 from the button")
    H.contains(table.concat(ops, " "), "0", "WARMODE 0 from the button")
    for _, op in ipairs(ops) do
        H.ok(op == "GET" or op == "0" or op == "1", "only WARMODE and GET: " .. op)
    end
end)
