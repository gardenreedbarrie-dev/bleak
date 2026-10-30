-- Activities' own pages in the old window's page anatomy (PLAN decision 3; Activities.lua A.Page): Bleakhold Royale
-- (Royale.lua), War Mode (WarMode.lua), Arena (Arena.lua) and Tasks (Activities.lua). Each page has the gold 22 title,
-- the white description 390 wide, gold labels with white values, gold section headings, tooltip panels, red buttons,
-- stock icons and marks, and its picture on the right (the island for Royale; the dense pages at low alpha). Their
-- data paths are the other files' tests (test_royale.lua, test_warmode.lua, test_arena.lua, test_windows.lua); here
-- the look, with the data that fills it.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local ROYALE, ANNOUNCER, WAR, WPVP, ARENA = 4096, 8192, 16384, 32768, 65536
local GOLD, WHITE, GREEN, RED = { 1, 0.82, 0 }, { 1, 1, 1 }, { 0.1, 1, 0.1 }, { 1, 0.1, 0.1 }
local TOOLTIP_BG, TOOLTIP_EDGE = "Interface\\Tooltips\\UI-Tooltip-Background", "Interface\\Tooltips\\UI-Tooltip-Border"
local COLUMN_TABS = "Interface\\FriendsFrame\\WhoFrame-ColumnTabs"

local function near(a, b, eps)
    return math.abs(a - b) < (eps or 0.01)
end

-- colorIs(want, what, r, g, b): the colour call goes last so all its values arrive
local function colorIs(want, what, r, g, b)
    H.ok(near(r, want[1]) and near(g, want[2]) and near(b, want[3]),
        what .. ": " .. table.concat({ r, g, b }, ",") .. " is not " .. table.concat(want, ","))
end

local function texture(t)
    return t.__texture
end

-- The page's own anatomy: the gold 22 title at (20, -18), the white description 390 wide at (20, -50).
local function anatomy(p, title, descPart)
    local A = p.title and p.anatomy and true
    H.ok(A, "an anatomy page (A.Page)")
    H.eq(p.title:GetText(), title)
    H.eq(select(2, p.title:GetFont()), 22, "the title is 22")
    colorIs(GOLD, "the title is gold", p.title:GetTextColor())
    local _, _, _, x, y = p.title:GetPoint(1)
    H.ok(x == 20 and y == -18, "the title at 20, -18")
    H.eq(p.desc:GetWidth(), 390, "the description is 390 wide")
    colorIs(WHITE, "the description is white", p.desc:GetTextColor())
    if descPart then
        H.contains(p.desc:GetText(), descPart)
    end
end

-- A tooltip panel (the old panelBox), not a flat 1 px box.
local function isPanel(f, what)
    H.eq(f.__backdrop and f.__backdrop.bgFile, TOOLTIP_BG, what .. ": the tooltip background")
    H.eq(f.__backdrop and f.__backdrop.edgeFile, TOOLTIP_EDGE, what .. ": the tooltip edge")
    H.eq(f.__backdrop and f.__backdrop.edgeSize, 16, what .. ": a 16 px edge")
end

local function isHeading(fs, text, what)
    H.eq(fs:GetText(), text, what)
    colorIs(GOLD, what .. " is gold", fs:GetTextColor())
    H.eq(select(2, fs:GetFont()), 14, what .. " is 14")
end

-- The red panel button: the kit's panel art (any colour name of the old kit draws it).
-- small: the small one for minor actions.
local function isRed(ns, b, what, small)
    local st = ns.UI.STYLES[b.style]
    H.ok(st and st.art == "panel" and (st.small and true or false) == (small and true or false),
        what .. ": the red panel button, style " .. tostring(b.style))
end

-- Every visible FontString of a frame's tree (regions and children).
local function texts(root)
    local out = {}
    local function walk(f)
        for _, r in ipairs(f.__regions or {}) do
            if r.__otype == "FontString" and r:IsVisible() and (r:GetText() or "") ~= "" then
                out[#out + 1] = r
            end
        end
        for _, c in ipairs(f.__children or {}) do
            walk(c)
        end
    end
    walk(root)
    return out
end

-- No caption in capitals: 3.3.5a writes titles, headings and labels in Title Case (four capitals or more in a row,
-- colour codes aside, are a caption written for show).
local function noCaps(root, what)
    local caps = {}
    for _, fs in ipairs(texts(root)) do
        local plain = fs:GetText():gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
        if plain:find("%u%u%u%u") then
            caps[#caps + 1] = plain
        end
    end
    H.ok(#caps == 0, what .. ": captions in capitals: " .. table.concat(caps, " | "))
end

-- The stat column (A.Page p:Stat): a gold 12 label right-aligned 20 from the right, 46 px apart, a white 15 value
-- with an outline under it.
local function isStat(v, i, label, what)
    H.eq(v.label:GetText(), label, what .. " label")
    colorIs(GOLD, what .. " label is gold", v.label:GetTextColor())
    local _, _, _, x, y = v.label:GetPoint(1)
    H.ok(x == -20 and y == -20 - (i - 1) * 46, what .. " at stat slot " .. i .. ": " .. tostring(x) .. "," .. tostring(y))
    local _, size, flags = v:GetFont()
    H.ok(size == 15 and flags == "OUTLINE", what .. " value 15 with an outline")
    colorIs(WHITE, what .. " value is white", v:GetTextColor())
end

------------------------------------------------------------------------------------------------------
-- Bleakhold Royale
------------------------------------------------------------------------------------------------------
test("royale page: the anatomy, the island as its picture, the last match in the stat column", function(M, ns)
    FX.connect(M, H, { [6] = ROYALE })
    ns.UI.Open("royale")
    M.Advance(0.3)
    local A, R = ns.Activities, ns.Royale
    local P = R.page
    H.ok(P:IsVisible(), "the Royale page")
    H.eq(A.pages.royale, P, "Activities' page")
    anatomy(P, "Bleakhold Royale", "the last player standing wins")
    -- the island map as the page's picture, cropped to the picture's shape and dimmed
    H.eq(A.artSource, "own")
    H.eq(texture(A.art), R.MAP_TEX, "the island map")
    H.ok(near(A.art:GetAlpha(), R.PAGE_ART_ALPHA) and R.PAGE_ART_ALPHA <= 0.6, "dimmed: " .. A.art:GetAlpha())
    local l, _, _, _, r = A.art:GetTexCoord()
    H.ok(near(r - l, A.ART_W / A.ART_H, 0.005) and near(l, 1 - r, 0.001), "a centred crop in the picture's shape")
    H.ok(A.fade:IsShown(), "fading into the dark on its left")
    -- the island card: the thumbnail as a square icon, the motto, the facts
    H.eq(texture(P.hero.thumb.icon), R.THUMB_TEX)
    H.eq(P.hero.title:GetText(), "Last one standing")
    H.eq(P.hero.facts:GetText(), "Solo · Level 80 · 20-40 players")
    local _, _, _, x, y = P.hero:GetPoint(1)
    H.ok(x == A.PAD and y == A.BODY_Y, "the card where the old pages' body starts")
    -- the stat column
    isStat(P.last.place, 1, "Last Match", "last match")
    isStat(P.last.kills, 2, "Eliminations", "eliminations")
    isStat(P.last.survived, 3, "Survived", "survived")
    isStat(P.last.running, 4, "Matches Running", "matches running")
    H.eq(P.last.place:GetText(), "No match yet")
    H.eq(P.last.kills:GetText(), "-")
    -- the sections
    isHeading(P.how.title, "How it works", "how it works")
    H.eq(#P.how.lines, 5)
    H.eq(P.how.numbers[3]:GetText(), "3.")
    colorIs(GOLD, "the step numbers", P.how.numbers[1]:GetTextColor())
    H.contains(P.how.lines[1]:GetText(), "ready check")
    -- the steps stay in the description's column (the art on the right fades into the dark)
    for i, line in ipairs(P.how.lines) do
        local _, _, _, sx = line:GetPoint(1)
        H.eq(sx + line:GetWidth(), A.PAD + A.DESC_W, "step " .. i .. " ends where the description does")
    end
    isHeading(P.last.title, "Last Match Rewards", "last match rewards")
    H.contains(P.last.none:GetText(), "Play a match")
    -- the queue, bottom right
    isRed(ns, P.join, "Queue")
    local point, _, rel = P.join:GetPoint(1)
    H.ok(point == "BOTTOMRIGHT" and rel == "BOTTOMRIGHT", "Queue in the bottom right corner")
    H.eq(P.hero.status:GetText(), "Not queued")
    H.send(M, "QUEUE", { { 4, 1, "B", 901, 0, 1, 12, "", "", "", 80, 80, 13, 20, 40, "", "", 2 } })
    M.Advance(0.6)
    H.eq(P.hero.status:GetText(), "13 / 20 queued")
    colorIs(GOLD, "queued: gold", P.hero.status:GetTextColor())
    H.eq(P.last.running:GetText(), "2", "the matches running now")
    H.eq(P.join.label:GetText(), "Leave queue")
    isRed(ns, P.join, "Leave queue")
    noCaps(P, "the Royale page")
end)

test("royale page: the last match's place, eliminations, time and rewards; kept for the next login", function(M, ns)
    FX.connect(M, H, { [6] = ROYALE })
    H.send(M, "ROYE", { { 7001, 7, 32, 2, 18400, 2100, 1840, "Dalia", 11, 7, 1 }, { "H", 400, "", "Placement" },
        { "S", 12, "", "Placement" } })
    M.Advance(0.2)
    ns.UI.Open("royale")
    M.Advance(0.3)
    local P = ns.Royale.page
    H.eq(P.last.place:GetText(), "#7 of 32")
    H.eq(P.last.kills:GetText(), "2")
    H.eq(P.last.survived:GetText(), "30:40")
    local rw = P.last.lines[1]
    H.ok(rw:IsShown() and not P.last.lines[3]:IsShown(), "one line per reward")
    H.contains(rw.text:GetText(), "Honor - Placement")
    H.ok(texture(rw.icon.icon):find("^Interface\\Icons\\"), "a stock icon by the reward")
    H.eq(P.last.none:GetText(), "")
    H.eq(M.env.BleakholdCharDB.royaleLast.survivedSec, 1840, "the time is kept too")
    -- the next session: only the saved place, eliminations and time
    ns.S.royaleResult = nil
    P:Refresh()
    H.eq(P.last.place:GetText(), "#7 of 32")
    H.eq(P.last.kills:GetText(), "2")
    H.eq(P.last.survived:GetText(), "30:40")
    H.ok(not rw:IsShown(), "no reward lines without the result")
    -- a match without rewards says so
    H.send(M, "ROYE", { { 7002, 1, 20, 9, 50000, 0, 700, "Tester", 1, 9, 0 } })
    M.Advance(0.2)
    H.eq(P.last.place:GetText(), "#1 Victory")
    H.eq(P.last.none:GetText(), "No rewards. You left early or saw no fight.")
end)

------------------------------------------------------------------------------------------------------
-- War Mode
------------------------------------------------------------------------------------------------------
local function wmst(M, over)
    local r = { 0, 0, "", 20, 0, 10, 0, 8, "H", 31, 22, 0, 0, 0, 0, 0, 3720, 0, 60, 7, 118, 96 }
    for k, v in pairs(over or {}) do r[k] = v end
    H.send(M, "WMST", { r })
end

test("warmode page: the state as the title, the toggle top right, tooltip panels with gold labels, the Fronts table",
    function(M, ns)
    M.env.IsResting = function() return 1 end
    FX.connect(M, H, { [6] = WAR + WPVP })
    wmst(M)
    ns.UI.Open("warmode")
    M.Advance(0.3)
    local A, WM = ns.Activities, ns.WarMode
    local P = WM.page
    H.ok(P:IsVisible(), "the War Mode page")
    anatomy(P, "War Mode is off", "flagged for PvP everywhere except sanctuaries")
    H.eq(P.hero.title, P.title, "the state is the page's title")
    -- a dense page: its picture at low alpha
    H.eq(A.artKey, "HELLFIRE")
    H.ok(A.art:GetAlpha() <= 0.5, "low alpha: " .. A.art:GetAlpha())
    -- the toggle, top right, why it is grey under it
    isRed(ns, P.toggle, "the toggle")
    local point, _, rel, x, y = P.toggle:GetPoint(1)
    H.ok(point == "TOPRIGHT" and rel == "TOPRIGHT" and x == -20 and y == -20, "the toggle top right")
    H.eq(P.hero.status:GetText(), "Change it at an inn or in a city.")
    -- the panels
    isPanel(P.bonus, "bonuses")
    isPanel(P.today, "today")
    isPanel(P.fronts, "fronts")
    isHeading(P.bonus.label, "Bonuses in the Open World", "bonuses heading")
    isHeading(P.today.label, "Today", "today heading")
    isHeading(P.fronts.label, "War Fronts", "fronts heading")
    H.eq(P.bonus.rows[3].label:GetText(), "War Mode Players", "labels in Title Case")
    colorIs(GOLD, "a gold label", P.bonus.rows[3].label:GetTextColor())
    colorIs(WHITE, "a white value", P.bonus.rows[3].value:GetTextColor())
    H.eq(P.today.rows[4].label:GetText(), "Kills / Deaths")
    H.eq(P.today.rows[4].value:GetText(), "118 / 96")
    -- the caps as the achievement progress bar
    H.eq(texture(P.today.honorBar:GetStatusBarTexture()), "Interface\\TargetingFrame\\UI-StatusBar")
    H.ok(P.today.honorBar:GetHeight() >= 14, "the achievement bar's height")
    -- the Fronts' zones under WhoFrame's column headers
    local names = {}
    for i, h in ipairs(P.fronts.headers) do
        names[i] = h.label:GetText()
        H.eq(texture(h.slices[2]), COLUMN_TABS, "a column header")
    end
    H.eq(table.concat(names, ","), "Zone,Front,Outposts,Levels,State")
    noCaps(P, "the War Mode page")
end)

test("warmode page: the hunt in red under the title; the Fronts' table hides without the objectives", function(M, ns)
    M.env.IsResting = function() return 1 end
    FX.connect(M, H, { [6] = WAR })
    wmst(M, { [1] = 1, [13] = 1, [14] = 840, [15] = 248 })
    ns.UI.Open("warmode")
    M.Advance(0.3)
    local P = ns.WarMode.page
    H.eq(P.title:GetText(), "War Mode is on")
    H.contains(P.hero.status:GetText(), "Wanted for a kill streak")
    colorIs(RED, "the hunt is red", P.hero.status:GetTextColor())
    H.eq(P.fronts.lines[1]:GetText(), "World PvP objectives are not open on this realm right now.")
    H.ok(not P.fronts.headers[1]:IsShown(), "no zone table without bit 32768")
end)

------------------------------------------------------------------------------------------------------
-- Arena
------------------------------------------------------------------------------------------------------
local function arena(M)
    local now = M.env.time()
    H.send(M, "ARENA", {
        { 1, 1, now - 86400, now + 30 * 86400, now + 32 * 86400, 1, 100000, "Arena Season 1" },
        { "S", 1, "Arena Season 1", 1, now - 86400, now + 30 * 86400 },
        { "B", 1, 1, 1734, 12, 48, 61, 38, 9, 6, 1734, 14, 3, 4, 66, 0, "Aldric" },
        { "B", 3, 1, 1912, 4, 22, 44, 30, 12, 8, 1890, 12, 4, 5, 163, 16, "Ironvow Wardens" },
        { "T", 3, 6, 1, 1, 2140, 2000 }, { "T", 3, 5, 2, 2, 2075, 2000 }, { "T", 3, 4, 4, 4, 1912, 1800 },
        { "T", 3, 3, 4, 4, 1912, 1650 }, { "T", 1, 4, 6, 6, 1801, 1800 }, { "T", 1, 3, 5, 5, 1702, 1650 },
        { "N", 1, 48, 1, 1 }, { "N", 3, 22, 1, 0 },
        { "M", 1, 1, 14, "Brenna", now - 600, 0, "" },
    })
end

test("arena page: the season as the title, bracket panels, the queue, the detail under the options frame's tabs",
    function(M, ns)
    FX.connect(M, H, { [6] = ARENA })
    arena(M)
    ns.UI.Open("arena")
    M.Advance(0.3)
    local A, AR = ns.Activities, ns.Arena
    local P = AR.page
    H.ok(P:IsVisible(), "the Arena page")
    anatomy(P, "Arena Season 1", "1v1 ladder of your own")
    H.eq(P.head.title, P.title, "the season is the page's title")
    H.eq(P.head.state.text:GetText(), "Live")
    colorIs(GREEN, "a live season is green", P.head.state.text:GetTextColor())
    H.ok(P.head.state.__backdrop == nil, "the state is plain text, not a pill")
    H.contains(P.head.clock:GetText(), "Ends in ")
    H.eq(A.artKey, "BLACKROCKDEPTHS")
    H.ok(A.art:GetAlpha() <= 0.5, "a dense page: low alpha")
    isRed(ns, P.head.board, "Leaderboard")
    isRed(ns, P.head.pvp, "Arena teams")
    -- the bracket panels: a gold heading in Title Case, the chosen one lit as the nav rows are
    for i, c in ipairs(P.cards) do
        isPanel(c, "bracket card " .. i)
        isHeading(c.kicker, AR.BracketName(c.bracket), "bracket heading " .. i)
        H.eq(c.selected and true or false, c.bracket == P.bracket, "only the chosen bracket is lit: " .. i)
    end
    H.eq(P.cards[1].kicker:GetText(), "1v1", "never 1V1")
    P.cards[3]:Click()
    H.ok(P.cards[3].selected and not P.cards[1].selected, "the click moves the light")
    -- the queue and the matches
    isPanel(P.queue, "the queue")
    isHeading(P.queue.label, "1v1 Queue", "queue heading")
    isRed(ns, P.queue.rated, "Rated 1v1")
    isRed(ns, P.queue.skirmish, "Skirmish")
    isPanel(P.matches, "the matches")
    isHeading(P.matches.label, "Last Rated Matches", "matches heading")
    -- the detail: the views as the options frame's tabs over the panel, the bracket as red buttons held down
    isPanel(P.detail, "the detail")
    local styles = {}
    for i, b in ipairs(P.detail.views) do
        styles[i] = b.style
        local point, rel, relPoint = b:GetPoint(1)
        H.ok(point == "BOTTOMLEFT" and rel == P.detail and relPoint == "TOPLEFT", "a tab sits on the panel")
    end
    H.eq(table.concat(styles, ","), "stripOn,strip,strip")
    styles = {}
    for i, b in ipairs(P.detail.brackets) do
        styles[i] = b.style
    end
    H.eq(table.concat(styles, ","), "tab,tab,tabOn,tab", "3v3 held down")
    H.eq(P.detail.heading:GetText(), "3v3 Cutoffs")
    -- the cutoffs under WhoFrame's column headers, the player's tier lit
    local cut = P.detail.cutoffs
    local names = {}
    for i, h in ipairs(cut.header.cols) do
        names[i] = h.label:GetText()
        H.eq(texture(h.slices[1]), COLUMN_TABS)
    end
    H.eq(table.concat(names, ","), "Tier,Places,Last In,Rating,Floor,Takes Now")
    local w = 0
    for _, h in ipairs(cut.header.cols) do w = w + h:GetWidth() end
    H.ok(w <= cut:GetWidth(), "the columns fit the table: " .. w .. " of " .. cut:GetWidth())
    H.ok(cut.rows[3].selected and not cut.rows[1].selected, "the player's tier")
    -- the checklist with the ready check's marks
    P.detail.views[2]:Click()
    H.eq(P.detail.heading:GetText(), "3v3 Reward Checklist")
    H.eq(table.concat({ P.detail.views[1].style, P.detail.views[2].style }, ","), "strip,stripOn")
    local ok, no = 0, 0
    for _, l in ipairs(P.detail.checklist.lines) do
        if l:IsShown() then
            local tex = texture(l.icon)
            if tex == AR.MARKS.ok then ok = ok + 1 elseif tex == AR.MARKS.no then no = no + 1 end
            H.ok(l.icon:IsShown(), "every line has its mark")
        end
    end
    H.ok(ok >= 1 and no >= 1, "met and missing: " .. ok .. " / " .. no)
    H.eq(AR.MARKS.ok, "Interface\\RaidFrame\\ReadyCheck-Ready")
    H.eq(AR.MARKS.no, "Interface\\RaidFrame\\ReadyCheck-NotReady")
    noCaps(P, "the Arena page")
end)

------------------------------------------------------------------------------------------------------
-- Tasks
------------------------------------------------------------------------------------------------------
test("tasks page: your week in the stat column, the era block, daily panels, weekly rows, the announcer",
    function(M, ns)
    FX.connect(M, H, { [6] = ANNOUNCER })
    FX.all(M, H)
    ns.UI.Open("tasks")
    M.Advance(0.5)
    local A = ns.Activities
    local P = A.tasksPage
    H.eq(A.pages.tasks, P)
    H.ok(P:IsVisible(), "the Tasks page")
    anatomy(P, "Tasks", "Dungeon Journey bounties a day")
    H.ok(A.art:GetAlpha() <= 0.5, "a dense page: low alpha")
    -- your week
    isHeading(P.week.label, "Your Week", "your week")
    local labels = { "Keys Timed", "Raid Echoes", "Rift Best", "Mythic Coins", "Shards" }
    for i, row in ipairs(P.week.rows) do
        isStat(row.value, i + 1, labels[i], labels[i])
    end
    H.eq(P.week.rows[3].value:GetText(), "Floor 18")
    H.eq(P.week.rows[4].value:GetText(), "2,140 / 5,500")
    isPanel(P.bonus, "the weekly bonus")
    isHeading(P.bonus.label, "Weekly Bonus", "weekly bonus heading")
    -- the era: a ring portrait of a stock icon, its name, the affixes
    H.eq(texture(P.era.badge.ring), "Interface\\Minimap\\MiniMap-TrackingBorder", "a ring portrait")
    H.eq(texture(P.era.badge.icon), "Interface\\Icons\\Spell_Fire_Fire", "the flame's icon in it")
    H.ok(P.era.badge.icon.__portrait, "cut round (SetPortraitToTexture)")
    H.eq(P.era.name:GetText(), "The Black Temple")
    H.ok(P.era.affixes[1]:IsShown() and P.era.affixes[3]:IsShown(), "the affix icons")
    -- next week's era: its own line beside the era text's second line (not on its first, where it read as the end of
    -- that sentence), the prefix gold
    H.eq(P.era.next:GetText(), "|cffffd100Next week:|r Ahn'Qiraj era")
    local npt, nrel, nrp, nx, ny = P.era.next:GetPoint(1)
    H.ok(npt == "TOPRIGHT" and nrel == P.era and nrp == "TOPRIGHT" and nx == 0 and ny == -48,
        "next week's era right-aligned on the era text's second line")
    local _, _, _, x, y = P.era:GetPoint(1)
    H.ok(x == A.PAD and y > A.BODY_Y - 40 and y < -90, "the era block under the description")
    -- daily tasks: tooltip panels under a gold heading
    isHeading(P.dailyTitle, "Daily Tasks", "daily heading")
    for i, c in ipairs(P.cards) do
        isPanel(c, "daily card " .. i)
    end
    isRed(ns, P.cards[3].claim, "Claim")
    H.ok(P.cards[3].claim:IsShown(), "the claimable task")
    isRed(ns, P.reroll, "Reroll one", true)
    -- reroll mode lights the cards that can be picked
    P.reroll:Click()
    H.ok(P.cards[1].selected and not P.cards[3].selected, "pickable cards lit")
    P.reroll:Click()
    H.ok(not P.cards[1].selected, "and dark again")
    -- weekly tasks: the old window's rows (a dark fill and a 1 px edge) under a gold heading
    isHeading(P.weeklyTitle, "Weekly Tasks", "weekly heading")
    for i, r in ipairs(P.rows) do
        H.eq(r.backdropKind, "edge", "weekly row " .. i .. " is a row")
    end
    H.eq(P.rows[1].bar:GetStatusBarTexture().__texture, "Interface\\TargetingFrame\\UI-StatusBar")
    -- the title and text get the room left of a 110 px bar, and the row's tooltip has them whole (a long text is cut
    -- with "..." on its line)
    local r2 = P.rows[2]
    H.eq(r2.bar:GetWidth(), 110, "a narrow bar")
    local _, _, _, barX = r2.bar:GetPoint(1)
    local _, _, _, textX = r2.title:GetPoint(1)
    H.ok(textX + r2.text:GetWidth() < r2:GetWidth() + barX, "the text ends before the bar")
    H.eq(r2.text:GetWidth(), r2.title:GetWidth(), "title and text share the width")
    H.eq(r2.text:GetText(), "Defeat 2 Raid Echoes in keys or the Rift.")
    M.Hover(r2)
    H.eq(M.env.GameTooltip.__lines[1], "Echo hunter", "the row's tooltip: the title")
    H.eq(M.env.GameTooltip.__lines[2], "Defeat 2 Raid Echoes in keys or the Rift.", "and the whole text")
    M.Hover(r2, false)
    H.ok(not M.env.GameTooltip:IsShown(), "gone when the cursor leaves")
    -- the announcer while the realm runs it
    H.ok(P.announcer:IsShown(), "the kill announcer's settings")
    local _, _, _, _, annY = P.announcer:GetPoint(1)
    H.ok(annY < select(5, P.rows[2]:GetPoint(1)), "under the weekly rows")
    H.eq(P.announcer.title:GetText(), "Kill Announcer")
    H.eq(P.announcer.text:GetText(), "First blood, streaks and multi-kills in BGs", "a line that fits")
    M.Hover(P.announcer)
    H.eq(M.env.GameTooltip.__lines[1], "Kill Announcer")
    H.contains(M.env.GameTooltip.__lines[2], "in every battleground", "the tooltip says it in full")
    M.Hover(P.announcer, false)
    -- Find a group, bottom right
    isRed(ns, P.find, "Find a group")
    local point, _, rel = P.find:GetPoint(1)
    H.ok(point == "BOTTOMRIGHT" and rel == "BOTTOMRIGHT", "Find a group in the bottom right corner")
    noCaps(P, "the Tasks page")
end)

test("tasks page: the realm's TASKS (three Journey bounties, no reroll, no weekly task): no Reroll, no empty heading",
    function(M, ns)
    FX.connect(M, H, { [6] = ANNOUNCER })
    -- bh_ui_bridge_map.cpp BountyTasks: freeRerolls 0, no cost, daily Shards bounties only
    H.send(M, "TASKS", {
        { 1, 0, 0, "G" },
        { 101, "D", 1, 0, 1, "S", 40, "", 0 },
        { 102, "D", 2, 0, 1, "S", 40, "", 0 },
        { 103, "D", 3, 1, 1, "S", 40, "", 2 },
    }, 90)
    ns.UI.Open("tasks")
    M.Advance(0.5)
    local P = ns.Activities.tasksPage
    H.ok(P.cards[1]:IsShown() and P.cards[3]:IsShown(), "the three bounties")
    H.ok(not P.reroll:IsShown(), "no Reroll: the server refuses every one")
    H.ok(not P.weeklyTitle:IsShown(), "no Weekly Tasks heading over nothing")
    for i, r in ipairs(P.rows) do
        H.ok(not r:IsShown(), "weekly row " .. i)
    end
    H.ok(P.announcer:IsShown())
    local _, _, _, _, annY = P.announcer:GetPoint(1)
    local _, _, _, _, weeklyY = P.weeklyTitle:GetPoint(1)
    H.eq(annY, weeklyY, "the announcer moves up into the weekly tasks' place")
end)

test("tasks page: before the server answers, the era block says so and the stats wait", function(M, ns)
    ns.UI.Open("tasks")
    M.Advance(0.3)
    local P = ns.Activities.tasksPage
    H.eq(P.era.name:GetText(), "Connecting to Bleakhold")
    H.contains(P.era.text:GetText(), "/bh demo")
    H.eq(P.week.rows[1].value:GetText(), "-")
    H.ok(not P.bonus:IsShown(), "no weekly bonus yet")
end)
