-- Bleakhold: item tooltip lines. Legacy set pieces get their era, where they drop and whether the look
-- is collected; the player's keystone gets its dungeon, level, affixes and mode. The item's own lines
-- (stats, set bonus) are left untouched.
local ADDON, ns = ...
local U, UI, Data = ns.U, ns.UI, ns.Data
local C = UI.C

local Tooltip = {}
ns.Tooltip = Tooltip

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

-- Lines for an item id: { {text, colorHex, wrap}, ... } (text already safe for display).
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
    local key = ns.S.key
    if key and key.hasKey and key.itemId and key.itemId == id then
        lines[#lines + 1] = { " " }
        lines[#lines + 1] = { U.Safe(ns.DungeonName(key.dungeonId)) .. " +" .. (key.level or 0), C.goldPale }
        local affixes = ns.AffixNames(key.affixes)
        if #affixes > 0 then
            lines[#lines + 1] = { "Affixes: " .. U.Safe(table.concat(affixes, ", ")), C.mid, true }
        end
        lines[#lines + 1] = { "Dungeon mode: " .. (Data.keyModes[key.mode] or "Normal"), C.dim }
        if key.depleted then
            lines[#lines + 1] = { "Depleted", C.red }
        end
    end
    return lines
end

local function onSetItem(tt)
    local _, link = tt:GetItem()
    local id = itemId(link)
    if not id or tt.bleakholdItem == id then
        return
    end
    tt.bleakholdItem = id
    local lines = Tooltip.Lines(id)
    if #lines == 0 then
        return
    end
    for _, l in ipairs(lines) do
        local r, g, b = UI.Rgb(l[2] or C.mid)
        tt:AddLine(l[1], r, g, b, l[3] and true or false)
    end
    tt:Show()
end

local function onCleared(tt)
    tt.bleakholdItem = nil
end

function Tooltip.Hook(tt)
    if tt and tt.HookScript and not tt.bleakholdHooked then
        tt.bleakholdHooked = true
        tt:HookScript("OnTooltipSetItem", onSetItem)
        tt:HookScript("OnTooltipCleared", onCleared)
    end
end

Tooltip.Hook(GameTooltip)
Tooltip.Hook(ItemRefTooltip)
Tooltip.Hook(ShoppingTooltip1)
Tooltip.Hook(ShoppingTooltip2)
