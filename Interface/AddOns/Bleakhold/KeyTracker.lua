-- Bleakhold: Mythic+ key tracker (timer, deaths, bosses, enemy forces, affixes) and the end-of-run
-- summary. Every number is server state (MPS/MP/MPE); the timer only counts on locally between MP
-- updates. Its own movable frame: AddicatUI (and DragonUI) keeps WatchFrame hidden and replaces it, so the
-- tracker sits beside that tracker when it exists and never changes its frames. AddicatUI's editor mode moves
-- it through the mover at the end of the position section; the spot stays in BleakholdCharDB either way.
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

-- The look of the stock quest tracker (WatchFrame): no panel, the lines straight on the world in GameFontHighlight with
-- its shadow, 16 px apart; the title gold, each boss an objective line ("- name", 0.8 grey; grey once killed, with a
-- green "done"); the timer white in GameFontHighlightHuge (red over time) over the breath bar's timer bar (UI.TimerBar,
-- the cast bar's gold; its failed red over time) with the chest thresholds marked on it; enemy forces on a second timer
-- bar, green, its count in the bar.
T.LINE_H = 16                                            -- WATCHFRAME_LINEHEIGHT
T.BAR_X = 12 + 9                                         -- the bars' left edge: the border's studs line up with text
T.BAR_W = T.W - 2 * T.BAR_X
T.OBJECTIVE = "CCCCCC"                                   -- WatchFrame's objective lines (0.8, 0.8, 0.8)

local f = CreateFrame("Frame", "BleakholdKeyTracker", UIParent)
f:SetSize(T.W, 200)
f:SetFrameStrata("MEDIUM")
f:Hide()
T.frame = f

f.title = UI.Text(f, 14, C.gold)
f.title:SetPoint("TOPLEFT", f, "TOPLEFT", 12, -6)
UI.OneLine(f.title, T.W - 82)
f.deaths = CreateFrame("Frame", nil, f)
f.deaths:SetSize(64, 16)
f.deaths:SetPoint("TOPRIGHT", f, "TOPRIGHT", -10, -6)
f.deaths:EnableMouse(true)
f.deaths.text = UI.Text(f.deaths, 11, C.dim, "body", "RIGHT")
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

f.timer = UI.Text(f, 20, C.text)
f.timer:SetPoint("TOPLEFT", f, "TOPLEFT", 12, -25)
f.limit = UI.Text(f, 12, C.dim)
f.limit:SetPoint("BOTTOMLEFT", f.timer, "BOTTOMRIGHT", 4, 2)

-- time bar with chest thresholds
f.timebar = UI.TimerBar(f, T.BAR_W, UI.BAR_GOLD)
f.timebar:SetPoint("TOPLEFT", f, "TOPLEFT", T.BAR_X, -60)
f.ticks = {}
for i = 1, 3 do
    local t = UI.Solid(f.timebar.border, "FFF2B3", "ARTWORK", 0.9)
    t:SetSize(2, UI.TIMER_H)
    t:Hide()
    f.ticks[i] = t
end

f.bosses = {}
for i = 1, T.MAX_BOSSES do
    local row = CreateFrame("Frame", nil, f)
    row:SetSize(T.W - 24, T.LINE_H)
    row:EnableMouse(true)
    row.dash = UI.Text(row, 12, T.OBJECTIVE)
    row.dash:SetPoint("LEFT")
    row.dash:SetText("- ")
    row.name = UI.Text(row, 12, T.OBJECTIVE)
    row.name:SetPoint("LEFT", row, "LEFT", 10, 0)
    row.name:SetPoint("RIGHT", row, "RIGHT", -44, 0)
    row.name:SetNonSpaceWrap(false)
    row.name:SetHeight(T.LINE_H)
    row.state = UI.Text(row, 12, C.mute, "body", "RIGHT")
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

f.forces = UI.TimerBar(f, T.BAR_W, C.bar)
f.forcesText = f.forces.text
f.forcesText:SetFont(UI.FONT_BODY, 10, "")
f.affixes = UI.Text(f, 11, C.dim)
f.affixes:SetWidth(T.W - 24)

-- end-of-run summary (replaces the rows)
f.result = UI.Text(f, 16, C.teal)
f.resultLines = {}
for i = 1, 8 do
    local l = UI.Text(f, 12, i == 1 and C.text or T.OBJECTIVE)
    l:SetWidth(T.W - 24)
    f.resultLines[i] = l
end
f.closeBtn = UI.Button(f, 80, 22, "Close", "ghost", 11)
f.closeBtn:SetScript("OnClick", function()
    T.dismissed = S.mplus and S.mplus.runId
    T.Refresh()
end)

------------------------------------------------------------------------------------------------------
-- Position: saved if the player moved it, else beside AddicatUI's (or DragonUI's) tracker, on the side
-- facing the middle of the screen, else under the minimap.
------------------------------------------------------------------------------------------------------
UI.MakeMovable(f)
f:SetClampedToScreen(true)

T.GAP = 12

function T.SavedPosition()
    local pos = ns.cdb.windows.BleakholdKeyTracker
    if type(pos) == "table" and type(pos.point) == "string" and type(pos.x) == "number" and type(pos.y) == "number" then
        return pos
    end
end

function T.Anchor()
    local pos = T.SavedPosition()
    local quests = AddicatUI_QuestTrackerFrame or DragonUI_QuestTrackerFrame
    f:ClearAllPoints()
    if pos then
        f:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, pos.x, pos.y)
    elseif quests then
        local qx = quests:GetCenter()
        local ux = UIParent:GetCenter()
        if qx and ux and qx < ux then
            f:SetPoint("TOPLEFT", quests, "TOPRIGHT", T.GAP, 0)
        else
            f:SetPoint("TOPRIGHT", quests, "TOPLEFT", -T.GAP, 0)
        end
    else
        f:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -40, -250)
    end
end

-- Puts the tracker's top edge where `region` has its top edge (same width) and, when save, keeps the spot.
function T.MoveTo(region, save)
    local point, relPoint, x, y = UI.TopAnchorOf(region)
    if not point then
        return
    end
    f:ClearAllPoints()
    f:SetPoint(point, UIParent, relPoint, x, y)
    if save then
        ns.cdb.windows.BleakholdKeyTracker = { point = point, relPoint = relPoint, x = x, y = y }
    end
end

function T.ResetPosition()
    ns.cdb.windows.BleakholdKeyTracker = nil
    T.Anchor()
end

------------------------------------------------------------------------------------------------------
-- Drawing
------------------------------------------------------------------------------------------------------
local function bossNames(m)
    if m.bossNames then
        return m.bossNames
    end
    local def = ns.Def("D", m.dungeonId)
    return def and def.bosses or {}
end

function T.UpdateTimer()
    local m = T.current
    if not m or m.result then
        return
    end
    if m.state == 0 then
        local left = (m.countdownMs or 0) / 1000 - (GetTime() - (m.startedAt or GetTime()))
        f.timer:SetText("Starts in " .. max(0, math.ceil(left)))
        UI.SetColor(f.timer, C.gold)
        f.limit:SetText("")
        f.timebar:SetProgress(0)
        return
    end
    local e = ns.MplusElapsed(m)
    local limit = m.timeLimitSec or 0
    local over = limit > 0 and e > limit
    f.timer:SetText(U.Clock(e))
    UI.SetColor(f.timer, over and C.red or C.text)
    f.limit:SetText(limit > 0 and ("/ " .. U.Clock(limit)) or "")
    f.timebar:SetProgress(limit > 0 and e / limit or 0)
    -- the cast bar's failed red once over time
    f.timebar:SetStatusBarColor(UI.Rgb(over and C.red or UI.BAR_GOLD))
end

-- The rows from y (under the time bar): the bosses, enemy forces, the affixes; the frame ends under the last.
local function layoutRun(m)
    local y = -84
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
            UI.SetColor(row.name, done and C.mute or T.OBJECTIVE)
            UI.SetColor(row.dash, done and C.mute or T.OBJECTIVE)
            row.state:SetText(done and "done" or "-")
            UI.SetColor(row.state, done and C.teal or C.mute)
            row:ClearAllPoints()
            row:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y)
            row:Show()
            y = y - T.LINE_H
        else
            row:Hide()
        end
    end
    if (m.forcesMax or 0) > 0 then
        local p = (m.forcesCur or 0) / m.forcesMax
        f.forces:ClearAllPoints()
        f.forces:SetPoint("TOPLEFT", f, "TOPLEFT", T.BAR_X, y - 14)
        f.forces:SetProgress(p)
        f.forces:Show()
        local pct = p * 100
        local txt = pct >= 100 and "100" or string.format("%.1f", floor(pct * 10) / 10)
        f.forcesText:SetText("Enemy forces " .. txt .. "%")
        f.forcesText:Show()
        y = y - 14 - UI.TIMER_H - 12
    else
        f.forces:Hide()
    end
    local affixes = m.affixNames or ns.AffixNames(m.affixes)
    if #affixes > 0 then
        UI.SetText(f.affixes, table.concat(affixes, ", "))
        f.affixes:ClearAllPoints()
        f.affixes:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y - 2)
        f.affixes:Show()
        y = y - 18
    else
        f.affixes:Hide()
    end
    -- chest thresholds as ticks on the time bar
    local limit = m.timeLimitSec or 0
    for i, t in ipairs(f.ticks) do
        local sec = m.chestSec and m.chestSec[i]
        if sec and limit > 0 and sec < limit then
            t:ClearAllPoints()
            t:SetPoint("CENTER", f.timebar, "LEFT", floor(T.BAR_W * sec / limit + 0.5), 0)
            t:Show()
        else
            t:Hide()
        end
    end
    f.result:Hide()
    for _, l in ipairs(f.resultLines) do l:Hide() end
    f.closeBtn:Hide()
    f.timebar:Show()
    f:SetHeight(-y + 8)
end

local RESULT = { [1] = "Timed!", [0] = "Over time", [2] = "Abandoned" }

local function layoutResult(m)
    local r = m.result
    for _, row in ipairs(f.bosses) do row:Hide() end
    f.forces:Hide()
    f.affixes:Hide()
    f.timebar:Hide()
    for _, t in ipairs(f.ticks) do t:Hide() end
    f.timer:SetText(U.Clock((r.timeMs or 0) / 1000))
    UI.SetColor(f.timer, C.text)
    f.limit:SetText((m.timeLimitSec or 0) > 0 and ("/ " .. U.Clock(m.timeLimitSec)) or "")
    f.result:SetText(RESULT[r.result] or "Run over")
    UI.SetColor(f.result, r.result == 1 and C.teal or C.red)
    f.result:ClearAllPoints()
    f.result:SetPoint("TOPLEFT", f, "TOPLEFT", 12, -52)
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
    local y = -74
    for i, l in ipairs(f.resultLines) do
        if lines[i] then
            UI.SetText(l, lines[i])
            l:ClearAllPoints()
            l:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y)
            l:Show()
            y = y - T.LINE_H
        else
            l:Hide()
        end
    end
    f.closeBtn:ClearAllPoints()
    f.closeBtn:SetPoint("TOPRIGHT", f, "TOPRIGHT", -12, y - 6)
    f.closeBtn:Show()
    f:SetHeight(-y + 34)
end

-- A sample run for positioning the tracker (AddicatUI's editor mode) while no run is on.
T.SAMPLE = {
    runId = 0, title = "Mythic+ Key Tracker", level = 0, state = 2, elapsedMs = 754000, timeLimitSec = 1800,
    deaths = 1, deathPenaltySec = 5, forcesCur = 62, forcesMax = 100, bossBits = 3, bossKillSec = { 301, 652 },
    chestSec = { 1260, 1440 }, bossNames = { "First boss", "Second boss", "Third boss", "Last boss" },
    affixNames = { "This week's affixes" },
}

-- The run to show: the server's, unless it is over and its summary dismissed or timed out.
local function liveRun()
    local m = S.mplus
    if not m or (m.state == 4 and not m.result) or T.dismissed == m.runId then
        return nil
    end
    if m.result and m.resultShownAt and GetTime() - m.resultShownAt > T.SUMMARY_TIME then
        return nil
    end
    return m
end

function T.Refresh()
    local m = liveRun() or (T.preview and T.SAMPLE) or nil
    T.current = m
    if not m then
        f:Hide()
        return
    end
    UI.SetText(f.title, (m.title or ns.DungeonName(m.dungeonId)) .. ((m.level or 0) > 0 and (" +" .. m.level) or ""))
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
        local m = T.current
        if m and m.result and m.resultShownAt and GetTime() - m.resultShownAt > T.SUMMARY_TIME then
            T.Refresh()
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

------------------------------------------------------------------------------------------------------
-- Editor mode (ns.Movers): the sample run shows while nothing real is on, so there is a frame to place.
------------------------------------------------------------------------------------------------------
UI.AddMover({
    name = "bleakhold_keytracker",
    title = "Mythic+ Key Tracker",
    frame = f,
    begin = function()
        T.preview = true
        T.Refresh()
    end,
    finish = function()
        T.preview = nil
        T.Refresh()
        if f:IsShown() then
            T.Anchor()
        end
    end,
    move = function(region, done)
        T.MoveTo(region, done)
    end,
    reset = function()
        T.ResetPosition()
    end,
    isDefault = function()
        return T.SavedPosition() == nil
    end,
    visible = function()
        return true
    end,
})
