-- The battleground kill announcer (docs/BleakholdProtocol.md section 18, Announcer.lua): BGANN through the real
-- receive path, the play order (multi-kill first), the busy-until time from the real line lengths, the waiting queue
-- with its priorities, the settings (Off / Male / Female, Normal / Quiet, the Royale settings carried over), where it
-- plays (feature bit 8192, battlegrounds only, never an arena), missing sound files, and AnnouncerData.lua against
-- the WAV files in Sounds/Announcer.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local BITS = { [6] = 8192 }
local DIR = "Interface\\AddOns\\Bleakhold\\Sounds\\Announcer\\"

-- Connected with the announcer bit, inside a battleground; every PlaySoundFile call is recorded with its time.
local function setup(M, opts)
    opts = opts or {}
    FX.connect(M, H, opts.bits or BITS)
    M.inInstance, M.instanceType = opts.inInstance ~= false, opts.instanceType or "pvp"
    local played = {}
    M.env.PlaySoundFile = function(path)
        played[#played + 1] = { path = path, at = M.now }
        return 1
    end
    return played
end

local function bgann(M, killer, victim, multi, streak)
    H.send(M, "BGANN", { { killer, 1, victim or "Brenna", 8, multi or "", streak or "" } })
end

local function file(path)
    return path:match("([^\\]+)%.wav$")
end

local function seconds(ns, set, line)
    return ns.ANNOUNCER_SECONDS[set][line]
end

------------------------------------------------------------------------------------------------------
-- The queue
------------------------------------------------------------------------------------------------------
test("announcer: a multi-kill plays before the streak, each after the other has finished", function(M, ns)
    local played = setup(M)
    local A = ns.Announcer
    bgann(M, "Aldric", "Dalia", "T", "S")
    M.Advance(0.05, 0.01)
    H.eq(#played, 1, "one line at a time")
    H.eq(played[1].path, DIR .. "male\\triplekill.wav")
    H.contains(A.banner.title:GetText(), "Aldric")
    H.contains(A.banner.title:GetText(), ": TRIPLE KILL")
    H.contains(A.banner.sub:GetText(), "killed ")
    H.contains(A.banner.sub:GetText(), "Dalia")
    H.ok(A.banner:IsShown(), "the banner shows")
    local len = seconds(ns, "male", "triplekill")
    H.ok(math.abs(A.busyUntil - (played[1].at + len + A.GAP)) < 1e-6, "busy for the line's real length")
    M.Advance(len + A.GAP - 0.1, 0.01)
    H.eq(#played, 1, "the triple kill is still playing")
    M.Advance(0.2, 0.01)
    H.eq(#played, 2, "then the streak")
    H.eq(file(played[2].path), "killingspree")
    H.ok(played[2].at - played[1].at >= len + A.GAP - 1e-6, "never overlapping: " .. (played[2].at - played[1].at))
    H.contains(A.banner.title:GetText(), ": KILLING SPREE")
    M.Advance(seconds(ns, "male", "killingspree") + 0.5, 0.05)
    H.ok(not A.banner:IsShown(), "the banner goes after the last line")
end)

test("announcer: every code has its line, file and title; holy shit and rampage repeat", function(M, ns)
    local played = setup(M)
    local A = ns.Announcer
    local want = {
        F = "firstblood", D = "doublekill", T = "triplekill", U = "ultrakill", R = "rampage", S = "killingspree",
        O = "dominating", K = "megakill", N = "unstoppable", W = "wickedsick", M = "monsterkill", G = "godlike",
        H = "holyshit",
    }
    local n = 0
    for code, f in pairs(want) do
        n = n + 1
        H.eq(A.LINES[code].file, f, code)
        local multi = (code == "D" or code == "T" or code == "U" or code == "R") and code or nil
        bgann(M, "Aldric", "Brenna", multi, not multi and code or nil)
        M.Advance(2.8, 0.05)
        H.eq(file(played[#played].path), f, "line for " .. code)
    end
    H.eq(n, 13)
    bgann(M, "Aldric", "Corwin", "R", "H")
    M.Advance(5, 0.05)
    H.eq(file(played[#played - 1].path), "rampage")
    H.eq(file(played[#played].path), "holyshit")
end)

test("announcer: at most two lines wait; the lowest go first, a newer one of equal rank stays", function(M, ns)
    local played = setup(M)
    local A = ns.Announcer
    bgann(M, "Aldric", "Brenna", nil, "F")         -- plays at once
    bgann(M, "Corwin", "Dalia", "D", nil)          -- waits
    bgann(M, "Eamon", "Fenna", nil, "S")           -- waits
    bgann(M, "Garrick", "Hesper", nil, "H")        -- the double kill (lowest) goes
    M.Advance(0.05, 0.01)
    H.eq(#A.waiting, 2)
    H.eq(A.waiting[1].code, "S"); H.eq(A.waiting[2].code, "H")
    bgann(M, "Ivo", "Jory", "D", nil)              -- lower than both: dropped itself
    H.eq(#A.waiting, 2); H.eq(A.waiting[1].code, "S"); H.eq(A.waiting[2].code, "H")
    bgann(M, "Kell", "Lia", nil, "S")              -- equal to the waiting S: the older one goes
    H.eq(A.waiting[1].code, "H"); H.eq(A.waiting[2].code, "S"); H.contains(A.waiting[2].killer, "Kell")
    M.Advance(10, 0.05)
    local got = {}
    for _, p in ipairs(played) do got[#got + 1] = file(p.path) end
    H.eq(table.concat(got, " "), "firstblood holyshit killingspree", "in arrival order, nothing dropped plays")
    for i = 2, #played do
        local before = file(played[i - 1].path)
        H.ok(played[i].at - played[i - 1].at >= seconds(ns, "male", before) + A.GAP - 1e-6, "no overlap")
    end
    -- a multi-kill and streak pair keeps its order when both survive
    bgann(M, "Aldric", "Brenna", "U", "N")
    M.Advance(5, 0.05)
    H.eq(file(played[#played - 1].path), "ultrakill"); H.eq(file(played[#played].path), "unstoppable")
end)

------------------------------------------------------------------------------------------------------
-- Settings
------------------------------------------------------------------------------------------------------
test("announcer: Male by default; Female, Quiet and Off from the settings and /bh announcer", function(M, ns)
    local played = setup(M)
    local A = ns.Announcer
    H.eq(A.Voice(), "male"); H.eq(A.Quiet(), false)
    bgann(M, "Aldric", "Brenna", "D")
    M.Advance(2.5)
    H.eq(played[#played].path, DIR .. "male\\doublekill.wav")
    M.env.SlashCmdList.BLEAKHOLD("announcer female")
    M.env.SlashCmdList.BLEAKHOLD("announcer quiet")
    H.eq(ns.db.options.announcerVoice, "female"); H.eq(ns.db.options.announcerQuiet, true)
    bgann(M, "Aldric", "Brenna", "T")
    M.Advance(2.5)
    H.eq(played[#played].path, DIR .. "female_quiet\\triplekill.wav")
    H.ok(math.abs(A.busyUntil - (played[#played].at + seconds(ns, "female_quiet", "triplekill") + A.GAP)) < 1e-6,
        "the quiet set's length")
    M.env.SlashCmdList.BLEAKHOLD("announcer normal")
    bgann(M, "Aldric", "Brenna", "U")
    M.Advance(2.5)
    H.eq(played[#played].path, DIR .. "female\\ultrakill.wav")
    -- Off: no voice, the banner still shows, paced without a sound
    M.env.SlashCmdList.BLEAKHOLD("announcer off")
    local n = #played
    bgann(M, "Aldric", "Brenna", "R", "W")
    M.Advance(0.1)
    H.eq(#played, n, "voice off")
    H.contains(A.banner.title:GetText(), ": RAMPAGE")
    M.Advance(A.SILENT_SECONDS + A.GAP + 0.1)
    H.contains(A.banner.title:GetText(), ": WICKED SICK", "the next banner after the silent pace")
    H.eq(#played, n)
    -- a value the addon does not know reads as the default
    ns.db.options.announcerVoice = "robot"
    H.eq(A.Voice(), "male")
    M.env.SlashCmdList.BLEAKHOLD("announcer robot")
    H.eq(ns.db.options.announcerVoice, "robot", "unknown words change nothing")
end)

test("announcer: the Tasks page holds the settings whenever bit 8192 is on, Royale off too", function(M, ns)
    setup(M)   -- the announcer bit alone: Bleakhold Royale is off on this realm
    local nav
    for _, b in ipairs(ns.Activities.nav) do
        if b.key == "royale" then nav = b end
    end
    H.ok(not nav:IsShown(), "no Royale page on this realm")
    ns.UI.Open("tasks")
    M.Advance(0.3)
    local ann = ns.Activities.tasksPage.announcer
    H.ok(ann:IsVisible(), "the settings without Royale")
    H.eq(ann.title:GetText(), "Kill Announcer", "a Title Case heading")
    H.eq(ann.voice.label:GetText(), "Voice: Male", "the default")
    H.eq(ann.volume.label:GetText(), "Volume: Normal")
    ann.voice:SetValue("female")
    ann.volume:SetValue("quiet")
    H.eq(ns.Announcer.Voice(), "female"); H.eq(ns.Announcer.Quiet(), true)
    H.eq(ns.db.options.announcerVoice, "female"); H.eq(ns.db.options.announcerQuiet, true)
    -- the slash commands change the same settings, and the page shows them
    M.env.SlashCmdList.BLEAKHOLD("announcer off")
    M.env.SlashCmdList.BLEAKHOLD("royale normal")
    ns.Activities.tasksPage:Refresh()
    H.eq(ann.voice.label:GetText(), "Voice: Off"); H.eq(ann.volume.label:GetText(), "Volume: Normal")
    -- no weekly task: the box takes the weekly tasks' place (their heading is hidden)
    local page = ns.Activities.tasksPage
    local _, rel, relPoint, _, y = ann:GetPoint(1)
    local _, _, _, _, weeklyY = page.weeklyTitle:GetPoint(1)
    H.ok(not page.weeklyTitle:IsShown() and rel == page and relPoint == "TOPLEFT" and y == weeklyY,
        "in the weekly tasks' place: " .. tostring(y))
    -- with weekly tasks it sits under them, as wide as the task column, above the page's bottom padding
    H.send(M, "TASKS", { { 1, 0, 0, "G" }, { 201, "W", 4, 1, 3, "C", 150, "", 0 } })
    M.Advance(0.3)
    page:Refresh()
    _, rel, relPoint, _, y = ann:GetPoint(1)
    local _, _, _, _, row3 = page.rows[3]:GetPoint(1)
    H.ok(page.weeklyTitle:IsShown() and rel == page and relPoint == "TOPLEFT"
        and y == row3 - page.rows[3]:GetHeight() - 10, "10 px under the third weekly row: " .. tostring(y))
    H.eq(ann:GetWidth(), page.rows[1]:GetWidth())
    H.ok(-y + ann:GetHeight() <= ns.Activities.CH - ns.Activities.PAD, "inside the page")
    -- the Royale page no longer carries them
    H.eq(ns.Royale.page.last.voice, nil)
    H.eq(ns.Royale.page.last.volume, nil)
end)

test("announcer: the settings follow feature bit 8192 at runtime, with or without Royale", function(M, ns)
    FX.connect(M, H, { [6] = 4096 })
    ns.UI.Open("tasks")
    M.Advance(0.3)
    local ann = ns.Activities.tasksPage.announcer
    H.ok(not ann:IsShown(), "no announcer on this realm: no settings, even with Royale")
    H.hello(M, BITS)
    M.Advance(0.3)
    H.ok(ann:IsVisible(), "the server turned the announcer on")
    H.hello(M, { [6] = 4096 })
    M.Advance(0.3)
    H.ok(not ann:IsShown(), "and off again")
end)

test("announcer: the Royale announcer's settings carry over once", function(M, ns)
    H.eq(ns.db.options.announcerVoice, "female")
    H.eq(ns.db.options.announcerQuiet, true)
    H.eq(ns.db.options.royaleVoice, nil); H.eq(ns.db.options.royaleQuiet, nil)
end, { before = function(M)
    M.env.BleakholdDB = { options = { royaleVoice = "female", royaleQuiet = true } }
end })

------------------------------------------------------------------------------------------------------
-- Where it plays
------------------------------------------------------------------------------------------------------
test("announcer: never in an arena, the open world, a dungeon, or without feature bit 8192", function(M, ns)
    local played = setup(M, { instanceType = "arena" })
    local A = ns.Announcer
    bgann(M, "Aldric", "Brenna", "D", "F")
    M.Advance(3)
    H.eq(#played, 0, "arena")
    H.ok(not A.banner:IsShown())
    M.inInstance, M.instanceType = false, "none"
    bgann(M, "Aldric", "Brenna", "D")
    M.inInstance, M.instanceType = true, "party"
    bgann(M, "Aldric", "Brenna", "D")
    M.Advance(3)
    H.eq(#played, 0, "open world and dungeon")
    -- a battleground the client reports as an arena (rated or skirmish arena maps)
    M.inInstance, M.instanceType = true, "pvp"
    M.env.IsActiveBattlefieldArena = function() return 1, nil end
    bgann(M, "Aldric", "Brenna", "D")
    M.Advance(3)
    H.eq(#played, 0, "IsActiveBattlefieldArena")
    M.env.IsActiveBattlefieldArena = function() return nil end
    bgann(M, "Aldric", "Brenna", "D")
    M.Advance(3)
    H.eq(#played, 1, "a battleground plays")
    -- without the bit the realm has no announcer
    H.hello(M, { [6] = 0 })
    M.Advance(0.3)
    bgann(M, "Aldric", "Brenna", "T")
    M.Advance(3)
    H.eq(#played, 1, "no feature bit")
    H.eq(ns.S.bgAnnounce.multi, "T", "still parsed")
end)

test("announcer: leaving the battleground forgets the waiting lines", function(M, ns)
    local played = setup(M)
    local A = ns.Announcer
    bgann(M, "Aldric", "Brenna", "D", "S")
    bgann(M, "Corwin", "Dalia", "T")
    M.Advance(0.1)
    H.eq(#A.waiting, 2)
    M.inInstance, M.instanceType = false, "none"
    M.FireEvent("PLAYER_ENTERING_WORLD")
    H.eq(#A.waiting, 0)
    H.ok(not A.banner:IsShown())
    M.Advance(5)
    H.eq(#played, 1, "only the line already playing (it cannot be stopped)")
end)

test("announcer: garbage BGANN is ignored; unknown codes are dropped", function(M, ns)
    local played = setup(M)
    H.send(M, "BGANN", { { "Aldric", 1, "Brenna", 8, "X", "Y" } })
    H.send(M, "BGANN", { { "", 1, "Brenna", 8, "D", "" } })
    H.send(M, "BGANN", { { "Aldric", 1, "", 8, "D", "" } })
    H.send(M, "BGANN", { { "Aldric", 1, "Brenna", 8 } })
    H.send(M, "BGANN", { { "|cffff0000Evil|r", 99999, "Brenna", -5, "DD", "S" } })
    M.Advance(3)
    H.eq(#played, 1, "only the last one, its streak")
    H.eq(file(played[1].path), "killingspree")
    H.contains(ns.Announcer.banner.title:GetText(), "||cffff0000Evil||r", "pipes doubled")
end)

------------------------------------------------------------------------------------------------------
-- Missing files
------------------------------------------------------------------------------------------------------
test("announcer: a line without a sound file shows its banner and keeps the queue moving", function(M, ns)
    local played = setup(M)
    local A = ns.Announcer
    ns.ANNOUNCER_SECONDS.male.doublekill = nil       -- a file the table does not list
    bgann(M, "Aldric", "Brenna", "D", "S")
    M.Advance(0.05, 0.01)
    H.eq(#played, 0, "no PlaySoundFile for a missing line")
    H.contains(A.banner.title:GetText(), ": DOUBLE KILL")
    M.Advance(A.SILENT_SECONDS + A.GAP + 0.05, 0.01)
    H.eq(#played, 1)
    H.eq(file(played[1].path), "killingspree")
    -- a whole set missing from the table
    ns.ANNOUNCER_SECONDS.female = nil
    A.SetVoice("female")
    bgann(M, "Aldric", "Brenna", "T")
    M.Advance(3)
    H.eq(#played, 1, "silent")
    -- no PlaySoundFile at all
    A.SetVoice("male")
    M.env.PlaySoundFile = nil
    bgann(M, "Aldric", "Brenna", "U")
    M.Advance(3)
    H.contains(A.banner.title:GetText() or "", "ULTRA KILL")
end)

-- WAV length from the RIFF chunks (like Tools/Announcer/import_sounds.py, written again here).
local function u32(s, i)
    local a, b, c, d = s:byte(i, i + 3)
    return a + b * 256 + c * 65536 + d * 16777216
end

local function u16(s, i)
    local a, b = s:byte(i, i + 1)
    return a + b * 256
end

local function wavInfo(data)
    if not data or data:sub(1, 4) ~= "RIFF" or data:sub(9, 12) ~= "WAVE" then
        return nil
    end
    local pos, info, size = 13, nil, nil
    while pos + 7 <= #data do
        local id, len = data:sub(pos, pos + 3), u32(data, pos + 4)
        if id == "fmt " then
            info = { tag = u16(data, pos + 8), channels = u16(data, pos + 10), rate = u32(data, pos + 12),
                align = u16(data, pos + 20), bits = u16(data, pos + 22) }
        elseif id == "data" then
            size = math.min(len, #data - pos - 7)
        end
        pos = pos + 8 + len + (len % 2)
    end
    if not info or not size then
        return nil
    end
    info.seconds = math.floor(size / info.align) / info.rate
    return info
end

test("announcer: every line of every set ships as 16-bit PCM WAV, and AnnouncerData.lua has its real length",
function(M, ns)
    local sets = { "male", "female", "male_quiet", "female_quiet" }
    local count = 0
    for _, set in ipairs(sets) do
        H.ok(type(ns.ANNOUNCER_SECONDS[set]) == "table", "AnnouncerData.lua lists " .. set)
        for code, line in pairs(ns.Announcer.LINES) do
            local path = addonDir .. "/Sounds/Announcer/" .. set .. "/" .. line.file .. ".wav"
            local info = wavInfo(host_readfile(path))
            H.ok(info, "a WAV file: " .. path)
            if info then
                H.ok(info.tag == 1 and info.bits == 16 and (info.channels == 1 or info.channels == 2),
                    path .. ": 16-bit PCM")
                local listed = ns.ANNOUNCER_SECONDS[set][line.file]
                local want = math.ceil(info.seconds * 1000 - 1e-9) / 1000
                H.ok(type(listed) == "number" and math.abs(listed - want) < 0.0005,
                    set .. "/" .. line.file .. ": " .. tostring(listed) .. " s listed, the file has " .. want
                    .. " s (run python3 -I Tools/Announcer/import_sounds.py)")
                H.ok(listed and listed < 4, "a line under 4 s (" .. code .. ")")
                count = count + 1
            end
        end
    end
    H.eq(count, 52)
    H.ok(host_readfile(addonDir .. "/Sounds/Announcer/CREDITS.txt"):find("Kokoro%-82M"), "the credit ships")
end)

test("announcer: /bh demo previews the announcer in the Royale match", function(M, ns)
    local played = {}
    -- the announcer's lines only (the Royale HUD plays its own ticks, wind and landing from Sounds\Royale)
    M.env.PlaySoundFile = function(path)
        if path:find(DIR, 1, true) == 1 then played[#played + 1] = path end
    end
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    ns.Royale.Join()
    M.Advance(5)
    if M.env.BleakholdRoyaleReady:IsShown() then
        M.env.BleakholdRoyaleReady.accept:Click()
    end
    M.Advance(55)   -- first blood at the landing, 47 s in (the drop takes 20 s), the double kill 4 s later
    H.ok(#played >= 2, "first blood and the double kill: " .. #played)
    H.eq(played[1], DIR .. "male\\firstblood.wav")
    M.env.SlashCmdList.BLEAKHOLD("demo off")
end)
