-- Server fixtures for tests: push a full, valid set of snapshots through the real receive path
-- (CHAT_MSG_ADDON -> Comm -> State), encoded by the test's own reference encoder.
local FX = {}

function FX.connect(M, H, extra)
    H.hello(M, extra)
    M.Advance(0.3)
end

function FX.all(M, H)
    local now = M.env.time()
    H.send(M, "WEEK", { { 1, 4, 1, 18, 2140, 5500, 1260 } })
    H.send(M, "ERA", { { 1, 7, 3, { 1, 3, 4 }, 1, 0 } })
    H.send(M, "TASKS", {
        { 1, 1, 500000, "G" },
        { 101, "D", 1, 0, 1, "C", 20, "", 0 },
        { 102, "D", 2, 14, 20, "I", 1, 40752, 0, "", "", "1 Emblem of Heroism" },
        { 103, "D", 3, 5, 5, "C", 20, "", 1 },
        { 201, "W", 4, 1, 3, "C", 150, "", 0 },
        { 202, "W", 5, 2, 2, "T", 0, "", 1, "", "", "Legacy Cache" },
    }, 90)
    H.send(M, "KEY", { { 1, 602, 8, { 1, 3, 4 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    H.send(M, "BOARD", {
        { 1, 1260, 55, 189, 2, "50 Shards", 1 },
        { 389, 1, 13, 18, 15, 900, 1, 2400, "Aldric", 0 },
        { 36, 1, 15, 21, 3, "", "", "", "", 0 },
        { 189, 2, 30, 40, 1, 1500, 0, 3100, "Brenna", 0 },
        { 602, 5, 77, 80, 1, "", "", "", "", 1 },
    })
    H.send(M, "QUEUE", { { 1, 0 } })
    H.send(M, "COLL", { { 1, 412, "", 0, 3771, 3, 48, { 3, 0, 0, 0, 0, 0, 0 }, { 8, 8, 5, 9, 5, 5, 8 } } })
    H.send(M, "SET", { { 1, 201, 1, "Battlegear of Might", 56, 0, { 16866, 16868, 16865, 16861, 16863, 16864, 16867, 16862 }, { 229, 329, 289, 429, 543 }, 58, 61, "Ragnaros", "" } })
    H.send(M, "LIDX", { { 1 }, { 16864, 1, 201, 1 }, { 16866, 1, 201, 0 } })
    H.send(M, "SEASON", {
        { 1, 1, 620, 1284, 1240, 2, 3, 260, "Breach the Greymane Wall", "Fill the bar together.", 3 },
        { "P", "Materials", 800 }, { "P", "Bosses and Echoes", 550 }, { "P", "Keys in time", 510 },
        { "R", 1, 1, "Earned" }, { "R", 2, 0, "7 / 20" },
    })
    H.send(M, "RIFT", { { 0, 0, "", "", "", "", 18, "", 42 } })
    H.send(M, "FIRSTS", { { "echo", "Echo of Ragnaros defeated", "Ironvow", now - 86400 } })
    H.send(M, "LB", {
        { "K", 1, 0, 0, 1, 3 },
        { 1, 602, 15, 300, now - 3600, { { "Aldric", 1 }, { "Brenna", 2 }, { "Corwin", 5 }, { "Dalia", 8 }, { "Eamon", 11 } } },
        { 2, 599, 14, 200, now - 7200, { { "Fenna", 3 } } },
        { 3, 575, 14, 100, now - 9000, { { "Garrick", 4 } } },
        { 4, 602, 13, 50, now - 9900, { { "Hesper", 6 } } },
    })
    H.send(M, "LBME", { { "K", 42, 12, 9, 602, 154, 580 } })
end

-- All S2C ops the client handles, with a valid example record set for each.
function FX.examples(M)
    local now = M.env.time()
    return {
        HELLO = { { 1, 1, now, 60, 7, 0, 1, now + 3600, now + 86400, "Bleakhold", "bleakhold.com" } },
        PONG = { { 5, now } },
        ERR = { { "TCLAIM", "1a", "not_claimable", "That task cannot be claimed yet." } },
        DEF = { { "D", 7 }, { 602, "Halls of Lightning", 5, 77, 80, { "General Bjarngrim", "Volkhan", "Ionar", "Loken" }, 1800 } },
        WEEK = { { 1, 4, 1, 18, 2140, 5500, 1260 } },
        ERA = { { 1, 7, 3, { 1, 3, 4 }, 1, 0 } },
        TASKS = { { 1, 1, 0, "G" }, { 101, "D", 1, 0, 1, "C", 20, "", 0 } },
        TASK = { { 2, 101, 1, 1 } },
        TOAST = { { "T", "Into the Rift", "Claim 20 Mythic Coins in Activities", "tasks" } },
        KEY = { { 1, 602, 8, { 1, 3, 4 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } },
        BOARD = { { 1, 1260, 55, 189, 2, "50 Shards", 1 }, { 189, 2, 30, 40, 1, 1500, 0, 3100, "Brenna", 0 } },
        QUEUE = { { 1, 2, "D", 189, 0, 5, 20, 300, 77, 40, 28, 33 }, { "Tester", 1, 4, 1, 30 }, { "Brenna", 2, 2, 0, 31 } },
        MPS = { { 7001, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } },
        MP = { { 7001, 600000, 1800, 2, 10, 64, 100, 1, { 300 }, { 1260, 1440 }, 1 } },
        MPE = { { 7001, 1, 1453000, 1, 599, 9, 1840 }, { "T", 1, "", "Spoils chest" }, { "C", 150 } },
        RIFT = { { 8001, 1, 7, 3, "Echo of Nefarian", 120000, 18, "", 42, 1, 1 } },
        RIFTE = { { 8001, 9, 180000, "", 0, "" }, { "C", 20 } },
        COLL = { { 1, 412, "", 0, 3771, 3, 48, { 3, 0 }, { 8, 8 } } },
        SET = { { 1, 201, 1, "Battlegear of Might", 56, 0, { 16866, 16868 }, { 229 }, 58, 61, "Ragnaros", "" } },
        LIDX = { { 1 }, { 16864, 1, 201, 1 } },
        LCOL = { { 2, 16866, 1 } },
        SEASON = { { 1, 1, 620, 1284, 1240, 2, 3, 260, "Breach the Greymane Wall", "Fill the bar.", 3 }, { "P", "Materials", 800 }, { "R", 1, 1, "Earned" } },
        LB = { { "K", 1, 0, 0, 1, 3 }, { 1, 602, 15, 300, now, { { "Aldric", 1 } }, "" } },
        LBME = { { "K", 42, 12, 9, 602, 154, 580 } },
        FIRSTS = { { "echo", "Echo of Ragnaros defeated", "Ironvow", now } },
        CASES = { { 990001 }, { 990002 } },
        CASE = { { 990001, "Glaive Case", "Unlock it to receive one of the items below.", "", "" }, { 32837, 1, 1200, 4 },
            { 32838, 1, 400, 5 } },
        UNBOX = { { 990001, 2, 32838, 1 } },
        CAMPST = { { "C", 0, 620, 1, 880, 1500, 15, { { 164, 2, 1 }, { 171, 1, 0 } }, { { 185, 1 }, { 356, 2 } }, 0, 1, 1 } },
        -- Bleakhold Royale (section 17), unrevisioned
        ROYS = { { 7001, 3, 0, 23, 24, 2, 1, "", 104, 96, 1, -267, -267, 1080, -150, -310, 520, 20000, 190000, 10, "",
            104, 96 } },
        ROYM = { { 901, -1066, 533, -1066, 533, 455, 455, 32, 750, -267, -267 },
            { 1, "L", -266, -266, 88, "The Bleak Hold" }, { 11, "C", -80, -710, 16, "Old Ford" },
            { 14, "Y", 455, 455, 32, "The Overlook" } },
        ROYO = { { 7001, 1 }, { 1, "S", 0, -266, -266, 2, 61000 }, { 3, "B", 1, 120, 80, 1, "" },
            { 20, "D", 0, -80, -180, 3, 20000 } },
        ROYK = { { "Aldric", 1, "Brenna", 8, "P", 23, 2 } },
        ROYV = { { "D", 0, -80, -180, 20000, "" } },
        ROYE = { { 7001, 12, 24, 1, 18400, 0, 214, "Dalia", 11, 7, 1 }, { "H", 70, "", "Placement" }, { "S", 5 } },
        -- the battleground kill announcer (section 18), unrevisioned
        BGANN = { { "Aldric", 1, "Brenna", 8, "D", "S" } },
        -- World PvP and War Mode (section 19), unrevisioned
        WMST = { { 1, 512, "", 20, 0, 10, 0, 8, "H", 31, 22, 3, 1, 840, 248, 412, 3720, 6, 60, 7, 121, 96 } },
        WPZ = { { 2817, "F", 1, 4320, 620, 380, "A", 2, 80, 80 }, { "O", 1, "Violet Stand", 512, 388, "A", 1000, 1 },
            { "O", 2, "Forlorn Woods", 604, 455, "N", -120, 6 }, { "O", 3, "Sunreaver Rise", "", "", "A", 800, 5 } },
        WPCAP = { { 2, -120, 20, 6, 2, 3, 5 } },
        WPMAP = { { 2817, 1, 4320, 66, 4920, 267, 1, 4320 }, { "Z", 2817, "F", 2, 0, 1, 80, 80, 1 },
            { "Z", 4197, "W", 0, 1, 0, "", "", 0 }, { "P", 2817, 1, "A", 1 }, { "P", 2817, 2, "N", 6 } },
        WANTED = { { 2817 }, { "W", "Garrick Stormwind", 4, "H", 5, "S", 248, 5, 560, 402, 35 } },
        WPEV = { { "C", 2817, 1, "A", "Violet Stand" } },
    }
end

-- Revisioned snapshot ops (first field is the revision).
FX.REV = { WEEK = true, ERA = true, TASKS = true, TASK = true, KEY = true, BOARD = true, QUEUE = true, COLL = true, LIDX = true, LCOL = true, SEASON = true }

function FX.openEverything(M, ns)
    for _, k in ipairs({ "tasks", "dungeons", "keys", "rift" }) do
        ns.UI.Open(k)
        M.Advance(0.3)
    end
    ns.UI.Open("collections")
    for _, tab in ipairs({ "transmog", "later", "legacy", "mounts", "pets", "animations" }) do
        ns.Collections.ShowTab(tab)
    end
    ns.UI.Open("royale")
    M.Advance(0.3)
    ns.UI.Open("royalemap")
    M.Advance(0.3)
    -- War Mode (section 19): its page while the realm runs it; the HUD, the bar and the map pins redraw either way
    if ns.WarMode.Live() then
        ns.UI.Open("warmode")
        M.Advance(0.3)
    end
    ns.WarFront.Tick()
    ns.WarFront.UpdateMap()
    ns.UI.Open("season")
    ns.UI.Open("leaderboards")
    for _, b in ipairs({ "K", "R", "E", "F" }) do
        ns.Leaderboards.board = b
        ns.Leaderboards.Refresh()
    end
    M.Advance(1.5)
end

-- The Animations tab's button for the entry `key`, after turning to its page (the dances come first and
-- fill more than one page).
function FX.showEntry(ns, key)
    local A = ns.Animations
    for i, e in ipairs(A.Filtered(ns.Collections.search or "", A.filter)) do
        if e.key == key then
            A.page = math.floor((i - 1) / A.PAGE_SIZE) + 1
            A.Refresh()
            return A.tab.entries[(i - 1) % A.PAGE_SIZE + 1]
        end
    end
end

return FX
