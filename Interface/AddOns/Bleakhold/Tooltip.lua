-- Bleakhold: item tooltip lines. Legacy set pieces get their era, where they drop and whether the look
-- is collected; the player's own keystone, hovered in the bags or the bank, gets its dungeon, level, affixes and mode.
-- The item's own lines (stats, set bonus) are left untouched.
--
-- Every keystone is the same item (KEY keystoneItemId, BHMP::ITEM_KEYSTONE): its dungeon and level live on the
-- server, for its owner only (bh_mplus.cpp SyncKeyItem gives a plain item). So the keystone block is the viewer's own
-- key, and only where the item is the viewer's: a bag slot (GameTooltip:SetBagItem) or a bank slot
-- (SetInventoryItem("player", ...)). Anywhere else (a chat link in ItemRefTooltip, a comparison, another addon's
-- SetHyperlink) the keystone could be anyone's, and the tooltip says so in one dim line.
local ADDON, ns = ...
local U, UI, Data = ns.U, ns.UI, ns.Data
local C = UI.C

local Tooltip = {}
ns.Tooltip = Tooltip

Tooltip.LINK_NOTE = "A keystone link does not show its dungeon and level."

local function itemId(link)
    if type(link) ~= "string" then
        return nil
    end
    return tonumber(link:match("item:(%d+)"))
end
Tooltip.ItemId = itemId

local function joinAnd(list)
    local n = #list
    if n == 0 then
        return ""
    elseif n == 1 then
        return list[1]
    end
    return table.concat(list, ", ", 1, n - 1) .. " and " .. list[n]
end
Tooltip.JoinAnd = joinAnd

-- Lines for an item id: { {text, colorHex, wrap}, ... } (text already safe for display). The keystone's are
-- Tooltip.KeyLines, added by the bag and bank hooks only.
function Tooltip.Lines(id)
    local lines = {}
    local e = ns.S.lidx and ns.S.lidx[id]
    if e then
        local tier = ns.Def("L", e.tier) or {}
        local eraName = ns.DefName("E", tier.eraId, tier.label or "Legacy")
        lines[#lines + 1] = { " " }
        lines[#lines + 1] = { "Raid Legacy - " .. U.Safe(eraName) .. " era", C.goldPale }
        local names = {}
        for _, d in ipairs(tier.sources or {}) do
            names[#names + 1] = U.Safe(ns.DungeonName(d))
        end
        if #names > 0 then
            local band = (tier.lvlMin and tier.lvlMax) and (" (" .. tier.lvlMin .. "-" .. tier.lvlMax .. ")") or ""
            lines[#lines + 1] = { "Drops in " .. joinAnd(names) .. band, C.dim, true }
        end
        if e.collected then
            lines[#lines + 1] = { "Look collected for your account", C.teal }
        else
            lines[#lines + 1] = { "Look not collected", C.mute }
        end
    end
    if ns.S.cases and ns.S.cases[id] then
        lines[#lines + 1] = { " " }
        lines[#lines + 1] = { "Case: right-click to see what it holds and unlock it", C.epic, true }
    end
    return lines
end

-- An affix's name by the server's id (ns.Keys.AffixInfo: the built-in DEF A of Data.lua numbers some differently).
local function affixName(id)
    local K = ns.Keys
    if K and K.AffixInfo then
        return (K.AffixInfo(id))
    end
    return ns.AffixNames({ id })[1]
end

-- KEY mode 1: the player's dungeon difficulty is Heroic, where no keystone starts (StartRun and the right-click refuse
-- it: "Mythic 0 and keystones run on Normal difficulty"; Mythic mode is Normal difficulty too).
Tooltip.KEY_MODE_HEROIC = 1
-- What the player can do about it: only the group leader (or a solo player) sets the dungeon difficulty, and only
-- outside dungeons (SetDifficulty, the bridge's KMODE; ns.Keys.DifficultyBlock): a member is not told to change it.
Tooltip.HEROIC_NOTE = "Keystones run on Normal or Mythic, not Heroic: change it before you enter."
Tooltip.HEROIC_NOTE_INSIDE = "Keystones run on Normal or Mythic, not Heroic: leave the dungeon to change it."
Tooltip.HEROIC_NOTE_MEMBER = "Keystones run on Normal or Mythic, not Heroic: your group leader sets the dungeon mode."

function Tooltip.HeroicNote()
    local K = ns.Keys
    if K and K.LeadsGroup and not K.LeadsGroup() then
        return Tooltip.HEROIC_NOTE_MEMBER
    end
    if IsInInstance and IsInInstance() then
        return Tooltip.HEROIC_NOTE_INSIDE
    end
    return Tooltip.HEROIC_NOTE
end

-- The player's keystone (KEY): "<dungeon> +level", "Run under way" during the player's own run (ns.Keys.OwnRun: the
-- run's level; whose run it is comes from the keys the server sends, not from who leads now), the affixes, the dungeon
-- mode (orange with the server's rule on Heroic, worded by what the player can do); {} without a keystone.
function Tooltip.KeyLines()
    local key = ns.S.key
    if not (key and key.hasKey) then
        return {}
    end
    local K = ns.Keys
    local run = K and K.OwnRun and K.OwnRun()
    local level = run and run.level or key.level or 0
    local lines = { { " " }, { U.Safe(ns.DungeonName(key.dungeonId)) .. " +" .. level, C.goldPale } }
    if run then
        lines[#lines + 1] = { "Run under way", C.gold }
    end
    local affixes = {}
    for _, id in ipairs(key.affixes or {}) do
        local name = affixName(id)
        if name then
            affixes[#affixes + 1] = name
        end
    end
    if #affixes > 0 then
        lines[#lines + 1] = { "Affixes: " .. U.Safe(table.concat(affixes, ", ")), C.mid, true }
    end
    local heroic = key.mode == Tooltip.KEY_MODE_HEROIC
    lines[#lines + 1] = { "Dungeon mode: " .. (Data.keyModes[key.mode] or "Normal"), heroic and C.orange or C.dim }
    if heroic then
        lines[#lines + 1] = { Tooltip.HeroicNote(), C.orange, true }
    end
    if key.depleted and not run then
        lines[#lines + 1] = { "Depleted", C.red }
    end
    return lines
end

-- Whether an item id is the keystone: the KEY's keystoneItemId, else the server's item (ns.Keys.KEY_ITEM).
function Tooltip.IsKeystone(id)
    if not id then
        return false
    end
    local key, K = ns.S.key, ns.Keys
    return (key and key.itemId == id) or (K and K.KEY_ITEM == id) or false
end

local function addLines(tt, lines)
    if #lines == 0 then
        return
    end
    for _, l in ipairs(lines) do
        local r, g, b = UI.Rgb(l[2] or C.mid)
        tt:AddLine(l[1], r, g, b, l[3] and true or false)
    end
    tt:Show()
end

local function onSetItem(tt)
    local _, link = tt:GetItem()
    local id = itemId(link)
    if not id or tt.bleakholdItem == id then
        return
    end
    tt.bleakholdItem = id
    addLines(tt, Tooltip.Lines(id))
end

-- The player's own keystone, in a bag or bank slot: its block, once per setting of the tooltip (the bags set it
-- again on every update; OnTooltipCleared lets the next setting add it again).
local function onOwnItem(tt)
    if tt.bleakholdKey then
        return
    end
    local _, link = tt:GetItem()
    local key = ns.S.key
    local id = itemId(link)
    if not (id and key and key.hasKey and key.itemId == id) then
        return
    end
    tt.bleakholdKey = true
    addLines(tt, Tooltip.KeyLines())
end

-- A keystone seen anywhere else: whose it is, and so its dungeon and level, is not on the item.
local function onLink(tt)
    if tt.bleakholdKey then
        return
    end
    local _, link = tt:GetItem()
    if not Tooltip.IsKeystone(itemId(link)) then
        return
    end
    tt.bleakholdKey = true
    addLines(tt, { { Tooltip.LINK_NOTE, C.dim, true } })
end

local function onCleared(tt)
    tt.bleakholdItem = nil
    tt.bleakholdKey = nil
end

function Tooltip.Hook(tt)
    if not (tt and tt.HookScript) or tt.bleakholdHooked then
        return
    end
    tt.bleakholdHooked = true
    tt:HookScript("OnTooltipSetItem", onSetItem)
    tt:HookScript("OnTooltipCleared", onCleared)
    -- post-hooks: they run after the item's own OnTooltipSetItem; a missing method must not break the load
    if tt.SetBagItem then
        hooksecurefunc(tt, "SetBagItem", function(self)
            onOwnItem(self)
        end)
    end
    if tt.SetInventoryItem then
        -- the bank's own slots; a unit's worn items (an inspect, a party member) are not the player's keystone
        hooksecurefunc(tt, "SetInventoryItem", function(self, unit)
            if unit == "player" then
                onOwnItem(self)
            end
        end)
    end
    if tt.SetHyperlink then
        hooksecurefunc(tt, "SetHyperlink", function(self)
            onLink(self)
        end)
    end
    if tt.SetHyperlinkCompareItem then
        hooksecurefunc(tt, "SetHyperlinkCompareItem", function(self)
            onLink(self)
        end)
    end
end

Tooltip.Hook(GameTooltip)
Tooltip.Hook(ItemRefTooltip)
Tooltip.Hook(ShoppingTooltip1)
Tooltip.Hook(ShoppingTooltip2)
