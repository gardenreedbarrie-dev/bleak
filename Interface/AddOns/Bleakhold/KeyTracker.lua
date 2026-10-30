-- Bleakhold: Mythic+ key tracker (timer, deaths, bosses, enemy forces, affixes) and the end-of-run summary, and the
-- Eclipse Rift floor tracker. The numbers are server state; the timer only counts on locally between updates. Its own
-- movable frame: AddicatUI (and DragonUI) keeps WatchFrame hidden and replaces it, so the tracker sits beside that
-- tracker when it exists and never changes its frames. AddicatUI's editor mode moves it through the mover at the end
-- of the position section; the spot stays in BleakholdCharDB either way.
--
-- Data:
--   a key or a Mythic 0   our MPS / MP / MPE (S.mplus). A Mythic 0 is MPS level 0 with no time limit (a key always
--                         has level >= 1): untimed, no time bar, and only its final boss ends it (CheckComplete).
--   what MP does not carry  the server's legacy BHMP lines (Legacy.lua), read only for the live run: L.Run() = { mode,
--                         dungeon, level, champsNeeded, champsKilled, bosses[i] = { role } } from S, T, B and D (mode
--                         3 a key, 2 a Mythic 0; boss role 1 shown, 2 an additional boss, 3 the final one, 0 unknown),
--                         L.BattleRes(), and the player's own L.AffixStacks() (Y) and the group's L.Boon() (V). Without
--                         them those lines stay away (the server's toasts and notices are the fallback).
--   a Rift floor          our RIFT (S.rift) and the Rift page's RunFloor / Elapsed (Rift.lua), while no key run shows.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S

local floor, ceil, max, min = math.floor, math.ceil, math.max, math.min

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
T.TEXT_W = T.W - 24
T.OBJECTIVE = "CCCCCC"                                   -- WatchFrame's objective lines (0.8, 0.8, 0.8)
T.ROWS_TIMED = -84                                       -- the first row: under the time bar
T.ROWS_UNTIMED = -52                                     -- under the clock (a Rift floor: no time bar)
T.ROWS_M0 = -68                                          -- a Mythic 0: under the clock and its "untimed" line

-- The legacy BHMP run's modes and boss roles (mod-bleakhold bh_mplus.h Mode, BossRole).
T.MODE_M0, T.MODE_KEY = 2, 3
T.ROLE_EXTRA, T.ROLE_FINAL = 2, 3
T.CHAMPIONS = 13                                         -- the Mythic Champions affix (its DEF A text is the tooltip)
T.PACK_TACTICS = 18                                      -- BHMP Y's Pack Tactics: allies away, not stacks

T.M0_LIMIT = "Mythic 0 - untimed"
T.M0_NOTE = "Defeat the final boss to finish"
T.OPTIONAL_TIP = "Optional: only the final boss ends a Mythic 0."
T.BONUS_TIP = "A bonus boss: the key ends without it."
T.BRES_TIP = { "Battle res", "Battle resurrections the group has left. More come with time, up to 5." }
-- RIFT's deaths are the whole run's (the bridge sends Run::riftRunDeaths; Run::deaths starts again every floor)
T.RIFT_DEATHS_TIP = { "Deaths", "Deaths in this run, on every floor so far" }
T.RIFT_BOSS = "The floor's boss"

-- The run's affixes (MPS: the server's ids) by name as the Keys page and the keystone tooltip name them
-- (ns.Keys.AffixNames: the server's names; Data.lua's built-in DEF A numbers some of them differently, 4 Volcanic
-- there for the server's Raging).
function T.AffixNames(ids)
    local K = ns.Keys
    if K and K.AffixNames then
        return K.AffixNames(ids)
    end
    return ns.AffixNames(ids)
end

-- The affix stacks the player has now (BHMP Y: 6 Bursting, 8 Necrotic, 9 Grievous, 18 Pack Tactics) and the group's
-- boon counting down (V), one orange line each under the affix names, in the server's own words (bh_mplus.cpp
-- AffixNotices: "Necrotic x20: -40% healing taken", "Pack Tactics: 2 allies over 10 yd away (...)"; the boon names of
-- its claim line). No quake line: the server's quake visual shows it.
T.MAX_STACK_LINES = 5

local f = CreateFrame("Frame", "BleakholdKeyTracker", UIParent)
f:SetSize(T.W, 200)
f:SetFrameStrata("MEDIUM")
f:Hide()
T.frame = f

local function hideTip()
    if GameTooltip then
        GameTooltip:Hide()
    end
end

f.title = UI.Text(f, 14, C.gold)
f.title:SetPoint("TOPLEFT", f, "TOPLEFT", 12, -6)
UI.OneLine(f.title, T.W - 82)
-- a key's level, right after the name: only the name is cut to the room left ("Scarlet Monastery: Cathedral +12"
-- is wider than the title), so the level always shows
f.titleLevel = UI.Text(f, 14, C.gold)
f.titleLevel:SetPoint("LEFT", f.title, "RIGHT", 4, 0)
f.deaths = CreateFrame("Frame", nil, f)
f.deaths:SetSize(64, 16)
f.deaths:SetPoint("TOPRIGHT", f, "TOPRIGHT", -10, -6)
f.deaths:EnableMouse(true)
f.deaths.text = UI.Text(f.deaths, 11, C.dim, "body", "RIGHT")
f.deaths.text:SetPoint("RIGHT")
f.deaths:SetScript("OnEnter", function(self)
    local m = T.current
    if m and m.rift then
        UI.ShowTooltip(self, T.RIFT_DEATHS_TIP)
    elseif m then
        local lost = (m.deathPenaltySec or 0) > 0
        UI.ShowTooltip(self, { "Deaths", lost and ("Time lost to deaths: " .. U.Clock(m.deathPenaltySec))
            or "No time lost to deaths" })
    end
end)
f.deaths:SetScript("OnLeave", hideTip)

-- the group's battle resurrections, under the deaths (a key with the legacy T line only)
f.bres = CreateFrame("Frame", nil, f)
f.bres:SetSize(80, 14)
f.bres:SetPoint("TOPRIGHT", f, "TOPRIGHT", -10, -22)
f.bres:EnableMouse(true)
f.bres.text = UI.Text(f.bres, 11, C.dim, "body", "RIGHT")
f.bres.text:SetPoint("RIGHT")
f.bres:SetScript("OnEnter", function(self)
    UI.ShowTooltip(self, T.BRES_TIP)
end)
f.bres:SetScript("OnLeave", hideTip)
f.bres:Hide()

f.timer = UI.Text(f, 20, C.text)
f.timer:SetPoint("TOPLEFT", f, "TOPLEFT", 12, -25)
f.limit = UI.Text(f, 12, C.dim)

-- The limit beside the clock ("/ 30:00"); a Mythic 0's "untimed" line under it (beside it, it would run into the
-- battle res under the deaths).
function T.PlaceLimit(below)
    if f.limitBelow == below then
        return
    end
    f.limitBelow = below
    f.limit:ClearAllPoints()
    if below then
        f.limit:SetPoint("TOPLEFT", f.timer, "BOTTOMLEFT", 0, -1)
    else
        f.limit:SetPoint("BOTTOMLEFT", f.timer, "BOTTOMRIGHT", 4, 2)
    end
end
T.PlaceLimit(false)

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

-- An objective line: "- name" and its state on the right ("done", "-", "optional", ...); row.tip = its tooltip lines.
local function newRow()
    local row = CreateFrame("Frame", nil, f)
    row:SetSize(T.TEXT_W, T.LINE_H)
    row:EnableMouse(true)
    row.dash = UI.Text(row, 12, T.OBJECTIVE)
    row.dash:SetPoint("LEFT")
    row.dash:SetText("- ")
    row.state = UI.Text(row, 12, C.mute, "body", "RIGHT")
    row.state:SetPoint("RIGHT")
    row.name = UI.Text(row, 12, T.OBJECTIVE)
    row.name:SetPoint("LEFT", row, "LEFT", 10, 0)
    row.name:SetPoint("RIGHT", row.state, "LEFT", -4, 0)
    row.name:SetNonSpaceWrap(false)
    row.name:SetHeight(T.LINE_H)
    row:SetScript("OnEnter", function(self)
        if self.tip then
            UI.ShowTooltip(self, self.tip)
        end
    end)
    row:SetScript("OnLeave", hideTip)
    row:Hide()
    return row
end

local function setObjective(row, text, state, color, stateColor)
    UI.SetText(row.name, text)
    UI.SetColor(row.name, color)
    UI.SetColor(row.dash, color)
    row.state:SetText(state or "")
    UI.SetColor(row.state, stateColor or C.mute)
end

local function placeRow(row, y)
    row:ClearAllPoints()
    row:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y)
    row:Show()
    return y - T.LINE_H
end

f.bosses = {}
for i = 1, T.MAX_BOSSES do
    f.bosses[i] = newRow()
end
f.note = newRow()                                        -- a Mythic 0 without boss roles: what ends it
f.champs = newRow()                                      -- Mythic Champions killed / needed

f.forces = UI.TimerBar(f, T.BAR_W, C.bar)
f.forcesText = f.forces.text
f.forcesText:SetFont(UI.FONT_BODY, 10, "")
f.affixes = UI.Text(f, 11, C.dim)
f.affixes:SetWidth(T.TEXT_W)

-- the affix stacks and the boon (orange, under the affix names); they may wrap to two lines
f.stacks = {}
for i = 1, T.MAX_STACK_LINES do
    local l = UI.Text(f, 11, C.orange)
    l:SetWidth(T.TEXT_W)
    l:Hide()
    f.stacks[i] = l
end

-- a cleared Rift floor: the server's words, in green (they may wrap)
f.cleared = UI.Text(f, 12, C.teal)
f.cleared:SetWidth(T.TEXT_W)
f.cleared:Hide()

-- end-of-run summary (replaces the rows)
f.result = UI.Text(f, 16, C.teal)
f.resultLines = {}
for i = 1, 8 do
    local l = UI.Text(f, 12, i == 1 and C.text or T.OBJECTIVE)
    l:SetWidth(T.TEXT_W)
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
-- What the run is
------------------------------------------------------------------------------------------------------
-- A Mythic 0: level 0 and no time limit (MpsOf; a key always has level >= 1). The sample (it has a title) never is.
function T.IsMythic0(m)
    return m ~= nil and not m.title and (m.level or 0) == 0 and m.timeLimitSec == 0
end

-- The server's legacy BHMP run (Legacy.lua L.Run(), from S / T / B / D) for the run shown, or nil: only for the
-- live run (never the sample or a summary), of its mode (T.MODE_KEY with a level, T.MODE_M0 without) and at its
-- level. Not by dungeon id: S carries the server's own dungeon id (bh_mplus.cpp SendFullState: run->d->id), MPS the
-- UI id (bh_ui_bridge.cpp MplusUiId: the map id, or MplusWingBase + the own id for a second wing), so the two never
-- agree. S is the instance's own run: X, E and the loading screen clear it (Legacy.lua clearRun).
function T.LegacyRun(m, mode)
    local L = ns.Legacy
    local run = L and L.Run and L.Run()
    if type(run) ~= "table" or not m or m ~= S.mplus or m.result or run.mode ~= mode then
        return nil
    end
    if (mode == T.MODE_KEY) ~= ((m.level or 0) > 0) then
        return nil
    end
    if type(run.level) == "number" and run.level ~= (m.level or 0) then
        return nil
    end
    return run
end

-- Boss i's role from B (1 shown, 2 extra, 3 final), or nil when unknown.
local function bossRole(run, i)
    local b = run and type(run.bosses) == "table" and run.bosses[i]
    local role = type(b) == "table" and tonumber(b.role) or 0
    return role > 0 and role or nil
end

-- One stack in the server's words: "Necrotic x20: -40% healing taken"; Pack Tactics counts allies, not stacks.
function T.StackText(a)
    if a.id == T.PACK_TACTICS then
        return a.name .. ": " .. a.effect
    end
    return a.name .. " x" .. a.stacks .. ": " .. a.effect
end

-- "Boon of Power (+15% damage) 1:42" while the group's boon lasts, else nil.
function T.BoonText()
    local L = ns.Legacy
    local b = L and L.Boon and L.Boon()
    if type(b) ~= "table" or not b.name or not b.left or b.left <= 0 then
        return nil
    end
    local left = ceil(b.left - 1e-6)
    return b.name .. (b.effect and (" (" .. b.effect .. ")") or "") .. " "
        .. string.format("%d:%02d", floor(left / 60), left % 60)
end

-- The stack lines the player has now (Y), then the boon (V); boonAt = the boon's index, or nil.
function T.StackLines()
    local L = ns.Legacy
    local lines, boonAt = {}, nil
    if L and L.AffixStacks then
        for _, a in ipairs(L.AffixStacks()) do
            if #lines < T.MAX_STACK_LINES - 1 then
                lines[#lines + 1] = T.StackText(a)
            end
        end
    end
    local boon = T.BoonText()
    if boon then
        lines[#lines + 1] = boon
        boonAt = #lines
    end
    return lines, boonAt
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
    if m.rift then
        local R = ns.Rift
        local e = R and R.Elapsed and R.Elapsed()
        f.timer:SetText(e and U.Clock(e) or "")
        UI.SetColor(f.timer, C.text)
        f.limit:SetText("")
        return
    end
    if f.boonLine then
        local text = T.BoonText()
        if text then
            f.boonLine:SetText(text)
        else
            T.Refresh()                                  -- the boon is gone: lay out without it
            return
        end
    end
    if m.state == 0 then
        local left = (m.countdownMs or 0) / 1000 - (GetTime() - (m.startedAt or GetTime()))
        f.timer:SetText("Starts in " .. max(0, math.ceil(left)))
        UI.SetColor(f.timer, C.gold)
        f.limit:SetText(T.IsMythic0(m) and T.M0_LIMIT or "")
        f.timebar:SetProgress(0)
        return
    end
    local e = ns.MplusElapsed(m)
    local limit = m.timeLimitSec or 0
    local over = limit > 0 and e > limit
    f.timer:SetText(U.Clock(e))
    UI.SetColor(f.timer, over and C.red or C.text)
    f.limit:SetText(limit > 0 and ("/ " .. U.Clock(limit)) or (T.IsMythic0(m) and T.M0_LIMIT or ""))
    f.timebar:SetProgress(limit > 0 and e / limit or 0)
    -- the cast bar's failed red once over time
    f.timebar:SetStatusBarColor(UI.Rgb(over and C.red or UI.BAR_GOLD))
end

local function hideStacks()
    for _, l in ipairs(f.stacks) do
        l:Hide()
    end
    f.boonLine = nil
end

-- Everything under the clock, before a layout shows its own.
local function hideRows()
    for _, row in ipairs(f.bosses) do
        row:Hide()
    end
    f.note:Hide()
    f.champs:Hide()
    f.forces:Hide()
    f.affixes:Hide()
    f.cleared:Hide()
    hideStacks()
    f.bres:Hide()
    f.timebar:Hide()
    for _, t in ipairs(f.ticks) do
        t:Hide()
    end
    f.result:Hide()
    for _, l in ipairs(f.resultLines) do
        l:Hide()
    end
    f.closeBtn:Hide()
end

-- The lines a text wraps to in the tracker's width (as Activities' A.WrappedLines): the client's own height for it,
-- else (a client that answers one line for a text wider than that) its one-line width over the line's, less a little
-- for the words that move down. Six affix names at +14 take two lines.
T.WRAP_FILL = 0.9
T.MAX_WRAP_LINES = 4
function T.WrappedLines(fs)
    local _, size = fs:GetFont()
    size = size or 12
    local spacing = fs:GetSpacing() or 0
    local n = floor(((fs:GetStringHeight() or size) + spacing) / (size + spacing) + 0.5)
    local w = fs:GetStringWidth() or 0
    if n <= 1 and w > T.TEXT_W then
        n = ceil(w / (T.TEXT_W * T.WRAP_FILL))
    end
    return max(1, min(T.MAX_WRAP_LINES, n))
end

-- A wrapping line at y: as many lines as the text takes (T.WrappedLines). Answers the y under it.
local function placeWrapped(fs, text, y)
    UI.SetText(fs, text)
    fs:ClearAllPoints()
    fs:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y)
    fs:Show()
    return y - T.LINE_H * T.WrappedLines(fs)
end

-- The bosses: in a Mythic 0 only the final boss (role 3) ends the run, the others are optional; in a key an
-- additional boss (role 2) is a bonus. Answers the y under them and whether the roles are known.
local function layoutBosses(m, run, m0, y)
    local names = bossNames(m)
    local count = max(#names, #(m.bossKillSec or {}), run and type(run.bosses) == "table" and #run.bosses or 0)
    for i = 1, 31 do
        if bit.band(m.bossBits or 0, bit.lshift(1, i - 1)) ~= 0 then
            count = max(count, i)
        end
    end
    count = min(count, T.MAX_BOSSES)
    local roles = false
    for i, row in ipairs(f.bosses) do
        if i <= count then
            local done = bit.band(m.bossBits or 0, bit.lshift(1, i - 1)) ~= 0
            local role = bossRole(run, i)
            roles = roles or role ~= nil
            local extra = role and (m0 and role ~= T.ROLE_FINAL or not m0 and role == T.ROLE_EXTRA)
            local b = run and type(run.bosses) == "table" and run.bosses[i]
            local name = names[i] or (type(b) == "table" and type(b.name) == "string" and b.name ~= "" and b.name)
                or ("Boss " .. i)
            local killSec = done and m.bossKillSec and m.bossKillSec[i] or nil
            local tip = { U.Safe(name) }
            if extra then
                tip[#tip + 1] = m0 and T.OPTIONAL_TIP or T.BONUS_TIP
            end
            if killSec then
                tip[#tip + 1] = "Defeated at " .. U.Clock(killSec)
            end
            row.bossName, row.killSec = name, killSec
            row.tip = #tip > 1 and tip or nil
            if done then
                setObjective(row, name, "done", C.mute, C.teal)
            elseif extra then
                setObjective(row, name, m0 and "optional" or "bonus", C.mute, C.mute)
            else
                setObjective(row, name, "-", T.OBJECTIVE, C.mute)
            end
            y = placeRow(row, y)
        end
    end
    return y, roles
end

-- The rows from under the time bar (under the clock for a Mythic 0): the bosses, enemy forces, the Mythic Champions,
-- the affixes and the player's stacks; the frame ends under the last.
local function layoutRun(m)
    hideRows()
    local m0 = T.IsMythic0(m)
    local run = T.LegacyRun(m, m0 and T.MODE_M0 or T.MODE_KEY)
    T.PlaceLimit(m0)
    local y, roles = layoutBosses(m, run, m0, m0 and T.ROWS_M0 or T.ROWS_TIMED)
    if m0 and not roles then
        f.note.tip = nil
        setObjective(f.note, T.M0_NOTE, "", T.OBJECTIVE)
        y = placeRow(f.note, y)
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
    end
    -- a key: the Mythic Champions that must fall (CheckComplete)
    local key = not m0 and run or nil
    local need = key and floor(tonumber(key.champsNeeded) or 0) or 0
    if need > 0 then
        local killed = min(need, floor(tonumber(key.champsKilled) or 0))
        local K = ns.Keys
        local name, text = "Mythic Champions", nil
        if K and K.AffixInfo then
            name, text = K.AffixInfo(T.CHAMPIONS)
        end
        f.champs.tip = text and { U.Safe(name), U.Safe(text) } or nil
        if killed >= need then
            setObjective(f.champs, "Mythic Champions " .. killed .. "/" .. need, "done", C.mute, C.teal)
        else
            setObjective(f.champs, "Mythic Champions " .. killed .. "/" .. need, "-", T.OBJECTIVE, C.mute)
        end
        y = placeRow(f.champs, y)
    end
    -- battle res: Mythic 0 and keys alike (bh_mplus_bres: every Mythic run), while it counts down or runs
    local L = ns.Legacy
    local bres = run and L and L.BattleRes and tonumber(L.BattleRes())
    if bres then
        bres = floor(bres)
        f.bres.text:SetText("Battle res " .. bres)
        UI.SetColor(f.bres.text, bres > 0 and C.dim or C.red)
        f.bres:Show()
    end
    -- the affix names, 2 px under the rows; at +14 and +15 MPS has six (the bridge adds the Mythic Champions and the
    -- Mythical Boons: bh_ui_bridge.cpp ViewOf), two lines in the tracker's width
    local affixes = m.affixNames or T.AffixNames(m.affixes)
    if #affixes > 0 then
        y = placeWrapped(f.affixes, table.concat(affixes, ", "), y - 2)
    end
    -- the player's own stacks and the group's boon (the live run only: never on the sample)
    if m == S.mplus then
        local lines, boonAt = T.StackLines()
        for i, l in ipairs(f.stacks) do
            if lines[i] then
                y = placeWrapped(l, lines[i], y)
            end
        end
        f.boonLine = boonAt and f.stacks[boonAt] or nil
    end
    -- chest thresholds as ticks on the time bar
    local limit = m.timeLimitSec or 0
    for i, t in ipairs(f.ticks) do
        local sec = m.chestSec and m.chestSec[i]
        if not m0 and sec and limit > 0 and sec < limit then
            t:ClearAllPoints()
            t:SetPoint("CENTER", f.timebar, "LEFT", floor(T.BAR_W * sec / limit + 0.5), 0)
            t:Show()
        end
    end
    if not m0 then
        f.timebar:Show()
    end
    f:SetHeight(-y + 8)
end

local RESULT = { [1] = "Timed!", [0] = "Over time", [2] = "Abandoned" }
T.M0_RESULT = "Complete!"

-- Whose the key run was, noted while it ran (ns.Keys.RunOwnership: from the KEYs the server sends, not from who leads):
-- T.owner = { runId, who = "own" | "other" | "unsure" }. Once "own", it stays so for that run: at the end the owner's
-- KEY becomes the new key (another dungeon), which would read as someone else's. The summary needs it for an older
-- bridge, which sent every member the owner's change as their own keyDelta ("Keystone -1", no new key; Complete()
-- sets a new key for run->owner only); the current one sends members no keyDelta, only a line naming the owner's key.
T.owner = nil
function T.NoteOwner()
    local m, K = S.mplus, ns.Keys
    if not (m and not m.result and (m.level or 0) > 0 and K and K.RunOwnership) then
        return
    end
    local who = K.RunOwnership()
    local o = T.owner
    if not who or (o and o.runId == m.runId and o.who == "own") then
        return
    end
    T.owner = { runId = m.runId, who = who }
end

-- Whether a summary's keyDelta is surely not the player's: a run noted as someone else's whose end names no new key.
function T.ForeignKeyDelta(m, r)
    local o = T.owner
    return o ~= nil and o.runId == m.runId and o.who == "other" and not (r.newDungeonId and r.newLevel)
end

local function layoutResult(m)
    local r = m.result
    hideRows()
    T.PlaceLimit(false)
    f.timer:SetText(U.Clock((r.timeMs or 0) / 1000))
    UI.SetColor(f.timer, C.text)
    f.limit:SetText((m.timeLimitSec or 0) > 0 and ("/ " .. U.Clock(m.timeLimitSec)) or "")
    -- a Mythic 0 has no time to beat: MpeOf sends its end as "in time"
    f.result:SetText(r.result == 1 and T.IsMythic0(m) and T.M0_RESULT or RESULT[r.result] or "Run over")
    UI.SetColor(f.result, r.result == 1 and C.teal or C.red)
    f.result:ClearAllPoints()
    f.result:SetPoint("TOPLEFT", f, "TOPLEFT", 12, -52)
    f.result:Show()
    local lines = {}
    if r.keyDelta and r.keyDelta ~= 0 and not T.ForeignKeyDelta(m, r) then
        local sign = r.keyDelta > 0 and ("+" .. r.keyDelta) or tostring(r.keyDelta)
        local newKey = (r.newDungeonId and r.newLevel)
            and (": " .. ns.DungeonName(r.newDungeonId) .. " +" .. r.newLevel) or ""
        lines[#lines + 1] = "Keystone " .. sign .. newKey
    elseif r.newDungeonId and r.newLevel then
        lines[#lines + 1] = "Keystone: " .. ns.DungeonName(r.newDungeonId) .. " +" .. r.newLevel
    end
    if r.score then lines[#lines + 1] = "Score " .. U.Commas(r.score) end
    for _, rw in ipairs(r.rewards) do lines[#lines + 1] = "+ " .. rw end
    -- a long line ("Keystone +2: Scarlet Monastery: Cathedral +12", a member's "+ Thrall's keystone: ...") wraps:
    -- the next one goes under all of it
    local y = -74
    for i, l in ipairs(f.resultLines) do
        if lines[i] then
            y = placeWrapped(l, lines[i], y)
        end
    end
    f.closeBtn:ClearAllPoints()
    f.closeBtn:SetPoint("TOPRIGHT", f, "TOPRIGHT", -12, y - 6)
    f.closeBtn:Show()
    f:SetHeight(-y + 34)
end

-- A Rift floor: its boss while it lives (once cleared, the server's words in green), then the group size and the best
-- floor for it (RIFT's bestFloor during a run: RiftBest for the run's party size). No time limit: the clock and the
-- deaths are the run's, from its first floor.
local function layoutRift(r)
    hideRows()
    T.PlaceLimit(false)
    local rf = r.rf
    local y = T.ROWS_UNTIMED
    if rf and rf.bossId then
        local row = f.bosses[1]
        row.bossName, row.killSec, row.tip = rf.bossName or T.RIFT_BOSS, nil, nil
        setObjective(row, row.bossName, "", T.OBJECTIVE)
        y = placeRow(row, y)
    elseif rf and rf.bossName then
        y = placeWrapped(f.cleared, rf.bossName, y)
    end
    local parts = {}
    if rf and rf.groupSize then
        parts[#parts + 1] = rf.groupSize == 1 and "Solo" or ("Group of " .. rf.groupSize)
    end
    if rf and (rf.bestFloor or 0) > 0 then
        parts[#parts + 1] = "Best floor " .. rf.bestFloor
    end
    if #parts > 0 then
        y = placeWrapped(f.affixes, table.concat(parts, "  -  "), y - 2)
    end
    f:SetHeight(-y + 8)
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

-- The Rift floor the player is on (Rift.lua's RunFloor), unless the run is over (RIFT_END: the server's toast takes
-- over); nil otherwise.
local function riftRun()
    local R = ns.Rift
    local floorNo = not T.riftOver and R and R.RunFloor and R.RunFloor()
    if not floorNo then
        return nil
    end
    local rf = S.rift
    return { rift = true, floor = floorNo, rf = rf and rf.state == 1 and rf or nil }
end

function T.Refresh()
    T.NoteOwner()
    local m = liveRun() or riftRun() or (T.preview and T.SAMPLE) or nil
    T.current = m
    if not m then
        f.boonLine = nil
        f:Hide()
        return
    end
    if m.rift then
        f.titleLevel:SetText("")
        f.title:SetWidth(T.W - 82)
        UI.SetText(f.title, "Eclipse Rift - Floor " .. m.floor)
        local d = m.rf and m.rf.deaths
        f.deaths.text:SetText(d and (d .. (d == 1 and " death" or " deaths")) or "")
        layoutRift(m)
        T.UpdateTimer()
    else
        -- the name in the room the level leaves (the client ends it with "..."), the level right after it
        local lvl = (m.level or 0) > 0 and ("+" .. m.level) or ""
        f.titleLevel:SetText(lvl)
        local room = T.W - 82 - (lvl ~= "" and (ceil(f.titleLevel:GetStringWidth()) + 4) or 0)
        f.title:SetWidth(room)
        UI.SetText(f.title, m.title or ns.DungeonName(m.dungeonId))
        f.title:SetWidth(min(room, ceil(f.title:GetStringWidth()) + 1))
        local d = m.deaths or 0
        f.deaths.text:SetText(d .. (d == 1 and " death" or " deaths"))
        if m.result then
            layoutResult(m)
        else
            layoutRun(m)
            T.UpdateTimer()
        end
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
    if topic == "KEY" then
        T.NoteOwner()
    end
    if topic == "RIFT" and S.rift and S.rift.state == 1 then
        T.riftOver = nil                                 -- a run (again): its floors show
    end
    if topic == "MPLUS" or topic == "RIFT" then
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

ns.On("RIFT_END", function()
    T.riftOver = true
    T.Refresh()
end)

-- The legacy lines the tracker reads: the run's (LEGACY_RUN: S, T, B, D, E, the stacks Y and the boon V, X) and the
-- Rift floor's (LEGACY: U, a floor's S, X).
ns.On("LEGACY_RUN", function()
    T.Refresh()
end)
T.LEGACY_TAGS = { S = true, U = true, X = true }
ns.On("LEGACY", function(tag)
    if tag == "S" then
        T.riftOver = nil                                 -- a Rift floor just entered
    end
    if T.LEGACY_TAGS[tag] then
        T.Refresh()
    end
end)

-- in or out of an instance: a Rift floor is only ever inside one (RunFloor)
ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
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
