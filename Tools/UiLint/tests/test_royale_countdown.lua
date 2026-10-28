-- Bleakhold Royale's drop countdown (RoyaleCountdown.lua): nothing before 15 s, one numeral a second in three tiers
-- with their sounds, caps and rings, one clock on screen, the client's pin lock at T-3.6 with the silent map close
-- and the glide to the centre, DROP! with the gong (or DROP! at once when the server drops first), a cancelled match,
-- corrections that jump without restarting, the circle banner folded into the countdown in the lobby, docking beside
-- the island map on 16:9, 4:3 and 5:4 (centred when it does not fit), reduced motion, late arrivals, and the texel
-- ratio of every texture the countdown shows.
local MAP = {
    { 901, -1066, 533, -1066, 533, 455, 455, 32, 750, -267, -267 }, { 1, "L", -266, -266, 88, "The Bleak Hold" },
    { 2, "L", 120, 80, 62, "Harrow Farm" }, { 11, "C", -80, -710, 16, "Old Ford" },
    { 14, "Y", 455, 455, 32, "The Overlook" },
}
local ROYALE_ART = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\"

local function near(a, b, eps, msg)
    if type(a) ~= "number" or math.abs(a - b) > (eps or 1e-6) then
        error((msg or "values differ") .. ": expected " .. tostring(b) .. ", got " .. tostring(a), 2)
    end
end

local function connect(M)
    H.hello(M, { [6] = 4096 })
    M.Advance(0.3)
end

-- A ROYS in the lobby (phase 1 unless `over` says otherwise; field index -> value).
local function roys(M, over)
    local r = { 7001, 1, 30000, 24, 24, 0, 0, "", "", "", 0, -267, -267, 860, "", "", "", "", "", 0, "", 450, 452 }
    for k, v in pairs(over or {}) do r[k] = v end
    H.send(M, "ROYS", { r })
end

-- The exact ROYS of T-15: circle 1 revealed, the pin at Harrow Farm.
local function reveal(M, over)
    local o = { [3] = 15000, [9] = 120, [10] = 80, [15] = -150, [16] = -310, [17] = 520 }
    for k, v in pairs(over or {}) do o[k] = v end
    roys(M, o)
end

-- Names of the Sounds\Royale files played (the _quiet copies too), in order.
local function royaleSounds(M)
    local out = {}
    for _, p in ipairs(M.soundFiles) do
        local name = p:match("Sounds\\Royale\\(%w+)")
        if name then out[#out + 1] = name end
    end
    return out
end

local function count(list, v)
    local n = 0
    for _, x in ipairs(list) do
        if x == v then n = n + 1 end
    end
    return n
end

-- Clock-like texts (M:SS) shown in the top bar.
local function barClocks(M)
    local found = {}
    local function walk(f)
        for _, r in ipairs({ f:GetRegions() }) do
            if r:IsObjectType("FontString") and r:IsVisible() and (r:GetText() or ""):find("%d:%d%d") then
                found[#found + 1] = r:GetText()
            end
        end
        for _, c in ipairs({ f:GetChildren() }) do walk(c) end
    end
    walk(M.env.BleakholdRoyaleBar)
    return found
end

-- The countdown's centre and left edge, in UIParent units from the screen's centre (it hangs from UIParent's TOP).
local function frameX(f)
    local p, rel, rp, x = f:GetPoint(1)
    assert(p == "TOP" and rp == "TOP", "the countdown hangs from UIParent's top")
    return x * f:GetScale()
end

local function leftEdge(f)
    return frameX(f) - f:GetWidth() * f:GetScale() / 2
end

local function topEdge(f)
    local _, _, _, _, y = f:GetPoint(1)
    return y * f:GetScale()
end

-- The island map's right edge from the screen's centre when it hangs from UIParent's horizontal middle, else nil.
local AX = { TOPLEFT = 0, LEFT = 0, BOTTOMLEFT = 0, TOP = 0.5, CENTER = 0.5, BOTTOM = 0.5, TOPRIGHT = 1, RIGHT = 1,
    BOTTOMRIGHT = 1 }
local function mapRightEdge(M, w)
    local p, rel, rp, x = w:GetPoint(1)
    if rel ~= M.env.UIParent or AX[rp] ~= 0.5 then return nil end
    local s = w:GetScale()
    return x * s + (1 - AX[p]) * w:GetWidth() * s
end

-- Lit notches of the ring: { count, contiguous from the top clockwise, any ember }.
local function notches(ns)
    local RS = ns.RoyaleStyle
    local lit, hot, firstDark, gap = 0, false, nil, false
    local er, eg = RS.Rgb("ember")
    for i, t in ipairs(ns.RoyaleCountdown.frame.stage.notches) do
        local r, g, b, a = t:GetVertexColor()
        local isLit = (a or 1) > 0.95 and r > 0.6
        if isLit then
            lit = lit + 1
            if firstDark then gap = true end
            if math.abs(r - er) < 0.02 and math.abs(g - eg) < 0.02 then hot = true end
        elseif not firstDark then
            firstDark = i
        end
    end
    return lit, not gap, hot
end

local function shownShocks(ns)
    local f, n = ns.RoyaleCountdown.frame, 0
    for _, t in ipairs({ f.shocks[1], f.shocks[2], f.dust }) do
        if t:IsShown() and t:GetAlpha() > 0.01 then n = n + 1 end
    end
    return n
end

------------------------------------------------------------------------------------------------------

test("royale countdown: nothing at 16 s; 15 at 15 s after the ring's entrance; one number a second in three tiers",
function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    roys(M, { [3] = 16000 })
    M.Advance(0.3)
    local RC = ns.RoyaleCountdown
    local cd = M.env.BleakholdRoyaleCountdown
    H.ok(not cd:IsShown(), "nothing at 15.7 s")
    H.eq(#royaleSounds(M), 0)
    -- the server's exact ROYS at 15000 ms
    reveal(M)
    H.ok(cd:IsShown(), "the countdown at 15 s")
    H.eq(RC.Shown(), 15)
    H.eq(cd:GetFrameStrata(), "DIALOG")
    H.eq(cd.num.cur:GetAlpha(), 0, "the 15 drops in after the ring")
    H.ok(cd:GetAlpha() < 0.5, "the frame fades in")
    near(cd.stage:GetScale(), RC.STAGE_FROM, 1e-6, "the ring assembles from 0.92")
    H.eq(#royaleSounds(M), 0, "the tick comes with the numeral")
    M.Advance(0.4)
    near(cd:GetAlpha(), 1); near(cd.stage:GetScale(), 1)
    near(cd.num.cur:GetAlpha(), 1, 1e-6, "the 15 is in")
    H.eq(cd.num:GetValue(), "15")
    H.eq(cd.num.cap, ns.RoyaleArt.countdown.twoDigitCap)
    local lit, run, hot = notches(ns)
    H.eq(lit, 15, "every notch lit"); H.ok(run and not hot)
    H.eq(shownShocks(ns), 0, "tier A: no ring")
    H.eq(table.concat(royaleSounds(M), " "), "tick")
    H.eq(cd.kick.text:GetText(), "DROP IN")
    H.eq(cd.line1:GetText(), "Circle 1 of 6 is on your map.")
    H.eq(cd.line2:GetText(), "Landing at Harrow Farm")
    H.eq(#barClocks(M), 0, "one clock on screen")
    -- then every second, sampled 0.4 s after each change
    for k = 1, 14 do
        M.Advance(1)
        local n = 15 - k
        H.eq(RC.Shown(), n, "the number " .. k .. " s in")
        H.eq(cd.num:GetValue(), tostring(n))
        local cap = n >= 10 and ns.RoyaleArt.countdown.twoDigitCap or (n > 3 and 150 or 172)
        H.eq(cd.num.cap, cap, "the cap of " .. n)
        local shocks = n >= 11 and 0 or (n >= 4 and 1 or 2)
        H.eq(shownShocks(ns), shocks, "the rings of " .. n)
        lit, run, hot = notches(ns)
        H.eq(lit, n, "lit notches at " .. n)
        H.ok(run, "the lit notches run from the top at " .. n)
        H.eq(hot, n <= 3, "ember notches at " .. n)
        H.eq(#barClocks(M), 0, "no second clock at " .. n)
    end
    local sounds = royaleSounds(M)
    H.eq(count(sounds, "tick"), 12, "tick.wav for 15-4")
    H.eq(table.concat(sounds, " ", 13), "tick3 tick2 tick1")
    H.eq(#sounds, 15)
    local turned = 0
    for _, r in ipairs(M.rotations) do
        if ns.RoyaleStyle.RootOf(r.texture) == cd then
            turned = turned + 1
            H.ok(r.path == ROYALE_ART .. "Notch" and math.abs(r.width - r.height) < 1e-6, "SetRotation on a notch only")
        end
    end
    H.eq(turned, 15, "the 15 notches turned once each")
end)

test("royale countdown: the circle banner is folded into the countdown in the lobby, and shown in the fight",
function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    reveal(M)
    H.send(M, "ROYV", { { "R", 1, -150, -310, "", "" } })
    M.Advance(0.3)
    local Hud = ns.RoyaleHud
    H.ok(Hud.current == nil and #Hud.queue == 0, "no R banner in phase 1")
    H.eq(ns.RoyaleCountdown.frame.line1:GetText(), "Circle 1 of 6 is on your map.")
    roys(M, { [2] = 3, [3] = 0, [6] = 2, [11] = 1 })
    H.send(M, "ROYV", { { "R", 2, -100, -300, "", "" } })
    M.Advance(0.2)
    local queued = (Hud.current and Hud.current.key == "eR")
    for _, q in ipairs(Hud.queue) do queued = queued or q.key == "eR" end
    H.ok(queued, "the R banner in phase 3")
end)

test("royale countdown: at T-3.6 the pin locks on the client, the map closes silently, the countdown glides to the "
    .. "centre by T-3.3; DROP! at zero with the gong; gone 1.1 s later", function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    roys(M)
    M.Advance(0.3)
    local RC, MP = ns.RoyaleCountdown, ns.RoyaleMap
    local cd, map = M.env.BleakholdRoyaleCountdown, M.env.BleakholdRoyaleMapFrame
    H.ok(map:IsShown(), "the lobby map opened by itself")
    local words = 0
    ns.On("ROYALE_DROP_WORD", function() words = words + 1 end)
    local locks = 0
    ns.On("ROYALE_PIN_LOCKED", function() locks = locks + 1 end)
    reveal(M)
    near(leftEdge(cd), 24, 1e-6, "docked: the left edge 24 units right of the centre")
    near(topEdge(cd), -112, 1e-6, "under the bar's tab")
    M.Advance(11.3)                    -- T-3.7
    H.ok(not RC.Locked(), "not yet locked")
    H.eq(RC.Shown(), 4)
    H.ok(map:IsShown())
    local closeSounds = count(M.sounds, "igCharacterInfoClose")
    M.Advance(0.2)                     -- T-3.5: during the 4
    H.ok(RC.Locked(), "locked on the client")
    if MP.PinLocked then
        H.ok(MP.PinLocked(), "the map's lock follows")
    end
    H.eq(locks, 1)
    H.ok(not map:IsShown(), "the map closed")
    if MP.Close then
        H.eq(count(M.sounds, "igCharacterInfoClose"), closeSounds, "with no close sound")
    end
    H.eq(cd.line2:GetText(), "Landing locked")
    local x = frameX(cd)
    H.ok(x > 0 and x < 24 + 210, "gliding: " .. x)
    M.Advance(0.25)                    -- T-3.25
    near(frameX(cd), 0, 1e-6, "centred by T-3.3")
    H.eq(RC.Shown(), 4, "before the 3 lands")
    M.Advance(0.5)
    H.eq(RC.Shown(), 3)
    near(frameX(cd), 0)
    -- zero
    M.Advance(2.6)                     -- T-0.15
    H.ok(not cd.drop:IsShown())
    H.eq(count(M.sounds, "Gong (Non-Looping)"), 0)
    M.Advance(0.2)                     -- T+0.05
    H.ok(cd.drop:IsShown(), "DROP! at the local zero")
    H.eq(count(M.sounds, "Gong (Non-Looping)"), 1, "the gong")
    H.eq(words, 1, "ROYALE_DROP_WORD once")
    H.ok(RC.Shown() == nil, "no number under DROP!")
    -- the server's drop follows within a tick, with the drop's times
    roys(M, { [2] = 2, [3] = 20000, [6] = 1, [11] = 1, [24] = 6, [25] = 8000, [26] = 20000, [27] = 8000 })
    M.Advance(0.5)
    H.eq(words, 1, "still once")
    H.eq(count(M.sounds, "Gong (Non-Looping)"), 1, "one gong")
    if ns.RoyaleDrop.PlayWind then
        H.eq(count(royaleSounds(M), "wind"), 1, "the wind 0.5 s after the gong (RoyaleDrop.lua)")
    end
    H.ok(cd:IsShown(), "DROP! holds")
    M.Advance(0.6)                     -- 1.15 s after DROP!
    H.ok(not cd:IsShown(), "the frame gone after 1.1 s")
    -- a stale phase-1 ROYS after the drop never restarts it
    roys(M, { [3] = 300 })
    M.Advance(0.3)
    H.ok(not cd:IsShown(), "no second countdown for the match")
    H.ok(not ns.RoyaleCountdown.frame.drop:IsShown())
end)

test("royale countdown: after the lock M keeps the map shut until the drop and says where the landing is locked",
function(M, ns)
    connect(M)
    M.inInstance, M.instanceType = true, "pvp"
    H.send(M, "ROYM", MAP)
    roys(M)
    M.Advance(0.3)
    local cd, map = M.env.BleakholdRoyaleCountdown, M.env.BleakholdRoyaleMapFrame
    reveal(M)
    M.Advance(11.9)                    -- T-3.1: locked, centred
    H.ok(ns.RoyaleCountdown.Locked(), "locked")
    near(frameX(cd), 0, 1e-6, "the countdown in the centre")
    H.ok(not map:IsShown(), "the lock closed the map")
    local from = #M.chat
    H.eq(cd.line2:GetText(), "Landing locked")
    M.env.BleakholdToggle("royalemap")   -- the M key and the micro menu
    H.ok(not map:IsShown(), "M does not dock the map under the centred ring")
    H.eq(cd.line2:GetText(), "Landing locked at Harrow Farm", "the countdown names the locked landing")
    near(select(1, cd.line2:GetTextColor()), select(1, ns.RoyaleStyle.Rgb("gold")), 1e-6, "in gold")
    for i = from + 1, #M.chat do
        H.ok(M.chat[i].frame ~= M.env.UIErrorsFrame, "no error line across the ring: " .. tostring(M.chat[i].msg))
    end
    M.Advance(2.6)
    H.eq(cd.line2:GetText(), "Landing locked", "back after 2.5 s")
    -- the stock world map's redirect out of combat says the same and opens nothing
    if M.LoadWorldMap then
        M.LoadWorldMap()
        M.mapInfo = "BleakholdRoyale"
        ns.RoyaleMap.HookWorldMap()
        M.env.WorldMapFrame:Show()
        M.Advance(0.05)
        H.ok(not map:IsShown(), "not through the stock map either")
        H.ok(not M.env.WorldMapFrame:IsShown(), "the stock map is closed again")
        H.eq(cd.line2:GetText(), "Landing locked at Harrow Farm", "and the countdown says where")
        -- in combat the stock map stays (protected) and covers the countdown anyway: ours opens above it as before
        M.SetCombat(true)
        M.env.WorldMapFrame:Show()
        M.Advance(0.05)
        H.ok(map:IsShown(), "ours over the stock map in combat")
        H.eq(map:GetFrameStrata(), "FULLSCREEN_DIALOG")
        M.env.WorldMapFrame:Hide()
        M.Advance(0.05)
        H.ok(not map:IsShown(), "and gone with it")
        M.SetCombat(false)
    end
    near(frameX(cd), 0, 1e-6, "the countdown stays in the centre")
    M.Advance(0.7)                     -- DROP!
    H.ok(cd.drop:IsShown(), "DROP!")
    M.env.BleakholdToggle("royalemap")
    H.ok(not map:IsShown(), "not under DROP! either")
    roys(M, { [2] = 2, [3] = 20000, [6] = 1, [11] = 1, [24] = 6, [25] = 8000, [26] = 20000, [27] = 8000 })
    M.Advance(1.2)
    M.env.BleakholdToggle("royalemap")
    H.ok(map:IsShown(), "after the drop M opens it")
    H.ok(not ns.RoyaleMap.docked, "centred for the fall, not docked")
end)

test("royale countdown: ROYS me 1 before the local zero shows DROP! at once", function(M, ns)
    connect(M)
    reveal(M)
    M.Advance(13.4)
    H.eq(ns.RoyaleCountdown.Shown(), 2)
    roys(M, { [2] = 2, [3] = 20000, [6] = 1, [25] = 8000, [26] = 20000, [27] = 8000 })
    local cd = M.env.BleakholdRoyaleCountdown
    H.ok(cd.drop:IsShown(), "DROP! with the ROYS")
    H.eq(count(M.sounds, "Gong (Non-Looping)"), 1)
    M.Advance(1.2)
    H.ok(not cd:IsShown())
    M.Advance(1)
    H.eq(count(M.sounds, "Gong (Non-Looping)"), 1, "no second DROP! at the local zero")
end)

test("royale countdown: a cancelled match shows MATCH CANCELLED for 1.5 s and no gong", function(M, ns)
    connect(M)
    reveal(M)
    M.Advance(5)
    roys(M, { [2] = 7, [3] = 0 })
    M.Advance(0.3)
    local cd = M.env.BleakholdRoyaleCountdown
    H.ok(cd.cancel:IsShown(), "MATCH CANCELLED")
    H.eq(cd.cancel.title, "MATCH CANCELLED")
    H.eq(cd.cancel.cap, 22)
    local r, g, b = cd.cancel.tex:GetVertexColor()
    local br, bg, bb = ns.RoyaleStyle.Rgb("blood")
    near(r, br); near(g, bg); near(b, bb)
    H.ok(not cd.drop:IsShown(), "no DROP!")
    M.Advance(1.0)
    H.ok(cd:IsShown(), "it holds")
    M.Advance(1.0)
    H.ok(not cd:IsShown(), "then goes")
    H.eq(count(M.sounds, "Gong (Non-Looping)"), 0, "no gong")
end)

test("royale countdown: a server time more than 0.35 s off jumps to the right second without a restart", function(M, ns)
    connect(M)
    reveal(M)
    local RC = ns.RoyaleCountdown
    local cd = M.env.BleakholdRoyaleCountdown
    local id = RC.run.id
    M.Advance(2.4)                     -- 12.6 s left: 13
    H.eq(RC.Shown(), 13)
    local endsAt = RC.run.endsAt
    -- 0.2 s off: the beat stays where it is
    roys(M, { [3] = 12400, [9] = 120, [10] = 80, [15] = -150, [16] = -310, [17] = 520 })
    H.eq(RC.run.endsAt, endsAt, "kept within 0.35 s")
    -- 2 s off: the next change jumps to 11, skipping 12
    roys(M, { [3] = 10600, [9] = 120, [10] = 80, [15] = -150, [16] = -310, [17] = 520 })
    M.Advance(0.1)
    H.eq(RC.Shown(), 11, "jumped to the server's second")
    H.eq(RC.run.id, id, "the same run: no restart")
    near(cd:GetAlpha(), 1, 1e-6, "no new entrance")
    local sounds = royaleSounds(M)
    H.eq(#sounds, 4, "15, 14, 13 and 11 only: " .. table.concat(sounds, " "))
    local lit = notches(ns)
    M.Advance(0.3)
    lit = notches(ns)
    H.eq(lit, 11, "the skipped notch is dark too")
    -- the server moves the drop back by more than a second: the countdown goes, and starts again at 15
    roys(M, { [3] = 25000 })
    M.Advance(0.5)
    H.ok(not cd:IsShown(), "gone while the drop is 25 s away")
    roys(M, { [3] = 15000 })
    H.ok(cd:IsShown()); H.eq(RC.Shown(), 15)
end)

test("royale countdown: a late arrival (falling without the lobby) never sees it", function(M, ns)
    connect(M)
    roys(M, { [2] = 2, [3] = 20000, [6] = 1, [25] = 8000, [26] = 20000, [27] = 8000 })
    M.Advance(2)
    H.ok(not M.env.BleakholdRoyaleCountdown:IsShown())
    H.eq(count(M.sounds, "Gong (Non-Looping)"), 0)
end)

test("royale countdown: with reduced motion the numbers, DROP! and its hold keep their timing", function(M, ns)
    connect(M)
    ns.RoyaleStyle.SetMotion(false)
    reveal(M)
    local cd = M.env.BleakholdRoyaleCountdown
    near(cd:GetAlpha(), 1, 1e-6, "no fade")
    M.Advance(0.2)
    near(cd.num.cur:GetAlpha(), 1)
    M.Advance(14.9)                    -- T+0.1
    H.ok(cd:IsShown() and cd.drop:IsShown(), "DROP! shows")
    near(cd.drop.rsZoom, 1)
    M.Advance(0.6)
    H.ok(cd:IsShown(), "and holds")
    M.Advance(0.3)
    H.ok(not cd:IsShown(), "gone after its hold")
    H.ok(not ns.RoyaleStyle.driver:IsShown(), "no tween left running")
end)

------------------------------------------------------------------------------------------------------
-- Docking beside the island map
------------------------------------------------------------------------------------------------------
for _, screen in ipairs({ { 1920, 1080 }, { 1024, 768 }, { 1280, 1024 } }) do
    local w, h = screen[1], screen[2]
    test(("royale countdown: docked beside the lobby map at %dx%d"):format(w, h), function(M, ns)
        M.SetScreen(w, h, 1)
        connect(M)
        H.send(M, "ROYM", MAP)
        roys(M)
        M.Advance(0.3)
        local cd, map = M.env.BleakholdRoyaleCountdown, M.env.BleakholdRoyaleMapFrame
        H.ok(map:IsShown(), "the map auto-opened in phase 1")
        reveal(M)
        H.ok(M.env.UIParent:GetWidth() / 2 - 40 >= 420, "room for the countdown")
        near(leftEdge(cd), 24, 1e-6, "the countdown's left edge at CENTER +24")
        H.ok(map:IsShown(), "the map stays beside it")
        if ns.RoyaleMap.Close then
            -- the rebuilt map docks itself (RoyaleMap.lua): its right edge at CENTER -24
            local right = mapRightEdge(M, map)
            H.ok(right and math.abs(right + 24) < 0.5, "the map's right edge at CENTER -24: " .. tostring(right))
        end
        -- the map closed by hand: the countdown glides to the centre
        map:Hide()
        M.Advance(0.5)
        near(frameX(cd), 0, 1e-6, "centred without the map")
        -- a new screen size lays it out again
        M.SetScreen(w, h, 0.8)
        M.Advance(0.2)
        near(frameX(cd), 0)
        near(topEdge(cd), -112)
    end)
end

test("royale countdown: a HUD scale that leaves no room centres it and closes the auto-opened map at T-15",
function(M, ns)
    M.SetScreen(1024, 768, 1)
    connect(M)
    ns.RoyaleStyle.SetHudScale(1.2)
    H.send(M, "ROYM", MAP)
    roys(M)
    M.Advance(0.3)
    local cd, map = M.env.BleakholdRoyaleCountdown, M.env.BleakholdRoyaleMapFrame
    H.ok(map:IsShown(), "auto-opened")
    reveal(M)
    near(cd:GetScale(), 1.2)
    near(frameX(cd), 0, 1e-6, "centred: 472 units of room < 420 x 1.2")
    near(topEdge(cd), -(98 * 1.2 + 14), 1e-6, "its top 14 under the bar's tab, which the HUD scale lowers")
    H.ok(not map:IsShown(), "the auto-opened map closed at T-15")
    -- back to 1.0 mid-countdown: laid out again (still centred, the map is closed)
    ns.RoyaleStyle.SetHudScale(1.0)
    M.Advance(0.2)
    near(frameX(cd), 0)
    near(topEdge(cd), -112)
end)

test("royale countdown: a HUD scale that still fits docks it at the scaled width (16:9, 1.4)", function(M, ns)
    M.SetScreen(1920, 1080, 1)
    connect(M)
    H.send(M, "ROYM", MAP)
    roys(M)
    M.Advance(0.3)
    reveal(M)
    local cd = M.env.BleakholdRoyaleCountdown
    near(leftEdge(cd), 24)
    ns.RoyaleStyle.SetHudScale(1.4)
    M.Advance(0.2)
    near(cd:GetScale(), 1.4)
    near(leftEdge(cd), 24, 1e-6, "re-docked at the new scale")
    near(topEdge(cd), -(98 * 1.4 + 14), 1e-6, "under the tab at 1.4 (its bottom at -137.2)")
end)

-- A frame's rectangle in UIParent units from its anchors and sizes, as the client lays it out: an anchor's offsets and
-- the size are in the frame's own (scaled) units. Returns left, right (from the screen's centre), top, bottom (from
-- the screen's top, negative downwards).
local POINT = { TOPLEFT = { 0, 0 }, TOP = { 0.5, 0 }, TOPRIGHT = { 1, 0 }, LEFT = { 0, 0.5 }, CENTER = { 0.5, 0.5 },
    RIGHT = { 1, 0.5 }, BOTTOMLEFT = { 0, 1 }, BOTTOM = { 0.5, 1 }, BOTTOMRIGHT = { 1, 1 } }
local function uiBox(M, f)
    local ui = M.env.UIParent
    if f == ui then
        return 0, 0, ui:GetWidth(), ui:GetHeight()
    end
    local k = f:GetEffectiveScale() / ui:GetEffectiveScale()
    local L, T, R, B, CX, CY
    for i = 1, f:GetNumPoints() do
        local p, rel, rp, x, y = f:GetPoint(i)
        local l, t, r, b = uiBox(M, rel or f:GetParent())
        local tx = l + (r - l) * POINT[rp][1] + (x or 0) * k
        local ty = t + (b - t) * POINT[rp][2] - (y or 0) * k
        local ax, ay = POINT[p][1], POINT[p][2]
        if ax == 0 then L = tx elseif ax == 1 then R = tx else CX = tx end
        if ay == 0 then T = ty elseif ay == 1 then B = ty else CY = ty end
    end
    local w, h = f:GetWidth() * k, f:GetHeight() * k
    if not (L and R) then
        if L then R = L + w elseif R then L = R - w else L, R = CX - w / 2, CX + w / 2 end
    end
    if not (T and B) then
        if T then B = T + h elseif B then T = B - h else T, B = CY - h / 2, CY + h / 2 end
    end
    return L, T, R, B
end

local function uiRect(M, f)
    local L, T, R, B = uiBox(M, f)
    local half = M.env.UIParent:GetWidth() / 2
    return L - half, R - half, -T, -B
end

test("royale countdown: at every HUD scale the docked map and the countdown start under the bar's tab", function(M, ns)
    M.SetScreen(1920, 1080, 1)
    connect(M)
    H.send(M, "ROYM", MAP)
    roys(M, { [9] = 120, [10] = 80 })
    M.Advance(0.3)
    reveal(M)
    M.Advance(0.5)
    local tab = ns.RoyaleHud.bar.tab
    local map, cd = M.env.BleakholdRoyaleMapFrame, M.env.BleakholdRoyaleCountdown
    for _, scale in ipairs({ 0.8, 1.0, 1.15, 1.25, 1.4 }) do
        ns.RoyaleStyle.SetHudScale(scale)
        M.Advance(0.2)
        H.ok(tab:IsShown(), "the tab shows the landing line at " .. scale)
        local _, _, _, tabBottom = uiRect(M, tab)
        near(tabBottom, -98 * scale, 1e-6, "the tab's bottom at " .. scale)
        H.ok(map:IsShown() and ns.RoyaleMap.docked, "docked at " .. scale)
        local ml, mr, mt, mb = uiRect(M, map)
        local cl, cr, ct = uiRect(M, cd)
        H.ok(mt <= tabBottom - 14 + 1e-6 and ct <= tabBottom - 14 + 1e-6,
            ("map top %.1f, countdown top %.1f, tab bottom %.1f at %s"):format(mt, ct, tabBottom, scale))
        H.ok(mt <= -112 + 1e-6 and ct <= -112 + 1e-6, "never above 112 at " .. scale)
        near(mr, -24, 1e-6, "the map's right edge at " .. scale)
        near(cl, 24, 1e-6, "the countdown's left edge at " .. scale)
        H.ok(mb >= -768 + 24 - 1e-6, "the map stays above the bottom margin at " .. scale)
    end
end)

------------------------------------------------------------------------------------------------------
-- Sizes
------------------------------------------------------------------------------------------------------
-- Width and height in texels of an Art\Royale file (TGA header, or BLP2 header).
local function fileDims(path)
    local rel = path:match("^Interface\\AddOns\\Bleakhold\\(.+)$"):gsub("\\", "/")
    local s = host_readfile(addonDir .. "/" .. rel .. ".tga")
    if s then
        return s:byte(13) + s:byte(14) * 256, s:byte(15) + s:byte(16) * 256
    end
    s = assert(host_readfile(addonDir .. "/" .. rel .. ".blp"), "no art file for " .. path)
    local function u32(o)
        return s:byte(o + 1) + s:byte(o + 2) * 256 + s:byte(o + 3) * 65536 + s:byte(o + 4) * 16777216
    end
    return u32(12), u32(16)
end

-- The worst texel:px ratio down the height of the countdown's shown art (9-slice pieces stretch by design).
local function worstRatio(M, ns)
    local RS = ns.RoyaleStyle
    local root = ns.RoyaleCountdown.frame
    local worst, what = 0, ""
    for _, o in ipairs(M.objects) do
        if o.__otype == "Texture" and type(o.rsPath) == "string" and o.rsPath:find(ROYALE_ART, 1, true) == 1
            and o:IsVisible() and o:GetHeight() > 0 and o.rsArt ~= "PlateTab" and RS.RootOf(o) == root then
            local w, h = fileDims(o.rsPath)
            local ulx, uly, llx, lly = o:GetTexCoord()
            local texels = math.sqrt(((llx - ulx) * w) ^ 2 + ((lly - uly) * h) ^ 2)
            local ratio = texels / (o:GetHeight() * RS.PxPerUnit(o))
            if ratio > worst then worst, what = ratio, o.rsArt .. " " .. o:GetHeight() end
        end
    end
    return worst, what
end

for _, screen in ipairs({ { 1920, 1080 }, { 2560, 1440 } }) do
    test(("royale countdown: no art minified past 2.2x at %dx%d, through every tier and DROP!"):format(screen[1],
        screen[2]), function(M, ns)
        M.SetScreen(screen[1], screen[2], 1)
        connect(M)
        reveal(M)
        local worst, what = 0, ""
        for _ = 1, 160 do
            M.Advance(0.1)
            local r, w = worstRatio(M, ns)
            if r > worst then worst, what = r, w end
        end
        H.ok(worst > 0, "art was measured")
        H.ok(worst <= 2.2, ("texel ratio %.2f (%s)"):format(worst, what))
    end)
end

test("royale countdown: its text fits the kicker tab and the frame at 1080p, 1440p and 2160p", function(M, ns)
    for _, screen in ipairs({ { 1920, 1080 }, { 2560, 1440 }, { 3840, 2160 } }) do
        M.SetScreen(screen[1], screen[2], 1)
        local cd = ns.RoyaleCountdown.frame
        local kick = cd.kick.text
        H.ok(kick:GetStringWidth() <= cd.kick:GetWidth() - 16, "DROP IN fits its tab")
        local _, size = kick:GetFont()
        H.ok(size * ns.RoyaleStyle.PxPerUnit(kick) <= 32 + 1e-6, "the label within the rasteriser's 32 px")
        for _, text in ipairs({ "Circle 12 of 16 is on your map.", "No landing chosen. You drop at random.",
            "Landing at Salvagers' Camp" }) do
            cd.line2:SetText(text)
            H.ok(cd.line2:GetStringWidth() <= cd:GetWidth() - 20, text .. " fits")
        end
    end
end)
