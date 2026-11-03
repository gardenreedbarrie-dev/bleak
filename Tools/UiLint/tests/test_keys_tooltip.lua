-- The keystone's item tooltip (Tooltip.lua). Every keystone is the same item (KEY keystoneItemId,
-- BHMP::ITEM_KEYSTONE); its dungeon and level live on the server for its owner only (bh_mplus.cpp SyncKeyItem). So
-- the keystone block is the viewer's own key, shown only where the item is the viewer's: a bag slot (SetBagItem) or a
-- bank slot (SetInventoryItem("player", ...)). A chat link, a comparison or another addon's SetHyperlink shows one
-- dim line instead. The affix names are the server's ids (4 is Raging; Data.lua's built-in DEF A says Volcanic).
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local KEYSTONE = "|cffa335ee|Hitem:900001:0:0:0:0:0:0:0:80|h[Mythic Keystone]|h|r"

local function inBag(M)
    M.env.GetContainerItemLink = function(bag, slot)
        return (bag == 0 and slot == 1) and KEYSTONE or nil
    end
end

local function text(tt)
    return table.concat(tt.__lines or {}, "\n")
end

local function count(s, sub)
    local n, at = 0, 1
    while true do
        local i = s:find(sub, at, true)
        if not i then return n end
        n, at = n + 1, i + #sub
    end
end

test("keystone tooltip: a bag hover shows the player's key, its affixes and mode, once", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    inBag(M)
    local tt = M.env.GameTooltip
    tt:SetOwner(M.env.UIParent, "ANCHOR_NONE")
    tt:SetBagItem(0, 1)
    local t = text(tt)
    H.contains(t, "Halls of Lightning +8")
    H.contains(t, "Affixes: Fortified, Bolstering, Raging", "the server's affix ids")
    H.contains(t, "Dungeon mode: Mythic")
    H.ok(not t:find("does not show its dungeon", 1, true), "no link note on the player's own keystone")
    H.ok(not t:find("Run under way", 1, true), "no run")
    local n = tt:NumLines()
    -- the client fires OnTooltipSetItem again, and the bags set the tooltip again on every update
    M.Fire(tt, "OnTooltipSetItem")
    H.eq(tt:NumLines(), n, "firing again adds nothing")
    tt:SetBagItem(0, 1)
    H.eq(tt:NumLines(), n, "set again: the same lines, once")
    H.eq(count(text(tt), "Halls of Lightning +8"), 1)
    -- an empty slot, another item: nothing of ours
    tt:SetBagItem(0, 2)
    H.eq(tt:NumLines(), 0)
end)

test("keystone tooltip: a bank slot is the player's; a unit's worn item is not", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    M.env.GetInventoryItemLink = function(unit, slot)
        return slot == 40 and KEYSTONE or nil
    end
    local tt = M.env.GameTooltip
    tt:SetOwner(M.env.UIParent, "ANCHOR_NONE")
    tt:SetInventoryItem("player", 40)
    H.contains(text(tt), "Halls of Lightning +8")
    tt:SetInventoryItem("party1", 40)
    H.ok(not text(tt):find("Halls of Lightning", 1, true), "not the player's")
end)

test("keystone tooltip: a chat link, another addon's link and a comparison show only the dim line", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    -- ItemRefTooltip: a keystone someone linked in chat (SetItemRef -> SetHyperlink)
    local ref = M.env.ItemRefTooltip
    ref:SetOwner(M.env.UIParent, "ANCHOR_NONE")
    ref:SetHyperlink("item:900001")
    H.eq(ref:NumLines(), 2, "the item's own line and the note")
    H.eq(ref.__lines[2], "A keystone link does not show its dungeon and level.")
    H.ok(not text(ref):find("Halls of Lightning", 1, true), "not the viewer's own key")
    H.ok(not text(ref):find("Affixes", 1, true))
    M.Fire(ref, "OnTooltipSetItem")
    H.eq(ref:NumLines(), 2, "firing again adds nothing")
    -- GameTooltip:SetHyperlink from another addon (a bag addon, a link hover)
    local tt = M.env.GameTooltip
    tt:SetOwner(M.env.UIParent, "ANCHOR_NONE")
    tt:SetHyperlink("item:900001")
    H.eq(tt:NumLines(), 2)
    H.eq(tt.__lines[2], "A keystone link does not show its dungeon and level.")
    -- the server's keystone item before KEY says which item it is (no keystone: no keystoneItemId)
    tt:SetHyperlink("item:" .. ns.Keys.KEY_ITEM)
    H.eq(tt.__lines[2], ns.Tooltip.LINK_NOTE)
    -- other items keep their own lines
    tt:SetHyperlink("item:6948")
    H.eq(tt:NumLines(), 1)
end)

test("keystone tooltip: no keystone, no block; the link note stays", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    H.send(M, "KEY", { { 2, 0, 0, "", 0, 0, "", 40, 0, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    inBag(M)
    local tt = M.env.GameTooltip
    tt:SetOwner(M.env.UIParent, "ANCHOR_NONE")
    tt:SetBagItem(0, 1)
    H.eq(tt:NumLines(), 1, "an old keystone item without a key: its own line only")
    tt:SetHyperlink("item:900001")
    H.eq(tt.__lines[2], "A keystone link does not show its dungeon and level.")
end)

test("keystone tooltip: 'Run under way' during the player's own run only", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    inBag(M)
    local tt = M.env.GameTooltip
    -- the owner's +8 Halls of Lightning: the bridge sends the run's own key while it runs (BuildKey)
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    M.Advance(0.3)
    tt:SetOwner(M.env.UIParent, "ANCHOR_NONE")
    tt:SetBagItem(0, 1)
    local t = text(tt)
    H.contains(t, "Halls of Lightning +8\nRun under way", "below the dungeon and level")
    -- an older server stored the key one level lower at the start: still the owner's run, at the run's level
    H.send(M, "KEY", { { 2, 602, 7, { 1, 3, 4 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    tt:SetBagItem(0, 1)
    H.contains(text(tt), "Halls of Lightning +8\nRun under way")
    -- a party member in the leader's run: their own Deadmines +3, which the run does not change
    H.send(M, "KEY", { { 3, 36, 3, { 1, 3 }, 0, 0, "", 40, 0, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    tt:SetBagItem(0, 1)
    t = text(tt)
    H.contains(t, "The Deadmines +3")
    H.ok(not t:find("Run under way", 1, true), "not their run")
    -- the run is over (MPE): no note
    H.send(M, "KEY", { { 4, 602, 8, { 1, 3, 4 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    H.send(M, "MPE", { { 7001, 0, 1900000, -1, 602, 7, 0 } })
    M.Advance(0.3)
    tt:SetBagItem(0, 1)
    H.ok(not text(tt):find("Run under way", 1, true), "finished")
end)

test("keystone tooltip: whose run it is comes from the keys the server sends, not from who leads", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    inBag(M)
    local tt = M.env.GameTooltip
    tt:SetOwner(M.env.UIParent, "ANCHOR_NONE")
    -- this player a member with their own +7, depleted, from before the leader's Halls of Lightning +8 starts: not
    -- said to be the run
    M.SetGroup("PARTY", 5, false)
    H.send(M, "KEY", { { 2, 602, 7, { 1, 3, 4 }, 2, 9, 599, 1, 2, 900001, 15, 7, 1 } })
    M.Advance(60)
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    M.Advance(0.3)
    tt:SetBagItem(0, 1)
    local t = text(tt)
    H.contains(t, "Halls of Lightning +7", "their own key's level")
    H.ok(not t:find("Run under way", 1, true), "not their run")
    H.contains(t, "Depleted", "their own key's state")
    -- the run's own key: the bridge sends it to the owner only (BuildKey), who may not lead now
    H.send(M, "KEY", { { 3, 602, 8, { 1, 3, 4 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    tt:SetBagItem(0, 1)
    H.contains(text(tt), "Halls of Lightning +8\nRun under way", "the owner's run without the lead")
    -- a member whose own key is the same: the old K (SendKey) is not lowered, so not the run
    ns.Legacy.Receive("K;4;8;1800;Halls of Lightning")
    tt:SetBagItem(0, 1)
    H.ok(not text(tt):find("Run under way", 1, true), "K at the run's level: a member's own key")
    -- the owner's K is a level under the run (StartRun stored it so)
    ns.Legacy.Receive("K;4;7;1800;Halls of Lightning")
    tt:SetBagItem(0, 1)
    H.contains(text(tt), "Halls of Lightning +8\nRun under way")
end)

test("keystone tooltip: the owner who passes the lead keeps 'Run under way'; the new leader's own key does not get it",
    function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    inBag(M)
    local tt = M.env.GameTooltip
    tt:SetOwner(M.env.UIParent, "ANCHOR_NONE")
    M.SetGroup("PARTY", 5, true)
    H.send(M, "MPS", { { 7001, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    M.Advance(0.3)
    tt:SetBagItem(0, 1)
    H.contains(text(tt), "Halls of Lightning +8\nRun under way")
    M.SetGroup("PARTY", 5, false)
    tt:SetBagItem(0, 1)
    H.contains(text(tt), "Halls of Lightning +8\nRun under way", "still the owner's run")
    -- the new leader: their own +7 from well before the run started
    H.send(M, "MPE", { { 7001, 0, 1900000, -1, 602, 7, 0 } })
    H.send(M, "KEY", { { 2, 602, 7, { 1, 3, 4 }, 2, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    M.Advance(60)
    H.send(M, "MPS", { { 7002, 602, 8, { 1, 3, 4 }, 7, 10000, 1800 } })
    M.Advance(0.3)
    M.SetGroup("PARTY", 5, true)
    tt:SetBagItem(0, 1)
    local t = text(tt)
    H.contains(t, "Halls of Lightning +7", "their own key")
    H.ok(not t:find("Halls of Lightning +8", 1, true), "not the run's level")
    H.ok(not t:find("Run under way", 1, true), "not their run")
end)

test("keystone tooltip: Heroic dungeon mode is orange and says a keystone does not start there", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    inBag(M)
    local tt = M.env.GameTooltip
    tt:SetOwner(M.env.UIParent, "ANCHOR_NONE")
    -- KEY mode 1: the player's dungeon difficulty is Heroic (bh_ui_bridge_map.cpp KeyMode)
    H.send(M, "KEY", { { 2, 602, 8, { 1, 3, 4 }, 1, 9, 599, 1, 2, 900001, 15, 7, 0 } })
    M.Advance(0.3)
    local lines = ns.Tooltip.KeyLines()
    local mode, note
    for i, l in ipairs(lines) do
        if l[1] == "Dungeon mode: Heroic" then
            mode, note = l, lines[i + 1]
        end
    end
    H.ok(mode ~= nil, "the mode line")
    H.eq(mode[2], ns.UI.C.orange, "orange")
    H.eq(note[1], "Keystones run on Normal or Mythic, not Heroic: change it before you enter.", "solo, outside")
    H.eq(note[2], ns.UI.C.orange)
    H.ok(note[3], "wraps")
    tt:SetBagItem(0, 1)
    H.contains(text(tt), "Dungeon mode: Heroic\nKeystones run on Normal or Mythic, not Heroic")
    local function noteNow()
        for i, l in ipairs(ns.Tooltip.KeyLines()) do
            if l[1] == "Dungeon mode: Heroic" then
                return ns.Tooltip.KeyLines()[i + 1][1]
            end
        end
    end
    -- the leader outside: theirs to change
    M.SetGroup("PARTY", 5, true)
    H.eq(noteNow(), "Keystones run on Normal or Mythic, not Heroic: change it before you enter.", "leader")
    -- a member cannot change it (SetDifficulty, KMODE: "Only the group leader can change the dungeon difficulty.")
    M.SetGroup("PARTY", 5, false)
    H.eq(noteNow(), "Keystones run on Normal or Mythic, not Heroic: your group leader sets the dungeon mode.", "member")
    M.SetGroup("RAID", 5, false)
    H.eq(noteNow(), ns.Tooltip.HEROIC_NOTE_MEMBER, "raid member")
    -- the leader inside a dungeon: the change is made outside ("Leave the dungeon first.")
    M.SetGroup("PARTY", 5, true)
    M.inInstance, M.instanceType, M.zone = true, "party", "Halls of Lightning"
    H.eq(noteNow(), "Keystones run on Normal or Mythic, not Heroic: leave the dungeon to change it.", "inside")
    M.inInstance, M.instanceType = false, "none"
    -- Normal and Mythic: one dim line, no rule
    for _, m in ipairs({ { 0, "Normal" }, { 2, "Mythic" } }) do
        H.send(M, "KEY", { { 3 + m[1], 602, 8, { 1, 3, 4 }, m[1], 9, 599, 1, 2, 900001, 15, 7, 0 } })
        M.Advance(0.3)
        lines = ns.Tooltip.KeyLines()
        local t = {}
        for _, l in ipairs(lines) do
            t[#t + 1] = l[1]
            if l[1] == "Dungeon mode: " .. m[2] then
                H.eq(l[2], ns.UI.C.dim, m[2] .. " dim")
            end
        end
        t = table.concat(t, "\n")
        H.contains(t, "Dungeon mode: " .. m[2])
        H.ok(not t:find("not Heroic", 1, true), m[2] .. ": no rule")
    end
end)
