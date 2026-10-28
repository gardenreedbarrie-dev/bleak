-- Bleakhold Royale's island map (RoyaleMap.lua): the M key through override bindings that wait out combat, the stock
-- world map redirected out of combat and covered in combat while patch-Q lacks the island's tiles (Shift-M's
-- battlefield minimap too), the lobby dock and its scale, the pin lock, labels that never collide, the place a point
-- lands near, the way to the next circle, the storm's shade snapped to whole pixels, the status line, and the texel
-- ratio of every texture the map shows.
local MAP = {
    { 901, -1066, 533, -1066, 533, 455, 455, 32, 750, -267, -267 }, { 1, "L", -266, -266, 88, "The Bleak Hold" },
    { 2, "L", 120, 80, 62, "Harrow Farm" }, { 11, "C", -80, -710, 16, "Old Ford" },
    { 14, "Y", 455, 455, 32, "The Overlook" },
}
-- the places of Bleakhold Royale v2 (Royale.lua's demo, as the server sends them)
local DEMO_PLACES = {
    { 5213, "Y", 455, 455, 32, "Sunwatch Overlook" },
    { 5201, "L", -258, -345, 95, "Sunstair Isle" }, { 5202, "L", -45, -170, 90, "Tidecall Village" },
    { 5203, "L", 320, -790, 80, "Twinfall Terrace" }, { 5204, "L", -490, -662, 60, "Saltwreck Cove" },
    { 5205, "L", -776, 339, 80, "Serpent Steps" }, { 5206, "L", -250, 200, 90, "Sunbloom Meadow" },
    { 5207, "L", 215, -312, 50, "Kingfisher Point" }, { 5208, "L", -255, -745, 80, "Mossvine Hollow" },
    { 5209, "L", -740, -290, 70, "Bamboo Reach" }, { 5210, "L", 360, 250, 60, "Sunwatch Falls" },
    { 5215, "L", -790, -784, 70, "Salvagers' Camp" }, { 5216, "L", -425, 50, 50, "Totem Knoll" },
    { 5217, "L", 80, -520, 50, "Heron Rise" },
    { 5211, "C", -10, -625, 16, "Stepping Stones" }, { 5212, "C", -785, 263, 18, "Vine Bridge" },
    { 5214, "C", -150, -275, 14, "Tidewalk" },
}
local PROBE = "Interface\\WorldMap\\BleakholdRoyale\\BleakholdRoyale1"
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

-- A ROYS (field index -> value): the lobby's landing phase unless `over` says otherwise.
local function roys(M, over)
    local r = { 7001, 1, 60000, 24, 24, 0, 0, "", "", "", 0, -267, -267, 860, "", "", "", "", "", 0, "", 450, 452 }
    for k, v in pairs(over or {}) do r[k] = v end
    H.send(M, "ROYS", { r })
end

-- The fight: circle 2 (curR 520 round -150,-310), moving to 300 round -60,-380; the player at (myX, myY).
local function fight(M, over)
    local o = { [2] = 3, [3] = 0, [6] = 2, [11] = 2, [12] = -150, [13] = -310, [14] = 520, [15] = -60, [16] = -380,
        [17] = 300, [18] = 20000, [19] = 60000, [22] = 210, [23] = -20 }
    for k, v in pairs(over or {}) do o[k] = v end
    roys(M, o)
end

local function count(list, v)
    local n = 0
    for _, x in ipairs(list) do
        if x == v then n = n + 1 end
    end
    return n
end

local function inBattleground(M)
    M.inInstance, M.instanceType = true, "pvp"
end

local function worldMap(M)
    M.LoadWorldMap()
end

------------------------------------------------------------------------------------------------------
-- (a) The M key
------------------------------------------------------------------------------------------------------
test("royale map: ROYM in a Royale battleground makes M open the island map (override binding)", function(M, ns)
    M.bindings.M = "TOGGLEWORLDMAP"
    inBattleground(M)
    connect(M)
    local MP = ns.RoyaleMap
    H.eq(M.OverrideAction("M"), nil, "nothing before the map")
    H.eq(MP.KeyText(), "/bh royale map", "no key yet: the command")
    H.send(M, "ROYM", MAP)
    H.eq(M.OverrideAction("M"), "BLEAKHOLD_ROYALE_MAP")
    local b = M.overrideBindings[1]
    H.eq(b.owner, M.env.BleakholdRoyaleBindings, "owned by BleakholdRoyaleBindings")
    H.eq(b.priority, false)
    H.eq(MP.KeyText(), "M", "the banner and the tab say M")
    -- M runs the map's binding: it toggles the window
    roys(M)
    M.Advance(0.2)
    M.env.BleakholdToggle("royalemap")
    H.ok(not M.env.BleakholdRoyaleMapFrame:IsShown(), "the auto-opened map toggles closed")
    M.env.BleakholdToggle("royalemap")
    H.ok(M.env.BleakholdRoyaleMapFrame:IsShown(), "and open again")
    -- the world map's key changes during the match: the override follows
    M.bindings.M, M.bindings.N = nil, "TOGGLEWORLDMAP"
    M.FireEvent("UPDATE_BINDINGS")
    H.eq(M.OverrideAction("M"), nil)
    H.eq(M.OverrideAction("N"), "BLEAKHOLD_ROYALE_MAP")
    -- leaving the battleground clears it
    M.inInstance, M.instanceType = false, "none"
    M.FireEvent("PLAYER_ENTERING_WORLD")
    H.eq(#M.overrideBindings, 0, "cleared")
    H.eq(MP.KeyText(), "ALT-M", "the map's own key again (offered with the first ROYS)")
end)

test("royale map: outside a battleground (the demo, another map) M stays the world map", function(M, ns)
    M.bindings.M = "TOGGLEWORLDMAP"
    connect(M)
    H.send(M, "ROYM", MAP)
    H.eq(#M.overrideBindings, 0, "not in a battleground")
    inBattleground(M)
    local other = { { 30, -1066, 533, -1066, 533, 455, 455, 32, 750, -267, -267 } }
    H.send(M, "ROYM", other)
    H.eq(#M.overrideBindings, 0, "another map")
    M.bindings["ALT-M"] = "BLEAKHOLD_ROYALE_MAP"
    H.eq(ns.RoyaleMap.KeyText(), "ALT-M", "the map's own key")
end)

test("royale map: in combat both the set and the clear wait for PLAYER_REGEN_ENABLED; the last one wins",
function(M, ns)
    M.bindings.M = "TOGGLEWORLDMAP"
    inBattleground(M)
    connect(M)
    local MP = ns.RoyaleMap
    -- the mock raises if SetOverrideBinding or ClearOverrideBindings runs in combat: the addon would report it
    M.SetCombat(true)
    H.send(M, "ROYM", MAP)
    roys(M)
    M.Advance(0.3)
    H.eq(#M.overrideBindings, 0, "nothing set in combat")
    H.eq(MP.bindQueue, "set")
    M.SetCombat(false)
    H.eq(M.OverrideAction("M"), "BLEAKHOLD_ROYALE_MAP", "set once combat ends")
    H.eq(MP.bindQueue, nil)
    -- the victory hold: the match is forgotten in combat
    M.SetCombat(true)
    M.inInstance, M.instanceType = false, "none"
    M.FireEvent("PLAYER_ENTERING_WORLD")
    H.eq(ns.S.royaleMap, nil, "forgotten")
    H.eq(M.OverrideAction("M"), "BLEAKHOLD_ROYALE_MAP", "still set in combat")
    H.eq(MP.bindQueue, "clear")
    M.SetCombat(false)
    H.eq(#M.overrideBindings, 0, "cleared once combat ends")
    -- set then clear within one fight: only the clear runs
    inBattleground(M)
    M.SetCombat(true)
    H.send(M, "ROYM", MAP)
    H.eq(MP.bindQueue, "set")
    M.inInstance, M.instanceType = false, "none"
    M.FireEvent("PLAYER_ENTERING_WORLD")
    H.eq(MP.bindQueue, "clear", "the last one queued")
    M.SetCombat(false)
    H.eq(#M.overrideBindings, 0)
    H.eq(#M.errors, 0, "no protected call in combat")
end)

------------------------------------------------------------------------------------------------------
-- (b) (c) The stock world map
------------------------------------------------------------------------------------------------------
test("royale map: out of combat the stock world map showing the island is hidden and ours opens", function(M, ns)
    inBattleground(M)
    connect(M)
    H.send(M, "ROYM", MAP)
    fight(M)
    M.Advance(0.3)
    local wm, ours = M.env.WorldMapFrame, M.env.BleakholdRoyaleMapFrame
    H.ok(not ours:IsShown(), "not opened by itself in the fight")
    M.mapInfo = "BleakholdRoyale"
    wm:Show()
    M.Advance(0.1)                     -- the next frame
    H.ok(not wm:IsShown(), "the stock map hidden")
    H.eq(M.hiddenPanels[#M.hiddenPanels], wm, "through HideUIPanel")
    H.ok(ours:IsShown(), "ours open")
    H.eq(ours:GetFrameStrata(), "HIGH")
    H.ok(not M.env.BleakholdRoyaleWorldMapCover:IsShown(), "patch-Q has the tiles: no cover")
    -- the player browses another map: left alone
    ns.RoyaleMap.Close()
    M.mapInfo = "Elwynn"
    local hidden = #M.hiddenPanels
    wm:Show()
    M.Advance(0.1)
    H.ok(wm:IsShown(), "Azeroth stays on screen")
    H.eq(#M.hiddenPanels, hidden)
    H.ok(not ours:IsShown())
end, { before = worldMap })

test("royale map: in combat the stock map is never touched: the cover hides its stale tiles and ours opens above it",
function(M, ns)
    M.missingTextures[PROBE] = true
    inBattleground(M)
    connect(M)
    H.send(M, "ROYM", MAP)
    fight(M)
    M.Advance(0.3)
    local wm, ours = M.env.WorldMapFrame, M.env.BleakholdRoyaleMapFrame
    local cover = M.env.BleakholdRoyaleWorldMapCover
    M.mapInfo = "BleakholdRoyale"
    M.SetCombat(true)
    wm:Show()
    M.Advance(0.1)
    H.ok(wm:IsShown(), "the stock map stays (protected in combat)")
    H.eq(#M.hiddenPanels, 0, "never hidden in combat")
    H.ok(cover:IsShown(), "the cover over the stale tiles")
    H.eq(cover:GetParent(), M.env.WorldMapDetailFrame)
    H.ok(cover:GetFrameLevel() < M.env.WorldMapButton:GetFrameLevel(), "under the player arrow and the POIs")
    H.ok(ours:IsShown(), "ours open")
    H.eq(ours:GetFrameStrata(), "FULLSCREEN_DIALOG", "above the stock map")
    -- the island letterboxed into the 1002:668 frame: the full height, centred, sea beside it
    local pic = cover.pic
    near(pic:GetHeight(), M.env.WorldMapDetailFrame:GetHeight(), 1e-6, "the island fills the height")
    local _, _, _, x = pic:GetPoint(1)
    near(x * 2 + pic:GetWidth(), M.env.WorldMapDetailFrame:GetWidth(), 1e-6, "centred")
    H.eq(pic:GetTexture(), ns.Royale.MAP_TEX)
    -- closing the stock map closes ours with it, silently (the stock map plays its own sound)
    local closes = count(M.sounds, "igCharacterInfoClose")
    wm:Hide()
    H.ok(not ours:IsShown(), "ours closes with it")
    H.eq(count(M.sounds, "igCharacterInfoClose"), closes)
    H.ok(not cover:IsShown() or not wm:IsVisible(), "the cover goes with the map")
    -- another map in combat: no cover, ours stays shut
    M.mapInfo = "Elwynn"
    wm:Show()
    M.Advance(0.1)
    H.ok(not cover:IsShown(), "no cover over Azeroth")
    H.ok(not ours:IsShown())
    M.SetCombat(false)
    H.eq(#M.errors, 0)
end, { before = worldMap })

test("royale map: Shift-M's battlefield minimap gets the cover while the tiles are missing", function(M, ns)
    M.missingTextures[PROBE] = true
    inBattleground(M)
    connect(M)
    H.send(M, "ROYM", MAP)
    fight(M)
    M.Advance(0.3)
    local bm = M.LoadBattlefieldMinimap()
    local cover = M.env.BleakholdRoyaleBattlefieldCover
    H.ok(cover, "made on ADDON_LOADED")
    H.ok(cover:IsShown(), "shown during the match")
    H.eq(cover:GetParent(), bm)
    H.eq(cover:GetFrameLevel(), bm:GetFrameLevel(), "at the minimap's level: over its tiles, under its POIs")
    -- the map area of 4 x 3 tiles holds the 1002 x 668 frame; the island fills its height
    local tile = M.env.BattlefieldMinimap1:GetWidth()
    near(cover:GetWidth(), tile * 4 * 1002 / 1024)
    near(cover.pic:GetHeight(), tile * 3 * 668 / 768)
    -- the match ends: gone
    M.inInstance, M.instanceType = false, "none"
    M.FireEvent("PLAYER_ENTERING_WORLD")
    H.ok(not cover:IsShown(), "no match, no cover")
end)

test("royale map: with patch-Q's tiles neither cover shows", function(M, ns)
    inBattleground(M)
    connect(M)
    H.send(M, "ROYM", MAP)
    fight(M)
    M.Advance(0.3)
    M.LoadBattlefieldMinimap()
    M.mapInfo = "BleakholdRoyale"
    M.SetCombat(true)
    M.env.WorldMapFrame:Show()
    M.Advance(0.1)
    H.ok(not M.env.BleakholdRoyaleWorldMapCover:IsShown())
    H.ok(not M.env.BleakholdRoyaleBattlefieldCover:IsShown())
    M.SetCombat(false)
end, { before = worldMap })

------------------------------------------------------------------------------------------------------
-- The window: auto-open, dock, pin lock, sounds
------------------------------------------------------------------------------------------------------
test("royale map: not in the warm-up brawl; opens by itself once when the landing phase starts, docked", function(M, ns)
    M.SetScreen(1920, 1080, 1)
    connect(M)
    H.send(M, "ROYM", MAP)
    roys(M, { [2] = 0 })
    M.Advance(0.3)
    local w, MP = M.env.BleakholdRoyaleMapFrame, ns.RoyaleMap
    H.ok(not w:IsShown(), "phase 0: closed (it would cover the chat and the unit frames)")
    roys(M, { [2] = 1 })
    M.Advance(0.1)
    H.ok(w:IsShown(), "phase 1: open")
    H.ok(MP.auto, "opened by itself")
    H.eq(count(M.sounds, "igCharacterInfoOpen"), 1)
    H.eq(w:GetFrameStrata(), "HIGH")
    -- docked: scale min(1, (768 - 136) / 700, (W/2 - 48) / 592) on 16:9; right edge 24 left of the centre
    near(w:GetScale(), (768 - 136) / 700, 1e-6, "0.903 on 16:9")
    local p, rel, rp, x, y = w:GetPoint(1)
    H.eq(p, "TOPRIGHT"); H.eq(rel, M.env.UIParent); H.eq(rp, "TOP")
    near(x * w:GetScale(), -24); near(y * w:GetScale(), -112)
    -- closed by hand: it stays closed for the match
    MP.Close()
    roys(M, { [2] = 1, [3] = 50000 })
    M.Advance(0.2)
    H.ok(not w:IsShown(), "closing keeps it closed")
    H.eq(count(M.sounds, "igCharacterInfoClose"), 1, "a hand close has its sound")
end)

test("royale map: the dock fits 4:3 and 5:4 and a larger HUD scale never pushes it off the screen", function(M, ns)
    local MP = ns.RoyaleMap
    connect(M)
    H.send(M, "ROYM", MAP)
    roys(M)
    M.Advance(0.2)
    local w = M.env.BleakholdRoyaleMapFrame
    for _, c in ipairs({ { 1024, 768, 1, (512 - 48) / 592 }, { 1280, 1024, 1 } }) do
        M.SetScreen(c[1], c[2], c[3])
        M.Advance(0.1)
        local W, Hh = M.env.UIParent:GetWidth(), M.env.UIParent:GetHeight()
        local s = w:GetScale()
        near(s, c[4] or math.min(1, (Hh - 136) / 700, (W / 2 - 48) / 592), 1e-6, "the fit at " .. c[1])
        H.ok(MP.W * s <= W / 2 - 24 + 1e-6, "inside the left half")
        H.ok(MP.H * s <= Hh - 112 + 1e-6, "under the tab, above the bottom")
    end
    M.SetScreen(1920, 1080, 1)
    ns.RoyaleStyle.SetHudScale(1.4)
    M.Advance(0.1)
    -- 1.4 would not fit, and its bar's tab ends 137.2 down: the dock starts 14 under it, the fit wins
    near(w:GetScale(), (768 - (98 * 1.4 + 14) - 24) / 700, 1e-6, "1.4 would not fit: the fit wins")
    local _, _, _, _, y = w:GetPoint(1)
    near(y * w:GetScale(), -(98 * 1.4 + 14), 1e-6, "under the larger tab")
    ns.RoyaleStyle.SetHudScale(0.8)
    M.Advance(0.1)
    near(w:GetScale(), 0.8, 1e-6, "a smaller HUD scale is honoured")
end)

test("royale map: from the drop on it opens at the centre (or where it was dragged) at the HUD scale", function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    fight(M)
    M.Advance(0.2)
    local w, MP = M.env.BleakholdRoyaleMapFrame, ns.RoyaleMap
    ns.UI.Open("royalemap", true)
    H.ok(w:IsShown())
    H.eq(MP.docked, false)
    local p, _, rp, x, y = w:GetPoint(1)
    H.eq(p, "CENTER"); H.eq(rp, "CENTER"); H.eq(x, 0); H.eq(y, 0)
    near(w:GetScale(), 1)
    -- dragged: the spot is kept for the fight
    M.Fire(w.header, "OnDragStart")
    w:ClearAllPoints()
    w:SetPoint("TOPLEFT", M.env.UIParent, "TOPLEFT", 40, -60)
    M.Fire(w.header, "OnDragStop")
    MP.Close()
    ns.UI.Open("royalemap", true)
    p, _, rp, x, y = w:GetPoint(1)
    H.eq(p, "TOPLEFT"); H.eq(x, 40); H.eq(y, -60)
    H.ok(ns.cdb.windows.BleakholdRoyaleMapFrame, "saved per character")
end)

test("royale map: ESC closes it; the close button and the open have their sounds; the T-3.6 close is silent",
function(M, ns)
    local names = {}
    for _, n in ipairs(M.env.UISpecialFrames) do names[n] = true end
    H.ok(names.BleakholdRoyaleMapFrame, "in UISpecialFrames")
    connect(M)
    H.send(M, "ROYM", MAP)
    roys(M)
    M.Advance(0.2)
    local w, MP = M.env.BleakholdRoyaleMapFrame, ns.RoyaleMap
    M.Fire(w.close, "OnClick")
    H.ok(not w:IsShown())
    H.eq(count(M.sounds, "igCharacterInfoClose"), 1)
    MP.Open(false)
    MP.Close(true)
    H.eq(count(M.sounds, "igCharacterInfoClose"), 1, "silent")
end)

test("royale map: the client locks the pin at T-3.6: clicks are refused, the status says so", function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    local MP = ns.RoyaleMap
    roys(M, { [3] = 40000 })
    M.Advance(0.05)
    H.eq(select(1, MP.StatusText(ns.Royale.Match())), "Click to choose your landing.")
    -- the status counts down to the client's lock, 0.6 s before the server's
    roys(M, { [3] = 12000 })
    M.Advance(0.05)
    H.eq(select(1, MP.StatusText(ns.Royale.Match())), "Landing locks in 0:09")
    roys(M, { [3] = 3500, [9] = 120, [10] = 80 })
    M.Advance(0.1)
    H.ok(MP.PinLocked(), "locked 0.6 s before the server")
    H.ok(ns.Royale.CanPin(), "the server would still take it")
    MP.Open(false)
    local canvas = MP.canvas
    M.cursorX = (canvas:GetLeft() + 100) * canvas:GetEffectiveScale()
    M.cursorY = (canvas:GetTop() - 100) * canvas:GetEffectiveScale()
    M.Fire(canvas, "OnMouseUp", "LeftButton")
    M.Advance(0.6)
    H.eq(H.countIntents(M, "RDROP"), 0, "no RDROP after the client's lock")
    H.eq(select(1, MP.StatusText(ns.Royale.Match())), "Landing locked")
end)

test("royale map: the status line through the match", function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    local MP, R = ns.RoyaleMap, ns.Royale
    roys(M, { [2] = 2, [3] = 20000, [6] = 1, [11] = 1, [24] = 6, [25] = 8000, [26] = 20000, [27] = 8000 })
    local left, right = MP.StatusText(R.Match())
    H.eq(left, "Landing in 0:20"); H.eq(right, "Circle 1 of 6")
    fight(M)
    left, right = MP.StatusText(R.Match())
    H.eq(left, "Storm closes in 0:20"); H.eq(right, "Circle 2 of 6")
    M.Advance(25)
    fight(M, { [18] = 0, [19] = 15000 })
    left = MP.StatusText(R.Match())
    H.eq(left, "Storm closing 0:15")
    fight(M, { [6] = 3, [21] = "Aldric" })
    H.eq(MP.StatusText(R.Match()), "Watching Aldric")
    roys(M, { [2] = 5, [6] = 3 })
    H.eq(MP.StatusText(R.Match()), "The match is over.")
    -- the header pill
    MP.Open(false)
    fight(M, { [4] = 17 })
    M.Advance(0.2)
    H.eq(M.env.BleakholdRoyaleMapFrame.alive.text:GetText(), "17/24 ALIVE")
end)

------------------------------------------------------------------------------------------------------
-- Places, the way, the shade
------------------------------------------------------------------------------------------------------
local function demoMap()
    local recs = { { 901, -1066, 533, -1066, 533, 455, 455, 32, 750, -267, -267 } }
    for _, p in ipairs(DEMO_PLACES) do recs[#recs + 1] = p end
    return recs
end

local function overlap(a, b)
    return a.l < b.r and b.l < a.r and a.t < b.b and b.t < a.b
end

test("royale map: the 17 places' labels never overlap each other, an icon or the scale bar, and stay inside",
function(M, ns)
    for _, screen in ipairs({ { 1920, 1080, 1 }, { 1280, 1024, 1 } }) do
        M.SetScreen(screen[1], screen[2], screen[3])
        connect(M)
        H.send(M, "ROYM", demoMap())
        roys(M)
        M.Advance(0.2)
        local MP = ns.RoyaleMap
        local list, rects = MP.labelList, MP.labelRects
        H.eq(#list, 17)
        local placed = 0
        for i, r in ipairs(rects) do
            if r then
                placed = placed + 1
                H.ok(r.l >= 0 and r.t >= 0 and r.r <= MP.SIZE and r.b <= MP.SIZE, "inside the canvas")
                for j, o in ipairs(rects) do
                    if o and j ~= i then
                        H.ok(not overlap(r, o), "labels " .. i .. " and " .. j .. " overlap")
                    end
                end
                for _, e in ipairs(list) do
                    local h = e.icon / 2
                    H.ok(not overlap(r, { l = e.x - h, t = e.y - h, r = e.x + h, b = e.y + h }), "label over an icon")
                end
                local sb = MP.scaleBar
                H.ok(not overlap(r, { l = 10, t = MP.SIZE - 10 - sb:GetHeight(), r = 10 + sb:GetWidth(),
                    b = MP.SIZE - 10 }), "label over the scale bar")
                near(r.r - r.l, list[i].w); near(r.b - r.t, list[i].h, 1e-6, "the halo is in the rectangle")
            end
        end
        H.ok(placed >= 15, "most places are named: " .. placed)
        -- the lobby first, then landmarks by radius, crossings last
        H.eq(list[1].icon, MP.ICON_LOBBY)
        H.eq(list[17].icon, MP.ICON_CROSSING)
        -- crossings show their name on hover only
        local crossing
        for i = 1, MP.pois.used do
            local f = MP.pois.items[i]
            if f.poi.kind == "C" and f.label.mpRect then crossing = f end
        end
        H.ok(crossing and not crossing.label:IsShown(), "a crossing's name hidden")
        M.Fire(crossing, "OnEnter")
        H.ok(crossing.label:IsShown(), "shown on hover")
        M.Fire(crossing, "OnLeave")
        H.ok(not crossing.label:IsShown())
    end
end)

test("royale map: an object over a place's label fades the label; the label keeps its place", function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    fight(M)
    local MP = ns.RoyaleMap
    MP.Open(false)
    M.Advance(0.2)
    local farm
    for i = 1, MP.pois.used do
        if MP.pois.items[i].poi.name == "Harrow Farm" then farm = MP.pois.items[i] end
    end
    local r = farm.label.mpRect
    near(farm.label:GetAlpha(), 1)
    -- an orb respawning (a timer) right on the label
    local x, y = MP.ToWorld((r.l + r.r) / 2, r.t)
    H.send(M, "ROYO", { { 7001, 1 }, { 6, "B", 3, math.floor(x), math.floor(y), 2, 45000 } })
    M.Advance(0.1)
    near(farm.label:GetAlpha(), 0.3, 1e-6, "faded under the orb and its timer")
    local _, _, _, lx, ly = farm.label:GetPoint(1)
    near(lx, r.l); near(-ly, r.t)
    H.send(M, "ROYO", { { 7001, 1 } })
    M.Advance(0.1)
    near(farm.label:GetAlpha(), 1, 1e-6, "back once the orb is gone")
end)

test("royale map: LayoutLabels moves a label round its icon and drops it when nothing fits", function(M, ns)
    local MP = ns.RoyaleMap
    local rects = MP.LayoutLabels({
        { x = 280, y = 280, icon = 14, w = 80, h = 19 },
        { x = 280, y = 280, icon = 14, w = 80, h = 19 },
        { x = 280, y = 280, icon = 14, w = 80, h = 19 },
        { x = 280, y = 280, icon = 14, w = 80, h = 19 },
        { x = 280, y = 280, icon = 14, w = 80, h = 19 },
        { x = 20, y = 20, icon = 14, w = 100, h = 19 },
    })
    near(rects[1].t, 280 + 7 + 4, 1e-6, "below first")
    near(rects[2].b, 280 - 7 - 4, 1e-6, "then above")
    near(rects[3].l, 280 + 7 + 4, 1e-6, "then right")
    near(rects[4].r, 280 - 7 - 4, 1e-6, "then left")
    H.eq(rects[5], false, "no room left")
    H.ok(rects[6] and rects[6].l == 20 + 7 + 4, "a corner place takes what stays inside: right of it")
end)

test("royale map: NearestPlace names the landmark or crossing within 1.5 radii, the nearest centre first",
function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    local MP = ns.RoyaleMap
    H.eq(MP.NearestPlace(120, 80), "Harrow Farm")
    H.eq(MP.NearestPlace(120 + 62 * 1.4, 80), "Harrow Farm", "within 1.5 radii")
    H.eq(MP.NearestPlace(120 + 62 * 1.6, 80), "the wilds", "beyond")
    H.eq(MP.NearestPlace(-80, -700), "Old Ford", "crossings count")
    H.eq(MP.NearestPlace(455, 455), "the wilds", "the lobby is no landing")
    H.eq(MP.NearestPlace(500, -1000), "the wilds")
end)

test("royale map: the way to the next circle runs from the player to its nearest point; none inside it",
function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    fight(M)
    M.Advance(0.1)
    local MP = ns.RoyaleMap
    MP.Open(false)
    M.Advance(0.2)
    local map = ns.S.royaleMap
    local ax, ay = MP.ToMap(210, -20)
    local nx, ny = MP.ToMap(-60, -380)
    local nr = MP.Yards(300)
    local n = MP.pathCount
    H.ok(n > 0, "dots")
    local dx, dy = nx - ax, ny - ay
    local dist = math.sqrt(dx * dx + dy * dy)
    local function dotAt(i)
        local _, _, _, x, y = MP.path[i].dot:GetPoint(1)
        return x, -y
    end
    local x1, y1 = dotAt(1)
    near(math.sqrt((x1 - ax) ^ 2 + (y1 - ay) ^ 2), MP.PATH_STEP, 1e-6, "the first a step from the player")
    local xn, yn = dotAt(n)
    local toCentre = math.sqrt((xn - nx) ^ 2 + (yn - ny) ^ 2)
    H.ok(toCentre >= nr - 0.01 and toCentre <= nr + MP.PATH_STEP, "the last at the circle")
    for i = 1, n do
        local x, y = dotAt(i)
        local cross = (x - ax) * dy - (y - ay) * dx
        near(cross / dist, 0, 1e-6, "on the line")
    end
    H.ok(math.abs(n - math.floor((dist - nr) / MP.PATH_STEP)) <= 1, "every 10 units")
    -- inside the next circle: none
    fight(M, { [22] = -60, [23] = -380 })
    M.Advance(0.2)
    H.eq(MP.pathCount, 0)
    -- a long way never takes more than 60 dots
    H.eq(MP.DrawPath(0, 0, 900, 0, 10), MP.PATH_MAX)
    -- in the lobby: no way
    roys(M)
    M.Advance(0.2)
    H.eq(MP.pathCount, 0)
end)

for _, ui in ipairs({ 1, 0.64 }) do
    test("royale map: the storm's shade and its hole meet exactly on whole pixels (1080p, UI scale " .. ui .. ")",
    function(M, ns)
        M.SetScreen(1920, 1080, ui)
        connect(M)
        H.send(M, "ROYM", MAP)
        roys(M)
        M.Advance(0.2)
        local MP, RS = ns.RoyaleMap, ns.RoyaleStyle
        H.ok(M.env.BleakholdRoyaleMapFrame:IsShown())
        local s = RS.PxPerUnit(MP.canvas)
        MP.DrawStorm(201.37, 263.91, 97.123)
        local sh = MP.shade
        local function edges(t)
            local p1, _, _, l, t1 = t:GetPoint(1)
            local p2, _, _, r, b = t:GetPoint(2)
            H.eq(p1, "TOPLEFT"); H.eq(p2, "BOTTOMRIGHT")
            return l, -t1, r, -b
        end
        local tl, tt, tr, tb = edges(sh.top)
        local bl, bt, br, bb = edges(sh.bottom)
        local ll, lt, lr, lb = edges(sh.left)
        local rl, rt, rr, rb = edges(sh.right)
        local hl, ht, hr, hb = edges(sh.hole)
        H.ok(tb == lt and lt == rt and rt == ht, "the top edge is one number")
        H.ok(bt == lb and lb == rb and rb == hb, "the bottom edge is one number")
        H.ok(lr == hl and hr == rl, "the sides are one number each")
        for _, v in ipairs({ ht, hb, hl, hr }) do
            near(v * s, math.floor(v * s + 0.5), 1e-6, "on a whole pixel")
        end
        H.ok(math.abs((hr - hl) - 2 * 97.123) <= 1 / s + 1e-9, "the hole is the circle's size")
        H.ok(sh.hole:GetTexture(), "the hole art")
        -- the hatch covers the shade and continues across the pieces (texcoords from canvas units)
        for _, t in ipairs(MP.hatch.rects) do
            if t:IsShown() then
                local l, top = edges(t)
                local u0, v0 = t:GetTexCoord()
                near(u0, l * s / MP.HATCH_TEXELS, 1e-9); near(v0, top * s / MP.HATCH_TEXELS, 1e-9)
            end
        end
        -- no hatch strip reaches into the circle
        local cx, cy, rx, ry = (hl + hr) / 2, (ht + hb) / 2, (hr - hl) / 2, (hb - ht) / 2
        for _, t in ipairs(MP.hatch.strips) do
            if t:IsShown() then
                local l, top, rgt, bot = edges(t)
                local y = math.max(top, math.min(cy, bot))
                local k = (y - cy) / ry
                local w = rx * math.sqrt(math.max(0, 1 - k * k))
                H.ok(rgt <= cx - w + 1e-6 or l >= cx + w - 1e-6, "a strip inside the circle")
            end
        end
    end)
end

test("royale map: the next circle's dashes turn only while the storm moves", function(M, ns)
    connect(M)
    H.send(M, "ROYM", MAP)
    fight(M, { [18] = 0, [19] = 30000 })
    local MP = ns.RoyaleMap
    MP.Open(false)
    M.Advance(0.2)
    local g = MP.rings.nextc.main
    local playing = false
    for _, a in ipairs(M.animations) do
        if a.__owner == g and a:IsPlaying() then playing = true end
    end
    H.ok(playing, "turning during the shrink")
    fight(M, { [18] = 20000, [19] = 60000 })
    M.Advance(0.2)
    playing = false
    for _, a in ipairs(M.animations) do
        if a.__owner == g and a:IsPlaying() then playing = true end
    end
    H.ok(not playing, "still while the storm holds")
end)

------------------------------------------------------------------------------------------------------
-- Sizes
------------------------------------------------------------------------------------------------------
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
    test(("royale map: no art minified past 2.2x at %dx%d, docked and in the fight"):format(screen[1], screen[2]),
    function(M, ns)
        M.SetScreen(screen[1], screen[2], 1)
        connect(M)
        H.send(M, "ROYM", demoMap())
        local RS, MP = ns.RoyaleStyle, ns.RoyaleMap
        local slices = ns.RoyaleArt.slices
        local worst, what, measured = 0, "", 0
        local function measure()
            for _, o in ipairs(M.objects) do
                if o.__otype == "Texture" and type(o.rsPath) == "string" and o.rsPath:find(ROYALE_ART, 1, true) == 1
                    and o:IsVisible() and o:GetHeight() > 0 and not slices[o.rsArt or ""]
                    and RS.RootOf(o) == MP.frame then
                    local w, h = fileDims(o.rsPath)
                    local ulx, uly, llx, lly = o:GetTexCoord()
                    local texels = math.sqrt(((llx - ulx) * w) ^ 2 + ((lly - uly) * h) ^ 2)
                    local ratio = texels / (o:GetHeight() * RS.PxPerUnit(o))
                    measured = measured + 1
                    if ratio > worst then worst, what = ratio, (o.rsArt or o.rsPath) .. " " .. o:GetHeight() end
                end
            end
        end
        roys(M, { [9] = -45, [10] = -170 })
        M.Advance(0.3)
        measure()
        fight(M)
        H.send(M, "ROYO", { { 7001, 1 }, { 3, "B", 1, -15, -150, 1, "" }, { 20, "D", 0, -67, -267, 3, 20000 } })
        MP.Open(false)
        for _ = 1, 12 do
            M.Advance(0.1)
            measure()
        end
        -- the late storm: small circles; and the last seconds of overtime, a circle smaller than any art
        fight(M, { [14] = 40, [17] = 20, [22] = -150, [23] = -310 })
        M.Advance(0.2)
        measure()
        fight(M, { [2] = 4, [14] = 30, [17] = 6, [22] = -150, [23] = -310 })
        M.Advance(0.2)
        measure()
        H.ok(measured > 20, "art was measured")
        H.ok(worst <= 2.2, ("texel ratio %.2f (%s)"):format(worst, what))
    end)
end
