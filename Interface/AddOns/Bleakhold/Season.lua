-- Bleakhold: Season window. Server War Effort (progress bar of 20 segments, parts, your part and rank,
-- hand-in), the season rewards track and the seasons timeline. The hand-in is an intent (WEHANDIN):
-- the server counts the tokens and the points.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S

local floor, max, min = math.floor, math.max, math.min

local SE = {}
ns.Season = SE

SE.W, SE.H = 900, 600

local win = UI.Window("BleakholdSeasonFrame", SE.W, SE.H, "SEASON", "banner")
SE.frame = win

local CW = SE.W - 2 - 40
local content = CreateFrame("Frame", nil, win.content)
content:SetPoint("TOPLEFT", win.content, "TOPLEFT", 20, -16)
content:SetSize(CW, SE.H - 4 - 46 - 32)

------------------------------------------------------------------------------------------------------
-- War effort
------------------------------------------------------------------------------------------------------
local we = UI.Box(content, CW, 286, C.eraBg, C.eraBorder)
we:SetPoint("TOPLEFT", content, "TOPLEFT", 0, 0)
we.label = UI.Text(we, 11, C.dim)
we.label:SetPoint("TOPLEFT", we, "TOPLEFT", 18, -16)
we.label:SetText("SERVER WAR EFFORT")
we.title = UI.Text(we, 24, C.goldPale, "title")
we.title:SetPoint("TOPLEFT", we.label, "BOTTOMLEFT", 0, -4)
we.text = UI.Text(we, 12, C.mid)
we.text:SetPoint("TOPLEFT", we.title, "BOTTOMLEFT", 0, -4)
we.text:SetWidth(CW - 220)
we.pct = UI.Text(we, 32, C.goldLight, "title", "RIGHT")
we.pct:SetPoint("TOPRIGHT", we, "TOPRIGHT", -18, -18)
we.helpers = UI.Text(we, 12, C.dim, "body", "RIGHT")
we.helpers:SetPoint("TOPRIGHT", we.pct, "BOTTOMRIGHT", 0, -4)

local SEGS = 20
local segW = (CW - 36 - (SEGS - 1) * 4) / SEGS
we.segments = {}
for i = 1, SEGS do
    local s = UI.Box(we, segW, 18, C.rail, C.border)
    s:SetPoint("TOPLEFT", we, "TOPLEFT", 18 + (i - 1) * (segW + 4), -96)
    we.segments[i] = s
end

local partW = floor((CW - 36 - 24) / 3)
we.parts = {}
for i = 1, 3 do
    local p = UI.Box(we, partW, 62, C.panel, C.border)
    p:SetPoint("TOPLEFT", we, "TOPLEFT", 18 + (i - 1) * (partW + 12), -126)
    p.ring = UI.Ring(p, 42, 5)
    p.ring:SetPoint("LEFT", p, "LEFT", 10, 0)
    p.name = UI.Text(p, 13, C.text)
    p.name:SetPoint("TOPLEFT", p.ring, "TOPRIGHT", 10, -6)
    UI.OneLine(p.name, partW - 70)
    p.value = UI.Text(p, 12, C.dim)
    p.value:SetPoint("TOPLEFT", p.name, "BOTTOMLEFT", 0, -4)
    we.parts[i] = p
end

local mine = UI.Box(we, CW - 36, 62, C.panel, C.border)
mine:SetPoint("TOPLEFT", we, "TOPLEFT", 18, -202)
mine.badge = UI.Badge(mine, 40, "shield", C.active, C.gold)
mine.badge:SetPoint("LEFT", mine, "LEFT", 12, 0)
mine.points = UI.Text(mine, 14, C.text)
mine.points:SetPoint("TOPLEFT", mine.badge, "TOPRIGHT", 12, -4)
mine.rank = UI.Text(mine, 12, C.dim)
mine.rank:SetPoint("TOPLEFT", mine.points, "BOTTOMLEFT", 0, -4)
mine.handin = UI.Button(mine, 190, 34, "Hand in spare tokens", "gold", 13)
mine.handin:SetPoint("RIGHT", mine, "RIGHT", -12, 0)
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
local TL_W = 360
local trackW = CW - TL_W - 16
local track = UI.Box(content, trackW, 210, C.card, C.border)
track:SetPoint("TOPLEFT", we, "BOTTOMLEFT", 0, -14)
track.title = UI.Text(track, 16, C.text, "title")
track.title:SetPoint("TOPLEFT", track, "TOPLEFT", 16, -14)
track.title:SetText("Season rewards")
local NODES = 4
local lineL, lineR = 16 + 23, trackW - 16 - 23
track.line = UI.Solid(track, C.track, "BORDER")
track.line:SetPoint("TOPLEFT", track, "TOPLEFT", lineL, -71)
track.line:SetSize(lineR - lineL, 4)
track.fill = UI.Solid(track, C.teal, "ARTWORK")
track.fill:SetPoint("TOPLEFT", track, "TOPLEFT", lineL, -71)
track.fill:SetSize(1, 4)
track.nodes = {}
for i = 1, NODES do
    local x = lineL + (lineR - lineL) * (i - 1) / (NODES - 1)
    local n = CreateFrame("Frame", nil, track)
    n:SetSize(150, 140)
    n:SetPoint("TOP", track, "TOPLEFT", x, -50)
    n.dot = UI.Badge(n, 46, "check", C.panel, C.eraBorder)
    n.dot:SetPoint("TOP", n, "TOP", 0, 0)
    n.name = UI.Text(n, 13, C.text, "body", "CENTER")
    n.name:SetPoint("TOP", n.dot, "BOTTOM", 0, -6)
    n.need = UI.Text(n, 11, C.dim, "body", "CENTER")
    n.need:SetPoint("TOP", n.name, "BOTTOM", 0, -4)
    n.need:SetWidth(140)
    n.state = UI.Text(n, 11, C.dim, "body", "CENTER")
    n.state:SetPoint("TOP", n.need, "BOTTOM", 0, -4)
    track.nodes[i] = n
end
SE.track = track

local tl = UI.Box(content, TL_W, 210, C.card, C.border)
tl:SetPoint("TOPRIGHT", we, "BOTTOMRIGHT", 0, -14)
tl.title = UI.Text(tl, 16, C.text, "title")
tl.title:SetPoint("TOPLEFT", tl, "TOPLEFT", 16, -14)
tl.title:SetText("The seasons")
tl.rows = {}
for i = 1, 5 do
    local r = CreateFrame("Frame", nil, tl)
    r:SetSize(TL_W - 32, 34)
    r:SetPoint("TOPLEFT", tl, "TOPLEFT", 16, -42 - (i - 1) * 34)
    r.dot = UI.Disc(r, 12, C.gold)
    r.dot:SetPoint("TOPLEFT", r, "TOPLEFT", 0, -3)
    r.ring = r:CreateTexture(nil, "OVERLAY")
    r.ring:SetTexture(UI.ART .. "Ring")
    r.ring:SetSize(12, 12)
    r.ring:SetPoint("CENTER", r.dot, "CENTER")
    r.ring:SetVertexColor(UI.Rgb(C.eraBorder))
    r.name = UI.Text(r, 13, C.text)
    r.name:SetPoint("TOPLEFT", r, "TOPLEFT", 22, 0)
    r.text = UI.Text(r, 11, C.dim)
    r.text:SetPoint("TOPLEFT", r.name, "BOTTOMLEFT", 0, -2)
    UI.OneLine(r.text, TL_W - 54)
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
    UI.SetText(win.title, string.upper(seasonName or "Season"))

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
    local filled = (s and s.wePermille or 0) / 1000 * SEGS
    for i, seg in ipairs(we.segments) do
        if i <= floor(filled) then
            UI.Colors(seg, C.gold, C.goldLight)
        elseif i - 1 < filled then
            UI.Colors(seg, C.goldDark, C.goldLight)
        else
            UI.Colors(seg, C.rail, C.border)
        end
    end
    for i, p in ipairs(we.parts) do
        local part = s and s.parts[i]
        if part then
            p.ring:SetProgress(part.permille / 1000, C.gold)
            UI.SetText(p.name, part.name)
            p.value:SetText(floor(part.permille / 10) .. "% of its goal")
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
            UI.SetText(n.state, (r and r.stateText) or (earned and "Earned" or ""))
            UI.SetColor(n.state, earned and C.teal or C.dim)
            n.dot.fill:SetVertexColor(UI.Rgb(earned and C.teal or C.panel))
            n.dot.ring:SetVertexColor(UI.Rgb(earned and C.teal or C.eraBorder))
            n.dot.glyph:SetVertexColor(UI.Rgb(earned and C.bg or C.goldLight))
            UI.SetGlyph(n.dot.glyph, ({ "check", "shirt", "mount", "banner" })[i] or "reward")
            if earned then
                UI.SetGlyph(n.dot.glyph, "check")
            end
            n:Show()
        else
            n:Hide()
        end
    end
    local fillW = (lineR - lineL) * max(0, lastEarned - 1) / (NODES - 1)
    track.fill:SetWidth(max(1, fillW))

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
            if now then
                r.dot:Show()
                r.ring:Hide()
            else
                r.dot:Hide()
                r.ring:Show()
            end
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
