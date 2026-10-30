-- Bleakhold: keystone start countdown, and a generic one (CD.StartGeneric) with the same bar and numerals but its own
-- kicker and title and no DBM message. The server starts the keystone one (MPS countdownMs) and roots the group.
-- It looks like DBM (Deadly Boss Mods), as Bleakhold Royale's drop countdown does (RoyaleCountdown.lua):
--   the head    the kicker (white 12), the dungeon and level (gold 20, GameFontNormalHuge), the affixes as their spell
--               icons (UI.AffixIcon, tooltips) and the era in gold
--   the bar     DBM's default timer bar ("Pull in", DBM-Core's DBT: a 195 x 20 status bar, the pull timer's icon on the
--               left, the name on the left and the time on the right, whole seconds above 10 s and then one decimal),
--               a spark at the fill's end; it fills up and its colour runs from DBM's start colour (1, 0.7, 0) to its
--               end colour (1, 0, 0), and from 7.75 s its fill flashes like DBM's
--   numerals    the last five seconds: the big numerals of the classic pull countdown (Royale's Art\Royale\Pull, bright
--               gold with a black outline), each popping in at 1.6 times its size and settling in 0.3 s while its gold
--               glow flares and settles to a halo; the one before fades out
--   zero        the frame goes (the run starts: MPLUS_GO), as before
-- With royaleMotion off (RoyaleStyle.lua) every pop and fade jumps to its end and the bar does not flash.
-- The kicker names the run: "Mythic+ Keystone" for a key, "Mythic 0 - untimed" for a Mythic 0 (MPS level 0: the
-- Font of Power's, which counts down 10 s; it has no affixes) over the bare dungeon name.
-- DBM: the group leader's client sends DBM's pull-timer messages to the group, or to itself when solo and DBM is
-- loaded, so DBM shows its own "Pull in" bar (and may count in the middle of the screen itself: hideNumeralsWithDBM
-- hides ours then). Two of them, one per DBM generation:
--   "DBMv4-PT"     body = seconds (0 cancels): the newer DBM builds (the Warmane backport)
--   "DBMv4-Pizza"  body = seconds .. "\tPull in", never for 0: the stock DBM-Core 4.x for 3.3.5a, which knows only its
--                  Pizza timer (from a leader or an assistant); the newer builds map a "Pull in" Pizza onto their PT
--                  sync with AntiSpam, so they still show one bar
-- A 4.x DBM ignores Pizza from its own player and drops a whisper from outside the group, so the sender (the leader,
-- or a solo player) makes its own bar there (DBM:CreatePizzaTimer, not broadcast), and on a cancel every client with a
-- 4.x DBM takes the "Pull in" bar away itself (DBM.Bars:CancelBar). These messages are for DBM only; never a Bleakhold
-- intent. When the server already sends the DBM message itself (HELLO feature bit DBM_BY_SERVER), the client does not;
-- the server sends PT only, so a client with a 4.x DBM makes its own bar then (CD.LocalServerPull).
-- While DBM shows its bar (CD.DbmBar asks DBM's bar module) ours hides, so one bar shows.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S

local floor, ceil, max, min = math.floor, math.ceil, math.max, math.min
local strformat = string.format

local CD = {}
ns.Countdown = CD

CD.DBM_PREFIX = "DBMv4-PT"
CD.DBM_PIZZA_PREFIX = "DBMv4-Pizza"
-- DBM 4.x numbers its releases (4442 for 4.52); the newer builds use a date (yyyymmdd...)
CD.DBM_OLD_BELOW = 1e6
CD.KEY_KICKER = "Mythic+ Keystone"
CD.M0_KICKER = "Mythic 0 - untimed"
-- the bridge's toast for the keystone right-clicked at its dungeon (bh_ui_bridge.cpp), stale once the countdown starts
CD.READY_TOAST = "Keystone ready"
CD.W, CD.H = 420, 270
CD.MAX_AFFIXES = 6
-- DBM-Core's DBT defaults: DBTBarTemplate 195 x 20, GameFontHighlightSmall, StartColor, EndColor, Flash below 7.75 s;
-- the pull timer's name and icon (DBM_CORE_TIMER_PULL, Spell_Holy_BorrowedTime)
CD.BAR_W, CD.BAR_H = 195, 20
CD.BAR_TEXT = "Pull in"
CD.BAR_ICON = "Interface\\Icons\\Spell_Holy_BorrowedTime"
CD.BAR_FILL = "Interface\\TargetingFrame\\UI-StatusBar"
CD.BAR_SPARK = "Interface\\CastingBar\\UI-CastingBar-Spark"
CD.BAR_START, CD.BAR_END = { 1, 0.7, 0 }, { 1, 0, 0 }
CD.BAR_DECIMALS = 10
CD.BAR_FLASH, CD.BAR_FLASH_PERIOD, CD.BAR_FLASH_LOW = 7.75, 1.25, 0.25
CD.BAR_Y = -84
-- the numerals (RoyaleCountdown.lua's: cap 110, the pop, the glow), centred NUM_Y under the frame's top
CD.BIG_FROM = 5
CD.BIG_CAP = 110
CD.NUM_Y = -184
CD.POP, CD.POP_DUR, CD.IN_DUR = 1.6, 0.3, 0.08
CD.GLOW_COLOR = { 1, 0.76, 0.23 }
CD.GLOW_PEAK, CD.GLOW_REST, CD.GLOW_DUR = 1, 0.4, 0.5
CD.OUT_DUR = 0.15

local f = CreateFrame("Frame", "BleakholdCountdown", UIParent)
f:SetSize(CD.W, CD.H)
f:SetPoint("TOP", UIParent, "TOP", 0, -80)
f:SetFrameStrata("DIALOG")
f:Hide()
CD.frame = f
local base = f:GetFrameLevel()

------------------------------------------------------------------------------------------------------
-- The head: kicker, title, affixes and era
------------------------------------------------------------------------------------------------------
f.kicker = UI.Text(f, 12, C.text, "body", "CENTER")
f.kicker:SetPoint("TOP", f, "TOP", 0, 0)
UI.OneLine(f.kicker, CD.W)
f.kicker:SetText(CD.KEY_KICKER)
f.title = UI.Text(f, 20, C.gold, "body", "CENTER")
f.title:SetPoint("TOP", f, "TOP", 0, -18)
UI.OneLine(f.title, CD.W)
f.affixRow = CreateFrame("Frame", nil, f)
f.affixRow:SetSize(10, 24)
f.affixRow:SetPoint("TOP", f, "TOP", 0, -46)
f.affixes = {}
for i = 1, CD.MAX_AFFIXES do
    local a = UI.AffixIcon(f.affixRow, 22)
    a:Hide()
    f.affixes[i] = a
end
f.era = UI.Text(f.affixRow, 12, C.gold, "body", "LEFT")
f.era:Hide()

------------------------------------------------------------------------------------------------------
-- DBM's bar
------------------------------------------------------------------------------------------------------
-- The bar's time: whole seconds above 10 s, then tenths, both rounded up (DBM writes it so).
function CD.BarText(left)
    if left > CD.BAR_DECIMALS then
        return tostring(ceil(left - 1e-6))
    end
    return strformat("%.1f", max(0, ceil(left * 10 - 1e-6) / 10))
end

-- The bar's colour at p (0 = the start, 1 = zero): DBM's DynamicColor from StartColor to EndColor.
function CD.BarColor(p)
    p = U.Clamp(p, 0, 1)
    local a, b = CD.BAR_START, CD.BAR_END
    return a[1] + (b[1] - a[1]) * p, a[2] + (b[2] - a[2]) * p, a[3] + (b[3] - a[3]) * p
end

local function motion()
    local RS = ns.RoyaleStyle
    return not (RS and RS.Motion) or RS.Motion()
end

-- The fill's alpha with `left` seconds to go: DBM's Flash (1.25 s cycles from 7.75 s: down for 0.25 s, back up in
-- 0.25 s, then held), never under BAR_FLASH_LOW; steady with reduced motion.
function CD.BarFlash(left)
    if left > CD.BAR_FLASH or not motion() then
        return 1
    end
    local t = (CD.BAR_FLASH - left) % CD.BAR_FLASH_PERIOD
    local dip = t < 0.25 and t / 0.25 or (t < 0.5 and (0.5 - t) / 0.25 or 0)
    return 1 - (1 - CD.BAR_FLASH_LOW) * dip
end

local function buildBar()
    local bar = CreateFrame("Frame", nil, f)
    bar:SetSize(CD.BAR_H + 1 + CD.BAR_W, CD.BAR_H)
    bar:SetPoint("TOP", f, "TOP", 0, CD.BAR_Y)
    bar:SetFrameLevel(base + 2)
    bar.edge = bar:CreateTexture(nil, "BACKGROUND")
    bar.edge:SetTexture(0, 0, 0, 0.9)
    bar.edge:SetPoint("TOPLEFT", bar, "TOPLEFT", -1, 1)
    bar.edge:SetPoint("BOTTOMRIGHT", bar, "BOTTOMRIGHT", 1, -1)
    bar.icon = bar:CreateTexture(nil, "ARTWORK")
    bar.icon:SetSize(CD.BAR_H, CD.BAR_H)
    bar.icon:SetPoint("LEFT", bar, "LEFT", 0, 0)
    bar.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    bar.icon:SetTexture(UI.IconPath(CD.BAR_ICON) or CD.BAR_ICON)
    local sb = CreateFrame("StatusBar", nil, bar)
    sb:SetSize(CD.BAR_W, CD.BAR_H)
    sb:SetPoint("RIGHT", bar, "RIGHT", 0, 0)
    sb.bg = sb:CreateTexture(nil, "BACKGROUND")
    sb.bg:SetTexture(CD.BAR_FILL)
    sb.bg:SetAllPoints(sb)
    sb.bg:SetVertexColor(0.16, 0.16, 0.16, 0.75)
    sb:SetStatusBarTexture(CD.BAR_FILL)
    sb:SetMinMaxValues(0, 1)
    sb:SetValue(0)
    sb:SetStatusBarColor(CD.BarColor(0))
    sb.spark = sb:CreateTexture(nil, "OVERLAY")
    sb.spark:SetTexture(CD.BAR_SPARK)
    sb.spark:SetBlendMode("ADD")
    sb.spark:SetSize(24, CD.BAR_H * 2)
    sb.spark:Hide()
    bar.spark = sb.spark
    -- the texts over the spark
    local top = CreateFrame("Frame", nil, sb)
    top:SetAllPoints(sb)
    top:SetFrameLevel(sb:GetFrameLevel() + 1)
    bar.name = UI.Text(top, 10, C.text, "body", "LEFT")
    bar.name:SetPoint("LEFT", sb, "LEFT", 6, 0)
    UI.OneLine(bar.name, CD.BAR_W - 52)
    bar.name:SetText(CD.BAR_TEXT)
    bar.time = UI.Text(top, 10, C.text, "body", "RIGHT")
    bar.time:SetPoint("RIGHT", sb, "RIGHT", -4, 0)
    bar.sb = sb
    return bar
end
f.bar = buildBar()

local function updateBar(left)
    local bar, sb = f.bar, f.bar.sb
    local p = U.Clamp(1 - left / max(CD.total or 1, 0.01), 0, 1)
    sb:SetValue(p)
    sb:SetStatusBarColor(CD.BarColor(p))
    local text = CD.BarText(left)
    if bar.timeText ~= text then
        bar.timeText = text
        bar.time:SetText(text)
    end
    local a = CD.BarFlash(left)
    local fill = sb:GetStatusBarTexture()
    if fill then
        fill:SetAlpha(a)
    end
    if p > 0.005 and p < 0.995 then
        sb.spark:ClearAllPoints()
        sb.spark:SetPoint("CENTER", sb, "LEFT", p * CD.BAR_W, 0)
        sb.spark:SetAlpha(a)
        sb.spark:Show()
    else
        sb.spark:Hide()
    end
end

------------------------------------------------------------------------------------------------------
-- The numerals: Royale's Pull atlas (RoyaleArtData.lua loads after this file: read when a numeral shows)
------------------------------------------------------------------------------------------------------
local function pullAtlas()
    local art = ns.RoyaleArt
    return art and art.atlases and art.atlases.Pull
end

local function setZoom(d, z)
    d.zoom = z
    local P = pullAtlas()
    local g = P and d.glyph and P.glyphs[d.glyph]
    if g then
        local c = CD.BIG_CAP * z
        d.tex:SetSize(g.w * c, g.h * c)
        d.glow:SetSize(g.w * c, g.h * c)
    end
end

-- d shows the numeral `text` (a key of the atlas's glyphs); false when the atlas has no such glyph.
local function setGlyph(d, text)
    local P = pullAtlas()
    local g = P and P.glyphs[text]
    if not g then
        return false
    end
    d.glyph = text
    d.tex:SetTexture(P.file)
    d.tex:SetTexCoord(g.u0, g.u1, g.v0, g.v1)
    d.glow:SetTexture(P.glow)
    d.glow:SetTexCoord(g.u0, g.u1, g.v0, g.v1)
    d:SetSize((g.inkW + 2 * g.stroke) * CD.BIG_CAP, (1 + 2 * g.stroke) * CD.BIG_CAP)
    setZoom(d, d.zoom or 1)
    return true
end

local function newBig(level)
    local d = CreateFrame("Frame", nil, f)
    d:SetFrameLevel(base + level)
    d:SetPoint("CENTER", f, "TOP", 0, CD.NUM_Y)
    d:SetSize(CD.BIG_CAP, CD.BIG_CAP)
    d.glow = d:CreateTexture(nil, "BACKGROUND")
    d.glow:SetPoint("CENTER", d, "CENTER", 0, 0)
    d.glow:SetBlendMode("ADD")
    d.glow:SetVertexColor(CD.GLOW_COLOR[1], CD.GLOW_COLOR[2], CD.GLOW_COLOR[3])
    d.glow:SetAlpha(0)
    d.tex = d:CreateTexture(nil, "ARTWORK")
    d.tex:SetPoint("CENTER", d, "CENTER", 0, 0)
    d.zoom = 1
    d:Hide()
    return d
end
f.numOld = newBig(3)
f.num = newBig(4)
-- the numeral that shows now first, the one fading out second
f.digits = { f.num, f.numOld }

local function outCubic(p)
    return 1 - (1 - p) ^ 3
end

-- The pop and the fade at `now` (every frame while they run).
local function animate(now)
    local num, old = f.num, f.numOld
    if num:IsShown() and num.popAt then
        local t = now - num.popAt
        if not motion() then
            t = 99
        end
        local p = outCubic(min(1, t / CD.POP_DUR))
        setZoom(num, CD.POP + (1 - CD.POP) * p)
        num:SetAlpha(min(1, t / CD.IN_DUR))
        local q = outCubic(min(1, t / CD.GLOW_DUR))
        num.glow:SetAlpha(CD.GLOW_PEAK + (CD.GLOW_REST - CD.GLOW_PEAK) * q)
        if t >= CD.GLOW_DUR then
            num.popAt = nil
        end
    end
    if old:IsShown() and old.outAt then
        local t = now - old.outAt
        if not motion() or t >= CD.OUT_DUR then
            old.outAt = nil
            old:Hide()
        else
            local p = t / CD.OUT_DUR
            old:SetAlpha((old.fromAlpha or 1) * (1 - p * p * p))
        end
    end
end

-- Hide our numerals when DBM already draws its centre countdown and the player asked for that.
function CD.HideNumerals()
    if not ns.Option("hideNumeralsWithDBM", false) then
        return false
    end
    return DBM ~= nil and type(DBM.Options) == "table" and DBM.Options.DontShowPTCountdownText == false
end

-- The numeral n pops in (the last five seconds; above them, or with the numerals hidden, none shows); the one before
-- fades out.
local function setNumber(n)
    local num, old = f.num, f.numOld
    if n == num.shown then
        return
    end
    num.shown = n
    if num:IsShown() and num.glyph then
        setGlyph(old, num.glyph)
        setZoom(old, num.zoom or 1)
        old.fromAlpha = num:GetAlpha()
        old:SetAlpha(old.fromAlpha)
        old.glow:SetAlpha(num.glow:GetAlpha())
        old.outAt = GetTime()
        old:Show()
    end
    if not n or n > CD.BIG_FROM or n < 1 or CD.HideNumerals() or not setGlyph(num, tostring(n)) then
        num:Hide()
        num.popAt = nil
        return
    end
    num:SetAlpha(0)
    num.glow:SetAlpha(CD.GLOW_PEAK)
    setZoom(num, CD.POP)
    num.popAt = GetTime()
    num:Show()
    animate(GetTime())
end
CD.SetNumber = setNumber

local function clearNumbers()
    for _, d in ipairs(f.digits) do
        d:Hide()
        d.popAt, d.outAt = nil, nil
    end
    f.num.shown = nil
end

------------------------------------------------------------------------------------------------------
-- DBM pull timer
------------------------------------------------------------------------------------------------------
CD.sentPull = false

local function dbmLoaded()
    return DBM ~= nil or (IsAddOnLoaded and IsAddOnLoaded("DBM-Core")) and true or false
end

-- Returns the channel the DBM message goes to, or nil when this client should not send it.
function CD.PullChannel()
    if Comm.HasFeature(Comm.FEATURE.DBM_BY_SERVER) or not ns.Option("dbmPull", true) then
        return nil
    end
    local kind, _, leader, officer = ns.GroupInfo()
    if kind == "RAID" then
        return (leader or officer) and "RAID" or nil
    elseif kind == "PARTY" then
        return leader and "PARTY" or nil
    end
    return dbmLoaded() and "WHISPER" or nil
end

-- Whether the DBM loaded is a 4.x build (the stock 3.3.5a DBM-Core: Pizza timers only, a release number), not a newer
-- one (a date) or none.
function CD.OldDbm()
    local d = DBM
    if type(d) ~= "table" or type(d.CreatePizzaTimer) ~= "function" then
        return false
    end
    local rev = tonumber(d.ReleaseRevision)
    return rev ~= nil and rev < CD.DBM_OLD_BELOW
end

function CD.SendPull(seconds)
    local channel = CD.PullChannel()
    if not channel then
        return false
    end
    if Comm.demo then
        ns.Print("demo: DBM pull timer of " .. seconds .. " s would go to " .. channel:lower())
        return false
    end
    local body = tostring(seconds)
    local old = CD.OldDbm()
    if channel ~= "WHISPER" then
        SendAddonMessage(CD.DBM_PREFIX, body, channel)
        if seconds >= 3 then
            SendAddonMessage(CD.DBM_PIZZA_PREFIX, body .. "\t" .. CD.BAR_TEXT, channel)
        end
    elseif not old then
        SendAddonMessage(CD.DBM_PREFIX, body, "WHISPER", ns.PlayerName())
    end
    -- a 4.x DBM shows nothing for its own player's message: the sender's bar is made here
    if old and seconds > 0 then
        pcall(DBM.CreatePizzaTimer, DBM, seconds, CD.BAR_TEXT, false)
    end
    CD.sentPull = seconds > 0
    return true
end

-- A realm whose server sends the pull timer itself (DBM_BY_SERVER: BleakholdMgr's RunPullTimerLocked) sends
-- "DBMv4-PT" only, which a 4.x DBM does not know: there every client with a 4.x DBM, leader or member, makes its own
-- "Pull in" bar (not broadcast), unless the player turned the DBM pull bar off (/bh dbm off). A newer DBM takes the
-- server's PT. Answers whether it made one.
function CD.LocalServerPull(seconds)
    if Comm.demo or seconds < 3 or not Comm.HasFeature(Comm.FEATURE.DBM_BY_SERVER) or not ns.Option("dbmPull", true)
        or not CD.OldDbm() then
        return false
    end
    return (pcall(DBM.CreatePizzaTimer, DBM, seconds, CD.BAR_TEXT, false))
end

-- DBM's "Pull in" bar goes (a 4.x DBM has no message that cancels a Pizza timer).
function CD.CancelDbmBar()
    local d = DBM
    local bars = type(d) == "table" and type(d.Bars) == "table" and d.Bars or nil
    if bars and type(bars.CancelBar) == "function" then
        pcall(bars.CancelBar, bars, CD.BAR_TEXT)
    end
end

-- Whether DBM shows its "Pull in" bar now: DBM-Core's bar module (DBM.Bars, DBT) finds a bar by its name, as
-- RoyaleCountdown.StartDbm checks its drop bar. nil when this DBM cannot be asked.
local function dbmPullBarShown()
    local d = DBM
    local bars = type(d) == "table" and type(d.Bars) == "table" and d.Bars or nil
    if not bars or type(bars.GetBar) ~= "function" then
        return nil
    end
    local ok, b = pcall(bars.GetBar, bars, CD.BAR_TEXT)
    return (ok and b ~= nil and b ~= false) and true or false
end

-- DBM shows its own "Pull in" bar for the keystone countdown, so ours hides and one bar shows. DBM is asked whether
-- its bar is there (every CD.Update), never assumed: the pull timer may not come (the leader turned it off with
-- /bh dbm off, or this DBM dropped the leader's message), and then ours stays. A DBM that cannot be asked: the timer
-- went out for sure (this client sent it, or the server sends it).
function CD.DbmBar()
    if CD.generic or not dbmLoaded() then
        return false
    end
    local shown = dbmPullBarShown()
    if shown ~= nil then
        return shown
    end
    return (CD.sentPull or Comm.HasFeature(Comm.FEATURE.DBM_BY_SERVER)) and true or false
end

-- Our bar, unless DBM's shows (again when DBM's goes before zero).
local function claimBar()
    if CD.DbmBar() then
        f.bar:Hide()
    else
        f.bar:Show()
    end
end

------------------------------------------------------------------------------------------------------
-- Countdown
------------------------------------------------------------------------------------------------------
function CD.Remaining()
    local g = CD.generic
    if g then
        return g.endsAt - GetTime()
    end
    local m = S.mplus
    if not m or m.state ~= 0 or m.result then
        return 0
    end
    return (m.countdownMs or 0) / 1000 - (GetTime() - (m.startedAt or GetTime()))
end

-- An affix's name and tooltip text by the server's id (MPS), as the Keys page names it (ns.Keys.AffixInfo: Data.lua's
-- built-in DEF A numbers some of them differently, 4 Volcanic there for the server's Raging).
function CD.AffixInfo(id)
    local K = ns.Keys
    if K and K.AffixInfo then
        return K.AffixInfo(id)
    end
    local d = ns.Def("A", id)
    return ns.AffixNames({ id })[1], d and d.text
end

-- The affix icons (the server's affix ids) and the era, centred under the title.
local function layoutHead(ids, era)
    local shown = {}
    for i, a in ipairs(f.affixes) do
        local id = ids and ids[i]
        if id then
            local name, text = CD.AffixInfo(id)
            a:SetAffix(name, nil, text)
            -- the Mythic Champions and Mythical Boons have no affix icon of their own: the Keys page's
            local special = ns.Keys and ns.Keys.SPECIAL_ICONS and ns.Keys.SPECIAL_ICONS[id]
            if special then
                a:SetIcon(special)
            end
            a:Show()
            shown[#shown + 1] = a
        else
            a:Hide()
        end
    end
    if era then
        UI.SetText(f.era, era)
        f.era:Show()
        shown[#shown + 1] = f.era
    else
        f.era:SetText("")
        f.era:Hide()
    end
    local gap, width = 6, 0
    for i, r in ipairs(shown) do
        width = width + (r == f.era and (f.era:GetStringWidth() or 0) or r:GetWidth()) + (i > 1 and gap or 0)
        if r == f.era and i > 1 then
            width = width + 4
        end
    end
    local prev
    for _, r in ipairs(shown) do
        r:ClearAllPoints()
        if not prev then
            r:SetPoint("LEFT", f.affixRow, "CENTER", -floor(width / 2 + 0.5), 0)
        else
            r:SetPoint("LEFT", prev, "RIGHT", r == f.era and gap + 4 or gap, 0)
        end
        prev = r
    end
end

function CD.Start(m)
    local secs = floor((m.countdownMs or 0) / 1000 + 0.5)
    if secs <= 0 then
        return
    end
    CD.generic = nil
    f.kicker:SetText((m.level or 0) == 0 and CD.M0_KICKER or CD.KEY_KICKER)
    UI.SetText(f.title, ns.DungeonName(m.dungeonId) .. ((m.level or 0) > 0 and (" +" .. m.level) or ""))
    local era = m.eraId and (ns.DefName("E", m.eraId, "Era") .. " era") or nil
    layoutHead(m.affixes, era)
    f.bar.name:SetText(CD.BAR_TEXT)
    f.bar.timeText = nil
    CD.total = secs
    clearNumbers()
    if secs >= 3 and not CD.SendPull(secs) then
        CD.LocalServerPull(secs)
    end
    claimBar()
    f:Show()
    -- the right-click's "Keystone ready: press Start keystone" (bh_ui_bridge.cpp) is done; it sat under the head and
    -- the bar (after f:Show, so the toasts waiting behind it wait for the countdown too: Toast.Covered)
    if ns.Toast and ns.Toast.Dismiss then
        ns.Toast.Dismiss("keys", CD.READY_TOAST)
    end
    CD.Update()
end

-- A countdown of another kind: the same bar and numerals, the given kicker and title (the bar is named after the
-- kicker), no affixes and no DBM pull timer. ms counts from now; a new call replaces a running generic countdown, and a
-- keystone countdown (CD.Start) replaces it too.
function CD.StartGeneric(kicker, title, ms)
    local secs = (tonumber(ms) or 0) / 1000
    if secs <= 0 then
        return
    end
    CD.generic = { endsAt = GetTime() + secs, kicker = kicker, title = title }
    UI.SetText(f.kicker, kicker or "")
    UI.SetText(f.title, title or "")
    layoutHead(nil, nil)
    UI.SetText(f.bar.name, kicker or "")
    f.bar.timeText = nil
    CD.total = secs
    clearNumbers()
    claimBar()
    f:Show()
    CD.Update()
end

-- Hide a generic countdown (the keystone one is left alone).
function CD.StopGeneric()
    if CD.generic then
        CD.generic = nil
        f:Hide()
        clearNumbers()
        f.kicker:SetText(CD.KEY_KICKER)
    end
end

function CD.Stop(cancelled)
    if CD.generic then
        CD.generic = nil
        f.kicker:SetText(CD.KEY_KICKER)
    end
    f:Hide()
    clearNumbers()
    if cancelled then
        local sent = CD.sentPull
        if sent then
            CD.SendPull(0)
        end
        -- the bar this client made, or a 4.x DBM's from the leader's Pizza: nothing else takes it away
        if sent or CD.OldDbm() then
            CD.CancelDbmBar()
        end
    end
    CD.sentPull = false
end

function CD.Update()
    local left = CD.Remaining()
    if left <= 0 then
        CD.Stop(false)
        return
    end
    claimBar()
    updateBar(left)
    setNumber(min(99, ceil(left - 1e-6)))
end

f:SetScript("OnUpdate", function(self, elapsed)
    self.acc = (self.acc or 0) + (elapsed or 0)
    if self.acc >= 0.05 then
        self.acc = 0
        CD.Update()
    end
    if self:IsShown() then
        animate(GetTime())
    end
end)

ns.On("MPLUS_START", function(m)
    CD.Start(m)
end)
ns.On("MPLUS_GO", function()
    CD.Stop(false)
end)
ns.On("MPLUS_ABANDONED", function()
    if f:IsShown() then
        CD.Stop(true)
    end
end)
ns.On("MPLUS_END", function()
    if f:IsShown() then
        CD.Stop(true)
    end
end)

ns.AddCommand("dbm", "DBM pull bar for keystone starts: /bh dbm on|off", function(args)
    args = (args or ""):lower()
    if args == "on" or args == "off" then
        ns.db.options.dbmPull = args == "on"
    end
    ns.Print("DBM pull timer for keystone starts: " .. (ns.Option("dbmPull", true) and "on" or "off"))
end)
