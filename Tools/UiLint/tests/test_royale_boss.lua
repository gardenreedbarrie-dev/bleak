-- Bleakhold Royale's storm beast in the addon (section 17 ROYV B A K F, ROYO X H, ROYK cause B; the realm's
-- Boss.Enable): the banners and their sounds (A BEAST STIRS with the place, THUNDERMAW AWAKENS, SLAIN with the top
-- damage dealer, FLEES and why), the island map's marker (the den's green beam and the time until it wakes, then the
-- beast in its ring with its health; the hoard), the legend's Boss entry once it has been announced, the minimap's
-- icons and edge pins (beside the safe-zone arrow, never under it), the kill feed's claw and the beast's name, the
-- bar's tab pointing at the beam, the winner's banner, reduced motion, and the texel ratio of the new art.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local ROYALE_ART = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\"
local MAP = {
    { 901, -1066, 533, -1066, 533, 455, 455, 32, 750, -267, -267 }, { 1, "L", -266, -266, 88, "The Bleak Hold" },
    { 2, "L", 120, 80, 62, "Harrow Farm" }, { 3, "L", 30, -420, 50, "Heron Rise" },
}
local DEN = { 30, -420 }

local function near(a, b, eps, msg)
    if type(a) ~= "number" or math.abs(a - b) > (eps or 1e-6) then
        error((msg or "values differ") .. ": expected " .. tostring(b) .. ", got " .. tostring(a), 2)
    end
end

local function connect(M)
    FX.connect(M, H, { [6] = 4096 })
    H.send(M, "ROYM", MAP)
end

-- A ROYS of match `id` (7001 unless over[1] says otherwise): the fight, alive, circle 2 holding round -150,-310 (520
-- yd), the next circle 300 yd round -110,-330, the player at -450,-310 inside both.
local function roys(M, over)
    local r = { 7001, 3, 0, 14, 24, 2, 2, "", "", "", 2, -150, -310, 520, -110, -330, 300, 100000, 140000, 20, "",
        -450, -310, 6, "", "", "" }
    for k, v in pairs(over or {}) do r[k] = v end
    H.send(M, "ROYS", { r })
end

-- The player's own position on the island (the client's map position and the server's myX/myY agree).
local function standAt(M, ns, x, y, over)
    local l, r, t, b = ns.Royale.WorldMapBounds(ns.S.royaleMap)
    M.mapInfo = "BleakholdRoyale"
    M.env.GetPlayerMapPosition = function() return (l - y) / (l - r), (t - x) / (t - b) end
    local o = { [22] = math.floor(x + 0.5), [23] = math.floor(y + 0.5) }
    for k, v in pairs(over or {}) do o[k] = v end
    roys(M, o)
    M.Advance(0.2)
end

local function played(M, name)
    local n = 0
    for _, s in ipairs(M.sounds) do
        if s == name then n = n + 1 end
    end
    return n
end

local function bannerNow(ns)
    local H_ = ns.RoyaleHud
    return H_.current and H_.current.title, H_.banner.line:GetText()
end

-- Advances until the banner on show is `title` (a banner shows for 2.9 s; at most 12 s).
local function waitBanner(M, ns, title)
    for _ = 1, 120 do
        if (bannerNow(ns)) == title then
            return true
        end
        M.Advance(0.1)
    end
    return false
end

local function legendShows(ns, key)
    for _, item in ipairs(ns.RoyaleMap.frame.legend.items) do
        if item.e.key == key then
            return item.tex:IsShown() and item.label:IsShown()
        end
    end
end

local function tooltipLines(M)
    return table.concat(M.env.GameTooltip.__lines or {}, "\n")
end

------------------------------------------------------------------------------------------------------
-- Banners
------------------------------------------------------------------------------------------------------
test("royale boss: B queues A BEAST STIRS with the place and TrexPreAggro; A awakens with TrexAggro", function(M, ns)
    connect(M)
    roys(M)
    H.send(M, "ROYV", { { "B", 0, DEN[1], DEN[2], 30000, "Heron Rise" } })
    local title, line = bannerNow(ns)
    H.eq(title, "A BEAST STIRS")
    H.eq(line, "Thundermaw stirs at Heron Rise! It wakes in 0:30.")
    H.eq(ns.RoyaleHud.current.color, "beast")
    H.eq(ns.RoyaleHud.current.icon, "beast")
    H.eq(played(M, "TrexPreAggro"), 1)
    H.eq(ns.RoyaleHud.banner.title.title, "A BEAST STIRS")
    -- a waiting banner reads its clock when it shows
    H.send(M, "ROYV", { { "A", 0, DEN[1], DEN[2], "", "" } })
    H.eq(played(M, "TrexAggro"), 0, "A waits for B's banner")
    H.ok(waitBanner(M, ns, "THUNDERMAW AWAKENS"))
    H.eq(select(2, bannerNow(ns)), "Slay it and claim its hoard.")
    H.eq(played(M, "TrexAggro"), 1)
    -- no place sent (the wilds): the map's nearest place, else the wilds
    M.Advance(3)
    H.send(M, "ROYV", { { "B", 0, 500, 500, 12000, "" } })
    H.ok(waitBanner(M, ns, "A BEAST STIRS"))
    H.contains(select(2, bannerNow(ns)), "stirs at the wilds! It wakes in 0:")
    -- a place is never markup
    M.Advance(3)
    H.send(M, "ROYV", { { "B", 0, DEN[1], DEN[2], 30000, "|cffff0000Red|r" } })
    H.ok(waitBanner(M, ns, "A BEAST STIRS"))
    H.contains(select(2, bannerNow(ns)), "||cffff0000Red||r", "the place is escaped")
end)

test("royale boss: K names who struck hardest (You for the player), then the cheer; F says why it fled",
function(M, ns)
    connect(M)
    roys(M)
    H.send(M, "ROYK", { { "Aldric", 1, "Brenna", 8, "P", 13, 3, "" } })
    H.send(M, "ROYV", { { "K", 0, DEN[1], DEN[2], "", "Aldric" } })
    H.ok(waitBanner(M, ns, "THUNDERMAW SLAIN"))
    H.eq(select(2, bannerNow(ns)), "|cff" .. ns.ClassColor(1) .. "Aldric|r struck hardest. The hoard lies open.")
    H.eq(ns.RoyaleHud.current.icon, "hoard")
    H.eq(played(M, "TrexDeath"), 1)
    H.eq(played(M, "AchievementSound"), 0, "the cheer follows")
    M.Advance(0.7)
    H.eq(played(M, "AchievementSound"), 1, "0.6 s later")
    M.Advance(10)
    H.send(M, "ROYV", { { "K", 0, DEN[1], DEN[2], "", "Tester" } })
    H.ok(waitBanner(M, ns, "THUNDERMAW SLAIN"))
    H.eq(select(2, bannerNow(ns)), "You struck hardest. The hoard lies open.")
    M.Advance(3)
    -- the storm reached the den, or overtime
    H.send(M, "ROYV", { { "F", 0, DEN[1], DEN[2], "", "" } })
    H.ok(waitBanner(M, ns, "THUNDERMAW FLEES"))
    H.eq(select(2, bannerNow(ns)), "The storm drove it off.")
    H.eq(ns.RoyaleHud.current.color, "ash")
    M.Advance(3)
    -- the last few players
    roys(M, { [4] = 3 })
    H.send(M, "ROYV", { { "F", 0, DEN[1], DEN[2], "", "" } })
    H.ok(waitBanner(M, ns, "THUNDERMAW FLEES"))
    H.eq(select(2, bannerNow(ns)), "It leaves the last few to each other.")
end)

test("royale boss: the winner's banner is VICTORY for the winner, WINNER and the name for everyone else",
function(M, ns)
    connect(M)
    roys(M)
    H.send(M, "ROYK", { { "Aldric", 1, "Brenna", 8, "P", 2, 5, "" } })
    H.send(M, "ROYV", { { "W", 5, "", "", "", "Aldric" } })
    H.ok(waitBanner(M, ns, "WINNER"))
    H.eq(select(2, bannerNow(ns)), "|cff" .. ns.ClassColor(1) .. "Aldric|r · 5 kills")
    M.Advance(4)
    H.send(M, "ROYV", { { "W", 7, "", "", "", "Tester" } })
    H.ok(waitBanner(M, ns, "VICTORY"))
    H.eq(select(2, bannerNow(ns)), "Last one standing · 7 kills")
    H.eq(ns.RoyaleHud.current.color, "gold")
end)

------------------------------------------------------------------------------------------------------
-- The island map and the legend
------------------------------------------------------------------------------------------------------
test("royale boss: ROYO X puts the beam and the time on the map, then the beast with its health; gone: off",
function(M, ns)
    connect(M)
    roys(M)
    local MP, RS = ns.RoyaleMap, ns.RoyaleStyle
    MP.Open(false)
    M.Advance(0.1)
    local b = MP.bossMarker
    H.ok(not b:IsShown(), "no beast yet")
    -- stirring: the beam over the den, the time until it wakes, no health bar
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 0, DEN[1], DEN[2], 3, 24000 } })
    M.Advance(0.1)
    H.ok(b:IsShown(), "the den is marked")
    local _, rel, _, x, y = b:GetPoint(1)
    local px, py = MP.ToMap(DEN[1], DEN[2])
    H.eq(rel, MP.canvas)
    near(x, px, 1e-6); near(y, -py, 1e-6)
    H.ok(b.beam:IsShown() and b.core:IsShown() and b.shadow:IsShown(), "the beam stands")
    H.ok(b.icon:IsShown() and b.icon.rsIcon == "beast", "the horned skull")
    H.ok(b.timer:IsShown(), "its time")
    H.eq(b.timer:GetText(), "0:24")
    H.ok(b.ping:IsShown(), "a ring spreads at the beam's foot")
    H.ok(not b.hpBack:IsShown() and not b.hpFill:IsShown(), "no health while it sleeps")
    M.Advance(2)
    H.eq(b.timer:GetText(), "0:22", "the time counts down")
    -- its tooltip: the name, the line, the beam, the time
    b:GetScript("OnEnter")(b)
    local tip = tooltipLines(M)
    H.contains(tip, "Thundermaw")
    H.contains(tip, "A storm-touched devilsaur. Its hoard is anyone's.")
    H.contains(tip, "A green beam marks its den.")
    H.contains(tip, "Wakes in 0:22")
    b:GetScript("OnLeave")(b)
    -- awake, hurt: the ring, 57 % of the bar, no beam, no time
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 57, DEN[1] + 22, DEN[2] - 14, 1 } })
    M.Advance(0.1)
    H.ok(b:IsShown())
    local _, _, _, x2 = b:GetPoint(1)
    near(x2, (MP.ToMap(DEN[1] + 22, DEN[2] - 14)), 1e-6, "it moved")
    H.ok(not b.beam:IsShown() and not b.core:IsShown() and not b.ping:IsShown(), "the beam is gone")
    H.ok(not b.timer:IsShown(), "no time")
    H.ok(b.ring:IsShown() and b.outline:IsShown(), "its ring")
    H.ok(b.pulse ~= nil, "the ring breathes (an animation group)")
    H.ok(b.hpBack:IsShown() and b.hpTrack:IsShown() and b.hpFill:IsShown(), "its health")
    local track = b.hpTrack:GetWidth()
    near(track, RS.Snap(MP.BOSS.barW, MP.canvas), 1e-6, "on whole pixels")
    near(b.hpTrack:GetHeight(), RS.Snap(MP.BOSS.barH, MP.canvas), 1e-6)
    near(b.hpFill:GetWidth(), RS.Snap(track * 0.57, MP.canvas), 1e-6, "57 % of the bar")
    b:GetScript("OnEnter")(b)
    H.contains(tooltipLines(M), "Awake · 57% health")
    b:GetScript("OnLeave")(b)
    -- the realm clamps the health; the client too (an older realm, garbage)
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 400, DEN[1] + 22, DEN[2] - 14, 1 } })
    M.Advance(0.1)
    near(b.hpFill:GetWidth(), track, 1e-6, "full")
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 0, DEN[1] + 22, DEN[2] - 14, 1 } })
    M.Advance(0.1)
    H.ok(not b.hpFill:IsShown() and b.hpTrack:IsShown(), "an empty bar")
    -- slain or fled: off the map
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 0, DEN[1] + 22, DEN[2] - 14, 0 } })
    M.Advance(0.1)
    H.ok(not b:IsShown(), "gone")
    for i = 1, MP.objects.used do
        H.ok(MP.objects.items[i].obj.kind ~= "X", "never drawn as an orb")
    end
end)

test("royale boss: the hoard is a gold-pinged chest until opened (then dimmed), gone unopened it leaves the map",
function(M, ns)
    connect(M)
    roys(M)
    local MP = ns.RoyaleMap
    MP.Open(false)
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 0, DEN[1], DEN[2], 0 }, { 9002, "H", 0, DEN[1], DEN[2], 1 } })
    M.Advance(0.1)
    local function hoard()
        for i = 1, MP.objects.used do
            local f = MP.objects.items[i]
            if f.obj.kind == "H" then
                return f
            end
        end
    end
    local f = hoard()
    H.ok(f, "the hoard is on the map")
    H.eq(f.icon.rsIcon, "hoard")
    H.ok(f.ping:IsShown(), "pinged while it waits")
    H.ok(not f.timer:IsShown(), "no time")
    f:GetScript("OnEnter")(f)
    local tip = tooltipLines(M)
    H.contains(tip, "Thundermaw's Hoard")
    H.contains(tip, "Rare loot. Opening it takes a few seconds; damage stops you.")
    H.contains(tip, "Ready to open")
    f:GetScript("OnLeave")(f)
    H.send(M, "ROYO", { { 7001, 0 }, { 9002, "H", 0, DEN[1], DEN[2], 4 } })
    M.Advance(0.1)
    f = hoard()
    H.ok(f and not f.ping:IsShown(), "opened: no ping")
    near(f:GetAlpha(), 0.6, 1e-6, "dimmed")
    f:GetScript("OnEnter")(f)
    H.contains(tooltipLines(M), "Opened")
    f:GetScript("OnLeave")(f)
    H.send(M, "ROYO", { { 7001, 0 }, { 9002, "H", 0, DEN[1], DEN[2], 0 } })
    M.Advance(0.1)
    H.eq(hoard(), nil, "gone unopened: off the map")
end)

test("royale boss: the legend shows Boss only once the beast is announced, until the next match", function(M, ns)
    connect(M)
    roys(M)
    local MP = ns.RoyaleMap
    MP.Open(false)
    M.Advance(0.1)
    H.ok(not legendShows(ns, "boss"), "no Boss before B")
    H.ok(legendShows(ns, "supply"), "the others show")
    H.send(M, "ROYV", { { "B", 0, DEN[1], DEN[2], 30000, "Heron Rise" } })
    H.ok(legendShows(ns, "boss"), "B: Boss in the legend")
    -- the entries stay inside the footer, centred
    local first, last
    for _, item in ipairs(MP.frame.legend.items) do
        if item.tex:IsShown() then
            local _, _, _, x = item.tex:GetPoint(1)
            first = first or x
            local _, _, _, lx = item.label:GetPoint(1)
            last = lx + item.label:GetStringWidth()
        end
    end
    H.ok(first > 0 and last < MP.SIZE, "the legend fits: " .. first .. " .. " .. last)
    -- a new match forgets it
    roys(M, { [1] = 7002 })
    H.ok(not legendShows(ns, "boss"), "a new match: no Boss")
    -- after a /reload the event is gone, but ROYO still has the beast (or its hoard)
    H.send(M, "ROYO", { { 7002, 1 }, { 9001, "X", 0, DEN[1], DEN[2], 3, 20000 } })
    M.Advance(0.1)
    H.ok(legendShows(ns, "boss"), "ROYO X: Boss in the legend")
    roys(M, { [1] = 7003 })
    H.send(M, "ROYO", { { 7003, 1 }, { 9002, "H", 0, DEN[1], DEN[2], 1 } })
    M.Advance(0.1)
    H.ok(legendShows(ns, "boss"), "ROYO H: Boss in the legend")
end)

test("royale boss: with reduced motion the beam's ring stands still and the beast's ring does not breathe",
function(M, ns)
    connect(M)
    roys(M)
    local MP, RS = ns.RoyaleMap, ns.RoyaleStyle
    RS.SetMotion(false)
    MP.Open(false)
    local b = MP.bossMarker
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 0, DEN[1], DEN[2], 3, 24000 } })
    M.Advance(0.1)
    local w = b.ping:GetWidth()
    near(w, (MP.BOSS.pingFrom + MP.BOSS.pingTo) / 2, 1e-6, "half way out")
    M.Advance(0.37)
    near(b.ping:GetWidth(), w, 1e-6, "and stays")
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 80, DEN[1], DEN[2], 1 } })
    M.Advance(0.1)
    H.ok(not (b.pulse and b.pulse:IsPlaying()), "no breathing")
    near(b.ring:GetAlpha(), MP.BOSS.still, 1e-6, "a steady ring")
end)

------------------------------------------------------------------------------------------------------
-- The minimap
------------------------------------------------------------------------------------------------------
local function minimapIcon(ns, kind)
    for _, e in ipairs(ns.RoyaleMinimap.icons) do
        if e.icon:IsShown() and e.obj and e.obj.kind == kind then
            return e
        end
    end
end

test("royale boss: ROYO X shows the minimap icon (on its glow) and pins it to the edge; gone: off", function(M, ns)
    connect(M)
    standAt(M, ns, DEN[1] - 40, DEN[2] + 55)
    local RM = ns.RoyaleMinimap
    -- stirring, in view
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 0, DEN[1], DEN[2], 3, 24000 } })
    M.Advance(0.2)
    local e = minimapIcon(ns, "X")
    H.ok(e, "the beast on the minimap")
    H.eq(e.icon.rsIcon, "beast")
    H.ok(not e.pinned and not e.tick:IsShown(), "in view")
    H.ok(e.glow:IsShown(), "on a glow")
    H.eq(e.glow.rsArt, "GemGlow")
    local _, _, _, a = e.glow:GetVertexColor()
    near(a, 0.75, 1e-6, "brighter while it stirs")
    near(e.icon:GetAlpha(), 0.85, 1e-6)
    -- awake, far away: pinned to the edge with a beast-green tick
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 64, DEN[1] + 600, DEN[2] - 400, 1 } })
    M.Advance(0.2)
    e = minimapIcon(ns, "X")
    H.ok(e and e.pinned and e.tick:IsShown(), "pinned")
    local r, g, bl = e.tick:GetVertexColor()
    near(r, 0x8F / 255, 0.01); near(g, 0xD1 / 255, 0.01); near(bl, 0x4F / 255, 0.01)
    -- the hoard: a gold chest, no glow
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 0, DEN[1] + 600, DEN[2] - 400, 0 },
        { 9002, "H", 0, DEN[1], DEN[2], 1 } })
    M.Advance(0.2)
    H.eq(minimapIcon(ns, "X"), nil, "the beast is gone")
    local h = minimapIcon(ns, "H")
    H.ok(h and h.icon.rsIcon == "hoard", "its hoard")
    H.ok(not h.glow:IsShown(), "no glow for the hoard")
    H.send(M, "ROYO", { { 7001, 0 }, { 9002, "H", 0, DEN[1], DEN[2], 4 } })
    M.Advance(0.2)
    H.eq(minimapIcon(ns, "H"), nil, "opened: nothing to travel for")
    local shown = 0
    for _, x in ipairs(RM.icons) do
        if x.glow:IsShown() then shown = shown + 1 end
    end
    H.eq(shown, 0, "no glow left behind")
end)

test("royale boss: a pin the safe-zone arrow would cover slides beside its socket, its tick still on the beast",
function(M, ns)
    connect(M)
    local RM = ns.RoyaleMinimap
    -- inside the next circle (-110,-330 r 300): the dimmed arrow points north at its centre; the beast far north
    -- on the same line
    standAt(M, ns, -380, -330)
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 50, 400, -330, 1 } })
    M.Advance(0.2)
    local ea = RM.arrow
    H.ok(ea:IsShown(), "the arrow shows")
    local e = minimapIcon(ns, "X")
    H.ok(e and e.pinned, "the beast is pinned")
    local _, _, _, ax, ay = ea:GetPoint(1)
    local _, _, _, ix, iy = e.icon:GetPoint(1)
    local socket = ea.socket:GetWidth()
    local d = math.sqrt((ix - ax) ^ 2 + (iy - ay) ^ 2)
    H.ok(d >= socket / 2 + e.icon:GetWidth() / 2, ("clear of the socket: %.1f"):format(d))
    H.ok(iy > 0, "still at the top")
    -- the tick points at the beast (north), whatever its spot
    local angle = e.tick.rsAngle
    near(math.cos(angle + math.pi / 2), 0, 1e-6)
    near(math.sin(angle + math.pi / 2), 1, 1e-6)
    -- elsewhere on the rim a pin keeps its own spot
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 50, -380, 400, 1 } })
    M.Advance(0.2)
    e = minimapIcon(ns, "X")
    local _, _, _, jx, jy = e.icon:GetPoint(1)
    H.ok(jx < 0 and math.abs(jy) < 1e-6, "due west, where it is")
end)

------------------------------------------------------------------------------------------------------
-- The kill feed and the bar's tab
------------------------------------------------------------------------------------------------------
test("royale boss: ROYK cause B shows the claw and Thundermaw in beast green; a credited player keeps their colour",
function(M, ns)
    connect(M)
    roys(M)
    local feed = ns.RoyaleHud.feed
    H.send(M, "ROYK", { { "Thundermaw", 0, "Dalia", 11, "B", 13 } })
    M.Advance(0.3)
    H.eq(feed.lines[1].killer:GetText(), "|cff8FD14FThundermaw|r")
    H.eq(feed.lines[1].icon.rsIcon, "claw")
    H.ok(not feed.lines[1].mine, "not the player's")
    -- a player credited for it
    H.send(M, "ROYK", { { "Aldric", 1, "Brenna", 8, "B", 12, 4 } })
    M.Advance(0.3)
    H.eq(feed.lines[1].killer:GetText(), "|cff" .. ns.ClassColor(1) .. "Aldric|r")
    H.eq(feed.lines[1].icon.rsIcon, "claw")
    -- a player who happens to be called Thundermaw is a player
    H.send(M, "ROYK", { { "Thundermaw", 4, "Corin", 9, "B", 11, 1 } })
    M.Advance(0.3)
    H.eq(feed.lines[1].killer:GetText(), "|cff" .. ns.ClassColor(4) .. "Thundermaw|r")
    -- the beast's kill of the player is the player's own line
    H.send(M, "ROYK", { { "Thundermaw", 0, "Tester", 1, "B", 10 } })
    M.Advance(0.3)
    H.ok(feed.lines[1].mine and feed.lines[1].mark:IsShown(), "own line")
end)

test("royale boss: while the beast stirs the tab points at its green beam; the storm and awake take it back",
function(M, ns)
    connect(M)
    roys(M)
    local Hud = ns.RoyaleHud
    local bar = Hud.bar
    H.send(M, "ROYV", { { "B", 0, DEN[1], DEN[2], 30000, "Heron Rise" } })
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 0, DEN[1], DEN[2], 3, 30000 } })
    M.Advance(0.5)
    local _, tab = Hud.BarCells(ns.S.royale)
    H.ok(tab, "a tab line")
    H.eq(tab.text, "Follow the |cff8FD14Fgreen beam|r to Heron Rise.")
    H.eq(tab.icon, "beast")
    H.eq(bar.sub:GetText(), tab.text)
    -- without the place (the event lost to a /reload): the place the den lies in
    Hud.beastPlace = nil
    local _, again = Hud.BarCells(ns.S.royale)
    H.eq(again.text, "Follow the |cff8FD14Fgreen beam|r to Heron Rise.")
    -- in the wilds
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 0, 500, 500, 3, 20000 } })
    local _, wild = Hud.BarCells(ns.S.royale)
    H.eq(wild.text, "Follow the |cff8FD14Fgreen beam|r to its den.")
    -- the storm's damage comes first
    Hud.outside = true
    local _, storm = Hud.BarCells(ns.S.royale)
    H.eq(storm.icon, "storm")
    Hud.outside = nil
    -- a spectator is told nothing
    roys(M, { [6] = 3 })
    local _, spec = Hud.BarCells(ns.S.royale)
    H.eq(spec, nil)
    -- awake: the banner said it, the map shows it
    roys(M)
    H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 100, DEN[1], DEN[2], 1 } })
    local _, awake = Hud.BarCells(ns.S.royale)
    H.eq(awake, nil)
end)

------------------------------------------------------------------------------------------------------
-- Texel ratio
------------------------------------------------------------------------------------------------------
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

for _, screen in ipairs({ { 1920, 1080, 1 }, { 2560, 1440, 1 }, { 1920, 1080, 0.64 } }) do
    test(("royale boss: no beast art minified past 2.2x at %dx%d, UI scale %.2f"):format(screen[1], screen[2],
        screen[3]), function(M, ns)
        M.SetScreen(screen[1], screen[2], screen[3])
        connect(M)
        local RS, MP, RM = ns.RoyaleStyle, ns.RoyaleMap, ns.RoyaleMinimap
        local worst, what, measured = 0, "", 0
        -- the beast's marker and the hoard on the map, the icons, glows and ticks on the minimap
        local function beastArt(o)
            local b = MP.bossMarker
            local f = o:GetParent()
            if f == b or f == b.token or f == b.fg then
                return true
            end
            if f and f.obj and f.obj.kind == "H" then
                return true
            end
            for _, e in ipairs(RM.icons) do
                if e.obj and (e.obj.kind == "X" or e.obj.kind == "H") and (o == e.icon or o == e.glow or o == e.tick) then
                    return true
                end
            end
            return false
        end
        local function measure(root)
            for _, o in ipairs(M.objects) do
                if o.__otype == "Texture" and type(o.rsPath) == "string" and o.rsPath:find(ROYALE_ART, 1, true) == 1
                    and o:IsVisible() and o:GetHeight() > 0 and RS.RootOf(o) == root and beastArt(o) then
                    local w, h = fileDims(o.rsPath)
                    local ulx, uly, llx, lly = o:GetTexCoord()
                    local texels = math.sqrt(((llx - ulx) * w) ^ 2 + ((lly - uly) * h) ^ 2)
                    local ratio = texels / (o:GetHeight() * RS.PxPerUnit(o))
                    measured = measured + 1
                    if ratio > worst then worst, what = ratio, (o.rsArt or o.rsPath) .. " " .. o:GetHeight() end
                end
            end
        end
        standAt(M, ns, DEN[1] - 40, DEN[2] + 55)
        MP.Open(false)
        H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 0, DEN[1], DEN[2], 3, 24000 } })
        for _ = 1, 14 do
            M.Advance(0.1)        -- the spreading ring through its sizes
            measure(MP.frame)
            measure(RM.layer)
        end
        H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 40, DEN[1], DEN[2], 1 }, { 9002, "H", 0, DEN[1], DEN[2] + 30, 1 } })
        for _ = 1, 14 do
            M.Advance(0.1)
            measure(MP.frame)
            measure(RM.layer)
        end
        H.send(M, "ROYO", { { 7001, 0 }, { 9001, "X", 40, DEN[1] + 900, DEN[2], 1 } })
        M.Advance(0.2)
        measure(RM.layer)
        H.ok(measured > 40, "art was measured: " .. measured)
        H.ok(worst <= 2.2, ("texel ratio %.2f (%s)"):format(worst, what))
    end)
end
