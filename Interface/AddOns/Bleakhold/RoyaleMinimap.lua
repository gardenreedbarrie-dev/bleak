-- Bleakhold: Bleakhold Royale on the minimap (frame BleakholdRoyaleMinimapLayer, a plain Frame child of Minimap: it
-- moves, scales and hides with the minimap, and AddicatUI's button collector takes Buttons only):
--   icons       supply drops (16 units), the boss (18) and its hoard (16), orbs (12), from ROYO (and a supply drop of
--               ROYV D or L that ROYO has not listed yet) at their places within the view, the boss on a soft green
--               glow (brighter while it stirs); a supply drop, the boss or the hoard outside the view is pinned to
--               the minimap's edge at 0.8 scale with a small tick pointing at it, like stock tracking, beside the
--               safe-zone arrow when the arrow's socket would cover it
--   safe arrow  BleakholdRoyaleSafeArrow on the edge of the minimap's own shape (round, or AddicatUI's square),
--               towards the safe zone (the next circle once shown, else the current one) with the distance: a needle
--               turning in a bronze socket (the stage pips' Gem socket), storm violet outside the current circle,
--               white outside only the next one; inside it stays, dimmed, with "N yd inside". The socket keeps the
--               bare white Arrow from reading as a mouse pointer and gives it the HUD's forged look
--   storm dots  only for a Bleakhold.exe that does not draw the storm on the minimap itself (no
--               BleakholdStorm_MinimapViewRadius, or its bleakStormMinimap CVar at 0): dots on the part of each circle
--               the minimap shows, the storm's edge in storm violet, the next circle white with every other dot left
--               out (dashed); only while the client knows its own position (the server's myX/myY can be 5 s old, and
--               the dots would jump)
-- Nothing shows for a spectator: the minimap follows the camera target, which the addon does not know. The projection
-- is the minimap's own: the view radius from Bleakhold.exe (MinimapGetViewRadius), else the client's zoom tables
-- (MinimapFrame.cpp) indexed by Minimap:GetZoom(), with IsIndoors() choosing the table (comparing the zoom CVars
-- cannot tell the two apart when they are equal); north up, or turned with the player (rotateMinimap). Positions
-- follow at 10 Hz, every frame while the minimap turns. /bh royale minimap on|off (royaleMinimap, RM.Command)
-- switches the exe's storm and the dots together.
local ADDON, ns = ...
local U, UI = ns.U, ns.UI
local S = ns.S
local R = ns.Royale
local RS = ns.RoyaleStyle

local type, tonumber, ipairs = type, tonumber, ipairs
local floor, ceil, max, min, abs, sqrt, sin, cos, atan2, acos, pi = math.floor, math.ceil, math.max, math.min,
    math.abs, math.sqrt, math.sin, math.cos, math.atan2, math.acos, math.pi

local RM = {}
ns.RoyaleMinimap = RM

------------------------------------------------------------------------------------------------------
-- Constants
------------------------------------------------------------------------------------------------------
-- yards from the minimap's centre to the middle of its edge by zoom 0-5 (MinimapFrame.cpp MinimapGetViewRadius:
-- outdoors half the shown tiles of 33.333 yd, indoors its own table)
RM.ZOOM_OUTDOOR = {}
for i, tiles in ipairs({ 14, 12, 10, 8, 6, 4 }) do
    RM.ZOOM_OUTDOOR[i] = tiles * 0.5 * 33.333332
end
RM.ZOOM_INDOOR = { 150, 120, 90, 60, 40, 25 }

RM.INTERVAL = 0.1             -- s between layouts of a north-up minimap (a turning one: every frame)
-- objects by kind (buff orbs by subtype): the icon (RoyaleArtData.lua icons), its size in units, its tick's colour,
-- whether it is pinned to the edge outside the view (orbs are not: only what players travel for), and a soft glow
-- under it (the storm beast: its aura on the island map)
RM.OBJECTS = {
    S = { icon = "eye", size = 12 },
    B1 = { icon = "orbSpeed", size = 12 },
    B2 = { icon = "orbRestore", size = 12 },
    B3 = { icon = "orbBerserk", size = 12 },
    D = { icon = "supply", size = 16, pin = true, color = "gold" },
    X = { icon = "beast", size = 18, pin = true, color = "beast", glow = 1.9 },
    H = { icon = "hoard", size = 16, pin = true, color = "gold" },
}
RM.SHOWN = { [1] = true, [3] = true }   -- ready and incoming; not hidden (0), taken (2) or opened (4)
RM.PIN_SCALE = 0.8
RM.TICK = 12                  -- the EdgeTick's visual size
RM.TICK_INSET = 4             -- units from the edge to the tick's centre (its tip just inside the rim)
RM.TICK_GAP = 2.5             -- units between the tick's centre and a pinned icon's edge
RM.ARROW = 22                 -- the Arrow needle's visual size
RM.SOCKET = 1.18              -- the socket's size by the needle's: its void (0.29) holds the needle (0.37) but the tips
RM.RIM_GAP = 1                -- units between the socket and the minimap's edge
RM.LABEL = 11                 -- the distance beside the arrow (FRIZQT OUTLINE)
-- interface textures have no mipmaps (CSimpleRender.cpp): on a small minimap or at a small UI scale a piece grows in
-- units so its art is never minified more than about 2.2 times (IconsSmall 32-px cells, Arrow 64 px, EdgeTick 32 px;
-- the 32-px Gem socket only grows with its needle)
RM.MIN_PX = { icon = 15, tick = 15, arrow = 30 }
RM.DOT = 3                    -- the storm dots: size and spacing in units, at most this many
RM.DOT_GAP = 7
RM.DOT_MAX = 120
RM.DOT_UNDER = 5              -- the dark disc under each dot, so it reads over beach and sand
-- the edge pieces' frame level over the Minimap's: above the stock border (MinimapBackdrop, a child: +1) and
-- AddicatUI's square border (+5)
RM.LEVEL = 6
RM.EVENT_PING = { D = 8, L = 10 }   -- s a supply drop of ROYV D (after its landing) or L shows without ROYO

RM.TEXT = {
    native = "Storm on the minimap: drawn by Bleakhold.exe.",
    dots = "Storm on the minimap: dotted circles (this game draws no storm on the minimap).",
    off = "Storm on the minimap: off (/bh royale minimap on).",
}

------------------------------------------------------------------------------------------------------
-- Frames
------------------------------------------------------------------------------------------------------
local mapFrame = Minimap or UIParent

local layer = CreateFrame("Frame", "BleakholdRoyaleMinimapLayer", mapFrame)
layer:SetAllPoints(mapFrame)
layer:EnableMouse(false)
layer:Hide()
RM.layer = layer

-- icons, ticks and the arrow: over the minimap's border art, since pinned icons sit on its rim
local rim = CreateFrame("Frame", nil, layer)
rim:SetAllPoints(layer)
rim:EnableMouse(false)
RM.rim = rim

local ea = CreateFrame("Frame", "BleakholdRoyaleSafeArrow", rim)
ea:SetSize(RM.ARROW * RS.SQRT2, RM.ARROW * RS.SQRT2)
ea:EnableMouse(false)
ea:Hide()
ea.socket = RS.Art(ea, "Gem", RM.ARROW * RM.SOCKET, RM.ARROW * RM.SOCKET, "ARTWORK", ns.RoyaleArt.gem.socket)
ea.socket:SetPoint("CENTER", ea, "CENTER", 0, 0)
ea.tex = RS.Rotatable(ea, "Arrow", RM.ARROW, "OVERLAY")
ea.tex:SetPoint("CENTER", ea, "CENTER", 0, 0)
ea.dist = RS.Text(ea, "map", RM.LABEL, "parchment", "CENTER")
RM.arrow = ea

-- The frame levels follow the minimap's (AddicatUI sets its own after load).
local levelOf
local function applyLevels()
    local base = mapFrame:GetFrameLevel() or 0
    if levelOf == base then
        return
    end
    levelOf = base
    layer:SetFrameLevel(base + 1)
    rim:SetFrameLevel(base + RM.LEVEL)
    ea:SetFrameLevel(base + RM.LEVEL + 1)
end

-- A rotatable's visual size (its square region is visual x sqrt(2)).
local function setVisual(t, v)
    if t.rsVisual ~= v then
        t.rsVisual = v
        t:SetSize(v * RS.SQRT2, v * RS.SQRT2)
    end
end

-- `units`, raised so the piece shows at least `px` physical pixels.
local function atLeast(units, px, region)
    return max(units, px / RS.PxPerUnit(region))
end

------------------------------------------------------------------------------------------------------
-- The projection
------------------------------------------------------------------------------------------------------
-- Yards the minimap shows from its centre to the middle of its edge.
function RM.ViewRadius()
    if BleakholdStorm_MinimapViewRadius then
        local r = BleakholdStorm_MinimapViewRadius()
        r = tonumber(r)
        if r and r > 0 then
            return r
        end
    end
    local zoom = Minimap and Minimap.GetZoom and Minimap:GetZoom()
    zoom = U.Clamp(floor(tonumber(zoom) or 0), 0, 5)
    local indoors = IsIndoors and IsIndoors() and true or false
    return (indoors and RM.ZOOM_INDOOR or RM.ZOOM_OUTDOOR)[zoom + 1]
end

local geo = {}

-- The minimap as the layer sees it: half (units from the centre to the middle of the edge), shape ("ROUND" or
-- "SQUARE"; the circle is inside every other shape LibDBIcon knows, so those count as round), view (yards for half),
-- k (units per yard), rotate, facing (radians) and its cos and sin. One shared table; nil without a minimap.
function RM.Geometry()
    if not Minimap then
        return nil
    end
    local w = Minimap:GetWidth() or 0
    local ls = layer:GetEffectiveScale() or 1
    if w <= 0 or ls <= 0 then
        return nil
    end
    local view = RM.ViewRadius()
    if not view or view <= 0 then
        return nil
    end
    geo.half = w / 2 * (Minimap:GetEffectiveScale() or 1) / ls
    geo.shape = (GetMinimapShape and GetMinimapShape() == "SQUARE") and "SQUARE" or "ROUND"
    geo.view = view
    geo.k = geo.half / view
    geo.rotate = GetCVar and GetCVar("rotateMinimap") == "1" or false
    geo.facing = geo.rotate and (R.Facing() or 0) or 0
    geo.cos, geo.sin = cos(geo.facing), sin(geo.facing)
    return geo
end

-- Is the layer point x, y (units from the centre) within h of the centre: a circle, or a square (max(|x|, |y|)).
function RM.Inside(x, y, h, shape)
    if shape == "SQUARE" then
        return max(abs(x), abs(y)) <= h
    end
    return x * x + y * y <= h * h
end

-- World offsets (dx north, dy west, yards; world X points north and Y west) to layer offsets (units, x right, y up)
-- and whether the point is on the minimap. A turning minimap shows the player's facing up: the north-up offset
-- turns by -facing: a direction of bearing b (from north towards west) shows at pi/2 + b - facing.
function RM.Project(dx, dy, g)
    g = g or RM.Geometry()
    if not g then
        return nil
    end
    local x, y = -dy * g.k, dx * g.k
    if g.rotate then
        local c, s = g.cos or cos(g.facing or 0), g.sin or sin(g.facing or 0)
        x, y = x * c + y * s, y * c - x * s
    end
    return x, y, RM.Inside(x, y, g.half, g.shape)
end

-- The point `inset` units inside the minimap's edge in the direction x, y (Orbs.Offset's square rule).
function RM.EdgePoint(x, y, inset, g)
    local h = g.half - (inset or 0)
    local m = g.shape == "SQUARE" and max(abs(x), abs(y)) or sqrt(x * x + y * y)
    if m <= 0 then
        return 0, h
    end
    return x / m * h, y / m * h
end

------------------------------------------------------------------------------------------------------
-- Objects: ROYO, and a supply drop ROYV D or L announced before ROYO listed it
------------------------------------------------------------------------------------------------------
local eventPing

ns.On("ROYALE_EVENT", function(e)
    if (e.kind == "D" or e.kind == "L") and e.x then
        local hold = RM.EVENT_PING[e.kind] + (e.kind == "D" and (e.msLeft or 20000) / 1000 or 0)
        eventPing = { id = -1, kind = "D", subtype = 0, x = e.x, y = e.y, state = e.kind == "D" and 3 or 1,
            msLeft = e.msLeft, recvAt = e.recvAt, untilAt = GetTime() + hold }
    elseif e.kind == "O" then
        eventPing = nil
    end
end)

ns.On("ROYALE_MATCH", function()
    eventPing = nil
end)

function RM.ObjectStyle(o)
    return RM.OBJECTS[o.kind == "B" and ("B" .. (o.subtype or 0)) or o.kind]
end

local objectList = {}

-- The objects of match m shown on the minimap (one shared list).
function RM.Objects(m)
    wipe(objectList)
    local store = S.royaleObjects
    if store and m and store.matchId == m.matchId then
        for _, o in ipairs(store.list) do
            if RM.SHOWN[o.state] and RM.ObjectStyle(o) then
                objectList[#objectList + 1] = o
            end
        end
    end
    local p = eventPing
    if p and GetTime() < p.untilAt then
        for _, o in ipairs(objectList) do
            if o.kind == "D" and abs(o.x - p.x) < 5 and abs(o.y - p.y) < 5 then
                return objectList
            end
        end
        objectList[#objectList + 1] = p
    end
    return objectList
end

------------------------------------------------------------------------------------------------------
-- Icons (pooled): in the view, or pinned to the edge with a tick
------------------------------------------------------------------------------------------------------
local icons = { used = 0 }
RM.icons = icons

local function iconEntry(i)
    local e = icons[i]
    if not e then
        e = { icon = RS.Icon(rim, "supply", 16, "ARTWORK"), tick = RS.Rotatable(rim, "EdgeTick", RM.TICK, "OVERLAY") }
        e.glow = RS.Art(rim, "GemGlow", 32, 32, "BORDER")
        e.glow:SetBlendMode("ADD")
        e.icon:Hide()
        e.tick:Hide()
        e.glow:Hide()
        icons[i] = e
    end
    return e
end

local function hideIcons(from)
    for i = from, #icons do
        icons[i].icon:Hide()
        icons[i].tick:Hide()
        icons[i].glow:Hide()
        icons[i].obj, icons[i].pinned = nil, nil
    end
    icons.used = from - 1
end

-- The direction (unit vector, layer units) at which a pin in direction (ux, uy) sits on the rim: its own, unless the
-- safe-zone arrow's socket (RM.arrowAt) would cover it there (the beast's den lies near the next circle's centre by
-- design, so the two often point the same way); then it slides along the rim beside the socket, on its own side.
-- Its tick keeps pointing at the object.
local function pinDirection(ux, uy, inset, half, g)
    local a = RM.arrowAt
    if not a then
        return ux, uy
    end
    local ix, iy = RM.EdgePoint(ux, uy, inset, g)
    local need = a.r + half + 2
    if (ix - a.x) ^ 2 + (iy - a.y) ^ 2 >= need * need then
        return ux, uy
    end
    local r = max(sqrt(ix * ix + iy * iy), need)
    local theta = need / r
    local side = (a.ux * uy - a.uy * ux) >= 0 and 1 or -1
    local c, s = cos(side * theta), sin(side * theta)
    return a.ux * c - a.uy * s, a.ux * s + a.uy * c
end

local function setIcon(e, name, size)
    local t = e.icon
    if t.rsIcon ~= name then
        t:SetIcon(name)
    end
    if t.rsSize ~= size then
        t:SetIconSize(size)
    end
end

function RM.UpdateIcons(m, x, y, g)
    local n = 0
    if x and g then
        local minIcon = RM.MIN_PX.icon / RS.PxPerUnit(rim)
        local tickSize = atLeast(RM.TICK, RM.MIN_PX.tick, rim)
        for _, o in ipairs(RM.Objects(m)) do
            local st = RM.ObjectStyle(o)
            local size = max(st.size, minIcon)
            local px, py = RM.Project(o.x - x, o.y - y, g)
            local inView = RM.Inside(px, py, g.half - size / 2, g.shape)
            if inView or st.pin then
                n = n + 1
                local e = iconEntry(n)
                e.obj = o
                e.pinned = not inView
                local shownSize = size
                if inView then
                    setIcon(e, st.icon, size)
                    e.icon:ClearAllPoints()
                    e.icon:SetPoint("CENTER", layer, "CENTER", px, py)
                    e.tick:Hide()
                else
                    local len = sqrt(px * px + py * py)
                    local ux, uy = px / len, py / len
                    local ps = max(size * RM.PIN_SCALE, minIcon)
                    local ts = tickSize / RM.TICK      -- a tick grown for a small minimap keeps its tip inside
                    shownSize = ps
                    setIcon(e, st.icon, ps)
                    local inset = (RM.TICK_INSET + RM.TICK_GAP) * ts + ps / 2
                    local dx, dy = pinDirection(ux, uy, inset, ps / 2, g)
                    local kx, ky = RM.EdgePoint(dx, dy, RM.TICK_INSET * ts, g)
                    local ix, iy = RM.EdgePoint(dx, dy, inset, g)
                    e.icon:ClearAllPoints()
                    e.icon:SetPoint("CENTER", layer, "CENTER", ix, iy)
                    setVisual(e.tick, tickSize)
                    e.tick:ClearAllPoints()
                    e.tick:SetPoint("CENTER", layer, "CENTER", kx, ky)
                    e.tick:SetAngle(atan2(uy, ux) - pi / 2)
                    e.tick:SetVertexColor(RS.Rgb(st.color or "gold"))
                    e.tick:Show()
                end
                e.icon:SetAlpha(o.state == 3 and 0.85 or 1)
                e.icon:Show()
                if st.glow then
                    local gs = shownSize * st.glow
                    e.glow:SetSize(gs, gs)
                    e.glow:ClearAllPoints()
                    e.glow:SetPoint("CENTER", e.icon, "CENTER", 0, 0)
                    e.glow:SetVertexColor(RS.Rgb(st.color or "gold", o.state == 3 and 0.75 or 0.5))
                    e.glow:Show()
                else
                    e.glow:Hide()
                end
            end
        end
    end
    hideIcons(n + 1)
end

------------------------------------------------------------------------------------------------------
-- The safe-zone arrow
------------------------------------------------------------------------------------------------------
function RM.UpdateArrow(m, x, y, g)
    RM.arrowAt = nil
    if not (m and x and g and m.me == R.ME.ALIVE and R.Fighting(m)) then
        ea:Hide()
        return
    end
    local cx, cy, cr = R.Circle(m)
    -- the safe zone: the next circle once it is shown, else the current one
    local tx, ty, tr = cx, cy, cr
    if m.nextR then
        tx, ty, tr = m.nextX, m.nextY, m.nextR
    end
    local away = R.OutsideBy(x, y, tx, ty, tr)
    if not away then
        ea:Hide()
        return
    end
    local out = R.OutsideBy(x, y, cx, cy, cr)
    local inStorm = out ~= nil and out > 0
    -- inside the safe zone the arrow stays, dimmed, pointing deeper in, with how far the edge is
    local inside = away <= 0
    local px, py = RM.Project(tx - x, ty - y, g)
    local len = sqrt(px * px + py * py)
    local ux, uy = 0, 1
    if len > 1e-6 then
        ux, uy = px / len, py / len
    end
    local size = atLeast(RM.ARROW, RM.MIN_PX.arrow, ea)
    local socket = size * RM.SOCKET
    setVisual(ea.tex, size)
    ea:SetSize(size * RS.SQRT2, size * RS.SQRT2)
    ea.socket:SetSize(socket, socket)
    local ex, ey = RM.EdgePoint(ux, uy, socket / 2 + RM.RIM_GAP, g)
    RM.arrowAt = { x = ex, y = ey, r = socket / 2, ux = ux, uy = uy }   -- pinned icons keep clear of it
    ea:ClearAllPoints()
    ea:SetPoint("CENTER", layer, "CENTER", ex, ey)
    ea.tex:SetAngle(atan2(uy, ux) - pi / 2)
    ea.tex:SetVertexColor(RS.Rgb(inStorm and "storm" or "safe", inside and 0.45 or 1))
    ea.socket:SetAlpha(inside and 0.7 or 1)
    local text = inside and (floor(-away) .. " yd inside") or (ceil(away) .. " yd")
    if ea.dist:GetText() ~= text then
        ea.dist:SetText(text)
    end
    ea.dist:SetTextColor(RS.Rgb(inside and "ash" or (inStorm and "stormLight" or "parchment"), inside and 0.8 or 1))
    -- the distance on the arrow's inner side, so it never hangs over the minimap's rim
    local d = socket / 2 + 2 + abs(ux) * (ea.dist:GetStringWidth() or 0) / 2 + abs(uy) * RM.LABEL / 2
    ea.dist:ClearAllPoints()
    ea.dist:SetPoint("CENTER", ea, "CENTER", -ux * d, -uy * d)
    ea:Show()
end

------------------------------------------------------------------------------------------------------
-- The storm dots (a Bleakhold.exe that does not draw the storm on the minimap)
------------------------------------------------------------------------------------------------------
-- The native storm is drawn: Bleakhold.exe with the overlay, and its CVar on.
function RM.NativeStorm()
    return BleakholdStorm_MinimapViewRadius ~= nil and not (GetCVar and GetCVar("bleakStormMinimap") == "0")
end

function RM.Enabled()
    return ns.Option("royaleMinimap", true) ~= false
end

function RM.DotsWanted()
    return RM.Enabled() and not RM.NativeStorm()
end

-- A circle is up from the reveal of circle 1, 15 s before the drop, until the match is decided (H.WallWanted's
-- rule: in the lobby the server's ROYS still says stage 0 after the reveal, with the next circle set).
function RM.CirclesWanted(m)
    if m == nil or m.phase < R.PHASE.COUNTDOWN or m.phase > R.PHASE.OVERTIME then
        return false
    end
    return (m.stage or 0) >= 1 or (m.phase == R.PHASE.COUNTDOWN and m.nextR ~= nil)
end

-- The arc (from, to radians, layer space, from <= to) of the circle at cx, cy with radius r (units) that lies within
-- h of the layer's centre; nil when none does. |P|^2 = d^2 + r^2 + 2rd cos(a - phi) <= h^2 holds on an arc around
-- the circle's side nearest the centre.
function RM.ArcInDisc(cx, cy, r, h)
    if not (r and r > 0 and h > 0) then
        return nil
    end
    local d = sqrt(cx * cx + cy * cy)
    if d + r <= h then
        return 0, 2 * pi
    end
    if d >= r + h or r >= d + h then
        return nil
    end
    local q = U.Clamp((h * h - d * d - r * r) / (2 * r * d), -1, 1)
    local half = pi - acos(q)
    local mid = atan2(cy, cx) + pi
    return mid - half, mid + half
end

local dots = { used = 0 }
RM.dots = dots

local function dotEntry(i)
    local e = dots[i]
    if not e then
        e = { under = layer:CreateTexture(nil, "ARTWORK"), dot = layer:CreateTexture(nil, "OVERLAY") }
        e.under:SetTexture(UI.ART .. "Disc")
        e.under:SetSize(RM.DOT_UNDER, RM.DOT_UNDER)
        e.under:SetVertexColor(0, 0, 0, 0.55)
        e.dot:SetTexture(UI.ART .. "Disc")
        e.dot:SetSize(RM.DOT, RM.DOT)
        dots[i] = e
    end
    return e
end

local function hideDots(from)
    for i = from, #dots do
        dots[i].dot:Hide()
        dots[i].under:Hide()
    end
    dots.used = from - 1
end

-- Dots every RM.DOT_GAP units on the visible part of a world circle (centre wx, wy and radius wr, yards, from the
-- player at x, y), from dot n + 1 on; `every` 2 leaves out every other one. The dots sit at fixed world angles, so
-- they stay put while the player moves. Returns the last dot used.
local function circleDots(n, wx, wy, wr, x, y, g, color, every)
    local cx, cy = RM.Project(wx - x, wy - y, g)
    local r = wr * g.k
    local margin = RM.DOT_UNDER / 2
    local h = g.half - margin
    local from, to = RM.ArcInDisc(cx, cy, r, g.shape == "SQUARE" and h * RS.SQRT2 or h)
    if not from then
        return n
    end
    -- the world angle 0 (north) in the layer: up, turned with a turning minimap
    local offset = pi / 2 - (g.rotate and g.facing or 0)
    local step = RM.DOT_GAP / r
    local j0, j1
    if to - from >= 2 * pi - 1e-9 then
        local count = floor(2 * pi * r / RM.DOT_GAP)
        count = count - count % every
        if count < every then
            return n
        end
        step = 2 * pi / count
        j0, j1 = 0, count - 1
    else
        j0, j1 = ceil((from - offset) / step), floor((to - offset) / step)
    end
    local cr, cg, cb, ca = RS.Rgb(color)
    for j = j0, j1 do
        if n >= RM.DOT_MAX then
            break
        end
        if j % every == 0 then
            local a = offset + j * step
            local px, py = cx + r * cos(a), cy + r * sin(a)
            if RM.Inside(px, py, h, g.shape) then
                n = n + 1
                local e = dotEntry(n)
                e.dot:SetVertexColor(cr, cg, cb, ca)
                e.dot:ClearAllPoints()
                e.dot:SetPoint("CENTER", layer, "CENTER", px, py)
                e.under:ClearAllPoints()
                e.under:SetPoint("CENTER", layer, "CENTER", px, py)
                e.dot:Show()
                e.under:Show()
            end
        end
    end
    return n
end

function RM.UpdateDots(m, g)
    local n = 0
    if g and RM.DotsWanted() and RM.CirclesWanted(m) then
        local x, y = R.ClientPos()
        if x then
            local cx, cy, cr = R.Circle(m)
            if cr then
                n = circleDots(n, cx, cy, cr, x, y, g, "storm", 1)
            end
            if m.nextR then
                n = circleDots(n, m.nextX, m.nextY, m.nextR, x, y, g, "safe", 2)
            end
        end
    end
    hideDots(n + 1)
end

------------------------------------------------------------------------------------------------------
-- Wiring
------------------------------------------------------------------------------------------------------
-- The players the layer is for: in the lobby, falling or alive (never a spectator, a player who left, or after the
-- match is decided).
local FOR_ME = { [0] = true, [1] = true, [2] = true }

function RM.Wanted(m)
    return m ~= nil and FOR_ME[m.me] == true and m.phase <= R.PHASE.OVERTIME
end

function RM.Update()
    local m = R.Match()
    if not RM.Wanted(m) then
        if layer:IsShown() then
            ea:Hide()
            RM.arrowAt = nil
            hideIcons(1)
            hideDots(1)
            layer:Hide()
        end
        return
    end
    applyLevels()
    if not layer:IsShown() then
        layer:Show()
    end
    local g = RM.Geometry()
    local x, y = R.MyPos()
    RM.UpdateDots(m, g)
    RM.UpdateArrow(m, x, y, g)
    RM.UpdateIcons(m, x, y, g)
end

local acc = 0
layer:SetScript("OnUpdate", function(self, elapsed)
    acc = acc + (elapsed or 0)
    -- a turning minimap turns every frame; a north-up one changes only as the player moves
    if acc >= RM.INTERVAL or (GetCVar and GetCVar("rotateMinimap") == "1") then
        acc = 0
        RM.Update()
    end
end)

-- the layer sleeps while hidden: this brings it back for a match (and hides it after one)
ns.Every(RM.INTERVAL, function()
    if (layer:IsShown() and true or false) ~= RM.Wanted(R.Match()) then
        RM.Update()
    end
end)

ns.On("STATE", function(topic)
    if topic == "ROYS" or topic == "ROYO" or topic == "ROYM" then
        RM.Update()
    end
end)

------------------------------------------------------------------------------------------------------
-- /bh royale minimap on|off
------------------------------------------------------------------------------------------------------
-- The storm on the minimap on or off: Bleakhold.exe's (the bleakStormMinimap CVar) and the dots together.
function RM.SetEnabled(on)
    ns.db.options.royaleMinimap = on and true or false
    if GetCVar and GetCVar("bleakStormMinimap") ~= nil then
        SetCVar("bleakStormMinimap", on and "1" or "0")
    end
    RM.Update()
end

function RM.StatusText()
    if not RM.Enabled() then
        return RM.TEXT.off
    end
    return RM.NativeStorm() and RM.TEXT.native or RM.TEXT.dots
end

-- /bh royale minimap [on|off] (Royale.lua's /bh royale hands the rest of the line here)
function RM.Command(args)
    local cmd = (args or ""):lower():match("^(%S*)")
    if cmd == "on" or cmd == "off" then
        RM.SetEnabled(cmd == "on")
    end
    ns.Print(RM.StatusText())
end
