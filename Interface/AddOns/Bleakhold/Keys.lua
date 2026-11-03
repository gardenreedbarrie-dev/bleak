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
-- its own dungeon by the group leader (right-click it, or the Font of Power, then Start keystone within 5 minutes), on
-- Normal difficulty (Normal or Mythic mode, not Heroic), also in a Mythic 0 no boss died in yet, and its countdown
-- cannot be stopped; in time it goes up 1 to 3 levels (at most KEY maxLevel) and moves to another dungeon, over time it
-- drops a level (never under +1); only the group leader sets the difficulty, outside dungeons (SetDifficulty, the
-- bridge's KMODE). The Mythical Caches are an allowance, not caches to open: each finished run spends 1 to 3 of them
-- and puts the gear straight into the bags (Complete, RollGear).
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

-- The Mythical Caches are a reward allowance the runs spend on their own, not caches to open (bh_mplus.cpp Complete:
-- 1 to 3 for a key in time, 1 over time or for a Mythic 0, capped by what is left; bh_rift.cpp: 1 every Rift.CacheEvery
-- floors; RollGear puts the gear in the bags). KEY's cachesReady is the whole allowance, cachesBanked the part over
-- the weekly amount (the bridge's Caches: banked = bank - weeklyCap), so the weekly amount is ready - banked while
-- something is banked and less than all of it is; KEY sends neither the weekly amount nor the cap of the bank. With
-- all of it banked (a realm with WeeklyCacheCap 0; a KEY with more banked than left, as the demo's) there is no weekly
-- amount to show.
function P.CachesTooltip()
    local k = S.key or {}
    local ready, banked = max(0, k.cachesReady or 0), max(0, k.cachesBanked or 0)
    local lines = { "Mythical Caches", { "Cache rewards you have left. Each finished key uses 1 to 3 (by the time "
        .. "left; 1 over time or in a Mythic 0) and every 5th Eclipse Rift floor uses 1; the gear goes straight into "
        .. "your bags.", C.text, true } }
    if banked > 0 and banked < ready then
        lines[#lines + 1] = { (ready - banked) .. " more every week; unused ones carry over.", C.text, true }
        lines[#lines + 1] = { banked .. " of them carried over from earlier weeks.", C.dim, true }
    else
        lines[#lines + 1] = { "More come every week; unused ones carry over.", C.text, true }
        if banked > 0 and ready > 0 then
            lines[#lines + 1] = { "All of them carried over from earlier weeks.", C.dim, true }
        end
    end
    if ready == 0 then
        lines[#lines + 1] = { "None left: runs give no cache gear until more come at the weekly reset.", C.orange,
            true }
    end
    return lines
end
P.cachesTip = CreateFrame("Frame", nil, P)
P.cachesTip:SetPoint("TOPRIGHT", P.caches.label, "TOPRIGHT", 0, 0)
P.cachesTip:SetSize(170, 40)
P.cachesTip:EnableMouse(true)
P.cachesTip:SetScript("OnEnter", function(self)
    UI.ShowTooltip(self, P.CachesTooltip())
end)
P.cachesTip:SetScript("OnLeave", function()
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
-- wider than the title and two lines high: the run notes ("Run under way: in time +9 to +11 in a new dungeon, over
-- time +7 here.") are long; below the stat column there is room up to the art
P.keySub = UI.Para(P, 11, C.dim, 460)
P.keySub:SetPoint("TOPLEFT", P.keyText, "BOTTOMLEFT", 0, -4)
P.keySub:SetHeight(28)

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
        { "Normal or Mythic dungeon mode, not Heroic.", C.text, true },
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

-- The names of a list of the server's affix ids (MPS, KEY, ERA), as P.AffixInfo names them: the key tracker and the
-- countdown use it too, so all of them call id 4 Raging.
function P.AffixNames(ids)
    local out = {}
    for _, id in ipairs(ids or {}) do
        out[#out + 1] = (P.AffixInfo(id))
    end
    return out
end

-- A keystone run going on now (counting down or running, no result yet; a Mythic 0 is level 0, not one), or nil. It
-- can be someone else's: every member of the leader's run gets its MPS and MP.
function P.RunningKey()
    local m = S.mplus
    if m and not m.result and (m.state or 0) <= 1 and (m.level or 0) > 0 then
        return m
    end
    return nil
end

-- Whether the player leads their group, or has none: only then can a keystone they hold start (StartRun: "Only the
-- group leader can start a run"; KSTART too).
function P.LeadsGroup()
    local raid = GetNumRaidMembers and GetNumRaidMembers() or 0
    if raid > 0 then
        return (IsRaidLeader and IsRaidLeader()) and true or false
    end
    local party = GetNumPartyMembers and GetNumPartyMembers() or 0
    return party == 0 or ((IsPartyLeader and IsPartyLeader()) and true or false)
end

-- Whose the keystone run going on now is, from what the server sends, not from who leads now: the lead can pass in
-- the middle of a run (or AzerothCore hands it away from an offline leader), and Complete() still sets the new key for
-- run->owner, whoever leads by then. Every member gets the run's MPS and MP, only while inside its instance (the
-- bridge's SyncRun: MpAbandoned once out).
-- The KEY against the run (MPS):
--   the run's dungeon and level: inside, the bridge sends the owner the run's own key (BuildKey, for run->owner only)
--     and every member their own stored key, so this is the owner's: "own". A member whose own key happens to be the
--     same is told apart by the old K when it came (Legacy.lua): StartRun stored the owner's key a level lower (SetKey,
--     then SendKey), so the owner's K is under the run's level and a member's K is their key as it is: "other" (not at
--     +1, where max(1, level - 1) stays 1).
--   its dungeon one level lower: what an older server (before BuildKey sent the run's key) sends the owner, and what a
--     member may hold. Told apart by what the KEYs did at the run's start (P.NoteRunStart): fallen from the run's level
--     then, "own"; held from well before, "other". When the start was not seen (a /reload, a login in the middle of
--     the run) the group leader's counts as the run, as before (StartRun takes only the leader's keystone), and
--     anyone else's is "unsure": a member's own key, or an older server's owner who passed the lead.
--   any other dungeon or level: never the owner's, "other".
-- nil without a running key run or a keystone.
function P.RunOwnership()
    local m, k = P.RunningKey(), S.key
    if not (m and k and k.hasKey) then
        return nil
    end
    if m.dungeonId ~= k.dungeonId then
        return "other"
    end
    if k.level == m.level then
        -- (not the demo's K: a fixed sample that its sample run never lowers)
        local old = not Comm.demo and L.mplus.key
        if m.level > 1 and old and old.level == m.level and L.KeyDungeonId(old.name) == k.dungeonId then
            return "other"
        end
        return "own"
    end
    if k.level + 1 == m.level then
        local v = P.verdict
        if v and v.runId == m.runId then
            return v.who
        end
        return P.LeadsGroup() and "own" or "unsure"
    end
    return "other"
end

-- What the KEYs did at a run's start (its first MPS, with the countdown: a later MPS, after a /reload or on entering
-- again, has none), for a key of its dungeon one level under it: an older bridge sent the owner the key StartRun stored
-- a level lower as soon as the run started (before or just after the MPS), while a member's KEY does not change when
-- someone else's run starts. P.verdict = { runId, who = "own" | "other" } for that run.
P.START_WINDOW = 10
P.held = nil   -- the KEY now: dungeonId, level, since (GetTime), fellAt (when it fell one level in its dungeon)

function P.NoteKey()
    local k = S.key
    local d, l = (k and k.hasKey) and k.dungeonId or 0, (k and k.hasKey) and k.level or 0
    local h = P.held
    if h and h.dungeonId == d and h.level == l then
        return
    end
    local now = GetTime()
    P.held = { dungeonId = d, level = l, since = now,
        fellAt = (h and d > 0 and h.dungeonId == d and h.level == l + 1) and now or nil }
end

function P.NoteRunStart()
    local m, h = P.RunningKey(), P.held
    if not (m and h and (m.countdownMs or 0) > 0) or (P.verdict and P.verdict.runId == m.runId) then
        return
    end
    if h.dungeonId ~= m.dungeonId or h.level + 1 ~= m.level then
        return
    end
    local at = m.startedAt or GetTime()
    if h.fellAt and math.abs(h.fellAt - at) <= P.START_WINDOW then
        P.verdict = { runId = m.runId, who = "own" }
    elseif h.since < at - P.START_WINDOW then
        P.verdict = { runId = m.runId, who = "other" }
    end
end

ns.On("STATE", function(topic)
    if topic == "KEY" then
        P.NoteKey()
        P.NoteRunStart()
    end
end)

-- The player's own keystone run going on now (P.RunOwnership), or nil.
function P.OwnRun()
    if P.RunOwnership() == "own" then
        return P.RunningKey()
    end
    return nil
end

-- What the run can make of the key, as Complete() does: in time +1 to +3 (at most KEY maxLevel) in another dungeon,
-- over time one level lower here (never under +1).
function P.RunOutcome(level)
    local top = (S.key and S.key.maxLevel) or 15
    local lo, hi = min(top, level + 1), min(top, level + 3)
    return "Run under way: in time +" .. lo .. (hi > lo and (" to +" .. hi) or "") .. " in a new dungeon, over time +"
        .. max(1, level - 1) .. " here."
end
-- for a run that is surely not the player's (P.RunOwnership "other"); P.RUN_UNSURE when it may be theirs
P.OTHER_RUN = "In a keystone run that is not yours: your keystone does not change."
P.RUN_UNSURE = "A keystone run is under way."

function P:RefreshKey()
    local level, name, timer, known, depleted = P.Keystone()
    -- the keystone item's own icon when the client knows the item, else the old page's key
    local icon = GetItemIcon and GetItemIcon((S.key and S.key.itemId) or P.KEY_ITEM)
    if type(icon) ~= "string" or icon == UI.STOCK.question then
        icon = nil
    end
    if level then
        local run, who = P.RunningKey(), P.RunOwnership()
        local own = who == "own" and run or nil
        -- during the player's own run the run's level (an older server's stored key is one lower until it ends)
        level = own and own.level or level
        P.keyIcon.icon:SetTexture(icon or UI.IconPath("INV_Misc_Key_15"))
        P.keyText:SetText("|cffa335ee+" .. level .. "|r  " .. U.Safe(name)
            .. ((depleted and not own) and "  |cff808080(depleted)|r" or ""))
        if own then
            P.keySub:SetText(P.RunOutcome(own.level))
        elseif who == "other" then
            P.keySub:SetText(P.OTHER_RUN)
        elseif run then
            P.keySub:SetText(P.RUN_UNSURE)
        else
            P.keySub:SetText((timer > 0 and ("Timer " .. U.Clock(timer) .. "  -  ") or "")
                .. "right-click the key inside the dungeon")
        end
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
-- Monastery" in "Scarlet Monastery: Armory", "Blackrock Spire" in "Lower Blackrock Spire"), or the wing after its hub
-- is ("Shadow Labyrinth" for "Auchindoun: Shadow Labyrinth").
function P.InKeyDungeon(keyName)
    if not A.InDungeon() or type(keyName) ~= "string" then
        return false
    end
    local here = GetInstanceInfo and GetInstanceInfo()
    if type(here) ~= "string" or here == "" then
        return false
    end
    -- Map.dbc names some wings with their hub ("Auchindoun: Shadow Labyrinth", "Coilfang: The Steamvault"); the key
    -- dungeon's own name may be just the wing's
    local short = here:match(":%s*(.+)$")
    return keyName:find(here, 1, true) ~= nil
        or (short ~= nil and (keyName:find(short, 1, true) ~= nil or short:find(keyName, 1, true) ~= nil))
end

-- StartRun's and KeyStartBlock's refusal on a Heroic instance (bh_mplus.cpp, bh_mplus_scripts.cpp): Mythic mode is
-- Normal difficulty, Heroic is not.
P.NORMAL_ONLY = "Mythic 0 and keystones run on Normal difficulty. Set your dungeon difficulty to Normal, leave and "
    .. "enter again."
-- Theirs in a Dungeon Journey run's instance (bh_mplus_scripts.cpp KeyStartBlock, bh_mplus.cpp StartRun), checked
-- after the difficulty as they do.
P.JOURNEY_RUN = "A Dungeon Journey run is active in this instance."

-- The same rule before the group enters (the dungeon difficulty is Heroic, the player outside the key's dungeon).
function P.HeroicOutsideText(name)
    return "Set the dungeon difficulty to Normal or Mythic before you enter " .. U.Safe(name or "the dungeon")
        .. ": keystones do not run on Heroic."
end

-- The instance's difficulty (GetInstanceInfo's third value; for a 5-player dungeon 1 Normal, 2 Heroic).
function P.InstanceDifficulty()
    if not GetInstanceInfo then
        return 1
    end
    local _, _, difficulty = GetInstanceInfo()
    return tonumber(difficulty) or 1
end

-- MythicRunText's words for a finished run (bh_mplus_scripts.cpp): the right-click and StartRun refuse every start in
-- an instance that had one until it is reset.
function P.FinishedText(level, name)
    local what = (level or 0) > 0 and (U.Safe(name) .. " +" .. level) or ("Mythic 0: " .. U.Safe(name))
    return what .. " - finished. Reset the dungeon for another run."
end

-- The run S.mplus shows ended here (its MPE, P.endedRun) and no loading screen came since: the player is still in the
-- instance it ran in, which has to be left to be reset. After MPE the bridge sends nothing when the player leaves (a
-- finished run is not opened again), so the MPE's run id is kept until PLAYER_ENTERING_WORLD.
P.endedRun = nil
ns.On("MPLUS_END", function(res)
    P.endedRun = type(res) == "table" and res.runId or nil
    -- the server sends no new L when a run ends (only E, then KEY/WEEK): ask again so the season bests follow
    L.Request(true)
end)
ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    P.endedRun = nil
end)

-- A Mythic 0 or key run that finished in this instance, as the server's refusal says it, or nil: the old S and T
-- (Legacy.lua) of the instance entered again after the run (SendFullState: state 3 ST_DONE), else the run S.mplus
-- shows, ended since the last loading screen and run in the dungeon the player stands in (a stale S.mplus never blocks
-- a later run).
function P.FinishedBlock()
    local run = L.Run()
    if run and run.state == L.STATE.DONE and (run.mode == L.MODE.KEY or run.mode == L.MODE.MYTHIC0)
        and type(run.name) == "string" and run.name ~= "" and A.InDungeon() then
        return P.FinishedText(run.mode == L.MODE.KEY and run.level or 0, run.name)
    end
    local m = S.mplus
    if not (m and P.endedRun and m.runId == P.endedRun) then
        return nil
    end
    if not (m.result or m.state == 2 or m.state == 3) or (m.dungeonId or 0) == 0 then
        return nil
    end
    local name = ns.DefName("D", m.dungeonId, nil) or ns.DungeonName(m.dungeonId)
    if P.InKeyDungeon(name) then
        return P.FinishedText(m.level, name)
    end
    return nil
end

-- What a run going on here leaves of Start keystone, or nil (StartRun; MythicRunText for the right-click): a Mythic 0
-- (MPS level 0) still takes the keystone while it runs and no boss has died (StartRun's fromMythic0: the server's own
-- Mythic mode starts one on entry, StartAutoMythic); a Mythic 0 counting down (the Font of Power) or a key run does
-- not; a run finished here (P.FinishedBlock) does not either.
function P.RunBlock()
    -- the server refuses a keystone outside its own dungeon first (OnKeyStart, the keystone's OnUse): a finished run
    -- or a Mythic 0 here only blocks the key of this dungeon
    local _, keyName = P.Keystone()
    local here = Comm.demo or L.SocketArmed() or P.InKeyDungeon(keyName)
    local done = here and P.FinishedBlock()
    if done then
        return done
    end
    -- an Eclipse Rift floor here (bh_rift.cpp RiftSetupFloor: MODE_RIFT on this instance's run): KeyStartBlock
    -- refuses every run but a fresh Mythic 0, so the keystone and the Font of Power never open the start
    local run = L.Run()
    if here and not Comm.demo and ((run and run.mode == L.MODE.RIFT)
        or (ns.Rift and ns.Rift.RunFloor and ns.Rift.RunFloor())) then
        return "This instance already had a run. Leave, reset the dungeon and enter again."
    end
    local m = S.mplus
    if not m or m.result or (m.state or 0) > 1 then
        return nil
    end
    if (m.level or 0) == 0 and (m.dungeonId or 0) > 0 then
        if not here then
            return nil
        elseif (m.state or 0) == 0 then
            return "Mythic 0: " .. U.Safe(ns.DefName("D", m.dungeonId, nil) or ns.DungeonName(m.dungeonId))
                .. " - in progress."
        elseif (m.bossBits or 0) ~= 0 then
            return "A boss is already dead in this Mythic 0. Reset the dungeon to insert a keystone."
        end
        return nil
    end
    if (m.state or 0) == 0 then
        return P.OwnRun() and "Your keystone's countdown is running." or "A keystone countdown is running."
    end
    return "A keystone run is under way."
end

-- Who StartRun names before it counts the players (its ForPlayers check over the instance: below Mythic.MinLevel, in
-- combat), or nil: the player and the party members the keystone saw inside when it opened the start (G).
function P.MemberBlock()
    local g = L.mplus.group
    if not g then
        return nil
    end
    local inside = {}
    for _, m in ipairs(g) do
        if m.inside then
            inside[m.name] = true
        end
    end
    local need = P.KeyMinLevel()
    for _, unit in ipairs({ "player", "party1", "party2", "party3", "party4" }) do
        local name = UnitName(unit)
        if name and (unit == "player" or inside[name]) then
            local level = UnitLevel(unit) or 0
            if level > 0 and level < need then
                return U.Safe(name) .. " is below level " .. need .. "."
            elseif UnitAffectingCombat(unit) then
                return U.Safe(name) .. " is in combat."
            end
        end
    end
    return nil
end

-- What keeps Start keystone from working, as the server checks KSTART, or nil: a keystone, no countdown or run going
-- (a fresh Mythic 0 aside), the group leader (or no group; mod-bleakhold-ui BleakholdMgr.cpp), the key's own dungeon on
-- Normal difficulty, nobody under the level or in combat, and a start the keystone or the Font of Power opened here
-- (the server's O: PeekPendingSocket wants it, in the key's own dungeon, within 5 minutes; Legacy.lua).
-- The demo has no dungeon to be in: there the button starts its sample run from anywhere.
function P.StartBlock()
    if not (Comm.ready or Comm.demo) then
        return "Waiting for the server..."
    end
    local k = S.key
    if not (k and k.hasKey) then
        return "You have no keystone."
    end
    local busy = P.RunBlock()
    if busy then
        return busy
    end
    if Comm.demo then
        return nil
    end
    if not P.LeadsGroup() then
        return "Only the group leader can start the keystone."
    end
    local armed = L.SocketArmed()
    local _, name = P.Keystone()
    local inside = P.InKeyDungeon(name)
    if not armed and not inside then
        -- Heroic set (KEY mode 1) before the group goes in: said now, not once they stand in a Heroic instance
        -- (P.NORMAL_ONLY) and have to leave, change it and reset; only the leader (or a solo player) gets here
        if L.Difficulty() == 2 then
            return P.HeroicOutsideText(name)
        end
        return "Use your keystone inside " .. U.Safe(name or "its dungeon") .. "."
    end
    -- a Heroic instance: the right-click refuses it too, so the start never opens there
    if inside and P.InstanceDifficulty() == 2 then
        return P.NORMAL_ONLY
    end
    -- a Dungeon Journey run in this instance (the bridge's QUEUE state 3 kind D, BuildOwnQueue): the keystone's
    -- right-click, the Font of Power and StartRun all refuse it (P.JOURNEY_RUN)
    local q = S.queue
    if inside and q and q.state == 3 and q.kind == "D" then
        return P.JOURNEY_RUN
    end
    local member = armed and P.MemberBlock()
    if member then
        return member
    end
    -- the players inside are StartRun's to count (live, Bleakhold.MythicPlus.KeyMinPlayers, staff exempt): G is a
    -- snapshot from the right-click and the minimum is not sent, so no count greys the button; a refusal comes back
    -- as ERR (the Activities strip)
    if not armed then
        return "Right-click your keystone (or use the Font of Power), then press Start keystone."
    end
    return nil
end

-- What keeps the group leader's difficulty change from working (the bridge's KMODE, SetDifficulty): any instance (the
-- bridge refuses it on a dungeon, raid, battleground or arena map), a member who is not the leader (of a party or a
-- raid: Group::IsLeader).
function P.DifficultyBlock()
    if IsInInstance() then
        return "Leave the dungeon or battleground first."
    end
    if not P.LeadsGroup() then
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
            P.best:SetText("+" .. k.weeklyBest
                .. (k.weeklyBestDungeon and ("  " .. U.Safe(ns.DungeonName(k.weeklyBestDungeon))) or ""))
        else
            P.best:SetText("-")
        end
        -- an allowance the runs spend (P.CachesTooltip), not caches to open
        P.caches:SetText(k.cachesReady .. " left"
            .. ((k.cachesBanked or 0) > 0 and (", " .. k.cachesBanked .. " carried over") or ""))
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
    if k then
        P.cachesTip:Show()
    else
        P.cachesTip:Hide()
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
    P.NoteRunStart()
    if P:IsVisible() then
        P:Refresh()
    end
end)
