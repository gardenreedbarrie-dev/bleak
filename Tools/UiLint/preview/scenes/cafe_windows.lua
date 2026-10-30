-- The café's windows (CafeWindow.lua, CafeMenu.lua) in demo mode, the café's demo server answering (Cafe.lua):
--
--   Tools/UiLint/preview/render.sh Tools/UiLint/preview/scenes/cafe_windows.lua shift out.png --stock <stock art>
--
-- The café window: shift (the shift offer, off shift, the hero machine's box; patch-4 present), shift_onshift (End
-- shift, the Rush), shift_nopatch (no patch-4: the stations in a ring), recipes, recipes_coffee, board (this week),
-- board_last (last week's board, the side panel retitled), rewards, help. The menu: menu (a drink chosen, +10% tip),
-- menu_confirm (the café's own confirmation, beside the menu), menu_order (an order being made), menu_cap (the café
-- full).
-- The summary card: summary (with the Staff Drink), summary_plain, summary_pending (the Staff Drink asked for),
-- summary_gated (chosen right after End Shift); shift_claim (the Shift tab's Claim Staff Drink), shift_tired (Tired
-- off shift), shift_capped (the day's XP capped). The developer's model viewer: model.
local S = {}
S.before = {}

local function demo(M, ns)
    M.playerLevel = 70
    -- in Stormwind as the client tells it: the world map's area of the zone
    M.zone = "Stormwind City"
    M.env.SetMapToCurrentZone = function() end
    M.env.GetCurrentMapAreaID = function()
        return 301
    end
    M.FireEvent("ZONE_CHANGED_NEW_AREA")
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1.5)
end

-- the café window on a tab; after(M, ns, env, P) runs once it is open, and what it returns is drawn instead
local function tab(key, after)
    return function(M, ns, RS, env, P)
        demo(M, ns)
        ns.UI.Open(key)
        M.Advance(1)
        local frames = after and after(M, ns, env, P)
        M.Advance(0.3)
        return frames or env.BleakholdCafeFrame
    end
end

S.shift = tab("cafeshift")
S.shift_onshift = tab("cafeshift", function(M, ns, env, P)
    ns.CafeWindow.shift.button:Click()
    M.Advance(1)
end)
S.shift_nopatch = tab("cafeshift")
S.recipes = tab("caferecipes")
S.recipes_coffee = tab("caferecipes", function(M, ns, env, P)
    ns.CafeWindow.recipes.filter.buttons[2]:Click()
    P.hover(ns.CafeWindow.recipes.cards.items[3])
end)
S.board = tab("cafeboard", function(M, ns, env, P)
    M.Advance(0.5)
    P.hover(ns.CafeWindow.board.table.rows[3])
end)
S.board_last = tab("cafeboard", function(M, ns, env, P)
    M.Advance(0.5)
    ns.CafeWindow.board.weekSel.buttons[2]:Click()
    M.Advance(0.5)
    -- last week's own board (the demo server answers every week alike): Brenna first as CAFP L has her, you third
    local t = env.time() - 7 * 86400
    ns.Demo.Push("LB", { { "C", 2963, 1, 0, 1, 1 },
        { 1, 1, 2480, 834, t, { { "Brenna", 2 } }, "151 drinks" },
        { 2, 1, 1710, 742, t - 1800, { { "Dalia", 8 } }, "92 drinks" },
        { 3, 1, 1520, 770, t - 5400, { { ns.PlayerName() or "Aldric", 1 } }, "81 drinks" },
        { 4, 1, 990, 610, t - 9000, { { "Korrin", 4 } }, "58 drinks" } })
    ns.Demo.Push("LBME", { { "C", 3, 60, 1520, 1, 770, 613, "81 drinks" } })
    M.Advance(0.5)
end)
S.rewards = tab("caferewards")
S.help = tab("cafehelp")

-- the menu, a drink chosen with a tip
local function menu(after)
    return function(M, ns, RS, env, P)
        demo(M, ns)
        ns.UI.Open("cafemenu")
        M.Advance(1)
        local MN = ns.CafeMenu
        for i = 1, MN.rows.used do
            local r = MN.rows.items[i]
            if r.recipeId == 103 then
                r:Click()
            end
        end
        MN.tipChoice.buttons[2]:Click()
        M.Advance(0.3)
        local frames = after and after(M, ns, env, P, MN)
        M.Advance(0.3)
        return frames or env.BleakholdCafeMenu
    end
end
S.menu = menu(function(M, ns, env, P, MN)
    P.hover(MN.rows.items[5])
end)
S.menu_confirm = menu(function(M, ns, env, P, MN)
    MN.order:Click()
    return { env.BleakholdCafeMenu, env.BleakholdCafeConfirm }
end)
S.menu_order = menu(function(M, ns, env, P, MN)
    MN.order:Click()
    env.BleakholdCafeConfirm.ok:Click()
    M.Advance(8)
end)
S.menu_cap = menu(function(M, ns, env, P, MN)
    ns.Demo.Push("CAFM", { { 1, 1, 0, 45, 0, 12, 12, 0, "cafe_cap" }, { 101, 3500, 0, 1 }, { 102, 3500, 0, 1 },
        { 103, 5300, 0, 1 }, { 104, 5300, 0, 1 }, { 105, 7900, 0, 1 }, { 106, 7900, 0, 1 }, { 107, 15800, 0, 1 } })
    M.Advance(0.3)
end)

-- the summary card, as a shift ends
local function summary(staff, reason)
    return function(M, ns, RS, env, P)
        demo(M, ns)
        ns.Demo.Push("CAFST", { { 0, 0, 7, 2400, 2320, 3220 }, { "D", 450, 450, 450, 64000, 180000, 380, 400, 22 } })
        ns.Demo.Push("CAFSUM", { { 1, reason, 2460, 22, 15, 21400, 386, 40, 380, 6, staff and 1 or 0 } })
        M.Advance(0.5)
        if staff then
            P.hover(ns.CafeWindow.summary.staff.choices[2])
        end
        return env.BleakholdCafeSummary
    end
end
-- the Staff Drink asked for (CSTAFF sent, no answer yet)
S.summary_pending = function(M, ns, RS, env, P)
    demo(M, ns)
    ns.Demo.Push("CAFST", { { 0, 0, 7, 2400, 2320, 3220, "", "", "", "", "", "", "", "", "", "", "", 16 },
        { "D", 450, 450, 450, 64000, 180000, 380, 400, 22 } })
    ns.Demo.Push("CAFSUM", { { 1, "E", 2460, 22, 15, 21400, 386, 40, 380, 6, 1 } })
    M.Advance(0.5)
    ns.CafeWindow.StaffPending("C")
    M.Advance(0.1)
    return env.BleakholdCafeSummary
end
-- the Shift tab with today's Staff Drink still to claim (CAFST flag 16, the card closed)
S.shift_claim = tab("cafeshift", function(M, ns, env, P)
    ns.Demo.Push("CAFST", { { 0, 0, 7, 2400, 2320, 3220, "", "", "", "", "", "", "", "", "", "", "", 16 },
        { "D", 450, 450, 450, 64000, 180000, 380, 400, 22 } })
    M.Advance(0.5)
end)
-- off shift and Tired (CAFST flag 4, 9:20 of rest still needed): the Shift tab says so before Start Shift
S.shift_tired = tab("cafeshift", function(M, ns, env, P)
    ns.Demo.Push("CAFST", { { 0, 0, 7, 2400, 2320, 3220, "", "", "", "", "", "", "", "", "", "", 560, 4 },
        { "D", 560, 450, 450, 64000, 180000, 380, 400, 22 } })
    M.Advance(0.5)
end)
-- the day's XP capped (675 credited of 450 + 225)
S.shift_capped = tab("cafeshift", function(M, ns, env, P)
    ns.Demo.Push("CAFST", { { 0, 0, 7, 2400, 2320, 3220 }, { "D", 675, 450, 450, 180000, 180000, 400, 400, 41 } })
    M.Advance(0.5)
end)
-- the Staff Drink chosen right after End Shift: shown as asked at once, sent when the shared gate opens
S.summary_gated = function(M, ns, RS, env, P)
    demo(M, ns)
    ns.Cafe.Send("CSHIFT", 1, 0)
    ns.Demo.Push("CAFST", { { 0, 0, 7, 2400, 2320, 3220, "", "", "", "", "", "", "", "", "", "", "", 16 },
        { "D", 450, 450, 450, 64000, 180000, 380, 400, 22 } })
    ns.Demo.Push("CAFSUM", { { 1, "E", 2460, 22, 15, 21400, 386, 40, 380, 6, 1 } })
    M.Advance(0.5)
    ns.CafeWindow.summary.staff.choices[1]:Click()
    M.Advance(0.1)
    return env.BleakholdCafeSummary
end
S.summary = summary(true, "E")
S.summary_plain = summary(false, "C")

S.model = function(M, ns, RS, env, P)
    demo(M, ns)
    ns.CafeWindow.ShowModelViewer("EspressoSW")
    M.Advance(0.3)
    return env.BleakholdCafeModelViewer
end

-- patch-4's café icons (BH_Cafe_*) exist only in that patch: every scene but the two with the 3D model shows a client
-- without it, so the stock icons stand in (Cafe.PatchPresent probes BH_Cafe_Espresso once)
local function noPatch(M)
    M.missingTextures["Interface\\Icons\\BH_Cafe_Espresso"] = true
end
for name in pairs(S) do
    if name ~= "before" and name ~= "shift" and name ~= "shift_onshift" then
        S.before[name] = noPatch
    end
end

return S
