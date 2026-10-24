-- mod-bleakhold-ui: capture every intent the real addon sends (through SendAddonMessage of the WoW mock),
-- by clicking every button of every window and by sending each op through the client's own encoder
-- (Comm.Send) with edge values. Each message is printed as "BHC <tab> time <tab> body" for the C++
-- parser test (tests/cpp/bh_intents.cpp).
--
-- Run by the repository's Tools/UiLint/testrunner.lua (see ../run_tests.sh).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

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
    FX.connect(M, H, { [6] = 512 + 1024 + 2048 })   -- camping, glide and field repair (the other windows need no bit)
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
