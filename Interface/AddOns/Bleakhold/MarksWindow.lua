-- Bleakhold: the Markings window (docs/BleakholdProtocol.md, section 22), in the stock look of the café's windows
-- (CafeWindow.lua: the dialog frame with a ring portrait, gold headings, quest-log rows, red panel buttons; no art of
-- its own):
--   left    the player on a DressUpModel (Bleakhold.exe gives it the player's marks, so it shows the preview too), the
--           character pane's rotate buttons under it
--   right   Design (None and the race-sex's four designs), Colour (its three colours as swatches, "glows" or
--           "paint"), Eyes (your own, the three eye colours, and Blood Red and Unholy Green for Death Knights; only
--           those DEF N has), a note, Show other players' marks (marksOthers), the price ("Free" or coins), the
--           cooldown, Accept and Cancel
-- Every pick previews on the player only (ns.Marks.Preview); Cancel, the close button and hiding the window put the
-- player's applied entry back. Accept sends MARKSET with the price the window showed; an ERR gives the pick back and
-- says why, the player's own MARK ends the preview with the server's state. Opener: markings (/bh marks).
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S
local Marks = ns.Marks

local ceil, max = math.ceil, math.max

local W = {}
ns.MarksWindow = W

W.W, W.H = 640, 440
W.MODEL_W = 230
W.RIGHT_X = W.MODEL_W + 16
W.COL_W = 176
W.EYES_X = W.RIGHT_X + W.COL_W + 12
W.ROW_H, W.ROW_PITCH = 20, 22
W.ROTATE = 2.5                  -- radians per second while a rotate button is held (Model_RotateLeft's speed)
W.ICON = "Interface\\Icons\\INV_Inscription_Tradeskill01"
W.ROTATE_ART = { left = "Interface\\Buttons\\UI-RotationLeft-Button-",
    right = "Interface\\Buttons\\UI-RotationRight-Button-" }

W.TEXT = {
    notOffered = "Marks are not made for this body yet.",
    noClient = "The glow needs the current Bleakhold client. Your choice is still kept on the realm.",
    pending = "Changing your markings...",
    offline = "Not connected to the realm.",
    noAnswer = "The realm did not answer. Try again in a moment.",
}

local win = UI.Window("BleakholdMarkingsFrame", W.W, W.H, "Markings", W.ICON)
W.frame = win
local CW, CH = UI.ContentSize(W.W, W.H)

------------------------------------------------------------------------------------------------------
-- The model
------------------------------------------------------------------------------------------------------
local box = UI.Box(win.content, W.MODEL_W, CH - 42, C.card, C.border, nil, "edge")
box:SetPoint("TOPLEFT", win.content, "TOPLEFT", 0, 0)
local model = CreateFrame("DressUpModel", nil, box)
model:SetPoint("TOPLEFT", box, "TOPLEFT", 1, -1)
model:SetPoint("BOTTOMRIGHT", box, "BOTTOMRIGHT", -1, 1)
model:EnableMouse(true)
model:SetScript("OnMouseDown", function(self)
    self.turning = true
    self.lastX = GetCursorPosition()
end)
model:SetScript("OnMouseUp", function(self)
    self.turning = false
end)
model:SetScript("OnUpdate", function(self, elapsed)
    if self.turning then
        local x = GetCursorPosition()
        if x and self.lastX then
            self:SetFacing((self:GetFacing() or 0) + (x - self.lastX) * 0.02)
            self.lastX = x
        end
    elseif self.spin then
        self:SetFacing((self:GetFacing() or 0) + self.spin * W.ROTATE * (elapsed or 0))
    end
end)
W.model = model

-- the character pane's rotate buttons: turn while held
local function rotateButton(side, dir)
    local b = CreateFrame("Button", nil, win.content)
    b:SetSize(35, 35)
    b:SetNormalTexture(W.ROTATE_ART[side] .. "Up")
    b:SetPushedTexture(W.ROTATE_ART[side] .. "Down")
    b:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Round", "ADD")
    b:SetScript("OnMouseDown", function()
        model.spin = dir
    end)
    b:SetScript("OnMouseUp", function()
        model.spin = nil
    end)
    b:SetScript("OnHide", function()
        model.spin = nil
    end)
    return b
end
W.rotateLeft = rotateButton("left", 1)
W.rotateLeft:SetPoint("TOPRIGHT", box, "BOTTOM", -2, -4)
W.rotateRight = rotateButton("right", -1)
W.rotateRight:SetPoint("TOPLEFT", box, "BOTTOM", 2, -4)

------------------------------------------------------------------------------------------------------
-- The choices
------------------------------------------------------------------------------------------------------
-- a quest-log row: the check on the chosen one, the label 22 px in (after the check), an optional swatch before it
-- and a dim tag at its right end; r.value is the choice it stands for
local function choiceRow(parent, w, value, swatch)
    local r = UI.Button(parent, w, W.ROW_H, "", "row", 12)
    r.value = value
    local x = 22
    if swatch then
        r.swatch = UI.Solid(r, C.text, "ARTWORK")
        r.swatch:SetSize(12, 12)
        r.swatch:SetPoint("LEFT", r, "LEFT", 22, 0)
        r.swatchRim = r:CreateTexture(nil, "BORDER")
        r.swatchRim:SetTexture(0, 0, 0, 1)
        r.swatchRim:SetSize(14, 14)
        r.swatchRim:SetPoint("CENTER", r.swatch, "CENTER", 0, 0)
        x = 40
    end
    r.label:ClearAllPoints()
    r.label:SetPoint("LEFT", r, "LEFT", x, 0)
    r.label:SetPoint("RIGHT", r, "RIGHT", -44, 0)
    r.label:SetJustifyH("LEFT")
    r.tag = UI.Text(r, 10, C.dim, "body", "RIGHT")
    r.tag:SetPoint("RIGHT", r, "RIGHT", -4, 0)
    return r
end

local function column(x, y, title)
    local h = UI.Heading(win.content, title, 13)
    h:SetPoint("TOPLEFT", win.content, "TOPLEFT", x, y)
    return h
end

W.designHead = column(W.RIGHT_X, 0, "Design")
W.designRows = {}
for i = 0, 4 do
    local r = choiceRow(win.content, W.COL_W, i)
    r:SetPoint("TOPLEFT", win.content, "TOPLEFT", W.RIGHT_X, -20 - i * W.ROW_PITCH)
    r:SetScript("OnClick", function(self)
        W.Pick("design", self.value)
    end)
    W.designRows[i] = r
end

local COLOUR_Y = -20 - 5 * W.ROW_PITCH - 12
W.colourHead = column(W.RIGHT_X, COLOUR_Y, "Colour")
W.colourRows = {}
for i = 1, 3 do
    local r = choiceRow(win.content, W.COL_W, i, true)
    r:SetPoint("TOPLEFT", win.content, "TOPLEFT", W.RIGHT_X, COLOUR_Y - 20 - (i - 1) * W.ROW_PITCH)
    r:SetScript("OnClick", function(self)
        W.Pick("colour", self.value)
    end)
    W.colourRows[i] = r
end

W.eyesHead = column(W.EYES_X, 0, "Eyes")
W.eyeRows = {}
for i = 0, 5 do
    local r = choiceRow(win.content, CW - W.EYES_X, i, i > 0)
    r:SetPoint("TOPLEFT", win.content, "TOPLEFT", W.EYES_X, -20 - i * W.ROW_PITCH)
    r:SetScript("OnClick", function(self)
        W.Pick("eye", self.value)
    end)
    W.eyeRows[i] = r
end

local NOTE_Y = COLOUR_Y - 20 - 3 * W.ROW_PITCH - 14
W.note = UI.Para(win.content, 11, C.dim, CW - W.RIGHT_X)
W.note:SetPoint("TOPLEFT", win.content, "TOPLEFT", W.RIGHT_X, NOTE_Y)

-- the option marksOthers (/bh marks others on|off)
W.others = UI.CheckButton(win.content, "Show other players' marks", 22)
W.others:SetPoint("BOTTOMLEFT", win.content, "BOTTOMLEFT", W.RIGHT_X - 3, 54)
W.others:SetScript("OnClick", function(self)
    Marks.SetOthers(self:GetChecked() and true or false)
    self:SetChecked(Marks.Others())
end)

------------------------------------------------------------------------------------------------------
-- Price, cooldown, Accept and Cancel
------------------------------------------------------------------------------------------------------
W.priceLabel = UI.Label(win.content, "Price", 12)
W.priceLabel:SetPoint("BOTTOMLEFT", win.content, "BOTTOMLEFT", W.RIGHT_X, 34)
W.free = UI.Text(win.content, 12, C.teal)
W.free:SetPoint("LEFT", W.priceLabel, "RIGHT", 8, 0)
W.free:SetText("Free")
W.money = ns.Cafe.MoneyFrame(win.content, 12)
W.money:SetPoint("LEFT", W.priceLabel, "RIGHT", 8, 0)
W.cooldown = UI.Text(win.content, 11, C.dim)
W.cooldown:SetPoint("BOTTOMLEFT", win.content, "BOTTOMLEFT", W.RIGHT_X, 6)
UI.OneLine(W.cooldown, CW - W.RIGHT_X - 230)

W.cancel = UI.Button(win.content, 110, 22, "Cancel", "red")
W.cancel:SetPoint("BOTTOMRIGHT", win.content, "BOTTOMRIGHT", 0, 2)
W.cancel:SetScript("OnClick", function()
    win:Hide()
end)
W.accept = UI.Button(win.content, 110, 22, "Accept", "red")
W.accept:SetPoint("RIGHT", W.cancel, "LEFT", -6, 0)
W.accept:SetScript("OnClick", function()
    W.Accept()
end)

------------------------------------------------------------------------------------------------------
-- State
------------------------------------------------------------------------------------------------------
W.pick = { design = 0, colour = 0, eye = 0 }
W.dirty = false           -- the player picked something since the window showed the server's state
W.pending = nil           -- a MARKSET waiting for its answer
W.message = nil           -- the last refusal, shown in the note

-- the applied choice: MARKME's, else the player's list entry, else none
function W.Current()
    local m = S.markMe
    if m then
        return m.design, m.colour, m.eye
    end
    local own = Marks.PlayerGuid() and S.marks[Marks.PlayerGuid()]
    if own then
        return own.design, own.colour, own.eye
    end
    return 0, 0, 0
end

function W.ResetPicks()
    local d, c, e = W.Current()
    W.pick.design, W.pick.colour, W.pick.eye = d, c, e
    W.dirty = false
end

function W.IsNone(p)
    p = p or W.pick
    return p.design == 0 and p.eye == 0
end

function W.Same()
    local d, c, e = W.Current()
    local p = W.pick
    return p.design == d and p.colour == c and p.eye == e
end

-- what the pick costs: a change to nothing at all is free, else MARKME's price (0 while the next change is free)
function W.Price()
    if W.IsNone() then
        return 0
    end
    return S.markMe and S.markMe.price or 0
end

-- the eyes the player may pick: those of DEF N, 4 and 5 only for Death Knights
function W.EyeOffered(i, def)
    local e = def and def.eyes[i]
    return e ~= nil and (not e.dkOnly or Marks.IsDeathKnight())
end

function W.Pick(kind, value)
    local p = W.pick
    if kind == "design" then
        if value > 0 and p.design == 0 then
            p.colour = W.lastColour or 1
        elseif value == 0 then
            if p.colour > 0 then
                W.lastColour = p.colour
            end
            p.colour = 0
        end
        p.design = value
    elseif kind == "colour" then
        if p.design == 0 then
            return
        end
        p.colour = value
    elseif kind == "eye" then
        p.eye = value
    end
    W.dirty = true
    W.message = nil
    Marks.Preview(p.design, p.colour, p.eye)
    W.Refresh()
end

-- why Accept is greyed (nil: it is not)
function W.Blocked()
    local m = S.markMe
    if not m then
        return "nostate"
    end
    if W.pending then
        return "pending"
    end
    if m.offered == 0 then
        return "offered"
    end
    if W.Same() then
        return "same"
    end
    if Marks.CooldownLeft() > 0 then
        return "cooldown"
    end
    if (GetMoney and GetMoney() or 0) < W.Price() then
        return "gold"
    end
    return nil
end

function W.Accept()
    if W.Blocked() then
        return
    end
    local p = W.pick
    local ok, why = Marks.Send(p.design, p.colour, p.eye, W.Price())
    if not ok and why == "wait" then
        -- right after an answer the gate is still shut: the pick goes out once it opens (unless it was given back)
        local token = {}
        W.pending = token
        ns.After(Marks.GateLeft() + 0.05, function()
            if W.pending == token then
                W.pending = nil
                W.Accept()
            end
        end)
        W.Refresh()
        return
    end
    if not ok then
        W.message = W.TEXT[why] or W.TEXT.offline
        W.Refresh()
        return
    end
    local token = {}
    W.pending = token
    ns.After(Marks.PENDING_WAIT, function()
        if W.pending == token then
            W.pending = nil
            W.message = W.TEXT.noAnswer
            Marks.EndPreview()
            W.ResetPicks()
            W.Refresh()
        end
    end)
    W.Refresh()
end

------------------------------------------------------------------------------------------------------
-- Refresh
------------------------------------------------------------------------------------------------------
local function chosen(r, on, active)
    r:SetStyle(on and "rowOn" or "row")
    r:SetActive(active ~= false)
end

function W.Refresh()
    if not win:IsShown() then
        return
    end
    local _, _, def = Marks.PlayerBody()
    local p = W.pick
    local offered = S.markMe == nil or S.markMe.offered ~= 0
    -- Design: None, then the race-sex's designs
    for i = 0, 4 do
        local r, d = W.designRows[i], def and def.designs[i]
        if i == 0 then
            r:SetLabel("None")
            r:Show()
        elseif d and offered then
            r:SetLabel(U.Safe(d.name))
            r:Show()
        else
            r:Hide()
        end
        chosen(r, p.design == i)
    end
    -- Colour: only with a design
    for i, r in ipairs(W.colourRows) do
        local c = def and def.colours[i]
        if c and offered then
            r:SetLabel(U.Safe(c.name))
            r.swatch:SetVertexColor(UI.Rgb(c.hex or C.text))
            r.tag:SetText(c.glow and "glows" or "paint")
            r:Show()
        else
            r:Hide()
        end
        chosen(r, p.colour == i, p.design > 0)
    end
    -- Eyes: your own, then those of DEF N this character may have
    local y = 0
    for i = 0, 5 do
        local r, e = W.eyeRows[i], def and def.eyes[i]
        if i == 0 or (offered and W.EyeOffered(i, def)) then
            r:SetLabel(i == 0 and "Your own" or U.Safe(e.name))
            if r.swatch then
                r.swatch:SetVertexColor(UI.Rgb(e.hex or C.text))
            end
            r:ClearAllPoints()
            r:SetPoint("TOPLEFT", win.content, "TOPLEFT", W.EYES_X, -20 - y * W.ROW_PITCH)
            r:Show()
            y = y + 1
        else
            r:Hide()
        end
        chosen(r, p.eye == i)
    end
    -- price and cooldown
    local price = W.Price()
    if price > 0 then
        W.free:Hide()
        W.money:SetCopper(price)
        W.money:Show()
    else
        W.money:Hide()
        W.free:Show()
    end
    local left = Marks.CooldownLeft()
    W.cooldown:SetText(left > 0 and ("Next change in " .. ceil(left / 60) .. " min") or "")
    -- the note: a refusal, the wait, what keeps Accept grey, the client
    local lines = {}
    local blocked = W.Blocked()
    if W.message then
        lines[#lines + 1] = "|cffFF4040" .. W.message .. "|r"
    end
    if blocked == "pending" then
        lines[#lines + 1] = W.TEXT.pending
    elseif blocked == "offered" then
        lines[#lines + 1] = W.TEXT.notOffered
    elseif blocked == "gold" then
        lines[#lines + 1] = "You need " .. ns.Cafe.MoneyPlain(price) .. "."
    end
    if not Marks.HasNatives() then
        lines[#lines + 1] = W.TEXT.noClient
    end
    W.note:SetText(table.concat(lines, "\n"))
    W.others:SetChecked(Marks.Others())
    W.accept:SetActive(blocked == nil)
end

-- the cooldown counts down while the window is open
win.elapsed = 0
win:SetScript("OnUpdate", function(self, elapsed)
    self.elapsed = self.elapsed + (elapsed or 0)
    if self.elapsed >= 1 then
        self.elapsed = 0
        W.Refresh()
    end
end)

function win:OnOpen()
    W.message, W.pending = nil, nil
    W.ResetPicks()
    model:SetUnit("player")
    model:SetFacing(0)
    Comm.Refresh("MARKME")
    W.Refresh()
end

function win:OnClose()
    model.spin = nil
    W.pending = nil
    Marks.EndPreview()
    W.ResetPicks()
end

ns.On("STATE", function(topic)
    if not win:IsShown() then
        return
    end
    if topic == "MARKME" then
        -- the answer to Accept (the player's own MARK follows and ends the preview), or a refresh
        if W.pending or not W.dirty then
            W.ResetPicks()
        end
        W.pending = nil
        W.Refresh()
    elseif topic == "MARKS" or topic == "DEF" then
        W.Refresh()
    end
end)

-- the player's own MARK: the change went through (or came from elsewhere); the server's state is shown
ns.On("MARKS_OWN", function()
    W.pending = nil
    W.ResetPicks()
    W.Refresh()
end)

ns.On("ERR", function(e)
    if not (e and e.op == "MARKSET") or not win:IsShown() then
        return
    end
    W.pending = nil
    W.message = e.shown or U.Safe(e.code or "")
    Marks.EndPreview()
    W.ResetPicks()
    W.Refresh()
end)

ns.On("HELLO", function()
    if not Marks.Available() then
        win:Hide()
    end
end)

UI.RegisterOpener("markings", function(toggle)
    if not Marks.Available() then
        ns.Print("glowing marks are not on for you on this realm.")
        return
    end
    if win:IsShown() then
        if toggle then
            win:Hide()
        end
        return
    end
    win:Show()
end)
