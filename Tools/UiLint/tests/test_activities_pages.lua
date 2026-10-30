-- The five old pages of Activities, rebuilt in the old window's look (old BleakholdActivities.lua :195-441):
-- Dungeons.lua (Dungeon Journey), Keys.lua (Mythic+ Dungeons), Rift.lua (Eclipse Rift), Heroic.lua and GroupFinder.lua.
-- Each page's content comes from the server's BHMP messages built the way mod-bleakhold builds them (Legacy.lua) and
-- from our protocol for the extras; its actions are the old chat commands or our intents; every rule a page states is
-- the server's (bh_activities.cpp, bh_dungeon.cpp, bh_mplus.cpp, bh_rift.cpp, bh_ui_bridge.cpp).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local JOURNAL = "Interface\\AddOns\\Bleakhold\\Art\\Journal\\"

local function feed(ns, list)
    for _, msg in ipairs(list) do
        ns.Legacy.Receive(msg)
    end
end

local function lastSay(M)
    for i = #M.said, 1, -1 do
        if M.said[i].chatType == "SAY" then return M.said[i].msg end
    end
end

local function says(M)
    local n = 0
    for _, s in ipairs(M.said) do
        if s.chatType == "SAY" then n = n + 1 end
    end
    return n
end

local function tipText(lines)
    local out = {}
    for _, l in ipairs(lines) do
        out[#out + 1] = type(l) == "table" and l[1] or l
    end
    return table.concat(out, "\n")
end

-- The board of bh_activities.cpp SendJourney: an open offer, one per lock reason (level, chapter, tier), one more open.
local BOARD = {
    "H;3600;0;0;0;1",
    "J;1001;36;0;0;1;15;0;82;845;3;120;The Deadmines;",
    "J;1002;33;1;2;1;18;0;0;0;0;160;Shadowfang Keep;Bolstering",
    "J;1003;189;2;5;2;30;1;0;0;0;240;Scarlet Monastery;Bolstering, Sanguine",
    "J;1004;209;0;0;3;42;2;0;0;0;300;Zul'Farrak;",
    "J;1005;33;2;0;1;18;3;0;0;0;200;Shadowfang Keep;",
}

------------------------------------------------------------------------------------------------------
-- Dungeon Journey
------------------------------------------------------------------------------------------------------
test("journey: the old board from H and J: thumbnails, tier, chapter, modifiers, Shards, best, locks", function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 20
    feed(ns, BOARD)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local P = ns.Dungeons
    H.eq(P.title:GetText(), "Dungeon Journey")
    H.contains(P.desc:GetText(), "Level through dungeons instead of quests")
    H.eq(P.boardTitle:GetText(), "Today's Board")
    -- rows in the server's order
    local r1, r2, r3 = P.rows[1], P.rows[2], P.rows[3]
    H.eq(r1.name:GetText(), "The Deadmines")
    H.eq(r1.thumb.__texture, JOURNAL .. "btn_DEADMINES", "the Journal thumbnail")
    local _, _, _, _, urx, ury = r1.thumb:GetTexCoord()
    H.eq(urx, 0.6796875, "the old btn crop (old :39)")
    H.eq(r1.reward:GetText(), "120 Shards")
    H.eq(r1.best:GetText(), "best 82%")
    H.contains(r1.line:GetText(), "Normal|r  Chapter 1")
    H.contains(r2.line:GetText(), "|cff1FFF00Veteran|r", "the tier in its colour (old :17)")
    H.contains(r2.line:GetText(), "|cffff8040+Bolstering|r", "the modifiers")
    H.eq(r2.best:GetText(), "", "no best yet")
    -- locked rows: the lock, the picture greyed, the name grey
    H.ok(not r1.lock:IsShown() and not r1.thumb.__desat, "an open run")
    H.ok(r3.lock:IsShown() and r3.thumb.__desat, "a locked run: the lock and a grey picture")
    H.eq(r3.lock.__texture, "Interface\\LFGFrame\\UI-LFG-ICON-LOCK")
    -- the reasons, in the server's words (OfferStatus 1/2/3, CanLaunch)
    H.contains(tipText(P.OfferTooltip(ns.Legacy.journey.byKey[1003])), "You need level 30.")
    H.contains(tipText(P.OfferTooltip(ns.Legacy.journey.byKey[1004])), "Clear a Chapter 2 dungeon on Normal first.")
    H.contains(tipText(P.OfferTooltip(ns.Legacy.journey.byKey[1005])), "Score 70% on Veteran Shadowfang Keep first.")
    local tip = tipText(P.OfferTooltip(ns.Legacy.journey.byKey[1001]))
    H.contains(tip, "Normal  -  Chapter 1  -  level 15+")
    H.contains(tip, "Reward: up to 120 Shards, +20% with 4 or 5 players")
    H.contains(tip, "Your best: 82% in 14:05 (3 runs)")
    H.ok(not tip:find("need level", 1, true), "no lock reason on an open run")
    -- the row's tooltip on the cursor
    M.Hover(r2)
    H.eq(M.env.GameTooltip.__lines[1], "Shadowfang Keep")
    M.Hover(r2, false)
    -- the stat column (old :198-200)
    H.eq(P.rot:GetText(), "1:00:00", "the board's rotation clock")
    M.Advance(2.1)
    H.ok(P.rot:GetText():match("^59:5%d$"), "it counts down: " .. P.rot:GetText())
    H.contains(P.bonus:GetText(), "double Shards", "the first run of the day is still to come")
    H.eq(P.queueStat:GetText(), "-")
    feed(ns, { "H;3000;0;0;1;1" })
    P:Refresh()
    H.contains(P.bonus:GetText(), "used")
end)

test("journey: the first open run is chosen; Find Group and Enter Dungeon say the old commands", function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 20
    feed(ns, BOARD)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local P = ns.Dungeons
    H.eq(P.selected, 1001, "the board's first open run (old :482)")
    H.ok(P.rows[1].selected and not P.rows[2].selected, "lit as the old window's chosen row")
    H.eq(ns.Activities.artKey, "DEADMINES", "the page art is the chosen run's dungeon")
    H.ok(P.find:IsEnabled() and P.enter:IsEnabled())
    H.contains(P.hint:GetText(), "Enter now alone")
    P.find:Click()
    H.eq(lastSay(M), ".act start 1001 queue")
    P.enter:Click()
    H.eq(lastSay(M), ".act start 1001 solo")
    -- another run: chosen, its art
    P.rows[2]:Click()
    H.eq(P.selected, 1002)
    H.eq(ns.Activities.artKey, "SHADOWFANGKEEP")
    P.enter:Click()
    H.eq(lastSay(M), ".act start 1002 solo")
    -- a locked run: chosen, but nothing to start
    local before = says(M)
    P.rows[3]:Click()
    H.ok(not P.find:IsEnabled() and not P.enter:IsEnabled(), "locked: no start")
    H.contains(P.hint:GetText(), "Locked:")
    P.find:Click()
    P.enter:Click()
    H.eq(says(M), before, "nothing said")
    -- the board rotates: the chosen run is gone, the first open one of the new board is chosen
    feed(ns, { "H;10800;0;0;0;1", "J;2001;43;0;0;1;16;0;0;0;0;110;Wailing Caverns;" })
    P:Refresh()
    H.eq(P.selected, 2001)
    H.ok(not P.rows[2]:IsShown(), "the old rows go")
end)

test("journey: party rules, a closed Journey, no server", function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 20
    feed(ns, BOARD)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local P = ns.Dungeons
    M.SetGroup("PARTY", 3, false)
    P:Refresh()
    H.ok(not P.find:IsEnabled() and not P.enter:IsEnabled(), "a member who is not the leader")
    H.eq(P.hint:GetText(), "Only your party leader can start or queue a run.")
    M.SetGroup("PARTY", 3, true)
    P:Refresh()
    H.ok(P.enter:IsEnabled(), "the leader")
    H.contains(P.hint:GetText(), "with your party")
    M.SetGroup("RAID", 10, true)
    P:Refresh()
    H.ok(not P.enter:IsEnabled())
    H.eq(P.hint:GetText(), "Raid groups can't start a dungeon run.")
    M.SetGroup("NONE", 1, false)
    -- the server's disabled board (bh_activities.cpp: H;0;0;0;0;0)
    feed(ns, { "H;0;0;0;0;0" })
    P:Refresh()
    H.eq(P.hint:GetText(), "The Dungeon Journey is closed right now.")
    H.ok(not P.find:IsEnabled() and not P.enter:IsEnabled())
    H.ok(not P.rows[1]:IsShown(), "no board")
    H.eq(P.rot:GetText(), "-")
    H.eq(P.empty:GetText(), "The Dungeon Journey is closed right now.", "the empty board says so too")
    -- open, but no offers (no dungeon enabled): not 'Loading...' for good
    feed(ns, { "H;3600;0;0;0;1" })
    P:Refresh()
    H.contains(P.empty:GetText(), "No runs on the board right now - it changes in ")
    H.contains(P.hint:GetText(), "No runs on the board right now")
end)

test("journey: no start inside an instance or in the Dungeon Finder's queue, as the server refuses", function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 20
    feed(ns, BOARD)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local P = ns.Dungeons
    H.ok(P.enter:IsEnabled())
    -- inside a run, a raid, a battleground (bh_activities.cpp: "Leave the dungeon or battleground first.")
    for _, kind in ipairs({ "party", "raid", "pvp", "arena" }) do
        M.inInstance, M.instanceType = true, kind
        P:Refresh()
        H.ok(not P.find:IsEnabled() and not P.enter:IsEnabled(), kind)
        H.eq(P.hint:GetText(), "Leave the dungeon or battleground first.")
    end
    M.inInstance, M.instanceType = nil, nil
    -- queued in the game's Dungeon Finder (bh_dungeon.cpp CanLaunch: LFG_STATE_QUEUED, ROLECHECK, PROPOSAL)
    M.env.GetLFGInfoServer = function() return false, true, true end
    P:Refresh()
    H.ok(not P.enter:IsEnabled(), "queued")
    H.eq(P.hint:GetText(), "Leave the Dungeon Finder queue first.")
    M.env.GetLFGInfoServer = function() return false, false, false end
    M.env.GetLFGProposal = function() return true end
    P:Refresh()
    H.eq(P.hint:GetText(), "Leave the Dungeon Finder queue first.", "a proposal")
    M.env.GetLFGProposal = function() return false end
    M.env.GetLFGRoleUpdate = function() return true end
    P:Refresh()
    H.eq(P.hint:GetText(), "Leave the Dungeon Finder queue first.", "a role check")
    M.env.GetLFGRoleUpdate = function() return false end
    P:Refresh()
    H.ok(P.enter:IsEnabled(), "free again")
end)

-- The board's dungeons from our BOARD: a locked one, one with Normal and Veteran, one with Normal only. Scores are
-- the Journey's percentages (bh_dungeon.cpp caps a score at 100), the record of the best's tier.
local CUSTOM_BOARD = {
    { 1, 1260, 0, 0, 0, "", 1 },
    { 36, 1, 15, 21, 1, 72, 0, 95, "Brenna", 0 },
    { 33, 1, 18, 25, 3, 64, 1, 88, "Dalia", 0 },
    { 209, 3, 42, 48, 1, "", "", "", "", 1 },
}

test("journey: a custom run of any unlocked dungeon at a chosen tier is QJOIN D, the size the party's", function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 23
    feed(ns, BOARD)
    H.send(M, "BOARD", CUSTOM_BOARD)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local P = ns.Dungeons
    local cr = P.customBox
    H.ok(cr:IsShown(), "the custom run under the stat column")
    local ids = {}
    for _, it in ipairs(cr.dungeon.items) do ids[#ids + 1] = it.value end
    H.eq(table.concat(ids, ","), "36,33", "unlocked dungeons only")
    H.eq(P.custom.dungeon, 33, "the first of the player's level band (18-25 at 23)")
    -- the rows' tooltips: chapter, level, best, server record
    local tip = tipText(cr.dungeon.items[2].tip)
    H.contains(tip, "level 18-25")
    H.contains(tip, "Your best: 64% (Veteran)")
    H.contains(tip, "Server record: 88% (Veteran) - Dalia")
    local tiers = {}
    for _, it in ipairs(cr.tier.items) do tiers[#tiers + 1] = it.text end
    H.eq(table.concat(tiers, ","), "Normal,Veteran", "the tiers unlocked there")
    H.eq(P.custom.tier, 1, "Normal to start with")
    cr.tier:SetValue(2)
    H.eq(P.custom.tier, 2)
    H.eq(cr.tier.label:GetText(), "Veteran")
    cr.enter:Click()
    H.eq(H.lastIntent(M, "QJOIN").payload, "D,33,1,4,1", "the dungeon, Veteran (tier 1), damage, alone")
    cr.find:Click()
    H.eq(H.lastIntent(M, "QJOIN").payload, "D,33,1,4,5", "find a group of five")
    -- another dungeon: its tiers; the player's Dungeon Finder roles go along
    cr.dungeon:SetValue(36)
    H.eq(P.custom.tier, 1, "Veteran is not unlocked there")
    M.env.GetLFGRoles = function() return false, true, true, false end
    M.SetGroup("PARTY", 3, true)
    P:Refresh()
    cr.enter:Click()
    H.eq(H.lastIntent(M, "QJOIN").payload, "D,36,0,3,3", "Normal, tank and healer, the party of 3")
    -- the same rules as the board's buttons
    M.SetGroup("PARTY", 3, false)
    P:Refresh()
    H.ok(not cr.enter:IsEnabled() and not cr.find:IsEnabled(), "not the leader")
    M.SetGroup("PARTY", 5, true)
    P:Refresh()
    H.ok(cr.enter:IsEnabled() and not cr.find:IsEnabled(), "a full party has no one to find")
    M.SetGroup("NONE", 1, false)
    M.inInstance, M.instanceType = true, "party"
    P:Refresh()
    H.ok(not cr.enter:IsEnabled(), "inside an instance")
    M.inInstance, M.instanceType = nil, nil
    -- queued: below the queue panel, and no second queue
    H.send(M, "QUEUE", { { 2, 1, "D", 33, 1, 5, 30, 90, "", "", 18, 25 } })
    M.Advance(0.3)
    H.ok(P.queue:IsShown())
    local _, rel = cr:GetPoint(1)
    H.eq(rel, P.queue, "under the queue panel")
    H.ok(not cr.enter:IsEnabled(), "already queued")
end)

test("journey: no custom run without our protocol's BOARD (the old commands have none)", function(M, ns)
    M.playerLevel = 20
    feed(ns, BOARD)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    H.ok(not ns.Dungeons.customBox:IsShown())
end)

test("journey: nothing from the server yet: waiting, and no command is said", function(M, ns)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local P = ns.Dungeons
    H.eq(P.hint:GetText(), "Waiting for the server...")
    H.ok(P.empty:IsShown())
    H.ok(not P.find:IsEnabled(), "no board, no start")
    H.eq(says(M), 0, "no '.' line on a server that is not Bleakhold")
    H.ok(not P.shards:IsShown() and not P.shards.label:IsShown(), "no Shards before the server says")
end)

test("journey: the queue panel from QUEUE and the old H; Leave queue is QLEAVE", function(M, ns)
    M.playerLevel = 34
    feed(ns, BOARD)
    feed(ns, { "H;3600;1002;3;0;1" })
    for _, msg in ipairs(BOARD) do
        if msg:sub(1, 2) == "J;" then ns.Legacy.Receive(msg) end
    end
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local P = ns.Dungeons
    local q = P.queue
    -- the old H alone: queued, 3 players (no QUEUE yet)
    H.contains(P.queueStat:GetText(), "queued")
    H.contains(P.queueStat:GetText(), "(3)")
    H.ok(q:IsShown(), "the panel")
    H.eq(q.status:GetText(), "In queue: Veteran Shadowfang Keep")
    H.ok(not q.leave:IsShown(), "no protocol: nothing to leave with (the old commands have no leave)")
    FX.connect(M, H)
    -- our QUEUE (the bridge's QueueOfLobby): the start countdown, the level band
    H.send(M, "QUEUE", { { 5, 1, "D", 33, 1, 5, 20, 100, "", "", 29, 39 } })
    M.Advance(0.3)
    H.eq(q.status:GetText(), "In queue: Veteran Shadowfang Keep")
    H.contains(q.timer:GetText(), "Starts in 01:40")
    H.contains(q.timer:GetText(), "or at 5 players", "a Journey queue starts at 5 players or its timer")
    H.eq(q.band:GetText(), "Levels 29-39  -  3 of 5 players")
    M.Advance(2.2)
    H.contains(q.timer:GetText(), "Starts in 01:3", "it counts down")
    H.ok(q.leave:IsVisible())
    q.leave:Click()
    H.ok(H.lastIntent(M, "QLEAVE"), "Leave queue")
    -- in the run: no leave (the dungeon's own Leave dungeon does it)
    H.send(M, "QUEUE", { { 6, 3, "D", 33, 1, 3 } })
    feed(ns, { "H;3600;0;0;0;1" })
    M.Advance(0.3)
    H.eq(q.status:GetText(), "In a run: Veteran Shadowfang Keep")
    H.eq(P.queueStat:GetText(), "in a run")
    H.ok(not q.leave:IsShown())
    -- Bleakhold Royale's queue shows here too
    H.send(M, "QUEUE", { { 7, 1, "B", 901, 0, 1, 12, "", "", "", 80, 80, 13, 20, 40, "", "", 1 } })
    M.Advance(0.3)
    H.eq(q.status:GetText(), "In queue: Bleakhold Royale")
    -- nothing queued: the panel goes
    H.send(M, "QUEUE", { { 8, 0 } })
    M.Advance(0.3)
    H.ok(not q:IsShown())
    H.eq(P.queueStat:GetText(), "-")
end)

test("journey: Shards from our protocol, a long board scrolls by rows", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    M.playerLevel = 80
    local msgs = { "H;3600;0;0;0;1" }
    for i = 1, 10 do
        msgs[#msgs + 1] = "J;" .. (3000 + i) .. ";36;0;0;1;15;0;0;0;0;100;The Deadmines;"
    end
    feed(ns, msgs)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local P = ns.Dungeons
    H.eq(P.shards:GetText(), "1,260", "the Shards balance (BOARD)")
    H.ok(P.shards.label:IsShown())
    H.eq(P.more:GetText(), "scroll for 3 more", "old :273")
    P.scroll:GetScript("OnMouseWheel")(P.scroll, -1)
    H.eq(P.more:GetText(), "scroll for 2 more", "one row a notch")
    H.ok(P.scroll.bar:IsShown(), "the stock scroll bar")
end)

------------------------------------------------------------------------------------------------------
-- Mythic+ Dungeons
------------------------------------------------------------------------------------------------------
local MPLUS = {
    "K;602;8;1800;Halls of Lightning",
    "W;12;1,3,10,8;14;1.096000;1.075000",
    "L;289;1800;12;Scholomance",
    "L;575;1800;0;Utgarde Pinnacle",
    "L;602;1800;11;Halls of Lightning",
    "Z;0",
}

test("mythic+: the keystone, the week's affixes from +2 to the Champions, the season grid, the difficulty",
    function(M, ns)
    feed(ns, MPLUS)
    ns.UI.Open("keys")
    M.Advance(0.3)
    local P = ns.Keys
    H.eq(P.title:GetText(), "Mythic+ Dungeons")
    H.contains(P.desc:GetText(), "Finish a Mythic 0 dungeon for your first keystone")
    H.eq(P.keyText:GetText(), "|cffa335ee+8|r  Halls of Lightning", "old :317")
    H.eq(P.keySub:GetText(), "Timer 30:00  -  right-click the key inside the dungeon")
    -- the four weekly affixes at +2, +4, +7, +10 (bh_mplus.cpp minLvl), then Champions and Boons at W's level
    local want = { { 1, "+2" }, { 3, "+4" }, { 10, "+7" }, { 8, "+10" }, { 13, "+14" }, { 14, "+14" } }
    for i, w in ipairs(want) do
        local a = P.aff[i]
        H.ok(a:IsShown(), "affix " .. i)
        H.eq(a.affixId, w[1])
        H.eq(a.level:GetText(), w[2])
    end
    H.eq(P.aff[1].icon.__texture, "Interface\\Icons\\Ability_Warrior_ShieldWall", "Fortified's icon (old :19)")
    H.eq(P.aff[5].icon.__texture, "Interface\\Icons\\Spell_Holy_SummonChampion")
    H.eq(P.aff[6].icon.__texture, "Interface\\Icons\\Spell_Holy_DivineIntervention")
    H.eq(P.aff[1].tipLines[1], "Fortified")
    H.eq(P.aff[5].tipLines[1], "Mythic Champions")
    -- the season's dungeons with their best keystone
    H.eq(P.rows[1].name:GetText(), "Scholomance")
    H.eq(P.rows[1].best:GetText(), "+12")
    H.eq(P.rows[2].best:GetText(), "|cff606060-|r", "none timed")
    H.eq(P.rows[1].thumb.__texture, JOURNAL .. "btn_SCHOLOMANCE")
    H.ok(P.rows[3].selected and not P.rows[1].selected, "the keystone's dungeon lit")
    H.ok(not P.rows[4]:IsShown())
    H.contains(tipText(P.DungeonTooltip(ns.Legacy.mplus.byId[289])), "Your best keystone: +12")
    -- the difficulty: Z 0 is Normal (old :348 raised an error here)
    H.eq(P.diff:GetText(), "Dungeon difficulty: Normal")
    feed(ns, { "Z;3" })
    P:Refresh()
    H.eq(P.diff:GetText(), "Dungeon difficulty: |cffA335EEMythic|r")
    -- Set difficulty: Mythic without our protocol is the old command (a BHMP message proved the server)
    P.mythic:Click()
    H.eq(lastSay(M), ".mplus difficulty mythic")
    -- the ladder (DEF M) on the keystone
    H.contains(tipText(P.LadderTooltip()), "Mythic 0:")
end)

test("mythic+: our KEY: no keystone, depleted, the week's best, caches, coins; Heroic from KEY.mode", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    feed(ns, MPLUS)
    ns.UI.Open("keys")
    M.Advance(0.3)
    local P = ns.Keys
    H.eq(P.best:GetText(), "+9  Halls of Stone", "the week's best key")
    H.eq(P.caches:GetText(), "1 left, 2 carried over", "the Mythical Caches (KEY)")
    H.eq(P.coins:GetText(), "2,140 / 5,500", "the week's Mythic Coins and cap (WEEK)")
    H.contains(P.diff:GetText(), "Mythic", "KEY.mode 2")
    P.mythic:Click()
    H.eq(H.lastIntent(M, "KMODE").payload, "2", "our KMODE while the protocol is up")
    -- KEY.mode 1: Heroic, though Z is only ever 0 or 3
    H.send(M, "KEY", { { 2, 602, 8, { 1, 3, 4 }, 1, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    H.eq(P.diff:GetText(), "Dungeon difficulty: |cff40C0FFHeroic|r")
    -- depleted
    H.send(M, "KEY", { { 3, 602, 7, { 1, 3, 4 }, 0, 9, 599, 1, 2, 900001, 15, 7, 1 } })
    M.Advance(0.3)
    H.contains(P.keyText:GetText(), "+7|r  Halls of Lightning")
    H.contains(P.keyText:GetText(), "(depleted)")
    -- no keystone
    H.send(M, "KEY", { { 4, 0, 0, "", 0, 0, "", 40, 0, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    H.eq(P.keyText:GetText(), "No keystone")
    H.eq(P.keySub:GetText(), "Defeat the final boss of a Mythic 0 dungeon to get one.")
    H.eq(P.caches:GetText(), "40 left")
    H.eq(P.best:GetText(), "-")
    H.ok(not P.start:IsEnabled(), "no keystone, no start")
end)

-- bh_mplus.cpp OpenSocket: the keystone (or the Font of Power) opened the start of a +8 Halls of Lightning
local SOCKET = "O;602;8;1800;10;8;8;1,3,4;Halls of Lightning"

test("mythic+: Start keystone as the server takes it (its dungeon, the keystone used, the leader); difficulty rules",
    function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("keys")
    M.Advance(0.3)
    local P = ns.Keys
    H.ok(not P.start:IsEnabled(), "outside a dungeon")
    H.eq(P.startHint:GetText(), "Use your keystone inside Halls of Lightning.", "why, under the grid")
    H.contains(tipText(P.start.tooltip()), "right-click the keystone")
    H.contains(tipText(P.start.tooltip()), "cannot be stopped")
    -- another dungeon (a Journey run, a raid, a Rift floor): the server says "Use your keystone inside ..."
    M.inInstance, M.instanceType, M.zone = true, "party", "The Deadmines"
    P:Refresh()
    H.ok(not P.start:IsEnabled(), "inside another dungeon")
    H.eq(P.startHint:GetText(), "Use your keystone inside Halls of Lightning.")
    -- its own dungeon, alone: a keystone is a 5-player run (StartRun, KeyMinPlayers)
    M.zone = "Halls of Lightning"
    P:Refresh()
    H.ok(not P.start:IsEnabled(), "alone")
    H.eq(P.startHint:GetText(), "A keystone needs 5 players inside the dungeon.")
    H.contains(tipText(P.start.tooltip()), "needs 5 players inside")
    H.contains(P.desc:GetText(), "with a group of 5")
    -- a group of 5, the keystone not used yet
    M.SetGroup("PARTY", 5, true)
    P:Refresh()
    H.ok(not P.start:IsEnabled(), "the keystone has not opened the start")
    H.contains(P.startHint:GetText(), "Right-click your keystone")
    -- right-clicked with only 3 of them inside: OpenSocket's G says so
    feed(ns, { "G;Me:1:1:1:1|Ann:2:1:0:1|Bo:5:1:0:1|Cy:8:0:0:1|Di:4:0:0:1", SOCKET })
    P:Refresh()
    H.ok(not P.start:IsEnabled(), "3 inside")
    H.eq(P.startHint:GetText(), "A keystone needs 5 players inside the dungeon - 3 are here now.")
    -- right-clicked with all 5 inside: the server's G and O
    feed(ns, { "G;Me:1:1:1:1|Ann:2:1:0:1|Bo:5:1:0:1|Cy:8:1:0:1|Di:4:1:0:1", SOCKET })
    P:Refresh()
    H.ok(P.start:IsEnabled(), "inside, the keystone used")
    H.eq(P.startHint:GetText(), "")
    H.ok(not P.mythic:IsEnabled(), "the difficulty is set outside dungeons")
    H.contains(ns.Keys.DifficultyBlock(), "Leave the dungeon or battleground first.")
    -- a party member who is not the leader: mod-bleakhold-ui refuses (not_leader)
    M.SetGroup("PARTY", 5, false)
    P:Refresh()
    H.ok(not P.start:IsEnabled(), "not the leader")
    H.eq(P.startHint:GetText(), "Only the group leader can start the keystone.")
    M.SetGroup("PARTY", 5, true)
    P:Refresh()
    H.ok(P.start:IsEnabled(), "the leader")
    P.start:Click()
    H.ok(H.lastIntent(M, "KSTART"), "KSTART")
    H.send(M, "MPS", FX.examples(M).MPS)
    M.Advance(0.3)
    H.ok(not P.start:IsEnabled(), "the countdown runs")
    H.ok(not ns.Legacy.SocketArmed(), "the start is used up")
    -- the keystone's start lasts 5 minutes in that instance, and ends with X (out of the dungeon)
    feed(ns, { SOCKET })
    H.ok(ns.Legacy.SocketArmed())
    M.Advance(ns.Legacy.SOCKET_SECONDS + 1)
    H.ok(not ns.Legacy.SocketArmed(), "after 5 minutes")
    feed(ns, { SOCKET, "X" })
    H.ok(not ns.Legacy.SocketArmed(), "out of the dungeon")
    M.SetGroup("NONE", 1, false)
    -- the leader sets the difficulty
    M.inInstance, M.instanceType = nil, nil
    M.SetGroup("PARTY", 4, false)
    P:Refresh()
    H.ok(not P.mythic:IsEnabled())
    H.eq(ns.Keys.DifficultyBlock(), "Only the group leader can change the dungeon difficulty.")
    M.SetGroup("PARTY", 4, true)
    P:Refresh()
    H.ok(P.mythic:IsEnabled())
end)

test("mythic+: under the key level the page says so; the coins stat is this week's earnings", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    -- the bridge's DEF D: a key dungeon's lvlMin is Mythic.MinLevel (bh_ui_bridge_map.cpp)
    H.send(M, "DEF", { { "D", 8 }, { 602, "Halls of Lightning", 5, 80, 80, { "Loken" }, 1800 } })
    H.send(M, "KEY", { { 2, 0 } })
    M.playerLevel = 30
    ns.UI.Open("keys")
    M.Advance(0.3)
    local P = ns.Keys
    H.eq(P.KeyMinLevel(), 80)
    H.eq(P.keyText:GetText(), "No keystone")
    H.eq(P.keySub:GetText(), "Mythic+ opens at level 80.", "not 'defeat the final boss' at level 30")
    H.contains(tipText(P.mythic.tooltip()), "Mythic+ opens at level 80.")
    M.playerLevel = 80
    P:Refresh()
    H.eq(P.keySub:GetText(), "Defeat the final boss of a Mythic 0 dungeon to get one.")
    H.ok(not tipText(P.mythic.tooltip()):find("opens at level", 1, true), "no level line at 80")
    -- WEEK's coins: earned this week toward the cap, not the coins in the bags
    H.eq(P.coins.label:GetText(), "Mythic Coins This Week")
    H.ok(P.coins:IsShown() and P.coinsTip:IsShown())
    H.contains(tipText(P.COINS_TIP), "toward the weekly cap")
end)

test("mythic+: no BHMP yet: the season list from DEF D, the affixes from ERA", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("keys")
    M.Advance(0.3)
    local P = ns.Keys
    H.eq(P.keyText:GetText(), "|cffa335ee+8|r  Halls of Lightning", "our KEY")
    H.eq(P.aff[1].affixId, 1, "ERA's affixes")
    H.ok(not P.aff[5]:IsShown(), "no Champions level known: no Champions icon")
    local names = {}
    for _, r in ipairs(P.rows) do
        if r:IsShown() then names[r.name:GetText()] = true end
    end
    H.ok(names["Halls of Lightning"] and names["Utgarde Pinnacle"], "the key dungeons of DEF D")
end)

------------------------------------------------------------------------------------------------------
-- Eclipse Rift
------------------------------------------------------------------------------------------------------
test("rift: bests by group size, checkpoint, rewards, start floors after each checkpoint, .rift enter", function(M, ns)
    FX.connect(M, H)
    feed(ns, { "U;24;18;12;9;20;80;1;0;50" })
    ns.UI.Open("rift")
    M.Advance(0.3)
    local P = ns.Rift
    H.eq(P.title:GetText(), "The Eclipse Rift")
    H.contains(P.desc:GetText(), "Every 5th floor is a checkpoint")
    H.eq(P.bests[1].label:GetText(), "Best Solo")
    H.eq(P.bests[1]:GetText(), "24")
    H.eq(P.bests[4]:GetText(), "9")
    H.eq(P.checkpoint:GetText(), "floor 20")
    -- the rewards, with their tooltips
    H.eq(#P.rewardIcons, 3)
    H.eq(P.rewardIcons[2].tipLines[1], "Rift Cache")
    H.contains(P.rewardIcons[1].tipLines[2][1], "double on a new best floor")
    -- start floors: 1 and right after each checkpoint reached (bh_rift.cpp RiftEnter)
    local floors = {}
    for _, it in ipairs(P.dd.items) do floors[#floors + 1] = it.value end
    H.eq(table.concat(floors, ","), "1,6,11,16,21")
    H.eq(P.dd.items[2].text, "Floor 6  (checkpoint 5)")
    H.eq(P.ChosenFloor(), 21, "the highest start, as the server's own default")
    H.eq(P.enter.label:GetText(), "Enter Solo Eclipse Rift")
    H.eq(P.note:GetText(), "50 different floors are waiting.")
    P.dd:SetValue(6)
    P.enter:Click()
    H.eq(lastSay(M), ".rift enter 6")
    H.ok(not M.env.BleakholdActivitiesFrame:IsShown(), "the window makes room, as the old one")
    -- with a party, as its leader
    M.SetGroup("PARTY", 3, true)
    ns.UI.Open("rift")
    M.Advance(0.3)
    H.eq(P.enter.label:GetText(), "Enter with your party")
    H.ok(P.enter:IsEnabled())
end)

test("rift: closed, under level, not the leader, a raid, inside a dungeon", function(M, ns)
    FX.connect(M, H)
    feed(ns, { "U;0;0;0;0;0;80;0;0;50" })
    ns.UI.Open("rift")
    M.Advance(0.3)
    local P = ns.Rift
    H.eq(P.note:GetText(), "The Eclipse Rift is closed right now.")
    H.ok(not P.enter:IsEnabled())
    feed(ns, { "U;0;0;0;0;0;80;1;0;50" })
    M.playerLevel = 72
    P:Refresh()
    H.eq(P.note:GetText(), "You need to be level 80.", "RiftEnter's own words")
    H.ok(not P.enter:IsEnabled())
    H.eq(P.checkpoint:GetText(), "-")
    H.eq(P.bests[1]:GetText(), "-")
    M.playerLevel = 80
    -- a member who is not the leader follows the rift the leader opened (bh_rift.cpp RiftEnter's follow path)
    M.SetGroup("PARTY", 2, false)
    P:Refresh()
    H.eq(P.note:GetText(), P.FOLLOW_NOTE)
    H.eq(P.enter.label:GetText(), "Follow your party")
    H.ok(P.enter:IsEnabled(), "the server's follow path takes it")
    H.ok(not P.dd:IsEnabled(), "the floor is the leader's choice")
    P.enter:Click()
    H.eq(lastSay(M), ".rift enter", "no floor: the follow path")
    ns.UI.Open("rift")
    M.SetGroup("PARTY", 2, true)
    P:Refresh()
    H.eq(P.enter.label:GetText(), "Enter with your party")
    H.ok(P.dd:IsEnabled())
    M.SetGroup("RAID", 6, true)
    P:Refresh()
    H.eq(P.note:GetText(), "The rift takes at most 5 players - leave the raid group first.")
    M.SetGroup("NONE", 1, false)
    M.inInstance, M.instanceType = true, "party"
    P:Refresh()
    H.eq(P.note:GetText(), "Leave the dungeon or battleground first.")
    M.inInstance, M.instanceType = nil, nil
    P:Refresh()
    H.ok(P.enter:IsEnabled(), "open again")
    local floors = {}
    for _, it in ipairs(P.dd.items) do floors[#floors + 1] = it.value end
    H.eq(table.concat(floors, ","), "1", "no checkpoint yet: floor 1 only")
end)

test("rift: in a run (RIFT, U), Leave says .rift leave; the last run; the rank; the leaderboard", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    feed(ns, { "U;24;18;12;9;20;80;1;0;50" })
    ns.UI.Open("rift")
    M.Advance(0.3)
    local P = ns.Rift
    H.eq(P.runTitle:GetText(), "Your Last Run")
    H.eq(P.runLines[1]:GetText(), "No run yet")
    H.eq(P.rank:GetText(), "42", "the Rift rank")
    -- every floor is inside a dungeon
    M.inInstance, M.instanceType = true, "party"
    H.send(M, "RIFT", FX.examples(M).RIFT)
    M.Advance(0.3)
    H.eq(P.runTitle:GetText(), "Your Run")
    H.eq(P.runLines[1]:GetText(), "Floor 7  -  Echo of Nefarian")
    H.contains(P.runLines[2]:GetText(), "Time 02:00")
    H.contains(P.runLines[2]:GetText(), "1 death")
    M.Advance(2)
    H.ok(P.runLines[2]:GetText():match("^Time 02:0[12]"), "the time counts on: " .. P.runLines[2]:GetText())
    H.eq(P.enter.label:GetText(), "Leave the Eclipse Rift")
    H.eq(P.note:GetText(), "You are on floor |cffff9a3c7|r.")
    H.ok(not P.dd:IsEnabled(), "no start floor while inside")
    P.enter:Click()
    H.eq(lastSay(M), ".rift leave")
    -- the old U alone says the floor too
    H.send(M, "RIFT", { { 8001, 0, "", "", "", "", 18, "", 42 } })
    feed(ns, { "U;24;18;12;9;20;80;1;12;50" })
    P:Refresh()
    H.eq(P.enter.label:GetText(), "Leave the Eclipse Rift")
    feed(ns, { "U;24;18;12;9;20;80;1;0;50" })
    -- the last run
    H.send(M, "RIFTE", FX.examples(M).RIFTE)
    M.Advance(0.3)
    H.eq(P.runTitle:GetText(), "Your Last Run")
    H.eq(P.runLines[1]:GetText(), "Reached floor 9")
    H.ok(#M.FindText("20 Mythic Coins", true) > 0, "its rewards")
    P.board:Click()
    H.ok(M.env.BleakholdLeaderboardsFrame:IsShown() and ns.Leaderboards.board == "R", "the Rift leaderboard")
end)

-- The server ends a run with X (RiftLeave: .rift leave, a collapse) and RIFTE, never with a new U.
test("rift: the run ends with X and RIFTE and no new U: Enter and the last run come back, U is asked again",
    function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    M.inInstance, M.instanceType = true, "party"
    feed(ns, { "U;24;18;12;9;20;80;1;7;50" })
    H.send(M, "RIFT", FX.examples(M).RIFT)
    ns.UI.Open("rift")
    M.Advance(0.3)
    local P = ns.Rift
    H.eq(P.enter.label:GetText(), "Leave the Eclipse Rift")
    H.eq(P.runTitle:GetText(), "Your Run")
    -- Leave: the command, then U is asked again once the player is out
    local said = #M.said
    P.enter:Click()
    H.eq(lastSay(M), ".rift leave")
    feed(ns, { "X" })
    H.eq(ns.Legacy.rift.inFloor, 0, "X ends U's floor")
    H.send(M, "RIFTE", FX.examples(M).RIFTE)
    M.Advance(0.3)
    H.eq(P.enter.label:GetText(), "Enter Solo Eclipse Rift", "not 'Leave' after the run")
    H.eq(P.runTitle:GetText(), "Your Last Run")
    H.ok(not P.note:GetText():find("You are on floor", 1, true), P.note:GetText())
    local asked = 0
    for i = said + 1, #M.said do
        if M.said[i].msg == ".act mplus" then asked = asked + 1 end
    end
    H.ok(asked >= 1, "RIFTE asks for U again")
    M.Advance(2.5)
    -- out of the dungeon: a stale floor in U is no run (the rift's exit is in the open world)
    M.inInstance, M.instanceType = nil, nil
    feed(ns, { "U;24;18;12;9;20;80;1;7;50" })
    P:Refresh()
    H.eq(P.enter.label:GetText(), "Enter Solo Eclipse Rift", "outside an instance there is no run")
    -- one floor deeper: X for the floor left, then the new floor's S;4
    M.inInstance, M.instanceType = true, "party"
    feed(ns, { "X", "S;4;575;8;0;;0;0;Eclipse Rift - Utgarde Pinnacle" })
    H.eq(ns.Legacy.rift.inFloor, 8, "the floor entered")
    H.eq(ns.Legacy.Receive("S;1;602;8;1800;1,3;0;1;Halls of Lightning"), nil, "a keystone's S is left alone")
    H.eq(ns.Legacy.rift.inFloor, 8)
end)

------------------------------------------------------------------------------------------------------
-- Heroic Dungeons and Group Finder
------------------------------------------------------------------------------------------------------
test("heroic: what each mode is, refused changes greyed (not the leader, inside a dungeon)", function(M, ns)
    FX.connect(M, H)
    feed(ns, MPLUS)
    ns.UI.Open("heroic")
    M.Advance(0.3)
    local P = ns.Heroic
    H.contains(P.desc:GetText(), "level 80 Heroic version")
    H.ok(P.modes[1]:IsEnabled() and P.modes[3]:IsEnabled())
    H.contains(tipText(P.modes[2].tooltip()), "every enemy is level 80")
    H.contains(tipText(P.modes[3].tooltip()), "Mythic 0")
    H.contains(tipText(P.TileTooltip(ns.Legacy.mplus.byId[289])), "Your best keystone: +12")
    M.SetGroup("PARTY", 3, false)
    P:Refresh()
    H.ok(not P.modes[2]:IsEnabled(), "a member who is not the leader")
    H.contains(P.diff:GetText(), "Only the group leader")
    M.SetGroup("NONE", 1, false)
    M.inInstance, M.instanceType = true, "party"
    P:Refresh()
    H.ok(not P.modes[2]:IsEnabled(), "inside a dungeon")
    H.contains(P.diff:GetText(), "Leave the dungeon or battleground first.")
end)

test("heroic: a long tile name wraps upward instead of being cut, and the dark band covers its lines", function(M, ns)
    FX.connect(M, H)
    feed(ns, { "L;189;1800;0;Scarlet Monastery: Armory", "L;190;1800;0;Scarlet Monastery: Cathedral",
        "L;230;1800;0;Blackrock Depths: Upper City" })
    ns.UI.Open("heroic")
    M.Advance(0.3)
    local P = ns.Heroic
    local r1, r2 = P.tiles[1], P.tiles[2]
    H.eq(r1.name:GetText(), "Scarlet Monastery: Armory", "the whole name, not cut")
    H.eq(r2.name:GetText(), "Scarlet Monastery: Cathedral")
    -- the old tile's name (old :414): a width and no height, so the client wraps it; anchored at the bottom left
    H.eq(r1.name:GetWidth(), P.TILE_W - 12, "as wide as the tile less its margins")
    H.eq(r1.name:GetHeight() or 0, 0, "no fixed height (UI.OneLine sets one): one line is not forced")
    local point, rel, relPoint = r1.name:GetPoint(1)
    H.ok(point == "BOTTOMLEFT" and rel == r1 and relPoint == "BOTTOMLEFT", "grows upward from the bottom left")
    H.eq(r1.band:GetHeight(), 22, "one line: the old 22 px band")
    -- two lines in the client: the band reaches over both (the text height plus 12)
    r1.name.GetStringHeight = function() return 22 end
    P:Refresh()
    H.eq(r1.band:GetHeight(), 34, "two lines: the band covers them")
    -- never taller than the tile
    r1.name.GetStringHeight = function() return 200 end
    P:Refresh()
    H.eq(r1.band:GetHeight(), P.TILE_H - 2, "capped at the tile")
end)

test("group finder: the player's queue and Leave queue", function(M, ns)
    FX.connect(M, H)
    ns.UI.Open("group")
    M.Advance(0.3)
    local P = ns.GroupFinder
    H.contains(P.queueStatus:GetText(), "Not in a queue.")
    H.ok(not P.leave:IsShown())
    H.send(M, "QUEUE", { { 5, 1, "D", 33, 1, 5, 20, 100, "", "", 29, 39 } })
    M.Advance(0.3)
    H.eq(P.queueStatus:GetText(), "In queue: Veteran Shadowfang Keep")
    P.leave:Click()
    H.ok(H.lastIntent(M, "QLEAVE"))
end)

------------------------------------------------------------------------------------------------------
-- What the server refuses is never offered
------------------------------------------------------------------------------------------------------
test("mythic+: a key run under way shows its own level, not the lowered key; Lower Blackrock Spire is its map",
    function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("keys")
    M.Advance(0.3)
    local P = ns.Keys
    -- StartRun lowered the stored key at once (+8 -> +7, depleted until the run is finished)
    H.send(M, "KEY", { { 3, 602, 7, { 1, 3, 4 }, 0, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    H.send(M, "MPS", FX.examples(M).MPS)
    M.Advance(0.3)
    P:Refresh()
    H.eq(P.keyText:GetText(), "|cffa335ee+8|r  Halls of Lightning", "the run's level; the note is under it")
    H.ok(not P.keySub:GetText():find("right-click", 1, true), "no 'right-click the key' while it runs")
    H.eq(P.keySub:GetText(), "Run under way: in time +9 to +11 in a new dungeon, over time +7 here.")
    -- the map is named "Blackrock Spire"; the key's dungeon "Lower Blackrock Spire"
    H.ok(P.InKeyDungeon("Lower Blackrock Spire") == false, "outside")
    M.inInstance, M.instanceType, M.zone = true, "party", "Blackrock Spire"
    H.ok(P.InKeyDungeon("Lower Blackrock Spire"), "inside")
    M.zone = "Scarlet Monastery"
    H.ok(P.InKeyDungeon("Scarlet Monastery: Armory"))
    H.ok(not P.InKeyDungeon("Halls of Lightning"))
end)

test("difficulty and starts: refused in a battleground; a Dungeon Finder group loses Mythic, the Journey and the Rift",
    function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    local K = ns.Keys
    -- a battleground or arena: the bridge refuses KMODE on any instanceable map
    for _, kind in ipairs({ "pvp", "arena" }) do
        M.inInstance, M.instanceType = true, kind
        H.eq(K.DifficultyBlock(), "Leave the dungeon or battleground first.", kind)
    end
    M.inInstance, M.instanceType = nil, nil
    ns.UI.Open("heroic")
    M.Advance(0.3)
    local Hp = ns.Heroic
    H.ok(Hp.modes[3]:IsEnabled(), "Mythic outside a Dungeon Finder group")
    -- a Dungeon Finder group after its run (GetLFGInfoServer's inParty, FrameXML's "lfgparty")
    M.SetGroup("PARTY", 5, true)
    M.env.GetLFGInfoServer = function() return true, false, false end
    Hp:Refresh()
    H.ok(Hp.modes[1]:IsEnabled() and Hp.modes[2]:IsEnabled(), "Normal and Heroic stay")
    H.ok(not Hp.modes[3]:IsEnabled(), "not Mythic")
    ns.UI.Open("keys")
    M.Advance(0.3)
    H.ok(not K.mythic:IsEnabled())
    H.eq(K.MythicBlock(), "Mythic difficulty is not for Dungeon Finder groups.")
    H.contains(tipText(K.mythic.tooltip()), "not for Dungeon Finder groups")
    M.env.GameTooltip:Hide()
    M.Hover(K.mythic)
    H.contains(table.concat(M.env.GameTooltip.__lines, "\n"), "not for Dungeon Finder groups",
        "hovering the greyed Mythic button says why")
    M.Hover(K.mythic, false)
    feed(ns, BOARD)
    M.playerLevel = 20
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local D = ns.Dungeons
    H.ok(not D.enter:IsEnabled() and not D.find:IsEnabled())
    H.eq(D.hint:GetText(), "Leave the Dungeon Finder group first.")
    M.playerLevel = 80
    feed(ns, { "U;0;0;0;0;0;80;1;0;50" })
    ns.UI.Open("rift")
    M.Advance(0.3)
    local R = ns.Rift
    H.ok(not R.enter:IsEnabled())
    H.eq(R.note:GetText(), "Leave the Dungeon Finder group first.")
    M.env.GetLFGInfoServer = function() return false, false, false end
    R:Refresh()
    H.ok(R.enter:IsEnabled(), "a plain party again")
end)

test("rift: a party member under the rift's level keeps the leader from opening it", function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 80
    feed(ns, { "U;0;0;0;0;0;80;1;0;50" })
    M.SetGroup("PARTY", 3, true)
    local levels = { party1 = 80, party2 = 74 }
    local unitLevel, unitName = M.env.UnitLevel, M.env.UnitName
    M.env.UnitLevel = function(u) return levels[u] or unitLevel(u) end
    M.env.UnitName = function(u) return u == "party2" and "Friend" or unitName(u) end
    ns.UI.Open("rift")
    M.Advance(0.3)
    local P = ns.Rift
    H.ok(not P.enter:IsEnabled())
    H.eq(P.note:GetText(), "Friend needs to be level 80.")
    -- a follower is not checked: the leader's opening is (RiftEnter's follow path comes first)
    M.SetGroup("PARTY", 3, false)
    P:Refresh()
    H.eq(P.note:GetText(), P.FOLLOW_NOTE)
    M.SetGroup("PARTY", 3, true)
    levels.party2 = 80
    P:Refresh()
    H.ok(P.enter:IsEnabled(), "all at level")
end)

test("pages: no control sends an intent the server refuses (BCLAIM, TCLAIM, TREROLL, KCANCEL, QREPLY)",
    function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    feed(ns, BOARD)
    feed(ns, MPLUS)
    feed(ns, { "U;24;18;12;9;20;80;1;0;50" })
    M.inInstance, M.instanceType, M.zone = true, "party", "Halls of Lightning"
    M.SetGroup("PARTY", 5, true)
    feed(ns, { SOCKET })
    H.send(M, "QUEUE", FX.examples(M).QUEUE)
    for _, key in ipairs({ "dungeons", "keys", "rift", "heroic", "group" }) do
        ns.UI.Open(key)
        M.Advance(0.3)
        for _, b in ipairs(M.Clickables(ns.Activities.pages[key])) do
            if b:IsVisible() and b:IsEnabled() and b.__scripts.OnClick then
                b:Click()
                M.Advance(0.2)
                if not M.env.BleakholdActivitiesFrame:IsShown() then
                    ns.UI.Open(key)
                end
            end
        end
    end
    for _, op in ipairs({ "BCLAIM", "TCLAIM", "TREROLL", "KCANCEL", "QREPLY" }) do
        H.eq(H.countIntents(M, op), 0, op .. " never sent from these pages")
    end
    H.ok(H.countIntents(M, "KSTART") >= 1, "Start keystone is there")
end)

test("pages: the demo shows the controls but says nothing", function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1.5)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local P = ns.Dungeons
    H.ok(#ns.Legacy.journey.offers > 0, "the sample board")
    H.ok(P.enter:IsEnabled(), "the page as it would be")
    local before = says(M)
    P.enter:Click()
    P.find:Click()
    ns.UI.Open("rift")
    M.Advance(0.3)
    ns.Rift.enter:Click()
    H.eq(says(M), before, "no '.' command in demo mode")
end)

test("pages: no Journal art -> the stock LFG pictures for the thumbnails too", function(M, ns)
    FX.connect(M, H)
    feed(ns, BOARD)
    feed(ns, MPLUS)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local r = ns.Dungeons.rows[1]
    H.eq(r.thumb.__texture, "Interface\\LFGFrame\\UI-LFG-BACKGROUND-DEADMINES")
    local l, t, _, b, rr = r.thumb:GetTexCoord()
    H.ok(math.abs((rr - l) * 2 / (b - t) - 84 / 46) < 0.01, "cut in the thumbnail's shape")
    ns.UI.Open("keys")
    M.Advance(0.3)
    H.eq(ns.Keys.rows[1].thumb.__texture, "Interface\\LFGFrame\\UI-LFG-BACKGROUND-SCHOLOMANCE")
end, { before = function(M)
    setmetatable(M.missingTextures, { __index = function(_, path)
        return (type(path) == "string" and path:find("^Interface\\AddOns\\Bleakhold\\Art\\Journal\\")) and true or nil
    end })
end })

------------------------------------------------------------------------------------------------------
-- What the server refuses that the pages must refuse first (review r3)
------------------------------------------------------------------------------------------------------
test("journey and rift: the Royale or 1v1 arena queue greys the starts, worded as the bridge's QJOIN", function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 80
    feed(ns, BOARD)
    feed(ns, { "U;24;18;12;9;20;80;1;0;50" })
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local D, R = ns.Dungeons, ns.Rift
    H.ok(D.enter:IsEnabled(), "free")
    -- .act start and .rift enter never check these queues: the run or floor would cost the player the queue spot
    local royale = "You are in the Bleakhold Royale queue. Leave it first."
    local arena = "You are in the 1v1 arena queue. Leave it first."
    H.send(M, "QUEUE", { { 7, 1, "B", 901, 0, 1, 12, "", "", "", 80, 80, 13, 20, 40, "", "", 1 } })
    M.Advance(0.3)
    H.eq(D.StartBlock(), royale)
    H.ok(not D.find:IsEnabled() and not D.enter:IsEnabled(), "the board greyed")
    H.eq(D.hint:GetText(), royale)
    local before = says(M)
    D.find:Click()
    D.enter:Click()
    H.eq(says(M), before, "no .act start")
    ns.UI.Open("rift")
    M.Advance(0.3)
    H.eq(R.EnterBlock(), royale)
    H.ok(not R.enter:IsEnabled(), "Enter Solo Eclipse Rift greyed")
    H.eq(R.note:GetText(), royale)
    R.enter:Click()
    H.eq(says(M), before, "no .rift enter")
    -- a follower too (the follow path takes the player to the party's floor)
    M.SetGroup("PARTY", 2, false)
    R:Refresh()
    H.ok(not R.enter:IsEnabled(), "Follow your party greyed")
    H.eq(R.note:GetText(), royale)
    M.SetGroup("NONE", 1, false)
    H.send(M, "QUEUE", { { 8, 1, "A", 1, 1, 1, 40, 95 } })
    M.Advance(0.3)
    H.eq(R.note:GetText(), arena)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    H.eq(D.hint:GetText(), arena)
    H.ok(not D.enter:IsEnabled())
    -- out of the queue: free again
    H.send(M, "QUEUE", { { 9, 0 } })
    M.Advance(0.3)
    H.ok(D.enter:IsEnabled() and D.find:IsEnabled())
    D.enter:Click()
    H.eq(lastSay(M), ".act start 1001 solo")
end)

test("journey and rift: dead, in combat, on a flight path or in the air, as the server refuses", function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 80
    feed(ns, BOARD)
    feed(ns, { "U;24;18;12;9;20;80;1;0;50" })
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local D, R = ns.Dungeons, ns.Rift
    local env = M.env
    local cases = {
        { "UnitIsDeadOrGhost", "You are dead.", "You are dead." },
        { "UnitAffectingCombat", "You are in combat.", "You are in combat." },
        { "UnitOnTaxi", "You are on a flight.", "You are busy (battleground or flight)." },
    }
    for _, c in ipairs(cases) do
        env[c[1]] = function(u) return u == "player" end
        M.FireEvent("PLAYER_REGEN_DISABLED")
        M.Advance(0.3)
        H.ok(not D.find:IsEnabled() and not D.enter:IsEnabled(), c[1])
        H.eq(D.hint:GetText(), c[2], "CanLaunch's words")
        H.eq(R.EnterBlock(), c[3], "RiftEnter's words")
        env[c[1]] = function() return false end
    end
    -- flying (a flying mount): .act start's own refusal, the Rift takes it
    env.IsFlying = function() return 1 end
    M.FireEvent("PLAYER_CONTROL_LOST")
    M.Advance(0.3)
    H.eq(D.hint:GetText(), "Land first: the run brings you back to where you start it.")
    H.eq(R.EnterBlock(), nil)
    env.IsFlying = function() return nil end
    M.FireEvent("PLAYER_CONTROL_GAINED")
    M.Advance(0.3)
    H.ok(D.enter:IsEnabled(), "landed")
    -- the Rift page follows its events too
    ns.UI.Open("rift")
    M.Advance(0.3)
    H.ok(R.enter:IsEnabled())
    env.UnitIsDeadOrGhost = function(u) return u == "player" end
    M.FireEvent("PLAYER_DEAD")
    M.Advance(0.3)
    H.ok(not R.enter:IsEnabled(), "dead: greyed without a click")
    H.eq(R.note:GetText(), "You are dead.")
    env.UnitIsDeadOrGhost = function() return false end
    M.FireEvent("PLAYER_UNGHOST")
    M.Advance(0.3)
    H.ok(R.enter:IsEnabled(), "back")
end)

test("activities: the open page follows the party, its leader and the zone (the server sends nothing then)",
    function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 80
    feed(ns, { "U;24;18;12;9;20;80;1;0;50" })
    ns.UI.Open("rift")
    M.Advance(0.3)
    local R = ns.Rift
    H.eq(R.enter.label:GetText(), "Enter Solo Eclipse Rift")
    -- a level-70 friend accepts the invitation: the label and the member-level rule follow at once
    local levels = {}
    local unitLevel, unitName = M.env.UnitLevel, M.env.UnitName
    M.env.UnitLevel = function(u) return levels[u] or unitLevel(u) end
    M.env.UnitName = function(u) return u == "party1" and "Friend" or unitName(u) end
    levels.party1 = 70
    M.SetGroup("PARTY", 2, true)
    M.FireEvent("PARTY_MEMBERS_CHANGED")
    M.Advance(0.3)
    H.eq(R.enter.label:GetText(), "Enter with your party")
    H.ok(not R.enter:IsEnabled(), "greyed before the click")
    H.eq(R.note:GetText(), "Friend needs to be level 80.")
    -- the friend levels up
    levels.party1 = 80
    M.FireEvent("UNIT_LEVEL", "party1")
    M.Advance(0.3)
    H.ok(R.enter:IsEnabled(), "UNIT_LEVEL")
    -- the lead passes to the friend: the player follows
    M.SetGroup("PARTY", 2, false)
    M.FireEvent("PARTY_LEADER_CHANGED")
    M.Advance(0.3)
    H.eq(R.enter.label:GetText(), "Follow your party")
    -- the Journey: a party member whose group disbands is free to start again
    feed(ns, BOARD)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local D = ns.Dungeons
    H.eq(D.hint:GetText(), "Only your party leader can start or queue a run.")
    M.SetGroup("NONE", 1, false)
    M.FireEvent("PARTY_MEMBERS_CHANGED")
    M.Advance(0.3)
    H.ok(D.enter:IsEnabled(), "disbanded")
    H.contains(D.hint:GetText(), "Enter now alone")
    -- into a battleground with the window open
    M.inInstance, M.instanceType = true, "pvp"
    M.FireEvent("PLAYER_ENTERING_WORLD")
    M.Advance(0.3)
    H.ok(not D.enter:IsEnabled(), "in a battleground")
    H.eq(D.hint:GetText(), "Leave the dungeon or battleground first.")
    M.inInstance, M.instanceType = nil, nil
    M.FireEvent("ZONE_CHANGED_NEW_AREA")
    M.Advance(0.3)
    H.ok(D.enter:IsEnabled(), "out again")
    -- one refresh per burst; nothing while the window is closed
    local n = 0
    local refresh = D.Refresh
    D.Refresh = function(self) n = n + 1 return refresh(self) end
    for _ = 1, 5 do M.FireEvent("UNIT_LEVEL", "party2") end
    M.FireEvent("PARTY_MEMBERS_CHANGED")
    M.FireEvent("RAID_ROSTER_UPDATE")
    M.Advance(0.3)
    H.eq(n, 1, "a burst is one refresh")
    M.FireEvent("UNIT_LEVEL", "target")
    M.Advance(0.3)
    H.eq(n, 1, "not for a unit outside the group")
    M.env.BleakholdActivitiesFrame:Hide()
    M.FireEvent("PARTY_MEMBERS_CHANGED")
    M.Advance(0.3)
    H.eq(n, 1, "closed: nothing")
    D.Refresh = refresh
end)

test("journey: queued, a start takes the party out of the queue; members below the run's level are left out",
    function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 20
    feed(ns, BOARD)
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    local D = ns.Dungeons
    -- a party with a friend below The Deadmines' level 15 (CanLaunch leaves them out of the run)
    local levels = { party1 = 20, party2 = 14 }
    local unitLevel, unitName = M.env.UnitLevel, M.env.UnitName
    M.env.UnitLevel = function(u) return levels[u] or unitLevel(u) end
    M.env.UnitName = function(u) return u == "party2" and "Friend" or unitName(u) end
    M.SetGroup("PARTY", 3, true)
    M.FireEvent("PARTY_MEMBERS_CHANGED")
    M.Advance(0.3)
    H.eq(D.selected, 1001)
    H.ok(D.enter:IsEnabled(), "the leader still goes in")
    H.eq(D.hint:GetText(), "Friend is below level 15 and will be left out.")
    levels.party2 = 15
    D:Refresh()
    H.eq(D.hint:GetText(), "Enter now with your party, or find a group of your level range.")
    -- queued for a Journey run (StartNow and JoinLobby leave that queue first, quietly): the hint says so
    H.send(M, "QUEUE", { { 5, 1, "D", 33, 1, 5, 20, 100, "", "", 29, 39 } })
    M.Advance(0.3)
    H.ok(D.enter:IsEnabled())
    H.eq(D.hint:GetText(), "You are queued for Veteran Shadowfang Keep: starting or queueing another run takes you "
        .. "(and your party) out of it.")
end)

test("mythic+: a fresh Mythic 0 takes a keystone; a boss down, a member below level 80 or Heroic do not",
    function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("keys")
    M.Advance(0.3)
    local P = ns.Keys
    M.inInstance, M.instanceType, M.zone = true, "party", "Halls of Lightning"
    M.SetGroup("PARTY", 5, true)
    -- the server's own Mythic 0, 3 s after the group came in (StartAutoMythic: level 0, running at once)
    H.send(M, "MPS", { { 7002, 602, 0, "", 7, 0, 1800 } })
    H.send(M, "MP", { { 7002, 5000, 1800, 0, 0, 0, 100, 0, "", "", 1 } })
    feed(ns, { "G;Me:1:1:1:1|Ann:2:1:0:1|Bo:5:1:0:1|Cy:8:1:0:1|Di:4:1:0:1", SOCKET })
    M.Advance(0.3)
    H.eq(P.StartBlock(), nil, "StartRun turns it into the key run (fromMythic0)")
    H.ok(P.start:IsEnabled())
    H.eq(P.startHint:GetText(), "")
    -- a member below the key level: StartRun refuses with the member's name
    local levels = { party3 = 78 }
    local unitLevel, unitName = M.env.UnitLevel, M.env.UnitName
    M.env.UnitLevel = function(u) return levels[u] or (u:match("^party") and 80) or unitLevel(u) end
    M.env.UnitName = function(u) return u == "party3" and "Cy" or unitName(u) end
    M.FireEvent("UNIT_LEVEL", "party3")
    M.Advance(0.3)
    H.ok(not P.start:IsEnabled(), "a member below level 80")
    H.eq(P.startHint:GetText(), "Cy is below level 80.")
    levels.party3 = 80
    M.FireEvent("UNIT_LEVEL", "party3")
    M.Advance(0.3)
    H.ok(P.start:IsEnabled())
    -- the first boss falls: too late for a keystone
    H.send(M, "MP", { { 7002, 400000, 1800, 0, 0, 30, 100, 1, { 300 }, "", 1 } })
    M.Advance(0.3)
    H.ok(not P.start:IsEnabled(), "a boss down")
    H.eq(P.startHint:GetText(), "A boss is already dead in this Mythic 0. Reset the dungeon to insert a keystone.")
    -- a keystone run of its own: under way
    H.send(M, "MPS", FX.examples(M).MPS)
    H.send(M, "MP", FX.examples(M).MP)
    M.Advance(0.3)
    H.eq(P.StartBlock(), "A keystone run is under way.")
    -- a Heroic instance of the key's dungeon: the keystone opens nothing there (KeyStartBlock)
    ns.S.mplus = nil
    feed(ns, { "X" })
    local getInstanceInfo = M.env.GetInstanceInfo
    M.env.GetInstanceInfo = function() return "Halls of Lightning", "party", 2, "Heroic", 5, 0, nil end
    P:Refresh()
    H.ok(not P.start:IsEnabled(), "Heroic")
    H.eq(P.startHint:GetText(), P.NORMAL_ONLY)
    M.env.GetInstanceInfo = getInstanceInfo
    P:Refresh()
    H.contains(P.startHint:GetText(), "Right-click your keystone", "Normal: the keystone opens the start")
end)

test("mythic+: the Champions' built-in text says one of them must fall", function(M, ns)
    local _, text = ns.Keys.AffixInfo(13)
    H.eq(text, "Mythic Champions guard the dungeon: one must fall to finish the key.")
end)
