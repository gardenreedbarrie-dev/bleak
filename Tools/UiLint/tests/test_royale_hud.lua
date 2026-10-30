-- Bleakhold Royale's HUD (RoyaleHud.lua): the top bar's cells and tab in every state (one clock on screen, the value
-- set only when its second changes, the ember and kill flashes, the stage gems), the banners (titles that fit the
-- ribbon, VICTORY for the winner only, the timing and its reduced-motion twin), the stock error text under the banner
-- in the fight, the kill feed (the slide-in, the player's own lines, the storm beast, the quest tracker it steps
-- around), the storm edge over the world with one pulse per storm hit, the spectator bar, the end card (the count-up,
-- the reward rows, the sounds, its height and spot), the layout of every plate at 1080p, 1440p and 2160p, the texel
-- ratio of every sized texture, and the wording rules of the design (section 1.9).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local ROYALE_ART = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\"
local SOUNDS = "Interface\\AddOns\\Bleakhold\\Sounds\\Royale\\"
local MAP = {
    { 901, -1066, 533, -1066, 533, 455, 455, 32, 750, -267, -267 }, { 1, "L", -266, -266, 88, "The Bleak Hold" },
    { 2, "L", 120, 80, 62, "Harrow Farm" },
}

local function near(a, b, eps, msg)
    if type(a) ~= "number" or math.abs(a - b) > (eps or 1e-6) then
        error((msg or "values differ") .. ": expected " .. tostring(b) .. ", got " .. tostring(a), 2)
    end
end

local function connect(M)
    FX.connect(M, H, { [6] = 4096 })
    H.send(M, "ROYM", MAP)
end

-- In a match: QUEUE kind B state 3 (20-40 players).
local function inQueue(M)
    H.send(M, "QUEUE", { { 5, 3, "B", 901, 0, 1, 0, "", "", "", 80, 80, "", 20, 40, "", "", 2 } })
end

-- A ROYS of match 7001 (field index -> value): the lobby before the countdown unless `over` says otherwise.
local function roys(M, over)
    local r = { 7001, 0, 60000, 24, 24, 0, 0, "", "", "", 0, -267, -267, 860, "", "", "", "", "", 0, "", 450, 452, 6,
        "", "", "" }
    for k, v in pairs(over or {}) do r[k] = v end
    H.send(M, "ROYS", { r })
end

-- The fight: alive, circle 2 at (-267,-267) r 320, the next circle shown, the storm moving in 100 s.
local FIGHT = { [2] = 3, [3] = 0, [6] = 2, [11] = 2, [14] = 320, [15] = -200, [16] = -300, [17] = 180,
    [18] = 100000, [19] = 150000, [20] = 20, [22] = -267, [23] = -267 }
local function fight(M, over)
    local t = {}
    for k, v in pairs(FIGHT) do t[k] = v end
    for k, v in pairs(over or {}) do t[k] = v end
    roys(M, t)
end

local function cell(bar, i)
    local c = bar.cells[i]
    return c.label:GetText(), c.value:GetText()
end

local function played(M, list, name)
    local n = 0
    for _, s in ipairs(list) do
        if s == name then n = n + 1 end
    end
    return n
end

local function rgbIs(fs, hex, msg)
    local r, g, b = fs:GetTextColor()
    local er, eg, eb = tonumber(hex:sub(1, 2), 16) / 255, tonumber(hex:sub(3, 4), 16) / 255,
        tonumber(hex:sub(5, 6), 16) / 255
    H.ok(math.abs(r - er) < 0.01 and math.abs(g - eg) < 0.01 and math.abs(b - eb) < 0.01,
        (msg or "colour") .. ": " .. r .. "," .. g .. "," .. b .. " is not " .. hex)
end

------------------------------------------------------------------------------------------------------
-- The top bar
------------------------------------------------------------------------------------------------------
test("royale hud: the bar's cells and tab through the lobby, the drop, the fight and the end", function(M, ns)
    connect(M)
    inQueue(M)
    local bar = M.env.BleakholdRoyaleBar
    local p, rel, rp, x, y = bar:GetPoint(1)
    H.eq(p, "TOP"); H.eq(rel, M.env.UIParent); H.eq(x, 0); H.eq(y, -6)
    H.eq(bar:GetWidth(), 384); H.eq(bar:GetHeight(), 72)
    -- the warm-up brawl: the players of the queue's most, the start, no landing yet
    roys(M, { [2] = 0, [3] = 25000 })
    M.Advance(0.3)
    local l, v = cell(bar, 1)
    H.eq(l, "PLAYERS"); H.eq(v, "24/40")
    l, v = cell(bar, 2)
    H.eq(l, "STARTS IN"); H.eq(v, "0:25")
    l, v = cell(bar, 3)
    H.eq(l, "LANDING"); H.eq(v, "", "no landing: the dash")
    H.ok(bar.cells[3].dash:IsShown(), "the engraved dash")
    H.eq(bar.sub:GetText(), "Warm-up brawl. Nobody dies here.")
    H.ok(bar.tab:IsShown(), "the tab under the bar")
    local shown = 0
    for _, pip in ipairs(bar.pips) do
        if pip:IsShown() then shown = shown + 1 end
        H.ok(not pip.lit, "nothing lit in the lobby")
    end
    H.eq(shown, 6, "six empty sockets: six circles ahead")
    M.Advance(8)
    H.eq(bar.sub:GetText(), "Press ALT-M to choose your landing", "then the tab points at the map")
    -- the landing phase with a pin
    roys(M, { [2] = 1, [3] = 50000, [9] = 120, [10] = 80 })
    M.Advance(0.3)
    l, v = cell(bar, 2)
    H.eq(l, "DROP IN"); H.eq(v, "0:50")
    l, v = cell(bar, 3)
    H.eq(v, "SET")
    rgbIs(bar.cells[3].value, "E5C07B", "SET in gold")
    H.eq(bar.sub:GetText(), "Landing at Harrow Farm")
    -- no pin in the landing phase: RANDOM in ember
    roys(M, { [2] = 1, [3] = 40000 })
    M.Advance(0.3)
    H.eq(select(2, cell(bar, 3)), "RANDOM")
    rgbIs(bar.cells[3].value, "FF7A3D", "RANDOM in ember")
    -- falling: no clock in the bar, no tab (the drop plate speaks)
    roys(M, { [2] = 2, [3] = 20000, [6] = 1, [11] = 1, [25] = 8000, [26] = 20000, [27] = 8000 })
    M.Advance(0.5)
    l, v = cell(bar, 1)
    H.eq(l, "ALIVE"); H.eq(v, "24/24")
    l, v = cell(bar, 2)
    H.eq(l, "DROPPING"); H.eq(v, "")
    H.ok(bar.cells[2].icon:IsShown() and not bar.cells[2].dash:IsShown(), "an icon, no dash")
    l, v = cell(bar, 3)
    H.eq(l, "KILLS"); H.eq(v, "0")
    H.ok(not bar.tab:IsShown(), "no tab while falling")
    -- the fight: the storm's hold, then its move
    fight(M)
    M.Advance(0.3)
    l, v = cell(bar, 2)
    H.eq(l, "STORM CLOSES IN"); H.eq(v, "1:40")
    rgbIs(bar.main, "F2E8D0", "parchment")
    H.ok(not bar.cells[2].icon:IsShown(), "the icon goes")
    fight(M, { [18] = 0, [19] = 20000 })
    M.Advance(0.3)
    l, v = cell(bar, 2)
    H.eq(l, "STORM CLOSING"); H.eq(v, "0:20")
    rgbIs(bar.main, "D7B6FF", "stormLight")
    -- overtime, watched by a spectator: the final storm, the tab says so
    fight(M, { [2] = 4, [6] = 3, [11] = 7, [14] = 0, [21] = "Dalia", [22] = "", [23] = "" })
    M.Advance(0.3)
    l, v = cell(bar, 2)
    H.eq(l, "FINAL STORM"); H.eq(v, "")
    H.ok(bar.cells[2].dash:IsShown(), "the dash")
    H.eq(bar.sub:GetText(), "The storm has closed. It grows every 5 s.")
    -- the winner's name in the middle, smaller, in its class colour
    H.send(M, "ROYK", { { "Dalia", 11, "Aldric", 1, "P", 1, 7, "" } })
    H.send(M, "ROYV", { { "W", 7, "", "", "", "Dalia" } })
    roys(M, { [2] = 5, [3] = 12000, [4] = 1, [6] = 3, [21] = "Dalia" })
    M.Advance(0.3)
    l, v = cell(bar, 2)
    H.eq(l, "WINNER"); H.eq(v, "|cff" .. ns.ClassColor(11) .. "Dalia|r")
    H.eq(select(2, bar.main:GetFont()), 14)
    H.ok(not bar.tab:IsShown(), "no tab in the victory hold")
    -- the end: the bar fades a second after the end card shows
    H.send(M, "ROYE", { { 7001, 9, 24, 0, 100, 0, 30, "Dalia", 11, 7, 1 } })
    roys(M, { [2] = 6, [3] = 120000, [4] = 1, [6] = 3 })
    M.Advance(0.5)
    H.ok(bar:IsShown(), "still there half a second after the card")
    M.Advance(1.2)
    H.ok(not bar:IsShown(), "gone a second after it")
    roys(M, { [2] = 6, [3] = 110000, [4] = 1, [6] = 3 })
    M.Advance(0.3)
    H.ok(not bar:IsShown(), "and stays gone for this match")
end)

test("royale hud: the countdown's last 15 s dim the middle cell; the clock text changes only with its second",
function(M, ns)
    connect(M)
    local bar = M.env.BleakholdRoyaleBar
    roys(M, { [2] = 1, [3] = 30000 })
    M.Advance(0.3)
    H.eq(bar.cells[2]:GetAlpha(), 1)
    local calls = 0
    local orig = bar.main.SetText
    bar.main.SetText = function(self, t)
        calls = calls + 1
        return orig(self, t)
    end
    M.Advance(2)
    H.ok(calls >= 1 and calls <= 3, "the clock set once a second, not ten times: " .. calls)
    bar.main.SetText = nil
    roys(M, { [2] = 1, [3] = 15000 })
    M.Advance(0.3)
    H.eq(bar.main:GetText(), "", "one clock on screen")
    near(bar.cells[2]:GetAlpha(), 0.35, 1e-6, "dimmed")
    -- the gems sit in the middle cell's frame, so they dim with it
    H.eq(bar.pips[1]:GetParent(), bar.cells[2])
end)

test("royale hud: an ember clock flashes once as it turns; the kills flash gold with the clang as they rise",
function(M, ns)
    connect(M)
    local RS = ns.RoyaleStyle
    local bar = M.env.BleakholdRoyaleBar
    roys(M, { [2] = 1, [3] = 22000 })
    M.Advance(0.3)
    rgbIs(bar.main, "F2E8D0", "parchment over 20 s")
    M.Advance(1.9)
    H.ok(RS.Busy(bar.main, "vertexColor"), "the ember flash runs")
    M.Advance(0.4)
    rgbIs(bar.main, "FF7A3D", "ember in the last 20 s")
    -- the kills
    fight(M, { [7] = 0 })
    M.Advance(0.3)
    local before = #M.soundFiles
    fight(M, { [7] = 1 })
    H.ok(RS.Busy(bar.cells[3].value, "vertexColor"), "the gold flash")
    H.eq(M.soundFiles[before + 1], SOUNDS .. "kill.wav")
    M.Advance(0.4)
    rgbIs(bar.cells[3].value, "E5C07B", "kills in gold")
    H.eq(select(2, cell(bar, 3)), "1")
    -- a new match first seen with kills (a /reload): no clang
    before = #M.soundFiles
    fight(M, { [1] = 7002, [7] = 3 })
    M.Advance(0.3)
    H.eq(#M.soundFiles, before, "no flash for kills seen the first time")
end)

test("royale hud: the gem just lit pulses for 3 s; the stage count sets the gems, centred", function(M, ns)
    connect(M)
    local bar = M.env.BleakholdRoyaleBar
    fight(M, { [11] = 1 })
    M.Advance(0.3)
    fight(M, { [11] = 2 })
    M.Advance(0.3)
    H.ok(bar.pips[2].lit and bar.pips[2].pulsing, "the new gem pulses")
    H.ok(not bar.pips[1].pulsing, "the older one does not")
    M.Advance(3.2)
    H.ok(not bar.pips[2].pulsing, "for three seconds")
    -- sixteen stages: spaced min(14, 116 / n), centred under the value
    fight(M, { [11] = 3, [24] = 16 })
    M.Advance(0.3)
    local _, _, _, x1 = bar.pips[1]:GetPoint(1)
    local _, _, _, x16 = bar.pips[16]:GetPoint(1)
    near(x1 + x16, 0, 1e-6, "centred")
    near(x16 - x1, 15 * 116 / 16, 1e-6, "116 units for sixteen")
end)

------------------------------------------------------------------------------------------------------
-- Banners
------------------------------------------------------------------------------------------------------
test("royale hud: every banner's title row fits the ribbon's iron band; long titles shrink, never under 21",
function(M, ns)
    connect(M)
    fight(M)
    M.Advance(0.3)
    local Hud = ns.RoyaleHud
    local banner = Hud.banner
    local list = { { title = "VICTORY", icon = "crown" }, { title = "WINNER", icon = "crown" },
        { title = "PLAYERS LEFT", numeral = true, value = 10 } }
    for _, def in pairs(Hud.EVENT_BANNERS) do
        if not def.numeral then
            list[#list + 1] = { title = def.title, icon = def.icon }
        end
    end
    for i, e in ipairs(list) do
        M.Advance(3)
        Hud.Banner({ key = "t" .. i, title = e.title, color = "gold", icon = e.icon, numeral = e.numeral,
            value = e.value, line = "A line." })
        Hud.UpdateBanner()
        H.eq(Hud.current.title, e.title)
        local cap = banner.title.cap
        H.ok(cap >= 21 and cap <= 26, e.title .. " cap " .. cap)
        local lead = e.numeral and banner.num or banner.icon
        local _, _, _, lx = lead:GetPoint(1)
        local _, _, _, tx = banner.title:GetPoint(1)
        local right = tx + banner.title:GetWidth()
        H.ok(lx >= -238 - 1e-6 and right <= 238 + 1e-6, e.title .. " fits: " .. lx .. " .. " .. right)
        near(-lx, right, 1e-6, e.title .. " centred")
    end
    H.eq(Hud.EVENT_BANNERS.A.title, "THUNDERMAW AWAKENS")
end)

test("royale hud: a banner enters at once, holds 2.4 s and leaves; reduced motion keeps the timing", function(M, ns)
    connect(M)
    fight(M)
    M.Advance(0.3)
    local Hud, RS = ns.RoyaleHud, ns.RoyaleStyle
    local banner = M.env.BleakholdRoyaleBanner
    local p, rel, rp, x, y = banner:GetPoint(1)
    H.eq(p, "TOP"); H.eq(y, -104); H.eq(banner:GetWidth(), 620); H.eq(banner:GetHeight(), 96)
    H.eq(banner:GetFrameStrata(), "HIGH")
    H.send(M, "ROYV", { { "S", 3, "", "", "", "" } })
    H.ok(banner:IsShown(), "at once")
    H.ok(RS.Busy(banner, "offset") and RS.Busy(banner.title, "zoom"), "it drops in and the title punches")
    H.ok(played(M, M.sounds, "RaidBossEmoteWarning") == 1, "its sound")
    M.Advance(2.0)
    near(banner:GetAlpha(), 1, 1e-6, "holding")
    M.Advance(1.0)
    H.ok(not banner:IsShown(), "gone after 2.9 s")
    H.eq(Hud.current, nil)
    RS.SetMotion(false)
    H.send(M, "ROYV", { { "D", 0, 120, 80, 20000, "" } })
    near(banner:GetAlpha(), 1, 1e-6, "no fade with motion off")
    H.eq(banner.line:GetText(), "Supplies fall near Harrow Farm in 0:20.")
    M.Advance(2.5)
    H.ok(banner:IsShown(), "still the full hold")
    M.Advance(0.6)
    H.ok(not banner:IsShown(), "and gone")
end)

------------------------------------------------------------------------------------------------------
-- The stock error text
------------------------------------------------------------------------------------------------------
local function errorsY(M)
    local p, rel, rp, x, y = M.env.UIErrorsFrame:GetPoint(1)
    return p == "TOP" and rp == "TOP" and x == 0 and y or nil
end

test("royale hud: the stock error text moves under the banner in the fight and back after the match", function(M, ns)
    connect(M)
    roys(M, { [2] = 1, [3] = 30000 })
    M.Advance(0.3)
    H.eq(errorsY(M), -122, "the lobby leaves it (it would sit over the character)")
    fight(M)
    M.Advance(0.3)
    H.eq(errorsY(M), -206, "under the banner in the fight")
    roys(M, { [2] = 6, [6] = 3 })
    M.Advance(0.3)
    H.eq(errorsY(M), -122, "back when the match is over")
    -- AddicatUI has a spot of its own for it: the player chose it
    M.env.AddicatUI = { db = { profile = { widgets = { errorMessages = { custom_position = true } } } } }
    M.env.UIErrorsFrame:ClearAllPoints()
    M.env.UIErrorsFrame:SetPoint("CENTER", M.env.UIParent, "CENTER", 0, 160)
    fight(M, { [1] = 7002 })
    M.Advance(0.3)
    local p, _, _, _, y = M.env.UIErrorsFrame:GetPoint(1)
    H.eq(p, "CENTER"); H.eq(y, 160)
end)

------------------------------------------------------------------------------------------------------
-- The kill feed
------------------------------------------------------------------------------------------------------
test("royale hud: a new feed line slides in, the older ones step down; the player's own lines are marked in gold",
function(M, ns)
    connect(M)
    fight(M)
    local RS = ns.RoyaleStyle
    local feed = ns.RoyaleHud.feed
    local p, _, _, x, y = M.env.BleakholdRoyaleFeed:GetPoint(1)
    H.eq(p, "TOPRIGHT"); H.eq(x, -24); H.eq(y, -232)
    H.send(M, "ROYK", { { "Aldric", 1, "Brenna", 8, "P", 23, 1, "" } })
    H.ok(RS.Busy(feed.lines[1].body, "offset"), "the new line slides in")
    M.Advance(0.3)
    H.send(M, "ROYK", { { "Tester", 1, "Corwin", 5, "P", 22, 1, "" } })
    H.ok(RS.Busy(feed.lines[1].body, "offset") and RS.Busy(feed.lines[2].body, "offset"), "in, and one down")
    M.Advance(0.3)
    H.ok(feed.lines[1].mine and feed.lines[1].mark:IsShown() and feed.lines[1].wash:IsShown(), "own line")
    H.ok(not feed.lines[2].mark:IsShown() and not feed.lines[2].wash:IsShown(), "another's")
    H.contains(feed.lines[1].killer:GetText(), "Tester")
    -- the storm beast as the killer (cause B, once State takes it): its name in beast green, the claw
    local S = ns.S
    S.royaleFeed[#S.royaleFeed + 1] = { killer = "Thundermaw", killerClassId = 0, victim = "Dalia", victimClassId = 11,
        cause = "B", at = M.now }
    ns.Fire("STATE", "ROYK")
    M.Advance(0.2)
    H.eq(feed.lines[1].killer:GetText(), "|cff8FD14FThundermaw|r")
    H.eq(feed.lines[1].icon.rsIcon, "claw")
    -- a long name is cut, the strip never wider than the feed
    H.send(M, "ROYK", { { string.rep("W", 40), 1, string.rep("M", 40), 2, "P", 20, 1, "" } })
    M.Advance(0.2)
    H.ok(feed.lines[1].killer:GetWidth() <= ns.RoyaleHud.FEED_NAME_W + 1e-6, "the killer cut")
    H.ok(feed.lines[1].strip:GetWidth() <= 330, "the strip within the feed")
end)

test("royale hud: the feed steps left of a quest tracker under it, never when the player placed it", function(M, ns)
    connect(M)
    fight(M)
    local feed = M.env.BleakholdRoyaleFeed
    local tracker = M.QuestTracker()
    H.send(M, "ROYK", { { "Aldric", 1, "Brenna", 8, "P", 23, 1, "" } })
    M.Advance(0.6)
    local p, rel, rp, x, y = feed:GetPoint(1)
    H.eq(p, "TOPRIGHT"); H.eq(rel, tracker); H.eq(rp, "TOPLEFT"); H.eq(x, -12); H.eq(y, 0)
    H.ok(tracker:IsShown(), "the tracker untouched")
    -- no quests tracked: back to its spot
    M.questWatches = 0
    M.Advance(0.6)
    p, rel, rp, x, y = feed:GetPoint(1)
    H.eq(rel, M.env.UIParent); H.eq(x, -24); H.eq(y, -232)
    -- placed by the player: it stays there
    M.questWatches = 1
    ns.cdb.windows.BleakholdRoyaleFeed = { point = "TOPRIGHT", relPoint = "TOPRIGHT", x = -300, y = -300 }
    ns.RoyaleHud.feedPos.Anchor()
    M.Advance(0.6)
    p, rel, rp, x, y = feed:GetPoint(1)
    H.eq(rel, M.env.UIParent); H.eq(x, -300)
end)

------------------------------------------------------------------------------------------------------
-- The storm edge
------------------------------------------------------------------------------------------------------
test("royale hud: the storm edge over the world: 0.5, 0.25 with the exe's tint, one pulse per storm hit",
function(M, ns)
    connect(M)
    local vg = M.env.BleakholdRoyaleVignette
    H.eq(vg:GetParent(), M.env.WorldFrame, "a WorldFrame child: Alt-Z keeps it")
    H.eq(vg.tex.rsPath, ROYALE_ART .. "Vignette")
    local hp = 1000
    M.env.UnitHealth = function() return hp end
    fight(M, { [22] = 300, [23] = 300 })
    M.Advance(0.3)
    H.ok(vg:IsShown(), "outside")
    near(vg:GetAlpha(), 0.5, 1e-6, "steady, no breathing")
    M.FireEvent("UNIT_HEALTH", "player")
    hp = 900
    M.FireEvent("UNIT_HEALTH", "player")
    near(vg:GetAlpha(), 0.6, 1e-6, "a hit: up by 0.1")
    M.Advance(0.6)
    near(vg:GetAlpha(), 0.5, 1e-6, "settled")
    hp = 800
    M.FireEvent("UNIT_HEALTH", "target")
    M.FireEvent("UNIT_HEALTH", "player")
    near(vg:GetAlpha(), 0.5, 1e-6, "at most one pulse per 0.8 s")
    M.Advance(0.3)
    hp = 700
    M.FireEvent("UNIT_HEALTH", "player")
    near(vg:GetAlpha(), 0.6, 1e-6, "the next hit pulses")
    M.Advance(0.6)
    -- Bleakhold.exe tints the screen itself: the edge softens
    M.env.BleakholdStorm_Status = function() return "" end
    M.Advance(0.2)
    near(vg:GetAlpha(), 0.25, 1e-6, "under the exe's tint")
    -- in and out: the sound at most every 10 s, SAFE on leaving
    local enters = played(M, M.sounds, "igPVPUpdate")
    H.eq(enters, 1)
    fight(M)
    M.Advance(0.2)
    H.eq(M.env.BleakholdRoyaleBar.sub:GetText(), "SAFE")
    fight(M, { [22] = 300, [23] = 300 })
    M.Advance(0.2)
    H.eq(played(M, M.sounds, "igPVPUpdate"), 1, "not again within 10 s")
    fight(M)
    M.Advance(10)
    fight(M, { [22] = 300, [23] = 300 })
    M.Advance(0.2)
    H.eq(played(M, M.sounds, "igPVPUpdate"), 2, "again after 10 s")
end, { before = function(M)
    M.LoadWorldFrame()
end })

------------------------------------------------------------------------------------------------------
-- The spectator bar
------------------------------------------------------------------------------------------------------
test("royale hud: the spectator bar names the watched player, cross-fades a new one, and ends with the match",
function(M, ns)
    connect(M)
    local RS = ns.RoyaleStyle
    local sb = M.env.BleakholdRoyaleSpectate
    fight(M)
    H.send(M, "ROYK", { { "Aldric", 1, "Tester", 1, "P", 11, 3, "" } })
    fight(M, { [6] = 3, [21] = "Aldric", [22] = "", [23] = "" })
    M.Advance(0.3)
    local p, _, _, x, y = sb:GetPoint(1)
    H.eq(p, "BOTTOM"); H.eq(y, 170); H.eq(sb:GetWidth(), 460); H.eq(sb:GetHeight(), 68)
    H.eq(sb.label:GetText(), "SPECTATING")
    H.eq(sb.name:GetText(), "|cff" .. ns.ClassColor(1) .. "Aldric|r|cffBDB4A0 · 3 kills|r")
    fight(M, { [6] = 3, [21] = "Dalia", [22] = "", [23] = "" })
    H.ok(RS.Busy(sb.name, "alpha"), "the name cross-fades")
    H.contains(sb.name:GetText(), " · 0 kills")
    H.eq(sb.prev.label:GetText(), "« Prev"); H.eq(sb.next.label:GetText(), "Next »")
    H.ok(sb.killer:IsEnabled(), "the camera works")
    roys(M, { [2] = 6, [6] = 3 })
    M.Advance(0.3)
    H.eq(sb.name:GetText(), "The match is over.")
    H.ok(not sb.killer:IsEnabled() and not sb.next:IsEnabled(), "no camera after the match")
end)

------------------------------------------------------------------------------------------------------
-- The end card
------------------------------------------------------------------------------------------------------
test("royale hud: the end card counts its tiles up, slides the rewards in and plays the elimination", function(M, ns)
    connect(M)
    fight(M, { [6] = 3, [22] = "", [23] = "" })
    M.Advance(0.3)
    local ec = M.env.BleakholdRoyaleResult
    H.send(M, "ROYE", { { 7001, 7, 32, 2, 18400, 2100, 214, "", "", "", 1 }, { "H", 180, "", "Placement" },
        { "S", 20, "", "Placement" } })
    M.Advance(0.1)
    H.eq(ec:GetFrameStrata(), "DIALOG")
    H.eq(ec:GetWidth(), 440)
    H.ok(ec.tiles[2].value:GetText() ~= "18,400", "counting up: " .. tostring(ec.tiles[2].value:GetText()))
    H.ok(ec.rewards[1]:GetAlpha() < 1, "the reward rows slide in after the plate")
    M.Advance(0.8)
    H.eq(ec.tiles[2].value:GetText(), "18,400")
    H.eq(ec.tiles[4].value:GetText(), "3:34")
    H.eq(ec.tiles[1].label:GetText(), "ELIMINATIONS"); H.eq(ec.tiles[4].label:GetText(), "SURVIVED")
    near(ec.rewards[2]:GetAlpha(), 1, 1e-6, "in")
    H.eq(played(M, M.sounds, "igQuestLogAbandonQuest"), 1, "the elimination's sound")
    H.eq(played(M, M.sounds, "AchievementSound"), 0)
    -- the same result again (the end, with the winner): no second entrance, no second sound
    H.send(M, "ROYE", { { 7001, 7, 32, 2, 18400, 2100, 214, "Dalia", 11, 7, 1 }, { "H", 180, "", "Placement" },
        { "S", 20, "", "Placement" } })
    M.Advance(0.1)
    H.eq(ec.tiles[2].value:GetText(), "18,400", "no count-up again")
    H.eq(played(M, M.sounds, "igQuestLogAbandonQuest"), 1)
    H.ok(ec.winner:IsShown())
end)

test("royale hud: the winner hears AchievementSound once for the VICTORY banner and the card together",
function(M, ns)
    connect(M)
    fight(M)
    M.Advance(0.3)
    roys(M, { [2] = 5, [6] = 5, [4] = 1 })
    H.send(M, "ROYV", { { "W", 4, "", "", "", "Tester" } })
    H.send(M, "ROYE", { { 7001, 1, 24, 4, 30000, 0, 600, "Tester", 1, 4, 1 }, { "H", 400, "", "Victory" } })
    M.Advance(1)
    H.eq(ns.RoyaleHud.current.title, "VICTORY")
    H.eq(ns.RoyaleHud.result.title.title, "VICTORY")
    H.eq(played(M, M.sounds, "AchievementSound"), 1, "once")
end)

test("royale hud: the end card holds its rewards within 430 units; an item shows its own icon", function(M, ns)
    connect(M)
    fight(M, { [6] = 3, [22] = "", [23] = "" })
    M.env.GetItemIcon = function(id) return id == 40752 and "Interface\\Icons\\INV_Misc_Bag_10" or nil end
    local recs = { { 7001, 7, 32, 2, 18400, 2100, 214, "Dalia", 11, 7, 1 }, { "I", 1, 40752, "Supply drop" } }
    for i = 1, 7 do recs[#recs + 1] = { "H", 10 * i, "", "Line " .. i } end
    H.send(M, "ROYE", recs)
    M.Advance(1)
    local ec = M.env.BleakholdRoyaleResult
    H.ok(ec:GetHeight() <= 430, "height " .. ec:GetHeight())
    local row = ec.rewards[1]
    H.ok(row.item:IsShown() and not row.icon:IsShown(), "the item's icon")
    H.eq(row.item:GetTexture(), "Interface\\Icons\\INV_Misc_Bag_10")
    local last
    for i, r in ipairs(ec.rewards) do
        if r:IsShown() then last = i end
    end
    H.ok(last and last < 8, "not every row fits")
    H.contains(ec.rewards[last].reason:GetText(), "more")
end)

test("royale hud: the end card rises over the spectator bar on a 768-unit screen, never into the top bar",
function(M, ns)
    M.SetScreen(1920, 1080, 1)
    connect(M)
    fight(M)
    H.send(M, "ROYK", { { "Aldric", 1, "Tester", 1, "P", 11, 3, "" } })
    fight(M, { [6] = 3, [21] = "Aldric", [22] = "", [23] = "" })
    H.send(M, "ROYE", { { 7001, 7, 32, 2, 18400, 2100, 214, "Dalia", 11, 7, 1 }, { "H", 180, "", "Placement" },
        { "H", 50, "", "2 eliminations" }, { "S", 20, "", "Placement" } })
    M.Advance(1)
    local ec = M.env.BleakholdRoyaleResult
    local _, _, _, _, cy = ec:GetPoint(1)
    local half = M.env.UIParent:GetHeight() / 2
    local bottom = half + cy - ec:GetHeight() / 2
    local top = half + cy + ec:GetHeight() / 2
    H.ok(cy > 40, "raised: " .. cy)
    H.ok(bottom >= 170 + 68 - 1e-6, "clear of the spectator bar: " .. bottom)
    H.ok(top <= 2 * half - 112 + 1e-6, "under the bar's tab: " .. top)
end)

------------------------------------------------------------------------------------------------------
-- Layout (section 7.1, item 13) and texel ratios (item 12)
------------------------------------------------------------------------------------------------------
local FP = { TOPLEFT = { 0, 0 }, TOP = { 0.5, 0 }, TOPRIGHT = { 1, 0 }, LEFT = { 0, 0.5 }, CENTER = { 0.5, 0.5 },
    RIGHT = { 1, 0.5 }, BOTTOMLEFT = { 0, 1 }, BOTTOM = { 0.5, 1 }, BOTTOMRIGHT = { 1, 1 } }

-- A region's rect in its root's units (left, top, right, bottom; y grows downwards), from its anchors, sizes and
-- string widths; regions inside the root carry no scale of their own.
local function resolver(root)
    local cache = {}
    local function res(o)
        if o == root then
            return { 0, 0, root:GetWidth(), root:GetHeight() }
        end
        if cache[o] then return cache[o] end
        local L, R, CX, T, B, CY
        for i = 1, o:GetNumPoints() do
            local p, rel, rp, x, y = o:GetPoint(i)
            local rr = res(rel or o:GetParent())
            local tx = rr[1] + (rr[3] - rr[1]) * FP[rp][1] + (x or 0)
            local ty = rr[2] + (rr[4] - rr[2]) * FP[rp][2] - (y or 0)
            local ax, ay = FP[p][1], FP[p][2]
            if ax == 0 then L = tx elseif ax == 1 then R = tx else CX = tx end
            if ay == 0 then T = ty elseif ay == 1 then B = ty else CY = ty end
        end
        local w, h = o:GetWidth() or 0, o:GetHeight() or 0
        if o:IsObjectType("FontString") then
            if w <= 0 then w = o:GetStringWidth() end
            if h <= 0 then h = select(2, o:GetFont()) end
        end
        if not (L and R) then
            if L then R = L + w elseif R then L = R - w elseif CX then L, R = CX - w / 2, CX + w / 2 end
        end
        if not (T and B) then
            if T then B = T + h elseif B then T = B - h elseif CY then T, B = CY - h / 2, CY + h / 2 end
        end
        cache[o] = { L, T, R, B }
        return cache[o]
    end
    return res
end

local function inside(res, o, box, what)
    local r = res(o)
    local ok = r[1] >= box[1] - 0.01 and r[2] >= box[2] - 0.01 and r[3] <= box[3] + 0.01 and r[4] <= box[4] + 0.01
    H.ok(ok, string.format("%s: %.1f,%.1f .. %.1f,%.1f leaves %.1f,%.1f .. %.1f,%.1f", what, r[1], r[2], r[3], r[4],
        box[1], box[2], box[3], box[4]))
    if o:IsObjectType("FontString") and o:GetWidth() > 0 and o.hudText ~= nil then
        H.ok(o:GetStringWidth() <= o:GetWidth() + 0.01 or o:GetText() == "",
            what .. " not cut: " .. o:GetText() .. " " .. o:GetStringWidth() .. " > " .. o:GetWidth())
    end
end

-- The rim's inner edge of a plate: its art's edge plus rim, at its corner size.
local slices
local function rimBox(frame, plate)
    local sl = slices[plate.kind]
    local k = (sl.edge + sl.rim) * plate.corner / sl.margin
    return { k, k, frame:GetWidth() - k, frame:GetHeight() - k }
end

for _, screen in ipairs({ { 1920, 1080 }, { 2560, 1440 }, { 3840, 2160 } }) do
    test(("royale hud: every plate's content stays inside it at %dx%d, text clamped to 32 px"):format(screen[1],
        screen[2]), function(M, ns)
        M.SetScreen(screen[1], screen[2], 1)
        slices = ns.RoyaleArt.slices
        local RS, Hud = ns.RoyaleStyle, ns.RoyaleHud
        connect(M)
        inQueue(M)
        -- the bar: the widest values of each state, the storm tab
        local bar = Hud.bar
        local res = resolver(bar)
        for _, st in ipairs({ { [2] = 0, [3] = 25000 }, { [2] = 1, [3] = 50000, [9] = 120, [10] = 80 },
            { [2] = 1, [3] = 40000 }, { [2] = 3, [4] = 40, [5] = 40, [7] = 12, [11] = 16, [24] = 16, [14] = 320,
                [18] = 600000, [19] = 700000, [20] = 20, [22] = 300, [23] = 300 },
            { [2] = 4, [4] = 40, [5] = 40, [6] = 3, [11] = 17, [24] = 16, [14] = 0, [22] = "", [23] = "" } }) do
            roys(M, st)
            M.Advance(0.5)
            res = resolver(bar)
            local box = rimBox(bar, bar.art)
            for i, c in ipairs(bar.cells) do
                inside(res, c.label, box, "bar label " .. i)
                inside(res, c.value, box, "bar value " .. i)
                local _, size = c.value:GetFont()
                H.ok(size * RS.PxPerUnit(c.value) <= 32 + 1e-6, "value within 32 px")
                local _, lsize = c.label:GetFont()
                H.ok(lsize * RS.PxPerUnit(c.label) <= 32 + 1e-6, "label within 32 px")
            end
            for i, pip in ipairs(bar.pips) do
                if pip:IsShown() then inside(res, pip, box, "gem " .. i) end
            end
            if bar.tab:IsShown() then
                local tres = resolver(bar.tab)
                local tbox = rimBox(bar.tab, bar.tab.art)
                inside(tres, bar.tab.text, tbox, "tab text")
                if bar.tab.icon:IsShown() then inside(tres, bar.tab.icon, tbox, "tab icon") end
            end
        end
        -- the banner: the title row and the line inside the iron band (15-80 units down, clear of its fading ends)
        for _, e in ipairs({ { "N", 10 }, { "D", 0, 120, 80, 20000 }, { "W", 7, nil, nil, nil, "Dalia" } }) do
            H.send(M, "ROYV", { { e[1], e[2], e[3] or "", e[4] or "", e[5] or "", e[6] or "" } })
            M.Advance(3)
        end
        Hud.Banner({ key = "x", title = "THUNDERMAW AWAKENS", color = "beast", icon = "beast",
            line = "Slay it and claim its hoard." })
        M.Advance(3)
        local banner = Hud.banner
        local bres = resolver(banner)
        local band = { 72, 15, 548, 81 }
        inside(bres, banner.title, band, "banner title")
        inside(bres, banner.icon, band, "banner icon")
        inside(bres, banner.line, { 30, 15, 590, 81 }, "banner line")
        -- the end card and the spectator bar
        fight(M, { [6] = 3, [21] = "Aldric Stormwind", [22] = "", [23] = "" })
        H.send(M, "ROYE", { { 7001, 17, 40, 12, 1234567, 999999, 3599, "Aldric Stormwind", 1, 12, 1 },
            { "H", 1250, "", "Placement" }, { "H", 300, "", "12 eliminations" }, { "S", 25, "", "Placement" } })
        M.Advance(1)
        local ec = Hud.result
        H.ok(ec:GetHeight() <= 430, "the card's height")
        local eres = resolver(ec)
        local ebox = rimBox(ec, ec.art)
        for _, r in ipairs({ ec.title, ec.rank, ec.of, ec.winner, ec.keep, ec.requeue, ec.leave }) do
            inside(eres, r, ebox, "end card")
        end
        for i, t in ipairs(ec.tiles) do
            inside(eres, t, ebox, "tile " .. i)
            local tres = resolver(t)
            local tbox = rimBox(t, t.art)
            inside(tres, t.value, tbox, "tile value " .. i)
            inside(tres, t.label, tbox, "tile label " .. i)
        end
        for i, r in ipairs(ec.rewards) do
            if r:IsShown() then inside(eres, r, ebox, "reward row " .. i) end
        end
        local sb = Hud.spectate
        local sres = resolver(sb)
        local sbox = rimBox(sb, sb.art)
        for _, r in ipairs({ sb.label, sb.name, sb.prev, sb.killer, sb.next, sb.requeue, sb.leave }) do
            inside(sres, r, sbox, "spectator bar")
        end
        H.ok(sres(sb.next)[3] < sres(sb.requeue)[1], "the camera buttons clear of Queue again")
    end)
end

-- Width and height in texels of an Art\Royale file (TGA header, or BLP2 header).
local function fileDims(path)
    local rel = path:match("^Interface\\AddOns\\Bleakhold\\(.+)$"):gsub("\\", "/")
    local s = host_readfile(addonDir .. "/" .. rel .. ".tga")
    if s then
        return s:byte(13) + s:byte(14) * 256, s:byte(15) + s:byte(16) * 256
    end
    s = assert(host_readfile(addonDir .. "/" .. rel .. ".blp"), "no art file for " .. path)
    local function u32(o)
        return s:byte(o + 1) + s:byte(o + 2) * 256 + s:byte(o + 3) * 65536 + s:byte(o + 4) * 16777216
    end
    return u32(12), u32(16)
end

local STRETCHED = { Plate = true, PlateTab = true, Button = true, ButtonGlow = true, LabelHalo = true,
    ShineStrip = true, Vignette = true }

for _, screen in ipairs({ { 1920, 1080 }, { 2560, 1440 } }) do
    test(("royale hud: no HUD art minified past 2.2x at %dx%d, UI scale 1"):format(screen[1], screen[2]),
    function(M, ns)
        M.SetScreen(screen[1], screen[2], 1)
        local RS, Hud = ns.RoyaleStyle, ns.RoyaleHud
        connect(M)
        fight(M)
        H.send(M, "ROYK", { { "Aldric", 1, "Tester", 1, "P", 11, 3, "" } })
        fight(M, { [6] = 3, [21] = "Aldric", [22] = "", [23] = "" })
        H.send(M, "ROYV", { { "N", 10, "", "", "", "" } })
        H.send(M, "ROYE", { { 7001, 7, 32, 2, 18400, 2100, 214, "Dalia", 11, 7, 1 }, { "H", 180, "", "Placement" },
            { "S", 20, "", "Placement" } })
        M.Advance(1)
        local roots = { [Hud.bar] = true, [Hud.banner] = true, [Hud.feed] = true, [Hud.result] = true,
            [Hud.spectate] = true }
        local checked, worst, what = {}, 0, ""
        local function measure()
            for _, o in ipairs(M.objects) do
                if o.__otype == "Texture" and type(o.rsPath) == "string" and o.rsPath:find(ROYALE_ART, 1, true) == 1
                    and o:IsVisible() and o:GetHeight() > 0 and not STRETCHED[o.rsArt] and roots[RS.RootOf(o)] then
                    local w, h = fileDims(o.rsPath)
                    local ulx, uly, llx, lly = o:GetTexCoord()
                    local texels = math.sqrt(((llx - ulx) * w) ^ 2 + ((lly - uly) * h) ^ 2)
                    local ratio = texels / (o:GetHeight() * RS.PxPerUnit(o))
                    checked[o.rsArt] = true
                    if ratio > worst then worst, what = ratio, (o.rsArt or "?") .. " " .. o:GetHeight() end
                end
            end
        end
        measure()
        -- the bar while falling (its icon) and the long banner at its smallest cap
        fight(M, { [2] = 2, [6] = 1, [11] = 1 })
        Hud.Banner({ key = "x", title = "THUNDERMAW AWAKENS", color = "beast", icon = "beast", line = "x" })
        M.Advance(3)
        measure()
        for _, art in ipairs({ "Gem", "GemGlow", "Titles", "NumeralsS", "Banner", "FeedStrip" }) do
            H.ok(checked[art], art .. " measured")
        end
        H.ok(checked.Icons or checked.IconsSmall, "icons measured")
        H.ok(worst <= 2.2, ("texel ratio %.2f (%s)"):format(worst, what))
    end)
end

------------------------------------------------------------------------------------------------------
-- Wording (section 1.9; section 7.1 item 9)
------------------------------------------------------------------------------------------------------
-- The Royale files this design has rewritten (Royale.lua's glue code is WS-C7's and follows it there).
local ROYALE_FILES = { "RoyaleHud.lua", "RoyaleMap.lua", "RoyaleCountdown.lua", "RoyaleDrop.lua", "RoyaleMinimap.lua",
    "RoyaleStyle.lua" }

-- A file's code without its comments.
local function code(name)
    local text = assert(host_readfile(addonDir .. "/" .. name), name)
    text = text:gsub("%-%-%[%[.-%]%]", "")
    local out = {}
    for line in (text .. "\n"):gmatch("(.-)\n") do
        local inStr, quote, cut = false, nil, nil
        for i = 1, #line do
            local c = line:sub(i, i)
            if inStr then
                if c == "\\" then
                    i = i + 1
                elseif c == quote then
                    inStr = false
                end
            elseif c == '"' or c == "'" then
                inStr, quote = true, c
            elseif line:sub(i, i + 1) == "--" then
                cut = i
                break
            end
        end
        out[#out + 1] = cut and line:sub(1, cut - 1) or line
    end
    return table.concat(out, "\n")
end

test("royale hud: the old sentences are gone, one clock format, key names from MP.KeyText, no glued sentences",
function(M, ns)
    local OLD = { "Players arriving", "Brawl while you wait", "The countdown starts in", "Set your landing pin",
        "Your landing pin is set", "Pins lock in", "Pins are locked", "The drop!", "Storm moves in", "Storm moving",
        "Overtime: the storm", "Storm stage", "Outside the storm circle", "OPEN PARACHUTE", "Click here (or bind",
        "THE STORM CLOSES IN", "is shown on the map", "THE STORM IS MOVING", "Watch the sky", "Nobody to watch",
        "#1 VICTORY", "You left early or did not", "Too few players arrived", "Click the map to set",
        "No pin: you land", "No picture of this map", "B L E A K H O L D" }
    for _, name in ipairs(ROYALE_FILES) do
        local src = code(name)
        for _, s in ipairs(OLD) do
            H.ok(not src:find(s, 1, true), name .. " still says: " .. s)
        end
        H.ok(not src:find("U.Clock(", 1, true), name .. ": RS.Clock is the one clock")
        H.ok(not src:find("MORPHEUS", 1, true), name .. ": MORPHEUS left the Royale UI")
        -- a key name only through MP.KeyText (the map's default key is defined once, in RoyaleMap.lua)
        for lit in src:gmatch('"([^"]*ALT%-M[^"]*)"') do
            H.ok(name == "RoyaleMap.lua" and lit == "ALT-M", name .. " names a key: " .. lit)
        end
        -- the middot only between two pieces of data, never after a sentence
        for lit in src:gmatch('"([^"\n]*)"') do
            if lit:find("·", 1, true) then
                H.ok(not lit:find("[%.!?]%s*·"), name .. " glues sentences: " .. lit)
            end
        end
    end
    local RS = ns.RoyaleStyle
    H.eq(RS.Clock(5), "0:05"); H.eq(RS.Clock(100), "1:40"); H.eq(RS.Clock(723), "12:03")
end)

-- The client's Lua (Engine/Source/lua-5.1: the code generator of Lua 5.1.1-5.1.3, as the 3.3.5a client has it)
-- frees an arithmetic's registers in the wrong order when its left operand needs a register for a constant past
-- index 255 (fixed in 5.1.4): in a chunk with more constants than that, "440 - 2 * t.pad" can come out as 40. The HUD
-- builds its frames in functions (each has its own constants), which keeps its main chunk well under the limit.
local function mainChunkConstants(path)
    local d = string.dump(assert(loadstring(assert(host_readfile(path)))))
    local sizeT, pos = d:byte(9), 13
    local function int()
        local a, b, c, e = d:byte(pos, pos + 3)
        pos = pos + 4
        return a + b * 256 + c * 65536 + e * 16777216
    end
    local n = 0
    for i = sizeT - 1, 0, -1 do n = n * 256 + d:byte(pos + i) end
    pos = pos + sizeT + n           -- the source name
    int(); int()                    -- the first and last line
    pos = pos + 4                   -- upvalues, parameters, vararg, stack size
    pos = pos + 4 * int()           -- the code
    return int()
end

test("royale hud: the HUD's main chunk stays under 256 constants (the client's Lua 5.1 miscompiles past them)",
function(M, ns)
    local n = mainChunkConstants(addonDir .. "/RoyaleHud.lua")
    H.ok(n > 50 and n < 256, "main chunk constants: " .. n)
end)

test("royale hud: a cancelled match's toast says so in the game's voice", function(M, ns)
    connect(M)
    local pushed
    local push = ns.Toast.Push
    ns.Toast.Push = function(t) pushed = t return push(t) end
    roys(M, { [2] = 1, [3] = 20000 })
    roys(M, { [2] = 7, [3] = 0 })
    ns.Toast.Push = push
    H.ok(pushed, "a toast")
    H.eq(pushed.title, "MATCH CANCELLED")
    H.eq(pushed.sub, "Too few players came. You keep your place in the queue.")
    H.eq(pushed.target, "royale")
end)

------------------------------------------------------------------------------------------------------
-- Samples
------------------------------------------------------------------------------------------------------
test("royale hud: /bh royale preview banner|end plays sample screens outside a match, not in one", function(M, ns)
    local Hud = ns.RoyaleHud
    H.ok(Hud.Preview("banner"), "banners")
    H.eq(Hud.current.title, "NEW STORM CIRCLE")
    H.eq(#Hud.queue, 4, "four more waiting")
    M.Advance(3)
    H.eq(Hud.current.title, "SUPPLY DROP")
    H.ok(Hud.Preview("end", "eliminated"), "the end card")
    local ec = M.env.BleakholdRoyaleResult
    M.Advance(1)
    H.ok(ec:IsShown(), "kept outside a match")
    H.eq(ec.title.title, "ELIMINATED")
    ec.keep:Click()
    H.ok(not ec:IsShown(), "closed")
    connect(M)
    fight(M)
    M.Advance(0.3)
    H.eq(Hud.Preview("end"), false, "not during a match")
end)
