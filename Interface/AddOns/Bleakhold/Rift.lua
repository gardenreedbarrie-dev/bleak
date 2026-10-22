-- Bleakhold: Activities - Rift. Eclipse Rift run status (floor, boss, time), best floor, the last run's
-- summary and a link to the Rift leaderboard. The Rift's points and rewards are still open on the
-- server side, so this page shows only the fields the server sends and invents no rules.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S
local A = ns.Activities

local floor, max = math.floor, math.max

local P = A.NewPage()
A.AddPage("rift", P)
ns.Rift = P

local LEFT = 470
local RIGHT = A.PW - LEFT - 14

local head = UI.Box(P, A.PW, 96, C.eraBg, C.eraBorder)
head:SetPoint("TOPLEFT", P, "TOPLEFT", 0, 0)
head.badge = UI.Badge(head, 58, "rift", C.active, C.gold)
head.badge:SetPoint("LEFT", head, "LEFT", 16, 0)
head.label = UI.Text(head, 11, C.dim)
head.label:SetPoint("TOPLEFT", head, "TOPLEFT", 88, -18)
head.label:SetText("ECLIPSE RIFT")
head.title = UI.Text(head, 22, C.goldPale, "title")
head.title:SetPoint("TOPLEFT", head.label, "BOTTOMLEFT", 0, -4)
head.text = UI.Text(head, 12, C.mid)
head.text:SetPoint("TOPLEFT", head.title, "BOTTOMLEFT", 0, -4)
head.text:SetText("An endless boss rush, alone or in a group: every fallen boss brings the next.")
P.head = head

-- Current run
local run = UI.Box(P, LEFT, 170, C.card, C.border)
run:SetPoint("TOPLEFT", head, "BOTTOMLEFT", 0, -12)
run.label = UI.Text(run, 11, C.dim)
run.label:SetPoint("TOPLEFT", run, "TOPLEFT", 12, -12)
run.label:SetText("CURRENT RUN")
run.floor = UI.Text(run, 26, C.text, "title")
run.floor:SetPoint("TOPLEFT", run.label, "BOTTOMLEFT", 0, -8)
run.boss = UI.Text(run, 13, C.goldLight)
run.boss:SetPoint("TOPLEFT", run.floor, "BOTTOMLEFT", 0, -6)
run.time = UI.Text(run, 13, C.mid)
run.time:SetPoint("TOPLEFT", run.boss, "BOTTOMLEFT", 0, -6)
run.extra = UI.Text(run, 12, C.dim)
run.extra:SetPoint("TOPLEFT", run.time, "BOTTOMLEFT", 0, -6)
P.run = run

P.solo = UI.Button(P, 150, 34, "Enter solo", "gold", 13)
P.solo:SetPoint("TOPLEFT", run, "BOTTOMLEFT", 0, -12)
P.group = UI.Button(P, 150, 34, "Queue as group", "dark", 13)
P.group:SetPoint("LEFT", P.solo, "RIGHT", 10, 0)
P.board = UI.Button(P, 150, 34, "Leaderboard", "ghost", 13)
P.board:SetPoint("LEFT", P.group, "RIGHT", 10, 0)

local function roles()
    return (ns.Dungeons and ns.Dungeons.roles) or 4
end
P.solo:SetScript("OnClick", function()
    Comm.Send("QJOIN", "R", 0, 0, roles(), 1)
end)
P.group:SetScript("OnClick", function()
    Comm.Send("QJOIN", "R", 0, 0, roles(), 5)
end)
P.board:SetScript("OnClick", function()
    UI.Open("leaderboards-rift")
end)

-- Best and summary
local best = UI.Box(P, RIGHT, 110, C.card, C.border)
best:SetPoint("TOPRIGHT", head, "BOTTOMRIGHT", 0, -12)
best.label = UI.Text(best, 11, C.dim)
best.label:SetPoint("TOPLEFT", best, "TOPLEFT", 12, -12)
best.label:SetText("YOUR BEST")
best.value = UI.Text(best, 24, C.goldPale, "title")
best.value:SetPoint("TOPLEFT", best.label, "BOTTOMLEFT", 0, -8)
best.extra = UI.Text(best, 12, C.dim)
best.extra:SetPoint("TOPLEFT", best.value, "BOTTOMLEFT", 0, -6)
UI.OneLine(best.extra, RIGHT - 24)
P.best = best

local sum = UI.Box(P, RIGHT, A.PH - 96 - 12 - 110 - 12, C.card, C.border)
sum:SetPoint("TOPRIGHT", best, "BOTTOMRIGHT", 0, -12)
sum.label = UI.Text(sum, 11, C.dim)
sum.label:SetPoint("TOPLEFT", sum, "TOPLEFT", 12, -12)
sum.label:SetText("LAST RUN")
sum.lines = {}
for i = 1, 9 do
    local l = UI.Text(sum, 12, i == 1 and C.text or C.mid)
    l:SetPoint("TOPLEFT", sum, "TOPLEFT", 12, -32 - (i - 1) * 19)
    UI.OneLine(l, RIGHT - 24)
    sum.lines[i] = l
end
P.summary = sum

local function elapsed(rf)
    if not rf or not rf.elapsedMs then
        return nil
    end
    local e = rf.elapsedMs / 1000
    if rf.state == 1 then
        e = e + (GetTime() - (rf.elapsedAt or GetTime()))
    end
    return e
end

function P:Tick()
    local rf = S.rift
    if rf and rf.state == 1 then
        local e = elapsed(rf)
        run.time:SetText(e and ("Time " .. U.Clock(e)) or "")
    end
end

function P:Refresh()
    local rf = S.rift
    if rf and rf.state == 1 then
        head.title:SetText("Run in progress")
        run.floor:SetText(rf.floor and ("Floor " .. rf.floor) or "Floor -")
        UI.SetText(run.boss, rf.bossName or "")
        local parts = {}
        if rf.deaths then parts[#parts + 1] = rf.deaths .. (rf.deaths == 1 and " death" or " deaths") end
        if rf.groupSize then parts[#parts + 1] = rf.groupSize == 1 and "solo" or ("group of " .. rf.groupSize) end
        if rf.score then parts[#parts + 1] = "score " .. U.Commas(rf.score) end
        run.extra:SetText(table.concat(parts, "  -  "))
        P:Tick()
    else
        head.title:SetText(Comm.ready and "Enter the Rift" or "Waiting for the server")
        run.floor:SetText("Not in a run")
        run.boss:SetText("")
        run.time:SetText("")
        run.extra:SetText("")
    end
    local q = S.queue
    local busy = (q and q.state ~= 0) or (rf and rf.state == 1)
    P.solo:SetActive(not busy)
    P.group:SetActive(not busy)

    local bestFloor = (rf and rf.bestFloor) or (S.week and S.week.riftBestFloor)
    best.value:SetText(bestFloor and bestFloor > 0 and ("Floor " .. bestFloor) or "-")
    local ex = {}
    if rf and rf.rank then ex[#ex + 1] = "Rank " .. rf.rank end
    best.extra:SetText(table.concat(ex, "  -  "))

    local sm = rf and rf.summary
    for i, l in ipairs(sum.lines) do
        l:SetText("")
    end
    if sm then
        local lines = {}
        lines[#lines + 1] = (sm.floor and ("Reached floor " .. sm.floor) or "Run over") .. (sm.newBest and "  -  new best!" or "")
        if sm.timeMs then lines[#lines + 1] = "Time " .. U.Clock(sm.timeMs / 1000) end
        if sm.score then lines[#lines + 1] = "Score " .. U.Commas(sm.score) end
        if sm.rank then lines[#lines + 1] = "Rank " .. sm.rank end
        for _, r in ipairs(sm.rewards) do lines[#lines + 1] = "+ " .. r end
        for i, l in ipairs(sum.lines) do
            if lines[i] then UI.SetText(l, lines[i]) end
        end
    else
        sum.lines[1]:SetText("No run yet")
    end
end

function P:OnOpen()
    Comm.Refresh("RIFT")
end

ns.On("RIFT_END", function()
    if P:IsVisible() then
        P:Refresh()
    end
end)
