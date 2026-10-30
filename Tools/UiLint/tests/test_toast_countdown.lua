-- The toast (Toast.lua, TOP -110, HIGH strata) and the keystone countdown (Countdown.lua, 420 x 270 from TOP -80,
-- DIALOG strata) share the top of the screen: the countdown's head and bar would sit on the toast's name and sub line.
-- The right-click's "Keystone ready" toast (bh_ui_bridge.cpp) goes when the countdown starts, and the other toasts wait
-- for the countdown to go.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local READY = { "K", "Keystone ready", "Press Start keystone in the Keys window", "keys" }

test("toast: the keystone countdown drops the 'Keystone ready' toast and holds the others until it goes",
    function(M, ns)
    FX.connect(M, H)
    local t, cd = M.env.BleakholdToastFrame, M.env.BleakholdCountdown
    H.send(M, "TOAST", { READY })
    H.ok(t:IsShown())
    H.eq(t.title:GetText(), "Keystone ready")
    ns.Toast.Push({ kicker = "Queue", title = "Behind it", sub = "x" })
    M.Advance(1)
    -- Start keystone at once: the countdown (MPS, 10 s)
    H.send(M, "MPS", FX.examples(M).MPS)
    H.ok(cd:IsShown())
    H.ok(not t:IsShown(), "no toast under the countdown")
    H.eq(ns.Toast.Pending(), 1, "the ready toast gone, the other waiting")
    M.Advance(5)
    H.ok(not t:IsShown(), "still waiting")
    -- a toast that comes in during the countdown waits too
    ns.Toast.Push({ kicker = "Queue", title = "During it", sub = "y" })
    M.Advance(0.6)
    H.ok(not t:IsShown())
    H.eq(ns.Toast.Pending(), 2)
    M.Advance(5)
    H.ok(not cd:IsShown(), "the run started")
    H.ok(t:IsShown(), "the waiting toast shows once the countdown is gone")
    H.eq(t.title:GetText(), "Behind it")
    M.Advance(ns.Toast.SHOW_TIME + 0.1)
    H.eq(t.title:GetText(), "During it")
end)

test("toast: one showing when the countdown starts comes back whole after it", function(M, ns)
    FX.connect(M, H)
    local t, cd = M.env.BleakholdToastFrame, M.env.BleakholdCountdown
    ns.Toast.Push({ kicker = "Queue", title = "Your group is ready", sub = "Accept in Activities - Dungeons" })
    M.Advance(2)
    H.send(M, "MPS", FX.examples(M).MPS)
    M.Advance(0.1)
    H.ok(cd:IsShown())
    H.ok(not t:IsShown(), "put back while the countdown shows")
    H.eq(ns.Toast.Pending(), 1)
    M.Advance(10.5)
    H.ok(not cd:IsShown())
    H.ok(t:IsShown())
    H.eq(t.title:GetText(), "Your group is ready")
    -- a "keys" toast that is not the ready one (ToastChampions) is not dropped by the countdown
    M.Advance(ns.Toast.SHOW_TIME + 0.1)
    H.send(M, "TOAST", { { "K", "1 Mythic Champion left", "The key ends when it falls", "keys" } })
    ns.Toast.Dismiss("keys", "Keystone ready")
    H.ok(t:IsShown())
    H.eq(t.title:GetText(), "1 Mythic Champion left")
end)
