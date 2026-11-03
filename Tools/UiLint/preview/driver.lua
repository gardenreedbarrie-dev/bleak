-- Bleakhold UI preview driver (run by render.sh): loads the real addon into the UiLint mock (mock/wowmock.lua), runs a
-- scene, lays the frames out like the 3.3.5a client and prints every visible region as JSON for render.py.
--
--   wowlua driver.lua <repo> <addonDir> <api.lua> <scenes.lua> <scene> <w> <h> <uiScale|0> <measure.lua|""> [hover=all]
--       [journal=0]   (journal=0: no Journal pictures, so their files count as missing, as in a client without them)
--
-- Layout follows the client's code (Engine/Source/Frame): CLayoutFrame's edge priorities (left from TOPLEFT, LEFT,
-- BOTTOMLEFT, ...), a frame's strata and level (a child one level above its parent; SetFrameStrata reaches every
-- child, SetFrameLevel shifts them), draw layers batched per level (CFrameStrataNode), CBackdropGenerator's pieces,
-- CSimpleStatusBar's fill, CSimpleSlider's thumb, CSimpleButton's state and highlight textures and a scroll frame's
-- child and clipping. Text and texture sizes come from render.py (pass 1 measures, pass 2 lays out with them).
-- Model, PlayerModel, DressUpModel and TabardModel frames go out as "Model" items (their frame type and box): the 3D
-- model is not drawn, render.py marks the box instead.
local repo, addonDir, apiPath, scenePath, scene = arg[1], arg[2], arg[3], arg[4], arg[5]
local W, Hpx, ui, measurePath = tonumber(arg[6]), tonumber(arg[7]), tonumber(arg[8]), arg[9]
local opts = {}
for i = 10, #arg do
    local k, v = arg[i]:match("^([%w_]+)=(.*)$")
    if k then opts[k] = v end
end
assert(repo and addonDir and apiPath and scenePath and scene and W and Hpx,
    "usage: driver.lua <repo> <addonDir> <api.lua> <scenes.lua> <scene> <w> <h> <uiScale|0> <measure.lua|\"\">")

-- render.py's numbers (pass 2): widths["font|px|text"] = px, lines["font|px|wrapPx|text"] = n, sizes[path] = {w, h}
local measure = { widths = {}, lines = {}, sizes = {} }
if measurePath and measurePath ~= "" then
    local chunk = host_loadfile(measurePath)
    if chunk then measure = chunk() end
end
local function plain(t) return (t:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")) end

local api = assert(host_loadfile(apiPath))()
local mockFactory = assert(host_loadfile(repo .. "/Tools/UiLint/mock/wowmock.lua"))()
local M = mockFactory({ api = api, repo = repo })
local env = M.env
M.quietErrors = true   -- stdout carries the JSON; the addon's Lua errors go into it (render.py prints them)
M.addonDir, M.repo = addonDir, repo

-- Item icons. The mock answers the question mark for every item (the tests rely on that); the client reads the icon
-- from Item.dbc and ItemDisplayInfo.dbc, so the demo's items show their own icon here, as they do in game. Set
-- before the addon loads (it may keep GetItemIcon in a local); a scene can still replace either function.
local ITEM_ICONS = {
    [40752] = "Interface\\Icons\\Spell_Holy_ProclaimChampion_02",   -- Emblem of Heroism (Demo.lua daily task reward)
}
local function itemId(item)
    return tonumber(item) or (type(item) == "string" and tonumber(item:match("item:(%d+)"))) or nil
end
local mockItemIcon, mockItemInfo = env.GetItemIcon, env.GetItemInfo
env.GetItemIcon = function(item, ...)
    local id = itemId(item)
    return (id and ITEM_ICONS[id]) or mockItemIcon(item, ...)
end
env.GetItemInfo = function(item, ...)
    local r = { mockItemInfo(item, ...) }
    local id = itemId(item)
    if r[1] and id and ITEM_ICONS[id] then r[10] = ITEM_ICONS[id] end
    return unpack(r, 1, math.max(#r, r[1] and 10 or 0))
end

------------------------------------------------------------------------------------------------------
-- Strata and levels as CSimpleFrame keeps them (__dstrata, __dlevel), for every frame made through CreateFrame
------------------------------------------------------------------------------------------------------
local base = Hpx / 768
local function scaleOf(o)
    local f, s = o.GetEffectiveScale and o or o.__parent, 1
    while f do s = s * (f.__scale or 1) f = f.__parent end
    return s
end
local function pxOf(o) return scaleOf(o) * base end

local function strataOf(f)
    if not f then return "MEDIUM" end
    if f.__dstrata then return f.__dstrata end
    -- a frame the mock built itself: its own strata when it set one, else its parent's
    if f.__strata and f.__strata ~= "MEDIUM" then return f.__strata end
    return f.__parent and strataOf(f.__parent) or (f.__strata or "MEDIUM")
end
local function levelOf(f)
    if not f then return 0 end
    if f.__dlevel then return f.__dlevel end
    if not f.__parent then return f.__level or 1 end
    return levelOf(f.__parent) + 1
end
local function eachChild(f, fn)
    for _, c in ipairs(f.__children or {}) do fn(c) end
end
local function setStrata(f, s)
    f.__dstrata = s
    eachChild(f, function(c) setStrata(c, s) end)
end
local function shiftLevel(f, delta)
    f.__dlevel = math.max(0, levelOf(f) + delta)
    local s = strataOf(f)
    eachChild(f, function(c) if strataOf(c) == s then shiftLevel(c, delta) end end)
end

-- text widths and heights the addon reads while it lays itself out come from the real faces (pass 2)
local function lineCount(fs, wrapPx, px)
    local text = plain(fs.__text or "")
    if wrapPx then
        local n = measure.lines[fs.__font[1] .. "|" .. px .. "|" .. wrapPx .. "|" .. text]
        if n then return n end
    end
    local _, nl = text:gsub("\n", "")
    return nl + 1
end
local function measured(fs)
    if not (fs.__text and fs.__font) then return nil end
    local ppu = pxOf(fs)
    local px = math.floor(fs.__font[2] * ppu + 0.5)
    local w = measure.widths[fs.__font[1] .. "|" .. px .. "|" .. plain(fs.__text)]
    return w and w / ppu
end
local function decorateFS(fs)
    local gsw, gsh = fs.GetStringWidth, fs.GetStringHeight
    fs.GetStringWidth = function(self) return measured(self) or gsw(self) end
    fs.GetStringHeight = function(self)
        if not (self.__text and self.__font) then return gsh(self) end
        local ppu = pxOf(self)
        local px = math.floor(self.__font[2] * ppu + 0.5)
        local wrap = (self.__w or 0) > 0 and math.floor(self.__w * ppu + 0.5) or nil
        local n = lineCount(self, wrap, px)
        return n * self.__font[2] + (n - 1) * (self.__spacing or 0)
    end
    fs.SetShadowOffset = function(self, x, y) self.__sox, self.__soy = x, y end
    fs.SetShadowColor = function(self, r, g, b, a) self.__sc = { r, g, b, a or 1 } end
end
local function decorateFrame(f)
    local cfs, sfl, sfs, sp = f.CreateFontString, f.SetFrameLevel, f.SetFrameStrata, f.SetParent
    if cfs then
        f.CreateFontString = function(self, ...) local fs = cfs(self, ...) decorateFS(fs) return fs end
    end
    if sfl then
        f.SetFrameLevel = function(self, l)
            local r = sfl(self, l)
            if type(l) == "number" then shiftLevel(self, math.max(0, math.floor(l)) - levelOf(self)) end
            return r
        end
    end
    if sfs then
        f.SetFrameStrata = function(self, s)
            local r = sfs(self, s)
            if s ~= "PARENT" then setStrata(self, s) end
            return r
        end
    end
    -- the addon reads the levels and strata of this model (SetFrameLevel(GetFrameLevel() + n) and the like)
    if f.GetFrameLevel then f.GetFrameLevel = function(self) return levelOf(self) end end
    if f.GetFrameStrata then f.GetFrameStrata = function(self) return strataOf(self) end end
    if sp then
        f.SetParent = function(self, p)
            local r = sp(self, p)
            if type(p) == "string" then p = env[p] end
            if p then
                self.__dstrata, self.__dlevel = strataOf(p), levelOf(p) + 1
            end
            return r
        end
    end
end
local cf = env.CreateFrame
env.CreateFrame = function(otype, name, parent, template)
    local f = cf(otype, name, parent, template)
    local p = type(parent) == "string" and env[parent] or parent
    if p then
        f.__dstrata, f.__dlevel = strataOf(p), levelOf(p) + 1
    else
        f.__dstrata, f.__dlevel = "MEDIUM", 0
    end
    decorateFrame(f)
    return f
end
decorateFrame(env.UIParent)
env.UIParent.__dstrata, env.UIParent.__dlevel = "MEDIUM", 0
-- the font strings the mock built itself (StaticPopup1..4) measure like the addon's
for _, o in ipairs(M.objects) do
    if o.__otype == "FontString" then decorateFS(o) end
end

------------------------------------------------------------------------------------------------------
-- The scene
------------------------------------------------------------------------------------------------------
-- Helpers handed to a scene: P.run(fn) runs fn with the game's globals (CreateFrame, UIParent, ...) as its
-- environment, P.hover(frame [, on]) puts the cursor over a frame (its HIGHLIGHT layer shows, OnEnter runs).
local P = {
    M = M, env = env,
    run = function(fn, ...) setfenv(fn, env) return fn(...) end,
    hover = function(frame, on) M.Hover(frame, on) end,
}
local scenes = assert(host_loadfile(scenePath))()
local standalone = scenes.standalone and scenes.standalone[scene]
-- No Journal pictures here (render.sh found no --journal folder: journal=0): the client would find no file either, so
-- the addon's probe (JournalArt.lua) must fail and fall back to the stock LFG art, as a player without them sees it.
-- Set before the addon loads; a scene's own "before" may still change it.
if opts.journal == "0" then
    setmetatable(M.missingTextures, { __index = function(_, path)
        return (type(path) == "string" and path:find("^Interface\\AddOns\\Bleakhold\\Art\\Journal\\")) and true or nil
    end })
end
if scenes.before and scenes.before[scene] then
    scenes.before[scene](M, env, P)
end
local ns = {}
if standalone then
    M.EnterWorld()
else
    ns = M.LoadAddon(addonDir, "Bleakhold")
    M.FireEvent("ADDON_LOADED", "Bleakhold")
    M.FireEvent("PLAYER_LOGIN")
    M.EnterWorld()
end
M.SetScreen(W, Hpx, ui and ui > 0 and ui or nil)

local fn = assert(scenes[scene], "no scene " .. tostring(scene) .. " in " .. scenePath)
local roots = fn(M, ns, ns.RoyaleStyle, env, P)
M.Advance(0.05)
if type(roots) == "table" and roots.__otype then roots = { roots } end
if type(roots) ~= "table" then roots = nil end

------------------------------------------------------------------------------------------------------
-- Layout (CLayoutFrame)
------------------------------------------------------------------------------------------------------
local FP = { TOPLEFT = { 0, 0 }, TOP = { 0.5, 0 }, TOPRIGHT = { 1, 0 }, LEFT = { 0, 0.5 }, CENTER = { 0.5, 0.5 },
    RIGHT = { 1, 0.5 }, BOTTOMLEFT = { 0, 1 }, BOTTOM = { 0.5, 1 }, BOTTOMRIGHT = { 1, 1 } }
-- the first point of each list that is set gives that edge (CLayoutFrame.cpp s_leftPoints, ...)
local EDGE_X = { L = { "TOPLEFT", "LEFT", "BOTTOMLEFT" }, R = { "TOPRIGHT", "RIGHT", "BOTTOMRIGHT" },
    C = { "TOP", "CENTER", "BOTTOM" } }
local EDGE_Y = { T = { "TOPLEFT", "TOP", "TOPRIGHT" }, B = { "BOTTOMLEFT", "BOTTOM", "BOTTOMRIGHT" },
    C = { "LEFT", "CENTER", "RIGHT" } }

local function alphaOf(o)
    local a, f = o.__alpha or 1, o.__parent
    while f do a = a * (f.__alpha or 1) f = f.__parent end
    return a
end
local function visible(o)
    if o.__dropped then return false end
    while o do
        if not o.__shown then return false end
        o = o.__parent
    end
    return true
end
local function under(o, rootSet)
    while o do
        if rootSet[o] then return true end
        o = o.__parent
    end
    return false
end

local function pointsOf(o)
    local parent = o.__parent
    -- a scroll frame's child hangs from its TOPLEFT, moved by the scroll offset (CSimpleScrollFrame)
    if parent and parent.__scrollChild == o then
        return { TOPLEFT = { "TOPLEFT", parent, "TOPLEFT", -(parent.__hscroll or 0), parent.__vscroll or 0 } }
    end
    -- a slider's thumb: TOP (VERTICAL) or LEFT, (length - thumb) * position along (CSimpleSlider::OnLayerUpdate)
    if o.__thumbOf then
        local s = o.__thumbOf
        local lo, hi = s.__min or 0, s.__max or 0
        local pos = (hi - lo) ~= 0 and ((s.__value or lo) - lo) / (hi - lo) or 0
        if s.__orient == "VERTICAL" then
            return { TOP = { "TOP", s, "TOP", 0, -(((s.__h or 0) - (o.__h or 0)) * pos) } }
        end
        return { LEFT = { "LEFT", s, "LEFT", ((s.__w or 0) - (o.__w or 0)) * pos, 0 } }
    end
    local out = {}
    for _, p in ipairs(o.__points or {}) do out[p[1]] = p end   -- a point set again replaces the old one
    return out
end

local cache = {}
local resolve
local function textBox(o, ppu, wrapW)
    local px = math.floor(o.__font[2] * ppu + 0.5)
    local wrapPx = wrapW and math.floor(wrapW * ppu + 0.5) or nil
    local n = lineCount(o, wrapPx, px)
    return n * o.__font[2] + (n - 1) * (o.__spacing or 0), n, px, wrapPx
end
resolve = function(o)
    if o == env.UIParent then return { L = 0, T = 0, R = W, B = Hpx, ppu = base * (o.__scale or 1) } end
    if cache[o] ~= nil then return cache[o] or nil end
    cache[o] = false
    local ppu = pxOf(o)
    local pts = pointsOf(o)
    local function coord(name, axis)
        local p = pts[name]
        if not p then return nil end
        local rel = p[2] or o.__parent
        if type(rel) == "string" then rel = env[rel] end
        local rr = rel and resolve(rel)
        if not (rr and rr.L and rr.R and rr.T and rr.B) then return nil end
        local fr = FP[p[3]] or FP[p[1]]
        if axis == "x" then return rr.L + (rr.R - rr.L) * fr[1] + (p[4] or 0) * ppu end
        return rr.T + (rr.B - rr.T) * fr[2] - (p[5] or 0) * ppu
    end
    local function first(list, axis)
        for _, n in ipairs(list) do
            local v = coord(n, axis)
            if v then return v end
        end
    end
    local L, R, CX = first(EDGE_X.L, "x"), first(EDGE_X.R, "x"), first(EDGE_X.C, "x")
    local T, B, CY = first(EDGE_Y.T, "y"), first(EDGE_Y.B, "y"), first(EDGE_Y.C, "y")
    local w, h = (o.__w or 0) * ppu, (o.__h or 0) * ppu
    local r = { ppu = ppu }
    if o.__otype == "FontString" and o.__font and o.__text then
        -- the wrap width: its own width, else both horizontal edges
        local wrapW = (o.__w or 0) > 0 and o.__w or ((L and R) and (R - L) / ppu) or nil
        if w <= 0 and not (L and R) then w = (measured(o) or o:GetStringWidth()) * ppu end
        local th, n, px, wrapPx = textBox(o, ppu, wrapW)
        if h <= 0 then h = th * ppu end
        r.lines, r.px, r.wrapPx = n, px, wrapPx
    elseif o.__otype == "Texture" and (w <= 0 or h <= 0) and o.__texture and measure.sizes[o.__texture] then
        -- a texture without a size shows its file at its own size
        local s = measure.sizes[o.__texture]
        if w <= 0 then w = s[1] * ppu end
        if h <= 0 then h = s[2] * ppu end
    end
    if L and R then
    elseif L and w > 0 then R = L + w
    elseif R and w > 0 then L = R - w
    elseif CX and w > 0 then L, R = CX - w / 2, CX + w / 2
    elseif L and CX then R = 2 * CX - L
    elseif R and CX then L = 2 * CX - R end
    if T and B then
    elseif T and h > 0 then B = T + h
    elseif B and h > 0 then T = B - h
    elseif CY and h > 0 then T, B = CY - h / 2, CY + h / 2
    elseif T and CY then B = 2 * CY - T
    elseif B and CY then T = 2 * CY - B end
    r.L, r.R, r.T, r.B = L, R, T, B
    cache[o] = r
    return r
end

-- a status bar's fill: from the left (or the bottom) by the value's share of min..max, none at 0
local function fillRect(o, r)
    local bar = o.__fillOf
    local lo, hi = bar.__min or 0, bar.__max or 0
    local v = bar.__value
    if v == nil or (hi - lo) == 0 then return nil end
    local f = math.max(0, math.min(1, (v - lo) / (hi - lo)))
    if f <= 0 then return nil end
    local c = { L = r.L, R = r.R, T = r.T, B = r.B, ppu = r.ppu }
    if bar.__orient == "VERTICAL" then
        c.T = r.B - (r.B - r.T) * f
    else
        c.R = r.L + (r.R - r.L) * f
    end
    return c
end

local function clipOf(o)
    local L, T, R, B
    local f = o.__parent
    while f do
        if f.__otype == "ScrollFrame" then
            local r = resolve(f)
            if r and r.L and r.R and r.T and r.B then
                L, T = math.max(L or r.L, r.L), math.max(T or r.T, r.T)
                R, B = math.min(R or r.R, r.R), math.min(B or r.B, r.B)
            end
        end
        f = f.__parent
    end
    if L then return { L, T, R, B } end
end

------------------------------------------------------------------------------------------------------
-- JSON
------------------------------------------------------------------------------------------------------
local function jstr(s)
    return '"' .. s:gsub('[%c"\\]', function(c)
        if c == '"' then return '\\"' elseif c == "\\" then return "\\\\" elseif c == "\n" then return "\\n" end
        return string.format("\\u%04x", c:byte())
    end) .. '"'
end
local function json(v)
    local t = type(v)
    if t == "table" then
        if #v > 0 or next(v) == nil then
            local parts = {}
            for i = 1, #v do parts[i] = json(v[i]) end
            return "[" .. table.concat(parts, ",") .. "]"
        end
        local parts = {}
        for k, x in pairs(v) do parts[#parts + 1] = jstr(tostring(k)) .. ":" .. json(x) end
        return "{" .. table.concat(parts, ",") .. "}"
    elseif t == "string" then
        return jstr(v)
    elseif t == "number" then
        if v ~= v or v == math.huge or v == -math.huge then return "0" end
        return string.format("%.6f", v)
    elseif t == "boolean" then
        return v and "true" or "false"
    end
    return "null"
end

------------------------------------------------------------------------------------------------------
-- Dump
------------------------------------------------------------------------------------------------------
local STRATA = { BACKGROUND = 1, LOW = 2, MEDIUM = 3, HIGH = 4, DIALOG = 5, FULLSCREEN = 6, FULLSCREEN_DIALOG = 7,
    TOOLTIP = 8 }
local LAYER = { BACKGROUND = 1, BORDER = 2, ARTWORK = 3, OVERLAY = 4, HIGHLIGHT = 5 }
local index = {}
for i, o in ipairs(M.objects) do index[o] = i end
local rootSet
if roots then
    rootSet = {}
    for _, f in ipairs(roots) do rootSet[f] = true end
end

-- the HIGHLIGHT layer shows on a frame under the cursor (not a disabled button) or one that locked it
local function lit(f)
    if opts.hover == "all" then return f.__state ~= "DISABLED" end
    if f.__hlLocked then return true end
    return f.__mouseOver and f.__state ~= "DISABLED"
end

local out = {}
local function frameKeys(f)
    return STRATA[strataOf(f)] or 3, levelOf(f), index[f] or 0
end

local function colorOf(c)
    if not c then return { 1, 1, 1, 1 } end
    return { c[1] or 1, c[2] or 1, c[3] or 1, c[4] or 1 }
end

-- CBackdropGenerator: the background (BACKGROUND layer) inside the insets, tiled by tileSize (u = frame width /
-- tileSize) or stretched; eight 1/8-wide cells of the edge file (left, right, top, bottom, then the four corners;
-- top and bottom stored turned) in the BORDER layer, edges tiled every edgeSize, a 1/16 cell inset on the texcoords
local function backdropItems(f, r)
    local bd = f.__backdrop
    local strata, level, fidx = frameKeys(f)
    local ppu = r.ppu
    local alpha = alphaOf(f)
    local function piece(layer, sub, path, L, T, R, B, tc, wrap, color)
        if not path or path == "" or R - L < 0.01 or B - T < 0.01 then return end
        out[#out + 1] = { kind = "Texture", strata = strata, level = level, layer = layer, fidx = fidx,
            idx = fidx + sub / 100, alpha = alpha, L = L, R = R, T = T, B = B, ppu = ppu, path = path, tc = tc,
            wrap = wrap, color = color, blend = "BLEND", clip = clipOf(f), backdrop = true }
    end
    local wUnits, hUnits = (r.R - r.L) / ppu, (r.B - r.T) / ppu
    local ins = bd.insets or {}
    local il, ir, it, ib = (ins.left or 0) * ppu, (ins.right or 0) * ppu, (ins.top or 0) * ppu, (ins.bottom or 0) * ppu
    if bd.bgFile and bd.bgFile ~= "" then
        local tc = { 0, 0, 0, 1, 1, 0, 1, 1 }
        if bd.tile then
            local ts = (bd.tileSize and bd.tileSize ~= 0) and bd.tileSize or (bd.edgeSize or 16)
            local u, v = wUnits / ts, hUnits / ts
            tc = { 0, 0, 0, v, u, 0, u, v }
        end
        piece(1, 0, bd.bgFile, r.L + il, r.T + it, r.R - ir, r.B - ib, tc, bd.tile and true or false,
            colorOf(f.__bdcolor))
    end
    if bd.edgeFile and bd.edgeFile ~= "" then
        local es = bd.edgeSize or 16
        local e = es * ppu
        local tilesX = math.max(0, wUnits / es - 2)
        local tilesY = math.max(0, hUnits / es - 2)
        local c = colorOf(f.__bdborder)
        local s, ee = 0.0625, 0.9375
        piece(2, 1, bd.edgeFile, r.L, r.T + e, r.L + e, r.B - e,
            { 0.0078125, s, 0.0078125, tilesY - s, 0.1171875, s, 0.1171875, tilesY - s }, true, c)
        piece(2, 2, bd.edgeFile, r.R - e, r.T + e, r.R, r.B - e,
            { 0.1328125, s, 0.1328125, tilesY - s, 0.2421875, s, 0.2421875, tilesY - s }, true, c)
        piece(2, 3, bd.edgeFile, r.L + e, r.T, r.R - e, r.T + e,
            { 0.2578125, tilesX - s, 0.3671875, tilesX - s, 0.2578125, s, 0.3671875, s }, true, c)
        piece(2, 4, bd.edgeFile, r.L + e, r.B - e, r.R - e, r.B,
            { 0.3828125, tilesX - s, 0.4921875, tilesX - s, 0.3828125, s, 0.4921875, s }, true, c)
        local corners = { { 0.5078125, 0.6171875, r.L, r.T }, { 0.6328125, 0.7421875, r.R - e, r.T },
            { 0.7578125, 0.8671875, r.L, r.B - e }, { 0.8828125, 0.9921875, r.R - e, r.B - e } }
        for i, k in ipairs(corners) do
            piece(2, 4 + i, bd.edgeFile, k[3], k[4], k[3] + e, k[4] + e, { k[1], s, k[1], ee, k[2], s, k[2], ee },
                false, c)
        end
    end
end

-- Model frames: the preview cannot draw the 3D model, so each shown one goes out as a "Model" item with its frame type
-- (and the unit it shows, if any), and render.py marks the box as a model shown in game. The client draws a model
-- over its frame's own layers (CSimpleModel), so the item sits after HIGHLIGHT at the frame's strata and level;
-- frames above it (a higher level) still cover it.
local MODEL_TYPES = { Model = true, PlayerModel = true, DressUpModel = true, TabardModel = true }
local MODEL_LAYER = 6
local function modelItem(o, idx)
    local r = resolve(o)
    if not (r and r.L and r.R and r.T and r.B) or r.R - r.L < 1 or r.B - r.T < 1 then return end
    local alpha = alphaOf(o)
    if alpha <= 0 then return end
    local strata, level, fidx = frameKeys(o)
    out[#out + 1] = { kind = "Model", otype = o.__otype, unit = o.__unit, idx = idx, fidx = fidx, strata = strata,
        level = level, layer = MODEL_LAYER, alpha = alpha, L = r.L, R = r.R, T = r.T, B = r.B, ppu = r.ppu,
        clip = clipOf(o) }
end

local need = {}   -- what pass 1 asks render.py to measure
for idx, o in ipairs(M.objects) do
    local isFrame = o.GetEffectiveScale ~= nil and o.__otype ~= "Texture" and o.__otype ~= "FontString"
    if isFrame and o.__backdrop and visible(o) and (not rootSet or under(o, rootSet)) and o ~= env.UIParent then
        local r = resolve(o)
        if r and r.L and r.R and r.T and r.B then backdropItems(o, r) end
    end
    if isFrame and MODEL_TYPES[o.__otype] and visible(o) and (not rootSet or under(o, rootSet)) then
        modelItem(o, idx)
    end
    local region = o.__otype == "Texture" or o.__otype == "FontString"
    local editText = o.__otype == "EditBox" and o.__text and o.__text ~= "" and o.__font
    if (region or editText) and visible(o) and (not rootSet or under(o, rootSet)) then
        local f = region and o.__parent or o
        local layerName = region and (o.__layer or "ARTWORK") or "OVERLAY"
        if layerName ~= "HIGHLIGHT" or lit(f) then
            local r = resolve(o)
            if r and o.__fillOf then r = fillRect(o, r) end
            local strata, level, fidx = frameKeys(f)
            local item = {
                kind = o.__otype == "Texture" and "Texture" or "FontString", idx = idx, fidx = fidx, strata = strata,
                level = level, layer = LAYER[layerName] or 3, alpha = alphaOf(o),
                ppu = r and r.ppu, clip = clipOf(o),
            }
            if r then item.L, item.R, item.T, item.B = r.L, r.R, r.T, r.B end
            if o.__otype == "Texture" then
                item.path = o.__texture
                item.solid = o.__solid
                item.tc = o.__tc8 or { 0, 0, 0, 1, 1, 0, 1, 1 }
                item.color = colorOf(o.__color)
                item.grad = o.__grad
                item.blend = o.__blend or "BLEND"
                item.desat = o.__desat and true or false
                item.wrap = o.__wrap and true or false
                item.portrait = o.__portrait and true or false
                if item.path and not measure.sizes[item.path] then need[item.path] = true end
                if (item.path or item.solid) and r and r.L and r.R and r.T and r.B and item.alpha > 0 then
                    out[#out + 1] = item
                end
            else
                local font = o.__font
                if o.__text and o.__text ~= "" and font then
                    item.text = o.__text
                    item.font = font[1]
                    item.size = font[2]
                    item.flags = font[3] or ""
                    item.color = colorOf(o.__tcolor)
                    item.justify = o.__jh or (o.__otype == "EditBox" and "LEFT" or "CENTER")
                    item.justifyV = o.__jv or "MIDDLE"
                    item.spacing = o.__spacing or 0
                    item.shadow = { o.__sox or 0, o.__soy or 0 }
                    item.shadowColor = o.__sc or { 0, 0, 0, 0 }
                    item.px = r and r.px or math.floor(font[2] * pxOf(o) + 0.5)
                    item.wrapPx = r and r.wrapPx
                    item.fixedH = (o.__h or 0) > 0
                    if item.alpha > 0 then out[#out + 1] = item end
                end
            end
        end
    end
end
local needList = {}
for p in pairs(need) do needList[#needList + 1] = p end
table.sort(needList)
print(json({ w = W, h = Hpx, items = out, needSizes = needList, errors = M.errors }))
