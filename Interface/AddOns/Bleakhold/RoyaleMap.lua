-- Bleakhold: Bleakhold Royale's island map (docs/BleakholdProtocol.md section 17). The picture (Art\Royale\Map, drawn
-- by Tools/BlpConvert/make_royale_art.py from the MapForge terrain) with what the server sends on top: the places of
-- ROYM with their names, the lobby the fighters may not enter, the storm (the current circle in purple with its shade
-- outside, the next one in white, moving as ROYS says), the orbs and supply drops of ROYO with their timers, the
-- supply pings of ROYV, the landing pin and the player's own arrow. In the lobby a click sets the landing pin (RDROP,
-- Royale.lua); the map opens by itself when the player arrives in the lobby and closes at the drop. Key binding
-- BLEAKHOLD_ROYALE_MAP (BleakholdToggle("royalemap"); ALT-M by default, set once per account when the player first
-- gets into a match and the key is free), /bh royale map, the minimap orb.
--
-- Map transform (ROYM's frame): u = (maxY - y) / (maxY - minY), v = (maxX - x) / (maxX - minX); north up, west left.
-- The map sits in a ScrollFrame, which clips what lies outside it (storm circles larger than the island).
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S
local R = ns.Royale

local floor, ceil, max, min, abs, sin = math.floor, math.ceil, math.max, math.min, math.abs, math.sin

local MP = {}
ns.RoyaleMap = MP

MP.SIZE = 512
MP.LIMIT = 700                     -- px beyond the picture where the storm's shade stops (the ScrollFrame clips it)
MP.RING = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\Ring"
MP.RING_MID = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\RingMid"
MP.RING_SMALL = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\RingSmall"
MP.HOLE = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\Hole"
MP.HOLE_SMALL = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\HoleSmall"
MP.ARROW = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\Arrow"
MP.PIN = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\Pin"
MP.STORM_ALPHA = 0.3
MP.NEXT_COLOR = "FFFFFF"
MP.LOBBY_COLOR = C.red
-- objects: colour and glyph by kind (buff orbs by subtype)
MP.OBJECT_STYLE = {
    S = { color = C.purple, glyph = "search", name = "Shadow Sight", text = "Stealth is no cover for a while." },
    B1 = { color = C.teal, glyph = "right", name = "Speed orb", text = "Run faster for a while." },
    B2 = { color = "7FD47F", glyph = "shield", name = "Restoration orb",
        text = "Health and mana back over a few seconds." },
    B3 = { color = C.orange, glyph = "sword", name = "Berserk orb",
        text = "More damage done, and taken, for a while." },
    D = { color = C.goldLight, glyph = "chest", name = "Supply drop", text = "A storm cache with rare loot." },
}
MP.STATE_TEXT = { [0] = "Not here yet", [1] = "Ready", [2] = "Taken", [3] = "Coming down", [4] = "Opened" }

------------------------------------------------------------------------------------------------------
-- Window
------------------------------------------------------------------------------------------------------
local W = MP.SIZE + 24
local H = 50 + 12 + MP.SIZE + 44
local win = UI.Window("BleakholdRoyaleMapFrame", W, H, "BLEAKHOLD ROYALE", "sword")
MP.frame = win

win.alive = UI.Pill(win.header, "", C.chip, C.chipBorder, C.text, 12)
win.alive:SetPoint("RIGHT", win.close, "LEFT", -10, 0)
win.alive:Hide()

local view = CreateFrame("ScrollFrame", nil, win.content)
view:SetSize(MP.SIZE, MP.SIZE)
view:SetPoint("TOP", win.content, "TOP", 0, -12)
local canvas = CreateFrame("Frame", nil, view)
canvas:SetSize(MP.SIZE, MP.SIZE)
view:SetScrollChild(canvas)
canvas:EnableMouse(true)
MP.view, MP.canvas = view, canvas

local border = UI.Box(win.content, MP.SIZE + 2, MP.SIZE + 2, nil, C.eraBorder)
border:SetPoint("CENTER", view, "CENTER", 0, 0)
border:SetFrameLevel(view:GetFrameLevel() + 8)
border:EnableMouse(false)

canvas.bg = UI.Solid(canvas, C.deep, "BACKGROUND")
canvas.bg:SetAllPoints(canvas)
canvas.pic = canvas:CreateTexture(nil, "BORDER")
canvas.pic:SetAllPoints(canvas)
canvas.pic:SetTexture(R.MAP_TEX)
canvas.none = UI.Text(canvas, 13, C.dim, "body", "CENTER")
canvas.none:SetPoint("CENTER", canvas, "CENTER", 0, 0)
canvas.none:SetText("No picture of this map")
canvas.none:Hide()

local function layer(level)
    local f = CreateFrame("Frame", nil, canvas)
    f:SetAllPoints(canvas)
    f:SetFrameLevel(canvas:GetFrameLevel() + level)
    return f
end
local shadeLayer, ringLayer, poiLayer, objLayer, topLayer = layer(1), layer(2), layer(3), layer(4), layer(5)

local strip = CreateFrame("Frame", nil, win.content)
strip:SetPoint("TOPLEFT", view, "BOTTOMLEFT", 0, -6)
strip:SetPoint("TOPRIGHT", view, "BOTTOMRIGHT", 0, -6)
strip:SetHeight(30)
strip.left = UI.Text(strip, 13, C.goldPale)
strip.left:SetPoint("LEFT", strip, "LEFT", 2, 0)
UI.OneLine(strip.left, 330)
strip.right = UI.Text(strip, 12, C.dim, "body", "RIGHT")
strip.right:SetPoint("RIGHT", strip, "RIGHT", -2, 0)
UI.OneLine(strip.right, 176)
MP.strip = strip

------------------------------------------------------------------------------------------------------
-- Transform
------------------------------------------------------------------------------------------------------
-- World (x, y) -> pixels from the picture's top-left corner.
function MP.ToMap(x, y, map)
    map = map or S.royaleMap
    local u = (map.maxY - y) / (map.maxY - map.minY)
    local v = (map.maxX - x) / (map.maxX - map.minX)
    return u * MP.SIZE, v * MP.SIZE
end

-- Pixels from the picture's top-left corner -> world (x, y).
function MP.ToWorld(px, py, map)
    map = map or S.royaleMap
    local u, v = px / MP.SIZE, py / MP.SIZE
    return map.maxX - v * (map.maxX - map.minX), map.maxY - u * (map.maxY - map.minY)
end

-- Yards -> pixels (the mean of both axes; the island's frame is square).
function MP.Yards(yd, map)
    map = map or S.royaleMap
    local span = ((map.maxX - map.minX) + (map.maxY - map.minY)) / 2
    return yd * MP.SIZE / span
end

-- The cursor in pixels from the picture's top-left corner.
function MP.CursorPos()
    local x, y = GetCursorPosition()
    local s = canvas:GetEffectiveScale() or 1
    local left, top = canvas:GetLeft(), canvas:GetTop()
    if not (x and left and top) or s <= 0 then
        return nil
    end
    return x / s - left, top - y / s
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
    local x, y = MP.ToWorld(px, py, map)
    R.SetPin(x, y)
end

canvas:SetScript("OnMouseUp", function(self, button)
    MP.OnMapClick(button)
end)

------------------------------------------------------------------------------------------------------
-- Drawing helpers
------------------------------------------------------------------------------------------------------
local function at(region, point, px, py)
    region:ClearAllPoints()
    region:SetPoint(point, canvas, "TOPLEFT", px, -py)
end

-- A ring of radius rpx pixels from the texture whose size is nearest (the client draws interface textures without
-- mipmaps, so a texture far larger than its place on screen loses its thin line).
local function ring(t, px, py, rpx)
    local d = rpx * 2
    if not px or d < 3 then
        t:Hide()
        return
    end
    local file = d > 256 and MP.RING or (d > 64 and MP.RING_MID or MP.RING_SMALL)
    if t.file ~= file then
        t:SetTexture(file)
        t.file = file
    end
    at(t, "CENTER", px, py)
    t:SetSize(d, d)
    t:Show()
end

local function newRing(parent, color, alpha)
    local t = parent:CreateTexture(nil, "ARTWORK")
    t:SetVertexColor(UI.Rgb(color, alpha))
    t:Hide()
    return t
end

local function rect(t, x0, y0, x1, y1)
    local L = MP.LIMIT
    x0, y0 = max(x0, -L), max(y0, -L)
    x1, y1 = min(x1, MP.SIZE + L), min(y1, MP.SIZE + L)
    if x1 - x0 < 0.5 or y1 - y0 < 0.5 then
        t:Hide()
        return
    end
    at(t, "TOPLEFT", x0, y0)
    t:SetSize(x1 - x0, y1 - y0)
    t:Show()
end

local shade = {}
for _, k in ipairs({ "top", "bottom", "left", "right" }) do
    shade[k] = UI.Solid(shadeLayer, C.purple, "ARTWORK", MP.STORM_ALPHA)
    shade[k]:Hide()
end
shade.hole = shadeLayer:CreateTexture(nil, "ARTWORK")
shade.hole:SetVertexColor(UI.Rgb(C.purple, MP.STORM_ALPHA))
shade.hole:Hide()
MP.shade = shade

-- The storm's shade outside the circle (px, py, rpx in pixels); no circle: none; radius 0: everywhere.
function MP.DrawStorm(px, py, rpx)
    local L, N = MP.LIMIT, MP.SIZE + MP.LIMIT
    if not px then
        for _, t in pairs(shade) do
            t:Hide()
        end
        return
    end
    if rpx <= 0.5 then
        rect(shade.top, -L, -L, N, N)
        shade.bottom:Hide()
        shade.left:Hide()
        shade.right:Hide()
        shade.hole:Hide()
        return
    end
    rect(shade.top, -L, -L, N, py - rpx)
    rect(shade.bottom, -L, py + rpx, N, N)
    rect(shade.left, -L, py - rpx, px - rpx, py + rpx)
    rect(shade.right, px + rpx, py - rpx, N, py + rpx)
    local file = rpx * 2 >= 96 and MP.HOLE or MP.HOLE_SMALL
    if shade.hole.file ~= file then
        shade.hole:SetTexture(file)
        shade.hole.file = file
    end
    at(shade.hole, "CENTER", px, py)
    shade.hole:SetSize(rpx * 2, rpx * 2)
    shade.hole:Show()
end

local rings = {
    lobby = newRing(ringLayer, MP.LOBBY_COLOR, 0.85),
    nextc = newRing(ringLayer, MP.NEXT_COLOR, 0.9),
    cur = newRing(ringLayer, C.purple, 1),
}
MP.rings = rings

local pins = {
    pin = topLayer:CreateTexture(nil, "OVERLAY"),
    pending = topLayer:CreateTexture(nil, "OVERLAY"),
}
for k, t in pairs(pins) do
    t:SetTexture(MP.PIN)
    t:SetSize(24, 24)
    t:SetVertexColor(UI.Rgb(k == "pin" and C.gold or "FFFFFF", k == "pin" and 1 or 0.7))
    t:Hide()
end
MP.pins = pins

local arrow = topLayer:CreateTexture(nil, "OVERLAY")
arrow:SetTexture(MP.ARROW)
arrow:SetSize(20, 20)
arrow:SetVertexColor(UI.Rgb(C.goldPale))
arrow:Hide()
MP.arrow = arrow

------------------------------------------------------------------------------------------------------
-- Places (ROYM)
------------------------------------------------------------------------------------------------------
local function poiTooltip(self)
    local p = self.poi
    if not p then
        return
    end
    local lines = { U.Safe(p.name or "?") }
    if p.kind == "C" then
        lines[#lines + 1] = { "A crossing over the river", C.mid }
    elseif p.kind == "Y" then
        lines[#lines + 1] = { "The lobby: players in the fight may not enter", C.red, true }
    end
    if R.CanPin() then
        lines[#lines + 1] = { "Click to land here", C.mute }
    end
    UI.ShowTooltip(self, lines)
end

local function hideTooltip()
    if GameTooltip then
        GameTooltip:Hide()
    end
end

local pois = UI.Pool(function()
    local f = CreateFrame("Frame", nil, poiLayer)
    f:SetSize(16, 16)
    f:EnableMouse(true)
    f.dot = UI.Disc(f, 8, C.goldPale, "ARTWORK")
    f.dot:SetPoint("CENTER", f, "CENTER", 0, 0)
    f.glyph = UI.Glyph(f, "banner", 14, C.gold, "OVERLAY")
    f.glyph:SetPoint("CENTER", f, "CENTER", 0, 0)
    f.label = UI.Text(f, 11, C.goldPale, "body", "CENTER")
    f.label:SetPoint("TOP", f, "BOTTOM", 0, 0)
    f:SetScript("OnEnter", poiTooltip)
    f:SetScript("OnLeave", hideTooltip)
    f:SetScript("OnMouseUp", function(self, button)
        MP.OnMapClick(button)
    end)
    return f
end)
MP.pois = pois

function MP.RefreshPlaces()
    pois:ReleaseAll()
    local map = S.royaleMap
    local hasPicture = map and map.mapId == R.MAP_ID
    if hasPicture then
        canvas.pic:Show()
        canvas.none:Hide()
    else
        canvas.pic:Hide()
        if map then
            canvas.none:Show()
        else
            canvas.none:Hide()
        end
    end
    if not map then
        rings.lobby:Hide()
        return
    end
    for _, p in ipairs(map.pois) do
        local f = pois:Acquire()
        f.poi = p
        local px, py = MP.ToMap(p.x, p.y, map)
        f:ClearAllPoints()
        f:SetPoint("CENTER", canvas, "TOPLEFT", px, -py)
        UI.SetText(f.label, p.name or "")
        if p.kind == "Y" then
            f.dot:Hide()
            f.glyph:Show()
            UI.SetColor(f.label, C.red)
            f.label:SetFont(UI.FONT_BODY, 11, "")
        elseif p.kind == "C" then
            f.dot:Show()
            f.dot:SetSize(6, 6)
            f.dot:SetVertexColor(UI.Rgb(C.teal))
            f.glyph:Hide()
            UI.SetColor(f.label, C.mid)
            f.label:SetFont(UI.FONT_BODY, 10, "")
        else
            f.dot:Show()
            f.dot:SetSize(8, 8)
            f.dot:SetVertexColor(UI.Rgb(C.goldPale))
            f.glyph:Hide()
            UI.SetColor(f.label, C.goldPale)
            f.label:SetFont(UI.FONT_BODY, 11, "")
        end
    end
    if map.lobbyX and (map.lobbyR or 0) > 0 then
        local px, py = MP.ToMap(map.lobbyX, map.lobbyY, map)
        ring(rings.lobby, px, py, MP.Yards(map.lobbyR, map))
    else
        rings.lobby:Hide()
    end
end

------------------------------------------------------------------------------------------------------
-- Orbs and supply drops (ROYO), supply pings (ROYV D and L)
------------------------------------------------------------------------------------------------------
local function objectStyle(o)
    return MP.OBJECT_STYLE[o.kind == "B" and ("B" .. (o.subtype or 0)) or o.kind] or MP.OBJECT_STYLE.S
end

local function objectTooltip(self)
    local o = self.obj
    if not o then
        return
    end
    local st = objectStyle(o)
    local lines = { st.name, { st.text, C.mid, true } }
    local left = ns.RoyaleLeft(o.msLeft, o.recvAt)
    local state = MP.STATE_TEXT[o.state] or ""
    if left and left > 0 and (o.state == 0 or o.state == 2 or o.state == 3) then
        local when = o.state == 3 and " - lands in " or (o.state == 2 and " - back in " or " - appears in ")
        state = state .. when .. U.Clock(ceil(left))
    end
    lines[#lines + 1] = { state, C.goldLight }
    UI.ShowTooltip(self, lines)
end

local objects = UI.Pool(function()
    local f = CreateFrame("Frame", nil, objLayer)
    f:SetSize(18, 18)
    f:EnableMouse(true)
    f.disc = UI.Disc(f, 16, C.purple, "ARTWORK")
    f.disc:SetPoint("CENTER", f, "CENTER", 0, 0)
    f.glyph = UI.Glyph(f, "search", 12, C.bg, "OVERLAY")
    f.glyph:SetPoint("CENTER", f, "CENTER", 0, 0)
    f.timer = UI.Text(f, 10, C.text, "body", "CENTER")
    f.timer:SetPoint("TOP", f, "BOTTOM", 0, -1)
    f.ping = f:CreateTexture(nil, "BORDER")
    f.ping:SetTexture(MP.RING_MID)
    f.ping:SetPoint("CENTER", f, "CENTER", 0, 0)
    f.ping:Hide()
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
    for _, o in ipairs(list) do
        local hidden = o.state == 0 and not o.msLeft
        if not hidden then
            local f = objects:Acquire()
            f.obj = o
            local st = objectStyle(o)
            local px, py = MP.ToMap(o.x, o.y, map)
            f:ClearAllPoints()
            f:SetPoint("CENTER", canvas, "TOPLEFT", px, -py)
            f.disc:SetVertexColor(UI.Rgb(st.color))
            UI.SetGlyph(f.glyph, st.glyph)
            local dim = o.state == 0 or o.state == 2 or o.state == 4
            f:SetAlpha(dim and 0.45 or 1)
            f.ping:SetVertexColor(UI.Rgb(st.color))
            f.ping:Hide()
        end
    end
    MP.UpdateObjects()
end

-- Timers under the objects and the supply ping, a few times a second.
function MP.UpdateObjects()
    local now = GetTime()
    for i = 1, objects.used do
        local f = objects.items[i]
        local o = f.obj
        local left = o and ns.RoyaleLeft(o.msLeft, o.recvAt)
        if left and left > 0 and (o.state == 0 or o.state == 2 or o.state == 3) then
            f.timer:SetText((U.Clock(ceil(left)):gsub("^00:", "0:")))
            f.timer:Show()
        else
            f.timer:Hide()
        end
        if o and o.kind == "D" and (o.state == 3 or o.state == 1) then
            local k = (now * 0.8) % 1
            local d = 18 + 34 * k
            f.ping:SetSize(d, d)
            f.ping:SetAlpha(1 - k)
            f.ping:Show()
        else
            f.ping:Hide()
        end
    end
end

------------------------------------------------------------------------------------------------------
-- Storm, pins, the player (redrawn while the map is shown)
------------------------------------------------------------------------------------------------------
local function setPin(t, x, y, map)
    if not x then
        t:Hide()
        return
    end
    local px, py = MP.ToMap(x, y, map)
    at(t, "BOTTOM", px, py)
    t:Show()
end

function MP.UpdateLive()
    local map = S.royaleMap
    local m = R.Match()
    if not map or not m then
        MP.DrawStorm(nil)
        rings.cur:Hide()
        rings.nextc:Hide()
        pins.pin:Hide()
        pins.pending:Hide()
        arrow:Hide()
        return
    end
    -- the storm
    local cx, cy, cr = R.Circle(m)
    local px, py = MP.ToMap(cx, cy, map)
    local rpx = MP.Yards(cr, map)
    MP.DrawStorm(px, py, rpx)
    ring(rings.cur, px, py, rpx)
    if m.nextR then
        local nx, ny = MP.ToMap(m.nextX, m.nextY, map)
        ring(rings.nextc, nx, ny, MP.Yards(m.nextR, map))
    else
        rings.nextc:Hide()
    end
    -- the landing pin: the server's (snapped), and the wish on its way
    local inLobby = R.InLobby(m)
    setPin(pins.pin, inLobby and m.pinX or nil, m.pinY, map)
    local pend = R.pendingPin
    setPin(pins.pending, (inLobby and pend and pend.matchId == m.matchId) and pend.x or nil, pend and pend.y, map)
    -- the player
    local x, y = R.MyPos()
    if x and m.me ~= R.ME.SPECTATING and m.me ~= R.ME.LEFT then
        local ax, ay = MP.ToMap(x, y, map)
        at(arrow, "CENTER", ax, ay)
        arrow:SetRotation(R.Facing() or 0)
        arrow:Show()
    else
        arrow:Hide()
    end
end

-- The line under the map.
function MP.StatusText(m)
    if not m then
        return "", ""
    end
    local right = ""
    if R.Overtime(m) then
        right = "Storm overtime"
    elseif m.stage > 0 then
        right = "Storm stage " .. m.stage .. " of " .. R.StageCount(m)
    end
    if R.InLobby(m) then
        if R.CanPin(m) then
            local lock = R.PinsLockIn(m)
            local left = "Click the map to set your landing pin"
            if lock and lock <= 10 then
                left = "Pins lock in " .. ceil(lock)
            end
            local pin = m.pinX and "Your pin is set" or "No pin: you land at a random place"
            return left, right ~= "" and right or pin
        end
        return "Pins are locked", right
    end
    if m.phase >= R.PHASE.VICTORY then
        return m.phase == R.PHASE.CANCELLED and "The match was cancelled" or "The match is over", right
    end
    if not R.Fighting(m) then
        return "The drop!", right   -- still falling (the fight's texts start at the landing)
    end
    local what, sec = R.StormTimer(m)
    local left
    if what == "hold" then
        left = "Storm moves in " .. U.Clock(ceil(sec))
    elseif what == "moving" then
        left = "Storm moving " .. U.Clock(ceil(sec))
    elseif R.Overtime(m) then
        left = "The storm has closed"
    else
        left = m.me == R.ME.SPECTATING and ("Watching " .. (m.watchName or "")) or ""
    end
    return left, right
end

function MP.Update()
    MP.UpdateLive()
    local m = R.Match()
    local left, right = MP.StatusText(m)
    UI.SetText(strip.left, left)
    UI.SetText(strip.right, right)
    if m then
        win.alive:SetValue((m.alive or 0) .. " / " .. (m.total or 0) .. " alive")
        win.alive:Show()
    else
        win.alive:Hide()
    end
end

function MP.Refresh()
    MP.RefreshPlaces()
    MP.RefreshObjects()
    MP.Update()
end

function win:OnOpen()
    MP.Refresh()
end

function win:OnClose()
    MP.auto = nil
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
    end
end)

------------------------------------------------------------------------------------------------------
-- Opening and closing
------------------------------------------------------------------------------------------------------
function MP.Open(auto)
    if not S.royaleMap then
        return false
    end
    if not win:IsShown() then
        win:Show()
    end
    MP.auto = auto and true or nil
    return true
end

function MP.Toggle()
    if win:IsShown() then
        win:Hide()
        return
    end
    if not MP.Open(false) then
        R.Notice(nil, "You are not in a Bleakhold Royale match.")
    end
end

UI.RegisterOpener("royalemap", function()
    MP.Toggle()
end)

-- The map's key: ALT-M (next to the world map's M; free in the stock key bindings, unlike N and SHIFT-M), set once per
-- account when the player first gets into a match, only when neither the key nor the map's binding is taken, like the
-- emote wheel's Ctrl+G (Animations.lua). Not in combat: tried again with the next ROYS.
MP.BINDING = "BLEAKHOLD_ROYALE_MAP"
MP.DEFAULT_KEY = "ALT-M"

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

-- The key that opens the map now, or nil.
function MP.KeyText()
    return GetBindingKey and GetBindingKey(MP.BINDING) or nil
end

-- In the lobby the map opens by itself, once per match (closing it keeps it closed); at the drop an
-- automatically opened map closes again.
function MP.AutoCheck()
    local m = R.Match()
    if not m or not S.royaleMap then
        return
    end
    if R.InLobby(m) and m.me == R.ME.LOBBY then
        if MP.autoFor ~= m.matchId then
            MP.autoFor = m.matchId
            MP.Open(true)
        end
    elseif m.phase >= R.PHASE.DROP and MP.auto and win:IsShown() then
        win:Hide()
    end
end

ns.On("STATE", function(topic)
    if topic == "ROYM" then
        if win:IsShown() then
            MP.Refresh()
        end
        MP.AutoCheck()
    elseif topic == "ROYS" then
        if not S.royale and win:IsShown() then
            win:Hide()
        elseif win:IsShown() then
            MP.Update()
        end
        MP.AutoCheck()
        if S.royale then
            MP.OfferDefaultKey()
        end
    elseif topic == "ROYO" and win:IsShown() then
        MP.RefreshObjects()
    end
end)

ns.On("ROYALE_MATCH", function()
    eventPing = nil
end)
