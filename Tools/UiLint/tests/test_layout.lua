-- Layout rules of the 3.3.5a anchor system that the client applies silently.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

-- Point -> (x fraction, y fraction from the top).
local FP = { TOPLEFT = { 0, 0 }, TOP = { 0.5, 0 }, TOPRIGHT = { 1, 0 }, LEFT = { 0, 0.5 }, CENTER = { 0.5, 0.5 },
    RIGHT = { 1, 0.5 }, BOTTOMLEFT = { 0, 1 }, BOTTOM = { 0.5, 1 }, BOTTOMRIGHT = { 1, 1 } }

local function openAll(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    FX.openEverything(M, ns)
    ns.UI.Open("keys")
    ns.Keys.start:Click()
    M.Advance(20)
    ns.Toast.Push({ title = "x" })
end

test("no region mixes an edge anchor with a centre anchor on the same axis", function(M, ns)
    -- e.g. TOPLEFT + RIGHT fixes the top edge AND the vertical centre, so the client stretches the
    -- region down to the reference's middle; TOPLEFT + TOPRIGHT (or a width) is what was meant.
    openAll(M, ns)
    local bad = {}
    for _, o in ipairs(M.objects) do
        local pts = o.__points
        if pts and #pts >= 2 then
            local fy, fx = {}, {}
            for _, p in ipairs(pts) do
                fy[FP[p[1]][2]] = p[6]
                fx[FP[p[1]][1]] = p[6]
            end
            if fy[0.5] and (fy[0] or fy[1]) then
                bad[#bad + 1] = "vertical: " .. tostring(fy[0.5]) .. " with " .. tostring(fy[0] or fy[1])
            end
            if fx[0.5] and (fx[0] or fx[1]) then
                bad[#bad + 1] = "horizontal: " .. tostring(fx[0.5]) .. " with " .. tostring(fx[0] or fx[1])
            end
        end
    end
    H.ok(#bad == 0, #bad .. " mixed anchors:\n  " .. table.concat(bad, "\n  "))
end)

test("leaderboard columns fit the table on every board", function(M, ns)
    openAll(M, ns)
    local LB = ns.Leaderboards
    for _, board in ipairs({ "K", "R", "E", "F", "A" }) do
        LB.board = board
        LB.Refresh()
        local total = 10
        for i = 1, 6 do
            local cell = LB.table.rows[1].cells[i]
            if cell:IsShown() then total = total + cell:GetWidth() + 6 end
        end
        H.ok(total <= LB.table:GetWidth(), board .. ": columns " .. total .. " > table " .. LB.table:GetWidth())
    end
end)

test("filter bar: dropdowns start right of the last tab (all five tabs, Arena on)", function(M, ns)
    local LB = ns.Leaderboards
    FX.connect(M, H, { [6] = 65536 })
    LB.LayoutTabs()
    local lastTab = LB.tabs[#LB.tabs]
    H.eq(#LB.tabs, 5)
    for _, t in ipairs(LB.tabs) do
        H.ok(t:IsShown(), t.key .. " tab shown")
    end
    H.eq(select(4, lastTab:GetPoint(1)), 16 + 4 * LB.TAB_STEP)
    local tabRight = 16 + 4 * LB.TAB_STEP + lastTab:GetWidth()
    local barW = ns.UI.ContentSize(ns.Leaderboards.frame:GetWidth(), ns.Leaderboards.frame:GetHeight())
    local used = 16 + LB.filters.class:GetWidth() + 6 + 34 + 14 + LB.filters.dungeon:GetWidth() + 6 + 56
    H.ok(barW - used >= tabRight, "filters overlap the tabs: " .. (barW - used) .. " < " .. tabRight)
end)
