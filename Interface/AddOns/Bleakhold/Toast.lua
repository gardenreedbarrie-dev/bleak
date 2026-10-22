-- Bleakhold: toast (task done, queue started, records...). Up to three wait their turn, five seconds
-- each; clicking one opens the related window.
local ADDON, ns = ...
local U, UI = ns.U, ns.UI
local C = UI.C

local Toast = {}
ns.Toast = Toast

Toast.SHOW_TIME = 5
Toast.FADE = 0.35
Toast.MAX_QUEUE = 3

local KICKERS = {
    T = "TASK DONE", Q = "QUEUE", K = "KEYSTONE", R = "NEW RECORD", S = "SEASON", I = "BLEAKHOLD",
}

local queue = {}
local current, shownAt

local f = CreateFrame("Button", "BleakholdToastFrame", UIParent)
f:SetSize(420, 74)
f:SetPoint("TOP", UIParent, "TOP", 0, -110)
f:SetFrameStrata("HIGH")
f:SetFrameLevel(20)
UI.Backdrop(f, C.panel, C.teal, 0.97)
f:Hide()
f:RegisterForClicks("LeftButtonUp")

f.disc = UI.Disc(f, 40, C.teal)
f.disc:SetPoint("LEFT", f, "LEFT", 14, 0)
f.check = UI.Glyph(f, "check", 22, C.bg)
f.check:SetPoint("CENTER", f.disc, "CENTER")
f.kicker = UI.Text(f, 11, C.teal)
f.kicker:SetPoint("TOPLEFT", f, "TOPLEFT", 66, -12)
f.title = UI.Text(f, 15, C.text)
f.title:SetPoint("TOPLEFT", f.kicker, "BOTTOMLEFT", 0, -3)
UI.OneLine(f.title, 342)
f.sub = UI.Text(f, 12, C.dim)
f.sub:SetPoint("TOPLEFT", f.title, "BOTTOMLEFT", 0, -3)
UI.OneLine(f.sub, 342)
Toast.frame = f

local function showNext()
    current = table.remove(queue, 1)
    if not current then
        f:Hide()
        return
    end
    UI.SetText(f.kicker, current.kicker or "BLEAKHOLD")
    UI.SetText(f.title, current.title or "")
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

-- d = { kicker, title, sub, target }
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
        kicker = t.kind == "W" and "WEEKLY TASK DONE" or "DAILY TASK DONE",
        title = ns.TaskTitle(t),
        sub = "Claim " .. ns.TaskReward(t) .. " in Activities",
        target = "tasks",
    })
end)

ns.On("TOAST", function(d)
    Toast.Push({ kicker = KICKERS[d.kind] or KICKERS.I, title = d.title, sub = d.sub, target = d.target })
end)

ns.On("QUEUE_PROPOSAL", function()
    Toast.Push({ kicker = "GROUP FOUND", title = "Your group is ready", sub = "Accept in Activities - Dungeons", target = "dungeons" })
end)
