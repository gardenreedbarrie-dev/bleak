-- Bleakhold: Bleakhold Royale (docs/BleakholdProtocol.md section 17), the core. Everything shown is server state
-- (QUEUE kind B, ROYS ROYM ROYO ROYK ROYV ROYE, parsed in State.lua); the client counts the timers down and sends
-- only the player's wishes: QJOIN B / QLEAVE / QREPLY (the queue and its ready check), RDROP (a landing pin),
-- RDEPLOY (the parachute) and RSPEC (the spectator camera). This file holds what the map (RoyaleMap.lua) and the HUD
-- (RoyaleHud.lua) share: the match helpers (storm circle now, the player's own position), the intents with their
-- client-side gates, the patch gate, and the queue side: the Royale page of Activities, the ready check popup, the
-- minimap orb, /bh royale and a scripted match for /bh demo.
--
-- Two gates before QJOIN goes out: HELLO feature bit 4096 (the realm runs the mode) and the map patch, tested with
-- Texture:SetTexture on a marker BLP that MapForge packs into patch-Q (a client without it cannot load map 901).
local ADDON, ns = ...
local U, UI, Comm, Data = ns.U, ns.UI, ns.Comm, ns.Data
local C = UI.C
local S = ns.S
local A = ns.Activities

local floor, ceil, max, min, sqrt = math.floor, math.ceil, math.max, math.min, math.sqrt

local R = {}
ns.Royale = R

R.MAP_ID = 901                    -- the island (MapForge bleakhold_royale.json); its picture is Art\Royale\Map
R.ACTIVITY = 901                  -- the mode id QJOIN B carries (the server's Bleakhold.Royale.ActivityId)
R.ROLES = 4                       -- ignored by the server for Royale; damage, like the Rift's default
R.MARKER = "Interface\\Bleakhold\\Royale\\Marker"      -- in patch-Q (MapForge archives.marker_texture)
R.MAP_TEX = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\Map"
R.THUMB_TEX = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\MapThumb"
R.MAP_FILE = "BleakholdRoyale"    -- the WorldMapArea row MapForge writes for the map (world_map_area.name)
R.WORLD_MAP_ASPECT = 1002 / 668   -- MapForge widens that row to the world map's frame (dbc/forge.py world_map_bounds)
R.PIN_LOCK = 3                    -- s before the drop when the pins lock (the server's PinLockSec)
R.STALE = 25                      -- s without a ROYS (the server sends one every 5 s) after which the match is over
R.POS_TOLERANCE = 40              -- yd the client's map position may be off the server's before it is dropped
R.PATCH_TEXT = "Install the latest client patch"
R.KICKER = "BLEAKHOLD ROYALE"
-- a little above the server's limits (section 8): RDROP and RSPEC 0.5 s, RDEPLOY 1 s, the queue 1 s
R.GAP = { QJOIN = 1.1, QLEAVE = 1.1, QREPLY = 1.1, RDROP = 0.55, RSPEC = 0.55, RDEPLOY = 1.05 }

R.PHASE = { ARRIVING = 0, COUNTDOWN = 1, DROP = 2, FIGHT = 3, OVERTIME = 4, VICTORY = 5, ENDED = 6, CANCELLED = 7 }
R.ME = { LOBBY = 0, DROPPING = 1, ALIVE = 2, SPECTATING = 3, LEFT = 4, WINNER = 5 }
R.SPEC = { KILLER = 0, NEXT = 1, PREVIOUS = 2 }
R.BUFFS = { [1] = "Speed", [2] = "Restoration", [3] = "Berserk" }

------------------------------------------------------------------------------------------------------
-- Gates
------------------------------------------------------------------------------------------------------
function R.Live()
    return Comm.HasFeature(Comm.FEATURE.ROYALE)
end

-- The map patch: SetTexture returns nil for a file the client cannot load (CSimpleTexture_Scripts.cpp). Tested once
-- (the patch needs a client restart anyway); R.HasPatch(true) tests again.
local probeFrame = CreateFrame("Frame", nil, UIParent)
probeFrame:Hide()
local probe = probeFrame:CreateTexture(nil, "BACKGROUND")

function R.HasPatch(recheck)
    if R.patch == nil or recheck then
        R.patch = probe:SetTexture(R.MARKER) and true or false
        probe:SetTexture(nil)
    end
    return R.patch
end

-- A refusal the client tells by itself: in the error frame, like the server's ERR sentences (Data.errorTexts).
local function notice(code, text)
    text = text or ns.ErrorText({ code = code })
    if text and UIErrorsFrame then
        UIErrorsFrame:AddMessage(text, 1, 0.45, 0.4)
    elseif text then
        ns.Print(text)
    end
end
R.Notice = notice

local function connected(quiet)
    if Comm.outdated then
        if not quiet then
            notice(nil, "Your Bleakhold addon is out of date.")
        end
        return false
    end
    if not Comm.ready and not Comm.demo then
        if not quiet then
            notice(nil, "Not connected to the realm.")
        end
        return false
    end
    return true
end

-- Why the player cannot queue from this client, or nil: not connected, the mode off, the patch missing.
function R.QueueBlock()
    if Comm.outdated then
        return "Your Bleakhold addon is out of date."
    end
    if not Comm.ready and not Comm.demo then
        return "Not connected to the realm."
    end
    if not R.Live() then
        return "Bleakhold Royale is not open on this realm."
    end
    if not R.HasPatch() then
        return R.PATCH_TEXT
    end
    return nil
end

------------------------------------------------------------------------------------------------------
-- The match
------------------------------------------------------------------------------------------------------
-- The match the player is in, or nil (none, left, or no ROYS for R.STALE seconds).
function R.Match()
    local m = S.royale
    if not m or GetTime() - (m.recvAt or 0) > R.STALE then
        return nil
    end
    return m
end

function R.InLobby(m)
    m = m or R.Match()
    return m ~= nil and m.phase <= R.PHASE.COUNTDOWN
end

-- The fight is on for this player: phase 3 or 4, or phase 2 once they are down from the drop. The server keeps phase
-- 2 until the last player has landed, so a player who landed early already fights with the storm timer, the stage
-- pips and the arrow to the safe zone; "The drop!" is for a player still falling (me 1, also a late drop in 3).
function R.Fighting(m)
    m = m or R.Match()
    if not m or m.me == R.ME.DROPPING or m.me == R.ME.LOBBY then
        return false
    end
    return m.phase == R.PHASE.FIGHT or m.phase == R.PHASE.OVERTIME or m.phase == R.PHASE.DROP
end

-- How many stages the storm has (ROYS `stages`; a server without the field has six) and whether it is in overtime
-- (phase 4, or the stage past the last one).
R.STAGES = 6
function R.StageCount(m)
    m = m or R.Match()
    return (m and m.stages) or R.STAGES
end

function R.Overtime(m)
    m = m or R.Match()
    return m ~= nil and (m.phase == R.PHASE.OVERTIME or (m.stage or 0) > R.StageCount(m))
end

-- Seconds until the next phase (nil when none is planned).
function R.PhaseLeft(m)
    m = m or R.Match()
    if not m or (m.phaseMsLeft or 0) <= 0 then
        return nil
    end
    return ns.RoyaleLeft(m.phaseMsLeft, m.recvAt)
end

-- Seconds until the pins lock (phase 1 only), else nil.
function R.PinsLockIn(m)
    m = m or R.Match()
    if not m or m.phase ~= R.PHASE.COUNTDOWN then
        return nil
    end
    local left = R.PhaseLeft(m)
    return left and max(0, left - R.PIN_LOCK) or nil
end

-- May the player set a landing pin now: in the lobby (phase 0, or 1 before the lock).
function R.CanPin(m)
    m = m or R.Match()
    if not m or m.me ~= R.ME.LOBBY then
        return false
    end
    if m.phase == R.PHASE.ARRIVING then
        return true
    end
    if m.phase == R.PHASE.COUNTDOWN then
        local lock = R.PinsLockIn(m)
        return lock == nil or lock > 0
    end
    return false
end

-- The storm circle now: cur until shrinkStartMs, then moving linearly to next until shrinkEndMs (both from the
-- moment the ROYS arrived), then next. Returns x, y, r, moving.
function R.Circle(m, now)
    m = m or S.royale
    if not m then
        return nil
    end
    local x, y, r = m.curX, m.curY, m.curR
    local e = m.shrinkEndMs
    if m.nextR and e and e > 0 then
        local t = ((now or GetTime()) - (m.recvAt or 0)) * 1000
        local s = m.shrinkStartMs or 0
        if t >= e then
            return m.nextX, m.nextY, m.nextR, false
        end
        if t > s and e > s then
            local k = (t - s) / (e - s)
            return x + (m.nextX - x) * k, y + (m.nextY - y) * k, r + (m.nextR - r) * k, true
        end
    end
    return x, y, r, false
end

-- What the storm does: "hold" (seconds until it moves) or "moving" (seconds until it stops); nil without a shrink.
function R.StormTimer(m)
    m = m or R.Match()
    if not m or not m.shrinkEndMs or m.shrinkEndMs <= 0 then
        return nil
    end
    local t = (GetTime() - (m.recvAt or 0)) * 1000
    local s = m.shrinkStartMs or 0
    if t < s then
        return "hold", (s - t) / 1000
    elseif t < m.shrinkEndMs then
        return "moving", (m.shrinkEndMs - t) / 1000
    end
    return nil
end

-- The WorldMapArea frame of the map (left, right, top, bottom: world Y, Y, X, X) from ROYM's picture frame, widened
-- like MapForge does it.
function R.WorldMapBounds(map)
    local left, right, top, bottom = map.maxY, map.minY, map.maxX, map.minX
    local w, h = left - right, top - bottom
    if h <= 0 or w <= 0 then
        return nil
    end
    if w / h < R.WORLD_MAP_ASPECT then
        local grow = (h * R.WORLD_MAP_ASPECT - w) / 2
        left, right = left + grow, right - grow
    else
        local grow = (w / R.WORLD_MAP_ASPECT - h) / 2
        top, bottom = top + grow, bottom - grow
    end
    return left, right, top, bottom
end

-- The player's world position from the client's own map (GetPlayerMapPosition on the Royale map's WorldMapArea), or
-- nil (another map is shown, no position, or it disagreed with the server's myX/myY: R.mapPosBad). The world map is
-- set to the current zone only while it is closed, and after three tries that do not reach the Royale map (a client
-- without the map's WorldMapArea row) the client stops trying for this match. One answer per frame time.
local posCache = { at = -1 }

local function clientPos()
    local map = S.royaleMap
    if not map or R.mapPosBad or map.mapId ~= R.MAP_ID or not GetPlayerMapPosition then
        return nil
    end
    local file = GetMapInfo and GetMapInfo()
    if file ~= R.MAP_FILE then
        if WorldMapFrame and WorldMapFrame:IsShown() then
            return nil        -- the player is looking at another map: leave it
        end
        if SetMapToCurrentZone then
            SetMapToCurrentZone()
        end
        file = GetMapInfo and GetMapInfo()
        if file ~= R.MAP_FILE then
            R.mapMisses = (R.mapMisses or 0) + 1
            if R.mapMisses >= 3 then
                R.mapPosBad = true
            end
            return nil
        end
    end
    R.mapMisses = 0
    local px, py = GetPlayerMapPosition("player")
    if type(px) ~= "number" or type(py) ~= "number" or (px == 0 and py == 0) then
        return nil
    end
    local left, right, top, bottom = R.WorldMapBounds(map)
    if not left then
        return nil
    end
    return top - py * (top - bottom), left - px * (left - right)
end

function R.ClientPos()
    if R.mapPosBad then
        return nil
    end
    local now = GetTime()
    if posCache.at ~= now then
        posCache.at = now
        posCache.x, posCache.y = clientPos()
    end
    return posCache.x, posCache.y
end

-- The player's position (world x, y) and whether the client found it itself; else the server's myX, myY.
function R.MyPos()
    local x, y = R.ClientPos()
    if x then
        return x, y, true
    end
    local m = R.Match()
    if m and m.myX then
        return m.myX, m.myY, false
    end
    return nil
end

-- The way the player faces in radians (0 north, counter-clockwise), or nil.
function R.Facing()
    local f = GetPlayerFacing and GetPlayerFacing()
    if type(f) == "number" and f == f then
        return f
    end
    return nil
end

-- Distance from (x, y) to the storm circle's edge: negative inside.
function R.OutsideBy(x, y, cx, cy, r)
    if not (x and cx) then
        return nil
    end
    local dx, dy = x - cx, y - cy
    return sqrt(dx * dx + dy * dy) - (r or 0)
end

-- The kills of a player of this match as the kill feed counted them (ROYK killerKills).
function R.KillsOf(name)
    return name and S.royaleKills[name] or 0
end

------------------------------------------------------------------------------------------------------
-- Intents (one gate per op, a little above the server's limits; ERR busy waits a full gap)
------------------------------------------------------------------------------------------------------
local nextAt = {}

local function send(op, ...)
    if not connected() then
        return false
    end
    local now = GetTime()
    if nextAt[op] and now < nextAt[op] then
        return false
    end
    local ok = Comm.Send(op, ...)
    if ok then
        nextAt[op] = now + (R.GAP[op] or 1)
    end
    return ok and true or false
end

ns.On("ERR", function(e)
    if e and R.GAP[e.op or ""] and e.code == "busy" then
        nextAt[e.op] = GetTime() + R.GAP[e.op]
    end
end)

local function royaleQueue()
    local q = S.queue
    return q and q.kind == "B" and q or nil
end
R.Queue = royaleQueue

function R.Join()
    local block = R.QueueBlock()
    if block then
        notice(nil, block)
        return false
    end
    return send("QJOIN", "B", R.ACTIVITY, 0, R.ROLES, 1)
end

function R.Leave()
    return send("QLEAVE")
end

function R.Reply(accept)
    local q = royaleQueue()
    if not q or q.state ~= 2 or not q.proposalId then
        return false
    end
    local ok = send("QREPLY", q.proposalId, accept and 1 or 0)
    if ok then
        R.answered = { id = q.proposalId, accept = accept and true or false }
        ns.Fire("ROYALE_READY_ANSWERED", R.answered)
    end
    return ok
end

-- The landing pin: the newest wish goes out as soon as the RDROP gate opens (clicks in between replace it); the
-- same pin is never sent twice within the server's duplicate window. The map shows R.pendingPin until the server's
-- ROYS brings the snapped pin.
local pinTimer

local function flushPin()
    pinTimer = nil
    local want = R.wantPin
    if not want then
        return
    end
    local m = R.Match()
    if not R.CanPin(m) or m.matchId ~= want.matchId then
        R.wantPin = nil
        R.pendingPin = nil
        return
    end
    local now = GetTime()
    local wait = (nextAt.RDROP or 0) - now
    if wait > 0 then
        pinTimer = ns.After(wait + 0.01, flushPin)
        return
    end
    R.wantPin = nil
    local last = R.sentPin
    if last and last.x == want.x and last.y == want.y and now - last.at < 1.1 then
        return
    end
    if send("RDROP", want.x, want.y) then
        R.sentPin = { x = want.x, y = want.y, at = now }
    end
end

function R.SetPin(x, y)
    if not connected() then
        return false
    end
    local m = R.Match()
    if not R.CanPin(m) then
        notice("royale_phase")
        return false
    end
    x = U.Clamp(floor(x + 0.5), -17067, 17067)
    y = U.Clamp(floor(y + 0.5), -17067, 17067)
    if x == 0 then x = 0 end   -- never "-0"
    if y == 0 then y = 0 end
    R.wantPin = { x = x, y = y, matchId = m.matchId }
    R.pendingPin = { x = x, y = y, matchId = m.matchId, at = GetTime() }
    if not pinTimer then
        flushPin()
    end
    ns.Fire("ROYALE_PIN", x, y)
    return true
end

-- The parachute: only while falling from the drop, once, 0.5 s into the fall (else the server drops it anyway).
function R.Deploy()
    local m = R.Match()
    if not m or m.me ~= R.ME.DROPPING or R.deployed or not R.dropAt or GetTime() - R.dropAt < 0.5 then
        return false
    end
    if send("RDEPLOY") then
        R.deployed = true
        ns.Fire("ROYALE_DEPLOYED")
        return true
    end
    return false
end

-- Whether the parachute is open: sent, the Slow Fall aura on the player, or past the server's 2.5 s auto-deploy.
function R.IsDeployed()
    if R.deployed then
        return true
    end
    if R.dropAt and GetTime() - R.dropAt > 3 then
        return true
    end
    local name = GetSpellInfo and GetSpellInfo(130)
    return name ~= nil and UnitBuff ~= nil and UnitBuff("player", name) ~= nil
end

function R.Spectate(dir)
    local m = R.Match()
    if not m or m.me ~= R.ME.SPECTATING then
        notice("royale_phase")
        return false
    end
    return send("RSPEC", dir)
end

-- Leave the battleground. Alive players forfeit (and get Deserter): they confirm first.
function R.LeaveMatch()
    local m = R.Match()
    local function go()
        if LeaveBattlefield then
            LeaveBattlefield()
        end
    end
    if m and (m.me == R.ME.LOBBY or m.me == R.ME.DROPPING or m.me == R.ME.ALIVE) and m.phase < R.PHASE.VICTORY then
        UI.Confirm("Leave the match? You forfeit it and become a deserter.", go, "Leave")
    else
        go()
    end
end

-- Key binding entry point (Bindings.xml).
function BleakholdRoyaleDeploy()
    R.Deploy()
end

------------------------------------------------------------------------------------------------------
-- Match bookkeeping: the drop, the client's own position check, leaving the map
------------------------------------------------------------------------------------------------------
ns.On("ROYALE_MATCH", function(m)
    R.deployed, R.dropAt, R.mapPosBad, R.posMisses, R.mapMisses = nil, nil, nil, 0, 0
    posCache.at = -1
    R.wantPin, R.pendingPin, R.sentPin = nil, nil, nil
end)

ns.On("ROYALE_ME", function(m)
    if m.me == R.ME.DROPPING then
        R.dropAt = GetTime()
        R.deployed = nil
    end
end)

ns.On("STATE", function(topic)
    local m = S.royale
    if topic ~= "ROYS" or not m then
        return
    end
    -- the snapped pin is here: the pending one is done
    if R.pendingPin and R.sentPin and m.recvAt > R.sentPin.at then
        R.pendingPin = nil
    end
    -- the client's own map position must agree with the server's (another WorldMapArea, a fallback map)
    if m.myX and not R.mapPosBad then
        posCache.at = -1
        local x, y = R.ClientPos()
        if x then
            local d = R.OutsideBy(x, y, m.myX, m.myY, 0)
            if d > R.POS_TOLERANCE then
                R.posMisses = (R.posMisses or 0) + 1
                if R.posMisses >= 2 then
                    R.mapPosBad = true
                end
            else
                R.posMisses = 0
            end
        end
    end
end)

local function inBattleground()
    local inside, kind = IsInInstance()
    return inside and kind == "pvp"
end
R.InBattleground = inBattleground

-- Back in the world: the match is over for this client (its result stays for the Activities card).
function R.ForgetMatch()
    if S.royale or S.royaleMap then
        S.royale, S.royaleMap, S.royaleObjects, S.royaleEvent = nil, nil, nil, nil
        S.royaleFeed, S.royaleKills = {}, {}
        ns.Fire("STATE", "ROYS")
    end
end

ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    if not inBattleground() and not Comm.demo then
        R.ForgetMatch()
    end
end)

-- After a /reload in a match: ask for the match once HELLO is answered (nothing comes back outside a match).
ns.On("HELLO", function()
    if R.Live() and inBattleground() then
        Comm.Get("ROYS")
        Comm.Get("ROYM")
    end
    ns.Orbs.Refresh()
    if R.page and R.page:IsVisible() then
        R.page:Refresh()
    end
end)

------------------------------------------------------------------------------------------------------
-- The ready check popup (QUEUE kind B state 2): a draining ring, Accept and Decline
------------------------------------------------------------------------------------------------------
local rc = CreateFrame("Frame", "BleakholdRoyaleReady", UIParent)
rc:SetSize(340, 196)
rc:SetPoint("TOP", UIParent, "TOP", 0, -170)
rc:SetFrameStrata("DIALOG")
rc:SetToplevel(true)
rc:EnableMouse(true)
UI.Backdrop(rc, C.panel, C.purple, 0.97)
rc:Hide()
R.ready = rc

rc.top = UI.Solid(rc, C.purple, "BORDER")
rc.top:SetPoint("TOPLEFT", rc, "TOPLEFT", 1, -1)
rc.top:SetPoint("TOPRIGHT", rc, "TOPRIGHT", -1, -1)
rc.top:SetHeight(3)
rc.kicker = UI.Text(rc, 11, C.purple, "body", "CENTER")
rc.kicker:SetPoint("TOP", rc, "TOP", 0, -14)
rc.kicker:SetText(R.KICKER)
rc.title = UI.Text(rc, 20, C.goldPale, "title", "CENTER")
rc.title:SetPoint("TOP", rc.kicker, "BOTTOM", 0, -6)
rc.title:SetText("Your match is ready")
rc.ring = UI.Ring(rc, 58, 5)
rc.ring:SetPoint("TOP", rc.title, "BOTTOM", 0, -10)
rc.count = UI.Text(rc, 12, C.mid, "body", "CENTER")
rc.count:SetPoint("TOP", rc.ring, "BOTTOM", 0, -6)
rc.accept = UI.Button(rc, 140, 30, "Accept", "teal", 13)
rc.accept:SetPoint("BOTTOMRIGHT", rc, "BOTTOM", -6, 14)
rc.decline = UI.Button(rc, 140, 30, "Decline", "dark", 13)
rc.decline:SetPoint("BOTTOMLEFT", rc, "BOTTOM", 6, 14)
rc.waiting = UI.Text(rc, 13, C.teal, "body", "CENTER")
rc.waiting:SetPoint("BOTTOM", rc, "BOTTOM", 0, 22)
rc.waiting:Hide()

rc.accept:SetScript("OnClick", function()
    R.Reply(true)
end)
rc.decline:SetScript("OnClick", function()
    if R.Reply(false) then
        rc:Hide()
    end
end)

function R.ReadyLeft(q)
    q = q or royaleQueue()
    if not q or not q.timeoutSec then
        return nil
    end
    return max(0, q.timeoutSec - (GetTime() - (q.recvAt or GetTime())))
end

function R.UpdateReady()
    local q = royaleQueue()
    if not q or q.state ~= 2 or not q.proposalId then
        rc:Hide()
        return
    end
    local left = R.ReadyLeft(q)
    if left and left <= 0 then
        rc:Hide()             -- no answer in time counts as a decline on the server
        return
    end
    local total = q.timeoutSec and q.timeoutSec > 0 and q.timeoutSec or 15
    rc.ring:SetProgress((left or total) / total, C.purple, C.track)
    rc.ring.label:SetText(left and tostring(ceil(left)) or "")
    if q.accepted and q.proposalSize then
        rc.count:SetText(q.accepted .. " / " .. q.proposalSize .. " accepted")
    else
        rc.count:SetText("")
    end
    local answered = R.answered and R.answered.id == q.proposalId and R.answered.accept
    if answered then
        rc.accept:Hide()
        rc.decline:Hide()
        rc.waiting:SetText("Accepted - waiting for the others")
        rc.waiting:Show()
    else
        rc.accept:Show()
        rc.decline:Show()
        rc.waiting:Hide()
    end
end

local rcAcc = 0
rc:SetScript("OnUpdate", function(self, elapsed)
    rcAcc = rcAcc + (elapsed or 0)
    if rcAcc >= 0.2 then
        rcAcc = 0
        R.UpdateReady()
    end
end)

-- A new Royale proposal opens the popup (with the queue pop sound); any QUEUE redraws or closes it.
ns.On("STATE", function(topic)
    if topic ~= "QUEUE" then
        return
    end
    local q = royaleQueue()
    if q and q.state == 2 and q.proposalId and q.proposalId ~= R.shownProposal then
        R.shownProposal = q.proposalId
        R.answered = nil
        rc:Show()
        if PlaySound then
            PlaySound("PVPTHROUGHQUEUE")
        end
    end
    if rc:IsShown() then
        R.UpdateReady()
    end
end)

------------------------------------------------------------------------------------------------------
-- Activities: the Royale page (the mode's card, the last match). The kill announcer's settings are on the Tasks page
-- (Activities.lua): the announcer plays in every battleground, Royale or not.
------------------------------------------------------------------------------------------------------
local P = A.NewPage()
A.AddPage("royale", P)
R.page = P

local HERO_H = 268
local THUMB = 236
local TEXT_X = THUMB + 34
local TEXT_W = A.PW - TEXT_X - 18

local hero = UI.Box(P, A.PW, HERO_H, C.eraBg, C.eraBorder)
hero:SetPoint("TOPLEFT", P, "TOPLEFT", 0, 0)
P.hero = hero
hero.thumbFrame = UI.Box(hero, THUMB, THUMB, C.bg, C.eraBorder)
hero.thumbFrame:SetPoint("TOPLEFT", hero, "TOPLEFT", 16, -16)
hero.thumb = hero.thumbFrame:CreateTexture(nil, "ARTWORK")
hero.thumb:SetPoint("TOPLEFT", hero.thumbFrame, "TOPLEFT", 1, -1)
hero.thumb:SetPoint("BOTTOMRIGHT", hero.thumbFrame, "BOTTOMRIGHT", -1, 1)
hero.thumb:SetTexture(R.THUMB_TEX)
hero.kicker = UI.Text(hero, 11, C.purple)
hero.kicker:SetPoint("TOPLEFT", hero, "TOPLEFT", TEXT_X, -22)
hero.kicker:SetText(R.KICKER)
hero.title = UI.Text(hero, 26, C.goldPale, "title")
hero.title:SetPoint("TOPLEFT", hero.kicker, "BOTTOMLEFT", 0, -4)
hero.title:SetText("Last one standing")
hero.facts = UI.Text(hero, 13, C.goldLight)
hero.facts:SetPoint("TOPLEFT", hero.title, "BOTTOMLEFT", 0, -6)
hero.facts:SetText("Solo · Level 80 · 20-40 players")
hero.text = UI.Text(hero, 12, C.mid)
hero.text:SetPoint("TOPLEFT", hero.facts, "BOTTOMLEFT", 0, -10)
hero.text:SetWidth(TEXT_W)
hero.text:SetJustifyV("TOP")
hero.text:SetHeight(48)
hero.text:SetText("Drop onto the island with up to 39 others, loot crates and orbs and outlast the storm. One life: "
    .. "the last player standing wins. Your own gear counts; the island's loot is yours for the match.")
hero.status = UI.Text(hero, 15, C.text)
hero.status:SetPoint("TOPLEFT", hero.text, "BOTTOMLEFT", 0, -10)
UI.OneLine(hero.status, TEXT_W)
hero.detail = UI.Text(hero, 12, C.dim)
hero.detail:SetPoint("TOPLEFT", hero.status, "BOTTOMLEFT", 0, -4)
UI.OneLine(hero.detail, TEXT_W)
hero.join = UI.Button(hero, 200, 36, "Queue", "gold", 14)
hero.join:SetPoint("BOTTOMLEFT", hero, "BOTTOMLEFT", TEXT_X, 18)
hero.notice = UI.Text(hero, 12, C.red)
hero.notice:SetPoint("LEFT", hero.join, "RIGHT", 14, 0)
UI.OneLine(hero.notice, TEXT_W - 214)
P.join = hero.join

hero.join:SetScript("OnClick", function()
    local q = royaleQueue()
    if q and (q.state == 1 or q.state == 2) then
        R.Leave()
    else
        R.Join()
    end
end)

local CARD_W = floor((A.PW - 12) / 2)
local CARD_H = A.PH - HERO_H - 12

local how = UI.Box(P, CARD_W, CARD_H, C.card, C.border)
how:SetPoint("TOPLEFT", hero, "BOTTOMLEFT", 0, -12)
how.label = UI.Text(how, 11, C.dim)
how.label:SetPoint("TOPLEFT", how, "TOPLEFT", 12, -12)
how.label:SetText("HOW IT WORKS")
how.lines = {}
local HOW = {
    "Queue alone. At 20 players a ready check goes out; answer it within 15 seconds.",
    "Brawl on The Overlook while the others arrive, and click the island map to set your landing pin.",
    "Drop from high above your pin; your parachute opens by itself (or bind a key to open it).",
    "Loot crates, orbs and supply drops, and stay inside the storm circle: it closes in stages.",
    "Eliminated players watch the rest, queue again or leave. Honor and Shards by placement.",
}
for i, line in ipairs(HOW) do
    local num = UI.Text(how, 13, C.purple, "title")
    num:SetPoint("TOPLEFT", how, "TOPLEFT", 12, -34 - (i - 1) * 38)
    num:SetText(tostring(i))
    local t = UI.Text(how, 12, C.mid)
    t:SetPoint("TOPLEFT", how, "TOPLEFT", 32, -34 - (i - 1) * 38)
    t:SetWidth(CARD_W - 44)
    t:SetJustifyV("TOP")
    t:SetHeight(34)
    t:SetText(line)
    how.lines[i] = t
end
P.how = how

local last = UI.Box(P, CARD_W, CARD_H, C.card, C.border)
last:SetPoint("TOPRIGHT", hero, "BOTTOMRIGHT", 0, -12)
last.label = UI.Text(last, 11, C.dim)
last.label:SetPoint("TOPLEFT", last, "TOPLEFT", 12, -12)
last.label:SetText("YOUR LAST MATCH")
last.place = UI.Text(last, 22, C.goldPale, "title")
last.place:SetPoint("TOPLEFT", last.label, "BOTTOMLEFT", 0, -6)
UI.OneLine(last.place, CARD_W - 24)
last.lines = {}
for i = 1, 4 do
    local l = UI.Text(last, 12, i == 1 and C.text or C.mid)
    l:SetPoint("TOPLEFT", last, "TOPLEFT", 12, -64 - (i - 1) * 18)
    UI.OneLine(l, CARD_W - 24)
    last.lines[i] = l
end
P.last = last

local QUEUE_STATUS = { [1] = "In the queue", [2] = "Match found - answer the ready check", [3] = "In a match" }

-- "#1 Victory" or "#7 of 32".
function R.PlaceText(placement, total)
    if placement == 1 then
        return "#1 Victory"
    end
    return "#" .. placement .. (total and (" of " .. total) or "")
end

function P:Tick()
    local q = royaleQueue()
    if not q then
        return
    end
    local since = GetTime() - (q.recvAt or GetTime())
    if q.state == 1 then
        local txt = "Waiting " .. U.Clock((q.queuedSec or 0) + since)
        if q.matchesRunning and q.matchesRunning > 0 then
            txt = txt .. "  -  " .. q.matchesRunning .. (q.matchesRunning == 1 and " match" or " matches") .. " running"
        end
        hero.detail:SetText(txt)
    elseif q.state == 2 then
        local left = R.ReadyLeft(q)
        hero.detail:SetText(left and ("Answer within " .. ceil(left) .. " s") or "")
    end
end

function P:Refresh()
    local q = royaleQueue()
    local st = q and q.state or 0
    local block = R.QueueBlock()
    if st == 1 or st == 2 then
        local n = q.queued and q.minPlayers and (q.queued .. " / " .. q.minPlayers .. " queued") or QUEUE_STATUS[st]
        hero.status:SetText(st == 2 and QUEUE_STATUS[2] or n)
        UI.SetColor(hero.status, st == 2 and C.teal or C.goldLight)
        hero.join:SetLabel("Leave queue")
        hero.join:SetStyle("dark")
        hero.join:SetActive(true)
    elseif st == 3 or R.Match() then
        hero.status:SetText(QUEUE_STATUS[3])
        UI.SetColor(hero.status, C.teal)
        hero.detail:SetText("")
        local m = R.Match()
        local spectator = m and (m.me == R.ME.SPECTATING or m.me == R.ME.LEFT)
        hero.join:SetLabel(spectator and "Queue again" or "In a match")
        hero.join:SetStyle("gold")
        hero.join:SetActive(spectator and not block)
    else
        local status = "Not queued"
        if q and q.queued and q.minPlayers then
            status = q.queued .. " / " .. q.minPlayers .. " queued"
        end
        hero.status:SetText(status)
        UI.SetColor(hero.status, C.text)
        hero.detail:SetText("")
        hero.join:SetLabel("Queue")
        hero.join:SetStyle("gold")
        hero.join:SetActive(block == nil)
    end
    UI.SetText(hero.notice, block or "")
    P:Tick()
    -- the last match (this session, or the one saved for this character)
    local res = S.royaleResult
    local saved = ns.cdb.royaleLast
    for _, l in ipairs(last.lines) do
        l:SetText("")
    end
    if res and res.placement then
        last.place:SetText(R.PlaceText(res.placement, res.total))
        local kills = res.kills .. (res.kills == 1 and " elimination" or " eliminations")
        local lines = { kills .. "  -  survived " .. U.Clock(res.survivedSec) }
        for _, rw in ipairs(res.rewards) do
            if #lines < #last.lines then
                lines[#lines + 1] = "+ " .. rw.line
            end
        end
        for i, l in ipairs(last.lines) do
            if lines[i] then
                UI.SetText(l, lines[i])
            end
        end
    elseif type(saved) == "table" and type(saved.placement) == "number" then
        last.place:SetText(R.PlaceText(saved.placement, type(saved.total) == "number" and saved.total or nil))
        if type(saved.kills) == "number" then
            last.lines[1]:SetText(saved.kills .. (saved.kills == 1 and " elimination" or " eliminations"))
        end
    else
        last.place:SetText("No match yet")
    end
end

function P:OnOpen()
    Comm.Get("QUEUE")
end

P:SetScript("OnUpdate", function(self, elapsed)
    self.acc = (self.acc or 0) + (elapsed or 0)
    if self.acc >= 0.5 then
        self.acc = 0
        P:Tick()
    end
end)

ns.On("STATE", function(topic)
    if (topic == "QUEUE" or topic == "ROYS" or topic == "ROYE") and P:IsVisible() then
        P:Refresh()
    end
end)

-- The last result, kept per character for the card after a relog.
ns.On("ROYALE_RESULT", function(res)
    ns.cdb.royaleLast = { placement = res.placement, total = res.total, kills = res.kills, matchId = res.matchId }
end)

------------------------------------------------------------------------------------------------------
-- Opening: /bh royale, the TOAST target `royale`, the minimap orb
------------------------------------------------------------------------------------------------------
local function openPage(toggle)
    if toggle and A.frame:IsShown() and A.current == "royale" then
        A.frame:Hide()
        return
    end
    A.Show("royale")
end
UI.RegisterOpener("royale", openPage)

local function orbLines()
    local lines = { "Bleakhold Royale" }
    local q = royaleQueue()
    local m = R.Match()
    if m then
        lines[#lines + 1] = { "In a match: " .. (m.alive or 0) .. " alive", C.teal }
        lines[#lines + 1] = { "Click for the island map", C.mute }
        return lines
    end
    if q and q.state == 1 then
        local count = (q.queued and q.minPlayers) and (": " .. q.queued .. " / " .. q.minPlayers) or ""
        lines[#lines + 1] = { "In the queue" .. count, C.goldLight }
    elseif q and q.state == 2 then
        lines[#lines + 1] = { "Match found - answer the ready check", C.teal }
    end
    lines[#lines + 1] = { "Solo free-for-all, level 80", C.mid }
    lines[#lines + 1] = { "Click to open", C.mute }
    return lines
end

R.orb = ns.Orbs.Add({
    key = "royale", glyph = "sword", title = "Bleakhold Royale", angle = 115,
    available = R.Live,
    onClick = function()
        if R.Match() and S.royaleMap then
            UI.Open("royalemap", true)
        else
            openPage(true)
        end
    end,
    lines = orbLines,
    update = function(b)
        local q = royaleQueue()
        if q and (q.state == 1 or q.state == 2) then
            b.pulse = (b.pulse or 0) + 0.25
            b.ring:SetAlpha(0.55 + 0.45 * math.abs(math.sin(b.pulse * 2)))
        else
            b.ring:SetAlpha(1)
        end
    end,
})

ns.AddCommand("royale", "Bleakhold Royale: /bh royale [map|leave|voice off|male|female|quiet|normal]", function(args)
    local a, b = (args or ""):lower():match("^(%S*)%s*(%S*)")
    if a == "map" then
        UI.Open("royalemap", true)
    elseif a == "leave" then
        R.LeaveMatch()
    elseif a == "voice" and (b == "off" or b == "male" or b == "female") then
        ns.Announcer.SetVoice(b)   -- the kill announcer of every battleground (/bh announcer)
        ns.Print(ns.Announcer.Describe())
    elseif a == "quiet" or a == "normal" then
        ns.Announcer.SetQuiet(a == "quiet")
        ns.Print(ns.Announcer.Describe())
    else
        openPage(false)
    end
end)

------------------------------------------------------------------------------------------------------
-- /bh demo: a short scripted match (Demo.lua routes QJOIN B, QREPLY, QLEAVE, RDROP, RSPEC and GET ROYS/ROYM here)
------------------------------------------------------------------------------------------------------
local DEMO_MATCH = 7001
local DEMO_PLACES = {
    { 1, "L", -266, -266, 88, "The Bleak Hold" }, { 2, "L", 120, 80, 62, "Harrow Farm" },
    { 3, "L", 180, -760, 54, "Blackvein Pit" }, { 4, "L", -620, -600, 40, "Gloomtimber Mill" },
    { 5, "L", -700, 60, 26, "The Pale Shrine" }, { 6, "L", 220, -250, 60, "Broken Siege" },
    { 7, "L", 60, -420, 60, "Crow's Rise" }, { 8, "L", -80, -120, 60, "Wrecked Caravan" },
    { 9, "L", -520, -260, 70, "Mirefen Hollow" }, { 10, "L", -480, 170, 60, "Forgotten Graves" },
    { 11, "C", -80, -710, 16, "Old Ford" }, { 12, "C", -560, -700, 18, "Covered Bridge" },
    { 13, "C", 150, -665, 0, "Pit Bridge" }, { 14, "Y", 455, 455, 32, "The Overlook" },
}
local demo

local function demoAfter(sec, fn)
    local run = demo and demo.run
    ns.After(sec, function()
        if Comm.demo and demo and demo.run == run then
            fn()
        end
    end)
end

local function demoPush(op, records)
    if ns.Demo then
        ns.Demo.Push(op, records)
    end
end

local function demoQueue(state, extra)
    demo.rev = demo.rev + 100
    local r = { demo.rev, state, "B", R.ACTIVITY, 0, 1, demo.queuedSec or 0, "", "", "", 80, 80, 13, 20, 40, "", "", 1 }
    for k, v in pairs(extra or {}) do
        r[k] = v
    end
    demoPush("QUEUE", { r })
end

local function demoState()
    local s = demo.st
    demoPush("ROYS", { { DEMO_MATCH, s.phase, s.ms or 0, s.alive, 24, s.me, s.kills or 0, s.placement or "",
        s.pinX or "", s.pinY or "", s.stage or 0, s.curX, s.curY, s.curR, s.nextX or "", s.nextY or "", s.nextR or "",
        s.start or "", s.stop or "", s.dmg or 0, s.watch or "", s.myX or "", s.myY or "", 6 } })
end

local function demoMap()
    local recs = { { R.MAP_ID, -1066, 533, -1066, 533, 455, 455, 32, 750, -267, -267 } }
    for _, p in ipairs(DEMO_PLACES) do
        recs[#recs + 1] = p
    end
    demoPush("ROYM", recs)
end

local function demoObjects()
    demoPush("ROYO", { { DEMO_MATCH, 1 }, { 1, "S", 0, -266, -266, 0, 30000 }, { 2, "S", 0, -712, 48, 0, 30000 },
        { 3, "B", 1, 120, 80, 1, "" }, { 4, "B", 2, -640, -576, 1, "" }, { 5, "B", 3, 180, -760, 1, "" },
        { 6, "B", 3, 220, -250, 2, 45000 }, { 7, "B", 1, 60, -420, 1, "" }, { 8, "B", 2, -520, -260, 1, "" } })
end

-- A kill feed line, and the kill announcer's BGANN when it carries a multi-kill or streak code (section 18).
local function demoKill(killer, kc, victim, vc, cause, kills, multi, streak)
    demo.st.alive = demo.st.alive - 1
    demoPush("ROYK", { { killer or "", killer and kc or "", victim, vc, cause, demo.st.alive, killer and kills or "" } })
    if killer and (multi or streak) then
        demoPush("BGANN", { { killer, kc, victim, vc, multi or "", streak or "" } })
    end
end

local function demoMatch()
    local st = { phase = 0, ms = 6000, alive = 24, me = 0, curX = -267, curY = -267, curR = 1080, myX = 452, myY = 450 }
    demo.st = st
    demoMap()
    demoState()
    demoAfter(6, function()
        st.phase, st.ms = 1, 20000
        demoState()
    end)
    demoAfter(11, function()
        st.stage, st.nextX, st.nextY, st.nextR = 1, -150, -310, 520
        demoPush("ROYV", { { "R", 1, -150, -310, "", "" } })
        st.ms = 15000
        demoState()
    end)
    demoAfter(26, function()
        st.phase, st.ms, st.me = 2, 6000, 1
        st.myX, st.myY = st.pinX or -80, st.pinY or -120
        demoState()
    end)
    demoAfter(32, function()
        st.phase, st.ms, st.me, st.start, st.stop, st.dmg = 3, 0, 2, 20000, 50000, 10
        demoState()
        demoObjects()
        demoKill("Aldric Stormwind", 1, "Brenna", 8, "P", 1, nil, "F")
    end)
    demoAfter(36, function()
        demoKill("Aldric Stormwind", 1, "Corwin", 5, "P", 2, "D", nil)
        demoPush("ROYV", { { "D", 0, -80, -180, 20000, "" } })
        demoPush("ROYO", { { DEMO_MATCH, 0 }, { 20, "D", 0, -80, -180, 3, 20000 } })
    end)
    demoAfter(39, function()
        demoKill(nil, nil, "Eamon", 11, "S", nil)
        demoKill("Dalia", 11, "Fenna", 3, "P", 1)
    end)
    demoAfter(52, function()
        st.curX, st.curY, st.curR, st.start, st.stop = -150, -310, 520, "", ""
        st.alive = 10
        demoPush("ROYV", { { "N", 10, "", "", "", "" } })
        demoPush("ROYO", { { DEMO_MATCH, 0 }, { 20, "D", 0, -80, -180, 1, "" } })
        demoState()
    end)
    demoAfter(58, function()
        demoKill("Aldric Stormwind", 1, ns.PlayerName() or "You", 1, "P", 3, nil, "S")
        demoPush("ROYE", { { DEMO_MATCH, 9, 24, demo.kills or 0, 9400, 0, 26, "", "", "", 1 },
            { "H", 120, "", "Placement" }, { "S", 12, "", "Placement" } })
        st.me, st.placement, st.watch, st.myX, st.myY = 3, 9, "Aldric Stormwind", nil, nil
        demoState()
    end)
    demoAfter(72, function()
        st.alive = 1
        demoKill("Dalia", 11, "Aldric Stormwind", 1, "P", 7, nil, "W")
        demoPush("ROYV", { { "W", 7, "", "", "", "Dalia" } })
        st.phase, st.ms, st.watch = 5, 12000, "Dalia"
        demoState()
        demoPush("ROYE", { { DEMO_MATCH, 9, 24, demo.kills or 0, 9400, 0, 26, "Dalia", 11, 7, 1 },
            { "H", 120, "", "Placement" }, { "S", 12, "", "Placement" } })
    end)
    demoAfter(84, function()
        st.phase, st.ms = 6, 120000
        demoState()
    end)
end

-- Returns true when the intent was the demo's (and is answered here).
function R.DemoRespond(op, recs)
    local f = recs[1] or {}
    if op == "QJOIN" and f[1] == "B" then
        demo = { run = (demo and demo.run or 0) + 1, rev = (demo and demo.rev or 0), queuedSec = 0 }
        demoQueue(1)
        demoAfter(3, function()
            demoQueue(2, { [7] = 3, [9] = 412, [10] = 15, [13] = 24, [16] = 3, [17] = 24 })
        end)
        return true
    end
    if not demo then
        return false
    end
    if op == "QREPLY" and f[1] == "412" then
        if f[2] == "1" then
            demoQueue(3, { [13] = "", [18] = 2 })
            demoAfter(1, demoMatch)
        else
            demoQueue(0)
            demo = nil
        end
        return true
    elseif op == "QLEAVE" then
        demoQueue(0)
        demo = nil
        return true
    elseif op == "RDROP" and demo.st then
        demo.st.pinX, demo.st.pinY = tonumber(f[1]), tonumber(f[2])
        demoState()
        return true
    elseif op == "RSPEC" and demo.st then
        demo.st.watch = demo.st.watch == "Dalia" and "Aldric Stormwind" or "Dalia"
        demoState()
        return true
    elseif op == "RDEPLOY" then
        return true
    elseif op == "GET" and demo.st then
        for _, r in ipairs(recs) do
            if r[1] == "ROYS" then
                demoState()
                demoObjects()
            elseif r[1] == "ROYM" then
                demoMap()
            end
        end
    end
    return false
end
