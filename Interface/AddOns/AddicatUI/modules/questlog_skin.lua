-- Bleakhold UI - the quest log (L) in AddicatUI's retail look. UI by Addicated.
-- Ported from the Bleakhold UI addon's QuestLog.lua.
-- WoW's own QuestLogFrame stays the window (UI panel, key binding, micro button, tracker clicks, other addons all keep
-- working); only its art and list change: retail's quest list (zone headers, objectives under each quest, quest-type
-- icons, track boxes, search) on the left, the quest on retail's parchment on the right, red buttons at the bottom.
-- The quest text itself is still WoW's (QuestInfo), so rewards, links and tooltips behave as before.
-- Needs the window chrome (utils/window_chrome.lua); turning the "questlog" module off gives WoW's quest log back.
local addon = select(2, ...)
local L = addon.L
local WC = addon.WindowChrome

local QuestLogSkin = { initialized = false, applied = false }

if addon.RegisterModule then
    addon:RegisterModule("questlog", QuestLogSkin, L["Quest Log"],
        L["Retail-style quest log (L): quest list with objectives, search and track boxes, the quest on parchment"], {
            lifecyclePrefix = "QuestLogSkin",
            loadOnce = true,
        })
end

local W, H, HALF = 676, 496, 338
local INSET_TOP, INSET_BOTTOM = 60, 26
local LANE = 24                       -- each inset's right strip, where its scroll bar runs
local PAGE_W, PAGE_H = 299, 404
local ROW_X, ROW_GAP = 4, 2
local HEADER_H, HEADER_GAP = 22, 6
local ICON = 16
local TEXT_X = 24                     -- quests sit under the header text, not under its toggle
local BOOK = "Interface\\QuestFrame\\UI-QuestLog-BookIcon"

local refresh                         -- defined below (the list's painter)
local built
local leftInset, rightInset, scroll, child, emptyText, search, hint
local rows, headers = {}, {}
local query = ""
local lastSel

local function on() return addon:IsModuleEnabled("questlog") end

-- ------------------------------------------------------------------ helpers
local function lift(frame, base)
    for _, c in ipairs({ frame:GetChildren() }) do
        if c:GetFrameLevel() <= base then c:SetFrameLevel(base + 1) end
        lift(c, c:GetFrameLevel())
    end
end
local function raiseAbove(frame, ref, by)
    if frame and ref and frame:GetFrameLevel() <= ref:GetFrameLevel() + (by or 1) - 1 then
        frame:SetFrameLevel(ref:GetFrameLevel() + (by or 1))
        lift(frame, frame:GetFrameLevel())
    end
end

-- retail's rounded quest-log frame around a rectangle (corners + stretched edges of one atlas)
local function ring(host, target, atlasName, corner, outset)
    local e = WC.atlasInfo(atlasName)
    if not e then return end
    local file, aw, ah, l, r, t, b = e[1], e[2], e[3], e[4], e[5], e[6], e[7]
    local u, v = (r - l) * (corner / aw), (b - t) * (corner / ah)
    local function piece(l1, r1, t1, b1)
        local tex = host:CreateTexture(nil, "ARTWORK")
        tex:SetTexture(file)
        tex:SetTexCoord(l1, r1, t1, b1)
        return tex
    end
    local tl, tr = piece(l, l + u, t, t + v), piece(r - u, r, t, t + v)
    local bl, br = piece(l, l + u, b - v, b), piece(r - u, r, b - v, b)
    for _, tex in ipairs({ tl, tr, bl, br }) do tex:SetSize(corner, corner) end
    tl:SetPoint("TOPLEFT", target, "TOPLEFT", -outset, outset)
    tr:SetPoint("TOPRIGHT", target, "TOPRIGHT", outset, outset)
    bl:SetPoint("BOTTOMLEFT", target, "BOTTOMLEFT", -outset, -outset)
    br:SetPoint("BOTTOMRIGHT", target, "BOTTOMRIGHT", outset, -outset)
    local top = piece(l + u, r - u, t, t + v)
    top:SetPoint("TOPLEFT", tl, "TOPRIGHT")
    top:SetPoint("BOTTOMRIGHT", tr, "BOTTOMLEFT")
    local bot = piece(l + u, r - u, b - v, b)
    bot:SetPoint("TOPLEFT", bl, "TOPRIGHT")
    bot:SetPoint("BOTTOMRIGHT", br, "BOTTOMLEFT")
    local lef = piece(l, l + u, t + v, b - v)
    lef:SetPoint("TOPLEFT", tl, "BOTTOMLEFT")
    lef:SetPoint("BOTTOMRIGHT", bl, "TOPRIGHT")
    local rig = piece(r - u, r, t + v, b - v)
    rig:SetPoint("TOPLEFT", tr, "BOTTOMLEFT")
    rig:SetPoint("BOTTOMRIGHT", br, "TOPRIGHT")
end

-- parchment page inside an inset (the quest text's ground)
local function page(inset)
    local p = inset:CreateTexture(nil, "BORDER", nil, -7)
    WC.atlas(p, "questbg-parchment")
    p:SetSize(PAGE_W, PAGE_H)
    p:SetPoint("TOPLEFT", inset, "TOPLEFT", 3, -3)
    return p
end

-- ------------------------------------------------------------------ the quest list
local TAGS = {}
local function addTag(key, atlas) if key then TAGS[string.lower(key)] = atlas end end
addTag(RAID, "raid"); addTag(LFG_TYPE_RAID, "raid"); addTag(LFG_TYPE_DUNGEON, "dungeon")
addTag(LFG_TYPE_HEROIC_DUNGEON, "heroic"); addTag(PVP, "pvp"); addTag(GROUP, "group"); addTag(ELITE, "group")
local function tagAtlas(tag)
    if not tag or tag == "" then return nil end
    local t = string.lower(tag)
    local hit = TAGS[t]
    if not hit then
        if t:find("raid") then hit = "raid"
        elseif t:find("heroic") then hit = "heroic"
        elseif t:find("dungeon") then hit = "dungeon"
        elseif t:find("pvp") then hit = "pvp"
        elseif t:find("group") or t:find("elite") then hit = "group" end
    end
    return hit and ("questlog-questtypeicon-" .. hit)
end

local function objectiveText(index, isComplete)
    if isComplete and isComplete > 0 then
        return "|cff40ff40" .. (QUEST_WATCH_QUEST_READY or "Ready for turn-in") .. "|r"
    end
    if isComplete and isComplete < 0 then return "|cffff4040" .. (FAILED or "Failed") .. "|r" end
    local lines = {}
    for j = 1, (GetNumQuestLeaderBoards(index) or 0) do
        local text, _, finished = GetQuestLogLeaderBoard(j, index)
        if text and not finished then lines[#lines + 1] = "- " .. text end
    end
    return table.concat(lines, "\n")
end

local function collect()
    local out, pending, headerHit = {}, nil, false
    local n = GetNumQuestLogEntries() or 0
    for i = 1, n do
        local title, level, tag, group, isHeader, isCollapsed, isComplete, isDaily = GetQuestLogTitle(i)
        if isHeader then
            pending = { kind = "header", index = i, title = title or "", collapsed = isCollapsed }
            -- a matching zone shows all of its quests
            headerHit = query ~= "" and string.find(string.lower(title or ""), query, 1, true) and true or false
            -- a collapsed zone has no quest rows to match: keep it, or it could not be opened again while searching
            if query == "" or headerHit or isCollapsed then
                out[#out + 1] = pending
                pending.added = true
            end
        elseif title then
            local objectives = objectiveText(i, isComplete)
            if query == "" or headerHit or string.find(string.lower(title), query, 1, true)
                or string.find(string.lower(objectives), query, 1, true) then
                if pending and not pending.added then
                    out[#out + 1] = pending
                    pending.added = true
                end
                out[#out + 1] = { kind = "quest", index = i, title = title, level = level, tag = tag, group = group,
                    complete = isComplete, daily = isDaily, objectives = objectives }
            end
        end
    end
    return out, n
end

-- Add/RemoveQuestWatch only: calling WatchFrame_Update (or QuestLog_Update) from here would build the tracker's POI
-- lines under our taint and block the map / tracker in combat. AddicatUI's tracker follows the calls themselves; WoW's
-- own tracker catches up on its next QUEST_LOG_UPDATE.
local function toggleWatch(index)
    if IsQuestWatched(index) then
        RemoveQuestWatch(index)
    else
        if GetNumQuestWatches() >= (MAX_WATCHABLE_QUESTS or 25) then
            local most = MAX_WATCHABLE_QUESTS or 25
            UIErrorsFrame:AddMessage(format(QUEST_WATCH_TOO_MANY or "%d", most), 1.0, 0.1, 0.1, 1.0)
            refresh()
            return
        end
        AddQuestWatch(index)
    end
    refresh()
end

local function rowTooltip(self)
    local d = self.data
    if not d then return end
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    local c = GetQuestDifficultyColor(d.level or 0)
    GameTooltip:SetText(d.title, c.r, c.g, c.b)
    local info = (LEVEL or "Level") .. " " .. tostring(d.level or "?")
    if d.tag and d.tag ~= "" then info = info .. "  -  " .. d.tag end
    if d.daily then info = info .. "  -  " .. (DAILY or "Daily") end
    GameTooltip:AddLine(info, 0.8, 0.8, 0.8)
    if d.group and d.group > 1 then
        GameTooltip:AddLine(format(QUEST_SUGGESTED_GROUP_NUM or "Suggested Players [%d]", d.group), 0.8, 0.8, 0.8)
    end
    local mates
    for p = 1, GetNumPartyMembers() do
        if IsUnitOnQuest(d.index, "party" .. p) then
            mates = (mates and (mates .. ", ") or "") .. (UnitName("party" .. p) or "?")
        end
    end
    if mates then
        GameTooltip:AddLine((PARTY_QUEST_STATUS_ON or "Party members on quest:") .. " " .. mates, 1, 1, 0.6, 1)
    end
    GameTooltip:AddLine(L["Shift-click: link / track"], 0.5, 0.5, 0.5)
    GameTooltip:Show()
end

local function newHeader(i)
    local h = CreateFrame("Button", nil, child)
    h:SetHeight(HEADER_H)
    h.toggle = h:CreateTexture(nil, "ARTWORK")
    h.toggle:SetSize(18, 18)
    h.toggle:SetPoint("LEFT", h, "LEFT", 1, 0)
    h.text = h:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    h.text:SetPoint("LEFT", h, "LEFT", TEXT_X, 0)
    h.text:SetPoint("RIGHT", h, "RIGHT", -4, 0)
    h.text:SetJustifyH("LEFT")
    h.line = h:CreateTexture(nil, "BACKGROUND")
    h.line:SetTexture(1, 0.82, 0, 0.18)
    h.line:SetHeight(1)
    h.line:SetPoint("BOTTOMLEFT", h, "BOTTOMLEFT", TEXT_X - 2, 0)
    h.line:SetPoint("BOTTOMRIGHT", h, "BOTTOMRIGHT", -2, 0)
    local hl = h:CreateTexture(nil, "HIGHLIGHT")
    hl:SetTexture(1, 1, 1, 0.07)
    hl:SetAllPoints(h)
    h:RegisterForClicks("LeftButtonUp")
    h:SetScript("OnClick", function(self)
        if self.collapsed then ExpandQuestHeader(self.index) else CollapseQuestHeader(self.index) end
    end)
    headers[i] = h
    return h
end

local function newRow(i)
    local r = CreateFrame("Button", nil, child)
    r.glow = r:CreateTexture(nil, "BACKGROUND")
    if not WC.atlas(r.glow, "questlog-quest-glow-yellow") then r.glow:SetTexture(1, 0.82, 0, 0.15) end
    r.glow:SetPoint("TOPLEFT", r, "TOPLEFT", -4, 0)
    r.glow:SetPoint("BOTTOMRIGHT", r, "BOTTOMRIGHT", 4, 0)
    r.glow:Hide()
    local hl = r:CreateTexture(nil, "HIGHLIGHT")
    hl:SetTexture(1, 1, 1, 0.07)
    hl:SetAllPoints(r)
    r.title = r:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    r.title:SetJustifyH("LEFT")
    r.title:SetWordWrap(false)
    r.objectives = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    r.objectives:SetJustifyH("LEFT")
    r.objectives:SetTextColor(0.80, 0.80, 0.80)
    r.objectives:SetPoint("TOPLEFT", r.title, "BOTTOMLEFT", 0, -3)
    r.track = CreateFrame("CheckButton", nil, r)
    r.track:SetSize(ICON, ICON)
    r.track:SetNormalTexture(WC.auiFile("UI\\ui-background-rock"))
    WC.atlas(r.track:GetNormalTexture(), "questlog-icon-ticksquare")
    r.track:SetCheckedTexture(WC.auiFile("UI\\ui-background-rock"))
    WC.atlas(r.track:GetCheckedTexture(), "questlog-icon-checkmark-yellow")
    r.track:SetHighlightTexture(WC.auiFile("UI\\ui-background-rock"))
    WC.atlas(r.track:GetHighlightTexture(), "questlog-icon-ticksquare")
    r.track:GetHighlightTexture():SetBlendMode("ADD")
    r.track:SetScript("OnClick", function() toggleWatch(r.data.index) end)
    r.track:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(TRACK_QUEST or "Track Quest")
        GameTooltip:Show()
    end)
    r.track:SetScript("OnLeave", function() GameTooltip:Hide() end)
    r.tag = r:CreateTexture(nil, "OVERLAY")
    r.tag:SetSize(ICON, ICON)
    r.tag2 = r:CreateTexture(nil, "OVERLAY")
    r.tag2:SetSize(ICON, ICON)
    r.level = r:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    r.level:SetJustifyH("RIGHT")
    r.mates = r:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    r:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    r:SetScript("OnClick", function(self, button)
        -- shift-click with no chat box open tracks (ours, see toggleWatch); everything else is WoW's own row handler:
        -- plain click selects, shift-click with the chat box open links the quest
        if IsModifiedClick("QUESTWATCHTOGGLE") and not (IsModifiedClick("CHATLINK") and ChatEdit_GetActiveWindow()) then
            toggleWatch(self.data.index)
            return
        end
        self:SetID(self.data.index)
        self.isHeader = nil
        QuestLogTitleButton_OnClick(self, button)
    end)
    r:SetScript("OnEnter", rowTooltip)
    r:SetScript("OnLeave", function() GameTooltip:Hide() end)
    rows[i] = r
    return r
end

local function fillRow(r, d, width)
    r.data = d
    local c = GetQuestDifficultyColor(d.level or 0)
    local selected = GetQuestLogSelection() == d.index
    -- right side, from the edge inwards: track box, quest-type icons, party count, level
    r.track:ClearAllPoints()
    r.track:SetPoint("TOPRIGHT", r, "TOPRIGHT", -2, -2)
    r.track:SetChecked(IsQuestWatched(d.index))
    local right = r.track
    local main = tagAtlas(d.tag)
    local second = d.daily and "questlog-questtypeicon-daily" or nil
    if d.complete and d.complete < 0 then main, second = "questlog-questtypeicon-questfailed", nil end
    if not main then main, second = second, nil end
    r.tag:Hide()
    r.tag2:Hide()
    if main and WC.atlas(r.tag, main) then
        r.tag:ClearAllPoints()
        r.tag:SetPoint("RIGHT", right, "LEFT", -2, 0)
        r.tag:Show()
        right = r.tag
        if second and WC.atlas(r.tag2, second) then
            r.tag2:ClearAllPoints()
            r.tag2:SetPoint("RIGHT", right, "LEFT", 0, 0)
            r.tag2:Show()
            right = r.tag2
        end
    end
    local n = 0
    for p = 1, GetNumPartyMembers() do
        if IsUnitOnQuest(d.index, "party" .. p) then n = n + 1 end
    end
    if n > 0 then
        r.mates:SetText("[" .. n .. "]")
        r.mates:ClearAllPoints()
        r.mates:SetPoint("RIGHT", right, "LEFT", -3, 0)
        r.mates:Show()
        right = r.mates
    else
        r.mates:Hide()
    end
    r.level:SetText(d.level or "")
    r.level:ClearAllPoints()
    r.level:SetPoint("RIGHT", right, "LEFT", -4, 0)
    r.title:ClearAllPoints()
    r.title:SetPoint("TOPLEFT", r, "TOPLEFT", TEXT_X, -3)
    r.title:SetPoint("RIGHT", r.level, "LEFT", -4, 0)
    r.title:SetText(d.title)
    if selected then r.title:SetTextColor(1, 1, 1) else r.title:SetTextColor(c.r, c.g, c.b) end
    if selected then r.glow:Show() else r.glow:Hide() end
    local h = 20
    if d.objectives ~= "" then
        r.objectives:SetWidth(width - TEXT_X - 6)
        r.objectives:SetText(d.objectives)
        r.objectives:Show()
        h = h + (r.objectives:GetStringHeight() or 12) + 4
    else
        r.objectives:Hide()
    end
    r:SetHeight(h)
end

function refresh()
    if not built or not QuestLogFrame:IsShown() or not child then return end
    local width = (child:GetWidth() or 0) - ROW_X * 2
    if width <= 0 then width = 290 end
    local data, n = collect()
    local y, nr, nh = 6, 0, 0
    local sel = GetQuestLogSelection()
    local selTop, selBottom
    for _, d in ipairs(data) do
        if d.kind == "header" then
            nh = nh + 1
            local h = headers[nh] or newHeader(nh)
            h.index, h.collapsed = d.index, d.collapsed
            h.text:SetText(d.title)
            if not WC.atlas(h.toggle, d.collapsed and "campaign_headericon_closed" or "campaign_headericon_open") then
                h.toggle:SetTexture(d.collapsed and "Interface\\Buttons\\UI-PlusButton-Up"
                    or "Interface\\Buttons\\UI-MinusButton-Up")
                h.toggle:SetTexCoord(0, 1, 0, 1)
            end
            if y > 6 then y = y + HEADER_GAP end
            h:ClearAllPoints()
            h:SetPoint("TOPLEFT", child, "TOPLEFT", ROW_X, -y)
            h:SetWidth(width)
            h:Show()
            y = y + HEADER_H + 2
        else
            nr = nr + 1
            local r = rows[nr] or newRow(nr)
            r:ClearAllPoints()
            r:SetPoint("TOPLEFT", child, "TOPLEFT", ROW_X, -y)
            r:SetWidth(width)
            fillRow(r, d, width)
            r:Show()
            if d.index == sel then selTop, selBottom = y, y + r:GetHeight() end
            y = y + r:GetHeight() + ROW_GAP
        end
    end
    for i = nr + 1, #rows do rows[i]:Hide() end
    for i = nh + 1, #headers do headers[i]:Hide() end
    child:SetHeight(math.max(y + 6, scroll:GetHeight() or 1))
    if n == 0 then
        emptyText:SetText(QUESTLOG_NO_QUESTS_TEXT or "No active quests")
        emptyText:Show()
    elseif #data == 0 then
        emptyText:SetText(L["No quests match"])
        emptyText:Show()
    else
        emptyText:Hide()
    end
    if scroll.UpdateScrollChildRect then scroll:UpdateScrollChildRect() end
    -- keep a newly selected quest in view
    if sel ~= lastSel and selTop then
        local view = scroll:GetHeight() or 0
        local cur = scroll:GetVerticalScroll() or 0
        local bar = _G[scroll:GetName() .. "ScrollBar"]
        if bar and view > 0 then
            if selTop < cur then
                bar:SetValue(math.max(0, selTop - 6))
            elseif selBottom > cur + view then
                bar:SetValue(selBottom - view + 6)
            end
        end
    end
    lastSel = sel
end
-- Not "Refresh": the module registry would call that in place of the apply step.
QuestLogSkin.RefreshList = refresh

-- ------------------------------------------------------------------ WoW's parts, placed in the new layout
local function placeDetail()
    if not built then return end
    local sf = QuestLogDetailScrollFrame
    local host
    if sf:GetParent() == QuestLogFrame then host = rightInset else host = QuestLogDetailFrame.bhInset end
    if not host then return end
    sf:ClearAllPoints()
    sf:SetPoint("TOPLEFT", host, "TOPLEFT", 6, -9)
    sf:SetSize(PAGE_W - 3, PAGE_H - 12)
    WC.placeScrollBar(sf, host, 0, -8, 0)
    for _, n in ipairs({ "QuestLogDetailScrollFrameScrollBackgroundTopLeft",
        "QuestLogDetailScrollFrameScrollBackgroundBottomRight" }) do
        if _G[n] then _G[n]:Hide() end
    end
    raiseAbove(sf, host, 2)
end

local function placeControls()
    if not built then return end
    local cp = QuestLogControlPanel
    local parent = cp:GetParent()
    if parent ~= QuestLogFrame and parent ~= QuestLogDetailFrame then return end
    cp:ClearAllPoints()
    cp:SetPoint("BOTTOMLEFT", parent, "BOTTOMLEFT", 4, 2)
    cp:SetWidth(HALF - 10)
    cp:SetHeight(22)
    raiseAbove(cp, parent, 6)
end

local function placeMapButton()
    if not built then return end
    local b = QuestLogFrameShowMapButton
    local parent = b:GetParent()
    if parent ~= QuestLogFrame and parent ~= QuestLogDetailFrame then return end
    b:ClearAllPoints()
    b:SetPoint("TOPRIGHT", parent, "TOPRIGHT", -10, -27)
    raiseAbove(b, parent, 6)
end

local function placeCount()
    if not built then return end
    QuestLogCount:ClearAllPoints()
    QuestLogCount:SetPoint("TOPLEFT", QuestLogFrame, "TOPLEFT", 58, -24)
end

-- ------------------------------------------------------------------ build
local function buildDetailWindow()
    local d = QuestLogDetailFrame
    WC.stripTextures(d)
    WC.dressWindow(d, HALF, H)
    WC.portrait(d, nil, BOOK)
    WC.title(d, QuestLogDetailTitleText)
    WC.closeButton(QuestLogDetailFrameCloseButton, d)
    d:SetAttribute("UIPanelLayout-xoffset", 6)
    d.bhInset = WC.inset(d)
    d.bhInset:SetPoint("TOPLEFT", d, "TOPLEFT", 4, -INSET_TOP)
    d.bhInset:SetPoint("BOTTOMRIGHT", d, "BOTTOMRIGHT", -6, INSET_BOTTOM)
    page(d.bhInset)
end

local function buildList(f)
    leftInset = WC.inset(f, false)
    leftInset:SetPoint("TOPLEFT", f, "TOPLEFT", 4, -INSET_TOP)
    leftInset:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", 4, INSET_BOTTOM)
    leftInset:SetWidth(HALF - 10)
    local listArea = CreateFrame("Frame", nil, leftInset)
    listArea:SetPoint("TOPLEFT", leftInset, "TOPLEFT", 3, -3)
    listArea:SetPoint("BOTTOMRIGHT", leftInset, "BOTTOMRIGHT", -LANE, 3)
    -- the dark quest book behind the list, cropped (not squashed) to the list's height
    local tome = leftInset:CreateTexture(nil, "BACKGROUND")
    local e = WC.atlasInfo("questlog-main-background")
    tome:SetTexture(e[1])
    local listH = H - INSET_TOP - INSET_BOTTOM - 6
    local frac = math.min(1, listH / e[3])
    tome:SetTexCoord(e[4], e[5], e[6], e[6] + (e[7] - e[6]) * frac)
    tome:SetAllPoints(listArea)
    local ringHost = CreateFrame("Frame", nil, leftInset)
    ringHost:SetAllPoints(listArea)
    ringHost:EnableMouse(false)
    ring(ringHost, listArea, "questlog-frame", 40, 3)
    local fil = ringHost:CreateTexture(nil, "OVERLAY")
    if WC.atlas(fil, "questlog-frame-filigree", true) then
        fil:SetPoint("TOP", listArea, "TOP", 0, 4)
    else
        fil:Hide()
    end
    local grad = ringHost:CreateTexture(nil, "BORDER")
    if WC.atlas(grad, "questlog-frame-gradient-bottom") then
        grad:SetHeight(60)
        grad:SetPoint("BOTTOMLEFT", listArea, "BOTTOMLEFT")
        grad:SetPoint("BOTTOMRIGHT", listArea, "BOTTOMRIGHT")
    else
        grad:Hide()
    end

    scroll = CreateFrame("ScrollFrame", "AddicatUIQuestLogListScroll", leftInset, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", listArea, "TOPLEFT", 0, -4)
    scroll:SetPoint("BOTTOMRIGHT", listArea, "BOTTOMRIGHT", 0, 4)
    child = CreateFrame("Frame", nil, scroll)
    child:SetSize(HALF - 10 - 3 - LANE, 10)
    scroll:SetScrollChild(child)
    scroll.scrollBarHideable = true
    scroll:EnableMouseWheel(true)
    WC.scrollBar(scroll, leftInset, 0, -8, 0, true)
    ringHost:SetFrameLevel(scroll:GetFrameLevel() + 6)   -- the rounded frame over the scrolling rows

    emptyText = leftInset:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    emptyText:SetPoint("TOP", listArea, "TOP", 0, -40)
    emptyText:SetWidth(240)
    emptyText:Hide()
end

local function buildSearch(f)
    search = CreateFrame("EditBox", "AddicatUIQuestLogSearch", f, "InputBoxTemplate")
    search:SetSize(150, 20)
    search:SetPoint("TOPRIGHT", f, "TOPLEFT", HALF - 14, -31)
    search:SetAutoFocus(false)
    search:SetTextInsets(16, 4, 0, 0)
    search:SetFontObject(ChatFontSmall or GameFontHighlightSmall)
    local glass = search:CreateTexture(nil, "OVERLAY")
    glass:SetSize(13, 13)
    glass:SetPoint("LEFT", search, "LEFT", 0, -1)
    glass:SetTexture(WC.auiFile("Collections\\UI-Searchbox-Icon"))
    hint = search:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
    hint:SetPoint("LEFT", search, "LEFT", 17, 0)
    hint:SetText(SEARCH or "Search")
    search:SetScript("OnTextChanged", function(self)
        local t = self:GetText() or ""
        if t == "" then hint:Show() else hint:Hide() end
        query = string.lower(t)
        refresh()
    end)
    search:SetScript("OnEditFocusGained", function() hint:Hide() end)
    search:SetScript("OnEditFocusLost", function(self) if (self:GetText() or "") == "" then hint:Show() end end)
    search:SetScript("OnEscapePressed", function(self)
        self:SetText("")
        self:ClearFocus()
    end)
    search:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
end

local function build()
    if built or not on() or not QuestLogFrame or not QuestLogDetailFrame or not (WC and WC.chrome()) then return end
    if not (QuestLogControlPanel and QuestLogDetailScrollFrame and QuestLogScrollFrame
        and QuestLogTitleButton_OnClick) then
        return
    end
    built = true
    QuestLogSkin.initialized = true
    local f = QuestLogFrame
    WC.stripTextures(f)
    WC.dressWindow(f, W, H)
    WC.portrait(f, nil, BOOK)
    WC.title(f, QuestLogTitleText)
    WC.closeButton(QuestLogFrameCloseButton, f)
    f:SetAttribute("UIPanelLayout-xoffset", 6)

    -- WoW's list stays (its code expects it) but is invisible and out of the mouse's way
    QuestLogScrollFrame:SetAlpha(0)
    QuestLogScrollFrame:EnableMouse(false)
    QuestLogScrollFrame:EnableMouseWheel(false)
    for _, b in ipairs(QuestLogScrollFrame.buttons or {}) do b:EnableMouse(false) end
    if QuestLogScrollFrameScrollBar then QuestLogScrollFrameScrollBar:EnableMouse(false) end
    for _, n in ipairs({ "QuestLogScrollFrameScrollBarScrollUpButton",
        "QuestLogScrollFrameScrollBarScrollDownButton" }) do
        if _G[n] then _G[n]:EnableMouse(false) end
    end
    EmptyQuestLogFrame:SetAlpha(0)
    WC.stripTextures(QuestLogCount)

    buildList(f)
    rightInset = WC.inset(f)
    rightInset:SetPoint("TOPRIGHT", f, "TOPRIGHT", -6, -INSET_TOP)
    rightInset:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -6, INSET_BOTTOM)
    rightInset:SetWidth(HALF - 10)
    page(rightInset)
    buildSearch(f)
    buildDetailWindow()
    WC.scrollBar(QuestLogDetailScrollFrame, rightInset, 0, -8, 0, true)

    for _, b in ipairs({ QuestLogFrameAbandonButton, QuestLogFramePushQuestButton, QuestLogFrameTrackButton,
        QuestLogFrameCancelButton }) do
        WC.redButton(b)
        b:SetHeight(22)
    end
    QuestLogFrameAbandonButton:SetWidth(108)
    QuestLogFrameTrackButton:SetWidth(100)
    QuestLogFrameCancelButton:ClearAllPoints()
    QuestLogFrameCancelButton:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -8, 2)
    QuestLogFrameCancelButton:SetWidth(96)

    -- WoW moves these on every show: put them back in our layout each time
    hooksecurefunc("QuestLogDetailFrame_AttachToQuestLog", placeDetail)
    hooksecurefunc("QuestLogDetailFrame_DetachFromQuestLog", placeDetail)
    hooksecurefunc("QuestLogControlPanel_UpdatePosition", placeControls)
    hooksecurefunc("QuestLogShowMapPOI_UpdatePosition", placeMapButton)
    hooksecurefunc("QuestLog_UpdateQuestCount", placeCount)
    hooksecurefunc("QuestLog_Update", refresh)
    -- QuestInfo re-parents its parts into the page on every quest: lift them so none lands under the parchment
    hooksecurefunc("QuestLog_UpdateQuestDetails", function()
        local sf = QuestLogDetailScrollFrame
        if sf then lift(sf, sf:GetFrameLevel()) end
    end)
    hooksecurefunc("QuestLogControlPanel_UpdateState", refresh)
    f:HookScript("OnShow", function()
        placeDetail()
        placeControls()
        placeMapButton()
        placeCount()
        WC.topLayers(f)
        refresh()
    end)
    QuestLogDetailFrame:HookScript("OnShow", function()
        placeDetail()
        placeControls()
        placeMapButton()
        WC.topLayers(QuestLogDetailFrame)
    end)

    -- layers: insets at the bottom, WoW's moving parts above them
    local base = f:GetFrameLevel()
    leftInset:SetFrameLevel(base + 1)
    rightInset:SetFrameLevel(base + 1)
    for _, c in ipairs({ f:GetChildren() }) do
        if c ~= leftInset and c ~= rightInset and c:GetFrameLevel() <= base + 1 then
            c:SetFrameLevel(base + 3)
            lift(c, base + 3)
        end
    end
    lift(leftInset, base + 1)
    placeDetail()
    placeControls()
    placeMapButton()
    placeCount()
    WC.topLayers(f)
    WC.topLayers(QuestLogDetailFrame)
    if f:IsShown() then refresh() end
end

function addon.ApplyQuestLogSkinSystem()
    if built or not on() then return end
    QuestLogSkin.applied = true
    local ok, err = pcall(build)
    if not ok then
        built = true
        addon:Print(L["Quest log skin skipped:"] .. " " .. tostring(err))
    end
end

function addon.RestoreQuestLogSkinSystem()
    QuestLogSkin.applied = false
end

local loginWatcher = CreateFrame("Frame")
loginWatcher:RegisterEvent("PLAYER_LOGIN")
loginWatcher:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    addon.ApplyQuestLogSkinSystem()
end)
