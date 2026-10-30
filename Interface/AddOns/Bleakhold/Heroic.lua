-- Bleakhold: Activities > Heroic Dungeons, the old window's page (old BleakholdActivities.lua :407-431) in its anatomy
-- (Activities.lua A.Page): the season's dungeons as a 3 x 4 grid of their Journal pictures (a band of the page art,
-- JournalArt.lua "tile"), and Normal / Heroic / Mythic for the group's next dungeon, the chosen one held down.
-- Data: the season list (Legacy.lua: BHMP L, else DEF D's key dungeons). The difficulty: Legacy.Difficulty (KEY.mode
-- when our protocol sent one, else the old Z, which is only ever 0 or 3, else the client's dungeon difficulty), set
-- with Legacy.SetDifficulty (KMODE, or .mplus difficulty as the old page did).
-- Rules as the server has them (mod-bleakhold bh_mplus.cpp, bh_mplus_scripts.cpp): Heroic is the game's own 5-player
-- Heroic, every enemy of a Mythic+ dungeon there is level 80 and each final boss pays Mythic Coins and a Mythic Spoils
-- chest; Mythic turns the group's next Normal Mythic+ dungeon into Mythic 0; only the group leader changes it, outside
-- dungeons (SetDifficulty, the bridge's KMODE, which also waits until nobody of the group is inside one).
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local A = ns.Activities
local L = ns.Legacy

local floor, ceil, min, max = math.floor, math.ceil, math.min, math.max

local P = A.Page("heroic", {
    desc = "Every Mythic+ dungeon also has a level 80 Heroic version - the vanilla classics included. Set the "
        .. "difficulty here before you go in. Final bosses pay Mythic Coins and a Mythic Spoils chest.",
})
ns.Heroic = P

P.COLS, P.TILE_W, P.TILE_H, P.GAP_X, P.GAP_Y = 3, 140, 92, 6, 6
P.tiles = {}
for i = 1, 12 do
    local col, row = (i - 1) % P.COLS, floor((i - 1) / P.COLS)
    local r = UI.Box(P, P.TILE_W, P.TILE_H, C.card, C.border, nil, "edge")
    r:SetPoint("TOPLEFT", P, "TOPLEFT", 18 + col * (P.TILE_W + P.GAP_X), -126 - row * (P.TILE_H + P.GAP_Y))
    r.thumb = r:CreateTexture(nil, "ARTWORK")
    r.thumb:SetPoint("TOPLEFT", r, "TOPLEFT", 1, -1)
    r.thumb:SetPoint("BOTTOMRIGHT", r, "BOTTOMRIGHT", -1, 1)
    r.band = r:CreateTexture(nil, "OVERLAY")
    r.band:SetTexture(0, 0, 0, 0.65)
    r.band:SetPoint("BOTTOMLEFT", r, "BOTTOMLEFT", 1, 1)
    r.band:SetPoint("BOTTOMRIGHT", r, "BOTTOMRIGHT", -1, 1)
    r.band:SetHeight(22)
    -- the name wraps upward from its bottom-left anchor, as the old tile's did (old :414: a width, no height), so
    -- "Scarlet Monastery: Armory" and "...: Cathedral" stay apart; Refresh fits the dark band to the lines
    r.name = UI.Text(r, 10, C.text)
    r.name:SetPoint("BOTTOMLEFT", r, "BOTTOMLEFT", 6, 6)
    r.name:SetWidth(P.TILE_W - 12)
    r.name:SetJustifyH("LEFT")
    r:EnableMouse(true)
    r:SetScript("OnEnter", function(self)
        if self.d then
            UI.ShowTooltip(self, P.TileTooltip(self.d))
        end
    end)
    r:SetScript("OnLeave", function()
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    r:Hide()
    P.tiles[i] = r
end

function P.TileTooltip(d)
    local lines = { U.Safe(d.name), { "Heroic: every enemy is level 80; the final boss pays Mythic Coins and a Mythic "
        .. "Spoils chest.", C.text, true } }
    if (d.timer or 0) > 0 then
        lines[#lines + 1] = { "Keystone timer " .. U.Clock(d.timer), C.dim }
    end
    if (d.best or 0) > 0 then
        lines[#lines + 1] = { "Your best keystone: +" .. d.best, C.gold }
    end
    return lines
end

-- Normal / Heroic / Mythic (old :420-422), right to left from the bottom right corner; what each one means, in the
-- server's words where it sends them (DEF M 0 for Mythic 0)
P.MODE_TEXT = {
    [1] = "The dungeons as they are, at their own level.",
    [2] = "The game's 5-player Heroic: in a Mythic+ dungeon every enemy is level 80, and each final boss pays Mythic "
        .. "Coins and a Mythic Spoils chest.",
    [3] = "Mythic 0: your group's next Mythic+ dungeon on Normal becomes an untimed level 80 run. Beat the final "
        .. "boss for Mythic Coins and your first keystone.",
}
P.modes = {}
for n, name in ipairs({ "Normal", "Heroic", "Mythic" }) do
    local b = UI.Button(P, 110, 26, name, "tab", 12)
    b:SetPoint("BOTTOMRIGHT", P, "BOTTOMRIGHT", -18 - (3 - n) * 116, 18)
    b.mode = n
    b:SetScript("OnClick", function()
        L.SetDifficulty(n)
    end)
    b.tooltip = function()
        local text = P.MODE_TEXT[n]
        local m0 = n == 3 and ns.Def("M", 0)
        if m0 and m0.text then
            text = U.Safe(m0.text)
        end
        return { name, { text, C.text, true }, { "The party leader sets it, outside dungeons.", C.dim, true } }
    end
    P.modes[n] = b
end
P.diff = UI.Text(P, 11, C.dim)
P.diff:SetPoint("BOTTOMLEFT", P, "BOTTOMLEFT", A.PAD, 24)
P.diff:SetWidth(420)

function P:Refresh()
    local list = L.SeasonDungeons()
    for i, r in ipairs(self.tiles) do
        local d = list[i]
        r.d = d
        if d then
            ns.Journal.Set(r.thumb, ns.Journal.Key(d.name), "tile", P.TILE_W - 2, P.TILE_H - 2)
            UI.SetText(r.name, d.name)
            r:Show()
            -- the dark band covers every line of the name (one line keeps the old 22), never more than the tile
            r.band:SetHeight(min(P.TILE_H - 2, max(22, ceil(r.name:GetStringHeight()) + 12)))
        else
            r:Hide()
        end
    end
    local now = L.Difficulty()
    -- the server refuses a change from inside a dungeon or from a member who is not the leader (ns.Keys has the rule)
    local block = ns.Keys and ns.Keys.DifficultyBlock()
    -- Mythic alone is refused to a Dungeon Finder group (Keys.MythicBlock)
    local mythicBlock = ns.Keys and ns.Keys.MythicBlock()
    local commands = Comm.ready or L.CanCommand() or Comm.demo
    for n, b in ipairs(self.modes) do
        b:SetStyle(n == now and "tabOn" or "tab")
        b:SetActive(commands and not (n == 3 and mythicBlock or block) and true or false)
    end
    self.diff:SetText("Current: " .. L.DifficultyName(now, true) .. "  -  "
        .. (block and block or "the party leader sets it, outside dungeons"))
end
