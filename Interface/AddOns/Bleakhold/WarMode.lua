-- Bleakhold: War Mode (docs/BleakholdProtocol.md section 19), the player's side. Everything shown is server state
-- (WMST, WPMAP and WPZ, parsed in State.lua); the client counts the timers down and sends one intent, WARMODE 1 or 0,
-- once the player confirmed it. The pieces:
--   the War Mode page of Activities   the toggle and why it cannot be used now, the bonuses (War Mode, the underdog
--                                     bonus and its faction, Dominion where the player is), today's caps, the streak,
--                                     the hunt while Wanted, and the Fronts of WPMAP with their countdowns
--   the minimap orb                   red while War Mode is on, pulsing while the player is Wanted
--   /bh warmode [on|off]              opens the page, or asks the server straight away (it checks everything again)
-- The button greys itself with what the client can see: the server's `block`, the level, dead, combat, an instance
-- or a taxi, not resting (IsResting: an inn or a city), Wanted (turning off) and the cooldown. The server checks it
-- all again and answers WMST or ERR (the sentences of Data.errorTexts).
-- Features: HELLO bit 16384 War Mode, 32768 World PvP objectives (counted only with 16384). Without 16384 nothing of
-- this shows and nothing is asked for; without 32768 the page has no Fronts and WarFront.lua draws nothing but the
-- Wanted players.
local ADDON, ns = ...
local U, UI, Comm, Data = ns.U, ns.UI, ns.Comm, ns.Data
local C = UI.C
local S = ns.S
local A = ns.Activities

local floor, ceil, max, min, abs, sin = math.floor, math.ceil, math.max, math.min, math.abs, math.sin

local WM = {}
ns.WarMode = WM

WM.GAP = 2.1                      -- s between two WARMODE (the server allows one per WarModeIntervalMs, 2 s)
WM.PENDING = 6                    -- s the button waits for the server's answer
WM.COLOR = "E0604A"               -- the [War] tag's colour
WM.KICKER = "WAR MODE"
WM.ICONS = "Interface\\Icons\\"
WM.UNKNOWN_ICON = "INV_Misc_QuestionMark"
WM.TEAM = {
    A = { name = "Alliance", color = "5E9BE8", icon = "INV_BannerPVP_02" },
    H = { name = "Horde", color = "E5604F", icon = "INV_BannerPVP_01" },
    N = { name = "Neutral", color = "8C877D" },
}
WM.KIND = { F = "Bleak Front", L = "Levelling Front", S = "Stock objectives", W = "Wintergrasp" }
WM.ZONE_STATE = { [0] = "Dormant", [1] = "Active", [2] = "Ceasefire" }
WM.WANTED = { [1] = "Wanted for a kill streak", [2] = "Wanted as a bully" }
WM.CONFIRM_ON = "Turn War Mode on? You will be flagged for PvP everywhere except sanctuaries, and you cannot "
    .. "change it again right away."
WM.CONFIRM_OFF = "Turn War Mode off? Its bonuses end now; your PvP flag fades after 5 minutes."
WM.TEXT = "Fight the other faction in the open world for more experience and honor, capture outposts and hunt "
    .. "Wanted players. While it is on you are flagged for PvP everywhere except sanctuaries."

------------------------------------------------------------------------------------------------------
-- Gates and helpers
------------------------------------------------------------------------------------------------------
function WM.Live()
    return Comm.HasFeature(Comm.FEATURE.WAR_MODE)
end

-- The objectives count only with War Mode (bit 32768 is only ever on together with 16384).
function WM.ObjectivesLive()
    return WM.Live() and Comm.HasFeature(Comm.FEATURE.WORLD_PVP)
end

-- The player's War Mode (WMST) while the realm runs it, else nil.
function WM.State()
    if not WM.Live() then
        return nil
    end
    return S.warMode
end

function WM.IsOn()
    local wm = WM.State()
    return wm ~= nil and wm.on
end

function WM.Wanted()
    local wm = WM.State()
    return wm ~= nil and wm.wantedState > 0
end

-- "A" or "H" for the player's faction, nil when the client does not say.
function WM.MyTeam()
    local f = UnitFactionGroup and UnitFactionGroup("player")
    if f == "Alliance" then
        return "A"
    elseif f == "Horde" then
        return "H"
    end
    return nil
end

function WM.TeamName(t)
    local d = WM.TEAM[t or ""]
    return d and d.name or "Nobody"
end

function WM.TeamColor(t)
    local d = WM.TEAM[t or ""]
    return d and d.color or C.mute
end

-- A stock icon; a file the client cannot load leaves the old texture (Script_SetTexture), so fall back.
function WM.SetIcon(tex, name)
    if not name or not tex:SetTexture(WM.ICONS .. name) then
        tex:SetTexture(WM.ICONS .. WM.UNKNOWN_ICON)
    end
end

function WM.CooldownLeft(wm)
    wm = wm or S.warMode
    return wm and ns.WarLeft(wm.cooldownSec, wm.recvAt) or 0
end

function WM.WantedLeft(wm)
    wm = wm or S.warMode
    return wm and wm.wantedState > 0 and ns.WarLeft(wm.wantedSec, wm.recvAt) or 0
end

-- "1:12:00" or "4:05" (no leading zero minutes).
function WM.Clock(sec)
    return (U.Clock(ceil(sec or 0)):gsub("^0(%d:)", "%1"))
end

-- "+10% XP, +10% honor" from the base bonuses (empty when there are none).
function WM.BonusText(wm)
    local parts = {}
    if (wm.xpPct or 0) > 0 then
        parts[#parts + 1] = "+" .. wm.xpPct .. "% XP"
    end
    if (wm.honorPct or 0) > 0 then
        parts[#parts + 1] = "+" .. wm.honorPct .. "% honor"
    end
    if (wm.shardPct or 0) > 0 then
        parts[#parts + 1] = "+" .. wm.shardPct .. "% Shards"
    end
    return table.concat(parts, ", ")
end

WM.WHY = { K = "a kill", C = "a capture", H = "holding outposts", B = "a bounty", S = "surviving the hunt",
    V = "the War Chest" }

-- "+186 Honor, +2 Shards - a capture (75%)": a WPEV R reward line (the server's amounts, after its caps).
function WM.RewardText(e)
    local parts = {}
    if (e.honor or 0) > 0 then
        parts[#parts + 1] = "+" .. U.Commas(e.honor) .. " Honor"
    end
    if (e.xp or 0) > 0 then
        parts[#parts + 1] = "+" .. U.Commas(e.xp) .. " XP"
    end
    if (e.shards or 0) > 0 then
        parts[#parts + 1] = "+" .. U.Commas(e.shards) .. ((e.shards == 1) and " Shard" or " Shards")
    end
    local txt = #parts > 0 and table.concat(parts, ", ") or "Nothing more today"
    txt = txt .. " - " .. (WM.WHY[e.why or ""] or "War Mode")
    if e.drPermille and e.drPermille < 1000 then
        txt = txt .. " (" .. floor(e.drPermille / 10 + 0.5) .. "%)"
    end
    return txt
end

-- A refusal the client tells by itself: in the error frame, like the server's ERR sentences.
local function notice(code, text)
    text = text or ns.ErrorText({ code = code })
    if text and UIErrorsFrame then
        UIErrorsFrame:AddMessage(text, 1, 0.45, 0.4)
    elseif text then
        ns.Print(text)
    end
end
WM.Notice = notice

local function connected()
    if Comm.outdated then
        return false, "Your Bleakhold addon is out of date."
    end
    if not Comm.ready and not Comm.demo then
        return false, "Not connected to the realm."
    end
    return true
end

-- Why the toggle cannot be used now, from what the client can see, in the server's order (section 19): an ERR code
-- (or nil) and the sentence; nothing when the button may be pressed. In /bh demo only the server's own fields count.
function WM.Block()
    local ok, why = connected()
    if not ok then
        return nil, why
    end
    if not WM.Live() then
        return "wm_off", ns.ErrorText({ code = "wm_off" })
    end
    local wm = S.warMode
    if not wm then
        return nil, "Waiting for the realm..."
    end
    local function refusal(code)
        return code, ns.ErrorText({ code = code }) or "You cannot change War Mode now."
    end
    if wm.block then
        return refusal(wm.block)
    end
    if not Comm.demo then
        local level = UnitLevel and UnitLevel("player")
        if wm.minLevel and type(level) == "number" and level > 0 and level < wm.minLevel then
            return refusal("wm_level")
        end
        if UnitIsDeadOrGhost and UnitIsDeadOrGhost("player") then
            return refusal("dead")
        end
        if (UnitAffectingCombat and UnitAffectingCombat("player")) or (InCombatLockdown and InCombatLockdown()) then
            return refusal("in_combat")
        end
        if (IsInInstance and IsInInstance()) or (UnitOnTaxi and UnitOnTaxi("player")) then
            return refusal("wm_busy")
        end
        if not (IsResting and IsResting()) then
            return refusal("wm_place")
        end
    end
    if wm.on and wm.wantedState > 0 then
        return refusal("wm_wanted")
    end
    if WM.CooldownLeft(wm) >= 1 then
        return refusal("wm_cooldown")
    end
    return nil
end

------------------------------------------------------------------------------------------------------
-- The intent (one gate, a little above the server's 2 s; ERR busy waits a full gap)
------------------------------------------------------------------------------------------------------
local nextAt = 0
local pending           -- { want, at } until WMST or ERR answers

function WM.Pending()
    return pending ~= nil and GetTime() - pending.at < WM.PENDING
end

-- Ask the server for War Mode on (true) or off (false). Only the connection, the feature and the client's own gap
-- are checked here: /bh warmode on|off uses this as it is, the server decides the rest.
function WM.Request(want)
    local ok, why = connected()
    if not ok then
        notice(nil, why)
        return false
    end
    if not WM.Live() then
        notice("wm_off")
        return false
    end
    local now = GetTime()
    if now < nextAt then
        return false
    end
    if not Comm.Send("WARMODE", want and 1 or 0) then
        return false
    end
    nextAt = now + WM.GAP
    pending = { want = want and true or false, at = now }
    WM.lastError = nil
    ns.Fire("WARMODE_PENDING", pending.want)
    return true
end

-- The button and the orb: the opposite of the state now, past the client's gates and a confirmation.
function WM.Toggle()
    local code, text = WM.Block()
    if code or text then
        notice(code, text)
        return false
    end
    if WM.Pending() then
        return false
    end
    local want = not S.warMode.on
    UI.Confirm(want and WM.CONFIRM_ON or WM.CONFIRM_OFF, function()
        WM.Request(want)
    end, want and "Turn on" or "Turn off")
    return true
end

ns.On("ERR", function(e)
    if not e or e.op ~= "WARMODE" then
        return
    end
    pending = nil
    WM.lastError = e
    e.warAt = GetTime()
    if e.code == "busy" then
        nextAt = GetTime() + WM.GAP
    end
    ns.Fire("STATE", "WMST")
end)

ns.On("STATE", function(topic)
    if topic == "WMST" and S.warMode and pending and S.warMode.recvAt >= pending.at then
        pending = nil
    end
end)

-- The objective state goes when its feature does; with `all` War Mode's own too.
function WM.Forget(all)
    if S.wpZone or S.wpCap or S.wpMap then
        S.wpZone, S.wpCap, S.wpMap = nil, nil, nil
        ns.Fire("STATE", "WPZ")
        ns.Fire("STATE", "WPCAP")
        ns.Fire("STATE", "WPMAP")
    end
    if all and (S.warMode or S.wanted) then
        S.warMode, S.wanted = nil, nil
        pending, WM.lastError = nil, nil
        ns.Fire("STATE", "WMST")
        ns.Fire("STATE", "WANTED")
    end
end

-- After the handshake (and a HELLO with new bits): ask for what is live, forget what is not.
ns.On("HELLO", function()
    if not WM.Live() then
        WM.Forget(true)
    else
        Comm.Get("WMST")
        if WM.ObjectivesLive() then
            Comm.Get("WPZ")
            Comm.Get("WPMAP")
        else
            WM.Forget(false)
        end
        if S.warMode and S.warMode.on then
            Comm.Get("WANTED")
        end
    end
    ns.Orbs.Refresh()
    if WM.page and WM.page:IsVisible() then
        WM.page:Refresh()
    end
end)

-- War Mode on: the Wanted players of the zone (only War Mode players get them); off: they are gone.
ns.On("WARMODE_CHANGED", function(wm)
    if not WM.Live() then
        return
    end
    if wm.on then
        Comm.Get("WANTED")
    elseif S.wanted then
        S.wanted = nil
        ns.Fire("STATE", "WANTED")
    end
end)

------------------------------------------------------------------------------------------------------
-- Activities: the War Mode page
------------------------------------------------------------------------------------------------------
local P = A.NewPage()
A.AddPage("warmode", P)
WM.page = P

local HERO_H = 150
local CARD_H = 170
local CARD_W = floor((A.PW - 12) / 2)
local FRONT_H = A.PH - HERO_H - CARD_H - 24
local VALUE_W = 220

local hero = UI.Box(P, A.PW, HERO_H, C.eraBg, C.eraBorder)
hero:SetPoint("TOPLEFT", P, "TOPLEFT", 0, 0)
P.hero = hero
hero.badge = UI.Badge(hero, 64, "shield", C.active, C.gold)
hero.badge:SetPoint("TOPLEFT", hero, "TOPLEFT", 16, -18)
hero.kicker = UI.Text(hero, 11, WM.COLOR)
hero.kicker:SetPoint("TOPLEFT", hero, "TOPLEFT", 96, -18)
hero.kicker:SetText(WM.KICKER)
hero.title = UI.Text(hero, 22, C.goldPale, "title")
hero.title:SetPoint("TOPLEFT", hero.kicker, "BOTTOMLEFT", 0, -4)
UI.OneLine(hero.title, 400)
hero.text = UI.Text(hero, 12, C.mid)
hero.text:SetPoint("TOPLEFT", hero.title, "BOTTOMLEFT", 0, -6)
hero.text:SetWidth(440)
hero.text:SetHeight(46)
hero.text:SetJustifyV("TOP")
hero.text:SetText(WM.TEXT)
hero.status = UI.Text(hero, 13, C.goldLight)
hero.status:SetPoint("BOTTOMLEFT", hero, "BOTTOMLEFT", 96, 14)
UI.OneLine(hero.status, 440)
hero.toggle = UI.Button(hero, 200, 36, "Turn War Mode on", "gold", 14)
hero.toggle:SetPoint("TOPRIGHT", hero, "TOPRIGHT", -18, -26)
hero.toggle:SetScript("OnClick", function()
    WM.Toggle()
end)
hero.reason = UI.Text(hero, 12, C.red, "body", "RIGHT")
hero.reason:SetPoint("TOPRIGHT", hero.toggle, "BOTTOMRIGHT", 0, -8)
hero.reason:SetWidth(260)
hero.reason:SetHeight(32)
hero.reason:SetJustifyV("TOP")
P.toggle = hero.toggle

-- A card with a label and rows of label / value (`ys`: each row's offset from the top, else 22 px apart).
local function card(w, h, title, rows, ys)
    local c = UI.Box(P, w, h, C.card, C.border)
    c.label = UI.Text(c, 11, C.dim)
    c.label:SetPoint("TOPLEFT", c, "TOPLEFT", 12, -12)
    c.label:SetText(title)
    c.rows = {}
    for i = 1, rows do
        local y = ys and ys[i] or (-34 - (i - 1) * 22)
        local l = UI.Text(c, 12, C.mid)
        l:SetPoint("TOPLEFT", c, "TOPLEFT", 12, y)
        UI.OneLine(l, w - VALUE_W - 30)
        local v = UI.Text(c, 12, C.text, "body", "RIGHT")
        v:SetPoint("TOPRIGHT", c, "TOPRIGHT", -12, y)
        UI.OneLine(v, VALUE_W)
        c.rows[i] = { label = l, value = v }
    end
    return c
end

local function setRow(row, label, value, color)
    UI.SetText(row.label, label or "")
    UI.SetText(row.value, value or "")
    UI.SetColor(row.value, color or C.text)
end

local bonus = card(CARD_W, CARD_H, "BONUSES IN THE OPEN WORLD", 5)
bonus:SetPoint("TOPLEFT", hero, "BOTTOMLEFT", 0, -12)
bonus.icon = bonus:CreateTexture(nil, "ARTWORK")
bonus.icon:SetSize(16, 16)
bonus.icon:Hide()
P.bonus = bonus

-- the honor row, its bar, the Shards row, its bar, then the streak, the kills and the bounty
local today = card(CARD_W, CARD_H, "TODAY", 5, { -32, -76, -110, -130, -150 })
today:SetPoint("TOPRIGHT", hero, "BOTTOMRIGHT", 0, -12)
today.honorBar = UI.Bar(today, CARD_W - 24, 5, WM.COLOR, C.deep)
today.honorBar:SetPoint("TOPLEFT", today, "TOPLEFT", 12, -51)
today.shardBar = UI.Bar(today, CARD_W - 24, 5, C.teal, C.deep)
today.shardBar:SetPoint("TOPLEFT", today, "TOPLEFT", 12, -95)
P.today = today

local fronts = UI.Box(P, A.PW, FRONT_H, C.card, C.border)
fronts:SetPoint("TOPLEFT", bonus, "BOTTOMLEFT", 0, -12)
fronts.label = UI.Text(fronts, 11, C.dim)
fronts.label:SetPoint("TOPLEFT", fronts, "TOPLEFT", 12, -12)
fronts.label:SetText("WAR FRONTS")
fronts.lines = {}
for i = 1, 3 do
    local l = UI.Text(fronts, 13, i == 1 and C.goldPale or C.mid)
    l:SetPoint("TOPLEFT", fronts, "TOPLEFT", 12, -32 - (i - 1) * 20)
    UI.OneLine(l, A.PW - 24)
    fronts.lines[i] = l
end
fronts.zones = {}
local ZONE_COLS = { 0, 260, 400, 560, 680 }
for i = 1, 4 do
    local row = {}
    for k, x in ipairs(ZONE_COLS) do
        local t = UI.Text(fronts, 11, k == 1 and C.text or C.mid)
        t:SetPoint("TOPLEFT", fronts, "TOPLEFT", 12 + x, -100 - (i - 1) * 18)
        UI.OneLine(t, (ZONE_COLS[k + 1] or (A.PW - 24)) - x - 8)
        row[k] = t
    end
    fronts.zones[i] = row
end
P.fronts = fronts

local function zoneLine(label, zoneId, state, sec, recvAt)
    if not zoneId or zoneId == 0 then
        return label .. ": none at this level cap"
    end
    local left = ns.WarLeft(sec, recvAt) or 0
    local txt = label .. ": " .. ns.WarZoneName(zoneId)
    if state == 1 then
        txt = txt .. "  -  " .. WM.Clock(left) .. " left"
    elseif state == 2 then
        txt = txt .. "  -  ceasefire " .. WM.Clock(left)
    end
    return txt
end

function P:RefreshFronts()
    for _, l in ipairs(fronts.lines) do
        l:SetText("")
    end
    for _, row in ipairs(fronts.zones) do
        for _, t in ipairs(row) do
            t:SetText("")
        end
    end
    if not WM.ObjectivesLive() then
        fronts.lines[1]:SetText("World PvP objectives are not open on this realm right now.")
        return
    end
    local m = S.wpMap
    if not m then
        fronts.lines[1]:SetText(Comm.ready and "Waiting for the realm..." or "Not connected to the realm.")
        return
    end
    UI.SetText(fronts.lines[1], zoneLine("Bleak Front", m.frontZone, m.frontState, m.secondsLeft, m.recvAt))
    if m.nextZone and m.nextZone > 0 then
        local starts = ns.WarLeft(m.nextStartsSec, m.recvAt) or 0
        UI.SetText(fronts.lines[2], "Next: " .. ns.WarZoneName(m.nextZone) .. " in " .. U.Duration(ceil(starts)))
    end
    if m.levelZone and m.levelZone > 0 then
        UI.SetText(fronts.lines[3], zoneLine("Levelling Front", m.levelZone, m.levelState, m.levelSecondsLeft,
            m.recvAt))
    end
    -- the zones: the running ones first
    local list = {}
    for _, z in ipairs(m.zones) do
        list[#list + 1] = z
    end
    table.sort(list, function(a, b)
        if (a.state == 1) ~= (b.state == 1) then
            return a.state == 1
        end
        return a.zoneId < b.zoneId
    end)
    for i, row in ipairs(fronts.zones) do
        local z = list[i]
        if z then
            UI.SetText(row[1], ns.WarZoneName(z.zoneId))
            UI.SetText(row[2], WM.KIND[z.kind] or z.kind)
            row[3]:SetText(U.Color(WM.TeamColor("A"), "A " .. z.heldA) .. "  " .. U.Color(WM.TeamColor("H"),
                "H " .. z.heldH) .. "  " .. U.Color(WM.TeamColor("N"), "N " .. z.neutral))
            local band = ""
            if z.levelMin and z.levelMax then
                band = z.levelMin == z.levelMax and ("Level " .. z.levelMin) or ("Levels " .. z.levelMin .. "-"
                    .. z.levelMax)
            end
            UI.SetText(row[4], band)
            UI.SetText(row[5], WM.ZONE_STATE[z.state] or "")
        end
    end
end

function P:Refresh()
    local wm = WM.State()
    local code, why = WM.Block()
    -- the hero: state, the hunt, the button and why it is grey
    hero.badge.ring:SetVertexColor(UI.Rgb(wm and wm.on and WM.COLOR or C.gold))
    hero.badge.glyph:SetVertexColor(UI.Rgb(wm and wm.on and WM.COLOR or C.goldLight))
    UI.SetColor(hero.title, wm and wm.on and WM.COLOR or C.goldPale)
    if not WM.Live() then
        hero.title:SetText("War Mode is not available")
        UI.SetText(hero.status, ns.ErrorText({ code = "wm_off" }))
        UI.SetColor(hero.status, C.mute)
        hero.toggle:SetLabel("Turn War Mode on")
        hero.toggle:SetActive(false)
        hero.reason:SetText("")
    elseif not wm then
        hero.title:SetText("War Mode")
        UI.SetText(hero.status, why or "Waiting for the realm...")
        UI.SetColor(hero.status, C.mute)
        hero.toggle:SetLabel("Turn War Mode on")
        hero.toggle:SetActive(false)
        hero.reason:SetText("")
    else
        hero.title:SetText(wm.on and "War Mode is on" or "War Mode is off")
        local status, color = "", C.goldLight
        if wm.wantedState > 0 then
            status = (WM.WANTED[wm.wantedState] or "Wanted") .. "  -  " .. WM.Clock(WM.WantedLeft(wm)) .. " left"
            if wm.bountyHonor > 0 then
                status = status .. "  -  bounty " .. U.Commas(wm.bountyHonor) .. " honor"
            end
            color = C.red
        elseif WM.CooldownLeft(wm) >= 1 then
            status = "You can change War Mode again in " .. WM.Clock(WM.CooldownLeft(wm))
            color = C.mid
        elseif wm.on then
            status = "Flagged for PvP. Streak " .. wm.streak .. (wm.streak == 1 and " kill" or " kills")
        else
            status = "Change it at an inn or in a city."
            color = C.mid
        end
        UI.SetText(hero.status, status)
        UI.SetColor(hero.status, color)
        hero.toggle:SetLabel(wm.on and "Turn War Mode off" or "Turn War Mode on")
        hero.toggle:SetStyle(wm.on and "dark" or "gold")
        local busy = WM.Pending()
        hero.toggle:SetActive(not code and not why and not busy)
        if busy then
            hero.reason:SetText("Waiting for the realm...")
            UI.SetColor(hero.reason, C.mid)
        else
            local last = WM.lastError
            local err = last and GetTime() - (last.warAt or 0) < 30 and last.shown or nil
            UI.SetText(hero.reason, why or err or "")
            UI.SetColor(hero.reason, C.red)
        end
    end
    -- the bonuses
    local rows = bonus.rows
    for _, row in ipairs(rows) do
        setRow(row, "", "")
    end
    bonus.icon:Hide()
    if wm then
        local base = WM.BonusText(wm)
        setRow(rows[1], "War Mode", base ~= "" and base or "none", wm.on and C.goldLight or C.mute)
        local mine = WM.MyTeam()
        if wm.underdogTeam and wm.underdogPct > 0 then
            local you = mine and wm.underdogTeam == mine
            setRow(rows[2], "Underdog", "+" .. wm.underdogPct .. "% for the " .. WM.TeamName(wm.underdogTeam)
                .. (you and " (you)" or ""), you and C.teal or C.mid)
            WM.SetIcon(bonus.icon, WM.TEAM[wm.underdogTeam].icon)
            bonus.icon:ClearAllPoints()
            bonus.icon:SetPoint("RIGHT", rows[2].value, "RIGHT", -floor(rows[2].value:GetStringWidth() + 6), 0)
            bonus.icon:Show()
        else
            setRow(rows[2], "Underdog", "none", C.mute)
        end
        setRow(rows[3], "War Mode players", wm.wmAlliance .. " Alliance  -  " .. wm.wmHorde .. " Horde")
        local z = WM.ObjectivesLive() and S.wpZone
        if z and (z.dominionStacks or 0) > 0 and z.dominionTeam then
            setRow(rows[4], "Dominion here", "x" .. z.dominionStacks .. "  " .. ns.WarZoneName(z.zoneId),
                WM.TeamColor(z.dominionTeam))
        elseif WM.ObjectivesLive() then
            setRow(rows[4], "Dominion here", "none", C.mute)
        end
        local last = S.warEvent
        if last and last.kind == "R" then
            setRow(rows[5], "Last reward", WM.RewardText(last), C.goldLight)
        end
    else
        setRow(rows[1], "War Mode", "-", C.mute)
    end
    -- today
    local t = today.rows
    if wm then
        setRow(t[1], "Bonus honor", U.Commas(wm.todayBonusHonor) .. " / " .. U.Commas(wm.bonusHonorCap))
        today.honorBar:SetProgress(wm.bonusHonorCap > 0 and wm.todayBonusHonor / wm.bonusHonorCap or 0)
        setRow(t[2], "War Mode Shards", U.Commas(wm.todayShards) .. " / " .. U.Commas(wm.shardsCap))
        today.shardBar:SetProgress(wm.shardsCap > 0 and wm.todayShards / wm.shardsCap or 0)
        setRow(t[3], "Streak", wm.streak .. "  (best " .. wm.bestStreak .. ")")
        setRow(t[4], "Kills / deaths", U.Commas(wm.kills) .. " / " .. U.Commas(wm.deaths))
        if wm.bountyHonor > 0 then
            setRow(t[5], "Bounty on you", U.Commas(wm.bountyHonor) .. " honor", C.red)
        else
            setRow(t[5], "", "")
        end
    else
        for _, row in ipairs(t) do
            setRow(row, "", "")
        end
        setRow(t[1], "Bonus honor", "-", C.mute)
        today.honorBar:SetProgress(0)
        today.shardBar:SetProgress(0)
    end
    P:RefreshFronts()
end

function P:Tick()
    if self:IsVisible() then
        self:Refresh()
    end
end

function P:OnOpen()
    if WM.Live() then
        Comm.Get("WMST")
        if WM.ObjectivesLive() then
            Comm.Get("WPMAP")
        end
    end
end

ns.On("STATE", function(topic)
    if (topic == "WMST" or topic == "WPMAP" or topic == "WPZ") and P:IsVisible() then
        P:Refresh()
    end
end)

ns.On("WARMODE_PENDING", function()
    if P:IsVisible() then
        P:Refresh()
    end
end)

-- Resting, combat, death and levels change what the button may do.
for _, event in ipairs({ "PLAYER_UPDATE_RESTING", "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED", "PLAYER_DEAD",
    "PLAYER_ALIVE", "PLAYER_UNGHOST", "PLAYER_LEVEL_UP" }) do
    ns.RegisterEvent(event, function()
        if P:IsVisible() then
            P:Refresh()
        end
    end)
end

------------------------------------------------------------------------------------------------------
-- Opening: /bh warmode, the minimap orb
------------------------------------------------------------------------------------------------------
local function openPage(toggle)
    if not WM.Live() then
        notice("wm_off")
        return
    end
    if toggle and A.frame:IsShown() and A.current == "warmode" then
        A.frame:Hide()
        return
    end
    A.Show("warmode")
end
UI.RegisterOpener("warmode", openPage)

local function orbLines()
    local lines = { "War Mode" }
    local wm = WM.State()
    if not wm then
        lines[#lines + 1] = { "Waiting for the realm", C.mute }
        return lines
    end
    lines[#lines + 1] = { wm.on and "On: flagged for PvP" or "Off", wm.on and WM.COLOR or C.mid }
    local base = WM.BonusText(wm)
    if wm.on and base ~= "" then
        lines[#lines + 1] = { base, C.goldLight }
    end
    if wm.underdogTeam and wm.underdogPct > 0 then
        lines[#lines + 1] = { "Underdog: +" .. wm.underdogPct .. "% for the " .. WM.TeamName(wm.underdogTeam), C.mid }
    end
    if wm.wantedState > 0 then
        lines[#lines + 1] = { (WM.WANTED[wm.wantedState] or "Wanted") .. ": " .. WM.Clock(WM.WantedLeft(wm))
            .. " left", C.red }
    end
    local m = WM.ObjectivesLive() and S.wpMap
    if m and m.frontZone and m.frontZone > 0 then
        lines[#lines + 1] = { U.Safe(zoneLine("Front", m.frontZone, m.frontState, m.secondsLeft, m.recvAt)), C.mid }
    end
    lines[#lines + 1] = { "Click to open", C.mute }
    return lines
end

WM.orb = ns.Orbs.Add({
    key = "warmode", glyph = "shield", title = "War Mode", angle = 70,
    available = WM.Live,
    onClick = function()
        openPage(true)
    end,
    lines = orbLines,
    update = function(b)
        local on, wanted = WM.IsOn(), WM.Wanted()
        if on and not b:IsMouseOver() then
            b.ring:SetVertexColor(UI.Rgb(WM.COLOR))
        end
        b.glyph:SetVertexColor(UI.Rgb(on and WM.COLOR or C.goldLight))
        if wanted then
            b.pulse = (b.pulse or 0) + 0.25
            b.ring:SetAlpha(0.45 + 0.55 * abs(sin(b.pulse * 2)))
        else
            b.ring:SetAlpha(1)
        end
    end,
})

ns.On("WARMODE_CHANGED", function(wm)
    if not wm.on and WM.orb then
        WM.orb.ring:SetVertexColor(UI.Rgb(C.gold))
    end
end)

ns.AddCommand("warmode", "War Mode: /bh warmode [on|off]", function(args)
    local a = (args or ""):lower():match("^(%S*)")
    if a == "on" or a == "off" then
        WM.Request(a == "on")
    else
        openPage(false)
    end
end)

------------------------------------------------------------------------------------------------------
-- /bh demo: War Mode and a short Front (Demo.lua routes WARMODE and GET WMST/WPZ/WPMAP/WANTED here)
------------------------------------------------------------------------------------------------------
local demo

local function demoPush(op, records)
    if ns.Demo then
        ns.Demo.Push(op, records)
    end
end

local function demoAfter(sec, fn)
    local run = demo and demo.run
    ns.After(sec, function()
        if Comm.demo and demo and demo.run == run then
            fn()
        end
    end)
end

local function demoState()
    local d = demo
    demoPush("WMST", { { d.on and 1 or 0, d.cd or 0, "", 20, 10, 10, 0, 8, "H", 31, 22, d.streak or 0, d.wanted or 0,
        d.wanted and 900 or 0, d.wanted and 248 or 0, d.honor or 0, 3720, d.shards or 0, 60, 7, 118 + (d.streak or 0),
        96 } })
end

local function demoZone()
    local d = demo
    demoPush("WPZ", { { 2817, "F", 1, 4320, 620, 380, "A", d.held or 2, 80, 80 },
        { "O", 1, "Violet Stand", 512, 388, "A", 1000, 1 },
        { "O", 2, "Forlorn Woods", 604, 455, d.held == 3 and "A" or "N", d.slider or -120, d.held == 3 and 1 or 6 },
        { "O", 3, "Sunreaver Rise", 701, 512, "A", 800, 1 } })
end

local function demoMap()
    demoPush("WPMAP", { { 2817, 1, 4320, 66, 4920, 267, 1, 4320 }, { "Z", 2817, "F", demo.held or 2, 0, 1, 80, 80, 1 },
        { "Z", 267, "L", 1, 1, 1, 20, 35, 1 }, { "Z", 3483, "S", 2, 1, 0, "", "", 1 },
        { "Z", 4197, "W", 0, 1, 0, "", "", 0 } })
end

local function demoFront()
    demoPush("WPEV", { { "X", 2817, 900, "Crystalsong Forest" } })
    demoAfter(4, function()
        demoPush("WPEV", { { "F", 2817, 7200, "Crystalsong Forest" } })
        demoMap()
        demoZone()
    end)
    for i = 1, 8 do
        demoAfter(5 + i, function()
            demo.slider = -120 + i * 45
            demoPush("WPCAP", { { 2, demo.slider, 20, demo.slider > 200 and 1 or 6, 3, 1, 5 } })
        end)
    end
    demoAfter(14, function()
        demo.held = 3
        demoPush("WPEV", { { "C", 2817, 2, "A", "Forlorn Woods" } })
        demoPush("WPEV", { { "R", "C", 186, 0, 2, 1000 } })
        demoZone()
        demoPush("WPCAP", { { 0 } })
    end)
    demoAfter(18, function()
        demo.streak, demo.honor = 5, 412
        demoState()
        demoPush("WPEV", { { "W", "Garrick Stormwind", 4, "H", 5, "S" } })
        demoPush("WANTED", { { 2817 }, { "W", "Garrick Stormwind", 4, "H", 5, "S", 248, 5, 560, 402, 0 } })
    end)
    demoAfter(24, function()
        demoPush("WPEV", { { "B", ns.PlayerName() or "You", "Garrick Stormwind", 248, 5 } })
        demoPush("WANTED", { { 2817 } })
    end)
end

-- Returns true when the intent was the demo's (and is answered here).
function WM.DemoRespond(op, recs)
    local f = recs[1] or {}
    if op == "WARMODE" then
        demo = demo or { run = 0 }
        demo.run = demo.run + 1
        demo.on = f[1] == "1"
        demo.cd = 900
        demoState()
        demoPush("TOAST", { { "I", demo.on and "War Mode is on" or "War Mode is off",
            demo.on and "Flagged for PvP in the open world" or "Your PvP flag fades in 5 minutes" } })
        if demo.on then
            demoAfter(2, demoFront)
        end
        return true
    end
    if op ~= "GET" then
        return false
    end
    demo = demo or { run = 0 }
    for _, r in ipairs(recs) do
        if r[1] == "WMST" then
            demoState()
        elseif r[1] == "WPZ" then
            demoZone()
        elseif r[1] == "WPMAP" then
            demoMap()
        end
    end
    return false    -- the other topics of the GET are Demo.lua's
end

function WM.DemoReset()
    demo = nil
end
