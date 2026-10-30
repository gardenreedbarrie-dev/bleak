-- The Dungeon Journey's custom run tooltip (Dungeons.lua P.CustomTip): the player's best and the server record are
-- percentages (bh_dungeon.cpp caps a Journey score at 100: "87% in 12:30"), and the record is the one of the best's
-- tier, Normal without a best (bleakserv bh_ui_bridge_map.cpp BoardRecord), so it carries that tier's name and the two
-- compare. BOARD records: dungeonId, chapter, lvlMin, lvlMax, tierBits, bestScore, bestTier, recordScore, recordName,
-- locked (docs/BleakholdProtocol.md, BOARD).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function tipText(lines)
    local out = {}
    for _, l in ipairs(lines) do
        out[#out + 1] = type(l) == "table" and l[1] or l
    end
    return table.concat(out, "\n")
end

local BOARD = {
    { 1, 1260, 0, 0, 0, "", 1 },
    { 36, 1, 15, 21, 1, 95, 0, 98, "Ana's group", 0 },
    { 33, 1, 18, 25, 7, 64, 2, 88, "Brenna", 0 },
    { 189, 2, 30, 40, 1, "", "", 92, "Dalia", 0 },
    { 209, 3, 42, 48, 1, "", "", "", "", 0 },
}

test("journey tip: the best and the server record are percentages of the same tier", function(M, ns)
    FX.connect(M, H)
    M.playerLevel = 20
    H.send(M, "BOARD", BOARD)
    local byId = ns.S.board.byId
    local P = ns.Dungeons
    local tip = tipText(P.CustomTip(byId[36]))
    H.contains(tip, "Your best: 95% (Normal)")
    H.contains(tip, "Server record: 98% (Normal) - Ana's group")
    tip = tipText(P.CustomTip(byId[33]))
    H.contains(tip, "Your best: 64% (Elite)")
    H.contains(tip, "Server record: 88% (Elite) - Brenna", "the record of the best's tier, named with it")
    tip = tipText(P.CustomTip(byId[189]))
    H.contains(tip, "No run here yet")
    H.contains(tip, "Server record: 92% (Normal) - Dalia", "Normal without a best")
    tip = tipText(P.CustomTip(byId[209]))
    H.ok(not tip:find("Server record", 1, true), "no record line without a record")
    for id in pairs({ [36] = true, [33] = true, [189] = true }) do
        for line in tipText(P.CustomTip(byId[id])):gmatch("[^\n]+") do
            if line:find("^Your best") or line:find("^Server record") then
                H.ok(line:find("^[^:]+: %d+%% %(%a+%)"), "a percentage and its tier: " .. line)
            end
        end
    end
end)

test("journey tip: a score over 100 reads 100% (the server's cap)", function(M, ns)
    local P = ns.Dungeons
    H.eq(P.Percent(87), "87%")
    H.eq(P.Percent(250), "100%")
    H.eq(P.Percent(nil), "0%")
    local tip = tipText(P.CustomTip({ id = 36, chapter = 1, bestScore = 101, bestTier = 3, recordScore = 100,
        recordName = "Ana's group" }))
    H.contains(tip, "Your best: 100% (Nightmare)")
    H.contains(tip, "Server record: 100% (Nightmare) - Ana's group")
end)
