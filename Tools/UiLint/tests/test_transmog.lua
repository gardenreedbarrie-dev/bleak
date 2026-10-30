-- Transmog tab: mod-transmog-plus's addon protocol ("transmog" self-whispers) and the tab built on it: the
-- looks per slot, picking and applying them with their price, the realm's say before Apply away from the NPC,
-- looks not collected yet and Bleakhold Coins (BHMOG), outfits, illusions, and bad input.

local EQUIPPED = { [1] = 100, [3] = 101, [5] = 102, [7] = 103, [16] = 104, [17] = 105 }
local NAMES = {
    [100] = "Helm of Dawn", [101] = "Spaulders", [102] = "Chestplate", [103] = "Leggings", [104] = "Sword",
    [105] = "Shield", [201] = "Ruby Robe", [202] = "Night Vest", [203] = "Sun Tunic", [211] = "Ruby Robe II",
    [300] = "Lost Tunic", [301] = "Forgotten Tunic",
}

local EQUIP_LOC = { [104] = "INVTYPE_WEAPON", [105] = "INVTYPE_SHIELD" }

local function setup(M)
    M.env.GetInventoryItemID = function(unit, slot)
        return unit == "player" and EQUIPPED[slot] or nil
    end
    for id, name in pairs(NAMES) do
        M.items[id] = { name = name }
    end
    local getItemInfo = M.env.GetItemInfo
    M.env.GetItemInfo = function(item)
        local r = { getItemInfo(item) }
        if r[1] and type(item) == "number" and EQUIP_LOC[item] then
            r[9] = EQUIP_LOC[item]
        end
        return unpack(r, 1, 10)
    end
end

local function tm(M, body, sender, channel)
    H.deliver(M, body, "transmog", channel, sender)
end

local function coins(M, body)
    H.deliver(M, body, "BHMOG")
end

-- The transmog requests sent since `from` (an index into M.sent).
local function sent(M, from)
    local out = {}
    for i = (from or 0) + 1, #M.sent do
        local s = M.sent[i]
        if s.prefix == "transmog" then
            H.eq(s.channel, "WHISPER")
            H.eq(s.target, M.playerName)
            out[#out + 1] = s.msg
        end
    end
    return out
end

local function has(list, msg)
    for _, m in ipairs(list) do
        if m == msg then
            return true
        end
    end
    return false
end

-- The chest's looks: two grouped looks (the second continued in a "+" token) and a single one.
local function chestLooks(M)
    tm(M, "AvailableTransmogs:4:5:3:start")
    tm(M, "AvailableTransmogs:4:5:3:201,211,212:202")
    tm(M, "AvailableTransmogs:4:5:3:+213:203")
    tm(M, "AvailableTransmogs:4:5:3:end")
end

local function open(M, ns, fromNpc)
    setup(M)
    if fromNpc then
        tm(M, "Open")
    else
        ns.Transmog.Open()
    end
    return ns.Transmog, ns.Transmog.frame
end

local function dialog(M)
    return M.env.BleakholdDialog
end

test("transmog: the NPC opens the tab, which asks the module for everything", function(M, ns)
    local start = #M.sent
    local TM, f = open(M, ns, true)
    H.ok(ns.Collections.frame:IsShown() and ns.Collections.tab == "transmog", "Collections on the Transmog tab")
    H.ok(f:IsShown(), "the tab is shown")
    local out = sent(M, start)
    for _, want in ipairs({ "GetTransmogStatus", "GetAvailableTransmogs:grouped", "GetOutfits", "GetIllusions" }) do
        H.ok(has(out, want), want .. " requested")
    end
    H.ok(TM.canApply, "at the transmogrifier")
    H.eq(ns.Collections.searchBox.hint:GetText(), "Search looks by item name")
    ns.Collections.ShowTab("legacy")
    H.ok(not f:IsShown(), "other tabs hide it")
    ns.Collections.frame:Hide()
    H.ok(not TM.canApply, "closing the window ends the visit")
end)

test("transmog: grouped looks, status, tiles and the empty texts", function(M, ns)
    local TM, f = open(M, ns, true)
    H.eq(f.empty:GetText(), "Loading looks...", "waiting for the list")
    chestLooks(M)
    local looks = TM.looks[5]
    H.eq(#looks, 3, "three looks")
    H.eq(table.concat(looks[1].sources, ","), "201,211,212")
    H.eq(table.concat(looks[2].sources, ","), "202,213", "a '+' token continues the look before it")
    H.eq(looks[3].lead, 203)
    tm(M, "TransmogStatus:1:4,202")
    H.eq(TM.applied[5], 202)
    H.ok(f.tiles[3]:IsShown() and not f.tiles[4]:IsShown(), "one tile per look")
    H.eq(f.count:GetText(), "3 looks")
    H.eq(f.slotName:GetText(), "Chest")
    local chosen, on = TM.TileState(f.tiles[2].look)
    H.ok(on and not chosen, "the look on now is marked")
    H.eq(f.pageText:GetText(), "Page 1 / 1")
    -- an empty slot and a slot without other looks
    TM.SelectSlot(10)
    H.eq(f.empty:GetText(), "Loading looks...")
    tm(M, "AvailableTransmogs:9:4:0:start")
    tm(M, "AvailableTransmogs:9:4:0:end")
    H.eq(f.empty:GetText(), "Equip an item in this slot to change its look.", "nothing in the hands slot")
    tm(M, "AvailableTransmogs:6:4:0:start")
    tm(M, "AvailableTransmogs:6:4:0:end")
    TM.SelectSlot(7)
    H.contains(f.empty:GetText(), "No other looks for this slot yet")
    -- the search filters by any item of the look
    TM.SelectSlot(5)
    ns.Collections.searchBox:SetText("ruby robe ii")
    H.eq(#TM.Tiles(), 1, "found through the look's second item")
    ns.Collections.searchBox:SetText("zzz")
    H.eq(f.empty:GetText(), "No look matches the search.")
end)

test("transmog: picking a look, its price and Apply at the transmogrifier", function(M, ns)
    local TM, f = open(M, ns, true)
    chestLooks(M)
    tm(M, "TransmogStatus:1:4,202")
    local start = #M.sent
    f.tiles[1]:Click("LeftButton")
    H.eq(TM.pending[5], 201, "picked")
    H.ok(f.slots[5].dot:IsShown(), "the slot shows a change")
    M.Advance(0.4)
    H.ok(has(sent(M, start), "CalculateCost:4:201"), "the price is asked for")
    H.eq(f.cost:GetText(), "|cff808080Cost: ...|r", "in the stock grey while the price is asked for")
    tm(M, "TransmogCost:12345:1")
    H.eq(f.cost:GetText(), "Cost: 1|cffffd700g|r 23|cffc7c7cfs|r 45|cffeda55fc|r")
    H.ok(f.apply.enabled, "Apply is live")
    start = #M.sent
    f.apply:Click()
    H.ok(dialog(M):IsShown(), "a price is confirmed first")
    H.contains(dialog(M).text:GetText(), "Change 1 slot for")
    dialog(M).ok:Click()
    H.ok(has(sent(M, start), "Apply:4:201"), "Apply sent")
    H.eq(f.cost:GetText(), "Applying...")
    tm(M, "ApplyTransmogResult:1:4,201")
    H.eq(TM.applied[5], 201)
    H.ok(next(TM.pending) == nil, "nothing pending")
    H.eq(f.status:GetText(), "Your new look is on.")
    H.ok(has(sent(M, start), "GetTransmogStatus"), "and the status asked again")
    -- clicking the chosen look again drops the choice
    f.tiles[3]:Click("LeftButton")
    f.tiles[3]:Click("LeftButton")
    H.eq(TM.pending[5], nil)
end)

test("transmog: failures, not enough gold and the answer that never comes", function(M, ns)
    local TM, f = open(M, ns, true)
    chestLooks(M)
    f.tiles[1]:Click("LeftButton")
    M.Advance(0.4)
    tm(M, "TransmogCost:99999999:0")
    H.contains(f.cost:GetText(), "(not enough)")
    H.ok(not f.apply.enabled, "Apply is off without the gold")
    tm(M, "TransmogCost:0:1")
    f.apply:Click()
    tm(M, "ApplyTransmogResult:0")
    H.contains(f.status:GetText(), "1 of 1 changes could not be made")
    f.tiles[1]:Click("LeftButton")
    M.Advance(0.4)
    tm(M, "TransmogCost:0:1")
    f.apply:Click()
    M.Advance(11)
    H.eq(f.status:GetText(), "The realm did not answer every change.")
    H.ok(not TM.applying, "Apply is free again")
end)

test("transmog: away from the NPC, Apply asks the realm first", function(M, ns)
    local TM, f = open(M, ns, false)
    H.ok(not TM.canApply)
    chestLooks(M)
    f.tiles[3]:Click("LeftButton")
    M.Advance(0.4)
    tm(M, "TransmogCost:0:1")
    local start = #M.sent
    f.apply:Click()
    local out = sent(M, start)
    H.ok(has(out, "RequestPortable") and not has(out, "Apply:4:203"), "asks first")
    tm(M, "Portable")
    H.ok(has(sent(M, start), "Apply:4:203"), "the realm agreed: free changes go at once")
    tm(M, "ApplyTransmogResult:1:4,203")
    -- closing drops the changes; a realm that keeps transmog at the NPC says nothing
    f.tiles[1]:Click("LeftButton")
    ns.Collections.frame:Hide()
    H.eq(TM.pending[5], nil, "closing drops what was not applied")
    ns.Transmog.Open()
    f.tiles[1]:Click("LeftButton")
    M.Advance(0.4)
    tm(M, "TransmogCost:0:1")
    start = #M.sent
    f.apply:Click()
    M.Advance(4.5)
    H.ok(not has(sent(M, start), "Apply:4:201"))
    H.eq(f.status:GetText(), "Visit a transmogrifier to change your look.")
end)

test("transmog: back to the real item, hiding, undo and taking everything off", function(M, ns)
    local TM, f = open(M, ns, true)
    chestLooks(M)
    tm(M, "TransmogStatus:2:4,202:0,203")
    tm(M, "IllusionStatus:3789:0")
    f.slots[5]:Click("RightButton")
    H.eq(TM.pending[5], 0, "right-click: back to the real item")
    f.slots[5]:Click("RightButton")
    H.eq(TM.pending[5], nil, "again: undo")
    f.hide:Click()
    H.eq(TM.pending[5], TM.HIDDEN, "hidden")
    H.ok(f.slots[5].hidden:IsShown(), "the slot shows it")
    TM.SelectSlot(16)
    H.ok(not f.hide.enabled, "weapons cannot be hidden")
    f.undo:Click()
    H.ok(next(TM.pending) == nil, "undo drops every change")
    f.slots[5]:Click("RightButton")
    M.Advance(0.4)
    local start = #M.sent
    f.apply:Click()
    H.ok(has(sent(M, start), "Remove:4"), "Remove for the real item")
    tm(M, "ApplyTransmogResult:1:4,0")
    H.eq(TM.applied[5], nil)
    start = #M.sent
    f.strip:Click()
    dialog(M).ok:Click()
    local out = sent(M, start)
    H.ok(has(out, "RemoveAll") and has(out, "ApplyIllusion:15:0"), "every transmog and illusion off")
end)

test("transmog: looks not collected, the search, old answers and Bleakhold Coins", function(M, ns)
    local TM, f = open(M, ns, true)
    chestLooks(M)
    H.ok(not f.coins:IsShown(), "no coins without mod-bleakhold")
    coins(M, "B;10;1;3;5")
    H.ok(f.coins:IsShown())
    H.eq(f.coins.text:GetText(), "10 coins")
    local start = #M.sent
    f.missing:Click()
    local s1 = TM.missingSeq
    H.ok(has(sent(M, start), "GetMissing:" .. s1 .. ":4"), "asks for the missing looks")
    H.eq(f.count:GetText(), "Loading...")
    tm(M, "MissingLooks:" .. s1 .. ":3:start")
    tm(M, "MissingLooks:" .. s1 .. ":3:300:301:951500")
    tm(M, "MissingLooks:" .. s1 .. ":3:end")
    H.eq(f.count:GetText(), "3 not collected")
    H.ok(f.tiles[1].look.missing and f.tiles[1].lock:IsShown(), "locked tiles")
    H.eq(f.tiles[1].price:GetText(), "3 coins", "an epic look costs the epic price")
    H.eq(f.tiles[3].price:GetText(), "Mythic+", "Mythic+ looks cannot be bought")
    -- typing a search asks again once typing pauses; an older answer is dropped
    start = #M.sent
    ns.Collections.searchBox:SetText("lost")
    M.Advance(0.5)
    local s2 = TM.missingSeq
    H.ok(s2 == s1 + 1 and has(sent(M, start), "GetMissing:" .. s2 .. ":4:lost"), "the search goes to the module")
    tm(M, "MissingLooks:" .. s1 .. ":1:start")
    tm(M, "MissingLooks:" .. s1 .. ":1:999")
    tm(M, "MissingLooks:" .. s1 .. ":1:end")
    H.eq(#TM.missing.list, 0, "the old answer is dropped")
    tm(M, "MissingLooks:" .. s2 .. ":1:start")
    tm(M, "MissingLooks:" .. s2 .. ":1:300")
    tm(M, "MissingLooks:" .. s2 .. ":1:end")
    H.eq(TM.missing.list[1].lead, 300)
    -- try it on, then unlock it
    f.tiles[1]:Click("LeftButton")
    H.eq(TM.trying[5], 300, "tried on the model only")
    H.eq(#TM.Changes(), 0, "not something Apply sends")
    H.ok(f.unlock:IsShown() and f.unlock.enabled)
    H.eq(f.unlock.label:GetText(), "Unlock for 3 Bleakhold Coins")
    f.unlock:Click()
    dialog(M).ok:Click()
    H.eq(M.said[#M.said].msg, ".mog unlock 300")
    start = #M.sent
    coins(M, "U;300")
    coins(M, "B;7;1;3;5")
    H.eq(TM.pending[5], 300, "the unlocked look is picked")
    H.ok(has(sent(M, start), "GetAvailableTransmogs:grouped"), "and the collection asked again")
    H.ok(not f.unlock:IsShown())
    -- too few coins
    coins(M, "B;2;1;3;5")
    tm(M, "MissingLooks:" .. s2 .. ":1:start")
    tm(M, "MissingLooks:" .. s2 .. ":1:301")
    tm(M, "MissingLooks:" .. s2 .. ":1:end")
    f.tiles[1]:Click("LeftButton")
    H.ok(f.unlock:IsShown() and not f.unlock.enabled, "not enough coins")
end)

test("transmog: outfits load, save and delete", function(M, ns)
    local TM, f = open(M, ns, true)
    chestLooks(M)
    tm(M, "TransmogStatus:1:6,103")
    tm(M, "Outfits:start")
    tm(M, "Outfit:1,100;5,201:Raid Night")
    tm(M, "Outfit::Empty")
    tm(M, "Outfit:5,202:Bad|Name")
    tm(M, "Outfits:end")
    H.eq(#TM.outfits, 3)
    H.eq(TM.outfits[1].name, "BadName", "sorted, '|' dropped")
    f.outfit:SetValue("Raid Night")
    H.eq(TM.pending[1], 100)
    H.eq(TM.pending[5], 201)
    H.eq(TM.pending[7], 0, "a slot the outfit leaves out goes back to the real item")
    H.ok(f.delete.enabled, "the picked outfit can be deleted")
    local start = #M.sent
    f.save:Click()
    H.ok(dialog(M).edit:IsShown())
    H.eq(dialog(M).edit:GetText(), "Raid Night", "the picked outfit's name")
    dialog(M).edit:SetText("  Gala|Night ")
    dialog(M).ok:Click()
    M.Advance(0.6)
    local out = sent(M, start)
    H.ok(has(out, "SaveOutfit:1,100;5,201:GalaNight"), "saved: " .. table.concat(out, " "))
    H.ok(has(out, "GetOutfits"), "the list asked again")
    tm(M, "Outfits:start")
    tm(M, "Outfit:1,100;5,201:GalaNight")
    tm(M, "Outfits:end")
    start = #M.sent
    f.delete:Click()
    dialog(M).ok:Click()
    H.ok(has(sent(M, start), "DeleteOutfit:GalaNight"))
    tm(M, "OutfitRejected:Too Many")
    local said = false
    for _, c in ipairs(M.chat) do
        said = said or tostring(c.msg):find("delete one before saving", 1, true) ~= nil
    end
    H.ok(said, "a full outfit list is explained")
    -- nothing to save
    TM.pending = {}
    tm(M, "TransmogStatus:0")
    f.save:Click()
    H.eq(f.status:GetText(), "Pick some looks before saving an outfit.")
end)

test("transmog: illusions", function(M, ns)
    local TM, f = open(M, ns, true)
    H.ok(not f.illusionsTab:IsShown(), "no Illusions tab until the module lists them")
    H.ok(not f.itemsTab:IsShown(), "nor the Items tab: a one-button choice is no choice")
    tm(M, "Illusions:start")
    tm(M, "IllusionName:3789:Berserking")
    tm(M, "IllusionName:3368:Rune of the Fallen Crusader")
    tm(M, "Illusions:3789:3368")
    tm(M, "Illusions:end")
    tm(M, "IllusionStatus:3789:0")
    H.ok(f.illusionsTab:IsShown() and f.itemsTab:IsShown(), "both tabs once there are illusions")
    f.illusionsTab:Click()
    H.ok(f.ill:IsShown() and not f.items:IsShown())
    local rows = f.illRows.items
    H.eq(rows[3].label:GetText(), "Berserking")
    H.eq(rows[3].style, "rowOn", "the main hand's illusion is marked (checked, as a dropdown list's row)")
    rows[4]:Click()
    H.eq(TM.illusionPending[16], 3368)
    local start = #M.sent
    M.Advance(0.4)
    H.ok(has(sent(M, start), "CalculateCost:i15:3368"))
    tm(M, "TransmogCost:5000:1")
    f.apply:Click()
    dialog(M).ok:Click()
    H.ok(has(sent(M, start), "ApplyIllusion:15:3368"))
    tm(M, "ApplyIllusionResult:1:15:3368")
    tm(M, "IllusionStatus:3368:0")
    H.eq(TM.illusionApplied[16], 3368)
    H.eq(f.status:GetText(), "Your new look is on.")
    f.offHand:Click()
    rows[2]:Click()
    H.eq(TM.illusionPending[17], nil, "a shield takes no illusion")
    H.contains(f.illEmpty:GetText(), "shields")
    EQUIP_LOC[105] = "INVTYPE_WEAPONOFFHAND"
    TM.Refresh()
    rows[2]:Click()
    H.eq(TM.illusionPending[17], TM.HIDDEN, "an off-hand weapon's glow hidden")
    EQUIP_LOC[105] = "INVTYPE_SHIELD"
end)

test("transmog: a realm without the module echoes the requests back", function(M, ns)
    local TM, f = open(M, ns, false)
    -- the server hands an unconsumed self-whisper back to the player
    tm(M, "GetTransmogStatus")
    tm(M, "GetAvailableTransmogs:grouped")
    H.ok(TM.echoed and not TM.heard, "our own requests are not answers")
    H.eq(f.empty:GetText(), "This realm has no transmog module.", "said at once")
end)

test("transmog: reopening the window asks again for what changed meanwhile", function(M, ns)
    local TM, f = open(M, ns, true)
    chestLooks(M)
    ns.Collections.frame:Hide()
    H.ok(not f:IsShown(), "the tab closes with the window")
    M.FireEvent("PLAYER_EQUIPMENT_CHANGED", 5, 1)
    local start = #M.sent
    tm(M, "Open")
    local out = sent(M, start)
    H.ok(has(out, "GetAvailableTransmogs:grouped") and has(out, "GetTransmogStatus"), "looks and status asked again")
    -- the NPC's Open while the window is open asks for the status (its gossip menu may have changed it)
    start = #M.sent
    tm(M, "Open")
    H.ok(has(sent(M, start), "GetTransmogStatus"))
end)

test("transmog: Apply waits for the price of the latest pick, and a late Accept sends nothing new", function(M, ns)
    local TM, f = open(M, ns, true)
    chestLooks(M)
    f.tiles[1]:Click("LeftButton")
    H.ok(not f.apply.enabled, "not priced yet: no Apply")
    local start = #M.sent
    TM.Apply()
    H.ok(not has(sent(M, start), "Apply:4:201"), "nothing sent before the price")
    M.Advance(0.4)
    H.ok(not f.apply.enabled, "the price is on its way")
    tm(M, "TransmogCost:50000:1")
    H.ok(f.apply.enabled)
    f.apply:Click()
    H.ok(dialog(M):IsShown(), "5 gold is confirmed")
    f.tiles[3]:Click("LeftButton")   -- another look while the question is open
    M.Advance(0.4)
    tm(M, "TransmogCost:50000:1")
    start = #M.sent
    dialog(M).ok:Click()
    H.ok(not has(sent(M, start), "Apply:4:203") and not has(sent(M, start), "Apply:4:201"), "not what was confirmed")
    H.ok(not TM.applying)
    f.apply:Click()
    ns.Collections.frame:Hide()
    start = #M.sent
    dialog(M).ok:Click()
    H.eq(#sent(M, start), 0, "the window is closed: Accept does nothing")
end)

test("transmog: trying a look not collected drops the slot's earlier pick", function(M, ns)
    local TM, f = open(M, ns, true)
    chestLooks(M)
    f.tiles[1]:Click("LeftButton")
    H.eq(TM.pending[5], 201)
    f.missing:Click()
    tm(M, "MissingLooks:" .. TM.missingSeq .. ":1:start")
    tm(M, "MissingLooks:" .. TM.missingSeq .. ":1:300")
    tm(M, "MissingLooks:" .. TM.missingSeq .. ":1:end")
    f.tiles[1]:Click("LeftButton")
    H.eq(TM.trying[5], 300)
    H.eq(TM.pending[5], nil, "Apply cannot send what the model no longer shows")
end)

test("transmog: the coin balance is asked for once, outfits skip empty slots, names stay whole", function(M, ns)
    local TM, f = open(M, ns, true)
    local asked = 0
    for _, s in ipairs(M.sent) do
        asked = asked + ((s.prefix == "BHMOG" and s.msg == "B?") and 1 or 0)
    end
    H.eq(asked, 1, "the balance is asked for when it is not known")
    coins(M, "B?")
    H.eq(TM.coins, nil, "an echo of the question is no balance")
    tm(M, "Outfits:start")
    tm(M, "Outfit:10,500;5,201:Gloves")
    tm(M, "Outfit:1,100:" .. "a" .. string.rep("\195\164", 30))
    tm(M, "Outfits:end")
    f.outfit:SetValue("Gloves")
    H.eq(TM.pending[10], nil, "nothing equipped on the hands: no look there")
    H.eq(TM.pending[5], 201)
    local long = TM.outfits[1].name
    H.ok(#long <= 48 and not long:find("\195$"), "cut between characters")
end)


test("transmog: bad, foreign and unknown messages never break it", function(M, ns)
    local TM, f = open(M, ns, true)
    chestLooks(M)
    tm(M, "TransmogStatus:1:4,202")
    for _, body in ipairs({
        "", ":", ":::", "AvailableTransmogs", "AvailableTransmogs:99:1:1:start", "AvailableTransmogs:x:y:z:start",
        "AvailableTransmogs:4:5:1:1,2", "AvailableTransmogs:4:5:1:abc,,-3:+", "TransmogStatus:2:abc,def:4,",
        "TransmogStatus:1:99,5", "Sources:", "Sources:x:start", "Sources:201:end", "MissingLooks:9:9:1:2",
        "Outfit:no", "Outfits:end", "IllusionName:", "IllusionStatus:x:y", "Illusions:5", "TransmogCost:",
        "ApplyTransmogResult:1:x,y", "ApplyIllusionResult:1:99:5", "Nonsense:1:2", "CollectionUpdated:abc",
        string.rep("9", 300), "AvailableTransmogs:4:5:1:" .. string.rep("1,", 120),
    }) do
        tm(M, body)
    end
    H.eq(#TM.looks[5], 3, "the list survives")
    tm(M, "TransmogStatus:0", "Stranger")
    tm(M, "TransmogStatus:0", nil, "PARTY")
    H.eq(TM.applied[5], nil, "TransmogStatus:1:99,5 is ignored, the bad slot dropped")
    tm(M, "TransmogStatus:1:4,202")
    tm(M, "TransmogStatus:0", "Stranger")
    H.eq(TM.applied[5], 202, "nobody else's whispers count")
    coins(M, "B;x")
    coins(M, "U;")
    H.eq(TM.coins, 0)
end)

test("transmog: no module on the realm, and the camera command", function(M, ns)
    local TM, f = open(M, ns, false)
    M.Advance(TM.WAIT + 0.5)
    H.eq(f.empty:GetText(), "This realm has no transmog module.")
    M.env.SlashCmdList.BLEAKHOLD("mog camera 1 -0.5 2")
    local nudge = ns.db.mogCamera["human:chest"]
    H.ok(nudge and nudge[1] == 1 and nudge[2] == -0.5 and nudge[3] == 2, "saved for the race and region")
    local d, s, h = TM.Framing("chest")
    H.eq(d, TM.FRAMING.chest[1] + 1)
    M.env.SlashCmdList.BLEAKHOLD("mog camera reset")
    H.eq(ns.db.mogCamera["human:chest"], nil)
    M.env.SlashCmdList.BLEAKHOLD("mog camera what")
    M.env.SlashCmdList.BLEAKHOLD("mog")
    H.ok(f:IsShown())
end)

test("transmog: /transmog asks the realm, Portable opens the tab", function(M, ns)
    setup(M)
    local start = #M.sent
    M.env.SlashCmdList.BLEAKHOLDTRANSMOG()
    H.ok(has(sent(M, start), "RequestPortable"))
    H.ok(ns.Transmog.frame:IsShown(), "browsing opens at once")
    tm(M, "Portable")
    H.ok(ns.Transmog.canApply, "the realm allows changes anywhere")
end)

test("transmog: with the module's own Transmog addon installed, that addon answers the NPC", function(M, ns)
    setup(M)
    tm(M, "Open")
    tm(M, "Portable")
    H.ok(not ns.Collections.frame:IsShown(), "the other addon's window opens instead")
    H.eq(M.env.SLASH_BLEAKHOLDTRANSMOG1, nil, "/transmog is left to it")
    ns.Transmog.Open()
    H.ok(ns.Transmog.frame:IsShown(), "the tab still works")
end, { before = function(M) M.addons.Transmog = true end })
