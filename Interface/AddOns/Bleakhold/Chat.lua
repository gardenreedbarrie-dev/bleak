-- Bleakhold: colour the server's announcement tags in chat ([Raid Legacy], [Server First], [Season],
-- [Queue], [Record], [Case], [Royale], [War], [Caf\195\169]) and let each chat window hide a tag. The server
-- sends these as plain system text that reads fine without the addon; links in the message are left exactly as the
-- server sent them.
-- Also /w2 for whispers to two-word character names (the server's mod-two-names), quoted names in /w, two-word
-- names in /w once seen this session, two-word names in /friend and name boxes long enough for them.
local ADDON, ns = ...
local Data = ns.Data

local Chat = {}
ns.Chat = Chat

local byTag, byKey = {}, {}
for _, t in ipairs(Data.chatTags) do
    byTag[t.tag] = t
    byKey[t.key] = t
end
Chat.byKey = byKey

local function frameName(frame)
    if type(frame) == "table" and frame.GetName then
        return frame:GetName() or "?"
    end
    return "?"
end

function Chat.IsHidden(frame, key)
    local h = ns.db.chat.hidden[frameName(frame)]
    return h and h[key] and true or false
end

function Chat.SetHidden(frameKey, key, hidden)
    local all = ns.db.chat.hidden
    all[frameKey] = all[frameKey] or {}
    all[frameKey][key] = hidden and true or nil
end

-- Chat filter: (self, event, message, ...) -> true to hide, or false, newMessage, ...
function Chat.Filter(frame, event, msg, ...)
    if type(msg) ~= "string" then
        return false
    end
    local tag, rest = msg:match("^%[([^%]|]+)%]%s?(.*)$")
    local def = tag and byTag[tag]
    if not def then
        return false
    end
    if Chat.IsHidden(frame, def.key) then
        return true
    end
    return false, "|cff" .. def.color .. "[" .. tag .. "]|r " .. rest, ...
end

if ChatFrame_AddMessageEventFilter then
    ChatFrame_AddMessageEventFilter("CHAT_MSG_SYSTEM", Chat.Filter)
end

ns.AddCommand("chat", "chat tags: /bh chat [tag on|off [window]]", function(args)
    local key, state, win = args:match("^(%S*)%s*(%S*)%s*(%S*)$")
    if not key or key == "" then
        for _, t in ipairs(Data.chatTags) do
            local hiddenIn = {}
            for name, h in pairs(ns.db.chat.hidden) do
                if h[t.key] then
                    hiddenIn[#hiddenIn + 1] = name
                end
            end
            ns.Print(string.format("|cff%s[%s]|r (%s): %s", t.color, t.tag, t.key, #hiddenIn > 0 and ("hidden in " .. table.concat(hiddenIn, ", ")) or "shown"))
        end
        return
    end
    local def = byKey[key:lower()]
    if not def or (state ~= "on" and state ~= "off") then
        ns.Print("usage: /bh chat <legacy|first|season|queue|record|case|royale|war|cafe> <on|off>"
            .. " [chat window number]")
        return
    end
    local n = tonumber(win) or 1
    Chat.SetHidden("ChatFrame" .. n, def.key, state == "off")
    ns.Print(string.format("[%s] %s in chat window %d", def.tag, state == "off" and "hidden" or "shown", n))
end)

-- Whispers to two-word names. The stock /w already takes a two-word name it can complete (friends, guild,
-- group, recent whispers); clicking a name and /r work for any name. /w2 First Last [message] works for any
-- name without hooking the chat box: with a message it whispers, without one it opens a whisper to that name.
local MAX_CHAT_BYTES = 255

-- The longest start of `text` that fits in `bytes` without cutting a UTF-8 character.
local function fitBytes(text, bytes)
    if #text <= bytes then
        return text
    end
    local cut = bytes
    while cut > 0 and text:byte(cut + 1) and text:byte(cut + 1) >= 128 and text:byte(cut + 1) < 192 do
        cut = cut - 1
    end
    return text:sub(1, cut)
end
Chat.FitBytes = fitBytes

function Chat.Whisper2(msg)
    local first, last, text = (msg or ""):match("^%s*(%S+)%s+(%S+)%s*(.-)%s*$")
    if not first then
        ns.Print("usage: /w2 First Last message")
        return
    end
    local name = first .. " " .. last
    if text == "" then
        if ChatFrame_SendTell then
            ChatFrame_SendTell(name)
        end
        return
    end
    SendChatMessage(fitBytes(text, MAX_CHAT_BYTES), "WHISPER", nil, name)
end

SLASH_BLEAKHOLDTELL1 = "/w2"
SLASH_BLEAKHOLDTELL2 = "/tell2"
SlashCmdList["BLEAKHOLDTELL"] = Chat.Whisper2

-- Typed /w with a two-word name. The stock extraction keeps a two-word target only when it is on the autocomplete
-- list, so `/w Arthas Menethil hi` whispers "Arthas" (who may be someone else). A quoted name is taken whole:
-- /w "Arthas Menethil" hi, and so is a two-word name seen this session (below). The first time a /w takes a one-word
-- target, a hint names the quoted form and /w2.
local stockExtractTellTarget = ChatEdit_ExtractTellTarget

local function hintTwoNames()
    local options = ns.db and ns.db.options
    if not options or options.hintTwoNameWhisper then
        return
    end
    options.hintTwoNameWhisper = true
    ns.Print('two-word names: /w "First Last" message, or /w2 First Last message')
end

-- Two-word names seen this session: chat senders, the guild roster, friends, /who results and the group. An
-- unquoted /w keeps typing while a seen name starts with the words typed so far and takes "First Last" whole once it
-- is a seen name; anything else goes to the stock rules, so one-word names (valid on this realm) work as before.
-- Kept for the session only; past SEEN_CAP names the one seen longest ago is dropped.
Chat.SEEN_CAP = 500

local seen = {}         -- "first last" (lower case) -> { key =, name = "First Last", first = "first", seq = }
local seenByFirst = {}  -- "first" -> { ["first last"] = entry }
local seenCount, seenSeq = 0, 0
-- One slot per sighting, oldest first; a slot whose seq is no longer its entry's is stale (seen again since).
local queueKey, queueSeq, queueHead, queueTail = {}, {}, 1, 0

local function forget(key)
    local e = seen[key]
    seen[key] = nil
    seenCount = seenCount - 1
    local group = seenByFirst[e.first]
    group[key] = nil
    if not next(group) then
        seenByFirst[e.first] = nil
    end
end

local function compactQueue()
    local live = {}
    for _, e in pairs(seen) do
        live[#live + 1] = e
    end
    table.sort(live, function(a, b) return a.seq < b.seq end)
    queueKey, queueSeq = {}, {}
    for i, e in ipairs(live) do
        queueKey[i], queueSeq[i] = e.key, e.seq
    end
    queueHead, queueTail = 1, #live
end

function Chat.RememberName(name)
    if type(name) ~= "string" or name:find("|", 1, true) then
        return
    end
    local first, last = (name:match("^([^%-]+)") or ""):match("^(%S+) (%S+)$")    -- no realm part; two words
    if not first then
        return
    end
    local full = first .. " " .. last
    local key = full:lower()
    seenSeq = seenSeq + 1
    local e = seen[key]
    if e then
        e.name, e.seq = full, seenSeq
    else
        e = { key = key, name = full, first = first:lower(), seq = seenSeq }
        seen[key] = e
        seenCount = seenCount + 1
        local group = seenByFirst[e.first]
        if not group then
            group = {}
            seenByFirst[e.first] = group
        end
        group[key] = e
    end
    queueTail = queueTail + 1
    queueKey[queueTail], queueSeq[queueTail] = key, seenSeq
    local cap = math.max(1, Chat.SEEN_CAP)
    while seenCount > cap do
        local k, s = queueKey[queueHead], queueSeq[queueHead]
        queueKey[queueHead], queueSeq[queueHead] = nil, nil
        queueHead = queueHead + 1
        local old = seen[k]
        if old and old.seq == s then
            forget(k)
        end
    end
    if queueTail - queueHead + 1 > 2 * cap + 64 then
        compactQueue()
    end
end

-- The seen spelling of "First Last" (any case), or nil.
function Chat.SeenName(name)
    local e = type(name) == "string" and seen[name:lower()]
    return e and e.name or nil
end

-- Whether a seen name starting with "first " runs on past `prefix` ("first" .. " " .. part of the second word).
local function seenRunsPast(first, prefix)
    for key in pairs(seenByFirst[first]) do
        if #key > #prefix and key:sub(1, #prefix) == prefix then
            return true
        end
    end
    return false
end

-- The seen-name rule for a /w target. nil: not a seen name, use the stock rules; false: keep typing; or the name and
-- the message after it. The stock box parses on every key (ChatEdit_OnTextChanged), a typed space twice
-- (OnSpacePressed, then OnTextChanged) and once more on Enter (ChatEdit_SendText); nothing tells the addon which.
-- `parses` is how many times in a row the box has parsed this same text: text ending in whitespace is parsed twice by
-- its space, so a third parse is Enter; text without it once by its last key, so a second parse is Enter. On Enter the
-- rule never says "keep typing": the stock box would close and drop the line (processChatType, send == 1).
function Chat.SeenTellTarget(msg, parses)
    parses = tonumber(parses) or 1
    local w1, s1, w2, s2, rest = (msg or ""):match("^%s*([^%s|]%S*)(%s*)(%S*)(%s*)(.*)$")
    if not w1 or s1 == "" then
        return nil
    end
    local first = w1:lower()
    if not seenByFirst[first] then
        return nil
    end
    if w2 == "" then
        if parses >= 3 then
            return nil    -- "/w First " + Enter: the one-word name First, as stock
        end
        return false    -- "First ": a seen name goes on
    end
    local key = first .. " " .. w2:lower()
    local e = seen[key]
    if s2 ~= "" then
        if e then
            return e.name, rest
        end
        return nil
    end
    if parses >= 2 then
        if e then
            return e.name, ""    -- "/w First Last" + Enter
        end
        return nil    -- "/w First ok" + Enter: as stock, "ok" to First
    end
    if e or seenRunsPast(first, key) then
        return false
    end
    return nil
end

-- edit box -> the text it last parsed, and how many times in a row (reset once a target is taken)
local lastParsed = setmetatable({}, { __mode = "k" })
local parsedTimes = setmetatable({}, { __mode = "k" })

local function rememberGroup()
    for i = 1, (GetNumPartyMembers and GetNumPartyMembers() or 0) do
        Chat.RememberName((UnitName("party" .. i)))
    end
    for i = 1, (GetNumRaidMembers and GetNumRaidMembers() or 0) do
        Chat.RememberName((UnitName("raid" .. i)))
    end
end

for _, event in ipairs({ "CHAT_MSG_SAY", "CHAT_MSG_YELL", "CHAT_MSG_EMOTE", "CHAT_MSG_TEXT_EMOTE", "CHAT_MSG_WHISPER",
    "CHAT_MSG_WHISPER_INFORM", "CHAT_MSG_PARTY", "CHAT_MSG_PARTY_LEADER", "CHAT_MSG_RAID", "CHAT_MSG_RAID_LEADER",
    "CHAT_MSG_RAID_WARNING", "CHAT_MSG_BATTLEGROUND", "CHAT_MSG_BATTLEGROUND_LEADER", "CHAT_MSG_GUILD",
    "CHAT_MSG_OFFICER", "CHAT_MSG_CHANNEL" }) do
    ns.RegisterEvent(event, function(_, _, sender)
        Chat.RememberName(sender)
    end)
end
ns.RegisterEvent("GUILD_ROSTER_UPDATE", function()
    if not (GetNumGuildMembers and GetGuildRosterInfo) then
        return
    end
    for i = 1, (GetNumGuildMembers(true) or 0) do
        local name, _, _, _, _, _, _, _, online = GetGuildRosterInfo(i)
        if online then
            Chat.RememberName(name)
        end
    end
end)
ns.RegisterEvent("FRIENDLIST_UPDATE", function()
    if not (GetNumFriends and GetFriendInfo) then
        return
    end
    for i = 1, (GetNumFriends() or 0) do
        Chat.RememberName((GetFriendInfo(i)))
    end
end)
ns.RegisterEvent("WHO_LIST_UPDATE", function()
    if not (GetNumWhoResults and GetWhoInfo) then
        return
    end
    for i = 1, ((GetNumWhoResults()) or 0) do
        Chat.RememberName((GetWhoInfo(i)))
    end
end)
ns.RegisterEvent("PARTY_MEMBERS_CHANGED", rememberGroup)
ns.RegisterEvent("RAID_ROSTER_UPDATE", rememberGroup)
ns.RegisterEvent("PLAYER_ENTERING_WORLD", rememberGroup)

local function setTell(editBox, name, rest)
    lastParsed[editBox], parsedTimes[editBox] = nil, nil
    editBox:SetAttribute("tellTarget", name)
    editBox:SetAttribute("chatType", "WHISPER")
    editBox:SetText(rest)
    ChatEdit_UpdateHeader(editBox)
end

function Chat.ExtractTellTarget(editBox, msg)
    msg = msg or ""
    local parses = 1
    if type(editBox) == "table" then
        if lastParsed[editBox] == msg then
            parses = (parsedTimes[editBox] or 1) + 1
        end
        lastParsed[editBox], parsedTimes[editBox] = msg, parses
    end
    local name, rest = msg:match('^%s*"([^"]+)"%s(.*)$')
    name = name and name:match("^%s*(.-)%s*$")
    if name and name ~= "" then
        setTell(editBox, name, rest)
        return true
    end
    if msg:match('^%s*"') then
        return false    -- the quoted name is still being typed
    end
    name, rest = Chat.SeenTellTarget(msg, parses)
    if name == false then
        return false
    elseif name then
        setTell(editBox, name, rest)
        return true
    end
    local taken = stockExtractTellTarget and stockExtractTellTarget(editBox, msg)
    if taken then
        if type(editBox) == "table" then
            lastParsed[editBox], parsedTimes[editBox] = nil, nil
        end
        if not (editBox:GetAttribute("tellTarget") or ""):find(" ", 1, true) then
            hintTwoNames()
        end
    end
    return taken
end

if stockExtractTellTarget then
    ChatEdit_ExtractTellTarget = Chat.ExtractTellTarget
end

-- /friend with a two-word name: the stock command adds (or, for a friend, REMOVES) the first word and makes the
-- second the note. A quoted name, or two capitalised words, is one name; anything else goes to the stock command.
local CAPITALISED = "[%u\192-\255][%a\128-\255]*"

function Chat.Friend(msg, editBox)
    msg = msg or ""
    local name, note = msg:match('^%s*"([^"]+)"%s*(.-)%s*$')
    if not name then
        local first, last, rest = msg:match("^%s*(" .. CAPITALISED .. ")%s+(" .. CAPITALISED .. ")%s*(.-)%s*$")
        if first then
            name, note = first .. " " .. last, rest
        end
    end
    name = name and name:match("^%s*(.-)%s*$")
    if name and name ~= "" then
        AddOrRemoveFriend(name, note)
    elseif Chat.stockFriends then
        Chat.stockFriends(msg, editBox)
    end
end

if SlashCmdList and SlashCmdList.FRIENDS then
    Chat.stockFriends = SlashCmdList.FRIENDS
    SlashCmdList.FRIENDS = Chat.Friend
end

-- Name boxes the stock interface stops at 12 letters; two-word names are up to 25 (TwoNames.MaxNameLength).
-- The engine also cuts text set from code, so Mail's Reply and shift-clicked names were cut too.
local NAME_LETTERS = 25
for _, which in ipairs({ "ADD_GUILDMEMBER", "ADD_TEAMMEMBER", "ADD_RAIDMEMBER", "ADD_MUTE" }) do
    local dialog = StaticPopupDialogs and StaticPopupDialogs[which]
    if dialog and (dialog.maxLetters or 0) < NAME_LETTERS then
        dialog.maxLetters = NAME_LETTERS
    end
end
if SendMailNameEditBox and SendMailNameEditBox.SetMaxLetters then
    SendMailNameEditBox:SetMaxLetters(NAME_LETTERS)
end
