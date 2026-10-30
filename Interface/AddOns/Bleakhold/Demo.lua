-- Bleakhold: /bh demo. A local stand-in for the server so every window can be checked without one.
-- Fixture snapshots are encoded into real protocol frames (several are split into small chunks on
-- purpose) and fed through Comm.Inject, the same parser and handlers the server's frames use. The
-- client's intents go to Demo.Respond instead of the server while demo mode is on; nothing reaches the
-- server and no real data changes.
local ADDON, ns = ...
local U, UI, Comm, Data = ns.U, ns.UI, ns.Comm, ns.Data

local floor, max, min = math.floor, math.max, math.min

local Demo = {}
ns.Demo = Demo

local seq = 0
local timers = {}
local rev = {}
local fx = {}           -- current fixture state

------------------------------------------------------------------------------------------------------
-- Encoding (a field that is a table is a ':' list; a list item that is a table is a '~' tuple)
------------------------------------------------------------------------------------------------------
local function encodeField(f)
    if type(f) ~= "table" then
        return Comm.Escape(f)
    end
    local items = {}
    for i, item in ipairs(f) do
        if type(item) == "table" then
            local parts = {}
            for k, p in ipairs(item) do
                parts[k] = Comm.Escape(p)
            end
            items[i] = table.concat(parts, "~")
        else
            items[i] = Comm.Escape(item)
        end
    end
    return table.concat(items, ":")
end

function Demo.Payload(records)
    local recs = {}
    for _, r in ipairs(records) do
        local fields = {}
        for i = 1, #r do
            fields[i] = encodeField(r[i])
        end
        recs[#recs + 1] = table.concat(fields, ",")
    end
    return table.concat(recs, ";")
end

-- Push one server message through the real receive path.
function Demo.Push(op, records, maxBody)
    seq = seq + 1
    local frames = Comm.BuildFrames(op, seq, Demo.Payload(records), maxBody)
    if not frames then
        return
    end
    for _, body in ipairs(frames) do
        Comm.Inject(body)
    end
end

local function nextRev(topic)
    rev[topic] = (rev[topic] or 0) + 1
    return rev[topic]
end

local function after(sec, fn)
    local t = ns.After(sec, function()
        if Comm.demo then
            fn()
        end
    end)
    timers[#timers + 1] = t
    return t
end

------------------------------------------------------------------------------------------------------
-- Fixtures (content of the Bleakhold design boards)
------------------------------------------------------------------------------------------------------
local NAMES = { "Aldric", "Brenna", "Corwin", "Dalia", "Eamon", "Fenna", "Garrick", "Hesper", "Ivo", "Jessa", "Korrin", "Lyra", "Maelis", "Norrin", "Odessa" }
local CLASS_IDS = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 11 }

local function group(start, n)
    local list = {}
    for i = 0, n - 1 do
        local k = (start + i - 1) % #NAMES + 1
        list[#list + 1] = { NAMES[k], CLASS_IDS[(start * 3 + i) % #CLASS_IDS + 1] }
    end
    return list
end

local function resetFixtures()
    local now = time()
    fx.now = now
    fx.tasks = {
        { 101, "D", 1, 0, 1, "C", 20, "", 0 },
        { 102, "D", 2, 14, 20, "I", 1, 40752, 0, "", "", "1 Emblem of Heroism" },
        { 103, "D", 3, 5, 5, "C", 20, "", 1 },
        { 201, "W", 4, 1, 3, "C", 150, "", 0 },
        { 202, "W", 5, 1, 2, "T", 0, "", 0, "", "", "Legacy Cache" },
        { 203, "W", 6, 0, 1, "T", 0, "", 0, "Echoes of the Black Temple", "", "Legacy Cache (Tier 6)" },
    }
    fx.freeRerolls = 1
    fx.week = { keysTimed = 4, echoes = 1, rift = 18, coins = 2140, cap = 5500, shards = 1260 }
    fx.key = { dungeon = 602, level = 8, affixes = { 1, 3, 4 }, mode = 2, best = 9, bestDungeon = 599, ready = 1, banked = 2 }
    fx.board = { bountyState = 2 }
    fx.queue = { state = 0 }
    fx.season = { points = 1240, tokens = 3 }
    fx.mightBits = 8 + 16 + 32
    fx.rift = { best = 18 }
end

local function pushHello()
    local now = time()
    Demo.Push("HELLO", { { ns.PROTO, 1, now, 0, 0, 2 + 8 + 16 + 32 + 64 + 4096 + 8192 + 16384 + 32768 + 65536, 1,
        now + 7 * 3600 + 12 * 60, now + 3 * 86400 + 5 * 3600, "Bleakhold", "bleakhold.com" } })
end

local function pushWeek()
    local w = fx.week
    Demo.Push("WEEK", { { nextRev("WEEK"), w.keysTimed, w.echoes, w.rift, w.coins, w.cap, w.shards } })
end

local function pushEra()
    Demo.Push("ERA", { { nextRev("ERA"), 7, 3, { 1, 3, 4 }, 1, 0 } })
end

local function pushTasks()
    local recs = { { nextRev("TASKS"), fx.freeRerolls, 500000, "G" } }
    for _, t in ipairs(fx.tasks) do
        recs[#recs + 1] = t
    end
    Demo.Push("TASKS", recs, 120)   -- small chunks: exercises reassembly
end

local function pushKey()
    local k = fx.key
    Demo.Push("KEY", { { nextRev("KEY"), k.dungeon, k.level, k.affixes, k.mode, k.best, k.bestDungeon, k.ready, k.banked, 900001, 15, 7, 0 } })
end

local function pushBoard()
    local b = fx.board
    local recs = { { nextRev("BOARD"), fx.week.shards, 55, 189, b.bountyState, "50 Shards", 1 } }
    local level = UnitLevel and UnitLevel("player") or 80
    for i, id in ipairs(ns.DefIds("D")) do
        local d = ns.Def("D", id) or {}
        local lvl = d.lvlMin or 0
        local bits = lvl <= 30 and 15 or (lvl <= 60 and 7 or 3)
        -- the Journey score, 0-100 (the bridge's BOARD best and record)
        local best = (i % 3 ~= 0) and (50 + (i * 7) % 45) or ""
        local bestTier = best ~= "" and (i % 4) or ""
        recs[#recs + 1] = { id, d.chapter or 1, d.lvlMin or "", d.lvlMax or "", bits, best, bestTier,
            75 + (i * 11) % 26, NAMES[i % #NAMES + 1], (lvl > level) and 1 or 0 }
    end
    Demo.Push("BOARD", recs, 400)
end

local function pushQueue()
    local q = fx.queue
    local level = UnitLevel and UnitLevel("player") or 80
    local recs = { { nextRev("QUEUE"), q.state, q.kind or "D", q.activity or 0, q.tier or 0, q.size or 5, q.queued or 0, q.state == 1 and 300 or "", q.state == 2 and 4242 or "", q.state == 2 and 40 or "", q.state ~= 0 and max(1, level - 2) or "", q.state ~= 0 and min(80, level + 3) or "" } }
    if q.state == 2 then
        local me = ns.PlayerName() or "You"
        recs[#recs + 1] = { me, 1, q.roles or 4, 1, level }
        for i, m in ipairs(group(3, 4)) do
            recs[#recs + 1] = { m[1], m[2], ({ 1, 2, 4, 4 })[i], i <= 2 and 1 or 0, level + (i % 3) - 1 }
        end
    end
    Demo.Push("QUEUE", recs)
end

local function pushColl()
    Demo.Push("COLL", { { nextRev("COLL"), 412, "", 0, 3771, 3, 48, { 3, 0, 0, 0, 0, 0, 0 }, { 8, 8, 5, 9, 5, 5, 8 } } })
end

local MIGHT = { 16866, 16868, 16865, 16861, 16863, 16864, 16867, 16862 }

local function pushSet(tier, classId)
    tier, classId = tonumber(tier) or 1, tonumber(classId) or 1
    if tier == 1 and classId == 1 then
        Demo.Push("SET", { { 1, 201, 1, "Battlegear of Might", fx.mightBits, fx.mightBits == 255 and 1 or 0, MIGHT, { 229, 329, 289, 429, 543 }, 58, 61, "Ragnaros", "" } })
    else
        local cls = ns.ClassInfo(classId)
        local t = ns.Def("L", tier) or {}
        Demo.Push("SET", { { tier, 200 + tier * 20 + classId, classId, (t.label or ("Tier " .. tier)) .. " " .. (cls and cls.name or "set"), 0, 0, {}, t.sources or {}, t.lvlMin or "", t.lvlMax or "", t.echoBoss or "", "The demo only has the pieces of Battlegear of Might (Tier 1, Warrior)." } })
    end
end

local function pushLidx()
    local recs = { { nextRev("LIDX") } }
    for i, id in ipairs(MIGHT) do
        recs[#recs + 1] = { id, 1, 201, bit.band(fx.mightBits, bit.lshift(1, i - 1)) ~= 0 and 1 or 0 }
    end
    Demo.Push("LIDX", recs)
end

local function pushSeason()
    Demo.Push("SEASON", {
        { nextRev("SEASON"), 1, 620, 1284, fx.season.points, 2, 3, 260, "Breach the Greymane Wall", "Fill the bar together and Season 2 opens: Gilneas, Karazhan Crypts and new keys.", fx.season.tokens },
        { "P", "Materials", 800 }, { "P", "Bosses and Echoes", 550 }, { "P", "Keys in time", 510 },
        { "R", 1, 1, "Earned" }, { "R", 2, 0, "7 / 20" }, { "R", 3, 0, "Best: floor 18" }, { "R", 4, 0, "Rank 142" },
    })
end

local function pushRift()
    local r = fx.rift
    if r.state == 1 then
        Demo.Push("RIFT", { { r.runId, 1, r.floor, r.floor, r.boss, floor((GetTime() - r.startedAt) * 1000), r.best, "", 42, r.deaths or 0, r.size or 1 } })
    else
        Demo.Push("RIFT", { { 0, r.state or 0, "", "", "", "", r.best, "", 42, "", "" } })
    end
end

local function pushFirsts()
    local now = time()
    Demo.Push("FIRSTS", {
        { "echo", "Echo of Ragnaros defeated", "Ironvow (Aldric, Brenna, Corwin, Dalia, Eamon)", now - 2 * 86400 },
        { "key", "First timed +15", "Dalia's group", now - 5 * 86400 },
        { "rift", "Solo Rift floor 25", "Korrin", now - 6 * 86400 },
    })
end

local BOSSES = { "Echo of Ragnaros", "Echo of Onyxia", "Echo of Nefarian", "Echo of C'Thun", "Echo of Kel'Thuzad", "Echo of Illidan" }

local function pushLB(board, seasonId, dungeonId, classId, page)
    page = tonumber(page) or 1
    local recs = { { board, seasonId or 1, dungeonId or 0, classId or 0, page, 3 } }
    local now = time()
    local dungeons = { 602, 599, 575 }
    for i = 1, 10 do
        local rank = (page - 1) * 10 + i
        local value, label, t
        if board == "K" then
            value, t = max(2, 15 - floor((rank - 1) / 2)), 300 - rank * 11
        elseif board == "R" then
            value, t = max(1, 32 - rank), 1500 + rank * 40
        else
            label, t = BOSSES[(rank - 1) % #BOSSES + 1], 140 + rank * 9
        end
        local d = dungeonId and dungeonId > 0 and dungeonId or dungeons[(rank - 1) % 3 + 1]
        recs[#recs + 1] = { rank, board == "K" and d or "", value or "", t, now - rank * 7200, group(rank, (board == "R" and rank % 3 == 0) and 1 or 5), label or "" }
    end
    Demo.Push("LB", recs, 300)
    if board == "K" then
        Demo.Push("LBME", { { "K", 42, 12, 9, 602, 154, 580 } })
    elseif board == "R" then
        Demo.Push("LBME", { { "R", 57, 18, 18, "", 1320, 560 } })
    else
        Demo.Push("LBME", { { "E", 88, 30, "", "", 212, 300, "Echo of Ragnaros" } })
    end
end

local TOPIC_PUSH = {
    WEEK = pushWeek, ERA = pushEra, TASKS = pushTasks, KEY = pushKey, BOARD = pushBoard, QUEUE = pushQueue,
    COLL = pushColl, LIDX = pushLidx, SEASON = pushSeason, RIFT = pushRift, FIRSTS = pushFirsts,
    MPLUS = function() end, DEF = function()
        Demo.Push("DEF", { { "A", 0 }, { 1, "Fortified", "Non-boss enemies have more health and hit harder." }, { 3, "Bolstering", "When a non-boss enemy dies, its allies nearby grow stronger." }, { 4, "Volcanic", "Plumes of flame erupt under players fighting at range." } })
        Demo.Push("DEF", { { "Z", 0 } })
    end,
}

------------------------------------------------------------------------------------------------------
-- Simulations
------------------------------------------------------------------------------------------------------
local function findTask(uid)
    for _, t in ipairs(fx.tasks) do
        if t[1] == uid then
            return t
        end
    end
end

local function taskDelta(t)
    Demo.Push("TASK", { { nextRev("TASKS"), t[1], t[4], t[9] } })
end

local function startKey()
    local k = fx.key
    local runId = 7000 + seq
    local limit = 1800
    local state = { elapsed = 0, deaths = 0, forces = 0, bosses = 0, kills = {} }
    Demo.Push("MPS", { { runId, k.dungeon, k.level, k.affixes, 7, 10000, limit } })
    Demo.Push("MP", { { runId, 0, limit, 0, 0, 0, 100, 0, "", { 1260, 1440 }, 0 } })
    local function heartbeat()
        Demo.Push("MP", { { runId, state.elapsed * 1000, limit, state.deaths, state.deaths * 5, state.forces, 100, state.bosses, state.kills, { 1260, 1440 }, 1 } })
    end
    after(10, function()
        heartbeat()
        for step = 1, 12 do
            after(step * 2, function()
                state.elapsed = state.elapsed + 120
                state.forces = min(100, state.forces + 9)
                if step == 3 or step == 6 or step == 9 or step == 12 then
                    local i = step / 3
                    state.bosses = state.bosses + bit.lshift(1, i - 1)
                    state.kills[i] = state.elapsed
                end
                if step == 4 then
                    state.deaths = 2
                end
                if step == 12 then
                    state.elapsed = 24 * 60 + 13
                    state.forces = 100
                end
                heartbeat()
                if step == 12 then
                    after(1, function()
                        Demo.Push("MP", { { runId, state.elapsed * 1000, limit, state.deaths, state.deaths * 5, 100, 100, state.bosses, state.kills, { 1260, 1440 }, 2 } })
                        Demo.Push("MPE", { { runId, 1, state.elapsed * 1000, 1, 599, 9, 1840 }, { "T", 1, "", "Spoils chest (in your bags)" }, { "C", 150 } })
                        k.dungeon, k.level = 599, 9
                        fx.week.keysTimed = fx.week.keysTimed + 1
                        pushKey()
                        pushWeek()
                        Demo.Chat("[Record] Halls of Lightning +8 timed in 24:13 by " .. (ns.PlayerName() or "you") .. "'s group")
                    end)
                end
            end)
        end
    end)
    fx.run = runId
end

local function startRift(size)
    local r = fx.rift
    r.state, r.runId, r.floor, r.startedAt, r.size, r.deaths = 1, 8000 + seq, 1, GetTime(), size, 0
    r.boss = BOSSES[1]
    pushRift()
    for f = 2, 6 do
        after((f - 1) * 3, function()
            r.floor = f
            r.boss = BOSSES[(f - 1) % #BOSSES + 1]
            pushRift()
        end)
    end
    after(18, function()
        r.state = 2
        Demo.Push("RIFT", { { r.runId, 2, 6, "", "", 18000, r.best, "", 42, 1, size } })
        Demo.Push("RIFTE", { { r.runId, 6, 18000, "", 0, "" }, { "C", 20 }, { "T", 1, "", "Eclipse Shard" } })
        fx.queue = { state = 0 }
        pushQueue()
    end)
end

function Demo.Chat(text)
    if DEFAULT_CHAT_FRAME then
        local _, msg = ns.Chat.Filter(DEFAULT_CHAT_FRAME, "CHAT_MSG_SYSTEM", text)
        DEFAULT_CHAT_FRAME:AddMessage(msg or U.Safe(text), 1, 1, 0)
    end
end

------------------------------------------------------------------------------------------------------
-- Intent responder
------------------------------------------------------------------------------------------------------
function Demo.Respond(op, payload)
    local recs = Comm.SplitRecords(payload)
    local f = recs[1] or {}
    -- Bleakhold Royale's scripted match (Royale.lua) answers its own intents
    if ns.Royale and ns.Royale.DemoRespond(op, recs) then
        return
    end
    -- War Mode and a short Front (WarMode.lua): WARMODE, and its topics of a GET
    if ns.WarMode and ns.WarMode.DemoRespond(op, recs) then
        return
    end
    -- the arena season, its ladder and the 1v1 queue (Arena.lua)
    if ns.Arena and ns.Arena.DemoRespond(op, recs) then
        return
    end
    if op == "HELLO" then
        pushHello()
    elseif op == "GET" then
        for _, r in ipairs(recs) do
            local push = TOPIC_PUSH[r[1]]
            if r[1] == "SET" then
                pushSet(r[2], r[3])
            elseif push then
                push()
            end
        end
    elseif op == "TCLAIM" then
        local t = findTask(tonumber(f[1]))
        if t and t[9] == 1 then
            t[9] = 2
            taskDelta(t)
            if t[6] == "C" then
                fx.week.coins = min(fx.week.cap, fx.week.coins + t[7])
                pushWeek()
            end
        else
            Demo.Push("ERR", { { "TCLAIM", "", "not_claimable", "That task cannot be claimed yet." } })
        end
    elseif op == "TREROLL" then
        local t = findTask(tonumber(f[1]))
        if t and t[9] == 0 then
            t[3] = (t[3] % 8) + 1
            t[4] = 0
            t[10], t[11] = "", ""
            fx.freeRerolls = max(0, fx.freeRerolls - 1)
            pushTasks()
        end
    elseif op == "QJOIN" then
        local kind, activity, tier, roles, size = f[1], tonumber(f[2]), tonumber(f[3]), tonumber(f[4]), tonumber(f[5])
        if size == 1 then
            if kind == "R" then
                fx.queue = { state = 3, kind = "R", activity = 0, size = 1 }
                pushQueue()
                startRift(1)
            else
                fx.queue = { state = 3, kind = "D", activity = activity, tier = tier, size = 1 }
                pushQueue()
                Demo.Push("TOAST", { { "Q", "Entering " .. ns.DungeonName(activity), "Solo run - the dungeon scales to you", "dungeons" } })
                after(6, function()
                    fx.queue = { state = 0 }
                    pushQueue()
                end)
            end
            return
        end
        fx.queue = { state = 1, kind = kind, activity = activity, tier = tier, size = size, roles = roles, queued = 0 }
        pushQueue()
        Demo.Chat("[Queue] " .. (ns.PlayerName() or "Someone") .. " is looking for a group: " .. (kind == "R" and "Eclipse Rift" or ns.DungeonName(activity)))
        after(4, function()
            if fx.queue.state == 1 then
                fx.queue.state = 2
                pushQueue()
            end
        end)
    elseif op == "QLEAVE" then
        fx.queue = { state = 0 }
        pushQueue()
    elseif op == "QREPLY" then
        if fx.queue.state == 2 then
            if f[2] == "1" then
                local kind = fx.queue.kind
                fx.queue.state = 3
                pushQueue()
                if kind == "R" then
                    startRift(5)
                else
                    after(6, function()
                        fx.queue = { state = 0 }
                        pushQueue()
                    end)
                end
            else
                fx.queue = { state = 0 }
                pushQueue()
            end
        end
    elseif op == "KMODE" then
        fx.key.mode = tonumber(f[1]) or 0
        pushKey()
    elseif op == "KSTART" then
        startKey()
    elseif op == "KCANCEL" then
        if fx.run then
            Demo.Push("MP", { { fx.run, 0, 1800, 0, 0, 0, 100, 0, "", "", 4 } })
            fx.run = nil
        end
    elseif op == "BCLAIM" then
        if fx.board.bountyState == 2 then
            fx.board.bountyState = 3
            fx.week.shards = fx.week.shards + 50
            pushBoard()
            pushWeek()
        end
    elseif op == "WEHANDIN" then
        if fx.season.tokens > 0 then
            fx.season.points = fx.season.points + fx.season.tokens * 40
            fx.season.tokens = 0
            pushSeason()
            Demo.Push("TOAST", { { "S", "Tokens handed in", "Your part of the War Effort grew", "season" } })
        end
    elseif op == "OUTFIT" then
        Demo.Push("ERR", { { "OUTFIT", "", "locked", "Collect every piece of the set first." } })
    elseif op == "LBQ" then
        pushLB(f[1], tonumber(f[2]), tonumber(f[3]), tonumber(f[4]), tonumber(f[5]))
    elseif op == "PING" then
        Demo.Push("PONG", { { f[1], time() } })
    end
end

------------------------------------------------------------------------------------------------------
-- On / off
------------------------------------------------------------------------------------------------------
function Demo.Start()
    Demo.Stop(true)
    Comm.Reset()
    ns.ResetState()
    resetFixtures()
    if ns.WarMode then
        ns.WarMode.DemoReset()
    end
    Comm.demo = Demo.Respond
    Comm.SendHello()
    -- a task finishes a little later, to show the toast
    after(8, function()
        local t = findTask(102)
        if t and t[9] == 0 then
            t[4], t[9] = 20, 1
            taskDelta(t)
        end
    end)
    Demo.Chat("[Raid Legacy] Aldric found [Belt of Might]")
    Demo.Chat("[Server First] Echo of Ragnaros defeated by Ironvow")
    Demo.Chat("[Season] War Effort reached 62% - Breach the Greymane Wall")
    ns.Print("demo mode on: the windows show sample data and nothing is sent to the server. /bh demo off to leave.")
    UI.Open("tasks")
end

function Demo.Stop(silent)
    for _, t in ipairs(timers) do
        ns.Cancel(t)
    end
    wipe(timers)
    wipe(rev)
    if not Comm.demo then
        return
    end
    Comm.demo = nil
    Comm.Reset()
    ns.ResetState()
    for _, w in pairs(UI.windows) do
        w:Hide()
    end
    if ns.KeyTracker then
        ns.KeyTracker.frame:Hide()
    end
    if ns.Countdown then
        ns.Countdown.frame:Hide()
    end
    if not silent then
        ns.Print("demo mode off.")
        if Comm.canSend then
            Comm.SendHello()
        end
    end
end

ns.AddCommand("demo", "preview every window with sample data: /bh demo [off]", function(args)
    if (args or ""):lower() == "off" then
        Demo.Stop(false)
    else
        Demo.Start()
    end
end)
