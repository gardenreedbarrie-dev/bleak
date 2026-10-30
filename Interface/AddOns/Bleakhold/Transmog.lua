-- Bleakhold: Transmog tab of the Collections window, for mod-transmog-plus (the realm's transmog module).
-- The player's model between the transmog slots, the looks the selected slot can take as 3D tiles (search,
-- pages, the looks not collected yet), the price and Apply, outfits saved for the account and weapon
-- illusions. It speaks the module's own addon protocol: self-whispers with the prefix "transmog" (requests
-- such as GetAvailableTransmogs:grouped, Apply:<slot>:<item>, CalculateCost, GetMissing; answers such as
-- AvailableTransmogs, TransmogStatus, ApplyTransmogResult, TransmogCost, MissingLooks). Slots on the wire are
-- the server's equipment slots (0 head ... 18 tabard); outfits use the 1-based inventory slots.
-- The transmogrifier NPC ("Open") and /transmog ("Portable", when the realm allows it anywhere) open the
-- tab; browsing it works anywhere, and Apply asks the realm first when neither did. Mod-bleakhold's
-- Bleakhold Coins (BHMOG: "B?" asks for the balance) unlock a look not collected yet with .mog unlock <item>.
-- When the module's own Transmog addon is installed too, that addon answers the NPC and /transmog.
local ADDON, ns = ...
local U, UI = ns.U, ns.UI
local C = UI.C
local CO = ns.Collections

local floor, max, min = math.floor, math.max, math.min
local tonumber, tostring, pairs, ipairs, type = tonumber, tostring, pairs, ipairs, type
local strfind, strsub, strlower = string.find, string.sub, string.lower
local strmatch, strformat = string.match, string.format

local TM = {}
ns.Transmog = TM

TM.PREFIX = "transmog"
TM.COIN_PREFIX = "BHMOG"
TM.HIDDEN = 999999            -- the module's HIDDEN_ITEM_ID and HIDDEN_ILLUSION_ID
TM.COLS, TM.ROWS = 6, 3
TM.PAGE_SIZE = TM.COLS * TM.ROWS
TM.MAX_LOOKS = 5000           -- looks kept per slot
TM.MAX_SOURCES = 60           -- items kept per look
TM.MAX_MISSING = 1200         -- the module sends at most this many missing looks
TM.MAX_OUTFITS = 60
TM.MAX_ILLUSIONS = 400
TM.OUTFIT_NAME = 48
TM.QUERY = 40
TM.WAIT = 6                   -- seconds without any answer before the tab says the realm has no module
TM.APPLY_TIMEOUT = 10
TM.UPSTREAM = "Transmog"      -- mod-transmog-plus's own addon
TM.MYTHIC_FIRST, TM.MYTHIC_LAST = 951000, 958620   -- looks only Mythic+ gives (bh_transmog.cpp)

-- The transmog slots in the order of the window: the left column, the right column, the weapons.
-- inv is the inventory slot (GetInventoryItemID); the module's slot is inv - 1.
TM.SLOTS = {
    { inv = 1, key = "HeadSlot", name = "Head", region = "head", col = "left" },
    { inv = 3, key = "ShoulderSlot", name = "Shoulders", region = "shoulder", col = "left" },
    { inv = 15, key = "BackSlot", name = "Back", region = "back", col = "left" },
    { inv = 5, key = "ChestSlot", name = "Chest", region = "chest", col = "left" },
    { inv = 4, key = "ShirtSlot", name = "Shirt", region = "chest", col = "left" },
    { inv = 19, key = "TabardSlot", name = "Tabard", region = "chest", col = "left" },
    { inv = 9, key = "WristSlot", name = "Wrists", region = "wrist", col = "left" },
    { inv = 10, key = "HandsSlot", name = "Hands", region = "hands", col = "right" },
    { inv = 6, key = "WaistSlot", name = "Waist", region = "waist", col = "right" },
    { inv = 7, key = "LegsSlot", name = "Legs", region = "legs", col = "right" },
    { inv = 8, key = "FeetSlot", name = "Feet", region = "feet", col = "right" },
    { inv = 16, key = "MainHandSlot", name = "Main Hand", region = "weapon", col = "weapon", weapon = true },
    { inv = 17, key = "SecondaryHandSlot", name = "Off Hand", region = "weapon", col = "weapon", weapon = true },
    { inv = 18, key = "RangedSlot", name = "Ranged", region = "weapon", col = "weapon", weapon = true },
}
TM.SLOT_BY_INV = {}
for _, s in ipairs(TM.SLOTS) do
    TM.SLOT_BY_INV[s.inv] = s
end
TM.ILLUSION_SLOTS = { 16, 17 }

-- Tile framing per body region: SetPosition's depth (towards the camera), side and height (a positive
-- height shows lower on the body), then the facing. Each race's model brings its own camera, so
-- RACE_FRAMING moves the start; /bh mog camera fine-tunes a region for the player's race and remembers it.
TM.FRAMING = {
    head = { 5.6, 0, -2.1, 0.5 },
    shoulder = { 4.6, 0, -1.6, 0.7 },
    back = { 3.6, 0, -0.9, 3.6 },
    chest = { 3.6, 0, -0.8, 0.5 },
    wrist = { 4.6, 0.3, -0.5, 1.3 },
    hands = { 4.6, 0.3, -0.3, 1.3 },
    waist = { 4.6, 0, -0.3, 0.5 },
    legs = { 3.6, 0, 0.8, 0.5 },
    feet = { 4.6, 0, 1.5, 0.5 },
    weapon = { 1.8, 0, 0, 0.9 },
}
TM.RACE_FRAMING = {
    nightelf = { 2.5, 0, 0 }, gnome = { -3, 0, 1.4 }, dwarf = { -1, 0, 0.9 }, troll = { 2, 0, 0 },
    goblin = { -0.5, 0, 0.6 }, scourge = { 1.5, 0, 0 }, draenei = { 1.5, 0, 0 }, eredar = { 1.5, 0, 0 },
    tauren = { 0.5, 0, 0 },
}

------------------------------------------------------------------------------------------------------
-- State
------------------------------------------------------------------------------------------------------
TM.slot = 5                 -- the selected slot (inventory slot)
TM.view = "items"           -- "items" or "illusions"
TM.page = 1
TM.missingMode = false
TM.applied = {}             -- [inv] = the look the module shows (HIDDEN: hidden)
TM.pending = {}             -- [inv] = the look to apply (0: back to the real item, HIDDEN: hide)
TM.trying = {}              -- [inv] = a look not collected, tried on the model only
TM.looks = {}               -- [inv] = { { lead = item, sources = { item, ... } }, ... }
TM.loaded = {}              -- [inv] = true once the slot's list arrived
TM.illusionNames = {}
TM.illusions = {}           -- collected illusions: { { id = enchant, name = text }, ... }
TM.illusionApplied = {}     -- [16|17] = enchant
TM.illusionPending = {}
TM.illusionSlot = 16
TM.outfits = {}             -- { { name = text, data = "inv,item;..." }, ... }
TM.sources = {}             -- [item] = { { id = item, collected = bool }, ... } (GetSources)
TM.cost, TM.canPay = 0, true
TM.coins = nil              -- Bleakhold Coins (BHMOG), nil until mod-bleakhold sent the balance
TM.prices = nil             -- { normal, epic, special }
TM.heard = false            -- any answer from the module this session
TM.canApply = false         -- the NPC or /transmog opened the tab
TM.echoed = false           -- our own requests came back: the realm runs no transmog module
-- GetMissing answers carry our number back; the module's own addon counts from 1, so start far from it
TM.missingSeq = 100000 + floor((GetTime() * 1000) % 100000)

local loading = {}          -- [inv] = the list being received
local loadingSources = {}
local loadingOutfits, loadingIllusions
local frame                 -- the tab, built on first show

local function split(s, sep)
    local out, pos = {}, 1
    while true do
        local a = strfind(s, sep, pos, true)
        if not a then
            out[#out + 1] = strsub(s, pos)
            return out
        end
        out[#out + 1] = strsub(s, pos, a - 1)
        pos = a + 1
    end
end

-- A positive id from the wire, or nil.
local function id(raw)
    if type(raw) ~= "string" or not strfind(raw, "^%d+$") or #raw > 9 then
        return nil
    end
    return tonumber(raw)
end

-- Our own requests: the server echoes a self-whisper nobody consumed, so seeing one means no module.
local REQUESTS = {
    GetTransmogStatus = true, GetCollectionStatus = true, GetAvailableTransmogs = true, Apply = true, Remove = true,
    RemoveAll = true, CalculateCost = true, RequestPortable = true, GetSources = true, GetMissing = true,
    GetOutfits = true, SaveOutfit = true, DeleteOutfit = true, GetIllusions = true, ApplyIllusion = true,
}

local function isSelf(sender)
    local me = ns.PlayerName()
    if type(sender) ~= "string" or not me then
        return false
    end
    return (strmatch(sender, "^([^%-]+)") or sender) == me
end

function TM.Upstream()
    return IsAddOnLoaded and IsAddOnLoaded(TM.UPSTREAM) and true or false
end

local function whisper(prefix, msg)
    local me = ns.PlayerName()
    if not me or not SendAddonMessage then
        return false
    end
    SendAddonMessage(prefix, msg, "WHISPER", me)
    return true
end

function TM.Send(msg)
    return whisper(TM.PREFIX, msg)
end

-- mod-bleakhold sends the coin balance at login; this asks again (after /reload).
function TM.AskCoins()
    TM.coinsAsked = true
    return whisper(TM.COIN_PREFIX, "B?")
end

function TM.Shown()
    return frame and frame:IsVisible() and true or false
end

local function refreshSoon()
    if TM.Shown() then
        TM.Refresh()
    end
end

------------------------------------------------------------------------------------------------------
-- Money and prices
------------------------------------------------------------------------------------------------------
function TM.Money(copper)
    copper = floor(tonumber(copper) or 0)
    local g, s, c = floor(copper / 10000), floor(copper / 100) % 100, copper % 100
    local parts = {}
    if g > 0 then
        parts[#parts + 1] = U.Commas(g) .. "|cffffd700g|r"
    end
    if s > 0 then
        parts[#parts + 1] = s .. "|cffc7c7cfs|r"
    end
    if c > 0 or #parts == 0 then
        parts[#parts + 1] = c .. "|cffeda55fc|r"
    end
    return table.concat(parts, " ")
end

-- Bleakhold Coins to unlock this look: nil when mod-bleakhold is not there, false for Mythic+ looks,
-- "?" while the item's quality is not known yet.
function TM.UnlockPrice(item)
    if not TM.prices or not item then
        return nil
    end
    if item >= TM.MYTHIC_FIRST and item <= TM.MYTHIC_LAST then
        return false
    end
    if item >= 900000 then
        return TM.prices[3]
    end
    local _, _, quality = GetItemInfo(item)
    if not quality then
        CO.RequestItem(item)
        return "?"
    end
    if quality >= 5 then
        return TM.prices[3]
    elseif quality == 4 then
        return TM.prices[2]
    end
    return TM.prices[1]
end

------------------------------------------------------------------------------------------------------
-- Looks per slot
------------------------------------------------------------------------------------------------------
function TM.RealItem(inv)
    return GetInventoryItemID and GetInventoryItemID("player", inv) or nil
end

-- What the slot shows once the pending changes are applied: an item id, TM.HIDDEN or nil (empty).
function TM.Effective(inv)
    if TM.trying[inv] then
        return TM.trying[inv]
    end
    local v = TM.pending[inv]
    if v == nil then
        v = TM.applied[inv] or 0
    end
    if v == 0 then
        return TM.RealItem(inv)
    end
    return v
end

function TM.EffectiveIllusion(inv)
    local v = TM.illusionPending[inv]
    if v == nil then
        v = TM.illusionApplied[inv] or 0
    end
    return v
end

function TM.Query()
    local q = CO.search or ""
    q = q:gsub(":", " ")
    return strsub(q, 1, TM.QUERY)
end

local function lookMatches(look, q)
    for _, item in ipairs(look.sources) do
        local name = GetItemInfo(item)
        if name and strfind(strlower(name), q, 1, true) then
            return true
        end
    end
    return false
end

-- The tiles of the selected slot: the collected looks (filtered by the search), or the missing ones.
function TM.Tiles()
    local inv = TM.slot
    if TM.missingMode then
        local m = TM.missing
        if m and m.inv == inv and m.query == TM.Query() then
            return m.list, m.done
        end
        return {}, false
    end
    local looks = TM.looks[inv] or {}
    local q = strlower(TM.Query())
    if q == "" then
        return looks, TM.loaded[inv]
    end
    local out, asked = {}, 0
    for _, look in ipairs(looks) do
        if lookMatches(look, q) then
            out[#out + 1] = look
        else
            -- names come from the item cache: ask for the unknown ones, a few hundred per pass
            for _, item in ipairs(look.sources) do
                if asked < 300 and not GetItemInfo(item) then
                    CO.RequestItem(item)
                    asked = asked + 1
                end
            end
        end
    end
    return out, TM.loaded[inv]
end

function TM.Pages()
    local tiles = TM.Tiles()
    return max(1, floor((#tiles + TM.PAGE_SIZE - 1) / TM.PAGE_SIZE))
end

-- The pending changes that differ from what the module shows.
function TM.Changes()
    local list = {}
    for _, s in ipairs(TM.SLOTS) do
        local v = TM.pending[s.inv]
        if v ~= nil and v ~= (TM.applied[s.inv] or 0) then
            list[#list + 1] = { inv = s.inv, item = v }
        end
    end
    for _, inv in ipairs(TM.ILLUSION_SLOTS) do
        local v = TM.illusionPending[inv]
        if v ~= nil and v ~= (TM.illusionApplied[inv] or 0) then
            list[#list + 1] = { inv = inv, illusion = v }
        end
    end
    return list
end

------------------------------------------------------------------------------------------------------
-- Requests
------------------------------------------------------------------------------------------------------
function TM.RequestAll()
    TM.askedAt = GetTime()
    TM.Send("GetTransmogStatus")
    TM.Send("GetAvailableTransmogs:grouped")
    TM.Send("GetOutfits")
    TM.Send("GetIllusions")
    TM.stale = false
end

function TM.RequestCost()
    local parts = {}
    for _, ch in ipairs(TM.Changes()) do
        if ch.illusion then
            parts[#parts + 1] = "i" .. (ch.inv - 1) .. ":" .. ch.illusion
        elseif ch.item > 0 then
            parts[#parts + 1] = (ch.inv - 1) .. ":" .. ch.item
        end
    end
    if #parts == 0 then
        TM.cost, TM.canPay = 0, true
        return
    end
    TM.costPending = true
    TM.Send("CalculateCost:" .. table.concat(parts, ","))
end

local missingTimer
function TM.RequestMissing()
    if missingTimer then
        ns.Cancel(missingTimer)
        missingTimer = nil
    end
    TM.missingSeq = TM.missingSeq + 1
    local q = TM.Query()
    TM.missing = { seq = TM.missingSeq, inv = TM.slot, query = q, list = {}, total = 0, done = false }
    local msg = "GetMissing:" .. TM.missingSeq .. ":" .. (TM.slot - 1)
    if q ~= "" then
        msg = msg .. ":" .. q
    end
    TM.Send(msg)
end

-- The search box changes on every key: ask for missing looks once typing pauses.
local function missingSoon()
    if missingTimer then
        ns.Cancel(missingTimer)
    end
    missingTimer = ns.After(0.4, function()
        missingTimer = nil
        if TM.missingMode and TM.Shown() then
            TM.RequestMissing()
            TM.Refresh()
        end
    end)
end

function TM.RequestSources(item)
    if item and not TM.sources[item] and not loadingSources[item] then
        loadingSources[item] = {}
        TM.Send("GetSources:" .. item)
    end
end

------------------------------------------------------------------------------------------------------
-- Answers from the module
------------------------------------------------------------------------------------------------------
local H = {}
TM.handlers = H

function H.Open()
    -- at the transmogrifier: Apply needs no further say from the realm, whichever addon shows the window
    TM.canApply = true
    if TM.Upstream() then
        return
    end
    if CloseGossip then
        CloseGossip()
    end
    if TM.Shown() then
        TM.Send("GetTransmogStatus")
    end
    TM.Open()
end

function H.Portable()
    local fn = TM.wantAccess
    TM.wantAccess = nil
    local asked = TM.portableAsked and GetTime() - TM.portableAsked < 5
    TM.portableAsked = nil
    if fn then
        TM.canApply = true
        ns.SafeCall(fn)
    elseif asked and not TM.Upstream() then
        TM.canApply = true
        TM.Open()
    end
end

function H.TransmogStatus(rest)
    local f = split(rest, ":")
    TM.applied = {}
    for i = 2, #f do
        local slot, item = strmatch(f[i], "^(%d+),(%d+)$")
        slot, item = id(slot), id(item)
        if slot and item and TM.SLOT_BY_INV[slot + 1] then
            TM.applied[slot + 1] = item
        end
    end
    -- pending entries that now match what is shown are done
    for inv, v in pairs(TM.pending) do
        if v == (TM.applied[inv] or 0) then
            TM.pending[inv] = nil
        end
    end
    refreshSoon()
end

function H.AvailableTransmogs(rest)
    local slot, payload = strmatch(rest, "^(%d+):%d+:%d+:(.*)$")
    slot = id(slot)
    local inv = slot and slot + 1
    if not inv or not TM.SLOT_BY_INV[inv] then
        return
    end
    if payload == "start" then
        loading[inv] = {}
        return
    elseif payload == "end" then
        TM.looks[inv] = loading[inv] or {}
        TM.loaded[inv] = true
        loading[inv] = nil
        if inv == TM.slot then
            refreshSoon()
        end
        return
    end
    local list = loading[inv]
    if not list then
        return
    end
    for _, token in ipairs(split(payload, ":")) do
        local more = strsub(token, 1, 1) == "+"
        if more then
            token = strsub(token, 2)
        end
        local ids = {}
        for _, raw in ipairs(split(token, ",")) do
            local item = id(raw)
            if item and item > 0 then
                ids[#ids + 1] = item
            end
        end
        if more and #list > 0 then
            local sources = list[#list].sources
            for _, item in ipairs(ids) do
                if #sources < TM.MAX_SOURCES then
                    sources[#sources + 1] = item
                end
            end
        elseif not more and #ids > 0 and #list < TM.MAX_LOOKS then
            while #ids > TM.MAX_SOURCES do
                ids[#ids] = nil
            end
            list[#list + 1] = { lead = ids[1], sources = ids }
        end
    end
end

local function applyResult(ok)
    local a = TM.applying
    if not a then
        return
    end
    a.left = a.left - 1
    if not ok then
        a.failed = a.failed + 1
    end
    if a.left <= 0 then
        TM.FinishApply()
    end
end

function H.ApplyTransmogResult(rest)
    local ok, tail = strmatch(rest, "^(%d)(.*)$")
    if ok == "1" then
        local slot, item = strmatch(tail, "^:(%d+),(%d+)$")
        slot, item = id(slot), id(item)
        if slot and item and TM.SLOT_BY_INV[slot + 1] then
            TM.applied[slot + 1] = item > 0 and item or nil
            if TM.pending[slot + 1] == item then
                TM.pending[slot + 1] = nil
            end
        end
    end
    applyResult(ok == "1")
    refreshSoon()
end

function H.ApplyIllusionResult(rest)
    local f = split(rest, ":")
    local slot, enchant = id(f[2]), id(f[3])
    if f[1] == "1" and slot and enchant and (slot == 15 or slot == 16) then
        TM.illusionApplied[slot + 1] = enchant
        if TM.illusionPending[slot + 1] == enchant then
            TM.illusionPending[slot + 1] = nil
        end
    end
    applyResult(f[1] == "1")
    refreshSoon()
end

function H.TransmogCost(rest)
    local f = split(rest, ":")
    TM.cost = id(f[1]) or 0
    TM.canPay = f[2] ~= "0"
    TM.costPending = false
    refreshSoon()
end

-- The price shown is the price of the changes picked: false while a pick is not priced yet.
function TM.CostKnown()
    return not TM.costPending and not TM.costDue
end

function H.Sources(rest)
    local item, payload = strmatch(rest, "^(%d+):(.*)$")
    item = id(item)
    if not item then
        return
    end
    if payload == "start" then
        loadingSources[item] = {}
        return
    end
    local list = loadingSources[item]
    if not list then
        return
    end
    if payload == "end" then
        TM.sources[item] = list
        loadingSources[item] = nil
        if TM.tooltipTile and TM.tooltipTile.look and TM.tooltipTile.look.lead == item then
            TM.TileTooltip(TM.tooltipTile)
        end
        return
    end
    for _, token in ipairs(split(payload, ":")) do
        local source, have = strmatch(token, "^(%d+),([01])$")
        source = id(source)
        if source and #list < TM.MAX_SOURCES then
            list[#list + 1] = { id = source, collected = have == "1" }
        end
    end
end

function H.MissingLooks(rest)
    local seq, total, payload = strmatch(rest, "^(%d+):(%d+):(.*)$")
    local m = TM.missing
    if not m or id(seq) ~= m.seq then
        return  -- an answer to an older search
    end
    m.total = id(total) or 0
    if payload == "start" then
        m.list = {}
    elseif payload == "end" then
        m.done = true
        refreshSoon()
    else
        for _, raw in ipairs(split(payload, ":")) do
            local item = id(raw)
            if item and item > 0 and #m.list < TM.MAX_MISSING then
                m.list[#m.list + 1] = { lead = item, sources = { item }, missing = true }
            end
        end
    end
end

-- Text as the module sends it (raw, not %-escaped): valid UTF-8, no control bytes or '|', cut whole.
local function plain(s, maxLen)
    s = U.CleanUtf8(s or ""):gsub("[%c|]", "")
    return U.CutUtf8(s, maxLen)
end

local function cleanName(s)
    return plain(s, TM.OUTFIT_NAME)
end

function H.Outfits(rest)
    if rest == "start" then
        loadingOutfits = {}
    elseif rest == "end" and loadingOutfits then
        table.sort(loadingOutfits, function(a, b)
            return strlower(a.name) < strlower(b.name)
        end)
        TM.outfits = loadingOutfits
        loadingOutfits = nil
        local known = false
        for _, o in ipairs(TM.outfits) do
            known = known or o.name == TM.outfit
        end
        if not known then
            TM.outfit = nil
        end
        refreshSoon()
    end
end

function H.Outfit(rest)
    local data, name = strmatch(rest, "^([^:]*):(.*)$")
    if not loadingOutfits or not data or #loadingOutfits >= TM.MAX_OUTFITS then
        return
    end
    name = cleanName(name)
    if name ~= "" then
        loadingOutfits[#loadingOutfits + 1] = { name = name, data = data }
    end
end

function H.OutfitRejected()
    ns.Print("You already have " .. 50 .. " outfits: delete one before saving another.")
    TM.status = "The outfit was not saved: you already have 50."
    refreshSoon()
end

function H.Illusions(rest)
    if rest == "start" then
        loadingIllusions = {}
    elseif rest == "end" then
        if loadingIllusions then
            TM.illusions = loadingIllusions
            loadingIllusions = nil
            TM.hasIllusions = true
            refreshSoon()
        end
    elseif loadingIllusions then
        for _, raw in ipairs(split(rest, ":")) do
            local enchant = id(raw)
            if enchant and #loadingIllusions < TM.MAX_ILLUSIONS then
                loadingIllusions[#loadingIllusions + 1] = { id = enchant,
                    name = TM.illusionNames[enchant] or ("Illusion " .. enchant) }
            end
        end
    end
end

function H.IllusionName(rest)
    local enchant, name = strmatch(rest, "^(%d+):(.*)$")
    enchant = id(enchant)
    if enchant then
        name = plain(name, 64)
        TM.illusionNames[enchant] = name ~= "" and name or ("Illusion " .. enchant)
    end
end

function H.IllusionStatus(rest)
    local f = split(rest, ":")
    TM.illusionApplied[16] = id(f[1]) or 0
    TM.illusionApplied[17] = id(f[2]) or 0
    refreshSoon()
end

function H.IllusionCollected()
    if TM.Shown() then
        TM.Send("GetIllusions")
    else
        TM.stale = true
    end
end

local collectedTimer
function H.CollectionUpdated()
    TM.stale = true
    TM.sources = {}
    if collectedTimer or not TM.Shown() then
        return
    end
    collectedTimer = ns.After(2, function()
        collectedTimer = nil
        if TM.Shown() then
            TM.Send("GetAvailableTransmogs:grouped")
            TM.stale = false
        end
    end)
end

function TM.Receive(msg)
    if type(msg) ~= "string" then
        return
    end
    local cmd, rest = strmatch(msg, "^(%a+)(.*)$")
    if not cmd then
        return
    end
    if REQUESTS[cmd] then
        TM.echoed = true   -- our own request came back: nothing on the realm took it
        refreshSoon()
        return
    end
    TM.heard = true
    rest = strsub(rest, 1, 1) == ":" and strsub(rest, 2) or rest
    local fn = H[cmd]
    if fn then
        fn(rest)
    end
end

-- mod-bleakhold: "B;<coins>;<normal>;<epic>;<special>" (the balance) and "U;<item>" (a look unlocked).
function TM.ReceiveCoins(msg)
    local f = split(msg or "", ";")
    if f[1] == "B" then
        TM.coins = id(f[2]) or 0
        TM.prices = { id(f[3]) or 1, id(f[4]) or 3, id(f[5]) or 5 }
        refreshSoon()
    elseif f[1] == "U" then
        local item = id(f[2])
        if item and TM.missing then
            for i, look in ipairs(TM.missing.list) do
                if look.lead == item then
                    table.remove(TM.missing.list, i)
                    TM.missing.total = max(0, TM.missing.total - 1)
                    break
                end
            end
        end
        TM.sources = {}
        for inv, v in pairs(TM.trying) do
            if v == item then
                TM.trying[inv] = nil
                TM.pending[inv] = item
            end
        end
        TM.selectedMissing = nil
        TM.stale = true
        if TM.Shown() then
            TM.Send("GetAvailableTransmogs:grouped")
            TM.RequestCost()
        end
        refreshSoon()
    end
end

ns.RegisterEvent("CHAT_MSG_ADDON", function(event, prefix, msg, channel, sender)
    if prefix ~= TM.PREFIX and prefix ~= TM.COIN_PREFIX then
        return
    end
    if channel ~= "WHISPER" or not isSelf(sender) then
        return
    end
    if prefix == TM.PREFIX then
        TM.Receive(msg)
    else
        TM.ReceiveCoins(msg)
    end
end)

------------------------------------------------------------------------------------------------------
-- Changing the look
------------------------------------------------------------------------------------------------------
local costTimer
local function changed()
    if costTimer then
        ns.Cancel(costTimer)
    end
    TM.costDue = true
    costTimer = ns.After(0.3, function()
        costTimer = nil
        TM.costDue = false
        TM.RequestCost()
        refreshSoon()
    end)
    refreshSoon()
end

-- Pick a collected look for a slot (nil: undo the slot's change).
function TM.SetPending(inv, item)
    if not TM.SLOT_BY_INV[inv] then
        return
    end
    TM.trying[inv] = nil
    if item ~= nil and item == (TM.applied[inv] or 0) then
        item = nil
    end
    TM.pending[inv] = item
    changed()
end

function TM.SetIllusion(inv, enchant)
    if enchant ~= nil and enchant == (TM.illusionApplied[inv] or 0) then
        enchant = nil
    end
    TM.illusionPending[inv] = enchant
    changed()
end

function TM.Undo()
    TM.pending, TM.illusionPending, TM.trying = {}, {}, {}
    TM.selectedMissing = nil
    changed()
end

-- Runs fn now when the NPC or /transmog opened the tab, else once the realm agrees (Portable).
function TM.WithAccess(fn)
    if TM.canApply then
        fn()
        return
    end
    TM.wantAccess = fn
    TM.Send("RequestPortable")
    ns.After(4, function()
        if TM.wantAccess == fn then
            TM.wantAccess = nil
            TM.status = "Visit a transmogrifier to change your look."
            refreshSoon()
        end
    end)
end

local function sendChanges(list)
    if #list == 0 or TM.applying then
        return
    end
    TM.applying = { left = #list, failed = 0, total = #list }
    TM.applying.timer = ns.After(TM.APPLY_TIMEOUT, function()
        if TM.applying then
            TM.FinishApply()
        end
    end)
    for _, ch in ipairs(list) do
        if ch.illusion then
            TM.Send("ApplyIllusion:" .. (ch.inv - 1) .. ":" .. ch.illusion)
        elseif ch.item == 0 then
            TM.Send("Remove:" .. (ch.inv - 1))
        else
            TM.Send("Apply:" .. (ch.inv - 1) .. ":" .. ch.item)
        end
    end
    refreshSoon()
end

-- The changes, as long as they are still the ones priced and confirmed: what a late Accept may send.
local function changesKey()
    local parts = {}
    for _, ch in ipairs(TM.Changes()) do
        parts[#parts + 1] = (ch.illusion and "i" or "") .. ch.inv .. ":" .. (ch.illusion or ch.item)
    end
    return table.concat(parts, ",")
end

function TM.Apply()
    local list = TM.Changes()
    if #list == 0 or TM.applying or not TM.CostKnown() then
        return false
    end
    TM.WithAccess(function()
        list = TM.Changes()
        if #list == 0 or TM.applying or not TM.CostKnown() then
            return
        end
        if not TM.canPay then
            TM.status = "You need " .. TM.Money(TM.cost) .. " for these changes."
            refreshSoon()
            return
        end
        if TM.cost > 0 then
            local key, cost = changesKey(), TM.cost
            UI.Confirm(strformat("Change %d %s for %s?", #list, #list == 1 and "slot" or "slots", TM.Money(TM.cost)),
                function()
                    -- only what was priced, while the tab is still open
                    if TM.Shown() and TM.canApply and changesKey() == key and TM.cost == cost and TM.CostKnown() then
                        sendChanges(TM.Changes())
                    end
                end, "Apply")
        else
            sendChanges(list)
        end
    end)
    return true
end

function TM.FinishApply()
    local a = TM.applying
    TM.applying = nil
    if not a then
        return
    end
    ns.Cancel(a.timer)
    if a.left > 0 then
        TM.status = "The realm did not answer every change."
    elseif a.failed > 0 then
        TM.status = strformat("%d of %d changes could not be made (gold, or the look no longer fits the item).",
            a.failed, a.total)
    else
        TM.status = "Your new look is on."
    end
    TM.pending, TM.illusionPending, TM.trying = {}, {}, {}
    TM.cost, TM.canPay = 0, true
    TM.Send("GetTransmogStatus")
    refreshSoon()
end

function TM.StripAll()
    if TM.applying then
        return
    end
    TM.WithAccess(function()
        UI.Confirm("Take every transmog and illusion off your character? It is free.", function()
            if TM.applying or not TM.Shown() then
                return
            end
            TM.Send("RemoveAll")
            for _, inv in ipairs(TM.ILLUSION_SLOTS) do
                if (TM.illusionApplied[inv] or 0) ~= 0 then
                    TM.Send("ApplyIllusion:" .. (inv - 1) .. ":0")
                end
            end
            TM.pending, TM.illusionPending, TM.trying = {}, {}, {}
            TM.cost, TM.canPay = 0, true
            TM.status = "Every transmog is off."
            refreshSoon()
        end, "Take off")
    end)
end

------------------------------------------------------------------------------------------------------
-- Outfits
------------------------------------------------------------------------------------------------------
function TM.OutfitData()
    local parts = {}
    for _, s in ipairs(TM.SLOTS) do
        local v = TM.pending[s.inv]
        if v == nil then
            v = TM.applied[s.inv] or 0
        end
        if v > 0 then
            parts[#parts + 1] = s.inv .. "," .. v
        end
    end
    return table.concat(parts, ";")
end

function TM.LoadOutfit(name)
    for _, o in ipairs(TM.outfits) do
        if o.name == name then
            local looks = {}
            for _, pair in ipairs(split(o.data, ";")) do
                local inv, item = strmatch(pair, "^(%d+),(%d+)$")
                inv, item = id(inv), id(item)
                if inv and item and TM.SLOT_BY_INV[inv] then
                    looks[inv] = item
                end
            end
            TM.trying = {}
            for _, s in ipairs(TM.SLOTS) do
                local v = looks[s.inv] or 0
                -- nothing equipped: nothing to show a look on
                if not TM.RealItem(s.inv) then
                    v = TM.applied[s.inv] or 0
                end
                TM.pending[s.inv] = v ~= (TM.applied[s.inv] or 0) and v or nil
            end
            TM.outfit = name
            changed()
            return true
        end
    end
    return false
end

function TM.SaveOutfit()
    local data = TM.OutfitData()
    if data == "" then
        TM.status = "Pick some looks before saving an outfit."
        refreshSoon()
        return
    end
    UI.Prompt("Name this outfit. Every character on your account can wear it.", TM.outfit or "", function(name)
        name = cleanName(name)
        if name == "" then
            return
        end
        TM.Send("SaveOutfit:" .. TM.OutfitData() .. ":" .. name)
        TM.outfit = name
        TM.status = "Outfit \"" .. name .. "\" saved."
        ns.After(0.5, function()
            TM.Send("GetOutfits")
        end)
        refreshSoon()
    end, "Save", TM.OUTFIT_NAME)
end

function TM.DeleteOutfit(name)
    if not name then
        return
    end
    UI.Confirm("Delete the outfit \"" .. name .. "\"?", function()
        TM.Send("DeleteOutfit:" .. name)
        if TM.outfit == name then
            TM.outfit = nil
        end
        ns.After(0.5, function()
            TM.Send("GetOutfits")
        end)
        refreshSoon()
    end, "Delete")
end

------------------------------------------------------------------------------------------------------
-- Unlocking with Bleakhold Coins
------------------------------------------------------------------------------------------------------
function TM.Unlock(item)
    local price = TM.UnlockPrice(item)
    if not price or price == "?" then
        return false
    end
    local name = GetItemInfo(item) or ("item " .. item)
    UI.Confirm(strformat("Unlock the look of %s for your account for %d Bleakhold Coins?", name, price), function()
        SendChatMessage(".mog unlock " .. item, "SAY")
    end, "Unlock")
    return true
end

------------------------------------------------------------------------------------------------------
-- The tab
------------------------------------------------------------------------------------------------------
local BW, BH = CO.BW, CO.BH
local PAD = 12                -- inside the tab's panel
local LEFT_W = 300
local RIGHT_X = PAD + LEFT_W + 14
local RIGHT_W = BW - RIGHT_X - PAD - 2
local TILE_GAP = 4
-- the tiles fill the right column: six across, three down above the page arrows
local TILE_W = floor((RIGHT_W + TILE_GAP) / TM.COLS) - TILE_GAP
local TILE_H = floor((BH - 2 * PAD - 34 - 32 - 38 + TILE_GAP) / TM.ROWS) - TILE_GAP
local SLOT_SIZE, SLOT_GAP = 36, 44
local WEAPON_Y = 96           -- the weapons' row, from the bottom of the left box
local ILL_ROW = 18            -- an illusion's row (UIDropDownMenu's rows are 16)
local PASS_MARK = "Interface\\Buttons\\UI-GroupLoot-Pass-Up"
local LOCK_MARK = "Interface\\LFGFrame\\UI-LFG-ICON-LOCK"
local COIN_ICON = "INV_Misc_Coin_02"

local function hideTooltip()
    if GameTooltip then
        GameTooltip:Hide()
    end
    TM.tooltipTile = nil
end

function TM.Race()
    local _, file = UnitRace("player")
    return strlower(file or "")
end

function TM.Framing(region)
    local f = TM.FRAMING[region] or TM.FRAMING.chest
    local race = TM.Race()
    local r = TM.RACE_FRAMING[race] or { 0, 0, 0 }
    local nudge = ns.db.mogCamera and ns.db.mogCamera[race .. ":" .. region] or nil
    local n = type(nudge) == "table" and nudge or { 0, 0, 0 }
    return f[1] + r[1] + (tonumber(n[1]) or 0), f[2] + r[2] + (tonumber(n[2]) or 0),
        f[3] + r[3] + (tonumber(n[3]) or 0), f[4]
end

-- Dresses the big model in the look being built; only when that look changed, so refreshes do not reset the
-- model (or the way the player turned it).
local function dressModel(model)
    local looks, key = {}, {}
    for _, s in ipairs(TM.SLOTS) do
        local item = TM.Effective(s.inv)
        if item and item ~= TM.HIDDEN then
            local ench = s.weapon and TM.EffectiveIllusion(s.inv) or 0
            local look = (ench > 0 and ench ~= TM.HIDDEN) and ("item:" .. item .. ":" .. ench) or item
            looks[#looks + 1] = look
            key[#key + 1] = tostring(look)
        end
    end
    key = table.concat(key, ";")
    if model.dressed == key then
        return
    end
    model.dressed = key
    local facing = model:GetFacing() or 0
    model:SetUnit("player")
    model:SetFacing(facing)
    model:Undress()
    for _, look in ipairs(looks) do
        model:TryOn(look)
    end
end

local function build()
    local body = CO.body
    frame = CreateFrame("Frame", nil, body)
    frame:SetAllPoints(body)
    frame:Hide()
    TM.frame = frame

    -- Left: outfits, the model between the slots (the character frame's paper doll), the price and Apply, in a dark
    -- row box (the old window's rows) inside the tab's panel.
    local left = UI.Box(frame, LEFT_W, BH - 2 * PAD, C.card, C.border, nil, "edge")
    left:SetPoint("TOPLEFT", frame, "TOPLEFT", PAD, -PAD)
    frame.left = left

    -- the equipment manager's row: the outfit list, Save and Delete (GearManagerDialog's red buttons)
    frame.outfit = UI.Dropdown(left, 150, function(value)
        if value and value ~= "" then
            TM.LoadOutfit(value)
        end
    end)
    frame.outfit:SetPoint("TOPLEFT", left, "TOPLEFT", 6, -10)
    frame.save = UI.Button(left, 58, 22, "Save", "dark")
    frame.save:SetPoint("LEFT", frame.outfit, "RIGHT", 4, 0)
    frame.save:SetScript("OnClick", function()
        TM.SaveOutfit()
    end)
    frame.delete = UI.Button(left, 62, 22, "Delete", "dark")
    frame.delete:SetPoint("LEFT", frame.save, "RIGHT", 4, 0)
    frame.delete.tooltip = function()
        return { "Delete outfit", "Deletes the outfit picked in the list." }
    end
    frame.delete:SetScript("OnClick", function()
        TM.DeleteOutfit(TM.outfit)
    end)

    local model = CreateFrame("DressUpModel", nil, left)
    model:SetPoint("TOPLEFT", left, "TOPLEFT", 54, -46)
    model:SetPoint("BOTTOMRIGHT", left, "BOTTOMRIGHT", -54, WEAPON_Y + SLOT_SIZE + 6)
    model:EnableMouse(true)
    model:SetScript("OnMouseDown", function(self)
        self.dragX = GetCursorPosition()
    end)
    model:SetScript("OnMouseUp", function(self)
        self.dragX = nil
    end)
    model:SetScript("OnUpdate", function(self)
        if self.dragX then
            local x = GetCursorPosition()
            self:SetFacing((self:GetFacing() or 0) + (x - self.dragX) * 0.02)
            self.dragX = x
        end
    end)
    frame.model = model

    -- The slots: item buttons (ItemButtonTemplate's art: the item's icon, or the paper doll's empty slot, in
    -- UI-Quickslot2), the open one checked (CheckButtonHilight), a change not applied yet marked with the green
    -- indicator ball, a hidden slot with the group loot's pass mark.
    frame.slots = {}
    local leftN, rightN, weaponN = 0, 0, 0
    local weapons = 0
    for _, s in ipairs(TM.SLOTS) do
        weapons = weapons + (s.col == "weapon" and 1 or 0)
    end
    for _, s in ipairs(TM.SLOTS) do
        local b = CreateFrame("Button", nil, left)
        b:SetSize(SLOT_SIZE, SLOT_SIZE)
        if s.col == "left" then
            b:SetPoint("TOPLEFT", left, "TOPLEFT", 10, -48 - leftN * SLOT_GAP)
            leftN = leftN + 1
        elseif s.col == "right" then
            b:SetPoint("TOPRIGHT", left, "TOPRIGHT", -10, -48 - rightN * SLOT_GAP)
            rightN = rightN + 1
        else
            b:SetPoint("BOTTOMLEFT", left, "BOTTOMLEFT",
                floor(LEFT_W / 2 - (weapons * SLOT_GAP - (SLOT_GAP - SLOT_SIZE)) / 2) + weaponN * SLOT_GAP, WEAPON_Y)
            weaponN = weaponN + 1
        end
        UI.SlotArt(b, SLOT_SIZE)
        b.icon:SetAllPoints(b)
        b.hidden = b:CreateTexture(nil, "OVERLAY")
        b.hidden:SetTexture(PASS_MARK)
        b.hidden:SetSize(24, 24)
        b.hidden:SetPoint("CENTER")
        -- on a child frame: the slot border (UI-Quickslot2) is OVERLAY too, and one layer is not drawn in order
        b.dot = UI.StatusDot(UI.Marks(b), 14, "green", "OVERLAY")
        b.dot:SetPoint("TOPRIGHT", b, "TOPRIGHT", 4, 4)
        b.slot = s
        b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
        b:SetScript("OnClick", function(self, button)
            if button == "RightButton" then
                -- back to the real item, or undo the slot's change
                if TM.pending[s.inv] ~= nil or TM.trying[s.inv] then
                    TM.SetPending(s.inv, nil)
                elseif (TM.applied[s.inv] or 0) ~= 0 then
                    TM.SetPending(s.inv, 0)
                end
            else
                TM.SelectSlot(s.inv)
            end
        end)
        b:SetScript("OnEnter", function(self)
            local lines = { s.name }
            local real = TM.RealItem(s.inv)
            local v = TM.Effective(s.inv)
            if not real then
                lines[#lines + 1] = { "Nothing equipped here.", C.dim }
            elseif v == TM.HIDDEN then
                lines[#lines + 1] = { "Hidden", C.red }
            elseif v and v ~= real then
                lines[#lines + 1] = { "Looks like: " .. (GetItemInfo(v) or ("item " .. v)), C.gold }
            end
            if TM.pending[s.inv] ~= nil then
                lines[#lines + 1] = { "Changed: Apply to keep it.", C.teal }
            end
            lines[#lines + 1] = { "Click: its looks. Right-click: back to the real item.", C.mute, true }
            UI.ShowTooltip(self, lines)
        end)
        b:SetScript("OnLeave", hideTooltip)
        frame.slots[s.inv] = b
    end

    -- Price and Apply: the status and the cost above a row of red buttons (Undo and Remove All are the small ones).
    frame.status = UI.Text(left, 11, C.dim, "body", "CENTER")
    frame.status:SetPoint("BOTTOMLEFT", left, "BOTTOMLEFT", 10, 64)
    frame.status:SetPoint("BOTTOMRIGHT", left, "BOTTOMRIGHT", -10, 64)
    frame.cost = UI.Text(left, 12, C.text)
    frame.cost:SetPoint("BOTTOMLEFT", left, "BOTTOMLEFT", 10, 42)
    frame.undo = UI.Button(left, 60, 22, "Undo", "ghost")
    frame.undo:SetPoint("BOTTOMLEFT", left, "BOTTOMLEFT", 8, 10)
    frame.undo.tooltip = function()
        return { "Undo", "Drops every change you have not applied." }
    end
    frame.undo:SetScript("OnClick", function()
        TM.Undo()
    end)
    frame.strip = UI.Button(left, 92, 22, "Remove All", "ghost")
    frame.strip:SetPoint("LEFT", frame.undo, "RIGHT", 4, 0)
    frame.strip.tooltip = function()
        return { "Take everything off", "Removes every transmog and illusion. It is free." }
    end
    frame.strip:SetScript("OnClick", function()
        TM.StripAll()
    end)
    frame.apply = UI.Button(left, 100, 22, "Apply", "gold")
    frame.apply:SetPoint("BOTTOMRIGHT", left, "BOTTOMRIGHT", -8, 10)
    frame.apply:SetScript("OnClick", function()
        TM.Apply()
    end)

    -- Right: Items / Illusions (red buttons, the open one held down), the balance and the count.
    local right = CreateFrame("Frame", nil, frame)
    right:SetPoint("TOPLEFT", frame, "TOPLEFT", RIGHT_X, -PAD)
    right:SetSize(RIGHT_W, BH - 2 * PAD)
    frame.right = right

    frame.itemsTab = UI.Button(right, 90, 22, "Items", "tab")
    frame.itemsTab:SetPoint("TOPLEFT", right, "TOPLEFT", 0, -2)
    frame.itemsTab:SetScript("OnClick", function()
        TM.view = "items"
        TM.Refresh()
    end)
    frame.illusionsTab = UI.Button(right, 90, 22, "Illusions", "tab")
    frame.illusionsTab:SetPoint("LEFT", frame.itemsTab, "RIGHT", 4, 0)
    frame.illusionsTab:SetScript("OnClick", function()
        TM.view = "illusions"
        TM.Refresh()
    end)
    -- the Bleakhold Coins balance: its coin and the amount, as the money frame writes a sum
    frame.coins = UI.Pill(right, "", C.text, 12)
    frame.coins:SetPoint("TOPRIGHT", right, "TOPRIGHT", 0, -6)
    frame.coins.icon = UI.Icon(frame.coins, 14, COIN_ICON)
    frame.coins.icon:SetPoint("RIGHT", frame.coins, "LEFT", -4, 0)
    frame.coins.tooltip = function()
        local p = TM.prices or { 1, 3, 5 }
        return { "Bleakhold Coins", strformat("Unlock a look you have not collected: %d (uncommon or rare), %d (epic), "
            .. "%d (legendary or Bleakhold).", p[1], p[2], p[3]) }
    end
    frame.collected = UI.LabelValue(right, "Collected", "", 12)
    frame.collected:SetJustifyH("RIGHT")
    frame.collected:SetPoint("TOPRIGHT", right, "TOPRIGHT", -150, -7)

    -- Items view
    local items = CreateFrame("Frame", nil, right)
    items:SetPoint("TOPLEFT", right, "TOPLEFT", 0, -34)
    items:SetPoint("BOTTOMRIGHT", right, "BOTTOMRIGHT", 0, 0)
    frame.items = items
    frame.slotName = UI.Heading(items, nil, 16)
    frame.slotName:SetPoint("TOPLEFT", items, "TOPLEFT", 0, -6)
    frame.count = UI.Text(items, 12, C.dim)
    frame.count:SetPoint("LEFT", frame.slotName, "RIGHT", 10, -1)
    frame.hide = UI.Button(items, 70, 22, "Hide", "dark")
    frame.hide:SetPoint("TOPRIGHT", items, "TOPRIGHT", 0, -2)
    frame.hide.tooltip = function()
        return { "Hide this slot", "Shows nothing in this slot. It is free." }
    end
    frame.hide:SetScript("OnClick", function()
        TM.SetPending(TM.slot, TM.HIDDEN)
    end)
    frame.missing = UI.Button(items, 116, 22, "Not Collected", "tab")
    frame.missing:SetPoint("RIGHT", frame.hide, "LEFT", -4, 0)
    frame.missing.tooltip = function()
        return { "Not collected", "The looks this item could take that your account has not collected yet. "
            .. "Click one to try it on." }
    end
    frame.missing:SetScript("OnClick", function()
        TM.SetMissingMode(not TM.missingMode)
    end)

    -- The tiles: the look on the player's model in a dark row box. Chosen: the nav row's blue (UI.Select); on now:
    -- the check; under the cursor: the row highlight; not collected: shaded, with the LFG lock and its price.
    frame.tiles = {}
    for i = 1, TM.PAGE_SIZE do
        local t = CreateFrame("Button", nil, items)
        t:SetSize(TILE_W, TILE_H)
        local col, row = (i - 1) % TM.COLS, floor((i - 1) / TM.COLS)
        t:SetPoint("TOPLEFT", items, "TOPLEFT", col * (TILE_W + TILE_GAP), -32 - row * (TILE_H + TILE_GAP))
        UI.Backdrop(t, C.card, C.border, nil, "edge")
        t.model = CreateFrame("DressUpModel", nil, t)
        t.model:SetPoint("TOPLEFT", t, "TOPLEFT", 1, -1)
        t.model:SetPoint("BOTTOMRIGHT", t, "BOTTOMRIGHT", -1, 1)
        -- the shade, marks and price sit on a frame above the model (a model draws over its own regions)
        t.over = CreateFrame("Frame", nil, t)
        t.over:SetAllPoints(t.model)
        t.over:SetFrameLevel(t.model:GetFrameLevel() + 1)
        t.shade = UI.Solid(t.over, C.bg, "BACKGROUND", 0.5)
        t.shade:SetAllPoints(t.over)
        -- under the cursor: the quest log's title highlight, added (as the rows of this window light up)
        t.glow = t.over:CreateTexture(nil, "OVERLAY")
        t.glow:SetTexture(UI.STOCK.rowHighlight)
        t.glow:SetBlendMode("ADD")
        t.glow:SetAllPoints(t.over)
        t.glow:SetAlpha(0.3)
        t.glow:Hide()
        t.lock = t.over:CreateTexture(nil, "OVERLAY")
        t.lock:SetTexture(LOCK_MARK)
        t.lock:SetSize(20, 20)
        t.lock:SetPoint("TOPRIGHT", t, "TOPRIGHT", -3, -3)
        t.check = UI.Check(t.over, 18)
        t.check:SetPoint("TOPLEFT", t, "TOPLEFT", 2, -2)
        t.check:Hide()
        t.price = UI.Text(t.over, 11, C.gold, "body", "CENTER", "OVERLAY")
        t.price:SetPoint("BOTTOM", t, "BOTTOM", 0, 6)
        t:RegisterForClicks("LeftButtonUp", "RightButtonUp")
        t:SetScript("OnClick", function(self, button)
            TM.ClickTile(self, button)
        end)
        t:SetScript("OnEnter", function(self)
            self.hovered = true
            TM.PaintTile(self)
            TM.TileTooltip(self)
        end)
        t:SetScript("OnLeave", function(self)
            self.hovered = false
            TM.PaintTile(self)
            hideTooltip()
        end)
        frame.tiles[i] = t
    end

    frame.empty = UI.Text(items, 13, C.mute, "body", "CENTER")
    frame.empty:SetPoint("TOP", items, "TOP", 0, -150)
    frame.empty:SetWidth(RIGHT_W - 60)

    -- the spellbook's page arrows, "Page 1 / 3" to their left
    frame.prev = UI.PageButton(items, "Prev")
    frame.prev:SetPoint("BOTTOMRIGHT", items, "BOTTOMRIGHT", -34, -2)
    frame.prev:SetScript("OnClick", function()
        TM.page = max(1, TM.page - 1)
        TM.Refresh()
    end)
    frame.next = UI.PageButton(items, "Next")
    frame.next:SetPoint("BOTTOMRIGHT", items, "BOTTOMRIGHT", 0, -2)
    frame.next:SetScript("OnClick", function()
        TM.page = min(TM.Pages(), TM.page + 1)
        TM.Refresh()
    end)
    frame.pageText = UI.Text(items, 12, C.text, "body", "RIGHT")
    frame.pageText:SetPoint("RIGHT", frame.prev, "LEFT", -6, 0)
    frame.unlock = UI.Button(items, 240, 22, "", "gold")
    frame.unlock:SetPoint("BOTTOMLEFT", items, "BOTTOMLEFT", 0, 3)
    frame.unlock:SetScript("OnClick", function()
        if TM.selectedMissing then
            TM.Unlock(TM.selectedMissing)
        end
    end)
    items:EnableMouseWheel(true)
    items:SetScript("OnMouseWheel", function(self, delta)
        TM.page = U.Clamp(TM.page - (delta or 0), 1, TM.Pages())
        TM.Refresh()
    end)

    -- Illusions view: Main Hand / Off Hand (held down when open) over a list of rows, the illusion on the weapon
    -- checked (the dropdown list's look).
    local ill = CreateFrame("Frame", nil, right)
    ill:SetPoint("TOPLEFT", right, "TOPLEFT", 0, -34)
    ill:SetPoint("BOTTOMRIGHT", right, "BOTTOMRIGHT", 0, 0)
    frame.ill = ill
    frame.mainHand = UI.Button(ill, 110, 22, "Main Hand", "tab")
    frame.mainHand:SetPoint("TOPLEFT", ill, "TOPLEFT", 0, -4)
    frame.mainHand:SetScript("OnClick", function()
        TM.illusionSlot = 16
        TM.Refresh()
    end)
    frame.offHand = UI.Button(ill, 110, 22, "Off Hand", "tab")
    frame.offHand:SetPoint("LEFT", frame.mainHand, "RIGHT", 4, 0)
    frame.offHand:SetScript("OnClick", function()
        TM.illusionSlot = 17
        TM.Refresh()
    end)
    -- the list shows whole rows (UI.Scroll's SetStep), with a line under it kept for the note (frame.illEmpty)
    local listRows = floor((BH - 2 * PAD - 34 - 36 - 34 - 12) / ILL_ROW)
    local listBox = UI.Box(ill, RIGHT_W, listRows * ILL_ROW + 12, C.card, C.border, nil, "edge")
    listBox:SetPoint("TOPLEFT", ill, "TOPLEFT", 0, -36)
    frame.illScroll = UI.Scroll(listBox)
    frame.illScroll:SetPoint("TOPLEFT", listBox, "TOPLEFT", 6, -6)
    frame.illScroll:SetPoint("BOTTOMRIGHT", listBox, "BOTTOMRIGHT", -4, 6)
    frame.illScroll:SetStep(ILL_ROW)
    frame.illRows = UI.Pool(function()
        local r = UI.Button(frame.illScroll.child, RIGHT_W - 34, ILL_ROW, "", "row", 12)
        r.label:ClearAllPoints()
        r.label:SetPoint("LEFT", r, "LEFT", 22, 0)
        r.label:SetPoint("RIGHT", r, "RIGHT", -4, 0)
        r.label:SetJustifyH("LEFT")
        return r
    end)
    frame.illEmpty = UI.Text(ill, 12, C.dim, "body", "CENTER")
    frame.illEmpty:SetPoint("TOP", listBox, "BOTTOM", 0, -10)
    frame.illEmpty:SetWidth(RIGHT_W - 20)
end

------------------------------------------------------------------------------------------------------
-- Tiles
------------------------------------------------------------------------------------------------------
-- The tile's look is the slot's current or chosen look: the check for what is on now, the blue for the choice.
function TM.TileState(look)
    local inv = TM.slot
    local chosen = TM.trying[inv] or TM.pending[inv]
    local on = TM.applied[inv]
    local isChosen, isOn = false, false
    for _, item in ipairs(look.sources) do
        if chosen and item == chosen then
            isChosen = true
        end
        if on and item == on then
            isOn = true
        end
    end
    return isChosen, isOn
end

function TM.PaintTile(t)
    local look = t.look
    if not look then
        return
    end
    local chosen, on = TM.TileState(look)
    UI.Select(t, chosen)
    if t.selectArt then
        -- the edge over the model, the gradient behind it (a model has no background of its own)
        t.selectArt.edge:SetFrameLevel(t.over:GetFrameLevel() + 1)
    end
    if on then
        t.check:Show()
    else
        t.check:Hide()
    end
    if t.hovered then
        t.glow:Show()
    else
        t.glow:Hide()
    end
end

local function showTile(t, look)
    t.look = look
    t:Show()
    local s = TM.SLOT_BY_INV[TM.slot]
    local depth, side, height, facing = TM.Framing(s.region)
    -- dress the tile's model only when its look or framing changed (refreshes come often)
    local key = strformat("%d:%.2f:%.2f:%.2f", look.lead, depth, side, height)
    if t.shown ~= key then
        t.shown = key
        local m = t.model
        m:SetUnit("player")
        m:Undress()
        m:SetPosition(depth, side, height)
        m:SetFacing(facing)
        if CO.RequestItem(look.lead) then
            m:TryOn(look.lead)
            t.waiting = nil
        else
            t.waiting = look.lead
        end
    end
    if look.missing then
        t.shade:Show()
        t.lock:Show()
        local price = TM.UnlockPrice(look.lead)
        if price == false then
            t.price:SetText("Mythic+")
        elseif price and price ~= "?" then
            t.price:SetText(price .. " coins")
        else
            t.price:SetText("")
        end
    else
        t.shade:Hide()
        t.lock:Hide()
        t.price:SetText("")
    end
    TM.PaintTile(t)
end

function TM.TileTooltip(t)
    local look = t.look
    if not look or not GameTooltip then
        return
    end
    TM.tooltipTile = t
    GameTooltip:SetOwner(t, "ANCHOR_RIGHT")
    GameTooltip:SetHyperlink("item:" .. look.lead)
    local sources = TM.sources[look.lead]
    if sources and #sources > 1 then
        local have = 0
        for _, src in ipairs(sources) do
            have = have + (src.collected and 1 or 0)
        end
        GameTooltip:AddLine(" ")
        GameTooltip:AddLine(strformat("%d items share this look (%d collected)", #sources, have), UI.Rgb(C.goldPale))
        for i = 1, min(8, #sources) do
            local src = sources[i]
            local name = GetItemInfo(src.id) or ("Item " .. src.id)
            if src.collected then
                GameTooltip:AddLine("  " .. name, UI.Rgb(C.teal))
            else
                GameTooltip:AddLine("  " .. name, UI.Rgb(C.mute))
            end
        end
    else
        TM.RequestSources(look.lead)
    end
    GameTooltip:AddLine(" ")
    if look.missing then
        local price = TM.UnlockPrice(look.lead)
        GameTooltip:AddLine("Not collected yet.", UI.Rgb(C.orange))
        if price == false then
            GameTooltip:AddLine("Only Mythic+ keystones give this look.", UI.Rgb(C.dim))
        elseif price and price ~= "?" then
            GameTooltip:AddLine(strformat("Click to try it on, then unlock it for %d Bleakhold Coins.", price),
                UI.Rgb(C.dim))
        else
            GameTooltip:AddLine("Click to try it on.", UI.Rgb(C.dim))
        end
    else
        GameTooltip:AddLine("Click to put it on, then Apply.", UI.Rgb(C.dim))
    end
    GameTooltip:AddLine("Shift-click: link it in chat.", UI.Rgb(C.mute))
    GameTooltip:Show()
end

function TM.ClickTile(t, button)
    local look = t.look
    if not look then
        return
    end
    if IsShiftKeyDown() then
        local _, link = GetItemInfo(look.lead)
        if link and ChatEdit_InsertLink then
            ChatEdit_InsertLink(link)
        end
        return
    end
    local inv = TM.slot
    if look.missing then
        if TM.trying[inv] == look.lead then
            TM.trying[inv] = nil
            TM.selectedMissing = nil
        else
            -- the model shows the look tried on, so Apply must not send an earlier pick for the slot
            if TM.pending[inv] ~= nil then
                TM.pending[inv] = nil
                changed()
            end
            TM.trying[inv] = look.lead
            TM.selectedMissing = look.lead
        end
        refreshSoon()
        return
    end
    local chosen = TM.TileState(look)
    if chosen then
        TM.SetPending(inv, nil)
    else
        TM.SetPending(inv, look.lead)
    end
end

------------------------------------------------------------------------------------------------------
-- Refresh
------------------------------------------------------------------------------------------------------
function TM.SelectSlot(inv)
    if not TM.SLOT_BY_INV[inv] then
        return
    end
    TM.slot = inv
    TM.page = 1
    TM.view = "items"
    TM.selectedMissing = nil
    for k in pairs(TM.trying) do
        TM.trying[k] = nil
    end
    if TM.missingMode then
        TM.RequestMissing()
    end
    TM.Refresh()
end

function TM.SetMissingMode(on)
    TM.missingMode = on and true or false
    TM.page = 1
    TM.selectedMissing = nil
    TM.trying = {}
    if TM.missingMode then
        TM.RequestMissing()
    end
    TM.Refresh()
end

local function refreshSlots()
    for _, s in ipairs(TM.SLOTS) do
        local b = frame.slots[s.inv]
        local real = TM.RealItem(s.inv)
        local v = TM.Effective(s.inv)
        local tex
        if v and v ~= TM.HIDDEN then
            tex = GetItemIcon(v)
        end
        if not tex then
            local _, empty = GetInventorySlotInfo(s.key)
            tex = empty
        end
        b.icon:SetTexture(tex)
        b.icon:SetVertexColor(1, 1, 1, real and 1 or 0.6)
        if v == TM.HIDDEN then
            b.hidden:Show()
        else
            b.hidden:Hide()
        end
        if TM.pending[s.inv] ~= nil or TM.trying[s.inv] then
            b.dot:Show()
        else
            b.dot:Hide()
        end
        b:SetSlotChecked(s.inv == TM.slot)
    end
end

local function refreshItems()
    local s = TM.SLOT_BY_INV[TM.slot]
    UI.SetText(frame.slotName, s.name)
    local tiles, done = TM.Tiles()
    local pages = max(1, floor((#tiles + TM.PAGE_SIZE - 1) / TM.PAGE_SIZE))
    TM.page = U.Clamp(TM.page, 1, pages)
    if TM.missingMode then
        local m = TM.missing
        frame.count:SetText(done and (U.Commas(m.total) .. " not collected") or "Loading...")
    else
        frame.count:SetText(done and (U.Commas(#tiles) .. (#tiles == 1 and " look" or " looks")) or "")
    end
    frame.missing:SetStyle(TM.missingMode and "tabOn" or "tab")
    frame.hide:SetActive(not s.weapon and TM.RealItem(TM.slot) and true or false)
    local first = (TM.page - 1) * TM.PAGE_SIZE
    for i, t in ipairs(frame.tiles) do
        local look = tiles[first + i]
        if look then
            showTile(t, look)
        else
            t.look = nil
            t.shown = nil
            t:Hide()
        end
    end
    if #tiles > 0 then
        frame.empty:Hide()
    else
        local text
        if not TM.heard and (TM.echoed or (TM.askedAt and GetTime() - TM.askedAt >= TM.WAIT)) then
            text = "This realm has no transmog module."
        elseif not done then
            text = "Loading looks..."
        elseif not TM.RealItem(TM.slot) then
            text = "Equip an item in this slot to change its look."
        elseif TM.missingMode then
            text = (TM.Query() ~= "") and "No look you are missing matches the search."
                or "You have collected every look this item can take."
        elseif TM.Query() ~= "" then
            text = "No look matches the search."
        else
            text = "No other looks for this slot yet. Equip, loot or buy items to collect their looks."
        end
        frame.empty:SetText(text)
        frame.empty:Show()
    end
    frame.pageText:SetText("Page " .. TM.page .. " / " .. pages)
    frame.prev:SetActive(TM.page > 1)
    frame.next:SetActive(TM.page < pages)

    local sel = TM.selectedMissing
    local price = sel and TM.UnlockPrice(sel)
    if sel and price and price ~= "?" then
        frame.unlock:SetLabel(strformat("Unlock for %d Bleakhold Coins", price))
        frame.unlock:SetActive((TM.coins or 0) >= price)
        frame.unlock:Show()
    else
        frame.unlock:Hide()
    end
end

-- Illusions go on weapons only (the module refuses shields and held-in-off-hand items).
local WEAPON_SLOTS = {
    [16] = { INVTYPE_WEAPON = true, INVTYPE_2HWEAPON = true, INVTYPE_WEAPONMAINHAND = true },
    [17] = { INVTYPE_WEAPON = true, INVTYPE_2HWEAPON = true, INVTYPE_WEAPONOFFHAND = true },
}
function TM.CanHaveIllusion(inv)
    local real = TM.RealItem(inv)
    if not real then
        return false
    end
    local _, _, _, _, _, _, _, _, equipLoc = GetItemInfo(real)
    if not equipLoc then
        CO.RequestItem(real)
        return false
    end
    return WEAPON_SLOTS[inv] and WEAPON_SLOTS[inv][equipLoc] or false
end

local function refreshIllusions()
    frame.mainHand:SetStyle(TM.illusionSlot == 16 and "tabOn" or "tab")
    frame.offHand:SetStyle(TM.illusionSlot == 17 and "tabOn" or "tab")
    frame.illRows:ReleaseAll()
    local inv = TM.illusionSlot
    local current = TM.EffectiveIllusion(inv)
    local list = { { id = 0, name = "No illusion" }, { id = TM.HIDDEN, name = "Hide the weapon's glow" } }
    for _, it in ipairs(TM.illusions) do
        list[#list + 1] = it
    end
    local y = 0
    local hasWeapon = TM.CanHaveIllusion(inv)
    for _, it in ipairs(list) do
        local r = frame.illRows:Acquire()
        r:ClearAllPoints()
        r:SetPoint("TOPLEFT", frame.illScroll.child, "TOPLEFT", 0, -y)
        r:SetLabel(it.name)
        r:SetStyle(it.id == current and "rowOn" or "row")
        r:SetActive(hasWeapon)
        r:SetScript("OnClick", function()
            TM.SetIllusion(inv, it.id)
        end)
        y = y + ILL_ROW
    end
    frame.illScroll:SetContentHeight(y)
    if not hasWeapon then
        frame.illEmpty:SetText("Equip a weapon in this hand to give it an illusion (shields and held items take none).")
        frame.illEmpty:Show()
    elseif #TM.illusions == 0 then
        frame.illEmpty:SetText("Enchant a weapon to collect its glow as an illusion.")
        frame.illEmpty:Show()
    else
        frame.illEmpty:Hide()
    end
end

function TM.Refresh()
    if not frame or not frame:IsShown() then
        return
    end
    refreshSlots()
    dressModel(frame.model)

    -- outfits
    local items = { { value = "", text = (#TM.outfits > 0) and "Outfits" or "No outfits yet" } }
    for _, o in ipairs(TM.outfits) do
        items[#items + 1] = { value = o.name, text = o.name }
    end
    frame.outfit:SetItems(items)
    local known = false
    for _, o in ipairs(TM.outfits) do
        known = known or o.name == TM.outfit
    end
    frame.outfit:SetValue(known and TM.outfit or "", true)
    frame.delete:SetActive(known)

    -- price and Apply
    local changes = TM.Changes()
    if TM.applying then
        frame.cost:SetText("Applying...")
    elseif #changes == 0 then
        frame.cost:SetText("|cff808080No changes|r")
    elseif TM.costPending then
        frame.cost:SetText("|cff808080Cost: ...|r")
    else
        frame.cost:SetText("Cost: " .. TM.Money(TM.cost) .. (TM.canPay and "" or "  |cffff2020(not enough)|r"))
    end
    frame.apply:SetActive(#changes > 0 and not TM.applying and TM.canPay and TM.CostKnown())
    frame.strip:SetActive(not TM.applying)
    frame.undo:SetActive(#changes > 0 or next(TM.trying) ~= nil)
    frame.status:SetText(TM.status or "")

    -- header: the Items / Illusions choice only when there is a choice (one button held down alone reads as a stray)
    if TM.hasIllusions then
        frame.itemsTab:Show()
        frame.illusionsTab:Show()
    else
        frame.itemsTab:Hide()
        frame.illusionsTab:Hide()
    end
    if not TM.hasIllusions and TM.view == "illusions" then
        TM.view = "items"
    end
    frame.itemsTab:SetStyle(TM.view == "items" and "tabOn" or "tab")
    frame.illusionsTab:SetStyle(TM.view == "illusions" and "tabOn" or "tab")
    if TM.coins then
        frame.coins:SetValue(U.Commas(TM.coins) .. " coins")
        frame.coins:Show()
    else
        frame.coins:Hide()
    end
    local total = 0
    for _, s in ipairs(TM.SLOTS) do
        total = total + #(TM.looks[s.inv] or {})
    end
    local coll = ns.S and ns.S.coll
    total = (coll and coll.transmogOwned) or total
    frame.collected:SetLabel(total > 0 and "Collected" or "")
    frame.collected:SetValue(total > 0 and U.Commas(total) or "")
    frame.collected:ClearAllPoints()
    if TM.coins then
        frame.collected:SetPoint("RIGHT", frame.coins.icon, "LEFT", -14, 0)
    else
        frame.collected:SetPoint("TOPRIGHT", frame.right, "TOPRIGHT", 0, -7)
    end

    if TM.view == "illusions" then
        frame.items:Hide()
        frame.ill:Show()
        refreshIllusions()
    else
        frame.ill:Hide()
        frame.items:Show()
        refreshItems()
    end
end

------------------------------------------------------------------------------------------------------
-- Showing the tab
------------------------------------------------------------------------------------------------------
local lastSearch
function TM.ShowTab()
    if not frame then
        build()
    end
    local first = not frame:IsShown()
    frame:Show()
    if first then
        -- models on frames that were hidden are dressed again
        frame.model.dressed = nil
        for _, t in ipairs(frame.tiles) do
            t.shown = nil
        end
        if TM.stale or not TM.askedAt or not TM.heard then
            TM.RequestAll()
        else
            TM.Send("GetTransmogStatus")
            TM.Send("GetOutfits")
        end
        if TM.missingMode then
            TM.RequestMissing()
        end
        if not TM.coins and not TM.coinsAsked then
            TM.AskCoins()
        end
        lastSearch = TM.Query()
        ns.After(TM.WAIT, refreshSoon)
    elseif TM.missingMode and TM.Query() ~= lastSearch then
        missingSoon()
    end
    lastSearch = TM.Query()
    TM.Refresh()
end

function TM.HideTab()
    if frame and frame:IsShown() then
        frame:Hide()
        hideTooltip()
    end
end

function TM.Open()
    CO.ShowTab("transmog")
end

-- The window closing ends the visit at the transmogrifier and drops the changes not applied.
local closed = CO.frame.OnClose
CO.frame.OnClose = function(self)
    if closed then
        closed(self)
    end
    TM.canApply = false
    TM.wantAccess = nil
    TM.portableAsked = nil
    -- the next show is a first show again: it asks the module for what changed meanwhile
    TM.HideTab()
    TM.pending, TM.illusionPending, TM.trying = {}, {}, {}
    TM.cost, TM.canPay = 0, true
    TM.selectedMissing = nil
    TM.status = nil
end

-- Item names and icons arrive from the server after CO.RequestItem: the tiles waiting for one retry.
ns.Every(0.5, function()
    if not TM.Shown() then
        return
    end
    for _, t in ipairs(frame.tiles) do
        if t.waiting and t:IsShown() and GetItemInfo(t.waiting) then
            t.model:TryOn(t.waiting)
            t.waiting = nil
        end
    end
end)

-- What the slots can take depends on the items in them.
ns.RegisterEvent("PLAYER_EQUIPMENT_CHANGED", function()
    TM.stale = true
    if TM.Shown() then
        H.CollectionUpdated()
        TM.Refresh()
    end
end)

------------------------------------------------------------------------------------------------------
-- Commands
------------------------------------------------------------------------------------------------------
local function cameraCommand(args)
    local s = TM.SLOT_BY_INV[TM.slot]
    local key = TM.Race() .. ":" .. s.region
    ns.db.mogCamera = type(ns.db.mogCamera) == "table" and ns.db.mogCamera or {}
    if args == "reset" then
        ns.db.mogCamera[key] = nil
        ns.Print("Transmog tiles for " .. s.name .. ": framing reset.")
    else
        local d, side, h = strmatch(args or "", "^(%-?[%d%.]+)%s+(%-?[%d%.]+)%s+(%-?[%d%.]+)$")
        d, side, h = tonumber(d), tonumber(side), tonumber(h)
        if not (d and side and h) then
            ns.Print("usage: /bh mog camera <depth> <side> <height> (moves the selected slot's tiles for your race), "
                .. "or /bh mog camera reset")
            return
        end
        ns.db.mogCamera[key] = { U.Clamp(d, -10, 10), U.Clamp(side, -10, 10), U.Clamp(h, -10, 10) }
        ns.Print(strformat("Transmog tiles for %s: depth %+.1f, side %+.1f, height %+.1f.", s.name, d, side, h))
    end
    refreshSoon()
end

ns.AddCommand("mog", "open Transmog (mog camera <depth> <side> <height> frames the tiles)", function(args)
    local sub, rest = strmatch(args or "", "^(%S*)%s*(.-)$")
    if sub == "camera" then
        cameraCommand(rest)
    else
        TM.Open()
    end
end)

-- /transmog is the module's own addon's when it is installed: decided at login, once every addon has loaded
-- (Bleakhold loads before Transmog).
ns.RegisterEvent("PLAYER_LOGIN", function()
    if TM.Upstream() or SLASH_BLEAKHOLDTRANSMOG1 then
        return
    end
    SLASH_BLEAKHOLDTRANSMOG1 = "/transmog"
    SlashCmdList.BLEAKHOLDTRANSMOG = function()
        TM.portableAsked = GetTime()
        TM.Send("RequestPortable")
        TM.Open()
    end
end)
