-- Bleakhold: camping (docs/BleakholdProtocol.md section 16). Everything shown is server state (CAMPST);
-- the client only counts the timers down between messages (ns.CampLeft) and sends intents:
--   CAMP M (make camp), CAMP O,<skill> (place a camp object), CAMP P (pack up), GLIDE, REPAIR.
-- The pieces: a Make camp orb on the minimap ring (with the cooldown under it), the movable Camp frame
-- shown while the player is at a campfire (state, settle and fire timers, warmth and XP bonus, the camp
-- objects with tooltips, Place/Repair/Pack up buttons), a small Warmth/Food indicator away from the fire,
-- the Glide button for Walk on Air (cooldown on it, a glide bar over it while a glide runs; it makes way for the
-- spellbook's Walk on Air once the server taught it) and its key binding (BleakholdGlide, Bindings.xml), Make camp's
-- key binding (BleakholdMakeCamp) and launcher entry (Integration.lua), /makecamp (/campfire), /glide, /repair.
-- Features: 512 camping, 1024 glide, 2048 field repair; everything of a feature the realm has off hides.
local ADDON, ns = ...
local U, UI, Comm, Data = ns.U, ns.UI, ns.Comm, ns.Data
local C = UI.C
local S = ns.S

local floor, ceil, max = math.floor, math.ceil, math.max
local strformat = string.format

local CP = {}
ns.Camp = CP

CP.W = 250
CP.GAP = 1.25            -- s between two CAMP or two GLIDE intents (the server allows one a second)
CP.REPAIR_GAP = 2.25     -- s between two REPAIR (the server allows one per two seconds)
CP.MAX_OBJECTS = 8       -- icons drawn (the server sends at most 8; a fire holds 3)
CP.MAX_PLACE = 6         -- place buttons drawn
CP.ICONS = "Interface\\Icons\\"
CP.UNKNOWN_ICON = "INV_Misc_QuestionMark"
CP.GLIDE_ICON = "Spell_Magic_FeatherFall"      -- the spellbook racial's icon (SpellIcon 505, races.json 100801)
CP.GLIDE_NAME = "Walk on Air"
-- Walk on Air in the spellbook (mod-bleakhold-ui's BleakholdUi.Glide.CastSpell, taught at login to who can glide): its
-- action bar button does what the Glide button does, sharing the cooldown, so the Glide button makes way for it.
CP.GLIDE_SPELL = 100801
-- The cast fails on the ground with SPELL_FAILED_NOT_ON_GROUND (the server's spell script); the client shows that
-- string. Other things give that result too (the server's item_only_for_flight: Arcane Charges, 34475, used off the
-- Isle of Quel'Danas flight), so it is reworded only while the player knows Walk on Air (CP.WordGroundError), and
-- worded so it stays true for those: the stock text comes back once the spell is gone.
CP.NOT_ON_GROUND_TEXT = "You must be in the air for that. To glide: jump, or step off a ledge, first."
CP.STOCK_NOT_ON_GROUND = SPELL_FAILED_NOT_ON_GROUND
-- (no seconds here: BleakholdUi.Glide.Duration may differ; the glide bar and the tooltip's Gliding line show them)
CP.GLIDE_TEXT = "Glide through the air, steering your descent. Does not gain altitude."
CP.GLIDE_HOW = "Use it while you fall, or just before you step off a ledge: its time runs from the moment you use it. "
    .. "Turn to steer; landing ends it."

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

-- Whether intents can go out: the realm answered HELLO with a protocol this addon speaks. The actions check this
-- before the feature bits, which read as all off until HELLO is answered.
local function connected()
    if Comm.outdated then
        notice(nil, "Your Bleakhold addon is out of date.")
        return false
    end
    if not Comm.ready then
        notice(nil, "Not connected to the realm.")
        return false
    end
    return true
end

local function send(op, ...)
    if not connected() then
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
    if not connected() then
        return false
    end
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
    if not connected() then
        return false
    end
    if not featureCamp() then
        notice("camp_off")
        return false
    end
    return send("CAMP", "P")
end

function CP.Glide()
    if not connected() then
        return false
    end
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
    if not connected() then
        return false
    end
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

-- Key binding entry points (Bindings.xml).
function BleakholdGlide()
    CP.Glide()
end

function BleakholdMakeCamp()
    CP.MakeCamp()
end

-- Make camp in AddicatUI's micro menu launcher (Integration.lua), for while the minimap orbs are off: listed while
-- the realm has camping on, its tooltip line with the cooldown the orb shows.
CP.MAKE_CAMP_TEXT = "Light a campfire here: Warmth, and bonus experience once the camp settles."

function CP.CampAvailable()
    return featureCamp() and true or false
end

function CP.MakeCampText()
    local cd = leftOf("cd")
    if cd and cd >= 1 then
        return CP.MAKE_CAMP_TEXT .. "\nYou can make camp again in " .. U.Duration(ceil(cd)) .. "."
    end
    return CP.MAKE_CAMP_TEXT
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
        lines[#lines + 1] = { g >= 1 and (CP.GLIDE_NAME .. " ready in " .. U.Clock(g)) or (CP.GLIDE_NAME .. " ready"), C.mid }
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
        else
            b.cd:Hide()
        end
        -- the stock buttons grey a picture that cannot be used now
        b.glyph:SetDesaturated(cd and cd >= 1 or false)
    end,
})
CP.orb.cd = UI.Text(CP.orb, 10, C.text, "body", "CENTER")
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
-- The look: the tooltip frame (UI-Tooltip-Background and -Border, tinted dark as the old window's panels), the title
-- gold, the state on the right (green while camping), the timers white and grey, the camp objects as item slots
-- (ItemButtonTemplate: the icon in UI-Quickslot2), red panel buttons.
local f = CreateFrame("Frame", "BleakholdCampFrame", UIParent)
f:SetSize(CP.W, 160)
f:SetFrameStrata("MEDIUM")
UI.Backdrop(f, C.panel, C.border, nil, "panel")
f:Hide()
CP.frame = f
local fpos = positioning(f, "TOPRIGHT", -40, -470)

f.title = UI.Heading(f, "Campfire", 14)
f.title:SetPoint("TOPLEFT", f, "TOPLEFT", 12, -10)
f.state = UI.Text(f, 12, C.gold, "body", "RIGHT")
f.state:SetPoint("TOPRIGHT", f, "TOPRIGHT", -12, -11)

f.settle = UI.Text(f, 12, C.text)
f.fire = UI.Text(f, 12, C.dim)
f.warmth = UI.Text(f, 12, C.gold)

f.objLabel = UI.Label(f, nil, 11)
f.objs = {}
for i = 1, CP.MAX_OBJECTS do
    local o = UI.ItemButton(f, 26)
    o:EnableMouse(true)
    o.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    o:SetScript("OnEnter", function(self)
        local e = self.obj
        if not e then
            return
        end
        local lines = objectLines(e)
        if e.mine then
            lines[#lines + 1] = { "Placed by you", C.gold }
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
    -- the object's icon clear of the red button's 12 px left cap, in the 1 px black edge of a square icon
    b.picon = b:CreateTexture(nil, "ARTWORK")
    b.picon:SetSize(14, 14)
    b.picon:SetPoint("LEFT", b, "LEFT", 8, 0)
    b.picon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    b.pedge = b:CreateTexture(nil, "BORDER")
    b.pedge:SetTexture(0, 0, 0, 1)
    b.pedge:SetPoint("TOPLEFT", b.picon, "TOPLEFT", -1, 1)
    b.pedge:SetPoint("BOTTOMRIGHT", b.picon, "BOTTOMRIGHT", 1, -1)
    b.label:ClearAllPoints()
    b.label:SetPoint("LEFT", b, "LEFT", 26, 0)
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
f.packBtn = UI.Button(f, (CP.W - 30) / 2, 24, "Pack up", "gold", 12)
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
    UI.SetColor(f.state, c.state == "C" and C.teal or C.gold)
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
        f.objLabel:SetLabel("Camp objects")
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
            o:SetPoint("TOPLEFT", f, "TOPLEFT", 14 + (i - 1) * 31, y - 2)
            o:Show()
        else
            o:Hide()
        end
    end
    if #c.objs > 0 then
        y = y - 34
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
    f:SetHeight(-y + 12)
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
-- (a one-line tooltip frame: the campfire's icon and the time in gold)
CP.WARMTH_ICON = "Spell_Fire_Fire"
local ind = CreateFrame("Frame", "BleakholdCampStatus", UIParent)
ind:SetSize(150, 30)
ind:SetFrameStrata("MEDIUM")
UI.Backdrop(ind, C.panel, C.border, nil, "panel")
ind:EnableMouse(true)
ind:Hide()
CP.indicator = ind
local ipos = positioning(ind, "TOP", 0, -200)

ind.flame = UI.Icon(ind, 18, CP.WARMTH_ICON)
ind.flame:SetPoint("LEFT", ind, "LEFT", 7, 0)
ind.text = UI.Text(ind, 12, C.gold)
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
    ind:SetWidth(floor(44 + ind.text:GetStringWidth() + 0.5))
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
-- The Glide button (Walk on Air): shown while the realm has glide on and the player can glide (CAMPST glide
-- not empty), with the cooldown on it and, while a glide runs (CAMPST gliding), a glide bar over it. The key
-- binding (Bindings.xml) does the same as a click, also in mid-air.
------------------------------------------------------------------------------------------------------
-- The spellbook has Walk on Air: its own button (an action bar's) replaces this one.
function CP.GlideSpellKnown()
    return (IsSpellKnown and IsSpellKnown(CP.GLIDE_SPELL)) and true or false
end

-- The ground error, worded for the glide while Walk on Air is known, else the client's own (see NOT_ON_GROUND_TEXT).
function CP.WordGroundError()
    if CP.GlideSpellKnown() then
        SPELL_FAILED_NOT_ON_GROUND = CP.NOT_ON_GROUND_TEXT
    else
        SPELL_FAILED_NOT_ON_GROUND = CP.STOCK_NOT_ON_GROUND
    end
end

-- (ActionButtonTemplate's art: the icon in UI-Quickslot2, ButtonHilight-Square under the cursor, UI-Quickslot-Depress
-- while pressed; grey with the time on it while it cools down)
local gb = CreateFrame("Button", "BleakholdGlideButton", UIParent)
gb:SetSize(36, 36)
gb:SetFrameStrata("MEDIUM")
gb:RegisterForClicks("LeftButtonUp")
gb:Hide()
CP.glideButton = gb
local gpos = positioning(gb, "BOTTOM", 0, 190)

UI.SlotArt(gb, 36)
-- the icon in BACKGROUND (as ActionButtonTemplate's): the pushed overlay is in ARTWORK, and one layer's batch is drawn
-- in texture order, not creation order, so an icon in ARTWORK could cover the Depress overlay
gb.icon:SetDrawLayer("BACKGROUND")
gb.icon:SetPoint("CENTER", gb, "CENTER", 0, 0)
setIcon(gb.icon, CP.GLIDE_ICON)
gb.cd = gb:CreateFontString(nil, "OVERLAY")
gb.cd:SetFont(UI.FONT_BODY, 13, "OUTLINE")
gb.cd:SetTextColor(1, 0.82, 0)
gb.cd:SetPoint("CENTER", gb, "CENTER", 0, 0)
gb.cd:Hide()
gb:SetPushedTexture("Interface\\Buttons\\UI-Quickslot-Depress")
gb:GetPushedTexture():SetAllPoints(gb.icon)

gb:SetScript("OnClick", function()
    CP.Glide()
end)
gb:SetScript("OnEnter", function(self)
    local lines = { CP.GLIDE_NAME, { "High Elf racial", C.dim }, { CP.GLIDE_TEXT, C.mid, true }, { CP.GLIDE_HOW, C.mute, true } }
    local gliding = CP.GlideLeft()
    local left = leftOf("glide")
    if gliding then
        lines[#lines + 1] = { "Gliding: " .. ceil(gliding) .. " sec left", C.teal }
    end
    lines[#lines + 1] = { (left and left >= 1) and ("Ready in " .. U.Clock(ceil(left))) or "Ready", C.goldLight }
    local key = GetBindingKey and GetBindingKey("BLEAKHOLD_GLIDE")
    lines[#lines + 1] = { key and ("Key: " .. key) or "Bind a key: Key Bindings, Bleakhold, Walk on Air", C.mute }
    lines[#lines + 1] = { "Walk on Air is in your spellbook (General) once the realm has taught it.", C.mute, true }
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

-- The glide bar: Walk on Air's time left, over the button, from CAMPST gliding (the server's glide, which also
-- waits there for a ledge). The server says when it ends (a landing) within a second; the bar goes at once when the
-- client sees the landing itself: a second in the air (IsFalling; a hop is shorter and does not use the glide up),
-- then on the ground again. That is a guess (the server starts a glide only 2.5 yd above the ground, and holds one
-- whose last push is still on its way): a new fall while the server still says gliding brings the bar back
-- (CP.GlideBarWatch, below).
CP.GLIDE_BAR_W = 150
CP.GLIDE_AIR_SEC = 1.0
-- (a child of UIParent, placed over the button: it stays when the button makes way for the spellbook's Walk on Air)
-- (the breath bar's look: UI.TimerBar, in the stock green)
local bar = UI.TimerBar(UIParent, CP.GLIDE_BAR_W, C.bar)
bar:SetFrameStrata("MEDIUM")
bar:SetPoint("BOTTOM", gb, "TOP", 0, 14)
bar:Hide()
CP.glideBar = bar
CP.glide = { recvAt = nil, last = 0, total = 0, fallSince = nil, air = false, landed = false }

local function falling()
    return (IsFalling and IsFalling()) and true or false
end

-- Seconds left of the glide that runs now, or nil (none, or it landed).
function CP.GlideLeft()
    local c = S.camp
    if not (featureGlide() and c) or CP.glide.landed then
        return nil
    end
    local left = leftOf("gliding", c)
    if not left or left <= 0 then
        return nil
    end
    return left
end

-- A new CAMPST: a glide that starts (or starts over: more time than the one running has left) resets the bar; one
-- the server ended clears it.
function CP.OnGlideState(c)
    local g = CP.glide
    local gliding = c and c.gliding or 0
    local now = GetTime()
    if gliding <= 0 then
        g.recvAt, g.last, g.total, g.fallSince, g.air, g.landed = nil, 0, 0, nil, false, false
        return
    end
    if not g.recvAt or gliding > g.last - (now - g.recvAt) + 1.5 then
        g.total, g.fallSince, g.air, g.landed = gliding, nil, false, false
    end
    g.recvAt, g.last = now, gliding
end

function CP.UpdateGlideBar()
    local g = CP.glide
    if g.landed and falling() then
        g.landed, g.air, g.fallSince = false, false, nil
    end
    local left = CP.GlideLeft()
    if CP.glidePreview and not left then
        bar:SetProgress(0.6)
        bar.text:SetText(CP.GLIDE_NAME .. "  6.0")
        bar:Show()
        return
    end
    if left then
        local now = GetTime()
        if falling() then
            g.fallSince = g.fallSince or now
            if now - g.fallSince >= CP.GLIDE_AIR_SEC then
                g.air = true
            end
        else
            g.fallSince = nil
            if g.air then
                g.landed = true   -- landed: the server ends the glide too, its CAMPST follows
                left = nil
            end
        end
    end
    if not left then
        bar:Hide()
        return
    end
    bar:SetProgress(left / max(g.total, 1))
    bar.text:SetText(CP.GLIDE_NAME .. "  " .. strformat("%.1f", left))
    bar:Show()
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
        bar:Hide()
        return
    end
    CP.UpdateGlideBar()
    if CP.GlideSpellKnown() and not CP.glidePreview then
        gb:Hide()   -- the spellbook's Walk on Air is on the action bar; the glide bar still shows over this place
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
        if not CP.glidePreview and (not glideLive() or CP.GlideSpellKnown()) then
            gb:Hide()
        else
            CP.UpdateGlide()
        end
    end
end)

local bacc = 0
bar:SetScript("OnUpdate", function(self, elapsed)
    bacc = bacc + (elapsed or 0)
    if bacc >= 0.05 then
        bacc = 0
        CP.UpdateGlideBar()
    end
end)

-- The bar's own OnUpdate stops while it is hidden, and the Glide button is often hidden too (it makes way for the
-- spellbook's Walk on Air), so neither can bring the bar back. While the server still says a glide runs and the bar
-- is down (the client guessed a landing: a push still on its way threw the player off again, or a waiting glide
-- found its ledge after a long slide), this looks again four times a second; a new fall shows the bar.
function CP.GlideBarWatch()
    if not bar:IsShown() and glideLive() and (leftOf("gliding") or 0) > 0 then
        CP.UpdateGlideBar()
    end
end
ns.Every(0.25, CP.GlideBarWatch)

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
        CP.OnGlideState(S.camp)
        CP.RefreshAll()
    end
end)

ns.On("HELLO", CP.RefreshAll)

-- The server teaches the spellbook's Walk on Air at login (or takes it): the Glide button makes way, or comes back,
-- and the ground error is worded for the glide, or the client's own again.
local function spellsChanged()
    CP.WordGroundError()
    CP.RefreshGlide()
end
ns.RegisterEvent("LEARNED_SPELL_IN_TAB", spellsChanged)
ns.RegisterEvent("SPELLS_CHANGED", spellsChanged)
ns.RegisterEvent("PLAYER_ENTERING_WORLD", CP.WordGroundError)

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

ns.AddCommand("glide", "Walk on Air: turn a fall into a glide you steer (High Elves)", function()
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
