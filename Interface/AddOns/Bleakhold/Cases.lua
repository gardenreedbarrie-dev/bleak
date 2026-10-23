-- Bleakhold: the case window (docs/BleakholdProtocol.md section 15).
-- Right-clicking a case item in the bags (an item in the server's CASES list; not while a vendor, the bank, the
-- mailbox, the auction house, a trade or a guild bank takes the click) opens it: the case's rewards
-- with their chances, a reel of reward cards under a gold marker, and Unlock. Unlock sends CASEOPEN; the reel
-- starts spinning at once and, when the server's UNBOX names the reward (already in the bags by then), slows
-- down to stop on it. Only the answer to the latest request counts: UNBOX carries the request's nonce, ERR its
-- sequence number. The reel is only the show: the server rolled before it answered. A click on the reel
-- skips to the end. /bh case opens the first case in the bags.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S

local floor, max, min, random = math.floor, math.max, math.min, math.random

local CA = {}
ns.Cases = CA

CA.W, CA.H = 820, 600
CA.CARD_W, CA.CARD_H, CA.STEP = 116, 140, 124
CA.REEL_W, CA.REEL_H = 786, 160
CA.SPEED = 1600              -- px/s while waiting for the server
CA.AHEAD = 24                -- the reward lands this many cards after the one under the marker
CA.WAIT = 5                  -- seconds to wait for UNBOX or ERR
CA.GAP = 1.25                -- seconds between two CASEOPEN (the server allows one a second)
CA.GRID_COLS = 6

-- Card colours by tier (item quality: poor .. artifact, 7 heirloom).
CA.TIER = { [0] = "9D9D9D", "FFFFFF", "1EFF00", "0070DD", "A335EE", "FF8000", "E6CC80", "E6CC80" }

CA.phase = "idle"            -- idle, wait (spinning, no answer yet), stop (slowing onto the reward), won
CA.nonce = floor((GetTime() * 1000) % 1000000)   -- CASEOPEN's request number, echoed in UNBOX
CA.offset = 0
CA.reel = {}

local win = UI.Window("BleakholdCaseFrame", CA.W, CA.H, "CASE", "chest")
CA.frame = win

------------------------------------------------------------------------------------------------------
-- Layout
------------------------------------------------------------------------------------------------------
local content = win.content
win.count = UI.Text(win.header, 12, C.dim, "body", "RIGHT")
win.count:SetPoint("RIGHT", win.close, "LEFT", -14, 0)

win.icon = content:CreateTexture(nil, "ARTWORK")
win.icon:SetSize(36, 36)
win.icon:SetPoint("TOPLEFT", content, "TOPLEFT", 16, -12)
win.text = UI.Text(content, 13, C.mid)
win.text:SetPoint("LEFT", win.icon, "RIGHT", 12, 0)
UI.OneLine(win.text, CA.W - 120)

-- The reel: a scroll frame clips the cards; a frame above it carries the marker and the edge shading.
local reelBox = UI.Box(content, CA.REEL_W + 4, CA.REEL_H + 4, C.deep, C.border)
reelBox:SetPoint("TOPLEFT", content, "TOPLEFT", 14, -60)
local clip = CreateFrame("ScrollFrame", nil, reelBox)
clip:SetPoint("TOPLEFT", reelBox, "TOPLEFT", 2, -2)
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

-- A reward card (reel and contents): icon, name in the tier's colour, a tier bar, and a chance line.
local function makeCard(parent, w, h, iconSize)
    local b = CreateFrame("Button", nil, parent)
    b:SetSize(w, h)
    UI.Backdrop(b, C.card, C.border)
    b.icon = b:CreateTexture(nil, "ARTWORK")
    b.icon:SetSize(iconSize, iconSize)
    b.icon:SetPoint("TOP", b, "TOP", 0, -12)
    b.name = UI.Text(b, 11, C.text, "body", "CENTER")
    b.name:SetPoint("TOP", b.icon, "BOTTOM", 0, -6)
    b.name:SetWidth(w - 12)
    b.name:SetHeight(28)
    b.bar = UI.Solid(b, C.purple, "ARTWORK")
    b.bar:SetPoint("BOTTOMLEFT", b, "BOTTOMLEFT", 1, 1)
    b.bar:SetPoint("BOTTOMRIGHT", b, "BOTTOMRIGHT", -1, 1)
    b.bar:SetHeight(4)
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
    b.icon:SetTexture(tex or GetItemIcon(r.itemId) or "Interface\\Icons\\INV_Misc_QuestionMark")
    local color = CA.TIER[r.tier] or CA.TIER[1]
    UI.SetText(b.name, (name or ("Item " .. r.itemId)) .. (r.count > 1 and (" x" .. r.count) or ""))
    UI.SetColor(b.name, color)
    b.bar:SetVertexColor(UI.Rgb(color))
    UI.Colors(b, r.tier >= 5 and "2A2018" or C.card, r.tier >= 5 and C.orange or C.border)
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
    local r, g, b = UI.Rgb(C.deep)
    if t.SetGradientAlpha then
        if side == "LEFT" then
            t:SetGradientAlpha("HORIZONTAL", r, g, b, 0.9, r, g, b, 0)
        else
            t:SetGradientAlpha("HORIZONTAL", r, g, b, 0, r, g, b, 0.9)
        end
    else
        t:SetVertexColor(r, g, b, 0.5)
    end
end
local marker = UI.Solid(over, C.gold, "OVERLAY")
marker:SetWidth(3)
marker:SetPoint("TOP", over, "TOP", 0, 0)
marker:SetPoint("BOTTOM", over, "BOTTOM", 0, 0)
local markTop = UI.Glyph(over, "down", 16, C.goldLight, "OVERLAY")
markTop:SetPoint("BOTTOM", over, "TOP", 0, -8)
local markBottom = UI.Glyph(over, "up", 16, C.goldLight, "OVERLAY")
markBottom:SetPoint("TOP", over, "BOTTOM", 0, 8)

win.result = UI.Text(content, 14, C.goldPale, "body", "CENTER")
win.result:SetPoint("TOP", reelBox, "BOTTOM", 0, -12)
win.result:SetWidth(CA.W - 60)

win.unlock = UI.Button(content, 260, 36, "UNLOCK", "green", 15)
win.unlock:SetPoint("TOP", reelBox, "BOTTOM", 0, -40)
win.unlock:SetScript("OnClick", function()
    CA.Unlock()
end)
win.need = UI.Text(content, 11, C.mute, "body", "CENTER")
win.need:SetPoint("TOP", win.unlock, "BOTTOM", 0, -6)

local contains = UI.Text(content, 11, C.dim, "body", "CENTER")
contains:SetPoint("TOP", win.unlock, "BOTTOM", 0, -28)
contains:SetText("CONTAINS ONE OF THE FOLLOWING")
local lineL = UI.Solid(content, C.border, "BORDER")
lineL:SetHeight(1)
lineL:SetPoint("RIGHT", contains, "LEFT", -10, 0)
lineL:SetPoint("LEFT", content, "LEFT", 16, 0)
local lineR = UI.Solid(content, C.border, "BORDER")
lineR:SetHeight(1)
lineR:SetPoint("LEFT", contains, "RIGHT", 10, 0)
lineR:SetPoint("RIGHT", content, "RIGHT", -16, 0)

local grid = UI.Scroll(content)
grid:SetPoint("TOPLEFT", content, "TOPLEFT", 16, -342)
grid:SetPoint("BOTTOMRIGHT", content, "BOTTOMRIGHT", -16, 12)
CA.grid = grid
local GRID_W = CA.REEL_W - 4
local GCARD_W = floor((GRID_W - (CA.GRID_COLS - 1) * 8) / CA.GRID_COLS)
local GCARD_H = 112
CA.gridCards = UI.Pool(function()
    local b = makeCard(grid.child, GCARD_W, GCARD_H, 40)
    b.chance = UI.Text(b, 11, C.goldPale, "body", "CENTER")
    b.chance:SetPoint("BOTTOM", b, "BOTTOM", 0, 10)
    return b
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
            UI.Colors(b, "2A2232", C.goldLight)
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
    UI.SetText(win.title, string.upper((c and c.title) or name or "Case"))
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
    win.unlock:SetLabel(CA.phase == "won" and "UNLOCK ANOTHER" or "UNLOCK")
    win.unlock:SetActive(c ~= nil and #c.rewards > 0 and have > 0 and keyOk and not busy and ready and true or false)
    if CA.status then
        win.result:SetText(CA.status)
    elseif not busy and CA.phase ~= "won" then
        win.result:SetText(have == 0 and "|cff8C877DYou have no such case in your bags.|r" or "")
    end

    -- contents: rows of up to six, each row centred
    CA.gridCards:ReleaseAll()
    local rewards = c and c.rewards or {}
    local rows = floor((#rewards + CA.GRID_COLS - 1) / CA.GRID_COLS)
    for i, r in ipairs(rewards) do
        local b = CA.gridCards:Acquire()
        local row, col = floor((i - 1) / CA.GRID_COLS), (i - 1) % CA.GRID_COLS
        local inRow = min(CA.GRID_COLS, #rewards - row * CA.GRID_COLS)
        local x0 = (GRID_W - (inRow * GCARD_W + (inRow - 1) * 8)) / 2
        b:ClearAllPoints()
        b:SetPoint("TOPLEFT", grid.child, "TOPLEFT", floor(x0 + col * (GCARD_W + 8)), -row * (GCARD_H + 8))
        fillCard(b, r)
        local pct = r.chance / 100
        b.chance:SetText(pct >= 1 and string.format("%d%%", floor(pct + 0.5)) or string.format("%.2f%%", pct))
        if CA.phase == "won" and CA.won and CA.won.index == i then
            UI.Colors(b, "2A2232", C.goldLight)
        end
    end
    grid:SetContentHeight(rows * (GCARD_H + 8))
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
        CA.status = "|cffE5604FNot connected to the realm.|r"
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
            CA.status = "|cffE5604FThe realm did not answer. Your case is still in your bags if it did not open.|r"
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
        CA.status = "|cffE5604F" .. U.Safe(e.text or "The case could not be opened.") .. "|r"
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
