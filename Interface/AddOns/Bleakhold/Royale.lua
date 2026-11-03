-- Bleakhold: Bleakhold Royale (docs/BleakholdProtocol.md section 17), the core. Everything shown is server state
-- (QUEUE kind B, ROYS ROYM ROYO ROYK ROYV ROYE, parsed in State.lua); the client counts the timers down and sends
-- only the player's wishes: QJOIN B / QLEAVE / QREPLY (the queue and its ready check), RDROP (a landing pin) and
-- RSPEC (the spectator camera); the parachute opens by itself (RoyaleDrop.lua shows the drop, RDEPLOY goes unused).
-- Bleakhold.exe also draws the storm circle as a wall in the world (RoyaleHud.lua hands it the circle:
-- BleakholdStorm_Set). This file holds what the map (RoyaleMap.lua) and the HUD (RoyaleHud.lua) share: the match
-- helpers (storm circle now, the player's own position), the intents with their client-side gates, the patch gate,
-- and the queue side: the Royale page of Activities, the ready check popup, the minimap orb, /bh royale with the
-- Royale options (motion, sounds, view distance, minimap storm, HUD scale), the routing of Royale toasts to the
-- banner during a match, sample screens for /bh royale preview and a scripted match for /bh demo. Both feed sample
-- frames through the real receive path (Demo.Push); a preview answers its own intents and never sends them.
--
-- The client's Lua (Lua 5.1.1-5.1.3's code generator, Engine/Source/lua-5.1/src/lcode.c) miscompiles an arithmetic
-- whose constant operand sits past index 255 of its function: the frames and pages here are built inside functions,
-- each with its own constants, so this file's main chunk stays under that (test_royale_glue.lua checks it).
--
-- Two gates before QJOIN goes out: HELLO feature bit 4096 (the realm runs the mode) and the map patch, tested with
-- Texture:SetTexture on a marker BLP that MapForge packs into patch-Q (a client without it cannot load map 901).
-- Each map version has its own marker (v1 Marker.blp, v2 MarkerV2.blp), so a client still holding an older
-- patch-Q, whose terrain no longer matches the server's, cannot queue either.
local ADDON, ns = ...
local U, UI, Comm, Data = ns.U, ns.UI, ns.Comm, ns.Data
local C = UI.C
local S = ns.S
local A = ns.Activities

local floor, ceil, max, min, sqrt, cos, sin = math.floor, math.ceil, math.max, math.min, math.sqrt, math.cos, math.sin

local R = {}
ns.Royale = R

R.MAP_ID = 901                    -- the island (MapForge bleakhold_royale.json); its picture is Art\Royale\IslandMap
R.ACTIVITY = 901                  -- the mode id QJOIN B carries (the server's Bleakhold.Royale.ActivityId)
R.ROLES = 4                       -- ignored by the server for Royale; damage, like the Rift's default
R.MARKER = "Interface\\Bleakhold\\Royale\\MarkerV2"    -- in v2's patch-Q (MapForge archives.marker_texture)
R.MAP_TEX = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\IslandMap"
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
R.MATCH_INTENTS = { RDROP = true, RSPEC = true, RDEPLOY = true }   -- a preview answers these itself

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
local previewRespond      -- the previews' own answer to a match intent (below), while their sample match runs

local function send(op, ...)
    local sample = R.MATCH_INTENTS[op] and R.InPreview()
    if not sample and not connected() then
        return false
    end
    local now = GetTime()
    if nextAt[op] and now < nextAt[op] then
        return false
    end
    local ok
    if sample then
        ok = previewRespond(op, ...)   -- never to the realm: it knows nothing of the sample match
    else
        ok = Comm.Send(op, ...)
    end
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
    if not R.InPreview() and not connected() then
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

-- RDEPLOY, kept for the protocol: the UI never sends it (the server opens the parachute by itself and ignores it).
-- Only while falling from the drop, once, 0.5 s into the fall.
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
-- The ready check (QUEUE kind B state 2): MATCH FOUND on an iron plate, the mode and the match's size, a bronze ring
-- around the seconds left in the metal numerals, the count who accepted, Accept (gold) and Decline (iron). The ring
-- is CountRingSmall (128 px at 80 units: 1.1x minified at 1080p). The countdown's Notch art cannot go that small (its
-- 64 px at 6 units would be minified 7x, and Interface textures have no mipmaps), so a faceted Gem (a 32-px cell at 11
-- units: 2.1x) sits in each of the ring's 15 sockets, white like a cut stone (a gold one vanished into the bronze).
-- While n fifteenths of the answer time are left the first n gems, from the top clockwise, stay set, as the
-- countdown's notches stay lit; a spent one leaves its dark socket, and the last three seconds burn ember.
------------------------------------------------------------------------------------------------------
R.READY = { w = 360, h = 226, top = 18, title = 22, bodyY = -50, ring = 80, ringY = -112, gem = 11, num = 22,
    countY = -160, button = 28, bottom = 16, acceptW = 140, declineW = 116, gap = 10, hot = 3, lit = "safe",
    burn = "ember", fade = 0.25, stagger = 0.02, rulePad = 30, ruleGap = 10 }
local RDY = R.READY
local rc

-- The lit gems for `left` of `total` seconds (all of them while the time is unknown); `fresh` lights them one after
-- another (the popup's entrance), else a gem going dark fades out.
local function readyRing(left, total, fresh)
    local RS = ns.RoyaleStyle
    local gems = rc.gems
    local n = #gems
    local lit = left and U.Clamp(ceil(left / total * n - 1e-6), 0, n) or n
    local hot = left ~= nil and left <= RDY.hot
    for i, g in ipairs(gems) do
        local on = i <= lit
        if g.hot ~= hot then
            g.hot = hot
            g:SetVertexColor(RS.Rgb(hot and RDY.burn or RDY.lit))
        end
        if fresh then
            g.on = on
            RS.Stop(g, "alpha")
            g:SetAlpha(0)
            if on then
                RS.Tween(g, "alpha", 0, 1, 0.12, "outCubic", { delay = 0.1 + (i - 1) * RDY.stagger })
            end
        elseif g.on ~= on then
            g.on = on
            RS.Tween(g, "alpha", nil, on and 1 or 0, RDY.fade, on and "outCubic" or "inCubic")
        end
    end
    -- the seconds: a short punch on each new one, an ember flare on the last three
    local sec = left and ceil(left - 1e-6) or nil
    local num = rc.num
    if sec ~= rc.shownSec then
        local had = rc.shownSec ~= nil
        rc.shownSec = sec
        num:SetValue(sec or "")
        num:SetGlowColor(hot and RDY.burn or "gold")
        if had and not fresh and sec then
            RS.Tween(num, "zoom", 1.14, 1, 0.18, "outBack")
            if hot then
                RS.Tween(num.glow, "alpha", 0.7, 0, 0.45, "outCubic")
            end
        end
    end
end

local function buildReady()
    local RS = ns.RoyaleStyle
    local DATA = ns.RoyaleArt
    rc = CreateFrame("Frame", "BleakholdRoyaleReady", UIParent)
    rc:SetSize(RDY.w, RDY.h)
    rc:SetPoint("TOP", UIParent, "TOP", 0, -170)
    rc:SetFrameStrata("DIALOG")
    rc:SetToplevel(true)
    rc:EnableMouse(true)
    rc:Hide()
    RS.RegisterRoot(rc)
    R.ready = rc
    rc.art = RS.Plate(rc, "Plate")
    rc.shine = RS.Shine(rc.art, 0.5)
    rc.title = RS.Title(rc, "MATCH FOUND", RDY.title, "gold")
    rc.title:SetPoint("TOP", rc, "TOP", 0, -RDY.top)
    rc.body = RS.Text(rc, "body", 13, "parchment", "CENTER")
    rc.body:SetPoint("TOP", rc, "TOP", 0, RDY.bodyY)
    UI.OneLine(rc.body, RDY.w - 48)
    -- the ring, its gems and the seconds in its dark disc
    local ring = CreateFrame("Frame", nil, rc)
    ring:SetSize(RDY.ring, RDY.ring)
    ring:SetPoint("CENTER", rc, "TOP", 0, RDY.ringY)
    rc.ring = ring
    rc.ringArt = RS.Art(ring, "CountRingSmall", RDY.ring, RDY.ring, "BORDER")
    rc.ringArt:SetPoint("CENTER", ring, "CENTER", 0, 0)
    -- an engraved rule either side, so the ring sits on a line like a medallion
    local half = RDY.ring / 2 + RDY.ruleGap
    rc.rules = {}
    for i, side in ipairs({ -1, 1 }) do
        local t = RS.Hairline(rc, RDY.w / 2 - RDY.rulePad - half, "bronzeLo", false, "BORDER", 0.9)
        t:SetPoint(side < 0 and "RIGHT" or "LEFT", rc, "TOP", side * half, RDY.ringY)
        rc.rules[i] = t
    end
    rc.gems = {}
    for i, s in ipairs(DATA.ring.sockets) do
        local g = RS.Art(ring, "Gem", RDY.gem, RDY.gem, "ARTWORK", DATA.gem.gem)
        g:SetPoint("CENTER", ring, "CENTER", cos(s.angle) * s.r * RDY.ring, sin(s.angle) * s.r * RDY.ring)
        g:SetVertexColor(RS.Rgb(RDY.lit))
        g.hot, g.on = false, true
        rc.gems[i] = g
    end
    rc.num = RS.Numeral(ring, { cap = RDY.num, glowColor = "gold", glowOver = true })
    rc.num:SetPoint("CENTER", ring, "CENTER", 0, 0)
    rc.count = RS.Text(rc, "body", 12, "ash", "CENTER")
    rc.count:SetPoint("TOP", rc, "TOP", 0, RDY.countY)
    UI.OneLine(rc.count, RDY.w - 48)
    -- the answer
    local bw = RDY.acceptW + RDY.gap + RDY.declineW
    rc.accept = RS.Button(rc, RDY.acceptW, RDY.button, "Accept", "gold", 13)
    rc.accept:SetPoint("BOTTOMLEFT", rc, "BOTTOM", -bw / 2, RDY.bottom)
    rc.decline = RS.Button(rc, RDY.declineW, RDY.button, "Decline", "iron", 13)
    rc.decline:SetPoint("BOTTOMRIGHT", rc, "BOTTOM", bw / 2, RDY.bottom)
    rc.waiting = RS.Text(rc, "body", 13, "gold", "CENTER")
    rc.waiting:SetPoint("BOTTOM", rc, "BOTTOM", 0, RDY.bottom + 7)
    rc.waiting:SetText("Accepted. Waiting for the others.")
    rc.waiting:Hide()

    rc.accept:SetScript("OnClick", function()
        R.Reply(true)
    end)
    rc.decline:SetScript("OnClick", function()
        if R.Reply(false) then
            RS.Tween(rc, "alpha", nil, 0, 0.2, "inCubic", { onDone = function()
                rc:Hide()
            end })
        end
    end)
    local acc = 0
    rc:SetScript("OnUpdate", function(self, elapsed)
        acc = acc + (elapsed or 0)
        if acc >= 0.1 then
            acc = 0
            R.UpdateReady()
        end
    end)
end
buildReady()

function R.ReadyLeft(q)
    q = q or royaleQueue()
    if not q or not q.timeoutSec then
        return nil
    end
    return max(0, q.timeoutSec - (GetTime() - (q.recvAt or GetTime())))
end

-- Lays the popup out from the queue's state (`fresh`: it just opened); hides it when the proposal is over.
function R.UpdateReady(fresh)
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
    readyRing(left, total, fresh)
    local size = q.proposalSize
    local body = size and ("Bleakhold Royale · " .. size .. " players") or "Bleakhold Royale"
    local count = (q.accepted and size) and (q.accepted .. " of " .. size .. " accepted") or ""
    if rc.body:GetText() ~= body then
        rc.body:SetText(body)
    end
    if (rc.count:GetText() or "") ~= count then
        rc.count:SetText(count)
    end
    local answered = R.answered and R.answered.id == q.proposalId and R.answered.accept
    for _, r in ipairs({ rc.accept, rc.decline, rc.waiting }) do
        if (r == rc.waiting) == (answered and true or false) then
            r:Show()
        else
            r:Hide()
        end
    end
end

-- A new proposal: the plate enters (0.2 s), the title punches in with its glow, a shine crosses it, the gems light
-- one after another.
local function showReady()
    local RS = ns.RoyaleStyle
    RS.Stop(rc)
    rc.shownSec = nil
    rc:SetAlpha(0)
    rc:Show()
    R.UpdateReady(true)
    RS.Tween(rc, "alpha", 0, 1, 0.2, "outCubic")
    RS.Tween(rc, "offset", { 0, 12 }, { 0, 0 }, 0.2, "outCubic")
    RS.Tween(rc.title, "zoom", 1.15, 1, 0.22, "outBack")
    RS.Tween(rc.title.glow, "alpha", 0.8, 0, 0.8, "outCubic")
    RS.Sweep(rc.shine, 0.1, 0.6)
end

-- A new Royale proposal opens the popup (with the queue pop sound); any QUEUE redraws or closes it.
ns.On("STATE", function(topic)
    if topic ~= "QUEUE" then
        return
    end
    local q = royaleQueue()
    if q and q.state == 2 and q.proposalId and q.proposalId ~= R.shownProposal then
        R.shownProposal = q.proposalId
        R.answered = nil
        showReady()
        if PlaySound then
            PlaySound("PVPTHROUGHQUEUE")
        end
    end
    if rc:IsShown() then
        R.UpdateReady()
    end
end)

------------------------------------------------------------------------------------------------------
-- Activities: the Royale page, in the old window's page anatomy (Activities.lua A.Page): the title and what the mode
-- is; the island map as the page's picture on the right; the last match in the stat column (place, eliminations,
-- time survived) with the matches running now; the island card (its thumbnail, "Last one standing" and the facts);
-- how it works; the last match's rewards; bottom right the queue's state over Queue / Leave queue, bottom left why
-- this client cannot queue. The kill announcer's settings are on the Tasks page (Activities.lua): the announcer plays
-- in every battleground, Royale or not.
------------------------------------------------------------------------------------------------------
R.PAGE_ART_ALPHA = 0.45           -- the island behind the page: bright art, so dimmed like the dense pages' pictures

-- "#1 Victory" or "#7 of 32".
function R.PlaceText(placement, total)
    if placement == 1 then
        return "#1 Victory"
    end
    return "#" .. placement .. (total and (" of " .. total) or "")
end

-- The island map, cropped to the page picture's shape (Activities.lua A.ART_W x A.ART_H).
function R.PageArt()
    local trim = max(0, (1 - A.ART_W / A.ART_H) / 2)
    return { file = R.MAP_TEX, coords = { trim, 1 - trim, 0, 1 } }
end

-- The island card (the old pages' keystone block): the map's thumbnail as an icon, the motto, the facts.
local function buildIsland(P)
    local hero = CreateFrame("Frame", nil, P)
    hero:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD, A.BODY_Y)
    hero:SetSize(A.DESC_W, 52)
    hero.thumb = UI.Icon(hero, 52, R.THUMB_TEX)
    hero.thumb:SetPoint("TOPLEFT", hero, "TOPLEFT", 0, 0)
    hero.title = UI.Text(hero, 16, C.text)
    hero.title:SetPoint("TOPLEFT", hero.thumb, "TOPRIGHT", 10, -7)
    UI.OneLine(hero.title, A.DESC_W - 62)
    hero.title:SetText("Last one standing")
    hero.facts = UI.Text(hero, 11, C.dim)
    hero.facts:SetPoint("TOPLEFT", hero.title, "BOTTOMLEFT", 0, -5)
    UI.OneLine(hero.facts, A.DESC_W - 62)
    hero.facts:SetText("Solo · Level 80 · 20-40 players")
    return hero
end

-- How it works: five numbered steps, the number in gold.
local HOW_Y, HOW_PITCH, HOW_W = -194, 34, 370
local function buildHow(P)
    local how = { title = P:Section("How it works", A.PAD, HOW_Y), lines = {}, numbers = {} }
    local HOW = {
        "Queue alone. At 20 players a ready check goes out; answer it within 15 seconds.",
        "Brawl on Sunwatch Overlook while the others arrive, and click the island map to set your landing pin.",
        "You drop from high above your landing, fall for 8 s, and your parachute opens by itself.",
        "Loot crates, orbs and supply drops, and stay inside the storm circle: it closes in stages.",
        "Eliminated players watch the rest, queue again or leave. Honor and Shards by placement.",
    }
    for i, line in ipairs(HOW) do
        local y = HOW_Y - 24 - (i - 1) * HOW_PITCH
        local num = UI.Text(P, 12, C.gold)
        num:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD, y)
        num:SetText(i .. ".")
        local t = UI.Para(P, 12, C.text, HOW_W)
        t:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD + 20, y)
        t:SetText(line)
        how.numbers[i], how.lines[i] = num, t
    end
    return how
end

-- The last match: its place, eliminations and time in the stat column (with the matches running now), its rewards
-- under a heading of their own.
local LAST_Y = -398
local function buildLast(P)
    local last = {}
    last.place = P:Stat(1, "Last Match")
    last.kills = P:Stat(2, "Eliminations")
    last.survived = P:Stat(3, "Survived")
    last.running = P:Stat(4, "Matches Running")
    last.title = P:Section("Last Match Rewards", A.PAD, LAST_Y)
    last.none = UI.Text(P, 12, C.dim)
    last.none:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD, LAST_Y - 24)
    UI.OneLine(last.none, HOW_W + 20)
    last.lines = {}
    for i = 1, 4 do
        local rw = UI.Reward(P, 16, 12)
        rw:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD, LAST_Y - 24 - (i - 1) * 20)
        rw:Hide()
        last.lines[i] = rw
    end
    return last
end

-- The queue, bottom right (as the other pages' actions): its state over its detail over Queue / Leave queue; why the
-- client cannot queue bottom left.
local function buildQueue(P, hero)
    hero.join = UI.Button(P, 200, 30, "Queue", "red", 12)
    hero.join:SetPoint("BOTTOMRIGHT", P, "BOTTOMRIGHT", -18, 18)
    hero.detail = UI.Text(P, 11, C.dim, "body", "RIGHT")
    hero.detail:SetPoint("BOTTOMRIGHT", hero.join, "TOPRIGHT", -2, 8)
    UI.OneLine(hero.detail, 340)
    hero.status = UI.Text(P, 14, C.text, "body", "RIGHT")
    hero.status:SetPoint("BOTTOMRIGHT", hero.detail, "TOPRIGHT", 0, 4)
    UI.OneLine(hero.status, 340)
    hero.notice = UI.Text(P, 12, C.red)
    hero.notice:SetPoint("BOTTOMLEFT", P, "BOTTOMLEFT", A.PAD, 26)
    UI.OneLine(hero.notice, 360)
    hero.join:SetScript("OnClick", function()
        local q = royaleQueue()
        if q and (q.state == 1 or q.state == 2) then
            R.Leave()
        else
            R.Join()
        end
    end)
end

-- One reward line of the last match: its icon and name, then the server's reason ("400 Honor - Placement").
local function setRewardLine(rw, e)
    rw:SetReward(e.kind, e.amount, e.itemId, e.text)
    UI.SetText(rw.text, e.line or "")
    rw:Show()
end

local QUEUE_STATUS = { [1] = "In the queue", [2] = "Match found - answer the ready check", [3] = "In a match" }

local function buildPage()
    local P = A.Page("royale", {
        title = "Bleakhold Royale",
        desc = "Drop onto the island with up to 39 others, loot crates and orbs and outlast the storm. One life: the "
            .. "last player standing wins. Your own gear counts; the island's loot is yours for the match.",
        art = R.PageArt(), artAlpha = R.PAGE_ART_ALPHA,
    })
    R.page = P
    local hero = buildIsland(P)
    P.hero = hero
    P.how = buildHow(P)
    local last = buildLast(P)
    P.last = last
    buildQueue(P, hero)
    P.join = hero.join

    function P:Tick()
        local q = royaleQueue()
        if not q then
            return
        end
        local since = GetTime() - (q.recvAt or GetTime())
        if q.state == 1 then
            local txt = "Waiting " .. U.Clock((q.queuedSec or 0) + since)
            if q.matchesRunning and q.matchesRunning > 0 then
                txt = txt .. "  -  " .. q.matchesRunning .. (q.matchesRunning == 1 and " match" or " matches")
                    .. " running"
            end
            hero.detail:SetText(txt)
        elseif q.state == 2 then
            local left = R.ReadyLeft(q)
            hero.detail:SetText(left and ("Answer within " .. ceil(left) .. " s") or "")
        end
    end

    function P:RefreshQueue()
        local q = royaleQueue()
        local st = q and q.state or 0
        local block = R.QueueBlock()
        if st == 1 or st == 2 then
            local n = q.queued and q.minPlayers and (q.queued .. " / " .. q.minPlayers .. " queued") or QUEUE_STATUS[st]
            hero.status:SetText(st == 2 and QUEUE_STATUS[2] or n)
            UI.SetColor(hero.status, st == 2 and C.teal or C.gold)
            hero.join:SetLabel("Leave queue")
            hero.join:SetActive(true)
        elseif st == 3 or R.Match() then
            hero.status:SetText(QUEUE_STATUS[3])
            UI.SetColor(hero.status, C.teal)
            hero.detail:SetText("")
            local m = R.Match()
            local spectator = m and (m.me == R.ME.SPECTATING or m.me == R.ME.LEFT)
            hero.join:SetLabel(spectator and "Queue again" or "In a match")
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
            hero.join:SetActive(block == nil)
        end
        UI.SetText(hero.notice, block or "")
        local running = q and q.matchesRunning
        last.running:SetText(running and tostring(running) or "-")
    end

    -- The last match: this session's, or the one saved for this character (place, eliminations and time only).
    function P:RefreshLast()
        local res = S.royaleResult
        local saved = ns.cdb.royaleLast
        for _, rw in ipairs(last.lines) do
            rw:Hide()
        end
        last.none:SetText("")
        if res and res.placement then
            last.place:SetText(R.PlaceText(res.placement, res.total))
            last.kills:SetText(tostring(res.kills or 0))
            last.survived:SetText(U.Clock(res.survivedSec or 0))
            for i, rw in ipairs(last.lines) do
                if res.rewards[i] then
                    setRewardLine(rw, res.rewards[i])
                end
            end
            if #res.rewards == 0 then
                last.none:SetText(res.rewarded and "No rewards this time." or "No rewards. You left early or saw no fight.")
            end
        elseif type(saved) == "table" and type(saved.placement) == "number" then
            last.place:SetText(R.PlaceText(saved.placement, type(saved.total) == "number" and saved.total or nil))
            last.kills:SetText(type(saved.kills) == "number" and tostring(saved.kills) or "-")
            last.survived:SetText(type(saved.survivedSec) == "number" and U.Clock(saved.survivedSec) or "-")
            last.none:SetText("Your rewards went to your bags and your mail.")
        else
            last.place:SetText("No match yet")
            last.kills:SetText("-")
            last.survived:SetText("-")
            last.none:SetText("Play a match: your place, eliminations and rewards show here.")
        end
    end

    function P:Refresh()
        P:RefreshQueue()
        P:Tick()
        P:RefreshLast()
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

    -- The last result, kept per character for the page after a relog.
    ns.On("ROYALE_RESULT", function(res)
        ns.cdb.royaleLast = { placement = res.placement, total = res.total, kills = res.kills,
            survivedSec = res.survivedSec, matchId = res.matchId }
    end)
end
buildPage()

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

local function addOrb()
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
end
addOrb()

------------------------------------------------------------------------------------------------------
-- The Royale options: /bh royale motion|sounds|farclip on|off, /bh royale minimap on|off, /bh royale scale 0.8-1.4.
-- Each answers with its state in a line: on its own, or after the change.
--   motion   royaleMotion (RoyaleStyle.lua): off makes every tween jump to its end and keeps the loops still
--   sounds   royaleSounds (RoyaleStyle.lua): the ticks, hammer blows, gong, wind, canopy, landing and kill clang
--   farclip  royaleFarclip (RoyaleDrop.lua): the view distance rises to 1277 for the drop and goes back after it
--   minimap  royaleMinimap and Bleakhold.exe's bleakStormMinimap (RoyaleMinimap.lua prints its own line)
--   scale    royaleHudScale (RoyaleStyle.lua): every Royale root frame, and the docked map's fit
------------------------------------------------------------------------------------------------------
R.OPTIONS = { motion = true, sounds = true, farclip = true, scale = true }

function R.OptionText(name)
    local RS = ns.RoyaleStyle
    if name == "motion" then
        return "Royale motion: " .. (RS.Motion() and "on." or "off. Every animation jumps to its end.")
    elseif name == "sounds" then
        return "Royale sounds: " .. (RS.Sounds() and "on." or "off. No ticks, gong, wind or clang.")
    elseif name == "farclip" then
        local RD = ns.RoyaleDrop
        if RD.FarclipOption() then
            return "Royale view distance: on. It rises to " .. RD.FARCLIP .. " for the drop and goes back after it."
        end
        return "Royale view distance: off. Yours stays as it is."
    elseif name == "scale" then
        return string.format("Royale HUD scale: %.2f (%.1f to %.1f).", RS.HudScale(), RS.HUD_SCALE_MIN,
            RS.HUD_SCALE_MAX)
    end
    return nil
end

-- Sets an option from a command word ("on" or "off"; a number for the scale; nothing leaves it) and returns its line.
function R.SetOption(name, value)
    local RS = ns.RoyaleStyle
    value = value or ""
    if name == "scale" then
        if value ~= "" then
            RS.SetHudScale(value)    -- a word that is no number changes nothing
        end
    elseif value == "on" or value == "off" then
        local on = value == "on"
        if name == "motion" then
            RS.SetMotion(on)
        elseif name == "sounds" then
            RS.SetSounds(on)
        elseif name == "farclip" then
            ns.RoyaleDrop.SetFarclipOption(on)   -- off puts a raised view distance back at once
        end
    end
    return R.OptionText(name)
end

R.USAGE = "Bleakhold Royale: /bh royale [map|leave|preview countdown|drop|banner|end|map|motion|sounds|farclip"
    .. "|minimap on|off|scale 0.8-1.4|wall on|off|test|stop|voice off|male|female|quiet|normal]"
R.PREVIEW_USAGE = "Royale previews: /bh royale preview countdown|drop|banner|end [eliminated]|map"

local function command(args)
    args = args or ""
    local a, b = args:lower():match("^(%S*)%s*(%S*)")
    local rest = args:match("^%S*%s*(.*)$") or ""
    if a == "map" then
        UI.Open("royalemap", true)
    elseif a == "wall" then
        ns.RoyaleHud.WallCommand(rest)   -- the storm wall (Bleakhold.exe)
    elseif a == "minimap" then
        ns.RoyaleMinimap.Command(rest)   -- the storm on the minimap: Bleakhold.exe's, or the addon's dots
    elseif R.OPTIONS[a] then
        ns.Print(R.SetOption(a, b))
    elseif a == "preview" then
        local kind, arg = rest:lower():match("^(%S*)%s*(%S*)")
        local ok, why = R.Preview(kind, arg)
        if not ok then
            ns.Print(why or R.PREVIEW_USAGE)
        end
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
end
ns.AddCommand("royale", R.USAGE, command)

------------------------------------------------------------------------------------------------------
-- Royale toasts during a match. Toast.lua's plate sits at TOP -110, on the banner's band (RoyaleHud.lua), so while
-- R.Match() a toast for the Royale page becomes the banner when its title is one of the baked titles (MATCH
-- CANCELLED, RoyaleHud.lua's), after the countdown's own MATCH CANCELLED has left; any other (the realm's queue
-- notices, "Bleakhold Royale" over a line) goes to the chat as a line. Outside a match toasts are as they were.
------------------------------------------------------------------------------------------------------
R.TOAST_BANNERS = { ["MATCH CANCELLED"] = "blood" }    -- a baked title -> its colour
R.TOAST_WAIT = 3                                       -- s a banner waits at most for the countdown to leave

local function toastBanner(d, color, waited)
    local RC = ns.RoyaleCountdown
    if RC and RC.frame and RC.frame:IsShown() and waited < R.TOAST_WAIT then
        ns.After(0.1, function()
            toastBanner(d, color, waited + 0.1)
        end)
        return
    end
    ns.RoyaleHud.Banner({ key = "toast", title = d.title, color = color, line = d.sub or "" })
end

-- Returns true when the toast went to the banner or the chat.
function R.RouteToast(d)
    if type(d) ~= "table" or d.target ~= "royale" or not R.Match() or not ns.RoyaleHud then
        return false
    end
    local color = R.TOAST_BANNERS[d.title or ""]
    if color then
        toastBanner(d, color, 0)
    else
        local text = (d.sub and d.sub ~= "") and d.sub or d.title
        ns.Print(U.Safe(tostring(text or "")))
    end
    return true
end

local function routeToasts()
    local push = ns.Toast.Push
    ns.Toast.Push = function(d)
        if R.RouteToast(d) then
            return
        end
        return push(d)
    end
end
routeToasts()

------------------------------------------------------------------------------------------------------
-- Sample matches: the frames /bh royale preview and /bh demo feed through the real receive path (Demo.Push)
------------------------------------------------------------------------------------------------------
-- The places of Bleakhold Royale v2 (MapForge specs/royale_v2.json pois, ids and radii as the server sends them).
local function samplePlaces()
    return {
        { 5213, "Y", 455, 455, 32, "Sunwatch Overlook" },
        { 5201, "L", -258, -345, 95, "Sunstair Isle" }, { 5202, "L", -45, -170, 90, "Tidecall Village" },
        { 5203, "L", 320, -790, 80, "Twinfall Terrace" }, { 5204, "L", -490, -662, 60, "Saltwreck Cove" },
        { 5205, "L", -776, 339, 80, "Serpent Steps" }, { 5206, "L", -250, 200, 90, "Sunbloom Meadow" },
        { 5207, "L", 215, -312, 50, "Kingfisher Point" }, { 5208, "L", -255, -745, 80, "Mossvine Hollow" },
        { 5209, "L", -740, -290, 70, "Bamboo Reach" }, { 5210, "L", 360, 250, 60, "Sunwatch Falls" },
        { 5215, "L", -790, -784, 70, "Salvagers' Camp" }, { 5216, "L", -425, 50, 50, "Totem Knoll" },
        { 5217, "L", 80, -520, 50, "Heron Rise" },
        { 5211, "C", -10, -625, 16, "Stepping Stones" }, { 5212, "C", -785, 263, 18, "Vine Bridge" },
        { 5214, "C", -150, -275, 14, "Tidewalk" },
    }
end

local function samplePush(op, records)
    if ns.Demo then
        ns.Demo.Push(op, records)
    end
end

-- ROYM: the island's picture frame, the lobby, the storm's bounds and the places.
local function sampleMap()
    local recs = { { R.MAP_ID, -1066, 533, -1066, 533, 455, 455, 32, 750, -267, -267 } }
    for _, p in ipairs(samplePlaces()) do
        recs[#recs + 1] = p
    end
    samplePush("ROYM", recs)
end

-- The ms from now to `at` (a GetTime() deadline), as a ROYS time field carries them; nil without one.
local function msTo(at)
    return at and max(0, floor((at - GetTime()) * 1000 + 0.5)) or nil
end

-- ROYS of match `id` in state `s`. Its times are GetTime() deadlines (phaseAt, shrinkFrom, shrinkTo, openAt for the
-- parachute, landAt), so a state sent again later (a pin, the spectator camera, GET ROYS) carries the time left, as
-- the realm's does; fields 25-27 only while falling.
local function sampleState(id, s)
    local fall = s.me == R.ME.DROPPING and s.landAt
    samplePush("ROYS", { { id, s.phase, msTo(s.phaseAt) or 0, s.alive, s.total or 24, s.me, s.kills or 0,
        s.placement or "", s.pinX or "", s.pinY or "", s.stage or 0, s.curX, s.curY, s.curR, s.nextX or "",
        s.nextY or "", s.nextR or "", msTo(s.shrinkFrom) or "", msTo(s.shrinkTo) or "", s.dmg or 0, s.watch or "",
        s.myX or "", s.myY or "", 6, fall and msTo(s.openAt) or "", fall and msTo(s.landAt) or "",
        fall and s.fallMs or "" } })
end

-- ROYO: two supply drops still falling and six orbs.
local function sampleObjects(id)
    samplePush("ROYO", { { id, 1 }, { 1, "S", 0, -351, -249, 0, 30000 }, { 2, "S", 0, -775, 350, 0, 30000 },
        { 3, "B", 1, -15, -150, 1, "" }, { 4, "B", 2, -460, -712, 1, "" }, { 5, "B", 3, 300, -790, 1, "" },
        { 6, "B", 3, 205, -306, 2, 45000 }, { 7, "B", 1, -235, 215, 1, "" }, { 8, "B", 2, -720, -310, 1, "" } })
end

------------------------------------------------------------------------------------------------------
-- /bh royale preview countdown|drop|banner|end|map: each screen with sample data outside a match, for screenshots and
-- the owner's review. The countdown and the map run a sample match through the real receive path, as /bh demo does,
-- so the top bar, the docked map, the countdown and the map's layers all show as in a match; a click on the map
-- (RDROP) is answered here and never reaches the realm. The drop, the banners and the end card play their modules'
-- own samples (RoyaleDrop.lua RD.Preview, RoyaleHud.lua H.Preview). The player's last result is kept for the
-- Activities card. A real match (or /bh demo's) refuses previews and ends a running one.
--   countdown  the lobby just under 16 s before the drop: the map opens docked, the realm's ROYS at 15000 ms brings
--              circle 1, the ring and its numerals count 15 to 1, the pin locks and the map closes at T-3.6, DROP!
--   map        the fight: the storm (circle 2 of 6, closing in 1:24), the next circle, the way to it, the places, the
--              orbs and supply drops; it runs until the map is closed (at most R.PREVIEW_MAP_MAX s)
------------------------------------------------------------------------------------------------------
R.PREVIEW_MATCH = 2147483000         -- the sample match's id: far above any id a realm hands out
R.PREVIEW_LEAD = 15.9                -- s before the sample's drop when the countdown preview starts (no farclip raise)
R.PREVIEW_MAP_MAX = 300
R.PREVIEW_HEARTBEAT = 5              -- s between the sample's ROYS (a match goes stale without one, R.STALE)
local pv                             -- the running sample match: { kind, run, result, at, st, pushedAt }
local previewRuns = 0

function R.InPreview(m)
    m = m or S.royale
    return pv ~= nil and m ~= nil and m.matchId == R.PREVIEW_MATCH
end

function R.PreviewKind()
    return pv and pv.kind or nil
end

local function previewAfter(sec, fn)
    local run = pv and pv.run
    ns.After(sec, function()
        if pv and pv.run == run and R.InPreview() then
            fn()
        end
    end)
end

-- Ends the sample match (the HUD it brought goes with it) and gives the player's last result back.
function R.EndPreview()
    local p = pv
    if not p then
        return false
    end
    pv = nil
    if S.royale and S.royale.matchId == R.PREVIEW_MATCH then
        R.ForgetMatch()
    end
    if p.result and not S.royaleResult then
        S.royaleResult = p.result
    end
    return true
end

local function startSample(kind, st)
    previewRuns = previewRuns + 1
    pv = { kind = kind, run = previewRuns, result = S.royaleResult, at = GetTime(), st = st, pushedAt = GetTime() }
    sampleMap()
    sampleState(R.PREVIEW_MATCH, st)
end

local function previewCountdown()
    local lead = R.PREVIEW_LEAD
    local st = { phase = R.PHASE.COUNTDOWN, phaseAt = GetTime() + lead, alive = 24, me = R.ME.LOBBY, curX = -267,
        curY = -267, curR = 860, pinX = -45, pinY = -170, myX = 452, myY = 450 }
    startSample("countdown", st)
    previewAfter(lead - 15, function()
        -- the realm's exact ROYS at 15000 ms reveals circle 1 (the countdown carries its banner in the lobby)
        st.nextX, st.nextY, st.nextR = -150, -310, 520
        samplePush("ROYV", { { "R", 1, -150, -310, "", "" } })
        sampleState(R.PREVIEW_MATCH, st)
        pv.pushedAt = GetTime()
    end)
    previewAfter(lead + 1.5, R.EndPreview)   -- DROP! has shown and faded by then
end

local function previewMap()
    local now = GetTime()
    local st = { phase = R.PHASE.FIGHT, alive = 17, me = R.ME.ALIVE, kills = 2, stage = 2, curX = -150, curY = -310,
        curR = 520, nextX = -60, nextY = -380, nextR = 300, shrinkFrom = now + 84, shrinkTo = now + 124, dmg = 20,
        myX = 170, myY = -40 }
    startSample("map", st)
    sampleObjects(R.PREVIEW_MATCH)
    ns.RoyaleMap.Open(false)
end

-- Keeps a map preview going while its map is open; a sample match that something else replaced or dropped is over.
local function previewTick()
    local p = pv
    if not p then
        return
    end
    if not R.InPreview() then
        pv = nil
        if not S.royale and p.result and not S.royaleResult then
            S.royaleResult = p.result
        end
        return
    end
    if p.kind ~= "map" then
        return
    end
    local now = GetTime()
    local MP = ns.RoyaleMap
    if not (MP.frame and MP.frame:IsShown()) or now - p.at > R.PREVIEW_MAP_MAX then
        R.EndPreview()
        return
    end
    if now - p.pushedAt >= R.PREVIEW_HEARTBEAT then
        p.pushedAt = now
        local st = p.st
        if st.shrinkTo and now >= st.shrinkTo then
            st.curX, st.curY, st.curR, st.shrinkFrom, st.shrinkTo = st.nextX, st.nextY, st.nextR, nil, nil
        end
        sampleState(R.PREVIEW_MATCH, st)
    end
end
ns.Every(0.5, previewTick)

-- A preview's own answer to a match intent: a landing pin moves the sample's pin (the map shows it as the realm's
-- snapped pin), anything else is accepted and ignored. Returns true like a sent intent.
previewRespond = function(op, x, y)
    if op == "RDROP" and pv and pv.st and R.CanPin() then
        local st = pv.st
        st.pinX, st.pinY = x, y
        ns.After(0.1, function()
            if pv and pv.st == st and R.InPreview() then
                sampleState(R.PREVIEW_MATCH, st)
            end
        end)
    end
    return true
end

-- /bh royale preview <kind> [eliminated]. Returns true when it plays, else false and why.
function R.Preview(kind, arg)
    local m = R.Match()
    if m and not R.InPreview(m) then
        return false, "Royale previews play outside a match."
    end
    R.EndPreview()
    if kind == "countdown" then
        previewCountdown()
        return true
    elseif kind == "map" then
        previewMap()
        return true
    elseif kind == "drop" then
        return ns.RoyaleDrop.Preview()
    elseif kind == "banner" then
        return ns.RoyaleHud.Preview("banner")
    elseif kind == "end" then
        return ns.RoyaleHud.Preview("end", arg == "eliminated" and arg or nil)
    end
    return false, R.PREVIEW_USAGE
end

------------------------------------------------------------------------------------------------------
-- /bh demo: a short scripted match (Demo.lua routes QJOIN B, QREPLY, QLEAVE, RDROP, RSPEC and GET ROYS/ROYM here).
-- The drop runs as the realm runs it by default: ROYS me 1 at the teleport, again at the start gun 0.2 s later (the
-- fall from rest, the times from there), again when the parachute opens by itself 8 s later; the touchdown 12 s after
-- that is seen 0.5 s later (ROYS me 2).
------------------------------------------------------------------------------------------------------
local DEMO_MATCH = 7001
R.DEMO_DROP = { at = 26, gun = 0.2, fall = 8, canopy = 12, hold = 0.5 }
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
    samplePush(op, records)
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
    sampleState(DEMO_MATCH, demo.st)
end

local function demoMap()
    sampleMap()
end

local function demoObjects()
    sampleObjects(DEMO_MATCH)
end

-- A kill feed line, and the kill announcer's BGANN when it carries a multi-kill or streak code (section 18).
local function demoKill(killer, kc, victim, vc, cause, kills, multi, streak)
    demo.st.alive = demo.st.alive - 1
    demoPush("ROYK", { { killer or "", killer and kc or "", victim, vc, cause, demo.st.alive,
        killer and kills or "" } })
    if killer and (multi or streak) then
        demoPush("BGANN", { { killer, kc, victim, vc, multi or "", streak or "" } })
    end
end

-- The drop: ROYS at the teleport, at the start gun and when the parachute opens; returns when the landing is seen.
local function demoDrop(st)
    local D = R.DEMO_DROP
    local function plan(fall, canopy)
        local now = GetTime()
        st.openAt, st.landAt = now + fall, now + fall + canopy
        st.phaseAt = st.landAt     -- phase 2 lasts until the last planned touchdown
        demoState()
    end
    demoAfter(D.at, function()
        st.phase, st.me, st.stage, st.fallMs = R.PHASE.DROP, R.ME.DROPPING, 1, D.fall * 1000
        st.myX, st.myY = st.pinX or -45, st.pinY or -170
        plan(D.fall, D.canopy)
    end)
    demoAfter(D.at + D.gun, function()
        plan(D.fall, D.canopy)
    end)
    demoAfter(D.at + D.gun + D.fall, function()
        plan(0, D.canopy)
    end)
    return D.at + D.gun + D.fall + D.canopy + D.hold
end

local function demoMatch()
    local st = { phase = 0, phaseAt = GetTime() + 6, alive = 24, me = 0, curX = -267, curY = -267, curR = 860,
        myX = 452, myY = 450 }
    demo.st = st
    demoMap()
    demoState()
    demoAfter(6, function()
        st.phase, st.phaseAt = 1, GetTime() + 20
        demoState()
    end)
    demoAfter(11, function()
        -- circle 1 is shown; like the server, the stage stays 0 until the drop
        st.nextX, st.nextY, st.nextR = -150, -310, 520
        demoPush("ROYV", { { "R", 1, -150, -310, "", "" } })
        demoState()
    end)
    local land = demoDrop(st)
    demoAfter(land, function()
        local now = GetTime()
        st.phase, st.phaseAt, st.me, st.shrinkFrom, st.shrinkTo, st.dmg = 3, nil, 2, now + 20, now + 50, 10
        st.openAt, st.landAt, st.fallMs = nil, nil, nil
        demoState()
        demoObjects()
        demoKill("Aldric Stormwind", 1, "Brenna", 8, "P", 1, nil, "F")
    end)
    demoAfter(land + 4, function()
        demoKill("Aldric Stormwind", 1, "Corwin", 5, "P", 2, "D", nil)
        demoPush("ROYV", { { "D", 0, -67, -267, 20000, "" } })
        demoPush("ROYO", { { DEMO_MATCH, 0 }, { 20, "D", 0, -67, -267, 3, 20000 } })
    end)
    demoAfter(land + 7, function()
        demoKill(nil, nil, "Eamon", 11, "S", nil)
        demoKill("Dalia", 11, "Fenna", 3, "P", 1)
    end)
    demoAfter(land + 20, function()
        st.curX, st.curY, st.curR, st.shrinkFrom, st.shrinkTo = -150, -310, 520, nil, nil
        st.alive = 10
        demoPush("ROYV", { { "N", 10, "", "", "", "" } })
        demoPush("ROYO", { { DEMO_MATCH, 0 }, { 20, "D", 0, -67, -267, 1, "" } })
        demoState()
    end)
    demoAfter(land + 26, function()
        demoKill("Aldric Stormwind", 1, ns.PlayerName() or "You", 1, "P", 3, nil, "S")
        demoPush("ROYE", { { DEMO_MATCH, 9, 24, demo.kills or 0, 9400, 0, 26, "", "", "", 1 },
            { "H", 120, "", "Placement" }, { "S", 12, "", "Placement" } })
        st.me, st.placement, st.watch, st.myX, st.myY = 3, 9, "Aldric Stormwind", nil, nil
        demoState()
    end)
    demoAfter(land + 40, function()
        st.alive = 1
        demoKill("Dalia", 11, "Aldric Stormwind", 1, "P", 7, nil, "W")
        demoPush("ROYV", { { "W", 7, "", "", "", "Dalia" } })
        st.phase, st.phaseAt, st.watch = 5, GetTime() + 12, "Dalia"
        demoState()
        demoPush("ROYE", { { DEMO_MATCH, 9, 24, demo.kills or 0, 9400, 0, 26, "Dalia", 11, 7, 1 },
            { "H", 120, "", "Placement" }, { "S", 12, "", "Placement" } })
    end)
    demoAfter(land + 52, function()
        st.phase, st.phaseAt = 6, GetTime() + 120
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
