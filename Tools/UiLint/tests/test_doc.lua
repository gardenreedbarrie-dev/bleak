-- docs/BleakholdProtocol.md must match the client: every example frame parses, every op is documented.
local DOC = repo .. "/docs/BleakholdProtocol.md"

local function docLines(prefix)
    local text = assert(host_readfile(DOC), "docs/BleakholdProtocol.md missing")
    local out = {}
    for line in text:gmatch("[^\n]+") do
        local body = line:match("^" .. prefix .. " (.+)$")
        if body then out[#out + 1] = body end
    end
    return out, text
end

test("every S> example in the protocol document is accepted by the client", function(M, ns)
    local frames = docLines("S>")
    H.ok(#frames >= 25, "examples found: " .. #frames)
    for _, body in ipairs(frames) do
        local before = ns.Comm.stats.framesIn
        local dropsBefore = 0
        for _, v in pairs(ns.Comm.stats.dropped) do dropsBefore = dropsBefore + v end
        local unknownBefore = ns.Comm.stats.unknown
        H.ok(#body <= 1000, "example within 1000 bytes")
        H.deliver(M, body)
        local drops = 0
        for _, v in pairs(ns.Comm.stats.dropped) do drops = drops + v end
        H.eq(drops, dropsBefore, "example dropped: " .. body)
        H.eq(ns.Comm.stats.unknown, unknownBefore, "unknown op in example: " .. body)
        H.eq(ns.Comm.stats.gaps, 0, "revision gap in example: " .. body)
    end
    -- the examples leave a sensible state behind
    H.eq(ns.S.week.coins, 2140)
    H.eq(ns.S.tasks.byUid[102].state, 1)
    H.eq(#ns.S.board.dungeons, 3)
    H.eq(ns.S.queue.members[2].name, "Brenna")
    H.eq(ns.S.mplus.result.newLevel, 9)
    H.eq(ns.S.lidx[16866].collected, true)
    H.eq(ns.S.lb.K.rows[1].members[5].name, "Eamon")
    H.eq(ns.DefName("A", 3), "Bolstering")
    H.eq(ns.Def("A", 3).text, "When a non-boss enemy dies, its allies nearby grow stronger.")
end)

test("every C> example is a valid intent the client itself would encode", function(M, ns)
    local frames = docLines("C>")
    H.ok(#frames >= 15)
    local seen = {}
    for _, body in ipairs(frames) do
        H.ok(#body <= 251, "within 251 bytes")
        local fr = ns.Comm.ParseFrameOut(body)
        H.ok(fr, "frame: " .. body)
        seen[fr.op] = true
        local recs = ns.Comm.SplitRecords(fr.payload)
        local args = {}
        if fr.op == "GET" then
            for i, r in ipairs(recs) do
                local rec = { r[1] }
                for k = 2, #r do rec[k] = tonumber(r[k]) end
                args[i] = rec
            end
        else
            for i, f in ipairs(recs[1] or {}) do
                args[i] = tonumber(f) or f
            end
        end
        local payload, err = ns.Comm.EncodeIntent(fr.op, unpack(args))
        H.ok(payload, "client accepts example " .. body .. " (" .. tostring(err) .. ")")
        H.eq(payload, fr.payload, "same encoding as the client")
    end
    for op in pairs(ns.Comm.INTENTS) do
        H.ok(seen[op], "intent " .. op .. " has an example")
    end
end)

test("every op the client handles or sends is documented", function(M, ns)
    local _, text = docLines("S>")
    for op in pairs(ns.Comm.handlers) do
        H.ok(text:find("`" .. op .. "`", 1, true) or text:find("### " .. op, 1, true), "S2C op " .. op .. " documented")
    end
    for op in pairs(ns.Comm.INTENTS) do
        H.ok(text:find("| `" .. op .. "` |", 1, true), "intent " .. op .. " in the intent table")
    end
    for topic in pairs(ns.Comm.TOPICS) do
        H.ok(text:find("`" .. topic .. "`", 1, true), "GET topic " .. topic .. " documented")
    end
end)
