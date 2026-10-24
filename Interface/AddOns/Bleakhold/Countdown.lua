-- Bleakhold: keystone start countdown. The server starts it (MPS countdownMs) and roots the group;
-- this draws the centre countdown (dungeon, level, affixes, era, a draining ring and big numerals from
-- the Digits atlas, since fonts stop at 32 px), and makes DBM show its own "Pull in" bar: the group
-- leader's client sends DBM's pull-timer message (prefix "DBMv4-PT", body = seconds) to the group, or
-- to itself when solo and DBM is loaded. That message is for DBM only; it is never a Bleakhold intent.
-- When the server already sends the DBM message itself (HELLO feature bit DBM_BY_SERVER), the client
-- does not.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S

local floor, ceil, max, min = math.floor, math.ceil, math.max, math.min

local CD = {}
ns.Countdown = CD

CD.DBM_PREFIX = "DBMv4-PT"
-- Digits.tga is 1024x256: digit d fills x = d*96 .. d*96+96; the strokes stay within y = 40 .. 216.
CD.DIGIT_W, CD.DIGIT_CELL, CD.DIGIT_V0, CD.DIGIT_V1 = 96, 96, 40 / 256, 216 / 256
CD.SHOW_DIGITS = 150

local f = CreateFrame("Frame", "BleakholdCountdown", UIParent)
f:SetSize(420, 470)
f:SetPoint("TOP", UIParent, "TOP", 0, -80)
f:SetFrameStrata("DIALOG")
f:Hide()
CD.frame = f

f.kicker = UI.Text(f, 13, C.mid, "body", "CENTER")
f.kicker:SetPoint("TOP", f, "TOP", 0, 0)
f.kicker:SetText("K E Y S T O N E   S T A R T S   I N")
f.title = UI.Text(f, 26, C.goldPale, "title", "CENTER")
f.title:SetPoint("TOP", f.kicker, "BOTTOM", 0, -8)
f.pills = {}
for i = 1, 6 do
    local p = UI.Pill(f, "", C.panel, C.eraBorder, C.text, 12)
    p:Hide()
    f.pills[i] = p
end
f.pillRow = CreateFrame("Frame", nil, f)
f.pillRow:SetSize(10, 22)
f.pillRow:SetPoint("TOP", f.title, "BOTTOM", 0, -10)

f.ringBg = UI.Disc(f, 240, C.bg, "BACKGROUND", 0.55)
f.ringBg:SetPoint("TOP", f, "TOP", 0, -120)
f.ring = UI.Ring(f, 240, 10)
f.ring:SetPoint("CENTER", f.ringBg, "CENTER")
f.ring.label:Hide()

f.digits = {}
for i = 1, 2 do
    local t = f:CreateTexture(nil, "OVERLAY")
    t:SetTexture(UI.ART .. "Digits")
    t:SetVertexColor(UI.Rgb(C.goldPale))
    t:Hide()
    f.digits[i] = t
end

local function setNumber(n)
    local s = tostring(n)
    local h = CD.SHOW_DIGITS
    local w = h * CD.DIGIT_W / ((CD.DIGIT_V1 - CD.DIGIT_V0) * 256)
    local total = w * #s
    for i, t in ipairs(f.digits) do
        local ch = s:sub(i, i)
        local d = tonumber(ch)
        if d then
            local u0 = d * CD.DIGIT_CELL / 1024
            local u1 = (d * CD.DIGIT_CELL + CD.DIGIT_W) / 1024
            t:SetTexCoord(u0, u1, CD.DIGIT_V0, CD.DIGIT_V1)
            t:SetSize(w, h)
            t:ClearAllPoints()
            t:SetPoint("CENTER", f.ring, "CENTER", -total / 2 + w * (i - 0.5), 0)
            if CD.HideNumerals() then
                t:Hide()
            else
                t:Show()
            end
        else
            t:Hide()
        end
    end
end
CD.SetNumber = setNumber

-- Hide our numerals when DBM already draws its centre countdown and the player asked for that.
function CD.HideNumerals()
    if not ns.Option("hideNumeralsWithDBM", false) then
        return false
    end
    return DBM ~= nil and type(DBM.Options) == "table" and DBM.Options.DontShowPTCountdownText == false
end

------------------------------------------------------------------------------------------------------
-- DBM pull timer
------------------------------------------------------------------------------------------------------
CD.sentPull = false

local function dbmLoaded()
    return DBM ~= nil or (IsAddOnLoaded and IsAddOnLoaded("DBM-Core")) and true or false
end

-- Returns the channel the DBM message goes to, or nil when this client should not send it.
function CD.PullChannel()
    if Comm.HasFeature(Comm.FEATURE.DBM_BY_SERVER) or not ns.Option("dbmPull", true) then
        return nil
    end
    local kind, _, leader, officer = ns.GroupInfo()
    if kind == "RAID" then
        return (leader or officer) and "RAID" or nil
    elseif kind == "PARTY" then
        return leader and "PARTY" or nil
    end
    return dbmLoaded() and "WHISPER" or nil
end

function CD.SendPull(seconds)
    local channel = CD.PullChannel()
    if not channel then
        return false
    end
    if Comm.demo then
        ns.Print("demo: DBM pull timer of " .. seconds .. " s would go to " .. channel:lower())
        return false
    end
    local body = tostring(seconds)
    if channel == "WHISPER" then
        SendAddonMessage(CD.DBM_PREFIX, body, "WHISPER", ns.PlayerName())
    else
        SendAddonMessage(CD.DBM_PREFIX, body, channel)
    end
    CD.sentPull = seconds > 0
    return true
end

------------------------------------------------------------------------------------------------------
-- Countdown
------------------------------------------------------------------------------------------------------
function CD.Remaining()
    local m = S.mplus
    if not m or m.state ~= 0 or m.result then
        return 0
    end
    return (m.countdownMs or 0) / 1000 - (GetTime() - (m.startedAt or GetTime()))
end

function CD.Start(m)
    local secs = floor((m.countdownMs or 0) / 1000 + 0.5)
    if secs <= 0 then
        return
    end
    UI.SetText(f.title, ns.DungeonName(m.dungeonId) .. ((m.level or 0) > 0 and (" +" .. m.level) or ""))
    local shown = {}
    local names = ns.AffixNames(m.affixes)
    for i, p in ipairs(f.pills) do
        local text, gold
        if names[i] then
            text = names[i]
        elseif i == #names + 1 and m.eraId then
            text, gold = ns.DefName("E", m.eraId, "Era") .. " era", true
        end
        if text then
            p:SetValue(text)
            UI.Colors(p, C.panel, gold and C.gold or C.eraBorder)
            UI.SetColor(p.text, gold and C.goldPale or C.text)
            p:Show()
            shown[#shown + 1] = p
        else
            p:Hide()
        end
    end
    local width = 0
    for _, p in ipairs(shown) do width = width + p:GetWidth() + 6 end
    UI.Row(shown, f.pillRow, "LEFT", "CENTER", -width / 2, 0, 6)
    CD.total = secs
    f:Show()
    CD.Update()
    if secs >= 3 then
        CD.SendPull(secs)
    end
end

function CD.Stop(cancelled)
    f:Hide()
    if cancelled and CD.sentPull then
        CD.SendPull(0)
    end
    CD.sentPull = false
end

function CD.Update()
    local left = CD.Remaining()
    if left <= 0 then
        CD.Stop(false)
        return
    end
    f.ring:SetProgress(left / max(1, CD.total or 1), C.gold, C.border)
    setNumber(min(99, ceil(left)))
end

f:SetScript("OnUpdate", function(self, elapsed)
    self.acc = (self.acc or 0) + (elapsed or 0)
    if self.acc >= 0.05 then
        self.acc = 0
        CD.Update()
    end
end)

ns.On("MPLUS_START", function(m)
    CD.Start(m)
end)
ns.On("MPLUS_GO", function()
    CD.Stop(false)
end)
ns.On("MPLUS_ABANDONED", function()
    if f:IsShown() then
        CD.Stop(true)
    end
end)
ns.On("MPLUS_END", function()
    if f:IsShown() then
        CD.Stop(true)
    end
end)

ns.AddCommand("dbm", "DBM pull bar for keystone starts: /bh dbm on|off", function(args)
    args = (args or ""):lower()
    if args == "on" or args == "off" then
        ns.db.options.dbmPull = args == "on"
    end
    ns.Print("DBM pull timer for keystone starts: " .. (ns.Option("dbmPull", true) and "on" or "off"))
end)
