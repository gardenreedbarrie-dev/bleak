-- Activities' Tasks page and title bar (Activities.lua): the daily and weekly resets roll on after HELLO's (sent once,
-- bh_ui_bridge.cpp SetResetTimesSource), and the new day is asked for once; the bounty cards show their goal in up to
-- three lines with the whole of it in their tooltip (bh_ui_bridge_map.cpp BountyTasks); the weekly bonus box grows to
-- its text (bh_ui_bridge.cpp EchoBonusText) with the whole of it in its tooltip.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local DAY, WEEK = 86400, 604800

local function getsOf(M, topic, from)
    local n = 0
    for _, it in ipairs(H.intents(M, from)) do
        if it.op == "GET" then
            for _, r in ipairs(it.records) do
                if r[1] == topic then n = n + 1 end
            end
        end
    end
    return n
end

test("resets: NextReset rolls a passed reset on by whole periods", function(M, ns)
    local A = ns.Activities
    H.eq(A.NextReset(1000, DAY, 500), 1000, "still to come")
    H.eq(A.NextReset(1000, DAY, 1000), 1000 + DAY, "at the reset: the next one")
    H.eq(A.NextReset(1000, DAY, 1001), 1000 + DAY)
    H.eq(A.NextReset(1000, DAY, 1000 + 3 * DAY + 5), 1000 + 4 * DAY, "days later")
    H.eq(A.NextReset(1000, WEEK, 1000 + WEEK - 1), 1000 + WEEK)
    H.eq(A.NextReset(nil, DAY, 5), nil)
end)

test("resets: after the daily reset the pill counts to the next one and the new day is asked for once", function(M, ns)
    local now = M.env.time()
    -- HELLO: the daily reset in 30 s, the weekly one in 3 days
    FX.connect(M, H, { [3] = now, [8] = now + 30, [9] = now + 3 * DAY })
    FX.all(M, H)
    ns.UI.Open("tasks")
    M.Advance(1.2)
    local A = ns.Activities
    local daily = A.resetTexts[1]
    H.eq(daily.text:GetText(), "Daily reset  < 1 min")
    local from = #M.sent + 1
    -- past the reset, then a few minutes more
    M.Advance(40, 0.5)
    H.contains(daily.text:GetText(), "Daily reset  23 h ", "the next day's reset, never 'now'")
    H.eq(getsOf(M, "TASKS", from), 1, "the new day's tasks, once")
    H.eq(getsOf(M, "WEEK", from), 1)
    H.eq(getsOf(M, "ERA", from), 1)
    M.Advance(180, 1)
    H.eq(getsOf(M, "TASKS", from), 1, "not again every minute")
    H.eq(getsOf(M, "WEEK", from), 1)
    H.ok(not daily.text:GetText():find("now", 1, true), daily.text:GetText())
    -- a day later the next reset passes: asked once more
    M.Advance(DAY - 200, 60)
    M.Advance(30, 0.5)
    H.eq(getsOf(M, "TASKS", from), 2, "the next day, once more")
    H.contains(daily.text:GetText(), "Daily reset  23 h ")
end)

test("resets: the weekly reset rolls on a week; a weekly reset alone asks for the week and the era", function(M, ns)
    local now = M.env.time()
    FX.connect(M, H, { [3] = now, [8] = now + 7200, [9] = now + 20, [4] = 0 })
    FX.all(M, H)
    ns.UI.Open("tasks")
    M.Advance(1.2)
    local A = ns.Activities
    local weekly = A.resetTexts[2]
    local before = weekly.text:GetText()
    local from = #M.sent + 1
    M.Advance(30, 0.5)
    H.eq(getsOf(M, "WEEK", from), 1, "the week once")
    H.eq(getsOf(M, "ERA", from), 1, "the era once")
    H.eq(getsOf(M, "TASKS", from), 0, "no daily reset passed")
    H.eq(weekly.text:GetText(), before, "the same weekday and time, a week on")
    H.eq(A.SeenResets().weekly, now + 20 + WEEK)
    M.Advance(120, 1)
    H.eq(getsOf(M, "WEEK", from), 1, "once")
end)

test("resets: a new HELLO starts the seen resets again", function(M, ns)
    local now = M.env.time()
    FX.connect(M, H, { [3] = now, [8] = now + 10, [9] = now + 3 * DAY })
    ns.UI.Open("tasks")
    M.Advance(20, 0.5)
    local A = ns.Activities
    H.eq(A.SeenResets().daily, now + 10 + DAY, "rolled on")
    H.hello(M, { [3] = M.env.time(), [8] = now + 5000, [9] = now + 4 * DAY })
    M.Advance(1.2)
    H.eq(A.SeenResets().daily, now + 5000, "the new HELLO's")
    H.eq(A.SeenResets().weekly, now + 4 * DAY)
end)

test("bounty cards: the goal gets three lines down to the reward row; the card's tooltip has it all", function(M, ns)
    FX.connect(M, H)
    -- bleakserv's BountyTasks: the tier as the title, the goal as the text
    H.send(M, "TASKS", {
        { 1, 0, 0, "G" },
        { 101, "D", 1, 1, 2, "S", 40, "", 0, "Easy bounty", "Complete 2 Journey runs." },
        { 102, "D", 2, 0, 1, "S", 60, "", 0, "Medium bounty", "Finish a run with a score of 85% or more." },
        { 103, "D", 3, 1, 1, "S", 90, "", 1, "Hard bounty", "Finish a Today's Board run with 3+ modifiers." },
    }, 90)
    ns.UI.Open("tasks")
    M.Advance(0.5)
    local P = ns.Activities.tasksPage
    local c = P.cards[2]
    H.eq(c.title:GetText(), "Medium bounty")
    H.eq(c.text:GetText(), "Finish a run with a score of 85% or more.")
    H.eq(c.text:GetHeight(), 44, "three 11 px lines")
    local _, _, _, _, textY = c.text:GetPoint(1)
    local _, _, _, _, claimY = c.claim:GetPoint(1)
    H.ok(-textY + c.text:GetHeight() <= c:GetHeight() - claimY - c.claim:GetHeight(), "above the Claim row")
    M.Hover(c)
    local tip = M.env.GameTooltip.__lines
    H.eq(tip[1], "Medium bounty")
    H.eq(tip[2], "Finish a run with a score of 85% or more.")
    H.eq(tip[3], "0 / 1")
    H.eq(tip[4], "Reward: 60 Shards")
    M.Hover(c, false)
    H.ok(not M.env.GameTooltip:IsShown())
    M.Hover(P.cards[1])
    H.eq(M.env.GameTooltip.__lines[3], "1 / 2")
    M.Hover(P.cards[1], false)
    M.Hover(P.cards[3])
    H.eq(M.env.GameTooltip.__lines[3], "Complete", "a finished bounty")
    M.Hover(P.cards[3], false)
end)

test("bounty cards: the live server's goal-as-title is cut on the card and whole in the tooltip", function(M, ns)
    FX.connect(M, H)
    local goal = "Finish a run with a score of 85% or more"
    H.send(M, "TASKS", {
        { 1, 0, 0, "G" },
        { 101, "D", 1, 0, 1, "S", 40, "", 0, goal,
            "Dungeon Journey bounty. The Shards are paid the moment it is done." },
    }, 90)
    ns.UI.Open("tasks")
    M.Advance(0.5)
    local c = ns.Activities.tasksPage.cards[1]
    H.eq(c.title:GetHeight(), 16, "the title stays one line")
    M.Hover(c)
    H.eq(M.env.GameTooltip.__lines[1], goal, "the whole goal")
    H.eq(M.env.GameTooltip.__lines[2], "Dungeon Journey bounty. The Shards are paid the moment it is done.")
    M.Hover(c, false)
    -- an empty card has no tooltip
    local empty = ns.Activities.tasksPage.cards[3]
    H.eq(empty.tip, nil)
end)

test("weekly bonus: the text takes the lines it needs, the box grows, the tooltip has it all", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("tasks")
    M.Advance(0.5)
    local A = ns.Activities
    local P = A.tasksPage
    local bonus = P.bonus
    H.ok(bonus:IsShown())
    local shortH = bonus:GetHeight()
    local long = "The first Raid Lord Echo you defeat each week gives a guaranteed piece of its era. Raid Lords "
        .. "appear after higher keystones and on deep Eclipse Rift floors."
    H.send(M, "DEF", { { "B", 7 }, { 1, "First Raid Lord Echo", long } })
    P:Refresh()
    H.eq(bonus.text:GetText(), long, "the whole text is set")
    local n = A.WrappedLines(bonus.text, bonus.text:GetWidth(), P.BONUS_LINES)
    H.ok(n >= 5, "a 155-character text wraps to 5 or more lines: " .. n)
    H.eq(bonus.text:GetHeight(), n * 11 + (n - 1) * 2 + 4, "the text as tall as its lines")
    H.ok(bonus:GetHeight() > shortH, "the box grows")
    -- the state line stays under the text, inside the box
    local _, _, _, _, stateY = bonus.state:GetPoint(1)
    H.eq(stateY, 10)
    -- room: the box ends above Find a group
    local _, _, _, _, boxY = bonus:GetPoint(1)
    local findTop = A.CH - 18 - P.find:GetHeight()
    H.ok(-boxY + bonus:GetHeight() < findTop, "above Find a group")
    M.Hover(bonus)
    H.eq(M.env.GameTooltip.__lines[1], "First Raid Lord Echo")
    H.eq(M.env.GameTooltip.__lines[2], long)
    M.Hover(bonus, false)
    -- no more than six lines
    H.send(M, "DEF", { { "B", 7 }, { 1, "First Raid Lord Echo", string.rep("word ", 39) } })
    P:Refresh()
    H.eq(bonus.text:GetHeight(), 6 * 11 + 5 * 2 + 4, "at most six lines")
end)
