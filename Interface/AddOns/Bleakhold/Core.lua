-- Bleakhold: core (namespace, events, timers, saved variables, value helpers, slash commands).
-- Built for the 3.3.5a client (Interface 30300): no C_Timer, one OnUpdate driver frame for all timers.
local ADDON, ns = ...

Bleakhold = ns
ns.ADDON = ADDON or "Bleakhold"
ns.VERSION = "1.0.0"
ns.PROTO = 1        -- protocol major version (docs/BleakholdProtocol.md)
ns.DATAVER = 1      -- version of the built-in fallback definitions in Data.lua
ns.errors = 0       -- handler errors caught by ns.SafeCall (shown by /bh status, checked by tests)

local type, pairs, ipairs, tostring, tonumber, select = type, pairs, ipairs, tostring, tonumber, select
local floor, max, min = math.floor, math.max, math.min
local strfind, strsub, strgsub, strformat, strlower = string.find, string.sub, string.gsub, string.format, string.lower

------------------------------------------------------------------------------------------------------
-- Errors
------------------------------------------------------------------------------------------------------
local function report(err)
    ns.errors = ns.errors + 1
    ns.lastError = err
    local handler = geterrorhandler and geterrorhandler()
    if handler then
        handler(err)
    end
end

-- Calls fn(...) and keeps going if it raises: one broken widget must not stop the protocol or the
-- other windows. The error still reaches the client's error handler.
function ns.SafeCall(fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok then
        report(err)
    end
    return ok
end

------------------------------------------------------------------------------------------------------
-- Game events
------------------------------------------------------------------------------------------------------
local eventFrame = CreateFrame("Frame", "BleakholdEventFrame")
local eventHandlers = {}

function ns.RegisterEvent(event, fn)
    local list = eventHandlers[event]
    if not list then
        list = {}
        eventHandlers[event] = list
        eventFrame:RegisterEvent(event)
    end
    list[#list + 1] = fn
end

eventFrame:SetScript("OnEvent", function(self, event, ...)
    local list = eventHandlers[event]
    if not list then
        return
    end
    for i = 1, #list do
        ns.SafeCall(list[i], event, ...)
    end
end)

------------------------------------------------------------------------------------------------------
-- Internal messages (state changes between modules)
------------------------------------------------------------------------------------------------------
local listeners = {}

function ns.On(message, fn)
    local list = listeners[message]
    if not list then
        list = {}
        listeners[message] = list
    end
    list[#list + 1] = fn
end

function ns.Fire(message, ...)
    local list = listeners[message]
    if not list then
        return
    end
    for i = 1, #list do
        ns.SafeCall(list[i], ...)
    end
end

------------------------------------------------------------------------------------------------------
-- Timers: one parentless driver frame (it keeps running while UIParent is hidden with Alt+Z)
------------------------------------------------------------------------------------------------------
local driver = CreateFrame("Frame", "BleakholdTimerFrame")
local timers = {}
local timerSerial = 0

function ns.After(delay, fn)
    timerSerial = timerSerial + 1
    local t = { id = timerSerial, due = GetTime() + (delay or 0), fn = fn }
    timers[#timers + 1] = t
    return t
end

function ns.Every(interval, fn)
    local t = ns.After(interval, fn)
    t.interval = interval
    return t
end

function ns.Cancel(t)
    if t then
        t.cancelled = true
    end
end

driver:SetScript("OnUpdate", function()
    local now = GetTime()
    local n = #timers
    if n == 0 then
        return
    end
    local i = 1
    while i <= n do
        local t = timers[i]
        if t.cancelled then
            table.remove(timers, i)
            n = n - 1
        elseif t.due <= now then
            if t.interval then
                t.due = now + t.interval
                i = i + 1
            else
                table.remove(timers, i)
                n = n - 1
            end
            ns.SafeCall(t.fn, t)
        else
            i = i + 1
        end
    end
end)

------------------------------------------------------------------------------------------------------
-- Value helpers. Every server value goes through these: a missing or malformed field becomes the
-- default instead of a Lua error (docs/BleakholdProtocol.md, "Parsing rules").
------------------------------------------------------------------------------------------------------
local U = {}
ns.U = U

-- Unescape %XX. Returns nil for a malformed escape or an escaped NUL.
function U.Unescape(s)
    if type(s) ~= "string" then
        return nil
    end
    if not strfind(s, "%", 1, true) then
        return s
    end
    local bad = false
    local out = strgsub(s, "%%(..)", function(hex)
        if not strfind(hex, "^%x%x$") then
            bad = true
            return ""
        end
        local b = tonumber(hex, 16)
        if b == 0 then
            bad = true
            return ""
        end
        return string.char(b)
    end)
    -- A '%' that is not followed by two characters (end of the field) is malformed too.
    if bad or strfind(strgsub(s, "%%..", ""), "%", 1, true) then
        return nil
    end
    return out
end

-- Replace bytes that are not part of valid UTF-8 with '?'. Server text reaches FontStrings.
function U.CleanUtf8(s)
    if not strfind(s, "[\128-\255]") then
        return s
    end
    local out, i, n = {}, 1, #s
    while i <= n do
        local c = s:byte(i)
        local len = 0
        if c < 0x80 then
            len = 1
        elseif c >= 0xC2 and c <= 0xDF then
            len = 2
        elseif c >= 0xE0 and c <= 0xEF then
            len = 3
        elseif c >= 0xF0 and c <= 0xF4 then
            len = 4
        end
        local okSeq = len > 0 and i + len - 1 <= n
        if okSeq then
            for j = i + 1, i + len - 1 do
                local cc = s:byte(j)
                if cc < 0x80 or cc > 0xBF then
                    okSeq = false
                    break
                end
            end
        end
        if okSeq then
            out[#out + 1] = strsub(s, i, i + len - 1)
            i = i + len
        else
            out[#out + 1] = "?"
            i = i + 1
        end
    end
    return table.concat(out)
end

-- Cut s to at most maxLen bytes without leaving half a UTF-8 sequence (s must be valid UTF-8).
local function cutUtf8(s, maxLen)
    if #s <= maxLen then
        return s
    end
    s = strsub(s, 1, maxLen)
    local j = #s
    while j > 0 do
        local b = s:byte(j)
        if b < 0x80 then
            return s
        end
        if b >= 0xC0 then
            break
        end
        j = j - 1
    end
    if j == 0 then
        return ""
    end
    local lead = s:byte(j)
    local need = (lead >= 0xF0 and 4) or (lead >= 0xE0 and 3) or 2
    if #s - j + 1 < need then
        return strsub(s, 1, j - 1)
    end
    return s
end
U.CutUtf8 = cutUtf8

-- A server string, unescaped, valid UTF-8, without control bytes, at most maxLen bytes.
function U.Str(raw, default, maxLen)
    local s = U.Unescape(raw)
    if not s or s == "" then
        return default
    end
    s = strgsub(s, "%c", " ")
    s = U.CleanUtf8(s)
    return cutUtf8(s, maxLen or 200)
end

-- An integer field: decimal digits with an optional minus sign only (no "nan", "inf", hex or
-- exponents), clamped to [lo, hi].
function U.Int(raw, default, lo, hi)
    local s = U.Unescape(raw)
    if not s or not strfind(s, "^%-?%d+$") or #s > 15 then
        return default
    end
    local v = tonumber(s)
    if not v then
        return default
    end
    if lo and v < lo then
        v = lo
    end
    if hi and v > hi then
        v = hi
    end
    return v
end

function U.Bool(raw, default)
    local v = U.Int(raw, nil, 0, 1)
    if v == nil then
        return default
    end
    return v == 1
end

-- Split a raw field into raw list items (':' separated). At most maxItems items are kept.
function U.List(raw, maxItems)
    local out = {}
    if type(raw) ~= "string" or raw == "" then
        return out
    end
    maxItems = maxItems or 64
    local start = 1
    while #out < maxItems do
        local i = strfind(raw, ":", start, true)
        if i then
            out[#out + 1] = strsub(raw, start, i - 1)
            start = i + 1
        else
            out[#out + 1] = strsub(raw, start)
            break
        end
    end
    return out
end

function U.IntList(raw, maxItems, lo, hi)
    local out = {}
    for _, item in ipairs(U.List(raw, maxItems)) do
        local v = U.Int(item, nil, lo, hi)
        if v then
            out[#out + 1] = v
        end
    end
    return out
end

-- Split a raw list item into raw sub-fields ('~' separated).
function U.Tuple(raw, maxItems)
    local out = {}
    if type(raw) ~= "string" or raw == "" then
        return out
    end
    maxItems = maxItems or 16
    local start = 1
    while #out < maxItems do
        local i = strfind(raw, "~", start, true)
        if i then
            out[#out + 1] = strsub(raw, start, i - 1)
            start = i + 1
        else
            out[#out + 1] = strsub(raw, start)
            break
        end
    end
    return out
end

-- Text for a FontString: '|' is doubled so server text can never inject colour, texture or link codes.
function U.Safe(s)
    if s == nil then
        return ""
    end
    s = tostring(s)
    return (strgsub(s, "|", "||"))
end

function U.Clamp(v, lo, hi)
    if type(v) ~= "number" or v ~= v then
        return lo
    end
    if v < lo then
        return lo
    end
    if v > hi then
        return hi
    end
    return v
end

function U.Commas(n)
    n = tonumber(n)
    if not n then
        return "0"
    end
    local neg = n < 0
    local s = tostring(floor(math.abs(n)))
    local out = s
    while true do
        local k
        out, k = strgsub(out, "^(%d+)(%d%d%d)", "%1,%2")
        if k == 0 then
            break
        end
    end
    return (neg and "-" or "") .. out
end

-- 3725 -> "1:02:05", 125 -> "02:05"
function U.Clock(sec)
    sec = floor(tonumber(sec) or 0)
    local neg = sec < 0
    if neg then
        sec = -sec
    end
    local h = floor(sec / 3600)
    local m = floor((sec % 3600) / 60)
    local s = sec % 60
    local txt
    if h > 0 then
        txt = strformat("%d:%02d:%02d", h, m, s)
    else
        txt = strformat("%02d:%02d", m, s)
    end
    return (neg and "-" or "") .. txt
end

-- 26000 -> "7 h 13 min", 300 -> "5 min", 40 -> "< 1 min"
function U.Duration(sec)
    sec = floor(tonumber(sec) or 0)
    if sec <= 0 then
        return "now"
    end
    local d = floor(sec / 86400)
    local h = floor((sec % 86400) / 3600)
    local m = floor((sec % 3600) / 60)
    if d > 0 then
        return strformat("%d d %d h", d, h)
    elseif h > 0 then
        return strformat("%d h %d min", h, m)
    elseif m > 0 then
        return strformat("%d min", m)
    end
    return "< 1 min"
end

-- date() that never fails: the client's date() returns nil when gmtime/localtime cannot represent
-- the time (negative or far-future values on Windows).
function U.Date(fmt, t)
    t = tonumber(t)
    if not t or t ~= t or t < 0 or t > 32503680000 then
        return nil
    end
    return date(fmt, t)
end

function U.Hex(hex)
    hex = strgsub(hex or "FFFFFF", "#", "")
    local r = tonumber(strsub(hex, 1, 2), 16) or 255
    local g = tonumber(strsub(hex, 3, 4), 16) or 255
    local b = tonumber(strsub(hex, 5, 6), 16) or 255
    return r / 255, g / 255, b / 255
end

-- "|cffRRGGBB" + text + "|r" for already-safe text.
function U.Color(hex, text)
    return "|cff" .. strgsub(hex or "FFFFFF", "#", "") .. text .. "|r"
end

------------------------------------------------------------------------------------------------------
-- Saved variables
------------------------------------------------------------------------------------------------------
local function initDB()
    if type(BleakholdDB) ~= "table" then
        BleakholdDB = {}
    end
    if type(BleakholdCharDB) ~= "table" then
        BleakholdCharDB = {}
    end
    local db, cdb = BleakholdDB, BleakholdCharDB
    if type(db.chat) ~= "table" then
        db.chat = { hidden = {} }
    end
    if type(db.chat.hidden) ~= "table" then
        db.chat.hidden = {}
    end
    if type(db.options) ~= "table" then
        db.options = {}
    end
    if type(cdb.windows) ~= "table" then
        cdb.windows = {}
    end
    if type(cdb.orbs) ~= "table" then
        cdb.orbs = {}
    end
    ns.db, ns.cdb = db, cdb
end

-- Defaults are in place before ADDON_LOADED too, so modules can read options at load time.
ns.db = { chat = { hidden = {} }, options = {} }
ns.cdb = { windows = {}, orbs = {} }

ns.RegisterEvent("ADDON_LOADED", function(event, name)
    if name == ns.ADDON then
        initDB()
        ns.Fire("DB_READY")
    end
end)

function ns.Option(key, default)
    local v = ns.db.options[key]
    if v == nil then
        return default
    end
    return v
end

------------------------------------------------------------------------------------------------------
-- Chat output
------------------------------------------------------------------------------------------------------
function ns.Print(msg)
    if DEFAULT_CHAT_FRAME then
        DEFAULT_CHAT_FRAME:AddMessage("|cffC9A25ABleakhold|r: " .. tostring(msg))
    end
end

------------------------------------------------------------------------------------------------------
-- Player helpers (3.3.5a has no IsInGroup / UnitIsGroupLeader)
------------------------------------------------------------------------------------------------------
function ns.PlayerName()
    local name = UnitName("player")
    return name
end

function ns.GroupInfo()
    local raid = GetNumRaidMembers and GetNumRaidMembers() or 0
    if raid > 0 then
        return "RAID", raid, (IsRaidLeader and IsRaidLeader()) and true or false, (IsRaidOfficer and IsRaidOfficer()) and true or false
    end
    local party = GetNumPartyMembers and GetNumPartyMembers() or 0
    if party > 0 then
        local leader = (IsPartyLeader and IsPartyLeader()) and true or false
        return "PARTY", party + 1, leader, leader
    end
    return nil, 1, true, true
end

------------------------------------------------------------------------------------------------------
-- Slash commands: /bh and /bleakhold
------------------------------------------------------------------------------------------------------
ns.commands = {}

function ns.AddCommand(name, help, fn)
    ns.commands[name] = { help = help, fn = fn }
end

local function slash(msg)
    msg = strtrim and strtrim(msg or "") or (msg or "")
    local cmd, rest = msg:match("^(%S*)%s*(.-)$")
    cmd = strlower(cmd or "")
    if cmd == "" then
        cmd = "activities"
    end
    local entry = ns.commands[cmd]
    if entry then
        entry.fn(rest or "")
        return
    end
    ns.Print("commands:")
    local names = {}
    for name in pairs(ns.commands) do
        names[#names + 1] = name
    end
    table.sort(names)
    for _, name in ipairs(names) do
        ns.Print("  /bh " .. name .. " - " .. ns.commands[name].help)
    end
end

-- Key binding labels (Bindings.xml)
BINDING_HEADER_BLEAKHOLD = "Bleakhold"
BINDING_NAME_BLEAKHOLD_ACTIVITIES = "Toggle Activities"
BINDING_NAME_BLEAKHOLD_COLLECTIONS = "Toggle Collections"
BINDING_NAME_BLEAKHOLD_SEASON = "Toggle Season"
BINDING_NAME_BLEAKHOLD_LEADERBOARDS = "Toggle Leaderboards"
BINDING_NAME_BLEAKHOLD_EMOTEWHEEL = "Emote Wheel (hold)"
BINDING_NAME_BLEAKHOLD_ANIMATIONS = "Toggle Animations"
BINDING_NAME_BLEAKHOLD_GRAPHICS = "Toggle Graphics settings"

SLASH_BLEAKHOLD1 = "/bh"
SLASH_BLEAKHOLD2 = "/bleakhold"
SlashCmdList["BLEAKHOLD"] = slash

ns.AddCommand("help", "list commands", function()
    slash("?")
end)
