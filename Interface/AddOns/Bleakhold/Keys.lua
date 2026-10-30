-- Bleakhold: Activities > Mythic+ Dungeons, the old window's page (old BleakholdActivities.lua :285-349, the owner's
-- reference screenshot) in its anatomy (Activities.lua A.Page): the keystone (icon, "+level dungeon", its timer), this
-- week's affixes as spell icons with the level each joins at (+2, +4, +7, +10, then the Mythic Champions and Mythical
-- Boons), the season's dungeons with their pictures and the best keystone timed in each, and Set difficulty: Mythic
-- with the group's difficulty above it. Our extras: the week's best key, the Mythical Caches left and the Mythic Coins
-- earned this week in the stat column, Start keystone (KSTART) with why it is greyed, and the difficulty from our KEY
-- (its mode) so Heroic shows too.
--
-- Data: the old page's BHMP K / W / L / Z and O (Legacy.lua: the keystone opened the start); our KEY, WEEK, ERA and
-- DEF A / D / M where they carry more (the keystone's item, the week's best, the caches, the affix texts, the level
-- ladder, the key level).
-- Rules as the server has them (mod-bleakhold bh_mplus.cpp): the four weekly affixes join at +2, +4, +7 and +10, the
-- Champions and Boons at Champions.MinLevel (W's third field); Mythic 0 and keys need Mythic.MinLevel (80; below it
-- the dungeon stays Normal); Mythic 0 ends with the final boss and gives the first keystone (+1); a key is used inside
-- its own dungeon by the group leader (right-click it, or the Font of Power, then Start keystone within 5 minutes) and
-- its countdown cannot be stopped; in time it goes up 1 to 3 levels and moves to another dungeon, over time it drops a
-- level; only the group leader sets the difficulty, outside dungeons (SetDifficulty, the bridge's KMODE).
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S
local A = ns.Activities
local L = ns.Legacy

local floor, max, min = math.floor, math.max, math.min

local P = A.Page("keys", {
    title = "Mythic+ Dungeons",
    desc = "Timed dungeons with weekly affixes. Finish a Mythic 0 dungeon for your first keystone, then, with a group "
        .. "of 5, right-click the key inside its dungeon. Beat the timer to upgrade it.",
})
ns.Keys = P

P.KEY_ITEM = 964000                       -- the keystone (BHMP::ITEM_KEYSTONE)
P.AFFIX_LEVELS = UI.AFFIX_LEVELS          -- +2, +4, +7, +10 (bh_mplus.cpp minLvl)
P.CHAMPIONS, P.BOONS = 13, 14             -- the server's affix ids (BHMP::AFF_CHAMPIONS, AFF_BOONS)
-- The server's affix ids and names (bh_mplus.cpp AffixName; the old page's table :18-25), for when DEF A is not here.
P.AFFIX_NAMES = {
    [1] = "Fortified", [2] = "Tyrannical", [3] = "Bolstering", [4] = "Raging", [5] = "Sanguine", [6] = "Bursting",
    [7] = "Inspiring", [8] = "Necrotic", [9] = "Grievous", [10] = "Volcanic", [11] = "Explosive", [12] = "Quaking",
    [13] = "Mythic Champions", [14] = "Mythical Boons", [15] = "Avenger", [16] = "True Sight", [17] = "Resistant",
    [18] = "Pack Tactics",
}
P.SPECIAL_ICONS = { [13] = "Spell_Holy_SummonChampion", [14] = "Spell_Holy_DivineIntervention" }
P.SPECIAL_TEXT = {
    [13] = "Mythic Champions guard the dungeon: one must fall to finish the key.",
    [14] = "Mythical Boons lie in the dungeon: touch one for a short blessing.",
}

------------------------------------------------------------------------------------------------------
-- The stat column: our extras
------------------------------------------------------------------------------------------------------
P.best = P:Stat(1, "Best This Week")
P.caches = P:Stat(2, "Mythical Caches")
-- WEEK's coins are the week's earnings toward the cap (the bridge's WeeklyCoins), not the coins in the bags: the
-- server words the same number "Mythic Coins this week: 120/500" (.mplus)
P.coins = P:Stat(3, "Mythic Coins This Week")
P.COINS_TIP = { "Mythic Coins This Week", { "Earned this week toward the weekly cap; keys, the Rift and Heroic bosses "
    .. "count.", C.text, true } }
P.coinsTip = CreateFrame("Frame", nil, P)
P.coinsTip:SetPoint("TOPRIGHT", P.coins.label, "TOPRIGHT", 0, 0)
P.coinsTip:SetSize(170, 40)
P.coinsTip:EnableMouse(true)
P.coinsTip:SetScript("OnEnter", function(self)
    UI.ShowTooltip(self, P.COINS_TIP)
end)
P.coinsTip:SetScript("OnLeave", function()
    if GameTooltip then
        GameTooltip:Hide()
    end
end)

------------------------------------------------------------------------------------------------------
-- The keystone (old :288-290)
------------------------------------------------------------------------------------------------------
P.keyIcon = UI.Icon(P, 44, "INV_Misc_Key_15")
P.keyIcon:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD, A.BODY_Y)
P.keyIcon:EnableMouse(true)
P.keyText = UI.Text(P, 15, C.text)
P.keyText:SetPoint("TOPLEFT", P.keyIcon, "TOPRIGHT", 10, -4)
UI.OneLine(P.keyText, 360)
P.keySub = UI.Text(P, 11, C.dim)
P.keySub:SetPoint("TOPLEFT", P.keyText, "BOTTOMLEFT", 0, -4)
UI.OneLine(P.keySub, 360)

-- the keystone's levels, as the server words them (DEF M; the built-in ladder before it sends one)
function P.LadderTooltip()
    local lines = { "Keystone Levels" }
    for _, id in ipairs(ns.DefIds("M")) do
        local d = ns.Def("M", id)
        if d and d.text then
            lines[#lines + 1] = { (id == 0 and "Mythic 0" or ("+" .. id)) .. ":  " .. U.Safe(d.text), C.text, true }
        end
    end
    return lines
end
P.keyIcon:SetScript("OnEnter", function(self)
    UI.ShowTooltip(self, P.LadderTooltip())
end)
P.keyIcon:SetScript("OnLeave", function()
    if GameTooltip then
        GameTooltip:Hide()
    end
end)

------------------------------------------------------------------------------------------------------
-- This week's affixes (old :291-298, :324-339)
------------------------------------------------------------------------------------------------------
P.affixTitle = P:Section("This Week's Affixes", A.PAD, -184)
P.aff = {}
for i = 1, 6 do
    local a = UI.AffixIcon(P, 34)
    a:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD + (i - 1) * 40, -206)
    a:Hide()
    P.aff[i] = a
end
P.noAffixes = UI.Text(P, 11, C.dim)
P.noAffixes:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD, -214)

------------------------------------------------------------------------------------------------------
-- Season dungeons (old :299-310, :340-347)
------------------------------------------------------------------------------------------------------
P.seasonTitle = P:Section("Season Dungeons", A.PAD, -258)
P.ROW_W, P.ROW_H, P.COL_PITCH, P.ROW_PITCH = 206, 40, 214, 44
P.rows = {}
for i = 1, 12 do
    local col, row = (i - 1) % 2, floor((i - 1) / 2)
    local r = UI.Box(P, P.ROW_W, P.ROW_H, C.card, C.border, nil, "edge")
    r:SetPoint("TOPLEFT", P, "TOPLEFT", 18 + col * P.COL_PITCH, -280 - row * P.ROW_PITCH)
    r.thumb = r:CreateTexture(nil, "ARTWORK")
    r.thumb:SetSize(64, 36)
    r.thumb:SetPoint("LEFT", r, "LEFT", 2, 0)
    r.name = UI.Text(r, 11, C.text)
    r.name:SetPoint("LEFT", r.thumb, "RIGHT", 8, 0)
    r.name:SetWidth(100)
    r.best = UI.Text(r, 14, C.gold, "body", "RIGHT")
    r.best:SetFont(UI.FONT_BODY, 14, "OUTLINE")
    r.best:SetPoint("RIGHT", r, "RIGHT", -8, 0)
    r:EnableMouse(true)
    r:SetScript("OnEnter", function(self)
        if self.d then
            UI.ShowTooltip(self, P.DungeonTooltip(self.d))
        end
    end)
    r:SetScript("OnLeave", function()
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    r:Hide()
    P.rows[i] = r
end

function P.DungeonTooltip(d)
    local lines = { U.Safe(d.name) }
    if (d.timer or 0) > 0 then
        lines[#lines + 1] = { "Keystone timer " .. U.Clock(d.timer), C.text }
    end
    if (d.best or 0) > 0 then
        lines[#lines + 1] = { "Your best keystone: +" .. d.best, C.gold }
    else
        lines[#lines + 1] = { "No keystone timed here yet", C.dim }
    end
    return lines
end

------------------------------------------------------------------------------------------------------
-- Set difficulty: Mythic (old :311-313) and Start keystone
------------------------------------------------------------------------------------------------------
P.mythic = UI.Button(P, 190, 26, "Set difficulty: Mythic", "red", 12)
P.mythic:SetPoint("BOTTOMRIGHT", P, "BOTTOMRIGHT", -18, 18)
P.mythic:SetScript("OnClick", function()
    L.SetDifficulty(3)
end)
P.mythic.tooltip = function()
    local m0 = ns.Def("M", 0)
    local lines = { "Set difficulty: Mythic", { m0 and U.Safe(m0.text) or "Your group's Mythic+ dungeons become Mythic "
        .. "0.", C.text, true }, { "The party leader sets it, outside dungeons.", C.dim, true } }
    if P.UnderKeyLevel() then
        -- the server takes the choice, but below its level the dungeon stays Normal for this player (bh_mplus.cpp)
        lines[#lines + 1] = { P.LevelText() .. " Below it, the dungeon stays Normal for you.", C.orange, true }
    end
    local block = P.MythicBlock()
    if block then
        lines[#lines + 1] = { block, C.orange, true }
    end
    return lines
end
P.diff = UI.Text(P, 11, C.dim, "body", "RIGHT")
P.diff:SetPoint("BOTTOMRIGHT", P.mythic, "TOPRIGHT", 0, 6)

P.start = UI.Button(P, 150, 26, "Start keystone", "red", 12)
P.start:SetPoint("BOTTOMRIGHT", P.mythic, "BOTTOMLEFT", -8, 0)
P.start:SetScript("OnClick", function()
    Comm.Send("KSTART")
end)
P.start.tooltip = function()
    return { "Start keystone", { "Inside your keystone's dungeon: right-click the keystone (or use the Font of "
        .. "Power), then press this to start the countdown for your group.", C.text, true },
        { "A keystone needs " .. P.KEY_MIN_PLAYERS .. " players inside the dungeon.", C.text, true },
        { "The countdown cannot be stopped once it starts.", C.dim, true } }
end
-- why Start keystone is greyed (P.StartBlock), under the season grid
P.startHint = UI.Text(P, 11, C.dim)
P.startHint:SetPoint("BOTTOMLEFT", P, "BOTTOMLEFT", A.PAD, 24)
P.startHint:SetWidth(400)

------------------------------------------------------------------------------------------------------
-- Refresh
------------------------------------------------------------------------------------------------------
-- The keystone: our KEY when it has one (its item, level, dungeon), else the old K. Answers level, name, timer and
-- whether one is known at all; nil level for no keystone.
function P.Keystone()
    local k = S.key
    local old = L.mplus.key
    if k and k.hasKey then
        local name = ns.DefName("D", k.dungeonId, nil) or (old and old.name) or ns.DungeonName(k.dungeonId)
        local def = ns.Def("D", k.dungeonId)
        local timer = (def and def.timeLimitSec) or (old and old.timer) or 0
        return k.level, name, timer, true, k.depleted
    elseif k then
        return nil, nil, 0, true
    elseif old then
        return old.level, old.name, old.timer, true
    end
    return nil, nil, 0, L.mplus.keyKnown
end

-- The level Mythic 0 and the keys need: the server's DEF D lvlMin of the key dungeons (those with a time limit), which
-- the bridge sets to Mythic.MinLevel (bh_ui_bridge_map.cpp DungeonDefs: keyMinLevel); P.KEY_MIN_LEVEL until the server
-- says (the built-in DEF D of Data.lua has the dungeons' own levels, not the key level).
P.KEY_MIN_LEVEL = 80
-- Players inside the dungeon a keystone needs (bh_mplus.cpp StartRun, Bleakhold.MythicPlus.KeyMinPlayers; only staff
-- accounts may start one with fewer).
P.KEY_MIN_PLAYERS = 5
function P.KeyMinLevel()
    local builtIn = ns.Data and ns.Data.defs and ns.Data.defs.D or {}
    local lvl
    for _, id in ipairs(ns.DefIds("D")) do
        local d = ns.Def("D", id)
        if d and d ~= builtIn[id] and (d.timeLimitSec or 0) > 0 and (d.lvlMin or 0) > 0 then
            lvl = max(lvl or 0, d.lvlMin)
        end
    end
    return lvl or P.KEY_MIN_LEVEL
end

function P.UnderKeyLevel()
    local level = UnitLevel and UnitLevel("player") or 0
    return level > 0 and level < P.KeyMinLevel()
end

function P.LevelText()
    return "Mythic+ opens at level " .. P.KeyMinLevel() .. "."
end

-- The week's affixes: the old W (with the Champions level), else our ERA's.
function P.WeekAffixes()
    local w = L.mplus.week
    if #w.affixes > 0 then
        return w.affixes, w.champMinLevel
    end
    local ids = S.era and S.era.affixes or {}
    return ids, nil
end

-- The level the Champions and Boons join at: W's, else read from DEF A's text ("From +14: ...").
function P.ChampionsLevel(fromW)
    if fromW and fromW > 0 then
        return fromW
    end
    local d = ns.Def("A", P.CHAMPIONS)
    local n = d and d.text and tonumber(d.text:match("^From %+(%d+)"))
    return n
end

-- An affix's name and text. The ids are the server's (W, ERA, KEY); the built-in DEF A table of Data.lua numbers some
-- of them differently, so the server's own name decides, and a DEF A text is shown only when its name agrees (the
-- server's DEF A, sent by the bridge, always does).
function P.AffixInfo(id)
    local d = ns.Def("A", id)
    local name = P.AFFIX_NAMES[id] or (d and d.name) or ("Affix " .. id)
    local text = (d and d.name == name and d.text) or P.SPECIAL_TEXT[id]
    return name, text
end

-- The keystone run going on now (counting down or running, no result yet), or nil. StartRun has already lowered the
-- stored key ("depleted until the run is finished"), so while it runs the page shows the run's own level.
function P.RunningKey()
    local m = S.mplus
    if m and not m.result and (m.state or 0) <= 1 and (m.level or 0) > 0 then
        return m
    end
    return nil
end

function P:RefreshKey()
    local run = P.RunningKey()
    if run then
        local runName = ns.DefName("D", run.dungeonId, nil) or ns.DungeonName(run.dungeonId)
        P.keyIcon.icon:SetTexture(UI.IconPath("INV_Misc_Key_15"))
        P.keyText:SetText("|cffa335ee+" .. run.level .. "|r  " .. U.Safe(runName) .. "  -  run under way")
        P.keySub:SetText("Beat the timer: +1 to +3 and a new dungeon. Over time: +" .. max(1, run.level - 1) .. ".")
        return
    end
    local level, name, timer, known, depleted = P.Keystone()
    -- the keystone item's own icon when the client knows the item, else the old page's key
    local icon = GetItemIcon and GetItemIcon((S.key and S.key.itemId) or P.KEY_ITEM)
    if type(icon) ~= "string" or icon == UI.STOCK.question then
        icon = nil
    end
    if level then
        P.keyIcon.icon:SetTexture(icon or UI.IconPath("INV_Misc_Key_15"))
        P.keyText:SetText("|cffa335ee+" .. level .. "|r  " .. U.Safe(name)
            .. (depleted and "  |cff808080(depleted)|r" or ""))
        P.keySub:SetText((timer > 0 and ("Timer " .. U.Clock(timer) .. "  -  ") or "")
            .. "right-click the key inside the dungeon")
    else
        P.keyIcon.icon:SetTexture(UI.IconPath("INV_Misc_Key_15"))
        P.keyText:SetText("No keystone")
        if P.UnderKeyLevel() then
            -- the server keeps Mythic 0 Normal below its level (bh_mplus.cpp SetDifficulty, StartRun)
            P.keySub:SetText(P.LevelText())
        elseif known then
            P.keySub:SetText("Defeat the final boss of a Mythic 0 dungeon to get one.")
        else
            P.keySub:SetText((Comm.ready or Comm.outdated or L.seen) and "Asking the server..."
                or "Waiting for the server...")
        end
    end
end

function P:RefreshAffixes()
    local ids, champW = P.WeekAffixes()
    local champs = P.ChampionsLevel(champW)
    local shown = 0
    for i, a in ipairs(P.aff) do
        local id, lvl
        if i <= 4 then
            id, lvl = ids[i], P.AFFIX_LEVELS[i]
        elseif champs and #ids > 0 then
            id, lvl = (i == 5) and P.CHAMPIONS or P.BOONS, champs
        end
        if id and id > 0 then
            local name, text = P.AffixInfo(id)
            a:SetAffix(name, lvl, text)
            if P.SPECIAL_ICONS[id] then
                a:SetIcon(P.SPECIAL_ICONS[id])
            end
            a.affixId = id
            a:Show()
            shown = shown + 1
        else
            a.affixId = nil
            a:Hide()
        end
    end
    P.noAffixes:SetText(shown == 0 and (Comm.ready or L.seen) and "No affixes this week." or "")
end

function P:RefreshDungeons()
    local list = L.SeasonDungeons()
    local _, keyName = P.Keystone()
    for i, r in ipairs(P.rows) do
        local d = list[i]
        r.d = d
        if d then
            ns.Journal.Set(r.thumb, ns.Journal.Key(d.name), "btn", 64, 36)
            UI.SetText(r.name, d.name)
            if (d.best or 0) > 0 then
                r.best:SetText("+" .. d.best)
            else
                r.best:SetText("|cff606060-|r")
            end
            -- the keystone's dungeon is the chosen one of the grid
            UI.Select(r, keyName ~= nil and d.name == keyName)
            r:Show()
        else
            r:Hide()
        end
    end
end

-- Inside the keystone's own dungeon: the instance's name (GetInstanceInfo) is in the key dungeon's ("Scarlet
-- Monastery" in "Scarlet Monastery: Armory", "Blackrock Spire" in "Lower Blackrock Spire").
function P.InKeyDungeon(keyName)
    if not A.InDungeon() or type(keyName) ~= "string" then
        return false
    end
    local here = GetInstanceInfo and GetInstanceInfo()
    return type(here) == "string" and here ~= "" and keyName:find(here, 1, true) ~= nil
end

-- What keeps Start keystone from working, as the server checks KSTART, or nil: a keystone, the group leader (or no
-- group; mod-bleakhold-ui BleakholdMgr.cpp), no key countdown or run going (a Mythic 0 with no boss down may still
-- become the key run), Normal difficulty, 5 players inside at the key level (StartRun), and a start the keystone or
-- the Font of Power opened here (the server's O: TakePendingSocket wants it, in the key's own dungeon, within 5
-- minutes; Legacy.lua). The demo has no dungeon to be in: there the button starts its sample run from anywhere.
function P.StartBlock()
    if not (Comm.ready or Comm.demo) then
        return "Waiting for the server..."
    end
    local k = S.key
    if not (k and k.hasKey) then
        return "You have no keystone."
    end
    -- a keystone run counting down or running; a Mythic 0 (level 0, which the server starts on its own in a key
    -- dungeon) becomes the key run until its first boss dies (StartRun's fromMythic0)
    local m = S.mplus
    if m and not m.result and (m.state or 0) <= 1 then
        if (m.level or 0) > 0 then
            return (m.state or 0) == 0 and "Your keystone's countdown is running." or "A keystone run is under way."
        elseif (m.bossBits or 0) ~= 0 then
            return "A boss is already dead in this Mythic 0. Reset the dungeon to insert a keystone."
        end
    end
    if Comm.demo then
        return nil
    end
    local raid, party = GetNumRaidMembers and GetNumRaidMembers() or 0, GetNumPartyMembers and GetNumPartyMembers() or 0
    if (raid > 0 and not (IsRaidLeader and IsRaidLeader())) or (raid == 0 and party > 0
        and not (IsPartyLeader and IsPartyLeader())) then
        return "Only the group leader can start the keystone."
    end
    local _, name = P.Keystone()
    -- keys run on Normal only: in a Heroic instance the keystone opens nothing (KeyStartBlock, StartRun)
    if P.InKeyDungeon(name) and GetInstanceInfo and select(3, GetInstanceInfo()) == 2 then
        return "Keystones run on Normal difficulty: set Normal (Heroic Dungeons page) outside, then enter again."
    end
    local armed = L.SocketArmed()
    if not armed then
        if not P.InKeyDungeon(name) then
            return "Use your keystone inside " .. U.Safe(name or "its dungeon") .. "."
        end
    end
    -- 5 players inside (StartRun): the group the keystone saw inside when it opened the start (G), else its size
    local seen = armed and L.GroupInside()
    if (seen or (raid > 0 and raid or 1 + party)) < P.KEY_MIN_PLAYERS then
        local text = "A keystone needs " .. P.KEY_MIN_PLAYERS .. " players inside the dungeon"
        if seen then
            return text .. " - " .. seen .. (seen == 1 and " is" or " are") .. " here now."
        end
        return text .. "."
    end
    -- every player inside at the key level (StartRun; a full party is all inside)
    local minLevel = P.KeyMinLevel()
    for i = 1, party do
        local unit = "party" .. i
        local lvl = UnitLevel and UnitLevel(unit) or 0
        if lvl > 0 and lvl < minLevel then
            return U.Safe(UnitName and UnitName(unit) or "A party member") .. " is below level " .. minLevel .. "."
        end
    end
    if not armed then
        return "Right-click your keystone (or use the Font of Power), then press Start keystone."
    end
    return nil
end

-- What keeps the group leader's difficulty change from working (the bridge's KMODE, SetDifficulty): any instance (the
-- bridge refuses it on a dungeon, raid, battleground or arena map), a member who is not the leader.
function P.DifficultyBlock()
    if IsInInstance() then
        return "Leave the dungeon or battleground first."
    end
    if (GetNumPartyMembers and GetNumPartyMembers() or 0) > 0 and not (IsPartyLeader and IsPartyLeader()) then
        return "Only the group leader can change the dungeon difficulty."
    end
    return nil
end

-- What keeps Mythic in particular from working: the rest of DifficultyBlock, and a Dungeon Finder group.
function P.MythicBlock()
    local block = P.DifficultyBlock()
    if block then
        return block
    end
    if A.InDungeonFinderGroup() then
        return "Mythic difficulty is not for Dungeon Finder groups."
    end
    return nil
end

function P:RefreshStats()
    local k = S.key
    if k then
        if (k.weeklyBest or 0) > 0 then
            P.best:SetText("+" .. k.weeklyBest .. (k.weeklyBestDungeon and ("  " .. U.Safe(ns.DungeonName(k.weeklyBestDungeon))) or ""))
        else
            P.best:SetText("-")
        end
        P.caches:SetText(k.cachesReady .. " left" .. ((k.cachesBanked or 0) > 0 and (", " .. k.cachesBanked .. " carried over") or ""))
    end
    for _, v in ipairs({ P.best, P.caches }) do
        if k then
            v:Show()
            v.label:Show()
        else
            v:Hide()
            v.label:Hide()
        end
    end
    local w = S.week
    if w and w.coins then
        P.coins:SetText(U.Commas(w.coins) .. ((w.coinsCap or 0) > 0 and (" / " .. U.Commas(w.coinsCap)) or ""))
        P.coins:Show()
        P.coins.label:Show()
        P.coinsTip:Show()
    else
        P.coins:Hide()
        P.coins.label:Hide()
        P.coinsTip:Hide()
    end
end

function P:Refresh()
    P:RefreshStats()
    P:RefreshKey()
    P:RefreshAffixes()
    P:RefreshDungeons()
    -- the difficulty (old :348, without the concatenation-before-or slip: Legacy.DifficultyName)
    P.diff:SetText("Dungeon difficulty: " .. L.DifficultyName(L.Difficulty(), true))
    local commands = Comm.ready or L.CanCommand() or Comm.demo
    P.mythic:SetActive(commands and not P.MythicBlock() and true or false)
    P:RefreshStart()
end

-- Start keystone and, while a keystone holder cannot press it, why (the start opened by the keystone ends after 5
-- minutes: checked every second while the page is open).
function P:RefreshStart()
    local block = P.StartBlock()
    P.start:SetActive(block == nil)
    P.startHint:SetText((block and S.key and S.key.hasKey) and block or "")
end

function P:Tick()
    P:RefreshStart()
end

function P:OnOpen()
    L.Request()
    Comm.Get("KEY")
    Comm.Get("WEEK")
end

ns.On("MPLUS_START", function()
    if P:IsVisible() then
        P:Refresh()
    end
end)
