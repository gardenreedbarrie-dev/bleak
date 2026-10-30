-- Bleakhold: the café's menu (docs/BleakholdProtocol.md, section 21), the window a customer orders from: the café
-- owner's gossip opens it (CAFUI menu), and so do the order chip and UI.Open("cafemenu"). Stock look: the options
-- frame's tabs (Coffee, Tea, Shakes) on a tooltip panel, a merchant-like list (the drink as an item button, its name
-- in gold, the flavour text in white, the buff as an item tooltip's green "Use:" line, the price in coins and who
-- makes it), the tip as segmented red buttons, the total and a red Order button; the server decides the price, the
-- queue and whether the order can be made (CAFM canOrder, reason), the client only asks: CORDER after the café's own
-- confirmation (Cafe.Confirm, the stock popup's look), CCANCEL while the order waits (CAFO Q) or the house finishes it
-- (F).
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S
local K = ns.CafeKit
local Cafe = K.Cafe

local floor, max, min = math.floor, math.max, math.min

local MN = {}
ns.CafeMenu = MN

MN.W, MN.H = 460, 695
MN.family = "C"
MN.tip = 0
MN.selected = {}          -- family -> recipe id
MN.ROW_H, MN.ROW_PITCH, MN.ROWS = 64, 66, 7
MN.TIPS = { 0, 10, 25, 50 }

local win = UI.Window("BleakholdCafeMenu", MN.W, MN.H, "Café", "INV_Drink_15")
MN.frame = win

MN.TABS = { { key = "C", label = Cafe.FAMILY_PLURAL.C }, { key = "T", label = Cafe.FAMILY_PLURAL.T },
    { key = "M", label = Cafe.FAMILY_PLURAL.M } }
local body, tabs, BW, BH = K.TabStrip(win, MN.TABS, function(key)
    MN.family = key
    MN.Refresh()
end)
MN.body, MN.tabs = body, tabs

------------------------------------------------------------------------------------------------------
-- The list
------------------------------------------------------------------------------------------------------
-- The list and the footer under it share one margin, 8 px inside the panel on both sides: a family that fits (no
-- family has more than MN.ROWS drinks) gives its rows the list's whole width, a longer one makes room for the
-- scrollbar at the list's right edge (MN.RowWidth).
MN.MARGIN = 8
local list = UI.Scroll(body)
list:SetPoint("TOPLEFT", body, "TOPLEFT", MN.MARGIN, -MN.MARGIN)
list:SetSize(BW - 2 * MN.MARGIN, MN.ROWS * MN.ROW_PITCH)
MN.list = list
MN.ROW_W = BW - 2 * MN.MARGIN
MN.ROW_W_SCROLL = MN.ROW_W - UI.SCROLL_W - 4

-- n rows: their height in the list, and the width each row gets
function MN.ContentHeight(n)
    return n > 0 and (n * MN.ROW_PITCH - (MN.ROW_PITCH - MN.ROW_H)) or 0
end

function MN.RowWidth(n)
    return MN.ContentHeight(n) > list:GetHeight() and MN.ROW_W_SCROLL or MN.ROW_W
end

-- a row's width and the texts that follow it (the price and who makes it stand at its right edge)
local function sizeRow(r, w)
    if r.rowW == w then
        return
    end
    r.rowW = w
    r:SetWidth(w)
    UI.OneLine(r.name, w - 150)
    r.text:SetWidth(w - 146)
    UI.OneLine(r.buff, w - 74)
end

local function newRow()
    local r = CreateFrame("Button", nil, list.child)
    r:SetHeight(MN.ROW_H)
    UI.Backdrop(r, C.card, C.border, nil, "edge")
    r.glow = r:CreateTexture(nil, "HIGHLIGHT")
    r.glow:SetTexture(UI.STOCK.rowHighlight)
    r.glow:SetBlendMode("ADD")
    r.glow:SetPoint("TOPLEFT", r, "TOPLEFT", 1, -1)
    r.glow:SetPoint("BOTTOMRIGHT", r, "BOTTOMRIGHT", -1, 1)
    r.glow:SetAlpha(0.35)
    r.item = UI.ItemButton(r, 40)
    r.item:SetPoint("LEFT", r, "LEFT", 10, 0)
    r.name = UI.Text(r, 14, C.gold)
    r.name:SetPoint("TOPLEFT", r, "TOPLEFT", 62, -6)
    r.text = UI.Para(r, 11, C.text)
    r.text:SetSpacing(1)
    r.text:SetHeight(26)
    r.text:SetPoint("TOPLEFT", r, "TOPLEFT", 62, -23)
    r.buff = UI.Text(r, 11, C.teal)
    r.buff:SetPoint("TOPLEFT", r, "TOPLEFT", 62, -50)
    sizeRow(r, MN.ROW_W)
    r.price = Cafe.MoneyFrame(r, 12)
    r.price:SetPoint("TOPRIGHT", r, "TOPRIGHT", -10, -7)
    r.tag = UI.Text(r, 10, C.dim, "body", "RIGHT")
    r.tag:SetPoint("TOPRIGHT", r, "TOPRIGHT", -10, -26)
    r:RegisterForClicks("LeftButtonUp")
    r:SetScript("OnClick", function(self)
        if PlaySound then
            PlaySound("igMainMenuOptionCheckBoxOn")
        end
        MN.selected[MN.family] = self.recipeId
        MN.Refresh()
    end)
    r:SetScript("OnEnter", function(self)
        MN.RowTip(self)
    end)
    r:SetScript("OnLeave", K.HideTip)
    return r
end

-- a row's tooltip: the drink, what its buff does and for how long
function MN.RowTip(self)
    local rr = Cafe.Recipe(self.recipeId)
    if not rr then
        return
    end
    local lines = { U.Safe(rr.name) }
    if rr.text then
        lines[#lines + 1] = { U.Safe(rr.text), C.text, true }
    end
    lines[#lines + 1] = { "Use: " .. (K.BUFF_LONG[rr.family] or ""), C.teal, true }
    lines[#lines + 1] = { (rr.buffMin or 30) .. " minutes, more for a Perfect drink.", C.dim, true }
    UI.ShowTooltip(self, lines)
end
-- the rows stay as they are while in use: a CAFE, CAFO or CAFBF push (or the once-a-second refresh) mid-click never
-- hides the row under the mouse, which would drop the click (Cafe.StablePool)
MN.rows = Cafe.StablePool(newRow)

------------------------------------------------------------------------------------------------------
-- The footer: tip, total, order, status, your café buffs; its right edge is the rows' (the list's) right edge
------------------------------------------------------------------------------------------------------
local foot = CreateFrame("Frame", nil, body)
foot:SetPoint("TOPLEFT", list, "BOTTOMLEFT", 0, -6)
foot:SetPoint("BOTTOMRIGHT", body, "BOTTOMRIGHT", -MN.MARGIN, MN.MARGIN)
MN.foot = foot
foot.rule = foot:CreateTexture(nil, "ARTWORK")
foot.rule:SetTexture(1, 1, 1, 0.12)
foot.rule:SetHeight(1)
foot.rule:SetPoint("TOPLEFT", foot, "TOPLEFT", 0, 0)
foot.rule:SetPoint("TOPRIGHT", foot, "TOPRIGHT", 0, 0)

foot.tipLabel = UI.Label(foot, "Tip", 12)
foot.tipLabel:SetPoint("TOPLEFT", foot, "TOPLEFT", 6, -14)
local tipDefs = {}
for i, pct in ipairs(MN.TIPS) do
    tipDefs[i] = { value = pct, label = pct == 0 and "No tip" or ("+" .. pct .. "%") }
end
MN.tipChoice = K.Segmented(foot, tipDefs, 72, 22, function(value)
    MN.tip = value
    MN.Refresh()
end)
MN.tipChoice.buttons[1]:SetPoint("TOPLEFT", foot, "TOPLEFT", 48, -9)

foot.total = UI.Text(foot, 13, C.text)
foot.total:SetPoint("TOPLEFT", foot, "TOPLEFT", 6, -45)
UI.OneLine(foot.total, BW - 170)
foot.totalLabel = UI.Label(foot, "Total", 13)
foot.totalLabel:SetPoint("TOPLEFT", foot, "TOPLEFT", 6, -45)
foot.totalMoney = Cafe.MoneyFrame(foot, 13)
foot.totalMoney:SetPoint("LEFT", foot.totalLabel, "RIGHT", 8, 0)
MN.order = UI.Button(foot, 120, 22, "Order", "red")
MN.order:SetPoint("TOPRIGHT", foot, "TOPRIGHT", 0, -40)
MN.order:SetScript("OnClick", function()
    MN.ConfirmOrder()
end)
MN.cancel = UI.Button(foot, 120, 22, "Cancel Order", "red")
MN.cancel:SetPoint("TOPRIGHT", foot, "TOPRIGHT", 0, -40)
MN.cancel:SetScript("OnClick", function()
    Cafe.CancelOrder()
end)
MN.cancel:Hide()

foot.status = UI.Text(foot, 11, C.text)
foot.status:SetPoint("TOPLEFT", foot, "TOPLEFT", 6, -72)
UI.OneLine(foot.status, BW - 130)
foot.count = UI.Text(foot, 11, C.dim, "body", "RIGHT")
foot.count:SetPoint("TOPRIGHT", foot, "TOPRIGHT", 0, -72)
UI.OneLine(foot.count, 110)

foot.buffLabel = UI.Label(foot, "Your Café Buffs", 11)
foot.buffLabel:SetPoint("TOPLEFT", foot, "TOPLEFT", 6, -96)
foot.buffs = {}
MN.BUFFS = { { family = "C", key = "coffeeSec" }, { family = "T", key = "teaSec" }, { family = "M", key = "shakeSec" } }
for i, b in ipairs(MN.BUFFS) do
    local f = UI.Icon(foot, 18, Cafe.Icon("family", b.family))
    f:SetPoint("LEFT", foot.buffLabel, "RIGHT", 10 + (i - 1) * 76, 0)
    f.time = UI.Text(foot, 11, C.text)
    f.time:SetPoint("LEFT", f, "RIGHT", 4, 0)
    UI.OneLine(f.time, 50)
    f.def = b
    K.Tip(f)
    foot.buffs[i] = f
end

------------------------------------------------------------------------------------------------------
-- Data
------------------------------------------------------------------------------------------------------
-- The café this menu is for: the one CAFUI named, else the player's own team's.
function MN.CafeId()
    return MN.cafeId or Cafe.MyCafe()
end

-- The rows of a family: CAFM's (the server's price, who makes it, whether the buff works) over the recipes;
-- before CAFM arrives, the recipes with their computed price.
function MN.Rows(family)
    local cafeId = MN.CafeId()
    local menu = S.cafeMenu and S.cafeMenu[cafeId]
    local out = {}
    for _, r in ipairs(Cafe.Recipes(cafeId, family)) do
        local row = menu and menu.byRecipe and menu.byRecipe[r.id]
        if menu and not row and menu.rows and #menu.rows > 0 then
            -- the server's menu leaves this one out: not on sale
        else
            out[#out + 1] = {
                recipe = r, recipeId = r.id, priceCopper = row and row.priceCopper or Cafe.Price(r.id),
                byBarista = row and row.byBarista, effective = row == nil or row.effective ~= 0,
            }
        end
    end
    return out
end

function MN.Selected()
    local rows = MN.Rows(MN.family)
    local want = MN.selected[MN.family]
    for _, r in ipairs(rows) do
        if r.recipeId == want then
            return r
        end
    end
    return rows[1]
end

-- what the player pays: the price and the tip (the server's own sum: floor of the tip's share)
function MN.Total(price, tip)
    return price + floor(price * (tip or 0) / 100)
end

local ORDER_STATE = {
    Q = function(o) return "In queue #" .. (o.position or 1) end,
    M = function(o)
        return "Being made by " .. U.Safe(o.barista or "a barista") .. " (" .. (o.nextStep or 0) .. "/"
            .. (o.stepCount or 0) .. ")"
    end,
    H = function(o)
        local left = Cafe.OrderLeft(o)
        return "The house is making it" .. (left and (" (~" .. Cafe.CeilSec(left) .. " s)") or "")
            .. Cafe.OrderPausedText(o)
    end,
    F = function()
        local cafe = Cafe.Cafe(MN.CafeId())
        return "Taking too long: " .. U.Safe(cafe and cafe.ownerName or "the owner") .. " is finishing it"
    end,
    -- pickup (section 21): within 15 yd of the counter, or sitting at a café table; its clock runs on in a pause
    R = function(o)
        local left = Cafe.OrderLeft(o)
        return "Ready" .. (left and (" · " .. K.Short(left)) or "") .. ": walk to the counter or sit at a café table"
    end,
    D = function() return "Delivered! Enjoy your drink." end,
    X = function() return "Cancelled: your money is back." end,
    E = function() return "Not picked up in time: the house's share came back." end,
}
MN.ORDER_STATE = ORDER_STATE

-- the order still open (the menu's footer shows it instead of the total): queued, being made, ready
local function pending(o)
    return o and o.orderId and o.state and o.state ~= "D" and o.state ~= "X" and o.state ~= "E"
end

-- the status line: why ordering is off (CAFM reason), else who makes it
local REASONS = {
    cafe_cap = "The café is full right now; try again in a minute.",
    cafe_paused = "Danger nearby: the café has paused.",
    cafe_closed = "The café is closed right now.",
    cafe_order = "You have an order already, or you used today's orders.",
    cafe_shift = "You are on shift: baristas do not order.",
    cafe_faction = "This is the other team's café.",
    cafe_where = "Come closer to the café to order.",
    cafe_combat = "Not while you are in combat.",
    dead = "Not while you are dead.",
}
MN.REASONS = REASONS

function MN.Refresh()
    if not win:IsShown() then
        return
    end
    local cafeId = MN.CafeId()
    local cafe = Cafe.Cafe(cafeId)
    UI.SetText(win.title, cafe and cafe.name or "Café")
    for _, b in ipairs(tabs) do
        b:SetStyle(b.key == MN.family and "stripOn" or "strip")
    end

    local menu = S.cafeMenu and S.cafeMenu[cafeId]
    local rows = MN.Rows(MN.family)
    local sel = MN.Selected()
    local rowW = MN.RowWidth(#rows)
    MN.rows:Begin()
    for i, d in ipairs(rows) do
        local r = MN.rows:Acquire()
        sizeRow(r, rowW)
        r:ClearAllPoints()
        r:SetPoint("TOPLEFT", list.child, "TOPLEFT", 0, -(i - 1) * MN.ROW_PITCH)
        r.recipeId = d.recipeId
        r.data = d
        r.item:SetIcon(Cafe.Icon("family", d.recipe.family))
        UI.SetText(r.name, d.recipe.name)
        UI.SetColor(r.name, K.TierColor(d.recipe.tier))
        UI.SetText(r.text, d.recipe.text or "")
        if d.effective then
            r.buff:SetText(K.BuffLine(d.recipe))
            UI.SetColor(r.buff, C.teal)
        else
            -- effective 0: coffee at the level cap or with XP gain off, or a family whose bonus is off on the realm
            r.buff:SetText(Cafe.NoEffectText(d.recipe.family))
            UI.SetColor(r.buff, C.red)
        end
        r.price:SetCopper(d.priceCopper)
        if d.byBarista == nil then
            r.tag:SetText("")
        else
            r.tag:SetText(d.byBarista ~= 0 and "Barista" or "House")
        end
        UI.Select(r, sel ~= nil and sel.recipeId == d.recipeId)
        Cafe.RetipIfOwned(r, MN.RowTip)
    end
    MN.rows:Finish()
    list:SetContentHeight(MN.ContentHeight(#rows))
    list:SetStep(MN.ROW_PITCH)

    -- the footer
    MN.tipChoice:Select(MN.tip)
    local o = S.cafeOrder
    local open = pending(o)
    local can = menu == nil or menu.canOrder ~= 0
    if open then
        local r = Cafe.Recipe(o.recipeId)
        local fn = ORDER_STATE[o.state]
        -- the drink here, its state on the status line under it
        local name = U.Color(K.TierColor(r and r.tier), U.Safe(r and r.name or "a drink"))
        foot.total:SetText("|cffffd100Your order:|r " .. name)
        foot.total:Show()
        foot.totalLabel:Hide()
        foot.totalMoney:Hide()
        MN.order:Hide()
        if o.state == "Q" or o.state == "F" then
            MN.cancel:Show()
        else
            MN.cancel:Hide()
        end
        for _, b in ipairs(MN.tipChoice.buttons) do
            b:SetActive(false)
        end
    else
        MN.cancel:Hide()
        MN.order:Show()
        for _, b in ipairs(MN.tipChoice.buttons) do
            b:SetActive(true)
        end
        MN.tipChoice:Select(MN.tip)
        foot.total:Hide()
        if sel then
            foot.totalMoney:SetCopper(MN.Total(sel.priceCopper, MN.tip))
            foot.totalLabel:Show()
            foot.totalMoney:Show()
        else
            foot.totalLabel:Hide()
            foot.totalMoney:Hide()
        end
        MN.order:SetActive(sel ~= nil and can and Comm.ready and true or false)
    end

    local status, color = "", C.text
    local row = S.cafes and S.cafes[cafeId]
    if open then
        local fn = ORDER_STATE[o.state]
        status = fn and fn(o) or ""
        color = o.state == "R" and C.teal or (o.state == "F" and C.orange or C.text)
    elseif menu and menu.canOrder == 0 then
        status = REASONS[menu.reason] or ns.ErrorText({ code = menu.reason }) or "You cannot order right now."
        color = menu.reason == "cafe_cap" and C.orange or C.red
    elseif row and row.open == 2 then
        status, color = REASONS.cafe_paused, C.red
    elseif menu or row then
        local n = (menu and menu.baristas) or (row and row.baristas) or 0
        if n > 0 then
            status = "Baristas on shift: " .. n
        else
            local eta = (menu and menu.houseEtaSec) or (row and row.houseEtaSec)
            status = "The house will make it" .. (eta and (": about " .. eta .. " s") or ".")
        end
    elseif not Comm.ready then
        status, color = "Waiting for the server...", C.dim
    end
    foot.status:SetText(status)
    UI.SetColor(foot.status, color)
    if menu and menu.ordersCap and menu.ordersCap > 0 then
        foot.count:SetText("Today " .. (menu.ordersToday or 0) .. " / " .. menu.ordersCap)
    else
        foot.count:SetText("")
    end
    MN.RefreshBuffs()
end

function MN.RefreshBuffs()
    local b = S.cafeBuffs
    for _, f in ipairs(foot.buffs) do
        local left = b and Cafe.Left(b, f.def.key)
        local on = left and left > 0
        f.icon:SetDesaturated(not on)
        if on then
            -- rounded as the HUD's buff chips (the stock abbreviations, Cafe.ShortTime)
            f.time:SetText(Cafe.ShortTime(left))
        else
            f.time:SetText("-")
        end
        UI.SetColor(f.time, on and C.gold or C.mute)
        f.tip = function()
            local lines = { K.FAMILY_NAMES[f.def.family] or "", { K.BUFF_LONG[f.def.family] or "", C.text, true } }
            if f.def.family == "C" and b and b.coffeeCounts == 0 then
                lines[2] = { Cafe.NoEffectText("C") .. ".", C.dim }
            elseif f.def.family == "M" and on then
                lines[#lines + 1] = b.shakeActive == 1 and { "Speed on", C.teal } or { "Speed off here", C.dim }
            end
            if not on then
                lines[#lines + 1] = { "Not active", C.dim }
            end
            return lines
        end
    end
end

-- The confirmation (the café's own, Cafe.Confirm "order": the kit's shared dialog is never moved) stands beside the
-- menu, never on it: the stock popup's background lets the rows show through, and the question names the drink its own
-- row names. To the right of the menu when the screen has room, else to its left, else over the footer, under the list.
-- Each question opens at Cafe.CONFIRM_HOME first, so a later one of the café's (Bin) is never left here.
MN.DIALOG_GAP = 8
function MN.PlaceDialog(d)
    if not d then
        return
    end
    local scale = (win:GetEffectiveScale() or 1) / (UIParent:GetEffectiveScale() or 1)
    local left, right = win:GetLeft(), win:GetRight()
    local dw = d:GetWidth() or 340
    local gap = MN.DIALOG_GAP
    d:ClearAllPoints()
    if right and right * scale + gap + dw <= (UIParent:GetWidth() or 0) then
        d:SetPoint("LEFT", win, "RIGHT", gap, 0)
        d.cafeSide = "right"
    elseif left and left * scale - gap - dw >= 0 then
        d:SetPoint("RIGHT", win, "LEFT", -gap, 0)
        d.cafeSide = "left"
    else
        d:SetPoint("BOTTOM", win, "BOTTOM", 0, 16)
        d.cafeSide = "footer"
    end
end

-- Order the selected drink, after the confirmation (the server takes the money and may still refuse).
function MN.ConfirmOrder()
    local sel = MN.Selected()
    if not sel then
        return
    end
    local cafeId, tip = MN.CafeId(), MN.tip
    local total = MN.Total(sel.priceCopper, tip)
    local text = "Order " .. sel.recipe.name .. " for " .. Cafe.MoneyPlain(total) .. "?"
    if not sel.effective then
        text = text .. "\n\nThis drink's buff does nothing for you right now."
    end
    local recipeId = sel.recipeId
    MN.PlaceDialog(Cafe.Confirm("order", text, function()
        Cafe.Send("CORDER", cafeId, recipeId, tip)
    end, "Order"))
end

------------------------------------------------------------------------------------------------------
-- Opening and updates
------------------------------------------------------------------------------------------------------
function win:OnOpen()
    local cafeId = MN.CafeId()
    Comm.Refresh("CAFM", cafeId)
    Comm.Refresh("CAFO")
    Comm.Refresh("CAFBF")
    MN.Refresh()
end

function win:OnClose()
    MN.cafeId = nil
    -- the order's confirmation goes with the menu it stands beside (only the café's own question, never another's)
    Cafe.CloseConfirm("order")
end

-- Open the menu (CAFUI menu names the café; a café of the other team is refused by the server anyway).
function MN.Open(cafeId)
    if not Cafe.Enabled() then
        ns.Print("The café is not open on this realm right now.")
        return
    end
    MN.cafeId = (cafeId == 1 or cafeId == 2) and cafeId or nil
    if win:IsShown() then
        win:OnOpen()
    else
        win:Show()
    end
end

UI.RegisterOpener("cafemenu", function(toggle)
    if toggle and win:IsShown() then
        win:Hide()
        return
    end
    MN.Open(MN.cafeId)
end)

-- CAFUI menu names its café: Cafe.lua opens the menu (UI.Open has no café argument), this keeps the one named
ns.On("CAFE_UI", function(what, cafeId)
    if what == "menu" and (cafeId == 1 or cafeId == 2) and cafeId ~= MN.CafeId() and win:IsShown() then
        MN.Open(cafeId)
    end
end)

-- CAFM is answered to a GET only: a change of the order (a new one, delivered, cancelled, expired) changes canOrder and
-- today's count, so the open menu asks again
local lastOrder
local function orderKey(o)
    return o and o.orderId and (o.orderId .. ":" .. (pending(o) and "open" or "done")) or "none"
end

MN.REFRESH_ON = { CAFM = true, CAFO = true, CAFBF = true, CAFE = true, DEF = true }
ns.On("STATE", function(topic)
    if topic == "CAFO" then
        local key = orderKey(S.cafeOrder)
        if lastOrder ~= nil and key ~= lastOrder and win:IsShown() then
            Comm.Refresh("CAFM", MN.CafeId())
        end
        lastOrder = key
    end
    if MN.REFRESH_ON[topic] then
        MN.Refresh()
    end
end)

-- reasons that pass on their own (walking closer, combat ending, the danger leaving, the café's queue moving): the
-- open menu asks again every MN.POLL seconds (Comm.Get's cooldown bounds it as well)
MN.POLL = 3
MN.POLL_REASONS = { cafe_where = true, cafe_combat = true, cafe_paused = true, cafe_cap = true }
function MN.Poll()
    if not win:IsShown() then
        return
    end
    local menu = S.cafeMenu and S.cafeMenu[MN.CafeId()]
    if menu and menu.canOrder == 0 and MN.POLL_REASONS[menu.reason or ""] then
        Comm.Get("CAFM", MN.CafeId())
    end
end

ns.On("HELLO", function()
    if not Cafe.Enabled() then
        win:Hide()
    end
end)

-- the order's countdowns (house, pickup) and the buffs tick while the menu is open
foot.elapsed, foot.pollElapsed = 0, 0
foot:SetScript("OnUpdate", function(self, elapsed)
    self.elapsed = self.elapsed + (elapsed or 0)
    self.pollElapsed = self.pollElapsed + (elapsed or 0)
    if self.pollElapsed >= MN.POLL then
        self.pollElapsed = 0
        MN.Poll()
    end
    if self.elapsed >= 1 then
        self.elapsed = 0
        local o = S.cafeOrder
        if pending(o) and (o.state == "H" or o.state == "R") then
            MN.Refresh()
        else
            MN.RefreshBuffs()
        end
    end
end)
