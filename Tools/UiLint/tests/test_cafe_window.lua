-- The café window (CafeWindow.lua, docs/BleakholdProtocol.md section 21): the feature gate, the five tabs (Shift,
-- Recipes, Leaderboard, Rewards, How it works), the 3D model and its no-patch fallback, the shift summary card with
-- the Staff Drink, the openers CAFUI uses, and the /bh cafe model viewer. Every message goes through the real
-- receive path (Comm -> State), every intent is read back from what the addon sent.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local CAFE_BIT = { [6] = 131072 }

local function connect(M)
    FX.connect(M, H, CAFE_BIT)
end

-- The player's zone as the client knows it: the world map's area (SetMapToCurrentZone, then GetCurrentMapAreaID:
-- WorldMapArea.dbc) and its name in the client's language; a zone change fires ZONE_CHANGED_NEW_AREA.
local AREAS = { ["Stormwind City"] = 301, Sturmwind = 301, Orgrimmar = 321, Dalaran = 504 }
local function inZone(M, name)
    M.zone = name
    M.zoneArea = AREAS[name]
    M.env.SetMapToCurrentZone = function()
        M.mapArea = M.zoneArea
    end
    M.env.GetCurrentMapAreaID = function()
        return M.mapArea or 0
    end
    M.FireEvent("ZONE_CHANGED_NEW_AREA")
end

-- the café's fixtures, all of them or the named ones
local function push(M, ...)
    local ex = FX.examples(M)
    local ops = { ... }
    if #ops == 0 then
        ops = { "CAFE", "CAFST", "CAFQ", "CAFP", "CAFBF" }
    end
    for _, op in ipairs(ops) do
        H.send(M, op, ex[op])
    end
    M.Advance(0.1)
end

local function intents(M, op, from)
    local out = {}
    for _, it in ipairs(H.intents(M, from)) do
        if it.op == op then
            out[#out + 1] = it.payload
        end
    end
    return out
end

local function gets(M, from)
    local out = {}
    for _, it in ipairs(H.intents(M, from)) do
        if it.op == "GET" then
            out[#out + 1] = it.payload
        end
    end
    return table.concat(out, ";")
end

-- an off-shift CAFST: level 6 with today's caps (the fixture's first record, off shift)
local function offShift(M, level)
    H.send(M, "CAFST", { { 0, 0, level or 6, 1890, 1600, 2320 }, { "D", 210, 450, 450, 30000, 180000, 180, 400, 14 } })
    M.Advance(0.1)
end

local function visibleText(M, root, text)
    for _, o in ipairs(M.FindText(text, true)) do
        local p = o
        while p and p ~= root do p = p:GetParent() end
        if p == root then
            return true
        end
    end
    return false
end

test("café window: nothing opens without the café bit", function(M, ns)
    FX.connect(M, H)
    ns.UI.Open("cafe")
    M.Advance(0.2)
    H.ok(not M.env.BleakholdCafeFrame:IsShown(), "no café window while the realm's café is off for the player")
    ns.UI.Open("cafemenu")
    H.ok(not M.env.BleakholdCafeMenu:IsShown(), "no menu either")
end)

test("café window: opens on the Shift tab, asks for its state, and closes on a HELLO without the bit", function(M, ns)
    connect(M)
    local from = #M.sent + 1
    ns.UI.Open("cafe")
    M.Advance(0.2)
    local f = M.env.BleakholdCafeFrame
    H.ok(f:IsShown(), "the window")
    local g = gets(M, from)
    for _, topic in ipairs({ "CAFST", "CAFE", "CAFP" }) do
        H.contains(g, topic, "GET " .. topic .. " on open")
    end
    H.eq(ns.CafeWindow.tab, "shift", "the first tab")
    H.ok(ns.CafeWindow.shift:IsVisible(), "the Shift page")
    -- toggling the same key closes it
    ns.UI.Open("cafe", true)
    H.ok(not f:IsShown(), "the binding toggles it shut")
    ns.UI.Open("cafe")
    H.ok(f:IsShown(), "open again")
    H.hello(M)
    M.Advance(0.3)
    H.ok(not f:IsShown(), "a HELLO without bit 131072 hides it")
end)

test("café window: the Shift tab shows the level, today's caps, the Rush and who is on shift", function(M, ns)
    connect(M)
    push(M, "CAFE", "CAFP")
    offShift(M)
    ns.UI.Open("cafeshift")
    M.Advance(0.2)
    local sh = ns.CafeWindow.shift
    H.eq(sh.level:GetText(), "Barista 6", "the level")
    H.contains(sh.levelNote:GetText(), "430 XP to level 7", "XP to the next level")
    H.eq(sh.xp.text:GetText(), "1,890 / 2,320", "the XP bar's count")
    H.ok(math.abs(sh.xp:GetValue() - (290 / 720)) < 0.01, "the bar fills the level's share: " .. sh.xp:GetValue())
    H.eq(sh.rows.xp.bar.text:GetText(), "210 / 450", "today's XP")
    H.eq(sh.rows.xp.note:GetText(), "then up to +225 at half rate", "the half-rate allowance: half of 450 credited")
    H.eq(sh.rows.tips.money.a.copper, 30000, "today's tips in coins (the stock money frame)")
    H.eq(sh.rows.tips.money.b.copper, 180000, "of the day's cap")
    H.eq(sh.rows.tips.money.a.parts[1].coin:GetTexture(), "Interface\\MoneyFrame\\UI-GoldIcon", "the gold coin")
    H.eq(sh.rows.points.bar.text:GetText(), "180 / 400", "today's points")
    H.eq(sh.rush:GetText(), "Starts in 3:00", "the Rush countdown from CAFE")
    M.Advance(61)
    local t = sh.rush:GetText()
    H.ok(t == "Starts in 1:59" or t == "Starts in 2:00", "it ticks down locally (each second): " .. t)
    H.contains(sh.crew:GetText(), "On shift now: 1 barista", "the baristas on shift")
    H.contains(sh.crew:GetText(), "2 orders in the queue", "the queue")
    H.eq(sh.button.label:GetText(), "Start Shift", "the start button off shift")
end)

test("café window: Start shift sends CSHIFT 1,1 and End shift CSHIFT 1,0", function(M, ns)
    connect(M)
    push(M, "CAFE")
    offShift(M)
    inZone(M, "Stormwind City")
    ns.UI.Open("cafe")
    M.Advance(3)
    local sh = ns.CafeWindow.shift
    sh.button:Click()
    M.Advance(0.1)
    local sent = intents(M, "CSHIFT")
    H.eq(sent[#sent], "1,1", "start a shift at the player's own café")
    -- on shift (CAFST onShift 1), the same button ends it
    push(M, "CAFST")
    H.eq(sh.button.label:GetText(), "End Shift", "End shift while on shift")
    M.Advance(3)
    sh.button:Click()
    M.Advance(0.1)
    sent = intents(M, "CSHIFT")
    H.eq(sent[#sent], "1,0", "end the shift at the café of the shift")
end)

test("café window: a Horde player's café is The Grinding Tusk; a paused café blocks Start shift", function(M, ns)
    M.env.UnitFactionGroup = function() return "Horde", "Horde" end
    connect(M)
    offShift(M)
    -- café 2 paused (open 2): danger nearby
    H.send(M, "CAFE", { { 1, 1, 0, 0, 0, "", 45 }, { 2, 2, 0, 0, 0, "", 60 } })
    M.Advance(0.1)
    ns.UI.Open("cafe")
    M.Advance(0.2)
    local cw = ns.CafeWindow
    H.contains(cw.kicker.name:GetText(), "The Grinding Tusk", "the Horde café's name in the title bar")
    H.eq(cw.kicker.emblem:GetTexture(), "Interface\\TargetingFrame\\UI-PVP-Horde", "the Horde emblem")
    H.ok(not cw.shift.button.enabled, "no Start shift while the café is paused")
    H.contains(cw.shift.note:GetText(), "Danger nearby", "the reason is written")
end)

test("café window: the hero machine shows as a model with patch-4 and as a ring of stations without", function(M, ns)
    connect(M)
    push(M, "CAFE")
    offShift(M)
    ns.UI.Open("cafe")
    M.Advance(0.2)
    local sh = ns.CafeWindow.shift
    H.ok(sh.model:IsShown(), "the model with the patch")
    H.eq(sh.model.__model, ns.CafeData.models[1].path, "the Stormwind espresso machine")
    H.eq(sh.model.__modelScale, ns.CafeData.models[1].scale, "its scale")
    H.ok(not sh.ring:IsShown(), "no fallback")
    H.contains(sh.caption.name:GetText(), "Royal Brass Engine", "the machine's name over the model")
    local f0 = sh.model:GetFacing()
    M.Advance(2)
    H.ok(sh.model:GetFacing() > f0, "a slow spin")
    -- motion off: no spin
    ns.db.options.cafeMotion = false
    local f1 = sh.model:GetFacing()
    M.Advance(2)
    H.eq(sh.model:GetFacing(), f1, "reduced motion stops the spin")
end)

-- Cafe.PatchPresent probes once (the first icon asks): the patch is missing from the start
test("café window: without patch-4 (the probe misses) the 3D model is hidden", function(M, ns)
    connect(M)
    push(M, "CAFE")
    offShift(M)
    ns.UI.Open("cafe")
    M.Advance(0.2)
    local sh = ns.CafeWindow.shift
    H.ok(not ns.Cafe.PatchPresent(), "the probe missed")
    H.ok(not sh.model:IsShown(), "no model")
    H.ok(sh.ring:IsShown(), "the stations in a ring")
    H.eq(#sh.ring.stations, 7, "seven stations")
    H.eq(sh.ring.stations[1].name:GetText(), "Grinder", "the stations' names")
    H.eq(sh.ring.stations[1].icon:GetTexture(), "Interface\\Icons\\INV_Gizmo_02", "a stock icon per station")
end, { before = function(M) M.missingTextures["Interface\\Icons\\BH_Cafe_Espresso"] = true end })

-- the Shift tab leaves no empty quadrant: the box fills the right side beside the whole left column, rules included
test("café window: the hero machine's box reaches the Start Shift row; the rules stay beside it", function(M, ns)
    connect(M)
    push(M, "CAFE")
    offShift(M)
    ns.UI.Open("cafeshift")
    M.Advance(0.2)
    local cw = ns.CafeWindow
    local sh = cw.shift
    local _, _, _, sx, sy = sh.stage:GetPoint(1)
    local _, _, _, _, by = sh.button:GetPoint(1)
    local stageBottom = -sy + sh.stage:GetHeight()
    local buttonTop = cw.BH - by - sh.button:GetHeight()
    H.eq(stageBottom + cw.STAGE_GAP, buttonTop, "the box ends one gap above the Start Shift row")
    H.ok(cw.STAGE_GAP <= 16, "just above it")
    H.ok(sh.stage:GetHeight() > 400, "taller than the old 300 box: the lower right is the box's")
    -- the rules wrap inside the left column, clear of the box
    local stageLeft = cw.BW + sx - sh.stage:GetWidth()
    for i, t in ipairs(sh.rules) do
        local _, _, _, tx = t:GetPoint(1)
        local left = i == 1 and tx or cw.PAD + 18
        H.ok(left + t:GetWidth() + 12 <= stageLeft, "rule " .. i .. " stays clear of the box")
        H.eq(t.num:GetText(), i .. ".", "its number")
    end
    -- the station ring spreads over the taller box, every icon and name inside it and above the note
    local halfW, halfH = sh.stage:GetWidth() / 2, sh.stage:GetHeight() / 2
    local top, bottom = -math.huge, math.huge
    for _, s in ipairs(sh.ring.stations) do
        local _, _, _, x, y = s:GetPoint(1)
        H.ok(math.abs(x) + s:GetWidth() / 2 <= halfW - 20, s.letter .. ": inside the box's sides")
        H.ok(y + s:GetWidth() / 2 <= halfH - 16, s.letter .. ": under the box's top")
        H.ok(y - s:GetWidth() / 2 - 16 >= -halfH + 24, s.letter .. ": its name above the note")
        top, bottom = math.max(top, y), math.min(bottom, y)
    end
    H.ok(top - bottom >= halfH, "the ring uses the box's height")
    -- the developer's viewer frames models in a box of the same size, so its modelFrame values hold here
    cw.ShowModelViewer("EspressoSW")
    local mv = M.env.BleakholdCafeModelViewer
    H.eq(mv.box:GetWidth(), sh.stage:GetWidth(), "the viewer's box as wide")
    H.eq(mv.box:GetHeight(), sh.stage:GetHeight(), "and as tall")
end)

test("café window: Recipes shows cards per family with tier stars, price, steps and locks", function(M, ns)
    connect(M)
    offShift(M, 2)
    ns.UI.Open("caferecipes")
    M.Advance(0.2)
    local rc = ns.CafeWindow.recipes
    H.ok(rc:IsVisible(), "the Recipes page")
    H.eq(rc.cards.used, 19, "every drink of The Lion's Roast")
    H.contains(rc.summary:GetText(), "7 of 19 recipes unlocked at barista level 2", "the unlocked count")
    rc.filter.buttons[2]:Click()
    H.eq(rc.cards.used, 7, "seven coffees")
    rc.filter.buttons[3]:Click()
    H.eq(rc.cards.used, 6, "six teas")
    rc.filter.buttons[4]:Click()
    H.eq(rc.cards.used, 6, "six milkshakes")
    -- the Champion's Triple Scoop: tier 5, locked until level 10, three scoops as one icon with x3
    local triple
    for i = 1, rc.cards.used do
        local c = rc.cards.items[i]
        if c.recipe.id == 119 then triple = c end
    end
    H.ok(triple, "the triple scoop card")
    H.eq(triple.name:GetText(), "Champion's Triple Scoop", "its name")
    H.eq(triple.stars.count, 5, "five stars")
    H.ok(triple.lock:IsShown(), "locked at level 2")
    H.eq(triple.need:GetText(), "Barista level 10", "the level it needs")
    H.ok(triple.item.icon:IsDesaturated(), "a locked drink's icon is grey")
    H.eq(triple.steps[1].count:GetText(), "×3", "three scoops merged into one icon")
    H.eq(triple.steps[1].icon:GetTexture(), "Interface\\Icons\\INV_Misc_Food_31", "the scoop's icon")
    H.ok(triple.steps[6]:IsShown() and not triple.steps[7]:IsShown(), "six step icons for eight steps")
    H.eq(triple.money.copper, ns.Cafe.Price(119), "the price in coins")
    -- a step icon's tooltip names the action and its station
    M.Hover(triple.steps[1])
    local tip = M.env.GameTooltip
    H.contains(table.concat(tip.__lines or {}, "|"), "Scoop Ice Cream", "the action")
    H.contains(table.concat(tip.__lines or {}, "|"), "Cold Box", "the station")
    -- an unlocked one has no lock
    rc.filter.buttons[1]:Click()
    H.ok(not rc.cards.items[1].lock:IsShown(), "Cathedral Black is open at level 2")
end)

test("café window: the Leaderboard asks for LBQ C, draws only the shown café's week, pins your row", function(M, ns)
    connect(M)
    push(M, "CAFP")
    local from = #M.sent + 1
    ns.UI.Open("cafeboard")
    M.Advance(0.2)
    local lbq = intents(M, "LBQ", from)
    H.eq(lbq[#lbq], "C,0,1,0,1", "this week's board of The Lion's Roast")
    local bd = ns.CafeWindow.board
    -- an answer for the other café is not drawn
    H.send(M, "LB", { { "C", 2964, 2, 0, 1, 1 }, { 1, 2, 1990, 700, M.epoch, { { "Morgra", 1 } }, "88 drinks" } })
    M.Advance(0.1)
    H.ok(not bd.table.rows[1]:IsShown(), "café 2's board is not the one shown")
    H.send(M, "LB", { { "C", 2964, 1, 0, 1, 1 },
        { 1, 1, 2310, 812, M.epoch - 60, { { "Brenna", 2 } }, "142 drinks" },
        { 2, 1, 1830, 790, M.epoch - 600, { { "Aldric", 1 } }, "96 drinks" },
        { 4, 1, 900, 600, M.epoch - 900, { { "Corwin", 5 } }, "51 drinks" } })
    H.send(M, "LBME", { { "C", 2, 40, 1830, 1, 790, 792, "96 drinks" } })
    M.Advance(0.1)
    local r1 = bd.table.rows[1]
    H.ok(r1:IsShown(), "the first row")
    H.ok(r1.medal:IsShown(), "the podium as a medal")
    H.eq(r1.medal.rank:GetText(), "1", "rank 1")
    H.contains(r1.cells[2]:GetText(), "Brenna", "the name")
    H.contains(r1.cells[2]:GetText(), "|cff", "in the class colour")
    H.eq(r1.cells[3]:GetText(), "2,310", "points")
    H.eq(r1.cells[4]:GetText(), "142 drinks", "drinks from the label")
    H.eq(r1.cells[5]:GetText(), "81%", "Perfect from permille")
    local r3 = bd.table.rows[3]
    H.ok(not r3.medal:IsShown(), "no medal from rank 4")
    H.eq(r3.cells[1]:GetText(), "4", "the rank as a number")
    H.eq(bd.table.me.medal.rank:GetText(), "2", "your row: rank 2, pinned")
    H.eq(bd.table.me.cells[3]:GetText(), "1,830", "your points")
    H.contains(bd.aside.value:GetText(), "1,830 points", "your week from CAFP W")
    H.contains(bd.aside.detail:GetText(), "Rank 2", "your rank")
    H.contains(bd.aside.lastName:GetText(), "Brenna", "last week's Best Barista")
    -- the city switch: The Grinding Tusk's board
    from = #M.sent + 1
    bd.city.buttons[2]:Click()
    M.Advance(0.1)
    lbq = intents(M, "LBQ", from)
    H.eq(lbq[#lbq], "C,0,2,0,1", "the other café")
    H.ok(not bd.table.rows[1]:IsShown(), "café 1's rows are not shown for café 2")
    -- last week: CAFP W's week id - 1
    from = #M.sent + 1
    bd.weekSel.buttons[2]:Click()
    M.Advance(0.1)
    lbq = intents(M, "LBQ", from)
    H.eq(lbq[#lbq], "C,2963,2,0,1", "last week")
end)

test("café window: Rewards shows the level ladder, the aprons on the player, titles and lifetime", function(M, ns)
    M.items[909380] = { name = "Apprentice's Apron" }
    M.items[909382] = { name = "Master Barista's Apron" }
    M.items[909384] = { name = "Golden Apron" }
    connect(M)
    push(M, "CAFP")
    ns.UI.Open("caferewards")
    M.Advance(0.2)
    local rw = ns.CafeWindow.rewards
    H.ok(rw:IsVisible(), "the Rewards page")
    H.ok(not rw.nodes[6].badge.icon:IsDesaturated(), "level 6 reached")
    H.ok(rw.nodes[6].check:IsShown(), "with its check")
    H.ok(rw.nodes[7].badge.icon:IsDesaturated(), "level 7 not yet")
    H.ok(not rw.nodes[7].check:IsShown(), "no check")
    -- the aprons on the player's own model: 909380 (the Lion's Roast), 909382, 909384
    local tried = {}
    for _, id in ipairs(M.tryOn) do tried[id] = true end
    H.ok(tried[909384], "the Golden Apron tried on")
    for _, box in ipairs(rw.aprons) do
        H.eq(box.model.__unit, "player", "the player's model")
    end
    H.eq(rw.aprons[1].item, 909380, "the Lion's Roast's Apprentice's Apron")
    H.eq(rw.aprons[1].state:GetText(), "Earned", "rewards bit 1: earned")
    H.eq(rw.aprons[2].state:GetText(), "At barista level 10", "the master apron not yet")
    H.contains(rw.titles[1].name:GetText(), "the Barista", "the title")
    H.eq(rw.titles[1].state:GetText(), "At barista level 10", "not earned")
    H.eq(rw.titles[2].state:GetText(), "3 weekly wins: 0/3", "Café Legend's progress")
    H.contains(rw.life[1]:GetText(), "412", "lifetime drinks")
    H.contains(rw.life[2]:GetText(), "73%", "Perfect share")
    H.contains(rw.life[3]:GetText(), "×14", "best streak")
    H.contains(rw.life[4]:GetText(), "5.1 s", "fastest drink")
    -- a level reached later: CAFP level 10 with every reward
    H.send(M, "CAFP", { { 10, 5700, 5640, "", 900, 700, 12, 20, 4800, 3, 31 } })
    M.Advance(0.1)
    H.ok(rw.nodes[10].check:IsShown(), "level 10")
    H.eq(rw.titles[2].state:GetText(), "Earned", "Café Legend earned")
end)

test("café window: How it works has six sections, with today's XP caps, the keys and the options", function(M, ns)
    connect(M)
    H.send(M, "CAFST", { { 0, 0, 3, 400, 320, 620 }, { "D", 0, 500, 250, 0, 100000, 0, 300, 0 } })
    M.Advance(0.1)
    ns.UI.Open("cafehelp")
    M.Advance(0.2)
    local hp = ns.CafeWindow.help
    H.ok(hp:IsVisible(), "the page")
    H.eq(#hp.sections, 6, "six sections")
    H.eq(hp.sections[1].head:GetText(), "Shifts", "the first heading")
    H.contains(hp.sections[4].text:GetText(), "first 500 XP", "the server's full-rate XP")
    H.contains(hp.sections[4].text:GetText(), "next 250 at half rate", "and the half rate")
    local shifts = hp.sections[1].text:GetText()
    H.contains(shifts, "idle for two minutes while holding a ticket (five without one)", "the server's idle rules")
    H.contains(shifts, "go AFK")
    H.contains(shifts, "Keys 1 to 8 press the barista bar")
    H.eq(hp.sections[5].head:GetText(), "Ordering a Drink")
    H.contains(hp.sections[5].text:GetText(), "walk to the counter or sit at a café table to pick it up")
    H.eq(hp.sections[6].head:GetText(), "Options")
    for _, cmd in ipairs({ "/bh cafe keys", "/bh cafe scale", "/bh cafe sound", "/bh cafe motion", "/bh cafe memory",
        "/bh cafe autoselect" }) do
        H.contains(hp.sections[6].text:GetText(), cmd)
    end
    -- remapped keys: the help names them
    M.env.SlashCmdList.BLEAKHOLD("cafe keys q,w,e,r,t,y,u,i")
    M.Advance(0.2)
    hp:Refresh()
    H.contains(hp.sections[1].text:GetText(), "Your café keys (Q, W, E, R, T, Y, U, I) press the barista bar")
end)

test("café window: CAFUI opens the menu, the shift, the board and the help", function(M, ns)
    connect(M)
    push(M, "CAFE")
    local cw = ns.CafeWindow
    for what, tab in pairs({ board = "board", help = "help" }) do
        cw.frame:Hide()
        H.send(M, "CAFUI", { { what, 1 } })
        M.Advance(0.1)
        H.ok(cw.frame:IsShown(), "CAFUI " .. what .. " opens the café window")
        H.eq(cw.tab, tab, "on the " .. tab .. " tab")
    end
    H.send(M, "CAFUI", { { "menu", 1 } })
    M.Advance(0.1)
    H.ok(M.env.BleakholdCafeMenu:IsShown(), "CAFUI menu opens the menu")
    -- CAFUI shift: the shift has started (the owner's gossip); the window would cover the bar and the ticket
    cw.frame:Hide()
    H.send(M, "CAFUI", { { "shift", 1 } })
    M.Advance(0.6)
    H.ok(not cw.frame:IsShown(), "CAFUI shift leaves the window shut")
    local told = false
    for _, c in ipairs(M.chat) do
        if c.frame == M.env.UIErrorsFrame and c.msg == ns.Cafe.SHIFT_STARTED_TEXT then
            told = true
        end
    end
    H.ok(told, "the start is told in the error frame")
end)

test("café window: the shift summary card, its reason, and the Staff Drink", function(M, ns)
    connect(M)
    offShift(M, 7)
    -- a combat end with the Staff Drink on offer
    H.send(M, "CAFSUM", { { 1, "C", 1840, 14, 9, 10600, 212, 40, 190, 4, 1 } })
    M.Advance(0.1)
    local s = M.env.BleakholdCafeSummary
    H.ok(s:IsShown(), "CAFSUM opens the card")
    H.eq(s:GetFrameStrata(), "DIALOG", "on the dialog strata")
    H.eq(s.reason:GetText(), "Combat ended your shift.", "the reason")
    H.contains(s.lines[1]:GetText(), "30:40", "the shift's length")
    H.contains(s.lines[3]:GetText(), "9 (64%)", "Perfect drinks and share")
    H.eq(s.tips.copper, 10600, "the tips in coins")
    H.contains(s.cap:GetText(), "40 XP", "what the daily cap took")
    H.ok(s.staff:IsShown(), "the Staff Drink choice")
    local coffee = s.staff.choices[1]
    H.contains(coffee.name:GetText(), "Cathedral Black", "the lowest coffee of level 7")
    s.staff.choices[3]:Click()
    M.Advance(0.1)
    local sent = intents(M, "CSTAFF")
    H.eq(sent[#sent], "114", "the lowest shake unlocked: the Vanilla Lion Cub")
    H.ok(s.staff.choices[3].chosen:IsShown(), "the chosen one is lit")
    s.staff.choices[1]:Click()
    M.Advance(0.1)
    H.eq(#intents(M, "CSTAFF"), 1, "one Staff Drink only")
    -- a plain end: no choice
    H.send(M, "CAFSUM", { { 1, "E", 600, 3, 1, 900, 40, 0, 30, 1, 0 } })
    M.Advance(0.1)
    H.ok(not s.staff:IsShown(), "no Staff Drink without staffDrink")
    H.eq(s.reason:GetText(), "You ended your shift.", "ended by the player")
end)

-- the point a region hangs from: point, relative region, relative point, x, y
local function point(r)
    return r:GetPoint(1)
end

test("café window: the summary card is as tall as what it shows; the Staff Drink is one column of rows", function(M, ns)
    connect(M)
    offShift(M, 7)
    local cw = ns.CafeWindow
    local s = M.env.BleakholdCafeSummary
    -- no Staff Drink, XP over the cap: the stats, the cap line, Close
    H.send(M, "CAFSUM", { { 1, "C", 1840, 14, 9, 10600, 212, 40, 190, 4, 0 } })
    M.Advance(0.1)
    H.ok(not s.staff:IsShown(), "no Staff Drink")
    H.eq(s:GetHeight(), cw.SummaryHeight(true, false), "the plain card fits its lines")
    H.ok(s:GetHeight() <= 260, "the plain card is short: " .. s:GetHeight())
    local i = ns.UI.WINDOW_INSETS
    local free = s:GetHeight() - i.top - i.bottom - (cw.SUM_STATS_BOTTOM + cw.SUM_CAP_GAP + cw.SUM_CAP_H)
        - cw.SUM_CLOSE_H - 2
    H.eq(free, cw.SUM_CLOSE_GAP, "only the close gap between the cap line and Close")
    -- nothing over the cap: the cap line goes and the card shrinks again
    H.send(M, "CAFSUM", { { 1, "E", 600, 3, 1, 900, 40, 0, 30, 1, 0 } })
    M.Advance(0.1)
    H.ok(not s.cap:IsShown(), "no cap line")
    H.eq(s:GetHeight(), cw.SummaryHeight(false, false), "without the cap line")
    H.ok(cw.SummaryHeight(false, false) < cw.SummaryHeight(true, false), "shorter")
    -- the Staff Drink without a cap line: straight under the stats
    H.send(M, "CAFSUM", { { 1, "E", 600, 3, 1, 900, 40, 0, 30, 1, 1 } })
    M.Advance(0.1)
    H.ok(s.staff:IsShown(), "the Staff Drink")
    H.eq(s:GetHeight(), cw.SummaryHeight(false, true), "the card fits the choices")
    H.eq(select(5, point(s.staff)), -(cw.SUM_STATS_BOTTOM + cw.SUM_STAFF_GAP), "under the stats")
    -- one full-width row per family, the name on one line
    local c = s.staff.choices
    H.eq(#c, 3, "three choices")
    local _, _, _, x1, y1 = point(c[1])
    for k = 2, 3 do
        local _, _, _, x, y = point(c[k])
        H.eq(x, x1, "row " .. k .. " in the same column")
        H.eq(y, y1 - (k - 1) * cw.SUM_CHOICE_PITCH, "row " .. k .. " under the one before")
        H.eq(c[k]:GetWidth(), c[1]:GetWidth(), "as wide")
    end
    H.eq(c[1]:GetWidth(), cw.SUM_W - 28 - 24, "the card's width")
    H.contains(c[3].name:GetText(), "Vanilla Lion Cub", "the shake")
    H.ok(c[3].name:GetStringWidth() <= c[3].name:GetWidth(), "the name fits one line")
    H.eq(c[3].tag:GetText(), "Shake", "the family at the row's end, singular as Coffee and Tea")
    -- the cap line and the Staff Drink: the choices move under the cap line
    H.send(M, "CAFSUM", { { 1, "C", 1840, 14, 9, 10600, 212, 40, 190, 4, 1 } })
    M.Advance(0.1)
    H.eq(s:GetHeight(), cw.SummaryHeight(true, true), "both")
    H.eq(select(5, point(s.staff)), -(cw.SUM_STATS_BOTTOM + cw.SUM_CAP_GAP + cw.SUM_CAP_H + cw.SUM_STAFF_GAP),
        "under the cap line")
end)

test("café window: the tabs are as wide as their labels with room each side, and stock-tall", function(M, ns)
    connect(M)
    ns.UI.Open("cafeshift")
    M.Advance(0.2)
    local cw, K = ns.CafeWindow, ns.CafeKit
    local right = 0
    for _, b in ipairs(cw.tabs) do
        H.eq(b:GetHeight(), K.TAB_H, b.label:GetText() .. ": the tab's height")
        local want = math.max(K.TAB_MIN, math.ceil(b.label:GetStringWidth() + K.TAB_PAD))
        H.eq(b:GetWidth(), want, b.label:GetText() .. ": its label and 12 px of air inside each rim")
        local _, _, _, x = point(b)
        right = math.max(right, x + b:GetWidth())
    end
    H.ok(right < cw.W - 28, "the strip fits the window: " .. right)
    H.eq(cw.BH, cw.H - 58 - K.STRIP_H, "the body under the strip")
    -- the menu's tabs are the same strip
    ns.UI.Open("cafemenu")
    M.Advance(0.2)
    for _, b in ipairs(ns.CafeMenu.tabs) do
        H.eq(b:GetHeight(), K.TAB_H, "menu tab " .. b.label:GetText())
        H.ok(b:GetWidth() >= K.TAB_MIN, "at least the least width")
    end
end)

test("café window: Last Week retitles the side panel and drops this week's bar and days", function(M, ns)
    connect(M)
    push(M, "CAFP")
    ns.UI.Open("cafeboard")
    M.Advance(0.2)
    local bd = ns.CafeWindow.board
    local aside = bd.aside
    H.send(M, "LB", { { "C", 2964, 1, 0, 1, 1 }, { 2, 1, 1830, 790, M.epoch - 600, { { "Aldric", 1 } }, "96 drinks" } })
    H.send(M, "LBME", { { "C", 2, 40, 1830, 1, 790, 792, "96 drinks" } })
    M.Advance(0.1)
    H.eq(aside.label:GetText(), "Your Week", "this week")
    H.ok(aside.bar:IsShown(), "the bar against the first")
    H.ok(aside.days:IsShown(), "the days worked")
    local _, rel = point(aside.days)
    H.ok(rel == aside.bar, "the days under the bar")
    -- last week: LBME of that week's board
    bd.weekSel.buttons[2]:Click()
    M.Advance(0.1)
    H.send(M, "LB", { { "C", 2963, 1, 0, 1, 1 },
        { 1, 1, 2480, 834, M.epoch - 7 * 86400, { { "Brenna", 2 } }, "151 drinks" },
        { 3, 1, 1520, 770, M.epoch - 7 * 86400, { { "Aldric", 1 } }, "81 drinks" } })
    H.send(M, "LBME", { { "C", 3, 60, 1520, 1, 770, 613, "81 drinks" } })
    M.Advance(0.1)
    H.eq(aside.label:GetText(), "Your Last Week", "retitled for the week shown")
    H.contains(aside.value:GetText(), "1,520 points", "last week's points")
    H.contains(aside.detail:GetText(), "Rank 3", "last week's rank")
    H.contains(aside.detail:GetText(), "81 drinks", "last week's drinks")
    H.ok(not aside.bar:IsShown(), "no bar")
    H.ok(not aside.days:IsShown(), "no days worked (CAFP has this week's only)")
    local _, under, _, _, gap = point(aside.state)
    H.ok(under == aside.detail, "the state straight under the rank line")
    H.eq(gap, -8, "with the lines' own gap")
    local _, lastUnder = point(aside.lastLabel)
    H.ok(lastUnder == aside.state, "last week's Best Barista under the state")
    -- back to this week
    bd.weekSel.buttons[1]:Click()
    M.Advance(0.1)
    H.eq(aside.label:GetText(), "Your Week", "back")
    H.ok(aside.days:IsShown(), "the days again")
end)

test("café window: the model viewer loads a café model by name and moves it", function(M, ns)
    connect(M)
    local cw = ns.CafeWindow
    H.ok(not cw.ShowModelViewer("NotAModel"), "an unknown name is refused")
    H.ok(cw.ShowModelViewer("grindersw"), "names in any case")
    local mv = M.env.BleakholdCafeModelViewer
    H.ok(mv:IsShown(), "the viewer")
    H.eq(mv.model.__model, "World\\Bleakhold\\Cafe\\GrinderSW\\BH_Cafe_GrinderSW.m2", "the file of spec 5.8")
    H.contains(mv.line:GetText(), "position {0.00, 0.00, 0.00} scale 1.00 facing 0.00", "the live line")
    cw.ShowModelViewer("EspressoSW")
    H.contains(mv.line:GetText(), "position {0.00, 0.00, -0.35} scale 1.60 facing 0.40", "CafeData's view")
    mv.buttons[2]:Click()       -- X +
    H.contains(mv.line:GetText(), "position {0.10, 0.00, -0.35}", "X moved")
    local printed = false
    for _, c in ipairs(M.chat) do
        if c.msg:find("EspressoSW: position {0.10", 1, true) then printed = true end
    end
    H.ok(printed, "printed to chat for copying")
    -- the slash command (Cafe.lua fires CAFE_MODEL with the name)
    M.env.SlashCmdList.BLEAKHOLD("cafe model CupSW")
    M.Advance(0.1)
    H.eq(mv.model.__model, "World\\Bleakhold\\Cafe\\CupSW\\BH_Cafe_CupSW.m2", "/bh cafe model CupSW")
end)

test("café window: every tab renders from the fixtures without errors", function(M, ns)
    connect(M)
    push(M)
    local ex = FX.examples(M)
    for _, op in ipairs({ "CAFT", "CAFEV", "CAFRES", "CAFM", "CAFO", "CAFSUM", "CAFAT" }) do
        H.send(M, op, ex[op])
    end
    M.Advance(0.2)
    for _, key in ipairs({ "cafeshift", "caferecipes", "cafeboard", "caferewards", "cafehelp" }) do
        ns.UI.Open(key)
        M.Advance(0.3)
    end
    H.eq(#M.errors, 0, "no Lua errors")
end)

-- The windows use the client's own art only (PLAN decision 1): every texture they set (and the café HUD's, shown
-- too) is a file of the stock folders tests/test_static.lua allows (its list and rule, copied), never the addon's.
local STOCK_PREFIXES = {
    "Minimap\\Tracking",
    "DialogFrame", "Tooltips", "Buttons", "Minimap", "TargetingFrame", "LFGFrame", "QuestFrame", "PaperDollInfoFrame",
    "AchievementFrame", "Common", "Icons", "ChatFrame", "PVPFrame", "CharacterFrame", "OptionsFrame", "FriendsFrame",
    "WorldStateFrame", "MoneyFrame", "Glues\\CharacterCreate", "CastingBar", "RaidFrame",
}
local function stockPath(path)
    local low = path:lower()
    for _, p in ipairs(STOCK_PREFIXES) do
        local pre = "interface\\" .. p:lower() .. "\\"
        if low:sub(1, #pre) == pre then
            local name = path:sub(#pre + 1)
            return name:match("^[%w_%-!]+$") ~= nil and not name:find("%.%a%a%a$")
        end
    end
    return false
end
test("café window: every texture of the café's windows is stock art", function(M, ns)
    connect(M)
    push(M)
    M.items[909380] = { name = "Apprentice's Apron" }
    M.textures = {}
    for _, key in ipairs({ "cafeshift", "caferecipes", "cafeboard", "caferewards", "cafehelp", "cafemenu" }) do
        ns.UI.Open(key)
        M.Advance(0.3)
    end
    H.send(M, "CAFSUM", { { 1, "C", 1840, 14, 9, 10600, 212, 40, 190, 4, 1 } })
    ns.CafeWindow.ShowModelViewer("CupSW")
    M.Advance(0.3)
    local n = 0
    for path in pairs(M.textures) do
        H.ok(stockPath(path), "stock art only: " .. path)
        n = n + 1
    end
    H.ok(n > 30, "the windows set their textures: " .. n)
end)

-- an off-shift CAFST with flags (16: the Staff Drink can be claimed)
local function offShiftFlags(M, level, flags)
    H.send(M, "CAFST", { { 0, 0, level or 7, 1890, 1600, 2320, "", "", "", "", "", "", "", "", "", "", "", flags or "" },
        { "D", 210, 450, 450, 30000, 180000, 180, 400, 14 } })
    M.Advance(0.1)
end

test("café window: the Staff Drink is pending until the server confirms it; a refusal gives the choice back", function(M, ns)
    connect(M)
    offShiftFlags(M, 7, 16)
    H.send(M, "CAFSUM", { { 1, "C", 1840, 14, 9, 10600, 212, 40, 190, 4, 1 } })
    M.Advance(0.1)
    local s = M.env.BleakholdCafeSummary
    local c = s.staff.choices
    c[2]:Click()
    M.Advance(0.1)
    H.eq(#intents(M, "CSTAFF"), 1, "CSTAFF sent")
    H.ok(c[2].chosen:IsShown(), "the choice lit while it is asked for")
    H.ok(not c[1]:IsEnabled() and not c[3]:IsEnabled(), "the others wait")
    H.eq(s.staff.note:GetText(), "Asking for your Staff Drink...", "not claimed yet")
    -- ERR CSTAFF: nothing changed, the choice is back
    H.send(M, "ERR", { { "CSTAFF", ns.Comm.lastSeq, "cafe_staff", "No Staff Drink for you right now." } })
    M.Advance(0.1)
    H.ok(not c[2].chosen:IsShown(), "no longer lit")
    H.ok(c[1]:IsEnabled() and c[2]:IsEnabled() and c[3]:IsEnabled(), "every choice again")
    H.eq(s.staff.note:GetText(), "A free drink of your choice, once a day.")
    H.ok(not visibleText(M, s, "Enjoy your Staff Drink."), "never told it worked")
    -- again, past the send gate: CAFST without flag 16 confirms it
    M.Advance(3)
    c[1]:Click()
    M.Advance(0.1)
    H.eq(#intents(M, "CSTAFF"), 2, "sent again")
    offShiftFlags(M, 7, "")
    H.eq(s.staff.note:GetText(), "Enjoy your Staff Drink.", "confirmed by the server")
    H.ok(c[1].chosen:IsShown() and not c[2]:IsEnabled(), "kept")
end)

test("café window: a Staff Drink with no answer gives the choice back; CAFBF with its timer confirms it", function(M, ns)
    connect(M)
    offShiftFlags(M, 7, 16)
    H.send(M, "CAFSUM", { { 1, "C", 1840, 14, 9, 10600, 212, 40, 190, 4, 1 } })
    M.Advance(0.1)
    local s = M.env.BleakholdCafeSummary
    local c = s.staff.choices
    c[2]:Click()
    M.Advance(ns.CafeWindow.STAFF_WAIT + 0.5)
    H.ok(c[2]:IsEnabled() and not c[2].chosen:IsShown(), "no answer: the choice is back")
    c[2]:Click()
    M.Advance(0.1)
    H.send(M, "CAFBF", { { "", 2400, "", 0, 1 } })
    M.Advance(0.1)
    H.eq(s.staff.note:GetText(), "Enjoy your Staff Drink.", "the tea's buff is on")
end)

test("café window: Claim Staff Drink on the Shift tab while flag 16 is set opens the choice again", function(M, ns)
    connect(M)
    push(M, "CAFE")
    offShiftFlags(M, 7, "")
    ns.UI.Open("cafeshift")
    M.Advance(0.2)
    local sh = ns.CafeWindow.shift
    H.ok(not sh.claim:IsShown(), "nothing to claim")
    offShiftFlags(M, 7, 16)
    M.Advance(0.2)
    ns.CafeWindow.Refresh()
    H.ok(sh.claim:IsShown(), "Claim Staff Drink beside Start Shift")
    local s = M.env.BleakholdCafeSummary
    H.ok(not s:IsShown())
    sh.claim:Click()
    M.Advance(0.1)
    H.ok(s:IsShown() and s.staff:IsShown(), "the card with the choice")
    H.eq(s.title:GetText(), "Staff Drink", "no summary since the /reload: the choice alone")
    H.ok(not s.lines[1]:IsShown(), "no stats")
    H.eq(s:GetHeight(), ns.CafeWindow.SummaryHeight(false, true, true))
    s.staff.choices[1]:Click()
    M.Advance(0.1)
    H.eq(#intents(M, "CSTAFF"), 1)
end)

test("café window: Order a Drink opens the menu, as /bh cafe menu does; How It Works names the real routes",
    function(M, ns)
    connect(M)
    push(M, "CAFE")
    offShift(M)
    ns.UI.Open("cafe")
    M.Advance(0.2)
    local cw = ns.CafeWindow
    H.ok(cw.orderBtn:IsShown(), "off shift: Order a Drink in the title bar")
    H.eq(cw.orderBtn.label:GetText(), "Order a Drink")
    cw.orderBtn:Click()
    M.Advance(0.2)
    H.ok(M.env.BleakholdCafeMenu:IsShown(), "the menu opens")
    H.ok(not cw.frame:IsShown(), "in the window's place")
    M.env.BleakholdCafeMenu:Hide()
    M.env.SlashCmdList.BLEAKHOLD("cafe menu")
    M.Advance(0.2)
    H.ok(M.env.BleakholdCafeMenu:IsShown(), "/bh cafe menu")
    M.env.BleakholdCafeMenu:Hide()
    ns.UI.Open("cafehelp")
    M.Advance(0.2)
    local hp = cw.help
    hp:Refresh()
    local order = hp.sections[5].text:GetText()
    H.contains(order, "Talk to Rosalind Thornbury, or press Order a Drink at the top of this window")
    H.ok(not order:find("button", 1, true), "no button that does not exist")
    local keys = hp.sections[2].text:GetText()
    H.contains(keys, "Both end your Perfect streak")
    H.contains(keys, "A player's order goes to the house after a second ruin")
    H.contains(hp.sections[3].text:GetText(), "a player's order goes to the house")
    -- the today rows and the summary say whose money they count
    H.eq(cw.shift.rows.tips.label:GetText(), "NPC tips (daily cap)")
    H.eq(cw.SUM_LINES[5], "Earned")
    -- on shift: a barista does not order
    push(M, "CAFST")
    M.Advance(0.2)
    H.ok(ns.Cafe.OnShift())
    H.ok(not cw.orderBtn:IsShown(), "no ordering on shift")
end)

test("café window: the Shift tab finds the café's city on any client language", function(M, ns)
    connect(M)
    push(M, "CAFE")
    offShift(M)
    inZone(M, "Sturmwind")
    ns.UI.Open("cafeshift")
    M.Advance(0.2)
    local sh = ns.CafeWindow.shift
    H.ok(not (sh.note:GetText() or ""):find("Go to", 1, true), "in Sturmwind (deDE): no 'Go to': " .. sh.note:GetText())
    inZone(M, "Dalaran")
    sh:Refresh()
    H.eq(sh.note:GetText(), "Go to The Lion's Roast to start.")
end)

test("café window: the Tired note goes once its rest has run down", function(M, ns)
    connect(M)
    push(M, "CAFE")
    inZone(M, "Stormwind City")
    H.send(M, "CAFST", { { 0, 0, 6, 1890, 1600, 2320, "", "", "", "", "", "", "", "", "", "", 3, 4 },
        { "D", 210, 450, 450, 30000, 180000, 180, 400, 14 } })
    ns.UI.Open("cafeshift")
    M.Advance(0.2)
    local sh = ns.CafeWindow.shift
    H.contains(sh.note:GetText(), "more rest")
    M.Advance(5, 0.5)
    H.ok(not (sh.note:GetText() or ""):find("Tired", 1, true), "rested: the next shift pays in full: "
        .. tostring(sh.note:GetText()))
    H.eq(ns.CafeWindow.TiredNote(ns.S.cafeState), nil)
end)

test("café window: the café's confirmation wraps at its own width (sized for the lines it draws)", function(M, ns)
    connect(M)
    local d = ns.Cafe.Confirm("order", "Order Valley of Honor Triple Scoop for 2g 40s?\n\nThis drink's buff does "
        .. "nothing for you right now.", function() end)
    H.eq(d.text:GetWidth(), ns.Cafe.CONFIRM_TEXT_W, "an explicit width, as StaticPopup's text")
    H.eq(d.text:GetWidth(), d:GetWidth() - 40, "20 px in from each side")
    d:Hide()
end)
