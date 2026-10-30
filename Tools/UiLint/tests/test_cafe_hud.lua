-- The café's HUD (CafeHud.lua and the timing bar of CafeBar.lua, section 21): the strip, the ticket, the queue, the
-- result banner, the buffs, the order chip and the "at the bar" strip, from the server's messages.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local CAFE_BIT = { [6] = 131072 }

-- The player's zone as the client knows it: the world map's area of it (SetMapToCurrentZone, then
-- GetCurrentMapAreaID: WorldMapArea.dbc) and its name in the client's language; a zone change fires
-- ZONE_CHANGED_NEW_AREA, as the client does.
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

local function cafst(M, extra, day, rush)
    local r = { 1, 1, 6, 1890, 1600, 2320, 760, 14, 9, 4, 10600, 212, "E", "E", 3, 2, 3600, 0 }
    for k, v in pairs(extra or {}) do
        r[k] = v
    end
    local recs = { r, day or { "D", 210, 450, 450, 30000, 180000, 180, 400, 14 } }
    if rush ~= false then
        recs[#recs + 1] = rush or { "R", 1, 180, 0, 60, 0 }
    end
    H.send(M, "CAFST", recs)
end

local function onShift(M, extra)
    -- the HUD measured as the client measures: cut to a box with both a width and a height
    M.measureAsShown = true
    FX.connect(M, H, CAFE_BIT)
    H.send(M, "CAFE", { { 1, 1, 1, 2, 1, 180, 45 }, { 2, 1, 0, 0, 1, 180, 60 } })
    cafst(M, extra)
    M.Advance(0.3)
end

local function ticket(M, patienceMs, maxMs, nextStep)
    H.send(M, "CAFT", { { 41, 1209, 103, "P", "Brenna", patienceMs or 57000, maxMs or 60000, nextStep or 2, 1,
        "One latte, please.", { { 1, "P" }, { 3, "N" }, { 6, "N" }, { 16, "N" }, { 25, "N" } }, 2100 } })
end

local function rgb(hex)
    return tonumber(hex:sub(1, 2), 16) / 255, tonumber(hex:sub(3, 4), 16) / 255, tonumber(hex:sub(5, 6), 16) / 255
end

local function textColor(fs)
    local r, g, b = fs:GetTextColor()
    return string.format("%02X%02X%02X", math.floor(r * 255 + 0.5), math.floor(g * 255 + 0.5), math.floor(b * 255 + 0.5))
end

local function barColor(bar)
    local r, g, b = bar:GetStatusBarColor()
    return string.format("%02X%02X%02X", math.floor(r * 255 + 0.5), math.floor(g * 255 + 0.5), math.floor(b * 255 + 0.5))
end

test("cafe hud: every café message of the fixtures draws without errors", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    local ex = FX.examples(M)
    for _, op in ipairs({ "CAFE", "CAFST", "CAFQ", "CAFT", "CAFEV", "CAFRES", "CAFM", "CAFO", "CAFP", "CAFBF", "CAFSUM",
        "CAFUI", "CAFAT" }) do
        H.send(M, op, ex[op])
        M.Advance(0.2)
    end
    H.send(M, "CAFST", ex.CAFST)
    M.Advance(1)
    for _, name in ipairs({ "BleakholdCafeBar", "BleakholdCafeStrip", "BleakholdCafeTicket", "BleakholdCafeQueue" }) do
        H.ok(M.env[name]:IsShown(), name .. " on shift")
    end
    H.ok(not M.env.BleakholdCafeOrderChip:IsShown(), "never the order chip on shift (the strip's spot)")
    FX.openEverything(M, ns)
    M.Advance(3)
end)

test("cafe hud: nothing shows while the realm has the café off", function(M, ns)
    FX.connect(M, H)
    local ex = FX.examples(M)
    for _, op in ipairs({ "CAFE", "CAFST", "CAFQ", "CAFT", "CAFEV", "CAFRES", "CAFO", "CAFBF", "CAFAT" }) do
        H.send(M, op, ex[op])
    end
    inZone(M, "Stormwind City")
    M.Advance(1)
    for _, name in ipairs({ "BleakholdCafeBar", "BleakholdCafeStrip", "BleakholdCafeTicket", "BleakholdCafeQueue",
        "BleakholdCafeResult", "BleakholdCafeBuffs", "BleakholdCafeOrderChip", "BleakholdCafeAtBar" }) do
        H.ok(not M.env[name]:IsShown(), name .. " hidden")
    end
    H.ok(not M.env.BleakholdOrb_cafe:IsShown(), "no orb")
end)

test("cafe hud: patience turns from green to yellow at half and to red at a quarter, with the seconds", function(M, ns)
    onShift(M)
    ticket(M, 40000, 60000)
    M.Advance(0.1, 0.1)
    local tk = M.env.BleakholdCafeTicket
    H.eq(barColor(tk.patience), "00FF00")
    H.contains(tk.patience.text:GetText(), "40 s")
    M.Advance(10.5, 0.5)
    H.eq(barColor(tk.patience), "FFFF00", "below half")
    H.contains(tk.patience.text:GetText(), "30 s", "29.4 s left: the seconds rounded up")
    M.Advance(15, 0.5)
    H.eq(barColor(tk.patience), "FF0000", "below a quarter")
    H.contains(tk.patience.text:GetText(), " s")
    -- the queue's rows count down the same way
    H.send(M, "CAFQ", { { 1, 1, 6, 2, "" }, { 1207, "N", 101, "Sergeant Corwin Ashgrove", 10000, 48000, "W", "", 0 } })
    M.Advance(0.2)
    local row = M.env.BleakholdCafeQueue.pool.items[1]
    H.contains(row.secs:GetText(), "10 s")
    H.eq(barColor(row.bar), "FF0000")
end)

test("cafe hud: the ticket lists the steps, merges repeats and shows the drink's progress", function(M, ns)
    onShift(M)
    ticket(M)
    M.Advance(0.2)
    local tk = M.env.BleakholdCafeTicket
    H.eq(tk.customer:GetText(), "Brenna")
    H.eq(tk.drink:GetText(), "Goldshire Honey Cappuccino")
    H.contains(tk.kicker:GetText(), "Order #1209")
    H.contains(tk.kicker:GetText(), "Player")
    H.eq(tk.line:GetText(), "\"One latte, please.\"")
    H.ok(tk.stars[2]:IsShown() and not tk.stars[3]:IsShown(), "tier 2: two stars")
    local _, starRel, starRelPoint = tk.stars[1]:GetPoint()
    H.ok(starRel == tk.drink and starRelPoint == "RIGHT", "the stars follow the drink's name, on its line")
    H.ok(tk.drink:GetWidth() <= 280 - 24 - (4 + 2 * 13), "the name leaves the stars their room")
    H.ok(math.abs(tk.progress:GetValue() - 0.2) < 1e-6, "1 of 5 steps")
    H.eq(tk.stepsLabel:GetText(), "Steps")
    H.eq(tk.progress.text:GetText(), "1 / 5")
    H.eq(tk.progress:GetHeight(), 5, "a slim bar, no second ornate frame")
    local rows = tk.rowPool.items
    H.eq(tk.rowPool.used, 5)
    H.ok(rows[1].mark:IsShown(), "done: the ready check")
    H.contains(rows[1].name:GetText(), "Grind Beans")
    H.ok(rows[2].arrow:IsShown() and not rows[2].dash:IsShown(), "the next step: the arrow where the dash is")
    H.ok(rows[3].dash:IsShown() and not rows[3].arrow:IsShown(), "a later step: the dash")
    H.eq(textColor(rows[2].name), "FFFFFF", "the next step in white")
    H.eq(textColor(rows[3].name), "CCCCCC", "the later ones in the objectives' grey")
    H.eq(rows[2].sub:GetText(), "Gold about 70-85%", "not running: the action's zone, which each step moves a little")
    H.eq(textColor(rows[2].sub), "FFD100", "the step about to be done: its gold range in full gold")
    H.eq(textColor(rows[3].sub), "C4A300", "a later timed step's range in the darker gold")
    H.eq(rows[2].where:GetText(), "Espresso [1]", "the station (short) and its key")
    -- the rows' right column ends where the patience and Steps bars end, and a name stops short of it
    local hud = ns.Cafe.Hud
    local barRight = hud.TICKET_BAR_X + tk.patience:GetWidth()
    H.eq(hud.TICKET_BAR_X + tk.progress:GetWidth(), barRight)
    for i = 1, tk.rowPool.used do
        local _, rel, relPoint, x = rows[i]:GetPoint(1)
        H.ok(rel == tk and relPoint == "TOPLEFT", "row " .. i .. " on the ticket")
        H.eq(x + rows[i]:GetWidth(), barRight, "row " .. i .. "'s right edge meets the bars'")
        H.ok(hud.ROW_TEXT_X + rows[i].name:GetWidth() + 8 + rows[i].where:GetStringWidth() <= rows[i]:GetWidth() + 0.5,
            "row " .. i .. ": the name stops 8 short of the station")
    end
    H.contains(tk.footNext:GetText(), "Next: Espresso Machine")
    H.eq(tk.footMoney.copper, 2100)
    -- repeats merge: Champion's Triple Scoop (11 x3)
    H.send(M, "CAFT", { { 42, 1300, 119, "N", "Squire", 60000, 60000, 2, 1, "",
        { { 11, "P" }, { 11, "N" }, { 11, "N" }, { 18, "N" }, { 20, "N" }, { 15, "N" }, { 23, "N" }, { 25, "N" } }, 500 } })
    M.Advance(0.2)
    H.contains(rows[1].name:GetText(), "Scoop Ice Cream \195\1513 (1/3)")
    H.eq(tk.rowPool.used, 6)
    -- from memory (flag 2 and the option): what comes next is hidden
    cafst(M, { [18] = 2 })
    ns.Cafe.SetOption("cafeMemory", true)
    M.Advance(0.2)
    H.eq(rows[2].name:GetText(), "? ? ?")
    H.eq(M.env.BleakholdCafeBar.hint:GetText(), "")
    -- no ticket
    H.send(M, "CAFT", { { 0 } })
    M.Advance(0.2)
    H.eq(tk.emptyTitle:GetText(), "No ticket")
    H.ok(tk.emptyTitle:IsShown() and tk.empty:IsShown(), "the tracker's title and objective line")
    H.eq(tk.empty:GetText(), "Walk to the Serving Counter to take an order.",
        "away from the counter no key: there the bar's slots name the stations")
    cafst(M, { [13] = "V", [14] = "V" })
    M.Advance(0.2)
    H.eq(tk.empty:GetText(), "Take the next order [1]", "at the counter, with the bar's key")
    H.ok(not tk.progress:IsShown() and not tk.stepsLabel:IsShown())
end)

test("cafe hud: a running tap fills a green bar in a band under its row while it runs", function(M, ns)
    onShift(M, { [13] = "G", [14] = "G" })
    ticket(M, 57000, 60000, 1)
    M.Advance(0.2)
    local tk = M.env.BleakholdCafeTicket
    local rows = tk.rowPool.items
    local _, _, _, _, y2 = rows[2]:GetPoint(1)
    H.ok(not tk.stepBar:IsShown(), "nothing runs yet")
    H.send(M, "CAFEV", { { 41, 1, 1, "S", 1500, "", "", "", 1 } })
    M.Advance(0.6, 0.1)
    H.ok(tk.stepBar:IsShown(), "Grind Beans runs")
    local _, rel, relPoint, x = tk.stepBar:GetPoint(1)
    H.ok(rel == rows[1] and relPoint == "TOPLEFT", "under the running step's row")
    H.eq(x, ns.Cafe.Hud.ROW_TEXT_X, "under its name")
    H.ok(math.abs(tk.stepBar:GetValue() - 0.4) < 0.08, "0.6 of 1.5 s: " .. tk.stepBar:GetValue())
    H.eq(barColor(tk.stepBar), "00FF00")
    local _, _, _, _, y2run = rows[2]:GetPoint(1)
    H.eq(y2run, y2 - ns.Cafe.Hud.RUN_BAND, "the rows under it make room for the band")
    H.send(M, "CAFEV", { { 41, 1, 1, "D", 1500, "", "", "P", 2 } })
    M.Advance(0.2)
    H.ok(not tk.stepBar:IsShown(), "gone with its D")
    local _, _, _, _, y2done = rows[2]:GetPoint(1)
    H.eq(y2done, y2, "and the band with it")
    -- a lost D: the bar goes when the step stops counting as running
    ticket(M, 57000, 60000, 1)
    H.send(M, "CAFEV", { { 41, 1, 1, "S", 1500, "", "", "", 3 } })
    M.Advance(0.2)
    H.ok(tk.stepBar:IsShown())
    M.Advance(3.2, 0.1)
    H.ok(not tk.stepBar:IsShown(), "gone after the step's time and its grace")
    local _, _, _, _, y2stale = rows[2]:GetPoint(1)
    H.eq(y2stale, y2, "the rows laid out again without the band")
    -- a timed step has the timing bar over the café bar instead
    cafst(M, { [13] = "E", [14] = "E" })
    ticket(M, 57000, 60000, 2)
    H.send(M, "CAFEV", { { 41, 2, 3, "S", 3000, 2160, 2610, "", 4 } })
    M.Advance(0.5)
    H.ok(not tk.stepBar:IsShown(), "no ticket bar for a timed step")
end)

test("cafe hud: queue rows are as tall as their lines: no empty band under a row without a tag", function(M, ns)
    onShift(M)
    H.send(M, "CAFQ", { { 1, 3, 6, 2, "" },
        { 1209, "P", 103, "Brenna", 21000, 25000, "W", "", 0 },
        { 1207, "N", 101, "Sergeant Corwin Ashgrove", 30000, 48000, "W", "", 0 },
        { 1212, "G", 102, "Night Watch Guard", 14000, 51000, "W", "", 0, 7 } })
    M.Advance(0.2)
    local rows = M.env.BleakholdCafeQueue.pool.items
    local hud = ns.Cafe.Hud
    H.eq(rows[1]:GetHeight(), hud.QUEUE_ROW, "Player and the price: three lines")
    H.eq(rows[2]:GetHeight(), hud.QUEUE_ROW_SHORT, "a name and a drink: two lines")
    H.ok(not rows[2].mark:IsShown())
    local _, _, _, _, y2 = rows[2]:GetPoint(1)
    local _, _, _, _, y3 = rows[3]:GetPoint(1)
    H.eq(y2 - y3, hud.QUEUE_ROW_SHORT, "the next row follows right under it")
    -- the name runs up to 6 short of the seconds at their longest (the row's full patience): no early cut
    for i = 1, 3 do
        local r = rows[i]
        local _, _, _, nameX = r.customer:GetPoint(1)
        H.eq(nameX, hud.QUEUE_TEXT_X)
        r.secs:SetText(math.ceil(r.data.patienceMaxMs / 1000) .. " s")
        H.ok(math.abs(nameX + r.customer:GetWidth() + 6 - (hud.QUEUE_SECS_R - r.secs:GetStringWidth())) < 1,
            "row " .. i .. ": the name ends 6 short of the seconds")
        H.ok(r.customer:GetWidth() > 110, "row " .. i .. ": wider than the old 110")
    end
end)

test("cafe hud: the strip's numbers share one baseline; the level bar hangs under Barista", function(M, ns)
    onShift(M)
    local st = M.env.BleakholdCafeStrip
    for _, key in ipairs({ "shift", "drinks", "streak", "tips", "xp", "level" }) do
        local point, _, _, _, y = st.stats[key]:GetPoint(1)
        H.eq(point, "LEFT", key)
        H.eq(y, 0, key .. " on the strip's middle line")
    end
    local _, rel, relPoint = st.levelBar:GetPoint(1)
    H.ok(rel == st.stats.level and relPoint == "BOTTOMLEFT", "the bar under the label")
end)

test("cafe hud: the buffs sit under the strip or the order chip, else at the top; a moved spot stays", function(M, ns)
    onShift(M)
    inZone(M, "Stormwind City")
    H.send(M, "CAFBF", { { 1680, 2400, 900, 1, 1 } })
    M.Advance(0.6)
    local bf, st, oc = M.env.BleakholdCafeBuffs, M.env.BleakholdCafeStrip, M.env.BleakholdCafeOrderChip
    H.ok(bf:IsShown() and st:IsShown())
    local point, rel, relPoint, _, y = bf:GetPoint(1)
    H.ok(point == "TOP" and rel == st and relPoint == "TOP", "under the strip")
    H.ok(st.rush:IsShown(), "with the Rush line under it")
    H.eq(y, -(36 + 16 - 2 + 6), "clear of the strip and its Rush line: " .. tostring(y))
    -- a warning line more: the buffs move down with it
    cafst(M, { [18] = 64, [19] = 4 })
    M.Advance(0.2)
    _, _, _, _, y = bf:GetPoint(1)
    H.eq(y, -(36 + 32 - 2 + 6), "under the warning and the Rush: " .. tostring(y))
    -- off shift with an order: under the chip
    cafst(M, { [1] = 0, [2] = 0 })
    H.send(M, "CAFO", { { 1210, 1, 103, "M", "", "Aldric", 2, 5, "", 5300, 530 } })
    M.Advance(0.6)
    H.ok(oc:IsShown() and not st:IsShown())
    point, rel, relPoint, _, y = bf:GetPoint(1)
    H.ok(point == "TOP" and rel == oc and relPoint == "BOTTOM" and y == -6, "6 under the order chip")
    -- neither: the top of the screen
    H.send(M, "CAFO", { { 1210, 1, 103, "X", "", "", 0, 5, "", 5300, 530 } })
    M.Advance(5.6)
    H.ok(not oc:IsShown())
    point, rel, relPoint, _, y = bf:GetPoint(1)
    H.ok(point == "TOP" and rel == M.env.UIParent and y == -36, "TOP 0,-36")
    -- moved in the editor: kept, whatever shows
    ns.cdb.windows.BleakholdCafeBuffs = { point = "TOPLEFT", relPoint = "TOPLEFT", x = 300, y = -200 }
    ns.Cafe.Hud.buffsPlace.Anchor()
    cafst(M)
    M.Advance(0.6)
    point, rel, _, _, y = bf:GetPoint(1)
    H.ok(point == "TOPLEFT" and rel == M.env.UIParent and y == -200, "the saved spot")
end)

test("cafe hud: tabs for two tickets; the drink in hand cannot be switched away from", function(M, ns)
    onShift(M)
    H.send(M, "CAFT", {
        { 41, 1209, 103, "P", "Brenna", 57000, 60000, 1, 0, "", { { 1, "N" }, { 3, "N" } }, 2100 },
        { 42, 1207, 101, "N", "Corwin", 43200, 43200, 1, 0, "", { { 1, "N" }, { 3, "N" } }, 400 } })
    M.Advance(0.2)
    local tk = M.env.BleakholdCafeTicket
    H.ok(tk.tabs[1]:IsShown() and tk.tabs[2]:IsShown() and not tk.tabs[3]:IsShown())
    tk.tabs[1]:Click()
    H.eq(tk.customer:GetText(), "Brenna")
    H.eq(tk.tabs[1].style, "tabOn")
    H.send(M, "CAFT", {
        { 41, 1209, 103, "P", "Brenna", 57000, 60000, 1, 0, "", { { 1, "N" }, { 3, "N" } }, 2100 },
        { 42, 1207, 101, "N", "Corwin", 43200, 43200, 2, 1, "", { { 1, "P" }, { 3, "N" } }, 400 } })
    M.Advance(0.2)
    H.eq(tk.customer:GetText(), "Corwin", "the drink in hand")
    H.eq(tk.tabs[2].label:GetText(), "In hand")
    tk.tabs[1]:Click()
    H.eq(tk.customer:GetText(), "Corwin", "stays")
end)

test("cafe hud: the timing bar follows the step, its gold zone bracketed, and flashes the grade", function(M, ns)
    onShift(M)
    ticket(M)
    M.Advance(0.2)
    H.send(M, "CAFEV", { { 41, 2, 3, "S", 3000, 2160, 2610, "", 2 } })
    local tm = M.env.BleakholdCafeTiming
    H.ok(tm:IsShown(), "shown while a timed step runs")
    M.Advance(1.5, 0.016)
    local Bar = ns.Cafe.Bar
    H.ok(math.abs(Bar.progress - 0.5) < 0.02, "half way after 1.5 s of 3: " .. tostring(Bar.progress))
    local _, _, _, x = tm.bar.spark:GetPoint(1)
    H.ok(math.abs(x - 170) < 6, "the spark at the fill's head: " .. tostring(x))
    H.ok(math.abs(Bar.zone.x1 - 340 * 0.72) < 0.5 and math.abs(Bar.zone.x2 - 340 * 0.87) < 0.5, "the gold zone")
    H.eq(tm.bar.goldLabel:GetText(), "Gold")
    H.ok(tm.bar.brackets[1]:IsShown() and tm.bar.brackets[2]:IsShown(), "brackets: never colour alone")
    -- the Good band either side of the gold, in the stock green and visible; the fill darker than the zone
    for i, g in ipairs(tm.bar.good) do
        local r, gg, b, a = g:GetVertexColor()
        H.ok(g:IsShown() and gg > 0.9 and r < 0.2 and a >= 0.35 and a <= 0.45,
            "Good band " .. i .. " green at 0.35-0.45")
        H.ok(math.abs(g:GetWidth() - 34) < 0.5, "10% of the bar each side: " .. tostring(g:GetWidth()))
    end
    local _, _, _, gx = tm.bar.good[2]:GetPoint(1)
    H.ok(math.abs(gx - Bar.zone.x2) < 0.5, "the right band starts where the gold ends (they do not overlap)")
    H.eq(barColor(tm.bar), "BF7300", "the running fill is a darker amber than the zone")
    H.ok(tm.bar.goldEdges[1]:IsShown() and tm.bar.goldEdges[2]:IsShown(), "the zone's light edges")
    H.eq(tm.bar.goldEdges[1]:GetDrawLayer(), "OVERLAY")
    H.contains(tm.bar.left:GetText(), "Pull Shot 5")
    H.eq(tm.bar.right:GetText(), "Release [1]")
    H.send(M, "CAFEV", { { 41, 2, 3, "D", 3000, 2160, 2610, "P", 3 } })
    H.eq(tm.bar.text:GetText(), "Perfect")
    H.eq(barColor(tm.bar), "00FF00")
    H.ok(tm.bar.flashFrame:IsShown(), "the cast bar's flash")
    M.Advance(0.7)
    H.ok(not tm:IsShown(), "gone after the grade")
    -- interrupted: red, as the stock cast bar
    H.send(M, "CAFEV", { { 41, 3, 6, "S", 2000, 760, 1160, "", 3 } })
    M.Advance(0.5)
    H.send(M, "CAFEV", { { 41, 3, 6, "I", "", "", "", "", 3 } })
    H.eq(tm.bar.text:GetText(), "Interrupted")
    H.eq(barColor(tm.bar), "FF0000")
end)

test("cafe hud: a ruined drink flashes and shows the banner; the result banner goes after 2 s", function(M, ns)
    onShift(M, { [13] = "E" })
    ticket(M)
    M.Advance(0.2)
    H.send(M, "CAFEV", { { 41, 2, 5, "X", "", "", "", "", 1 } })
    local rs = M.env.BleakholdCafeResult
    H.ok(rs:IsShown())
    H.eq(rs.word:GetText(), "Ruined!")
    local hud = ns.Cafe.Hud
    local _, _, _, _, subY = rs.sub:GetPoint(1)
    H.eq(subY, hud.SUB_Y_BARE, "no stars: the sub line right under the word")
    H.ok(not rs.stars[1]:IsShown())
    H.ok(M.env.BleakholdCafeStep3.red:IsShown(), "Steam Milk's slot flashes red")
    H.eq(M.sounds[#M.sounds], "igQuestLogAbandonQuest")
    M.Advance(2.1)
    H.ok(not rs:IsShown(), "gone after 2 s")
    H.send(M, "CAFRES", { { 41, 103, "P", 27, 1400, 22, 4, 0, 6, "Brenna", "", 0 } })
    H.eq(rs.word:GetText(), "Perfect!")
    H.ok(rs.stars[3]:IsShown(), "three stars")
    _, _, _, _, subY = rs.sub:GetPoint(1)
    H.eq(subY, hud.SUB_Y, "under the stars")
    local _, _, _, _, moneyY = rs.money:GetPoint(1)
    H.eq(moneyY, hud.SUB_Y, "the coins on the sub line")
    H.eq(rs.sub:GetText(), "+27 XP \194\183 +")
    H.ok(rs.money:IsShown(), "the tip in coins")
    H.eq(rs.money.copper, 1400)
    H.eq(rs.sub2:GetText(), "pay \194\183 +22 pts \194\183 Streak \195\1514",
        "a player's order pays a wage and their tip: pay, then the drink's Café Points")
    H.eq(M.sounds[#M.sounds], "igQuestListComplete")
    M.Advance(1.0)
    H.ok(rs:IsShown(), "held")
    M.Advance(1.1)
    H.ok(not rs:IsShown(), "faded out")
    H.send(M, "CAFRES", { { 41, 103, "G", 0, 600, 12, 0, 0, 6, "Brenna", "", 18 } })
    H.contains(rs.sub:GetText(), "Daily XP cap reached")
    H.eq(rs.money.copper, 600)
    H.eq(rs.word:GetText(), "Good")
    -- no tip: one line of text, no coins
    H.send(M, "CAFRES", { { 43, 103, "S", 5, 0, 0, 0, 0, 6, "Brenna", "", 0 } })
    H.ok(not rs.money:IsShown() and not rs.sub2:IsShown())
    H.eq(rs.sub:GetText(), "+5 XP")
end)

test("cafe hud: a level-up plays LEVELUPSOUND and toasts once (the server's toast counts)", function(M, ns)
    onShift(M)
    local pushed = 0
    local push = ns.Toast.Push
    ns.Toast.Push = function(d) pushed = pushed + 1 return push(d) end
    H.send(M, "TOAST", { { "I", "Barista level 7", "Staff Drink unlocked", "cafe" } })
    H.send(M, "CAFRES", { { 41, 103, "P", 27, 1400, 22, 4, 1, 7, "Brenna", "", 0 } })
    H.eq(M.sounds[#M.sounds], "LEVELUPSOUND")
    M.Advance(2)
    H.eq(pushed, 1, "the server's toast only")
    H.send(M, "CAFRES", { { 42, 103, "P", 27, 1400, 22, 5, 1, 8, "Brenna", "", 0 } })
    M.Advance(5)
    H.eq(pushed, 2, "without a server toast the client's own")
end)

test("cafe hud: the strip counts the shift, its level bar and the Morning Rush", function(M, ns)
    onShift(M)
    local st = M.env.BleakholdCafeStrip
    H.ok(not st.name:IsShown(), "no café name on the strip")
    M.Hover(st.iconHit)
    H.eq(M.env.GameTooltip.__lines[1], "The Lion's Roast", "the café's name is the icon's tooltip")
    H.contains(st.stats.drinks:GetText(), "14")
    H.eq(st.stats.xp:GetText(), "|cffffd100XP|r +212", "this shift's XP, today's in the tooltip")
    M.Hover(st.xpHit)
    H.eq(M.env.GameTooltip.__lines[3], "Today: 210/450 today")
    H.contains(st.stats.level:GetText(), "6")
    H.eq(st.tips.copper, 10600)
    H.ok(math.abs(st.levelBar:GetValue() - (1890 - 1600) / (2320 - 1600)) < 1e-6, "the barista level bar")
    M.Hover(st.levelHit)
    H.eq(M.env.GameTooltip.__lines[2], "1,890 / 2,320")
    H.contains(st.rush.text:GetText(), "Morning Rush in 03:00")
    M.Advance(10)
    H.contains(st.rush.text:GetText(), "Morning Rush in 02:50")
    cafst(M, nil, nil, { "R", 2, 372, 41, 60, 3 })
    M.Advance(0.2)
    H.contains(st.rush.text:GetText(), "Morning Rush \194\183 06:12 left \194\183 41/60 served")
    st.endBtn:Click()
    H.eq(H.lastIntent(M, "CSHIFT").payload, "1,0")
end)

test("cafe hud: warnings: danger, outside the café, mounted; the facing hint on the bar", function(M, ns)
    onShift(M, { [13] = "", [14] = "G", [18] = 32 })
    H.contains(M.env.BleakholdCafeBar.hint:GetText(), "Turn to face the Grinder")
    cafst(M, { [18] = 64, [19] = 4 })
    M.Advance(0.2)
    local st = M.env.BleakholdCafeStrip
    H.contains(st.warn:GetText(), "Dismount and show yourself: 4")
    M.Advance(2)
    H.contains(st.warn:GetText(), "Dismount and show yourself: 2", "counts down")
    cafst(M, { [18] = 8, [19] = 10 })
    M.Advance(0.2)
    H.contains(st.warn:GetText(), "Return to the caf\195\169: 10")
    H.send(M, "CAFE", { { 1, 2, 1, 2, 0, "", 45 } })
    M.Advance(0.2)
    H.contains(st.warn:GetText(), "Danger nearby: the caf\195\169 has paused")
    H.ok(st.warn:IsShown())
end)

test("cafe hud: the queue lists the orders with their marks; a click chooses or takes", function(M, ns)
    onShift(M)
    H.send(M, "CAFQ", { { 1, 5, 6, 2, 3 },
        { 1209, "P", 103, "Brenna", 25000, 25000, "W", "", 0 },
        { 1207, "N", 101, "Sergeant Corwin Ashgrove", 45000, 48000, "W", "", 0 },
        { 1212, "G", 102, "Night Watch Guard", 38000, 51000, "W", "", 0, 7 },
        { 1213, "N", 107, "Lady Seraphine Ravenmoor", 50000, 54000, "W", "", 9 },
        { 1208, "N", 108, "Grandma Hester", 30000, 60000, "T", "Aldric", 0 } })
    M.Advance(0.2)
    local q = M.env.BleakholdCafeQueue
    H.eq(q.header:GetText(), "Queue 5/6 \194\183 2 baristas \194\183 +3 more")
    local rows = q.pool.items
    H.eq(rows[1].mark:GetText(), "Player")
    H.ok(not rows[1].money, "no price: CAFQ has none, and it depends on the customer's level")
    H.eq(rows[3].mark:GetText(), "Group")
    H.eq(rows[4].mark:GetText(), "Level 9")
    H.eq(rows[4].markIcon:GetTexture(), "Interface\\LFGFrame\\UI-LFG-ICON-LOCK")
    H.eq(rows[5].mark:GetText(), "Taken by Aldric")
    H.eq(rows[5]:GetAlpha(), 0.5, "taken rows dimmed")
    -- away from the counter a click chooses the order for Take Order
    rows[2]:Click()
    H.eq(ns.Cafe.SelectedOrder(), 1207)
    H.ok(rows[2].selected, "UI.Select's look")
    -- at the counter it takes it
    cafst(M, { [13] = "V", [14] = "V" })
    M.Advance(0.2)
    rows[1]:Click()
    H.eq(H.lastIntent(M, "CTAKE").payload, "1209")
    M.Advance(1)
    local n = H.countIntents(M, "CTAKE")
    rows[4]:Click()
    H.eq(H.countIntents(M, "CTAKE"), n, "a locked order is not sent")
end)

test("cafe hud: the order chip follows the order: queued, made, ready, delivered", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    local chip = M.env.BleakholdCafeOrderChip
    H.send(M, "CAFO", { { 1210, 1, 103, "Q", 1, "", 0, 5, "", 5300, 530 } })
    M.Advance(0.2)
    H.ok(chip:IsShown())
    H.eq(chip.name:GetText(), "Goldshire Honey Cappuccino")
    H.eq(chip.status:GetText(), "In queue #1")
    H.ok(chip.cancel:IsShown(), "Cancel while queued")
    H.send(M, "CAFO", { { 1210, 1, 103, "M", "", "Aldric", 2, 5, "", 5300, 530 } })
    M.Advance(0.2)
    H.eq(chip.status:GetText(), "Being made by Aldric (2/5)")
    H.ok(chip.bar:IsShown())
    -- the cast bar across the text column (its studs reach CHIP_STUD out of it), its frame clear of the bottom edge
    local hud = ns.Cafe.Hud
    local _, _, _, barX, barY = chip.bar:GetPoint(1)
    H.eq(barX - hud.CHIP_STUD, hud.CHIP_TEXT_X, "the left stud at the text column")
    H.eq(barX + chip.bar:GetWidth() + hud.CHIP_STUD, hud.CHIP_TEXT_X + hud.CHIP_TEXT_W, "the right stud at the status line's end")
    H.eq(chip:GetHeight(), hud.CHIP_H_MADE)
    H.ok(chip:GetHeight() + barY - ns.UI.TIMER_H - 8 >= 7, "the bar's frame 7+ clear of the chip's bottom")
    H.ok(not chip.cancel:IsShown(), "no Cancel while a barista makes it")
    H.send(M, "CAFO", { { 1210, 1, 103, "R", "", "", 5, 5, 179, 5300, 530 } })
    M.Advance(0.2)
    H.contains(chip.status:GetText(), "Ready at the counter")
    H.contains(chip.status:GetText(), "02:59", "179 s, rounded up")
    H.eq(M.sounds[#M.sounds], "igQuestListComplete")
    local n = #M.sounds
    H.send(M, "CAFO", { { 1210, 1, 103, "R", "", "", 5, 5, 170, 5300, 530 } })
    M.Advance(0.2)
    H.eq(#M.sounds, n, "the ready sound plays once")
    H.send(M, "CAFO", { { 1210, 1, 103, "D", "", "", 0, 5, "", 5300, 530 } })
    M.Advance(0.2)
    H.eq(chip.status:GetText(), "Delivered!")
    M.Advance(3)
    H.ok(not chip:IsShown(), "gone 3 s after delivery")
end)

test("cafe hud: the order chip: taking too long, Cancel sends CCANCEL", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    local chip = M.env.BleakholdCafeOrderChip
    H.send(M, "CAFO", { { 1210, 1, 103, "Q", 1, "", 0, 5, "", 5300, 530 } })
    H.send(M, "CAFO", { { 1210, 1, 103, "M", "", "Aldric", 1, 5, "", 5300, 530 } })
    H.send(M, "CAFO", { { 1210, 1, 103, "F", "", "", 1, 5, 40, 5300, 530 } })
    M.Advance(0.2)
    H.eq(chip.status:GetText(), "Taking too long: Rosalind Thornbury is finishing it")
    H.ok(chip.cancel:IsShown())
    chip.cancel:Click()
    H.eq(H.lastIntent(M, "CCANCEL").payload, "1210")
    H.send(M, "CAFO", { { 1210, 1, 103, "X", "", "", 0, 5, "", 5300, 530 } })
    M.Advance(0.2)
    H.eq(chip.status:GetText(), "Order cancelled: your money is back.")
    M.Advance(5)
    H.ok(not chip:IsShown(), "the reason line goes after 5 s")
end)

test("cafe hud: at the bar: rows, their bars and the strip hiding after the last step", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    local ex = FX.examples(M)
    H.send(M, "CAFAT", ex.CAFAT)
    local ab = M.env.BleakholdCafeAtBar
    M.Advance(0.5, 0.5)
    H.ok(ab:IsShown())
    H.eq(ab.rows[1].who:GetText(), "Aldric")
    H.eq(ab.rows[1].text:GetText(), "Pull Shot")
    H.eq(ab.rows[1].count:GetText(), "2/5")
    H.ok(math.abs(ab.rows[1].bar:GetValue() - 0.3) < 0.01, "400 ms in, then 0.5 s: 900 of 3000 ms")
    H.eq(barColor(ab.rows[1].bar), "00FF00", "a timed step green")
    H.ok(math.abs(ab.rows[2].bar:GetValue() - 1400 / 1500) < 0.01)
    -- the player's own row is left out
    H.send(M, "CAFAT", { { 1, 1 }, { "Tester", 3, 400, 3000, "H", 2, 5 } })
    M.Advance(0.2)
    H.ok(not ab.rows[1]:IsShown(), "own row hidden")
    H.send(M, "CAFAT", { { 1, 0 } })
    M.Advance(0.5)
    H.ok(ab:IsShown(), "stays a moment")
    M.Advance(0.7)
    H.ok(not ab:IsShown(), "hidden 1 s after the last one ended")
end)

test("cafe hud: the buff chips show in Stormwind and Orgrimmar, out of combat", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    H.send(M, "CAFBF", { { 1680, "", 1800, 1, 0 } })
    local bf = M.env.BleakholdCafeBuffs
    inZone(M, "Dalaran")
    M.Advance(0.6)
    H.ok(not bf:IsShown(), "not in Dalaran")
    inZone(M, "Stormwind City")
    M.Advance(0.6)
    H.ok(bf:IsShown(), "in Stormwind")
    H.eq(bf.chips[1].time:GetText(), "28 m")
    H.ok(bf.chips[1]:IsShown() and not bf.chips[2]:IsShown() and bf.chips[3]:IsShown())
    H.eq(bf.chips[3].extra:GetText(), "Speed on")
    M.Hover(bf.chips[1])
    H.eq(M.env.GameTooltip.__lines[2], "No effect at the level cap.")
    M.SetCombat(true)
    H.ok(not bf:IsShown(), "hidden in combat")
    M.SetCombat(false)
    H.ok(bf:IsShown())
    inZone(M, "Orgrimmar")
    M.Advance(0.6)
    H.ok(bf:IsShown(), "in Orgrimmar")
end)

test("cafe hud: with motion off nothing pulses and the banner does not pop", function(M, ns)
    onShift(M, { [13] = "E" })
    ticket(M)
    M.Advance(0.2)
    local glow = M.env.BleakholdCafeStep1.glow
    H.ok(glow:IsShown(), "Pull Shot is next")
    local seen = {}
    for _ = 1, 6 do
        M.Advance(0.2, 0.2)
        seen[#seen + 1] = glow:GetAlpha()
    end
    H.ok(seen[1] ~= seen[3] or seen[2] ~= seen[4], "it pulses")
    ns.Cafe.SetOption("cafeMotion", false)
    for i = 1, 6 do
        M.Advance(0.2, 0.2)
        H.eq(glow:GetAlpha(), 0.8, "steady")
    end
    H.send(M, "CAFRES", { { 41, 103, "P", 27, 1400, 22, 4, 0, 6, "Brenna", "", 0 } })
    M.Advance(0.05, 0.05)
    H.eq(M.env.BleakholdCafeResult:GetScale(), ns.Cafe.Option("cafeScale"), "no pop")
end)

test("cafe hud: the HUD scale applies to every café frame", function(M, ns)
    onShift(M)
    M.env.SlashCmdList.BLEAKHOLD("cafe scale 1.2")
    for _, name in ipairs({ "BleakholdCafeBar", "BleakholdCafeStrip", "BleakholdCafeTicket", "BleakholdCafeQueue",
        "BleakholdCafeBuffs", "BleakholdCafeOrderChip", "BleakholdCafeAtBar" }) do
        H.eq(M.env[name]:GetScale(), 1.2, name)
    end
end)

test("cafe hud: the orb tells each café's state", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    H.send(M, "CAFE", { { 1, 1, 1, 2, 1, 180, 45 }, { 2, 4, 0, 0, 0, "", 60 } })
    M.Advance(0.2)
    local orb = M.env.BleakholdOrb_cafe
    H.ok(orb:IsShown())
    M.Hover(orb)
    local text = {}
    for _, l in ipairs(M.env.GameTooltip.__lines) do
        text[#text + 1] = l
    end
    text = table.concat(text, "\n")
    H.contains(text, "The Lion's Roast: Open")
    H.contains(text, "The Grinding Tusk: Closed for safety")
    H.contains(text, "Morning Rush in 03:00")
end)

test("cafe hud: patch-4 missing: the strip says so once a café is open", function(M, ns)
    onShift(M)
    local st = M.env.BleakholdCafeStrip
    H.eq(st.notice:GetText(), "Update your Bleakhold client to see the new caf\195\169 art.")
    H.ok(st.notice:IsShown())
end, { before = function(M)
    M.missingTextures["Interface\\Icons\\BH_Cafe_Espresso"] = true
end })

test("cafe hud: /bh demo cafe plays a shift through the bar and the demo server", function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo cafe")
    M.Advance(3)
    H.ok(ns.Cafe.OnShift(), "on shift")
    H.ok(M.env.BleakholdCafeBar:IsShown())
    M.Advance(18)
    H.eq(ns.S.cafeResult and ns.S.cafeResult.quality, "P", "the first drink is Perfect")
    M.Advance(15)
    H.ok(M.env.BleakholdCafeResult.word:GetText() == "Ruined!" or ns.S.cafeStep.event == "X", "then a ruined one")
    M.Advance(25)
    H.ok(not ns.Cafe.OnShift(), "the shift ended")
    H.ok(ns.S.cafeSummary and ns.S.cafeSummary.drinks >= 2, "with its summary")
    H.eq(M.OverrideAction("1"), nil, "the keys are free again")
    local dropped = 0
    for _, v in pairs(ns.Comm.stats.dropped) do dropped = dropped + v end
    H.eq(dropped, 0, "no frame dropped")
    M.env.SlashCmdList.BLEAKHOLD("demo off")
    H.ok(not M.env.BleakholdCafeBar:IsShown())
end)

test("cafe hud: in demo mode an order runs from the queue to the counter, with the bar's worker shown", function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    H.ok(ns.Cafe.Enabled(), "the demo realm has the café")
    ns.Cafe.Send("CORDER", 1, 103, 10)
    M.Advance(0.5)
    local chip = M.env.BleakholdCafeOrderChip
    H.ok(chip:IsShown())
    H.eq(chip.status:GetText(), "In queue #1")
    M.Advance(3)
    H.eq(chip.status:GetText(), "Being made by Aldric (0/5)")
    H.ok(M.env.BleakholdCafeAtBar:IsShown(), "Aldric at the bar")
    H.eq(M.env.BleakholdCafeAtBar.rows[1].who:GetText(), "Aldric")
    H.eq(M.env.BleakholdCafeAtBar.rows[1].text:GetText(), "Grind Beans")
    M.Advance(11)
    H.contains(chip.status:GetText(), "Ready at the counter")
    M.Advance(5.5)
    H.eq(chip.status:GetText(), "Delivered!")
    H.eq(ns.S.cafeBuffs.coffeeSec ~= nil, true, "the buff is on")
    local dropped = 0
    for _, v in pairs(ns.Comm.stats.dropped) do dropped = dropped + v end
    H.eq(dropped, 0, "no frame dropped")
end)

test("cafe hud: a ready order says how to pick it up", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    local chip = M.env.BleakholdCafeOrderChip
    H.send(M, "CAFO", { { 1210, 1, 103, "R", "", "", 5, 5, 179, 5300, 530 } })
    M.Advance(0.2)
    H.ok(chip.hint:IsShown(), "a second line")
    H.eq(chip.hint:GetText(), "Walk to the counter or sit at a caf\195\169 table to pick it up.")
    H.eq(chip:GetHeight(), ns.Cafe.Hud.CHIP_H_HINT)
    H.send(M, "CAFO", { { 1210, 1, 103, "D", "", "", 0, 5, "", 5300, 530 } })
    M.Advance(0.2)
    H.ok(not chip.hint:IsShown(), "gone once delivered")
end)

test("cafe hud: while the café is paused its clocks stand still, and the resume asks for the tickets", function(M, ns)
    onShift(M)
    ticket(M, 40000, 60000, 2)
    H.send(M, "CAFQ", { { 1, 1, 6, 1, 0 }, { 1207, "N", 101, "Sergeant Corwin Ashgrove", 30000, 48000, "W", "", 0 } })
    H.send(M, "CAFO", { { 1210, 1, 103, "R", "", "", 5, 5, 179, 5300, 530 } })
    M.Advance(1, 0.1)
    local tk = M.env.BleakholdCafeTicket
    H.contains(tk.patience.text:GetText(), "39 s")
    -- an enemy at the counter: CAFE open 2
    H.send(M, "CAFE", { { 1, 2, 1, 2, 1, 179, 45 }, { 2, 1, 0, 0, 1, 180, 60 } })
    M.Advance(60, 0.5)
    H.eq(tk.patience.text:GetText(), "39 s (paused)", "the ticket's patience stood still")
    local q = M.env.BleakholdCafeQueue
    H.contains(q.header:GetText(), "(paused)")
    H.eq(q.pool.items[1].secs:GetText(), "29 s", "the queue's too")
    -- the pickup's clock runs on (the server's order tick still expires a ready order in a pause)
    H.ok(math.abs(ns.Cafe.OrderLeft(ns.S.cafeOrder) - 118) < 1, "the pickup clock ran on")
    local from = #M.sent + 1
    -- the resume: the clocks run on from where they stood; CAFT is asked for (the server sends only CAFQ)
    H.send(M, "CAFE", { { 1, 1, 1, 2, 1, 179, 45 }, { 2, 1, 0, 0, 1, 180, 60 } })
    M.Advance(0.3)
    H.contains(tk.patience.text:GetText(), "39 s")
    H.ok(not tk.patience.text:GetText():find("paused", 1, true))
    local asked = false
    for _, it in ipairs(H.intents(M, from)) do
        if it.op == "GET" and it.payload:find("CAFT", 1, true) then asked = true end
    end
    H.ok(asked, "GET CAFT after the resume")
    M.Advance(10, 0.5)
    H.contains(tk.patience.text:GetText(), "29 s", "counting again")
    H.eq(q.pool.items[1].secs:GetText(), "19 s")
end)

test("cafe hud: at the bar, a row ends with its step even when no clearing CAFAT comes", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    H.send(M, "CAFAT", { { 1, 1 }, { "Aldric", 3, 400, 3000, "H", 2, 5 } })
    local ab = M.env.BleakholdCafeAtBar
    M.Advance(0.5, 0.5)
    H.ok(ab:IsShown() and ab.rows[1]:IsShown(), "Aldric's Pull Shot")
    -- the player walks out of the 30 yd: no "1, 0" comes
    M.Advance(4, 0.5)
    H.ok(not ab:IsShown(), "gone after the step's time and a second")
    -- a zone change forgets the list
    H.send(M, "CAFAT", { { 1, 1 }, { "Aldric", 3, 0, 30000, "H", 2, 5 } })
    M.Advance(0.3)
    H.ok(ab:IsShown())
    M.FireEvent("ZONE_CHANGED_NEW_AREA")
    M.Advance(0.3)
    H.ok(not ab:IsShown(), "another zone: the list is gone")
    H.eq(next(ns.S.cafeAtBar), nil)
end)

test("cafe hud: after a /reload in combat the buff chips stay hidden", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    inZone(M, "Stormwind City")
    -- in combat already, no PLAYER_REGEN_DISABLED in this UI
    M.combat = true
    H.send(M, "CAFBF", { { 1680, "", 1800, 1, 0 } })
    M.Advance(0.6)
    H.ok(not M.env.BleakholdCafeBuffs:IsShown(), "hidden in combat")
    M.SetCombat(false)
    M.Advance(0.6)
    H.ok(M.env.BleakholdCafeBuffs:IsShown(), "back after it")
end)

test("cafe hud: the strip's XP: full rate, then the half rate, then the cap", function(M, ns)
    onShift(M)
    local hud = ns.Cafe.Hud
    -- dayXp is credited XP: the 450 half-rate XP credit at most 225, so a capped day ends at 675, never 900
    H.eq(hud.DayXpText({ dayXp = 210, dayXpFull = 450, dayXpHalf = 450 }), "210/450 today")
    H.eq(hud.DayXpText({ dayXp = 560, dayXpFull = 450, dayXpHalf = 450 }), "450/450 \194\183 +110/225 half rate")
    H.eq(hud.DayXpText({ dayXp = 674, dayXpFull = 450, dayXpHalf = 450 }), "450/450 \194\183 +224/225 half rate")
    H.eq(hud.DayXpText({ dayXp = 675, dayXpFull = 450, dayXpHalf = 450 }), "Daily XP cap reached")
    H.eq(hud.DayXpText({ dayXp = 451, dayXpFull = 450, dayXpHalf = 451 }), "450/450 \194\183 +1/225 half rate",
        "an odd half band credits its floor")
    local strip = M.env.BleakholdCafeStrip
    cafst(M, nil, { "D", 560, 450, 450, 30000, 180000, 180, 400, 14 })
    M.Advance(0.6)
    H.eq(strip.stats.xp:GetText(), "|cffffd100XP|r +212", "the strip itself stays short")
    H.ok(strip.dayXp:IsShown(), "past the full rate: a line under the strip")
    H.eq(strip.dayXp:GetText(), "Barista XP today: 450/450 \194\183 +110/225 half rate")
    M.Hover(strip.xpHit)
    H.eq(M.env.GameTooltip.__lines[3], "Today: 450/450 \194\183 +110/225 half rate")
    cafst(M, nil, { "D", 675, 450, 450, 30000, 180000, 180, 400, 14 })
    M.Advance(0.6)
    H.eq(strip.dayXp:GetText(), "Daily XP cap reached: no more barista XP today", "a capped day says so")
    M.Hover(strip.xpHit)
    H.eq(M.env.GameTooltip.__lines[3], "Today: Daily XP cap reached")
    cafst(M, nil, { "D", 210, 450, 450, 30000, 180000, 180, 400, 14 })
    M.Advance(0.6)
    H.ok(not strip.dayXp:IsShown(), "in full: only the tooltip")
    H.eq(strip.endBtn.label:GetText(), "End Shift", "title case, as the window's button")
end)

test("cafe hud: the strip stays about 600 wide, clear of the target frame at 1080p", function(M, ns)
    M.SetScreen(1920, 1080)
    onShift(M)
    local strip = M.env.BleakholdCafeStrip
    -- the widest a shift gets: over an hour, a long streak, tips at the day's 18 gold cap, the day's XP capped
    cafst(M, { [7] = 3725, [8] = 140, [10] = 24, [11] = 179999, [12] = 675 },
        { "D", 675, 450, 450, 30000, 180000, 180, 400, 14 })
    M.Advance(0.6)
    -- the mock measures text about 6% wider than the client's FRIZQT at these sizes (559 here for the default shift,
    -- 527 in the renderer's preview)
    local w = strip:GetWidth() / 1.06
    H.ok(w <= ns.Cafe.Hud.STRIP_MAX_W, "at most " .. ns.Cafe.Hud.STRIP_MAX_W .. ": " .. w)
    -- centred on UIParent: its left edge clear of the stock target frame (TOPLEFT 250,-4, 232 wide) give or take its
    -- portrait's rim
    local left = (M.env.UIParent:GetWidth() - w) / 2
    H.ok(left >= 250 + 232 - 30, "left edge at " .. left)
end)

-- an NPC's ticket (kind N): Corwin's Black Coffee
local function npcTicket(M, nextStep)
    H.send(M, "CAFT", { { 42, 1207, 101, "N", "Sergeant Corwin Ashgrove", 30000, 48000, nextStep or 1, 0,
        "Black coffee, quick.", { { 1, "N" }, { 3, "N" }, { 25, "N" } }, 3400 } })
end

test("cafe hud: an NPC's tip stops at the daily tip cap; a player's order shows its pay, the strip what was earned",
    function(M, ns)
    onShift(M)
    -- today's NPC tips 29,000 of 30,000 copper: the ticket promises what the cap still allows
    cafst(M, nil, { "D", 210, 450, 450, 29000, 30000, 180, 400, 14 })
    npcTicket(M)
    M.Advance(0.3)
    local tk, st = M.env.BleakholdCafeTicket, M.env.BleakholdCafeStrip
    H.eq(tk.footLabel:GetText(), "Tip: about")
    H.eq(tk.footMoney.copper, 1000, "min(the hint, the cap left)")
    H.ok(not st.caps:IsShown(), "under the cap: no line")
    -- at the cap: no tip promised, and the strip says it
    cafst(M, nil, { "D", 210, 450, 450, 30000, 30000, 180, 400, 14 })
    M.Advance(0.3)
    H.eq(tk.footLabel:GetText(), "Tip: none (daily tip cap reached)")
    H.ok(not tk.footMoney:IsShown(), "no coins")
    H.ok(st.caps:IsShown())
    H.contains(st.caps:GetText(), "Daily tip cap reached")
    -- the result: no tip, and why
    local rs = M.env.BleakholdCafeResult
    H.send(M, "CAFRES", { { 42, 101, "G", 20, 0, 15, 0, 0, 6, "Sergeant Corwin Ashgrove", "Good.", 0 } })
    H.eq(rs.sub:GetText(), "+20 XP \194\183 +15 pts", "the drink's Café Points on the banner")
    H.eq(rs.notes[1]:GetText(), "No tip: the daily tip cap is reached")
    -- a player's order: the pay (the wage and the customer's tip), whatever the NPC cap
    ticket(M)
    M.Advance(0.3)
    H.eq(tk.footLabel:GetText(), "Pay: about")
    H.eq(tk.footMoney.copper, 2100)
    H.ok(tk.footMoney:IsShown())
    H.eq(st.stats.tips:GetText(), "|cffffd100Earned|r", "the strip's money is what the shift earned")
    M.Hover(st.tipsHit)
    H.contains(table.concat(M.env.GameTooltip.__lines, "\n"), "your wage and their tip")
end)

test("cafe hud: an NPC drink's money is a tip on the banner, a player's is pay", function(M, ns)
    onShift(M)
    npcTicket(M)
    M.Advance(0.3)
    local rs = M.env.BleakholdCafeResult
    H.send(M, "CAFRES", { { 42, 101, "P", 30, 900, 18, 2, 0, 6, "Sergeant Corwin Ashgrove", "Good.", 0 } })
    H.eq(rs.sub2:GetText(), "tip \194\183 +18 pts \194\183 Streak \195\1512")
    H.ok(not rs.notes[1]:IsShown(), "nothing capped")
    -- the daily points cap: the strip and the banner say it
    cafst(M, nil, { "D", 210, 450, 450, 3000, 30000, 400, 400, 25 })
    M.Advance(0.3)
    H.contains(M.env.BleakholdCafeStrip.caps:GetText(), "Caf\195\169 Points today: 400/400: no more points today")
    H.send(M, "CAFRES", { { 42, 101, "G", 10, 400, 0, 0, 0, 6, "Sergeant Corwin Ashgrove", "Good.", 0 } })
    H.eq(rs.notes[1]:GetText(), "No Caf\195\169 Points: today's cap is reached")
end)

test("cafe hud: a server-closed NPC ticket's line is plain text, a complaint is quoted", function(M, ns)
    onShift(M)
    npcTicket(M)
    M.Advance(0.3)
    local rs = M.env.BleakholdCafeResult
    H.send(M, "CAFRES", { { 42, 101, "L", 0, 0, 0, 0, 0, 6, "Sergeant Corwin Ashgrove", "The customer has gone.", 0 } })
    H.eq(rs.sub:GetText(), "The customer has gone.", "the server's own line, no quotes")
    npcTicket(M)
    H.send(M, "CAFRES", { { 42, 101, "L", 0, 0, 0, 0, 0, 6, "Sergeant Corwin Ashgrove", "The order was cancelled.", 0 } })
    H.eq(rs.sub:GetText(), "The order was cancelled.")
    npcTicket(M)
    H.send(M, "CAFRES", { { 42, 101, "L", 0, 0, 0, 0, 0, 6, "Sergeant Corwin Ashgrove", "Too slow. I'm off.", 0 } })
    H.eq(rs.sub:GetText(), "\"Too slow. I'm off.\"", "the customer's words")
end)

test("cafe hud: a ruin says the streak ends; a player's first ruin says the second goes to the house", function(M, ns)
    onShift(M, { [13] = "E" })
    ticket(M)
    M.Advance(0.2)
    local rs = M.env.BleakholdCafeResult
    H.send(M, "CAFEV", { { 41, 2, 5, "X", "", "", "", "", 1 } })
    H.eq(rs.sub:GetText(), "Wrong step: the drink starts again from step 1.")
    H.eq(rs.notes[1]:GetText(), "Your Perfect streak ends.")
    H.ok(rs.notes[2]:IsShown())
    H.eq(rs.notes[2]:GetText(), "One more ruin and Rosalind Thornbury takes this order over.")
    local _, _, _, _, y1 = rs.notes[1]:GetPoint(1)
    H.eq(y1, ns.Cafe.Hud.SUB_Y_BARE - ns.Cafe.Hud.NOTE_PITCH, "under the sub line")
    -- an NPC's ticket: the streak only
    npcTicket(M, 2)
    M.Advance(0.2)
    H.send(M, "CAFEV", { { 42, 2, 5, "X", "", "", "", "", 1 } })
    H.eq(rs.notes[1]:GetText(), "Your Perfect streak ends.")
    H.ok(not rs.notes[2]:IsShown(), "no house for an NPC")
end)

test("cafe hud: measured text grows back: a long drink after a short one, two order lines after one", function(M, ns)
    -- the mock measures as the client does: cut to the box once a width and a height are set
    M.measureAsShown = true
    onShift(M)
    local tk = M.env.BleakholdCafeTicket
    local function drink(recipeId, line)
        H.send(M, "CAFT", { { 41, 1209, recipeId, "N", "Grandma Hester", 57000, 60000, 1, 0, line,
            { { 1, "N" }, { 25, "N" } }, 2100 } })
        M.Advance(0.2)
    end
    local fs = tk.drink
    fs:SetWidth(30)
    fs:SetHeight(17)
    fs:SetText("A long drink name here")
    H.eq(fs:GetStringWidth(), 30, "cut to the box")
    local short, long
    for id, r in pairs(ns.CafeData.recipes) do
        if not short or #r.name < #short.name then
            short = r
        end
        if not long or #r.name > #long.name then
            long = r
        end
    end
    drink(short.id, "Tea.")
    local wShort = tk.drink:GetWidth()
    drink(long.id, "Tea.")
    H.ok(tk.drink:GetWidth() > wShort, "the long name gets its width again: " .. tk.drink:GetWidth() .. " > " .. wShort)
    H.eq(tk.line:GetHeight(), 14, "a one-line order")
    drink(long.id, "Two pumps of honey, a pinch of cinnamon and the milk steamed until it sings, if you please.")
    H.eq(tk.line:GetHeight(), 28, "two lines again after a one-line order")
    H.eq(tk.line:GetWidth(), ns.Cafe.Hud.TICKET_W - 24)
    -- at the bar: each row as wide as its own action
    local hud = ns.Cafe.Hud
    local r = M.env.BleakholdCafeAtBar.rows[1]
    hud.LayoutAtBarRow(r, "Aldric", "Serve")
    local wServe = r.text:GetWidth()
    hud.LayoutAtBarRow(r, "Aldric", "Grind Beans")
    H.ok(r.text:GetWidth() > wServe, "a longer action after Serve keeps its width")
end)

test("cafe hud: a queue push mid-click leaves the rows shown (a hide would drop the click)", function(M, ns)
    onShift(M, { [13] = "V", [14] = "V" })
    local ex = FX.examples(M)
    H.send(M, "CAFQ", ex.CAFQ)
    M.Advance(0.3)
    local q = M.env.BleakholdCafeQueue
    local row = q.pool.items[1]
    local hides = 0
    row:HookScript("OnHide", function()
        hides = hides + 1
    end)
    local id = row.data.orderId
    -- mouse down, a CAFQ and a CAFST land, mouse up
    local down = row:GetScript("OnMouseDown")
    down(row, "LeftButton")
    H.send(M, "CAFQ", ex.CAFQ)
    cafst(M, { [13] = "V", [14] = "V", [15] = 4 })
    M.Advance(0.1)
    H.eq(hides, 0, "never hidden by a refresh")
    H.ok(row:IsShown())
    row:Click()
    H.eq(H.intents(M)[#H.intents(M)].op, "CTAKE")
    H.eq(H.intents(M)[#H.intents(M)].payload, tostring(id), "the order pressed")
    -- fewer orders: only the rows past the count hide
    H.send(M, "CAFQ", { ex.CAFQ[1], ex.CAFQ[2] })
    M.Advance(0.1)
    H.eq(q.pool.used, 1)
    H.ok(q.pool.items[1]:IsShown() and not (q.pool.items[2] and q.pool.items[2]:IsShown()))
end)

test("cafe hud: the patch notice shows on the strip for the first minute only", function(M, ns)
    onShift(M)
    local st = M.env.BleakholdCafeStrip
    H.ok(st.notice:IsShown(), "at first")
    M.Advance(61, 0.5)
    H.ok(not st.notice:IsShown(), "gone after a minute")
    cafst(M)
    M.Advance(0.5)
    H.ok(not st.notice:IsShown(), "and stays gone this session")
end, { before = function(M)
    M.missingTextures["Interface\\Icons\\BH_Cafe_Espresso"] = true
end })

test("cafe hud: the running timed step's row prints its own gold zone, the others 'about'", function(M, ns)
    onShift(M)
    ticket(M)
    M.Advance(0.3)
    local tk = M.env.BleakholdCafeTicket
    local rows = tk.rowPool.items
    H.eq(rows[2].sub:GetText(), "Gold about 70-85%")
    -- Pull Shot runs with its zone moved up: 2250-2700 of 3000 ms
    H.send(M, "CAFEV", { { 41, 2, 3, "S", 3000, 2250, 2700, "", 2 } })
    M.Advance(0.1)
    H.eq(rows[2].sub:GetText(), "Gold 75-90%", "the step's real zone")
    H.ok((rows[3].sub:GetText() or ""):match("^Gold about %d+%-%d+%%$"), "a later timed step: the action's zone, about: "
        .. tostring(rows[3].sub:GetText()))
end)

test("cafe hud: in a party the ticket and the at-the-bar list stand right of the party frames", function(M, ns)
    onShift(M)
    local tk, ab = M.env.BleakholdCafeTicket, M.env.BleakholdCafeAtBar
    local hud = ns.Cafe.Hud
    local _, _, _, x = tk:GetPoint(1)
    H.eq(x, hud.LEFT_X, "alone: at the left edge")
    M.party = 2
    M.FireEvent("PARTY_MEMBERS_CHANGED")
    _, _, _, x = tk:GetPoint(1)
    H.eq(x, hud.PARTY_X, "in a party: clear of the party frames")
    local _, _, _, ax = ab:GetPoint(1)
    H.eq(ax, hud.PARTY_X)
    M.party = 0
    M.FireEvent("PARTY_MEMBERS_CHANGED")
    _, _, _, x = tk:GetPoint(1)
    H.eq(x, hud.LEFT_X)
end)

test("cafe hud: the buff chips find the city on any client language; coffee says where it does nothing",
    function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    H.send(M, "CAFBF", { { 1680, 1200, 1800, 1, 1 } })
    local bf = M.env.BleakholdCafeBuffs
    inZone(M, "Sturmwind")
    M.Advance(0.6)
    H.ok(bf:IsShown(), "deDE Sturmwind: the map area says Stormwind City")
    M.Hover(bf.chips[1])
    H.contains(table.concat(M.env.GameTooltip.__lines, "\n"), "Not in battlegrounds, arenas or Wintergrasp.")
    M.Hover(bf.chips[2])
    H.contains(table.concat(M.env.GameTooltip.__lines, "\n"), "Not in battlegrounds, arenas or Wintergrasp.")
    inZone(M, "Dalaran")
    M.Advance(0.6)
    H.ok(not bf:IsShown(), "not in Dalaran")
    -- the world map open: the area is not asked for (it would turn the map), the last answer stands
    local map = M.LoadWorldMap()
    map:Show()
    local asked = 0
    M.env.SetMapToCurrentZone = function()
        asked = asked + 1
    end
    M.FireEvent("ZONE_CHANGED_NEW_AREA")
    M.Advance(0.6)
    H.eq(asked, 0, "never while the world map shows")
end)

test("cafe hud: Tired off shift ends with its rest: the line goes and CAFST is asked for once", function(M, ns)
    FX.connect(M, H, CAFE_BIT)
    -- off shift, Tired (flag 4), 2 s of rest still needed
    H.send(M, "CAFST", { { 0, 0, 6, 1890, 1600, 2320, "", "", "", "", "", "", "", "", "", "", 2, 4 },
        { "D", 210, 450, 450, 30000, 180000, 180, 400, 14 } })
    M.Advance(0.1)
    local hud = ns.Cafe.Hud
    H.contains(hud.TiredLine(ns.S.cafeState), "rest off shift")
    local before = #H.intents(M)
    M.Advance(2.5)
    H.eq(hud.TiredLine(ns.S.cafeState), nil, "rested: nothing halved any more")
    M.Advance(1)
    local asked = 0
    for i, it in ipairs(H.intents(M)) do
        if i > before and it.op == "GET" and it.payload:find("CAFST", 1, true) then
            asked = asked + 1
        end
    end
    H.eq(asked, 1, "CAFST asked for once, so flag 4 clears from the server")
    hud.TiredLine(ns.S.cafeState)
    M.Advance(1)
    local again = 0
    for i, it in ipairs(H.intents(M)) do
        if i > before and it.op == "GET" and it.payload:find("CAFST", 1, true) then
            again = again + 1
        end
    end
    H.eq(again, 1, "only once")
end)
