-- The Bleakhold UI micro menu dock folded into AddicatUI (UI by Addicated): modules/micromenu.lua's "dock" layout
-- (two even rows beside the gryphon, the bag bar on top in one tooltip-border box, the backpack and bags larger),
-- its edit-mode mover, /bhui dock, the Dungeon Finder button opening Activities, and bag windows opening above the
-- dock (modules/bags_skin.lua). AddicatUI is not loaded as a whole: the real files run against a stand-in for the
-- parts of AddicatUI they reach and stand-ins for FrameXML's micro buttons, backpack, bag slots and gryphon, without
-- AddicatUI_Art.
local AUI = repo .. "/Interface/AddOns/AddicatUI/"

local function run(M, a, rel)
    local chunk = assert(host_loadfile(AUI .. rel))
    setfenv(chunk, M.env)
    chunk("AddicatUI", a)
end

local function read(rel)
    return assert(host_readfile(repo .. "/Interface/AddOns/" .. rel), "missing " .. rel)
end

local function near(a, b, msg)
    if type(a) ~= "number" or math.abs(a - b) > 1e-6 then
        error((msg or "values differ") .. ": expected " .. tostring(b) .. ", got " .. tostring(a), 2)
    end
end

local function said(M, from)
    local out = {}
    for i = from + 1, #M.chat do out[#out + 1] = M.chat[i].msg end
    return out
end

-- FrameXML's micro buttons in AddicatUI's order (micromenu.lua MICRO_BUTTONS; the launcher sits before MainMenu)
local STEMS = { "Character", "Profession", "Spellbook", "Talent", "Achievement", "QuestLog", "Socials", "LFD",
    "Collections", "PVP", "MainMenu", "Help" }

local function singlePoint(self, ...)
    self:ClearAllPoints()
    self:SetPoint(...)
end

-- What micromenu.lua and bags_skin.lua reach on AddicatUI's addon table. The mock lays nothing out, so the dock's
-- mover reports the corner its BOTTOMRIGHT anchor pins (a.dockCorner, UIParent units) and its height above it.
local function fakeAddicatUI(M, profile)
    local env = M.env
    local a = {
        L = setmetatable({}, { __index = function(_, k) return k end }),
        config = {},
        _dir = "Interface\\AddOns\\AddicatUI_Art\\Textures\\",
        db = { profile = profile, global = {} },
        registered = {},
        EditableFrames = {},
        timers = {},
        dockCorner = { 1020, 4 },
        NewItems = { AttachContainers = function() end, UpdateContainer = function() end },
    }
    a._noop = function() end
    function a:RegisterModule(name, module) self.registered[name] = module return true end
    function a:GetModuleConfig(name) return self.db.profile.modules and self.db.profile.modules[name] end
    function a:IsModuleEnabled(name)
        local cfg = self:GetModuleConfig(name)
        return cfg and cfg.enabled or false
    end
    function a:RegisterEditableFrame(info) self.EditableFrames[info.name] = info end
    function a:GetEditableFrameInfo(name) return self.EditableFrames[name] end
    function a:After(delay, fn) self.timers[#self.timers + 1] = { delay, fn } end
    a.SetEditorBoxScale = function() end
    a.package = { Subscribe = function() end }
    a.core = { ScheduleTimer = function() end }
    a.CreateUIFrame = function(w, h, name)
        local f = env.CreateFrame("Frame", "AddicatUI_" .. name, env.UIParent)
        f:SetSize(w, h)
        f.GetRight = function() return a.dockCorner[1] end
        f.GetBottom = function() return a.dockCorner[2] end
        f.GetTop = function(self) return a.dockCorner[2] + self:GetHeight() end
        return f
    end
    return a
end

local function profileFor(opts)
    return {
        micromenu = {
            layout = opts.layout or "dock", grayscale_icons = false, spacing_is_padding = true, show_launcher = true,
            hide_on_vehicle = false, bags_collapsed = false,
            normal = { scale_menu = 1.0, icon_spacing = -6, columns = opts.columns or 12, x_position = -113,
                y_position = -53 },
            grayscale = { scale_menu = 1.5, icon_spacing = 1, columns = 12 },
        },
        bags = { scale = 1.02, x_position = 1, y_position = 41 },
        widgets = {
            microdock = { anchor = "BOTTOMRIGHT", posX = -4, posY = 4 },
            micromenu = { anchor = "BOTTOMRIGHT", posX = -3, posY = 3 },
            bagsbar = { anchor = "BOTTOMRIGHT", posX = -5, posY = 40 },
        },
        modules = { micromenu = { enabled = true }, bags_skin = { enabled = true } },
        talents = {},
    }
end

-- The game around the micro menu as AddicatUI leaves it: the 12 stock buttons and Bleakhold's launcher on
-- AddicatUI_MicroButtonBar (scale 1.0, the default), the 50 px backpack on UIParent, the 28 px bag slots on the bag
-- bar, and the action bar's right gryphon ending at x = capRight.
local function dockGame(M, opts)
    opts = opts or {}
    local env = M.env
    env.RegisterStateDriver = function() end
    env.UnregisterStateDriver = function() end
    local art = env.CreateFrame("Frame", "MainMenuBarArtFrame", env.UIParent)
    local cap = art:CreateTexture("MainMenuBarRightEndCap", "OVERLAY")
    cap:SetSize(128, 128)
    cap.__cx = (opts.capRight or 700) - 64
    local menu = env.CreateFrame("Frame", "AddicatUI_MicroButtonBar", env.UIParent)
    menu:SetScale(1.0)
    for _, stem in ipairs(STEMS) do
        local b = env.CreateFrame("Button", stem .. "MicroButton", menu)
        b:SetSize(32, 40)
        if b:GetPushedTextOffset() == nil then         -- an older UiLint mock without it: the stock 0, 0
            b.GetPushedTextOffset = function() return 0, 0 end
        end
    end
    env.LFDMicroButton:SetScript("OnClick", function() env.ToggleLFDParentFrame() end)   -- MainMenuBarMicroButtons.xml
    env.CreateFrame("CheckButton", "MainMenuBarBackpackButton", env.UIParent):SetSize(50, 50)
    local bagBar = env.CreateFrame("Frame", "AddicatUI_BagButtonBar", env.UIParent)
    bagBar:SetScale(1.02)
    for i = 0, 3 do
        local slot = env.CreateFrame("CheckButton", "CharacterBag" .. i .. "Slot", bagBar)
        slot:SetSize(28, 28)
        slot.SetSinglePoint = singlePoint
    end
    env.CreateFrame("CheckButton", "KeyRingButton", env.CharacterBag3Slot).SetSinglePoint = singlePoint

    local a = fakeAddicatUI(M, profileFor(opts))
    run(M, a, "core/commands.lua")
    run(M, a, "modules/micromenu.lua")
    if opts.launcher ~= false then
        -- Bleakhold's launcher in the strip (layoutMicroButtons parents and shows it)
        a.RegisterMicroMenuLauncher({ id = "bleakhold", entries = {} })
        env.AddicatUI_LauncherMicroButton:SetParent(menu)
        env.AddicatUI_LauncherMicroButton:Show()
    end
    return a, a.registered.micromenu
end

local function order(M)
    local list = {}
    for _, stem in ipairs(STEMS) do
        if stem == "MainMenu" then list[#list + 1] = M.env.AddicatUI_LauncherMicroButton end
        list[#list + 1] = M.env[stem .. "MicroButton"]
    end
    return list
end

------------------------------------------------------------------------------------------------------
-- The layout
------------------------------------------------------------------------------------------------------
test("aui dock: 13 buttons in two even rows beside the gryphon, right aligned, in one tooltip-border box", function(M)
    local a = dockGame(M)
    a.RefreshMicromenu()
    local D = H.ok(a.MicroDock, "addon.MicroDock")
    H.eq(D.columns, 7, "314 free right of the gryphon at 34 a button: 8 fit, so 13 go 7 + 6")
    H.eq(D.rows, 2)

    local s = 1.0                                   -- the buttons' scale (the micro menu bar's)
    local stepX, stepY = 34 * s, 42 * s
    local gridW, gridH = 7 * stepX - 2 * s, 2 * stepY - 2 * s
    local bagW = 50 * 1.02 * 1.10 + 4 * (28 * 1.02 * 1.12 + 4) + 40
    local width, height = bagW + 14, gridH + 14 + 50 * 1.02 * 1.10 + 7
    local mover, box = M.env.AddicatUI_MicroDock, M.env.AddicatUI_MicroDockFrame
    near(mover:GetWidth(), width, "the bag row is the wider: it sets the box's width")
    near(mover:GetHeight(), height)
    local p, rel, rp, x, y = mover:GetPoint(1)
    H.ok(p == "BOTTOMRIGHT" and rel == M.env.UIParent and rp == "BOTTOMRIGHT" and x == -4 and y == 4,
        "the mover at widgets.microdock, the bottom right corner")
    H.eq(box:GetParent(), M.env.AddicatUI_MicroButtonBar, "the box fades and hides with the micro menu")
    near(box:GetEffectiveScale(), 1, "drawn at UIParent's scale whatever the menu's")
    H.eq(box:GetPoint(1), "TOPLEFT")
    H.eq(select(2, box:GetPoint(1)), mover, "the box covers the mover")
    H.eq(box:GetFrameStrata(), "BACKGROUND")
    local bd = box.__backdrop
    H.ok(bd.bgFile == "Interface\\Tooltips\\UI-Tooltip-Background"
        and bd.edgeFile == "Interface\\Tooltips\\UI-Tooltip-Border" and bd.edgeSize == 14 and bd.insets.left == 3,
        "the tooltip backdrop")
    H.ok(box.__bdborder[1] == 0.55 and box.__bdborder[2] == 0.46 and box.__bdborder[3] == 0.26, "the gold edge")

    for i, button in ipairs(order(M)) do
        local r, c = math.floor((i - 1) / 7), (i - 1) % 7
        local inRow = r == 0 and 7 or 6
        local bp, brel, brp, bx, by = button:GetPoint(1)
        H.ok(bp == "BOTTOMLEFT" and brel == box and brp == "BOTTOMLEFT", tostring(button) .. " on the box")
        near(bx * s, width - 7 - (inRow - c) * stepX + 2 * s, tostring(button) .. " x")
        near(by * s, 7 + (1 - r) * stepY, tostring(button) .. " y: rows from the top")
        H.eq(button:GetNumPoints(), 1)
        H.eq(button.SetPoint, a._noop, "locked like the strip's (a vehicle cannot move it)")
    end
    -- the shorter row ends under the first row's right edge
    local _, _, _, lastX = M.env.HelpMicroButton:GetPoint(1)
    near(lastX * s + 32 * s, width - 7, "the bottom row is right aligned")
    near(M.env.CharacterMicroButton:GetEffectiveScale() * 32, 32, "full-size buttons by default (the old dock's)")

    local line = box.line
    H.ok(line:IsShown(), "the divider under the bag row")
    local lp, lrel, _, lx, ly = line:GetPoint(1)
    H.ok(lp == "BOTTOMLEFT" and lrel == box and lx == 7, "from the left padding")
    near(ly, 7 + gridH + 3, "just over the grid")

    local backpack = M.env.MainMenuBarBackpackButton
    near(backpack:GetScale(), 1.02 * 1.10, "the backpack 10 % over the bag scale")
    local bp, brel, brp, bx, by = backpack:GetPoint(1)
    H.ok(bp == "RIGHT" and brel == box and brp == "TOPRIGHT", "in the box's bag row")
    near(bx * backpack:GetScale(), -7, "PAD in from the right")
    near(by * backpack:GetScale(), -(4 + 27), "centred on the bag bar's height under the top")
end)

test("aui dock: a menu scale of the player's own sizes the dock's buttons; the box keeps UIParent's scale", function(M)
    local a = dockGame(M)
    a.db.profile.micromenu.normal.scale_menu = 0.9
    a.RefreshMicromenu()
    local D = a.MicroDock
    H.eq(D.columns, 7, "314 free at 30.6 a button: 9 fit, so 13 still go 7 + 6")
    near(M.env.CharacterMicroButton:GetEffectiveScale() * 32, 28.8, "0.9 of 32")
    local box = M.env.AddicatUI_MicroDockFrame
    near(box:GetEffectiveScale(), 1, "the box's border is the same at any menu scale")
    local gridH = 2 * 42 * 0.9 - 2 * 0.9
    near(M.env.AddicatUI_MicroDock:GetHeight(), gridH + 14 + 50 * 1.02 * 1.10 + 7, "the grid shrinks with them")
end)

test("aui dock: Columns caps it, a dock moved off the bar has the cap only, and a narrow screen keeps 3", function(M)
    local a = dockGame(M, { columns = 5 })
    a.RefreshMicromenu()
    local D = a.MicroDock
    H.eq(D.columns, 5, "Columns 5")
    H.eq(D.rows, 3)

    a.db.profile.micromenu.normal.columns = 12
    a.dockCorner = { 400, 4 }               -- left of the gryphon's right edge: no room limit
    a.RefreshMicromenu()
    H.eq(D.columns, 7, "12 at most, then even rows")
    H.eq(D.rows, 2)

    H.eq(D.Grid(13, 30.6, 1.8, 60, 12), 3, "never fewer than 3 columns")
    local cols, rows = D.Grid(13, 30.6, 1.8, 1000, 1)
    H.ok(cols == 1 and rows == 13, "Columns 1 is a column")
    H.eq(D.Grid(12, 30.6, 1.8, 1000, 13), 12, "a single row once Columns reaches the button count")
end)

test("aui dock: the gryphon is a texture, measured at its frame's scale; without it the last action button", function(M)
    local a = dockGame(M)
    local D = a.MicroDock
    M.env.MainMenuBarArtFrame:SetScale(0.5)
    near(D.BarRight(), 350, "a texture has no GetEffectiveScale in 3.3.5a: its frame's scale applies")
    M.env.MainMenuBarRightEndCap:Hide()
    local b = M.env.CreateFrame("CheckButton", "ActionButton12", M.env.UIParent)
    b:SetSize(36, 36)
    b.__cx = 600 - 18
    near(D.BarRight(), 608, "gryphons off: the last button and 8 of air")
end)

------------------------------------------------------------------------------------------------------
-- Switching, /bhui dock, bag scales
------------------------------------------------------------------------------------------------------
test("aui dock: /bhui dock switches at once between the dock and the strip, bags and their scales with it", function(M)
    local a, mm = dockGame(M)
    mm.applied = true
    a.RefreshMicromenu()
    local B = a.BleakholdCommands
    local box = M.env.AddicatUI_MicroDockFrame
    local slot = M.env.CharacterBag1Slot

    local n = #M.chat
    B.Run("dock")
    H.eq(a.db.profile.micromenu.layout, "strip", "toggled off")
    H.contains(said(M, n)[1], "bottom-right dock off")
    H.ok(not box:IsShown(), "no box")
    local p, rel, rp = M.env.CharacterMicroButton:GetPoint(1)
    H.ok(p == "BOTTOMLEFT" and rel == M.env.AddicatUI_MicroButtonBar and rp == "BOTTOMRIGHT", "back in the strip")
    near(M.env.MainMenuBarBackpackButton:GetScale(), 1.02, "the bag scale only")
    near(slot:GetScale(), 1.0)
    H.eq(M.env.MainMenuBarBackpackButton:GetPoint(1), "BOTTOMRIGHT", "the backpack at the bag bar's own place")

    n = #M.chat
    B.Run("dock on")
    H.eq(a.db.profile.micromenu.layout, "dock")
    H.contains(said(M, n)[1], "bottom-right dock on.")
    H.ok(box:IsShown())
    H.eq(select(2, M.env.CharacterMicroButton:GetPoint(1)), box, "in the dock again, no reload")
    near(M.env.MainMenuBarBackpackButton:GetScale(), 1.02 * 1.10)
    near(slot:GetScale(), 1.12, "the small bags 12 % over the bag bar's scale")
    near(slot:GetEffectiveScale(), 1.02 * 1.12)
    B.Run("dock on")
    H.eq(a.db.profile.micromenu.layout, "dock", "on stays on")

    B.Run("dock off")
    H.eq(a.db.profile.micromenu.layout, "strip")
    B.Run("")
    local help = table.concat(said(M, n), "\n")
    H.contains(help, "/bhui dock", "listed in the help")
end)

test("aui dock: the micro menu module off, or the old Bleakhold UI addon loaded, means no dock", function(M)
    local a = dockGame(M)
    local D = a.MicroDock
    H.ok(D.Active(), "on by default")
    M.addons.BleakholdUI = true
    H.ok(not D.Active(), "the old addon lays out its own dock over the same buttons")
    a.RefreshMicromenu()
    H.ok(not M.env.AddicatUI_MicroDockFrame, "nothing built")
    H.eq(select(2, M.env.CharacterMicroButton:GetPoint(1)), M.env.AddicatUI_MicroButtonBar, "the strip")
    M.addons.BleakholdUI = nil
    a.db.profile.modules.micromenu.enabled = false
    H.ok(not D.Active())
    H.eq(D.BackpackScale(1.02), 1.02, "no dock scales without the dock")
    H.eq(D.SlotScale(), 1.0)
end)

test("aui dock: laid out again after login (the action bar settles late) and when the screen changes", function(M)
    local a, mm = dockGame(M)
    mm.InstallDockEvents()
    mm.InstallDockEvents()
    local events = H.ok(a.MicroDock.events, "one event frame")
    events.__scripts.OnEvent(events, "PLAYER_ENTERING_WORLD")
    H.eq(#a.timers, 2)
    H.ok(a.timers[1][1] == 0.5 and a.timers[2][1] == 2.5, "half a second and two and a half after")
    events.__scripts.OnEvent(events, "DISPLAY_SIZE_CHANGED")
    H.eq(#a.timers, 3)
    H.eq(a.timers[3][1], 0.3)
    mm.applied = true
    a.timers[3][2]()
    H.ok(M.env.AddicatUI_MicroDockFrame and M.env.AddicatUI_MicroDockFrame:IsShown(), "the relayout builds the dock")
    a.db.profile.micromenu.layout = "strip"
    events.__scripts.OnEvent(events, "DISPLAY_SIZE_CHANGED")
    H.eq(#a.timers, 3, "nothing to do for the strip")
    a.db.profile.micromenu.layout = "dock"

    -- leaving a vehicle: the player's own only (the event fires for every group member), one relayout at a time
    for i = 1, 25 do events.__scripts.OnEvent(events, "UNIT_EXITED_VEHICLE", "raid" .. i) end
    events.__scripts.OnEvent(events, "UNIT_EXITED_VEHICLE", "party1")
    H.eq(#a.timers, 3, "the group's vehicles leave the dock alone")
    events.__scripts.OnEvent(events, "UNIT_EXITED_VEHICLE", "player")
    H.eq(#a.timers, 4, "the player's vehicle")
    H.eq(a.timers[4][1], 0.3)
    events.__scripts.OnEvent(events, "UNIT_EXITED_VEHICLE", "player")
    events.__scripts.OnEvent(events, "DISPLAY_SIZE_CHANGED")
    H.eq(#a.timers, 4, "collapsed into the one waiting")
    a.timers[4][2]()
    events.__scripts.OnEvent(events, "DISPLAY_SIZE_CHANGED")
    H.eq(#a.timers, 5, "a new one once it ran")
end)

------------------------------------------------------------------------------------------------------
-- Edit mode
------------------------------------------------------------------------------------------------------
test("aui dock: one mover in edit mode while it is on; the strip's and the bag bar's stand aside", function(M)
    local a = dockGame(M)
    a.RefreshMicromenu()
    local info = H.ok(a.EditableFrames.microdock, "registered with edit mode")
    H.eq(info.frame, M.env.AddicatUI_MicroDock)
    H.ok(info.configPath[1] == "widgets" and info.configPath[2] == "microdock", "saved at widgets.microdock")
    H.ok(info.editorVisible() == true, "shown in edit mode with the dock on")
    a.db.profile.micromenu.layout = "strip"
    H.ok(info.editorVisible() == false, "hidden with the strip")
    a.db.profile.micromenu.layout = "dock"

    -- a reset or a typed position re-places the mover from the profile and lays the dock out for the new room
    a.db.profile.widgets.microdock = { anchor = "BOTTOMRIGHT", posX = -40, posY = 10 }
    local mm = a.registered.micromenu
    mm.applied = true
    info.applyPosition()
    local _, _, _, x, y = M.env.AddicatUI_MicroDock:GetPoint(1)
    H.ok(x == -40 and y == 10, "moved")
    H.eq(M.env.AddicatUI_MicroDock:GetNumPoints(), 1)

    local src = read("AddicatUI/modules/micromenu.lua")
    for _, name in ipairs({ "micromenu", "bagsbar" }) do
        local reg = H.ok(src:match('name = "' .. name .. '",.-%}%)'), name .. " registration")
        H.ok(reg:find("editorVisible = function() return not Dock.Active() end", 1, true),
            name .. "'s mover stands aside in the dock")
        H.ok(reg:find("showTest = function()", 1, true), name .. "'s mover comes back with the strip")
    end
end)

test("aui dock: defaults (dock on, its corner, bags 2 % larger) and Columns reaching every button", function(M)
    local a = fakeAddicatUI(M, {})
    run(M, a, "database.lua")
    local d = a.defaults.profile
    H.eq(d.micromenu.layout, "dock", "the dock by default")
    local w = d.widgets.microdock
    H.ok(w.anchor == "BOTTOMRIGHT" and w.posX == -4 and w.posY == 4, "its corner (edit mode's reset)")
    H.eq(d.bags.scale, 1.02)
    H.eq(d.micromenu.normal.scale_menu, 1.0, "full-size buttons, as the old Bleakhold UI dock had them")

    -- 12 stock buttons and Bleakhold's launcher
    local game = dockGame(M)
    local seen = 0
    for _, b in ipairs(order(M)) do if b and not b.addicatUISuppressed then seen = seen + 1 end end
    H.eq(seen, 13)
    local editor = read("AddicatUI/core/editor_settings.lua")
    local max = tonumber(editor:match("local MICRO_COLUMNS_MAX = (%d+)"))
    H.ok(max and max >= 13, "the editor's Columns slider reaches 13")
    H.ok(editor:find('Slider(T("Columns"), "micromenu.columns", 1, MICRO_COLUMNS_MAX', 1, true), "and uses it")
    H.ok(editor:find('E.Register("microdock"', 1, true), "the dock's mover has the micro menu's settings")
    local options = read("AddicatUI_Options/panel/tab_micromenu.lua")
    local omax = tonumber(options:match('LO%["Columns"%].-max = (%d+)'))
    H.ok(omax and omax >= 13, "the options panel's Columns slider reaches 13")
    H.ok(options:find('"micromenu.layout"', 1, true), "the options panel switches the dock")
    H.ok(game.L, "game built")
end)

test("aui dock: the update keeps the strip for a player who placed it, the bag bar or its columns", function(M)
    local a = fakeAddicatUI(M, {})
    run(M, a, "database.lua")
    run(M, a, "core/api.lua")
    H.ok(a.DB_SCHEMA_VERSION >= 4, "a schema step for the dock")
    -- AceDB writes the defaults into the profile; ApplyMissingDefaults does the same for these plain tables
    local function migrate(profile)
        a.db = { profile = profile, global = {} }
        a:ApplyDatabaseMigrations()
        return profile
    end
    H.eq(migrate({ version = 3 }).micromenu.layout, "dock", "default places: the dock")
    H.eq(migrate({}).micromenu.layout, "dock", "a new profile: the dock")
    H.eq(migrate({ version = 3, widgets = { micromenu = { anchor = "BOTTOMRIGHT", posX = -3.4, posY = 3 } } })
        .micromenu.layout, "dock", "less than a pixel from the default is no move")
    H.eq(migrate({ version = 3, widgets = { micromenu = { anchor = "TOPLEFT", posX = 12, posY = -40 } } })
        .micromenu.layout, "strip", "a micro menu moved to the top left stays there")
    H.eq(migrate({ version = 3, widgets = { bagsbar = { anchor = "BOTTOMRIGHT", posX = -5, posY = 74 } } })
        .micromenu.layout, "strip", "a bag bar moved up")
    H.eq(migrate({ version = 3, micromenu = { normal = { columns = 6 } } }).micromenu.layout, "strip",
        "the strip in two rows of the player's own")
    H.eq(migrate({ version = 3, micromenu = { grayscale_icons = true, grayscale = { columns = 4 } } })
        .micromenu.layout, "strip")
    local kept = migrate({ version = 3, micromenu = { normal = { columns = 6, scale_menu = 0.8 } } })
    H.eq(kept.micromenu.normal.scale_menu, 0.8, "the player's own scale untouched")
    H.eq(kept.version, a.DB_SCHEMA_VERSION)

    -- the strip kept keeps its old sizes: the new defaults AceDB just filled in (1.0, 1.02) are the dock's
    local placed = migrate({ version = 3, widgets = { micromenu = { anchor = "TOPLEFT", posX = 12, posY = -40 } } })
    H.eq(placed.micromenu.layout, "strip")
    H.eq(placed.micromenu.normal.scale_menu, 0.9, "the strip's buttons at their old size")
    H.eq(placed.bags.scale, 1, "and the bag bar")
    local bags = migrate({ version = 3, micromenu = { normal = { columns = 6 } }, bags = { scale = 1.3 } })
    H.eq(bags.bags.scale, 1.3, "the player's own bag scale untouched")
    H.eq(bags.micromenu.normal.scale_menu, 0.9)
    local docked = migrate({ version = 3 })
    H.eq(docked.micromenu.normal.scale_menu, 1.0, "the dock takes the new sizes")
    H.eq(docked.bags.scale, 1.02)
    -- with core.lua's note from before AceDB, a 1.0 the player stored (no default under the old 0.9) is theirs
    a.NoteStoredProfiles({ profiles = {
        Mine = { micromenu = { normal = { columns = 6, scale_menu = 1.0 } } },
        Plain = { micromenu = { normal = { columns = 6 } } },
    } })
    local function migrateNamed(name, profile)
        a.db = { profile = profile, global = {}, GetCurrentProfile = function() return name end }
        a:ApplyDatabaseMigrations()
        return profile
    end
    local mine = migrateNamed("Mine", { version = 3, micromenu = { normal = { columns = 6, scale_menu = 1.0 } } })
    H.eq(mine.micromenu.layout, "strip")
    H.eq(mine.micromenu.normal.scale_menu, 1.0, "a stored 1.0 is the player's choice")
    H.eq(mine.bags.scale, 1, "no bag scale stored: the old default")
    local plain = migrateNamed("Plain", { version = 3, micromenu = { normal = { columns = 6 } } })
    H.eq(plain.micromenu.normal.scale_menu, 0.9, "nothing stored: the old default")
    local chosen = migrate({ version = a.DB_SCHEMA_VERSION, micromenu = { layout = "dock" },
        widgets = { micromenu = { anchor = "TOPLEFT", posX = 12, posY = -40 } } })
    H.eq(chosen.micromenu.layout, "dock", "the dock switched on after the update stays on")
end)

-- AddicatUI's start-up with the real AceDB (and LibStub, CallbackHandler) over these saved profiles, the character on
-- "Main": core.lua notes what each profile stored, opens AceDB, runs the migrations and registers RefreshConfig for
-- the profile callbacks. AceAddon is a stand-in (core.lua only takes its addon object).
local function aceGame(M, profiles)
    local env = M.env
    env.UnitFactionGroup = function(unit) if unit == "player" then return "Alliance", "Alliance" end end
    env.AddicatUIDB = { profileKeys = { [env.UnitName("player") .. " - " .. env.GetRealmName()] = "Main" },
        profiles = profiles }
    local a = fakeAddicatUI(M, {})
    a.RefreshLocale = function() end
    for _, lib in ipairs({ "LibStub/LibStub.lua", "CallbackHandler-1.0/CallbackHandler-1.0.lua",
        "AceDB-3.0/AceDB-3.0.lua" }) do
        run(M, a, "libs/" .. lib)
    end
    local AceAddon = env.LibStub:NewLibrary("AceAddon-3.0", 1)
    function AceAddon:NewAddon() return { ScheduleTimer = function() end } end
    run(M, a, "database.lua")
    run(M, a, "core/api.lua")
    run(M, a, "core.lua")
    a.core:OnInitialize()
    return a
end

test("aui dock: Copy From keeps the strip's sizes by what the copied profile stored, not the current one", function(M)
    -- an alt's profile from before the update with a stored 1.0 (the player's own: the old default was 0.9), one with
    -- no size stored, and the character's own
    local function before(scale)
        return { version = 3, micromenu = { normal = { columns = 6, scale_menu = scale } } }
    end
    local a = aceGame(M, { Main = before(nil), ["Alt - Bleakhold"] = before(1.0), Plain = before(nil) })
    local p = a.db.profile
    H.eq(a.db:GetCurrentProfile(), "Main")
    H.eq(p.micromenu.layout, "strip", "two rows of the player's own: the strip stays")
    H.eq(p.micromenu.normal.scale_menu, 0.9, "nothing stored: the old default")
    a.db:CopyProfile("Alt - Bleakhold")
    p = a.db.profile
    H.eq(p.micromenu.layout, "strip")
    H.eq(p.micromenu.normal.scale_menu, 1.0, "the alt's own 1.0 comes along, not Main's note (nothing stored)")
    H.eq(p.version, a.DB_SCHEMA_VERSION)

    local M2 = H.newGame()
    local b = aceGame(M2, { Main = before(1.0), Plain = before(nil) })
    H.eq(b.db.profile.micromenu.normal.scale_menu, 1.0, "Main's own 1.0")
    b.db:CopyProfile("Plain")
    p = b.db.profile
    H.eq(p.micromenu.layout, "strip")
    H.eq(p.micromenu.normal.scale_menu, 0.9, "Plain stored none: its old default, not Main's own 1.0")
    H.eq(p.bags.scale, 1, "and the bag bar's")
end)

------------------------------------------------------------------------------------------------------
-- The Dungeon Finder button
------------------------------------------------------------------------------------------------------
test("aui dock: the Dungeon Finder button opens Bleakhold's Activities, the stock finder without Bleakhold", function(M)
    local a, mm = dockGame(M)
    local real = H.ok(M.env.BleakholdToggle, "the Bleakhold addon's global (Widgets.lua)")
    H.eq(type(real), "function")
    local opened = {}
    M.env.BleakholdToggle = function(key) opened[#opened + 1] = key end
    mm.SetupGroupFinderButton()
    mm.SetupGroupFinderButton()                 -- once only: the stock handler is not wrapped twice
    local button = M.env.LFDMicroButton
    button:Click()
    H.eq(table.concat(opened, ","), "activities", "Activities")
    H.ok(not M.env.LFDParentFrame:IsShown(), "not the stock finder")

    M.env.BleakholdToggle = nil
    button:Click()
    H.ok(M.env.LFDParentFrame:IsShown(), "no Bleakhold: the button's own ToggleLFDParentFrame")
    button:Click()
    H.ok(not M.env.LFDParentFrame:IsShown(), "and toggles it")
    H.eq(#opened, 1)
    H.ok(a.L, "game built")
end)

------------------------------------------------------------------------------------------------------
-- Bag windows above the dock (bags_skin.lua's container hook)
------------------------------------------------------------------------------------------------------
test("aui dock: bag windows start above the dock, laid out once more after WoW's own pass", function(M)
    local env = M.env
    env.ContainerFrame_Update = function() end
    local layouts = {}
    -- updateContainerFrameAnchors (ContainerFrame.lua): the first bag from CONTAINER_OFFSET_Y, the next on it
    local c1 = env.CreateFrame("Frame", "ContainerFrame1", env.UIParent)
    local c2 = env.CreateFrame("Frame", "ContainerFrame2", env.UIParent)
    c1.bags = { "ContainerFrame1", "ContainerFrame2" }
    env.updateContainerFrameAnchors = function()
        layouts[#layouts + 1] = env.CONTAINER_OFFSET_Y
        c1:ClearAllPoints()
        c1:SetPoint("BOTTOMRIGHT", env.UIParent, "BOTTOMRIGHT", -45, env.CONTAINER_OFFSET_Y)
        c2:ClearAllPoints()
        c2:SetPoint("BOTTOMRIGHT", c1, "TOPRIGHT", 0, 0)
    end
    env.CONTAINER_OFFSET_Y = 70
    local a = dockGame(M)
    run(M, a, "modules/bags_skin.lua")
    local skin = a.registered.bags_skin
    skin.applied = true                           -- the skin's spacing on: it shares the hook

    a.RefreshMicromenu()                          -- the dock's layout installs the hook and lifts open bags
    local top = 4 + env.AddicatUI_MicroDock:GetHeight()
    H.eq(#layouts, 2, "WoW's pass, then one more from the dock's top")
    H.eq(layouts[1], 70)
    near(layouts[2], top + 4)
    near(env.CONTAINER_OFFSET_Y, top + 4)

    -- UIParent lays the screen out and puts its own start back
    layouts = {}
    env.CONTAINER_OFFSET_Y = 70
    env.updateContainerFrameAnchors()
    H.eq(#layouts, 2)
    near(layouts[2], top + 4)
    H.eq(c2:GetNumPoints(), 2, "the skin's spacing ran once, on the final layout (one gap added)")
    local _, _, _, _, gapY = c2:GetPoint(2)
    H.eq(gapY, 4, "BAG_VERTICAL_GAP")

    -- already high enough: one pass
    layouts = {}
    env.updateContainerFrameAnchors()
    H.eq(#layouts, 1)

    -- a dock moved away from the bottom right corner leaves WoW's start alone
    a.dockCorner = { 400, 4 }
    layouts = {}
    env.CONTAINER_OFFSET_Y = 70
    env.updateContainerFrameAnchors()
    H.eq(#layouts, 1)
    H.eq(env.CONTAINER_OFFSET_Y, 70)

    -- and so does the strip
    a.dockCorner = { 1020, 4 }
    a.db.profile.micromenu.layout = "strip"
    env.updateContainerFrameAnchors()
    H.eq(env.CONTAINER_OFFSET_Y, 70)
end)
