-- Bleakhold: Leaderboards window. Tabs Mythic Keys / Eclipse Rift / Raid Echoes / Arena / Server Firsts,
-- season, dungeon (Arena: bracket) and class filters, top-three podium, ranked table with pages, your best (Arena:
-- your standing) and the latest server firsts. The server ranks everything; the client only asks for pages (LBQ).
-- The Arena tab (board A, section 20) is there only with HELLO feature bit 65536; its seasons come from ARENA S.
-- Stock 3.3.5a look: the options frame's tabs on a tooltip panel, UIDropDownMenu-dressed filters, medals as icons
-- (the arena achievements' axes), WhoFrame column headers over rows with the quest log highlight, the spellbook's
-- page arrows, the achievement progress bar and the indicator balls.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S

local floor, max, min = math.floor, math.max, math.min

local LB = {}
ns.Leaderboards = LB

LB.W, LB.H = 940, 600
LB.board = "K"
LB.season = nil
LB.dungeon = 0
LB.class = 0
LB.page = 1
LB.bracket = 3          -- board A: 1, 2, 3 or 5
LB.arenaSeason = 0      -- board A: an arena season id, 0 the current one
LB.ROWS = 8

local win = UI.Window("BleakholdLeaderboardsFrame", LB.W, LB.H, "Leaderboards", "trophy")
local CW, CH = UI.ContentSize(LB.W, LB.H)
LB.frame = win

------------------------------------------------------------------------------------------------------
-- Header: season
------------------------------------------------------------------------------------------------------
local seasonDD = UI.Dropdown(win.header, 190, function(value)
    if LB.board == "A" then
        LB.arenaSeason = value
    else
        LB.season = value
    end
    LB.page = 1
    LB.Query()
end)
seasonDD:SetPoint("RIGHT", win.close, "LEFT", -12, 0)
local seasonLabel = UI.Text(win.header, 12, C.gold)
seasonLabel:SetPoint("RIGHT", seasonDD, "LEFT", -6, 0)
seasonLabel:SetText("Season")

------------------------------------------------------------------------------------------------------
-- Tabs and filters: the options frame's top tabs standing on the body (a tooltip panel), the dungeon (Arena:
-- bracket) and class dropdowns at the right of the strip
------------------------------------------------------------------------------------------------------
LB.STRIP_H = 28
local body = UI.Box(win.content, CW, CH - LB.STRIP_H, C.panel, C.border, nil, "panel")
body:SetPoint("TOPLEFT", win.content, "TOPLEFT", 0, -LB.STRIP_H)
body:SetPoint("BOTTOMRIGHT", win.content, "BOTTOMRIGHT", 0, 0)
LB.body = body
-- above the body, so the open tab's legs cover the panel's top edge
local bar = CreateFrame("Frame", nil, win.content)
bar:SetPoint("TOPLEFT", win.content, "TOPLEFT", 0, 0)
bar:SetPoint("BOTTOMRIGHT", body, "TOPRIGHT", 0, 0)
bar:SetFrameLevel(body:GetFrameLevel() + 5)
local tabDefs = {
    { key = "K", label = "Mythic Keys" },
    { key = "R", label = "Eclipse Rift" },
    { key = "E", label = "Raid Echoes" },
    { key = "A", label = "Arena", available = function() return ns.Arena ~= nil and ns.Arena.Live() end },
    { key = "F", label = "Server Firsts" },
}
-- the tabs overlap by their art's see-through flanks
LB.TAB_W, LB.TAB_STEP = 100, 92
LB.tabs = {}
local function placeTab(b, n)
    b:ClearAllPoints()
    b:SetPoint("BOTTOMLEFT", body, "TOPLEFT", 16 + n * LB.TAB_STEP, -2)
end
for i, d in ipairs(tabDefs) do
    local b = UI.Button(bar, LB.TAB_W, 24, d.label, "strip")
    placeTab(b, i - 1)
    b:SetScript("OnClick", function()
        if PlaySound then
            PlaySound("igCharacterInfoTab")
        end
        LB.board = d.key
        LB.page = 1
        LB.Query()
        LB.Refresh()
    end)
    b.key = d.key
    b.available = d.available
    LB.tabs[i] = b
end

-- The board may be shown: Arena only with feature bit 65536.
function LB.Available(board)
    for _, b in ipairs(LB.tabs) do
        if b.key == board then
            return not b.available or b.available() and true or false
        end
    end
    return false
end

-- Stack the tabs without gaps, leaving out the ones whose available() says no.
function LB.LayoutTabs()
    local n = 0
    for _, b in ipairs(LB.tabs) do
        if not b.available or b.available() then
            placeTab(b, n)
            b:Show()
            n = n + 1
        else
            b:Hide()
        end
    end
end
LB.LayoutTabs()
local classDD = UI.Dropdown(bar, 120, function(value)
    LB.class = value
    LB.page = 1
    LB.Query()
end)
classDD:SetPoint("RIGHT", bar, "RIGHT", -10, 1)
local classLabel = UI.Text(bar, 12, C.gold)
classLabel:SetPoint("RIGHT", classDD, "LEFT", -6, 0)
classLabel:SetText("Class")
local dungeonDD = UI.Dropdown(bar, 120, function(value)
    if LB.board == "A" then
        LB.bracket = value
    else
        LB.dungeon = value
    end
    LB.page = 1
    LB.Query()
end)
dungeonDD:SetPoint("RIGHT", classLabel, "LEFT", -14, 0)
local dungeonLabel = UI.Text(bar, 12, C.gold)
dungeonLabel:SetPoint("RIGHT", dungeonDD, "LEFT", -6, 0)
dungeonLabel:SetText("Dungeon")
LB.filters = { season = seasonDD, class = classDD, dungeon = dungeonDD }

local PAD = 14
local ASIDE = 232
local MW = CW - 2 * PAD - ASIDE - 14
local BH = CH - LB.STRIP_H - 2 * PAD
local inner = CreateFrame("Frame", nil, body)
inner:SetPoint("TOPLEFT", body, "TOPLEFT", PAD, -PAD)
inner:SetPoint("BOTTOMRIGHT", body, "BOTTOMRIGHT", -PAD, PAD)

------------------------------------------------------------------------------------------------------
-- Podium: the first three on steps, each with its medal (the arena achievements' gold, silver and bronze axes)
------------------------------------------------------------------------------------------------------
local PODIUM_H = 180
local podium = CreateFrame("Frame", nil, inner)
podium:SetSize(MW, PODIUM_H)
podium:SetPoint("TOPLEFT", inner, "TOPLEFT", 0, 0)
LB.podium = podium
LB.MEDAL_ICONS = { "Achievement_Arena_2v2_7", "Achievement_Arena_2v2_3", "Achievement_Arena_2v2_1" }
local MEDALS = { { C.goldLight, PODIUM_H }, { C.silver, PODIUM_H - 24 }, { C.bronze, PODIUM_H - 44 } }
local PW = floor((MW - 24) / 3)
podium.boxes = {}
for rank = 1, 3 do
    local m = MEDALS[rank]
    local b = UI.Box(podium, PW, m[2], C.card, C.border, nil, "edge")
    local slot = ({ 2, 1, 3 })[rank]                 -- 2nd, 1st, 3rd from left
    local x = ({ 1, 0, 2 })[rank] * (PW + 12)
    b:SetPoint("BOTTOMLEFT", podium, "BOTTOMLEFT", x, 0)
    b.group = UI.Text(b, 12, C.text, "body", "CENTER")
    b.group:SetPoint("BOTTOMLEFT", b, "BOTTOMLEFT", 6, 72)
    b.group:SetPoint("BOTTOMRIGHT", b, "BOTTOMRIGHT", -6, 72)
    -- the medal as an icon with the place in its corner, as a stack count; it sits on the names, so every card has
    -- the same medal-to-name gap and the podium's step shows as space above the medal
    b.medal = UI.Icon(b, 38, LB.MEDAL_ICONS[rank])
    b.medal:SetPoint("BOTTOM", b.group, "TOP", 0, 4)
    b.rank = b.medal:CreateFontString(nil, "OVERLAY")
    b.rank:SetFont(UI.FONT_BODY, 14, "OUTLINE")
    b.rank:SetTextColor(1, 1, 1)
    b.rank:SetPoint("BOTTOMRIGHT", b.medal, "BOTTOMRIGHT", -1, 2)
    b.rank:SetText(tostring(rank))
    b.dungeon = UI.Text(b, 11, C.dim, "body", "CENTER")
    b.dungeon:SetPoint("BOTTOM", b, "BOTTOM", 0, 54)
    b.value = UI.Text(b, 22, m[1], "body", "CENTER")
    b.value:SetPoint("BOTTOM", b, "BOTTOM", 0, 26)
    b.time = UI.Text(b, 11, C.text, "body", "CENTER")
    b.time:SetPoint("BOTTOM", b, "BOTTOM", 0, 9)
    b.slot = slot
    b.valueColor = m[1]
    podium.boxes[rank] = b
end

------------------------------------------------------------------------------------------------------
-- Table: WhoFrame's column headers over rows with the quest log's highlight; a row's tooltip names the whole group
------------------------------------------------------------------------------------------------------
local ROW_H, TABLE_GAP = 24, 10
local tbl = UI.Box(inner, MW, BH - PODIUM_H - TABLE_GAP, C.card, C.border, nil, "edge")
tbl:SetPoint("TOPLEFT", podium, "BOTTOMLEFT", 0, -TABLE_GAP)
LB.table = tbl
local headerRow = CreateFrame("Frame", nil, tbl)
headerRow:SetPoint("TOPLEFT", tbl, "TOPLEFT", 1, -1)
headerRow:SetPoint("TOPRIGHT", tbl, "TOPRIGHT", -1, -1)
headerRow:SetHeight(24)
headerRow.cols, headerRow.cells = {}, {}
for i = 1, 6 do
    local h = UI.ColumnHeader(headerRow, 60, "")
    headerRow.cols[i] = h
    headerRow.cells[i] = h.label
end
LB.headerRow = headerRow

local function hideTooltip()
    if GameTooltip then
        GameTooltip:Hide()
    end
end

tbl.rows = {}
for i = 1, LB.ROWS do
    local r = CreateFrame("Button", nil, tbl)
    r:SetSize(MW - 2, ROW_H)
    r:SetPoint("TOPLEFT", headerRow, "BOTTOMLEFT", 0, -2 - (i - 1) * ROW_H)
    r:SetHighlightTexture(UI.STOCK.rowHighlight, "ADD")
    r.cells = {}
    for c = 1, 6 do
        r.cells[c] = UI.Text(r, 12, c == 4 and C.goldLight or C.text)
    end
    r:SetScript("OnEnter", function(self)
        if self.tip then
            UI.ShowTooltip(self, self.tip)
        end
    end)
    r:SetScript("OnLeave", hideTooltip)
    tbl.rows[i] = r
end
tbl.empty = UI.Text(tbl, 13, C.dim, "body", "CENTER")
tbl.empty:SetPoint("CENTER")
-- the spellbook's page arrows with "Page 1 / 3" between them
tbl.next = UI.PageButton(tbl, "Next")
tbl.next:SetPoint("BOTTOMRIGHT", tbl, "BOTTOMRIGHT", -6, 2)
tbl.pageText = UI.Text(tbl, 12, C.text, "body", "CENTER")
tbl.pageText:SetPoint("RIGHT", tbl.next, "LEFT", -4, 0)
tbl.pageText:SetWidth(90)
tbl.prev = UI.PageButton(tbl, "Prev")
tbl.prev:SetPoint("RIGHT", tbl.pageText, "LEFT", -4, 0)
tbl.prev:SetScript("OnClick", function()
    if LB.page > 1 then
        LB.page = LB.page - 1
        LB.Query()
    end
end)
tbl.next:SetScript("OnClick", function()
    local data = S.lb[LB.board]
    if data and LB.page < data.pages then
        LB.page = LB.page + 1
        LB.Query()
    end
end)

-- Columns from 10 px in: each header as wide as its column (the last one to the table's edge), its label over the
-- column's text.
local function layoutColumns(widths)
    local x, last = 10, 0
    for i = 1, 6 do
        if (widths[i] or 0) > 0 then
            last = i
        end
    end
    for i = 1, 6 do
        local w = widths[i] or 0
        local col = headerRow.cols[i]
        col:ClearAllPoints()
        if w > 0 then
            local cw = i == last and (MW - 2 - (x - 9)) or w
            col:SetWidth(cw)
            col:SetPoint("TOPLEFT", headerRow, "TOPLEFT", x - 9, 0)
            UI.OneLine(col.label, max(1, cw - 12))
            col:Show()
        else
            col:Hide()
        end
        for _, r in ipairs(tbl.rows) do
            local cell = r.cells[i]
            cell:ClearAllPoints()
            if w > 0 then
                -- one line, cut with "..." (the row's tooltip has the whole text)
                cell:SetPoint("LEFT", r, "LEFT", x, 0)
                UI.OneLine(cell, w - 6)
                cell:Show()
            else
                cell:Hide()
            end
        end
        x = x + w
    end
end

------------------------------------------------------------------------------------------------------
-- Aside
------------------------------------------------------------------------------------------------------
local best = UI.Box(inner, ASIDE, 150, C.card, C.border, nil, "edge")
best:SetPoint("TOPRIGHT", inner, "TOPRIGHT", 0, 0)
best.label = UI.Label(best, "Your Best")
best.label:SetPoint("TOPLEFT", best, "TOPLEFT", 14, -14)
best.value = UI.Text(best, 24, C.goldPale)
best.value:SetPoint("TOPLEFT", best.label, "BOTTOMLEFT", 0, -6)
best.detail = UI.Text(best, 12, C.text)
best.detail:SetPoint("TOPLEFT", best.value, "BOTTOMLEFT", 0, -4)
UI.OneLine(best.detail, ASIDE - 26)
best.bar = UI.Bar(best, ASIDE - 38, 14)
best.bar:SetPoint("TOPLEFT", best.detail, "BOTTOMLEFT", 5, -10)
best.rank = UI.Text(best, 11, C.dim)
best.rank:SetPoint("TOPLEFT", best.bar, "BOTTOMLEFT", -5, -9)
LB.best = best

local firsts = UI.Box(inner, ASIDE, 206, C.card, C.border, nil, "edge")
firsts:SetPoint("TOPRIGHT", best, "BOTTOMRIGHT", 0, -10)
firsts.label = UI.Label(firsts, "Latest Server Firsts")
firsts.label:SetPoint("TOPLEFT", firsts, "TOPLEFT", 14, -14)
firsts.items = {}
for i = 1, 3 do
    local it = CreateFrame("Frame", nil, firsts)
    it:SetSize(ASIDE - 28, 50)
    it:SetPoint("TOPLEFT", firsts, "TOPLEFT", 14, -38 - (i - 1) * 54)
    it.dot = UI.StatusDot(it, 14, "yellow")
    it.dot:SetPoint("TOPLEFT", it, "TOPLEFT", -2, -1)
    it.what = UI.Text(it, 12, C.text)
    it.what:SetPoint("TOPLEFT", it, "TOPLEFT", 16, 0)
    UI.OneLine(it.what, ASIDE - 44)
    it.who = UI.Text(it, 11, C.dim)
    it.who:SetPoint("TOPLEFT", it.what, "BOTTOMLEFT", 0, -3)
    UI.OneLine(it.who, ASIDE - 44)
    firsts.items[i] = it
end
LB.firsts = firsts

local site = UI.Button(inner, ASIDE, 22, "Full boards on bleakhold.com", "red", 12)
site:SetPoint("TOPRIGHT", firsts, "BOTTOMRIGHT", 0, -12)
site:SetScript("OnClick", function()
    local url = Comm.server.site or "bleakhold.com"
    UI.CopyBox("There is no web browser in game. Copy the address:", url)
end)
LB.site = site

------------------------------------------------------------------------------------------------------
-- Data
------------------------------------------------------------------------------------------------------
local function membersText(members, maxLen)
    if #members == 0 then
        return "-"
    end
    local parts, len = {}, 0
    for i, m in ipairs(members) do
        len = len + #m.name + 2
        if len > (maxLen or 40) and i > 1 then
            return table.concat(parts, ", ") .. " +" .. (#members - i + 1)
        end
        parts[#parts + 1] = U.Color(ns.ClassColor(m.classId), U.Safe(m.name))
    end
    return table.concat(parts, ", ")
end
LB.MembersText = membersText

local function dateText(epoch)
    return epoch and U.Date("%d %b %Y", epoch) or "-"
end

-- "61-9" from season wins and games (board A).
local function winLoss(row)
    if not row.wins or not row.games then
        return "-"
    end
    return row.wins .. "-" .. max(0, row.games - row.wins)
end

local ARENA_FLAG = { INACTIVE = 1, PROVISIONAL = 2, FINAL = 4 }
LB.ARENA_FLAG = ARENA_FLAG

local function arenaTier(row)
    if bit.band(row.flags or 0, ARENA_FLAG.PROVISIONAL) ~= 0 then
        return U.Color(C.mute, "Provisional")
    end
    return row.tierId and ns.Arena.TierText(row.tierId) or "-"
end

local function arenaLast(row)
    if bit.band(row.flags or 0, ARENA_FLAG.INACTIVE) ~= 0 then
        return U.Color(C.mute, "Inactive")
    end
    return row.date and U.Date("%d %b", row.date) or "-"
end

-- Board A: the team's name (a 1v1 player: the name in its class colour).
local function arenaName(row, maxLen)
    if #row.members == 1 or not row.label then
        return membersText(row.members, maxLen)
    end
    return U.Safe(row.label)
end

local function valueText(board, row)
    if board == "A" then
        return row.value and tostring(row.value) or "-"
    elseif board == "K" then
        return row.value and ("+" .. row.value) or "-"
    elseif board == "R" then
        return row.value and ("Floor " .. row.value) or "-"
    end
    return row.label and U.Safe(row.label) or "-"
end

local function timeText(board, row)
    if not row.timeSec then
        return "-"
    end
    if board == "K" then
        return row.timeSec >= 0 and U.Clock(row.timeSec) or ("-" .. U.Clock(-row.timeSec))
    end
    return U.Clock(math.abs(row.timeSec))
end

-- A row's tooltip: the place and the whole group (the row cuts long groups to "+2"), then what it did.
function LB.RowTip(board, row)
    local lines = { "Rank " .. row.rank .. "  -  " .. valueText(board, row) }
    if board == "A" and row.label and #row.members > 1 then
        lines[#lines + 1] = { U.Safe(row.label), C.text }
    end
    if #row.members > 0 then
        lines[#lines + 1] = { membersText(row.members, 1000), C.text, true }
    end
    if board == "K" and row.dungeonId and row.dungeonId > 0 then
        lines[#lines + 1] = { U.Safe(ns.DungeonName(row.dungeonId)) .. "  -  " .. timeText(board, row) .. " left", C.dim }
    elseif row.date then
        lines[#lines + 1] = { dateText(row.date), C.dim }
    end
    return lines
end

function LB.Query()
    local season = LB.season or Comm.server.seasonId or 0
    if LB.board == "A" and not LB.Available("A") then
        LB.board = "K"
    end
    if LB.board == "F" then
        Comm.Refresh("FIRSTS")
    elseif LB.board == "A" then
        Comm.Send("LBQ", "A", LB.arenaSeason or 0, LB.bracket or 3, LB.class or 0, LB.page)
        if not S.arena then
            ns.Arena.Ask(false)     -- the season choice comes from ARENA S
        end
    else
        Comm.Send("LBQ", LB.board, season, LB.dungeon or 0, LB.class or 0, LB.page)
    end
end

-- column widths add up to at most MW - 20
local HEADERS = {
    K = { { "Rank", 44 }, { "Group", 230 }, { "Dungeon", 140 }, { "Key", 40 }, { "Time Left", 72 }, { "Date", 80 } },
    R = { { "Rank", 44 }, { "Group", 230 }, { "Floor", 90 }, { "", 0 }, { "Time", 72 }, { "Date", 80 } },
    E = { { "Rank", 44 }, { "Group", 230 }, { "Boss", 140 }, { "", 0 }, { "Kill Time", 72 }, { "Date", 80 } },
    F = { { "", 0 }, { "What", 280 }, { "Who", 220 }, { "", 0 }, { "", 0 }, { "Date", 90 } },
    A = { { "Rank", 44 }, { "Player / Team", 230 }, { "Rating", 70 }, { "W-L", 80 }, { "Tier", 90 }, { "Last", 70 } },
}
LB.HEADERS = HEADERS
LB.BRACKET_ITEMS = { { value = 1, text = "1v1" }, { value = 2, text = "2v2" }, { value = 3, text = "3v3" },
    { value = 5, text = "5v5" } }

function LB.RefreshFilters()
    if LB.board == "A" then
        seasonDD:SetItems(ns.Arena.SeasonItems())
        seasonDD:SetValue(LB.arenaSeason or 0, true)
        dungeonDD:SetItems(LB.BRACKET_ITEMS)
        dungeonDD:SetValue(LB.bracket or 3, true)
        dungeonLabel:SetText("Bracket")
        local classes = { { value = 0, text = "All classes" } }
        for _, c in ipairs(ns.Classes()) do
            classes[#classes + 1] = { value = c.id, text = c.name }
        end
        classDD:SetItems(classes)
        classDD:SetValue(LB.class or 0, true)
        for _, w in ipairs({ classDD, classLabel, dungeonDD, dungeonLabel }) do
            w:Show()
        end
        return
    end
    dungeonLabel:SetText("Dungeon")
    local seasons = {}
    for _, id in ipairs(ns.DefIds("S")) do
        seasons[#seasons + 1] = { value = id, text = ns.DefName("S", id, "Season " .. id) }
    end
    seasonDD:SetItems(seasons)
    seasonDD:SetValue(LB.season or Comm.server.seasonId or (seasons[1] and seasons[1].value), true)
    local dungeons = { { value = 0, text = "All dungeons" } }
    for _, id in ipairs(ns.DefIds("D")) do
        local d = ns.Def("D", id)
        if d and d.timeLimitSec then
            dungeons[#dungeons + 1] = { value = id, text = d.name or ("Dungeon " .. id) }
        end
    end
    dungeonDD:SetItems(dungeons)
    dungeonDD:SetValue(LB.dungeon or 0, true)
    local classes = { { value = 0, text = "All classes" } }
    for _, c in ipairs(ns.Classes()) do
        classes[#classes + 1] = { value = c.id, text = c.name }
    end
    classDD:SetItems(classes)
    classDD:SetValue(LB.class or 0, true)
    local showFilters = LB.board ~= "F"
    for _, w in ipairs({ classDD, classLabel, dungeonDD, dungeonLabel }) do
        if showFilters then w:Show() else w:Hide() end
    end
    if LB.board ~= "K" then
        dungeonDD:Hide()
        dungeonLabel:Hide()
    end
end

function LB.Refresh()
    if not win:IsShown() then
        return
    end
    LB.LayoutTabs()
    if not LB.Available(LB.board) then
        LB.board = "K"
    end
    for _, b in ipairs(LB.tabs) do
        b:SetStyle(b.key == LB.board and "stripOn" or "strip")
    end
    LB.RefreshFilters()
    local board = LB.board
    local hdr = HEADERS[board]
    local widths = {}
    for i, h in ipairs(hdr) do
        headerRow.cols[i]:SetLabel(h[1])
        widths[i] = h[2]
    end
    layoutColumns(widths)

    local rows = {}
    local data = S.lb[board]
    if board == "F" then
        podium:Hide()
        tbl:ClearAllPoints()
        tbl:SetPoint("TOPLEFT", inner, "TOPLEFT", 0, 0)
        tbl:SetHeight(BH)
        for _, fst in ipairs(S.firsts or {}) do
            rows[#rows + 1] = { "", U.Safe(fst.text), U.Safe(fst.who or "-"), "", "", dateText(fst.date),
                tip = { U.Safe(fst.text), { U.Safe(fst.who or "-"), C.text, true }, { dateText(fst.date), C.dim } } }
        end
        tbl.pageText:SetText("")
        tbl.prev:Hide()
        tbl.next:Hide()
    else
        podium:Show()
        tbl:ClearAllPoints()
        tbl:SetPoint("TOPLEFT", podium, "BOTTOMLEFT", 0, -TABLE_GAP)
        tbl:SetHeight(BH - PODIUM_H - TABLE_GAP)
        local list = data and data.rows or {}
        for rank = 1, 3 do
            local b = podium.boxes[rank]
            local row
            for _, r in ipairs(list) do
                if r.rank == rank then row = r end
            end
            UI.SetColor(b.value, b.valueColor)
            if row and board == "A" then
                b.group:SetText(arenaName(row, 22))
                b.dungeon:SetText(#row.members > 1 and membersText(row.members, 26) or "")
                b.value:SetText(valueText(board, row))
                UI.SetColor(b.value, row.tierId and ns.Arena.TierColor(row.tierId) or b.valueColor)
                b.time:SetText(arenaTier(row) .. "  -  " .. winLoss(row))
            elseif row and board == "E" then
                -- Raid Echoes rank the kill time: the boss small, the time big in the medal's colour, then the date
                b.group:SetText(membersText(row.members, 22))
                b.dungeon:SetText(U.Safe(row.label))
                b.value:SetText(timeText(board, row))
                b.time:SetText(dateText(row.date))
            elseif row then
                b.group:SetText(membersText(row.members, 22))
                UI.SetText(b.dungeon, board == "K" and ns.DungeonName(row.dungeonId) or "")
                b.value:SetText(valueText(board, row))
                b.time:SetText(board == "K" and (timeText(board, row) .. " left") or timeText(board, row))
            else
                b.group:SetText("-")
                b.dungeon:SetText("")
                b.value:SetText("")
                b.time:SetText("")
            end
        end
        for _, r in ipairs(list) do
            if board == "A" and (r.rank > 3 or (data and data.page and data.page > 1)) then
                rows[#rows + 1] = {
                    tostring(r.rank), arenaName(r, 34), valueText(board, r), winLoss(r), arenaTier(r), arenaLast(r),
                    tip = LB.RowTip(board, r),
                }
            elseif r.rank > 3 or (data and data.page and data.page > 1) then
                rows[#rows + 1] = {
                    tostring(r.rank), membersText(r.members, 34),
                    board == "K" and U.Safe(ns.DungeonName(r.dungeonId)) or valueText(board, r),
                    board == "K" and valueText(board, r) or "",
                    timeText(board, r), dateText(r.date),
                    tip = LB.RowTip(board, r),
                }
            end
        end
        local pages = data and data.pages or 1
        tbl.pageText:SetText("Page " .. (data and data.page or 1) .. " / " .. pages)
        tbl.prev:Show()
        tbl.next:Show()
        tbl.prev:SetActive(LB.page > 1)
        tbl.next:SetActive(LB.page < pages)
    end
    for i, r in ipairs(tbl.rows) do
        local row = rows[i]
        for c = 1, 6 do
            r.cells[c]:SetText(row and row[c] or "")
        end
        r.tip = row and row.tip or nil
        if row then r:Show() else r:Hide() end
    end
    if #rows == 0 then
        tbl.empty:SetText(Comm.ready and (data or board == "F") and "Nothing here yet." or "Waiting for the server...")
        tbl.empty:Show()
    else
        tbl.empty:Hide()
    end

    -- your best (Arena: your standing in the shown bracket)
    local me = S.lbme[board == "F" and "K" or board]
    best.label:SetLabel(board == "A" and "Your Standing" or "Your Best")
    UI.SetColor(best.value, C.goldPale)
    if board == "A" then
        LB.RefreshStanding(me, data)
    elseif me and (me.value or me.rank) then
        best.value:SetText(valueText(board == "F" and "K" or board, me))
        local detail = {}
        if me.dungeonId and me.dungeonId > 0 then detail[#detail + 1] = U.Safe(ns.DungeonName(me.dungeonId)) end
        if me.timeSec then detail[#detail + 1] = timeText(board, me) .. (board == "K" and " left" or "") end
        best.detail:SetText(table.concat(detail, "  -  "))
        best.bar:SetProgress((me.barPermille or 0) / 1000)
        local rk = {}
        if me.rank then rk[#rk + 1] = "Rank " .. me.rank end
        if me.topPercent then rk[#rk + 1] = "top " .. me.topPercent .. "% of the server" end
        best.rank:SetText(table.concat(rk, "  -  "))
    else
        best.value:SetText("-")
        best.detail:SetText("No ranked run yet")
        best.bar:SetProgress(0)
        best.rank:SetText("")
    end

    -- latest firsts
    for i, it in ipairs(firsts.items) do
        local fst = S.firsts and S.firsts[i]
        if fst then
            UI.SetText(it.what, fst.text)
            UI.SetText(it.who, (fst.who or "") .. (fst.date and ("  -  " .. (dateText(fst.date))) or ""))
            it:Show()
        else
            it:Hide()
        end
    end
end

-- "top 0.4%" below 10 % (topPermille), else "top 19%".
function LB.TopText(me)
    if me.topPermille and me.topPermille < 100 then
        return string.format("top %.1f%%", me.topPermille / 10)
    elseif me.topPercent then
        return "top " .. me.topPercent .. "%"
    end
    return nil
end

-- The aside on board A: the player's own team in the shown bracket (LBME A).
function LB.RefreshStanding(me, data)
    local final = false
    for _, r in ipairs(data and data.rows or {}) do
        if bit.band(r.flags or 0, ARENA_FLAG.FINAL) ~= 0 then
            final = true
        end
    end
    local bracket = ns.Arena.BracketName(LB.bracket)
    if me and (me.value or me.rank) then
        best.value:SetText(me.value and tostring(me.value) or "-")
        if me.tierId then
            UI.SetColor(best.value, ns.Arena.TierColor(me.tierId))
        end
        local name = me.label and U.Safe(me.label) or (me.tierId and U.Safe(ns.Arena.TierName(me.tierId))) or nil
        local tier = name and U.Color(me.tierId and ns.Arena.TierColor(me.tierId) or C.mid, name) or "No tier yet"
        best.detail:SetText(bracket .. "  -  " .. tier .. (final and "  -  final" or " pace"))
        best.bar:SetProgress((me.barPermille or 0) / 1000)
        local rk = {}
        if me.rank then rk[#rk + 1] = "Rank " .. me.rank end
        local top = LB.TopText(me)
        if top then rk[#rk + 1] = top end
        best.rank:SetText(table.concat(rk, "  -  "))
    else
        best.value:SetText("-")
        best.detail:SetText("No " .. bracket .. " team on this ladder")
        best.bar:SetProgress(0)
        best.rank:SetText(final and "Final standings" or "")
    end
end

-- Open the Arena board, on a bracket (1, 2, 3 or 5) when given.
function LB.OpenArena(bracket)
    if not LB.Available("A") then
        if ns.Arena then
            ns.Arena.Notice("Arena seasons are not running on this realm.")
        end
        return
    end
    if bracket == 1 or bracket == 2 or bracket == 3 or bracket == 5 then
        LB.bracket = bracket
    end
    LB.board = "A"
    LB.page = 1
    if win:IsShown() then
        LB.Query()
        LB.Refresh()
    else
        win:Show()
    end
end

function win:OnOpen()
    LB.Query()
    Comm.Get("FIRSTS")
    LB.Refresh()
end

ns.On("STATE", function(topic)
    if topic == "LB" or topic == "FIRSTS" or topic == "DEF" or (topic == "ARENA" and LB.board == "A") then
        LB.Refresh()
    end
end)

ns.On("HELLO", function()
    LB.LayoutTabs()
    if win:IsShown() then
        LB.Query()
        LB.Refresh()
    end
end)

local function open(board, toggle)
    if toggle and win:IsShown() and (not board or board == LB.board) then
        win:Hide()
        return
    end
    if board then
        LB.board = board
        LB.page = 1
    end
    if win:IsShown() then
        LB.Query()
        LB.Refresh()
    else
        win:Show()
    end
end

UI.RegisterOpener("leaderboards", function(toggle) open(nil, toggle) end)
UI.RegisterOpener("leaderboards-rift", function(toggle) open("R", toggle) end)
UI.RegisterOpener("leaderboards-arena", function(toggle)
    if toggle and win:IsShown() and LB.board == "A" then
        win:Hide()
    else
        LB.OpenArena()
    end
end)
ns.AddCommand("leaderboards", "open Leaderboards", function() open(nil, true) end)
ns.AddCommand("lb", "open Leaderboards", function() open(nil, true) end)
