-- The Bleakhold UI talent window folded into AddicatUI (UI by Addicated): WoW's own PlayerTalentFrame by default
-- (database.lua, the migration in core/api.lua), dressed by modules/talents_classic.lua: node ranks and glows, the
-- tree heading, the spec panel at its right, glyph names under the sockets and the optional glyph list, and
-- /bhui talents. AddicatUI is not loaded as a whole: the real files run against a stand-in for the parts of AddicatUI
-- they reach and stand-ins for Blizzard_TalentUI's and Blizzard_GlyphUI's frames, without AddicatUI_Art.
local AUI = repo .. "/Interface/AddOns/AddicatUI/"

local function run(M, a, rel)
    local chunk = assert(host_loadfile(AUI .. rel))
    setfenv(chunk, M.env)
    chunk("AddicatUI", a)
end

local function read(rel)
    return assert(host_readfile(repo .. "/Interface/AddOns/" .. rel), "missing " .. rel)
end

-- Delivers an event to the frames created since `from` (the file under test's own), not to the Bleakhold addon's.
local function fireNew(M, from, event, ...)
    for i = from + 1, #M.objects do
        local o = M.objects[i]
        if o.__events and o.__events[event] and o.__scripts.OnEvent then
            o.__scripts.OnEvent(o, event, ...)
        end
    end
end

local function said(M, from)
    local out = {}
    for i = from + 1, #M.chat do out[#out + 1] = M.chat[i].msg end
    return out
end

local function fakeAddicatUI(profile)
    local a = {
        L = setmetatable({}, { __index = function(_, k) return k end }),
        _dir = "Interface\\AddOns\\AddicatUI_Art\\Textures\\",
        db = { profile = profile, global = {} },
        registered = {},
    }
    function a:RegisterModule(name, module) self.registered[name] = module return true end
    function a:GetModuleConfig(name) return self.db.profile.modules and self.db.profile.modules[name] end
    function a:IsModuleEnabled(name)
        local cfg = self:GetModuleConfig(name)
        return cfg and cfg.enabled or false
    end
    return a
end

-- the three trees (GetTalentTabInfo: name, icon, points spent, background file)
local TREES = {
    { "Arcane", "Interface\\Icons\\Spell_Holy_MagicalSentry", 11, "MageArcane" },
    { "Fire", "Interface\\Icons\\Spell_Fire_FireBolt02", 0, "MageFire" },
    { "Frost", "Interface\\Icons\\Spell_Frost_FrostBolt02", 0, "MageFrost" },
}
-- the first tree's nodes (GetTalentInfo: tier, rank, max rank, prerequisites met)
local NODES = {
    { tier = 1, rank = 5, max = 5, meets = 1 },      -- maxed: gold
    { tier = 1, rank = 0, max = 3, meets = 1 },      -- a point can go in: green
    { tier = 4, rank = 0, max = 1, meets = 1 },      -- tier 4 needs 15 in the tree: locked
    { tier = 2, rank = 2, max = 3, meets = nil },    -- spent in, but its prerequisite is missing: no glow
    { tier = 1, rank = 0, max = 2, meets = 1 },      -- hidden button
}

-- the second specialization (dual spec): its points per tree and the first tree's ranks; the pet's ranks
local SPEC2_POINTS = { 0, 5, 41 }
local SPEC2_RANKS = { 0, 3, 0, 0, 0 }
local PET_RANK = 1

-- WoW's glyph sockets (GetGlyphSocketInfo: enabled, type 1 major / 2 minor, spell, icon), and the second spec's
local SOCKETS = {
    { 1, 1, 100, "Interface\\Icons\\INV_Glyph_MajorMage" },
    { 1, 2, nil },
    { nil, 2 },
    { 1, 1, 0 },
    { nil, 2 },
    { nil, 1 },
}
local SOCKETS2 = {
    { 1, 1, 101, "Interface\\Icons\\INV_Glyph_MajorMage" },
    { 1, 2, nil },
    { nil, 2 },
    { 1, 1, 0 },
    { nil, 2 },
    { nil, 1 },
}

-- Stand-ins for what an older UiLint mock lacks, so this file passes with or without its later additions: FrameXML's
-- StaticPopup_Show (formats the dialog's text, returns the dialog, records the show in M.popups as the mock does) and
-- a texture's blend mode (CSimpleTexture keeps it; BLEND until set).
local function standIns(M)
    local env = M.env
    if not env.StaticPopup_Show then
        M.popups = M.popups or {}
        env.StaticPopup_Show = function(which, a1, a2, data)
            local info = env.StaticPopupDialogs and env.StaticPopupDialogs[which]
            if not info then return nil end
            local dialog = { which = which, data = data }
            local text = string.format(info.text or "", a1, a2)
            M.popups[#M.popups + 1] = { which = which, text = text, data = data, dialog = dialog }
            return dialog
        end
    end
end

local function withBlendMode(region)
    if region.GetBlendMode and region:GetBlendMode() ~= nil then return region end
    local set = region.SetBlendMode
    region.SetBlendMode = function(self, mode)
        self.__standInBlend = mode
        if set then return set(self, mode) end
    end
    region.GetBlendMode = function(self) return self.__standInBlend or "BLEND" end
    return region
end

local function talentGame(M, opts)
    opts = opts or {}
    local env = M.env
    standIns(M)
    for _, name in ipairs({ "GameFontNormal", "GameFontNormalLarge", "GameFontHighlightSmall",
        "GameFontDisableSmall" }) do
        env.CreateFont(name).__font = { "Fonts\\FRIZQT__.TTF", 12 }
    end
    env.STANDARD_TEXT_FONT = "Fonts\\FRIZQT__.TTF"
    env.PanelTemplates_GetSelectedTab = function(frame) return frame.selectedTab end
    env.PlayerTalentFrame_Update = function() end
    env.GetActiveTalentGroup = function() return 1 end
    env.GetUnspentTalentPoints = function() return 5 end
    -- talent group 2 is the second specialization; pet = true the hunter's pet (one tree, Ferocity)
    env.GetTalentTabInfo = function(tab, _, pet, group)
        if pet then
            if tab == 1 then return "Ferocity", "Interface\\Icons\\Ability_Druid_Swipe", 10, "HunterPetFerocity", 0 end
            return
        end
        local t = TREES[tab]
        if t then return t[1], t[2], group == 2 and SPEC2_POINTS[tab] or t[3], t[4], 0 end
    end
    -- preview talents (GetCVarBool("previewTalents")): the 9th value, the rank once the previewed points go in
    env.GetTalentInfo = function(tab, id, _, pet, group)
        local n = NODES[id]
        if not n then return end
        if pet then return "Pet talent " .. id, "icon", 1, 1, PET_RANK, 2, nil, 1 end
        local rank = group == 2 and SPEC2_RANKS[id] or n.rank
        return "Talent " .. id, "icon", n.tier, 1, rank, n.max, nil, n.meets, n.preview
    end
    env.GetGlyphSocketInfo = function(id, group)
        local s = (group == 2 and SOCKETS2 or SOCKETS)[id]
        return s[1], s[2], s[3], s[4]
    end
    env.GetSpellInfo = function(id)
        if id == 100 then return "Glyph of Frostbolt" elseif id == 101 then return "Glyph of Ice Lance" end
    end
    local profile = { modules = { talents = { enabled = opts.addicatTalents or false } },
        talents = { glyph_list = opts.glyphList or false } }
    local a = fakeAddicatUI(profile)
    run(M, a, "core/commands.lua")
    local from = #M.objects
    run(M, a, "modules/talents_classic.lua")
    return a, from
end

-- Blizzard_TalentUI (load-on-demand): the window, its four bottom tabs and the first tree's buttons, and how it
-- redraws. PlayerTalentFrame_OnLoad stores PlayerTalentFrame_Update as self.updateFunction before any addon can hook
-- the global, and TalentFrame_Update calls that copy. Everything that redraws the window calls
-- PlayerTalentFrame_Refresh by name: OnShow, the bottom tabs (PlayerTalentFrameTab_OnClick), the dual-spec and pet
-- tabs (PlayerSpecTab_OnClick, which fires no event) and the talent, preview and pet events. Refresh shows the glyph
-- page on tab 4 (GlyphFrame_Update by name when it is shown already, no OnShow) and hides it on the others.
local function loadTalentUI(M, from)
    local env = M.env
    local f = env.CreateFrame("Frame", "PlayerTalentFrame", env.UIParent)
    f:SetSize(384, 512)
    f.selectedTab, f.talentGroup, f.pet = 1, 1, false
    f.updateFunction = env.PlayerTalentFrame_Update
    env.PlayerTalentFrame_Refresh = function()
        local g = env.GlyphFrame
        if f.selectedTab == 4 then
            if g and g:IsShown() then env.GlyphFrame_Update() elseif g then g:Show() end
        elseif g then
            g:Hide()
        end
        if f.updateFunction then f.updateFunction() end        -- TalentFrame_Update, then the buttons laid out
    end
    env.PlayerSpecTab_OnClick = function(spec)
        f.pet, f.talentGroup = spec.pet or false, spec.talentGroup or 1
        env.PlayerTalentFrame_Refresh()
    end
    for i = 1, 4 do
        local tab = env.CreateFrame("Button", "PlayerTalentFrameTab" .. i, f)
        tab:SetScript("OnClick", function()
            f.selectedTab = i
            env.PlayerTalentFrame_Refresh()
        end)
    end
    for i, _ in ipairs(NODES) do
        local b = env.CreateFrame("Button", "PlayerTalentFrameTalent" .. i, f)
        local createTexture = b.CreateTexture
        b.CreateTexture = function(self, ...) return withBlendMode(createTexture(self, ...)) end
        b:SetSize(37, 37)
        b:SetID(i)
        local rank = b:CreateFontString("PlayerTalentFrameTalent" .. i .. "Rank", "OVERLAY")
        rank:SetFont("Fonts\\FRIZQT__.TTF", 10)
        b:CreateTexture("PlayerTalentFrameTalent" .. i .. "RankBorder", "OVERLAY")
    end
    env.PlayerTalentFrameTalent5:Hide()
    M.addons.Blizzard_TalentUI = true
    fireNew(M, from, "ADDON_LOADED", "Blizzard_TalentUI")
    return f
end

-- Blizzard_GlyphUI (load-on-demand): the round page and its six sockets; GlyphFrame_Update redraws the sockets
local function loadGlyphUI(M, from)
    local env = M.env
    local g = env.CreateFrame("Frame", "GlyphFrame", env.UIParent)
    g:SetSize(384, 512)
    for i = 1, 6 do env.CreateFrame("Button", "GlyphFrameGlyph" .. i, g) end
    env.GlyphFrame_Update = function() end
    M.addons.Blizzard_GlyphUI = true
    fireNew(M, from, "ADDON_LOADED", "Blizzard_GlyphUI")
    return g
end

local function color(fs)
    local r, g, b = fs:GetTextColor()
    return string.format("%.2f,%.2f,%.2f", r, g, b)
end

------------------------------------------------------------------------------------------------------
-- Defaults and the migration
------------------------------------------------------------------------------------------------------
test("aui talents: WoW's window by default, a stored old default moves to it once, a later choice stays", function(M)
    local a = fakeAddicatUI({ modules = {} })
    run(M, a, "database.lua")
    run(M, a, "core/api.lua")
    H.eq(a.defaults.profile.modules.talents.enabled, false, "AddicatUI's all-trees window off: WoW's own")
    H.eq(a.defaults.profile.talents.glyph_list, false, "WoW's round glyph page with names")

    local function migrate(profile)
        a.db = { profile = profile, global = {} }
        a:ApplyDatabaseMigrations()
        return profile
    end
    local old = migrate({ version = 3, modules = { talents = { enabled = true } } })
    H.eq(rawget(old.modules.talents, "enabled"), nil, "the old default written out is dropped: WoW's window")
    H.eq(old.version, a.DB_SCHEMA_VERSION)
    local chosen = migrate({ version = a.DB_SCHEMA_VERSION, modules = { talents = { enabled = true } } })
    H.eq(chosen.modules.talents.enabled, true, "AddicatUI's window chosen after the move stays selectable")
    local off = migrate({ version = 3, modules = { talents = { enabled = false } } })
    H.eq(off.modules.talents.enabled, false)

    local panels = read("AddicatUI_Options/panel/tab_panels.lua")
    H.ok(panels:find('EnsureModuleTable("talents").enabled = val', 1, true), "the all-trees window stays in Options")
    H.ok(panels:find("TalentSettings().glyph_list = val", 1, true), "the glyph list is an option")
    local xml = read("AddicatUI/modules/modules.xml")
    local classic = H.ok(xml:find('<Script file="talents_classic.lua"/>', 1, true), "talents_classic.lua loads")
    H.ok(classic > xml:find('talents\\talents.xml', 1, true), "after the talents module whose switch it reads")
end)

------------------------------------------------------------------------------------------------------
-- The talent window
------------------------------------------------------------------------------------------------------
test("aui talents: the spec panel at the window's right, trees on their own art, credited to Addicated", function(M)
    local a, from = talentGame(M)
    fireNew(M, from, "PLAYER_LOGIN")
    H.ok(a.ClassicTalents.Active(), "active with the talents module off")
    local f = loadTalentUI(M, from)
    local sp = H.ok(M.env.AddicatUI_TalentSpecPanel, "the spec panel")
    H.eq(sp:GetParent(), f)
    H.ok(sp:GetWidth() == 178 and sp:GetHeight() == 286, "178 x 286")
    local p, rel, rp, x, y = sp:GetPoint(1)
    H.ok(p == "TOPLEFT" and rel == f and rp == "TOPRIGHT" and x == 30 and y == -40,
        "right of the window, clear of WoW's spec tabs (TOPRIGHT -32, art out to +29)")
    H.eq(sp.__backdrop.edgeFile, "Interface\\Tooltips\\UI-Tooltip-Border")
    H.eq(sp.title:GetText(), "Specializations")
    H.eq(sp.credit:GetText(), "UI by Addicated")
    for i = 1, 3 do
        local b = sp.buttons[i]
        H.eq(b.name:GetText(), TREES[i][1])
        H.eq(b.sub:GetText(), TREES[i][3] .. " points")
        H.eq(b.icon:GetTexture(), TREES[i][2])
        H.eq(b.art:GetTexture(), "Interface\\TalentFrame\\" .. TREES[i][4] .. "-TopLeft", "the tree's own art")
        H.eq(b.tag:GetText(), ({ "1st", "2nd", "3rd" })[i])
    end
    H.eq(sp.buttons[4].name:GetText(), "Glyphs")
    H.ok(sp.buttons[4]:IsShown(), "Glyphs while WoW's glyph tab is there")
    H.eq(sp.buttons[1].__bdborder[1], 1, "the selected tree in gold")
    H.eq(sp.buttons[2].__bdborder[1], 0.4)
    for i = 1, 4 do
        local tab = M.env["PlayerTalentFrameTab" .. i]
        H.ok(tab:GetAlpha() == 0 and not tab:IsMouseEnabled(), "bottom tab " .. i .. " hidden behind the panel")
    end

    sp.buttons[2]:Click()
    H.eq(f.selectedTab, 2, "a tree button clicks WoW's own tab")
    H.eq(sp.buttons[2].__bdborder[1], 1, "and lights")
    H.eq(sp.buttons[1].__bdborder[1], 0.4)

    M.env.PlayerTalentFrameTab4:Hide()
    fireNew(M, from, "PLAYER_TALENT_UPDATE")
    H.ok(not sp.buttons[4]:IsShown(), "no Glyphs button below level 15")

    f.pet = true
    fireNew(M, from, "PLAYER_TALENT_UPDATE")
    H.ok(not sp:IsShown(), "pet talents: WoW's own tabs")
    H.ok(M.env.PlayerTalentFrameTab1:GetAlpha() == 1 and M.env.PlayerTalentFrameTab1:IsMouseEnabled(), "back")
end)

test("aui talents: each node shows rank/max, a green glow while learnable, gold when maxed; the tree heads", function(M)
    local _, from = talentGame(M)
    fireNew(M, from, "PLAYER_LOGIN")
    local f = loadTalentUI(M, from)
    local function node(i) return M.env["PlayerTalentFrameTalent" .. i] end

    H.eq(node(1).bhRank:GetText(), "5/5")
    H.ok(node(1).bhGlow:IsShown(), "maxed: glow")
    local r, g, b = node(1).bhGlow:GetVertexColor()
    H.ok(r == 1 and g == 0.82 and b == 0, "gold")
    H.eq(color(node(1).bhRank), "1.00,0.82,0.00")

    H.eq(node(2).bhRank:GetText(), "0/3")
    H.ok(node(2).bhGlow:IsShown(), "a point can go in now")
    r, g, b = node(2).bhGlow:GetVertexColor()
    H.ok(r == 0.2 and g == 1 and b == 0.2, "green")

    H.ok(not node(3).bhGlow:IsShown(), "tier 4 with 11 points in the tree: locked")
    H.eq(color(node(3).bhRank), "0.55,0.55,0.55")
    H.ok(not node(4).bhGlow:IsShown(), "prerequisite missing")
    H.eq(color(node(4).bhRank), "0.25,1.00,0.25", "spent in: green text")
    H.ok(not node(5).bhRank:IsShown() and not node(5).bhGlow:IsShown(), "a hidden button shows nothing")

    H.eq(M.env.PlayerTalentFrameTalent1Rank:GetAlpha(), 0, "WoW's corner counter gives way")
    H.eq(M.env.PlayerTalentFrameTalent1RankBorder:GetAlpha(), 0)
    local glow = node(1).bhGlow
    H.ok(glow:GetTexture() == "Interface\\Buttons\\UI-ActionButton-Border" and glow:GetBlendMode() == "ADD",
        "the action button border, additive")
    H.ok(math.abs(glow:GetWidth() - 37 * 1.85) < 1e-6, "1.85 times the button")

    -- the heading: the tree's name and points big at the top
    local head
    for _, region in ipairs({ f:GetRegions() }) do
        if region.GetText and region:GetText() and region:GetText():find("ARCANE", 1, true) then head = region end
    end
    H.ok(head, "the tree heading")
    H.eq(head:GetText(), "|cffe6cc80ARCANE|r   |cff40ff4011|r")
    local file, size, flags = head:GetFont()
    H.ok(file == "Fonts\\MORPHEUS.ttf" and size == 22 and flags == "OUTLINE", "MORPHEUS 22 outline")
    f.selectedTab = 4
    fireNew(M, from, "PLAYER_TALENT_UPDATE")
    H.ok(not head:IsShown(), "not over the glyph tab")
end)

test("aui talents: WoW's dual-spec and pet tabs and preview points redraw the ranks, the heading and the panel",
    function(M)
    local _, from = talentGame(M)
    fireNew(M, from, "PLAYER_LOGIN")
    local f = loadTalentUI(M, from)
    local sp = M.env.AddicatUI_TalentSpecPanel
    local function node(i) return M.env["PlayerTalentFrameTalent" .. i] end
    local head
    for _, region in ipairs({ f:GetRegions() }) do
        if region.GetText and region:GetText() and region:GetText():find("ARCANE", 1, true) then head = region end
    end
    H.eq(node(1).bhRank:GetText(), "5/5")

    -- the secondary spec's tab: PlayerSpecTab_OnClick, then PlayerTalentFrame_Refresh; no event this file hears
    M.env.PlayerSpecTab_OnClick({ talentGroup = 2 })
    H.eq(node(1).bhRank:GetText(), "0/5", "the second spec's ranks")
    H.ok(not node(1).bhGlow:IsShown(), "no glow: not the active spec, nothing to learn there now")
    H.eq(color(node(1).bhRank), "0.55,0.55,0.55")
    H.eq(node(2).bhRank:GetText(), "3/3")
    local r, g, b = node(2).bhGlow:GetVertexColor()
    H.ok(node(2).bhGlow:IsShown() and r == 1 and g == 0.82 and b == 0, "maxed there: gold")
    H.eq(head:GetText(), "|cffe6cc80ARCANE|r   |cff40ff400|r", "the heading counts the second spec's points")
    H.eq(sp.buttons[3].sub:GetText(), "41 points", "and the panel")
    M.env.PlayerSpecTab_OnClick({ talentGroup = 1 })
    H.eq(node(1).bhRank:GetText(), "5/5", "the first spec again")
    H.eq(sp.buttons[3].sub:GetText(), "0 points")

    -- the hunter's pet tab: the pet's talents under WoW's own tabs
    M.env.PlayerSpecTab_OnClick({ pet = true })
    H.ok(not sp:IsShown(), "no spec panel over the pet's talents")
    H.ok(M.env.PlayerTalentFrameTab1:GetAlpha() == 1 and M.env.PlayerTalentFrameTab1:IsMouseEnabled(), "its tabs")
    H.ok(not head:IsShown(), "no player tree heading")
    H.eq(node(1).bhRank:GetText(), PET_RANK .. "/2", "the pet's ranks, not the player's")
    M.env.PlayerSpecTab_OnClick({ talentGroup = 1 })
    H.ok(sp:IsShown(), "the player's talents: the panel again")
    H.eq(node(1).bhRank:GetText(), "5/5")

    -- preview talents: PREVIEW_TALENT_POINTS_CHANGED redraws through PlayerTalentFrame_Refresh as well
    M.env.GetCVarBool = function(name) return name == "previewTalents" end
    NODES[2].preview = 2
    M.env.PlayerTalentFrame_Refresh()
    local previewed = node(2).bhRank:GetText()
    NODES[2].preview = nil
    H.eq(previewed, "2/3", "a previewed point shows at once")
end)

test("aui talents: AddicatUI's own window chosen, or the old Bleakhold UI addon loaded: WoW's window as is", function(M)
    local a, from = talentGame(M, { addicatTalents = true })
    fireNew(M, from, "PLAYER_LOGIN")
    H.ok(not a.ClassicTalents.Active())
    loadTalentUI(M, from)
    loadGlyphUI(M, from)
    H.ok(not M.env.AddicatUI_TalentSpecPanel, "no spec panel")
    H.ok(not M.env.PlayerTalentFrameTalent1.bhRank, "no node dressing")

    local M2 = H.newGame()
    M2.addons.BleakholdUI = true
    local b, from2 = talentGame(M2)
    fireNew(M2, from2, "PLAYER_LOGIN")
    H.ok(not b.ClassicTalents.Active(), "the old addon draws the same panels itself")
    loadTalentUI(M2, from2)
    H.ok(not M2.env.AddicatUI_TalentSpecPanel, "drawn once")
end)

------------------------------------------------------------------------------------------------------
-- The glyph page
------------------------------------------------------------------------------------------------------
test("aui talents: the glyph names under WoW's sockets, major gold and minor blue, and the hint", function(M)
    local _, from = talentGame(M)
    fireNew(M, from, "PLAYER_LOGIN")
    local g = loadGlyphUI(M, from)
    local labels = {}
    for _, region in ipairs({ g:GetRegions() }) do
        local p, rel = region:GetPoint(1)
        for id = 1, 6 do
            if p == "TOP" and rel == M.env["GlyphFrameGlyph" .. id] then labels[id] = region end
        end
    end
    H.eq(labels[1]:GetText(), "Frostbolt", "the glyph's name without \"Glyph of\"")
    H.eq(color(labels[1]), "1.00,0.82,0.00")
    H.eq(labels[2]:GetText(), "Empty minor")
    H.eq(labels[3]:GetText(), "Level 50", "a locked socket says when it opens")
    H.eq(labels[4]:GetText(), "Empty major")
    H.eq(labels[5]:GetText(), "Level 70")
    H.eq(labels[6]:GetText(), "Level 80")
    H.eq(#M.FindText("then click a socket", false), 1, "the hint")
    H.ok(not M.env.AddicatUI_GlyphList, "no list by default")

    SOCKETS[2][3] = 100
    fireNew(M, from, "GLYPH_ADDED")
    H.eq(labels[2]:GetText(), "Frostbolt", "follows a new glyph")
    H.eq(color(labels[2]), "0.55,0.78,1.00", "minor in blue")
    SOCKETS[2][3] = nil
end)

test("aui talents: a dual-spec tab click on the glyph page renames the sockets, with no glyph event", function(M)
    local _, from = talentGame(M)
    fireNew(M, from, "PLAYER_LOGIN")
    local f = loadTalentUI(M, from)
    local g = loadGlyphUI(M, from)
    f.selectedTab = 4
    local label
    for _, region in ipairs({ g:GetRegions() }) do
        local p, rel = region:GetPoint(1)
        if p == "TOP" and rel == M.env.GlyphFrameGlyph1 then label = region end
    end
    H.eq(label:GetText(), "Frostbolt")
    -- PlayerSpecTab_OnClick: PlayerTalentFrame_Refresh, and GlyphFrame_Update as the page is shown already
    M.env.PlayerSpecTab_OnClick({ talentGroup = 2 })
    H.ok(g:IsShown(), "the page stays shown: no OnShow")
    H.eq(label:GetText(), "Ice Lance", "the second spec's glyph under the socket")
    M.env.PlayerSpecTab_OnClick({ talentGroup = 1 })
    H.eq(label:GetText(), "Frostbolt")
    -- WoW's own socket redraw alone (USE_GLYPH, a level up) renames them as well
    f.talentGroup = 2
    M.env.GlyphFrame_Update()
    H.eq(label:GetText(), "Ice Lance", "GlyphFrame_Update")
    f.talentGroup = 1
end)

test("aui talents: the glyph list places, removes on Shift + right-click, links, leaves the other spec be", function(M)
    local a, from = talentGame(M, { glyphList = true })
    M.env.StaticPopupDialogs.CONFIRM_REMOVE_GLYPH = { text = "Remove %s?", button1 = "Yes", button2 = "No" }
    local placed = {}
    M.env.GlyphMatchesSocket = function(id) return id == 4 end
    M.env.PlaceGlyphInSocket = function(id) placed[#placed + 1] = id end
    fireNew(M, from, "PLAYER_LOGIN")
    loadTalentUI(M, from)
    local g = loadGlyphUI(M, from)
    local list = H.ok(M.env.AddicatUI_GlyphList, "the list over the page")
    H.ok(list:IsShown() and list:GetFrameLevel() == g:GetFrameLevel() + 20 and list:IsMouseEnabled(),
        "over the sockets, catching their clicks")
    -- GlyphFrame spans the whole talent window: the list keeps to its art, under the portrait and the title row
    H.eq(list:GetNumPoints(), 2, "not over the whole window")
    local p1, rel1, rp1, left, top = list:GetPoint(1)
    local p2, rel2, rp2, right, bottom = list:GetPoint(2)
    H.ok(p1 == "TOPLEFT" and rel1 == g and rp1 == "TOPLEFT" and left == 18 and top == -66, "its top left")
    H.ok(p2 == "BOTTOMRIGHT" and rel2 == g and rp2 == "BOTTOMRIGHT", "its bottom right")
    H.ok(right <= -30 and bottom >= 70, "inside the art (GlyphFrame's HitRectInsets: right 30, bottom 70)")
    -- PlayerTalentFrameCloseButton: CENTER on the window's TOPRIGHT at -44, -25, 32 px; the portrait 60 px at 7, -6
    H.ok(top < -25 - 16 and top <= -6 - 60, "below the close button and the portrait")
    local height = 512 + top - bottom
    local content = 8 + 2 * 18 + 4 + 5 * 47 + 44
    H.ok(content + 30 <= height, "two headings, six rows and a two-line hint fit its " .. height .. " px")
    local rows = list.rows
    H.eq(#rows, 6)
    H.eq(table.concat({ rows[1].id, rows[2].id, rows[3].id, rows[4].id, rows[5].id, rows[6].id }, ","), "1,4,6,2,3,5",
        "major sockets first, then minor")
    H.eq(rows[1].name:GetText(), "Glyph of Frostbolt")
    H.eq(rows[1].sub:GetText(), "Shift + right-click to remove")
    H.eq(rows[2].name:GetText(), "Empty major socket")
    H.eq(rows[2].icon:GetTexture(), "Interface\\Icons\\INV_Glyph_MajorWarrior", "the class's glyph icon")
    H.ok(rows[2].icon:IsDesaturated(), "greyed while empty")
    H.eq(rows[3].name:GetText(), "Major socket")
    H.eq(rows[3].sub:GetText(), "Unlocks at level 80")
    H.eq(rows[3].icon:GetTexture(), "Interface\\LFGFrame\\UI-LFG-ICON-LOCK")
    H.contains(list.hint:GetText(), "UI by Addicated")

    rows[2]:Click("LeftButton")
    H.eq(table.concat(placed, ","), "4", "the glyph on the cursor goes in")
    rows[3]:Click("LeftButton")
    H.eq(#placed, 1, "not where it does not fit")

    M.shift = true
    rows[1]:Click("RightButton")
    local popup = H.ok(M.popups[#M.popups], "WoW's own remove confirmation")
    H.eq(popup.which, "CONFIRM_REMOVE_GLYPH")
    H.eq(popup.text, "Remove Glyph of Frostbolt?")
    H.eq(popup.dialog.data, 1, "for socket 1")
    M.shift = false

    M.env.IsModifiedClick = function(what) return what == "CHATLINK" end
    M.env.GetGlyphLink = function(id) return "[Glyph " .. id .. "]" end
    rows[1]:Click("LeftButton")
    H.eq(M.insertedLink, "[Glyph 1]", "Shift-click links it")
    M.env.IsModifiedClick = function() return nil end

    -- WoW's secondary-spec tab with the page shown: PlayerSpecTab_OnClick and PlayerTalentFrame_Refresh, the page
    -- staying shown (GlyphFrame_Update, no OnShow); no glyph event fires
    local f = M.env.PlayerTalentFrame
    f.selectedTab = 4
    M.env.PlayerSpecTab_OnClick({ talentGroup = 2 })
    H.ok(list:IsShown(), "the page stays")
    H.eq(rows[1].name:GetText(), "Glyph of Ice Lance", "the second spec's glyph")
    H.eq(rows[1].sub:GetText(), "Other specialization")
    rows[2]:Click("LeftButton")
    H.eq(#placed, 1, "the other specialization: look, don't touch")
    -- the active spec's tab again while the rows still show the second spec's glyphs (no redraw reached them yet):
    -- the remove question names the glyph its button removes, read at the click
    f.talentGroup = 1
    M.shift = true
    rows[1]:Click("RightButton")
    H.eq(M.popups[#M.popups].text, "Remove Glyph of Frostbolt?", "socket 1's glyph in the active spec, not Ice Lance")
    M.shift = false
    M.env.PlayerSpecTab_OnClick({ talentGroup = 1 })
    H.eq(rows[1].name:GetText(), "Glyph of Frostbolt", "redrawn for the active spec")

    -- a glyph on the cursor over an inscribed socket: WoW's "the existing glyph will be lost" question first
    M.env.StaticPopupDialogs.CONFIRM_GLYPH_PLACEMENT = {
        text = "Are you sure you want to inscribe this glyph? The existing glyph will be lost.",
        button1 = "Yes", button2 = "No", OnAccept = function(self) M.env.PlaceGlyphInSocket(self.data) end }
    M.env.GlyphMatchesSocket = function(id) return id == 1 or id == 4 end
    local shown = #M.popups
    rows[1]:Click("LeftButton")
    H.eq(#placed, 1, "Frostbolt is not inscribed over at once")
    local ask = H.ok(M.popups[shown + 1], "WoW's own placement question")
    H.eq(ask.which, "CONFIRM_GLYPH_PLACEMENT")
    H.eq(ask.dialog.data, 1, "for socket 1")
    M.StaticPopupClick("CONFIRM_GLYPH_PLACEMENT", 2)
    H.eq(#placed, 1, "No keeps the glyph")
    rows[1]:Click("LeftButton")
    M.StaticPopupClick("CONFIRM_GLYPH_PLACEMENT", 1)
    H.eq(table.concat(placed, ","), "4,1", "Yes inscribes it")
    shown = #M.popups
    rows[2]:Click("LeftButton")
    H.eq(table.concat(placed, ","), "4,1,4", "an empty socket takes it at once")
    H.eq(#M.popups, shown, "without a question")

    a.db.profile.talents.glyph_list = false
    a.ClassicTalents.RefreshGlyphs()
    H.ok(not list:IsShown(), "off at once: WoW's round page again")
end)

------------------------------------------------------------------------------------------------------
-- /talents
------------------------------------------------------------------------------------------------------
test("aui talents: /talents opens WoW's window while AddicatUI's is off, AddicatUI's while it runs", function(M)
    local a = fakeAddicatUI({ modules = { talents = { enabled = false } }, talents = {} })
    run(M, a, "modules/talents/namespace.lua")
    run(M, a, "modules/talents/entry_points.lua")
    local opened = 0
    M.env.ToggleTalentFrame = function() opened = opened + 1 end      -- FrameXML's, what the talent key runs
    H.eq(M.env.SLASH_ADDICATUI_TALENTS1, "/talents")
    local slash = H.ok(M.env.SlashCmdList.ADDICATUI_TALENTS, "registered")
    slash("")
    H.eq(opened, 1, "the talents module off (the default): WoW's own window, not nothing")

    local TM = a.TalentModule
    local toggled = 0
    TM.ns.ToggleTalents = function() toggled = toggled + 1 end
    TM.applied = true
    slash("")
    H.eq(toggled, 1, "AddicatUI's window while the module runs")
    H.eq(opened, 1)

    TM.applied = false
    M.env.ToggleTalentFrame = nil
    slash("")
    H.eq(toggled, 1, "no FrameXML toggle: nothing, and no error")
end)

------------------------------------------------------------------------------------------------------
-- /bhui talents
------------------------------------------------------------------------------------------------------
test("aui talents: /bhui talents picks the window (a /reload) and the glyph page's view (at once)", function(M)
    local a, from = talentGame(M)
    fireNew(M, from, "PLAYER_LOGIN")
    local B = a.BleakholdCommands
    local n = #M.chat
    B.Run("talents glyphs list")
    H.eq(a.db.profile.talents.glyph_list, true)
    H.contains(said(M, n)[1], "the list of sockets")
    B.Run("talents glyphs round")
    H.eq(a.db.profile.talents.glyph_list, false)
    n = #M.chat
    B.Run("talents glyphs")
    H.contains(said(M, n)[1], "glyphs round | glyphs list", "no choice: the usage")

    B.Run("talents addicatui")
    H.eq(a.db.profile.modules.talents.enabled, true, "AddicatUI's window (core/commands.lua's handler)")
    n = #M.chat
    B.Run("talents blizzard")
    H.eq(a.db.profile.modules.talents.enabled, false, "WoW's window")
    H.contains(said(M, n)[1], "/reload")

    n = #M.chat
    B.Run("help")
    local lines = said(M, n)
    H.contains(lines[1], "/bhui talents blizzard | addicatui | glyphs round | glyphs list", "first in the help still")
end)

test("aui talents: every string the talent window, the dock and their options ask for is in enUS", function(M)
    local enUS = read("AddicatUI/Locales/enUS.lua")
    local have = {}
    for key in enUS:gmatch('L%["(.-)"%] =') do have[key] = true end
    for _, rel in ipairs({ "AddicatUI/modules/talents_classic.lua", "AddicatUI/modules/micromenu.lua",
        "AddicatUI_Options/panel/tab_panels.lua", "AddicatUI_Options/panel/tab_micromenu.lua" }) do
        local src = read(rel)
        -- the options tabs use the options locale (LO) as well; addon.L is AddicatUI's own, strict
        local pattern = rel:find("Options", 1, true) and 'addon%.L%["(.-)"%]' or '%f[%w_]L%["(.-)"%]'
        for key in src:gmatch(pattern) do
            H.ok(have[key], rel .. ": no enUS string " .. key)
        end
    end
    H.ok(have.MicroDock, "the dock's edit-mode label (CreateUIFrame reads L[\"MicroDock\"])")
end)
