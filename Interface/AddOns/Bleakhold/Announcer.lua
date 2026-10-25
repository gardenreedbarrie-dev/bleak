-- Bleakhold: the battleground kill announcer (docs/BleakholdProtocol.md section 18). The server decides every line
-- (BGANN: first blood, the kill streaks, the multi-kills; parsed in State.lua) and sends it to everyone in the
-- battleground: Warsong Gulch to Isle of Conquest and Bleakhold Royale. This file shows a big banner
-- "<killer>: DOUBLE KILL" and plays the voice line, one line at a time.
--
--   active    only with HELLO feature bit 8192, inside a battleground (IsInInstance "pvp"), never in an arena; a
--             BGANN outside is ignored, and leaving the battleground forgets what is waiting
--   order     a kill with a multi-kill and a streak (or first blood) code plays the multi-kill first, then the other
--   voice     PlaySoundFile(path) only: 3.3.5a has no channel argument, no StopSound and no volume argument, so a line
--             can never be cut off and "Quiet" is a second, pre-attenuated set of files:
--             Interface\AddOns\Bleakhold\Sounds\Announcer\<male|female>[_quiet]\<line>.wav
--   no overlap   the next line waits for the busy-until time: the line's real length (AnnouncerData.lua, generated
--             from the WAV files by Tools/Announcer/import_sounds.py) plus a short gap. When lines pile up, at most
--             two wait: the lowest ones are dropped (first blood lowest, then by rank, see A.LINES)
--   settings  Announcer Off / Male / Female (default Male) and Volume Normal / Quiet: ns.db.options.announcerVoice and
--             announcerQuiet, on the Royale page of Activities and with /bh announcer. Off silences the voice; the
--             banners still show. A line without a sound file (or a set missing from AnnouncerData.lua) shows its
--             banner for A.SILENT_SECONDS.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C

local min = math.min

local A = {}
ns.Announcer = A

A.SOUND_DIR = "Interface\\AddOns\\Bleakhold\\Sounds\\Announcer\\"
A.MAX_WAITING = 2                -- lines waiting behind the one playing
A.GAP = 0.15                     -- s of quiet between two lines
A.SILENT_SECONDS = 2.0           -- how long a line without a voice holds its banner
A.FADE_IN, A.FADE_OUT = 0.15, 0.3
-- code -> sound file, banner title, rank (the lowest waiting line is dropped first). Multi-kills and streaks
-- interleave by how rare they are; first blood ranks lowest because it never comes with a second code.
A.LINES = {
    F = { file = "firstblood", title = "FIRST BLOOD", rank = 1, color = C.red },
    D = { file = "doublekill", title = "DOUBLE KILL", rank = 2 },
    T = { file = "triplekill", title = "TRIPLE KILL", rank = 3 },
    S = { file = "killingspree", title = "KILLING SPREE", rank = 4 },
    U = { file = "ultrakill", title = "ULTRA KILL", rank = 5 },
    O = { file = "dominating", title = "DOMINATING", rank = 6 },
    R = { file = "rampage", title = "RAMPAGE", rank = 7 },
    K = { file = "megakill", title = "MEGA KILL", rank = 8 },
    N = { file = "unstoppable", title = "UNSTOPPABLE", rank = 9 },
    W = { file = "wickedsick", title = "WICKED SICK", rank = 10 },
    M = { file = "monsterkill", title = "MONSTER KILL", rank = 11 },
    G = { file = "godlike", title = "GODLIKE", rank = 12 },
    H = { file = "holyshit", title = "HOLY SHIT", rank = 13 },
}
A.VOICES = { off = true, male = true, female = true }

A.waiting = {}                   -- { code, killer, killerClassId, victim, victimClassId }, in play order
A.current = nil                  -- the line on screen (shownAt, untilAt)
A.busyUntil = 0

------------------------------------------------------------------------------------------------------
-- Settings
------------------------------------------------------------------------------------------------------
function A.Voice()
    local v = ns.Option("announcerVoice", "male")
    return A.VOICES[v] and v or "male"
end

function A.Quiet()
    return ns.Option("announcerQuiet", false) and true or false
end

function A.SetVoice(v)
    if A.VOICES[v] then
        ns.db.options.announcerVoice = v
    end
end

function A.SetQuiet(quiet)
    ns.db.options.announcerQuiet = quiet and true or false
end

-- The Royale announcer's own settings (royaleVoice, royaleQuiet) carry over once.
ns.On("DB_READY", function()
    local o = ns.db.options
    if o.announcerVoice == nil and A.VOICES[o.royaleVoice] then
        o.announcerVoice = o.royaleVoice
    end
    if o.announcerQuiet == nil and o.royaleQuiet ~= nil then
        o.announcerQuiet = o.royaleQuiet and true or false
    end
    o.royaleVoice, o.royaleQuiet = nil, nil
end)

------------------------------------------------------------------------------------------------------
-- Where it plays
------------------------------------------------------------------------------------------------------
function A.InBattleground()
    local inside, kind = IsInInstance()
    if not inside or kind ~= "pvp" then
        return false
    end
    return not (IsActiveBattlefieldArena and IsActiveBattlefieldArena())
end

function A.Active()
    if not Comm.HasFeature(Comm.FEATURE.BG_ANNOUNCER) then
        return false
    end
    return Comm.demo ~= nil or A.InBattleground()
end

------------------------------------------------------------------------------------------------------
-- The banner
------------------------------------------------------------------------------------------------------
local banner = CreateFrame("Frame", "BleakholdAnnouncerBanner", UIParent)
banner:SetSize(760, 96)
banner:SetPoint("TOP", UIParent, "TOP", 0, -250)
banner:SetFrameStrata("HIGH")
banner:EnableMouse(false)
banner:Hide()
A.banner = banner
banner.title = UI.Text(banner, 34, C.purple, "title", "CENTER")
banner.title:SetPoint("TOP", banner, "TOP", 0, 0)
UI.OneLine(banner.title, 760)
banner.sub = UI.Text(banner, 14, C.mid, "body", "CENTER")
banner.sub:SetPoint("TOP", banner.title, "BOTTOM", 0, -4)
UI.OneLine(banner.sub, 700)

local function classText(name, classId)
    return U.Color(ns.ClassColor(classId), U.Safe(name))
end

-- "<killer>: DOUBLE KILL" (the killer in class colour, the title in the line's colour) over "killed <victim>".
function A.BannerText(e)
    local line = A.LINES[e.code]
    local hex = line.color or C.purple
    return classText(e.killer, e.killerClassId) .. U.Color(hex, ": " .. line.title),
        "killed " .. classText(e.victim, e.victimClassId)
end

------------------------------------------------------------------------------------------------------
-- The voice
------------------------------------------------------------------------------------------------------
-- The file and its length for a line, or nil (voice off, or no such file in AnnouncerData.lua).
function A.Sound(code)
    local line = A.LINES[code]
    local voice = A.Voice()
    if not line or voice == "off" then
        return nil
    end
    local set = voice .. (A.Quiet() and "_quiet" or "")
    local seconds = ns.ANNOUNCER_SECONDS and ns.ANNOUNCER_SECONDS[set] and ns.ANNOUNCER_SECONDS[set][line.file]
    if type(seconds) ~= "number" or seconds <= 0 then
        return nil
    end
    return A.SOUND_DIR .. set .. "\\" .. line.file .. ".wav", seconds
end

-- parentless, so the queue keeps moving while UIParent is hidden (Alt+Z)
local ticker = CreateFrame("Frame")
ticker:Hide()

local function play(e, now)
    local path, seconds = A.Sound(e.code)
    local hold = seconds or A.SILENT_SECONDS
    A.busyUntil = now + hold + A.GAP
    e.shownAt, e.untilAt = now, now + hold
    A.current = e
    A.lastPlayed = e.code
    local title, sub = A.BannerText(e)
    banner.title:SetText(title)
    banner.sub:SetText(sub)
    banner:SetAlpha(0)
    banner:Show()
    if path and PlaySoundFile then
        PlaySoundFile(path)
    end
    ticker:Show()
end

-- Queue one line; it plays at once when nothing is playing. Over A.MAX_WAITING the lowest waiting line goes (of
-- equal ones the oldest), which may be the new one.
function A.Push(e)
    if not A.LINES[e.code] then
        return
    end
    local now = GetTime()
    if now >= A.busyUntil and #A.waiting == 0 then
        play(e, now)
        return
    end
    A.waiting[#A.waiting + 1] = e
    while #A.waiting > A.MAX_WAITING do
        local low = 1
        for i = 2, #A.waiting do
            if A.LINES[A.waiting[i].code].rank < A.LINES[A.waiting[low].code].rank then
                low = i
            end
        end
        table.remove(A.waiting, low)
    end
    ticker:Show()
end

function A.Clear()
    A.waiting = {}
    A.current = nil
    banner:Hide()
end

function A.Update()
    local now = GetTime()
    if now >= A.busyUntil and #A.waiting > 0 then
        play(table.remove(A.waiting, 1), now)
    end
    local cur = A.current
    if cur and now >= cur.untilAt + A.GAP then
        A.current = nil
        cur = nil
    end
    if not cur then
        banner:Hide()
        if #A.waiting == 0 then
            ticker:Hide()
        end
        return
    end
    local t = now - cur.shownAt
    banner:SetAlpha(U.Clamp(min(t / A.FADE_IN, (cur.untilAt - now) / A.FADE_OUT), 0, 1))
end

ticker:SetScript("OnUpdate", function()
    A.Update()
end)

-- One BGANN: the multi-kill line first, then the streak (or first blood).
function A.OnAnnounce(a)
    if not A.Active() then
        return
    end
    for _, code in ipairs({ a.multi or "", a.streak or "" }) do
        if A.LINES[code] then
            A.Push({ code = code, killer = a.killer, killerClassId = a.killerClassId, victim = a.victim,
                victimClassId = a.victimClassId })
        end
    end
end

ns.On("BG_ANNOUNCE", A.OnAnnounce)

-- Out of the battleground (or into an arena): forget what waits.
ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    if not A.InBattleground() and not Comm.demo then
        A.Clear()
    end
end)

------------------------------------------------------------------------------------------------------
-- /bh announcer
------------------------------------------------------------------------------------------------------
function A.Describe()
    local v = A.Voice()
    return "Kill announcer: " .. (v == "off" and "off" or (v .. (A.Quiet() and ", quiet" or ", normal volume")))
end

ns.AddCommand("announcer", "battleground kill announcer: /bh announcer off|male|female|quiet|normal|test",
function(args)
    local a = (args or ""):lower():match("^(%S*)")
    if A.VOICES[a] then
        A.SetVoice(a)
    elseif a == "quiet" or a == "normal" then
        A.SetQuiet(a == "quiet")
    elseif a == "test" then
        -- a local preview of the voice and the banner (nothing is sent)
        local me = ns.PlayerName() or "You"
        A.Push({ code = "D", killer = me, killerClassId = 1, victim = "Brenna", victimClassId = 8 })
        A.Push({ code = "S", killer = me, killerClassId = 1, victim = "Brenna", victimClassId = 8 })
    end
    ns.Print(A.Describe())
end)
