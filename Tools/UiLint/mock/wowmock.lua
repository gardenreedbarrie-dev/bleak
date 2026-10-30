-- A small mock of the 3.3.5a game environment for Bleakhold unit tests (run by wowlua).
--
-- Strict where it matters:
--   * widget methods exist only if the client has them for that widget type (api.methods, extracted
--     from the client source), so SetColorTexture, SetAtlas & co. fail like they would in 3.3.5a;
--   * globals are only the client's C functions (api.globals), the Lua base set the game opens, the
--     client's own compat aliases (run from its source), and the FrameXML names in framexml_globals.txt;
--   * RegisterEvent only accepts events of the client's event table;
--   * FontString:SetText needs a font, SetPoint needs valid anchor names.
-- Unknown C functions are stubs that return nil (the addon must cope with that anyway).
--
-- local M = dofile("wowmock.lua")({ api = api, repo = root })
return function(opts)
    local api = opts.api
    local M = {
        now = 1000, t0 = 1000, epoch = 1792648725, playerName = "Tester", playerClass = "WARRIOR", playerLevel = 80,
        party = 0, raid = 0, leader = false, officer = false, inInstance = false, instanceType = "none", zone = "Dalaran",
        inWorld = false, combat = false, shift = false,
        sent = {}, objects = {}, errors = {}, calls = {}, textures = {}, fonts = {}, chat = {}, sounds = {}, items = {},
        companions = { MOUNT = {}, CRITTER = {} }, addons = {}, tryOn = {}, animations = {},
    }
    local env = {}
    M.env = env

    -- Lua base set of the game (FrameScript_Initialize: base, string, table, math, bit)
    for _, n in ipairs({ "assert", "collectgarbage", "error", "gcinfo", "getfenv", "getmetatable", "loadstring", "next",
        "pcall", "rawequal", "rawget", "rawset", "select", "setfenv", "setmetatable", "tonumber", "tostring", "type",
        "unpack", "xpcall", "ipairs", "pairs", "newproxy", "_VERSION", "coroutine", "string", "table", "math", "bit" }) do
        env[n] = _G[n]
    end
    env._G = env

    local function record(name)
        M.calls[name] = (M.calls[name] or 0) + 1
    end

    ------------------------------------------------------------------------------------------------
    -- FrameScript extras with the client's semantics (FrameScript_Scripts.cpp)
    ------------------------------------------------------------------------------------------------
    local function inSet(set, c)
        return set:find(c, 1, true) ~= nil
    end
    env.strtrim = function(s, chars)
        assert(type(s) == "string" or type(s) == "number", "Usage: strtrim(string [, chars])")
        s = tostring(s)
        chars = chars or " \t\r\n"
        local i, j = 1, #s
        while i <= j and inSet(chars, s:sub(i, i)) do i = i + 1 end
        while j >= i and inSet(chars, s:sub(j, j)) do j = j - 1 end
        return s:sub(i, j)
    end
    env.strsplit = function(delims, s, limit)
        assert(type(delims) == "string" and (type(s) == "string" or type(s) == "number"), "Usage: strsplit(delimiters, string [, limit])")
        s = tostring(s)
        limit = limit or 0
        local out, start = {}, 1
        if limit == 0 or limit > 1 then
            for i = 1, #s do
                if inSet(delims, s:sub(i, i)) then
                    out[#out + 1] = s:sub(start, i - 1)
                    start = i + 1
                    if #out == limit - 1 then break end
                end
            end
        end
        if #out > 7900 then error("strsplit(): Stack overflow") end
        out[#out + 1] = s:sub(start)
        return unpack(out)
    end
    env.strjoin = function(sep, ...)
        assert(type(sep) == "string", "Usage: strjoin(separator, ...)")
        return table.concat({ ... }, sep)
    end
    env.strreplace = function(s, a, b)
        local out = s:gsub(a:gsub("%p", "%%%0"), (b:gsub("%%", "%%%%")))
        return out
    end
    env.strconcat = function(...) return table.concat({ ... }) end
    env.strlenutf8 = function(s) local _, n = s:gsub("[^\128-\191]", "") return n end
    env.date = function(fmt, t)
        fmt = fmt or "%c"
        t = t or env.time()
        if t < 0 then return nil end          -- gmtime/localtime fail on Windows
        local s = host_date(fmt, t)
        if s == "" then error("'date' format too long") end
        return s
    end
    env.time = function(t) if t then return host_time(t) end return M.epoch + math.floor(M.now - M.t0) end
    env.difftime = function(a, b) return a - b end
    env.issecure = function() return false end
    env.issecurevariable = function() return false, nil end
    env.securecall = function(fn, ...) if type(fn) == "string" then fn = env[fn] end return fn(...) end
    env.hooksecurefunc = function(a, b, c)
        local tbl, name, hook = env, a, b
        if type(a) == "table" then tbl, name, hook = a, b, c end
        local orig = tbl[name]
        assert(type(orig) == "function", "hooksecurefunc(): " .. tostring(name) .. " is not a function")
        tbl[name] = function(...)
            local r = { orig(...) }
            hook(...)
            return unpack(r)
        end
    end
    M.errorHandler = function(err)
        M.errors[#M.errors + 1] = tostring(err)
        if not M.quietErrors then
            print("  [addon error] " .. tostring(err))
        end
    end
    env.geterrorhandler = function() return M.errorHandler end
    env.seterrorhandler = function(f) M.errorHandler = f end
    env.debugprofilestop = function() return host_clock() * 1000 end
    env.debugstack = function() return "" end

    -- The client's own compat aliases, run from its source text.
    do
        local chunk = assert(loadstring(api.compat_lua, "compat.lua"))
        setfenv(chunk, env)
        chunk()
    end

    ------------------------------------------------------------------------------------------------
    -- Widgets
    ------------------------------------------------------------------------------------------------
    local POINTS = { TOPLEFT = 1, TOP = 1, TOPRIGHT = 1, LEFT = 1, CENTER = 1, RIGHT = 1, BOTTOMLEFT = 1, BOTTOM = 1, BOTTOMRIGHT = 1 }
    local STRATA = { BACKGROUND = 1, LOW = 1, MEDIUM = 1, HIGH = 1, DIALOG = 1, FULLSCREEN = 1, FULLSCREEN_DIALOG = 1, TOOLTIP = 1, PARENT = 1 }
    local LAYERS = { BACKGROUND = 1, BORDER = 1, ARTWORK = 1, OVERLAY = 1, HIGHLIGHT = 1 }
    local CREATABLE = { Frame = 1, Button = 1, CheckButton = 1, EditBox = 1, StatusBar = 1, Slider = 1, ScrollFrame = 1,
        Model = 1, PlayerModel = 1, DressUpModel = 1, TabardModel = 1, MessageFrame = 1, ScrollingMessageFrame = 1,
        SimpleHTML = 1, ColorSelect = 1, Cooldown = 1, GameTooltip = 1, MovieFrame = 1 }
    local ANIMS = { Animation = 1, Alpha = 1, Scale = 1, Rotation = 1, Translation = 1, Path = 1 }

    local IMPL = {}
    local stubs = {}

    local function isA(otype, want)
        local t = otype
        while t do
            if t == want then return true end
            t = api.parents[t]
        end
        return false
    end

    local function lookup(otype, k)
        local allowed = api.methods[otype]
        if not allowed or not allowed[k] then
            return nil
        end
        local impl = IMPL[k]
        if impl then
            return impl
        end
        local s = stubs[k]
        if not s then
            s = function(self) record(otype .. ":" .. k) end
            stubs[k] = s
        end
        return s
    end

    local function new(otype, name, parent)
        local o = {
            __otype = otype, __name = name, __parent = parent, __shown = true, __scripts = {}, __points = {},
            __w = 0, __h = 0, __alpha = 1, __scale = 1, __events = {}, __children = {}, __regions = {}, __level = 1,
            __strata = "MEDIUM", __enabled = true,
        }
        setmetatable(o, { __index = function(_, k) return lookup(otype, k) end, __tostring = function() return otype .. ":" .. tostring(name) end })
        if parent and type(parent) == "table" and parent.__children then
            if isA(otype, "Frame") then
                table.insert(parent.__children, o)
            else
                table.insert(parent.__regions, o)
            end
        end
        M.objects[#M.objects + 1] = o
        if name then
            env[name] = o
        end
        return o
    end
    M.New = new

    local function fire(o, script, ...)
        local fn = o.__scripts[script]
        if fn then
            return fn(o, ...)
        end
    end
    M.Fire = fire

    function IMPL.GetName(self) return self.__name end
    function IMPL.GetObjectType(self) return self.__otype end
    function IMPL.IsObjectType(self, t) return isA(self.__otype, t) end
    function IMPL.GetParent(self) return self.__parent end
    function IMPL.SetParent(self, p) self.__parent = p end
    function IMPL.Show(self)
        if not self.__shown then
            self.__shown = true
            fire(self, "OnShow")
        end
    end
    function IMPL.Hide(self)
        if self.__shown then
            self.__shown = false
            fire(self, "OnHide")
            if self.__otype == "GameTooltip" then
                fire(self, "OnTooltipCleared")
            end
        end
    end
    function IMPL.IsShown(self) return self.__shown and 1 or nil end
    function IMPL.IsVisible(self)
        local o = self
        while o do
            if not o.__shown then return nil end
            o = o.__parent
        end
        return 1
    end
    local function checkPoint(self, point, rel, relPoint, x, y)
        assert(POINTS[point], "SetPoint: invalid point " .. tostring(point))
        if relPoint ~= nil and type(relPoint) ~= "number" then
            assert(POINTS[relPoint], "SetPoint: invalid relative point " .. tostring(relPoint))
        end
        assert(rel ~= self, "SetPoint: cannot anchor to itself")
    end
    function IMPL.SetPoint(self, point, rel, relPoint, x, y)
        if type(rel) == "number" then
            rel, relPoint, x, y = nil, nil, rel, relPoint
        end
        checkPoint(self, point, rel, relPoint, x, y)
        if type(rel) == "string" then
            rel = env[rel]
        end
        -- where in the addon this anchor was set (for layout test messages)
        local where = host_traceback and host_traceback("", 2):match("Interface\\AddOns\\[^:\n]+:%d+") or "?"
        self.__points[#self.__points + 1] = { point, rel or self.__parent, relPoint or point, x or 0, y or 0, where }
    end
    function IMPL.SetAllPoints(self, rel)
        self.__points = { { "TOPLEFT", rel or self.__parent, "TOPLEFT", 0, 0 }, { "BOTTOMRIGHT", rel or self.__parent, "BOTTOMRIGHT", 0, 0 } }
        if type(rel) == "table" then
            self.__w, self.__h = rel.__w, rel.__h
        end
    end
    function IMPL.ClearAllPoints(self) self.__points = {} end
    function IMPL.GetNumPoints(self) return #self.__points end
    function IMPL.GetPoint(self, i)
        local p = self.__points[i or 1]
        if p then return p[1], p[2], p[3], p[4], p[5] end
    end
    local function num(v, what)
        assert(type(v) == "number" and v == v, what .. ": number expected, got " .. tostring(v))
        return v
    end
    function IMPL.SetWidth(self, w) self.__w = num(w, "SetWidth") end
    function IMPL.SetHeight(self, h) self.__h = num(h, "SetHeight") end
    function IMPL.SetSize(self, w, h) self.__w = num(w, "SetSize"); self.__h = num(h, "SetSize") end
    function IMPL.GetWidth(self) return self.__w end
    function IMPL.GetHeight(self) return self.__h end
    function IMPL.GetSize(self) return self.__w, self.__h end
    function IMPL.SetAlpha(self, a) self.__alpha = num(a, "SetAlpha") end
    function IMPL.GetAlpha(self) return self.__alpha end
    function IMPL.SetScale(self, s) assert(num(s, "SetScale") > 0, "SetScale: scale must be > 0"); self.__scale = s end
    function IMPL.GetScale(self) return self.__scale end
    function IMPL.GetEffectiveScale(self)
        local s, o = 1, self
        while o do s = s * (o.__scale or 1); o = o.__parent end
        return s
    end
    function IMPL.GetCenter(self) return self.__cx or 512, self.__cy or 384 end
    function IMPL.GetLeft(self) return (self.__cx or 512) - self.__w / 2 end
    function IMPL.GetRight(self) return (self.__cx or 512) + self.__w / 2 end
    function IMPL.GetTop(self) return (self.__cy or 384) + self.__h / 2 end
    function IMPL.GetBottom(self) return (self.__cy or 384) - self.__h / 2 end
    function IMPL.IsMouseOver(self) return self.__mouseOver and 1 or nil end
    function IMPL.SetFrameStrata(self, s) assert(STRATA[s], "SetFrameStrata: invalid strata " .. tostring(s)); self.__strata = s end
    function IMPL.GetFrameStrata(self) return self.__strata end
    function IMPL.SetFrameLevel(self, l) self.__level = num(l, "SetFrameLevel") end
    function IMPL.GetFrameLevel(self) return self.__level end
    function IMPL.SetID(self, id) self.__id = id end
    function IMPL.GetID(self) return self.__id or 0 end
    function IMPL.GetChildren(self) return unpack(self.__children) end
    function IMPL.GetRegions(self) return unpack(self.__regions) end

    function IMPL.SetScript(self, script, fn)
        assert(type(script) == "string" and script:match("^On%u"), "SetScript: bad handler name " .. tostring(script))
        assert(fn == nil or type(fn) == "function", "SetScript: function expected")
        self.__scripts[script] = fn
    end
    function IMPL.GetScript(self, script) return self.__scripts[script] end
    function IMPL.HookScript(self, script, fn)
        local prev = self.__scripts[script]
        if prev then
            self.__scripts[script] = function(...) prev(...); fn(...) end
        else
            self.__scripts[script] = fn
        end
    end
    function IMPL.RegisterEvent(self, event)
        assert(api.events[event], "RegisterEvent: unknown event " .. tostring(event))
        self.__events[event] = true
    end
    function IMPL.UnregisterEvent(self, event) self.__events[event] = nil end
    function IMPL.UnregisterAllEvents(self) self.__events = {} end
    function IMPL.IsEventRegistered(self, event) return self.__events[event] and 1 or nil end

    function IMPL.CreateTexture(self, name, layer)
        assert(layer == nil or LAYERS[layer], "CreateTexture: invalid layer " .. tostring(layer))
        local t = new("Texture", name, self)
        t.__layer = layer or "ARTWORK"
        return t
    end
    function IMPL.CreateFontString(self, name, layer, inherits)
        assert(layer == nil or LAYERS[layer], "CreateFontString: invalid layer " .. tostring(layer))
        local fs = new("FontString", name, self)
        fs.__layer = layer or "ARTWORK"
        if inherits then
            assert(env[inherits], "CreateFontString: unknown font object " .. tostring(inherits))
            fs.__font = env[inherits].__font
        end
        return fs
    end
    function IMPL.CreateAnimationGroup(self, name)
        local g = new("AnimationGroup", name, nil)
        g.__owner, g.__anims, g.__shown = self, {}, true
        M.animations[#M.animations + 1] = g
        return g
    end
    function IMPL.CreateAnimation(self, atype, name)
        assert(ANIMS[atype or "Animation"], "CreateAnimation: invalid type " .. tostring(atype))
        local a = new(atype or "Animation", name, nil)
        a.__group, a.__duration, a.__delay, a.__order = self, 0, 0, 1
        table.insert(self.__anims, a)
        return a
    end
    function IMPL.SetDuration(self, d) self.__duration = num(d, "SetDuration") end
    function IMPL.SetStartDelay(self, d) self.__delay = num(d, "SetStartDelay") end
    function IMPL.SetOrder(self, o) self.__order = num(o, "SetOrder") end
    function IMPL.SetChange(self, c) self.__change = num(c, "SetChange") end
    function IMPL.Play(self)
        self.__playing, self.__t = true, 0
        fire(self, "OnPlay")
    end
    function IMPL.Stop(self)
        if self.__playing then
            self.__playing = false
            fire(self, "OnStop")
        end
    end
    function IMPL.IsPlaying(self) return self.__playing and 1 or nil end
    function IMPL.SetLooping(self, l) self.__looping = l end

    -- Like Script_SetTexture: a file that cannot be loaded (M.missingTextures) returns nil and keeps the
    -- old texture; nil clears it. Numbers make a solid colour texture (CSimpleTexture::SetTexture(CImVector),
    -- kept in __solid, alpha 1 when left out); the file's second argument turns on wrapping (tiling, __wrap).
    -- __tried is the last file asked for, loaded or not (a missing file the code never replaced is visible to tests).
    M.missingTextures = {}
    function IMPL.SetTexture(self, a, g, b, al)
        if type(a) == "string" then
            M.textures[a] = true
            self.__tried = a
            if M.missingTextures[a] then
                return nil
            end
            self.__texture = a
            self.__solid, self.__portrait = nil, nil
            self.__wrap = g and true or nil
        elseif type(a) == "number" then
            self.__texture, self.__portrait, self.__tried = nil, nil, nil
            self.__solid = { a, tonumber(g) or 0, tonumber(b) or 0, tonumber(al) or 1 }
        elseif a == nil then
            self.__texture, self.__solid, self.__portrait, self.__tried = nil, nil, nil, nil
        else
            error("SetTexture: string or numbers expected")
        end
        return 1
    end
    function IMPL.GetTexture(self) return self.__texture end
    -- One vertex colour replaces a gradient and a gradient replaces the vertex colour (CSimpleRegion.cpp: both set
    -- m_colorCount; GetVertexColor answers white while a gradient is on).
    function IMPL.SetVertexColor(self, r, g, b, a)
        self.__color = { num(r, "SetVertexColor"), num(g, "SetVertexColor"), num(b, "SetVertexColor"), a }
        self.__grad = nil
    end
    local ORIENTATIONS = { HORIZONTAL = true, VERTICAL = true }
    local function orientation(o, usage)
        local u = type(o) == "string" and o:upper()
        assert(u and ORIENTATIONS[u], usage)
        return u
    end
    -- Script_SetGradient / Script_SetGradientAlpha (CSimpleTexture_Scripts.cpp): HORIZONTAL runs min (left) to max
    -- (right), VERTICAL min (bottom) to max (top); SetGradient keeps both alphas at 1.
    function IMPL.SetGradient(self, o, r1, g1, b1, r2, g2, b2)
        local u = orientation(o, "Usage: " .. tostring(self.__name or "<unnamed>")
            .. ":SetGradient(\"orientation\", minR, minG, minB, maxR, maxG, maxB)")
        self.__grad = { u, num(r1, "SetGradient"), num(g1, "SetGradient"), num(b1, "SetGradient"), 1,
            num(r2, "SetGradient"), num(g2, "SetGradient"), num(b2, "SetGradient"), 1 }
        self.__color = nil
    end
    function IMPL.SetGradientAlpha(self, o, r1, g1, b1, a1, r2, g2, b2, a2)
        local u = orientation(o, "Usage: " .. tostring(self.__name or "<unnamed>")
            .. ":SetGradientAlpha(\"orientation\", minR, minG, minB, minA, maxR, maxG, maxB, maxA)")
        self.__grad = { u, num(r1, "SetGradientAlpha"), num(g1, "SetGradientAlpha"), num(b1, "SetGradientAlpha"),
            num(a1, "SetGradientAlpha"), num(r2, "SetGradientAlpha"), num(g2, "SetGradientAlpha"),
            num(b2, "SetGradientAlpha"), num(a2, "SetGradientAlpha") }
        self.__color = nil
    end
    -- StringToBlendMode's names; the texture keeps the mode (__blend, BLEND until set)
    local BLENDS = { DISABLE = true, BLEND = true, ALPHAKEY = true, ADD = true, MOD = true }
    function IMPL.SetBlendMode(self, mode)
        assert(type(mode) == "string" and BLENDS[mode:upper()], "Usage: " .. tostring(self.__name or "<unnamed>")
            .. ":SetBlendMode(\"mode\")")
        self.__blend = mode:upper()
    end
    function IMPL.GetBlendMode(self) return self.__blend or "BLEND" end
    function IMPL.GetVertexColor(self) local c = self.__color or { 1, 1, 1, 1 } return c[1], c[2], c[3], c[4] or 1 end
    function IMPL.SetTexCoord(self, ...)
        local n = select("#", ...)
        assert(n == 4 or n == 8, "SetTexCoord: 4 or 8 numbers expected")
        for i = 1, n do num(select(i, ...), "SetTexCoord") end
        self.__tc = { ... }
        if n == 4 then
            local l, r, t, b = ...
            self.__tc8 = { l, t, l, b, r, t, r, b }
        else
            self.__tc8 = { ... }
        end
    end
    -- The four corners UL, LL, UR, LR as CSimpleTexture keeps them (m_texCoords), also after a 4-number SetTexCoord
    -- or a SetRotation; __tc keeps the numbers of the last call as they were given.
    function IMPL.GetTexCoord(self)
        return unpack(self.__tc8 or { 0, 0, 0, 1, 1, 0, 1, 1 }, 1, 8)
    end
    -- Script_SetRotation (CSimpleTexture_Scripts.cpp): all four texcoords become a square of radius 1 around (cx, cy)
    -- turned by angle - pi/4, so an atlas cell set before is lost. Every call goes to M.rotations with the texture's
    -- file and its region's size, for the tests that allow it on square standalone art only.
    M.rotations = {}
    function IMPL.SetRotation(self, angle, cx, cy)
        assert(type(angle) == "number",
            "Usage: " .. tostring(self.__name or "<unnamed>") .. ":SetRotation(angle, [cx, cy])")
        if type(cx) ~= "number" or type(cy) ~= "number" then
            cx, cy = 0.5, 0.5
        end
        local s, c = math.sin(angle - 0.78539819), math.cos(angle - 0.78539819)
        self.__tc8 = { s + cx, cy - c, cx - c, cy - s, c + cx, s + cy, cx - s, cy + c }
        self.__tc = { unpack(self.__tc8) }
        self.__angle = angle
        M.rotations[#M.rotations + 1] = {
            path = self.__texture, width = self.__w, height = self.__h, angle = angle, texture = self,
        }
    end
    function IMPL.SetDrawLayer(self, layer) assert(LAYERS[layer], "SetDrawLayer: invalid layer " .. tostring(layer)); self.__layer = layer end
    function IMPL.GetDrawLayer(self) return self.__layer or "ARTWORK" end
    function IMPL.SetBackdrop(self, bd)
        if bd then
            assert(type(bd) == "table", "SetBackdrop: table expected")
            if bd.bgFile then M.textures[bd.bgFile] = true end
            if bd.edgeFile then M.textures[bd.edgeFile] = true end
        end
        self.__backdrop = bd
    end
    function IMPL.SetBackdropColor(self, r, g, b, a) self.__bdcolor = { num(r, "SetBackdropColor"), num(g, "x"), num(b, "x"), a } end
    function IMPL.SetBackdropBorderColor(self, r, g, b, a) self.__bdborder = { num(r, "SetBackdropBorderColor"), num(g, "x"), num(b, "x"), a } end

    function IMPL.SetFont(self, path, size, flags)
        assert(type(path) == "string" and type(size) == "number" and size > 0, "SetFont: path and size expected")
        M.fonts[path] = true
        self.__font = { path, size, flags }
        return 1
    end
    function IMPL.GetFont(self) if self.__font then return unpack(self.__font) end end
    function IMPL.SetFontObject(self, fo)
        if type(fo) == "string" then fo = env[fo] end
        assert(type(fo) == "table" and fo.__font, "SetFontObject: font object with a font expected")
        self.__font = fo.__font
    end
    function IMPL.SetText(self, t)
        assert(t == nil or type(t) == "string" or type(t) == "number", "SetText: string expected, got " .. type(t))
        if (self.__otype == "FontString" or self.__otype == "EditBox") and not self.__font then
            error(self.__otype .. ":SetText(): Font not set")
        end
        self.__text = t ~= nil and tostring(t) or nil
        if self.__otype == "EditBox" then fire(self, "OnTextChanged", false) end
    end
    function IMPL.SetFormattedText(self, fmt, ...) IMPL.SetText(self, string.format(fmt, ...)) end
    function IMPL.GetText(self) return self.__text end
    -- CSimpleFontString::GetStringWidth measures the text as shown (GetDisplayText(width, height)): with both a width
    -- and a height set it is cut to the box with "...", so it is never wider than the width. Tests opt in with
    -- M.clientCut (or its other name, M.measureAsShown); off by default, so the tests that check a line is not cut can
    -- still measure the whole of it.
    function IMPL.GetStringWidth(self)
        local size = self.__font and self.__font[2] or 12
        local full = #(self.__text or ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "") * size * 0.52
        if (M.clientCut or M.measureAsShown) and (self.__w or 0) > 0 and (self.__h or 0) > 0 then
            return math.min(full, self.__w)
        end
        return full
    end
    function IMPL.GetStringHeight(self) return self.__font and self.__font[2] or 12 end
    function IMPL.SetTextColor(self, r, g, b, a) self.__tcolor = { num(r, "SetTextColor"), num(g, "x"), num(b, "x"), a } end
    function IMPL.GetTextColor(self) local c = self.__tcolor or { 1, 1, 1 } return c[1], c[2], c[3], c[4] or 1 end
    function IMPL.SetJustifyH(self, j) assert(j == "LEFT" or j == "CENTER" or j == "RIGHT", "SetJustifyH: bad value " .. tostring(j)); self.__jh = j end
    function IMPL.SetJustifyV(self, j)
        assert(j == "TOP" or j == "MIDDLE" or j == "BOTTOM", "SetJustifyV: bad value " .. tostring(j))
        self.__jv = j
    end
    function IMPL.SetSpacing(self, s) self.__spacing = num(s, "SetSpacing") end
    function IMPL.GetSpacing(self) return self.__spacing or 0 end

    ------------------------------------------------------------------------------------------------
    -- Button state textures (CSimpleButton.cpp). Set*Texture takes a file (a new texture of the button's ARTWORK
    -- layer over all of it), a texture object (moved to the button's ARTWORK layer) or nil; only the texture of the
    -- button's state shows, and a state without its own texture keeps the one showing (SetButtonState), except
    -- NORMAL. The highlight texture sits in the HIGHLIGHT layer, ADD unless a blend mode is given.
    ------------------------------------------------------------------------------------------------
    local STATE_KEYS = { NORMAL = "__normalTex", PUSHED = "__pushedTex", DISABLED = "__disabledTex" }
    local function dropRegion(t)
        t.__shown, t.__dropped = false, true
    end
    local function setStateTexture(self, state, tex)
        local key = STATE_KEYS[state]
        local old = self[key]
        if tex == old then return end
        if self.__activeTex == old then self.__activeTex = nil end
        if old then dropRegion(old) end
        self[key] = tex
        if tex then
            tex.__parent, tex.__layer, tex.__shown, tex.__dropped = self, "ARTWORK", false, nil
            if (self.__state or "NORMAL") == state then
                self.__activeTex = tex
                tex.__shown = true
            end
        end
    end
    local function stateTextureArg(self, state, arg, method)
        if type(arg) == "table" then
            assert(arg.__otype == "Texture", tostring(self.__name or "<unnamed>") .. ":" .. method
                .. "(): Wrong object type, expected texture")
            setStateTexture(self, state, arg)
        elseif type(arg) == "string" then
            local cur = self[STATE_KEYS[state]]
            if cur then
                IMPL.SetTexture(cur, arg)
                return
            end
            local t = new("Texture", nil, self)
            t.__layer = "ARTWORK"
            if not IMPL.SetTexture(t, arg) then
                dropRegion(t)
                return
            end
            IMPL.SetAllPoints(t, self)
            setStateTexture(self, state, t)
        else
            assert(arg == nil, "Usage: " .. tostring(self.__name or "<unnamed>") .. ":" .. method
                .. "(texture or \"texture\" or nil)")
            setStateTexture(self, state, nil)
        end
    end
    function IMPL.SetNormalTexture(self, arg) stateTextureArg(self, "NORMAL", arg, "SetNormalTexture") end
    function IMPL.SetPushedTexture(self, arg) stateTextureArg(self, "PUSHED", arg, "SetPushedTexture") end
    function IMPL.SetDisabledTexture(self, arg) stateTextureArg(self, "DISABLED", arg, "SetDisabledTexture") end
    function IMPL.GetNormalTexture(self) return self.__normalTex end
    function IMPL.GetPushedTexture(self) return self.__pushedTex end
    function IMPL.GetDisabledTexture(self) return self.__disabledTex end
    function IMPL.SetHighlightTexture(self, arg, mode)
        local blend = type(mode) == "string" and BLENDS[mode:upper()] and mode:upper() or "ADD"
        local t
        if type(arg) == "table" then
            assert(arg.__otype == "Texture", tostring(self.__name or "<unnamed>")
                .. ":SetHighlightTexture(): Wrong object type, expected texture")
            if arg == self.__highlightTex then return end
            if self.__highlightTex then dropRegion(self.__highlightTex) end
            t = arg
            t.__parent, t.__layer, t.__shown, t.__dropped = self, "HIGHLIGHT", true, nil
        elseif type(arg) == "string" then
            t = self.__highlightTex
            if t then
                IMPL.SetTexture(t, arg)
            else
                t = new("Texture", nil, self)
                t.__layer = "HIGHLIGHT"
                if not IMPL.SetTexture(t, arg) then
                    dropRegion(t)
                    return
                end
                IMPL.SetAllPoints(t, self)
            end
        else
            return
        end
        t.__blend = blend
        self.__highlightTex = t
    end
    function IMPL.GetHighlightTexture(self) return self.__highlightTex end
    local BUTTON_STATES = { NORMAL = true, PUSHED = true, DISABLED = true }
    local function setButtonState(self, state, locked)
        self.__stateLocked = locked and true or nil
        local cur = self.__state or "NORMAL"
        if state == cur then return end
        local tex = self[STATE_KEYS[state]]
        if self.__activeTex and (tex or state == "NORMAL") then
            self.__activeTex.__shown = false
            self.__activeTex = nil
        end
        if tex then
            self.__activeTex = tex
            tex.__shown = true
        end
        self.__state = state
        -- CSimpleCheckbox: the disabled checked texture stands in for the checked one while disabled
        if self.__checkedTex or self.__disabledCheckedTex then IMPL.SetChecked(self, self.__checked) end
    end
    function IMPL.SetButtonState(self, state, locked)
        assert(BUTTON_STATES[state], "Usage: " .. tostring(self.__name or "<unnamed>")
            .. ":SetButtonState(\"state\" [, lock])")
        setButtonState(self, state, locked)
    end
    function IMPL.GetButtonState(self) return self.__state or "NORMAL" end
    function IMPL.LockHighlight(self) self.__hlLocked = true end
    function IMPL.UnlockHighlight(self) self.__hlLocked = nil end
    function IMPL.SetPushedTextOffset(self, x, y)
        self.__pushedOffset = { num(x, "SetPushedTextOffset"), num(y, "SetPushedTextOffset") }
    end
    function IMPL.GetPushedTextOffset(self) local p = self.__pushedOffset or { 0, 0 } return p[1], p[2] end

    function IMPL.Enable(self)
        self.__enabled = true
        if isA(self.__otype, "Button") and self.__state == "DISABLED" then setButtonState(self, "NORMAL") end
    end
    function IMPL.Disable(self)
        self.__enabled = false
        if isA(self.__otype, "Button") then setButtonState(self, "DISABLED") end
    end
    function IMPL.IsEnabled(self) return self.__enabled and 1 or nil end
    -- CSimpleButton: off by default (the constructor), so a disabled button runs no OnEnter / OnLeave (M.Hover)
    function IMPL.SetMotionScriptsWhileDisabled(self, on) self.__motionWhileDisabled = on and true or nil end
    function IMPL.GetMotionScriptsWhileDisabled(self) return self.__motionWhileDisabled and 1 or nil end
    function IMPL.Click(self, button)
        if self.__enabled then fire(self, "OnClick", button or "LeftButton", false) end
    end
    -- CSimpleCheckbox.cpp: the checked texture (OVERLAY, over all of the button) shows while checked; while disabled
    -- the disabled checked texture replaces it when there is one
    local function checkTextureArg(self, key, arg, method)
        local old = self[key]
        if type(arg) == "string" then
            if old then
                IMPL.SetTexture(old, arg)
            else
                local t = new("Texture", nil, self)
                t.__layer = "OVERLAY"
                if not IMPL.SetTexture(t, arg) then
                    dropRegion(t)
                    return
                end
                IMPL.SetAllPoints(t, self)
                self[key] = t
            end
        elseif type(arg) == "table" then
            assert(arg.__otype == "Texture", tostring(self.__name or "<unnamed>") .. ":" .. method
                .. "(): Wrong object type, expected texture")
            if old and old ~= arg then dropRegion(old) end
            arg.__parent, arg.__layer, arg.__dropped = self, "OVERLAY", nil
            self[key] = arg
        else
            if old then dropRegion(old) end
            self[key] = nil
        end
        IMPL.SetChecked(self, self.__checked)
    end
    function IMPL.SetCheckedTexture(self, arg) checkTextureArg(self, "__checkedTex", arg, "SetCheckedTexture") end
    function IMPL.SetDisabledCheckedTexture(self, arg)
        checkTextureArg(self, "__disabledCheckedTex", arg, "SetDisabledCheckedTexture")
    end
    function IMPL.GetCheckedTexture(self) return self.__checkedTex end
    function IMPL.GetDisabledCheckedTexture(self) return self.__disabledCheckedTex end
    function IMPL.SetChecked(self, c)
        self.__checked = c and true or false
        local on, dis = self.__checkedTex, self.__disabledCheckedTex
        if on then on.__shown = false end
        if dis then dis.__shown = false end
        if self.__checked then
            local t = (dis and self.__state == "DISABLED") and dis or on
            if t then t.__shown = true end
        end
    end
    function IMPL.GetChecked(self) return self.__checked and 1 or nil end
    function IMPL.SetFocus(self) self.__focus = true; fire(self, "OnEditFocusGained") end
    function IMPL.ClearFocus(self) self.__focus = false end
    function IMPL.HasFocus(self) return self.__focus and 1 or nil end

    function IMPL.SetMinMaxValues(self, a, b) self.__min, self.__max = num(a, "SetMinMaxValues"), num(b, "SetMinMaxValues") end
    function IMPL.GetMinMaxValues(self) return self.__min or 0, self.__max or 1 end
    function IMPL.SetValue(self, v) self.__value = num(v, "SetValue") end
    function IMPL.GetValue(self) return self.__value or 0 end
    function IMPL.SetOrientation(self, o)
        self.__orient = orientation(o, "Usage: " .. tostring(self.__name or "<unnamed>")
            .. ":SetOrientation(\"orientation\")")
    end
    function IMPL.GetOrientation(self) return self.__orient or "HORIZONTAL" end
    -- CSimpleStatusBar.cpp: the bar texture (a file: a new texture, ARTWORK unless a layer is given; or a texture
    -- object) covers the filled part (value between min and max, from the left, or from the bottom when VERTICAL;
    -- hidden at 0); SetStatusBarColor is its vertex colour. The preview renderer draws the fill from __bar and the
    -- values.
    function IMPL.SetStatusBarTexture(self, arg, layer)
        layer = (type(layer) == "string" and LAYERS[layer]) and layer or "ARTWORK"
        local t
        if type(arg) == "table" then
            assert(arg.__otype == "Texture", tostring(self.__name or "<unnamed>")
                .. ":SetStatusBarTexture(): Wrong object type, expected texture")
            if self.__bar and self.__bar ~= arg then dropRegion(self.__bar) end
            t = arg
            t.__parent, t.__dropped = self, nil
        elseif type(arg) == "string" then
            t = self.__bar
            if t then
                IMPL.SetTexture(t, arg)
            else
                t = new("Texture", nil, self)
                if not IMPL.SetTexture(t, arg) then
                    dropRegion(t)
                    return
                end
            end
        else
            return
        end
        t.__layer = layer
        IMPL.SetAllPoints(t, self)
        t.__fillOf = self
        self.__bar = t
        if self.__barColor then
            local c = self.__barColor
            IMPL.SetVertexColor(t, c[1], c[2], c[3], c[4])
        end
    end
    function IMPL.GetStatusBarTexture(self) return self.__bar end
    function IMPL.SetStatusBarColor(self, r, g, b, a)
        self.__barColor = { num(r, "SetStatusBarColor"), num(g, "x"), num(b, "x"), a }
        if self.__bar then IMPL.SetVertexColor(self.__bar, r, g, b, a) end
    end
    function IMPL.GetStatusBarColor(self)
        local c = self.__barColor or { 1, 1, 1, 1 }
        return c[1], c[2], c[3], c[4] or 1
    end
    -- CSimpleSlider.cpp: the thumb (a file: a new OVERLAY texture; or a texture object, its own anchors dropped) hangs
    -- from the slider's TOP (VERTICAL) or LEFT, (length - thumb) * position along; the preview renderer places it.
    function IMPL.SetThumbTexture(self, arg, layer)
        local t
        if type(arg) == "table" then
            assert(arg.__otype == "Texture", tostring(self.__name or "<unnamed>")
                .. ":SetThumbTexture(): Wrong object type, expected texture")
            if self.__thumb and self.__thumb ~= arg then dropRegion(self.__thumb) end
            t = arg
            t.__parent, t.__dropped = self, nil
            if type(layer) == "string" and LAYERS[layer] then t.__layer = layer end
        elseif type(arg) == "string" then
            t = self.__thumb
            if t then
                IMPL.SetTexture(t, arg)
            else
                t = new("Texture", nil, self)
                t.__layer = "OVERLAY"
                if not IMPL.SetTexture(t, arg) then
                    dropRegion(t)
                    return
                end
            end
        else
            return
        end
        t.__thumbOf = self
        self.__thumb = t
    end
    function IMPL.GetThumbTexture(self) return self.__thumb end

    function IMPL.SetScrollChild(self, c) self.__scrollChild = c end
    function IMPL.GetScrollChild(self) return self.__scrollChild end
    function IMPL.SetVerticalScroll(self, v) self.__vscroll = num(v, "SetVerticalScroll") end
    function IMPL.GetVerticalScroll(self) return self.__vscroll or 0 end
    function IMPL.GetVerticalScrollRange(self) return 0 end

    function IMPL.SetUnit(self, unit) self.__unit = unit end
    function IMPL.SetSequence(self, id)
        -- CSimpleModel_Scripts.cpp: a number in 0 - 505, else a Lua error
        assert(type(id) == "number" and id >= 0 and id < 506, "SetSequence(sequence) exceeds valid range of 0 - 506")
        self.__sequence = math.floor(id)
    end
    function IMPL.Undress(self) M.tryOn = {} end
    function IMPL.TryOn(self, item) M.tryOn[#M.tryOn + 1] = item end
    function IMPL.SetFacing(self, f) self.__facing = num(f, "SetFacing") end
    function IMPL.GetFacing(self) return self.__facing or 0 end
    function IMPL.SetPosition(self, x, y, z) self.__pos = { num(x, "SetPosition"), num(y, "x"), num(z, "x") } end
    function IMPL.GetPosition(self) local p = self.__pos or { 0, 0, 0 } return p[1], p[2], p[3] end
    -- Model:SetModel(file) and SetModelScale(scale) (CSimpleModel_Scripts.cpp): kept for tests (__model, __modelScale)
    function IMPL.SetModel(self, file)
        assert(type(file) == "string", "Usage: SetModel(\"file\")")
        self.__model = file
    end
    function IMPL.SetModelScale(self, s) self.__modelScale = num(s, "SetModelScale") end

    function IMPL.SetOwner(self, owner, anchor) self.__owner = owner; self.__lines = {}; self.__item = nil; self.__shown = true end
    function IMPL.GetOwner(self) return self.__owner end
    function IMPL.IsOwned(self, f) return (self.__shown and self.__owner == f) and 1 or nil end
    function IMPL.ClearLines(self) self.__lines = {}; self.__item = nil; fire(self, "OnTooltipCleared") end
    function IMPL.AddLine(self, text, r, g, b, wrap)
        self.__lines = self.__lines or {}
        table.insert(self.__lines, tostring(text))
    end
    function IMPL.AddDoubleLine(self, a, b) IMPL.AddLine(self, tostring(a) .. "\t" .. tostring(b)) end
    function IMPL.NumLines(self) return #(self.__lines or {}) end
    function IMPL.SetHyperlink(self, link)
        IMPL.ClearLines(self)
        local id = tonumber(tostring(link):match("item:(%d+)"))
        if id then
            local info = M.items[id]
            local name = info and info.name or ("Item " .. id)
            self.__item = { name, "|cffa335ee|Hitem:" .. id .. ":0:0:0:0:0:0:0:80|h[" .. name .. "]|h|r" }
            IMPL.AddLine(self, name)
            fire(self, "OnTooltipSetItem")
        end
    end
    -- the bag and bank hovers (ContainerFrameItemButton_OnEnter, BankFrameItemButton_OnEnter): the slot's item as
    -- env.GetContainerItemLink / GetInventoryItemLink give it, set like SetHyperlink (cleared, OnTooltipSetItem)
    function IMPL.SetBagItem(self, bag, slot) IMPL.SetHyperlink(self, env.GetContainerItemLink(bag, slot) or "") end
    function IMPL.SetInventoryItem(self, unit, slot) IMPL.SetHyperlink(self, env.GetInventoryItemLink(unit, slot) or "") end
    function IMPL.GetItem(self) if self.__item then return self.__item[1], self.__item[2] end end
    function IMPL.AddMessage(self, msg) table.insert(M.chat, { frame = self, msg = msg }) end
    function IMPL.SetMaxLetters(self, n) self.__maxLetters = n end
    function IMPL.GetMaxLetters(self) return self.__maxLetters or 0 end

    ------------------------------------------------------------------------------------------------
    -- Global C functions
    ------------------------------------------------------------------------------------------------
    for name in pairs(api.globals) do
        if env[name] == nil then
            env[name] = function() record(name) end
        end
    end

    env.CreateFrame = function(otype, name, parent, template)
        assert(CREATABLE[otype], "CreateFrame: unknown frame type " .. tostring(otype))
        -- only GameTooltipTemplate (for the hidden item-cache tooltip); no other FrameXML template
        assert(template == nil or (template == "GameTooltipTemplate" and otype == "GameTooltip"),
            "CreateFrame: unexpected FrameXML template " .. tostring(template))
        if type(parent) == "string" then parent = env[parent] end
        local f = new(otype, name, parent)
        if otype == "GameTooltip" then f.__shown = false end
        return f
    end
    env.CreateFont = function(name)
        local f = new("Font", name, nil)
        return f
    end
    env.GetTime = function() return M.now end
    env.UnitName = function(unit) if unit == "player" then return M.playerName end end
    env.UnitClass = function(unit) if unit == "player" then return "Warrior", M.playerClass end end
    env.UnitLevel = function(unit) if unit == "player" then return M.playerLevel end return 0 end
    -- the player and every member M.SetGroup made are online (1); a test stubs an offline one
    env.UnitIsConnected = function(unit)
        local kind, n = tostring(unit):match("^(%a+)(%d*)$")
        n = tonumber(n) or 0
        local count = kind == "party" and M.party or kind == "raid" and M.raid or 0
        if unit == "player" or (n >= 1 and n <= count) then
            return 1
        end
    end
    env.UnitRace = function(unit) if unit == "player" then return "Human", "Human" end end
    env.GetRealmName = function() return "Bleakhold" end
    env.GetLocale = function() return "enUS" end
    env.GetNumPartyMembers = function() return M.party end
    env.GetNumRaidMembers = function() return M.raid end
    env.IsPartyLeader = function() return M.leader and 1 or nil end
    env.IsRaidLeader = function() return (M.raid > 0 and M.leader) and 1 or nil end
    env.IsRaidOfficer = function() return (M.raid > 0 and (M.leader or M.officer)) and 1 or nil end
    env.IsInInstance = function() return M.inInstance and 1 or nil, M.instanceType end
    env.GetRealZoneText = function() return M.zone end
    env.GetInstanceInfo = function() return M.zone, M.instanceType, 1, "Normal", 5, 0, nil end
    env.InCombatLockdown = function() return M.combat and 1 or nil end
    env.UnitAffectingCombat = function(unit) return (unit == "player" and M.combat) and 1 or nil end
    -- M.dead: the player is dead or a ghost (the café's summary card waits for PLAYER_ALIVE / PLAYER_UNGHOST)
    env.UnitIsDeadOrGhost = function(unit) return (unit == "player" and M.dead) and 1 or nil end
    env.IsShiftKeyDown = function() return M.shift and 1 or nil end
    -- the player's movement (Script_IsFalling: 1 while falling or jumping); tests set M.falling
    env.IsFalling = function() return M.falling and 1 or nil end
    env.IsControlKeyDown = function() return nil end
    env.IsAltKeyDown = function() return nil end
    env.IsModifiedClick = function() return nil end
    M.cursorX, M.cursorY = 512, 384
    env.GetCursorPosition = function() return M.cursorX, M.cursorY end
    -- Emotes and key bindings (ChatFrame_Scripts.cpp, UIBindings_Scripts.cpp)
    M.emotes, M.bindings, M.savedBindings = {}, {}, 0
    env.DoEmote = function(token, unit)
        assert(type(token) == "string" and token ~= "", "Usage: DoEmote(\"emote\" [, \"target\"])")
        M.emotes[#M.emotes + 1] = token
    end
    env.GetBindingKey = function(action)
        for key, a in pairs(M.bindings) do
            if a == action then return key end
        end
    end
    env.GetBindingAction = function(key) return M.bindings[key] or "" end
    env.SetBinding = function(key, action)
        assert(not M.combat, "SetBinding in combat")
        M.bindings[key] = action
        return 1
    end
    -- the set in use: 1 the account's (ACCOUNT_BINDINGS), 2 the character's own (CHARACTER_BINDINGS); a test sets
    -- M.bindingSet = 2 for "Character Specific Key Bindings"
    M.savedBindingSets = {}
    env.GetCurrentBindingSet = function() return M.bindingSet or 1 end
    env.SaveBindings = function(which)
        assert(which == 1 or which == 2, "Usage: SaveBindings(1 or 2)")
        M.savedBindings = M.savedBindings + 1
        M.savedBindingSets[#M.savedBindingSets + 1] = which
    end
    -- UIParent's size in UI units (Script_GetScreenWidth/Height); M.SetScreen changes it
    M.screenW, M.screenH = 1024, 768
    env.GetScreenWidth = function() return M.screenW end
    env.GetScreenHeight = function() return M.screenH end
    env.PlaySound = function(s) M.sounds[#M.sounds + 1] = s end
    -- CVars the client registered (only those GetCVar/SetCVar find, ConsoleVar.cpp LookupRegistered)
    M.cvars = {}
    -- the window's size in physical pixels (the UI's own 1024x768 layout above stays the tests' default; M.SetScreen
    -- sets both together)
    M.cvars.gxResolution = "1920x1080"
    M.screenPixels = { 1920, 1080 }
    env.GetCVar = function(name) return M.cvars[name] end
    env.SetCVar = function(name, value)
        assert(M.cvars[name] ~= nil, "Couldn't find CVar named '" .. tostring(name) .. "'")
        M.cvars[name] = tostring(value)
    end
    env.IsAddOnLoaded = function(n) return M.addons[n] and 1 or nil end
    -- DisableAddOn / ReloadUI (GameUI_Scripts.cpp): the addon is off for this character from the next UI load;
    -- M.disabledAddons keeps the names, M.reloads counts ReloadUI calls
    M.disabledAddons, M.reloads = {}, 0
    env.DisableAddOn = function(n)
        assert(type(n) == "string" or type(n) == "number", "Usage: DisableAddOn(index or \"name\")")
        M.disabledAddons[#M.disabledAddons + 1] = n
    end
    env.ReloadUI = function() M.reloads = M.reloads + 1 end
    env.GetItemInfo = function(id)
        if type(id) == "string" then id = tonumber(id:match("item:(%d+)")) end
        local i = id and M.items[id]
        if i then return i.name, "|cffa335ee|Hitem:" .. id .. "|h[" .. i.name .. "]|h|r", 4, 60, 60, "Armor", "Plate", 1, "INVTYPE_CHEST", "Interface\\Icons\\INV_Misc_QuestionMark" end
    end
    env.GetItemIcon = function() return "Interface\\Icons\\INV_Misc_QuestionMark" end
    -- Script_SetPortraitToTexture (GameUI_Scripts.cpp, PortraitButton.cpp): the texture (object or name) shows the file
    -- as a 64x64 circle (TempPortraitAlphaMaskSmall); a file that does not load leaves it as it was. __texture keeps
    -- the file and __portrait the circle, for tests and the preview renderer.
    env.SetPortraitToTexture = function(tex, path)
        if type(tex) == "string" then tex = env[tex] end
        assert(type(tex) == "table" and tex.__otype == "Texture",
            "SetPortraitToTexture(): Wrong object type, expected texture")
        if type(path) ~= "string" or path == "" then return end
        M.textures[path] = true
        tex.__tried = path
        if M.missingTextures[path] then return end
        tex.__texture, tex.__solid, tex.__portrait = path, nil, true
    end
    env.GetNumCompanions = function(kind) return #(M.companions[kind] or {}) end
    env.GetCompanionInfo = function(kind, i)
        local c = (M.companions[kind] or {})[i]
        if c then return c.creatureID, c.name, c.spellID, c.icon, c.active end
    end
    M.said = {}
    env.SendChatMessage = function(msg, chatType, language, target)
        assert(type(msg) == "string", "Usage: SendChatMessage(\"text\" [,\"type\" [,language [,\"target\"]]])")
        assert(#msg <= 255, "SendChatMessage: message longer than 255 bytes")
        if chatType == "WHISPER" then assert(type(target) == "string" and target ~= "", "SendChatMessage: WHISPER needs a target") end
        M.said[#M.said + 1] = { msg = msg, chatType = chatType, language = language, target = target }
    end
    env.SendAddonMessage = function(prefix, msg, chatType, target)
        assert(type(prefix) == "string" and type(msg) == "string", "Usage: SendAddonMessage(\"prefix\", \"text\", \"type\" [, \"target\"])")
        assert(not prefix:find("\t"), "SendAddonMessage: prefix with a tab")
        chatType = chatType or "PARTY"
        assert(chatType == "PARTY" or chatType == "RAID" or chatType == "GUILD" or chatType == "BATTLEGROUND" or chatType == "WHISPER",
            "SendAddonMessage: bad chat type " .. tostring(chatType))
        if chatType == "WHISPER" then assert(type(target) == "string", "SendAddonMessage: WHISPER needs a target") end
        if not M.inWorld then return end   -- the client does nothing without an active player
        if chatType == "PARTY" and M.party == 0 and M.raid == 0 then return end
        M.sent[#M.sent + 1] = { prefix = prefix, msg = msg, channel = chatType, target = target, t = M.now }
    end
    -- Script_IsIndoors (ScriptEvents_Scripts.cpp): 1 while the player is not outdoors; tests set M.indoors
    env.IsIndoors = function() return M.indoors and 1 or nil end
    -- Script_GetMapInfo (WorldMap_Scripts.cpp): the file name of the map the world map shows; tests set M.mapInfo
    env.GetMapInfo = function() return M.mapInfo end
    -- Script_PlaySoundFile (SoundInterface2_Scripts.cpp): every file in M.soundFiles, its time in M.soundFileTimes
    M.soundFiles, M.soundFileTimes = {}, {}
    env.PlaySoundFile = function(path)
        assert(type(path) == "string" or type(path) == "number", "Usage: PlaySoundFile(\"soundfile\")")
        M.soundFiles[#M.soundFiles + 1] = tostring(path)
        M.soundFileTimes[#M.soundFileTimes + 1] = M.now
        return 1
    end
    -- The view distance (GameUI_Scripts.cpp: both read and write the farclip CVar). 777 is a value of the hardware
    -- table (ConsoleDetect.cpp), below the 1277 a fresh install starts at.
    M.farclip = 777
    env.GetFarclip = function() return M.farclip end
    env.SetFarclip = function(v)
        assert(type(v) == "number", "Usage: SetFarclip(value)")
        M.farclip = v
    end
    -- Override bindings (UIBindings_Scripts.cpp), owned by a frame. Both are protected, so like the originals they
    -- fail in combat lockdown: the mock raises. M.overrideBindings lists { owner, priority, key, command } in the
    -- order they were set; M.OverrideAction(key) answers the command a key runs through them.
    M.overrideBindings = {}
    local function bindingOwner(owner, usage)
        assert(type(owner) == "table" and owner.__otype and isA(owner.__otype, "Frame"), usage)
    end
    env.SetOverrideBinding = function(owner, isPriority, key, command)
        local usage = "Usage: SetOverrideBinding(owner, isPriority, \"KEY\"[, \"COMMAND\"])"
        bindingOwner(owner, usage)
        assert(type(key) == "string", usage)
        assert(not M.combat, "SetOverrideBinding in combat")
        for i = #M.overrideBindings, 1, -1 do
            local b = M.overrideBindings[i]
            if b.owner == owner and b.key == key then
                table.remove(M.overrideBindings, i)
            end
        end
        if type(command) == "string" then
            M.overrideBindings[#M.overrideBindings + 1] = { owner = owner, priority = isPriority and true or false,
                key = key, command = command }
        end
    end
    -- the café's barista bar (CafeBar.lua): a key clicks a named button, the client's command "CLICK name:mouseButton"
    -- in the same list (M.OverrideButton(key) answers the button and whether the binding has priority)
    env.SetOverrideBindingClick = function(owner, isPriority, key, button, mouseButton)
        local usage = "Usage: SetOverrideBindingClick(owner, isPriority, \"KEY\", \"buttonName\"[, \"mouseButton\"])"
        bindingOwner(owner, usage)
        assert(type(key) == "string" and type(button) == "string", usage)
        assert(not M.combat, "SetOverrideBindingClick in combat")
        env.SetOverrideBinding(owner, isPriority, key, "CLICK " .. button .. ":" .. (mouseButton or "LeftButton"))
        local b = M.overrideBindings[#M.overrideBindings]
        b.button = button
    end
    function M.OverrideButton(key)
        local command = M.OverrideAction(key)
        for _, b in ipairs(M.overrideBindings) do
            if b.key == key and b.command == command and b.button then
                return b.button, b.priority
            end
        end
    end
    env.ClearOverrideBindings = function(owner)
        bindingOwner(owner, "Usage: ClearOverrideBindings(owner)")
        assert(not M.combat, "ClearOverrideBindings in combat")
        for i = #M.overrideBindings, 1, -1 do
            if M.overrideBindings[i].owner == owner then
                table.remove(M.overrideBindings, i)
            end
        end
    end
    function M.OverrideAction(key)
        local found
        for _, b in ipairs(M.overrideBindings) do
            if b.key == key and (not found or b.priority or not found.priority) then
                found = b
            end
        end
        return found and found.command
    end

    ------------------------------------------------------------------------------------------------
    -- FrameXML (framexml_globals.txt)
    ------------------------------------------------------------------------------------------------
    env.UIParent = new("Frame", "UIParent", nil)
    env.UIParent:SetSize(1024, 768)
    env.MinimapCluster = new("Frame", "MinimapCluster", env.UIParent)
    env.Minimap = new("Minimap", "Minimap", env.MinimapCluster)
    env.Minimap:SetSize(140, 140)
    env.Minimap.__cx, env.Minimap.__cy = 940, 680
    env.MinimapBackdrop = new("Frame", "MinimapBackdrop", env.Minimap)
    env.GameTooltip = new("GameTooltip", "GameTooltip", env.UIParent)
    env.GameTooltip.__shown = false
    env.ItemRefTooltip = new("GameTooltip", "ItemRefTooltip", env.UIParent)
    env.ShoppingTooltip1 = new("GameTooltip", "ShoppingTooltip1", env.UIParent)
    env.ShoppingTooltip2 = new("GameTooltip", "ShoppingTooltip2", env.UIParent)
    env.UIErrorsFrame = new("MessageFrame", "UIErrorsFrame", env.UIParent)
    env.WatchFrame = new("Frame", "WatchFrame", env.UIParent)
    env.NUM_CHAT_WINDOWS = 3
    for i = 1, 3 do
        new("ScrollingMessageFrame", "ChatFrame" .. i, env.UIParent)
    end
    env.DEFAULT_CHAT_FRAME = env.ChatFrame1
    env.UISpecialFrames = {}
    env.SlashCmdList = {}
    env.RAID_CLASS_COLORS = { WARRIOR = { r = 0.78, g = 0.61, b = 0.43 }, PALADIN = { r = 0.96, g = 0.55, b = 0.73 }, MAGE = { r = 0.41, g = 0.8, b = 0.94 } }
    env.ITEM_QUALITY_COLORS = { [4] = { r = 0.64, g = 0.21, b = 0.93, hex = "|cffa335ee" } }
    M.chatFilters = {}
    env.ChatFrame_AddMessageEventFilter = function(event, fn)
        assert(api.events[event], "ChatFrame_AddMessageEventFilter: unknown event " .. tostring(event))
        M.chatFilters[event] = M.chatFilters[event] or {}
        table.insert(M.chatFilters[event], fn)
    end
    env.ChatEdit_InsertLink = function(link) M.insertedLink = link return true end
    env.ChatFrame_SendTell = function(name) M.tellOpened = name end
    -- Stock chat pieces the addon wraps, as FrameXML 3.3.5a has them (ChatFrame.lua), with the autocomplete list
    -- (friends, guild, group, recent) reduced to exact names in M.autocomplete.
    M.autocomplete = {}
    env.ChatEdit_UpdateHeader = function(box) M.headerUpdated = box end
    env.ChatEdit_ExtractTellTarget = function(editBox, msg)
        local target = msg:match("%s*(.*)")
        if not target or not target:find("%s") or target:sub(1, 1) == "|" then return false end
        if M.autocomplete[target] then return false end
        while target:find("%s") do
            target = target:match("(.+)%s+[^%s]*")
            if M.autocomplete[target] then break end
        end
        msg = msg:sub(#target + 2)
        editBox:SetAttribute("tellTarget", target)
        editBox:SetAttribute("chatType", "WHISPER")
        editBox:SetText(msg)
        env.ChatEdit_UpdateHeader(editBox)
        return true
    end
    env.AddOrRemoveFriend = function(name, note) M.friended = { name = name, note = note } end
    env.SlashCmdList.FRIENDS = function(msg)
        local player, note = msg:match("%s*([^%s]+)%s*(.*)")
        if player and player ~= "" then
            env.AddOrRemoveFriend(player, note)
        else
            M.friendsPanel = true
        end
    end
    env.StaticPopupDialogs = {
        ADD_GUILDMEMBER = { maxLetters = 12 }, ADD_TEAMMEMBER = { maxLetters = 12 },
        ADD_RAIDMEMBER = { maxLetters = 12 }, ADD_MUTE = { maxLetters = 12 }, ADD_FRIEND = { maxLetters = 77 },
    }
    -- StaticPopup.lua / StaticPopup.xml (3.3.5a): four dialogs StaticPopup1..4 (DIALOG strata, 320 wide, DialogBox
    -- backdrop, white text, two StaticPopupButtonTemplate buttons). StaticPopup_Show(which, arg1, arg2, data) finds
    -- StaticPopupDialogs[which] (nil when there is none), reuses the dialog already showing it or takes the first free
    -- one, formats the text, runs OnShow and returns the dialog; StaticPopup_Hide(which [, data]) hides it. Every show
    -- is in M.popups; M.StaticPopupClick(which, 1 or 2) presses a button like a player (OnAccept / OnCancel, then
    -- hide).
    M.popups = {}
    local function popupButton(dialog, i)
        local b = new("Button", dialog.__name .. "Button" .. i, dialog)
        b:SetSize(128, 21)
        local tc = { 0, 1, 0, 0.71875 }
        for _, s in ipairs({ { "SetNormalTexture", "Up" }, { "SetPushedTexture", "Down" },
            { "SetDisabledTexture", "Disabled" }, { "SetHighlightTexture", "Highlight" } }) do
            IMPL[s[1]](b, "Interface\\Buttons\\UI-DialogBox-Button-" .. s[2])
        end
        for _, t in ipairs({ b.__normalTex, b.__pushedTex, b.__disabledTex, b.__highlightTex }) do
            IMPL.SetTexCoord(t, unpack(tc))
        end
        local fs = IMPL.CreateFontString(b, b.__name .. "Text", "OVERLAY")
        IMPL.SetFont(fs, "Fonts\\FRIZQT__.TTF", 12)
        IMPL.SetTextColor(fs, 1, 0.82, 0)
        IMPL.SetPoint(fs, "CENTER", b, "CENTER", 0, 1)
        b.text = fs
        b:SetScript("OnClick", function(self) M.StaticPopupClick(dialog.which, i, dialog) end)
        return b
    end
    local popupDialogs = {}
    for i = 1, 4 do
        local d = new("Frame", "StaticPopup" .. i, env.UIParent)
        d.__shown = false
        d:SetFrameStrata("DIALOG")
        d:SetSize(320, 72)
        d:SetPoint("TOP", env.UIParent, "TOP", 0, -135 - (i - 1) * 100)
        IMPL.SetBackdrop(d, { bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
            edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border", tile = true, tileSize = 32, edgeSize = 32,
            insets = { left = 11, right = 12, top = 12, bottom = 11 } })
        d.text = IMPL.CreateFontString(d, d.__name .. "Text", "ARTWORK")
        IMPL.SetFont(d.text, "Fonts\\FRIZQT__.TTF", 12)
        d.text:SetWidth(290)
        d.text:SetPoint("TOP", d, "TOP", 0, -16)
        d.button1, d.button2 = popupButton(d, 1), popupButton(d, 2)
        d.button1:SetPoint("BOTTOMRIGHT", d, "BOTTOM", -6, 16)
        d.button2:SetPoint("LEFT", d.button1, "RIGHT", 13, 0)
        popupDialogs[i] = d
    end
    env.StaticPopup_Show = function(which, a1, a2, data)
        local info = env.StaticPopupDialogs[which]
        if not info then return nil end
        local dialog
        for _, d in ipairs(popupDialogs) do
            if d.__shown and d.which == which then dialog = d break end
        end
        if not dialog then
            for _, d in ipairs(popupDialogs) do
                if not d.__shown then dialog = d break end
            end
        end
        if not dialog then return nil end
        dialog.which, dialog.data = which, data
        local text = string.format(info.text or "", a1, a2)
        dialog.text:SetText(text)
        -- StaticPopup_Resize: the text's height between a 16 px top and the buttons (the mock's GetStringHeight
        -- knows one line; the preview driver measures the wrapped text)
        local lines = select(2, text:gsub("\n", "")) + 1
        dialog:SetHeight(16 + math.max(lines * 12, dialog.text:GetStringHeight()) + 8 + 21 + 16)
        for i, b in ipairs({ dialog.button1, dialog.button2 }) do
            local label = info["button" .. i]
            b.text:SetText(label)
            b.__shown = label ~= nil
        end
        if not info.button2 then
            dialog.button1:ClearAllPoints()
            dialog.button1:SetPoint("BOTTOM", dialog, "BOTTOM", 0, 16)
        else
            dialog.button1:ClearAllPoints()
            dialog.button1:SetPoint("BOTTOMRIGHT", dialog, "BOTTOM", -6, 16)
        end
        M.popups[#M.popups + 1] = { which = which, text = text, data = data, dialog = dialog }
        dialog:Show()
        if info.OnShow then info.OnShow(dialog, data) end
        return dialog
    end
    env.StaticPopup_Hide = function(which, data)
        for _, d in ipairs(popupDialogs) do
            if d.__shown and d.which == which and (data == nil or d.data == data) then
                d:Hide()
                local info = env.StaticPopupDialogs[which]
                if info and info.OnHide then info.OnHide(d, d.data) end
            end
        end
    end
    function M.StaticPopupClick(which, button, dialog)
        if not dialog then
            for _, d in ipairs(popupDialogs) do
                if d.__shown and d.which == which then dialog = d break end
            end
        end
        assert(dialog, "StaticPopupClick: no dialog showing " .. tostring(which))
        local info = env.StaticPopupDialogs[which] or {}
        -- button2 runs OnCancel only (a dialog without one just hides), never OnAccept
        local fn
        if button == 2 then fn = info.OnCancel else fn = info.OnAccept end
        if fn then fn(dialog, dialog.data, "clicked") end
        env.StaticPopup_Hide(which)
    end
    new("EditBox", "SendMailNameEditBox", env.UIParent):SetMaxLetters(12)
    env.DressUpItemLink = function(link) M.dressedUp = link end
    env.TogglePVPFrame = function() M.pvpFrameToggled = (M.pvpFrameToggled or 0) + 1 end
    -- the stock Dungeon Finder: a UI panel, hidden until ShowUIPanel or ToggleLFDParentFrame opens it
    env.LFDParentFrame = new("Frame", "LFDParentFrame", env.UIParent)
    env.LFDParentFrame.__shown = false
    env.ShowUIPanel = function(frame) if frame then frame:Show() end end
    env.ToggleLFDParentFrame = function()
        if env.LFDParentFrame:IsShown() then env.LFDParentFrame:Hide() else env.ShowUIPanel(env.LFDParentFrame) end
    end
    -- GetMinimapShape, DragonUI*, DBM: absent unless a test sets them
    -- BleakholdUI_ScreenPixels (Bleakhold.exe): absent unless a test sets it (M.screenPixels has the numbers)

    -- The stock error text's own anchor (UIErrorsFrame.xml: 512x60, TOP of UIParent, 122 down); its points are
    -- recorded like every region's, so a test sees where the addon moved it and that it came back.
    env.UIErrorsFrame:SetSize(512, 60)
    env.UIErrorsFrame:SetPoint("TOP", env.UIParent, "TOP", 0, -122)
    -- WorldFrame and the world map: absent until a test asks (M.LoadWorldFrame, M.LoadWorldMap)
    -- UIParent.lua's HideUIPanel, reduced to hiding the frame (the panel layout is not modelled); every call is in
    -- M.hiddenPanels
    M.hiddenPanels = {}
    env.HideUIPanel = function(frame)
        M.hiddenPanels[#M.hiddenPanels + 1] = frame
        if frame then frame:Hide() end
    end

    ------------------------------------------------------------------------------------------------
    -- Driving the mock
    ------------------------------------------------------------------------------------------------
    function M.FireEvent(event, ...)
        assert(api.events[event], "FireEvent: unknown event " .. tostring(event))
        for _, o in ipairs(M.objects) do
            if o.__events[event] then
                fire(o, "OnEvent", event, ...)
            end
        end
    end

    -- Run a chat message through the registered chat filters like ChatFrame_MessageEventHandler does.
    function M.FilterChat(event, frame, msg, ...)
        for _, fn in ipairs(M.chatFilters[event] or {}) do
            local hide, newMsg = fn(frame, event, msg, ...)
            if hide then return nil end
            if newMsg then msg = newMsg end
        end
        return msg
    end

    local function animDuration(g)
        local orders = {}
        for _, a in ipairs(g.__anims) do
            local d = (a.__delay or 0) + (a.__duration or 0)
            orders[a.__order] = math.max(orders[a.__order] or 0, d)
        end
        local total = 0
        for _, d in pairs(orders) do total = total + d end
        return total
    end

    function M.Advance(seconds, step)
        step = step or 0.1
        local t = 0
        while t < seconds - 1e-9 do
            local dt = math.min(step, seconds - t)
            M.now = M.now + dt
            t = t + dt
            local list = {}
            for _, o in ipairs(M.objects) do
                if o.__scripts.OnUpdate and IMPL.IsVisible(o) then list[#list + 1] = o end
            end
            for _, o in ipairs(list) do
                if o.__scripts.OnUpdate then fire(o, "OnUpdate", dt) end
            end
            for _, g in ipairs(M.animations) do
                if g.__playing then
                    g.__t = g.__t + dt
                    if g.__t >= animDuration(g) then
                        if g.__looping and g.__looping ~= "NONE" then
                            g.__t = 0
                        else
                            g.__playing = false
                            fire(g, "OnFinished")
                        end
                    end
                end
            end
        end
    end

    function M.EnterWorld()
        M.inWorld = true
        M.FireEvent("PLAYER_ENTERING_WORLD")
    end

    function M.SetGroup(kind, size, leader)
        M.party, M.raid = 0, 0
        if kind == "PARTY" then M.party = size - 1 elseif kind == "RAID" then M.raid = size end
        M.leader = leader and true or false
    end

    -- Every visible frame whose text contains s (for window checks).
    function M.FindText(s, visibleOnly)
        local found = {}
        for _, o in ipairs(M.objects) do
            if o.__text and o.__text:find(s, 1, true) and (not visibleOnly or IMPL.IsVisible(o)) then
                found[#found + 1] = o
            end
        end
        return found
    end

    -- The cursor enters (on) or leaves a frame: IsMouseOver answers it, OnEnter / OnLeave run, and a frame under the
    -- cursor lights its HIGHLIGHT layer (CSimpleFrame; a disabled button does not, CSimpleButton::OnLayerCursorEnter).
    -- A disabled button runs OnEnter / OnLeave only after SetMotionScriptsWhileDisabled(true) (CSimpleButton.cpp:832).
    function M.Hover(frame, on)
        if on == nil then on = true end
        frame.__mouseOver = on and true or nil
        if isA(frame.__otype, "Button") and not frame.__enabled and not frame.__motionWhileDisabled then
            return
        end
        fire(frame, on and "OnEnter" or "OnLeave", true)
    end

    function M.Clickables(root)
        local out = {}
        local function walk(f)
            if f.__otype == "Button" or f.__otype == "CheckButton" then out[#out + 1] = f end
            for _, c in ipairs(f.__children or {}) do walk(c) end
        end
        walk(root)
        return out
    end

    -- Load an addon folder like the client: TOC files in order, each Lua chunk called with (name, ns).
    function M.LoadAddon(dir, name)
        local toc = assert(host_readfile(dir .. "/" .. name .. ".toc"), "no toc")
        local ns = {}
        M.ns = ns
        M.loaded = {}
        for line in toc:gmatch("[^\r\n]+") do
            line = line:gsub("%s+$", "")
            if line ~= "" and not line:match("^#") then
                local path = dir .. "/" .. line:gsub("\\", "/")
                if line:lower():match("%.lua$") then
                    local chunk, err = host_loadfile(path, "Interface\\AddOns\\" .. name .. "\\" .. line)
                    assert(chunk, err)
                    setfenv(chunk, env)
                    chunk(name, ns)
                    M.loaded[#M.loaded + 1] = line
                elseif line:lower():match("%.xml$") then
                    error("XML files in the TOC are not supported by the mock: " .. line)
                end
            end
        end
        return ns
    end

    -- The 3D world's frame (WorldFrame.xml): not under UIParent, so Alt-Z does not hide it and the UI scale does not
    -- scale it. Call it in a test's `before` when the addon parents frames to it at load.
    function M.LoadWorldFrame()
        local f = new("Frame", "WorldFrame", nil)
        f:SetSize(768 * M.screenW / M.screenH, 768)
        return f
    end

    -- The world map (WorldMapFrame.xml), hidden until opened: the detail frame holds the 1002x668 map tiles, and
    -- WorldMapButton (the map area the player arrow and the POIs live on) sits over it at frame level 5. Call it in a
    -- test's `before` when the addon hooks the map at load.
    function M.LoadWorldMap()
        local map = new("Frame", "WorldMapFrame", env.UIParent)
        map.__shown = false
        map:SetFrameStrata("FULLSCREEN")
        map:SetSize(1024, 768)
        local detail = new("Frame", "WorldMapDetailFrame", map)
        detail:SetSize(1002, 668)
        detail:SetPoint("TOPLEFT", map, "TOPLEFT", 0, 0)
        detail:SetFrameLevel(2)
        local button = new("Button", "WorldMapButton", map)
        button:SetSize(1002, 668)
        button:SetPoint("TOPLEFT", detail, "TOPLEFT", 0, 0)
        button:SetFrameLevel(5)
        return map
    end

    -- A window of w x h physical pixels, with the UI scale the player chose (useUiScale 1) or none (nil). UIParent's
    -- scale follows the client: ScaleToScreenSize without a UI scale (768/h, at least 0.9), SetUIScale with one (at
    -- least 0.64), and both cap it at aspect * 0.75 on screens narrower than 4:3 (GameUI.cpp, GameUI_CVar.cpp).
    -- UIParent is then 768 * aspect / scale x 768 / scale units; DISPLAY_SIZE_CHANGED fires.
    function M.SetScreen(w, h, uiScale)
        assert(type(w) == "number" and type(h) == "number" and w > 0 and h > 0, "SetScreen(w, h [, uiScale])")
        local aspect = w / h
        local scale
        if uiScale then
            scale = uiScale
            M.cvars.useUiScale, M.cvars.uiScale = "1", tostring(uiScale)
        else
            scale = h > 768 and 768 / h or 1
            M.cvars.useUiScale = "0"
        end
        if aspect * 3 < 4 and aspect * 0.75 <= scale then
            scale = aspect * 0.75
        end
        scale = math.max(scale, uiScale and 0.64 or 0.9)
        M.cvars.gxResolution = w .. "x" .. h
        M.screenPixels = { w, h }
        env.UIParent:SetScale(scale)
        M.screenW, M.screenH = 768 * aspect / scale, 768 / scale
        env.UIParent:SetSize(M.screenW, M.screenH)
        if env.WorldFrame then
            env.WorldFrame:SetSize(768 * aspect, 768)
        end
        M.FireEvent("DISPLAY_SIZE_CHANGED")
    end

    -- Combat lockdown in the client's order (GameUI.cpp SetRegenEnabled): PLAYER_REGEN_DISABLED fires while protected
    -- actions are still allowed, PLAYER_REGEN_ENABLED once they are allowed again.
    function M.SetCombat(on)
        if on then
            M.FireEvent("PLAYER_REGEN_DISABLED")
            M.combat = true
        else
            M.combat = false
            M.FireEvent("PLAYER_REGEN_ENABLED")
        end
    end

    -- Blizzard_BattlefieldMinimap (Shift-M, load-on-demand): its frame, hidden like the stock one until shown, with
    -- the twelve map tiles BattlefieldMinimap1..12 (4 x 3 of a 225-unit-wide map), then ADDON_LOADED as LoadAddOn
    -- sends it.
    function M.LoadBattlefieldMinimap()
        local f = new("Frame", "BattlefieldMinimap", env.UIParent)
        f.__shown = false
        f:SetSize(225, 150)
        f:SetFrameStrata("LOW")
        local tile = 225 / 4
        for i = 1, 12 do
            local t = f:CreateTexture("BattlefieldMinimap" .. i, "BACKGROUND")
            t:SetSize(tile, tile)
            t:SetPoint("TOPLEFT", f, "TOPLEFT", (i - 1) % 4 * tile, -math.floor((i - 1) / 4) * tile)
        end
        M.addons.Blizzard_BattlefieldMinimap = true
        M.FireEvent("ADDON_LOADED", "Blizzard_BattlefieldMinimap")
        return f
    end

    -- A quest tracker with quest lines, where it sits by default: AddicatUI's (TOPRIGHT -210,-255 of UIParent,
    -- AddicatUI/database.lua) or, with opts.stock, the stock WatchFrame. GetNumQuestWatches answers opts.watches (1).
    function M.QuestTracker(opts)
        opts = opts or {}
        local f = opts.stock and env.WatchFrame or new("Frame", "AddicatUI_QuestTrackerFrame", env.UIParent)
        local w, h = opts.w or 250, opts.h or 300
        f:SetSize(w, h)
        f:ClearAllPoints()
        f:SetPoint("TOPRIGHT", env.UIParent, "TOPRIGHT", -210, -255)
        f.__cx, f.__cy = M.screenW - 210 - w / 2, M.screenH - 255 - h / 2
        f:Show()
        M.questWatches = opts.watches or 1
        env.GetNumQuestWatches = function() return M.questWatches end
        return f
    end

    -- A font file the client cannot load (M.missingFonts[path] = true): like Script_SetFont
    -- (CSimpleFontString_Scripts.cpp), SetFont answers nil and the font string keeps the font it had.
    M.missingFonts = {}
    local setFont = IMPL.SetFont
    function IMPL.SetFont(self, path, size, flags)
        if M.missingFonts[path] then
            assert(type(path) == "string" and type(size) == "number" and size > 0, "SetFont: path and size expected")
            M.fonts[path] = true
            return nil
        end
        return setFont(self, path, size, flags)
    end

    -- Script_SetDesaturated and Script_IsDesaturated (CSimpleTexture_Scripts.cpp) work through the texture's pixel
    -- shader (nil or false: off), and CSimpleTexture::SetTexture (CSimpleRender.cpp) sets the Normal shader again
    -- whenever it loads a file other than the one it has: a texture greyed before its file comes shows in colour.
    function IMPL.SetDesaturated(self, on)
        self.__desat = (on ~= nil and on ~= false and on ~= 0) or nil
        return 1
    end
    function IMPL.IsDesaturated(self) return self.__desat and 1 or nil end
    local setTexture = IMPL.SetTexture
    function IMPL.SetTexture(self, a, ...)
        local before = self.__texture
        local ok = setTexture(self, a, ...)
        if ok and type(a) == "string" and a ~= "" and a ~= before then
            self.__desat = nil
        end
        return ok
    end

    -- EnableMouse and IsMouseEnabled keep the flag, so tests can tell a click-through frame (a frame without it never
    -- takes the mouse focus from the world frame, CSimpleTop::OnMouseDown).
    function IMPL.EnableMouse(self, on)
        self.__mouse = (on ~= nil and on ~= false and on ~= 0) or nil
    end
    function IMPL.IsMouseEnabled(self) return self.__mouse and 1 or nil end

    return M
end
