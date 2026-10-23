-- Emoji bubbles in the Animations tab and on the emote wheel: the catalogue (EmojiData.lua), the icons,
-- sending EMOJI with its cooldown, the notices, /bh emoji, /bh emojis, the preview and wheel seeding.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local JOY = "Interface\\Bleakhold\\Emoji\\Emoji000"
local EMOJI_BIT = { [6] = 64 }    -- HELLO feature bits: emoji bubbles live

local function texturePath(id)
    return string.format("Interface\\Bleakhold\\Emoji\\Emoji%03d", id)
end

local function openTab(M, ns, filter)
    ns.UI.Open("collections")
    ns.Collections.ShowTab("animations")
    local A = ns.Animations
    if filter then
        A.tab.filter:SetValue(filter)
    end
    return A, A.tab
end

-- The id field of every EMOJI sent to the server, joined with ",".
local function sentEmojis(M)
    local out = {}
    for _, it in ipairs(H.intents(M)) do
        if it.op == "EMOJI" then
            out[#out + 1] = it.fields[1]
        end
    end
    return table.concat(out, ",")
end

-- How many messages containing `text` were added (to `frame`, or to any frame).
local function printed(M, text, frame)
    local n = 0
    for _, c in ipairs(M.chat) do
        if (not frame or c.frame == frame) and tostring(c.msg):find(text, 1, true) then
            n = n + 1
        end
    end
    return n
end

local function near(a, b, msg)
    H.ok(type(a) == "number" and math.abs(a - b) < 1e-6,
        (msg or "value") .. ": expected " .. tostring(b) .. ", got " .. tostring(a))
end

local function pointAt(M, A, slot, dist)
    local cx, cy = A.wheel:GetCenter()
    local x, y = A.SlotOffset(slot, dist or 100)
    M.cursorX, M.cursorY = cx + x, cy + y
end

local function wheelPage(A, page)
    local keys = {}
    for s = 1, A.WHEEL_SLOTS do
        local e = A.WheelEntry(page, s)
        keys[s] = e and e.key or "-"
    end
    return table.concat(keys, ",")
end

test("emojis: catalogue, groups, default wheel and the Emojis filter", function(M, ns)
    local A, Data = ns.Animations, ns.Data
    local groups, keys = {}, {}
    for _, g in ipairs(Data.emojiGroups) do
        groups[g.key] = true
    end
    H.ok(#Data.emojis >= 1 and #Data.emojis <= 256, "1..256 emojis")
    for i, m in ipairs(Data.emojis) do
        H.eq(m.id, i - 1, "ids are 0..n-1")
        H.ok(not keys[m.key], "unique key " .. m.key)
        keys[m.key] = true
        H.ok(groups[m.group], m.key .. " is in a known group: " .. tostring(m.group))
        local e = A.Get("emoji:" .. m.key)
        H.ok(e and e.emoji == m.id and e.name == m.name and e.texture == texturePath(m.id), m.key .. " entry")
    end
    H.eq(table.concat(Data.defaultWheel[4], ",", 5, 8), "emoji:joy,emoji:fire,emoji:skull,emoji:heart")
    for s = 5, 8 do
        H.ok(A.Get(Data.defaultWheel[4][s]), "default page 4 key " .. Data.defaultWheel[4][s])
    end
    local inFilter
    for _, it in ipairs(A.tab.filter.items) do
        if it.value == "emoji" and it.text == "Emojis" then
            inFilter = true
        end
    end
    H.ok(inFilter, "Emojis category in the filter")
    H.eq(#A.Filtered("", "emoji"), #Data.emojis)
    H.eq(#A.List(), #Data.dances + #Data.emotes + #Data.emojis, "the tab lists dances, emotes and emojis")
    for _, name in ipairs({ "Heart Eyes", "heart_eyes", ":heart_eyes:", "  HEART   EYES ", "Heart_Eyes" }) do
        local e = A.EmojiByName(name)
        H.ok(e and e.emoji == 3, "EmojiByName(" .. name .. ")")
    end
    H.ok(A.EmojiByName("dance") == nil and A.EmojiByName("") == nil, "only emojis")
end)

test("emojis: grid, wheel editor, wheel and drag icon show the emoji art", function(M, ns)
    local A, tab = openTab(M, ns, "emoji")
    local b = tab.entries[1]
    H.eq(b.entry.key, "emoji:joy")
    H.eq(b.icon.__texture, JOY)
    H.eq(table.concat(b.icon.__tc, ","), "0,1,0,1", "the whole texture")
    H.eq(table.concat({ b.icon:GetVertexColor() }, ","), "1,1,1,1", "not tinted")
    H.eq(tab.entries[2].icon.__texture, texturePath(1))
    A.SetWheelPage(4)
    local want = { [5] = 0, [6] = 50, [7] = 10, [8] = 52 }
    for s, id in pairs(want) do
        H.eq(tab.right.editor.slots[s].icon.__texture, texturePath(id), "editor page 4 slot " .. s)
    end
    H.eq(tab.right.editor.slots[1].icon.__texture, ns.UI.ART .. "Emotes", "emotes keep their glyph")
    A.wheelPage = 4
    A.OpenWheel(false)
    H.eq(A.wheel.slots[5].icon.__texture, JOY, "wheel slot")
    A.CloseWheel()
    M.Fire(b, "OnDragStart", "LeftButton")
    H.eq(M.env.BleakholdAnimationDrag.icon.__texture, JOY, "drag icon")
    M.Fire(b, "OnDragStop")
end)

test("emojis: missing art falls back to the glyph and hides the preview", function(M, ns)
    M.missingTextures[JOY] = true
    local A, tab = openTab(M, ns, "emoji")
    ns.Collections.searchBox:SetText("rolling")
    H.eq(tab.entries[1].icon.__texture, texturePath(1), "rofl has its art")
    ns.Collections.searchBox:SetText("tears")
    local icon = tab.entries[1].icon
    H.eq(tab.entries[1].entry.key, "emoji:joy")
    H.eq(icon.__texture, ns.UI.ART .. "Emotes", "the Emotes atlas, not the emoji path (nor the previous emoji)")
    H.ok(icon.__tc[2] - icon.__tc[1] < 0.2, "one glyph of the atlas")
    tab.entries[1]:Click("LeftButton")
    H.ok(not A.emojiPreview:IsShown(), "no preview without art")
    ns.Collections.searchBox:SetText("")
    tab.entries[2]:Click("LeftButton")
    H.ok(A.emojiPreview:IsShown(), "rofl previews")
    tab.entries[1]:Click("LeftButton")
    H.ok(not A.emojiPreview:IsShown() and A.emojiPreview.tex.__texture == nil, "no stale emoji in the preview")
end)

test("emojis: double-click sends EMOJI, Play waits for the cooldown", function(M, ns)
    M.cvars.emojiBubbles = "1"
    FX.connect(M, H, EMOJI_BIT)
    local A, tab = openTab(M, ns, "emoji")
    M.Fire(tab.entries[1], "OnDoubleClick", "LeftButton")
    H.eq(sentEmojis(M), "0")
    H.eq(A.selected.key, "emoji:joy")
    H.eq(#M.emotes, 0, "no DoEmote")
    tab.right.play:Click()
    H.eq(sentEmojis(M), "0", "nothing sent during the cooldown")
    H.eq(printed(M, "Wait a moment before the next emoji.", M.env.UIErrorsFrame), 1)
    M.Advance(3.3)
    tab.right.play:Click()
    H.eq(sentEmojis(M), "0,0")
    H.eq(printed(M, "cannot draw emoji bubbles"), 0, "Bleakhold.exe: no note")
    H.eq(printed(M, "Wait a moment"), 1)
end)

test("emojis: page 4 slot 5 of the wheel, released, sends EMOJI 0", function(M, ns)
    M.cvars.emojiBubbles = "1"
    FX.connect(M, H, EMOJI_BIT)
    local A = ns.Animations
    M.env.BleakholdEmoteWheel("down")
    for _ = 1, 3 do
        M.Fire(A.wheel, "OnMouseWheel", -1)
    end
    H.eq(A.wheelPage, 4)
    pointAt(M, A, 5)
    M.Advance(0.5)
    H.eq(A.wheel.title:GetText(), "Tears of Joy")
    M.env.BleakholdEmoteWheel("up")
    H.eq(sentEmojis(M), "0")
    H.ok(not A.wheel:IsShown(), "closes after sending")
    H.eq(#M.emotes, 0)
end)

test("emojis: no realm answer or the feature off: a notice, a hint and no EMOJI", function(M, ns)
    local A = ns.Animations
    local joy = A.EmojiByName("joy")
    local ok, reason = A.SendEmoji(joy)
    H.ok(ok == false and reason == "offline", "refused: " .. tostring(reason))
    local offline = "Emojis need the Bleakhold server module, and this realm has not answered (/bh status)."
    H.eq(printed(M, offline), 1)
    A.SendEmoji(joy)
    H.eq(printed(M, offline), 1, "at most once per 10 s")
    M.Advance(10.5)
    A.SendEmoji(joy)
    H.eq(printed(M, offline), 2)
    local _, tab = openTab(M, ns, "emoji")
    tab.entries[1]:Click("LeftButton")
    H.eq(tab.right.hint:GetText(), offline, "the hint says why")
    FX.connect(M, H, { [6] = 32 })
    H.eq(tab.right.hint:GetText(), "Emojis are turned off on this realm.", "HELLO refreshes the hint")
    H.eq(A.SendEmoji(joy), false)
    H.eq(printed(M, "Emojis are turned off on this realm."), 1)
    H.eq(sentEmojis(M), "")
    tab.filter:SetValue("all")
    FX.showEntry(ns, "dance"):Click("LeftButton")
    H.ok(tab.right.hint:GetText():find("wheel"), "emotes keep the key hint")
end)

test("emojis: an outdated UI says so", function(M, ns)
    H.hello(M, { [1] = 3, [2] = 2, [6] = 64 })
    local A = ns.Animations
    H.ok(ns.Comm.outdated)
    H.eq(A.SendEmoji(A.EmojiByName("joy")), false)
    H.eq(printed(M, "Emojis: your Bleakhold UI is out of date for this realm."), 1)
    H.eq(sentEmojis(M), "")
end)

test("emojis: a refused Comm.Send is reported and starts no cooldown", function(M, ns)
    FX.connect(M, H, EMOJI_BIT)
    local A = ns.Animations
    ns.Comm.blocked = true
    local ok, err = A.SendEmoji(A.EmojiByName("joy"))
    H.ok(ok == false and err == "blocked", "refused: " .. tostring(err))
    H.eq(printed(M, "Emojis: could not send (blocked)."), 1)
    H.eq(A.emojiReadyAt, 0)
    ns.Comm.blocked = false
    H.eq(A.SendEmoji(A.EmojiByName("joy")), true)
    H.eq(sentEmojis(M), "0")
end)

test("emojis: demo mode says once that nobody sees it", function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    local A, tab = openTab(M, ns, "emoji")
    tab.entries[1]:Click("LeftButton")
    local demoNote = "Demo mode: no realm is connected, so nobody sees this emoji."
    tab.right.play:Click()
    H.eq(printed(M, demoNote), 1)
    M.Advance(3.3)
    tab.right.play:Click()
    M.Advance(1)
    H.eq(printed(M, demoNote), 1, "once per session")
    local routed = 0
    for _, e in ipairs(ns.Comm.log) do
        if e.dir == ">" and e.body:find(" EMOJI ", 1, true) then
            routed = routed + 1
        end
    end
    H.eq(routed, 2, "both went to the demo responder")
    H.eq(H.countIntents(M, "EMOJI"), 0, "nothing reached the server")
    H.eq(printed(M, "cannot draw emoji bubbles"), 0, "only the demo note")
    H.eq(ns.Comm.stats.unknown, 0)
end)

test("emojis: a stock client is told once that it cannot draw the bubbles", function(M, ns)
    FX.connect(M, H, EMOJI_BIT)
    local A = ns.Animations
    local note = "Your game cannot draw emoji bubbles (start it with Bleakhold.exe); others still see yours."
    H.eq(A.SendEmoji(A.EmojiByName("joy")), true)
    M.Advance(3.3)
    H.eq(A.SendEmoji(A.EmojiByName("joy")), true)
    H.eq(printed(M, note), 1)
    H.eq(sentEmojis(M), "0,0", "sent all the same")
end)

test("emojis: ERR busy from the server waits the whole cooldown again", function(M, ns)
    M.cvars.emojiBubbles = "1"
    FX.connect(M, H, EMOJI_BIT)
    local A = ns.Animations
    local fire = A.EmojiByName("fire")
    H.eq(A.SendEmoji(fire), true)
    M.Advance(3.3)
    H.send(M, "ERR", { { "EMOJI", "", "busy", "You are doing that too often." } })
    near(A.emojiReadyAt, M.now + A.EMOJI_COOLDOWN, "ready a cooldown from now")
    H.eq(select(2, A.SendEmoji(fire)), "cooldown")
    M.Advance(3.3)
    H.send(M, "ERR", { { "EMOJI", "", "muted", "You cannot use emojis while muted." } })
    H.send(M, "ERR", { { "TCLAIM", "", "busy", "You are doing that too often." } })
    H.eq(A.SendEmoji(fire), true, "other errors leave the cooldown alone")
    H.eq(sentEmojis(M), "50,50")
end)

test("emojis: /bh emoji by key, name or :key:, the list and the usage", function(M, ns)
    M.cvars.emojiBubbles = "1"
    FX.connect(M, H, EMOJI_BIT)
    local bh = M.env.SlashCmdList.BLEAKHOLD
    bh("emoji fire")
    M.Advance(3.3)
    bh("emoji Heart Eyes")
    M.Advance(3.3)
    bh("emoji :skull:")
    H.eq(sentEmojis(M), "50,3,10")
    M.Advance(3.3)
    bh("emoji nope")
    bh("emoji")
    H.eq(printed(M, "usage: /bh emoji <name>, for example /bh emoji joy (/bh emoji list shows them all)"), 2)
    local before = #M.chat
    bh("emoji LIST")
    H.ok(#M.chat - before >= 2, "list printed")
    local lines = {}
    for i = before + 1, #M.chat do
        local line = M.chat[i].msg:gsub("^|cff%x+Bleakhold|r: ", "")
        H.ok(#line <= 240, "a line of at most 240 characters: " .. #line)
        lines[#lines + 1] = line
    end
    local all = " " .. table.concat(lines, " ") .. " "
    for _, m in ipairs(ns.Data.emojis) do
        H.contains(all, " " .. m.key .. " ", "listed")
    end
    H.eq(sentEmojis(M), "50,3,10", "neither the usage nor the list sends")
end)

test("emojis: /bh emote plays emotes only", function(M, ns)
    FX.connect(M, H, EMOJI_BIT)
    local bh = M.env.SlashCmdList.BLEAKHOLD
    bh("emote cool")
    bh("emote Tears of Joy")
    H.eq(printed(M, "usage: /bh emote <name>"), 2)
    bh("emote kiss")
    H.eq(table.concat(M.emotes, ","), "KISS", "the emote, not the emoji of the same key")
    H.eq(H.countIntents(M, "EMOJI"), 0)
end)

test("emojis: /bh emojis without Bleakhold.exe explains and never calls SetCVar", function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("emojis off")
    M.env.SlashCmdList.BLEAKHOLD("emojis")
    H.eq(printed(M, "Your game cannot draw emoji bubbles: start it with Bleakhold.exe."), 2)
    H.ok(M.cvars.emojiBubbles == nil)
end)

test("emojis: /bh emojis on|off sets the emojiBubbles CVar", function(M, ns)
    M.cvars.emojiBubbles = "1"
    local bh = M.env.SlashCmdList.BLEAKHOLD
    bh("emojis off")
    H.eq(M.cvars.emojiBubbles, "0")
    H.eq(printed(M, "Emoji bubbles are hidden (yours too); others still see the ones you send."), 1)
    bh("emojis")
    H.eq(printed(M, "Emoji bubbles are off. /bh emojis on|off"), 1)
    bh("emojis ON")
    H.eq(M.cvars.emojiBubbles, "1")
    H.eq(printed(M, "Emoji bubbles are shown."), 1)
    bh("emojis what")
    H.eq(printed(M, "Emoji bubbles are on. /bh emojis on|off"), 1)
end)

test("emojis: the preview pops like the bubble and hides for emotes", function(M, ns)
    FX.connect(M, H, EMOJI_BIT)
    local A = ns.Animations
    near(A.EmojiPop(0), 0, "0 s")
    near(A.EmojiPop(0.06), 0.9375, "0.06 s")
    near(A.EmojiPop(0.12), 1.25, "0.12 s")
    near(A.EmojiPop(0.185), 1.125, "0.185 s")
    near(A.EmojiPop(0.03), 0.546875, "0.03 s: ease-out growth")
    near(A.EmojiPop(0.1525), 1.2109375, "0.1525 s: smoothstep settle")
    near(A.EmojiPop(0.25), 1, "0.25 s")
    near(A.EmojiPop(3), 1, "3 s")
    local _, tab = openTab(M, ns, "emoji")
    H.eq(A.selected.key, "dance:string_swing", "the tab opens on the first entry")
    H.ok(not A.emojiPreview:IsShown(), "hidden for an emote")
    tab.entries[1]:Click("LeftButton")
    local tex = A.emojiPreview.tex
    H.ok(A.emojiPreview:IsShown(), "shown for an emoji")
    H.eq(tex.__texture, JOY)
    H.eq(tex:GetWidth(), 1, "starts from nothing")
    M.Advance(0.1)
    H.ok(tex:GetWidth() > 112, "overshoots while popping: " .. tex:GetWidth())
    M.Advance(0.2)
    H.eq(tex:GetWidth(), 112)
    H.eq(tex:GetHeight(), 112)
    H.ok(A.emojiPreview:GetScript("OnUpdate") == nil, "the pop is over")
    H.eq(A.model.__sequence, 0, "the model just stands")
    tab.right.play:Click()
    H.eq(tex:GetWidth(), 1, "sending pops it again")
    M.Advance(0.3)
    H.eq(tex:GetWidth(), 112)
    tab.filter:SetValue("all")
    tab.entries[1]:Click("LeftButton")
    H.ok(not A.emojiPreview:IsShown(), "selecting an emote hides it")
end)

test("emojis: a wheel saved before emojis gets the four emojis once, in free slots", function(M, ns)
    local A = ns.Animations
    H.eq(ns.cdb.emojiWheel, true, "flag set")
    H.eq(wheelPage(A, 4), "sit,emoji:joy,kneel,emoji:fire,emoji:heart,-,-,-",
        "the free slots of page 4; skull is on page 2 already")
    H.eq(wheelPage(A, 2), "emoji:skull,-,-,-,-,-,-,-")
    A.SetWheelSlot(4, 2, nil)
    A.EnsureWheel()
    H.eq(wheelPage(A, 4), "sit,-,kneel,emoji:fire,emoji:heart,-,-,-", "a removed emoji is not added back")
end, { before = function(M)
    M.env.BleakholdCharDB = { wheel = { { "dance" }, { "emoji:skull" }, {}, { [1] = "sit", [3] = "kneel" } } }
end })

test("emojis: seeding never replaces a slot", function(M, ns)
    local A = ns.Animations
    H.eq(wheelPage(A, 4), "dance,wave,bow,cheer,applaud,laugh,flex,kiss", "a full page stays as it was")
    H.ok(not A.OnWheel("emoji:joy"), "no emoji elsewhere either")
    H.eq(ns.cdb.emojiWheel, true)
end, { before = function(M)
    local full = { "dance", "wave", "bow", "cheer", "applaud", "laugh", "flex", "kiss" }
    M.env.BleakholdCharDB = { wheel = { {}, {}, {}, full } }
end })

test("emojis: a character that already had its emojis seeded keeps its wheel", function(M, ns)
    local A = ns.Animations
    H.eq(wheelPage(A, 4), "sit,-,-,-,-,-,-,-")
end, { before = function(M)
    M.env.BleakholdCharDB = { wheel = { {}, {}, {}, { "sit" } }, emojiWheel = true }
end })

test("emojis: the addon's timings are the client's (WoW/Common/BleakholdEmoji.h)", function(M, ns)
    local A = ns.Animations
    local h = H.ok(host_readfile(repo .. "/WoW/Common/BleakholdEmoji.h"), "client header")
    local function const(name)
        local v = h:match("BLEAKHOLD_EMOJI_" .. name .. "%s*=%s*([%d%.]+)f?;")
        H.ok(v, "constant BLEAKHOLD_EMOJI_" .. name)
        return tonumber(v)
    end
    local lifetime, pop, settle, scale = const("LIFETIME_MS"), const("POP_MS"), const("SETTLE_MS"), const("POP_SCALE")
    H.eq(lifetime, A.EMOJI_COOLDOWN * 1000, "the addon waits one bubble's lifetime")
    near(pop / 1000, A.EMOJI_POP, "POP_MS")
    near(settle / 1000, A.EMOJI_SETTLE, "SETTLE_MS")
    near(scale, A.EMOJI_POP_SCALE, "POP_SCALE")
    near(A.EmojiPop(pop / 1000), scale, "full size times POP_SCALE at POP_MS")
    H.ok(A.EmojiPop(pop / 1000 - 0.001) < scale, "still growing just before POP_MS")
    H.ok(A.EmojiPop(settle / 1000 - 0.001) > 1, "still settling just before SETTLE_MS")
    near(A.EmojiPop(settle / 1000), 1, "settled at SETTLE_MS")
end)
