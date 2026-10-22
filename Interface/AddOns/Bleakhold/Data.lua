-- Bleakhold: built-in fallback definitions.
-- The server is the source of truth: it sends names and texts with DEF messages (cached per dataVer
-- in BleakholdDB). These tables are only used until then, and by /bh demo.
local ADDON, ns = ...

local Data = {}
ns.Data = Data

-- The ten classes of the 3.3.5a client (ChrClasses ids). Extra Bleakhold classes come from DEF X.
Data.classes = {
    { id = 1, token = "WARRIOR", name = "Warrior", short = "WAR", color = "C79C6E" },
    { id = 2, token = "PALADIN", name = "Paladin", short = "PAL", color = "F58CBA" },
    { id = 3, token = "HUNTER", name = "Hunter", short = "HUN", color = "ABD473" },
    { id = 4, token = "ROGUE", name = "Rogue", short = "ROG", color = "FFF569" },
    { id = 5, token = "PRIEST", name = "Priest", short = "PRI", color = "FFFFFF" },
    { id = 6, token = "DEATHKNIGHT", name = "Death Knight", short = "DK", color = "C41F3B" },
    { id = 7, token = "SHAMAN", name = "Shaman", short = "SHA", color = "0070DE" },
    { id = 8, token = "MAGE", name = "Mage", short = "MAG", color = "69CCF0" },
    { id = 9, token = "WARLOCK", name = "Warlock", short = "WLK", color = "9482C9" },
    { id = 11, token = "DRUID", name = "Druid", short = "DRU", color = "FF7D0A" },
}

Data.tiers = { "Normal", "Veteran", "Elite", "Nightmare" }      -- Dungeon Journey tiers (bits 1, 2, 4, 8)
Data.keyModes = { [0] = "Normal", [1] = "Heroic", [2] = "Mythic" }
Data.roles = { [1] = "Tank", [2] = "Healer", [4] = "Damage" }

-- Definitions by kind (see docs/BleakholdProtocol.md, DEF):
--   A affix, E era, T task template, B weekly bonus, C chapter, D dungeon, L legacy tier, S season,
--   K rank, W season reward, M mythic level, X extra class, R rift boss
local defs = {}
Data.defs = defs

defs.A = {
    [1] = { name = "Fortified", text = "Non-boss enemies have more health and hit harder." },
    [2] = { name = "Tyrannical", text = "Bosses have more health and hit harder." },
    [3] = { name = "Bolstering", text = "When a non-boss enemy dies, its allies nearby grow stronger." },
    [4] = { name = "Volcanic", text = "Plumes of flame erupt under players fighting at range." },
    [5] = { name = "Raging", text = "Non-boss enemies enrage when their health is low." },
    [6] = { name = "Sanguine", text = "Slain non-boss enemies leave a pool that heals their allies." },
    [7] = { name = "Bursting", text = "Slain non-boss enemies burst and hurt the whole group." },
    [8] = { name = "Necrotic", text = "Enemy melee hits stack a wound that reduces healing taken." },
}

defs.E = {
    [1] = { name = "Molten Core", text = "Tier 1 tokens and Molten Core loot drop in every key and Rift floor.", tier = 1 },
    [2] = { name = "Blackwing Lair", text = "Tier 2 tokens and Blackwing Lair loot drop in every key and Rift floor.", tier = 2 },
    [3] = { name = "Ahn'Qiraj", text = "Tier 2.5 tokens and Ahn'Qiraj loot drop in every key and Rift floor.", tier = 3 },
    [4] = { name = "Naxxramas", text = "Tier 3 tokens and Naxxramas loot drop in every key and Rift floor.", tier = 4 },
    [5] = { name = "Karazhan", text = "Tier 4 tokens, Karazhan, Gruul and Magtheridon loot drop in every key and Rift floor.", tier = 5 },
    [6] = { name = "Serpentshrine", text = "Tier 5 tokens, Serpentshrine and Tempest Keep loot drop in every key and Rift floor.", tier = 6 },
    [7] = { name = "The Black Temple", text = "Tier 6 tokens, Hyjal, Black Temple and Sunwell loot drop in every key and Rift floor.", tier = 7 },
}

defs.T = {
    [1] = { title = "Heroic hero", text = "Clear any heroic dungeon." },
    [2] = { title = "Key sweeper", text = "Defeat 20 enemies inside a Mythic key." },
    [3] = { title = "Into the Rift", text = "Clear 5 Eclipse Rift floors." },
    [4] = { title = "Timed and tested", text = "Finish 3 keys of +5 or higher in time." },
    [5] = { title = "Echo hunter", text = "Defeat 2 Raid Echoes in keys or the Rift." },
    [6] = { title = "Echoes of the era", text = "Clear a dungeon or key this week." },
    [7] = { title = "Journey onward", text = "Finish 3 dungeons from the board." },
    [8] = { title = "Bounty hunter", text = "Finish today's bounty dungeon." },
}

defs.B = {
    [1] = { title = "First Raid Lord Echo", text = "Your first Raid Echo kill this week drops an era token for sure." },
}

defs.C = {
    [1] = { name = "Chapter I - Old Kingdoms", text = "The first dungeons of the journey." },
    [2] = { name = "Chapter II - Deep Places", text = "Caverns, crypts and sunken halls." },
    [3] = { name = "Chapter III - The Blackrock Depths", text = "Fire and iron under the mountain." },
    [4] = { name = "Chapter IV - Outland", text = "Through the Dark Portal." },
    [5] = { name = "Chapter V - Northrend", text = "The last road north." },
}

-- Dungeons by map id. bosses are listed in kill order.
defs.D = {
    [389] = { name = "Ragefire Chasm", chapter = 1, lvlMin = 13, lvlMax = 18 },
    [36] = { name = "The Deadmines", chapter = 1, lvlMin = 15, lvlMax = 21 },
    [43] = { name = "Wailing Caverns", chapter = 1, lvlMin = 16, lvlMax = 22 },
    [33] = { name = "Shadowfang Keep", chapter = 1, lvlMin = 18, lvlMax = 24 },
    [48] = { name = "Blackfathom Deeps", chapter = 2, lvlMin = 21, lvlMax = 27 },
    [90] = { name = "Gnomeregan", chapter = 2, lvlMin = 25, lvlMax = 31 },
    [47] = { name = "Razorfen Kraul", chapter = 2, lvlMin = 27, lvlMax = 33 },
    [189] = { name = "Scarlet Monastery", chapter = 2, lvlMin = 30, lvlMax = 40 },
    [209] = { name = "Zul'Farrak", chapter = 3, lvlMin = 42, lvlMax = 48 },
    [349] = { name = "Maraudon", chapter = 3, lvlMin = 44, lvlMax = 50 },
    [230] = { name = "Blackrock Depths", chapter = 3, lvlMin = 50, lvlMax = 56 },
    [229] = { name = "Blackrock Spire", chapter = 3, lvlMin = 55, lvlMax = 60 },
    [329] = { name = "Stratholme", chapter = 3, lvlMin = 56, lvlMax = 61 },
    [289] = { name = "Scholomance", chapter = 3, lvlMin = 56, lvlMax = 61 },
    [429] = { name = "Dire Maul", chapter = 3, lvlMin = 56, lvlMax = 61 },
    [543] = { name = "Hellfire Ramparts", chapter = 4, lvlMin = 58, lvlMax = 63 },
    [547] = { name = "The Slave Pens", chapter = 4, lvlMin = 61, lvlMax = 66 },
    [558] = { name = "Auchenai Crypts", chapter = 4, lvlMin = 64, lvlMax = 69 },
    [555] = { name = "Shadow Labyrinth", chapter = 4, lvlMin = 67, lvlMax = 70 },
    [574] = { name = "Utgarde Keep", chapter = 5, lvlMin = 69, lvlMax = 73 },
    [576] = { name = "The Nexus", chapter = 5, lvlMin = 70, lvlMax = 74 },
    [604] = { name = "Gundrak", chapter = 5, lvlMin = 74, lvlMax = 78 },
    [602] = { name = "Halls of Lightning", chapter = 5, lvlMin = 77, lvlMax = 80, timeLimitSec = 1800,
        bosses = { "General Bjarngrim", "Volkhan", "Ionar", "Loken" } },
    [599] = { name = "Halls of Stone", chapter = 5, lvlMin = 76, lvlMax = 80, timeLimitSec = 1800,
        bosses = { "Krystallus", "Maiden of Grief", "Tribunal of Ages", "Sjonnir the Ironshaper" } },
    [575] = { name = "Utgarde Pinnacle", chapter = 5, lvlMin = 78, lvlMax = 80, timeLimitSec = 1800,
        bosses = { "Svala Sorrowgrave", "Gortok Palehoof", "Skadi the Ruthless", "King Ymiron" } },
}

defs.L = {
    [1] = { label = "Tier 1", raids = "Molten Core, Zul'Gurub", eraId = 1, sources = { 229, 329, 289, 429, 543 }, lvlMin = 58, lvlMax = 61, echoBoss = "Ragnaros", total = 8 },
    [2] = { label = "Tier 2", raids = "Blackwing Lair, AQ20", eraId = 2, sources = { 229, 329, 289 }, lvlMin = 60, lvlMax = 63, echoBoss = "Nefarian", total = 8 },
    [3] = { label = "Tier 2.5", raids = "Temple of Ahn'Qiraj", eraId = 3, sources = { 349, 230 }, lvlMin = 60, lvlMax = 64, echoBoss = "C'Thun", total = 5 },
    [4] = { label = "Tier 3", raids = "Naxxramas 40", eraId = 4, sources = { 329, 289 }, lvlMin = 60, lvlMax = 65, echoBoss = "Kel'Thuzad", total = 9 },
    [5] = { label = "Tier 4", raids = "Karazhan, Gruul, Magtheridon", eraId = 5, sources = { 543, 547, 558 }, lvlMin = 66, lvlMax = 70, echoBoss = "Prince Malchezaar", total = 5 },
    [6] = { label = "Tier 5", raids = "Serpentshrine, Tempest Keep", eraId = 6, sources = { 555, 558 }, lvlMin = 68, lvlMax = 70, echoBoss = "Kael'thas Sunstrider", total = 5 },
    [7] = { label = "Tier 6", raids = "Hyjal, Black Temple, Sunwell", eraId = 7, sources = { 602, 599, 575 }, lvlMin = 70, lvlMax = 80, echoBoss = "Illidan Stormrage", total = 8 },
}

defs.S = {
    [1] = { name = "Season 1 - Bleak Dawn", text = "Naxxramas, the Bleakhold raid, Mythic+ Season 1, Eclipse Rift", state = 1 },
    [2] = { name = "Season 2 - The Fallen Kingdom", text = "Gilneas, Karazhan Crypts, Ulduar", state = 2 },
    [3] = { name = "Season 3 - Twilight Gate", text = "Grim Batol, Azshara Crater, Trial of the Crusader", state = 2 },
    [4] = { name = "Season 4 - Dream's End", text = "The Emerald Nightmare, Icecrown Citadel", state = 2 },
}

defs.K = {
    [1] = { name = "Recruit of the Wall" },
    [2] = { name = "Sergeant of the Wall" },
    [3] = { name = "Captain of the Wall" },
    [4] = { name = "Commander of the Wall" },
}

defs.W = {
    [1] = { name = "Title", need = "\"of the Bleak Dawn\" at 500 points" },
    [2] = { name = "Cosmetic set", need = "Time 20 keys of +10 or higher" },
    [3] = { name = "Season mount", need = "Rift floor 30 solo" },
    [4] = { name = "Banner", need = "Top 100 War Effort" },
}

-- Mythic levels (shown on the Keys tab; the server can replace every line with DEF M).
defs.M = {
    [0] = { text = "Where every keystone begins: beat a dungeon's end boss on Mythic 0 to get your first key." },
    [2] = { text = "Keystones start here. Enemies grow stronger with every level." },
    [4] = { text = "A second affix joins the first." },
    [7] = { text = "A third affix joins in." },
    [10] = { text = "Bosses and enemies gain extra abilities." },
    [15] = { text = "The highest keystone level." },
}

defs.X = {}
defs.R = {}

-- Fallback seasons reward icons (glyph names in the art atlas).
Data.rewardGlyphs = { "check", "chest", "mount", "banner" }

-- Animations every 3.3.5a character has: DoEmote token, the English slash command, the AnimationData id the
-- preview plays (WoW/Source/Object/ObjectClient/Types.h, ANIM_*), the category and the glyph (UI.EMOTE_GLYPHS).
-- "pose" animations hold until the character moves. Server dances are added to these (Animations.lua).
Data.animationCategories = {
    { key = "dance", label = "Dances" },
    { key = "emote", label = "Emotes" },
    { key = "talk", label = "Talk" },
    { key = "pose", label = "Poses" },
}
Data.emotes = {
    { key = "dance", name = "Dance", token = "DANCE", cmd = "/dance", anim = 69, cat = "dance", glyph = "dance", text = "Your race's own dance." },
    { key = "wave", name = "Wave", token = "WAVE", cmd = "/wave", anim = 67, cat = "emote", glyph = "wave" },
    { key = "bow", name = "Bow", token = "BOW", cmd = "/bow", anim = 66, cat = "emote", glyph = "bow" },
    { key = "cheer", name = "Cheer", token = "CHEER", cmd = "/cheer", anim = 68, cat = "emote", glyph = "cheer" },
    { key = "applaud", name = "Applaud", token = "APPLAUD", cmd = "/applaud", anim = 80, cat = "emote", glyph = "clap" },
    { key = "laugh", name = "Laugh", token = "LAUGH", cmd = "/laugh", anim = 70, cat = "emote", glyph = "laugh" },
    { key = "flex", name = "Flex", token = "FLEX", cmd = "/flex", anim = 82, cat = "emote", glyph = "flex" },
    { key = "kiss", name = "Blow a Kiss", token = "KISS", cmd = "/kiss", anim = 76, cat = "emote", glyph = "kiss" },
    { key = "salute", name = "Salute", token = "SALUTE", cmd = "/salute", anim = 113, cat = "emote", glyph = "salute" },
    { key = "roar", name = "Roar", token = "ROAR", cmd = "/roar", anim = 74, cat = "emote", glyph = "roar" },
    { key = "point", name = "Point", token = "POINT", cmd = "/point", anim = 84, cat = "emote", glyph = "point" },
    { key = "chicken", name = "Chicken", token = "CHICKEN", cmd = "/chicken", anim = 78, cat = "emote", glyph = "chicken" },
    { key = "cry", name = "Cry", token = "CRY", cmd = "/cry", anim = 77, cat = "emote", glyph = "cry" },
    { key = "shy", name = "Shy", token = "SHY", cmd = "/shy", anim = 83, cat = "emote", glyph = "shy" },
    { key = "beg", name = "Beg", token = "BEG", cmd = "/beg", anim = 79, cat = "emote", glyph = "beg" },
    { key = "rude", name = "Rude", token = "RUDE", cmd = "/rude", anim = 73, cat = "emote", glyph = "rude" },
    { key = "nod", name = "Nod", token = "NOD", cmd = "/nod", anim = 185, cat = "emote", glyph = "yes" },
    { key = "no", name = "No", token = "NO", cmd = "/no", anim = 186, cat = "emote", glyph = "no" },
    { key = "eat", name = "Eat", token = "EAT", cmd = "/eat", anim = 61, cat = "emote", glyph = "eat" },
    { key = "train", name = "Train", token = "TRAIN", cmd = "/train", anim = 195, cat = "emote", glyph = "train" },
    { key = "talk", name = "Talk", token = "TALK", cmd = "/talk", anim = 60, cat = "talk", glyph = "talk" },
    { key = "talkex", name = "Exclaim", token = "TALKEX", cmd = "/talkex", anim = 64, cat = "talk", glyph = "shout" },
    { key = "talkq", name = "Question", token = "TALKQ", cmd = "/talkq", anim = 65, cat = "talk", glyph = "question" },
    { key = "shout", name = "Shout", token = "SHOUT", cmd = "/shout", anim = 81, cat = "talk", glyph = "shout" },
    { key = "sit", name = "Sit", token = "SIT", cmd = "/sit", anim = 97, cat = "pose", glyph = "sit" },
    { key = "kneel", name = "Kneel", token = "KNEEL", cmd = "/kneel", anim = 115, cat = "pose", glyph = "kneel" },
    { key = "sleep", name = "Sleep", token = "SLEEP", cmd = "/sleep", anim = 100, cat = "pose", glyph = "sleep" },
    { key = "stand", name = "Stand", token = "STAND", cmd = "/stand", anim = 0, cat = "pose", glyph = "stand" },
}

-- The emote wheel a character starts with: four pages of eight slots (keys of Data.emotes).
Data.defaultWheel = {
    { "dance", "wave", "cheer", "laugh", "bow", "flex", "kiss", "roar" },
    { "salute", "applaud", "point", "rude", "chicken", "cry", "shy", "beg" },
    { "talk", "talkex", "talkq", "shout", "nod", "no", "train", "eat" },
    { "sit", "kneel", "sleep", "stand" },
}

-- Legacy set chat/tooltip tags.
Data.chatTags = {
    { tag = "Raid Legacy", color = "E5C07B", key = "legacy" },
    { tag = "Server First", color = "FF9D3B", key = "first" },
    { tag = "Season", color = "6CC6D9", key = "season" },
    { tag = "Queue", color = "9FD8E5", key = "queue" },
    { tag = "Record", color = "F1D9A0", key = "record" },
}
