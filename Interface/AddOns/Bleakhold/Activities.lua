-- Bleakhold: the Activities window, rebuilt in the old BleakholdActivities window's look and proportions (old
-- BleakholdActivities.lua :105-192, the owner's reference screenshot) from the client's own art (Widgets.lua): the
-- dialog frame with a ring portrait that shows the open page's icon and the page's gold title in the dark title bar;
-- the nav panel on the left (ring icons and labels, the open page lit blue); the content panel with the page's dungeon
-- picture on the right, fading into the dark (JournalArt.lua). Inside a party or raid instance the title bar has
-- "Leave dungeon" (the stock dialog, then .mplus leave: Legacy.lua).
--
-- Nav (PLAN 3): Dungeon Journey, Mythic+ Dungeons, Eclipse Rift, Heroic Dungeons, Group Finder; Bleakhold Royale,
-- War Mode and Arena while the realm runs them (HELLO feature bits 4096, 16384, 65536: an entry's available()); then
-- Tasks, Legacies (Collections' Legacy Sets tab) and Season (its own window). The rows keep the old 70 px pitch while
-- every live entry fits and close up when they do not (A.LayoutNav): all eleven fit.
--
-- Pages: Dungeons.lua, Keys.lua, Rift.lua, Heroic.lua, GroupFinder.lua, Royale.lua, WarMode.lua and Arena.lua add
-- theirs; the Tasks page is below (era banner, daily task cards, weekly tasks, your week, and the kill announcer's
-- settings while the realm runs it, HELLO feature bit 8192). Two kinds:
--   A.Page(key, spec)   a page in the old anatomy (old :177-192), covering the content panel (A.CW x A.CH):
--       p.title               gold 22 at (A.PAD, -18): spec.title, else the nav entry's label
--       p.desc                white 12, A.DESC_W wide, 3 px leading, at (A.PAD, -50): spec.desc
--       p:Stat(i, label)      the right-hand stat column: a gold 12 label with a white 15 value under it, right-aligned,
--                             A.STAT_PITCH apart; returns the value FontString (value.label is the label)
--       p:Section(text, x, y) a gold 14 heading at (x, y): default (A.PAD, A.BODY_Y), the old pages' first section
--       the art               spec.art: a JournalArt key ("SCHOLOMANCE"), a function(page) answering one, a table
--                             { file = path, coords = { l, r, t, b } } for art of the addon's own, or false for none;
--                             default the nav entry's. spec.artAlpha (default 1). p:SetArt(art, alpha) changes both.
--     A.Page on a key that has an anatomy page already returns that page (title, text and art set again from spec
--     where given), so a file can add to a page another one started.
--   A.NewPage() + A.AddPage(key, page)  a plain body of A.PW x A.PH inside the content panel (the pages of the earlier
--     design; the nav entry's art shows behind them)
-- Either kind may have Refresh (on open and when STATE or the legacy messages change), OnOpen, Tick (every second
-- while open) and Available (false keeps it closed: A.Show opens Tasks instead).
--
-- Entry points: the I key (A.OfferDefaultKey below), /act and /activities [page] (the old addon's commands, registered
-- when free; old page names work: journey, mplus, ...), /bh [activities|tasks|dungeons|keys|rift|heroic|group], the
-- launcher flyout (Integration.lua), the server's "A;<page>" at the first login (Legacy.lua), UI.Open(key) and
-- BleakholdToggle (Bindings.xml).
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S

local floor, max, min = math.floor, math.max, math.min

local A = {}
ns.Activities = A

-- The old window was 940 x 620 for five nav rows and 678 px pages. 1080 x 680 keeps its look with room for eleven
-- rows, and keeps the plain pages' body (A.PW) as wide as they were laid out (788).
A.W, A.H = 1080, 680
A.TOP, A.EDGE = 46, 18                          -- panels start 46 down and stop 18 from the edges (old :140, :167)
A.NAV_X, A.NAV_W = 18, 216                      -- the nav panel (old :140)
A.NAV_H = A.H - A.TOP - A.EDGE
A.ROW_W, A.NAV_PAD, A.NAV_GAP = 204, 6, 4       -- its rows: 204 wide, 6 in from the panel, 4 apart (old :153)
A.NAV_PITCH = 70                                -- the old pitch (66 px rows), kept while every live entry fits
A.RING = 50                                     -- the old nav ring
A.CONTENT_X = 244                               -- the content panel (old :167)
A.CW, A.CH = A.W - A.CONTENT_X - A.EDGE, A.H - A.TOP - A.EDGE
A.PAD, A.DESC_W, A.STAT_PITCH, A.BODY_Y = 20, 390, 46, -122   -- the page anatomy (old :177-192)
A.MAIN_X, A.MAIN_TOP, A.MAIN_BOTTOM = 15, 14, 12              -- the plain page body inside the content panel
A.PW = A.CW - 2 * A.MAIN_X
A.PH = A.CH - A.MAIN_TOP - A.MAIN_BOTTOM
A.ART_W, A.ART_H = floor((A.CH - 10) * 390 / 423), A.CH - 10    -- the page art: the old crop's shape (old :169)
A.FADE_W = 260
A.pages = {}
A.order = {}
A.current = nil
A.DEFAULT = "dungeons"                          -- the old window opened on the Dungeon Journey

local win = UI.Window("BleakholdActivitiesFrame", A.W, A.H, "Activities",
    "Interface\\Icons\\Achievement_Dungeon_ClassicDungeonMaster",
    { openSound = "AchievementMenuOpen", closeSound = "AchievementMenuClose" })
A.frame = win

------------------------------------------------------------------------------------------------------
-- Nav entries. label: the nav row; title: the title bar (the old window's own for its five pages, else the label);
-- icon: an Interface\Icons picture for the row's ring and the portrait (the old window's for its five pages);
-- art: the page's picture (see A.Page); available: a test that leaves the entry out of the nav while it says no.
------------------------------------------------------------------------------------------------------
local function journeyArt()
    local L = ns.Legacy
    local o = L and L.journey.offers[1]
    return (o and ns.Journal.Key(o.name)) or "STRATHOLME"
end

-- the keystone's dungeon: our KEY's when it has one, else the old K's
local function keyArt()
    local name
    if S.key and S.key.hasKey and S.key.dungeonId then
        name = ns.DefName("D", S.key.dungeonId)
    end
    local k = ns.Legacy and ns.Legacy.mplus.key
    if not name and k then
        name = k.name
    end
    return (name and ns.Journal.Key(name)) or "SCHOLOMANCE"
end

local navDefs = {
    { key = "dungeons", label = "Dungeon Journey", title = "Dungeon Finder",
      icon = "Achievement_Dungeon_ClassicDungeonMaster", art = journeyArt },
    { key = "keys", label = "Mythic+ Dungeons", icon = "Spell_Holy_BorrowedTime", art = keyArt },
    { key = "rift", label = "Eclipse Rift", title = "Enter the Eclipse Rift", icon = "Ability_Druid_EclipseOrange",
      art = "EYEOFETERNITY" },
    { key = "heroic", label = "Heroic Dungeons", icon = "Achievement_Dungeon_HEROIC_GloryoftheRaider",
      art = "UTGARDEPINNACLE" },
    { key = "group", label = "Group Finder", icon = "INV_Misc_GroupNeedMore", art = "DEADMINES" },
    { key = "royale", label = "Bleakhold Royale", icon = "Achievement_BG_KillXEnemies_GeneralsRoom", art = false,
      available = function()
          return ns.Royale ~= nil and ns.Royale.Live()
      end },
    { key = "warmode", label = "War Mode", icon = "Achievement_BG_winWSG", art = "HELLFIRE", artAlpha = 0.45,
      available = function()
          return ns.WarMode ~= nil and ns.WarMode.Live()
      end },
    { key = "arena", label = "Arena", icon = "Achievement_Arena_2v2_7", art = "BLACKROCKDEPTHS", artAlpha = 0.45,
      available = function()
          return ns.Arena ~= nil and ns.Arena.Live()
      end },
    { key = "tasks", label = "Tasks", icon = "Achievement_Quests_Completed_Daily_08", art = "SHADOWFANGKEEP",
      artAlpha = 0.45 },
    { key = "legacies", label = "Legacies", icon = "INV_Chest_Plate16" },
    { key = "season", label = "Season", icon = "Achievement_Reputation_ArgentChampion" },
}
A.NAV = navDefs
local navByKey = {}
for _, d in ipairs(navDefs) do
    navByKey[d.key] = d
end
A.navByKey = navByKey

-- The old window's page names (/act <page>, the server's A;<page>) and a few other words for the pages.
A.ALIASES = { journey = "dungeons", dungeon = "dungeons", board = "dungeons", mplus = "keys", ["m+"] = "keys",
    key = "keys", mythic = "keys", heroics = "heroic", finder = "group", lfg = "group", groupfinder = "group",
    task = "tasks", legacy = "legacies", pvp = "warmode", ["1v1"] = "arena" }

function A.Resolve(page)
    page = type(page) == "string" and page:lower() or nil
    return page and (A.ALIASES[page] or page) or nil
end

------------------------------------------------------------------------------------------------------
-- Title bar: the page's title (UI.Window's), the daily and weekly reset on the Tasks page, Leave dungeon
------------------------------------------------------------------------------------------------------
local dailyPill = UI.Pill(win.header, "", C.dim, 11)
dailyPill:SetPoint("LEFT", win.bar, "LEFT", 10, 0)
local weeklyPill = UI.Pill(win.header, "", C.dim, 11)
weeklyPill:SetPoint("LEFT", dailyPill, "RIGHT", 14, 0)
A.resetTexts = { dailyPill, weeklyPill }

function A.ResetTexts()
    local s = Comm.server or {}
    local now = Comm.ServerTime()
    local daily, weekly
    if s.dailyReset then
        daily = "Daily reset  " .. U.Duration(s.dailyReset - now)
    else
        daily = "Daily reset  -"
    end
    if s.weeklyReset then
        local offset = (s.utcOffsetMin or 0) * 60
        weekly = "Weekly reset  " .. (U.Date("!%a %H:%M", s.weeklyReset + offset) or "-")
    else
        weekly = "Weekly reset  -"
    end
    return daily, weekly
end

local resetAsked = 0
local function updateHeader()
    local onTasks = A.current == "tasks"
    for _, p in ipairs(A.resetTexts) do
        if onTasks then
            p:Show()
        else
            p:Hide()
        end
    end
    if onTasks then
        local daily, weekly = A.ResetTexts()
        dailyPill:SetValue(daily)
        weeklyPill:SetValue(weekly)
    end
    -- after a reset passes, fetch the new day once
    local s = Comm.server or {}
    if s.dailyReset and Comm.ServerTime() >= s.dailyReset and GetTime() - resetAsked > 60 and Comm.ready then
        resetAsked = GetTime()
        Comm.Refresh("TASKS")
        Comm.Refresh("WEEK")
        Comm.Refresh("ERA")
    end
end

-- Leave dungeon (old :118-130): inside a party or raid instance; greyed while dead or in combat, as the server refuses
-- then (bh_leave.cpp LeaveDungeon); the dialog says where it goes (Legacy.LeaveText: the Eclipse Rift has its own
-- exit). The window closes before the question: the stock dialog (at TOP -135, a see-through
-- background) would sit on the page's title and text. No reopens it on the same page (Legacy.lua's OnCancel).
local leave = UI.Button(win.header, 110, 22, "Leave dungeon", "red", 12)
leave:SetPoint("RIGHT", win.close, "LEFT", -2, 0)
leave:SetFrameLevel(win.close:GetFrameLevel())
leave:SetScript("OnClick", function()
    win:Hide()
    ns.Legacy.ConfirmLeave()
end)
leave:Hide()
A.leave = leave
leave.tooltip = function()
    local why = A.LeaveBlock()
    return { "Leave dungeon", { why or "Leave this dungeon (you are asked first).", why and C.orange or C.text, true } }
end

function A.InDungeon()
    local inInstance, kind = IsInInstance()
    return (inInstance and (kind == "party" or kind == "raid")) and true or false
end

-- In a Dungeon Finder group (GetLFGInfoServer's first value, which FrameXML's GetLFGMode reads as "lfgparty"): the
-- server lets it enter only its own dungeon (bh_dungeon.cpp CanLaunch, bh_rift.cpp RiftEnter), never on Mythic
-- (bh_mplus.cpp SetDifficulty).
function A.InDungeonFinderGroup()
    if not GetLFGInfoServer then
        return false
    end
    local inParty = GetLFGInfoServer()
    return inParty and true or false
end

-- The Bleakhold Royale or the 1v1 arena queue the player is in (our QUEUE, kind B or A), worded as the bridge refuses a
-- QJOIN then (bh_ui_bridge.cpp OnQueueJoin), or nil. The old commands a page sends (.act start, .rift enter) never
-- check these queues, and a player taken into a dungeon or a Rift floor drops out of the Royale queue at its proposal
-- (bh_royale_queue.cpp Recheck), so the pages refuse first. Queued or proposed (states 1 and 2): in the match (3) the
-- player is inside its battleground or arena, which the pages' instance rule words.
function A.OtherQueueBlock()
    local q = S.queue
    if not q or (q.state ~= 1 and q.state ~= 2) then
        return nil
    end
    if q.kind == "B" then
        return "You are in the Bleakhold Royale queue. Leave it first."
    elseif q.kind == "A" then
        return "You are in the 1v1 arena queue. Leave it first."
    end
    return nil
end

-- What keeps the server from taking the player out now, or nil: alive and out of combat (bh_leave.cpp).
function A.LeaveBlock()
    if UnitIsDeadOrGhost and UnitIsDeadOrGhost("player") then
        return "Release your spirit first."
    end
    if UnitAffectingCombat and UnitAffectingCombat("player") then
        return "You cannot leave while you are in combat."
    end
    return nil
end

function A.UpdateLeave()
    if A.InDungeon() then
        leave:SetActive(A.LeaveBlock() == nil)
        leave:Show()
    else
        leave:Hide()
    end
end

------------------------------------------------------------------------------------------------------
-- The nav panel and the content panel (the old panelBox: the tooltip frame, tinted dark)
------------------------------------------------------------------------------------------------------
local nav = UI.Box(win, A.NAV_W, A.NAV_H, C.panel, C.border, nil, "panel")
nav:SetPoint("TOPLEFT", win, "TOPLEFT", A.NAV_X, -A.TOP)
A.navPanel = nav

local content = UI.Box(win, A.CW, A.CH, C.panel, C.border, nil, "panel")
content:SetPoint("TOPLEFT", win, "TOPLEFT", A.CONTENT_X, -A.TOP)
A.content = content

-- The page's picture on the right, 5 px inside the panel's edge, in the old crop's shape (390 x 423), dimmed a little;
-- a 260 px fade from the panel's dark over its left part, and the same dark, solid, left of it (old :169-175).
local art = content:CreateTexture(nil, "BORDER")
art:SetPoint("TOPRIGHT", content, "TOPRIGHT", -5, -5)
art:SetSize(A.ART_W, A.ART_H)
art:SetVertexColor(0.85, 0.82, 0.8)
local fade = content:CreateTexture(nil, "ARTWORK")
fade:SetTexture(UI.STOCK.white)
fade:SetPoint("TOPLEFT", art, "TOPLEFT", 0, 0)
fade:SetPoint("BOTTOMLEFT", art, "BOTTOMLEFT", 0, 0)
fade:SetWidth(A.FADE_W)
fade:SetGradientAlpha("HORIZONTAL", 0.02, 0.02, 0.04, 1, 0.02, 0.02, 0.04, 0)
local shade = content:CreateTexture(nil, "ARTWORK")
shade:SetTexture(UI.STOCK.white)
shade:SetPoint("TOPLEFT", content, "TOPLEFT", 5, -5)
shade:SetPoint("BOTTOMRIGHT", fade, "BOTTOMLEFT", 0, 0)
shade:SetVertexColor(0.02, 0.02, 0.04, 1)
A.art, A.fade, A.shade = art, fade, shade

-- The addon's own pictures (an { file, coords } spec, e.g. the Royale island) have no vignette of their own, unlike the
-- Journal and stock LFG ones: 60 px fades at the top and bottom and 50 px at the right melt them into the dark too.
local function artEdge(point, relPoint, w, h, orient, a1, a2)
    local t = content:CreateTexture(nil, "ARTWORK")
    t:SetTexture(UI.STOCK.white)
    t:SetPoint(point, art, point, 0, 0)
    t:SetPoint(relPoint, art, relPoint, 0, 0)
    if w then
        t:SetWidth(w)
    else
        t:SetHeight(h)
    end
    t:SetGradientAlpha(orient, 0.02, 0.02, 0.04, a1, 0.02, 0.02, 0.04, a2)
    t:Hide()
    return t
end
A.edges = {
    top = artEdge("TOPLEFT", "TOPRIGHT", nil, 60, "VERTICAL", 0, 1),            -- dark at the top
    bottom = artEdge("BOTTOMLEFT", "BOTTOMRIGHT", nil, 60, "VERTICAL", 1, 0),   -- dark at the bottom
    right = artEdge("TOPRIGHT", "BOTTOMRIGHT", 50, nil, "HORIZONTAL", 0, 1),     -- dark at the right
}

-- The plain page body (A.NewPage), inside the content panel.
local main = CreateFrame("Frame", nil, content)
main:SetPoint("TOPLEFT", content, "TOPLEFT", A.MAIN_X, -A.MAIN_TOP)
main:SetPoint("BOTTOMRIGHT", content, "BOTTOMRIGHT", -A.MAIN_X, A.MAIN_BOTTOM)
A.main = main

-- Strip for server errors and the out-of-date notice (over the bottom of the page, hidden when empty).
local strip = UI.Box(content, 10, 26, "3A1F1F", C.red, 0.95)
strip:SetPoint("BOTTOMLEFT", main, "BOTTOMLEFT", 0, 0)
strip:SetPoint("BOTTOMRIGHT", main, "BOTTOMRIGHT", 0, 0)
strip:SetFrameLevel(main:GetFrameLevel() + 20)
strip.text = UI.Text(strip, 12, C.text, "body", "CENTER")
strip.text:SetPoint("CENTER")
strip:Hide()
A.strip = strip

function A.ShowStrip(text, seconds)
    UI.SetText(strip.text, text)
    strip:Show()
    strip.hideAt = seconds and (GetTime() + seconds) or nil
end

------------------------------------------------------------------------------------------------------
-- Pages
------------------------------------------------------------------------------------------------------
function A.AddPage(key, page)
    page:SetParent(main)
    page:ClearAllPoints()
    page:SetPoint("TOPLEFT", main, "TOPLEFT", 0, 0)
    page:SetSize(A.PW, A.PH)
    page:Hide()
    A.pages[key] = page
end

function A.NewPage()
    local p = CreateFrame("Frame", nil, main)
    p:SetSize(A.PW, A.PH)
    return p
end

-- The right-hand stat column (old :184-188): a gold label, a white value with an outline under it, right-aligned,
-- A.STAT_PITCH apart from the top right. Returns the value (value.label is the label).
local function pageStat(p, i, label)
    local l = UI.Label(p, label, 12)
    l:SetJustifyH("RIGHT")
    l:SetPoint("TOPRIGHT", p, "TOPRIGHT", -A.PAD, -A.PAD - (i - 1) * A.STAT_PITCH)
    local v = UI.Text(p, 15, C.text, "body", "RIGHT")
    v:SetFont(UI.FONT_BODY, 15, "OUTLINE")
    v:SetPoint("TOPRIGHT", l, "BOTTOMRIGHT", 0, -3)
    v.label = l
    return v
end

-- A gold section heading (old :189-192) at x, y of the page.
local function pageSection(p, text, x, y)
    local t = UI.Heading(p, text, 14)
    t:SetPoint("TOPLEFT", p, "TOPLEFT", x or A.PAD, y or A.BODY_Y)
    return t
end

local function pageSetArt(p, a, alpha)
    p.art, p.artAlpha = a, alpha
    if A.current == p.key then
        A.UpdateArt()
    end
end

function A.Page(key, spec)
    spec = spec or {}
    local def = navByKey[key]
    local p = A.pages[key]
    if not (p and p.anatomy) then
        if p then
            p:Hide()
        end
        p = CreateFrame("Frame", nil, content)
        p:SetAllPoints(content)
        p:Hide()
        p.key = key
        p.anatomy = true
        p.title = UI.Text(p, 22, C.gold)
        p.title:SetPoint("TOPLEFT", p, "TOPLEFT", A.PAD, -18)
        p.title:SetText((def and def.label) or "")
        p.desc = UI.Para(p, 12, C.text, A.DESC_W)
        p.desc:SetPoint("TOPLEFT", p, "TOPLEFT", A.PAD, -50)
        p.Stat = pageStat
        p.Section = pageSection
        p.SetArt = pageSetArt
        A.pages[key] = p
    end
    if spec.title then
        p.title:SetText(spec.title)
    end
    if spec.desc then
        p.desc:SetText(spec.desc)
    end
    if spec.descWidth then
        p.desc:SetWidth(spec.descWidth)
    end
    if spec.art ~= nil then
        p.art = spec.art
    end
    if spec.artAlpha ~= nil then
        p.artAlpha = spec.artAlpha
    end
    return p
end

-- What a page's art is: its own (A.Page's spec.art, p:SetArt), else its nav entry's; a function is asked. Answers a
-- JournalArt key, an { file, coords } table, or nil for none.
function A.ArtOf(key)
    local page, def = A.pages[key or ""], navByKey[key or ""]
    local spec = page and page.art
    if spec == nil then
        spec = def and def.art
    end
    if type(spec) == "function" then
        local ok, v = pcall(spec, page)
        spec = ok and v or nil
    end
    if type(spec) == "string" or (type(spec) == "table" and type(spec.file) == "string") then
        return spec
    end
    return nil
end

function A.UpdateArt()
    local spec = A.ArtOf(A.current)
    local src
    if type(spec) == "table" then
        art:SetTexture(spec.file)
        art:SetTexCoord(unpack(spec.coords or { 0, 1, 0, 1 }))
        art:Show()
        src = "own"
    elseif spec then
        src = ns.Journal.Set(art, spec, "bg", A.ART_W, A.ART_H)
    end
    if src then
        local page, def = A.pages[A.current or ""], navByKey[A.current or ""]
        local alpha = page and page.artAlpha
        if alpha == nil then
            alpha = def and def.artAlpha
        end
        art:SetAlpha(alpha or 1)
        fade:Show()
        shade:Show()
    else
        art:Hide()
        fade:Hide()
        shade:Hide()
    end
    for _, t in pairs(A.edges) do
        if src == "own" then
            t:Show()
        else
            t:Hide()
        end
    end
    A.artKey, A.artSource = src and spec or nil, src
end

function A.Show(key)
    key = A.Resolve(key)
    if key == "legacies" then
        UI.Open("collections-legacy")
        return
    elseif key == "season" then
        UI.Open("season")
        return
    end
    local page = A.pages[key or ""]
    if not page or (page.Available and not page.Available()) then
        key = "tasks"
        page = A.pages.tasks
    end
    A.current = key
    for k, p in pairs(A.pages) do
        if k == key then
            p:Show()
        else
            p:Hide()
        end
    end
    for _, b in ipairs(A.nav) do
        b:SetStyle(b.key == key and "tabOn" or "tab")
    end
    local def = navByKey[key]
    UI.SetText(win.title, def and (def.title or def.label) or "Activities")
    win:SetIcon(def and def.icon or "star")
    A.UpdateArt()
    updateHeader()
    ns.cdb.activitiesTab = key
    if page and page.OnOpen then
        ns.SafeCall(page.OnOpen, page)
    end
    if page and page.Refresh then
        ns.SafeCall(page.Refresh, page)
    end
    if not win:IsShown() then
        win:Show()
    end
end

------------------------------------------------------------------------------------------------------
-- Nav rows (the old window's: a ring icon and the label, the open page lit blue; UI.IconButton draws them)
------------------------------------------------------------------------------------------------------
A.nav = {}
for i, d in ipairs(navDefs) do
    local b = UI.IconButton(nav, A.ROW_W, A.NAV_PITCH - A.NAV_GAP, d.icon, d.label, "tab")
    b.key = d.key
    b.available = d.available
    b.def = d
    b:SetPoint("TOPLEFT", nav, "TOPLEFT", A.NAV_PAD, -A.NAV_PAD - (i - 1) * A.NAV_PITCH)
    b:SetScript("OnClick", function()
        if PlaySound then
            PlaySound("igCharacterInfoTab")
        end
        A.Show(d.key)
    end)
    A.nav[i] = b
end

-- Stack the entries without gaps, leaving out the ones whose available() says no: at the old 70 px pitch while they
-- fit, closer when they do not, with the ring 12 px under the row's height (the old one: 50 on a 66 px row).
function A.LayoutNav()
    local list = {}
    for _, b in ipairs(A.nav) do
        if not b.available or b.available() then
            list[#list + 1] = b
        else
            b:Hide()
        end
    end
    local room = A.NAV_H - 2 * A.NAV_PAD + A.NAV_GAP
    local pitch = min(A.NAV_PITCH, floor(room / max(1, #list)))
    local h = pitch - A.NAV_GAP
    for i, b in ipairs(list) do
        b:SetHeight(h)
        b:SetRingSize(min(A.RING, h - 12))
        b:ClearAllPoints()
        b:SetPoint("TOPLEFT", nav, "TOPLEFT", A.NAV_PAD, -A.NAV_PAD - (i - 1) * pitch)
        b:Show()
    end
    A.navPitch, A.navCount = pitch, #list
end
A.LayoutNav()

------------------------------------------------------------------------------------------------------
-- Tasks page, in the old window's page anatomy (A.Page): the title and what tasks are; your week in the stat column
-- under a gold heading, the weekly bonus in a tooltip panel under it; the week's era as the old pages' keystone block
-- (its ring portrait, name and text, the affix icons with the level each starts at, next week's era); gold section
-- headings over the three daily tasks (tooltip panels: the achievement progress bar, the reward as quest rewards show
-- it, Claim) and the weekly ones (rows; the heading only while there are some: the bridge's TASKS carries the Dungeon
-- Journey's three daily bounties, paid in Shards, and no weekly task), then the kill announcer's settings (moved up
-- when there is no weekly task); Find a group bottom right. A dense
-- page: its picture (the nav entry's) shows at low alpha. The daily and weekly resets are in the title bar (above).
------------------------------------------------------------------------------------------------------
local P = A.Page("tasks", {
    title = "Tasks",
    desc = "Three Dungeon Journey bounties a day, new at the daily reset. Each pays Dungeon Shards the moment it is "
        .. "done.",
})
A.tasksPage = P

local ASIDE = 190                                   -- the stat column and the weekly bonus
local LEFT = A.CW - 2 * A.PAD - ASIDE - 18          -- the tasks
local ERA_Y, DAILY_Y, WEEKLY_Y, ANN_Y = -100, -180, -352, -524

-- The week's era (the old pages' keystone block): ring portrait, name and text, the affixes, next week's era
local era = CreateFrame("Frame", nil, P)
era:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD, ERA_Y)
era:SetSize(LEFT, 64)
era.badge = UI.Badge(era, 48, "flame")
era.badge:SetPoint("TOPLEFT", era, "TOPLEFT", -2, 2)
era.label = UI.Text(era, 11, C.dim)
era.label:SetPoint("TOPLEFT", era, "TOPLEFT", 58, -1)
era.label:SetText("Active Era This Week")
era.name = UI.Text(era, 16, C.text)
era.name:SetPoint("TOPLEFT", era.label, "BOTTOMLEFT", 0, -3)
UI.OneLine(era.name, LEFT - 190)
era.text = UI.Text(era, 11, C.dim)
era.text:SetPoint("TOPLEFT", era.name, "BOTTOMLEFT", 0, -3)
era.text:SetWidth(LEFT - 200)
era.text:SetHeight(28)
era.text:SetJustifyV("TOP")
era.next = UI.Text(era, 11, C.dim, "body", "RIGHT")
era.next:SetPoint("TOPRIGHT", era, "TOPRIGHT", 0, -48)
UI.OneLine(era.next, 180)
-- the week's affixes as the old window showed them: spell icons with the level each starts at (+2, +4, ...)
era.affixes = {}
for i = 1, 4 do
    local a = UI.AffixIcon(era, 26)
    a:Hide()
    era.affixes[i] = a
end
P.era = era

-- Daily tasks
local dailyTitle = P:Section("Daily Tasks", A.PAD, DAILY_Y)
local reroll = UI.Button(P, 150, 20, "Reroll one", "ghost", 10)
reroll:SetPoint("TOPRIGHT", P, "TOPLEFT", A.PAD + LEFT, DAILY_Y + 2)
P.reroll = reroll
P.dailyTitle = dailyTitle

-- a daily task: title, the achievement progress bar with "14 / 20" in it, the text, and its reward as quest rewards
-- show one (icon and name); a finished task shows the check and "Complete" in green instead of the bar
local CARD_W = floor((LEFT - 20) / 3)
local CARD_H = 136
local CARD_BAR_W = min(170, CARD_W - 24)
P.cards = {}
for i = 1, 3 do
    local c = UI.Box(P, CARD_W, CARD_H, C.card, C.border, nil, "panel")
    c:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD + (i - 1) * (CARD_W + 10), DAILY_Y - 22)
    c.title = UI.Text(c, 13, C.text)
    c.title:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -12)
    UI.OneLine(c.title, CARD_W - 44)
    c.bar = UI.Bar(c, CARD_BAR_W, 14)
    c.bar:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -37)
    c.check = UI.Check(c, 20)
    c.check:SetPoint("TOPRIGHT", c, "TOPRIGHT", -8, -8)
    c.check:Hide()
    c.complete = UI.Text(c, 12, C.teal)
    c.complete:SetPoint("LEFT", c.bar, "LEFT", 0, 0)
    c.complete:SetText("Complete")
    c.complete:Hide()
    c.text = UI.Text(c, 11, C.text)
    c.text:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -60)
    c.text:SetWidth(CARD_W - 22)
    c.text:SetJustifyV("TOP")
    c.text:SetHeight(30)
    c.claim = UI.Button(c, min(150, CARD_W - 24), 22, "Claim", "red", 12)
    c.claim:SetPoint("BOTTOM", c, "BOTTOM", 0, 10)
    c.reward = UI.Reward(c, 16, 11)
    c.reward:SetPoint("BOTTOMLEFT", c, "BOTTOMLEFT", 12, 14)
    c.pick = UI.Button(c, min(150, CARD_W - 24), 22, "Reroll this task", "red", 12)
    c.pick:SetPoint("BOTTOM", c, "BOTTOM", 0, 10)
    c.pick:Hide()
    P.cards[i] = c
end

-- Weekly tasks: rows as the old window drew them (a dark fill with a 1 px edge)
local weeklyTitle = P:Section("Weekly Tasks", A.PAD, WEEKLY_Y)
P.weeklyTitle = weeklyTitle
local ROW_H, ROW_PITCH = 44, 48
P.rows = {}
for i = 1, 3 do
    local r = UI.Box(P, LEFT, ROW_H, C.card, C.border, nil, "edge")
    r:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD, WEEKLY_Y - 22 - (i - 1) * ROW_PITCH)
    r.title = UI.Text(r, 13, C.text)
    r.title:SetPoint("TOPLEFT", r, "TOPLEFT", 10, -7)
    UI.OneLine(r.title, LEFT - 318)
    r.text = UI.Text(r, 11, C.dim)
    r.text:SetPoint("TOPLEFT", r.title, "BOTTOMLEFT", 0, -3)
    UI.OneLine(r.text, LEFT - 318)
    r.bar = UI.Bar(r, 110, 14)
    r.bar:SetPoint("LEFT", r, "RIGHT", -300, 0)
    r.reward = UI.Reward(r, 16, 11)
    r.reward:SetPoint("LEFT", r.bar, "RIGHT", 16, 0)
    r.claim = UI.Button(r, 90, 22, "Claim", "red", 12)
    r.claim:SetPoint("RIGHT", r, "RIGHT", -10, 0)
    -- a text too long for its line is cut with "..."; the row's tooltip has the whole title and text (setRow)
    r:EnableMouse(true)
    r:SetScript("OnEnter", function(self)
        if self.tip then
            UI.ShowTooltip(self, self.tip)
        end
    end)
    r:SetScript("OnLeave", function()
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    P.rows[i] = r
end

-- The battleground kill announcer (section 18): its voice and volume, under the weekly tasks, shown while the realm
-- runs the announcer (feature bit 8192) whether or not Bleakhold Royale is on
local ann = UI.Box(P, LEFT, ROW_H, C.card, C.border, nil, "edge")
-- under the weekly rows, or in their place while there is no weekly task (P:Refresh)
function P.PlaceAnnouncer(hasWeekly)
    ann:ClearAllPoints()
    ann:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD, hasWeekly and ANN_Y or WEEKLY_Y)
end
ann.title = UI.Text(ann, 13, C.gold)
ann.title:SetPoint("TOPLEFT", ann, "TOPLEFT", 10, -7)
ann.title:SetText("Kill Announcer")
ann.text = UI.Text(ann, 11, C.dim)
ann.text:SetPoint("TOPLEFT", ann.title, "BOTTOMLEFT", 0, -3)
UI.OneLine(ann.text, LEFT - 310)
ann.text:SetText("First blood, streaks and multi-kills in BGs")
ann.tip = { "Kill Announcer", { "Calls out first blood, kill streaks and multi-kills in every battleground, Bleakhold "
    .. "Royale included. Pick the voice and the volume here.", C.text, true } }
ann:EnableMouse(true)
ann:SetScript("OnEnter", function(self)
    UI.ShowTooltip(self, self.tip)
end)
ann:SetScript("OnLeave", function()
    if GameTooltip then
        GameTooltip:Hide()
    end
end)
ann.volume = UI.Dropdown(ann, 140, function(v)
    ns.Announcer.SetQuiet(v == "quiet")
end)
ann.volume:SetPoint("RIGHT", ann, "RIGHT", -9, 0)
ann.volume:SetItems({ { value = "normal", text = "Volume: Normal" }, { value = "quiet", text = "Volume: Quiet" } })
ann.voice = UI.Dropdown(ann, 130, function(v)
    ns.Announcer.SetVoice(v)
end)
ann.voice:SetPoint("RIGHT", ann.volume, "LEFT", -8, 0)
ann.voice:SetItems({ { value = "off", text = "Voice: Off" }, { value = "male", text = "Voice: Male" },
    { value = "female", text = "Voice: Female" } })
ann:Hide()
P.announcer = ann
P.PlaceAnnouncer(false)

function P:RefreshAnnouncer()
    if not (ns.Announcer and Comm.HasFeature(Comm.FEATURE.BG_ANNOUNCER)) then
        ann:Hide()
        return
    end
    ann.voice:SetValue(ns.Announcer.Voice(), true)
    ann.volume:SetValue(ns.Announcer.Quiet() and "quiet" or "normal", true)
    ann:Show()
end

-- Your week: the stat column (gold labels, white values) under a gold heading
local week = { rows = {} }
week.label = UI.Heading(P, "Your Week", 14)
week.label:SetPoint("TOPRIGHT", P, "TOPRIGHT", -A.PAD, -A.PAD)
week.label:SetJustifyH("RIGHT")
for i = 1, 5 do
    local v = P:Stat(i + 1, "")
    week.rows[i] = { label = v.label, value = v }
end
P.week = week

-- The weekly bonus: a tooltip panel under the stat column
local bonus = UI.Box(P, ASIDE, 124, C.panel, C.border, nil, "panel")
bonus:SetPoint("TOPRIGHT", P, "TOPRIGHT", -A.PAD, -A.PAD - 6 * A.STAT_PITCH + 4)
bonus.label = UI.Heading(bonus, "Weekly Bonus", 14)
bonus.label:SetPoint("TOPLEFT", bonus, "TOPLEFT", 12, -12)
bonus.title = UI.Text(bonus, 13, C.text)
bonus.title:SetPoint("TOPLEFT", bonus.label, "BOTTOMLEFT", 0, -6)
UI.OneLine(bonus.title, ASIDE - 24)
bonus.text = UI.Text(bonus, 11, C.dim)
bonus.text:SetPoint("TOPLEFT", bonus.title, "BOTTOMLEFT", 0, -4)
bonus.text:SetWidth(ASIDE - 24)
bonus.text:SetJustifyV("TOP")
bonus.text:SetHeight(42)
bonus.state = UI.Text(bonus, 12, C.teal)
bonus.state:SetPoint("BOTTOMLEFT", bonus, "BOTTOMLEFT", 12, 10)
P.bonus = bonus

local find = UI.Button(P, 160, 26, "Find a group", "red", 12)
find:SetPoint("BOTTOMRIGHT", P, "BOTTOMRIGHT", -18, 18)
find:SetScript("OnClick", function()
    A.Show("dungeons")
end)
P.find = find

local rerollMode = false

local function taskByUid(uid)
    return S.tasks and S.tasks.byUid[uid]
end

local function doReroll(uid)
    rerollMode = false
    local t = S.tasks
    if not t or not taskByUid(uid) then
        return
    end
    if (t.freeRerolls or 0) > 0 or (t.rerollCost or 0) == 0 then
        Comm.Send("TREROLL", uid)
    else
        local cost = t.rerollCurrency == "C" and (U.Commas(t.rerollCost) .. " Mythic Coins") or ns.RewardText("G", t.rerollCost)
        UI.Confirm("Reroll this task for " .. cost .. "?", function()
            Comm.Send("TREROLL", uid)
        end, "Reroll")
    end
    P:Refresh()
end

reroll:SetScript("OnClick", function()
    rerollMode = not rerollMode
    P:Refresh()
end)

-- a claimed reward keeps its icon, greyed, with "Claimed"
local function setReward(rw, t)
    rw:SetReward(t.rewardKind, t.rewardAmount, t.rewardItemId, t.rewardText)
    if t.state == 2 then
        rw.icon.icon:SetDesaturated(true)
        UI.SetColor(rw.text, C.mute)
        rw.text:SetText("Claimed")
    end
end

local function setCard(c, t)
    c.check:Hide()
    c.complete:Hide()
    c.claim:Hide()
    c.reward:Hide()
    c.pick:Hide()
    UI.Colors(c, C.card, C.border)
    if not t then
        c.bar:SetProgress(0, "")
        c.bar:Show()
        UI.SetText(c.title, Comm.ready and "No task" or "Waiting for the server")
        UI.SetText(c.text, "")
        return
    end
    local need = max(1, t.need or 1)
    local have = min(t.have or 0, need)
    local done = t.state >= 1
    c.bar:SetProgress(have / need, have .. " / " .. need)
    if done then
        c.bar:Hide()
        c.check:Show()
        c.complete:Show()
    else
        c.bar:Show()
    end
    UI.SetText(c.title, ns.TaskTitle(t))
    UI.SetText(c.text, ns.TaskText(t))
    if rerollMode and t.state == 0 then
        UI.Colors(c, C.active, C.border)
        c.pick:Show()
        c.pick:SetScript("OnClick", function()
            doReroll(t.uid)
        end)
    elseif t.state == 1 then
        c.claim:SetLabel("Claim " .. U.Safe(ns.TaskReward(t)))
        c.claim:Show()
        c.claim:SetScript("OnClick", function()
            Comm.Send("TCLAIM", t.uid)
        end)
    else
        setReward(c.reward, t)
        c.reward:Show()
    end
end

local function setRow(r, t)
    if not t then
        r.tip = nil
        r:Hide()
        return
    end
    r:Show()
    local need = max(1, t.need or 1)
    local have = min(t.have or 0, need)
    UI.SetText(r.title, ns.TaskTitle(t))
    UI.SetText(r.text, ns.TaskText(t))
    r.tip = { U.Safe(ns.TaskTitle(t)), { U.Safe(ns.TaskText(t)), C.text, true } }
    r.bar:SetProgress(have / need, have .. " / " .. need)
    setReward(r.reward, t)
    -- the design has no claim button for weekly tasks; one appears only if the server marks it claimable
    if t.state == 1 then
        r.reward:Hide()
        r.claim:Show()
        r.claim:SetScript("OnClick", function()
            Comm.Send("TCLAIM", t.uid)
        end)
    else
        r.claim:Hide()
        r.reward:Show()
    end
end

function P:RefreshEra()
    local e = S.era
    if e and e.eraId then
        local def = ns.Def("E", e.eraId) or {}
        era.label:SetText("Active Era This Week")
        UI.SetText(era.name, def.name or ("Era " .. e.eraId))
        UI.SetText(era.text, def.text or "")
        local nextName = e.nextEraId and ns.DefName("E", e.nextEraId)
        era.next:SetText(nextName and ("|cffffd100Next week:|r " .. U.Safe(nextName) .. " era") or "")
    else
        era.label:SetText(Comm.ready and "Active Era This Week" or "Bleakhold")
        UI.SetText(era.name, Comm.ready and "No era this week" or (Comm.outdated and "Client out of date" or "Connecting to Bleakhold"))
        UI.SetText(era.text, Comm.ready and "" or "Bleakhold features appear once the server answers. /bh demo shows a preview.")
        era.next:SetText("")
    end
    local affixes = e and e.affixes or {}
    local shown = {}
    for i, a in ipairs(era.affixes) do
        local id = affixes[i]
        if id then
            local d = ns.Def("A", id)
            a:SetAffix(ns.DefName("A", id, "Affix " .. id), UI.AFFIX_LEVELS[i], d and d.text)
            a:Show()
            shown[#shown + 1] = a
        else
            a:Hide()
        end
    end
    -- laid out from the right edge: reverse so they read in order
    local rtl = {}
    for i = #shown, 1, -1 do
        rtl[#rtl + 1] = shown[i]
    end
    UI.Row(rtl, era, "TOPRIGHT", "TOPRIGHT", 0, 0, 4, true)
end

function P:RefreshWeek(e)
    local w = S.week
    local rows = {
        { "Keys Timed", w and tostring(w.keysTimed) or "-" },
        { "Raid Echoes", w and tostring(w.echoes) or "-" },
        { "Rift Best", w and ("Floor " .. w.riftBestFloor) or "-" },
        { "Mythic Coins", w and (U.Commas(w.coins) .. (w.coinsCap > 0 and (" / " .. U.Commas(w.coinsCap)) or ""))
            or "-" },
    }
    if w and w.shards then
        rows[#rows + 1] = { "Shards", U.Commas(w.shards) }
    end
    for i, slot in ipairs(week.rows) do
        local row = rows[i]
        if row then
            slot.label:SetText(row[1])
            slot.value:SetText(row[2])
        else
            slot.label:SetText("")
            slot.value:SetText("")
        end
    end
    local b = e and e.bonusId and ns.Def("B", e.bonusId)
    if b then
        UI.SetText(bonus.title, b.title or "")
        UI.SetText(bonus.text, b.text or "")
        bonus.state:SetText(e.bonusDone and "Done" or "Still open")
        UI.SetColor(bonus.state, e.bonusDone and C.mute or C.teal)
        bonus:Show()
    else
        bonus:Hide()
    end
end

function P:Refresh()
    P:RefreshEra()

    -- daily
    local t = S.tasks
    local daily = t and t.daily or {}
    for i, c in ipairs(P.cards) do
        setCard(c, daily[i])
    end
    local free = t and t.freeRerolls or 0
    -- the server offers rerolls (free ones or a price), else it refuses each one ("Daily bounties cannot be rerolled.
    -- New ones come with the daily reset.", bh_ui_bridge.cpp OnTaskReroll): no button then
    local canReroll = t ~= nil and (free > 0 or (t.rerollCost or 0) > 0)
    if not canReroll then
        rerollMode = false
    end
    if rerollMode then
        reroll:SetLabel("Cancel reroll")
    elseif free > 0 then
        reroll:SetLabel("Reroll one (" .. free .. " free)")
    else
        reroll:SetLabel("Reroll one")
    end
    reroll:SetActive(#daily > 0)
    if canReroll then
        reroll:Show()
    else
        reroll:Hide()
    end

    -- weekly: the heading only over rows
    local weekly = t and t.weekly or {}
    for i, r in ipairs(P.rows) do
        setRow(r, weekly[i])
    end
    if #weekly > 0 then
        weeklyTitle:Show()
    else
        weeklyTitle:Hide()
    end
    P.PlaceAnnouncer(#weekly > 0)

    P:RefreshWeek(S.era)
    P:RefreshAnnouncer()
end

function P:OnOpen()
    Comm.Get("TASKS")
    Comm.Get("WEEK")
    Comm.Get("ERA")
end

------------------------------------------------------------------------------------------------------
-- Window behaviour
------------------------------------------------------------------------------------------------------
-- The page to open: the one asked for, else the one open last, else the Dungeon Journey (the old window's first).
local function startPage()
    return A.current or ns.cdb.activitiesTab or A.DEFAULT
end

function win:OnOpen()
    A.LayoutNav()
    A.UpdateLeave()
    -- the old window asked for the board, the keystone, the season list and the Rift on every open (Legacy.lua: at
    -- most every few seconds, and only on a Bleakhold server)
    ns.Legacy.Request()
    A.Show(startPage())
end

local tick, quick = 0, 0
win:SetScript("OnUpdate", function(self, elapsed)
    tick = tick + (elapsed or 0)
    quick = quick + (elapsed or 0)
    if strip:IsShown() and strip.hideAt and GetTime() >= strip.hideAt then
        strip:Hide()
    end
    if quick >= 0.5 then
        quick = 0
        A.UpdateLeave()
    end
    if tick >= 1 then
        tick = 0
        updateHeader()
        local page = A.pages[A.current or ""]
        if page and page.Tick then
            ns.SafeCall(page.Tick, page)
        end
    end
end)

local function refreshCurrent()
    local page = A.pages[A.current or ""]
    if page and page.Refresh then
        ns.SafeCall(page.Refresh, page)
    end
    A.UpdateArt()
end
A.RefreshCurrent = refreshCurrent

ns.On("STATE", function(topic)
    if win:IsShown() then
        refreshCurrent()
    end
end)

-- The legacy messages come in bursts (a board is an H and up to a dozen J, the season list a dozen L): one refresh
-- after the burst.
local refreshPending = false
local function refreshSoon()
    if not win:IsShown() or refreshPending then
        return
    end
    refreshPending = true
    ns.After(0.1, function()
        refreshPending = false
        if win:IsShown() then
            refreshCurrent()
        end
    end)
end
A.RefreshSoon = refreshSoon
ns.On("LEGACY", function(tag)
    refreshSoon()
end)

-- The game's own state the pages read for their buttons and hints (StartBlock, EnterBlock, MythicBlock, the Rift's
-- "Enter with your party"): the server sends nothing when a party forms or breaks up, its leader changes, the player
-- enters a battleground or the Dungeon Finder, a member levels, the difficulty changes, combat starts or ends, the
-- player dies, comes back or takes a flight path. The open page reads it again, once per burst.
local function onGameState()
    refreshSoon()
end
ns.RegisterEvent("PARTY_MEMBERS_CHANGED", onGameState)
ns.RegisterEvent("PARTY_LEADER_CHANGED", onGameState)
ns.RegisterEvent("RAID_ROSTER_UPDATE", onGameState)
ns.RegisterEvent("LFG_UPDATE", onGameState)
ns.RegisterEvent("PLAYER_ENTERING_WORLD", onGameState)
ns.RegisterEvent("ZONE_CHANGED_NEW_AREA", onGameState)
ns.RegisterEvent("PLAYER_LEVEL_UP", onGameState)
ns.RegisterEvent("PLAYER_DIFFICULTY_CHANGED", onGameState)
ns.RegisterEvent("PLAYER_REGEN_DISABLED", onGameState)
ns.RegisterEvent("PLAYER_REGEN_ENABLED", onGameState)
ns.RegisterEvent("PLAYER_DEAD", onGameState)
ns.RegisterEvent("PLAYER_ALIVE", onGameState)
ns.RegisterEvent("PLAYER_UNGHOST", onGameState)
-- a flight path takes and gives back control (FrameXML's taxi map has no event of its own)
ns.RegisterEvent("PLAYER_CONTROL_LOST", onGameState)
ns.RegisterEvent("PLAYER_CONTROL_GAINED", onGameState)
-- a party member's level (the Rift and a keystone need every member at their level); not every unit the client knows
ns.RegisterEvent("UNIT_LEVEL", function(event, unit)
    if unit == "player" or (type(unit) == "string" and (unit:match("^party%d$") or unit:match("^raid%d+$"))) then
        refreshSoon()
    end
end)

ns.On("HELLO", function()
    A.LayoutNav()
    P:RefreshAnnouncer()
    if win:IsShown() then
        updateHeader()
        -- a page the realm turned off (Arena without feature bit 65536) goes back to Tasks
        local page = A.pages[A.current or ""]
        if page and page.Available and not page.Available() then
            A.Show("tasks")
        end
        -- opened before the handshake was answered (the first second after a login or /reload): the old commands
        -- were refused then (Legacy.CanCommand), so ask for the board, the keystone and the Rift now. A request that
        -- did go out stamps the rate limit, so this does not repeat one made a moment ago.
        if Comm.ready then
            ns.Legacy.Request()
            refreshCurrent()
        end
    end
end)

ns.On("ERR", function(e)
    if win:IsShown() and e.text then
        A.ShowStrip(e.text, 6)
    end
end)

ns.On("OUTDATED", function()
    A.ShowStrip("This client is too old for the Bleakhold server. Please update the client.", nil)
    -- the answer proves a Bleakhold server, so the old commands work (Legacy.CanCommand): ask for the old pages' data
    if win:IsShown() then
        ns.Legacy.Request()
        refreshCurrent()
    end
end)

local function open(key, toggle)
    if toggle and win:IsShown() and (key == nil or key == A.current) then
        win:Hide()
        return
    end
    A.current = key or startPage()
    if win:IsShown() then
        A.Show(A.current)
    else
        win:Show()
    end
end

-- Open Activities on a page (an old page name works too: journey, mplus, ...); never closes it. Legacies and Season
-- open their own windows. Answers false for a page that does not exist.
function A.OpenPage(page)
    local key = A.Resolve(page)
    if key == "legacies" or key == "season" then
        A.Show(key)
        return true
    end
    if not A.pages[key or ""] then
        return false
    end
    open(key)
    return true
end

UI.RegisterOpener("activities", function(toggle) open(nil, toggle) end)
for _, key in ipairs({ "tasks", "dungeons", "keys", "rift", "heroic", "group" }) do
    UI.RegisterOpener(key, function(toggle) open(key, toggle) end)
    ns.AddCommand(key, "open Activities - " .. navByKey[key].label, function() open(key) end)
end
ns.AddCommand("activities", "open the Activities window", function() open(nil, true) end)

-- The server's "A;<page>" (Legacy.lua): the first login at the Dungeon Journey's level opens it, as the old addon did.
ns.On("LEGACY_OPEN", function(page)
    A.OpenPage(page)
end)

------------------------------------------------------------------------------------------------------
-- /act and /activities [page], the old addon's commands: with no page (or one that does not exist) they open or
-- close the window, with one they open it there. Registered under the old addon's own name, so a copy of it still
-- installed lands on the same entry (OldAddons.lua points it back here); a command another addon has already is
-- left to it.
------------------------------------------------------------------------------------------------------
A.SLASH_ID = "BLEAKHOLDACTIVITIES"
A.SLASH = { "/act", "/activities" }

function A.SlashCommand(msg)
    local arg = (strtrim and strtrim(msg or "") or (msg or "")):lower()
    if arg == "" or not A.OpenPage(arg) then
        open(nil, true)
    end
end

local function slashTaken(cmd, id)
    for name in pairs(SlashCmdList) do
        if name ~= id then
            local i = 1
            while _G["SLASH_" .. name .. i] do
                if string.lower(_G["SLASH_" .. name .. i]) == cmd then
                    return true
                end
                i = i + 1
            end
        end
    end
    return false
end

function A.RegisterSlash()
    local n = 0
    for _, cmd in ipairs(A.SLASH) do
        if not slashTaken(cmd, A.SLASH_ID) then
            n = n + 1
            _G["SLASH_" .. A.SLASH_ID .. n] = cmd
        end
    end
    if n > 0 then
        SlashCmdList[A.SLASH_ID] = A.SlashCommand
    end
    A.slashCount = n
    return n
end
A.RegisterSlash()

------------------------------------------------------------------------------------------------------
-- The game's own Dungeon Finder (random dungeons and heroics), one click away (Group Finder, Dungeons): the I key
-- opens Activities instead
------------------------------------------------------------------------------------------------------
function A.OpenDungeonFinder()
    win:Hide()
    if LFDParentFrame and ShowUIPanel then
        ShowUIPanel(LFDParentFrame)
    elseif type(ToggleLFDParentFrame) == "function" then
        ToggleLFDParentFrame()
    end
end

-- The finder button's tooltip: what it is and the key it has (or where to give it one).
function A.FinderTooltip()
    local key = GetBindingKey and GetBindingKey("TOGGLELFGPARENT")
    return { "Dungeon Finder", { "The game's own finder: random dungeons and random heroics.", C.mid, true },
             { key and ("Key: " .. key) or "Give it a key in Key Bindings: Toggle Dungeon Finder.", C.mute, true } }
end

-- The I key: once per set of key bindings, I opens Activities, as it did before. Taken only from the stock Dungeon
-- Finder (TOGGLELFGPARENT, ToggleLFDParentFrame in the 3.3.5a FrameXML Bindings.xml: I in the stock key bindings)
-- or when nothing has it; a key the player gave anything else stays theirs, and so does a key they gave Activities
-- already. Not in combat (SetBinding is protected there): tried again when combat ends or at the next login.
-- SaveBindings writes the set in use only: the account's (ACCOUNT_BINDINGS, 1), or with "Character Specific Key
-- Bindings" ticked the character's own (CHARACTER_BINDINGS, 2). So "offered" is kept where that set lives: the
-- account's in BleakholdDB, a character's own in BleakholdCharDB; every set gets the offer once.
A.KEY = "I"
A.BINDING = "BLEAKHOLD_ACTIVITIES"
A.STOCK_FINDER = { TOGGLELFGPARENT = true }
A.CHARACTER_SET = 2

-- The saved table that holds "offered" for the set of key bindings in use now.
function A.KeyOfferStore()
    local set = GetCurrentBindingSet and GetCurrentBindingSet()
    if set == A.CHARACTER_SET then
        return ns.cdb
    end
    return ns.db.options
end

function A.KeyOffered()
    return A.KeyOfferStore().activitiesKeyOffered and true or false
end

function A.OfferDefaultKey()
    if A.KeyOffered() or not SetBinding or not GetBindingAction then
        return
    end
    if InCombatLockdown and InCombatLockdown() then
        return
    end
    A.KeyOfferStore().activitiesKeyOffered = true
    if GetBindingKey and GetBindingKey(A.BINDING) then
        return
    end
    local current = GetBindingAction(A.KEY) or ""
    if current == "" or A.STOCK_FINDER[current] then
        if SetBinding(A.KEY, A.BINDING) and SaveBindings and GetCurrentBindingSet then
            SaveBindings(GetCurrentBindingSet())
            ns.Print("I opens Activities (the Dungeon Journey, Mythic+, the Eclipse Rift, the Group Finder). The game's "
                .. "Dungeon Finder is in Activities > Group Finder, and Key Bindings can give it a key of its own.")
        end
    end
end

ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    ns.After(1, A.OfferDefaultKey)
end)
ns.RegisterEvent("PLAYER_REGEN_ENABLED", function()
    if not A.KeyOffered() then
        ns.After(0.5, A.OfferDefaultKey)
    end
end)
