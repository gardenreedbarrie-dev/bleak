-- Bleakhold Royale's drop countdown (RoyaleCountdown.lua) in the DBM style: nothing before 15 s; a DBM-style timer bar
-- (195x20, the icon left, "Drop in", the seconds with one decimal under 10 s, the spark, DBM's colours from orange to
-- red, its flash); the classic pull countdown's big numerals for the last five seconds, popping in large and settling
-- with their glow; the ticks; one clock on screen; the client's pin lock at T-3.6 with the silent map close and the
-- glide to the centre; DROP! as a special warning with the gong (or at once when the server drops first); a cancelled
-- match; corrections that jump without restarting; DBM's own bar when DBM is loaded (a local pizza timer, never a
-- sync) with ours hidden; the circle banner folded into the countdown in the lobby; docking beside the island map on
-- 16:9, 4:3 and 5:4 (centred when it does not fit); reduced motion; late arrivals; and the texel ratio of every
-- texture the countdown shows.
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

-- The bar's state: shown, its name, time, value and colour.
local function barState(ns)
    local bar = ns.RoyaleCountdown.frame.bar
    local r, g, b = bar.sb:GetStatusBarColor()
    return { shown = bar:IsVisible(), name = bar.name:GetText(), time = bar.time:GetText(), value = bar.sb:GetValue(),
        r = r, g = g, b = b }
end

-- The big numeral shown (its glyph), or nil.
local function bigShown(ns)
    local num = ns.RoyaleCountdown.frame.num
    return num:IsVisible() and num.glyph or nil
end

-- Advances in 0.05 s steps until the countdown shows the second n (at most `limit` s).
local function untilShown(M, ns, n, limit)
    local waited = 0
    while ns.RoyaleCountdown.Shown() ~= n do
        M.Advance(0.05, 0.05)
        waited = waited + 0.05
        assert(waited < (limit or 16), "never showed " .. n)
    end
end

-- A stand-in for DBM-Core (3.3.5a): CreatePizzaTimer and DBM.Bars (DBT) GetBar/CancelBar, recording every call.
local function fakeDbm(M, opts)
    opts = opts or {}
    local d = { calls = {}, cancels = {}, bars = {} }
    function d:CreatePizzaTimer(t, text, broadcast, ...)
        if opts.fail then error("DBM broke") end
        self.calls[#self.calls + 1] = { t = t, text = text, broadcast = broadcast, n = select("#", ...) + 3,
            at = M.now }
        if not opts.noBar then self.bars[text] = { timer = t } end
    end
    d.Bars = {}
    function d.Bars:GetBar(id) return d.bars[id] end
    function d.Bars:CancelBar(id)
        d.cancels[#d.cancels + 1] = id
        d.bars[id] = nil
    end
    M.env.DBM = d
    return d
end

------------------------------------------------------------------------------------------------------

test("royale countdown: nothing at 16 s; at 15 s a DBM-style bar counts down; the last five as big pull numerals",
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
    H.ok(cd:GetAlpha() < 0.5, "the frame fades in")
    H.eq(table.concat(royaleSounds(M), " "), "tick", "the first tick with the bar")
    -- DBM's default bar: 195x20, the icon left of it, the stock bar fill, the name left, the time right
    local bar = cd.bar
    H.eq(bar.sb:GetWidth(), 195); H.eq(bar.sb:GetHeight(), 20)
    H.eq(bar.icon:GetWidth(), 20); H.eq(bar.icon:GetHeight(), 20)
    H.eq(bar.icon:GetTexture(), "Interface\\Icons\\Spell_Magic_FeatherFall")
    near(select(1, bar.icon:GetTexCoord()), 0.07, 1e-6, "the icon's edge cut like an action button's")
    local p1, rel1, rp1 = bar.icon:GetPoint(1)
    H.ok(p1 == "LEFT" and rel1 == bar and rp1 == "LEFT", "the icon on the left")
    H.eq(bar.sb:GetStatusBarTexture():GetTexture(), "Interface\\TargetingFrame\\UI-StatusBar")
    H.eq(bar.spark:GetTexture(), "Interface\\CastingBar\\UI-CastingBar-Spark")
    H.eq(bar.spark:GetBlendMode(), "ADD")
    H.eq(bar.name:GetText(), "Drop in")
    local pn, _, rpn = bar.name:GetPoint(1)
    local pt, _, rpt = bar.time:GetPoint(1)
    H.ok(pn == "LEFT" and rpn == "LEFT" and pt == "RIGHT" and rpt == "RIGHT", "the name left, the time right")
    local st = barState(ns)
    H.ok(st.shown, "our bar without DBM")
    H.eq(st.time, "15")
    near(st.value, 0, 1e-6, "an empty bar fills up")
    near(st.r, 1); near(st.g, 0.7); near(st.b, 0)
    H.ok(not bigShown(ns), "no big numeral at 15")
    M.Advance(0.4)
    near(cd:GetAlpha(), 1)
    H.eq(cd.line1:GetText(), "Circle 1 of 6 is on your map.")
    H.eq(cd.line2:GetText(), "Landing at Harrow Farm")
    H.eq(#barClocks(M), 0, "one clock on screen")
    -- then every second, sampled 0.4 s after each change
    for k = 1, 14 do
        M.Advance(1)
        local n, left = 15 - k, 14.6 - k
        H.eq(RC.Shown(), n, "the second " .. k .. " s in")
        st = barState(ns)
        H.eq(st.time, n >= 11 and tostring(n) or ("%.1f"):format(left), "the bar's time at " .. left)
        local p = 1 - left / 15
        near(st.value, p, 1e-3, "filled at " .. left)
        near(st.g, 0.7 * (1 - p), 1e-3, "from orange towards red at " .. left)
        near(st.r, 1); near(st.b, 0)
        H.eq(bigShown(ns), n <= 5 and tostring(n) or nil, "the big numeral at " .. n)
        if n <= 5 then
            near(cd.num.rsZoom, 1, 1e-6, "settled at " .. n)
            local g = ns.RoyaleArt.atlases.Pull.glyphs[tostring(n)]
            near(cd.num.tex:GetHeight(), g.h * RC.BIG_CAP, 1e-6, "the numeral's size at " .. n)
            local ga = cd.num.glow:GetAlpha()
            H.ok(ga >= RC.GLOW_REST - 1e-6 and ga <= RC.GLOW_PEAK, "a gold glow at " .. n .. ": " .. ga)
            H.ok(bar.spark:IsShown(), "the spark at the fill's end")
        end
        H.eq(#barClocks(M), 0, "no second clock at " .. n)
    end
    local sounds = royaleSounds(M)
    H.eq(count(sounds, "tick"), 12, "tick.wav for 15-4")
    H.eq(table.concat(sounds, " ", 13), "tick3 tick2 tick1")
    H.eq(#sounds, 15)
    for _, r in ipairs(M.rotations) do
        H.ok(ns.RoyaleStyle.RootOf(r.texture) ~= cd, "nothing of the countdown turned: " .. tostring(r.path))
    end
end)

test("royale countdown: each big numeral pops in large and settles with its gold glow; the one before fades",
function(M, ns)
    connect(M)
    reveal(M)
    local RC = ns.RoyaleCountdown
    local cd = M.env.BleakholdRoyaleCountdown
    untilShown(M, ns, 6)
    H.ok(not bigShown(ns), "nothing big at 6")
    untilShown(M, ns, 5)
    H.eq(bigShown(ns), "5")
    H.ok(cd.num.rsZoom >= 1.3, "pops in large: " .. cd.num.rsZoom)
    H.ok(cd.num:GetAlpha() < 1, "and fades in")
    H.ok(cd.num.glow:GetAlpha() > 0.8, "with a gold flare")
    local g = ns.RoyaleArt.atlases.Pull.glyphs["5"]
    local ulx, uly, llx, lly, urx = cd.num.tex:GetTexCoord()
    near(ulx, g.u0); near(urx, g.u1); near(uly, g.v0); near(lly, g.v1)
    H.eq(cd.num.tex:GetTexture(), ns.RoyaleArt.atlases.Pull.file)
    H.eq(cd.num.glow:GetBlendMode(), "ADD")
    M.Advance(0.35)
    near(cd.num.rsZoom, 1, 1e-6, "settled")
    near(cd.num:GetAlpha(), 1)
    local ga = cd.num.glow:GetAlpha()
    H.ok(ga < 0.9 and ga >= RC.GLOW_REST, "the glow settles: " .. ga)
    -- the next second: 4 pops, 5 fades out behind it
    untilShown(M, ns, 4)
    H.eq(bigShown(ns), "4")
    H.ok(cd.numOld:IsShown() and cd.numOld.glyph == "5", "the 5 fades")
    M.Advance(0.03, 0.03)
    H.ok(cd.numOld:GetAlpha() < 0.5, "mostly gone 30 ms after the pop (no doubled digit): " .. cd.numOld:GetAlpha())
    M.Advance(0.3)
    H.ok(not cd.numOld:IsShown(), "and is gone")
    -- the art: 1-5 and DROP! in one atlas, bright gold with a black stroke
    for _, k in ipairs({ "1", "2", "3", "4", "5", "DROP!" }) do
        H.ok(ns.RoyaleArt.atlases.Pull.glyphs[k], "Pull has " .. k)
    end
end)

test("royale countdown: the bar flashes like DBM's from 7.75 s; the time has one decimal from 10 s", function(M, ns)
    local RC = ns.RoyaleCountdown
    H.eq(RC.BarText(15.25), "15", "never 16"); H.eq(RC.BarText(10.4), "11"); H.eq(RC.BarText(10), "10.0")
    H.eq(RC.BarText(9.95), "10.0"); H.eq(RC.BarText(9.91), "10.0"); H.eq(RC.BarText(9.9), "9.9")
    H.eq(RC.BarText(5), "5.0"); H.eq(RC.BarText(0.04), "0.1")
    near(RC.BarFlash(8), 1); near(RC.BarFlash(7.5), RC.BAR_FLASH_LOW, 1e-6, "down at 0.25 s")
    near(RC.BarFlash(7.375), (1 + RC.BAR_FLASH_LOW) / 2, 1e-6, "half way")
    near(RC.BarFlash(7.0), 1, 1e-6, "held from 0.5 s"); near(RC.BarFlash(6.25), RC.BAR_FLASH_LOW, 1e-6, "again")
    local r, g, b = RC.BarColor(0.5)
    near(r, 1); near(g, 0.35); near(b, 0)
    connect(M)
    reveal(M)
    local cd = M.env.BleakholdRoyaleCountdown
    local fill = cd.bar.sb:GetStatusBarTexture()
    M.Advance(7.0)                     -- 8 s left
    near(fill:GetAlpha(), 1)
    M.Advance(0.5)                     -- 7.5 s left
    near(fill:GetAlpha(), RC.BAR_FLASH_LOW, 0.02, "the fill dips")
    near(cd.bar.time:GetAlpha(), 1, 1e-6, "the time stays")
    M.Advance(0.5)
    near(fill:GetAlpha(), 1, 1e-6, "and comes back")
    ns.RoyaleStyle.SetMotion(false)
    M.Advance(0.75)                    -- 6.25 s left: a dip with motion on
    near(fill:GetAlpha(), 1, 1e-6, "steady with reduced motion")
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
    M.Advance(0.3)
    local st = barState(ns)
    H.eq(st.time, "11", "the bar jumped with it")
    near(st.value, 1 - (RC.run.endsAt - M.now) / RC.run.total, 1e-6, "its fill from the server's time")
    near(RC.run.total, 15, 1e-6, "the bar keeps its span")
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

test("royale countdown: DROP! is a special warning: the word slams in, the screen's edge flashes, the rest goes",
function(M, ns)
    connect(M)
    reveal(M)
    local t0 = M.now
    local RC = ns.RoyaleCountdown
    local cd = M.env.BleakholdRoyaleCountdown
    M.Advance(14.9)                    -- T-0.1: the 1
    H.eq(bigShown(ns), "1")
    local drop = cd.drop
    while not drop:IsShown() do M.Advance(0.05, 0.05) end
    H.ok(M.now - t0 - 15 < 0.06, "DROP! at the zero")
    H.eq(drop.glyph, "DROP!")
    H.ok(not cd.num:IsShown() and not cd.numOld:IsShown(), "the numerals go at once: no 1 behind DROP!")
    H.eq(drop.cap, RC.DROP_CAP)
    H.ok(drop.rsZoom >= 1.5, "slams in from large: " .. drop.rsZoom)
    H.eq(drop.tex:GetTexture(), ns.RoyaleArt.atlases.Pull.file)
    M.Advance(0.1, 0.05)
    H.ok(cd.flash:IsShown() and cd.flash:GetAlpha() > 0.2, "the edge flashes: " .. cd.flash:GetAlpha())
    H.eq(cd.flash:GetBlendMode(), "ADD")
    local p, rel = cd.flash:GetPoint(1)
    H.ok(rel == M.env.UIParent, "over the whole screen")
    M.Advance(0.3)
    near(drop.rsZoom, 1, 1e-6, "settled")
    near(cd.bar:GetAlpha(), 0, 1e-6, "the bar went")
    H.ok(not cd.num:IsShown(), "the numeral went")
    M.Advance(0.3)
    near(cd.flash:GetAlpha(), 0, 1e-6, "the flash is over in 0.6 s")
    H.ok(cd:IsShown(), "DROP! holds")
    M.Advance(0.6)
    H.ok(not cd:IsShown(), "gone 1.1 s after it showed")
end)

test("royale countdown: with DBM loaded its own bar counts the drop (a local pizza timer) and ours hides",
function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    local dbm = fakeDbm(M)
    reveal(M)
    local RC = ns.RoyaleCountdown
    local cd = M.env.BleakholdRoyaleCountdown
    H.eq(#dbm.calls, 1, "DBM:CreatePizzaTimer once")
    near(dbm.calls[1].t, 15, 0.05)
    H.eq(dbm.calls[1].text, "Drop in")
    H.eq(dbm.calls[1].broadcast, false, "never broadcast: no sync to the group")
    H.ok(cd:IsShown(), "the countdown runs")
    H.ok(not cd.bar:IsShown(), "one bar on screen: DBM's")
    local _, _, _, _, y = cd.lines:GetPoint(1)
    near(y, 0, 1e-6, "the lines move up to the top")
    H.eq(cd.line2:GetText(), "Landing at Harrow Farm")
    H.eq(#barClocks(M), 0, "and no clock in the top bar")
    -- a correction past 0.35 s restarts DBM's bar at the server's time
    M.Advance(2.4)
    roys(M, { [3] = 10600, [9] = 120, [10] = 80, [15] = -150, [16] = -310, [17] = 520 })
    H.eq(dbm.cancels[1], "Drop in", "the old bar cancelled")
    H.eq(#dbm.calls, 2)
    near(dbm.calls[2].t, 10.6, 0.05, "the new one at the server's time")
    -- a jitter within 0.35 s leaves it alone
    roys(M, { [3] = 10400, [9] = 120, [10] = 80, [15] = -150, [16] = -310, [17] = 520 })
    H.eq(#dbm.calls, 2)
    -- the big numerals, the ticks and DROP! are ours as before
    untilShown(M, ns, 5)
    H.eq(bigShown(ns), "5")
    M.Advance(5.2)
    H.ok(cd.drop:IsShown(), "DROP!")
    H.eq(count(M.sounds, "Gong (Non-Looping)"), 1)
    H.eq(dbm.cancels[#dbm.cancels], "Drop in", "DBM's bar ends with DROP!")
    for _, s in ipairs(M.sent) do
        H.ok(not s.prefix:find("^DBM"), "no DBM message to anyone: " .. s.prefix)
    end
    H.eq(ns.errors, 0)
end)

test("royale countdown: a cancelled match or a left lobby cancels DBM's bar; a DBM that fails leaves ours",
function(M, ns)
    connect(M)
    local dbm = fakeDbm(M)
    reveal(M)
    M.Advance(3)
    roys(M, { [2] = 7, [3] = 0 })
    M.Advance(0.3)
    local cd = M.env.BleakholdRoyaleCountdown
    H.ok(cd.cancel:IsShown(), "MATCH CANCELLED")
    H.eq(#dbm.cancels, 1, "DBM's bar cancelled with it")
    -- a DBM whose call errors: our bar shows, and nothing is counted as our error
    local errors = ns.errors
    fakeDbm(M, { fail = true })
    roys(M, { [1] = 7002, [3] = 15000, [9] = 120, [10] = 80, [15] = -150, [16] = -310, [17] = 520 })
    M.Advance(0.1)
    H.ok(cd:IsShown() and cd.bar:IsShown(), "our bar when DBM fails")
    H.eq(ns.errors, errors)
    -- a DBM that takes the call but shows no bar: ours too
    M.Advance(15.5)
    local quiet = fakeDbm(M, { noBar = true })
    roys(M, { [1] = 7003, [3] = 15000 })
    M.Advance(0.1)
    H.eq(#quiet.calls, 1)
    H.ok(cd.bar:IsShown(), "our bar when DBM shows none")
    M.env.DBM = nil
end)

test("royale countdown: with reduced motion the numbers, DROP! and its hold keep their timing", function(M, ns)
    connect(M)
    ns.RoyaleStyle.SetMotion(false)
    reveal(M)
    local cd = M.env.BleakholdRoyaleCountdown
    near(cd:GetAlpha(), 1, 1e-6, "no fade")
    M.Advance(10.1)                    -- 4.9 s left: the 5 in place at once
    H.eq(bigShown(ns), "5")
    near(cd.num.rsZoom, 1); near(cd.num:GetAlpha(), 1)
    near(cd.num.glow:GetAlpha(), ns.RoyaleCountdown.GLOW_REST)
    near(cd.bar.sb:GetStatusBarTexture():GetAlpha(), 1, 1e-6, "no flashing bar")
    M.Advance(5.0)                     -- T+0.1
    H.ok(cd:IsShown() and cd.drop:IsShown(), "DROP! shows")
    near(cd.drop.rsZoom, 1)
    near(cd.flash:GetAlpha(), 0, 1e-6, "no screen flash")
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
    test(("royale countdown: no art minified past 2.2x at %dx%d, through the numerals and DROP!"):format(screen[1],
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

test("royale countdown: its text fits the bar and the frame at 1080p, 1440p and 2160p", function(M, ns)
    for _, screen in ipairs({ { 1920, 1080 }, { 2560, 1440 }, { 3840, 2160 } }) do
        M.SetScreen(screen[1], screen[2], 1)
        local cd = ns.RoyaleCountdown.frame
        local name, time = cd.bar.name, cd.bar.time
        H.ok(name:GetStringWidth() <= name:GetWidth(), "Drop in fits its bar")
        time:SetText("10.0")
        H.ok(name:GetStringWidth() + time:GetStringWidth() + 16 <= cd.bar.sb:GetWidth(), "the time beside it")
        local _, size = time:GetFont()
        H.ok(size * ns.RoyaleStyle.PxPerUnit(time) <= 32 + 1e-6, "the bar's text within the rasteriser's 32 px")
        for _, text in ipairs({ "Circle 12 of 16 is on your map.", "No landing chosen. You drop at random.",
            "Landing at Salvagers' Camp" }) do
            cd.line2:SetText(text)
            H.ok(cd.line2:GetStringWidth() <= cd:GetWidth() - 20, text .. " fits")
        end
    end
end)
