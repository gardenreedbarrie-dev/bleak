-- Scenes of the café's HUD (CafeBar.lua, CafeHud.lua), fed with server messages through the real receive path:
--
--   Tools/UiLint/preview/render.sh Tools/UiLint/preview/scenes/cafe_hud.lua shift out.png --stock <stock art> --bg ground
--
-- Scenes: shift (on shift at the counter: strip, bar, empty ticket, queue), away, step_tap (grinding), step_timed_early
-- (a timed step before its gold zone), step_timed (a timed step running in the gold), step_perfect (its grade on the
-- cast bar), result_perfect, result_good, result_ruined, queue, ticket_two (two tickets, the drink in hand), warnings
-- (danger, mounted, the Rush live), buffs, shift_buffs and order_buffs (the buffs under the strip and the order chip),
-- order_queued, order_made, order_ready, order_slow, paused (danger nearby: the clocks stand still, the bar says so),
-- order_ready_paused (the pickup's clock runs on), xp_half and xp_capped (today's XP past the full rate, at the cap),
-- shift_wide (the widest strip), tired and tired_soon, taken_over (the house finishing a player's order),
-- bin_confirm (the café's own question), away_empty (no ticket between the stations), atbar, atbar_busy (a
-- bystander by a busy bar); turned (a timed step runs on after the barista turned away: its release stays),
-- counter_ticket (Take Order dim and steady while the ticket's next step is elsewhere), tip_capped (the daily tip cap
-- reached: the ticket promises no tip, the strip says it, a drink's result names it), ruined_player (a player's first
-- ruin: the second goes to the house), result_npc (an NPC's tip and the drink's points), party (the ticket right of
-- the party frames). Patch-4 is left out, as on most clients: the café's icons are the stock ones.
local S = {}

local function noPatch(M)
    M.missingTextures["Interface\\Icons\\BH_Cafe_Espresso"] = true
end
S.before = setmetatable({}, { __index = function() return noPatch end })

local function push(ns, op, records)
    ns.Demo.Push(op, records)
end

-- in Stormwind as the client tells it: the world map's area of the zone (SetMapToCurrentZone, GetCurrentMapAreaID)
local function inCity(M)
    M.zone = "Stormwind City"
    M.env.SetMapToCurrentZone = function() end
    M.env.GetCurrentMapAreaID = function()
        return 301
    end
    M.FireEvent("ZONE_CHANGED_NEW_AREA")
end

local function connect(M, ns)
    push(ns, "HELLO", { { 1, 1, M.env.time(), 0, 0, 131072, 1, 0, 0, "Bleakhold", "" } })
    push(ns, "CAFE", { { 1, 1, 2, 4, 1, 252, 45 }, { 2, 1, 1, 2, 1, 252, 60 } })
    M.Advance(0.3)
end

-- CAFST on shift at a station (nil: away); extra fields by index; day: today's credited XP (210 by default)
local function shift(M, ns, station, extra, rush, day)
    local r = { 1, 1, 6, 1890, 1600, 2320, 760, 14, 9, 4, 10600, 212, station or "", station or "G", station and 3 or 40, 2,
        2400, 2 }
    for k, v in pairs(extra or {}) do
        r[k] = v
    end
    push(ns, "CAFST", { r, { "D", day or 210, 450, 450, 30000, 180000, 180, 400, 14 },
        rush or { "R", 1, 252, 0, 60, 0 } })
end

local QUEUE = {
    { 1, 5, 6, 2, "" },
    { 1209, "P", 103, "Brenna", 21000, 25000, "W", "", 0 },
    { 1207, "N", 101, "Sergeant Corwin Ashgrove", 30000, 48000, "W", "", 0 },
    { 1212, "G", 102, "Night Watch Guard", 14000, 51000, "W", "", 0, 7 },
    { 1213, "N", 107, "Lady Seraphine Ravenmoor", 50000, 54000, "W", "", 9 },
    { 1208, "N", 108, "Grandma Hester", 41000, 60000, "T", "Aldric", 0 },
}

local function brenna(nextStep, inHand, patienceMs)
    local steps = { { 1, "N" }, { 3, "N" }, { 6, "N" }, { 16, "N" }, { 25, "N" } }
    for i = 1, (nextStep or 1) - 1 do
        steps[i][2] = "P"
    end
    return { 41, 1209, 103, "P", "Brenna", patienceMs or 47000, 60000, nextStep or 1, inHand or 0, "", steps, 2100 }
end

local function corwin(nextStep, inHand)
    local steps = { { 1, "N" }, { 3, "N" }, { 4, "N" }, { 25, "N" } }
    for i = 1, (nextStep or 1) - 1 do
        steps[i][2] = i == 2 and "G" or "P"
    end
    return { 42, 1207, 101, "N", "Sergeant Corwin Ashgrove", 21000, 54000, nextStep or 1, inHand or 0,
        "Cathedral Black. No sugar, no chatter, no delay.", steps, 400 }
end

local function hud(env)
    return { env.BleakholdCafeStrip, env.BleakholdCafeBar, env.BleakholdCafeTicket, env.BleakholdCafeQueue,
        env.BleakholdCafeResult }
end

S.shift = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "V")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { { 0 } })
    M.Advance(1)
    return hud(env)
end

S.away = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, nil)
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { brenna(2, 1) })
    M.Advance(1)
    return hud(env)
end

S.step_tap = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "G")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { brenna(1, 0) })
    M.Advance(0.5)
    push(ns, "CAFEV", { { 41, 1, 1, "S", 1500, "", "", "", 1 } })
    M.Advance(0.6)
    return hud(env)
end

local function timed(after)
    return function(M, ns, RS, env)
        connect(M, ns)
        shift(M, ns, "E")
        push(ns, "CAFQ", QUEUE)
        push(ns, "CAFT", { brenna(2, 1) })
        M.Advance(0.5)
        push(ns, "CAFEV", { { 41, 2, 3, "S", 3000, 2160, 2610, "", 2 } })
        M.Advance(after, 0.05)
        return hud(env)
    end
end

S.step_timed_early = timed(1.3)
S.step_timed = timed(2.3)

S.step_perfect = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "E")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { brenna(2, 1) })
    M.Advance(0.5)
    push(ns, "CAFEV", { { 41, 2, 3, "S", 3000, 2160, 2610, "", 2 } })
    M.Advance(2.4, 0.05)
    push(ns, "CAFEV", { { 41, 2, 3, "D", 3000, 2160, 2610, "P", 3 } })
    push(ns, "CAFT", { brenna(3, 1) })
    M.Advance(0.1)
    return hud(env)
end

-- a drink's result; tickets: the ticket list before it (its kind says tip or pay), none by default
local function result(records, tickets)
    return function(M, ns, RS, env)
        connect(M, ns)
        shift(M, ns, "V")
        push(ns, "CAFQ", QUEUE)
        push(ns, "CAFT", tickets or { { 0 } })
        M.Advance(0.5)
        push(ns, records[1], records[2])
        M.Advance(0.6)
        return hud(env)
    end
end

-- Brenna's order: a player's, so its money is the barista's pay (wage and tip)
S.result_perfect = result({ "CAFRES", { { 41, 103, "P", 27, 1400, 22, 4, 0, 6, "Brenna", "", 0 } } }, { brenna(5, 1) })
S.result_good = result({ "CAFRES", { { 42, 101, "G", 12, 260, 12, 0, 0, 6, "Sergeant Corwin Ashgrove",
    "Hot and bitter. Like my shift.", 0 } } })
S.result_ruined = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "E")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { corwin(3, 1) })
    M.Advance(0.5)
    push(ns, "CAFEV", { { 42, 3, 5, "X", "", "", "", "", 1 } })
    push(ns, "CAFT", { corwin(1, 0) })
    M.Advance(0.25)
    return hud(env)
end

S.queue = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "G")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { { 0 } })
    M.Advance(0.5)
    ns.Cafe.SelectOrder(1207)
    local row = env.BleakholdCafeQueue.pool.items[1]
    M.Hover(row)
    M.Advance(0.3)
    return { env.BleakholdCafeQueue }
end

S.ticket_two = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "E")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { brenna(1, 0), corwin(3, 1) })
    M.Advance(1)
    return { env.BleakholdCafeTicket, env.BleakholdCafeBar }
end

S.warnings = function(M, ns, RS, env)
    connect(M, ns)
    push(ns, "CAFE", { { 1, 2, 2, 4, 2, 372, 45 }, { 2, 1, 1, 2, 2, 372, 60 } })
    shift(M, ns, "V", { [18] = 2 + 64, [19] = 4 }, { "R", 2, 372, 41, 60, 3 })
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { { 0 } })
    M.Advance(1)
    return { env.BleakholdCafeStrip, env.BleakholdCafeBar }
end

-- a barista on shift with a café buff (the Staff Drink): the buffs under the strip and its lines
S.shift_buffs = function(M, ns, RS, env)
    connect(M, ns)
    inCity(M)
    shift(M, ns, "V")
    push(ns, "CAFT", { { 0 } })
    push(ns, "CAFBF", { { 1680, 2400, 900, 1, 1 } })
    M.Advance(1)
    return { env.BleakholdCafeStrip, env.BleakholdCafeBuffs }
end

-- a customer with a buff and an order being made: the buffs under the order chip
S.order_buffs = function(M, ns, RS, env)
    connect(M, ns)
    inCity(M)
    shift(M, ns, nil, { [1] = 0, [2] = 0 })
    push(ns, "CAFBF", { { 1680, 2400, 900, 1, 1 } })
    push(ns, "CAFO", { { 1210, 1, 103, "M", "", "Aldric", 2, 5, "", 5300, 530 } })
    M.Advance(1)
    return { env.BleakholdCafeOrderChip, env.BleakholdCafeBuffs }
end

S.buffs = function(M, ns, RS, env)
    connect(M, ns)
    inCity(M)
    push(ns, "CAFBF", { { 1680, 2400, 900, 1, 1 } })
    M.Advance(1)
    M.Hover(env.BleakholdCafeBuffs.chips[3])
    return { env.BleakholdCafeBuffs }
end

local function order(records, after)
    return function(M, ns, RS, env)
        connect(M, ns)
        shift(M, ns, nil, { [1] = 0, [2] = 0 })
        for _, r in ipairs(records) do
            push(ns, "CAFO", { r })
        end
        M.Advance(after or 0.5)
        return { env.BleakholdCafeOrderChip }
    end
end

S.order_queued = order({ { 1210, 1, 103, "Q", 1, "", 0, 5, "", 5300, 530 } })
S.order_made = order({ { 1210, 1, 103, "M", "", "Aldric", 2, 5, "", 5300, 530 } })
S.order_ready = order({ { 1210, 1, 103, "R", "", "", 5, 5, 179, 5300, 530 } })
S.order_slow = order({ { 1210, 1, 103, "F", "", "", 2, 5, 40, 5300, 530 } })

-- danger nearby (CAFE open 2): the ticket's, the queue's clocks stand still, greyed with "(paused)"
S.paused = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "E")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { brenna(2, 1) })
    M.Advance(0.5)
    push(ns, "CAFE", { { 1, 2, 2, 4, 1, 252, 45 }, { 2, 1, 1, 2, 1, 252, 60 } })
    M.Advance(5, 0.1)
    return { env.BleakholdCafeStrip, env.BleakholdCafeTicket, env.BleakholdCafeQueue, env.BleakholdCafeBar }
end

-- a customer's ready order in a pause: the pickup's clock keeps running, as the server's
S.order_ready_paused = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, nil, { [1] = 0, [2] = 0 })
    push(ns, "CAFO", { { 1210, 1, 103, "R", "", "", 5, 5, 120, 5300, 530 } })
    M.Advance(0.5)
    push(ns, "CAFE", { { 1, 2, 2, 4, 1, 252, 45 }, { 2, 1, 1, 2, 1, 252, 60 } })
    M.Advance(30, 0.5)
    return { env.BleakholdCafeOrderChip }
end

-- today's XP past the full rate (credited 560 of 450 + 225), and a drink in that band: what it still earned
S.xp_half = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "V", nil, nil, 560)
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { { 0 } })
    M.Advance(0.5)
    push(ns, "CAFRES", { { 41, 103, "G", 13, 600, 12, 0, 0, 6, "Brenna", "", 13 } })
    M.Advance(0.6)
    return { env.BleakholdCafeStrip, env.BleakholdCafeResult }
end

-- the day's XP capped (675 credited): the strip's line, and a drink that earned no more
S.xp_capped = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "V", nil, nil, 675)
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { { 0 } })
    M.Advance(0.5)
    push(ns, "CAFRES", { { 41, 103, "G", 0, 600, 12, 0, 0, 6, "Brenna", "", 20 } })
    M.Advance(0.6)
    return { env.BleakholdCafeStrip, env.BleakholdCafeResult }
end

-- the widest strip a shift gets: over an hour, a long streak, tips at the day's 18 gold cap, the day's XP capped
S.shift_wide = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "V", { [7] = 3725, [8] = 140, [10] = 24, [11] = 179999, [12] = 675 }, nil, 675)
    push(ns, "CAFT", { { 0 } })
    M.Advance(1)
    return { env.BleakholdCafeStrip }
end

-- Tired: what is halved, with the rest it needs; and five minutes before it, the countdown
S.tired = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "V", { [17] = 900, [18] = 2 + 4 })
    push(ns, "CAFT", { { 0 } })
    M.Advance(1)
    return { env.BleakholdCafeStrip }
end
S.tired_soon = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "V", { [17] = 252 })
    push(ns, "CAFT", { { 0 } })
    M.Advance(1)
    return { env.BleakholdCafeStrip }
end

-- a player's order the house took over (the barista too slow): not a customer who left
S.taken_over = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "V")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { brenna(3, 1) })
    M.Advance(0.5)
    push(ns, "CAFRES", { { 41, 103, "L", 0, 0, 0, 0, 0, 6, "Brenna", "Too slow: the house is finishing it.", 0 } })
    push(ns, "CAFT", { { 0 } })
    M.Advance(0.6)
    return { env.BleakholdCafeResult }
end

-- Bin with four steps done: the café's own question (never the kit's shared dialog)
S.bin_confirm = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "V")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { brenna(5, 1) })
    M.Advance(0.5)
    ns.Cafe.Press(3)
    M.Advance(0.3)
    return { env.BleakholdCafeStrip, env.BleakholdCafeBar, env.BleakholdCafeTicket, env.BleakholdCafeQueue,
        env.BleakholdCafeConfirm }
end

-- a new barista between the stations, no ticket yet: the ticket names the counter, not a key
S.away_empty = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, nil)
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { { 0 } })
    M.Advance(1)
    return hud(env)
end

-- a bystander by a busy bar (six at work in a Rush, the player's order being made): the list on the left, the order
-- chip at the top, nothing at the right edge where the quest tracker hangs
S.atbar_busy = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, nil, { [1] = 0, [2] = 0 })
    push(ns, "CAFO", { { 1210, 1, 103, "M", "", "Aldric", 2, 5, "", 5300, 530 } })
    push(ns, "CAFAT", { { 1, 6 }, { "Aldric", 3, 400, 3000, "H", 2, 5 },
        { "Rosalind Thornbury", 1, 900, 1500, "T", 1, 4 },
        { "Brenna", 15, 1200, 2500, "H", 4, 5 }, { "Tobias Brindle", 9, 300, 1500, "T", 1, 3 },
        { "Kessa", 6, 800, 2000, "H", 3, 6 }, { "Dalia", 24, 100, 500, "T", 1, 5 } })
    M.Advance(0.5)
    return { env.BleakholdCafeAtBar, env.BleakholdCafeOrderChip }
end

S.atbar = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, nil, { [1] = 0, [2] = 0 })
    push(ns, "CAFAT", { { 1, 3 }, { "Aldric", 3, 400, 3000, "H", 2, 5 }, { "Rosalind Thornbury", 1, 900, 1500, "T", 1, 4 },
        { "Brenna", 15, 1200, 2500, "H", 4, 5 } })
    M.Advance(0.5)
    return { env.BleakholdCafeAtBar }
end

-- a timed step runs on after the barista turned away from the machine (CAFST names no station): the bar keeps its
-- station's slots and the release, the timing bar its key
S.turned = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "E")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { brenna(2, 1) })
    M.Advance(0.5)
    push(ns, "CAFEV", { { 41, 2, 3, "S", 3000, 2250, 2700, "", 2 } })
    M.Advance(0.6, 0.05)
    shift(M, ns, nil)
    M.Advance(1.6, 0.05)
    return hud(env)
end

-- at the counter with a ticket just taken: its next step (the Grinder) is the hint, Take Order only dim and steady
S.counter_ticket = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "V")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { corwin(1, 0) })
    M.Advance(1)
    return hud(env)
end

-- the daily tip cap reached: an NPC's ticket promises no tip, the strip says it, and so does a drink's result
S.tip_capped = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "E")
    push(ns, "CAFST", { { 1, 1, 6, 1890, 1600, 2320, 760, 14, 9, 4, 10600, 212, "E", "E", 3, 2, 2400, 2 },
        { "D", 210, 450, 450, 30000, 30000, 400, 400, 25 }, { "R", 1, 252, 0, 60, 0 } })
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { corwin(2, 1), brenna(2, 0) })
    M.Advance(0.5)
    ns.Cafe.SelectTicket(42)
    push(ns, "CAFRES", { { 43, 101, "G", 12, 0, 0, 0, 0, 6, "Little Wendel", "Thanks!", 0 } })
    M.Advance(0.6)
    return hud(env)
end

-- a player's drink ruined once: the streak ends, and one more ruin hands the order to the house
S.ruined_player = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "E")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { brenna(3, 1) })
    M.Advance(0.5)
    push(ns, "CAFEV", { { 41, 3, 5, "X", "", "", "", "", 1 } })
    push(ns, "CAFT", { brenna(1, 0) })
    M.Advance(0.25)
    return hud(env)
end

-- an NPC's Perfect drink: the tip (an NPC's own), the drink's Café Points, the streak
S.result_npc = function(M, ns, RS, env)
    connect(M, ns)
    shift(M, ns, "V")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { corwin(4, 1) })
    M.Advance(0.5)
    push(ns, "CAFRES", { { 42, 101, "P", 27, 340, 22, 5, 0, 6, "Sergeant Corwin Ashgrove",
        "Hot and bitter. Like my shift.", 0 } })
    M.Advance(0.6)
    return hud(env)
end

-- in a party: the ticket stands right of the party frames' column (TOPLEFT 10,-160 stock, -200 in AddicatUI)
S.party = function(M, ns, RS, env)
    M.party = 2
    connect(M, ns)
    shift(M, ns, "G")
    push(ns, "CAFQ", QUEUE)
    push(ns, "CAFT", { brenna(1, 0) })
    M.FireEvent("PARTY_MEMBERS_CHANGED")
    M.Advance(1)
    return hud(env)
end

return S
