-- Bleakhold: the case window (docs/BleakholdProtocol.md section 15).
-- Right-clicking a case item in the bags (an item in the server's CASES list; not while a vendor, the bank, the
-- mailbox, the auction house, a trade or a guild bank takes the click) opens it: the case's rewards
-- with their chances, a reel of reward cards under a gold marker, and Unlock. Unlock sends CASEOPEN; the reel
-- starts spinning at once and, when the server's UNBOX names the reward (already in the bags by then), slows
-- down to stop on it. Only the answer to the latest request counts: UNBOX carries the request's nonce, ERR its
-- sequence number. The reel is only the show: the server rolled before it answered. A click on the reel
-- skips to the end. /bh case opens the first case in the bags. Stock 3.3.5a look: rewards as item buttons in their
-- quality colour (cards of the reel like loot slots, the contents like quest rewards on their name plates), the
-- cast bar's spark as the marker, the chosen quest reward's highlight on the one won.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S

local floor, max, min, random = math.floor, math.max, math.min, math.random

local CA = {}
ns.Cases = CA

CA.W, CA.H = 848, 570         -- the reel (REEL_W + 4) fits the content with 14 px each side
CA.CARD_W, CA.CARD_H, CA.STEP = 116, 140, 124
CA.REEL_W, CA.REEL_H = 786, 160
CA.SPEED = 1600              -- px/s while waiting for the server
CA.AHEAD = 24                -- the reward lands this many cards after the one under the marker
CA.WAIT = 5                  -- seconds to wait for UNBOX or ERR
CA.GAP = 1.25                -- seconds between two CASEOPEN (the server allows one a second)
CA.GRID_COLS = 4

-- Name colours by tier (item quality: poor .. artifact, 7 heirloom); uncommon and better also light the icon's edge.
CA.TIER = { [0] = "9D9D9D", "FFFFFF", "1EFF00", "0070DD", "A335EE", "FF8000", "E6CC80", "E6CC80" }

CA.phase = "idle"            -- idle, wait (spinning, no answer yet), stop (slowing onto the reward), won
CA.nonce = floor((GetTime() * 1000) % 1000000)   -- CASEOPEN's request number, echoed in UNBOX
CA.offset = 0
CA.reel = {}

local win = UI.Window("BleakholdCaseFrame", CA.W, CA.H, "Case", "chest")
CA.frame = win

------------------------------------------------------------------------------------------------------
-- Layout
------------------------------------------------------------------------------------------------------
local STOCK = UI.STOCK
local ART = {
    glow = "Interface\\Buttons\\UI-ActionButton-Border",     -- the action button's border light (ADD)
    hover = "Interface\\Buttons\\ButtonHilight-Square",      -- an item button under the cursor (ADD)
    nameFrame = "Interface\\QuestFrame\\UI-QuestItemNameFrame", -- the plate behind a quest reward's name
    chosen = "Interface\\QuestFrame\\UI-QuestItemHighlight",  -- the chosen quest reward (ADD)
    spark = "Interface\\CastingBar\\UI-CastingBar-Spark",     -- the cast bar's spark (ADD), the marker line
    arrow = "Interface\\Buttons\\UI-SortArrow",               -- the column sort arrow, the marker's ends
}
CA.ART = ART

local content = win.content
win.count = UI.Text(win.header, 12, C.text, "body", "RIGHT")
win.count:SetPoint("RIGHT", win.close, "LEFT", -14, 0)

-- the case itself as an item button, its text beside it
win.item = UI.ItemButton(content, 36)
win.item:SetPoint("TOPLEFT", content, "TOPLEFT", 16, -10)
win.icon = win.item.icon
win.text = UI.Text(content, 13, C.text)
win.text:SetPoint("LEFT", win.item, "RIGHT", 12, 0)
UI.OneLine(win.text, CA.W - 120)

-- The reel: a tooltip panel; a scroll frame inside it clips the cards; a frame above them carries the marker and
-- the shading at both ends.
local REEL_INSET = 5
local reelBox = UI.Box(content, CA.REEL_W + 2 * REEL_INSET, CA.REEL_H + 2 * REEL_INSET, C.deep, C.border, 0.92, "panel")
reelBox:SetPoint("TOP", content, "TOP", 0, -56)
local clip = CreateFrame("ScrollFrame", nil, reelBox)
clip:SetPoint("TOPLEFT", reelBox, "TOPLEFT", REEL_INSET, -REEL_INSET)
clip:SetSize(CA.REEL_W, CA.REEL_H)
local strip = CreateFrame("Frame", nil, clip)
strip:SetSize(CA.REEL_W, CA.REEL_H)
clip:SetScrollChild(strip)
CA.clip = clip

local function rewardOf(index)
    local c = CA.Def()
    return c and c.rewards[index]
end

local function hideTooltip()
    if GameTooltip then
        GameTooltip:Hide()
    end
end

local function itemTooltip(owner, itemId)
    if GameTooltip and itemId then
        GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
        GameTooltip:SetHyperlink("item:" .. itemId)
        GameTooltip:Show()
    end
end

-- An item button for a reward: the icon in UI-Quickslot2, the item button's highlight under the cursor and, on the
-- reel (glow), the quality's light round it for uncommon and better (the action button's border light in the quality
-- colour), so a good card stands out while the reel spins.
local function rewardSlot(b, size, glow)
    b.slot = UI.ItemButton(b, size)
    b.icon = b.slot.icon
    b.hover = b:CreateTexture(nil, "HIGHLIGHT")
    b.hover:SetTexture(ART.hover)
    b.hover:SetBlendMode("ADD")
    b.hover:SetAllPoints(b.slot)
    if not glow then
        return b.slot
    end
    b.glow = b.slot:CreateTexture(nil, "OVERLAY")
    b.glow:SetTexture(ART.glow)
    b.glow:SetBlendMode("ADD")
    b.glow:SetSize(size * 62 / 36, size * 62 / 36)
    b.glow:SetAlpha(0.85)
    b.glow:SetPoint("CENTER", b.slot, "CENTER", 0, 0)
    b.glow:Hide()
    return b.slot
end

-- A card of the reel, as a loot slot stood up: a dark row with the item button and the name in its quality colour.
local function makeCard(parent, w, h, iconSize)
    local b = CreateFrame("Button", nil, parent)
    b:SetSize(w, h)
    UI.Backdrop(b, C.card, C.border, nil, "edge")
    rewardSlot(b, iconSize, true):SetPoint("TOP", b, "TOP", 0, -18)
    b.name = UI.Text(b, 11, C.text, "body", "CENTER")
    b.name:SetPoint("TOP", b.slot, "BOTTOM", 0, -10)
    b.name:SetWidth(w - 12)
    b.name:SetHeight(28)
    b:SetScript("OnEnter", function(self)
        itemTooltip(self, self.itemId)
    end)
    b:SetScript("OnLeave", hideTooltip)
    return b
end

-- A reward of the contents, as quest rewards list them: the item button, the name plate beside it with the name in
-- its quality colour and the chance under it; the one just won wears the chosen reward's highlight.
-- (the plate's art fills x 11-116 and y 11-52 of its 128 x 64 file, the highlight's two rims x 9-43 and 49-151, y 7-44
-- of 256 x 64: each is cut to its part and laid round the icon or the plate)
local function makeItem(parent, w, iconSize)
    local b = CreateFrame("Button", nil, parent)
    b:SetSize(w, iconSize + 4)
    rewardSlot(b, iconSize):SetPoint("LEFT", b, "LEFT", 2, 0)
    b.plate = b:CreateTexture(nil, "BACKGROUND")
    b.plate:SetTexture(ART.nameFrame)
    b.plate:SetTexCoord(11 / 128, 117 / 128, 11 / 64, 53 / 64)
    b.plate:SetSize(w - iconSize - 4, iconSize + 3)
    b.plate:SetPoint("LEFT", b.slot, "RIGHT", 1, 0)
    b.name = UI.Text(b, 11, C.text, "body", "LEFT")
    b.name:SetPoint("TOPLEFT", b.plate, "TOPLEFT", 8, -5)
    UI.OneLine(b.name, w - iconSize - 18)
    b.chance = UI.Text(b, 11, C.text, "body", "LEFT")
    b.chance:SetPoint("TOPLEFT", b.name, "BOTTOMLEFT", 0, -3)
    b.chosen = b:CreateTexture(nil, "OVERLAY")
    b.chosen:SetTexture(ART.chosen)
    b.chosen:SetTexCoord(9 / 256, 44 / 256, 7 / 64, 45 / 64)
    b.chosen:SetBlendMode("ADD")
    b.chosen:SetPoint("TOPLEFT", b.slot, "TOPLEFT", -3, 3)
    b.chosen:SetPoint("BOTTOMRIGHT", b.slot, "BOTTOMRIGHT", 3, -3)
    b.chosenName = b:CreateTexture(nil, "OVERLAY")
    b.chosenName:SetTexture(ART.chosen)
    b.chosenName:SetTexCoord(49 / 256, 152 / 256, 7 / 64, 45 / 64)
    b.chosenName:SetBlendMode("ADD")
    b.chosenName:SetPoint("TOPLEFT", b.plate, "TOPLEFT", -2, 2)
    b.chosenName:SetPoint("BOTTOMRIGHT", b.plate, "BOTTOMRIGHT", 2, -2)
    function b:SetChosen(on)
        if on then
            self.chosen:Show()
            self.chosenName:Show()
        else
            self.chosen:Hide()
            self.chosenName:Hide()
        end
        self.isChosen = on and true or false
    end
    b:SetChosen(false)
    b:SetScript("OnEnter", function(self)
        itemTooltip(self, self.itemId)
    end)
    b:SetScript("OnLeave", hideTooltip)
    return b
end

local function fillCard(b, r)
    b.itemId = r and r.itemId
    if not r then
        b:Hide()
        return
    end
    b:Show()
    local name, _, _, _, _, _, _, _, _, tex = GetItemInfo(r.itemId)
    if not name and ns.Collections then
        ns.Collections.RequestItem(r.itemId)
    end
    b.icon:SetTexture(tex or GetItemIcon(r.itemId) or STOCK.question)
    local color = CA.TIER[r.tier] or CA.TIER[1]
    UI.SetText(b.name, (name or ("Item " .. r.itemId)) .. (r.count > 1 and (" x" .. r.count) or ""))
    UI.SetColor(b.name, color)
    if b.glow and r.tier >= 2 then
        b.glow:SetVertexColor(UI.Rgb(color))
        b.glow:Show()
    elseif b.glow then
        b.glow:Hide()
    end
    if b.backdropKind then
        UI.Colors(b, C.card, C.border)
    end
    if b.SetChosen then
        b:SetChosen(false)
    end
end

CA.cards = {}
for i = 1, 8 do
    local b = makeCard(strip, CA.CARD_W, CA.CARD_H, 52)
    b:SetScript("OnClick", function()
        CA.Skip()
    end)
    CA.cards[i] = b
end
strip:EnableMouse(true)
strip:SetScript("OnMouseUp", function()
    CA.Skip()
end)

local over = CreateFrame("Frame", nil, reelBox)
over:SetAllPoints(clip)
over:SetFrameLevel(clip:GetFrameLevel() + 5)
for _, side in ipairs({ "LEFT", "RIGHT" }) do
    local t = over:CreateTexture(nil, "BORDER")
    t:SetTexture(UI.WHITE)
    t:SetWidth(90)
    t:SetPoint("TOP" .. side, over, "TOP" .. side, 0, 0)
    t:SetPoint("BOTTOM" .. side, over, "BOTTOM" .. side, 0, 0)
    if side == "LEFT" then
        t:SetGradientAlpha("HORIZONTAL", 0, 0, 0, 0.9, 0, 0, 0, 0)
    else
        t:SetGradientAlpha("HORIZONTAL", 0, 0, 0, 0, 0, 0, 0, 0.9)
    end
end
-- the marker: the cast bar's spark stood across the reel, a sort arrow at each end pointing at it
local marker = over:CreateTexture(nil, "OVERLAY")
marker:SetTexture(ART.spark)
marker:SetBlendMode("ADD")
marker:SetWidth(26)
marker:SetPoint("TOP", over, "TOP", 0, 2)
marker:SetPoint("BOTTOM", over, "BOTTOM", 0, -2)
local markTop = over:CreateTexture(nil, "OVERLAY")
markTop:SetTexture(ART.arrow)
markTop:SetTexCoord(0, 0.5625, 0, 1)
markTop:SetSize(18, 16)
markTop:SetPoint("BOTTOM", over, "TOP", 0, -6)
local markBottom = over:CreateTexture(nil, "OVERLAY")
markBottom:SetTexture(ART.arrow)
markBottom:SetTexCoord(0, 0.5625, 1, 0)
markBottom:SetSize(18, 16)
markBottom:SetPoint("TOP", over, "BOTTOM", 0, 6)
CA.marker = marker

win.result = UI.Text(content, 14, C.gold, "body", "CENTER")
win.result:SetPoint("TOP", reelBox, "BOTTOM", 0, -10)
win.result:SetWidth(CA.W - 60)

win.unlock = UI.Button(content, 150, 22, "Unlock", "gold", 12)
win.unlock:SetPoint("TOP", reelBox, "BOTTOM", 0, -34)
win.unlock:SetScript("OnClick", function()
    CA.Unlock()
end)
win.need = UI.Text(content, 11, C.dim, "body", "CENTER")
win.need:SetPoint("TOP", win.unlock, "BOTTOM", 0, -5)

local contains = UI.Heading(content, "Contents")
contains:SetPoint("TOPLEFT", content, "TOPLEFT", 16, -312)
win.contains = contains

local grid = UI.Scroll(content)
grid:SetPoint("TOPLEFT", content, "TOPLEFT", 16, -336)
grid:SetPoint("BOTTOMRIGHT", content, "BOTTOMRIGHT", -16, 10)
CA.grid = grid
local GRID_W = CA.REEL_W - 24        -- clear of the scroll bar
local GCARD_W = floor((GRID_W - (CA.GRID_COLS - 1) * 12) / CA.GRID_COLS)
local GCARD_H = 44
local GAP_X, GAP_Y = 12, 10
CA.gridCards = UI.Pool(function()
    return makeItem(grid.child, GCARD_W, 37)
end)

------------------------------------------------------------------------------------------------------
-- The case and the reel
------------------------------------------------------------------------------------------------------
function CA.Def()
    return CA.caseId and S.caseDefs[CA.caseId]
end

local function bagCount(itemId)
    return itemId and GetItemCount(itemId) or 0
end

-- A reward index drawn by the chances (cosmetic: the reel's filler cards).
local function drawReward()
    local c = CA.Def()
    if not c or #c.rewards == 0 then
        return nil
    end
    local total = 0
    for _, r in ipairs(c.rewards) do
        total = total + max(1, r.chance)
    end
    local x = random() * total
    for i, r in ipairs(c.rewards) do
        x = x - max(1, r.chance)
        if x <= 0 then
            return i
        end
    end
    return #c.rewards
end

local function reelAt(i)
    if not CA.reel[i] then
        CA.reel[i] = drawReward()
    end
    return CA.reel[i]
end

-- The reel position whose card i (from 1) sits centred under the marker.
local function centreOf(i)
    return (i - 1) * CA.STEP + CA.CARD_W / 2 - CA.REEL_W / 2
end

-- The card under the marker.
function CA.MarkerIndex()
    return floor((CA.offset + CA.REEL_W / 2) / CA.STEP) + 1
end

local function layoutReel()
    local first = max(1, floor(CA.offset / CA.STEP) + 1)
    for k, b in ipairs(CA.cards) do
        local i = first + k - 1
        fillCard(b, rewardOf(reelAt(i) or 0))
        b.reelIndex = i
        b:ClearAllPoints()
        b:SetPoint("TOPLEFT", strip, "TOPLEFT", (i - 1) * CA.STEP - CA.offset, -10)
        if CA.phase == "won" and i == CA.target then
            UI.Select(b, true)
        end
    end
end

local function resetReel()
    CA.reel = {}
    CA.offset = centreOf(4)
    CA.target = nil
    CA.phase = "idle"
end

------------------------------------------------------------------------------------------------------
-- Refresh
------------------------------------------------------------------------------------------------------
function CA.Refresh()
    if not win:IsShown() then
        return
    end
    local c = CA.Def()
    local id = CA.caseId
    local name, _, _, _, _, _, _, _, _, tex = GetItemInfo(id or 0)
    UI.SetText(win.title, (c and c.title) or name or "Case")
    win.icon:SetTexture(tex or (id and GetItemIcon(id)) or "Interface\\Icons\\INV_Misc_Bag_10")
    UI.SetText(win.text, (c and c.text) or (c and "" or "Loading the case..."))
    local have = bagCount(id)
    win.count:SetText(have .. " in your bags")

    local keyOk, needText = true, ""
    if c and c.keyItem then
        local keyHave = bagCount(c.keyItem)
        keyOk = keyHave >= c.keyCount
        local keyName = GetItemInfo(c.keyItem) or ("item " .. c.keyItem)
        local amount = c.keyCount > 1 and (c.keyCount .. " x ") or ""
        needText = "Needs " .. amount .. keyName .. " (you have " .. keyHave .. ")"
    end
    UI.SetText(win.need, needText)
    local busy = CA.phase == "wait" or CA.phase == "stop"
    local ready = Comm.ready or Comm.demo
    win.unlock:SetLabel(CA.phase == "won" and "Unlock Another" or "Unlock")
    win.unlock:SetActive(c ~= nil and #c.rewards > 0 and have > 0 and keyOk and not busy and ready and true or false)
    if CA.status then
        win.result:SetText(CA.status)
    elseif not busy and CA.phase ~= "won" then
        win.result:SetText(have == 0 and "|cff808080You have no such case in your bags.|r" or "")
    end

    -- contents: rows of up to four, as quest rewards from the left
    CA.gridCards:ReleaseAll()
    local rewards = c and c.rewards or {}
    local rows = floor((#rewards + CA.GRID_COLS - 1) / CA.GRID_COLS)
    for i, r in ipairs(rewards) do
        local b = CA.gridCards:Acquire()
        local row, col = floor((i - 1) / CA.GRID_COLS), (i - 1) % CA.GRID_COLS
        b:ClearAllPoints()
        b:SetPoint("TOPLEFT", grid.child, "TOPLEFT", col * (GCARD_W + GAP_X), -4 - row * (GCARD_H + GAP_Y))
        fillCard(b, r)
        local pct = r.chance / 100
        b.chance:SetText(pct >= 1 and string.format("%d%%", floor(pct + 0.5)) or string.format("%.2f%%", pct))
        if CA.phase == "won" and CA.won and CA.won.index == i then
            b:SetChosen(true)
        end
    end
    grid:SetContentHeight(rows * (GCARD_H + GAP_Y) + 4)
    layoutReel()
end

------------------------------------------------------------------------------------------------------
-- Opening
------------------------------------------------------------------------------------------------------
function CA.Open(caseItemId)
    if not caseItemId then
        return false
    end
    if CA.caseId ~= caseItemId then
        CA.caseId = caseItemId
        CA.status = nil
        CA.won = nil
        resetReel()
    end
    Comm.Get("CASE", caseItemId)
    if not win:IsShown() then
        win:Show()
    end
    CA.Refresh()
    return true
end

function CA.Unlock()
    local c = CA.Def()
    if not c or CA.phase == "wait" or CA.phase == "stop" then
        return false
    end
    local now = GetTime()
    if CA.nextAt and now < CA.nextAt then
        return false
    end
    CA.nonce = CA.nonce % 2147483647 + 1
    if not Comm.Send("CASEOPEN", c.id, CA.nonce) then
        CA.status = "|cffff2020Not connected to the realm.|r"
        CA.Refresh()
        return false
    end
    CA.reqNonce, CA.reqSeq = CA.nonce, Comm.lastSeq
    CA.nextAt = now + CA.GAP
    -- spin on from where the reel is, with fresh cards ahead of the marker
    local here = CA.MarkerIndex()
    for i in pairs(CA.reel) do
        if i > here + 1 then
            CA.reel[i] = nil
        end
    end
    CA.won, CA.target, CA.status = nil, nil, nil
    CA.phase = "wait"
    CA.waitStart = now
    CA.lastTick = here
    win.result:SetText("")
    CA.Refresh()
    return true
end

-- UNBOX: plan the stop on the reward.
local function onUnbox(e)
    -- only the answer to the request this spin waits for (a late answer to an earlier one is not it)
    if CA.phase ~= "wait" or e.caseItemId ~= CA.caseId or (e.nonce and e.nonce ~= CA.reqNonce) then
        return
    end
    local c = CA.Def()
    local r = c and c.rewards[e.index]
    if not r or r.itemId ~= e.itemId then
        -- the list shown is not the server's any more (it reloaded): no reel, the item by its id, a fresh list
        CA.phase = "won"
        CA.won = nil
        local name = GetItemInfo(e.itemId) or ("item " .. e.itemId)
        CA.status = "You received " .. U.Safe(name) .. (e.count > 1 and (" x" .. e.count) or "") .. "!"
        S.caseDefs[CA.caseId] = nil
        Comm.Get("CASE", CA.caseId)
        CA.Refresh()
        return
    end
    CA.won = e
    local t = CA.MarkerIndex() + CA.AHEAD
    CA.reel[t] = e.index
    CA.target = t
    local jitter = (random() - 0.5) * (CA.CARD_W - 24)
    CA.stopFrom = CA.offset
    CA.stopTo = centreOf(t) + jitter
    -- a cubic ease-out whose starting speed is the spinning speed
    CA.stopTime = 3 * (CA.stopTo - CA.stopFrom) / CA.SPEED
    CA.stopStart = GetTime()
    CA.phase = "stop"
end

local function finish()
    local e = CA.won
    CA.phase = "won"
    if CA.stopTo then
        CA.offset = CA.stopTo
    end
    local r = e and rewardOf(e.index)
    local name = r and GetItemInfo(r.itemId) or (r and ("item " .. r.itemId)) or "an item"
    local color = r and (CA.TIER[r.tier] or "FFFFFF") or "FFFFFF"
    local amount = (e and e.count > 1) and (" x" .. e.count) or ""
    CA.status = "You received |cff" .. color .. U.Safe(name) .. amount .. "|r!"
    if r and r.tier >= 5 then
        PlaySoundFile("Sound\\Interface\\LevelUp.wav")
    else
        PlaySound("igQuestListComplete")
    end
    CA.Refresh()
end

function CA.Skip()
    if CA.phase == "stop" then
        finish()
    end
end

win:SetScript("OnUpdate", function(self, elapsed)
    if CA.phase == "wait" then
        CA.offset = CA.offset + CA.SPEED * (elapsed or 0)
        if GetTime() - CA.waitStart > CA.WAIT then
            CA.phase = "idle"
            CA.status = "|cffff2020The realm did not answer. Your case is still in your bags if it did not open.|r"
            CA.Refresh()
            return
        end
    elseif CA.phase == "stop" then
        local u = CA.stopTime > 0 and min(1, (GetTime() - CA.stopStart) / CA.stopTime) or 1
        local k = 1 - (1 - u) ^ 3
        CA.offset = CA.stopFrom + (CA.stopTo - CA.stopFrom) * k
        if u >= 1 then
            finish()
            return
        end
    else
        return
    end
    local here = CA.MarkerIndex()
    if here ~= CA.lastTick then
        CA.lastTick = here
        PlaySound("igMainMenuOptionCheckBoxOn")
    end
    layoutReel()
end)

ns.On("UNBOX", onUnbox)

ns.On("ERR", function(e)
    if e and e.op == "CASEOPEN" and CA.phase == "wait" and (not e.seq or not CA.reqSeq or e.seq == CA.reqSeq) then
        CA.phase = "idle"
        CA.status = "|cffff2020" .. U.Safe(e.text or "The case could not be opened.") .. "|r"
        CA.Refresh()
    end
end)

ns.On("STATE", function(topic)
    if not win:IsShown() then
        return
    end
    -- a new case list drops the cached contents: ask again for the case on show
    if topic == "CASES" and CA.caseId and not S.caseDefs[CA.caseId] then
        Comm.Get("CASE", CA.caseId)
    end
    if topic == "CASE" or topic == "CASES" then
        CA.Refresh()
    end
end)

ns.RegisterEvent("BAG_UPDATE", function()
    if win:IsShown() then
        CA.Refresh()
    end
end)

function win:OnClose()
    -- a spin in progress has its result already: the bags have the reward
    if CA.phase == "stop" then
        finish()
    end
    if CA.phase ~= "wait" then
        CA.status = nil
    end
end

resetReel()

-- While these are open a right-click in the bags sells, stores, mails, auctions or trades the item.
CA.CLICK_TAKERS = { "MerchantFrame", "BankFrame", "MailFrame", "AuctionFrame", "TradeFrame", "GuildBankFrame" }

local function clickTaken()
    if SpellIsTargeting and SpellIsTargeting() then
        return true
    end
    for _, name in ipairs(CA.CLICK_TAKERS) do
        local f = _G[name]
        if f and f.IsShown and f:IsShown() then
            return true
        end
    end
    return false
end

-- Right-click in the bags (any bag addon calls UseContainerItem).
function CA.OnUseContainerItem(bag, slot)
    local id = GetContainerItemID and GetContainerItemID(bag, slot)
    if id and S.cases[id] and not clickTaken() then
        CA.Open(id)
    end
end
hooksecurefunc("UseContainerItem", function(bag, slot)
    ns.SafeCall(CA.OnUseContainerItem, bag, slot)
end)

-- The first case in the bags.
function CA.FirstInBags()
    for bag = 0, 4 do
        for slot = 1, GetContainerNumSlots(bag) or 0 do
            local id = GetContainerItemID(bag, slot)
            if id and S.cases[id] then
                return id
            end
        end
    end
end

ns.AddCommand("case", "open a case from your bags", function()
    local id = CA.FirstInBags()
    if id then
        CA.Open(id)
    elseif next(S.cases) then
        ns.Print("You have no case in your bags.")
    else
        ns.Print("This realm has no cases.")
    end
end)
