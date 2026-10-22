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

    function IMPL.SetTexture(self, a, g, b, al)
        if type(a) == "string" then
            M.textures[a] = true
            self.__texture = a
        elseif type(a) == "number" then
            self.__texture = nil
        elseif a ~= nil then
            error("SetTexture: string or numbers expected")
        end
        return 1
    end
    function IMPL.GetTexture(self) return self.__texture end
    function IMPL.SetVertexColor(self, r, g, b, a) self.__color = { num(r, "SetVertexColor"), num(g, "SetVertexColor"), num(b, "SetVertexColor"), a } end
    function IMPL.GetVertexColor(self) local c = self.__color or { 1, 1, 1, 1 } return c[1], c[2], c[3], c[4] or 1 end
    function IMPL.SetTexCoord(self, ...)
        local n = select("#", ...)
        assert(n == 4 or n == 8, "SetTexCoord: 4 or 8 numbers expected")
        for i = 1, n do num(select(i, ...), "SetTexCoord") end
        self.__tc = { ... }
    end
    function IMPL.SetDrawLayer(self, layer) assert(LAYERS[layer], "SetDrawLayer: invalid layer " .. tostring(layer)); self.__layer = layer end
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
    function IMPL.GetStringWidth(self)
        local size = self.__font and self.__font[2] or 12
        return #(self.__text or ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "") * size * 0.52
    end
    function IMPL.GetStringHeight(self) return self.__font and self.__font[2] or 12 end
    function IMPL.SetTextColor(self, r, g, b, a) self.__tcolor = { num(r, "SetTextColor"), num(g, "x"), num(b, "x"), a } end
    function IMPL.GetTextColor(self) local c = self.__tcolor or { 1, 1, 1 } return c[1], c[2], c[3], c[4] or 1 end
    function IMPL.SetJustifyH(self, j) assert(j == "LEFT" or j == "CENTER" or j == "RIGHT", "SetJustifyH: bad value " .. tostring(j)); self.__jh = j end
    function IMPL.SetJustifyV(self, j) assert(j == "TOP" or j == "MIDDLE" or j == "BOTTOM", "SetJustifyV: bad value " .. tostring(j)) end

    function IMPL.Enable(self) self.__enabled = true end
    function IMPL.Disable(self) self.__enabled = false end
    function IMPL.IsEnabled(self) return self.__enabled and 1 or nil end
    function IMPL.Click(self, button)
        if self.__enabled then fire(self, "OnClick", button or "LeftButton", false) end
    end
    function IMPL.SetChecked(self, c) self.__checked = c and true or false end
    function IMPL.GetChecked(self) return self.__checked and 1 or nil end
    function IMPL.SetFocus(self) self.__focus = true; fire(self, "OnEditFocusGained") end
    function IMPL.ClearFocus(self) self.__focus = false end
    function IMPL.HasFocus(self) return self.__focus and 1 or nil end

    function IMPL.SetMinMaxValues(self, a, b) self.__min, self.__max = num(a, "SetMinMaxValues"), num(b, "SetMinMaxValues") end
    function IMPL.GetMinMaxValues(self) return self.__min or 0, self.__max or 1 end
    function IMPL.SetValue(self, v) self.__value = num(v, "SetValue") end
    function IMPL.GetValue(self) return self.__value or 0 end

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

    function IMPL.SetOwner(self, owner, anchor) self.__owner = owner; self.__lines = {}; self.__item = nil; self.__shown = true end
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
    function IMPL.GetItem(self) if self.__item then return self.__item[1], self.__item[2] end end
    function IMPL.AddMessage(self, msg) table.insert(M.chat, { frame = self, msg = msg }) end
    function IMPL.SetMaxLetters() end

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
    env.IsShiftKeyDown = function() return M.shift and 1 or nil end
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
    env.GetCurrentBindingSet = function() return 1 end
    env.SaveBindings = function(which) M.savedBindings = M.savedBindings + 1 end
    env.GetScreenWidth = function() return 1024 end
    env.GetScreenHeight = function() return 768 end
    env.PlaySound = function(s) M.sounds[#M.sounds + 1] = s end
    env.GetCVar = function() return nil end
    env.IsAddOnLoaded = function(n) return M.addons[n] and 1 or nil end
    env.GetItemInfo = function(id)
        if type(id) == "string" then id = tonumber(id:match("item:(%d+)")) end
        local i = id and M.items[id]
        if i then return i.name, "|cffa335ee|Hitem:" .. id .. "|h[" .. i.name .. "]|h|r", 4, 60, 60, "Armor", "Plate", 1, "INVTYPE_CHEST", "Interface\\Icons\\INV_Misc_QuestionMark" end
    end
    env.GetItemIcon = function() return "Interface\\Icons\\INV_Misc_QuestionMark" end
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
    env.DressUpItemLink = function(link) M.dressedUp = link end
    -- GetMinimapShape, DragonUI*, DBM: absent unless a test sets them

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

    return M
end
