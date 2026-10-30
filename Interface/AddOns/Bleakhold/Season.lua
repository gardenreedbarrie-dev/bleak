-- Bleakhold: Season window. Server War Effort (a bar of 20 segments, the goals, your part and rank, hand-in), the
-- season rewards track and the seasons timeline. The hand-in is an intent (WEHANDIN): the server counts the tokens
-- and the points. Stock 3.3.5a look: tooltip panels, the segments as small UI-StatusBar bars, the goals and the
-- rewards track as the achievement progress bar, rewards as ring portraits with the check when earned, the seasons
-- as radio buttons.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S

local floor, max = math.floor, math.max

local SE = {}
ns.Season = SE

SE.W, SE.H = 900, 600

local win = UI.Window("BleakholdSeasonFrame", SE.W, SE.H, "Season", "banner")
SE.frame = win

local WCW, WCH = UI.ContentSize(SE.W, SE.H)
local CW = WCW - 16
local content = CreateFrame("Frame", nil, win.content)
content:SetPoint("TOPLEFT", win.content, "TOPLEFT", 8, -6)
content:SetSize(CW, WCH - 14)

------------------------------------------------------------------------------------------------------
-- War effort: the old window's page anatomy in a tooltip panel (a gold label and title, a white description,
-- the share as a gold stat label with its white value on the right), the bar of 20 segments, the three goals
-- as achievement progress bars, and your part
------------------------------------------------------------------------------------------------------
local PAD = 16
local we = UI.Box(content, CW, 290, C.panel, C.border, nil, "panel")
we:SetPoint("TOPLEFT", content, "TOPLEFT", 0, 0)
we.label = UI.Label(we, "Server War Effort")
we.label:SetPoint("TOPLEFT", we, "TOPLEFT", PAD + 4, -16)
we.title = UI.Text(we, 22, C.gold)
we.title:SetPoint("TOPLEFT", we.label, "BOTTOMLEFT", 0, -4)
UI.OneLine(we.title, CW - 260)
we.text = UI.Para(we, 12, C.text, CW - 260)
we.text:SetPoint("TOPLEFT", we.title, "BOTTOMLEFT", 0, -4)
we.pctLabel = UI.Label(we, "War Effort")
we.pctLabel:SetJustifyH("RIGHT")
we.pctLabel:SetPoint("TOPRIGHT", we, "TOPRIGHT", -PAD - 4, -16)
we.pct = UI.Text(we, 24, C.text, "body", "RIGHT")
we.pct:SetFont(UI.FONT_BODY, 24, "OUTLINE")
we.pct:SetPoint("TOPRIGHT", we.pctLabel, "BOTTOMRIGHT", 0, -4)
we.helpers = UI.Text(we, 11, C.dim, "body", "RIGHT")
we.helpers:SetPoint("TOPRIGHT", we.pct, "BOTTOMRIGHT", 0, -4)

-- One segment of the war effort: a small status bar (TargetingFrame\UI-StatusBar in the cast bar's gold on black,
-- in the old rows' 1 px edge), full, partly filled or empty.
local function segment(parent, w, h)
    local s = CreateFrame("StatusBar", nil, parent)
    s:SetSize(w, h)
    s:SetStatusBarTexture(UI.STOCK.statusBar)
    s:SetStatusBarColor(UI.Rgb(UI.BAR_GOLD))
    s:SetMinMaxValues(0, 1)
    s:SetValue(0)
    s.bg = s:CreateTexture(nil, "BACKGROUND")
    s.bg:SetTexture(0, 0, 0, 0.6)
    s.bg:SetAllPoints(s)
    s.edge = CreateFrame("Frame", nil, s)
    s.edge:SetPoint("TOPLEFT", s, "TOPLEFT", -1, 1)
    s.edge:SetPoint("BOTTOMRIGHT", s, "BOTTOMRIGHT", 1, -1)
    s.edge:SetBackdrop({ edgeFile = UI.STOCK.white, edgeSize = 1 })
    s.edge:SetBackdropBorderColor(UI.Rgb(UI.ROW_EDGE))
    return s
end

local SEGS, SEG_GAP = 20, 5
local segW = floor((CW - 2 * PAD - 8 - (SEGS - 1) * SEG_GAP) / SEGS)
local segX = floor((CW - (SEGS * segW + (SEGS - 1) * SEG_GAP)) / 2)
we.segments = {}
for i = 1, SEGS do
    local s = segment(we, segW, 14)
    s:SetPoint("TOPLEFT", we, "TOPLEFT", segX + (i - 1) * (segW + SEG_GAP), -100)
    we.segments[i] = s
end

local partW = floor((CW - 2 * PAD - 8 - 24) / 3)
we.parts = {}
for i = 1, 3 do
    local p = UI.Box(we, partW, 60, C.card, C.border, nil, "edge")
    p:SetPoint("TOPLEFT", we, "TOPLEFT", PAD + 4 + (i - 1) * (partW + 12), -130)
    p.name = UI.Text(p, 12, C.gold)
    p.name:SetPoint("TOPLEFT", p, "TOPLEFT", 12, -10)
    UI.OneLine(p.name, partW - 24)
    -- the goal as the achievement frame's progress bar, its share inside ("80%")
    p.bar = UI.Bar(p, partW - 34, 14)
    p.bar:SetPoint("TOPLEFT", p, "TOPLEFT", 17, -34)
    we.parts[i] = p
end

local mine = UI.Box(we, CW - 2 * PAD - 8, 64, C.card, C.border, nil, "edge")
mine:SetPoint("TOPLEFT", we, "TOPLEFT", PAD + 4, -204)
mine.badge = UI.Badge(mine, 44, "shield", C.active, C.gold)
mine.badge:SetPoint("LEFT", mine, "LEFT", 10, 0)
mine.points = UI.Text(mine, 14, C.text)
mine.points:SetPoint("TOPLEFT", mine, "TOPLEFT", 66, -14)
mine.rank = UI.Text(mine, 12, C.dim)
mine.rank:SetPoint("TOPLEFT", mine.points, "BOTTOMLEFT", 0, -5)
mine.handin = UI.Button(mine, 170, 22, "Hand in spare tokens", "gold", 12)
mine.handin:SetPoint("RIGHT", mine, "RIGHT", -14, 0)
mine.handin:SetScript("OnClick", function()
    local s = S.season
    local text = "Hand in your spare war effort tokens?"
    if s and s.tokens then
        text = "Hand in " .. s.tokens .. " spare war effort " .. (s.tokens == 1 and "token" or "tokens") .. "?"
    end
    UI.Confirm(text, function()
        Comm.Send("WEHANDIN")
    end, "Hand in")
end)
we.mine = mine
SE.we = we

------------------------------------------------------------------------------------------------------
-- Rewards track and timeline
------------------------------------------------------------------------------------------------------
local TL_W = 316
local trackW = CW - TL_W - 12
local LOWER_H = WCH - 14 - 290 - 10
local track = UI.Box(content, trackW, LOWER_H, C.panel, C.border, nil, "panel")
track:SetPoint("TOPLEFT", we, "BOTTOMLEFT", 0, -10)
track.title = UI.Heading(track, "Season Rewards")
track.title:SetPoint("TOPLEFT", track, "TOPLEFT", PAD + 4, -16)
-- each reward in a column of its own (its text never runs into the next); the achievement progress bar runs from
-- the first ring to the last and fills up to the last reward earned
local NODES = 4
local colW = floor((trackW - 2 * PAD) / NODES)
local function nodeX(i)
    return PAD + colW * (i - 0.5)
end
local RING, RING_Y = 52, -50
track.bar = UI.Bar(track, nodeX(NODES) - nodeX(1), 14)
track.bar:SetPoint("TOPLEFT", track, "TOPLEFT", nodeX(1), RING_Y - RING / 2 + 7)
track.fill = track.bar
track.nodes = {}
for i = 1, NODES do
    local n = CreateFrame("Frame", nil, track)
    n:SetSize(colW, LOWER_H + RING_Y - 8)
    n:SetPoint("TOP", track, "TOPLEFT", nodeX(i), RING_Y)
    n:SetFrameLevel(track.bar:GetFrameLevel() + 3)
    n.dot = UI.Badge(n, RING, "check", C.panel, C.gold)
    n.dot:SetPoint("TOP", n, "TOP", 0, 0)
    -- earned: the stock check on the ring; not yet: the picture greyed
    n.check = UI.Check(UI.Marks(n.dot), 20)
    n.check:SetPoint("TOPRIGHT", n.dot, "TOPRIGHT", 2, 2)
    n.check:Hide()
    n.name = UI.Text(n, 13, C.text, "body", "CENTER")
    n.name:SetPoint("TOP", n.dot, "BOTTOM", 0, -6)
    UI.OneLine(n.name, colW - 6)
    n.need = UI.Text(n, 11, C.dim, "body", "CENTER")
    n.need:SetPoint("TOP", n.name, "BOTTOM", 0, -3)
    n.need:SetWidth(colW - 8)
    n.state = UI.Text(n, 11, C.dim, "body", "CENTER")
    n.state:SetPoint("TOP", n.need, "BOTTOM", 0, -4)
    track.nodes[i] = n
end
SE.track = track

local tl = UI.Box(content, TL_W, LOWER_H, C.panel, C.border, nil, "panel")
tl:SetPoint("TOPRIGHT", we, "BOTTOMRIGHT", 0, -10)
tl.title = UI.Heading(tl, "The Seasons")
tl.title:SetPoint("TOPLEFT", tl, "TOPLEFT", PAD + 4, -16)
tl.rows = {}
for i = 1, 5 do
    local r = CreateFrame("Frame", nil, tl)
    r:SetSize(TL_W - 2 * PAD - 8, 34)
    r:SetPoint("TOPLEFT", tl, "TOPLEFT", PAD + 4, -44 - (i - 1) * 36)
    -- the current season is the checked radio button, the others unchecked
    r.radio = UI.Radio(r, 16)
    r.radio:SetPoint("TOPLEFT", r, "TOPLEFT", 0, -1)
    r.name = UI.Text(r, 13, C.text)
    r.name:SetPoint("TOPLEFT", r, "TOPLEFT", 22, 0)
    UI.OneLine(r.name, TL_W - 2 * PAD - 30)
    r.text = UI.Text(r, 11, C.dim)
    r.text:SetPoint("TOPLEFT", r.name, "BOTTOMLEFT", 0, -2)
    UI.OneLine(r.text, TL_W - 2 * PAD - 30)
    tl.rows[i] = r
end
SE.timeline = tl

------------------------------------------------------------------------------------------------------
-- Refresh
------------------------------------------------------------------------------------------------------
function SE.Refresh()
    if not win:IsShown() then
        return
    end
    local s = S.season
    local seasonId = (s and s.seasonId) or Comm.server.seasonId
    local seasonName = ns.DefName("S", seasonId, nil)
    UI.SetText(win.title, seasonName or "Season")

    if s then
        UI.SetText(we.title, s.title or "War Effort")
        UI.SetText(we.text, s.text or "")
        we.pct:SetText(floor(s.wePermille / 10) .. "%")
        we.helpers:SetText(U.Commas(s.contributors) .. (s.contributors == 1 and " player has helped" or " players have helped"))
    else
        we.title:SetText(Comm.ready and "No war effort right now" or "Waiting for the server")
        we.text:SetText("")
        we.pct:SetText("-")
        we.helpers:SetText("")
    end
    -- 62% fills twelve segments and two fifths of the thirteenth
    local filled = (s and s.wePermille or 0) / 1000 * SEGS
    for i, seg in ipairs(we.segments) do
        seg:SetValue(U.Clamp(filled - (i - 1), 0, 1))
    end
    for i, p in ipairs(we.parts) do
        local part = s and s.parts[i]
        if part then
            p.bar:SetProgress(part.permille / 1000, floor(part.permille / 10) .. "%")
            UI.SetText(p.name, part.name)
            p:Show()
        else
            p:Hide()
        end
    end
    if s then
        we.mine.points:SetText("Your part: " .. U.Color(C.goldLight, U.Commas(s.points) .. " points"))
        local rank = s.rankId and ns.DefName("K", s.rankId)
        local nextRank = s.nextRankId and ns.DefName("K", s.nextRankId)
        local txt = rank and ("Rank: " .. rank) or ""
        if s.nextRankPoints and nextRank then
            txt = txt .. (txt ~= "" and "  -  " or "") .. U.Commas(s.nextRankPoints) .. " points to " .. nextRank
        end
        UI.SetText(we.mine.rank, txt)
        we.mine.handin:SetActive(s.tokens == nil or s.tokens > 0)
    else
        we.mine.points:SetText("Your part: -")
        we.mine.rank:SetText("")
        we.mine.handin:SetActive(false)
    end

    -- rewards track: server records first, built-in reward names when the server sends none
    local rewards = (s and #s.rewards > 0) and s.rewards or {}
    local lastEarned = 0
    for i, n in ipairs(track.nodes) do
        local r = rewards[i]
        local def = r and ns.Def("W", r.id) or ns.Def("W", i)
        if def or r then
            UI.SetText(n.name, def and def.name or ("Reward " .. i))
            UI.SetText(n.need, def and def.need or "")
            local earned = r and r.earned
            if earned then
                lastEarned = i
            end
            UI.SetText(n.state, (r and r.stateText) or (earned and "Complete" or ""))
            UI.SetColor(n.state, earned and C.teal or C.dim)
            UI.SetGlyph(n.dot.glyph, ({ "check", "shirt", "mount", "banner" })[i] or "reward")
            n.dot:SetLocked(not earned)
            if earned then
                n.check:Show()
            else
                n.check:Hide()
            end
            n:Show()
        else
            n:Hide()
        end
    end
    track.bar:SetProgress(max(0, lastEarned - 1) / (NODES - 1))

    -- timeline
    local ids = ns.DefIds("S")
    for i, r in ipairs(tl.rows) do
        local id = ids[i]
        local d = id and ns.Def("S", id)
        if d then
            local now = (id == seasonId) or (seasonId == nil and d.state == 1)
            UI.SetText(r.name, (d.name or ("Season " .. id)) .. (now and " (now)" or ""))
            UI.SetColor(r.name, now and C.goldPale or C.text)
            UI.SetText(r.text, d.text or "")
            r.radio:SetChecked(now)
            r:Show()
        else
            r:Hide()
        end
    end
end

function win:OnOpen()
    Comm.Refresh("SEASON")
    SE.Refresh()
end

ns.On("STATE", function(topic)
    if topic == "SEASON" or topic == "DEF" then
        SE.Refresh()
    end
end)

UI.RegisterOpener("season", function(toggle)
    if toggle and win:IsShown() then
        win:Hide()
    else
        win:Show()
    end
end)
ns.AddCommand("season", "open the Season window", function() UI.Open("season", true) end)
