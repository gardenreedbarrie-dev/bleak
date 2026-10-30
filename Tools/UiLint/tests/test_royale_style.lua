-- Bleakhold Royale's style kit (RoyaleStyle.lua): pixels per unit and snapping on the screens players use, the font
-- rules (the rasteriser's 32 px ceiling, 12 px labels, FRIZQT under 13 px and when the client refuses a face), the
-- texel ratio of every numeral, title, icon, ring and rotatable size the design uses, SetRotation on the rotatable
-- art only, the tween driver that sleeps when idle, the tween kinds and eases, lazy textures, numerals on their shared
-- baseline, titles, plates, buttons, icons, the clock, sounds, the HUD scale and the loops.

local ROYALE_ART = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\"

local function near(a, b, eps, msg)
    if type(a) ~= "number" or math.abs(a - b) > (eps or 1e-6) then
        error((msg or "values differ") .. ": expected " .. tostring(b) .. ", got " .. tostring(a), 2)
    end
end

-- An anonymous root frame under UIParent, hidden unless `shown`.
local function newRoot(M, shown)
    local f = M.env.CreateFrame("Frame", nil, M.env.UIParent)
    f:SetSize(600, 400)
    f:SetPoint("CENTER", M.env.UIParent, "CENTER", 0, 0)
    if not shown then
        f:Hide()
    end
    return f
end

-- Width and height in texels of an Art\Royale file (TGA header, or BLP2 header).
local dims = {}
local function fileDims(path)
    if dims[path] then
        return dims[path][1], dims[path][2]
    end
    local rel = path:match("^Interface\\AddOns\\Bleakhold\\(.+)$"):gsub("\\", "/")
    local s = host_readfile(addonDir .. "/" .. rel .. ".tga")
    local w, h
    if s then
        w, h = s:byte(13) + s:byte(14) * 256, s:byte(15) + s:byte(16) * 256
    else
        s = assert(host_readfile(addonDir .. "/" .. rel .. ".blp"), "no art file for " .. path)
        assert(s:sub(1, 4) == "BLP2", path .. ": BLP2 expected")
        local function u32(o)
            return s:byte(o + 1) + s:byte(o + 2) * 256 + s:byte(o + 3) * 65536 + s:byte(o + 4) * 16777216
        end
        w, h = u32(12), u32(16)
    end
    dims[path] = { w, h }
    return w, h
end

-- Texels per physical pixel down a texture's height (the art's UL -> LL side in texel space, also when turned).
local function texelRatio(RS, t)
    local w, h = fileDims(t.rsPath)
    local ulx, uly, llx, lly = t:GetTexCoord()
    local texels = math.sqrt(((llx - ulx) * w) ^ 2 + ((lly - uly) * h) ^ 2)
    return texels / (t:GetHeight() * RS.PxPerUnit(t))
end

-- Every shown, sized texture the kit gave Royale art (9-slice edges and centres are sized by anchors and stretch by
-- design, so they are left out).
local function royaleTextures(M)
    local out = {}
    for _, o in ipairs(M.objects) do
        if o.__otype == "Texture" and type(o.rsPath) == "string" and o.rsPath:find(ROYALE_ART, 1, true) == 1
            and o.__shown and o:GetHeight() > 0 then
            out[#out + 1] = o
        end
    end
    return out
end

local function fontOf(fs)
    local path, size, flags = fs:GetFont()
    return path, size, flags
end

------------------------------------------------------------------------------------------------------

test("royale style: loaded before Royale.lua with the new modules, and the palette is the design's", function(M, ns)
    local RS = ns.RoyaleStyle
    H.ok(RS, "ns.RoyaleStyle")
    local order = {}
    for i, f in ipairs(M.loaded) do order[f] = i end
    H.ok(order["RoyaleArtData.lua"] < order["RoyaleStyle.lua"], "the art data before the kit")
    H.eq(order["RoyaleStyle.lua"] + 1, order["Royale.lua"], "the kit right before Royale.lua")
    for _, f in ipairs({ "RoyaleCountdown.lua", "RoyaleDrop.lua", "RoyaleMinimap.lua" }) do
        H.ok(order[f] and order[f] > order["Royale.lua"], f .. " loaded after Royale.lua")
    end
    H.ok(type(ns.RoyaleCountdown) == "table" and type(ns.RoyaleDrop) == "table" and type(ns.RoyaleMinimap) == "table",
        "the three modules exist")
    local design = {
        ironTop = "1E2127", ironBottom = "121418", bronzeHi = "F3DDA4", bronze = "C9A25A", bronzeLo = "7A5A2C",
        bronzeDeep = "3B2A14", parchment = "F2E8D0", ash = "BDB4A0", smoke = "8A8273", gold = "E5C07B",
        storm = "A66BE0", stormLight = "D7B6FF", stormDeep = "4B2A6E", safe = "FFFFFF", ember = "FF7A3D",
        blood = "E5604F", beast = "8FD14F",
    }
    for k, v in pairs(design) do
        H.eq(RS.C[k], v, "token " .. k)
    end
    local r, g, b, a = RS.Rgb("gold")
    near(r, 0xE5 / 255); near(g, 0xC0 / 255); near(b, 0x7B / 255); H.eq(a, 1)
    local r2 = RS.Rgb("80FF00", 0.5)
    near(r2, 0x80 / 255)
    H.eq(RS.Hex("storm"), "A66BE0")
    H.eq(RS.Color("ember", "x"), "|cffFF7A3Dx|r")
end)

test("royale style: pixels per unit at 1080p (UI scale 1 and 0.64), the exe's screen first, the cache refreshed",
    function(M, ns)
    local RS = ns.RoyaleStyle
    M.SetScreen(1920, 1080, 1)
    near(RS.PxPerUnit(M.env.UIParent), 1.40625)
    near(RS.PxPerUnit(), 1.40625, 1e-6, "nil means UIParent")
    near(RS.Snap(10.3), 14 / 1.40625)
    near(RS.MaxTextUnits(), 32 / 1.40625)
    M.SetScreen(1920, 1080, 0.64)
    near(RS.PxPerUnit(M.env.UIParent), 0.9)
    near(RS.Snap(10.3), 10)
    -- a frame scaled 1.2 under UIParent: its textures and font strings use its scale
    local f = M.env.CreateFrame("Frame", nil, M.env.UIParent)
    f:SetScale(1.2)
    local t, fs = f:CreateTexture(nil, "ARTWORK"), f:CreateFontString(nil, "OVERLAY")
    near(RS.PxPerUnit(f), 1.08)
    near(RS.PxPerUnit(t), 1.08)
    near(RS.PxPerUnit(fs), 1.08)
    -- Bleakhold.exe's own pixel size wins over gxResolution (a resized window), at once
    M.env.BleakholdUI_ScreenPixels = function() return 2560, 1440 end
    near(RS.PxPerUnit(M.env.UIParent), 0.64 * 1440 / 768)
    M.env.BleakholdUI_ScreenPixels = function() return nil end
    near(RS.PxPerUnit(M.env.UIParent), 0.9, 1e-6, "a nil answer falls back to gxResolution")
    M.env.BleakholdUI_ScreenPixels = nil
    -- the CVar is cached until the client says the screen or a CVar changed
    M.cvars.gxResolution = "3840x2160"
    near(RS.PxPerUnit(M.env.UIParent), 0.9, 1e-6, "cached")
    M.FireEvent("DISPLAY_SIZE_CHANGED")
    near(RS.PxPerUnit(M.env.UIParent), 0.64 * 2160 / 768)
    M.cvars.gxResolution = "2560x1440"
    M.FireEvent("CVAR_UPDATE", "USE_UISCALE", "1")
    near(RS.PxPerUnit(M.env.UIParent), 0.64 * 1440 / 768)
    -- the text ceiling at UI scale 1
    M.SetScreen(2560, 1440, 1)
    near(RS.MaxTextUnits(), 32 / 1.875)
    M.SetScreen(3840, 2160, 1)
    near(RS.MaxTextUnits(), 32 / 2.8125)
    -- without a UI scale the client scales UIParent to 0.9 at 1080p
    M.SetScreen(1920, 1080)
    near(RS.PxPerUnit(M.env.UIParent), 0.9 * 1080 / 768)
end)

test("royale style: FRIZQT when the client refuses a face; labels at least 12 px and FRIZQT under 13 px; 32 px top",
    function(M, ns)
    local RS = ns.RoyaleStyle
    local root = newRoot(M, true)
    M.SetScreen(1920, 1080, 1)
    local label = RS.Text(root, "label", 10)
    local path, size, flags = fontOf(label)
    H.eq(path, RS.FONT_SC, "Marcellus SC at 14 px")
    near(size, 10)
    H.eq(flags, "")
    local lr, lg, lb = label:GetTextColor()
    near(lr, 0xBD / 255, 1e-6, "labels are ash by default")
    -- the client cannot load the face: FRIZQT at the same size
    M.missingFonts[RS.FONT_SC] = true
    local refused = RS.Text(root, "label", 10)
    path, size = fontOf(refused)
    H.eq(path, RS.FONT_BODY, "FRIZQT fallback")
    near(size, 10)
    M.missingFonts[RS.FONT_SC] = nil
    -- 1080p at UI scale 0.64: 10 units are 9 px, raised to 12 px (13.3 units), FRIZQT under 13 px
    M.SetScreen(1920, 1080, 0.64)
    path, size = fontOf(label)
    H.eq(path, RS.FONT_BODY, "the label set at UI scale 1 follows the new scale")
    near(size, 12 / 0.9)
    local small = RS.Text(root, "label", 10)
    path, size = fontOf(small)
    H.eq(path, RS.FONT_BODY)
    near(size * RS.PxPerUnit(small), 12, 1e-6, "12 physical px")
    local heading = RS.Text(root, "heading", 16)
    path, size, flags = fontOf(heading)
    H.eq(path, RS.FONT_SC, "a 16-unit heading is 14.4 px: Marcellus SC")
    H.eq(flags, "OUTLINE")
    -- values are clamped to the rasteriser's 32 px: 20 units are 37.5 px at 1440p
    M.SetScreen(2560, 1440, 1)
    local value = RS.Text(root, "value", 20, "ember", "CENTER")
    path, size, flags = fontOf(value)
    H.eq(path, RS.FONT_BODY); H.eq(flags, "OUTLINE")
    near(size, 32 / 1.875)
    local vr = value:GetTextColor()
    near(vr, 1, 1e-6, "ember")
    M.SetScreen(3840, 2160, 1)
    near(select(2, fontOf(value)), 32 / 2.8125, 1e-6, "re-clamped at 2160p")
    M.SetScreen(1920, 1080, 1)
    near(select(2, fontOf(value)), 20, 1e-6, "back to 20 units at 1080p")
    -- every font string the kit made: within 12-32 px for labels and headings, at most 32 px for all
    for _, res in ipairs({ { 1920, 1080, 1 }, { 1920, 1080, 0.64 }, { 2560, 1440, 1 }, { 3840, 2160, 1 } }) do
        M.SetScreen(res[1], res[2], res[3])
        for fs in pairs(RS.made.fonts) do
            local p, s = fontOf(fs)
            local px = s * RS.PxPerUnit(fs)
            H.ok(px <= 32 + 1e-6, "at most 32 px: " .. px)
            if fs.rsRole == "label" or fs.rsRole == "heading" then
                H.ok(px >= 12 - 1e-6, "labels at least 12 px: " .. px)
                H.eq(p == RS.FONT_SC, px >= 13 - 1e-6, "Marcellus SC from 13 px")
            end
        end
    end
end)

test("royale style: every numeral, title, DROP!, icon, ring and rotatable size is at most 2.2x minified",
    function(M, ns)
    local RS = ns.RoyaleStyle
    local root = newRoot(M, true)
    -- the sizes the design uses (section 1.6 and the screens)
    for _, cap in ipairs({ 22, 30, 34, 112, 150, 172 }) do
        RS.Numeral(root, { cap = cap, value = cap >= 100 and 15 or 8 })
    end
    RS.Numeral(root, { cap = 22, value = "#7", justify = "RIGHT" })
    for _, cap in ipairs({ 21, 22, 26, 30, 32 }) do
        RS.Title(root, "THUNDERMAW AWAKENS", cap, "beast")
        RS.Title(root, "VICTORY", cap, "gold")
    end
    RS.DropWord(root, 96)
    for _, size in ipairs({ 12, 14, 16, 18, 22, 24, 26, 28, 40, 44 }) do
        RS.Icon(root, "storm", size)
    end
    RS.Art(root, "CountRingSmall", 72)
    RS.Art(root, "ShockSmall", 60)
    RS.Art(root, "ShockSmall", 72)
    RS.Art(root, "Gem", 12, 12, nil, ns.RoyaleArt.gem.socket)
    RS.Art(root, "Parachute", 44, 44, nil, ns.RoyaleArt.parachute.pack)
    RS.Rotatable(root, "Notch", 22):SetAngle(1.2)
    RS.Rotatable(root, "You", 22):SetAngle(-0.4)
    RS.Rotatable(root, "Arrow", 26)
    RS.Rotatable(root, "EdgeTick", 12):SetAngle(3)
    local plate = M.env.CreateFrame("Frame", nil, root)
    plate:SetSize(384, 72)
    RS.Plate(plate, "Plate")
    RS.Plate(plate, "PlateTab")
    RS.Button(root, 120, 28, "Queue again", "gold")
    -- and whatever the addon's own Royale frames made
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    for _, res in ipairs({ { 1920, 1080 }, { 2560, 1440 } }) do
        M.SetScreen(res[1], res[2], 1)
        local list = royaleTextures(M)
        H.ok(#list >= 60, "textures measured: " .. #list)
        for _, t in ipairs(list) do
            local ratio = texelRatio(RS, t)
            H.ok(ratio <= 2.2 + 1e-6, string.format("%s at %dx%d: %.2f texels per pixel", t.rsPath:sub(#ROYALE_ART + 1),
                res[1], res[2], ratio))
        end
    end
    -- the atlases follow the displayed size
    M.SetScreen(1920, 1080, 1)
    local n = RS.Numeral(root, { cap = 112, value = 15 })
    H.eq(n.atlas, "NumeralsL", "157 px")
    n:SetCap(34)
    H.eq(n.atlas, "NumeralsS", "48 px")
    n:SetCap(60)
    H.eq(n.atlas, "NumeralsM", "84 px")
    local ic = RS.Icon(root, "storm", 28)
    H.eq(ic.rsPath, ns.RoyaleArt.icons.small, "28 units are 39 px at 1080p")
    M.SetScreen(2560, 1440, 1)
    H.eq(ic.rsPath, ns.RoyaleArt.icons.file, "and 52 px at 1440p")
    H.eq(n.atlas, "NumeralsM", "113 px")
end)

test("royale style: SetRotation only on the rotatable art, in square regions, also through a whole demo match",
    function(M, ns)
    local RS = ns.RoyaleStyle
    local root = newRoot(M, false)
    local notch = RS.Rotatable(root, "Notch", 22)
    notch:SetAngle(0.5)
    H.eq(#M.rotations, 0, "no SetRotation before the art is set")
    root:Show()
    H.ok(#M.rotations >= 1, "turned once the art is set")
    local last = M.rotations[#M.rotations]
    H.eq(last.path, ns.RoyaleArt.rotatable.Notch)
    near(last.angle, 0.5)
    near(last.width, 22 * math.sqrt(2))
    notch:SetAngle(2)
    near(M.rotations[#M.rotations].angle, 2)
    for _, name in ipairs({ "You", "Arrow", "EdgeTick" }) do
        RS.Rotatable(root, name, 20):SetAngle(1)
    end
    H.ok(not pcall(RS.Rotatable, root, "Pin", 20), "Pin is not rotatable art")
    H.ok(not pcall(RS.Tween, root:CreateTexture(nil, "ARTWORK"), "angle", 0, 1, 0.2), "angle tweens on rotatables only")
    RS.Tween(notch, "angle", 0, math.pi, 0.4, "linear")
    M.Advance(0.5)
    near(notch.rsAngle, math.pi)
    -- a whole match in /bh demo, with the island map open
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    ns.UI.Open("royale")
    M.Advance(0.3)
    ns.Royale.page.join:Click()
    M.Advance(3.5)
    M.env.BleakholdRoyaleReady.accept:Click()
    for _ = 1, 95 do
        M.Advance(1)
    end
    M.env.SlashCmdList.BLEAKHOLD("demo off")
    M.Advance(0.5)
    local allowed = {}
    for _, path in pairs(ns.RoyaleArt.rotatable) do allowed[path] = true end
    for name in pairs(RS.ROTATABLE) do
        H.ok(ns.RoyaleArt.rotatable[name], "art data for " .. name)
    end
    H.ok(#M.rotations >= 5, "rotations recorded: " .. #M.rotations)
    for i, r in ipairs(M.rotations) do
        H.ok(allowed[r.path], "SetRotation " .. i .. " on " .. tostring(r.path))
        near(r.width, r.height, 1e-6, "square region for " .. tostring(r.path))
    end
end)

test("royale style: the tween driver sleeps when no tween runs", function(M, ns)
    local RS = ns.RoyaleStyle
    H.ok(not RS.driver:IsShown(), "hidden at load")
    local root = newRoot(M, true)
    local t = root:CreateTexture(nil, "ARTWORK")
    local done = 0
    RS.Tween(t, "alpha", 0, 1, 0.2, "linear", { onDone = function() done = done + 1 end })
    H.ok(RS.driver:IsShown(), "shown while a tween runs")
    H.ok(RS.Busy(t, "alpha"))
    M.Advance(0.1)
    near(t:GetAlpha(), 0.5, 1e-6, "halfway")
    M.Advance(0.2)
    near(t:GetAlpha(), 1)
    H.eq(done, 1, "onDone once")
    H.ok(not RS.driver:IsShown(), "hidden again")
    H.ok(not RS.Busy(t))
    RS.Tween(t, "alpha", 1, 0, 5)
    H.ok(RS.driver:IsShown())
    RS.Stop(t)
    H.ok(not RS.driver:IsShown(), "a stop that leaves nothing running hides it at once")
    near(t:GetAlpha(), 1, 1e-6, "a plain stop leaves the value where it was")
    -- and after a whole demo match
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    for _ = 1, 40 do
        M.Advance(1)
    end
    M.env.SlashCmdList.BLEAKHOLD("demo off")
    M.Advance(3)
    H.ok(not RS.driver:IsShown(), "asleep after the demo")
end)

test("royale style: eases and tween kinds; replacing, stopping and finishing; an offset returns to its rest",
    function(M, ns)
    local RS = ns.RoyaleStyle
    local E = RS.EASE
    near(E.linear(0.25), 0.25)
    near(E.outCubic(0.5), 0.875)
    near(E.inCubic(0.5), 0.125)
    near(E.inOutSine(0.5), 0.5)
    for _, e in pairs(E) do
        near(e(0), 0, 1e-9); near(e(1), 1, 1e-9)
    end
    local peak = 0
    for i = 1, 99 do peak = math.max(peak, E.outBack(i / 100)) end
    H.ok(peak > 1.05 and peak < 1.2, "outBack overshoots a little: " .. peak)

    local root = newRoot(M, true)
    -- offset: deltas on the owner's anchor
    local banner = M.env.CreateFrame("Frame", nil, root)
    banner:SetSize(620, 96)
    banner:SetPoint("TOP", M.env.UIParent, "TOP", 0, -104)
    RS.Tween(banner, "offset", { 0, 14 }, { 0, 0 }, 0.2, "outCubic")
    near(select(5, banner:GetPoint(1)), -90, 1e-6, "the start applies at once")
    M.Advance(0.3)
    near(select(5, banner:GetPoint(1)), -104)
    H.eq(banner:GetNumPoints(), 1)
    RS.Tween(banner, "offset", nil, { 0, 8 }, 0.3, "inCubic")
    M.Advance(0.4)
    near(select(5, banner:GetPoint(1)), -96, 1e-6, "the exit")
    RS.Tween(banner, "offset", { 0, 14 }, { 0, 0 }, 0.2)
    near(select(5, banner:GetPoint(1)), -90, 1e-6, "the next entrance starts from the rest, not where the exit ended")
    M.Advance(0.3)
    banner:ClearAllPoints()
    banner:SetPoint("TOP", M.env.UIParent, "TOP", 0, -200)
    RS.Tween(banner, "offset", { 0, 10 }, { 0, 0 }, 0.2)
    near(select(5, banner:GetPoint(1)), -190, 1e-6, "the owner moved it: the new spot is the rest")
    M.Advance(0.3)
    near(select(5, banner:GetPoint(1)), -200)
    -- a region with two anchors moves as a whole
    local strip = root:CreateTexture(nil, "ARTWORK")
    strip:SetPoint("TOPLEFT", root, "TOPLEFT", 10, -10)
    strip:SetPoint("BOTTOMRIGHT", root, "BOTTOMRIGHT", -10, 10)
    RS.Tween(strip, "offset", { 30, 0 }, { 0, 0 }, 0.2, "linear")
    near(select(4, strip:GetPoint(1)), 40); near(select(4, strip:GetPoint(2)), 20)
    M.Advance(0.1)
    near(select(4, strip:GetPoint(1)), 25); near(select(4, strip:GetPoint(2)), 5)
    M.Advance(0.2)
    near(select(4, strip:GetPoint(1)), 10); near(select(4, strip:GetPoint(2)), -10)
    -- size, texcoord, vertexColor (a token, and on a font string), number, zoom
    local ring = root:CreateTexture(nil, "ARTWORK")
    ring:SetSize(280, 280)
    RS.Tween(ring, "size", { 280 * 0.92, 280 * 0.92 }, { 280, 280 }, 0.3, "linear")
    M.Advance(0.15)
    near(ring:GetWidth(), 280 * 0.96, 1e-6, "size halfway")
    RS.Tween(ring, "texcoord", { 0.75, 1, 0, 1 }, { 0, 0.25, 0, 1 }, 0.2, "linear")
    M.Advance(0.1)
    local l, t, _, b, r = ring:GetTexCoord()
    near(l, 0.375); near(r, 0.625); near(t, 0); near(b, 1)
    RS.Tween(ring, "vertexColor", "safe", "ember", 0.2, "linear")
    M.Advance(0.1)
    local cr, cg, cb = ring:GetVertexColor()
    near(cr, 1); near(cg, (1 + 0x7A / 255) / 2); near(cb, (1 + 0x3D / 255) / 2)
    local fs = RS.Text(root, "value", 20)
    RS.Tween(fs, "vertexColor", "parchment", "gold", 0.2)
    M.Advance(0.3)
    near(select(1, fs:GetTextColor()), 0xE5 / 255, 1e-6, "font strings tween their text colour")
    local counted = {}
    local key = {}
    RS.Tween(key, "number", 0, 1200, 0.6, "linear", { set = function(v) counted[#counted + 1] = v end })
    M.Advance(0.7)
    near(counted[1], 0, 1e-6, "the start value at once")
    near(counted[#counted], 1200, 1e-6, "ends on the value")
    H.ok(not pcall(RS.Tween, key, "number", 0, 1, 0.2), "a number tween needs opts.set")
    local n = RS.Numeral(root, { cap = 150, value = 9 })
    local h0 = n.cur:GetHeight()
    RS.Tween(n, "zoom", 1.12, 1, 0.22, "outBack")
    near(n.cur:GetHeight(), h0 * 1.12, 1e-6, "zoomed")
    M.Advance(0.3)
    near(n.cur:GetHeight(), h0, 1e-6, "back to its cap")
    -- a second tween of the same kind replaces the first, whose onDone is dropped
    local first, second = 0, 0
    RS.Tween(ring, "alpha", 0, 1, 1, "linear", { onDone = function() first = first + 1 end })
    M.Advance(0.5)
    RS.Tween(ring, "alpha", nil, 0, 0.2, "linear", { onDone = function() second = second + 1 end })
    near(ring:GetAlpha(), 0.5, 1e-6, "continues from where the first one was")
    M.Advance(0.3)
    H.eq(first, 0); H.eq(second, 1); near(ring:GetAlpha(), 0)
    -- a delay holds the start value until it passes
    RS.Tween(ring, "alpha", 0.2, 1, 0.2, "linear", { delay = 0.3 })
    M.Advance(0.2)
    near(ring:GetAlpha(), 0.2, 1e-6, "held during the delay")
    M.Advance(0.4)
    near(ring:GetAlpha(), 1)
    -- RS.Stop with finish jumps to the end and runs onDone
    local finished = 0
    RS.Tween(ring, "alpha", 1, 0.3, 2, "linear", { onDone = function() finished = finished + 1 end })
    RS.Stop(ring, "alpha", true)
    near(ring:GetAlpha(), 0.3); H.eq(finished, 1)
    H.ok(not pcall(RS.Tween, ring, "spin", 0, 1, 1), "unknown kinds raise")
end)

test("royale style: reduced motion jumps every tween to its end and keeps the loops off", function(M, ns)
    local RS = ns.RoyaleStyle
    local root = newRoot(M, true)
    local t = root:CreateTexture(nil, "ARTWORK")
    RS.Tween(t, "alpha", 0, 1, 2, "linear")
    M.Advance(0.5)
    local g = RS.Loop(t, "pulse", { from = 0.5, to = 1 })
    H.ok(g:IsPlaying(), "the loop plays with motion on")
    RS.SetMotion(false)
    H.eq(ns.db.options.royaleMotion, false)
    near(t:GetAlpha(), 1, 1e-6, "the running tween jumped to its end")
    H.ok(not g:IsPlaying(), "loops stop")
    H.ok(not RS.driver:IsShown())
    local done = 0
    RS.Tween(t, "alpha", 1, 0.25, 1, "linear", { delay = 1, onDone = function() done = done + 1 end })
    near(t:GetAlpha(), 0.25, 1e-6, "at its end at once")
    H.eq(done, 1, "onDone at once")
    H.ok(not RS.driver:IsShown(), "the driver stays asleep")
    H.ok(not RS.Loop(t, "sway"):IsPlaying(), "no loop starts")
    RS.SetMotion(true)
    H.ok(RS.Loop(t, "sway"):IsPlaying())
end)

test("royale style: loops are AnimationGroups: pulse, shimmer, sway and spin", function(M, ns)
    local RS = ns.RoyaleStyle
    local root = newRoot(M, true)
    local gem, lines, canopy, dashes = root:CreateTexture(), root:CreateTexture(), root:CreateTexture(),
        root:CreateTexture()
    local p = RS.Loop(gem, "pulse")
    H.eq(p.__looping, "BOUNCE")
    near(gem:GetAlpha(), 0.5, 1e-6, "pulse starts at its low alpha")
    near(p.__anims[1].__change, 0.5)
    local s = RS.Loop(lines, "shimmer", { from = 0.28, to = 0.16 })
    near(lines:GetAlpha(), 0.28)
    near(s.__anims[1].__change, -0.12)
    near(s.__anims[1].__duration, 0.45)
    local w = RS.Loop(canopy, "sway", { origin = { "TOP", 0, 0 } })
    H.eq(w.__looping, "REPEAT")
    H.eq(#w.__anims, 3, "out, across, back")
    local total = 0
    for _, a in ipairs(w.__anims) do total = total + a.__duration end
    near(total, 1.6)
    local sp = RS.Loop(dashes, "spin")
    near(sp.__anims[1].__duration, 60)
    H.ok(RS.Loop(gem, "pulse") == p, "one group per region and kind")
    RS.Stop(gem, "loop")
    H.ok(not p:IsPlaying())
    RS.StopLoop(canopy, "sway")
    H.ok(not w:IsPlaying())
    H.ok(not pcall(RS.Loop, gem, "wobble"), "unknown loops raise")
    H.ok(not pcall(RS.Loop, RS.Text(root, "body", 12), "sway"), "font strings ignore rotation")
end)

test("royale style: no Royale texture is set before its root frame shows", function(M, ns)
    local RS = ns.RoyaleStyle
    local root = newRoot(M, false)
    root:SetScript("OnShow", function() end)   -- the owner's own OnShow, set before the kit's textures
    local inner = M.env.CreateFrame("Frame", nil, M.env.CreateFrame("Frame", nil, root))
    local plate = RS.Plate(inner, "Plate")
    local icon = RS.Icon(inner, "crown", 28)
    local n = RS.Numeral(inner, { cap = 112, value = 15 })
    local title = RS.Title(inner, "VICTORY", 32, "gold")
    H.eq(RS.RootOf(icon), root, "the root is the highest frame below UIParent")
    local all = { plate.pieces.tl, plate.pieces.c, icon, n.cur.texs[1], n.glow.texs[1], title.tex, title.glow }
    for _, t in ipairs(all) do
        H.eq(t:GetTexture(), nil, "nothing set while hidden: " .. tostring(t.rsPath))
        H.ok(t.rsPath, "the path waits")
    end
    for _, t in ipairs(all) do
        H.ok(not M.textures[t.rsPath], "the file not loaded yet: " .. t.rsPath)
    end
    icon:SetIconSize(44)   -- the atlas changes while hidden: the last path wins
    root:Show()
    for _, t in ipairs(all) do
        H.eq(t:GetTexture(), t.rsPath, "set on show: " .. tostring(t.rsPath))
    end
    H.eq(icon:GetTexture(), ns.RoyaleArt.icons.file)
    -- once shown, later textures are set at once (also while it is hidden again)
    root:Hide()
    local late = RS.Art(inner, "ShockSmall", 72)
    H.eq(late:GetTexture(), ns.RoyaleArt.files.ShockSmall)
    -- a visible root sets them at once
    local shown = newRoot(M, true)
    H.eq(RS.Art(shown, "Gem", 12):GetTexture(), ns.RoyaleArt.files.Gem)
end)

test("royale style: a region greyed before its lazy file arrives (or its atlas changes) stays grey", function(M, ns)
    -- the client's SetTexture puts the Normal shader back on every new file (CSimpleRender.cpp), and the mock does so
    local RS = ns.RoyaleStyle
    local plain = M.env.CreateFrame("Frame", nil, M.env.UIParent):CreateTexture(nil, "ARTWORK")
    plain:SetDesaturated(true)
    plain:SetTexture(ns.RoyaleArt.files.Gem)
    H.eq(plain:IsDesaturated(), nil, "the mock resets it like the client")
    local root = newRoot(M, false)
    local icon = RS.Icon(root, "storm", 16)
    local button = RS.Button(root, 140, 28, "Queue again", "gold")
    local plate = RS.Plate(root, "Plate")
    RS.Desaturate(icon, true)
    button:SetActive(false)
    plate:SetDesaturated(true)
    root:Show()
    H.eq(icon:GetTexture(), ns.RoyaleArt.icons.small, "the file came on show")
    H.eq(icon:IsDesaturated(), 1, "the icon is still grey")
    for k, t in pairs(button.faces.Button.pieces) do
        H.eq(t:IsDesaturated(), 1, "the disabled button's face is grey: " .. k)
    end
    for k, t in pairs(plate.pieces) do
        H.eq(t:IsDesaturated(), 1, "the plate is grey: " .. k)
    end
    icon:SetIconSize(44)
    H.eq(icon:GetTexture(), ns.RoyaleArt.icons.file, "the large atlas")
    H.eq(icon:IsDesaturated(), 1, "still grey after the atlas swap")
    RS.Desaturate(icon, false)
    icon:SetIconSize(16)
    H.eq(icon:IsDesaturated(), nil, "colour back, and it stays back")
    button:SetActive(true)
    H.eq(button.faces.Button.pieces.c:IsDesaturated(), nil)
end)

test("royale style: Royale code greys a region through RS.Desaturate only (it survives the lazy file)", function(M, ns)
    for _, name in ipairs({ "Royale.lua", "RoyaleCountdown.lua", "RoyaleDrop.lua", "RoyaleHud.lua", "RoyaleMap.lua",
        "RoyaleMinimap.lua", "RoyaleStyle.lua" }) do
        local text = assert(host_readfile(addonDir .. "/" .. name), name)
        local n = 0
        for line in (text .. "\n"):gmatch("(.-)\n") do
            local code = line:gsub("%-%-.*$", "")
            if code:find(":SetDesaturated%(") and not code:find("^%s*function ") then
                n = n + 1
                H.ok(name == "RoyaleStyle.lua" and (code:find("tex:SetDesaturated", 1, true)
                    or code:find("face:SetDesaturated", 1, true)), name .. " calls SetDesaturated: " .. line)
            end
        end
        if name == "RoyaleStyle.lua" then
            H.eq(n, 3, "RS.Desaturate, applyTexture and the button's plate face")
        end
    end
end)

test("royale style: numerals sit on one baseline, centre on their anchor and cross-fade from the old layer",
    function(M, ns)
    local RS = ns.RoyaleStyle
    local A = ns.RoyaleArt.atlases
    local root = newRoot(M, true)
    M.SetScreen(1920, 1080, 1)
    local n = RS.Numeral(root, { cap = 112, value = 15 })
    n:SetPoint("CENTER", root, "CENTER", 0, 0)
    H.eq(n.atlas, "NumeralsL")
    local at = A.NumeralsL
    local c, k = 112, 112 / at.cap
    local g1, g5 = at.glyphs["1"], at.glyphs["5"]
    local stroke = at.stroke * k
    local width = g1.advance * c + g5.inkR * c - g1.inkL * c + 2 * stroke
    near(n:GetWidth(), width, 1e-6, "ink plus stroke")
    near(n:GetHeight(), c + 2 * stroke)
    H.eq(select(1, n.cur:GetPoint(1)), "CENTER", "the digits hang from the centre")
    local t1, t2 = n.cur.texs[1], n.cur.texs[2]
    H.ok(t1:IsShown() and t2:IsShown())
    local _, _, rp1, x1, y1 = t1:GetPoint(1)
    local _, _, _, x2, y2 = t2:GetPoint(1)
    H.eq(rp1, "BOTTOMLEFT")
    near(y1, y2, 1e-9, "one shared baseline")
    near(y1, at.baseline * k + stroke, 1e-6, "the quad's top above the baseline")
    near(x1 + g1.ox * c + g1.inkL * c, stroke, 1e-6, "the ink starts one stroke in")
    near(x2 - x1, g1.advance * c + (g1.ox - g5.ox) * c, 1e-6, "the pen moves by the advance")
    near(t1:GetWidth(), at.cellW * k); near(t1:GetHeight(), at.cellH * k)
    local u0, v0, _, v1, u1 = t1:GetTexCoord()
    near(u0, g1.u0); near(u1, g1.u1); near(v0, g1.v0); near(v1, g1.v1)
    -- the glow: the same layout in the glow atlas, ADD, alpha 0 until tweened
    H.eq(n.glow.texs[1].rsPath, at.glow)
    near(n.glow:GetAlpha(), 0)
    n:SetGlowColor("ember")
    near(select(2, n.glow.texs[1]:GetVertexColor()), 0x7A / 255)
    -- swap: the old layer keeps "15" at its cap while 9 comes in at 150
    n:Swap(9)
    n:SetCap(150)
    H.ok(n.old:IsShown())
    H.eq(n.old.text, "15"); H.eq(n.old.cap, 112)
    H.eq(n.cur.text, "9"); H.eq(n.value, "9")
    near(n:GetHeight(), 150 + 2 * at.stroke * 150 / at.cap)
    near(n.old:GetHeight(), 112 + 2 * stroke, 1e-6, "the old digits keep their size")
    RS.Tween(n.old, "alpha", 1, 0, 0.15, "inCubic")
    RS.Tween(n.old, "zoom", 1, 0.85, 0.15, "inCubic")
    RS.Tween(n.cur, "offset", { 0, 60 }, { 0, 0 }, 0.22, "outCubic")
    near(select(5, n.cur:GetPoint(1)), 60)
    M.Advance(0.3)
    near(n.old:GetAlpha(), 0)
    near(n.old:GetHeight(), (112 + 2 * stroke) * 0.85)
    near(select(5, n.cur:GetPoint(1)), 0)
    n:ClearOld()
    H.ok(not n.old:IsShown())
    -- '#' and '/' exist in NumeralsS only; a right-aligned numeral hangs from its right edge
    local rank = RS.Numeral(root, { cap = 22, value = "#7", justify = "RIGHT" })
    H.eq(rank.atlas, "NumeralsS")
    H.eq(select(1, rank.cur:GetPoint(1)), "RIGHT")
    H.eq(rank.cur.texs[1]:GetTexCoord(), A.NumeralsS.glyphs["#"].u0)
    local big = RS.Numeral(root, { cap = 200, value = "1/2" })
    H.eq(big.atlas, "NumeralsS", "a / falls back to the atlas that has it")
    -- an empty value is an empty frame
    local none = RS.Numeral(root, { cap = 34 })
    H.ok(none:GetWidth() < 0.1)
end)

test("royale style: titles refuse a cap under 21 units; titles and DROP! size from the art data", function(M, ns)
    local RS = ns.RoyaleStyle
    local A = ns.RoyaleArt
    local root = newRoot(M, true)
    local ok, err = pcall(RS.Title, root, "VICTORY", 20, "gold")
    H.ok(not ok, "a 20-unit title is refused")
    H.contains(err, "under 21")
    local t = RS.Title(root, "VICTORY", 32, "gold")
    local d, at = A.titles.VICTORY, A.atlases.Titles
    local s = at.stroke / at.cap
    near(t.tex:GetWidth(), d.w * 32); near(t.tex:GetHeight(), d.h * 32)
    near(t:GetWidth(), (d.inkW + 2 * s) * 32); near(t:GetHeight(), (1 + 2 * s) * 32)
    H.eq(select(1, t.tex:GetPoint(1)), "CENTER", "the cap's middle on the frame's middle")
    near(select(2, t.tex:GetVertexColor()), 0xC0 / 255, 1e-6, "tinted gold")
    near(t.glow:GetAlpha(), 0)
    H.eq(t.glow.rsPath, at.glow)
    t:SetTitle("WINNER")
    near(t.tex:GetTexCoord(), A.titles.WINNER.u0)
    t:SetColor("parchment")
    near(select(3, t.tex:GetVertexColor()), 0xD0 / 255)
    H.ok(not pcall(t.SetCap, t, 18), "SetCap refuses it too")
    t:SetZoom(1.15)
    near(t.tex:GetHeight(), d.h * 32 * 0 + A.titles.WINNER.h * 32 * 1.15, 1e-6, "zoom scales the art, not the frame")
    near(t:GetWidth(), (A.titles.WINNER.inkW + 2 * s) * 32)
    H.ok(not pcall(RS.Title, root, "NOT A TITLE", 30), "unknown titles raise")
    -- DROP!: the ink centred on the frame's centre, the cap band around it
    local w = RS.DropWord(root, 96)
    local dw = A.atlases.DropWord
    local g = dw.glyphs["DROP!"]
    near(w.tex:GetWidth(), dw.cellW / dw.cap * 96); near(w.tex:GetHeight(), dw.cellH / dw.cap * 96)
    local _, _, rp, x, y = w.tex:GetPoint(1)
    H.eq(rp, "CENTER")
    near(x + (g.ox + g.inkL) * 96, -(g.inkR - g.inkL) / 2 * 96, 1e-6, "the ink centred")
    near(y - dw.baseline / dw.cap * 96, -48, 1e-6, "the baseline half a cap under the centre")
    H.eq(w.glow.rsPath, dw.glow)
end)

test("royale style: plates are nine pieces of the art's margins, corners at 16 units (8 for tabs), whole pixels",
    function(M, ns)
    local RS = ns.RoyaleStyle
    local A = ns.RoyaleArt
    local root = newRoot(M, true)
    M.SetScreen(1920, 1080, 1)
    local f = M.env.CreateFrame("Frame", nil, root)
    f:SetSize(384, 72)
    local p = RS.Plate(f, "Plate")
    local n = 0
    for _ in pairs(p.pieces) do n = n + 1 end
    H.eq(n, 9)
    local m = A.slices.Plate.margin / A.slices.Plate.w
    local l, t, _, b, r = p.pieces.tl:GetTexCoord()
    near(l, 0); near(r, m); near(t, 0); near(b, m)
    l, t, _, b, r = p.pieces.c:GetTexCoord()
    near(l, m); near(r, 1 - m)
    near(p.pieces.tl:GetWidth(), 23 / 1.40625, 1e-6, "16 units (22.5 px) snapped to 23 px")
    H.eq(p.pieces.c:GetTexture(), A.files.Plate)
    near(p.fillInset, (8 + 6 + 7) * 16 / 32)
    p:SetColor("stormDeep")
    near(select(3, p.pieces.br:GetVertexColor()), 0x6E / 255, 1e-6, "tinted")
    local tab = RS.Plate(f, "PlateTab")
    near(tab.pieces.tl:GetWidth(), 11 / 1.40625, 1e-6, "8 units snapped to 11 px")
    M.SetScreen(2560, 1440, 1)
    near(p.pieces.tl:GetWidth(), 16, 1e-6, "30 px at 1440p")
    H.ok(not pcall(RS.Plate, f, "Nope"), "unknown plates raise")
    -- the shine: over the fill, showing a clear part of the strip, swept left to right
    local shine = RS.Shine(p)
    H.eq(shine.rsPath, A.files.ShineStrip)
    near(select(4, shine:GetPoint(1)), p.fillInset)
    near(shine:GetTexCoord(), -0.1, 1e-6, "clear before the first sweep")
    near(shine:GetAlpha(), 0.6)
    RS.Sweep(shine)
    near(shine:GetTexCoord(), 0.6, 1e-6, "the sweep starts right of the streak")
    M.Advance(0.05)
    near(shine:GetTexCoord(), 0.6, 1e-6, "waits 0.1 s")
    M.Advance(0.8)
    near(shine:GetTexCoord(), -0.1, 1e-6, "ends left of it")
    -- the streak (the strip's middle 192 of 1024 texels) is outside the window at both ends
    for _, w in ipairs({ RS.SHINE_FROM, RS.SHINE_TO }) do
        H.ok(w[2] <= 0.40625 or w[1] >= 0.59375, "a clear window: " .. w[1] .. "-" .. w[2])
    end
    -- a hairline is one physical pixel
    local line = RS.Hairline(f, 36, "bronzeLo", true)
    near(line:GetWidth() * RS.PxPerUnit(line), 1)
    near(line:GetHeight(), 36)
    M.SetScreen(1920, 1080, 0.64)
    near(line:GetWidth() * RS.PxPerUnit(line), 1, 1e-6, "also after a change of scale")
end)

test("royale style: buttons have gold, iron and ghost faces, hover and press glows, and UI.Button's API",
    function(M, ns)
    local RS = ns.RoyaleStyle
    local root = newRoot(M, true)
    local clicks = 0
    local b = RS.Button(root, 140, 28, "Queue again", "gold")
    b:SetScript("OnClick", function() clicks = clicks + 1 end)
    H.ok(b.faces.Button, "the gold face is the Button art")
    H.eq(b.faces.Button.pieces.c:GetTexture(), ns.RoyaleArt.files.Button)
    H.eq(b.label:GetText(), "Queue again")
    near(select(1, b.label:GetTextColor()), 0x1A / 255, 1e-6, "dark text on gold")
    local function glow() return b.glow.pieces.c:GetAlpha() end
    near(glow(), 0)
    M.Fire(b, "OnEnter")
    near(glow(), 0.35, 1e-6, "hover")
    M.Fire(b, "OnMouseDown", "LeftButton")
    near(glow(), 0.6, 1e-6, "press")
    near(select(5, b.label:GetPoint(1)), -1, 1e-6, "the label goes down one unit")
    M.Fire(b, "OnMouseUp", "LeftButton")
    near(glow(), 0.35)
    near(select(5, b.label:GetPoint(1)), 0)
    b:Click()
    H.eq(clicks, 1)
    M.Fire(b, "OnLeave")
    near(glow(), 0)
    b:SetStyle("iron")
    H.ok(b.faces.PlateTab, "the iron face is the plate tab")
    H.ok(not b.faces.Button.pieces.c:IsShown(), "the gold face hides")
    near(select(1, b.label:GetTextColor()), 0xF2 / 255, 1e-6, "parchment on iron")
    b:SetStyle("ghost")
    H.ok(b.faces.LabelHalo and b.faces.LabelHalo.pieces.c:IsShown(), "the ghost's soft pill")
    b:SetActive(false)
    H.ok(not b:IsEnabled())
    M.Fire(b, "OnEnter")
    near(glow(), 0, 1e-6, "no glow while disabled")
    near(select(1, b.label:GetTextColor()), 0x8A / 255, 1e-6, "smoke")
    b:Click()
    H.eq(clicks, 1, "a disabled button does not click")
    b:SetActive(true)
    b:SetLabel("Leave")
    H.eq(b.label:GetText(), "Leave")
    b.tooltip = function() return { "Leave the match" } end
    M.Fire(b, "OnEnter")
    H.eq(M.env.GameTooltip.__lines[1], "Leave the match")
    M.Fire(b, "OnLeave")
    -- an icon-only close button
    local close = RS.Button(root, 22, 22, nil, "iron")
    close:SetIcon("close", 14)
    H.eq(select(1, close.icon:GetPoint(1)), "CENTER")
    near(close.icon:GetWidth(), 14)
    H.ok(RS.Button(root, 80, 24, "x", "bogus").style == "iron", "unknown styles are iron")
end)

test("royale style: icons pick the atlas drawn for their displayed size", function(M, ns)
    local RS = ns.RoyaleStyle
    local I = ns.RoyaleArt.icons
    local root = newRoot(M, true)
    M.SetScreen(1920, 1080, 1)
    local small = RS.Icon(root, "storm", 16)
    H.eq(small:GetTexture(), I.small)
    local u0, v0, _, v1, u1 = small:GetTexCoord()
    local cell = I.cells.storm
    near(u0, cell.u0); near(u1, cell.u1); near(v0, cell.v0); near(v1, cell.v1)
    local large = RS.Icon(root, "crown", 30)
    H.eq(large:GetTexture(), I.file, "30 units are 42 px")
    large:SetIcon("beast")
    near(large:GetTexCoord(), I.cells.beast.u0)
    large:SetIconSize(20)
    H.eq(large:GetTexture(), I.small)
    near(large:GetWidth(), 20)
    local unknown = RS.Icon(root, "no-such-icon", 16)
    near(unknown:GetTexCoord(), I.cells.warning.u0, 1e-6, "unknown names show the warning icon")
end)

test("royale style: the clock is M:SS everywhere", function(M, ns)
    local RS = ns.RoyaleStyle
    H.eq(RS.Clock(5), "0:05")
    H.eq(RS.Clock(100), "1:40")
    H.eq(RS.Clock(723), "12:03")
    H.eq(RS.Clock(4.2), "0:05", "a countdown rounds up")
    H.eq(RS.Clock(4.2, true), "0:04", "a time that passed rounds down")
    H.eq(RS.Clock(99.9999999), "1:40")
    H.eq(RS.Clock(0), "0:00")
    H.eq(RS.Clock(-3), "0:00")
    H.eq(RS.Clock(nil), "0:00")
    H.eq(RS.Clock(0 / 0), "0:00")
    H.eq(RS.Clock(3600), "60:00")
end)

test("royale style: our sounds honour Quiet and the Royale sounds switch, and every file and face exists",
    function(M, ns)
    local RS = ns.RoyaleStyle
    for _, name in ipairs(RS.SOUNDS) do
        for _, suffix in ipairs({ "", "_quiet" }) do
            H.ok(host_readfile(addonDir .. "/Sounds/Royale/" .. name .. suffix .. ".wav"), name .. suffix .. ".wav")
        end
    end
    H.ok(host_readfile(addonDir .. "/" .. RS.FONT_SC:match("^Interface\\AddOns\\Bleakhold\\(.+)$"):gsub("\\", "/")),
        "Marcellus SC in the addon")
    for name, path in pairs(ns.RoyaleArt.files) do
        local rel = path:match("^Interface\\AddOns\\Bleakhold\\(.+)$"):gsub("\\", "/")
        H.ok(host_readfile(addonDir .. "/" .. rel .. ".tga") or host_readfile(addonDir .. "/" .. rel .. ".blp"),
            "art file " .. name)
    end
    H.ok(RS.PlayFile("tick"))
    H.eq(M.soundFiles[#M.soundFiles], RS.SOUND_DIR .. "tick.wav")
    ns.Announcer.SetQuiet(true)
    RS.PlayFile("tick3")
    H.eq(M.soundFiles[#M.soundFiles], RS.SOUND_DIR .. "tick3_quiet.wav")
    ns.Announcer.SetQuiet(false)
    H.ok(RS.Play("MapPing"))
    H.eq(M.sounds[#M.sounds], "MapPing")
    RS.SetSounds(false)
    local files, kits = #M.soundFiles, #M.sounds
    H.ok(not RS.PlayFile("kill")); H.ok(not RS.Play("igPVPUpdate"))
    H.eq(#M.soundFiles, files); H.eq(#M.sounds, kits)
    RS.SetSounds(true)
    H.ok(RS.PlayFile("kill"))
end)

test("royale style: the HUD scale is 0.8-1.4 on every registered root, and the kit lays itself out again",
    function(M, ns)
    local RS = ns.RoyaleStyle
    H.eq(RS.HudScale(), 1.2, "the saved value")
    local root = newRoot(M, true)
    RS.RegisterRoot(root)
    near(root:GetScale(), 1.2)
    RS.RegisterRoot(root)
    M.SetScreen(2560, 1440, 1)
    local value = RS.Text(root, "value", 20)
    near(select(2, value:GetFont()), 32 / (1.875 * 1.2))
    local fired
    ns.On("ROYALE_HUD_SCALE", function(v) fired = v end)
    H.eq(RS.SetHudScale(1.25), 1.25)
    H.eq(fired, 1.25)
    near(root:GetScale(), 1.25)
    H.eq(ns.db.options.royaleHudScale, 1.25)
    near(select(2, value:GetFont()), 32 / (1.875 * 1.25), 1e-6, "re-clamped for the new scale")
    H.eq(RS.SetHudScale(3), 1.4)
    H.eq(RS.SetHudScale(0.2), 0.8)
    H.eq(RS.SetHudScale(1.234), 1.23)
    H.eq(RS.SetHudScale("big"), nil)
    near(root:GetScale(), 1.23)
end, { before = function(M)
    M.env.BleakholdDB = { options = { royaleHudScale = 1.2 } }
end })
