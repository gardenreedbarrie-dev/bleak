-- The run the player is in, from the server's legacy BHMP messages (Legacy.lua): what our protocol's MP does not
-- carry (the Mythic Champions still needed, the battle res charges, each boss's role) and the affix stacks, the
-- Mythical Boon and the quake that only BHMP sends. Each line is built the way mod-bleakhold builds it:
-- bh_mplus.cpp SendFullState (S;mode;dungeon;level;timer;affixes;champsNeeded;hasForces;name, a B;i;role;done;name
-- per boss, SyncLine), SyncLine (T;elapsedMs;deaths;penaltySec;forcesDone;forcesNeeded;bres;champsKilled;state),
-- OnCreatureDeath's D;i, Complete's E, the affix ticks' Y;affix;stacks, V;boon;sec and Q;ms; bh_rift.cpp
-- SendRiftState for a Rift floor (S;4;dungeon;floor;0;;0;0;Eclipse Rift - place, B;1;3;done;boss, RiftSync).
-- S's dungeon is mod-bleakhold's own bh_mp_dungeon id (run->d->id), never our protocol's: the bridge sends
-- MplusUiId of it (the map id, or 100000 + the own id for a second wing), so the lines here carry small own ids
-- (4 for Halls of Lightning) beside our MPS's 602.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function bhmp(M, msg)
    M.FireEvent("CHAT_MSG_ADDON", "BHMP", msg, "WHISPER", M.playerName)
end

local function counter(ns, message)
    local c = { n = 0, tags = {} }
    ns.On(message, function(tag)
        c.n = c.n + 1
        c.tags[#c.tags + 1] = tag
    end)
    return c
end

-- A +15 Halls of Lightning: Fortified, Bolstering, Volcanic, Necrotic, then Mythic Champions and Mythical Boons
-- (AffixCsv: 13 and 14 from Champions.MinLevel); one champion needed (Champions.Required 1); Volkhan an extra boss.
local KEY_STATE = {
    "S;3;4;15;1800;1,3,10,8,13,14;1;1;Halls of Lightning",
    "B;1;1;1;General Bjarngrim",
    "B;2;2;0;Volkhan",
    "B;3;1;1;Ionar",
    "B;4;3;0;Loken",
    "T;1500000;3;15;88;100;2;0;2",
}

test("legacy run: S, B, T of a +15 key: the champions still needed and the battle res charges", function(M, ns)
    local L = ns.Legacy
    H.eq(L.Run(), nil, "no run before S")
    H.eq(L.ChampionsLeft(), nil)
    H.eq(L.BattleRes(), nil)
    for _, msg in ipairs(KEY_STATE) do
        H.eq(L.Receive(msg), msg:match("^(%a+)"), "accepted: " .. msg)
    end
    local run = L.Run()
    H.eq(run.mode, L.MODE.KEY)
    H.eq(run.ownDungeon, 4, "S's own id, kept apart")
    H.eq(run.dungeon, 602, "our protocol's id, by the key dungeon's name (here the built-in DEF D)")
    H.eq(run.level, 15); H.eq(run.timer, 1800); H.eq(run.name, "Halls of Lightning")
    H.eq(table.concat(run.affixes, ","), "1,3,10,8,13,14")
    H.eq(run.champsNeeded, 1); H.eq(run.hasForces, true)
    H.eq(#run.bosses, 4)
    H.eq(run.bosses[2].name, "Volkhan"); H.eq(run.bosses[2].role, L.ROLE.EXTRA); H.eq(run.bosses[2].done, false)
    H.eq(run.bosses[1].done, true)
    H.eq(run.elapsed, 1500000); H.eq(run.deaths, 3); H.eq(run.penalty, 15)
    H.eq(run.forcesDone, 88); H.eq(run.forcesNeeded, 100)
    H.eq(run.state, L.STATE.RUNNING)
    local left, killed, needed = L.ChampionsLeft()
    H.eq(left, 1, "the champion still alive")
    H.eq(killed, 0); H.eq(needed, 1)
    H.eq(L.BattleRes(), 2)
    -- Loken dies (D), the forces fill: the run still waits for the champion (CheckComplete)
    bhmp(M, "D;4")
    H.eq(run.bosses[4].done, true)
    bhmp(M, "T;1530000;3;15;100;100;2;0;2")
    H.eq(L.ChampionsLeft(), 1, "every boss and 100% forces, and still one champion to slay")
    -- a battle res (bh_mplus_bres: the T of OnSpellCast), the champion falls
    bhmp(M, "T;1540000;3;15;100;100;1;0;2")
    H.eq(L.BattleRes(), 1, "one charge spent")
    bhmp(M, "T;1550000;3;15;100;100;1;1;2")
    H.eq(L.ChampionsLeft(), 0, "none left")
    -- Complete: the last SyncLine (state 3), then E: the run is over
    bhmp(M, "T;1551000;3;15;100;100;1;1;3")
    H.eq(L.BattleRes(), nil, "no charges once the run is done")
    bhmp(M, "E;2;1551000;1800000;15;17;3;450;1;Halls of Lightning")
    H.eq(L.Run(), nil, "E ends the run")
    H.eq(L.ChampionsLeft(), nil)
end)

test("legacy run: a key below Champions.MinLevel needs no champion; its charges still count", function(M, ns)
    local L = ns.Legacy
    bhmp(M, "S;3;9;7;1800;1,3,10;0;1;Utgarde Pinnacle")
    H.eq(L.BattleRes(), nil, "charges unknown until the first T")
    bhmp(M, "C;10")
    bhmp(M, "T;0;0;0;0;120;1;0;1")
    H.eq(L.ChampionsLeft(), nil, "no champions in this key")
    H.eq(L.BattleRes(), 1, "the countdown already has the charges")
end)

test("legacy run: Mythic 0 ends with the final boss, a key never waits for an extra boss (boss roles)", function(M, ns)
    local L = ns.Legacy
    -- StartRun MODE_MYTHIC0: no level, no time limit, no affixes, no forces
    bhmp(M, "S;2;7;0;0;;0;0;Utgarde Keep")
    bhmp(M, "B;1;1;0;Prince Keleseth")
    bhmp(M, "B;2;1;0;Skarvald the Constructor")
    bhmp(M, "B;3;3;0;Ingvar the Plunderer")
    bhmp(M, "T;60000;0;0;0;0;1;0;2")
    local run = L.Run()
    H.eq(run.mode, L.MODE.MYTHIC0)
    H.eq(run.level, 0); H.eq(run.timer, 0, "untimed")
    H.eq(L.BossRole(3), L.ROLE.FINAL)
    H.eq(L.BossOptional(1), true, "Keleseth does not end a Mythic 0")
    H.eq(L.BossOptional(2), true)
    H.eq(L.BossOptional(3), false, "Ingvar does")
    H.eq(L.BossRole(9), nil, "no such boss")
    H.eq(L.BossOptional(9), nil)
    H.eq(L.ChampionsLeft(), nil)
    H.eq(L.BattleRes(), 1, "Mythic 0 has battle res charges too (Run::Mythic)")
    -- a key in the same dungeon kind: only BOSS_EXTRA is optional
    for _, msg in ipairs(KEY_STATE) do
        bhmp(M, msg)
    end
    H.eq(#L.Run().bosses, 4, "a new S starts a new run")
    H.eq(L.BossOptional(1), false)
    H.eq(L.BossOptional(2), true, "Volkhan, an extra boss")
    H.eq(L.BossOptional(4), false, "Loken, the final boss")
end)

test("legacy run: the run's tags fire LEGACY_RUN, not LEGACY (the pages do not redraw every 5 s)", function(M, ns)
    local L = ns.Legacy
    local pages, runs = counter(ns, "LEGACY"), counter(ns, "LEGACY_RUN")
    for _, msg in ipairs(KEY_STATE) do
        bhmp(M, msg)
    end
    bhmp(M, "D;2")
    bhmp(M, "Y;8;4")
    bhmp(M, "V;1;120")
    bhmp(M, "Q;2500")
    bhmp(M, "E;2;1551000;1800000;15;17;3;450;1;Halls of Lightning")
    H.eq(pages.n, 0, "no page redraw: " .. table.concat(pages.tags, ","))
    H.eq(table.concat(runs.tags, ","), "S,B,B,B,B,T,D,Y,V,Q,E")
    -- a Rift floor's S is the Rift page's too (the floor now); X both
    bhmp(M, "S;4;9;12;0;;0;0;Eclipse Rift - Utgarde Pinnacle")
    H.eq(L.rift.inFloor, 12, "the floor just entered")
    bhmp(M, "X")
    H.eq(table.concat(pages.tags, ","), "S,X")
    H.eq(runs.tags[#runs.tags - 1], "S"); H.eq(runs.tags[#runs.tags], "X")
    -- the page tags stay the pages'
    bhmp(M, "K;575;7;1800;Utgarde Pinnacle")
    H.eq(pages.tags[#pages.tags], "K")
    H.eq(runs.tags[#runs.tags], "X", "K is no run tag")
end)

test("legacy run: an Eclipse Rift floor is a run without charges or champions; X ends it", function(M, ns)
    local L = ns.Legacy
    bhmp(M, "S;4;9;12;0;;0;0;Eclipse Rift - Utgarde Pinnacle")
    bhmp(M, "B;1;3;0;King Ymiron")
    bhmp(M, "T;30000;1;0;0;0;0;0;2")
    local run = L.Run()
    H.eq(run.mode, L.MODE.RIFT)
    H.eq(run.level, 12, "the floor")
    H.eq(run.dungeon, nil, "a Rift floor is no key dungeon")
    H.eq(run.bosses[1].name, "King Ymiron")
    H.eq(L.BossOptional(1), false, "the floor's boss ends it")
    H.eq(L.BattleRes(), nil, "RiftSync's 0 is no charge count")
    H.eq(L.ChampionsLeft(), nil)
    bhmp(M, "D;1")
    H.eq(run.bosses[1].done, true)
    bhmp(M, "X")
    H.eq(L.Run(), nil)
    H.eq(L.rift.inFloor, 0)
end)

test("legacy run: B and D without an S, or a T of no live run, change nothing; a Heroic or a short T is not ours",
    function(M, ns)
    local L = ns.Legacy
    H.eq(L.Receive("B;1;1;0;General Bjarngrim"), "B", "a B is read")
    H.eq(L.Receive("D;1"), "D")
    H.eq(L.Receive("T;1551000;3;15;100;100;1;1;3"), "T", "a done run's T")
    H.eq(L.Receive("T;0;0;0;0;0;0;0;0"), "T", "an idle one's")
    H.eq(L.Run(), nil, "no run comes of them")
    -- a T of a run under way with no S (a /reload): a partial run, of no mode while our protocol has no run either
    H.eq(L.Receive("T;1500000;3;15;88;100;2;0;2"), "T")
    H.eq(L.Run().partial, true)
    H.eq(L.Run().mode, 0, "no MPS, no RIFT: unknown")
    H.eq(L.BattleRes(), nil, "no charges for a run of no known mode")
    H.eq(L.ChampionsLeft(), nil)
    H.eq(L.Receive("S;1;4;0;0;;0;0;Halls of Lightning"), nil, "the server sends no S for a Heroic")
    H.eq(L.Receive("T;1;2;3"), nil, "a T has 8 fields")
    -- fields are clamped
    bhmp(M, "S;3;4;400;1800;1,2,3,4,5,6,7,8,9,10;300;1;Halls|cffff0000 of\1 Lightning")
    local run = L.Run()
    H.eq(run.partial, nil, "an S replaces the partial run")
    H.eq(run.level, 400, "a Rift floor can be deep: the level is not cut to 99")
    H.eq(#run.affixes, 8, "eight affix ids at most")
    H.eq(run.champsNeeded, 99)
    H.ok(not run.name:find("\1", 1, true), "no control bytes")
    bhmp(M, "B;999;7;1;Too far")
    H.eq(run.bosses[64].role, 3, "index and role clamped")
    bhmp(M, "T;-5;x;0;0;0;500;500;9")
    H.eq(run.elapsed, 0); H.eq(run.deaths, 0); H.eq(run.bres, 99); H.eq(run.champsKilled, 99)
    H.eq(run.state, 3)
end)

test("legacy run: S arriving during the loading screen survives PLAYER_ENTERING_WORLD; the next loading ends it",
    function(M, ns)
    local L = ns.Legacy
    local runs = counter(ns, "LEGACY_RUN")
    -- OnPlayerEnterAll's SendFullState can come before the loading screen is gone
    for _, msg in ipairs(KEY_STATE) do
        bhmp(M, msg)
    end
    bhmp(M, "Y;8;4")
    M.FireEvent("PLAYER_ENTERING_WORLD")
    H.ok(L.Run() ~= nil, "the new instance's run is kept")
    H.eq(L.ChampionsLeft(), 1)
    local n = runs.n
    M.FireEvent("PLAYER_LEAVING_WORLD")
    H.eq(L.Run(), nil, "a loading screen ends it")
    H.eq(#L.AffixStacks(), 0, "the stacks too")
    H.eq(runs.n, n + 1, "the tracker is told")
    M.FireEvent("PLAYER_LEAVING_WORLD")
    H.eq(runs.n, n + 1, "once")
end)

test("legacy affixes: Y stacks with the server's effects, V the Boon and its time, Q the quake", function(M, ns)
    local L = ns.Legacy
    H.eq(#L.AffixStacks(), 0)
    bhmp(M, "Y;8;19")
    bhmp(M, "Y;6;3")
    bhmp(M, "Y;9;4")
    bhmp(M, "Y;18;2")
    bhmp(M, "Y;12;5")
    local s = L.AffixStacks()
    H.eq(#s, 4, "Quaking stacks nothing")
    H.eq(s[1].id, 6); H.eq(s[1].name, "Bursting"); H.eq(s[1].stacks, 3)
    H.eq(s[1].effect, "4.5% of your health each second", "1.5% a stack (AffixDamage 1.5f * burst)")
    H.eq(s[2].name, "Necrotic"); H.eq(s[2].effect, "-38% healing taken", "2% a stack")
    H.eq(s[3].name, "Grievous"); H.eq(s[3].effect, "4% health every 3 sec - heal above 90%")
    H.eq(s[4].name, "Pack Tactics")
    H.eq(s[4].effect, "2 allies over 10 yd away (-10% damage, +10% taken)")
    -- Necrotic comes at 1, 4, ... 43 (necro % 3 == 1) and never at its cap of 45: at 43 the player may be at the cap
    bhmp(M, "Y;8;40")
    H.eq(L.AffixStacks()[2].effect, "-80% healing taken")
    bhmp(M, "Y;8;43")
    H.eq(L.AffixStacks()[2].stacks, 43)
    H.eq(L.AffixStacks()[2].effect, "-86% to -90% healing taken", "the last count the server sends below the cap")
    -- once bleakserv sends the cap too
    bhmp(M, "Y;8;45")
    H.eq(L.AffixStacks()[2].effect, "-90% healing taken", "Necrotic stops at 90%")
    bhmp(M, "Y;6;30")
    H.eq(L.AffixStacks()[1].effect, "45% of your health each second")
    bhmp(M, "Y;18;12")
    H.eq(L.AffixStacks()[4].effect, "12 allies over 10 yd away (-50% damage, +60% taken)", "damage done at most -50%")
    bhmp(M, "Y;18;1")
    H.eq(L.AffixStacks()[4].effect, "1 ally over 10 yd away (-5% damage, +5% taken)")
    bhmp(M, "Y;8;0")
    bhmp(M, "Y;6;0")
    s = L.AffixStacks()
    H.eq(#s, 2, "0 takes a stack away")
    H.eq(s[1].name, "Grievous")
    -- the Boon: two minutes, faded on V;0;0 or when its time is up
    H.eq(L.Boon(), nil)
    bhmp(M, "V;2;120")
    local b = L.Boon()
    H.eq(b.id, 2); H.eq(b.name, "Boon of Vigor"); H.eq(b.effect, "+15% healing")
    H.eq(math.floor(b.left + 0.5), 120)
    M.Advance(30)
    H.eq(math.floor(L.Boon().left + 0.5), 90, "counts down")
    bhmp(M, "V;0;0")
    H.eq(L.Boon(), nil, "faded")
    bhmp(M, "V;3;120")
    H.eq(L.Boon().effect, "-10% damage taken")
    M.Advance(121)
    H.eq(L.Boon(), nil, "over without a V;0;0")
    -- the quake in 2.5 s
    H.eq(L.QuakeIn(), nil)
    bhmp(M, "Q;2500")
    H.ok(math.abs(L.QuakeIn() - 2.5) < 0.01)
    M.Advance(3)
    H.eq(L.QuakeIn(), nil, "past")
    -- X (out of the instance) clears them
    bhmp(M, "Y;9;4")
    bhmp(M, "V;1;120")
    bhmp(M, "X")
    H.eq(#L.AffixStacks(), 0)
    H.eq(L.Boon(), nil)
end)

test("legacy run: S's own dungeon id is never our protocol's; the key tracker takes the run by name, a second wing too",
    function(M, ns)
    local L, T = ns.Legacy, ns.KeyTracker
    FX.connect(M, H)
    M.inInstance, M.instanceType = true, "party"
    -- our MPS names map 602, S mod-bleakhold's own id 4 (bh_ui_bridge_map.cpp DungeonIds: MplusUiId(4) = 602)
    H.send(M, "MPS", { { 7001, 602, 15, { 1, 3, 4 }, 7, 0, 1800 } })
    H.send(M, "MP", { { 7001, 600000, 1800, 2, 10, 88, 100, 1, { 300 }, { 1260, 1440 }, 1 } })
    for _, msg in ipairs(KEY_STATE) do
        bhmp(M, msg)
    end
    local run = L.Run()
    H.eq(run.ownDungeon, 4)
    H.eq(run.dungeon, 602, "DEF D 602 is Halls of Lightning")
    H.ok(T.LegacyRun(ns.S.mplus, T.MODE_KEY) == run, "the tracker takes this run (champions, battle res, roles)")
    -- a second wing: our id 100000 + the own id, the map's id taken by the first wing
    H.send(M, "DEF", { { "D", 8 }, { 189, "Scarlet Monastery: Armory", 2, 30, 40, { "Herod" }, 1800 },
        { 100006, "Scarlet Monastery: Cathedral", 2, 30, 40, { "High Inquisitor Whitemane" }, 1800 } })
    H.send(M, "MPS", { { 7002, 100006, 8, { 1, 3, 4 }, 7, 0, 1800 } })
    bhmp(M, "S;3;6;8;1800;1,3,10;0;1;Scarlet Monastery: Cathedral")
    bhmp(M, "T;60000;0;0;10;100;1;0;2")
    run = L.Run()
    H.eq(run.ownDungeon, 6)
    H.eq(run.dungeon, 100006, "the Cathedral, not the Armory")
    H.ok(T.LegacyRun(ns.S.mplus, T.MODE_KEY) == run, "a second wing's run is taken too")
    H.eq(L.BattleRes(), 1)
    -- two key dungeons of one name: no id rather than a wrong one
    H.send(M, "DEF", { { "D", 9 }, { 100007, "Scarlet Monastery: Cathedral", 2, 30, 40, {}, 1800 } })
    H.eq(L.KeyDungeonId("Scarlet Monastery: Cathedral"), nil)
    H.eq(L.KeyDungeonId("Scarlet Monastery: Armory"), 189)
    H.eq(L.KeyDungeonId("The Deadmines"), nil, "a Journey dungeon has no time limit: no key dungeon")
    H.eq(L.KeyDungeonId(""), nil)
end)

test("legacy run: after a /reload (no S) the run's T keeps a partial run: battle res back, the rest unknown",
    function(M, ns)
    local L, T = ns.Legacy, ns.KeyTracker
    FX.connect(M, H)
    M.inInstance, M.instanceType = true, "party"
    -- a +15 under way: our MPS / MP come back with the handshake, BHMP sends only its T every 5 s
    H.send(M, "MPS", { { 7001, 602, 15, { 1, 3, 4 }, 7, 0, 1800 } })
    H.send(M, "MP", { { 7001, 600000, 1800, 2, 10, 88, 100, 1, { 300 }, { 1260, 1440 }, 1 } })
    H.eq(L.Run(), nil)
    bhmp(M, "T;1500000;3;15;88;100;2;0;2")
    local run = L.Run()
    H.eq(run.partial, true)
    H.eq(run.mode, L.MODE.KEY, "a key: MPS has a level")
    H.eq(L.BattleRes(), 2, "the charges are back")
    H.eq(L.ChampionsLeft(), nil, "this MPS lists no Mythic Champions (test_rift_reload_champions: one that does)")
    H.eq(L.BossRole(1), nil); H.eq(L.BossOptional(1), nil)
    H.eq(run.level, nil); H.eq(run.dungeon, nil)
    H.ok(T.LegacyRun(ns.S.mplus, T.MODE_KEY) == run, "the tracker takes it: its battle res line")
    bhmp(M, "D;4")
    H.eq(run.bosses[4].done, true)
    bhmp(M, "T;1505000;3;15;90;100;1;0;2")
    H.eq(L.BattleRes(), 1, "T goes on counting")
    -- the run's S (on the next entry; .act mplus does not send it until bleakserv's HandleMplus calls SendFullState)
    -- replaces it
    for _, msg in ipairs(KEY_STATE) do
        bhmp(M, msg)
    end
    H.eq(L.Run().partial, nil)
    H.eq(L.ChampionsLeft(), 1)
    -- a Mythic 0 (MPS level 0, untimed) and a Rift floor (RIFT running) after a /reload
    bhmp(M, "X")
    H.send(M, "MPS", { { 7003, 574, 0, {}, 7, 0, 0 } })
    bhmp(M, "T;60000;0;0;0;0;1;0;2")
    H.eq(L.Run().mode, L.MODE.MYTHIC0)
    H.eq(L.BattleRes(), 1)
    bhmp(M, "X")
    ns.S.mplus = nil
    H.send(M, "RIFT", { { 8001, 1, 7, 3, "Echo of Nefarian", 120000, 18, "", 42, 3, 3 } })
    bhmp(M, "T;30000;1;0;0;0;0;0;2")
    H.eq(L.Run().mode, L.MODE.RIFT)
    H.eq(L.BattleRes(), nil, "a Rift floor has no charges")
    -- the mode follows our protocol: MPS before its level is known (an MP alone) is no mode yet
    bhmp(M, "X")
    ns.S.rift = nil
    ns.S.mplus = { runId = 7004, dungeonId = 0, level = 0, timeLimitSec = 1800, affixes = {}, state = 1 }
    bhmp(M, "T;30000;0;0;0;0;2;0;2")
    H.eq(L.Run().mode, 0)
    ns.S.mplus.level = 12
    H.eq(L.Run().mode, L.MODE.KEY, "known as soon as MPS says")
end)

local function said(M, msg)
    local n = 0
    for _, s in ipairs(M.said) do
        if s.chatType == "SAY" and s.msg == msg then
            n = n + 1
        end
    end
    return n
end

test("legacy run: the handshake in a dungeon with no run from S (a /reload) asks for the state again", function(M, ns)
    M.inInstance, M.instanceType = true, "party"
    FX.connect(M, H)
    H.eq(said(M, ".act mplus"), 1, "W, the season list, the keystone, U and Z (the run's S not yet: HandleMplus)")
    H.eq(said(M, ".act journey"), 1, "the old window's request, whole")
end)

test("legacy run: no such request in the open world, in a battleground or with the run's S; a partial run asks",
    function(M, ns)
    local L = ns.Legacy
    FX.connect(M, H)
    H.eq(said(M, ".act mplus"), 0, "the open world")
    M.inInstance, M.instanceType = true, "pvp"
    ns.Fire("HELLO", ns.Comm.server)
    H.eq(said(M, ".act mplus"), 0, "a battleground")
    -- a login into the dungeon: OnPlayerEnterAll's S came before the handshake was answered
    M.instanceType = "party"
    L.Receive(KEY_STATE[1])
    ns.Fire("HELLO", ns.Comm.server)
    H.eq(said(M, ".act mplus"), 0, "the run is known")
    -- only the run's T since the /reload: still asked
    L.Receive("X")
    L.Receive("T;1500000;3;15;88;100;2;0;2")
    H.eq(L.Run().partial, true)
    ns.Fire("HELLO", ns.Comm.server)
    H.eq(said(M, ".act mplus"), 1, "a partial run lacks the boss roles")
end)
