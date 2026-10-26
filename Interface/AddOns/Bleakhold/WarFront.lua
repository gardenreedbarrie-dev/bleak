-- Bleakhold: World PvP on screen (docs/BleakholdProtocol.md section 19), drawn from server state only (WPZ WPCAP
-- WANTED WPEV, parsed in State.lua; the client counts the timers down):
--   the Front HUD     top centre, movable: the zone, its phase and time left, one pip per outpost (blue, red or grey,
--                     pulsing while contested), the Front's control bar (the factions' points) and the player's
--                     Dominion; in a Front zone (WPZ kind F or L) while it runs or is in ceasefire. Under it the
--                     player's last reward (WPEV R), with the diminishing returns applied
--   the capture bar   WPCAP at the outpost the player stands at: Alliance on the left, Horde on the right, the neutral
--                     band in the middle, the marker, the way the bar moves (the counts' difference up to maxNet) and
--                     both counts; gone with WPCAP 0, or a few seconds after the last one
--   banners           WPEV C N A (the zone's outposts) and W B S (Wanted players); toasts for F E X (the Fronts)
--   the world map     pins for the outposts (WPZ) and the Wanted players (WANTED) while the world map shows the
--                     player's zone: its map area id is learnt with SetMapToCurrentZone while the map is closed, so the
--                     map the player looks at is never turned. Outposts and players without a position (a zone without
--                     a world map of its own, old Mount Hyjal) are listed in a box on the map instead
--   minimap arrows    on the minimap's edge towards the player's faction's outposts under attack (WPEV A, or a bar the
--                     other side is pushing), like Bleakhold Royale's safe-zone arrow
-- Stock outdoor PvP zones (WPZ kind S) keep their native world states and capture bar: there only the map pins and
-- the banners show. Nothing here shows without HELLO feature bit 16384; the outposts need 32768 too.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S
local WM = ns.WarMode

local floor, ceil, max, min, abs, sin, cos, atan2, pi = math.floor, math.ceil, math.max, math.min, math.abs, math.sin,
    math.cos, math.atan2, math.pi

local WF = {}
ns.WarFront = WF

WF.MAX_PIPS = 6
WF.PIP_GAP = 20
WF.CONTROL_W = 280                -- px of the HUD's control bar
WF.BAR_W = 240                    -- px of the capture bar
WF.CAP_STALE = 3.5                -- s without a WPCAP (one a second) after which the bar goes
WF.WANTED_STALE = 16              -- s without a WANTED (one every 5 s) after which its pins go
WF.ATTACK_TIME = 60               -- s an outpost counts as under attack after WPEV A
WF.BANNER_TIME = 3                -- s a banner holds (fade in and out included)
WF.REWARD_TIME = 6                -- s the reward line stays
WF.MAX_ARROWS = 3
WF.MAP_ASPECT = 1002 / 668        -- a zone map's width in yards over its height (WorldMapArea frames match the map)
WF.ARROW = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\Arrow"
WF.KICKER = { F = "BLEAK FRONT", L = "LEVELLING FRONT" }
WF.STATE_TEXT = {
    [0] = "Neutral", [1] = "Held by the Alliance", [2] = "Held by the Horde",
    [3] = "Neutral: the Alliance is taking it", [4] = "Neutral: the Horde is taking it",
    [5] = "The Alliance's: the Horde is taking it", [6] = "The Horde's: the Alliance is taking it",
}

local function teamColor(t)
    return WM.TeamColor(t)
end

local function classText(name, classId)
    return U.Color(ns.ClassColor(classId), U.Safe(name))
end

-- A contested outpost (one side pushing the bar: states 3 to 6).
local function contested(state)
    return (state or 0) >= 3
end

------------------------------------------------------------------------------------------------------
-- Positions: saved like the key tracker's, else a default spot
------------------------------------------------------------------------------------------------------
local function positioning(f, defPoint, defX, defY)
    UI.MakeMovable(f)
    f:SetClampedToScreen(true)
    local t = {}
    function t.Saved()
        local pos = ns.cdb.windows[f:GetName()]
        if type(pos) == "table" and type(pos.point) == "string" and type(pos.x) == "number"
            and type(pos.y) == "number" then
            return pos
        end
    end
    function t.Anchor()
        local pos = t.Saved()
        f:ClearAllPoints()
        if pos then
            f:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, pos.x, pos.y)
        else
            f:SetPoint(defPoint, UIParent, defPoint, defX, defY)
        end
    end
    function t.MoveTo(region, save)
        local point, relPoint, x, y = UI.TopAnchorOf(region)
        if not point then
            return
        end
        f:ClearAllPoints()
        f:SetPoint(point, UIParent, relPoint, x, y)
        if save then
            ns.cdb.windows[f:GetName()] = { point = point, relPoint = relPoint, x = x, y = y }
        end
    end
    function t.Reset()
        ns.cdb.windows[f:GetName()] = nil
        t.Anchor()
    end
    return t
end

------------------------------------------------------------------------------------------------------
-- The Front HUD
------------------------------------------------------------------------------------------------------
local hud = CreateFrame("Frame", "BleakholdWarFront", UIParent)
hud:SetSize(380, 90)
hud:SetFrameStrata("MEDIUM")
UI.Backdrop(hud, "101216", C.chipBorder, 0.9)
hud:Hide()
WF.hud = hud
local hudPos = positioning(hud, "TOP", 0, -8)

hud.line = UI.Solid(hud, WM.COLOR, "BORDER")
hud.line:SetPoint("TOPLEFT", hud, "TOPLEFT", 1, -1)
hud.line:SetPoint("TOPRIGHT", hud, "TOPRIGHT", -1, -1)
hud.line:SetHeight(2)
hud.kicker = UI.Text(hud, 10, WM.COLOR)
hud.kicker:SetPoint("TOPLEFT", hud, "TOPLEFT", 12, -9)
hud.zone = UI.Text(hud, 15, C.goldPale, "title")
hud.zone:SetPoint("TOPLEFT", hud.kicker, "BOTTOMLEFT", 0, -2)
UI.OneLine(hud.zone, 230)
hud.time = UI.Text(hud, 15, C.text, "title", "RIGHT")
hud.time:SetPoint("TOPRIGHT", hud, "TOPRIGHT", -12, -9)
UI.OneLine(hud.time, 120)
hud.phase = UI.Text(hud, 10, C.dim, "body", "RIGHT")
hud.phase:SetPoint("TOPRIGHT", hud.time, "BOTTOMRIGHT", 0, -1)
UI.OneLine(hud.phase, 120)
hud.pips = {}
for i = 1, WF.MAX_PIPS do
    local p = UI.Disc(hud, 12, C.track, "ARTWORK")
    p:Hide()
    hud.pips[i] = p
end
hud.control = CreateFrame("Frame", nil, hud)
hud.control:SetSize(WF.CONTROL_W, 6)
hud.control:SetPoint("TOP", hud, "TOP", 0, -64)
hud.control.bg = UI.Solid(hud.control, C.track, "BACKGROUND")
hud.control.bg:SetAllPoints(hud.control)
hud.control.a = UI.Solid(hud.control, WM.TEAM.A.color, "ARTWORK")
hud.control.a:SetPoint("TOPLEFT", hud.control, "TOPLEFT", 0, 0)
hud.control.a:SetPoint("BOTTOMLEFT", hud.control, "BOTTOMLEFT", 0, 0)
hud.control.h = UI.Solid(hud.control, WM.TEAM.H.color, "ARTWORK")
hud.control.h:SetPoint("TOPRIGHT", hud.control, "TOPRIGHT", 0, 0)
hud.control.h:SetPoint("BOTTOMRIGHT", hud.control, "BOTTOMRIGHT", 0, 0)
hud.aText = UI.Text(hud, 10, WM.TEAM.A.color, "body", "RIGHT")
hud.aText:SetPoint("RIGHT", hud.control, "LEFT", -6, 0)
hud.hText = UI.Text(hud, 10, WM.TEAM.H.color)
hud.hText:SetPoint("LEFT", hud.control, "RIGHT", 6, 0)
hud.note = UI.Text(hud, 11, C.mid, "body", "CENTER")
hud.note:SetPoint("TOP", hud.control, "BOTTOM", 0, -5)
UI.OneLine(hud.note, 356)
hud.reward = UI.Text(hud, 12, C.goldLight, "body", "CENTER")
hud.reward:SetPoint("TOP", hud, "BOTTOM", 0, -4)
UI.OneLine(hud.reward, 420)

WF.SAMPLE = {
    zoneId = 2817, kind = "F", state = 1, secondsLeft = 4320, controlA = 620, controlH = 380, dominionTeam = "A",
    dominionStacks = 2, objectives = { { objId = 1, owner = "A", state = 1 }, { objId = 2, owner = "N", state = 6 },
        { objId = 3, owner = "A", state = 1 } },
}

-- The zone the HUD shows: a Front zone (F or L) while it runs or is in ceasefire, with the objectives live.
function WF.HudZone()
    local z = S.wpZone
    if not WM.ObjectivesLive() or not z or (z.kind ~= "F" and z.kind ~= "L") or z.state == 0 then
        return nil
    end
    return z
end

-- The note under the control bar: Dominion (and Supremacy with every outpost), else who may capture here.
function WF.HudNote(z)
    local n = #z.objectives
    if z.dominionTeam and (z.dominionStacks or 0) > 0 then
        local txt = "Dominion x" .. z.dominionStacks
        if n > 0 and z.dominionStacks >= n then
            txt = txt .. "  -  Supremacy"
        end
        return txt, teamColor(z.dominionTeam)
    end
    local level = UnitLevel and UnitLevel("player")
    if z.levelMin and z.levelMax and type(level) == "number" and level > 0 and (level < z.levelMin
        or level > z.levelMax) then
        return "Only levels " .. z.levelMin .. "-" .. z.levelMax .. " can capture here", C.mute
    end
    if z.state == 2 then
        return "Ceasefire: the outposts are frozen", C.mute
    end
    return "", C.mid
end

function WF.UpdateHud()
    local z = WF.HudZone() or (WF.preview and WF.SAMPLE)
    if not z then
        if hud:IsShown() then
            hud:Hide()
        end
        return
    end
    hud.kicker:SetText(WF.KICKER[z.kind] or "WORLD PVP")
    UI.SetText(hud.zone, ns.WarZoneName(z.zoneId))
    local left = WF.preview and z.secondsLeft or (ns.WarLeft(z.secondsLeft, z.recvAt) or 0)
    hud.time:SetText(WM.Clock(left))
    hud.phase:SetText(z.state == 2 and "CEASEFIRE" or "LEFT")
    UI.SetColor(hud.time, z.state == 2 and C.mute or C.text)
    -- one pip per outpost, centred
    local n = min(#z.objectives, WF.MAX_PIPS)
    local t = GetTime()
    for i, p in ipairs(hud.pips) do
        local o = z.objectives[i]
        if o and i <= n then
            p:ClearAllPoints()
            p:SetPoint("TOP", hud, "TOP", (i - (n + 1) / 2) * WF.PIP_GAP, -44)
            p:SetVertexColor(UI.Rgb(teamColor(o.owner)))
            p:SetAlpha(contested(o.state) and z.state ~= 2 and (0.35 + 0.65 * abs(sin(t * 4))) or 1)
            p:Show()
        else
            p:Hide()
        end
    end
    -- the Front's points, in permille of all points
    local a, h = z.controlA, z.controlH
    if a and h and a + h > 0 then
        local wa, wh = floor(WF.CONTROL_W * a / 1000 + 0.5), floor(WF.CONTROL_W * h / 1000 + 0.5)
        if wa >= 1 then
            hud.control.a:SetWidth(wa)
            hud.control.a:Show()
        else
            hud.control.a:Hide()
        end
        if wh >= 1 then
            hud.control.h:SetWidth(wh)
            hud.control.h:Show()
        else
            hud.control.h:Hide()
        end
        hud.aText:SetText(floor(a / 10 + 0.5) .. "%")
        hud.hText:SetText(floor(h / 10 + 0.5) .. "%")
    else
        hud.control.a:Hide()
        hud.control.h:Hide()
        hud.aText:SetText("")
        hud.hText:SetText("")
    end
    local note, color = WF.HudNote(z)
    UI.SetText(hud.note, note)
    UI.SetColor(hud.note, color)
    local r = WF.reward
    local age = r and (t - r.at) or 99
    if age < WF.REWARD_TIME then
        UI.SetText(hud.reward, r.text)
        hud.reward:SetAlpha(U.Clamp(WF.REWARD_TIME - age, 0, 1))
    else
        hud.reward:SetText("")
    end
    if not hud:IsShown() then
        hudPos.Anchor()
        hud:Show()
    end
end

------------------------------------------------------------------------------------------------------
-- The capture bar
------------------------------------------------------------------------------------------------------
local cap = CreateFrame("Frame", "BleakholdWarCapture", UIParent)
cap:SetSize(320, 58)
cap:SetFrameStrata("MEDIUM")
UI.Backdrop(cap, "101216", C.chipBorder, 0.9)
cap:Hide()
WF.cap = cap
local capPos = positioning(cap, "TOP", 0, -104)

cap.name = UI.Text(cap, 12, C.goldPale, "body", "CENTER")
cap.name:SetPoint("TOP", cap, "TOP", 0, -6)
UI.OneLine(cap.name, 300)
cap.bar = CreateFrame("Frame", nil, cap)
cap.bar:SetSize(WF.BAR_W, 12)
cap.bar:SetPoint("TOP", cap, "TOP", 0, -24)
cap.bar.bg = UI.Solid(cap.bar, C.deep, "BACKGROUND")
cap.bar.bg:SetAllPoints(cap.bar)
cap.bar.a = UI.Solid(cap.bar, WM.TEAM.A.color, "BORDER", 0.85)
cap.bar.a:SetPoint("TOPLEFT", cap.bar, "TOPLEFT", 0, 0)
cap.bar.a:SetPoint("BOTTOMLEFT", cap.bar, "BOTTOMLEFT", 0, 0)
cap.bar.a:SetWidth(WF.BAR_W / 2)
cap.bar.h = UI.Solid(cap.bar, WM.TEAM.H.color, "BORDER", 0.85)
cap.bar.h:SetPoint("TOPRIGHT", cap.bar, "TOPRIGHT", 0, 0)
cap.bar.h:SetPoint("BOTTOMRIGHT", cap.bar, "BOTTOMRIGHT", 0, 0)
cap.bar.h:SetWidth(WF.BAR_W / 2)
cap.bar.n = UI.Solid(cap.bar, C.strong, "ARTWORK")
cap.bar.n:SetHeight(12)
cap.bar.n:SetPoint("CENTER", cap.bar, "CENTER", 0, 0)
cap.bar.marker = UI.Solid(cap.bar, C.goldPale, "OVERLAY")
cap.bar.marker:SetSize(3, 20)
cap.arrow = UI.Glyph(cap.bar, "left", 14, C.text, "OVERLAY")
cap.countA = UI.Text(cap, 14, WM.TEAM.A.color, "title", "RIGHT")
cap.countA:SetPoint("RIGHT", cap.bar, "LEFT", -8, 0)
cap.countH = UI.Text(cap, 14, WM.TEAM.H.color, "title")
cap.countH:SetPoint("LEFT", cap.bar, "RIGHT", 8, 0)
cap.state = UI.Text(cap, 10, C.dim, "body", "CENTER")
cap.state:SetPoint("TOP", cap.bar, "BOTTOM", 0, -5)
UI.OneLine(cap.state, 300)

WF.CAP_SAMPLE = { objId = 2, slider = -120, neutralPct = 20, state = 6, countA = 2, countH = 3, maxNet = 5 }

-- The bar the player stands at: fresh WPCAP, objectives live, not a stock zone (it has its native bar).
function WF.CapState()
    local c = S.wpCap
    if not c or not WM.ObjectivesLive() or GetTime() - (c.recvAt or 0) > WF.CAP_STALE then
        return nil
    end
    local z = S.wpZone
    if z and z.kind == "S" then
        return nil
    end
    return c
end

-- The marker's offset from the bar's centre in px: Alliance full (+1000) at the left end, Horde full at the right.
function WF.MarkerX(slider)
    return floor(-(slider or 0) / 1000 * WF.BAR_W / 2 + 0.5)
end

-- The way the bar moves: the counts' difference, at most maxNet either way (0 for none).
function WF.Net(c)
    local net = (c.countA or 0) - (c.countH or 0)
    if (c.maxNet or 0) > 0 then
        net = U.Clamp(net, -c.maxNet, c.maxNet)
    end
    return net
end

function WF.UpdateCap()
    local c = WF.CapState() or (WF.capPreview and WF.CAP_SAMPLE)
    if not c then
        if cap:IsShown() then
            cap:Hide()
        end
        return
    end
    local z = S.wpZone
    local o = z and z.byId and z.byId[c.objId]
    UI.SetText(cap.name, (o and o.name) or (z and ns.WarObjectiveName(z.zoneId, c.objId)) or "Forlorn Woods")
    local band = floor(WF.BAR_W * (c.neutralPct or 0) / 100 + 0.5)    -- neutralPct of each half, both sides
    if band >= 1 then
        cap.bar.n:SetWidth(band)
        cap.bar.n:Show()
    else
        cap.bar.n:Hide()
    end
    local x = WF.MarkerX(c.slider)
    cap.markerX = x
    cap.bar.marker:ClearAllPoints()
    cap.bar.marker:SetPoint("CENTER", cap.bar, "CENTER", x, 0)
    local net = WF.Net(c)
    cap.net = net
    cap.arrow:ClearAllPoints()
    if net > 0 then
        UI.SetGlyph(cap.arrow, "left")
        cap.arrow:SetVertexColor(UI.Rgb(WM.TEAM.A.color))
        cap.arrow:SetPoint("RIGHT", cap.bar.marker, "LEFT", -2, 0)
        cap.arrow:Show()
    elseif net < 0 then
        UI.SetGlyph(cap.arrow, "right")
        cap.arrow:SetVertexColor(UI.Rgb(WM.TEAM.H.color))
        cap.arrow:SetPoint("LEFT", cap.bar.marker, "RIGHT", 2, 0)
        cap.arrow:Show()
    else
        cap.arrow:Hide()
    end
    cap.countA:SetText(tostring(c.countA or 0))
    cap.countH:SetText(tostring(c.countH or 0))
    cap.state:SetText(WF.STATE_TEXT[c.state] or "")
    if not cap:IsShown() then
        capPos.Anchor()
        cap:Show()
    end
end

------------------------------------------------------------------------------------------------------
-- Banners (one at a time; a newer one of a kind already waiting takes its place) and toasts
------------------------------------------------------------------------------------------------------
local banner = CreateFrame("Frame", "BleakholdWarBanner", UIParent)
banner:SetSize(640, 86)
banner:SetPoint("TOP", UIParent, "TOP", 0, -196)
banner:SetFrameStrata("HIGH")
banner:EnableMouse(false)
banner:Hide()
WF.banner = banner
banner.kicker = UI.Text(banner, 15, C.text, "body", "CENTER")
banner.kicker:SetPoint("TOP", banner, "TOP", 0, 0)
UI.OneLine(banner.kicker, 620)
banner.title = UI.Text(banner, 30, WM.COLOR, "title", "CENTER")
banner.title:SetPoint("TOP", banner.kicker, "BOTTOM", 0, -2)
UI.OneLine(banner.title, 640)
banner.sub = UI.Text(banner, 13, C.mid, "body", "CENTER")
banner.sub:SetPoint("TOP", banner.title, "BOTTOM", 0, -2)
UI.OneLine(banner.sub, 600)

WF.queue = {}
WF.current = nil

-- e = { key, kicker (already safe for a FontString), title, sub (server text allowed), color }
function WF.Banner(e)
    for i, q in ipairs(WF.queue) do
        if q.key == e.key then
            WF.queue[i] = e
            return
        end
    end
    WF.queue[#WF.queue + 1] = e
    if #WF.queue > 3 then
        table.remove(WF.queue, 1)
    end
end

function WF.UpdateBanner()
    local now = GetTime()
    local cur = WF.current
    if cur and now - cur.shownAt >= WF.BANNER_TIME then
        WF.current = nil
        cur = nil
    end
    if not cur and #WF.queue > 0 then
        cur = table.remove(WF.queue, 1)
        cur.shownAt = now
        WF.current = cur
        banner.kicker:SetText(cur.kicker or "")
        UI.SetText(banner.title, cur.title or "")
        UI.SetColor(banner.title, cur.color or WM.COLOR)
        UI.SetText(banner.sub, cur.sub or "")
    end
    if not cur then
        if banner:IsShown() then
            banner:Hide()
        end
        return
    end
    local t = now - cur.shownAt
    banner:SetAlpha(U.Clamp(min(t / 0.15, (WF.BANNER_TIME - t) / 0.3), 0, 1))
    banner:Show()
end

local function amounts(honor, shards)
    local parts = {}
    if (honor or 0) > 0 then
        parts[#parts + 1] = U.Commas(honor) .. " honor"
    end
    if (shards or 0) > 0 then
        parts[#parts + 1] = U.Commas(shards) .. (shards == 1 and " Shard" or " Shards")
    end
    return table.concat(parts, ", ")
end

WF.attacked = {}     -- objId -> { at, team, zoneId } from WPEV A
WF.reward = nil      -- { text, at } from WPEV R

local EVENT_VERB = { C = "CAPTURED", N = "NEUTRALISED", A = "UNDER ATTACK" }

ns.On("WAR_EVENT", function(e)
    if not WM.Live() then
        return
    end
    local k = e.kind
    if k == "C" or k == "N" or k == "A" then
        if not WM.ObjectivesLive() then
            return
        end
        if k == "A" then
            WF.attacked[e.objId] = { at = GetTime(), team = e.team, zoneId = e.zoneId }
        end
        local who = e.team and WM.TeamName(e.team) or "someone"
        local sub = (k == "A" and ("the " .. who .. " is attacking it")) or ("by the " .. who)
        WF.Banner({ key = "o" .. e.zoneId .. ":" .. e.objId, kicker = U.Safe(e.name), title = EVENT_VERB[k], sub = sub,
            color = teamColor(e.team) })
    elseif k == "F" or k == "X" or k == "E" then
        if not WM.ObjectivesLive() then
            return
        end
        local title, sub
        if k == "F" then
            title = e.name .. ": the Front has begun"
            sub = "It lasts " .. U.Duration(e.seconds) .. ". Capture and hold its outposts."
        elseif k == "X" then
            title = "A Front starts in " .. U.Duration(e.seconds)
            sub = e.name
        elseif e.winner then
            title = "The " .. WM.TeamName(e.winner) .. " wins " .. e.name
            sub = "Alliance " .. floor(e.controlA / 10 + 0.5) .. "%  -  Horde " .. floor(e.controlH / 10 + 0.5) .. "%"
        else
            title = e.name .. ": a draw"
            sub = "Alliance " .. floor(e.controlA / 10 + 0.5) .. "%  -  Horde " .. floor(e.controlH / 10 + 0.5) .. "%"
        end
        ns.Toast.Push({ kicker = "WAR FRONT", title = title, sub = sub, target = "warmode" })
    elseif k == "W" then
        local me = e.name == ns.PlayerName()
        local sub
        if me then
            sub = "Survive the hunt, or someone claims your bounty"
        elseif e.reason == "B" then
            sub = "Killed a player far below their level"
        else
            sub = "A streak of " .. e.streak .. " kills: hunt them down"
        end
        WF.Banner({ key = "w", kicker = me and "" or classText(e.name, e.classId),
            title = me and "YOU ARE WANTED" or (e.reason == "B" and "WANTED: BULLY" or "WANTED"), sub = sub,
            color = C.red })
        if PlaySound then
            PlaySound("RaidWarning")
        end
    elseif k == "B" then
        WF.Banner({ key = "b", kicker = U.Safe(e.killer) .. " claimed the bounty on " .. U.Safe(e.victim),
            title = "BOUNTY CLAIMED", sub = amounts(e.honor, e.shards), color = C.goldLight })
    elseif k == "S" then
        WF.Banner({ key = "s", kicker = U.Safe(e.name), title = "SURVIVED THE HUNT", sub = amounts(e.honor, e.shards),
            color = C.goldLight })
    elseif k == "R" then
        WF.reward = { text = WM.RewardText(e), at = GetTime() }
        if not hud:IsShown() then
            ns.Print(U.Color(WM.COLOR, "War Mode") .. ": " .. U.Safe(WF.reward.text))
        end
    end
end)

------------------------------------------------------------------------------------------------------
-- The world map: the player's zone, the pins, the list of what has no position
------------------------------------------------------------------------------------------------------
-- The map area id of the player's zone, learnt while the world map is closed (SetMapToCurrentZone would turn the map
-- the player looks at). Until then nothing is pinned.
function WF.LearnArea()
    if not (SetMapToCurrentZone and GetCurrentMapAreaID) then
        return
    end
    if WorldMapFrame and WorldMapFrame:IsShown() then
        WF.myArea, WF.learnLater = nil, true
        return
    end
    SetMapToCurrentZone()
    local id = GetCurrentMapAreaID()
    WF.myArea = type(id) == "number" and id or nil
    WF.learnLater = nil
end

function WF.MapShowsMyZone()
    if not (WorldMapFrame and WorldMapFrame:IsShown() and GetCurrentMapAreaID) then
        return false
    end
    return WF.myArea ~= nil and GetCurrentMapAreaID() == WF.myArea
end

-- The Wanted players of the player's zone while they are fresh (WANTED comes every 5 s).
function WF.WantedNow()
    local w = S.wanted
    if not w or not WM.Live() or #w.list == 0 or GetTime() - (w.recvAt or 0) > WF.WANTED_STALE then
        return nil
    end
    if S.wpZone and S.wpZone.zoneId ~= w.zoneId then
        return nil
    end
    return w
end

local mapLayer, mapList
local objPins, wantedPins = {}, {}
WF.objPins, WF.wantedPins = objPins, wantedPins

local function newPin(glyph, fill)
    local b = UI.Badge(mapLayer, 18, glyph, fill, C.goldDark, C.text)
    b:EnableMouse(true)
    b:SetScript("OnEnter", function(self)
        if self.lines then
            UI.ShowTooltip(self, self.lines)
        end
    end)
    b:SetScript("OnLeave", function()
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    return b
end

local function ensureMap()
    if mapLayer or not WorldMapButton then
        return mapLayer
    end
    mapLayer = CreateFrame("Frame", nil, WorldMapButton)
    mapLayer:SetAllPoints(WorldMapButton)
    mapLayer:SetFrameLevel((WorldMapButton:GetFrameLevel() or 1) + 6)
    WF.mapLayer = mapLayer
    mapList = UI.Box(mapLayer, 240, 40, C.panel, C.border, 0.9)
    mapList:SetPoint("TOPLEFT", mapLayer, "TOPLEFT", 12, -12)
    mapList.lines = {}
    for i = 1, 12 do
        local l = UI.Text(mapList, 11, C.text)
        l:SetPoint("TOPLEFT", mapList, "TOPLEFT", 8, -6 - (i - 1) * 15)
        UI.OneLine(l, 224)
        mapList.lines[i] = l
    end
    mapList:Hide()
    WF.mapList = mapList
    if WorldMapFrame and WorldMapFrame.HookScript then
        WorldMapFrame:HookScript("OnHide", function()
            if WF.learnLater then
                WF.LearnArea()
            end
        end)
    end
    return mapLayer
end

-- Pixel offset of a map position (permille) from the map's top-left corner.
function WF.MapOffset(u, v)
    local w = WorldMapButton and WorldMapButton:GetWidth() or 0
    local h = WorldMapButton and WorldMapButton:GetHeight() or 0
    return u / 1000 * w, -v / 1000 * h
end

local function placePin(pin, u, v)
    local x, y = WF.MapOffset(u, v)
    pin:ClearAllPoints()
    pin:SetPoint("CENTER", mapLayer, "TOPLEFT", x, y)
    pin.u, pin.v = u, v
    pin:Show()
end

local function objectiveLines(z, o)
    local owner = o.owner == "N" and "Neutral" or ("Held by the " .. WM.TeamName(o.owner))
    local lines = { U.Safe(o.name or ns.WarObjectiveName(z.zoneId, o.objId)), { owner, teamColor(o.owner) } }
    if contested(o.state) then
        lines[#lines + 1] = { WF.STATE_TEXT[o.state], C.mid }
    end
    local side = o.slider > 0 and "Alliance" or (o.slider < 0 and "Horde" or "")
    lines[#lines + 1] = { "Bar: " .. floor(abs(o.slider) / 10 + 0.5) .. "% " .. side, C.mute }
    return lines
end

local function wantedLines(x, recvAt)
    local age = (x.ageSec or 0) + (GetTime() - (recvAt or GetTime()))
    return {
        "WANTED: " .. U.Safe(x.name),
        { x.reason == "B" and "A bully" or ("A streak of " .. x.streak .. " kills"), C.red },
        { "Bounty: " .. (amounts(x.bountyHonor, x.bountyShards) ~= "" and amounts(x.bountyHonor, x.bountyShards)
            or "none"), C.goldLight },
        { "Wanted for " .. WM.Clock(age), C.mute },
    }
end

function WF.UpdateMap()
    local layer = ensureMap()
    if not layer then
        return
    end
    if not WM.Live() or not WF.MapShowsMyZone() then
        layer:Hide()
        return
    end
    layer:Show()
    local listed = {}
    local n = 0
    local z = WM.ObjectivesLive() and S.wpZone
    if z and z.kind then
        for _, o in ipairs(z.objectives) do
            if o.u then
                n = n + 1
                local pin = objPins[n] or newPin("banner", C.chip)
                objPins[n] = pin
                pin.fill:SetVertexColor(UI.Rgb(teamColor(o.owner)))
                pin:SetAlpha(contested(o.state) and (0.45 + 0.55 * abs(sin(GetTime() * 4))) or 1)
                pin.objId = o.objId
                pin.lines = objectiveLines(z, o)
                placePin(pin, o.u, o.v)
            else
                listed[#listed + 1] = U.Color(teamColor(o.owner), U.Safe(o.name or ns.WarObjectiveName(z.zoneId,
                    o.objId)))
            end
        end
    end
    for i = n + 1, #objPins do
        objPins[i]:Hide()
    end
    n = 0
    local w = WF.WantedNow()
    for _, x in ipairs(w and w.list or {}) do
        if x.u then
            n = n + 1
            local pin = wantedPins[n] or newPin("skull", C.red)
            wantedPins[n] = pin
            pin.name = x.name
            pin.lines = wantedLines(x, w.recvAt)
            placePin(pin, x.u, x.v)
        else
            listed[#listed + 1] = U.Color(C.red, "Wanted: ") .. classText(x.name, x.classId)
        end
    end
    for i = n + 1, #wantedPins do
        wantedPins[i]:Hide()
    end
    if #listed > 0 then
        for i, l in ipairs(mapList.lines) do
            l:SetText(listed[i] or "")
        end
        mapList:SetHeight(12 + min(#listed, #mapList.lines) * 15)
        mapList:Show()
    else
        mapList:Hide()
    end
end

------------------------------------------------------------------------------------------------------
-- Minimap arrows to the player's faction's outposts under attack
------------------------------------------------------------------------------------------------------
local arrows = {}
for i = 1, WF.MAX_ARROWS do
    local a = CreateFrame("Frame", "BleakholdWarArrow" .. i, UIParent)
    a:SetSize(24, 24)
    a:SetFrameStrata("MEDIUM")
    a:SetFrameLevel(12)
    a:EnableMouse(false)
    a:Hide()
    a.tex = a:CreateTexture(nil, "OVERLAY")
    a.tex:SetTexture(WF.ARROW)
    a.tex:SetAllPoints(a)
    a.tex:SetVertexColor(UI.Rgb(C.red))
    arrows[i] = a
end
WF.arrows = arrows

-- The outposts to defend: the player's faction's, attacked lately (WPEV A by the other side) or with the other side
-- pushing their bar (states 5 and 6), with a position, and not the one the player stands at.
local NONE = {}
function WF.UnderAttack()
    local z = WM.ObjectivesLive() and S.wpZone
    local mine = WM.MyTeam()
    if not z or not z.kind or not mine or #z.objectives == 0 then
        return NONE
    end
    local out = {}
    local now = GetTime()
    for _, o in ipairs(z.objectives) do
        local hit = WF.attacked[o.objId]
        local attacked = hit and hit.zoneId == z.zoneId and now - hit.at < WF.ATTACK_TIME and hit.team ~= mine
            and o.owner == mine
        local pushed = (mine == "A" and o.state == 5) or (mine == "H" and o.state == 6)
        local here = S.wpCap and S.wpCap.objId == o.objId and now - (S.wpCap.recvAt or 0) <= WF.CAP_STALE
        if (attacked or pushed) and o.u and not here and #out < WF.MAX_ARROWS then
            out[#out + 1] = o
        end
    end
    return out
end

-- The player's place on the zone map (permille), from the client's own map while it shows the player's zone.
function WF.PlayerMapPos()
    if not (GetPlayerMapPosition and GetCurrentMapAreaID) then
        return nil
    end
    if WorldMapFrame and WorldMapFrame:IsShown() then
        if not WF.MapShowsMyZone() then
            return nil
        end
    elseif not WF.myArea or GetCurrentMapAreaID() ~= WF.myArea then
        WF.LearnArea()       -- the closed map was turned elsewhere (another addon): back to the player's zone
    end
    local x, y = GetPlayerMapPosition("player")
    if type(x) ~= "number" or type(y) ~= "number" or (x == 0 and y == 0) then
        return nil
    end
    return x * 1000, y * 1000
end

-- Screen angle (radians from the right, counter-clockwise) of a map direction on the minimap: du east, dv south.
function WF.MinimapAngle(du, dv)
    local bearing = atan2(-du * WF.MAP_ASPECT, -dv)    -- from north towards west, like GetPlayerFacing
    local rotate = GetCVar and GetCVar("rotateMinimap") == "1"
    local facing = rotate and GetPlayerFacing and GetPlayerFacing() or 0
    if type(facing) ~= "number" or facing ~= facing then
        facing = 0
    end
    return pi / 2 + bearing - facing
end

function WF.UpdateArrows()
    local list = WF.UnderAttack()
    local px, py
    if #list > 0 and Minimap then
        px, py = WF.PlayerMapPos()
    end
    for i, a in ipairs(arrows) do
        local o = px and list[i]
        local du, dv = o and (o.u - px), o and (o.v - py)
        if o and (du * du + dv * dv) > 4 then
            local ang = WF.MinimapAngle(du, dv)
            local scale = (Minimap:GetEffectiveScale() or 1) / (a:GetEffectiveScale() or 1)
            local radius = (Minimap:GetWidth() or 140) / 2 * scale - 10
            a:ClearAllPoints()
            a:SetPoint("CENTER", Minimap, "CENTER", cos(ang) * radius, sin(ang) * radius)
            a.tex:SetRotation(ang - pi / 2)
            a.objId, a.angle = o.objId, ang
            a:Show()
        else
            a:Hide()
        end
    end
end

------------------------------------------------------------------------------------------------------
-- Wiring: one tick for everything (cheap while nothing shows)
------------------------------------------------------------------------------------------------------
local mapAcc = 0
function WF.Tick()
    WF.UpdateHud()
    WF.UpdateCap()
    WF.UpdateBanner()
    WF.UpdateArrows()
    mapAcc = mapAcc + 1
    if mapAcc >= 3 and WorldMapFrame and WorldMapFrame:IsShown() then
        mapAcc = 0
        WF.UpdateMap()
    end
end

ns.Every(0.2, WF.Tick)

ns.On("STATE", function(topic)
    if topic == "WPZ" or topic == "WPCAP" or topic == "WANTED" or topic == "WMST" then
        WF.UpdateHud()
        WF.UpdateCap()
        WF.UpdateArrows()
        WF.UpdateMap()
    end
end)

-- Another zone: learn its map; the last zone's Wanted players and attacks are gone.
local function newZone()
    wipe(WF.attacked)
    if S.wanted then
        S.wanted = nil
        ns.Fire("STATE", "WANTED")
    end
    WF.LearnArea()
end

ns.RegisterEvent("ZONE_CHANGED_NEW_AREA", newZone)
ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    WF.LearnArea()
end)
ns.RegisterEvent("WORLD_MAP_UPDATE", function()
    WF.UpdateMap()
end)
ns.On("WAR_ZONE", function()
    wipe(WF.attacked)
    WF.LearnArea()
end)

ns.On("HELLO", function()
    if not WM.Live() then
        wipe(WF.queue)
        WF.current, WF.reward = nil, nil
    end
    WF.Tick()
    WF.UpdateMap()
end)

ns.On("DB_READY", function()
    hudPos.Anchor()
    capPos.Anchor()
end)

------------------------------------------------------------------------------------------------------
-- Editor mode (ns.Movers): sample content while no Front is on
------------------------------------------------------------------------------------------------------
local function mover(name, title, frame, pos, flag, sample)
    UI.AddMover({
        name = name,
        title = title,
        frame = frame,
        begin = function()
            WF[flag] = true
            sample.recvAt = GetTime()
            WF.Tick()
        end,
        finish = function()
            WF[flag] = nil
            WF.Tick()
        end,
        move = function(region, done)
            pos.MoveTo(region, done)
        end,
        reset = function()
            pos.Reset()
        end,
        isDefault = function()
            return pos.Saved() == nil
        end,
        visible = function()
            return WM.ObjectivesLive() and true or false
        end,
    })
end
mover("bleakhold_war_front", "War Front HUD", hud, hudPos, "preview", WF.SAMPLE)
mover("bleakhold_war_capture", "War Front capture bar", cap, capPos, "capPreview", WF.CAP_SAMPLE)
