-- Bleakhold: camping (docs/BleakholdProtocol.md section 16). Everything shown is server state (CAMPST);
-- the client only counts the timers down between messages (ns.CampLeft) and sends intents:
--   CAMP M (make camp), CAMP O,<skill> (place a camp object), CAMP P (pack up), GLIDE, REPAIR.
-- The pieces: a Make camp orb on the minimap ring (with the cooldown under it), the movable Camp frame
-- shown while the player is at a campfire (state, settle and fire timers, warmth and XP bonus, the camp
-- objects with tooltips, Place/Repair/Pack up buttons), a small Warmth/Food indicator away from the fire,
-- the Glide button (cooldown on it) and key binding (BleakholdGlide, Bindings.xml), /makecamp (/campfire), /glide,
-- /repair.
-- Features: 512 camping, 1024 glide, 2048 field repair; everything of a feature the realm has off hides.
local ADDON, ns = ...
local U, UI, Comm, Data = ns.U, ns.UI, ns.Comm, ns.Data
local C = UI.C
local S = ns.S

local floor, ceil = math.floor, math.ceil

local CP = {}
ns.Camp = CP

CP.W = 250
CP.GAP = 1.25            -- s between two CAMP or two GLIDE intents (the server allows one a second)
CP.REPAIR_GAP = 2.25     -- s between two REPAIR (the server allows one per two seconds)
CP.MAX_OBJECTS = 8       -- icons drawn (the server sends at most 8; a fire holds 3)
CP.MAX_PLACE = 6         -- place buttons drawn
CP.ICONS = "Interface\\Icons\\"
CP.UNKNOWN_ICON = "INV_Misc_QuestionMark"
CP.GLIDE_ICON = "Spell_Magic_FeatherFall"

local function featureCamp()
    return Comm.HasFeature(Comm.FEATURE.CAMP)
end

local function featureGlide()
    return Comm.HasFeature(Comm.FEATURE.GLIDE)
end

local function featureRepair()
    return Comm.HasFeature(Comm.FEATURE.FIELD_REPAIR) or featureCamp()
end

-- Seconds left of a camp timer, or nil (no state / the field was empty).
local function leftOf(key, c)
    return ns.CampLeft(key, c)
end

-- Profession and camp object names (Data.campProfessions; unknown skill lines still draw).
function CP.Profession(skill)
    return Data.campProfessions[skill] or { name = "Profession #" .. tostring(skill), icon = CP.UNKNOWN_ICON, tiers = {} }
end

-- A stock icon; a file the client cannot load leaves the old texture (Script_SetTexture), so fall back.
local function setIcon(tex, name)
    if not tex:SetTexture(CP.ICONS .. (name or CP.UNKNOWN_ICON)) then
        tex:SetTexture(CP.ICONS .. CP.UNKNOWN_ICON)
    end
end

-- The tooltip of a camp object: name, profession and tier, the buff.
local function objectLines(e)
    local p, name, buff = CP.ObjectInfo(e.skill, e.tier)
    local lines = { name, { p.name .. " - " .. (Data.campTierNames[e.tier] or ("tier " .. e.tier)), C.mid } }
    if buff then
        lines[#lines + 1] = { buff, C.teal, true }
    end
    return lines
end

-- A refusal the client can tell by itself: the same sentence as the server's ERR (Data.errorTexts).
local function notice(code, text)
    text = text or ns.ErrorText({ code = code })
    if text and UIErrorsFrame then
        UIErrorsFrame:AddMessage(text, 1, 0.45, 0.4)
    elseif text then
        ns.Print(text)
    end
end

function CP.ObjectInfo(skill, tier)
    local p = CP.Profession(skill)
    local t = p.tiers[tier] or {}
    return p, t.name or (p.name .. " camp object"), t.buff
end

------------------------------------------------------------------------------------------------------
-- Sending (one gate per op, a little above the server's per-op cooldown; ERR busy waits a full gap)
------------------------------------------------------------------------------------------------------
local nextAt = {}

local function gapOf(op)
    return op == "REPAIR" and CP.REPAIR_GAP or CP.GAP
end

local function send(op, ...)
    if Comm.outdated then
        notice(nil, "Your Bleakhold addon is out of date.")
        return false
    end
    if not Comm.ready then
        notice(nil, "Not connected to the realm.")
        return false
    end
    local now = GetTime()
    if nextAt[op] and now < nextAt[op] then
        return false
    end
    local ok = Comm.Send(op, ...)
    if ok then
        nextAt[op] = now + gapOf(op)
    end
    return ok and true or false
end

ns.On("ERR", function(e)
    if e and (e.op == "CAMP" or e.op == "GLIDE" or e.op == "REPAIR") and e.code == "busy" then
        nextAt[e.op] = GetTime() + gapOf(e.op)
    end
end)

------------------------------------------------------------------------------------------------------
-- Actions
------------------------------------------------------------------------------------------------------
-- A refusal from the local state also asks for CAMPST again (rate limited), so a stale state mends itself.
local function refuse(code)
    notice(code)
    Comm.Get("CAMPST")
    return false
end

function CP.MakeCamp()
    if not featureCamp() then
        notice("camp_off")
        return false
    end
    local cd = leftOf("cd")
    if cd and cd >= 1 then
        return refuse("camp_cooldown")
    end
    return send("CAMP", "M")
end

function CP.PlaceObject(skill)
    if not featureCamp() or not skill then
        return false
    end
    return send("CAMP", "O", skill)
end

function CP.PackUp()
    if not featureCamp() then
        return false
    end
    return send("CAMP", "P")
end

function CP.Glide()
    if not featureGlide() then
        notice("glide_off")
        return false
    end
    local c = S.camp
    if c and c.glide == nil then
        return refuse("glide_race")
    end
    local cd = leftOf("glide")
    if cd and cd >= 1 then
        return refuse("glide_cooldown")
    end
    return send("GLIDE")
end

function CP.Repair()
    if not featureRepair() then
        notice("repair_off")
        return false
    end
    local c = S.camp
    if c and not c.repair then
        return refuse("repair_skill")
    end
    return send("REPAIR")
end

-- Key binding entry point (Bindings.xml).
function BleakholdGlide()
    CP.Glide()
end

------------------------------------------------------------------------------------------------------
-- The Make camp orb (minimap ring), with the cooldown under it
------------------------------------------------------------------------------------------------------
local function orbLines()
    local lines = { "Make camp" }
    local c = S.camp
    if c and c.state ~= "N" then
        lines[#lines + 1] = { c.state == "C" and "Camping by the fire" or "Resting at a campfire", C.teal }
    end
    local w = leftOf("warmth")
    if w and w >= 1 then
        lines[#lines + 1] = { "Warmth: " .. U.Clock(w) .. " (+" .. (c and c.xp or 0) .. "% XP)", C.goldLight }
    end
    if c and c.fed then
        lines[#lines + 1] = { "Well fed: bonus XP from food", C.goldLight }
    end
    local g = leftOf("glide")
    if g then
        lines[#lines + 1] = { g >= 1 and ("Glide ready in " .. U.Clock(g)) or "Glide ready", C.mid }
    end
    local cd = leftOf("cd")
    if cd and cd >= 1 then
        lines[#lines + 1] = { "You can make camp again in " .. U.Duration(ceil(cd)), C.mute }
    else
        lines[#lines + 1] = { "Click to make camp", C.mute }
    end
    return lines
end

CP.orb = ns.Orbs.Add({
    key = "camp", glyph = "flame", title = "Make camp", angle = 155,
    available = featureCamp,
    onClick = function()
        CP.MakeCamp()
    end,
    lines = orbLines,
    update = function(b)
        local cd = leftOf("cd")
        if cd and cd >= 1 then
            b.cd:SetText(U.Clock(cd))
            b.cd:Show()
            b.glyph:SetVertexColor(UI.Rgb(C.mute))
        else
            b.cd:Hide()
            b.glyph:SetVertexColor(UI.Rgb(C.goldLight))
        end
    end,
})
CP.orb.cd = UI.Text(CP.orb, 10, C.goldLight, "body", "CENTER")
CP.orb.cd:SetPoint("TOP", CP.orb, "BOTTOM", 0, -1)
CP.orb.cd:Hide()

------------------------------------------------------------------------------------------------------
-- Positions (camp frame and indicator): saved like the key tracker's, else a default spot
------------------------------------------------------------------------------------------------------
local function positioning(f, defPoint, defX, defY)
    UI.MakeMovable(f)
    f:SetClampedToScreen(true)
    local t = {}
    function t.Saved()
        local pos = ns.cdb.windows[f:GetName()]
        if type(pos) == "table" and type(pos.point) == "string" and type(pos.x) == "number" and type(pos.y) == "number" then
            return pos
        end
    end
    function t.Anchor()
        local pos = t.Saved()
        f:ClearAllPoints()
        if pos then
            f:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, pos.x, pos.y)
        else
            f:SetPoint(defPoint, UIParent, defPoint, defX, defY)
        end
    end
    function t.MoveTo(region, save)
        local point, relPoint, x, y = UI.TopAnchorOf(region)
        if not point then
            return
        end
        f:ClearAllPoints()
        f:SetPoint(point, UIParent, relPoint, x, y)
        if save then
            ns.cdb.windows[f:GetName()] = { point = point, relPoint = relPoint, x = x, y = y }
        end
    end
    function t.Reset()
        ns.cdb.windows[f:GetName()] = nil
        t.Anchor()
    end
    return t
end

------------------------------------------------------------------------------------------------------
-- The Camp frame: shown while the player is at a campfire (state R or C)
------------------------------------------------------------------------------------------------------
local f = CreateFrame("Frame", "BleakholdCampFrame", UIParent)
f:SetSize(CP.W, 160)
f:SetFrameStrata("MEDIUM")
UI.Backdrop(f, "101216", C.chipBorder, 0.92)
f:Hide()
CP.frame = f
local fpos = positioning(f, "TOPRIGHT", -40, -470)

f.title = UI.Text(f, 15, C.goldPale, "title")
f.title:SetPoint("TOPLEFT", f, "TOPLEFT", 12, -10)
f.title:SetText("Campfire")
f.state = UI.Text(f, 13, C.goldLight, "body", "RIGHT")
f.state:SetPoint("TOPRIGHT", f, "TOPRIGHT", -12, -12)

f.settle = UI.Text(f, 12, C.mid)
f.fire = UI.Text(f, 12, C.dim)
f.warmth = UI.Text(f, 12, C.goldLight)

f.objLabel = UI.Text(f, 11, C.mute)
f.objs = {}
for i = 1, CP.MAX_OBJECTS do
    local o = CreateFrame("Frame", nil, f)
    o:SetSize(26, 26)
    o:EnableMouse(true)
    UI.Backdrop(o, C.chip, C.chipBorder)
    o.icon = o:CreateTexture(nil, "ARTWORK")
    o.icon:SetSize(22, 22)
    o.icon:SetPoint("CENTER")
    o.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    o:SetScript("OnEnter", function(self)
        local e = self.obj
        if not e then
            return
        end
        local lines = objectLines(e)
        if e.mine then
            lines[#lines + 1] = { "Placed by you", C.goldLight }
        end
        UI.ShowTooltip(self, lines)
    end)
    o:SetScript("OnLeave", function()
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    o:Hide()
    f.objs[i] = o
end

f.place = {}
for i = 1, CP.MAX_PLACE do
    local b = UI.Button(f, CP.W - 24, 22, "", "dark", 11)
    b.picon = b:CreateTexture(nil, "ARTWORK")
    b.picon:SetSize(16, 16)
    b.picon:SetPoint("LEFT", b, "LEFT", 4, 0)
    b.picon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    b.label:ClearAllPoints()
    b.label:SetPoint("LEFT", b, "LEFT", 24, 0)
    b.label:SetPoint("RIGHT", b, "RIGHT", -6, 0)
    b:SetScript("OnClick", function(self)
        if self.skill then
            CP.PlaceObject(self.skill)
        end
    end)
    b.tooltip = function()
        local e = f.place[i].entry
        if not e then
            return nil
        end
        local lines = objectLines(e)
        lines[#lines + 1] = { "Everyone settled at this fire gets the buff.", C.mute, true }
        return lines
    end
    b:Hide()
    f.place[i] = b
end

f.repairBtn = UI.Button(f, (CP.W - 30) / 2, 24, "Repair", "gold", 12)
f.repairBtn:SetScript("OnClick", function()
    CP.Repair()
end)
f.repairBtn.tooltip = function()
    return { "Repair", { "Repairs everything you wear and carry, at the usual price (blacksmiths pay less).", C.mid, true } }
end
f.repairBtn:Hide()
f.packBtn = UI.Button(f, (CP.W - 30) / 2, 24, "Pack up", "ghost", 12)
f.packBtn:SetScript("OnClick", function()
    CP.PackUp()
end)
f.packBtn.tooltip = function()
    return { "Pack up", { "Puts out your campfire; the camp objects at it go with it.", C.mid, true } }
end
f.packBtn:Hide()

-- A sample state for placing the frame in AddicatUI's editor mode while not camping.
CP.SAMPLE = {
    state = "C", settle = 0, fire = 620, mine = true, cd = 880, warmth = 1500, xp = 15,
    objs = { { skill = 164, tier = 2, mine = true }, { skill = 171, tier = 1, mine = false } },
    place = { { skill = 185, tier = 1 } }, glide = 0, repair = true, fed = true,
}

-- The state the frame shows: at a fire (the server says R or C) while camping is on; else nothing.
local function live()
    local c = S.camp
    if c and featureCamp() and c.state ~= "N" then
        return c
    end
    return nil
end

function CP.UpdateTimers()
    local c = CP.current
    if not c then
        return
    end
    if c.state == "R" then
        local s = leftOf("settle", c) or 0
        f.settle:SetText("Settled in " .. U.Clock(ceil(s)))
    end
    -- fire 0 at a fire: one that does not go out (a campfire of the world)
    local fire = leftOf("fire", c) or 0
    local burns = (c.fire or 0) > 0 and U.Clock(ceil(fire)) or "keeps burning"
    f.fire:SetText("Fire: " .. burns .. (c.mine and " (yours)" or ""))
    local w = leftOf("warmth", c) or 0
    if (w >= 1 or c.fed) ~= (f.warmth:IsShown() and true or false) then
        return CP.Refresh()   -- the warmth ran out here: lay the frame out again (Refresh agrees with this test)
    end
    if w >= 1 then
        f.warmth:SetText("Warmth " .. U.Clock(ceil(w)) .. ((c.xp or 0) > 0 and (" - +" .. c.xp .. "% XP") or ""))
    elseif c.fed then
        f.warmth:SetText("Well fed" .. ((c.xp or 0) > 0 and (" - +" .. c.xp .. "% XP") or ""))
    end
end

function CP.Refresh()
    local c = live() or (CP.preview and CP.SAMPLE) or nil
    CP.current = c
    if not c then
        f:Hide()
        return
    end
    f.state:SetText(c.state == "C" and "Camping" or "Resting")
    UI.SetColor(f.state, c.state == "C" and C.teal or C.goldLight)
    local y = -32
    if c.state == "R" then
        f.settle:ClearAllPoints()
        f.settle:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y)
        f.settle:Show()
        y = y - 17
    else
        f.settle:Hide()
    end
    f.fire:ClearAllPoints()
    f.fire:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y)
    y = y - 17
    local w = leftOf("warmth", c) or 0
    if w >= 1 or c.fed then
        f.warmth:ClearAllPoints()
        f.warmth:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y)
        f.warmth:Show()
        y = y - 17
    else
        f.warmth:Hide()
    end
    -- the camp objects at this fire
    if #c.objs > 0 then
        f.objLabel:SetText("Camp objects")
        f.objLabel:ClearAllPoints()
        f.objLabel:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y - 4)
        f.objLabel:Show()
        y = y - 19
    else
        f.objLabel:Hide()
    end
    for i, o in ipairs(f.objs) do
        local e = c.objs[i]
        o.obj = e
        if e then
            setIcon(o.icon, CP.Profession(e.skill).icon)
            o:ClearAllPoints()
            o:SetPoint("TOPLEFT", f, "TOPLEFT", 12 + (i - 1) * 29, y)
            o:Show()
        else
            o:Hide()
        end
    end
    if #c.objs > 0 then
        y = y - 30
    end
    -- what the player may place here
    for i, b in ipairs(f.place) do
        local e = c.place[i]
        b.entry = e
        b.skill = e and e.skill
        if e then
            local p, name = CP.ObjectInfo(e.skill, e.tier)
            setIcon(b.picon, p.icon)
            b:SetLabel("Place " .. name)
            b:ClearAllPoints()
            b:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y - 2)
            b:Show()
            y = y - 26
        else
            b:Hide()
        end
    end
    -- repair and pack up
    if c.repair or c.mine then
        y = y - 6
        if c.repair then
            f.repairBtn:ClearAllPoints()
            f.repairBtn:SetPoint("TOPLEFT", f, "TOPLEFT", 12, y)
            f.repairBtn:Show()
        else
            f.repairBtn:Hide()
        end
        if c.mine then
            f.packBtn:ClearAllPoints()
            f.packBtn:SetPoint("TOPRIGHT", f, "TOPRIGHT", -12, y)
            f.packBtn:Show()
        else
            f.packBtn:Hide()
        end
        y = y - 26
    else
        f.repairBtn:Hide()
        f.packBtn:Hide()
    end
    f:SetHeight(-y + 10)
    CP.UpdateTimers()
    if not f:IsShown() then
        fpos.Anchor()
        f:Show()
    end
end

local acc = 0
f:SetScript("OnUpdate", function(self, elapsed)
    acc = acc + (elapsed or 0)
    if acc >= 0.25 then
        acc = 0
        if not CP.preview and CP.current ~= live() then
            CP.Refresh()
        else
            CP.UpdateTimers()
        end
    end
end)

------------------------------------------------------------------------------------------------------
-- The Warmth/Food indicator: a small chip while the bonus runs and the player is not at a fire
------------------------------------------------------------------------------------------------------
local ind = CreateFrame("Frame", "BleakholdCampStatus", UIParent)
ind:SetSize(150, 30)
ind:SetFrameStrata("MEDIUM")
UI.Backdrop(ind, "101216", C.chipBorder, 0.92)
ind:EnableMouse(true)
ind:Hide()
CP.indicator = ind
local ipos = positioning(ind, "TOP", 0, -200)

ind.flame = UI.Glyph(ind, "flame", 16, C.orange)
ind.flame:SetPoint("LEFT", ind, "LEFT", 8, 0)
ind.text = UI.Text(ind, 12, C.goldLight)
ind.text:SetPoint("LEFT", ind.flame, "RIGHT", 6, 0)

ind:SetScript("OnEnter", function(self)
    local c = S.camp or (CP.indPreview and CP.SAMPLE)
    local lines = { "Campfire Warmth" }
    local w = c and leftOf("warmth", c)
    if w and w >= 1 then
        lines[#lines + 1] = { "Warmth: " .. U.Clock(ceil(w)) .. " left", C.goldLight }
    end
    if c and c.fed then
        lines[#lines + 1] = { "Well fed: bonus XP from food", C.goldLight }
    end
    if c and (c.xp or 0) > 0 then
        lines[#lines + 1] = { "+" .. c.xp .. "% experience from kills and quests", C.teal }
    end
    UI.ShowTooltip(self, lines)
end)
ind:SetScript("OnLeave", function()
    if GameTooltip then
        GameTooltip:Hide()
    end
end)

-- The indicator's state: away from any fire, warmth still running or well fed (feature 512).
local function indLive()
    local c = S.camp
    if not c or not featureCamp() or c.state ~= "N" then
        return nil
    end
    local w = leftOf("warmth", c) or 0
    if w >= 1 or c.fed then
        return c
    end
    return nil
end

function CP.RefreshIndicator()
    local c = indLive() or (CP.indPreview and CP.SAMPLE) or nil
    if not c then
        ind:Hide()
        return
    end
    local w = leftOf("warmth", c) or 0
    local xp = (c.xp or 0) > 0 and (" - +" .. c.xp .. "% XP") or ""
    if w >= 1 then
        ind.text:SetText(U.Clock(ceil(w)) .. xp)
    else
        ind.text:SetText("Well fed" .. xp)
    end
    ind:SetWidth(floor(38 + ind.text:GetStringWidth() + 0.5))
    if not ind:IsShown() then
        ipos.Anchor()
        ind:Show()
    end
end

local iacc = 0
ind:SetScript("OnUpdate", function(self, elapsed)
    iacc = iacc + (elapsed or 0)
    if iacc >= 0.5 then
        iacc = 0
        if not CP.indPreview then
            CP.RefreshIndicator()
        end
    end
end)

------------------------------------------------------------------------------------------------------
-- The Glide button: shown while the realm has glide on and the player can glide (CAMPST glide not empty),
-- with the cooldown on it. The key binding (Bindings.xml) does the same.
------------------------------------------------------------------------------------------------------
local gb = CreateFrame("Button", "BleakholdGlideButton", UIParent)
gb:SetSize(36, 36)
gb:SetFrameStrata("MEDIUM")
UI.Backdrop(gb, C.chip, C.gold)
gb:RegisterForClicks("LeftButtonUp")
gb:Hide()
CP.glideButton = gb
local gpos = positioning(gb, "BOTTOM", 0, 190)

gb.icon = gb:CreateTexture(nil, "ARTWORK")
gb.icon:SetSize(32, 32)
gb.icon:SetPoint("CENTER")
gb.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
setIcon(gb.icon, CP.GLIDE_ICON)
gb.cd = UI.Text(gb, 12, C.text, "body", "CENTER", "OVERLAY")
gb.cd:SetPoint("CENTER")
gb.cd:Hide()

gb:SetScript("OnClick", function()
    CP.Glide()
end)
gb:SetScript("OnEnter", function(self)
    local lines = { "Glide", { "Float down slowly instead of falling (High Elves).", C.mid, true } }
    local left = leftOf("glide")
    lines[#lines + 1] = { (left and left >= 1) and ("Ready in " .. U.Clock(ceil(left))) or "Ready", C.goldLight }
    local key = GetBindingKey and GetBindingKey("BLEAKHOLD_GLIDE")
    lines[#lines + 1] = { key and ("Key: " .. key) or "Bind a key: Key Bindings, Bleakhold, Glide", C.mute }
    UI.ShowTooltip(self, lines)
end)
gb:SetScript("OnLeave", function()
    if GameTooltip then
        GameTooltip:Hide()
    end
end)

local function glideLive()
    local c = S.camp
    return (featureGlide() and c and c.glide ~= nil) and c or nil
end

function CP.UpdateGlide()
    local left = leftOf("glide") or 0
    if left >= 1 then
        gb.cd:SetText(left >= 60 and U.Clock(ceil(left)) or tostring(ceil(left)))
        gb.cd:Show()
        gb.icon:SetDesaturated(true)
        gb.icon:SetVertexColor(0.6, 0.6, 0.6)
    else
        gb.cd:Hide()
        gb.icon:SetDesaturated(false)
        gb.icon:SetVertexColor(1, 1, 1)
    end
end

function CP.RefreshGlide()
    if not (glideLive() or CP.glidePreview) then
        gb:Hide()
        return
    end
    CP.UpdateGlide()
    if not gb:IsShown() then
        gpos.Anchor()
        gb:Show()
    end
end

local gacc = 0
gb:SetScript("OnUpdate", function(self, elapsed)
    gacc = gacc + (elapsed or 0)
    if gacc >= 0.25 then
        gacc = 0
        if not CP.glidePreview and not glideLive() then
            gb:Hide()
        else
            CP.UpdateGlide()
        end
    end
end)

------------------------------------------------------------------------------------------------------
-- Wiring: a CAMPST or a HELLO (feature bits) redraws everything; the shown frames keep their own timers
-- (OnUpdate runs only while a frame is shown, so nothing ticks while nothing is up).
------------------------------------------------------------------------------------------------------
function CP.RefreshAll()
    ns.Orbs.Refresh()
    CP.Refresh()
    CP.RefreshIndicator()
    CP.RefreshGlide()
end

ns.On("STATE", function(topic)
    if topic == "CAMPST" then
        CP.RefreshAll()
    end
end)

ns.On("HELLO", CP.RefreshAll)

ns.On("CAMP_SETTLED", function(c)
    ns.Toast.Push({
        kicker = "CAMP",
        title = "Camp settled",
        sub = (c.xp or 0) > 0 and ("+" .. c.xp .. "% experience by the fire") or "The fire keeps you warm",
    })
end)

ns.On("DB_READY", function()
    fpos.Anchor()
    ipos.Anchor()
    gpos.Anchor()
end)

------------------------------------------------------------------------------------------------------
-- Slash commands: /bh camp|glide|repair, /makecamp and /campfire always (never /camp, the stock logout); /glide
-- and /repair unless another addon took them first, like the dances' own slash commands.
------------------------------------------------------------------------------------------------------
ns.AddCommand("camp", "make camp here (/bh camp pack packs it up)", function(args)
    CP.CampCommand(args)
end)

ns.AddCommand("glide", "glide down slowly instead of falling (High Elves)", function()
    CP.Glide()
end)

ns.AddCommand("repair", "repair your gear in the field", function()
    CP.Repair()
end)

local function addSlash(id, cmd, fn)
    for name in pairs(SlashCmdList) do
        local i = 1
        while _G["SLASH_" .. name .. i] do
            if string.lower(_G["SLASH_" .. name .. i]) == cmd then
                return
            end
            i = i + 1
        end
    end
    _G["SLASH_" .. id .. "1"] = cmd
    SlashCmdList[id] = fn
end

function CP.CampCommand(msg)
    local want = (strtrim and strtrim(msg or "") or (msg or "")):lower()
    if want == "pack" or want == "packup" then
        CP.PackUp()
    else
        CP.MakeCamp()
    end
end

-- /camp stays the stock client's logout alias (SLASH_LOGOUT): players who type it to log out must not get a fire.
SLASH_BLEAKHOLDMAKECAMP1 = "/makecamp"
SLASH_BLEAKHOLDMAKECAMP2 = "/campfire"
SlashCmdList.BLEAKHOLDMAKECAMP = CP.CampCommand

addSlash("BLEAKHOLDGLIDE", "/glide", function()
    CP.Glide()
end)
addSlash("BLEAKHOLDREPAIR", "/repair", function()
    CP.Repair()
end)

------------------------------------------------------------------------------------------------------
-- Editor mode (ns.Movers): sample content while nothing real is on, so there is a frame to place
------------------------------------------------------------------------------------------------------
UI.AddMover({
    name = "bleakhold_camp",
    title = "Camp frame",
    frame = f,
    begin = function()
        CP.preview = true
        CP.SAMPLE.recvAt = GetTime()
        CP.Refresh()
    end,
    finish = function()
        CP.preview = nil
        CP.Refresh()
    end,
    move = function(region, done)
        fpos.MoveTo(region, done)
    end,
    reset = function()
        fpos.Reset()
    end,
    isDefault = function()
        return fpos.Saved() == nil
    end,
    visible = function()
        return featureCamp() and true or false
    end,
})

UI.AddMover({
    name = "bleakhold_camp_status",
    title = "Warmth indicator",
    frame = ind,
    begin = function()
        CP.indPreview = true
        CP.SAMPLE.recvAt = GetTime()
        CP.RefreshIndicator()
    end,
    finish = function()
        CP.indPreview = nil
        CP.RefreshIndicator()
    end,
    move = function(region, done)
        ipos.MoveTo(region, done)
    end,
    reset = function()
        ipos.Reset()
    end,
    isDefault = function()
        return ipos.Saved() == nil
    end,
    visible = function()
        return featureCamp() and true or false
    end,
})

UI.AddMover({
    name = "bleakhold_glide",
    title = "Glide button",
    frame = gb,
    begin = function()
        CP.glidePreview = true
        CP.RefreshGlide()
    end,
    finish = function()
        CP.glidePreview = nil
        CP.RefreshGlide()
    end,
    move = function(region, done)
        gpos.MoveTo(region, done)
    end,
    reset = function()
        gpos.Reset()
    end,
    isDefault = function()
        return gpos.Saved() == nil
    end,
    visible = function()
        return featureGlide() and true or false
    end,
})
