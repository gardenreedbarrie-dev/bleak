-- Bleakhold: arena seasons and the 1v1 ladder (docs/BleakholdProtocol.md section 20). Everything shown is server
-- state (ARENA, LB/LBME board A, DEF V and Q, QUEUE kind A, parsed in State.lua); the client counts the season's
-- clock down and sends only the player's wishes: GET ARENA (at most every 30 s), QJOIN A,1,tier,4,1 and QLEAVE.
-- This file holds the helpers the Leaderboards' Arena tab shares (tier names and colours, the season list), the
-- Arena page of Activities (the season header, a card per bracket, the 1v1 queue, the last matches, and the live
-- cutoffs, the reward checklist and the season's rewards of one bracket), the match toast, /bh arena and the
-- arena part of /bh demo.
--
-- Without HELLO feature bit 65536 there is no Arena page, no nav entry and no Arena leaderboard: the page's
-- Available() says no (Activities.Show goes to Tasks) and nothing of section 20 is sent.
local ADDON, ns = ...
local U, UI, Comm, Data = ns.U, ns.UI, ns.Comm, ns.Data
local C = UI.C
local S = ns.S
local A = ns.Activities

local floor, ceil, max, min = math.floor, math.ceil, math.max, math.min

local AR = {}
ns.Arena = AR

AR.BRACKETS = { 1, 2, 3, 5 }
AR.ACTIVITY = 1                   -- QJOIN A: the activity is always 1, the size always 1
AR.ROLES = 4                      -- ignored by the server for the arena
AR.ASK_EVERY = 30                 -- GET ARENA at most this often while the page shows the cutoffs (section 8)
AR.GAP = { QJOIN = 1.1, QLEAVE = 1.1 }
AR.NOTICE_TIME = 12               -- s an ERR of the 1v1 queue stays on the queue card
AR.KICKER = "ARENA"

AR.STATE = { NONE = 0, LIVE = 1, FINAL_WEEK = 2, CLOSED = 3, FINAL = 4, DELIVERED = 5, UPCOMING = 6 }
AR.STATE_TEXT = {
    [0] = "No arena season", [1] = "Live", [2] = "Final week", [3] = "Rated closed", [4] = "Final standings",
    [5] = "Rewards delivered", [6] = "Upcoming",
}
AR.STATE_COLOR = {
    [0] = C.mute, [1] = C.teal, [2] = C.orange, [3] = C.red, [4] = C.goldLight, [5] = C.goldLight, [6] = C.purple,
}

-- What keeps the player from the rewards (ARENA B missingMask), in the order of the checklist.
AR.MISSING = { GAMES = 1, SHARE = 2, PERSONAL = 4, RECENT = 8, WINS = 16, LEVEL = 32, HELD = 64, CLOSED = 128 }

AR.GRANT_TEXT = { [0] = "Rewards on the way", [1] = "Rewards delivered", [2] = "Rewards held for review" }
AR.GRANT_COLOR = { [0] = C.goldLight, [1] = C.teal, [2] = C.orange }

-- Match verdicts (ARENA M): short text for the row, sentence for its tooltip.
local VERDICTS = {
    [1] = { R = { "Half gain: rematch", "Reduced: the same opponents met for the 4th to 6th time within 24 hours, so "
        .. "the winners gained half." } },
    [2] = {
        R = { "Not counted: rematch",
            "Win not counted: the same opponents met for the 7th time or more within 24 hours." },
        I = { "Not counted: same network", "Win not counted: a winner and a loser play from the same network." },
        E = { "Not counted: no contest", "Win not counted: the match ended within a minute of the gates opening and "
            .. "the losers did next to nothing." },
        S = { "Not counted: too short", "Win not counted: the match was over within 15 seconds of the gates opening." },
    },
}

-- What a reward kind (DEF Q) is called before its text.
local REWARD_PREFIX = { T = "Title", M = "Mount", I = "Item", X = "Looks" }

------------------------------------------------------------------------------------------------------
-- Helpers (the Leaderboards' Arena tab uses these too)
------------------------------------------------------------------------------------------------------
function AR.Live()
    return Comm.HasFeature(Comm.FEATURE.ARENA)
end

function AR.State()
    return S.arena
end

function AR.BracketName(b)
    return b and (b .. "v" .. b) or "-"
end

function AR.TierName(id)
    if not id then
        return nil
    end
    return ns.DefName("V", id, "Tier " .. id)
end

-- The tier's colour as six hex digits (anything else from the server falls back to a neutral colour).
function AR.TierColor(id)
    local d = id and ns.Def("V", id)
    local c = d and d.color
    if type(c) == "string" and c:match("^%x%x%x%x%x%x$") then
        return c:upper()
    end
    return C.mid
end

-- The tier's name in its colour, ready for a FontString; "-" for none.
function AR.TierText(id)
    local name = AR.TierName(id)
    if not name then
        return "-"
    end
    return U.Color(AR.TierColor(id), U.Safe(name))
end

-- What a tier takes now: the higher of the last team inside it and its floor.
function AR.Takes(cut)
    return max(cut.cutRating or 0, cut.floor or 0)
end

-- The live cutoffs of one bracket, highest tier first.
function AR.Cutoffs(bracket, a)
    a = a or S.arena
    local list = {}
    for _, c in ipairs(a and a.cutoffs or {}) do
        if c.bracket == bracket then
            list[#list + 1] = c
        end
    end
    table.sort(list, function(x, y) return x.tierId > y.tierId end)
    return list
end

function AR.Cutoff(bracket, tierId, a)
    for _, c in ipairs(AR.Cutoffs(bracket, a)) do
        if c.tierId == tierId then
            return c
        end
    end
    return nil
end

-- The way from what the player's tier takes now to what the next one takes (0..1), or nil when unknown: LBME's
-- barPermille when the shown leaderboard is this bracket of this season, else from the cutoffs of ARENA T.
function AR.NextBar(bracket, a)
    a = a or S.arena
    local b = a and a.brackets[bracket]
    if not b or not b.hasTeam or not b.rating or not b.nextTierId or not b.toNext then
        return nil
    end
    local lb, me = S.lb.A, S.lbme.A
    if lb and me and lb.dungeonId == bracket and (lb.seasonId == 0 or lb.seasonId == a.seasonId)
        and me.dungeonId == bracket and me.tierId == b.tierId then
        return (me.barPermille or 0) / 1000
    end
    local cut = b.tierId and AR.Cutoff(bracket, b.tierId, a)
    if not cut then
        return nil
    end
    local lo, hi = AR.Takes(cut), b.rating + b.toNext
    if hi <= lo then
        return 1
    end
    return U.Clamp((b.rating - lo) / (hi - lo), 0, 1)
end

-- "+66 to Duelist", "Rating enough for Gladiator", "Top of the ladder", or "".
function AR.NextText(b)
    if not b or not b.hasTeam then
        return ""
    end
    if b.nextTierId and b.toNext then
        local name = U.Safe(AR.TierName(b.nextTierId))
        if b.toNext > 0 then
            return "+" .. b.toNext .. " to " .. name
        end
        return "Rating enough for " .. name
    end
    if b.tierId == 6 then
        return "Top of the ladder"
    end
    return ""
end

local function bits(mask, bitValue)
    return bit.band(mask or 0, bitValue) ~= 0
end
AR.HasBit = bits

-- The reward checklist of one bracket: { { ok = bool, text = "..." }, ... } (missingMask, section 20).
function AR.Checklist(bracket, b)
    local out = {}
    if not b or not b.hasTeam then
        return out
    end
    local M = AR.MISSING
    local mask = b.missing or 0
    local team = bracket ~= 1
    local function add(bitValue, okText, badText)
        local bad = bits(mask, bitValue)
        out[#out + 1] = { ok = not bad, bit = bitValue, text = bad and badText or okText }
    end
    local games, wins, recent = b.games or 0, b.wins or 0, b.recent or 0
    add(M.GAMES, "Season games: " .. games, "Season games: " .. games .. " - more are needed for rewards")
    if team then
        add(M.SHARE, "You played enough of your team's games", "Play at least half of your team's games")
        local pr = b.personal and (" (" .. b.personal .. ")") or ""
        add(M.PERSONAL, "Personal rating close enough to the team's" .. pr,
            "Personal rating too far below the team's" .. pr)
    end
    add(M.RECENT, "Recent games: " .. recent .. " in the last 21 days",
        "Recent games: " .. recent .. " in the last 21 days - too few for Duelist and above")
    add(M.WINS, "Season wins: " .. wins, "Season wins: " .. wins .. " - too few for Gladiator and Rank One")
    add(M.LEVEL, "At the level cap", "Reach the level cap")
    if bits(mask, M.HELD) then
        add(M.HELD, "", "Your rewards wait for a game master's review")
    end
    if bits(mask, M.CLOSED) then
        add(M.CLOSED, "", "Too few teams this season: this bracket gives Combatant only")
    end
    return out
end

-- The missing conditions only (for tooltips).
function AR.MissingLines(bracket, b)
    local out = {}
    for _, line in ipairs(AR.Checklist(bracket, b)) do
        if not line.ok then
            out[#out + 1] = line.text
        end
    end
    return out
end

-- short, sentence, colour of a match verdict; nil for a counted match.
function AR.Verdict(m)
    if not m or (m.verdict or 0) == 0 then
        return nil
    end
    local byReason = VERDICTS[m.verdict] or {}
    local v = byReason[m.reason or ""]
    local color = m.verdict == 2 and C.orange or C.goldLight
    if v then
        return v[1], v[2], color
    end
    if m.verdict == 1 then
        return "Half gain", "Reduced: the winners gained half.", color
    end
    return "Not counted", "Win not counted.", color
end

-- "+14", "-11", "0".
function AR.Signed(n)
    n = n or 0
    if n > 0 then
        return "+" .. n
    end
    return tostring(n)
end

-- The season's reward rows of one bracket (DEF Q): a row of this season replaces the season-0 row of the same tier
-- and kind. Returns { { tierId, rows = { q, ... } }, ... }, highest tier first.
function AR.Rewards(bracket, seasonId)
    local pick = {}
    for _, id in ipairs(ns.DefIds("Q")) do
        local q = ns.Def("Q", id)
        if q and q.bracket == bracket and q.tierId and q.kind and (q.seasonId == 0 or q.seasonId == seasonId) then
            local key = q.tierId .. q.kind
            local have = pick[key]
            if q.seasonId ~= 0 then
                if not (have and have.seasonId ~= 0) then
                    pick[key] = { list = { q }, seasonId = q.seasonId }
                else
                    have.list[#have.list + 1] = q
                end
            elseif not have then
                pick[key] = { list = { q }, seasonId = 0 }
            elseif have.seasonId == 0 then
                have.list[#have.list + 1] = q
            end
        end
    end
    local byTier = {}
    for _, p in pairs(pick) do
        for _, q in ipairs(p.list) do
            byTier[q.tierId] = byTier[q.tierId] or {}
            local rows = byTier[q.tierId]
            rows[#rows + 1] = q
        end
    end
    local out = {}
    for tierId, rows in pairs(byTier) do
        table.sort(rows, function(x, y)
            if x.kind ~= y.kind then
                return x.kind < y.kind
            end
            return (x.entry or 0) < (y.entry or 0)
        end)
        out[#out + 1] = { tierId = tierId, rows = rows }
    end
    table.sort(out, function(x, y) return x.tierId > y.tierId end)
    return out
end

-- One reward as text, and whether the character has it already (a title's achievement, an item in the bags).
function AR.RewardLine(q)
    local text = q.text
    local owned = false
    if q.kind == "T" and q.entry and q.entry > 0 and GetAchievementInfo then
        local _, name, _, completed = GetAchievementInfo(q.entry)
        text = text or name
        owned = completed and true or false
    elseif (q.kind == "M" or q.kind == "I") and q.entry and q.entry > 0 then
        text = text or GetItemInfo(q.entry) or ("item #" .. q.entry)
        owned = GetItemCount ~= nil and (GetItemCount(q.entry) or 0) > 0
    elseif q.kind == "C" then
        text = text or (U.Commas(q.count) .. " Dungeon Shards")
    elseif q.kind == "H" then
        text = text or (U.Commas(q.count) .. " honor")
    elseif q.kind == "A" then
        text = text or (U.Commas(q.count) .. " arena points")
    elseif q.kind == "W" then
        text = text or (U.Commas(q.count) .. " war effort")
    elseif q.kind == "F" then
        text = text or "A server first"
    end
    text = U.Safe(text or "Reward")
    local prefix = REWARD_PREFIX[q.kind or ""]
    if prefix then
        text = prefix .. ": " .. text
    end
    return text, owned
end

-- The arena seasons for the leaderboard's season choice: the current one first (value 0), then the past ones.
function AR.SeasonItems()
    local a = S.arena
    local items, current = {}, nil
    local past = {}
    for _, s in ipairs(a and a.seasons or {}) do
        if s.state == 1 then
            current = s
        elseif s.state == 0 then
            past[#past + 1] = s
        end
    end
    local currentName = current and U.Safe(current.name or ("Arena Season " .. current.id))
    items[1] = { value = 0, text = currentName or "Current season" }
    table.sort(past, function(x, y) return x.id > y.id end)
    for _, s in ipairs(past) do
        items[#items + 1] = { value = s.id, text = U.Safe(s.name or ("Arena Season " .. s.id)) }
    end
    return items
end

-- The season's clock: "Ends in 30 d 4 h", "Starts in 2 d 1 h", ...
function AR.Countdown(a, now)
    a = a or S.arena
    if not a then
        return ""
    end
    now = now or Comm.ServerTime()
    local st = a.state
    local function left(epoch)
        return epoch and U.Duration(epoch - now) or nil
    end
    if st == AR.STATE.LIVE or st == AR.STATE.FINAL_WEEK then
        local l = left(a.endEpoch)
        return l and ("Ends in " .. l) or ""
    elseif st == AR.STATE.UPCOMING then
        local l = left(a.startEpoch or a.nextStartEpoch)
        return l and ("Starts in " .. l) or "The next season is coming"
    elseif st == AR.STATE.NONE then
        return "No arena season is scheduled"
    end
    local l = left(a.nextStartEpoch)
    local head = st == AR.STATE.FINAL and "Game masters review the results" or "Rated arena is closed"
    if st == AR.STATE.DELIVERED then
        head = "Season over"
    end
    return head .. (l and ("  -  next season in " .. l) or "")
end

------------------------------------------------------------------------------------------------------
-- Asking for ARENA (unrevisioned: the server pushes it after HELLO and after each rated match; the client asks
-- when it shows the page, then at most every 30 s while the page stays open)
------------------------------------------------------------------------------------------------------
AR.askedAt = nil

function AR.Ask(force)
    if not AR.Live() or (not Comm.ready and not Comm.demo) then
        return false
    end
    local now = GetTime()
    -- without any ARENA yet (the push after HELLO went missing) a few seconds are enough
    local every = S.arena and AR.ASK_EVERY or 5
    if not force and AR.askedAt and now - AR.askedAt < every then
        return false
    end
    AR.askedAt = now
    return Comm.Refresh("ARENA")
end

ns.On("STATE", function(topic)
    if topic == "ARENA" and S.arena then
        AR.askedAt = AR.askedAt and max(AR.askedAt, S.arena.recvAt or 0) or S.arena.recvAt
    end
end)

------------------------------------------------------------------------------------------------------
-- The 1v1 queue: QJOIN A,1,tier,4,1 and QLEAVE (one gate per op, a little above the server's 1 s)
------------------------------------------------------------------------------------------------------
local nextAt = {}

local function notice(text)
    if text and UIErrorsFrame then
        UIErrorsFrame:AddMessage(text, 1, 0.45, 0.4)
    elseif text then
        ns.Print(text)
    end
end
AR.Notice = notice

local function send(op, ...)
    local now = GetTime()
    if nextAt[op] and now < nextAt[op] then
        return false
    end
    local ok = Comm.Send(op, ...)
    if ok then
        nextAt[op] = now + (AR.GAP[op] or 1)
        AR.sentAt = now
    end
    return ok and true or false
end

function AR.Queue()
    local q = S.queue
    return q and q.kind == "A" and q or nil
end

function AR.Queued()
    local q = AR.Queue()
    return q ~= nil and (q.state == 1 or q.state == 2)
end

-- Why the player cannot queue for the 1v1 arena from this client (rated or not), or nil.
function AR.QueueBlock(rated)
    if Comm.outdated then
        return "Your Bleakhold addon is out of date."
    end
    if not Comm.ready and not Comm.demo then
        return "Not connected to the realm."
    end
    if not AR.Live() then
        return "Arena seasons are not running on this realm."
    end
    local a = S.arena
    if not a then
        return "Waiting for your arena season..."
    end
    if not a.teamCost then
        return "The 1v1 queue is not open on this realm."
    end
    if rated and not a.ratedOpen then
        local l = a.nextStartEpoch and U.Duration(a.nextStartEpoch - Comm.ServerTime())
        return "Rated arena is closed" .. (l and (" - the next season starts in " .. l) or "") .. "."
    end
    return nil
end

-- Join the 1v1 queue: rated (tier 1) or a skirmish (tier 0). A rated join without a 1v1 team that costs money asks
-- first; the server makes the team and takes the money.
function AR.Join(rated)
    local block = AR.QueueBlock(rated)
    if block then
        notice(block)
        return false
    end
    local a = S.arena
    local b1 = a.brackets[1]
    local function go()
        return send("QJOIN", "A", AR.ACTIVITY, rated and 1 or 0, AR.ROLES, 1)
    end
    if rated and not (b1 and b1.hasTeam) and (a.teamCost or 0) > 0 then
        UI.Confirm("Rated 1v1 needs your own 1v1 arena team. Make it for " .. ns.RewardText("G", a.teamCost)
            .. " and join the queue?", go, "Pay and queue")
        return "confirm"
    end
    return go()
end

function AR.Leave()
    if not AR.Queued() then
        return false
    end
    return send("QLEAVE")
end

-- An ERR of the 1v1 queue goes on the queue card (and to the error frame, State.lua).
ns.On("ERR", function(e)
    if not e or (e.op ~= "QJOIN" and e.op ~= "QLEAVE") then
        return
    end
    if e.code == "busy" and AR.GAP[e.op] then
        nextAt[e.op] = GetTime() + AR.GAP[e.op]
    end
    local ours = (e.code or ""):find("^arena_") or (AR.sentAt and GetTime() - AR.sentAt < 5)
    if ours then
        AR.lastError = { text = e.shown or U.Safe(e.text or e.code or ""), code = e.code, at = GetTime() }
        if AR.page and AR.page:IsVisible() then
            AR.page:Refresh()
        end
    end
end)

function AR.ErrorNotice()
    local e = AR.lastError
    if e and GetTime() - e.at < AR.NOTICE_TIME then
        return e.text
    end
    return nil
end

------------------------------------------------------------------------------------------------------
-- Activities: the Arena page
------------------------------------------------------------------------------------------------------
local P = A.NewPage()
A.AddPage("arena", P)
AR.page = P
P.bracket = 1
P.view = "cutoffs"

function P.Available()
    return AR.Live()
end

local PW, PH = A.PW, A.PH
local HEAD_H = 64
local CARD_Y = HEAD_H + 12
local CARD_H = 150
local CARD_W = floor((PW - 30) / 4)
local LOW_Y = CARD_Y + CARD_H + 12
local LOW_H = PH - LOW_Y
local LEFT_W = 300
local RIGHT_W = PW - LEFT_W - 12
local QUEUE_H = 132
local MATCH_H = LOW_H - QUEUE_H - 10

-- Header: the season, its state and its clock
local head = UI.Box(P, PW, HEAD_H, C.eraBg, C.eraBorder)
head:SetPoint("TOPLEFT", P, "TOPLEFT", 0, 0)
head.kicker = UI.Text(head, 11, C.purple)
head.kicker:SetPoint("TOPLEFT", head, "TOPLEFT", 16, -12)
head.kicker:SetText(AR.KICKER)
head.title = UI.Text(head, 20, C.goldPale, "title")
head.title:SetPoint("TOPLEFT", head.kicker, "BOTTOMLEFT", 0, -3)
UI.OneLine(head.title, 300)
head.state = UI.Pill(head, "", C.chip, C.chipBorder, C.text, 11)
head.state:SetPoint("LEFT", head.kicker, "RIGHT", 10, 0)
head.clock = UI.Text(head, 12, C.mid)
head.clock:SetPoint("TOPLEFT", head, "TOPLEFT", 330, -36)
UI.OneLine(head.clock, 220)
head.board = UI.Button(head, 112, 28, "Leaderboard", "ghost", 12)
head.board:SetPoint("RIGHT", head, "RIGHT", -14, 0)
head.board:SetScript("OnClick", function()
    if ns.Leaderboards then
        ns.Leaderboards.OpenArena(AR.page.bracket)
    end
end)
head.pvp = UI.Button(head, 112, 28, "Arena teams", "ghost", 12)
head.pvp:SetPoint("RIGHT", head.board, "LEFT", -8, 0)
head.pvp.tooltip = function()
    return { "Arena teams", "The 2v2, 3v3 and 5v5 teams are made and managed in the game's PvP window." }
end
P.head = head

function AR.OpenPvpWindow()
    if TogglePVPFrame then
        TogglePVPFrame()
    else
        notice("Open the PvP window to manage your arena teams.")
    end
end
head.pvp:SetScript("OnClick", AR.OpenPvpWindow)

-- One card per bracket
P.cards = {}
for i, bracket in ipairs(AR.BRACKETS) do
    local c = CreateFrame("Button", nil, P)
    c:SetSize(CARD_W, CARD_H)
    UI.Backdrop(c, C.card, C.border)
    c:SetPoint("TOPLEFT", P, "TOPLEFT", (i - 1) * (CARD_W + 10), -CARD_Y)
    c:RegisterForClicks("LeftButtonUp")
    c.bracket = bracket
    c.kicker = UI.Text(c, 11, C.dim)
    c.kicker:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -10)
    c.kicker:SetText(AR.BracketName(bracket):upper())
    c.tier = UI.Text(c, 12, C.mid, "body", "RIGHT")
    c.tier:SetPoint("TOPRIGHT", c, "TOPRIGHT", -10, -10)
    UI.OneLine(c.tier, CARD_W - 60)
    c.team = UI.Text(c, 12, C.mid)
    c.team:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -26)
    UI.OneLine(c.team, CARD_W - 24)
    c.rating = UI.Text(c, 22, C.goldPale, "title")
    c.rating:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -44)
    c.rank = UI.Text(c, 11, C.dim)
    c.rank:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -74)
    UI.OneLine(c.rank, CARD_W - 24)
    c.record = UI.Text(c, 11, C.mid)
    c.record:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -90)
    UI.OneLine(c.record, CARD_W - 24)
    c.bar = UI.Bar(c, CARD_W - 24, 5, C.gold, C.deep)
    c.bar:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -108)
    c.next = UI.Text(c, 11, C.text)
    c.next:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -117)
    UI.OneLine(c.next, CARD_W - 24)
    c.status = UI.Text(c, 11, C.teal)
    c.status:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -132)
    UI.OneLine(c.status, CARD_W - 24)
    c.pvp = UI.Button(c, 110, 24, "PvP window", "ghost", 11)
    c.pvp:SetPoint("BOTTOMLEFT", c, "BOTTOMLEFT", 12, 12)
    c.pvp:SetScript("OnClick", AR.OpenPvpWindow)
    c.pvp:Hide()
    c:SetScript("OnClick", function(self)
        P.bracket = self.bracket
        ns.cdb.arenaBracket = self.bracket
        P:Refresh()
    end)
    c:SetScript("OnEnter", function(self)
        if self.tooltip then
            UI.ShowTooltip(self, self.tooltip())
        end
    end)
    c:SetScript("OnLeave", function()
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    P.cards[i] = c
end

-- The 1v1 queue
local queue = UI.Box(P, LEFT_W, QUEUE_H, C.card, C.border)
queue:SetPoint("TOPLEFT", P, "TOPLEFT", 0, -LOW_Y)
queue.label = UI.Text(queue, 11, C.dim)
queue.label:SetPoint("TOPLEFT", queue, "TOPLEFT", 12, -12)
queue.label:SetText("1V1 QUEUE")
queue.status = UI.Text(queue, 14, C.text)
queue.status:SetPoint("TOPLEFT", queue, "TOPLEFT", 12, -30)
UI.OneLine(queue.status, LEFT_W - 24)
queue.detail = UI.Text(queue, 11, C.dim)
queue.detail:SetPoint("TOPLEFT", queue, "TOPLEFT", 12, -50)
UI.OneLine(queue.detail, LEFT_W - 24)
queue.notice = UI.Text(queue, 11, C.red)
queue.notice:SetPoint("TOPLEFT", queue, "TOPLEFT", 12, -64)
queue.notice:SetWidth(LEFT_W - 24)
queue.notice:SetHeight(26)
queue.notice:SetJustifyV("TOP")
queue.rated = UI.Button(queue, 136, 30, "Rated 1v1", "gold", 13)
queue.rated:SetPoint("BOTTOMLEFT", queue, "BOTTOMLEFT", 12, 12)
queue.skirmish = UI.Button(queue, 128, 30, "Skirmish", "dark", 13)
queue.skirmish:SetPoint("BOTTOMRIGHT", queue, "BOTTOMRIGHT", -12, 12)
queue.leave = UI.Button(queue, LEFT_W - 24, 30, "Leave queue", "dark", 13)
queue.leave:SetPoint("BOTTOMLEFT", queue, "BOTTOMLEFT", 12, 12)
queue.leave:Hide()
queue.rated:SetScript("OnClick", function()
    AR.Join(true)
end)
queue.skirmish:SetScript("OnClick", function()
    AR.Join(false)
end)
queue.leave:SetScript("OnClick", function()
    AR.Leave()
end)
P.queue = queue

-- The last rated matches
local matches = UI.Box(P, LEFT_W, MATCH_H, C.card, C.border)
matches:SetPoint("TOPLEFT", queue, "BOTTOMLEFT", 0, -10)
matches.label = UI.Text(matches, 11, C.dim)
matches.label:SetPoint("TOPLEFT", matches, "TOPLEFT", 12, -12)
matches.label:SetText("LAST RATED MATCHES")
matches.empty = UI.Text(matches, 12, C.mute)
matches.empty:SetPoint("TOPLEFT", matches, "TOPLEFT", 12, -36)
matches.rows = {}
for i = 1, 5 do
    local r = CreateFrame("Frame", nil, matches)
    r:SetSize(LEFT_W - 24, 20)
    r:SetPoint("TOPLEFT", matches, "TOPLEFT", 12, -32 - (i - 1) * 21)
    r:EnableMouse(true)
    r.left = UI.Text(r, 12, C.text)
    r.left:SetPoint("LEFT", r, "LEFT", 0, 0)
    UI.OneLine(r.left, 118)
    r.right = UI.Text(r, 11, C.dim, "body", "RIGHT")
    r.right:SetPoint("RIGHT", r, "RIGHT", 0, 0)
    UI.OneLine(r.right, LEFT_W - 24 - 122)
    r:SetScript("OnEnter", function(self)
        if self.tooltip then
            UI.ShowTooltip(self, self.tooltip())
        end
    end)
    r:SetScript("OnLeave", function()
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    r:Hide()
    matches.rows[i] = r
end
P.matches = matches

-- One bracket in detail: the live cutoffs, the reward checklist, the season's rewards
local detail = UI.Box(P, RIGHT_W, LOW_H, C.panel, C.border)
detail:SetPoint("TOPRIGHT", P, "TOPRIGHT", 0, -LOW_Y)
P.detail = detail
detail.brackets = {}
for i, bracket in ipairs(AR.BRACKETS) do
    local b = UI.Button(detail, 48, 24, AR.BracketName(bracket), "tab", 12)
    b:SetPoint("TOPLEFT", detail, "TOPLEFT", 12 + (i - 1) * 52, -10)
    b.bracket = bracket
    b:SetScript("OnClick", function(self)
        P.bracket = self.bracket
        ns.cdb.arenaBracket = self.bracket
        P:Refresh()
    end)
    detail.brackets[i] = b
end
local VIEWS = { { key = "cutoffs", label = "Cutoffs" }, { key = "checklist", label = "Checklist" },
    { key = "rewards", label = "Rewards" } }
detail.views = {}
for i = #VIEWS, 1, -1 do
    local d = VIEWS[i]
    local b = UI.Button(detail, 80, 24, d.label, "tab", 12)
    b:SetPoint("TOPRIGHT", detail, "TOPRIGHT", -12 - (#VIEWS - i) * 84, -10)
    b.view = d.key
    b:SetScript("OnClick", function(self)
        P.view = self.view
        P:Refresh()
    end)
    detail.views[i] = b
end
local INNER_W = RIGHT_W - 24
detail.body = CreateFrame("Frame", nil, detail)
detail.body:SetPoint("TOPLEFT", detail, "TOPLEFT", 12, -44)
detail.body:SetSize(INNER_W, LOW_H - 56)
detail.empty = UI.Text(detail.body, 12, C.mute, "body", "CENTER")
detail.empty:SetPoint("TOP", detail.body, "TOP", 0, -60)
detail.empty:SetWidth(INNER_W - 40)
detail.foot = UI.Text(detail.body, 11, C.dim)
detail.foot:SetPoint("BOTTOMLEFT", detail.body, "BOTTOMLEFT", 0, 4)
detail.foot:SetWidth(INNER_W)
detail.foot:SetJustifyV("BOTTOM")
detail.foot:SetHeight(28)

-- cutoffs table: TIER, PLACES, LAST IN, RATING, FLOOR, TAKES NOW
local CUT_COLS = { { "TIER", 140 }, { "PLACES", 64 }, { "LAST IN", 72 }, { "RATING", 64 }, { "FLOOR", 64 },
    { "TAKES NOW", 72 } }
local cut = CreateFrame("Frame", nil, detail.body)
cut:SetAllPoints(detail.body)
cut.header = UI.Box(cut, INNER_W, 22, C.header)
cut.header:SetPoint("TOPLEFT", cut, "TOPLEFT", 0, 0)
local function cells(parent, size, color)
    local list, x = {}, 8
    for i, col in ipairs(CUT_COLS) do
        local t = UI.Text(parent, size, color, "body", i == 1 and "LEFT" or "RIGHT")
        t:SetPoint("LEFT", parent, "LEFT", x, 0)
        UI.OneLine(t, col[2] - 8)
        list[i] = t
        x = x + col[2]
    end
    return list
end
cut.header.cells = cells(cut.header, 10, C.dim)
for i, col in ipairs(CUT_COLS) do
    cut.header.cells[i]:SetText(col[1])
end
cut.rows = {}
for i = 1, 7 do
    local bg = i % 2 == 1 and C.zebra or C.panel
    local r = UI.Box(cut, INNER_W, 24, bg, bg)
    r.bg = bg
    r:SetPoint("TOPLEFT", cut.header, "BOTTOMLEFT", 0, -(i - 1) * 24)
    r.cells = cells(r, 12, C.text)
    cut.rows[i] = r
end
detail.cutoffs = cut

-- checklist and rewards: lines with a glyph
local function lineList(parent, n, height)
    local list = {}
    for i = 1, n do
        local l = CreateFrame("Frame", nil, parent)
        l:SetSize(INNER_W, height)
        l:SetPoint("TOPLEFT", parent, "TOPLEFT", 0, -(i - 1) * height)
        l:EnableMouse(true)
        l.icon = UI.Glyph(l, "check", 12, C.teal)
        l.icon:SetPoint("LEFT", l, "LEFT", 2, 0)
        l.label = UI.Text(l, 12, C.text)
        l.label:SetPoint("LEFT", l, "LEFT", 22, 0)
        UI.OneLine(l.label, 116)
        l.text = UI.Text(l, 12, C.text)
        l.text:SetPoint("LEFT", l, "LEFT", 22, 0)
        UI.OneLine(l.text, INNER_W - 26)
        l:SetScript("OnEnter", function(self)
            if self.tooltip then
                UI.ShowTooltip(self, self.tooltip())
            end
        end)
        l:SetScript("OnLeave", function()
            if GameTooltip then
                GameTooltip:Hide()
            end
        end)
        l:Hide()
        list[i] = l
    end
    return list
end
local check = CreateFrame("Frame", nil, detail.body)
check:SetAllPoints(detail.body)
check.lines = lineList(check, 9, 22)
detail.checklist = check
local rew = CreateFrame("Frame", nil, detail.body)
rew:SetAllPoints(detail.body)
rew.lines = lineList(rew, 7, 26)
detail.rewards = rew

------------------------------------------------------------------------------------------------------
-- Refresh
------------------------------------------------------------------------------------------------------
local function ago(epoch)
    if not epoch then
        return ""
    end
    local d = Comm.ServerTime() - epoch
    if d < 60 then
        return "just now"
    end
    return U.Duration(d) .. " ago"
end
AR.Ago = ago

local function finalOf(a, bracket)
    if a and (a.state == AR.STATE.FINAL or a.state == AR.STATE.DELIVERED) then
        return a.finals[bracket]
    end
    return nil
end
AR.FinalOf = finalOf

function P:RefreshHeader()
    local a = S.arena
    if a then
        UI.SetText(head.title, a.seasonName or (a.seasonId > 0 and ("Arena Season " .. a.seasonId)) or "Arena")
        head.state:SetValue(AR.STATE_TEXT[a.state] or "")
        UI.SetColor(head.state.text, AR.STATE_COLOR[a.state] or C.text)
        head.state:Show()
        head.clock:SetText(AR.Countdown(a))
    else
        head.title:SetText(Comm.ready and "Arena" or "Connecting to Bleakhold")
        head.state:Hide()
        head.clock:SetText(Comm.ready and "Waiting for your arena season..." or "")
    end
end

local function setCard(c, a)
    local bracket = c.bracket
    local b = a and a.brackets[bracket]
    local selected = P.bracket == bracket
    UI.Colors(c, selected and C.active or C.card, selected and C.gold or C.border)
    c.pvp:Hide()
    c.bar:Hide()
    c.tooltip = nil
    UI.SetColor(c.status, C.teal)
    if not b or not b.hasTeam then
        c.tier:SetText("")
        c.rating:SetText("-")
        c.rank:SetText("")
        c.record:SetText("")
        c.next:SetText("")
        c.status:SetText("")
        if bracket == 1 then
            c.team:SetText("No 1v1 team yet")
            if a and a.teamCost then
                c.rank:SetText("A rated 1v1 queue makes your team")
                c.record:SetText(a.teamCost > 0 and ("It costs " .. ns.RewardText("G", a.teamCost)) or "It is free")
            end
        else
            c.team:SetText(a and "No team" or "")
            if a then
                c.rank:SetText("Make one in the PvP window")
                c.pvp:Show()
            end
        end
        return
    end
    UI.SetText(c.team, b.team or (bracket == 1 and ns.PlayerName() or "Your team"))
    c.tier:SetText(b.tierId and AR.TierText(b.tierId) or "")
    c.rating:SetText(b.rating and tostring(b.rating) or "-")
    if b.rank then
        c.rank:SetText("Rank " .. b.rank .. (b.size and b.size > 0 and (" of " .. b.size) or ""))
    else
        c.rank:SetText("Not on the ladder yet")
    end
    local games, wins = b.games or 0, b.wins or 0
    local week = ""
    if b.weekGames then
        week = "  -  week " .. (b.weekWins or 0) .. "-" .. (b.weekGames - (b.weekWins or 0))
    end
    c.record:SetText(wins .. "-" .. max(0, games - wins) .. week)
    local final = finalOf(a, bracket)
    if final then
        c.next:SetText("Final #" .. (final.rank or "-") .. "  -  " .. AR.TierText(final.tierId))
        c.status:SetText(AR.GRANT_TEXT[final.grant] or "")
        UI.SetColor(c.status, AR.GRANT_COLOR[final.grant] or C.text)
    else
        local p = AR.NextBar(bracket, a)
        if p then
            c.bar:SetProgress(p)
            c.bar:SetStatusBarColor(UI.Rgb(AR.TierColor(b.nextTierId)))
            c.bar:Show()
        end
        c.next:SetText(AR.NextText(b))
        local missing = AR.MissingLines(bracket, b)
        if #missing > 0 then
            c.status:SetText(#missing == 1 and "1 thing keeps you from rewards"
                or (#missing .. " things keep you from rewards"))
            UI.SetColor(c.status, C.orange)
        elseif b.tierId then
            c.status:SetText("On pace for " .. U.Safe(AR.TierName(b.tierId)))
        else
            c.status:SetText("No tier yet")
            UI.SetColor(c.status, C.mute)
        end
    end
    c.tooltip = function()
        local lines = { AR.BracketName(bracket) .. (b.team and ("  -  " .. U.Safe(b.team)) or "") }
        if b.personal and bracket ~= 1 then
            lines[#lines + 1] = { "Personal rating " .. b.personal, C.mid }
        end
        if b.recent then
            lines[#lines + 1] = { b.recent .. " games in the last 21 days", C.mid }
        end
        for _, t in ipairs(AR.MissingLines(bracket, b)) do
            lines[#lines + 1] = { t, C.orange, true }
        end
        lines[#lines + 1] = { "Click for the details below", C.mute }
        return lines
    end
end

function P:RefreshQueue()
    local q = AR.Queue()
    local st = q and q.state or 0
    local a = S.arena
    local blockAny = AR.QueueBlock(false)
    local blockRated = AR.QueueBlock(true)
    queue.leave:Hide()
    queue.rated:Show()
    queue.skirmish:Show()
    if st == 1 or st == 2 then
        queue.status:SetText(q.tier == 1 and "In the rated 1v1 queue" or "In the 1v1 skirmish queue")
        UI.SetColor(queue.status, C.goldLight)
        queue.rated:Hide()
        queue.skirmish:Hide()
        queue.leave:Show()
        queue.leave:SetActive(true)
    elseif st == 3 then
        queue.status:SetText(q.tier == 1 and "In a rated 1v1 match" or "In a 1v1 skirmish")
        UI.SetColor(queue.status, C.teal)
        queue.rated:SetActive(false)
        queue.skirmish:SetActive(false)
    else
        queue.status:SetText("Not queued")
        UI.SetColor(queue.status, C.text)
        queue.rated:SetActive(blockRated == nil)
        queue.skirmish:SetActive(blockAny == nil)
    end
    local b1 = a and a.brackets[1]
    if st == 0 and a and a.teamCost and not (b1 and b1.hasTeam) then
        queue.detail:SetText(a.teamCost > 0 and ("Rated makes your 1v1 team for " .. ns.RewardText("G", a.teamCost))
            or "Rated makes your 1v1 team for free")
    elseif st == 0 then
        queue.detail:SetText("Skirmishes are open in every season state")
    end
    queue.blockText = st == 0 and blockRated or nil
    P:Tick()
end

-- The server's refusal (already safe text) while it is fresh, else the client's own reason.
function P:RefreshNotice()
    queue.notice:SetText(AR.ErrorNotice() or queue.blockText or "")
end

function P:RefreshMatches()
    local a = S.arena
    local list = a and a.matches or {}
    for i, r in ipairs(matches.rows) do
        local m = list[i]
        if m then
            local wl = m.won and U.Color(C.teal, "W") or U.Color(C.red, "L")
            r.left:SetText(wl .. "  " .. AR.Signed(m.change) .. "  " .. U.Safe(m.opponent or "?"))
            local short, sentence, color = AR.Verdict(m)
            if short then
                r.right:SetText(short)
                UI.SetColor(r.right, color)
            else
                r.right:SetText(AR.BracketName(m.bracket) .. "  -  " .. ago(m.endEpoch))
                UI.SetColor(r.right, C.dim)
            end
            r.tooltip = function()
                local lines = { (m.won and "Won" or "Lost") .. " against " .. U.Safe(m.opponent or "?"),
                    { AR.BracketName(m.bracket) .. "  -  rating " .. AR.Signed(m.change) .. "  -  " .. ago(m.endEpoch),
                        C.mid } }
                if sentence then
                    lines[#lines + 1] = { sentence, color, true }
                    if m.verdict == 2 then
                        lines[#lines + 1] = { "The winners got no rating, no win and no game; the losers lost as usual.",
                            C.mute, true }
                    end
                end
                return lines
            end
            r:Show()
        else
            r:Hide()
        end
    end
    if #list == 0 then
        matches.empty:SetText(a and "No rated match this season yet." or "")
        matches.empty:Show()
    else
        matches.empty:Hide()
    end
end

local function showLines(lines, items)
    for i, l in ipairs(lines) do
        local it = items[i]
        if it then
            l.label:SetText(it.label or "")
            l.text:ClearAllPoints()
            l.text:SetPoint("LEFT", l, "LEFT", it.label and 140 or 22, 0)
            UI.OneLine(l.text, INNER_W - (it.label and 144 or 26))
            l.text:SetText(it.text or "")
            UI.SetColor(l.text, it.color or C.text)
            if it.glyph then
                UI.SetGlyph(l.icon, it.glyph)
                l.icon:SetVertexColor(UI.Rgb(it.glyphColor or C.teal))
                l.icon:Show()
            else
                l.icon:Hide()
            end
            l.tooltip = it.tooltip
            l:Show()
        else
            l.tooltip = nil
            l:Hide()
        end
    end
end

function P:RefreshCutoffs(a, bracket)
    local list = AR.Cutoffs(bracket, a)
    local b = a and a.brackets[bracket]
    for i, r in ipairs(cut.rows) do
        local c = list[i]
        if c then
            local mine = b and b.hasTeam and b.tierId == c.tierId
            UI.Colors(r, mine and C.active or r.bg, mine and C.gold or r.bg)
            r.cells[1]:SetText(AR.TierText(c.tierId))
            r.cells[2]:SetText(tostring(c.slots or 0))
            r.cells[3]:SetText(c.cutRank and ("#" .. c.cutRank) or "-")
            r.cells[4]:SetText(c.cutRating and tostring(c.cutRating) or "-")
            r.cells[5]:SetText(tostring(c.floor or 0))
            r.cells[6]:SetText(U.Color(C.goldLight, tostring(AR.Takes(c))))
            r:Show()
        else
            r:Hide()
        end
    end
    local n = a and a.ladders[bracket]
    local foot = {}
    if n then
        foot[#foot + 1] = n.eligible .. (n.eligible == 1 and " team counts" or " teams count") .. " for rewards"
        if not n.rewardsOpen then
            foot[#foot + 1] = "too few for more than Combatant"
        elseif not n.titlesOpen then
            foot[#foot + 1] = "too few for titles"
        end
    end
    detail.foot:SetText(#foot > 0 and (table.concat(foot, "  -  ") .. ". A tier takes the higher of the last team "
        .. "inside it and its floor.") or "")
    if #list == 0 then
        detail.empty:SetText(a and ("No cutoffs for " .. AR.BracketName(bracket) .. " yet.")
            or "Waiting for your arena season...")
        detail.empty:Show()
        cut.header:Hide()
    else
        detail.empty:Hide()
        cut.header:Show()
    end
end

function P:RefreshChecklist(a, bracket)
    local b = a and a.brackets[bracket]
    local items = {}
    for _, line in ipairs(AR.Checklist(bracket, b)) do
        items[#items + 1] = { text = line.text, glyph = line.ok and "check" or "close",
            glyphColor = line.ok and C.teal or C.red, color = line.ok and C.text or C.orange }
    end
    local final = finalOf(a, bracket)
    if final then
        items[#items + 1] = { text = "Final standing: #" .. (final.rank or "-") .. "  -  " .. (final.rating or "-")
            .. "  -  " .. AR.TierText(final.tierId) .. "  -  " .. U.Color(AR.GRANT_COLOR[final.grant] or C.text,
            AR.GRANT_TEXT[final.grant] or ""), glyph = "trophy", glyphColor = C.goldLight }
    end
    showLines(check.lines, items)
    if #items == 0 then
        if not a then
            detail.empty:SetText("Waiting for your arena season...")
        elseif bracket == 1 then
            detail.empty:SetText("You have no 1v1 team yet: queue for rated 1v1 to make one.")
        else
            detail.empty:SetText("You have no " .. AR.BracketName(bracket) .. " team. Make one in the game's PvP window.")
        end
        detail.empty:Show()
    else
        detail.empty:Hide()
    end
    detail.foot:SetText(b and b.hasTeam and "These decide your season rewards. Your place on the ladder stays either way."
        or "")
end

function P:RefreshRewards(a, bracket)
    local seasonId = a and a.seasonId or 0
    local tiers = AR.Rewards(bracket, seasonId)
    local b = a and a.brackets[bracket]
    local items = {}
    for _, t in ipairs(tiers) do
        local parts, lines, ownedAny = {}, {}, false
        for _, q in ipairs(t.rows) do
            local text, owned = AR.RewardLine(q)
            parts[#parts + 1] = text
            if owned then
                ownedAny = true
                lines[#lines + 1] = { text .. " - you have it: 200 Dungeon Shards instead", C.mute, true }
            else
                lines[#lines + 1] = { text, C.text, true }
            end
        end
        local tierId = t.tierId
        items[#items + 1] = {
            label = AR.TierText(tierId), text = table.concat(parts, ", "),
            color = ownedAny and C.mid or C.text,
            glyph = (b and b.hasTeam and b.tierId == tierId) and "reward" or nil, glyphColor = C.goldLight,
            tooltip = function()
                local out = { U.Safe(AR.TierName(tierId)) }
                local d = ns.Def("V", tierId)
                if d and d.text then
                    out[#out + 1] = { U.Safe(d.text), C.dim, true }
                end
                for _, l in ipairs(lines) do
                    out[#out + 1] = l
                end
                return out
            end,
        }
    end
    showLines(rew.lines, items)
    local foot = "Each tier also gets the rewards of the tiers below it. What you already have pays 200 Dungeon "
        .. "Shards instead."
    local n = a and a.ladders[bracket]
    if n and not n.titlesOpen then
        foot = "Too few teams for titles this season: a title pays 200 Dungeon Shards instead. " .. foot
    end
    local final = finalOf(a, bracket)
    if final then
        foot = "Final: " .. AR.TierText(final.tierId) .. "  -  " .. (AR.GRANT_TEXT[final.grant] or "") .. ". " .. foot
    end
    detail.foot:SetText(#items > 0 and foot or "")
    if #items == 0 then
        detail.empty:SetText("The season's rewards for " .. AR.BracketName(bracket) .. " show once the server lists them.")
        detail.empty:Show()
    else
        detail.empty:Hide()
    end
end

function P:RefreshDetail()
    local a = S.arena
    local bracket = P.bracket
    for _, b in ipairs(detail.brackets) do
        b:SetStyle(b.bracket == bracket and "tabOn" or "tab")
    end
    for _, b in ipairs(detail.views) do
        b:SetStyle(b.view == P.view and "tabOn" or "tab")
    end
    cut:Hide()
    check:Hide()
    rew:Hide()
    if P.view == "checklist" then
        check:Show()
        P:RefreshChecklist(a, bracket)
    elseif P.view == "rewards" then
        rew:Show()
        P:RefreshRewards(a, bracket)
    else
        cut:Show()
        P:RefreshCutoffs(a, bracket)
    end
end

function P:Refresh()
    if not AR.Live() then
        return
    end
    local a = S.arena
    P:RefreshHeader()
    for _, c in ipairs(P.cards) do
        setCard(c, a)
    end
    P:RefreshQueue()
    P:RefreshMatches()
    P:RefreshDetail()
end

-- Every second from Activities: the clocks, the queue time, and GET ARENA again after 30 s.
function P:Tick()
    if S.arena then
        head.clock:SetText(AR.Countdown(S.arena))
    end
    P:RefreshNotice()
    local q = AR.Queue()
    if q and (q.state == 1 or q.state == 2) then
        local since = GetTime() - (q.recvAt or GetTime())
        local txt = "Waiting " .. U.Clock((q.queuedSec or 0) + since)
        if q.estWaitSec then
            txt = txt .. "  -  usually " .. U.Clock(q.estWaitSec)
        end
        queue.detail:SetText(txt)
    elseif q and q.state == 3 then
        queue.detail:SetText("The game's own dialog takes you in and out")
    end
    if P:IsVisible() then
        AR.Ask(false)
    end
end

function P:OnOpen()
    local saved = ns.cdb.arenaBracket
    if saved == 1 or saved == 2 or saved == 3 or saved == 5 then
        P.bracket = saved
    end
    AR.Ask(false)
    Comm.Get("QUEUE")
end

ns.On("STATE", function(topic)
    if (topic == "ARENA" or topic == "QUEUE" or topic == "DEF" or topic == "LB") and P:IsVisible() then
        P:Refresh()
    end
end)

------------------------------------------------------------------------------------------------------
-- The match toast: a new match in ARENA M (after the first ARENA of the session) shows the change, the rating, the
-- place and the tier pace; a tier change of a bracket gets its own line.
------------------------------------------------------------------------------------------------------
local function matchKey(m)
    return m and table.concat({ m.bracket, m.endEpoch or 0, m.opponent or "", m.change or 0 }, ":") or nil
end

local lastSeen

ns.On("STATE", function(topic)
    if topic ~= "ARENA" then
        return
    end
    local a = S.arena
    if not a then
        lastSeen = nil
        return
    end
    local m = a.matches[1]
    local key = matchKey(m)
    local before = lastSeen
    lastSeen = { key = key, tiers = {} }
    for _, br in ipairs(AR.BRACKETS) do
        local b = a.brackets[br]
        lastSeen.tiers[br] = b and b.hasTeam and b.tierId or false
    end
    lastSeen.seasonId = a.seasonId
    if not before or not m or key == before.key or before.seasonId ~= a.seasonId then
        return
    end
    local b = a.brackets[m.bracket]
    local parts = { AR.Signed(m.change) }
    if b and b.rating then parts[#parts + 1] = tostring(b.rating) end
    if b and b.rank then parts[#parts + 1] = "Rank " .. b.rank end
    if b and b.tierId then parts[#parts + 1] = U.Safe(AR.TierName(b.tierId)) .. " pace" end
    local short = AR.Verdict(m)
    local title = (m.won and "Won" or "Lost") .. " " .. AR.BracketName(m.bracket) .. " against "
        .. U.Safe(m.opponent or "?")
    local sub = table.concat(parts, "  -  ")
    if short then
        sub = short .. "  -  " .. sub
    end
    local oldTier = before.tiers[m.bracket]
    if b and b.tierId and oldTier ~= nil and oldTier ~= false and oldTier ~= b.tierId then
        sub = sub .. "  -  " .. (b.tierId > oldTier and "up to " or "down to ") .. U.Safe(AR.TierName(b.tierId))
    end
    if ns.Toast then
        ns.Toast.Push({ kicker = "ARENA", title = title, sub = sub, target = "arena" })
    end
end)

------------------------------------------------------------------------------------------------------
-- Opening: /bh arena, the TOAST target `arena`
------------------------------------------------------------------------------------------------------
local function openPage(toggle)
    if not AR.Live() then
        notice(Comm.ready and "Arena seasons are not running on this realm." or "Not connected to the realm.")
        return
    end
    if toggle and A.frame:IsShown() and A.current == "arena" then
        A.frame:Hide()
        return
    end
    A.Show("arena")
end
AR.OpenPage = openPage
UI.RegisterOpener("arena", openPage)

ns.AddCommand("arena", "arena seasons: /bh arena [lb|rated|skirmish|leave]", function(args)
    local a = (args or ""):lower():match("^(%S*)")
    if a == "lb" then
        UI.Open("leaderboards-arena")
    elseif a == "rated" or a == "skirmish" then
        AR.Join(a == "rated")
    elseif a == "leave" then
        AR.Leave()
    else
        openPage(false)
    end
end)

-- After HELLO: the page and the nav follow feature bit 65536 (Activities.lua).
ns.On("HELLO", function()
    if not AR.Live() then
        AR.askedAt = nil
        lastSeen = nil
        return
    end
    -- the server pushes ARENA after HELLO and State.lua asks for it too: the next GET only if neither comes
    AR.askedAt = GetTime()
    if P:IsVisible() then
        P:Refresh()
    end
end)

------------------------------------------------------------------------------------------------------
-- /bh demo: an arena season (Demo.lua routes GET ARENA, LBQ A, QJOIN A and QLEAVE here)
------------------------------------------------------------------------------------------------------
local demo

local function demoPush(op, records, maxBody)
    if ns.Demo then
        ns.Demo.Push(op, records, maxBody)
    end
end

local DEMO_NAMES = { "Brenna", "Corwin", "Dalia", "Eamon", "Fenna", "Garrick", "Hesper", "Ivo", "Jessa", "Korrin" }
local DEMO_CLASSES = { 2, 5, 8, 11, 3, 4, 6, 7, 9, 1 }
local DEMO_TEAMS = { "Dawnbreakers", "The Unbowed", "Ashen Pact", "Ironvow Wardens", "Grey Lanterns", "Thornwatch",
    "Last Light", "Night Harriers", "Cinder Oath", "Stonebound" }

local function demoDefs()
    demoPush("DEF", { { "V", 0 }, { 1, "Combatant", "9D9D9D", "Enough season games and 1300 rating." },
        { 2, "Challenger", "1EFF00", "The top 35% of the ladder with 1500 rating." },
        { 3, "Rival", "0070DD", "The top 10% of the ladder with 1650 rating." },
        { 4, "Duelist", "A335EE", "The top 3% of the ladder with 1800 rating and 10 recent games." },
        { 5, "Gladiator", "FF8000", "The top 0.5% of the ladder with 50 wins." },
        { 6, "Rank One", "E6CC80", "The first team of the ladder." },
        { 7, "Class Champion", "3FC7EB", "1v1 only: the best player of each class." } })
    local q = { { "Q", 0 } }
    local id = 100
    for _, br in ipairs(AR.BRACKETS) do
        local function add(season, tier, kind, entry, count, text)
            id = id + 1
            q[#q + 1] = { id, season, br, tier, kind, entry, count, text }
        end
        add(0, 1, "C", 0, 150, "150 Dungeon Shards")
        add(0, 1, "H", 0, 2000, "2,000 honor")
        add(0, 2, "C", 0, 300, "300 Dungeon Shards")
        add(0, 3, "C", 0, 500, "500 Dungeon Shards")
        add(0, 4, "C", 0, 800, "800 Dungeon Shards")
        add(0, 5, "C", 0, 1200, "1,200 Dungeon Shards")
        add(0, 6, "F", 0, 1, "A server first")
        if br ~= 1 then
            add(0, 2, "T", 2090, 1, "Challenger")
            add(0, 3, "T", 2093, 1, "Rival")
            add(0, 4, "T", 2092, 1, "Duelist")
            add(1, 5, "T", 2091, 1, "Gladiator")
            add(1, 5, "M", 30609, 1, "Swift Nether Drake")
            add(1, 2, "X", 11, 1, "Gladiator armor looks")
        end
    end
    demoPush("DEF", q, 400)
end

local function demoArena()
    local now = time()
    local d = demo
    local recs = { { 1, d.state, now - 30 * 86400, now + 54 * 86400, now + 56 * 86400, d.state <= 2 and 1 or 0, 100000,
        "Arena Season 1" },
        { "S", 1, "Arena Season 1", 1, now - 30 * 86400, now + 54 * 86400 },
        { "S", 2, "Arena Season 2", 2, now + 56 * 86400, now + 140 * 86400 } }
    if d.oneTeam then
        recs[#recs + 1] = { "B", 1, 1, d.rating, 12, 48, d.games, d.wins, 9, 6, d.rating, 14, 3, 4, 1800 - d.rating, 0,
            ns.PlayerName() or "You" }
    else
        recs[#recs + 1] = { "B", 1, 0 }
    end
    recs[#recs + 1] = { "B", 3, 1, 1912, 4, 22, 44, 30, 12, 8, 1890, 12, 4, 5, 163, 16, "Ironvow Wardens" }
    for _, t in ipairs({ { 1, 6, 1, 1, 2140, 2000 }, { 1, 5, 3, 3, 2010, 1950 }, { 1, 4, 6, 6, 1801, 1800 },
        { 1, 3, 5, 5, 1702, 1650 }, { 1, 2, 17, 17, 1540, 1500 }, { 1, 1, 48, 48, 1310, 1300 },
        { 3, 6, 1, 1, 2140, 2000 }, { 3, 5, 2, 2, 2075, 2000 }, { 3, 4, 4, 4, 1912, 1800 }, { 3, 3, 4, 4, 1912, 1650 },
        { 3, 2, 8, 8, 1702, 1500 }, { 3, 1, 22, 22, 1310, 1300 } }) do
        recs[#recs + 1] = { "T", t[1], t[2], t[3], t[4], t[5], t[6] }
    end
    recs[#recs + 1] = { "N", 1, 48, 1, 1 }
    recs[#recs + 1] = { "N", 3, 22, 1, 1 }
    for i = 1, min(5, #d.matches) do
        local m = d.matches[i]
        recs[#recs + 1] = { "M", m[1], m[2], m[3], m[4], m[5], m[6], m[7] or "" }
    end
    demoPush("ARENA", recs, 300)
end

local function demoQueue(state, tier, queued)
    demo.rev = demo.rev + 1
    demoPush("QUEUE", { { 50000 + demo.rev, state, "A", 1, tier or 0, 1, queued or 0, state == 1 and 95 or "" } })
end

local function demoStart()
    local now = time()
    demo = { state = 1, oneTeam = false, rating = 1734, games = 61, wins = 38, rev = 0, run = 0, matches = {
        { 3, 1, 14, "Brenna", now - 3600, 0, "" }, { 3, 0, -11, "Corwin", now - 4000, 0, "" },
        { 3, 1, 0, "Dalia", now - 5000, 2, "I" }, { 3, 1, 7, "Eamon", now - 6000, 1, "R" } } }
    demoDefs()
end

local function demoAfter(sec, fn)
    local run = demo and demo.run
    ns.After(sec, function()
        if Comm.demo and demo and demo.run == run then
            fn()
        end
    end)
end

local function demoLB(seasonId, bracket, classId, page)
    page = page or 1
    local now = time()
    local recs = { { "A", seasonId or 0, bracket, classId or 0, page, 2 } }
    for i = 1, 10 do
        local rank = (page - 1) * 10 + i
        local members, label = {}, nil
        for k = 1, bracket do
            local n = (rank + k - 2) % #DEMO_NAMES + 1
            members[k] = { DEMO_NAMES[n], DEMO_CLASSES[n] }
        end
        if bracket == 1 then
            label = DEMO_NAMES[(rank - 1) % #DEMO_NAMES + 1]
        else
            label = DEMO_TEAMS[(rank - 1) % #DEMO_TEAMS + 1]
        end
        local rating = max(1300, 2140 - (rank - 1) * 38)
        local tier = rank == 1 and 6 or (rank <= 3 and 5 or (rank <= 6 and 4 or (rank <= 12 and 3 or 2)))
        local flags = (rank == 9 and 1 or 0) + (rank == 14 and 2 or 0) + ((seasonId or 0) > 0 and 4 or 0)
        recs[#recs + 1] = { rank, bracket, rating, "", now - rank * 5400 - (rank == 9 and 8 * 86400 or 0), members, label,
            70 - rank * 2, 90 - rank, tier, flags }
    end
    demoPush("LB", recs, 300)
    if bracket == 3 then
        demoPush("LBME", { { "A", 4, 19, 1912, 3, "", 407, "Duelist", 182, 4 } })
    elseif bracket == 1 and demo.oneTeam then
        demoPush("LBME", { { "A", 12, 25, demo.rating, 1, "", 520, "Rival", 250, 3 } })
    else
        demoPush("LBME", { { "A" } })
    end
end

local function demoMatch(tier)
    demoQueue(3, tier)
    demoAfter(5, function()
        demoQueue(0)
        if tier == 1 then
            demo.oneTeam = true
            demo.rating = demo.rating + 14
            demo.games, demo.wins = demo.games + 1, demo.wins + 1
            table.insert(demo.matches, 1, { 1, 1, 14, "Garrick", time(), 0, "" })
            demoArena()
        end
    end)
end

-- Returns true when the intent was the arena demo's (and is answered here).
function AR.DemoRespond(op, recs)
    local f = recs[1] or {}
    if op == "HELLO" then
        -- like the server: ARENA follows HELLO while bit 65536 is on
        demoStart()
        local run = demo.run
        ns.After(0.2, function()
            if Comm.demo and demo and demo.run == run then
                demoArena()
            end
        end)
        return false
    end
    if not demo then
        demoStart()
    end
    if op == "GET" then
        for _, r in ipairs(recs) do
            if r[1] == "ARENA" then
                demoArena()
            end
        end
        return false
    elseif op == "LBQ" and f[1] == "A" then
        demoLB(tonumber(f[2]), tonumber(f[3]) or 3, tonumber(f[4]), tonumber(f[5]))
        return true
    elseif op == "QJOIN" and f[1] == "A" then
        demo.run = demo.run + 1
        local tier = tonumber(f[3]) or 0
        demoQueue(1, tier)
        demoPush("TOAST", { { "Q", tier == 1 and "Rated 1v1" or "1v1 skirmish", "You joined the queue", "arena" } })
        demoAfter(4, function()
            demoMatch(tier)
        end)
        return true
    elseif op == "QLEAVE" then
        local q = AR.Queue()
        if q and q.state ~= 0 then
            demo.run = demo.run + 1
            demoQueue(0)
            return true
        end
    end
    return false
end
