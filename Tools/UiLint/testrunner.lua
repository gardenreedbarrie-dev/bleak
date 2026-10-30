-- Bleakhold unit-test runner (run by wowlua, see run_tests.sh / check.sh).
--
--   wowlua testrunner.lua <repo> <addonDir> <api.lua> <test files...>
--
-- Every test gets a fresh mock game environment with the addon loaded from its TOC and the player in
-- the world: test("name", function(M, ns) ... end). A test fails if it raises or if the addon
-- reported a Lua error through the error handler (unless the test sets M.allowErrors).
local repo, addonDir, apiPath = arg[1], arg[2], arg[3]
assert(repo and addonDir and apiPath, "usage: testrunner.lua <repo> <addonDir> <api.lua> <tests...>")

local api = assert(host_loadfile(apiPath))()
local mockFactory = assert(host_loadfile(repo .. "/Tools/UiLint/mock/wowmock.lua"))()

local results = { pass = 0, fail = 0, failures = {} }

local function newGame(opts)
    local M = mockFactory({ api = api, repo = repo })
    M.addonDir = addonDir
    M.repo = repo
    if opts and opts.before then
        opts.before(M)
    end
    local ns = M.LoadAddon(addonDir, "Bleakhold")
    M.FireEvent("ADDON_LOADED", "Bleakhold")
    M.FireEvent("PLAYER_LOGIN")
    if not (opts and opts.noWorld) then
        M.EnterWorld()
    end
    return M, ns
end

-- Shared helpers for test files.
local H = {}

function H.eq(a, b, msg)
    if a ~= b then
        error((msg or "values differ") .. ": expected " .. tostring(b) .. ", got " .. tostring(a), 2)
    end
end

function H.ok(v, msg)
    if not v then
        error(msg or "assertion failed", 2)
    end
    return v
end

function H.contains(s, sub, msg)
    if type(s) ~= "string" or not s:find(sub, 1, true) then
        error((msg or "missing text") .. ": " .. tostring(sub) .. " not in " .. tostring(s), 2)
    end
end

-- Reference encoder, written independently of Comm.lua.
function H.esc(v)
    if v == nil then return "" end
    if v == true then return "1" end
    if v == false then return "0" end
    local s = tostring(v)
    local out = {}
    for i = 1, #s do
        local c = s:sub(i, i)
        local b = c:byte()
        if b < 32 or b == 127 or c == "%" or c == ";" or c == "," or c == ":" or c == "~" or c == "|" then
            out[#out + 1] = string.format("%%%02X", b)
        else
            out[#out + 1] = c
        end
    end
    return table.concat(out)
end

-- records: { {field, field, ...}, ... }; a field that is a table is a list (items escaped, ':' joined);
-- a list item that is a table is a tuple ('~' joined).
function H.payload(records)
    local recs = {}
    for _, r in ipairs(records) do
        local fields = {}
        for i = 1, #r do
            local f = r[i]
            if type(f) == "table" then
                local items = {}
                for j, item in ipairs(f) do
                    if type(item) == "table" then
                        local parts = {}
                        for k, p in ipairs(item) do parts[k] = H.esc(p) end
                        items[j] = table.concat(parts, "~")
                    else
                        items[j] = H.esc(item)
                    end
                end
                fields[i] = table.concat(items, ":")
            else
                fields[i] = H.esc(f)
            end
        end
        recs[#recs + 1] = table.concat(fields, ",")
    end
    return table.concat(recs, ";")
end

H.serverSeq = 100

local B36 = "0123456789abcdefghijklmnopqrstuvwxyz"
function H.b36(n)
    if n == 0 then return "0" end
    local s = ""
    while n > 0 do
        local d = n % 36
        s = B36:sub(d + 1, d + 1) .. s
        n = math.floor(n / 36)
    end
    return s
end

-- Build server frames for a payload, splitting every `chunk` bytes of payload (no smart cuts, so the
-- test controls where the cuts fall).
function H.frames(op, payload, chunk, seq)
    H.serverSeq = H.serverSeq + 1
    seq = seq or H.serverSeq
    local parts = {}
    chunk = chunk or 900
    if payload == "" then
        parts[1] = ""
    end
    local i = 1
    while i <= #payload do
        parts[#parts + 1] = payload:sub(i, i + chunk - 1)
        i = i + chunk
    end
    local frames = {}
    for p = 1, #parts do
        local body = "1 " .. op .. " " .. H.b36(seq) .. " " .. p .. "/" .. #parts
        if parts[p] ~= "" then body = body .. " " .. parts[p] end
        frames[p] = body
    end
    return frames, seq
end

function H.deliver(M, body, prefix, channel, sender)
    M.FireEvent("CHAT_MSG_ADDON", prefix or "BHs", body, channel or "WHISPER", sender or M.playerName)
end

-- Send a whole S2C message (records table or raw payload string).
function H.send(M, op, records, chunk)
    local payload = type(records) == "string" and records or H.payload(records)
    local frames = H.frames(op, payload, chunk)
    for _, f in ipairs(frames) do
        H.deliver(M, f)
    end
    return frames
end

-- Standard handshake reply so the addon considers the server connected.
function H.hello(M, extra)
    local f = { 1, 1, M.epoch + 5, 60, 7, 0, 1, M.epoch + 3600 * 7, M.epoch + 86400 * 3, "Bleakhold", "bleakhold.com" }
    for k, v in pairs(extra or {}) do f[k] = v end
    H.send(M, "HELLO", { f })
end

-- Parsed client messages: { op=, seq=, fields={raw...}, records={...}, body= }
function H.intents(M, from)
    local out = {}
    for i = from or 1, #M.sent do
        local s = M.sent[i]
        if s.prefix == "BHc" then
            local ver, op, seq, part, total, rest = s.msg:match("^(%d+) (%u+) (%w+) (%d+)/(%d+)(.*)$")
            local payload = rest and rest:sub(2) or ""
            local records = {}
            for rec in (payload .. ";"):gmatch("([^;]*);") do
                if rec ~= "" then
                    local fields = {}
                    for fld in (rec .. ","):gmatch("([^,]*),") do fields[#fields + 1] = fld end
                    records[#records + 1] = fields
                end
            end
            out[#out + 1] = { op = op, seq = seq, part = tonumber(part), total = tonumber(total), payload = payload,
                records = records, fields = records[1] or {}, body = s.msg, raw = s }
        end
    end
    return out
end

function H.lastIntent(M, op)
    local list = H.intents(M)
    for i = #list, 1, -1 do
        if not op or list[i].op == op then return list[i] end
    end
end

function H.countIntents(M, op)
    local n = 0
    for _, it in ipairs(H.intents(M)) do
        if it.op == op then n = n + 1 end
    end
    return n
end

H.newGame = newGame

------------------------------------------------------------------------------------------------------
local function runFile(path)
    local tests = {}
    local tenv = setmetatable({
        test = function(name, fn, opts) tests[#tests + 1] = { name = name, fn = fn, opts = opts } end,
        H = H, print = print, host_readfile = host_readfile, host_loadfile = host_loadfile, repo = repo, addonDir = addonDir, api = api,
    }, { __index = _G })
    local chunk, err = host_loadfile(path)
    if not chunk then
        results.fail = results.fail + 1
        results.failures[#results.failures + 1] = path .. ": " .. tostring(err)
        print("FAIL " .. path .. ": " .. tostring(err))
        return
    end
    setfenv(chunk, tenv)
    local okLoad, loadErr = xpcall(chunk, host_traceback)
    if not okLoad then
        results.fail = results.fail + 1
        results.failures[#results.failures + 1] = path .. ": " .. tostring(loadErr)
        print("FAIL " .. path .. ": " .. tostring(loadErr))
        return
    end
    local short = path:match("([^/]+)$")
    for _, t in ipairs(tests) do
        local M, ns
        local ok, e = xpcall(function()
            M, ns = newGame(t.opts)
            t.fn(M, ns)
        end, host_traceback)
        if ok and M and #M.errors > 0 and not M.allowErrors then
            ok, e = false, "addon reported Lua errors: " .. M.errors[1]
        end
        if ok then
            results.pass = results.pass + 1
        else
            results.fail = results.fail + 1
            results.failures[#results.failures + 1] = short .. " :: " .. t.name .. "\n    " .. tostring(e):gsub("\n", "\n    ")
            print("FAIL " .. short .. " :: " .. t.name)
        end
    end
    print(string.format("%-28s %d tests", short, #tests))
end

for i = 4, #arg do
    runFile(arg[i])
end

print(string.format("\n%d passed, %d failed", results.pass, results.fail))
for _, f in ipairs(results.failures) do
    print("\n" .. f)
end
host_exit(results.fail == 0 and 0 or 1)
