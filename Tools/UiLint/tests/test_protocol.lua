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

test("HELLO names the addon's optional parts (caps) only when it has some", function(M, ns)
    local C = ns.Comm
    M.Advance(0.5)
    local hello = H.lastIntent(M, "HELLO")
    H.ok(hello, "HELLO on entering the world")
    H.eq(#hello.fields, 4, "the café's UI is not built: no caps field, as an older server expects")
    H.eq(C.clientCaps, 0)
    H.eq(C.EncodeIntent("HELLO", 1, "1.0.0", 0, "enUS", C.CAPS.CAFE_UI), "1,1.0.0,0,enUS,1")
    H.eq(C.EncodeIntent("HELLO", 1, "1.0.0", 0, "enUS", 1, 1), nil, "one caps field at most")
    -- the café's UI sets its bit; the next HELLO (login or /reload) carries it
    C.clientCaps = C.CAPS.CAFE_UI
    M.Advance(6)
    local before = H.countIntents(M, "HELLO")
    C.SendHello()
    M.Advance(0.5)
    H.eq(H.countIntents(M, "HELLO"), before + 1)
    hello = H.lastIntent(M, "HELLO")
    H.eq(#hello.fields, 5)
    H.eq(hello.fields[5], "1", "caps bit 1: the café's UI")
    C.clientCaps = 0
end)

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

------------------------------------------------------------------------------------------------------
-- Bleakhold Royale (section 17): ROYS fields 25-27, the drop's times
------------------------------------------------------------------------------------------------------
-- A ROYS of a player falling from the drop (phase 2, me 1): fields 1-24, then `drop` as fields 25 on; `over` replaces
-- fields by index (nil-free: "" is an empty field).
local function dropRoys(M, ns, drop, over)
    local r = { 7001, 2, 20000, 24, 24, 1, 0, "", 104, 96, 1, -267, -267, 1080, -150, -310, 520, 119800, 289800, 0, "",
        104, 96, 6 }
    for i, v in ipairs(drop or {}) do r[24 + i] = v end
    for k, v in pairs(over or {}) do r[k] = v end
    H.send(M, "ROYS", { r })
    return ns.S.royale
end

test("ROYS fields 25-27: the drop's times, counted from the moment the ROYS arrives", function(M, ns)
    H.hello(M, { [6] = 4096 })
    M.Advance(0.3)
    -- the start gun: 8 s of free fall, then 12 s under the parachute
    local m = dropRoys(M, ns, { 8000, 20000, 8000 })
    H.eq(m.me, 1); H.eq(m.stages, 6, "field 24 before them")
    H.eq(m.fallMsLeft, 8000); H.eq(m.landMsLeft, 20000); H.eq(m.fallMs, 8000)
    H.eq(m.recvAt, M.env.GetTime())
    M.Advance(3)
    H.ok(math.abs(ns.RoyaleLeft(m.fallMsLeft, m.recvAt) - 5) < 1e-6, "5 s of free fall left after 3 s")
    H.ok(math.abs(ns.RoyaleLeft(m.landMsLeft, m.recvAt) - 17) < 1e-6, "17 s to the touchdown")
    -- the parachute opened by itself: fallMsLeft 0, not empty
    m = dropRoys(M, ns, { 0, 12000, 8000 }, { [3] = 12000, [18] = 111800, [19] = 281800 })
    H.eq(m.fallMsLeft, 0); H.eq(m.landMsLeft, 12000); H.eq(m.fallMs, 8000)
    -- the document lists them as fields 25-27, with these two ROYS as its example
    local doc = assert(host_readfile(repo .. "/docs/BleakholdProtocol.md"))
    local list = doc:match("\n### ROYS[^\n]*\n\n`(matchId, [^`]+)`")
    H.ok(list, "the ROYS field list")
    local names = {}
    for name in list:gmatch("[^, ]+") do names[#names + 1] = name end
    H.eq(#names, 27); H.eq(names[24], "stages")
    H.eq(names[25], "fallMsLeft"); H.eq(names[26], "landMsLeft"); H.eq(names[27], "fallMs")
    H.contains(doc, "`...,6,8000,20000,8000`"); H.contains(doc, "`...,6,0,12000,8000`")
end)

test("ROYS of an older server (23 or 24 fields) parses as before, with no drop times", function(M, ns)
    H.hello(M, { [6] = 4096 })
    M.Advance(0.3)
    local m = dropRoys(M, ns)
    H.eq(m.me, 1); H.eq(m.stages, 6); H.eq(m.pinX, 104); H.eq(m.shrinkEndMs, 289800)
    H.eq(m.fallMsLeft, nil); H.eq(m.landMsLeft, nil); H.eq(m.fallMs, nil)
    local r = { 7001, 2, 20000, 24, 24, 1, 0, "", 104, 96, 1, -267, -267, 1080, -150, -310, 520, 119800, 289800, 0, "",
        104, 96 }
    H.send(M, "ROYS", { r })
    m = ns.S.royale
    H.eq(m.stages, nil); H.eq(m.myY, 96); H.eq(m.fallMsLeft, nil); H.eq(m.fallMs, nil)
    -- field 24 empty, the drop's times after it
    m = dropRoys(M, ns, { 7000, 19000, 8000 }, { [24] = "" })
    H.eq(m.stages, nil); H.eq(m.fallMsLeft, 7000); H.eq(m.landMsLeft, 19000); H.eq(m.fallMs, 8000)
end)

test("ROYS drop times: only while falling, all three or none, never garbage", function(M, ns)
    H.hello(M, { [6] = 4096 })
    M.Advance(0.3)
    -- landed (me 2) or in the lobby (me 0): whatever comes in fields 25-27 is not a drop
    local m = dropRoys(M, ns, { 8000, 20000, 8000 }, { [3] = 0, [6] = 2 })
    H.eq(m.me, 2); H.eq(m.fallMsLeft, nil); H.eq(m.landMsLeft, nil); H.eq(m.fallMs, nil)
    m = dropRoys(M, ns, { 8000, 20000, 8000 }, { [2] = 1, [6] = 0 })
    H.eq(m.me, 0); H.eq(m.fallMsLeft, nil)
    -- one of the three missing: none of them
    for _, drop in ipairs({ { "", 20000, 8000 }, { 8000, "", 8000 }, { 8000, 20000, "" }, { 8000, 20000 } }) do
        m = dropRoys(M, ns, drop)
        H.eq(m.fallMsLeft, nil); H.eq(m.landMsLeft, nil); H.eq(m.fallMs, nil)
        H.eq(m.me, 1, "the rest of the ROYS still counts")
    end
    -- garbage numbers are empty fields
    for _, bad in ipairs({ "abc", "1e4", "8000.5", "0x10", " 8000", "9999999999999999" }) do
        m = dropRoys(M, ns, { bad, 20000, 8000 })
        H.eq(m.fallMsLeft, nil, "fallMsLeft " .. bad); H.eq(m.landMsLeft, nil)
    end
    -- 0 to a day, like every Royale time
    m = dropRoys(M, ns, { -5, 99999999999, 8000 })
    H.eq(m.fallMsLeft, 0); H.eq(m.landMsLeft, 86400000)
    -- the touchdown never comes before the parachute opens
    m = dropRoys(M, ns, { 8000, 5000, 8000 })
    H.eq(m.fallMsLeft, 8000); H.eq(m.landMsLeft, 8000)
    -- a later server's field 28 is ignored
    m = dropRoys(M, ns, { 6000, 18000, 8000, 42 })
    H.eq(m.fallMsLeft, 6000); H.eq(m.landMsLeft, 18000); H.eq(m.fallMs, 8000)
end)

------------------------------------------------------------------------------------------------------
-- Bleakhold Royale (section 17): the storm beast's kinds, ROYV B A K F, ROYO X H and ROYK cause B
------------------------------------------------------------------------------------------------------
-- One "### " block of section 17 (to the next heading), and the one-letter codes it lists: the rows of its table, or
-- the codes of one of its list items.
local function royaleDoc(heading)
    local doc = assert(host_readfile(repo .. "/docs/BleakholdProtocol.md"))
    return assert(doc:match("\n### " .. heading .. "[^\n]*\n(.-)\n#"), heading)
end

local function letters(text, pattern)
    local out = {}
    for c in text:gmatch(pattern) do out[#out + 1] = c end
    return table.concat(out)
end

test("ROYV B A K F: the storm beast stirs at a place, wakes, is slain or flees", function(M, ns)
    H.hello(M, { [6] = 4096 })
    M.Advance(0.3)
    local seen = {}
    ns.On("ROYALE_EVENT", function(e) seen[#seen + 1] = e.kind end)
    H.send(M, "ROYV", { { "B", 0, 60, -420, 30000, "Crow's Rise" } })
    local e = ns.S.royaleEvent
    H.eq(e.kind, "B"); H.eq(e.value, 0); H.eq(e.x, 60); H.eq(e.y, -420); H.eq(e.msLeft, 30000)
    H.eq(e.name, "Crow's Rise"); H.eq(e.recvAt, M.env.GetTime())
    M.Advance(12)
    H.ok(math.abs(ns.RoyaleLeft(e.msLeft, e.recvAt) - 18) < 1e-6, "it wakes in 18 s, 12 s later")
    -- B names a place: at most 40 bytes, as in ROYM; K names a character: 48
    H.send(M, "ROYV", { { "B", 0, 60, -420, 30000, string.rep("p", 60) } })
    H.eq(#ns.S.royaleEvent.name, 40)
    H.send(M, "ROYV", { { "A", 0, 60, -420 } })
    e = ns.S.royaleEvent
    H.eq(e.kind, "A"); H.eq(e.x, 60); H.eq(e.msLeft, nil); H.eq(e.name, nil)
    H.send(M, "ROYV", { { "K", 0, 60, -420, "", "Aldric Stormwind" } })
    H.eq(ns.S.royaleEvent.kind, "K"); H.eq(ns.S.royaleEvent.name, "Aldric Stormwind")
    H.send(M, "ROYV", { { "K", 0, 60, -420, "", string.rep("n", 60) } })
    H.eq(#ns.S.royaleEvent.name, 48)
    H.send(M, "ROYV", { { "F", 0, 60, -420 } })
    H.eq(ns.S.royaleEvent.kind, "F"); H.eq(ns.S.royaleEvent.y, -420)
    -- a kind this client does not know (a later server's), two letters, lower case: ignored, nothing changes
    for _, bad in ipairs({ "Z", "BX", "KA", "b", "" }) do
        H.send(M, "ROYV", { { bad, 0, 1, 2, 3000, "x" } })
    end
    H.eq(ns.S.royaleEvent.kind, "F"); H.eq(ns.S.royaleEvent.x, 60)
    H.eq(table.concat(seen, ""), "BBAKKF")
end)

test("ROYO X and H: the storm beast with its health in percent, clamped to 0-100, and its hoard", function(M, ns)
    H.hello(M, { [6] = 4096 })
    M.Advance(0.3)
    H.send(M, "ROYO", { { 7001, 1 }, { 30, "X", 100, 60, -420, 3, 30000 }, { 31, "H", 0, 62, -418, 1 },
        { 3, "B", 2, 120, 80, 1 } })
    local o = ns.S.royaleObjects
    H.eq(#o.list, 3)
    local x, h = o.byId[30], o.byId[31]
    H.eq(x.kind, "X"); H.eq(x.subtype, 100); H.eq(x.state, 3); H.eq(x.msLeft, 30000); H.eq(x.x, 60); H.eq(x.y, -420)
    H.eq(h.kind, "H"); H.eq(h.subtype, 0); H.eq(h.state, 1); H.eq(h.msLeft, nil)
    H.eq(o.byId[3].subtype, 2, "a buff orb keeps its buff")
    -- awake, then hurt: changes for the beast alone; its health is clamped to 0-100, garbage is 0
    for _, c in ipairs({ { 57, 57 }, { 0, 0 }, { 101, 100 }, { 4000000000, 100 }, { -5, 0 }, { "abc", 0 },
        { "57.5", 0 }, { "", 0 }, { 100, 100 } }) do
        H.send(M, "ROYO", { { 7001, 0 }, { 30, "X", c[1], 60, -420, 1 } })
        H.eq(ns.S.royaleObjects.byId[30].subtype, c[2], "health " .. tostring(c[1]))
    end
    x = ns.S.royaleObjects.byId[30]
    H.eq(x, o.byId[30], "updated in place"); H.eq(x.state, 1); H.eq(x.msLeft, nil, "awake: no time left")
    -- slain: the beast gone (0), its hoard opened (4); the hoard never has a subtype, whatever is sent
    H.send(M, "ROYO", { { 7001, 0 }, { 30, "X", 0, 60, -420, 0 }, { 31, "H", 9, 62, -418, 4 } })
    H.eq(x.state, 0); H.eq(x.subtype, 0); H.eq(h.state, 4); H.eq(h.subtype, 0)
    -- the other kinds keep their rules: a supply drop has no subtype, a buff orb at most 3
    H.send(M, "ROYO", { { 7001, 0 }, { 20, "D", 77, -950, -250, 3, 20000 }, { 3, "B", 99, 120, 80, 2 } })
    H.eq(ns.S.royaleObjects.byId[20].subtype, 0); H.eq(ns.S.royaleObjects.byId[3].subtype, 3)
    -- kinds this client does not know are skipped; the others of the same ROYO still count
    H.send(M, "ROYO", { { 7001, 0 }, { 40, "Q", 1, 0, 0, 1 }, { 41, "XH", 50, 0, 0, 1 }, { 42, "x", 5, 0, 0, 1 },
        { 31, "H", 0, 62, -418, 0 } })
    o = ns.S.royaleObjects
    H.eq(#o.list, 4); H.eq(o.byId[40], nil); H.eq(o.byId[41], nil); H.eq(o.byId[42], nil); H.eq(h.state, 0)
end)

test("ROYK cause B: killed by the storm beast itself (class 0, no tally) or with a player's credit", function(M, ns)
    H.hello(M, { [6] = 4096 })
    M.Advance(0.3)
    local function last() return ns.S.royaleFeed[#ns.S.royaleFeed] end
    H.send(M, "ROYK", { { "Thundermaw", 0, "Ysolde", 5, "B", 21 } })
    local k = last()
    H.eq(k.killer, "Thundermaw"); H.eq(k.killerClassId, 0); H.eq(k.victim, "Ysolde"); H.eq(k.cause, "B")
    H.eq(k.aliveAfter, 21); H.eq(k.byBoss, true); H.eq(k.killerKills, nil); H.eq(ns.S.royaleKills.Thundermaw, nil)
    -- a tally sent along is not the beast's either
    H.send(M, "ROYK", { { "Thundermaw", 0, "Corin", 11, "B", 20, 3 } })
    H.eq(last().byBoss, true); H.eq(last().killerKills, nil); H.eq(ns.S.royaleKills.Thundermaw, nil)
    -- a player credited for it (one may even be called Thundermaw): their elimination and tally count
    H.send(M, "ROYK", { { "Aldric", 1, "Brenna", 8, "B", 19, 4 } })
    H.eq(last().cause, "B"); H.eq(last().byBoss, nil); H.eq(ns.S.royaleKills.Aldric, 4)
    H.send(M, "ROYK", { { "Thundermaw", 4, "Dalia", 11, "B", 18, 1 } })
    H.eq(last().byBoss, nil); H.eq(ns.S.royaleKills.Thundermaw, 1)
    -- class 0 with another cause is not the beast
    H.send(M, "ROYK", { { "Garrick", 0, "Erin", 2, "P", 17, 2 } })
    H.eq(last().byBoss, nil); H.eq(last().killerKills, 2)
    -- causes this client does not know show as a player's kill
    for _, bad in ipairs({ "Z", "BX", "b", "" }) do
        H.send(M, "ROYK", { { "Aldric", 1, "Brenna", 8, bad, 16, 5 } })
        H.eq(last().cause, "P", "cause " .. bad); H.eq(last().byBoss, nil)
    end
end)

test("the client takes exactly the ROYV, ROYO and ROYK codes that section 17 lists, the storm beast's included",
    function(M, ns)
    H.hello(M, { [6] = 4096 })
    M.Advance(0.3)
    local events = letters(royaleDoc("ROYV"), "\n| `(%u)` |")
    local objects = letters(assert(royaleDoc("ROYO"):match("\n%- `kind`: (.-)`subtype`")), "`(%u)` ")
    local causes = letters(assert(royaleDoc("ROYK"):match("\n%- `cause`: (.-)\n%- ")), "`(%u)` ")
    H.eq(events, "RSDLONWBAKF"); H.eq(objects, "SBDXH"); H.eq(causes, "PSFLAB")
    local got = {}
    ns.On("ROYALE_EVENT", function(e) got[#got + 1] = e.kind end)
    local recs = { { 7001, 1 } }
    for i = 1, 26 do
        local c = string.char(64 + i)
        H.send(M, "ROYV", { { c, 0, 1, 2 } })
        recs[#recs + 1] = { i, c, 0, 0, 0, 1 }
        H.send(M, "ROYK", { { "Aldric", 1, "Brenna", 8, c, 20 } })
        local cause = ns.S.royaleFeed[#ns.S.royaleFeed].cause
        H.eq(cause, causes:find(c, 1, true) and c or "P", "ROYK cause " .. c)
    end
    -- in alphabetical order, as they were sent
    local alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    H.eq(table.concat(got, ""), letters(alphabet, "[" .. events .. "]"), "ROYV kinds taken")
    H.send(M, "ROYO", recs)
    local kinds = {}
    for _, o in ipairs(ns.S.royaleObjects.list) do kinds[#kinds + 1] = o.kind end
    H.eq(table.concat(kinds, ""), letters(alphabet, "[" .. objects .. "]"), "ROYO kinds taken")
end)
