-- The Activities window in the old BleakholdActivities window's look (Activities.lua): the frame, the nav (it must fit
-- with every entry live), the page anatomy and its art (JournalArt.lua), Leave dungeon, the entry points, and the old
-- addons a player may still have installed (OldAddons.lua).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local ALL_LIVE = { [6] = 4096 + 16384 + 65536 }   -- Bleakhold Royale, War Mode, Arena

local function navEntry(ns, key)
    for _, b in ipairs(ns.Activities.nav) do
        if b.key == key then return b end
    end
end

local function shownNav(ns)
    local out = {}
    for _, b in ipairs(ns.Activities.nav) do
        if b:IsShown() then out[#out + 1] = b end
    end
    return out
end

local function saidSay(M)
    local out = {}
    for _, s in ipairs(M.said) do
        if s.chatType == "SAY" then out[#out + 1] = s.msg end
    end
    return out
end

local function texture(t)
    return t.__texture
end

test("shell: the old window's frame, title bar, portrait, nav panel and content panel", function(M, ns)
    local A = ns.Activities
    local win = M.env.BleakholdActivitiesFrame
    H.eq(win, A.frame)
    H.eq(win:GetWidth(), A.W); H.eq(win:GetHeight(), A.H)
    H.eq(win.__backdrop.bgFile, "Interface\\DialogFrame\\UI-DialogBox-Background-Dark", "the dialog frame")
    H.eq(win.__backdrop.edgeFile, "Interface\\DialogFrame\\UI-DialogBox-Border")
    -- the panels: the tooltip frame, tinted dark (old panelBox), the nav at (18, -46), 216 wide, the content from 244
    for _, p in ipairs({ A.navPanel, A.content }) do
        H.eq(p.__backdrop.bgFile, "Interface\\Tooltips\\UI-Tooltip-Background")
        H.eq(p.__backdrop.edgeFile, "Interface\\Tooltips\\UI-Tooltip-Border")
        H.eq(p.__backdrop.edgeSize, 16)
    end
    local _, rel, _, x, y = A.navPanel:GetPoint(1)
    H.ok(rel == win and x == 18 and y == -46, "nav panel at 18, -46")
    H.eq(A.navPanel:GetWidth(), 216)
    H.eq(A.NAV_H, A.H - 46 - 18, "down to 18 from the bottom")
    _, rel, _, x, y = A.content:GetPoint(1)
    H.ok(rel == win and x == 244 and y == -46, "content panel at 244, -46")
    H.eq(A.content:GetWidth() + 244 + 18, A.W, "to 18 from the right")
    H.eq(A.content:GetHeight() + 46 + 18, A.H, "and from the bottom")
    -- the plain pages keep the body they were laid out for, taller now
    H.ok(A.PW >= 788, "plain page width " .. A.PW)
    H.ok(A.PH >= 516, "plain page height " .. A.PH)
    -- every page opens with the old window's title and the page's icon in the portrait
    ns.UI.Open("keys")
    H.eq(win.title:GetText(), "Mythic+ Dungeons")
    H.eq(win.portrait.icon.__texture, "Interface\\Icons\\Spell_Holy_BorrowedTime", "the page's icon, cut round")
    H.ok(win.portrait.icon.__portrait, "SetPortraitToTexture")
    ns.Activities.Show("journey")
    H.eq(ns.Activities.current, "dungeons", "the old page name")
    H.eq(win.title:GetText(), "Dungeon Finder")
    ns.Activities.Show("rift")
    H.eq(win.title:GetText(), "Enter the Eclipse Rift")
    H.eq(win.portrait.icon.__texture, "Interface\\Icons\\Ability_Druid_EclipseOrange")
    ns.Activities.Show("tasks")
    H.eq(win.title:GetText(), "Tasks")
    -- the open page is the one lit (held "tabOn"), the label gold
    H.eq(navEntry(ns, "tasks").style, "tabOn")
    H.eq(navEntry(ns, "rift").style, "tab")
    local opened = false
    for _, snd in ipairs(M.sounds) do
        if snd == "AchievementMenuOpen" then opened = true end
    end
    H.ok(opened, "the achievement window's sound, as the old window")
end)

test("shell: the nav fits with every entry live, at the old pitch while it can", function(M, ns)
    local A = ns.Activities
    FX.connect(M, H)
    A.LayoutNav()
    local base = shownNav(ns)
    H.eq(#base, 8, "five old pages, Tasks, Legacies, Season")
    H.eq(A.navPitch, 70, "the old 70 px pitch")
    H.eq(base[1]:GetHeight(), 66, "66 px rows")
    H.eq(base[1].ring.ringSize, 50, "50 px rings")
    FX.connect(M, H, ALL_LIVE)
    A.LayoutNav()
    local all = shownNav(ns)
    H.eq(#all, 11, "every entry live")
    local keys = {}
    for i, b in ipairs(all) do keys[i] = b.key end
    H.eq(table.concat(keys, ","), "dungeons,keys,rift,heroic,group,royale,warmode,arena,tasks,legacies,season",
        "PLAN 3's order")
    for i, b in ipairs(all) do
        local point, rel, relPoint, x, y = b:GetPoint(1)
        H.ok(point == "TOPLEFT" and rel == A.navPanel and relPoint == "TOPLEFT", b.key .. " anchored to the panel")
        H.eq(x, A.NAV_PAD)
        local bottom = -y + b:GetHeight()
        H.ok(bottom <= A.navPanel:GetHeight() - A.NAV_PAD, b.key .. " ends at " .. bottom .. ", inside the panel ("
            .. A.navPanel:GetHeight() .. ")")
        H.ok(b:GetWidth() + A.NAV_PAD * 2 <= A.navPanel:GetWidth(), "as wide as the panel allows")
        if i > 1 then
            local _, _, _, _, py = all[i - 1]:GetPoint(1)
            H.ok(-y >= -py + all[i - 1]:GetHeight(), b.key .. " below " .. all[i - 1].key .. ", no overlap")
        end
        H.ok(b.ring.ringSize >= 32 and b.ring.ringSize <= b:GetHeight() - 8, b.key .. ": ring " .. b.ring.ringSize
            .. " in a " .. b:GetHeight() .. " px row")
    end
    -- the panel itself inside the window
    H.ok(46 + A.navPanel:GetHeight() <= A.H - 11, "the panel inside the window's border")
    -- and back: a realm that turns them off closes the gaps
    FX.connect(M, H)
    A.LayoutNav()
    H.eq(#shownNav(ns), 8)
    H.ok(not navEntry(ns, "arena"):IsShown())
end)

test("shell: the page anatomy (A.Page): title, description, stat column, section, art", function(M, ns)
    local A = ns.Activities
    local p = A.Page("group")
    H.ok(p.anatomy, "Group Finder is an anatomy page")
    H.eq(A.Page("group"), p, "asking again gives the same page")
    H.eq(p.title:GetText(), "Group Finder", "the nav label")
    local _, _, _, x, y = p.title:GetPoint(1)
    H.ok(x == 20 and y == -18, "gold 22 title at 20, -18")
    H.eq(select(2, p.title:GetFont()), 22)
    _, _, _, x, y = p.desc:GetPoint(1)
    H.ok(x == 20 and y == -50, "description at 20, -50")
    H.eq(p.desc:GetWidth(), 390, "390 wide")
    H.contains(p.desc:GetText(), "classic Dungeon Finder")
    local v = p:Stat(2, "Best Solo")
    H.eq(v.label:GetText(), "Best Solo")
    local _, _, _, sx, sy = v.label:GetPoint(1)
    H.ok(sx == -20 and sy == -20 - 46, "the second stat 46 px under the first, 20 in from the right")
    H.eq(select(2, v:GetFont()), 15)
    local s = p:Section("How it works")
    local _, _, _, hx, hy = s:GetPoint(1)
    H.ok(hx == 20 and hy == -122, "a section at the old pages' first heading")
    -- a page made by a file of its own takes the place of a plain one of the same key
    local plain = A.NewPage()
    A.AddPage("probe", plain)
    local q = A.Page("probe", { title = "Probe", desc = "text", art = "SCHOLOMANCE", artAlpha = 0.5 })
    H.ok(q ~= plain and A.pages.probe == q, "replaced")
    H.eq(q.title:GetText(), "Probe")
    H.eq(A.ArtOf("probe"), "SCHOLOMANCE")
    q:SetArt(false)
    H.eq(A.ArtOf("probe"), nil, "no art")
    q:SetArt({ file = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\MapThumb", coords = { 0, 1, 0, 1 } })
    H.eq(A.ArtOf("probe").file, "Interface\\AddOns\\Bleakhold\\Art\\Royale\\MapThumb", "art of our own")
end)

test("shell art: a picture of our own fades into the dark at the top, bottom and right too", function(M, ns)
    local A = ns.Activities
    local own = { file = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\MapThumb" }
    local q = A.Page("probe", { title = "Probe", art = own })
    A.Show("probe")
    H.eq(A.artSource, "own")
    H.ok(A.art:IsShown() and A.fade:IsShown(), "the art and the left fade")
    local dark = { 0.02, 0.02, 0.04 }
    local want = {
        top = { "VERTICAL", 0, 1, "TOPLEFT", "TOPRIGHT" },
        bottom = { "VERTICAL", 1, 0, "BOTTOMLEFT", "BOTTOMRIGHT" },
        right = { "HORIZONTAL", 0, 1, "TOPRIGHT", "BOTTOMRIGHT" },
    }
    for side, w in pairs(want) do
        local t = A.edges[side]
        H.ok(t:IsShown(), side .. " edge shown")
        H.eq(t.__layer, "ARTWORK", side .. " over the art (BORDER)")
        local g = t.__grad
        H.ok(g and g[1] == w[1], side .. " runs " .. w[1])
        H.ok(g[2] == dark[1] and g[3] == dark[2] and g[4] == dark[3] and g[5] == w[2], side .. " min: the panel's dark")
        H.ok(g[6] == dark[1] and g[7] == dark[2] and g[8] == dark[3] and g[9] == w[3], side .. " max: the panel's dark")
        for i, pt in ipairs({ w[4], w[5] }) do
            local p, rel, rp, x, y = t:GetPoint(i)
            H.ok(p == pt and rel == A.art and rp == pt and x == 0 and y == 0, side .. " on the art's " .. pt)
        end
    end
    H.eq(A.edges.top:GetHeight(), 60)
    H.eq(A.edges.bottom:GetHeight(), 60)
    H.eq(A.edges.right:GetWidth(), 50)
    -- the Journal and stock pictures bring their own vignette: no extra edges
    ns.UI.Open("rift")
    H.eq(A.artSource, "journal")
    for side, t in pairs(A.edges) do
        H.ok(not t:IsShown(), side .. " edge hidden on Journal art")
    end
    q:SetArt(false)
    A.Show("probe")
    H.eq(A.artSource, nil)
    for side, t in pairs(A.edges) do
        H.ok(not t:IsShown(), side .. " edge hidden without art")
    end
end)

test("shell art: the Journal picture, else the stock LFG one, else none (the dark panel)", function(M, ns)
    local A = ns.Activities
    ns.UI.Open("rift")
    H.eq(A.artSource, "journal")
    H.eq(texture(A.art), "Interface\\AddOns\\Bleakhold\\Art\\Journal\\bg_EYEOFETERNITY")
    H.ok(A.art:IsShown() and A.fade:IsShown() and A.shade:IsShown(), "art, fade and shade")
    H.eq(A.fade.__grad ~= nil, true, "the fade is a gradient")
    -- the old crop of the 512 x 512 picture: 390 x 423
    local ulx, uly, llx, lly, urx = A.art:GetTexCoord()
    H.eq(urx, 0.76171875); H.eq(lly, 0.826171875)
    ns.UI.Open("heroic")
    H.eq(texture(A.art), "Interface\\AddOns\\Bleakhold\\Art\\Journal\\bg_UTGARDEPINNACLE")
    ns.UI.Open("group")
    H.eq(texture(A.art), "Interface\\AddOns\\Bleakhold\\Art\\Journal\\bg_DEADMINES")
    -- the Mythic+ page shows the keystone's dungeon
    ns.Legacy.Receive("K;289;7;1800;Scholomance")
    ns.UI.Open("keys")
    H.eq(texture(A.art), "Interface\\AddOns\\Bleakhold\\Art\\Journal\\bg_SCHOLOMANCE")
    ns.Legacy.Receive("K;575;7;1800;Utgarde Pinnacle")
    A.RefreshCurrent()
    H.eq(texture(A.art), "Interface\\AddOns\\Bleakhold\\Art\\Journal\\bg_UTGARDEPINNACLE")
end)

test("shell art: no Journal files -> the stock LFG backgrounds", function(M, ns)
    local A = ns.Activities
    ns.UI.Open("rift")
    H.eq(A.artSource, "stock")
    H.eq(texture(A.art), "Interface\\LFGFrame\\UI-LFG-BACKGROUND-MALYGOS", "the Eye of Eternity's stock name")
    ns.UI.Open("heroic")
    H.eq(texture(A.art), "Interface\\LFGFrame\\UI-LFG-BACKGROUND-UTGARDEPINNACLE")
    H.eq(ns.Journal.StockPath("ZULFARRAK"), "Interface\\LFGFrame\\UI-LFG-BACKGROUND-ZULFARAK")
    H.eq(ns.Journal.StockPath("UTGARDEKEEP"), "Interface\\LFGFrame\\UI-LFG-BACKGROUND-UTGARDE")
    H.eq(ns.Journal.StockPath("HELLFIRE"), "Interface\\LFGFrame\\UI-LFG-BACKGROUND-HELLFIRECITADEL")
    -- a stock picture is a 2:1 scene: the page art takes a slice of its middle in its own shape
    local l, t, _, b, r = A.art:GetTexCoord()
    H.ok(l > 0 and r < 1 and t == 0 and b == 1, "cut from the middle")
    H.ok(math.abs((r - l) * 2 - A.ART_W / A.ART_H) < 0.01, "in the page art's shape")
end, { before = function(M)
    setmetatable(M.missingTextures, { __index = function(_, path)
        return (type(path) == "string" and path:find("^Interface\\AddOns\\Bleakhold\\Art\\Journal\\")) and true or nil
    end })
end })

test("shell art: neither -> no picture, no fade: the dark panel", function(M, ns)
    local A = ns.Activities
    ns.UI.Open("rift")
    H.eq(A.artSource, nil)
    H.ok(not A.art:IsShown() and not A.fade:IsShown() and not A.shade:IsShown(), "nothing drawn over the panel")
    H.ok(A.content:IsVisible(), "the panel stays")
end, { before = function(M)
    setmetatable(M.missingTextures, { __index = function(_, path)
        return (type(path) == "string" and (path:find("^Interface\\AddOns\\Bleakhold\\Art\\Journal\\")
            or path:find("^Interface\\LFGFrame\\UI%-LFG%-BACKGROUND"))) and true or nil
    end })
end })

test("shell: Leave dungeon shows in a party or raid instance and asks first (.mplus leave)", function(M, ns)
    local A = ns.Activities
    FX.connect(M, H)
    ns.UI.Open("tasks")
    M.Advance(0.6)
    H.ok(not A.leave:IsShown(), "not in the open world")
    M.inInstance, M.instanceType = true, "pvp"
    M.Advance(0.6)
    H.ok(not A.leave:IsShown(), "not in a battleground")
    M.inInstance, M.instanceType = true, "party"
    M.Advance(0.6)
    H.ok(A.leave:IsVisible(), "in a dungeon")
    H.eq(A.leave.label:GetText(), "Leave dungeon")
    local _, rel = A.leave:GetPoint(1)
    H.eq(rel, A.frame.close, "beside the close button")
    local before = #saidSay(M)
    A.leave:Click()
    local p = M.popups[#M.popups]
    H.ok(p and p.which == "BLEAKHOLD_LEAVE_DUNGEON", "the stock dialog")
    H.contains(p.text, "Leave this dungeon?")
    -- the dialog's see-through background would sit on the page's title: the window goes first
    H.ok(not A.frame:IsShown(), "the window closes before the question")
    M.StaticPopupClick("BLEAKHOLD_LEAVE_DUNGEON", 2)
    H.eq(#saidSay(M), before, "No leaves nothing")
    H.ok(A.frame:IsShown(), "No brings the window back")
    H.eq(A.current, "tasks", "on the page it came from")
    ns.UI.Open("group")
    A.leave:Click()
    H.ok(not A.frame:IsShown())
    M.StaticPopupClick("BLEAKHOLD_LEAVE_DUNGEON", 1)
    local said = saidSay(M)
    H.eq(said[#said], ".mplus leave")
    H.ok(not A.frame:IsShown(), "Yes leaves it closed")
    ns.UI.Open("group")
    M.inInstance, M.instanceType = true, "raid"
    M.Advance(0.6)
    H.ok(A.leave:IsVisible(), "in a raid too")
    -- the server refuses in combat and while dead (bh_leave.cpp): greyed, the tooltip says why
    M.env.UnitAffectingCombat = function(u) return u == "player" end
    M.Advance(0.6)
    H.ok(A.leave:IsVisible() and not A.leave:IsEnabled(), "greyed in combat")
    H.contains(A.leave.tooltip()[2][1], "in combat")
    -- the greyed button still runs its motion scripts (SetMotionScriptsWhileDisabled), so hovering shows the why
    M.env.GameTooltip:Hide()
    M.Hover(A.leave)
    H.ok(M.env.GameTooltip:IsShown(), "hovering the greyed button shows its tooltip")
    H.contains(table.concat(M.env.GameTooltip.__lines, "\n"), "in combat")
    M.Hover(A.leave, false)
    M.env.UnitAffectingCombat = function() return false end
    M.env.UnitIsDeadOrGhost = function(u) return u == "player" end
    M.Advance(0.6)
    H.ok(not A.leave:IsEnabled(), "greyed while dead")
    M.env.UnitIsDeadOrGhost = function() return false end
    M.Advance(0.6)
    H.ok(A.leave:IsEnabled(), "alive and out of combat")
    -- a Journey run goes back to where it started, an Eclipse Rift floor back to Dalaran (bh_leave.cpp)
    A.leave:Click()
    H.contains(M.popups[#M.popups].text, "Dungeon Journey run takes you back")
    M.StaticPopupClick("BLEAKHOLD_LEAVE_DUNGEON", 2)
    ns.Legacy.Receive("S;4;602;7;0;0;0;0")
    A.leave:Click()
    H.eq(M.popups[#M.popups].text, "Leave the Eclipse Rift and return to Dalaran?")
end)

test("entry points: /act and /activities with the old page names, /bh pages, openers, the I key's toggle",
    function(M, ns)
    local A = ns.Activities
    local win = M.env.BleakholdActivitiesFrame
    H.eq(M.env.SLASH_BLEAKHOLDACTIVITIES1, "/act")
    H.eq(M.env.SLASH_BLEAKHOLDACTIVITIES2, "/activities")
    local act = M.env.SlashCmdList.BLEAKHOLDACTIVITIES
    act("")
    H.ok(win:IsShown(), "/act opens")
    H.eq(A.current, "dungeons", "on the Dungeon Journey, as the old window")
    act("")
    H.ok(not win:IsShown(), "and closes")
    for word, key in pairs({ journey = "dungeons", mplus = "keys", rift = "rift", heroic = "heroic", group = "group",
        tasks = "tasks", Mplus = "keys" }) do
        act(word)
        H.ok(win:IsShown() and A.current == key, "/act " .. word .. " -> " .. key)
    end
    act("heroic")
    H.ok(win:IsShown(), "a page never closes it")
    act("nonsense")
    H.ok(not win:IsShown(), "an unknown word toggles, as the old one")
    for _, key in ipairs({ "heroic", "group", "dungeons", "keys", "rift", "tasks" }) do
        M.env.SlashCmdList.BLEAKHOLD(key)
        H.ok(win:IsShown() and A.current == key, "/bh " .. key)
        win:Hide()
        H.ok(ns.UI.Open(key), "opener " .. key)
        H.eq(A.current, key)
        win:Hide()
    end
    -- Legacies and Season open their own windows
    act("legacies")
    H.ok(M.env.BleakholdCollectionsFrame:IsShown(), "Collections")
    act("season")
    H.ok(M.env.BleakholdSeasonFrame:IsShown(), "Season")
    navEntry(ns, "season"):Click()
    H.ok(M.env.BleakholdSeasonFrame:IsShown())
    -- the key binding toggles
    win:Hide()
    M.env.BleakholdToggle("activities")
    H.ok(win:IsShown())
    M.env.BleakholdToggle("activities")
    H.ok(not win:IsShown())
end)

test("entry points: /act is left to an addon that has it already; /activities still ours", function(M, ns)
    H.eq(M.env.SlashCmdList.OTHERACT, M.env.otherAct, "theirs untouched")
    H.eq(M.env.SLASH_BLEAKHOLDACTIVITIES1, "/activities")
    H.eq(M.env.SLASH_BLEAKHOLDACTIVITIES2, nil)
    M.env.SlashCmdList.BLEAKHOLDACTIVITIES("mplus")
    H.eq(ns.Activities.current, "keys")
end, { before = function(M)
    M.env.otherAct = function() end
    M.env.SLASH_OTHERACT1 = "/act"
    M.env.SlashCmdList.OTHERACT = M.env.otherAct
end })

test("entry points: opened before the handshake, the window asks the server once HELLO is answered", function(M, ns)
    -- I pressed in the first second after a login: no Bleakhold server known yet, so no '.' line may go out
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    H.eq(#saidSay(M), 0, "nothing said before the handshake")
    H.eq(ns.Dungeons.hint:GetText(), "Waiting for the server...")
    FX.connect(M, H)
    local said = saidSay(M)
    H.eq(said[1], ".act journey", "the board")
    H.eq(said[2], ".act mplus", "the keystone, the season list and the Rift")
    -- the board arrives and the page shows it
    ns.Legacy.Receive("H;3600;0;0;0;1")
    ns.Legacy.Receive("J;1001;36;0;0;1;15;0;82;845;3;120;The Deadmines;")
    M.Advance(0.3)
    H.ok(ns.Dungeons.rows[1]:IsShown(), "the board, without closing and opening the window")
    -- a later HELLO (the realm's features change) does not repeat a request made a moment ago
    local n = #saidSay(M)
    FX.connect(M, H)
    H.eq(#saidSay(M), n)
end)

test("Group Finder: the classic Dungeon Finder one click away", function(M, ns)
    ns.UI.Open("group")
    local P = ns.GroupFinder
    H.ok(P:IsVisible())
    H.contains(P.finder.label:GetText(), "classic Dungeon Finder")
    H.eq(P.finder.tooltip()[1], "Dungeon Finder")
    H.contains(P.tips:GetText(), "/join lfg")
    P.finder:Click()
    H.ok(M.env.LFDParentFrame:IsShown(), "the game's own finder")
    H.ok(not M.env.BleakholdActivitiesFrame:IsShown(), "Activities makes room")
    ns.UI.Open("group")
    P.journey:Click()
    H.eq(ns.Activities.current, "dungeons", "and the Journey's queue")
end)

test("Heroic Dungeons: the season grid in Journal tiles, Normal / Heroic / Mythic held down", function(M, ns)
    FX.connect(M, H)
    local L = ns.Legacy
    for _, msg in ipairs({ "L;289;1800;12;Scholomance", "L;575;1800;8;Utgarde Pinnacle", "L;999;1800;0;Nowhere Keep",
        "Z;0" }) do
        L.Receive(msg)
    end
    ns.UI.Open("heroic")
    M.Advance(0.3)
    local P = ns.Heroic
    H.ok(P.tiles[1]:IsShown() and P.tiles[3]:IsShown() and not P.tiles[4]:IsShown(), "three tiles")
    H.eq(P.tiles[1].name:GetText(), "Scholomance")
    H.eq(P.tiles[1].thumb.__texture, "Interface\\AddOns\\Bleakhold\\Art\\Journal\\bg_SCHOLOMANCE")
    local _, t, _, b = P.tiles[1].thumb:GetTexCoord()
    H.ok(t == 0.2 and b == 0.55, "a band of the page art (old :427)")
    H.ok(not P.tiles[3].thumb:IsShown(), "a dungeon without art keeps the dark tile")
    H.eq(P.modes[1].style, "tabOn", "Normal held")
    H.contains(P.diff:GetText(), "Current: Normal")
    P.modes[2]:Click()
    H.eq(H.lastIntent(M, "KMODE").payload, "1", "Heroic through our KMODE")
    -- the server confirms with KEY (mode 1): Heroic held, although Z says 0
    H.send(M, "KEY", { { 1, 602, 8, { 1, 3, 4 }, 1, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    H.eq(P.modes[2].style, "tabOn", "Heroic held")
    H.eq(P.modes[1].style, "tab")
    H.contains(P.diff:GetText(), "Heroic")
end)

test("Heroic Dungeons: no BHMP yet -> the key dungeons of DEF D", function(M, ns)
    FX.connect(M, H)
    H.send(M, "DEF", { { "D", 7 }, { 289, "Scholomance", 3, 38, 48, "", 1800 }, { 36, "The Deadmines", 1, 15, 21, "", 0 } })
    M.Advance(0.3)
    local list = ns.Legacy.SeasonDungeons()
    local names = {}
    for _, d in ipairs(list) do names[d.name] = true end
    H.ok(names.Scholomance, "a key dungeon")
    H.ok(not names["The Deadmines"], "not one without a time limit")
end)

test("old addons: the old Activities loaded after ours: one window, our names, the stock finder back", function(M, ns)
    local A, O = ns.Activities, ns.OldAddons
    local env = M.env
    -- what the old addon does when it loads (old :105-116, :533-536, :548-550)
    local stockToggle = env.ToggleLFDParentFrame
    local old = env.CreateFrame("Frame", "BleakholdActivitiesFrame", env.UIParent)
    old:SetScript("OnShow", function() env.oldShown = true end)
    table.insert(env.UISpecialFrames, "BleakholdActivitiesFrame")
    env.SLASH_BLEAKHOLDACTIVITIES1 = "/act"
    env.SlashCmdList.BLEAKHOLDACTIVITIES = function() env.oldSlash = true end
    M.addons.BleakholdActivities = true
    M.addons.BleakholdChat = true
    M.FireEvent("ADDON_LOADED", "BleakholdActivities")
    H.eq(env.BleakholdActivitiesFrame, A.frame, "the global name is ours again (ESC closes ours)")
    H.ok(not old:IsVisible(), "the old window is out of sight")
    old:Show()
    H.ok(not old:IsVisible() and not env.oldShown, "and stays there, its OnShow off")
    env.SlashCmdList.BLEAKHOLDACTIVITIES("mplus")
    H.ok(not env.oldSlash and A.frame:IsShown() and A.current == "keys", "/act is ours")
    -- at login the old addon put its own function in place of the Dungeon Finder's
    old.origLFD = stockToggle
    env.ToggleLFDParentFrame = function() env.oldToggle = true end
    M.FireEvent("PLAYER_ENTERING_WORLD")
    H.eq(env.ToggleLFDParentFrame, stockToggle, "the game's own Dungeon Finder again")
    -- the question, once per character
    M.Advance(O.ASK_AFTER + 0.5)
    local p = M.popups[#M.popups]
    H.ok(p and p.which == "BLEAKHOLD_OLD_ADDONS", "the stock dialog asks")
    H.contains(p.text, "These are now built into Bleakhold")
    H.contains(p.text, "BleakholdActivities, BleakholdChat")
    H.eq(env.StaticPopupDialogs.BLEAKHOLD_OLD_ADDONS.button1, "Turn off")
    M.StaticPopupClick("BLEAKHOLD_OLD_ADDONS", 1)
    H.eq(table.concat(M.disabledAddons, ","), "BleakholdActivities,BleakholdChat", "both turned off")
    H.eq(M.reloads, 1, "and the interface reloads")
    H.ok(env.BleakholdCharDB.oldAddonsAsked, "asked: kept per character")
    local n = #M.popups
    M.FireEvent("PLAYER_ENTERING_WORLD")
    M.Advance(O.ASK_AFTER + 0.5)
    H.eq(#M.popups, n, "not asked again")
    env.SlashCmdList.BLEAKHOLD("oldaddons")
    H.eq(#M.popups, n + 1, "/bh oldaddons asks again")
    M.StaticPopupClick("BLEAKHOLD_OLD_ADDONS", 2)
    H.eq(M.reloads, 1, "Not now changes nothing")
end)

test("old addons: the old Activities loaded first: its window parked, ours under the name", function(M, ns)
    local env = M.env
    H.ok(env.oldFirst ~= env.BleakholdActivitiesFrame, "ours took the name")
    H.eq(env.BleakholdActivitiesFrame, ns.Activities.frame)
    H.ok(not env.oldFirst:IsVisible(), "the old one is parked")
    M.Advance(ns.OldAddons.ASK_AFTER + 0.5)
    H.ok(#M.popups == 1 and M.popups[1].text:find("BleakholdActivities", 1, true), "and the question comes")
end, { before = function(M)
    M.env.oldFirst = M.env.CreateFrame("Frame", "BleakholdActivitiesFrame", M.env.UIParent)
    M.addons.BleakholdActivities = true
end })

test("old addons: BleakholdUI is turned off only while AddicatUI, which replaces it, is loaded", function(M, ns)
    local O = ns.OldAddons
    M.addons.BleakholdUI = true
    M.addons.BleakholdChat = true
    M.Advance(O.ASK_AFTER + 0.5)
    local p = M.popups[#M.popups]
    H.ok(p and p.which == "BLEAKHOLD_OLD_ADDONS", "asked about the chat copy")
    H.ok(not p.text:find("BleakholdUI", 1, true), "but BleakholdUI is not listed: " .. p.text)
    M.StaticPopupClick("BLEAKHOLD_OLD_ADDONS", 1)
    H.eq(table.concat(M.disabledAddons, ","), "BleakholdChat", "BleakholdUI stays on")
    -- only BleakholdUI: no question at all, and /bh oldaddons says why
    M.addons.BleakholdChat = nil
    local n = #M.popups
    M.env.SlashCmdList.BLEAKHOLD("oldaddons")
    H.eq(#M.popups, n, "no question")
    local said = false
    for _, c in ipairs(M.chat) do
        if c.msg and c.msg:find("BleakholdUI stays on", 1, true) then said = true end
    end
    H.ok(said, "says it stays on")
    -- with AddicatUI loaded it is replaced
    M.addons.AddicatUI = true
    H.eq(table.concat(O.Loaded(), ","), "BleakholdUI")
    M.env.SlashCmdList.BLEAKHOLD("oldaddons")
    H.contains(M.popups[#M.popups].text, "BleakholdUI")
end)

test("old addons: an old BleakholdChat left on does not replace our whisper-target handling", function(M, ns)
    local env = M.env
    local ours = ns.Chat.ExtractTellTarget
    H.eq(env.ChatEdit_ExtractTellTarget, ours, "Chat.lua's is in place")
    -- what the old copy does when it loads after us (old BleakholdChat.lua :53-62): its own split, ours never called
    local function oldSplit(editBox, msg)
        env.oldSplitRan = true
        return false
    end
    env.ChatEdit_ExtractTellTarget = oldSplit
    M.addons.BleakholdChat = true
    M.FireEvent("ADDON_LOADED", "BleakholdChat")
    H.eq(env.ChatEdit_ExtractTellTarget, ours, "ours again at its ADDON_LOADED")
    -- and again at login, should the old copy put its own back later ("Not now" keeps it on)
    env.ChatEdit_ExtractTellTarget = oldSplit
    M.FireEvent("PLAYER_ENTERING_WORLD")
    H.eq(env.ChatEdit_ExtractTellTarget, ours, "ours again after PLAYER_ENTERING_WORLD")
    -- a one-word name is still a one-word name ("/w Thrall hi there" whispers Thrall), through the stock fallback
    local box = { attr = {} }
    function box:SetAttribute(k, v) self.attr[k] = v end
    function box:GetAttribute(k) return self.attr[k] end
    function box:SetText(t) self.text = t end
    H.eq(env.ChatEdit_ExtractTellTarget(box, "Thrall hi there"), true)
    H.eq(box:GetAttribute("tellTarget"), "Thrall", "not 'Thrall hi'")
    H.eq(box.text, "hi there")
    H.ok(not env.oldSplitRan, "the old split never ran")
end)

test("old addons: an old BleakholdUI next to AddicatUI: its /bhui runs AddicatUI's command", function(M, ns)
    local env = M.env
    local function run() end
    env.AddicatUI = { BleakholdCommands = { Run = run } }
    M.addons.AddicatUI = true
    -- the old addon's command (old BleakholdUI.lua :614)
    local function oldBhui() env.oldBhuiRan = true end
    env.SLASH_BLEAKHOLDUI1 = "/bhui"
    env.SlashCmdList.BLEAKHOLDUI = oldBhui
    M.addons.BleakholdUI = true
    M.FireEvent("ADDON_LOADED", "BleakholdUI")
    H.eq(env.SlashCmdList.BLEAKHOLDUI, run, "the old entry runs AddicatUI's /bhui")
    env.SlashCmdList.BLEAKHOLDUI = oldBhui
    M.FireEvent("PLAYER_ENTERING_WORLD")
    H.eq(env.SlashCmdList.BLEAKHOLDUI, run, "again after PLAYER_ENTERING_WORLD")
    -- without AddicatUI the old copy is the interface: its command stays its own
    M.addons.AddicatUI = nil
    env.SlashCmdList.BLEAKHOLDUI = oldBhui
    M.FireEvent("PLAYER_ENTERING_WORLD")
    H.eq(env.SlashCmdList.BLEAKHOLDUI, oldBhui, "kept while AddicatUI is off")
end)

test("old addons: none loaded: no question, nothing touched", function(M, ns)
    M.Advance(ns.OldAddons.ASK_AFTER + 0.5)
    H.eq(#M.popups, 0)
    H.eq(ns.OldAddons.parked, nil)
    M.env.SlashCmdList.BLEAKHOLD("oldaddons")
    H.eq(#M.popups, 0)
    local said = false
    for _, c in ipairs(M.chat) do
        if c.msg and c.msg:find("No old Bleakhold addons", 1, true) then said = true end
    end
    H.ok(said, "says so")
end)
