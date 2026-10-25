-- Bleakhold: Bleakhold Royale's HUD (docs/BleakholdProtocol.md section 17), drawn from server state only:
--   the top bar      players alive, own eliminations, the storm ("Storm moves in 0:45", "Storm moving 0:20"), one
--                    pip per storm stage (ROYS `stages`) and the storm's damage while the player is outside the
--                    circle, from the player's landing on (the server's phase 2 lasts until everyone has landed);
--                    in the lobby the drop countdown and "Pins lock in 3"
--   the kill feed    five lines at the top right that fade after 8 s (ROYK)
--   banners          milestones (ROYV N), the circle, the storm, supply drops and the winner; the kill announcer
--                    (first blood, streaks, multi-kills) is Announcer.lua's (BGANN, section 18) in every battleground
--   the parachute    "Open parachute" while falling from the drop (RDEPLOY; key binding BLEAKHOLD_ROYALE_DEPLOY)
--   the storm        a purple screen edge while outside the circle, and an arrow on the minimap's edge to the safe
--                    zone (the next circle once shown) with the distance
--   spectating       "Watching <name> (N kills)" with Killer / Prev / Next (RSPEC), Queue again (QJOIN B), Leave
--   the end card     ROYE: "#1 VICTORY" or "#7 of 32", eliminations, damage, healing, time survived, rewards
--   the countdown    the last seconds before the drop in the centre (Countdown.lua CD.StartGeneric)
-- The bar, the feed and the spectator bar are movable (drag, or AddicatUI's editor mode through ns.Movers).
--
-- ROYK's `announce` field is superseded by BGANN and ignored (State.lua), so nothing plays twice.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S
local R = ns.Royale

local floor, ceil, max, min, abs, sin, cos, atan2, pi = math.floor, math.ceil, math.max, math.min, math.abs, math.sin,
    math.cos, math.atan2, math.pi

local H = {}
ns.RoyaleHud = H

H.FEED_LINES = 5
H.FEED_TIME = 8                  -- s a kill feed line stays
H.BANNER_TIME = 2.5              -- s a banner holds (fade in and out included)
H.COUNTDOWN = 10                 -- the centre countdown shows the last seconds before the drop
H.CAUSE_GLYPH = { P = "sword", S = "flame", F = "down", L = "left", A = "hourglass" }
H.CAUSE_COLOR = { P = C.goldLight, S = C.purple, F = C.mid, L = C.mute, A = C.mute }
H.CAUSE_SUFFIX = { L = " (left)", A = " (away)", F = " (fell)" }
H.KICKER = "B L E A K H O L D   R O Y A L E"

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

local function clock(sec)
    return (U.Clock(ceil(sec or 0)):gsub("^00:", "0:"))
end

local function classText(name, classId)
    if not name then
        return ""
    end
    return U.Color(ns.ClassColor(classId), U.Safe(name))
end

------------------------------------------------------------------------------------------------------
-- The top bar
------------------------------------------------------------------------------------------------------
local bar = CreateFrame("Frame", "BleakholdRoyaleBar", UIParent)
bar:SetSize(440, 50)
bar:SetFrameStrata("MEDIUM")
UI.Backdrop(bar, "101216", C.chipBorder, 0.9)
bar:Hide()
H.bar = bar
local barPos = positioning(bar, "TOP", 0, -8)

bar.line = UI.Solid(bar, C.purple, "BORDER")
bar.line:SetPoint("TOPLEFT", bar, "TOPLEFT", 1, -1)
bar.line:SetPoint("TOPRIGHT", bar, "TOPRIGHT", -1, -1)
bar.line:SetHeight(2)
bar.aliveLabel = UI.Text(bar, 10, C.dim)
bar.aliveLabel:SetPoint("TOPLEFT", bar, "TOPLEFT", 12, -9)
bar.alive = UI.Text(bar, 16, C.text, "title")
bar.alive:SetPoint("TOPLEFT", bar.aliveLabel, "BOTTOMLEFT", 0, -2)
bar.killsLabel = UI.Text(bar, 10, C.dim, "body", "RIGHT")
bar.killsLabel:SetPoint("TOPRIGHT", bar, "TOPRIGHT", -12, -9)
bar.killsLabel:SetText("KILLS")
bar.kills = UI.Text(bar, 16, C.goldLight, "title", "RIGHT")
bar.kills:SetPoint("TOPRIGHT", bar.killsLabel, "BOTTOMRIGHT", 0, -2)
bar.main = UI.Text(bar, 15, C.goldPale, "body", "CENTER")
bar.main:SetPoint("TOP", bar, "TOP", 0, -9)
UI.OneLine(bar.main, 280)
H.PIP_GAP = 14
bar.pips = {}
for i = 1, ns.ROYALE_MAX_STAGES do
    local p = UI.Disc(bar, 8, C.track, "ARTWORK")
    p:Hide()
    bar.pips[i] = p
end

-- Centre the first n pips under the main text.
local function layoutPips(n)
    if bar.pipCount == n then
        return
    end
    bar.pipCount = n
    for i, p in ipairs(bar.pips) do
        p:ClearAllPoints()
        p:SetPoint("TOP", bar, "TOP", (i - (n + 1) / 2) * H.PIP_GAP, -32)
    end
end
bar.sub = UI.Text(bar, 12, C.purple, "body", "CENTER")
bar.sub:SetPoint("TOP", bar, "BOTTOM", 0, -4)
UI.OneLine(bar.sub, 420)

H.SAMPLE = {
    matchId = 0, phase = 3, phaseMsLeft = 0, alive = 23, total = 32, me = 2, kills = 2, stage = 2, curX = 0, curY = 0,
    curR = 320, nextX = 0, nextY = 0, nextR = 180, shrinkStartMs = 45000, shrinkEndMs = 95000, dmgPermille = 20,
    stages = 6,
}

function H.BarTexts(m)
    local main, sub = "", ""
    local lobby = R.InLobby(m)
    if m.phase == R.PHASE.ARRIVING then
        local left = R.PhaseLeft(m)
        main = "Players arriving"
        sub = left and ("The countdown starts in " .. clock(left)) or "Brawl while you wait"
    elseif m.phase == R.PHASE.COUNTDOWN then
        local left = R.PhaseLeft(m)
        main = left and ("Drop in " .. clock(left)) or "Drop soon"
        local lock = R.PinsLockIn(m)
        if lock and lock > 0 and lock <= 10 then
            sub = "Pins lock in " .. ceil(lock)
        elseif lock and lock <= 0 then
            sub = "Pins are locked"
        else
            sub = m.pinX and "Your landing pin is set" or "Set your landing pin on the map"
        end
    elseif R.Fighting(m) then
        local what, sec = R.StormTimer(m)
        if what == "hold" then
            main = "Storm moves in " .. clock(sec)
        elseif what == "moving" then
            main = "Storm moving " .. clock(sec)
        elseif R.Overtime(m) then
            main = "Overtime: the storm has closed"
        else
            main = m.stage > 0 and ("Storm stage " .. m.stage) or "Survive"
        end
    elseif m.phase == R.PHASE.DROP or m.phase == R.PHASE.FIGHT or m.phase == R.PHASE.OVERTIME then
        main = "The drop!"   -- still falling (a late drop too)
    elseif m.phase == R.PHASE.VICTORY then
        local e = S.royaleEvent
        local name = (e and e.kind == "W" and e.name) or (S.royaleResult and S.royaleResult.winnerName)
        main = name and (name .. " wins!") or "Victory"
    elseif m.phase == R.PHASE.ENDED then
        main = "The match is over"
    else
        main = "The match was cancelled"
    end
    return main, sub, lobby
end

function H.UpdateBar(m)
    m = m or (H.preview and H.SAMPLE)
    if not m then
        bar:Hide()
        return
    end
    local main, sub, lobby = H.BarTexts(m)
    bar.aliveLabel:SetText(lobby and "PLAYERS" or "ALIVE")
    bar.alive:SetText(lobby and tostring(m.total or 0) or ((m.alive or 0) .. " / " .. (m.total or 0)))
    bar.kills:SetText(tostring(m.kills or 0))
    UI.SetText(bar.main, main)
    local fighting = R.Fighting(m)
    local count = R.StageCount(m)
    local lit = R.Overtime(m) and count or (m.stage or 0)
    layoutPips(count)
    for i, p in ipairs(bar.pips) do
        if fighting and i <= count then
            p:SetVertexColor(UI.Rgb(i <= lit and C.purple or C.track))
            p:Show()
        else
            p:Hide()
        end
    end
    -- outside the circle: the storm's damage
    if fighting and m.me == R.ME.ALIVE and (H.outside or H.preview) and (m.dmgPermille or 0) > 0 then
        sub = string.format("Outside the storm circle: %.1f%% of your health per second", m.dmgPermille / 10)
    end
    UI.SetText(bar.sub, sub)
    if not bar:IsShown() then
        barPos.Anchor()
        bar:Show()
    end
end

------------------------------------------------------------------------------------------------------
-- The kill feed
------------------------------------------------------------------------------------------------------
local feed = CreateFrame("Frame", "BleakholdRoyaleFeed", UIParent)
feed:SetSize(330, H.FEED_LINES * 22)
feed:SetFrameStrata("MEDIUM")
feed:Hide()
H.feed = feed
local feedPos = positioning(feed, "TOPRIGHT", -24, -232)     -- under the minimap, clear of the buffs

feed.lines = {}
for i = 1, H.FEED_LINES do
    local l = CreateFrame("Frame", nil, feed)
    l:SetSize(330, 20)
    l:SetPoint("TOPRIGHT", feed, "TOPRIGHT", 0, -(i - 1) * 22)
    l.bg = UI.Solid(l, "000000", "BACKGROUND", 0.45)
    l.bg:SetPoint("RIGHT", l, "RIGHT", 0, 0)
    l.bg:SetHeight(20)
    l.victim = UI.Text(l, 12, C.text, "body", "RIGHT")
    l.victim:SetPoint("RIGHT", l, "RIGHT", -6, 0)
    l.icon = UI.Glyph(l, "sword", 14, C.goldLight)
    l.icon:SetPoint("RIGHT", l.victim, "LEFT", -5, 0)
    l.killer = UI.Text(l, 12, C.text, "body", "RIGHT")
    l.killer:SetPoint("RIGHT", l.icon, "LEFT", -5, 0)
    l:Hide()
    feed.lines[i] = l
end

H.FEED_SAMPLE = {
    { killer = "Aldric", killerClassId = 1, victim = "Brenna", victimClassId = 8, cause = "P" },
    { victim = "Corwin", victimClassId = 5, cause = "S" },
}

local function fillLine(l, k)
    local me = ns.PlayerName()
    l.killer:SetText(classText(k.killer, k.killerClassId))
    l.victim:SetText(classText(k.victim, k.victimClassId) .. (H.CAUSE_SUFFIX[k.cause] or ""))
    UI.SetGlyph(l.icon, H.CAUSE_GLYPH[k.cause] or "sword")
    l.icon:SetVertexColor(UI.Rgb(H.CAUSE_COLOR[k.cause] or C.goldLight))
    local w = 6 + l.victim:GetStringWidth() + 5 + 14 + 5 + (k.killer and (l.killer:GetStringWidth() + 8) or 4)
    l.bg:SetWidth(min(330, floor(w + 0.5)))
    local mine = me and (k.killer == me or k.victim == me)
    l.bg:SetVertexColor(UI.Rgb(mine and C.goldDark or "000000", mine and 0.6 or 0.45))
end

function H.UpdateFeed()
    if not H.feedPreview and (not R.Match() or #S.royaleFeed == 0) then
        if feed:IsShown() then
            feed:Hide()
        end
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
        return
    end
    for i, l in ipairs(feed.lines) do
        local k = list[i]
        if k then
            fillLine(l, k)
            local age = H.feedPreview and 0 or (now - (k.at or now))
            l:SetAlpha(U.Clamp(H.FEED_TIME - age, 0, 1))
            l:Show()
        else
            l:Hide()
        end
    end
    if not feed:IsShown() then
        feedPos.Anchor()
        feed:Show()
    end
end

------------------------------------------------------------------------------------------------------
-- Event banners: one at a time, at most one waiting per kind
------------------------------------------------------------------------------------------------------
local banner = CreateFrame("Frame", "BleakholdRoyaleBanner", UIParent)
banner:SetSize(660, 86)
banner:SetPoint("TOP", UIParent, "TOP", 0, -150)
banner:SetFrameStrata("HIGH")
banner:EnableMouse(false)
banner:Hide()
H.banner = banner
banner.kicker = UI.Text(banner, 16, C.text, "body", "CENTER")
banner.kicker:SetPoint("TOP", banner, "TOP", 0, 0)
UI.OneLine(banner.kicker, 640)
banner.title = UI.Text(banner, 32, C.purple, "title", "CENTER")
banner.title:SetPoint("TOP", banner.kicker, "BOTTOM", 0, -2)
UI.OneLine(banner.title, 660)

H.queue = {}
H.current = nil

-- e = { key, kicker (already safe for a FontString), title, color }; keys "e<kind>" are the match events'. A newer
-- banner of a kind already waiting takes its place.
function H.Banner(e)
    for i, q in ipairs(H.queue) do
        if q.key == e.key then
            H.queue[i] = e
            return
        end
    end
    H.queue[#H.queue + 1] = e
end

function H.UpdateBanner()
    local now = GetTime()
    local cur = H.current
    if cur and now - cur.shownAt >= H.BANNER_TIME then
        H.current = nil
        cur = nil
    end
    if not cur and #H.queue > 0 then
        cur = table.remove(H.queue, 1)
        cur.shownAt = now
        H.current = cur
        banner.kicker:SetText(cur.kicker or "")
        UI.SetText(banner.title, cur.title or "")
        UI.SetColor(banner.title, cur.color or C.purple)
    end
    if not cur then
        banner:Hide()
        return
    end
    local t = now - cur.shownAt
    banner:SetAlpha(U.Clamp(min(t / 0.15, (H.BANNER_TIME - t) / 0.3), 0, 1))
    banner:Show()
end

ns.On("ROYALE_EVENT", function(e)
    if e.kind == "N" and e.value > 0 then
        local title = e.value .. (e.value == 1 and " PLAYER LEFT" or " PLAYERS LEFT")
        H.Banner({ key = "eN", kicker = "", title = title, color = C.goldPale })
    elseif e.kind == "R" then
        local kicker = "The storm circle " .. (e.value > 0 and e.value or "") .. " is shown on the map"
        H.Banner({ key = "eR", kicker = kicker, title = "THE STORM CLOSES IN", color = C.purple })
    elseif e.kind == "S" then
        H.Banner({ key = "eS", kicker = "", title = "THE STORM IS MOVING", color = C.purple })
    elseif e.kind == "D" then
        local kicker = "Watch the sky: it lands in " .. clock((e.msLeft or 0) / 1000)
        H.Banner({ key = "eD", kicker = kicker, title = "SUPPLY DROP", color = C.goldLight })
    elseif e.kind == "W" and e.name then
        local kicker = U.Safe(e.name) .. " - " .. e.value .. (e.value == 1 and " elimination" or " eliminations")
        H.Banner({ key = "eW", kicker = kicker, title = "VICTORY", color = C.gold })
    end
end)

------------------------------------------------------------------------------------------------------
-- The parachute prompt
------------------------------------------------------------------------------------------------------
-- (not "BleakholdRoyaleDeploy": that global is the key binding's function, Royale.lua)
local dp = CreateFrame("Button", "BleakholdRoyaleParachute", UIParent)
dp:SetSize(300, 58)
dp:SetPoint("CENTER", UIParent, "CENTER", 0, -150)
dp:SetFrameStrata("HIGH")
UI.Backdrop(dp, C.panel, C.gold, 0.92)
dp:RegisterForClicks("LeftButtonUp")
dp:Hide()
H.deploy = dp
dp.title = UI.Text(dp, 18, C.goldPale, "title", "CENTER")
dp.title:SetPoint("TOP", dp, "TOP", 0, -10)
dp.title:SetText("OPEN PARACHUTE")
dp.key = UI.Text(dp, 12, C.mid, "body", "CENTER")
dp.key:SetPoint("TOP", dp.title, "BOTTOM", 0, -4)
dp:SetScript("OnClick", function()
    R.Deploy()
end)

function H.UpdateDeploy(m)
    if not m or m.me ~= R.ME.DROPPING or R.IsDeployed() then
        dp:Hide()
        return
    end
    local key = GetBindingKey and GetBindingKey("BLEAKHOLD_ROYALE_DEPLOY")
    UI.SetText(dp.key, key and ("Press " .. key .. " or click here") or "Click here (or bind a key: Bleakhold)")
    dp:Show()
end

------------------------------------------------------------------------------------------------------
-- The storm: the screen edge and the arrow to the safe zone on the minimap's edge
------------------------------------------------------------------------------------------------------
local vg = CreateFrame("Frame", "BleakholdRoyaleVignette", UIParent)
vg:SetAllPoints(UIParent)
vg:SetFrameStrata("BACKGROUND")
vg:SetFrameLevel(0)
vg:EnableMouse(false)
vg:Hide()
vg.tex = vg:CreateTexture(nil, "BACKGROUND")
vg.tex:SetTexture("Interface\\AddOns\\Bleakhold\\Art\\Royale\\Vignette")
vg.tex:SetAllPoints(vg)
vg.tex:SetVertexColor(UI.Rgb(C.purple))
H.vignette = vg

local ea = CreateFrame("Frame", "BleakholdRoyaleSafeArrow", UIParent)
ea:SetSize(28, 28)
ea:SetFrameStrata("MEDIUM")
ea:SetFrameLevel(12)
ea:EnableMouse(false)
ea:Hide()
ea.tex = ea:CreateTexture(nil, "OVERLAY")
ea.tex:SetTexture("Interface\\AddOns\\Bleakhold\\Art\\Royale\\Arrow")
ea.tex:SetAllPoints(ea)
ea.dist = UI.Text(ea, 11, C.text, "body", "CENTER")
ea.dist:SetPoint("TOP", ea, "BOTTOM", 0, 0)
H.edgeArrow = ea

-- Screen angle (radians from the right, counter-clockwise) of a world direction on the minimap.
function H.MinimapAngle(dx, dy)
    local bearing = atan2(dy, dx)           -- from north towards west (world X north, Y west)
    local rotate = GetCVar and GetCVar("rotateMinimap") == "1"
    local facing = rotate and R.Facing() or 0
    return pi / 2 + bearing - facing
end

function H.UpdateStorm(m)
    H.outside = false
    local fighting = m and m.me == R.ME.ALIVE and R.Fighting(m)
    local x, y = nil, nil
    if fighting then
        x, y = R.MyPos()
    end
    if not x then
        vg:Hide()
        ea:Hide()
        return
    end
    local cx, cy, cr = R.Circle(m)
    local out = R.OutsideBy(x, y, cx, cy, cr)
    H.outside = out ~= nil and out > 0
    if H.outside then
        vg:SetAlpha(0.55 + 0.15 * sin(GetTime() * 4))
        vg:Show()
    else
        vg:Hide()
    end
    -- the safe zone: the next circle once it is shown, else the current one
    local tx, ty, tr = cx, cy, cr
    if m.nextR then
        tx, ty, tr = m.nextX, m.nextY, m.nextR
    end
    local away = R.OutsideBy(x, y, tx, ty, tr)
    if not away or away <= 0 or not Minimap then
        ea:Hide()
        return
    end
    local a = H.MinimapAngle(tx - x, ty - y)
    local scale = (Minimap:GetEffectiveScale() or 1) / (ea:GetEffectiveScale() or 1)
    local radius = (Minimap:GetWidth() or 140) / 2 * scale - 10
    ea:ClearAllPoints()
    ea:SetPoint("CENTER", Minimap, "CENTER", cos(a) * radius, sin(a) * radius)
    ea.tex:SetRotation(a - pi / 2)
    ea.tex:SetVertexColor(UI.Rgb(H.outside and C.purple or "FFFFFF"))
    ea.dist:SetText(ceil(away) .. " yd")
    ea:Show()
end

------------------------------------------------------------------------------------------------------
-- The spectator bar
------------------------------------------------------------------------------------------------------
local sb = CreateFrame("Frame", "BleakholdRoyaleSpectate", UIParent)
sb:SetSize(500, 72)
sb:SetFrameStrata("MEDIUM")
UI.Backdrop(sb, "101216", C.chipBorder, 0.92)
sb:Hide()
H.spectate = sb
local sbPos = positioning(sb, "BOTTOM", 0, 150)

sb.label = UI.Text(sb, 10, C.purple)
sb.label:SetPoint("TOPLEFT", sb, "TOPLEFT", 12, -8)
sb.label:SetText("SPECTATING")
sb.name = UI.Text(sb, 15, C.goldPale)
sb.name:SetPoint("TOPLEFT", sb.label, "BOTTOMLEFT", 0, -2)
UI.OneLine(sb.name, 476)
local function sbButton(label, style, w, fn)
    local b = UI.Button(sb, w, 24, label, style, 12)
    b:SetScript("OnClick", fn)
    return b
end
sb.killer = sbButton("Killer", "dark", 76, function() R.Spectate(R.SPEC.KILLER) end)
sb.prev = sbButton("Prev", "dark", 70, function() R.Spectate(R.SPEC.PREVIOUS) end)
sb.next = sbButton("Next", "dark", 70, function() R.Spectate(R.SPEC.NEXT) end)
sb.requeue = sbButton("Queue again", "gold", 120, function() R.Join() end)
sb.leave = sbButton("Leave", "ghost", 80, function() R.LeaveMatch() end)
UI.Row({ sb.killer, sb.prev, sb.next, sb.requeue, sb.leave }, sb, "BOTTOMLEFT", "BOTTOMLEFT", 12, 9, 6)
sb.killer.tooltip = function() return { "Watch your killer", { "Or the first player alive.", C.mid } } end

H.SPECTATE_SAMPLE = { me = 3, watchName = "Aldric", phase = 3 }

function H.UpdateSpectator(m)
    m = m or (H.spectatePreview and H.SPECTATE_SAMPLE)
    if not m or (m.me ~= R.ME.SPECTATING and m.me ~= R.ME.LEFT) then
        sb:Hide()
        return
    end
    local watching = m.me == R.ME.SPECTATING and m.watchName
    if watching then
        local k = R.KillsOf(m.watchName)
        UI.SetText(sb.name, "Watching " .. m.watchName .. " (" .. k .. (k == 1 and " kill)" or " kills)"))
    else
        sb.name:SetText(m.phase >= R.PHASE.VICTORY and "The match is over" or "Nobody to watch")
    end
    local camera = m.me == R.ME.SPECTATING and m.phase < R.PHASE.ENDED
    sb.killer:SetActive(camera)
    sb.prev:SetActive(camera)
    sb.next:SetActive(camera)
    sb.requeue:SetActive(R.QueueBlock() == nil)
    if not sb:IsShown() then
        sbPos.Anchor()
        sb:Show()
    end
end

------------------------------------------------------------------------------------------------------
-- The end card (ROYE)
------------------------------------------------------------------------------------------------------
local ec = CreateFrame("Frame", "BleakholdRoyaleResult", UIParent)
ec:SetSize(380, 300)
ec:SetPoint("CENTER", UIParent, "CENTER", 0, 60)
ec:SetFrameStrata("HIGH")
ec:SetToplevel(true)
ec:EnableMouse(true)
UI.Backdrop(ec, C.panel, C.gold, 0.97)
ec:Hide()
H.result = ec
ec.top = UI.Solid(ec, C.purple, "BORDER")
ec.top:SetPoint("TOPLEFT", ec, "TOPLEFT", 1, -1)
ec.top:SetPoint("TOPRIGHT", ec, "TOPRIGHT", -1, -1)
ec.top:SetHeight(3)
ec.kicker = UI.Text(ec, 11, C.purple, "body", "CENTER")
ec.kicker:SetPoint("TOP", ec, "TOP", 0, -16)
ec.kicker:SetText(R.KICKER)
ec.place = UI.Text(ec, 30, C.goldPale, "title", "CENTER")
ec.place:SetPoint("TOP", ec.kicker, "BOTTOM", 0, -6)
UI.OneLine(ec.place, 356)
ec.winner = UI.Text(ec, 12, C.mid, "body", "CENTER")
ec.winner:SetPoint("TOP", ec.place, "BOTTOM", 0, -4)
UI.OneLine(ec.winner, 356)
ec.rows = {}
for i = 1, 4 do
    local l = UI.Text(ec, 13, C.mid)
    local v = UI.Text(ec, 13, C.text, "body", "RIGHT")
    ec.rows[i] = { label = l, value = v }
end
ec.rewardsLabel = UI.Text(ec, 11, C.dim)
ec.rewards = {}
for i = 1, 6 do
    local l = UI.Text(ec, 12, C.goldLight)
    UI.OneLine(l, 340)
    ec.rewards[i] = l
end
ec.keep = UI.Button(ec, 110, 26, "Keep watching", "dark", 12)
ec.requeue = UI.Button(ec, 110, 26, "Queue again", "gold", 12)
ec.leave = UI.Button(ec, 110, 26, "Leave", "ghost", 12)
UI.Row({ ec.keep, ec.requeue, ec.leave }, ec, "BOTTOMLEFT", "BOTTOMLEFT", 16, 14, 7)
ec.keep:SetScript("OnClick", function()
    H.resultDismissed = S.royaleResult and S.royaleResult.matchId
    ec:Hide()
end)
ec.requeue:SetScript("OnClick", function()
    R.Join()
end)
ec.leave:SetScript("OnClick", function()
    R.LeaveMatch()
end)

function H.ResultTitle(res)
    if res.placement == 1 then
        return "#1 VICTORY"
    end
    return "#" .. (res.placement or "?") .. (res.total and (" of " .. res.total) or "")
end

function H.ShowResult(res)
    res = res or S.royaleResult
    if not res then
        ec:Hide()
        return
    end
    ec.place:SetText(H.ResultTitle(res))
    UI.SetColor(ec.place, res.placement == 1 and C.gold or C.goldPale)
    if res.winnerName and res.placement ~= 1 then
        UI.SetText(ec.winner, "Winner: " .. res.winnerName .. (res.winnerKills and (" (" .. res.winnerKills ..
            (res.winnerKills == 1 and " elimination)" or " eliminations)")) or ""))
    else
        ec.winner:SetText(res.placement == 1 and "Last one standing" or "")
    end
    local stats = {
        { "Eliminations", tostring(res.kills or 0) },
        { "Damage to players", U.Commas(res.damage or 0) },
        { "Healing", U.Commas(res.healing or 0) },
        { "Time survived", U.Clock(res.survivedSec or 0) },
    }
    local y = -88
    for i, row in ipairs(ec.rows) do
        row.label:SetText(stats[i][1])
        row.value:SetText(stats[i][2])
        row.label:ClearAllPoints()
        row.label:SetPoint("TOPLEFT", ec, "TOPLEFT", 20, y)
        row.value:ClearAllPoints()
        row.value:SetPoint("TOPRIGHT", ec, "TOPRIGHT", -20, y)
        y = y - 20
    end
    y = y - 8
    ec.rewardsLabel:ClearAllPoints()
    ec.rewardsLabel:SetPoint("TOPLEFT", ec, "TOPLEFT", 20, y)
    ec.rewardsLabel:SetText(res.rewarded and "REWARDS" or "NO REWARDS")
    y = y - 18
    for i, l in ipairs(ec.rewards) do
        local rw = res.rewards[i]
        l:ClearAllPoints()
        if rw then
            UI.SetText(l, "+ " .. rw.line)
            l:SetPoint("TOPLEFT", ec, "TOPLEFT", 20, y)
            l:Show()
            y = y - 17
        elseif i == 1 and not res.rewarded then
            l:SetText("You left early or did not take part in the fight.")
            l:SetPoint("TOPLEFT", ec, "TOPLEFT", 20, y)
            l:Show()
            y = y - 17
        else
            l:Hide()
        end
    end
    local m = R.Match()
    ec.keep:SetLabel((m and m.me == R.ME.SPECTATING) and "Keep watching" or "Close")
    ec.requeue:SetActive(R.QueueBlock() == nil)
    ec:SetHeight(-y + 52)
    ec:Show()
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
-- The drop countdown in the centre (the last H.COUNTDOWN seconds of phase 1)
------------------------------------------------------------------------------------------------------
function H.UpdateCountdown(m)
    local CD = ns.Countdown
    if not CD then
        return
    end
    local g = CD.generic
    local left = m and m.phase == R.PHASE.COUNTDOWN and R.PhaseLeft(m)
    if left and left <= H.COUNTDOWN and left > 0.25 then
        local drift = g and g.matchId == m.matchId and abs((g.endsAt - GetTime()) - left) or 99
        if drift > 0.5 then
            CD.StartGeneric(H.KICKER, "The drop", left * 1000)
            if CD.generic then
                CD.generic.matchId = m.matchId
            end
        end
    elseif g and g.matchId then
        CD.StopGeneric()
    end
end

------------------------------------------------------------------------------------------------------
-- Wiring: one tick for everything (cheap without a match)
------------------------------------------------------------------------------------------------------
function H.Tick()
    local m = R.Match()
    H.UpdateStorm(m)
    H.UpdateBar(m)
    H.UpdateFeed()
    H.UpdateBanner()
    H.UpdateDeploy(m)
    H.UpdateSpectator(m)
    H.UpdateCountdown(m)
    -- back in the world: the card goes (its result stays on the Activities page)
    if ec:IsShown() and not S.royale then
        ec:Hide()
    end
end

ns.Every(0.1, H.Tick)

ns.On("ROYALE_MATCH", function()
    wipe(H.queue)
    H.current = nil
    H.resultDismissed = nil
    ec:Hide()
end)

ns.On("ROYALE_PHASE", function(m, before)
    if m.phase == R.PHASE.CANCELLED and before ~= R.PHASE.CANCELLED then
        ns.Toast.Push({ kicker = "BLEAKHOLD ROYALE", title = "Match cancelled",
            sub = "Too few players arrived: you are back at the front of the queue", target = "royale" })
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
-- Editor mode (ns.Movers): sample content while no match is on
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
mover("bleakhold_royale_bar", "Bleakhold Royale bar", bar, barPos, "preview")
mover("bleakhold_royale_feed", "Bleakhold Royale kill feed", feed, feedPos, "feedPreview")
mover("bleakhold_royale_spectate", "Bleakhold Royale spectator bar", sb, sbPos, "spectatePreview")
