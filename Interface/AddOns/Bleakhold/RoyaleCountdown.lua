-- Bleakhold: Bleakhold Royale's drop countdown (frame BleakholdRoyaleCountdown; docs/BleakholdProtocol.md section 17):
-- the last 15 s of the lobby in an engraved bronze ring, one forged metal numeral per second, then DROP!.
--
--   trigger    phase 1 and R.PhaseLeft <= 15.25 (the server sends an exact ROYS at 15000 ms: revealing circle 1 marks
--              every player dirty). It ends at the drop (ROYS me 1 or phase 2, or the local clock's zero, whichever
--              comes first: DROP! shows either way) or when the phase leaves 1; a cancelled match shows MATCH CANCELLED
--              instead, with no gong. A late arrival (me 1 without the lobby) never sees it.
--   the clock  the target time comes from every phase-1 ROYS: within 0.35 s of the running one it is kept (a ROYS's
--              arrival jitter would otherwise move every second's beat); beyond that the next numeral change jumps to
--              the right second, and the numbers in between are skipped without animation. It never restarts and never
--              counts up (the old centre countdown restarted whenever the drift passed 0.5 s).
--   rhythm     three tiers, so the beat builds: 15-11 calm (a short drop, tick.wav), 10-4 heavier (a longer drop with
--              a punch, a dust ring at the baseline, a gold flash), 3-2-1 the hero (bigger, an ember flare, two shock
--              rings, hammer hits rising in pitch). While n shows, the first n notches of the ring (from the top,
--              clockwise) are lit: one goes dark each second, and the last three burn ember.
--   T-3.6      during the "4", away from the loud beats: the pin locks locally (RC.Locked, ROYALE_PIN_LOCKED for the
--              map), an open lobby map closes with no sound, and a docked countdown glides to the centre, done at
--              T-3.3, before the "3" lands. The server's own lock at T-3 (PinLockSec) stays the authority.
--   docking    while the lobby map is open (it docks left of the screen's centre) and the room right of the centre,
--              W/2 - 24 - 16, takes the countdown at the HUD scale, the countdown's left edge sits 24 units right of
--              the centre; else it is centred, and a map that opened by itself closes when the countdown starts.
--              Computed when the countdown starts, when the map opens or closes, and on a new screen size or HUD
--              scale, never during a glide.
--   one clock  RC.OwnsClock(m): the top bar shows no time of its own while the countdown runs.
-- Timing is driven by the frame's own OnUpdate while it shows (each numeral changes on the frame it is due), the
-- motion by RS.Tween; with reduced motion every tween jumps to its end and the holds keep their length.
-- Sounds: tick.wav for 15-4, tick3/tick2/tick1, the gong at DROP!. The freefall wind is RoyaleDrop.lua's: it starts
-- 0.5 s after ROYALE_DROP_WORD, which this module fires when DROP! shows.
local ADDON, ns = ...
local U, UI = ns.U, ns.UI
local S = ns.S
local R = ns.Royale
local RS = ns.RoyaleStyle
local DATA = ns.RoyaleArt

local floor, ceil, max, min, abs, cos, sin, sqrt, pi = math.floor, math.ceil, math.max, math.min, math.abs, math.cos,
    math.sin, math.sqrt, math.pi
local strformat = string.format

local RC = {}
ns.RoyaleCountdown = RC

RC.FROM = 15                     -- the first number (the server reveals circle 1 and sends ROYS at 15000 ms)
RC.EARLY = 0.25                  -- s before T-15 the countdown may start (its 15 shows a little longer, never a 16)
RC.MIN_LEFT = 0.25               -- no countdown for less time than this: the drop is already there
RC.W, RC.H = 420, 372
RC.TOP = 112                     -- the frame's top, under the top bar's tab (-98; lower at a HUD scale over 1.14)
RC.RING = DATA.countdown.ringUnits or 280
RC.RING_Y = -174                 -- the ring's centre from the frame's top
RC.NOTCH = 22                    -- a notch's visual size (its square region is that x sqrt 2)
RC.STAGE_FROM = 0.92             -- the ring grows from this to 1 as it assembles
RC.DOCK_GAP, RC.DOCK_MARGIN = 24, 16
RC.LOCK_AT = 3.6                 -- s before the drop: the local pin lock, the silent map close, the glide
RC.REMIND = 2.5                  -- s line 2 names the locked landing after M during the lock (RC.Remind)
RC.GLIDE = 0.3
RC.DRIFT = 0.35                  -- s: a server time this far off the running one moves the count
RC.CAP_TWO = DATA.countdown.twoDigitCap or 112   -- 15-10: the widest fills at most 88 % of the ring's inner disc
RC.CAP_ONE, RC.CAP_HERO = 150, 172               -- 9-4, 3-1
RC.DROP_CAP = 96
RC.DROP_HOLD, RC.DROP_FADE = 0.8, 0.3            -- DROP! holds, then the frame fades (gone 1.1 s after it showed)
RC.CANCEL_CAP, RC.CANCEL_HOLD, RC.OUT_FADE = 22, 1.5, 0.25
RC.LIT, RC.DARK, RC.HOT, RC.DARK_ALPHA = "bronzeHi", "bronzeDeep", "ember", 0.9
RC.GONG = "Gong (Non-Looping)"

-- The three tiers: rise = units the incoming numeral drops from, dur = its fall (s), punch = the size it lands from
-- (outBack), glow = its flash { colour, alpha, s }, dust = a ring kicked up at its baseline, shocks = shock rings from
-- the ring's centre.
RC.TIERS = {
    { name = "calm", rise = 24, dur = 0.18 },
    { name = "heavy", rise = 60, dur = 0.22, punch = 1.12, glow = { "gold", 0.35, 0.4 }, dust = true },
    { name = "hero", rise = 90, dur = 0.22, punch = 1.18, glow = { "ember", 0.8, 0.5 }, shocks = 2 },
}

function RC.Tier(n)
    if n <= 3 then
        return RC.TIERS[3]
    elseif n <= 10 then
        return RC.TIERS[2]
    end
    return RC.TIERS[1]
end

function RC.Cap(n)
    if n >= 10 then
        return RC.CAP_TWO
    elseif n > 3 then
        return RC.CAP_ONE
    end
    return RC.CAP_HERO
end

-- The sound (Sounds\Royale) of a number landing.
function RC.Sound(n)
    return n <= 3 and ("tick" .. n) or "tick"
end

-- The number shown with `left` seconds to go: 15 from 15.25 down to just above 14, ..., 1 in the last second.
function RC.ValueFor(left)
    return U.Clamp(ceil(left - 1e-6), 1, RC.FROM)
end

-- The countdown runs (phase 1, at most 15.25 s left): the bar's middle cell shows no time of its own then.
function RC.OwnsClock(m)
    m = m or R.Match()
    if not m or m.phase ~= R.PHASE.COUNTDOWN then
        return false
    end
    local left = R.PhaseLeft(m)
    return left ~= nil and left <= RC.FROM + RC.EARLY
end

------------------------------------------------------------------------------------------------------
-- The frame
------------------------------------------------------------------------------------------------------
local f = CreateFrame("Frame", "BleakholdRoyaleCountdown", UIParent)
f:SetSize(RC.W, RC.H)
f:SetFrameStrata("DIALOG")
f:EnableMouse(false)
f:SetPoint("TOP", UIParent, "TOP", 0, -RC.TOP)
f:Hide()
RC.frame = f
RS.RegisterRoot(f)
local base = f:GetFrameLevel()

-- the kicker: an engraved tab over the ring
local kick = CreateFrame("Frame", nil, f)
kick:SetSize(200, 26)
kick:SetPoint("TOP", f, "TOP", 0, 0)
kick:SetFrameLevel(base + 1)
RS.Plate(kick, "PlateTab")
kick.text = RS.Text(kick, "label", 13, "bronzeHi", "CENTER")
kick.text:SetPoint("CENTER", kick, "CENTER", 0, 0)
kick.text:SetText("DROP IN")
f.kick = kick

-- the stage: the ring and its notches in one frame, so the entrance grows them together
local stage = CreateFrame("Frame", nil, f)
stage:SetSize(RC.RING, RC.RING)
stage:SetFrameLevel(base + 1)
f.stage = stage

-- k: the stage's size factor (its offsets are in its own scale, so the centre stays where it is)
local function placeStage(k)
    stage:SetScale(k)
    stage:ClearAllPoints()
    stage:SetPoint("CENTER", f, "TOP", 0, RC.RING_Y / k)
end
placeStage(1)

stage.ring = RS.Art(stage, "CountRing", RC.RING, RC.RING, "BACKGROUND")
stage.ring:SetPoint("CENTER", stage, "CENTER", 0, 0)
stage.notches = {}
for i, sock in ipairs(DATA.ring.sockets) do
    local t = RS.Rotatable(stage, "Notch", RC.NOTCH, "BORDER")
    t:SetPoint("CENTER", stage, "CENTER", cos(sock.angle) * sock.r * RC.RING, sin(sock.angle) * sock.r * RC.RING)
    t:SetAngle(sock.angle - pi / 2)   -- the art's tick stands upright: turned to face the centre
    stage.notches[i] = t
end

-- shock and dust rings, above the ring and under the numerals (the digits stand in them)
local fx = CreateFrame("Frame", nil, f)
fx:SetAllPoints(f)
fx:SetFrameLevel(base + 2)
f.fx = fx
local function newShock(parent, art)
    local t = RS.Art(parent, art or "Shock", 96, 96, "ARTWORK")
    t:SetAlpha(0)
    t:Hide()
    return t
end
f.shocks = { newShock(fx), newShock(fx) }
f.bigShock = newShock(fx)
-- the dust ring is the small ring squashed to a ground plane: its height stays within the 2.2x minification rule
f.dust = newShock(fx, "ShockSmall")

-- the numeral, its cap's middle on the ring's centre (explicit levels: glow over the digits, outgoing under them)
local num = RS.Numeral(f, { cap = RC.CAP_TWO, glowColor = "gold" })
num:SetPoint("CENTER", f, "TOP", 0, RC.RING_Y)
num:SetFrameLevel(base + 3)
num.old:SetFrameLevel(base + 5)
num.cur:SetFrameLevel(base + 6)
num:SetGlowOver(true)
f.num = num

-- DROP! and MATCH CANCELLED, on the ring's centre
local drop = RS.DropWord(f, RC.DROP_CAP)
drop:SetPoint("CENTER", f, "TOP", 0, RC.RING_Y)
drop:SetFrameLevel(base + 8)
drop:Hide()
f.drop = drop

local cancel = RS.Title(f, "MATCH CANCELLED", RC.CANCEL_CAP, "blood")
cancel:SetPoint("CENTER", f, "TOP", 0, RC.RING_Y)
cancel:SetFrameLevel(base + 8)
cancel:Hide()
f.cancel = cancel

-- the two lines under the ring, on a soft dark pill: the island is bright sand and water at noon
local lines = CreateFrame("Frame", nil, f)
lines:SetSize(RC.W - 20, 52)
lines:SetPoint("TOP", f, "TOP", 0, -318)
lines:SetFrameLevel(base + 1)
lines.back = RS.Plate(lines, "LabelHalo", { corner = 10 })
lines.back:SetAlpha(0.85)
f.lines = lines
local function line(size, y)
    local fs = RS.Text(lines, "body", size, "parchment", "CENTER")
    fs:SetPoint("TOP", f, "TOP", 0, y)
    fs:SetWidth(RC.W - 20)
    fs:SetHeight(size + 4)
    fs:SetNonSpaceWrap(false)
    return fs
end
f.line1 = line(13, -324)
f.line2 = line(12, -346)
RC.LINES_PAD, RC.LINES_MIN = 48, 220   -- the pill: the longer line plus this, at least this wide

-- The pill hugs the longer line (only when a text changes).
local function fitLines()
    local w = max(f.line1:GetStringWidth() or 0, f.line2:GetStringWidth() or 0) + RC.LINES_PAD
    lines:SetWidth(U.Clamp(floor(w + 0.5), RC.LINES_MIN, RC.W - 10))
end

------------------------------------------------------------------------------------------------------
-- A run: one countdown from its entrance to DROP! (or its exit)
------------------------------------------------------------------------------------------------------
-- mode: nil (idle), "count", "drop", "cancel" or "out"; endsAt: GetTime() of the drop; shown: the number shown;
-- x: the frame's centre, in UIParent units from the screen's centre.
local run = {}
RC.run = run
local serial = 0
-- keys of the run's number tweens: the ring's growth and the docking glide run side by side
local stageKey, glideKey = {}, {}

local function rgba(token, alpha)
    return { RS.Rgb(token, alpha) }
end

local function stopAll()
    RS.Stop(stageKey)
    RS.Stop(glideKey)
    RS.Stop(f)
    RS.Stop(stage)
    RS.Stop(kick)
    RS.Stop(num)
    RS.Stop(num.cur)
    RS.Stop(num.glow)
    RS.Stop(num.old)
    RS.Stop(drop)
    RS.Stop(drop.glow)
    RS.Stop(cancel)
    RS.Stop(lines)
    for _, t in ipairs(stage.notches) do
        RS.Stop(t)
    end
    for _, t in ipairs({ f.shocks[1], f.shocks[2], f.bigShock, f.dust }) do
        RS.Stop(t)
        t:Hide()
    end
end

local function finish()
    stopAll()
    drop:Hide()
    cancel:Hide()
    f:Hide()
    wipe(run)
end

-- Every part back to its resting state, for a new run.
local function resetVisuals()
    stopAll()
    f:SetAlpha(1)
    kick:SetAlpha(1)
    stage:SetAlpha(1)
    placeStage(1)
    lines:SetAlpha(1)
    num:SetAlpha(1)
    num:ClearOld()
    num:SetZoom(1)
    num.cur:SetAlpha(1)
    num.glow:SetAlpha(0)
    num:Show()
    for _, t in ipairs(stage.notches) do
        t:SetVertexColor(RS.Rgb(RC.DARK, RC.DARK_ALPHA))
    end
    drop:Hide()
    drop:SetZoom(1)
    drop.glow:SetAlpha(0)
    cancel:Hide()
    cancel:SetAlpha(1)
end

------------------------------------------------------------------------------------------------------
-- Docking beside the lobby map
------------------------------------------------------------------------------------------------------
local function mapFrame()
    local MP = ns.RoyaleMap
    return MP and MP.frame
end

-- The lobby map is open (in phase 0 and 1 every open docks it left of the centre, RoyaleMap.lua).
local function mapUp(m)
    local w = mapFrame()
    return w ~= nil and w:IsShown() and m ~= nil and m.phase <= R.PHASE.COUNTDOWN and true or false
end

-- The frame's centre (UIParent units right of the screen's centre) docked beside the map, or nil when the room right
-- of the centre is narrower than the countdown at the HUD scale.
function RC.DockX()
    local s = f:GetScale()
    local free = UIParent:GetWidth() / 2 - RC.DOCK_GAP - RC.DOCK_MARGIN
    if free + 1e-6 < RC.W * s then
        return nil
    end
    return RC.DOCK_GAP + RC.W * s / 2
end

-- The frame's top, in UIParent units under the screen's top: under the top bar's tab at the HUD scale (RoyaleHud.lua's
-- H.LobbyTop, the docked map's top too), at least RC.TOP.
function RC.Top()
    local H = ns.RoyaleHud
    return max(RC.TOP, H and H.LobbyTop and H.LobbyTop() or 0)
end

local function place(x)
    run.x = x
    local s = f:GetScale()
    f:ClearAllPoints()
    f:SetPoint("TOP", UIParent, "TOP", x / s, -RC.Top() / s)
end

local function wantedX(m)
    if run.locked or not mapUp(m) then
        return 0
    end
    return RC.DockX() or 0
end

local function glideTo(x)
    if abs((run.x or 0) - x) < 0.01 then
        return
    end
    run.gliding = true
    RS.Tween(glideKey, "number", run.x or 0, x, RC.GLIDE, "inOutSine", {
        set = place,
        onDone = function() run.gliding = nil end,
    })
end

-- Closes the lobby map without its close sound (RoyaleMap.lua's MP.Close(true); an older map window only hides).
local function closeMap()
    local MP = ns.RoyaleMap
    local w = mapFrame()
    if not (w and w:IsShown()) then
        return
    end
    if MP.Close then
        MP.Close(true)
    else
        w:Hide()
    end
end

------------------------------------------------------------------------------------------------------
-- The lines under the ring
------------------------------------------------------------------------------------------------------
-- The place a pin lands near: RoyaleMap.lua's MP.NearestPlace, or the same rule (a landmark or crossing whose circle,
-- r x 1.5, holds the point; the nearest centre wins; else "the wilds").
function RC.PlaceName(x, y)
    local MP = ns.RoyaleMap
    if MP and MP.NearestPlace then
        return MP.NearestPlace(x, y)
    end
    local best, bestD
    local map = S.royaleMap
    for _, p in ipairs(map and map.pois or {}) do
        if (p.kind == "L" or p.kind == "C") and p.name then
            local d = sqrt((x - p.x) ^ 2 + (y - p.y) ^ 2)
            if d <= (p.r or 0) * 1.5 and (not bestD or d < bestD) then
                best, bestD = p.name, d
            end
        end
    end
    return best or "the wilds"
end

-- Line 1 and 2 (text, colour) for a match in its last 15 s.
function RC.Lines(m)
    local l1
    if m.nextR then
        local total = R.StageCount(m)
        l1 = strformat("Circle %d of %d is on your map.", U.Clamp((m.stage or 0) + 1, 1, total), total)
    else
        l1 = "The storm gathers."
    end
    local l2, c2
    if not (m.pinX and m.pinY) then
        l2, c2 = "No landing chosen. You drop at random.", "ember"
    elseif RC.Locked(m) and run.remindUntil and GetTime() < run.remindUntil then
        l2, c2 = "Landing locked at " .. RC.PlaceName(m.pinX, m.pinY), "gold"
    elseif RC.Locked(m) then
        l2, c2 = "Landing locked", "ash"
    else
        l2, c2 = "Landing at " .. RC.PlaceName(m.pinX, m.pinY), "gold"
    end
    return l1, l2, c2
end

local function refreshLines(m)
    local l1, l2, c2 = RC.Lines(m)
    local changed = false
    if f.line1.rcText ~= l1 then
        f.line1.rcText = l1
        f.line1:SetText(l1)
        changed = true
    end
    if f.line2.rcText ~= l2 or f.line2.rcColor ~= c2 then
        f.line2.rcText, f.line2.rcColor = l2, c2
        UI.SetText(f.line2, l2)
        f.line2:SetTextColor(RS.Rgb(c2))
        changed = true
    end
    if changed then
        fitLines()
    end
end

-- M while the lock keeps the map shut (RoyaleMap.lua's MP.Open answers "locked"): line 2 names the locked landing for
-- RC.REMIND s with a soft flash, where the player already looks, rather than an error line across the ring. False
-- when no countdown counts (DROP! holds the centre for a moment more: the map opens once the drop starts).
function RC.Remind(m)
    m = m or R.Match()
    if run.mode ~= "count" or not m or m.matchId ~= run.matchId then
        return false
    end
    run.remindUntil = GetTime() + RC.REMIND
    refreshLines(m)
    RS.Tween(f.line2, "alpha", 0.35, 1, 0.25, "outCubic")
    return true
end

------------------------------------------------------------------------------------------------------
-- The local pin lock
------------------------------------------------------------------------------------------------------
-- The pin is locked on this client: from T-3.6 in phase 1 (the server's own lock follows at T-3).
function RC.Locked(m)
    m = m or R.Match()
    if not m or m.phase ~= R.PHASE.COUNTDOWN then
        return false
    end
    if run.locked and run.matchId == m.matchId then
        return true
    end
    local left = R.PhaseLeft(m)
    return left ~= nil and left <= RC.LOCK_AT
end

local function lock(m)
    run.locked = true
    closeMap()
    glideTo(0)
    refreshLines(m)
    ns.Fire("ROYALE_PIN_LOCKED", m)
end

------------------------------------------------------------------------------------------------------
-- Motion
------------------------------------------------------------------------------------------------------
-- Runs `fn` after `delay` s (at once for none) while the same run still counts.
local function later(delay, fn)
    if not delay or delay <= 0 then
        fn()
        return
    end
    local id = run.id
    ns.After(delay, function()
        if run.id == id and run.mode == "count" then
            fn()
        end
    end)
end

-- A ring of `t` from `size0` to `size1` units ({ w, h }), fading out from `alpha`, centred `dy` units under the
-- ring's centre (nothing shows before it starts).
local function ring(t, size0, size1, alpha, dur, color, blend, dy)
    RS.Stop(t)
    t:ClearAllPoints()
    t:SetPoint("CENTER", f, "TOP", 0, RC.RING_Y + (dy or 0))
    t:SetBlendMode(blend or "ADD")
    t:SetVertexColor(RS.Rgb(color))
    t:Show()
    RS.Tween(t, "size", size0, size1, dur, "outCubic")
    -- the alpha holds and goes late, so a ring still reads once it has grown past the digits
    RS.Tween(t, "alpha", alpha, 0, dur, "inCubic", { onDone = function(r) r:Hide() end })
end

-- The numeral `n` lands: its tier's fall, punch, flash, rings and sound, after `delay` s.
local function arrive(n, delay)
    local tier = RC.Tier(n)
    local opts = { delay = delay > 0 and delay or nil }
    RS.Tween(num.cur, "offset", { 0, tier.rise }, { 0, 0 }, tier.dur, "outCubic", opts)
    RS.Tween(num.cur, "alpha", 0, 1, 0.10, "linear", opts)
    if tier.punch then
        RS.Tween(num, "zoom", tier.punch, 1, tier.dur, "outBack", opts)
    else
        num:SetZoom(1)
    end
    RS.Stop(num.glow)
    num.glow:SetAlpha(0)
    if tier.glow then
        num:SetGlowColor(tier.glow[1])
        later(delay, function()
            RS.Tween(num.glow, "alpha", tier.glow[2], 0, tier.glow[3], "outCubic")
        end)
    end
    -- the rings when the digits touch down (most of the fall is in its first half: outCubic)
    local land = delay + tier.dur * 0.6
    if tier.dust then
        -- a flat dust ring where the digits stand
        local cap = RC.Cap(n)
        later(land, function()
            ring(f.dust, { 96, 48 }, { 200, 100 }, 0.35, 0.3, "bronzeHi", "ADD", -cap / 2)
        end)
    end
    for i = 1, tier.shocks or 0 do
        later(land + (i - 1) * 0.08, function()
            ring(f.shocks[i], { 96, 96 }, { 240, 240 }, 0.5, 0.35, i == 1 and "ember" or "gold", "ADD", 0)
        end)
    end
    later(delay, function()
        RS.PlayFile(RC.Sound(n))
    end)
end

-- Notch i lit (`hot`: ember) or dark, over `dur` s after `delay`.
local function notch(i, lit, hot, dur, delay)
    local t = stage.notches[i]
    if not t then
        return
    end
    local to = lit and rgba(hot and RC.HOT or RC.LIT, 1) or rgba(RC.DARK, RC.DARK_ALPHA)
    RS.Tween(t, "vertexColor", nil, to, dur or 0.2, "outCubic", { delay = delay })
end

-- From the number shown to `n` (lower): the old digits fall away, the notches between go dark, `n` lands. Numbers
-- skipped by a correction are never animated.
local function change(n)
    local from = run.shown
    RS.Stop(num, nil, true)
    RS.Stop(num.cur, nil, true)
    num:Swap(n)
    num:SetCap(RC.Cap(n))
    RS.Tween(num.old, "alpha", 1, 0, 0.15, "inCubic", { onDone = function() num:ClearOld() end })
    RS.Tween(num.old, "zoom", num.old.rsZoom or 1, 0.85, 0.15, "inCubic")
    for i = n + 1, from do
        notch(i, false)
    end
    if n <= 3 and (from > 3 or from - n > 1) then
        for i = 1, n do
            notch(i, true, true)
        end
    end
    run.shown = n
    arrive(n, 0)
end

------------------------------------------------------------------------------------------------------
-- Entrance, DROP!, exits
------------------------------------------------------------------------------------------------------
function RC.Start(m, left)
    resetVisuals()
    serial = serial + 1
    wipe(run)
    run.id, run.mode, run.matchId = serial, "count", m.matchId
    run.endsAt = GetTime() + left
    run.mapUp = mapUp(m)
    -- docking: beside the map when it fits, else centred (and a map that opened by itself goes now)
    local x = wantedX(m)
    if run.mapUp and x == 0 then
        local MP = ns.RoyaleMap
        if MP and MP.auto then
            closeMap()
            run.mapUp = mapUp(m)
        end
    end
    place(x)
    refreshLines(m)
    local n = RC.ValueFor(left)
    run.shown = n
    num:ClearOld()
    num:SetCap(RC.Cap(n))
    num:SetValue(n)
    num.cur:SetAlpha(0)
    f:SetAlpha(0)
    f:Show()
    RS.Tween(f, "alpha", 0, 1, 0.2, "outCubic")
    RS.Tween(stageKey, "number", RC.STAGE_FROM, 1, 0.3, "outCubic", { set = placeStage })
    local hot = n <= 3
    for i = 1, n do
        notch(i, true, hot, 0.12, (i - 1) * 0.02)
    end
    arrive(n, 0.15)
    if left <= RC.LOCK_AT then
        lock(m)
    end
end

-- DROP!: the ring goes, the word slams in with the gong (RoyaleDrop.lua starts the wind 0.5 s later and its plate
-- 0.8 s later, from ROYALE_DROP_WORD), the frame fades out from 0.8 s to 1.1 s.
local function showDrop(m)
    run.mode = "drop"
    run.dropAt = GetTime()
    RC.dropFor, RC.dropShownAt = run.matchId, run.dropAt
    RS.Stop(stageKey)
    RS.Stop(glideKey)
    placeStage(1)
    if run.gliding then
        run.gliding = nil
        place(0)
    end
    for _, r in ipairs({ stage, kick, lines, num }) do
        RS.Tween(r, "alpha", nil, 0, 0.2, "outCubic")
    end
    drop:SetAlpha(0)
    drop:Show()
    RS.Tween(drop, "alpha", 0, 1, 0.06, "linear")
    RS.Tween(drop, "zoom", 0.6, 1.12, 0.12, "outBack", {
        onDone = function()
            RS.Tween(drop, "zoom", 1.12, 1, 0.12, "outBack")
        end,
    })
    drop:SetGlowColor("gold")
    RS.Tween(drop.glow, "alpha", 1, 0, 0.6, "outCubic")
    ring(f.bigShock, { 96, 96 }, { 400, 400 }, 0.7, 0.45, "gold", "BLEND", 0)   -- over bright terrain: a gold ring
    RS.Play(RC.GONG)
    ns.Fire("ROYALE_DROP_WORD", m)
end

local function fadeOut(dur)
    run.fading = true
    run.fadeEnd = GetTime() + dur
    RS.Tween(f, "alpha", nil, 0, dur, "inCubic", { onDone = finish })
end

local function showCancel()
    run.mode = "cancel"
    run.cancelAt = GetTime()
    RS.Stop(stageKey)
    RS.Stop(glideKey)
    run.gliding = nil
    for _, r in ipairs({ stage, kick, lines, num }) do
        RS.Tween(r, "alpha", nil, 0, 0.2, "outCubic")
    end
    cancel:SetAlpha(0)
    cancel:Show()
    RS.Tween(cancel, "alpha", 0, 1, 0.2, "outCubic")
    RS.Tween(cancel, "zoom", 1.15, 1, 0.22, "outBack")
end

local function leave()
    run.mode = "out"
    fadeOut(RC.OUT_FADE)
end

------------------------------------------------------------------------------------------------------
-- The clock
------------------------------------------------------------------------------------------------------
function RC.Update()
    local mode = run.mode
    if not mode then
        if f:IsShown() then
            f:Hide()
        end
        return
    end
    local now = GetTime()
    if run.fading then
        if now >= run.fadeEnd + 0.05 then
            finish()
        end
        return
    end
    if mode == "drop" then
        if now - run.dropAt >= RC.DROP_HOLD then
            fadeOut(RC.DROP_FADE)
        end
        return
    elseif mode == "cancel" then
        if now - run.cancelAt >= RC.CANCEL_HOLD then
            fadeOut(RC.OUT_FADE)
        end
        return
    elseif mode ~= "count" then
        return
    end
    local m = R.Match()
    if not m or m.matchId ~= run.matchId then
        leave()
        return
    end
    if m.phase == R.PHASE.CANCELLED then
        showCancel()
        return
    end
    -- the server dropped us first: DROP! at once
    if m.me == R.ME.DROPPING or (m.phase >= R.PHASE.DROP and m.phase <= R.PHASE.OVERTIME) then
        showDrop(m)
        return
    end
    if m.phase ~= R.PHASE.COUNTDOWN then
        leave()
        return
    end
    local left = run.endsAt - now
    if left <= 0 then
        showDrop(m)
        return
    end
    if left > RC.FROM + 1 then
        leave()   -- the server moved the drop back: the countdown starts again at 15
        return
    end
    local n = RC.ValueFor(left)
    if n < run.shown then
        change(n)
    end
    if not run.locked and left <= RC.LOCK_AT then
        lock(m)
    end
    -- docking follows the map until the lock; a new screen or HUD scale is laid out once no glide runs
    if not run.locked and not run.gliding then
        local up = mapUp(m)
        if up ~= run.mapUp then
            run.mapUp = up
            glideTo(wantedX(m))
        elseif run.relayout then
            place(wantedX(m))
        end
        run.relayout = nil
    elseif run.relayout and not run.gliding then
        place(wantedX(m))
        run.relayout = nil
    end
    refreshLines(m)
end

f:SetScript("OnUpdate", function()
    RC.Update()
end)

-- Starts a countdown when one is due (phase 1, at most 15.25 s left, no DROP! yet for this match); a running one takes
-- every phase-1 ROYS's time when it is more than 0.35 s off.
function RC.Check()
    local m = R.Match()
    if run.mode == "count" then
        if m and m.matchId == run.matchId and m.phase == R.PHASE.COUNTDOWN and (m.phaseMsLeft or 0) > 0 then
            local endsAt = (m.recvAt or GetTime()) + m.phaseMsLeft / 1000
            if abs(endsAt - run.endsAt) > RC.DRIFT then
                run.endsAt = endsAt
            end
        end
        RC.Update()
        return
    end
    if run.mode or not m or m.phase ~= R.PHASE.COUNTDOWN or RC.dropFor == m.matchId then
        return
    end
    local left = R.PhaseLeft(m)
    if left and left > RC.MIN_LEFT and left <= RC.FROM + RC.EARLY then
        RC.Start(m, left)
    end
end

-- True while the countdown holds the screen's centre, from its lock at T-3.6 through DROP!: RoyaleMap.lua keeps the
-- lobby map shut then (it closed at the lock; opened again it would dock under the centred ring).
function RC.HoldsCentre(m)
    m = m or R.Match()
    return m ~= nil and run.matchId == m.matchId and (run.mode == "drop" or (run.mode == "count" and run.locked))
        and true or false
end

-- The value shown now (nil when no countdown runs), for tests and previews.
function RC.Shown()
    return run.mode == "count" and run.shown or nil
end

ns.Every(0.1, RC.Check)

ns.On("STATE", function(topic)
    if topic == "ROYS" then
        RC.Check()
    end
end)

ns.On("ROYALE_MATCH", function(m)
    if run.mode and run.matchId ~= m.matchId then
        finish()
    end
    -- a match record that (re)appears counts down afresh: the samples of /bh royale preview countdown and /bh demo come
    -- back under their fixed ids, and the last run's DROP! must not keep the next one silent (a realm's ids are new)
    RC.dropFor, RC.dropShownAt = nil, nil
end)

local function relayout()
    if run.mode then
        run.relayout = true
        fitLines()
    end
end

ns.RegisterEvent("DISPLAY_SIZE_CHANGED", relayout)
ns.On("ROYALE_HUD_SCALE", relayout)
