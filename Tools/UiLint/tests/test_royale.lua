-- Bleakhold Royale (docs/BleakholdProtocol.md section 17): the protocol document's frames through State and the HUD at
-- the frame sizes the server may use, the Royale card and its gates (feature bit 4096, the patch marker), the ready
-- check, the island map's transform and the landing pin, the parachute, the spectator camera, the storm (timer,
-- circle, screen edge, safe-zone arrow), the kill feed and the announcer, the end card, the drop countdown, the
-- player's own position, garbage, and a whole scripted match in /bh demo.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local ROYALE = { [6] = 4096 }
local MARKER = "Interface\\Bleakhold\\Royale\\Marker"
local MAP = {
    { 901, -1066, 533, -1066, 533, 455, 455, 32, 750, -267, -267 }, { 1, "L", -266, -266, 88, "The Bleak Hold" },
    { 2, "L", 120, 80, 62, "Harrow Farm" }, { 11, "C", -80, -710, 16, "Old Ford" },
    { 14, "Y", 455, 455, 32, "The Overlook" },
}

local function connect(M, extra)
    local bits = { [6] = 4096 }
    for k, v in pairs(extra or {}) do bits[k] = v end
    FX.connect(M, H, bits)
end

-- A ROYS: the lobby before the countdown, unless `over` says otherwise (field index -> value).
local function roys(M, over)
    local r = { 7001, 0, 60000, 24, 24, 0, 0, "", "", "", 0, -267, -267, 1080, "", "", "", "", "", 0, "", 450, 452 }
    for k, v in pairs(over or {}) do r[k] = v end
    H.send(M, "ROYS", { r })
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

-- Click the island map at pixel (px, py) from its top-left corner.
local function clickMap(M, ns, px, py)
    local canvas = ns.RoyaleMap.canvas
    local s = canvas:GetEffectiveScale()
    M.cursorX = (canvas:GetLeft() + px) * s
    M.cursorY = (canvas:GetTop() - py) * s
    M.Fire(canvas, "OnMouseUp", "LeftButton")
end

-- Section 17's S> example frames: { op, payload }.
local function docExamples()
    local text = assert(host_readfile(repo .. "/docs/BleakholdProtocol.md"))
    local sec = assert(text:match("\n## 17%. Bleakhold Royale(.*)$"), "section 17")
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
    test("doc section 17 frames at max body " .. size .. " reach State and the HUD", function(M, ns)
        connect(M)
        local S, R = ns.S, ns.Royale
        local C = ns.Comm
        local examples = docExamples()
        H.ok(#examples >= 12, "section 17 examples: " .. #examples)
        local seq, proposals, kills, results, events = 500, 0, {}, 0, {}
        ns.On("QUEUE_PROPOSAL", function() proposals = proposals + 1 end)
        ns.On("ROYALE_KILL", function(k) kills[#kills + 1] = k end)
        ns.On("ROYALE_RESULT", function() results = results + 1 end)
        ns.On("ROYALE_EVENT", function(e) events[#events + 1] = e.kind end)
        local framesIn = C.stats.framesIn
        local sent = 0
        for _, ex in ipairs(examples) do
            seq = seq + 1
            local frames = assert(C.BuildFrames(ex.op, seq, ex.payload, size))
            for _, body in ipairs(frames) do
                H.ok(#body <= size, "frame within " .. size .. " bytes")
                H.deliver(M, body)
                sent = sent + 1
            end
            if ex.op == "QUEUE" and ex.payload:match("^5,") then
                -- the ready check: the popup, the counts
                H.ok(M.env.BleakholdRoyaleReady:IsShown(), "ready check popup")
                H.eq(R.ready.count:GetText(), "0 / 24 accepted")
                H.eq(R.ready.ring.label:GetText(), "15")
            end
            M.Advance(0.1)
        end
        if size == 64 then
            H.ok(sent > #examples, "frames were chunked: " .. sent)
        end
        local drops = 0
        for _, v in pairs(C.stats.dropped) do drops = drops + v end
        H.eq(drops, 0, "no frame dropped")
        H.eq(C.stats.unknown, 0, "every op has a handler")
        H.eq(C.stats.framesIn - framesIn, sent)
        H.eq(C.PendingChunks(), 0)
        -- QUEUE kind B (the last one, h: in a match)
        local q = S.queue
        H.eq(q.kind, "B"); H.eq(q.state, 3); H.eq(q.activityId, 901); H.eq(q.size, 1)
        H.eq(q.minPlayers, 20); H.eq(q.maxPlayers, 40); H.eq(q.matchesRunning, 2); H.eq(q.queued, nil)
        H.eq(#q.members, 0, "no members for Royale")
        H.eq(proposals, 1)
        H.ok(not M.env.BleakholdRoyaleReady:IsShown(), "the popup goes with the proposal")
        -- ROYM
        local map = S.royaleMap
        H.eq(map.mapId, 901); H.eq(map.minX, -1066); H.eq(map.maxX, 533); H.eq(map.minY, -1066); H.eq(map.maxY, 533)
        H.eq(map.lobbyX, 455); H.eq(map.lobbyR, 32); H.eq(map.boundHalf, 750); H.eq(map.centerX, -267)
        H.eq(#map.pois, 2); H.eq(map.pois[1].name, "The Bleak Hold"); H.eq(map.pois[2].kind, "L");
        H.eq(map.pois[2].x, 120)
        -- ROYS k (the snapped pin)
        local m = S.royale
        H.eq(m.matchId, 7001); H.eq(m.phase, 1); H.eq(m.alive, 23, "from ROYK aliveAfter"); H.eq(m.total, 24);
        H.eq(m.me, 0)
        H.eq(m.pinX, 104); H.eq(m.pinY, 96); H.eq(m.stage, 0); H.eq(m.curR, 1080); H.eq(m.nextR, nil)
        H.eq(m.myX, 450); H.eq(m.myY, 452); H.eq(m.placement, nil); H.eq(m.watchName, nil)
        -- ROYO l
        local o = S.royaleObjects
        H.eq(o.matchId, 7001); H.eq(#o.list, 3)
        H.eq(o.byId[1].kind, "S"); H.eq(o.byId[1].state, 0); H.eq(o.byId[1].msLeft, 90000)
        H.eq(o.byId[3].kind, "B"); H.eq(o.byId[3].subtype, 1); H.eq(o.byId[3].state, 1); H.eq(o.byId[3].msLeft, nil)
        -- ROYK n
        H.eq(#kills, 1)
        local k = kills[1]
        H.eq(k.killer, "Aldric"); H.eq(k.killerClassId, 1); H.eq(k.victim, "Brenna"); H.eq(k.victimClassId, 8)
        H.eq(k.cause, "P"); H.eq(k.aliveAfter, 23); H.eq(k.killerKills, 1); H.eq(k.announce, "F")
        H.eq(S.royaleKills.Aldric, 1)
        -- ROYV m and p
        H.eq(table.concat(events, ""), "DW")
        H.eq(S.royaleEvent.kind, "W"); H.eq(S.royaleEvent.value, 7); H.eq(S.royaleEvent.name, "Dalia")
        -- ROYE o
        H.eq(results, 1)
        local res = S.royaleResult
        H.eq(res.matchId, 7001); H.eq(res.placement, 12); H.eq(res.total, 24); H.eq(res.kills, 1);
        H.eq(res.damage, 18400)
        H.eq(res.healing, 0); H.eq(res.survivedSec, 214); H.eq(res.rewarded, true); H.eq(res.winnerName, nil)
        H.eq(#res.rewards, 3)
        H.eq(res.rewards[1].line, "70 Honor - Placement")
        H.eq(res.rewards[2].line, "25 Honor - 1 elimination")
        H.eq(res.rewards[3].line, "5 Shards - Placement")
        -- ERR q
        H.eq(S.err.code, "glide_here"); H.eq(S.err.shown, "You cannot glide here.")
        -- the HUD
        M.Advance(0.3)
        local bar = M.env.BleakholdRoyaleBar
        H.ok(bar:IsShown(), "top bar")
        H.contains(bar.main:GetText(), "Drop in 0:4", "drop countdown")
        H.eq(bar.alive:GetText(), "24", "players in the lobby")
        H.ok(M.env.BleakholdRoyaleMapFrame:IsShown(), "the map opens in the lobby")
        H.ok(ns.RoyaleMap.pins.pin:IsShown(), "the snapped pin on the map")
        H.ok(M.env.BleakholdRoyaleResult:IsShown(), "end card")
        H.eq(ns.RoyaleHud.result.place:GetText(), "#12 of 24")
        H.ok(M.env.BleakholdRoyaleFeed:IsShown(), "kill feed")
        H.contains(ns.RoyaleHud.feed.lines[1].killer:GetText(), "Aldric")
        H.contains(ns.RoyaleHud.feed.lines[1].victim:GetText(), "Brenna")
        H.eq(ns.RoyaleHud.banner.title:GetText(), "FIRST BLOOD")
    end)
end

------------------------------------------------------------------------------------------------------
-- The queue: the Royale card, its gates, the ready check
------------------------------------------------------------------------------------------------------
test("royale: the card shows the queue counts and queues with QJOIN B,901,0,4,1; Leave sends QLEAVE", function(M, ns)
    connect(M)
    ns.UI.Open("royale")
    M.Advance(0.3)
    local P = ns.Royale.page
    H.ok(P:IsVisible(), "Royale page")
    H.eq(P.hero.facts:GetText(), "Solo · Level 80 · 20-40 players")
    H.eq(P.join:GetText() or P.join.label:GetText(), "Queue")
    H.ok(P.join:IsEnabled(), "Queue enabled")
    P.join:Click()
    M.Advance(0.3)
    H.eq(table.concat(intentsOf(M, "QJOIN"), " "), "B,901,0,4,1")
    H.send(M, "QUEUE", { { 4, 1, "B", 901, 0, 1, 12, "", "", "", 80, 80, 13, 20, 40, "", "", 1 } })
    M.Advance(0.6)
    H.eq(P.hero.status:GetText(), "13 / 20 queued")
    H.contains(P.hero.detail:GetText(), "1 match running")
    H.contains(P.hero.detail:GetText(), "Waiting 00:1")
    H.eq(P.join.label:GetText(), "Leave queue")
    M.Advance(1.2)
    P.join:Click()
    M.Advance(0.3)
    H.eq(#intentsOf(M, "QLEAVE"), 1)
    -- the activities orb and the Dungeons page name it too
    local lines = {}
    M.env.BleakholdOrb_activities:GetScript("OnEnter")(M.env.BleakholdOrb_activities)
    for _, l in ipairs(M.env.GameTooltip.__lines or {}) do lines[#lines + 1] = l end
    H.contains(table.concat(lines, "|"), "Bleakhold Royale queue")
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    H.eq(ns.Dungeons.queue.status:GetText(), "In queue: Bleakhold Royale")
end)

test("royale: the nav entry and the orb follow feature bit 4096", function(M, ns)
    FX.connect(M, H)
    local nav
    for _, b in ipairs(ns.Activities.nav) do
        if b.key == "royale" then nav = b end
    end
    H.ok(nav and not nav:IsShown(), "no Royale entry without the bit")
    H.ok(not M.env.BleakholdOrb_royale:IsShown(), "no orb without the bit")
    ns.UI.Open("royale")
    M.Advance(0.3)
    H.ok(not ns.Royale.page.join:IsEnabled(), "Queue disabled")
    H.eq(ns.Royale.page.hero.notice:GetText(), "Bleakhold Royale is not open on this realm.")
    local before = #M.sent
    ns.Royale.Join()
    M.Advance(0.3)
    H.eq(#M.sent, before, "no QJOIN")
    -- the server turns the mode on at runtime: a new HELLO
    H.hello(M, ROYALE)
    M.Advance(0.3)
    H.ok(nav:IsShown(), "Royale entry with the bit")
    H.ok(M.env.BleakholdOrb_royale:IsShown(), "orb with the bit")
    H.eq(select(5, nav:GetPoint(1)), -12 - 3 * 66, "after Rift, before Tasks")
end)

test("royale: without the patch marker the card is disabled and QJOIN is never sent", function(M, ns)
    connect(M)
    ns.UI.Open("royale")
    M.Advance(0.3)
    local P = ns.Royale.page
    H.ok(not P.join:IsEnabled(), "Queue disabled")
    H.eq(P.hero.notice:GetText(), "Install the latest client patch")
    local before = #M.sent
    ns.Royale.Join()
    M.env.SlashCmdList.BLEAKHOLD("royale")
    M.Advance(1)
    H.eq(#M.sent, before, "nothing sent")
    H.ok(errorsShown(M, "Install the latest client patch") >= 1, "the reason in the error frame")
    H.ok(M.textures[MARKER], "the marker was tested")
end, { before = function(M)
    M.missingTextures[MARKER] = true
end })

test("royale: the ready check popup accepts and declines with QREPLY, and goes when its time is up", function(M, ns)
    connect(M)
    local sounds = #M.sounds
    H.send(M, "QUEUE", { { 5, 2, "B", 901, 0, 1, 95, "", 412, 15, 80, 80, 24, 20, 40, 0, 24, 1 } })
    local rc = M.env.BleakholdRoyaleReady
    H.ok(rc:IsShown(), "popup")
    H.eq(M.sounds[sounds + 1], "PVPTHROUGHQUEUE", "the queue pop sound")
    H.eq(ns.Toast.Pending(), 0, "no dungeon group toast for Royale")
    rc.accept:Click()
    M.Advance(0.3)
    H.eq(table.concat(intentsOf(M, "QREPLY"), " "), "412,1")
    H.ok(rc.waiting:IsShown() and not rc.accept:IsShown(), "waiting for the others")
    H.send(M, "QUEUE", { { 6, 2, "B", 901, 0, 1, 96, "", 412, 14, 80, 80, 24, 20, 40, 9, 24, 1 } })
    M.Advance(0.3)
    H.eq(rc.count:GetText(), "9 / 24 accepted")
    -- a new proposal: decline
    H.send(M, "QUEUE", { { 7, 1, "B", 901, 0, 1, 100, "", "", "", 80, 80, 20, 20, 40, "", "", 1 } })
    H.ok(not rc:IsShown(), "gone with the proposal")
    M.Advance(1.2)
    H.send(M, "QUEUE", { { 8, 2, "B", 901, 0, 1, 110, "", 413, 15, 80, 80, 24, 20, 40, 0, 24, 1 } })
    H.ok(rc:IsShown())
    rc.decline:Click()
    M.Advance(0.3)
    H.eq(table.concat(intentsOf(M, "QREPLY"), " "), "412,1 413,0")
    H.ok(not rc:IsShown(), "hidden after declining")
    -- no answer: the popup goes when the time is up
    M.Advance(1.2)
    H.send(M, "QUEUE", { { 9, 2, "B", 901, 0, 1, 120, "", 414, 3, 80, 80, 24, 20, 40, 0, 24, 1 } })
    H.ok(rc:IsShown())
    M.Advance(3.5)
    H.ok(not rc:IsShown(), "timed out")
end)

------------------------------------------------------------------------------------------------------
-- The lobby: the map, the landing pin, the countdown
------------------------------------------------------------------------------------------------------
test("royale: the map turns a click into RDROP through ROYM's frame, negative yards included", function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    roys(M)
    M.Advance(0.3)
    local mp = ns.RoyaleMap
    H.ok(M.env.BleakholdRoyaleMapFrame:IsShown(), "opened by itself in the lobby")
    -- the transform: u = (maxY - y) / (maxY - minY), v = (maxX - x) / (maxX - minX)
    local px, py = mp.ToMap(-266, -266)
    H.ok(math.abs(px - 512 * 799 / 1599) < 0.01 and math.abs(py - 512 * 799 / 1599) < 0.01, "the keep near the middle")
    local x, y = mp.ToWorld(512, 0)
    H.eq(x, 533); H.eq(y, -1066)
    clickMap(M, ns, 100, 200)
    M.Advance(0.1)
    H.eq(table.concat(intentsOf(M, "RDROP"), " "), "-92,221", "x from the row, y from the column")
    H.ok(mp.pins.pending:IsShown(), "the wish shows until the server answers")
    -- three quick clicks: the first waits for the gate, only the last goes out
    clickMap(M, ns, 400, 450)
    clickMap(M, ns, 300, 300)
    clickMap(M, ns, 256, 256)
    M.Advance(0.2)
    H.eq(#intentsOf(M, "RDROP"), 1, "within the 0.5 s gate")
    M.Advance(0.5)
    H.eq(table.concat(intentsOf(M, "RDROP"), " "), "-92,221 -266,-266", "the last wish after the gate")
    -- the server's snapped pin replaces the wish
    roys(M, { [9] = -260, [10] = -270 })
    M.Advance(0.2)
    H.ok(not mp.pins.pending:IsShown() and mp.pins.pin:IsShown(), "the snapped pin")
    -- the same pin again within the duplicate window is not sent
    M.Advance(0.6)
    clickMap(M, ns, 256, 256)
    M.Advance(0.2)
    H.eq(#intentsOf(M, "RDROP"), 2, "same pin within 1 s: not sent")
    -- a click on a place's marker sets the pin there too
    M.Advance(1)
    local poi = mp.pois.items[2]
    H.eq(poi.poi.name, "Harrow Farm")
    local px2, py2 = mp.ToMap(120, 80)
    local canvas = mp.canvas
    M.cursorX = (canvas:GetLeft() + px2) * canvas:GetEffectiveScale()
    M.cursorY = (canvas:GetTop() - py2) * canvas:GetEffectiveScale()
    M.Fire(poi, "OnMouseUp", "LeftButton")
    M.Advance(0.2)
    local last = intentsOf(M, "RDROP")
    H.eq(last[#last], "120,80", "the farm")
end)

test("royale: pins lock 3 s before the drop; the drop closes the map; the last 10 s count down in the centre",
function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    roys(M, { [2] = 1, [3] = 15000 })
    M.Advance(0.3)
    local bar = M.env.BleakholdRoyaleBar
    H.eq(bar.main:GetText(), "Drop in 0:15")
    M.Advance(2)
    H.eq(bar.sub:GetText(), "Pins lock in 10")
    H.ok(not M.env.BleakholdCountdown:IsShown(), "no centre countdown yet")
    M.Advance(3.5)
    H.ok(M.env.BleakholdCountdown:IsShown(), "the drop countdown")
    H.eq(ns.Countdown.frame.kicker:GetText(), ns.RoyaleHud.KICKER)
    H.eq(ns.Countdown.frame.title:GetText(), "The drop")
    M.Advance(6.6)
    H.eq(bar.sub:GetText(), "Pins are locked")
    local before = #intentsOf(M, "RDROP")
    clickMap(M, ns, 100, 100)
    M.Advance(0.2)
    H.eq(#intentsOf(M, "RDROP"), before, "no RDROP after the lock")
    H.ok(errorsShown(M, "You cannot do that now.") >= 1, "royale_phase sentence")
    for _, s in ipairs(M.sent) do
        H.ok(s.prefix ~= "DBMv4-PT", "no DBM pull timer for the drop")
    end
    roys(M, { [2] = 2, [3] = 5000, [6] = 1 })
    M.Advance(0.3)
    H.ok(not M.env.BleakholdCountdown:IsShown(), "countdown gone at the drop")
    H.ok(not M.env.BleakholdRoyaleMapFrame:IsShown(), "the map closes at the drop")
end)

test("royale: RDEPLOY from the binding only while falling, once, 0.5 s into the fall", function(M, ns)
    connect(M)
    roys(M, { [2] = 2, [3] = 5000 })
    M.env.BleakholdRoyaleDeploy()
    M.Advance(0.2)
    H.eq(#intentsOf(M, "RDEPLOY"), 0, "not falling: nothing")
    roys(M, { [2] = 2, [3] = 5000, [6] = 1 })
    M.Advance(0.2)
    local dp = M.env.BleakholdRoyaleParachute
    H.ok(dp:IsShown(), "prompt while falling")
    H.contains(dp.key:GetText(), "Click here")
    M.env.BleakholdRoyaleDeploy()
    M.Advance(0.1)
    H.eq(#intentsOf(M, "RDEPLOY"), 0, "too early in the fall")
    M.Advance(0.4)
    M.env.SetBinding("F", "BLEAKHOLD_ROYALE_DEPLOY")
    M.Advance(0.2)
    H.contains(dp.key:GetText(), "Press F")
    M.env.BleakholdRoyaleDeploy()
    M.Advance(0.2)
    H.eq(table.concat(intentsOf(M, "RDEPLOY"), "|"), "", "RDEPLOY has no fields")
    H.eq(#intentsOf(M, "RDEPLOY"), 1)
    H.ok(not dp:IsShown(), "prompt gone")
    M.Advance(1.2)
    M.env.BleakholdRoyaleDeploy()
    M.Advance(0.2)
    H.eq(#intentsOf(M, "RDEPLOY"), 1, "once per drop")
end)

------------------------------------------------------------------------------------------------------
-- The fight: storm, feed, announcer
------------------------------------------------------------------------------------------------------
test("royale: the storm timer counts down, the circle moves, the screen edge and the safe-zone arrow show outside",
function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    local R = ns.Royale
    -- stage 2: cur (-267,-267) r 320, next (-200,-300) r 180, moves in 10 s for 20 s; the player outside
    roys(M, { [2] = 3, [3] = 0, [6] = 2, [11] = 2, [14] = 320, [15] = -200, [16] = -300, [17] = 180, [18] = 10000,
        [19] = 30000, [20] = 20, [22] = 300, [23] = -267 })
    M.Advance(0.3)
    local bar = M.env.BleakholdRoyaleBar
    H.eq(bar.main:GetText(), "Storm moves in 0:10")
    H.eq(bar.sub:GetText(), "Outside the storm circle: 2.0% of your health per second")
    local pips = 0
    for _, p in ipairs(bar.pips) do
        local r = p:GetVertexColor()
        if p:IsShown() and math.abs(r - 0xB5 / 255) < 0.01 then pips = pips + 1 end
    end
    H.eq(pips, 2, "two stage pips lit")
    H.ok(M.env.BleakholdRoyaleVignette:IsShown(), "purple screen edge outside")
    local ea = M.env.BleakholdRoyaleSafeArrow
    H.ok(ea:IsShown(), "arrow to the safe zone")
    H.eq(ea.dist:GetText(), "322 yd")
    local _, _, _, ax, ay = ea:GetPoint(1)
    H.ok(ay < -40 and math.abs(ax) < 10, "south on a north-up minimap: " .. ax .. "," .. ay)
    M.Advance(10)
    H.contains(bar.main:GetText(), "Storm moving 0:2")
    M.Advance(9.7)
    local x, y, r, moving = R.Circle()
    H.ok(moving, "moving")
    H.ok(math.abs(r - 250) < 2 and math.abs(x - (-233.5)) < 1 and math.abs(y - (-283.5)) < 1, "halfway: " .. r)
    -- inside both circles: no edge, no arrow
    roys(M, { [2] = 3, [3] = 0, [6] = 2, [11] = 2, [14] = 320, [15] = -200, [16] = -300, [17] = 180, [18] = 10000,
        [19] = 30000, [20] = 20, [22] = -267, [23] = -267 })
    M.Advance(0.3)
    H.ok(not M.env.BleakholdRoyaleVignette:IsShown(), "inside: no edge")
    H.ok(not ea:IsShown(), "inside the next circle: no arrow")
    H.ok(not bar.sub:GetText():find("Outside", 1, true))
    -- a spectator sees neither
    roys(M, { [2] = 3, [6] = 3, [14] = 10, [22] = 300, [23] = -267 })
    M.Advance(0.3)
    H.ok(not M.env.BleakholdRoyaleVignette:IsShown() and not ea:IsShown(), "spectators take no storm")
end)

test("royale: the kill feed keeps five lines for 8 s; banners take turns; only the highest waiting line is voiced",
function(M, ns)
    connect(M)
    roys(M, { [2] = 3, [6] = 2 })
    local played = {}
    M.env.PlaySoundFile = function(path) played[#played + 1] = path end
    local Hud = ns.RoyaleHud
    H.send(M, "ROYK", { { "Aldric", 1, "Brenna", 8, "P", 23, 1, "F" } })
    M.Advance(0.2)
    H.eq(played[1], "Interface\\AddOns\\Bleakhold\\Sounds\\Royale\\male\\firstblood.wav")
    H.eq(Hud.banner.title:GetText(), "FIRST BLOOD")
    H.contains(Hud.banner.kicker:GetText(), "Aldric")
    H.send(M, "ROYK", { { "Corwin", 5, "Dalia", 11, "P", 22, 2, "D" } })
    H.send(M, "ROYK", { { "Eamon", 9, "Fenna", 3, "P", 21, 2, "D" } })
    H.send(M, "ROYK", { { "Corwin", 5, "Garrick", 4, "P", 20, 3, "T" } })
    H.send(M, "ROYK", { { "Corwin", 5, "Hesper", 6, "S", 19, 6, "G" } })
    H.send(M, "ROYK", { { "", "", "Ivo", 2, "L", 18, "", "" } })
    M.Advance(0.2)
    H.eq(#played, 1, "the first line still plays")
    H.eq(#Hud.queue, 3, "one waiting banner per line: D, T, G")
    H.contains(Hud.queue[1].kicker, "Eamon", "the newer double kill replaced the older one")
    M.Advance(2.4)
    H.eq(played[2], "Interface\\AddOns\\Bleakhold\\Sounds\\Royale\\male\\godlike.wav", "only the highest waiting line")
    H.eq(Hud.banner.title:GetText(), "DOUBLE KILL", "banners in order, 2.5 s each")
    M.Advance(2.5)
    H.eq(Hud.banner.title:GetText(), "TRIPLE KILL")
    M.Advance(2.5)
    H.eq(Hud.banner.title:GetText(), "GODLIKE")
    H.eq(#played, 2, "D and T were never voiced")
    -- the feed: newest first, five lines, the forfeit says so
    local feed = Hud.feed
    H.ok(feed:IsShown())
    H.contains(feed.lines[1].victim:GetText(), "Ivo|r (left)")
    H.eq(feed.lines[1].killer:GetText(), "")
    H.contains(feed.lines[2].victim:GetText(), "Hesper")
    H.ok(feed.lines[5]:IsShown() and feed.lines[5].victim:GetText():find("Dalia", 1, true), "five lines")
    H.eq(ns.S.royale.alive, 18, "alive from aliveAfter")
    H.eq(ns.Royale.KillsOf("Corwin"), 6)
    M.Advance(1.5)
    roys(M, { [2] = 3, [6] = 2 })
    M.Advance(0.5)
    H.ok(not feed:IsShown(), "faded after 8 s")
    -- the voice setting: female, quiet; off is silent
    ns.db.options.royaleVoice = "female"
    ns.db.options.royaleQuiet = true
    M.Advance(3)
    H.send(M, "ROYK", { { "Aldric", 1, "Jory", 7, "P", 17, 4, "M" } })
    M.Advance(0.2)
    H.eq(played[#played], "Interface\\AddOns\\Bleakhold\\Sounds\\Royale\\female_quiet\\monsterkill.wav")
    ns.db.options.royaleVoice = "off"
    M.Advance(3)
    local n = #played
    H.send(M, "ROYK", { { "Aldric", 1, "Kell", 7, "P", 16, 5, "R" } })
    M.Advance(0.2)
    H.eq(#played, n, "voice off")
    H.eq(Hud.banner.title:GetText(), "RAMPAGE", "the banner still shows")
end)

test("royale: no announcement without a credited killer, for a forfeit or an AFK elimination", function(M, ns)
    connect(M)
    roys(M, { [2] = 3, [6] = 2 })
    local played = {}
    M.env.PlaySoundFile = function(path) played[#played + 1] = path end
    H.send(M, "ROYK", { { "", "", "Brenna", 8, "S", 23, "", "F" } })
    H.send(M, "ROYK", { { "Aldric", 1, "Corwin", 5, "L", 22, 1, "F" } })
    H.send(M, "ROYK", { { "Aldric", 1, "Dalia", 11, "A", 21, 1, "D" } })
    H.send(M, "ROYK", { { "Aldric", 1, "Eamon", 9, "P", 20, 1, "X" } })
    M.Advance(0.3)
    H.eq(#played, 0, "silent")
    H.ok(not ns.RoyaleHud.banner:IsShown(), "no banner")
    for _, k in ipairs(ns.S.royaleFeed) do
        H.eq(k.announce, nil)
    end
end)

test("royale: milestones, the circle and the winner get banners", function(M, ns)
    connect(M)
    roys(M, { [2] = 3, [6] = 2 })
    H.send(M, "ROYV", { { "N", 10, "", "", "", "" } })
    M.Advance(0.2)
    H.eq(ns.RoyaleHud.banner.title:GetText(), "10 PLAYERS LEFT")
    H.send(M, "ROYV", { { "W", 7, "", "", "", "Dalia" } })
    M.Advance(2.6)
    H.eq(ns.RoyaleHud.banner.title:GetText(), "VICTORY")
    H.contains(ns.RoyaleHud.banner.kicker:GetText(), "Dalia - 7 eliminations")
    -- a kill line cuts a showing event banner short and goes before the waiting ones, so it shows with its voice
    M.Advance(3)
    H.send(M, "ROYV", { { "D", 0, -80, -180, 20000, "" } })
    H.send(M, "ROYV", { { "S", 2, "", "", "", "" } })
    M.Advance(0.2)
    H.eq(ns.RoyaleHud.banner.title:GetText(), "SUPPLY DROP")
    H.send(M, "ROYK", { { "Aldric", 1, "Brenna", 8, "P", 23, 1, "F" } })
    M.Advance(0.2)
    H.eq(ns.RoyaleHud.banner.title:GetText(), "FIRST BLOOD")
    M.Advance(2.5)
    H.eq(ns.RoyaleHud.banner.title:GetText(), "THE STORM IS MOVING", "the waiting event after the kill")
end)

------------------------------------------------------------------------------------------------------
-- Spectating and the end
------------------------------------------------------------------------------------------------------
test("royale: the spectator bar sends RSPEC 0/2/1, queues again and leaves", function(M, ns)
    connect(M)
    local left = 0
    M.env.LeaveBattlefield = function() left = left + 1 end
    roys(M, { [2] = 3, [6] = 2 })
    H.send(M, "ROYK", { { "Aldric Stormwind", 1, "Tester", 1, "P", 11, 3, "T" } })
    roys(M, { [2] = 3, [6] = 3, [8] = 12, [21] = "Aldric Stormwind", [22] = "", [23] = "" })
    M.Advance(0.3)
    local sb = M.env.BleakholdRoyaleSpectate
    H.ok(sb:IsShown(), "spectator bar")
    H.eq(sb.name:GetText(), "Watching Aldric Stormwind (3 kills)")
    sb.killer:Click()
    M.Advance(0.6)
    sb.prev:Click()
    M.Advance(0.6)
    sb.next:Click()
    sb.next:Click()
    M.Advance(0.6)
    sb.next:Click()
    M.Advance(0.3)
    H.eq(table.concat(intentsOf(M, "RSPEC"), " "), "0 2 1 1", "the second quick Next waits for the gate")
    sb.requeue:Click()
    M.Advance(0.3)
    H.eq(table.concat(intentsOf(M, "QJOIN"), " "), "B,901,0,4,1")
    sb.leave:Click()
    H.eq(left, 1, "a spectator leaves without a question")
    -- an alive player confirms first (a forfeit)
    roys(M, { [2] = 3, [6] = 2 })
    ns.Royale.LeaveMatch()
    local d = M.env.BleakholdDialog
    H.ok(d:IsShown(), "confirm")
    H.contains(d.text:GetText(), "forfeit")
    d.ok:Click()
    H.eq(left, 2)
    -- RSPEC from a non-spectator is refused locally
    local n = #intentsOf(M, "RSPEC")
    M.Advance(1)
    ns.Royale.Spectate(1)
    M.Advance(0.3)
    H.eq(#intentsOf(M, "RSPEC"), n)
end)

test("royale: the end card shows the placement, the stats and the rewards; the winner's says #1 VICTORY",
function(M, ns)
    connect(M)
    roys(M, { [2] = 3, [6] = 3 })
    H.send(M, "ROYE", { { 7001, 7, 32, 2, 18400, 2100, 214, "", "", "", 1 }, { "H", 180, "", "Placement" },
        { "H", 50, "", "2 eliminations" }, { "S", 20, "", "Placement" } })
    M.Advance(0.2)
    local ec = M.env.BleakholdRoyaleResult
    H.ok(ec:IsShown())
    H.eq(ec.place:GetText(), "#7 of 32")
    H.eq(ec.rows[1].value:GetText(), "2"); H.eq(ec.rows[2].value:GetText(), "18,400");
    H.eq(ec.rows[3].value:GetText(), "2,100")
    H.eq(ec.rows[4].value:GetText(), "03:34")
    H.eq(ec.rewards[1]:GetText(), "+ 180 Honor - Placement")
    H.eq(ec.rewards[3]:GetText(), "+ 20 Shards - Placement")
    H.eq(ec.keep.label:GetText(), "Keep watching")
    -- the server sends it again at the end with the winner
    H.send(M, "ROYE", { { 7001, 7, 32, 2, 18400, 2100, 214, "Dalia", 11, 7, 1 }, { "H", 180, "", "Placement" } })
    M.Advance(0.2)
    H.eq(ec.winner:GetText(), "Winner: Dalia (7 eliminations)")
    ec.keep:Click()
    H.ok(not ec:IsShown(), "dismissed")
    H.send(M, "ROYE", { { 7001, 7, 32, 2, 18400, 2100, 214, "Dalia", 11, 7, 1 } })
    M.Advance(0.2)
    H.ok(not ec:IsShown(), "stays dismissed for this match")
    -- not rewarded: no reward lines even if some were sent
    roys(M, { [1] = 7002, [2] = 6, [6] = 5 })
    H.send(M, "ROYE", { { 7002, 1, 20, 9, 50000, 0, 700, "Tester", 1, 9, 0 }, { "H", 400, "", "Placement" } })
    M.Advance(0.2)
    H.ok(ec:IsShown())
    H.eq(ec.place:GetText(), "#1 VICTORY")
    H.eq(#ns.S.royaleResult.rewards, 0)
    H.eq(ec.rewardsLabel:GetText(), "NO REWARDS")
    H.eq(ec.keep.label:GetText(), "Close")
    -- the Activities card remembers it
    ns.UI.Open("royale")
    M.Advance(0.3)
    H.eq(ns.Royale.page.last.place:GetText(), "#1 Victory")
    H.eq(M.env.BleakholdCharDB.royaleLast.placement, 1)
end)

test("royale: leaving the battleground forgets the match; no ROYS for 25 s hides the HUD", function(M, ns)
    connect(M)
    M.inInstance, M.instanceType = true, "pvp"
    H.send(M, "ROYM", MAP)
    roys(M, { [2] = 3, [6] = 2 })
    M.Advance(0.3)
    H.ok(M.env.BleakholdRoyaleBar:IsShown())
    M.Advance(26)
    H.ok(not M.env.BleakholdRoyaleBar:IsShown(), "stale: hidden")
    roys(M, { [2] = 3, [6] = 2 })
    M.Advance(0.3)
    H.ok(M.env.BleakholdRoyaleBar:IsShown(), "back with a fresh ROYS")
    M.inInstance, M.instanceType = false, "none"
    M.FireEvent("PLAYER_ENTERING_WORLD")
    M.Advance(0.3)
    H.eq(ns.S.royale, nil, "forgotten")
    H.ok(not M.env.BleakholdRoyaleBar:IsShown())
    H.ok(not M.env.BleakholdRoyaleMapFrame:IsShown())
end)

test("royale: after a /reload in a battleground, HELLO brings GET ROYS;ROYM (not elsewhere)", function(M, ns)
    connect(M)
    M.Advance(1)
    H.ok(not gets(M):find("ROYS", 1, true), "not in a battleground: no GET ROYS")
end)

test("royale: GET ROYS;ROYM after HELLO inside a battleground", function(M, ns)
    M.inInstance, M.instanceType = true, "pvp"
    connect(M)
    M.Advance(1)
    H.contains(gets(M), "ROYS", "GET ROYS")
    H.contains(gets(M), "ROYM", "GET ROYM")
end)

------------------------------------------------------------------------------------------------------
-- The player's own position
------------------------------------------------------------------------------------------------------
test("royale: own position from GetPlayerMapPosition through MapForge's WorldMapArea; myX/myY when they disagree",
function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    local R = ns.Royale
    -- MapForge's frame: Y widened to 1002:668 around the tiles (left 932.75, right -1465.75, top 533, bottom -1066)
    local l, r, t, b = R.WorldMapBounds(ns.S.royaleMap)
    H.ok(math.abs(l - 932.75) < 1e-6 and math.abs(r + 1465.75) < 1e-6 and t == 533 and b == -1066, "bounds")
    local px, py = (l - 96) / (l - r), (t - 104) / (t - b)
    M.env.GetMapInfo = function() return "BleakholdRoyale" end
    M.env.GetPlayerMapPosition = function() return px, py end
    M.env.GetPlayerFacing = function() return math.pi / 2 end
    roys(M, { [2] = 3, [6] = 2, [22] = 104, [23] = 96 })
    local x, y, own = R.MyPos()
    H.ok(own and math.abs(x - 104) < 0.01 and math.abs(y - 96) < 0.01, "the client's own position")
    ns.UI.Open("royalemap")
    M.Advance(0.3)
    local arrow = ns.RoyaleMap.arrow
    H.ok(arrow:IsShown(), "own arrow")
    -- another map on the world map: SetMapToCurrentZone, then ours again
    local set = 0
    local file = "Elwynn"
    M.env.GetMapInfo = function() return file end
    M.env.SetMapToCurrentZone = function() set = set + 1; file = "BleakholdRoyale" end
    M.Advance(0.1)        -- one answer per frame time
    x = R.MyPos()
    H.eq(set, 1, "back to the current zone")
    H.ok(math.abs(x - 104) < 0.01)
    -- the server disagrees twice by more than 40 yd: its position from now on
    roys(M, { [2] = 3, [6] = 2, [22] = 300, [23] = 300 })
    roys(M, { [2] = 3, [6] = 2, [22] = 300, [23] = 300 })
    x, y, own = R.MyPos()
    H.eq(own, false, "server position")
    H.eq(x, 300)
end)

test("royale: a client without the map's WorldMapArea stops asking for the current zone after three tries",
function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    local set = 0
    M.env.GetMapInfo = function() return "Elwynn" end
    M.env.SetMapToCurrentZone = function() set = set + 1 end
    M.env.GetPlayerMapPosition = function() return 0.5, 0.5 end
    roys(M, { [2] = 3, [6] = 2, [22] = 104, [23] = 96 })
    M.Advance(2)
    H.eq(set, 3, "three tries")
    local x, _, own = ns.Royale.MyPos()
    H.eq(own, false)
    H.eq(x, 104, "the server's position")
end)

------------------------------------------------------------------------------------------------------
-- Robustness and the rest of the protocol surface
------------------------------------------------------------------------------------------------------
test("royale: unknown enums, broken frames, deltas without a full list and long names", function(M, ns)
    connect(M)
    local S = ns.S
    roys(M, { [2] = 3, [6] = 2 })
    roys(M, { [2] = 9, [6] = 77 })
    H.eq(S.royale.phase, 3, "an unknown phase keeps the last one")
    H.eq(S.royale.me, 2, "an unknown me keeps the last one")
    roys(M, { [9] = 104, [10] = "" })
    H.eq(S.royale.pinX, nil, "half a pin is no pin")
    -- ROYM without a usable frame is ignored
    H.send(M, "ROYM", { { 901, 533, -1066, -1066, 533 } })
    H.eq(S.royaleMap, nil)
    -- a delta for objects never listed in full: applied, and the full list asked for
    M.Advance(3.5)
    H.send(M, "ROYO", { { 7001, 0 }, { 20, "D", 0, -80, -180, 3, 20000 }, { 21, "Q", 0, 0, 0, 1 } })
    M.Advance(0.3)
    H.eq(#S.royaleObjects.list, 1, "unknown kinds dropped")
    H.contains(gets(M), "ROYS", "GET ROYS for the full list")
    -- at most 64 objects
    local recs = { { 7001, 1 } }
    for i = 1, 80 do recs[#recs + 1] = { i, "B", i % 4, i, -i, 1, "" } end
    H.send(M, "ROYO", recs)
    H.eq(#S.royaleObjects.list, 64)
    -- names: at most 48 bytes, no escape codes
    local long = string.rep("A", 60)
    H.send(M, "ROYK", { { long, 1, "|cffff0000Evil|r", 8, "P", 23, 1, "" } })
    H.eq(#S.royaleFeed[1].killer, 48)
    M.Advance(0.2)
    H.contains(ns.RoyaleHud.feed.lines[1].victim:GetText(), "||cffff0000Evil||r", "pipes doubled")
    -- another match id: the old feed, objects and events go
    roys(M, { [1] = 7002, [2] = 0 })
    H.eq(#S.royaleFeed, 0)
    H.eq(S.royaleObjects, nil)
end)

test("royale: reward kind H, the [Royale] chat tag and the TOAST target royale", function(M, ns)
    connect(M)
    H.eq(ns.RewardText("H", 70), "70 Honor")
    H.eq(ns.RewardText("H", 1250), "1,250 Honor")
    local line = "[Royale] Dalia won Bleakhold Royale (7 eliminations, 24 players)"
    local out = M.FilterChat("CHAT_MSG_SYSTEM", M.env.ChatFrame1, line)
    H.eq(out, "|cffB98CFF[Royale]|r Dalia won Bleakhold Royale (7 eliminations, 24 players)")
    H.send(M, "TOAST", { { "Q", "Bleakhold Royale", "24 players are ready", "royale" } })
    M.env.BleakholdToastFrame:Click()
    M.Advance(0.3)
    H.ok(M.env.BleakholdActivitiesFrame:IsShown() and ns.Activities.current == "royale",
        "the toast opens the Royale page")
    H.eq(ns.Comm.FEATURE.ROYALE, 4096)
end)

test("royale: the intents' encoder takes only valid Royale fields", function(M, ns)
    local C = ns.Comm
    H.eq(C.EncodeIntent("QJOIN", "B", 901, 0, 4, 1), "B,901,0,4,1")
    H.eq(C.EncodeIntent("QJOIN", "B", 0, 0, 4, 1), nil, "activity 0")
    H.eq(C.EncodeIntent("QJOIN", "B", 901, 1, 4, 1), nil, "tier 1")
    H.eq(C.EncodeIntent("QJOIN", "B", 901, 0, 4, 5), nil, "size 5")
    H.eq(C.EncodeIntent("RDROP", -17067, 17067), "-17067,17067")
    H.eq(C.EncodeIntent("RDROP", -17068, 0), nil)
    H.eq(C.EncodeIntent("RDROP", 1.5, 0), nil)
    H.eq(C.EncodeIntent("RDROP", 1), nil, "two fields")
    H.eq(C.EncodeIntent("RDEPLOY"), "")
    H.eq(C.EncodeIntent("RDEPLOY", 1), nil)
    H.eq(C.EncodeIntent("RSPEC", 2), "2")
    H.eq(C.EncodeIntent("RSPEC", 3), nil)
    H.eq(C.EncodeIntent("GET", { "ROYS" }, { "ROYM" }), "ROYS;ROYM")
end)

test("royale: the movers preview the bar, the feed and the spectator bar", function(M, ns)
    connect(M)
    local movers = {}
    for _, m in ipairs(ns.Movers) do movers[m.name] = m end
    for _, name in ipairs({ "bleakhold_royale_bar", "bleakhold_royale_feed", "bleakhold_royale_spectate" }) do
        local mv = H.ok(movers[name], name)
        H.ok(mv.visible(), name .. " visible with the bit")
        mv.begin()
        H.ok(mv.frame:IsShown(), name .. " sample shown")
        mv.finish()
        H.ok(not mv.frame:IsShown(), name .. " hidden again")
    end
end)

test("royale: /bh demo plays a whole match through the real receive path", function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    ns.UI.Open("royale")
    M.Advance(0.3)
    local P = ns.Royale.page
    H.ok(P.join:IsEnabled(), "demo has the mode on")
    P.join:Click()
    M.Advance(3.5)
    H.ok(M.env.BleakholdRoyaleReady:IsShown(), "ready check")
    M.env.BleakholdRoyaleReady.accept:Click()
    M.Advance(2)
    H.ok(M.env.BleakholdRoyaleMapFrame:IsShown(), "the island map in the lobby")
    clickMap(M, ns, 250, 260)
    M.Advance(1)
    H.ok(ns.S.royale.pinX ~= nil, "the demo echoed the pin")
    for _ = 1, 90 do
        M.Advance(1)
    end
    local dropped = 0
    for _, v in pairs(ns.Comm.stats.dropped) do dropped = dropped + v end
    H.eq(dropped, 0)
    H.eq(ns.Comm.stats.unknown, 0)
    H.eq(ns.S.royaleResult.placement, 9)
    H.eq(ns.S.royaleResult.winnerName, "Dalia")
    H.eq(ns.S.royale.phase, 6)
    M.env.SlashCmdList.BLEAKHOLD("demo off")
    M.Advance(0.5)
    H.ok(not M.env.BleakholdRoyaleBar:IsShown(), "demo off: the HUD goes")
end)
