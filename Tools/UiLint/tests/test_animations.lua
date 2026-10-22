-- Animations tab of Collections and the emote wheel.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function openTab(M, ns)
    ns.UI.Open("collections")
    ns.Collections.ShowTab("animations")
    return ns.Animations, ns.Animations.tab
end

-- Puts the cursor `dist` units from the wheel centre in the direction of `slot` (1 = top, clockwise).
local function pointAt(M, A, slot, dist)
    local cx, cy = A.wheel:GetCenter()
    local x, y = A.SlotOffset(slot, dist or 100)
    M.cursorX, M.cursorY = cx + x, cy + y
end

test("animations: catalogue is valid client data", function(M, ns)
    local A = ns.Animations
    local seen, tokens = {}, {}
    for _, e in ipairs(A.List()) do
        H.ok(type(e.key) == "string" and not seen[e.key], "unique key " .. tostring(e.key))
        seen[e.key] = true
        H.ok(type(e.token) == "string" and e.token:match("^%u+$") and not tokens[e.token], "token " .. tostring(e.token))
        tokens[e.token] = true
        H.ok(type(e.anim) == "number" and e.anim >= 0 and e.anim < 506, e.key .. " anim id in the client's SetSequence range")
        H.ok(e.cmd == "/" .. e.token:lower(), e.key .. " command matches its token")
        H.ok(ns.UI.EMOTE_INDEX[e.glyph], e.key .. " glyph exists: " .. tostring(e.glyph))
        H.ok(A.CategoryLabel(e.cat) ~= "Animations", e.key .. " has a known category")
    end
    for p, page in ipairs(ns.Data.defaultWheel) do
        H.ok(#page <= A.WHEEL_SLOTS, "default page " .. p .. " fits")
        for _, key in ipairs(page) do H.ok(A.Get(key), "default wheel key " .. key) end
    end
end)

test("animations: tab lists, searches, filters and pages", function(M, ns)
    local A, tab = openTab(M, ns)
    local total = #A.List()
    H.ok(tab:IsShown(), "tab shown")
    H.contains(tab.count:GetText(), total .. "|r of " .. total)
    H.eq(tab.entries[1].name:GetText(), "Dance")
    H.eq(tab.entries[1].cmd:GetText(), "/dance")
    H.eq(tab.pageText:GetText(), "Page 1 / " .. A.Pages(total))
    H.ok(not tab.prev.enabled and tab.next.enabled, "pager buttons")
    tab.next:Click()
    H.eq(A.page, 2)
    H.eq(tab.entries[1].entry, A.List()[A.PAGE_SIZE + 1])
    ns.Collections.searchBox:SetText("Kn")
    H.eq(A.page, 1, "search clamps the page")
    H.eq(tab.entries[1].name:GetText(), "Kneel")
    H.ok(not tab.entries[2]:IsShown(), "one match")
    ns.Collections.searchBox:SetText("/sh")
    H.eq(#A.Filtered(ns.Collections.search, A.filter), 2, "search by command: /shy, /shout")
    ns.Collections.searchBox:SetText("zzzz")
    H.ok(tab.empty:IsShown() and not tab.entries[1]:IsShown(), "no match message")
    ns.Collections.searchBox:SetText("")
    tab.filter:SetValue("pose")
    H.eq(#A.Filtered("", "pose"), 4)
    H.contains(tab.count:GetText(), "POSES")
    tab.filter:SetValue("wheel")
    H.eq(#A.Filtered("", "wheel"), 28, "every built-in is on the default wheel")
    H.eq(ns.Collections.searchBox.hint:GetText(), "Search dances and emotes")
    ns.Collections.ShowTab("legacy")
    H.ok(not tab:IsShown(), "other tabs hide it")
    H.eq(ns.Collections.searchBox.hint:GetText(), "Search sets, pieces, dungeons")
end)

test("animations: click previews, double-click and Play perform", function(M, ns)
    local A, tab = openTab(M, ns)
    H.eq(A.model.__unit, "player")
    H.eq(A.model.__sequence, 69, "first entry previewed")
    local wave = tab.entries[2]
    wave:Click("LeftButton")
    H.eq(A.selected.key, "wave")
    H.eq(A.model.__sequence, 67)
    A.model.__sequence = nil
    M.Advance(0.5)
    H.eq(A.model.__sequence, 67, "sequence set again once the model loaded")
    H.eq(tab.right.name:GetText(), "Wave")
    H.eq(#M.emotes, 0, "a click does not play")
    M.Fire(wave, "OnDoubleClick", "LeftButton")
    H.eq(M.emotes[1], "WAVE")
    tab.right.play:Click()
    H.eq(M.emotes[2], "WAVE")
    M.env.SlashCmdList.BLEAKHOLD("emote Dance")
    H.eq(M.emotes[3], "DANCE")
    M.env.SlashCmdList.BLEAKHOLD("emote /salute")
    H.eq(M.emotes[4], "SALUTE")
end)

test("animations: wheel editor adds, fills, clears and drags", function(M, ns)
    local A, tab = openTab(M, ns)
    H.ok(A.WheelEntry(1, 1).key == "dance", "default wheel in place after DB_READY")
    local editor = tab.right.editor
    H.eq(editor.pageText:GetText(), "1 / 4")
    -- page 4 has four free slots
    editor.next:Click(); editor.next:Click(); editor.next:Click()
    H.eq(A.wheelPage, 4)
    A.SetWheelSlot(1, 2, nil)
    tab.filter:SetValue("all")
    local wave = tab.entries[2]
    H.ok(not wave.mark:IsShown(), "wave no longer on the wheel")
    wave:Click("RightButton")
    H.eq(A.WheelEntry(4, 5).key, "wave", "right-click fills the first free slot from the shown page")
    H.ok(wave.mark:IsShown(), "on-wheel mark")
    local p, s, already = A.AddToWheel("wave")
    H.ok(p == 4 and s == 5 and already, "no duplicates")
    editor.slots[5]:Click("RightButton")
    H.ok(A.WheelEntry(4, 5) == nil, "right-click empties a slot")
    -- drag onto slot 6
    M.Fire(wave, "OnDragStart", "LeftButton")
    H.ok(M.env.BleakholdAnimationDrag:IsShown(), "drag icon follows the cursor")
    editor.slots[6].__mouseOver = true
    M.Fire(wave, "OnDragStop")
    H.eq(A.WheelEntry(4, 6).key, "wave", "dropped on the slot under the cursor")
    H.ok(not M.env.BleakholdAnimationDrag:IsShown())
    editor.slots[6].__mouseOver = nil
    -- click an empty slot with a selection
    wave:Click("LeftButton")
    editor.slots[7]:Click("LeftButton")
    H.eq(A.WheelEntry(4, 7).key, "wave")
    -- a full wheel refuses
    for page = 1, 4 do for slot = 1, 8 do A.SetWheelSlot(page, slot, "bow") end end
    H.eq(A.AddToWheel("wave"), nil, "full wheel")
    H.ok(not A.SetWheelSlot(5, 1, "bow") and not A.SetWheelSlot(1, 9, "bow") and not A.SetWheelSlot(1, 1, "nope"), "bad slots refused")
end)

test("animations: saved wheel is repaired", function(M, ns)
    local A = ns.Animations
    ns.cdb.wheel = { { "dance", 7, "nope", { } }, "garbage", nil, { [8] = "sleep", [9] = "bow" } }
    A.EnsureWheel()
    H.eq(A.WheelEntry(1, 1).key, "dance")
    H.ok(A.WheelEntry(1, 2) == nil and A.WheelEntry(1, 3) == nil, "bad keys dropped")
    H.ok(A.WheelEntry(2, 1) == nil, "bad page emptied")
    H.eq(A.WheelEntry(4, 8).key, "sleep")
    H.ok(ns.cdb.wheel[4][9] == nil, "slot 9 dropped")
    ns.cdb.wheel = "x"
    A.EnsureWheel()
    H.eq(A.WheelEntry(1, 1).key, "dance", "not a table: default wheel")
end)

test("emote wheel: hold, point and release plays the slot", function(M, ns)
    local A = ns.Animations
    M.env.BleakholdEmoteWheel("down")
    H.ok(A.wheel:IsShown(), "opens on key down")
    H.eq(A.wheel.slots[1].name:GetText(), "Dance")
    pointAt(M, A, 3)
    M.Advance(0.5)
    H.eq(A.wheel.title:GetText(), "Cheer", "hovered slot named in the centre")
    M.env.BleakholdEmoteWheel("up")
    H.eq(M.emotes[1], "CHEER")
    H.ok(not A.wheel:IsShown(), "closes after playing")
    -- releasing inside the dead zone plays nothing
    M.env.BleakholdEmoteWheel("down")
    pointAt(M, A, 1, 10)
    M.Advance(0.5)
    M.env.BleakholdEmoteWheel("up")
    H.eq(#M.emotes, 1)
    H.ok(not A.wheel:IsShown())
end)

test("emote wheel: a tap keeps it open; click, mouse wheel, right-click, key again", function(M, ns)
    local A = ns.Animations
    M.cursorX, M.cursorY = 512, 384
    M.env.BleakholdEmoteWheel("down")
    M.env.BleakholdEmoteWheel("up")
    H.ok(A.wheel:IsShown(), "tap leaves it open")
    M.Fire(A.wheel, "OnMouseWheel", -1)
    H.eq(A.wheelPage, 2)
    H.eq(A.wheel.slots[1].name:GetText(), "Salute")
    pointAt(M, A, 2)
    M.Advance(0.1)
    M.Fire(A.wheel, "OnMouseUp", "LeftButton")
    H.eq(M.emotes[1], "APPLAUD")
    H.ok(not A.wheel:IsShown())
    M.env.SlashCmdList.BLEAKHOLD("wheel")
    H.ok(A.wheel:IsShown(), "/bh wheel opens it")
    M.Fire(A.wheel, "OnMouseUp", "RightButton")
    H.ok(not A.wheel:IsShown(), "right-click closes")
    H.eq(#M.emotes, 1)
    M.cursorX, M.cursorY = 512, 384
    M.env.BleakholdEmoteWheel("down"); M.env.BleakholdEmoteWheel("up")
    M.env.BleakholdEmoteWheel("down")
    H.ok(not A.wheel:IsShown(), "pressing the key again closes")
    M.env.BleakholdEmoteWheel("up")
    H.ok(not A.wheel:IsShown())
    -- empty slots play nothing
    for slot = 1, 8 do A.SetWheelSlot(A.wheelPage, slot, nil) end
    M.env.BleakholdEmoteWheel("down")
    pointAt(M, A, 4)
    M.Advance(0.5)
    M.env.BleakholdEmoteWheel("up")
    H.eq(#M.emotes, 1)
    H.ok(not A.wheel:IsShown(), "released over an empty slot: closes")
end)

test("emote wheel: Ctrl+G is offered once when free", function(M, ns)
    M.Advance(1.5)
    H.eq(M.bindings["CTRL-G"], "BLEAKHOLD_EMOTEWHEEL")
    H.eq(M.savedBindings, 1)
    M.bindings["CTRL-G"] = nil
    M.FireEvent("PLAYER_ENTERING_WORLD")
    M.Advance(1.5)
    H.ok(M.bindings["CTRL-G"] == nil, "a removed binding is not put back")
    local A, tab = openTab(M, ns)
    H.contains(tab.right.hint:GetText(), "Bind a key")
    M.bindings["ALT-E"] = "BLEAKHOLD_EMOTEWHEEL"
    A.Refresh()
    H.contains(tab.right.hint:GetText(), "Hold ALT-E")
end)

test("emote wheel: a taken Ctrl+G is left alone", function(M, ns)
    M.bindings["CTRL-G"] = "TOGGLEGUILDTAB"
    M.Advance(1.5)
    H.eq(M.bindings["CTRL-G"], "TOGGLEGUILDTAB")
    H.eq(M.savedBindings, 0)
end, { before = function(M) M.bindings["CTRL-G"] = "TOGGLEGUILDTAB" end })

test("emote wheel: not bound in combat, offered after", function(M, ns)
    M.combat = true
    M.Advance(1.5)
    H.ok(M.bindings["CTRL-G"] == nil, "not in combat")
    M.combat = false
    M.FireEvent("PLAYER_ENTERING_WORLD")
    M.Advance(1.5)
    H.eq(M.bindings["CTRL-G"], "BLEAKHOLD_EMOTEWHEEL")
end, { before = function(M) M.combat = true end })
