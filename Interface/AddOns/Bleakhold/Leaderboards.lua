-- Bleakhold: Leaderboards window. Tabs Mythic Keys / Eclipse Rift / Raid Echoes / Server Firsts,
-- season, dungeon and class filters, top-three podium, ranked table with pages, your best and the
-- latest server firsts. The server ranks everything; the client only asks for pages (LBQ).
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
LB.ROWS = 8

local win = UI.Window("BleakholdLeaderboardsFrame", LB.W, LB.H, "LEADERBOARDS", "trophy")
LB.frame = win

------------------------------------------------------------------------------------------------------
-- Header: season
------------------------------------------------------------------------------------------------------
local seasonDD = UI.Dropdown(win.header, 190, function(value)
    LB.season = value
    LB.page = 1
    LB.Query()
end)
seasonDD:SetPoint("RIGHT", win.close, "LEFT", -12, 0)
local seasonLabel = UI.Text(win.header, 12, C.dim)
seasonLabel:SetPoint("RIGHT", seasonDD, "LEFT", -6, 0)
seasonLabel:SetText("Season")

------------------------------------------------------------------------------------------------------
-- Tabs and filters
------------------------------------------------------------------------------------------------------
local bar = UI.Box(win.content, 10, 44, C.rail)
bar:SetPoint("TOPLEFT", win.content, "TOPLEFT", 0, 0)
bar:SetPoint("TOPRIGHT", win.content, "TOPRIGHT", 0, 0)
local tabDefs = {
    { key = "K", label = "Mythic Keys" },
    { key = "R", label = "Eclipse Rift" },
    { key = "E", label = "Raid Echoes" },
    { key = "F", label = "Server Firsts" },
}
LB.tabs = {}
for i, d in ipairs(tabDefs) do
    local b = UI.Button(bar, 118, 30, d.label, "tab", 13)
    b:SetPoint("LEFT", bar, "LEFT", 16 + (i - 1) * 124, 0)
    b:SetScript("OnClick", function()
        LB.board = d.key
        LB.page = 1
        LB.Query()
        LB.Refresh()
    end)
    b.key = d.key
    LB.tabs[i] = b
end
local classDD = UI.Dropdown(bar, 130, function(value)
    LB.class = value
    LB.page = 1
    LB.Query()
end)
classDD:SetPoint("RIGHT", bar, "RIGHT", -16, 0)
local classLabel = UI.Text(bar, 12, C.dim)
classLabel:SetPoint("RIGHT", classDD, "LEFT", -6, 0)
classLabel:SetText("Class")
local dungeonDD = UI.Dropdown(bar, 150, function(value)
    LB.dungeon = value
    LB.page = 1
    LB.Query()
end)
dungeonDD:SetPoint("RIGHT", classLabel, "LEFT", -14, 0)
local dungeonLabel = UI.Text(bar, 12, C.dim)
dungeonLabel:SetPoint("RIGHT", dungeonDD, "LEFT", -6, 0)
dungeonLabel:SetText("Dungeon")
LB.filters = { season = seasonDD, class = classDD, dungeon = dungeonDD }

local body = CreateFrame("Frame", nil, win.content)
body:SetPoint("TOPLEFT", bar, "BOTTOMLEFT", 18, -16)
body:SetPoint("BOTTOMRIGHT", win.content, "BOTTOMRIGHT", -18, 14)
local ASIDE = 260
local MW = LB.W - 2 - 36 - ASIDE - 16
local BH = LB.H - 4 - 46 - 44 - 30

------------------------------------------------------------------------------------------------------
-- Podium
------------------------------------------------------------------------------------------------------
local podium = CreateFrame("Frame", nil, body)
podium:SetSize(MW, 170)
podium:SetPoint("TOPLEFT", body, "TOPLEFT", 0, 0)
LB.podium = podium
local MEDALS = { { C.goldLight, C.gold, 170 }, { C.silver, "6B7078", 146 }, { C.bronze, "7A5A3E", 128 } }
local PW = floor((MW - 24) / 3)
podium.boxes = {}
for rank = 1, 3 do
    local m = MEDALS[rank]
    local b = UI.Box(podium, PW, m[3], C.card, m[2])
    local slot = ({ 2, 1, 3 })[rank]                 -- 2nd, 1st, 3rd from left
    local x = ({ 1, 0, 2 })[rank] * (PW + 12)
    b:SetPoint("BOTTOMLEFT", podium, "BOTTOMLEFT", x, 0)
    b.medal = UI.Disc(b, 34, m[1], "ARTWORK")
    b.medal:SetPoint("TOP", b, "TOP", 0, -12)
    b.rank = UI.Text(b, 16, C.bg, "title", "CENTER")
    b.rank:SetPoint("CENTER", b.medal, "CENTER", 0, 0)
    b.rank:SetText(tostring(rank))
    b.group = UI.Text(b, 12, C.text, "body", "CENTER")
    b.group:SetPoint("BOTTOMLEFT", b, "BOTTOMLEFT", 6, 70)
    b.group:SetPoint("BOTTOMRIGHT", b, "BOTTOMRIGHT", -6, 70)
    b.dungeon = UI.Text(b, 11, C.dim, "body", "CENTER")
    b.dungeon:SetPoint("BOTTOM", b, "BOTTOM", 0, 52)
    b.value = UI.Text(b, 22, m[1], "title", "CENTER")
    b.value:SetPoint("BOTTOM", b, "BOTTOM", 0, 24)
    b.time = UI.Text(b, 11, C.mid, "body", "CENTER")
    b.time:SetPoint("BOTTOM", b, "BOTTOM", 0, 8)
    b.slot = slot
    podium.boxes[rank] = b
end

------------------------------------------------------------------------------------------------------
-- Table
------------------------------------------------------------------------------------------------------
local tbl = UI.Box(body, MW, BH - 170 - 12, C.panel, C.border)
tbl:SetPoint("TOPLEFT", podium, "BOTTOMLEFT", 0, -12)
LB.table = tbl
local headerRow = UI.Box(tbl, MW - 2, 26, C.header)
headerRow:SetPoint("TOPLEFT", tbl, "TOPLEFT", 1, -1)
headerRow.cells = {}
for i = 1, 6 do
    local t = UI.Text(headerRow, 10, C.dim)
    headerRow.cells[i] = t
end
tbl.rows = {}
for i = 1, LB.ROWS do
    local r = UI.Box(tbl, MW - 2, 26, i % 2 == 1 and C.zebra or C.panel)
    r:SetPoint("TOPLEFT", headerRow, "BOTTOMLEFT", 0, -(i - 1) * 26)
    r.cells = {}
    for c = 1, 6 do
        r.cells[c] = UI.Text(r, 12, c == 1 and C.text or (c == 4 and C.goldLight or C.text))
    end
    tbl.rows[i] = r
end
tbl.empty = UI.Text(tbl, 13, C.dim, "body", "CENTER")
tbl.empty:SetPoint("CENTER")
tbl.prev = UI.Button(tbl, 28, 22, "", "dark")
tbl.prev.icon = UI.Glyph(tbl.prev, "left", 12, C.text)
tbl.prev.icon:SetPoint("CENTER")
tbl.prev:SetPoint("BOTTOMRIGHT", tbl, "BOTTOMRIGHT", -100, 6)
tbl.next = UI.Button(tbl, 28, 22, "", "dark")
tbl.next.icon = UI.Glyph(tbl.next, "right", 12, C.text)
tbl.next.icon:SetPoint("CENTER")
tbl.next:SetPoint("BOTTOMRIGHT", tbl, "BOTTOMRIGHT", -8, 6)
tbl.pageText = UI.Text(tbl, 11, C.dim, "body", "CENTER")
tbl.pageText:SetPoint("RIGHT", tbl.next, "LEFT", -6, 0)
tbl.pageText:SetWidth(56)
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

local function layoutColumns(widths)
    local x = 10
    for i = 1, 6 do
        local w = widths[i] or 0
        local cells = { headerRow.cells[i] }
        for _, r in ipairs(tbl.rows) do cells[#cells + 1] = r.cells[i] end
        for _, cell in ipairs(cells) do
            cell:ClearAllPoints()
            if w > 0 then
                cell:SetPoint("LEFT", cell:GetParent(), "LEFT", x, 0)
                cell:SetWidth(w - 6)
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
local best = UI.Box(body, ASIDE, 150, C.eraBg, C.eraBorder)
best:SetPoint("TOPRIGHT", body, "TOPRIGHT", 0, 0)
best.label = UI.Text(best, 11, C.dim)
best.label:SetPoint("TOPLEFT", best, "TOPLEFT", 14, -14)
best.label:SetText("YOUR BEST")
best.value = UI.Text(best, 24, C.goldPale, "title")
best.value:SetPoint("TOPLEFT", best.label, "BOTTOMLEFT", 0, -6)
best.detail = UI.Text(best, 12, C.text)
best.detail:SetPoint("TOPLEFT", best.value, "BOTTOMLEFT", 0, -4)
UI.OneLine(best.detail, ASIDE - 26)
best.bar = UI.Bar(best, ASIDE - 28, 6, C.gold, C.bg)
best.bar:SetPoint("TOPLEFT", best.detail, "BOTTOMLEFT", 0, -8)
best.rank = UI.Text(best, 11, C.dim)
best.rank:SetPoint("TOPLEFT", best.bar, "BOTTOMLEFT", 0, -5)
LB.best = best

local firsts = UI.Box(body, ASIDE, 200, C.card, C.border)
firsts:SetPoint("TOPRIGHT", best, "BOTTOMRIGHT", 0, -12)
firsts.label = UI.Text(firsts, 11, C.dim)
firsts.label:SetPoint("TOPLEFT", firsts, "TOPLEFT", 14, -14)
firsts.label:SetText("LATEST SERVER FIRSTS")
firsts.items = {}
for i = 1, 3 do
    local it = CreateFrame("Frame", nil, firsts)
    it:SetSize(ASIDE - 28, 50)
    it:SetPoint("TOPLEFT", firsts, "TOPLEFT", 14, -36 - (i - 1) * 54)
    it.dot = UI.Disc(it, 8, C.orange)
    it.dot:SetPoint("TOPLEFT", it, "TOPLEFT", 0, -5)
    it.what = UI.Text(it, 12, C.text)
    it.what:SetPoint("TOPLEFT", it, "TOPLEFT", 16, 0)
    UI.OneLine(it.what, ASIDE - 44)
    it.who = UI.Text(it, 11, C.dim)
    it.who:SetPoint("TOPLEFT", it.what, "BOTTOMLEFT", 0, -3)
    UI.OneLine(it.who, ASIDE - 44)
    firsts.items[i] = it
end
LB.firsts = firsts

local site = UI.Button(body, ASIDE, 38, "Full boards on bleakhold.com", "ghost", 13)
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

local function valueText(board, row)
    if board == "K" then
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

function LB.Query()
    local season = LB.season or Comm.server.seasonId or 0
    if LB.board == "F" then
        Comm.Refresh("FIRSTS")
    else
        Comm.Send("LBQ", LB.board, season, LB.dungeon or 0, LB.class or 0, LB.page)
    end
end

-- column widths add up to at most MW - 20
local HEADERS = {
    K = { { "RANK", 44 }, { "GROUP", 230 }, { "DUNGEON", 140 }, { "KEY", 40 }, { "TIME LEFT", 72 }, { "DATE", 80 } },
    R = { { "RANK", 44 }, { "GROUP", 230 }, { "FLOOR", 90 }, { "", 0 }, { "TIME", 72 }, { "DATE", 80 } },
    E = { { "RANK", 44 }, { "GROUP", 230 }, { "BOSS", 140 }, { "", 0 }, { "KILL TIME", 72 }, { "DATE", 80 } },
    F = { { "", 0 }, { "WHAT", 280 }, { "WHO", 220 }, { "", 0 }, { "", 0 }, { "DATE", 90 } },
}

function LB.RefreshFilters()
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
    for _, b in ipairs(LB.tabs) do
        b:SetStyle(b.key == LB.board and "tabOn" or "tab")
    end
    LB.RefreshFilters()
    local board = LB.board
    local hdr = HEADERS[board]
    local widths = {}
    for i, h in ipairs(hdr) do
        headerRow.cells[i]:SetText(h[1])
        widths[i] = h[2]
    end
    layoutColumns(widths)

    local rows = {}
    local data = S.lb[board]
    if board == "F" then
        podium:Hide()
        tbl:ClearAllPoints()
        tbl:SetPoint("TOPLEFT", body, "TOPLEFT", 0, 0)
        tbl:SetHeight(BH)
        for _, fst in ipairs(S.firsts or {}) do
            rows[#rows + 1] = { "", U.Safe(fst.text), U.Safe(fst.who or "-"), "", "", dateText(fst.date) }
        end
        tbl.pageText:SetText("")
        tbl.prev:Hide()
        tbl.next:Hide()
    else
        podium:Show()
        tbl:ClearAllPoints()
        tbl:SetPoint("TOPLEFT", podium, "BOTTOMLEFT", 0, -12)
        tbl:SetHeight(BH - 170 - 12)
        local list = data and data.rows or {}
        for rank = 1, 3 do
            local b = podium.boxes[rank]
            local row
            for _, r in ipairs(list) do
                if r.rank == rank then row = r end
            end
            if row then
                b.group:SetText(membersText(row.members, 22))
                UI.SetText(b.dungeon, board == "K" and ns.DungeonName(row.dungeonId) or (board == "E" and (row.label or "") or ""))
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
            if r.rank > 3 or (data and data.page and data.page > 1) then
                rows[#rows + 1] = {
                    tostring(r.rank), membersText(r.members, 34),
                    board == "K" and U.Safe(ns.DungeonName(r.dungeonId)) or valueText(board, r),
                    board == "K" and valueText(board, r) or "",
                    timeText(board, r), dateText(r.date),
                }
            end
        end
        local pages = data and data.pages or 1
        tbl.pageText:SetText((data and data.page or 1) .. " / " .. pages)
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
        if row then r:Show() else r:Hide() end
    end
    if #rows == 0 then
        tbl.empty:SetText(Comm.ready and (data or board == "F") and "Nothing here yet." or "Waiting for the server...")
        tbl.empty:Show()
    else
        tbl.empty:Hide()
    end

    -- your best
    local me = S.lbme[board == "F" and "K" or board]
    if me and (me.value or me.rank) then
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

function win:OnOpen()
    LB.Query()
    Comm.Get("FIRSTS")
    LB.Refresh()
end

ns.On("STATE", function(topic)
    if topic == "LB" or topic == "FIRSTS" or topic == "DEF" then
        LB.Refresh()
    end
end)

ns.On("HELLO", function()
    if win:IsShown() then
        LB.Query()
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
ns.AddCommand("leaderboards", "open Leaderboards", function() open(nil, true) end)
ns.AddCommand("lb", "open Leaderboards", function() open(nil, true) end)
