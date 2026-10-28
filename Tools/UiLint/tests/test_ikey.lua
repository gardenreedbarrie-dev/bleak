-- The I key opens Activities again (Activities.lua): once per set of key bindings (the account's, or a character's
-- own), only from the stock Dungeon Finder (TOGGLELFGPARENT) or an unbound I, never a key the player gave anything
-- else; and the stock Dungeon Finder stays a click away in Activities > Dungeons.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function stockKeys(M)
    M.bindings["I"] = "TOGGLELFGPARENT"
end

test("I key: taken from the stock Dungeon Finder once, saved in the current set", function(M, ns)
    H.eq(M.bindings["I"], "TOGGLELFGPARENT", "not before the bindings are in place")
    M.Advance(1.5)
    H.eq(M.bindings["I"], "BLEAKHOLD_ACTIVITIES", "I opens Activities")
    H.ok(M.savedBindings >= 1, "saved")
    H.ok(M.env.BleakholdDB.options.activitiesKeyOffered, "offered once for the account's key bindings")
    local said = false
    for _, line in ipairs(M.chat) do
        if line.msg and line.msg:find("Dungeon Finder", 1, true) then said = true end
    end
    H.ok(said, "says where the Dungeon Finder went")
    -- the key works: Bindings.xml runs BleakholdToggle("activities")
    M.env.BleakholdToggle("activities")
    H.ok(M.env.BleakholdActivitiesFrame:IsShown(), "Activities opens")
    -- the player puts the finder back on I: never taken again
    M.bindings["I"] = "TOGGLELFGPARENT"
    M.FireEvent("PLAYER_ENTERING_WORLD")
    M.Advance(1.5)
    H.eq(M.bindings["I"], "TOGGLELFGPARENT", "a key the player set back stays")
end, { before = stockKeys })

test("I key: an unbound I is taken", function(M, ns)
    M.Advance(1.5)
    H.eq(M.bindings["I"], "BLEAKHOLD_ACTIVITIES")
end)

test("I key: a key the player gave something else stays theirs", function(M, ns)
    M.Advance(1.5)
    H.eq(M.bindings["I"], "TOGGLEBACKPACK", "not taken")
    H.ok(M.bindings["J"] == nil and M.env.GetBindingKey("BLEAKHOLD_ACTIVITIES") == nil, "and no other key is taken")
    H.eq(M.savedBindings, 1, "only the emote wheel's Ctrl+G was saved")
end, { before = function(M) M.bindings["I"] = "TOGGLEBACKPACK" end })

test("I key: Activities already on a key of the player's: I stays the Dungeon Finder", function(M, ns)
    M.Advance(1.5)
    H.eq(M.bindings["I"], "TOGGLELFGPARENT")
    H.eq(M.bindings["SHIFT-J"], "BLEAKHOLD_ACTIVITIES")
end, { before = function(M)
    stockKeys(M)
    M.bindings["SHIFT-J"] = "BLEAKHOLD_ACTIVITIES"
end })

test("I key: offered once per account set, not again on another character that uses it", function(M, ns)
    M.Advance(1.5)
    H.eq(M.bindings["I"], "TOGGLELFGPARENT", "this account's key bindings were offered it already")
end, { before = function(M)
    stockKeys(M)
    M.env.BleakholdDB = { options = { activitiesKeyOffered = true } }
end })

-- Saved variables carried from one login to the next: the account's (BleakholdDB) always, the character's
-- (BleakholdCharDB) only when it is the same character. A deep copy, like the client's SavedVariables file.
local function copy(t)
    if type(t) ~= "table" then return t end
    local out = {}
    for k, v in pairs(t) do out[k] = copy(v) end
    return out
end

local function login(prev, sameCharacter, set)
    return H.newGame({ before = function(M)
        stockKeys(M)
        M.bindingSet = set
        M.env.BleakholdDB = copy(prev.env.BleakholdDB)
        if sameCharacter then
            M.env.BleakholdCharDB = copy(prev.env.BleakholdCharDB)
            M.bindings["I"] = prev.bindings["I"]
        end
    end })
end

test("I key: a character with its own key bindings is offered it in its set; the account's set still gets it",
    function(M, ns)
    M.Advance(1.5)
    H.eq(M.bindings["I"], "BLEAKHOLD_ACTIVITIES", "I opens Activities on this character")
    H.eq(M.savedBindingSets[#M.savedBindingSets], 2, "saved into the character's own set")
    H.ok(M.env.BleakholdCharDB.activitiesKeyOffered, "offered: kept with the character's set")
    H.ok(not M.env.BleakholdDB.options.activitiesKeyOffered, "the account's set was not offered it")
    -- the next login: another character, on the account's key bindings, where I is still the Dungeon Finder
    local M2 = login(M, false, 1)
    M2.Advance(1.5)
    H.eq(M2.bindings["I"], "BLEAKHOLD_ACTIVITIES", "the account's set is offered it too")
    H.eq(M2.savedBindingSets[#M2.savedBindingSets], 1, "saved into the account's set")
    H.ok(M2.env.BleakholdDB.options.activitiesKeyOffered, "and now counts as offered")
    -- the first character again, with I given back to the finder: never taken twice from the same set
    local M3 = H.newGame({ before = function(N)
        N.bindingSet = 2
        N.bindings["I"] = "TOGGLELFGPARENT"
        N.env.BleakholdDB = copy(M2.env.BleakholdDB)
        N.env.BleakholdCharDB = copy(M.env.BleakholdCharDB)
    end })
    M3.Advance(1.5)
    H.eq(M3.bindings["I"], "TOGGLELFGPARENT", "the character's set was offered it already")
end, { before = function(M)
    stockKeys(M)
    M.bindingSet = 2
end })

test("I key: the account's set offered first; a character that then uses its own set is offered it there",
    function(M, ns)
    M.Advance(1.5)
    H.eq(M.bindings["I"], "BLEAKHOLD_ACTIVITIES")
    H.eq(M.savedBindingSets[#M.savedBindingSets], 1, "the account's set")
    H.ok(not M.env.BleakholdCharDB.activitiesKeyOffered, "nothing kept per character for the account's set")
    -- the same character ticks Character Specific Key Bindings: its new set starts from the stock keys
    local M2 = login(M, true, 2)
    M2.bindings["I"] = "TOGGLELFGPARENT"
    M2.FireEvent("PLAYER_ENTERING_WORLD")
    M2.Advance(1.5)
    H.eq(M2.bindings["I"], "BLEAKHOLD_ACTIVITIES", "its own set is offered it")
    H.eq(M2.savedBindingSets[#M2.savedBindingSets], 2)
    -- back on the account's set (another character): offered there already, I stays as the player left it
    local M3 = login(M2, false, 1)
    M3.Advance(1.5)
    H.eq(M3.bindings["I"], "TOGGLELFGPARENT", "the account's set is not offered it twice")
end, { before = stockKeys })

test("I key: not in combat, taken when combat ends", function(M, ns)
    M.combat = true
    M.Advance(1.5)
    H.eq(M.bindings["I"], "TOGGLELFGPARENT", "never in combat")
    H.ok(not M.env.BleakholdDB.options.activitiesKeyOffered, "still to offer")
    M.combat = false
    M.FireEvent("PLAYER_REGEN_ENABLED")
    M.Advance(1)
    H.eq(M.bindings["I"], "BLEAKHOLD_ACTIVITIES", "taken once combat is over")
end, { before = function(M)
    stockKeys(M)
    M.combat = true
end })

test("Dungeon Finder: Activities > Dungeons opens the game's own finder", function(M, ns)
    FX.connect(M, H)
    M.env.SlashCmdList.BLEAKHOLD("dungeons")
    local button = ns.Dungeons.finder
    H.ok(button:IsVisible(), "the button shows on the Dungeons page")
    H.contains(button.label:GetText(), "Dungeon Finder")
    local lines = button.tooltip()
    H.eq(lines[1], "Dungeon Finder")
    H.contains(lines[3][1], "Key Bindings", "no key yet: says where to give it one")
    M.bindings["SHIFT-I"] = "TOGGLELFGPARENT"
    H.contains(button.tooltip()[3][1], "SHIFT-I", "names the finder's key")
    button:Click()
    H.ok(M.env.LFDParentFrame:IsShown(), "the stock Dungeon Finder opens")
    H.ok(not M.env.BleakholdActivitiesFrame:IsShown(), "Activities makes room for it")
end)
