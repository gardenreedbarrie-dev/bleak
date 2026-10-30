-- Bleakhold: Bleakhold Royale's drop countdown (frame BleakholdRoyaleCountdown; docs/BleakholdProtocol.md section 17),
-- in the look players know from DBM (Deadly Boss Mods): a timer bar through the last 15 s of the lobby, the big
-- numerals of the classic pull countdown for its last five seconds, then DROP! as a special warning.
--
--   trigger    phase 1 and R.PhaseLeft <= 15.25 (the server sends an exact ROYS at 15000 ms: revealing circle 1 marks
--              every player dirty). It ends at the drop (ROYS me 1 or phase 2, or the local clock's zero, whichever
--              comes first: DROP! shows either way) or when the phase leaves 1; a cancelled match shows MATCH CANCELLED
--              instead, with no gong. A late arrival (me 1 without the lobby) never sees it.
--   the clock  the target time comes from every phase-1 ROYS: within 0.35 s of the running one it is kept (a ROYS's
--              arrival jitter would otherwise move every second's beat); beyond that the bar and the next numeral
--              jump to the right second, and the numbers in between are skipped without animation. It never restarts
--              and never counts up (the old centre countdown restarted whenever the drift passed 0.5 s).
--   the bar    DBM's default timer bar (DBM-Core's DBT): a 195x20 status bar, the icon left of it, "Drop in" on the
--              left and the time on the right (whole seconds above 10 s, then one decimal, as DBM writes it), a spark
--              at the fill's end. It fills up as the drop nears and its colour runs from DBM's start colour
--              (1, 0.7, 0) to its end colour (1, 0, 0) over the countdown; from 7.75 s its fill flashes like DBM's.
--              The fill is the stock UI-StatusBar on a dark back with a 1-px black edge. Two lines under it name
--              the circle and the landing.
--   numerals   5, 4, 3, 2, 1: one big numeral a second (Art\Royale\Pull, bright gold with a black outline), popping
--              in at 1.6 times its size and settling in 0.3 s while its gold glow flares and settles to a halo; the
--              outgoing one fades in 0.1 s (outCubic: mostly gone in the pop's first frames, never a doubled digit).
--              Every second also ticks: tick.wav for 15-4, tick3/tick2/tick1.
--   DROP!      the special warning: the numerals go at once (the word lands on their spot), the word slams in from
--              1.6 times its size with a gold flare, the screen's edge flashes DBM's warning yellow, the gong; the
--              frame fades out from 0.8 s (gone 1.1 s after it showed).
--   DBM        when DBM is loaded, its own bar counts the drop: DBM:CreatePizzaTimer(seconds, "Drop in", false), a
--              local timer (never a sync message to the group), and ours hides, so one bar shows. A correction of
--              the clock restarts DBM's bar; an early end (cancelled, the server's drop, the match left) cancels it.
--              When DBM is missing or its call fails, ours shows.
--   T-3.6      during the "4", away from the loud beats: the pin locks locally (RC.Locked, ROYALE_PIN_LOCKED for the
--              map), an open lobby map closes with no sound, and a docked countdown glides to the centre, done at
--              T-3.3, before the "3" lands. The server's own lock at T-3 (PinLockSec) stays the authority.
--   docking    while the lobby map is open (it docks left of the screen's centre) and the room right of the centre,
--              W/2 - 24 - 16, takes the countdown at the HUD scale, the countdown's left edge sits 24 units right of
--              the centre; else it is centred, and a map that opened by itself closes when the countdown starts.
--              Computed when the countdown starts, when the map opens or closes, and on a new screen size or HUD
--              scale, never during a glide.
--   one clock  RC.OwnsClock(m): the top bar shows no time of its own while the countdown runs (the bar, ours or
--              DBM's, is the one clock).
-- Timing is driven by the frame's own OnUpdate while it shows (each numeral changes on the frame it is due), the
-- motion by RS.Tween; with reduced motion every tween jumps to its end, the bar does not flash, and the holds keep
-- their length. The freefall wind is RoyaleDrop.lua's: it starts 0.5 s after ROYALE_DROP_WORD, which this module
-- fires when DROP! shows.
local ADDON, ns = ...
local U, UI = ns.U, ns.UI
local S = ns.S
local R = ns.Royale
local RS = ns.RoyaleStyle
local DATA = ns.RoyaleArt

local floor, ceil, max, min, abs, sqrt = math.floor, math.ceil, math.max, math.min, math.abs, math.sqrt
local strformat = string.format

local RC = {}
ns.RoyaleCountdown = RC

RC.FROM = 15                     -- the first second (the server reveals circle 1 and sends ROYS at 15000 ms)
RC.EARLY = 0.25                  -- s before T-15 the countdown may start (its 15 shows a little longer, never a 16)
RC.MIN_LEFT = 0.25               -- no countdown for less time than this: the drop is already there
RC.W, RC.H = 420, 244
RC.TOP = 112                     -- the frame's top, under the top bar's tab (-98; lower at a HUD scale over 1.14)
RC.DOCK_GAP, RC.DOCK_MARGIN = 24, 16
RC.LOCK_AT = 3.6                 -- s before the drop: the local pin lock, the silent map close, the glide
RC.REMIND = 2.5                  -- s line 2 names the locked landing after M during the lock (RC.Remind)
RC.GLIDE = 0.3
RC.DRIFT = 0.35                  -- s: a server time this far off the running one moves the count

-- The bar: DBM-Core's DBT defaults (DBTBarTemplate 195x20, the icon left, GameFontHighlightSmall, StartColor and
-- EndColor, DynamicColor, FillUpBars, Flash below 7.75 s).
RC.BAR_W, RC.BAR_H = 195, 20
RC.BAR_TEXT = "Drop in"          -- our bar's name and DBM's pizza timer (16 characters at most there)
RC.BAR_FONT = 10
RC.BAR_ICONS = { "Interface\\Icons\\Spell_Magic_FeatherFall", "Interface\\Icons\\INV_Misc_QuestionMark" }
RC.BAR_FILL = "Interface\\TargetingFrame\\UI-StatusBar"
RC.BAR_SPARK = "Interface\\CastingBar\\UI-CastingBar-Spark"
RC.BAR_START, RC.BAR_END = { 1, 0.7, 0 }, { 1, 0, 0 }
RC.BAR_DECIMALS = 10             -- s: one decimal from here down
RC.BAR_FLASH, RC.BAR_FLASH_PERIOD, RC.BAR_FLASH_LOW = 7.75, 1.25, 0.25
RC.LINES_Y = -(RC.BAR_H + 6)     -- the lines' top under the bar (at the frame's top when DBM has the bar)

-- The numerals and the special warning, centred NUM_Y under the frame's top.
RC.BIG_FROM = 5                  -- the big numerals count 5 to 1
RC.BIG_CAP = 110
RC.NUM_Y = -176
RC.POP, RC.POP_DUR = 1.6, 0.3    -- a numeral pops in at this size and settles to 1 over this
RC.GLOW_COLOR = "FFC23A"
RC.GLOW_PEAK, RC.GLOW_REST, RC.GLOW_DUR = 1, 0.4, 0.5
RC.OUT_DUR = 0.1                 -- s the outgoing numeral takes to fade (outCubic: mostly gone at once)
RC.DROP_CAP = 80
RC.DROP_HOLD, RC.DROP_FADE = 0.8, 0.3            -- DROP! holds, then the frame fades (gone 1.1 s after it showed)
RC.FLASH_COLOR, RC.FLASH_ALPHA, RC.FLASH_IN, RC.FLASH_OUT = "FFE14D", 0.55, 0.08, 0.5
RC.CANCEL_CAP, RC.CANCEL_HOLD, RC.OUT_FADE = 22, 1.5, 0.25
RC.GONG = "Gong (Non-Looping)"

-- The sound (Sounds\Royale) of a second's turn.
function RC.Sound(n)
    return n <= 3 and ("tick" .. n) or "tick"
end

-- The second shown with `left` seconds to go: 15 from 15.25 down to just above 14, ..., 1 in the last second.
function RC.ValueFor(left)
    return U.Clamp(ceil(left - 1e-6), 1, RC.FROM)
end

-- The bar's time: whole seconds above 10 s (never 16 in the early quarter second), then tenths, both rounded up, so
-- the bar reads 5.0 as the 5 lands and 0.1 in the last tenth.
function RC.BarText(left)
    if left > RC.BAR_DECIMALS then
        return tostring(RC.ValueFor(left))
    end
    return strformat("%.1f", max(0, ceil(left * 10 - 1e-6) / 10))
end

-- The bar's colour at `p` (0 = the start, 1 = the drop): DBM's DynamicColor from StartColor to EndColor.
function RC.BarColor(p)
    p = U.Clamp(p, 0, 1)
    local a, b = RC.BAR_START, RC.BAR_END
    return a[1] + (b[1] - a[1]) * p, a[2] + (b[2] - a[2]) * p, a[3] + (b[3] - a[3]) * p
end

-- The fill's alpha with `left` seconds to go: DBM's Flash (1.25 s cycles from 7.75 s: down for 0.25 s, back up in
-- 0.25 s, then held), never under RC.BAR_FLASH_LOW; steady with reduced motion.
function RC.BarFlash(left)
    if left > RC.BAR_FLASH or not RS.Motion() then
        return 1
    end
    local t = (RC.BAR_FLASH - left) % RC.BAR_FLASH_PERIOD
    local dip = t < 0.25 and t / 0.25 or (t < 0.5 and (0.5 - t) / 0.25 or 0)
    return 1 - (1 - RC.BAR_FLASH_LOW) * dip
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

-- The timer bar: the icon and the status bar on one 1-px black edge.
local function buildBar()
    local bar = CreateFrame("Frame", nil, f)
    bar:SetSize(RC.BAR_H + 1 + RC.BAR_W, RC.BAR_H)
    bar:SetPoint("TOP", f, "TOP", 0, -1)
    bar:SetFrameLevel(base + 2)
    bar.edge = UI.Solid(bar, "000000", "BACKGROUND", 0.9)
    bar.edge:SetPoint("TOPLEFT", bar, "TOPLEFT", -1, 1)
    bar.edge:SetPoint("BOTTOMRIGHT", bar, "BOTTOMRIGHT", 1, -1)
    local icon = bar:CreateTexture(nil, "ARTWORK")
    icon:SetSize(RC.BAR_H, RC.BAR_H)
    icon:SetPoint("LEFT", bar, "LEFT", 0, 0)
    icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    for _, path in ipairs(RC.BAR_ICONS) do
        if icon:SetTexture(path) then
            break
        end
    end
    bar.icon = icon
    local sb = CreateFrame("StatusBar", nil, bar)
    sb:SetSize(RC.BAR_W, RC.BAR_H)
    sb:SetPoint("RIGHT", bar, "RIGHT", 0, 0)
    sb.bg = sb:CreateTexture(nil, "BACKGROUND")
    sb.bg:SetTexture(RC.BAR_FILL)
    sb.bg:SetAllPoints(sb)
    sb.bg:SetVertexColor(0.16, 0.16, 0.16, 0.75)
    sb:SetStatusBarTexture(RC.BAR_FILL)
    sb:SetMinMaxValues(0, 1)
    sb:SetValue(0)
    sb:SetStatusBarColor(RC.BarColor(0))
    sb.spark = sb:CreateTexture(nil, "OVERLAY")
    sb.spark:SetTexture(RC.BAR_SPARK)
    sb.spark:SetBlendMode("ADD")
    sb.spark:SetSize(24, RC.BAR_H * 2)
    sb.spark:Hide()
    bar.spark = sb.spark
    -- the texts over the spark
    local top = CreateFrame("Frame", nil, sb)
    top:SetAllPoints(sb)
    top:SetFrameLevel(sb:GetFrameLevel() + 1)
    bar.name = RS.Text(top, "body", RC.BAR_FONT, "safe", "LEFT")
    bar.name:SetPoint("LEFT", sb, "LEFT", 6, 0)
    bar.name:SetWidth(RC.BAR_W - 52)
    bar.name:SetNonSpaceWrap(false)
    bar.name:SetText(RC.BAR_TEXT)
    bar.time = RS.Text(top, "body", RC.BAR_FONT, "safe", "RIGHT")
    bar.time:SetPoint("RIGHT", sb, "RIGHT", -4, 0)
    bar.sb = sb
    return bar
end
f.bar = buildBar()

-- The two lines under the bar, on a soft dark pill: the island is bright sand and water at noon.
local function buildLines()
    local lines = CreateFrame("Frame", nil, f)
    lines:SetSize(RC.W - 20, 52)
    lines:SetFrameLevel(base + 1)
    lines.back = RS.Plate(lines, "LabelHalo", { corner = 10 })
    lines.back:SetAlpha(0.85)
    local function line(size, y)
        local fs = RS.Text(lines, "body", size, "parchment", "CENTER")
        fs:SetPoint("TOP", lines, "TOP", 0, y)
        fs:SetWidth(RC.W - 20)
        fs:SetHeight(size + 4)
        fs:SetNonSpaceWrap(false)
        return fs
    end
    f.line1 = line(13, -6)
    f.line2 = line(12, -28)
    return lines
end
f.lines = buildLines()
RC.LINES_PAD, RC.LINES_MIN = 48, 220   -- the pill: the longer line plus this, at least this wide

-- The lines under our bar, or at the top when DBM draws the bar.
local function placeLines(dbm)
    f.lines:ClearAllPoints()
    f.lines:SetPoint("TOP", f, "TOP", 0, dbm and 0 or RC.LINES_Y)
end
placeLines(false)

-- The pill hugs the longer line (only when a text changes).
local function fitLines()
    local w = max(f.line1:GetStringWidth() or 0, f.line2:GetStringWidth() or 0) + RC.LINES_PAD
    f.lines:SetWidth(U.Clamp(floor(w + 0.5), RC.LINES_MIN, RC.W - 10))
end

-- A glyph of the Pull atlas (a numeral or DROP!) at `cap` units, centred NUM_Y under the frame's top, its gold glow
-- behind it (ADD, alpha 0 until tweened): d:SetGlyph(text), d:SetZoom(f) (a factor on its size, for RS.Tween zoom).
local PULL = DATA.atlases.Pull

local function bigSetZoom(d, z)
    d.rsZoom = z
    local g = PULL.glyphs[d.glyph]
    if g then
        local c = d.cap * z
        d.tex:SetSize(g.w * c, g.h * c)
        d.glow:SetSize(g.w * c, g.h * c)
    end
end

local function bigSetGlyph(d, text)
    local g = PULL.glyphs[text]
    assert(g, "RoyaleCountdown: no Pull glyph " .. tostring(text))
    d.glyph = text
    d.tex:SetTexCoord(g.u0, g.u1, g.v0, g.v1)
    d.glow:SetTexCoord(g.u0, g.u1, g.v0, g.v1)
    d:SetSize((g.inkW + 2 * g.stroke) * d.cap, (1 + 2 * g.stroke) * d.cap)
    bigSetZoom(d, d.rsZoom or 1)
end

local function newBig(level, cap, text)
    local d = CreateFrame("Frame", nil, f)
    d:SetFrameLevel(base + level)
    d:SetPoint("CENTER", f, "TOP", 0, RC.NUM_Y)
    d.cap, d.rsZoom = cap, 1
    d.glow = RS.Art(d, "PullGlow", 1, 1, "BACKGROUND")
    d.glow:SetPoint("CENTER", d, "CENTER", 0, 0)
    d.glow:SetBlendMode("ADD")
    d.glow:SetVertexColor(RS.Rgb(RC.GLOW_COLOR))
    d.glow:SetAlpha(0)
    d.tex = RS.Art(d, "Pull", 1, 1, "ARTWORK")
    d.tex:SetPoint("CENTER", d, "CENTER", 0, 0)
    d.SetZoom, d.SetGlyph = bigSetZoom, bigSetGlyph
    d:SetGlyph(text)
    d:Hide()
    return d
end
f.numOld = newBig(3, RC.BIG_CAP, "1")
f.num = newBig(4, RC.BIG_CAP, "1")
f.drop = newBig(6, RC.DROP_CAP, "DROP!")

-- MATCH CANCELLED where the numerals stand
local cancel = RS.Title(f, "MATCH CANCELLED", RC.CANCEL_CAP, "blood")
cancel:SetPoint("CENTER", f, "TOP", 0, RC.NUM_Y)
cancel:SetFrameLevel(base + 6)
cancel:Hide()
f.cancel = cancel

-- the special warning's flash: the storm edge's art over the whole screen, in DBM's warning yellow
local flash = RS.Art(f, "Vignette", nil, nil, "BACKGROUND")
flash:SetAllPoints(UIParent)
flash:SetBlendMode("ADD")
flash:SetVertexColor(RS.Rgb(RC.FLASH_COLOR))
flash:SetAlpha(0)
flash:Hide()
f.flash = flash

------------------------------------------------------------------------------------------------------
-- A run: one countdown from its entrance to DROP! (or its exit)
------------------------------------------------------------------------------------------------------
-- mode: nil (idle), "count", "drop", "cancel" or "out"; endsAt: GetTime() of the drop; total: the seconds the bar
-- spans; shown: the second shown; x: the frame's centre, in UIParent units from the screen's centre; dbm: DBM draws
-- the bar.
local run = {}
RC.run = run
local serial = 0
-- the key of the docking glide's number tween
local glideKey = {}

local function stopAll()
    RS.Stop(glideKey)
    for _, r in ipairs({ f, f.bar, f.lines, f.line2, f.num, f.num.glow, f.numOld, f.numOld.glow, f.drop, f.drop.glow,
        cancel, flash }) do
        RS.Stop(r)
    end
end

------------------------------------------------------------------------------------------------------
-- DBM's own bar
------------------------------------------------------------------------------------------------------
-- DBM's bar module (DBM.Bars, DBM-Core's DBT) when DBM is loaded.
local function dbmBars()
    local d = DBM
    return type(d) == "table" and type(d.Bars) == "table" and d.Bars or nil
end

-- Starts DBM's own timer bar for the drop, `left` seconds: a local pizza timer (broadcast false: no sync to the
-- group). True when DBM took it; any error inside DBM leaves the bar to us.
function RC.StartDbm(left)
    local d = DBM
    if type(d) ~= "table" or type(d.CreatePizzaTimer) ~= "function" then
        return false
    end
    local secs = floor(left * 10 + 0.5) / 10
    if not pcall(d.CreatePizzaTimer, d, secs, RC.BAR_TEXT, false) then
        return false
    end
    -- a DBM that can look its bars up must show this one
    local bars = dbmBars()
    if bars and type(bars.GetBar) == "function" then
        local ok, b = pcall(bars.GetBar, bars, RC.BAR_TEXT)
        if ok and not b then
            return false
        end
    end
    return true
end

-- Cancels DBM's bar for the drop (DBT:CancelBar, by the pizza timer's name).
function RC.StopDbm()
    local bars = dbmBars()
    if bars and type(bars.CancelBar) == "function" then
        pcall(bars.CancelBar, bars, RC.BAR_TEXT)
    end
end

local function dropDbm()
    if run.dbm then
        run.dbm = nil
        RC.StopDbm()
    end
end

-- Hands the bar to DBM (`left` seconds), or shows ours when DBM cannot take it.
local function claimBar(left)
    run.dbm = RC.StartDbm(left) or nil
    if run.dbm then
        f.bar:Hide()
    else
        f.bar:Show()
    end
    placeLines(run.dbm)
end

local function finish()
    stopAll()
    dropDbm()
    f.num:Hide()
    f.numOld:Hide()
    f.drop:Hide()
    cancel:Hide()
    flash:Hide()
    f:Hide()
    wipe(run)
end

-- Every part back to its resting state, for a new run.
local function resetVisuals()
    stopAll()
    f:SetAlpha(1)
    f.bar:SetAlpha(1)
    f.lines:SetAlpha(1)
    f.line2:SetAlpha(1)
    for _, d in ipairs({ f.num, f.numOld, f.drop }) do
        d:SetAlpha(1)
        d:SetZoom(1)
        d.glow:SetAlpha(0)
        d:Hide()
    end
    cancel:Hide()
    cancel:SetAlpha(1)
    cancel:SetZoom(1)
    flash:SetAlpha(0)
    flash:Hide()
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
-- The lines under the bar
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
-- RC.REMIND s with a soft flash, where the player already looks, rather than an error line across the numerals.
-- False when no countdown counts (DROP! holds the centre for a moment more: the map opens once the drop starts).
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
-- The bar and the numerals
------------------------------------------------------------------------------------------------------
-- The bar at `left` seconds to go: fill, colour, spark, time and flash.
local function updateBar(left)
    if run.dbm then
        return
    end
    local bar, sb = f.bar, f.bar.sb
    local p = U.Clamp(1 - left / max(run.total or RC.FROM, 0.01), 0, 1)
    sb:SetValue(p)
    sb:SetStatusBarColor(RC.BarColor(p))
    local text = RC.BarText(left)
    if bar.timeText ~= text then
        bar.timeText = text
        bar.time:SetText(text)
    end
    local a = RC.BarFlash(left)
    local fill = sb:GetStatusBarTexture()
    if fill then
        fill:SetAlpha(a)
    end
    if p > 0.005 and p < 0.995 then
        sb.spark:ClearAllPoints()
        sb.spark:SetPoint("CENTER", sb, "LEFT", p * RC.BAR_W, 0)
        sb.spark:SetAlpha(a)
        sb.spark:Show()
    else
        sb.spark:Hide()
    end
end

-- The big numeral `n` pops in (from 1.6 times its size, settling with its gold glow); the one before fades.
local function pop(n)
    local num, old = f.num, f.numOld
    if num:IsShown() and num.glyph then
        RS.Stop(old)
        RS.Stop(old.glow)
        old:SetGlyph(num.glyph)
        old:SetZoom(num.rsZoom or 1)
        old:SetAlpha(num:GetAlpha())
        old.glow:SetAlpha(num.glow:GetAlpha())
        old:Show()
        RS.Tween(old, "alpha", nil, 0, RC.OUT_DUR, "outCubic", { onDone = function(r) r:Hide() end })
    end
    RS.Stop(num)
    RS.Stop(num.glow)
    num:SetGlyph(tostring(n))
    num:Show()
    RS.Tween(num, "alpha", 0, 1, 0.08, "linear")
    RS.Tween(num, "zoom", RC.POP, 1, RC.POP_DUR, "outCubic")
    RS.Tween(num.glow, "alpha", RC.GLOW_PEAK, RC.GLOW_REST, RC.GLOW_DUR, "outCubic")
end

-- To the second `n` (lower than the one shown): its tick, and its big numeral in the last five. Seconds skipped by a
-- correction are never animated.
local function change(n)
    run.shown = n
    if n <= RC.BIG_FROM then
        pop(n)
    end
    RS.PlayFile(RC.Sound(n))
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
    run.total = left
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
    claimBar(left)
    f.bar.timeText = nil
    updateBar(left)
    refreshLines(m)
    f:SetAlpha(0)
    f:Show()
    RS.Tween(f, "alpha", 0, 1, 0.2, "outCubic")
    change(RC.ValueFor(left))
    if left <= RC.LOCK_AT then
        lock(m)
    end
end

-- DROP!: the bar and the lines fade, the numerals go at once, the special warning slams in with its flash and the gong
-- (RoyaleDrop.lua starts the wind 0.5 s later and its plate 0.8 s later, from ROYALE_DROP_WORD), the frame fades out
-- from 0.8 s to 1.1 s.
local function showDrop(m)
    run.mode = "drop"
    run.dropAt = GetTime()
    RC.dropFor, RC.dropShownAt = run.matchId, run.dropAt
    dropDbm()
    RS.Stop(glideKey)
    if run.gliding then
        run.gliding = nil
        place(0)
    end
    for _, r in ipairs({ f.bar, f.lines }) do
        RS.Tween(r, "alpha", nil, 0, 0.2, "outCubic")
    end
    -- the numerals go at once: DROP! lands on their spot, and a fading 1 would show through it
    for _, d in ipairs({ f.num, f.numOld }) do
        RS.Stop(d)
        RS.Stop(d.glow)
        d:Hide()
    end
    local drop = f.drop
    drop:SetAlpha(0)
    drop:Show()
    RS.Tween(drop, "alpha", 0, 1, 0.06, "linear")
    RS.Tween(drop, "zoom", RC.POP, 1, 0.18, "outBack")
    RS.Tween(drop.glow, "alpha", RC.GLOW_PEAK, RC.GLOW_REST, 0.6, "outCubic")
    flash:Show()
    RS.Tween(flash, "alpha", 0, RC.FLASH_ALPHA, RC.FLASH_IN, "linear", {
        onDone = function(t)
            RS.Tween(t, "alpha", RC.FLASH_ALPHA, 0, RC.FLASH_OUT, "inCubic")
        end,
    })
    if not RS.Motion() then
        flash:SetAlpha(0)
    end
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
    dropDbm()
    RS.Stop(glideKey)
    run.gliding = nil
    for _, r in ipairs({ f.bar, f.lines, f.num, f.numOld }) do
        RS.Tween(r, "alpha", nil, 0, 0.2, "outCubic")
    end
    cancel:SetAlpha(0)
    cancel:Show()
    RS.Tween(cancel, "alpha", 0, 1, 0.2, "outCubic")
    RS.Tween(cancel, "zoom", 1.15, 1, 0.22, "outBack")
end

local function leave()
    run.mode = "out"
    dropDbm()
    fadeOut(RC.OUT_FADE)
end

------------------------------------------------------------------------------------------------------
-- The clock
------------------------------------------------------------------------------------------------------
-- Docking follows the map until the lock; a new screen or HUD scale is laid out once no glide runs.
local function follow(m)
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
end

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
    updateBar(left)
    if not run.locked and left <= RC.LOCK_AT then
        lock(m)
    end
    follow(m)
    refreshLines(m)
end

f:SetScript("OnUpdate", function()
    RC.Update()
end)

-- Starts a countdown when one is due (phase 1, at most 15.25 s left, no DROP! yet for this match); a running one takes
-- every phase-1 ROYS's time when it is more than 0.35 s off (and DBM's bar follows it).
function RC.Check()
    local m = R.Match()
    if run.mode == "count" then
        if m and m.matchId == run.matchId and m.phase == R.PHASE.COUNTDOWN and (m.phaseMsLeft or 0) > 0 then
            local endsAt = (m.recvAt or GetTime()) + m.phaseMsLeft / 1000
            if abs(endsAt - run.endsAt) > RC.DRIFT then
                run.endsAt = endsAt
                if run.dbm then
                    RC.StopDbm()
                    claimBar(endsAt - GetTime())
                end
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
-- lobby map shut then (it closed at the lock; opened again it would dock under the centred countdown).
function RC.HoldsCentre(m)
    m = m or R.Match()
    return m ~= nil and run.matchId == m.matchId and (run.mode == "drop" or (run.mode == "count" and run.locked))
        and true or false
end

-- The second shown now (nil when no countdown counts), for tests and previews.
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
