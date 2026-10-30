-- Chat.lua's seen-two-word-names rule for an unquoted /w: two-word names seen this session (chat senders, guild
-- roster, friends, /who, group) are taken whole; the box keeps typing while a seen name starts with the words typed;
-- everything else is the stock extraction, so one-word names keep working. The stock 3.3.5a chat box parses the text
-- after every key (ChatEdit_OnTextChanged), a space twice (OnSpacePressed first) and once more on Enter
-- (ChatEdit_SendText), with no ChatEdit_ParseText hook in the addon.

local function editBox()
    local box = { attr = {} }
    function box:SetAttribute(k, v) self.attr[k] = v end
    function box:GetAttribute(k) return self.attr[k] end
    function box:SetText(t) self.text = t end
    return box
end

-- Types `text` after "/w " one key at a time and returns how many letters were typed when a target was taken (nil:
-- never, the box kept typing).
local function typeTell(extract, box, text)
    for i = 1, #text do
        local sofar = text:sub(1, i)
        for _ = 1, (text:sub(i, i) == " " and 2 or 1) do
            if extract(box, sofar) then
                return i
            end
        end
    end
    return nil
end

local function say(M, sender, event)
    M.FireEvent(event or "CHAT_MSG_SAY", "well met", sender, "Common", "", "", "", 0, 0, "", 0, 1)
end

test("chat: a two-word name seen in chat is taken whole, the box keeping on while it is typed", function(M, ns)
    local extract = M.env.ChatEdit_ExtractTellTarget
    H.eq(extract, ns.Chat.ExtractTellTarget, "the stock extraction is wrapped")
    say(M, "Arthas Menethil")
    H.eq(ns.Chat.SeenName("arthas menethil"), "Arthas Menethil")
    local box = editBox()
    H.eq(typeTell(extract, box, "Arthas Menethil the throne awaits"), #"Arthas Menethil ",
        "kept typing through the second word, taken at the space after it")
    H.eq(box.attr.tellTarget, "Arthas Menethil")
    H.eq(box.attr.chatType, "WHISPER")
    H.eq(box.text, "")
    H.eq(M.headerUpdated, box, "the chat header names the target")
    -- pasted or set at once, in any case: the seen spelling is the target
    box = editBox()
    H.eq(extract(box, "  arthas MENETHIL   the throne awaits"), true)
    H.eq(box.attr.tellTarget, "Arthas Menethil")
    H.eq(box.text, "the throne awaits")
    H.eq(ns.db.options.hintTwoNameWhisper, nil, "no hint for a two-word target")
end)

test("chat: two-word names are seen from chat, guild, friends, /who and the group, one-word names not", function(M, ns)
    local Chat = ns.Chat
    say(M, "Uther Lightbringer-Bleakhold", "CHAT_MSG_CHANNEL")
    say(M, "Kael Sunstrider", "CHAT_MSG_WHISPER")
    say(M, "Thrall")
    say(M, "|cffff0000Fake Name|r")
    H.eq(Chat.SeenName("Uther Lightbringer"), "Uther Lightbringer", "the realm part is not part of the name")
    H.eq(Chat.SeenName("Kael Sunstrider"), "Kael Sunstrider")
    H.eq(Chat.SeenName("Thrall"), nil, "a one-word name needs no memory")
    H.eq(Chat.SeenName("Fake Name"), nil)
    local guild = { { "Jaina Proudmoore", true }, { "Offline Person", false } }
    M.env.GetNumGuildMembers = function() return #guild end
    M.env.GetGuildRosterInfo = function(i)
        return guild[i][1], "Member", 1, 80, "Mage", "Dalaran", "", "", guild[i][2] and 1 or nil, 0, "MAGE"
    end
    M.FireEvent("GUILD_ROSTER_UPDATE")
    H.eq(Chat.SeenName("Jaina Proudmoore"), "Jaina Proudmoore", "an online guild member")
    H.eq(Chat.SeenName("Offline Person"), nil, "nobody whispers an offline member")
    M.env.GetNumFriends = function() return 1 end
    M.env.GetFriendInfo = function() return "Sylvanas Windrunner", 80, "Hunter", "Undercity", 1 end
    M.FireEvent("FRIENDLIST_UPDATE")
    H.eq(Chat.SeenName("Sylvanas Windrunner"), "Sylvanas Windrunner")
    M.env.GetNumWhoResults = function() return 1, 1 end
    M.env.GetWhoInfo = function() return "Varian Wrynn", "", 80, "Human", "Warrior", "Stormwind City", "WARRIOR" end
    M.FireEvent("WHO_LIST_UPDATE")
    H.eq(Chat.SeenName("Varian Wrynn"), "Varian Wrynn")
    local units = { party1 = "Tirion Fordring", raid1 = "Tirion Fordring", raid2 = "Bolvar Fordragon" }
    local unitName = M.env.UnitName
    M.env.UnitName = function(unit) return units[unit] or unitName(unit) end
    M.party = 1
    M.FireEvent("PARTY_MEMBERS_CHANGED")
    H.eq(Chat.SeenName("Tirion Fordring"), "Tirion Fordring")
    M.raid = 2
    M.FireEvent("RAID_ROSTER_UPDATE")
    H.eq(Chat.SeenName("Bolvar Fordragon"), "Bolvar Fordragon")
    local box = editBox()
    H.eq(M.env.ChatEdit_ExtractTellTarget(box, "Sylvanas Windrunner dark lady"), true)
    H.eq(box.attr.tellTarget, "Sylvanas Windrunner")
    H.eq(box.text, "dark lady")
end)

test("chat: an unseen one-word name with a message keeps the stock extraction", function(M, ns)
    local extract = M.env.ChatEdit_ExtractTellTarget
    local box = editBox()
    H.eq(typeTell(extract, box, "Thrall lok'tar ogar"), #"Thrall ", "taken at the first space, as stock")
    H.eq(box.attr.tellTarget, "Thrall")
    box = editBox()
    H.eq(extract(box, "Thrall lok'tar ogar"), true)
    H.eq(box.attr.tellTarget, "Thrall")
    H.eq(box.text, "lok'tar ogar")
    H.eq(ns.db.options.hintTwoNameWhisper, true, "a one-word target shows the hint")
    -- a seen two-word name sharing the first word: the box waits at "John ", then the second word decides
    say(M, "John Doe")
    box = editBox()
    H.eq(typeTell(extract, box, "John hello there"), #"John h", "no seen name goes on as \"john h\": stock")
    H.eq(box.attr.tellTarget, "John")
    H.eq(box.text, "h")
    box = editBox()
    H.eq(extract(box, "John hello there"), true)
    H.eq(box.attr.tellTarget, "John")
    H.eq(box.text, "hello there")
    box = editBox()
    H.eq(extract(box, "John Do you hear me"), true, "a finished second word that is not a seen name: stock")
    H.eq(box.attr.tellTarget, "John")
    H.eq(box.text, "Do you hear me")
    box = editBox()
    H.eq(typeTell(extract, box, "John Doer hi"), #"John Doer", "past every seen name: stock")
    H.eq(box.attr.tellTarget, "John")
    -- the stock autocomplete list still keeps its own two-word names whole
    M.autocomplete["Jaina Proudmoore"] = true
    box = editBox()
    H.eq(extract(box, "Jaina Proudmoore hello"), true)
    H.eq(box.attr.tellTarget, "Jaina Proudmoore")
    H.eq(box.text, "hello")
    -- a link is never a name
    H.eq(extract(editBox(), "|cffffd000|Hitem:1|h[x]|h|r "), false)
end)

test("chat: a quoted name still works, seen or not", function(M, ns)
    local extract = M.env.ChatEdit_ExtractTellTarget
    say(M, "Arthas Menethil")
    local box = editBox()
    H.eq(extract(box, ' "Arthas Menethil" the throne awaits'), true)
    H.eq(box.attr.tellTarget, "Arthas Menethil")
    H.eq(box.text, "the throne awaits")
    box = editBox()
    H.eq(extract(box, '"Kel Thuzad" rise'), true, "an unseen two-word name, quoted")
    H.eq(box.attr.tellTarget, "Kel Thuzad")
    H.eq(box.text, "rise")
    box = editBox()
    H.eq(typeTell(extract, box, '"Arthas Me'), nil, "an open quote: still typing")
    H.eq(box.attr.tellTarget, nil)
end)

test("chat: seen names are capped, the one seen longest ago dropped", function(M, ns)
    local Chat = ns.Chat
    local cap = Chat.SEEN_CAP
    H.eq(cap, 500)
    local function name(i) return "Alpha" .. i .. " Omega" end
    for i = 1, cap do
        Chat.RememberName(name(i))
    end
    H.eq(Chat.SeenName(name(1)), name(1))
    H.eq(Chat.SeenName(name(cap)), name(cap))
    say(M, name(1))    -- seen again: now the newest
    Chat.RememberName("Beta Omega")
    H.eq(Chat.SeenName("Beta Omega"), "Beta Omega")
    H.eq(Chat.SeenName(name(1)), name(1), "seen again, so kept")
    H.eq(Chat.SeenName(name(2)), nil, "the one seen longest ago is dropped")
    H.eq(Chat.SeenName(name(3)), name(3))
    -- a dropped name is unknown to /w again: stock
    local box = editBox()
    H.eq(M.env.ChatEdit_ExtractTellTarget(box, "Alpha2 Omega hi"), true)
    H.eq(box.attr.tellTarget, "Alpha2")
    -- many more sightings (with repeats) never grow past the cap
    for i = 1, 3 * cap do
        Chat.RememberName(name(1000 + i))
        Chat.RememberName("Beta Omega")
    end
    local kept = 0
    for i = 1, 3 * cap do
        if Chat.SeenName(name(1000 + i)) then kept = kept + 1 end
    end
    H.eq(kept, cap - 1, "the cap holds: the newest names and Beta Omega")
    H.eq(Chat.SeenName("Beta Omega"), "Beta Omega")
    H.eq(Chat.SeenName(name(1000 + 3 * cap)), name(1000 + 3 * cap))
    H.eq(Chat.SeenName(name(1000 + 2 * cap + 1)), nil)
    H.eq(Chat.SeenName(name(1)), nil)
end)

test("chat: /w First Last + Enter takes a seen name with nothing to say; typing never takes it early", function(M, ns)
    local extract = M.env.ChatEdit_ExtractTellTarget
    say(M, "Arthas Menethil")
    local box = editBox()
    H.eq(typeTell(extract, box, "Arthas Menethil"), nil, "the last letter typed: still typing")
    H.eq(box.attr.tellTarget, nil)
    H.eq(extract(box, "Arthas Menethil"), true, "Enter parses the same text again")
    H.eq(box.attr.tellTarget, "Arthas Menethil")
    H.eq(box.attr.chatType, "WHISPER")
    H.eq(box.text, "")
    -- a longer seen name that starts the same: typing goes on to it, Enter takes the shorter one
    say(M, "John Doe")
    say(M, "John Doeman")
    box = editBox()
    H.eq(typeTell(extract, box, "John Doeman be well"), #"John Doeman ")
    H.eq(box.attr.tellTarget, "John Doeman")
    H.eq(box.text, "")
    box = editBox()
    H.eq(typeTell(extract, box, "John Doe"), nil)
    H.eq(extract(box, "John Doe"), true)
    H.eq(box.attr.tellTarget, "John Doe")
    -- the unseen second word of a seen first word, and an unseen one-word name, with Enter: as stock
    box = editBox()
    H.eq(extract(box, "Thrall"), false)
    H.eq(extract(box, "Thrall"), false, "one word + Enter: stock")
    H.eq(box.attr.tellTarget, nil)
end)

test("chat: Enter on part of a seen name never closes the box: the one-word name gets the line", function(M, ns)
    local extract = M.env.ChatEdit_ExtractTellTarget
    say(M, "John Okafor")
    local box = editBox()
    H.eq(typeTell(extract, box, "John ok"), nil, "a seen name goes on as \"john ok\": still typing")
    H.eq(box.attr.tellTarget, nil)
    H.eq(extract(box, "John ok"), true, "Enter: the stock rules, not keep-typing (which would drop the line)")
    H.eq(box.attr.tellTarget, "John")
    H.eq(box.text, "ok")
    -- the same text parsed twice with no trailing space is Enter
    say(M, "John Doe")
    box = editBox()
    H.eq(extract(box, "John d"), false)
    H.eq(extract(box, "John d"), true)
    H.eq(box.attr.tellTarget, "John")
    H.eq(box.text, "d")
    -- and a whole seen name + Enter is still taken whole
    box = editBox()
    H.eq(typeTell(extract, box, "John Doe"), nil)
    H.eq(extract(box, "John Doe"), true)
    H.eq(box.attr.tellTarget, "John Doe")
    H.eq(box.text, "")
end)

test("chat: /w First + space + Enter opens a whisper to the one-word name that starts a seen name", function(M, ns)
    local extract = M.env.ChatEdit_ExtractTellTarget
    say(M, "John Smith")
    local box = editBox()
    H.eq(typeTell(extract, box, "John "), nil, "the space is parsed twice: still typing towards John Smith")
    H.eq(box.attr.tellTarget, nil)
    H.eq(extract(box, "John "), true, "a third parse of the same text is Enter: stock takes John")
    H.eq(box.attr.tellTarget, "John")
    H.eq(box.attr.chatType, "WHISPER")
    H.eq(box.text, "")
    -- a target taken starts the count again: the same box typing "John " next time still waits for the last name
    H.eq(extract(box, "John "), false, "first parse of the next space")
    H.eq(extract(box, "John "), false, "second parse of it")
    box.attr.tellTarget = nil
    H.eq(typeTell(extract, box, "John Smith hi"), #"John Smith ")
    H.eq(box.attr.tellTarget, "John Smith")
end)
