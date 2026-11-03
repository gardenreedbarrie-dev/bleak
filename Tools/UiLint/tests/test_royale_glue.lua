-- Bleakhold Royale's glue code (Royale.lua, WS-C7 of the Royale UX design): the ready check on its plate (MATCH FOUND,
-- the gems that drain with the answer time, the seconds in the metal numerals, the count, the answer), the Royale
-- options and their commands (/bh royale motion|sounds|farclip|minimap|scale), /bh royale preview (the countdown and
-- the map through a sample match that never reaches the realm, the drop, the banners and the end card through their
-- modules), the routing of Royale toasts during a match, the drop of /bh demo with ROYS fields 25-27, and Royale.lua's
-- own wording and constant count.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local ROYALE_ART = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\"
local MAP = {
    { 901, -1066, 533, -1066, 533, 455, 455, 32, 750, -267, -267 }, { 1, "L", -266, -266, 88, "The Bleak Hold" },
}

local function near(a, b, eps, msg)
    if type(a) ~= "number" or math.abs(a - b) > (eps or 1e-6) then
        error((msg or "values differ") .. ": expected " .. tostring(b) .. ", got " .. tostring(a), 2)
    end
end

local function connect(M)
    FX.connect(M, H, { [6] = 4096 })
end

-- A ready check: QUEUE kind B state 2, proposal 412, `timeout` s to answer, `accepted` of 24.
local function proposal(M, timeout, accepted, rev)
    H.send(M, "QUEUE", { { rev or 5, 2, "B", 901, 0, 1, 95, "", 412, timeout or 15, 80, 80, 24, 20, 40, accepted or 0,
        24, 1 } })
end

-- A ROYS of match 7001 (field index -> value): the lobby before the countdown unless `over` says otherwise.
local function roys(M, over)
    local r = { 7001, 0, 60000, 24, 24, 0, 0, "", "", "", 0, -267, -267, 860, "", "", "", "", "", 0, "", 450, 452, 6,
        "", "", "" }
    for k, v in pairs(over or {}) do r[k] = v end
    H.send(M, "ROYS", { r })
end

local function chatSince(M, from)
    local out = {}
    for i = from + 1, #M.chat do
        out[#out + 1] = M.chat[i].msg
    end
    return table.concat(out, "\n")
end

local function slash(M, line)
    M.env.SlashCmdList.BLEAKHOLD(line)
end

local function lit(rc)
    local n = 0
    for _, g in ipairs(rc.gems) do
        if g.on then n = n + 1 end
    end
    return n
end

local FP = { TOPLEFT = { 0, 0 }, TOP = { 0.5, 0 }, TOPRIGHT = { 1, 0 }, LEFT = { 0, 0.5 }, CENTER = { 0.5, 0.5 },
    RIGHT = { 1, 0.5 }, BOTTOMLEFT = { 0, 1 }, BOTTOM = { 0.5, 1 }, BOTTOMRIGHT = { 1, 1 } }

-- A region's rect in its root's units (left, top, right, bottom; y grows downwards), from its anchors and sizes.
local function resolver(root)
    local cache = {}
    local function res(o)
        if o == root then
            return { 0, 0, root:GetWidth(), root:GetHeight() }
        end
        if cache[o] then return cache[o] end
        local L, R, CX, T, B, CY
        for i = 1, o:GetNumPoints() do
            local p, rel, rp, x, y = o:GetPoint(i)
            local rr = res(rel or o:GetParent())
            local tx = rr[1] + (rr[3] - rr[1]) * FP[rp][1] + (x or 0)
            local ty = rr[2] + (rr[4] - rr[2]) * FP[rp][2] - (y or 0)
            local ax, ay = FP[p][1], FP[p][2]
            if ax == 0 then L = tx elseif ax == 1 then R = tx else CX = tx end
            if ay == 0 then T = ty elseif ay == 1 then B = ty else CY = ty end
        end
        local w, h = o:GetWidth() or 0, o:GetHeight() or 0
        if o:IsObjectType("FontString") then
            if w <= 0 then w = o:GetStringWidth() end
            if h <= 0 then h = select(2, o:GetFont()) end
        end
        if not (L and R) then
            if L then R = L + w elseif R then L = R - w elseif CX then L, R = CX - w / 2, CX + w / 2 end
        end
        if not (T and B) then
            if T then B = T + h elseif B then T = B - h elseif CY then T, B = CY - h / 2, CY + h / 2 end
        end
        cache[o] = { L, T, R, B }
        return cache[o]
    end
    return res
end

local function inside(res, o, box, what)
    local r = res(o)
    local ok = r[1] >= box[1] - 0.01 and r[2] >= box[2] - 0.01 and r[3] <= box[3] + 0.01 and r[4] <= box[4] + 0.01
    H.ok(ok, string.format("%s: %.1f,%.1f .. %.1f,%.1f leaves %.1f,%.1f .. %.1f,%.1f", what, r[1], r[2], r[3], r[4],
        box[1], box[2], box[3], box[4]))
    return r
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

------------------------------------------------------------------------------------------------------
-- The ready check
------------------------------------------------------------------------------------------------------
test("royale glue: the ready check is MATCH FOUND on a plate; its gems and seconds drain with the answer time",
function(M, ns)
    connect(M)
    local R, RS = ns.Royale, ns.RoyaleStyle
    local rc = M.env.BleakholdRoyaleReady
    proposal(M, 15, 3)
    H.ok(rc:IsShown(), "shown")
    H.eq(rc:GetWidth(), 360)
    H.eq(rc:GetFrameStrata(), "DIALOG")
    H.eq(rc.title.title, "MATCH FOUND")
    H.ok(rc.title.cap >= RS.TITLE_MIN_CAP, "a baked title at cap 21 or more")
    H.eq(rc.body:GetText(), "Bleakhold Royale · 24 players")
    H.eq(rc.count:GetText(), "3 of 24 accepted")
    H.eq(#rc.gems, 15, "a gem in each of the ring's 15 sockets")
    H.eq(rc.num:GetValue(), "15")
    H.eq(lit(rc), 15)
    M.Advance(1)
    H.eq(rc.gems[15]:GetAlpha(), 1, "the gems light one after another as it enters")
    -- one gem a second, from the last socket back to the first (the first n stay set, from the top clockwise)
    M.Advance(5.2)
    H.eq(rc.num:GetValue(), "9")
    H.eq(lit(rc), 9)
    H.ok(rc.gems[9].on and not rc.gems[10].on, "the first nine set")
    M.Advance(0.5)
    near(rc.gems[10]:GetAlpha(), 0, 1e-6, "a spent gem fades out")
    local r, g, b = rc.gems[1]:GetVertexColor()
    near(r, 1, 0.01, "white like a cut stone")
    -- the last three seconds burn ember
    M.Advance(6.1)
    H.eq(rc.num:GetValue(), "3")
    r, g, b = rc.gems[1]:GetVertexColor()
    local er, eg, eb = RS.Rgb("ember")
    near(r, er, 0.01); near(g, eg, 0.01); near(b, eb, 0.01)
    H.eq(rc.num.glowColor, "ember")
    -- the answer
    H.ok(rc.accept:IsShown() and rc.decline:IsShown() and not rc.waiting:IsShown())
    R.answered = { id = 412, accept = true }
    proposal(M, 15, 9, 6)
    H.ok(not rc.accept:IsShown() and not rc.decline:IsShown(), "the buttons go once accepted")
    H.eq(rc.waiting:GetText(), "Accepted. Waiting for the others.")
    H.ok(rc.waiting:IsShown())
    H.eq(rc.count:GetText(), "9 of 24 accepted")
end)

test("royale glue: an unknown answer time keeps every gem set and no seconds", function(M, ns)
    connect(M)
    local rc = M.env.BleakholdRoyaleReady
    H.send(M, "QUEUE", { { 5, 2, "B", 901, 0, 1, 95, "", 412, "", 80, 80, "", 20, 40, "", "", 1 } })
    H.ok(rc:IsShown())
    H.eq(lit(rc), 15)
    H.eq(rc.num:GetValue(), "")
    H.eq(rc.body:GetText(), "Bleakhold Royale")
    H.eq(rc.count:GetText() or "", "")
end)

for _, screen in ipairs({ { 1920, 1080 }, { 2560, 1440 }, { 3840, 2160 } }) do
    test(("royale glue: the ready check's content stays inside its rim at %dx%d, art at most 2.2x minified")
        :format(screen[1], screen[2]), function(M, ns)
        M.SetScreen(screen[1], screen[2], 1)
        connect(M)
        local RS = ns.RoyaleStyle
        local rc = M.env.BleakholdRoyaleReady
        proposal(M, 15, 23)
        M.Advance(1)
        local sl = ns.RoyaleArt.slices.Plate
        local k = (sl.edge + sl.rim) * rc.art.corner / sl.margin
        local box = { k, k, rc:GetWidth() - k, rc:GetHeight() - k }
        local res = resolver(rc)
        for name, r in pairs({ title = rc.title, body = rc.body, ring = rc.ring, count = rc.count,
            accept = rc.accept, decline = rc.decline, waiting = rc.waiting }) do
            inside(res, r, box, "ready check " .. name)
        end
        for i, t in ipairs(rc.rules) do
            inside(res, t, box, "rule " .. i)
        end
        H.ok(res(rc.body)[4] <= res(rc.ring)[2], "the line above the ring")
        H.ok(res(rc.ring)[4] <= res(rc.count)[2], "the count under the ring")
        H.ok(res(rc.count)[4] <= res(rc.accept)[2], "the buttons under the count")
        for _, fs in ipairs({ rc.body, rc.count, rc.waiting }) do
            local _, size = fs:GetFont()
            H.ok(size * RS.PxPerUnit(fs) <= 32 + 1e-6, "text within 32 px")
            H.ok(fs:GetStringWidth() <= fs:GetWidth() + 0.01 or fs:GetWidth() == 0, "not cut: " .. fs:GetText())
        end
        -- every sized piece of art (the ring, its gems, the numerals, the title) is minified 2.2x at most
        local worst, what, n = 0, "", 0
        for _, o in ipairs(M.objects) do
            if o.__otype == "Texture" and type(o.rsPath) == "string" and o.rsPath:find(ROYALE_ART, 1, true) == 1
                and o:IsVisible() and RS.RootOf(o) == rc and o:GetHeight() > 0 and o.rsArt ~= "Plate"
                and o.rsArt ~= "ShineStrip" and o.rsArt ~= "Button" and o.rsArt ~= "ButtonGlow"
                and o.rsArt ~= "PlateTab" then
                local w, h = fileDims(o.rsPath)
                local ulx, uly, llx, lly = o:GetTexCoord()
                local texels = math.sqrt(((llx - ulx) * w) ^ 2 + ((lly - uly) * h) ^ 2)
                local ratio = texels / (o:GetHeight() * RS.PxPerUnit(o))
                n = n + 1
                if ratio > worst then worst, what = ratio, tostring(o.rsArt) .. " " .. o:GetHeight() end
            end
        end
        H.ok(n >= 18, "art measured: " .. n)
        H.ok(worst <= 2.2, ("texel ratio %.2f (%s)"):format(worst, what))
    end)
end

test("royale glue: Decline sends QREPLY 0 and the popup leaves; a new proposal enters again with the queue pop",
function(M, ns)
    connect(M)
    local rc = M.env.BleakholdRoyaleReady
    proposal(M, 15, 0)
    M.Advance(0.5)
    rc.decline:Click()
    M.Advance(0.3)
    H.ok(not rc:IsShown(), "gone")
    local sounds = #M.sounds
    H.send(M, "QUEUE", { { 9, 2, "B", 901, 0, 1, 120, "", 413, 15, 80, 80, 24, 20, 40, 0, 24, 1 } })
    H.ok(rc:IsShown())
    H.eq(M.sounds[sounds + 1], "PVPTHROUGHQUEUE")
    H.eq(rc:GetAlpha(), 0, "it fades in")
    M.Advance(0.3)
    H.eq(rc:GetAlpha(), 1)
    H.eq(lit(rc), 15, "the new proposal's gems all set")
end)

------------------------------------------------------------------------------------------------------
-- Options and commands
------------------------------------------------------------------------------------------------------
test("royale glue: /bh royale motion|sounds|farclip|scale set the options and say their state", function(M, ns)
    connect(M)
    local RS, opts = ns.RoyaleStyle, ns.db.options
    local from = #M.chat
    slash(M, "royale motion off")
    H.eq(opts.royaleMotion, false)
    H.ok(not RS.Motion())
    slash(M, "royale motion")
    slash(M, "royale motion on")
    H.eq(opts.royaleMotion, true)
    local text = chatSince(M, from)
    H.contains(text, "Royale motion: off. Every animation jumps to its end.")
    H.contains(text, "Royale motion: on.")
    from = #M.chat
    slash(M, "royale sounds off")
    H.eq(opts.royaleSounds, false)
    H.ok(not ns.RoyaleStyle.PlayFile("tick"), "no Royale sound while off")
    slash(M, "royale sounds on")
    H.ok(RS.Sounds())
    H.contains(chatSince(M, from), "Royale sounds: off.")
    -- the view distance: off puts a raised one back at once
    from = #M.chat
    roys(M, { [2] = 1, [3] = 50000 })
    H.eq(M.farclip, 1277, "raised for the drop")
    slash(M, "royale farclip off")
    H.eq(opts.royaleFarclip, false)
    H.eq(M.farclip, 777, "back at once")
    slash(M, "royale farclip on")
    H.eq(opts.royaleFarclip, true)
    text = chatSince(M, from)
    H.contains(text, "Royale view distance: off. Yours stays as it is.")
    H.contains(text, "Royale view distance: on. It rises to 1277")
    -- the HUD scale: every Royale root takes it; a word that is no number changes nothing; 0.8-1.4 only
    from = #M.chat
    slash(M, "royale scale 1.2")
    near(RS.HudScale(), 1.2)
    near(M.env.BleakholdRoyaleBar:GetScale(), 1.2, 1e-6, "the bar")
    near(M.env.BleakholdRoyaleReady:GetScale(), 1.2, 1e-6, "the ready check")
    slash(M, "royale scale big")
    near(RS.HudScale(), 1.2)
    slash(M, "royale scale 3")
    near(RS.HudScale(), 1.4)
    text = chatSince(M, from)
    H.contains(text, "Royale HUD scale: 1.20 (0.8 to 1.4).")
    H.contains(text, "Royale HUD scale: 1.40 (0.8 to 1.4).")
end)

test("royale glue: /bh royale minimap hands over to the minimap layer; the usage lists every command", function(M, ns)
    connect(M)
    local from = #M.chat
    slash(M, "royale minimap off")
    H.eq(ns.db.options.royaleMinimap, false)
    slash(M, "royale minimap on")
    H.eq(ns.db.options.royaleMinimap, true)
    H.ok(#M.chat >= from + 2, "the layer says its state")
    local usage = ns.commands.royale.help
    for _, word in ipairs({ "map", "leave", "preview", "countdown", "drop", "banner", "end", "motion", "sounds",
        "farclip", "minimap", "scale 0.8-1.4", "wall", "voice" }) do
        H.contains(usage, word)
    end
end)

------------------------------------------------------------------------------------------------------
-- Previews
------------------------------------------------------------------------------------------------------
test("royale glue: /bh royale preview countdown runs a sample lobby: the docked map, 15 to 1, DROP!, then it ends",
function(M, ns)
    connect(M)
    local R, S = ns.Royale, ns.S
    S.royaleResult = { matchId = 1234, placement = 3, total = 30, kills = 2, survivedSec = 300, rewards = {} }
    local sent = #M.sent
    local gongs = #M.sounds
    slash(M, "royale preview countdown")
    H.ok(R.InPreview(), "a sample match")
    H.eq(R.PreviewKind(), "countdown")
    H.ok(R.Match() ~= nil)
    H.eq(M.farclip, 777, "a preview leaves the view distance alone")
    M.Advance(0.3)
    H.ok(M.env.BleakholdRoyaleMapFrame:IsShown(), "the map opens docked as the landing phase starts")
    H.ok(ns.RoyaleMap.docked, "docked")
    M.Advance(1.2)
    H.eq(ns.RoyaleCountdown.Shown(), 15, "the countdown from 15")
    H.eq(S.royale.nextR, 520, "circle 1 came with the 15 s ROYS")
    -- a click on the map moves the sample's pin; nothing goes to the realm
    local canvas = ns.RoyaleMap.canvas
    local s = canvas:GetEffectiveScale()
    M.cursorX = (canvas:GetLeft() + 200) * s
    M.cursorY = (canvas:GetTop() - 300) * s
    M.Fire(canvas, "OnMouseUp", "LeftButton")
    M.Advance(0.5)
    H.ok(S.royale.pinX ~= -45, "the sample's pin moved: " .. tostring(S.royale.pinX))
    M.Advance(5.3)
    H.eq(ns.RoyaleCountdown.Shown(), 9)
    M.Advance(8.6)
    H.ok(not M.env.BleakholdRoyaleMapFrame:IsShown(), "the map closed at T-3.6")
    M.Advance(1.6)
    local gong = false
    for i = gongs + 1, #M.sounds do
        if M.sounds[i] == "Gong (Non-Looping)" then gong = true end
    end
    H.ok(gong, "DROP! and the gong")
    M.Advance(1.5)
    H.ok(not R.InPreview(), "the sample ended")
    H.eq(S.royale, nil)
    H.eq(S.royaleResult and S.royaleResult.matchId, 1234, "the player's last result is back for the card")
    M.Advance(1.2)
    H.ok(not M.env.BleakholdRoyaleBar:IsShown(), "the bar went with it")
    H.ok(not M.env.BleakholdRoyaleCountdown:IsShown())
    for i = sent + 1, #M.sent do
        local op = M.sent[i].msg:match("^%d+ (%u+) ")
        H.ok(op ~= "RDROP" and op ~= "GET", "nothing of the sample to the realm: " .. M.sent[i].msg)
    end
end)

test("royale glue: a second /bh royale preview countdown in one session docks the map and counts 15 to 1 again",
function(M, ns)
    connect(M)
    local R = ns.Royale
    local function gongs()
        local n = 0
        for _, snd in ipairs(M.sounds) do
            if snd == "Gong (Non-Looping)" then n = n + 1 end
        end
        return n
    end
    for run = 1, 2 do
        slash(M, "royale preview countdown")
        M.Advance(0.3)
        H.ok(M.env.BleakholdRoyaleMapFrame:IsShown(), "run " .. run .. ": the map opens docked")
        H.ok(ns.RoyaleMap.docked, "run " .. run .. ": docked")
        M.Advance(1.2)
        H.eq(ns.RoyaleCountdown.Shown(), 15, "run " .. run .. ": the countdown from 15")
        H.ok(M.env.BleakholdRoyaleCountdown:IsShown(), "run " .. run .. ": the ring shows")
        M.Advance(15.5)
        H.eq(gongs(), run, "run " .. run .. ": DROP! and its gong")
        M.Advance(1.5)
        H.ok(not R.InPreview(), "run " .. run .. ": the sample ended")
        M.Advance(1.2)
    end
end)

test("royale glue: a second /bh demo in one session counts down beside the map and drops on the same timing",
function(M, ns)
    local S = ns.S
    local RD = ns.RoyaleDrop
    for run = 1, 2 do
        slash(M, "demo")
        M.Advance(1)
        ns.Royale.Join()
        M.Advance(3.5)
        M.env.BleakholdRoyaleReady.accept:Click()
        local waited = 0
        while not ns.RoyaleCountdown.Shown() do
            M.Advance(0.05)
            waited = waited + 0.05
            assert(waited < 60, "run " .. run .. ": no countdown")
        end
        H.ok(ns.RoyaleCountdown.Shown() >= 14, "run " .. run .. ": from 15 or 14: " .. ns.RoyaleCountdown.Shown())
        H.ok(M.env.BleakholdRoyaleMapFrame:IsShown(), "run " .. run .. ": the lobby map opened by itself")
        local gong
        local from = #M.sounds
        while not gong do
            M.Advance(0.05)
            waited = waited + 0.05
            assert(waited < 90, "run " .. run .. ": no DROP!")
            for i = from + 1, #M.sounds do
                if M.sounds[i] == "Gong (Non-Looping)" then gong = M.env.GetTime() end
            end
        end
        -- the plate follows DROP! by RD.PLATE_DELAY, also when the demo's fixed match id comes back
        while M.env.GetTime() < gong + RD.PLATE_DELAY - 0.2 do
            M.Advance(0.05)
        end
        H.ok(not M.env.BleakholdRoyaleDrop:IsShown(), "run " .. run .. ": no plate before 0.8 s after DROP!")
        M.Advance(0.6)
        H.ok(M.env.BleakholdRoyaleDrop:IsShown(), "run " .. run .. ": the drop plate")
        H.eq(S.royale.me, 1, "run " .. run .. ": falling")
        slash(M, "demo off")
        M.Advance(2)
    end
end)

test("royale glue: /bh royale preview map shows the fight's map until it is closed", function(M, ns)
    connect(M)
    local R, S = ns.Royale, ns.S
    slash(M, "royale preview map")
    M.Advance(0.3)
    local win = M.env.BleakholdRoyaleMapFrame
    H.ok(win:IsShown(), "the map")
    H.eq(R.PreviewKind(), "map")
    H.eq(S.royale.phase, 3)
    H.eq(S.royale.nextR, 300)
    H.ok(S.royaleObjects and #S.royaleObjects.list >= 8, "orbs and supply drops")
    local left, right = ns.RoyaleMap.StatusText(S.royale)
    H.contains(left, "Storm closes in 1:2")
    H.eq(right, "Circle 2 of 6")
    -- kept going past the 25 s a match without ROYS goes stale
    M.Advance(40)
    H.ok(R.Match() ~= nil and R.InPreview(), "still on after 40 s")
    H.ok(win:IsShown())
    ns.RoyaleMap.Close()
    M.Advance(0.6)
    H.ok(not R.InPreview(), "closing the map ends it")
    H.eq(S.royale, nil)
end)

test("royale glue: the drop, the banners and the end card preview through their modules; none during a match",
function(M, ns)
    connect(M)
    local R = ns.Royale
    slash(M, "royale preview drop")
    M.Advance(1)
    H.ok(M.env.BleakholdRoyaleDrop:IsShown(), "the drop plate")
    M.Advance(25)
    slash(M, "royale preview banner")
    M.Advance(0.3)
    H.eq(ns.RoyaleHud.current.title, "NEW STORM CIRCLE")
    slash(M, "royale preview end eliminated")
    M.Advance(1)
    H.eq(M.env.BleakholdRoyaleResult.title.title, "ELIMINATED")
    M.env.BleakholdRoyaleResult.keep:Click()
    -- a real match refuses them (and a preview never replaces it)
    roys(M, { [2] = 3, [6] = 2, [11] = 1 })
    local from = #M.chat
    for _, kind in ipairs({ "countdown", "map", "drop", "banner", "end" }) do
        local ok = R.Preview(kind)
        H.ok(not ok, kind .. " refused in a match")
        slash(M, "royale preview " .. kind)
    end
    H.eq(ns.S.royale.matchId, 7001, "the match stays")
    H.contains(chatSince(M, from), "Royale previews play outside a match.")
    from = #M.chat
    roys(M, { [2] = 6 })
    M.Advance(30)
    slash(M, "royale preview nothing")
    H.contains(chatSince(M, from), "/bh royale preview countdown|drop|banner|end [eliminated]|map")
end)

test("royale glue: a real match's ROYS takes over from a preview", function(M, ns)
    connect(M)
    local R = ns.Royale
    slash(M, "royale preview map")
    M.Advance(0.6)
    roys(M, { [2] = 1, [3] = 40000 })
    M.Advance(0.6)
    H.ok(not R.InPreview())
    H.eq(R.PreviewKind(), nil)
    H.eq(ns.S.royale.matchId, 7001)
end)

------------------------------------------------------------------------------------------------------
-- Toasts during a match
------------------------------------------------------------------------------------------------------
test("royale glue: in a match MATCH CANCELLED is the banner (after the countdown's own), a queue notice a chat line",
function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    roys(M, { [2] = 1, [3] = 12000 })
    M.Advance(1)
    H.ok(M.env.BleakholdRoyaleCountdown:IsShown(), "the countdown runs")
    roys(M, { [2] = 7, [3] = 0 })
    M.Advance(0.3)
    H.ok(not M.env.BleakholdToastFrame:IsShown(), "no toast over the banner band")
    H.ok(ns.RoyaleHud.current == nil or ns.RoyaleHud.current.key ~= "toast", "the banner waits for the countdown")
    M.Advance(2.5)
    local cur = ns.RoyaleHud.current
    H.ok(cur and cur.key == "toast", "the banner")
    H.eq(cur.title, "MATCH CANCELLED")
    H.eq(cur.color, "blood")
    H.eq(ns.RoyaleHud.banner.line:GetText(), "Too few players came. You keep your place in the queue.")
    -- the realm's queue notices in a match: a chat line
    local from = #M.chat
    H.send(M, "TOAST", { { "Q", "Bleakhold Royale", "You left the queue.", "royale" } })
    H.ok(not M.env.BleakholdToastFrame:IsShown())
    H.contains(chatSince(M, from), "You left the queue.")
    -- outside a match toasts are as they were
    ns.Royale.ForgetMatch()
    H.send(M, "TOAST", { { "Q", "Bleakhold Royale", "24 players are ready", "royale" } })
    H.ok(M.env.BleakholdToastFrame:IsShown(), "the toast outside a match")
end)

------------------------------------------------------------------------------------------------------
-- /bh demo's drop
------------------------------------------------------------------------------------------------------
test("royale glue: /bh demo drops as the realm does: 8 s of freefall, then 12 s under the parachute (fields 25-27)",
function(M, ns)
    local S = ns.S
    slash(M, "demo")
    M.Advance(1)
    ns.Royale.Join()
    M.Advance(3.5)
    M.env.BleakholdRoyaleReady.accept:Click()
    local waited = 0
    while not (S.royale and S.royale.me == 1) do      -- the teleport, 26 s into the match
        M.Advance(0.05)
        waited = waited + 0.05
        assert(waited < 60, "no drop")
    end
    local m = S.royale
    H.eq(m.fallMsLeft, 8000); H.eq(m.landMsLeft, 20000); H.eq(m.fallMs, 8000)
    H.eq(m.phaseMsLeft, 20000, "phase 2 lasts until the planned touchdown")
    local teleport = m.recvAt
    M.Advance(0.25)        -- the start gun: the plan again from the fall's real start
    H.ok(S.royale.recvAt > teleport, "the start gun's ROYS")
    H.eq(S.royale.fallMsLeft, 8000)
    M.Advance(1.45)
    H.ok(M.env.BleakholdRoyaleDrop:IsShown(), "the drop plate")
    H.eq(ns.RoyaleDrop.plate.num:GetValue(), "7", "FREEFALL counts down from 8")
    M.Advance(6.6)         -- the parachute opens by itself
    H.eq(S.royale.fallMsLeft, 0); H.eq(S.royale.landMsLeft, 12000)
    M.Advance(12.25)       -- touchdown 20 s after the start gun, seen 0.5 s later
    H.eq(S.royale.me, 1, "still under the parachute")
    M.Advance(0.35)
    H.eq(S.royale.me, 2, "landed")
    H.eq(S.royale.phase, 3)
    H.eq(S.royale.fallMsLeft, nil, "no drop times once down")
    slash(M, "demo off")
    M.Advance(0.5)
end)

------------------------------------------------------------------------------------------------------
-- Royale.lua's wording and the client's Lua
------------------------------------------------------------------------------------------------------
-- A file's code without its comments.
local function code(name)
    local text = assert(host_readfile(addonDir .. "/" .. name), name)
    local out = {}
    for line in (text .. "\n"):gmatch("(.-)\n") do
        local inStr, quote, cut = false, nil, nil
        local i = 1
        while i <= #line do
            local c = line:sub(i, i)
            if inStr then
                if c == "\\" then
                    i = i + 1
                elseif c == quote then
                    inStr = false
                end
            elseif c == '"' or c == "'" then
                inStr, quote = true, c
            elseif line:sub(i, i + 1) == "--" then
                cut = i
                break
            end
            i = i + 1
        end
        out[#out + 1] = cut and line:sub(1, cut - 1) or line
    end
    return table.concat(out, "\n")
end

test("royale glue: Royale.lua's strings follow the design's wording: no key names, no glued sentences", function(M, ns)
    local src = code("Royale.lua")
    for _, s in ipairs({ "Your match is ready", "Accepted - waiting", "Open parachute", "OPEN PARACHUTE",
        "bind a key", "B L E A K H O L D", "MORPHEUS" }) do
        H.ok(not src:find(s, 1, true), "Royale.lua still says: " .. s)
    end
    for lit in src:gmatch('"([^"]*ALT%-M[^"]*)"') do
        H.ok(false, "Royale.lua names a key: " .. lit)
    end
    for lit in src:gmatch('"([^"\n]*)"') do
        if lit:find("·", 1, true) then
            H.ok(not lit:find("[%.!?]%s*·"), "Royale.lua glues sentences: " .. lit)
        end
    end
    H.contains(src, "fall for 8 s, and your parachute opens by itself", "the help text has the owner's drop")
end)

-- The number of constants of a file's main chunk, from string.dump (the client's Lua 5.1 bytecode).
local function mainChunkConstants(path)
    local d = string.dump(assert(loadstring(assert(host_readfile(path)))))
    local sizeT, pos = d:byte(9), 13
    local function int()
        local a, b, c, e = d:byte(pos, pos + 3)
        pos = pos + 4
        return a + b * 256 + c * 65536 + e * 16777216
    end
    local n = 0
    for i = sizeT - 1, 0, -1 do n = n * 256 + d:byte(pos + i) end
    pos = pos + sizeT + n           -- the source name
    int(); int()                    -- the first and last line
    pos = pos + 4                   -- upvalues, parameters, vararg, stack size
    pos = pos + 4 * int()           -- the code
    return int()
end

test("royale glue: Royale.lua's main chunk stays under 256 constants (the client's Lua 5.1 miscompiles past them)",
function(M, ns)
    local n = mainChunkConstants(addonDir .. "/Royale.lua")
    H.ok(n > 50 and n < 256, "main chunk constants: " .. n)
end)
