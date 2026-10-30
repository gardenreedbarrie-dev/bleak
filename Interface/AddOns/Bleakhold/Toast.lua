-- Bleakhold: toast (task done, queue started, records...) in the achievement alert's look: the alert's background,
-- the icon in the achievement icon frame on its left, and in the dark band a gold kicker, the white name and the sub
-- line dim under it (the server's say what was won or what to do next: "+72 Mythic Coins, a Rift Cache", "Find and
-- defeat <boss>"). A name or sub line too long for the band steps its font down; a sub still too long takes a shorter
-- wording (Toast.FitSub: the caller's alts, else a server line's last whole clause that fits, marked ", ..." so the
-- line never looks whole) before the client cuts anything with "..."; the tooltip has both whole. Up to three wait their turn, five seconds each; clicking one opens
-- the related window.
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
-- from the top left), the dark band the text (x 75-290, y 27-62): the kicker at 26, the name at 38, the sub at 52.
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
Toast.TEXT_W = 200
Toast.TITLE_SIZES = { 13, 12, 11 }        -- the name's font, stepped down until it fits (then cut)
Toast.SUB_SIZES = { 11, 10 }              -- the sub line's
f.kicker = UI.Text(f, 10, UI.C.gold)
f.kicker:SetPoint("TOPLEFT", f, "TOPLEFT", 82, -26)
UI.OneLine(f.kicker, Toast.TEXT_W)
f.title = UI.Text(f, 13, UI.C.text)
f.title:SetPoint("TOPLEFT", f, "TOPLEFT", 82, -38)
UI.OneLine(f.title, Toast.TEXT_W)
f.sub = UI.Text(f, 11, UI.C.dim)
f.sub:SetPoint("TOPLEFT", f, "TOPLEFT", 82, -52)
UI.OneLine(f.sub, Toast.TEXT_W)
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

-- Sets fs to s (escaped) in the largest of sizes whose line fits w; past the smallest the client cuts it with "...".
-- Returns the size used.
function Toast.Fit(fs, s, sizes, w)
    local path = fs:GetFont()
    local size
    for _, px in ipairs(sizes) do
        size = px
        fs:SetFont(path or UI.FONT_BODY, px, "")
        UI.OneLine(fs, w)
        UI.SetText(fs, s)
        if (fs:GetStringWidth() or 0) <= w then
            break
        end
    end
    return size
end

-- Whether s fits the band in the sub line's smallest size (measured on a hidden line, so the toast showing keeps its
-- text).
f.measure = UI.Text(f, Toast.SUB_SIZES[#Toast.SUB_SIZES], UI.C.dim)
f.measure:Hide()
function Toast.SubFits(s)
    local fs = Toast.frame.measure
    fs:SetFont(Toast.frame.sub:GetFont() or UI.FONT_BODY, Toast.SUB_SIZES[#Toast.SUB_SIZES], "")
    UI.SetText(fs, s or "")
    return (fs:GetStringWidth() or 0) <= Toast.TEXT_W
end

-- s up to the end of its last whole clause (before a ", " or " - ") followed by the cut's mark (that separator and
-- "...", so the line shows it goes on) that fits the band at the smallest size, the clause keeping at least
-- Toast.MIN_CLAUSE bytes, or nil: "Find Loken, then the Bridge, then the Vault" -> "Find Loken, then the Bridge, ..."
-- rather than the client's "..., then the Va..." or a head that reads as the whole line.
Toast.MIN_CLAUSE = 10
Toast.CLAUSE_MARK = "..."
function Toast.Clause(s)
    if type(s) ~= "string" then
        return nil
    end
    local ends, i = {}, 1
    while #ends < 32 do
        local a = s:find(", ", i, true)
        local b = s:find(" - ", i, true)
        local at = (a and b) and math.min(a, b) or a or b
        if not at then
            break
        end
        ends[#ends + 1] = { at - 1, at == a and ", " or " - " }
        i = at + 1
    end
    for k = #ends, 1, -1 do
        local head = s:sub(1, ends[k][1])
        local cut = head .. ends[k][2] .. Toast.CLAUSE_MARK
        if #head >= Toast.MIN_CLAUSE and Toast.SubFits(cut) then
            return cut
        end
    end
    return nil
end

-- Sets the sub line: sub when it fits the band at some size, else the first of alts (shorter wordings, best first)
-- that does, else (clause set: the server's lines) sub's last whole clause that does, marked as cut (Toast.Clause),
-- else sub whole for the client to cut with "...". Returns the text drawn.
function Toast.FitSub(fs, sub, alts, clause)
    sub = sub or ""
    local pick
    if Toast.SubFits(sub) then
        pick = sub
    else
        for _, alt in ipairs(type(alts) == "table" and alts or {}) do
            if type(alt) == "string" and Toast.SubFits(alt) then
                pick = alt
                break
            end
        end
        pick = pick or (clause and Toast.Clause(sub)) or sub
    end
    Toast.Fit(fs, pick, Toast.SUB_SIZES, Toast.TEXT_W)
    return pick
end

-- The flash at t seconds after the toast showed: the glow's alpha, the shine's alpha and its offset to the right.
function Toast.Flash(t)
    local glow = t < 0.2 and t / 0.2 or math.max(0, 1 - (t - 0.2) / 0.5)
    local shine = t < 0.2 and t / 0.2 or (t < 0.55 and 1 or math.max(0, 1 - (t - 0.55) / 0.5))
    local x = 240 * U.Clamp((t - 0.2) / 0.85, 0, 1)
    return glow, shine, x
end

-- The tooltip: the name and the sub line whole, as the caller sent them (the band may show a shorter wording; tip:
-- the caller's own whole line, when its sub is already a part of it).
f:SetScript("OnEnter", function(self)
    if current then
        local sub = U.Safe(current.tip or current.sub or "")
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
    Toast.Fit(f.title, Toast.TitleCase(current.title or ""), Toast.TITLE_SIZES, Toast.TEXT_W)
    Toast.FitSub(f.sub, current.sub, current.alts, current.clause)
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

-- d = { kicker, title, sub, alts (shorter subs, best first: Toast.FitSub), clause (a sub too long may end at its last
-- whole clause, marked as cut: Toast.Clause), tip (the tooltip's sub, default sub), target, glyph }
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

-- A long reward name ("Claim 2x Mythical Cache of the Eclipse in Activities") drops "in Activities" first, then the
-- name (the tooltip keeps the whole line).
Toast.TASK_SUB_SHORT = "Claim your reward in Activities"
ns.On("TASK_DONE", function(t)
    local reward = ns.TaskReward(t)
    Toast.Push({
        kicker = t.kind == "W" and "Weekly Task Complete" or "Daily Task Complete",
        title = ns.TaskTitle(t),
        sub = "Claim " .. reward .. " in Activities",
        alts = { "Claim " .. reward, Toast.TASK_SUB_SHORT },
        target = "tasks",
    })
end)

-- Server sub lines said another way, by target: those that still name a window by an old name (the bridge's
-- "Keystone ready" toast, bh_ui_bridge.cpp, says "the Keys window": the page is Activities > Mythic+ Dungeons now;
-- the Rift's run-over one, bh_ui_bridge_map.cpp RiftEndToast, "the Eclipse Rift window") and those too long for the
-- band (RiftClearedToast's checkpoint line). Each fits the band at the sub's smallest size. Drop an entry once the
-- server says it the new way.
Toast.SUB_FIXES = {
    keys = { ["Press Start keystone in the Keys window"] = "Start keystone on Mythic+ Dungeons" },
    rift = {
        ["Checkpoint reached - step into the rift portal"] = "Checkpoint reached - take the portal",
        ["The run summary is in the Eclipse Rift window"] = "The run summary is on the Rift page",
    },
}
function Toast.FixSub(sub, target)
    local fixes = Toast.SUB_FIXES[target or ""]
    return fixes and sub and fixes[sub] or sub
end

-- The Rift's run-over toast (RiftEndToast) ends its sub with the record it set ("+72 Mythic Coins, a Rift Cache - new
-- duo best", or "New duo best" alone): with the rewards before it, too long for the band. The record goes up into the
-- kicker ("New Duo Best" instead of "New Record") and the rewards stay in the sub. Answers the kicker (nil: none) and
-- the sub.
function Toast.RecordKicker(sub)
    if type(sub) ~= "string" then
        return nil, sub
    end
    local rest, size = sub:match("^(.-) %- new (%a+) best$")
    if not rest then
        size = sub:match("^New (%a+) best$")
        rest = size and ""
    end
    if not size then
        return nil, sub
    end
    return "New " .. size:sub(1, 1):upper() .. size:sub(2):lower() .. " Best", rest
end

-- The Rift's run-over rewards (RiftEndToast: "+150 Mythic Coins, 2 Rift Caches, 3 Mythic-only looks") said shorter,
-- step by step, every reward kept (the rarest, the looks, comes last: the first a clause cut would drop): "Mythic
-- Coins" -> "Coins", then "Rift Caches" -> "Caches", "Mythic-only looks" -> "Mythic looks", -> "looks". Answers the
-- alts for Toast.FitSub, best first (none when sub names no reward).
Toast.RIFT_REWARD_SHORT = {
    { "Mythic Coins", "Coins" },
    { "Rift Cache", "Cache" },
    { "Mythic%-only look", "Mythic look" },
    { "Mythic look", "look" },
}
function Toast.RiftRewardAlts(sub)
    local alts = {}
    if type(sub) ~= "string" then
        return alts
    end
    local s = sub
    for _, step in ipairs(Toast.RIFT_REWARD_SHORT) do
        local n
        s, n = s:gsub(step[1], step[2])
        if n > 0 then
            alts[#alts + 1] = s
        end
    end
    return alts
end

ns.On("TOAST", function(d)
    local kicker, sub = KICKERS[d.kind] or KICKERS.I, Toast.FixSub(d.sub, d.target)
    local tip, alts
    if d.target == "rift" then
        if d.kind == "R" then
            local record, rest = Toast.RecordKicker(sub)
            if record then
                kicker, sub, tip = record, rest, sub
            end
        end
        alts = Toast.RiftRewardAlts(sub)
    end
    Toast.Push({ kicker = kicker, title = d.title, sub = sub, alts = alts, clause = true, tip = tip,
        target = d.target })
end)

ns.On("QUEUE_PROPOSAL", function(q)
    if q and q.kind == "B" then
        return    -- Bleakhold Royale's ready check has its own popup (Royale.lua)
    end
    Toast.Push({ kicker = "Group Found", title = "Your group is ready", sub = "Accept in Activities - Dungeons",
        target = "dungeons" })
end)
