-- In-game additions: chat tags, toast, tooltip lines, minimap orbs, key tracker, countdown + DBM.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

------------------------------------------------------------------------------------------------------
-- Chat
------------------------------------------------------------------------------------------------------
test("chat: tags are coloured, links kept, other lines untouched", function(M, ns)
    local f = M.env.ChatFrame1
    local link = "|cffa335ee|Hitem:16864:0:0:0:0:0:0:0:80|h[Belt of Might]|h|r"
    H.eq(M.FilterChat("CHAT_MSG_SYSTEM", f, "[Raid Legacy] Aldric found " .. link), "|cffE5C07B[Raid Legacy]|r Aldric found " .. link)
    H.eq(M.FilterChat("CHAT_MSG_SYSTEM", f, "[Server First] Echo of Ragnaros defeated"), "|cffFF9D3B[Server First]|r Echo of Ragnaros defeated")
    H.eq(M.FilterChat("CHAT_MSG_SYSTEM", f, "[Season] War Effort reached 62%"), "|cff6CC6D9[Season]|r War Effort reached 62%")
    H.eq(M.FilterChat("CHAT_MSG_SYSTEM", f, "You are now AFK"), "You are now AFK")
    H.eq(M.FilterChat("CHAT_MSG_SYSTEM", f, "[Unknown Tag] hello"), "[Unknown Tag] hello")
end)

test("chat: the [War] tag of World PvP (section 10) is coloured and can be hidden", function(M, ns)
    local f = M.env.ChatFrame1
    H.eq(M.FilterChat("CHAT_MSG_SYSTEM", f, "[War] A Front starts in Crystalsong Forest in 15 minutes."),
        "|cffE0604A[War]|r A Front starts in Crystalsong Forest in 15 minutes.")
    M.env.SlashCmdList.BLEAKHOLD("chat war off 1")
    H.eq(M.FilterChat("CHAT_MSG_SYSTEM", f, "[War] The Alliance wins Crystalsong Forest."), nil)
end)

test("chat: the [Caf\195\169] tag of the cafe (section 21) is coloured and can be hidden", function(M, ns)
    local f = M.env.ChatFrame1
    H.eq(M.FilterChat("CHAT_MSG_SYSTEM", f, "[Caf\195\169] The Morning Rush starts in 5 minutes"),
        "|cffD8B98A[Caf\195\169]|r The Morning Rush starts in 5 minutes")
    H.eq(ns.Chat.byKey.cafe.color, "D8B98A")   -- BleakholdUi.Announce.Color.Cafe
    M.env.SlashCmdList.BLEAKHOLD("chat cafe off 1")
    H.eq(M.FilterChat("CHAT_MSG_SYSTEM", f, "[Caf\195\169] The Grinding Tusk out-brewed The Lion's Roast"), nil)
    M.env.SlashCmdList.BLEAKHOLD("chat cafe on 1")
    H.ok(M.FilterChat("CHAT_MSG_SYSTEM", f, "[Caf\195\169] back"))
end)

test("chat: a tag can be hidden per chat window", function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("chat season off 2")
    H.eq(M.FilterChat("CHAT_MSG_SYSTEM", M.env.ChatFrame2, "[Season] hidden here"), nil)
    H.ok(M.FilterChat("CHAT_MSG_SYSTEM", M.env.ChatFrame1, "[Season] shown here"), "still shown in window 1")
    M.env.SlashCmdList.BLEAKHOLD("chat season on 2")
    H.ok(M.FilterChat("CHAT_MSG_SYSTEM", M.env.ChatFrame2, "[Season] back"))
end)

test("chat: /w2 whispers a two-word name, or opens a whisper to it", function(M, ns)
    local w2 = M.env.SlashCmdList.BLEAKHOLDTELL
    H.eq(M.env.SLASH_BLEAKHOLDTELL1, "/w2")
    w2("  Arthas Menethil   the throne awaits  ")
    H.eq(#M.said, 1)
    H.eq(M.said[1].msg, "the throne awaits")
    H.eq(M.said[1].chatType, "WHISPER")
    H.eq(M.said[1].target, "Arthas Menethil")
    w2("Jaina Proudmoore")
    H.eq(M.tellOpened, "Jaina Proudmoore", "no message: whisper opened")
    H.eq(#M.said, 1)
    w2("Thrall")
    H.eq(#M.said, 1, "one word: usage, nothing sent")
    w2("A B " .. string.rep("x", 300))
    H.eq(#M.said[2].msg, 255, "long message cut to 255 bytes")
    H.eq(ns.Chat.FitBytes("ab\195\169", 3), "ab", "never cuts a UTF-8 letter")
    H.eq(ns.Chat.FitBytes("ab\195\169", 4), "ab\195\169")
end)

local function editBox()
    local box = { attr = {} }
    function box:SetAttribute(k, v) self.attr[k] = v end
    function box:GetAttribute(k) return self.attr[k] end
    function box:SetText(t) self.text = t end
    return box
end

test("chat: /w takes a quoted two-word name whole, and keeps the stock extraction otherwise", function(M, ns)
    local extract = M.env.ChatEdit_ExtractTellTarget
    H.eq(extract, ns.Chat.ExtractTellTarget, "the stock extraction is wrapped")
    local box = editBox()
    H.eq(extract(box, ' "Arthas Menethil" the throne awaits'), true)
    H.eq(box.attr.tellTarget, "Arthas Menethil")
    H.eq(box.attr.chatType, "WHISPER")
    H.eq(box.text, "the throne awaits")
    H.eq(M.headerUpdated, box, "the chat header names the target")
    box = editBox()
    H.eq(extract(box, ' "Arthas Mene'), false, "an open quote: still typing")
    H.eq(box.attr.tellTarget, nil)
    -- unquoted: the stock rules (a two-word name on the autocomplete list stays whole)
    M.autocomplete["Jaina Proudmoore"] = true
    box = editBox()
    H.eq(extract(box, "Jaina Proudmoore hello"), true)
    H.eq(box.attr.tellTarget, "Jaina Proudmoore")
    H.eq(box.text, "hello")
    H.eq(ns.db.options.hintTwoNameWhisper, nil, "no hint for a two-word target")
    box = editBox()
    H.eq(extract(box, "Thrall lok'tar"), true)
    H.eq(box.attr.tellTarget, "Thrall")
    H.eq(ns.db.options.hintTwoNameWhisper, true, "a one-word target shows the hint once")
    local printed = #M.chat
    extract(editBox(), "Thrall again")
    H.eq(#M.chat, printed, "only once")
end)

test("chat: /friend takes a quoted name or two capitalised words as one name", function(M, ns)
    local friend = M.env.SlashCmdList.FRIENDS
    friend("Arthas Menethil")
    H.eq(M.friended.name, "Arthas Menethil")
    H.eq(M.friended.note, "")
    friend('"Sylvanas Windrunner" ranger')
    H.eq(M.friended.name, "Sylvanas Windrunner")
    H.eq(M.friended.note, "ranger")
    friend("\195\137lise Dupont")
    H.eq(M.friended.name, "\195\137lise Dupont", "a capital letter outside ASCII")
    friend("Thrall warchief")
    H.eq(M.friended.name, "Thrall", "lower-case second word: the stock name and note")
    H.eq(M.friended.note, "warchief")
    M.friendsPanel = nil
    friend("")
    H.eq(M.friendsPanel, true, "no name: the stock command (friends panel)")
end)

test("chat: the stock 12-letter name boxes take 25 letters", function(M, ns)
    for _, which in ipairs({ "ADD_GUILDMEMBER", "ADD_TEAMMEMBER", "ADD_RAIDMEMBER", "ADD_MUTE" }) do
        H.eq(M.env.StaticPopupDialogs[which].maxLetters, 25, which)
    end
    H.eq(M.env.StaticPopupDialogs.ADD_FRIEND.maxLetters, 77, "longer boxes are left alone")
    H.eq(M.env.SendMailNameEditBox:GetMaxLetters(), 25)
end)

------------------------------------------------------------------------------------------------------
-- Toast
------------------------------------------------------------------------------------------------------
test("toast: a task becoming claimable shows the toast; click opens Tasks", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    H.send(M, "TASK", { { 2, 102, 20, 1 } })
    local t = M.env.BleakholdToastFrame
    H.ok(t:IsShown())
    H.eq(t.kicker:GetText(), "Daily Task Complete")
    H.eq(t.title:GetText(), "Key sweeper")
    H.eq(t.sub:GetText(), "Claim 1 Emblem of Heroism in Activities")
    t:Click()
    H.ok(M.env.BleakholdActivitiesFrame:IsShown() and ns.Activities.current == "tasks")
end)

test("toast: queue of three, five seconds each", function(M, ns)
    for i = 1, 5 do ns.Toast.Push({ title = "T" .. i }) end
    H.eq(ns.Toast.Pending(), 4, "one showing, three waiting")
    H.eq(M.env.BleakholdToastFrame.title:GetText(), "T1")
    M.Advance(5.2)
    H.eq(M.env.BleakholdToastFrame.title:GetText(), "T3", "oldest waiting toast dropped when full")
    M.Advance(16)
    H.ok(not M.env.BleakholdToastFrame:IsShown(), "all shown")
end)

test("toast: server TOAST op", function(M, ns)
    FX.connect(M, H)
    H.send(M, "TOAST", { { "R", "New record", "Halls of Lightning +8", "leaderboards" } })
    H.eq(M.env.BleakholdToastFrame.kicker:GetText(), "New Record")
    M.env.BleakholdToastFrame:Click()
    H.ok(M.env.BleakholdLeaderboardsFrame:IsShown())
end)

test("toast: the server's 'Keys window' line names the Mythic+ Dungeons page", function(M, ns)
    FX.connect(M, H)
    -- bh_ui_bridge.cpp, the keystone used at its dungeon
    H.send(M, "TOAST", { { "K", "Keystone ready", "Press Start keystone in the Keys window", "keys" } })
    H.eq(M.env.BleakholdToastFrame.sub:GetText(), "Press Start keystone on the Mythic+ Dungeons page")
    H.eq(ns.Toast.FixSub("Press Start keystone in the Keys window", "tasks"), "Press Start keystone in the Keys window",
        "only for its own target")
end)

------------------------------------------------------------------------------------------------------
-- Tooltip
------------------------------------------------------------------------------------------------------
test("tooltip: legacy lines once per item, collected state", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    local tt = M.env.GameTooltip
    tt:SetOwner(M.env.UIParent, "ANCHOR_NONE")
    tt:SetHyperlink("item:16864")
    local text = table.concat(tt.__lines, "\n")
    H.contains(text, "Raid Legacy - Molten Core era")
    H.contains(text, "Drops in Blackrock Spire, Stratholme, Scholomance, Dire Maul and Hellfire Ramparts (58-61)")
    H.contains(text, "Look collected for your account")
    local n = tt:NumLines()
    M.Fire(tt, "OnTooltipSetItem")      -- the client can fire it again for the same item
    H.eq(tt:NumLines(), n, "no duplicate lines")
    tt:SetHyperlink("item:16866")
    H.contains(table.concat(tt.__lines, "\n"), "Look not collected")
    tt:SetHyperlink("item:6948")
    H.eq(tt:NumLines(), 1, "other items untouched")
end)

test("tooltip: keystone lines on the player's keystone", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    local tt = M.env.ItemRefTooltip
    tt:SetOwner(M.env.UIParent, "ANCHOR_NONE")
    tt:SetHyperlink("item:900001")
    local text = table.concat(tt.__lines, "\n")
    H.contains(text, "Halls of Lightning +8")
    H.contains(text, "Affixes: Fortified, Bolstering, Volcanic")
    H.contains(text, "Dungeon mode: Mythic")
end)

------------------------------------------------------------------------------------------------------
-- Minimap orbs
------------------------------------------------------------------------------------------------------
test("orbs: holder is a UIParent child anchored to the Minimap, never a Minimap child", function(M, ns)
    local holder = M.env.BleakholdOrbHolder
    H.eq(holder:GetParent(), M.env.UIParent)
    M.Advance(1.1)
    local _, rel = holder:GetPoint(1)
    H.eq(rel, M.env.Minimap, "anchored to the minimap centre")
    -- AddicatUI collects the Buttons parented to Minimap and MinimapBackdrop (and one Frame further down): of ours,
    -- only a plain frame without Buttons may hang there (the Royale minimap layer, RoyaleMinimap.lua)
    for _, parent in ipairs({ M.env.Minimap, M.env.MinimapBackdrop }) do
        for _, c in ipairs(parent.__children) do
            if tostring(c:GetName()):find("Bleakhold") then
                H.eq(c:GetObjectType(), "Frame", "no Button of ours on " .. parent:GetName())
                H.eq(#M.Clickables(c), 0, "no Button inside " .. c:GetName())
            end
        end
    end
    local orb = M.env.BleakholdOrb_activities
    H.eq(orb:GetParent(), holder)
    local _, _, _, x, y = orb:GetPoint(1)
    H.ok(x < 0 and y < 0, "Activities orb below-left of the map")
end)

test("orbs: click opens, badge shows claimable tasks, right-drag saves the angle", function(M, ns)
    FX.connect(M, H)
    FX.all(M, H)
    M.env.BleakholdOrb_collections:Click()
    H.ok(M.env.BleakholdCollectionsFrame:IsShown())
    H.ok(M.env.BleakholdOrb_activities.dot:IsShown(), "claimable badge")
    local orb = M.env.BleakholdOrb_season
    M.Fire(orb, "OnDragStart")
    M.Advance(0.2)
    M.Fire(orb, "OnDragStop")
    H.eq(type(M.env.BleakholdCharDB.orbs.season), "number", "angle saved")
    -- the pressed shade over the picture: not in its ARTWORK layer (the client sorts one layer by texture)
    H.eq(orb.pressed.__layer, "OVERLAY")
    H.eq(orb.glyph.__layer, "ARTWORK")
end)

test("orbs: the War Mode orb only with HELLO bit 16384 (32768 alone is not War Mode)", function(M, ns)
    local orb = M.env.BleakholdOrb_warmode
    H.ok(not orb:IsShown(), "hidden before HELLO")
    FX.connect(M, H, { [6] = 32768 })
    H.ok(not orb:IsShown(), "World PvP alone: no War Mode")
    H.hello(M, { [6] = 16384 })
    H.ok(orb:IsShown(), "War Mode live")
    H.hello(M, { [6] = 16384 + 32768 })
    H.ok(orb:IsShown())
    H.hello(M, { [6] = 0 })
    H.ok(not orb:IsShown(), "switched off at runtime")
    for _, o in ipairs(ns.Orbs.list) do
        if o.key == "warmode" then H.eq(o.angle, 70, "its own place on the ring") end
    end
end)

test("orbs: square minimap puts orbs on the edge", function(M, ns)
    local x, y = ns.Orbs.Offset(225, 80, "SQUARE")
    H.ok(math.abs(math.abs(x) - 80) < 0.01 and math.abs(math.abs(y) - 80) < 0.01, "corner")
    local rx, ry = ns.Orbs.Offset(270, 80, "ROUND")
    H.ok(math.abs(rx) < 0.01 and math.abs(ry + 80) < 0.01, "bottom of the circle")
end)

------------------------------------------------------------------------------------------------------
-- Key tracker and countdown
------------------------------------------------------------------------------------------------------
local function startRun(M)
    local ex = FX.examples(M)
    H.send(M, "MPS", ex.MPS)
end

test("countdown: shown from MPS, the pull bar counts, pull numerals for the last five seconds, gone at zero",
    function(M, ns)
    FX.connect(M, H)
    startRun(M)
    local cd = M.env.BleakholdCountdown
    H.ok(cd:IsShown())
    H.eq(cd.title:GetText(), "Halls of Lightning +8")
    H.ok(#M.FindText("The Black Temple era", true) > 0, "era")
    H.ok(cd.bar:IsShown(), "our bar while DBM's does not show")
    H.eq(cd.bar.name:GetText(), "Pull in"); H.eq(cd.bar.time:GetText(), "10.0")
    H.ok(not cd.digits[1]:IsShown(), "no numeral above five seconds")
    M.Advance(6)
    H.ok(cd.digits[1]:IsShown(), "a numeral under five seconds")
    H.eq(cd.digits[1].glyph, "4", "the pull atlas's 4")
    H.contains(cd.digits[1].tex:GetTexture(), "Art\\Royale\\Pull")
    H.eq(cd.bar.time:GetText(), "4.0")
    M.Advance(1.05)
    H.eq(cd.digits[1].glyph, "3"); H.ok(cd.digits[2]:IsShown(), "the 4 fades out")
    M.Advance(0.3)
    H.ok(not cd.digits[2]:IsShown(), "faded")
    M.Advance(2.85)
    H.ok(not cd:IsShown(), "hidden at zero")
end)

test("countdown: DBM pull timer from the party leader, cancel sends 0", function(M, ns)
    FX.connect(M, H)
    M.SetGroup("PARTY", 5, true)
    startRun(M)
    local pt
    for _, s in ipairs(M.sent) do if s.prefix == "DBMv4-PT" then pt = s end end
    H.ok(pt, "DBM message sent")
    H.eq(pt.msg, "10")
    H.eq(pt.channel, "PARTY")
    H.send(M, "MP", { { 7001, 0, 1800, 0, 0, 0, 100, 0, "", "", 4 } })
    H.eq(M.sent[#M.sent].prefix, "DBMv4-PT")
    H.eq(M.sent[#M.sent].msg, "0", "cancel")
end)

test("countdown: no DBM message from a non-leader, or when the server sends it", function(M, ns)
    FX.connect(M, H)
    M.SetGroup("PARTY", 5, false)
    startRun(M)
    for _, s in ipairs(M.sent) do H.ok(s.prefix ~= "DBMv4-PT", "non-leader sent nothing") end
end)

test("countdown: server-side DBM feature bit", function(M, ns)
    FX.connect(M, H, { [6] = 4 })
    M.SetGroup("RAID", 10, true)
    startRun(M)
    for _, s in ipairs(M.sent) do H.ok(s.prefix ~= "DBMv4-PT", "server sends DBM itself") end
end)

test("countdown: raid leader uses RAID; solo with DBM whispers itself", function(M, ns)
    FX.connect(M, H)
    M.SetGroup("RAID", 10, true)
    startRun(M)
    H.eq(M.sent[#M.sent].channel, "RAID")
end)

-- DBM's bar module as DBM-Core has it (DBT: GetBar by the bar's name)
local function fakeDbm(M)
    local bars = {}
    M.env.DBM = { Options = {}, Bars = { GetBar = function(_, name) return bars[name] end } }
    return bars
end

test("countdown: ours hides only while DBM really shows its Pull in bar, and comes back if DBM's goes", function(M, ns)
    FX.connect(M, H)
    -- a member, not the leader: the leader turned the pull timer off (/bh dbm off), so no DBM bar comes
    M.SetGroup("PARTY", 5, false)
    local bars = fakeDbm(M)
    startRun(M)
    local cd = M.env.BleakholdCountdown
    M.Advance(0.3)
    H.ok(cd.bar:IsShown(), "no DBM bar: ours, not nothing")
    bars["Pull in"] = {}
    M.Advance(0.3)
    H.ok(not cd.bar:IsShown(), "DBM shows its bar: ours hides")
    bars["Pull in"] = nil
    M.Advance(0.3)
    H.ok(cd.bar:IsShown(), "DBM's went before zero: ours again")
    -- a DBM that cannot be asked: only a pull timer that surely went out hides ours
    M.env.DBM = { Options = {} }
    M.Advance(0.3)
    H.ok(cd.bar:IsShown(), "a member's DBM, nothing sent")
end)

test("countdown: solo with DBM loaded whispers the pull timer to itself", function(M, ns)
    FX.connect(M, H)
    M.env.DBM = { Options = { DontShowPTCountdownText = false } }
    startRun(M)
    local s = M.sent[#M.sent]
    H.eq(s.prefix, "DBMv4-PT")
    H.eq(s.channel, "WHISPER")
    H.eq(s.target, M.playerName)
end)

test("tracker: timer, deaths, bosses, forces, over time, end summary", function(M, ns)
    FX.connect(M, H)
    startRun(M)
    local t = M.env.BleakholdKeyTracker
    H.ok(t:IsShown(), "shown during the countdown")
    H.contains(t.timer:GetText(), "Starts in")
    M.Advance(10.5)
    H.send(M, "MP", { { 7001, 1122000, 1800, 2, 10, 64, 100, 1, { 300 }, { 1260, 1440 }, 1 } })
    H.eq(t.title:GetText(), "Halls of Lightning +8")
    H.eq(t.deaths.text:GetText(), "2 deaths")
    H.eq(t.timer:GetText(), "18:42")
    H.eq(t.limit:GetText(), "/ 30:00")
    H.eq(t.bosses[1].name:GetText(), "General Bjarngrim")
    H.eq(t.bosses[1].state:GetText(), "done")
    H.eq(t.bosses[2].state:GetText(), "-")
    H.eq(t.forcesText:GetText(), "Enemy forces 64.0%")
    M.Advance(3.3)
    H.eq(t.timer:GetText(), "18:45", "counts on between updates")
    H.send(M, "MP", { { 7001, 1900000, 1800, 2, 10, 100, 100, 15, { 300, 600, 900, 1200 }, "", 1 } })
    local r = t.timer.__tcolor
    H.ok(r[1] > 0.8 and r[2] < 0.5, "red over time")
    H.eq(t.forcesText:GetText(), "Enemy forces 100%")
    H.send(M, "MPE", FX.examples(M).MPE)
    H.eq(t.result:GetText(), "Timed!")
    H.ok(#M.FindText("Keystone +1: Halls of Stone +9", true) > 0)
    H.ok(#M.FindText("+ Spoils chest", true) > 0)
    M.Advance(61)
    H.ok(not t:IsShown(), "summary hides after a minute")
end)

test("tracker: sits beside DragonUI's tracker when present", function(M, ns)
    FX.connect(M, H)
    startRun(M)
    local _, rel = M.env.BleakholdKeyTracker:GetPoint(1)
    H.eq(rel, M.env.DragonUI_QuestTrackerFrame)
    H.eq(M.env.DragonUIObjectiveTracker.__alpha, 1, "DragonUI's frames are not changed")
end, { before = function(M)
    M.New("Frame", "DragonUI_QuestTrackerFrame", M.env.UIParent)
    M.New("Frame", "DragonUIObjectiveTracker", M.env.DragonUI_QuestTrackerFrame)
end })
