-- mod-bleakhold-ui: capture every intent the real addon sends (through SendAddonMessage of the WoW mock),
-- by clicking every button of every window and by sending each op through the client's own encoder
-- (Comm.Send) with edge values. Each message is printed as "BHC <tab> time <tab> body" for the C++
-- parser test (tests/cpp/bh_intents.cpp).
--
-- Run by the repository's Tools/UiLint/testrunner.lua (see ../run_tests.sh).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

-- Click Bleakhold Royale's island map at pixel (px, py) from its top-left corner, given in a 512-unit picture (the
-- canvas is RoyaleMap.lua's MP.SIZE units across), so the same world point is clicked whatever the canvas size.
local function clickMap(M, ns, px, py)
    local canvas = ns.RoyaleMap.canvas
    local sc = canvas:GetEffectiveScale()
    local k = ns.RoyaleMap.SIZE / 512
    M.cursorX = (canvas:GetLeft() + px * k) * sc
    M.cursorY = (canvas:GetTop() - py * k) * sc
    M.Fire(canvas, "OnMouseUp", "LeftButton")
end

local function clickAll(M, root)
    for _, b in ipairs(M.Clickables(root)) do
        if b:IsVisible() and b:IsEnabled() and b.__scripts.OnClick then
            b:Click()
            local d = M.env.BleakholdDialog
            if d and d:IsShown() and d.ok:IsShown() then
                d.ok:Click()
            end
            M.Advance(0.2)
        end
    end
end

test("every intent the addon can send, captured for the C++ parser", function(M, ns)
    local C = ns.Comm
    -- camping, glide, field repair, Bleakhold Royale, War Mode and World PvP, arena seasons, the café
    FX.connect(M, H, { [6] = 512 + 1024 + 2048 + 4096 + 16384 + 32768 + 65536 + 131072 })
    FX.all(M, H)

    -- the windows' own buttons (the paths players use)
    for _, k in ipairs({ "tasks", "dungeons", "keys", "rift" }) do
        ns.UI.Open(k)
        M.Advance(0.3)
        clickAll(M, ns.Activities.pages[k])
    end
    ns.Dungeons.selected = 389
    ns.UI.Open("dungeons")
    clickAll(M, ns.Dungeons.queue)
    H.send(M, "QUEUE", FX.examples(M).QUEUE)
    clickAll(M, ns.Dungeons.queue)
    for _, k in ipairs({ "collections", "season", "leaderboards" }) do
        ns.UI.Open(k)
        M.Advance(0.3)
        local frameName = ({ collections = "BleakholdCollectionsFrame", season = "BleakholdSeasonFrame", leaderboards = "BleakholdLeaderboardsFrame" })[k]
        clickAll(M, ns.UI.windows[frameName].content)
    end
    -- the Arena page (the 1v1 queue: QJOIN A, then QLEAVE once queued) and the Arena leaderboard (LBQ A)
    H.send(M, "ARENA", FX.examples(M).ARENA)
    M.Advance(2.1)
    ns.UI.Open("arena")
    M.Advance(1.2)
    clickAll(M, ns.Arena.page)
    M.Advance(2.1)
    H.send(M, "QUEUE", { { 50, 1, "A", 1, 1, 1, 3, "" } })
    clickAll(M, ns.Arena.page)
    M.Advance(2.1)
    ns.UI.Open("leaderboards-arena")
    M.Advance(1.2)
    clickAll(M, ns.UI.windows.BleakholdLeaderboardsFrame.content)
    M.Advance(10)

    -- every op through the client's encoder, with edge values
    local sends = {
        { "PING", 0 }, { "PING", 2147483647 },
        { "TCLAIM", 1 }, { "TCLAIM", 2147483647 }, { "TREROLL", 101 },
        { "QJOIN", "D", 389, 0, 1, 1 }, { "QJOIN", "D", 602, 3, 7, 5 }, { "QJOIN", "R", 0, 0, 4, 5 }, { "QJOIN", "R", 0, 0, 2, 1 },
        { "QLEAVE" }, { "QREPLY", 77, 1 }, { "QREPLY", 2147483647, 0 },
        { "KMODE", 0 }, { "KMODE", 1 }, { "KMODE", 2 }, { "KSTART" }, { "KCANCEL" },
        { "BCLAIM", 55 }, { "WEHANDIN" }, { "OUTFIT", 201 },
        { "LBQ", "K", 1, 0, 0, 1 }, { "LBQ", "R", 1, 602, 11, 999 }, { "LBQ", "E", 0, 0, 0, 3 }, { "LBQ", "F", 1, 0, 0, 1 },
        -- arena seasons (section 20): the arena board one bracket at a time, the 1v1 queue rated and skirmish
        { "LBQ", "A", 0, 3, 0, 1 }, { "LBQ", "A", 2147483647, 1, 11, 999 }, { "LBQ", "A", 1, 5, 0, 2 },
        { "QJOIN", "A", 1, 1, 4, 1 }, { "QJOIN", "A", 1, 0, 7, 1 },
    }
    for _, s in ipairs(sends) do
        H.eq(C.Send(unpack(s)), true, "the client sends " .. s[1])
        M.Advance(2.1)
    end
    -- EMOJI as the addon spaces it (3.25 s), so the replay sees both accepted by the 2.5 s cooldown
    H.eq(C.Send("EMOJI", 0), true, "the client sends EMOJI 0")
    M.Advance(3.3)
    H.eq(C.Send("EMOJI", 255), true, "the client sends EMOJI 255")
    M.Advance(3.3)
    -- DANCE as the addon spaces it (1.25 s), against the 1 s cooldown
    H.eq(C.Send("DANCE", 0), true, "the client sends DANCE 0")
    M.Advance(1.3)
    H.eq(C.Send("DANCE", 1023), true, "the client sends DANCE 1023")
    M.Advance(1.3)
    -- CASEOPEN as the addon spaces it (1.25 s, after each answer), against the 1 s cooldown
    H.eq(C.Send("CASEOPEN", 990001, 0), true, "the client sends CASEOPEN")
    M.Advance(1.3)
    H.eq(C.Send("CASEOPEN", 2147483647, 2147483647), true, "the client sends CASEOPEN with the largest id and nonce")
    M.Advance(1.3)
    -- camping (section 16) from the real UI, as the addon spaces it: CAMP and GLIDE 1.25 s apart (the server
    -- allows one a second and drops the same payload within a second), REPAIR 2.25 s (one per two seconds)
    M.env.BleakholdOrb_camp:Click()                                        -- Make camp orb: CAMP M
    M.Advance(1.3)
    H.send(M, "CAMPST", { { "R", 60, 900, 1, 900, 0, 0, { { 164, 2, 1 } }, { { 185, 1 }, { 356, 3 } }, 0, 1, 0 } })
    M.Advance(0.3)
    local camp = M.env.BleakholdCampFrame
    H.ok(camp:IsShown(), "camp frame shown at the fire")
    camp.place[1]:Click()                                                  -- Place Cookpot: CAMP O,185
    M.Advance(1.3)
    camp.place[2]:Click()                                                  -- Place Rowboat: CAMP O,356
    M.Advance(1.3)
    camp.repairBtn:Click()                                                 -- Repair: REPAIR
    M.Advance(2.3)
    camp.packBtn:Click()                                                   -- Pack up: CAMP P
    M.Advance(1.3)
    M.env.BleakholdGlide()                                                 -- the Glide key binding: GLIDE
    M.Advance(1.3)
    M.env.SlashCmdList.BLEAKHOLD("repair")                                 -- /bh repair
    M.Advance(2.3)
    H.eq(C.Send("CAMP", "O", 1), true, "the client sends CAMP O with the smallest skill line")
    M.Advance(1.3)
    H.eq(C.Send("CAMP", "O", 2147483647), true, "the client sends CAMP O with the largest skill line")
    M.Advance(1.3)
    H.eq(C.Send("CAMP", "M,1"), false, "a skill line only with O")
    H.eq(C.Send("CAMP", "M", 164), false, "a skill line only with O")
    H.eq(C.Send("CAMP", "O"), false, "O needs its skill line")
    H.eq(C.Send("CAMP", "O", 0), false, "skill lines start at 1")
    H.eq(C.Send("GLIDE", 1), false, "GLIDE has no field")
    local camps = {}
    for _, it in ipairs(H.intents(M)) do
        if it.op == "CAMP" then camps[#camps + 1] = it.payload end
    end
    H.eq(table.concat(camps, " "), "M O,185 O,356 P O,1 O,2147483647", "the CAMP intents the UI sent")
    H.eq(H.countIntents(M, "GLIDE"), 1)
    H.eq(H.countIntents(M, "REPAIR"), 2)
    -- Bleakhold Royale (section 17) from the real UI, as the addon spaces it: the queue's intents 1.1 s apart (1 per
    -- second each), RDROP and RSPEC 0.55 s (one per 0.5 s), RDEPLOY 1.05 s (one per second)
    M.Advance(1.3)
    ns.UI.Open("royale")
    M.Advance(0.3)
    ns.Royale.page.join:Click()                                            -- Queue: QJOIN B,901,0,4,1
    M.Advance(1.3)
    H.send(M, "QUEUE", { { 900, 2, "B", 901, 0, 1, 95, "", 412, 15, 80, 80, 24, 20, 40, 0, 24, 1 } })
    M.env.BleakholdRoyaleReady.accept:Click()                              -- ready check: QREPLY 412,1
    M.Advance(1.3)
    H.send(M, "ROYM", { { 901, -1066, 533, -1066, 533, 455, 455, 32, 750, -267, -267 },
        { 1, "L", -266, -266, 88, "The Bleak Hold" } })
    local function roys(phase, me, watch)
        H.send(M, "ROYS", { { 7001, phase, 30000, 24, 24, me, 0, "", "", "", 0, -267, -267, 1080, "", "", "", "", "", 0,
            watch or "", 450, 452 } })
    end
    roys(0, 0)
    M.Advance(0.3)
    clickMap(M, ns, 100, 200)                                              -- landing pin: RDROP -92,221
    M.Advance(0.6)
    clickMap(M, ns, 500, 10)                                               -- RDROP 502,-1029
    M.Advance(0.6)
    roys(2, 1)
    M.Advance(0.6)
    ns.Royale.Deploy()                     -- RDEPLOY: R.Deploy stays for the protocol (no button or key sends it)
    M.Advance(1.1)
    roys(3, 3, "Aldric")
    M.Advance(0.3)
    local spec = M.env.BleakholdRoyaleSpectate
    -- RSPEC 0, 2, 1, 1 ("next" twice: two steps)
    for _, b in ipairs({ spec.killer, spec.prev, spec.next, spec.next }) do
        b:Click()
        M.Advance(0.6)
    end
    H.eq(C.Send("RDROP", -17067, 17067), true, "the client sends RDROP with the smallest x and the largest y")
    M.Advance(0.6)
    H.eq(C.Send("RDROP", 17067, -17067), true, "the client sends RDROP with the largest x and the smallest y")
    M.Advance(0.6)
    H.eq(C.Send("RSPEC", 2), true)
    M.Advance(0.6)
    H.eq(C.Send("RDEPLOY"), true)
    M.Advance(1.1)
    H.eq(C.Send("QJOIN", "B", 1, 0, 1, 1), true, "QJOIN B with the smallest mode id")
    M.Advance(1.1)
    H.eq(C.Send("RDROP", -17068, 0), false, "outside -17067..17067")
    H.eq(C.Send("RSPEC", 3), false, "dir 0..2")
    H.eq(C.Send("QJOIN", "B", 901, 1, 4, 1), false, "Royale: tier 0")
    H.eq(C.Send("QJOIN", "B", 901, 0, 4, 2), false, "Royale: size 1")
    H.eq(C.Send("QJOIN", "B", 0, 0, 4, 1), false, "Royale: a mode id above 0")
    H.eq(C.Send("QJOIN", "A", 2, 1, 4, 1), false, "arena: activity 1")
    H.eq(C.Send("QJOIN", "A", 1, 2, 4, 1), false, "arena: tier 0 or 1")
    H.eq(C.Send("QJOIN", "A", 1, 1, 4, 2), false, "arena: solo")
    H.eq(C.Send("LBQ", "A", 0, 0, 0, 1), false, "arena board: a bracket, never all")
    H.eq(C.Send("LBQ", "A", 0, 4, 0, 1), false, "arena board: 1, 2, 3 or 5")
    local royale = {}
    for _, it in ipairs(H.intents(M)) do
        if it.op == "RDROP" or it.op == "RSPEC" or it.op == "RDEPLOY" then
            royale[#royale + 1] = it.op .. " " .. it.payload
        end
    end
    H.eq(table.concat(royale, "|"), "RDROP -92,221|RDROP 502,-1029|RDEPLOY |RSPEC 0|RSPEC 2|RSPEC 1|RSPEC 1|"
        .. "RDROP -17067,17067|RDROP 17067,-17067|RSPEC 2|RDEPLOY ", "the Royale intents the UI sent")
    -- War Mode (section 19) from the real UI, as the addon spaces it: one WARMODE per 2.1 s (the server allows one per
    -- 2 s and drops the same `on` within a second); the page's button asks for a confirmation first
    M.env.IsResting = function() return 1 end
    local function wmst(on)
        H.send(M, "WMST", { { on, 0, "", 20, 0, 10, 0, 8, "H", 31, 22, 0, 0, 0, 0, 0, 3720, 0, 60, 7, 118, 96 } })
    end
    wmst(0)
    ns.UI.Open("warmode")
    M.Advance(0.3)
    ns.WarMode.page.toggle:Click()                                         -- Turn War Mode on: WARMODE 1
    M.env.BleakholdDialog.ok:Click()
    M.Advance(2.2)
    wmst(1)
    M.Advance(0.3)
    ns.WarMode.page.toggle:Click()                                         -- Turn War Mode off: WARMODE 0
    M.env.BleakholdDialog.ok:Click()
    M.Advance(2.2)
    M.env.SlashCmdList.BLEAKHOLD("warmode on")                             -- /bh warmode on: WARMODE 1
    M.Advance(2.2)
    H.eq(C.Send("WARMODE", 2), false, "on is 0 or 1")
    H.eq(C.Send("WARMODE"), false, "WARMODE needs its field")
    H.eq(C.Send("WARMODE", 1, 1), false, "one field only")
    H.eq(table.concat((function()
        local out = {}
        for _, it in ipairs(H.intents(M)) do
            if it.op == "WARMODE" then out[#out + 1] = it.payload end
        end
        return out
    end)(), " "), "1 0 1", "the WARMODE intents the UI sent")
    -- the café (section 21) through the client's encoder, with edge values, as the café's send gates space them:
    -- CSHIFT and CSTAFF 2.3 s apart (one per 2 s together), CTAKE 0.65 s (one per 0.5 s), CSTEP 0.3 s (one per 0.2 s),
    -- CREL 0.3 s (one per 0.1 s; at once), CORDER and CCANCEL 2.3 s (one per 2 s together). CTAKE, CSTEP and CREL
    -- are sent again with the same payload inside the server's 1 s duplicate window: never duplicates (section 8).
    M.Advance(2.3)
    local cafe = {
        { 2.3, "CSHIFT", 1, 1 }, { 0.65, "CTAKE", 0 }, { 0.65, "CTAKE", 0 }, { 0.65, "CTAKE", 2147483647 },
        { 0.3, "CSTEP", 1, 1, 1 }, { 0.3, "CSTEP", 1, 1, 1 }, { 0.3, "CSTEP", 2147483647, 12, 63 },
        { 0.3, "CREL", 1, 1, 0 }, { 0.3, "CREL", 1, 1, 0 }, { 0.3, "CREL", 2147483647, 12, 60000 },
        { 2.3, "CSHIFT", 255, 0 }, { 2.3, "CSTAFF", 1 }, { 2.3, "CSTAFF", 65535 },
        { 2.3, "CORDER", 1, 1, 0 }, { 2.3, "CORDER", 2, 201, 10 }, { 2.3, "CORDER", 1, 103, 25 },
        { 2.3, "CORDER", 255, 65535, 50 }, { 2.3, "CCANCEL", 1 }, { 2.3, "CCANCEL", 2147483647 },
        { 0.6, "LBQ", "C", 0, 1, 0, 1 }, { 0.6, "LBQ", "C", 2147483647, 2, 0, 999 },
    }
    local from = #M.sent + 1
    for _, s in ipairs(cafe) do
        H.eq(C.Send(unpack(s, 2)), true, "the client sends " .. s[2])
        M.Advance(s[1])
    end
    local sentCafe = {}
    for _, it in ipairs(H.intents(M, from)) do
        sentCafe[#sentCafe + 1] = it.op .. " " .. it.payload
    end
    H.eq(table.concat(sentCafe, "|"), "CSHIFT 1,1|CTAKE 0|CTAKE 0|CTAKE 2147483647|CSTEP 1,1,1|CSTEP 1,1,1|"
        .. "CSTEP 2147483647,12,63|CREL 1,1,0|CREL 1,1,0|CREL 2147483647,12,60000|CSHIFT 255,0|CSTAFF 1|CSTAFF 65535|"
        .. "CORDER 1,1,0|CORDER 2,201,10|CORDER 1,103,25|CORDER 255,65535,50|CCANCEL 1|CCANCEL 2147483647|"
        .. "LBQ C,0,1,0,1|LBQ C,2147483647,2,0,999", "the café intents went out, repeats included")
    -- every other op keeps the 0.5 s identical-intent check
    H.eq(C.Send("CSHIFT", 1, 1), true)
    H.eq(select(2, C.Send("CSHIFT", 1, 1)), "dedup", "a second CSHIFT within 0.5 s is sent once")
    M.Advance(2.3)
    -- CREL goes out at once, ahead of what waits for a token, and still takes a token
    M.Advance(3)
    from = #M.sent + 1
    for i = 1, 7 do
        H.eq(C.Send("PING", 900 + i), true)
    end
    H.eq(C.Send("CREL", 2, 3, 2380), true)
    local now = {}
    for _, it in ipairs(H.intents(M, from)) do now[#now + 1] = it.op .. " " .. it.payload end
    H.eq(table.concat(now, "|"), "PING 901|PING 902|PING 903|PING 904|PING 905|PING 906|CREL 2,3,2380",
        "the release overtook the seventh PING")
    M.Advance(0.3)
    H.eq(#H.intents(M, from), 7, "the queue waits for the token the release took")
    M.Advance(1)
    H.eq(#H.intents(M, from), 8, "then the seventh PING goes")
    M.Advance(2)
    -- outside the schemas: refused by the client itself
    H.eq(C.Send("CSHIFT", 0, 1), false, "a café id 1..255")
    H.eq(C.Send("CSHIFT", 1, 2), false, "on is 0 or 1")
    H.eq(C.Send("CTAKE", -1), false, "an order id 0..2147483647")
    H.eq(C.Send("CSTEP", 1, 13, 1), false, "steps 1..12")
    H.eq(C.Send("CSTEP", 1, 1, 64), false, "actions 1..63")
    H.eq(C.Send("CSTEP", 0, 1, 1), false, "ticket ids from 1")
    H.eq(C.Send("CREL", 1, 1, 60001), false, "clientMs 0..60000")
    H.eq(C.Send("CREL", 1, 1), false, "CREL needs clientMs")
    H.eq(C.Send("CORDER", 1, 103, 5), false, "a tip of 0, 10, 25 or 50")
    H.eq(C.Send("CORDER", 1, 103, 100), false, "a tip of 0, 10, 25 or 50")
    H.eq(C.Send("CORDER", 1, 0, 0), false, "recipes from 1")
    H.eq(C.Send("CCANCEL", 0), false, "order ids from 1")
    H.eq(C.Send("CSTAFF", 65536), false, "recipes up to 65535")
    H.eq(C.Send("LBQ", "C", 0, 0, 0, 1), false, "café board: a café, never all")
    H.eq(C.Send("LBQ", "C", 0, 3, 0, 1), false, "café board: café 1 or 2")
    H.eq(C.Get("CAFAT"), false, "CAFAT is pushed only")
    -- GET of every topic; the client batches one frame's requests (8 records at most per GET)
    for _, topic in ipairs({ "WEEK", "ERA", "TASKS", "KEY", "BOARD", "QUEUE", "COLL", "LIDX", "SEASON", "FIRSTS", "MPLUS", "RIFT" }) do
        C.Refresh(topic)
    end
    C.Refresh("SET", 1, 1)
    C.Refresh("SET", 7, 12)
    C.Refresh("DEF", 0)
    C.Refresh("CASES")
    C.Refresh("CASE", 990001)
    C.Refresh("CAMPST")
    C.Refresh("ROYS")
    C.Refresh("ROYM")
    C.Refresh("WMST")
    C.Refresh("WPZ")
    C.Refresh("WPMAP")
    C.Refresh("WANTED")
    C.Refresh("ARENA")
    for _, topic in ipairs({ "CAFE", "CAFST", "CAFQ", "CAFT", "CAFO", "CAFP", "CAFBF" }) do
        C.Refresh(topic)
    end
    C.Refresh("CAFM", 1)
    C.Refresh("CAFM", 2)
    C.Refresh("CAFM", 255)
    M.Advance(10)

    local ops, topics, n = {}, {}, 0
    for _, s in ipairs(M.sent) do
        if s.prefix == "BHc" then
            H.eq(s.channel, "WHISPER")
            H.eq(s.target, M.playerName)
            H.ok(not s.msg:find("[\r\n\t]"), "one line")
            print(string.format("BHC\t%.3f\t%s", s.t, s.msg))
            n = n + 1
            local op = s.msg:match("^%d+ (%u+) ")
            ops[op] = true
            if op == "GET" then
                for rec in (s.msg:match("^%S+ %S+ %S+ %S+ (.*)$") .. ";"):gmatch("([^;]*);") do
                    topics[rec:match("^(%u+)")] = true
                end
            end
        end
    end
    H.ok(n >= 40, "intents captured: " .. n)
    for op in pairs(C.INTENTS) do
        H.ok(ops[op], "captured " .. op)
    end
    for topic in pairs(C.TOPICS) do
        H.ok(topics[topic], "captured GET " .. topic)
    end
end)
