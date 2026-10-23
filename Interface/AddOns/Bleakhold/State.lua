-- Bleakhold: server state. Each S2C op is parsed here into plain tables; windows only read these.
-- Every field goes through ns.U (missing or malformed -> default), so garbage never raises.
local ADDON, ns = ...
local U, Comm, Data = ns.U, ns.Comm, ns.Data

local type, pairs, ipairs, tostring = type, pairs, ipairs, tostring
local bit = bit

local INT32 = 2147483647
local S = {}
ns.S = S

local function reset()
    S.week = nil
    S.era = nil
    S.tasks = nil
    S.key = nil
    S.board = nil
    S.queue = nil
    S.mplus = nil
    S.rift = nil
    S.coll = nil
    S.sets = {}
    S.lidx = {}
    S.season = nil
    S.lb = {}
    S.lbme = {}
    S.firsts = nil
    S.err = nil
end
reset()
ns.ResetState = reset

------------------------------------------------------------------------------------------------------
-- Definitions: server DEF entries over the built-in Data.defs
------------------------------------------------------------------------------------------------------
local memDefs = {}   -- used in demo mode and before saved variables load

local function defStore()
    if Comm.demo then
        return memDefs
    end
    if type(ns.db.defs) ~= "table" then
        ns.db.defs = {}
    end
    return ns.db.defs
end

function ns.Def(kind, id)
    if id == nil then
        return nil
    end
    local store = defStore()
    local k = store[kind]
    local v = k and k[id]
    if v ~= nil then
        return v
    end
    local fk = Data.defs[kind]
    return fk and fk[id]
end

function ns.DefName(kind, id, fallback)
    local d = ns.Def(kind, id)
    if d then
        return d.name or d.title or d.label or fallback
    end
    return fallback
end

-- All ids of a kind (server and built-in), sorted.
function ns.DefIds(kind)
    local seen, ids = {}, {}
    for _, src in ipairs({ defStore()[kind] or {}, Data.defs[kind] or {} }) do
        for id in pairs(src) do
            if not seen[id] then
                seen[id] = true
                ids[#ids + 1] = id
            end
        end
    end
    table.sort(ids)
    return ids
end

function ns.DungeonName(id)
    return ns.DefName("D", id, id and id > 0 and ("Dungeon #" .. id) or "Unknown dungeon")
end

function ns.AffixNames(ids)
    local out = {}
    for _, id in ipairs(ids or {}) do
        out[#out + 1] = ns.DefName("A", id, "Affix #" .. tostring(id))
    end
    return out
end

-- Classes: the ten stock classes plus extra classes the server defines (DEF X).
function ns.Classes()
    local list = {}
    for _, c in ipairs(Data.classes) do
        list[#list + 1] = c
    end
    for _, id in ipairs(ns.DefIds("X")) do
        local d = ns.Def("X", id)
        if d and not ns.ClassInfo(id, true) then
            list[#list + 1] = { id = id, token = d.token or ("CLASS" .. id), name = d.name or ("Class " .. id), short = d.short or "?", color = d.color or "B8B2A6" }
        end
    end
    return list
end

function ns.ClassInfo(id, stockOnly)
    for _, c in ipairs(Data.classes) do
        if c.id == id then
            return c
        end
    end
    if stockOnly then
        return nil
    end
    local d = ns.Def("X", id)
    if d then
        return { id = id, token = d.token or ("CLASS" .. id), name = d.name or ("Class " .. id), short = d.short or "?", color = d.color or "B8B2A6" }
    end
    return nil
end

function ns.ClassColor(id)
    local c = ns.ClassInfo(id)
    if c and RAID_CLASS_COLORS and RAID_CLASS_COLORS[c.token] then
        local rc = RAID_CLASS_COLORS[c.token]
        return string.format("%02X%02X%02X", (rc.r or 1) * 255, (rc.g or 1) * 255, (rc.b or 1) * 255)
    end
    return c and c.color or "ECE7DD"
end

local DEF_PARSERS = {
    A = function(f) return { name = U.Str(f[2], nil, 40), text = U.Str(f[3], nil, 200) } end,
    E = function(f) return { name = U.Str(f[2], nil, 48), text = U.Str(f[3], nil, 200), tier = U.Int(f[4], nil, 0, 99) } end,
    T = function(f) return { title = U.Str(f[2], nil, 48), text = U.Str(f[3], nil, 200) } end,
    B = function(f) return { title = U.Str(f[2], nil, 48), text = U.Str(f[3], nil, 200) } end,
    C = function(f) return { name = U.Str(f[2], nil, 60), text = U.Str(f[3], nil, 200) } end,
    D = function(f)
        local bosses = {}
        for _, b in ipairs(U.List(f[6], 12)) do
            bosses[#bosses + 1] = U.Str(b, "?", 40)
        end
        return {
            name = U.Str(f[2], nil, 48), chapter = U.Int(f[3], nil, 0, 999), lvlMin = U.Int(f[4], nil, 0, 255),
            lvlMax = U.Int(f[5], nil, 0, 255), bosses = bosses, timeLimitSec = U.Int(f[7], nil, 0, 86400),
        }
    end,
    L = function(f)
        return {
            label = U.Str(f[2], nil, 24), raids = U.Str(f[3], nil, 80), eraId = U.Int(f[4], nil, 0, INT32),
            sources = U.IntList(f[5], 12, 0, INT32), lvlMin = U.Int(f[6], nil, 0, 255), lvlMax = U.Int(f[7], nil, 0, 255),
            echoBoss = U.Str(f[8], nil, 48), total = U.Int(f[9], nil, 0, 99),
        }
    end,
    S = function(f) return { name = U.Str(f[2], nil, 60), text = U.Str(f[3], nil, 200), state = U.Int(f[4], 2, 0, 2) } end,
    K = function(f) return { name = U.Str(f[2], nil, 48) } end,
    W = function(f) return { name = U.Str(f[2], nil, 40), need = U.Str(f[3], nil, 120) } end,
    M = function(f) return { text = U.Str(f[2], nil, 200) } end,
    X = function(f) return { name = U.Str(f[2], nil, 24), token = U.Str(f[3], nil, 24), color = U.Str(f[4], nil, 6), short = U.Str(f[5], nil, 4) } end,
    R = function(f) return { name = U.Str(f[2], nil, 48) } end,
}
ns.DEF_PARSERS = DEF_PARSERS

Comm.Handle("DEF", function(r)
    local head = r[1] or {}
    local kind = U.Str(head[1], nil, 1)
    -- "DEF Z,dataVer" closes a complete set: only then is it kept for that dataVer
    if kind == "Z" then
        if not Comm.demo then
            ns.db.defsVer = U.Int(head[2], Comm.server.dataVer, 0, INT32)
        end
        ns.Fire("STATE", "DEF")
        return
    end
    local parse = kind and DEF_PARSERS[kind]
    if not parse then
        return
    end
    local store = defStore()
    store[kind] = store[kind] or {}
    local count = 0
    for i = 2, #r do
        local id = U.Int(r[i][1], nil, 0, INT32)
        if id and count < 2000 then
            store[kind][id] = parse(r[i])
            count = count + 1
        end
    end
    ns.Fire("STATE", "DEF")
end)
Comm.MapOpToTopic("DEF", "DEF")

------------------------------------------------------------------------------------------------------
-- Snapshot topics
------------------------------------------------------------------------------------------------------
local function changed(topic)
    ns.Fire("STATE", topic)
end

Comm.RegisterTopic("WEEK", "WEEK")
Comm.Handle("WEEK", function(r)
    local f = r[1]
    S.week = {
        keysTimed = U.Int(f[2], 0, 0, 9999), echoes = U.Int(f[3], 0, 0, 9999), riftBestFloor = U.Int(f[4], 0, 0, 9999),
        coins = U.Int(f[5], 0, 0, INT32), coinsCap = U.Int(f[6], 0, 0, INT32), shards = U.Int(f[7], nil, 0, INT32),
    }
    changed("WEEK")
end)

Comm.RegisterTopic("ERA", "ERA")
Comm.Handle("ERA", function(r)
    local f = r[1]
    S.era = {
        eraId = U.Int(f[2], nil, 0, INT32), nextEraId = U.Int(f[3], nil, 0, INT32), affixes = U.IntList(f[4], 6, 0, INT32),
        bonusId = U.Int(f[5], nil, 0, INT32), bonusDone = U.Bool(f[6], false),
    }
    changed("ERA")
end)

local REWARD_KINDS = { C = true, S = true, I = true, G = true, T = true }

local function parseTask(f)
    local uid = U.Int(f[1], nil, 1, INT32)
    if not uid then
        return nil
    end
    local kind = U.Str(f[2], "D", 1)
    if kind ~= "D" and kind ~= "W" then
        kind = "D"
    end
    local rk = U.Str(f[6], "T", 1)
    return {
        uid = uid, kind = kind, templateId = U.Int(f[3], nil, 0, INT32),
        have = U.Int(f[4], 0, 0, INT32), need = U.Int(f[5], 1, 1, INT32),
        rewardKind = REWARD_KINDS[rk] and rk or "T", rewardAmount = U.Int(f[7], 0, 0, INT32), rewardItemId = U.Int(f[8], nil, 1, INT32),
        state = U.Int(f[9], 0, 0, 2), title = U.Str(f[10], nil, 48), text = U.Str(f[11], nil, 200), rewardText = U.Str(f[12], nil, 60),
    }
end

function ns.TaskTitle(t)
    if t.title then
        return t.title
    end
    local d = ns.Def("T", t.templateId)
    return d and d.title or "Task"
end

function ns.TaskText(t)
    if t.text then
        return t.text
    end
    local d = ns.Def("T", t.templateId)
    return d and d.text or ""
end

-- "20 Mythic Coins", "1 Shard", an item name, gold text or the server's text.
function ns.RewardText(kind, amount, itemId, text)
    if text then
        return text
    end
    amount = amount or 0
    if kind == "C" then
        return U.Commas(amount) .. " Mythic Coins"
    elseif kind == "S" then
        return U.Commas(amount) .. (amount == 1 and " Shard" or " Shards")
    elseif kind == "G" then   -- copper, like the client's money values
        local g = math.floor(amount / 10000)
        local s = math.floor((amount % 10000) / 100)
        local c = amount % 100
        local parts = {}
        if g > 0 then parts[#parts + 1] = U.Commas(g) .. "g" end
        if s > 0 then parts[#parts + 1] = s .. "s" end
        if c > 0 or #parts == 0 then parts[#parts + 1] = c .. "c" end
        return table.concat(parts, " ")
    elseif kind == "I" and itemId then
        local name = GetItemInfo(itemId)
        local prefix = amount > 1 and (amount .. "x ") or ""
        return prefix .. (name or ("item #" .. itemId))
    end
    return amount > 0 and tostring(amount) or "Reward"
end

function ns.TaskReward(t)
    return ns.RewardText(t.rewardKind, t.rewardAmount, t.rewardItemId, t.rewardText)
end

Comm.RegisterTopic("TASKS", "TASKS", { "TASK" })
Comm.Handle("TASKS", function(r)
    local f = r[1]
    local tasks = { freeRerolls = U.Int(f[2], 0, 0, 99), rerollCost = U.Int(f[3], 0, 0, INT32), rerollCurrency = U.Str(f[4], "G", 1), byUid = {}, daily = {}, weekly = {} }
    for i = 2, #r do
        local t = parseTask(r[i])
        if t and not tasks.byUid[t.uid] and #tasks.daily + #tasks.weekly < 24 then
            tasks.byUid[t.uid] = t
            local list = t.kind == "W" and tasks.weekly or tasks.daily
            list[#list + 1] = t
        end
    end
    local old = S.tasks
    S.tasks = tasks
    -- a task that became claimable since the last snapshot gets its toast too
    if old then
        for uid, t in pairs(tasks.byUid) do
            local o = old.byUid[uid]
            if o and o.state == 0 and t.state == 1 then
                ns.Fire("TASK_DONE", t)
            end
        end
    end
    changed("TASKS")
end)

Comm.Handle("TASK", function(r)
    local f = r[1]
    local uid = U.Int(f[2], nil, 1, INT32)
    local t = uid and S.tasks and S.tasks.byUid[uid]
    if not t then
        Comm.Refresh("TASKS")
        return
    end
    local before = t.state
    t.have = U.Int(f[3], t.have, 0, INT32)
    t.state = U.Int(f[4], t.state, 0, 2)
    if before == 0 and t.state == 1 then
        ns.Fire("TASK_DONE", t)
    end
    changed("TASKS")
end)

function ns.ClaimableTasks()
    local n = 0
    if S.tasks then
        for _, t in pairs(S.tasks.byUid) do
            if t.state == 1 then
                n = n + 1
            end
        end
    end
    return n
end

Comm.RegisterTopic("KEY", "KEY")
Comm.Handle("KEY", function(r)
    local f = r[1]
    local dungeonId = U.Int(f[2], 0, 0, INT32)
    S.key = {
        dungeonId = dungeonId, hasKey = dungeonId > 0, level = U.Int(f[3], 0, 0, 99), affixes = U.IntList(f[4], 6, 0, INT32),
        mode = U.Int(f[5], 0, 0, 2), weeklyBest = U.Int(f[6], 0, 0, 99), weeklyBestDungeon = U.Int(f[7], nil, 0, INT32),
        cachesReady = U.Int(f[8], 0, 0, 999), cachesBanked = U.Int(f[9], 0, 0, 999), itemId = U.Int(f[10], nil, 1, INT32),
        maxLevel = U.Int(f[11], 15, 2, 99), eraId = U.Int(f[12], nil, 0, INT32), depleted = U.Bool(f[13], false),
    }
    changed("KEY")
end)

Comm.RegisterTopic("BOARD", "BOARD")
Comm.Handle("BOARD", function(r)
    local f = r[1]
    local b = {
        shards = U.Int(f[2], nil, 0, INT32), bountyId = U.Int(f[3], nil, 1, INT32), bountyDungeon = U.Int(f[4], nil, 0, INT32),
        bountyState = U.Int(f[5], 0, 0, 3), bountyReward = U.Str(f[6], nil, 60), firstRunBonus = U.Bool(f[7], false),
        dungeons = {}, byId = {},
    }
    for i = 2, #r do
        local d = r[i]
        local id = U.Int(d[1], nil, 1, INT32)
        if id and not b.byId[id] and #b.dungeons < 120 then
            local def = ns.Def("D", id) or {}
            local e = {
                id = id, chapter = U.Int(d[2], def.chapter or 0, 0, 999), lvlMin = U.Int(d[3], def.lvlMin, 0, 255),
                lvlMax = U.Int(d[4], def.lvlMax, 0, 255), tierBits = U.Int(d[5], 1, 0, 255), bestScore = U.Int(d[6], nil, 0, INT32),
                bestTier = U.Int(d[7], nil, 0, 9), recordScore = U.Int(d[8], nil, 0, INT32), recordName = U.Str(d[9], nil, 24),
                locked = U.Bool(d[10], false),
            }
            b.byId[id] = e
            b.dungeons[#b.dungeons + 1] = e
        end
    end
    table.sort(b.dungeons, function(x, y)
        if x.chapter ~= y.chapter then
            return x.chapter < y.chapter
        end
        if (x.lvlMin or 0) ~= (y.lvlMin or 0) then
            return (x.lvlMin or 0) < (y.lvlMin or 0)
        end
        return x.id < y.id
    end)
    S.board = b
    changed("BOARD")
end)

Comm.RegisterTopic("QUEUE", "QUEUE")
Comm.Handle("QUEUE", function(r)
    local f = r[1]
    local kind = U.Str(f[3], "D", 1)
    local q = {
        state = U.Int(f[2], 0, 0, 3), kind = (kind == "R") and "R" or "D", activityId = U.Int(f[4], 0, 0, INT32),
        tier = U.Int(f[5], 0, 0, 9), size = U.Int(f[6], 5, 1, 5), queuedSec = U.Int(f[7], 0, 0, 864000),
        estWaitSec = U.Int(f[8], nil, 0, 864000), proposalId = U.Int(f[9], nil, 1, INT32), timeoutSec = U.Int(f[10], nil, 0, 3600),
        bandMin = U.Int(f[11], nil, 0, 255), bandMax = U.Int(f[12], nil, 0, 255), members = {}, recvAt = GetTime(),
    }
    for i = 2, math.min(#r, 41) do
        local m = r[i]
        local name = U.Str(m[1], nil, 24)
        if name then
            q.members[#q.members + 1] = {
                name = name, classId = U.Int(m[2], 0, 0, 255), role = U.Int(m[3], 0, 0, 7),
                accepted = U.Int(m[4], 0, 0, 2), level = U.Int(m[5], nil, 0, 255),
            }
        end
    end
    local before = S.queue and S.queue.state or 0
    S.queue = q
    if q.state == 2 and before ~= 2 then
        ns.Fire("QUEUE_PROPOSAL", q)
    end
    changed("QUEUE")
end)

------------------------------------------------------------------------------------------------------
-- Mythic+ run (not revisioned: MP is a full state sent on every change and as a heartbeat)
------------------------------------------------------------------------------------------------------
Comm.MapOpToTopic("MPS", "MPLUS")
Comm.MapOpToTopic("MP", "MPLUS")
Comm.Handle("MPS", function(r)
    local f = r[1]
    local runId = U.Int(f[1], nil, 1, INT32)
    if not runId then
        return
    end
    local m = {
        runId = runId, dungeonId = U.Int(f[2], 0, 0, INT32), level = U.Int(f[3], 0, 0, 99), affixes = U.IntList(f[4], 6, 0, INT32),
        eraId = U.Int(f[5], nil, 0, INT32), countdownMs = U.Int(f[6], 0, 0, 120000), timeLimitSec = U.Int(f[7], 0, 0, 86400),
        startedAt = GetTime(), state = 0, elapsedMs = 0, elapsedAt = GetTime(), deaths = 0, deathPenaltySec = 0,
        forcesCur = 0, forcesMax = 0, bossBits = 0, bossKillSec = {}, chestSec = {},
    }
    S.mplus = m
    ns.Fire("MPLUS_START", m)
    changed("MPLUS")
end)

Comm.Handle("MP", function(r)
    local f = r[1]
    local runId = U.Int(f[1], nil, 1, INT32)
    if not runId then
        return
    end
    local m = S.mplus
    if not m or m.runId ~= runId then
        m = { runId = runId, dungeonId = 0, level = 0, affixes = {}, countdownMs = 0, startedAt = GetTime() }
        S.mplus = m
        Comm.Get("MPLUS")
    end
    m.elapsedMs = U.Int(f[2], m.elapsedMs or 0, 0, 864000000)
    m.elapsedAt = GetTime()
    m.timeLimitSec = U.Int(f[3], m.timeLimitSec or 0, 0, 86400)
    m.deaths = U.Int(f[4], 0, 0, 9999)
    m.deathPenaltySec = U.Int(f[5], 0, 0, 86400)
    m.forcesCur = U.Int(f[6], 0, 0, INT32)
    m.forcesMax = U.Int(f[7], 0, 0, INT32)
    m.bossBits = U.Int(f[8], 0, 0, INT32)
    m.bossKillSec = U.IntList(f[9], 16, 0, 86400)
    m.chestSec = U.IntList(f[10], 4, 0, 86400)
    local before = m.state
    m.state = U.Int(f[11], 1, 0, 4)
    if before == 0 and m.state >= 1 and m.state <= 3 then
        ns.Fire("MPLUS_GO", m)
    end
    if m.state == 4 then
        ns.Fire("MPLUS_ABANDONED", m)
    end
    changed("MPLUS")
end)

Comm.Handle("MPE", function(r)
    local f = r[1]
    local res = {
        runId = U.Int(f[1], nil, 1, INT32), result = U.Int(f[2], 0, 0, 2), timeMs = U.Int(f[3], 0, 0, 864000000),
        keyDelta = U.Int(f[4], 0, -99, 99), newDungeonId = U.Int(f[5], nil, 0, INT32), newLevel = U.Int(f[6], nil, 0, 99),
        score = U.Int(f[7], nil, 0, INT32), rewards = {},
    }
    for i = 2, math.min(#r, 21) do
        local rw = r[i]
        res.rewards[#res.rewards + 1] = ns.RewardText(U.Str(rw[1], "T", 1), U.Int(rw[2], 0, 0, INT32), U.Int(rw[3], nil, 1, INT32), U.Str(rw[4], nil, 60))
    end
    local m = S.mplus
    if m and res.runId and m.runId == res.runId then
        m.result = res
        if res.result == 1 then
            m.state = 2
        elseif res.result == 0 then
            m.state = 3
        else
            m.state = 4
        end
    else
        S.mplus = { runId = res.runId or 0, dungeonId = 0, level = 0, affixes = {}, result = res, state = 3 }
    end
    ns.Fire("MPLUS_END", res)
    changed("MPLUS")
end)

-- Elapsed run time in seconds, counted on from the last MP (anchored to GetTime()).
function ns.MplusElapsed(m)
    m = m or S.mplus
    if not m then
        return 0
    end
    if m.result then
        return (m.result.timeMs or 0) / 1000
    end
    local e = (m.elapsedMs or 0) / 1000
    if m.state == 1 then
        e = e + (GetTime() - (m.elapsedAt or GetTime()))
    end
    return e
end

------------------------------------------------------------------------------------------------------
-- Eclipse Rift (no rules on the client: everything shown is what the server sends)
------------------------------------------------------------------------------------------------------
Comm.MapOpToTopic("RIFT", "RIFT")
Comm.Handle("RIFT", function(r)
    local f = r[1]
    S.rift = S.rift or {}
    local rf = S.rift
    rf.runId = U.Int(f[1], nil, 0, INT32)
    rf.state = U.Int(f[2], 0, 0, 2)
    rf.floor = U.Int(f[3], nil, 0, 9999)
    rf.bossId = U.Int(f[4], nil, 0, INT32)
    rf.bossName = U.Str(f[5], nil, 48) or (rf.bossId and ns.DefName("R", rf.bossId))
    rf.elapsedMs = U.Int(f[6], nil, 0, 864000000)
    rf.elapsedAt = GetTime()
    rf.bestFloor = U.Int(f[7], nil, 0, 9999)
    rf.score = U.Int(f[8], nil, 0, INT32)
    rf.rank = U.Int(f[9], nil, 1, INT32)
    rf.deaths = U.Int(f[10], nil, 0, 9999)
    rf.groupSize = U.Int(f[11], nil, 1, 5)
    if rf.state == 1 then
        rf.summary = nil
    end
    changed("RIFT")
end)

Comm.Handle("RIFTE", function(r)
    local f = r[1]
    S.rift = S.rift or {}
    local sm = {
        runId = U.Int(f[1], nil, 0, INT32), floor = U.Int(f[2], nil, 0, 9999), timeMs = U.Int(f[3], nil, 0, 864000000),
        score = U.Int(f[4], nil, 0, INT32), newBest = U.Bool(f[5], false), rank = U.Int(f[6], nil, 1, INT32), rewards = {},
    }
    for i = 2, math.min(#r, 21) do
        local rw = r[i]
        sm.rewards[#sm.rewards + 1] = ns.RewardText(U.Str(rw[1], "T", 1), U.Int(rw[2], 0, 0, INT32), U.Int(rw[3], nil, 1, INT32), U.Str(rw[4], nil, 60))
    end
    S.rift.summary = sm
    S.rift.state = 2
    if sm.floor and (not S.rift.bestFloor or sm.floor > S.rift.bestFloor) and sm.newBest then
        S.rift.bestFloor = sm.floor
    end
    ns.Fire("RIFT_END", sm)
    changed("RIFT")
end)

------------------------------------------------------------------------------------------------------
-- Collections
------------------------------------------------------------------------------------------------------
Comm.RegisterTopic("COLL", "COLL")
Comm.Handle("COLL", function(r)
    local f = r[1]
    S.coll = {
        transmogOwned = U.Int(f[2], nil, 0, INT32), transmogTotal = U.Int(f[3], nil, 0, INT32),
        laterOwned = U.Int(f[4], nil, 0, INT32), laterTotal = U.Int(f[5], nil, 0, INT32),
        setsOwned = U.Int(f[6], nil, 0, INT32), setsTotal = U.Int(f[7], nil, 0, INT32),
        tierHave = U.IntList(f[8], 16, 0, 999), tierTotal = U.IntList(f[9], 16, 0, 999),
    }
    changed("COLL")
end)

local function setKey(tier, classId)
    return tostring(tier) .. ":" .. tostring(classId)
end
ns.SetKey = setKey

Comm.Handle("SET", function(r)
    local f = r[1]
    local tier = U.Int(f[1], nil, 0, 99)
    local classId = U.Int(f[3], nil, 0, 255)
    if not tier or not classId then
        return
    end
    local set = {
        tier = tier, setId = U.Int(f[2], nil, 1, INT32), classId = classId, name = U.Str(f[4], nil, 60),
        collectedBits = U.Int(f[5], 0, 0, INT32), outfitUnlocked = U.Bool(f[6], false), items = U.IntList(f[7], 12, 1, INT32),
        sources = U.IntList(f[8], 12, 0, INT32), lvlMin = U.Int(f[9], nil, 0, 255), lvlMax = U.Int(f[10], nil, 0, 255),
        echoBoss = U.Str(f[11], nil, 48), note = U.Str(f[12], nil, 120),
    }
    S.sets[setKey(tier, classId)] = set
    for i, itemId in ipairs(set.items) do
        S.lidx[itemId] = S.lidx[itemId] or {}
        local e = S.lidx[itemId]
        e.tier, e.setId = tier, set.setId
        e.collected = bit.band(set.collectedBits, bit.lshift(1, i - 1)) ~= 0
    end
    changed("SET")
end)

function ns.SetCollected(set, i)
    return bit.band(set.collectedBits or 0, bit.lshift(1, i - 1)) ~= 0
end

Comm.RegisterTopic("LIDX", "LIDX", { "LCOL" })
Comm.Handle("LIDX", function(r)
    local idx = {}
    for i = 2, math.min(#r, 4001) do
        local e = r[i]
        local itemId = U.Int(e[1], nil, 1, INT32)
        if itemId then
            idx[itemId] = { tier = U.Int(e[2], nil, 0, 99), setId = U.Int(e[3], nil, 1, INT32), collected = U.Bool(e[4], false) }
        end
    end
    S.lidx = idx
    changed("LIDX")
end)

Comm.Handle("LCOL", function(r)
    local f = r[1]
    local itemId = U.Int(f[2], nil, 1, INT32)
    if itemId then
        S.lidx[itemId] = S.lidx[itemId] or {}
        S.lidx[itemId].collected = U.Bool(f[3], false)
        changed("LIDX")
    end
end)

------------------------------------------------------------------------------------------------------
-- Season
------------------------------------------------------------------------------------------------------
Comm.RegisterTopic("SEASON", "SEASON")
Comm.Handle("SEASON", function(r)
    local f = r[1]
    local s = {
        seasonId = U.Int(f[2], nil, 0, INT32), wePermille = U.Int(f[3], 0, 0, 1000), contributors = U.Int(f[4], 0, 0, INT32),
        points = U.Int(f[5], 0, 0, INT32), rankId = U.Int(f[6], nil, 0, INT32), nextRankId = U.Int(f[7], nil, 0, INT32),
        nextRankPoints = U.Int(f[8], nil, 0, INT32), title = U.Str(f[9], nil, 60), text = U.Str(f[10], nil, 200),
        tokens = U.Int(f[11], nil, 0, INT32), parts = {}, rewards = {},
    }
    for i = 2, math.min(#r, 41) do
        local e = r[i]
        local tag = U.Str(e[1], nil, 1)
        if tag == "P" and #s.parts < 6 then
            s.parts[#s.parts + 1] = { name = U.Str(e[2], "?", 40), permille = U.Int(e[3], 0, 0, 1000) }
        elseif tag == "R" and #s.rewards < 8 then
            local id = U.Int(e[2], nil, 0, INT32)
            if id then
                s.rewards[#s.rewards + 1] = { id = id, earned = U.Int(e[3], 0, 0, 1) == 1, stateText = U.Str(e[4], nil, 40) }
            end
        end
    end
    S.season = s
    changed("SEASON")
end)

------------------------------------------------------------------------------------------------------
-- Leaderboards
------------------------------------------------------------------------------------------------------
local BOARDS = { K = true, R = true, E = true, F = true }
ns.BOARDS = BOARDS

Comm.Handle("LB", function(r)
    local f = r[1]
    local board = U.Str(f[1], nil, 1)
    if not board or not BOARDS[board] then
        return
    end
    local lb = {
        board = board, seasonId = U.Int(f[2], 0, 0, INT32), dungeonId = U.Int(f[3], 0, 0, INT32), classId = U.Int(f[4], 0, 0, 255),
        page = U.Int(f[5], 1, 1, 999), pages = U.Int(f[6], 1, 1, 999), rows = {},
    }
    for i = 2, math.min(#r, 51) do
        local e = r[i]
        local row = {
            rank = U.Int(e[1], nil, 1, INT32), dungeonId = U.Int(e[2], nil, 0, INT32), value = U.Int(e[3], nil, 0, INT32),
            timeSec = U.Int(e[4], nil, -86400, 864000), date = U.Int(e[5], nil, 0, INT32), members = {}, label = U.Str(e[7], nil, 48),
        }
        for _, item in ipairs(U.List(e[6], 10)) do
            local t = U.Tuple(item, 2)
            local name = U.Str(t[1], nil, 24)
            if name then
                row.members[#row.members + 1] = { name = name, classId = U.Int(t[2], 0, 0, 255) }
            end
        end
        if row.rank then
            lb.rows[#lb.rows + 1] = row
        end
    end
    table.sort(lb.rows, function(a, b) return a.rank < b.rank end)
    S.lb[board] = lb
    changed("LB")
end)

Comm.Handle("LBME", function(r)
    local f = r[1]
    local board = U.Str(f[1], nil, 1)
    if not board or not BOARDS[board] then
        return
    end
    S.lbme[board] = {
        rank = U.Int(f[2], nil, 1, INT32), topPercent = U.Int(f[3], nil, 0, 100), value = U.Int(f[4], nil, 0, INT32),
        dungeonId = U.Int(f[5], nil, 0, INT32), timeSec = U.Int(f[6], nil, -86400, 864000), barPermille = U.Int(f[7], 0, 0, 1000),
        label = U.Str(f[8], nil, 48),
    }
    changed("LB")
end)

Comm.MapOpToTopic("FIRSTS", "FIRSTS")
Comm.Handle("FIRSTS", function(r)
    local list = {}
    for i = 1, math.min(#r, 50) do
        local e = r[i]
        local text = U.Str(e[2], nil, 120)
        if text then
            list[#list + 1] = { kind = U.Str(e[1], nil, 16), text = text, who = U.Str(e[3], nil, 80), date = U.Int(e[4], nil, 0, INT32) }
        end
    end
    S.firsts = list
    changed("FIRSTS")
end)

------------------------------------------------------------------------------------------------------
-- Errors and toasts
------------------------------------------------------------------------------------------------------
Comm.Handle("ERR", function(r)
    local f = r[1]
    local e = { op = U.Str(f[1], nil, 8), seq = U.Str(f[2], nil, 8), code = U.Str(f[3], nil, 24), text = U.Str(f[4], nil, 160), at = GetTime() }
    S.err = e
    ns.Fire("ERR", e)
    if e.text and UIErrorsFrame then
        UIErrorsFrame:AddMessage(U.Safe(e.text), 1, 0.45, 0.4)
    end
end)

------------------------------------------------------------------------------------------------------
-- Cases (section 15): which items are cases, what a case holds, and what opening one gave
------------------------------------------------------------------------------------------------------
S.cases = {}        -- [caseItemId] = true
S.caseDefs = {}     -- [caseItemId] = { id, title, text, keyItem, keyCount, rewards = { { itemId, count, chance, tier } } }

Comm.Handle("CASES", function(r)
    local list = {}
    for i = 1, math.min(#r, 200) do
        local id = U.Int(r[i][1], nil, 1, INT32)
        if id then
            list[id] = true
        end
    end
    S.cases = list
    changed("CASES")
end)

Comm.Handle("CASE", function(r)
    local f = r[1]
    local id = U.Int(f[1], nil, 1, INT32)
    if not id then
        return
    end
    local c = { id = id, title = U.Str(f[2], nil, 60), text = U.Str(f[3], nil, 120), keyItem = U.Int(f[4], nil, 1, INT32),
        keyCount = U.Int(f[5], 1, 1, 255), rewards = {} }
    for i = 2, math.min(#r, 61) do
        local g = r[i]
        local item = U.Int(g[1], nil, 1, INT32)
        if item then
            c.rewards[#c.rewards + 1] = { itemId = item, count = U.Int(g[2], 1, 1, 10000), chance = U.Int(g[3], 0, 0, 10000),
                tier = U.Int(g[4], 1, 0, 7) }
        end
    end
    S.caseDefs[id] = c
    S.cases[id] = true
    changed("CASE")
end)

Comm.Handle("UNBOX", function(r)
    local f = r[1]
    local e = { caseItemId = U.Int(f[1], nil, 1, INT32), index = U.Int(f[2], nil, 1, 60), itemId = U.Int(f[3], nil, 1, INT32),
        count = U.Int(f[4], 1, 1, 10000) }
    if e.caseItemId and e.index and e.itemId then
        ns.Fire("UNBOX", e)
    end
end)

local TOAST_TARGETS = { tasks = true, dungeons = true, keys = true, rift = true, collections = true, season = true, leaderboards = true }
Comm.Handle("TOAST", function(r)
    local f = r[1]
    local title = U.Str(f[2], nil, 60)
    if not title then
        return
    end
    local target = U.Str(f[4], nil, 16)
    ns.Fire("TOAST", { kind = U.Str(f[1], "I", 1), title = title, sub = U.Str(f[3], nil, 100), target = TOAST_TARGETS[target or ""] and target or nil })
end)

------------------------------------------------------------------------------------------------------
-- After the handshake: definitions and the topics the always-visible parts need
------------------------------------------------------------------------------------------------------
ns.On("HELLO", function(s)
    if s.dataVer and s.dataVer > 0 and tostring(ns.db.defsVer) ~= tostring(s.dataVer) then
        ns.db.defs = {}
        ns.db.defsVer = nil
        Comm.Get("DEF", 0)
    end
    Comm.Get("WEEK")
    Comm.Get("ERA")
    Comm.Get("TASKS")
    Comm.Get("KEY")
    Comm.Get("QUEUE")
    Comm.Get("MPLUS")
    Comm.Get("LIDX")
    if Comm.HasFeature(Comm.FEATURE.CASES) then
        Comm.Get("CASES")
    end
end)
