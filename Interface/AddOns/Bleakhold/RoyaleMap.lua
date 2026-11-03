-- Bleakhold: Bleakhold Royale's island map (frame BleakholdRoyaleMapFrame; docs/BleakholdProtocol.md section 17) and
-- the M key in a match.
--
--   window     a riveted plate (RoyaleStyle.lua), 592x700: a header with the compass and the alive count, a 560-unit
--              canvas in a bronze frame, a footer with the status line and a legend. ESC closes it; it drags by the
--              header. While the match is in the lobby (phase 0 and 1) every open docks it left of the screen's
--              centre (right edge 24 units left of it, top under the bar's tab at -112), scaled to fit any aspect
--              ratio, so the drop countdown sits right of the centre (RoyaleCountdown.lua); from the drop on it opens
--              at the centre, or where the player last dragged it. It opens by itself once per match when the
--              landing phase starts (phase 1, never in the warm-up brawl, where it would cover the chat and the
--              unit frames); the countdown closes it with no sound at T-3.6 (MP.Close(true)).
--   picture    Art\Royale\Map (Tools/BlpConvert/make_royale_art.py: the terrain's own colours, hillshade, contours,
--              buildings), with what the server sends on top, bottom to top: the storm's shade outside the circle
--              (four rectangles and a hole, every edge snapped to whole pixels from the same numbers so they meet
--              with no seam and no doubled alpha, and a sparse hatch over it, so the storm reads without colour),
--              the storm's edge (violet, with a dark outline), the next circle (white dashes, turning slowly while
--              the storm moves), the lobby (red ring), the dotted way from the player to the next circle, the places
--              of ROYM with their names (laid out on ROYM so no two collide; one under an object fades), the orbs and
--              supply drops of ROYO with their timers, the storm beast (its den's green beam and the time until it
--              wakes, then the beast in a pulsing ring with its health) and its hoard, the landing pin and the
--              player's own chevron.
--   pins       in the lobby a left click sets the landing pin (R.SetPin, RDROP), unless the pin is locked: by the
--              server, or by this client from T-3.6 (RoyaleCountdown.lua's RC.Locked), so a click never vanishes
--              with the map. Hovering the canvas shows a ghost pin and the place it lands near.
--   M key      in a Royale battleground the keys of TOGGLEWORLDMAP run BLEAKHOLD_ROYALE_MAP through override
--              bindings owned by BleakholdRoyaleBindings. Setting and clearing them is protected in combat, so both
--              go through one queue that waits for PLAYER_REGEN_ENABLED (the last one queued wins). The stock world
--              map, opened another way (the micro button, a macro, AddicatUI's menus), is redirected out of combat
--              (hidden on the next frame, ours opened); in combat it is never touched (showing and hiding it is
--              protected): ours opens above it, and while patch-Q lacks the island's world map tiles a cover over
--              its detail frame shows the island instead of the stale tiles the client keeps from the last map that
--              had some (a failed SetTexture keeps the old picture). Ours is a UIParent child, which UIParent.lua
--              hides while a full-screen panel shows, so over the full-size stock map the cover alone shows the
--              island; over the windowed map (AddicatUI forces it) both do. Shift-M's battlefield minimap gets the
--              same cover. With the tiles in patch-Q both covers stay hidden.
--
-- Map transform (ROYM's frame): u = (maxY - y) / (maxY - minY), v = (maxX - x) / (maxX - minX); north up, west left.
-- Canvas units: MP.SIZE across the picture. The canvas sits in a ScrollFrame, which clips what lies outside it
-- (storm circles larger than the island).
local ADDON, ns = ...
local U, UI = ns.U, ns.UI
local S = ns.S
local R = ns.Royale
local RS = ns.RoyaleStyle
local DATA = ns.RoyaleArt

local floor, max, min, abs, sqrt, cos, pi = math.floor, math.max, math.min, math.abs, math.sqrt, math.cos, math.pi
local strformat = string.format

local MP = {}
ns.RoyaleMap = MP

-- 3.3.5 has no Region:SetShown
local function shown(region, on)
    if on then
        region:Show()
    else
        region:Hide()
    end
end

MP.W, MP.H = 592, 700              -- the window, in units at scale 1
MP.SIZE = 560                      -- the canvas (the picture) in units: MP.ToMap and MP.ToWorld use it
MP.BASE = MP.SIZE
MP.CANVAS_X, MP.CANVAS_Y = 16, 52  -- the canvas's top-left inside the window
MP.LIMIT = 700                     -- units beyond the canvas where the storm's shade stops (the ScrollFrame clips it)
MP.DOCK_GAP = 24                   -- lobby dock: the right edge this far left of the screen's centre
MP.DOCK_TOP, MP.DOCK_BOTTOM = 112, 24   -- under the top bar's tab (lower at a HUD scale over 1.14); room kept below
MP.SHADE_ALPHA, MP.HATCH_ALPHA = 0.42, 0.35
MP.HATCH_TEXELS = 32               -- Hatch.tga's size: one texel per physical pixel
MP.HATCH_BANDS = 12                -- bands per half circle that carry the hatch into the hole's corners
MP.EDGE_UNITS = 3                  -- the storm edge's line, aimed at by the ring art's size
MP.PATH_STEP, MP.PATH_DOT, MP.PATH_MAX = 10, 5, 60
MP.LABEL_GAP, MP.LABEL_PAD = 4, 4  -- a label 4 units off its icon; its halo 4 units round the text
MP.LABEL_SIZE, MP.CROSSING_SIZE = 11, 10
MP.TEXT_MIN_PX = 10                -- the window's live text never under 10 physical px (a docked map on 4:3 is small)
MP.ICON_LANDMARK, MP.ICON_CROSSING, MP.ICON_LOBBY = 14, 12, 16
MP.ICON_OBJECT, MP.PIN, MP.YOU = 18, 26, 24   -- You: 24 keeps its 64 texels within 2.2x on a docked 1080p map
MP.SCALE_YARDS = 200               -- the scale bar
MP.SEA = "8DA8AC"                  -- the covers' sea, the world map tiles' parchment-toned water (make_royale_art.py)
MP.INK = "1A120A"
MP.TILE_PROBE = "Interface\\WorldMap\\BleakholdRoyale\\BleakholdRoyale1"   -- patch-Q's world map tiles (MapForge)
-- ring art by size (texels): the line is 3 texels at the texture's edge, so its width follows the shown size
MP.RINGS = {
    { "Interface\\AddOns\\Bleakhold\\Art\\Royale\\Ring", 512 },
    { "Interface\\AddOns\\Bleakhold\\Art\\Royale\\RingMid", 128 },
    { "Interface\\AddOns\\Bleakhold\\Art\\Royale\\RingSmall", 32 },
}
MP.DASHED = {
    { "Interface\\AddOns\\Bleakhold\\Art\\Royale\\RingDashed", 512 },
    { "Interface\\AddOns\\Bleakhold\\Art\\Royale\\RingDashedMid", 128 },
}
MP.HOLES = {
    { "Interface\\AddOns\\Bleakhold\\Art\\Royale\\Hole", 256 },
    { "Interface\\AddOns\\Bleakhold\\Art\\Royale\\HoleSmall", 64 },
}
MP.MIN_TEXEL_RATIO = 2.2           -- interface textures have no mipmaps: never minified more than this

-- objects: the icon (RoyaleArtData.lua icons), the token for the minimap and the tooltip's lines, by kind (buff orbs
-- by subtype)
MP.OBJECT_STYLE = {
    S = { icon = "eye", color = "storm", name = "Shadow Sight", text = "Stealth is no cover for a while." },
    B1 = { icon = "orbSpeed", color = "orbSpeed", name = "Speed orb", text = "Run faster for a while." },
    B2 = { icon = "orbRestore", color = "orbRestore", name = "Restoration orb",
        text = "Health and mana back over a few seconds." },
    B3 = { icon = "orbBerserk", color = "orbBerserk", name = "Berserk orb",
        text = "More damage done, and taken, for a while." },
    D = { icon = "supply", color = "gold", name = "Supply drop", text = "A storm cache with rare loot." },
}
MP.STATE_TEXT = { [0] = "Not here yet", [1] = "Ready", [2] = "Taken", [3] = "Coming down", [4] = "Opened" }
MP.STATE_WHEN = { [0] = "Appears in ", [2] = "Back in ", [3] = "Lands in " }

-- the legend under the canvas; `when` hides an entry until it applies (the boss: once it has been announced)
MP.LEGEND = {
    { key = "you", art = "You", label = "You" },
    { key = "pin", icon = "pin", label = "Landing" },
    { key = "storm", icon = "stormArea", label = "Storm" },
    { key = "next", icon = "nextCircle", label = "Next circle" },
    { key = "supply", icon = "supply", label = "Supply" },
    { key = "orbs", icon = "orbSpeed", label = "Orbs" },
    { key = "boss", icon = "beast", label = "Boss", when = function() return MP.bossKnown and true or false end },
}

------------------------------------------------------------------------------------------------------
-- The window
------------------------------------------------------------------------------------------------------
local win = CreateFrame("Frame", "BleakholdRoyaleMapFrame", UIParent)
win:SetSize(MP.W, MP.H)
win:SetFrameStrata("HIGH")
win:SetToplevel(true)
win:EnableMouse(true)
win:SetMovable(true)
win:SetClampedToScreen(true)
win:SetPoint("CENTER", UIParent, "CENTER", 0, 20)
win:Hide()
MP.frame = win
if UISpecialFrames then
    table.insert(UISpecialFrames, win:GetName())
end

-- The kit's regions this window made, laid out again for a new scale (the dock scale changes with the screen).
local mine = { fonts = {}, icons = {}, plates = {}, hairlines = {} }

-- The kit's font at `size` units, raised to MP.TEXT_MIN_PX physical pixels at the window's scale now.
local function font(fs, role, size)
    fs.mpSize = size
    RS.Font(fs, role, max(size, MP.TEXT_MIN_PX / RS.PxPerUnit(fs)))
end

local function text(parent, role, size, color, justify, layer)
    local fs = RS.Text(parent, role, size, color, justify, layer)
    fs.mpSize = size
    mine.fonts[#mine.fonts + 1] = fs
    return fs
end

local function icon(parent, name, size, layer)
    local t = RS.Icon(parent, name, size, layer)
    mine.icons[#mine.icons + 1] = t
    return t
end

local function plate(frame, kind, opts)
    local p = RS.Plate(frame, kind, opts)
    mine.plates[#mine.plates + 1] = p
    return p
end

local function hairline(parent, length, color, vertical, layer, alpha)
    local t = RS.Hairline(parent, length, color, vertical, layer, alpha)
    mine.hairlines[#mine.hairlines + 1] = t
    return t
end

-- Sizes that follow the physical pixel (clamped text, icon atlases, plate corners, hairlines, the hatch, the ring
-- art) are applied again for the window's scale now.
local function relayout()
    for _, fs in ipairs(mine.fonts) do
        font(fs, fs.rsRole, fs.mpSize or fs.rsSize)
    end
    for _, t in ipairs(mine.icons) do
        t:SetIconSize(t.rsSize)
    end
    for _, p in ipairs(mine.plates) do
        p:Layout()
    end
    for _, t in ipairs(mine.hairlines) do
        local px = 1 / RS.PxPerUnit(t)
        if t.rsVertical then
            t:SetSize(px, t.rsLength)
        else
            t:SetSize(t.rsLength, px)
        end
    end
    MP.drawn = nil      -- the storm, rings and hatch are drawn again for the new pixel size
    if MP.LayoutLegend then
        MP.LayoutLegend()
    end
end

-- Scripts first: the kit hooks OnShow for its lazy textures.
win:SetScript("OnShow", function()
    if not MP.silent and PlaySound then
        PlaySound("igCharacterInfoOpen")
    end
    MP.Refresh()
end)
win:SetScript("OnHide", function()
    if not MP.silent and PlaySound then
        PlaySound("igCharacterInfoClose")
    end
    MP.auto, MP.overStock, MP.hover = nil, nil, nil
    win:SetFrameStrata("HIGH")
    if MP.rings then
        MP.rings.nextc.spinning = nil      -- a hidden region's animations stop: started again on the next show
    end
    if MP.ghost then
        MP.ghost:Hide()
    end
    if GameTooltip and GameTooltip:IsOwned(MP.canvas) then
        GameTooltip:Hide()
    end
end)

win.plate = plate(win, "Plate")

-- the header: compass, title, alive count, close
local header = CreateFrame("Frame", nil, win)
header:SetPoint("TOPLEFT", win, "TOPLEFT", 12, -8)
header:SetPoint("TOPRIGHT", win, "TOPRIGHT", -12, -8)
header:SetHeight(MP.CANVAS_Y - 12)
header:EnableMouse(true)
header:RegisterForDrag("LeftButton")
win.header = header

header.north = icon(header, "north", 24, "ARTWORK")
header.north:SetPoint("LEFT", header, "LEFT", 4, -1)
header.title = text(header, "heading", 16, "parchment", "LEFT")
header.title:SetPoint("LEFT", header.north, "RIGHT", 8, 0)
header.title:SetText("BLEAKHOLD ROYALE")

header.close = RS.Button(header, 22, 22, "", "iron")
header.close:SetIcon("close", 12)
header.close:SetPoint("RIGHT", header, "RIGHT", -4, 0)
header.close:SetScript("OnClick", function()
    MP.Close()
end)
win.close = header.close

local pill = CreateFrame("Frame", nil, header)
pill:SetSize(96, 22)
pill:SetPoint("RIGHT", header.close, "LEFT", -8, 0)
pill.plate = plate(pill, "PlateTab")
pill.text = text(pill, "body", 12, "parchment", "CENTER")
pill.text:SetPoint("CENTER", pill, "CENTER", 0, 0)
pill:Hide()
win.alive = pill

header:SetScript("OnDragStart", function()
    win:StartMoving()
end)
header:SetScript("OnDragStop", function()
    win:StopMovingOrSizing()
    -- only the fight's spot is kept: the lobby dock is always computed
    if not MP.docked then
        local point, _, relPoint, x, y = win:GetPoint(1)
        if point then
            ns.cdb.windows[win:GetName()] = { point = point, relPoint = relPoint, x = floor((x or 0) + 0.5),
                y = floor((y or 0) + 0.5) }
        end
    end
end)

-- the canvas in its bronze frame: a dark mat, a bronze hairline round it, a soft shadow inside the picture's edge
local mat = win:CreateTexture(nil, "BORDER")
mat:SetTexture(UI.WHITE)
mat:SetVertexColor(RS.Rgb(MP.INK, 1))
mat:SetPoint("TOPLEFT", win, "TOPLEFT", MP.CANVAS_X - 3, -(MP.CANVAS_Y - 3))
mat:SetSize(MP.SIZE + 6, MP.SIZE + 6)
win.mat = mat
do
    local o = 3                      -- the bronze line on the mat's outer edge
    local L = MP.SIZE + 2 * o
    local x0, y0 = MP.CANVAS_X - o, -(MP.CANVAS_Y - o)
    local top = hairline(win, L, "bronze", false, "ARTWORK")
    top:SetPoint("TOPLEFT", win, "TOPLEFT", x0, y0)
    local bottom = hairline(win, L, "bronzeLo", false, "ARTWORK")
    bottom:SetPoint("BOTTOMLEFT", win, "TOPLEFT", x0, y0 - L)
    local left = hairline(win, L, "bronze", true, "ARTWORK")
    left:SetPoint("TOPLEFT", win, "TOPLEFT", x0, y0)
    local right = hairline(win, L, "bronzeLo", true, "ARTWORK")
    right:SetPoint("TOPRIGHT", win, "TOPLEFT", x0 + L, y0)
end

local view = CreateFrame("ScrollFrame", nil, win)
view:SetSize(MP.SIZE, MP.SIZE)
view:SetPoint("TOPLEFT", win, "TOPLEFT", MP.CANVAS_X, -MP.CANVAS_Y)
local canvas = CreateFrame("Frame", nil, view)
canvas:SetSize(MP.SIZE, MP.SIZE)
view:SetScrollChild(canvas)
canvas:EnableMouse(true)
MP.view, MP.canvas = view, canvas

canvas.sea = canvas:CreateTexture(nil, "BACKGROUND")
canvas.sea:SetTexture(UI.WHITE)
canvas.sea:SetVertexColor(RS.Rgb(MP.SEA, 1))
canvas.sea:SetAllPoints(canvas)
canvas.pic = canvas:CreateTexture(nil, "BORDER")
canvas.pic:SetAllPoints(canvas)
RS.LazyTexture(canvas.pic, R.MAP_TEX)
canvas.none = text(canvas, "body", 13, "ash", "CENTER")
canvas.none:SetPoint("CENTER", canvas, "CENTER", 0, 0)
canvas.none:SetText("Map unavailable")
canvas.none:Hide()

local base = canvas:GetFrameLevel()
local function layer(level)
    local f = CreateFrame("Frame", nil, canvas)
    f:SetAllPoints(canvas)
    f:SetFrameLevel(base + level)
    return f
end
local shadeLayer, ringLayer, pathLayer, poiLayer = layer(1), layer(2), layer(3), layer(4)
local dressLayer, labelLayer, objLayer, topLayer, fxLayer = layer(5), layer(6), layer(7), layer(8), layer(9)
MP.layers = { shade = shadeLayer, ring = ringLayer, path = pathLayer, poi = poiLayer, dress = dressLayer,
    obj = objLayer, label = labelLayer, top = topLayer, fx = fxLayer }

-- the inner shadow along the picture's edges (it sits on the picture, under everything drawn on it)
do
    local W = 12
    local function edge(point, w, h, orient, a1, a2)
        local t = shadeLayer:CreateTexture(nil, "BACKGROUND")
        t:SetTexture(UI.WHITE)
        t:SetPoint(point, canvas, point, 0, 0)
        t:SetSize(w, h)
        t:SetGradientAlpha(orient, 0, 0, 0, a1, 0, 0, 0, a2)
        return t
    end
    -- VERTICAL runs from the bottom (min) to the top (max), HORIZONTAL from the left
    edge("TOPLEFT", MP.SIZE, W, "VERTICAL", 0, 0.45)
    edge("BOTTOMLEFT", MP.SIZE, W, "VERTICAL", 0.45, 0)
    edge("TOPLEFT", W, MP.SIZE, "HORIZONTAL", 0.45, 0)
    edge("TOPRIGHT", W, MP.SIZE, "HORIZONTAL", 0, 0.45)
end

-- the footer: the status line, a hairline, the legend
local foot = CreateFrame("Frame", nil, win)
foot:SetPoint("TOPLEFT", win, "TOPLEFT", MP.CANVAS_X, -(MP.CANVAS_Y + MP.SIZE + 6))
foot:SetSize(MP.SIZE, 74)
win.foot = foot
foot.left = text(foot, "body", 13, "parchment", "LEFT")
foot.left:SetPoint("LEFT", foot, "TOPLEFT", 2, -16)
foot.left:SetWidth(380)
foot.left:SetHeight(17)
foot.left:SetNonSpaceWrap(false)
foot.right = text(foot, "body", 12, "ash", "RIGHT")
foot.right:SetPoint("RIGHT", foot, "TOPRIGHT", -2, -16)
foot.right:SetWidth(172)
foot.right:SetHeight(16)
foot.right:SetNonSpaceWrap(false)
foot.rule = hairline(foot, MP.SIZE, "bronzeLo", false, "ARTWORK")
foot.rule:SetPoint("TOPLEFT", foot, "TOPLEFT", 0, -32)
MP.strip = foot

local legend = CreateFrame("Frame", nil, foot)
legend:SetPoint("TOPLEFT", foot, "TOPLEFT", 0, -36)
legend:SetSize(MP.SIZE, 32)
legend.items = {}
for _, e in ipairs(MP.LEGEND) do
    local item = { e = e }
    if e.art then
        -- the chevron's ink is 70 % of its art: at 23 units it matches the 16-unit icons beside it, and its 64 texels
        -- stay within 2.2x on a docked 1080p map
        item.tex = RS.Rotatable(legend, e.art, 23, "ARTWORK")
        item.w = 16
    else
        item.tex = icon(legend, e.icon, 16, "ARTWORK")
        item.w = 16
    end
    item.label = text(legend, "body", 11, "ash", "LEFT")
    item.label:SetText(e.label)
    legend.items[#legend.items + 1] = item
end
win.legend = legend

-- The legend's entries side by side, centred (only the ones that apply).
function MP.LayoutLegend()
    local vis, total = {}, 0
    for _, item in ipairs(legend.items) do
        local on = not item.e.when or item.e.when()
        shown(item.tex, on)
        shown(item.label, on)
        if on then
            vis[#vis + 1] = item
            total = total + item.w + 5 + (item.label:GetStringWidth() or 0)
        end
    end
    local gap = 18
    total = total + gap * max(0, #vis - 1)
    local x = floor((MP.SIZE - total) / 2)
    for _, item in ipairs(vis) do
        item.tex:ClearAllPoints()
        item.tex:SetPoint("CENTER", legend, "LEFT", x + item.w / 2, 0)
        item.label:ClearAllPoints()
        item.label:SetPoint("LEFT", legend, "LEFT", x + item.w + 5, 0)
        x = x + item.w + 5 + (item.label:GetStringWidth() or 0) + gap
    end
end
MP.LayoutLegend()

------------------------------------------------------------------------------------------------------
-- Transform
------------------------------------------------------------------------------------------------------
-- World (x, y) -> canvas units from the picture's top-left corner.
function MP.ToMap(x, y, map)
    map = map or S.royaleMap
    local u = (map.maxY - y) / (map.maxY - map.minY)
    local v = (map.maxX - x) / (map.maxX - map.minX)
    return u * MP.SIZE, v * MP.SIZE
end

-- Canvas units from the picture's top-left corner -> world (x, y).
function MP.ToWorld(px, py, map)
    map = map or S.royaleMap
    local u, v = px / MP.SIZE, py / MP.SIZE
    return map.maxX - v * (map.maxX - map.minX), map.maxY - u * (map.maxY - map.minY)
end

-- Yards -> canvas units (the mean of both axes; the island's frame is square).
function MP.Yards(yd, map)
    map = map or S.royaleMap
    local span = ((map.maxX - map.minX) + (map.maxY - map.minY)) / 2
    return yd * MP.SIZE / span
end

-- The cursor in canvas units from the picture's top-left corner.
function MP.CursorPos()
    local x, y = GetCursorPosition()
    local s = canvas:GetEffectiveScale() or 1
    local left, top = canvas:GetLeft(), canvas:GetTop()
    if not (x and left and top) or s <= 0 then
        return nil
    end
    return x / s - left, top - y / s
end

------------------------------------------------------------------------------------------------------
-- Places: the name a point lands near, and labels that never collide
------------------------------------------------------------------------------------------------------
-- The landmark or crossing whose circle (its radius x 1.5) holds (x, y), the nearest centre first; else "the wilds"
-- (lower case: it is used inside sentences: "Landing at the wilds" never shows, the tab says "Land near ...").
function MP.NearestPlace(x, y, map)
    map = map or S.royaleMap
    local best, bestD
    for _, p in ipairs(map and map.pois or {}) do
        if (p.kind == "L" or p.kind == "C") and p.name and p.name ~= "" then
            local d = sqrt((x - p.x) ^ 2 + (y - p.y) ^ 2)
            if d <= (p.r or 0) * 1.5 and (not bestD or d < bestD) then
                best, bestD = p.name, d
            end
        end
    end
    return best or "the wilds"
end

local function overlaps(a, b)
    return a.l < b.r and b.l < a.r and a.t < b.b and b.t < a.b
end

-- Greedy, deterministic label placement. list: { x, y (the icon's centre), icon (its size), w, h (the label's
-- rectangle, halo included) }, in priority order; obstacles: rectangles no label may cover (besides the icons).
-- Each label tries below, above, right and left of its icon (MP.LABEL_GAP off) and keeps the first rectangle that
-- stays inside the canvas and meets neither an earlier label nor an icon; none fits: false (the tooltip still names
-- the place). Returns one rectangle { l, t, r, b } (or false) per entry; y grows downwards.
function MP.LayoutLabels(list, obstacles)
    local icons, placed, out = {}, {}, {}
    for _, e in ipairs(list) do
        local h = (e.icon or 0) / 2
        icons[#icons + 1] = { l = e.x - h, t = e.y - h, r = e.x + h, b = e.y + h }
    end
    for _, o in ipairs(obstacles or {}) do
        icons[#icons + 1] = o
    end
    local g = MP.LABEL_GAP
    for i, e in ipairs(list) do
        local h = (e.icon or 0) / 2
        local tries = {
            { l = e.x - e.w / 2, t = e.y + h + g },                    -- below
            { l = e.x - e.w / 2, t = e.y - h - g - e.h },              -- above
            { l = e.x + h + g, t = e.y - e.h / 2 },                    -- right
            { l = e.x - h - g - e.w, t = e.y - e.h / 2 },              -- left
        }
        out[i] = false
        for _, c in ipairs(tries) do
            c.r, c.b = c.l + e.w, c.t + e.h
            local ok = c.l >= 0 and c.t >= 0 and c.r <= MP.SIZE and c.b <= MP.SIZE
            if ok then
                for _, o in ipairs(placed) do
                    if overlaps(c, o) then
                        ok = false
                        break
                    end
                end
            end
            if ok then
                for _, o in ipairs(icons) do
                    if overlaps(c, o) then
                        ok = false
                        break
                    end
                end
            end
            if ok then
                out[i] = c
                placed[#placed + 1] = c
                break
            end
        end
    end
    return out
end

------------------------------------------------------------------------------------------------------
-- Drawing helpers
------------------------------------------------------------------------------------------------------
local function at(region, point, px, py)
    region:ClearAllPoints()
    region:SetPoint(point, canvas, "TOPLEFT", px, -py)
end

-- A region spanning canvas units [x0, x1] x [y0, y1], both corners anchored: neighbours that share a value share the
-- exact edge.
local function span(region, x0, y0, x1, y1)
    region:ClearAllPoints()
    region:SetPoint("TOPLEFT", canvas, "TOPLEFT", x0, -y0)
    region:SetPoint("BOTTOMRIGHT", canvas, "TOPLEFT", x1, -y1)
end

local function ppu()
    return RS.PxPerUnit(canvas)
end

-- The art of `set` for a ring `d` units across: the line nearest MP.EDGE_UNITS on screen among the sizes that are not
-- minified past MP.MIN_TEXEL_RATIO; none of them: the `fallback` set's (a dashed ring too small for dashes is drawn
-- solid), else the smallest.
local function ringArt(set, d, fallback)
    local s = ppu()
    local px = d * s
    local want = MP.EDGE_UNITS * s
    local best, bestErr
    for _, a in ipairs(set) do
        if a[2] / px <= MP.MIN_TEXEL_RATIO then
            local err = abs(3 * px / a[2] - want)
            if not bestErr or err < bestErr then
                best, bestErr = a, err
            end
        end
    end
    if not best and fallback then
        return ringArt(fallback, d)
    end
    return (best or set[#set])[1]
end

-- The largest art of `set` that is not minified past MP.MIN_TEXEL_RATIO at `px` physical pixels (else the smallest).
local function pickArt(set, px)
    for _, a in ipairs(set) do
        if a[2] / px <= MP.MIN_TEXEL_RATIO then
            return a[1]
        end
    end
    return set[#set][1]
end

local function setFile(t, file, wrap)
    if t.mpFile ~= file then
        t.mpFile = file
        RS.LazyTexture(t, file, wrap)
    end
end

-- A ring `pair` (its line and the dark copy one unit outside it) of radius rpx at (px, py).
local function drawRing(pair, px, py, rpx)
    local d = (px and rpx or 0) * 2
    if d < 3 then
        pair.main:Hide()
        pair.outline:Hide()
        return
    end
    -- a circle smaller than the smallest art allows (the last seconds of overtime) is drawn at that size: a marker
    local small = (pair.fallback or pair.set)
    d = max(d, small[#small][2] / (MP.MIN_TEXEL_RATIO * ppu()))
    local file = ringArt(pair.set, d, pair.fallback)
    setFile(pair.main, file)
    setFile(pair.outline, file)
    at(pair.main, "CENTER", px, py)
    pair.main:SetSize(d, d)
    at(pair.outline, "CENTER", px, py)
    pair.outline:SetSize(d + 2, d + 2)
    pair.main:Show()
    pair.outline:Show()
end

local function newRing(parent, set, color, alpha, fallback)
    local pair = { set = set, fallback = fallback }
    pair.outline = parent:CreateTexture(nil, "BORDER")
    pair.outline:SetVertexColor(0, 0, 0, 0.5)
    pair.outline:Hide()
    pair.main = parent:CreateTexture(nil, "ARTWORK")
    pair.main:SetVertexColor(RS.Rgb(color, alpha))
    pair.main:Hide()
    return pair
end

------------------------------------------------------------------------------------------------------
-- The storm's shade: four rectangles and a hole, snapped, with the hatch over it
------------------------------------------------------------------------------------------------------
local shade = {}
for _, k in ipairs({ "top", "bottom", "left", "right" }) do
    local t = shadeLayer:CreateTexture(nil, "BORDER")
    t:SetTexture(UI.WHITE)
    t:SetVertexColor(RS.Rgb("stormDeep", MP.SHADE_ALPHA))
    t:Hide()
    shade[k] = t
end
shade.hole = shadeLayer:CreateTexture(nil, "BORDER")
shade.hole:SetVertexColor(RS.Rgb("stormDeep", MP.SHADE_ALPHA))
shade.hole:Hide()
MP.shade = shade

local hatch = { rects = {}, strips = {} }
local function newHatch()
    local t = shadeLayer:CreateTexture(nil, "ARTWORK")
    t:SetVertexColor(RS.Rgb("stormLight", MP.HATCH_ALPHA))
    t.rsArt = "Hatch"
    t:Hide()
    return t
end
for i = 1, 4 do
    hatch.rects[i] = newHatch()
end
MP.hatch = hatch

-- The hatch tiled over [x0, x1] x [y0, y1]: texcoords from canvas units, one texel per physical pixel, so the lines
-- stay crisp and continue seamlessly from one piece to the next.
local function hatchSpan(t, x0, y0, x1, y1)
    if x1 - x0 < 0.25 or y1 - y0 < 0.25 then
        t:Hide()
        return
    end
    setFile(t, DATA.files.Hatch, true)
    span(t, x0, y0, x1, y1)
    local k = ppu() / MP.HATCH_TEXELS
    t:SetTexCoord(x0 * k, x1 * k, y0 * k, y1 * k)
    t:Show()
end

local function rect(t, h, x0, y0, x1, y1)
    local L = MP.LIMIT
    x0, y0 = max(x0, -L), max(y0, -L)
    x1, y1 = min(x1, MP.SIZE + L), min(y1, MP.SIZE + L)
    if x1 - x0 < 0.25 or y1 - y0 < 0.25 then
        t:Hide()
        h:Hide()
        return
    end
    span(t, x0, y0, x1, y1)
    t:Show()
    hatchSpan(h, x0, y0, x1, y1)
end

-- The hatch inside the hole's square but outside the circle: horizontal bands, each as wide as the circle's widest
-- point in it, so no line falls inside the circle. The bands are even in angle round the circle (thin where its edge
-- runs flat, at the top and the bottom), so the slivers left beside the edge stay under its line.
local function hatchCorners(x0, y0, x1, y1)
    local n = MP.HATCH_BANDS
    local cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    local rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    local used = 0
    local function strip(a, b, c, d)
        used = used + 1
        local t = hatch.strips[used]
        if not t then
            t = newHatch()
            hatch.strips[used] = t
        end
        hatchSpan(t, a, b, c, d)
    end
    local ya = y0
    for i = 1, 2 * n do
        local yb = i == 2 * n and y1 or (cy - ry * cos(pi * i / (2 * n)))
        -- the circle's half width at the band's edge nearest the centre (as a fraction of the half height)
        local k = (ya < cy and yb > cy) and 0 or min(abs(ya - cy), abs(yb - cy)) / ry
        local w = rx * sqrt(max(0, 1 - k * k))
        strip(x0, ya, cx - w, yb)
        strip(cx + w, ya, x1, yb)
        ya = yb
    end
    for i = used + 1, #hatch.strips do
        hatch.strips[i]:Hide()
    end
end

-- The storm's shade outside the circle at (px, py), radius rpx (canvas units); no circle: none; radius 0: everywhere.
-- Every edge is snapped to whole physical pixels (RS.Snap) once, and each piece takes the same numbers.
function MP.DrawStorm(px, py, rpx)
    local L, N = MP.LIMIT, MP.SIZE + MP.LIMIT
    if not px then
        for _, t in pairs(shade) do
            t:Hide()
        end
        for _, t in ipairs(hatch.rects) do
            t:Hide()
        end
        for _, t in ipairs(hatch.strips) do
            t:Hide()
        end
        MP.shadeEdges = nil
        return
    end
    local H = hatch.rects
    if rpx <= 0.5 then
        rect(shade.top, H[1], -L, -L, N, N)
        shade.bottom:Hide()
        shade.left:Hide()
        shade.right:Hide()
        shade.hole:Hide()
        for i = 2, 4 do
            H[i]:Hide()
        end
        for _, t in ipairs(hatch.strips) do
            t:Hide()
        end
        MP.shadeEdges = nil
        return
    end
    local x0, x1 = RS.Snap(px - rpx, canvas), RS.Snap(px + rpx, canvas)
    local y0, y1 = RS.Snap(py - rpx, canvas), RS.Snap(py + rpx, canvas)
    MP.shadeEdges = { x0 = x0, x1 = x1, y0 = y0, y1 = y1 }
    rect(shade.top, H[1], -L, -L, N, y0)
    rect(shade.bottom, H[2], -L, y1, N, N)
    rect(shade.left, H[3], -L, y0, x0, y1)
    rect(shade.right, H[4], x1, y0, N, y1)
    setFile(shade.hole, pickArt(MP.HOLES, (x1 - x0) * ppu()))
    span(shade.hole, x0, y0, x1, y1)
    shade.hole:Show()
    hatchCorners(x0, y0, x1, y1)
end

local rings = {
    lobby = newRing(ringLayer, MP.RINGS, "blood", 0.85),
    nextc = newRing(ringLayer, MP.DASHED, "safe", 0.95, MP.RINGS),
    cur = newRing(ringLayer, MP.RINGS, "storm", 1),
}
MP.rings = rings

------------------------------------------------------------------------------------------------------
-- The way to the next circle
------------------------------------------------------------------------------------------------------
local path = {}
MP.path = path

local function pathDot(i)
    local d = path[i]
    if not d then
        d = {}
        d.back = pathLayer:CreateTexture(nil, "BORDER")
        d.back:SetTexture(UI.ART .. "Disc")
        d.back:SetSize(MP.PATH_DOT + 3, MP.PATH_DOT + 3)
        d.back:SetVertexColor(0, 0, 0, 0.45)
        d.dot = pathLayer:CreateTexture(nil, "ARTWORK")
        d.dot:SetTexture(UI.ART .. "Disc")
        d.dot:SetSize(MP.PATH_DOT, MP.PATH_DOT)
        d.dot:SetVertexColor(RS.Rgb("safe", 0.85))
        path[i] = d
    end
    return d
end

-- Dots every MP.PATH_STEP units (more spread when the way is long: at most MP.PATH_MAX) from the player at (ax, ay)
-- to the nearest point of the circle (nx, ny, nr); none when the player is inside it. Returns the dots shown.
function MP.DrawPath(ax, ay, nx, ny, nr)
    local n = 0
    if ax and nx then
        local dx, dy = nx - ax, ny - ay
        local dist = sqrt(dx * dx + dy * dy)
        local len = dist - nr
        if len > MP.PATH_STEP and dist > 0 then
            local step = max(MP.PATH_STEP, len / MP.PATH_MAX)
            local ux, uy = dx / dist, dy / dist
            local s = step
            while s <= len + 0.01 and n < MP.PATH_MAX do
                n = n + 1
                local d = pathDot(n)
                local x, y = ax + ux * s, ay + uy * s
                at(d.back, "CENTER", x, y)
                at(d.dot, "CENTER", x, y)
                d.back:Show()
                d.dot:Show()
                s = s + step
            end
        end
    end
    for i = n + 1, #path do
        path[i].back:Hide()
        path[i].dot:Hide()
    end
    MP.pathCount = n
    return n
end

------------------------------------------------------------------------------------------------------
-- Pins, the player, the click
------------------------------------------------------------------------------------------------------
-- own pin: the banner-flag Pin (its tip at the bottom centre) in gold, its place's name above it on a halo; the wish
-- on its way to the server: the hollow pin in parchment (its pole is 35 % from the cell's left)
local pins = {}
pins.pin = RS.Art(topLayer, "Pin", MP.PIN, MP.PIN, "OVERLAY")
pins.pin:SetVertexColor(RS.Rgb("gold"))
pins.pin:Hide()
pins.pending = icon(topLayer, "pinHollow", MP.PIN, "OVERLAY")
pins.pending:SetVertexColor(RS.Rgb("parchment", 0.7))
pins.pending:Hide()
MP.HOLLOW_POLE = 0.35
MP.pins = pins

local function newLabel(parent, size, color)
    local f = CreateFrame("Frame", nil, parent)
    f:SetSize(40, size + 2 * MP.LABEL_PAD)
    f.halo = plate(f, "LabelHalo")
    f.text = text(f, "map", size, color, "CENTER")
    f.text:SetPoint("CENTER", f, "CENTER", 0, 0)
    f:Hide()
    return f
end

-- Sets a label's text and fits its halo; returns its width and height (units).
local function setLabel(f, s)
    UI.SetText(f.text, s or "")
    local w = floor((f.text:GetStringWidth() or 0) + 2 * MP.LABEL_PAD + 0.5)
    local h = floor((select(2, f.text:GetFont()) or MP.LABEL_SIZE) + 2 * MP.LABEL_PAD + 0.5)
    f:SetSize(max(w, 12), h)
    return w, h
end

pins.name = newLabel(topLayer, MP.LABEL_SIZE, "gold")

local you = RS.Rotatable(topLayer, "You", MP.YOU, "OVERLAY")
you:Hide()
MP.arrow = you

-- the ghost pin under the cursor while choosing a landing
local ghost = icon(topLayer, "pinHollow", MP.PIN, "OVERLAY")
ghost:SetVertexColor(RS.Rgb("parchment", 0.35))
ghost:Hide()
MP.ghost = ghost

local shock = RS.Art(fxLayer, "ShockSmall", 72, 72, "OVERLAY")
shock:SetBlendMode("ADD")
shock:SetVertexColor(RS.Rgb("gold"))
shock:Hide()
MP.shock = shock

-- A small shock ring where the player clicked (spreading to 72 units in 0.3 s; never drawn under 48, where its
-- 128-texel art would be minified past 2.2x on a docked 1080p map).
function MP.Shock(px, py)
    RS.Stop(shock)
    at(shock, "CENTER", px, py)
    shock:Show()
    RS.Tween(shock, "size", { 48, 48 }, { 72, 72 }, 0.3, "outCubic")
    RS.Tween(shock, "alpha", 0.7, 0, 0.3, "inCubic", { onDone = function(t) t:Hide() end })
end

-- The pin is locked: by the server (R.CanPin is false), or by this client from T-3.6 (RoyaleCountdown.lua).
function MP.PinLocked(m)
    m = m or R.Match()
    if not m or not R.CanPin(m) then
        return true
    end
    local RC = ns.RoyaleCountdown
    return RC ~= nil and RC.Locked ~= nil and RC.Locked(m) and true or false
end

function MP.OnMapClick(button)
    if button and button ~= "LeftButton" then
        return
    end
    local map = S.royaleMap
    if not map then
        return
    end
    local px, py = MP.CursorPos()
    if not px or px < 0 or py < 0 or px > MP.SIZE or py > MP.SIZE then
        return
    end
    local m = R.Match()
    if MP.PinLocked(m) then
        -- in the lobby a locked pin says so (the server's sentence); in the fight a click on the map is just a look
        if m and R.InLobby(m) then
            R.Notice("royale_phase")
        end
        return
    end
    local x, y = MP.ToWorld(px, py, map)
    if R.SetPin(x, y) then
        MP.Shock(px, py)
    end
end

canvas:SetScript("OnMouseUp", function(self, button)
    MP.OnMapClick(button)
end)
canvas:SetScript("OnEnter", function()
    MP.hover = true
end)
canvas:SetScript("OnLeave", function()
    MP.hover = nil
    ghost:Hide()
    MP.ghostPlace = nil
    if GameTooltip and GameTooltip:IsOwned(canvas) then
        GameTooltip:Hide()
    end
end)

-- The ghost pin and "Land near ..." while the cursor is over the canvas and a landing can be chosen.
function MP.UpdateGhost()
    local m = R.Match()
    local px, py
    if MP.hover and S.royaleMap and not MP.PinLocked(m) then
        px, py = MP.CursorPos()
    end
    if not px or px < 0 or py < 0 or px > MP.SIZE or py > MP.SIZE then
        if ghost:IsShown() then
            ghost:Hide()
            MP.ghostPlace = nil
            if GameTooltip and GameTooltip:IsOwned(canvas) then
                GameTooltip:Hide()
            end
        end
        return
    end
    at(ghost, "BOTTOM", px + (0.5 - MP.HOLLOW_POLE) * MP.PIN, py)
    ghost:Show()
    local place = MP.NearestPlace(MP.ToWorld(px, py))
    if place ~= MP.ghostPlace and GameTooltip then
        MP.ghostPlace = place
        GameTooltip:SetOwner(canvas, "ANCHOR_CURSOR")
        GameTooltip:AddLine(place == "the wilds" and "Land in the wilds" or ("Land near " .. U.Safe(place)),
            RS.Rgb("parchment"))
        GameTooltip:Show()
    end
end

------------------------------------------------------------------------------------------------------
-- Places (ROYM)
------------------------------------------------------------------------------------------------------
local function hideTooltip()
    if GameTooltip then
        GameTooltip:Hide()
    end
end

local function poiTooltip(self)
    local p = self.poi
    if not p then
        return
    end
    local lines = { U.Safe(p.name or "?") }
    if p.kind == "C" then
        lines[#lines + 1] = { "A crossing over the river", RS.C.ash }
    elseif p.kind == "Y" then
        lines[#lines + 1] = { "The lobby. Fighters may not enter.", RS.C.blood, true }
    end
    if p.kind ~= "Y" and not MP.PinLocked() then
        lines[#lines + 1] = { "Click to land here.", RS.C.smoke }
    end
    UI.ShowTooltip(self, lines)
    if p.kind == "C" and self.label.mpRect then
        self.label:Show()
    end
end

local function poiLeave(self)
    hideTooltip()
    if self.poi and self.poi.kind == "C" then
        self.label:Hide()
    end
end

local pois = UI.Pool(function()
    local f = CreateFrame("Frame", nil, poiLayer)
    f:SetSize(MP.ICON_LANDMARK, MP.ICON_LANDMARK)
    f:EnableMouse(true)
    f.icon = icon(f, "landmark", MP.ICON_LANDMARK, "ARTWORK")
    f.icon:SetPoint("CENTER", f, "CENTER", 0, 0)
    f.label = newLabel(labelLayer, MP.LABEL_SIZE, "mapLabel")
    f:SetScript("OnEnter", poiTooltip)
    f:SetScript("OnLeave", poiLeave)
    f:SetScript("OnMouseUp", function(self, button)
        MP.OnMapClick(button)
    end)
    return f
end)
MP.pois = pois

-- The scale bar: MP.SCALE_YARDS of the picture, bottom-left on a soft dark pill.
local scale = CreateFrame("Frame", nil, dressLayer)
scale:SetSize(100, 22)
scale:SetPoint("BOTTOMLEFT", canvas, "BOTTOMLEFT", 10, 10)
scale.halo = plate(scale, "LabelHalo")
scale.bar = scale:CreateTexture(nil, "ARTWORK")
scale.bar:SetTexture(UI.WHITE)
scale.bar:SetVertexColor(RS.Rgb("bronze"))
scale.ends = {}
for i = 1, 2 do
    local t = scale:CreateTexture(nil, "ARTWORK")
    t:SetTexture(UI.WHITE)
    t:SetVertexColor(RS.Rgb("bronze"))
    t:SetSize(2, 6)
    scale.ends[i] = t
end
scale.label = text(scale, "map", MP.CROSSING_SIZE, "parchment", "LEFT")
scale.label:SetText(MP.SCALE_YARDS .. " yd")
MP.scaleBar = scale

local function layoutScale(map)
    local len = floor(MP.Yards(MP.SCALE_YARDS, map) + 0.5)
    scale.bar:SetSize(len, 2)
    scale.bar:ClearAllPoints()
    scale.bar:SetPoint("LEFT", scale, "LEFT", 8, 0)
    scale.ends[1]:ClearAllPoints()
    scale.ends[1]:SetPoint("CENTER", scale.bar, "LEFT", 1, 0)
    scale.ends[2]:ClearAllPoints()
    scale.ends[2]:SetPoint("CENTER", scale.bar, "RIGHT", -1, 0)
    scale.label:ClearAllPoints()
    scale.label:SetPoint("LEFT", scale.bar, "RIGHT", 6, 0)
    scale:SetWidth(floor(8 + len + 6 + (scale.label:GetStringWidth() or 0) + 8 + 0.5))
end

-- The scale bar's rectangle in canvas units (labels keep off it).
local function scaleRect()
    local w, h = scale:GetWidth(), scale:GetHeight()
    return { l = 10, t = MP.SIZE - 10 - h, r = 10 + w, b = MP.SIZE - 10 }
end

-- Lays the place labels out (on ROYM only): the lobby, then landmarks by radius (largest first), then crossings;
-- crossings show their name on hover only.
function MP.PlaceLabels()
    local map = S.royaleMap
    local order = {}
    for i = 1, pois.used do
        local f = pois.items[i]
        order[#order + 1] = f
    end
    local rank = { Y = 1, L = 2, C = 3 }
    table.sort(order, function(a, b)
        local ka, kb = rank[a.poi.kind] or 4, rank[b.poi.kind] or 4
        if ka ~= kb then
            return ka < kb
        end
        if (a.poi.r or 0) ~= (b.poi.r or 0) then
            return (a.poi.r or 0) > (b.poi.r or 0)
        end
        return (a.poi.id or 0) < (b.poi.id or 0)
    end)
    local list = {}
    for i, f in ipairs(order) do
        local w, h = setLabel(f.label, f.poi.name)
        local px, py = MP.ToMap(f.poi.x, f.poi.y, map)
        list[i] = { x = px, y = py, icon = f.size, w = w, h = h }
    end
    local rects = MP.LayoutLabels(list, { scaleRect() })
    MP.labelList, MP.labelRects = list, rects
    for i, f in ipairs(order) do
        local r = rects[i]
        f.label.mpRect = r or nil
        if r then
            f.label:ClearAllPoints()
            f.label:SetPoint("TOPLEFT", canvas, "TOPLEFT", r.l, -r.t)
        end
    end
    MP.ShowPlaceLabels(MP.labelExcept)
end

-- Shows the laid-out labels of landmarks and the lobby, except the place named `except` (the own pin's).
function MP.ShowPlaceLabels(except)
    MP.labelExcept = except
    for i = 1, pois.used do
        local f = pois.items[i]
        local p = f.poi
        if f.label.mpRect and p.kind ~= "C" and (p.name or "") ~= "" and p.name ~= except then
            f.label:Show()
        else
            f.label:Hide()
        end
    end
end

function MP.RefreshPlaces()
    for i = 1, #pois.items do
        pois.items[i].label:Hide()
    end
    pois:ReleaseAll()
    pins.name.mpFor, MP.labelExcept = nil, nil
    local map = S.royaleMap
    local hasPicture = map and map.mapId == R.MAP_ID
    shown(canvas.pic, hasPicture and true or false)
    shown(canvas.none, map ~= nil and not hasPicture)
    if not map then
        drawRing(rings.lobby, nil)
        scale:Hide()
        return
    end
    layoutScale(map)
    scale:Show()
    for _, p in ipairs(map.pois) do
        local f = pois:Acquire()
        f.poi = p
        local px, py = MP.ToMap(p.x, p.y, map)
        local size, name, color = MP.ICON_LANDMARK, "landmark", "mapLabel"
        if p.kind == "Y" then
            size, name, color = MP.ICON_LOBBY, "lobby", "blood"
        elseif p.kind == "C" then
            size, name = MP.ICON_CROSSING, "crossing"
        end
        f.size = size
        f:SetSize(size, size)
        f.icon:SetIcon(name)
        f.icon:SetIconSize(size)
        f.icon:SetVertexColor(RS.Rgb(p.kind == "Y" and "FFB4A8" or "safe"))
        f.label.text:SetTextColor(RS.Rgb(color))
        font(f.label.text, "map", p.kind == "C" and MP.CROSSING_SIZE or MP.LABEL_SIZE)
        f:ClearAllPoints()
        f:SetPoint("CENTER", canvas, "TOPLEFT", px, -py)
    end
    MP.PlaceLabels()
    if map.lobbyX and (map.lobbyR or 0) > 0 then
        local px, py = MP.ToMap(map.lobbyX, map.lobbyY, map)
        drawRing(rings.lobby, px, py, MP.Yards(map.lobbyR, map))
    else
        drawRing(rings.lobby, nil)
    end
end

------------------------------------------------------------------------------------------------------
-- Orbs and supply drops (ROYO), supply pings (ROYV D and L)
------------------------------------------------------------------------------------------------------
function MP.ObjectStyle(o)
    return MP.OBJECT_STYLE[o.kind == "B" and ("B" .. (o.subtype or 0)) or o.kind] or MP.OBJECT_STYLE.S
end
local objectStyle = MP.ObjectStyle

-- The words before a state's time ("Lands in "), by kind where a kind says it its own way (the beast wakes).
local function stateWhen(o)
    local own = MP.KIND_STATE_WHEN and MP.KIND_STATE_WHEN[o.kind]
    if own then
        return own[o.state]
    end
    return MP.STATE_WHEN[o.state]
end

-- "Lands in 0:20", "Back in 0:45", "Appears in 0:30", "Wakes in 0:24", or the state's word.
function MP.ObjectState(o)
    local left = ns.RoyaleLeft(o.msLeft, o.recvAt)
    local when = stateWhen(o)
    if left and left > 0 and when then
        return when .. RS.Clock(left)
    end
    local own = MP.KIND_STATE_TEXT and MP.KIND_STATE_TEXT[o.kind]
    return (own and own[o.state]) or MP.STATE_TEXT[o.state] or ""
end

local function objectTooltip(self)
    local o = self.obj
    if not o then
        return
    end
    local st = objectStyle(o)
    UI.ShowTooltip(self, { st.name, { st.text, RS.C.ash, true }, { MP.ObjectState(o), RS.C.gold } })
end

local objects = UI.Pool(function()
    local f = CreateFrame("Frame", nil, objLayer)
    f:SetSize(MP.ICON_OBJECT + 2, MP.ICON_OBJECT + 2)
    f:EnableMouse(true)
    f.ping = f:CreateTexture(nil, "BACKGROUND")
    f.ping:SetPoint("CENTER", f, "CENTER", 0, 0)
    f.ping:Hide()
    f.icon = icon(f, "orbSpeed", MP.ICON_OBJECT, "ARTWORK")
    f.icon:SetPoint("CENTER", f, "CENTER", 0, 0)
    f.timer = text(f, "map", 10, "parchment", "CENTER")
    f.timer:SetPoint("TOP", f, "BOTTOM", 0, 1)
    f:SetScript("OnEnter", objectTooltip)
    f:SetScript("OnLeave", hideTooltip)
    f:SetScript("OnMouseUp", function(self, button)
        MP.OnMapClick(button)
    end)
    return f
end)
MP.objects = objects

-- The supply drop of a ROYV D (coming down) or L (landed) that ROYO has not listed: pinged for a while.
local eventPing

ns.On("ROYALE_EVENT", function(e)
    if (e.kind == "D" or e.kind == "L") and e.x then
        eventPing = { x = e.x, y = e.y, kind = e.kind, msLeft = e.msLeft, recvAt = e.recvAt,
            untilAt = GetTime() + (e.kind == "D" and ((e.msLeft or 20000) / 1000 + 8) or 10) }
    elseif e.kind == "O" then
        eventPing = nil
    end
    if win:IsShown() then
        MP.RefreshObjects()
    end
end)

function MP.RefreshObjects()
    objects:ReleaseAll()
    local map = S.royaleMap
    if not map then
        return
    end
    local list = {}
    local store = S.royaleObjects
    local m = S.royale
    if store and m and store.matchId == m.matchId then
        for _, o in ipairs(store.list) do
            list[#list + 1] = o
        end
    end
    local p = eventPing
    if p and GetTime() < p.untilAt then
        local listed = false
        for _, o in ipairs(list) do
            if o.kind == "D" and abs(o.x - p.x) < 5 and abs(o.y - p.y) < 5 then
                listed = true
            end
        end
        if not listed then
            list[#list + 1] = { id = -1, kind = "D", subtype = 0, x = p.x, y = p.y, state = p.kind == "D" and 3 or 1,
                msLeft = p.msLeft, recvAt = p.recvAt }
        end
    end
    local beast
    for _, o in ipairs(list) do
        local hidden = o.state == 0 and not o.msLeft
        if o.kind == "H" then
            MP.NoteBoss()        -- its hoard: the beast was announced (the legend after a /reload)
        end
        if o.kind == "X" then
            beast = o            -- the storm beast has a marker of its own (MP.PlaceBoss)
        elseif not hidden then
            local f = objects:Acquire()
            f.obj = o
            local st = objectStyle(o)
            local px, py = MP.ToMap(o.x, o.y, map)
            f:ClearAllPoints()
            f:SetPoint("CENTER", canvas, "TOPLEFT", px, -py)
            f.icon:SetIcon(st.icon)
            local dim = o.state == 0 or o.state == 2 or o.state == 4
            RS.Desaturate(f.icon, dim)
            f:SetAlpha(dim and 0.6 or 1)
            f.ping:SetVertexColor(RS.Rgb(st.color or "gold"))
            f.ping:Hide()
        end
    end
    MP.PlaceBoss(beast, map)
    MP.UpdateObjects()
    MP.DimCoveredLabels()
end

-- A place label under an object (its icon, or its timer) fades, so the object and its time read clearly; the labels
-- themselves keep their places (laid out on ROYM only).
function MP.DimCoveredLabels()
    local rects = {}
    for i = 1, objects.used do
        local f = objects.items[i]
        local _, _, _, x, y = f:GetPoint(1)
        if x then
            local h = MP.ICON_OBJECT / 2
            local r = { l = x - h, t = -y - h, r = x + h, b = -y + h }
            if f.timer:IsShown() then
                local tw = (f.timer:GetStringWidth() or 0) / 2 + 2
                r.l, r.r, r.b = min(r.l, x - tw), max(r.r, x + tw), r.b + 13
            end
            rects[#rects + 1] = r
        end
    end
    local beast = MP.BossRect()
    if beast then
        rects[#rects + 1] = beast
    end
    for i = 1, pois.used do
        local label = pois.items[i].label
        local rr = label.mpRect
        local covered = false
        if rr then
            for _, o in ipairs(rects) do
                if overlaps(rr, o) then
                    covered = true
                    break
                end
            end
        end
        label:SetAlpha(covered and 0.3 or 1)
    end
end

-- Timers under the objects and the supply ping, a few times a second.
function MP.UpdateObjects()
    local now = GetTime()
    local changed = false
    for i = 1, objects.used do
        local f = objects.items[i]
        local o = f.obj
        local left = o and ns.RoyaleLeft(o.msLeft, o.recvAt)
        if left and left > 0 and stateWhen(o) then
            local s = RS.Clock(left)
            if f.timer.mpText ~= s then
                f.timer.mpText = s
                f.timer:SetText(s)
            end
            if not f.timer:IsShown() then
                f.timer:Show()
                changed = true
            end
        elseif f.timer:IsShown() then
            f.timer:Hide()
            changed = true
        end
        if o and ((o.kind == "D" and (o.state == 3 or o.state == 1)) or (o.kind == "H" and o.state == 1)) then
            -- a ring spreading from the cache (or the beast's unopened hoard), the ring art drawn nearest its size
            local k = (now * 0.8) % 1
            local d = 22 + 38 * k
            setFile(f.ping, ringArt(MP.RINGS, d))
            f.ping:SetSize(d, d)
            f.ping:SetAlpha(0.9 * (1 - k))
            f.ping:Show()
        else
            f.ping:Hide()
        end
    end
    if MP.AnimateBoss(now) then
        changed = true
    end
    if changed then
        MP.DimCoveredLabels()
    end
end

------------------------------------------------------------------------------------------------------
-- The storm beast (ROYO X) and its hoard (H)
------------------------------------------------------------------------------------------------------
-- While it stirs (state 3) its den carries the green beam the island sees in the sky: a shaft of light rising from
-- the den, a ring spreading at its foot, and the time until it wakes. Awake (1) it is the horned skull in a pulsing
-- ring with its health under it; slain or fled (0) it leaves the map. Its hoard is a chest pinged in gold until it is
-- opened (then dimmed); gone unopened (0) it leaves the map. The legend's Boss entry shows once the beast has been
-- announced: ROYV B (or A, K, F), or an X or H in ROYO after a /reload. Built in a function: the file's main chunk is
-- past 256 constants, where the client's Lua 5.1 miscompiles some arithmetic (test_royale_hud.lua explains it).
local function buildBoss()
    MP.BOSS = { icon = 22, ring = 30, disc = 26, barW = 28, barH = 4, barGap = 2, beamW = 10, coreW = 3,
        shadowW = 16, beamH = 60, glow = 40, aura = 0.6, auraSize = 60, pingFrom = 26, pingTo = 62,
        pulse = { from = 0.45, to = 1, duration = 0.9 }, still = 0.8 }
    local BS = MP.BOSS
    MP.BOSS_EVENTS = { B = true, A = true, K = true, F = true }
    MP.OBJECT_STYLE.X = { icon = "beast", color = "beast", name = "Thundermaw",
        text = "A storm-touched devilsaur. Its hoard is anyone's." }
    MP.OBJECT_STYLE.H = { icon = "hoard", color = "gold", name = "Thundermaw's Hoard",
        text = "Rare loot. Opening it takes a few seconds; damage stops you." }
    MP.KIND_STATE_WHEN = { X = { [3] = "Wakes in " }, H = {} }
    MP.KIND_STATE_TEXT = { X = { [0] = "Gone", [1] = "Awake", [3] = "Stirring" },
        H = { [0] = "Gone", [1] = "Ready to open", [4] = "Opened" } }
    MP.BEAM_TEXT = "A green beam marks its den."

    local b = CreateFrame("Frame", nil, objLayer)
    b:SetSize(BS.ring, BS.ring)
    b:EnableMouse(true)
    b:Hide()
    MP.bossMarker = b
    local r, g, bl = RS.Rgb("beast")
    -- bottom: a soft glow round the den (the beam's foot, the awake beast's aura) and the ring spreading from it,
    -- then the beam: beast green fading upwards over a dark shadow (so it reads over the bright island), and a pale
    -- core of light
    b.glow = RS.Art(b, "GemGlow", BS.glow, BS.glow, "BACKGROUND")
    b.glow:SetBlendMode("ADD")
    b.glow:SetVertexColor(r, g, bl)
    b.glow:SetPoint("CENTER", b, "CENTER", 0, 0)
    b.ping = b:CreateTexture(nil, "BACKGROUND")
    b.ping:SetBlendMode("ADD")
    b.ping:SetVertexColor(r, g, bl)
    b.ping:SetPoint("CENTER", b, "CENTER", 0, 0)
    b.ping:Hide()
    b.shadow = b:CreateTexture(nil, "BORDER")
    b.shadow:SetTexture(UI.WHITE)
    b.shadow:SetSize(BS.shadowW, BS.beamH)
    b.shadow:SetPoint("BOTTOM", b, "CENTER", 0, 0)
    b.shadow:SetGradientAlpha("VERTICAL", 0, 0, 0, 0.4, 0, 0, 0, 0)
    b.beam = b:CreateTexture(nil, "ARTWORK")
    b.beam:SetTexture(UI.WHITE)
    b.beam:SetSize(BS.beamW, BS.beamH)
    b.beam:SetPoint("BOTTOM", b, "CENTER", 0, 0)
    b.beam:SetGradientAlpha("VERTICAL", r, g, bl, 0.9, r, g, bl, 0)
    b.core = b:CreateTexture(nil, "OVERLAY")
    b.core:SetTexture(UI.WHITE)
    b.core:SetBlendMode("ADD")
    b.core:SetSize(BS.coreW, BS.beamH)
    b.core:SetPoint("BOTTOM", b, "CENTER", 0, 0)
    b.core:SetGradientAlpha("VERTICAL", 0.9, 1, 0.8, 0.9, r, g, bl, 0)
    -- one frame level up: the token, a dark medallion in a beast-green ring with a dark outline
    local token = CreateFrame("Frame", nil, b)
    token:SetAllPoints(b)
    token:SetFrameLevel(b:GetFrameLevel() + 1)
    b.token = token
    b.outline = token:CreateTexture(nil, "BACKGROUND")
    b.outline:SetVertexColor(0, 0, 0, 0.6)
    b.outline:SetPoint("CENTER", b, "CENTER", 0, 0)
    b.disc = token:CreateTexture(nil, "BORDER")
    b.disc:SetTexture(UI.ART .. "Disc")
    b.disc:SetSize(BS.disc, BS.disc)
    b.disc:SetVertexColor(RS.Rgb(MP.INK, 0.75))
    b.disc:SetPoint("CENTER", b, "CENTER", 0, 0)
    b.ring = token:CreateTexture(nil, "ARTWORK")
    b.ring:SetVertexColor(r, g, bl)
    b.ring:SetPoint("CENTER", b, "CENTER", 0, 0)
    -- over them: the skull, its health bar and the time until it wakes
    local fg = CreateFrame("Frame", nil, b)
    fg:SetAllPoints(b)
    fg:SetFrameLevel(b:GetFrameLevel() + 2)
    b.fg = fg
    b.icon = icon(fg, "beast", BS.icon, "ARTWORK")
    b.icon:SetPoint("CENTER", b, "CENTER", 0, 0)
    b.hpBack = fg:CreateTexture(nil, "BACKGROUND")
    b.hpBack:SetTexture(UI.WHITE)
    b.hpBack:SetVertexColor(RS.Rgb(MP.INK, 0.85))
    b.hpBack:SetPoint("TOP", b, "CENTER", 0, -(BS.ring / 2 + BS.barGap))
    b.hpTrack = fg:CreateTexture(nil, "BORDER")
    b.hpTrack:SetTexture(UI.WHITE)
    b.hpTrack:SetVertexColor(r * 0.28, g * 0.28, bl * 0.28, 1)
    b.hpTrack:SetPoint("CENTER", b.hpBack, "CENTER", 0, 0)
    b.hpFill = fg:CreateTexture(nil, "ARTWORK")
    b.hpFill:SetTexture(UI.WHITE)
    b.hpFill:SetGradientAlpha("VERTICAL", r * 0.7, g * 0.7, bl * 0.7, 1, min(1, r * 1.2), min(1, g * 1.15), bl, 1)
    b.hpFill:SetPoint("LEFT", b.hpTrack, "LEFT", 0, 0)
    b.timer = text(fg, "map", 10, "parchment", "CENTER")
    b.timer:SetPoint("TOP", b, "CENTER", 0, -(BS.ring / 2))
    b.timer:Hide()

    -- the bar on whole pixels (a 1-pixel dark frame round it), its fill in whole pixels of it
    local function healthBar(o)
        local px = 1 / ppu()
        local pct = U.Clamp(o.subtype or 0, 0, 100)
        local tw, th = RS.Snap(BS.barW, canvas), RS.Snap(BS.barH, canvas)
        b.hpBack:SetSize(tw + 2 * px, th + 2 * px)
        b.hpTrack:SetSize(tw, th)
        local w = RS.Snap(tw * pct / 100, canvas)
        b.hpFill:SetSize(max(w, px), th)
        shown(b.hpFill, w > 0)
        b.hpBack:Show()
        b.hpTrack:Show()
        b.pct = pct
    end

    local function hideHealth()
        b.hpBack:Hide()
        b.hpTrack:Hide()
        b.hpFill:Hide()
        b.pct = nil
    end

    -- "Awake · 57% health"
    function MP.BossHealthText(o)
        return strformat("Awake · %d%% health", U.Clamp(o.subtype or 0, 0, 100))
    end

    b:SetScript("OnEnter", function(self)
        local o = self.obj
        if not o then
            return
        end
        local st = MP.OBJECT_STYLE.X
        local lines = { { st.name, RS.C.beast }, { st.text, RS.C.ash, true } }
        if o.state == 3 then
            lines[#lines + 1] = { MP.BEAM_TEXT, RS.C.beast, true }
            lines[#lines + 1] = { MP.ObjectState(o), RS.C.gold }
        else
            lines[#lines + 1] = { MP.BossHealthText(o), RS.C.gold }
        end
        UI.ShowTooltip(self, lines)
    end)
    b:SetScript("OnLeave", hideTooltip)
    b:SetScript("OnMouseUp", function(self, button)
        MP.OnMapClick(button)
    end)

    -- The Boss entry of the legend, once the beast has been announced this match.
    function MP.NoteBoss()
        if not MP.bossKnown then
            MP.bossKnown = true
            MP.LayoutLegend()
        end
    end

    -- The storm beast's ROYO object (kind X; `kind` H for its hoard) of the match `m` (the one now), or nil.
    function MP.BossObject(m, kind)
        m = m or R.Match()
        local store = S.royaleObjects
        if not (m and store and store.matchId == m.matchId) then
            return nil
        end
        kind = kind or "X"
        for _, o in ipairs(store.list) do
            if o.kind == kind then
                return o
            end
        end
        return nil
    end

    -- The beast's marker for its ROYO object `o` (stirring or awake; anything else hides it).
    function MP.PlaceBoss(o, map)
        b.obj = o
        local state = o and o.state
        if not (o and map and (state == 1 or state == 3)) then
            b:Hide()
            b.ping:Hide()
            return
        end
        MP.NoteBoss()
        local px, py = MP.ToMap(o.x, o.y, map)
        b:ClearAllPoints()
        b:SetPoint("CENTER", canvas, "TOPLEFT", px, -py)
        b:Show()
        local stirring = state == 3
        shown(b.shadow, stirring)
        shown(b.beam, stirring)
        shown(b.core, stirring)
        local file = ringArt(MP.RINGS, BS.ring)
        setFile(b.ring, file)
        setFile(b.outline, file)
        b.ring:SetSize(BS.ring, BS.ring)
        b.outline:SetSize(BS.ring + 2, BS.ring + 2)
        b.icon:SetAlpha(stirring and 0.85 or 1)
        if stirring then
            -- asleep: the token still, the beam over it, the glow at its foot
            b.glow:SetSize(BS.glow, BS.glow)
            hideHealth()
            RS.StopLoop(b.ring, "pulse")
            b.ring:SetAlpha(0.7)
        else
            -- awake: a wide aura round the token
            b.glow:SetSize(BS.auraSize, BS.auraSize)
            b.glow:SetAlpha(BS.aura)
            healthBar(o)
            -- the ring breathes (an animation group: started again after the window was hidden, which stops it)
            if not (b.pulse and b.pulse:IsPlaying()) then
                b.pulse = RS.Loop(b.ring, "pulse", BS.pulse)
                if not RS.Motion() then
                    b.ring:SetAlpha(BS.still)
                end
            end
        end
        MP.AnimateBoss(GetTime())
    end

    -- The stirring beast's spreading ring and its time, a few times a second; true when the time showed or hid.
    function MP.AnimateBoss(now)
        local o = b.obj
        if not (o and b:IsShown()) then
            return false
        end
        local changed = false
        local left = o.state == 3 and ns.RoyaleLeft(o.msLeft, o.recvAt)
        if o.state == 3 then
            -- reduced motion: a still ring half way out
            local k = RS.Motion() and ((now * 0.8) % 1) or 0.5
            local d = BS.pingFrom + (BS.pingTo - BS.pingFrom) * k
            setFile(b.ping, ringArt(MP.RINGS, d))
            b.ping:SetSize(d, d)
            b.ping:SetAlpha(0.85 * (1 - k))
            b.ping:Show()
            b.glow:SetAlpha(0.3 + 0.3 * (1 - k))
        else
            b.ping:Hide()
        end
        if left and left > 0 then
            local s = RS.Clock(left)
            if b.timer.mpText ~= s then
                b.timer.mpText = s
                b.timer:SetText(s)
            end
            if not b.timer:IsShown() then
                b.timer:Show()
                changed = true
            end
        elseif b.timer:IsShown() then
            b.timer:Hide()
            changed = true
        end
        return changed
    end

    -- The marker's rectangle in canvas units (y down), with its time or health under it; nil while hidden.
    function MP.BossRect()
        if not b:IsShown() then
            return nil
        end
        local _, _, _, x, y = b:GetPoint(1)
        if not x then
            return nil
        end
        local h = BS.ring / 2
        local below = (b.timer:IsShown() or b.hpBack:IsShown()) and 12 or 0
        return { l = x - h, t = -y - h, r = x + h, b = -y + h + below }
    end

    ns.On("ROYALE_EVENT", function(e)
        if MP.BOSS_EVENTS[e.kind] then
            MP.NoteBoss()
        end
    end)
    ns.On("ROYALE_MATCH", function()
        MP.bossKnown = nil
        MP.LayoutLegend()
    end)
end
buildBoss()

------------------------------------------------------------------------------------------------------
-- Storm, pins, the player, the way (redrawn while the map is shown)
------------------------------------------------------------------------------------------------------
-- Places a region only when its spot changed (a running drop-in tween keeps its own offset meanwhile).
local function place(t, point, px, py)
    if t.mpX ~= px or t.mpY ~= py or not t:IsShown() then
        t.mpX, t.mpY = px, py
        at(t, point, px, py)
    end
    t:Show()
end

local function forget(t)
    t.mpX, t.mpY = nil, nil
    t:Hide()
end

local function hideLive()
    MP.DrawStorm(nil)
    drawRing(rings.cur, nil)
    drawRing(rings.nextc, nil)
    if rings.nextc.spinning then
        rings.nextc.spinning = false
        RS.StopLoop(rings.nextc.main, "spin")
        RS.StopLoop(rings.nextc.outline, "spin")
    end
    forget(pins.pin)
    forget(pins.pending)
    pins.name:Hide()
    forget(you)
    MP.DrawPath(nil)
    MP.drawn = nil
end

function MP.UpdateLive()
    local map = S.royaleMap
    local m = R.Match()
    if not map or not m then
        hideLive()
        return
    end
    -- the storm (drawn again only when it moved or the pixel size changed)
    local cx, cy, cr, moving = R.Circle(m)
    local px, py = MP.ToMap(cx, cy, map)
    local rpx = MP.Yards(cr, map)
    local key = strformat("%.2f %.2f %.2f %.4f %s %s %s %s", px, py, rpx, ppu(), tostring(m.nextX),
        tostring(m.nextY), tostring(m.nextR), tostring(moving))
    if MP.drawn ~= key then
        MP.drawn = key
        MP.DrawStorm(px, py, rpx)
        drawRing(rings.cur, px, py, rpx)
        if m.nextR then
            local nx, ny = MP.ToMap(m.nextX, m.nextY, map)
            drawRing(rings.nextc, nx, ny, MP.Yards(m.nextR, map))
        else
            drawRing(rings.nextc, nil)
        end
        -- the next circle's dashes (and their dark copy) turn while the storm moves towards it, one turn a minute
        local spin = (moving and m.nextR) and true or false
        if spin ~= rings.nextc.spinning then
            rings.nextc.spinning = spin
            for _, t in ipairs({ rings.nextc.main, rings.nextc.outline }) do
                if spin then
                    RS.Loop(t, "spin", { duration = 60 })
                else
                    RS.StopLoop(t, "spin")
                end
            end
        end
    end
    -- the landing pin: the server's (snapped), and the wish on its way
    local inLobby = R.InLobby(m)
    if inLobby and m.pinX then
        local ox, oy = MP.ToMap(m.pinX, m.pinY, map)
        place(pins.pin, "BOTTOM", ox, oy)
        if pins.name.mpFor ~= m.pinX .. "," .. m.pinY then
            pins.name.mpFor = m.pinX .. "," .. m.pinY
            local where = MP.NearestPlace(m.pinX, m.pinY, map)
            setLabel(pins.name, where == "the wilds" and "The wilds" or where)
            MP.ShowPlaceLabels(where)      -- the pin's gold name stands in for its place's label
        end
        pins.name:ClearAllPoints()
        pins.name:SetPoint("BOTTOM", canvas, "TOPLEFT", ox, -(oy - MP.PIN - 1))
        pins.name:Show()
    elseif pins.name.mpFor then
        pins.name.mpFor = nil
        forget(pins.pin)
        pins.name:Hide()
        MP.ShowPlaceLabels(nil)
    else
        forget(pins.pin)
        pins.name:Hide()
    end
    local pend = R.pendingPin
    if inLobby and pend and pend.matchId == m.matchId then
        local qx, qy = MP.ToMap(pend.x, pend.y, map)
        local fresh = not pins.pending:IsShown() or pins.pending.mpAt ~= pend.at
        pins.pending.mpAt = pend.at
        place(pins.pending, "BOTTOM", qx + (0.5 - MP.HOLLOW_POLE) * MP.PIN, qy)
        if fresh then
            -- the wish drops in
            RS.Tween(pins.pending, "offset", { 0, 16 }, { 0, 0 }, 0.18, "outBack")
        end
    else
        forget(pins.pending)
    end
    -- the player and the way to the next circle
    local x, y = R.MyPos()
    if x and m.me ~= R.ME.SPECTATING and m.me ~= R.ME.LEFT then
        local ax, ay = MP.ToMap(x, y, map)
        place(you, "CENTER", ax, ay)
        local facing = R.Facing() or 0
        if not you.mpFacing or abs(you.mpFacing - facing) > 0.005 then
            you.mpFacing = facing
            you:SetAngle(facing)
        end
        if m.nextR and m.me == R.ME.ALIVE and R.Fighting(m) then
            local nx, ny = MP.ToMap(m.nextX, m.nextY, map)
            MP.DrawPath(ax, ay, nx, ny, MP.Yards(m.nextR, map))
        else
            MP.DrawPath(nil)
        end
    else
        forget(you)
        MP.DrawPath(nil)
    end
end

-- The status line under the map: left (what to do or what comes), right (the circle).
function MP.StatusText(m)
    if not m then
        return "", ""
    end
    local right = ""
    local total = R.StageCount(m)
    if R.Overtime(m) then
        right = "Final storm"
    elseif (m.stage or 0) > 0 then
        right = strformat("Circle %d of %d", m.stage, total)
    elseif m.nextR then
        right = strformat("Circle 1 of %d", total)
    end
    if R.InLobby(m) then
        if m.me ~= R.ME.LOBBY then
            return "", right
        end
        if MP.PinLocked(m) then
            return "Landing locked", right
        end
        local lock = R.PinsLockIn(m)
        local RC = ns.RoyaleCountdown
        if lock and RC and RC.LOCK_AT then
            lock = max(0, lock - (RC.LOCK_AT - R.PIN_LOCK))   -- this client locks 0.6 s before the server
        end
        if lock and lock <= 10 then
            return "Landing locks in " .. RS.Clock(lock), right
        end
        return "Click to choose your landing.", right
    end
    if m.phase >= R.PHASE.VICTORY then
        return m.phase == R.PHASE.CANCELLED and "The match was cancelled." or "The match is over.", right
    end
    if m.me == R.ME.DROPPING then
        local left = ns.RoyaleLeft(m.landMsLeft, m.recvAt)
        return left and ("Landing in " .. RS.Clock(left)) or "Dropping", right
    end
    if m.me == R.ME.SPECTATING and m.watchName then
        return "Watching " .. m.watchName, right
    end
    local what, sec = R.StormTimer(m)
    if what == "hold" then
        return "Storm closes in " .. RS.Clock(sec), right
    elseif what == "moving" then
        return "Storm closing " .. RS.Clock(sec), right
    elseif R.Overtime(m) then
        return "The storm has closed.", right
    end
    return "", right
end

local function setIf(fs, s, safe)
    if fs.mpText ~= s then
        fs.mpText = s
        if safe then
            UI.SetText(fs, s)
        else
            fs:SetText(s)
        end
    end
end

function MP.Update()
    MP.UpdateLive()
    local m = R.Match()
    local left, right = MP.StatusText(m)
    setIf(foot.left, left, true)
    setIf(foot.right, right)
    if m then
        local s = strformat("%d/%d %s", m.alive or 0, m.total or 0, R.InLobby(m) and "PLAYERS" or "ALIVE")
        if pill.text.mpText ~= s then
            setIf(pill.text, s)
            pill:SetWidth(floor((pill.text:GetStringWidth() or 0) + 22 + 0.5))
        end
        pill:Show()
    else
        pill:Hide()
    end
end

function MP.Refresh()
    MP.drawn = nil
    MP.RefreshPlaces()
    MP.RefreshObjects()
    MP.LayoutLegend()
    MP.Update()
end

local acc, objAcc = 0, 0
win:SetScript("OnUpdate", function(self, elapsed)
    acc = acc + (elapsed or 0)
    objAcc = objAcc + (elapsed or 0)
    if acc >= 0.1 then
        acc = 0
        MP.Update()
    end
    if objAcc >= 0.05 then
        objAcc = 0
        MP.UpdateObjects()
        MP.UpdateGhost()
    end
end)

------------------------------------------------------------------------------------------------------
-- Placement: the lobby dock, the fight's spot
------------------------------------------------------------------------------------------------------
-- The lobby docks the map (phase 0 and 1).
function MP.Docked(m)
    m = m or R.Match()
    return m ~= nil and m.phase <= R.PHASE.COUNTDOWN
end

-- The dock's top, in UIParent units under the screen's top: under the top bar's tab at the HUD scale (RoyaleHud.lua's
-- H.LobbyTop: 112 up to 1.14, 151.2 at 1.4), at least MP.DOCK_TOP.
function MP.DockTop()
    local H = ns.RoyaleHud
    return max(MP.DOCK_TOP, H and H.LobbyTop and H.LobbyTop() or 0)
end

-- The dock's scale: the HUD scale, made smaller where it would not fit between the bar's tab and the bottom, or in
-- the left half of the screen (0.903 on 16:9, 0.784 on 4:3, 0.730 on 5:4 at UI scale 1). A larger HUD scale never
-- pushes the docked map off the screen.
function MP.DockScale()
    local W, H = UIParent:GetWidth(), UIParent:GetHeight()
    local fitH = (H - MP.DockTop() - MP.DOCK_BOTTOM) / MP.H
    local fitW = (W / 2 - 2 * MP.DOCK_GAP) / MP.W
    return max(0.4, min(RS.HudScale(), fitH, fitW))
end

-- The fight's scale: the HUD scale, at most what fits the screen's height.
function MP.FightScale()
    return max(0.4, min(RS.HudScale(), (UIParent:GetHeight() - 40) / MP.H))
end

-- Puts the window where it belongs now: docked in the lobby (TOPRIGHT at UIParent's TOP -24, -MP.DockTop(), in the
-- window's own scale), else at the player's spot or the centre.
function MP.Place()
    local m = R.Match()
    win:ClearAllPoints()
    if MP.Docked(m) then
        local s = MP.DockScale()
        win:SetScale(s)
        win:SetPoint("TOPRIGHT", UIParent, "TOP", -MP.DOCK_GAP / s, -MP.DockTop() / s)
        MP.docked = true
    else
        win:SetScale(MP.FightScale())
        local pos = ns.cdb.windows[win:GetName()]
        if type(pos) == "table" and type(pos.point) == "string" and type(pos.x) == "number"
            and type(pos.y) == "number" then
            win:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, pos.x, pos.y)
        else
            win:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
        end
        MP.docked = false
    end
    relayout()
end

------------------------------------------------------------------------------------------------------
-- Opening and closing
------------------------------------------------------------------------------------------------------
-- Opens the map (auto: opened by itself, so it may close by itself); strata FULLSCREEN_DIALOG puts it above the stock
-- world map. Returns false without a map from the server, and false, "locked" in the lobby's last 3.6 s: the
-- countdown closed the map at its lock and holds the centre until DROP!, where a docked map would slide under it
-- (above the stock world map it may open: that one covers the countdown anyway).
function MP.Open(auto, strata)
    if not S.royaleMap then
        return false
    end
    local m = R.Match()
    local RC = ns.RoyaleCountdown
    if strata ~= "FULLSCREEN_DIALOG" and MP.Docked(m) and RC and RC.HoldsCentre and RC.HoldsCentre(m) then
        return false, "locked"
    end
    win:SetFrameStrata(strata or "HIGH")
    MP.Place()
    if win:IsShown() then
        MP.Refresh()
    else
        win:Show()
    end
    MP.auto = auto and true or nil
    return true
end

-- Closes the map; `silent` without its close sound (the lock at T-3.6, the stock map closing over it).
function MP.Close(silent)
    if not win:IsShown() then
        return
    end
    MP.silent = silent and true or nil
    win:Hide()
    MP.silent = nil
end

-- M while the countdown keeps the map shut (MP.Open's "locked"): the countdown's line 2 names the locked landing
-- (RC.Remind); under DROP! nothing, the map opens a moment later with the drop.
function MP.SayLocked()
    local RC = ns.RoyaleCountdown
    if RC and RC.Remind then
        RC.Remind()
    end
end

function MP.Toggle()
    if win:IsShown() then
        MP.Close()
        return
    end
    local ok, why = MP.Open(false)
    if why == "locked" then
        MP.SayLocked()
    elseif not ok then
        R.Notice(nil, "You are not in a Bleakhold Royale match.")
    end
end

UI.RegisterOpener("royalemap", function()
    MP.Toggle()
end)

-- The map's own key: ALT-M (next to the world map's M; free in the stock key bindings, unlike N and SHIFT-M), set once
-- per account when the player first gets into a match, only when neither the key nor the map's binding is taken,
-- like the emote wheel's Ctrl+G (Animations.lua). Not in combat: tried again with the next ROYS. In a Royale
-- battleground M itself opens the map too (the override below).
MP.BINDING = "BLEAKHOLD_ROYALE_MAP"
MP.DEFAULT_KEY = "ALT-M"
MP.WORLD_MAP_BINDING = "TOGGLEWORLDMAP"
MP.COMMAND_TEXT = "/bh royale map"

function MP.OfferDefaultKey()
    local opts = ns.db.options
    if opts.royaleMapKeyOffered or not SetBinding or not GetBindingAction or not GetBindingKey then
        return
    end
    if InCombatLockdown and InCombatLockdown() then
        return
    end
    opts.royaleMapKeyOffered = true
    if GetBindingKey(MP.BINDING) then
        return
    end
    local current = GetBindingAction(MP.DEFAULT_KEY)
    if current == nil or current == "" then
        if SetBinding(MP.DEFAULT_KEY, MP.BINDING) and SaveBindings and GetCurrentBindingSet then
            SaveBindings(GetCurrentBindingSet())
        end
    else
        ns.Print("Royale island map: " .. MP.DEFAULT_KEY .. " is taken; bind a key in Key Bindings, Bleakhold.")
    end
end

-- In the lobby the map opens by itself once per match when the landing phase starts (closing it keeps it closed); a
-- late arrival in phase 1 gets it only while the countdown can still dock beside it and the pin is not locked. From
-- the drop on an automatically opened map closes again.
function MP.AutoCheck()
    local m = R.Match()
    if not m or not S.royaleMap then
        return
    end
    if m.phase == R.PHASE.COUNTDOWN and m.me == R.ME.LOBBY then
        if MP.autoFor ~= m.matchId then
            MP.autoFor = m.matchId
            local RC = ns.RoyaleCountdown
            if MP.PinLocked(m) then
                return
            end
            if RC and RC.OwnsClock and RC.OwnsClock(m) and RC.DockX and not RC.DockX() then
                return
            end
            MP.Open(true)
        end
    elseif m.phase >= R.PHASE.DROP and MP.auto and win:IsShown() then
        MP.Close(true)
    end
end

------------------------------------------------------------------------------------------------------
-- The M key: override bindings in a Royale battleground, set and cleared out of combat only
------------------------------------------------------------------------------------------------------
local owner = CreateFrame("Frame", "BleakholdRoyaleBindings", UIParent)
MP.bindOwner = owner
MP.overrideKeys = {}               -- the keys running BLEAKHOLD_ROYALE_MAP now
MP.bindQueue = nil                 -- "set" or "clear", waiting for the end of combat

local function worldMapKeys()
    if not GetBindingKey then
        return {}
    end
    return { GetBindingKey(MP.WORLD_MAP_BINDING) }
end

local function applyBinding(op)
    if not (SetOverrideBinding and ClearOverrideBindings) then
        return
    end
    ClearOverrideBindings(owner)
    MP.overrideKeys = {}
    if op == "set" then
        for _, key in ipairs(worldMapKeys()) do
            SetOverrideBinding(owner, false, key, MP.BINDING)
            MP.overrideKeys[#MP.overrideKeys + 1] = key
        end
    end
end

-- "set" or "clear" now, or after combat (the last one queued wins). Returns true when it ran now.
function MP.QueueBinding(op)
    if InCombatLockdown and InCombatLockdown() then
        MP.bindQueue = op
        return false
    end
    MP.bindQueue = nil
    applyBinding(op)
    return true
end

-- M opens the island map while the player is in a Royale battleground (ROYM of map 901).
function MP.WantOverride()
    local map = S.royaleMap
    return map ~= nil and map.mapId == R.MAP_ID and R.InBattleground() and true or false
end

local function sameKeys(a, b)
    if #a ~= #b then
        return false
    end
    for i = 1, #a do
        if a[i] ~= b[i] then
            return false
        end
    end
    return true
end

-- The override as it should be: set (again, when the world map's keys changed) or cleared.
function MP.CheckBindings()
    if MP.WantOverride() then
        if MP.bindQueue == "clear" or not sameKeys(worldMapKeys(), MP.overrideKeys) then
            MP.QueueBinding("set")
        end
    elseif #MP.overrideKeys > 0 or MP.bindQueue == "set" then
        MP.QueueBinding("clear")
    end
end

-- The key that opens the map now: M (the world map's first key) while the override runs, else the map's own binding,
-- else the slash command.
function MP.KeyText()
    if MP.overrideKeys[1] then
        return MP.overrideKeys[1]
    end
    local key = GetBindingKey and GetBindingKey(MP.BINDING)
    if key and key ~= "" then
        return key
    end
    return MP.COMMAND_TEXT
end

ns.RegisterEvent("PLAYER_REGEN_ENABLED", function()
    local op = MP.bindQueue
    if op then
        MP.bindQueue = nil
        applyBinding(op)
    end
end)

ns.RegisterEvent("UPDATE_BINDINGS", function()
    if MP.WantOverride() or #MP.overrideKeys > 0 then
        MP.CheckBindings()
    end
end)

------------------------------------------------------------------------------------------------------
-- The stock world map and Shift-M's battlefield minimap in a match
------------------------------------------------------------------------------------------------------
-- The stock maps show the island: GetMapInfo names it, or names nothing while the player is in the Royale
-- battleground (a client without the map's WorldMapArea row).
function MP.IslandView()
    local file = GetMapInfo and GetMapInfo()
    if file == R.MAP_FILE then
        return true
    end
    if file == nil or file == "" then
        local map = S.royaleMap
        return map ~= nil and map.mapId == R.MAP_ID and R.InBattleground() and true or false
    end
    return false
end

-- patch-Q's world map tiles are missing (probed once: SetTexture answers nil for a file the client cannot load).
local probe = owner:CreateTexture(nil, "BACKGROUND")
probe:Hide()
function MP.TilesMissing(recheck)
    if MP.tilesMissing == nil or recheck then
        MP.tilesMissing = not probe:SetTexture(MP.TILE_PROBE)
        probe:SetTexture(nil)
    end
    return MP.tilesMissing
end

-- A cover: the sea over the whole map area, the island's picture where WorldMapArea puts it.
local function newCover(name, parent)
    local f = CreateFrame("Frame", name, parent)
    f.sea = f:CreateTexture(nil, "BORDER")
    f.sea:SetTexture(UI.WHITE)
    f.sea:SetVertexColor(RS.Rgb(MP.SEA, 1))
    f.pic = f:CreateTexture(nil, "ARTWORK")
    RS.LazyTexture(f.pic, R.MAP_TEX)
    f:Hide()
    return f
end

-- Letterboxes the picture into a w x h map area hanging from `area`'s top-left: the WorldMapArea frame MapForge
-- writes is ROYM's frame widened to 1002:668 (R.WorldMapBounds), so the island sits in the middle with sea beside it.
local function layoutCover(f, area, w, h)
    local map = S.royaleMap
    local left, right, top, bottom = R.WorldMapBounds(map)
    if not left then
        return false
    end
    f:ClearAllPoints()
    f:SetPoint("TOPLEFT", area, "TOPLEFT", 0, 0)
    f:SetSize(w, h)
    f.sea:SetAllPoints(f)
    local u0, u1 = (left - map.maxY) / (left - right), (left - map.minY) / (left - right)
    local v0, v1 = (top - map.maxX) / (top - bottom), (top - map.minX) / (top - bottom)
    f.pic:ClearAllPoints()
    f.pic:SetPoint("TOPLEFT", f, "TOPLEFT", u0 * w, -v0 * h)
    f.pic:SetSize((u1 - u0) * w, (v1 - v0) * h)
    return true
end

-- Covers are wanted while the server has sent the island (ROYM, until the match is forgotten), the stock maps show
-- it and patch-Q has no tiles for it.
function MP.CoverWanted()
    return S.royaleMap ~= nil and MP.IslandView() and MP.TilesMissing() and true or false
end

function MP.UpdateCovers()
    local want = (MP.worldCover or MP.fieldCover) and MP.CoverWanted()
    local f = MP.worldCover
    if f then
        if want and WorldMapDetailFrame and layoutCover(f, WorldMapDetailFrame, WorldMapDetailFrame:GetWidth(),
            WorldMapDetailFrame:GetHeight()) then
            -- under the player arrow and the POIs on WorldMapButton, over the detail frame's tiles
            if WorldMapButton then
                f:SetFrameLevel(max(0, WorldMapButton:GetFrameLevel() - 1))
            end
            f:Show()
        else
            f:Hide()
        end
    end
    f = MP.fieldCover
    if f then
        local tile = BattlefieldMinimap1 and BattlefieldMinimap1:GetWidth() or 0
        -- 4 x 3 tiles of 256 hold a 1002 x 668 map
        if want and tile > 0 and layoutCover(f, BattlefieldMinimap, tile * 4 * 1002 / 1024, tile * 3 * 668 / 768) then
            f:Show()
        else
            f:Hide()
        end
    end
end

-- The redirect: the stock world map showing the island during a match.
local function overStock()
    MP.UpdateCovers()
    if MP.Open(false, "FULLSCREEN_DIALOG") then
        MP.overStock = true
    end
end

function MP.OnWorldMapShow()
    if not (R.Match() and S.royaleMap and MP.IslandView()) then
        MP.UpdateCovers()
        return
    end
    if InCombatLockdown and InCombatLockdown() then
        -- the stock map is protected now: leave it, cover its stale tiles, open ours above it
        overStock()
        return
    end
    MP.UpdateCovers()
    ns.After(0, function()
        if not (WorldMapFrame and WorldMapFrame:IsShown() and R.Match() and MP.IslandView()) then
            return
        end
        if InCombatLockdown and InCombatLockdown() then
            overStock()
            return
        end
        if HideUIPanel then
            HideUIPanel(WorldMapFrame)
        end
        if WorldMapFrame:IsShown() then
            WorldMapFrame:Hide()
        end
        local _, why = MP.Open(false)
        if why == "locked" then
            MP.SayLocked()
        end
    end)
end

function MP.HookWorldMap()
    if MP.worldHooked or not (WorldMapFrame and WorldMapFrame.HookScript and WorldMapDetailFrame) then
        return
    end
    MP.worldHooked = true
    MP.worldCover = newCover("BleakholdRoyaleWorldMapCover", WorldMapDetailFrame)
    WorldMapFrame:HookScript("OnShow", function()
        MP.OnWorldMapShow()
    end)
    WorldMapFrame:HookScript("OnHide", function()
        if MP.overStock and win:IsShown() then
            MP.Close(true)
        end
        MP.UpdateCovers()
    end)
    MP.UpdateCovers()
end

function MP.HookBattlefieldMinimap()
    if MP.fieldCover or not (BattlefieldMinimap and BattlefieldMinimap1) then
        return
    end
    -- at the minimap's own level: the textures draw over its tiles (BACKGROUND, the same level batches layer by
    -- layer), its party, POI and arrow frames (one level up) stay above
    MP.fieldCover = newCover("BleakholdRoyaleBattlefieldCover", BattlefieldMinimap)
    MP.fieldCover:SetFrameLevel(BattlefieldMinimap:GetFrameLevel())
    if BattlefieldMinimap.HookScript then
        BattlefieldMinimap:HookScript("OnShow", function()
            MP.UpdateCovers()
        end)
    end
    MP.UpdateCovers()
end

MP.HookWorldMap()
if IsAddOnLoaded and IsAddOnLoaded("Blizzard_BattlefieldMinimap") then
    MP.HookBattlefieldMinimap()
end

ns.RegisterEvent("ADDON_LOADED", function(event, name)
    if name == "Blizzard_BattlefieldMinimap" then
        MP.HookBattlefieldMinimap()
    end
end)

ns.RegisterEvent("WORLD_MAP_UPDATE", function()
    MP.UpdateCovers()
end)

ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    MP.HookWorldMap()
    MP.CheckBindings()
    MP.UpdateCovers()
end)

------------------------------------------------------------------------------------------------------
-- State
------------------------------------------------------------------------------------------------------
ns.On("STATE", function(topic)
    if topic == "ROYM" then
        if win:IsShown() then
            MP.Refresh()
        end
        MP.CheckBindings()
        MP.UpdateCovers()
        MP.AutoCheck()
    elseif topic == "ROYS" then
        if not S.royale then
            MP.Close(true)
            MP.CheckBindings()
            MP.UpdateCovers()
            return
        end
        if win:IsShown() then
            if MP.docked ~= MP.Docked() then
                MP.Place()
            end
            MP.Update()
        end
        MP.AutoCheck()
        MP.OfferDefaultKey()
        MP.UpdateCovers()
    elseif topic == "ROYO" and win:IsShown() then
        MP.RefreshObjects()
    end
end)

ns.On("ROYALE_MATCH", function()
    eventPing = nil
    MP.autoFor = nil   -- a record that (re)appears (a preview or the demo again, under its fixed id) opens it again
end)

-- The client's lock at T-3.6 (RoyaleCountdown.lua): the own pin flashes once.
ns.On("ROYALE_PIN_LOCKED", function()
    if win:IsShown() and pins.pin:IsShown() then
        RS.Tween(pins.pin, "vertexColor", "safe", "gold", 0.5, "outCubic")
    end
end)

local function replace()
    if win:IsShown() then
        MP.Place()
        MP.Refresh()
    end
end
ns.On("ROYALE_HUD_SCALE", replace)
ns.RegisterEvent("DISPLAY_SIZE_CHANGED", replace)
