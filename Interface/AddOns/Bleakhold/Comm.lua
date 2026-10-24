-- Bleakhold: protocol v1 transport (docs/BleakholdProtocol.md).
--
-- Client -> server: SendAddonMessage("BHc", body, "WHISPER", <own name>). Only INTENTS are sent: what
-- the player asked for (open a board, join a queue, start a key, claim a task...), never a result,
-- score, reward, loot or state. The server decides everything and must validate every message.
-- Server -> client: an addon whisper from the player to the player with prefix "BHs".
--
-- Frame: VER SP OP SP SEQ SP PART/TOTAL [SP PAYLOAD]
-- Payload: records ';', fields ',', list items ':', tuple parts '~'; those bytes, '%', '|' and control
-- bytes are escaped as %XX.
local ADDON, ns = ...
local U = ns.U

local type, pairs, ipairs, tostring, tonumber = type, pairs, ipairs, tostring, tonumber
local floor = math.floor
local strfind, strsub, strgsub, strformat, strbyte = string.find, string.sub, string.gsub, string.format, string.byte
local tconcat = table.concat

local Comm = {}
ns.Comm = Comm

Comm.PREFIX_OUT = "BHc"
Comm.PREFIX_IN = "BHs"
Comm.MAX_OUT_BODY = 251          -- AzerothCore drops client chat over 255 bytes: "BHc" + tab + body
Comm.MAX_IN_BODY = 1000          -- server frames above this are dropped (client chat buffers are 3000 bytes)
Comm.MAX_PARTS = 99
Comm.MAX_ASSEMBLED = 64 * 1024   -- a reassembled payload is never larger than this
Comm.MAX_BUFFERS = 16            -- chunk buffers kept at once (one per OP)
Comm.CHUNK_TIMEOUT = 5           -- seconds from the first part until an incomplete message is dropped
Comm.BURST = 6                   -- send throttle: bucket size ...
Comm.RATE = 4                    -- ... refilled at this many messages per second
Comm.QUEUE_MAX = 24              -- intents waiting for the throttle
Comm.DEDUP = 0.5                 -- identical intents within this many seconds are sent once
Comm.GET_COOLDOWN = 3            -- a topic is requested again at most this often
Comm.MAX_GET_RECORDS = 8
Comm.HELLO_RETRY = { 10, 30, 90 }

local SEQ_MOD = 36 ^ 6
local B36 = "0123456789abcdefghijklmnopqrstuvwxyz"

------------------------------------------------------------------------------------------------------
-- Escaping
------------------------------------------------------------------------------------------------------
local function escByte(c)
    return strformat("%%%02X", strbyte(c))
end

-- Escape a value for a payload field (numbers become decimal text).
function Comm.Escape(v)
    if v == nil then
        return ""
    end
    if type(v) == "boolean" then
        return v and "1" or "0"
    end
    local s = tostring(v)
    return (strgsub(s, "[%%;,:~|%c]", escByte))
end

Comm.Unescape = U.Unescape

------------------------------------------------------------------------------------------------------
-- Sequence numbers (base 36, 1-6 digits, per direction)
------------------------------------------------------------------------------------------------------
function Comm.Base36(n)
    n = floor(n) % SEQ_MOD
    if n == 0 then
        return "0"
    end
    local t = {}
    while n > 0 do
        local d = n % 36
        t[#t + 1] = strsub(B36, d + 1, d + 1)
        n = floor(n / 36)
    end
    local out = {}
    for i = #t, 1, -1 do
        out[#out + 1] = t[i]
    end
    return tconcat(out)
end

-- true if sequence a comes after b (with wrap-around)
function Comm.SeqNewer(a, b)
    local d = (a - b) % SEQ_MOD
    return d > 0 and d < SEQ_MOD / 2
end

------------------------------------------------------------------------------------------------------
-- Frames
------------------------------------------------------------------------------------------------------
-- Parse a frame body. Returns a table or nil, reason.
function Comm.ParseFrame(body)
    if type(body) ~= "string" then
        return nil, "type"
    end
    if #body > Comm.MAX_IN_BODY then
        return nil, "oversize"
    end
    local ver, op, seq, part, total, rest = body:match("^(%d+) (%u+) (%w+) (%d+)/(%d+)(.*)$")
    if not ver then
        return nil, "header"
    end
    if #op < 2 or #op > 6 or #seq > 6 or #ver > 3 or #part > 2 or #total > 2 then
        return nil, "header"
    end
    local payload
    if rest == "" then
        payload = ""
    elseif strsub(rest, 1, 1) == " " then
        payload = strsub(rest, 2)
    else
        return nil, "header"
    end
    if strfind(payload, "\0", 1, true) then
        return nil, "nul"
    end
    part, total = tonumber(part), tonumber(total)
    if part < 1 or total < 1 or total > Comm.MAX_PARTS or part > total then
        return nil, "part"
    end
    return { ver = tonumber(ver), op = op, seq = tonumber(seq, 36), part = part, total = total, payload = payload }
end

-- Split a raw payload into records of raw fields. Empty records are skipped.
function Comm.SplitRecords(payload, maxRecords, maxFields)
    local records = {}
    if type(payload) ~= "string" or payload == "" then
        return records
    end
    maxRecords = maxRecords or 500
    maxFields = maxFields or 40
    local start, n = 1, #payload
    while start <= n + 1 and #records < maxRecords do
        local e = strfind(payload, ";", start, true)
        local rec = strsub(payload, start, (e or n + 1) - 1)
        if rec ~= "" then
            local fields, fs = {}, 1
            while #fields < maxFields do
                local c = strfind(rec, ",", fs, true)
                if c then
                    fields[#fields + 1] = strsub(rec, fs, c - 1)
                    fs = c + 1
                else
                    fields[#fields + 1] = strsub(rec, fs)
                    break
                end
            end
            records[#records + 1] = fields
        end
        if not e then
            break
        end
        start = e + 1
    end
    return records
end

local function isCont(b)
    return b and b >= 0x80 and b < 0xC0
end

-- Split a server payload into frames of at most maxBody bytes (the server does the same; the demo and
-- the tests use this). Cuts after a record separator when one is near, never inside %XX or a UTF-8
-- sequence.
function Comm.BuildFrames(op, seq, payload, maxBody)
    maxBody = maxBody or Comm.MAX_IN_BODY
    payload = payload or ""
    local seqStr = Comm.Base36(seq)
    local room = maxBody - #("1 " .. op .. " " .. seqStr .. " 99/99 ")
    if room < 8 then
        return nil, "room"
    end
    local parts, i, n = {}, 1, #payload
    while i <= n do
        local j = i + room - 1
        if j >= n then
            parts[#parts + 1] = strsub(payload, i)
            break
        end
        local cut
        for k = j, i + floor(room / 2), -1 do
            if strbyte(payload, k) == 59 then -- ';'
                cut = k
                break
            end
        end
        if not cut then
            cut = j
            if strbyte(payload, cut) == 37 then
                cut = cut - 1
            elseif strbyte(payload, cut - 1) == 37 then
                cut = cut - 2
            end
            while cut > i and isCont(strbyte(payload, cut + 1)) do
                cut = cut - 1
            end
            -- cut now ends on a lead byte of the sequence that follows? keep the whole sequence out
            local b = strbyte(payload, cut)
            if b and b >= 0xC0 then
                cut = cut - 1
            end
        end
        parts[#parts + 1] = strsub(payload, i, cut)
        i = cut + 1
    end
    if #parts == 0 then
        parts[1] = ""
    end
    if #parts > Comm.MAX_PARTS then
        return nil, "parts"
    end
    local frames = {}
    for p = 1, #parts do
        local body = "1 " .. op .. " " .. seqStr .. " " .. p .. "/" .. #parts
        if parts[p] ~= "" then
            body = body .. " " .. parts[p]
        end
        frames[p] = body
    end
    return frames
end

------------------------------------------------------------------------------------------------------
-- Intents (client -> server). Every field is an integer, an enum or a short token: the client never
-- sends free text, results or state.
------------------------------------------------------------------------------------------------------
local INT32 = 2147483647
local function int(lo, hi) return { kind = "int", lo = lo, hi = hi } end
local function enum(...) local t = {} for i = 1, select("#", ...) do t[select(i, ...)] = true end return { kind = "enum", values = t } end
local function token(maxLen) return { kind = "token", max = maxLen } end

Comm.TOPICS = {
    WEEK = 0, ERA = 0, TASKS = 0, KEY = 0, BOARD = 0, QUEUE = 0, MPLUS = 0, RIFT = 0, COLL = 0,
    SET = 2, LIDX = 0, SEASON = 0, FIRSTS = 0, DEF = 1, CASES = 0, CASE = 1, CAMPST = 0,
}

-- A schema lists its fields in order; `min` (default: all of them) is how many must be given, the rest may be
-- left off the end, and `check(...)` is called with the given values when they must agree with each other.
Comm.INTENTS = {
    HELLO = { int(1, 99), token(16), int(0, INT32), token(8) },       -- proto, addonVer, dataVer, locale
    GET = "records",                                                  -- topic[,args] per record
    TCLAIM = { int(1, INT32) },                                       -- task uid (from TASKS)
    TREROLL = { int(1, INT32) },                                      -- task uid
    QJOIN = { enum("D", "R"), int(0, INT32), int(0, 3), int(1, 7), int(1, 5) }, -- kind, activity, tier (0 Normal .. 3 Nightmare), roles, size
    QLEAVE = {},
    QREPLY = { int(1, INT32), int(0, 1) },                            -- proposal id, accept
    KMODE = { int(0, 2) },                                            -- 0 normal, 1 heroic, 2 mythic
    KSTART = {},
    KCANCEL = {},
    BCLAIM = { int(1, INT32) },                                       -- bounty id (from BOARD)
    WEHANDIN = {},
    OUTFIT = { int(1, INT32) },                                       -- legacy set id (from SET)
    LBQ = { enum("K", "R", "E", "F"), int(0, INT32), int(0, INT32), int(0, INT32), int(1, 999) },
    PING = { int(0, INT32) },
    EMOJI = { int(0, 255) },                                          -- emoji id (the server checks its catalogue)
    DANCE = { int(0, 1023) },                                         -- dance id (the server checks its catalogue)
    CASEOPEN = { int(1, INT32), int(0, INT32) },                      -- case item id (from CASES), nonce (back in UNBOX)
    -- M make camp, O place a camp object (skill line id from CAMPST place, only with O), P pack up my camp
    CAMP = { enum("M", "O", "P"), int(1, INT32), min = 1, check = function(act, skill) return (act == "O") == (skill ~= nil) end },
    GLIDE = {},
    REPAIR = {},
}

local function checkField(spec, v)
    if spec.kind == "int" then
        if type(v) == "boolean" then
            v = v and 1 or 0
        end
        v = tonumber(v)
        if not v or v ~= v or v ~= floor(v) or v < spec.lo or v > spec.hi then
            return nil
        end
        return tostring(v)
    elseif spec.kind == "enum" then
        if type(v) == "string" and spec.values[v] then
            return v
        end
        return nil
    elseif spec.kind == "token" then
        if type(v) == "number" then
            v = tostring(v)
        end
        if type(v) ~= "string" or #v < 1 or #v > spec.max or not strfind(v, "^[%w_%.%-]+$") then
            return nil
        end
        return v
    end
    return nil
end

-- Encode an intent payload. Returns payload or nil, reason.
function Comm.EncodeIntent(op, ...)
    local schema = Comm.INTENTS[op]
    if not schema then
        return nil, "not an intent"
    end
    if schema == "records" then
        local recs = {}
        for i = 1, select("#", ...) do
            local r = select(i, ...)
            if type(r) ~= "table" then
                return nil, "record"
            end
            local topic = r[1]
            local nargs = Comm.TOPICS[topic]
            if not nargs or #r - 1 > nargs then
                return nil, "topic"
            end
            local fields = { topic }
            for k = 2, #r do
                local f = checkField(int(0, INT32), r[k])
                if not f then
                    return nil, "arg"
                end
                fields[k] = f
            end
            recs[#recs + 1] = tconcat(fields, ",")
        end
        if #recs == 0 or #recs > Comm.MAX_GET_RECORDS then
            return nil, "records"
        end
        return tconcat(recs, ";")
    end
    local n = select("#", ...)
    if n < (schema.min or #schema) or n > #schema then
        return nil, "fields"
    end
    local fields = {}
    for i = 1, n do
        local f = checkField(schema[i], (select(i, ...)))
        if not f then
            return nil, "field " .. i
        end
        fields[i] = f
    end
    if schema.check and not schema.check(...) then
        return nil, "fields"
    end
    return tconcat(fields, ",")
end

------------------------------------------------------------------------------------------------------
-- State
------------------------------------------------------------------------------------------------------
Comm.stats = { framesIn = 0, dropped = {}, sent = 0, refused = 0, gaps = 0, timeouts = 0, dups = 0, unknown = 0, foreign = 0 }
Comm.log = {}
Comm.handlers = {}
Comm.topicRev = {}
Comm.ready = false        -- server answered HELLO
Comm.blocked = false      -- protocol too old: send nothing more
Comm.canSend = false      -- player is in the world (SendAddonMessage needs it)
Comm.clockOffset = 0

local outSeq = 0
local queue = {}
local tokens = Comm.BURST
local lastRefill = nil
local recent = {}         -- body -> time, for de-duplication
local buffers = {}        -- op -> chunk buffer
local lastDone = {}       -- op -> seq of the last reassembled message
local topicOf = {}        -- op -> { topic, snapshot = bool }
local lastGet = {}        -- topic key -> time
local pendingGets = {}
local helloTries = 0
local helloTimer
local deferred = {}       -- GETs asked for before the server answered HELLO

local function drop(reason)
    local d = Comm.stats.dropped
    d[reason] = (d[reason] or 0) + 1
end

local function addLog(dir, body)
    local log = Comm.log
    log[#log + 1] = { t = GetTime(), dir = dir, body = body }
    if #log > 60 then
        table.remove(log, 1)
    end
end

-- Register a snapshot topic: snapshotOp replaces it, deltaOps update it; the first field of the
-- first record of all of them is the revision.
function Comm.RegisterTopic(topic, snapshotOp, deltaOps)
    topicOf[snapshotOp] = { topic = topic, snapshot = true }
    for _, op in ipairs(deltaOps or {}) do
        topicOf[op] = { topic = topic, snapshot = false }
    end
end

-- Topic that an op belongs to (used to re-request after a lost chunk).
local opTopic = {}
function Comm.MapOpToTopic(op, topic)
    opTopic[op] = topic
end

function Comm.Handle(op, fn)
    Comm.handlers[op] = fn
end

------------------------------------------------------------------------------------------------------
-- Sending
------------------------------------------------------------------------------------------------------
local function rawSend(body)
    Comm.stats.sent = Comm.stats.sent + 1
    addLog(">", body)
    if Comm.demo then
        local fr = Comm.ParseFrameOut(body)
        if fr then
            ns.After(0.05, function()
                Comm.demo(fr.op, fr.payload, fr.seq)
            end)
        end
        return
    end
    SendAddonMessage(Comm.PREFIX_OUT, body, "WHISPER", ns.PlayerName())
end

-- Parse one of our own outgoing frames (for the demo responder and tests).
function Comm.ParseFrameOut(body)
    local ver, op, seq, rest = body:match("^(%d+) (%u+) (%w+) 1/1(.*)$")
    if not ver then
        return nil
    end
    return { ver = tonumber(ver), op = op, seq = tonumber(seq, 36), payload = strsub(rest, 2) }
end

local function refill(now)
    if not lastRefill then
        lastRefill = now
        return
    end
    local dt = now - lastRefill
    if dt > 0 then
        tokens = math.min(Comm.BURST, tokens + dt * Comm.RATE)
        lastRefill = now
    end
end

function Comm.Flush()
    if not Comm.canSend and not Comm.demo then
        return
    end
    refill(GetTime())
    while #queue > 0 and tokens >= 1 do
        tokens = tokens - 1
        rawSend(table.remove(queue, 1))
    end
end

-- Send an intent. Returns true when queued, or false, reason.
function Comm.Send(op, ...)
    if Comm.blocked and op ~= "HELLO" then
        Comm.stats.refused = Comm.stats.refused + 1
        return false, "blocked"
    end
    -- Until the server answers HELLO there is nobody to act on an intent (or the server has no
    -- Bleakhold module): only the handshake and requests for data go out.
    if not Comm.ready and not Comm.demo and op ~= "HELLO" and op ~= "GET" then
        Comm.stats.refused = Comm.stats.refused + 1
        return false, "not connected"
    end
    local payload, err = Comm.EncodeIntent(op, ...)
    if not payload then
        Comm.stats.refused = Comm.stats.refused + 1
        return false, err
    end
    local key = op .. " " .. payload
    local now = GetTime()
    if recent[key] and now - recent[key] < Comm.DEDUP then
        return true, "dedup"
    end
    outSeq = outSeq % (SEQ_MOD - 1) + 1
    local body = "1 " .. op .. " " .. Comm.Base36(outSeq) .. " 1/1"
    if payload ~= "" then
        body = body .. " " .. payload
    end
    if #body > Comm.MAX_OUT_BODY then
        Comm.stats.refused = Comm.stats.refused + 1
        return false, "too long"
    end
    if #queue >= Comm.QUEUE_MAX then
        Comm.stats.refused = Comm.stats.refused + 1
        return false, "queue full"
    end
    recent[key] = now
    queue[#queue + 1] = body
    Comm.lastSeq = Comm.Base36(outSeq)   -- what an ERR for this intent will name
    Comm.Flush()
    return true
end

-- Request topics. Requests made in the same frame are sent together in one GET.
function Comm.Get(topic, ...)
    if not Comm.TOPICS[topic] then
        return false
    end
    local rec = { topic, ... }
    local key = tconcat(rec, ",")
    if not Comm.ready and not Comm.demo then
        deferred[key] = rec
        return true
    end
    local now = GetTime()
    if lastGet[key] and now - lastGet[key] < Comm.GET_COOLDOWN then
        return false
    end
    lastGet[key] = now
    for _, r in ipairs(pendingGets) do
        if tconcat(r, ",") == key then
            return true
        end
    end
    pendingGets[#pendingGets + 1] = rec
    if #pendingGets == 1 then
        ns.After(0, Comm.FlushGets)
    end
    return true
end

function Comm.FlushGets()
    while #pendingGets > 0 do
        local batch = {}
        while #pendingGets > 0 and #batch < Comm.MAX_GET_RECORDS do
            batch[#batch + 1] = table.remove(pendingGets, 1)
        end
        Comm.Send("GET", unpack(batch))
    end
end

-- Forget the GET cooldown for a topic (a user action such as opening a window may refresh at once).
function Comm.Refresh(topic, ...)
    lastGet[tconcat({ topic, ... }, ",")] = nil
    return Comm.Get(topic, ...)
end

------------------------------------------------------------------------------------------------------
-- Receiving
------------------------------------------------------------------------------------------------------
local function requestTopic(topic)
    if topic then
        Comm.Get(topic)
    end
end

function Comm.Dispatch(op, payload, seq)
    local records = Comm.SplitRecords(payload)
    if not records[1] then
        records[1] = {}   -- handlers can always read the first record
    end
    local spec = topicOf[op]
    if spec then
        local rev = U.Int(records[1] and records[1][1], nil, 0, INT32)
        if spec.snapshot then
            if rev == nil then
                drop("norev")
                return
            end
            Comm.topicRev[spec.topic] = rev
        else
            local last = Comm.topicRev[spec.topic]
            if last == nil then
                requestTopic(spec.topic)
                drop("nosnapshot")
                return
            end
            if rev == nil or rev <= last then
                Comm.stats.dups = Comm.stats.dups + 1
                return
            end
            if rev ~= last + 1 then
                Comm.stats.gaps = Comm.stats.gaps + 1
                requestTopic(spec.topic)
                return
            end
            Comm.topicRev[spec.topic] = rev
        end
    end
    local h = Comm.handlers[op]
    if not h then
        Comm.stats.unknown = Comm.stats.unknown + 1
        return
    end
    ns.SafeCall(h, records, op, seq)
end

local function countBuffers()
    local n, oldestOp, oldestT = 0, nil, nil
    for op, b in pairs(buffers) do
        n = n + 1
        if not oldestT or b.t0 < oldestT then
            oldestOp, oldestT = op, b.t0
        end
    end
    return n, oldestOp
end

-- Feed one server frame body (already checked to come from the server channel).
function Comm.Receive(body)
    Comm.stats.framesIn = Comm.stats.framesIn + 1
    local fr, why = Comm.ParseFrame(body)
    if not fr then
        drop(why)
        return
    end
    addLog("<", body)
    if fr.op ~= "HELLO" then
        if fr.ver ~= ns.PROTO then
            drop("version")
            return
        end
        if Comm.blocked then
            drop("blocked")
            return
        end
    end
    if fr.total == 1 then
        Comm.Dispatch(fr.op, fr.payload, fr.seq)
        return
    end
    local op, seq = fr.op, fr.seq
    if lastDone[op] and not Comm.SeqNewer(seq, lastDone[op]) then
        Comm.stats.dups = Comm.stats.dups + 1
        return
    end
    local buf = buffers[op]
    if buf and buf.seq ~= seq then
        if Comm.SeqNewer(seq, buf.seq) then
            buffers[op] = nil
            drop("superseded")
            buf = nil
        else
            drop("stale")
            return
        end
    end
    if not buf then
        local n, oldestOp = countBuffers()
        if n >= Comm.MAX_BUFFERS and oldestOp then
            buffers[oldestOp] = nil
            drop("evicted")
        end
        buf = { seq = seq, total = fr.total, parts = {}, have = 0, bytes = 0, t0 = GetTime() }
        buffers[op] = buf
    end
    if buf.total ~= fr.total then
        buffers[op] = nil
        drop("total")
        requestTopic(opTopic[op] or (topicOf[op] and topicOf[op].topic))
        return
    end
    if buf.parts[fr.part] then
        Comm.stats.dups = Comm.stats.dups + 1
        return
    end
    buf.parts[fr.part] = fr.payload
    buf.have = buf.have + 1
    buf.bytes = buf.bytes + #fr.payload
    if buf.bytes > Comm.MAX_ASSEMBLED then
        buffers[op] = nil
        drop("toolarge")
        return
    end
    if buf.have == buf.total then
        buffers[op] = nil
        lastDone[op] = seq
        Comm.Dispatch(op, tconcat(buf.parts, "", 1, buf.total), seq)
    end
end

-- Drop chunk buffers that did not complete in time and ask for their topic again.
function Comm.Sweep()
    local now = GetTime()
    for op, b in pairs(buffers) do
        if now - b.t0 > Comm.CHUNK_TIMEOUT then
            buffers[op] = nil
            Comm.stats.timeouts = Comm.stats.timeouts + 1
            requestTopic(opTopic[op] or (topicOf[op] and topicOf[op].topic))
        end
    end
end

function Comm.PendingChunks()
    local n = countBuffers()
    return n
end

local function sameName(a, b)
    if type(a) ~= "string" or type(b) ~= "string" then
        return false
    end
    a = a:match("^([^%-]+)") or a
    return a == b
end

function Comm.OnAddonMessage(event, prefix, msg, channel, sender)
    if prefix ~= Comm.PREFIX_IN then
        return
    end
    if channel ~= "WHISPER" or not sameName(sender, ns.PlayerName()) then
        Comm.stats.foreign = Comm.stats.foreign + 1
        return
    end
    if Comm.demo then
        drop("demo")
        return
    end
    Comm.Receive(msg)
end

-- Inject a server frame without the chat layer (demo mode).
function Comm.Inject(body)
    Comm.Receive(body)
end

------------------------------------------------------------------------------------------------------
-- Handshake and clock
------------------------------------------------------------------------------------------------------
function Comm.SendHello()
    local locale = GetLocale and GetLocale() or "enUS"
    local dataVer = (ns.db.defsVer and tonumber(ns.db.defsVer)) or 0
    Comm.Send("HELLO", ns.PROTO, ns.VERSION, dataVer, locale)
end

local function scheduleHelloRetry()
    if helloTimer then
        ns.Cancel(helloTimer)
    end
    helloTries = helloTries + 1
    local delay = Comm.HELLO_RETRY[helloTries]
    if not delay then
        return
    end
    helloTimer = ns.After(delay, function()
        helloTimer = nil
        if not Comm.ready and not Comm.demo then
            Comm.SendHello()
            scheduleHelloRetry()
        end
    end)
end

function Comm.ServerTime()
    return time() + (Comm.clockOffset or 0)
end

Comm.server = {}

Comm.Handle("HELLO", function(r)
    local f = r[1] or {}
    local s = {
        proto = U.Int(f[1], 0, 0, 999),
        minProto = U.Int(f[2], 0, 0, 999),
        serverEpoch = U.Int(f[3], nil, 0, INT32),
        utcOffsetMin = U.Int(f[4], 0, -1440, 1440),
        dataVer = U.Int(f[5], 0, 0, INT32),
        features = U.Int(f[6], 0, 0, INT32),
        seasonId = U.Int(f[7], 0, 0, INT32),
        dailyReset = U.Int(f[8], nil, 0, INT32),
        weeklyReset = U.Int(f[9], nil, 0, INT32),
        realm = U.Str(f[10], nil, 48),
        site = U.Str(f[11], nil, 80),
    }
    Comm.server = s
    if s.serverEpoch then
        Comm.clockOffset = s.serverEpoch - time()
    end
    if helloTimer then
        ns.Cancel(helloTimer)
        helloTimer = nil
    end
    if ns.PROTO < s.minProto then
        Comm.blocked = true
        Comm.outdated = true
        wipe(queue)
        ns.Fire("OUTDATED", s)
        return
    end
    Comm.ready = true
    ns.Fire("HELLO", s)
    for key, rec in pairs(deferred) do
        deferred[key] = nil
        Comm.Get(unpack(rec))
    end
end)

Comm.Handle("PONG", function(r)
    local f = r[1] or {}
    local epoch = U.Int(f[2], nil, 0, INT32)
    if epoch then
        Comm.clockOffset = epoch - time()
    end
end)

-- Feature bits from HELLO (the server can hide boards that are not ready).
Comm.FEATURE = { RIFT_SCORE = 1, SHARDS = 2, DBM_BY_SERVER = 4, SEASON = 8, LEADERBOARDS = 16, COLLECTIONS = 32,
    EMOJI = 64, DANCE = 128, CASES = 256, CAMP = 512, GLIDE = 1024, FIELD_REPAIR = 2048 }

function Comm.HasFeature(bitValue)
    local f = Comm.server and Comm.server.features or 0
    return bit.band(f, bitValue) ~= 0
end

------------------------------------------------------------------------------------------------------
-- Wiring
------------------------------------------------------------------------------------------------------
ns.RegisterEvent("CHAT_MSG_ADDON", Comm.OnAddonMessage)

ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    Comm.canSend = true
    if not Comm.ready and not Comm.demo then
        helloTries = 0
        Comm.SendHello()
        scheduleHelloRetry()
    end
    Comm.Flush()
end)

ns.Every(0.25, function()
    Comm.Flush()
end)

ns.Every(1, function()
    Comm.Sweep()
    local now = GetTime()
    for k, t in pairs(recent) do
        if now - t > 5 then
            recent[k] = nil
        end
    end
end)

-- Reset everything learnt from the server (leaving demo mode, tests).
function Comm.Reset()
    wipe(buffers)
    wipe(lastDone)
    wipe(Comm.topicRev)
    wipe(lastGet)
    wipe(pendingGets)
    wipe(queue)
    wipe(recent)
    wipe(deferred)
    Comm.ready = false
    Comm.blocked = false
    Comm.outdated = false
    Comm.server = {}
    Comm.clockOffset = 0
end

ns.AddCommand("status", "protocol status", function()
    local s = Comm.stats
    ns.Print(strformat("server %s, proto %d, demo %s, in %d, sent %d, refused %d, gaps %d, timeouts %d, errors %d",
        Comm.ready and "connected" or (Comm.outdated and "requires a newer client" or "not answering"),
        ns.PROTO, Comm.demo and "on" or "off", s.framesIn, s.sent, s.refused, s.gaps, s.timeouts, ns.errors))
    local parts = {}
    for k, v in pairs(s.dropped) do
        parts[#parts + 1] = k .. "=" .. v
    end
    if #parts > 0 then
        ns.Print("dropped: " .. tconcat(parts, " "))
    end
end)
