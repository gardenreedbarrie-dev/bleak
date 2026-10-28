-- Bleakhold: Bleakhold Royale's drop HUD, from the lobby's DROP! to the landing (docs/BleakholdProtocol.md section 17,
-- ROYS fields 25-27: fallMsLeft, landMsLeft, fallMs). One counter at a time:
--   freefall   the drop plate low on the screen (BleakholdRoyaleDrop): FREEFALL, "Parachute opens in" and one metal
--              counter, 8 -> 1 (it never counts up: the start gun's ROYS moves the plan 0.1-0.3 s later than the
--              teleport's), the altimeter right of the character (BleakholdRoyaleAltimeter) and speed lines over the
--              world (BleakholdRoyaleSpeedLines, a WorldFrame child, so Alt-Z keeps them); wind.wav 0.5 s after
--              DROP!'s gong, cut for an 8 s fall (any other fall plays nothing)
--   canopy     the server opens the parachute by itself fallMs after the start gun: PARACHUTE "Landing in 12" over a
--              draining bar, the open canopy swaying, canopy.wav and a shine across the plate
--   landing    ROYS me 2: LANDED for 0.8 s, land.wav, and the HUD leaves (a player eliminated in the air: it just
--              leaves)
-- There is no prompt, button or key: RDEPLOY is accepted and ignored by the server. The plate enters 0.8 s after DROP!
-- (RoyaleCountdown.lua fires ROYALE_DROP_WORD; without it, the same rule: the local zero or the ROYS me 1, whichever
-- comes first), as DROP! leaves. A late drop (no lobby countdown) shows LATE DROP at once; after a /reload in the air
-- the HUD resumes where the times say, silently. An older server sends no fields 25-27: the plate then shows no
-- number until a Slow Fall (130) or Parachute (44795) aura shows, then the canopy without a timer, and the altimeter
-- needs Bleakhold.exe's BleakholdStorm_Altitude.
--
-- The view distance: at the start of phase 1 a farclip under 1277 is raised to 1277 (the island is 1600 yd across
-- and the drop starts 471 yd up), far from any beat of the countdown; the old value waits in SavedVariables
-- (royaleFarclipRestore) and goes back 8 s after the landing, when the match ends, or at the next login outside a
-- battleground (SetFarclip writes the saved CVar, so a crash in the air must not leave a weak PC at 1277). Option
-- royaleFarclip, default on (RD.SetFarclipOption).
local ADDON, ns = ...
local U, UI = ns.U, ns.UI
local S = ns.S
local R = ns.Royale
local RS = ns.RoyaleStyle
local DATA = ns.RoyaleArt

local type, tonumber, pairs, ipairs = type, tonumber, pairs, ipairs
local floor, ceil, max, min, abs = math.floor, math.ceil, math.max, math.min, math.abs

local RD = {}
ns.RoyaleDrop = RD

------------------------------------------------------------------------------------------------------
-- The fall (3.3.5 movement: the client's MovementShared.cpp and the server's MovementUtil.cpp agree)
------------------------------------------------------------------------------------------------------
RD.G = 19.29110527                      -- yd/s2
RD.VT = 60.148003                       -- terminal speed, yd/s
RD.TT = RD.VT / RD.G                    -- 3.118 s until terminal speed
RD.DT = RD.VT * RD.VT / (2 * RD.G)      -- 93.77 yd fallen by then
RD.CANOPY_VT = 7.0                      -- yd/s under the canopy (feather fall clamps the speed at once)
RD.CANOPY_DEFAULT = 12                  -- s under the canopy when no freefall ROYS told it (a /reload under it)
RD.ALT_TRUST = 40                       -- yd Bleakhold.exe's ground height may move the altimeter off the model

-- Yards fallen from rest after t seconds.
function RD.FallDistance(t)
    if not t or t <= 0 then
        return 0
    end
    if t < RD.TT then
        return RD.G * t * t / 2
    end
    return RD.DT + RD.VT * (t - RD.TT)
end

-- The drop height for a freefall of F s and C s under the canopy: 471.4 yd for 8 + 12.
function RD.DropHeight(F, C)
    return RD.CANOPY_VT * max(0, C or 0) + RD.FallDistance(F)
end

-- Yards above the landing from the times left (s): the server opens the canopy 7*C yd up and the canopy lands it
-- C s later, where C = landLeft - fallLeft.
function RD.Altitude(fallLeft, landLeft, F)
    fallLeft, landLeft = max(0, fallLeft or 0), max(0, landLeft or 0)
    if fallLeft > 0 then
        local C = max(0, landLeft - fallLeft)
        return RD.CANOPY_VT * C + RD.FallDistance(F) - RD.FallDistance((F or 0) - fallLeft)
    end
    return RD.CANOPY_VT * landLeft
end

------------------------------------------------------------------------------------------------------
-- Timing and constants
------------------------------------------------------------------------------------------------------
RD.PLATE_DELAY = 0.8          -- s after DROP!, as it leaves
RD.WIND_DELAY = 0.5           -- s after the gong, so the two never start in one frame
RD.WIND_FALL = 8              -- s of freefall wind.wav is cut for (Tools/Announcer/make_royale_sfx.py)
RD.WIND_LATE = 1              -- s the wind may still start late (a slow ROYS); later it would outlast the fall
RD.FRESH = 0.75               -- s into the fall a drop still counts as just begun (else: a /reload in the air)
RD.LANDED_HOLD = 0.8          -- s LANDED holds before the plate leaves
RD.CANOPY_AURAS = { [130] = true, [44795] = true }    -- Slow Fall, the canopy (old-server fallback)
RD.FARCLIP = 1277             -- a fresh install's view distance (ConsoleDetect.cpp)
RD.FARCLIP_HOLD = 8           -- s after the landing before it goes back
RD.FARCLIP_QUIET = 16         -- s before the drop from which a late raise would hitch on the countdown

RD.SIZE = { w = 320, h = 68 }
RD.ICON = 44                  -- the parachute illustrations
RD.TEXT_X = 64                -- the text column
RD.BAR = { w = 236, h = 5, y = -46 }  -- under the text and the counter (the spec's 200 left the right third bare)
RD.NUMERAL_CAP = 34
RD.SEP_X = 62                 -- units from the plate's right edge to the hairline before the counter
RD.ALT = { w = 44, h = 300, scaleW = 36, scaleH = 288, marker = 22, canopy = 14 }
-- the speed lines' cross-fade (ADD white): under the spec's 0.16-0.28, which read as comic-book streaks over the bright
-- island in the previews
RD.SPEED_ALPHA = { 0.1, 0.2 }

RD.TEXT = {
    freefall = "FREEFALL", late = "LATE DROP", parachute = "PARACHUTE", ground = "GROUND",
    opensIn = "Parachute opens in", opensItself = "Your parachute opens by itself.", drifting = "Drifting down.",
}

------------------------------------------------------------------------------------------------------
-- Positions: saved per character like the other Royale frames, in the frame's own units (it carries the HUD scale)
------------------------------------------------------------------------------------------------------
-- Draggable, but click-through until updateMouse says otherwise: both sit where the cursor rests while the player
-- looks around during a drop, and a click that lands on a frame never reaches the camera (CSimpleTop::OnMouseDown).
local updateMouse
local function placement(f, defPoint, defX, defY)
    UI.MakeMovable(f)
    f:EnableMouse(false)
    local p = {}
    function p.Saved()
        local pos = ns.cdb.windows[f:GetName()]
        if type(pos) == "table" and type(pos.point) == "string" and type(pos.x) == "number"
            and type(pos.y) == "number" then
            return pos
        end
    end
    function p.Anchor()
        local pos = p.Saved()
        f:ClearAllPoints()
        if pos then
            f:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, pos.x, pos.y)
        else
            f:SetPoint(defPoint, UIParent, defPoint, defX, defY)
        end
    end
    function p.MoveTo(region, save)
        local point, relPoint, x, y = UI.TopAnchorOf(region)
        if not point then
            return
        end
        local s = f:GetScale() or 1
        f:ClearAllPoints()
        f:SetPoint(point, UIParent, relPoint, x / s, y / s)
        if save then
            ns.cdb.windows[f:GetName()] = { point = point, relPoint = relPoint, x = x / s, y = y / s }
        end
    end
    function p.Reset()
        ns.cdb.windows[f:GetName()] = nil
        p.Anchor()
    end
    return p
end

------------------------------------------------------------------------------------------------------
-- The drop plate
------------------------------------------------------------------------------------------------------
local plate = CreateFrame("Frame", "BleakholdRoyaleDrop", UIParent)
plate:SetSize(RD.SIZE.w, RD.SIZE.h)
plate:SetFrameStrata("HIGH")
plate:Hide()
RS.RegisterRoot(plate)
RD.plate = plate
local platePos = placement(plate, "CENTER", 0, -230)
RD.platePos = platePos

plate.art = RS.Plate(plate, "Plate")
plate.shine = RS.Shine(plate.art)

-- the illustration's socket: a small bronze-rimmed well in the iron
local socket = CreateFrame("Frame", nil, plate)
socket:SetSize(RD.ICON + 8, RD.ICON + 8)
socket:SetPoint("LEFT", plate, "LEFT", RS.INSET - 4, 0)
plate.socket = socket
socket.art = RS.Plate(socket, "PlateTab")
socket.art:SetColor({ 0.62, 0.6, 0.58 })
plate.pack = RS.Art(socket, "Parachute", RD.ICON, RD.ICON, "ARTWORK", DATA.parachute.pack)
plate.pack:SetPoint("CENTER", socket, "CENTER", 0, 0)
plate.canopy = RS.Art(socket, "Parachute", RD.ICON, RD.ICON, "ARTWORK", DATA.parachute.canopy)
plate.canopy:SetPoint("CENTER", socket, "CENTER", 0, 0)
plate.canopy:SetAlpha(0)

-- freefall: the label, the line, the counter
local ff = CreateFrame("Frame", nil, plate)
ff:SetAllPoints(plate)
ff:SetFrameLevel(socket:GetFrameLevel() + 1)
plate.ff = ff
plate.ffLabel = RS.Text(ff, "label", 11, "bronzeHi")
plate.ffLabel:SetPoint("TOPLEFT", plate, "TOPLEFT", RD.TEXT_X, -12)
plate.ffLine = RS.Text(ff, "body", 13, "parchment")
plate.ffLine:SetPoint("TOPLEFT", plate, "TOPLEFT", RD.TEXT_X, -28)
-- the counter, centred in its window between the hairline and the right inset (a right-aligned 1 would leave the
-- window lopsided)
plate.num = RS.Numeral(ff, { cap = RD.NUMERAL_CAP, glowColor = "gold" })
plate.num:SetPoint("CENTER", plate, "RIGHT", -(RD.SEP_X + 14) / 2, 0)
-- a bronze hairline sets the counter apart, like a readout window in the iron
plate.sep = RS.Hairline(ff, 36, "bronzeLo", true, "BORDER", 0.9)
plate.sep:SetPoint("CENTER", plate, "RIGHT", -RD.SEP_X, 0)

-- canopy: the label, "Landing in N" and the bar
local cp = CreateFrame("Frame", nil, plate)
cp:SetAllPoints(plate)
cp:SetFrameLevel(socket:GetFrameLevel() + 1)
cp:SetAlpha(0)
plate.cp = cp
plate.cpLabel = RS.Text(cp, "label", 11, "bronzeHi")
plate.cpLabel:SetPoint("TOPLEFT", plate, "TOPLEFT", RD.TEXT_X, -12)
plate.cpLabel:SetText(RD.TEXT.parachute)
plate.cpLine = RS.Text(cp, "body", 13, "parchment")
plate.cpLine:SetPoint("TOPLEFT", plate, "TOPLEFT", RD.TEXT_X, -28)
-- the bar: a dark bronze track with a fine rim, the gold fill, a bright leading edge
plate.trackRim = UI.Solid(cp, RS.C.bronzeLo, "BORDER", 0.9)
plate.trackRim:SetPoint("TOPLEFT", plate, "TOPLEFT", RD.TEXT_X - 1, RD.BAR.y + 1)
plate.trackRim:SetSize(RD.BAR.w + 2, RD.BAR.h + 2)
plate.track = UI.Solid(cp, RS.C.bronzeDeep, "ARTWORK", 1)
plate.track:SetPoint("TOPLEFT", plate, "TOPLEFT", RD.TEXT_X, RD.BAR.y)
plate.track:SetSize(RD.BAR.w, RD.BAR.h)
plate.fill = UI.Solid(cp, RS.C.gold, "OVERLAY", 1)
plate.fill:SetPoint("TOPLEFT", plate.track, "TOPLEFT", 0, 0)
plate.fill:SetSize(RD.BAR.w, RD.BAR.h)
plate.edge = UI.Solid(cp, RS.C.parchment, "OVERLAY", 1)
plate.edge:SetBlendMode("ADD")
plate.edge:SetPoint("TOPRIGHT", plate.fill, "TOPRIGHT", 0, 1)
plate.edge:SetSize(2, RD.BAR.h + 2)

-- landing: the title in place of the content
plate.landed = RS.Title(plate, "LANDED", 30, "parchment")
plate.landed:SetPoint("CENTER", plate, "CENTER", 0, 0)
plate.landed:SetFrameLevel(socket:GetFrameLevel() + 2)
plate.landed:SetGlowColor("parchment")
plate.landed:SetAlpha(0)

------------------------------------------------------------------------------------------------------
-- The altimeter: the engraved scale from the drop height down to the ground, the player's chevron, the canopy mark
------------------------------------------------------------------------------------------------------
local alt = CreateFrame("Frame", "BleakholdRoyaleAltimeter", UIParent)
alt:SetSize(RD.ALT.w, RD.ALT.h)
alt:SetFrameStrata("HIGH")
alt:Hide()
RS.RegisterRoot(alt)
RD.alt = alt
local altPos = placement(alt, "CENTER", 300, 20)
RD.altPos = altPos

alt.scale = RS.Art(alt, "Altimeter", RD.ALT.scaleW, RD.ALT.scaleH, "ARTWORK")
alt.scale:SetPoint("TOP", alt, "TOP", 0, 0)
alt.canopyLine = UI.Solid(alt, RS.C.bronze, "OVERLAY", 0.9)
alt.canopyLine:SetSize(RD.ALT.scaleW - 14, 1)     -- across the scale's dark channel
alt.canopyIcon = RS.Icon(alt, "canopy", RD.ALT.canopy, "OVERLAY")
alt.marker = RS.Art(alt, "AltMarker", RD.ALT.marker, RD.ALT.marker / 2, "OVERLAY")
alt.ground = RS.Text(alt, "label", 10, "ash", "CENTER")
alt.ground:SetPoint("TOP", alt.scale, "BOTTOM", 0, -2)
alt.ground:SetText(RD.TEXT.ground)

-- Texture rows of the scale's top (the drop height) and its ground band, as fractions of its height.
local ALT_TOP, ALT_BOTTOM = DATA.altimeter.top, DATA.altimeter.bottom

-- Units from the scale's top for a height fraction (1 = the drop height, 0 = the ground), on whole pixels.
local function altY(frac)
    local y = (ALT_TOP + (1 - U.Clamp(frac, 0, 1)) * (ALT_BOTTOM - ALT_TOP)) * RD.ALT.scaleH
    return RS.Snap(y, alt)
end
RD.AltY = altY

------------------------------------------------------------------------------------------------------
-- The speed lines over the world (WorldFrame is not scaled by the UI and stays through Alt-Z)
------------------------------------------------------------------------------------------------------
local sl = CreateFrame("Frame", "BleakholdRoyaleSpeedLines", WorldFrame or UIParent)
sl:SetAllPoints(WorldFrame or UIParent)
sl:SetFrameStrata("LOW")
sl:EnableMouse(false)
sl:Hide()
RD.speedLines = sl
sl.a = RS.Art(sl, "SpeedLinesA", nil, nil, "ARTWORK")
sl.a:SetAllPoints(sl)
sl.a:SetBlendMode("ADD")
sl.b = RS.Art(sl, "SpeedLinesB", nil, nil, "ARTWORK")
sl.b:SetAllPoints(sl)
sl.b:SetBlendMode("ADD")

------------------------------------------------------------------------------------------------------
-- The drop
------------------------------------------------------------------------------------------------------
-- Per match: the lobby countdown's zero (zeroAt), whether this client saw it (countdown), DROP!'s moment (wordAt),
-- the last phase seen and whether the farclip went up.
local matches = {}
local function matchInfo(id)
    local mt = matches[id]
    if not mt then
        wipe(matches)
        mt = {}
        matches[id] = mt
    end
    return mt
end

-- The drop under way, or nil.
RD.drop = nil

local ctl = CreateFrame("Frame")    -- runs the drop while one is on (a hidden frame gets no OnUpdate)
ctl:Hide()

-- The match the HUD follows: the real one, or the sample of RD.Preview.
function RD.Source()
    return RD.sample or R.Match()
end

-- fallLeft, landLeft, F in seconds from the latest ROYS, or nil without fields 25-27.
function RD.Times(m)
    if not (m and m.fallMsLeft and m.landMsLeft and m.fallMs) then
        return nil
    end
    return ns.RoyaleLeft(m.fallMsLeft, m.recvAt), ns.RoyaleLeft(m.landMsLeft, m.recvAt), m.fallMs / 1000
end

-- Is the canopy (or Slow Fall) on the player? UnitBuff's 11th value is the spell id (ScriptEvents.cpp PushUnitAura).
function RD.CanopyAura()
    if not UnitBuff then
        return false
    end
    for i = 1, 40 do
        local name, _, _, _, _, _, _, _, _, _, id = UnitBuff("player", i)
        if not name then
            return false
        end
        if RD.CANOPY_AURAS[id] then
            return true
        end
    end
    return false
end

local function setLabel(d)
    plate.ffLabel:SetText(d.late and RD.TEXT.late or RD.TEXT.freefall)
end

-- What the freefall and canopy lines say, with or without fields 25-27.
local function setLines(fields)
    if fields then
        plate.ffLine:SetText(RD.TEXT.opensIn)
        plate.num:Show()
    else
        plate.ffLine:SetText(RD.TEXT.opensItself)
        plate.num:Hide()
    end
    if not fields then
        plate.cpLine:SetText(RD.TEXT.drifting)
    end
    for _, t in ipairs({ plate.trackRim, plate.track, plate.fill, plate.edge }) do
        if fields then t:Show() else t:Hide() end
    end
end

-- The plate back to its resting state (the next drop or sample starts from there).
local function restPlate()
    for _, r in ipairs({ plate, socket, ff, cp, plate.pack, plate.canopy, plate.landed, plate.landed.glow,
        plate.num.cur, plate.num.glow }) do
        RS.Stop(r, nil, true)
    end
    RS.StopLoop(plate.canopy, "sway")
    plate.num:ClearOld()
    plate.num.glow:SetAlpha(0)
    plate.num.cur:SetAlpha(1)
    ff:SetAlpha(1)
    cp:SetAlpha(0)
    socket:SetAlpha(1)
    plate.pack:SetAlpha(1)
    plate.canopy:SetAlpha(0)
    plate.landed:SetAlpha(0)
    plate.landed.glow:SetAlpha(0)
    plate.landed:SetZoom(1)
    plate:SetAlpha(1)
end

local function hideAll()
    restPlate()
    RS.Stop(alt, nil, true)
    RS.Stop(sl, nil, true)
    RS.StopLoop(sl.a, "shimmer")
    RS.StopLoop(sl.b, "shimmer")
    alt:SetAlpha(1)
    RS.Desaturate(alt.marker, false)
    alt.marker:SetVertexColor(1, 1, 1, 1)
    plate:Hide()
    alt:Hide()
    sl:Hide()
end

-- A panel's entrance (0.2 s outCubic: alpha 0 -> 1, from 12 units higher) and exit (0.25 s inCubic, 8 units up).
local function enter(f)
    f:SetAlpha(0)
    f:Show()
    RS.Tween(f, "alpha", 0, 1, 0.2, "outCubic")
    RS.Tween(f, "offset", { 0, 12 }, { 0, 0 }, 0.2, "outCubic")
end

local function leave(f, after)
    RS.Tween(f, "offset", nil, { 0, 8 }, 0.25, "inCubic")
    RS.Tween(f, "alpha", nil, 0, 0.25, "inCubic", { onDone = function()
        f:Hide()
        RS.Stop(f, "offset")
        if after then
            after()
        end
    end })
end

local function altimeterWanted(d)
    return d.fields or BleakholdStorm_Altitude ~= nil
end

-- wind.wav, once per drop (RoyaleCountdown.lua plays the gong and never the wind).
function RD.PlayWind()
    local d = RD.drop
    if not d or d.windDone then
        return false
    end
    d.windDone = true
    return RS.PlayFile("wind")
end

-- What the newest ROYS says about this drop: fields, the canopy time, the drop height, whether wind.wav fits.
local function refresh(d, m)
    local fallLeft, landLeft, F = RD.Times(m)
    local fields = fallLeft ~= nil
    if fields ~= d.fields then
        d.fields = fields
        setLines(fields)
    end
    if not fields then
        return
    end
    d.F = F
    if fallLeft > 0 then
        d.C = max(0, landLeft - fallLeft)
    elseif not d.C then
        d.C = max(landLeft, RD.CANOPY_DEFAULT)
    end
    d.H0 = RD.DropHeight(F, d.C)
    if d.windOk == nil then
        d.windOk = not d.resumed and fallLeft >= F - RD.FRESH and abs(F - RD.WIND_FALL) <= 0.25
    end
end

-- The player left the lobby (ROYS me 1): the speed lines now, the plate and the altimeter 0.8 s after DROP!.
local function begin(m, mt)
    hideAll()
    local now = GetTime()
    local fallLeft, _, F = RD.Times(m)
    -- a /reload in the air: no lobby countdown seen and the fall well under way
    local fresh = fallLeft == nil or fallLeft >= F - RD.FRESH
    local d = { matchId = m.matchId, startAt = now, late = false, resumed = false }
    if mt.countdown then
        d.wordAt = min(now, mt.wordAt or mt.zeroAt or now)
        if now - d.wordAt > 5 then
            d.wordAt = now
        end
    elseif fresh and (fallLeft ~= nil or m.phase >= R.PHASE.FIGHT) then
        d.late = true        -- a late arrival: no countdown, no DROP!
    else
        d.resumed = true     -- after a /reload: no wind, no entrance delay
        -- the parachute opened before the /reload: no canopy sound or shine for it
        d.openAtStart = fallLeft ~= nil and fallLeft <= 0
    end
    d.plateAt = d.wordAt and max(now, d.wordAt + RD.PLATE_DELAY) or now
    d.windAt = (d.wordAt or now) + RD.WIND_DELAY
    RD.drop = d
    updateMouse()
    setLabel(d)
    refresh(d, m)
    -- the speed lines come at once (the fall is felt while DROP! still holds), unless already under the canopy
    if not (fallLeft and fallLeft <= 0) then
        sl:SetAlpha(0)
        sl:Show()
        RS.Loop(sl.a, "shimmer", { from = RD.SPEED_ALPHA[1], to = RD.SPEED_ALPHA[2] })
        RS.Loop(sl.b, "shimmer", { from = RD.SPEED_ALPHA[2], to = RD.SPEED_ALPHA[1] })
        RS.Tween(sl, "alpha", 0, 1, 0.3, "linear")
    end
    ctl:Show()
    RD.Update()
end

local function speedLinesOut(duration)
    if not sl:IsShown() then
        return
    end
    RS.Tween(sl, "alpha", nil, 0, duration, "linear", { onDone = function()
        sl:Hide()
        RS.StopLoop(sl.a, "shimmer")
        RS.StopLoop(sl.b, "shimmer")
    end })
end

local function showPlate(d)
    d.plateIn = true
    restPlate()
    setLabel(d)
    setLines(d.fields)
    if d.canopy then
        ff:SetAlpha(0)
        cp:SetAlpha(1)
        plate.pack:SetAlpha(0)
        plate.canopy:SetAlpha(1)
        RS.Loop(plate.canopy, "sway", { origin = { "TOP", 0, 0 } })
    end
    if d.shown then
        plate.num:SetValue(d.shown)
    end
    if not plate:IsShown() then
        platePos.Anchor()
    end
    enter(plate)
    if altimeterWanted(d) then
        if not alt:IsShown() then
            altPos.Anchor()
        end
        enter(alt)
    end
end

-- The parachute is open: cross-fade to the canopy (0.2 s), canopy.wav, a shine, the speed lines out (0.4 s).
local function toCanopy(d, landLeft, now)
    d.canopy = true
    d.canopyAt = now
    d.canopyTotal = landLeft and max(landLeft, 0.1) or nil
    if not d.openAtStart then
        RS.PlayFile("canopy")
    end
    speedLinesOut(0.4)
    -- the marker turns from gold to parchment (the art is baked gold: grey it first, then tint)
    RS.Desaturate(alt.marker, true)
    alt.marker:SetVertexColor(RS.Rgb("parchment"))
    if not d.plateIn then
        return
    end
    RS.Tween(ff, "alpha", nil, 0, 0.2, "linear")
    RS.Tween(cp, "alpha", nil, 1, 0.2, "linear")
    RS.Tween(plate.pack, "alpha", nil, 0, 0.2, "linear")
    RS.Tween(plate.canopy, "alpha", nil, 1, 0.2, "linear")
    RS.Loop(plate.canopy, "sway", { origin = { "TOP", 0, 0 } })
    if not d.openAtStart then
        RS.Sweep(plate.shine, 0.1, 0.6)
    end
end

-- The freefall counter: ceil(fallLeft), never up. A change drops in from 20 units higher (0.18 s) with a gold glow.
local function updateCounter(d, fallLeft)
    local v = max(1, ceil(fallLeft - 1e-6))
    if d.shown and v >= d.shown then
        return
    end
    local first = d.shown == nil
    d.shown = v
    if not d.plateIn then
        return
    end
    local n = plate.num
    if first or n:GetValue() == "" then
        n:SetValue(v)
        return
    end
    n:Swap(v)
    RS.Tween(n.old, "alpha", nil, 0, 0.1, "inCubic", { onDone = function() n:ClearOld() end })
    RS.Tween(n.cur, "offset", { 0, 20 }, { 0, 0 }, 0.18, "outCubic")
    RS.Tween(n.cur, "alpha", 0, 1, 0.1, "linear")
    RS.Tween(n.glow, "alpha", 0.3, 0, 0.3, "linear")
end

local function updateCanopy(d, landLeft)
    if not (landLeft and d.fields) then
        return
    end
    local n = max(1, ceil(landLeft - 1e-6))
    if n ~= d.lineN then
        d.lineN = n
        plate.cpLine:SetText("Landing in " .. n)
    end
    if landLeft > (d.canopyTotal or 0) then
        d.canopyTotal = landLeft
    end
    local frac = U.Clamp(landLeft / max(d.canopyTotal or landLeft, 0.1), 0, 1)
    local w = RS.Snap(RD.BAR.w * frac, plate)
    if w < 0.5 then
        plate.fill:Hide()
        plate.edge:Hide()
    else
        plate.fill:SetWidth(w)
        plate.fill:Show()
        plate.edge:Show()
    end
end

local function updateAltimeter(d, fallLeft, landLeft, F)
    if not alt:IsShown() then
        return
    end
    local model = fallLeft and RD.Altitude(fallLeft, landLeft, F)
    local real = BleakholdStorm_Altitude and BleakholdStorm_Altitude()
    if type(real) ~= "number" or real ~= real then
        real = nil
    end
    local a
    if model then
        a = real and U.Clamp(real, model - RD.ALT_TRUST, model + RD.ALT_TRUST) or model
    elseif real then
        a = real
        d.altMax = max(d.altMax or 0, real, 60)
    end
    local top = d.fields and d.H0 or d.altMax
    if not a or not top or top <= 0 then
        alt.marker:Hide()
        return
    end
    local y = altY(a / top)
    alt.marker:ClearAllPoints()
    alt.marker:SetPoint("RIGHT", alt.scale, "TOPLEFT", 6, -y)
    alt.marker:Show()
    if d.fields and d.C then
        local cy = altY(RD.CANOPY_VT * d.C / top)
        alt.canopyLine:ClearAllPoints()
        alt.canopyLine:SetPoint("CENTER", alt.scale, "TOP", 0, -cy)
        alt.canopyLine:Show()
        alt.canopyIcon:ClearAllPoints()
        alt.canopyIcon:SetPoint("LEFT", alt.scale, "TOPRIGHT", 3, -cy)
        alt.canopyIcon:Show()
    else
        alt.canopyLine:Hide()
        alt.canopyIcon:Hide()
    end
end

-- Landed (ROYS me 2): LANDED alone on the plate for 0.8 s (the illustration goes too: an open canopy under LANDED
-- would contradict it), land.wav; the altimeter and the lines go.
local function land(d)
    d.ending = GetTime() + RD.LANDED_HOLD
    d.landed = true
    RS.StopLoop(plate.canopy, "sway")
    speedLinesOut(0.2)
    if alt:IsShown() then
        leave(alt)
    end
    if not plate:IsShown() then
        platePos.Anchor()
        enter(plate)
    end
    RS.Tween(ff, "alpha", nil, 0, 0.15, "linear")
    RS.Tween(cp, "alpha", nil, 0, 0.15, "linear")
    RS.Tween(socket, "alpha", nil, 0, 0.15, "linear")
    RS.Tween(plate.landed, "alpha", 0, 1, 0.15, "linear")
    RS.Tween(plate.landed, "zoom", 1.15, 1, 0.22, "outBack")
    RS.Tween(plate.landed.glow, "alpha", 0.5, 0, 0.6, "linear")
    RS.PlayFile("land")
end

-- The HUD's last frame: everything put away, the driver asleep.
local function finish()
    RD.drop = nil
    hideAll()
    ctl:Hide()
end

-- Eliminated in the air, gone from the match: the HUD just leaves (0.25 s), no LANDED.
local function abort(d, now)
    d.ending = now
    d.aborted = true
    RS.StopLoop(plate.canopy, "sway")
    speedLinesOut(0.2)
    if alt:IsShown() then
        leave(alt)
    end
end

function RD.Update()
    local d = RD.drop
    if not d then
        ctl:Hide()
        return
    end
    local now = GetTime()
    if d.ending then
        if now >= d.ending and not d.leaving then
            d.leaving = true
            if plate:IsShown() then
                leave(plate, finish)
            else
                finish()
            end
        end
        return
    end
    local m = RD.Source()
    if not m or m.matchId ~= d.matchId then
        finish()
        return
    end
    if m.me ~= R.ME.DROPPING then
        if m.me == R.ME.ALIVE or m.me == R.ME.WINNER then
            land(d)
        else
            abort(d, now)
        end
        return
    end
    local fallLeft, landLeft, F = RD.Times(m)
    -- wind.wav 0.5 s after the gong, only for the fall it is cut for
    if d.windOk and not d.windDone and now >= d.windAt then
        if now - d.windAt <= RD.WIND_LATE then
            RD.PlayWind()
        else
            d.windDone = true
        end
    end
    if not d.canopy then
        local open
        if fallLeft then
            open = fallLeft <= 0
        elseif now >= (d.auraAt or 0) then
            d.auraAt = now + 0.1
            open = RD.CanopyAura()
        end
        if open then
            toCanopy(d, landLeft, now)
        elseif fallLeft then
            updateCounter(d, fallLeft)
        end
    end
    if not d.plateIn and now >= d.plateAt then
        showPlate(d)
    end
    if d.canopy then
        updateCanopy(d, landLeft)
    end
    updateAltimeter(d, fallLeft, landLeft, F)
end

ctl:SetScript("OnUpdate", function()
    RD.Update()
end)

------------------------------------------------------------------------------------------------------
-- The view distance (royaleFarclip)
------------------------------------------------------------------------------------------------------
function RD.FarclipOption()
    return ns.Option("royaleFarclip", true) ~= false
end

-- Raises a farclip under RD.FARCLIP to it, keeping the player's value in SavedVariables (an older one waiting there
-- stays: it is the player's own). Returns true when it raised it.
function RD.RaiseFarclip()
    if not (RD.FarclipOption() and GetFarclip and SetFarclip) then
        return false
    end
    local cur = tonumber(GetFarclip())
    if not cur or cur >= RD.FARCLIP then
        return false
    end
    if type(ns.db.royaleFarclipRestore) ~= "number" then
        ns.db.royaleFarclipRestore = cur
    end
    SetFarclip(RD.FARCLIP)
    return true
end

-- Puts the player's farclip back, unless they chose another one since (the options panel writes the same CVar).
function RD.RestoreFarclip()
    RD.farclipTimer = nil
    local old = ns.db.royaleFarclipRestore
    if old == nil then
        return false
    end
    ns.db.royaleFarclipRestore = nil
    if type(old) ~= "number" or old ~= old or old <= 0 or not (SetFarclip and GetFarclip) then
        return false
    end
    if tonumber(GetFarclip()) ~= RD.FARCLIP then
        return false
    end
    SetFarclip(old)
    return true
end

local function restoreLater(sec)
    if RD.farclipTimer or ns.db.royaleFarclipRestore == nil then
        return
    end
    local t = {}
    RD.farclipTimer = t
    ns.After(sec, function()
        if RD.farclipTimer == t then
            RD.RestoreFarclip()
        end
    end)
end

-- /bh royale farclip on|off (Royale.lua): off puts a raised farclip back at once.
function RD.SetFarclipOption(on)
    ns.db.options.royaleFarclip = on and true or false
    if not on then
        RD.RestoreFarclip()
    end
end

local function farclipState(m, mt, prevPhase)
    if m.phase == R.PHASE.COUNTDOWN and m.me == R.ME.LOBBY and not mt.farclip then
        mt.farclip = true
        local left = R.PhaseLeft(m)
        if prevPhase == R.PHASE.ARRIVING or (left and left > RD.FARCLIP_QUIET) then
            RD.RaiseFarclip()
        end
    end
    if ns.db.royaleFarclipRestore == nil then
        return
    end
    if m.phase >= R.PHASE.VICTORY then
        RD.RestoreFarclip()
    elseif m.me ~= R.ME.LOBBY and m.me ~= R.ME.DROPPING then
        restoreLater(RD.FARCLIP_HOLD)
    end
end

------------------------------------------------------------------------------------------------------
-- Wiring
------------------------------------------------------------------------------------------------------
-- Every ROYS: the lobby countdown's zero, a drop starting, landing or ending, the farclip.
function RD.OnState()
    if RD.sample then
        return
    end
    local m = R.Match()
    if not m then
        if RD.drop then
            finish()
        end
        if ns.db.royaleFarclipRestore ~= nil and not S.royale then
            RD.RestoreFarclip()
        end
        return
    end
    local mt = matchInfo(m.matchId)
    local prevPhase = mt.phase
    mt.phase = m.phase
    if m.phase == R.PHASE.COUNTDOWN and m.me == R.ME.LOBBY then
        mt.countdown = true
        if (m.phaseMsLeft or 0) > 0 then
            mt.zeroAt = m.recvAt + m.phaseMsLeft / 1000
        end
    end
    farclipState(m, mt, prevPhase)
    local d = RD.drop
    if m.me == R.ME.DROPPING then
        if not d or d.matchId ~= m.matchId or d.ending then
            begin(m, mt)
        else
            refresh(d, m)
            RD.Update()
        end
    elseif d and not d.ending then
        RD.Update()
    end
end

ns.On("STATE", function(topic)
    if topic == "ROYS" then
        RD.OnState()
    end
end)

-- DROP! showed (RoyaleCountdown.lua): the plate follows it by 0.8 s, the wind by 0.5 s.
ns.On("ROYALE_DROP_WORD", function(m)
    m = m or S.royale
    if not m or not m.matchId then
        return
    end
    local now = GetTime()
    local mt = matchInfo(m.matchId)
    mt.wordAt = min(mt.wordAt or now, now)
    local d = RD.drop
    if d and d.matchId == m.matchId and not d.plateIn and not d.late and not d.resumed then
        d.wordAt = min(d.wordAt or now, now)
        d.plateAt = max(now, d.wordAt + RD.PLATE_DELAY)
        d.windAt = d.wordAt + RD.WIND_DELAY
    end
end)

ns.On("ROYALE_MATCH", function(m)
    -- a record that (re)appears starts clean: /bh demo again under its fixed id must not keep the last DROP!'s time
    matches[m.matchId] = nil
    matchInfo(m.matchId)
end)

-- The next login outside a battleground puts back a farclip a crash or a disconnect left raised.
ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    if ns.db.royaleFarclipRestore ~= nil and not R.InBattleground() and not R.Match() then
        RD.RestoreFarclip()
    end
end)

ns.On("DB_READY", function()
    platePos.Anchor()
    altPos.Anchor()
end)

------------------------------------------------------------------------------------------------------
-- Sample drops: /bh royale preview drop (Royale.lua) and AddicatUI's editor mode (ns.Movers)
------------------------------------------------------------------------------------------------------
-- A whole drop with the default times (8 s + 12 s) through the real code, as if DROP! showed now. Not during a match.
function RD.Preview()
    if R.Match() then
        return false
    end
    local now = GetTime()
    RD.sample = { matchId = -1, phase = R.PHASE.DROP, me = R.ME.DROPPING, fallMsLeft = 8000, landMsLeft = 20000,
        fallMs = 8000, recvAt = now }
    local mt = { countdown = true, wordAt = now }
    begin(RD.sample, mt)
    ns.After(20.5, function()
        if RD.sample and RD.sample.recvAt == now then
            RD.sample.me = R.ME.ALIVE
            ns.After(1.2, function()
                if RD.sample and RD.sample.recvAt == now then
                    RD.sample = nil
                end
            end)
        end
    end)
    return true
end

-- Editor mode: the plate and the altimeter standing still at 5 s into the fall.
local editing = {}

-- The plate and the altimeter take the mouse only to be dragged into place under a sample (/bh royale preview drop,
-- the editor's still frames; AddicatUI's editor moves them through its own handle either way), never in a real drop.
updateMouse = function()
    local live = RD.drop ~= nil and RD.sample == nil
    local on = not live and (RD.sample ~= nil or next(editing) ~= nil)
    plate:EnableMouse(on)
    alt:EnableMouse(on)
end

local function showStill()
    if RD.drop then
        return
    end
    restPlate()
    local d = { late = false, fields = true, shown = 3, C = 12, H0 = RD.DropHeight(8, 12) }
    setLabel(d)
    setLines(true)
    plate.num:SetValue(3)
    platePos.Anchor()
    plate:Show()
    altPos.Anchor()
    alt:Show()
    updateAltimeter(d, 3, 15, 8)
    updateMouse()
end

local function hideStill()
    if not RD.drop and not next(editing) then
        hideAll()
    end
end

local function mover(name, title, frame, pos)
    UI.AddMover({
        name = name,
        title = title,
        frame = frame,
        begin = function()
            editing[name] = true
            showStill()
        end,
        finish = function()
            editing[name] = nil
            hideStill()
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
            return R.Live() and true or false
        end,
    })
end
mover("bleakhold_royale_drop", "Bleakhold Royale drop plate", plate, platePos)
mover("bleakhold_royale_altimeter", "Bleakhold Royale altimeter", alt, altPos)
