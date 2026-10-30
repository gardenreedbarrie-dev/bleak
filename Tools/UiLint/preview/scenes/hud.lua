-- Scenes of the small Bleakhold frames on the HUD, in demo mode: the toast, the Mythic+ key tracker, the keystone start
-- countdown, the camp frames, the War Front HUD and capture bar, the minimap buttons. Each returns only its frames:
--
--   Tools/UiLint/preview/render.sh Tools/UiLint/preview/scenes/hud.lua countdown out.png --stock <stock art>
--
-- Scenes: toast, toast_in (its glow 0.3 s in), toast_arena; keytracker, keytracker_over, keytracker_result;
-- countdown_bar (7.3 s), countdown_pop (2.9 s), countdown (2.55 s), countdown_dbm (DBM shows its bar); camp_frame,
-- camp_status, camp_glide, camp_glide_pressed (all three: camp); warfront; orbs (round a stand-in minimap: the client draws the real one).
-- The capture bar's art is the 3.3.5a Interface\WorldStateFrame\WorldState-CaptureBar (256 x 64); the retail exports
-- name a different atlas WorldStateCaptureBar, so without a 3.3.5a copy the bars show without their frame.
local S = {}

local function demo(M)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
end

local MPS = { 7001, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 }

S.toast = function(M, ns, RS, env, P)
    demo(M)
    ns.Toast.Push({ kicker = "Daily Task Complete", title = "Key sweeper", sub = "Claim 20 Mythic Coins in Activities",
        target = "tasks" })
    M.Advance(1)
    return env.BleakholdToastFrame
end

-- the glow and the shine of the toast as it comes in (0.3 s)
S.toast_in = function(M, ns, RS, env, P)
    demo(M)
    ns.Toast.Push({ kicker = "New Record", title = "Halls of Lightning +8", sub = "Rank 3 this season",
        target = "leaderboards" })
    M.Advance(0.3)
    return env.BleakholdToastFrame
end

S.toast_arena = function(M, ns, RS, env, P)
    demo(M)
    ns.Toast.Push({ kicker = "ARENA", title = "Rated 1v1 match found", sub = "Enter now", target = "arena" })
    M.Advance(1)
    return env.BleakholdToastFrame
end

S.keytracker = function(M, ns, RS, env, P)
    demo(M)
    ns.Demo.Push("MPS", { MPS })
    M.Advance(10.5)
    ns.Demo.Push("MP", { { 7001, 1122000, 1800, 2, 10, 64, 100, 1, { 300 }, { 1260, 1440 }, 1 } })
    M.Advance(0.3)
    return env.BleakholdKeyTracker
end

S.keytracker_over = function(M, ns, RS, env, P)
    demo(M)
    ns.Demo.Push("MPS", { MPS })
    M.Advance(10.5)
    ns.Demo.Push("MP", { { 7001, 1900000, 1800, 6, 30, 100, 100, 15, { 300, 600, 900, 1200 }, { 1260, 1440 }, 1 } })
    M.Advance(0.3)
    return env.BleakholdKeyTracker
end

S.keytracker_result = function(M, ns, RS, env, P)
    demo(M)
    ns.Demo.Push("MPS", { MPS })
    M.Advance(10.5)
    ns.Demo.Push("MP", { { 7001, 1500000, 1800, 2, 10, 100, 100, 15, { 300, 600, 900, 1200 }, { 1260, 1440 }, 1 } })
    M.Advance(0.3)
    ns.Demo.Push("MPE", { { 7001, 1, 1500000, 1, 599, 9, 1840 }, { "T", 1, "", "Spoils chest (in your bags)" },
        { "C", 150 } })
    M.Advance(0.3)
    return env.BleakholdKeyTracker
end

-- the keystone countdown: at 7.3 s the bar only, at 2.9 s the numeral popping in, at 2.6 s settled
local function countdown(after)
    return function(M, ns, RS, env, P)
        demo(M)
        ns.Demo.Push("MPS", { MPS })
        M.Advance(after, 0.05)
        return env.BleakholdCountdown
    end
end
S.countdown_bar = countdown(2.7)
S.countdown_pop = countdown(7.12)
S.countdown = countdown(7.45)

S.countdown_dbm = function(M, ns, RS, env, P)
    M.SetGroup("PARTY", 5, false)
    -- DBM showing its "Pull in" bar (its bar module finds it by name): ours hides
    env.DBM = { Options = {}, Bars = { GetBar = function(_, name) return name == "Pull in" and {} or nil end } }
    demo(M)
    ns.Demo.Push("MPS", { MPS })
    M.Advance(7.45, 0.05)
    return env.BleakholdCountdown
end

S.camp = function(M, ns, RS, env, P)
    demo(M)
    local CP = ns.Camp
    CP.preview = true
    CP.SAMPLE.recvAt = env.GetTime()
    CP.Refresh()
    CP.indPreview = true
    CP.RefreshIndicator()
    CP.glidePreview = true
    CP.RefreshGlide()
    M.Advance(0.3)
    return { env.BleakholdCampFrame, env.BleakholdCampStatus, env.BleakholdGlideButton, CP.glideBar }
end

local function campScene(pick)
    return function(M, ns, RS, env, P)
        demo(M)
        local CP = ns.Camp
        CP.preview = true
        CP.SAMPLE.recvAt = env.GetTime()
        CP.Refresh()
        CP.indPreview = true
        CP.RefreshIndicator()
        CP.glidePreview = true
        CP.RefreshGlide()
        M.Advance(0.3)
        return pick(env, CP, P)
    end
end
S.camp_frame = campScene(function(env) return env.BleakholdCampFrame end)
S.camp_status = campScene(function(env) return env.BleakholdCampStatus end)
S.camp_glide = campScene(function(env, CP, P)
    P.hover(env.BleakholdGlideButton)
    return { env.BleakholdGlideButton, CP.glideBar }
end)
-- pressed: the Depress overlay (ARTWORK) over the icon (BACKGROUND), as ActionButtonTemplate draws it
S.camp_glide_pressed = campScene(function(env, CP, P)
    local gb = env.BleakholdGlideButton
    P.hover(gb)
    gb:SetButtonState("PUSHED", true)
    return { gb, CP.glideBar }
end)

S.warfront = function(M, ns, RS, env, P)
    demo(M)
    local WF = ns.WarFront
    WF.preview = true
    WF.SAMPLE.recvAt = env.GetTime()
    WF.capPreview = true
    WF.CAP_SAMPLE.recvAt = env.GetTime()
    WF.Tick()
    M.Advance(0.25)
    return { env.BleakholdWarFront, env.BleakholdWarCapture }
end

-- the minimap buttons round a stand-in minimap (the stock minimap and its border are drawn by the client)
S.orbs = function(M, ns, RS, env, P)
    demo(M)
    ns.Orbs.SetShown(true)
    ns.Orbs.Refresh()
    ns.Orbs.Layout(true)
    local mm = env.Minimap
    mm:ClearAllPoints()
    mm:SetPoint("CENTER", env.UIParent, "CENTER", 0, 0)
    ns.Orbs.Layout(true)
    local stand = env.CreateFrame("Frame", nil, env.UIParent)
    stand:SetAllPoints(mm)
    stand:SetFrameStrata("LOW")
    -- the rim: a larger disc under the map's (its own layer: one layer is not drawn in creation order, Widgets.lua)
    local rim = stand:CreateTexture(nil, "BACKGROUND")
    rim:SetTexture(ns.UI.ART .. "Disc")
    rim:SetPoint("TOPLEFT", stand, "TOPLEFT", -6, 6)
    rim:SetPoint("BOTTOMRIGHT", stand, "BOTTOMRIGHT", 6, -6)
    rim:SetVertexColor(0.55, 0.5, 0.4)
    local disc = stand:CreateTexture(nil, "BORDER")
    disc:SetTexture(ns.UI.ART .. "Disc")
    disc:SetAllPoints(stand)
    disc:SetVertexColor(0.24, 0.30, 0.18)
    P.hover(env.BleakholdOrb_season)
    return { stand, env.BleakholdOrbHolder }
end

return S
