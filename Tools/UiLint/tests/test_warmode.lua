-- War Mode and World PvP (docs/BleakholdProtocol.md section 19): the document's frames through State, the HUD and the
-- capture bar at the frame sizes the server may use; WMST and the War Mode page (the toggle, its confirmation, why it
-- is grey, the throttle, every ERR sentence); the feature bits 16384 and 32768; the Front HUD per WPZ kind and phase;
-- the capture bar; the world map pins and their math; the minimap arrows; WANTED and WPEV banners and toasts; the orb;
-- garbage; and War Mode in /bh demo.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local WAR, WPVP = 16384, 32768
local BOTH = WAR + WPVP

local function connect(M, bits)
    FX.connect(M, H, { [6] = bits or BOTH })
end

-- A WMST: War Mode off, nothing on cooldown, unless `over` says otherwise (field index -> value).
local function wmst(M, over)
    local r = { 0, 0, "", 20, 0, 10, 0, 8, "H", 31, 22, 0, 0, 0, 0, 0, 3720, 0, 60, 7, 118, 96 }
    for k, v in pairs(over or {}) do r[k] = v end
    H.send(M, "WMST", { r })
end

local ZONE = {
    { 2817, "F", 1, 4320, 620, 380, "A", 2, 80, 80 }, { "O", 1, "Violet Stand", 512, 388, "A", 1000, 1 },
    { "O", 2, "Forlorn Woods", 604, 455, "N", -120, 6 }, { "O", 3, "Sunreaver Rise", 701, 512, "A", 800, 1 },
}

-- WPZ: the Crystalsong Front, with the header (and outposts by index) changed by `over` / `objs`.
local function wpz(M, over, objs)
    local recs = {}
    for i, r in ipairs(ZONE) do
        local copy = {}
        for k, v in ipairs(r) do copy[k] = v end
        recs[i] = copy
    end
    for k, v in pairs(over or {}) do recs[1][k] = v end
    for i, o in pairs(objs or {}) do
        for k, v in pairs(o) do recs[i + 1][k] = v end
    end
    H.send(M, "WPZ", recs)
end

local function resting(M, on)
    M.env.IsResting = function() return on and 1 or nil end
end

local function faction(M, f)
    M.env.UnitFactionGroup = function(unit)
        if unit == "player" then return f, f end
    end
end

local function intentsOf(M, op)
    local out = {}
    for _, it in ipairs(H.intents(M)) do
        if it.op == op then out[#out + 1] = it.payload end
    end
    return out
end

local function gets(M)
    local out = {}
    for _, it in ipairs(H.intents(M)) do
        if it.op == "GET" then out[#out + 1] = it.payload end
    end
    return table.concat(out, ";")
end

local function errorsShown(M, text)
    local n = 0
    for _, c in ipairs(M.chat) do
        if c.frame == M.env.UIErrorsFrame and c.msg:find(text, 1, true) then n = n + 1 end
    end
    return n
end

local function near(a, b, eps)
    return math.abs(a - b) <= (eps or 0.01)
end

-- The world map of FrameXML (WorldMapFrame, WorldMapButton) and the map functions, the map shown being M.mapArea and
-- the player's zone's map M.myArea.
local function withMap(extra)
    return { before = function(M)
        local f = M.New("Frame", "WorldMapFrame", M.env.UIParent)
        f:Hide()
        local b = M.New("Button", "WorldMapButton", f)
        b:SetSize(1002, 668)
        local tip = M.New("GameTooltip", "WorldMapTooltip", f)
        tip.__shown = false
        M.mapArea, M.myArea = 0, 511
        M.env.SetMapToCurrentZone = function() M.mapArea = M.myArea end
        M.env.GetCurrentMapAreaID = function() return M.mapArea end
        M.env.GetPlayerMapPosition = function() return M.px or 0, M.py or 0 end
        if extra then extra(M) end
    end }
end

-- Section 19's S> example frames: { op, payload }.
local function docExamples()
    local text = assert(host_readfile(repo .. "/docs/BleakholdProtocol.md"))
    local sec = text:match("\n## 19%. World PvP and War Mode(.-)\n## %d")
        or text:match("\n## 19%. World PvP and War Mode(.*)$")
    assert(sec, "section 19")
    local out = {}
    for line in sec:gmatch("[^\n]+") do
        local body = line:match("^S> (.+)$")
        if body then
            local op, payload = body:match("^1 (%u+) %w+ 1/1 ?(.*)$")
            out[#out + 1] = { op = op, payload = payload, body = body }
        end
    end
    return out
end

------------------------------------------------------------------------------------------------------
-- The document's frames, re-framed at every size the server may use
------------------------------------------------------------------------------------------------------
for _, size in ipairs({ 1000, 251, 64 }) do
    test("doc section 19 frames at max body " .. size .. " reach State, the HUD and the capture bar", function(M, ns)
        faction(M, "Alliance")
        connect(M)
        local S, C, WF = ns.S, ns.Comm, ns.WarFront
        local examples = docExamples()
        H.ok(#examples >= 20, "section 19 examples: " .. #examples)
        local events, seq, sent = {}, 700, 0
        ns.On("WAR_EVENT", function(e) events[#events + 1] = e.kind end)
        local zone, capture, wanted, map
        for _, ex in ipairs(examples) do
            seq = seq + 1
            local frames = assert(C.BuildFrames(ex.op, seq, ex.payload, size))
            for _, body in ipairs(frames) do
                H.ok(#body <= size, "frame within " .. size .. " bytes")
                H.deliver(M, body)
                sent = sent + 1
            end
            M.Advance(0.3)
            if ex.op == "WPZ" and ex.payload:match("^2817,F") then
                zone = S.wpZone
                H.ok(WF.hud:IsShown(), "the Front HUD in Crystalsong Forest")
                H.eq(WF.hud.zone:GetText(), "Crystalsong Forest")
                H.eq(WF.hud.note:GetText(), "Dominion x2")
            elseif ex.op == "WPCAP" then
                capture = S.wpCap
                H.ok(WF.cap:IsShown(), "the capture bar at the outpost")
                H.eq(WF.cap.name:GetText(), "Forlorn Woods")
                H.eq(WF.cap.markerX, 14, "slider -120: a little towards the Horde's end")
                H.eq(WF.cap.net, -1, "three Horde against two Alliance")
            elseif ex.op == "WANTED" and ex.payload:find(";W,", 1, true) then
                wanted = S.wanted
            elseif ex.op == "WPMAP" then
                map = S.wpMap
            end
        end
        if size == 64 then
            H.ok(sent > #examples, "frames were chunked: " .. sent)
        end
        local drops = 0
        for _, v in pairs(C.stats.dropped) do drops = drops + v end
        H.eq(drops, 0, "no frame dropped")
        H.eq(C.stats.unknown, 0, "every op has a handler")
        H.eq(C.PendingChunks(), 0)
        -- WMST 2o
        local wm = S.warMode
        H.eq(wm.on, true); H.eq(wm.cooldownSec, 512); H.eq(wm.block, nil); H.eq(wm.minLevel, 20); H.eq(wm.xpPct, 0)
        H.eq(wm.honorPct, 10); H.eq(wm.shardPct, 0); H.eq(wm.underdogPct, 8); H.eq(wm.underdogTeam, "H")
        H.eq(wm.wmAlliance, 31); H.eq(wm.wmHorde, 22); H.eq(wm.streak, 3); H.eq(wm.wantedState, 0)
        H.eq(wm.wantedSec, 0)
        H.eq(wm.bountyHonor, 0); H.eq(wm.todayBonusHonor, 412); H.eq(wm.bonusHonorCap, 3720); H.eq(wm.todayShards, 6)
        H.eq(wm.shardsCap, 60); H.eq(wm.bestStreak, 7); H.eq(wm.kills, 121); H.eq(wm.deaths, 96)
        -- WPZ 2j
        H.eq(zone.zoneId, 2817); H.eq(zone.kind, "F"); H.eq(zone.state, 1); H.eq(zone.secondsLeft, 4320)
        H.eq(zone.controlA, 620); H.eq(zone.controlH, 380); H.eq(zone.dominionTeam, "A"); H.eq(zone.dominionStacks, 2)
        H.eq(zone.levelMin, 80); H.eq(zone.levelMax, 80); H.eq(#zone.objectives, 3)
        H.eq(zone.objectives[1].name, "Violet Stand"); H.eq(zone.objectives[1].u, 512); H.eq(zone.objectives[1].v, 388)
        H.eq(zone.objectives[2].owner, "N"); H.eq(zone.byId[3].name, "Sunreaver Rise"); H.eq(zone.byId[3].slider, 800)
        -- WPCAP 2k
        H.eq(capture.objId, 2); H.eq(capture.slider, -120); H.eq(capture.neutralPct, 20); H.eq(capture.state, 6)
        H.eq(capture.countA, 2); H.eq(capture.countH, 3); H.eq(capture.maxNet, 5)
        -- WPMAP 2i
        H.eq(map.frontZone, 2817); H.eq(map.frontState, 1); H.eq(map.secondsLeft, 4320); H.eq(map.nextZone, 66)
        H.eq(map.nextStartsSec, 4920); H.eq(map.levelZone, 267); H.eq(map.levelState, 1)
        H.eq(map.levelSecondsLeft, 4320)
        H.eq(#map.zones, 4); H.eq(#map.points, 6)
        H.eq(map.zoneById[2817].heldA, 2); H.eq(map.zoneById[2817].neutral, 1); H.eq(map.zoneById[2817].levelMin, 80)
        H.eq(#map.zoneById[2817].points, 3); H.eq(map.zoneById[3483].kind, "S"); H.eq(map.zoneById[3483].levelMin, nil)
        H.eq(map.zoneById[4197].kind, "W"); H.eq(map.zoneById[4197].state, 0); H.eq(map.points[5].owner, "H")
        -- WANTED 2q, then the empty 2s, then another zone (2x) forgets the zone's Wanted players
        H.eq(wanted.zoneId, 2817); H.eq(#wanted.list, 1)
        local w = wanted.list[1]
        H.eq(w.name, "Garrick Stormwind"); H.eq(w.classId, 4); H.eq(w.team, "H"); H.eq(w.streak, 5); H.eq(w.reason, "S")
        H.eq(w.bountyHonor, 248); H.eq(w.bountyShards, 5); H.eq(w.u, 560); H.eq(w.v, 402); H.eq(w.ageSec, 35)
        H.eq(S.wanted, nil, "Dalaran: the Wanted list of Crystalsong is gone")
        -- WPEV: every kind, in the document's order
        H.eq(table.concat(events, ""), "XFACRWBSNER")
        H.eq(S.warEvent.kind, "R"); H.eq(S.warEvent.why, "V"); H.eq(S.warEvent.honor, 496); H.eq(S.warEvent.shards, 10)
        H.eq(S.warEvent.drPermille, 1000)
        -- WPZ 2x: Dalaran has no objectives, the Front display hides
        H.eq(S.wpZone.zoneId, 4395); H.eq(S.wpZone.kind, nil); H.eq(#S.wpZone.objectives, 0)
        H.ok(not WF.hud:IsShown(), "no HUD in Dalaran")
        H.ok(not WF.cap:IsShown(), "no capture bar in Dalaran")
        -- ERR 2z keeps the server's sentence (the seconds left)
        H.eq(S.err.op, "WARMODE"); H.eq(S.err.code, "wm_cooldown")
        H.eq(S.err.shown, "You can change War Mode again in 296 s.")
    end)
end

------------------------------------------------------------------------------------------------------
-- The War Mode page and the toggle
------------------------------------------------------------------------------------------------------
test("warmode: off at an inn, confirm, WARMODE 1; on, the cooldown greys the button; later WARMODE 0", function(M, ns)
    faction(M, "Alliance")
    resting(M, true)
    connect(M)
    wmst(M)
    ns.UI.Open("warmode")
    M.Advance(0.3)
    local P = ns.WarMode.page
    H.ok(P:IsVisible(), "War Mode page")
    H.eq(P.hero.title:GetText(), "War Mode is off")
    H.eq(P.toggle.label:GetText(), "Turn War Mode on")
    H.ok(P.toggle:IsEnabled(), "enabled at an inn")
    H.eq(P.bonus.rows[1].value:GetText(), "+10% honor")
    H.eq(P.bonus.rows[2].value:GetText(), "+8% for the Horde")
    H.ok(P.bonus.icon:IsShown(), "the underdog faction's icon")
    H.eq(P.bonus.rows[3].value:GetText(), "31 Alliance  -  22 Horde")
    H.eq(P.today.rows[1].value:GetText(), "0 / 3,720")
    H.eq(P.today.rows[4].value:GetText(), "118 / 96")
    -- the last row of Today keeps clear of the panel's bottom border, and the War Fronts table still fits under it
    local _, _, _, _, lastY = P.today.rows[5].label:GetPoint(1)
    H.ok(P.today:GetHeight() + lastY - 12 >= 16, "Today's last row has room above the border")
    local _, _, _, _, zoneY = P.fronts.zones[4][1]:GetPoint(1)
    H.ok(P.fronts:GetHeight() + zoneY - 12 >= 16, "the War Fronts table fits its panel")
    P.toggle:Click()
    local d = M.env.BleakholdDialog
    H.ok(d:IsShown(), "a confirmation first")
    H.contains(d.text:GetText(), "flagged for PvP everywhere except sanctuaries")
    H.eq(#intentsOf(M, "WARMODE"), 0, "nothing before the confirmation")
    d.ok:Click()
    M.Advance(0.3)
    H.eq(table.concat(intentsOf(M, "WARMODE"), " "), "1")
    H.eq(P.hero.reason:GetText(), "Waiting for the realm...")
    H.ok(not P.toggle:IsEnabled(), "busy until the server answers")
    wmst(M, { [1] = 1, [2] = 900 })
    M.Advance(0.3)
    H.eq(P.hero.title:GetText(), "War Mode is on")
    H.eq(P.toggle.label:GetText(), "Turn War Mode off")
    H.ok(not P.toggle:IsEnabled(), "on cooldown")
    H.eq(P.hero.reason:GetText(), "You can change War Mode again in 15 min.")
    H.eq(P.hero.status:GetText(), "You can change War Mode again in 15:00")
    M.Advance(300)
    P:Refresh()
    H.eq(P.hero.status:GetText(), "You can change War Mode again in 10:00", "counted down here")
    M.Advance(601)
    H.ok(P.toggle:IsEnabled(), "the cooldown is over")
    H.eq(P.hero.status:GetText(), "Flagged for PvP. Streak 0 kills")
    P.toggle:Click()
    H.contains(d.text:GetText(), "Turn War Mode off?")
    d.ok:Click()
    M.Advance(0.3)
    H.eq(table.concat(intentsOf(M, "WARMODE"), " "), "1 0")
end)

test("warmode: the button greys itself (place, combat, dead, level, busy, the server's block, Wanted)", function(M, ns)
    faction(M, "Horde")
    resting(M, true)
    connect(M)
    wmst(M)
    ns.UI.Open("warmode")
    M.Advance(0.3)
    local P, WM = ns.WarMode.page, ns.WarMode
    local function reason()
        P:Refresh()
        return P.hero.reason:GetText(), P.toggle:IsEnabled()
    end
    local r, on = reason()
    H.eq(r, ""); H.ok(on)
    resting(M, false)
    r, on = reason()
    H.eq(r, "War Mode can only be changed in an inn or a city."); H.ok(not on)
    resting(M, true)
    M.env.UnitAffectingCombat = function() return 1 end
    H.eq(reason(), "You cannot do that while in combat.")
    M.env.UnitAffectingCombat = function() return nil end
    M.env.UnitIsDeadOrGhost = function() return 1 end
    H.eq(reason(), "You cannot do that while dead.")
    M.env.UnitIsDeadOrGhost = function() return nil end
    M.playerLevel = 12
    H.eq(reason(), "You must be level 20 to use War Mode.")
    -- the level only refuses turning it on: on below the level (MinLevel raised since), the button turns it off
    wmst(M, { [1] = 1 })
    r, on = reason()
    H.eq(r, ""); H.ok(on, "War Mode on below the level: the button stays enabled")
    wmst(M)
    M.playerLevel = 80
    M.inInstance = true
    H.eq(reason(), "You cannot change War Mode from where you are now.")
    M.inInstance = false
    wmst(M, { [3] = "wm_hardcore" })
    H.eq(reason(), "Hardcore and Iron Man characters cannot use War Mode.", "the server's own block")
    wmst(M, { [1] = 1, [13] = 1, [14] = 840, [15] = 248 })
    r, on = reason()
    H.eq(r, "You are Wanted: War Mode stays on until the hunt ends."); H.ok(not on)
    -- the reason is right-aligned under the toggle, wide enough for this one on a line, clear of the description
    local A = ns.Activities
    H.eq(P.hero.reason:GetWidth(), 340)
    local _, rel, rp, rx = P.hero.reason:GetPoint(1)
    local tp, _, _, tx = P.toggle:GetPoint(1)
    H.ok(rel == P.toggle and rp == "BOTTOMRIGHT" and tp == "TOPRIGHT", "under the toggle, right-aligned")
    H.ok(A.CW + tx + rx - P.hero.reason:GetWidth() > A.PAD + A.DESC_W, "clear of the description")
    H.eq(P.hero.status:GetText(), "Wanted for a kill streak  -  14:00 left  -  bounty 248 honor")
    -- a grey button sends nothing; Toggle tells why in the error frame
    P.toggle:Click()
    H.eq(WM.Toggle(), false)
    H.ok(errorsShown(M, "You are Wanted") >= 1)
    H.eq(#intentsOf(M, "WARMODE"), 0)
    -- /bh warmode off asks the server anyway (it decides)
    M.env.SlashCmdList.BLEAKHOLD("warmode off")
    M.Advance(0.3)
    H.eq(table.concat(intentsOf(M, "WARMODE"), " "), "0")
end)

test("warmode: one WARMODE per 2 s, ERR busy waits a full gap, and every ERR code has its sentence", function(M, ns)
    resting(M, true)
    connect(M)
    wmst(M)
    local WM = ns.WarMode
    H.eq(WM.Request(true), true)
    H.eq(WM.Request(true), false, "within the client's gap")
    M.Advance(1)
    H.eq(WM.Request(false), false)
    M.Advance(1.2)
    H.eq(WM.Request(false), true, "after 2.1 s")
    H.send(M, "ERR", { { "WARMODE", ns.Comm.lastSeq, "busy", "Slow down." } })
    M.Advance(2)
    H.eq(WM.Request(true), false, "busy: a full gap from the ERR")
    M.Advance(0.2)
    H.eq(WM.Request(true), true)
    H.eq(table.concat(intentsOf(M, "WARMODE"), " "), "1 0 1")
    local texts = {
        wm_off = "War Mode is not available on this realm right now.",
        wm_level = "You must be level 20 to use War Mode.",
        wm_hardcore = "Hardcore and Iron Man characters cannot use War Mode.",
        wm_place = "War Mode can only be changed in an inn or a city.",
        wm_cooldown = "You can change War Mode again in 296 s.",
        wm_wanted = "You are Wanted: War Mode stays on until the hunt ends.",
        wm_busy = "You cannot change War Mode on a taxi.",
        dead = "You cannot do that while dead.",
        in_combat = "You cannot do that while in combat.",
        busy = "Slow down.",
    }
    local server = {
        wm_cooldown = "You can change War Mode again in 296 s.", wm_busy = "You cannot change War Mode on a taxi.",
        busy = "Slow down.", dead = "You cannot do that while dead.", in_combat = "You cannot do that while in combat.",
    }
    for code, want in pairs(texts) do
        H.send(M, "ERR", { { "WARMODE", "9", code, server[code] or "Server sentence." } })
        H.eq(ns.S.err.shown, want, code)
    end
    -- without a server sentence: the client's own
    H.send(M, "ERR", { { "WARMODE", "9", "wm_busy", "" } })
    H.eq(ns.S.err.shown, "You cannot change War Mode from where you are now.")
    H.send(M, "ERR", { { "WARMODE", "9", "in_combat", "" } })
    H.eq(ns.S.err.shown, "You cannot do that while in combat.")
    wmst(M, { [2] = 300 })
    H.send(M, "ERR", { { "WARMODE", "9", "wm_cooldown", "" } })
    H.eq(ns.S.err.shown, "You can change War Mode again in 5 min.")
    -- the page shows the last refusal under the button
    ns.UI.Open("warmode")
    M.Advance(0.3)
    H.eq(ns.WarMode.page.hero.reason:GetText(), "You can change War Mode again in 5 min.")
end)

------------------------------------------------------------------------------------------------------
-- The feature bits
------------------------------------------------------------------------------------------------------
test("features: nothing without bit 16384, and 32768 alone counts for nothing", function(M, ns)
    for _, bits in ipairs({ 0, WPVP }) do
        connect(M, bits)
        M.Advance(0.5)
        local WM = ns.WarMode
        H.ok(not WM.Live() and not WM.ObjectivesLive(), "bits " .. bits)
        H.ok(not M.env.BleakholdOrb_warmode:IsShown(), "no orb")
        ns.Activities.LayoutNav()
        for _, b in ipairs(ns.Activities.nav) do
            if b.key == "warmode" then H.ok(not b:IsShown(), "no War Mode in the rail") end
        end
        H.ok(not gets(M):find("WMST", 1, true), "no GET WMST")
        -- whatever arrives draws nothing
        wmst(M, { [1] = 1 })
        wpz(M)
        H.send(M, "WPCAP", { { 2, -120, 20, 6, 2, 3, 5 } })
        M.Advance(0.5)
        H.ok(not ns.WarFront.hud:IsShown() and not ns.WarFront.cap:IsShown(), "no HUD, no bar")
        H.eq(WM.Request(true), false)
        H.ok(errorsShown(M, "War Mode is not available") >= 1)
        M.env.SlashCmdList.BLEAKHOLD("warmode")
        H.ok(not ns.Activities.frame:IsShown(), "the page does not open")
        H.eq(#intentsOf(M, "WARMODE"), 0)
        ns.Comm.Reset()
        ns.ResetState()
    end
end)

test("features: 16384 alone has War Mode without objectives; both ask for everything; turned off, it is forgotten",
    function(M, ns)
    resting(M, true)
    connect(M, WAR)
    M.Advance(0.5)
    local WM, WF = ns.WarMode, ns.WarFront
    H.ok(WM.Live() and not WM.ObjectivesLive())
    H.ok(M.env.BleakholdOrb_warmode:IsShown(), "the orb")
    local g = gets(M)
    H.contains(g, "WMST")
    H.ok(not g:find("WPZ", 1, true) and not g:find("WPMAP", 1, true), "no objective topics: " .. g)
    wmst(M, { [1] = 1 })
    M.Advance(3.5)
    H.contains(gets(M), "WANTED", "War Mode on: the zone's Wanted players")
    wpz(M)
    M.Advance(0.5)
    H.ok(not WF.hud:IsShown(), "no HUD without bit 32768")
    ns.UI.Open("warmode")
    M.Advance(0.3)
    H.eq(WM.page.fronts.lines[1]:GetText(), "World PvP objectives are not open on this realm right now.")
    -- the realm turns the objectives on: a new HELLO
    H.hello(M, { [6] = BOTH })
    M.Advance(3.5)
    g = gets(M)
    H.contains(g, "WPZ"); H.contains(g, "WPMAP")
    wpz(M)
    M.Advance(0.3)
    H.ok(WF.hud:IsShown(), "the HUD with both bits")
    -- and turns War Mode off again: everything goes
    H.hello(M, { [6] = 0 })
    M.Advance(0.5)
    H.eq(ns.S.warMode, nil); H.eq(ns.S.wpZone, nil); H.eq(ns.S.wanted, nil)
    H.ok(not WF.hud:IsShown(), "HUD gone")
    H.ok(not M.env.BleakholdOrb_warmode:IsShown(), "orb gone")
    H.ok(not ns.WarMode.page:IsVisible() or ns.WarMode.page.hero.title:GetText() == "War Mode is not available")
end)

------------------------------------------------------------------------------------------------------
-- The Front HUD and the capture bar
------------------------------------------------------------------------------------------------------
test("hud: shown in a running Front, its pips, control, Dominion and countdown; hidden per kind and phase",
    function(M, ns)
    faction(M, "Alliance")
    connect(M)
    local WF, WM = ns.WarFront, ns.WarMode
    local hud = WF.hud
    wpz(M)
    M.Advance(0.3)
    H.ok(hud:IsShown())
    H.eq(hud.kicker:GetText(), "Bleak Front"); H.eq(hud.zone:GetText(), "Crystalsong Forest")
    H.eq(hud.time:GetText(), "1:12:00"); H.eq(hud.phase:GetText(), "left")
    H.ok(hud.pips[1]:IsShown() and hud.pips[3]:IsShown() and not hud.pips[4]:IsShown(), "three pips")
    local r, g, b = hud.pips[1]:GetVertexColor()
    local ar, ag, ab = ns.UI.Rgb(WM.TEAM.A.color)
    H.ok(near(r, ar) and near(g, ag) and near(b, ab), "Alliance blue")
    -- the contested pip pulses, the others do not
    local alphas = {}
    for i = 1, 5 do
        M.Advance(0.1)
        alphas[#alphas + 1] = hud.pips[2]:GetAlpha()
        H.eq(hud.pips[1]:GetAlpha(), 1)
    end
    local lo, hi = math.min(unpack(alphas)), math.max(unpack(alphas))
    H.ok(hi - lo > 0.1, "contested pip pulses")
    H.eq(hud.control.a:GetWidth(), 174); H.eq(hud.control.h:GetWidth(), 106)
    H.eq(hud.aText:GetText(), "62%"); H.eq(hud.hText:GetText(), "38%")
    H.eq(hud.note:GetText(), "Dominion x2")
    M.Advance(60)
    H.eq(hud.time:GetText(), "1:11:00", "counts down between heartbeats")
    wpz(M, { [8] = 3 }, { [2] = { [6] = "A", [7] = 400, [8] = 1 } })
    M.Advance(0.3)
    H.eq(hud.note:GetText(), "Dominion x3  -  Supremacy")
    wpz(M, { [3] = 2, [4] = 600, [5] = "", [6] = "", [7] = "", [8] = 0 })
    M.Advance(0.3)
    H.eq(hud.phase:GetText(), "Ceasefire"); H.eq(hud.time:GetText(), "10:00")
    H.ok(not hud.control.a:IsShown() and hud.aText:GetText() == "", "no points outside a running Front")
    H.eq(hud.note:GetText(), "Ceasefire: the outposts are frozen")
    wpz(M, { [3] = 0 })
    M.Advance(0.3)
    H.ok(not hud:IsShown(), "a dormant Front zone")
    wpz(M, { [1] = 3483, [2] = "S", [4] = 0, [5] = "", [6] = "", [9] = "", [10] = "" })
    M.Advance(0.3)
    H.ok(not hud:IsShown(), "stock zones keep their native world states")
    H.send(M, "WPZ", { { 4395 } })
    M.Advance(0.3)
    H.ok(not hud:IsShown(), "a zone without objectives")
    wpz(M, { [1] = 267, [2] = "L", [7] = "", [8] = 0, [9] = 20, [10] = 35 })
    M.Advance(0.3)
    H.ok(hud:IsShown())
    H.eq(hud.kicker:GetText(), "Levelling Front"); H.eq(hud.zone:GetText(), "Hillsbrad Foothills")
    H.eq(hud.note:GetText(), "Only levels 20-35 can capture here", "a level 80 out of the band")
end)

test("capture bar: marker, neutral band, direction and counts; gone with objId 0, when stale, in stock zones",
    function(M, ns)
    connect(M)
    local WF = ns.WarFront
    local cap = WF.cap
    wpz(M)
    H.send(M, "WPCAP", { { 2, -120, 20, 6, 2, 3, 5 } })
    M.Advance(0.3)
    H.ok(cap:IsShown())
    H.eq(cap.name:GetText(), "Forlorn Woods")
    H.eq(cap.markerX, 14); H.eq(cap.bar.n:GetWidth(), 48, "20% of each half is neutral")
    H.eq(cap.net, -1); H.ok(cap.arrow:IsShown()); H.eq(select(1, cap.arrow:GetPoint(1)), "LEFT", "towards the Horde")
    H.eq(cap.countA:GetText(), "2"); H.eq(cap.countH:GetText(), "3")
    H.eq(cap.state:GetText(), "The Horde's: the Alliance is taking it")
    H.eq(ns.S.wpZone.byId[2].slider, -120)
    H.send(M, "WPCAP", { { 2, 260, 20, 1, 4, 1, 5 } })
    M.Advance(0.3)
    H.eq(cap.markerX, -31); H.eq(cap.net, 3); H.eq(select(1, cap.arrow:GetPoint(1)), "RIGHT", "towards the Alliance")
    H.eq(ns.S.wpZone.byId[2].owner, "A", "the pip follows the bar")
    H.send(M, "WPCAP", { { 2, 1000, 20, 1, 9, 0, 5 } })
    M.Advance(0.3)
    H.eq(cap.markerX, -120, "Alliance full: the left end"); H.eq(cap.net, 5, "at most maxNet")
    H.send(M, "WPCAP", { { 2, 1000, 20, 1, 3, 3, 5 } })
    M.Advance(0.3)
    H.ok(not cap.arrow:IsShown(), "even: the bar stands still")
    H.send(M, "WPCAP", { { 0 } })
    M.Advance(0.3)
    H.ok(not cap:IsShown(), "left the outpost")
    H.send(M, "WPCAP", { { 2, 0, 20, 0, 1, 0, 5 } })
    M.Advance(0.3)
    H.ok(cap:IsShown())
    M.Advance(4)
    H.ok(not cap:IsShown(), "no WPCAP for a few seconds: gone")
    wpz(M, { [2] = "S" })
    H.send(M, "WPCAP", { { 2, 0, 20, 0, 1, 0, 5 } })
    M.Advance(0.3)
    H.ok(not cap:IsShown(), "stock zones have their native bar")
end)

------------------------------------------------------------------------------------------------------
-- The world map and the minimap
------------------------------------------------------------------------------------------------------
test("map: pins for the outposts and the Wanted players only while the map shows the player's zone", function(M, ns)
    faction(M, "Alliance")
    connect(M)
    wmst(M, { [1] = 1 })
    local WF = ns.WarFront
    wpz(M, nil, { [3] = { [4] = "", [5] = "" } })
    H.send(M, "WANTED", { { 2817 }, { "W", "Garrick Stormwind", 4, "H", 5, "B", 248, 5, 560, 402, 35 },
        { "W", "Br\195\169nna", 8, "H", 9, "S", 446, 9, "", "", 10 } })
    M.Advance(0.3)
    H.eq(WF.myArea, 511, "learnt while the map was closed")
    local map = M.env.WorldMapFrame
    M.mapArea = 300    -- the player looked at another map last
    map:Show()
    M.FireEvent("WORLD_MAP_UPDATE")
    H.ok(not WF.mapLayer:IsShown(), "another map: no pins")
    M.mapArea = 511
    M.FireEvent("WORLD_MAP_UPDATE")
    H.ok(WF.mapLayer:IsShown(), "the player's zone")
    local pin = WF.objPins[1]
    H.ok(pin:IsShown() and WF.objPins[2]:IsShown())
    H.ok(not WF.objPins[3] or not WF.objPins[3]:IsShown(), "no pin without a position")
    local point, rel, relPoint, x, y = pin:GetPoint(1)
    H.eq(point, "CENTER"); H.eq(relPoint, "TOPLEFT")
    H.ok(near(x, 512 / 1000 * 1002) and near(y, -388 / 1000 * 668), "u, v on the map: " .. x .. ", " .. y)
    H.eq(pin.lines[1], "Violet Stand"); H.eq(pin.lines[2][1], "Held by the Alliance")
    local wp = WF.wantedPins[1]
    H.ok(wp:IsShown())
    local _, _, _, wx, wy = wp:GetPoint(1)
    H.ok(near(wx, 560 / 1000 * 1002) and near(wy, -402 / 1000 * 668))
    H.eq(wp.lines[1], "WANTED: Garrick Stormwind"); H.eq(wp.lines[2][1], "A bully")
    H.eq(wp.lines[3][1], "Bounty: 248 honor, 5 Shards")
    -- the tooltips use the world map's own tooltip: the full-size map hides UIParent, and GameTooltip with it
    M.Fire(pin, "OnEnter")
    H.ok(M.env.WorldMapTooltip:IsShown(), "WorldMapTooltip shown")
    H.eq(M.env.WorldMapTooltip.__lines[1], "Violet Stand")
    H.eq(M.env.WorldMapTooltip.__owner, pin)
    H.ok(not M.env.GameTooltip:IsShown(), "GameTooltip is not used on the map")
    M.Fire(pin, "OnLeave")
    H.ok(not M.env.WorldMapTooltip:IsShown())
    M.Fire(wp, "OnEnter")
    H.eq(M.env.WorldMapTooltip.__lines[1], "WANTED: Garrick Stormwind")
    M.Fire(wp, "OnLeave")
    H.ok(not M.env.WorldMapTooltip:IsShown() and not M.env.GameTooltip:IsShown())
    -- the ones without a position are listed
    H.ok(WF.mapList:IsShown())
    H.contains(WF.mapList.lines[1]:GetText(), "Sunreaver Rise")
    H.contains(WF.mapList.lines[2]:GetText(), "Br\195\169nna")
    -- the Wanted list goes stale, then empties
    M.Advance(17)
    M.FireEvent("WORLD_MAP_UPDATE")
    H.ok(not wp:IsShown(), "no WANTED for 16 s: no pins")
    -- the map was turned while open: learn the zone's map again once it closes
    map:Hide()
    M.myArea = 520
    M.FireEvent("ZONE_CHANGED_NEW_AREA")
    H.eq(WF.myArea, 520)
    map:Show()
    M.FireEvent("ZONE_CHANGED_NEW_AREA")
    H.eq(WF.myArea, nil, "never turns the map the player looks at")
    map:Hide()
    H.eq(WF.myArea, 520, "learnt once it closed")
end, withMap())

test("map: Wanted pins in plain zones while World PvP is live (a kind-less WPZ is not refreshed)", function(M, ns)
    faction(M, "Alliance")
    connect(M)   -- 16384 and 32768
    wmst(M, { [1] = 1 })
    local WF = ns.WarFront
    H.send(M, "WPZ", { { 1519 } })   -- the login zone, Stormwind: no objectives
    M.Advance(0.3)
    H.eq(ns.S.wpZone.zoneId, 1519); H.eq(ns.S.wpZone.kind, nil)
    -- into Elwynn Forest: the server sends no WPZ between two zones without objectives
    M.FireEvent("ZONE_CHANGED_NEW_AREA")
    H.send(M, "WANTED", { { 10 }, { "W", "Garrick Stormwind", 4, "H", 5, "S", 248, 5, 560, 402, 35 } })
    M.Advance(0.3)
    local w = WF.WantedNow()
    H.ok(w ~= nil, "the Wanted list of the zone the player is in now")
    H.eq(w and w.zoneId, 10)
    H.eq(w and #w.list, 1)
    -- a WPZ of a zone with objectives still says where the player is: another zone's WANTED is not shown there
    wpz(M)
    M.Advance(0.3)
    H.send(M, "WANTED", { { 10 }, { "W", "Garrick Stormwind", 4, "H", 5, "S", 248, 5, 560, 402, 35 } })
    M.Advance(0.3)
    H.eq(WF.WantedNow(), nil, "in Crystalsong, Elwynn's list is not the zone's")
end, withMap())

test("minimap: arrows to the player's faction's outposts under attack", function(M, ns)
    faction(M, "Alliance")
    connect(M)
    local WF = ns.WarFront
    M.px, M.py = 0.5, 0.5
    wpz(M, nil, { [3] = { [8] = 5 } })    -- Sunreaver Rise: the Alliance's, the Horde pushing
    M.Advance(0.3)
    local a = WF.arrows[1]
    H.ok(a:IsShown(), "an arrow")
    H.eq(a.objId, 3)
    local _, rel, _, x, y = a:GetPoint(1)
    H.eq(rel, M.env.Minimap)
    H.ok(x > 55 and y < 0 and y > -5, "east, a little south: " .. x .. ", " .. y)
    H.ok(not WF.arrows[2]:IsShown())
    H.send(M, "WPEV", { { "A", 2817, 1, "H", "Violet Stand" } })
    M.Advance(0.3)
    H.ok(WF.arrows[2]:IsShown() and WF.arrows[2].objId == 1 or WF.arrows[1].objId == 1, "attacked: a second arrow")
    -- standing at it: no arrow for that one
    H.send(M, "WPCAP", { { 3, 400, 20, 5, 1, 2, 5 } })
    M.Advance(0.3)
    local ids = {}
    for _, ar in ipairs(WF.arrows) do if ar:IsShown() then ids[#ids + 1] = ar.objId end end
    H.eq(table.concat(ids, ","), "1")
    M.Advance(61)
    H.ok(not WF.arrows[1]:IsShown() or WF.arrows[1].objId ~= 1, "an attack counts for a minute")
    -- the rotating minimap turns the arrows with the player
    M.cvars.rotateMinimap = "1"
    M.env.GetPlayerFacing = function() return math.pi / 2 end
    H.ok(near(WF.MinimapAngle(1, 0), 0 - math.pi / 2, 0.001), "east while facing west: down")
    -- for the Horde: Forlorn Woods, the Horde's last, with the Alliance pushing its bar (state 6)
    faction(M, "Horde")
    M.cvars.rotateMinimap = "0"
    M.Advance(0.3)
    ids = {}
    for _, ar in ipairs(WF.arrows) do if ar:IsShown() then ids[#ids + 1] = ar.objId end end
    H.eq(table.concat(ids, ","), "2")
end, withMap())

------------------------------------------------------------------------------------------------------
-- Banners, toasts, the reward line, the orb
------------------------------------------------------------------------------------------------------
test("events: banners for outposts and Wanted players, toasts for Fronts, the reward line", function(M, ns)
    faction(M, "Alliance")
    connect(M)
    local WF = ns.WarFront
    local banner = WF.banner
    local function ev(rec)
        H.send(M, "WPEV", { rec })
        M.Advance(0.3)
    end
    ev({ "C", 2817, 2, "A", "Forlorn Woods" })
    H.ok(banner:IsShown())
    H.eq(banner.kicker:GetText(), "Forlorn Woods"); H.eq(banner.title:GetText(), "CAPTURED")
    H.eq(banner.sub:GetText(), "by the Alliance")
    ev({ "W", "Garrick Stormwind", 4, "H", 5, "B" })
    M.Advance(3)
    H.eq(banner.title:GetText(), "WANTED: BULLY"); H.contains(banner.kicker:GetText(), "Garrick Stormwind")
    H.eq(banner.sub:GetText(), "Killed a player far below their level")
    H.ok(#M.sounds > 0 and M.sounds[#M.sounds] == "RaidWarning")
    ev({ "W", "Tester", 1, "A", 6, "S" })
    M.Advance(3)
    H.eq(banner.title:GetText(), "YOU ARE WANTED")
    ev({ "B", "Aldric", "Garrick Stormwind", 248, 5 })
    M.Advance(3)
    H.eq(banner.title:GetText(), "BOUNTY CLAIMED")
    H.eq(banner.kicker:GetText(), "Aldric claimed the bounty on Garrick Stormwind")
    H.eq(banner.sub:GetText(), "248 honor, 5 Shards")
    ev({ "S", "Br\195\169nna", 248, 5 })
    M.Advance(3)
    H.eq(banner.title:GetText(), "SURVIVED THE HUNT")
    M.Advance(4)
    H.ok(not banner:IsShown(), "one at a time, then gone")
    -- Fronts: toasts that open the War Mode page
    local toast = M.env.BleakholdToastFrame
    ev({ "F", 2817, 7200, "Crystalsong Forest" })
    H.eq(toast.kicker:GetText(), "War Front"); H.eq(toast.title:GetText(), "Crystalsong Forest: the Front has begun")
    H.eq(toast.sub:GetText(), "It lasts 2 h 0 min. Capture and hold its outposts.")
    toast:Click()
    H.ok(ns.Activities.frame:IsShown() and ns.Activities.current == "warmode", "the toast opens War Mode")
    ev({ "E", 2817, "", 500, 500 })
    M.Advance(5.5)
    H.eq(toast.title:GetText(), "Crystalsong Forest: a draw"); H.eq(toast.sub:GetText(), "Alliance 50%  -  Horde 50%")
    ev({ "X", 66, 900, "Zul'Drak" })
    M.Advance(5.5)
    H.eq(toast.title:GetText(), "A Front starts in 15 min"); H.eq(ns.WarZoneName(66), "Zul'Drak")
    -- the reward line: under the HUD in a Front, in chat elsewhere
    wpz(M)
    ev({ "R", "C", 186, 0, 2, 1000 })
    H.eq(WF.hud.reward:GetText(), "+186 Honor, +2 Shards - a capture")
    ev({ "R", "K", 93, 1200, 0, 750 })
    H.eq(WF.hud.reward:GetText(), "+93 Honor, +1,200 XP - a kill (75%)")
    M.Advance(7)
    H.eq(WF.hud.reward:GetText(), "", "gone after a few seconds")
    H.send(M, "WPZ", { { 4395 } })
    local chats = #M.chat
    ev({ "R", "V", 496, 0, 10, 1000 })
    H.ok(#M.chat > chats and M.chat[#M.chat].msg:find("+496 Honor, +10 Shards - the War Chest", 1, true), "printed")
end)

test("orb: red while War Mode is on, pulsing while Wanted; its tooltip; a click opens the page", function(M, ns)
    resting(M, true)
    connect(M)
    wmst(M)
    M.Advance(0.5)
    local orb = M.env.BleakholdOrb_warmode
    H.ok(orb:IsShown())
    wmst(M, { [1] = 1 })
    M.Advance(0.5)
    local r, g = orb.ring:GetVertexColor()
    local wr, wg = ns.UI.Rgb(ns.WarMode.COLOR)
    H.ok(near(r, wr) and near(g, wg), "red ring")
    H.eq(orb.ring:GetAlpha(), 1)
    wmst(M, { [1] = 1, [13] = 2, [14] = 600 })
    local alphas = {}
    for i = 1, 6 do
        M.Advance(0.25)
        alphas[i] = orb.ring:GetAlpha()
    end
    H.ok(math.max(unpack(alphas)) - math.min(unpack(alphas)) > 0.1, "Wanted: pulsing")
    M.Fire(orb, "OnEnter")
    local text = table.concat(M.env.GameTooltip.__lines, "\n")
    H.contains(text, "On: flagged for PvP"); H.contains(text, "Wanted as a bully: 9:5")
    M.Fire(orb, "OnLeave")
    orb:Click()
    H.ok(ns.Activities.frame:IsShown() and ns.Activities.current == "warmode")
    orb:Click()
    H.ok(not ns.Activities.frame:IsShown(), "a second click closes it")
end)

test("page: the Fronts of WPMAP with their countdowns, Dominion where the player is", function(M, ns)
    faction(M, "Alliance")
    connect(M)
    wmst(M, { [1] = 1 })
    H.send(M, "WPMAP", { { 2817, 1, 4320, 66, 4920, 267, 2, 300 }, { "Z", 2817, "F", 2, 0, 1, 80, 80, 1 },
        { "Z", 267, "L", 1, 1, 1, 20, 35, 2 }, { "Z", 3483, "S", 2, 1, 0, "", "", 1 } })
    wpz(M)
    ns.UI.Open("warmode")
    M.Advance(0.3)
    local F = ns.WarMode.page.fronts
    H.eq(F.lines[1]:GetText(), "Bleak Front: Crystalsong Forest  -  1:12:00 left")
    H.eq(F.lines[2]:GetText(), "Next: Zul'Drak in 1 h 22 min")
    H.eq(F.lines[3]:GetText(), "Levelling Front: Hillsbrad Foothills  -  ceasefire 5:00")
    H.eq(F.zones[1][1]:GetText(), "Crystalsong Forest", "running zones first, by id")
    H.eq(F.zones[1][2]:GetText(), "Bleak Front"); H.eq(F.zones[1][4]:GetText(), "Level 80")
    H.eq(F.zones[2][1]:GetText(), "Hellfire Peninsula"); H.eq(F.zones[2][4]:GetText(), "")
    H.eq(F.zones[3][1]:GetText(), "Hillsbrad Foothills"); H.eq(F.zones[3][4]:GetText(), "Levels 20-35")
    H.eq(F.zones[3][5]:GetText(), "Ceasefire")
    H.eq(ns.WarMode.page.bonus.rows[4].value:GetText(), "x2  Crystalsong Forest")
    M.Advance(10)
    ns.WarMode.page:Refresh()
    H.eq(F.lines[1]:GetText(), "Bleak Front: Crystalsong Forest  -  1:11:50 left", "counts down")
    H.send(M, "WPMAP", { { 0, 0, 0, 0, 0, 0, 0, 0 } })
    M.Advance(1.1)
    H.eq(F.lines[1]:GetText(), "Bleak Front: none at this level cap")
end)

------------------------------------------------------------------------------------------------------
-- Garbage and the demo
------------------------------------------------------------------------------------------------------
local GARBAGE = { "", "nan", "-1", "99999999999999999999", "1e308", "%ZZ", "%00", "abc", "%7C%7Ccff00ff00evil%7Cr",
    "\255\254", string.rep("A", 300), "~~~", "-0", "F", "W", "O", "Z", "P", "A", "H", "N", "S", "B", "R", "7", "-1000",
    "1001" }

test("garbage in every section 19 op with both features on, the map open and the page shown", function(M, ns)
    faction(M, "Alliance")
    connect(M)
    M.px, M.py = 0.4, 0.6
    ns.UI.Open("warmode")
    M.env.WorldMapFrame:Show()
    local seed = 4242
    local function pick()
        seed = (seed * 1103515245 + 12345) % 2147483648
        return GARBAGE[seed % #GARBAGE + 1]
    end
    for round = 1, 30 do
        for _, op in ipairs({ "WMST", "WPZ", "WPCAP", "WPMAP", "WANTED", "WPEV", "ERR" }) do
            local recs = {}
            for i = 1, 1 + round % 5 do
                local r = {}
                for k = 1, 24 do r[k] = pick() end
                recs[i] = table.concat(r, ",")
            end
            for _, f in ipairs(H.frames(op, table.concat(recs, ";"), 400)) do H.deliver(M, f) end
        end
        M.Advance(0.3)
        M.FireEvent("WORLD_MAP_UPDATE")
        ns.WarMode.page:Refresh()
    end
    -- and valid states with the longest lists
    local big = { { 2817, "F", 1, 4320, 620, 380, "A", 9, 1, 255 } }
    for i = 1, 30 do big[#big + 1] = { "O", i, string.rep("N", 60), i * 30, i * 30, "H", -1000, 6 } end
    H.send(M, "WPZ", big)
    H.eq(#ns.S.wpZone.objectives, 16, "at most 16 outposts")
    H.eq(#ns.S.wpZone.objectives[1].name, 40, "names cut at 40 bytes")
    local wanted = { { 2817 } }
    for i = 1, 12 do wanted[#wanted + 1] = { "W", "N" .. i, 4, "H", i, "S", 1, 1, 10 * i, 10 * i, 1 } end
    H.send(M, "WANTED", wanted)
    H.eq(#ns.S.wanted.list, 8, "at most 8 Wanted players")
    -- the map was open since before the zone was known: its pins come once it was closed and opened again
    M.env.WorldMapFrame:Hide()
    M.env.WorldMapFrame:Show()
    M.Advance(0.6)
    M.FireEvent("WORLD_MAP_UPDATE")
    local shown = 0
    for _, p in ipairs(ns.WarFront.objPins) do if p:IsShown() then shown = shown + 1 end end
    H.eq(shown, 16)
end, withMap())

test("demo: War Mode on, a Front, a capture, a Wanted player and the bounty", function(M, ns)
    local before = #M.sent
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    ns.UI.Open("warmode")
    M.Advance(0.5)
    local P = ns.WarMode.page
    H.eq(P.hero.title:GetText(), "War Mode is off")
    H.ok(P.toggle:IsEnabled(), "the demo's server decides")
    local events = {}
    ns.On("WAR_EVENT", function(e) events[#events + 1] = e.kind end)
    P.toggle:Click()
    M.env.BleakholdDialog.ok:Click()
    M.Advance(1)
    H.eq(ns.S.warMode.on, true)
    M.Advance(30)
    H.eq(table.concat(events, ""), "XFCRWB")
    local dropped = 0
    for _, v in pairs(ns.Comm.stats.dropped) do dropped = dropped + v end
    H.eq(dropped, 0); H.eq(ns.Comm.stats.unknown, 0)
    H.eq(ns.S.wpZone.dominionStacks, 3)
    H.eq(#M.sent, before, "nothing reached the server")
end)
