-- Bleakhold: toast (task done, queue started, records...) in the achievement alert's look: the alert's background,
-- the icon in the achievement icon frame on its left, a gold kicker and the white name in the dark band; the sub
-- line shows in the tooltip. Up to three wait their turn, five seconds each; clicking one opens the related window.
local ADDON, ns = ...
local U, UI = ns.U, ns.UI

local Toast = {}
ns.Toast = Toast

Toast.SHOW_TIME = 5
Toast.FADE = 0.35
Toast.MAX_QUEUE = 3

local KICKERS = {
    T = "Task Complete", Q = "Queue", K = "Keystone", R = "New Record", S = "Season", I = "Bleakhold",
}

-- The glyph whose icon shows for toasts that open a given window (the check mark's otherwise).
local TARGET_GLYPHS = { arena = "shield" }
Toast.TARGET_GLYPHS = TARGET_GLYPHS

-- The stock frames write headings in Title Case: an all-caps kicker or name from a caller ("WAR FRONT") is shown as
-- "War Front"; mixed case is kept.
function Toast.TitleCase(s)
    s = tostring(s or "")
    if s == "" or s ~= s:upper() or not s:find("%a") then
        return s
    end
    return (s:lower():gsub("(%a)([%w']*)", function(first, rest)
        return first:upper() .. rest
    end))
end

local queue = {}
local current, shownAt

-- AchievementAlertFrame: the art fills 310 x 90 of its 512 x 128 file; its left square holds the icon (centre 38, 44
-- from the top left), the dark band the text (x 75-290, y 27-62).
local f = CreateFrame("Button", "BleakholdToastFrame", UIParent)
f:SetSize(300, 88)
f:SetPoint("TOP", UIParent, "TOP", 0, -110)
f:SetFrameStrata("HIGH")
f:SetFrameLevel(20)
f:Hide()
f:RegisterForClicks("LeftButtonUp")

f.bg = f:CreateTexture(nil, "BACKGROUND")
f.bg:SetTexture(UI.STOCK.alertBg)
f.bg:SetAllPoints(f)
f.bg:SetTexCoord(0, 0.605, 0, 0.703)
f.icon = f:CreateTexture(nil, "ARTWORK")
f.icon:SetSize(50, 50)
f.icon:SetPoint("CENTER", f, "TOPLEFT", 38, -44)
f.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
f.iconFrame = f:CreateTexture(nil, "OVERLAY")
f.iconFrame:SetTexture(UI.STOCK.alertIconFrame)
f.iconFrame:SetSize(72, 72)
f.iconFrame:SetPoint("CENTER", f, "TOPLEFT", 38, -44)
f.iconFrame:SetTexCoord(0, 0.5625, 0, 0.5625)
f.kicker = UI.Text(f, 10, UI.C.gold)
f.kicker:SetPoint("TOPLEFT", f, "TOPLEFT", 82, -30)
UI.OneLine(f.kicker, 200)
f.title = UI.Text(f, 13, UI.C.text)
f.title:SetPoint("TOPLEFT", f, "TOPLEFT", 82, -44)
UI.OneLine(f.title, 200)
-- the sub line is not drawn on the alert: it is the tooltip's second line
f.sub = UI.Text(f, 12, UI.C.dim)
f.sub:Hide()
-- The alert's flash as it comes in (AchievementAlertFrameTemplate's animIn): the glow (UI-Achievement-Alert-Glow, ADD,
-- 400 x 171 on the centre) flares in 0.2 s and fades in 0.5 s; the shine (its 67 x 72 cell) sweeps 240 px to the right
-- in 0.85 s from the icon, fading from 0.55 s on.
Toast.GLOW = "Interface\\AchievementFrame\\UI-Achievement-Alert-Glow"
f.glow = f:CreateTexture(nil, "OVERLAY")
f.glow:SetTexture(Toast.GLOW)
f.glow:SetBlendMode("ADD")
f.glow:SetSize(400, 171)
f.glow:SetPoint("CENTER", f, "CENTER", 0, 0)
f.glow:SetTexCoord(0, 0.78125, 0, 0.66796875)
f.glow:SetAlpha(0)
f.shine = f:CreateTexture(nil, "OVERLAY")
f.shine:SetTexture(Toast.GLOW)
f.shine:SetBlendMode("ADD")
f.shine:SetSize(67, 72)
f.shine:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", 0, 8)
f.shine:SetTexCoord(0.78125, 0.912109375, 0, 0.28125)
f.shine:SetAlpha(0)
Toast.frame = f

-- The flash at t seconds after the toast showed: the glow's alpha, the shine's alpha and its offset to the right.
function Toast.Flash(t)
    local glow = t < 0.2 and t / 0.2 or math.max(0, 1 - (t - 0.2) / 0.5)
    local shine = t < 0.2 and t / 0.2 or (t < 0.55 and 1 or math.max(0, 1 - (t - 0.55) / 0.5))
    local x = 240 * U.Clamp((t - 0.2) / 0.85, 0, 1)
    return glow, shine, x
end

f:SetScript("OnEnter", function(self)
    if current then
        local sub = self.sub:GetText()
        UI.ShowTooltip(self, { self.title:GetText() or "", sub ~= "" and sub or nil })
    end
end)
f:SetScript("OnLeave", function()
    if GameTooltip then
        GameTooltip:Hide()
    end
end)

local function showNext()
    current = table.remove(queue, 1)
    if not current then
        f:Hide()
        return
    end
    f.glyph = current.glyph or TARGET_GLYPHS[current.target or ""] or "check"
    f.icon:SetTexture(UI.IconPath(f.glyph) or UI.IconPath("check"))
    UI.SetText(f.kicker, Toast.TitleCase(current.kicker or KICKERS.I))
    UI.SetText(f.title, Toast.TitleCase(current.title or ""))
    UI.SetText(f.sub, current.sub or "")
    shownAt = GetTime()
    f:SetAlpha(0)
    f:Show()
    if PlaySound then
        PlaySound("igMainMenuOptionCheckBoxOn")
    end
end

f:SetScript("OnUpdate", function(self)
    if not current or not shownAt then
        return
    end
    local t = GetTime() - shownAt
    local glow, shine, x = Toast.Flash(t)
    self.glow:SetAlpha(glow)
    self.shine:SetAlpha(shine)
    if shine > 0 then
        self.shine:SetPoint("BOTTOMLEFT", self, "BOTTOMLEFT", x, 8)
    end
    if t < Toast.FADE then
        self:SetAlpha(t / Toast.FADE)
    elseif t < Toast.SHOW_TIME - Toast.FADE then
        self:SetAlpha(1)
    elseif t < Toast.SHOW_TIME then
        self:SetAlpha(math.max(0, (Toast.SHOW_TIME - t) / Toast.FADE))
    else
        showNext()
    end
end)

f:SetScript("OnClick", function()
    local target = current and current.target
    current = nil
    showNext()
    if target then
        UI.Open(target)
    end
end)

-- d = { kicker, title, sub, target, glyph }
function Toast.Push(d)
    if type(d) ~= "table" or not d.title then
        return
    end
    if #queue >= Toast.MAX_QUEUE then
        table.remove(queue, 1)
    end
    queue[#queue + 1] = d
    if not current then
        showNext()
    end
end

function Toast.Pending()
    return #queue + (current and 1 or 0)
end

ns.On("TASK_DONE", function(t)
    Toast.Push({
        kicker = t.kind == "W" and "Weekly Task Complete" or "Daily Task Complete",
        title = ns.TaskTitle(t),
        sub = "Claim " .. ns.TaskReward(t) .. " in Activities",
        target = "tasks",
    })
end)

-- Server sub lines that still name a window by an old name, by target: the bridge's "Keystone ready" toast
-- (bh_ui_bridge.cpp) says "the Keys window", and the page is Activities > Mythic+ Dungeons now. Drop an entry once
-- the server says it the new way.
Toast.SUB_FIXES = {
    keys = { ["Press Start keystone in the Keys window"] = "Press Start keystone on the Mythic+ Dungeons page" },
}
function Toast.FixSub(sub, target)
    local fixes = Toast.SUB_FIXES[target or ""]
    return fixes and sub and fixes[sub] or sub
end

ns.On("TOAST", function(d)
    Toast.Push({ kicker = KICKERS[d.kind] or KICKERS.I, title = d.title, sub = Toast.FixSub(d.sub, d.target),
        target = d.target })
end)

ns.On("QUEUE_PROPOSAL", function(q)
    if q and q.kind == "B" then
        return    -- Bleakhold Royale's ready check has its own popup (Royale.lua)
    end
    Toast.Push({ kicker = "Group Found", title = "Your group is ready", sub = "Accept in Activities - Dungeons",
        target = "dungeons" })
end)
