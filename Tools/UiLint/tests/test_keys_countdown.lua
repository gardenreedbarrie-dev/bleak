-- The keystone countdown (Countdown.lua): its kicker for a Mythic 0 (the Font of Power's: MPS level 0, a 10 s
-- countdown, no time limit), and DBM's pull timer for both DBM generations: "DBMv4-PT" for the newer builds and the
-- "DBMv4-Pizza" timer the stock DBM-Core 4.x for 3.3.5a knows ("<sec>\tPull in"), with a local bar where a 4.x DBM
-- would show none (its own player's Pizza, a self-whisper).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function sentWith(M, prefix, from)
    local out = {}
    for i = (from or 0) + 1, #M.sent do
        local s = M.sent[i]
        if s.prefix == prefix then
            out[#out + 1] = s
        end
    end
    return out
end

-- DBM-Core 4.52 for 3.3.5a: a release number, Pizza timers, its bar module (DBT)
local function oldDbm(M)
    local d = { calls = {}, cancels = {}, bars = {} }
    M.env.DBM = {
        ReleaseRevision = 4442, Version = "4.52", Options = {},
        CreatePizzaTimer = function(self, time, text, broadcast)
            d.calls[#d.calls + 1] = { self = self, time = time, text = text, broadcast = broadcast }
            d.bars[text] = {}
        end,
        Bars = {
            GetBar = function(_, id) return d.bars[id] end,
            CancelBar = function(_, id)
                d.cancels[#d.cancels + 1] = id
                d.bars[id] = nil
            end,
        },
    }
    return d
end

test("countdown: a Mythic 0 counts down as one, untimed, over the bare dungeon name", function(M, ns)
    FX.connect(M, H)
    H.send(M, "MPS", { { 7002, 574, 0, "", "", 10000, 0 } })
    local cd = M.env.BleakholdCountdown
    H.ok(cd:IsShown())
    H.eq(cd.kicker:GetText(), "Mythic 0 - untimed")
    H.eq(cd.title:GetText(), "Utgarde Keep")
    for _, a in ipairs(cd.affixes) do
        H.ok(not a:IsShown(), "no affix icons")
    end
    H.eq(cd.bar.name:GetText(), "Pull in", "the same bar")
    M.Advance(10.3)
    H.ok(not cd:IsShown(), "gone at zero")
    -- a key next: its own kicker again
    H.send(M, "MPS", FX.examples(M).MPS)
    H.eq(cd.kicker:GetText(), "Mythic+ Keystone")
    H.eq(cd.title:GetText(), "Halls of Lightning +8")
end)

test("countdown: the party leader sends DBM's PT and the 4.x Pizza timer; a cancel sends PT 0 only", function(M, ns)
    FX.connect(M, H)
    M.SetGroup("PARTY", 5, true)
    H.send(M, "MPS", FX.examples(M).MPS)
    local pt, pizza = sentWith(M, "DBMv4-PT"), sentWith(M, "DBMv4-Pizza")
    H.eq(#pt, 1); H.eq(pt[1].msg, "10"); H.eq(pt[1].channel, "PARTY")
    H.eq(#pizza, 1, "the Pizza timer too")
    H.eq(pizza[1].msg, "10\tPull in", "seconds, a tab and DBM's own pull text")
    H.eq(pizza[1].channel, "PARTY")
    local before = #M.sent
    H.send(M, "MP", { { 7001, 0, 1800, 0, 0, 0, 100, 0, "", "", 4 } })
    pt, pizza = sentWith(M, "DBMv4-PT", before), sentWith(M, "DBMv4-Pizza", before)
    H.eq(#pt, 1); H.eq(pt[1].msg, "0", "PT cancels")
    H.eq(#pizza, 0, "never a Pizza for 0")
end)

test("countdown: a raid leader sends both to RAID", function(M, ns)
    FX.connect(M, H)
    M.SetGroup("RAID", 10, true)
    H.send(M, "MPS", FX.examples(M).MPS)
    H.eq(sentWith(M, "DBMv4-Pizza")[1].channel, "RAID")
    H.eq(sentWith(M, "DBMv4-PT")[1].channel, "RAID")
end)

test("countdown: solo with a 4.x DBM makes its own Pull in bar instead of the whisper it would drop", function(M, ns)
    FX.connect(M, H)
    local d = oldDbm(M)
    H.send(M, "MPS", FX.examples(M).MPS)
    H.eq(#sentWith(M, "DBMv4-PT"), 0, "no self-whisper")
    H.eq(#sentWith(M, "DBMv4-Pizza"), 0)
    H.eq(#d.calls, 1, "DBM:CreatePizzaTimer")
    H.eq(d.calls[1].self, M.env.DBM, "called as a method")
    H.eq(d.calls[1].time, 10); H.eq(d.calls[1].text, "Pull in")
    H.ok(not d.calls[1].broadcast, "not broadcast")
    local cd = M.env.BleakholdCountdown
    M.Advance(0.3)
    H.ok(not cd.bar:IsShown(), "DBM's bar shows: ours hides")
    -- cancelled: DBM's bar goes too
    H.send(M, "MP", { { 7001, 0, 1800, 0, 0, 0, 100, 0, "", "", 4 } })
    H.eq(d.cancels[1], "Pull in", "DBM.Bars:CancelBar")
    H.ok(not cd:IsShown())
end)

test("countdown: the leader with a 4.x DBM sends both and makes its own bar (its own Pizza is ignored)", function(M, ns)
    FX.connect(M, H)
    M.SetGroup("PARTY", 5, true)
    local d = oldDbm(M)
    H.send(M, "MPS", FX.examples(M).MPS)
    H.eq(#sentWith(M, "DBMv4-PT"), 1)
    H.eq(#sentWith(M, "DBMv4-Pizza"), 1)
    H.eq(#d.calls, 1)
    H.eq(d.calls[1].time, 10)
end)

test("countdown: a member with a 4.x DBM takes the leader's Pizza bar away on a cancel", function(M, ns)
    FX.connect(M, H)
    M.SetGroup("PARTY", 5, false)
    local d = oldDbm(M)
    H.send(M, "MPS", FX.examples(M).MPS)
    H.eq(#d.calls, 0, "a member makes no bar: the leader's Pizza does")
    d.bars["Pull in"] = {}
    H.send(M, "MP", { { 7001, 0, 1800, 0, 0, 0, 100, 0, "", "", 4 } })
    H.eq(d.cancels[1], "Pull in")
    H.eq(#sentWith(M, "DBMv4-PT"), 0, "a member sends nothing")
end)

test("countdown: solo with a newer DBM (a date revision) whispers PT to itself as before", function(M, ns)
    FX.connect(M, H)
    local called = 0
    M.env.DBM = { ReleaseRevision = 20220812000000, Options = {},
        CreatePizzaTimer = function() called = called + 1 end }
    H.send(M, "MPS", FX.examples(M).MPS)
    local pt = sentWith(M, "DBMv4-PT")
    H.eq(#pt, 1)
    H.eq(pt[1].channel, "WHISPER")
    H.eq(pt[1].target, M.playerName)
    H.eq(called, 0, "no local Pizza")
    H.eq(#sentWith(M, "DBMv4-Pizza"), 0, "no Pizza to oneself")
end)

test("countdown: the affix icons are named by the server's ids, as the Keys page names them", function(M, ns)
    FX.connect(M, H)
    -- Data.lua's built-in DEF A says Volcanic for 4; the server's 4 is Raging (its 10 is Volcanic)
    H.send(M, "MPS", { { 7001, 602, 15, { 1, 3, 4, 10, 13, 14 }, 7, 10000, 1800 } })
    local cd = M.env.BleakholdCountdown
    local names = {}
    for i, a in ipairs(cd.affixes) do
        if a:IsShown() then
            names[#names + 1] = a.tipLines and a.tipLines[1]
        end
    end
    H.eq(table.concat(names, ", "), "Fortified, Bolstering, Raging, Volcanic, Mythic Champions, Mythical Boons")
    -- a built-in text is shown only where its name agrees (Fortified), the Champions' own text otherwise
    H.eq(cd.affixes[1].tipLines[2], ns.Def("A", 1).text)
    H.ok(cd.affixes[3].tipLines[2] == nil or not cd.affixes[3].tipLines[2]:find("Plumes of flame", 1, true),
        "not Volcanic's text on Raging")
    H.eq(cd.affixes[5].tipLines[2], ns.Keys.SPECIAL_TEXT[13])
    -- every icon a real one; the Champions and Boons the Keys page's
    H.eq(cd.affixes[3].icon:GetTexture(), "Interface\\Icons\\Ability_Druid_ChallangingRoar", "Raging's icon")
    H.eq(cd.affixes[5].icon:GetTexture(), "Interface\\Icons\\Spell_Holy_SummonChampion")
    H.eq(cd.affixes[6].icon:GetTexture(), "Interface\\Icons\\Spell_Holy_DivineIntervention")
end)

test("countdown: the server sends the pull timer (PT only): a 4.x DBM's client makes its own bar, leader or member",
    function(M, ns)
    -- HELLO feature bit 4: BleakholdMgr sends "DBMv4-PT" itself, which a 4.x DBM does not know
    FX.connect(M, H, { [6] = 4 })
    M.SetGroup("PARTY", 5, false)
    local d = oldDbm(M)
    H.send(M, "MPS", FX.examples(M).MPS)
    H.eq(#sentWith(M, "DBMv4-PT"), 0, "the server sends it")
    H.eq(#sentWith(M, "DBMv4-Pizza"), 0, "nothing broadcast")
    H.eq(#d.calls, 1, "a local Pull in bar")
    H.eq(d.calls[1].time, 10); H.eq(d.calls[1].text, "Pull in"); H.ok(not d.calls[1].broadcast)
    M.Advance(0.3)
    H.ok(not M.env.BleakholdCountdown.bar:IsShown(), "DBM's bar shows: ours hides")
    -- cancelled: it goes
    H.send(M, "MP", { { 7001, 0, 1800, 0, 0, 0, 100, 0, "", "", 4 } })
    H.eq(d.cancels[1], "Pull in")
    -- the leader too
    M.SetGroup("PARTY", 5, true)
    H.send(M, "MPS", { { 7002, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    H.eq(#d.calls, 2)
    H.eq(#sentWith(M, "DBMv4-PT"), 0)
    -- turned off (/bh dbm off), or a newer DBM (it takes the server's PT): none
    ns.db.options.dbmPull = false
    H.send(M, "MPS", { { 7003, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    H.eq(#d.calls, 2, "off")
    ns.db.options.dbmPull = true
    M.env.DBM.ReleaseRevision = 20220812000000
    H.send(M, "MPS", { { 7004, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    H.eq(#d.calls, 2, "a newer DBM")
    -- under 3 s DBM shows no pull bar
    M.env.DBM.ReleaseRevision = 4442
    H.send(M, "MPS", { { 7005, 602, 8, { 1, 3, 4 }, 7, 2000, 1800 } })
    H.eq(#d.calls, 2, "under 3 s")
end)
