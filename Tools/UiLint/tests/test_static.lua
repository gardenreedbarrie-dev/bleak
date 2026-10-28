-- Consistency checks between the addon, its art and the 3.3.5a rules.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local function fileExistsCI(path)
    -- the client resolves loose files case-insensitively; the repo spelling is checked by lint too
    return host_readfile(path) ~= nil
end

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
        elseif sub then
            local file = addonDir .. "/" .. sub:gsub("\\", "/")
            H.ok(fileExistsCI(file .. ".tga") or fileExistsCI(file .. ".blp") or fileExistsCI(file), "texture file for " .. path)
            n = n + 1
        elseif emoji then
            -- emoji bubbles art, shipped as loose files in Data\Interface\Bleakhold\Emoji (Tools/EmojiForge)
            H.ok(fileExistsCI(repo .. "/" .. path:gsub("\\", "/") .. ".blp"), "emoji art for " .. path)
            emojis = emojis + 1
        else
            H.ok(path:match("^Interface\\Icons\\"), "only stock icons outside the addon: " .. path)
        end
    end
    H.ok(n >= 6, "addon textures used: " .. n)
    H.ok(emojis >= 14, "emoji textures used: " .. emojis)
    local stock = { ["Fonts\\FRIZQT__.TTF"] = true, ["Fonts\\MORPHEUS.TTF"] = true, ["Fonts\\ARIALN.TTF"] = true }
    for path in pairs(M.fonts) do
        H.ok(stock[path], "stock font: " .. path)
    end
end)

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
            if not (k:find("^Bleakhold") or k:find("^ChatFrame") or ({ UIParent = 1, Minimap = 1, MinimapCluster = 1, MinimapBackdrop = 1, GameTooltip = 1, ItemRefTooltip = 1, ShoppingTooltip1 = 1, ShoppingTooltip2 = 1, UIErrorsFrame = 1, WatchFrame = 1, SendMailNameEditBox = 1, LFDParentFrame = 1 })[k]) then
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
    ns.UI.Open("dungeons")
    ns.Dungeons.selected = 389
    ns.Dungeons.queue.join:Click()
    M.Advance(5)
    ns.Dungeons.queue.accept:Click()
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
