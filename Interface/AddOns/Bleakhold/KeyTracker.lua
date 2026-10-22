-- Bleakhold: Mythic+ key tracker (timer, deaths, bosses, enemy forces, affixes) and the end-of-run
-- summary. Every number is server state (MPS/MP/MPE); the timer only counts on locally between MP
-- updates. Its own movable frame: DragonUI keeps WatchFrame hidden and replaces it, so the tracker
-- sits beside DragonUI's tracker when that exists and never changes DragonUI's frames.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S

local floor, max, min = math.floor, math.max, math.min

local T = {}
ns.KeyTracker = T

T.W = 250
T.MAX_BOSSES = 8
T.SUMMARY_TIME = 60

local f = CreateFrame("Frame", "BleakholdKeyTracker", UIParent)
f:SetSize(T.W, 200)
f:SetFrameStrata("MEDIUM")
UI.Backdrop(f, "101216", C.chipBorder, 0.92)
f:Hide()
T.frame = f

f.title = UI.Text(f, 15, C.goldPale, "title")
f.title:SetPoint("TOPLEFT", f, "TOPLEFT", 12, -10)
UI.OneLine(f.title, T.W - 82)
f.deaths = CreateFrame("Frame", nil, f)
f.deaths:SetSize(64, 16)
f.deaths:SetPoint("TOPRIGHT", f, "TOPRIGHT", -10, -12)
f.deaths:EnableMouse(true)
f.deaths.text = UI.Text(f.deaths, 12, C.dim, "body", "RIGHT")
f.deaths.text:SetPoint("RIGHT")
f.deaths:SetScript("OnEnter", function(self)
    local m = S.mplus
    if m then
        UI.ShowTooltip(self, { "Deaths", (m.deathPenaltySec or 0) > 0 and ("Time lost to deaths: " .. U.Clock(m.deathPenaltySec)) or "No time lost to deaths" })
    end
end)
f.deaths:SetScript("OnLeave", function()
    if GameTooltip then GameTooltip:Hide() end
end)

f.timer = UI.Text(f, 26, C.text, "title")
f.timer:SetPoint("TOPLEFT", f.title, "BOTTOMLEFT", 0, -6)
f.limit = UI.Text(f, 14, C.dim, "title")
f.limit:SetPoint("BOTTOMLEFT", f.timer, "BOTTOMRIGHT", 4, 3)

-- time bar with chest thresholds
f.timebar = UI.Bar(f, T.W - 24, 4, C.goldDark, C.bg)
f.timebar:SetPoint("TOPLEFT", f.timer, "BOTTOMLEFT", 0, -6)
f.ticks = {}
for i = 1, 3 do
    local t = UI.Solid(f.timebar, C.goldPale, "OVERLAY")
    t:SetSize(2, 8)
    t:Hide()
    f.ticks[i] = t
end

f.bosses = {}
for i = 1, T.MAX_BOSSES do
    local row = CreateFrame("Frame", nil, f)
    row:SetSize(T.W - 24, 18)
    row:EnableMouse(true)
    row.name = UI.Text(row, 13, C.text)
    row.name:SetPoint("LEFT")
    row.name:SetPoint("RIGHT", row, "RIGHT", -50, 0)
    row.state = UI.Text(row, 13, C.mute, "body", "RIGHT")
    row.state:SetPoint("RIGHT")
    row:SetScript("OnEnter", function(self)
        if self.killSec then
            UI.ShowTooltip(self, { U.Safe(self.bossName or "Boss"), "Defeated at " .. U.Clock(self.killSec) })
        end
    end)
    row:SetScript("OnLeave", function()
        if GameTooltip then GameTooltip:Hide() end
    end)
    row:Hide()
    f.bosses[i] = row
end

f.forces = UI.Bar(f, T.W - 24, 8, C.gold, C.bg)
f.forcesText = UI.Text(f, 12, C.dim)
f.affixes = UI.Text(f, 11, C.mute)
f.affixes:SetWidth(T.W - 24)

-- end-of-run summary (replaces the rows)
f.result = UI.Text(f, 20, C.teal, "title")
f.resultLines = {}
for i = 1, 8 do
    local l = UI.Text(f, 12, i == 1 and C.text or C.mid)
    l:SetWidth(T.W - 24)
    f.resultLines[i] = l
end
f.closeBtn = UI.Button(f, 80, 22, "Close", "dark", 11)
f.closeBtn:SetScript("OnClick", function()
    T.dismissed = S.mplus and S.mplus.runId
    f:Hide()
end)

------------------------------------------------------------------------------------------------------
-- Position: saved if the player moved it, else beside DragonUI's tracker, else under the minimap.
------------------------------------------------------------------------------------------------------
UI.MakeMovable(f)
f:SetClampedToScreen(true)

function T.Anchor()
    local pos = ns.cdb.windows.BleakholdKeyTracker
    f:ClearAllPoints()
    if type(pos) == "table" and type(pos.point) == "string" and type(pos.x) == "number" and type(pos.y) == "number" then
        f:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, pos.x, pos.y)
    elseif DragonUI_QuestTrackerFrame then
        f:SetPoint("TOPRIGHT", DragonUI_QuestTrackerFrame, "TOPLEFT", -12, 0)
    else
        f:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -40, -250)
    end
end

------------------------------------------------------------------------------------------------------
-- Drawing
------------------------------------------------------------------------------------------------------
local function bossNames(m)
    local def = ns.Def("D", m.dungeonId)
    return def and def.bosses or {}
end

function T.UpdateTimer()
    local m = S.mplus
    if not m or m.result then
        return
    end
    if m.state == 0 then
        local left = (m.countdownMs or 0) / 1000 - (GetTime() - (m.startedAt or GetTime()))
        f.timer:SetText("Starts in " .. max(0, math.ceil(left)))
        UI.SetColor(f.timer, C.goldLight)
        f.limit:SetText("")
        f.timebar:SetProgress(0)
        return
    end
    local e = ns.MplusElapsed(m)
    local limit = m.timeLimitSec or 0
    f.timer:SetText(U.Clock(e))
    UI.SetColor(f.timer, (limit > 0 and e > limit) and C.red or C.text)
    f.limit:SetText(limit > 0 and ("/ " .. U.Clock(limit)) or "")
    f.timebar:SetProgress(limit > 0 and e / limit or 0)
end

local function layoutRun(m)
    local y = -86
    local names = bossNames(m)
    local count = max(#names, #(m.bossKillSec or {}))
    for i = 1, 31 do
        if bit.band(m.bossBits or 0, bit.lshift(1, i - 1)) ~= 0 then
            count = max(count, i)
        end
    end
    count = min(count, T.MAX_BOSSES)
    for i, row in ipairs(f.bosses) do
        if i <= count then
            local done = bit.band(m.bossBits or 0, bit.lshift(1, i - 1)) ~= 0
            row.bossName = names[i] or ("Boss " .. i)
            row.killSec = done and m.bossKillSec and m.bossKillSec[i] or nil
            UI.SetText(row.name, row.bossName)
            UI.SetColor(row.name, done and C.teal or C.text)
            row.state:SetText(done and "done" or "-")
            UI.SetColor(row.state, done and C.teal or C.mute)
            row:ClearAllPoints()
            row:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y)
            row:Show()
            y = y - 19
        else
            row:Hide()
        end
    end
    if (m.forcesMax or 0) > 0 then
        local p = (m.forcesCur or 0) / m.forcesMax
        f.forces:ClearAllPoints()
        f.forces:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y - 6)
        f.forces:SetProgress(p)
        f.forces:Show()
        local pct = p * 100
        local txt = pct >= 100 and "100" or string.format("%.1f", floor(pct * 10) / 10)
        f.forcesText:SetText("Enemy forces " .. txt .. "%")
        f.forcesText:ClearAllPoints()
        f.forcesText:SetPoint("TOPLEFT", f.forces, "BOTTOMLEFT", 0, -3)
        f.forcesText:Show()
        y = y - 6 - 8 - 18
    else
        f.forces:Hide()
        f.forcesText:Hide()
    end
    local affixes = ns.AffixNames(m.affixes)
    if #affixes > 0 then
        UI.SetText(f.affixes, table.concat(affixes, ", "))
        f.affixes:ClearAllPoints()
        f.affixes:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y - 4)
        f.affixes:Show()
        y = y - 20
    else
        f.affixes:Hide()
    end
    -- chest thresholds as ticks on the time bar
    local limit = m.timeLimitSec or 0
    for i, t in ipairs(f.ticks) do
        local sec = m.chestSec and m.chestSec[i]
        if sec and limit > 0 and sec < limit then
            t:ClearAllPoints()
            t:SetPoint("CENTER", f.timebar, "LEFT", (T.W - 24) * sec / limit, 0)
            t:Show()
        else
            t:Hide()
        end
    end
    f.result:Hide()
    for _, l in ipairs(f.resultLines) do l:Hide() end
    f.closeBtn:Hide()
    f.timebar:Show()
    f:SetHeight(-y + 12)
end

local RESULT = { [1] = "Timed!", [0] = "Over time", [2] = "Abandoned" }

local function layoutResult(m)
    local r = m.result
    for _, row in ipairs(f.bosses) do row:Hide() end
    f.forces:Hide()
    f.forcesText:Hide()
    f.affixes:Hide()
    f.timebar:Hide()
    for _, t in ipairs(f.ticks) do t:Hide() end
    f.timer:SetText(U.Clock((r.timeMs or 0) / 1000))
    UI.SetColor(f.timer, C.text)
    f.limit:SetText((m.timeLimitSec or 0) > 0 and ("/ " .. U.Clock(m.timeLimitSec)) or "")
    f.result:SetText(RESULT[r.result] or "Run over")
    UI.SetColor(f.result, r.result == 1 and C.teal or C.red)
    f.result:ClearAllPoints()
    f.result:SetPoint("TOPLEFT", f, "TOPLEFT", 12, -82)
    f.result:Show()
    local lines = {}
    if r.keyDelta and r.keyDelta ~= 0 then
        local sign = r.keyDelta > 0 and ("+" .. r.keyDelta) or tostring(r.keyDelta)
        local newKey = (r.newDungeonId and r.newLevel) and (": " .. ns.DungeonName(r.newDungeonId) .. " +" .. r.newLevel) or ""
        lines[#lines + 1] = "Keystone " .. sign .. newKey
    elseif r.newDungeonId and r.newLevel then
        lines[#lines + 1] = "Keystone: " .. ns.DungeonName(r.newDungeonId) .. " +" .. r.newLevel
    end
    if r.score then lines[#lines + 1] = "Score " .. U.Commas(r.score) end
    for _, rw in ipairs(r.rewards) do lines[#lines + 1] = "+ " .. rw end
    local y = -110
    for i, l in ipairs(f.resultLines) do
        if lines[i] then
            UI.SetText(l, lines[i])
            l:ClearAllPoints()
            l:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y)
            l:Show()
            y = y - 18
        else
            l:Hide()
        end
    end
    f.closeBtn:ClearAllPoints()
    f.closeBtn:SetPoint("TOPRIGHT", f, "TOPRIGHT", -12, y - 6)
    f.closeBtn:Show()
    f:SetHeight(-y + 40)
end

function T.Refresh()
    local m = S.mplus
    if not m or (m.state == 4 and not m.result) or T.dismissed == m.runId then
        f:Hide()
        return
    end
    if m.result and m.resultShownAt and GetTime() - m.resultShownAt > T.SUMMARY_TIME then
        f:Hide()
        return
    end
    UI.SetText(f.title, ns.DungeonName(m.dungeonId) .. ((m.level or 0) > 0 and (" +" .. m.level) or ""))
    local d = m.deaths or 0
    f.deaths.text:SetText(d .. (d == 1 and " death" or " deaths"))
    if m.result then
        layoutResult(m)
    else
        layoutRun(m)
        T.UpdateTimer()
    end
    if not f:IsShown() then
        T.Anchor()
        f:Show()
    end
end

local acc = 0
f:SetScript("OnUpdate", function(self, elapsed)
    acc = acc + (elapsed or 0)
    if acc >= 0.1 then
        acc = 0
        T.UpdateTimer()
        local m = S.mplus
        if m and m.result and m.resultShownAt and GetTime() - m.resultShownAt > T.SUMMARY_TIME then
            self:Hide()
        end
    end
end)

ns.On("STATE", function(topic)
    if topic == "MPLUS" then
        T.Refresh()
    end
end)

ns.On("MPLUS_START", function()
    T.dismissed = nil
end)

ns.On("MPLUS_END", function()
    local m = S.mplus
    if m then
        m.resultShownAt = GetTime()
    end
    T.dismissed = nil
    T.Refresh()
end)
