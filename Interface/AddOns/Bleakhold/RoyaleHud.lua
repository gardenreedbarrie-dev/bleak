-- Bleakhold: Bleakhold Royale's HUD (docs/BleakholdProtocol.md section 17), drawn from server state only, in the
-- Royale style kit (RoyaleStyle.lua: riveted plates, engraved labels, baked titles and numerals):
--   the top bar      a plate of three cells, label over value (H.BarCells): players or alive, the drop or storm clock,
--                    the landing or the player's kills; stage gems under the clock (one per storm stage, ROYS
--                    `stages`); a tab tucked under it for one line at a time (the warm-up, where the player lands,
--                    the storm's damage while outside the circle, SAFE on leaving it, overtime). One clock on screen:
--                    the middle cell has no time while the countdown runs (RoyaleCountdown.lua) or the player falls
--                    (RoyaleDrop.lua). From the landing on (the server's phase 2 lasts until everyone is down) the
--                    storm clock; the bar fades out a second after the match's end card
--   banners          a ribbon under the bar, one at a time, at most one waiting per kind: the circle, the storm
--                    moving, supply drops, players left, the winner (VICTORY for the winner only), the storm beast;
--                    the kill announcer (first blood, streaks, multi-kills) is Announcer.lua's (BGANN, section 18). In
--                    the fight the stock error text moves under the ribbon (unless AddicatUI has it placed)
--   the kill feed    five lines at the top right, newest on top, that fade after 8 s (ROYK); killer, cause icon,
--                    victim in class colours, the player's own lines marked in gold; it steps left of a quest tracker
--                    that would sit under it
--   the storm        a violet storm edge over the world while outside the circle (WorldFrame, so Alt-Z keeps it),
--                    softer when Bleakhold.exe tints the screen itself, with one pulse per storm hit (the arrow to the
--                    safe zone is RoyaleMinimap.lua's); in Bleakhold.exe also the storm wall in the world
--                    (BleakholdStorm_*, WoW/Source/Ui/BleakholdStorm.h): the circle of every ROYS goes to the exe,
--                    which moves it like R.Circle and draws a purple wall on its edge and a pale ring where the next
--                    circle is; /bh royale wall [on|off|test|stop]
--   spectating       SPECTATING <name> · N kills, with Prev / Killer / Next (RSPEC), Queue again (QJOIN B), Leave
--   the end card     ROYE: VICTORY or ELIMINATED, the rank of the total, four stat tiles counting up, the rewards
-- The drop countdown (the last 15 s of the lobby) is RoyaleCountdown.lua's, the drop RoyaleDrop.lua's.
-- The bar, the feed and the spectator bar are movable (drag, or AddicatUI's editor mode through ns.Movers); every
-- root frame takes the HUD scale (/bh royale scale).
--
-- ROYK's `announce` field is superseded by BGANN and ignored (State.lua), so nothing plays twice.
local ADDON, ns = ...
local U, UI = ns.U, ns.UI
local S = ns.S
local R = ns.Royale
local RS = ns.RoyaleStyle
local DATA = ns.RoyaleArt

local type, tostring, ipairs, pairs = type, tostring, ipairs, pairs
local floor, ceil, max, min, abs = math.floor, math.ceil, math.max, math.min, math.abs
local strformat = string.format

local H = {}
ns.RoyaleHud = H

-- The HUD's numbers and tables (set in a function, like the frames below: see buildBar)
local function defineConstants()
    H.FEED_LINES = 5
    H.FEED_TIME = 8                  -- s a kill feed line stays (it fades over the last one)
    H.FEED_W, H.FEED_LINE_H = 330, 24
    H.FEED_NAME_W = 132              -- units a name may take before it is cut
    H.BANNER_IN, H.BANNER_HOLD, H.BANNER_OUT = 0.2, 2.4, 0.3
    H.BANNER_TIME = H.BANNER_IN + H.BANNER_HOLD + H.BANNER_OUT
    -- the ribbon's iron band runs from 15 to 80 units down, under a bronze diamond down to 28: the title row sits
    -- under the diamond's tip, the line over the lower hairline; a banner with no line centres its title row
    H.BANNER = { w = 620, h = 96, titleY = -41, lineY = -69, soloY = -47, cap = 26, capMin = RS.TITLE_MIN_CAP,
        icon = 32, numeral = 30, textW = 476, lineW = 560 }
    H.BAR = { w = 384, h = 72, cellX = 12, cellTop = 10, cellW = 120, cellH = 52, textW = 112, labelY = -12,
        valueY = -26, label = 10, value = 20, winner = 14, sepY = -14, sepH = 36, pipY = -52, pip = 12, pipGlow = 20,
        pipGap = 14, pipRow = 116 }
    H.TAB = { w = 300, h = 24, y = 4, textW = 280, icon = 14, text = 12 }
    H.BAR_Y = 6                      -- the bar's default spot: TOP 0,-6 (in its own, HUD-scaled units)
    H.LOBBY_GAP, H.LOBBY_TOP = 14, 112   -- lobby windows start this far under the tab, never above 112 (spec 1.5)
    H.EMBER_FROM = 20                -- s: a clock's value turns ember (the lobby's last 20 s, a hold's last 20 s)
    H.SAFE_FLASH = 0.6               -- s SAFE shows in the tab after leaving the storm
    H.WARMUP_LINE = 8                -- s the lobby's tab says the brawl is safe before it points at the map
    H.STORM_SOUND_GAP = 10           -- s: entering the storm plays its sound at most this often
    H.EDGE = { base = 0.5, native = 0.25, pulse = 0.1, settle = 0.5, gap = 0.8 }
    H.PIP_PULSE = 3                  -- s the gem just lit pulses
    H.ERRORS_Y, H.ERRORS_FIGHT_Y = -122, -206   -- the stock error text's spot, and under the banner in the fight
    H.END_FADE = 1                   -- s after the end card shows the bar fades out (cancelled: after the phase)
    H.CHEER_GAP = 5                  -- s: VICTORY's sound plays once for the banner and the card together
    H.CAUSE_ICON = { P = "swords", S = "storm", F = "fall", L = "door", A = "afk", B = "claw" }
    H.CAUSE_SUFFIX = { L = " (left)", A = " (away)" }
    H.BOSS_NAME = "Thundermaw"
    H.BOSS_FLEE_ALIVE = 3            -- the realm's Boss.FleeAlive: at so few players left the beast leaves them be
    -- the tab's rim in the storm: a violet cast on the bronze (stormDeep would turn the plate black, as
    -- SetVertexColor multiplies)
    H.STORM_TAB_TINT = "C9A8F0"
    H.DASH = "-"                     -- no value: an engraved dash is drawn (FRIZQT may lack the em dash)
    -- labels that do not fit their cell at a small UI scale (12-px labels, RoyaleStyle.lua) take the short form
    H.SHORT = { ["STORM CLOSES IN"] = "CLOSES IN", ["STORM CLOSING"] = "CLOSING", ["FINAL STORM"] = "FINAL",
        ["MATCH OVER"] = "OVER", ["CANCELLED"] = "OFF" }
end
defineConstants()

------------------------------------------------------------------------------------------------------
-- Positions: saved per character like the key tracker's, in the frame's own units (it carries the HUD scale)
------------------------------------------------------------------------------------------------------
local function positioning(f, defPoint, defX, defY)
    UI.MakeMovable(f)
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
        local s = f:GetScale() or 1
        f:ClearAllPoints()
        f:SetPoint(point, UIParent, relPoint, x / s, y / s)
        if save then
            ns.cdb.windows[f:GetName()] = { point = point, relPoint = relPoint, x = x / s, y = y / s }
        end
    end
    function t.Reset()
        ns.cdb.windows[f:GetName()] = nil
        t.Anchor()
    end
    return t
end

-- Server names, safe for a FontString, in their class colour.
local function classText(name, classId)
    if not name then
        return ""
    end
    return U.Color(ns.ClassColor(classId), U.Safe(name))
end
H.ClassText = classText

-- A player's class this match, from the kill feed or the result (ROYV W carries no class).
function H.ClassOf(name)
    if not name then
        return nil
    end
    local res = S.royaleResult
    if res and res.winnerName == name and res.winnerClassId then
        return res.winnerClassId
    end
    for i = #S.royaleFeed, 1, -1 do
        local k = S.royaleFeed[i]
        if k.killer == name and k.killerClassId then
            return k.killerClassId
        elseif k.victim == name then
            return k.victimClassId
        end
    end
    return nil
end

local function kills(n)
    return n .. (n == 1 and " kill" or " kills")
end

-- Text set only when it changes (the bar is redrawn ten times a second; the client relays out a string on SetText).
local function setText(fs, text)
    text = text or ""
    if fs.hudText ~= text then
        fs.hudText = text
        fs:SetText(text)
    end
end

-- One line, `w` units wide, cut with an ellipsis: a width and a height of one line (a font string with a width and
-- no height wraps). The height follows the font when the kit sizes it again (a new screen, UI scale or HUD scale).
local oneLines = setmetatable({}, { __mode = "k" })
local function oneLine(fs, w)
    if w then
        oneLines[fs] = w
        fs:SetWidth(w)
        fs:SetNonSpaceWrap(false)
    end
    local _, size = fs:GetFont()
    fs:SetHeight((size or 12) + 4)
end

local function refreshLines()
    for fs in pairs(oneLines) do
        oneLine(fs)
    end
    if H.RefitLabels then
        H.RefitLabels()
    end
end
ns.RegisterEvent("DISPLAY_SIZE_CHANGED", refreshLines)
ns.RegisterEvent("CVAR_UPDATE", refreshLines)
ns.On("ROYALE_HUD_SCALE", refreshLines)
ns.On("DB_READY", refreshLines)

-- A panel's entrance (alpha 0 -> 1, from `dy` units higher) and exit (alpha -> 0, `up` units up), RoyaleStyle motion.
local function enter(f, dy, duration)
    f:SetAlpha(0)
    f:Show()
    RS.Tween(f, "alpha", 0, 1, duration or 0.2, "outCubic")
    RS.Tween(f, "offset", { 0, dy or 12 }, { 0, 0 }, duration or 0.2, "outCubic")
end

local function leave(f, up, duration, after)
    RS.Tween(f, "offset", nil, { 0, up or 8 }, duration or 0.25, "inCubic")
    RS.Tween(f, "alpha", nil, 0, duration or 0.25, "inCubic", { onDone = function()
        f:Hide()
        RS.Stop(f, "offset")
        if after then
            after()
        end
    end })
end

-- Colour a font string: a flash tweens from `from` to the colour, else it is set (never while a flash runs).
local function setColor(fs, color, from)
    if fs.hudColor == color then
        return
    end
    fs.hudColor = color
    if from then
        RS.Tween(fs, "vertexColor", from, color, from == "safe" and 0.3 or 0.2, "outCubic")
    else
        RS.Stop(fs, "vertexColor")
        fs:SetTextColor(RS.Rgb(color))
    end
end

------------------------------------------------------------------------------------------------------
-- The top bar
------------------------------------------------------------------------------------------------------
local B, T = H.BAR, H.TAB
local bar, barPos, pipCell, tab

-- The frames are built in functions: each function has its own constants, and the client's Lua 5.1 miscompiles some
-- arithmetic in a chunk past 256 of them (see test_royale_hud.lua); the file's main chunk stays well under that.
local function buildBar()
    bar = CreateFrame("Frame", "BleakholdRoyaleBar", UIParent)
    bar:SetSize(B.w, B.h)
    bar:SetFrameStrata("MEDIUM")
    bar:SetFrameLevel(5)
    bar:Hide()
    RS.RegisterRoot(bar)
    H.bar = bar
    barPos = positioning(bar, "TOP", 0, -H.BAR_Y)
    H.barPos = barPos
    bar.art = RS.Plate(bar, "Plate")

    bar.cells = {}
    for i = 1, 3 do
        local c = CreateFrame("Frame", nil, bar)
        c:SetSize(B.cellW, B.cellH)
        c:SetPoint("TOPLEFT", bar, "TOPLEFT", B.cellX + B.cellW * (i - 1), -B.cellTop)
        c:SetFrameLevel(bar:GetFrameLevel() + 2)
        -- anchored to the cell, so a cell's cross-fade moves its label and value together
        c.label = RS.Text(c, "label", B.label, "ash", "CENTER")
        c.label:SetPoint("TOP", c, "TOP", 0, B.labelY + B.cellTop)
        oneLine(c.label, B.textW)
        c.value = RS.Text(c, "value", B.value, "parchment", "CENTER")
        c.value:SetPoint("TOP", c, "TOP", 0, B.valueY + B.cellTop)
        oneLine(c.value, B.textW)
        -- no value: an engraved dash, dark-edged like the outlined values
        c.dashEdge = UI.Solid(c, "000000", "ARTWORK", 0.75)
        c.dashEdge:SetSize(18, 4)
        c.dashEdge:SetPoint("CENTER", c.value, "CENTER", 0, 0)
        c.dash = UI.Solid(c, RS.C.parchment, "OVERLAY", 1)
        c.dash:SetSize(16, 2)
        c.dash:SetPoint("CENTER", c.value, "CENTER", 0, 0)
        c.icon = RS.Icon(c, "fall", 18, "OVERLAY")
        c.icon:SetPoint("CENTER", c.value, "CENTER", 0, 0)
        c.icon:Hide()
        bar.cells[i] = c
        if i < 3 then
            local sep = RS.Hairline(bar, B.sepH, "bronzeLo", true, "BORDER", 0.9)
            sep:SetPoint("TOP", bar, "TOPLEFT", B.cellX + B.cellW * i, B.sepY)
        end
    end
    -- the middle value, by its old name
    bar.main = bar.cells[2].value

    -- the stage gems under the middle cell's value (in its frame, so they dim with it): a socket each, a violet gem
    -- and its glow when lit
    bar.pips = {}
    pipCell = bar.cells[2]
    for i = 1, ns.ROYALE_MAX_STAGES do
        local p = RS.Art(pipCell, "Gem", B.pip, B.pip, "ARTWORK", DATA.gem.socket)
        p.glow = RS.Art(pipCell, "GemGlow", B.pipGlow, B.pipGlow, "OVERLAY")
        p.glow:SetBlendMode("ADD")
        p.glow:SetVertexColor(RS.Rgb("storm"))
        p.glow:SetPoint("CENTER", p, "CENTER", 0, 0)
        p.gem = RS.Art(pipCell, "Gem", B.pip, B.pip, "OVERLAY", DATA.gem.gem)
        p.gem:SetVertexColor(RS.Rgb("storm"))
        p.gem:SetPoint("CENTER", p, "CENTER", 0, 0)
        p:Hide()
        p.glow:Hide()
        p.gem:Hide()
        bar.pips[i] = p
    end

    -- the tab tucked under the bar's rim (a level below it): one line at a time, an optional icon left of it
    tab = CreateFrame("Frame", nil, bar)
    tab:SetSize(T.w, T.h)
    tab:SetPoint("TOP", bar, "BOTTOM", 0, T.y)
    tab:SetFrameLevel(bar:GetFrameLevel() - 1)
    tab:Hide()
    bar.tab = tab
    tab.art = RS.Plate(tab, "PlateTab")
    tab.text = RS.Text(tab, "body", T.text, "parchment", "LEFT")
    tab.icon = RS.Icon(tab, "storm", T.icon, "OVERLAY")
    tab.icon:SetPoint("RIGHT", tab.text, "LEFT", -6, 0)
    tab.icon:Hide()
    bar.sub = tab.text

    -- the editor's sample
    H.SAMPLE = {
        matchId = 0, phase = 3, phaseMsLeft = 0, alive = 23, total = 32, me = 2, kills = 2, stage = 2, curX = 0,
        curY = 0, curR = 320, nextX = 0, nextY = 0, nextR = 180, shrinkStartMs = 45000, shrinkEndMs = 95000,
        dmgPermille = 20, stages = 6,
    }
end
buildBar()

-- A label in its short form when the full one does not fit its cell (again after a new screen or scale).
local function fitLabel(c)
    if not c.hudLabel then
        return
    end
    c.label:SetText(c.hudLabel)
    if c.label:GetStringWidth() > B.textW and H.SHORT[c.hudLabel] then
        c.label:SetText(H.SHORT[c.hudLabel])
    end
end

function H.RefitLabels()
    for _, c in ipairs(bar.cells) do
        fitLabel(c)
    end
end

-- Centre the first n gems under the middle cell's value, min(14, 116 / n) apart.
function H.LayoutPips(n)
    if bar.pipCount == n then
        return
    end
    bar.pipCount = n
    local gap = min(B.pipGap, B.pipRow / max(n, 1))
    for i, p in ipairs(bar.pips) do
        p:ClearAllPoints()
        p:SetPoint("TOP", pipCell, "TOP", (i - (n + 1) / 2) * gap, B.pipY + B.cellTop)
    end
end

-- What the tab says about the landing in the lobby (phase 0 and 1).
local function landingLine(m)
    local RC = ns.RoyaleCountdown
    local locked = RC and RC.Locked and RC.Locked(m)
    if m.pinX and m.pinY then
        if locked then
            return "Landing locked"
        end
        return "Landing at " .. U.Safe(ns.RoyaleMap.NearestPlace(m.pinX, m.pinY))
    end
    if locked then
        return "You drop at random."
    end
    local key = ns.RoyaleMap.KeyText()
    if key:sub(1, 1) == "/" then
        return "Type " .. key .. " to choose your landing"
    end
    return "Press " .. key .. " to choose your landing"
end

-- The tab while the storm beast stirs (ROYO X incoming): where its green beam stands, for the players who would go
-- there. No clock: the banner and the map carry the time until it wakes.
local function beastLine(m)
    local MP = ns.RoyaleMap
    local o = MP.BossObject and MP.BossObject(m)
    if not (o and o.state == 3) then
        return nil
    end
    local bp = H.beastPlace
    local where = bp and bp.matchId == m.matchId and bp.name or nil
    if not where then
        local p = MP.NearestPlace(o.x, o.y)
        where = p ~= "the wilds" and p or nil
    end
    local beam = RS.Color("beast", "green beam")
    if where then
        return { text = "Follow the " .. beam .. " to " .. U.Safe(where) .. ".", icon = "beast" }
    end
    return { text = "Follow the " .. beam .. " to its den.", icon = "beast" }
end
H.BeastLine = beastLine

-- The winner's name in its class colour, or nil.
local function winnerText()
    local e = S.royaleEvent
    local res = S.royaleResult
    local name = (e and e.kind == "W" and e.name) or (res and res.winnerName)
    return name and classText(name, H.ClassOf(name)) or nil
end

-- The bar's three cells { label, value, color, icon, dim, size } and its tab { text, icon, color, storm } (or nil) for
-- the match `m`. A value of H.DASH shows the engraved dash; no value and no icon leaves the label alone.
function H.BarCells(m)
    local left, mid, right, tabLine
    local lobby = R.InLobby(m)
    if lobby then
        local q = S.queue
        local cap = q and q.kind == "B" and q.maxPlayers
        left = { label = "PLAYERS", value = (m.total or 0) .. ((cap and cap > 0) and ("/" .. cap) or "") }
        if m.pinX and m.pinY then
            right = { label = "LANDING", value = "SET", color = "gold" }
        elseif m.phase == R.PHASE.COUNTDOWN then
            right = { label = "LANDING", value = "RANDOM", color = "ember" }
        else
            right = { label = "LANDING", value = H.DASH }
        end
    else
        left = { label = "ALIVE", value = (m.alive or 0) .. "/" .. (m.total or 0) }
        local k = m.kills or 0
        right = { label = "KILLS", value = tostring(k), color = k > 0 and "gold" or "parchment" }
    end
    if m.phase == R.PHASE.ARRIVING then
        local t = R.PhaseLeft(m)
        mid = t and { label = "STARTS IN", value = RS.Clock(t) } or { label = "WAITING", value = H.DASH }
        local since = GetTime() - (H.lobbyAt or GetTime())
        if not (m.pinX and m.pinY) and since < H.WARMUP_LINE then
            tabLine = { text = "Warm-up brawl. Nobody dies here." }
        else
            tabLine = { text = landingLine(m) }
        end
    elseif m.phase == R.PHASE.COUNTDOWN then
        local RC = ns.RoyaleCountdown
        if RC and RC.OwnsClock(m) then
            mid = { label = "DROP IN", dim = true }   -- the countdown's ring holds the time: one clock on screen
        else
            local t = R.PhaseLeft(m)
            mid = { label = "DROP IN", value = t and RS.Clock(t) or H.DASH,
                color = (t and t <= H.EMBER_FROM) and "ember" or nil }
        end
        tabLine = { text = landingLine(m) }
    elseif m.me == R.ME.DROPPING then
        mid = { label = "DROPPING", icon = "altitude" }   -- the drop plate carries the times
    elseif m.phase == R.PHASE.VICTORY then
        mid = { label = "WINNER", value = winnerText() or H.DASH, size = B.winner }
    elseif m.phase >= R.PHASE.ENDED then
        mid = { label = m.phase == R.PHASE.ENDED and "MATCH OVER" or "CANCELLED", value = H.DASH }
    else
        local what, sec = R.StormTimer(m)
        if R.Overtime(m) then
            mid = { label = "FINAL STORM", value = H.DASH, color = "ember" }
            tabLine = { text = "The storm has closed. It grows every 5 s." }
        elseif what == "hold" then
            mid = { label = "STORM CLOSES IN", value = RS.Clock(sec),
                color = sec <= H.EMBER_FROM and "ember" or nil }
        elseif what == "moving" then
            mid = { label = "STORM CLOSING", value = RS.Clock(sec), color = "stormLight" }
        else
            local stage = m.stage or 0
            mid = { label = "CIRCLE", value = stage > 0 and (stage .. "/" .. R.StageCount(m)) or H.DASH }
        end
        -- outside the circle: the storm's damage; just out of it: SAFE
        if m.me == R.ME.ALIVE and (H.outside or H.preview) and (m.dmgPermille or 0) > 0 then
            tabLine = { text = "IN THE STORM  " .. RS.Color("ember", strformat("-%.1f%% HP/s", m.dmgPermille / 10)),
                icon = "storm", storm = true }
        elseif m.me == R.ME.ALIVE and GetTime() < (H.safeUntil or 0) then
            tabLine = { text = "SAFE", color = "safe" }
        elseif m.me == R.ME.ALIVE and not R.Overtime(m) then
            tabLine = beastLine(m) or tabLine
        end
    end
    return { left, mid, right }, tabLine
end

-- The tab: shown with text (sliding down 8 units), a new line swaps in place, no line slides it back up.
local function setTab(line)
    local key = line and (line.text .. "|" .. tostring(line.icon) .. "|" .. tostring(line.color)) or nil
    if key == tab.key then
        return
    end
    tab.key = key
    if not line then
        if tab:IsShown() and not tab.leaving then
            tab.leaving = true
            leave(tab, 8, 0.2, function() tab.leaving = nil end)
        end
        return
    end
    local wasLeaving = tab.leaving
    tab.leaving = nil
    tab.text:SetWidth(0)
    tab.text:SetText(line.text)
    tab.text:SetTextColor(RS.Rgb(line.color or "parchment"))
    local iconRoom = line.icon and (T.icon + 6) or 0
    local full, limit = tab.text:GetStringWidth(), T.textW - iconRoom
    local w = min(full, limit)
    oneLine(tab.text, full <= limit and full + 2 or limit)   -- 2 units of slack: no ellipsis from rounding
    tab.text:ClearAllPoints()
    tab.text:SetPoint("LEFT", tab, "CENTER", -(w + iconRoom) / 2 + iconRoom, 0)
    if line.icon then
        tab.icon:SetIcon(line.icon)
        tab.icon:Show()
    else
        tab.icon:Hide()
    end
    tab.art:SetColor(line.storm and H.STORM_TAB_TINT or "safe")
    if not tab:IsShown() or wasLeaving then
        enter(tab, 8, 0.2)
    end
end
H.SetTab = setTab

-- One cell: the label (its short form if it does not fit), the value or the dash or the icon, its colour (an ember
-- clock flashes once as it turns; the kills flash gold as they rise), and a quick cross-fade when the cell changes
-- meaning (PLAYERS to ALIVE at the landing, DROP IN to DROPPING, ...).
local function setCell(c, cell, flash)
    local changed = c.hudLabel ~= cell.label
    if changed then
        c.hudLabel = cell.label
        fitLabel(c)
    end
    local size = cell.size or B.value
    if c.hudSize ~= size then
        c.hudSize = size
        RS.Font(c.value, "value", size)
        oneLine(c.value)
        -- a smaller value (the winner's name) sits on the same middle as the others
        c.value:ClearAllPoints()
        c.value:SetPoint("TOP", c, "TOP", 0, B.valueY + B.cellTop - (B.value - size) / 2)
    end
    local dash = cell.value == H.DASH
    setText(c.value, (dash or not cell.value) and "" or cell.value)
    if dash then
        c.dash:Show()
        c.dashEdge:Show()
        c.dash:SetVertexColor(RS.Rgb(cell.color or "parchment"))
    else
        c.dash:Hide()
        c.dashEdge:Hide()
    end
    if cell.icon then
        c.icon:SetIcon(cell.icon)
        c.icon:Show()
    else
        c.icon:Hide()
    end
    setColor(c.value, cell.color or "parchment", flash)
    local alpha = cell.dim and 0.35 or 1
    if changed and c.hudShown then
        RS.Tween(c, "alpha", 0, alpha, 0.2, "outCubic")
        RS.Tween(c, "offset", { 0, 4 }, { 0, 0 }, 0.2, "outCubic")
    elseif c.hudAlpha ~= alpha then
        RS.Tween(c, "alpha", nil, alpha, 0.2, "outCubic")
    end
    c.hudAlpha, c.hudShown = alpha, true
end

-- The gems: lit up to the stage (all in overtime); the one just lit pulses for a few seconds.
local function updatePips(m)
    local count = R.StageCount(m)
    local show = m.me ~= R.ME.DROPPING and m.phase < R.PHASE.VICTORY
    local lit = 0
    if R.Fighting(m) then
        lit = R.Overtime(m) and count or min(m.stage or 0, count)
    end
    H.LayoutPips(count)
    local now = GetTime()
    if bar.pipMatch == m.matchId and lit > (bar.pipLit or 0) and lit <= count then
        bar.pipPulse, bar.pipPulseAt = lit, now
    end
    bar.pipMatch, bar.pipLit = m.matchId, lit
    for i, p in ipairs(bar.pips) do
        if show and i <= count then
            p:Show()
            p.lit = i <= lit
            if p.lit then
                p.gem:Show()
                p.glow:Show()
                local pulsing = i == bar.pipPulse and now - (bar.pipPulseAt or 0) < H.PIP_PULSE
                if pulsing and not p.pulsing then
                    p.pulsing = true
                    RS.Loop(p.glow, "pulse", { from = 0.35, to = 1 })
                elseif not pulsing then
                    if p.pulsing then
                        p.pulsing = nil
                        RS.StopLoop(p.glow, "pulse")
                    end
                    p.glow:SetAlpha(i == lit and 0.7 or 0.4)
                end
            else
                p.gem:Hide()
                p.glow:Hide()
            end
        else
            p.lit = false
            p:Hide()
            p.gem:Hide()
            p.glow:Hide()
        end
    end
end

-- Per match: the moment the client first saw it in the lobby, the player's kills, whether the bar went at the end.
local function barMatch(m)
    if H.barMatchId ~= m.matchId then
        H.barMatchId = m.matchId
        H.lobbyAt = R.InLobby(m) and GetTime() or nil
        H.lastKills = m.kills or 0
        H.barGone, H.barFadeAt, H.safeUntil = nil, nil, nil
        RS.Stop(bar)
        bar:SetAlpha(1)
        for _, c in ipairs(bar.cells) do
            c.hudShown = nil
        end
    elseif not H.lobbyAt and R.InLobby(m) then
        H.lobbyAt = GetTime()
    end
end

function H.UpdateBar(m)
    m = m or (H.preview and H.SAMPLE)
    if not m then
        H.barMatchId = nil
        if bar:IsShown() then
            RS.Stop(bar, nil, true)
            bar:Hide()
        end
        return
    end
    barMatch(m)
    -- the end: the bar fades out a second after the end card shows (or the cancelled phase arrives)
    if m.phase >= R.PHASE.ENDED and not H.preview then
        if H.barGone then
            return
        end
        local now = GetTime()
        H.barFadeAt = H.barFadeAt or ((H.resultShownAt and H.resultShownAt <= now) and H.resultShownAt or now)
            + H.END_FADE
        if now >= H.barFadeAt then
            H.barGone = true
            if bar:IsShown() then
                leave(bar, 0, 0.4)
            end
            return
        end
    end
    local cells, tabLine = H.BarCells(m)
    -- flashes: the kills rising (gold, with the clang), a clock turning ember
    local k = m.kills or 0
    local killFlash = k > (H.lastKills or k) and not H.preview
    H.lastKills = k
    if killFlash then
        RS.PlayFile("kill")
    end
    local midFlash = cells[2].color == "ember" and bar.cells[2].hudColor ~= "ember" and bar.cells[2].hudShown
        and bar.cells[2].hudLabel == cells[2].label
    setCell(bar.cells[1], cells[1])
    setCell(bar.cells[2], cells[2], midFlash and "safe" or nil)
    if killFlash then
        bar.cells[3].hudColor = nil
    end
    setCell(bar.cells[3], cells[3], killFlash and "safe" or nil)
    updatePips(m)
    setTab(tabLine)
    if not bar:IsShown() then
        barPos.Anchor()
        bar:SetAlpha(1)
        bar:Show()
    end
end

------------------------------------------------------------------------------------------------------
-- The kill feed
------------------------------------------------------------------------------------------------------
local feed, feedPos
local function buildFeed()
    feed = CreateFrame("Frame", "BleakholdRoyaleFeed", UIParent)
    feed:SetSize(H.FEED_W, H.FEED_LINES * H.FEED_LINE_H)
    feed:SetFrameStrata("MEDIUM")
    feed:Hide()
    RS.RegisterRoot(feed)
    H.feed = feed
    feedPos = positioning(feed, "TOPRIGHT", -24, -232)     -- under the minimap, clear of the buffs
    H.feedPos = feedPos

    feed.lines = {}
    for i = 1, H.FEED_LINES do
        local l = CreateFrame("Frame", nil, feed)
        l:SetSize(H.FEED_W, H.FEED_LINE_H)
        l:SetPoint("TOPRIGHT", feed, "TOPRIGHT", 0, -(i - 1) * H.FEED_LINE_H)
        -- the body moves (a new line slides in, older ones step down); the line's own alpha is its age
        local b = CreateFrame("Frame", nil, l)
        b:SetSize(H.FEED_W, H.FEED_LINE_H)
        b:SetPoint("TOPRIGHT", l, "TOPRIGHT", 0, 0)
        l.body = b
        l.strip = RS.Art(b, "FeedStrip", 200, H.FEED_LINE_H - 2, "BACKGROUND")
        l.strip:SetPoint("RIGHT", b, "RIGHT", 0, 0)
        -- the player's own lines: a gold wash over the strip (fading left with it) and a gold bar at its right edge
        l.wash = UI.Solid(b, "FFFFFF", "BORDER", 1)
        l.wash:SetSize(200, H.FEED_LINE_H - 2)
        l.wash:SetPoint("RIGHT", b, "RIGHT", 0, 0)
        l.wash:SetBlendMode("ADD")
        do
            local r, g, bl = RS.Rgb("gold")
            l.wash:SetGradientAlpha("HORIZONTAL", r, g, bl, 0, r, g, bl, 0.32)
        end
        l.mark = UI.Solid(b, RS.C.gold, "ARTWORK", 1)
        l.mark:SetSize(2, H.FEED_LINE_H - 2)
        l.mark:SetPoint("RIGHT", b, "RIGHT", 0, 0)
        l.victim = RS.Text(b, "body", 12, "parchment", "RIGHT")
        l.victim:SetPoint("RIGHT", b, "RIGHT", -12, 0)
        l.icon = RS.Icon(b, "swords", 16, "ARTWORK")
        l.icon:SetPoint("RIGHT", l.victim, "LEFT", -5, 0)
        l.killer = RS.Text(b, "body", 12, "parchment", "RIGHT")
        l.killer:SetPoint("RIGHT", l.icon, "LEFT", -5, 0)
        l:Hide()
        feed.lines[i] = l
    end

    H.FEED_SAMPLE = {
        { killer = "Aldric", killerClassId = 1, victim = "Brenna", victimClassId = 8, cause = "P" },
        { victim = "Corwin", victimClassId = 5, cause = "S" },
    }
end
buildFeed()

-- A name in a feed line, cut at H.FEED_NAME_W.
local function feedName(fs, text)
    fs:SetWidth(0)
    fs:SetText(text)
    if fs:GetStringWidth() > H.FEED_NAME_W then
        oneLine(fs, H.FEED_NAME_W)
    else
        fs:SetHeight(0)
    end
    return min(fs:GetStringWidth(), H.FEED_NAME_W)
end

-- The storm beast itself as the killer: State.lua marks it (cause B, class 0, which no player has); a player may be
-- called Thundermaw, so the name alone never decides.
local function byBeast(k)
    return k.byBoss or (k.cause == "B" and k.killer ~= nil and k.killerClassId == 0)
end
H.ByBeast = byBeast

local function fillLine(l, k)
    local me = ns.PlayerName()
    local beast = byBeast(k)
    local killer = ""
    if k.killer then
        killer = beast and RS.Color("beast", H.BOSS_NAME) or classText(k.killer, k.killerClassId)
    end
    local suffix = H.CAUSE_SUFFIX[k.cause]
    local victim = classText(k.victim, k.victimClassId) .. (suffix and RS.Color("smoke", suffix) or "")
    local vw = feedName(l.victim, victim)
    local kw = k.killer and feedName(l.killer, killer) or feedName(l.killer, "")
    l.icon:SetIcon(H.CAUSE_ICON[k.cause] or "swords")
    -- the strip: the content, plus room on the right and a longer fade on the left
    local w = 12 + vw + 5 + 16 + (k.killer and (5 + kw) or 0) + 40
    w = min(H.FEED_W, floor(w + 0.5))
    l.strip:SetWidth(w)
    l.wash:SetWidth(w)
    local mine = me and ((k.killer == me and not beast) or k.victim == me)
    l.mine = mine and true or false
    if mine then
        l.wash:Show()
        l.mark:Show()
    else
        l.wash:Hide()
        l.mark:Hide()
    end
end

-- The feed steps left of a quest tracker it would cover (AddicatUI's sits under it by default; the stock WatchFrame
-- too), unless the player placed the feed. The tracker itself is never touched (its item buttons are secure).
local function trackerRect()
    local t = AddicatUI_QuestTrackerFrame
    if not (t and t:IsVisible()) then
        t = WatchFrame
        if not (t and t:IsVisible()) then
            return nil
        end
    end
    if not (GetNumQuestWatches and (GetNumQuestWatches() or 0) > 0) then
        return nil
    end
    local l, r, top, b = t:GetLeft(), t:GetRight(), t:GetTop(), t:GetBottom()
    if not (l and r and top and b) then
        return nil
    end
    local k = (t:GetEffectiveScale() or 1) / (UIParent:GetEffectiveScale() or 1)
    return t, l * k, r * k, top * k, b * k
end

function H.PlaceFeed()
    if feedPos.Saved() then
        H.feedBeside = nil
        return
    end
    local t, l, r, top, b = trackerRect()
    local s = feed:GetScale() or 1
    local W, Ht = UIParent:GetWidth(), UIParent:GetHeight()
    -- the feed's default rect in UIParent units (TOPRIGHT -24,-232 of a frame at the HUD scale)
    local fr, ft = W - 24 * s, Ht - 232 * s
    local fl, fb = fr - H.FEED_W * s, ft - H.FEED_LINES * H.FEED_LINE_H * s
    local beside = t and l < fr and r > fl and b < ft and top > fb and t or nil
    if beside ~= H.feedBeside then
        H.feedBeside = beside
        feed:ClearAllPoints()
        if beside then
            feed:SetPoint("TOPRIGHT", beside, "TOPLEFT", -12, 0)
        else
            feedPos.Anchor()
        end
    end
end

function H.UpdateFeed()
    if not H.feedPreview and (not R.Match() or #S.royaleFeed == 0) then
        if feed:IsShown() then
            feed:Hide()
        end
        H.feedShown = nil
        return
    end
    local list = {}
    local now = GetTime()
    if H.feedPreview then
        list = H.FEED_SAMPLE
    else
        local all = S.royaleFeed
        for i = #all, 1, -1 do
            local k = all[i]
            if now - (k.at or 0) < H.FEED_TIME and #list < H.FEED_LINES then
                list[#list + 1] = k
            end
        end
    end
    if #list == 0 then
        feed:Hide()
        H.feedShown = nil
        return
    end
    if not feed:IsShown() then
        feedPos.Anchor()
        H.feedBeside = nil
        feed:Show()
    end
    if now - (H.feedPlacedAt or 0) >= 0.5 then
        H.feedPlacedAt = now
        H.PlaceFeed()
    end
    -- a new line slides in from the right; the lines it pushes step down one slot
    local shown = H.feedShown or {}
    local fresh = list[1] ~= shown[1] and not H.feedPreview
    for i, l in ipairs(feed.lines) do
        local k = list[i]
        if k then
            if k ~= shown[i] then
                fillLine(l, k)
                if fresh and i == 1 then
                    RS.Tween(l.body, "alpha", 0, 1, 0.2, "outCubic")
                    RS.Tween(l.body, "offset", { 30, 0 }, { 0, 0 }, 0.2, "outCubic")
                elseif fresh and k == shown[i - 1] then
                    RS.Tween(l.body, "offset", { 0, H.FEED_LINE_H }, { 0, 0 }, 0.15, "outCubic")
                end
            end
            local age = H.feedPreview and 0 or (now - (k.at or now))
            l:SetAlpha(U.Clamp(H.FEED_TIME - age, 0, 1))
            l:Show()
        else
            l:Hide()
        end
    end
    H.feedShown = list
end

------------------------------------------------------------------------------------------------------
-- Event banners: one at a time, at most one waiting per kind
------------------------------------------------------------------------------------------------------
local BN = H.BANNER
local banner
local function buildBanner()
    banner = CreateFrame("Frame", "BleakholdRoyaleBanner", UIParent)
    banner:SetSize(BN.w, BN.h)
    banner:SetPoint("TOP", UIParent, "TOP", 0, -104)
    banner:SetFrameStrata("HIGH")
    banner:EnableMouse(false)
    banner:Hide()
    RS.RegisterRoot(banner)
    H.banner = banner
    banner.ribbon = RS.Art(banner, "Banner", BN.w, BN.h, "BACKGROUND")
    banner.ribbon:SetPoint("CENTER", banner, "CENTER", 0, 0)
    -- the shine: over the ribbon's iron band only (its ends fade to clear; 3.3.5 clips nothing, so it never moves)
    banner.shine = banner:CreateTexture(nil, "BORDER")
    banner.shine:SetBlendMode("ADD")
    banner.shine:SetPoint("TOPLEFT", banner, "TOPLEFT", 110, -18)
    banner.shine:SetPoint("BOTTOMRIGHT", banner, "BOTTOMRIGHT", -110, 18)
    banner.shine:SetTexCoord(RS.SHINE_TO[1], RS.SHINE_TO[2], RS.SHINE_TO[3], RS.SHINE_TO[4])
    banner.shine:SetAlpha(0.45)
    RS.LazyTexture(banner.shine, DATA.files.ShineStrip)
    banner.shine.rsArt = "ShineStrip"
    banner.title = RS.Title(banner, "NEW STORM CIRCLE", BN.cap, "storm")
    banner.icon = RS.Icon(banner, "storm", BN.icon, "ARTWORK")
    banner.num = RS.Numeral(banner, { cap = BN.numeral, justify = "LEFT", glowColor = "parchment" })
    banner.line = RS.Text(banner, "body", 13, "parchment", "CENTER")
    banner.line:SetPoint("CENTER", banner, "TOP", 0, BN.lineY)
    oneLine(banner.line, BN.lineW)
end
buildBanner()

H.queue = {}
H.current = nil

-- The banners of the match events (ROYV kinds): title (a Titles cell), colour, icon, the line under it (a function
-- of the event, read when the banner shows, so a waiting banner's clock is right), sound.
local function inClock(e)
    local t = e.msLeft and ns.RoyaleLeft(e.msLeft, e.recvAt)
    return t and (" in " .. RS.Clock(t)) or ""
end

local function placeOf(e)
    if e.x and e.y then
        return U.Safe(ns.RoyaleMap.NearestPlace(e.x, e.y))
    end
    return "the wilds"
end

local function buildEventBanners()
    H.EVENT_BANNERS = {
        R = { title = "NEW STORM CIRCLE", color = "storm", icon = "storm", sound = "MapPing",
            line = function(e)
                local n = e.value > 0 and e.value or max(1, (R.Match() and R.Match().stage) or 1)
                return strformat("The storm draws in. Circle %d of %d is on your map (%s).", n, R.StageCount(),
                    ns.RoyaleMap.KeyText())
            end },
        S = { title = "THE STORM MOVES", color = "storm", icon = "storm", sound = "RaidBossEmoteWarning",
            line = function(e)
                local what, sec = R.StormTimer()
                if e.msLeft then
                    return "Reach the white circle" .. inClock(e) .. "."
                elseif what == "moving" then
                    return "Reach the white circle in " .. RS.Clock(sec) .. "."
                end
                return "Reach the white circle."
            end },
        D = { title = "SUPPLY DROP", color = "gold", icon = "supply", sound = "MapPing",
            line = function(e) return "Supplies fall near " .. placeOf(e) .. inClock(e) .. "." end },
        N = { title = "PLAYERS LEFT", color = "parchment", numeral = true },
        B = { title = "A BEAST STIRS", color = "beast", icon = "beast", sound = "TrexPreAggro",
            line = function(e)
                local where = e.name and U.Safe(e.name) or placeOf(e)
                local t = e.msLeft and ns.RoyaleLeft(e.msLeft, e.recvAt)
                local wakes = t and (" It wakes in " .. RS.Clock(t) .. ".") or ""
                return H.BOSS_NAME .. " stirs at " .. where .. "!" .. wakes
            end },
        A = { title = "THUNDERMAW AWAKENS", color = "beast", icon = "beast", sound = "TrexAggro",
            line = function() return "Slay it and claim its hoard." end },
        K = { title = "THUNDERMAW SLAIN", color = "gold", icon = "hoard", sound = "TrexDeath", cheer = 0.6,
            line = function(e)
                local me = ns.PlayerName()
                if me and e.name == me then
                    return "You struck hardest. The hoard lies open."
                end
                local who = e.name and classText(e.name, H.ClassOf(e.name)) or "A hero"
                return who .. " struck hardest. The hoard lies open."
            end },
        -- it flees from the storm (its edge at the den, or overtime) or from the last few players
        F = { title = "THUNDERMAW FLEES", color = "ash", icon = "beast",
            line = function()
                local m = R.Match()
                if m and not R.Overtime(m) and (m.alive or 0) > 0 and m.alive <= H.BOSS_FLEE_ALIVE then
                    return "It leaves the last few to each other."
                end
                return "The storm drove it off."
            end },
    }
end
buildEventBanners()

-- e = { key, title (a Titles cell), color, icon, numeral, line (already safe for a FontString, or a function),
-- sound, cheer (s after which AchievementSound follows) }; keys "e<kind>" are the match events'. A newer banner of a
-- kind already waiting takes its place.
function H.Banner(e)
    for i, q in ipairs(H.queue) do
        if q.key == e.key then
            H.queue[i] = e
            return
        end
    end
    H.queue[#H.queue + 1] = e
end

-- VICTORY's AchievementSound plays once for the banner and the end card together.
local function cheer()
    local now = GetTime()
    if now - (H.cheerAt or -99) < H.CHEER_GAP then
        return
    end
    H.cheerAt = now
    RS.Play("AchievementSound")
end

-- The title row: icon or numeral, then the title, centred as one; long titles shrink to fit the iron band (never
-- under 21 units, where the baked Titles would be minified past 2.2x).
local function layoutBanner(e, solo)
    local at = DATA.atlases.Titles
    local cellT = DATA.titles[e.title]
    local s = at.stroke / at.cap
    local lead, leadW = nil, 0
    if e.numeral then
        banner.num:SetValue(e.value or "")
        lead, leadW = banner.num, banner.num:GetWidth() + 10
    elseif e.icon then
        banner.icon:SetIcon(e.icon)
        lead, leadW = banner.icon, BN.icon + 8
    end
    local cap = U.Clamp((BN.textW - leadW) / (cellT.inkW + 2 * s), BN.capMin, BN.cap)
    banner.title:SetTitle(e.title)
    banner.title:SetCap(cap)
    banner.title:SetColor(e.color)
    banner.title:SetGlowColor(e.color)
    local total = leadW + banner.title:GetWidth()
    local x = -total / 2
    local y = solo and BN.soloY or BN.titleY
    banner.icon:Hide()
    banner.num:Hide()
    if lead then
        lead:ClearAllPoints()
        -- the numeral's baseline on the title's (its cap is taller)
        lead:SetPoint("LEFT", banner, "TOP", x, y + (lead == banner.num and (BN.numeral - cap) / 2 or 0))
        lead:Show()
    end
    banner.title:ClearAllPoints()
    banner.title:SetPoint("LEFT", banner, "TOP", x + leadW, y)
end

local function showBanner(e)
    local line = type(e.line) == "function" and e.line(e) or e.line or ""
    layoutBanner(e, line == "")
    setText(banner.line, line)
    banner:SetAlpha(0)
    banner:Show()
    RS.Tween(banner, "alpha", 0, 1, H.BANNER_IN, "outCubic")
    RS.Tween(banner, "offset", { 0, 14 }, { 0, 0 }, H.BANNER_IN, "outCubic")
    RS.Tween(banner.title, "zoom", 1.15, 1, 0.22, "outBack")
    RS.Tween(banner.title.glow, "alpha", 0.6, 0, 0.6, "outCubic")
    RS.Sweep(banner.shine, 0.1, 0.6)
    if e.numeral then
        RS.Tween(banner.num.glow, "alpha", 0.5, 0, 0.5, "outCubic")
    end
    if e.sound == "AchievementSound" then
        cheer()
    elseif e.sound then
        RS.Play(e.sound)
    end
    if e.cheer then
        ns.After(e.cheer, cheer)
    end
end

function H.UpdateBanner()
    local now = GetTime()
    local cur = H.current
    if cur and not cur.leaving and now - cur.shownAt >= H.BANNER_IN + H.BANNER_HOLD then
        cur.leaving = true
        leave(banner, 8, H.BANNER_OUT)
    end
    if cur and now - cur.shownAt >= H.BANNER_TIME then
        H.current = nil
        cur = nil
    end
    if not cur and #H.queue > 0 then
        cur = table.remove(H.queue, 1)
        cur.shownAt = now
        H.current = cur
        showBanner(cur)
    end
    if not cur and banner:IsShown() and not RS.Busy(banner, "alpha") then
        banner:Hide()
    end
end

-- The winner's banner: VICTORY for the winner, WINNER and the winner's name for everyone else (an eliminated player
-- just saw ELIMINATED; a gold VICTORY would read as their own).
local function winnerBanner(e)
    local m = R.Match()
    local me = ns.PlayerName()
    local won = (m and m.me == R.ME.WINNER) or (me and e.name == me)
    if won then
        return { key = "eW", title = "VICTORY", color = "gold", icon = "crown", sound = "AchievementSound",
            line = "Last one standing · " .. kills(e.value) }
    end
    return { key = "eW", title = "WINNER", color = "parchment", icon = "crown",
        line = classText(e.name, H.ClassOf(e.name)) .. " · " .. kills(e.value) }
end

ns.On("ROYALE_EVENT", function(e)
    local def = H.EVENT_BANNERS[e.kind]
    if e.kind == "B" then
        local m = R.Match()
        H.beastPlace = { matchId = m and m.matchId, name = e.name }
    end
    if e.kind == "W" and e.name then
        H.Banner(winnerBanner(e))
    elseif e.kind == "N" and e.value > 0 then
        H.Banner({ key = "eN", title = def.title, color = def.color, numeral = true, value = e.value })
    elseif e.kind == "R" and R.InLobby() then
        return   -- in the lobby the countdown says it ("Circle 1 of 6 is on your map.")
    elseif def and def.line then
        H.Banner({ key = "e" .. e.kind, title = def.title, color = def.color, icon = def.icon, sound = def.sound,
            cheer = def.cheer, line = function() return def.line(e) end })
    else
        return
    end
    H.UpdateBanner()
end)

------------------------------------------------------------------------------------------------------
-- The stock error text: under the banner in the fight (its own spot, TOP 0,-122, is inside the banner's band), back
-- after the match; left alone when AddicatUI has a spot of its own for it (the player chose it) or anything else moved
-- it.
------------------------------------------------------------------------------------------------------
local function errorsAt(y)
    local f = UIErrorsFrame
    if not f or f:GetNumPoints() ~= 1 then
        return false
    end
    local p, rel, rp, x, py = f:GetPoint(1)
    return p == "TOP" and rp == "TOP" and (rel == nil or rel == UIParent) and abs(x or 0) < 0.5
        and abs((py or 0) - y) < 0.5
end

local function addicatPlacedErrors()
    local aui = _G.AddicatUI
    local p = aui and aui.db and aui.db.profile
    local cfg = p and p.widgets and p.widgets.errorMessages
    return cfg and cfg.custom_position and true or false
end

function H.UpdateErrors(m)
    local want = m ~= nil and m.phase >= R.PHASE.DROP and m.phase < R.PHASE.ENDED
    if want and not H.errorsMoved then
        if errorsAt(H.ERRORS_Y) and not addicatPlacedErrors() then
            UIErrorsFrame:ClearAllPoints()
            UIErrorsFrame:SetPoint("TOP", UIParent, "TOP", 0, H.ERRORS_FIGHT_Y)
            H.errorsMoved = true
        end
    elseif not want and H.errorsMoved then
        H.errorsMoved = nil
        if errorsAt(H.ERRORS_FIGHT_Y) then
            UIErrorsFrame:ClearAllPoints()
            UIErrorsFrame:SetPoint("TOP", UIParent, "TOP", 0, H.ERRORS_Y)
        end
    end
end

------------------------------------------------------------------------------------------------------
-- The storm: the edge over the world (the arrow to the safe zone on the minimap's edge is RoyaleMinimap.lua's)
------------------------------------------------------------------------------------------------------
local vg
local function buildEdge()
    vg = CreateFrame("Frame", "BleakholdRoyaleVignette", WorldFrame or UIParent)
    vg:SetAllPoints(WorldFrame or UIParent)
    vg:SetFrameStrata("BACKGROUND")
    vg:SetFrameLevel(0)
    vg:EnableMouse(false)
    vg:Hide()
    vg.tex = RS.Art(vg, "Vignette", nil, nil, "BACKGROUND")
    vg.tex:SetAllPoints(vg)
    vg.tex:SetVertexColor(RS.Rgb("storm"))
    H.vignette = vg
end
buildEdge()

-- The edge's resting alpha: softer while Bleakhold.exe tints the screen in the storm itself (BleakholdStorm.h).
function H.EdgeAlpha()
    if BleakholdStorm_Status and BleakholdStorm_Status() == "" then
        return H.EDGE.native
    end
    return H.EDGE.base
end

function H.UpdateStorm(m)
    local was = H.outside
    H.outside = false
    local fighting = m and m.me == R.ME.ALIVE and R.Fighting(m)
    local x, y = nil, nil
    if fighting then
        x, y = R.MyPos()
    end
    if x then
        local cx, cy, cr = R.Circle(m)
        local out = R.OutsideBy(x, y, cx, cy, cr)
        H.outside = out ~= nil and out > 0
    end
    local now = GetTime()
    if H.outside then
        if not was and now - (H.stormSoundAt or -99) >= H.STORM_SOUND_GAP then
            H.stormSoundAt = now
            RS.Play("igPVPUpdate")
        end
        if not RS.Busy(vg, "alpha") then
            vg:SetAlpha(H.EdgeAlpha())
        end
        vg:Show()
    else
        if was and fighting then
            H.safeUntil = now + H.SAFE_FLASH
        end
        RS.Stop(vg, "alpha")
        vg:Hide()
    end
end

-- One pulse per storm hit: the player's health falls while outside the circle (the storm damages once per tick).
ns.RegisterEvent("UNIT_HEALTH", function(_, unit)
    if unit ~= "player" or not UnitHealth then
        return
    end
    local hp = UnitHealth("player")
    local last = H.lastHealth
    H.lastHealth = hp
    if not (hp and last and hp < last and H.outside and vg:IsShown()) then
        return
    end
    local now = GetTime()
    if now - (H.pulseAt or -99) < H.EDGE.gap then
        return
    end
    H.pulseAt = now
    local base = H.EdgeAlpha()
    RS.Tween(vg, "alpha", base + H.EDGE.pulse, base, H.EDGE.settle, "outCubic")
end)

------------------------------------------------------------------------------------------------------
-- The storm wall in the world (Bleakhold.exe: BleakholdStorm_*). The exe moves the circle each frame exactly as
-- R.Circle does and forgets it 30 s after the last one; a stock client has none of these functions.
------------------------------------------------------------------------------------------------------
H.WALL_REFRESH = 10      -- s: the circle goes again this often without a new ROYS

-- A circle is up from the reveal of circle 1, 15 s before the drop, until the match is decided. In the lobby the
-- server's ROYS still says stage 0 after the reveal (stage 1 comes with the drop), with the next circle set.
function H.WallWanted(m)
    if m == nil or m.phase < R.PHASE.COUNTDOWN or m.phase > R.PHASE.OVERTIME then
        return false
    end
    return (m.stage or 0) >= 1 or (m.phase == R.PHASE.COUNTDOWN and m.nextR ~= nil)
end

function H.UpdateWall(m)
    if not BleakholdStorm_Set then
        return
    end
    if not H.WallWanted(m) then
        if H.wallKey then
            H.wallKey = nil
            if BleakholdStorm_Clear then
                BleakholdStorm_Clear()
            end
        end
        return
    end
    -- the lobby lies outside circle 0 but out of the storm's reach: no purple over the world there
    local noTint = m.me == R.ME.LOBBY
    local key = m.matchId .. ":" .. tostring(m.recvAt) .. ":" .. tostring(noTint)
    local now = GetTime()
    if key == H.wallKey and now - (H.wallSentAt or 0) < H.WALL_REFRESH then
        return
    end
    H.wallKey, H.wallSentAt = key, now
    local mapId = (S.royaleMap and S.royaleMap.mapId) or R.MAP_ID
    BleakholdStorm_Set(mapId, m.curX, m.curY, m.curR, m.nextX, m.nextY, m.nextR, m.recvAt, m.shrinkStartMs,
        m.shrinkEndMs, noTint)
end

H.WALL_STATUS = {
    [""] = "drawing the storm circle",
    off = "off (/bh royale wall on)",
    device = "needs the Direct3D 9 renderer with shader model 3",
    shaders = "this Bleakhold.exe has no storm shaders, or the graphics driver refused them",
    nodata = "on; no storm circle right now",
    map = "on; the storm circle is for another map",
}

function H.WallStatusText()
    if not BleakholdStorm_Status then
        return "Storm wall: this game is not Bleakhold.exe (the storm shows on the island map and as the purple "
            .. "screen edge)."
    end
    local status = BleakholdStorm_Status()
    return "Storm wall: " .. (H.WALL_STATUS[status] or tostring(status)) .. "."
end

-- /bh royale wall [on|off|test [radius [seconds]]|stop]
function H.WallCommand(args)
    local cmd, a, b = (args or ""):lower():match("^(%S*)%s*(%S*)%s*(%S*)")
    if (cmd == "on" or cmd == "off") and GetCVar and GetCVar("bleakStormWall") ~= nil then
        SetCVar("bleakStormWall", cmd == "on" and "1" or "0")
    elseif cmd == "test" and BleakholdStorm_Test then
        local radius = U.Clamp(tonumber(a) or 60, 5, 2000)
        local seconds = U.Clamp(tonumber(b) or 30, 1, 600)
        if H.WallWanted(R.Match()) then
            ns.Print("Storm wall test: not during a match; the wall shows the storm itself.")
        elseif BleakholdStorm_Test(radius, seconds) then
            ns.Print(string.format("Storm wall test: a %d yd circle around you closes to %d yd over %d s "
                .. "(/bh royale wall stop ends it).", radius, radius / 2, seconds))
        else
            ns.Print("Storm wall test: no position to put it at.")
            return
        end
    elseif cmd == "stop" and BleakholdStorm_Clear then
        BleakholdStorm_Clear()
        H.wallKey = nil
    end
    ns.Print(H.WallStatusText())
end

------------------------------------------------------------------------------------------------------
-- The spectator bar: SPECTATING and the watched player on top, the camera and the way out under it
------------------------------------------------------------------------------------------------------
H.SPECTATE = { w = 460, h = 68, rowY = -20, buttonY = -34, buttonH = 22, camera = 62, requeue = 112, leave = 70 }
local SP = H.SPECTATE
local sb, sbPos
local function buildSpectate()
    sb = CreateFrame("Frame", "BleakholdRoyaleSpectate", UIParent)
    sb:SetSize(SP.w, SP.h)
    sb:SetFrameStrata("MEDIUM")
    sb:Hide()
    RS.RegisterRoot(sb)
    H.spectate = sb
    sbPos = positioning(sb, "BOTTOM", 0, 170)
    H.spectatePos = sbPos
    sb.art = RS.Plate(sb, "Plate")

    sb.label = RS.Text(sb, "label", 10, "ash", "LEFT")
    sb.label:SetPoint("LEFT", sb, "TOPLEFT", RS.INSET + 2, SP.rowY)
    sb.label:SetText("SPECTATING")
    sb.name = RS.Text(sb, "body", 16, "parchment", "LEFT")
    sb.name:SetPoint("LEFT", sb.label, "RIGHT", 8, 0)
    local function sbButton(label, style, w, fn)
        local b = RS.Button(sb, w, SP.buttonH, label, style, 12)
        b:SetScript("OnClick", fn)
        return b
    end
    sb.prev = sbButton("« Prev", "iron", SP.camera, function() R.Spectate(R.SPEC.PREVIOUS) end)
    sb.killer = sbButton("Killer", "iron", SP.camera, function() R.Spectate(R.SPEC.KILLER) end)
    sb.next = sbButton("Next »", "iron", SP.camera, function() R.Spectate(R.SPEC.NEXT) end)
    sb.requeue = sbButton("Queue again", "gold", SP.requeue, function() R.Join() end)
    sb.leave = sbButton("Leave", "ghost", SP.leave, function() R.LeaveMatch() end)
    sb.prev:SetPoint("TOPLEFT", sb, "TOPLEFT", RS.INSET, SP.buttonY)
    sb.killer:SetPoint("LEFT", sb.prev, "RIGHT", 4, 0)
    sb.next:SetPoint("LEFT", sb.killer, "RIGHT", 4, 0)
    sb.leave:SetPoint("TOPRIGHT", sb, "TOPRIGHT", -RS.INSET, SP.buttonY)
    sb.requeue:SetPoint("RIGHT", sb.leave, "LEFT", -6, 0)
    sb.killer.tooltip = function()
        return { "Watch your killer", { "Or the first player alive.", RS.C.ash } }
    end

    H.SPECTATE_SAMPLE = { me = 3, watchName = "Aldric", phase = 3 }
end
buildSpectate()

-- "Aldric · 2 kills" (the name in its class colour), or the line when nobody is watched.
function H.SpectateText(m)
    if m.me == R.ME.SPECTATING and m.watchName then
        local name = classText(m.watchName, H.ClassOf(m.watchName))
        return name .. RS.Color("ash", " · " .. kills(R.KillsOf(m.watchName)))
    end
    return m.phase >= R.PHASE.VICTORY and "The match is over." or "No one left to watch."
end

function H.UpdateSpectator(m)
    m = m or (H.spectatePreview and H.SPECTATE_SAMPLE)
    if not m or (m.me ~= R.ME.SPECTATING and m.me ~= R.ME.LEFT) then
        sb.watch = nil
        if sb:IsShown() then
            sb:Hide()
        end
        return
    end
    local text = H.SpectateText(m)
    if sb.name.hudText ~= text then
        setText(sb.name, text)
        local room = SP.w - 2 * (RS.INSET + 2) - sb.label:GetStringWidth() - 8
        oneLine(sb.name, room)
        -- another player watched: the name cross-fades
        if sb:IsShown() and sb.watch ~= m.watchName then
            RS.Tween(sb.name, "alpha", 0, 1, 0.15, "outCubic")
        end
        sb.watch = m.watchName
    end
    local camera = m.me == R.ME.SPECTATING and m.phase < R.PHASE.ENDED
    sb.killer:SetActive(camera)
    sb.prev:SetActive(camera)
    sb.next:SetActive(camera)
    sb.requeue:SetActive(R.QueueBlock() == nil)
    if not sb:IsShown() then
        sbPos.Anchor()
        enter(sb, -12, 0.2)
    end
end

------------------------------------------------------------------------------------------------------
-- The end card (ROYE): the title, the rank of the total, four stat tiles, the rewards, the buttons
------------------------------------------------------------------------------------------------------
H.END = { w = 440, maxH = 430, top = 22, title = 32, rank = 22, tileW = 196, tileH = 52, gap = 8, rowH = 33,
    icon = 24, button = 26, bottom = 18, pad = 20, titleGap = 9 }
local EC = H.END
local ec
local function buildResult()
    ec = CreateFrame("Frame", "BleakholdRoyaleResult", UIParent)
    ec:SetSize(EC.w, 380)
    ec:SetPoint("CENTER", UIParent, "CENTER", 0, 40)
    ec:SetFrameStrata("DIALOG")
    ec:SetToplevel(true)
    ec:EnableMouse(true)
    ec:Hide()
    RS.RegisterRoot(ec)
    H.result = ec
    ec.art = RS.Plate(ec, "Plate")
    ec.shine = RS.Shine(ec.art, 0.5)
    ec.title = RS.Title(ec, "VICTORY", EC.title, "gold")
    ec.title:SetPoint("TOP", ec, "TOP", 0, -EC.top)
    ec.rank = RS.Numeral(ec, { cap = EC.rank, justify = "LEFT" })
    ec.of = RS.Text(ec, "body", 13, "ash", "LEFT")
    ec.winner = RS.Text(ec, "body", 12, "ash", "CENTER")
    oneLine(ec.winner, EC.w - 2 * EC.pad)

    H.STAT_LABELS = { "ELIMINATIONS", "DAMAGE", "HEALING", "SURVIVED" }
    ec.tiles = {}
    for i = 1, 4 do
        local t = CreateFrame("Frame", nil, ec)
        t:SetSize(EC.tileW, EC.tileH)
        t.art = RS.Plate(t, "PlateTab")
        t.value = RS.Text(t, "value", 20, "parchment", "CENTER")
        t.value:SetPoint("TOP", t, "TOP", 0, -8)
        oneLine(t.value, EC.tileW - 16)
        t.label = RS.Text(t, "label", 10, "ash", "CENTER")
        t.label:SetPoint("TOP", t, "TOP", 0, -33)
        t.label:SetText(H.STAT_LABELS[i])
        ec.tiles[i] = t
    end
    ec.sep = RS.Hairline(ec, EC.w - 2 * EC.pad - 40, "bronzeLo", false, "BORDER", 0.8)

    ec.rewards = {}
    for i = 1, 8 do
        local row = CreateFrame("Frame", nil, ec)
        row:SetSize(EC.w - 2 * EC.pad, EC.rowH)
        row.icon = RS.Icon(row, "honor", EC.icon, "ARTWORK")
        row.icon:SetPoint("LEFT", row, "LEFT", 4, 1)
        row.item = row:CreateTexture(nil, "ARTWORK")
        row.item:SetSize(EC.icon, EC.icon)
        row.item:SetPoint("LEFT", row, "LEFT", 4, 1)
        row.item:SetTexCoord(0.07, 0.93, 0.07, 0.93)
        row.amount = RS.Text(row, "body", 13, "gold", "LEFT")
        row.amount:SetPoint("TOPLEFT", row, "TOPLEFT", EC.icon + 14, -1)
        oneLine(row.amount, EC.w - 2 * EC.pad - EC.icon - 18)
        row.reason = RS.Text(row, "body", 11, "ash", "LEFT")
        row.reason:SetPoint("TOPLEFT", row, "TOPLEFT", EC.icon + 14, -17)
        oneLine(row.reason, EC.w - 2 * EC.pad - EC.icon - 18)
        row:Hide()
        ec.rewards[i] = row
    end
    ec.none = RS.Text(ec, "body", 12, "ash", "CENTER")
    oneLine(ec.none, EC.w - 2 * EC.pad)
    ec.none:SetText("No rewards. You left early or saw no fight.")

    ec.keep = RS.Button(ec, 124, EC.button, "Keep watching", "iron", 12)
    ec.requeue = RS.Button(ec, 132, EC.button, "Queue again", "gold", 12)
    ec.leave = RS.Button(ec, 84, EC.button, "Leave", "ghost", 12)
    ec.keep:SetScript("OnClick", function()
        H.resultDismissed = S.royaleResult and S.royaleResult.matchId
        H.resultPreview = nil
        ec:Hide()
    end)
    ec.requeue:SetScript("OnClick", function()
        R.Join()
    end)
    ec.leave:SetScript("OnClick", function()
        R.LeaveMatch()
    end)
end
buildResult()

-- The icon of a reward: ours for honor and Shards, the item's own (GetItemIcon) for an item.
H.REWARD_ICON = { H = "honor", S = "shards" }
local function rewardIcon(row, rw)
    local path = rw.kind == "I" and rw.itemId and GetItemIcon and GetItemIcon(rw.itemId)
    if path then
        row.item:SetTexture(path)
        row.item:Show()
        row.icon:Hide()
    else
        row.icon:SetIcon(H.REWARD_ICON[rw.kind] or "crown")
        row.icon:Show()
        row.item:Hide()
    end
end

-- The values the stat tiles show (and count up to): kills, damage, healing, seconds survived.
local function statText(i, v)
    v = floor(v + 0.5)
    if i == 4 then
        return RS.Clock(v, true)
    elseif i == 1 then
        return tostring(v)
    end
    return U.Commas(v)
end

local function countUp(t, i, target, animate)
    if not animate or target <= 0 then
        RS.Stop(t.value, "number")
        setText(t.value, statText(i, target))
        return
    end
    local lastAt = -1
    RS.Tween(t.value, "number", 0, target, 0.6, "outCubic", { set = function(v)
        local now = GetTime()
        if v >= target or now - lastAt >= 0.05 then   -- the text at 20 Hz, the last value exact
            lastAt = now
            setText(t.value, statText(i, v))
        end
    end })
end

-- Lays the card out for `res` (top to bottom) and returns its height; the rewards that do not fit end in a line
-- "and N more".
function H.LayoutResult(res)
    local won = res.placement == 1
    ec.title:SetTitle(won and "VICTORY" or "ELIMINATED")
    ec.title:SetColor(won and "gold" or "steel")
    ec.title:SetGlowColor(won and "gold" or "steel")
    local y = -EC.top - ec.title:GetHeight() - EC.titleGap
    -- the rank: "#7" in the metal numerals, "of 32" beside it on the same baseline
    ec.rank:SetValue("#" .. (res.placement or "?"))
    setText(ec.of, res.total and ("of " .. res.total) or "")
    local rankH = ec.rank:GetHeight()
    local ofW = res.total and (ec.of:GetStringWidth() + 6) or 0
    local total = ec.rank:GetWidth() + ofW
    local rankMid = y - rankH / 2
    ec.rank:ClearAllPoints()
    ec.rank:SetPoint("LEFT", ec, "TOP", -total / 2, rankMid)
    ec.of:ClearAllPoints()
    ec.of:SetPoint("LEFT", ec, "TOP", -total / 2 + ec.rank:GetWidth() + 6, rankMid - EC.rank / 2 + 5)
    y = y - rankH - 6
    -- the winner, for everyone else
    if res.winnerName and not won then
        local kk = res.winnerKills and (" · " .. kills(res.winnerKills)) or ""
        setText(ec.winner, "Winner · " .. classText(res.winnerName, res.winnerClassId) .. kk)
        ec.winner:ClearAllPoints()
        ec.winner:SetPoint("TOP", ec, "TOP", 0, y)
        ec.winner:Show()
        y = y - 18
    else
        ec.winner:Hide()
    end
    y = y - 8
    -- the tiles, two by two
    local x0 = -(2 * EC.tileW + EC.gap) / 2
    for i, t in ipairs(ec.tiles) do
        local col, row = (i - 1) % 2, floor((i - 1) / 2)
        t:ClearAllPoints()
        t:SetPoint("TOPLEFT", ec, "TOP", x0 + col * (EC.tileW + EC.gap), y - row * (EC.tileH + EC.gap))
    end
    y = y - 2 * EC.tileH - EC.gap - 9
    ec.sep:ClearAllPoints()
    ec.sep:SetPoint("TOP", ec, "TOP", 0, y)
    y = y - 9
    -- the rewards, as many as the card's height allows
    local fixed = -y + 14 + EC.button + EC.bottom
    local list = res.rewarded and res.rewards or {}
    local fit = max(1, floor((EC.maxH - fixed) / EC.rowH))
    local shown = #list <= fit and #list or (fit - 1)
    for i, row in ipairs(ec.rewards) do
        local rw = list[i]
        row:ClearAllPoints()
        if rw and i <= shown then
            rewardIcon(row, rw)
            setText(row.amount, "+" .. ns.RewardText(rw.kind, rw.amount, rw.itemId))
            setText(row.reason, rw.text and U.Safe(rw.text) or "")
            row:SetPoint("TOPLEFT", ec, "TOPLEFT", EC.pad, y)
            row:Show()
            y = y - EC.rowH
        elseif i == shown + 1 and #list > shown then
            row.icon:Hide()
            row.item:Hide()
            setText(row.amount, "")
            setText(row.reason, "and " .. (#list - shown) .. " more")
            row:SetPoint("TOPLEFT", ec, "TOPLEFT", EC.pad, y + 12)
            row:Show()
            y = y - 18
        else
            row:Hide()
        end
    end
    if #list == 0 then
        ec.none:ClearAllPoints()
        ec.none:SetPoint("TOP", ec, "TOP", 0, y - 4)
        ec.none:Show()
        y = y - 24
    else
        ec.none:Hide()
    end
    -- the buttons, centred
    y = y - 14
    local bw = ec.keep:GetWidth() + ec.requeue:GetWidth() + ec.leave:GetWidth() + 20
    ec.keep:ClearAllPoints()
    ec.keep:SetPoint("TOPLEFT", ec, "TOP", -bw / 2, y)
    ec.requeue:ClearAllPoints()
    ec.requeue:SetPoint("LEFT", ec.keep, "RIGHT", 10, 0)
    ec.leave:ClearAllPoints()
    ec.leave:SetPoint("LEFT", ec.requeue, "RIGHT", 10, 0)
    local h = min(EC.maxH, -y + EC.button + EC.bottom)
    ec:SetHeight(h)
    return h
end

-- Where a window under the top bar may start (the docked island map, the countdown, the end card's highest spot), in
-- UIParent units under the screen's top: H.LOBBY_GAP under the bar's tab at its default spot and the HUD scale (the
-- tab's bottom is 98 units down at scale 1, 137.2 at 1.4), never above H.LOBBY_TOP: 112 up to scale 1.14, 151.2 at
-- 1.4. Every fit is computed after the HUD scale (spec 1.5), so a larger HUD never puts the tab under a window.
function H.LobbyTop()
    local tabBottom = (H.BAR_Y + B.h - T.y + T.h) * RS.HudScale()
    return max(H.LOBBY_TOP, tabBottom + H.LOBBY_GAP)
end

-- The card's spot: CENTER 0,+40; raised over the spectator bar when both show at their default spots (a tall card
-- on a 768-unit screen would cover the bar's name), but never into the top bar and its tab.
H.END_GAP = 8
function H.PlaceResult()
    if RS.Busy(ec, "offset") then
        return
    end
    local y = 40
    if sb:IsShown() and not sbPos.Saved() then
        local s, ss = ec:GetScale() or 1, sb:GetScale() or 1
        local half, h = UIParent:GetHeight() / 2, ec:GetHeight() * s
        local need = (170 * ss + SP.h * ss + H.END_GAP - half + h / 2) / s
        local cap = (half - H.LobbyTop() - h / 2) / s
        y = max(40, min(need, cap))
    end
    local _, _, _, _, cy = ec:GetPoint(1)
    if cy ~= y then
        ec:ClearAllPoints()
        ec:SetPoint("CENTER", UIParent, "CENTER", 0, y)
    end
end

function H.ShowResult(res)
    res = res or S.royaleResult
    if not res then
        ec:Hide()
        return
    end
    local fresh = H.resultMatch ~= res.matchId or not ec:IsShown()
    H.resultMatch = res.matchId
    H.LayoutResult(res)
    local stats = { res.kills or 0, res.damage or 0, res.healing or 0, res.survivedSec or 0 }
    for i, t in ipairs(ec.tiles) do
        if fresh or t.hudTarget ~= stats[i] then
            countUp(t, i, stats[i], fresh)
            t.hudTarget = stats[i]
        end
    end
    local m = R.Match()
    ec.keep:SetLabel((m and m.me == R.ME.SPECTATING) and "Keep watching" or "Close")
    ec.requeue:SetActive(R.QueueBlock() == nil)
    H.PlaceResult()
    if fresh then
        H.resultShownAt = GetTime()
        enter(ec, 12, 0.2)
        RS.Tween(ec.title, "zoom", 1.15, 1, 0.22, "outBack")
        RS.Tween(ec.title.glow, "alpha", 0.8, 0, 0.8, "outCubic")
        RS.Sweep(ec.shine, 0.1, 0.6)
        for i, row in ipairs(ec.rewards) do
            if row:IsShown() then
                local delay = 0.25 + (i - 1) * 0.08
                row:SetAlpha(0)
                RS.Tween(row, "alpha", 0, 1, 0.2, "outCubic", { delay = delay })
                RS.Tween(row, "offset", { 16, 0 }, { 0, 0 }, 0.2, "outCubic", { delay = delay })
            end
        end
        if res.placement == 1 then
            cheer()
        else
            RS.Play("igQuestLogAbandonQuest")
        end
    end
end

ns.On("ROYALE_RESULT", function(res, first)
    if first then
        H.resultDismissed = nil
    end
    if H.resultDismissed ~= res.matchId then
        H.ShowResult(res)
    end
end)

------------------------------------------------------------------------------------------------------
-- Wiring: one tick for everything (cheap without a match)
------------------------------------------------------------------------------------------------------
function H.Tick()
    local m = R.Match()
    H.UpdateStorm(m)
    H.UpdateWall(m)
    H.UpdateBar(m)
    H.UpdateFeed()
    H.UpdateBanner()
    H.UpdateSpectator(m)
    H.UpdateErrors(m)
    -- back in the world: the card goes (its result stays on the Activities page)
    if ec:IsShown() and not S.royale and not H.resultPreview then
        ec:Hide()
    elseif ec:IsShown() then
        H.PlaceResult()
    end
end

ns.Every(0.1, H.Tick)

ns.On("ROYALE_MATCH", function()
    wipe(H.queue)
    H.current = nil
    RS.Stop(banner)
    banner:Hide()
    H.resultDismissed, H.resultMatch, H.resultShownAt = nil, nil, nil
    ec:Hide()
end)

ns.On("ROYALE_PHASE", function(m, before)
    if m.phase == R.PHASE.CANCELLED and before ~= R.PHASE.CANCELLED then
        ns.Toast.Push({ kicker = R.KICKER, title = "MATCH CANCELLED",
            sub = "Too few players came. You keep your place in the queue.", target = "royale" })
    end
end)

ns.On("STATE", function(topic)
    if topic == "ROYS" or topic == "ROYK" then
        H.Tick()
    end
end)

ns.On("DB_READY", function()
    barPos.Anchor()
    feedPos.Anchor()
    sbPos.Anchor()
end)

------------------------------------------------------------------------------------------------------
-- Samples: AddicatUI's editor mode (ns.Movers) and /bh royale preview banner|end (Royale.lua), outside a match
------------------------------------------------------------------------------------------------------
local function mover(name, title, frame, pos, flag)
    UI.AddMover({
        name = name,
        title = title,
        frame = frame,
        begin = function()
            H[flag] = true
            if flag == "preview" then
                H.SAMPLE.recvAt = GetTime()
            end
            H.Tick()
        end,
        finish = function()
            H[flag] = nil
            H.Tick()
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
local function registerSamples()
    mover("bleakhold_royale_bar", "Bleakhold Royale bar", bar, barPos, "preview")
    mover("bleakhold_royale_feed", "Bleakhold Royale kill feed", feed, feedPos, "feedPreview")
    mover("bleakhold_royale_spectate", "Bleakhold Royale spectator bar", sb, sbPos, "spectatePreview")

    H.RESULT_SAMPLE = {
        matchId = 0, placement = 1, total = 32, kills = 5, damage = 48210, healing = 6140, survivedSec = 702,
        rewarded = true, rewards = {
            { kind = "H", amount = 400, text = "Victory and 5 eliminations" },
            { kind = "S", amount = 25, text = "Journey" },
        },
    }
end
registerSamples()

-- /bh royale preview banner|end [eliminated]: the banners in turn, or the end card, with sample data. Not during a
-- match. Returns whether it played.
function H.Preview(kind, arg)
    if R.Match() then
        return false
    end
    if kind == "banner" then
        local n = R.StageCount()
        H.Banner({ key = "pR", title = "NEW STORM CIRCLE", color = "storm", icon = "storm", sound = "MapPing",
            line = strformat("The storm draws in. Circle 3 of %d is on your map (%s).", n, ns.RoyaleMap.KeyText()) })
        H.Banner({ key = "pD", title = "SUPPLY DROP", color = "gold", icon = "supply", sound = "MapPing",
            line = "Supplies fall near Tidecall Village in 0:20." })
        H.Banner({ key = "pN", title = "PLAYERS LEFT", color = "parchment", numeral = true, value = 10 })
        H.Banner({ key = "pA", title = "THUNDERMAW AWAKENS", color = "beast", icon = "beast",
            line = "Slay it and claim its hoard." })
        H.Banner({ key = "pW", title = "VICTORY", color = "gold", icon = "crown",
            line = "Last one standing · " .. kills(5) })
        H.UpdateBanner()
        return true
    elseif kind == "end" then
        local res = {}
        for k, v in pairs(H.RESULT_SAMPLE) do
            res[k] = v
        end
        if arg == "eliminated" then
            res.placement, res.winnerName, res.winnerClassId, res.winnerKills = 7, "Aldric", 1, 5
        end
        res.matchId = -GetTime()   -- a fresh card each time
        H.resultPreview = true
        H.ShowResult(res)
        return true
    end
    return false
end
