-- Bleakhold: dungeon pictures for the Activities pages (ns.Journal), as the old BleakholdActivities window drew them.
--   1. the owner's Dungeon Journal art, Interface\AddOns\Bleakhold\Art\Journal\bg_<KEY> (512 x 512: the page art and
--      the grid tiles) and btn_<KEY> (256 x 128: row thumbnails). It reaches players through the launcher's extra/
--      layer and is never in this repository (gitignored), so it may be missing: each file is probed once.
--   2. else the client's own LFG picture, Interface\LFGFrame\UI-LFG-BACKGROUND-<SUFFIX> (LFGDungeons.dbc's texture
--      names), probed too, cropped to the area's shape.
--   3. else no picture: the texture is hidden and the dark panel shows (J.Set answers nil).
-- SetTexture answers nil for a file that does not load, silently, and keeps what the texture had: so the probing is
-- done on a hidden texture of its own, and a page's texture is only ever given a file that loaded.
--
--   J.Key(nameOrMapId)           the art key of a dungeon name ("Stratholme: Main Gate" -> STRATHOLME) or a map id
--   J.Set(tex, key, kind, w, h)  kind "bg" (page art), "tile" (a band of the page art, the Heroic grid) or "btn"
--                                (thumbnail); w, h the area's size for the stock crop. Answers "journal", "stock" or nil
--   J.Source(key, kind)          what J.Set would use, without a texture
local ADDON, ns = ...
local UI = ns.UI

local J = {}
ns.Journal = J

J.PATH = UI.ART .. "Journal\\"
J.STOCK = "Interface\\LFGFrame\\UI-LFG-BACKGROUND-"

-- The 15 pictures of the owner's Journal art (old media/).
J.KEYS = {
    AUCHINDOUN = true, BLACKROCKDEPTHS = true, BLACKROCKSPIRE = true, DEADMINES = true, DIREMAUL = true,
    EYEOFETERNITY = true, HALLSOFLIGHTNING = true, HELLFIRE = true, SCARLETMONASTERY = true, SCHOLOMANCE = true,
    SHADOWFANGKEEP = true, STRATHOLME = true, UTGARDEKEEP = true, UTGARDEPINNACLE = true, ZULFARRAK = true,
}

-- The stock LFG picture of a key, where the names differ (LFGDungeons.dbc: Zul'Farrak is ZULFARAK, Utgarde Keep
-- UTGARDE, the Hellfire wings HELLFIRECITADEL, the Eye of Eternity MALYGOS); any other key is its own suffix.
J.STOCK_SUFFIX = { ZULFARRAK = "ZULFARAK", HELLFIRE = "HELLFIRECITADEL", UTGARDEKEEP = "UTGARDE", EYEOFETERNITY = "MALYGOS" }

-- Dungeon names to keys: the old window's table (old :11-16) and the other dungeons the stock LFG art covers. The
-- first entry found in the name wins (so the Culling of Stratholme is the Caverns of Time, not Stratholme).
J.NAMES = {
    { "Culling of Stratholme", "CAVERNSOFTIME" }, { "Old Hillsbrad", "CAVERNSOFTIME" }, { "Black Morass", "CAVERNSOFTIME" },
    { "Scarlet", "SCARLETMONASTERY" }, { "Stratholme", "STRATHOLME" }, { "Scholomance", "SCHOLOMANCE" },
    { "Blackrock Depths", "BLACKROCKDEPTHS" }, { "Blackrock Spire", "BLACKROCKSPIRE" }, { "Dire Maul", "DIREMAUL" },
    { "Zul'Farrak", "ZULFARRAK" }, { "Shadow Labyrinth", "AUCHINDOUN" }, { "Auchenai", "AUCHINDOUN" },
    { "Sethekk", "AUCHINDOUN" }, { "Mana-Tombs", "AUCHINDOUN" }, { "Utgarde Pinnacle", "UTGARDEPINNACLE" },
    { "Halls of Lightning", "HALLSOFLIGHTNING" }, { "Deadmines", "DEADMINES" }, { "Shadowfang", "SHADOWFANGKEEP" },
    { "Utgarde Keep", "UTGARDEKEEP" }, { "Hellfire", "HELLFIRE" }, { "Blood Furnace", "HELLFIRE" },
    { "Shattered Halls", "HELLFIRE" }, { "Ragefire", "RAGEFIRECHASM" }, { "Wailing Caverns", "WAILINGCAVERNS" },
    { "Blackfathom", "BLACKFATHOMDEEPS" }, { "Gnomeregan", "GNOMEREGAN" }, { "Razorfen Kraul", "RAZORFENKRAUL" },
    { "Razorfen Downs", "RAZORFENDOWNS" }, { "Maraudon", "MARAUDON" }, { "Uldaman", "ULDAMAN" },
    { "Sunken Temple", "SUNKENTEMPLE" }, { "Atal'Hakkar", "SUNKENTEMPLE" }, { "Stockade", "STORMWINDSTOCKADES" },
    { "Slave Pens", "COILFANG" }, { "Underbog", "COILFANG" }, { "Steamvault", "COILFANG" }, { "Mechanar", "TEMPESTKEEP" },
    { "Botanica", "TEMPESTKEEP" }, { "Arcatraz", "TEMPESTKEEP" }, { "Magisters", "MAGISTERSTERRACE" },
    { "Nexus", "THENEXUS" }, { "Oculus", "THEOCULUS" }, { "Gundrak", "GUNDRAK" }, { "Halls of Stone", "HALLSOFSTONE" },
    { "Azjol", "AZJOLNERUB" }, { "Ahn'kahet", "AHNKALET" }, { "Drak'Tharon", "DRAKTHARON" },
    { "Violet Hold", "THEVIOLETHOLD" }, { "Trial of the Champion", "ARGENTDUNGEON" },
    { "Forge of Souls", "THEFORGEOFSOULS" }, { "Pit of Saron", "PITOFSARON" }, { "Halls of Reflection", "HALLSOFREFLECTION" },
    { "Eye of Eternity", "EYEOFETERNITY" },
}

-- The Journal crops the old window used: bg 390 x 423 of 512 (old :36), a band of it for the grid tiles (old :427),
-- btn 174 x 96 of 256 x 128 (old :39).
J.CROP = {
    bg = { 0, 0.76171875, 0, 0.826171875 },
    tile = { 0, 0.76171875, 0.2, 0.55 },
    btn = { 0, 0.6796875, 0, 0.75 },
}
-- The stock LFG pictures as the live client's exports have them: a 2:1 scene filling the file. J.STOCK_AREA is the
-- part of the file the scene covers (left, right, top, bottom); the 3.3.5a files are unverified, so it is kept here
-- to be corrected after a check in game.
J.STOCK_ASPECT = 2
J.STOCK_AREA = { 0, 1, 0, 1 }
-- the shape of each kind, for a crop when no size is given
J.ASPECT = { bg = 390 / 423, tile = 140 / 92, btn = 84 / 46 }

function J.Key(name)
    if type(name) == "number" then
        name = ns.DefName and ns.DefName("D", name, nil)
    end
    if type(name) ~= "string" or name == "" then
        return nil
    end
    local low = name:lower()
    for _, e in ipairs(J.NAMES) do
        if low:find(e[1]:lower(), 1, true) then
            return e[2]
        end
    end
    return nil
end

function J.JournalPath(key, kind)
    return J.PATH .. (kind == "btn" and "btn_" or "bg_") .. key
end

function J.StockPath(key)
    return J.STOCK .. (J.STOCK_SUFFIX[key] or key)
end

-- Probing: one hidden texture, every answer kept. Trusted only when it finds a file that surely exists (else every
-- file counts as there, as the old addon had it).
local probe, probeWorks
local known = {}
local function loads(path)
    local k = known[path]
    if k ~= nil then
        return k
    end
    if not probe then
        probe = UIParent:CreateTexture(nil, "BACKGROUND")
        probe:Hide()
        probeWorks = probe:SetTexture(UI.STOCK.question) and true or false
    end
    k = (not probeWorks or probe:SetTexture(path)) and true or false
    known[path] = k
    return k
end

-- Forget the probes (tests; a reload does it in game).
function J.Forget()
    wipe(known)
    probe, probeWorks = nil, nil
end

function J.Source(key, kind)
    if type(key) ~= "string" or key == "" then
        return nil
    end
    if J.KEYS[key] and loads(J.JournalPath(key, kind)) then
        return "journal", J.JournalPath(key, kind)
    end
    if loads(J.StockPath(key)) then
        return "stock", J.StockPath(key)
    end
    return nil
end

-- The texcoords of a w:h area cut from the middle of the stock scene.
local function stockCoords(aspect)
    local a = J.STOCK_AREA
    local l, r, t, b = 0, 1, 0, 1
    if aspect < J.STOCK_ASPECT then
        local w = aspect / J.STOCK_ASPECT
        l, r = 0.5 - w / 2, 0.5 + w / 2
    else
        local h = J.STOCK_ASPECT / aspect
        t, b = 0.5 - h / 2, 0.5 + h / 2
    end
    local aw, ah = a[2] - a[1], a[4] - a[3]
    return a[1] + l * aw, a[1] + r * aw, a[3] + t * ah, a[3] + b * ah
end
J.StockCoords = stockCoords

function J.Set(tex, key, kind, w, h)
    kind = J.CROP[kind] and kind or "bg"
    local src, path = J.Source(key, kind)
    if src == "journal" then
        tex:SetTexture(path)
        tex:SetTexCoord(unpack(J.CROP[kind]))
    elseif src == "stock" then
        tex:SetTexture(path)
        local aspect = (w and h and h > 0) and (w / h) or J.ASPECT[kind]
        tex:SetTexCoord(stockCoords(aspect))
    else
        tex:Hide()
        return nil
    end
    tex:Show()
    return src
end
