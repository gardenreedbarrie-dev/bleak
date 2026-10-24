-- Bleakhold: colour the server's announcement tags in chat ([Raid Legacy], [Server First], [Season],
-- [Queue], [Record], [Case]) and let each chat window hide a tag. The server sends these as plain system text
-- that reads fine without the addon; links in the message are left exactly as the server sent them.
-- Also /w2 for whispers to two-word character names (the server's mod-two-names), quoted names in /w,
-- two-word names in /friend and name boxes long enough for them.
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
        ns.Print("usage: /bh chat <legacy|first|season|queue|record|case|royale> <on|off> [chat window number]")
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
-- /w "Arthas Menethil" hi. The first time a /w takes a one-word target, a hint names the quoted form and /w2.
local stockExtractTellTarget = ChatEdit_ExtractTellTarget

local function hintTwoNames()
    local options = ns.db and ns.db.options
    if not options or options.hintTwoNameWhisper then
        return
    end
    options.hintTwoNameWhisper = true
    ns.Print('two-word names: /w "First Last" message, or /w2 First Last message')
end

function Chat.ExtractTellTarget(editBox, msg)
    msg = msg or ""
    local name, rest = msg:match('^%s*"([^"]+)"%s(.*)$')
    name = name and name:match("^%s*(.-)%s*$")
    if name and name ~= "" then
        editBox:SetAttribute("tellTarget", name)
        editBox:SetAttribute("chatType", "WHISPER")
        editBox:SetText(rest)
        ChatEdit_UpdateHeader(editBox)
        return true
    end
    if msg:match('^%s*"') then
        return false    -- the quoted name is still being typed
    end
    local taken = stockExtractTellTarget and stockExtractTellTarget(editBox, msg)
    if taken and not (editBox:GetAttribute("tellTarget") or ""):find(" ", 1, true) then
        hintTwoNames()
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
