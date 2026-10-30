-- The Bleakhold UI features folded into AddicatUI (UI by Addicated): the window chrome, the quest log and PvP skins'
-- wiring, the BLEAKHOLD mark and the game-menu credit, /bhui, the classic theme default and its migration, and the
-- addon manager sparing Bleakhold. AddicatUI is not loaded as a whole here: each test runs the real AddicatUI file
-- against a stand-in for the parts of AddicatUI it reaches, and without AddicatUI_Art (no art is ever loaded).
local AUI = repo .. "/Interface/AddOns/AddicatUI/"

-- What the files reach on AddicatUI's addon table, recorded.
local function fakeAddicatUI(profile)
    local a = {
        L = setmetatable({}, { __index = function(_, k) return k end }),
        _dir = "Interface\\AddOns\\AddicatUI_Art\\Textures\\",
        db = { profile = profile or { minimap = {}, modules = {} }, global = {} },
        registered = {},
        printed = {},
    }
    function a:RegisterModule(name, module, displayName, description, options)
        self.registered[name] = { module = module, displayName = displayName, description = description,
            options = options or {} }
        return true
    end
    function a:GetModuleConfig(name)
        return self.db.profile.modules and self.db.profile.modules[name]
    end
    function a:IsModuleEnabled(name)
        local cfg = self:GetModuleConfig(name)
        return cfg and cfg.enabled or false
    end
    function a:Print(...)
        self.printed[#self.printed + 1] = table.concat({ ... }, " ")
    end
    return a
end

-- Runs one AddicatUI file the way the client does: (addon name, addon table) as its `...`, in the game's globals.
local function run(M, a, rel)
    local chunk = assert(host_loadfile(AUI .. rel))
    setfenv(chunk, M.env)
    chunk("AddicatUI", a)
end

-- Delivers an event to the frames created since `from` (the file under test's own), not to the Bleakhold addon's.
local function fireNew(M, from, event, ...)
    for i = from + 1, #M.objects do
        local o = M.objects[i]
        if o.__events and o.__events[event] and o.__scripts.OnEvent then
            o.__scripts.OnEvent(o, event, ...)
        end
    end
end

local function font(M, name)
    local f = M.env.CreateFont(name)
    f.__font = { "Fonts\\FRIZQT__.TTF", 10 }
    return f
end

local function read(rel)
    return assert(host_readfile(repo .. "/Interface/AddOns/" .. rel), "missing " .. rel)
end

-- The file a texture was last asked for. AddicatUI_Art is not in the repo, so a mock that knows which files exist
-- loads none of it and keeps the request in __tried; an older mock loads any path, and GetTexture has it.
local function asked(tex)
    return tex.__tried or tex:GetTexture()
end

------------------------------------------------------------------------------------------------------
-- Window chrome (utils/window_chrome.lua)
------------------------------------------------------------------------------------------------------
local function chromeAddicatUI(M)
    local a = fakeAddicatUI()
    a.atlasinfo = {
        ["questbg-parchment"] = { "parchment", 299, 407, 0, 0.29, 0, 0.39 },
        ["questlog-main-background"] = { "tome", 307, 510, 0, 0.6, 0, 0.99 },
        ["_UI-Frame-TopTileStreaks"] = { "streaks", 256, 43, 0, 1, 0.0078, 0.34 },
    }
    a.red = {}
    a.SkinRedButton = function(b) a.red[#a.red + 1] = b end
    a.closed = {}
    a.bars = {}
    a.CharacterPanel = {
        ReskinScrollBar = function(scroll, host, top, x, bottom, steppers)
            a.bars[#a.bars + 1] = { scroll, host, top, x, bottom, steppers }
        end,
        ModernizeCloseButton = function(btn, owner, x, y) a.closed[#a.closed + 1] = { btn, owner, x, y } end,
    }
    local applied = {}
    M.env.AddicatUI_NineSlice = {
        GetLayout = function(name)
            if name == "PortraitFrameTemplate" or name == "InsetFrameTemplate" then return { name = name } end
        end,
        ApplyLayout = function(frame, layout) applied[#applied + 1] = { frame, layout.name } end,
    }
    run(M, a, "utils/window_chrome.lua")
    return a, applied
end

test("aui chrome: AddicatUI.WindowChrome is there, and false (with every call harmless) without its pieces",
    function(M)
        local a = fakeAddicatUI()
        run(M, a, "utils/window_chrome.lua")
        local WC = H.ok(a.WindowChrome, "exported as addon.WindowChrome")
        H.ok(WC.chrome() == false, "no atlas registry, nine-slice or character panel: no chrome")
        local f = M.env.CreateFrame("Frame", nil, M.env.UIParent)
        local tex = f:CreateTexture(nil, "ARTWORK")
        H.ok(WC.atlas(tex, "questbg-parchment") == false and asked(tex) == nil, "an unknown atlas changes nothing")
        H.ok(WC.nineSlice(f, "PortraitFrameTemplate") == false, "no nine-slice layouts")
        local btn = M.env.CreateFrame("Button", nil, f)
        WC.redButton(btn)
        WC.closeButton(btn, f)
        H.eq(f.bhClose, btn, "the close button is still remembered for the layers")
        WC.scrollBar(M.env.CreateFrame("ScrollFrame", nil, f), f, 0, -8, 0, true)
        H.eq(WC.CREDIT, "Bleakhold UI  -  made by Addicated")
    end)

test("aui chrome: a dressed window has the metal on top, rock and streaks under, ring portrait and centred title",
    function(M)
        local a, applied = chromeAddicatUI(M)
        local WC = a.WindowChrome
        H.ok(WC.chrome() == true, "every piece there")
        local f = M.env.CreateFrame("Frame", "AuiChromeTest", M.env.UIParent)
        f:SetFrameLevel(5)
        WC.dressWindow(f, 338, 496)
        H.eq(f:GetWidth(), 338)
        H.eq(f:GetHeight(), 496)
        H.eq(f.bhBorder:GetFrameLevel(), 15, "the metal border 10 levels above the window")
        H.eq(applied[1][1], f.bhBorder)
        H.eq(applied[1][2], "PortraitFrameTemplate")
        H.eq(asked(f.bhRock), a._dir .. "UI\\ui-background-rock", "the rock ground")
        H.eq(asked(f.bhStreaks), "streaks", "the streaks under the title from the atlas")
        H.eq(f.bhStreaks:GetHeight(), 43)

        local portrait = WC.portrait(f, nil, "Interface\\QuestFrame\\UI-QuestLog-BookIcon")
        local p, rel, rp, x, y = portrait:GetPoint(1)
        H.ok(p == "TOPLEFT" and rel == f and x == -5 and y == 7, "the portrait sits in the ring")
        H.eq(portrait:GetWidth(), 62)

        local title = f:CreateFontString(nil, "OVERLAY")
        WC.title(f, title)
        H.eq(title:GetParent(), f.bhTitleHolder, "the title moves onto a holder")
        H.eq(f.bhTitleHolder:GetFrameLevel(), f.bhBorder:GetFrameLevel() + 2, "above the metal")

        -- content raised past the metal later: topLayers puts the metal (and its holders) back on top
        local content = M.env.CreateFrame("Frame", nil, f)
        content:SetFrameLevel(40)
        local close = M.env.CreateFrame("Button", nil, f)
        WC.closeButton(close, f)
        H.eq(a.closed[1][3], 1)
        H.eq(a.closed[1][4], 0)
        WC.topLayers(f)
        H.eq(f.bhBorder:GetFrameLevel(), 41)
        H.eq(f.bhTitleHolder:GetFrameLevel(), 42)
        H.eq(close:GetFrameLevel(), 43)

        local inset = WC.inset(f)
        H.eq(applied[#applied][2], "InsetFrameTemplate")
        H.eq(asked(inset.bg), a._dir .. "UI\\ui-background-marble")
        H.ok(WC.inset(f, false).bg == nil, "a plain inset has no marble")

        font(M, "GameFontDisableSmall")
        local credit = WC.creditLine(f)
        H.eq(credit:GetText(), "Bleakhold UI by Addicated")
    end)

------------------------------------------------------------------------------------------------------
-- Quest log and PvP skins: modules, defaults and wiring
------------------------------------------------------------------------------------------------------
test("aui skins: questlog and pvpframe register load-once and stay quiet without WoW's frames", function(M)
    local a = fakeAddicatUI({ minimap = {},
        modules = { questlog = { enabled = true }, pvpframe = { enabled = true } } })
    run(M, a, "utils/window_chrome.lua")
    run(M, a, "modules/questlog_skin.lua")
    run(M, a, "modules/pvpframe_skin.lua")
    local q, p = H.ok(a.registered.questlog, "questlog module"), H.ok(a.registered.pvpframe, "pvpframe module")
    H.ok(q.options.loadOnce and p.options.loadOnce, "their hooks cannot be undone: load-once")
    H.eq(q.displayName, "Quest Log")
    H.eq(p.displayName, "PvP Window")
    -- AddicatUI_Art is absent and so are QuestLogFrame and PVPParentFrame here: nothing is built, nothing printed
    a.ApplyQuestLogSkinSystem()
    a.ApplyPvPFrameSkinSystem()
    H.eq(#a.printed, 0, "no 'skipped' message when the frames are simply not there")
    H.ok(not q.module.initialized and not p.module.initialized, "nothing built")
    H.ok(not q.module.Refresh, "no Refresh for the registry to call in place of the apply step")

    local off = fakeAddicatUI({ minimap = {}, modules = { questlog = { enabled = false }, pvpframe = {} } })
    run(M, off, "utils/window_chrome.lua")
    run(M, off, "modules/questlog_skin.lua")
    run(M, off, "modules/pvpframe_skin.lua")
    off.ApplyQuestLogSkinSystem()
    off.ApplyPvPFrameSkinSystem()
    H.ok(not off.registered.questlog.module.applied and not off.registered.pvpframe.module.applied, "off stays off")
end)

test("aui skins: defaults on, wired after the chrome, listed under Panels", function(M)
    local a = fakeAddicatUI()
    run(M, a, "database.lua")
    local modules = a.defaults.profile.modules
    H.eq(modules.questlog.enabled, true, "quest log skin on by default")
    H.eq(modules.pvpframe.enabled, true, "PvP skin on by default")

    local utils = read("AddicatUI/utils/utils.xml")
    local chrome = H.ok(utils:find('<Script file="window_chrome.lua"/>', 1, true), "window_chrome.lua loads")
    H.ok(chrome > utils:find('<Script file="nineslice.lua"/>', 1, true)
        and chrome > utils:find('<Script file="redbutton.lua"/>', 1, true), "after nineslice and redbutton")

    local xml = read("AddicatUI/modules/modules.xml")
    local cp = xml:find('characterpanel\\characterpanel.xml', 1, true)
    for _, file in ipairs({ "questlog_skin.lua", "pvpframe_skin.lua" }) do
        local at = H.ok(xml:find('<Script file="' .. file .. '"/>', 1, true), file .. " in modules.xml")
        H.ok(at > cp, file .. " after the character panel it borrows the close button and scroll bars from")
    end
    local mark = H.ok(xml:find('<Script file="bleakmark.lua"/>', 1, true), "bleakmark.lua in modules.xml")
    H.ok(mark > xml:find('<Script file="gamemenu.lua"/>', 1, true), "the credit file after gamemenu.lua")

    local panels = read("AddicatUI_Options/panel/tab_modules.lua"):match('{ title = "Panels", modules = (%b{})')
    H.ok(panels and panels:find('"questlog"', 1, true) and panels:find('"pvpframe"', 1, true),
        "both in the Options Panels list")
end)

test("aui locale: every string the Bleakhold UI files ask for is in enUS", function(M)
    local enUS = read("AddicatUI/Locales/enUS.lua")
    local have = {}
    for key in enUS:gmatch('L%["(.-)"%] = true') do have[key] = true end
    for _, rel in ipairs({ "AddicatUI/modules/questlog_skin.lua", "AddicatUI/modules/pvpframe_skin.lua",
        "AddicatUI/modules/bleakmark.lua", "AddicatUI/core/commands.lua", "AddicatUI/modules/addonmanager.lua",
        "AddicatUI_Options/panel/tab_minimap.lua" }) do
        local src = read(rel)
        -- only the strings this port added are checked in the older files
        local from = rel:find("commands", 1, true) and src:find("/bhui: THE BLEAKHOLD UI COMMAND", 1, true) or 1
        local to = rel:find("commands", 1, true) and src:find("COMMAND REGISTRATION", from, true) or #src
        for key in src:sub(from, to):gmatch('L%["(.-)"%]') do
            if rel:find("addonmanager", 1, true) or rel:find("tab_minimap", 1, true) then
                if key == "Built in" or key:find("Bleakhold", 1, true) or key:find("BLEAKHOLD", 1, true) then
                    H.ok(have[key], rel .. ": no enUS string " .. key)
                end
            else
                H.ok(have[key], rel .. ": no enUS string " .. key)
            end
        end
    end
end)

------------------------------------------------------------------------------------------------------
-- The BLEAKHOLD mark and the game-menu credit (modules/bleakmark.lua)
------------------------------------------------------------------------------------------------------
local function markGame(M, profile)
    local a = fakeAddicatUI(profile)
    a.durability = 0
    a.MinimapModule = { ApplyDurabilityPosition = function() a.durability = a.durability + 1 end }
    font(M, "GameFontDisableSmall")
    local menu = M.env.CreateFrame("Frame", "GameMenuFrame", M.env.UIParent)
    menu:SetSize(195, 296)
    local from = #M.objects
    run(M, a, "utils/window_chrome.lua")
    run(M, a, "modules/bleakmark.lua")
    return a, from, menu
end

test("aui mark: BLEAKHOLD in MORPHEUS 12 outline gold under the minimap, with the Addicated tooltip", function(M)
    local a, from = markGame(M)
    fireNew(M, from, "PLAYER_LOGIN")
    local mark = H.ok(M.env.AddicatUIBleakholdMark, "the mark")
    H.eq(mark:GetParent(), M.env.Minimap)
    H.eq(mark:GetWidth(), 110)
    H.eq(mark:GetHeight(), 14)
    local p, rel, rp, x, y = mark:GetPoint(1)
    H.ok(p == "TOP" and rel == M.env.Minimap and rp == "BOTTOM" and x == 0 and y == -6,
        "TOP of the map's BOTTOM, 0, -6")
    H.eq(mark:GetFrameLevel(), M.env.Minimap:GetFrameLevel() + 5)
    H.eq(mark.text:GetText(), "BLEAKHOLD")
    local file, size, flags = mark.text:GetFont()
    H.ok(file == "Fonts\\MORPHEUS.ttf" and size == 12 and flags == "OUTLINE", "MORPHEUS 12 OUTLINE")
    local r, g, b = mark.text:GetTextColor()
    H.ok(r == 0.90 and g == 0.80 and b == 0.50, "the Bleakhold gold")
    H.ok(mark:IsShown(), "on by default")
    H.eq(a.durability, 1, "the durability figure is placed again once the mark is up")

    M.Fire(mark, "OnEnter")
    local lines = M.env.GameTooltip.__lines
    H.eq(lines[1], "Bleakhold")
    H.eq(lines[2], "UI by Addicated")
    H.contains(lines[3], "/bhui")
    M.Fire(mark, "OnLeave")
end)

test("aui mark: its band clears the durability figure, follows a capture bar and goes with the option", function(M)
    local a, from = markGame(M)
    fireNew(M, from, "PLAYER_LOGIN")
    local BM, mark = a.BleakMark, M.env.AddicatUIBleakholdMark
    -- the band minimap.lua moves the durability figure down by: the mark's 14 + its 6 gap + 4 of air
    H.eq(BM.Band(), 24)
    BM.SetCaptureBar(true)
    local _, _, _, _, y = mark:GetPoint(1)
    H.eq(y, -36, "below a capture bar (centred 20 under the map)")
    H.eq(mark:GetNumPoints(), 1, "moved, not pinned twice")
    BM.SetCaptureBar(false)
    _, _, _, _, y = mark:GetPoint(1)
    H.eq(y, -6)

    a.db.profile.minimap.bleakhold_mark = false
    BM.Refresh()
    H.ok(not mark:IsShown(), "hidden by the option")
    H.eq(BM.Band(), 0, "a hidden mark takes no room: the figure goes back up")
    H.eq(a.durability, 2)
    a.db.profile.minimap.bleakhold_mark = true
    BM.Refresh()
    H.ok(mark:IsShown())

    local off = fakeAddicatUI({ minimap = { bleakhold_mark = false }, modules = {} })
    local before = #M.objects
    run(M, off, "modules/bleakmark.lua")
    fireNew(M, before, "PLAYER_LOGIN")
    H.ok(not M.env.AddicatUIBleakholdMark:IsShown(), "a profile with the mark off logs in without it")
end)

test("aui mark: the game-menu credit hangs under the menu, and an old Bleakhold UI copy's pair is hidden",
    function(M)
        local _, from, menu = markGame(M)
        local oldMark = M.env.CreateFrame("Frame", "BleakholdUIMark", M.env.Minimap)
        local oldCredit = menu:CreateFontString("BleakholdUIMenuCredit", "OVERLAY", "GameFontDisableSmall")
        fireNew(M, from, "PLAYER_LOGIN")
        fireNew(M, from, "PLAYER_ENTERING_WORLD")
        local credit = H.ok(M.env.AddicatUIBleakholdMenuCredit, "the credit")
        H.eq(credit:GetParent(), menu)
        H.eq(credit:GetText(), "Bleakhold UI  -  made by Addicated")
        local p, rel, rp, x, y = credit:GetPoint(1)
        -- anchored to the bottom edge, so the frame growing for AddicatUI's buttons carries it along
        H.ok(p == "BOTTOM" and rel == menu and rp == "BOTTOM" and x == 0 and y == -16, "BOTTOM of the menu, 0, -16")
        H.ok(not oldMark:IsShown() and not oldCredit:IsShown(), "one mark and one credit")
    end)

------------------------------------------------------------------------------------------------------
-- /bhui (core/commands.lua)
------------------------------------------------------------------------------------------------------
local function bhui(M)
    local a = fakeAddicatUI({ minimap = {}, modules = { talents = { enabled = true },
        questlog = { enabled = true }, pvpframe = { enabled = true } } })
    a.refreshed = 0
    a.BleakMark = { Refresh = function() a.refreshed = a.refreshed + 1 end }
    run(M, a, "core/commands.lua")
    return a, a.BleakholdCommands
end

local function said(M, from)
    local out = {}
    for i = from + 1, #M.chat do out[#out + 1] = M.chat[i].msg end
    return out
end

test("aui /bhui: help lists talents, dock, mark, quests, pvp and help, credited to Addicated", function(M)
    local _, B = bhui(M)
    B.Run("")
    local lines = said(M, 0)
    local want = { "/bhui talents", "/bhui dock", "/bhui mark", "/bhui quests", "/bhui pvp", "/bhui help" }
    for i, w in ipairs(want) do H.contains(lines[i], w) end
    H.contains(lines[#want + 1], "UI by Addicated.")
    H.eq(#lines, #want + 1)
    local n = #M.chat
    B.Run("help")
    H.eq(#M.chat - n, #want + 1, "help says the same")
    n = #M.chat
    B.Run("nonsense")
    H.eq(#M.chat - n, #want + 1, "an unknown word gets the help")
end)

test("aui /bhui: quests, pvp, mark and talents switch AddicatUI's own options", function(M)
    local a, B = bhui(M)
    local modules = a.db.profile.modules
    B.Run("quests classic")
    H.eq(modules.questlog.enabled, false, "WoW's quest log")
    B.Run("Quests BLEAKHOLD")
    H.eq(modules.questlog.enabled, true, "case does not matter")
    local n = #M.chat
    B.Run("quests")
    H.eq(modules.questlog.enabled, true, "no choice, no change")
    H.contains(said(M, n)[1], "/bhui quests bleakhold | classic")
    B.Run("pvp classic")
    H.eq(modules.pvpframe.enabled, false)
    H.contains(M.chat[#M.chat].msg, "/reload")

    B.Run("mark")
    H.eq(a.db.profile.minimap.bleakhold_mark, false, "hidden")
    H.eq(a.refreshed, 1, "the mark follows at once")
    B.Run("mark")
    H.eq(a.db.profile.minimap.bleakhold_mark, true, "shown again")

    B.Run("talents blizzard")
    H.eq(modules.talents.enabled, false, "WoW's own talent window")
    B.Run("talents addicatui")
    H.eq(modules.talents.enabled, true)
end)

test("aui /bhui: a listed subcommand without a handler says so until a file registers it", function(M)
    local _, B = bhui(M)
    local n = #M.chat
    B.Run("dock")
    H.contains(said(M, n)[1], "not available in this build: /bhui dock")
    local got
    B.Register("dock", function(arg) got = arg end, "/bhui dock - the dock")
    B.Run("dock off")
    H.eq(got, "off", "the rest of the line, lower case")
    B.Run("")
    local lines = said(M, n + 1)
    H.eq(lines[2], "|cffe6cc80Bleakhold UI|r /bhui dock - the dock", "taking a name over keeps its place in the list")
end)

------------------------------------------------------------------------------------------------------
-- Theme default and its migration (database.lua, core/api.lua)
------------------------------------------------------------------------------------------------------
local function migrate(M, profile)
    local a = fakeAddicatUI(profile)
    run(M, a, "database.lua")
    run(M, a, "core/api.lua")
    a.db = { profile = profile, global = {} }
    a:ApplyDatabaseMigrations()
    return a
end

test("aui theme: classic is the default, the old stored default moves to it once, a later choice stays", function(M)
    local a = fakeAddicatUI()
    run(M, a, "database.lua")
    run(M, a, "core/api.lua")
    H.eq(a.defaults.profile.modules.theme.style, "classic", "the World of Warcraft look by default")
    H.eq(a.DB_SCHEMA_VERSION, 4)
    H.eq(a.defaults.profile.minimap.bleakhold_mark, true, "the mark on by default")

    local old = { version = 3, modules = { theme = { style = "bleakhold" } } }
    migrate(M, old)
    H.eq(rawget(old.modules.theme, "style"), nil, "the stored old default is dropped: the new default applies")
    H.eq(old.version, 4)

    local chosen = { version = 4, modules = { theme = { style = "bleakhold" } } }
    migrate(M, chosen)
    H.eq(chosen.modules.theme.style, "bleakhold", "the flat theme chosen after the move stays selectable")

    local classic = { version = 3, modules = { theme = { style = "classic" } } }
    migrate(M, classic)
    H.eq(classic.modules.theme.style, "classic")

    local untouched = { version = 3, modules = {} }
    migrate(M, untouched)
    H.eq(untouched.modules.theme.style, "classic", "an untouched profile gets the new default")
end)

------------------------------------------------------------------------------------------------------
-- Addon manager (modules/addonmanager.lua)
------------------------------------------------------------------------------------------------------
local function addonList(M, list)
    local disabled, enabled = {}, {}
    local byName = {}
    for i, e in ipairs(list) do byName[e.name] = e; e.index = i end
    M.env.GetNumAddOns = function() return #list end
    M.env.GetAddOnInfo = function(id)
        local e = type(id) == "number" and list[id] or byName[id]
        if not e then return id, nil, nil, nil, nil, "MISSING", "INSECURE" end
        return e.name, e.name, nil, e.enabled and 1 or nil, 1, e.enabled and nil or "DISABLED", "INSECURE"
    end
    M.env.DisableAddOn = function(id)
        local e = type(id) == "number" and list[id] or byName[id]
        disabled[#disabled + 1] = e and e.name or tostring(id)
    end
    M.env.EnableAddOn = function(id)
        local e = type(id) == "number" and list[id] or byName[id]
        enabled[#enabled + 1] = e and e.name or tostring(id)
    end
    -- the toc's ## Dependencies (GameUI_Scripts.cpp: nothing for an unknown name)
    M.env.GetAddOnDependencies = function(id)
        local e = type(id) == "number" and list[id] or byName[id]
        if e and e.deps then return unpack(e.deps) end
    end
    M.env.LibStub = function() return nil end
    return disabled, enabled
end

test("aui addon manager: Disable All spares Bleakhold, AddicatUI, the art it needs and its settings", function(M)
    local disabled = addonList(M, {
        { name = "AddicatUI", enabled = true, deps = { "AddicatUI_Art" } },
        { name = "AddicatUI_Options", enabled = true, deps = { "AddicatUI" } },
        { name = "AddicatUI_Art", enabled = true }, { name = "Bleakhold", enabled = true },
        { name = "Questie", enabled = true }, { name = "DBM-Core", enabled = true },
        { name = "DBM-Party", enabled = true, deps = { "DBM-Core" } },
    })
    local a = fakeAddicatUI({ minimap = {}, modules = { addonmanager = { enabled = true } } })
    run(M, a, "modules/addonmanager.lua")
    local module = a.registered.addonmanager.module
    module.DisableAll()
    H.eq(table.concat(disabled, ","), "Questie,DBM-Core,DBM-Party",
        "AddicatUI_Art stays on: AddicatUI.toc requires it, and AddicatUI would not load without it")
    local keep = module.AlwaysOn()
    H.ok(keep.AddicatUI and keep.Bleakhold and keep.AddicatUI_Art, "the always-on addons and what they require")
    H.ok(not keep["DBM-Core"] and not keep.AddicatUI_Options, "nothing they do not require")
    local toc = read("AddicatUI/AddicatUI.toc")
    H.ok(toc:find("## Dependencies: AddicatUI_Art", 1, true), "the requirement this follows")
end)

test("aui addon manager: Bleakhold is built in: one turned off before is put back, a missing one is left", function(M)
    local _, enabled = addonList(M, {
        { name = "AddicatUI", enabled = true }, { name = "Bleakhold", enabled = false }, { name = "Questie" },
    })
    local a = fakeAddicatUI({ minimap = {}, modules = { addonmanager = { enabled = true } } })
    run(M, a, "modules/addonmanager.lua")
    a.registered.addonmanager.module.KeepAlwaysOn()
    H.eq(table.concat(enabled, ","), "Bleakhold", "only Bleakhold, and Questie stays as it was")

    local _, none = addonList(M, { { name = "AddicatUI", enabled = true } })
    a.registered.addonmanager.module.KeepAlwaysOn()
    H.eq(#none, 0, "no Bleakhold folder: nothing to enable")

    local _, art = addonList(M, { { name = "AddicatUI", enabled = true, deps = { "AddicatUI_Art" } },
        { name = "AddicatUI_Art", enabled = false }, { name = "Bleakhold", enabled = true } })
    a.registered.addonmanager.module.KeepAlwaysOn()
    H.eq(table.concat(art, ","), "AddicatUI_Art", "an art addon an older Disable All turned off is put back")

    local src = read("AddicatUI/modules/addonmanager.lua")
    H.ok(src:find('L["Built in"]', 1, true), "its row reads Built in")
end)
