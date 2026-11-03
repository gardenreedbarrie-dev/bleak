-- The Bleakhold windows in their states, as the owner's previews show them: every scene in demo mode (Demo.lua), with
-- the server's legacy messages fed through Legacy.Receive where a page reads them (BHMP H/J, K/W/L/Z, U, RIDE).
--
--   Tools/UiLint/preview/render.sh Tools/UiLint/preview/scenes/pages.lua journey out.png --stock <stock art> \
--       --journal <Journal pictures>
--
-- Activities: journey (queued, a row hovered; the custom run under the queue), journey_nojournal (the stock LFG
-- pictures), dropdown_custom (the custom run's dungeon list open), mplus, mplus_nojournal, mplus_nokey,
-- mplus_lowlevel (under the key level), mplus_run (a key run under way), rift (the last run), rift_run (in a run),
-- rift_follow (a party member), dropdown_rift, heroic, group, royale, royale_idle, warmode, warmode_wanted, arena,
-- arena_checklist, tasks, tasks_realm (the bridge's TASKS), act_leave (the Leave dungeon button), dialog_leave.
-- Collections: collections_legacy, collections_mounts, collections_pets, collections_later, transmog,
-- transmog_missing, transmog_illusions, dropdown_outfit, animations, emotewheel.
-- Windows: season, leaderboards, leaderboards_rift, leaderboards_echoes, leaderboards_firsts, leaderboards_arena,
-- case, case_won, graphics, dropdown_graphics.
-- Dialogs: dialog (UI.Confirm), dialog_prompt (UI.Prompt), dialog_ride (BHMP RIDE), dialog_oldaddons.
-- The HUD frames are in hud.lua, the Royale countdown in royale_countdown.lua, the kit sheet in kit.lua.
local S = {}
S.before = {}

------------------------------------------------------------------------------------------------------
-- helpers
------------------------------------------------------------------------------------------------------
local function demo(M, ns, level)
    M.playerLevel = level or 80
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1.5)
end

-- an Activities page; after(M, ns, env, P, "before"|"after") runs before UI.Open and after it (what it returns after
-- the open, if anything, is drawn instead of the window alone)
local function page(key, after, level)
    return function(M, ns, RS, env, P)
        demo(M, ns, level)
        if after then after(M, ns, env, P, "before") end
        ns.UI.Open(key)
        M.Advance(1.2)
        local frames = after and after(M, ns, env, P, "after")
        return frames or env.BleakholdActivitiesFrame
    end
end

local function noJournal(M, env, P)
    setmetatable(M.missingTextures, { __index = function(_, path)
        return (type(path) == "string" and path:find("^Interface\\AddOns\\Bleakhold\\Art\\Journal\\")) and true or nil
    end })
end

------------------------------------------------------------------------------------------------------
-- Activities
------------------------------------------------------------------------------------------------------
-- the Journey: a level 34 character in the Journey's queue for Veteran Shadowfang Keep (3 of 5 players)
local function journey(M, ns, env, P, when)
    if when == "before" then
        M.playerLevel = 34
        ns.Legacy.Receive("H;5400;1002;3;0;1")
        for _, msg in ipairs(ns.Legacy.DEMO) do
            if msg:sub(1, 2) == "J;" then ns.Legacy.Receive(msg) end
        end
        ns.Legacy.Receive("J;1009;48;1;1;2;24;0;71;1104;4;160;Blackfathom Deeps;Fortified")
        ns.Legacy.Receive("J;1010;90;0;0;2;25;0;0;0;0;130;Gnomeregan;")
        ns.Demo.Push("QUEUE", { { 90, 1, "D", 33, 1, 5, 20, 100, "", "", 29, 39 } })
        M.Advance(0.3)
    else
        ns.Dungeons.selected = 1003
        ns.Dungeons:Refresh()
        ns.Activities.UpdateArt()
        P.hover(ns.Dungeons.rows[2])
    end
end
S.journey = page("dungeons", journey, 34)
S.before.journey_nojournal = noJournal
S.journey_nojournal = page("dungeons", journey, 34)

-- Mythic+: the keystone, the week's affixes with Champions and Boons from +14, the season list with bests
local function mplus(M, ns, env, P, when)
    if when == "before" then
        ns.Legacy.Receive("W;12;1,3,10,8;14;1.096000;1.075000")
        ns.Legacy.Receive("Z;3")
    end
end
S.mplus = page("keys", mplus)
S.before.mplus_nojournal = noJournal
S.mplus_nojournal = page("keys", mplus)

-- a +8 run under way: the stored key is already one level lower, the page shows the run's own level
S.mplus_run = page("keys", function(M, ns, env, P, when)
    if when == "before" then
        mplus(M, ns, env, P, "before")
        ns.Demo.Push("MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
        M.Advance(0.3)
    end
end)

-- no keystone yet (the owner's screenshot)
S.mplus_nokey = page("keys", function(M, ns, env, P, when)
    if when == "before" then
        ns.Legacy.Receive("W;12;1,3,10,8;14;1.096000;1.075000")
        ns.Demo.Push("KEY", { { 99, 0, 0, "", 2, 0, "", 40, 0, 900001, 15, 7, 0 } })
        M.Advance(0.3)
    end
end)

-- the Rift: bests by size, checkpoint 20, the last run
S.rift = page("rift", function(M, ns, env, P, when)
    if when == "before" then
        ns.Legacy.Receive("U;24;18;12;9;20;80;1;0;50")
        ns.Demo.Push("RIFTE", { { 8001, 23, 912000, 1840, 1, 42 }, { "C", 106 },
            { "T", 1, "", "Mythical Cache: Helm of the Rift" } })
        M.Advance(0.3)
    end
end)

-- in a run, floor 23
S.rift_run = page("rift", function(M, ns, env, P, when)
    if when == "before" then
        ns.Legacy.Receive("U;24;18;12;9;20;80;1;23;50")
    else
        ns.Demo.Push("RIFT", { { 8002, 1, 23, 3, "Ingvar the Plunderer", 754000, 24, 3120, 42, 2, 3 } })
        M.Advance(0.3)
    end
end)

S.heroic = page("heroic", function(M, ns, env, P, when)
    if when == "after" then P.hover(ns.Heroic.tiles[5]) end
end)

S.group = page("group", function(M, ns, env, P, when)
    if when == "before" then
        ns.Demo.Push("QUEUE", { { 91, 1, "D", 33, 1, 5, 20, 100, "", "", 29, 39 } })
        M.Advance(0.3)
    end
end)

-- queued (13 of 20), two matches running, the last match placed 7th of 32 with its rewards
S.royale = page("royale", function(M, ns, env, P, when)
    if when == "before" then
        ns.Demo.Push("ROYE", { { 7001, 7, 32, 2, 18400, 2100, 1840, "Dalia", 11, 7, 1 }, { "H", 400, "", "Placement" },
            { "S", 12, "", "Placement" }, { "H", 150, "", "Eliminations" } })
        M.Advance(0.2)
        local H = ns.RoyaleHud
        if H and H.result then H.result:Hide() end
    else
        ns.Demo.Push("QUEUE", { { 4, 1, "B", 901, 0, 1, 12, "", "", "", 80, 80, 13, 20, 40, "", "", 2 } })
        M.Advance(0.6)
    end
end)
S.royale_idle = page("royale")

S.warmode = page("warmode")
S.warmode_wanted = page("warmode", function(M, ns, env, P, when)
    if when == "after" then
        ns.Demo.Push("WMST", { { 1, 600, "", 20, 0, 10, 0, 8, "H", 31, 22, 4, 1, 840, 248, 1200, 3720, 18, 60, 7, 118,
            96 } })
        M.Advance(0.3)
    end
end)

S.arena = page("arena")
S.arena_checklist = page("arena", function(M, ns, env, P, when)
    if when == "after" then
        ns.Arena.page.cards[3]:Click()
        ns.Arena.page.detail.views[2]:Click()
        M.Advance(0.3)
    end
end)

S.tasks = page("tasks")

-- the realm's TASKS as the bridge sends it (bh_ui_bridge_map.cpp BountyTasks): three Journey bounties paid in Shards,
-- no reroll, no weekly task (no Reroll button, no empty Weekly Tasks heading)
S.tasks_realm = page("tasks", function(M, ns, env, P, when)
    if when == "before" then
        ns.Demo.Push("TASKS", { { 999, 0, 0, "G" }, { 101, "D", 1, 0, 1, "S", 40, "", 0 },
            { 102, "D", 2, 0, 1, "S", 40, "", 0 }, { 103, "D", 3, 1, 1, "S", 40, "", 1 } })
        M.Advance(0.3)
    end
end)

-- the custom run's dungeon list open, a row hovered (its tooltip: chapter, level, best, the server record)
S.dropdown_custom = page("dungeons", function(M, ns, env, P, when)
    if when == "before" then
        M.playerLevel = 34
    else
        local dd = ns.Dungeons.customBox.dungeon
        dd:Click()
        M.Advance(0.1)
        return { env.BleakholdActivitiesFrame, dd.menu }
    end
end, 34)

-- a level 30 character: Mythic+ opens at level 80
S.mplus_lowlevel = page("keys", function(M, ns, env, P, when)
    if when == "before" then
        ns.Legacy.Receive("W;12;1,3,10,8;14;1.096000;1.075000")
        ns.Demo.Push("KEY", { { 99, 0, 0, "", 2, 0, "", 40, 0, 900001, 15, 7, 0 } })
        M.Advance(0.3)
    end
end, 30)

-- a party member who is not the leader: Follow your party
S.rift_follow = page("rift", function(M, ns, env, P, when)
    if when == "before" then
        ns.Legacy.Receive("U;24;18;12;9;20;80;1;0;50")
        M.SetGroup("PARTY", 3, false)
    end
end)

-- the Rift's start-floor dropdown, open (its menu hangs off UIParent, so it is returned with the window)
S.dropdown_rift = function(M, ns, RS, env, P)
    demo(M, ns)
    ns.Legacy.Receive("U;24;18;12;9;20;80;1;0;50")
    ns.UI.Open("rift")
    M.Advance(1.2)
    local dd = ns.Activities.pages.rift.dd
    dd:Click()
    M.Advance(0.1)
    return { env.BleakholdActivitiesFrame, dd.menu }
end

------------------------------------------------------------------------------------------------------
-- Collections, Transmog, Animations, emote wheel (W1)
------------------------------------------------------------------------------------------------------
local ICONS = {
    [16866] = "INV_Helmet_09", [16868] = "INV_Shoulder_15", [16865] = "INV_Chest_Plate16",
    [16861] = "INV_Bracer_18", [16863] = "INV_Gauntlets_10", [16864] = "INV_Belt_09",
    [16867] = "INV_Pants_04", [16862] = "INV_Boots_Plate_04",
    [100] = "INV_Helmet_09", [101] = "INV_Shoulder_15", [102] = "INV_Chest_Plate16", [103] = "INV_Pants_04",
    [104] = "INV_Sword_04", [105] = "INV_Shield_06", [201] = "INV_Chest_Cloth_17", [202] = "INV_Chest_Leather_09",
    [203] = "INV_Chest_Cloth_43",
    [32837] = "INV_Weapon_Glave_01", [32838] = "INV_Axe_02", [32839] = "INV_Sword_04",
    [32840] = "INV_Shield_06", [32841] = "INV_Misc_Bag_10", [32842] = "INV_Chest_Plate16",
    [32843] = "Ability_Mount_RidingHorse", [990001] = "INV_Box_02",
}
local NAMES = {
    [16866] = "Helm of Might", [16868] = "Pauldrons of Might", [16865] = "Breastplate of Might",
    [16861] = "Bracers of Might", [16863] = "Gauntlets of Might", [16864] = "Belt of Might",
    [16867] = "Legplates of Might", [16862] = "Sabatons of Might",
    [100] = "Helm of Dawn", [101] = "Spaulders", [102] = "Chestplate", [103] = "Leggings", [104] = "Sword",
    [105] = "Shield", [201] = "Ruby Robe", [202] = "Night Vest", [203] = "Sun Tunic", [211] = "Ruby Robe II",
}
local SLOT_ART = {
    HeadSlot = "Head", ShoulderSlot = "Shoulder", BackSlot = "Chest", ChestSlot = "Chest", ShirtSlot = "Shirt",
    TabardSlot = "Tabard", WristSlot = "Wrists", HandsSlot = "Hands", WaistSlot = "Waist", LegsSlot = "Legs",
    FeetSlot = "Feet", MainHandSlot = "MainHand", SecondaryHandSlot = "SecondaryHand", RangedSlot = "Ranged",
}
local EQUIPPED = { [1] = 100, [3] = 101, [5] = 102, [7] = 103, [16] = 104, [17] = 105 }

local function items(M, env)
    for id, name in pairs(NAMES) do
        M.items[id] = { name = name }
    end
    env.GetItemIcon = function(id)
        id = tonumber(id) or tonumber(tostring(id):match("item:(%d+)"))
        return "Interface\\Icons\\" .. (ICONS[id] or "INV_Misc_QuestionMark")
    end
    env.GetInventorySlotInfo = function(key)
        return 0, "Interface\\PaperDoll\\UI-PaperDoll-Slot-" .. (SLOT_ART[key] or "Chest")
    end
    local LOC = { [104] = "INVTYPE_WEAPON", [105] = "INVTYPE_SHIELD", [100] = "INVTYPE_HEAD" }
    local info = env.GetItemInfo
    env.GetItemInfo = function(id)
        local r = { info(id) }
        local n = tonumber(id) or tonumber(tostring(id):match("item:(%d+)"))
        if r[1] and LOC[n] then r[9] = LOC[n] end
        if r[1] and ICONS[n] then r[10] = "Interface\\Icons\\" .. ICONS[n] end
        return unpack(r, 1, 10)
    end
    env.GetInventoryItemID = function(unit, slot)
        return unit == "player" and EQUIPPED[slot] or nil
    end
end

local function idemo(M, ns, env)
    items(M, env)
    demo(M, ns)
end

local function tm(M, body)
    M.FireEvent("CHAT_MSG_ADDON", "transmog", body, "WHISPER", M.playerName)
end

S.collections_legacy = function(M, ns, RS, env, P)
    idemo(M, ns, env)
    ns.UI.Open("collections")
    ns.Collections.ShowTab("legacy")
    M.Advance(1)
    P.hover(ns.Collections.main.pieces[3])
    return env.BleakholdCollectionsFrame
end

local function mount(id, name, icon)
    return { creatureID = id, name = name, icon = "Interface\\Icons\\" .. icon }
end
local MOUNTS = {
    mount(1, "Swift Gryphon", "Ability_Mount_Gryphon_01"), mount(2, "Black Stallion", "Ability_Mount_RidingHorse"),
    mount(3, "Brown Ram", "Ability_Mount_MountainRam"), mount(4, "Red Mechanostrider", "Ability_Mount_MechaStrider"),
    mount(5, "Swift White Hawkstrider", "Ability_Mount_CockatriceMountElite_White"),
    mount(6, "Black War Kodo", "Ability_Mount_Kodo_01"), mount(7, "Swift Frostsaber", "Ability_Mount_WhiteTiger"),
    mount(8, "Swift Stripped Tiger", "Ability_Mount_JungleTiger"), mount(9, "Emerald Raptor", "Ability_Mount_Raptor"),
    mount(10, "Frostwolf Howler", "Ability_Mount_WhiteDireWolf"), mount(11, "Red Proto-Drake", "Ability_Mount_Drake_Proto"),
    mount(12, "Deathcharger", "Ability_Mount_Undeadhorse"), mount(13, "Dreadsteed", "Ability_Mount_Dreadsteed"),
    mount(14, "Charger", "Ability_Mount_Charger"),
}
local PETS = {
    mount(21, "Mechanical Squirrel", "INV_Misc_EngGizmos_01"), mount(22, "Orange Tabby Cat", "INV_Pet_Cats_OrangeTabbyCat"),
    mount(23, "Sprite Darter Hatchling", "INV_Misc_Head_Dragon_Blue"), mount(24, "Whiskers the Rat", "INV_Misc_MonsterTail_03"),
    mount(25, "Hawk Owl", "Ability_Hunter_Pet_Owl"), mount(26, "Baby Blizzard Bear", "INV_Pet_BabyBlizzardBear"),
    mount(27, "Speedy", "Ability_Hunter_Pet_Turtle"), mount(28, "Mini Diablo", "INV_Egg_03"),
    mount(29, "Silver Tabby Cat", "Ability_Hunter_Pet_Cat"), mount(30, "Pet Carrier Kitten", "INV_Box_PetCarrier_01"),
}

local function companions(kind)
    return function(M, ns, RS, env, P)
        M.companions.MOUNT = MOUNTS
        M.companions.CRITTER = PETS
        env.CallCompanion = function() end
        idemo(M, ns, env)
        ns.UI.Open("collections")
        ns.Collections.ShowTab(kind)
        M.Advance(0.5)
        P.hover(ns.Collections.companions.scroll.child)
        return env.BleakholdCollectionsFrame
    end
end
S.collections_mounts = companions("mounts")
S.collections_pets = companions("pets")

S.collections_later = function(M, ns, RS, env, P)
    idemo(M, ns, env)
    ns.UI.Open("collections")
    M.Advance(0.5)
    ns.Collections.ShowTab("later")
    M.Advance(0.5)
    -- a character part way through the later looks (the demo has none); after the window's own GET
    ns.Demo.Push("COLL", { { 9999, 412, "", 1214, 3771, 3, 48, { 3, 0, 0, 0, 0, 0, 0 }, { 8, 8, 5, 9, 5, 5, 8 } } })
    M.Advance(0.5)
    return env.BleakholdCollectionsFrame
end

local function transmog(M, ns, env)
    idemo(M, ns, env)
    tm(M, "Open")
    tm(M, "AvailableTransmogs:4:5:3:start")
    tm(M, "AvailableTransmogs:4:5:3:201,211,212:202")
    tm(M, "AvailableTransmogs:4:5:3:+213:203")
    tm(M, "AvailableTransmogs:4:5:3:end")
    tm(M, "TransmogStatus:1:4,202")
    M.FireEvent("CHAT_MSG_ADDON", "BHMOG", "B;10;1;3;5", "WHISPER", M.playerName)
    M.Advance(0.5)
    local TM = ns.Transmog
    TM.SelectSlot(5)
    TM.frame.tiles[1]:Click("LeftButton")
    M.Advance(0.5)
    tm(M, "TransmogCost:12345:1")
    M.Advance(0.5)
    return TM
end

S.transmog = function(M, ns, RS, env, P)
    local TM = transmog(M, ns, env)
    P.hover(TM.frame.tiles[3])
    return env.BleakholdCollectionsFrame
end

S.transmog_missing = function(M, ns, RS, env, P)
    local TM = transmog(M, ns, env)
    local f = TM.frame
    f.missing:Click()
    local seq = TM.missingSeq
    tm(M, "MissingLooks:" .. seq .. ":4:start")
    tm(M, "MissingLooks:" .. seq .. ":4:201:202:203:211")
    tm(M, "MissingLooks:" .. seq .. ":4:end")
    M.Advance(0.5)
    f.tiles[2]:Click("LeftButton")
    M.Advance(0.5)
    P.hover(f.tiles[4])
    return env.BleakholdCollectionsFrame
end

S.transmog_illusions = function(M, ns, RS, env, P)
    local TM = transmog(M, ns, env)
    tm(M, "Illusions:start")
    tm(M, "IllusionName:3789:Berserking")
    tm(M, "IllusionName:3368:Rune of the Fallen Crusader")
    tm(M, "IllusionName:3370:Rune of Razorice")
    tm(M, "IllusionName:2673:Mongoose")
    tm(M, "Illusions:3789:3368:3370:2673")
    tm(M, "Illusions:end")
    tm(M, "IllusionStatus:3789:0")
    M.Advance(0.5)
    TM.frame.illusionsTab:Click()
    M.Advance(0.5)
    P.hover(TM.frame.illRows.items[4])
    return env.BleakholdCollectionsFrame
end

-- the outfit dropdown open
S.dropdown_outfit = function(M, ns, RS, env, P)
    local TM = transmog(M, ns, env)
    local dd = TM.frame.outfit
    dd:SetItems({ { value = "1", text = "Raid night" }, { value = "2", text = "Scarlet crusader" },
        { value = "3", text = "Fishing day" }, { value = "4", text = "Arena gladiator" } })
    dd:SetValue("2", true)
    dd:Click()
    M.Advance(0.1)
    return { env.BleakholdCollectionsFrame, dd.menu }
end

S.animations = function(M, ns, RS, env, P)
    idemo(M, ns, env)
    -- dances on (feature bit 128; the demo realm has them off)
    ns.Comm.server.features = bit.bor(ns.Comm.server.features or 0, 128)
    ns.UI.Open("animations")
    M.Advance(0.5)
    P.hover(ns.Animations.tab.entries[4])
    return env.BleakholdCollectionsFrame
end

S.emotewheel = function(M, ns, RS, env, P)
    idemo(M, ns, env)
    local A = ns.Animations
    A.OpenWheel(false)
    local w = A.wheel
    w:ClearAllPoints()
    w:SetPoint("CENTER", env.UIParent, "CENTER", 0, 0)
    env.GetCursorPosition = function() return (960 + 110), 540 end
    A.RefreshWheel(true)
    return w
end

------------------------------------------------------------------------------------------------------
-- Season, Leaderboards, Case, Graphics (W2)
------------------------------------------------------------------------------------------------------
S.season = function(M, ns, RS, env, P)
    demo(M, ns)
    ns.UI.Open("season")
    M.Advance(0.5)
    P.hover(ns.Season.we.mine.handin)
    return env.BleakholdSeasonFrame
end

S.leaderboards = function(M, ns, RS, env, P)
    demo(M, ns)
    ns.UI.Open("leaderboards")
    M.Advance(0.5)
    P.hover(ns.Leaderboards.table.rows[3])
    return env.BleakholdLeaderboardsFrame
end

S.leaderboards_rift = function(M, ns, RS, env, P)
    demo(M, ns)
    ns.UI.Open("leaderboards-rift")
    M.Advance(0.5)
    return env.BleakholdLeaderboardsFrame
end

-- a board by its tab (the tab's own click: query, then refresh)
local function board(i)
    return function(M, ns, RS, env, P)
        demo(M, ns)
        ns.UI.Open("leaderboards")
        M.Advance(0.5)
        ns.Leaderboards.tabs[i]:Click()
        M.Advance(0.5)
        return env.BleakholdLeaderboardsFrame
    end
end
S.leaderboards_echoes = board(3)
S.leaderboards_firsts = board(5)

S.leaderboards_arena = function(M, ns, RS, env, P)
    demo(M, ns)
    ns.UI.Open("leaderboards")
    M.Advance(0.5)
    ns.Leaderboards.OpenArena(3)
    M.Advance(0.5)
    P.hover(ns.Leaderboards.table.rows[1])
    return env.BleakholdLeaderboardsFrame
end

local function caseScene(M, ns, env, count)
    items(M, env)
    demo(M, ns)
    M.items[32837] = { name = "Gold Glaive" }
    M.items[32838] = { name = "Rainbow Glaive" }
    M.items[32839] = { name = "Ashen Blade" }
    M.items[32840] = { name = "Bulwark of Dawn" }
    M.items[32841] = { name = "Traveler's Pack" }
    M.items[32842] = { name = "Breastplate of Might" }
    M.items[32843] = { name = "Bleak Steed" }
    M.items[990001] = { name = "Glaive Case" }
    env.GetItemCount = function(id) return id == 990001 and count or 0 end
    ns.Demo.Push("CASE", { { 990001, "Glaive Case", "Unlock it to receive one of the items below.", "", "" },
        { 32837, 1, 1200, 4 }, { 32838, 2, 400, 5 }, { 32839, 1, 2400, 3 }, { 32840, 1, 2000, 3 },
        { 32841, 1, 3000, 2 }, { 32842, 1, 900, 4 }, { 32843, 1, 100, 5 } })
    ns.Cases.Open(990001)
    M.Advance(0.5)
end

S.case = function(M, ns, RS, env, P)
    caseScene(M, ns, env, 3)
    P.hover(ns.Cases.frame.unlock)
    return env.BleakholdCaseFrame
end

S.case_won = function(M, ns, RS, env, P)
    caseScene(M, ns, env, 2)
    local CA = ns.Cases
    CA.frame.unlock:Click()
    M.Advance(0.4)
    ns.Demo.Push("UNBOX", { { 990001, 7, 32843, 1, CA.reqNonce } })
    M.Advance(9)
    return env.BleakholdCaseFrame
end

local GFX = {
    bleakFx = "1", bleakFxAA = "2", bleakFxAO = "0.6", bleakFxAORadius = "1.5", bleakFxSunShafts = "0.4",
    bleakFxBloom = "0.35", bleakFxBloomThreshold = "0.8", bleakFxClarity = "0.35", bleakFxContrast = "0.18",
    bleakFxSaturation = "1.05", bleakFxVibrance = "0.25", bleakFxWarmth = "0.3", bleakFxBrightness = "1",
    bleakFxShadows = "0.012", bleakFxVignette = "0.18", bleakFxSharpen = "0.25", gxMultisample = "1",
    bleakFxWater = "1", bleakFxWaterReflections = "1", bleakFxWaterRipples = "0.12",
    bleakFxGrassWind = "1", bleakFxGrassParting = "1", bleakFxContactShadows = "0.6",
}

S.graphics = function(M, ns, RS, env, P)
    for k, v in pairs(GFX) do M.cvars[k] = v end
    demo(M, ns)
    ns.UI.Open("graphics")
    M.Advance(0.5)
    P.hover(ns.Graphics.frame.sliders[3].slider)
    return env.BleakholdGraphics
end

-- the preset dropdown open
S.dropdown_graphics = function(M, ns, RS, env, P)
    for k, v in pairs(GFX) do M.cvars[k] = v end
    demo(M, ns)
    ns.UI.Open("graphics")
    M.Advance(0.5)
    local dd = ns.Graphics.frame.preset
    dd:Click()
    M.Advance(0.1)
    return { env.BleakholdGraphics, dd.menu }
end

------------------------------------------------------------------------------------------------------
-- dialogs
------------------------------------------------------------------------------------------------------
S.dialog = function(M, ns, RS, env, P)
    demo(M, ns)
    ns.UI.Confirm("Reroll this task for 50 Mythic Coins?\nThe server checks the price again.", function() end,
        "Reroll")
    return env.BleakholdDialog
end

S.dialog_prompt = function(M, ns, RS, env, P)
    demo(M, ns)
    ns.UI.Prompt("Name this outfit:", "Raid night", function() end, "Save", 24)
    return env.BleakholdDialog
end

-- the server's riding offer (BHMP RIDE), a StaticPopup
S.dialog_ride = function(M, ns, RS, env, P)
    env.GetCoinTextureString = function(c) return math.floor(c / 10000) .. " gold" end
    ns.Legacy.Receive("RIDE;40000")
    return env.StaticPopup1
end

-- in a dungeon: the window's Leave dungeon button (hovered) on the Mythic+ page
S.act_leave = function(M, ns, RS, env, P)
    demo(M, ns)
    M.inInstance, M.instanceType = true, "party"
    ns.Legacy.Receive("W;12;1,3,10,8;14;1.096000;1.075000")
    ns.UI.Open("keys")
    M.Advance(1.2)
    ns.Activities.UpdateLeave()
    P.hover(ns.Activities.leave)
    return env.BleakholdActivitiesFrame
end

-- its question: the window closes first (Activities.lua: the dialog would sit on the page's title)
S.dialog_leave = function(M, ns, RS, env, P)
    demo(M, ns)
    M.inInstance, M.instanceType = true, "party"
    ns.UI.Open("group")
    M.Advance(0.6)
    ns.Activities.leave:Click()
    return { env.BleakholdActivitiesFrame, env.StaticPopup1 }
end

-- an old addon from the website still installed
S.before.dialog_oldaddons = function(M, env, P)
    M.addons.BleakholdActivities = true
    M.addons.BleakholdChat = true
end
S.dialog_oldaddons = function(M, ns, RS, env, P)
    M.Advance(4)
    return env.StaticPopup1
end

return S
