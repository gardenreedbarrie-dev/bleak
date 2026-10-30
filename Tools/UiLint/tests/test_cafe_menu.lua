-- The café's menu (CafeMenu.lua, docs/BleakholdProtocol.md section 21): the customer's window. The rows per family
-- from CAFM (price in coins, who makes it, the buff or "No effect for you right now"), the tip and the total, the stock
-- confirmation before CORDER, the order in the footer with Cancel (CCANCEL in Q and F only), the status line
-- (baristas, the house, CAFM's reason), the buffs, and the openers (UI.Open, CAFUI menu).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local CAFE_BIT = { [6] = 131072 }

local function intents(M, op, from)
    local out = {}
    for _, it in ipairs(H.intents(M, from)) do
        if it.op == op then
            out[#out + 1] = it.payload
        end
    end
    return out
end

-- a whole CAFM of a café: every recipe at the server's price; over[id] = { byBarista, effective }; head overrides
local function menu(M, ns, cafeId, head, over)
    local h = { cafeId, 1, 1, 45, 0, 2, 12, 1, "" }
    for k, v in pairs(head or {}) do h[k] = v end
    local recs = { h }
    for _, r in ipairs(ns.Cafe.Recipes(cafeId)) do
        local o = (over or {})[r.id] or {}
        recs[#recs + 1] = { r.id, ns.Cafe.Price(r.id), o[1] or 1, o[2] or 1 }
    end
    H.send(M, "CAFM", recs)
    M.Advance(0.1)
end

local function open(M, ns)
    FX.connect(M, H, CAFE_BIT)
    ns.UI.Open("cafemenu")
    M.Advance(0.2)
    return ns.CafeMenu
end

local function rowOf(MN, recipeId)
    for i = 1, MN.rows.used do
        local r = MN.rows.items[i]
        if r.recipeId == recipeId then return r end
    end
end

test("café menu: opens with the café bit and asks for the menu, the order and the buffs", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    local from = #M.sent + 1
    ns.UI.Open("cafemenu")
    M.Advance(0.2)
    H.ok(M.env.BleakholdCafeMenu:IsShown(), "the menu")
    local g = {}
    for _, it in ipairs(H.intents(M, from)) do
        if it.op == "GET" then g[#g + 1] = it.payload end
    end
    g = table.concat(g, ";")
    H.contains(g, "CAFM,1", "GET CAFM of The Lion's Roast")
    H.contains(g, "CAFO", "GET CAFO")
    H.contains(g, "CAFBF", "GET CAFBF")
    H.eq(M.env.BleakholdCafeMenu.title:GetText(), "The Lion's Roast", "the café's name as the title")
    ns.UI.Open("cafemenu", true)
    H.ok(not M.env.BleakholdCafeMenu:IsShown(), "toggled shut")
end)

test("café menu: 7 coffees, 6 teas, 6 shakes, prices in coins, who makes it, and the buff", function(M, ns)
    local MN = open(M, ns)
    menu(M, ns, 1, nil, { [119] = { 0, 1 }, [101] = { 1, 0 } })
    H.eq(MN.rows.used, 7, "seven coffees")
    MN.tabs[2]:Click()
    H.eq(MN.rows.used, 6, "six teas")
    MN.tabs[3]:Click()
    H.eq(MN.rows.used, 6, "six shakes")
    local triple = rowOf(MN, 119)
    H.eq(triple.name:GetText(), "Champion's Triple Scoop", "the name")
    H.eq(triple.price.copper, ns.Cafe.Price(119), "the price in coins (the stock money frame)")
    H.eq(triple.price.parts[2].coin:GetTexture(), "Interface\\MoneyFrame\\UI-SilverIcon", "with the stock coin icons")
    H.eq(triple.tag:GetText(), "House", "nobody on shift has it: the house makes it")
    H.contains(triple.buff:GetText(), "+15% run speed", "the shake's buff")
    MN.tabs[1]:Click()
    local black = rowOf(MN, 101)
    H.eq(black.buff:GetText(), "No effect at the level cap", "effective 0: coffee at level 80")
    H.eq(rowOf(MN, 102).tag:GetText(), "Barista", "a barista on shift makes it")
    H.contains(rowOf(MN, 102).buff:GetText(), "+5% XP", "coffee's buff")
    H.contains(rowOf(MN, 102).buff:GetText(), "Well Fed", "counts as Well Fed")
    H.eq(MN.foot.status:GetText(), "Baristas on shift: 1", "the status line")
    H.eq(MN.foot.count:GetText(), "Today 2 / 12", "the day's orders")
end)

test("café menu: the tip changes the total; the confirmation sends CORDER 1,103,10", function(M, ns)
    local MN = open(M, ns)
    menu(M, ns, 1)
    local cap = rowOf(MN, 103)
    cap:Click()
    H.ok(cap.selectArt and cap.selectArt.bg:IsShown(), "the chosen row is lit (UI.Select)")
    local price = ns.Cafe.Price(103)
    H.eq(MN.foot.totalMoney.copper, price, "no tip: the price")
    MN.tipChoice.buttons[2]:Click()
    H.eq(MN.tip, 10, "+10%")
    H.eq(MN.foot.totalMoney.copper, price + math.floor(price * 10 / 100), "the total with the tip")
    MN.tipChoice.buttons[4]:Click()
    H.eq(MN.foot.totalMoney.copper, price + math.floor(price * 50 / 100), "+50%")
    MN.tipChoice.buttons[2]:Click()
    MN.order:Click()
    local d = M.env.BleakholdCafeConfirm
    H.ok(d:IsShown(), "the café's confirmation")
    local words = ns.Cafe.MoneyPlain(price + math.floor(price / 10))
    H.eq(d.text:GetText(), "Order Goldshire Honey Cappuccino for " .. words .. "?", "what it costs, in words")
    H.eq(#intents(M, "CORDER"), 0, "nothing before the accept")
    d.ok:Click()
    M.Advance(0.1)
    local sent = intents(M, "CORDER")
    H.eq(sent[#sent], "1,103,10", "CORDER café, recipe, tip")
end)

test("café menu: the confirmation stands beside the menu, never on its rows, and never moves the kit's dialog", function(M, ns)
    -- a 1080p screen (UIParent 1517 wide at the 0.9 scale), the menu in its middle
    M.SetScreen(1920, 1080)
    local MN = open(M, ns)
    menu(M, ns, 1)
    rowOf(MN, 103):Click()
    local win = M.env.BleakholdCafeMenu
    win.__cx = M.screenW / 2
    MN.order:Click()
    local d = M.env.BleakholdCafeConfirm
    H.ok(d:IsShown(), "the confirmation")
    H.ok(not (M.env.BleakholdDialog and M.env.BleakholdDialog:IsShown()), "the kit's shared dialog is not used")
    local p, rel, rp, x = d:GetPoint(1)
    H.eq(d:GetNumPoints(), 1, "one point")
    H.ok(rel == win, "anchored to the menu")
    H.eq(p .. ">" .. rp, "LEFT>RIGHT", "to its right")
    H.eq(x, MN.DIALOG_GAP, "a small gap off its edge")
    -- another window asks on the kit's dialog meanwhile: it stays at the kit's spot, and the café's question stays too
    local kit = ns.UI.Confirm("Something else?", function() end)
    H.ok(kit ~= d, "two frames")
    H.ok(select(2, kit:GetPoint(1)) == M.env.UIParent, "the kit's dialog where the kit put it")
    H.ok(d:IsShown(), "the café's question still up")
    d.cancel:Click()
    H.ok(not d:IsShown(), "closed")
    H.ok(kit:IsShown(), "the other window's question untouched")
    kit:Hide()
    -- the café's next question (Bin) opens where the stock popups stand, never where the menu put the last one
    local bin = ns.Cafe.Confirm("bin", "Bin this drink?", function() end, "Bin")
    local bp, brel, _, _, by = bin:GetPoint(1)
    H.eq(bp, "CENTER", "home point")
    H.ok(brel == M.env.UIParent, "on UIParent")
    H.eq(by, 120, "120 up")
    bin:Hide()
    -- no room on the right: the left side; on neither side (a 4:3 screen, 1024 wide): over the footer, under the list
    M.SetScreen(1024, 768)
    win.__cx = 900
    MN.order:Click()
    p, rel, rp = d:GetPoint(1)
    H.eq(p .. ">" .. rp, "RIGHT>LEFT", "to its left by the screen's right edge")
    d:Hide()
    win.__cx = 512
    MN.order:Click()
    p, rel, rp = d:GetPoint(1)
    H.ok(rel == win, "still on the menu")
    H.eq(p .. ">" .. rp, "BOTTOM>BOTTOM", "over the footer when no side has room")
    -- closing the menu takes its confirmation along, but never another window's question on the kit's dialog
    local other = ns.UI.Confirm("Reroll this key?", function() end)
    win:Hide()
    H.ok(not d:IsShown(), "gone with the menu")
    H.ok(other:IsShown(), "the kit's dialog is left alone")
    other:Hide()
    H.eq(#intents(M, "CORDER"), 0, "nothing ordered")
    -- a café question that is not the order's (Bin) is not the menu's to close
    MN.Open(1)
    ns.Cafe.Confirm("bin", "Bin this drink?", function() end, "Bin")
    win:Hide()
    H.ok(d:IsShown(), "the bin question stays")
    d:Hide()
end)

test("café menu: the rows fill the list when a family fits and make room for the scrollbar when not", function(M, ns)
    local MN = open(M, ns)
    menu(M, ns, 1)
    local list, foot = MN.list, MN.foot
    -- one margin for the list and the footer: their right edges are one edge
    local _, _, _, lx = list:GetPoint(1)
    local _, _, _, fx = foot:GetPoint(2)
    H.eq(lx, MN.MARGIN, "the list's left margin")
    H.eq(fx, -MN.MARGIN, "the footer's right margin is the same")
    H.eq(lx + list:GetWidth() + MN.MARGIN, MN.body:GetWidth(), "the list ends at that margin")
    H.eq(select(4, MN.order:GetPoint(1)), 0, "Order ends at the footer's (the rows') right edge")
    H.eq(select(4, MN.cancel:GetPoint(1)), 0, "and Cancel Order")
    H.eq(select(4, foot.count:GetPoint(1)), 0, "and the day's orders")
    for _, i in ipairs({ 1, 2, 3 }) do
        MN.tabs[i]:Click()
        H.ok(MN.rows.used <= MN.ROWS, MN.TABS[i].label .. ": every drink fits the list")
        H.ok(not list.bar:IsShown(), MN.TABS[i].label .. ": no scrollbar")
        for k = 1, MN.rows.used do
            H.eq(MN.rows.items[k]:GetWidth(), list:GetWidth(), MN.TABS[i].label .. ": the row spans the list")
        end
    end
    local r = MN.rows.items[1]
    H.eq(r.text:GetWidth(), list:GetWidth() - 146, "the flavour text follows the row's width")
    -- a longer family (none today): the rows leave the scrollbar its room, and get it back after
    local real = ns.Cafe.Recipes
    ns.Cafe.Recipes = function(cafeId, family)
        local out = {}
        for _, rr in ipairs(real(cafeId, family)) do out[#out + 1] = rr end
        for k = 1, 2 do out[#out + 1] = out[k] end
        return out
    end
    MN.tabs[1]:Click()
    H.eq(MN.rows.used, MN.ROWS + 2, "nine rows")
    H.ok(list.bar:IsShown(), "the scrollbar")
    H.eq(MN.rows.items[1]:GetWidth(), list:GetWidth() - ns.UI.SCROLL_W - 4, "the rows clear the scrollbar")
    H.eq(MN.rows.items[1].text:GetWidth(), list:GetWidth() - ns.UI.SCROLL_W - 4 - 146, "and their text")
    ns.Cafe.Recipes = real
    MN.tabs[2]:Click()
    H.ok(not list.bar:IsShown(), "back to a family that fits")
    H.eq(MN.rows.items[1]:GetWidth(), list:GetWidth(), "the whole width again")
end)

test("café menu: a drink whose buff does nothing asks twice", function(M, ns)
    local MN = open(M, ns)
    menu(M, ns, 1, nil, { [101] = { 1, 0 } })
    rowOf(MN, 101):Click()
    MN.order:Click()
    H.contains(M.env.BleakholdCafeConfirm.text:GetText(), "This drink's buff does nothing for you right now.",
        "the warning")
end)

test("café menu: cafe_cap turns Order off with its sentence", function(M, ns)
    local MN = open(M, ns)
    menu(M, ns, 1, { [8] = 0, [9] = "cafe_cap" })
    H.ok(not MN.order.enabled, "Order disabled")
    H.eq(MN.foot.status:GetText(), "The café is full right now; try again in a minute.", "the reason")
    MN.order:Click()
    H.ok(not M.env.BleakholdCafeConfirm or not M.env.BleakholdCafeConfirm:IsShown(), "no confirmation")
end)

test("café menu: the pending order shows in the footer; Cancel only while queued or the house finishes", function(M, ns)
    local MN = open(M, ns)
    menu(M, ns, 1)
    H.send(M, "CAFO", { { 1210, 1, 103, "Q", 1, "", 0, 5, "", 5300, 530 } })
    M.Advance(0.1)
    H.contains(MN.foot.total:GetText(), "Goldshire Honey Cappuccino", "the order")
    H.eq(MN.foot.status:GetText(), "In queue #1", "its state on the status line")
    H.ok(MN.cancel:IsShown() and not MN.order:IsShown(), "Cancel instead of Order")
    MN.cancel:Click()
    M.Advance(0.1)
    local sent = intents(M, "CCANCEL")
    H.eq(sent[#sent], "1210", "CCANCEL the order")
    H.send(M, "CAFO", { { 1210, 1, 103, "M", "", "Aldric", 2, 5, "", 5300, 530 } })
    M.Advance(0.1)
    H.eq(MN.foot.status:GetText(), "Being made by Aldric (2/5)", "being made")
    H.ok(not MN.cancel:IsShown(), "no Cancel while a barista makes it")
    H.send(M, "CAFO", { { 1210, 1, 103, "F", "", "", 3, 5, 40, 5300, 530 } })
    M.Advance(0.1)
    H.contains(MN.foot.status:GetText(), "Rosalind Thornbury is finishing it", "the owner takes over")
    H.ok(MN.cancel:IsShown(), "Cancel again")
    H.send(M, "CAFO", { { 1210, 1, 103, "R", "", "", 5, 5, 179, 5300, 530 } })
    M.Advance(0.1)
    H.contains(MN.foot.status:GetText(), "Ready · 2:59", "ready, with the pickup countdown")
    H.contains(MN.foot.status:GetText(), "walk to the counter or sit at a café table", "and how to pick it up")
    M.Advance(10)
    local t = MN.foot.status:GetText()
    H.ok(t:find("· 2:49", 1, true) or t:find("· 2:50", 1, true), "it counts down: " .. t)
    H.send(M, "CAFO", { { 0 } })
    M.Advance(0.1)
    H.ok(MN.order:IsShown() and not MN.cancel:IsShown(), "no order: Order again")
end)

test("café menu: the status line names the house's wait when nobody is on shift, and the buffs' times", function(M, ns)
    local MN = open(M, ns)
    menu(M, ns, 1, { [3] = 0, [4] = 40 })
    H.eq(MN.foot.status:GetText(), "The house will make it: about 40 s", "the house")
    H.send(M, "CAFBF", { { 1320, "", 1800, 0, 1 } })
    M.Advance(0.1)
    local b = MN.foot.buffs
    H.eq(b[1].time:GetText(), "22 m", "coffee")
    H.ok(not b[1].icon:IsDesaturated(), "active in colour")
    H.eq(b[2].time:GetText(), "-", "no tea")
    H.ok(b[2].icon:IsDesaturated(), "inactive greyed")
    H.eq(b[3].time:GetText(), "30 m", "shake")
    M.Hover(b[3])
    H.contains(table.concat(M.env.GameTooltip.__lines or {}, "|"), "Speed off here", "shakeActive 0")
end)

test("café menu: a Horde player's menu is The Grinding Tusk's, and CAFUI menu opens it", function(M, ns)
    M.env.UnitFactionGroup = function() return "Horde", "Horde" end
    FX.connect(M, H, CAFE_BIT)
    local from = #M.sent + 1
    H.send(M, "CAFUI", { { "menu", 2 } })
    M.Advance(0.2)
    local MN = ns.CafeMenu
    H.ok(M.env.BleakholdCafeMenu:IsShown(), "CAFUI menu opens the menu")
    H.eq(M.env.BleakholdCafeMenu.title:GetText(), "The Grinding Tusk", "the Horde café")
    local g = {}
    for _, it in ipairs(H.intents(M, from)) do
        if it.op == "GET" then g[#g + 1] = it.payload end
    end
    H.contains(table.concat(g, ";"), "CAFM,2", "GET CAFM,2")
    menu(M, ns, 2)
    H.eq(MN.rows.items[1].name:GetText(), "Grunt's Black", "the Grinding Tusk's coffee")
end)

test("café menu: every fixture renders without errors", function(M, ns)
    open(M, ns)
    local ex = FX.examples(M)
    for _, op in ipairs({ "CAFE", "CAFM", "CAFO", "CAFBF", "CAFST" }) do
        H.send(M, op, ex[op])
    end
    M.Advance(1)
    for i = 1, 3 do
        ns.CafeMenu.tabs[i]:Click()
    end
    H.eq(#M.errors, 0, "no Lua errors")
end)

test("café menu: an order's change and the passing reasons ask for CAFM again while it is open", function(M, ns)
    local MN = open(M, ns)
    -- an order pending: canOrder 0, cafe_order
    H.send(M, "CAFM", { { 1, 1, 1, 45, 1210, 2, 12, 0, "cafe_order" } })
    H.send(M, "CAFO", { { 1210, 1, 103, "M", "", "Aldric", 2, 5, "", 5300, 530 } })
    M.Advance(3)
    local function camfGets(from)
        local n = 0
        for _, it in ipairs(H.intents(M, from)) do
            if it.op == "GET" and it.payload:find("CAFM,1", 1, true) then n = n + 1 end
        end
        return n
    end
    local from = #M.sent + 1
    M.Advance(10)
    H.eq(camfGets(from), 0, "cafe_order does not pass on its own: no polling")
    -- delivered: the menu asks again (canOrder, today's count)
    H.send(M, "CAFO", { { 1210, 1, 103, "D", "", "", 0, 5, "", 5300, 530 } })
    M.Advance(0.2)
    H.eq(camfGets(from), 1, "GET CAFM after the order ended")
    -- too far away: asked again every few seconds while the menu is open
    H.send(M, "CAFM", { { 1, 1, 1, 45, 0, 3, 12, 0, "cafe_where" } })
    M.Advance(0.2)
    from = #M.sent + 1
    M.Advance(10)
    H.ok(camfGets(from) >= 2, "polled for cafe_where: " .. camfGets(from))
    H.send(M, "CAFM", { { 1, 1, 1, 45, 0, 3, 12, 1, "" } })
    M.Advance(0.2)
    H.ok(MN.order:IsShown())
    from = #M.sent + 1
    M.Advance(10)
    H.eq(camfGets(from), 0, "no polling once the order can go")
    M.env.BleakholdCafeMenu:Hide()
end)

test("café menu: no effect wording: the level cap only for coffee at level 80, else neutral", function(M, ns)
    local MN = open(M, ns)
    M.playerLevel = 30
    menu(M, ns, 1, nil, { [101] = { 1, 0 } })
    local black = rowOf(MN, 101)
    H.eq(black.buff:GetText(), "No effect for you right now", "XP gain off at level 30: not the level")
    MN.tabs[2]:Click()
    M.playerLevel = 80
end)

test("cafe menu: its clocks round as the HUD's: buff minutes up, the house's seconds up", function(M, ns)
    local MN = open(M, ns)
    menu(M, ns, 1)
    -- 28:30 of coffee: the HUD's chip reads 29 m (Cafe.ShortTime), so does the menu
    H.send(M, "CAFBF", { { 1710, "", "", 1, 0 } })
    M.Advance(0.1)
    local b = MN.foot.buffs
    H.eq(b[1].time:GetText(), "29 m", "rounded up, as the buff chip")
    H.eq(b[1].time:GetText(), ns.Cafe.ShortTime(ns.Cafe.Left(ns.S.cafeBuffs, "coffeeSec")))
    H.send(M, "CAFBF", { { 61, "", "", 1, 0 } })
    M.Advance(0.1)
    H.eq(b[1].time:GetText(), "2 m")
    -- the house's ETA: the order chip's ceil
    H.send(M, "CAFO", { { 1210, 1, 103, "H", "", "", 2, 5, 45, 5300, 530 } })
    M.Advance(0.5)
    MN.Refresh()
    local menuSec = MN.foot.status:GetText():match("~(%d+) s")
    H.eq(menuSec, "45", "44.5 s left reads ~45 s")
    H.eq(ns.Cafe.Hud.OrderStatus(ns.S.cafeOrder):match("~(%d+) s"), menuSec, "the chip and the menu agree")
end)

test("cafe menu: a push mid-click leaves the rows shown (a hide would drop the click)", function(M, ns)
    local MN = open(M, ns)
    menu(M, ns, 1)
    local r = MN.rows.items[2]
    local hides = 0
    r:HookScript("OnHide", function()
        hides = hides + 1
    end)
    menu(M, ns, 1)
    H.send(M, "CAFBF", { { 1710, "", "", 1, 0 } })
    H.send(M, "CAFO", { { 1210, 1, 103, "H", "", "", 2, 5, 45, 5300, 530 } })
    M.Advance(1.2)
    H.eq(hides, 0, "the rows in use are never hidden by a refresh")
    H.ok(r:IsShown())
end)
