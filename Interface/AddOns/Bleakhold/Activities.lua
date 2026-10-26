-- Bleakhold: Activities window. Nav rail (Dungeons, Keys, Rift, Royale, War Mode, Tasks, Legacies, Season), header
-- with the daily and weekly reset, and the Tasks page: era banner with affixes, daily task cards with
-- progress rings and Claim, weekly tasks, "your week" aside and Find a group, and the battleground kill
-- announcer's settings (Announcer.lua) while the realm runs it (HELLO feature bit 8192), Royale on or off.
-- Dungeons.lua, Keys.lua, Rift.lua, Royale.lua and WarMode.lua add their pages through Activities.AddPage. A nav entry
-- with an available() test (Royale: HELLO feature bit 4096, War Mode: 16384) is left out of the rail while it says no
-- (A.LayoutNav).
local ADDON, ns = ...
local U, UI, Comm, Data = ns.U, ns.UI, ns.Comm, ns.Data
local C = UI.C
local S = ns.S

local floor, max, min = math.floor, math.max, math.min

local A = {}
ns.Activities = A

A.W, A.H = 940, 600
A.RAIL = 92
A.pages = {}
A.order = {}
A.current = nil

local win = UI.Window("BleakholdActivitiesFrame", A.W, A.H, "ACTIVITIES", "star")
A.frame = win

------------------------------------------------------------------------------------------------------
-- Header: reset pills
------------------------------------------------------------------------------------------------------
local weeklyPill = UI.Pill(win.header, "", C.chip, C.chipBorder, C.text, 12)
weeklyPill:SetPoint("RIGHT", win.close, "LEFT", -10, 0)
local dailyPill = UI.Pill(win.header, "", C.chip, C.chipBorder, C.text, 12)
dailyPill:SetPoint("RIGHT", weeklyPill, "LEFT", -8, 0)

function A.ResetTexts()
    local s = Comm.server or {}
    local now = Comm.ServerTime()
    local daily, weekly
    if s.dailyReset then
        daily = "Daily reset  " .. U.Duration(s.dailyReset - now)
    else
        daily = "Daily reset  -"
    end
    if s.weeklyReset then
        local offset = (s.utcOffsetMin or 0) * 60
        weekly = "Weekly reset  " .. (U.Date("!%a %H:%M", s.weeklyReset + offset) or "-")
    else
        weekly = "Weekly reset  -"
    end
    return daily, weekly
end

local resetAsked = 0
local function updateHeader()
    local daily, weekly = A.ResetTexts()
    dailyPill:SetValue(daily)
    weeklyPill:SetValue(weekly)
    -- after a reset passes, fetch the new day once
    local s = Comm.server or {}
    if s.dailyReset and Comm.ServerTime() >= s.dailyReset and GetTime() - resetAsked > 60 and Comm.ready then
        resetAsked = GetTime()
        Comm.Refresh("TASKS")
        Comm.Refresh("WEEK")
        Comm.Refresh("ERA")
    end
end

------------------------------------------------------------------------------------------------------
-- Rail and pages
------------------------------------------------------------------------------------------------------
local rail = UI.Box(win.content, A.RAIL, 10, C.rail)
rail:SetPoint("TOPLEFT", win.content, "TOPLEFT", 0, 0)
rail:SetPoint("BOTTOMLEFT", win.content, "BOTTOMLEFT", 0, 0)
local railLine = UI.Solid(rail, C.border, "BORDER")
railLine:SetPoint("TOPRIGHT")
railLine:SetPoint("BOTTOMRIGHT")
railLine:SetWidth(1)

local main = CreateFrame("Frame", nil, win.content)
main:SetPoint("TOPLEFT", rail, "TOPRIGHT", 16, -14)
main:SetPoint("BOTTOMRIGHT", win.content, "BOTTOMRIGHT", -16, 12)
A.main = main
A.PW = A.W - 2 - A.RAIL - 32       -- page width
A.PH = A.H - 4 - 46 - 26           -- page height

-- Strip for server errors and the out-of-date notice (above the page, hidden when empty).
local strip = UI.Box(win.content, 10, 26, "3A1F1F", C.red, 0.95)
strip:SetPoint("BOTTOMLEFT", main, "BOTTOMLEFT", 0, 0)
strip:SetPoint("BOTTOMRIGHT", main, "BOTTOMRIGHT", 0, 0)
strip:SetFrameLevel(main:GetFrameLevel() + 20)
strip.text = UI.Text(strip, 12, C.text, "body", "CENTER")
strip.text:SetPoint("CENTER")
strip:Hide()
A.strip = strip

function A.ShowStrip(text, seconds)
    UI.SetText(strip.text, text)
    strip:Show()
    strip.hideAt = seconds and (GetTime() + seconds) or nil
end

local navDefs = {
    { key = "dungeons", glyph = "dungeon", label = "Dungeons" },
    { key = "keys", glyph = "key", label = "Keys" },
    { key = "rift", glyph = "rift", label = "Rift" },
    { key = "royale", glyph = "sword", label = "Royale", available = function()
        return ns.Royale ~= nil and ns.Royale.Live()
    end },
    { key = "warmode", glyph = "shield", label = "War Mode", available = function()
        return ns.WarMode ~= nil and ns.WarMode.Live()
    end },
    { key = "tasks", glyph = "tasks", label = "Tasks" },
    { key = "legacies", glyph = "legacy", label = "Legacies" },
    { key = "season", glyph = "banner", label = "Season" },
}
A.nav = {}

function A.AddPage(key, page)
    page:SetParent(main)
    page:ClearAllPoints()
    page:SetPoint("TOPLEFT", main, "TOPLEFT", 0, 0)
    page:SetSize(A.PW, A.PH)
    page:Hide()
    A.pages[key] = page
end

function A.NewPage()
    local p = CreateFrame("Frame", nil, main)
    p:SetSize(A.PW, A.PH)
    return p
end

function A.Show(key)
    if key == "legacies" then
        UI.Open("collections-legacy")
        return
    elseif key == "season" then
        UI.Open("season")
        return
    end
    if not A.pages[key] then
        key = "tasks"
    end
    A.current = key
    for k, p in pairs(A.pages) do
        if k == key then
            p:Show()
        else
            p:Hide()
        end
    end
    for _, b in ipairs(A.nav) do
        b:SetStyle(b.key == key and "tabOn" or "tab")
    end
    ns.cdb.activitiesTab = key
    local page = A.pages[key]
    if page and page.OnOpen then
        ns.SafeCall(page.OnOpen, page)
    end
    if page and page.Refresh then
        ns.SafeCall(page.Refresh, page)
    end
    if not win:IsShown() then
        win:Show()
    end
end

for i, d in ipairs(navDefs) do
    local b = UI.IconButton(rail, 76, 58, d.glyph, d.label, "tab")
    b.key = d.key
    b.available = d.available
    b:SetPoint("TOP", rail, "TOP", 0, -12 - (i - 1) * 66)
    b:SetScript("OnClick", function()
        A.Show(d.key)
    end)
    A.nav[i] = b
end

-- Stack the rail's entries without gaps, leaving out the ones whose available() says no.
function A.LayoutNav()
    local n = 0
    for _, b in ipairs(A.nav) do
        if not b.available or b.available() then
            b:ClearAllPoints()
            b:SetPoint("TOP", rail, "TOP", 0, -12 - n * 66)
            b:Show()
            n = n + 1
        else
            b:Hide()
        end
    end
end
A.LayoutNav()

------------------------------------------------------------------------------------------------------
-- Tasks page
------------------------------------------------------------------------------------------------------
local P = A.NewPage()
A.AddPage("tasks", P)
A.tasksPage = P

local ASIDE = 230
local LEFT = A.PW - ASIDE - 14

-- Era banner
local era = UI.Box(P, A.PW, 86, C.eraBg, C.eraBorder)
era:SetPoint("TOPLEFT", P, "TOPLEFT", 0, 0)
era.glow = era:CreateTexture(nil, "BORDER")
era.glow:SetTexture(UI.ART .. "Fade")
era.glow:SetPoint("TOPLEFT", era, "TOPLEFT", 1, -1)
era.glow:SetPoint("TOPRIGHT", era, "TOPRIGHT", -1, -1)
era.glow:SetHeight(40)
era.glow:SetVertexColor(UI.Rgb(C.gold, 0.10))
era.badge = UI.Badge(era, 54, "flame", C.active, C.gold)
era.badge:SetPoint("LEFT", era, "LEFT", 16, 0)
era.label = UI.Text(era, 11, C.dim)
era.label:SetPoint("TOPLEFT", era, "TOPLEFT", 84, -14)
era.label:SetText("ACTIVE ERA THIS WEEK")
era.name = UI.Text(era, 22, C.goldPale, "title")
era.name:SetPoint("TOPLEFT", era.label, "BOTTOMLEFT", 0, -3)
era.text = UI.Text(era, 12, C.mid)
era.text:SetPoint("TOPLEFT", era.name, "BOTTOMLEFT", 0, -3)
era.text:SetWidth(430)
era.next = UI.Text(era, 12, C.mid, "body", "RIGHT")
era.next:SetPoint("BOTTOMRIGHT", era, "BOTTOMRIGHT", -16, 14)
era.pills = {}
for i = 1, 4 do
    local p = UI.Pill(era, "", "2E2638", C.eraBorder, C.text, 12)
    p:Hide()
    era.pills[i] = p
end
P.era = era

-- Daily tasks
local dailyTitle = UI.Text(P, 16, C.text, "title")
dailyTitle:SetPoint("TOPLEFT", era, "BOTTOMLEFT", 0, -16)
dailyTitle:SetText("Daily tasks")
local reroll = UI.Button(P, 170, 26, "Reroll one", "ghost", 12)
reroll:SetPoint("TOPRIGHT", P, "TOPLEFT", LEFT, -98)
P.reroll = reroll

local CARD_W = floor((LEFT - 20) / 3)
P.cards = {}
for i = 1, 3 do
    local c = UI.Box(P, CARD_W, 150, C.card, C.border)
    c:SetPoint("TOPLEFT", P, "TOPLEFT", (i - 1) * (CARD_W + 10), -132)
    c.ring = UI.Ring(c, 46, 5)
    c.ring:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -12)
    c.title = UI.Text(c, 13, C.text)
    c.title:SetPoint("TOPLEFT", c.ring, "TOPRIGHT", 10, -6)
    UI.OneLine(c.title, CARD_W - 76)
    c.progress = UI.Text(c, 12, C.dim)
    c.progress:SetPoint("TOPLEFT", c.title, "BOTTOMLEFT", 0, -4)
    c.text = UI.Text(c, 11, C.mid)
    c.text:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -66)
    c.text:SetWidth(CARD_W - 22)
    c.text:SetJustifyV("TOP")
    c.text:SetHeight(34)
    c.claim = UI.Button(c, CARD_W - 24, 30, "Claim", "teal", 13)
    c.claim:SetPoint("BOTTOM", c, "BOTTOM", 0, 10)
    c.chip = UI.Box(c, CARD_W - 24, 30, C.header, C.border)
    c.chip:SetPoint("BOTTOM", c, "BOTTOM", 0, 10)
    c.chip.icon = UI.Glyph(c.chip, "reward", 14, C.goldLight)
    c.chip.icon:SetPoint("LEFT", c.chip, "LEFT", 8, 0)
    c.chip.text = UI.Text(c.chip, 12, C.goldLight)
    c.chip.text:SetPoint("LEFT", c.chip.icon, "RIGHT", 6, 0)
    c.chip.text:SetPoint("RIGHT", c.chip, "RIGHT", -6, 0)
    c.pick = UI.Button(c, CARD_W - 24, 30, "Reroll this task", "gold", 12)
    c.pick:SetPoint("BOTTOM", c, "BOTTOM", 0, 10)
    c.pick:Hide()
    P.cards[i] = c
end

-- Weekly tasks
local weeklyTitle = UI.Text(P, 16, C.text, "title")
weeklyTitle:SetPoint("TOPLEFT", P, "TOPLEFT", 0, -296)
weeklyTitle:SetText("Weekly tasks")
P.rows = {}
for i = 1, 3 do
    local r = UI.Box(P, LEFT, 44, C.card, C.border)
    r:SetPoint("TOPLEFT", P, "TOPLEFT", 0, -322 - (i - 1) * 50)
    r.title = UI.Text(r, 13, C.text)
    r.title:SetPoint("TOPLEFT", r, "TOPLEFT", 12, -7)
    r.text = UI.Text(r, 11, C.dim)
    r.text:SetPoint("TOPLEFT", r.title, "BOTTOMLEFT", 0, -3)
    r.text:SetWidth(LEFT - 360)
    r.bar = UI.Bar(r, 150, 6, C.gold, C.deep)
    r.bar:SetPoint("RIGHT", r, "RIGHT", -170, 5)
    r.progress = UI.Text(r, 11, C.mid)
    r.progress:SetPoint("TOPLEFT", r.bar, "BOTTOMLEFT", 0, -3)
    r.reward = UI.Pill(r, "", C.active, C.eraBorder, C.goldPale, 11)
    r.reward:SetPoint("RIGHT", r, "RIGHT", -10, 0)
    r.claim = UI.Button(r, 90, 24, "Claim", "teal", 12)
    r.claim:SetPoint("RIGHT", r, "RIGHT", -10, 0)
    P.rows[i] = r
end

-- The battleground kill announcer (section 18): its voice and volume, under the weekly tasks, shown while the realm
-- runs the announcer (feature bit 8192) whether or not Bleakhold Royale is on
local ann = UI.Box(P, LEFT, 44, C.card, C.border)
ann:SetPoint("TOPLEFT", P, "TOPLEFT", 0, -472)
ann.title = UI.Text(ann, 13, C.text)
ann.title:SetPoint("TOPLEFT", ann, "TOPLEFT", 12, -7)
ann.title:SetText("Kill announcer")
ann.text = UI.Text(ann, 11, C.dim)
ann.text:SetPoint("TOPLEFT", ann.title, "BOTTOMLEFT", 0, -3)
UI.OneLine(ann.text, LEFT - 310)
ann.text:SetText("First blood, streaks and multi-kills in every battleground")
ann.volume = UI.Dropdown(ann, 140, function(v)
    ns.Announcer.SetQuiet(v == "quiet")
end)
ann.volume:SetPoint("RIGHT", ann, "RIGHT", -9, 0)
ann.volume:SetItems({ { value = "normal", text = "Volume: Normal" }, { value = "quiet", text = "Volume: Quiet" } })
ann.voice = UI.Dropdown(ann, 130, function(v)
    ns.Announcer.SetVoice(v)
end)
ann.voice:SetPoint("RIGHT", ann.volume, "LEFT", -8, 0)
ann.voice:SetItems({ { value = "off", text = "Voice: Off" }, { value = "male", text = "Voice: Male" },
    { value = "female", text = "Voice: Female" } })
ann:Hide()
P.announcer = ann

function P:RefreshAnnouncer()
    if not (ns.Announcer and Comm.HasFeature(Comm.FEATURE.BG_ANNOUNCER)) then
        ann:Hide()
        return
    end
    ann.voice:SetValue(ns.Announcer.Voice(), true)
    ann.volume:SetValue(ns.Announcer.Quiet() and "quiet" or "normal", true)
    ann:Show()
end

-- Aside
local week = UI.Box(P, ASIDE, 150, C.card, C.border)
week:SetPoint("TOPRIGHT", P, "TOPRIGHT", 0, -100)
week.label = UI.Text(week, 11, C.dim)
week.label:SetPoint("TOPLEFT", week, "TOPLEFT", 12, -12)
week.label:SetText("YOUR WEEK")
week.rows = {}
for i = 1, 5 do
    local l = UI.Text(week, 13, C.mid)
    l:SetPoint("TOPLEFT", week, "TOPLEFT", 12, -34 - (i - 1) * 22)
    local v = UI.Text(week, 13, C.text, "body", "RIGHT")
    v:SetPoint("TOPRIGHT", week, "TOPRIGHT", -12, -34 - (i - 1) * 22)
    week.rows[i] = { label = l, value = v }
end
P.week = week

local bonus = UI.Box(P, ASIDE, 118, C.eraBg, C.eraBorder)
bonus:SetPoint("TOPRIGHT", week, "BOTTOMRIGHT", 0, -12)
bonus.label = UI.Text(bonus, 11, C.dim)
bonus.label:SetPoint("TOPLEFT", bonus, "TOPLEFT", 12, -12)
bonus.label:SetText("WEEKLY BONUS")
bonus.title = UI.Text(bonus, 14, C.goldPale)
bonus.title:SetPoint("TOPLEFT", bonus.label, "BOTTOMLEFT", 0, -6)
UI.OneLine(bonus.title, ASIDE - 22)
bonus.text = UI.Text(bonus, 11, C.mid)
bonus.text:SetPoint("TOPLEFT", bonus.title, "BOTTOMLEFT", 0, -4)
bonus.text:SetWidth(ASIDE - 22)
bonus.text:SetJustifyV("TOP")
bonus.text:SetHeight(30)
bonus.state = UI.Text(bonus, 12, C.teal)
bonus.state:SetPoint("BOTTOMLEFT", bonus, "BOTTOMLEFT", 12, 10)
P.bonus = bonus

local find = UI.Button(P, ASIDE, 40, "Find a group", "gold", 14)
find:SetPoint("TOPRIGHT", bonus, "BOTTOMRIGHT", 0, -12)
find:SetScript("OnClick", function()
    A.Show("dungeons")
end)
P.find = find

local rerollMode = false

local function taskByUid(uid)
    return S.tasks and S.tasks.byUid[uid]
end

local function doReroll(uid)
    rerollMode = false
    local t = S.tasks
    if not t or not taskByUid(uid) then
        return
    end
    if (t.freeRerolls or 0) > 0 or (t.rerollCost or 0) == 0 then
        Comm.Send("TREROLL", uid)
    else
        local cost = t.rerollCurrency == "C" and (U.Commas(t.rerollCost) .. " Mythic Coins") or ns.RewardText("G", t.rerollCost)
        UI.Confirm("Reroll this task for " .. cost .. "?", function()
            Comm.Send("TREROLL", uid)
        end, "Reroll")
    end
    P:Refresh()
end

reroll:SetScript("OnClick", function()
    rerollMode = not rerollMode
    P:Refresh()
end)

local function setCard(c, t)
    if not t then
        c.ring:SetProgress(0)
        UI.SetText(c.title, Comm.ready and "No task" or "Waiting for the server")
        c.progress:SetText("")
        UI.SetText(c.text, "")
        c.claim:Hide()
        c.chip:Hide()
        c.pick:Hide()
        UI.Colors(c, C.card, C.border)
        return
    end
    local need = max(1, t.need or 1)
    local have = min(t.have or 0, need)
    local done = t.state >= 1
    c.ring:SetProgress(have / need, done and C.teal or C.gold)
    UI.SetText(c.title, ns.TaskTitle(t))
    c.progress:SetText(have .. " / " .. need)
    UI.SetText(c.text, ns.TaskText(t))
    UI.Colors(c, C.card, done and C.teal or C.border)
    c.claim:Hide()
    c.chip:Hide()
    c.pick:Hide()
    if rerollMode and t.state == 0 then
        c.pick:Show()
        c.pick:SetScript("OnClick", function()
            doReroll(t.uid)
        end)
    elseif t.state == 1 then
        c.claim:SetLabel("Claim " .. U.Safe(ns.TaskReward(t)))
        c.claim:Show()
        c.claim:SetScript("OnClick", function()
            Comm.Send("TCLAIM", t.uid)
        end)
    elseif t.state == 2 then
        c.chip:Show()
        UI.SetColor(c.chip.text, C.mute)
        c.chip.text:SetText("Claimed")
        c.chip.icon:SetVertexColor(UI.Rgb(C.mute))
    else
        c.chip:Show()
        UI.SetColor(c.chip.text, C.goldLight)
        c.chip.icon:SetVertexColor(UI.Rgb(C.goldLight))
        UI.SetText(c.chip.text, ns.TaskReward(t))
    end
end

local function setRow(r, t)
    if not t then
        r:Hide()
        return
    end
    r:Show()
    local need = max(1, t.need or 1)
    local have = min(t.have or 0, need)
    UI.SetText(r.title, ns.TaskTitle(t))
    UI.SetText(r.text, ns.TaskText(t))
    r.bar:SetProgress(have / need)
    r.progress:SetText(have .. " / " .. need)
    r.reward:SetValue(ns.TaskReward(t))
    -- the design has no claim button for weekly tasks; one appears only if the server marks it claimable
    if t.state == 1 then
        r.reward:Hide()
        r.claim:Show()
        r.claim:SetScript("OnClick", function()
            Comm.Send("TCLAIM", t.uid)
        end)
    else
        r.claim:Hide()
        r.reward:Show()
        if t.state == 2 then
            r.reward:SetValue("Claimed")
        end
    end
end

function P:Refresh()
    -- era banner
    local e = S.era
    if e and e.eraId then
        local def = ns.Def("E", e.eraId) or {}
        UI.SetText(era.name, def.name or ("Era " .. e.eraId))
        UI.SetText(era.text, def.text or "")
        local nextName = e.nextEraId and ns.DefName("E", e.nextEraId)
        UI.SetText(era.next, nextName and ("Next week: " .. nextName .. " era") or "")
    else
        UI.SetText(era.name, Comm.ready and "No era this week" or (Comm.outdated and "Client out of date" or "Connecting to Bleakhold"))
        UI.SetText(era.text, Comm.ready and "" or "Bleakhold features appear once the server answers. /bh demo shows a preview.")
        era.next:SetText("")
    end
    local affixes = e and e.affixes or {}
    local shown = {}
    for i, p in ipairs(era.pills) do
        local id = affixes[i]
        if id then
            p:SetValue(ns.DefName("A", id, "Affix " .. id))
            local d = ns.Def("A", id)
            p.tooltip = function()
                return { U.Safe(ns.DefName("A", id, "Affix " .. id)), d and d.text and U.Safe(d.text) or nil }
            end
            p:Show()
            shown[#shown + 1] = p
        else
            p:Hide()
        end
    end
    -- laid out from the right edge: reverse so they read in order
    local rtl = {}
    for i = #shown, 1, -1 do
        rtl[#rtl + 1] = shown[i]
    end
    UI.Row(rtl, era, "TOPRIGHT", "TOPRIGHT", -16, -16, 6, true)

    -- daily
    local t = S.tasks
    local daily = t and t.daily or {}
    for i, c in ipairs(P.cards) do
        setCard(c, daily[i])
    end
    local free = t and t.freeRerolls or 0
    if rerollMode then
        reroll:SetLabel("Cancel reroll")
    elseif free > 0 then
        reroll:SetLabel("Reroll one (" .. free .. " free)")
    else
        reroll:SetLabel("Reroll one")
    end
    reroll:SetActive(t ~= nil and #daily > 0)

    -- weekly
    local weekly = t and t.weekly or {}
    for i, r in ipairs(P.rows) do
        setRow(r, weekly[i])
    end

    -- aside
    local w = S.week
    local rows = {
        { "Keys timed", w and tostring(w.keysTimed) or "-" },
        { "Raid Echoes", w and tostring(w.echoes) or "-" },
        { "Rift best", w and ("Floor " .. w.riftBestFloor) or "-" },
        { "Mythic Coins", w and (U.Commas(w.coins) .. (w.coinsCap > 0 and (" / " .. U.Commas(w.coinsCap)) or "")) or "-", C.goldLight },
    }
    if w and w.shards then
        rows[#rows + 1] = { "Shards", U.Commas(w.shards) }
    end
    for i, slot in ipairs(week.rows) do
        local row = rows[i]
        if row then
            slot.label:SetText(row[1])
            slot.value:SetText(row[2])
            UI.SetColor(slot.value, row[3] or C.text)
        else
            slot.label:SetText("")
            slot.value:SetText("")
        end
    end
    local b = e and e.bonusId and ns.Def("B", e.bonusId)
    if b then
        UI.SetText(bonus.title, b.title or "")
        UI.SetText(bonus.text, b.text or "")
        bonus.state:SetText(e.bonusDone and "Done" or "Still open")
        UI.SetColor(bonus.state, e.bonusDone and C.mute or C.teal)
        bonus:Show()
    else
        bonus:Hide()
    end
    P:RefreshAnnouncer()
end

function P:OnOpen()
    Comm.Get("TASKS")
    Comm.Get("WEEK")
    Comm.Get("ERA")
end

------------------------------------------------------------------------------------------------------
-- Window behaviour
------------------------------------------------------------------------------------------------------
function win:OnOpen()
    A.LayoutNav()
    updateHeader()
    A.Show(A.current or ns.cdb.activitiesTab or "tasks")
end

local tick = 0
win:SetScript("OnUpdate", function(self, elapsed)
    tick = tick + (elapsed or 0)
    if strip:IsShown() and strip.hideAt and GetTime() >= strip.hideAt then
        strip:Hide()
    end
    if tick >= 1 then
        tick = 0
        updateHeader()
        local page = A.pages[A.current or ""]
        if page and page.Tick then
            ns.SafeCall(page.Tick, page)
        end
    end
end)

ns.On("STATE", function(topic)
    if not win:IsShown() then
        return
    end
    local page = A.pages[A.current or ""]
    if page and page.Refresh then
        page:Refresh()
    end
end)

ns.On("HELLO", function()
    A.LayoutNav()
    P:RefreshAnnouncer()
    if win:IsShown() then
        updateHeader()
    end
end)

ns.On("ERR", function(e)
    if win:IsShown() and e.text then
        A.ShowStrip(e.text, 6)
    end
end)

ns.On("OUTDATED", function()
    A.ShowStrip("This client is too old for the Bleakhold server. Please update the client.", nil)
end)

local function open(key, toggle)
    if toggle and win:IsShown() and (key == nil or key == A.current) then
        win:Hide()
        return
    end
    A.current = key or A.current or ns.cdb.activitiesTab or "tasks"
    if win:IsShown() then
        A.Show(A.current)
    else
        win:Show()
    end
end

UI.RegisterOpener("activities", function(toggle) open(nil, toggle) end)
for _, key in ipairs({ "tasks", "dungeons", "keys", "rift" }) do
    UI.RegisterOpener(key, function(toggle) open(key, toggle) end)
    ns.AddCommand(key, "open Activities - " .. key, function() open(key) end)
end
ns.AddCommand("activities", "open the Activities window", function() open(nil, true) end)
