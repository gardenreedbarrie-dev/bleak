-- Activities > Heroic (Heroic.lua): a Dungeon Finder group leader outside a dungeon can set Normal and Heroic but not
-- Mythic (the bridge's SetDifficulty: "Mythic difficulty is not for Dungeon Finder groups."); the page's difficulty
-- line and the greyed Mythic button's tooltip say so, rather than "the party leader sets it, outside dungeons".
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function tipText(lines)
    local out = {}
    for _, l in ipairs(lines) do
        out[#out + 1] = type(l) == "table" and l[1] or l
    end
    return table.concat(out, "\n")
end

test("heroic page: a Dungeon Finder group leader is told why Mythic is greyed", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    ns.UI.Open("heroic")
    M.Advance(0.3)
    local P = ns.Heroic
    -- the leader of a plain party in Dalaran: every mode, the leader's rule
    M.SetGroup("PARTY", 5, true)
    M.env.GetLFGInfoServer = function() return true, false, false end
    M.env.IsPartyLFG = function() return nil end
    P:Refresh()
    H.ok(P.modes[3]:IsEnabled())
    H.contains(P.diff:GetText(), "the party leader sets it, outside dungeons")
    H.ok(not tipText(P.modes[3].tooltip()):find("Dungeon Finder", 1, true), "no refusal to tell")
    -- still grouped with a Dungeon Finder group after its run (IsPartyLFG)
    M.env.IsPartyLFG = function() return 1 end
    P:Refresh()
    H.ok(P.modes[1]:IsEnabled() and P.modes[2]:IsEnabled(), "Normal and Heroic stay")
    H.ok(not P.modes[3]:IsEnabled(), "not Mythic")
    H.contains(P.diff:GetText(), "Mythic difficulty is not for Dungeon Finder groups.", "the server's reason")
    H.ok(not P.diff:GetText():find("the party leader sets it", 1, true), "not the rule the leader already meets")
    H.contains(tipText(P.modes[3].tooltip()), "Mythic difficulty is not for Dungeon Finder groups.")
    H.ok(not tipText(P.modes[2].tooltip()):find("Dungeon Finder", 1, true), "Heroic is not refused")
    -- a member who is not the leader: every mode is refused, and that is said first
    M.SetGroup("PARTY", 5, false)
    P:Refresh()
    H.contains(P.diff:GetText(), "Only the group leader can change the dungeon difficulty.")
    H.contains(tipText(P.modes[2].tooltip()), "Only the group leader can change the dungeon difficulty.")
    H.contains(tipText(P.modes[3].tooltip()), "Only the group leader can change the dungeon difficulty.")
end)
