-- Bleakhold: the server's legacy Activities messages (ns.Legacy). The old BleakholdActivities addon read them, and the
-- server still sends them to every player (mod-bleakhold BHMP::Mgr::SendAddon, bh_mplus.cpp: a whisper to oneself
-- in LANG_ADDON, so CHAT_MSG_ADDON with prefix "BHMP" and ';'-separated fields). They carry what our own protocol
-- does not: the Journey board's offers and rotation, the best keystone per dungeon, the Eclipse Rift's bests by group
-- size, checkpoint and floor count, the riding offer and the first-login "open Activities". The old addon's chat
-- commands still do the old actions (.act, .rift, .mplus, .ride: SEC_PLAYER commands said in /say, which the server
-- takes as commands and never repeats).
--
-- Messages (fields after the tag; old handlers BleakholdActivities.lua :474-511, senders in mod-bleakhold):
--   H  rotation seconds, queued offer key, players queued, first run done (0/1), Journey on (0/1)  bh_activities.cpp:47-54
--      (it starts a new board: the J offers follow)
--   J  key, dungeon, tier (0 Normal .. 3 Nightmare), modifier bits, chapter, min level, status (0 open, 1 level,
--      2 chapter, 3 tier), best score %, best time s, runs, reward Shards, name, modifier names        bh_activities.cpp:62-65
--   K  dungeon id, level, timer s, name; or "K;0" for no keystone                                      bh_mplus.cpp:973-984
--   W  week index, "a1,a2,a3,a4" affix ids, champions/boons from level, hp % per level, damage % per level   :986-991
--   L  dungeon id, timer s, best keystone level, name (one per season dungeon)                        bh_mplus.cpp:993-998
--   U  best floor solo, duo, trio, group, checkpoint, min level, Rift on (0/1), floor now (0 outside), floor count
--                                                                                                       bh_rift.cpp:180-190
--   Z  3 when the group leader chose Mythic, else 0 (the server never sends 1 or 2)                    bh_mplus.cpp:866-869
--   RIDE  price in copper: the riding offer popup                                                       bh_leveling.cpp:236
--   A  page: open Activities there (A;journey at the first login at Journey level)                     bh_leveling.cpp:254
--   G  the group as OpenSocket sees it, just before O: "name:class:inside:leader:alive|..." (inside 1: in the
--      key's instance)                                                                   bh_mplus.cpp:1199-1217
--   O  dungeon id, level, timer s, hp %, damage %, damage %, affix ids, name: the keystone (or the Font of Power)
--      opened the start in its dungeon; Start keystone (KSTART) works for 300 s there    bh_mplus.cpp:1204 OpenSocket
--   X  no run here: on leaving a keystone dungeon (a Rift floor too), on .rift leave and a collapse
--                                                      bh_mplus_scripts.cpp:286, bh_rift.cpp:1082 RiftLeave, :345
--   S  read only for an Eclipse Rift floor (mode 4): S;4;dungeon;floor;...: the floor just entered    bh_rift.cpp:350
-- The other BHMP tags (the keystone HUD's B/C/T/..., a keystone's S) are left to our own protocol.
--
-- State: L.journey, L.mplus, L.rift (see below); ns.Fire("LEGACY", tag) after each message.
local ADDON, ns = ...
local U, Comm = ns.U, ns.Comm

local floor = math.floor

local L = {}
ns.Legacy = L

L.PREFIX = "BHMP"
L.REQUEST_EVERY = 5     -- seconds between two board requests (.act journey / .act mplus)
local INT = 2147483647

-- The Journey's tiers as the old window coloured them (old :17).
L.TIERS = { [0] = { name = "Normal", color = "FFFFFF" }, [1] = { name = "Veteran", color = "1FFF00" },
    [2] = { name = "Elite", color = "338CFF" }, [3] = { name = "Nightmare", color = "BF4DFF" } }
L.DIFFICULTIES = { [1] = "Normal", [2] = "Heroic", [3] = "Mythic" }
L.DIFFICULTY_COLORS = { [1] = "FFFFFF", [2] = "40C0FF", [3] = "A335EE" }

local function reset()
    -- the Journey board: offers in the server's order; rotAt is GetTime() when the board changes (0: unknown)
    L.journey = { offers = {}, byKey = {}, rotAt = 0, queuedKey = 0, queuedPlayers = 0, firstDone = false, on = true,
        known = false }
    -- Mythic+: key = { id, level, timer, name } or nil; week.affixes = { ids }; list = season dungeons in the server's
    -- order { id, timer, best, name }; z = the last Z (0 or 3); socket = { at, dungeon, level, name } from O while the
    -- keystone has opened the start (L.SocketArmed), else nil; group = the last G's members { name, class, inside,
    -- leader, alive } (kept with the socket: gone when it goes)
    L.mplus = { key = nil, keyKnown = false, week = { index = 0, affixes = {}, champMinLevel = 0, hpPerLevel = 0,
        dmgPerLevel = 0 }, list = {}, byId = {}, z = 0, socket = nil, group = nil }
    -- the Eclipse Rift: best[1..4] = solo, duo, trio, group
    L.rift = { best = { 0, 0, 0, 0 }, checkpoint = 0, minLevel = 80, on = true, inFloor = 0, floors = 0, known = false }
    L.seen = false
    L.demoFed = false
end
reset()
L.Reset = reset

------------------------------------------------------------------------------------------------------
-- Parsing
------------------------------------------------------------------------------------------------------
local function int(v, lo, hi)
    return U.Int(v, 0, lo or 0, hi or INT)
end

-- Server text for a FontString: no control bytes, valid UTF-8, at most maxLen bytes (default 80; UI.SetText escapes
-- '|').
local function text(v, maxLen)
    if type(v) ~= "string" or v == "" then
        return ""
    end
    local s = v:gsub("%c", " ")
    return U.CutUtf8(U.CleanUtf8(s), maxLen or 80)
end
L.Text = text

-- How many fields each tag has; extra ';' are kept in the last field (a free text).
L.FIELDS = { H = 5, J = 13, K = 4, W = 5, L = 4, U = 9, Z = 1, RIDE = 1, A = 1, G = 1, O = 8, X = 0, S = 8 }

function L.Split(msg)
    local parts = {}
    for f in (msg .. ";"):gmatch("([^;]*);") do
        parts[#parts + 1] = f
        if #parts > 64 then
            break
        end
    end
    local tag = table.remove(parts, 1)
    local n = L.FIELDS[tag]
    if n and n > 0 and #parts > n then
        parts[n] = table.concat(parts, ";", n)
        for i = #parts, n + 1, -1 do
            parts[i] = nil
        end
    end
    return tag, parts
end

local H = {}
L.handlers = H

function H.H(f)
    local j = L.journey
    j.offers, j.byKey = {}, {}
    local rot = int(f[1])
    j.rotAt = rot > 0 and (GetTime() + rot) or 0
    j.queuedKey = int(f[2])
    j.queuedPlayers = int(f[3], 0, 99)
    j.firstDone = f[4] == "1"
    j.on = f[5] ~= "0"
    j.known = true
end

function H.J(f)
    local j = L.journey
    local o = {
        key = int(f[1]), dungeon = int(f[2]), tier = int(f[3], 0, 3), mods = int(f[4]), chapter = int(f[5], 0, 99),
        minLevel = int(f[6], 0, 255), status = int(f[7], 0, 3), best = int(f[8], 0, 100), time = int(f[9]),
        runs = int(f[10]), reward = int(f[11]), name = text(f[12]), modNames = text(f[13], 200),
    }
    if o.key == 0 or #j.offers >= 64 then
        return
    end
    local old = j.byKey[o.key]
    if old then
        for k, v in pairs(o) do
            old[k] = v
        end
    else
        j.offers[#j.offers + 1] = o
        j.byKey[o.key] = o
    end
end

function H.K(f)
    local m = L.mplus
    m.keyKnown = true
    local id = int(f[1])
    if id == 0 then
        m.key = nil
    else
        m.key = { id = id, level = int(f[2], 0, 99), timer = int(f[3]), name = text(f[4]) }
    end
end

function H.W(f)
    local w = { index = int(f[1]), affixes = {}, champMinLevel = int(f[3], 0, 99), hpPerLevel = int(f[4], 0, 1000),
        dmgPerLevel = int(f[5], 0, 1000) }
    for a in (f[2] or ""):gmatch("%d+") do
        if #w.affixes < 4 then
            w.affixes[#w.affixes + 1] = tonumber(a)
        end
    end
    L.mplus.week = w
end

function H.L(f)
    local m = L.mplus
    local id = int(f[1])
    if id == 0 then
        return
    end
    local d = m.byId[id]
    if d then
        d.timer, d.best = int(f[2]), int(f[3], 0, 99)
        local name = text(f[4])
        if name ~= "" then
            d.name = name
        end
    elseif #m.list < 64 then
        d = { id = id, timer = int(f[2]), best = int(f[3], 0, 99), name = text(f[4]) }
        m.list[#m.list + 1] = d
        m.byId[id] = d
    end
end

function H.U(f)
    local r = L.rift
    r.best = { int(f[1], 0, 9999), int(f[2], 0, 9999), int(f[3], 0, 9999), int(f[4], 0, 9999) }
    r.checkpoint = int(f[5], 0, 9999)
    r.minLevel = int(f[6], 0, 255)
    r.on = f[7] == "1"
    r.inFloor = int(f[8], 0, 9999)
    r.floors = int(f[9], 0, 9999)
    r.known = true
end

function H.Z(f)
    L.mplus.z = int(f[1], 0, 3)
end

function H.RIDE(f)
    L.ShowRide(int(f[1]))
end

function H.A(f)
    local page = text(f[1]):lower()
    if page ~= "" then
        ns.Fire("LEGACY_OPEN", page)
    end
end

-- G: the group when the keystone opened the start (OpenSocket sends it just before O): who is inside the instance.
function H.G(f)
    local group = {}
    for member in (text(f[1], 1000) .. "|"):gmatch("([^|]*)|") do
        local name, class, inside, leader, alive = member:match("^([^:]*):(%d*):(%d*):(%d*):(%d*)$")
        if name and name ~= "" and #group < 40 then
            group[#group + 1] = { name = name, class = int(class, 0, 99), inside = inside == "1",
                leader = leader == "1", alive = alive == "1" }
        end
    end
    L.mplus.group = group
end

-- How many of the group were inside the key's instance when the keystone opened the start (the last G), or nil.
function L.GroupInside()
    local g = L.mplus.group
    if not g then
        return nil
    end
    local n = 0
    for _, m in ipairs(g) do
        if m.inside then
            n = n + 1
        end
    end
    return n
end

-- O: the keystone (or the Font of Power) opened the start in its dungeon (OpenSocket). Start keystone works there for
-- L.SOCKET_SECONDS (L.SocketArmed).
function H.O(f)
    L.mplus.socket = { at = GetTime(), dungeon = int(f[1]), level = int(f[2], 0, 99), name = text(f[8]) }
end

-- X: no run where the player is now (out of a keystone dungeon or a Rift floor; out of the rift by .rift leave or a
-- collapse). U's floor is over: the server sends no new U then, and a player who only went one floor deeper gets the
-- new floor's S;4 next. The keystone's start is gone too.
function H.X()
    L.rift.inFloor = 0
    L.mplus.socket = nil
    L.mplus.group = nil
end

-- S: read for a Rift floor only (mode 4: S;4;dungeon;floor;...): the floor the player has just entered (SendRiftState).
-- A keystone's S is our protocol's (L.ACCEPT leaves it alone).
function H.S(f)
    local n = int(f[3], 0, 9999)
    if n > 0 then
        L.rift.inFloor = n
    end
end

-- Tags read only in part: the message is ours when this says so.
L.ACCEPT = {
    S = function(f)
        return f[1] == "4"
    end,
}

-- One BHMP message (without the prefix). Answers the tag when it was one of ours.
function L.Receive(msg)
    if type(msg) ~= "string" or msg == "" or #msg > 1024 then
        return nil
    end
    local tag, fields = L.Split(msg)
    local h = H[tag]
    if not h or (L.ACCEPT[tag] and not L.ACCEPT[tag](fields)) then
        return nil
    end
    L.seen = true
    h(fields)
    ns.Fire("LEGACY", tag)
    return tag
end

local function fromSelf(channel, sender)
    if channel ~= "WHISPER" or type(sender) ~= "string" then
        return false
    end
    return (sender:match("^([^%-]+)") or sender) == ns.PlayerName()
end

-- Only the server's own whisper to this character counts: another player cannot open windows or offer a mount.
ns.RegisterEvent("CHAT_MSG_ADDON", function(event, prefix, msg, channel, sender)
    if prefix ~= L.PREFIX or Comm.demo or not fromSelf(channel, sender) then
        return
    end
    L.Receive(msg)
end)

------------------------------------------------------------------------------------------------------
-- What the pages read
------------------------------------------------------------------------------------------------------
-- The dungeon difficulty, 1 Normal, 2 Heroic, 3 Mythic. Z says Mythic or not (it is never 2), so Heroic comes from our
-- own KEY (its mode 0..2) when the server sent one, else from the client's dungeon difficulty (Heroic is the game's
-- own 5-player Heroic: .mplus difficulty heroic sets it).
function L.Difficulty()
    local key = ns.S and ns.S.key
    if key and key.mode then
        return key.mode + 1
    end
    if L.mplus.z == 3 then
        return 3
    end
    local d = GetDungeonDifficulty and GetDungeonDifficulty()
    if d == 2 then
        return 2
    end
    return 1
end

-- "Normal", "Heroic" or "Mythic"; colored with the stock colours when color is set (old :348 and :429, without the
-- concatenation-before-or slip of :348).
function L.DifficultyName(n, color)
    n = n or L.Difficulty()
    local name = L.DIFFICULTIES[n] or L.DIFFICULTIES[1]
    if color and n ~= 1 then
        return "|cff" .. L.DIFFICULTY_COLORS[n] .. name .. "|r"
    end
    return name
end

-- The season's Mythic+ dungeons in the server's order: the L list ({ id, timer, best, name }), else (no BHMP yet) the
-- DEF D dungeons with a time limit (the key dungeons, bh_ui_bridge_map.cpp), best unknown (0).
function L.SeasonDungeons()
    if #L.mplus.list > 0 then
        return L.mplus.list
    end
    local out = {}
    for _, id in ipairs(ns.DefIds("D")) do
        local d = ns.Def("D", id)
        if d and (d.timeLimitSec or 0) > 0 and #out < 64 then
            out[#out + 1] = { id = id, timer = d.timeLimitSec, best = 0, name = d.name or ns.DungeonName(id) }
        end
    end
    return out
end

-- Whether the keystone has opened the start here (O), so the server takes Start keystone: TakePendingSocket wants
-- the same instance within 300 s. Gone on X (out of the dungeon), on a loading screen, once the countdown starts
-- (MPS) and after L.SOCKET_SECONDS.
L.SOCKET_SECONDS = 300
function L.SocketArmed()
    local s = L.mplus.socket
    if not s then
        return false
    end
    if GetTime() - s.at > L.SOCKET_SECONDS then
        L.mplus.socket = nil
        return false
    end
    return true
end

ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    L.mplus.socket = nil
    L.mplus.group = nil
end)
ns.On("MPLUS_START", function()
    L.mplus.socket = nil
end)

-- Seconds until the Journey board changes, or nil when unknown.
function L.BoardChangesIn()
    local at = L.journey.rotAt
    if not at or at <= 0 then
        return nil
    end
    return math.max(0, floor(at - GetTime()))
end

------------------------------------------------------------------------------------------------------
-- The old commands
------------------------------------------------------------------------------------------------------
-- Commands go out only on a Bleakhold server (our handshake answered, or refused as too old - only Bleakhold says
-- that -, or a BHMP message came): anywhere else a '.' line would be said aloud. Never in demo mode.
function L.CanCommand()
    if Comm.demo then
        return false
    end
    return (Comm.ready or Comm.outdated or L.seen) and true or false
end

function L.Cmd(line)
    if not L.CanCommand() then
        return false
    end
    SendChatMessage(line, "SAY")
    return true
end

-- Ask for the board, the keystone, the season list, the Rift and the difficulty (the old window did on every open);
-- at most every L.REQUEST_EVERY seconds unless forced.
local lastRequest = -1e9
function L.Request(force)
    if not force and GetTime() - lastRequest < L.REQUEST_EVERY then
        return false
    end
    if not L.CanCommand() then
        return false
    end
    lastRequest = GetTime()
    L.Cmd(".act journey")
    L.Cmd(".act mplus")
    return true
end

-- A board offer: alone ("solo") or through the Journey's group queue ("queue").
function L.StartJourney(key, how)
    key = tonumber(key)
    if not key or key <= 0 then
        return false
    end
    return L.Cmd(".act start " .. floor(key) .. " " .. (how == "queue" and "queue" or "solo"))
end

function L.RiftEnter(floorNo)
    return L.Cmd(".rift enter " .. math.max(1, floor(tonumber(floorNo) or 1)))
end

-- A party member follows the rift the party leader opened (RiftEnter's follow path, which takes no floor); with
-- nothing to follow the server answers "Only your party leader can open the rift."
function L.RiftFollow()
    return L.Cmd(".rift enter")
end

-- Out of the rift; the server answers with X only, so U is asked again once the player is out (L.LEAVE_REFRESH s).
L.LEAVE_REFRESH = 2
function L.RiftLeave()
    if not L.Cmd(".rift leave") then
        return false
    end
    ns.After(L.LEAVE_REFRESH, function()
        L.Request(true)
    end)
    return true
end

-- The dungeon difficulty for the group (1 Normal, 2 Heroic, 3 Mythic; the party leader, outside dungeons): our KMODE
-- (0..2) while the protocol is up, which the server confirms with a new KEY (its mode), else the old command.
local DIFF_WORDS = { [1] = "normal", [2] = "heroic", [3] = "mythic" }
function L.SetDifficulty(n)
    local w = DIFF_WORDS[n]
    if not w then
        return false
    end
    if Comm.ready then
        Comm.Send("KMODE", n - 1)
        return true
    end
    return L.Cmd(".mplus difficulty " .. w)
end

function L.LeaveDungeon()
    return L.Cmd(".mplus leave")
end

------------------------------------------------------------------------------------------------------
-- Popups (the stock dialog; the old addon's names, so a copy of it still installed shows one dialog, not two)
------------------------------------------------------------------------------------------------------
L.RIDE_TEXT = "You can ride now!\n\nApprentice Riding (60%% speed) and your first mount for %s?"
-- Where Leave dungeon takes the player, as the server's LeaveDungeon does it (bh_leave.cpp): an Eclipse Rift floor
-- leaves the rift (RiftLeave, back to Dalaran); a Dungeon Journey run goes back to the Dungeon Board (or the spot) it
-- was started from; any other dungeon, outside its entrance. The client cannot tell a Journey run from a plain one.
L.LEAVE_TEXT = "Leave this dungeon?\nA Dungeon Journey run takes you back to where you started it; any other "
    .. "dungeon, outside its entrance."
L.LEAVE_RIFT_TEXT = "Leave the Eclipse Rift and return to Dalaran?"
function L.LeaveText()
    local rift = ns.Rift
    if rift and rift.RunFloor and rift.RunFloor() then
        return L.LEAVE_RIFT_TEXT
    end
    return L.LEAVE_TEXT
end

function L.InstallDialogs()
    StaticPopupDialogs.BLEAKHOLD_RIDE = {
        text = L.RIDE_TEXT, button1 = "Buy", button2 = "Later", timeout = 0, whileDead = 1, hideOnEscape = 1,
        preferredIndex = 3,
        OnAccept = function()
            L.Cmd(".ride")
        end,
    }
    StaticPopupDialogs.BLEAKHOLD_LEAVE_DUNGEON = {
        text = "%s", button1 = "Yes", button2 = "No", timeout = 0, whileDead = 1, hideOnEscape = 1,
        preferredIndex = 3,
        OnAccept = function()
            L.LeaveDungeon()
        end,
        -- the Leave dungeon button closes Activities before asking; No (or Escape) brings it back on its page
        OnCancel = function()
            local A = ns.Activities
            if A and A.OpenPage then
                A.OpenPage(A.current or "group")
            end
        end,
    }
end
L.InstallDialogs()

function L.Money(copper)
    if GetCoinTextureString then
        local s = GetCoinTextureString(copper)
        if type(s) == "string" and s ~= "" then
            return s
        end
    end
    return floor(copper / 10000) .. " gold"
end

-- The old BleakholdActivities, still loaded ("Not now" in OldAddons.lua), reads RIDE as well and plays the same sound
-- (old :505-508): the sound once, from it then. StaticPopup_Show reuses the shown dialog, so it shows once either way.
function L.ShowRide(price)
    local oldPlays = IsAddOnLoaded and IsAddOnLoaded("BleakholdActivities")
    if PlaySoundFile and not oldPlays then
        PlaySoundFile("Sound\\Spells\\ReputationLevelUp.wav")
    end
    return StaticPopup_Show("BLEAKHOLD_RIDE", L.Money(price or 0))
end

function L.ConfirmLeave()
    return StaticPopup_Show("BLEAKHOLD_LEAVE_DUNGEON", L.LeaveText())
end

------------------------------------------------------------------------------------------------------
-- Demo mode (/bh demo): a board, a keystone, the season list and the Rift, through the same parser
------------------------------------------------------------------------------------------------------
L.DEMO = {
    "H;5400;0;0;0;1",
    "J;1001;36;0;0;1;15;0;82;845;3;120;The Deadmines;",
    "J;1002;33;1;2;1;18;0;0;0;0;160;Shadowfang Keep;Bolstering",
    "J;1003;189;2;5;2;30;0;64;1310;1;240;Scarlet Monastery;Bolstering, Sanguine",
    "J;1004;209;0;0;3;42;1;0;0;0;300;Zul'Farrak;",
    "J;1005;230;3;8;3;50;3;0;0;0;380;Blackrock Depths;Raging",
    "J;1006;329;1;0;3;56;2;0;0;0;420;Stratholme;",
    "J;1007;575;2;1;5;78;1;0;0;0;600;Utgarde Pinnacle;Fortified",
    "J;1008;602;3;3;5;77;1;0;0;0;640;Halls of Lightning;Fortified, Bolstering",
    "K;602;8;1800;Halls of Lightning",
    "W;12;1,3,10,8;10;8;5",
    "L;189;1800;9;Scarlet Monastery: Armory",
    "L;190;1800;0;Scarlet Monastery: Cathedral",
    "L;329;1800;7;Stratholme: Main Gate",
    "L;330;1800;0;Stratholme: Service Entrance",
    "L;289;1800;12;Scholomance",
    "L;230;1800;4;Blackrock Depths: Upper City",
    "L;229;1800;0;Lower Blackrock Spire",
    "L;429;1800;0;Dire Maul: West",
    "L;209;1800;6;Zul'Farrak",
    "L;555;1800;0;Shadow Labyrinth",
    "L;575;1800;8;Utgarde Pinnacle",
    "L;602;1800;11;Halls of Lightning",
    "U;24;18;12;9;20;80;1;0;50",
    "Z;3",
}

function L.DemoFeed()
    for _, msg in ipairs(L.DEMO) do
        L.Receive(msg)
    end
    L.demoFed = true
end

-- /bh demo resets the state and says hello: the sample board comes with it; leaving demo mode forgets it.
local resetState = ns.ResetState
ns.ResetState = function(...)
    resetState(...)
    reset()
end

ns.On("HELLO", function()
    if Comm.demo and not L.demoFed then
        L.DemoFeed()
    end
end)
