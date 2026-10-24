-- Every S2C op and every window must survive missing and garbage fields without a Lua error.
-- The runner fails a test when the addon reports any error through the error handler.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local GARBAGE = {
    "", "nan", "inf", "-inf", "-1", "-999999999", "99999999999999999999", "1e308", "0x7fffffff", "1.5",
    "%ZZ", "%00", "%", "abc", "%7C%7Ccff00ff00evil%7Cr", "\255\254\253", string.rep("A", 400),
    string.rep("%41", 120), "%E2%82", "~~~", "-0", " 7", "D", "W", "R", "K", "F", "P",
}

local seed = 12345
local function rand(n)
    seed = (seed * 1103515245 + 12345) % 2147483648
    return seed % n + 1
end

local function garbageField()
    local g = GARBAGE[rand(#GARBAGE)]
    -- raw garbage: separators inside are allowed here on purpose (they split fields/lists)
    if rand(5) == 1 then
        return g .. ":" .. GARBAGE[rand(#GARBAGE)] .. "~" .. GARBAGE[rand(#GARBAGE)]
    end
    return g
end

local function rawPayload(records)
    local recs = {}
    for _, r in ipairs(records) do recs[#recs + 1] = table.concat(r, ",") end
    return table.concat(recs, ";")
end

local function sendRaw(M, op, payload)
    -- H.frames splits without regard for escapes: also tests cuts in odd places
    for _, f in ipairs(H.frames(op, payload, 700)) do H.deliver(M, f) end
end

local function allOps(M)
    local ops = {}
    for op in pairs(FX.examples(M)) do ops[#ops + 1] = op end
    table.sort(ops)
    return ops
end

test("every handled op is covered by the fuzz examples", function(M, ns)
    local ex = FX.examples(M)
    for op in pairs(ns.Comm.handlers) do
        H.ok(ex[op], "fixtures.lua has an example for " .. op)
    end
end)

test("empty payloads", function(M, ns)
    FX.connect(M, H)
    for _, op in ipairs(allOps(M)) do
        if op ~= "HELLO" then sendRaw(M, op, "") end
    end
    FX.openEverything(M, ns)
end)

test("records with every field empty", function(M, ns)
    FX.connect(M, H)
    for _, op in ipairs(allOps(M)) do
        if op ~= "HELLO" then
            sendRaw(M, op, string.rep(",", 15) .. ";" .. string.rep(",", 15))
            sendRaw(M, op, "1" .. string.rep(",", 15))
        end
    end
    FX.openEverything(M, ns)
end)

test("valid examples with fields removed from the end", function(M, ns)
    FX.connect(M, H)
    local ex = FX.examples(M)
    for _, op in ipairs(allOps(M)) do
        if op ~= "HELLO" then
            local recs = ex[op]
            for cut = 1, #recs[1] do
                local r = {}
                for i, rec in ipairs(recs) do
                    local copy = {}
                    for k = 1, (i == 1 and cut or #rec) do copy[k] = rec[k] end
                    r[i] = copy
                end
                -- bump the revision so snapshots are applied each time
                if FX.REV[op] then r[1][1] = 100 + cut end
                H.send(M, op, r)
            end
        end
    end
    FX.openEverything(M, ns)
end)

test("random garbage in every field (valid revision so handlers run)", function(M, ns)
    FX.connect(M, H)
    local ex = FX.examples(M)
    for round = 1, 12 do
        for _, op in ipairs(allOps(M)) do
            if op ~= "HELLO" then
                local recs = {}
                local n = rand(6)
                for i = 1, n do
                    local width = #(ex[op][math.min(i, #ex[op])])
                    local r = {}
                    for k = 1, width + rand(3) - 1 do r[k] = garbageField() end
                    recs[i] = r
                end
                if FX.REV[op] then recs[1][1] = tostring(1000 + round) end
                sendRaw(M, op, rawPayload(recs))
            end
        end
        if round % 4 == 0 then FX.openEverything(M, ns) end
    end
    FX.openEverything(M, ns)
end)

test("garbage revisions and garbage HELLO", function(M, ns)
    for _, g in ipairs(GARBAGE) do
        sendRaw(M, "HELLO", g .. "," .. g .. "," .. g .. ",,,,,," .. g)
        sendRaw(M, "WEEK", g .. ",4,1")
        sendRaw(M, "TASK", g .. ",101,1,1")
    end
    FX.connect(M, H)
    FX.openEverything(M, ns)
end)

test("many records and huge lists", function(M, ns)
    FX.connect(M, H)
    local big = { "1,1,0,G" }
    for i = 1, 400 do big[#big + 1] = i .. ",D," .. i .. ",1,2,C,5,,0" end
    sendRaw(M, "TASKS", table.concat(big, ";"))
    local board = { "1,10,1,189,1,x,1" }
    for i = 1, 300 do board[#board + 1] = i .. "," .. (i % 9) .. ",10,20,15," .. i end
    sendRaw(M, "BOARD", table.concat(board, ";"))
    local lb = { "K,1,0,0,1,999" }
    for i = 1, 200 do lb[#lb + 1] = i .. ",602,15,30,1," .. string.rep("N~1:", 50) end
    sendRaw(M, "LB", table.concat(lb, ";"))
    sendRaw(M, "MP", "7001,1000,1800,1,1,1,1,2147483647," .. string.rep("1:", 300) .. "," .. string.rep("9:", 300) .. ",1")
    sendRaw(M, "SET", "1,201,1,Name,2147483647,1," .. string.rep("16861:", 200) .. "," .. string.rep("229:", 200))
    H.ok(#ns.S.tasks.daily + #ns.S.tasks.weekly <= 24, "task list capped")
    H.ok(#ns.S.board.dungeons <= 120, "board capped")
    FX.openEverything(M, ns)
end)

test("random raw bytes as payload", function(M, ns)
    FX.connect(M, H)
    for round = 1, 40 do
        local bytes = {}
        for i = 1, rand(600) do bytes[i] = string.char(rand(255)) end
        local payload = table.concat(bytes)
        for _, op in ipairs({ "WEEK", "TASKS", "BOARD", "QUEUE", "MP", "LB", "SEASON", "SET", "DEF", "TOAST", "ERR" }) do
            sendRaw(M, op, "1," .. payload)
        end
    end
    FX.openEverything(M, ns)
end)

test("valid data, then the run, queue and rift timers keep ticking", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    local ex = FX.examples(M)
    H.send(M, "MPS", ex.MPS)
    M.Advance(3)
    H.send(M, "MP", ex.MP)
    H.send(M, "QUEUE", ex.QUEUE)
    H.send(M, "RIFT", ex.RIFT)
    FX.openEverything(M, ns)
    M.Advance(30)
    H.send(M, "MPE", ex.MPE)
    H.send(M, "RIFTE", ex.RIFTE)
    M.Advance(90)
end)

test("server strings cannot inject escape codes into FontStrings", function(M, ns)
    FX.connect(M, H)
    H.send(M, "TASKS", { { 1, 0, 0, "G" }, { 101, "D", 1, 0, 1, "C", 20, "", 0, "|cffff0000Evil|r|Hitem:1|h[x]|h", "|TInterface\\Icons\\Foo:0|t" } })
    ns.UI.Open("tasks")
    M.Advance(0.3)
    local card = ns.Activities.tasksPage.cards[1]
    H.eq(card.title:GetText(), "||cffff0000Evil||r||Hitem:1||h[x]||h", "pipes doubled")
end)
