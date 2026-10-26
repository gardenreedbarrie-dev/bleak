-- Bleakhold: Activities - Dungeons. The Dungeon Journey board (chapters, dungeon cards, tier, group
-- size, best score, server record, daily bounty, double Shards marker, Shards) and the queue panel
-- (dungeon or Eclipse Rift, join/leave, status, the server's level band, group proposal).
-- Every button sends an intent; what is unlocked, matched or paid is decided by the server.
local ADDON, ns = ...
local U, UI, Comm, Data = ns.U, ns.UI, ns.Comm, ns.Data
local C = UI.C
local S = ns.S
local A = ns.Activities

local floor, max, min = math.floor, math.max, math.min

local P = A.NewPage()
A.AddPage("dungeons", P)
ns.Dungeons = P

local QW = 250
local LW = A.PW - QW - 14

P.tier = 1           -- 1 Normal, 2 Veteran, 3 Elite, 4 Nightmare (QJOIN sends tier-1)
P.size = 5
P.kind = "D"         -- D dungeon, R Eclipse Rift
P.roles = 4          -- bits: 1 tank, 2 healer, 4 damage
P.selected = nil

------------------------------------------------------------------------------------------------------
-- Top cards: Shards, daily bounty, first run of the day
------------------------------------------------------------------------------------------------------
local cardW = floor((LW - 20) / 3)
local function topCard(i, glyph, label)
    local c = UI.Box(P, cardW, 62, C.card, C.border)
    c:SetPoint("TOPLEFT", P, "TOPLEFT", (i - 1) * (cardW + 10), 0)
    c.icon = UI.Badge(c, 36, glyph, C.chip, C.gold)
    c.icon:SetPoint("LEFT", c, "LEFT", 12, 0)
    c.label = UI.Text(c, 10, C.dim)
    c.label:SetPoint("TOPLEFT", c, "TOPLEFT", 58, -11)
    c.label:SetText(label)
    c.value = UI.Text(c, 14, C.text)
    c.value:SetPoint("TOPLEFT", c.label, "BOTTOMLEFT", 0, -3)
    UI.OneLine(c.value, cardW - 66)
    c.sub = UI.Text(c, 11, C.dim)
    c.sub:SetPoint("TOPLEFT", c.value, "BOTTOMLEFT", 0, -2)
    UI.OneLine(c.sub, cardW - 66)
    return c
end
P.shardsCard = topCard(1, "shards", "SHARDS")
P.bountyCard = topCard(2, "bounty", "DAILY BOUNTY")
P.bonusCard = topCard(3, "reward", "FIRST RUN TODAY")
-- when the bounty is done, the Claim button takes the place of the sub line
P.bountyClaim = UI.Button(P.bountyCard, cardW - 66, 18, "Claim", "teal", 11)
P.bountyClaim:SetPoint("TOPLEFT", P.bountyCard.value, "BOTTOMLEFT", 0, -2)
P.bountyClaim:Hide()

------------------------------------------------------------------------------------------------------
-- Tier and group size
------------------------------------------------------------------------------------------------------
local tierLabel = UI.Text(P, 12, C.dim)
tierLabel:SetPoint("TOPLEFT", P, "TOPLEFT", 0, -82)
tierLabel:SetText("Tier")
P.tierButtons = {}
for i, name in ipairs(Data.tiers) do
    local b = UI.Button(P, 72, 24, name, "tab", 12)
    b:SetPoint("TOPLEFT", P, "TOPLEFT", 34 + (i - 1) * 76, -76)
    b:SetScript("OnClick", function()
        P.tier = i
        P:Refresh()
    end)
    P.tierButtons[i] = b
end
local sizeLabel = UI.Text(P, 12, C.dim)
sizeLabel:SetPoint("TOPLEFT", P, "TOPLEFT", 350, -82)
sizeLabel:SetText("Group")
P.sizeButtons = {}
for n = 1, 5 do
    local b = UI.Button(P, 26, 24, tostring(n), "tab", 12)
    b:SetPoint("TOPLEFT", P, "TOPLEFT", 394 + (n - 1) * 30, -76)
    b.tooltip = function()
        return { n == 1 and "Solo" or ("Group of " .. n), n == 1 and "Run it alone; the dungeon scales to one player." or "The dungeon scales to the group's size." }
    end
    b:SetScript("OnClick", function()
        P.size = n
        P:Refresh()
    end)
    P.sizeButtons[n] = b
end

------------------------------------------------------------------------------------------------------
-- Board list
------------------------------------------------------------------------------------------------------
local listBox = UI.Box(P, LW, A.PH - 112, C.rail, C.border)
listBox:SetPoint("TOPLEFT", P, "TOPLEFT", 0, -110)
local scroll = UI.Scroll(listBox)
scroll:SetPoint("TOPLEFT", listBox, "TOPLEFT", 6, -6)
scroll:SetPoint("BOTTOMRIGHT", listBox, "BOTTOMRIGHT", -6, 6)
scroll:SetSize(LW - 12, A.PH - 124)
P.scroll = scroll
P.empty = UI.Text(listBox, 13, C.dim, "body", "CENTER")
P.empty:SetPoint("CENTER")

local ROW_W = LW - 22
local headers = UI.Pool(function()
    local h = CreateFrame("Frame", nil, scroll.child)
    h:SetSize(ROW_W, 34)
    h.title = UI.Text(h, 14, C.goldLight, "title")
    h.title:SetPoint("BOTTOMLEFT", h, "BOTTOMLEFT", 4, 12)
    h.text = UI.Text(h, 11, C.dim)
    h.text:SetPoint("LEFT", h.title, "RIGHT", 10, 0)
    return h
end)
local rows = UI.Pool(function()
    local r = CreateFrame("Button", nil, scroll.child)
    r:SetSize(ROW_W, 42)
    UI.Backdrop(r, C.card, C.border)
    r.name = UI.Text(r, 13, C.text)
    r.name:SetPoint("TOPLEFT", r, "TOPLEFT", 10, -7)
    r.band = UI.Text(r, 11, C.dim)
    r.band:SetPoint("TOPLEFT", r.name, "BOTTOMLEFT", 0, -3)
    r.best = UI.Text(r, 11, C.mid, "body", "RIGHT")
    r.best:SetPoint("TOPRIGHT", r, "TOPRIGHT", -10, -8)
    r.record = UI.Text(r, 11, C.dim, "body", "RIGHT")
    r.record:SetPoint("TOPRIGHT", r.best, "BOTTOMRIGHT", 0, -3)
    r.bounty = UI.Pill(r, "BOUNTY", "3A2A1A", C.orange, C.orange, 10)
    r.bounty:SetPoint("LEFT", r, "LEFT", 230, 0)
    r:RegisterForClicks("LeftButtonUp")
    return r
end)

function P.TierAllowed(d, tier)
    return bit.band(d.tierBits or 0, bit.lshift(1, (tier or 1) - 1)) ~= 0
end

local function selectDungeon(id)
    P.selected = id
    P.kind = "D"
    P:Refresh()
end

function P:RefreshList()
    headers:ReleaseAll()
    rows:ReleaseAll()
    local b = S.board
    if not b or #b.dungeons == 0 then
        UI.SetText(P.empty, Comm.ready and "The board is empty." or "Waiting for the server...")
        P.empty:Show()
        scroll:SetContentHeight(0)
        return
    end
    P.empty:Hide()
    local y, chapter = 0, nil
    local level = UnitLevel and UnitLevel("player") or 0
    for _, d in ipairs(b.dungeons) do
        if d.chapter ~= chapter then
            chapter = d.chapter
            local h = headers:Acquire()
            h:ClearAllPoints()
            h:SetPoint("TOPLEFT", scroll.child, "TOPLEFT", 0, -y)
            local cdef = ns.Def("C", chapter)
            UI.SetText(h.title, cdef and cdef.name or ("Chapter " .. tostring(chapter)))
            UI.SetText(h.text, cdef and cdef.text or "")
            y = y + 36
        end
        local r = rows:Acquire()
        r:ClearAllPoints()
        r:SetPoint("TOPLEFT", scroll.child, "TOPLEFT", 0, -y)
        y = y + 46
        local allowed = not d.locked and P.TierAllowed(d, P.tier)
        UI.SetText(r.name, ns.DungeonName(d.id))
        UI.SetColor(r.name, allowed and C.text or C.mute)
        local band = (d.lvlMin and d.lvlMax) and ("Level " .. d.lvlMin .. "-" .. d.lvlMax) or ""
        if d.locked then
            band = band .. "  -  locked"
        elseif not P.TierAllowed(d, P.tier) then
            band = band .. "  -  " .. Data.tiers[P.tier] .. " not unlocked"
        end
        UI.SetText(r.band, band)
        UI.SetColor(r.band, (d.lvlMin and level > 0 and level >= d.lvlMin and level <= (d.lvlMax or 255)) and C.teal or C.dim)
        if d.bestScore then
            UI.SetText(r.best, "Best " .. U.Commas(d.bestScore) .. (d.bestTier and Data.tiers[d.bestTier + 1] and (" (" .. Data.tiers[d.bestTier + 1] .. ")") or ""))
        else
            r.best:SetText("No run yet")
        end
        if d.recordScore then
            UI.SetText(r.record, "Server record " .. U.Commas(d.recordScore) .. (d.recordName and (" - " .. d.recordName) or ""))
        else
            r.record:SetText("")
        end
        if b.bountyDungeon == d.id and (b.bountyState or 0) > 0 then
            r.bounty:Show()
        else
            r.bounty:Hide()
        end
        UI.Colors(r, P.selected == d.id and P.kind == "D" and C.active or C.card, P.selected == d.id and P.kind == "D" and C.gold or C.border)
        r:SetScript("OnClick", function()
            selectDungeon(d.id)
        end)
    end
    scroll:SetContentHeight(y)
end

------------------------------------------------------------------------------------------------------
-- Queue panel
------------------------------------------------------------------------------------------------------
local q = UI.Box(P, QW, A.PH - 76, C.card, C.border)
q:SetPoint("TOPRIGHT", P, "TOPRIGHT", 0, 0)
P.queue = q
q.label = UI.Text(q, 11, C.dim)
q.label:SetPoint("TOPLEFT", q, "TOPLEFT", 12, -12)
q.label:SetText("FIND A GROUP")
q.dungeon = UI.Button(q, 110, 26, "Dungeon", "tab", 12)
q.dungeon:SetPoint("TOPLEFT", q, "TOPLEFT", 12, -32)
q.rift = UI.Button(q, 110, 26, "Eclipse Rift", "tab", 12)
q.rift:SetPoint("TOPRIGHT", q, "TOPRIGHT", -12, -32)
q.dungeon:SetScript("OnClick", function()
    P.kind = "D"
    P:Refresh()
end)
q.rift:SetScript("OnClick", function()
    P.kind = "R"
    P:Refresh()
end)
q.target = UI.Text(q, 15, C.goldPale, "title")
q.target:SetPoint("TOPLEFT", q, "TOPLEFT", 12, -70)
UI.OneLine(q.target, QW - 24)
q.detail = UI.Text(q, 11, C.dim)
q.detail:SetPoint("TOPLEFT", q.target, "BOTTOMLEFT", 0, -4)
UI.OneLine(q.detail, QW - 24)
q.rolesLabel = UI.Text(q, 11, C.dim)
q.rolesLabel:SetPoint("TOPLEFT", q, "TOPLEFT", 12, -122)
q.rolesLabel:SetText("ROLES")
q.roleButtons = {}
local roleDefs = { { 1, "Tank" }, { 2, "Healer" }, { 4, "Damage" } }
for i, rd in ipairs(roleDefs) do
    local b = UI.Button(q, 72, 24, rd[2], "tab", 11)
    b:SetPoint("TOPLEFT", q, "TOPLEFT", 12 + (i - 1) * 76, -140)
    b:SetScript("OnClick", function()
        local bitv = rd[1]
        local newRoles = bit.bxor(P.roles, bitv)
        if newRoles ~= 0 then
            P.roles = newRoles
        end
        P:Refresh()
    end)
    q.roleButtons[i] = { button = b, bit = rd[1] }
end
q.join = UI.Button(q, QW - 24, 36, "Find group", "gold", 14)
q.join:SetPoint("TOPLEFT", q, "TOPLEFT", 12, -176)
q.status = UI.Text(q, 13, C.text)
q.status:SetPoint("TOPLEFT", q, "TOPLEFT", 12, -226)
UI.OneLine(q.status, QW - 24)
q.timer = UI.Text(q, 12, C.mid)
q.timer:SetPoint("TOPLEFT", q.status, "BOTTOMLEFT", 0, -4)
UI.OneLine(q.timer, QW - 24)
q.band = UI.Text(q, 12, C.teal)
q.band:SetPoint("TOPLEFT", q.timer, "BOTTOMLEFT", 0, -4)
UI.OneLine(q.band, QW - 24)
q.members = {}
for i = 1, 5 do
    local m = UI.Text(q, 12, C.text)
    m:SetPoint("TOPLEFT", q, "TOPLEFT", 12, -298 - (i - 1) * 18)
    UI.OneLine(m, QW - 24)
    q.members[i] = m
end
q.accept = UI.Button(q, (QW - 30) / 2, 30, "Accept", "teal", 13)
q.accept:SetPoint("BOTTOMLEFT", q, "BOTTOMLEFT", 12, 12)
q.decline = UI.Button(q, (QW - 30) / 2, 30, "Decline", "dark", 13)
q.decline:SetPoint("BOTTOMRIGHT", q, "BOTTOMRIGHT", -12, 12)

local ROLE_SHORT = { [1] = "T", [2] = "H", [4] = "D" }

local function queueState()
    return S.queue and S.queue.state or 0
end

local function joinIntent()
    if P.kind == "R" then
        return "R", 0, 0
    end
    return "D", P.selected, P.tier - 1
end

q.join:SetScript("OnClick", function()
    local st = queueState()
    if st == 1 or st == 2 then
        Comm.Send("QLEAVE")
        return
    end
    local kind, activity, tier = joinIntent()
    if kind == "D" and not activity then
        return
    end
    Comm.Send("QJOIN", kind, activity, tier, P.roles, P.size)
end)

q.accept:SetScript("OnClick", function()
    local qs = S.queue
    if qs and qs.proposalId then
        Comm.Send("QREPLY", qs.proposalId, 1)
    end
end)
q.decline:SetScript("OnClick", function()
    local qs = S.queue
    if qs and qs.proposalId then
        Comm.Send("QREPLY", qs.proposalId, 0)
    end
end)

local QUEUE_TEXT = { [0] = "Not queued", [1] = "In queue", [2] = "Group found", [3] = "In a run" }

function P:QueueTick()
    local qs = S.queue
    if not qs then
        q.timer:SetText("")
        return
    end
    local since = GetTime() - (qs.recvAt or GetTime())
    if qs.state == 1 then
        local txt = "Waiting " .. U.Clock((qs.queuedSec or 0) + since)
        if qs.estWaitSec then
            txt = txt .. "  -  estimated " .. U.Clock(qs.estWaitSec)
        end
        q.timer:SetText(txt)
    elseif qs.state == 2 then
        local left = qs.timeoutSec and max(0, qs.timeoutSec - since)
        q.timer:SetText(left and ("Answer within " .. floor(left) .. " s") or "")
    else
        q.timer:SetText("")
    end
end

function P:RefreshQueue()
    q.dungeon:SetStyle(P.kind == "D" and "tabOn" or "tab")
    q.rift:SetStyle(P.kind == "R" and "tabOn" or "tab")
    for _, rb in ipairs(q.roleButtons) do
        rb.button:SetStyle(bit.band(P.roles, rb.bit) ~= 0 and "tabOn" or "tab")
    end
    local d = P.selected and S.board and S.board.byId[P.selected]
    if P.kind == "R" then
        q.target:SetText("Eclipse Rift")
        q.detail:SetText("Endless boss rush, alone or in a group.")
    elseif P.selected then
        UI.SetText(q.target, ns.DungeonName(P.selected))
        q.detail:SetText(Data.tiers[P.tier] .. "  -  " .. (P.size == 1 and "solo" or ("group of " .. P.size)))
    else
        q.target:SetText("Pick a dungeon")
        q.detail:SetText("Choose one on the board, or the Eclipse Rift.")
    end
    local st = queueState()
    local qs = S.queue
    UI.SetText(q.status, QUEUE_TEXT[st] or "")
    if qs and st ~= 0 then
        local what = qs.kind == "R" and "Eclipse Rift"
            or (qs.kind == "B" and "Bleakhold Royale")
            or (qs.kind == "A" and (qs.tier == 1 and "Rated 1v1 arena" or "1v1 arena skirmish"))
            or ns.DungeonName(qs.activityId)
        local match = (qs.kind == "B" or qs.kind == "A") and st == 3
        UI.SetText(q.status, (match and "In a match" or (QUEUE_TEXT[st] or "")) .. ": " .. what)
    end
    if qs and qs.bandMin and qs.bandMax and st ~= 0 then
        q.band:SetText("Matching levels " .. qs.bandMin .. "-" .. qs.bandMax)
    else
        q.band:SetText("")
    end
    if st == 1 or st == 2 then
        q.join:SetLabel("Leave queue")
        q.join:SetStyle("dark")
        q.join:SetActive(true)
    elseif st == 3 then
        q.join:SetLabel("In a run")
        q.join:SetActive(false)
    else
        q.join:SetLabel(P.size == 1 and "Enter solo" or "Find group")
        q.join:SetStyle("gold")
        local canJoin = P.kind == "R" or (d and not d.locked and P.TierAllowed(d, P.tier))
        q.join:SetActive(canJoin and true or false)
    end
    for i, m in ipairs(q.members) do
        local mem = qs and st >= 2 and qs.members[i]
        if mem then
            local mark = mem.accepted == 1 and "  ready" or (mem.accepted == 2 and "  declined" or "")
            m:SetText(U.Color(ns.ClassColor(mem.classId), U.Safe(mem.name)) .. "  " .. (ROLE_SHORT[mem.role] or "") .. (mem.level and ("  " .. mem.level) or "") .. mark)
        else
            m:SetText("")
        end
    end
    if st == 2 and qs.proposalId then
        q.accept:Show()
        q.decline:Show()
    else
        q.accept:Hide()
        q.decline:Hide()
    end
    P:QueueTick()
end

function P:RefreshTop()
    local b = S.board
    local w = S.week
    local shards = (b and b.shards) or (w and w.shards)
    P.shardsCard.value:SetText(shards and U.Commas(shards) or "-")
    P.shardsCard.sub:SetText("From board runs")
    if b and b.bountyDungeon and b.bountyState > 0 then
        UI.SetText(P.bountyCard.value, ns.DungeonName(b.bountyDungeon))
        local stateText = ({ [1] = "open", [2] = "done", [3] = "claimed" })[b.bountyState] or ""
        UI.SetText(P.bountyCard.sub, (b.bountyReward and (b.bountyReward .. ", ") or "") .. stateText)
    else
        P.bountyCard.value:SetText("-")
        P.bountyCard.sub:SetText(b and "No bounty today" or "")
    end
    local claimable = b and b.bountyState == 2 and b.bountyId
    if claimable then
        P.bountyCard.sub:Hide()
        P.bountyClaim:SetLabel("Claim " .. U.Safe(b.bountyReward or "bounty"))
        P.bountyClaim:Show()
        P.bountyClaim:SetScript("OnClick", function()
            Comm.Send("BCLAIM", b.bountyId)
        end)
    else
        P.bountyCard.sub:Show()
        P.bountyClaim:Hide()
    end
    if b and b.firstRunBonus then
        P.bonusCard.value:SetText("Double Shards")
        P.bonusCard.sub:SetText("On your first run today")
        UI.SetColor(P.bonusCard.value, C.teal)
    else
        P.bonusCard.value:SetText(b and "Used today" or "-")
        P.bonusCard.sub:SetText(b and "Back after the reset" or "")
        UI.SetColor(P.bonusCard.value, C.text)
    end
end

function P:Refresh()
    for i, tb in ipairs(P.tierButtons) do
        tb:SetStyle(i == P.tier and "tabOn" or "tab")
    end
    for n, sb in ipairs(P.sizeButtons) do
        sb:SetStyle(n == P.size and "tabOn" or "tab")
    end
    P:RefreshTop()
    P:RefreshList()
    P:RefreshQueue()
end

function P:Tick()
    P:QueueTick()
end

function P:OnOpen()
    Comm.Refresh("BOARD")
    Comm.Get("QUEUE")
end

-- The queue timers count every second while the page is open.
P:SetScript("OnUpdate", function(self, elapsed)
    self.acc = (self.acc or 0) + (elapsed or 0)
    if self.acc >= 0.5 then
        self.acc = 0
        P:QueueTick()
    end
end)
