-- Protocol v1: escaping, frames, chunk reassembly, revisions, throttle, handshake.

------------------------------------------------------------------------------------------------------
-- Escaping
------------------------------------------------------------------------------------------------------
test("escape round-trips every byte except NUL", function(M, ns)
    local C, U = ns.Comm, ns.U
    local all = {}
    for b = 1, 255 do all[#all + 1] = string.char(b) end
    local s = table.concat(all)
    local e = C.Escape(s)
    H.ok(not e:find("[;,:~|%c]"), "no separators or control bytes left")
    H.eq(U.Unescape(e), s, "round trip")
    H.eq(e, H.esc(s), "matches the reference encoder")
end)

test("escape covers the separators, percent and pipe", function(M, ns)
    local C = ns.Comm
    H.eq(C.Escape("a;b,c:d~e|f%g"), "a%3Bb%2Cc%3Ad%7Ee%7Cf%25g")
    H.eq(C.Escape(12), "12")
    H.eq(C.Escape(nil), "")
    H.eq(C.Escape(true), "1")
end)

test("malformed escapes and escaped NUL are rejected", function(M, ns)
    local U = ns.U
    H.eq(U.Unescape("%4"), nil, "short escape")
    H.eq(U.Unescape("abc%"), nil, "trailing percent")
    H.eq(U.Unescape("%G1"), nil, "not hex")
    H.eq(U.Unescape("%00"), nil, "escaped NUL")
    H.eq(U.Unescape("%41%42"), "AB")
    H.eq(U.Unescape("plain"), "plain")
    H.eq(U.Str("%4", "dflt"), "dflt", "bad escape -> default")
end)

test("value helpers reject garbage numbers", function(M, ns)
    local U = ns.U
    for _, bad in ipairs({ "nan", "inf", "-inf", "1e5", "0x10", "1.5", "", " 1", "1 ", "--1", "99999999999999999" }) do
        H.eq(U.Int(bad, -7), -7, "Int(" .. bad .. ")")
    end
    H.eq(U.Int("42", 0), 42)
    H.eq(U.Int("-3", 0), -3)
    H.eq(U.Int("500", 0, 0, 100), 100, "clamped high")
    H.eq(U.Int("-5", 0, 0, 100), 0, "clamped low")
    H.eq(U.Bool("1"), true)
    H.eq(U.Bool("x", false), false)
end)

test("strings are cleaned: control bytes, invalid UTF-8, length", function(M, ns)
    local U = ns.U
    H.eq(U.Str("a%0Ab"), "a b", "control byte")
    H.eq(U.Str("caf\195\169"), "caf\195\169", "valid UTF-8 kept")
    H.eq(U.Str("bad\255\254x"), "bad??x", "invalid bytes replaced")
    H.eq(U.Str("\226\130"), "??", "truncated sequence")
    local long = string.rep("\195\169", 30)  -- 60 bytes
    local cut = U.Str(long, nil, 7)
    H.eq(#cut, 6, "cut before a split sequence")
    H.eq(U.Safe("|cffff0000red|r"), "||cffff0000red||r", "pipes doubled for FontStrings")
end)

test("lists and tuples split raw fields before unescaping", function(M, ns)
    local U = ns.U
    local items = U.List("a%3Ab:c")
    H.eq(#items, 2)
    H.eq(U.Str(items[1]), "a:b")
    local t = U.Tuple("Nam%7Ee~7")
    H.eq(U.Str(t[1]), "Nam~e")
    H.eq(U.Int(t[2]), 7)
    H.eq(#U.IntList("1:x:3"), 2, "garbage list items dropped")
    H.eq(#U.List(string.rep("1:", 500), 64), 64, "list length capped")
end)

------------------------------------------------------------------------------------------------------
-- Frames
------------------------------------------------------------------------------------------------------
test("frame parsing accepts the documented header", function(M, ns)
    local C = ns.Comm
    local f = C.ParseFrame("1 WEEK 2s 1/1 3,4")
    H.eq(f.op, "WEEK"); H.eq(f.seq, 2 * 36 + 28); H.eq(f.part, 1); H.eq(f.total, 1); H.eq(f.payload, "3,4")
    local g = C.ParseFrame("1 QLEAVE 1 1/1")
    H.eq(g.payload, "", "empty payload without trailing space")
end)

test("frame parsing rejects bad headers", function(M, ns)
    local C = ns.Comm
    for _, bad in ipairs({ "", "1", "1 W 1 1/1 x", "1 TOOLONGOP 1 1/1", "1 week 1 1/1", "1 WEEK 1234567 1/1",
        "1 WEEK 1 0/1", "1 WEEK 1 2/1", "1 WEEK 1 1/100", "1 WEEK 1 1/1x", "1  WEEK 1 1/1", "x WEEK 1 1/1",
        "1 WEEK 1 1/1 a\0b" }) do
        H.eq(C.ParseFrame(bad), nil, "rejects " .. bad:gsub("%z", "\\0"))
    end
end)

test("overlong server frames are dropped", function(M, ns)
    H.hello(M)
    local before = ns.Comm.stats.dropped.oversize or 0
    H.deliver(M, "1 WEEK zz 1/1 1," .. string.rep("9", 1000))
    H.eq(ns.Comm.stats.dropped.oversize, before + 1)
    H.eq(ns.S.week, nil, "not applied")
end)

test("only own WHISPER on the BHs prefix is accepted", function(M, ns)
    H.hello(M)
    local frames = H.frames("WEEK", H.payload({ { 1, 4, 1, 18, 2140, 5500 } }))
    H.deliver(M, frames[1], "BHs", "PARTY", M.playerName)
    H.deliver(M, frames[1], "BHs", "WHISPER", "Mallory")
    H.deliver(M, frames[1], "BHc", "WHISPER", M.playerName)
    H.eq(ns.S.week, nil, "foreign frames ignored")
    H.deliver(M, frames[1])
    H.eq(ns.S.week.keysTimed, 4)
    H.eq(ns.S.week.coinsCap, 5500)
end)

test("frames of an unknown protocol version are dropped (HELLO excepted)", function(M, ns)
    H.deliver(M, "2 WEEK 5 1/1 1,4")
    H.eq(ns.S.week, nil)
    H.deliver(M, "2 HELLO 6 1/1 2,2," .. M.epoch)
    H.ok(ns.Comm.outdated, "HELLO of a newer server still read")
end)

test("unknown ops are ignored", function(M, ns)
    H.hello(M)
    H.send(M, "ZZTOP", { { 1, 2, 3 } })
    H.eq(ns.Comm.stats.unknown, 1)
end)

test("BuildFrames cuts at records and never inside an escape or UTF-8 sequence", function(M, ns)
    local C = ns.Comm
    local recs = {}
    for i = 1, 60 do recs[#recs + 1] = { i, "Na%me;" .. i, "\195\169\226\130\172 caf\195\169" } end
    local payload = H.payload(recs)
    for _, maxBody in ipairs({ 60, 100, 233, 1000 }) do
        local frames = assert(C.BuildFrames("LB", 77, payload, maxBody))
        local parts = {}
        for i, f in ipairs(frames) do
            H.ok(#f <= maxBody, "frame within " .. maxBody)
            local p = C.ParseFrame(f)
            H.ok(p, "own frame parses")
            H.eq(p.part, i)
            H.eq(p.total, #frames)
            H.ok(not p.payload:find("%%.?$"), "no cut inside an escape")
            local last = p.payload:byte(#p.payload)
            H.ok(not last or last < 0xC0, "no cut after a UTF-8 lead byte")
            parts[#parts + 1] = p.payload
        end
        H.eq(table.concat(parts), payload, "reassembles to the payload")
    end
end)

------------------------------------------------------------------------------------------------------
-- Chunks
------------------------------------------------------------------------------------------------------
local function bigBoard(n)
    local recs = { { 5, 120, 9, 602, 1, "Bonus", 1 } }
    for i = 1, n do recs[#recs + 1] = { 1000 + i, 1 + i % 5, 10 + i % 60, 15 + i % 60, 15, i * 10, 1, 9999, "Record%Holder" .. i } end
    return H.payload(recs)
end

test("chunks in order", function(M, ns)
    H.hello(M)
    local frames = H.frames("BOARD", bigBoard(80), 300)
    H.ok(#frames > 3, "several parts")
    for _, f in ipairs(frames) do H.deliver(M, f) end
    H.eq(#ns.S.board.dungeons, 80)
    H.eq(ns.S.board.byId[1001].recordName, "Record%Holder1", "escapes across chunk cuts")
    H.eq(ns.Comm.PendingChunks(), 0)
end)

test("chunks out of order and duplicated", function(M, ns)
    H.hello(M)
    local frames = H.frames("BOARD", bigBoard(50), 200)
    local order = {}
    for i = #frames, 1, -1 do order[#order + 1] = frames[i] end
    table.insert(order, 2, frames[#frames])     -- duplicate
    table.insert(order, 1, frames[2])           -- duplicate early
    for _, f in ipairs(order) do H.deliver(M, f) end
    H.eq(#ns.S.board.dungeons, 50)
    H.ok(ns.Comm.stats.dups >= 1, "duplicates counted")
    -- a late duplicate of a completed message does not start a new buffer
    H.deliver(M, frames[1])
    H.eq(ns.Comm.PendingChunks(), 0)
end)

test("incomplete chunks time out and the topic is requested again", function(M, ns)
    H.hello(M)
    M.Advance(1)
    local n0 = H.countIntents(M, "GET")
    local frames = H.frames("BOARD", bigBoard(40), 200)
    for i = 1, #frames - 1 do H.deliver(M, frames[i]) end
    H.eq(ns.S.board, nil, "not applied while incomplete")
    M.Advance(7)
    H.eq(ns.Comm.PendingChunks(), 0, "buffer dropped")
    H.ok(ns.Comm.stats.timeouts >= 1, "timeout counted")
    local get = H.lastIntent(M, "GET")
    H.ok(H.countIntents(M, "GET") > n0 and get.payload:find("BOARD", 1, true), "GET BOARD sent")
end)

test("a newer SEQ of the same op replaces an unfinished buffer; stale parts are ignored", function(M, ns)
    H.hello(M)
    local old = H.frames("BOARD", bigBoard(30), 200, 500)
    local new = H.frames("BOARD", bigBoard(31), 200, 501)
    H.deliver(M, old[1])
    for _, f in ipairs(new) do H.deliver(M, f) end
    H.eq(#ns.S.board.dungeons, 31)
    H.deliver(M, old[2])
    H.eq(ns.Comm.PendingChunks(), 0, "stale part does not open a buffer")
end)

test("oversize: a reassembled payload over the cap is dropped", function(M, ns)
    H.hello(M)
    local C = ns.Comm
    C.MAX_ASSEMBLED = 2000
    local frames = H.frames("BOARD", bigBoard(60), 900)
    for _, f in ipairs(frames) do H.deliver(M, f) end
    H.eq(ns.S.board, nil)
    H.ok((C.stats.dropped.toolarge or 0) >= 1)
end)

test("a part whose TOTAL disagrees drops the buffer", function(M, ns)
    H.hello(M)
    H.deliver(M, "1 BOARD 7k 1/3 1,5")
    H.deliver(M, "1 BOARD 7k 2/4 ,1")
    H.eq(ns.Comm.PendingChunks(), 0)
    H.ok((ns.Comm.stats.dropped.total or 0) >= 1)
end)

test("interleaved chunked ops reassemble independently", function(M, ns)
    H.hello(M)
    local a = H.frames("BOARD", bigBoard(20), 150)
    local recs = { { 3, 6, 1, 0, "C" } }
    for i = 1, 6 do recs[#recs + 1] = { i, "D", 1, 0, 3, "C", 20, "", 0 } end
    local b = H.frames("TASKS", H.payload(recs), 40)
    local n = math.max(#a, #b)
    for i = 1, n do
        if a[i] then H.deliver(M, a[i]) end
        if b[i] then H.deliver(M, b[i]) end
    end
    H.eq(#ns.S.board.dungeons, 20)
    H.eq(#ns.S.tasks.daily, 6)
end)

------------------------------------------------------------------------------------------------------
-- Revisions
------------------------------------------------------------------------------------------------------
local function tasksSnapshot(rev)
    return { { rev, 1, 0, "C" }, { 11, "D", 1, 0, 1, "C", 20, "", 0 }, { 12, "D", 2, 14, 20, "I", 1, 40752, 0 } }
end

test("delta with rev+1 is applied, then a gap requests a snapshot", function(M, ns)
    H.hello(M)
    M.Advance(4)
    H.send(M, "TASKS", tasksSnapshot(5))
    H.send(M, "TASK", { { 6, 12, 15, 0 } })
    H.eq(ns.S.tasks.byUid[12].have, 15, "rev 6 applied")
    local gets = H.countIntents(M, "GET")
    H.send(M, "TASK", { { 9, 12, 19, 0 } })
    H.eq(ns.S.tasks.byUid[12].have, 15, "rev 9 not applied after a gap")
    H.eq(ns.Comm.stats.gaps, 1)
    M.Advance(0.2)
    H.ok(H.countIntents(M, "GET") > gets, "GET sent")
    H.contains(H.lastIntent(M, "GET").payload, "TASKS")
end)

test("duplicate and old deltas are ignored", function(M, ns)
    H.hello(M)
    H.send(M, "TASKS", tasksSnapshot(5))
    H.send(M, "TASK", { { 6, 12, 15, 0 } })
    H.send(M, "TASK", { { 6, 12, 16, 0 } })
    H.send(M, "TASK", { { 4, 12, 17, 0 } })
    H.eq(ns.S.tasks.byUid[12].have, 15)
end)

test("a delta before any snapshot asks for the snapshot", function(M, ns)
    H.hello(M)
    M.Advance(4)
    local gets = H.countIntents(M, "GET")
    H.send(M, "TASK", { { 2, 12, 15, 0 } })
    M.Advance(0.2)
    H.ok(H.countIntents(M, "GET") > gets)
    H.eq(ns.S.tasks, nil)
end)

test("a snapshot without a revision is dropped", function(M, ns)
    H.hello(M)
    H.send(M, "WEEK", { { "", 4 } })
    H.eq(ns.S.week, nil)
end)

test("a task becoming claimable fires the toast", function(M, ns)
    H.hello(M)
    local toasts = 0
    ns.On("TASK_DONE", function() toasts = toasts + 1 end)
    H.send(M, "TASKS", tasksSnapshot(1))
    H.send(M, "TASK", { { 2, 12, 20, 1 } })
    H.eq(toasts, 1)
end)

test("GET requests are coalesced and rate limited per topic", function(M, ns)
    local C = ns.Comm
    H.hello(M)
    M.Advance(4)
    local before = H.countIntents(M, "GET")
    C.Get("WEEK"); C.Get("ERA"); C.Get("WEEK")
    M.Advance(0.2)
    H.eq(H.countIntents(M, "GET"), before + 1, "one GET message")
    local g = H.lastIntent(M, "GET")
    H.eq(#g.records, 2, "two topics in it")
    C.Get("WEEK")
    M.Advance(0.2)
    H.eq(H.countIntents(M, "GET"), before + 1, "cooldown")
    M.Advance(3.5)
    C.Get("WEEK")
    M.Advance(0.2)
    H.eq(H.countIntents(M, "GET"), before + 2, "after the cooldown")
end)

------------------------------------------------------------------------------------------------------
-- Throttle and limits
------------------------------------------------------------------------------------------------------
test("send throttle: a burst, then the steady rate", function(M, ns)
    local C = ns.Comm
    H.hello(M)
    M.Advance(5)
    local start = #M.sent
    for i = 1, 20 do H.ok(C.Send("PING", i), "queued " .. i) end
    H.eq(#M.sent - start, C.BURST, "burst size")
    M.Advance(1)
    local after1 = #M.sent - start
    H.ok(after1 >= C.BURST + C.RATE - 1 and after1 <= C.BURST + C.RATE + 1, "about RATE more after one second: " .. after1)
    M.Advance(5)
    H.eq(#M.sent - start, 20, "all sent eventually")
end)

test("the send queue is bounded", function(M, ns)
    local C = ns.Comm
    H.hello(M)
    local accepted = 0
    for i = 1, 100 do
        if C.Send("PING", i) then accepted = accepted + 1 end
    end
    H.ok(accepted <= C.BURST + C.QUEUE_MAX + 1, "queue cap: " .. accepted)
end)

test("identical intents within the dedup window are sent once", function(M, ns)
    local C = ns.Comm
    H.hello(M)
    M.Advance(5)
    local n = #M.sent
    C.Send("KMODE", 2); C.Send("KMODE", 2); C.Send("KMODE", 2)
    H.eq(#M.sent - n, 1)
    M.Advance(1)
    C.Send("KMODE", 2)
    H.eq(#M.sent - n, 2)
end)

test("every client message fits 255 bytes with prefix and tab", function(M, ns)
    local C = ns.Comm
    H.hello(M)
    C.Send("LBQ", "K", 2147483647, 2147483647, 2147483647, 999)
    C.Get("SET", 2147483647, 2147483647, 2147483647)
    M.Advance(3)
    for _, s in ipairs(M.sent) do
        if s.prefix == "BHc" then
            H.ok(#s.prefix + 1 + #s.msg <= 255, "message size " .. (#s.msg + 4))
            H.eq(s.channel, "WHISPER")
            H.eq(s.target, M.playerName, "whispered to self")
        end
    end
end)

test("nothing is sent before the player is in the world", function(M, ns)
    local C = ns.Comm
    C.Get("WEEK")
    M.Advance(0.5)
    H.eq(#M.sent, 0)
    M.EnterWorld()
    M.Advance(0.5)
    H.ok(H.lastIntent(M, "HELLO"), "HELLO after PLAYER_ENTERING_WORLD")
end, { noWorld = true })

test("before the server answers HELLO: intents are refused, GETs wait for the answer", function(M, ns)
    local C = ns.Comm
    M.Advance(0.5)
    local ok, why = C.Send("QLEAVE")
    H.eq(ok, false)
    H.eq(why, "not connected")
    C.Get("BOARD")
    M.Advance(0.5)
    H.eq(H.countIntents(M, "GET"), 0, "GET held back")
    H.hello(M)
    M.Advance(0.3)
    local found = false
    for _, it in ipairs(H.intents(M)) do
        if it.op == "GET" and it.payload:find("BOARD", 1, true) then found = true end
    end
    H.ok(found, "held GET sent after HELLO")
    H.ok(C.Send("QLEAVE"), "intents allowed once connected")
end)

------------------------------------------------------------------------------------------------------
-- Handshake
------------------------------------------------------------------------------------------------------
test("HELLO reply sets the clock offset and requests the base topics", function(M, ns)
    M.Advance(1)
    H.hello(M)
    H.ok(ns.Comm.ready)
    H.eq(ns.Comm.clockOffset, M.epoch + 5 - M.env.time())
    M.Advance(0.3)
    local get = H.lastIntent(M, "GET")
    H.ok(get, "GET after HELLO")
    for _, t in ipairs({ "WEEK", "ERA", "TASKS", "KEY", "QUEUE" }) do
        H.contains(get.payload, t)
    end
end)

test("HELLO is retried while the server does not answer", function(M, ns)
    M.Advance(0.5)
    H.eq(H.countIntents(M, "HELLO"), 1)
    M.Advance(11)
    H.eq(H.countIntents(M, "HELLO"), 2)
    M.Advance(31)
    H.eq(H.countIntents(M, "HELLO"), 3)
    H.hello(M)
    M.Advance(200)
    H.eq(H.countIntents(M, "HELLO"), 3, "no retry after the answer")
end)

test("a server that needs a newer protocol blocks all sends", function(M, ns)
    local outdated = false
    ns.On("OUTDATED", function() outdated = true end)
    H.hello(M, { [1] = 3, [2] = 2 })
    H.ok(outdated and ns.Comm.blocked)
    M.Advance(2)
    local n = #M.sent
    H.eq(ns.Comm.Send("QLEAVE"), false)
    M.Advance(2)
    H.eq(#M.sent, n, "nothing sent")
    H.send(M, "WEEK", { { 1, 4 } })
    H.eq(ns.S.week, nil, "pushes ignored")
end)
