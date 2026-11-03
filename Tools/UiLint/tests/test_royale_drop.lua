-- Bleakhold Royale's drop HUD (RoyaleDrop.lua, ROYS fields 25-27): the altitude model of an 8 s freefall and 12 s
-- under the canopy, the drop plate 0.8 s after DROP! with one counter that never counts up, wind.wav once, the canopy
-- with "Landing in N", LANDED, a late drop, a /reload in the air, an older server without the fields, a player
-- eliminated in the air, no deploy prompt or key anywhere, the plate's layout and texel ratios, and the view distance
-- raised for the drop and put back.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local SOUNDS = "Interface\\AddOns\\Bleakhold\\Sounds\\Royale\\"

local function near(a, b, eps, msg)
    if type(a) ~= "number" or math.abs(a - b) > (eps or 1e-6) then
        error((msg or "values differ") .. ": expected " .. tostring(b) .. ", got " .. tostring(a), 2)
    end
end

local function connect(M)
    FX.connect(M, H, { [6] = 4096 })
end

-- A ROYS of match 7001 (field index -> value): the lobby before the countdown unless `over` says otherwise.
local function roys(M, over)
    local r = { 7001, 0, 60000, 24, 24, 0, 0, "", "", "", 0, -267, -267, 860, "", "", "", "", "", 0, "", 450, 452, 6,
        "", "", "" }
    for k, v in pairs(over or {}) do r[k] = v end
    H.send(M, "ROYS", { r })
end

-- The lobby in phase 1 with `ms` left, then the drop ROYS (me 1) with the times (or none: an older server).
local function lobby(M, ms)
    roys(M, { [2] = 0, [3] = 20000 })
    roys(M, { [2] = 1, [3] = ms or 2000, [15] = -150, [16] = -310, [17] = 520 })
end

local function drop(M, fallMs, landMs, F, over)
    local t = { [2] = 2, [3] = 20000, [6] = 1, [11] = 1, [15] = -150, [16] = -310, [17] = 520,
        [25] = fallMs or "", [26] = landMs or "", [27] = F or "" }
    for k, v in pairs(over or {}) do t[k] = v end
    roys(M, t)
end

local function played(M, name)
    local n, at = 0, nil
    for i, p in ipairs(M.soundFiles) do
        if p == SOUNDS .. name .. ".wav" or p == SOUNDS .. name .. "_quiet.wav" then
            n = n + 1
            at = at or M.soundFileTimes[i]
        end
    end
    return n, at
end

local function intents(M, op)
    local n = 0
    for _, it in ipairs(H.intents(M)) do
        if it.op == op then n = n + 1 end
    end
    return n
end

------------------------------------------------------------------------------------------------------
-- The model
------------------------------------------------------------------------------------------------------
test("royale drop: the altitude model follows 8 s of freefall and 12 s under the canopy (471.4 yd)", function(M, ns)
    local RD = ns.RoyaleDrop
    near(RD.FallDistance(2.5), 60.3, 0.05)
    near(RD.FallDistance(RD.TT), 93.77, 0.05)
    near(RD.FallDistance(8), 387.42, 0.05)
    near(RD.FallDistance(10), 507.7, 0.05)
    near(RD.FallDistance(-1), 0)
    near(RD.DropHeight(8, 12), 471.42, 0.05)
    near(RD.DropHeight(10, 12), 591.7, 0.05)
    -- the server's timeline (WS-E): t = 0, 3, 5, 8, 14, 20 s after the start gun
    local F, C = 8, 12
    for _, row in ipairs({ { 0, 471.42 }, { 3, 384.61 }, { 5, 264.44 }, { 8, 84.0 }, { 14, 42.0 }, { 20, 0 } }) do
        local t = row[1]
        local fallLeft = math.max(0, F - t)
        local landLeft = math.max(0, F + C - t)
        near(RD.Altitude(fallLeft, landLeft, F), row[2], 0.5, "altitude at t = " .. t)
    end
    -- parachute the whole way (FreefallMs 0): 7 yd/s
    near(RD.Altitude(0, 22, 0), 154, 0.01)
end)

------------------------------------------------------------------------------------------------------
-- A whole drop
------------------------------------------------------------------------------------------------------
test("royale drop: the plate enters 0.8 s after DROP!, FREEFALL counts 8 down, wind.wav once 0.5 s after the gong",
function(M, ns)
    connect(M)
    local plate, alt, sl = M.env.BleakholdRoyaleDrop, M.env.BleakholdRoyaleAltimeter, M.env.BleakholdRoyaleSpeedLines
    lobby(M, 2000)
    local zero = M.now + 2
    M.Advance(2.1)
    -- the teleport's ROYS: 8 s of freefall, the touchdown 20 s away
    drop(M, 8000, 20000, 8000)
    M.Advance(0.1)
    H.ok(sl:IsShown(), "the speed lines come with the drop")
    H.ok(not plate:IsShown(), "no plate while DROP! holds")
    H.ok(not alt:IsShown(), "no altimeter while DROP! holds")
    -- the start gun's ROYS, 0.2 s later: the plan from there
    M.Advance(0.1)
    drop(M, 8000, 20000, 8000)
    M.Advance(0.4)
    H.ok(not plate:IsShown(), "not before 0.8 s after DROP!")
    M.Advance(0.2)
    H.ok(plate:IsShown(), "the plate 0.8 s after DROP!")
    H.ok(alt:IsShown(), "the altimeter with it")
    local RD = ns.RoyaleDrop
    H.eq(RD.plate.ffLabel:GetText(), "FREEFALL")
    H.eq(RD.plate.ffLine:GetText(), "Parachute opens in")
    H.eq(RD.plate.num:GetValue(), "8")
    local n, at = played(M, "wind")
    H.eq(n, 1, "wind.wav")
    near(at, zero + 0.5, 0.11, "wind.wav 0.5 s after DROP!")
    -- 3.5 s after the start gun: 4.5 s left
    M.Advance(3.5 - 0.7)
    H.eq(RD.plate.num:GetValue(), "5")
    H.eq(played(M, "wind"), 1, "the wind plays once")
    H.eq(played(M, "canopy"), 0)
    -- the marker rides the scale
    H.ok(RD.alt.marker:IsShown(), "the altimeter's marker")
    H.ok(RD.alt.canopyIcon:IsShown(), "the canopy height is marked")
end)

test("royale drop: the counter never counts up when the start gun's ROYS moves the plan later", function(M, ns)
    connect(M)
    lobby(M, 1000)
    M.Advance(1)
    drop(M, 8000, 20000, 8000)
    M.Advance(1.3)
    local num = ns.RoyaleDrop.plate.num
    H.eq(num:GetValue(), "7")
    -- a late start gun: the fall restarts the plan from 7.9 s
    drop(M, 7900, 19900, 8000)
    M.Advance(0.1)
    H.eq(num:GetValue(), "7", "never 8 again after 7")
    M.Advance(1.0)
    H.eq(num:GetValue(), "7")
    M.Advance(0.9)
    H.eq(num:GetValue(), "6")
end)

test("royale drop: the parachute opens by itself: PARACHUTE, Landing in 12, canopy.wav; me 2 shows LANDED, then goes",
function(M, ns)
    connect(M)
    local RD = ns.RoyaleDrop
    local plate, alt, sl = M.env.BleakholdRoyaleDrop, M.env.BleakholdRoyaleAltimeter, M.env.BleakholdRoyaleSpeedLines
    lobby(M, 1000)
    M.Advance(1)
    drop(M, 8000, 20000, 8000)
    M.Advance(7.9)
    H.ok(RD.plate.ff:GetAlpha() > 0.99 and RD.plate.cp:GetAlpha() < 0.01, "still freefall")
    H.eq(played(M, "canopy"), 0)
    M.Advance(0.2)
    H.eq(played(M, "canopy"), 1, "canopy.wav when fallMsLeft reaches 0")
    M.Advance(0.3)
    H.ok(RD.plate.cp:GetAlpha() > 0.99, "PARACHUTE content")
    H.ok(RD.plate.ff:GetAlpha() < 0.01, "the freefall content gone")
    H.eq(RD.plate.cpLabel:GetText(), "PARACHUTE")
    H.eq(RD.plate.cpLine:GetText(), "Landing in 12")
    H.ok(RD.plate.canopy:GetAlpha() > 0.99, "the open canopy")
    H.ok(not sl:IsShown(), "the speed lines go at the canopy")
    -- the deploy ROYS: fallMsLeft 0, not empty
    drop(M, 0, 11500, 8000)
    M.Advance(0.1)
    H.eq(RD.plate.cpLine:GetText(), "Landing in 12")
    H.eq(played(M, "canopy"), 1, "once")
    M.Advance(6)
    H.eq(RD.plate.cpLine:GetText(), "Landing in 6")
    local w = RD.plate.fill:GetWidth()
    near(w, RD.BAR.w * 5.4 / 12, 2, "the bar drains with the canopy time")
    -- touchdown
    M.Advance(5.6)
    H.eq(RD.plate.cpLine:GetText(), "Landing in 1")
    roys(M, { [2] = 2, [3] = 3000, [6] = 2, [11] = 1, [15] = -150, [16] = -310, [17] = 520, [18] = 100000,
        [19] = 270000 })
    M.Advance(0.3)
    H.ok(RD.plate.landed:GetAlpha() > 0.99, "LANDED")
    H.ok(plate:IsShown())
    H.eq(played(M, "land"), 1, "land.wav")
    H.ok(not alt:IsShown(), "the altimeter left")
    M.Advance(0.6)
    H.ok(plate:IsShown(), "LANDED holds 0.8 s")
    M.Advance(0.4)
    H.ok(not plate:IsShown(), "then the plate leaves")
    H.eq(RD.drop, nil, "the drop is over")
    H.eq(intents(M, "RDEPLOY"), 0, "no RDEPLOY in a whole drop")
end)

test("royale drop: an older server (no fields 25-27): no number until the Slow Fall aura, then the canopy, no timer",
function(M, ns)
    connect(M)
    local RD = ns.RoyaleDrop
    local plate, alt = M.env.BleakholdRoyaleDrop, M.env.BleakholdRoyaleAltimeter
    lobby(M, 1000)
    M.Advance(1)
    drop(M)
    M.Advance(1)
    H.ok(plate:IsShown())
    H.ok(not RD.plate.num:IsShown(), "no number")
    H.eq(RD.plate.ffLine:GetText(), "Your parachute opens by itself.")
    H.ok(not alt:IsShown(), "no altimeter without the times or Bleakhold.exe's height")
    H.eq(played(M, "wind"), 0, "no wind for an unknown fall")
    local slowFall = false
    M.env.UnitBuff = function(unit, i)
        if unit == "player" and i == 1 and slowFall then
            return "Slow Fall", "", "Interface\\Icons\\Spell_Magic_FeatherFall", 0, "Magic", 30, M.now + 30, "player",
                nil, nil, 130
        end
    end
    M.Advance(2)
    H.ok(RD.plate.ff:GetAlpha() > 0.99, "still freefall")
    slowFall = true
    M.Advance(0.5)
    H.ok(RD.plate.cp:GetAlpha() > 0.99, "the canopy")
    H.eq(RD.plate.cpLine:GetText(), "Drifting down.")
    H.ok(not RD.plate.fill:IsShown() and not RD.plate.track:IsShown(), "no timer bar")
    H.eq(played(M, "canopy"), 1)
end)

test("royale drop: with Bleakhold.exe's height the altimeter shows for an older server too, and clamps it to the model",
function(M, ns)
    connect(M)
    local RD = ns.RoyaleDrop
    local height = 300
    M.env.BleakholdStorm_Altitude = function() return height end
    lobby(M, 1000)
    M.Advance(1)
    drop(M)
    M.Advance(1)
    H.ok(M.env.BleakholdRoyaleAltimeter:IsShown(), "the altimeter from the exe's height")
    H.ok(RD.alt.marker:IsShown())
    H.ok(not RD.alt.canopyIcon:IsShown(), "no canopy mark without the times")
    -- with the times the exe's height is trusted 40 yd around the model
    drop(M, 8000, 20000, 8000)
    height = 9999
    M.Advance(0.1)
    local _, _, _, _, y = RD.alt.marker:GetPoint(1)
    local model = RD.Altitude(7.9, 19.9, 8)
    near(-y, RD.AltY((model + 40) / RD.DropHeight(8, 12)), 0.01, "clamped to the model + 40 yd")
end)

test("royale drop: a late drop (no lobby countdown) shows LATE DROP at once with the wind", function(M, ns)
    connect(M)
    local RD = ns.RoyaleDrop
    drop(M, 8000, 20000, 8000, { [2] = 3 })
    M.Advance(0.1)
    H.ok(M.env.BleakholdRoyaleDrop:IsShown(), "at once")
    H.eq(RD.plate.ffLabel:GetText(), "LATE DROP")
    H.eq(RD.plate.num:GetValue(), "8")
    M.Advance(0.5)
    H.eq(played(M, "wind"), 1)
    M.Advance(8)
    H.eq(RD.plate.cpLabel:GetText(), "PARACHUTE")
end)

test("royale drop: after a /reload in the air the HUD resumes from the times, without the wind", function(M, ns)
    connect(M)
    local RD = ns.RoyaleDrop
    drop(M, 3000, 15000, 8000)
    M.Advance(0.1)
    H.ok(M.env.BleakholdRoyaleDrop:IsShown(), "at once")
    H.eq(RD.plate.ffLabel:GetText(), "FREEFALL", "not a late drop")
    H.eq(RD.plate.num:GetValue(), "3")
    M.Advance(1)
    H.eq(played(M, "wind"), 0, "the wind does not replay")
    M.Advance(2.1)
    H.eq(played(M, "canopy"), 1, "the canopy opening is live")
end)

test("royale drop: a /reload under the canopy resumes there silently", function(M, ns)
    connect(M)
    local RD = ns.RoyaleDrop
    drop(M, 0, 7000, 8000)
    M.Advance(0.2)
    H.ok(M.env.BleakholdRoyaleDrop:IsShown())
    H.ok(RD.plate.cp:GetAlpha() > 0.99, "the canopy content at once")
    H.eq(RD.plate.cpLine:GetText(), "Landing in 7")
    H.eq(RD.alt.marker:GetTexture(), ns.RoyaleArt.files.AltMarker, "the marker's file came with the altimeter")
    H.eq(RD.alt.marker:IsDesaturated(), 1, "and it stays pale under the canopy (greyed before its file came)")
    H.ok(not M.env.BleakholdRoyaleSpeedLines:IsShown(), "no speed lines under the canopy")
    H.eq(played(M, "canopy"), 0)
    H.eq(played(M, "wind"), 0)
end)

test("royale drop: eliminated in the air, the HUD just leaves: no LANDED, no land.wav", function(M, ns)
    connect(M)
    local RD = ns.RoyaleDrop
    lobby(M, 1000)
    M.Advance(1)
    drop(M, 8000, 20000, 8000)
    M.Advance(2)
    roys(M, { [2] = 2, [3] = 18000, [6] = 3, [11] = 1, [21] = "Aldric" })
    M.Advance(0.5)
    H.ok(not M.env.BleakholdRoyaleDrop:IsShown())
    H.ok(not M.env.BleakholdRoyaleAltimeter:IsShown())
    H.ok(not M.env.BleakholdRoyaleSpeedLines:IsShown())
    H.ok(RD.plate.landed:GetAlpha() < 0.01, "no LANDED")
    H.eq(played(M, "land"), 0)
    H.eq(RD.drop, nil)
end)

test("royale drop: reduced motion keeps every beat: the plate, the canopy, LANDED for 0.8 s", function(M, ns)
    connect(M)
    local RD = ns.RoyaleDrop
    ns.RoyaleStyle.SetMotion(false)
    lobby(M, 1000)
    M.Advance(1)
    drop(M, 8000, 20000, 8000)
    M.Advance(0.9)
    H.ok(M.env.BleakholdRoyaleDrop:IsShown())
    H.eq(M.env.BleakholdRoyaleDrop:GetAlpha(), 1)
    M.Advance(7.3)
    H.eq(RD.plate.cp:GetAlpha(), 1)
    roys(M, { [2] = 2, [3] = 3000, [6] = 2, [11] = 1 })
    M.Advance(0.5)
    H.ok(M.env.BleakholdRoyaleDrop:IsShown(), "LANDED holds")
    H.eq(RD.plate.landed:GetAlpha(), 1)
    M.Advance(0.5)
    H.ok(not M.env.BleakholdRoyaleDrop:IsShown())
end)

------------------------------------------------------------------------------------------------------
-- No deploy UI
------------------------------------------------------------------------------------------------------
test("royale drop: no parachute prompt, no deploy key; nothing in the drop HUD sends RDEPLOY", function(M, ns)
    H.eq(M.env.BleakholdRoyaleParachute, nil, "no prompt frame")
    H.eq(M.env.BleakholdRoyaleDeploy, nil, "no binding function")
    H.eq(M.env.BINDING_NAME_BLEAKHOLD_ROYALE_DEPLOY, nil, "no binding label")
    H.eq(ns.Royale.IsDeployed, nil, "no client-side deploy guess")
    local xml = assert(host_readfile(addonDir .. "/Bindings.xml"))
    H.ok(not xml:find("DEPLOY", 1, true), "no deploy binding in Bindings.xml")
    H.ok(not xml:find("BleakholdRoyaleDeploy", 1, true))
    connect(M)
    lobby(M, 1000)
    M.Advance(1)
    drop(M, 8000, 20000, 8000)
    M.Advance(1)
    local before = intents(M, "RDEPLOY")
    for _, root in ipairs({ M.env.BleakholdRoyaleDrop, M.env.BleakholdRoyaleAltimeter }) do
        for _, script in ipairs({ "OnMouseDown", "OnMouseUp", "OnClick", "OnDragStart", "OnDragStop" }) do
            if root:GetScript(script) then
                if script == "OnDragStart" or script == "OnDragStop" then
                    root.StartMoving = function() end
                    root.StopMovingOrSizing = function() end
                end
                M.Fire(root, script, "LeftButton")
            end
        end
        for _, b in ipairs(M.Clickables(root)) do
            b:Click()
        end
    end
    -- every key the player has: none runs a deploy
    for key, action in pairs(M.bindings) do
        H.ok(not tostring(action):find("DEPLOY"), "key " .. key)
    end
    M.Advance(9)
    H.eq(intents(M, "RDEPLOY") - before, 0, "RDEPLOY is never sent")
end)

------------------------------------------------------------------------------------------------------
-- Layout
------------------------------------------------------------------------------------------------------
test("royale drop: the plate and the altimeter sit where the design puts them, movable, at the HUD scale",
function(M, ns)
    local RS = ns.RoyaleStyle
    local plate, alt = M.env.BleakholdRoyaleDrop, M.env.BleakholdRoyaleAltimeter
    local p, rel, rp, x, y = plate:GetPoint(1)
    H.eq(p, "CENTER"); H.eq(rel, M.env.UIParent); H.eq(rp, "CENTER"); H.eq(x, 0); H.eq(y, -230)
    H.eq(plate:GetWidth(), 320); H.eq(plate:GetHeight(), 68)
    p, rel, rp, x, y = alt:GetPoint(1)
    H.eq(p, "CENTER"); H.eq(x, 300); H.eq(y, 20)
    H.eq(alt:GetWidth(), 44); H.eq(alt:GetHeight(), 300)
    H.eq(plate:GetFrameStrata(), "HIGH")
    H.eq(alt:GetFrameStrata(), "HIGH")
    local names = {}
    for _, m in ipairs(ns.Movers) do names[m.name] = m end
    H.ok(names.bleakhold_royale_drop and names.bleakhold_royale_altimeter, "both are movers")
    RS.SetHudScale(1.2)
    H.eq(plate:GetScale(), 1.2)
    H.eq(alt:GetScale(), 1.2)
    -- the editor shows them still, with sample content, and they can be dragged then
    names.bleakhold_royale_drop.begin()
    H.ok(plate:IsShown() and alt:IsShown())
    H.eq(ns.RoyaleDrop.plate.num:GetValue(), "3")
    H.eq(plate:IsMouseEnabled(), 1, "the still plate takes the mouse to be dragged")
    H.eq(alt:IsMouseEnabled(), 1)
    names.bleakhold_royale_drop.finish()
    H.ok(not plate:IsShown() and not alt:IsShown())
end)

test("royale drop: in a real drop the plate and the altimeter are click-through (the camera keeps the mouse)",
function(M, ns)
    connect(M)
    local plate, alt = M.env.BleakholdRoyaleDrop, M.env.BleakholdRoyaleAltimeter
    H.eq(plate:IsMouseEnabled(), nil, "click-through from the start")
    H.eq(alt:IsMouseEnabled(), nil)
    -- /bh royale preview drop: a sample, so they may be dragged into place
    H.ok(ns.RoyaleDrop.Preview())
    M.Advance(1)
    H.ok(plate:IsShown())
    H.eq(plate:IsMouseEnabled(), 1, "draggable in the preview")
    H.eq(alt:IsMouseEnabled(), 1)
    M.Advance(25)
    H.ok(not plate:IsShown(), "the preview is over")
    -- the editor is open when the realm drops the player: the real drop wins
    local names = {}
    for _, m in ipairs(ns.Movers) do names[m.name] = m end
    names.bleakhold_royale_altimeter.begin()
    H.eq(alt:IsMouseEnabled(), 1)
    lobby(M, 1000)
    M.Advance(1)
    drop(M, 8000, 20000, 8000)
    M.Advance(1)
    H.ok(plate:IsShown() and alt:IsShown(), "the drop HUD")
    H.eq(plate:IsMouseEnabled(), nil, "a right-click on the plate starts mouselook")
    H.eq(alt:IsMouseEnabled(), nil, "and on the altimeter too")
    drop(M, 0, 12000, 8000)
    M.Advance(0.5)
    H.eq(plate:IsMouseEnabled(), nil, "still under the canopy")
    names.bleakhold_royale_altimeter.finish()
end)

for _, screen in ipairs({ { 1920, 1080 }, { 2560, 1440 }, { 3840, 2160 } }) do
    test(string.format("royale drop: the plate's content stays in its content rect at %dx%d", screen[1], screen[2]),
    function(M, ns)
        local RD, RS = ns.RoyaleDrop, ns.RoyaleStyle
        M.SetScreen(screen[1], screen[2])
        connect(M)
        lobby(M, 1000)
        M.Advance(1)
        drop(M, 8000, 20000, 8000)
        M.Advance(1)
        local P = RD.plate
        local inset = RS.INSET
        -- the text column: label and line, clamped like the client draws them, left of the counter
        local numLeft = 320 - 14 - P.num:GetWidth()
        for _, fs in ipairs({ P.ffLabel, P.ffLine, P.cpLabel }) do
            local _, size = fs:GetFont()
            H.ok(size <= RS.MaxTextUnits(fs) + 1e-6, "clamped to 32 px")
            local right = RD.TEXT_X + fs:GetStringWidth()
            H.ok(right <= numLeft - 4, fs:GetText() .. " clears the counter: " .. right .. " < " .. numLeft)
        end
        H.ok(numLeft >= RD.TEXT_X, "the counter right of the text column")
        local _, numH = P.num:GetSize()
        H.ok(numH <= 68 - 2 * inset + 1e-6, "the counter fits the content height: " .. numH)
        -- the canopy line and the bar
        drop(M, 0, 12000, 8000)
        M.Advance(0.3)
        local right = RD.TEXT_X + P.cpLine:GetStringWidth()
        H.ok(right <= 320 - inset, "Landing in 12 fits")
        H.ok(RD.TEXT_X + RD.BAR.w <= 320 - inset, "the bar fits")
        H.ok(-RD.BAR.y + RD.BAR.h <= 68 - inset + 1e-6, "the bar above the bottom inset")
        -- the illustration's socket inside the plate's rim, the icon at the content inset
        local _, _, _, sx = P.socket:GetPoint(1)
        H.ok(sx >= P.art.edgeInset, "the socket inside the rim")
        H.eq(sx + 4, inset)
        -- LANDED fits the content rect
        local tw, th = P.landed:GetSize()
        H.ok(tw <= 320 - 2 * inset and th <= 68 - 2 * inset, "LANDED fits: " .. tw .. "x" .. th)
    end)
end

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

for _, screen in ipairs({ { 1920, 1080 }, { 2560, 1440 } }) do
    test(string.format("royale drop: every sized drop texture is at most 2.2x minified at %dx%d, UI scale 1", screen[1],
        screen[2]),
    function(M, ns)
        local RS = ns.RoyaleStyle
        M.SetScreen(screen[1], screen[2], 1)
        connect(M)
        lobby(M, 1000)
        M.Advance(1)
        drop(M, 8000, 20000, 8000)
        M.Advance(1.5)
        local checked = {}
        local function check(t)
            if type(t.rsPath) ~= "string" or not t.__shown or t:GetHeight() <= 0 then return end
            local w, h = fileDims(t.rsPath)
            local ulx, uly, llx, lly = t:GetTexCoord()
            local texels = math.sqrt(((llx - ulx) * w) ^ 2 + ((lly - uly) * h) ^ 2)
            local ratio = texels / (t:GetHeight() * RS.PxPerUnit(t))
            H.ok(ratio <= 2.2, (t.rsArt or t.rsPath) .. " minified " .. ratio)
            checked[t.rsArt or t.rsPath] = true
        end
        local RD = ns.RoyaleDrop
        for _, t in ipairs({ RD.plate.pack, RD.plate.canopy, RD.alt.scale, RD.alt.marker, RD.alt.canopyIcon }) do
            check(t)
        end
        for _, t in ipairs(RD.plate.num.cur.texs) do check(t) end
        RD.plate.landed:SetAlpha(1)
        check(RD.plate.landed.tex)
        for _, art in ipairs({ "Parachute", "Altimeter", "AltMarker", "IconsSmall", "NumeralsS", "Titles" }) do
            H.ok(checked[art], art .. " checked")
        end
    end)
end

------------------------------------------------------------------------------------------------------
-- The view distance
------------------------------------------------------------------------------------------------------
test("royale drop: phase 1 raises the farclip to 1277 and keeps the old one; 8 s after landing it goes back",
function(M, ns)
    connect(M)
    H.eq(M.farclip, 777)
    roys(M, { [2] = 0, [3] = 20000 })
    H.eq(M.farclip, 777, "not in the warm-up")
    roys(M, { [2] = 1, [3] = 60000 })
    H.eq(M.farclip, 1277, "raised at phase 1's start")
    H.eq(M.env.BleakholdDB.royaleFarclipRestore, 777, "the old value in SavedVariables")
    roys(M, { [2] = 1, [3] = 40000 })
    H.eq(M.env.BleakholdDB.royaleFarclipRestore, 777, "kept, not overwritten")
    drop(M, 8000, 20000, 8000)
    M.Advance(20)
    roys(M, { [2] = 3, [6] = 2, [11] = 1 })
    M.Advance(7.8)
    H.eq(M.farclip, 1277, "still raised")
    M.Advance(0.4)
    H.eq(M.farclip, 777, "back 8 s after the landing")
    H.eq(M.env.BleakholdDB.royaleFarclipRestore, nil)
end)

test("royale drop: a disconnect in the air leaves the farclip raised; the next login outside puts it back",
function(M, ns)
    H.eq(M.farclip, 777, "restored at login")
    H.eq(M.env.BleakholdDB.royaleFarclipRestore, nil)
end, { before = function(M)
    M.env.BleakholdDB = { options = {}, royaleFarclipRestore = 777 }
    M.farclip = 1277
end })

test("royale drop: a login back into the match keeps it raised until the match lets it go", function(M, ns)
    H.eq(M.farclip, 1277, "kept in the battleground")
    connect(M)
    roys(M, { [2] = 2, [3] = 9000, [6] = 1, [25] = 3000, [26] = 15000, [27] = 8000 })
    M.Advance(1)
    H.eq(M.farclip, 1277)
    roys(M, { [2] = 6, [3] = 120000, [6] = 3 })
    H.eq(M.farclip, 777, "back when the match ends")
end, { before = function(M)
    M.env.BleakholdDB = { options = {}, royaleFarclipRestore = 777 }
    M.farclip = 1277
    M.inInstance, M.instanceType = true, "pvp"
end })

test("royale drop: the farclip is left alone with the option off, or when it is already 1277 or more", function(M, ns)
    connect(M)
    ns.RoyaleDrop.SetFarclipOption(false)
    roys(M, { [2] = 0, [3] = 20000 })
    roys(M, { [2] = 1, [3] = 60000 })
    H.eq(M.farclip, 777, "option off")
    H.eq(M.env.BleakholdDB.royaleFarclipRestore, nil)
    -- a new match, the option on, a far view already
    ns.RoyaleDrop.SetFarclipOption(true)
    M.farclip = 1500
    roys(M, { 7002, 0, 20000 })
    roys(M, { 7002, 1, 60000 })
    H.eq(M.farclip, 1500)
    H.eq(M.env.BleakholdDB.royaleFarclipRestore, nil)
end)

test("royale drop: a farclip the player changes during the match is theirs; turning the option off restores at once",
function(M, ns)
    connect(M)
    roys(M, { [2] = 0, [3] = 20000 })
    roys(M, { [2] = 1, [3] = 60000 })
    H.eq(M.farclip, 1277)
    ns.RoyaleDrop.SetFarclipOption(false)
    H.eq(M.farclip, 777, "off: back at once")
    ns.RoyaleDrop.SetFarclipOption(true)
    -- a new match: raised, then the player picks 900 in the options
    roys(M, { 7002, 0, 20000 })
    roys(M, { 7002, 1, 60000 })
    H.eq(M.farclip, 1277)
    M.farclip = 900
    roys(M, { 7002, 7, 0 })
    H.eq(M.farclip, 900, "the player's choice stays")
    H.eq(M.env.BleakholdDB.royaleFarclipRestore, nil)
end)

test("royale drop: no raise when the client first sees phase 1 in the last 16 s (no hitch on the countdown)",
function(M, ns)
    connect(M)
    roys(M, { [2] = 1, [3] = 12000 })
    H.eq(M.farclip, 777)
end)

------------------------------------------------------------------------------------------------------
-- Preview
------------------------------------------------------------------------------------------------------
test("royale drop: RD.Preview plays a whole sample drop outside a match, not during one", function(M, ns)
    local RD = ns.RoyaleDrop
    H.ok(RD.Preview(), "a sample drop")
    M.Advance(0.9)
    H.ok(M.env.BleakholdRoyaleDrop:IsShown())
    H.eq(RD.plate.num:GetValue(), "8")
    M.Advance(8)
    H.eq(RD.plate.cpLine:GetText(), "Landing in 12")
    M.Advance(12.0)
    H.ok(RD.plate.landed:GetAlpha() > 0.99, "LANDED")
    M.Advance(1.5)
    H.ok(not M.env.BleakholdRoyaleDrop:IsShown())
    H.eq(RD.sample, nil)
    connect(M)
    roys(M, { [2] = 1, [3] = 30000 })
    H.ok(not RD.Preview(), "refused during a match")
end)
