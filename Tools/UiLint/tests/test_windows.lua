-- Window behaviour against server snapshots (live mode, frames through the real receive path).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function texts(M, s)
    return #M.FindText(s, true)
end

test("windows are registered for ESC and open from /bh and /bleakhold", function(M, ns)
    local names = {}
    for _, n in ipairs(M.env.UISpecialFrames) do names[n] = true end
    ns.UI.Confirm("test", function() end)
    for _, n in ipairs(M.env.UISpecialFrames) do names[n] = true end
    for _, n in ipairs({ "BleakholdActivitiesFrame", "BleakholdCollectionsFrame", "BleakholdSeasonFrame", "BleakholdLeaderboardsFrame", "BleakholdDialog" }) do
        H.ok(names[n], n .. " in UISpecialFrames")
    end
    H.eq(M.env.SLASH_BLEAKHOLD1, "/bh")
    H.eq(M.env.SLASH_BLEAKHOLD2, "/bleakhold")
    M.env.SlashCmdList.BLEAKHOLD("")
    H.ok(M.env.BleakholdActivitiesFrame:IsShown(), "/bh opens Activities")
    M.env.SlashCmdList.BLEAKHOLD("collections")
    H.ok(M.env.BleakholdCollectionsFrame:IsShown())
    M.env.SlashCmdList.BLEAKHOLD("season")
    H.ok(M.env.BleakholdSeasonFrame:IsShown())
    M.env.SlashCmdList.BLEAKHOLD("lb")
    H.ok(M.env.BleakholdLeaderboardsFrame:IsShown())
    M.env.SlashCmdList.BLEAKHOLD("nonsense")
    H.ok(#M.chat > 0, "help printed")
end)

test("windows are movable by the header and remember their position", function(M, ns)
    local w = M.env.BleakholdActivitiesFrame
    w:Show()
    local header = w.header
    M.Fire(header, "OnDragStart")
    w:ClearAllPoints()
    w:SetPoint("TOPLEFT", M.env.UIParent, "TOPLEFT", 120, -80)
    M.Fire(header, "OnDragStop")
    local pos = M.env.BleakholdCharDB.windows.BleakholdActivitiesFrame
    H.eq(pos.point, "TOPLEFT")
    H.eq(pos.x, 120)
    H.eq(pos.y, -80)
end)

test("Activities: era, affixes, tasks, your week, resets", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("tasks")
    M.Advance(1.2)
    H.ok(texts(M, "The Black Temple") > 0, "era name")
    H.ok(texts(M, "|cffffd100Next week:|r Ahn'Qiraj era") > 0, "next era, its prefix gold")
    -- the affixes as the old window showed them: spell icons with the level each starts at, names in the tooltip
    local aff = ns.Activities.tasksPage.era.affixes
    H.ok(aff[1]:IsShown() and aff[3]:IsShown(), "affix icons")
    H.eq(aff[1].icon:GetTexture(), "Interface\\Icons\\Ability_Warrior_ShieldWall", "Fortified's icon")
    H.eq(aff[1].level:GetText(), "+2")
    H.eq(aff[3].level:GetText(), "+7")
    H.eq(aff[3].tipLines[1], "Volcanic")
    H.ok(texts(M, "Heroic hero") > 0 and texts(M, "Key sweeper") > 0, "daily cards")
    H.ok(texts(M, "14 / 20") > 0, "progress")
    H.ok(texts(M, "Claim 20 Mythic Coins") > 0, "claim button on the claimable task")
    H.ok(texts(M, "1 Emblem of Heroism") > 0, "reward chip")
    H.ok(texts(M, "Timed and tested") > 0, "weekly row")
    H.ok(texts(M, "2,140 / 5,500") > 0, "coins")
    H.ok(texts(M, "Floor 18") > 0, "rift best")
    H.ok(texts(M, "First Raid Lord Echo") > 0 and texts(M, "Still open") > 0, "weekly bonus")
    H.ok(texts(M, "Daily reset  6 h 59 min") > 0, "daily reset countdown")
    H.ok(texts(M, "Weekly reset  ") > 0, "weekly reset")
    H.ok(texts(M, "Reroll one (1 free)") > 0)
end)

test("Activities: weekly task with a server claim state shows a Claim button", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("tasks")
    local row = ns.Activities.tasksPage.rows[2]
    H.ok(row.claim:IsShown(), "claimable weekly task")
    row.claim:Click()
    H.eq(H.lastIntent(M, "TCLAIM").payload, "202")
end)

test("Activities: reroll with a free reroll, then with a price after confirming", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("tasks")
    local P = ns.Activities.tasksPage
    P.reroll:Click()
    H.ok(P.cards[1].pick:IsShown(), "pick mode on open tasks")
    H.ok(not P.cards[3].pick:IsShown(), "claimable task cannot be rerolled")
    P.cards[1].pick:Click()
    H.eq(H.lastIntent(M, "TREROLL").payload, "101")
    H.send(M, "TASKS", { { 2, 0, 500000, "G" }, { 101, "D", 7, 0, 1, "C", 20, "", 0 } })
    P.reroll:Click()
    P.cards[1].pick:Click()
    local d = M.env.BleakholdDialog
    H.ok(d:IsShown(), "price confirmation")
    H.contains(d.text:GetText(), "50g")
    local before = H.countIntents(M, "TREROLL")
    M.Advance(1)
    d.ok:Click()
    H.eq(H.countIntents(M, "TREROLL"), before + 1)
end)

test("Dungeons: the Journey board (BHMP), Shards and first run (BOARD), the queue panel with the level band",
    function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    M.playerLevel = 34
    for _, msg in ipairs({ "H;3600;0;0;0;1", "J;1001;36;0;0;1;15;0;82;845;3;120;The Deadmines;",
        "J;1002;33;1;2;1;18;0;0;0;0;160;Shadowfang Keep;Bolstering" }) do
        ns.Legacy.Receive(msg)
    end
    ns.UI.Open("dungeons")
    M.Advance(0.5)
    local P = ns.Dungeons
    H.ok(texts(M, "Today's Board") > 0, "the old board")
    H.ok(texts(M, "Shadowfang Keep") > 0, "an offer")
    H.ok(texts(M, "160 Shards") > 0, "its reward")
    H.ok(texts(M, "double Shards") > 0, "first run of the day")
    H.ok(texts(M, "1,260") > 0, "Shards")
    P.rows[2]:Click()
    P.find:Click()
    H.eq(M.said[#M.said].msg, ".act start 1002 queue", "Find Group: the old command")
    H.send(M, "QUEUE", { { 2, 1, "D", 33, 1, 5, 30, 90, "", "", 29, 39 } })
    H.ok(texts(M, "Levels 29-39") > 0, "level band from the server")
    M.Advance(2)
    H.ok(texts(M, "Starts in 01:2") > 0, "the start counts down")
    P.queue.leave:Click()
    H.ok(H.lastIntent(M, "QLEAVE"), "leave")
end)

test("Keys: keystone, week's best, caches, mode intent, start inside its dungeon", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("keys")
    local P = ns.Keys
    H.ok(texts(M, "Halls of Lightning") > 0)
    H.ok(texts(M, "+9  Halls of Stone") > 0, "the week's best")
    H.ok(texts(M, "1 left, 2 carried over") > 0, "caches")
    H.ok(texts(M, "Season Dungeons") > 0 and texts(M, "This Week's Affixes") > 0, "the old page's sections")
    P.mythic:Click()
    H.eq(H.lastIntent(M, "KMODE").payload, "2")
    -- inside its dungeon with a group of 5, once the keystone opened the start (the server's BHMP O)
    M.inInstance, M.instanceType, M.zone = true, "party", "Halls of Lightning"
    M.SetGroup("PARTY", 5, true)
    ns.Legacy.Receive("O;602;8;1800;10;8;8;1,3,4;Halls of Lightning")
    P:Refresh()
    P.start:Click()
    H.ok(H.lastIntent(M, "KSTART"))
    H.send(M, "KEY", { { 2, 0 } })
    H.ok(texts(M, "No keystone") > 0)
    H.ok(not P.start:IsEnabled(), "no key, no start")
end)

test("Rift: run status, summary, buttons", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.Legacy.Receive("U;24;18;12;9;20;80;1;0;50")
    ns.UI.Open("rift")
    local P = ns.Rift
    P.enter:Click()
    H.eq(M.said[#M.said].msg, ".rift enter 21", "the old command, from the highest checkpoint")
    ns.UI.Open("rift")
    M.inInstance, M.instanceType = true, "party"      -- a floor is a dungeon
    H.send(M, "RIFT", FX.examples(M).RIFT)
    H.ok(texts(M, "Floor 7  -  Echo of Nefarian") > 0)
    H.eq(P.enter.label:GetText(), "Leave the Eclipse Rift", "in the run")
    M.Advance(2)
    H.ok(texts(M, "Time 02:0") > 0, "rift timer counts on")
    H.send(M, "RIFTE", FX.examples(M).RIFTE)
    H.ok(texts(M, "Reached floor 9") > 0, "summary")
    H.ok(texts(M, "20 Mythic Coins") > 0, "rewards")
    H.eq(texts(M, "Score"), 0, "no score shown when the server sends none")
    P.board:Click()
    H.ok(M.env.BleakholdLeaderboardsFrame:IsShown() and ns.Leaderboards.board == "R", "leaderboard link")
end)

test("Leaderboards: Raid Echoes podium: boss small, kill time big, date; medals sit on the names", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("leaderboards")
    M.Advance(0.3)
    local LB = ns.Leaderboards
    local when = 1792000000
    LB.tabs[3]:Click()
    H.eq(LB.board, "E")
    H.send(M, "LB", {
        { "E", 1, 0, 0, 1, 1 },
        { 1, 0, 0, 149, when, { { "Aldric", 1 }, { "Brenna", 2 } }, "Echo of Ragnaros" },
        { 2, 0, 0, 158, when, { { "Fenna", 3 } }, "Echo of Onyxia" },
    })
    local b = LB.podium.boxes[1]
    H.eq(b.dungeon:GetText(), "Echo of Ragnaros", "the boss, small")
    H.eq(b.value:GetText(), ns.U.Clock(149), "the kill time, big in the medal's colour")
    H.eq(b.time:GetText(), ns.U.Date("%d %b %Y", when), "the date")
    H.eq(LB.podium.boxes[2].value:GetText(), ns.U.Clock(158))
    for rank = 1, 3 do
        local box = LB.podium.boxes[rank]
        local point, rel, relPoint, _, y = box.medal:GetPoint(1)
        H.ok(point == "BOTTOM" and rel == box.group and relPoint == "TOP" and y == 4,
            "medal " .. rank .. " sits 4 above the names, the same on every step")
    end
end)

test("Collections: Later Ages lists every collection's count, a bar where there is a total", function(M, ns)
    M.companions.MOUNT = { { creatureID = 1, name = "Swift Gryphon", icon = "x" } }
    FX.connect(M, H)
    ns.UI.Open("collections")
    H.send(M, "COLL", { { 1, 412, "", 1214, 3771, 3, 48, { 3, 0, 0, 0, 0, 0, 0 }, { 8, 8, 5, 9, 5, 5, 8 } } })
    ns.Collections.ShowTab("later")
    local summary = ns.Collections.summary
    H.eq(summary.heading:GetText(), "Your Collection")
    local byKey = {}
    for _, st in ipairs(summary.stats) do
        byKey[st.key] = st
    end
    H.eq(#summary.stats, 6)
    H.eq(byKey.transmog.label:GetText(), "Transmog")
    H.eq(byKey.transmog.value:GetText(), "412")
    H.ok(not byKey.transmog.bar:IsShown(), "no total, no bar")
    H.eq(byKey.later.value:GetText(), "1,214 / 3,771")
    H.ok(byKey.later.bar:IsShown() and math.abs(byKey.later.bar:GetValue() - 1214 / 3771) < 1e-6, "the later looks' bar")
    H.eq(byKey.legacy.value:GetText(), "3 / 48")
    H.ok(byKey.legacy.bar:IsShown())
    H.eq(byKey.mounts.value:GetText(), "1")
    H.eq(byKey.pets.value:GetText(), "0")
    H.eq(byKey.animations.value:GetText(), tostring(#ns.Animations.List()))
    H.ok(texts(M, "Transmog (412)") > 0 and texts(M, "Looks of Later Ages (1,214 / 3,771)") > 0, "the tabs' counts")
end)

test("Collections: legacy set, class selector, try on, save outfit", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    M.items[16864] = { name = "Belt of Might" }
    M.items[16861] = { name = "Bracers of Might" }
    ns.UI.Open("collections")
    M.Advance(1)
    local CO = ns.Collections
    H.ok(texts(M, "Battlegear of Might") > 0)
    H.ok(texts(M, "Tier 1 - Molten Core era") > 0, "the tier and its era, in Title Case (never all caps)")
    H.ok(texts(M, "+6") > 0, "overflow shows the six classes past the first four")
    H.eq(#CO.main.more.items, 6)
    for _, it in ipairs(CO.main.more.items) do
        H.ok(it.text ~= "", "class name")
    end
    H.ok(texts(M, "3 of 8 collected") > 0)
    H.ok(texts(M, "Raid Echo: Ragnaros") > 0)
    H.ok(texts(M, "Blackrock Spire") > 0, "drops in")
    H.ok(texts(M, "Belt of Might") > 0, "cached item name")
    H.ok(texts(M, "Loading...") > 0, "uncached item")
    H.ok(not CO.modelCol.save:IsEnabled(), "outfit locked")
    -- try on a cached piece
    M.tryOn = {}
    CO.main.pieces[6]:Click()
    H.eq(M.tryOn[#M.tryOn], 16864)
    -- shift-click links it
    M.shift = true
    CO.main.pieces[6]:Click()
    H.contains(M.insertedLink, "Belt of Might")
    M.shift = false
    -- the server unlocks the outfit
    H.send(M, "SET", { { 1, 201, 1, "Battlegear of Might", 255, 1, { 16866, 16868, 16865, 16861, 16863, 16864, 16867, 16862 } } })
    H.ok(CO.modelCol.save:IsEnabled())
    CO.modelCol.save:Click()
    H.eq(H.lastIntent(M, "OUTFIT").payload, "201")
    -- class change asks for that set
    CO.main.classes[2]:Click()
    M.Advance(0.2)
    H.contains(H.lastIntent(M, "GET").payload, "SET,1,2")
    -- search filters the eras rail
    CO.searchBox:SetText("naxx")
    H.ok(texts(M, "Naxxramas 40") > 0, "matching era kept")
    H.eq(texts(M, "Molten Core, Zul'Gurub"), 0, "other eras filtered out")
    CO.searchBox:SetText("")
    H.ok(texts(M, "Molten Core, Zul'Gurub") > 0, "all eras back")
end)

test("Collections: mounts and pets are counted on the client", function(M, ns)
    M.companions.MOUNT = { { creatureID = 1, name = "Swift Gryphon", icon = "x" }, { creatureID = 2, name = "Bleak Steed", icon = "y" } }
    ns.UI.Open("collections")
    ns.Collections.ShowTab("mounts")
    H.ok(texts(M, "Swift Gryphon") > 0)
    H.ok(texts(M, "Mounts (2)") > 0, "the tab counts them")
    ns.Collections.ShowTab("pets")
    H.ok(texts(M, "No pets yet.") > 0)
end)

test("Collections: the picked mount's name and Summon / Dismiss, as the companion page", function(M, ns)
    M.companions.MOUNT = { { creatureID = 1, name = "Swift Gryphon", icon = "x" },
        { creatureID = 2, name = "Bleak Steed", icon = "y", active = 1 } }
    local called, dismissed = {}, {}
    M.env.CallCompanion = function(kind, i) called[#called + 1] = kind .. ":" .. i end
    M.env.DismissCompanion = function(kind) dismissed[#dismissed + 1] = kind end
    ns.UI.Open("collections")
    ns.Collections.ShowTab("mounts")
    local c = ns.Collections.companions
    H.eq(c.picked:GetText(), "Swift Gryphon", "the first one until another is clicked")
    H.eq(c.summon.label:GetText(), "Summon")
    c.summon:Click()
    H.eq(table.concat(called, ","), "MOUNT:1")
    local steed
    for _, r in ipairs({ c.scroll.child:GetChildren() }) do
        if r.name and r.name:GetText() == "Bleak Steed" and r:IsShown() then
            steed = r
        end
    end
    H.ok(steed, "a row per mount")
    steed:Click()
    H.eq(c.picked:GetText(), "Bleak Steed")
    H.eq(c.summon.label:GetText(), "Dismiss", "the one out is dismissed")
    c.summon:Click()
    H.eq(table.concat(dismissed, ","), "MOUNT")
    H.eq(#called, 1, "no second summon")
end)

test("ToggleCollectionsJournal opens Collections when no journal addon is loaded", function(M, ns)
    H.eq(type(M.env.ToggleCollectionsJournal), "function")
    M.env.ToggleCollectionsJournal()
    H.ok(M.env.BleakholdCollectionsFrame:IsShown())
end)

test("with AddicatUI or DragonUI loaded, their Pets & Mounts journal keeps the button", function(M, ns)
    H.eq(M.env.ToggleCollectionsJournal, nil, "AddicatUI opens its own journal, which can summon")
    ns.UI.Open("collections")
    H.ok(M.env.BleakholdCollectionsFrame:IsShown(), "Collections still opens from Bleakhold")
end, { before = function(M) M.addons.AddicatUI = true end })

test("ToggleCollectionsJournal of another addon is left alone", function(M, ns)
    H.eq(M.env.ToggleCollectionsJournal, M.preexisting)
end, { before = function(M) M.preexisting = function() end; M.env.ToggleCollectionsJournal = M.preexisting end })

test("Season: war effort, parts, rank, rewards, timeline, hand-in", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("season")
    H.ok(texts(M, "Season 1 - Bleak Dawn") > 0, "title from season definitions, in Title Case as stock titles")
    H.ok(texts(M, "Breach the Greymane Wall") > 0)
    H.ok(texts(M, "62%") > 0 and texts(M, "1,284 players have helped") > 0)
    H.eq(ns.Season.we.parts[1].bar.text:GetText(), "80%", "a goal's share inside its progress bar")
    H.ok(texts(M, "260 points to Captain of the Wall") > 0)
    H.ok(texts(M, "Earned") > 0 and texts(M, "7 / 20") > 0)
    H.ok(texts(M, "(now)") > 0, "current season marked")
    local seg = ns.Season.we.segments
    H.eq(seg[12]:GetValue(), 1, "12 full segments for 62%")
    H.ok(math.abs(seg[13]:GetValue() - 0.4) < 0.001, "the 13th two fifths full")
    H.eq(seg[14]:GetValue(), 0, "the rest empty")
    H.eq(seg[1]:GetStatusBarTexture():GetTexture(), "Interface\\TargetingFrame\\UI-StatusBar", "status-bar art")
    ns.Season.we.mine.handin:Click()
    local d = M.env.BleakholdDialog
    H.contains(d.text:GetText(), "3 spare")
    d.ok:Click()
    H.ok(H.lastIntent(M, "WEHANDIN"))
end)

test("Leaderboards: podium, table, paging, tabs, your best, firsts, site", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("leaderboards")
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "LBQ").payload, "K,1,0,0,1")
    local LB = ns.Leaderboards
    H.ok(texts(M, "+15") > 0, "podium first")
    H.ok(texts(M, "Rank 42  -  top 12% of the server") > 0, "your best")
    H.ok(texts(M, "Echo of Ragnaros defeated") > 0, "latest firsts")
    H.ok(texts(M, "1 / 3") > 0, "pages")
    H.ok(texts(M, "Hesper") > 0, "rank 4 in the table")
    LB.table.next:Click()
    H.eq(H.lastIntent(M, "LBQ").payload, "K,1,0,0,2")
    LB.tabs[2]:Click()
    H.eq(H.lastIntent(M, "LBQ").payload, "R,1,0,0,1")
    LB.filters.class:SetValue(2)
    H.eq(H.lastIntent(M, "LBQ").payload, "R,1,0,2,1")
    local firstsTab
    for _, t in ipairs(LB.tabs) do
        if t.key == "F" then firstsTab = t end
    end
    H.ok(firstsTab:IsShown(), "Server Firsts tab")
    H.ok(not LB.tabs[4]:IsShown() and LB.tabs[4].key == "A", "no Arena tab without feature bit 65536")
    H.eq(select(4, firstsTab:GetPoint(1)), 16 + 3 * LB.TAB_STEP, "Server Firsts takes the Arena tab's place")
    firstsTab:Click()
    H.ok(texts(M, "What") > 0, "server firsts table")
    LB.site:Click()
    local d = M.env.BleakholdDialog
    H.eq(d.edit:GetText(), "bleakhold.com")
end)
