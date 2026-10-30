-- Bleakhold: Activities > Dungeon Journey, the old window's page (old BleakholdActivities.lua :195-282) in its anatomy
-- (Activities.lua A.Page): today's board of the Dungeon Board's offers, each a row with the dungeon's thumbnail
-- (JournalArt.lua "btn"), its tier in the tier's colour, the chapter, the modifiers, the Shards it pays, the best score
-- and a lock with the reason in the tooltip; the board's rotation clock, the first run of the day and the queue in the
-- stat column; Find Group and Enter Dungeon for the chosen run. Our extras: the Dungeon Shards balance, the queue
-- panel (what the player is queued for, the start countdown, the level band, Leave queue) and the custom run (any
-- unlocked dungeon at an unlocked tier, with the best and the server record in its list's tooltips).
--
-- Data: the board is the server's BHMP H and J (Legacy.lua), the same offers as the Dungeon Board NPC; the queue, the
-- Shards, the first-run bonus and the custom run's dungeons come from our protocol (QUEUE, BOARD) when it is up, else
-- from H.
-- Actions: the old commands (.act start <key> queue | solo, Legacy.StartJourney), as the old page sent them; the
-- custom run is our QJOIN D, Leave queue our QLEAVE (the old window had neither).
-- Rules as the server has them (mod-bleakhold bh_dungeon.cpp, bh_activities.cpp): an offer is open (J status 0), or
-- needs a level (1), a Chapter N-1 dungeon cleared on Normal (2) or 70% on the tier below (3, UnlockScore); a run
-- starts outside any instance and out of the game's Dungeon Finder queue, from the party leader only, never a raid
-- group (CanLaunch); a queue starts when 5 players joined or its
-- timer ran out (JoinLobby); a run's Shards scale with its score, +20% with 4 or 5 players, and the first run of the
-- day pays them twice (TakeFirstRunBonus).
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S
local A = ns.Activities
local L = ns.Legacy

local floor, max, min = math.floor, math.max, math.min

local P = A.Page("dungeons", {
    title = "Dungeon Journey",
    desc = "Level through dungeons instead of quests. Pick a run from today's board, start it alone or queue for a "
        .. "group - the dungeon scales to your party. Clear it fast and clean for a high score and more Shards.",
    art = function(page)
        return page:ArtKey()
    end,
})
ns.Dungeons = P

-- The old board's rows (old :205): 420 x 50, 53 apart, seven in view; the scroll bar beside them.
P.ROW_W, P.ROW_H, P.PITCH, P.ROWS = 420, 50, 53, 7
P.LIST_X, P.LIST_Y = 18, -144
P.THUMB_W, P.THUMB_H = 84, 46
P.UNLOCK_SCORE = 70            -- Bleakhold.Journey.UnlockScore (bh_dungeon.cpp), the old page's "70%"
P.MAX_PARTY = 5
P.selected = nil               -- the chosen offer's key

------------------------------------------------------------------------------------------------------
-- The stat column (old :198-200) and the Shards balance
------------------------------------------------------------------------------------------------------
P.rot = P:Stat(1, "Board changes in")
P.bonus = P:Stat(2, "First run of the day")
P.queueStat = P:Stat(3, "Queue")
P.shards = P:Stat(4, "Dungeon Shards")

P.boardTitle = P:Section("Today's Board")

------------------------------------------------------------------------------------------------------
-- Today's board
------------------------------------------------------------------------------------------------------
local scroll = UI.Scroll(P)
scroll:SetPoint("TOPLEFT", P, "TOPLEFT", P.LIST_X, P.LIST_Y)
scroll:SetSize(P.ROW_W + 4 + UI.SCROLL_W, P.ROWS * P.PITCH)
scroll:SetStep(P.PITCH)
P.scroll = scroll

P.empty = UI.Text(P, 12, C.dim, "body", "CENTER")
P.empty:SetPoint("TOP", scroll, "TOP", -10, -60)
P.empty:SetWidth(P.ROW_W - 40)

-- "scroll for 3 more" under the last row in view (old :237)
P.more = UI.Text(P, 10, "999999", "body", "RIGHT")
P.more:SetPoint("TOPRIGHT", scroll, "BOTTOMRIGHT", -(4 + UI.SCROLL_W), -3)

local function tierOf(o)
    return L.TIERS[o.tier] or L.TIERS[0]
end

-- The offer's tooltip (old :215-228), with the reward rules of the server's board.
function P.OfferTooltip(o)
    local t = tierOf(o)
    local lines = { U.Safe(o.name) }
    lines[#lines + 1] = { t.name .. "  -  Chapter " .. o.chapter .. "  -  level " .. o.minLevel .. "+", t.color }
    if o.modNames ~= "" then
        lines[#lines + 1] = { "Modifiers: " .. U.Safe(o.modNames), C.orange, true }
    end
    lines[#lines + 1] = { "Reward: up to " .. U.Commas(o.reward) .. " Shards, +20% with 4 or 5 players", C.text, true }
    if o.best > 0 then
        lines[#lines + 1] = { "Your best: " .. o.best .. "% in " .. U.Clock(o.time) .. " (" .. o.runs
            .. (o.runs == 1 and " run)" or " runs)"), "B3B3B3" }
    end
    local why = P.LockReason(o)
    if why then
        lines[#lines + 1] = { why, "FF4D4D", true }
    end
    return lines
end

-- Why an offer is closed to this character (J status, bh_activities.cpp OfferStatus; the server's own words,
-- bh_dungeon.cpp CanLaunch), or nil when it is open.
function P.LockReason(o)
    if o.status == 1 then
        return "You need level " .. o.minLevel .. "."
    elseif o.status == 2 then
        return "Clear a Chapter " .. max(1, o.chapter - 1) .. " dungeon on Normal first."
    elseif o.status == 3 then
        local below = L.TIERS[max(0, o.tier - 1)] or L.TIERS[0]
        return "Score " .. P.UNLOCK_SCORE .. "% on " .. below.name .. " " .. U.Safe(o.name) .. " first."
    end
    return nil
end

local function selectOffer(o)
    if not o then
        return
    end
    P.selected = o.key
    if PlaySound then
        PlaySound("igMainMenuOptionCheckBoxOn")
    end
    P:Refresh()
    A.UpdateArt()
end

P.rows = {}
local function newRow(i)
    local r = CreateFrame("Button", nil, scroll.child)
    r:SetSize(P.ROW_W, P.ROW_H)
    r:SetPoint("TOPLEFT", scroll.child, "TOPLEFT", 0, -(i - 1) * P.PITCH)
    UI.Backdrop(r, C.card, C.border, nil, "edge")
    r.thumb = r:CreateTexture(nil, "ARTWORK")
    r.thumb:SetSize(P.THUMB_W, P.THUMB_H)
    r.thumb:SetPoint("LEFT", r, "LEFT", 2, 0)
    r.name = UI.Text(r, 13, C.text)
    r.name:SetPoint("TOPLEFT", r, "TOPLEFT", P.THUMB_W + 12, -7)
    UI.OneLine(r.name, 220)
    r.line = UI.Text(r, 11, C.dim)
    r.line:SetPoint("TOPLEFT", r.name, "BOTTOMLEFT", 0, -3)
    UI.OneLine(r.line, 230)
    r.reward = UI.Text(r, 12, C.gold, "body", "RIGHT")
    r.reward:SetPoint("TOPRIGHT", r, "TOPRIGHT", -10, -7)
    r.best = UI.Text(r, 11, "B3B3B3", "body", "RIGHT")
    r.best:SetPoint("BOTTOMRIGHT", r, "BOTTOMRIGHT", -10, 8)
    r.lock = r:CreateTexture(nil, "OVERLAY")
    r.lock:SetTexture("Interface\\LFGFrame\\UI-LFG-ICON-LOCK")
    r.lock:SetSize(20, 20)
    r.lock:SetPoint("RIGHT", r.thumb, "RIGHT", -2, 0)
    r.glow = r:CreateTexture(nil, "HIGHLIGHT")
    r.glow:SetTexture(UI.STOCK.rowHighlight)
    r.glow:SetBlendMode("ADD")
    r.glow:SetAlpha(0.35)
    r.glow:SetPoint("TOPLEFT", r, "TOPLEFT", 1, -1)
    r.glow:SetPoint("BOTTOMRIGHT", r, "BOTTOMRIGHT", -1, 1)
    r:RegisterForClicks("LeftButtonUp")
    r:SetScript("OnClick", function(self)
        selectOffer(self.o)
    end)
    r:SetScript("OnEnter", function(self)
        if self.o then
            UI.ShowTooltip(self, P.OfferTooltip(self.o))
        end
    end)
    r:SetScript("OnLeave", function()
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    return r
end

local function paintRow(r, o)
    r.o = o
    local locked = o.status ~= 0
    ns.Journal.Set(r.thumb, ns.Journal.Key(o.name), "btn", P.THUMB_W, P.THUMB_H)
    r.thumb:SetDesaturated(locked)
    UI.SetText(r.name, o.name)
    UI.SetColor(r.name, locked and "999999" or C.text)
    local t = tierOf(o)
    r.line:SetText("|cff" .. t.color .. t.name .. "|r  Chapter " .. o.chapter
        .. (o.modNames ~= "" and ("  |cffff8040+" .. U.Safe(o.modNames) .. "|r") or ""))
    r.reward:SetText(U.Commas(o.reward) .. " Shards")
    r.best:SetText(o.best > 0 and ("best " .. o.best .. "%") or "")
    if locked then
        r.lock:Show()
    else
        r.lock:Hide()
    end
    UI.Select(r, P.selected == o.key)
    r:Show()
end

-- The chosen offer (on the board now), else the first open one.
function P.Selected()
    local j = L.journey
    local o = P.selected and j.byKey[P.selected]
    if o then
        return o
    end
    P.selected = nil
    for _, x in ipairs(j.offers) do
        if x.status == 0 then
            P.selected = x.key
            return x
        end
    end
    return nil
end

-- The page's picture: the chosen run's dungeon, else the board's first, else Stratholme (old :444).
function P:ArtKey()
    local o = P.Selected() or L.journey.offers[1]
    return (o and ns.Journal.Key(o.name)) or "STRATHOLME"
end

-- How many offers are below the rows in view (old :272-273).
function P:UpdateMore()
    local first = floor((scroll:GetVerticalScroll() or 0) / P.PITCH + 0.5)
    local hidden = #L.journey.offers - P.ROWS - first
    P.more:SetText(hidden > 0 and ("scroll for " .. hidden .. " more") or "")
end

function P:RefreshBoard()
    local j = L.journey
    local offers = j.offers
    for i, o in ipairs(offers) do
        local r = P.rows[i] or newRow(i)
        P.rows[i] = r
        paintRow(r, o)
    end
    for i = #offers + 1, #P.rows do
        P.rows[i].o = nil
        P.rows[i]:Hide()
    end
    scroll:SetContentHeight(#offers > 0 and (#offers * P.PITCH - (P.PITCH - P.ROW_H)) or 0)
    P:UpdateMore()
    if #offers > 0 then
        P.empty:Hide()
    else
        P.empty:SetText(P.EmptyText())
        P.empty:Show()
    end
end

-- The empty board's line: closed (the server's H;0;0;0;0;0, no J), no offers (no dungeon enabled), or not here yet.
function P.EmptyText()
    local j = L.journey
    if j.known and not j.on then
        return "The Dungeon Journey is closed right now."
    elseif j.known then
        local left = L.BoardChangesIn()
        return "No runs on the board right now" .. (left and (" - it changes in " .. U.Clock(left) .. ".") or ".")
    end
    return P.WaitText()
end

------------------------------------------------------------------------------------------------------
-- Find Group / Enter Dungeon (old :238-246)
------------------------------------------------------------------------------------------------------
P.find = UI.Button(P, 170, 26, "Find Group", "red", 12)
P.find:SetPoint("BOTTOMRIGHT", P, "BOTTOMRIGHT", -196, 18)
P.enter = UI.Button(P, 170, 26, "Enter Dungeon", "red", 12)
P.enter:SetPoint("BOTTOMRIGHT", P, "BOTTOMRIGHT", -18, 18)
P.hint = UI.Text(P, 11, C.dim)
P.hint:SetPoint("BOTTOMLEFT", P, "BOTTOMLEFT", A.PAD, 24)
P.hint:SetWidth(360)

P.find.tooltip = function()
    return { "Find Group", { "Queues this run for players of your level range. It starts when 5 players joined or "
        .. "its timer runs out; the dungeon scales to the group.", C.text, true } }
end
P.enter.tooltip = function()
    return { "Enter Dungeon", { "Starts this run now, alone or with your party: the dungeon scales to you.", C.text,
        true } }
end

local function start(how)
    local o = P.Selected()
    if not (o and o.status == 0) then
        return
    end
    if L.StartJourney(o.key, how) and PlaySoundFile then
        PlaySoundFile(how == "queue" and "Sound\\Interface\\lfg_rolecheck.wav" or "Sound\\Interface\\lfg_dungeonready.wav")
    end
end
P.find:SetScript("OnClick", function()
    start("queue")
end)
P.enter:SetScript("OnClick", function()
    start("solo")
end)

-- The old commands go out on a Bleakhold server only; the demo shows the page as it would be.
local function canCommand()
    return L.CanCommand() or Comm.demo and true or false
end

-- In the game's Dungeon Finder: queued, in its role check or its group proposal (the server's LFG_STATE_QUEUED,
-- ROLECHECK, PROPOSAL; 3.3.5a's GetLFGInfoServer, GetLFGRoleUpdate and GetLFGProposal, as FrameXML's GetLFGMode).
function P.InDungeonFinder()
    local queued = GetLFGInfoServer and select(3, GetLFGInfoServer())
    local roleCheck = GetLFGRoleUpdate and GetLFGRoleUpdate()
    local proposal = GetLFGProposal and GetLFGProposal()
    return (queued or roleCheck or proposal) and true or false
end

-- What is in the way of a start, as the server sees it (bh_activities.cpp .act start, bh_dungeon.cpp CanLaunch,
-- bh_ui_bridge.cpp OnQueueJoin): the Bleakhold Royale or 1v1 arena queue (the bridge's QJOIN refuses then; .act start
-- does not, and the run would cost the player that queue), any instance (a dungeon, a raid, a battleground or arena:
-- the run would pull the party out of it), the Dungeon Finder's queue, a raid group, a member who is not the leader,
-- and the player dead, in combat, on a flight path or in the air (CanLaunch; .act start's "Land first").
function P.StartBlock()
    local queued = A.OtherQueueBlock()
    if queued then
        return queued
    end
    if IsInInstance() then
        return "Leave the dungeon or battleground first."
    end
    if P.InDungeonFinder() then
        return "Leave the Dungeon Finder queue first."
    end
    if A.InDungeonFinderGroup() then
        return "Leave the Dungeon Finder group first."
    end
    if (GetNumRaidMembers and GetNumRaidMembers() or 0) > 0 then
        return "Raid groups can't start a dungeon run."
    end
    if (GetNumPartyMembers and GetNumPartyMembers() or 0) > 0 and not (IsPartyLeader and IsPartyLeader()) then
        return "Only your party leader can start or queue a run."
    end
    if UnitIsDeadOrGhost and UnitIsDeadOrGhost("player") then
        return "You are dead."
    end
    if UnitAffectingCombat and UnitAffectingCombat("player") then
        return "You are in combat."
    end
    if UnitOnTaxi and UnitOnTaxi("player") then
        return "You are on a flight."
    end
    if IsFlying and IsFlying() then
        return "Land first: the run brings you back to where you start it."
    end
    return nil
end

-- The party members below a run's level: CanLaunch leaves them out of it ("You were left out of the run"), so the
-- leader goes in without them.
function P.UnderLevel(minLevel)
    local names = {}
    for i = 1, GetNumPartyMembers and GetNumPartyMembers() or 0 do
        local unit = "party" .. i
        local lvl = UnitLevel and UnitLevel(unit) or 0
        if lvl > 0 and lvl < (minLevel or 0) then
            names[#names + 1] = U.Safe(UnitName and UnitName(unit) or "A party member")
        end
    end
    return names
end

function P.WaitText()
    if Comm.ready or Comm.outdated or L.seen or Comm.demo then
        return "Loading the board..."
    end
    return "Waiting for the server..."
end

function P:RefreshButtons()
    local j = L.journey
    local o = P.Selected()
    local block = P.StartBlock()
    local ok = o and o.status == 0 and j.on and not block and canCommand()
    P.find:SetActive(ok and true or false)
    P.enter:SetActive(ok and true or false)
    local hint
    if j.known and not j.on then
        hint = "The Dungeon Journey is closed right now."
    elseif block then
        hint = block
    elseif not o then
        hint = #j.offers > 0 and "Pick a run from the board." or P.EmptyText()
    elseif o.status ~= 0 then
        hint = "|cffff5040Locked:|r hover the run to see why."
    elseif P.QueueState() == 1 or P.QueueState() == 2 then
        -- StartNow and JoinLobby take the player's party out of its Journey queue first (bh_dungeon.cpp LeaveLobby)
        hint = "You are queued for " .. P.QueuedFor() .. ": starting or queueing another run takes you (and your "
            .. "party) out of it."
    elseif (GetNumPartyMembers and GetNumPartyMembers() or 0) > 0 then
        local low = P.UnderLevel(o.minLevel)
        if #low > 0 then
            hint = table.concat(low, ", ") .. (#low == 1 and " is" or " are") .. " below level " .. o.minLevel
                .. " and will be left out."
        else
            hint = "Enter now with your party, or find a group of your level range."
        end
    else
        hint = "Enter now alone, or find a group of your level range."
    end
    P.hint:SetText(hint)
end

------------------------------------------------------------------------------------------------------
-- The queue panel (our extra): what the player is queued for, its countdown and level band, Leave queue
------------------------------------------------------------------------------------------------------
local q = UI.Box(P, 250, 124, C.panel, C.border, nil, "panel")
q:SetPoint("TOPRIGHT", P, "TOPRIGHT", -A.PAD + 4, -A.PAD - 4 * A.STAT_PITCH + 2)
q.title = UI.Heading(q, "Your Queue", 13)
q.title:SetPoint("TOPLEFT", q, "TOPLEFT", 12, -10)
q.status = UI.Text(q, 12, C.text)
q.status:SetPoint("TOPLEFT", q.title, "BOTTOMLEFT", 0, -6)
UI.OneLine(q.status, 226)
q.timer = UI.Text(q, 11, C.dim)
q.timer:SetPoint("TOPLEFT", q.status, "BOTTOMLEFT", 0, -4)
UI.OneLine(q.timer, 226)
q.band = UI.Text(q, 11, C.dim)
q.band:SetPoint("TOPLEFT", q.timer, "BOTTOMLEFT", 0, -3)
UI.OneLine(q.band, 226)
q.leave = UI.Button(q, 120, 22, "Leave queue", "red", 12)
q.leave:SetPoint("BOTTOMRIGHT", q, "BOTTOMRIGHT", -10, 10)
q.leave:SetScript("OnClick", function()
    Comm.Send("QLEAVE")
end)
q:Hide()
P.queue = q

local QUEUE_TEXT = { [1] = "In queue", [2] = "Group found", [3] = "In a run" }

-- What a QUEUE is for: a Journey run (its tier and dungeon), the Eclipse Rift, Bleakhold Royale or the 1v1 arena.
function P.QueueWhat(qs)
    if qs.kind == "R" then
        return "Eclipse Rift"
    elseif qs.kind == "B" then
        return "Bleakhold Royale"
    elseif qs.kind == "A" then
        return qs.tier == 1 and "Rated 1v1 arena" or "1v1 arena skirmish"
    end
    local tier = ns.Data.tiers[(qs.tier or 0) + 1]
    return (tier and (tier .. " ") or "") .. ns.DungeonName(qs.activityId)
end

-- What the player is queued for: our QUEUE's, else the old H's queued offer.
function P.QueuedFor()
    local st, qs = P.QueueState()
    if qs then
        return P.QueueWhat(qs)
    end
    local j = L.journey
    local o = st ~= 0 and j.byKey[j.queuedKey]
    return o and (tierOf(o).name .. " " .. o.name) or "Dungeon Journey"
end

-- The queue's state: 0 none, 1 queued, 2 group found, 3 in a run (QUEUE; else the old H's queued offer).
function P.QueueState()
    local qs = S.queue
    if qs and qs.state ~= 0 then
        return qs.state, qs
    end
    if not qs and L.journey.queuedKey ~= 0 then
        return 1, nil
    end
    return 0, nil
end

function P:QueueTick()
    local st, qs = P.QueueState()
    if st == 0 then
        return
    end
    local since = qs and (GetTime() - (qs.recvAt or GetTime())) or 0
    if qs and st == 1 then
        if qs.kind == "D" and qs.estWaitSec then
            -- a Journey queue starts at its timer's end (or at 5 players): the server's estimate is that start
            q.timer:SetText("Starts in " .. U.Clock(max(0, qs.estWaitSec - since)) .. " or at 5 players")
        else
            local txt = "Waiting " .. U.Clock((qs.queuedSec or 0) + since)
            if qs.estWaitSec then
                txt = txt .. "  -  estimated " .. U.Clock(qs.estWaitSec)
            end
            q.timer:SetText(txt)
        end
    elseif qs and st == 2 then
        local left = qs.timeoutSec and max(0, qs.timeoutSec - since)
        q.timer:SetText(left and ("Answer within " .. floor(left) .. " s") or "")
    end
end

function P:RefreshQueue()
    local st, qs = P.QueueState()
    local j = L.journey
    -- the stat (old :281): queued (players) / in a run / -
    local players = j.queuedKey ~= 0 and j.queuedPlayers > 0 and (" (" .. j.queuedPlayers .. ")") or ""
    if st == 1 or st == 2 then
        P.queueStat:SetText("|cff1aff1aqueued|r" .. players)
    elseif st == 3 then
        P.queueStat:SetText(qs and (qs.kind == "B" or qs.kind == "A") and "in a match" or "in a run")
    else
        P.queueStat:SetText("-")
    end
    if st == 0 then
        q:Hide()
        return
    end
    local what = P.QueuedFor()
    local head = QUEUE_TEXT[st] or ""
    if st == 3 and qs and (qs.kind == "B" or qs.kind == "A") then
        head = "In a match"
    end
    UI.SetText(q.status, head .. ": " .. what)
    q.timer:SetText("")
    local band = ""
    if qs and qs.bandMin and qs.bandMax then
        band = "Levels " .. qs.bandMin .. "-" .. qs.bandMax
    end
    if j.queuedKey ~= 0 and j.queuedPlayers > 0 and (not qs or qs.kind == "D") then
        band = band .. (band ~= "" and "  -  " or "") .. j.queuedPlayers .. " of " .. P.MAX_PARTY .. " players"
    end
    q.band:SetText(band)
    -- leaving needs our protocol (the old commands have no leave); a run is left from inside (Leave dungeon)
    if Comm.ready and (st == 1 or st == 2) then
        q.leave:Show()
    else
        q.leave:Hide()
    end
    q:Show()
    P:QueueTick()
end

------------------------------------------------------------------------------------------------------
-- Custom run (our extra; the Dungeon Board's "Custom run"): any Journey dungeon the player unlocked, at a tier it
-- unlocked there, no modifiers, from anywhere outside an instance. BOARD's dungeons (chapter, level band, tiers, best,
-- server record, lock); QJOIN D <dungeon> <tier> <roles> <size> (bh_ui_bridge.cpp OnQueueJoin, with
-- Bleakhold.UiBridge.RemoteJourney on: the run starts at once when the group is complete as asked, else the player
-- joins that run's queue). Under the stat column, below the queue panel while it shows; only on a realm whose bridge
-- sends BOARD.
------------------------------------------------------------------------------------------------------
P.CUSTOM_W, P.CUSTOM_H = 250, 176
P.custom = { dungeon = nil, tier = 1 }          -- tier 1 Normal .. 4 Nightmare (Data.tiers; QJOIN sends tier - 1)

local cr = UI.Box(P, P.CUSTOM_W, P.CUSTOM_H, C.panel, C.border, nil, "panel")
cr.title = UI.Heading(cr, "Custom Run", 13)
cr.title:SetPoint("TOPLEFT", cr, "TOPLEFT", 12, -10)
cr.text = UI.Para(cr, 11, C.dim, P.CUSTOM_W - 24)
cr.text:SetPoint("TOPLEFT", cr.title, "BOTTOMLEFT", 0, -5)
cr.text:SetText("Any dungeon and tier you have unlocked, without modifiers.")
local function customRow(label, y, onSelect)
    local l = UI.Label(cr, label, 12)
    l:SetPoint("TOPLEFT", cr, "TOPLEFT", 12, y - 6)
    local dd = UI.Dropdown(cr, 160, onSelect)
    dd:SetPoint("TOPRIGHT", cr, "TOPRIGHT", -10, y)
    return dd
end
cr.dungeon = customRow("Dungeon", -72, function(v)
    P.custom.dungeon = tonumber(v)
    P:RefreshCustom()
end)
cr.tier = customRow("Tier", -104, function(v)
    P.custom.tier = tonumber(v) or 1
    P:RefreshCustom()
end)
cr.enter = UI.Button(cr, 110, 24, "Enter Dungeon", "red", 11)
cr.enter:SetPoint("BOTTOMRIGHT", cr, "BOTTOMRIGHT", -10, 12)
cr.find = UI.Button(cr, 110, 24, "Find Group", "red", 11)
cr.find:SetPoint("RIGHT", cr.enter, "LEFT", -6, 0)
cr.enter.tooltip = function()
    return { "Enter Dungeon", { "Starts this run now at the chosen tier, alone or with your party: the dungeon scales "
        .. "to you.", C.text, true } }
end
cr.find.tooltip = function()
    return { "Find Group", { "Queues this run for players of your level range. It starts when 5 players joined or "
        .. "its timer runs out.", C.text, true } }
end
cr:Hide()
P.customBox = cr

function P.TierAllowed(d, tier)
    return d ~= nil and bit.band(d.tierBits or 0, bit.lshift(1, (tier or 1) - 1)) ~= 0
end

-- The dungeons a custom run can take: BOARD's that are not locked, in its order (chapter, then level).
function P.CustomDungeons()
    local out = {}
    for _, d in ipairs(S.board and S.board.dungeons or {}) do
        if not d.locked then
            out[#out + 1] = d
        end
    end
    return out
end

-- A dungeon's row tooltip: chapter, level band, the player's best and the server record.
function P.CustomTip(d)
    local cdef = ns.Def("C", d.chapter)
    local lines = { U.Safe(ns.DungeonName(d.id)) }
    lines[#lines + 1] = { (cdef and cdef.name and U.Safe(cdef.name) or ("Chapter " .. (d.chapter or 0)))
        .. ((d.lvlMin and d.lvlMax) and ("  -  level " .. d.lvlMin .. "-" .. d.lvlMax) or ""), C.dim }
    if d.bestScore then
        local tier = d.bestTier and ns.Data.tiers[d.bestTier + 1]
        -- the Journey score, 0-100 as on the board ("best 82%")
        lines[#lines + 1] = { "Your best: " .. d.bestScore .. "%" .. (tier and (" (" .. tier .. ")") or ""), C.text }
    else
        lines[#lines + 1] = { "No run here yet", C.dim }
    end
    if d.recordScore then
        lines[#lines + 1] = { "Server record: " .. d.recordScore .. "%"
            .. (d.recordName and (" - " .. U.Safe(d.recordName)) or ""), C.gold }
    end
    return lines
end

function P.PartySize()
    return 1 + (GetNumPartyMembers and GetNumPartyMembers() or 0)
end

-- The roles the player picked in the game's Dungeon Finder (GetLFGRoles: leader, tank, healer, damage), else damage.
function P.Roles()
    local _, tank, healer, dps
    if GetLFGRoles then
        _, tank, healer, dps = GetLFGRoles()
    end
    local r = (tank and 1 or 0) + (healer and 2 or 0) + (dps and 4 or 0)
    return r > 0 and r or 4
end

local function customJoin(size, sound)
    local id, tier = P.custom.dungeon, P.custom.tier
    if not id or not P.TierAllowed(S.board and S.board.byId[id], tier) then
        return
    end
    if Comm.Send("QJOIN", "D", id, tier - 1, P.Roles(), size) and PlaySoundFile then
        PlaySoundFile(sound)
    end
end
cr.enter:SetScript("OnClick", function()
    customJoin(P.PartySize(), "Sound\\Interface\\lfg_dungeonready.wav")
end)
cr.find:SetScript("OnClick", function()
    customJoin(P.MAX_PARTY, "Sound\\Interface\\lfg_rolecheck.wav")
end)

function P:RefreshCustom()
    local b = S.board
    if not (b and #b.dungeons > 0) or not (Comm.ready or Comm.demo) then
        cr:Hide()
        return
    end
    local list = P.CustomDungeons()
    -- the chosen dungeon while it stays open, else the first one of the player's level band, else the first
    local chosen = P.custom.dungeon and b.byId[P.custom.dungeon]
    if chosen and chosen.locked then
        chosen = nil
    end
    if not chosen then
        local level = UnitLevel and UnitLevel("player") or 0
        for _, d in ipairs(list) do
            if d.lvlMin and d.lvlMax and level >= d.lvlMin and level <= d.lvlMax then
                chosen = d
                break
            end
        end
        chosen = chosen or list[1]
    end
    P.custom.dungeon = chosen and chosen.id or nil
    local items = {}
    for _, d in ipairs(list) do
        items[#items + 1] = { value = d.id, text = U.Safe(ns.DungeonName(d.id)), tip = P.CustomTip(d) }
    end
    cr.dungeon:SetItems(items)
    if chosen then
        cr.dungeon:SetValue(chosen.id, true)
    else
        cr.dungeon.label:SetText("None unlocked")
    end
    cr.dungeon:SetActive(#items > 0)
    -- the tiers unlocked for it: the chosen one while it is (Normal to start with), else the highest
    local tiers = {}
    for i, name in ipairs(ns.Data.tiers) do
        if P.TierAllowed(chosen, i) then
            tiers[#tiers + 1] = { value = i, text = name }
        end
    end
    if not P.TierAllowed(chosen, P.custom.tier) then
        P.custom.tier = #tiers > 0 and tiers[#tiers].value or 1
    end
    cr.tier:SetItems(tiers)
    cr.tier:SetValue(P.custom.tier, true)
    if #tiers == 0 then
        cr.tier.label:SetText("-")
    end
    cr.tier:SetActive(#tiers > 1)
    local j = L.journey
    local st = P.QueueState()
    local ok = chosen ~= nil and P.TierAllowed(chosen, P.custom.tier) and not (j.known and not j.on)
        and not P.StartBlock() and st ~= 1 and st ~= 2
    cr.enter:SetActive(ok and true or false)
    -- a full party has no one to find: Enter Dungeon starts it
    cr.find:SetActive(ok and P.PartySize() < P.MAX_PARTY or false)
    cr:ClearAllPoints()
    if q:IsShown() then
        cr:SetPoint("TOPRIGHT", q, "BOTTOMRIGHT", 0, -8)
    else
        cr:SetPoint("TOPRIGHT", q, "TOPRIGHT", 0, 0)
    end
    cr:Show()
end

------------------------------------------------------------------------------------------------------
-- Refresh
------------------------------------------------------------------------------------------------------
function P:RefreshStats()
    local j = L.journey
    local left = L.BoardChangesIn()
    P.rot:SetText(left and U.Clock(left) or "-")
    local done
    if j.known then
        done = j.firstDone
    elseif S.board then
        done = not S.board.firstRunBonus
    end
    if done == nil then
        P.bonus:SetText("-")
    elseif done then
        P.bonus:SetText("|cff808080used|r")
    else
        P.bonus:SetText("|cff1aff1adouble Shards|r")
    end
    local shards = (S.board and S.board.shards) or (S.week and S.week.shards)
    if shards then
        P.shards:SetText(U.Commas(shards))
        P.shards:Show()
        P.shards.label:Show()
    else
        P.shards:Hide()
        P.shards.label:Hide()
    end
end

function P:Refresh()
    P.Selected()
    P:RefreshStats()
    P:RefreshBoard()
    P:RefreshButtons()
    P:RefreshQueue()
    P:RefreshCustom()
end

function P:Tick()
    local left = L.BoardChangesIn()
    P.rot:SetText(left and U.Clock(left) or "-")
    P:QueueTick()
    -- the board changed: ask for the new one (at most every few seconds)
    if left == 0 then
        L.Request()
    end
end

function P:OnOpen()
    L.Request()
    Comm.Get("BOARD")
    Comm.Get("QUEUE")
end

-- the wheel, the arrows and the knob move the board: the "more" line follows
scroll:HookScript("OnMouseWheel", function()
    P:UpdateMore()
end)
scroll.bar:HookScript("OnValueChanged", function()
    P:UpdateMore()
end)
