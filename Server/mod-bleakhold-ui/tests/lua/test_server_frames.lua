-- mod-bleakhold-ui: frames built by the C++ module (tests/cpp/bh_gen.cpp: the module's encoders and its
-- Endpoint for the handshake, revisions, SEQ and chunking) go through the addon's real receive path
-- (CHAT_MSG_ADDON -> Comm.lua -> State.lua). Every value set in bh_gen.cpp is checked here.
--
-- Run by the repository's Tools/UiLint/testrunner.lua (see ../run_tests.sh).
local BUILD = repo .. "/Server/mod-bleakhold-ui/tests/build/"

local function loadFrames(size)
    local chunk = assert(host_loadfile(BUILD .. "frames_" .. size .. ".lua"), "run bh_gen first (frames_" .. size .. ".lua)")
    return chunk()
end

local function feed(M, data)
    for _, chat in ipairs(data.frames) do
        local prefix, body = chat:match("^([^\t]*)\t(.*)$")
        H.eq(prefix, "BHs", "server prefix")
        H.ok(#chat <= 1004 and #body <= 1000, "frame body within the client's 1000 bytes")
        H.deliver(M, body, prefix)
    end
end

local function list(t)
    local out = {}
    for i, v in ipairs(t or {}) do out[i] = tostring(v) end
    return table.concat(out, ":")
end

for _, size in ipairs({ 1000, 251, 64 }) do
    test("C++ server frames (max body " .. size .. ") reach the addon's state intact", function(M, ns)
        local data = loadFrames(size)
        H.eq(data.maxBody, size)
        local C, S = ns.Comm, ns.S
        local events = {}
        for _, e in ipairs({ "HELLO", "TOAST", "ERR", "TASK_DONE", "MPLUS_START", "MPLUS_GO", "MPLUS_END", "RIFT_END", "QUEUE_PROPOSAL" }) do
            ns.On(e, function(x)
                events[e] = (events[e] or 0) + 1
                events[e .. ":arg"] = x
            end)
        end

        feed(M, data)
        M.Advance(1)

        -- transport: every frame accepted, every message complete, revisions continuous
        local drops = {}
        for k, v in pairs(C.stats.dropped) do drops[#drops + 1] = k .. "=" .. v end
        H.eq(#drops, 0, "dropped frames: " .. table.concat(drops, " "))
        H.eq(C.stats.framesIn, #data.frames, "frames in")
        H.eq(C.stats.gaps, 0, "revision gaps")
        H.eq(C.stats.unknown, 0, "unknown ops")
        H.eq(C.stats.dups, 0, "duplicates")
        H.eq(C.PendingChunks(), 0, "unfinished chunk buffers")
        if size < 1000 then
            H.ok(#data.frames > data.messages, "small frames: messages were chunked")
        end
        for topic, rev in pairs(data.revs) do
            if rev > 0 then
                H.eq(C.topicRev[topic], rev, "revision of " .. topic)
            end
        end

        -- HELLO
        H.eq(events.HELLO, 1)
        H.ok(C.ready, "connected")
        local sv = C.server
        H.eq(sv.proto, 1); H.eq(sv.minProto, 1); H.eq(sv.serverEpoch, 1792648725); H.eq(sv.utcOffsetMin, -300)
        H.eq(sv.dataVer, 4242); H.eq(sv.seasonId, 1); H.eq(sv.dailyReset, 1792674645); H.eq(sv.weeklyReset, 1792907925)
        H.eq(sv.realm, "Bleak;hold|Realm"); H.eq(sv.site, "bleakhold.com/a,b")
        H.ok(C.HasFeature(C.FEATURE.DBM_BY_SERVER) and C.HasFeature(C.FEATURE.SEASON) and C.HasFeature(C.FEATURE.LEADERBOARDS))
        H.ok(not C.HasFeature(C.FEATURE.RIFT_SCORE), "rift scoring off")

        -- DEF (complete set: Z stores the version)
        H.eq(ns.db.defsVer, 4242, "DEF Z stored the data version")
        H.eq(ns.DefName("A", 4), "Volcanic; 100% |cffff0000red|r")
        H.eq(ns.Def("A", 4).text, "Plumes: of flame~erupt, under %s players.")
        H.eq(ns.Def("A", 3).text, "When a non-boss enemy dies, its allies nearby grow stronger.")
        H.eq(ns.Def("A", 9).name, "Br\195\187lant")
        H.eq(ns.Def("A", 9).text, "UTF-8 \226\130\172 text and a bad byte ? here.", "invalid UTF-8 replaced by the server")
        H.eq(ns.Def("E", 7).tier, 7)
        H.eq(ns.Def("T", 2).text, "Defeat 20 enemies, inside a key.")
        H.eq(ns.Def("B", 1).title, "First Raid Lord Echo")
        H.eq(ns.Def("C", 5).name, "Chapter V - Northrend")
        H.eq(list(ns.Def("D", 1000).bosses), "Boss: one:Boss~two:Boss;three:Boss %four")
        H.eq(ns.Def("D", 1024).name, "Dungeon 24, the long name")
        H.eq(ns.Def("D", 1024).lvlMin, 34)
        H.eq(list(ns.Def("D", 602).bosses), "General Bjarngrim:Volkhan:Ionar:Loken")
        H.eq(ns.Def("D", 602).timeLimitSec, 1800)
        H.eq(list(ns.Def("L", 1).sources), "229:329:289:429:543")
        H.eq(ns.Def("L", 1).raids, "Molten Core, Zul'Gurub")
        H.eq(ns.Def("L", 1).total, 8)
        H.eq(ns.Def("S", 1).state, 1)
        H.eq(ns.Def("S", 2).state, 2)
        H.eq(ns.Def("K", 2).name, "Sergeant of the Wall")
        H.eq(ns.Def("W", 1).need, "\"of the Bleak Dawn\" at 500 points")
        H.eq(ns.Def("M", 0).text, "Where every keystone begins.")
        H.eq(ns.Def("M", 15).text, "The highest keystone level.")
        H.eq(ns.Def("X", 12).color, "7FBF7F")
        H.eq(ns.Def("X", 12).short, "GRV")
        H.eq(ns.ClassInfo(12).name, "Gravewarden")
        H.eq(ns.Def("R", 3).name, "Echo of Nefarian")

        -- WEEK (the second snapshot replaced the first)
        local w = S.week
        H.eq(w.keysTimed, 4); H.eq(w.echoes, 1); H.eq(w.riftBestFloor, 18); H.eq(w.coins, 2140); H.eq(w.coinsCap, 5500); H.eq(w.shards, 1260)

        -- ERA
        H.eq(S.era.eraId, 7); H.eq(S.era.nextEraId, 3); H.eq(list(S.era.affixes), "1:3:4"); H.eq(S.era.bonusId, 1); H.eq(S.era.bonusDone, true)

        -- TASKS + TASK delta
        local t = S.tasks
        H.eq(t.freeRerolls, 1); H.eq(t.rerollCost, 500000); H.eq(t.rerollCurrency, "C")
        H.eq(#t.daily, 3); H.eq(#t.weekly, 2)
        H.eq(t.byUid[102].have, 20, "TASK delta applied"); H.eq(t.byUid[102].state, 1)
        H.eq(events.TASK_DONE, 1, "task done toast event")
        H.eq(t.byUid[102].rewardKind, "I"); H.eq(t.byUid[102].rewardItemId, 40752); H.eq(t.byUid[102].rewardText, "1 Emblem of Heroism")
        H.eq(t.byUid[103].rewardKind, "S"); H.eq(t.byUid[103].state, 1)
        H.eq(t.byUid[201].kind, "W"); H.eq(t.byUid[201].title, "Echoes; of, the: era~"); H.eq(t.byUid[201].text, "Clear 3 keys | 100% in time")
        H.eq(t.byUid[201].rewardKind, "G"); H.eq(t.byUid[201].rewardAmount, 1234567); H.eq(t.byUid[201].rewardText, "Legacy Cache (Tier 6)")
        H.eq(t.byUid[202].state, 2)
        H.eq(t.byUid[101].title, nil, "empty override -> template text"); H.eq(ns.TaskTitle(t.byUid[101]), "Heroic hero")

        -- KEY
        local k = S.key
        H.eq(k.dungeonId, 602); H.ok(k.hasKey); H.eq(k.level, 8); H.eq(list(k.affixes), "1:3:4"); H.eq(k.mode, 2)
        H.eq(k.weeklyBest, 9); H.eq(k.weeklyBestDungeon, 599); H.eq(k.cachesReady, 1); H.eq(k.cachesBanked, 2)
        H.eq(k.itemId, 900001); H.eq(k.maxLevel, 20); H.eq(k.eraId, 7); H.eq(k.depleted, true)

        -- BOARD (100 dungeons: several chunks for the small frame sizes)
        local b = S.board
        H.eq(#b.dungeons, 100); H.eq(b.shards, 1260); H.eq(b.bountyId, 55); H.eq(b.bountyDungeon, 189); H.eq(b.bountyState, 2)
        H.eq(b.bountyReward, "50 Shards, doubled"); H.eq(b.firstRunBonus, true)
        H.eq(b.byId[2001].recordName, "Br\195\169nna%"); H.eq(b.byId[2002].recordName, "Aldric")
        H.eq(b.byId[2000].bestScore, nil, "missing field"); H.eq(b.byId[2001].bestScore, 10); H.eq(b.byId[2002].bestTier, 2)
        H.eq(b.byId[2007].locked, true); H.eq(b.byId[2008].locked, false); H.eq(b.byId[2099].recordScore, 9099)

        -- QUEUE (proposal)
        local q = S.queue
        H.eq(q.state, 2); H.eq(q.kind, "R"); H.eq(q.activityId, 0); H.eq(q.size, 5); H.eq(q.proposalId, 77); H.eq(q.timeoutSec, 40)
        H.eq(q.bandMin, 23); H.eq(q.bandMax, 28); H.eq(q.estWaitSec, nil)
        H.eq(#q.members, 3); H.eq(q.members[2].name, "Br\195\169nna"); H.eq(q.members[2].accepted, 2); H.eq(q.members[2].role, 2)
        H.eq(q.members[3].classId, 12); H.eq(q.members[3].accepted, 0); H.eq(q.members[3].level, 24)
        H.eq(events.QUEUE_PROPOSAL, 1)

        -- MPS, MP, MP, MPE
        local m = S.mplus
        H.eq(events.MPLUS_START, 1); H.eq(events.MPLUS_GO, 1); H.eq(events.MPLUS_END, 1)
        H.eq(m.runId, 7001); H.eq(m.dungeonId, 602); H.eq(m.level, 8); H.eq(list(m.affixes), "1:3:4"); H.eq(m.eraId, 7)
        H.eq(m.countdownMs, 10000); H.eq(m.timeLimitSec, 1800); H.eq(m.elapsedMs, 1122000); H.eq(m.deaths, 2); H.eq(m.deathPenaltySec, 10)
        H.eq(m.forcesCur, 64); H.eq(m.forcesMax, 100); H.eq(m.bossBits, 5); H.eq(list(m.bossKillSec), "300:0:900"); H.eq(list(m.chestSec), "1260:1440")
        H.eq(m.state, 2, "finished in time")
        H.eq(m.result.result, 1); H.eq(m.result.timeMs, 1453000); H.eq(m.result.keyDelta, -2); H.eq(m.result.newDungeonId, 599)
        H.eq(m.result.newLevel, 6); H.eq(m.result.score, 1840)
        H.eq(m.result.rewards[1], "Spoils chest, in your bags"); H.eq(m.result.rewards[2], "150 Mythic Coins"); H.eq(m.result.rewards[3], "2x item #40752")

        -- RIFT, RIFTE
        local r = S.rift
        H.eq(r.runId, 8001); H.eq(r.floor, 7); H.eq(r.bossId, 3); H.eq(r.bossName, "Echo of Nefarian"); H.eq(r.groupSize, 5); H.eq(r.deaths, 1)
        H.eq(r.state, 2, "over after RIFTE"); H.eq(events.RIFT_END, 1)
        H.eq(r.summary.floor, 21); H.eq(r.summary.score, 777); H.eq(r.summary.newBest, true); H.eq(r.summary.rank, 3)
        H.eq(r.summary.rewards[1], "20 Mythic Coins"); H.eq(r.bestFloor, 21, "new best floor")

        -- COLL
        local c = S.coll
        H.eq(c.transmogOwned, 412); H.eq(c.transmogTotal, nil); H.eq(c.laterOwned, 0); H.eq(c.laterTotal, 3771); H.eq(c.setsOwned, 3)
        H.eq(c.setsTotal, 48); H.eq(list(c.tierHave), "3:0:0:0:0:0:0"); H.eq(list(c.tierTotal), "8:8:5:9:5:5:8")

        -- SET
        local set = S.sets[ns.SetKey(1, 1)]
        H.eq(set.setId, 201); H.eq(set.name, "Battlegear of Might"); H.eq(set.collectedBits, 56); H.eq(set.outfitUnlocked, false)
        H.eq(list(set.items), "16866:16868:16865:16861:16863:16864:16867:16862"); H.eq(list(set.sources), "229:329:289:429:543")
        H.eq(set.lvlMin, 58); H.eq(set.lvlMax, 61); H.eq(set.echoBoss, "Ragnaros"); H.eq(set.note, "Drops in keys: and the Rift.")

        -- LIDX (1500 items given, 499 sent: the client splits at most 500 records per message) + LCOL delta
        local n = 0
        for _ in pairs(S.lidx) do n = n + 1 end
        H.eq(n, 499)
        H.eq(S.lidx[30000].collected, true); H.eq(S.lidx[30001].collected, true, "LCOL applied"); H.eq(S.lidx[30003].collected, false)
        H.eq(S.lidx[30006].tier, 7); H.eq(S.lidx[30008].setId, 201); H.eq(S.lidx[30498].setId, 200 + math.floor(498 / 8))
        H.eq(S.lidx[30499], nil, "the 500th item is not sent")

        -- SEASON
        local s = S.season
        H.eq(s.seasonId, 1); H.eq(s.wePermille, 620); H.eq(s.contributors, 1284); H.eq(s.points, 1240); H.eq(s.rankId, 2)
        H.eq(s.nextRankId, 3); H.eq(s.nextRankPoints, 260); H.eq(s.title, "Breach the Greymane Wall")
        H.eq(s.text, "Fill the bar together; 100% opens it."); H.eq(s.tokens, 3)
        H.eq(#s.parts, 3); H.eq(s.parts[2].name, "Bosses, Echoes"); H.eq(s.parts[2].permille, 550)
        H.eq(#s.rewards, 2); H.eq(s.rewards[1].earned, true); H.eq(s.rewards[2].stateText, "7 / 20")

        -- LB / LBME / FIRSTS
        local lk = S.lb.K
        H.eq(lk.page, 2); H.eq(lk.pages, 7); H.eq(lk.seasonId, 1); H.eq(#lk.rows, 10); H.eq(lk.rows[1].rank, 11)
        H.eq(#lk.rows[1].members, 5); H.eq(lk.rows[1].members[1].name, "Br\195\169nna"); H.eq(lk.rows[1].members[2].classId, 2)
        H.eq(#lk.rows[2].members, 1); H.eq(lk.rows[1].dungeonId, 602); H.eq(lk.rows[1].value, 15); H.eq(lk.rows[10].timeSec, -240)
        H.eq(lk.rows[1].date, 1792645125)
        H.eq(S.lb.R.rows[1].value, 30); H.eq(S.lb.R.rows[1].timeSec, 1500); H.eq(S.lb.R.rows[1].dungeonId, nil)
        H.eq(S.lb.E.rows[3].label, "Echo of Ragnaros"); H.eq(S.lb.E.rows[3].value, nil); H.eq(S.lb.E.rows[3].timeSec, 158)
        H.eq(S.lbme.K.rank, 42); H.eq(S.lbme.K.topPercent, 12); H.eq(S.lbme.K.value, 9); H.eq(S.lbme.K.dungeonId, 602)
        H.eq(S.lbme.K.timeSec, -154); H.eq(S.lbme.K.barPermille, 580); H.eq(S.lbme.E.label, "Echo of Ragnaros"); H.eq(S.lbme.E.value, nil)
        H.eq(#S.firsts, 2); H.eq(S.firsts[1].kind, "echo"); H.eq(S.firsts[1].who, "Ironvow (Aldric, Br\195\169nna)")
        H.eq(S.firsts[1].date, 1792562325); H.eq(S.firsts[2].text, "First timed +15")

        -- TOAST, ERR
        local toast = events["TOAST:arg"]
        H.eq(events.TOAST, 1); H.eq(toast.kind, "R"); H.eq(toast.title, "New record"); H.eq(toast.sub, "Halls of Lightning +8 in 24:13")
        H.eq(toast.target, "leaderboards")
        H.eq(S.err.op, "TCLAIM"); H.eq(S.err.seq, "1a"); H.eq(S.err.code, "not_claimable"); H.eq(S.err.text, "That task cannot be claimed yet, sorry.")
        H.eq(events.ERR, 1)
    end)
end

------------------------------------------------------------------------------------------------------
-- CAMPST (section 16) through the same receive path: every state, full and empty lists, empty fields, at the
-- server's frame sizes (Comm.BuildFrames cuts like the module's framer) and in raw cuts that split tuples,
-- delivered in order and out of order. The values follow docs/BleakholdProtocol.md section 16.
------------------------------------------------------------------------------------------------------
local CAMP_BITS = { [6] = 512 + 1024 + 2048 }

local campSeq = 500
local function campFrames(C, payload, size)
    campSeq = campSeq + 1
    return assert(C.BuildFrames("CAMPST", campSeq, payload, size))
end

local function deliverAll(M, frames, reverse)
    local from, to, step = 1, #frames, 1
    if reverse then from, to, step = #frames, 1, -1 end
    for i = from, to, step do
        H.deliver(M, frames[i])
    end
end

local function noDrops(C, what)
    local drops = {}
    for k, v in pairs(C.stats.dropped) do drops[#drops + 1] = k .. "=" .. v end
    H.eq(#drops, 0, what .. ": dropped frames: " .. table.concat(drops, " "))
    H.eq(C.stats.unknown, 0, what .. ": unknown ops")
    H.eq(C.PendingChunks(), 0, what .. ": unfinished chunk buffers")
end

local CAMP_RESTING = { "R", 45, 870, 1, 880, 0, 0, { { 164, 2, 1 }, { 171, 1, 0 } }, { { 185, 1 }, { 356, 3 }, { 773, 2 } }, "", 0, 0 }
local CAMP_SETTLED = { "C", 30, 600, 0, 0, 1500, 15, { { 164, 3, 0 }, { 197, 2, 1 }, { 999, 1, 0 } }, {}, 120, 1, 1, 9 }
local CAMP_LONG = { "C", 0, 600, 1, 0, 1500, 25, {}, {}, 0, 0, 1 }
for i = 1, 8 do CAMP_LONG[8][i] = { 100 + i, (i - 1) % 3 + 1, i % 2 } end
for i = 1, 16 do CAMP_LONG[9][i] = { 200 + i, (i - 1) % 3 + 1 } end

for _, size in ipairs({ 1000, 251, 64 }) do
    test("CAMPST frames (max body " .. size .. "): every state reaches the addon's state and the camp UI", function(M, ns)
        local C, S = ns.Comm, ns.S
        H.hello(M, CAMP_BITS)
        M.Advance(0.3)
        local settled = 0
        ns.On("CAMP_SETTLED", function() settled = settled + 1 end)
        local f, ind = M.env.BleakholdCampFrame, M.env.BleakholdCampStatus

        -- R: resting at the own fire, objects and places, no glide (empty field)
        local frames = campFrames(C, H.payload({ CAMP_RESTING }), size)
        for _, body in ipairs(frames) do H.ok(#body <= size, "frame within " .. size .. " bytes") end
        deliverAll(M, frames)
        M.Advance(0.3)
        noDrops(C, "resting")
        local c = S.camp
        H.eq(c.state, "R"); H.eq(c.settle, 45); H.eq(c.fire, 870); H.eq(c.mine, true); H.eq(c.cd, 880)
        H.eq(c.warmth, 0); H.eq(c.xp, 0); H.eq(c.glide, nil, "empty glide: cannot glide"); H.eq(c.repair, false); H.eq(c.fed, false)
        H.eq(c.gliding, 0, "no 13th field: no glide running")
        H.eq(#c.objs, 2); H.eq(c.objs[1].skill, 164); H.eq(c.objs[1].tier, 2); H.eq(c.objs[1].mine, true); H.eq(c.objs[2].mine, false)
        H.eq(#c.place, 3); H.eq(c.place[2].skill, 356); H.eq(c.place[2].tier, 3); H.eq(c.place[3].skill, 773)
        H.ok(f:IsShown(), "camp frame at the fire"); H.eq(f.state:GetText(), "Resting")
        H.eq(f.place[1].label:GetText(), "Place Cookpot"); H.eq(f.place[2].label:GetText(), "Place Rowboat")
        H.eq(f.place[3].label:GetText(), "Place Open Tome"); H.ok(not f.place[4]:IsShown())
        H.ok(f.packBtn:IsShown() and not f.repairBtn:IsShown(), "own fire, no anvil")
        H.ok(not ind:IsShown(), "no indicator at a fire")
        H.eq(settled, 0)

        -- C: settled at someone else's fire (settle ignored outside R), an unknown profession, glide, repair, fed
        deliverAll(M, campFrames(C, H.payload({ CAMP_SETTLED }), size), true)
        M.Advance(0.3)
        noDrops(C, "settled")
        c = S.camp
        H.eq(c.state, "C"); H.eq(c.settle, 0, "settle only with R"); H.eq(c.mine, false); H.eq(c.warmth, 1500); H.eq(c.xp, 15)
        H.eq(c.glide, 120); H.eq(c.repair, true); H.eq(c.fed, true); H.eq(#c.place, 0); H.eq(c.objs[3].skill, 999)
        H.eq(c.gliding, 9, "gliding (Walk on Air) in the 13th field")
        H.eq(settled, 1, "settled once")
        H.eq(f.state:GetText(), "Camping"); H.ok(f.repairBtn:IsShown() and not f.packBtn:IsShown())
        H.ok(not f.place[1]:IsShown(), "nothing to place"); H.ok(f.objs[3]:IsShown(), "unknown profession still drawn")
        H.contains(f.warmth:GetText(), "+15% XP")

        -- the longest lists the server sends (8 objects, 16 places): chunked at the small sizes
        local longPayload = H.payload({ CAMP_LONG })
        local long = campFrames(C, longPayload, size)
        if #longPayload > size - 20 then H.ok(#long > 1, "the long state is chunked at " .. size) end
        deliverAll(M, long)
        M.Advance(0.3)
        noDrops(C, "long")
        H.eq(#S.camp.objs, 8); H.eq(#S.camp.place, 16); H.eq(S.camp.place[16].skill, 216); H.eq(S.camp.xp, 25)
        H.ok(f.objs[8]:IsShown(), "eight icons"); H.ok(f.place[6]:IsShown(), "six place buttons drawn")
        H.eq(settled, 1, "still settled: no second toast")

        -- N with only warmth and xp, every other field empty: the indicator replaces the frame
        deliverAll(M, campFrames(C, "N,,,,,600,10,,,,,", size))
        M.Advance(0.6)
        noDrops(C, "away")
        c = S.camp
        H.eq(c.state, "N"); H.eq(c.fire, 0); H.eq(c.mine, false); H.eq(c.cd, 0); H.eq(c.warmth, 600); H.eq(c.glide, nil)
        H.eq(#c.objs, 0); H.eq(#c.place, 0)
        H.ok(not f:IsShown(), "frame hidden away from the fire"); H.ok(ind:IsShown(), "warmth indicator")
        H.contains(ind.text:GetText(), "+10% XP")
        M.Advance(30)
        H.contains(ind.text:GetText(), "09:", "warmth counts down locally")

        -- N with nothing: everything hides
        deliverAll(M, campFrames(C, "N", size))
        M.Advance(0.6)
        H.ok(not f:IsShown() and not ind:IsShown(), "nothing shown")
    end)
end

test("CAMPST in raw cuts (inside tuples and lists), duplicated and out of order", function(M, ns)
    local C, S = ns.Comm, ns.S
    H.hello(M, CAMP_BITS)
    M.Advance(0.3)
    local payload = H.payload({ CAMP_RESTING })
    for _, chunk in ipairs({ 1, 3, 7 }) do
        local frames = H.frames("CAMPST", payload, chunk)
        H.ok(#frames > 5, "cut into many parts")
        -- every second part first, then all of them (duplicates are ignored)
        for i = 2, #frames, 2 do H.deliver(M, frames[i]) end
        for i = #frames, 1, -1 do H.deliver(M, frames[i]) end
        M.Advance(0.2)
        noDrops(C, "chunk " .. chunk)
        H.eq(S.camp.state, "R"); H.eq(#S.camp.objs, 2); H.eq(#S.camp.place, 3); H.eq(S.camp.place[3].tier, 2)
        S.camp = nil
    end
    H.ok(C.stats.dups > 0, "duplicate parts counted")
end)

test("CAMPST frames produced by the C++ module (bh_gen) parse into a camp state", function(M, ns)
    local data = loadFrames(1000)
    local any = false
    for _, chat in ipairs(data.frames) do
        if chat:find("^BHs\t1 CAMPST ") then any = true end
    end
    if not any then
        print("  (bh_gen.cpp sends no CAMPST yet: nothing to check here)")
        return
    end
    for _, chat in ipairs(data.frames) do
        local prefix, body = chat:match("^([^\t]*)\t(.*)$")
        H.deliver(M, body, prefix)
    end
    M.Advance(0.5)
    noDrops(ns.Comm, "bh_gen")
    local c = ns.S.camp
    H.ok(c and (c.state == "N" or c.state == "R" or c.state == "C"), "a camp state from the C++ encoder")
    -- the last CAMPST of bh_gen.cpp: settled (settle is sent as 0 outside R), three objects, nothing to place
    H.eq(c.state, "C"); H.eq(c.settle, 0); H.eq(c.fire, 700); H.eq(c.mine, true); H.eq(c.cd, 880); H.eq(c.warmth, 1800)
    H.eq(c.xp, 15); H.eq(#c.objs, 3); H.eq(#c.place, 0); H.eq(c.glide, 95); H.eq(c.repair, true); H.eq(c.fed, true)
    H.eq(c.gliding, 7, "the glide that runs now")
    H.eq(c.objs[1].skill, 164); H.eq(c.objs[1].tier, 2); H.eq(c.objs[1].mine, true)
    H.eq(c.objs[3].skill, 197); H.eq(c.objs[3].tier, 3); H.eq(c.objs[3].mine, false)
end)

------------------------------------------------------------------------------------------------------
-- Bleakhold Royale (section 17): the C++ module's Royale session (bh_gen.cpp `royale`: QUEUE kind B, ROYS ROYM ROYO
-- ROYK ROYV ROYE) through the addon's transport at every frame size. The Royale HUD checks the values
-- (Tools/UiLint/tests/test_royale.lua); here every frame must be accepted and every message reassembled, whether or
-- not the addon has a handler for the op yet.
------------------------------------------------------------------------------------------------------
for _, size in ipairs({ 1000, 251, 64 }) do
    test("C++ Royale frames (max body " .. size .. ") pass the addon's transport", function(M, ns)
        local data = loadFrames(size).royale
        H.ok(data and #data.frames >= data.messages and data.messages >= 20, "bh_gen wrote the Royale session")
        local C = ns.Comm
        -- inside a battleground, so the kill announcer plays its BGANN lines
        M.inInstance, M.instanceType = true, "pvp"
        local played, announced = {}, {}
        M.env.PlaySoundFile = function(path) played[#played + 1] = path end
        ns.On("BG_ANNOUNCE", function(a) announced[#announced + 1] = (a.multi or "-") .. (a.streak or "-") end)
        feed(M, data)
        M.Advance(1)
        local drops = {}
        for k, v in pairs(C.stats.dropped) do drops[#drops + 1] = k .. "=" .. v end
        H.eq(#drops, 0, "dropped frames: " .. table.concat(drops, " "))
        H.eq(C.stats.framesIn, #data.frames, "frames in")
        H.eq(C.stats.gaps, 0, "revision gaps")
        H.eq(C.PendingChunks(), 0, "unfinished chunk buffers")
        H.eq(C.topicRev.QUEUE, data.revs.QUEUE, "revision of QUEUE")
        if size < 1000 then
            H.ok(#data.frames > data.messages, "small frames: messages were chunked")
        end
        H.ok(C.ready, "connected")
        H.ok(C.HasFeature(4096), "HELLO feature bit 4096: Bleakhold Royale live")
        H.eq(C.stats.unknown, 0, "the addon handles every Royale op")
        H.eq(ns.S.err.op, "GLIDE"); H.eq(ns.S.err.code, "glide_here"); H.eq(ns.S.err.seq, "c")
        H.eq(ns.S.err.shown, "You cannot glide here.")
        -- QUEUE kind B: the last one says "not queued"
        local S = ns.S
        H.eq(S.queue.state, 0); H.eq(S.queue.kind, "B")
        -- ROYM: the frame and the places (crate spots and final sites are never sent)
        local map = S.royaleMap
        H.eq(map.mapId, 901); H.eq(map.minX, -1066); H.eq(map.maxY, 533); H.eq(map.lobbyX, 455); H.eq(map.lobbyR, 32)
        H.eq(map.boundHalf, 750); H.eq(map.centerY, -267); H.eq(#map.pois, 14)
        H.eq(map.pois[1].name, "The Bleak Hold"); H.eq(map.pois[1].r, 88); H.eq(map.pois[11].kind, "C")
        H.eq(map.pois[13].r, 0); H.ok(#map.pois[13].name <= 40, "place names at most 40 bytes")
        H.eq(map.pois[13].name:sub(1, 33), "Pit Bridge; the third, crossing: ", "separators unescaped")
        H.eq(map.pois[14].kind, "Y"); H.eq(map.pois[14].name, "The Overlook")
        -- ROYS: the last one (the victory hold, watching)
        local m = S.royale
        H.eq(m.matchId, 7001); H.eq(m.phase, 5); H.eq(m.phaseMsLeft, 12000); H.eq(m.alive, 1); H.eq(m.total, 24)
        H.eq(m.me, 3); H.eq(m.placement, 12); H.eq(m.pinX, 104); H.eq(m.pinY, 96); H.eq(m.stage, 1)
        H.eq(m.curR, 1080); H.eq(m.nextX, -150); H.eq(m.nextY, -310); H.eq(m.nextR, 520)
        H.eq(m.shrinkStartMs, 0); H.eq(m.shrinkEndMs, 170000); H.eq(m.dmgPermille, 10)
        H.eq(m.watchName, "Aldric Stormwind"); H.eq(m.myX, nil); H.eq(m.myY, nil); H.eq(m.stages, 6)
        -- ROYO: the full list, then the change (the supply drop opened)
        local o = S.royaleObjects
        H.eq(o.matchId, 7001); H.eq(#o.list, 11)
        H.eq(o.byId[1].kind, "S"); H.eq(o.byId[1].state, 2); H.eq(o.byId[1].msLeft, 61000)
        H.eq(o.byId[2].state, 1); H.eq(o.byId[2].msLeft, nil)
        H.eq(o.byId[10].kind, "B"); H.eq(o.byId[10].subtype, 2); H.eq(o.byId[10].x, 130); H.eq(o.byId[10].y, -260)
        H.eq(o.byId[20].kind, "D"); H.eq(o.byId[20].state, 4); H.eq(o.byId[20].msLeft, nil)
        -- ROYK: the triple kill, then the storm with nobody credited (no announcement)
        local feed = S.royaleFeed
        H.eq(#feed, 2)
        H.eq(feed[1].killer, "Aldric Stormwind"); H.eq(feed[1].killerClassId, 1); H.eq(feed[1].victim, "Br\195\169nna")
        H.eq(feed[1].victimClassId, 8); H.eq(feed[1].cause, "P"); H.eq(feed[1].aliveAfter, 23);
        H.eq(feed[1].killerKills, 3)
        H.eq(feed[1].announce, nil, "ROYK announce is superseded by BGANN")
        H.eq(feed[2].killer, nil); H.eq(feed[2].victim, "Corwin"); H.eq(feed[2].victimClassId, 12);
        H.eq(feed[2].cause, "S")
        H.eq(feed[2].announce, nil)
        -- BGANN (section 18): the triple kill with its killing spree, an ultra kill, a long name with holy shit
        H.ok(C.HasFeature(8192), "HELLO feature bit 8192: the kill announcer live")
        H.eq(table.concat(announced, " "), "TS U- -H")
        local a = S.bgAnnounce
        H.eq(a.killer, "Garrick Stormwind, the; bold|one~of:many and the"); H.eq(#a.killer, 48)
        H.eq(a.killerClassId, 4); H.eq(a.victim, "Corwin"); H.eq(a.victimClassId, 12); H.eq(a.multi, nil)
        H.eq(a.streak, "H")
        H.eq(played[1], "Interface\\AddOns\\Bleakhold\\Sounds\\Announcer\\male\\triplekill.wav", "the multi-kill first")
        -- ROYV: the last is the winner
        H.eq(S.royaleEvent.kind, "W"); H.eq(S.royaleEvent.value, 7); H.eq(S.royaleEvent.name, "Dalia")
        -- ROYE: sent again at the end with the winner; the last counts
        local r = S.royaleResult
        H.eq(r.matchId, 7001); H.eq(r.placement, 12); H.eq(r.total, 24); H.eq(r.kills, 1); H.eq(r.damage, 18400)
        H.eq(r.healing, 2100); H.eq(r.survivedSec, 214); H.eq(r.rewarded, true)
        H.eq(r.winnerName, "Dalia"); H.eq(r.winnerClassId, 11); H.eq(r.winnerKills, 7)
        H.eq(#r.rewards, 3)
        H.eq(r.rewards[1].line, "70 Honor - Placement"); H.eq(r.rewards[2].line, "25 Honor - 1 elimination")
        H.eq(r.rewards[3].line, "5 Shards")
    end)
end

------------------------------------------------------------------------------------------------------
-- World PvP and War Mode (section 19): the C++ module's War session (bh_gen.cpp `wpvp`: HELLO with bits 16384 and
-- 32768, WMST, ERR wm_place, WPEV of every kind, WPMAP, WPZ, WPCAP, WANTED) through the addon's transport and State at
-- every frame size. Every value bh_gen.cpp sets is checked; the states between are caught as they arrive.
------------------------------------------------------------------------------------------------------
for _, size in ipairs({ 1000, 251, 64 }) do
    test("C++ World PvP frames (max body " .. size .. ") reach the addon's War Mode state", function(M, ns)
        local data = loadFrames(size).wpvp
        H.ok(data and #data.frames >= data.messages and data.messages >= 26, "bh_gen wrote the World PvP session")
        local C, S = ns.Comm, ns.S
        local seen = { WMST = {}, WPZ = {}, WPCAP = {}, WANTED = {}, WPMAP = {} }
        local owners = {}    -- the outposts' owners as each WPZ brought them (a WPCAP moves them on afterwards)
        ns.On("STATE", function(topic)
            local now = ({ WMST = S.warMode, WPZ = S.wpZone, WPCAP = S.wpCap, WANTED = S.wanted,
                WPMAP = S.wpMap })[topic]
            if seen[topic] and now then
                local list = seen[topic]
                if list[#list] ~= now then
                    list[#list + 1] = now
                    if topic == "WPZ" then
                        local o = {}
                        for i, obj in ipairs(now.objectives) do o[i] = obj.owner .. obj.state end
                        owners[#list] = table.concat(o, " ")
                    end
                end
            end
        end)
        local events = {}
        ns.On("WAR_EVENT", function(e) events[#events + 1] = e end)
        feed(M, data)
        M.Advance(1)
        local drops = {}
        for k, v in pairs(C.stats.dropped) do drops[#drops + 1] = k .. "=" .. v end
        H.eq(#drops, 0, "dropped frames: " .. table.concat(drops, " "))
        H.eq(C.stats.framesIn, #data.frames, "frames in")
        H.eq(C.stats.unknown, 0, "the addon handles every section 19 op")
        H.eq(C.PendingChunks(), 0, "unfinished chunk buffers")
        if size == 64 then
            H.ok(#data.frames > data.messages, "small frames: messages were chunked")
        end
        H.ok(C.ready and C.HasFeature(16384) and C.HasFeature(32768) and C.HasFeature(8), "HELLO bits 8, 16384, 32768")
        H.ok(ns.WarMode.Live() and ns.WarMode.ObjectivesLive())
        -- WMST: off and blocked, on, then the streak and the hunt
        H.eq(#seen.WMST, 3)
        local w1, w2, w3 = seen.WMST[1], seen.WMST[2], seen.WMST[3]
        H.eq(w1.on, false); H.eq(w1.block, "wm_busy"); H.eq(w1.minLevel, 20); H.eq(w1.xpPct, 0); H.eq(w1.honorPct, 10)
        H.eq(w1.shardPct, 0); H.eq(w1.underdogPct, 8); H.eq(w1.underdogTeam, "H"); H.eq(w1.wmAlliance, 31)
        H.eq(w1.wmHorde, 22); H.eq(w1.bonusHonorCap, 3720); H.eq(w1.shardsCap, 60); H.eq(w1.bestStreak, 7)
        H.eq(w1.kills, 118); H.eq(w1.deaths, 96); H.eq(w1.cooldownSec, 0); H.eq(w1.wantedState, 0)
        H.eq(w2.on, true); H.eq(w2.block, nil); H.eq(w2.cooldownSec, 900)
        H.eq(w3.on, true); H.eq(w3.cooldownSec, 512); H.eq(w3.streak, 5); H.eq(w3.wantedState, 1)
        H.eq(w3.wantedSec, 900)
        H.eq(w3.bountyHonor, 248); H.eq(w3.todayBonusHonor, 412); H.eq(w3.todayShards, 6); H.eq(w3.kills, 123)
        H.eq(w3.deaths, 96); H.eq(S.warMode, w3)
        -- ERR wm_place for WARMODE
        H.eq(S.err.op, "WARMODE"); H.eq(S.err.seq, "3"); H.eq(S.err.code, "wm_place")
        H.eq(S.err.shown, "War Mode can only be changed in an inn or a city.")
        -- WPMAP: the Front running, then its ceasefire
        H.eq(#seen.WPMAP, 2)
        local m = seen.WPMAP[1]
        H.eq(m.frontZone, 2817); H.eq(m.frontState, 1); H.eq(m.secondsLeft, 7200); H.eq(m.nextZone, 66)
        H.eq(m.nextStartsSec, 7800); H.eq(m.levelZone, 267); H.eq(m.levelState, 2); H.eq(m.levelSecondsLeft, 300)
        H.eq(#m.zones, 4); H.eq(#m.points, 6)
        local z1, z2, z3, z4 = m.zones[1], m.zones[2], m.zones[3], m.zones[4]
        H.eq(z1.zoneId, 2817); H.eq(z1.kind, "F"); H.eq(z1.heldA, 2); H.eq(z1.heldH, 0); H.eq(z1.neutral, 1)
        H.eq(z1.levelMin, 80); H.eq(z1.levelMax, 80); H.eq(z1.state, 1); H.eq(#z1.points, 3)
        H.eq(z2.zoneId, 267); H.eq(z2.kind, "L"); H.eq(z2.neutral, 3); H.eq(z2.levelMin, 20); H.eq(z2.levelMax, 35)
        H.eq(z2.state, 2)
        H.eq(z3.zoneId, 3483); H.eq(z3.kind, "S"); H.eq(z3.heldA, 2); H.eq(z3.heldH, 1); H.eq(z3.levelMin, nil)
        H.eq(z3.state, 1); H.eq(#z3.points, 3)
        H.eq(z4.zoneId, 4197); H.eq(z4.kind, "W"); H.eq(z4.heldH, 1); H.eq(z4.levelMax, nil)
        H.eq(m.points[2].objId, 2); H.eq(m.points[2].owner, "N"); H.eq(m.points[2].state, 6)
        H.eq(m.points[4].objId, 101); H.eq(m.points[6].owner, "H"); H.eq(m.points[6].state, 2)
        H.eq(S.wpMap.frontState, 2); H.eq(S.wpMap.secondsLeft, 600); H.eq(S.wpMap.nextStartsSec, 600)
        -- WPZ: the Front, the Front after the capture, then Dalaran (no objectives)
        H.eq(#seen.WPZ, 3)
        local a, b = seen.WPZ[1], seen.WPZ[2]
        H.eq(a.zoneId, 2817); H.eq(a.kind, "F"); H.eq(a.state, 1); H.eq(a.secondsLeft, 4320); H.eq(a.controlA, 620)
        H.eq(a.controlH, 380); H.eq(a.dominionTeam, "A"); H.eq(a.dominionStacks, 2); H.eq(a.levelMin, 80)
        H.eq(a.levelMax, 80); H.eq(#a.objectives, 3)
        H.eq(a.objectives[1].name, "Violet Stand"); H.eq(a.objectives[1].u, 512); H.eq(a.objectives[1].v, 388)
        H.eq(owners[1], "A1 N6 A1", "owners and states as the first WPZ sent them")
        H.eq(a.objectives[1].slider, 1000)
        local long = "Forlorn Woods; the \"old\" one, %20|cffff0000red|r"
        H.eq(a.objectives[2].name, long:sub(1, 40), "separators unescaped, cut at 40 bytes by the server")
        H.eq(a.objectives[2].u, 604); H.eq(a.objectives[2].v, 455)
        H.eq(a.objectives[2].slider, 260, "the capture bar moved the outpost's bar on")
        H.eq(a.objectives[3].name, "Sunreaver Rise"); H.eq(a.objectives[3].u, nil); H.eq(a.objectives[3].v, nil)
        H.eq(a.objectives[3].slider, 800)
        H.eq(b.controlA, 700); H.eq(b.controlH, 300); H.eq(b.dominionStacks, 3); H.eq(b.secondsLeft, 4100)
        H.eq(owners[2], "A1 A1 A1"); H.eq(b.byId[2].slider, 260)
        H.eq(S.wpZone.zoneId, 4395); H.eq(S.wpZone.kind, nil); H.eq(#S.wpZone.objectives, 0)
        -- WPCAP: two bars, then 0 (left it)
        H.eq(#seen.WPCAP, 2)
        local c1, c2 = seen.WPCAP[1], seen.WPCAP[2]
        H.eq(c1.objId, 2); H.eq(c1.slider, -120); H.eq(c1.neutralPct, 20); H.eq(c1.state, 6); H.eq(c1.countA, 2)
        H.eq(c1.countH, 3); H.eq(c1.maxNet, 5)
        H.eq(c2.slider, 260); H.eq(c2.state, 1); H.eq(c2.countA, 4); H.eq(c2.countH, 1)
        H.eq(S.wpCap, nil)
        -- WANTED: two (the second without a position), one, none; Dalaran forgets the list
        H.eq(#seen.WANTED, 3)
        local l1 = seen.WANTED[1]
        H.eq(l1.zoneId, 2817); H.eq(#l1.list, 2)
        local g = l1.list[1]
        H.eq(g.name, "Garrick Stormwind, the; bold|one~of:many"); H.eq(g.classId, 4); H.eq(g.team, "H")
        H.eq(g.streak, 5); H.eq(g.reason, "B"); H.eq(g.bountyHonor, 248); H.eq(g.bountyShards, 5); H.eq(g.u, 560)
        H.eq(g.v, 402); H.eq(g.ageSec, 35)
        local br = l1.list[2]
        H.eq(br.name, "Br\195\169nna"); H.eq(br.classId, 8); H.eq(br.streak, 9); H.eq(br.reason, "S")
        H.eq(br.bountyHonor, 446); H.eq(br.bountyShards, 9); H.eq(br.u, nil); H.eq(br.v, nil)
        H.eq(#seen.WANTED[2].list, 1); H.eq(seen.WANTED[2].list[1].name, "Br\195\169nna")
        H.eq(#seen.WANTED[3].list, 0)
        H.eq(S.wanted, nil, "another zone: the Wanted list is gone")
        -- WPEV: every kind bh_gen sends, in order
        local kinds = {}
        for i, e in ipairs(events) do kinds[i] = e.kind end
        H.eq(table.concat(kinds, ""), "XFACRWBSER")
        H.eq(events[1].zoneId, 2817); H.eq(events[1].seconds, 900); H.eq(events[1].name, "Crystalsong Forest")
        H.eq(events[2].seconds, 7200)
        H.eq(events[3].objId, 3); H.eq(events[3].team, "H"); H.eq(events[3].name, "Sunreaver Rise")
        H.eq(events[4].objId, 2); H.eq(events[4].team, "A"); H.eq(events[4].name, "Forlorn Woods")
        H.eq(events[5].why, "C"); H.eq(events[5].honor, 186); H.eq(events[5].xp, 0); H.eq(events[5].shards, 2)
        H.eq(events[5].drPermille, 1000)
        H.eq(events[6].name, "Garrick Stormwind, the; bold|one~of:many"); H.eq(events[6].classId, 4)
        H.eq(events[6].team, "H"); H.eq(events[6].streak, 5); H.eq(events[6].reason, "B")
        H.eq(events[7].killer, "Aldric"); H.eq(events[7].victim, "Garrick Stormwind, the; bold|one~of:many")
        H.eq(events[7].honor, 248); H.eq(events[7].shards, 5)
        H.eq(events[8].name, "Br\195\169nna"); H.eq(events[8].honor, 248); H.eq(events[8].shards, 5)
        H.eq(events[9].zoneId, 2817); H.eq(events[9].winner, "A"); H.eq(events[9].controlA, 640)
        H.eq(events[9].controlH, 360)
        H.eq(events[10].why, "V"); H.eq(events[10].honor, 496); H.eq(events[10].shards, 10)
        H.eq(ns.WarZoneName(2817), "Crystalsong Forest")
        -- the screen: in Dalaran no HUD and no bar
        H.ok(not ns.WarFront.hud:IsShown() and not ns.WarFront.cap:IsShown())
    end)
end

------------------------------------------------------------------------------------------------------
-- Arena seasons and the 1v1 ladder (section 20): the C++ module's arena session (bh_gen.cpp `arena`: HELLO bit 65536,
-- DEF V and Q, ARENA, LB / LBME board A, QUEUE kind A, ERR arena_closed) into the addon's state at every frame size.
------------------------------------------------------------------------------------------------------
for _, size in ipairs({ 1000, 251, 64 }) do
    test("C++ arena frames (max body " .. size .. ") reach the addon's state", function(M, ns)
        local data = loadFrames(size).arena
        H.ok(data and #data.frames >= data.messages and data.messages >= 12, "bh_gen wrote the arena session")
        local C, S = ns.Comm, ns.S
        feed(M, data)
        M.Advance(1)
        noDrops(C, "arena")
        H.eq(C.stats.framesIn, #data.frames, "frames in")
        H.eq(C.PendingChunks(), 0, "unfinished chunk buffers")
        H.eq(C.topicRev.QUEUE, data.revs.QUEUE, "revision of QUEUE")
        if size < 1000 then
            H.ok(#data.frames > data.messages, "small frames: messages were chunked")
        end
        H.ok(C.HasFeature(65536), "HELLO feature bit 65536: arena seasons live")
        -- DEF V and Q
        H.eq(ns.Def("V", 4).name, "Duelist"); H.eq(ns.Def("V", 4).color, "A335EE"); H.eq(ns.Def("V", 7).name, "Class Champion")
        H.eq(ns.Def("V", 5).text, "Top 0.5%, 50 wins.")
        local q = ns.Def("Q", 105)
        H.eq(q.seasonId, 1); H.eq(q.bracket, 3); H.eq(q.tierId, 5); H.eq(q.kind, "M"); H.eq(q.entry, 30609); H.eq(q.count, 1)
        H.eq(q.text, "Swift Nether Drake")
        H.eq(ns.Def("Q", 110).count, 150); H.eq(ns.Def("Q", 110).kind, "C"); H.eq(ns.Def("Q", 101).seasonId, 0)
        -- the last ARENA: final standings, the 1v1 rewards held for review
        local a = S.arena
        H.eq(a.seasonId, 1); H.eq(a.state, 4); H.eq(a.ratedOpen, false); H.eq(a.nextStartEpoch, 1800748800)
        H.eq(a.teamCost, nil, "the 1v1 queue's cost is left out: off"); H.eq(a.seasonName, "Arena Season 1")
        H.eq(a.brackets[1].missing, 64); H.eq(a.brackets[1].rating, 1734); H.eq(a.brackets[2], nil)
        H.eq(a.finals[1].rank, 12); H.eq(a.finals[1].rating, 1734); H.eq(a.finals[1].tierId, 3); H.eq(a.finals[1].grant, 2)
        H.eq(#a.matches, 0); H.eq(#a.cutoffs, 0)
        -- LB board A: ten rows with the arena fields
        local lb = S.lb.A
        H.eq(lb.board, "A"); H.eq(lb.dungeonId, 3); H.eq(lb.pages, 3); H.eq(#lb.rows, 10)
        H.eq(lb.rows[1].value, 2160); H.eq(lb.rows[1].label, "Team number 1"); H.eq(lb.rows[1].tierId, 6)
        H.eq(lb.rows[1].wins, 59); H.eq(lb.rows[1].games, 70); H.eq(lb.rows[1].flags, 0)
        H.eq(lb.rows[10].flags, 3); H.eq(lb.rows[10].members[3].name, "Garrick Stormwind"); H.eq(lb.rows[10].members[2].classId, 5)
        local me = S.lbme.A
        H.eq(me.rank, 4); H.eq(me.topPercent, 19); H.eq(me.value, 1912); H.eq(me.dungeonId, 3); H.eq(me.barPermille, 407)
        H.eq(me.label, "Duelist"); H.eq(me.topPermille, 182); H.eq(me.tierId, 4)
        -- QUEUE kind A: queued, in the match, then not queued; never members
        H.eq(S.queue.kind, "A"); H.eq(S.queue.state, 0); H.eq(#S.queue.members, 0)
        -- ERR arena_closed
        H.eq(S.err.op, "QJOIN"); H.eq(S.err.code, "arena_closed"); H.eq(S.err.seq, "2j")
    end)
end

test("C++ arena frames: the live ARENA before the season ended", function(M, ns)
    local data = loadFrames(1000).arena
    -- deliver up to (and including) the first ARENA only
    for _, chat in ipairs(data.frames) do
        local prefix, body = chat:match("^([^\t]*)\t(.*)$")
        H.deliver(M, body, prefix)
        if body:find("^1 ARENA ") then break end
    end
    M.Advance(0.5)
    local a = ns.S.arena
    H.eq(a.state, 1); H.eq(a.ratedOpen, true); H.eq(a.teamCost, 0); H.eq(a.seasonName, "Arena Season 1, the; first|one")
    H.eq(#a.seasons, 1); H.eq(a.seasons[1].name, "Arena Season 1"); H.eq(a.seasons[1].state, 1)
    local one, two = a.brackets[1], a.brackets[2]
    H.eq(one.rank, 12); H.eq(one.size, 48); H.eq(one.games, 61); H.eq(one.wins, 38); H.eq(one.weekGames, 9)
    H.eq(one.personal, 1734); H.eq(one.recent, 14); H.eq(one.tierId, 3); H.eq(one.nextTierId, 4); H.eq(one.toNext, 66)
    H.eq(one.missing, 0); H.eq(one.team, "Aldric"); H.eq(one.hasTeam, true)
    H.eq(two.rank, nil); H.eq(two.missing, 33); H.eq(two.team, "Br\195\169nna & Co")
    H.eq(#a.cutoffs, 2); H.eq(a.cutoffs[1].cutRating, 1801); H.eq(a.cutoffs[2].cutRank, nil); H.eq(a.cutoffs[2].floor, 1850)
    H.eq(a.ladders[5].rewardsOpen, false); H.eq(a.ladders[5].titlesOpen, false); H.eq(a.ladders[1].eligible, 48)
    H.eq(#a.matches, 2); H.eq(a.matches[1].change, 14); H.eq(a.matches[2].verdict, 2); H.eq(a.matches[2].reason, "E")
    H.eq(a.matches[1].reason, nil)
end)
