-- Scenes of Bleakhold Royale's drop countdown (RoyaleCountdown.lua, the DBM style): the lobby's last 15 s driven by
-- ROYM/ROYS states set straight into State, as the realm sends them.
--
--   Tools/UiLint/preview/render.sh Tools/UiLint/preview/scenes/royale_countdown.lua t5 out.png --bg ground \
--       --stock <stock art>
--
-- t15, t9, t5, t3pop, t1, drop, cancel: the countdown centred (the lobby map closed); docked: at T-12 beside the
-- lobby map, which opened by itself; dbm: with DBM loaded (its bar is DBM's own, so ours hides).
local S = {}

local PLACES = {
    { 5213, "Y", 455, 455, 32, "Sunwatch Overlook" },
    { 5201, "L", -258, -345, 95, "Sunstair Isle" }, { 5202, "L", -45, -170, 90, "Tidecall Village" },
    { 5203, "L", 320, -790, 80, "Twinfall Terrace" }, { 5206, "L", -250, 200, 90, "Sunbloom Meadow" },
    { 5210, "L", 360, 250, 60, "Sunwatch Falls" }, { 5214, "C", -150, -275, 14, "Tidewalk" },
}

local function setMap(M, ns)
    local m = { mapId = 901, minX = -1066, maxX = 533, minY = -1066, maxY = 533, lobbyX = 455, lobbyY = 455,
        lobbyR = 32, boundHalf = 750, centerX = -267, centerY = -267, pois = {}, recvAt = M.now }
    for _, p in ipairs(PLACES) do
        m.pois[#m.pois + 1] = { id = p[1], kind = p[2], x = p[3], y = p[4], r = p[5], name = p[6] }
    end
    ns.S.royaleMap = m
    ns.Fire("STATE", "ROYM")
end

local function push(M, ns, over)
    local m = { matchId = 7001, phase = 1, phaseMsLeft = 40000, alive = 24, total = 24, me = 0, kills = 0, stage = 0,
        curX = -267, curY = -267, curR = 860, nextX = -150, nextY = -310, nextR = 520, dmgPermille = 0, stages = 6,
        pinX = -45, pinY = -170, myX = 452, myY = 450, recvAt = M.now }
    for k, v in pairs(over or {}) do m[k] = v end
    local old = ns.S.royale
    ns.S.royale = m
    if not old or old.matchId ~= m.matchId then ns.Fire("ROYALE_MATCH", m) end
    ns.Fire("STATE", "ROYS")
end

-- The lobby, then the exact ROYS of T-15; `left` s before the drop on return (negative: after it). keepMap leaves the
-- lobby map open (it opened by itself), else it is closed by hand before the countdown starts.
local function lobby(M, ns, left, keepMap)
    setMap(M, ns)
    ns.S.queue = { kind = "B", state = 3, maxPlayers = 40, minPlayers = 20, members = {} }
    push(M, ns, { phaseMsLeft = 30000 })
    M.Advance(0.3)
    if not keepMap and ns.RoyaleMap.Close then
        ns.RoyaleMap.Close(true)
        M.Advance(0.05)
    end
    push(M, ns, { phaseMsLeft = 15000 })
    local n = math.floor((15 - left) / 0.05 + 0.5)
    for _ = 1, n do M.Advance(0.05, 0.05) end
end

-- the countdown's own frame and the top bar above it (the lobby map too when it is open)
local function frames(env, withMap)
    local list = { env.BleakholdRoyaleCountdown, env.BleakholdRoyaleBar }
    if withMap then list[#list + 1] = env.BleakholdRoyaleMapFrame end
    return list
end

local function at(left)
    return function(M, ns, RS, env)
        lobby(M, ns, left)
        return frames(env)
    end
end

S.t15 = at(14.7)        -- the bar has just come in
S.t9 = at(9.4)          -- one decimal from 10 s
S.t5 = at(4.6)          -- the 5 settled with its glow
S.t3pop = at(2.97)      -- the 3 popping in
S.t1 = at(0.6)
S.drop = at(-0.08)      -- DROP! slamming in, the edge flashing

S.cancel = function(M, ns, RS, env)
    lobby(M, ns, 8)
    push(M, ns, { phase = 7, phaseMsLeft = 0 })
    M.Advance(0.5)
    return frames(env)
end

S.docked = function(M, ns, RS, env)
    lobby(M, ns, 12, true)
    return frames(env, true)
end

S.dbm = function(M, ns, RS, env)
    env.DBM = { Bars = {} }
    function env.DBM:CreatePizzaTimer() end
    lobby(M, ns, 4.6)
    return frames(env)
end

return S
