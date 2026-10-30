-- Bleakhold inside AddicatUI (Integration.lua), against a stand-in for AddicatUI's two entry points: the micro
-- menu launcher and the editor mode's external frames. AddicatUI itself is not loaded here; the stand-in only
-- records what Bleakhold hands over, and the tests drive those callbacks the way AddicatUI's editor does.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

-- AddicatUI's public surface as Bleakhold sees it (modules/micromenu.lua, modules/editor_mode.lua).
local function fakeAddicatUI(M)
    local aui = { launchers = {}, movers = {}, order = {} }
    function aui.RegisterMicroMenuLauncher(spec)
        aui.launchers[#aui.launchers + 1] = spec
        return true
    end
    aui.EditorMode = {}
    function aui.EditorMode:RegisterExternalFrame(spec)
        assert(self == aui.EditorMode, "called as a method")
        assert(type(spec.name) == "string" and type(spec.move) == "function", "name and move")
        assert(type(spec.frame) == "table" and type(spec.frame.GetLeft) == "function", "a frame to outline")
        assert(not aui.movers[spec.name], "unique name " .. spec.name)
        aui.movers[spec.name] = spec
        aui.order[#aui.order + 1] = spec.name
        return true
    end
    M.env.AddicatUI = aui
    return aui
end

-- AddicatUI's quest tracker anchor, where its module puts it (top right, under the minimap).
local function questTracker(M, cx)
    local q = M.New("Frame", "AddicatUI_QuestTrackerFrame", M.env.UIParent)
    q:SetSize(250, 300)
    q.__cx, q.__cy = cx or 880, 450
    return q
end

-- The editor's outline: a UIParent child with a rect of its own.
local function outline(M, cx, cy, w, h)
    local o = M.New("Frame", nil, M.env.UIParent)
    o:SetSize(w or 250, h or 200)
    o.__cx, o.__cy = cx, cy
    return o
end

local function withAddicatUI(extra)
    return { before = function(M)
        fakeAddicatUI(M)
        if extra then extra(M) end
    end }
end

------------------------------------------------------------------------------------------------------
-- Alone and load order
------------------------------------------------------------------------------------------------------
test("integration: without AddicatUI nothing is registered and nothing breaks", function(M, ns)
    H.ok(not ns.Integration.launcher and not ns.Integration.movers, "no registration")
    M.FireEvent("ADDON_LOADED", "AddicatUI")
    H.ok(not ns.Integration.launcher, "an ADDON_LOADED without the addon's table registers nothing")
    FX.connect(M, H)
    FX.openEverything(M, ns)
end)

test("integration: AddicatUI loaded first registers at load, once", function(M, ns)
    local aui = M.env.AddicatUI
    H.eq(#aui.launchers, 1, "one launcher")
    H.eq(#aui.order, #ns.Movers, "every mover")
    M.FireEvent("ADDON_LOADED", "AddicatUI")
    H.eq(#aui.launchers, 1, "not registered twice")
end, withAddicatUI())

test("integration: AddicatUI loaded after Bleakhold registers on its ADDON_LOADED", function(M, ns)
    local aui = fakeAddicatUI(M)
    H.eq(#aui.launchers, 0)
    M.FireEvent("ADDON_LOADED", "AddicatUI")
    H.eq(#aui.launchers, 1)
    H.ok(aui.movers.bleakhold_keytracker and aui.movers.bleakhold_orb_activities, "movers")
end)

test("integration: an AddicatUI without these entry points (older build, DragonUI) is left alone", function(M, ns)
    M.env.AddicatUI = { EditorMode = {} }
    M.FireEvent("ADDON_LOADED", "AddicatUI")
    H.ok(not ns.Integration.launcher and not ns.Integration.movers)
end)

------------------------------------------------------------------------------------------------------
-- Micro menu launcher
------------------------------------------------------------------------------------------------------
test("launcher: every window with its key binding, a tooltip line and Bleakhold's own glyph art", function(M, ns)
    local spec = M.env.AddicatUI.launchers[1]
    H.eq(spec.id, "bleakhold")
    H.eq(spec.title, "Bleakhold")
    H.ok(spec.description ~= "", "button tooltip line")
    local bindings = assert(host_readfile(addonDir .. "/Bindings.xml"))
    local function checkIcon(icon, what)
        local art = "Interface\\AddOns\\Bleakhold\\Art\\"
        H.ok(icon.file == art .. "Glyphs" or icon.file == art .. "Emotes", what .. ": a Bleakhold atlas, no new art")
        local c = icon.coords
        H.eq(#c, 4, what .. ": four texcoords")
        H.ok(c[1] >= 0 and c[2] <= 1 and c[1] < c[2] and c[3] >= 0 and c[4] <= 1 and c[3] < c[4], what .. ": one cell")
        H.ok(math.abs((c[2] - c[1]) - 1 / 8) < 1e-9 and math.abs((c[4] - c[3]) - 1 / 4) < 1e-9,
            what .. ": an 8 x 4 cell")
        H.eq(#icon.color, 3, what .. ": gold tint")
    end
    checkIcon(spec.icon, "button")
    local keys = {}
    for _, e in ipairs(spec.entries) do
        keys[#keys + 1] = e.key
        H.ok(bindings:find('name="' .. e.binding .. '"', 1, true), e.key .. ": binding in Bindings.xml")
        H.ok(type(M.env["BINDING_NAME_" .. e.binding]) == "string", e.key .. ": binding label")
        local text = type(e.description) == "function" and e.description() or e.description
        H.ok(e.title ~= "" and type(text) == "string" and text ~= "", e.key .. ": title and tooltip line")
        H.ok(type(e.open) == "function", e.key .. ": opens")
        if e.key ~= "camp" then
            H.ok(ns.UI.openers[e.key], e.key .. ": an opener")
        end
        H.ok(e.shown == nil or type(e.shown) == "function", e.key .. ": shown is a predicate")
        checkIcon(e.icon, e.key)
    end
    H.eq(table.concat(keys, ","), "activities,collections,animations,season,leaderboards,graphics,camp")
end, withAddicatUI())

------------------------------------------------------------------------------------------------------
-- Make camp: the minimap orbs are off with AddicatUI, so its launcher and a key binding make camp
------------------------------------------------------------------------------------------------------
local CAMPING = { [6] = 512 }

local function campEntry(M)
    for _, e in ipairs(M.env.AddicatUI.launchers[1].entries) do
        if e.key == "camp" then return e end
    end
end

local function campIntents(M)
    local n = 0
    for _, it in ipairs(H.intents(M)) do
        if it.op == "CAMP" and it.fields[1] == "M" then n = n + 1 end
    end
    return n
end

test("launcher: Make camp, listed while the realm has camping on, makes camp with the orbs off", function(M, ns)
    local e = campEntry(M)
    H.ok(not M.env.BleakholdOrbHolder:IsShown(), "the orbs are off with AddicatUI")
    H.ok(e, "a Make camp entry")
    H.eq(e.title, "Make camp")
    H.eq(e.binding, "BLEAKHOLD_MAKECAMP")
    H.ok(not e.shown(), "not listed before the server says camping is on")
    FX.connect(M, H)
    H.ok(not e.shown(), "not listed on a realm with camping off")
    FX.connect(M, H, CAMPING)
    H.ok(e.shown(), "listed with camping on")
    H.ok(not e.isOpen(), "an action, never open")
    e.open()
    M.Advance(0.3)
    H.eq(campIntents(M), 1, "the entry sends CAMP M, as the orb does")
end, withAddicatUI())

test("launcher: Make camp's tooltip line tells the cooldown the orb showed", function(M, ns)
    FX.connect(M, H, CAMPING)
    local e = campEntry(M)
    H.ok(not e.description():find("again in", 1, true), "no cooldown: no countdown")
    H.send(M, "CAMPST", { { "N", 0, 0, 0, 1800, 0, 0, {}, {}, "", 0, 0 } })   -- made camp: 30 min cooldown
    H.contains(e.description(), "You can make camp again in", "the cooldown")
    local sent = campIntents(M)
    e.open()
    M.Advance(0.3)
    H.eq(campIntents(M), sent, "on cooldown: refused locally, as the orb is")
    M.Advance(1801)
    H.ok(not e.description():find("again in", 1, true), "the cooldown ran out")
end, withAddicatUI())

test("Make camp key binding: Bindings.xml runs BleakholdMakeCamp, labelled for Key Bindings", function(M, ns)
    local bindings = assert(host_readfile(addonDir .. "/Bindings.xml"))
    H.ok(bindings:find('name="BLEAKHOLD_MAKECAMP"', 1, true), "the binding")
    H.ok(bindings:find("BleakholdMakeCamp()", 1, true), "runs BleakholdMakeCamp")
    H.eq(M.env.BINDING_NAME_BLEAKHOLD_MAKECAMP, "Make camp")
    FX.connect(M, H, CAMPING)
    M.env.BleakholdMakeCamp()
    M.Advance(0.3)
    H.eq(campIntents(M), 1, "the key makes camp")
end)

test("launcher: an entry toggles its window and reports it open", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    local byKey = {}
    for _, e in ipairs(M.env.AddicatUI.launchers[1].entries) do byKey[e.key] = e end
    for _, key in ipairs({ "activities", "season", "leaderboards", "graphics" }) do
        local e = byKey[key]
        H.ok(not e.isOpen(), key .. " starts closed")
        e.open()
        H.ok(e.isOpen(), key .. " open")
        e.open()
        H.ok(not e.isOpen(), key .. " toggled shut")
    end
    -- Animations is a tab of the Collections window: only one of the two reads as open.
    byKey.collections.open()
    H.ok(byKey.collections.isOpen() and not byKey.animations.isOpen(), "collections tab")
    byKey.animations.open()
    H.ok(M.env.BleakholdCollectionsFrame:IsShown(), "same window")
    H.ok(byKey.animations.isOpen() and not byKey.collections.isOpen(), "animations tab")
    byKey.animations.open()
    H.ok(not M.env.BleakholdCollectionsFrame:IsShown(), "toggled shut")
end, withAddicatUI())

------------------------------------------------------------------------------------------------------
-- Editor mode: key tracker
------------------------------------------------------------------------------------------------------
test("editor: the key tracker shows a sample run while idle; a real run takes over; closing hides it", function(M, ns)
    local mover = M.env.AddicatUI.movers.bleakhold_keytracker
    local t = M.env.BleakholdKeyTracker
    H.eq(mover.frame, t)
    H.ok(mover.visible(), "always in the editor")
    H.ok(not t:IsShown())
    mover.begin()
    H.ok(t:IsShown(), "sample shown")
    H.eq(t.title:GetText(), "Mythic+ Key Tracker")
    H.eq(t.bosses[1].name:GetText(), "First boss")
    H.eq(t.timer:GetText(), "12:34")
    M.Advance(2)
    H.eq(t.timer:GetText(), "12:34", "the sample's clock stands still")
    H.eq(ns.S.mplus, nil, "no fake run in the state")
    FX.connect(M, H)
    H.send(M, "MPS", FX.examples(M).MPS)
    H.eq(t.title:GetText(), "Halls of Lightning", "the real run replaces the sample")
    H.eq(t.titleLevel:GetText(), "+8")
    mover.finish()
    H.ok(t:IsShown(), "a real run stays up")
    H.send(M, "MP", { { 7001, 1122000, 1800, 2, 10, 64, 100, 1, { 300 }, { 1260, 1440 }, 4 } })
    H.ok(not t:IsShown(), "abandoned: gone, no sample left behind")
    mover.begin()
    H.eq(t.title:GetText(), "Mythic+ Key Tracker", "sample again while the editor is open")
    mover.finish()
    H.ok(not t:IsShown())
end, withAddicatUI())

test("editor: a drop saves Bleakhold's own position; reset puts it back beside the quest tracker", function(M, ns)
    local mover = M.env.AddicatUI.movers.bleakhold_keytracker
    local t = M.env.BleakholdKeyTracker
    mover.begin()
    local _, rel = t:GetPoint(1)
    H.eq(rel, M.env.AddicatUI_QuestTrackerFrame, "default: beside the quest tracker")
    H.ok(mover.isDefault())
    -- dragging: the tracker follows, nothing is stored yet
    mover.move(outline(M, 880, 500), false)
    local point, relTo, relPoint, x, y = t:GetPoint(1)
    H.eq(point, "TOPRIGHT")
    H.eq(relTo, M.env.UIParent)
    H.eq(relPoint, "TOPRIGHT")
    H.eq(x, -19)
    H.eq(y, -168)
    H.eq(M.env.BleakholdCharDB.windows.BleakholdKeyTracker, nil, "not saved while dragging")
    H.ok(mover.isDefault())
    -- dropped in the left third: anchored to the left edge
    mover.move(outline(M, 200, 400), true)
    local pos = M.env.BleakholdCharDB.windows.BleakholdKeyTracker
    H.eq(pos.point, "TOPLEFT")
    H.eq(pos.relPoint, "TOPLEFT")
    H.eq(pos.x, 75)
    H.eq(pos.y, -268)
    H.ok(not mover.isDefault())
    mover.finish()
    -- the same spot as Bleakhold's own restore uses (the format its drag saves)
    mover.begin()
    point, relTo, relPoint, x, y = t:GetPoint(1)
    H.eq(point .. relPoint .. x .. y, "TOPLEFTTOPLEFT75-268")
    mover.reset()
    H.eq(M.env.BleakholdCharDB.windows.BleakholdKeyTracker, nil, "forgotten")
    _, rel = t:GetPoint(1)
    H.eq(rel, M.env.AddicatUI_QuestTrackerFrame, "back beside the quest tracker")
    H.ok(mover.isDefault())
    mover.finish()
end, withAddicatUI(function(M) questTracker(M) end))

test("editor: a saved spot from before (Bleakhold's own drag) is the starting point", function(M, ns)
    local t = M.env.BleakholdKeyTracker
    local mover = M.env.AddicatUI.movers.bleakhold_keytracker
    H.ok(not mover.isDefault(), "existing installs keep their spot")
    mover.begin()
    local point, relTo, relPoint, x, y = t:GetPoint(1)
    H.eq(point, "CENTER")
    H.eq(relTo, M.env.UIParent)
    H.eq(x, 40)
    H.eq(y, -20)
    mover.finish()
end, withAddicatUI(function(M)
    local spot = { point = "CENTER", relPoint = "CENTER", x = 40, y = -20 }
    M.env.BleakholdCharDB = { windows = { BleakholdKeyTracker = spot } }
end))

test("tracker: AddicatUI's quest tracker on the left half puts the key tracker on its right", function(M, ns)
    FX.connect(M, H)
    H.send(M, "MPS", FX.examples(M).MPS)
    local point, rel, relPoint, x = M.env.BleakholdKeyTracker:GetPoint(1)
    H.eq(rel, M.env.AddicatUI_QuestTrackerFrame)
    H.eq(point, "TOPLEFT")
    H.eq(relPoint, "TOPRIGHT")
    H.eq(x, 12)
end, { before = function(M) questTracker(M, 150) end })

------------------------------------------------------------------------------------------------------
-- Minimap orbs: off by default with AddicatUI (its launcher lists the windows), the player's choice wins
------------------------------------------------------------------------------------------------------
test("orbs: on by default without AddicatUI, the only launcher there is", function(M, ns)
    H.ok(M.env.BleakholdOrbHolder:IsShown(), "shown")
    H.eq(M.env.BleakholdCharDB.orbsHidden, nil, "no choice saved")
    M.env.SlashCmdList.BLEAKHOLD("orbs off")
    H.ok(not M.env.BleakholdOrbHolder:IsShown(), "off")
    H.eq(M.env.BleakholdCharDB.orbsHidden, true, "the choice is saved")
    M.env.SlashCmdList.BLEAKHOLD("orbs on")
    H.ok(M.env.BleakholdOrbHolder:IsShown())
    H.eq(M.env.BleakholdCharDB.orbsHidden, false)
end)

test("orbs: off by default with AddicatUI; /bh orbs on and reset bring them back", function(M, ns)
    H.ok(not M.env.BleakholdOrbHolder:IsShown(), "AddicatUI's micro menu lists the windows: no orbs")
    H.eq(M.env.BleakholdCharDB.orbsHidden, nil, "a default, not a saved choice")
    H.eq(#M.env.AddicatUI.launchers, 1, "the launcher is there instead")
    M.FireEvent("PLAYER_ENTERING_WORLD")
    H.ok(not M.env.BleakholdOrbHolder:IsShown(), "still off after entering the world")
    M.env.SlashCmdList.BLEAKHOLD("orbs on")
    H.ok(M.env.BleakholdOrbHolder:IsShown(), "on when asked")
    M.env.SlashCmdList.BLEAKHOLD("orbs off")
    H.ok(not M.env.BleakholdOrbHolder:IsShown())
    M.env.SlashCmdList.BLEAKHOLD("orbs reset")
    H.ok(M.env.BleakholdOrbHolder:IsShown(), "reset shows them at their first places")
    H.eq(M.env.BleakholdCharDB.orbsHidden, false)
end, withAddicatUI())

test("orbs: a player who turned them on keeps them with AddicatUI", function(M, ns)
    H.ok(M.env.BleakholdOrbHolder:IsShown(), "the saved choice wins over the default")
    M.FireEvent("ADDON_LOADED", "AddicatUI")
    H.ok(M.env.BleakholdOrbHolder:IsShown(), "and keeps winning")
end, withAddicatUI(function(M) M.env.BleakholdCharDB = { orbsHidden = false } end))

test("orbs: a player who turned them off keeps them off without AddicatUI", function(M, ns)
    H.ok(not M.env.BleakholdOrbHolder:IsShown())
end, { before = function(M) M.env.BleakholdCharDB = { orbsHidden = true } end })

test("orbs: AddicatUI without the launcher in its strip leaves them on", function(M, ns)
    H.ok(M.env.BleakholdOrbHolder:IsShown(), "micro menu module off: the orbs are the launcher")
    M.env.AddicatUI.MicroMenuLauncherAvailable = function() error("broken") end
    M.allowErrors = true
    M.FireEvent("ADDON_LOADED", "AddicatUI")
    H.ok(not M.env.BleakholdOrbHolder:IsShown(), "a failing query counts as AddicatUI being there")
end, withAddicatUI(function(M) M.env.AddicatUI.MicroMenuLauncherAvailable = function() return false end end))

test("orbs: AddicatUI loaded after Bleakhold turns the default off", function(M, ns)
    H.ok(M.env.BleakholdOrbHolder:IsShown(), "on while AddicatUI is not there")
    fakeAddicatUI(M)
    M.FireEvent("ADDON_LOADED", "AddicatUI")
    H.ok(not M.env.BleakholdOrbHolder:IsShown(), "off once its launcher lists the windows")
end)

------------------------------------------------------------------------------------------------------
-- Editor mode: minimap orbs
------------------------------------------------------------------------------------------------------
test("editor: an orb follows its outline around the minimap ring and saves the angle", function(M, ns)
    local aui = M.env.AddicatUI
    -- with AddicatUI the orbs start off (its launcher lists the windows), and so does their outline
    H.ok(not M.env.BleakholdOrbHolder:IsShown(), "orbs off by default with AddicatUI")
    H.ok(not aui.movers.bleakhold_orb_season.visible(), "hidden orbs are not in the editor")
    M.env.SlashCmdList.BLEAKHOLD("orbs on")
    M.Advance(1.1)
    for _, o in ipairs(ns.Orbs.list) do
        local mover = aui.movers["bleakhold_orb_" .. o.key]
        H.ok(mover, o.key .. " mover")
        H.eq(mover.frame, o.button)
        H.eq(mover.title, o.title .. " orb")
        H.ok(mover.isDefault())
    end
    local mover = aui.movers.bleakhold_orb_season
    mover.begin()
    -- Minimap centre is (940, 680) in the mock: straight left of it is 180 degrees
    mover.move(outline(M, 800, 680, 34, 34), false)
    H.eq(M.env.BleakholdCharDB.orbs.season, 180)
    mover.move(outline(M, 940, 600, 34, 34), true)
    H.eq(M.env.BleakholdCharDB.orbs.season, 270, "below the map")
    local _, _, _, x, y = M.env.BleakholdOrb_season:GetPoint(1)
    H.ok(math.abs(x) < 0.01 and y < 0, "the orb sits under the map")
    H.ok(not mover.isDefault())
    mover.reset()
    H.eq(M.env.BleakholdCharDB.orbs.season, nil)
    H.ok(mover.isDefault())
    mover.finish()
    -- orbs switched off are left out of the editor
    H.ok(mover.visible())
    M.env.SlashCmdList.BLEAKHOLD("orbs off")
    H.ok(not mover.visible(), "hidden orbs are not in the editor")
end, withAddicatUI())

test("editor: a mover that fails is reported by Bleakhold and returns nothing, AddicatUI goes on", function(M, ns)
    M.allowErrors = true
    local mover = M.env.AddicatUI.movers.bleakhold_keytracker
    local saved = ns.KeyTracker.MoveTo
    ns.KeyTracker.MoveTo = function() error("broken") end
    local before = ns.errors
    H.eq(mover.move(outline(M, 500, 400), true), nil)
    H.eq(ns.errors, before + 1, "counted and reported")
    ns.KeyTracker.MoveTo = saved
end, withAddicatUI())
