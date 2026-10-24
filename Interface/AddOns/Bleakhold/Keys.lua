-- Bleakhold: Activities - Keys. The player's keystone, the Mythic 0 to +15 ladder, weekly caches and
-- a dungeon mode selector. The mode is an intent (KMODE) the server applies: the protected portrait
-- Dungeon Difficulty menu is left alone, and nothing here touches UnitPopup menus.
local ADDON, ns = ...
local U, UI, Comm, Data = ns.U, ns.UI, ns.Comm, ns.Data
local C = UI.C
local S = ns.S
local A = ns.Activities

local floor, max, min = math.floor, math.max, math.min

local P = A.NewPage()
A.AddPage("keys", P)
ns.Keys = P

local LEFT = 420
local RIGHT = A.PW - LEFT - 14

------------------------------------------------------------------------------------------------------
-- Keystone card
------------------------------------------------------------------------------------------------------
local card = UI.Box(P, LEFT, 196, C.eraBg, C.eraBorder)
card:SetPoint("TOPLEFT", P, "TOPLEFT", 0, 0)
card.badge = UI.Badge(card, 58, "key", C.active, C.gold)
card.badge:SetPoint("TOPLEFT", card, "TOPLEFT", 16, -16)
card.label = UI.Text(card, 11, C.dim)
card.label:SetPoint("TOPLEFT", card, "TOPLEFT", 88, -18)
card.label:SetText("YOUR KEYSTONE")
card.name = UI.Text(card, 22, C.goldPale, "title")
card.name:SetPoint("TOPLEFT", card.label, "BOTTOMLEFT", 0, -4)
UI.OneLine(card.name, LEFT - 100)
card.text = UI.Text(card, 12, C.mid)
card.text:SetPoint("TOPLEFT", card.name, "BOTTOMLEFT", 0, -4)
card.text:SetWidth(LEFT - 100)
card.text:SetJustifyV("TOP")
card.text:SetHeight(32)
card.pills = {}
for i = 1, 5 do
    local p = UI.Pill(card, "", "2E2638", C.eraBorder, C.text, 11)
    p:Hide()
    card.pills[i] = p
end
card.best = UI.Text(card, 12, C.dim)
card.best:SetPoint("BOTTOMLEFT", card, "BOTTOMLEFT", 16, 14)
P.card = card

-- Mode selector
local modeBox = UI.Box(P, LEFT, 118, C.card, C.border)
modeBox:SetPoint("TOPLEFT", card, "BOTTOMLEFT", 0, -12)
modeBox.label = UI.Text(modeBox, 11, C.dim)
modeBox.label:SetPoint("TOPLEFT", modeBox, "TOPLEFT", 12, -12)
modeBox.label:SetText("DUNGEON MODE")
modeBox.buttons = {}
for i = 0, 2 do
    local b = UI.Button(modeBox, 120, 28, Data.keyModes[i], "tab", 13)
    b:SetPoint("TOPLEFT", modeBox, "TOPLEFT", 12 + i * 130, -32)
    b:SetScript("OnClick", function()
        Comm.Send("KMODE", i)
    end)
    modeBox.buttons[i] = b
end
modeBox.note = UI.Text(modeBox, 11, C.dim)
modeBox.note:SetPoint("TOPLEFT", modeBox, "TOPLEFT", 12, -70)
modeBox.note:SetWidth(LEFT - 24)
modeBox.note:SetText("Sets the mode of the next dungeon you enter. Mythic uses your keystone; the server confirms the change.")
P.modeBox = modeBox

-- Start / cancel
P.start = UI.Button(P, 200, 36, "Start keystone", "gold", 14)
P.start:SetPoint("TOPLEFT", modeBox, "BOTTOMLEFT", 0, -12)
P.start:SetScript("OnClick", function()
    Comm.Send("KSTART")
end)
P.start.tooltip = function()
    return { "Start keystone", "Starts the countdown for your group inside the dungeon. The server checks the key, the group and where you are." }
end
P.cancel = UI.Button(P, 200, 36, "Cancel countdown", "dark", 14)
P.cancel:SetPoint("LEFT", P.start, "RIGHT", 20, 0)
P.cancel:SetScript("OnClick", function()
    Comm.Send("KCANCEL")
end)

------------------------------------------------------------------------------------------------------
-- Weekly caches and the level ladder
------------------------------------------------------------------------------------------------------
local caches = UI.Box(P, RIGHT, 96, C.card, C.border)
caches:SetPoint("TOPRIGHT", P, "TOPRIGHT", 0, 0)
caches.label = UI.Text(caches, 11, C.dim)
caches.label:SetPoint("TOPLEFT", caches, "TOPLEFT", 12, -12)
caches.label:SetText("WEEKLY CACHES")
caches.icon = UI.Badge(caches, 40, "chest", C.chip, C.gold)
caches.icon:SetPoint("TOPLEFT", caches, "TOPLEFT", 12, -32)
caches.ready = UI.Text(caches, 15, C.text)
caches.ready:SetPoint("TOPLEFT", caches.icon, "TOPRIGHT", 12, -2)
caches.banked = UI.Text(caches, 12, C.dim)
caches.banked:SetPoint("TOPLEFT", caches.ready, "BOTTOMLEFT", 0, -4)
UI.OneLine(caches.banked, RIGHT - 76)
P.caches = caches

local ladder = UI.Box(P, RIGHT, A.PH - 108, C.card, C.border)
ladder:SetPoint("TOPRIGHT", caches, "BOTTOMRIGHT", 0, -12)
ladder.label = UI.Text(ladder, 11, C.dim)
ladder.label:SetPoint("TOPLEFT", ladder, "TOPLEFT", 12, -12)
ladder.label:SetText("MYTHIC 0 TO +15")
ladder.rows = {}
for i = 1, 8 do
    local lv = UI.Text(ladder, 14, C.goldLight, "title")
    lv:SetPoint("TOPLEFT", ladder, "TOPLEFT", 12, -34 - (i - 1) * 36)
    lv:SetWidth(70)
    local tx = UI.Text(ladder, 11, C.mid)
    tx:SetPoint("TOPLEFT", ladder, "TOPLEFT", 86, -34 - (i - 1) * 36)
    tx:SetWidth(RIGHT - 98)
    tx:SetJustifyV("TOP")
    tx:SetHeight(32)
    ladder.rows[i] = { level = lv, text = tx }
end
ladder.rules = UI.Text(ladder, 11, C.dim)
ladder.rules:SetPoint("BOTTOMLEFT", ladder, "BOTTOMLEFT", 12, 12)
ladder.rules:SetWidth(RIGHT - 24)
ladder.rules:SetText("In time: your keystone goes up a level. Over time: it goes down one. Everyone is brought back to life when the run ends, and the spoils chest goes to your bags.")
P.ladder = ladder

function P:Refresh()
    local k = S.key
    local shown = {}
    if k and k.hasKey then
        UI.SetText(card.name, ns.DungeonName(k.dungeonId) .. " +" .. k.level)
        card.text:SetText(k.depleted and "Depleted: time it to raise it again." or "Bring your group to the dungeon and start it on Mythic.")
        local list = {}
        for _, n in ipairs(ns.AffixNames(k.affixes)) do
            list[#list + 1] = { n, false }
        end
        if k.eraId then
            list[#list + 1] = { ns.DefName("E", k.eraId, "Era") .. " era", true }
        end
        for i, p in ipairs(card.pills) do
            local item = list[i]
            if item then
                p:SetValue(item[1])
                UI.Colors(p, "2E2638", item[2] and C.gold or C.eraBorder)
                p:Show()
                shown[#shown + 1] = p
            else
                p:Hide()
            end
        end
    else
        card.name:SetText(k and "No keystone yet" or (Comm.ready and "No keystone" or "Waiting for the server"))
        local m0 = ns.Def("M", 0)
        UI.SetText(card.text, m0 and m0.text or "")
        for _, p in ipairs(card.pills) do
            p:Hide()
        end
    end
    UI.Row(shown, card, "TOPLEFT", "TOPLEFT", 16, -124, 6)
    if k and k.weeklyBest and k.weeklyBest > 0 then
        UI.SetText(card.best, "Best this week: +" .. k.weeklyBest .. (k.weeklyBestDungeon and ("  " .. ns.DungeonName(k.weeklyBestDungeon)) or ""))
    else
        card.best:SetText(k and "No key timed this week" or "")
    end

    local mode = k and k.mode or 0
    for i = 0, 2 do
        modeBox.buttons[i]:SetStyle(i == mode and "tabOn" or "tab")
    end

    local m = S.mplus
    local counting = m and m.state == 0 and not m.result
    P.start:SetActive(k and k.hasKey and not counting and true or false)
    if counting then
        P.cancel:Show()
    else
        P.cancel:Hide()
    end

    if k then
        caches.ready:SetText(k.cachesReady .. (k.cachesReady == 1 and " cache ready" or " caches ready"))
        caches.banked:SetText(k.cachesBanked > 0 and (k.cachesBanked .. " saved from earlier weeks") or "Caches you leave unopened wait for you next week")
    else
        caches.ready:SetText("-")
        caches.banked:SetText("")
    end

    local ids = ns.DefIds("M")
    for i, row in ipairs(ladder.rows) do
        local id = ids[i]
        local d = id and ns.Def("M", id)
        if d then
            row.level:SetText(id == 0 and "Mythic 0" or ("+" .. id))
            UI.SetText(row.text, d.text or "")
        else
            row.level:SetText("")
            row.text:SetText("")
        end
    end
end

function P:OnOpen()
    Comm.Refresh("KEY")
end

ns.On("MPLUS_START", function()
    if P:IsVisible() then
        P:Refresh()
    end
end)
