-- Consistency checks between the addon, its art and the 3.3.5a rules.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function fileExistsCI(path)
    -- the client resolves loose files case-insensitively; the repo spelling is checked by lint too
    return host_readfile(path) ~= nil
end

-- Stock 3.3.5a art the addon may use (the WoW look: dialog and tooltip frames, red panel buttons, the minimap ring,
-- bars, LFG art, tabs, icons, ...). It is in every client's MPQs and never in this repository, so the path cannot be
-- checked against a file here: only these folders of Interface\ are allowed, each named explicitly.
local STOCK_PREFIXES = {
    -- a subfolder before its parent (the first prefix that matches decides)
    "Minimap\\Tracking",
    "DialogFrame", "Tooltips", "Buttons", "Minimap", "TargetingFrame", "LFGFrame", "QuestFrame", "PaperDollInfoFrame",
    "AchievementFrame", "Common", "Icons", "ChatFrame", "PVPFrame", "CharacterFrame", "OptionsFrame", "FriendsFrame",
    "WorldStateFrame", "MoneyFrame", "Glues\\CharacterCreate", "CastingBar", "RaidFrame",
}
-- Interface\<prefix>\<file> with a plain file name (no extension, no deeper folder, no '/' or '..'), any case
local function stockPath(path)
    local low = path:lower()
    for _, p in ipairs(STOCK_PREFIXES) do
        local pre = "interface\\" .. p:lower() .. "\\"
        if low:sub(1, #pre) == pre then
            local name = path:sub(#pre + 1)
            return name:match("^[%w_%-!]+$") ~= nil and not name:find("%.%a%a%a$")
        end
    end
    return false
end
-- The dungeon pictures (the owner's Journal art, PLAN decision 4) reach players through the launcher's extra/ layer
-- as Interface\AddOns\Bleakhold\Art\Journal\bg_<KEY> and btn_<KEY>; they are never in the repository, so the code
-- probes them and falls back (see the test below).
local JOURNAL = "^Interface\\AddOns\\Bleakhold\\Art\\Journal\\"
local function journalPath(path)
    local name = path:match(JOURNAL .. "(.+)$")
    return name ~= nil and (name:match("^bg_[A-Z0-9]+$") or name:match("^btn_[A-Z0-9]+$")) ~= nil
end

test("the stock art allow-list accepts stock files only", function(M, ns)
    H.ok(stockPath("Interface\\DialogFrame\\UI-DialogBox-Border"), "dialog border")
    H.ok(stockPath("Interface\\Minimap\\MiniMap-TrackingBorder"), "minimap ring")
    H.ok(stockPath("Interface\\MINIMAP\\MiniMap-TrackingBorder"), "any case, like the client")
    H.ok(stockPath("Interface\\Icons\\INV_Misc_QuestionMark"), "icon")
    H.ok(stockPath("Interface\\Glues\\CharacterCreate\\CharacterCreate-LabelFrame"), "dropdown label frame")
    H.ok(not stockPath("Interface\\Glues\\LoadingScreens\\LoadScreenDeadmines"), "a folder not on the list")
    H.ok(not stockPath("Interface\\Buttons\\Sub\\File"), "no deeper folder")
    H.ok(stockPath("Interface\\Minimap\\Tracking\\None"), "a subfolder on the list (the tracking magnifier)")
    H.ok(not stockPath("Interface\\Buttons\\UI-Panel-Button-Up.tga"), "no extension")
    H.ok(not stockPath("Interface\\Buttons\\"), "a file, not the folder")
    H.ok(not stockPath("Interface\\AddOns\\Other\\Art"), "another addon's art")
    H.ok(journalPath("Interface\\AddOns\\Bleakhold\\Art\\Journal\\bg_SCHOLOMANCE"), "journal picture")
    H.ok(journalPath("Interface\\AddOns\\Bleakhold\\Art\\Journal\\btn_UTGARDEPINNACLE"), "journal button")
    H.ok(not journalPath("Interface\\AddOns\\Bleakhold\\Art\\Journal\\other"), "only bg_ and btn_ files")
end)

test("glyph names in Widgets.lua match the atlas order in make_art.py", function(M, ns)
    local py = host_readfile(repo .. "/Tools/UiLint/make_art.py")
    local block = py:match("GLYPHS = %[(.-)\n%]")
    local names = {}
    for name in block:gmatch('%(%"([%w_]+)%",') do names[#names + 1] = name end
    H.eq(#names, #ns.UI.GLYPHS, "glyph count")
    for i, n in ipairs(names) do
        H.eq(ns.UI.GLYPHS[i], n, "glyph " .. i)
    end
    H.ok(#names <= 32, "fits the 8 x 4 atlas")
end)

test("emote glyph names in Widgets.lua match the emote atlas order in make_art.py", function(M, ns)
    local py = host_readfile(repo .. "/Tools/UiLint/make_art.py")
    local block = py:match("EMOTE_GLYPHS = %[(.-)\n%]")
    local names = {}
    for name in block:gmatch('\n    %(%"([%w_]+)%",') do names[#names + 1] = name end
    H.eq(#names, #ns.UI.EMOTE_GLYPHS, "emote glyph count")
    for i, n in ipairs(names) do
        H.eq(ns.UI.EMOTE_GLYPHS[i], n, "emote glyph " .. i)
    end
    H.ok(#names <= 32, "fits the 8 x 4 atlas")
end)

test("every texture the addon sets exists, and fonts are stock client fonts", function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    FX.openEverything(M, ns)
    -- emoji icons: a page of the Emojis filter, the wheel editor's emoji page and the emoji preview
    local A = ns.Animations
    A.tab.filter:SetValue("emoji")
    A.Select(A.Filtered("", "emoji")[1])
    A.SetWheelPage(4)
    M.Advance(40)
    local n, emojis = 0, 0
    for path in pairs(M.textures) do
        local sub = path:match("^Interface\\AddOns\\Bleakhold\\(.+)$")
        local emoji = path:match("^Interface\\Bleakhold\\Emoji\\Emoji%d%d%d$")
        if path == ns.Royale.MARKER then
            -- Bleakhold Royale's patch gate: a marker MapForge packs into patch-Q (archives.marker_texture of
            -- bleakhold_royale_v2.json; v1's Marker would let a client with the old map patch queue)
            H.eq(path, "Interface\\Bleakhold\\Royale\\MarkerV2", "the patch marker MapForge packs")
        elseif path:find(JOURNAL) then
            -- the Journal art comes from the launcher, not the repo: only its file names are checked
            H.ok(journalPath(path), "a Journal picture (bg_<KEY> or btn_<KEY>): " .. path)
        elseif sub then
            local file = addonDir .. "/" .. sub:gsub("\\", "/")
            H.ok(fileExistsCI(file .. ".tga") or fileExistsCI(file .. ".blp") or fileExistsCI(file), "texture file for " .. path)
            n = n + 1
        elseif emoji then
            -- emoji bubbles art, shipped as loose files in Data\Interface\Bleakhold\Emoji (Tools/EmojiForge)
            H.ok(fileExistsCI(repo .. "/" .. path:gsub("\\", "/") .. ".blp"), "emoji art for " .. path)
            emojis = emojis + 1
        else
            H.ok(stockPath(path), "outside the addon only stock art of the allow-list: " .. path)
        end
    end
    H.ok(n >= 6, "addon textures used: " .. n)
    H.ok(emojis >= 14, "emoji textures used: " .. emojis)
    local stock = { ["Fonts\\FRIZQT__.TTF"] = true, ["Fonts\\MORPHEUS.TTF"] = true, ["Fonts\\ARIALN.TTF"] = true }
    for path in pairs(M.fonts) do
        -- or a face the addon ships in Fonts\ (the Royale style kit's Marcellus SC, OFL; RoyaleStyle.lua RS.FONT_SC)
        local own = path:match("^Interface\\AddOns\\Bleakhold\\(Fonts\\[^\\]+%.ttf)$")
        H.ok(stock[path] or (own and fileExistsCI(addonDir .. "/" .. own:gsub("\\", "/"))), "stock font: " .. path)
    end
end)

test("the Journal art is optional: without its files no shown texture is left on a missing Journal picture",
    function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    FX.openEverything(M, ns)
    M.Advance(1)
    local left = {}
    for _, o in ipairs(M.objects) do
        -- the last file this texture asked for is a Journal picture that did not load: the code must fall back (stock
        -- LFG art, or no art) or hide it, never keep showing what it had before
        if o.__otype == "Texture" and type(o.__tried) == "string" and o.__tried:find(JOURNAL) and o:IsVisible() then
            left[#left + 1] = o.__tried
        end
    end
    H.ok(#left == 0, #left .. " textures kept a missing Journal picture: " .. table.concat(left, ", "))
end, { before = function(M)
    setmetatable(M.missingTextures, { __index = function(_, path)
        return (type(path) == "string" and path:find(JOURNAL)) and true or nil
    end })
end })

test("every emoji of the catalogue has its art in the repo", function(M, ns)
    H.ok(#ns.Data.emojis >= 1, "emoji catalogue loaded")
    for _, m in ipairs(ns.Data.emojis) do
        H.ok(m.texture:match("^Interface\\Bleakhold\\Emoji\\Emoji%d%d%d$"), "emoji texture path " .. m.texture)
        H.ok(fileExistsCI(repo .. "/" .. m.texture:gsub("\\", "/") .. ".blp"), "emoji art for " .. m.key)
    end
end)

test("the ten stock classes only (no extra built-in classes)", function(M, ns)
    local ids = {}
    for _, c in ipairs(ns.Data.classes) do ids[#ids + 1] = c.id end
    H.eq(table.concat(ids, ","), "1,2,3,4,5,6,7,8,9,11")
    H.eq(#ns.Classes(), 10)
end)

test("extra classes come only from the server (DEF X)", function(M, ns)
    FX.connect(M, H)
    H.send(M, "DEF", { { "X", 7 }, { 12, "Bleakhold Warden", "WARDEN", "8FD6E4", "WRD" } })
    H.eq(#ns.Classes(), 11)
    H.eq(ns.Classes()[11].name, "Bleakhold Warden")
end)

test("server definitions override the built-in fallback and persist per dataVer", function(M, ns)
    FX.connect(M, H, { [5] = 9 })
    M.Advance(0.3)
    H.contains(H.lastIntent(M, "GET").payload, "DEF,0", "new dataVer asks for definitions")
    H.send(M, "DEF", { { "A", 9 }, { 1, "Fortified (server)", "Server text" } })
    H.eq(ns.DefName("A", 1), "Fortified (server)")
    H.eq(M.env.BleakholdDB.defsVer, nil, "not complete before DEF Z")
    H.send(M, "DEF", { { "Z", 9 } })
    H.eq(M.env.BleakholdDB.defsVer, 9)
    H.eq(ns.DefName("A", 3), "Bolstering", "built-in fallback for the rest")
end)

local function defGets(M)
    local n = 0
    for _, it in ipairs(H.intents(M)) do
        if it.op == "GET" and it.payload:find("^DEF,0") then n = n + 1 end
    end
    return n
end

test("a definitions cache of an older addon (no DEF schema) is fetched again, even with the server's dataVer",
    function(M, ns)
    H.eq(H.lastIntent(M, "HELLO").fields[3], "0", "HELLO gives no dataVer for a cache of another schema")
    FX.connect(M, H, { [5] = 9 })
    H.eq(defGets(M), 1, "the cache of dataVer 9 without V and Q is not trusted")
    H.eq(M.env.BleakholdDB.defsSchema, nil, "cleared until the new set is complete")
    H.send(M, "DEF", { { "Q", 9 }, { 101, 0, 3, 2, "T", 2090, 1, "Challenger" } })
    H.send(M, "DEF", { { "Z", 9 } })
    H.eq(M.env.BleakholdDB.defsVer, 9)
    H.eq(M.env.BleakholdDB.defsSchema, ns.DEF_SCHEMA)
    H.hello(M, { [5] = 9 })
    M.Advance(0.3)
    H.eq(defGets(M), 1, "a complete cache of this schema is kept")
    ns.Comm.SendHello()
    H.eq(H.lastIntent(M, "HELLO").fields[3], "9", "and its dataVer is the hint again")
end, { before = function(M)
    M.env.BleakholdDB = { defsVer = 9, defs = { A = { [1] = { name = "Fortified (old)", text = "" } } } }
end })

test("globals created at runtime are Bleakhold-prefixed (or required by FrameXML)", function(M, ns)
    local allowed = { SLASH_BLEAKHOLD1 = true, SLASH_BLEAKHOLD2 = true, ToggleCollectionsJournal = true, BINDING_HEADER_BLEAKHOLD = true }
    local fresh = {}
    for k in pairs(M.env) do
        if type(k) == "string" and (k:find("^Bleakhold") or allowed[k] or k:find("^BINDING_NAME_BLEAKHOLD_")) then
            fresh[#fresh + 1] = k
        end
    end
    H.ok(#fresh > 10, "addon globals present")
    for k, v in pairs(M.env) do
        if type(k) == "string" and type(v) == "table" and v.__otype and v.__name == k then
            -- StaticPopup1..4 and their parts are FrameXML's dialogs (the mock builds them like StaticPopup.xml)
            if not (k:find("^Bleakhold") or k:find("^ChatFrame") or k:find("^StaticPopup%d") or ({ UIParent = 1, Minimap = 1, MinimapCluster = 1, MinimapBackdrop = 1, GameTooltip = 1, ItemRefTooltip = 1, ShoppingTooltip1 = 1, ShoppingTooltip2 = 1, UIErrorsFrame = 1, WatchFrame = 1, SendMailNameEditBox = 1, LFDParentFrame = 1 })[k]) then
                error("unexpected named frame " .. k)
            end
        end
    end
end)

test("demo fixtures parse cleanly through the real receive path", function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
    FX.openEverything(M, ns)
    ns.UI.Open("keys")
    ns.Keys.start:Click()
    M.Advance(45)
    -- the demo's queue and its group proposal (the Dungeon Journey page starts runs with the server's own commands
    -- now, which the demo does not answer: these intents still exercise the demo's QUEUE frames)
    ns.UI.Open("dungeons")
    ns.Comm.Send("QJOIN", "D", 389, 0, 4, 3)
    M.Advance(5)
    ns.Comm.Send("QREPLY", 4242, 1)
    M.Advance(10)
    local dropped = 0
    for _, v in pairs(ns.Comm.stats.dropped) do dropped = dropped + v end
    H.eq(dropped, 0, "no frame dropped")
    H.eq(ns.Comm.stats.unknown, 0, "no unknown op")
    H.ok(ns.Comm.stats.framesIn > 40, "frames fed: " .. ns.Comm.stats.framesIn)
    H.ok(ns.S.mplus and ns.S.mplus.result and ns.S.mplus.result.result == 1, "demo key run finished in time")
    M.env.SlashCmdList.BLEAKHOLD("demo off")
    H.eq(ns.Comm.demo, nil)
    H.eq(ns.S.week, nil, "demo state cleared")
end)

test("saved window positions are applied once saved variables load", function(M, ns)
    H.eq(select(4, M.env.BleakholdSeasonFrame:GetPoint(1)), 33)
    H.eq(select(5, M.env.BleakholdSeasonFrame:GetPoint(1)), -44)
end, { before = function(M)
    M.env.BleakholdCharDB = { windows = { BleakholdSeasonFrame = { point = "TOPLEFT", relPoint = "TOPLEFT", x = 33, y = -44 } } }
end })

test("demo mode leaves the server and saved definitions alone", function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(2)
    ns.Comm.Get("DEF", 0)
    M.Advance(1)
    H.eq(M.env.BleakholdDB.defs, nil, "demo DEFs are not saved")
    local before = #M.sent
    -- a real server frame arriving during the demo is ignored
    H.deliver(M, "1 WEEK 9 1/1 50,1,1,1,1,1")
    H.ok(ns.S.week.coins ~= 1, "server frame ignored in demo")
end)

-- No all-caps captions or titles outside the Royale HUD kit: 3.3.5a writes window titles, headings and labels in Title
-- Case ("Dungeon Finder", "This Week's Affixes"), so text is never upper-cased for show and never written in capitals.
-- Checked in the source: string.upper / :upper() inside the arguments of a text setter, and a string literal there
-- with a word of four or more capitals (compared values and table keys aside; PvP, XP, 1v1 and the like are short or
-- mixed case anyway).
local CAPS_ALLOW = { FXAA = true, SMAA = true, SSAO = true }
local TEXT_SETTERS = { "SetText", "SetFormattedText", "SetLabel", "UI%.Heading", "UI%.Label" }
local function callArgs(line, open)
    local depth = 0
    for i = open, #line do
        local ch = line:sub(i, i)
        if ch == "(" then
            depth = depth + 1
        elseif ch == ")" then
            depth = depth - 1
            if depth == 0 then
                return line:sub(open + 1, i - 1)
            end
        end
    end
    return line:sub(open + 1)
end
local function capsProblems(file, src)
    local out, n = {}, 0
    for line in (src .. "\n"):gmatch("([^\n]*)\n") do
        n = n + 1
        local code = line:gsub("^%s*%-%-.*$", "")
        for _, setter in ipairs(TEXT_SETTERS) do
            local pos = 1
            while true do
                local _, e = code:find(setter .. "%(", pos)
                if not e then
                    break
                end
                local args = callArgs(code, e)
                if args:find("string%.upper") or args:find("[:%.]upper%(") then
                    out[#out + 1] = file .. ":" .. n .. ": upper-cased text"
                end
                local plain = args:gsub("\\\"", "")
                for q1, lit, q2 in plain:gmatch("()\"([^\"]*)\"()") do
                    local before, after = plain:sub(1, q1 - 1), plain:sub(q2)
                    if not before:find("[=~]=%s*$") and not after:find("^%s*[=~]=") and not before:find("%[%s*$") then
                        local text = lit:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|T.-|t", ""):gsub("|H.-|h", "")
                        for word in text:gmatch("%u%u%u%u+") do
                            if not CAPS_ALLOW[word] then
                                out[#out + 1] = file .. ":" .. n .. ": all-caps \"" .. lit .. "\""
                                break
                            end
                        end
                    end
                end
                pos = e + 1
            end
        end
    end
    return out
end

test("no all-caps captions: never upper-cased or written in capitals (Royale HUD kit aside, its page in)",
    function(M, ns)
    -- the rule itself
    H.eq(#capsProblems("x", 'fs:SetText(string.upper(name))'), 1, "string.upper")
    H.eq(#capsProblems("x", 'UI.SetText(win.title, (c.title or name):upper())'), 1, ":upper()")
    H.eq(#capsProblems("x", 'label:SetText("YOUR WEEK")'), 1, "a caption in capitals")
    H.eq(#capsProblems("x", 'q:SetText(board == "A" and "YOUR STANDING" or "Your Best")'), 1, "after a comparison")
    H.eq(#capsProblems("x", 'e:SetText(kind == "MOUNT" and "No mounts yet." or "No pets yet.")'), 0, "a compared value")
    H.eq(#capsProblems("x", 'fs:SetText("|cffFFD100Your Week|r PvP 1v1 XP FXAA")'), 0, "colour codes, PvP, XP")
    H.eq(#capsProblems("x", '-- fs:SetText("YOUR WEEK")'), 0, "a comment")
    local toc = host_readfile(addonDir .. "/Bleakhold.toc")
    local found, files = {}, 0
    -- the Royale HUD kit (its own approved look) aside; Royale.lua holds the Bleakhold Royale page of Activities,
    -- which is checked with the other windows
    local KIT = { "RoyaleStyle", "RoyaleHud", "RoyaleCountdown", "RoyaleDrop", "RoyaleMap", "RoyaleMinimap",
        "RoyaleArtData" }
    local kit = {}
    for _, n in ipairs(KIT) do
        kit[n .. ".lua"] = true
    end
    H.ok(toc:find("Royale.lua", 1, true) ~= nil, "Royale.lua is in the toc")
    local royaleChecked = false
    for name in toc:gmatch("([%w_]+%.lua)") do
        if name == "Royale.lua" then
            royaleChecked = true
        end
        if not kit[name] then
            files = files + 1
            for _, p in ipairs(capsProblems(name, host_readfile(addonDir .. "/" .. name) or "")) do
                found[#found + 1] = p
            end
        end
    end
    H.ok(files > 20, "files checked: " .. files)
    H.ok(royaleChecked, "the Royale page (Royale.lua) is checked")
    H.ok(#found == 0, #found .. " all-caps texts:\n    " .. table.concat(found, "\n    "))
end)
