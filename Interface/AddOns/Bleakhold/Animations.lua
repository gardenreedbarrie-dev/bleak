-- Bleakhold: Animations tab of the Collections window and the emote wheel.
-- The tab lists the Bleakhold dances, every animation the character can play and every emoji (search,
-- category filter, pages of 14), previews the selected one on the player model, plays it, and edits the
-- emote wheel: four pages of eight slots, saved per character. The wheel opens with its key binding (Ctrl+G
-- by default): hold the key, point at a slot and release to play it; a short tap leaves the wheel open for
-- clicking.
-- Dances (Data.dances, DanceData.lua from Tools/DanceForge) are a DANCE intent: the server sets the
-- player's emote state to the stock dance and tells everyone nearby which Bleakhold dance it is, and
-- Bleakhold.exe plays that dance on the character, with its music if the file is there (section 14). Each
-- dance has its own slash command (/stringswing) and /bh dance <name>. The client's own emotes are DoEmote
-- (Data.emotes). Emojis (Data.emojis, EmojiData.lua) are an EMOJI intent: the server shows the emoji
-- above the player's head to everyone nearby, and Bleakhold.exe draws it there (emoji bubbles,
-- docs/BleakholdProtocol.md section 13). /bh emoji <name> sends one.
local ADDON, ns = ...
local U, UI, Data = ns.U, ns.UI, ns.Data
local C = UI.C

local floor, max, min, sqrt, atan2, deg = math.floor, math.max, math.min, math.sqrt, math.atan2, math.deg

local A = {}
ns.Animations = A

A.GRID_COLS, A.GRID_ROWS = 2, 7
A.PAGE_SIZE = A.GRID_COLS * A.GRID_ROWS
A.WHEEL_SLOTS = 8
A.WHEEL_PAGES = 4
A.TAP_SECONDS = 0.25      -- a key press shorter than this leaves the wheel open for clicking
A.DEAD_ZONE = 40          -- cursor distance from the wheel centre below which no slot is chosen
A.BINDING = "BLEAKHOLD_EMOTEWHEEL"
A.DEFAULT_KEY = "CTRL-G"
A.EMOJI_PAGE = 4          -- the default wheel's emojis are on this page (Data.defaultWheel)

A.page = 1
A.filter = "all"
A.wheelPage = 1

------------------------------------------------------------------------------------------------------
-- Catalogue: the emotes, then one entry per emoji (key "emoji:<key>", on the wheel and in saved wheels)
------------------------------------------------------------------------------------------------------
local entries = {}
local dances = {}
for _, d in ipairs(Data.dances or {}) do
    local e = { key = "dance:" .. d.key, name = d.name, cmd = d.cmd, cat = "dance", dance = d.id, danceKey = d.key,
        style = d.cat, bpm = d.bpm, seconds = d.seconds, glyph = "dance",
        text = "A Bleakhold dance: everyone nearby sees it." }
    entries[#entries + 1] = e
    dances[#dances + 1] = e
end
for _, e in ipairs(Data.emotes) do
    entries[#entries + 1] = e
end
local emojis = {}
for _, m in ipairs(Data.emojis or {}) do
    local e = { key = "emoji:" .. m.key, name = m.name, cmd = "/bh emoji " .. m.key, cat = "emoji", emoji = m.id,
        emojiKey = m.key, group = m.group, texture = m.texture, glyph = "sparkle",
        text = "Everyone nearby sees it above your head." }
    entries[#entries + 1] = e
    emojis[#emojis + 1] = e
end

local byKey = {}
for _, e in ipairs(entries) do
    byKey[e.key] = e
end

-- The name normal form of Tools/EmojiForge: lower case, trimmed, no leading or trailing ':', runs of
-- whitespace turned into '_'. Keys and names are unique under it (the catalogue is checked when built).
local function norm(s)
    s = string.lower(strtrim(tostring(s or "")))
    s = s:gsub("^:+", ""):gsub(":+$", "")
    return (s:gsub("%s+", "_"))
end

local emojiByNorm = {}
for _, e in ipairs(emojis) do
    emojiByNorm[e.emojiKey] = e
end
for _, e in ipairs(emojis) do
    local n = norm(e.name)
    emojiByNorm[n] = emojiByNorm[n] or e
end

function A.List()
    return entries
end

function A.Dances()
    return dances
end

local danceByNorm = {}
for _, e in ipairs(dances) do
    danceByNorm[e.danceKey] = e
    danceByNorm[norm(e.name)] = danceByNorm[norm(e.name)] or e
    danceByNorm[e.cmd:sub(2)] = danceByNorm[e.cmd:sub(2)] or e
end

-- The dance entry for a key, a name or a command: "string_swing", "String Swing" and "stringswing" all match.
function A.DanceByName(s)
    return danceByNorm[norm(s)]
end

function A.Get(key)
    return key and byKey[key]
end

-- The emoji entry for a key or a name: "Heart Eyes", "heart_eyes" and ":heart_eyes:" all match.
function A.EmojiByName(s)
    return emojiByNorm[norm(s)]
end

local categoryLabel = {}
for _, c in ipairs(Data.animationCategories) do
    categoryLabel[c.key] = c.label
end

function A.CategoryLabel(cat)
    return categoryLabel[cat] or "Animations"
end

-- Is `key` on any wheel page?
function A.OnWheel(key)
    local wheel = ns.cdb.wheel
    if type(wheel) ~= "table" then
        return false
    end
    for p = 1, A.WHEEL_PAGES do
        local page = wheel[p]
        for s = 1, A.WHEEL_SLOTS do
            if page and page[s] == key then
                return true
            end
        end
    end
    return false
end

-- Entries matching the search text (name or command) and the category filter.
function A.Filtered(search, filter)
    search = string.lower(search or "")
    filter = filter or "all"
    local out = {}
    for _, e in ipairs(A.List()) do
        local okCat = filter == "all" or e.cat == filter or (filter == "wheel" and A.OnWheel(e.key))
        local okText = search == "" or string.find(string.lower(e.name), search, 1, true)
            or string.find(e.cmd, search, 1, true)
        if okCat and okText then
            out[#out + 1] = e
        end
    end
    return out
end

------------------------------------------------------------------------------------------------------
-- Wheel storage (BleakholdCharDB.wheel = { [page] = { [slot] = key } })
------------------------------------------------------------------------------------------------------
-- Rebuilds the saved wheel from whatever is stored: unknown keys and malformed pages are dropped, a
-- missing wheel becomes the default one. A wheel saved before emojis existed gets the default page's
-- emojis once, in the free slots of page 4 (BleakholdCharDB.emojiWheel); no slot is ever replaced, and an
-- emoji the player took off later stays off.
function A.EnsureWheel()
    local saved = ns.cdb.wheel
    local wheel = {}
    for p = 1, A.WHEEL_PAGES do
        wheel[p] = {}
        local src = type(saved) == "table" and saved[p] or nil
        if type(saved) ~= "table" then
            src = Data.defaultWheel[p]
        end
        if type(src) == "table" then
            for s = 1, A.WHEEL_SLOTS do
                local key = src[s]
                if type(key) == "string" and byKey[key] then
                    wheel[p][s] = key
                end
            end
        end
    end
    ns.cdb.wheel = wheel
    if not ns.cdb.emojiWheel then
        ns.cdb.emojiWheel = true
        local page = wheel[A.EMOJI_PAGE]
        for _, key in ipairs(type(saved) == "table" and Data.defaultWheel[A.EMOJI_PAGE] or {}) do
            if key:find("^emoji:") and byKey[key] and not A.OnWheel(key) then
                for s = 1, A.WHEEL_SLOTS do
                    if not page[s] then
                        page[s] = key
                        break
                    end
                end
            end
        end
    end
    -- A wheel saved before dances existed gets page 1's dances once, in its first free slots (page 1 first).
    if not ns.cdb.danceWheel then
        ns.cdb.danceWheel = true
        for _, key in ipairs(type(saved) == "table" and Data.defaultWheel[1] or {}) do
            if key:find("^dance:") and byKey[key] and not A.OnWheel(key) then
                local placed = false
                for p = 1, A.WHEEL_PAGES do
                    for s = 1, A.WHEEL_SLOTS do
                        if not placed and not wheel[p][s] then
                            wheel[p][s] = key
                            placed = true
                        end
                    end
                end
            end
        end
    end
    return wheel
end

function A.WheelEntry(page, slot)
    local wheel = ns.cdb.wheel
    local p = type(wheel) == "table" and wheel[page]
    return p and A.Get(p[slot]) or nil
end

function A.SetWheelSlot(page, slot, key)
    if page < 1 or page > A.WHEEL_PAGES or slot < 1 or slot > A.WHEEL_SLOTS then
        return false
    end
    if key ~= nil and not byKey[key] then
        return false
    end
    local wheel = type(ns.cdb.wheel) == "table" and ns.cdb.wheel or A.EnsureWheel()
    wheel[page] = wheel[page] or {}
    wheel[page][slot] = key
    ns.Fire("WHEEL")
    return true
end

-- Puts `key` in the first empty slot, starting on the wheel page shown in the editor. Returns page, slot
-- (or the slot it already has), or nil when the wheel is full.
function A.AddToWheel(key)
    if not byKey[key] then
        return nil
    end
    for p = 1, A.WHEEL_PAGES do
        for s = 1, A.WHEEL_SLOTS do
            local e = A.WheelEntry(p, s)
            if e and e.key == key then
                return p, s, true
            end
        end
    end
    for i = 0, A.WHEEL_PAGES - 1 do
        local p = (A.wheelPage - 1 + i) % A.WHEEL_PAGES + 1
        for s = 1, A.WHEEL_SLOTS do
            if not A.WheelEntry(p, s) then
                A.SetWheelSlot(p, s, key)
                return p, s
            end
        end
    end
    return nil
end

ns.On("DB_READY", function()
    A.EnsureWheel()
end)

------------------------------------------------------------------------------------------------------
-- Playing: an emote is DoEmote; an emoji is an EMOJI intent (the server checks it and shows the bubble
-- to everyone nearby, the player included). The cooldown and the feature check live here, not in
-- Comm.Send, which only sends.
------------------------------------------------------------------------------------------------------
A.EMOJI_COOLDOWN = 3.25   -- s: one bubble's lifetime (WoW/Common/BleakholdEmoji.h), 0.75 s over the server's 2.5 s
A.emojiReadyAt = 0
A.NOTICE_SECONDS = 10     -- the same notice is printed at most once in this time

local noticeAt = {}

function A.EmojiNotice(text)
    local now = GetTime()
    if noticeAt[text] and now - noticeAt[text] < A.NOTICE_SECONDS then
        return false
    end
    noticeAt[text] = now
    ns.Print(text)
    return true
end

-- nil when an emoji can be sent now (cooldown aside), else reason, text.
function A.EmojiState()
    local Comm = ns.Comm
    if Comm.outdated then
        return "outdated", "Emojis: your Bleakhold UI is out of date for this realm."
    end
    if not Comm.ready and not Comm.demo then
        return "offline", "Emojis need the Bleakhold server module, and this realm has not answered (/bh status)."
    end
    if not Comm.HasFeature(Comm.FEATURE.EMOJI) then
        return "off", "Emojis are turned off on this realm."
    end
    return nil
end

local demoNoted, noBubblesNoted

-- Returns true when sent, or false, reason.
function A.SendEmoji(entry)
    if type(entry) == "string" then
        entry = A.Get(entry)
    end
    if not entry or not entry.emoji then
        return false, "not an emoji"
    end
    local reason, text = A.EmojiState()
    if reason then
        A.EmojiNotice(text)
        return false, reason
    end
    local now = GetTime()
    if now < A.emojiReadyAt then
        if UIErrorsFrame then
            UIErrorsFrame:AddMessage("Wait a moment before the next emoji.", 1, 0.45, 0.4)
        end
        return false, "cooldown"
    end
    local ok, err = ns.Comm.Send("EMOJI", entry.emoji)
    if not ok then
        A.EmojiNotice("Emojis: could not send (" .. tostring(err) .. ").")
        return false, err
    end
    A.emojiReadyAt = now + A.EMOJI_COOLDOWN
    if A.selected == entry and A.emojiPreview and A.emojiPreview:IsVisible() then
        A.PopEmojiPreview()
    end
    if ns.Comm.demo then
        if not demoNoted then
            demoNoted = true
            ns.Print("Demo mode: no realm is connected, so nobody sees this emoji.")
        end
    elseif GetCVar("emojiBubbles") == nil and not noBubblesNoted then
        -- the CVar exists only in Bleakhold.exe (WoW/Source/Ui/EmojiBubbleFrame.cpp)
        noBubblesNoted = true
        ns.Print("Your game cannot draw emoji bubbles (start it with Bleakhold.exe); others still see yours.")
    end
    return true
end

-- The server's cooldown answered first (a press that arrived early): wait the whole cooldown again.
ns.On("ERR", function(e)
    if e and e.op == "EMOJI" and e.code == "busy" then
        A.emojiReadyAt = GetTime() + A.EMOJI_COOLDOWN
    elseif e and e.op == "DANCE" and e.code == "busy" then
        A.danceReadyAt = GetTime() + A.DANCE_COOLDOWN
    end
end)

------------------------------------------------------------------------------------------------------
-- Dances: a DANCE intent (the server checks it, starts the stock dance for everyone and tells the
-- Bleakhold clients which dance it is). Without a realm that knows dances, Bleakhold.exe dances here only.
------------------------------------------------------------------------------------------------------
A.DANCE_COOLDOWN = 1.25   -- s: the server's 1 s (BleakholdUi.Dance.CooldownMs) with a margin
A.danceReadyAt = 0

-- True when this game is Bleakhold.exe with the dance pack (BleakholdDance_* are its functions).
function A.CanShowDances()
    return BleakholdDance_Info ~= nil and BleakholdDance_Status ~= nil and BleakholdDance_Status() == ""
end

-- nil when a dance can be sent to the realm now (cooldown aside), else reason, text.
function A.DanceState()
    local Comm = ns.Comm
    if Comm.outdated then
        return "outdated", "Dances: your Bleakhold UI is out of date for this realm."
    end
    if not Comm.ready and not Comm.demo then
        return "offline", "Dances need the Bleakhold server module, and this realm has not answered (/bh status)."
    end
    if not Comm.ready and Comm.demo then
        return "demo", "Demo mode: no realm is connected, so only you see this dance."
    end
    if not Comm.HasFeature(Comm.FEATURE.DANCE) then
        return "off", "Dances are turned off on this realm."
    end
    return nil
end

-- 1 when the dance's music file is installed (Bleakhold.exe only), else nil.
function A.DanceHasMusic(entry)
    if not entry or not entry.dance or not BleakholdDance_Info then
        return nil
    end
    local key, seconds, bpm, music = BleakholdDance_Info(entry.dance)
    return key and music and 1 or nil
end

local noDanceClientNoted

-- Dances here only (Bleakhold.exe), when the realm cannot be asked. Returns true when it plays.
local function danceHere(entry)
    if BleakholdDance_PlayLocal and BleakholdDance_PlayLocal(entry.dance) then
        return true
    end
    if DoEmote then
        DoEmote("DANCE")
    end
    return false
end

-- Returns true when sent (or played here only), or false, reason.
function A.SendDance(entry)
    if type(entry) == "string" then
        entry = A.Get(entry) or A.DanceByName(entry)
    end
    if not entry or not entry.dance then
        return false, "not a dance"
    end
    local now = GetTime()
    if now < A.danceReadyAt then
        return false, "cooldown"
    end
    local reason, text = A.DanceState()
    if reason then
        A.EmojiNotice(text)
        A.danceReadyAt = now + A.DANCE_COOLDOWN
        if reason == "outdated" then
            return false, reason
        end
        danceHere(entry)
        return true, reason
    end
    local ok, err = ns.Comm.Send("DANCE", entry.dance)
    if not ok then
        A.EmojiNotice("Dances: could not send (" .. tostring(err) .. ").")
        return false, err
    end
    A.danceReadyAt = now + A.DANCE_COOLDOWN
    if not A.CanShowDances() and not noDanceClientNoted then
        noDanceClientNoted = true
        ns.Print("Your game cannot show Bleakhold dances (start it with Bleakhold.exe); others see yours.")
    end
    return true
end

function A.Perform(entry)
    if type(entry) == "string" then
        entry = A.Get(entry)
    end
    if entry and entry.emoji then
        return A.SendEmoji(entry)
    end
    if entry and entry.dance then
        return A.SendDance(entry)
    end
    if not entry or not entry.token or not DoEmote then
        return false
    end
    DoEmote(entry.token)
    return true
end

------------------------------------------------------------------------------------------------------
-- The Animations tab (built inside the Collections window)
------------------------------------------------------------------------------------------------------
local CO = ns.Collections
local body = CO.body
local BH = CO.BH

local tab = CreateFrame("Frame", nil, body)
tab:SetAllPoints(body)
tab:Hide()
A.tab = tab

local LEFT, TOP = 16, 14
local ENTRY_W, ENTRY_H, ENTRY_GAP = 270, 52, 6
local GRID_W = A.GRID_COLS * ENTRY_W + (A.GRID_COLS - 1) * 10
local RIGHT_X = LEFT + GRID_W + 18
local RIGHT_W = CO.BW - RIGHT_X - 16

-- Header row: the category in gold with the count ("Dances  12 of 12"), and the category filter.
tab.count = UI.Text(tab, 13, C.dim)
tab.count:SetPoint("TOPLEFT", tab, "TOPLEFT", LEFT, -TOP - 6)
local filterItems = { { value = "all", text = "All animations" } }
for _, c in ipairs(Data.animationCategories) do
    filterItems[#filterItems + 1] = { value = c.key, text = c.label }
end
filterItems[#filterItems + 1] = { value = "wheel", text = "On the wheel" }
tab.filter = UI.Dropdown(tab, 150, function(value)
    A.filter = value
    A.page = 1
    A.Refresh()
end)
tab.filter:SetItems(filterItems)
tab.filter:SetValue("all", true)
tab.filter:SetPoint("TOPRIGHT", tab, "TOPLEFT", LEFT + GRID_W, -TOP)

-- Grid of entries.
local HOW_EMOTE = "Click: preview. Double-click: play. Drag onto the wheel, or right-click to add it."
local HOW_EMOJI = "Click: preview. Double-click: show it above your head. Drag onto the wheel, or right-click to "
    .. "add it."

local function entryTooltip(self)
    local e = self.entry
    if e then
        local lines = { e.name, { e.cmd .. "  -  " .. A.CategoryLabel(e.cat), C.dim } }
        if A.OnWheel(e.key) then
            lines[#lines + 1] = { "On your emote wheel.", C.teal }
        end
        lines[#lines + 1] = e.emoji and HOW_EMOJI or HOW_EMOTE
        UI.ShowTooltip(self, lines)
    end
end

local function hideTooltip()
    if GameTooltip then
        GameTooltip:Hide()
    end
end

-- An animation in an action slot (ActionButtonTemplate's art on b, UI.SlotArt): the empty slot behind it, an emoji's
-- picture filling the slot, an emote's glyph a little smaller inside it (the glyphs reach their cell's edges). The
-- slot's light and check keep the slot's size whatever the picture's; setIcon sizes the picture.
local GLYPH_FILL = 0.72
local function emoteSlot(b, size)
    UI.SlotArt(b, size, true)
    b.icon.artSize, b.icon.glyphSize = size, floor(size * GLYPH_FILL + 0.5)
    for _, t in ipairs({ b.slotGlow, b.slotCheck }) do
        t:ClearAllPoints()
        t:SetSize(size, size)
        t:SetPoint("CENTER", b.icon, "CENTER", 0, 0)
    end
    return b.icon
end

-- The rows: the old window's dark rows (a 1 px edge), the animation in its slot, the name in white and the command
-- in grey; the chosen one in the nav row's blue (UI.Select); the stock check on the ones already on the wheel.
local ENTRY_SLOT = 36
tab.entries = {}
for i = 1, A.PAGE_SIZE do
    local b = CreateFrame("Button", nil, tab)
    b:SetSize(ENTRY_W, ENTRY_H)
    local col, row = (i - 1) % A.GRID_COLS, floor((i - 1) / A.GRID_COLS)
    b:SetPoint("TOPLEFT", tab, "TOPLEFT", LEFT + col * (ENTRY_W + 10), -TOP - 34 - row * (ENTRY_H + ENTRY_GAP))
    UI.Backdrop(b, C.card, C.border, nil, "edge")
    emoteSlot(b, ENTRY_SLOT)
    b.icon:SetPoint("CENTER", b, "LEFT", 8 + ENTRY_SLOT / 2, 0)
    b.name = UI.Text(b, 13, C.text)
    b.name:SetPoint("TOPLEFT", b, "TOPLEFT", 54, -10)
    UI.OneLine(b.name, ENTRY_W - 80)
    b.cmd = UI.Text(b, 11, C.mute)
    b.cmd:SetPoint("TOPLEFT", b.name, "BOTTOMLEFT", 0, -3)
    UI.OneLine(b.cmd, ENTRY_W - 80)
    b.mark = UI.Check(b, 18)
    b.mark:SetPoint("TOPRIGHT", b, "TOPRIGHT", -4, -4)
    b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    b:RegisterForDrag("LeftButton")
    b:SetScript("OnClick", function(self, button)
        if not self.entry then
            return
        end
        if button == "RightButton" then
            A.AddToWheel(self.entry.key)
        else
            A.Select(self.entry)
        end
    end)
    b:SetScript("OnDoubleClick", function(self)
        if self.entry then
            A.Select(self.entry)
            A.Perform(self.entry)
        end
    end)
    b:SetScript("OnDragStart", function(self)
        A.BeginDrag(self.entry)
    end)
    b:SetScript("OnDragStop", function()
        A.EndDrag()
    end)
    b:SetScript("OnEnter", entryTooltip)
    b:SetScript("OnLeave", hideTooltip)
    tab.entries[i] = b
end

-- Pager: the spellbook's page arrows with "Page 1 / 13" between them.
tab.prev = UI.PageButton(tab, "Prev")
tab.next = UI.PageButton(tab, "Next")
tab.pageText = UI.Text(tab, 12, C.text, "body", "CENTER")
tab.pageText:SetWidth(110)
local pagerY = -TOP - 34 - A.GRID_ROWS * (ENTRY_H + ENTRY_GAP) - 4
tab.pageText:SetPoint("TOP", tab, "TOPLEFT", LEFT + GRID_W / 2, pagerY - 5)
tab.prev:SetPoint("RIGHT", tab.pageText, "LEFT", -4, 0)
tab.next:SetPoint("LEFT", tab.pageText, "RIGHT", 4, 0)
tab.prev:SetScript("OnClick", function()
    A.SetPage(A.page - 1)
end)
tab.next:SetScript("OnClick", function()
    A.SetPage(A.page + 1)
end)
tab.empty = UI.Text(tab, 13, C.dim, "body", "CENTER")
tab.empty:SetPoint("TOP", tab, "TOPLEFT", LEFT + GRID_W / 2, -TOP - 140)
tab.empty:SetText("Nothing matches the search.")

-- Right column: preview, buttons, wheel editor.
local right = CreateFrame("Frame", nil, tab)
right:SetSize(RIGHT_W, BH - 2 * TOP)
right:SetPoint("TOPLEFT", tab, "TOPLEFT", RIGHT_X, -TOP)
tab.right = right

-- Fixed rows of the right column (y from its top).
local MODEL_H = 168
local Y_NAME, Y_CMD, Y_BUTTONS, Y_WHEEL_LABEL = -(MODEL_H + 10), -(MODEL_H + 35), -(MODEL_H + 55), -(MODEL_H + 97)
local EDIT_RADIUS, EDIT_SLOT = 62, 34
local editCenterY = Y_WHEEL_LABEL - 20 - EDIT_RADIUS - EDIT_SLOT / 2

local modelBox = UI.Box(right, RIGHT_W, MODEL_H, C.card, C.border, nil, "edge")
modelBox:SetPoint("TOPLEFT", right, "TOPLEFT", 0, 0)
local model = CreateFrame("PlayerModel", "BleakholdAnimationModel", modelBox)
model:SetPoint("TOPLEFT", modelBox, "TOPLEFT", 1, -1)
model:SetPoint("BOTTOMRIGHT", modelBox, "BOTTOMRIGHT", -1, 1)
model:EnableMouse(true)
model:SetScript("OnMouseDown", function(self)
    self.turning = true
    self.lastX = GetCursorPosition()
end)
model:SetScript("OnMouseUp", function(self)
    self.turning = false
end)
model:SetScript("OnUpdate", function(self)
    if self.turning then
        local x = GetCursorPosition()
        if x and self.lastX then
            self:SetFacing((self:GetFacing() or 0) + (x - self.lastX) * 0.02)
            self.lastX = x
        end
    end
end)
A.model = model

-- Emoji preview: the emoji pops up over the model's head the way the bubble does in the game (the same
-- timings as BleakholdEmojiPose in WoW/Common/BleakholdEmoji.h, in seconds).
local EMOJI_SIZE = 112
local emojiPreview = CreateFrame("Frame", nil, modelBox)
emojiPreview:SetAllPoints(modelBox)
emojiPreview:SetFrameLevel(model:GetFrameLevel() + 2)
emojiPreview.tex = emojiPreview:CreateTexture(nil, "OVERLAY")
emojiPreview.tex:SetPoint("CENTER", modelBox, "TOP", 0, -8 - EMOJI_SIZE / 2)   -- grows from its centre
emojiPreview.tex:SetSize(EMOJI_SIZE, EMOJI_SIZE)
emojiPreview:Hide()
A.emojiPreview = emojiPreview

A.EMOJI_POP, A.EMOJI_SETTLE, A.EMOJI_POP_SCALE = 0.12, 0.25, 1.25

-- Size of the popping emoji (fraction of its full size) t seconds after it appears.
function A.EmojiPop(t)
    t = max(0, t or 0)
    if t < A.EMOJI_POP then
        local u = 1 - t / A.EMOJI_POP
        return A.EMOJI_POP_SCALE * (1 - u * u)
    elseif t < A.EMOJI_SETTLE then
        local s = (t - A.EMOJI_POP) / (A.EMOJI_SETTLE - A.EMOJI_POP)
        return A.EMOJI_POP_SCALE - (A.EMOJI_POP_SCALE - 1) * s * s * (3 - 2 * s)
    end
    return 1
end

local function popUpdate(self)
    local t = GetTime() - self.popStart
    local size = EMOJI_SIZE
    if t >= A.EMOJI_SETTLE then
        self:SetScript("OnUpdate", nil)
    else
        size = max(1, EMOJI_SIZE * A.EmojiPop(t))
    end
    self.tex:SetSize(size, size)
end

function A.PopEmojiPreview()
    emojiPreview.popStart = GetTime()
    emojiPreview.tex:SetSize(1, 1)
    emojiPreview:SetScript("OnUpdate", popUpdate)
end

right.name = UI.Text(right, 18, C.gold)
right.name:SetPoint("TOPLEFT", right, "TOPLEFT", 0, Y_NAME)
UI.OneLine(right.name, RIGHT_W)
right.cmd = UI.Text(right, 11, C.dim)
right.cmd:SetPoint("TOPLEFT", right, "TOPLEFT", 0, Y_CMD)
UI.OneLine(right.cmd, RIGHT_W)
right.play = UI.Button(right, (RIGHT_W - 8) / 2, 24, "Play", "gold")
right.play:SetPoint("TOPLEFT", right, "TOPLEFT", 0, Y_BUTTONS)
right.add = UI.Button(right, (RIGHT_W - 8) / 2, 24, "Add to Wheel", "dark")
right.add:SetPoint("TOPRIGHT", right, "TOPRIGHT", 0, Y_BUTTONS)
right.play:SetScript("OnClick", function()
    A.Perform(A.selected)
end)
right.add:SetScript("OnClick", function()
    if A.selected then
        A.AddToWheel(A.selected.key)
    end
end)

right.wheelLabel = UI.Heading(right, "Emote Wheel")
right.wheelLabel:SetPoint("TOPLEFT", right, "TOPLEFT", 0, Y_WHEEL_LABEL)

-- The wheel's page as the wheel itself draws it (below): minimap-button rings round a dark round plate (the
-- minimap button's own disc), the page number in the middle.
local editor = CreateFrame("Frame", nil, right)
editor:SetSize(2 * (EDIT_RADIUS + EDIT_SLOT), 2 * (EDIT_RADIUS + EDIT_SLOT))
editor:SetPoint("CENTER", right, "TOPLEFT", RIGHT_W / 2, editCenterY)
editor.plate = editor:CreateTexture(nil, "BACKGROUND")
editor.plate:SetTexture(UI.STOCK.ringBg)
editor.plate:SetSize(2 * EDIT_RADIUS + EDIT_SLOT + 24, 2 * EDIT_RADIUS + EDIT_SLOT + 24)
editor.plate:SetPoint("CENTER")
editor.plate:SetAlpha(0.8)
editor.pageText = UI.Text(editor, 13, C.text, "body", "CENTER")
editor.pageText:SetPoint("CENTER", editor, "CENTER", 0, 0)
right.editor = editor

-- A wheel slot: a ring portrait (MiniMap-TrackingBorder round the minimap button's disc) with the animation's
-- picture in it, and the minimap button's light (UI-Common-MouseHilight, added) when it is pointed at or chosen;
-- an empty slot's ring is greyed. f:SetLit(on), f:SetFilled(on).
local function wheelSlot(f, size, iconSize)
    f.badge = UI.Badge(f, size)
    f.badge:SetPoint("CENTER", f, "CENTER", 0, 0)
    f.icon = f.badge:CreateTexture(nil, "ARTWORK")
    f.icon:SetSize(iconSize, iconSize)
    f.icon:SetPoint("CENTER", f.badge, "CENTER", 0, 0)
    f.glow = f.badge:CreateTexture(nil, "OVERLAY")
    f.glow:SetTexture(UI.STOCK.arrowHighlight)
    f.glow:SetBlendMode("ADD")
    f.glow:SetSize(size * 1.2, size * 1.2)
    f.glow:SetPoint("CENTER", f.badge, "CENTER", 1, 0)
    f.glow:Hide()
    function f:SetLit(on)
        if on then
            self.glow:Show()
        else
            self.glow:Hide()
        end
        self.lit = on and true or false
    end
    function f:SetFilled(on)
        self.badge.ring:SetDesaturated(not on)
        self.badge.ring:SetAlpha(on and 1 or 0.6)
    end
    return f
end

-- Slot positions: slot 1 at the top, then clockwise.
local function slotOffset(slot, radius)
    local a = math.rad(90 - (slot - 1) * 360 / A.WHEEL_SLOTS)
    return math.cos(a) * radius, math.sin(a) * radius
end
A.SlotOffset = slotOffset

editor.slots = {}
for s = 1, A.WHEEL_SLOTS do
    local b = CreateFrame("Button", nil, editor)
    b:SetSize(EDIT_SLOT, EDIT_SLOT)
    local x, y = slotOffset(s, EDIT_RADIUS)
    b:SetPoint("CENTER", editor, "CENTER", x, y)
    wheelSlot(b, EDIT_SLOT, 22)
    b.slot = s
    b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    b:SetScript("OnClick", function(self, button)
        local e = A.WheelEntry(A.wheelPage, self.slot)
        if button == "RightButton" then
            A.SetWheelSlot(A.wheelPage, self.slot, nil)
        elseif e then
            A.Select(e)
        elseif A.selected then
            A.SetWheelSlot(A.wheelPage, self.slot, A.selected.key)
        end
    end)
    b:SetScript("OnEnter", function(self)
        self.hovered = true
        self.glow:Show()
        local e = A.WheelEntry(A.wheelPage, self.slot)
        if e then
            UI.ShowTooltip(self, { e.name, { e.cmd, C.dim }, "Click: preview. Right-click: empty the slot." })
        else
            UI.ShowTooltip(self, { "Empty slot", "Drag an animation here, or click to put the selected one in it." })
        end
    end)
    b:SetScript("OnLeave", function(self)
        self.hovered = false
        self:SetLit(self.lit)
        hideTooltip()
    end)
    editor.slots[s] = b
end
editor.prev = UI.PageButton(right, "Prev")
editor.prev:SetPoint("CENTER", right, "TOPLEFT", 16, editCenterY)
editor.next = UI.PageButton(right, "Next")
editor.next:SetPoint("CENTER", right, "TOPLEFT", RIGHT_W - 16, editCenterY)
editor.prev:SetScript("OnClick", function()
    A.SetWheelPage(A.wheelPage - 1)
end)
editor.next:SetScript("OnClick", function()
    A.SetWheelPage(A.wheelPage + 1)
end)

right.hint = UI.Text(right, 11, C.mute, "body", "CENTER")
right.hint:SetPoint("BOTTOM", right, "BOTTOM", 0, 0)
right.hint:SetWidth(RIGHT_W)

-- Icons: an emoji shows its own art; an emote, or an emoji whose art is missing (stock Wow.exe does not
-- read the loose files in Data\Interface\Bleakhold\Emoji, or only the AddOns folder was installed),
-- shows its glyph. SetTexture fails without changing the texture, and SetEmoteGlyph sets both the
-- texture and the coords, so a reused icon never keeps the previous emoji. A path that failed once is
-- not tried again.
local artMissing = {}

local function setArt(texture, path)
    if artMissing[path] then
        return false
    end
    if texture:SetTexture(path) then
        return true
    end
    artMissing[path] = true
    return false
end

local function setIcon(texture, entry, color)
    if entry and entry.texture and setArt(texture, entry.texture) then
        texture:SetTexCoord(0, 1, 0, 1)
        texture:SetVertexColor(1, 1, 1, 1)
        if texture.artSize then
            texture:SetSize(texture.artSize, texture.artSize)
        end
        return
    end
    UI.SetEmoteGlyph(texture, entry and entry.glyph or "plus")
    texture:SetVertexColor(UI.Rgb(color or (entry and C.goldLight or C.mute)))
    if texture.glyphSize then
        texture:SetSize(texture.glyphSize, texture.glyphSize)
    end
end
A.SetIcon = setIcon

-- Drag and drop onto the wheel editor: the animation's slot follows the cursor, as a dragged action does;
-- releasing over a slot fills it.
local dragIcon = CreateFrame("Frame", "BleakholdAnimationDrag", UIParent)
dragIcon:SetSize(ENTRY_SLOT, ENTRY_SLOT)
dragIcon:SetFrameStrata("TOOLTIP")
dragIcon:Hide()
emoteSlot(dragIcon, ENTRY_SLOT)
dragIcon.icon:SetPoint("CENTER", dragIcon, "CENTER", 0, 0)
dragIcon:SetScript("OnUpdate", function(self)
    local x, y = GetCursorPosition()
    local s = UIParent:GetEffectiveScale()
    self:ClearAllPoints()
    self:SetPoint("CENTER", UIParent, "BOTTOMLEFT", x / s, y / s)
end)

function A.BeginDrag(entry)
    if not entry then
        return
    end
    A.dragging = entry
    setIcon(dragIcon.icon, entry, C.goldLight)
    dragIcon:Show()
end

function A.EndDrag()
    local entry = A.dragging
    A.dragging = nil
    dragIcon:Hide()
    if not entry then
        return
    end
    for s, b in ipairs(editor.slots) do
        if b:IsVisible() and b:IsMouseOver() then
            A.SetWheelSlot(A.wheelPage, s, entry.key)
            return
        end
    end
end

------------------------------------------------------------------------------------------------------
-- Tab logic
------------------------------------------------------------------------------------------------------
function A.Pages(count)
    return max(1, floor((count + A.PAGE_SIZE - 1) / A.PAGE_SIZE))
end

function A.SetPage(page)
    local list = A.Filtered(CO.search, A.filter)
    A.page = U.Clamp(page, 1, A.Pages(#list))
    A.Refresh()
end

function A.SetWheelPage(page)
    A.wheelPage = (page - 1) % A.WHEEL_PAGES + 1
    A.Refresh()
end

-- The model is loaded after SetUnit returns, so the sequence is set again once it has had time to load.
local previewTimer

local function previewEmoji(entry)
    local tex = emojiPreview.tex
    if entry and entry.emoji then
        if setArt(tex, entry.texture) then
            emojiPreview:Show()
            A.PopEmojiPreview()
            return
        end
        tex:SetTexture(nil)    -- missing art: no stale emoji left behind
    end
    emojiPreview:SetScript("OnUpdate", nil)
    emojiPreview:Hide()
end

-- A Bleakhold dance on the preview model (Bleakhold.exe's model:SetBleakholdDance); true when it plays.
local function previewDance(entry)
    if not model.SetBleakholdDance then
        return false
    end
    return model:SetBleakholdDance(entry and entry.dance or nil) and true or false
end

function A.Preview(entry)
    model:SetUnit("player")
    model:SetFacing(0)
    previewEmoji(entry)
    ns.Cancel(previewTimer)
    if not entry then
        previewDance(nil)
        return
    end
    -- a dance without Bleakhold.exe (or before the model exists) shows the race's own dance
    local anim = U.Clamp(entry.anim or (entry.dance and 69) or 0, 0, 505)
    local dancing = entry.dance and previewDance(entry)
    if not entry.dance then
        previewDance(nil)
    end
    model:SetSequence(dancing and 0 or anim)
    previewTimer = ns.After(0.3, function()
        if A.selected == entry then
            if entry.dance and not dancing then
                dancing = previewDance(entry)
            end
            model:SetSequence(dancing and 0 or anim)
        end
    end)
end

function A.Select(entry)
    A.selected = entry
    A.Preview(entry)
    A.Refresh()
end

function A.RefreshWheelEditor()
    for s, b in ipairs(editor.slots) do
        local e = A.WheelEntry(A.wheelPage, s)
        setIcon(b.icon, e)
        local on = e and A.selected and e.key == A.selected.key
        b:SetFilled(e ~= nil)
        b:SetLit(on)
        if b.hovered then
            b.glow:Show()
        end
    end
    editor.pageText:SetText(A.wheelPage .. " / " .. A.WHEEL_PAGES)
end

function A.KeyText()
    local key = GetBindingKey and GetBindingKey(A.BINDING)
    return key
end

function A.Refresh()
    if not tab:IsShown() then
        return
    end
    local list = A.Filtered(CO.search, A.filter)
    local pages = A.Pages(#list)
    A.page = U.Clamp(A.page, 1, pages)
    local total = #A.Filtered("", A.filter)
    tab.count:SetText("|cffFFD100" .. A.CategoryLabel(A.filter ~= "all" and A.filter ~= "wheel" and A.filter or nil)
        .. "|r  |cffFFFFFF" .. #list .. "|r of " .. total)
    local first = (A.page - 1) * A.PAGE_SIZE
    for i, b in ipairs(tab.entries) do
        local e = list[first + i]
        b.entry = e
        if e then
            setIcon(b.icon, e)
            UI.SetText(b.name, e.name)
            UI.SetText(b.cmd, e.dance and A.DanceHasMusic(e) and (e.cmd .. "  with music") or e.cmd)
            local sel = A.selected and A.selected.key == e.key
            UI.Select(b, sel)
            UI.SetColor(b.name, sel and C.gold or C.text)
            if A.OnWheel(e.key) then
                b.mark:Show()
            else
                b.mark:Hide()
            end
            b:Show()
        else
            b:Hide()
        end
    end
    if #list == 0 then
        tab.empty:Show()
    else
        tab.empty:Hide()
    end
    tab.pageText:SetText("Page " .. A.page .. " / " .. pages)
    tab.prev:SetActive(A.page > 1)
    tab.next:SetActive(A.page < pages)

    local sel = A.selected
    if sel and sel.dance then
        UI.SetText(right.name, sel.name)
        UI.SetText(right.cmd, sel.cmd .. (A.DanceHasMusic(sel) and "  with music" or "") .. "  -  "
            .. string.format("%g BPM, %.1f s loop", sel.bpm or 0, sel.seconds or 0))
    elseif sel then
        UI.SetText(right.name, sel.name)
        UI.SetText(right.cmd, sel.cmd .. "  -  " .. A.CategoryLabel(sel.cat) .. (sel.text and ("  -  " .. sel.text) or ""))
    else
        right.name:SetText("Animations")
        right.cmd:SetText("Pick an animation to preview it.")
    end
    right.play:SetLabel(sel and sel.dance and "Dance" or (sel and sel.emoji and "Show" or "Play"))
    right.play:SetActive(sel ~= nil)
    right.add:SetActive(sel ~= nil and not A.OnWheel(sel.key))
    A.RefreshWheelEditor()
    local hint = sel and sel.emoji and select(2, A.EmojiState())
    if not hint and sel and sel.dance then
        -- without a realm the dance still plays here; only a realm that refuses dances is worth the hint
        local reason, text = A.DanceState()
        hint = (reason == "off" or reason == "outdated") and text or nil
    end
    if not hint then
        local key = A.KeyText()
        hint = key and ("Hold " .. key .. " in the game to use the wheel.")
            or "Bind a key to the emote wheel in Key Bindings, Bleakhold."
    end
    right.hint:SetText(hint)
end

-- Called by the Collections window when the tab is shown.
function A.ShowTab()
    tab:Show()
    if not A.selected then
        A.selected = A.List()[1]
        A.Preview(A.selected)
    end
    A.Refresh()
end

function A.HideTab()
    tab:Hide()
    A.EndDrag()
end

ns.On("WHEEL", function()
    A.Refresh()
    if A.wheel and A.wheel:IsShown() then
        A.RefreshWheel(true)
    end
end)

-- The realm's answer decides whether emojis can be sent (the hint under the wheel editor).
ns.On("HELLO", function()
    A.Refresh()
end)
ns.On("OUTDATED", function()
    A.Refresh()
end)

------------------------------------------------------------------------------------------------------
-- The emote wheel
------------------------------------------------------------------------------------------------------
local WHEEL_SIZE, WHEEL_RADIUS, WHEEL_SLOT = 330, 118, 58

local wheel = CreateFrame("Frame", "BleakholdEmoteWheelFrame", UIParent)
wheel:SetSize(WHEEL_SIZE, WHEEL_SIZE)
wheel:SetFrameStrata("DIALOG")
wheel:SetClampedToScreen(true)
wheel:EnableMouse(true)
wheel:EnableMouseWheel(true)
wheel:Hide()
A.wheel = wheel
UISpecialFrames[#UISpecialFrames + 1] = "BleakholdEmoteWheelFrame"

-- Stock materials in the wheel's round layout: the minimap button's dark disc as the plate (a darker one in the
-- middle, where no slot is chosen), and the slots as minimap-button rings (wheelSlot above).
wheel.bg = wheel:CreateTexture(nil, "BACKGROUND")
wheel.bg:SetTexture(UI.STOCK.ringBg)
wheel.bg:SetSize(WHEEL_SIZE, WHEEL_SIZE)
wheel.bg:SetPoint("CENTER")
wheel.bg:SetAlpha(0.78)
wheel.inner = wheel:CreateTexture(nil, "BORDER")
wheel.inner:SetTexture(UI.STOCK.ringBg)
wheel.inner:SetSize(2 * A.DEAD_ZONE + 56, 2 * A.DEAD_ZONE + 56)
wheel.inner:SetPoint("CENTER")
wheel.inner:SetAlpha(0.7)
wheel.title = UI.Text(wheel, 15, C.gold, "body", "CENTER")
wheel.title:SetPoint("CENTER", wheel, "CENTER", 0, 8)
wheel.title:SetWidth(110)
wheel.pageText = UI.Text(wheel, 11, C.dim, "body", "CENTER")
wheel.pageText:SetPoint("TOP", wheel.title, "BOTTOM", 0, -4)
wheel.hint = UI.Text(wheel, 11, C.mid, "body", "CENTER")
wheel.hint:SetPoint("TOP", wheel, "BOTTOM", 0, -6)
wheel.hint:SetWidth(WHEEL_SIZE + 80)
wheel.hint:SetText("Release or click to play  -  Mouse wheel: next page  -  Right-click: close")

wheel.slots = {}
for s = 1, A.WHEEL_SLOTS do
    local f = CreateFrame("Frame", nil, wheel)
    f:SetSize(WHEEL_SLOT, WHEEL_SLOT)
    local x, y = slotOffset(s, WHEEL_RADIUS)
    f:SetPoint("CENTER", wheel, "CENTER", x, y)
    wheelSlot(f, WHEEL_SLOT, 36)
    f.name = UI.Text(f, 11, C.text, "body", "CENTER")
    f.name:SetPoint("TOP", f, "BOTTOM", 0, -2)
    UI.OneLine(f.name, 90)
    wheel.slots[s] = f
end

-- The slot the cursor points at (direction from the centre, outside the dead zone), or nil.
function A.HoveredSlot()
    local x, y = GetCursorPosition()
    local scale = wheel:GetEffectiveScale()
    local cx, cy = wheel:GetCenter()
    if not x or not cx or not scale or scale <= 0 then
        return nil
    end
    local dx, dy = x / scale - cx, y / scale - cy
    if sqrt(dx * dx + dy * dy) < A.DEAD_ZONE then
        return nil
    end
    local clockwise = (90 - deg(atan2(dy, dx))) % 360
    return floor((clockwise + 180 / A.WHEEL_SLOTS) / (360 / A.WHEEL_SLOTS)) % A.WHEEL_SLOTS + 1
end

-- Runs every frame while the wheel is open; redraws only when the hovered slot or the page changed.
local drawn = {}

function A.RefreshWheel(force)
    local hovered = A.HoveredSlot()
    local hoveredEntry = hovered and A.WheelEntry(A.wheelPage, hovered)
    if not hoveredEntry then
        hovered = nil
    end
    A.hovered = hovered
    if not force and drawn.hovered == hovered and drawn.page == A.wheelPage then
        return
    end
    drawn.hovered, drawn.page = hovered, A.wheelPage
    for s, f in ipairs(wheel.slots) do
        local e = A.WheelEntry(A.wheelPage, s)
        local on = hoveredEntry and s == hovered
        setIcon(f.icon, e)
        f:SetFilled(e ~= nil)
        f:SetLit(on)
        UI.SetText(f.name, e and e.name or "")
        UI.SetColor(f.name, on and C.gold or C.text)
    end
    UI.SetText(wheel.title, hoveredEntry and hoveredEntry.name or "Emotes")
    wheel.pageText:SetText("Page " .. A.wheelPage .. " / " .. A.WHEEL_PAGES)
end

local function placeAtCursor()
    local x, y = GetCursorPosition()
    local s = UIParent:GetEffectiveScale()
    wheel:ClearAllPoints()
    if x and s and s > 0 then
        wheel:SetPoint("CENTER", UIParent, "BOTTOMLEFT", x / s, y / s)
    else
        wheel:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
    end
end

function A.OpenWheel(held)
    A.wheelHeld = held and true or false
    A.wheelOpenedAt = GetTime()
    placeAtCursor()
    wheel:Show()
    A.RefreshWheel(true)
end

function A.CloseWheel()
    A.wheelHeld = false
    wheel:Hide()
end

-- Plays the slot the cursor points at, then closes. Returns the entry played.
function A.ReleaseWheel()
    A.RefreshWheel()
    local entry = A.hovered and A.WheelEntry(A.wheelPage, A.hovered)
    A.CloseWheel()
    if entry then
        A.Perform(entry)
    end
    return entry
end

-- Key binding: hold to choose and release to play; a short tap keeps the wheel open for clicking, and
-- pressing the key again closes it.
function A.WheelKey(keystate)
    if keystate == "up" then
        if not wheel:IsShown() or not A.wheelHeld then
            return
        end
        A.wheelHeld = false
        A.RefreshWheel()
        if GetTime() - (A.wheelOpenedAt or 0) < A.TAP_SECONDS and not A.hovered then
            return
        end
        A.ReleaseWheel()
        return
    end
    if wheel:IsShown() then
        A.CloseWheel()
    else
        A.OpenWheel(true)
    end
end

function BleakholdEmoteWheel(keystate)
    ns.SafeCall(A.WheelKey, keystate)
end

wheel:SetScript("OnUpdate", function()
    A.RefreshWheel()
end)
wheel:SetScript("OnMouseUp", function(self, button)
    if button == "RightButton" then
        A.CloseWheel()
    else
        A.ReleaseWheel()
    end
end)
wheel:SetScript("OnMouseWheel", function(self, delta)
    A.wheelPage = ((A.wheelPage - 1) + (delta and delta < 0 and 1 or -1)) % A.WHEEL_PAGES + 1
    A.RefreshWheel(true)
end)
wheel:SetScript("OnHide", function()
    A.wheelHeld = false
end)

------------------------------------------------------------------------------------------------------
-- Default key: Ctrl+G, once per account, only when neither the key nor the action is bound yet.
------------------------------------------------------------------------------------------------------
function A.OfferDefaultKey()
    local opts = ns.db.options
    if opts.wheelKeyOffered or not SetBinding or not GetBindingAction then
        return
    end
    if InCombatLockdown and InCombatLockdown() then
        return
    end
    opts.wheelKeyOffered = true
    if GetBindingKey(A.BINDING) then
        return
    end
    local current = GetBindingAction(A.DEFAULT_KEY)
    if current == nil or current == "" then
        if SetBinding(A.DEFAULT_KEY, A.BINDING) and SaveBindings and GetCurrentBindingSet then
            SaveBindings(GetCurrentBindingSet())
        end
    else
        ns.Print("Emote wheel: " .. A.DEFAULT_KEY .. " is taken; bind a key in Key Bindings, Bleakhold.")
    end
end

-- After entering the world the saved key bindings are in place.
ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    ns.After(1, A.OfferDefaultKey)
end)

------------------------------------------------------------------------------------------------------
-- Commands and openers
------------------------------------------------------------------------------------------------------
UI.RegisterOpener("animations", function(toggle)
    if toggle and CO.frame:IsShown() and CO.tab == "animations" then
        CO.frame:Hide()
        return
    end
    CO.ShowTab("animations")
end)

ns.AddCommand("animations", "open the Animations collection", function()
    UI.Open("animations", true)
end)

ns.AddCommand("wheel", "open the emote wheel", function()
    if wheel:IsShown() then
        A.CloseWheel()
    else
        A.OpenWheel(false)
    end
end)

ns.AddCommand("emote", "play an animation: /bh emote <name>", function(args)
    local want = string.lower(strtrim and strtrim(args or "") or (args or "")):gsub("^/", "")
    for _, e in ipairs(A.List()) do
        if not e.emoji and (e.key == want or string.lower(e.name) == want or e.cmd == "/" .. want) then
            A.Perform(e)
            return
        end
    end
    ns.Print("usage: /bh emote <name>, for example /bh emote dance")
end)

A.LIST_LINE = 240         -- /bh emoji list: longest line printed

ns.AddCommand("dance", "dance a Bleakhold dance: /bh dance <name>", function(args)
    local want = strtrim(args or "")
    local lower = string.lower(want)
    if lower == "list" then
        ns.Print(#dances .. " dances (/bh dance <name>, or each dance's own command):")
        local line = ""
        for _, e in ipairs(dances) do
            local item = e.cmd
            if line ~= "" and #line + 1 + #item > A.LIST_LINE then
                ns.Print(line)
                line = ""
            end
            line = line == "" and item or (line .. " " .. item)
        end
        if line ~= "" then
            ns.Print(line)
        end
        return
    end
    if lower == "stop" then
        if BleakholdDance_StopLocal then
            BleakholdDance_StopLocal()
        end
        ns.Print("Move or turn to stop dancing.")
        return
    end
    if lower == "debug" then
        if not BleakholdDance_Status then
            ns.Print("Dances: this game is not Bleakhold.exe.")
            return
        end
        local pack = BleakholdDance_Status()
        local rig = BleakholdDance_RigStatus and BleakholdDance_RigStatus() or ""
        ns.Print("Dances: pack " .. (pack == "" and "ok" or pack) .. "; your model " .. (rig == "" and "can dance" or rig)
            .. "; realm " .. (select(2, A.DanceState()) or "ok") .. ".")
        return
    end
    local entry = want ~= "" and A.DanceByName(want:gsub("^/", ""))
    if entry then
        A.SendDance(entry)
        return
    end
    ns.Print("usage: /bh dance <name>, for example /bh dance string swing (/bh dance list shows them all)")
end)

-- Every dance's own slash command (/stringswing), unless another addon took it first.
A.danceCommands = {}
for _, e in ipairs(dances) do
    local id = "BLEAKHOLDDANCE" .. string.upper(e.danceKey)
    local taken = false
    for name, fn in pairs(SlashCmdList) do
        local i = 1
        while _G["SLASH_" .. name .. i] do
            if string.lower(_G["SLASH_" .. name .. i]) == e.cmd then
                taken = true
            end
            i = i + 1
        end
    end
    if not taken then
        _G["SLASH_" .. id .. "1"] = e.cmd
        SlashCmdList[id] = function()
            A.SendDance(e)
        end
        A.danceCommands[#A.danceCommands + 1] = e.cmd
    end
end

ns.AddCommand("emoji", "show an emoji above your head: /bh emoji <name>", function(args)
    local want = strtrim(args or "")
    if string.lower(want) == "list" then
        ns.Print(#emojis .. " emojis, by key (/bh emoji <key>):")
        local line = ""
        for _, e in ipairs(emojis) do
            if line ~= "" and #line + 1 + #e.emojiKey > A.LIST_LINE then
                ns.Print(line)
                line = ""
            end
            line = line == "" and e.emojiKey or (line .. " " .. e.emojiKey)
        end
        if line ~= "" then
            ns.Print(line)
        end
        return
    end
    local entry = want ~= "" and A.EmojiByName(want)
    if entry then
        A.SendEmoji(entry)
        return
    end
    ns.Print("usage: /bh emoji <name>, for example /bh emoji joy (/bh emoji list shows them all)")
end)

-- The emojiBubbles CVar exists only in Bleakhold.exe (SetCVar of an unknown CVar is a Lua error).
ns.AddCommand("emojis", "emoji bubbles over characters: /bh emojis on|off", function(args)
    local value = GetCVar("emojiBubbles")
    if value == nil then
        ns.Print("Your game cannot draw emoji bubbles: start it with Bleakhold.exe.")
        return
    end
    local want = string.lower(strtrim(args or ""))
    if want == "on" then
        SetCVar("emojiBubbles", "1")
        ns.Print("Emoji bubbles are shown.")
    elseif want == "off" then
        SetCVar("emojiBubbles", "0")
        ns.Print("Emoji bubbles are hidden (yours too); others still see the ones you send.")
    else
        ns.Print("Emoji bubbles are " .. (tonumber(value) == 0 and "off" or "on") .. ". /bh emojis on|off")
    end
end)
