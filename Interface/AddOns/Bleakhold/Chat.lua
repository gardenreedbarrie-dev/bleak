-- Bleakhold: colour the server's announcement tags in chat ([Raid Legacy], [Server First], [Season],
-- [Queue], [Record]) and let each chat window hide a tag. The server sends these as plain system text
-- that reads fine without the addon; links in the message are left exactly as the server sent them.
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
        ns.Print("usage: /bh chat <legacy|first|season|queue|record> <on|off> [chat window number]")
        return
    end
    local n = tonumber(win) or 1
    Chat.SetHidden("ChatFrame" .. n, def.key, state == "off")
    ns.Print(string.format("[%s] %s in chat window %d", def.tag, state == "off" and "hidden" or "shown", n))
end)
