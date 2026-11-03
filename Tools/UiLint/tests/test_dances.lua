-- Bleakhold dances in the Animations tab: the catalogue (DanceData.lua), the Dance button and DANCE with its
-- cooldown, playing here only without a realm, the preview, the music marker, slash commands and wheel seeding.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local DANCE_BIT = { [6] = 128 }    -- HELLO feature bits: dances live

local function openTab(M, ns, filter)
    ns.UI.Open("collections")
    ns.Collections.ShowTab("animations")
    local A = ns.Animations
    if filter then
        A.tab.filter:SetValue(filter)
    end
    return A, A.tab
end

-- The id field of every DANCE sent to the server, joined with ",".
local function sentDances(M)
    local out = {}
    for _, it in ipairs(H.intents(M)) do
        if it.op == "DANCE" then
            out[#out + 1] = it.fields[1]
        end
    end
    return table.concat(out, ",")
end

local function printed(M, text)
    local n = 0
    for _, c in ipairs(M.chat) do
        if tostring(c.msg):find(text, 1, true) then
            n = n + 1
        end
    end
    return n
end

-- Bleakhold.exe's dance functions, recording what the addon asks of them.
local function fakeClient(M, opts)
    opts = opts or {}
    local log = { local_ = {}, stops = 0 }
    M.env.BleakholdDance_Status = function() return opts.status or "" end
    M.env.BleakholdDance_Info = function(id)
        for _, d in ipairs(M.env.BleakholdDanceTestData or {}) do
            if d.id == id then
                return d.key, d.seconds, d.bpm, opts.music and opts.music[d.key] or nil
            end
        end
        return nil
    end
    M.env.BleakholdDance_PlayLocal = function(id)
        log.local_[#log.local_ + 1] = id
        return true
    end
    M.env.BleakholdDance_StopLocal = function() log.stops = log.stops + 1 end
    M.env.BleakholdDance_RigStatus = function() return opts.rig or "" end
    return log
end

test("dances: catalogue, entries, names and slash commands", function(M, ns)
    local A, Data = ns.Animations, ns.Data
    local cats, keys, cmds = {}, {}, {}
    for _, c in ipairs(Data.danceCategories) do
        cats[c.key] = true
    end
    H.ok(#Data.dances >= 1 and #Data.dances <= 1024, "1..1024 dances")
    for i, d in ipairs(Data.dances) do
        H.eq(d.id, i - 1, "ids are 0..n-1")
        H.ok(not keys[d.key] and d.key:match("^[a-z][a-z0-9_]*$"), "unique key " .. d.key)
        keys[d.key] = true
        H.ok(not cmds[d.cmd] and d.cmd:match("^/[a-z][a-z0-9]+$"), "unique command " .. d.cmd)
        cmds[d.cmd] = true
        H.ok(cats[d.cat], d.key .. " is in a known category")
        local e = A.Get("dance:" .. d.key)
        H.ok(e and e.dance == d.id and e.name == d.name and e.cat == "dance", d.key .. " entry")
        H.eq(A.DanceByName(d.key), e, "by key")
        H.eq(A.DanceByName(d.name), e, "by name")
        H.eq(A.DanceByName(d.cmd:sub(2)), e, "by command")
        H.ok(M.env.SlashCmdList["BLEAKHOLDDANCE" .. string.upper(d.key)], d.cmd .. " is registered")
        H.eq(M.env["SLASH_BLEAKHOLDDANCE" .. string.upper(d.key) .. "1"], d.cmd)
    end
    H.eq(#A.danceCommands, #Data.dances, "every dance got its command")
    H.ok(A.DanceByName("  STRING   swing ") ~= nil and A.DanceByName("dance") == nil, "names, and no emotes")
    H.eq(#A.Filtered("", "dance"), #Data.dances + 1, "the Dances filter: the Bleakhold dances and the race's own")
end)

test("dances: Dance sends DANCE with its cooldown; busy waits again", function(M, ns)
    FX.connect(M, H, DANCE_BIT)
    local A, tab = openTab(M, ns, "dance")
    tab.entries[1]:Click("LeftButton")
    H.eq(A.selected.key, "dance:string_swing")
    H.eq(tab.right.play.label:GetText(), "Dance", "the button says Dance")
    tab.right.play:Click()
    H.eq(sentDances(M), "0", "DANCE 0 sent")
    tab.right.play:Click()
    H.eq(sentDances(M), "0", "the cooldown holds the second press")
    M.Advance(1.3)
    tab.entries[2]:Click("LeftButton")
    M.Fire(tab.entries[2], "OnDoubleClick", "LeftButton")
    H.eq(sentDances(M), "0,1", "double-click dances too")
    M.Advance(1.3)
    H.send(M, "ERR", { { "DANCE", "", "busy", "You are doing that too often." } })
    H.ok(A.danceReadyAt > M.now + 1.2, "busy: the whole cooldown again")
    M.env.SlashCmdList.BLEAKHOLDDANCEMECH_BOT()
    H.eq(sentDances(M), "0,1", "still waiting")
    M.Advance(1.3)
    M.env.SlashCmdList.BLEAKHOLDDANCEMECH_BOT()
    H.eq(sentDances(M), "0,1,5", "/mechbot sends DANCE 5")
    H.eq(printed(M, "Bleakhold.exe"), 1, "a stock game is told once that it cannot show dances")
    M.Advance(1.3)
    M.env.SlashCmdList.BLEAKHOLD("dance disco fever")
    H.eq(sentDances(M), "0,1,5,2", "/bh dance <name>")
    H.eq(printed(M, "Bleakhold.exe"), 1, "only once")
end)

test("dances: no realm, demo mode or dances off: here only, with a notice", function(M, ns)
    local log = fakeClient(M)
    local A = ns.Animations
    H.eq(A.SendDance("dance:twist_it"), true)
    H.eq(log.local_[1], 3, "danced here only")
    H.eq(sentDances(M), "", "nothing sent before the realm answered")
    H.eq(printed(M, "Dances need the Bleakhold server module"), 1, "a notice")
    FX.connect(M, H, { [6] = 64 })
    local _, tab = openTab(M, ns, "dance")
    tab.entries[1]:Click("LeftButton")
    H.eq(tab.right.hint:GetText(), "Dances are turned off on this realm.", "the hint says why")
    M.Advance(1.3)
    H.eq(A.SendDance("dance:string_swing"), true)
    H.eq(log.local_[2], 0)
    H.eq(sentDances(M), "", "no DANCE to a realm with dances off")
    M.env.BleakholdDance_PlayLocal = nil
    M.Advance(1.3)
    A.SendDance("dance:string_swing")
    H.eq(M.emotes[#M.emotes], "DANCE", "a stock game falls back to the race's own dance")
end)

test("dances: the preview plays the dance on the model in Bleakhold.exe", function(M, ns)
    fakeClient(M)
    local A, tab = openTab(M, ns, "dance")
    A.model.SetBleakholdDance = function(self, id)
        self.__dance = id
        return id and true or nil
    end
    tab.entries[3]:Click("LeftButton")
    H.eq(A.model.__dance, 2, "model:SetBleakholdDance(2)")
    H.eq(A.model.__sequence, 0, "the stance plays underneath")
    tab.filter:SetValue("emote")
    tab.entries[1]:Click("LeftButton")
    H.ok(A.model.__dance == nil, "an emote stops the dance")
    H.eq(A.model.__sequence, 67, "and plays its own sequence")
end)

test("dances: music marker, tempo and length", function(M, ns)
    M.env.BleakholdDanceTestData = ns.Data.dances
    fakeClient(M, { music = { running_man = true } })
    local A, tab = openTab(M, ns, "dance")
    H.eq(tab.entries[2].cmd:GetText(), "/runningman  with music", "the list marks dances with music")
    H.eq(tab.entries[1].cmd:GetText(), "/stringswing")
    tab.entries[2]:Click("LeftButton")
    local d = ns.Data.dances[2]
    H.contains(tab.right.cmd:GetText(), "with music")
    H.contains(tab.right.cmd:GetText(), string.format("%g BPM, %.1f s loop", d.bpm, d.seconds))
end)

test("dances: a wheel saved before dances gets them once, in free slots", function(M, ns)
    local A = ns.Animations
    ns.cdb.danceWheel = nil
    ns.cdb.wheel = { { "dance", "wave" }, { "salute" }, {}, { "sit" } }
    A.EnsureWheel()
    H.eq(A.WheelEntry(1, 1).key, "dance", "no slot is replaced")
    H.eq(A.WheelEntry(1, 3).key, "dance:string_swing", "the first free slots of page 1")
    H.eq(A.WheelEntry(1, 6).key, "dance:mech_bot")
    H.ok(ns.cdb.danceWheel, "remembered")
    A.SetWheelSlot(1, 3, nil)
    A.EnsureWheel()
    H.ok(A.WheelEntry(1, 3) == nil, "a dance taken off stays off")
end)

test("dances: /bh dance list, stop and debug", function(M, ns)
    local log = fakeClient(M, { rig = "missing key bones" })
    M.env.SlashCmdList.BLEAKHOLD("dance list")
    H.ok(printed(M, "/stringswing") >= 1 and printed(M, "/mechbot") >= 1, "the commands are listed")
    M.env.SlashCmdList.BLEAKHOLD("dance stop")
    H.eq(log.stops, 1)
    M.env.SlashCmdList.BLEAKHOLD("dance debug")
    H.eq(printed(M, "your model missing key bones"), 1, "debug names why the model cannot dance")
    M.env.SlashCmdList.BLEAKHOLD("dance nonsense")
    H.eq(printed(M, "usage: /bh dance"), 1)
end)
