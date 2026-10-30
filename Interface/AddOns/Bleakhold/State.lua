-- Bleakhold: server state. Each S2C op is parsed here into plain tables; windows only read these.
-- Every field goes through ns.U (missing or malformed -> default), so garbage never raises.
local ADDON, ns = ...
local U, Comm, Data = ns.U, ns.Comm, ns.Data

local type, pairs, ipairs, tostring = type, pairs, ipairs, tostring
local bit = bit
local max, floor = math.max, math.floor

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
    S.camp = nil
    S.royale = nil
    S.royaleMap = nil
    S.royaleObjects = nil
    S.royaleFeed = {}
    S.royaleKills = {}
    S.royaleEvent = nil
    S.royaleResult = nil
    S.warMode = nil
    S.wpZone = nil
    S.wpCap = nil
    S.wpMap = nil
    S.wanted = nil
    S.warEvent = nil
    S.warZoneNames = {}
    S.warObjNames = {}
    S.arena = nil
    -- the café (section 21): see its section below for the shapes
    S.cafes = {}
    S.cafeState = nil
    S.cafeQueue = nil
    S.cafeTickets = {}
    S.cafeStep = nil
    S.cafeResult = nil
    S.cafeMenu = {}
    S.cafeOrder = nil
    S.cafeProfile = nil
    S.cafeBuffs = nil
    S.cafeSummary = nil
    S.cafeAtBar = {}
    S.cafeRaw = {}
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

-- The café's station letters (section 21): G grinder, E espresso machine, K kettle, C cold box, B blender, S syrup
-- shelf, V serving counter.
local CAFE_STATIONS = { G = true, E = true, K = true, C = true, B = true, S = true, V = true }
ns.CAFE_STATIONS = CAFE_STATIONS

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
    -- arena tiers and rewards (section 20)
    V = function(f) return { name = U.Str(f[2], nil, 30), color = U.Str(f[3], nil, 6), text = U.Str(f[4], nil, 120) } end,
    Q = function(f)
        return {
            seasonId = U.Int(f[2], 0, 0, INT32), bracket = U.Int(f[3], nil, 1, 5), tierId = U.Int(f[4], nil, 0, 99),
            kind = U.Str(f[5], nil, 1), entry = U.Int(f[6], 0, 0, INT32), count = U.Int(f[7], 1, 0, INT32),
            text = U.Str(f[8], nil, 60),
        }
    end,
    -- the café (section 21): H a café, G a barista action, F a recipe, U a barista level (its id is the level). The
    -- getters of Cafe.lua lay these over the built-in CafeData.lua; a field left empty keeps the built-in value.
    H = function(f)
        local team = U.Str(f[4], nil, 1)
        return {
            name = U.Str(f[2], nil, 48), cityKey = U.Str(f[3], nil, 8), team = (team == "A" or team == "H") and team or nil,
            zoneId = U.Int(f[5], nil, 0, INT32), mapId = U.Int(f[6], nil, 0, INT32), ownerName = U.Str(f[7], nil, 48),
            tagline = U.Str(f[8], nil, 160), colorHex = U.Str(f[9], nil, 6),
        }
    end,
    G = function(f)
        local station = U.Str(f[2], nil, 1)
        local kind = U.Str(f[4], nil, 1)
        return {
            station = station and CAFE_STATIONS[station] and station or nil, key = U.Int(f[3], nil, 1, 8),
            kind = (kind == "T" or kind == "H") and kind or nil, durMs = U.Int(f[5], nil, 1, 60000),
            goldLoPermille = U.Int(f[6], nil, 0, 1000), goldHiPermille = U.Int(f[7], nil, 0, 1000),
            name = U.Str(f[8], nil, 48), hordeName = U.Str(f[9], nil, 48), spellId = U.Int(f[10], nil, 0, INT32),
        }
    end,
    F = function(f)
        local family = U.Str(f[4], nil, 1)
        local steps = U.IntList(f[9], 12, 1, 63)
        return {
            cafeId = U.Int(f[2], nil, 1, 255), archetype = U.Int(f[3], nil, 1, 99),
            family = (family == "C" or family == "T" or family == "M") and family or nil, tier = U.Int(f[5], nil, 1, 9),
            unlockLevel = U.Int(f[6], nil, 1, 99), price80Copper = U.Int(f[7], nil, 0, INT32),
            buffMin = U.Int(f[8], nil, 0, 999), steps = #steps > 0 and steps or nil, name = U.Str(f[10], nil, 48),
            text = U.Str(f[11], nil, 160),
        }
    end,
    U = function(f) return { totalXp = U.Int(f[2], nil, 0, INT32), text = U.Str(f[3], nil, 160) } end,
}
ns.DEF_PARSERS = DEF_PARSERS
-- The kinds above, as a number: raise it whenever DEF_PARSERS gains a kind. A cache saved under another schema (an
-- addon that skipped kinds it did not know, such as V and Q before the arena, or H, G, F and U before the café) is
-- fetched again even when its dataVer matches the server's.
local DEF_SCHEMA = 3
ns.DEF_SCHEMA = DEF_SCHEMA

Comm.Handle("DEF", function(r)
    local head = r[1] or {}
    local kind = U.Str(head[1], nil, 1)
    -- "DEF Z,dataVer" closes a complete set: only then is it kept for that dataVer
    if kind == "Z" then
        if not Comm.demo then
            ns.db.defsVer = U.Int(head[2], Comm.server.dataVer, 0, INT32)
            ns.db.defsSchema = DEF_SCHEMA
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
    elseif kind == "H" then   -- honor (Bleakhold Royale results)
        return U.Commas(amount) .. " Honor"
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

-- kind D dungeon board, R Eclipse Rift, B Bleakhold Royale (section 17: the queue counts after bandMax, no members)
local QUEUE_KINDS = { D = true, R = true, B = true, A = true }

Comm.RegisterTopic("QUEUE", "QUEUE")
Comm.Handle("QUEUE", function(r)
    local f = r[1]
    local kind = U.Str(f[3], "D", 1)
    local q = {
        state = U.Int(f[2], 0, 0, 3), kind = QUEUE_KINDS[kind] and kind or "D", activityId = U.Int(f[4], 0, 0, INT32),
        tier = U.Int(f[5], 0, 0, 9), size = U.Int(f[6], 5, 1, 5), queuedSec = U.Int(f[7], 0, 0, 864000),
        estWaitSec = U.Int(f[8], nil, 0, 864000), proposalId = U.Int(f[9], nil, 1, INT32), timeoutSec = U.Int(f[10], nil, 0, 3600),
        bandMin = U.Int(f[11], nil, 0, 255), bandMax = U.Int(f[12], nil, 0, 255), members = {}, recvAt = GetTime(),
    }
    if q.kind == "B" then
        q.queued = U.Int(f[13], nil, 0, 99999)
        q.minPlayers = U.Int(f[14], nil, 0, 999)
        q.maxPlayers = U.Int(f[15], nil, 0, 999)
        q.accepted = U.Int(f[16], nil, 0, 999)
        q.proposalSize = U.Int(f[17], nil, 0, 999)
        q.matchesRunning = U.Int(f[18], nil, 0, 999)
    end
    for i = 2, (q.kind == "B" or q.kind == "A") and 1 or math.min(#r, 41) do
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
local BOARDS = { K = true, R = true, E = true, F = true, A = true, C = true }   -- C: the café (section 21)
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
        if board == "A" then
            -- section 20: the bracket in dungeonId, the rating in value, the team in label, then these
            row.wins = U.Int(e[8], nil, 0, 99999)
            row.games = U.Int(e[9], nil, 0, 99999)
            row.tierId = U.Int(e[10], nil, 0, 99)
            row.flags = U.Int(e[11], 0, 0, 255)
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
    if board == "A" then   -- section 20
        S.lbme.A.topPermille = U.Int(f[9], nil, 0, 1000)
        S.lbme.A.tierId = U.Int(f[10], nil, 0, 99)
    end
    changed("LB")
end)

------------------------------------------------------------------------------------------------------
-- Arena seasons and the 1v1 ladder (section 20): ARENA, the player's arena season (unrevisioned)
------------------------------------------------------------------------------------------------------
local ARENA_BRACKETS = { [1] = true, [2] = true, [3] = true, [5] = true }
ns.ARENA_BRACKETS = ARENA_BRACKETS

-- 1, 2, 3 or 5; anything else (9 too: U.Int would clamp it to 5) is no bracket
local function arenaBracket(raw)
    local b = U.Int(raw, nil, 0, 99)
    return b and ARENA_BRACKETS[b] and b or nil
end

Comm.MapOpToTopic("ARENA", "ARENA")
Comm.Handle("ARENA", function(r)
    local f = r[1]
    local a = {
        seasonId = U.Int(f[1], 0, 0, INT32), state = U.Int(f[2], 0, 0, 99), startEpoch = U.Int(f[3], nil, 0, INT32),
        endEpoch = U.Int(f[4], nil, 0, INT32), nextStartEpoch = U.Int(f[5], nil, 0, INT32), ratedOpen = U.Bool(f[6], false),
        teamCost = U.Int(f[7], nil, 0, INT32), seasonName = U.Str(f[8], nil, 48),
        seasons = {}, brackets = {}, cutoffs = {}, ladders = {}, matches = {}, finals = {}, recvAt = GetTime(),
    }
    for i = 2, #r do
        local e = r[i]
        local tag = U.Str(e[1], nil, 1)
        if tag == "S" and #a.seasons < 24 then
            local id = U.Int(e[2], nil, 0, INT32)
            if id and id >= 1 then
                a.seasons[#a.seasons + 1] = {
                    id = id, name = U.Str(e[3], nil, 48), state = U.Int(e[4], 0, 0, 2), startEpoch = U.Int(e[5], nil, 0, INT32),
                    endEpoch = U.Int(e[6], nil, 0, INT32),
                }
            end
        elseif tag == "B" then
            local b = arenaBracket(e[2])
            if b then
                a.brackets[b] = {
                    bracket = b, hasTeam = U.Bool(e[3], false), rating = U.Int(e[4], nil, 0, 99999),
                    rank = U.Int(e[5], nil, 1, INT32), size = U.Int(e[6], nil, 0, INT32), games = U.Int(e[7], nil, 0, 99999),
                    wins = U.Int(e[8], nil, 0, 99999), weekGames = U.Int(e[9], nil, 0, 99999),
                    weekWins = U.Int(e[10], nil, 0, 99999), personal = U.Int(e[11], nil, 0, 99999),
                    recent = U.Int(e[12], nil, 0, 99999), tierId = U.Int(e[13], nil, 0, 99), nextTierId = U.Int(e[14], nil, 0, 99),
                    toNext = U.Int(e[15], nil, 0, 99999), missing = U.Int(e[16], 0, 0, 255), team = U.Str(e[17], nil, 48),
                }
            end
        elseif tag == "T" and #a.cutoffs < 32 then
            local b = arenaBracket(e[2])
            local tier = U.Int(e[3], nil, 0, 99)
            if b and tier then
                a.cutoffs[#a.cutoffs + 1] = {
                    bracket = b, tierId = tier, slots = U.Int(e[4], 0, 0, INT32), cutRank = U.Int(e[5], nil, 1, INT32),
                    cutRating = U.Int(e[6], nil, 0, 99999), floor = U.Int(e[7], 0, 0, 99999),
                }
            end
        elseif tag == "N" then
            local b = arenaBracket(e[2])
            if b then
                a.ladders[b] = {
                    bracket = b, eligible = U.Int(e[3], 0, 0, INT32), rewardsOpen = U.Bool(e[4], true),
                    titlesOpen = U.Bool(e[5], true),
                }
            end
        elseif tag == "M" and #a.matches < 5 then
            local b = arenaBracket(e[2])
            if b then
                a.matches[#a.matches + 1] = {
                    bracket = b, won = U.Bool(e[3], false), change = U.Int(e[4], 0, -9999, 9999), opponent = U.Str(e[5], nil, 48),
                    endEpoch = U.Int(e[6], nil, 0, INT32), verdict = U.Int(e[7], 0, 0, 2), reason = U.Str(e[8], nil, 1),
                }
            end
        elseif tag == "F" then
            local b = arenaBracket(e[2])
            if b then
                a.finals[b] = {
                    bracket = b, rank = U.Int(e[3], nil, 1, INT32), rating = U.Int(e[4], nil, 0, 99999),
                    tierId = U.Int(e[5], nil, 0, 99), grant = U.Int(e[6], 0, 0, 2),
                }
            end
        end
    end
    if a.state > 6 then
        a.state = 0           -- a state this client does not know: shown as none (ratedOpen still says it all)
    end
    S.arena = a
    changed("ARENA")
end)

------------------------------------------------------------------------------------------------------
-- The café (section 21). Every café message is unrevisioned (the last one counts); the fields keep the protocol's
-- names. Times in ...Ms and ...Sec count from recvAt, the GetTime() the message arrived at (ns.Cafe.Left, LeftMs).
-- Yes/no fields keep the protocol's 0 and 1 (canOrder, byBarista, effective, levelUp, shakeActive, coffeeCounts,
-- staffDrink, eligible), except S.cafeState.onShift and a ticket's inHand, which are booleans. A lost chunk asks for
-- the op's state again (CAFEV for CAFT; CAFRES and CAFSUM for CAFST; CAFM needs its café id, so the menu asks itself;
-- CAFUI and CAFAT wait for the next one).
--   S.cafes[cafeId]      CAFE   { cafeId, open (0 off, 1 open, 2 paused, 3 not open yet, 4 closed for safety),
--                               baristas, queueLen, rushState (0 none, 1 soon, 2 live), rushSec, houseEtaSec }
--   S.cafeState          CAFST  the player as a barista, with .day (always) and .rush (on shift, else nil)
--   S.cafeQueue          CAFQ   { cafeId, count, cap, baristas, more, rows = { orderId, kind, recipeId, customer,
--                               patienceMs, patienceMaxMs, state, takenBy, needLevel, group } }
--   S.cafeTickets        CAFT   the tickets in ticket id order, each with steps = { { actionId, grade } }; {} none
--   S.cafeStep           CAFEV  the last step event; CAFE_STEP fires with it
--   S.cafeResult         CAFRES the last drink result; CAFE_RESULT fires
--   S.cafeMenu[cafeId]   CAFM   with rows (menu order) and byRecipe[recipeId] = row
--   S.cafeOrder          CAFO   the player's order, nil when there is none
--   S.cafeProfile        CAFP   with .week (W, or nil) and .last[cafeId] (L)
--   S.cafeBuffs          CAFBF  nil while no café buff runs; a timer that is not running is nil
--   S.cafeSummary        CAFSUM the last shift's summary; CAFE_SUMMARY fires
--   S.cafeAtBar[cafeId]  CAFAT  { cafeId, count, rows = { name, actionId, startedAgoMs, durMs, kind, stepIndex,
--                               stepCount } }
--   CAFUI                       not kept: CAFE_UI fires with what (menu, shift, board, help) and the café id
------------------------------------------------------------------------------------------------------
local CAFE_OPS = { CAFE = "CAFE", CAFST = "CAFST", CAFQ = "CAFQ", CAFT = "CAFT", CAFEV = "CAFT", CAFRES = "CAFST",
    CAFM = false, CAFO = "CAFO", CAFP = "CAFP", CAFBF = "CAFBF", CAFSUM = "CAFST", CAFUI = false, CAFAT = false }
for op, topic in pairs(CAFE_OPS) do
    if topic then
        Comm.MapOpToTopic(op, topic)
    end
end

-- the protocol's caps (BleakholdMessages.h): queue rows, tickets, steps, recipes, at-bar rows, name and line bytes
local CAFE_ROWS, CAFE_TICKETS, CAFE_STEPS, CAFE_RECIPES, CAFE_AT_ROWS = 8, 3, 12, 40, 6
local CAFE_NAME, CAFE_LINE = 48, 160
local CAFE_MS = 3600000          -- no café timer in milliseconds runs longer than an hour
local CAFE_SEC = 864000

local function letters(...)
    local t = {}
    for i = 1, select("#", ...) do
        t[select(i, ...)] = true
    end
    return t
end
local CAFE_KINDS = letters("N", "P", "G")                       -- an NPC, a player, an NPC of a Rush group
local CAFE_QUEUE_STATES = letters("W", "T", "H")                -- waiting, taken, the house makes it
local CAFE_GRADES = letters("N", "P", "G", "O")                 -- not done, Perfect, Good, Off
local CAFE_EVENTS = letters("S", "D", "I", "X", "W", "B")       -- started, done, interrupted, ruined, wrong, binned
local CAFE_QUALITIES = letters("P", "G", "S", "R", "L")         -- Perfect, Good, Sloppy, Ruined, Left
local CAFE_ORDER_STATES = letters("Q", "M", "H", "F", "R", "D", "X", "E")
local CAFE_END_REASONS = letters("E", "C", "A", "I", "W", "D", "M", "X", "O")
local CAFE_AT_KINDS = letters("T", "H")
local CAFE_WINDOWS = { menu = true, shift = true, board = true, help = true }

local function cafeLetter(raw, allowed, default)
    local s = U.Str(raw, nil, 1)
    if s and allowed[s] then
        return s
    end
    return default
end

-- an id: above 0 (U.Int clamps, so "0" would read as 1 with a floor of 1: the record 0 means none)
local function cafeIdOf(raw, hi)
    local v = U.Int(raw, nil, 0, hi or INT32)
    return v and v > 0 and v or nil
end

-- patience left and its total: the total is never below what is left
local function patience(rawLeft, rawMax)
    local left = U.Int(rawLeft, 0, 0, CAFE_MS)
    return left, max(left, U.Int(rawMax, 0, 0, CAFE_MS))
end

Comm.Handle("CAFE", function(r)
    local list, now = {}, GetTime()
    for i = 1, math.min(#r, 16) do
        local e = r[i]
        local id = cafeIdOf(e[1], 255)
        if id then
            list[id] = {
                cafeId = id, open = U.Int(e[2], 0, 0, 4), baristas = U.Int(e[3], 0, 0, 255), queueLen = U.Int(e[4], 0, 0, 999),
                rushState = U.Int(e[5], 0, 0, 2), rushSec = U.Int(e[6], nil, 0, CAFE_SEC),
                houseEtaSec = U.Int(e[7], nil, 0, CAFE_SEC), recvAt = now,
            }
        end
    end
    S.cafes = list
    changed("CAFE")
end)

Comm.Handle("CAFST", function(r)
    local f = r[1]
    local cafeId = U.Int(f[1], 0, 0, 255)
    local on = U.Bool(f[2], false) and cafeId > 0
    local st = {
        cafeId = cafeId, onShift = on, level = U.Int(f[3], 1, 1, 10), xp = U.Int(f[4], 0, 0, INT32),
        levelXp = U.Int(f[5], 0, 0, INT32), nextLevelXp = U.Int(f[6], nil, 0, INT32), shiftSec = U.Int(f[7], nil, 0, CAFE_SEC),
        drinks = U.Int(f[8], 0, 0, INT32), perfects = U.Int(f[9], 0, 0, INT32), streak = U.Int(f[10], 0, 0, INT32),
        tipsCopper = U.Int(f[11], 0, 0, INT32), shiftXp = U.Int(f[12], 0, 0, INT32),
        station = cafeLetter(f[13], CAFE_STATIONS), nearStation = cafeLetter(f[14], CAFE_STATIONS),
        nearDm = U.Int(f[15], nil, 0, 255), maxTickets = U.Int(f[16], 1, 1, CAFE_TICKETS),
        tiredSec = U.Int(f[17], nil, 0, CAFE_SEC), flags = U.Int(f[18], 0, 0, INT32), warnSec = U.Int(f[19], nil, 0, CAFE_SEC),
        recvAt = GetTime(),
    }
    for i = 2, math.min(#r, 4) do
        local e = r[i]
        local tag = U.Str(e[1], nil, 1)
        if tag == "D" then
            st.day = {
                dayXp = U.Int(e[2], 0, 0, INT32), dayXpFull = U.Int(e[3], 0, 0, INT32), dayXpHalf = U.Int(e[4], 0, 0, INT32),
                dayTipsCopper = U.Int(e[5], 0, 0, INT32), dayTipsCapCopper = U.Int(e[6], 0, 0, INT32),
                dayPoints = U.Int(e[7], 0, 0, INT32), dayPointsCap = U.Int(e[8], 0, 0, INT32), dayDrinks = U.Int(e[9], 0, 0, INT32),
            }
        elseif tag == "R" and on then
            st.rush = {
                rushState = U.Int(e[2], 0, 0, 2), rushSec = U.Int(e[3], nil, 0, CAFE_SEC), rushServed = U.Int(e[4], 0, 0, INT32),
                rushGoal = U.Int(e[5], 0, 0, INT32), myRushServed = U.Int(e[6], 0, 0, INT32),
            }
        end
    end
    st.day = st.day or { dayXp = 0, dayXpFull = 0, dayXpHalf = 0, dayTipsCopper = 0, dayTipsCapCopper = 0, dayPoints = 0,
        dayPointsCap = 0, dayDrinks = 0 }
    -- the Rush's seconds count from the same arrival (Cafe.Left reads recvAt)
    st.day.recvAt = st.recvAt
    if st.rush then
        st.rush.recvAt = st.recvAt
    end
    S.cafeState = st
    -- kept across /reload (S is not): after the next HELLO the client asks for the tickets and the queue too
    if not Comm.demo then
        ns.cdb.cafeOnShift = on or nil
    end
    changed("CAFST")
end)

Comm.Handle("CAFQ", function(r)
    local f = r[1]
    local q = {
        cafeId = U.Int(f[1], 0, 0, 255), count = U.Int(f[2], 0, 0, 9999), cap = U.Int(f[3], 0, 0, 9999),
        baristas = U.Int(f[4], 0, 0, 255), more = U.Int(f[5], 0, 0, 9999), rows = {}, recvAt = GetTime(),
    }
    for i = 2, math.min(#r, 1 + 4 * CAFE_ROWS) do
        local e = r[i]
        local id = cafeIdOf(e[1], INT32)
        if id and #q.rows < CAFE_ROWS then
            local left, total = patience(e[5], e[6])
            q.rows[#q.rows + 1] = {
                orderId = id, kind = cafeLetter(e[2], CAFE_KINDS, "N"), recipeId = cafeIdOf(e[3], 65535),
                customer = U.Str(e[4], nil, CAFE_NAME), patienceMs = left, patienceMaxMs = total,
                state = cafeLetter(e[7], CAFE_QUEUE_STATES, "W"), takenBy = U.Str(e[8], nil, CAFE_NAME),
                needLevel = U.Int(e[9], 0, 0, 99), group = U.Int(e[10], nil, 0, INT32),
            }
        end
    end
    S.cafeQueue = q
    changed("CAFQ")
end)

Comm.Handle("CAFT", function(r)
    local list, now = {}, GetTime()
    for i = 1, math.min(#r, 4 * CAFE_TICKETS) do
        local e = r[i]
        local id = cafeIdOf(e[1], INT32)
        if id and #list < CAFE_TICKETS then
            local steps = {}
            for _, item in ipairs(U.List(e[11], CAFE_STEPS)) do
                local t = U.Tuple(item, 2)
                local action = cafeIdOf(t[1], 63)
                if action then
                    steps[#steps + 1] = { actionId = action, grade = cafeLetter(t[2], CAFE_GRADES, "N") }
                end
            end
            local left, total = patience(e[6], e[7])
            list[#list + 1] = {
                ticketId = id, orderId = cafeIdOf(e[2], INT32), recipeId = cafeIdOf(e[3], 65535),
                kind = cafeLetter(e[4], CAFE_KINDS, "N"), customer = U.Str(e[5], nil, CAFE_NAME), patienceMs = left,
                patienceMaxMs = total, nextStep = U.Int(e[8], 1, 1, CAFE_STEPS), inHand = U.Bool(e[9], false),
                orderLine = U.Str(e[10], nil, CAFE_LINE), steps = steps, tipHintCopper = U.Int(e[12], 0, 0, INT32),
                recvAt = now,
            }
        end
    end
    table.sort(list, function(a, b) return a.ticketId < b.ticketId end)
    S.cafeTickets = list
    changed("CAFT")
end)

Comm.Handle("CAFEV", function(r)
    local f = r[1]
    local ticketId = cafeIdOf(f[1], INT32)
    local event = cafeLetter(f[4], CAFE_EVENTS)
    if not ticketId or not event then
        return
    end
    -- recvAt is the moment CREL's clientMs counts from (section 21): stamped here, as the message arrives
    local step = {
        ticketId = ticketId, stepIndex = U.Int(f[2], 1, 1, CAFE_STEPS), actionId = cafeIdOf(f[3], 63), event = event,
        durMs = U.Int(f[5], nil, 0, 60000), goldLoMs = U.Int(f[6], nil, 0, 60000), goldHiMs = U.Int(f[7], nil, 0, 60000),
        grade = cafeLetter(f[8], CAFE_GRADES), nextStep = U.Int(f[9], nil, 1, CAFE_STEPS), recvAt = GetTime(),
    }
    S.cafeStep = step
    -- the CAFT that follows can wait for the next 250 ms push: until it comes, the ticket takes the event's nextStep,
    -- so a press right after a release, a bin or a ruin names the step the server expects now
    -- (D done, X ruined, B binned: S, I and W leave the ticket where it was)
    local ticketMoved = false
    for _, t in ipairs(S.cafeTickets) do
        if t.ticketId == ticketId and (event == "D" or event == "X" or event == "B") then
            if step.nextStep and t.nextStep ~= step.nextStep then
                t.nextStep = step.nextStep
                ticketMoved = true
            end
            if event == "D" then
                if not t.inHand then t.inHand = true; ticketMoved = true end
                local s = t.steps[step.stepIndex]
                if s and step.grade and s.grade ~= step.grade then s.grade = step.grade; ticketMoved = true end
            elseif event == "X" or event == "B" then
                t.nextStep, t.inHand = 1, false
                for _, s in ipairs(t.steps) do s.grade = "N" end
                ticketMoved = true
            end
            break
        end
    end
    changed("CAFEV")
    ns.Fire("CAFE_STEP", step)
    -- after CAFE_STEP: the timing bar ends its run with the grade before the bar lays itself out again
    if ticketMoved then
        changed("CAFT")
    end
end)

Comm.Handle("CAFRES", function(r)
    local f = r[1]
    local quality = cafeLetter(f[3], CAFE_QUALITIES)
    if not quality then
        return
    end
    local res = {
        ticketId = cafeIdOf(f[1], INT32), recipeId = cafeIdOf(f[2], 65535), quality = quality,
        xp = U.Int(f[4], 0, 0, INT32), tipCopper = U.Int(f[5], 0, 0, INT32), points = U.Int(f[6], 0, 0, INT32),
        streak = U.Int(f[7], 0, 0, INT32), levelUp = U.Int(f[8], 0, 0, 1), level = U.Int(f[9], nil, 1, 10),
        customer = U.Str(f[10], nil, CAFE_NAME), line = U.Str(f[11], nil, CAFE_LINE), xpCapped = U.Int(f[12], 0, 0, INT32),
        recvAt = GetTime(),
    }
    S.cafeResult = res
    changed("CAFRES")
    ns.Fire("CAFE_RESULT", res)
end)

Comm.Handle("CAFM", function(r)
    local f = r[1]
    local id = cafeIdOf(f[1], 255)
    if not id then
        return
    end
    local m = {
        cafeId = id, open = U.Int(f[2], 0, 0, 4), baristas = U.Int(f[3], 0, 0, 255), houseEtaSec = U.Int(f[4], nil, 0, CAFE_SEC),
        pendingOrderId = U.Int(f[5], 0, 0, INT32), ordersToday = U.Int(f[6], 0, 0, 9999), ordersCap = U.Int(f[7], 0, 0, 9999),
        canOrder = U.Int(f[8], 0, 0, 1), reason = U.Str(f[9], nil, 24), rows = {}, byRecipe = {}, recvAt = GetTime(),
    }
    for i = 2, math.min(#r, 1 + CAFE_RECIPES) do
        local e = r[i]
        local recipeId = cafeIdOf(e[1], 65535)
        if recipeId and not m.byRecipe[recipeId] then
            local row = { recipeId = recipeId, priceCopper = U.Int(e[2], 0, 0, INT32), byBarista = U.Int(e[3], 0, 0, 1),
                effective = U.Int(e[4], 1, 0, 1) }
            m.rows[#m.rows + 1] = row
            m.byRecipe[recipeId] = row
        end
    end
    S.cafeMenu[id] = m
    changed("CAFM")
end)

Comm.Handle("CAFO", function(r)
    local f = r[1]
    local id = cafeIdOf(f[1], INT32)
    local state = cafeLetter(f[4], CAFE_ORDER_STATES)
    if id and state then
        S.cafeOrder = {
            orderId = id, cafeId = U.Int(f[2], 0, 0, 255), recipeId = cafeIdOf(f[3], 65535), state = state,
            position = U.Int(f[5], nil, 1, 9999), barista = U.Str(f[6], nil, CAFE_NAME), nextStep = U.Int(f[7], 0, 0, CAFE_STEPS),
            stepCount = U.Int(f[8], 0, 0, CAFE_STEPS), leftSec = U.Int(f[9], nil, 0, CAFE_SEC),
            priceCopper = U.Int(f[10], 0, 0, INT32), tipCopper = U.Int(f[11], 0, 0, INT32), recvAt = GetTime(),
        }
    else
        S.cafeOrder = nil     -- the record 0: no order
    end
    changed("CAFO")
end)

Comm.Handle("CAFP", function(r)
    local f = r[1]
    local p = {
        level = U.Int(f[1], 1, 1, 10), xp = U.Int(f[2], 0, 0, INT32), levelXp = U.Int(f[3], 0, 0, INT32),
        nextLevelXp = U.Int(f[4], nil, 0, INT32), drinks = U.Int(f[5], 0, 0, INT32), perfects = U.Int(f[6], 0, 0, INT32),
        memoryDrinks = U.Int(f[7], 0, 0, INT32), bestStreak = U.Int(f[8], 0, 0, INT32), fastestMs = U.Int(f[9], nil, 0, INT32),
        weeklyWins = U.Int(f[10], 0, 0, INT32), rewards = U.Int(f[11], 0, 0, 255), last = {}, recvAt = GetTime(),
    }
    for i = 2, math.min(#r, 8) do
        local e = r[i]
        local tag = U.Str(e[1], nil, 1)
        if tag == "W" then
            p.week = {
                weekId = U.Int(e[2], 0, 0, INT32), cafeId = U.Int(e[3], 0, 0, 255), rank = U.Int(e[4], nil, 1, INT32),
                points = U.Int(e[5], 0, 0, INT32), drinks = U.Int(e[6], 0, 0, INT32), perfectPermille = U.Int(e[7], 0, 0, 1000),
                days = U.Int(e[8], 0, 0, 7), eligible = U.Int(e[9], 0, 0, 1),
            }
        elseif tag == "L" then
            local cafeId = cafeIdOf(e[3], 255)
            if cafeId then
                p.last[cafeId] = { weekId = U.Int(e[2], 0, 0, INT32), cafeId = cafeId, winnerName = U.Str(e[4], nil, CAFE_NAME),
                    points = U.Int(e[5], 0, 0, INT32) }
            end
        end
    end
    S.cafeProfile = p
    changed("CAFP")
end)

Comm.Handle("CAFBF", function(r)
    local f = r[1]
    local function timer(raw)
        local v = U.Int(raw, nil, 0, CAFE_SEC)
        return v and v > 0 and v or nil
    end
    local b = { coffeeSec = timer(f[1]), teaSec = timer(f[2]), shakeSec = timer(f[3]), shakeActive = U.Int(f[4], 0, 0, 1),
        coffeeCounts = U.Int(f[5], 1, 0, 1), recvAt = GetTime() }
    S.cafeBuffs = (b.coffeeSec or b.teaSec or b.shakeSec) and b or nil
    changed("CAFBF")
end)

Comm.Handle("CAFSUM", function(r)
    local f = r[1]
    local sum = {
        cafeId = U.Int(f[1], 0, 0, 255), reason = cafeLetter(f[2], CAFE_END_REASONS, "E"), shiftSec = U.Int(f[3], 0, 0, CAFE_SEC),
        drinks = U.Int(f[4], 0, 0, INT32), perfects = U.Int(f[5], 0, 0, INT32), tipsCopper = U.Int(f[6], 0, 0, INT32),
        xp = U.Int(f[7], 0, 0, INT32), xpLost = U.Int(f[8], 0, 0, INT32), points = U.Int(f[9], 0, 0, INT32),
        bestStreak = U.Int(f[10], 0, 0, INT32), staffDrink = U.Int(f[11], 0, 0, 1), recvAt = GetTime(),
    }
    S.cafeSummary = sum
    changed("CAFSUM")
    ns.Fire("CAFE_SUMMARY", sum)
end)

Comm.Handle("CAFUI", function(r)
    local f = r[1]
    local what = U.Str(f[1], nil, 8)
    if what and CAFE_WINDOWS[what] then
        changed("CAFUI")
        ns.Fire("CAFE_UI", what, cafeIdOf(f[2], 255))
    end
end)

Comm.Handle("CAFAT", function(r)
    local f = r[1]
    local id = cafeIdOf(f[1], 255)
    if not id then
        return
    end
    local a = { cafeId = id, count = U.Int(f[2], 0, 0, 255), rows = {}, recvAt = GetTime() }
    for i = 2, math.min(#r, 1 + 4 * CAFE_AT_ROWS) do
        local e = r[i]
        local name = U.Str(e[1], nil, CAFE_NAME)
        if name and #a.rows < CAFE_AT_ROWS then
            a.rows[#a.rows + 1] = {
                name = name, actionId = cafeIdOf(e[2], 63), startedAgoMs = U.Int(e[3], 0, 0, CAFE_MS),
                durMs = U.Int(e[4], 0, 0, 60000), kind = cafeLetter(e[5], CAFE_AT_KINDS, "T"),
                stepIndex = U.Int(e[6], nil, 1, CAFE_STEPS), stepCount = U.Int(e[7], nil, 1, CAFE_STEPS),
            }
        end
    end
    S.cafeAtBar[id] = a
    changed("CAFAT")
end)

-- The records as they came too (S.cafeRaw[op], and S.cafeRaw.DEF[kind] for H G F U): what the module's own Lua tests
-- (Server/mod-bleakhold-ui/tests/lua/test_server_frames.lua) read back until they move to the parsed state above.
for op in pairs(CAFE_OPS) do
    local parse = Comm.handlers[op]
    Comm.Handle(op, function(r, ...)
        S.cafeRaw[op] = r
        return parse(r, ...)
    end)
end
do
    local parseDef = Comm.handlers.DEF
    local RAW_DEF = { H = true, G = true, F = true, U = true }
    Comm.Handle("DEF", function(r, ...)
        local kind = U.Str(r[1] and r[1][1], nil, 1)
        if kind and RAW_DEF[kind] then
            S.cafeRaw.DEF = S.cafeRaw.DEF or {}
            S.cafeRaw.DEF[kind] = r
        end
        return parseDef(r, ...)
    end)
end

-- Every café state gone (a HELLO without bit 131072): the café's frames read it as off.
function ns.ClearCafeState()
    local had = S.cafeState or S.cafeQueue or S.cafeOrder or S.cafeBuffs or #S.cafeTickets > 0 or next(S.cafes)
        or next(S.cafeAtBar) or next(S.cafeMenu) or S.cafeProfile
    S.cafes, S.cafeState, S.cafeQueue, S.cafeTickets, S.cafeStep, S.cafeResult = {}, nil, nil, {}, nil, nil
    S.cafeMenu, S.cafeOrder, S.cafeProfile, S.cafeBuffs, S.cafeSummary, S.cafeAtBar = {}, nil, nil, nil, nil, {}
    S.cafeRaw = {}
    if not Comm.demo then
        ns.cdb.cafeOnShift = nil
    end
    if had then
        for _, op in ipairs({ "CAFE", "CAFST", "CAFQ", "CAFT", "CAFM", "CAFO", "CAFP", "CAFBF", "CAFAT" }) do
            changed(op)
        end
    end
end

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
-- The sentence for a refusal: the addon's own for the codes in Data.errorTexts (a string, or a function of the
-- error that may return nil), else the server's text. Already safe for a FontString.
function ns.ErrorText(e)
    local t = e and e.code and Data.errorTexts[e.code]
    if type(t) == "function" then
        t = t(e)
    end
    if type(t) == "string" then
        return t
    end
    return e and e.text and U.Safe(e.text) or nil
end

Comm.Handle("ERR", function(r)
    local f = r[1]
    local e = { op = U.Str(f[1], nil, 8), seq = U.Str(f[2], nil, 8), code = U.Str(f[3], nil, 24), text = U.Str(f[4], nil, 160), at = GetTime() }
    e.shown = ns.ErrorText(e)
    S.err = e
    ns.Fire("ERR", e)
    if e.shown and UIErrorsFrame then
        UIErrorsFrame:AddMessage(e.shown, 1, 0.45, 0.4)
    end
end)

------------------------------------------------------------------------------------------------------
-- Cases (section 15): which items are cases, what a case holds, and what opening one gave
------------------------------------------------------------------------------------------------------
S.cases = {}        -- [caseItemId] = true
S.caseDefs = {}     -- [caseItemId] = { id, title, text, keyItem, keyCount, rewards = { { itemId, count, chance, tier } } }

Comm.Handle("CASES", function(r)
    -- a new list (the server reloaded its cases): the cached contents may be stale too
    S.caseDefs = {}
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
            c.rewards[#c.rewards + 1] = { itemId = item, count = U.Int(g[2], 1, 1, 65535), chance = U.Int(g[3], 0, 0, 10000),
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
        count = U.Int(f[4], 1, 1, 65535), nonce = U.Int(f[5], nil, 0, INT32) }
    if e.caseItemId and e.index and e.itemId then
        ns.Fire("UNBOX", e)
    end
end)

------------------------------------------------------------------------------------------------------
-- Camping (CAMPST): the campfire the player is at, the camp objects, the warmth and food XP bonus, glide and
-- field repair. A full state, not revisioned; its timers (seconds left when it arrived) count down here
-- between messages: ns.CampLeft.
------------------------------------------------------------------------------------------------------
local CAMP_STATES = { N = true, R = true, C = true }
local CAMP_MAX_OBJECTS = 8      -- the server sends at most 8 (a fire holds 3)
local CAMP_MAX_TIME = 864000

Comm.MapOpToTopic("CAMPST", "CAMPST")
Comm.Handle("CAMPST", function(r)
    local f = r[1]
    local state = U.Str(f[1], "N", 1)
    if not CAMP_STATES[state] then
        state = "N"
    end
    local c = {
        state = state, settle = state == "R" and U.Int(f[2], 0, 0, CAMP_MAX_TIME) or 0, fire = U.Int(f[3], 0, 0, CAMP_MAX_TIME),
        mine = U.Bool(f[4], false), cd = U.Int(f[5], 0, 0, CAMP_MAX_TIME), warmth = U.Int(f[6], 0, 0, CAMP_MAX_TIME),
        xp = U.Int(f[7], 0, 0, 1000), objs = {}, place = {}, glide = U.Int(f[10], nil, 0, CAMP_MAX_TIME),
        repair = U.Bool(f[11], false), fed = U.Bool(f[12], false), gliding = U.Int(f[13], 0, 0, 600), recvAt = GetTime(),
    }
    for _, item in ipairs(U.List(f[8], CAMP_MAX_OBJECTS)) do
        local t = U.Tuple(item, 3)
        local skill = U.Int(t[1], nil, 1, INT32)
        if skill then
            c.objs[#c.objs + 1] = { skill = skill, tier = U.Int(t[2], 1, 1, 3), mine = U.Bool(t[3], false) }
        end
    end
    local seen = {}
    for _, item in ipairs(U.List(f[9], 16)) do
        local t = U.Tuple(item, 2)
        local skill = U.Int(t[1], nil, 1, INT32)
        if skill and not seen[skill] then
            seen[skill] = true
            c.place[#c.place + 1] = { skill = skill, tier = U.Int(t[2], 1, 1, 3) }
        end
    end
    -- settled just now (not the first state after logging in or a reload, which may already be C)
    local before = S.camp and S.camp.state
    S.camp = c
    if state == "C" and before and before ~= "C" then
        ns.Fire("CAMP_SETTLED", c)
    end
    changed("CAMPST")
end)

-- Seconds left on a CAMPST timer (settle, fire, cd, warmth, glide, gliding) now; nil when the field is missing
-- (glide: the player cannot glide) or there is no camp state.
function ns.CampLeft(key, c)
    c = c or S.camp
    local v = c and c[key]
    if type(v) ~= "number" then
        return nil
    end
    return max(0, v - (GetTime() - (c.recvAt or GetTime())))
end

------------------------------------------------------------------------------------------------------
-- Bleakhold Royale (section 17): ROYS ROYM ROYO ROYK ROYV ROYE, unrevisioned full states and events. Positions are
-- integer world yards; times (phaseMsLeft, shrinkStartMs, shrinkEndMs, msLeft) count from the moment the message
-- arrived (recvAt) and ns.RoyaleLeft counts them down. Another matchId in ROYS is another match: the last one's
-- objects, kill feed and events are forgotten (its result stays for the Activities card).
------------------------------------------------------------------------------------------------------
local ROYALE_POS = 100000         -- |x| <= 17067 on any map; anything wilder is clamped, never trusted for maths
local ROYALE_MS = 86400000
local ROYALE_NAME = 48            -- character names (two-word names fit)
local ROYALE_PLACE = 40           -- names of places
local ROYALE_FEED = 20            -- kill feed lines kept
local ROYALE_POI_KINDS = { L = true, C = true, Y = true }
-- ROYO: orbs (S, B), supply drops (D), the storm beast (X) and the hoard it leaves (H). A subtype only where the kind
-- has one, clamped: the buff of a B, the beast's health in percent; 0 for the rest.
local ROYALE_OBJECT_KINDS = { S = true, B = true, D = true, X = true, H = true }
local ROYALE_SUBTYPE_MAX = { B = 3, X = 100 }
-- ROYK: a player, the storm, a fall, left, away, the storm beast; a cause this client does not know shows as P
local ROYALE_CAUSES = { P = true, S = true, F = true, L = true, A = true, B = true }
-- ROYV: R S D L O N W, and the storm beast's B (stirs), A (awake), K (slain), F (fled); others are ignored
local ROYALE_EVENTS = {
    R = true, S = true, D = true, L = true, O = true, N = true, W = true, B = true, A = true, K = true, F = true,
}
ns.ROYALE_MAX_OBJECTS = 64
ns.ROYALE_MAX_STAGES = 16         -- the server's Storm.Stages takes 1..16; ROYS `stages` (empty: six)

local function royalePos(raw, default)
    return U.Int(raw, default, -ROYALE_POS, ROYALE_POS)
end

-- An enum sent as a number: nil unless it is one of 0..maxValue (a future value is not clamped into another one).
local function royaleEnum(raw, maxValue)
    local v = U.Int(raw, nil)
    if v and v >= 0 and v <= maxValue then
        return v
    end
    return nil
end

local function royaleMs(raw)
    return U.Int(raw, nil, 0, ROYALE_MS)
end

-- Seconds left of a time in ms that counted from recvAt (a ROYS, ROYO or ROYV time); nil for an empty field.
function ns.RoyaleLeft(ms, recvAt)
    if type(ms) ~= "number" then
        return nil
    end
    return max(0, ms / 1000 - (GetTime() - (recvAt or GetTime())))
end

-- "70 Honor - Placement": the amount from the reward kind, the server's text as the reason.
function ns.RoyaleRewardText(rw)
    local base = ns.RewardText(rw.kind, rw.amount, rw.itemId, nil)
    if rw.text and rw.text ~= "" then
        return base .. " - " .. rw.text
    end
    return base
end

Comm.MapOpToTopic("ROYS", "ROYS")
Comm.Handle("ROYS", function(r)
    local f = r[1]
    local matchId = U.Int(f[1], nil, 0, INT32)
    if not matchId then
        return
    end
    local old = S.royale
    local same = old and old.matchId == matchId
    local m = {
        matchId = matchId, phase = royaleEnum(f[2], 7) or (same and old.phase) or 0, phaseMsLeft = royaleMs(f[3]) or 0,
        alive = U.Int(f[4], 0, 0, 9999), total = U.Int(f[5], 0, 0, 9999),
        me = royaleEnum(f[6], 5) or (same and old.me) or 0,
        kills = U.Int(f[7], 0, 0, 9999), placement = U.Int(f[8], nil, 1, 9999), pinX = royalePos(f[9]),
        pinY = royalePos(f[10]),
        stage = U.Int(f[11], 0, 0, 99), curX = royalePos(f[12], 0), curY = royalePos(f[13], 0),
        curR = U.Int(f[14], 0, 0, ROYALE_POS),
        nextX = royalePos(f[15]), nextY = royalePos(f[16]), nextR = U.Int(f[17], nil, 0, ROYALE_POS),
        shrinkStartMs = royaleMs(f[18]), shrinkEndMs = royaleMs(f[19]), dmgPermille = U.Int(f[20], 0, 0, 1000000),
        watchName = U.Str(f[21], nil, ROYALE_NAME), myX = royalePos(f[22]), myY = royalePos(f[23]),
        stages = U.Int(f[24], nil, 1, ns.ROYALE_MAX_STAGES),
        fallMsLeft = royaleMs(f[25]), landMsLeft = royaleMs(f[26]), fallMs = royaleMs(f[27]), recvAt = GetTime(),
    }
    -- a pair or nothing
    if not (m.pinX and m.pinY) then
        m.pinX, m.pinY = nil, nil
    end
    if not (m.nextX and m.nextY and m.nextR) then
        m.nextX, m.nextY, m.nextR = nil, nil, nil
    end
    if not (m.myX and m.myY) then
        m.myX, m.myY = nil, nil
    end
    -- the drop's times (fields 25-27): all three while falling (me 1), or none (an older server sends none, and the
    -- drop HUD then goes by the parachute's aura); the planned touchdown never comes before the parachute opens
    if m.me ~= 1 or not (m.fallMsLeft and m.landMsLeft and m.fallMs) then
        m.fallMsLeft, m.landMsLeft, m.fallMs = nil, nil, nil
    elseif m.landMsLeft < m.fallMsLeft then
        m.landMsLeft = m.fallMsLeft
    end
    if not same then
        S.royaleObjects = nil
        S.royaleFeed = {}
        S.royaleKills = {}
        S.royaleEvent = nil
        if S.royaleResult and S.royaleResult.matchId ~= matchId then
            S.royaleResult = nil
        end
    end
    S.royale = m
    if not same then
        ns.Fire("ROYALE_MATCH", m)
    end
    if not same or old.phase ~= m.phase then
        ns.Fire("ROYALE_PHASE", m, same and old.phase or nil)
    end
    if not same or old.me ~= m.me then
        ns.Fire("ROYALE_ME", m, same and old.me or nil)
    end
    changed("ROYS")
end)

Comm.MapOpToTopic("ROYM", "ROYM")
Comm.Handle("ROYM", function(r)
    local f = r[1]
    local m = {
        mapId = U.Int(f[1], nil, 0, INT32), minX = royalePos(f[2]), maxX = royalePos(f[3]), minY = royalePos(f[4]),
        maxY = royalePos(f[5]), lobbyX = royalePos(f[6]), lobbyY = royalePos(f[7]),
        lobbyR = U.Int(f[8], 0, 0, ROYALE_POS),
        boundHalf = U.Int(f[9], nil, 0, ROYALE_POS), centerX = royalePos(f[10]), centerY = royalePos(f[11]), pois = {},
        recvAt = GetTime(),
    }
    -- the map picture's frame: without it nothing can be placed on the map
    if not (m.mapId and m.minX and m.maxX and m.minY and m.maxY and m.minX < m.maxX and m.minY < m.maxY) then
        return
    end
    m.centerX = m.centerX or floor((m.minX + m.maxX) / 2)
    m.centerY = m.centerY or floor((m.minY + m.maxY) / 2)
    if not (m.lobbyX and m.lobbyY) then
        m.lobbyX, m.lobbyY, m.lobbyR = nil, nil, 0
    end
    for i = 2, math.min(#r, 65) do
        local p = r[i]
        local id = U.Int(p[1], nil, 0, INT32)
        local kind = U.Str(p[2], nil, 1)
        if id and kind and ROYALE_POI_KINDS[kind] then
            m.pois[#m.pois + 1] = { id = id, kind = kind, x = royalePos(p[3], 0), y = royalePos(p[4], 0),
                r = U.Int(p[5], 0, 0, ROYALE_POS), name = U.Str(p[6], nil, ROYALE_PLACE) }
        end
    end
    S.royaleMap = m
    changed("ROYM")
end)

local function parseRoyaleObject(o)
    local id = U.Int(o[1], nil, 0, INT32)
    local kind = U.Str(o[2], nil, 2)   -- 2: "XH" is no kind, not "X"
    if not id or not kind or not ROYALE_OBJECT_KINDS[kind] then
        return nil
    end
    local maxSubtype = ROYALE_SUBTYPE_MAX[kind]
    return { id = id, kind = kind, subtype = maxSubtype and U.Int(o[3], 0, 0, maxSubtype) or 0, x = royalePos(o[4], 0),
        y = royalePos(o[5], 0), state = royaleEnum(o[6], 4) or 0, msLeft = royaleMs(o[7]), recvAt = GetTime() }
end

Comm.MapOpToTopic("ROYO", "ROYS")
Comm.Handle("ROYO", function(r)
    local f = r[1]
    local matchId = U.Int(f[1], nil, 0, INT32)
    if not matchId then
        return
    end
    local full = U.Bool(f[2], false)
    local store = S.royaleObjects
    if full or not store or store.matchId ~= matchId then
        if not full then
            -- a change for objects this client never had in full: apply it and ask for the whole list
            Comm.Get("ROYS")
        end
        store = { matchId = matchId, byId = {}, list = {} }
    end
    for i = 2, math.min(#r, ns.ROYALE_MAX_OBJECTS + 1) do
        local o = parseRoyaleObject(r[i])
        if o then
            local known = store.byId[o.id]
            if known then
                for k, v in pairs(o) do
                    known[k] = v
                end
                known.msLeft = o.msLeft
            elseif #store.list < ns.ROYALE_MAX_OBJECTS then
                store.byId[o.id] = o
                store.list[#store.list + 1] = o
            end
        end
    end
    S.royaleObjects = store
    changed("ROYO")
end)

Comm.MapOpToTopic("ROYK", "ROYS")
Comm.Handle("ROYK", function(r)
    local f = r[1]
    local victim = U.Str(f[3], nil, ROYALE_NAME)
    if not victim then
        return
    end
    local cause = U.Str(f[5], "P", 2)   -- 2: "BX" is no cause, not "B"
    local k = {
        killer = U.Str(f[1], nil, ROYALE_NAME), killerClassId = U.Int(f[2], nil, 0, 255), victim = victim,
        victimClassId = U.Int(f[4], 0, 0, 255), cause = ROYALE_CAUSES[cause] and cause or "P",
        aliveAfter = U.Int(f[6], nil, 0, 9999),
        killerKills = U.Int(f[7], nil, 0, 9999), at = GetTime(),
    }
    -- f[8] (`announce`) is superseded by BGANN (section 18) and ignored, so no announcer line plays twice
    if not k.killer then
        k.killerClassId, k.killerKills = nil, nil
    elseif k.cause == "B" and k.killerClassId == 0 then
        -- the storm beast itself (no player has class 0, and a player may be called Thundermaw): no tally of its own
        k.byBoss, k.killerKills = true, nil
    end
    local feed = S.royaleFeed
    feed[#feed + 1] = k
    while #feed > ROYALE_FEED do
        table.remove(feed, 1)
    end
    if k.killer and k.killerKills then
        S.royaleKills[k.killer] = k.killerKills
    end
    if S.royale and k.aliveAfter then
        S.royale.alive = k.aliveAfter
    end
    ns.Fire("ROYALE_KILL", k)
    changed("ROYK")
end)

------------------------------------------------------------------------------------------------------
-- BGANN (section 18): one announced kill of the battleground kill announcer, unrevisioned and never stored. Codes
-- the client does not know are dropped; a message left with neither code, or without both names, is ignored.
------------------------------------------------------------------------------------------------------
local BG_MULTI = { D = true, T = true, U = true, R = true }
local BG_STREAK = { F = true, S = true, O = true, K = true, N = true, W = true, M = true, G = true, H = true }
local BG_NAME = 48

Comm.Handle("BGANN", function(r)
    local f = r[1]
    local multi, streak = U.Str(f[5], nil, 2), U.Str(f[6], nil, 2)   -- 2: "DD" is no code, not "D"
    local a = {
        killer = U.Str(f[1], nil, BG_NAME), killerClassId = U.Int(f[2], 0, 0, 255),
        victim = U.Str(f[3], nil, BG_NAME), victimClassId = U.Int(f[4], 0, 0, 255),
        multi = BG_MULTI[multi or ""] and multi or nil, streak = BG_STREAK[streak or ""] and streak or nil,
        at = GetTime(),
    }
    if not a.killer or not a.victim or not (a.multi or a.streak) then
        return
    end
    S.bgAnnounce = a
    ns.Fire("BG_ANNOUNCE", a)
end)

Comm.MapOpToTopic("ROYV", "ROYS")
Comm.Handle("ROYV", function(r)
    local f = r[1]
    local kind = U.Str(f[1], nil, 2)   -- 2: "BX" is no kind, not "B"
    if not kind or not ROYALE_EVENTS[kind] then
        return
    end
    -- the name is a character's, but the place for the storm beast's B
    local e = { kind = kind, value = U.Int(f[2], 0, 0, INT32), x = royalePos(f[3]), y = royalePos(f[4]),
        msLeft = royaleMs(f[5]), name = U.Str(f[6], nil, kind == "B" and ROYALE_PLACE or ROYALE_NAME),
        recvAt = GetTime() }
    if not (e.x and e.y) then
        e.x, e.y = nil, nil
    end
    S.royaleEvent = e
    ns.Fire("ROYALE_EVENT", e)
    changed("ROYV")
end)

Comm.MapOpToTopic("ROYE", "ROYS")
Comm.Handle("ROYE", function(r)
    local f = r[1]
    local res = {
        matchId = U.Int(f[1], nil, 0, INT32), placement = U.Int(f[2], nil, 1, 9999), total = U.Int(f[3], nil, 0, 9999),
        kills = U.Int(f[4], 0, 0, 9999), damage = U.Int(f[5], 0, 0, INT32), healing = U.Int(f[6], 0, 0, INT32),
        survivedSec = U.Int(f[7], 0, 0, 864000), winnerName = U.Str(f[8], nil, ROYALE_NAME),
        winnerClassId = U.Int(f[9], nil, 0, 255),
        winnerKills = U.Int(f[10], nil, 0, 9999), rewarded = U.Bool(f[11], false), rewards = {}, recvAt = GetTime(),
    }
    if not res.matchId then
        return
    end
    if res.rewarded then
        for i = 2, math.min(#r, 21) do
            local rw = r[i]
            local e = { kind = U.Str(rw[1], "T", 1), amount = U.Int(rw[2], 0, 0, INT32),
                itemId = U.Int(rw[3], nil, 1, INT32), text = U.Str(rw[4], nil, 60) }
            e.line = ns.RoyaleRewardText(e)
            res.rewards[#res.rewards + 1] = e
        end
    end
    local first = not (S.royaleResult and S.royaleResult.matchId == res.matchId)
    S.royaleResult = res
    ns.Fire("ROYALE_RESULT", res, first)
    changed("ROYE")
end)

------------------------------------------------------------------------------------------------------
-- World PvP and War Mode (section 19): WMST WPZ WPCAP WPMAP WANTED WPEV, unrevisioned full states and events. Times
-- (cooldownSec, wantedSec, secondsLeft, nextStartsSec, ...) count from the moment the message arrived (recvAt);
-- ns.WarLeft counts them down. Factions are letters (A, H; N for objectives only), an empty field is nobody;
-- positions u, v are permille of the zone's world map, a pair or nothing. Letters and states the client does not
-- know are not clamped into known ones: an unknown objective state reads as neutral, an unknown zone kind as none.
------------------------------------------------------------------------------------------------------
local WAR_NAME = 48               -- character names
local WAR_PLACE = 40              -- objective and zone names
local WAR_TIME = 864000           -- 10 days: any longer time is clamped
local WAR_BIG = 999999            -- counts (players, kills, streaks)
local WAR_TEAMS = { A = true, H = true }
local WAR_OWNERS = { A = true, H = true, N = true }
local WAR_ZONE_KINDS = { F = true, L = true, S = true, W = true }
local WAR_EVENTS = { C = true, N = true, A = true, F = true, E = true, X = true, W = true, B = true, S = true,
    R = true }
local WAR_WHY = { K = true, C = true, H = true, B = true, S = true, V = true }
local WAR_REASONS = { S = true, B = true }
local WAR_TAG_O, WAR_TAG_W, WAR_TAG_ZP = { O = true }, { W = true }, { Z = true, P = true }
-- the owner an objective state means (AzerothCore's ObjectiveStates: 1 the Alliance's, 2 the Horde's; 3 to 6 are in the
-- neutral band, 5 and 6 on the side of the faction that held it last)
local WAR_STATE_OWNER = { [0] = "N", [1] = "A", [2] = "H", [3] = "N", [4] = "N", [5] = "N", [6] = "N" }
ns.WAR_MAX_OBJECTIVES = 16
ns.WAR_MAX_ZONES = 32
ns.WAR_MAX_POINTS = 96
ns.WAR_MAX_WANTED = 8
ns.WAR_STATE_OWNER = WAR_STATE_OWNER

-- A one-letter field from a set (2 bytes read: "AH" is no letter, not "A"), or nil.
local function warLetter(raw, set)
    local v = U.Str(raw, nil, 2)
    if v and set[v] then
        return v
    end
    return nil
end

local function warPermille(raw)
    return U.Int(raw, nil, 0, 1000)
end

-- A pair of permille map positions, or nothing.
local function warPos(rawU, rawV)
    local u, v = warPermille(rawU), warPermille(rawV)
    if u and v then
        return u, v
    end
    return nil, nil
end

local function warTime(raw)
    return U.Int(raw, 0, 0, WAR_TIME)
end

-- Seconds left of a section 19 time that counted from recvAt; 0 once it ran out, nil for a missing one.
function ns.WarLeft(sec, recvAt)
    if type(sec) ~= "number" then
        return nil
    end
    return max(0, sec - (GetTime() - (recvAt or GetTime())))
end

-- The name of a zone: what WPEV F or X said, the built-in list, the client's own name for the zone the player is in
-- (WPZ is always that zone), else "Zone <id>".
function ns.WarZoneName(zoneId)
    if not zoneId then
        return "Unknown zone"
    end
    local n = S.warZoneNames[zoneId] or Data.warZones[zoneId]
    if n then
        return n
    end
    if S.wpZone and S.wpZone.zoneId == zoneId and GetRealZoneText then
        local z = GetRealZoneText()
        if type(z) == "string" and z ~= "" then
            return U.CutUtf8(U.CleanUtf8(z), WAR_PLACE)
        end
    end
    return "Zone " .. zoneId
end

-- The name of an objective (WPZ, WPEV C N A), else "Outpost <id>".
function ns.WarObjectiveName(zoneId, objId)
    return S.warObjNames[tostring(zoneId) .. ":" .. tostring(objId)] or ("Outpost " .. tostring(objId))
end

local function rememberObjective(zoneId, objId, name)
    if zoneId and objId and name then
        S.warObjNames[tostring(zoneId) .. ":" .. tostring(objId)] = name
    end
end

Comm.MapOpToTopic("WMST", "WMST")
Comm.Handle("WMST", function(r)
    local f = r[1]
    local on = U.Bool(f[1], nil)
    if on == nil then
        return    -- without its first field the message says nothing
    end
    local block = U.Str(f[3], nil, 24)
    if block and not block:find("^[%w_]+$") then
        block = nil
    end
    local wanted = U.Int(f[13], nil)
    local wm = {
        on = on, cooldownSec = warTime(f[2]), block = block, minLevel = U.Int(f[4], nil, 1, 255),
        xpPct = U.Int(f[5], 0, 0, 1000), honorPct = U.Int(f[6], 0, 0, 1000), shardPct = U.Int(f[7], 0, 0, 1000),
        underdogPct = U.Int(f[8], 0, 0, 1000), underdogTeam = warLetter(f[9], WAR_TEAMS),
        wmAlliance = U.Int(f[10], 0, 0, WAR_BIG), wmHorde = U.Int(f[11], 0, 0, WAR_BIG),
        streak = U.Int(f[12], 0, 0, WAR_BIG), wantedState = (wanted and wanted >= 0 and wanted <= 2) and wanted or 0,
        wantedSec = warTime(f[14]), bountyHonor = U.Int(f[15], 0, 0, INT32),
        todayBonusHonor = U.Int(f[16], 0, 0, INT32), bonusHonorCap = U.Int(f[17], 0, 0, INT32),
        todayShards = U.Int(f[18], 0, 0, INT32), shardsCap = U.Int(f[19], 0, 0, INT32),
        bestStreak = U.Int(f[20], 0, 0, WAR_BIG), kills = U.Int(f[21], 0, 0, INT32), deaths = U.Int(f[22], 0, 0, INT32),
        recvAt = GetTime(),
    }
    if wm.underdogPct == 0 then
        wm.underdogTeam = nil
    end
    local old = S.warMode
    S.warMode = wm
    if not old or old.on ~= wm.on then
        ns.Fire("WARMODE_CHANGED", wm, old and old.on)
    end
    if (old and old.wantedState or 0) ~= wm.wantedState then
        ns.Fire("WARMODE_WANTED", wm, old and old.wantedState or 0)
    end
    changed("WMST")
end)

Comm.MapOpToTopic("WPZ", "WPZ")
Comm.Handle("WPZ", function(r)
    local f = r[1]
    local zoneId = U.Int(f[1], nil, 0, INT32)
    if not zoneId then
        return
    end
    local kind = warLetter(f[2], WAR_ZONE_KINDS)
    if kind == "W" then
        kind = nil    -- Wintergrasp is only in WPMAP
    end
    local z = { zoneId = zoneId, kind = kind, objectives = {}, byId = {}, recvAt = GetTime() }
    if kind then
        local state = U.Int(f[3], nil)
        z.state = (state and state >= 0 and state <= 2) and state or 0
        z.secondsLeft = warTime(f[4])
        z.controlA, z.controlH = warPermille(f[5]), warPermille(f[6])
        z.dominionTeam = warLetter(f[7], WAR_TEAMS)
        z.dominionStacks = z.dominionTeam and U.Int(f[8], 0, 0, 9) or 0
        if z.dominionStacks == 0 then
            z.dominionTeam = nil
        end
        z.levelMin, z.levelMax = U.Int(f[9], nil, 0, 255), U.Int(f[10], nil, 0, 255)
        for i = 2, #r do
            local o = r[i]
            if #z.objectives >= ns.WAR_MAX_OBJECTIVES then
                break
            end
            local id = warLetter(o[1], WAR_TAG_O) and U.Int(o[2], nil, 0, INT32)
            if id and not z.byId[id] then
                local st = U.Int(o[8], nil)
                local e = { objId = id, name = U.Str(o[3], nil, WAR_PLACE), owner = warLetter(o[6], WAR_OWNERS) or "N",
                    slider = U.Int(o[7], 0, -1000, 1000), state = (st and WAR_STATE_OWNER[st]) and st or 0 }
                e.u, e.v = warPos(o[4], o[5])
                rememberObjective(zoneId, id, e.name)
                z.byId[id] = e
                z.objectives[#z.objectives + 1] = e
            end
        end
    end
    local old = S.wpZone
    S.wpZone = z
    if not old or old.zoneId ~= zoneId then
        -- another zone: its Wanted players and the bar of the last outpost are gone
        if S.wanted and S.wanted.zoneId ~= zoneId then
            S.wanted = nil
            changed("WANTED")
        end
        if S.wpCap then
            S.wpCap = nil
            changed("WPCAP")
        end
        ns.Fire("WAR_ZONE", z, old)
    end
    changed("WPZ")
end)

Comm.MapOpToTopic("WPCAP", "WPZ")
Comm.Handle("WPCAP", function(r)
    local f = r[1]
    local objId = U.Int(f[1], nil, 0, INT32)
    if not objId then
        return
    end
    if objId == 0 then
        S.wpCap = nil    -- the player left the outpost
        changed("WPCAP")
        return
    end
    local st = U.Int(f[4], nil)
    local cap = { objId = objId, slider = U.Int(f[2], 0, -1000, 1000), neutralPct = U.Int(f[3], 0, 0, 100),
        state = (st and WAR_STATE_OWNER[st]) and st or 0, countA = U.Int(f[5], 0, 0, WAR_BIG),
        countH = U.Int(f[6], 0, 0, WAR_BIG), maxNet = U.Int(f[7], 0, 0, WAR_BIG), recvAt = GetTime() }
    S.wpCap = cap
    -- the outpost's bar in WPZ follows the capture bar between two WPZ
    local o = S.wpZone and S.wpZone.byId[objId]
    if o then
        o.slider, o.state, o.owner = cap.slider, cap.state, WAR_STATE_OWNER[cap.state]
    end
    changed("WPCAP")
end)

Comm.MapOpToTopic("WPMAP", "WPMAP")
Comm.Handle("WPMAP", function(r)
    local f = r[1]
    local function zoneState(raw)
        local v = U.Int(raw, nil)
        return (v and v >= 0 and v <= 2) and v or 0
    end
    local m = {
        frontZone = U.Int(f[1], 0, 0, INT32), frontState = zoneState(f[2]), secondsLeft = warTime(f[3]),
        nextZone = U.Int(f[4], 0, 0, INT32), nextStartsSec = warTime(f[5]), levelZone = U.Int(f[6], 0, 0, INT32),
        levelState = zoneState(f[7]), levelSecondsLeft = warTime(f[8]), zones = {}, zoneById = {}, points = {},
        recvAt = GetTime(),
    }
    for i = 2, #r do
        local e = r[i]
        local tag = warLetter(e[1], WAR_TAG_ZP)
        if tag == "Z" and #m.zones < ns.WAR_MAX_ZONES then
            local id, kind = U.Int(e[2], nil, 0, INT32), warLetter(e[3], WAR_ZONE_KINDS)
            if id and kind and not m.zoneById[id] then
                local z = { zoneId = id, kind = kind, heldA = U.Int(e[4], 0, 0, 999), heldH = U.Int(e[5], 0, 0, 999),
                    neutral = U.Int(e[6], 0, 0, 999), levelMin = U.Int(e[7], nil, 0, 255),
                    levelMax = U.Int(e[8], nil, 0, 255), state = zoneState(e[9]), points = {} }
                m.zoneById[id] = z
                m.zones[#m.zones + 1] = z
            end
        elseif tag == "P" and #m.points < ns.WAR_MAX_POINTS then
            local zid, oid = U.Int(e[2], nil, 0, INT32), U.Int(e[3], nil, 0, INT32)
            if zid and oid then
                local st = U.Int(e[5], nil)
                m.points[#m.points + 1] = { zoneId = zid, objId = oid, owner = warLetter(e[4], WAR_OWNERS) or "N",
                    state = (st and WAR_STATE_OWNER[st]) and st or 0 }
            end
        end
    end
    for _, p in ipairs(m.points) do
        local z = m.zoneById[p.zoneId]
        if z then
            z.points[#z.points + 1] = p
        end
    end
    S.wpMap = m
    changed("WPMAP")
end)

Comm.MapOpToTopic("WANTED", "WANTED")
Comm.Handle("WANTED", function(r)
    local zoneId = U.Int(r[1][1], nil, 0, INT32)
    if not zoneId then
        return
    end
    local w = { zoneId = zoneId, list = {}, recvAt = GetTime() }
    for i = 2, #r do
        local e = r[i]
        if #w.list >= ns.WAR_MAX_WANTED then
            break
        end
        local name = warLetter(e[1], WAR_TAG_W) and U.Str(e[2], nil, WAR_NAME)
        if name then
            local x = { name = name, classId = U.Int(e[3], 0, 0, 255), team = warLetter(e[4], WAR_TEAMS),
                streak = U.Int(e[5], 0, 0, WAR_BIG), reason = warLetter(e[6], WAR_REASONS),
                bountyHonor = U.Int(e[7], 0, 0, INT32), bountyShards = U.Int(e[8], 0, 0, INT32),
                ageSec = warTime(e[11]) }
            x.u, x.v = warPos(e[9], e[10])
            w.list[#w.list + 1] = x
        end
    end
    S.wanted = w
    changed("WANTED")
end)

-- WPEV: one event, never stored but the last (S.warEvent); WAR_EVENT carries it to the banners and toasts.
Comm.Handle("WPEV", function(r)
    local f = r[1]
    local kind = warLetter(f[1], WAR_EVENTS)
    if not kind then
        return
    end
    local e = { kind = kind, at = GetTime() }
    if kind == "C" or kind == "N" or kind == "A" then
        e.zoneId, e.objId = U.Int(f[2], nil, 0, INT32), U.Int(f[3], nil, 0, INT32)
        e.team, e.name = warLetter(f[4], WAR_TEAMS), U.Str(f[5], nil, WAR_PLACE)
        if not (e.zoneId and e.objId) then
            return
        end
        rememberObjective(e.zoneId, e.objId, e.name)
        e.name = e.name or ns.WarObjectiveName(e.zoneId, e.objId)
    elseif kind == "F" or kind == "X" then
        e.zoneId, e.seconds, e.name = U.Int(f[2], nil, 0, INT32), warTime(f[3]), U.Str(f[4], nil, WAR_PLACE)
        if not e.zoneId then
            return
        end
        if e.name then
            S.warZoneNames[e.zoneId] = e.name
        end
        e.name = ns.WarZoneName(e.zoneId)
    elseif kind == "E" then
        e.zoneId, e.winner = U.Int(f[2], nil, 0, INT32), warLetter(f[3], WAR_TEAMS)
        e.controlA, e.controlH = warPermille(f[4]) or 0, warPermille(f[5]) or 0
        if not e.zoneId then
            return
        end
        e.name = ns.WarZoneName(e.zoneId)
    elseif kind == "W" then
        e.name, e.classId = U.Str(f[2], nil, WAR_NAME), U.Int(f[3], 0, 0, 255)
        e.team, e.streak = warLetter(f[4], WAR_TEAMS), U.Int(f[5], 0, 0, WAR_BIG)
        e.reason = warLetter(f[6], WAR_REASONS)
        if not e.name then
            return
        end
    elseif kind == "B" then
        e.killer, e.victim = U.Str(f[2], nil, WAR_NAME), U.Str(f[3], nil, WAR_NAME)
        e.honor, e.shards = U.Int(f[4], 0, 0, INT32), U.Int(f[5], 0, 0, INT32)
        if not (e.killer and e.victim) then
            return
        end
    elseif kind == "S" then
        e.name, e.honor, e.shards = U.Str(f[2], nil, WAR_NAME), U.Int(f[3], 0, 0, INT32), U.Int(f[4], 0, 0, INT32)
        if not e.name then
            return
        end
    else -- R
        e.why = warLetter(f[2], WAR_WHY)
        e.honor, e.xp, e.shards = U.Int(f[3], 0, 0, INT32), U.Int(f[4], 0, 0, INT32), U.Int(f[5], 0, 0, INT32)
        e.drPermille = U.Int(f[6], 1000, 0, 1000)
        if not e.why then
            return
        end
    end
    S.warEvent = e
    ns.Fire("WAR_EVENT", e)
    changed("WPEV")
end)

local TOAST_TARGETS = { tasks = true, dungeons = true, keys = true, rift = true, collections = true, season = true,
    leaderboards = true, royale = true, arena = true, cafe = true }
Comm.Handle("TOAST", function(r)
    local f = r[1]
    local title = U.Str(f[2], nil, 60)
    if not title then
        return
    end
    local target = U.Str(f[4], nil, 16)
    target = TOAST_TARGETS[target or ""] and target or nil
    ns.Fire("TOAST", { kind = U.Str(f[1], "I", 1), title = title, sub = U.Str(f[3], nil, 100), target = target })
end)

------------------------------------------------------------------------------------------------------
-- After the handshake: definitions and the topics the always-visible parts need
------------------------------------------------------------------------------------------------------
ns.On("HELLO", function(s)
    if s.dataVer and s.dataVer > 0
        and (tostring(ns.db.defsVer) ~= tostring(s.dataVer) or ns.db.defsSchema ~= DEF_SCHEMA) then
        ns.db.defs = {}
        ns.db.defsVer = nil
        ns.db.defsSchema = nil
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
    -- the server sends CAMPST after HELLO too; asking makes sure (a realm with all three off has none)
    local F = Comm.FEATURE
    if Comm.HasFeature(F.CAMP) or Comm.HasFeature(F.GLIDE) or Comm.HasFeature(F.FIELD_REPAIR) then
        Comm.Get("CAMPST")
    elseif S.camp then
        S.camp = nil
        changed("CAMPST")
    end
    -- the server pushes ARENA after HELLO while bit 65536 is on (section 20); asking makes sure (the login push
    -- can come before HELLO, and /reload has none). Without the bit the season is gone
    if Comm.HasFeature(F.ARENA) then
        Comm.Get("ARENA")
    elseif S.arena then
        S.arena = nil
        changed("ARENA")
    end
    -- the café (section 21): the server pushes CAFE, CAFBF, CAFST and CAFO after HELLO with bit 131072, and CAFT and
    -- CAFQ while the player is on shift; asking makes sure (the login push can come before HELLO, and /reload has
    -- none: whether a shift ran before it is kept in BleakholdCharDB). Without the bit every café state is gone
    if Comm.HasFeature(F.CAFE) then
        Comm.Get("CAFE")
        Comm.Get("CAFST")
        Comm.Get("CAFBF")
        Comm.Get("CAFO")
        if (S.cafeState and S.cafeState.onShift) or (not Comm.demo and ns.cdb.cafeOnShift) then
            Comm.Get("CAFT")
            Comm.Get("CAFQ")
        end
    else
        ns.ClearCafeState()
    end
end)
