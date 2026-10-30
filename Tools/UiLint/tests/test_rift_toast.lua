-- The toast's text in the alert's dark band (Toast.lua): the server's Rift toasts (bh_ui_bridge_map.cpp RiftEndToast,
-- RiftFloorToast) carry what was won and what to do next in the sub line, so it is drawn under the name (dim, one
-- line); a name or sub too long for the band steps its font down (13, 12, 11 and 11, 10) before the client cuts it,
-- and the tooltip keeps both whole.
local GREY = 0xBF / 255

local function size(fs)
    local _, px = fs:GetFont()
    return px
end

local function toast(M, H, title, sub, kind)
    H.send(M, "TOAST", { { kind or "I", title, sub, "rift" } })
    M.Advance(0.5)
    return M.env.BleakholdToastFrame
end

test("rift toast: the run-over toast shows its rewards on the alert, its title fitted to the band", function(M, ns)
    H.hello(M)
    M.Advance(0.3)
    local t = toast(M, H, "Eclipse Rift over - floor 9 cleared", "+72 Mythic Coins, a Rift Cache", "R")
    H.ok(t:IsShown())
    H.eq(t.kicker:GetText(), "New Record")
    H.eq(t.title:GetText(), "Eclipse Rift over - floor 9 cleared", "the whole title")
    H.ok(size(t.title) < 13, "a 35-character title steps its font down: " .. size(t.title))
    H.eq(t.title:GetWidth(), ns.Toast.TEXT_W, "in the band's width")
    -- the sub line on the alert, dim, under the name
    H.ok(t.sub:IsShown(), "the sub line is drawn")
    H.eq(t.sub:GetText(), "+72 Mythic Coins, a Rift Cache")
    H.eq(size(t.sub), 11)
    local r, g, b = t.sub:GetTextColor()
    H.ok(math.abs(r - GREY) < 0.01 and math.abs(g - GREY) < 0.01 and math.abs(b - GREY) < 0.01, "dim")
    local _, _, _, kx, ky = t.kicker:GetPoint(1)
    local _, _, _, tx, ty = t.title:GetPoint(1)
    local _, _, _, sx, sy = t.sub:GetPoint(1)
    H.ok(kx == 82 and tx == 82 and sx == 82, "one left edge")
    H.ok(ky == -26 and ty == -38 and sy == -52, "kicker, name and sub in the dark band (27-62)")
    H.eq(t.sub:GetHeight(), 14, "one line")
    -- the tooltip has both whole
    M.Hover(t)
    H.eq(M.env.GameTooltip.__lines[1], "Eclipse Rift over - floor 9 cleared")
    H.eq(M.env.GameTooltip.__lines[2], "+72 Mythic Coins, a Rift Cache")
end)

test("rift toast: a new floor names the boss to find on the alert", function(M, ns)
    H.hello(M)
    M.Advance(0.3)
    local t = toast(M, H, "Eclipse Rift - floor 7", "Find and defeat Echo of Nefarian")
    H.eq(size(t.title), 13, "a short title keeps 13")
    H.ok(t.sub:IsShown())
    H.eq(t.sub:GetText(), "Find and defeat Echo of Nefarian")
end)

test("rift toast: the font steps 13, 12, 11 for the name and 11, 10 for the sub, then the client cuts", function(M, ns)
    local T = ns.Toast
    local f = T.frame
    local w = T.TEXT_W
    local function needs(px, s)
        f.title:SetFont(ns.UI.FONT_BODY, px, "")
        f.title:SetText(s)
        return f.title:GetStringWidth() <= w
    end
    -- the longest name that fits at each size, then one that fits at none (a server title is at most 60 bytes)
    local fits12, fits11, none = nil, nil, string.rep("Long title ", 6)
    for n = 10, 60 do
        local s = string.rep("x", n)
        if not fits12 and not needs(13, s) and needs(12, s) then fits12 = s end
        if not fits11 and not needs(12, s) and needs(11, s) then fits11 = s end
    end
    H.ok(fits12 and fits11, "the mock measures widths")
    H.eq(T.Fit(f.title, "Short", T.TITLE_SIZES, w), 13)
    H.eq(T.Fit(f.title, fits12, T.TITLE_SIZES, w), 12)
    H.eq(T.Fit(f.title, fits11, T.TITLE_SIZES, w), 11)
    H.eq(T.Fit(f.title, none, T.TITLE_SIZES, w), 11, "the smallest, cut by the client")
    H.eq(f.title:GetText(), none, "the text is kept whole (the client draws the '...')")
    H.eq(f.title:GetHeight(), 14, "one line at the size used")
    H.eq(f.title:GetWidth(), w)
    H.eq(T.Fit(f.sub, string.rep("y", 36), T.SUB_SIZES, w), 10, "a long sub steps to 10")
    H.eq(T.Fit(f.sub, "", T.SUB_SIZES, w), 11)
    -- server text stays escaped
    T.Fit(f.title, "a|cffff0000b", T.TITLE_SIZES, w)
    H.eq(f.title:GetText(), "a||cffff0000b")
end)

test("rift toast: one toast at a time keeps its own sizes", function(M, ns)
    ns.Toast.Push({ kicker = "Bleakhold", title = "Eclipse Rift over - floor 12 cleared - long", sub = "x" })
    ns.Toast.Push({ kicker = "Bleakhold", title = "Short", sub = "Find and defeat Loken" })
    local t = M.env.BleakholdToastFrame
    H.eq(size(t.title), 11)
    M.Advance(ns.Toast.SHOW_TIME + 0.1)
    H.eq(t.title:GetText(), "Short")
    H.eq(size(t.title), 13, "the next toast starts at 13 again")
    H.eq(t.sub:GetText(), "Find and defeat Loken")
    H.eq(size(t.sub), 11)
end)
