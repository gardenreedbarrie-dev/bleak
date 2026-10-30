-- The café (section 21): State.lua's parsers (S.cafe*), DEF H/G/F/U under the built-in CafeData, the GETs after HELLO,
-- and ns.Cafe's queries and send gates (Cafe.lua).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local CAFE_BIT = { [6] = 131072 }

local function gets(M, from)
    local out = {}
    for _, it in ipairs(H.intents(M, from)) do
        if it.op == "GET" then
            for _, r in ipairs(it.records) do
                out[#out + 1] = table.concat(r, ",")
            end
        end
    end
    return out
end

local function has(list, v)
    for _, x in ipairs(list) do
        if x == v then
            return true
        end
    end
    return false
end

local function sendAll(M)
    local ex = FX.examples(M)
    for _, op in ipairs({ "CAFE", "CAFST", "CAFQ", "CAFT", "CAFEV", "CAFRES", "CAFM", "CAFO", "CAFP", "CAFBF", "CAFSUM",
        "CAFAT" }) do
        H.send(M, op, ex[op])
    end
end

local function errorsShown(M, text)
    local n = 0
    for _, c in ipairs(M.chat) do
        if c.frame == M.env.UIErrorsFrame and c.msg:find(text, 1, true) then
            n = n + 1
        end
    end
    return n
end

test("cafe state: every message of the fixtures parses into its documented shape", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    sendAll(M)
    local S = ns.S
    H.eq(S.cafes[1].open, 1)
    H.eq(S.cafes[1].baristas, 1)
    H.eq(S.cafes[1].queueLen, 2)
    H.eq(S.cafes[1].rushState, 1)
    H.eq(S.cafes[1].rushSec, 180)
    H.eq(S.cafes[2].houseEtaSec, 60)
    local st = S.cafeState
    H.eq(st.cafeId, 1)
    H.eq(st.onShift, true, "onShift is a boolean")
    H.eq(st.level, 6)
    H.eq(st.xp, 1890)
    H.eq(st.levelXp, 1600)
    H.eq(st.nextLevelXp, 2320)
    H.eq(st.station, "V")
    H.eq(st.nearStation, "V")
    H.eq(st.nearDm, 3)
    H.eq(st.maxTickets, 2)
    H.eq(st.tiredSec, 3600)
    H.eq(st.flags, 2)
    H.eq(st.warnSec, nil)
    H.eq(st.day.dayXp, 210)
    H.eq(st.day.dayTipsCapCopper, 180000)
    H.eq(st.day.dayDrinks, 14)
    H.eq(st.rush.rushGoal, 60)
    H.eq(st.rush.rushSec, 180)
    local q = S.cafeQueue
    H.eq(q.cafeId, 1)
    H.eq(q.cap, 6)
    H.eq(q.baristas, 2)
    H.eq(#q.rows, 2)
    H.eq(q.rows[1].orderId, 1209)
    H.eq(q.rows[1].kind, "P")
    H.eq(q.rows[1].customer, "Brenna")
    H.eq(q.rows[2].state, "T")
    H.eq(q.rows[2].takenBy, "Aldric")
    H.eq(q.rows[2].patienceMaxMs, 48000)
    local t = S.cafeTickets[1]
    H.eq(#S.cafeTickets, 1)
    H.eq(t.ticketId, 41)
    H.eq(t.orderId, 1209)
    H.eq(t.recipeId, 103)
    H.eq(t.nextStep, 2)
    H.eq(t.inHand, true, "inHand is a boolean")
    H.eq(#t.steps, 5)
    H.eq(t.steps[1].actionId, 1)
    H.eq(t.steps[1].grade, "P")
    H.eq(t.steps[5].actionId, 25)
    H.eq(t.tipHintCopper, 2100)
    local cs = S.cafeStep
    H.eq(cs.ticketId, 41)
    H.eq(cs.stepIndex, 2)
    H.eq(cs.event, "S")
    H.eq(cs.durMs, 3000)
    H.eq(cs.goldLoMs, 2160)
    H.eq(cs.goldHiMs, 2610)
    H.eq(cs.recvAt, M.now, "stamped as it arrives")
    local res = S.cafeResult
    H.eq(res.quality, "P")
    H.eq(res.xp, 32)
    H.eq(res.tipCopper, 2100)
    H.eq(res.levelUp, 0)
    H.eq(res.customer, "Brenna")
    local m = S.cafeMenu[1]
    H.eq(m.canOrder, 1)
    H.eq(#m.rows, 3)
    H.eq(m.byRecipe[103].priceCopper, 5300)
    H.eq(m.byRecipe[119].byBarista, 0)
    H.eq(m.byRecipe[119].effective, 1)
    local o = S.cafeOrder
    H.eq(o.orderId, 1210)
    H.eq(o.state, "Q")
    H.eq(o.position, 1)
    H.eq(o.stepCount, 5)
    H.eq(o.tipCopper, 530)
    local p = S.cafeProfile
    H.eq(p.level, 6)
    H.eq(p.fastestMs, 5120)
    H.eq(p.rewards, 1)
    H.eq(p.week.rank, 2)
    H.eq(p.week.perfectPermille, 790)
    H.eq(p.last[1].winnerName, "Brenna")
    local b = S.cafeBuffs
    H.eq(b.coffeeSec, 1320)
    H.eq(b.teaSec, nil, "an empty timer is nil")
    H.eq(b.shakeSec, 1800)
    H.eq(b.coffeeCounts, 1)
    local sum = S.cafeSummary
    H.eq(sum.reason, "E")
    H.eq(sum.drinks, 14)
    H.eq(sum.staffDrink, 0)
    local at = S.cafeAtBar[1]
    H.eq(at.count, 2)
    H.eq(#at.rows, 2)
    H.eq(at.rows[1].name, "Aldric")
    H.eq(at.rows[1].kind, "H")
    H.eq(at.rows[2].stepCount, 4)
end)

test("cafe state: the empty records (no tickets, no order, no buff) and events", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    sendAll(M)
    H.send(M, "CAFT", { { 0 } })
    H.eq(#ns.S.cafeTickets, 0, "CAFT 0: no tickets")
    H.send(M, "CAFO", { { 0 } })
    H.eq(ns.S.cafeOrder, nil, "CAFO 0: no order")
    H.send(M, "CAFBF", { { "", "", "", 0, 1 } })
    H.eq(ns.S.cafeBuffs, nil, "no café buff running")
    -- off shift: CAFST without the shift's fields, its rush record dropped
    H.send(M, "CAFST", { { 0, 0, 6, 1890, 1600, 2320 }, { "D", 210, 450, 450, 30000, 180000, 180, 400, 14 },
        { "R", 1, 180, 0, 60, 0 } })
    H.eq(ns.S.cafeState.onShift, false)
    H.eq(ns.S.cafeState.rush, nil, "the Rush record only on shift")
    H.eq(ns.S.cafeState.station, nil)
    local fired = {}
    ns.On("CAFE_UI", function(what, cafeId) fired[#fired + 1] = what .. cafeId end)
    ns.On("CAFE_STEP", function(s) fired[#fired + 1] = "step" .. s.event end)
    ns.On("CAFE_RESULT", function(r) fired[#fired + 1] = "res" .. r.quality end)
    ns.On("CAFE_SUMMARY", function(s) fired[#fired + 1] = "sum" .. s.reason end)
    H.send(M, "CAFUI", { { "board", 2 } })
    H.send(M, "CAFUI", { { "evil", 2 } })
    H.send(M, "CAFEV", { { 41, 3, 6, "D", 2000, 760, 1160, "P", 4 } })
    H.send(M, "CAFEV", { { 41, 3, 6, "Q", 2000, 760, 1160, "P", 4 } })
    H.send(M, "CAFRES", { { 41, 103, "L", 0, 0, 0, 0, 0, 6, "Brenna", "Forget it.", 0 } })
    H.send(M, "CAFSUM", { { 1, "C", 600, 3, 1, 900, 40, 12, 30, 1, 0 } })
    H.eq(table.concat(fired, ","), "board2,stepD,resL,sumC", "an unknown window or event is dropped")
    H.eq(ns.S.cafeStep.grade, "P")
end)

test("cafe state: DEF H/G/F/U lie over the built-in catalogue (DEF schema 3)", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    H.eq(ns.DEF_SCHEMA, 3)
    local Cafe = ns.Cafe
    H.eq(Cafe.Cafe(1).name, "The Lion's Roast", "built in before any DEF")
    H.eq(Cafe.Action(3).name, "Pull Shot")
    H.send(M, "DEF", { { "H", 8 }, { 1, "The Lion's Roast II", "sw", "A", 1519, 0, "Rosalind", "", "3F6FB5" } })
    H.send(M, "DEF", { { "G", 8 }, { 3, "E", 1, "H", 3200, 690, 840, "Pull Shot", "", 100903 },
        { 21, "S", 6, "T", 800, "", "", "Elwynn Berry", "Cactus Apple", 100921 } })
    H.send(M, "DEF", { { "F", 8 }, { 101, 1, 1, "C", 1, 1, 4400, 30, { 1, 3, 4, 25 }, "Cathedral Black", "" } })
    H.send(M, "DEF", { { "U", 8 }, { 5, 1040, "Iced latte and mint tea." } })
    H.eq(Cafe.Cafe(1).name, "The Lion's Roast II", "DEF H's name")
    H.eq(Cafe.Cafe(1).tagline, ns.CafeData.cafes[1].tagline, "an empty DEF field keeps the built-in value")
    H.eq(Cafe.Action(3).durMs, 3200)
    H.eq(Cafe.Action(3).gold[1], 690)
    H.eq(Cafe.Action(3).timed, true)
    H.eq(Cafe.Recipe(101).price80, 4400)
    H.eq(Cafe.Recipe(101).text, ns.CafeData.recipes[101].text)
    H.eq(Cafe.Level(5).text, "Iced latte and mint tea.")
    H.eq(Cafe.Level(5).xp, 1040)
    H.eq(Cafe.ActionsAt("E")[1].id, 3)
    H.eq(Cafe.ActionsAt("S")[6].name, "Elwynn Berry")
    -- at the Horde café the action's Horde name
    H.send(M, "CAFST", { { 2, 1, 6, 1890, 1600, 2320, 0, 0, 0, 0, 0, 0, "S", "S", 3, 2, 3600, 0 },
        { "D", 0, 450, 450, 0, 180000, 0, 400, 0 } })
    H.eq(Cafe.ActionsAt("S")[6].name, "Cactus Apple")
    H.eq(#Cafe.Recipes(1, "M"), 6)
    H.eq(#Cafe.Recipes(2), 19)
end)

test("cafe state: after HELLO with the bit the client asks for its state; without it everything is gone", function(M, ns)
    local from = #M.sent + 1
    FX.connect(M, H, CAFE_BIT)
    M.Advance(0.3)
    local g = gets(M, from)
    for _, topic in ipairs({ "CAFE", "CAFST", "CAFBF", "CAFO" }) do
        H.ok(has(g, topic), "GET " .. topic)
    end
    H.ok(not has(g, "CAFT") and not has(g, "CAFQ"), "no tickets or queue off shift")
    sendAll(M)
    H.eq(M.env.BleakholdCharDB.cafeOnShift, true, "a shift is remembered across /reload")
    H.hello(M, {})
    M.Advance(0.3)
    H.eq(ns.S.cafeState, nil, "HELLO without the bit: no café state")
    H.eq(#ns.S.cafeTickets, 0)
    H.eq(next(ns.S.cafes), nil)
    H.eq(M.env.BleakholdCharDB.cafeOnShift, nil)
end)

test("cafe state: after /reload during a shift the tickets and the queue are asked for too", function(M, ns)
    local from = #M.sent + 1
    FX.connect(M, H, CAFE_BIT)
    M.Advance(0.3)
    local g = gets(M, from)
    H.ok(has(g, "CAFT") and has(g, "CAFQ"), "GET CAFT and CAFQ: " .. table.concat(g, ";"))
end, { before = function(M)
    M.env.BleakholdCharDB = { cafeOnShift = true }
end })

test("cafe state: a toast to the café keeps its target", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    local got
    ns.On("TOAST", function(d) got = d end)
    H.send(M, "TOAST", { { "I", "Barista level 5", "Apprentice's Apron unlocked", "cafe" } })
    H.eq(got.target, "cafe")
end)

test("cafe api: prices, money, timers, colours, words", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    local Cafe = ns.Cafe
    M.playerLevel = 70
    -- the server's rule: max(200, price80 x level/80) rounded up to whole silver (7/8 of 60s = 52s 50c -> 53s)
    H.eq(Cafe.Price(103), 5300)
    M.playerLevel = 1
    H.eq(Cafe.Price(101), 400, "at least a tenth of the level-80 price")
    H.send(M, "CAFM", { { 1, 1, 1, 45, 0, 2, 12, 1 }, { 101, 3500, 1, 1 } })
    H.eq(Cafe.Price(101), 3500, "the menu's price wins")
    H.eq(Cafe.MoneyPlain(15800), "1g 58s")
    local money = Cafe.Money(15805)
    H.contains(money, "1|TInterface\\MoneyFrame\\UI-GoldIcon")
    H.contains(money, "58|TInterface\\MoneyFrame\\UI-SilverIcon")
    H.contains(money, "5|TInterface\\MoneyFrame\\UI-CopperIcon")
    H.contains(Cafe.Money(0), "0|TInterface\\MoneyFrame\\UI-CopperIcon")
    H.eq(Cafe.PatienceColor(0.8), "00FF00")
    H.eq(Cafe.PatienceColor(0.5), "FFFF00")
    H.eq(Cafe.PatienceColor(0.3), "FFFF00")
    H.eq(Cafe.PatienceColor(0.2), "FF0000")
    H.eq(Cafe.QualityText("P"), "Perfect")
    H.eq(Cafe.QualityText("L"), "Customer Left")
    H.send(M, "CAFBF", { { 1320, "", 1800, 0, 1 } })
    M.Advance(20)
    H.ok(math.abs(Cafe.Left(ns.S.cafeBuffs, "coffeeSec") - 1300) < 0.01, "counts down from the message")
    H.eq(Cafe.Left(ns.S.cafeBuffs, "teaSec"), nil)
    H.eq(Cafe.Family(110), "T")
    H.eq(Cafe.FamilyName("M"), "Shake", "one name for the family: the singular as a tag")
    H.eq(Cafe.FAMILY_PLURAL.M, "Shakes", "and the plural on tabs and filters")
    H.eq(Cafe.MyCafe(), 1, "no faction from the client: The Lion's Roast")
    M.env.UnitFactionGroup = function() return "Horde" end
    H.eq(Cafe.MyCafe(), 2)
end)

test("cafe api: the café's icons are stock until patch-4 is there", function(M, ns)
    local Cafe = ns.Cafe
    H.eq(Cafe.PatchPresent(), false)
    H.eq(Cafe.Icon("station", "E"), "INV_Gizmo_01")
    H.eq(Cafe.Icon("family", "M"), "INV_Misc_Food_31")
    H.eq(Cafe.Icon("action", 26), "Interface\\Buttons\\UI-GroupLoot-Pass-Up")
end, { before = function(M)
    M.missingTextures["Interface\\Icons\\BH_Cafe_Espresso"] = true
end })

test("cafe api: with patch-4 the stations and families show the café's own icons", function(M, ns)
    local Cafe = ns.Cafe
    H.eq(Cafe.PatchPresent(), true)
    H.eq(Cafe.Icon("station", "E"), "BH_Cafe_Espresso")
    H.eq(Cafe.Icon("family", "T"), "BH_Cafe_Tea")
    H.eq(Cafe.Icon("action", 3), "INV_Gizmo_01", "the steps keep the stock icons")
end)

test("cafe api: keys, the active ticket, the Staff Drink", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    local Cafe = ns.Cafe
    H.eq(table.concat(Cafe.Keys(), ","), "1,2,3,4,5,6,7,8")
    H.eq(table.concat(Cafe.ParseKeys("q, w, e, r, SHIFT-1, ctrl-2, alt-shift-3, ="), ","),
        "Q,W,E,R,SHIFT-1,CTRL-2,ALT-SHIFT-3,=")
    H.eq(Cafe.ParseKeys("1,2,3"), nil, "eight keys")
    H.eq(Cafe.ParseKeys("1,2,3,4,5,6,7,7"), nil, "different keys")
    H.eq(Cafe.ParseKeys("1,2,3,4,5,6,7,F11"), nil, "one key name")
    H.eq(Cafe.ParseKeys("1,2,3,4,5,6,7,META-8"), nil, "known modifiers only")
    H.eq(Cafe.KeyLabel("SHIFT-1"), "s-1")
    -- tickets: the drink in hand wins; then the chosen tab; then the oldest
    H.send(M, "CAFT", {
        { 41, 1209, 103, "P", "Brenna", 57000, 60000, 1, 0, "", { { 1, "N" }, { 3, "N" } }, 2100 },
        { 42, 1207, 101, "N", "Corwin", 43200, 43200, 1, 0, "", { { 1, "N" }, { 3, "N" } }, 400 } })
    H.eq(Cafe.ActiveTicket().ticketId, 42, "a new ticket is worked on (auto-select)")
    H.ok(Cafe.SelectTicket(41))
    H.eq(Cafe.ActiveTicket().ticketId, 41)
    H.send(M, "CAFT", {
        { 41, 1209, 103, "P", "Brenna", 57000, 60000, 1, 0, "", { { 1, "N" }, { 3, "N" } }, 2100 },
        { 42, 1207, 101, "N", "Corwin", 43200, 43200, 2, 1, "", { { 1, "P" }, { 3, "N" } }, 400 } })
    H.eq(Cafe.ActiveTicket().ticketId, 42, "the drink in hand")
    H.eq(Cafe.SelectTicket(41), false, "cannot switch away from the drink in hand")
    -- the Staff Drink: the lowest unlocked recipe of the family
    H.send(M, "CAFST", { { 1, 1, 6, 1890, 1600, 2320, 0, 0, 0, 0, 0, 0, "V", "V", 3, 2, 3600, 0 },
        { "D", 0, 450, 450, 0, 180000, 0, 400, 0 } })
    H.eq(Cafe.StaffRecipe("C"), 101)
    H.eq(Cafe.StaffRecipe("M"), 114)
    H.eq(Cafe.StaffRecipe("T"), 108)
end)

test("cafe api: send gates, ERR busy and the not-connected refusal", function(M, ns)
    local Cafe = ns.Cafe
    H.eq(Cafe.Send("CSHIFT", 1, 1), false, "before HELLO")
    H.eq(errorsShown(M, "Not connected to the realm."), 1)
    FX.connect(M, H, CAFE_BIT)
    H.ok(Cafe.Send("CSTEP", 41, 2, 3))
    H.eq(Cafe.Send("CSTEP", 41, 2, 3), false, "within 0.25 s")
    M.Advance(0.3)
    H.ok(Cafe.Send("CSTEP", 41, 2, 3), "the same step again: never a duplicate")
    H.eq(H.countIntents(M, "CSTEP"), 2)
    H.ok(Cafe.Send("CSHIFT", 1, 1))
    M.Advance(1)
    H.eq(Cafe.Send("CSTAFF", 108), false, "CSHIFT and CSTAFF share one gate")
    M.Advance(1.5)
    H.ok(Cafe.Send("CORDER", 1, 103, 10))
    M.Advance(0.5)
    H.send(M, "ERR", { { "CORDER", ns.Comm.lastSeq, "busy", "Slow down." } })
    M.Advance(2)
    H.eq(Cafe.Send("CCANCEL", 1210), false, "busy waits a full gap from the refusal")
    M.Advance(0.5)
    H.ok(Cafe.Send("CCANCEL", 1210))
    local before = H.countIntents(M, "GET")
    H.send(M, "ERR", { { "CSTEP", ns.Comm.lastSeq, "cafe_ticket", "That ticket moved on." } })
    M.Advance(0.3)
    local found = false
    for _, it in ipairs(H.intents(M)) do
        if it.op == "GET" and it.payload:find("CAFT", 1, true) then
            found = true
        end
    end
    H.ok(found and H.countIntents(M, "GET") > before, "cafe_ticket asks for the tickets")
end)

test("cafe api: /bh cafe sets the options and opens the window", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    local Cafe = ns.Cafe
    M.env.SlashCmdList.BLEAKHOLD("cafe scale 3")
    H.eq(Cafe.Option("cafeScale"), 1.4, "clamped")
    M.env.SlashCmdList.BLEAKHOLD("cafe sound off")
    H.eq(Cafe.Option("cafeSound"), false)
    M.env.SlashCmdList.BLEAKHOLD("cafe motion")
    H.eq(Cafe.Option("cafeMotion"), false, "toggled")
    M.env.SlashCmdList.BLEAKHOLD("cafe keys a,b,c,d,e,f,g,h")
    H.eq(Cafe.Option("cafeKeys"), "A,B,C,D,E,F,G,H")
    M.env.SlashCmdList.BLEAKHOLD("cafe keys a,b")
    H.eq(Cafe.Option("cafeKeys"), "A,B,C,D,E,F,G,H", "refused")
    local opened
    ns.UI.RegisterOpener("cafe", function() opened = true end)
    M.env.SlashCmdList.BLEAKHOLD("cafe")
    H.ok(opened, "the café window")
    H.eq(M.env.BINDING_NAME_BLEAKHOLD_CAFE, "Open the caf\195\169 window")
    H.eq(bit.band(ns.Comm.clientCaps, ns.Comm.CAPS.CAFE_UI), ns.Comm.CAPS.CAFE_UI, "HELLO names the café's UI")
end)

test("cafe api: CAFUI opens the window the café's staff chose", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    local opened = {}
    for _, k in ipairs({ "cafemenu", "cafeshift", "cafeboard", "cafehelp" }) do
        ns.UI.RegisterOpener(k, function() opened[#opened + 1] = k end)
    end
    for _, w in ipairs({ "menu", "shift", "board", "help" }) do
        H.send(M, "CAFUI", { { w, 1 } })
    end
    -- CAFUI shift comes once the owner's gossip started the shift: the HUD is the answer, no window over it
    H.eq(table.concat(opened, ","), "cafemenu,cafeboard,cafehelp")
end)
