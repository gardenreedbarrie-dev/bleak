-- Bleakhold: round buttons around the minimap (Activities, Collections, Season, Leaderboards).
-- They live on BleakholdOrbHolder, a child of UIParent anchored to the Minimap's centre, never on the
-- Minimap itself: AddicatUI (DragonUI) collects every button parented to Minimap/MinimapBackdrop into its drawer,
-- and it moves and rescales the Minimap, which the holder follows. In AddicatUI's editor mode each orb has
-- an outline of its own (the movers at the end); dropping one slides the orb to that angle, saved as before.
local ADDON, ns = ...
local U, UI = ns.U, ns.UI
local C = UI.C

local Orbs = {}
ns.Orbs = Orbs

local rad, cos, sin, atan2, deg = math.rad, math.cos, math.sin, math.atan2, math.deg

Orbs.SIZE = 34
Orbs.GAP = 6
Orbs.list = {
    { key = "activities", glyph = "star", title = "Activities", angle = 205 },
    { key = "collections", glyph = "layers", title = "Collections", angle = 245 },
    { key = "season", glyph = "banner", title = "Season", angle = 295 },
    { key = "leaderboards", glyph = "trophy", title = "Leaderboards", angle = 335 },
}

local holder = CreateFrame("Frame", "BleakholdOrbHolder", UIParent)
holder:SetSize(1, 1)
holder:SetFrameStrata("MEDIUM")
holder:SetFrameLevel(10)
Orbs.holder = holder

local lastW, lastScale, lastShape

local function minimapGeometry()
    if not Minimap then
        return nil
    end
    local w = Minimap:GetWidth() or 0
    local ms = Minimap:GetEffectiveScale() or 1
    local hs = holder:GetEffectiveScale() or 1
    if w <= 0 or hs <= 0 then
        return nil
    end
    local shape = GetMinimapShape and GetMinimapShape() or "ROUND"
    return w / 2 * ms / hs, shape, w, ms
end

local function angleOf(o)
    local saved = ns.cdb.orbs[o.key]
    if type(saved) == "number" and saved == saved then
        return saved
    end
    return o.angle
end

-- Offset of an orb centre from the minimap centre, on the circle or on the square's edge.
function Orbs.Offset(angleDeg, radius, shape)
    local a = rad(angleDeg)
    local x, y = cos(a), sin(a)
    if shape == "SQUARE" then
        local m = math.max(math.abs(x), math.abs(y))
        if m > 0 then
            x, y = x / m, y / m
        end
    end
    return x * radius, y * radius
end

function Orbs.Layout(force)
    local radius, shape, w, ms = minimapGeometry()
    if not radius then
        return
    end
    if not force and w == lastW and ms == lastScale and shape == lastShape then
        return
    end
    lastW, lastScale, lastShape = w, ms, shape
    holder:ClearAllPoints()
    holder:SetPoint("CENTER", Minimap, "CENTER", 0, 0)
    for _, o in ipairs(Orbs.list) do
        if o.button then
            local x, y = Orbs.Offset(angleOf(o), radius + Orbs.SIZE / 2 + Orbs.GAP - 8, shape)
            o.button:ClearAllPoints()
            o.button:SetPoint("CENTER", holder, "CENTER", x, y)
        end
    end
end

-- Turns orb o towards the screen point x, y (unscaled pixels, like GetCursorPosition) and saves the angle.
function Orbs.SetAngleTowards(o, x, y)
    if not (Minimap and x and y) then
        return
    end
    local cx, cy = Minimap:GetCenter()
    if not cx then
        return
    end
    local s = Minimap:GetEffectiveScale() or 1
    local a = deg(atan2(y - cy * s, x - cx * s)) % 360
    ns.cdb.orbs[o.key] = math.floor(a + 0.5)
    Orbs.Layout(true)
end

local function statusLines(key)
    local S = ns.S
    if key == "activities" then
        local lines = { "Activities" }
        local n = ns.ClaimableTasks()
        if n > 0 then
            lines[#lines + 1] = { n .. (n == 1 and " task" or " tasks") .. " ready to claim", C.teal }
        end
        local q = S.queue
        if q and q.state == 1 then
            lines[#lines + 1] = { "In queue", C.goldLight }
        elseif q and q.state == 2 then
            lines[#lines + 1] = { "Group found - accept in Dungeons", C.teal }
        end
        lines[#lines + 1] = { "Click to open", C.mute }
        return lines
    elseif key == "collections" then
        local c = S.coll
        local lines = { "Collections" }
        if c and c.setsOwned then
            lines[#lines + 1] = { "Legacy sets: " .. c.setsOwned .. (c.setsTotal and (" / " .. c.setsTotal) or ""), C.mid }
        end
        lines[#lines + 1] = { "Click to open", C.mute }
        return lines
    elseif key == "season" then
        local s = S.season
        local lines = { U.Safe(ns.DefName("S", s and s.seasonId or (ns.Comm.server.seasonId), "Season")) }
        if s then
            lines[#lines + 1] = { "War Effort: " .. math.floor((s.wePermille or 0) / 10) .. "%", C.goldLight }
        end
        lines[#lines + 1] = { "Click to open", C.mute }
        return lines
    end
    local me = S.lbme and S.lbme.K
    local lines = { "Leaderboards" }
    if me and me.value then
        lines[#lines + 1] = { "Your best key: +" .. me.value .. (me.rank and (" - rank " .. me.rank) or ""), C.goldLight }
    end
    lines[#lines + 1] = { "Click to open", C.mute }
    return lines
end

local function makeOrb(o)
    local b = CreateFrame("Button", "BleakholdOrb_" .. o.key, holder)
    b:SetSize(Orbs.SIZE, Orbs.SIZE)
    b:SetFrameLevel(holder:GetFrameLevel() + 2)
    b.fill = UI.Disc(b, Orbs.SIZE, C.panel, "BACKGROUND")
    b.fill:SetPoint("CENTER")
    b.ring = b:CreateTexture(nil, "BORDER")
    b.ring:SetTexture(UI.ART .. "Ring")
    b.ring:SetAllPoints(b)
    b.ring:SetVertexColor(UI.Rgb(C.gold))
    b.glyph = UI.Glyph(b, o.glyph, 18, C.goldLight, "ARTWORK")
    b.glyph:SetPoint("CENTER")
    b.dot = UI.Disc(b, 10, C.teal, "OVERLAY")
    b.dot:SetPoint("TOPRIGHT", b, "TOPRIGHT", 1, 1)
    b.dot:Hide()
    b:RegisterForClicks("LeftButtonUp")
    b:RegisterForDrag("RightButton")
    b:SetScript("OnClick", function()
        UI.Open(o.key, true)
    end)
    b:SetScript("OnEnter", function(self)
        self.ring:SetVertexColor(UI.Rgb(C.goldPale))
        UI.ShowTooltip(self, statusLines(o.key))
    end)
    b:SetScript("OnLeave", function(self)
        self.ring:SetVertexColor(UI.Rgb(C.gold))
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    -- Right-drag slides the orb along the ring (angle saved per character).
    b:SetScript("OnDragStart", function(self)
        self.dragging = true
    end)
    b:SetScript("OnDragStop", function(self)
        self.dragging = false
    end)
    b:SetScript("OnUpdate", function(self)
        if not self.dragging then
            return
        end
        local mx, my = GetCursorPosition()
        Orbs.SetAngleTowards(o, mx, my)
    end)
    o.button = b
    return b
end

for _, o in ipairs(Orbs.list) do
    makeOrb(o)
end

function Orbs.UpdateBadges()
    local act = Orbs.list[1].button
    if act then
        if ns.ClaimableTasks() > 0 then
            act.dot:Show()
        else
            act.dot:Hide()
        end
    end
end

local pulse = 0
ns.Every(0.1, function()
    local q = ns.S.queue
    local act = Orbs.list[1].button
    if act then
        if q and (q.state == 1 or q.state == 2) then
            pulse = pulse + 0.1
            act.ring:SetAlpha(0.55 + 0.45 * math.abs(sin(pulse * 2)))
        else
            act.ring:SetAlpha(1)
        end
    end
end)

ns.Every(1, function()
    Orbs.Layout(false)
end)

ns.On("STATE", function(topic)
    if topic == "TASKS" or topic == "QUEUE" then
        Orbs.UpdateBadges()
    end
end)

function Orbs.SetShown(show)
    ns.cdb.orbsHidden = not show
    if show then
        holder:Show()
    else
        holder:Hide()
    end
end

ns.On("DB_READY", function()
    if ns.cdb.orbsHidden then
        holder:Hide()
    end
    Orbs.Layout(true)
end)

if Minimap and Minimap.HookScript then
    Minimap:HookScript("OnSizeChanged", function()
        Orbs.Layout(true)
    end)
end

ns.AddCommand("orbs", "minimap buttons: /bh orbs on|off|reset", function(args)
    args = (args or ""):lower()
    if args == "off" then
        Orbs.SetShown(false)
    elseif args == "reset" then
        wipe(ns.cdb.orbs)
        Orbs.SetShown(true)
        Orbs.Layout(true)
    else
        Orbs.SetShown(true)
    end
end)

-- Editor mode (ns.Movers): an orb follows the outline's centre around the ring.
for _, o in ipairs(Orbs.list) do
    UI.AddMover({
        name = "bleakhold_orb_" .. o.key,
        title = o.title .. " orb",
        frame = o.button,
        begin = function()
            Orbs.Layout(true)
        end,
        finish = function()
            Orbs.Layout(true)
        end,
        move = function(region)
            local x, y = region:GetCenter()
            local s = region:GetEffectiveScale() or 1
            if x then
                Orbs.SetAngleTowards(o, x * s, y * s)
            end
        end,
        reset = function()
            ns.cdb.orbs[o.key] = nil
            Orbs.Layout(true)
        end,
        isDefault = function()
            return type(ns.cdb.orbs[o.key]) ~= "number"
        end,
        visible = function()
            return holder:IsShown() and true or false
        end,
    })
end
