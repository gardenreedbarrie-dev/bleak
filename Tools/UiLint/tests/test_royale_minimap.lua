-- Bleakhold Royale on the minimap (RoyaleMinimap.lua): the projection on a round and a square minimap, north up and
-- turning with the player; the view radius from Bleakhold.exe or the zoom tables with IsIndoors() deciding; the
-- storm dots of an old Bleakhold.exe only on the visible part of each circle and inside the shape (at most 120 for
-- an 860-yd circle at zoom 0, none without the client's own position, none while the exe draws the storm); the
-- safe-zone arrow on the shape's edge with "N yd inside"; supply drops, orbs and their pins on the edge; and the
-- layer's rules (a plain frame on the Minimap, rotation only on rotatable art, no art minified past 2.2x).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local MAP = {
    { 901, -1066, 533, -1066, 533, 455, 455, 32, 750, -267, -267 }, { 1, "L", -266, -266, 88, "The Bleak Hold" },
    { 2, "L", 120, 80, 62, "Harrow Farm" },
}
local CUR = { -267, -267, 860 }
local NEXT = { -150, -310, 520 }

local function near(a, b, eps, msg)
    if type(a) ~= "number" or math.abs(a - b) > (eps or 1e-6) then
        error((msg or "values differ") .. ": expected " .. tostring(b) .. ", got " .. tostring(a), 2)
    end
end

local function connect(M)
    FX.connect(M, H, { [6] = 4096 })
    H.send(M, "ROYM", MAP)
end

-- A ROYS of match 7001 (field index -> value): the fight, alive, circle 2 = CUR with NEXT shown, no shrink planned.
local function roys(M, over)
    local r = { 7001, 3, 0, 20, 24, 2, 0, "", "", "", 2, CUR[1], CUR[2], CUR[3], NEXT[1], NEXT[2], NEXT[3], "", "",
        20, "", "", "", 6, "", "", "" }
    for k, v in pairs(over or {}) do r[k] = v end
    H.send(M, "ROYS", { r })
end

-- The player at world x, y: the client's own map position (MapForge's WorldMapArea, as R.ClientPos reads it) and
-- the server's myX/myY agreeing, then a ROYS (`over`) and a moment for the layer.
local function at(M, ns, x, y, over)
    local l, r, t, b = ns.Royale.WorldMapBounds(ns.S.royaleMap)
    M.mapInfo = "BleakholdRoyale"
    M.env.GetPlayerMapPosition = function() return (l - y) / (l - r), (t - x) / (t - b) end
    local o = { [22] = math.floor(x + 0.5), [23] = math.floor(y + 0.5) }
    for k, v in pairs(over or {}) do o[k] = v end
    roys(M, o)
    M.Advance(0.2)
end

-- A point on the circle c at angle a (world radians from north towards west), `by` yards outside it.
local function onCircle(c, a, by)
    return c[1] + (c[3] + (by or 0)) * math.cos(a), c[2] + (c[3] + (by or 0)) * math.sin(a)
end

local function offsetOf(region)
    local _, _, _, x, y = region:GetPoint(1)
    return x, y
end

-- The storm dots shown: { x, y, r, g, b } each.
local function shownDots(ns)
    local out = {}
    for _, e in ipairs(ns.RoyaleMinimap.dots) do
        if e.dot:IsShown() then
            local x, y = offsetOf(e.dot)
            local r, g, b = e.dot:GetVertexColor()
            out[#out + 1] = { x = x, y = y, r = r, g = g, b = b }
        end
    end
    return out
end

local function shownIcons(ns)
    local out = {}
    for _, e in ipairs(ns.RoyaleMinimap.icons) do
        if e.icon:IsShown() then
            out[#out + 1] = e
        end
    end
    return out
end

local function isStorm(d) return math.abs(d.r - 0xA6 / 255) < 0.01 and math.abs(d.b - 0xE0 / 255) < 0.01 end
local function isWhite(d) return d.r > 0.99 and d.g > 0.99 and d.b > 0.99 end

------------------------------------------------------------------------------------------------------
-- The projection
------------------------------------------------------------------------------------------------------
test("royale minimap: RM.Project on a round and a square minimap, north up and turning with the player",
function(M, ns)
    local RM = ns.RoyaleMinimap
    local g = RM.Geometry()
    near(g.half, 70, 1e-9, "half the stock 140-unit minimap")
    H.eq(g.shape, "ROUND")
    near(g.view, 233.333, 0.001, "zoom 0 outdoors")
    H.eq(g.rotate, false)
    local x, y, inside = RM.Project(100, 0)
    near(x, 0, 1e-9); near(y, 30, 1e-3, "100 yd north: up")
    H.eq(inside, true)
    x, y = RM.Project(0, 100)
    near(x, -30, 1e-3, "100 yd west: left"); near(y, 0, 1e-9)
    -- the corner (60, 60): 84.9 units from the centre, off a round minimap, on a square one
    local cdx, cdy = 60 / g.k, -60 / g.k
    x, y, inside = RM.Project(cdx, cdy)
    near(x, 60, 1e-6); near(y, 60, 1e-6)
    H.eq(inside, false, "a corner is off the round minimap")
    M.env.GetMinimapShape = function() return "SQUARE" end
    g = RM.Geometry()
    H.eq(g.shape, "SQUARE")
    _, _, inside = RM.Project(cdx, cdy)
    H.eq(inside, true, "the corner is on the square minimap")
    _, _, inside = RM.Project(0, -75 / g.k)
    H.eq(inside, false, "past the square's edge")
    M.env.GetMinimapShape = function() return "CORNER-TOPRIGHT" end
    H.eq(RM.Geometry().shape, "ROUND", "LibDBIcon's other shapes hold the circle: round")
    M.env.GetMinimapShape = nil
    -- a scaled minimap (AddicatUI): the layer is its child, so units stay the minimap's
    M.env.Minimap:SetScale(1.25)
    near(RM.Geometry().half, 70, 1e-9)
    M.env.Minimap:SetScale(1)
    -- turning with the player (rotateMinimap 1): facing west puts west up and north right
    M.cvars.rotateMinimap = "1"
    M.env.GetPlayerFacing = function() return math.pi / 2 end
    g = RM.Geometry()
    H.eq(g.rotate, true)
    x, y = RM.Project(0, 100)
    near(x, 0, 1e-6); near(y, 30, 1e-3, "west up")
    x, y = RM.Project(100, 0)
    near(x, 30, 1e-3, "north right"); near(y, 0, 1e-6)
    -- any facing: the screen angle is pi/2 + bearing - facing (bearing from north towards west)
    for _, f in ipairs({ -2.5, -0.785, 0.3, 1.9, 3.1 }) do
        M.env.GetPlayerFacing = function() return f end
        g = RM.Geometry()
        for _, o in ipairs({ { 50, 20 }, { -80, 35 }, { 10, -120 } }) do
            x, y = RM.Project(o[1], o[2], g)
            local want = math.pi / 2 + math.atan2(o[2], o[1]) - f
            local diff = (math.atan2(y, x) - want) % (2 * math.pi)
            H.ok(diff < 1e-6 or diff > 2 * math.pi - 1e-6, "angle for facing " .. f)
            near(math.sqrt(x * x + y * y), math.sqrt(o[1] ^ 2 + o[2] ^ 2) * g.k, 1e-6, "length kept")
        end
    end
    -- north up again without the CVar, whatever the facing
    M.cvars.rotateMinimap = "0"
    x, y = RM.Project(100, 0)
    near(x, 0, 1e-9); near(y, 30, 1e-3)
    -- the edge point of a direction: on the circle, or on the square like the orbs (Orbs.Offset)
    g = RM.Geometry()
    x, y = RM.EdgePoint(1, 1, 10, g)
    near(x, 60 / math.sqrt(2), 1e-6); near(y, 60 / math.sqrt(2), 1e-6)
    M.env.GetMinimapShape = function() return "SQUARE" end
    x, y = RM.EdgePoint(1, 1, 10, RM.Geometry())
    near(x, 60, 1e-6); near(y, 60, 1e-6)
    x, y = RM.EdgePoint(3, 1, 10, RM.Geometry())
    near(x, 60, 1e-6); near(y, 20, 1e-6)
end)

test("royale minimap: the view radius is Bleakhold.exe's, else the zoom table IsIndoors() picks", function(M, ns)
    local RM = ns.RoyaleMinimap
    local zoom = 2
    M.env.Minimap.GetZoom = function() return zoom end
    near(RM.ViewRadius(), 166.667, 0.001, "outdoors, zoom 2")
    for z = 0, 5 do
        zoom = z
        near(RM.ViewRadius(), ({ 233.333, 200, 166.667, 133.333, 100, 66.667 })[z + 1], 0.001, "outdoor zoom " .. z)
        M.indoors = true
        near(RM.ViewRadius(), ({ 150, 120, 90, 60, 40, 25 })[z + 1], 1e-9, "indoor zoom " .. z)
        M.indoors = false
    end
    -- the zoom CVars equal (Astrolabe's comparison cannot tell): IsIndoors decides
    zoom = 2
    M.cvars.minimapZoom, M.cvars.minimapInsideZoom = "2", "2"
    M.indoors = true
    near(RM.ViewRadius(), 90, 1e-9, "indoors")
    M.indoors = false
    near(RM.ViewRadius(), 166.667, 0.001, "outdoors")
    -- a zoom out of range is clamped; no answer is zoom 0
    zoom = 9
    near(RM.ViewRadius(), 66.667, 0.001)
    M.env.Minimap.GetZoom = function() end
    near(RM.ViewRadius(), 233.333, 0.001)
    -- Bleakhold.exe answers for both tables
    M.env.BleakholdStorm_MinimapViewRadius = function() return 123.5 end
    M.indoors = true
    near(RM.ViewRadius(), 123.5, 1e-9, "the exe's")
    near(RM.Geometry().k, 70 / 123.5, 1e-9)
    M.env.BleakholdStorm_MinimapViewRadius = function() end
    near(RM.ViewRadius(), 150, 1e-9, "no answer: the tables")
end)

------------------------------------------------------------------------------------------------------
-- The storm dots (an old Bleakhold.exe)
------------------------------------------------------------------------------------------------------
test("royale minimap: an old exe's storm dots lie on the circles' visible part, inside the shape, at most 120",
function(M, ns)
    connect(M)
    local RM = ns.RoyaleMinimap
    -- on the edge of the 860-yd circle, zoom 0 (233 yd): about 2 x 67 units of it are on the minimap; the next
    -- circle (110 yd) 40 yd further in
    local a = 0.6
    local px, py = onCircle(CUR, a, 5)
    local nx, ny = math.floor(px - 150 * math.cos(a) + 0.5), math.floor(py - 150 * math.sin(a) + 0.5)
    at(M, ns, px, py, { [15] = nx, [16] = ny, [17] = 110 })
    H.ok(RM.layer:IsShown(), "the layer is up")
    local g = RM.Geometry()
    local dots = shownDots(ns)
    H.ok(#dots >= 10 and #dots <= RM.DOT_MAX, "dots on the visible arc: " .. #dots)
    local ccx, ccy = RM.Project(CUR[1] - px, CUR[2] - py, g)
    local ncx, ncy = RM.Project(nx - px, ny - py, g)
    local NEXT = { nx, ny, 110 }
    local storm, white = {}, {}
    for _, d in ipairs(dots) do
        H.ok(d.x * d.x + d.y * d.y <= (g.half - 2.5) ^ 2 + 1e-6, "inside the round minimap")
        local onCur = math.abs(math.sqrt((d.x - ccx) ^ 2 + (d.y - ccy) ^ 2) - CUR[3] * g.k) < 1e-6
        local onNext = math.abs(math.sqrt((d.x - ncx) ^ 2 + (d.y - ncy) ^ 2) - NEXT[3] * g.k) < 1e-6
        H.ok(onCur or onNext, "on a circle")
        if onCur then
            H.ok(isStorm(d), "the storm's edge in storm violet")
            storm[#storm + 1] = d
        else
            H.ok(isWhite(d), "the next circle white")
            white[#white + 1] = d
        end
    end
    -- the whole visible arc is dotted every 7 units, and nothing else of the circle
    local from, to = RM.ArcInDisc(ccx, ccy, CUR[3] * g.k, g.half - 2.5)
    local len = CUR[3] * g.k * (to - from)
    H.ok(#storm >= math.floor(len / RM.DOT_GAP) and #storm <= math.floor(len / RM.DOT_GAP) + 1,
        "one dot every 7 units of the " .. math.floor(len) .. "-unit arc: " .. #storm)
    -- the next circle (in view here too) is dashed: every other dot, so 14 units apart
    H.ok(#white >= 2, "next circle dots: " .. #white)
    for i = 1, #white do
        local best = math.huge
        for j = 1, #white do
            if i ~= j then
                best = math.min(best, math.sqrt((white[i].x - white[j].x) ^ 2 + (white[i].y - white[j].y) ^ 2))
            end
        end
        H.ok(best > 13.5, "dashed: " .. best)
    end
    -- the dots stay at their world angles while the player walks along the edge
    local first = { x = storm[1].x, y = storm[1].y }
    at(M, ns, px + 0.0001, py, { [15] = nx, [16] = ny, [17] = 110 })
    near(shownDots(ns)[1].x, first.x, 1e-3, "no crawl")
    -- deep inside the circle at the closest zoom no part of it is on the minimap
    M.env.Minimap.GetZoom = function() return 5 end
    at(M, ns, CUR[1], CUR[2], { [15] = "", [16] = "", [17] = "" })
    H.eq(#shownDots(ns), 0, "no dots off screen")
end)

test("royale minimap: the dots reach the square's corners, and never leave the square", function(M, ns)
    connect(M)
    local RM = ns.RoyaleMinimap
    -- an edge running diagonally across the minimap
    local px, py = onCircle(CUR, 3 * math.pi / 4, 0)
    at(M, ns, px, py, { [15] = "", [16] = "", [17] = "" })
    local round = #shownDots(ns)
    M.env.GetMinimapShape = function() return "SQUARE" end
    M.Advance(0.2)
    local dots = shownDots(ns)
    H.ok(#dots > round, "more of the edge on a square minimap: " .. #dots .. " > " .. round)
    local corner = false
    for _, d in ipairs(dots) do
        H.ok(math.max(math.abs(d.x), math.abs(d.y)) <= 70 - 2.5 + 1e-6, "inside the square")
        corner = corner or d.x * d.x + d.y * d.y > 70 * 70
    end
    H.ok(corner, "a dot in a corner, off the circle")
end)

test("royale minimap: no dots without the client's own position, while the exe draws the storm, or switched off",
function(M, ns)
    connect(M)
    local RM = ns.RoyaleMinimap
    local px, py = onCircle(CUR, 0.6, 5)
    at(M, ns, px, py)
    H.ok(#shownDots(ns) > 0, "dots")
    -- no client position: the server's myX/myY can be 5 s old
    M.env.GetPlayerMapPosition = function() return nil end
    M.Advance(0.2)
    H.eq(#shownDots(ns), 0, "none on the server's position")
    at(M, ns, px, py)
    H.ok(#shownDots(ns) > 0)
    -- Bleakhold.exe draws the storm itself
    M.env.BleakholdStorm_MinimapViewRadius = function() return 233.333 end
    M.cvars.bleakStormMinimap = "1"
    M.Advance(0.2)
    H.eq(#shownDots(ns), 0, "the exe draws it")
    H.eq(RM.StatusText(), RM.TEXT.native)
    M.cvars.bleakStormMinimap = "0"
    M.Advance(0.2)
    H.ok(#shownDots(ns) > 0, "its overlay off: the dots")
    H.eq(RM.StatusText(), RM.TEXT.dots)
    -- /bh royale minimap off: both
    RM.Command("off")
    M.Advance(0.2)
    H.eq(#shownDots(ns), 0, "off")
    H.eq(M.cvars.bleakStormMinimap, "0")
    H.eq(ns.db.options.royaleMinimap, false)
    H.eq(RM.StatusText(), RM.TEXT.off)
    H.contains(M.chat[#M.chat].msg, "off")
    RM.Command("on")
    M.Advance(0.2)
    H.eq(M.cvars.bleakStormMinimap, "1", "the exe's back on")
    H.eq(#shownDots(ns), 0, "and it draws the storm")
    -- a stock client: the option alone
    M.env.BleakholdStorm_MinimapViewRadius = nil
    M.cvars.bleakStormMinimap = nil
    RM.SetEnabled(false)
    M.Advance(0.2)
    H.eq(#shownDots(ns), 0)
    RM.SetEnabled(true)
    M.Advance(0.2)
    H.ok(#shownDots(ns) > 0)
    -- the lobby before circle 1 has no circle; after its reveal the lobby shows both
    at(M, ns, 455, 455, { [2] = 0, [6] = 0, [11] = 0, [14] = 860, [15] = "", [16] = "", [17] = "" })
    H.eq(#shownDots(ns), 0, "phase 0: no circle yet")
    -- a spectator: nothing at all (the minimap follows the camera target)
    at(M, ns, px, py, { [6] = 3 })
    H.eq(#shownDots(ns), 0)
    H.ok(not RM.layer:IsShown(), "the layer sleeps")
end)

------------------------------------------------------------------------------------------------------
-- The safe-zone arrow
------------------------------------------------------------------------------------------------------
test("royale minimap: the safe arrow sits on the shape's edge, storm violet in the storm; inside it says N yd inside",
function(M, ns)
    connect(M)
    local RM = ns.RoyaleMinimap
    local ea = M.env.BleakholdRoyaleSafeArrow
    H.eq(ea, RM.arrow)
    -- the next circle's centre 100 yd north-east (north and east: up and right)
    local next = { [15] = -100, [16] = -300, [17] = 50 }
    at(M, ns, -200, -200, next)
    H.ok(ea:IsShown(), "the arrow")
    H.eq(ea.dist:GetText(), math.ceil(math.sqrt(2) * 100 - 50) .. " yd")
    local inset = RM.ARROW * RM.SOCKET / 2 + RM.RIM_GAP      -- the socket just inside the rim
    local x, y = offsetOf(ea)
    near(x, (70 - inset) / math.sqrt(2), 1e-6, "on the circle")
    near(y, (70 - inset) / math.sqrt(2), 1e-6)
    near(ea.tex.__angle, -math.pi / 4, 1e-6, "pointing north-east")
    local r, g, b, a = ea.tex:GetVertexColor()
    H.ok(r > 0.99 and g > 0.99 and b > 0.99 and a > 0.99, "white: outside only the next circle")
    -- the distance sits on the arrow's inner side
    local _, _, _, lx, ly = ea.dist:GetPoint(1)
    H.ok(lx < 0 and ly < 0, "towards the centre")
    -- AddicatUI's square minimap: in the corner
    M.env.GetMinimapShape = function() return "SQUARE" end
    M.Advance(0.2)
    x, y = offsetOf(ea)
    near(x, 70 - inset, 1e-6, "on the square's edge")
    near(y, 70 - inset, 1e-6)
    -- straight south: the middle of the bottom edge
    at(M, ns, -200, -200, { [15] = -400, [16] = -200, [17] = 50 })
    x, y = offsetOf(ea)
    near(x, 0, 1e-6); near(y, -(70 - inset), 1e-6)
    -- outside the current circle too: storm violet
    at(M, ns, -267, 603, { [15] = -400, [16] = -200, [17] = 50 })
    r, g, b = ea.tex:GetVertexColor()
    H.ok(math.abs(r - 0xA6 / 255) < 0.01 and math.abs(b - 0xE0 / 255) < 0.01, "storm violet in the storm")
    -- inside the safe zone: dimmed, pointing deeper in, with how far the edge is
    at(M, ns, -380.5, -200, { [15] = -400, [16] = -200, [17] = 50 })
    H.eq(ea.dist:GetText(), "30 yd inside")
    _, _, _, a = ea.tex:GetVertexColor()
    H.ok(a < 0.6, "dimmed inside")
    -- a turning minimap moves it every frame, without a new ROYS
    M.env.GetMinimapShape = nil
    M.cvars.rotateMinimap = "1"
    M.env.GetPlayerFacing = function() return math.pi end      -- facing south: south up
    M.Advance(0.02, 0.02)
    x, y = offsetOf(ea)
    near(x, 0, 1e-6); near(y, 70 - inset, 1e-6, "south is up now")
    -- the drop and spectators: no arrow
    at(M, ns, -200, -200, { [2] = 2, [6] = 1, [11] = 1 })
    H.ok(not ea:IsShown(), "falling: no arrow")
    at(M, ns, -200, -200, { [6] = 3 })
    H.ok(not ea:IsShown(), "spectating: no arrow")
end)

------------------------------------------------------------------------------------------------------
-- Icons
------------------------------------------------------------------------------------------------------
test("royale minimap: orbs and supply drops in view; supply drops off the minimap are pinned to its edge",
function(M, ns)
    connect(M)
    local RM = ns.RoyaleMinimap
    at(M, ns, 0, 0, { [15] = "", [16] = "", [17] = "" })
    H.send(M, "ROYO", { { 7001, 1 },
        { 1, "B", 1, 100, 0, 1, "" },          -- a speed orb 100 yd north: in view
        { 2, "B", 2, 0, -900, 1, "" },         -- far east: not pinned
        { 3, "B", 3, -50, 0, 2, 45000 },       -- taken: hidden
        { 4, "S", 0, 0, 60, 0, 30000 },        -- not here yet: hidden
        { 5, "D", 0, -600, 0, 3, 20000 },      -- a supply drop coming down far south: pinned
    })
    M.Advance(0.2)
    local list = shownIcons(ns)
    H.eq(#list, 2, "the orb in view and the pinned supply drop")
    local orb, supply
    for _, e in ipairs(list) do
        if e.obj.kind == "B" then orb = e else supply = e end
    end
    H.eq(orb.icon.rsIcon, "orbSpeed")
    H.eq(orb.pinned, false)
    local x, y = offsetOf(orb.icon)
    near(x, 0, 1e-6); near(y, 30, 1e-3, "at its place")
    near(orb.icon:GetWidth(), 12, 1e-9)
    H.ok(not orb.tick:IsShown())
    H.eq(supply.icon.rsIcon, "supply")
    H.eq(supply.pinned, true)
    near(supply.icon:GetWidth(), 16 * RM.PIN_SCALE, 1e-9, "0.8 scale on the edge")
    x, y = offsetOf(supply.icon)
    near(x, 0, 1e-6)
    near(y, -(70 - RM.TICK_INSET - RM.TICK_GAP - 16 * RM.PIN_SCALE / 2), 1e-6, "inside the bottom edge")
    H.ok(supply.tick:IsShown(), "with a tick")
    x, y = offsetOf(supply.tick)
    near(y, -(70 - RM.TICK_INSET), 1e-6, "the tick on the rim")
    near(supply.tick.__angle, -math.pi, 1e-6, "pointing at it (down)")
    -- it comes into view: at its place, no tick
    at(M, ns, -500, 0, { [15] = "", [16] = "", [17] = "" })
    list = shownIcons(ns)
    for _, e in ipairs(list) do
        if e.obj.kind == "D" then supply = e end
    end
    H.eq(supply.pinned, false)
    x, y = offsetOf(supply.icon)
    near(y, -30, 1e-3)
    H.ok(not supply.tick:IsShown())
    -- opened: gone
    H.send(M, "ROYO", { { 7001, 0 }, { 5, "D", 0, -600, 0, 4, "" } })
    M.Advance(0.2)
    for _, e in ipairs(shownIcons(ns)) do
        H.ok(e.obj.kind ~= "D", "an opened supply drop leaves the minimap")
    end
end)

test("royale minimap: a supply drop of ROYV D shows before ROYO lists it, once, and goes when opened",
function(M, ns)
    connect(M)
    at(M, ns, 0, 0, { [15] = "", [16] = "", [17] = "" })
    H.send(M, "ROYV", { { "D", 0, 40, 0, 20000, "" } })
    M.Advance(0.2)
    local list = shownIcons(ns)
    H.eq(#list, 1, "the announced drop")
    H.eq(list[1].icon.rsIcon, "supply")
    H.send(M, "ROYO", { { 7001, 0 }, { 20, "D", 0, 41, 1, 3, 19000 } })
    M.Advance(0.2)
    H.eq(#shownIcons(ns), 1, "once ROYO lists it, once")
    H.send(M, "ROYO", { { 7001, 0 }, { 20, "D", 0, 41, 1, 4, "" } })
    H.send(M, "ROYV", { { "O", 0, 41, 1, "", "" } })
    M.Advance(0.2)
    H.eq(#shownIcons(ns), 0, "opened")
    -- a spectator sees no icons
    H.send(M, "ROYV", { { "D", 0, 40, 0, 20000, "" } })
    at(M, ns, 0, 0, { [6] = 3 })
    H.eq(#shownIcons(ns), 0)
end)

------------------------------------------------------------------------------------------------------
-- The layer's rules
------------------------------------------------------------------------------------------------------
test("royale minimap: a plain frame on the Minimap, no buttons for AddicatUI's collector, edge pieces over its border",
function(M, ns)
    local RM = ns.RoyaleMinimap
    local layer = M.env.BleakholdRoyaleMinimapLayer
    H.eq(layer, RM.layer)
    H.eq(layer:GetParent(), M.env.Minimap)
    H.eq(layer:GetObjectType(), "Frame")
    H.eq(#M.Clickables(layer), 0, "AddicatUI collects Buttons parented to the Minimap (and one level of Frames)")
    for _, c in ipairs({ layer:GetChildren() }) do
        H.eq(c:GetObjectType(), "Frame")
    end
    M.env.Minimap:SetFrameLevel(3)
    connect(M)
    at(M, ns, 0, 0)
    H.eq(layer:GetFrameLevel(), 4)
    H.eq(RM.rim:GetFrameLevel(), 3 + RM.LEVEL, "over the stock border (+1) and AddicatUI's square border (+5)")
    H.ok(RM.arrow:GetFrameLevel() > RM.rim:GetFrameLevel())
end)

test("royale minimap: SetRotation only on rotatable art in square regions; no art minified past 2.2x", function(M, ns)
    local RM, RS = ns.RoyaleMinimap, ns.RoyaleStyle
    local DATA = ns.RoyaleArt
    connect(M)
    local function check(label)
        local ppu = RS.PxPerUnit(RM.rim)
        for _, e in ipairs(RM.icons) do
            if e.icon:IsShown() then
                local cell = e.icon.rsArt == "Icons" and DATA.icons.cellPx or DATA.icons.smallCellPx
                local px = e.icon:GetWidth() * ppu
                H.ok(cell / px <= 2.2 + 1e-9, label .. ": icon " .. e.icon.rsIcon .. " " .. cell .. " texels on "
                    .. px .. " px")
            end
            if e.tick:IsShown() then
                H.ok(32 / (e.tick.rsVisual * ppu) <= 2.2 + 1e-9, label .. ": tick")
            end
        end
        H.ok(64 / (RM.arrow.tex.rsVisual * RS.PxPerUnit(RM.arrow)) <= 2.2 + 1e-9, label .. ": arrow")
        H.ok(32 / (RM.arrow.socket:GetWidth() * RS.PxPerUnit(RM.arrow)) <= 2.2 + 1e-9, label .. ": socket")
        H.ok(RM.arrow.socket:GetWidth() >= RM.arrow.tex.rsVisual * 1.15, label .. ": the socket holds the needle")
    end
    for _, screen in ipairs({ { 1920, 1080, 1 }, { 2560, 1440, 1 }, { 1920, 1080, 0.64 } }) do
        M.SetScreen(screen[1], screen[2], screen[3])
        at(M, ns, 0, 0, { [15] = -100, [16] = -300, [17] = 50 })
        H.send(M, "ROYO", { { 7001, 1 }, { 1, "B", 1, 100, 0, 1, "" }, { 2, "S", 0, 0, 60, 1, "" },
            { 5, "D", 0, -600, 0, 3, 20000 } })
        M.Advance(0.2)
        check(screen[1] .. "x" .. screen[2] .. " UI scale " .. screen[3])
    end
    M.cvars.rotateMinimap = "1"
    M.env.GetPlayerFacing = function() return 1 end
    M.Advance(0.3)
    local rotatable = {}
    for name in pairs(RS.ROTATABLE) do
        rotatable[DATA.rotatable[name]] = true
    end
    H.ok(#M.rotations > 0, "the arrow and the ticks turned")
    for _, rot in ipairs(M.rotations) do
        H.ok(rotatable[rot.path], "SetRotation on " .. tostring(rot.path))
        near(rot.width, rot.height, 1e-9, "a square region")
    end
end)
