-- The key tracker (KeyTracker.lua) beyond MPS / MP / MPE: from the server's legacy BHMP lines (Legacy.lua; sent to the
-- player as SendFullState's S, a B per boss, SyncLine's T, AffixNotices' Y and the boon's V) the Mythic Champions a
-- +14 / +15 key still needs (CheckComplete waits for them), the battle resurrections left, the boss roles, the
-- player's affix stacks and the group's boon; a Mythic 0 (MPS level 0, no time limit: untimed, only its final boss
-- ends it); an Eclipse Rift floor (RIFT, while no key run shows).
-- S names the dungeon by the server's own id (bh_mp_dungeon.id: 4 for Halls of Lightning here), MPS by the UI id (the
-- map id 602; bh_ui_bridge.cpp MplusUiId): the two never agree, as on a live server.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function bhmp(M, msg)
    M.FireEvent("CHAT_MSG_ADDON", "BHMP", msg, "WHISPER", M.playerName)
end

local function tracker(M)
    return M.env.BleakholdKeyTracker
end

-- A Halls of Lightning key at `level`, running for 10 minutes (no countdown), every boss down, forces full.
local function keyRun(M, level)
    FX.connect(M, H)
    H.send(M, "MPS", { { 7001, 602, level, { 1, 3, 4 }, 7, 0, 1800 } })
    H.send(M, "MP", { { 7001, 600000, 1800, 2, 10, 100, 100, 15, { 300, 600, 900, 1200 }, { 1260, 1440 }, 1 } })
end

local function yOf(region)
    local _, _, _, _, y = region:GetPoint(1)
    return y
end

local function tipText(M)
    return table.concat(M.env.GameTooltip.__lines or {}, "\n")
end

local function red(fs)
    local c = fs.__tcolor
    return c[1] > 0.9 and c[2] < 0.2 and c[3] < 0.2
end

test("tracker: a +14 key shows the Mythic Champions still needed under the forces, and the battle res left",
    function(M, ns)
    keyRun(M, 14)
    local t = tracker(M)
    H.send(M, "DEF", { { "A", 1 }, { 13, "Mythic Champions", "From +14: 2 Mythic Champions (4x health) guard the "
        .. "dungeon; 1 must fall to finish the key." } })
    H.ok(not t.champs:IsVisible() and not t.bres:IsVisible(), "nothing without the server's S and T")
    local h0 = t:GetHeight()
    bhmp(M, "S;3;4;14;1800;1,3,10,8,13,14;1;1;Halls of Lightning")
    bhmp(M, "T;600000;2;10;100;100;1;0;2")
    H.ok(t.champs:IsVisible(), "the champion line")
    H.eq(t.champs.name:GetText(), "Mythic Champions 0/1")
    H.eq(t.champs.state:GetText(), "-")
    H.ok(yOf(t.champs) < yOf(t.forces) - 13, "under the Enemy forces bar")
    H.eq(t:GetHeight(), h0 + 16, "the frame grows by a line")
    M.Hover(t.champs)
    H.contains(tipText(M), "1 must fall to finish the key", "the server's DEF A text")
    M.Hover(t.champs, false)
    H.ok(t.bres:IsVisible(), "battle res under the deaths")
    H.eq(t.bres.text:GetText(), "Battle res 1")
    H.ok(not red(t.bres.text), "dim while charges are left")
    H.ok(yOf(t.bres) < yOf(t.deaths), "under the deaths count")
    M.Hover(t.bres)
    H.contains(tipText(M), "Battle resurrections the group has left. More come with time, up to 5.")
    -- the champion falls: done; the last charge is used: red
    bhmp(M, "T;610000;2;10;100;100;0;1;2")
    H.eq(t.champs.name:GetText(), "Mythic Champions 1/1")
    H.eq(t.champs.state:GetText(), "done")
    local c = t.champs.name.__tcolor
    H.ok(c[1] < 0.6 and math.abs(c[1] - c[2]) < 0.01, "grey once enough have fallen")
    H.eq(t.bres.text:GetText(), "Battle res 0")
    H.ok(red(t.bres.text), "red at 0")
    -- the run is over: the summary has neither
    H.send(M, "MPE", FX.examples(M).MPE)
    H.ok(not t.champs:IsVisible() and not t.bres:IsVisible(), "not on the summary")
    H.eq(t.result:GetText(), "Timed!", "a key still ends Timed!")
end)

test("tracker: a key below the champions' level has no champion line; S of another level is not this run",
    function(M, ns)
    keyRun(M, 10)
    local t = tracker(M)
    bhmp(M, "S;3;4;10;1800;1,3,10,8;0;1;Halls of Lightning")
    bhmp(M, "T;600000;0;0;100;100;2;0;2")
    H.ok(not t.champs:IsVisible(), "champsNeeded 0")
    H.eq(t.bres.text:GetText(), "Battle res 2")
    -- an S of a +14 elsewhere (a stale run): nothing from it on this +10
    bhmp(M, "S;3;4;14;1800;1,3,10,8,13,14;1;1;Halls of Lightning")
    bhmp(M, "T;600000;0;0;100;100;2;0;2")
    H.ok(not t.champs:IsVisible() and not t.bres:IsVisible(), "only the run shown")
end)

test("tracker: a key's additional boss (B role 2) is a dimmed bonus", function(M, ns)
    FX.connect(M, H)
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 0, 1800 } })
    H.send(M, "MP", { { 7001, 300000, 1800, 0, 0, 20, 100, 1, { 280 }, { 1260, 1440 }, 1 } })
    local t = tracker(M)
    H.eq(t.bosses[2].state:GetText(), "-", "every boss an objective without roles")
    bhmp(M, "S;3;4;8;1800;1,3,4;0;1;Halls of Lightning")
    bhmp(M, "B;1;1;1;General Bjarngrim")
    bhmp(M, "B;2;2;0;Volkhan")
    bhmp(M, "B;3;1;0;Ionar")
    bhmp(M, "B;4;3;0;Loken")
    H.eq(t.bosses[1].state:GetText(), "done")
    H.eq(t.bosses[2].state:GetText(), "bonus")
    H.eq(t.bosses[3].state:GetText(), "-")
    H.eq(t.bosses[4].state:GetText(), "-", "the final boss of a key is an objective like the others")
    M.Hover(t.bosses[2])
    H.contains(tipText(M), "the key ends without it")
end)

test("tracker: the player's affix stacks and the group's boon, in the server's words, under the affixes",
    function(M, ns)
    keyRun(M, 10)
    local t = tracker(M)
    local h0 = t:GetHeight()
    local function shown(s)
        return #M.FindText(s, true) > 0
    end
    bhmp(M, "Y;8;20")
    H.ok(shown("Necrotic x20: -40% healing taken"), "the Necrotic line")
    H.eq(t:GetHeight(), h0 + 16, "one line more")
    H.ok(yOf(t.stacks[1]) < yOf(t.affixes), "under the affix names")
    local c = t.stacks[1].__tcolor
    H.ok(c[1] > 0.9 and c[2] > 0.4 and c[2] < 0.6 and c[3] < 0.3, "orange")
    bhmp(M, "Y;6;3")
    H.ok(shown("Bursting x3: 4.5% of your health each second"))
    bhmp(M, "Y;9;4")
    H.ok(shown("Grievous x4: 4% health every 3 sec - heal above 90%"))
    bhmp(M, "Y;18;2")
    H.ok(shown("Pack Tactics: 2 allies over 10 yd away (-10% damage, +10% taken)"))
    bhmp(M, "Y;8;0")
    H.ok(not shown("Necrotic"), "gone at 0")
    bhmp(M, "Y;6;0")
    bhmp(M, "Y;9;0")
    bhmp(M, "Y;18;0")
    H.eq(t:GetHeight(), h0, "back to the run's own lines")
    -- the boon counts down in the tracker's own update
    bhmp(M, "V;1;120")
    H.ok(shown("Boon of Power (+15% damage) 2:00"))
    M.Advance(18)
    H.ok(shown("Boon of Power (+15% damage) 1:42"), "18 s later")
    bhmp(M, "V;0;0")
    H.ok(not shown("Boon of"), "gone on V;0;0")
    H.eq(t:GetHeight(), h0)
    -- one that runs out on its own goes with it
    bhmp(M, "V;3;5")
    H.ok(shown("Boon of Warding (-10% damage taken) 0:05"))
    M.Advance(5.3)
    H.ok(not shown("Boon of"), "gone at its end")
    H.eq(t:GetHeight(), h0)
end)

test("tracker: six affixes at +14 wrap to two lines; the stack and boon lines go under them", function(M, ns)
    FX.connect(M, H)
    -- the bridge adds the Mythic Champions and the Mythical Boons to a +14's affixes (bh_ui_bridge.cpp ViewOf)
    H.send(M, "DEF", { { "A", 1 }, { 1, "Fortified", "" }, { 3, "Bolstering", "" }, { 4, "Raging", "" },
        { 8, "Necrotic", "" }, { 13, "Mythic Champions", "" }, { 14, "Mythical Boons", "" } })
    H.send(M, "MPS", { { 7001, 602, 14, { 1, 3, 4, 8, 13, 14 }, 7, 0, 1800 } })
    H.send(M, "MP", { { 7001, 600000, 1800, 2, 10, 40, 100, 1, { 300 }, { 1260, 1440 }, 1 } })
    local t = tracker(M)
    H.eq(t.affixes:GetText(), "Fortified, Bolstering, Raging, Necrotic, Mythic Champions, Mythical Boons")
    local lines = ns.KeyTracker.WrappedLines(t.affixes)
    H.ok(lines >= 2, "wider than the tracker: more than one line")
    local h0 = t:GetHeight()
    bhmp(M, "Y;8;45")
    bhmp(M, "V;2;100")
    H.eq(t.stacks[1]:GetText(), "Necrotic x45: -90% healing taken")
    H.eq(t.stacks[2]:GetText(), "Boon of Vigor (+15% healing) 1:40")
    H.ok(yOf(t.stacks[1]) <= yOf(t.affixes) - 16 * lines, "the first stack line under the affixes' last line")
    H.ok(yOf(t.stacks[2]) < yOf(t.stacks[1]), "the boon under it")
    H.eq(t:GetHeight(), h0 + 32, "the frame ends under both")
    -- one line of affixes keeps its old room (2 px under the rows, 18 px in all)
    H.send(M, "MPS", { { 7002, 602, 2, { 1 }, 7, 0, 1800 } })
    H.send(M, "MP", { { 7002, 600000, 1800, 2, 10, 40, 100, 1, { 300 }, { 1260, 1440 }, 1 } })
    H.eq(ns.KeyTracker.WrappedLines(t.affixes), 1)
    H.eq(yOf(t.stacks[1]), yOf(t.affixes) - 16, "right under the one line")
end)

test("tracker: a Mythic 0 is untimed, without a time bar; with no roles it says what ends it", function(M, ns)
    FX.connect(M, H)
    H.send(M, "MPS", { { 7002, 602, 0, "", "", 0, 0 } })
    H.send(M, "MP", { { 7002, 120000, 0, 0, 0, 0, 0, 0, "", "", 1 } })
    local t = tracker(M)
    H.ok(t:IsShown())
    H.eq(t.title:GetText(), "Halls of Lightning", "the dungeon, no level")
    H.eq(t.timer:GetText(), "02:00")
    H.eq(t.limit:GetText(), "Mythic 0 - untimed")
    H.ok(not t.timebar:IsVisible(), "no time bar")
    for _, tick in ipairs(t.ticks) do
        H.ok(not tick:IsVisible(), "no chest ticks")
    end
    local _, rel, relPoint = t.limit:GetPoint(1)
    H.ok(rel == t.timer and relPoint == "BOTTOMLEFT", "its own line under the clock, clear of the battle res")
    H.eq(yOf(t.bosses[1]), -68, "the bosses under it: no time bar")
    H.ok(t.note:IsVisible(), "without roles: what ends it")
    H.eq(t.note.name:GetText(), "Defeat the final boss to finish")
    H.ok(yOf(t.note) < yOf(t.bosses[4]), "under the bosses")
    -- the server's S and B: the final boss is the objective, the others optional
    bhmp(M, "S;2;4;0;0;;0;0;Halls of Lightning")
    bhmp(M, "B;1;1;0;General Bjarngrim")
    bhmp(M, "B;2;1;0;Volkhan")
    bhmp(M, "B;3;2;0;Ionar")
    bhmp(M, "B;4;3;0;Loken")
    bhmp(M, "T;120000;0;0;0;0;1;0;2")
    H.ok(not t.note:IsVisible(), "the roles say it")
    for i = 1, 3 do
        H.eq(t.bosses[i].state:GetText(), "optional", "boss " .. i)
        local c = t.bosses[i].name.__tcolor
        H.ok(c[1] < 0.6, "dimmed")
    end
    H.eq(t.bosses[4].state:GetText(), "-", "the final boss")
    H.eq(t.bosses[4].name:GetText(), "Loken")
    H.ok(t.bosses[4].name.__tcolor[1] > 0.75, "an objective")
    M.Hover(t.bosses[1])
    H.contains(tipText(M), "only the final boss ends a Mythic 0")
    H.ok(not t.champs:IsVisible(), "no champions in a Mythic 0")
    H.eq(t.bres.text:GetText(), "Battle res 1", "battle res counts in a Mythic 0 too")
    M.Advance(3.3)
    H.eq(t.timer:GetText(), "02:03", "counts on")
    H.eq(t.limit:GetText(), "Mythic 0 - untimed")
    -- the final boss falls: MpeOf sends a Mythic 0's end as "in time"; the first keystone comes with it
    H.send(M, "MPE", { { 7002, 1, 900000, 0, 599, 2, "" } })
    H.eq(t.result:GetText(), "Complete!")
    H.eq(t.limit:GetText(), "", "no limit")
    H.ok(#M.FindText("Keystone: Halls of Stone +2", true) > 0, "its first keystone")
end)

test("tracker: an Eclipse Rift floor: its floor, boss, the run's time and deaths; cleared; gone when it is over",
    function(M, ns)
    FX.connect(M, H)
    M.inInstance, M.instanceType = true, "party"
    local t = tracker(M)
    H.send(M, "RIFT", { { 8001, 1, 7, 3, "Echo of Nefarian", 120000, 18, "", 42, 1, 1 } })
    H.ok(t:IsShown(), "shown on a Rift floor")
    H.eq(t.title:GetText(), "Eclipse Rift - Floor 7")
    H.eq(t.deaths.text:GetText(), "1 death")
    H.eq(t.timer:GetText(), "02:00")
    H.eq(t.limit:GetText(), "", "no limit")
    H.ok(not t.timebar:IsVisible(), "no time bar")
    H.ok(t.bosses[1]:IsVisible())
    H.eq(t.bosses[1].name:GetText(), "Echo of Nefarian")
    H.ok(not t.bosses[2]:IsVisible(), "one boss a floor")
    H.eq(t.affixes:GetText(), "Solo  -  Best floor 18")
    M.Hover(t.deaths)
    H.contains(tipText(M), "Deaths in this run", "RIFT's deaths are the run's (riftRunDeaths)")
    M.Advance(3.3)
    H.eq(t.timer:GetText(), "02:03", "the run's clock counts on")
    -- cleared (no boss id): the server's words, in green
    H.send(M, "RIFT", { { 8001, 1, 7, "", "Cleared - step into the rift portal", 150000, 18, "", 42, 2, 3 } })
    H.ok(not t.bosses[1]:IsVisible(), "no boss line")
    H.ok(t.cleared:IsVisible())
    H.eq(t.cleared:GetText(), "Cleared - step into the rift portal")
    local c = t.cleared.__tcolor
    H.ok(c[2] > 0.9 and c[1] < 0.2, "green")
    H.eq(t.deaths.text:GetText(), "2 deaths")
    H.eq(t.affixes:GetText(), "Group of 3  -  Best floor 18")
    -- the run is over: the server's toast takes over
    H.send(M, "RIFTE", FX.examples(M).RIFTE)
    H.ok(not t:IsShown(), "hidden on RIFTE")
    -- a new run
    H.send(M, "RIFT", { { 8002, 1, 1, 5, "Edwin VanCleef", 0, 18, "", 42, 0, 1 } })
    H.ok(t:IsShown(), "the next run shows")
    H.eq(t.title:GetText(), "Eclipse Rift - Floor 1")
    -- out of the rift: no floor
    M.inInstance, M.instanceType = nil, nil
    bhmp(M, "X")
    H.ok(not t:IsShown(), "hidden without a floor")
end)

test("tracker: a key run wins over a Rift floor; no Rift tracker outside an instance", function(M, ns)
    FX.connect(M, H)
    local t = tracker(M)
    H.send(M, "RIFT", { { 8001, 1, 7, 3, "Echo of Nefarian", 120000, 18, "", 42, 1, 1 } })
    H.ok(not t:IsShown(), "a Rift floor is inside an instance")
    M.inInstance, M.instanceType = true, "party"
    M.EnterWorld()
    H.ok(t:IsShown(), "into the instance")
    H.eq(t.title:GetText(), "Eclipse Rift - Floor 7")
    H.send(M, "MPS", FX.examples(M).MPS)
    H.eq(t.title:GetText(), "Halls of Lightning +8", "the key")
    H.ok(t.timebar:IsVisible())
end)

test("tracker: the affixes are named by the server's ids, as the Keys page names them, before the server's DEF A",
    function(M, ns)
    FX.connect(M, H)
    -- no DEF A from the server: Data.lua's built-in one numbers 4 Volcanic and 5 Raging; MPS carries the server's ids
    -- (bh_mplus.cpp AffixName: 4 Raging, 10 Volcanic)
    H.eq(ns.Def("A", 4).name, "Volcanic", "the built-in table")
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 0, 1800 } })
    H.send(M, "MP", { { 7001, 600000, 1800, 2, 10, 40, 100, 1, { 300 }, { 1260, 1440 }, 1 } })
    local t = tracker(M)
    H.eq(t.affixes:GetText(), "Fortified, Bolstering, Raging")
    -- the same words as the Keys page and the keystone tooltip
    local K = ns.Keys
    H.eq(table.concat(K.AffixNames({ 1, 3, 4 }), ", "), t.affixes:GetText())
    -- a +15: the bridge adds the Mythic Champions and the Mythical Boons (13, 14); none of them "Affix #"
    H.send(M, "MPS", { { 7002, 602, 15, { 1, 3, 10, 8, 13, 14 }, 7, 0, 1800 } })
    H.send(M, "MP", { { 7002, 600000, 1800, 2, 10, 40, 100, 1, { 300 }, { 1260, 1440 }, 1 } })
    H.eq(t.affixes:GetText(), "Fortified, Bolstering, Volcanic, Necrotic, Mythic Champions, Mythical Boons")
    H.ok(not t.affixes:GetText():find("Affix #", 1, true))
    -- the sample run for placing the tracker keeps its own words
    H.send(M, "MP", { { 7002, 0, 1800, 0, 0, 0, 100, 0, "", "", 4 } })
    ns.KeyTracker.preview = true
    ns.KeyTracker.Refresh()
    H.eq(t.affixes:GetText(), "This week's affixes")
    ns.KeyTracker.preview = nil
end)

-- An older bridge sent every member the owner's key change as their own keyDelta (MpeOf: timed = the result, over time
-- -1, no new key); Complete() changes the owner's key only. The current one sends a member no keyDelta, only a Text
-- naming the owner's key.
test("tracker: a member's summary never shows the owner's key change as theirs; the owner's still does",
    function(M, ns)
    FX.connect(M, H)
    local t = tracker(M)
    -- the member's own Deadmines +3; the leader's Halls of Lightning +8 under way
    H.send(M, "KEY", { { 2, 36, 3, { 1, 3 }, 0, 0, "", 40, 0, 900001, 15, 7, 0 } })
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 0, 1800 } })
    H.send(M, "MP", { { 7001, 600000, 1800, 0, 0, 100, 100, 15, "", "", 1 } })
    M.Advance(0.3)
    H.eq(ns.KeyTracker.owner and ns.KeyTracker.owner.who, "other", "noted as someone else's run")
    -- over time, the older bridge's member end: keyDelta -1 and no new key
    H.send(M, "MPE", { { 7001, 0, 1953000, -1 }, { "C", 40 } })
    M.Advance(0.1)
    H.eq(t.result:GetText(), "Over time")
    for _, l in ipairs(t.resultLines) do
        if l:IsVisible() then
            H.ok(not (l:GetText() or ""):find("Keystone", 1, true), "no 'Keystone -1' for a member: " .. l:GetText())
        end
    end
    -- the current bridge's member end: no keyDelta, the owner's key named in a Text
    H.send(M, "MPS", { { 7002, 602, 8, { 1, 3, 4 }, 7, 0, 1800 } })
    H.send(M, "MP", { { 7002, 600000, 1800, 0, 0, 100, 100, 15, "", "", 1 } })
    M.Advance(0.3)
    H.send(M, "MPE", { { 7002, 0, 1953000 }, { "T", 1, "", "Ann's keystone dropped to +7" } })
    M.Advance(0.1)
    H.eq(t.resultLines[1]:GetText(), "+ Ann's keystone dropped to +7")
    -- the owner's own run (KEY of the run's dungeon and level): its change shows, with the new key
    H.send(M, "KEY", { { 3, 602, 8, { 1, 3, 4 }, 0, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    H.send(M, "MPS", { { 7003, 602, 8, { 1, 3, 4 }, 7, 0, 1800 } })
    H.send(M, "MP", { { 7003, 600000, 1800, 0, 0, 100, 100, 15, "", "", 1 } })
    M.Advance(0.3)
    H.eq(ns.KeyTracker.owner.who, "own")
    -- the owner's new key arrives before the end: the run stays the owner's
    H.send(M, "KEY", { { 4, 599, 10, { 1, 3, 4 }, 0, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    M.Advance(0.1)
    H.eq(ns.KeyTracker.owner.who, "own", "still the owner's run")
    H.send(M, "MPE", { { 7003, 1, 1453000, 2, 599, 10 } })
    M.Advance(0.1)
    H.contains(t.resultLines[1]:GetText(), "Keystone +2")
    H.contains(t.resultLines[1]:GetText(), "+10")
end)
