-- Arena seasons and the 1v1 ladder (docs/BleakholdProtocol.md section 20): the document's frames through State, the
-- Arena page and the Arena leaderboard at every frame size the server may use; the gates of feature bit 65536; the
-- 1v1 queue (QJOIN A, the cost confirmation, QUEUE kind A, QLEAVE, the refusals on the card); GET ARENA at most every
-- 30 s; the cards, the cutoffs, the checklist, the rewards and the match verdicts; the match toast; garbage; and
-- the arena season of /bh demo.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local ARENA = { [6] = 65536 }

local function connect(M, extra)
    local bits = { [6] = 65536 }
    for k, v in pairs(extra or {}) do bits[k] = v end
    FX.connect(M, H, bits)
end

local function texts(M, s)
    return #M.FindText(s, true)
end

local function intentsOf(M, op)
    local out = {}
    for _, it in ipairs(H.intents(M)) do
        if it.op == op then out[#out + 1] = it.payload end
    end
    return out
end

local function getsOf(M, topic)
    local n = 0
    for _, it in ipairs(H.intents(M)) do
        if it.op == "GET" then
            for _, r in ipairs(it.records) do
                if r[1] == topic then n = n + 1 end
            end
        end
    end
    return n
end

local function errorsShown(M, text)
    local n = 0
    for _, c in ipairs(M.chat) do
        if c.frame == M.env.UIErrorsFrame and c.msg:find(text, 1, true) then n = n + 1 end
    end
    return n
end

local function navEntry(ns, key)
    for _, b in ipairs(ns.Activities.nav) do
        if b.key == key then return b end
    end
end

local function tab(ns, key)
    for _, b in ipairs(ns.Leaderboards.tabs) do
        if b.key == key then return b end
    end
end

-- A live season: the doc's first ARENA, at the mock's clock (field index -> value overrides the header).
local function arena(M, over, extra)
    local now = M.env.time()
    local head = { 1, 1, now - 86400, now + 30 * 86400, now + 32 * 86400, 1, 100000, "Arena Season 1" }
    for k, v in pairs(over or {}) do head[k] = v end
    local recs = { head,
        { "S", 1, "Arena Season 1", 1, now - 86400, now + 30 * 86400 },
        { "S", 2, "Arena Season 2", 2, now + 32 * 86400, now + 90 * 86400 },
        { "B", 1, 1, 1734, 12, 48, 61, 38, 9, 6, 1734, 14, 3, 4, 66, 0, "Aldric" },
        { "B", 3, 1, 1912, 4, 22, 44, 30, 12, 8, 1890, 12, 4, 5, 163, 16, "Ironvow Wardens" },
        { "T", 3, 6, 1, 1, 2140, 2000 }, { "T", 3, 5, 2, 2, 2075, 2000 }, { "T", 3, 4, 4, 4, 1912, 1800 },
        { "T", 3, 3, 4, 4, 1912, 1650 }, { "T", 3, 2, 8, 8, 1702, 1500 }, { "T", 3, 1, 22, 22, 1310, 1300 },
        { "T", 1, 4, 6, 6, 1801, 1800 }, { "T", 1, 3, 5, 5, 1702, 1650 },
        { "N", 1, 48, 1, 1 }, { "N", 3, 22, 1, 0 },
        { "M", 1, 1, 14, "Brenna", now - 600, 0, "" }, { "M", 1, 0, -11, "Corwin", now - 1200, 0, "" },
        { "M", 1, 1, 0, "Dalia", now - 1800, 2, "I" }, { "M", 1, 1, 7, "Eamon", now - 2400, 1, "R" },
    }
    for _, r in ipairs(extra or {}) do recs[#recs + 1] = r end
    H.send(M, "ARENA", recs)
end

local function openPage(M, ns)
    ns.UI.Open("arena")
    M.Advance(0.3)
    return ns.Arena.page
end

-- Section 20's S> example messages, chunks joined: { op, payload }.
local function docExamples()
    local text = assert(host_readfile(repo .. "/docs/BleakholdProtocol.md"))
    local sec = assert(text:match("\n## 20%. Arena seasons and the 1v1 ladder(.-)\n## %d")
        or text:match("\n## 20%. Arena seasons and the 1v1 ladder(.*)$"), "section 20")
    local out, open = {}, {}
    for line in sec:gmatch("[^\n]+") do
        local body = line:match("^S> (.+)$")
        if body then
            local op, seq, part, total, payload = body:match("^1 (%u+) (%w+) (%d+)/(%d+) ?(.*)$")
            local key = op .. seq
            local cur = open[key] or { op = op, parts = {} }
            open[key] = cur
            cur.parts[tonumber(part)] = payload
            if tonumber(part) == tonumber(total) then
                out[#out + 1] = { op = op, payload = table.concat(cur.parts) }
                open[key] = nil
            end
        end
    end
    return out
end

------------------------------------------------------------------------------------------------------
-- The document's frames, re-framed at every size the server may use
------------------------------------------------------------------------------------------------------
for _, size in ipairs({ 1000, 251, 64 }) do
    test("doc section 20 frames at max body " .. size .. " reach State, the Arena page and the leaderboard",
        function(M, ns)
        connect(M)
        local S, C, AR = ns.S, ns.Comm, ns.Arena
        local examples = docExamples()
        H.ok(#examples >= 8, "section 20 examples: " .. #examples)
        ns.UI.Open("arena")
        M.Advance(0.3)
        local seq, sent, firstArena = 700, 0, nil
        for _, ex in ipairs(examples) do
            seq = seq + 1
            local frames = assert(C.BuildFrames(ex.op, seq, ex.payload, size))
            for _, body in ipairs(frames) do
                H.ok(#body <= size, "frame within " .. size .. " bytes")
                H.deliver(M, body)
                sent = sent + 1
            end
            if ex.op == "ARENA" and not firstArena then
                firstArena = S.arena
                -- the live season, as the page shows it
                local P = AR.page
                H.eq(P.head.title:GetText(), "Arena Season 1")
                H.eq(P.head.state.text:GetText(), "Live")
                H.contains(P.head.clock:GetText(), "Ends in ")
                local c1, c3 = P.cards[1], P.cards[3]
                H.eq(c1.rating:GetText(), "1734")
                H.eq(c1.rank:GetText(), "Rank 12 of 48")
                H.eq(c1.record:GetText(), "38-23  -  week 6-3")
                H.eq(c1.next:GetText(), "+66 to Duelist")
                H.contains(c1.tier:GetText(), "Rival")
                H.eq(c1.status:GetText(), "On pace for Rival")
                H.eq(c3.team:GetText(), "Ironvow Wardens")
                H.eq(c3.next:GetText(), "+163 to Gladiator")
                H.eq(c3.status:GetText(), "1 thing keeps you from rewards")
                H.eq(P.matches.rows[3].right:GetText(), "Not counted: same network")
                H.eq(P.matches.rows[4].right:GetText(), "Half gain: rematch")
                H.contains(P.matches.rows[1].left:GetText(), "+14  Brenna")
                H.contains(P.matches.rows[2].left:GetText(), "-11  Corwin")
            end
            M.Advance(0.1)
        end
        if size == 64 then
            H.ok(sent > #examples, "frames were chunked: " .. sent)
        end
        local drops = 0
        for _, v in pairs(C.stats.dropped) do drops = drops + v end
        H.eq(drops, 0, "no frame dropped")
        H.eq(C.stats.unknown, 0, "every op has a handler")
        H.eq(C.PendingChunks(), 0)
        -- the first ARENA in State
        local a = firstArena
        H.eq(a.seasonId, 1); H.eq(a.state, 1); H.eq(a.startEpoch, 1793318400); H.eq(a.endEpoch, 1800576000)
        H.eq(a.nextStartEpoch, 1800748800); H.eq(a.ratedOpen, true); H.eq(a.teamCost, 0)
        H.eq(a.seasonName, "Arena Season 1")
        H.eq(#a.seasons, 2); H.eq(a.seasons[2].name, "Arena Season 2"); H.eq(a.seasons[2].state, 2)
        local b1, b3 = a.brackets[1], a.brackets[3]
        H.eq(b1.hasTeam, true); H.eq(b1.rating, 1734); H.eq(b1.rank, 12); H.eq(b1.size, 48); H.eq(b1.games, 61)
        H.eq(b1.wins, 38); H.eq(b1.weekGames, 9); H.eq(b1.weekWins, 6); H.eq(b1.personal, 1734); H.eq(b1.recent, 14)
        H.eq(b1.tierId, 3); H.eq(b1.nextTierId, 4); H.eq(b1.toNext, 66); H.eq(b1.missing, 0); H.eq(b1.team, "Aldric")
        H.eq(b3.tierId, 4); H.eq(b3.missing, 16); H.eq(b3.team, "Ironvow Wardens")
        H.eq(#a.cutoffs, 6); H.eq(a.cutoffs[1].tierId, 6); H.eq(a.cutoffs[1].cutRating, 2140)
        H.eq(AR.Takes(a.cutoffs[3]), 1912)
        H.eq(a.ladders[1].eligible, 48); H.eq(a.ladders[3].eligible, 22); H.eq(a.ladders[3].titlesOpen, true)
        H.eq(#a.matches, 4); H.eq(a.matches[3].verdict, 2); H.eq(a.matches[3].reason, "I")
        H.eq(a.matches[4].verdict, 1); H.eq(a.matches[4].reason, "R"); H.eq(a.matches[2].won, false)
        H.eq(a.matches[2].change, -11)
        -- LB / LBME board A
        local lb = S.lb.A
        H.eq(lb.seasonId, 1, "the season the server resolved 0 to"); H.eq(lb.dungeonId, 3); H.eq(lb.pages, 3); H.eq(#lb.rows, 3)
        H.eq(lb.rows[1].label, "Dawnbreakers"); H.eq(lb.rows[1].value, 2140); H.eq(lb.rows[1].wins, 61)
        H.eq(lb.rows[1].games, 70); H.eq(lb.rows[1].tierId, 6); H.eq(lb.rows[1].flags, 0)
        H.eq(lb.rows[2].members[3].name, "Garrick Stormwind"); H.eq(lb.rows[3].flags, 1)
        local me = S.lbme.A
        H.eq(me.rank, 4); H.eq(me.topPercent, 19); H.eq(me.value, 1912); H.eq(me.dungeonId, 3)
        H.eq(me.barPermille, 407); H.eq(me.label, "Duelist"); H.eq(me.topPermille, 182); H.eq(me.tierId, 4)
        -- DEF V / Q
        H.eq(ns.DefName("V", 5), "Gladiator"); H.eq(ns.Def("V", 5).color, "FF8000")
        H.eq(ns.Def("V", 5).text, "The top 0.5% of the ladder with 50 wins.")
        local q = ns.Def("Q", 105)
        H.eq(q.seasonId, 1); H.eq(q.bracket, 3); H.eq(q.tierId, 5); H.eq(q.kind, "M"); H.eq(q.entry, 30609)
        H.eq(q.text, "Swift Nether Drake")
        -- QUEUE kind A, then ERR arena_closed (the server's sentence), then the final standings
        H.eq(S.queue.kind, "A"); H.eq(S.queue.state, 1); H.eq(S.queue.tier, 1); H.eq(S.queue.queuedSec, 8)
        H.eq(S.queue.estWaitSec, 95); H.eq(#S.queue.members, 0)
        H.eq(S.err.code, "arena_closed")
        H.eq(S.err.shown, "Rated arena opens again when Arena Season 2 starts.")
        local fin = S.arena
        H.eq(fin.state, 4); H.eq(fin.ratedOpen, false); H.eq(fin.brackets[1].missing, 64)
        H.eq(fin.finals[1].rank, 12); H.eq(fin.finals[1].tierId, 3); H.eq(fin.finals[1].grant, 2)
        local P = AR.page
        H.eq(P.head.state.text:GetText(), "Final standings")
        H.contains(P.cards[1].next:GetText(), "Final #12")
        H.eq(P.cards[1].status:GetText(), "Rewards held for review")
        H.eq(P.queue.status:GetText(), "In the rated 1v1 queue")
        H.ok(P.queue.leave:IsShown(), "Leave while queued")
        -- the leaderboard of the examples
        ns.Leaderboards.OpenArena(3)
        M.Advance(0.3)
        H.ok(texts(M, "Dawnbreakers") > 0, "podium team")
        H.ok(texts(M, "YOUR STANDING") > 0)
        H.ok(texts(M, "Rank 4  -  top 19%") > 0, "your standing")
    end)
end

------------------------------------------------------------------------------------------------------
-- Feature bit 65536
------------------------------------------------------------------------------------------------------
test("arena: no page, no nav entry, no leaderboard tab and no QJOIN A without feature bit 65536", function(M, ns)
    FX.connect(M, H)
    local nav = navEntry(ns, "arena")
    H.ok(nav and not nav:IsShown(), "no Arena entry without the bit")
    ns.UI.Open("arena")
    M.Advance(0.3)
    H.ok(not ns.Arena.page:IsVisible(), "no Arena page")
    H.ok(errorsShown(M, "Arena seasons are not running on this realm.") >= 1, "the reason in the error frame")
    ns.Activities.Show("arena")
    H.eq(ns.Activities.current, "tasks", "Activities.Show falls back to Tasks")
    ns.UI.Open("leaderboards")
    M.Advance(0.3)
    H.ok(not tab(ns, "A"):IsShown(), "no Arena tab")
    ns.Leaderboards.board = "A"
    ns.Leaderboards.Query()
    ns.Leaderboards.Refresh()
    H.eq(ns.Leaderboards.board, "K", "board A falls back to Mythic Keys")
    local before = #M.sent
    ns.Arena.Join(true)
    ns.Arena.Join(false)
    M.env.SlashCmdList.BLEAKHOLD("arena rated")
    ns.Arena.Ask(true)
    M.Advance(1)
    H.eq(#intentsOf(M, "QJOIN"), 0, "no QJOIN")
    H.eq(getsOf(M, "ARENA"), 0, "no GET ARENA")
    for _, it in ipairs(H.intents(M)) do
        H.ok(not it.payload:find("^A,"), "nothing of board A: " .. it.body)
    end
    H.ok(#M.sent >= before)
end)

test("arena: the bit at runtime shows the nav entry after Rift and the Arena tab; off again goes back", function(M, ns)
    FX.connect(M, H)
    local nav = navEntry(ns, "arena")
    H.hello(M, ARENA)
    M.Advance(0.3)
    H.ok(nav:IsShown(), "Arena entry with the bit")
    H.eq(select(5, nav:GetPoint(1)), -12 - 3 * 66, "after Rift (Royale off), before Tasks")
    H.hello(M, { [6] = 65536 + 4096 })
    M.Advance(0.3)
    H.eq(select(5, nav:GetPoint(1)), -12 - 4 * 66, "after Royale")
    arena(M)
    local P = openPage(M, ns)
    H.ok(P:IsVisible(), "Arena page")
    ns.UI.Open("leaderboards-arena")
    M.Advance(0.3)
    H.ok(tab(ns, "A"):IsShown(), "Arena tab")
    H.eq(ns.Leaderboards.board, "A")
    -- off again: the page goes to Tasks, the tab and the season go
    H.hello(M, { [6] = 0 })
    M.Advance(0.3)
    H.ok(not nav:IsShown(), "entry gone")
    H.eq(ns.Activities.current, "tasks", "back to Tasks")
    H.ok(not P:IsVisible())
    H.ok(not tab(ns, "A"):IsShown(), "tab gone")
    H.eq(ns.Leaderboards.board, "K")
    H.eq(ns.S.arena, nil, "the season is forgotten")
end)

------------------------------------------------------------------------------------------------------
-- The 1v1 queue
------------------------------------------------------------------------------------------------------
test("arena: Rated without a 1v1 team asks to pay first, then QJOIN A,1,1,4,1; Skirmish QJOIN A,1,0,4,1", function(M, ns)
    connect(M)
    arena(M, nil, { { "B", 1, 0 } })
    local P = openPage(M, ns)
    H.eq(P.cards[1].team:GetText(), "No 1v1 team yet")
    H.eq(P.cards[1].record:GetText(), "It costs 10g")
    H.eq(P.queue.detail:GetText(), "Rated makes your 1v1 team for 10g")
    H.ok(P.queue.rated:IsEnabled() and P.queue.skirmish:IsEnabled())
    P.queue.rated:Click()
    local d = M.env.BleakholdDialog
    H.ok(d:IsShown(), "cost confirmation")
    H.contains(d.text:GetText(), "10g")
    H.eq(#intentsOf(M, "QJOIN"), 0, "nothing before the confirmation")
    d.ok:Click()
    M.Advance(0.3)
    H.eq(table.concat(intentsOf(M, "QJOIN"), " "), "A,1,1,4,1")
    M.Advance(1.2)
    P.queue.skirmish:Click()
    M.Advance(0.3)
    H.eq(table.concat(intentsOf(M, "QJOIN"), " "), "A,1,1,4,1 A,1,0,4,1")
end)

test("arena: with a 1v1 team Rated joins at once; QUEUE kind A shows the wait; Leave sends QLEAVE", function(M, ns)
    connect(M)
    arena(M)
    local P = openPage(M, ns)
    P.queue.rated:Click()
    M.Advance(0.3)
    H.ok(not M.env.BleakholdDialog or not M.env.BleakholdDialog:IsShown(), "no confirmation with a team")
    H.eq(table.concat(intentsOf(M, "QJOIN"), " "), "A,1,1,4,1")
    H.send(M, "QUEUE", { { 3, 1, "A", 1, 1, 1, 40, 95 } })
    M.Advance(1.1)
    H.eq(P.queue.status:GetText(), "In the rated 1v1 queue")
    H.contains(P.queue.detail:GetText(), "Waiting 00:4")
    H.contains(P.queue.detail:GetText(), "usually 01:35")
    H.ok(P.queue.leave:IsShown() and not P.queue.rated:IsShown(), "Leave instead of the join buttons")
    H.ok(texts(M, "In queue: Rated 1v1 arena") == 0, "Dungeons page not shown")
    P.queue.leave:Click()
    M.Advance(0.3)
    H.eq(#intentsOf(M, "QLEAVE"), 1)
    H.send(M, "QUEUE", { { 4, 3, "A", 1, 1, 1, 0, "" } })
    M.Advance(0.3)
    H.eq(P.queue.status:GetText(), "In a rated 1v1 match")
    H.ok(not P.queue.rated:IsEnabled(), "no join while in a match")
    -- the Dungeons page names the arena queue
    H.send(M, "QUEUE", { { 5, 1, "A", 1, 0, 1, 3, "" } })
    ns.UI.Open("dungeons")
    M.Advance(0.3)
    H.ok(texts(M, "In queue: 1v1 arena skirmish") > 0, "Dungeons status")
end)

test("arena: rated closed leaves the skirmish; no 1v1 queue on the realm disables both", function(M, ns)
    connect(M)
    local now = M.env.time()
    arena(M, { [2] = 3, [6] = 0, [5] = now + 2 * 86400 + 1800 })
    local P = openPage(M, ns)
    H.eq(P.head.state.text:GetText(), "Rated closed")
    H.contains(P.head.clock:GetText(), "next season in 2 d")
    H.ok(not P.queue.rated:IsEnabled(), "rated closed")
    H.ok(P.queue.skirmish:IsEnabled(), "skirmish open")
    H.contains(P.queue.notice:GetText(), "Rated arena is closed - the next season starts in 2 d")
    local before = #intentsOf(M, "QJOIN")
    ns.Arena.Join(true)
    M.Advance(0.3)
    H.eq(#intentsOf(M, "QJOIN"), before, "no rated QJOIN while closed")
    arena(M, { [7] = "" })
    M.Advance(0.3)
    H.ok(not P.queue.rated:IsEnabled() and not P.queue.skirmish:IsEnabled(), "no 1v1 queue")
    H.contains(P.queue.notice:GetText(), "The 1v1 queue is not open on this realm.")
end)

test("arena: refusals show on the queue card with the addon's sentences; busy waits a full gap", function(M, ns)
    connect(M)
    arena(M)
    local P = openPage(M, ns)
    P.queue.skirmish:Click()
    M.Advance(0.3)
    local seq = ns.Comm.lastSeq
    H.send(M, "ERR", { { "QJOIN", seq, "arena_talents", "" } })
    M.Advance(0.1)
    H.eq(P.queue.notice:GetText(), "Your talents are not allowed in the 1v1 arena.")
    H.send(M, "ERR", { { "QJOIN", seq, "arena_busy", "You are in a group." } })
    H.eq(P.queue.notice:GetText(), "You are in a group.", "the server's reason when it gives one")
    H.send(M, "ERR", { { "QJOIN", seq, "arena_gold", "" } })
    H.eq(P.queue.notice:GetText(), "You need 10g for a 1v1 arena team.")
    H.eq(ns.ErrorText({ code = "arena_deserter" }), "You cannot join while you are a deserter.")
    H.eq(ns.ErrorText({ code = "arena_off" }), "The 1v1 arena is not open on this realm right now.")
    H.eq(ns.ErrorText({ code = "arena_closed" }), "Rated arena is closed until the next season starts.")
    M.Advance(13)
    H.eq(P.queue.notice:GetText(), "", "the notice goes after a while")
    -- busy: the next click waits
    H.send(M, "ERR", { { "QJOIN", seq, "busy", "" } })
    local n = #intentsOf(M, "QJOIN")
    P.queue.skirmish:Click()
    M.Advance(0.3)
    H.eq(#intentsOf(M, "QJOIN"), n, "within the gap")
    M.Advance(1)
    P.queue.skirmish:Click()
    M.Advance(0.3)
    H.eq(#intentsOf(M, "QJOIN"), n + 1)
end)

------------------------------------------------------------------------------------------------------
-- GET ARENA
------------------------------------------------------------------------------------------------------
test("arena: GET ARENA when the page opens, then at most every 30 s while it is shown, never while closed",
    function(M, ns)
    connect(M)
    M.Advance(1)
    H.eq(getsOf(M, "ARENA"), 0, "the server pushes ARENA after HELLO: no GET")
    arena(M)
    M.Advance(31)
    H.eq(getsOf(M, "ARENA"), 0, "nothing while the page is closed")
    openPage(M, ns)
    H.eq(getsOf(M, "ARENA"), 1, "asked on opening (the last one is 31 s old)")
    M.Advance(10)
    openPage(M, ns)
    ns.Activities.Show("tasks")
    ns.Activities.Show("arena")
    M.Advance(15)
    H.eq(getsOf(M, "ARENA"), 1, "not again within 30 s")
    M.Advance(7)
    H.eq(getsOf(M, "ARENA"), 2, "again after 30 s")
    arena(M)
    M.Advance(25)
    H.eq(getsOf(M, "ARENA"), 2, "a pushed ARENA restarts the 30 s")
    M.Advance(7)      -- Activities ticks the page about every second
    H.eq(getsOf(M, "ARENA"), 3)
    ns.Activities.frame:Hide()
    M.Advance(65)
    H.eq(getsOf(M, "ARENA"), 3, "none after the window closed")
end)

------------------------------------------------------------------------------------------------------
-- The page's views
------------------------------------------------------------------------------------------------------
test("arena: cutoffs, checklist and rewards of the selected bracket", function(M, ns)
    connect(M)
    arena(M)
    H.send(M, "DEF", { { "Q", 7 }, { 101, 0, 3, 2, "T", 2090, 1, "Challenger" },
        { 110, 0, 3, 1, "C", 0, 150, "150 Dungeon Shards" }, { 112, 0, 3, 5, "M", 30610, 1, "Old Drake" },
        { 124, 1, 3, 5, "M", 30609, 1, "Swift Nether Drake" }, { 125, 2, 3, 5, "M", 34092, 1, "Merciless Nether Drake" },
        { 126, 1, 3, 5, "C", 0, 1200, "1,200 Dungeon Shards" }, { 130, 0, 1, 1, "C", 0, 150, "150 Dungeon Shards" } })
    local P = openPage(M, ns)
    P.cards[3]:Click()
    H.eq(P.bracket, 3)
    H.eq(ns.cdb.arenaBracket, 3, "remembered")
    -- cutoffs
    local cut = P.detail.cutoffs
    H.ok(cut:IsVisible())
    H.contains(cut.rows[1].cells[1]:GetText(), "Rank One")
    H.eq(cut.rows[3].cells[3]:GetText(), "#4")
    H.contains(cut.rows[3].cells[6]:GetText(), "1912")
    H.contains(cut.rows[6].cells[6]:GetText(), "1310")
    H.eq(cut.rows[3].__bdcolor[1], select(1, ns.UI.Rgb(ns.UI.C.active)), "the player's tier is marked")
    H.contains(P.detail.foot:GetText(), "22 teams count for rewards  -  too few for titles")
    -- checklist
    P.detail.views[2]:Click()
    H.ok(P.detail.checklist:IsVisible())
    local lines = {}
    for _, l in ipairs(P.detail.checklist.lines) do
        if l:IsShown() then lines[#lines + 1] = l.text:GetText() end
    end
    H.eq(#lines, 6, "games, share, personal, recent, wins, level")
    H.eq(lines[1], "Season games: 44")
    H.eq(lines[5], "Season wins: 30 - too few for Gladiator and Rank One")
    H.eq(lines[3], "Personal rating close enough to the team's (1890)")
    P.detail.brackets[1]:Click()
    lines = {}
    for _, l in ipairs(P.detail.checklist.lines) do
        if l:IsShown() then lines[#lines + 1] = l.text:GetText() end
    end
    H.eq(#lines, 4, "1v1 has no team share or personal rating")
    P.detail.brackets[2]:Click()
    H.contains(P.detail.empty:GetText(), "no 2v2 team")
    H.ok(P.cards[2].pvp:IsShown(), "the 2v2 card points at the PvP window")
    P.cards[2].pvp:Click()
    H.eq(M.pvpFrameToggled, 1)
    P.head.pvp:Click()
    H.eq(M.pvpFrameToggled, 2)
    -- rewards: season 1 replaces the season-0 mount of 3v3 Gladiator; season 2's row is not this season's
    P.detail.brackets[3]:Click()
    P.detail.views[3]:Click()
    H.ok(P.detail.rewards:IsVisible())
    local tiers = ns.Arena.Rewards(3, 1)
    H.eq(#tiers, 3)
    H.eq(tiers[1].tierId, 5)
    H.eq(#tiers[1].rows, 2, "the season's mount and Shards")
    H.eq(tiers[1].rows[2].text, "Swift Nether Drake")
    H.eq(tiers[3].rows[1].text, "150 Dungeon Shards")
    local r1 = P.detail.rewards.lines[1]
    H.contains(r1.label:GetText(), "Gladiator")
    H.eq(r1.text:GetText(), "1,200 Dungeon Shards, Mount: Swift Nether Drake")
    H.contains(P.detail.rewards.lines[2].text:GetText(), "Title: Challenger")
    H.contains(P.detail.foot:GetText(), "Too few teams for titles this season")
    H.eq(#ns.Arena.Rewards(3, 2)[1].rows, 1, "season 2: its own mount only")
    H.eq(ns.Arena.Rewards(3, 2)[1].rows[1].text, "Merciless Nether Drake")
end)

test("arena: final standings and grant states on the cards and the checklist", function(M, ns)
    connect(M)
    arena(M, { [2] = 5, [6] = 0 }, { { "F", 1, 12, 1734, 3, 1 }, { "F", 3, 4, 1912, 4, 2 } })
    local P = openPage(M, ns)
    H.eq(P.head.state.text:GetText(), "Rewards delivered")
    H.contains(P.cards[1].next:GetText(), "Final #12")
    H.eq(P.cards[1].status:GetText(), "Rewards delivered")
    H.eq(P.cards[3].status:GetText(), "Rewards held for review")
    P.detail.views[2]:Click()
    local last
    for _, l in ipairs(P.detail.checklist.lines) do
        if l:IsShown() then last = l.text:GetText() end
    end
    H.contains(last, "Final standing: #12  -  1734")
    H.contains(last, "Rewards delivered")
    -- the same finals in a live state are not shown
    arena(M, nil, { { "F", 1, 12, 1734, 3, 1 } })
    M.Advance(0.1)
    H.eq(P.cards[1].next:GetText(), "+66 to Duelist")
end)

test("arena: the next-tier bar from the cutoffs, and from LBME when the shown board is this bracket", function(M, ns)
    connect(M)
    arena(M)
    local AR = ns.Arena
    -- 1v1: Rival takes 1702 now, Duelist 1734 + 66 = 1800
    H.ok(math.abs(AR.NextBar(1) - (1734 - 1702) / (1800 - 1702)) < 1e-6, "from ARENA T")
    H.eq(AR.NextBar(2), nil, "no team")
    H.send(M, "LB", { { "A", 0, 3, 0, 1, 1 } })
    H.send(M, "LBME", { { "A", 4, 19, 1912, 3, "", 407, "Duelist", 182, 4 } })
    H.ok(math.abs(AR.NextBar(3) - 0.407) < 1e-6, "LBME barPermille")
    local P = openPage(M, ns)
    H.ok(P.cards[3].bar:IsShown())
    H.ok(math.abs(P.cards[3].bar:GetValue() - 0.407) < 1e-6)
end)

test("arena: match verdicts read as sentences in the tooltips", function(M, ns)
    connect(M)
    arena(M)
    local AR = ns.Arena
    local s, long = AR.Verdict({ verdict = 2, reason = "E" })
    H.eq(s, "Not counted: no contest")
    H.contains(long, "the losers did next to nothing")
    H.eq(AR.Verdict({ verdict = 2, reason = "S" }), "Not counted: too short")
    H.eq(AR.Verdict({ verdict = 2, reason = "R" }), "Not counted: rematch")
    H.eq(AR.Verdict({ verdict = 2, reason = "Q" }), "Not counted", "an unknown reason")
    H.eq(AR.Verdict({ verdict = 0 }), nil)
    local P = openPage(M, ns)
    local row = P.matches.rows[3]
    local tip = row.tooltip()
    H.eq(tip[1], "Won against Dalia")
    H.eq(tip[3][1], "Win not counted: a winner and a loser play from the same network.")
    H.contains(tip[4][1], "the losers lost as usual")
end)

------------------------------------------------------------------------------------------------------
-- The Arena leaderboard
------------------------------------------------------------------------------------------------------
test("arena leaderboard: LBQ A with the bracket, the arena seasons and the class; rows, flags, standing", function(M, ns)
    connect(M)
    arena(M, nil, { { "S", 7, "Arena Season 0", 0, 1, 2 } })
    local LB = ns.Leaderboards
    ns.UI.Open("leaderboards")
    M.Advance(0.3)
    tab(ns, "A"):Click()
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "LBQ").payload, "A,0,3,0,1", "3v3 of the current season by default")
    H.eq(LB.filters.dungeon.label:GetText(), "3v3")
    H.ok(texts(M, "Bracket") > 0, "the dungeon filter is the bracket")
    LB.filters.dungeon:SetValue(1)
    H.eq(H.lastIntent(M, "LBQ").payload, "A,0,1,0,1")
    LB.filters.class:SetValue(8)
    H.eq(H.lastIntent(M, "LBQ").payload, "A,0,1,8,1")
    local items = LB.filters.season.items
    H.eq(items[1].value, 0); H.eq(items[1].text, "Arena Season 1")
    H.eq(items[2].value, 7, "past seasons follow; upcoming ones are left out")
    H.eq(#items, 2)
    LB.filters.season:SetValue(7)
    H.eq(H.lastIntent(M, "LBQ").payload, "A,7,1,8,1")
    local now = M.env.time()
    H.send(M, "LB", { { "A", 7, 1, 8, 1, 1 },
        { 1, 1, 2140, "", now - 3600, { { "Brenna", 2 } }, "Brenna", 61, 70, 6, 4 },
        { 2, 1, 2075, "", now - 7200, { { "Corwin", 5 } }, "Corwin", 55, 68, 5, 4 },
        { 3, 1, 1990, "", now - 9000, { { "Dalia", 8 } }, "Dalia", 40, 52, 4, 4 },
        { 4, 1, 1912, "", now - 9 * 86400, { { "Eamon", 11 } }, "Eamon", 30, 50, 3, 5 },
        { 5, 1, 1700, "", now - 3600, { { "Fenna", 3 } }, "Fenna", 8, 12, 2, 6 } })
    H.send(M, "LBME", { { "A", 1, 1, 2140, 1, "", 1000, "Rank One", 4, 6 } })
    M.Advance(0.3)
    local rows = LB.table.rows
    H.eq(rows[1].cells[1]:GetText(), "4")
    H.contains(rows[1].cells[2]:GetText(), "Eamon")
    H.eq(rows[1].cells[3]:GetText(), "1912")
    H.eq(rows[1].cells[4]:GetText(), "30-20")
    H.contains(rows[1].cells[5]:GetText(), "Rival")
    H.contains(rows[1].cells[6]:GetText(), "Inactive")
    H.contains(rows[2].cells[5]:GetText(), "Provisional")
    H.eq(LB.podium.boxes[1].value:GetText(), "2140")
    H.contains(LB.podium.boxes[1].time:GetText(), "Rank One")
    H.contains(LB.podium.boxes[1].time:GetText(), "61-9")
    H.eq(LB.best.value:GetText(), "2140")
    H.eq(LB.best.rank:GetText(), "Rank 1  -  top 0.4%")
    H.contains(LB.best.detail:GetText(), "final")
    -- a team bracket: the team's name, the members under it on the podium
    H.send(M, "LB", { { "A", 0, 3, 0, 1, 1 },
        { 1, 3, 2140, "", now, { { "Brenna", 2 }, { "Corwin", 5 }, { "Dalia", 8 } }, "Dawnbreakers", 61, 70, 6 } })
    H.send(M, "LBME", { { "A" } })
    LB.bracket = 3
    LB.Refresh()
    H.eq(LB.podium.boxes[1].group:GetText(), "Dawnbreakers")
    H.contains(LB.podium.boxes[1].dungeon:GetText(), "Corwin")
    H.eq(LB.best.detail:GetText(), "No 3v3 team on this ladder")
    -- the Arena page's button opens its bracket
    ns.Arena.page.bracket = 1
    openPage(M, ns)
    ns.Arena.page.head.board:Click()
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "LBQ").payload, "A,7,1,8,1")
end)

------------------------------------------------------------------------------------------------------
-- Toasts, garbage, demo
------------------------------------------------------------------------------------------------------
test("arena: a new match in ARENA toasts the change, rating, place and pace; click opens the page", function(M, ns)
    connect(M)
    arena(M)
    M.Advance(6)
    local t = M.env.BleakholdToastFrame
    H.ok(not t:IsShown(), "no toast for the first ARENA of the session")
    local now = M.env.time()
    H.send(M, "ARENA", { { 1, 1, now - 86400, now + 86400, "", 1, 0, "Arena Season 1" },
        { "B", 1, 1, 1810, 9, 48, 62, 39, 10, 7, 1810, 15, 4, 5, 140, 0, "Aldric" },
        { "M", 1, 1, 14, "Garrick", now, 0, "" }, { "M", 1, 1, 14, "Brenna", now - 600, 0, "" } })
    H.ok(t:IsShown(), "match toast")
    H.eq(t.title:GetText(), "Won 1v1 against Garrick")
    H.eq(t.sub:GetText(), "+14  -  1810  -  Rank 9  -  Duelist pace  -  up to Duelist")
    H.eq(t.glyph, "shield", "the arena glyph")
    t:Click()
    H.ok(ns.Arena.page:IsVisible(), "opens the Arena page")
    -- the server's TOAST with target arena
    H.send(M, "TOAST", { { "S", "Arena Season 1", "The final week", "arena" } })
    H.eq(t.kicker:GetText(), "SEASON")
    H.eq(t.glyph, "shield")
end)

test("arena: garbage ARENA, unknown brackets, bad colours and long names are survived", function(M, ns)
    connect(M)
    H.send(M, "ARENA", { { "x", 99, "", "", "", "", "", string.rep("N", 200) },
        { "B", 4, 1, 1500 }, { "B", 1, 1, "abc", -5 }, { "T", 7, 1 }, { "T", 3, "" }, { "M", 9, 1 },
        { "F", "", 1 }, { "Z", 1, 2, 3 }, { "S", 0, "zero" } })
    local a = ns.S.arena
    H.eq(a.seasonId, 0); H.eq(a.state, 0); H.eq(#a.seasonName, 48)
    H.eq(a.brackets[4], nil, "bracket 4 is not a bracket")
    H.eq(a.brackets[1].rating, nil)
    H.eq(#a.cutoffs, 0); H.eq(#a.matches, 0); H.eq(#a.seasons, 0)
    H.send(M, "DEF", { { "V", 7 }, { 3, "Rival|r|cffff0000x", "|cffAA", "x" } })
    H.eq(ns.Arena.TierColor(3), ns.UI.C.mid, "a colour that is not six hex digits")
    H.ok(not ns.Arena.TierText(3):find("|r|c", 1, true), "the name's pipes are escaped")
    local P = openPage(M, ns)
    for _, v in ipairs({ "cutoffs", "checklist", "rewards" }) do
        P.view = v
        P:Refresh()
    end
    H.eq(#M.errors, 0, "no Lua errors")
    -- many cutoffs and matches are capped
    local recs = { { 1, 1, "", "", "", 1, 0, "S" } }
    for i = 1, 40 do recs[#recs + 1] = { "T", 3, i, 1, 1, 1, 1 } end
    for i = 1, 9 do recs[#recs + 1] = { "M", 3, 1, i, "X", 1, 0, "" } end
    H.send(M, "ARENA", recs)
    H.eq(#ns.S.arena.cutoffs, 32); H.eq(#ns.S.arena.matches, 5)
end)

test("arena: /bh arena opens the page; /bh arena lb the leaderboard; skirmish and leave", function(M, ns)
    connect(M)
    arena(M)
    M.env.SlashCmdList.BLEAKHOLD("arena")
    M.Advance(0.3)
    H.ok(ns.Arena.page:IsVisible())
    M.env.SlashCmdList.BLEAKHOLD("arena lb")
    M.Advance(0.3)
    H.ok(M.env.BleakholdLeaderboardsFrame:IsShown())
    H.eq(ns.Leaderboards.board, "A")
    M.env.SlashCmdList.BLEAKHOLD("arena skirmish")
    M.Advance(0.3)
    H.eq(table.concat(intentsOf(M, "QJOIN"), " "), "A,1,0,4,1")
    M.env.SlashCmdList.BLEAKHOLD("arena leave")
    M.Advance(0.3)
    H.eq(#intentsOf(M, "QLEAVE"), 0, "not queued: no QLEAVE")
    H.send(M, "QUEUE", { { 9, 1, "A", 1, 0, 1, 0, "" } })
    M.env.SlashCmdList.BLEAKHOLD("arena leave")
    M.Advance(0.3)
    H.eq(#intentsOf(M, "QLEAVE"), 1)
end)

test("arena: /bh demo shows a season, the ladder and a rated 1v1 through the real receive path", function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    local P = openPage(M, ns)
    M.Advance(0.5)
    H.ok(P:IsVisible(), "Arena page in the demo")
    H.eq(P.head.title:GetText(), "Arena Season 1")
    H.eq(P.cards[1].team:GetText(), "No 1v1 team yet")
    H.eq(P.cards[3].rating:GetText(), "1912")
    P.queue.rated:Click()
    local d = M.env.BleakholdDialog
    H.ok(d:IsShown(), "the demo's team costs 10g")
    d.ok:Click()
    M.Advance(1)
    H.eq(P.queue.status:GetText(), "In the rated 1v1 queue")
    M.Advance(5)
    H.eq(P.queue.status:GetText(), "In a rated 1v1 match")
    M.Advance(6)
    H.eq(P.queue.status:GetText(), "Not queued")
    H.eq(P.cards[1].rating:GetText(), "1748", "the won match counted")
    H.ok(texts(M, "Won 1v1 against Garrick") > 0, "the match toast")
    ns.Leaderboards.OpenArena(3)
    M.Advance(1)
    H.ok(texts(M, "Dawnbreakers") > 0, "the demo ladder")
    H.ok(texts(M, "Rank 4  -  top 19%") > 0, "the demo standing")
    local dropped = 0
    for _, v in pairs(ns.Comm.stats.dropped) do dropped = dropped + v end
    H.eq(dropped, 0, "no frame dropped")
    H.eq(ns.Comm.stats.unknown, 0)
end)
