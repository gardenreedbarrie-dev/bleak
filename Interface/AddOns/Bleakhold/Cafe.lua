-- Bleakhold: the café (docs/BleakholdProtocol.md section 21). Everything shown is server state (State.lua parses every
-- café message into S.cafe*); this file holds what the café's frames share:
--   ns.Cafe          the queries (catalogue lookups over CafeData.lua and DEF H/G/F/U, prices, money text, timers,
--                    the active ticket, icons), the per-op send gates, the options, sounds and the HUD placement helper
--   the orb          a cup on the minimap ring: each café's state, baristas, queue and Morning Rush; opens the window
--   /bh cafe         opens the café window (menu: the menu); keys, scale, sound, motion, memory, autoselect and model
--                    <name> set options
--   demo mode        Cafe.DemoRespond answers the café's GETs and intents for /bh demo (Demo.lua), with a small stand-in
--                    for the server's shift (tickets, steps, grades, results, the queue, an order); /bh demo cafe runs a
--                    60 s scripted shift through the real bar (Cafe.Press) and receive path
-- The barista bar, the timing bar and the key overrides are CafeBar.lua; the other HUD panels CafeHud.lua; the windows
-- CafeWindow.lua and CafeMenu.lua, which open by UI.Open keys (cafe, cafeshift, caferecipes, cafeboard, caferewards,
-- cafehelp, cafemenu). Feature 131072: with it off nothing of the café shows.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S
local CD = ns.CafeData

local floor, ceil, max, min = math.floor, math.ceil, math.max, math.min
local strformat = string.format

local Cafe = {}
ns.Cafe = Cafe

-- text bytes kept ASCII in the source (UTF-8 escapes)
Cafe.E = "\195\169"            -- é
Cafe.TIMES = "\195\151"        -- ×
Cafe.DOT = " \194\183 "        -- " · "
Cafe.NAME = "Caf\195\169"

BINDING_NAME_BLEAKHOLD_CAFE = "Open the caf\195\169 window"

-- HELLO caps (Comm.lua): the café's UI is here, so the café staff's gossip opens its windows (CAFUI) instead of pages
Comm.clientCaps = bit.bor(Comm.clientCaps or 0, Comm.CAPS.CAFE_UI)

Cafe.PATCH_PROBE = "Interface\\Icons\\BH_Cafe_Espresso"   -- shipped only in patch-4 (cafe.json icons)
Cafe.STATION_ORDER = CD.stationOrder

------------------------------------------------------------------------------------------------------
-- Options (ns.db.options): keys, HUD scale, sounds, motion, from-memory checklist, ticket auto-select
------------------------------------------------------------------------------------------------------
Cafe.DEFAULTS = { cafeKeys = "1,2,3,4,5,6,7,8", cafeScale = 1.0, cafeSound = true, cafeMotion = true, cafeMemory = false,
    cafeTicketAutoSelect = true }
Cafe.SCALE_MIN, Cafe.SCALE_MAX = 0.8, 1.4

function Cafe.Option(name)
    local v = ns.db.options[name]
    local d = Cafe.DEFAULTS[name]
    if v == nil or (d ~= nil and type(v) ~= type(d)) then
        return d
    end
    if name == "cafeScale" then
        return U.Clamp(v, Cafe.SCALE_MIN, Cafe.SCALE_MAX)
    end
    return v
end

function Cafe.SetOption(name, v)
    ns.db.options[name] = v
    ns.Fire("CAFE_OPTIONS", name)
end

-- A key as the option takes it: an optional SHIFT-, CTRL- and ALT- in front of one of A-Z, 0-9, - and =, in any order.
-- It comes back in the client's own order, ALT-CTRL-SHIFT- (the string a pressed key's binding is looked up by), so
-- "SHIFT-CTRL-1" binds and counts as "CTRL-SHIFT-1".
function Cafe.ValidKey(key)
    if type(key) ~= "string" then
        return nil
    end
    key = key:upper():gsub("%s", "")
    local rest, seen = key, {}
    while true do
        local mod, tail = rest:match("^(%u+)%-(.+)$")
        if mod and (mod == "SHIFT" or mod == "CTRL" or mod == "ALT") and not seen[mod] then
            seen[mod] = true
            rest = tail
        else
            break
        end
    end
    if rest:match("^[A-Z0-9=%-]$") then
        return (seen.ALT and "ALT-" or "") .. (seen.CTRL and "CTRL-" or "") .. (seen.SHIFT and "SHIFT-" or "") .. rest
    end
    return nil
end

-- "1,2,3,4,5,6,7,8": exactly eight different keys, or nil and the reason.
function Cafe.ParseKeys(text)
    local keys, seen = {}, {}
    for part in (tostring(text or "") .. ","):gmatch("([^,]*),") do
        if part:match("%S") then
            local key = Cafe.ValidKey(part)
            if not key then
                return nil, "\"" .. part:gsub("^%s+", ""):gsub("%s+$", "") .. "\" is not a key (A-Z, 0-9, - or =, "
                    .. "with SHIFT-, CTRL- or ALT- in front)."
            end
            if seen[key] then
                return nil, key .. " is given twice."
            end
            seen[key] = true
            keys[#keys + 1] = key
        end
    end
    if #keys ~= 8 then
        return nil, "Give exactly eight keys, one per slot (" .. #keys .. " given)."
    end
    return keys
end

function Cafe.Keys()
    return Cafe.ParseKeys(Cafe.Option("cafeKeys")) or Cafe.ParseKeys(Cafe.DEFAULTS.cafeKeys)
end

-- The hotkey text of an action button (GetBindingText(key, "KEY_", 1)): SHIFT-1 reads s-1.
function Cafe.KeyLabel(key)
    key = key or ""
    return (key:gsub("SHIFT%-", "s-"):gsub("CTRL%-", "c-"):gsub("ALT%-", "a-"))
end

function Cafe.SlotKey(slot)
    local keys = Cafe.Keys()
    return Cafe.KeyLabel(keys[slot] or "")
end

------------------------------------------------------------------------------------------------------
-- State queries
------------------------------------------------------------------------------------------------------
function Cafe.Enabled()
    return Comm.HasFeature(Comm.FEATURE.CAFE)
end

function Cafe.OnShift()
    local st = S.cafeState
    return Cafe.Enabled() and st ~= nil and st.onShift == true
end

-- The café of the player's team: 1 The Lion's Roast (Alliance), 2 The Grinding Tusk (Horde).
function Cafe.MyCafe()
    local f = UnitFactionGroup and UnitFactionGroup("player")
    if f == "Horde" then
        return 2
    elseif f == "Alliance" then
        return 1
    end
    local st = S.cafeState
    return (st and st.cafeId and st.cafeId > 0) and st.cafeId or 1
end

function Cafe.CafeId()
    local st = S.cafeState
    if st and st.cafeId and st.cafeId > 0 then
        return st.cafeId
    end
    return Cafe.MyCafe()
end

-- a built-in record with the server's DEF fields laid over it (an empty DEF field keeps the built-in value)
local function over(base, def, map)
    local out = {}
    for k, v in pairs(base or {}) do
        out[k] = v
    end
    for from, to in pairs(map) do
        if def and def[from] ~= nil then
            out[to] = def[from]
        end
    end
    return out
end

function Cafe.Cafe(id)
    id = tonumber(id)
    if not id then
        return nil
    end
    local base, def = CD.cafes[id], ns.Def("H", id)
    if not base and not def then
        return nil
    end
    local c = over(base, def, { name = "name", cityKey = "city", team = "team", ownerName = "owner", tagline = "tagline",
        zoneId = "zone", mapId = "map", colorHex = "trim" })
    c.id = id
    c.cityKey = c.city
    c.ownerName = c.owner
    c.name = c.name or ("Caf" .. Cafe.E .. " #" .. id)
    return c
end

function Cafe.CafeName(id)
    local c = Cafe.Cafe(id)
    return c and c.name or Cafe.NAME
end

function Cafe.Station(letter)
    local s = CD.stations[letter or ""]
    if not s then
        return nil
    end
    local out = over(s, nil, {})
    out.cafeName = s.names and s.names[Cafe.CafeId()] or s.name
    return out
end

function Cafe.StationName(letter)
    local s = CD.stations[letter or ""]
    return s and s.name or "station"
end

-- short station names, for a slot's label and a checklist line
Cafe.SHORT_STATION = { G = "Grinder", E = "Espresso", K = "Kettle", C = "Cold Box", B = "Blender", S = "Syrups",
    V = "Counter" }
function Cafe.ShortStation(letter)
    return Cafe.SHORT_STATION[letter or ""] or Cafe.StationName(letter)
end

function Cafe.Action(id)
    id = tonumber(id)
    if not id then
        return nil
    end
    local base, def = CD.actions[id], ns.Def("G", id)
    if not base and not def then
        return nil
    end
    local a = over(base, def, { station = "station", key = "key", kind = "kind", durMs = "durMs", name = "name",
        hordeName = "hordeName", spellId = "spellId" })
    a.id = id
    if def and def.goldLoPermille and def.goldHiPermille then
        a.gold = { def.goldLoPermille, def.goldHiPermille }
    end
    if Cafe.CafeId() == 2 and a.hordeName then
        a.name = a.hordeName
    end
    a.name = a.name or ("Step " .. id)
    a.timed = a.kind == "H"
    return a
end

function Cafe.ActionName(id)
    local a = Cafe.Action(id)
    return a and a.name or "?"
end

-- The actions of a station by bar key: { [key] = action }.
function Cafe.ActionsAt(letter)
    local out = {}
    local ids = {}
    for id in pairs(CD.actions) do
        ids[id] = true
    end
    for _, id in ipairs(ns.DefIds("G")) do
        ids[id] = true
    end
    for id in pairs(ids) do
        local a = Cafe.Action(id)
        if a and a.station == letter and a.key and a.key >= 1 and a.key <= 8 and not out[a.key] then
            out[a.key] = a
        end
    end
    return out
end

function Cafe.Recipe(id)
    id = tonumber(id)
    if not id then
        return nil
    end
    local base, def = CD.recipes[id], ns.Def("F", id)
    if not base and not def then
        return nil
    end
    local r = over(base, def, { cafeId = "cafeId", family = "family", tier = "tier", unlockLevel = "unlock",
        price80Copper = "price80", buffMin = "buffMin", steps = "steps", name = "name", text = "text", archetype = "n" })
    r.id = id
    r.unlockLevel = r.unlock or 1
    r.unlock = r.unlockLevel
    r.tier = r.tier or 1
    r.price80Copper = r.price80 or (CD.tiers[r.tier] and CD.tiers[r.tier].price80) or 0
    r.price80 = r.price80Copper
    r.buffMin = r.buffMin or (CD.tiers[r.tier] and CD.tiers[r.tier].buffMin) or 30
    r.steps = r.steps or {}
    r.name = r.name or ("Drink #" .. id)
    return r
end

function Cafe.RecipeName(id)
    local r = Cafe.Recipe(id)
    return r and r.name or "a drink"
end

-- The recipes of a café (optionally of one family), by id.
function Cafe.Recipes(cafeId, family)
    local ids, out = {}, {}
    for id in pairs(CD.recipes) do
        ids[id] = true
    end
    for _, id in ipairs(ns.DefIds("F")) do
        ids[id] = true
    end
    for id in pairs(ids) do
        local r = Cafe.Recipe(id)
        if r and (not cafeId or r.cafeId == cafeId) and (not family or r.family == family) then
            out[#out + 1] = r
        end
    end
    table.sort(out, function(a, b) return a.id < b.id end)
    return out
end

function Cafe.Level(n)
    n = tonumber(n)
    local base, def = CD.levels[n or 0], ns.Def("U", n)
    if not base and not def then
        return nil
    end
    local l = over(base, def, { totalXp = "xp", text = "text" })
    l.level = n
    l.totalXp = l.xp
    return l
end

-- One name per family everywhere: the singular as a tag (a recipe card, the Staff Drink's rows), the plural on tabs and
-- filters (the menu's Coffee / Tea / Shakes, the Recipes filter).
Cafe.FAMILY_NAMES = { C = "Coffee", T = "Tea", M = "Shake" }
Cafe.FAMILY_PLURAL = { C = "Coffee", T = "Tea", M = "Shakes" }
function Cafe.Family(recipeId)
    local r = Cafe.Recipe(recipeId)
    return r and r.family or "C"
end

function Cafe.FamilyName(f)
    local d = CD.families[f or ""]
    return Cafe.FAMILY_NAMES[f or ""] or (d and d.name) or "Drink"
end

-- The stock look has no family accents (PLAN decision 1): the gold of names everywhere; kept for the spec's API.
function Cafe.FamilyColor()
    return C.gold
end

-- The player's price: the menu's (CAFM), else the server's rule: max(200, price80 x max(0.10, level/80)) rounded up to
-- whole silver.
function Cafe.Price(recipeId)
    local r = Cafe.Recipe(recipeId)
    local menu = r and S.cafeMenu[r.cafeId] or S.cafeMenu[Cafe.MyCafe()]
    local row = menu and menu.byRecipe[recipeId]
    if row then
        return row.priceCopper
    end
    if not r then
        return 0
    end
    local level = (UnitLevel and UnitLevel("player")) or 80
    local raw = r.price80Copper * max(0.10, level / 80)
    return max(200, ceil(raw / 100 - 1e-9) * 100)
end

-- Why a drink's buff does nothing (CAFM effective 0, CAFBF coffeeCounts 0). The server does not say: coffee at the level
-- cap, XP gain off, or a family whose bonus is off on the realm. The level wording only where it is surely the reason
-- (coffee at the level cap), else a neutral line.
-- Today's XP (CAFST D): the XP credited so far, the full-rate allowance and what the half-rate band can still credit.
-- The server credits half of every XP earned in that band (CreditXp), so dayXp never passes full + floor(half / 2).
function Cafe.DayXpBands(day)
    day = day or {}
    local full = max(0, day.dayXpFull or 0)
    return max(0, day.dayXp or 0), full, floor(max(0, day.dayXpHalf or 0) / 2)
end

Cafe.LEVEL_CAP = 80                -- Wrath of the Lich King's level cap
function Cafe.NoEffectText(family)
    if family == "C" and UnitLevel and (UnitLevel("player") or 0) >= Cafe.LEVEL_CAP then
        return "No effect at the level cap"
    end
    return "No effect for you right now"
end

-- Money as the client writes it (GetCoinTextureString): "1|T..gold..|t 20|T..silver..|t". Set it with SetText, never
-- UI.SetText (which doubles the '|').
local COINS = { { 10000, "Interface\\MoneyFrame\\UI-GoldIcon" }, { 100, "Interface\\MoneyFrame\\UI-SilverIcon" },
    { 1, "Interface\\MoneyFrame\\UI-CopperIcon" } }
Cafe.COINS = COINS
function Cafe.Money(copper)
    copper = max(0, floor(tonumber(copper) or 0))
    local parts = {}
    for i, c in ipairs(COINS) do
        local n = floor(copper / c[1])
        copper = copper - n * c[1]
        if n > 0 or (i == 3 and #parts == 0) then
            parts[#parts + 1] = (i == 1 and U.Commas(n) or tostring(n)) .. "|T" .. c[2] .. ":0:0:2:0|t"
        end
    end
    return table.concat(parts, " ")
end

-- Plain money text for dialogs and tooltips: "1g 20s 5c".
function Cafe.MoneyPlain(copper)
    return ns.RewardText("G", max(0, floor(tonumber(copper) or 0)))
end

------------------------------------------------------------------------------------------------------
-- Pauses (CAFE open 2: danger nearby). The server's café clocks stand still (patience, the house and a live Morning
-- Rush): while a café is paused its timers show the value they had when the pause began, and on the resume every one
-- received before it moves its recvAt forward by the paused span. Two clocks keep running through a pause, as the
-- server's do: an order's pickup (CAFO R: its order tick still expires it) and a Rush that is only coming (rushState 1:
-- its start is wall-clock time). The server re-sends CAFQ (and CAFE) on its own, not CAFT, so a barista on shift there
-- asks for it.
------------------------------------------------------------------------------------------------------
local pausedAt = {}          -- [cafeId] = the GetTime() the pause began

function Cafe.Paused(cafeId)
    local c = cafeId and S.cafes and S.cafes[cafeId]
    return (c and c.open == 2) and true or false
end

-- Seconds of a timer's countdown since recvAt; with cafeId the current pause of that café does not count.
function Cafe.Elapsed(recvAt, cafeId)
    local now = GetTime()
    recvAt = recvAt or now
    local p0 = cafeId and pausedAt[cafeId]
    if p0 and Cafe.Paused(cafeId) then
        return max(0, min(now, p0) - recvAt)
    end
    return max(0, now - recvAt)
end

-- the paused span [p0, p1] that a timer received at t.recvAt counted down through
local function unfreeze(t, p0, p1)
    if t and t.recvAt then
        t.recvAt = t.recvAt + max(0, p1 - max(t.recvAt, p0))
    end
end

local function resumed(cafeId, p0, p1)
    local st = S.cafeState
    local mine = st and st.onShift and st.cafeId == cafeId
    if mine then
        for _, t in ipairs(S.cafeTickets or {}) do
            unfreeze(t, p0, p1)
        end
        if st.rush and st.rush.rushState == 2 then
            unfreeze(st.rush, p0, p1)
        end
    end
    if S.cafeQueue and S.cafeQueue.cafeId == cafeId then
        unfreeze(S.cafeQueue, p0, p1)
    end
    if S.cafeOrder and S.cafeOrder.cafeId == cafeId and S.cafeOrder.state ~= "R" then
        unfreeze(S.cafeOrder, p0, p1)
    end
    if mine and Cafe.Enabled() then
        Comm.Refresh("CAFT")
    end
end

ns.On("STATE", function(topic)
    if topic ~= "CAFE" then
        return
    end
    local now = GetTime()
    for id, c in pairs(S.cafes or {}) do
        if c.open == 2 and not pausedAt[id] then
            pausedAt[id] = c.recvAt or now
        end
    end
    for id, p0 in pairs(pausedAt) do
        local c = S.cafes and S.cafes[id]
        if not (c and c.open == 2) then
            pausedAt[id] = nil
            resumed(id, p0, (c and c.recvAt) or now)
        end
    end
end)

-- Seconds (or ms) left of a state timer, counted down from the message's arrival; nil when the field is empty. With
-- cafeId the timer is one of the café's clocks and stands still while that café is paused.
function Cafe.Left(tbl, key, cafeId)
    local v = tbl and tbl[key]
    if type(v) ~= "number" then
        return nil
    end
    return max(0, v - Cafe.Elapsed(tbl.recvAt, cafeId))
end

-- The Morning Rush's seconds (a CAFE row or CAFST R): only a live Rush (rushState 2) stands still in a pause.
function Cafe.RushLeft(tbl, cafeId)
    return Cafe.Left(tbl, "rushSec", tbl and tbl.rushState == 2 and cafeId or nil)
end

-- An order's leftSec (CAFO): the house's clock stands still in a pause, the pickup's (R) keeps running.
function Cafe.OrderLeft(o)
    return Cafe.Left(o, "leftSec", o and o.state ~= "R" and o.cafeId or nil)
end

-- " (paused)" after an order's clock while its café is paused and that clock stands still (never the pickup's)
function Cafe.OrderPausedText(o)
    return (o and o.state ~= "R" and Cafe.Paused(o.cafeId)) and " (paused)" or ""
end

function Cafe.LeftMs(tbl, key, cafeId)
    local v = tbl and tbl[key]
    if type(v) ~= "number" then
        return nil
    end
    return max(0, v - Cafe.Elapsed(tbl.recvAt, cafeId) * 1000)
end

-- A step in seconds: the stock abbreviations (SecondsToTimeAbbrev): "28 m", "45 s".
function Cafe.ShortTime(sec)
    sec = max(0, floor((sec or 0) + 0.5))
    if sec >= 3600 then
        return ceil(sec / 3600) .. " h"
    elseif sec >= 60 then
        return ceil(sec / 60) .. " m"
    end
    return sec .. " s"
end

-- A countdown's whole seconds, rounded up as the stock timers count (every café clock: "~45 s" stays 45 until 44.0).
function Cafe.CeilSec(sec)
    return max(0, ceil((sec or 0) - 1e-6))
end

-- Tired off shift (CAFST flag 4 with tiredSec, the rest still needed): once that rest has run down here the next shift
-- pays in full, though no CAFST says so (the server only drops the Tired aura): true then, and CAFST is asked for once
-- per record (at most every REST_ASK_GAP s, should the server's answer still carry flag 4), so flag 4 clears.
Cafe.REST_ASK_GAP = 10
local restAskedAt
function Cafe.Rested(st)
    if not st or st.onShift or bit.band(st.flags or 0, 4) == 0 or type(st.tiredSec) ~= "number" then
        return false
    end
    if (Cafe.Left(st, "tiredSec") or 0) > 0 then
        return false
    end
    local now = GetTime()
    if not st.restAsked and (not restAskedAt or now - restAskedAt >= Cafe.REST_ASK_GAP) then
        st.restAsked = true
        restAskedAt = now
        if Comm.ready then
            Comm.Refresh("CAFST")
        end
    end
    return true
end

------------------------------------------------------------------------------------------------------
-- Text and rows
------------------------------------------------------------------------------------------------------
-- The whole width of fs's text. The client measures a FontString as it shows it, cut with "..." to the box it was
-- given once both a width and a height are set (UI.OneLine sets both; CSimpleFontString::GetStringWidth measures
-- GetDisplayText(width, height)), so a box measured again would only ever shrink. The box is let go first (width and
-- height 0 show the whole text); the caller sets it again.
function Cafe.FullWidth(fs)
    fs:SetWidth(0)
    fs:SetHeight(0)
    return fs:GetStringWidth() or 0
end

-- A pool of list rows that leaves the rows in use as they are. UI.Pool's ReleaseAll hides every row and Acquire shows
-- it again, and a hide resets a Button to NORMAL, after which the client drops its mouse-up (CSimpleButton): a refresh
-- between a row's mouse-down and mouse-up (a CAFQ, a CAFST on every yard walked) would lose the click. Here
-- pool:Begin() starts a layout, pool:Acquire() hands out the next row (shown only if it was hidden), pool:Finish() hides
-- the rows past the last one handed out. items and used read as UI.Pool's.
function Cafe.StablePool(factory)
    local pool = { items = {}, used = 0 }
    function pool:Begin()
        self.used = 0
    end
    function pool:Acquire()
        self.used = self.used + 1
        local item = self.items[self.used]
        if not item then
            item = factory(self.used)
            self.items[self.used] = item
        end
        if not item:IsShown() then
            item:Show()
        end
        return item
    end
    function pool:Finish()
        for i = self.used + 1, #self.items do
            if self.items[i]:IsShown() then
                self.items[i]:Hide()
            end
        end
    end
    return pool
end

-- The tooltip of a row shown again when the row's content changed under it (a refresh reuses rows for other entries).
function Cafe.RetipIfOwned(row, fn)
    if GameTooltip and GameTooltip:IsShown() and GameTooltip.GetOwner and GameTooltip:GetOwner() == row then
        fn(row)
    end
end

------------------------------------------------------------------------------------------------------
-- The café's city, without the zone's name (GetRealZoneText is in the client's language: "Sturmwind" on deDE). The
-- world map's area of the player's zone (WorldMapArea.dbc: Stormwind City 301, Orgrimmar 321), learnt with
-- SetMapToCurrentZone only while the world map is closed (it would turn the map the player looks at) and again after
-- each zone change; until it is known (or without the map functions) IsResting() stands in: both cities are rest areas.
------------------------------------------------------------------------------------------------------
Cafe.CITY_AREAS = { sw = 301, org = 321 }
local zoneArea, zoneDirty = nil, true

function Cafe.ZoneArea()
    if zoneDirty and SetMapToCurrentZone and GetCurrentMapAreaID
        and not (WorldMapFrame and WorldMapFrame:IsShown()) then
        SetMapToCurrentZone()
        local id = GetCurrentMapAreaID()
        zoneArea = type(id) == "number" and id > 0 and id or nil
        zoneDirty = false
    end
    return zoneArea
end

local function zoneChanged()
    zoneDirty = true
end
ns.RegisterEvent("ZONE_CHANGED_NEW_AREA", zoneChanged)
ns.RegisterEvent("PLAYER_ENTERING_WORLD", zoneChanged)

-- Is the player in the city of café cafeId (nil: of any café)?
function Cafe.InCafeCity(cafeId)
    local area = Cafe.ZoneArea()
    if not area then
        return IsResting and IsResting() and true or false
    end
    for id, base in pairs(CD.cafes) do
        if cafeId == nil or id == cafeId then
            local c = Cafe.Cafe(id)
            local want = Cafe.CITY_AREAS[(c and c.cityKey) or base.city or ""]
            if want and want == area then
                return true
            end
        end
    end
    return false
end

------------------------------------------------------------------------------------------------------
-- Tickets and the queue selection
------------------------------------------------------------------------------------------------------
local selectedTicket, selectedOrder

function Cafe.Tickets()
    return S.cafeTickets or {}
end

function Cafe.Ticket(id)
    for _, t in ipairs(Cafe.Tickets()) do
        if t.ticketId == id then
            return t
        end
    end
end

-- The ticket the bar works on: the drink in hand, else the chosen tab, else the oldest.
function Cafe.ActiveTicket()
    local list = Cafe.Tickets()
    for _, t in ipairs(list) do
        if t.inHand then
            return t
        end
    end
    if selectedTicket then
        local t = Cafe.Ticket(selectedTicket)
        if t then
            return t
        end
    end
    return list[1]
end

-- Choose a ticket tab; the drink in hand cannot be switched away from (the server says cafe_hands).
function Cafe.SelectTicket(id)
    for _, t in ipairs(Cafe.Tickets()) do
        if t.inHand and t.ticketId ~= id then
            return false
        end
    end
    if not Cafe.Ticket(id) then
        return false
    end
    selectedTicket = id
    ns.Fire("CAFE_SELECT", "ticket", id)
    return true
end

-- The queue row slot 1 takes (CTAKE id; nil: CTAKE 0, the best one the barista can make).
function Cafe.SelectedOrder()
    local q = S.cafeQueue
    if not selectedOrder or not q then
        return nil
    end
    for _, r in ipairs(q.rows) do
        if r.orderId == selectedOrder and r.state == "W" then
            return selectedOrder
        end
    end
    return nil
end

function Cafe.SelectOrder(orderId)
    selectedOrder = orderId
    ns.Fire("CAFE_SELECT", "order", orderId)
end

-- the ticket list changed: a new ticket is the one worked on while no cup is in hand (option cafeTicketAutoSelect)
local knownTickets = {}
ns.On("STATE", function(op)
    if op ~= "CAFT" then
        return
    end
    local fresh, now = {}, {}
    for _, t in ipairs(Cafe.Tickets()) do
        now[t.ticketId] = true
        if not knownTickets[t.ticketId] then
            fresh[#fresh + 1] = t.ticketId
        end
    end
    knownTickets = now
    if selectedTicket and not now[selectedTicket] then
        selectedTicket = nil
    end
    local active = Cafe.ActiveTicket()
    if #fresh > 0 and Cafe.Option("cafeTicketAutoSelect") and not (active and active.inHand) then
        selectedTicket = fresh[#fresh]
    end
end)

-- The lowest unlocked recipe of a family at the player's café (the Staff Drink).
function Cafe.StaffRecipe(family)
    local level = (S.cafeState and S.cafeState.level) or (S.cafeProfile and S.cafeProfile.level) or 1
    local best
    for _, r in ipairs(Cafe.Recipes(Cafe.MyCafe(), family)) do
        if r.unlockLevel <= level and (not best or r.unlockLevel < best.unlockLevel
            or (r.unlockLevel == best.unlockLevel and r.id < best.id)) then
            best = r
        end
    end
    return best and best.id or nil
end

------------------------------------------------------------------------------------------------------
-- Look: icons, patience colours, quality words, sounds
------------------------------------------------------------------------------------------------------
-- Stock 3.3.5a icons (SpellIcon.dbc); patch-4 ships the café's own (BH_Cafe_*) for stations, families and rewards.
Cafe.ICONS = {
    family = { C = "INV_Drink_15", T = "INV_Drink_23", M = "INV_Misc_Food_31" },
    station = { G = "INV_Gizmo_02", E = "INV_Gizmo_01", K = "INV_Drink_17", C = "Spell_Frost_FrostNova", B = "INV_Drink_21",
        S = "INV_Drink_11", V = "INV_Misc_Note_01" },
    action = {
        [1] = "INV_Misc_Food_02", [2] = "INV_Misc_Dust_02", [3] = "INV_Gizmo_01", [4] = "INV_Drink_06",
        [5] = "INV_Misc_Dust_04", [6] = "Spell_Misc_Drink", [7] = "INV_Drink_17", [8] = "INV_Misc_Herb_10",
        [9] = "INV_Misc_Herb_15", [10] = "INV_Misc_Herb_16", [11] = "INV_Misc_Food_31", [12] = "Spell_Frost_FrostNova",
        [13] = "INV_Drink_12", [14] = "INV_Drink_16", [15] = "INV_Drink_21", [16] = "INV_Misc_Flower_01",
        [17] = "INV_Misc_Flower_03", [18] = "INV_Misc_Food_30", [19] = "INV_Misc_Food_73CinnamonRoll",
        [20] = "INV_Misc_Food_27", [21] = "INV_Misc_Food_104_TundraBerries", [22] = "INV_Misc_Herb_04",
        [23] = "INV_Misc_Food_35", [24] = "INV_Misc_Note_01", [25] = "INV_Drink_15",
        [26] = "Interface\\Buttons\\UI-GroupLoot-Pass-Up",
    },
    cafe = { [1] = "INV_Drink_15", [2] = "INV_Drink_15" },
    reward = { apron = "INV_Chest_Cloth_21", masterApron = "INV_Chest_Cloth_30", goldenApron = "INV_Chest_Cloth_30",
        title = "INV_Crown_01", tips = "INV_Misc_Coin_01", window = "Achievement_Profession_ChefHat",
        shift = "INV_Chest_Cloth_21", tired = "Spell_Nature_Sleep", crown = "INV_Crown_01", speed = "Ability_Rogue_Sprint",
        group = "INV_Misc_GroupNeedMore", patience = "Spell_Holy_BorrowedTime" },
}
Cafe.PATCH_ICONS = {
    family = { C = "BH_Cafe_Coffee", T = "BH_Cafe_Tea", M = "BH_Cafe_Shake" },
    station = { G = "BH_Cafe_Grinder", E = "BH_Cafe_Espresso", K = "BH_Cafe_Kettle", C = "BH_Cafe_ColdBox",
        B = "BH_Cafe_Blender", S = "BH_Cafe_Shelf", V = "BH_Cafe_Counter" },
    cafe = { [1] = "BH_Cafe_Coffee", [2] = "BH_Cafe_Coffee" },
    reward = { shift = "BH_Cafe_Shift", tired = "BH_Cafe_Tired", crown = "BH_Cafe_Crown", speed = "BH_Cafe_Speed" },
}

local patchProbe, patchPresent
-- patch-4 (the café's models and icons) is installed: its icon loads (SetTexture answers nil for a missing file).
function Cafe.PatchPresent()
    if patchPresent == nil then
        patchProbe = patchProbe or UIParent:CreateTexture(nil, "BACKGROUND")
        patchProbe:Hide()
        patchPresent = patchProbe:SetTexture(Cafe.PATCH_PROBE) and true or false
    end
    return patchPresent
end

-- An icon name or path for UI.IconPath / UI.Icon / UI.ItemButton: kind family, station, action, cafe or reward.
function Cafe.Icon(kind, key)
    if Cafe.PatchPresent() then
        local p = Cafe.PATCH_ICONS[kind]
        if p and p[key] then
            return p[key]
        end
    end
    local t = Cafe.ICONS[kind]
    return t and t[key] or "INV_Misc_QuestionMark"
end

function Cafe.IconPath(kind, key)
    local name = Cafe.Icon(kind, key)
    return UI.IconPath(name) or UI.STOCK.question
end

-- The icon of a recipe's family (the drink's own picture).
function Cafe.RecipeIcon(recipeId)
    return Cafe.Icon("family", Cafe.Family(recipeId))
end

-- The stock health bar colours: green above half, yellow from a quarter, red below (always with the seconds too).
function Cafe.PatienceColor(frac)
    frac = tonumber(frac) or 0
    if frac > 0.5 then
        return "00FF00"
    elseif frac >= 0.25 then
        return "FFFF00"
    end
    return "FF0000"
end

Cafe.QUALITY = {
    P = { "Perfect", C.gold }, G = { "Good", C.teal }, S = { "Sloppy", C.orange }, R = { "Ruined", C.red },
    L = { "Customer Left", C.mute },
}
function Cafe.QualityText(q)
    local d = Cafe.QUALITY[q or ""]
    if not d then
        return "Done", C.text
    end
    return d[1], d[2]
end

Cafe.GRADES = { P = { "Perfect", C.gold }, G = { "Good", C.teal }, O = { "Off", C.orange } }

function Cafe.Sound(name)
    if Cafe.Option("cafeSound") and PlaySound then
        PlaySound(name)
    end
end

function Cafe.Motion()
    return Cafe.Option("cafeMotion") and true or false
end

-- A refusal the client can tell by itself, in the error frame like the server's ERR.
function Cafe.Notice(text, r, g, b)
    if UIErrorsFrame then
        UIErrorsFrame:AddMessage(text, r or 1, g or 0.82, b or 0)
    else
        ns.Print(text)
    end
end

------------------------------------------------------------------------------------------------------
-- The café's own confirmation (BleakholdCafeConfirm): the look of the kit's dialog (the stock UI-DialogBox popup
-- backdrop, the dialog-style buttons) on a frame of its own, so the café never moves or closes the kit's shared
-- BleakholdDialog, on which other windows ask their questions. One café question at a time: a new one takes the frame
-- over. owner names whose question it is ("order", "bin"); Cafe.CloseConfirm(owner) closes it only while it still holds
-- that one. It opens where the stock popups stand (Cafe.CONFIRM_HOME); the menu then puts it beside itself.
------------------------------------------------------------------------------------------------------
Cafe.CONFIRM_HOME = { "CENTER", 0, 120 }
Cafe.CONFIRM_W = 340
Cafe.CONFIRM_TEXT_W = Cafe.CONFIRM_W - 40   -- 20 px in from each side
local confirm

local function confirmFrame()
    if confirm then
        return confirm
    end
    local d = CreateFrame("Frame", "BleakholdCafeConfirm", UIParent)
    d:SetSize(Cafe.CONFIRM_W, 136)
    d:SetFrameStrata("DIALOG")
    d:SetToplevel(true)
    d:EnableMouse(true)
    d:SetBackdrop(UI.BACKDROPS.popup)
    d.backdropKind = "popup"
    -- an explicit width, as StaticPopup's text has: the client wraps GetStringHeight at the FontString's own width (or
    -- its unwrapped one), never at an anchored one, so only this sizes the dialog for the lines it draws
    d.text = UI.Text(d, 13, C.text, "body", "CENTER")
    d.text:SetPoint("TOP", d, "TOP", 0, -20)
    d.text:SetWidth(Cafe.CONFIRM_TEXT_W)
    d.ok = UI.Button(d, 128, 21, "Accept", "dialog")
    d.ok:SetPoint("BOTTOMRIGHT", d, "BOTTOM", -6, 16)
    d.cancel = UI.Button(d, 128, 21, "Cancel", "dialog")
    d.cancel:SetPoint("BOTTOMLEFT", d, "BOTTOM", 6, 16)
    d.cancel:SetScript("OnClick", function()
        d:Hide()
    end)
    d:SetScript("OnHide", function(self)
        self.owner = nil
    end)
    d:Hide()
    if UISpecialFrames then
        table.insert(UISpecialFrames, "BleakholdCafeConfirm")
    end
    confirm = d
    return d
end

function Cafe.Confirm(owner, text, onAccept, acceptLabel)
    local d = confirmFrame()
    d.owner = owner
    UI.SetText(d.text, text)
    d.ok:SetLabel(acceptLabel or "Accept")
    d.ok:SetScript("OnClick", function()
        d:Hide()
        if onAccept then
            ns.SafeCall(onAccept)
        end
    end)
    local h = Cafe.CONFIRM_HOME
    d:ClearAllPoints()
    d:SetPoint(h[1], UIParent, h[1], h[2], h[3])
    -- as tall as the text and the buttons (StaticPopup_Resize)
    d:SetHeight(max(100, floor(20 + (d.text:GetStringHeight() or 13) + 14 + 21 + 18 + 0.5)))
    d:Show()
    return d
end

-- the café question of owner (any café question without one), if it is still up
function Cafe.ConfirmShown(owner)
    return (confirm and confirm:IsShown() and (owner == nil or confirm.owner == owner)) and confirm or nil
end

function Cafe.CloseConfirm(owner)
    local d = Cafe.ConfirmShown(owner)
    if d then
        d:Hide()
    end
end

------------------------------------------------------------------------------------------------------
-- Money as the stock SmallMoneyFrame draws it: each amount white with its coin after it (for HUD panels; FontStrings
-- that may hold coins use Cafe.Money). f:SetCopper(copper) lays it out; the frame is as wide as its content.
------------------------------------------------------------------------------------------------------
function Cafe.MoneyFrame(parent, size)
    size = size or 11
    local f = CreateFrame("Frame", nil, parent)
    f:SetSize(1, size + 2)
    f.parts = {}
    for i = 1, 3 do
        local text = UI.Text(f, size, C.text)
        local coin = f:CreateTexture(nil, "ARTWORK")
        coin:SetTexture(COINS[i][2])
        coin:SetSize(size + 1, size + 1)
        f.parts[i] = { text = text, coin = coin }
    end
    function f:SetCopper(copper)
        copper = max(0, floor(tonumber(copper) or 0))
        self.copper = copper
        local x, shown = 0, 0
        for i, c in ipairs(COINS) do
            local n = floor(copper / c[1])
            copper = copper - n * c[1]
            local p = self.parts[i]
            if n > 0 or (i == 3 and shown == 0) then
                shown = shown + 1
                p.text:SetText(i == 1 and U.Commas(n) or tostring(n))
                p.text:ClearAllPoints()
                p.text:SetPoint("LEFT", self, "LEFT", x, 0)
                x = x + ceil(p.text:GetStringWidth() or 0) + 1
                p.coin:ClearAllPoints()
                p.coin:SetPoint("LEFT", self, "LEFT", x, 0)
                x = x + size + 1 + 4
                p.text:Show()
                p.coin:Show()
            else
                p.text:Hide()
                p.coin:Hide()
            end
        end
        self:SetWidth(max(1, x - 4))
    end
    f:SetCopper(0)
    return f
end

------------------------------------------------------------------------------------------------------
-- HUD frames: a saved spot (BleakholdCharDB, like the camp frame's), a mover for AddicatUI's editor mode, the café's
-- HUD scale. Cafe.hud lists them; Cafe.editing is true while the editor shows them with their content as it is.
-- def.anchor(f), optional: places a frame that has no saved spot against another HUD frame (it sets the point and
-- returns true; nil falls back to def.point). t.Anchor() runs it again; not while the mover drags the frame.
------------------------------------------------------------------------------------------------------
Cafe.hud = {}
Cafe.refreshers = {}

function Cafe.Place(f, def)
    local t = { frame = f }
    function t.Saved()
        local pos = ns.cdb.windows[f:GetName()]
        if type(pos) == "table" and type(pos.point) == "string" and type(pos.x) == "number" and type(pos.y) == "number" then
            return pos
        end
    end
    function t.Anchor()
        if t.dragging then
            return
        end
        local pos = t.Saved()
        f:ClearAllPoints()
        if pos then
            f:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, pos.x, pos.y)
        elseif not (def.anchor and def.anchor(f)) then
            f:SetPoint(def.point, UIParent, def.relPoint or def.point, def.x or 0, def.y or 0)
        end
    end
    function t.MoveTo(region, save)
        local point, relPoint, x, y = UI.TopAnchorOf(region)
        if not point then
            return
        end
        t.dragging = not save or nil
        f:ClearAllPoints()
        f:SetPoint(point, UIParent, relPoint, x, y)
        if save then
            ns.cdb.windows[f:GetName()] = { point = point, relPoint = relPoint, x = x, y = y }
        end
    end
    t.Anchor()
    f:SetScale(Cafe.Option("cafeScale"))
    Cafe.hud[#Cafe.hud + 1] = t
    if def.refresh then
        Cafe.refreshers[#Cafe.refreshers + 1] = def.refresh
    end
    UI.AddMover({
        name = def.mover, title = def.title, frame = f,
        begin = function()
            Cafe.editing = true
            Cafe.RefreshAll()
        end,
        finish = function()
            Cafe.editing = nil
            t.dragging = nil
            Cafe.RefreshAll()
        end,
        move = function(region, done)
            t.MoveTo(region, done)
        end,
        reset = function()
            ns.cdb.windows[f:GetName()] = nil
            t.dragging = nil
            t.Anchor()
        end,
        isDefault = function()
            return t.Saved() == nil
        end,
        visible = function()
            return Cafe.Enabled() and true or false
        end,
    })
    return t
end

function Cafe.RefreshAll()
    for _, fn in ipairs(Cafe.refreshers) do
        ns.SafeCall(fn)
    end
end

function Cafe.ApplyScale()
    local s = Cafe.Option("cafeScale")
    for _, t in ipairs(Cafe.hud) do
        t.frame:SetScale(s)
    end
end

ns.On("DB_READY", function()
    for _, t in ipairs(Cafe.hud) do
        t.Anchor()
    end
    Cafe.ApplyScale()
end)

ns.On("CAFE_OPTIONS", function(name)
    if name == "cafeScale" then
        Cafe.ApplyScale()
    end
    Cafe.RefreshAll()
end)

------------------------------------------------------------------------------------------------------
-- Sending: one gate per op a little above the server's interval (CSHIFT and CSTAFF share one, CORDER and CCANCEL
-- another); ERR busy waits a full gap. CREL has no gate: Comm sends it at once, ahead of the queue (Comm.PRIORITY).
-- A click refused by its own gate is never silent: Cafe.Send says "One moment..." for the window ops (the keys' CTAKE
-- and CSTEP stay quiet: a key held down repeats), and returns false, "wait" and the seconds left; Cafe.SendWhenReady
-- sends it once the gate opens instead (the Staff Drink chosen right after End Shift, Cancel right after Order).
------------------------------------------------------------------------------------------------------
Cafe.GAPS = { CSHIFT = 2.25, CSTAFF = 2.25, CTAKE = 0.6, CSTEP = 0.25, CORDER = 2.25, CCANCEL = 2.25 }
local GATE = { CSHIFT = "shift", CSTAFF = "shift", CORDER = "order", CCANCEL = "order", CTAKE = "take", CSTEP = "step" }
local nextAt = {}

local function connected()
    if Comm.outdated then
        Cafe.Notice("Your Bleakhold addon is out of date.", 1, 0.45, 0.4)
        return false
    end
    if not Comm.ready and not Comm.demo then
        Cafe.Notice("Not connected to the realm.", 1, 0.45, 0.4)
        return false
    end
    return true
end

Cafe.WAIT_NOTICE = { CSHIFT = true, CSTAFF = true, CORDER = true, CCANCEL = true }
Cafe.WAIT_TEXT = "One moment..."

local function send(op, quiet, ...)
    if not connected() then
        return false, "offline"
    end
    local gate = GATE[op]
    local now = GetTime()
    if gate and nextAt[gate] and now < nextAt[gate] then
        if not quiet and Cafe.WAIT_NOTICE[op] then
            Cafe.Notice(Cafe.WAIT_TEXT)
        end
        return false, "wait", nextAt[gate] - now
    end
    local ok = Comm.Send(op, ...)
    if ok and gate then
        nextAt[gate] = now + (Cafe.GAPS[op] or 0.25)
    end
    return ok and true or false
end

function Cafe.Send(op, ...)
    return send(op, false, ...)
end

-- Send now, or as soon as the op's gate opens: true when sent (and "queued" when waiting to go). args: the op's fields;
-- still (optional): asked again just before the late send, false drops it (the choice was made moot meanwhile);
-- onFail: the late send did not go out. One waits per op: a later call replaces it.
local waiting = {}
function Cafe.SendWhenReady(op, args, still, onFail)
    args = args or {}
    local ok, why, left = send(op, true, unpack(args))
    if ok or why ~= "wait" then
        return ok
    end
    local token = {}
    waiting[op] = token
    ns.After((left or 0) + 0.05, function()
        if waiting[op] ~= token then
            return
        end
        waiting[op] = nil
        if still and not still() then
            return
        end
        if not send(op, false, unpack(args)) and onFail then
            onFail()
        end
    end)
    return true, "queued"
end

-- forget the gates and the sends waiting on them (leaving demo mode, tests)
function Cafe.ResetGates()
    wipe(nextAt)
    wipe(waiting)
end

ns.On("ERR", function(e)
    if not e or not e.op then
        return
    end
    if e.code == "busy" and GATE[e.op] then
        nextAt[GATE[e.op]] = GetTime() + (Cafe.GAPS[e.op] or 0.25)
    end
    -- an unknown ticket or a step out of sync: the server sends CAFT too; asking makes sure
    if e.code == "cafe_ticket" and e.op ~= "CORDER" then
        Comm.Get("CAFT")
    end
end)

-- Cancel my order (CAFO Q, or F while the owner finishes it). Right after Order its gate is still shut: the cancel goes
-- out once it opens, if the order can still be cancelled then.
local function cancellable(o)
    return o and o.orderId and (o.state == "Q" or o.state == "F") and true or false
end

function Cafe.CancelOrder()
    local o = S.cafeOrder
    if not cancellable(o) then
        return false
    end
    local id = o.orderId
    local ok, how = Cafe.SendWhenReady("CCANCEL", { id }, function()
        return cancellable(S.cafeOrder) and S.cafeOrder.orderId == id
    end)
    if how == "queued" then
        Cafe.Notice(Cafe.WAIT_TEXT)
    end
    return ok
end

function Cafe.StartShift()
    return Cafe.Send("CSHIFT", Cafe.MyCafe(), 1)
end

function Cafe.EndShift()
    return Cafe.Send("CSHIFT", Cafe.CafeId(), 0)
end

-- Combat ended the shift (the server ends it too, section 21): off shift here until a fresh CAFST says 1.
function Cafe.MarkShiftEndedLocally()
    local st = S.cafeState
    if st and st.onShift then
        st.onShift = false
        ns.Fire("STATE", "CAFST")
    end
end

-- From memory is the client's own mode (spec 0.3 #4: no intent tells the server, so CAFP memoryDrinks stays 0): the
-- addon counts each drink served (P, G or S) while it hides the steps, per character in BleakholdCharDB. Demo drinks
-- do not count.
function Cafe.MemoryDrinks()
    return max(0, floor(tonumber(ns.cdb.cafeMemoryDrinks) or 0))
end

ns.On("CAFE_RESULT", function(res)
    local q = res and res.quality
    if (q == "P" or q == "G" or q == "S") and not Comm.demo and Cafe.MemoryMode and Cafe.MemoryMode() then
        ns.cdb.cafeMemoryDrinks = Cafe.MemoryDrinks() + 1
    end
end)

-- what the server's CAFUI opens (the gossip of the café's staff). CAFUI shift comes once the owner's "I'd like to work a
-- barista shift" has started the shift: the barista bar, the ticket and the strip showing up are the answer, and the
-- 860 x 585 window (HIGH strata, centred) would cover them as the bar says where to walk, so it stays shut and the
-- shift's start is told where the stock UI tells such things.
Cafe.UI_KEYS = { menu = "cafemenu", shift = "cafeshift", board = "cafeboard", help = "cafehelp" }
Cafe.SHIFT_STARTED_TEXT = "Your shift has started."
ns.On("CAFE_UI", function(what)
    local key = Cafe.UI_KEYS[what or ""]
    if not key or not Cafe.Enabled() then
        return
    end
    if what == "shift" then
        Cafe.Notice(Cafe.SHIFT_STARTED_TEXT)
        return
    end
    UI.Open(key)
end)

------------------------------------------------------------------------------------------------------
-- The orb
------------------------------------------------------------------------------------------------------
Cafe.OPEN_TEXT = { [0] = "Off", "Open", "Paused: danger nearby", "Not open yet", "Closed for safety" }

local function rushText(st, sec)
    if st == 2 then
        return "Morning Rush" .. Cafe.DOT .. U.Clock(ceil(sec or 0)) .. " left"
    elseif st == 1 then
        return "Morning Rush in " .. U.Clock(ceil(sec or 0))
    end
end
Cafe.RushText = rushText

function Cafe.OrbLines()
    local lines = { Cafe.NAME }
    local any = false
    for _, id in ipairs({ 1, 2 }) do
        local c = S.cafes[id]
        if c then
            any = true
            lines[#lines + 1] = { U.Safe(Cafe.CafeName(id)) .. ": " .. (Cafe.OPEN_TEXT[c.open] or "Off"),
                c.open == 1 and C.teal or (c.open == 2 and C.red or C.dim) }
            lines[#lines + 1] = { c.baristas .. (c.baristas == 1 and " barista" or " baristas") .. " on shift" .. Cafe.DOT
                .. c.queueLen .. (c.queueLen == 1 and " order" or " orders") .. " waiting", C.mid }
            local r = rushText(c.rushState, Cafe.RushLeft(c, c.cafeId))
            if r then
                lines[#lines + 1] = { r, C.orange }
            end
        end
    end
    if not any then
        lines[#lines + 1] = { "Coffee, tea and milkshakes in Stormwind and Orgrimmar.", C.mid, true }
    end
    if Cafe.OnShift() then
        lines[#lines + 1] = { "You are on shift.", C.teal }
    end
    lines[#lines + 1] = { "Click to open", C.mute }
    return lines
end

if ns.Orbs and ns.Orbs.Add then
    Cafe.orb = ns.Orbs.Add({
        key = "cafe", glyph = "INV_Drink_15", title = Cafe.NAME, angle = 25,
        available = Cafe.Enabled,
        lines = Cafe.OrbLines,
        onClick = function()
            UI.Open("cafe", true)
        end,
    })
end

-- a toast to the café (TOAST target cafe) shows the café's cup
if ns.Toast and ns.Toast.TARGET_GLYPHS then
    ns.Toast.TARGET_GLYPHS.cafe = "INV_Drink_15"
end

ns.On("HELLO", function()
    if ns.Orbs and ns.Orbs.Refresh then
        ns.Orbs.Refresh()
    end
end)

------------------------------------------------------------------------------------------------------
-- /bh cafe
------------------------------------------------------------------------------------------------------
local ONOFF = { on = true, ["1"] = true, off = false, ["0"] = false }
local TOGGLES = { sound = "cafeSound", motion = "cafeMotion", memory = "cafeMemory", autoselect = "cafeTicketAutoSelect" }

function Cafe.Command(args)
    args = strtrim and strtrim(args or "") or (args or "")
    local cmd, rest = args:match("^(%S*)%s*(.-)$")
    cmd = (cmd or ""):lower()
    if cmd == "" then
        if not UI.Open("cafe", true) then
            ns.Print("the caf" .. Cafe.E .. " window is not available.")
        end
    elseif cmd == "menu" then
        -- the customer's menu (also the café window's Order a Drink)
        if not UI.Open("cafemenu") then
            ns.Print("the caf" .. Cafe.E .. " menu is not available.")
        end
    elseif cmd == "keys" then
        if rest == "" then
            ns.Print("caf" .. Cafe.E .. " keys: " .. table.concat(Cafe.Keys(), ","))
            return
        end
        local keys, why = Cafe.ParseKeys(rest)
        if not keys then
            ns.Print("caf" .. Cafe.E .. " keys not changed: " .. why)
            return
        end
        Cafe.SetOption("cafeKeys", table.concat(keys, ","))
        ns.Fire("CAFE_KEYS")
        ns.Print("caf" .. Cafe.E .. " keys: " .. table.concat(keys, ","))
    elseif cmd == "scale" then
        local v = tonumber(rest)
        if not v then
            ns.Print("caf" .. Cafe.E .. " HUD scale: " .. Cafe.Option("cafeScale") .. " (0.8 to 1.4)")
            return
        end
        Cafe.SetOption("cafeScale", U.Clamp(v, Cafe.SCALE_MIN, Cafe.SCALE_MAX))
        ns.Print("caf" .. Cafe.E .. " HUD scale: " .. Cafe.Option("cafeScale"))
    elseif TOGGLES[cmd] then
        local key = TOGGLES[cmd]
        local v = ONOFF[(rest or ""):lower()]
        if v == nil then
            v = not Cafe.Option(key)
        end
        Cafe.SetOption(key, v)
        ns.Print("caf" .. Cafe.E .. " " .. cmd .. ": " .. (v and "on" or "off"))
        -- from memory needs barista level 6 (CAFST flag 2): the option is kept and takes effect then
        local st = S.cafeState
        if key == "cafeMemory" and v and st and bit.band(st.flags or 0, 2) == 0 then
            ns.Print("From memory opens at barista level 6; it turns on then.")
        end
    elseif cmd == "model" then
        -- the dev viewer of CafeWindow.lua
        ns.Fire("CAFE_MODEL", rest)
    else
        ns.Print("usage: /bh cafe [menu | keys 1,2,3,4,5,6,7,8 | scale 0.8-1.4 | sound | motion | memory | autoselect | "
            .. "model <name>]")
    end
end

ns.AddCommand("cafe", "the caf\195\169: /bh cafe [menu|keys|scale|sound|motion|memory|autoselect|model <name>]",
    Cafe.Command)

------------------------------------------------------------------------------------------------------
-- Demo mode (/bh demo): a stand-in for the server's café. Demo.lua hands every intent here first; GETs of café
-- topics are answered (and passed on, for the other topics of the same GET), the café's intents are answered here.
------------------------------------------------------------------------------------------------------
local demo
local demoRun = 0

local function demoPush(op, records)
    if ns.Demo and Comm.demo then
        ns.Demo.Push(op, records)
    end
end

local function demoAfter(sec, fn)
    local run = demoRun
    ns.After(sec, function()
        if Comm.demo and demo and run == demoRun then
            fn()
        end
    end)
end

local DEMO_NAMES = { "Brenna", "Sergeant Corwin Ashgrove", "Grandma Hester", "Night Watch Guard", "Little Wendel",
    "Private Tilly Dunmore", "Tessa Furrow", "Keldrin Coalbrand" }

local function demoReset()
    demoRun = demoRun + 1
    demo = {
        onShift = false, station = nil, level = 6, xp = 1890, drinks = 0, perfects = 0, streak = 0, tips = 0, shiftXp = 0,
        shiftStart = GetTime(), nextTicket = 41, nextOrder = 1209, tickets = {}, step = nil, maxTickets = 2,
        queue = {
            { 1209, "P", 103, "Brenna", 25000, 25000, "W", "", 0 },
            { 1207, "N", 101, "Sergeant Corwin Ashgrove", 45000, 48000, "W", "", 0 },
            { 1211, "N", 108, "Grandma Hester", 52000, 60000, "W", "", 0 },
            { 1212, "G", 102, "Night Watch Guard", 38000, 51000, "W", "", 0, 7 },
            { 1213, "N", 107, "Lady Seraphine Ravenmoor", 50000, 54000, "W", "", 9 },
        },
        order = nil, buffs = { 1320, "", 1800, 1, 1 }, rush = { 1, 180 },
    }
end
Cafe.DemoReset = demoReset

local function demoCafes()
    local r = demo.rush
    demoPush("CAFE", { { 1, 1, demo.onShift and 2 or 1, #demo.queue, r[1], r[2], 45 }, { 2, 1, 0, 0, 1, 180, 60 } })
end

local function demoState()
    local d = demo
    local nextXp = Cafe.Level(d.level + 1)
    local rec = { d.onShift and 1 or 0, d.onShift and 1 or 0, d.level, d.xp, (Cafe.Level(d.level) or {}).xp or 0,
        nextXp and nextXp.xp or "" }
    if d.onShift then
        rec[1] = 1
        local flags = 2 + (d.flags or 0)
        local list = { floor(GetTime() - d.shiftStart), d.drinks, d.perfects, d.streak, d.tips, d.shiftXp, d.station or "",
            d.station or d.near or "", d.station and 3 or 40, d.maxTickets, 2400, flags, d.warnSec or "" }
        for _, v in ipairs(list) do
            rec[#rec + 1] = v
        end
    end
    local recs = { rec, { "D", 210 + d.shiftXp, 450, 450, 30000 + d.tips, 180000, 180 + d.drinks * 12, 400, 14 + d.drinks } }
    if d.onShift then
        recs[#recs + 1] = { "R", d.rush[1], d.rush[2], 41, 60, d.drinks }
    end
    demoPush("CAFST", recs)
end

local function demoQueue()
    local d = demo
    local recs = { { 1, #d.queue, 6, 2, "" } }
    for i = 1, min(8, #d.queue) do
        recs[#recs + 1] = d.queue[i]
    end
    demoPush("CAFQ", recs)
end

local function ticketSteps(t)
    local r = Cafe.Recipe(t.recipeId)
    local list = {}
    for i, a in ipairs(r and r.steps or {}) do
        list[i] = { a, t.grades[i] or "N" }
    end
    return list
end

local function demoTickets()
    local recs = {}
    for _, t in ipairs(demo.tickets) do
        local inHand = t.next > 1 and 1 or 0
        recs[#recs + 1] = { t.id, t.orderId, t.recipeId, t.kind, t.customer, max(0, floor(t.patience - (GetTime() - t.at) * 1000)),
            t.patienceMax, t.next, inHand, t.line or "", ticketSteps(t), t.tip }
    end
    if #recs == 0 then
        recs[1] = { 0 }
    end
    demoPush("CAFT", recs)
end

local function demoTicket(id)
    for i, t in ipairs(demo.tickets) do
        if t.id == id then
            return t, i
        end
    end
end

local function demoErr(op, code, text)
    demoPush("ERR", { { op, Comm.lastSeq or "", code, text } })
end

local DEMO_LINES = { [1207] = "Cathedral Black. No sugar, no chatter, no delay.",
    [1211] = "A nice green tea, dearie. Take your time; I've nowhere to be." }

local function demoTake(orderId)
    local d = demo
    if not d.onShift then
        return demoErr("CTAKE", "cafe_shift", "You are not on shift.")
    end
    if d.station ~= "V" then
        return demoErr("CTAKE", "cafe_station", "Take orders at the serving counter.")
    end
    if #d.tickets >= d.maxTickets then
        return demoErr("CTAKE", "cafe_full", "Your hands are full: finish a ticket first.")
    end
    local pick
    for i, row in ipairs(d.queue) do
        if row[7] == "W" and row[9] == 0 and (orderId == 0 or row[1] == orderId) then
            pick = i
            break
        end
    end
    if not pick then
        return demoErr("CTAKE", "cafe_taken", "That order is taken already.")
    end
    local row = table.remove(d.queue, pick)
    local r = Cafe.Recipe(row[3])
    local lines = r and #r.steps or 4
    local t = { id = d.nextTicket, orderId = row[1], recipeId = row[3], kind = row[2], customer = row[4], next = 1, grades = {},
        patience = (30 + 6 * lines) * 1000, patienceMax = (30 + 6 * lines) * 1000, at = GetTime(), line = DEMO_LINES[row[1]],
        tip = row[2] == "P" and 2100 or 400 }
    d.nextTicket = d.nextTicket + 1
    d.tickets[#d.tickets + 1] = t
    demoTickets()
    demoQueue()
end

local function demoResult(t)
    local timedOff, allPerfect = false, true
    local r = Cafe.Recipe(t.recipeId)
    for i, a in ipairs(r and r.steps or {}) do
        local act = Cafe.Action(a)
        local g = t.grades[i]
        if act and act.timed then
            if g ~= "P" then
                allPerfect = false
            end
            if g == "O" then
                timedOff = true
            end
        end
    end
    local q = (allPerfect and "P") or (timedOff and "S") or "G"
    local d = demo
    local xp = q == "P" and 27 or (q == "G" and 18 or 9)
    d.drinks, d.xp, d.shiftXp, d.tips = d.drinks + 1, d.xp + xp, d.shiftXp + xp, d.tips + t.tip
    d.streak = q == "P" and d.streak + 1 or 0
    d.perfects = d.perfects + (q == "P" and 1 or 0)
    local _, i = demoTicket(t.id)
    table.remove(d.tickets, i)
    demoPush("CAFRES", { { t.id, t.recipeId, q, xp, t.tip, q == "P" and 22 or 12, d.streak, 0, d.level, t.customer,
        t.kind == "P" and "" or "Hot and bitter. Like my shift.", 0 } })
    demoTickets()
    demoState()
    -- a new customer joins the queue
    d.nextOrder = d.nextOrder + 10
    d.queue[#d.queue + 1] = { d.nextOrder, "N", 109, DEMO_NAMES[(d.nextOrder % #DEMO_NAMES) + 1], 60000, 60000, "W", "", 0 }
    demoQueue()
end

local function demoFinishStep(t, idx, action, grade)
    local d = demo
    d.step = nil
    t.grades[idx] = grade
    t.next = idx + 1
    demoPush("CAFEV", { { t.id, idx, action, "D", (Cafe.Action(action) or {}).durMs or 1000, "", "", grade, t.next } })
    if action == 25 then
        demoResult(t)
    else
        demoTickets()
    end
end

local function demoStep(ticketId, idx, action)
    local d = demo
    local t = demoTicket(ticketId)
    if not d.onShift then
        return demoErr("CSTEP", "cafe_shift", "You are not on shift.")
    end
    if not t or idx ~= t.next then
        demoErr("CSTEP", "cafe_ticket", "That ticket moved on.")
        return demoTickets()
    end
    if d.step then
        return demoErr("CSTEP", "cafe_busy", "A step is running.")
    end
    for _, o in ipairs(d.tickets) do
        if o ~= t and o.next > 1 then
            return demoErr("CSTEP", "cafe_hands", "Finish or bin the drink in your hands first.")
        end
    end
    local act = Cafe.Action(action)
    if not act then
        return
    end
    if act.station ~= d.station then
        return demoErr("CSTEP", "cafe_station", "Walk to the " .. Cafe.StationName(act.station) .. " first.")
    end
    if action == 26 then
        t.next, t.grades = 1, {}
        d.streak = 0
        demoPush("CAFEV", { { t.id, idx, action, "B", "", "", "", "", 1 } })
        return demoTickets()
    end
    local r = Cafe.Recipe(t.recipeId)
    if not r or r.steps[idx] ~= action then
        t.next, t.grades = 1, {}
        d.streak = 0
        demoPush("CAFEV", { { t.id, idx, action, "X", "", "", "", "", 1 } })
        return demoTickets()
    end
    local dur = act.durMs or 1000
    if act.timed then
        local g = act.gold or { 700, 850 }
        local lo, hi = floor(dur * g[1] / 1000) - 50, floor(dur * g[2] / 1000) - 40
        d.step = { ticketId = t.id, idx = idx, action = action, lo = lo, hi = hi, dur = dur, at = GetTime() }
        demoPush("CAFEV", { { t.id, idx, action, "S", dur, lo, hi, "", idx } })
        local step = d.step
        demoAfter(dur / 1000 + 0.3, function()
            if d.step == step then
                demoFinishStep(t, idx, action, "O")
            end
        end)
    else
        d.step = { ticketId = t.id, idx = idx, action = action, dur = dur, at = GetTime() }
        demoPush("CAFEV", { { t.id, idx, action, "S", dur, "", "", "", idx } })
        local step = d.step
        demoAfter(dur / 1000, function()
            if d.step == step then
                demoFinishStep(t, idx, action, "P")
            end
        end)
    end
end

local function demoRelease(ticketId, idx, ms)
    local s = demo.step
    if not s or s.ticketId ~= ticketId or s.idx ~= idx or not s.lo then
        return demoErr("CREL", "cafe_ticket", "No step to release.")
    end
    local band = s.dur * 0.1
    local grade = (ms >= s.lo and ms <= s.hi) and "P" or ((ms >= s.lo - band and ms <= s.hi + band) and "G" or "O")
    demoFinishStep(demoTicket(ticketId), idx, s.action, grade)
end

local function demoOrderPush()
    local o = demo.order
    if not o then
        return demoPush("CAFO", { { 0 } })
    end
    demoPush("CAFO", { { o.id, o.cafe or 1, o.recipeId, o.state, o.state == "Q" and 1 or "", o.state == "M" and "Aldric" or "",
        o.done or 0, o.steps, o.left or "", o.price, o.tip } })
end

local function demoOrder(cafeId, recipeId, tipPct)
    local r = Cafe.Recipe(recipeId)
    if not r then
        return demoErr("CORDER", "cafe_ticket", "That drink is not on this menu.")
    end
    if demo.order and demo.order.state ~= "D" and demo.order.state ~= "X" and demo.order.state ~= "E" then
        return demoErr("CORDER", "cafe_order", "You already have an order waiting.")
    end
    local price = Cafe.Price(recipeId)
    demo.order = { id = 1210, cafe = cafeId or 1, recipeId = recipeId, state = "Q", steps = #r.steps, price = price,
        tip = floor(price * (tipPct or 0) / 100) }
    local o = demo.order
    demoOrderPush()
    local plan = { { 3, "M", 0 }, { 7, "M", 2 }, { 11, "M", 4 }, { 14, "R", #r.steps, 180 }, { 19, "D", 0 } }
    for _, p in ipairs(plan) do
        demoAfter(p[1], function()
            if demo.order == o and o.state ~= "X" then
                o.state, o.done, o.left = p[2], p[3], p[4]
                demoOrderPush()
                -- who works at the bar: Aldric on the order's steps, then nobody
                if p[2] == "M" then
                    local a = r.steps[p[3] + 1] or 25
                    local act = Cafe.Action(a)
                    demoPush("CAFAT", { { o.cafe or 1, 1 }, { "Aldric", a, 0, act and act.durMs or 1000, act and act.timed and "H" or "T",
                        p[3] + 1, #r.steps } })
                elseif p[2] == "R" then
                    demoPush("CAFAT", { { 1, 0 } })
                end
                if p[2] == "D" then
                    demo.buffs = { 1800, demo.buffs[2], demo.buffs[3], demo.buffs[4], 1 }
                    demoPush("CAFBF", { demo.buffs })
                end
            end
        end)
    end
end

local function demoMenu(cafeId)
    cafeId = cafeId or Cafe.MyCafe()
    local recs = { { cafeId, 1, demo.onShift and 2 or 1, 45, demo.order and demo.order.id or 0, 2, 12, 1, "" } }
    local level = demo.level
    for _, r in ipairs(Cafe.Recipes(cafeId)) do
        recs[#recs + 1] = { r.id, Cafe.Price(r.id), r.unlockLevel <= level and 1 or 0,
            (r.family == "C" and ((UnitLevel and UnitLevel("player")) or 80) >= 80) and 0 or 1 }
    end
    demoPush("CAFM", recs)
end

local function demoProfile()
    demoPush("CAFP", { { demo.level, demo.xp, 1600, 2320, 412 + demo.drinks, 301 + demo.perfects, 0, 14, 5120, 0, 1 },
        { "W", 2964, 1, 2, 1830, 96, 790, 4, 1 }, { "L", 2963, 1, "Brenna", 2480 }, { "L", 2963, 2, "Morgra", 1990 } })
end

local function demoBoard(week, cafeId, page)
    local now = time()
    local wk = (week and week > 0) and week or 2964
    demoPush("LB", { { "C", wk, cafeId, 0, page or 1, 1 },
        { 1, cafeId, 2310, 812, now - 3600, { { "Brenna", 2 } }, "142 drinks" },
        { 2, cafeId, 1830, 790, now - 7200, { { ns.PlayerName() or "Aldric", 1 } }, "96 drinks" },
        { 3, cafeId, 1640, 701, now - 9000, { { "Dalia", 8 } }, "88 drinks" },
        { 4, cafeId, 1205, 655, now - 9900, { { "Korrin", 4 } }, "71 drinks" } })
    demoPush("LBME", { { "C", 2, 40, 1830, cafeId, 790, 792, "96 drinks" } })
end

-- The café's answer to a demo intent; true when it was the café's (nothing else answers it).
function Cafe.DemoRespond(op, recs)
    local f = recs[1] or {}
    if op == "HELLO" then
        if not demo then
            demoReset()
        end
        return false
    end
    if not demo then
        demoReset()
    end
    if op == "GET" then
        for _, r in ipairs(recs) do
            local topic = r[1]
            if topic == "CAFE" then
                demoCafes()
            elseif topic == "CAFST" then
                demoState()
            elseif topic == "CAFQ" and demo.onShift then
                demoQueue()
            elseif topic == "CAFT" and demo.onShift then
                demoTickets()
            elseif topic == "CAFM" then
                demoMenu(tonumber(r[2]))
            elseif topic == "CAFO" then
                demoOrderPush()
            elseif topic == "CAFP" then
                demoProfile()
            elseif topic == "CAFBF" then
                demoPush("CAFBF", { demo.buffs })
            end
        end
        return false
    elseif op == "CSHIFT" then
        if f[2] == "1" then
            if demo.onShift then
                demoErr("CSHIFT", "cafe_account", "You are on a shift already.")
                return true
            end
            demo.onShift, demo.station, demo.shiftStart = true, "V", GetTime()
            demo.drinks, demo.perfects, demo.streak, demo.tips, demo.shiftXp = 0, 0, 0, 0, 0
            demoState()
            demoQueue()
            demoTickets()
            demoCafes()
        else
            if not demo.onShift then
                demoErr("CSHIFT", "cafe_shift", "You are not on shift.")
                return true
            end
            local d = demo
            d.onShift, d.tickets, d.step = false, {}, nil
            demoPush("CAFSUM", { { 1, "E", floor(GetTime() - d.shiftStart), d.drinks, d.perfects, d.tips, d.shiftXp, 0,
                d.drinks * 18, d.streak, d.drinks >= 10 and 1 or 0 } })
            demoState()
            demoCafes()
        end
        return true
    elseif op == "CTAKE" then
        demoTake(tonumber(f[1]) or 0)
        return true
    elseif op == "CSTEP" then
        demoStep(tonumber(f[1]), tonumber(f[2]), tonumber(f[3]))
        return true
    elseif op == "CREL" then
        demoRelease(tonumber(f[1]), tonumber(f[2]), tonumber(f[3]) or 0)
        return true
    elseif op == "CORDER" then
        demoOrder(tonumber(f[1]), tonumber(f[2]), tonumber(f[3]))
        return true
    elseif op == "CCANCEL" then
        local o = demo.order
        if o and (o.state == "Q" or o.state == "F") then
            o.state = "X"
            demoOrderPush()
            demoAfter(5, function()
                if demo.order == o then
                    demo.order = nil
                    demoOrderPush()
                end
            end)
        else
            demoErr("CCANCEL", "cafe_order", "That order can no longer be cancelled.")
        end
        return true
    elseif op == "CSTAFF" then
        demoErr("CSTAFF", "cafe_staff", "No staff drink for you today.")
        return true
    elseif op == "LBQ" and f[1] == "C" then
        demoBoard(tonumber(f[2]), tonumber(f[3]) or 1, tonumber(f[5]))
        return true
    end
    return false
end

-- The demo server moves the barista (the real server reads the player's position): station letter or nil (away).
function Cafe.DemoWalk(station)
    if not (Comm.demo and demo) then
        return
    end
    demo.station = station
    demoState()
end

-- /bh demo cafe: a 60 s shift played through the bar's own buttons (Cafe.Press) and the demo server above: the
-- counter, a Perfect drink (taps and two timed steps released in the gold), a late release, a ruined drink, a customer
-- order, the shift summary.
function Cafe.DemoShift()
    if not Comm.demo then
        return
    end
    if not demo then
        demoReset()
    end
    local press = function(slot)
        return function()
            if Cafe.Press then
                Cafe.Press(slot)
            end
        end
    end
    local walk = function(st)
        return function()
            Cafe.DemoWalk(st)
        end
    end
    -- press a timed step's key, then press it again `at` seconds after its CAFEV S arrived
    local function hold(slot, at)
        return function()
            press(slot)()
            local tries = 0
            local function wait()
                local cs = S.cafeStep
                if cs and cs.event == "S" and GetTime() - cs.recvAt < 0.5 then
                    demoAfter(max(0, at - (GetTime() - cs.recvAt)), press(slot))
                elseif tries < 20 then
                    tries = tries + 1
                    demoAfter(0.05, wait)
                end
            end
            demoAfter(0.05, wait)
        end
    end
    local script = {
        { 0.5, function() Cafe.StartShift() end },
        { 2.5, press(1) },                                   -- Take Order: Brenna's Goldshire Honey Cappuccino
        { 4, walk("G") }, { 5, press(1) },                   -- Grind Beans (a tap)
        { 7.5, walk("E") }, { 8.5, hold(1, 2.3) },          -- Pull Shot, released in the gold
        { 12.5, hold(4, 0.95) },                             -- Froth Foam, in the gold
        { 15, walk("S") }, { 16, press(1) },                 -- Honey
        { 18, walk("V") }, { 19, press(2) },                 -- Serve: Perfect
        { 22, press(1) },                                    -- the sergeant's Cathedral Black
        { 24, walk("G") }, { 25, press(1) },
        { 27.5, walk("E") }, { 28.5, hold(1, 2.95) },        -- released late: Off
        { 33, press(3) },                                    -- Steam Milk where Hot Water belongs: ruined
        { 36, walk(nil) },                                   -- away from the stations
        { 36.5, function()                                   -- the owner at the kettle for the house
            demoPush("CAFAT", { { 1, 1 }, { "Rosalind Thornbury", 7, 0, 2000, "T", 1, 4 } })
        end },
        { 39, function() demoPush("CAFAT", { { 1, 0 } }) end },
        { 39, walk("G") }, { 40, press(1) },
        { 42.5, walk("E") }, { 43.5, hold(1, 2.65) },        -- just past the gold: Good
        { 47.5, press(2) },                                  -- Hot Water
        { 50, walk("V") }, { 51, press(2) },                 -- Serve: Good (the ruin cleared the earlier Off)
        { 56, function() Cafe.EndShift() end },
    }
    for _, s in ipairs(script) do
        demoAfter(s[1], s[2])
    end
end

-- Demo mode ended (Demo.Stop): its state, selections and gates are gone; the frames hide and the keys come free.
function Cafe.Reset()
    selectedTicket, selectedOrder = nil, nil
    knownTickets = {}
    wipe(pausedAt)
    wipe(nextAt)
    demo = nil
    demoRun = demoRun + 1
    ns.Fire("CAFE_RESET")
    Cafe.RefreshAll()
end
