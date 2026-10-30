-- Mock of the 3.3.5a glue widget API and the glue C++ script functions, for testing the Bleakhold glue Lua with
-- the client's own Lua 5.1 (wowlua). Behaviour mirrors the decomp where the Bleakhold code depends on it:
-- Texture:SetTexture returns nil for a missing file (CSimpleTexture::SetTexture), Font:SetFont returns nil for a
-- missing font, Button:Set*Texture(path) reuses an existing state texture or creates one with SetAllPoints
-- (CSimpleButton::SetStateTexture) and Set*Texture(texture) takes that texture, CreateFrame errors on an unknown
-- template before it makes anything (Script_CreateFrame), LoginServerLogin's gate. Anchors as CScriptRegion_Scripts.cpp
-- keeps them: SetPoint without a relative region anchors to the parent, with an explicit nil to the screen; GetPoint
-- lists the points in FRAMEPOINT order and gives nil for the screen; anchoring to itself or to a region that depends
-- on this one is an error. GetLeft/GetTop/GetRect resolve the anchors (MOCK.rect) the way the layout does, with
-- scales as CLayoutFrame applies them: a region's anchor offsets and size count in its effective scale (its own
-- times its parents', CSimpleFrame::UpdateScale), and GetLeft/GetTop/GetRect answer in that scale's units.
-- CreateFrame's fifth argument is the frame's id, set before the template's OnLoad runs (CSimpleFrame::PreLoadXML).

MOCK = { collisions = {}, files = {}, log = {}, launched = {}, logins = {}, messages = {}, sounds = {} }

function MOCK.addFile(path) MOCK.files[string.lower(path)] = true end
function MOCK.hasFile(path) return path and MOCK.files[string.lower(path)] or false end

local function copy(t) local r = {} for k, v in pairs(t) do r[k] = v end return r end

-- ----------------------------------------------------------------------------------------------- objects

local Object = {}
Object.__index = Object
local allFrames = {}

local function newObject(kind, name, parent)
    local o = setmetatable({ _kind = kind, _name = name, _parent = parent, _shown = true, _points = {}, _alpha = 1,
                             _width = 0, _height = 0, _scale = 1, _scripts = {}, _regions = {}, _children = {} },
                           Object)
    if name then
        if _G[name] ~= nil and not string.find(name, "^CharacterCreateRaceButton%d+") then table.insert(MOCK.collisions, name) end
        _G[name] = o
    end
    return o
end

function Object:GetName() return self._name end
function Object:GetParent() return self._parent end
function Object:GetObjectType() return self._kind end
function Object:IsObjectType(t) return self._kind == t end
function Object:SetWidth(w) self._width = w end
function Object:SetHeight(h) self._height = h; self:_fire("OnSizeChanged", self._width, h) end
function Object:SetSize(w, h) self._width = w; self._height = h end
function Object:GetWidth() return self._width end
function Object:GetHeight() return self._height end
-- Frames only (CSimpleFrame_Scripts.cpp); a texture or font string is drawn at its frame's effective scale.
local NOT_FRAMES = { Texture = true, FontString = true, Font = true, Screen = true }
function Object:SetScale(s)
    if NOT_FRAMES[self._kind] then
        error(tostring(self._name) .. ":SetScale(): not a method of a " .. self._kind, 2)
    end
    if type(s) ~= "number" or s <= 0 then error("Usage: " .. tostring(self._name) .. ":SetScale(scale)", 2) end
    self._scale = s
end
function Object:GetScale() return self._scale or 1 end
local function effectiveScale(region)
    local scale = 1
    while region and region ~= MOCK.SCREEN do
        scale = scale * (region._scale or 1)
        region = region._parent
    end
    return scale
end
function Object:GetEffectiveScale() return effectiveScale(self) end
-- CSimpleTop: what an anchor to nil means. GetPoint reports it as nil.
MOCK.SCREEN = setmetatable({ _kind = "Screen", _points = {}, _children = {}, _regions = {}, _scripts = {} }, Object)
local FRAMEPOINTS = { "TOPLEFT", "TOP", "TOPRIGHT", "LEFT", "CENTER", "RIGHT", "BOTTOMLEFT", "BOTTOM", "BOTTOMRIGHT" }
local POINT_ORDER = {}
for i, p in ipairs(FRAMEPOINTS) do POINT_ORDER[p] = i end

local function layoutParent(self) return self._parent or MOCK.SCREEN end
local function displayName(self) return self._name or "<unnamed>" end
-- CLayoutFrame::IsResizeDependency: rel is laid out from self (through its anchors, at any depth).
local function dependsOn(rel, self, seen)
    if rel == self then return true end
    seen = seen or {}
    if seen[rel] then return false end
    seen[rel] = true
    for _, p in ipairs(rel._points or {}) do
        if p[2] and dependsOn(p[2], self, seen) then return true end
    end
    return false
end
local function relativeRegion(self, method, n, rel)
    local relative = layoutParent(self)
    if n >= 1 then
        if type(rel) == "string" then
            relative = _G[rel]
            if type(relative) ~= "table" then error(displayName(self) .. ":" .. method .. "(): Couldn't find region named '" .. rel .. "'", 3) end
        elseif type(rel) == "table" then relative = rel
        elseif rel == nil then relative = MOCK.SCREEN end
    end
    if relative == self then error(displayName(self) .. ":" .. method .. "(): trying to anchor to itself", 3) end
    if dependsOn(relative, self) then error(displayName(self) .. ":" .. method .. "(): " .. displayName(relative) .. " is dependent on this", 3) end
    return relative
end
function Object:SetPoint(point, ...)
    if type(point) ~= "string" then error("Usage: " .. displayName(self) .. ':SetPoint("point" [, region or nil] [, "relativePoint"] [, offsetX, offsetY])', 2) end
    if not POINT_ORDER[point] then error(displayName(self) .. ":SetPoint(): Unknown region point", 2) end
    local n, args = select("#", ...), { ... }
    local i = 1
    local rel = layoutParent(self)
    if n >= 1 and type(args[1]) ~= "number" then rel = relativeRegion(self, "SetPoint", n, args[1]); i = 2 end
    local relPoint = point
    if type(args[i]) == "string" then
        relPoint = args[i]
        if not POINT_ORDER[relPoint] then error(displayName(self) .. ":SetPoint(): Unknown region point", 2) end
        i = i + 1
    end
    local x, y = 0, 0
    if type(args[i]) == "number" and type(args[i + 1]) == "number" then x, y = args[i], args[i + 1] end
    for k, p in ipairs(self._points) do
        if p[1] == point then table.remove(self._points, k) break end
    end
    table.insert(self._points, { point, rel, relPoint, x, y })
    table.sort(self._points, function(a, b) return POINT_ORDER[a[1]] < POINT_ORDER[b[1]] end)
end
function Object:ClearAllPoints() self._points = {} end
function Object:GetNumPoints() return #self._points end
function Object:GetPoint(i)
    local p = self._points[i or 1]
    if p then
        local rel = p[2]
        if rel == MOCK.SCREEN then rel = nil end
        return p[1], rel, p[3], p[4], p[5]
    end
end
function Object:SetAllPoints(...)
    local rel = relativeRegion(self, "SetAllPoints", select("#", ...), ...)
    self._points = { { "TOPLEFT", rel, "TOPLEFT", 0, 0 }, { "BOTTOMRIGHT", rel, "BOTTOMRIGHT", 0, 0 } }
end
function Object:SetParent(parent)
    if type(parent) == "string" then parent = _G[parent] end
    local ancestor = parent
    while ancestor do
        if ancestor == self then error(displayName(self) .. ":SetParent(): Would create a loop parenting to " .. displayName(parent), 2) end
        ancestor = ancestor._parent
    end
    local old = self._parent
    if old then
        for k, c in ipairs(old._children) do if c == self then table.remove(old._children, k) break end end
    end
    self._parent = parent
    if parent then
        table.insert(parent._children, self)
        self._level = (parent._level or 0) + 1
    end
end

-- The rectangle the layout gives a region (left, bottom, width, height) in screen units, from its anchors and size
-- (both times its effective scale, as CFramePoint::X/Y and CLayoutFrame::Resize take them); nil when it has no
-- anchors (a top-level frame without any is taken as placed at the origin, as GlueParent fills the screen).
local H = { TOPLEFT = 0, TOP = 0.5, TOPRIGHT = 1, LEFT = 0, CENTER = 0.5, RIGHT = 1, BOTTOMLEFT = 0, BOTTOM = 0.5, BOTTOMRIGHT = 1 }
local V = { TOPLEFT = 1, TOP = 1, TOPRIGHT = 1, LEFT = 0.5, CENTER = 0.5, RIGHT = 0.5, BOTTOMLEFT = 0, BOTTOM = 0, BOTTOMRIGHT = 0 }
function MOCK.rect(region, depth)
    depth = (depth or 0) + 1
    assert(depth < 64, "anchor loop")
    if region == MOCK.SCREEN then return 0, 0, MOCK.cpp.screenWidth, MOCK.cpp.screenHeight end
    local scale = effectiveScale(region)
    if #region._points == 0 then
        if not region._parent then return 0, 0, region._width * scale, region._height * scale end
        return nil
    end
    local hs, vs = {}, {}
    for _, p in ipairs(region._points) do
        local l, b, w, h = MOCK.rect(p[2], depth)
        if not l then return nil end
        hs[H[p[1]]] = l + w * H[p[3]] + p[4] * scale
        vs[V[p[1]]] = b + h * V[p[3]] + p[5] * scale
    end
    local function solve(set, size)
        if set[0] and set[1] then return set[0], set[1] - set[0] end
        if set[0] then return set[0], size end
        if set[1] then return set[1] - size, size end
        return set[0.5] - size / 2, size
    end
    local left, width = solve(hs, region._width * scale)
    local bottom, height = solve(vs, region._height * scale)
    return left, bottom, width, height
end
-- Script_GetRect, GetLeft, ...: the rectangle in the region's own units (screen units over its effective scale).
local function ownRect(region)
    local l, b, w, h = MOCK.rect(region)
    if not l then return nil end
    local s = effectiveScale(region)
    return l / s, b / s, w / s, h / s
end
function Object:GetRect() return ownRect(self) end
function Object:GetLeft() local l = ownRect(self); return l end
function Object:GetBottom() local _, b = ownRect(self); return b end
function Object:GetRight() local l, _, w = ownRect(self); return l and l + w end
function Object:GetTop() local _, b, _, h = ownRect(self); return b and b + h end
function Object:GetCenter() local l, b, w, h = ownRect(self); if l then return l + w / 2, b + h / 2 end end
function Object:SetAlpha(a) self._alpha = a end
function Object:GetAlpha() return self._alpha end
function Object:IsShown() return self._shown and 1 or nil end
function Object:IsVisible()
    local o = self
    while o do if not o._shown then return nil end o = o._parent end
    return 1
end

local function visible(o) return o:IsVisible() ~= nil end

function Object:Show()
    if self._shown then return end
    local wasVisible = self._parent == nil or visible(self._parent)
    self._shown = true
    if wasVisible then self:_propagate("OnShow") end
end
function Object:Hide()
    if not self._shown then return end
    local wasVisible = visible(self)
    self._shown = false
    if wasVisible then self:_propagate("OnHide") end
end
function Object:_propagate(script)
    self:_fire(script)
    for _, c in ipairs(self._children) do
        if c._shown then c:_propagate(script) end
    end
end

-- scripts
function Object:SetScript(name, fn) self._scripts[name] = fn end
function Object:GetScript(name) return self._scripts[name] end
function Object:HookScript(name, fn)
    local old = self._scripts[name]
    if old then
        self._scripts[name] = function(...) old(...); fn(...) end
    else
        self._scripts[name] = fn
    end
end
function Object:_fire(name, ...)
    local fn = self._scripts[name]
    if fn then fn(self, ...) end
end

-- frames
local eventRegistry = {}
function Object:RegisterEvent(e) eventRegistry[e] = eventRegistry[e] or {}; table.insert(eventRegistry[e], self) end
function Object:UnregisterEvent(e) end
function MOCK.fireEvent(e, ...)
    for _, f in ipairs(eventRegistry[e] or {}) do f:_fire("OnEvent", e, ...) end
end
function Object:SetFrameLevel(l)
    local delta = l - (self._level or 0)
    self._level = l
    for _, c in ipairs(self._children) do c:SetFrameLevel((c._level or 0) + delta) end
end
function Object:GetFrameLevel() return self._level or 0 end
function Object:GetFrameStrata() return self._strata or "MEDIUM" end
function Object:GetChildren() return unpack(self._children) end
function Object:GetRegions() return unpack(self._regions) end
function Object:SetID(id) self._id = id end
function Object:GetID() return self._id or 0 end
function Object:SetBackdrop(b) self._backdrop = b and copy(b) or nil end
function Object:GetBackdrop() return self._backdrop end
function Object:SetBackdropColor(r, g, b, a) self._backdropColor = { r, g, b, a or 1 } end
function Object:GetBackdropColor() local c = self._backdropColor; if c then return c[1], c[2], c[3], c[4] end end
function Object:SetBackdropBorderColor(r, g, b, a) self._backdropBorderColor = { r, g, b, a or 1 } end
function Object:GetBackdropBorderColor() local c = self._backdropBorderColor; if c then return c[1], c[2], c[3], c[4] end end
function Object:SetHitRectInsets(l, r, t, b) self._hitRect = { l, r, t, b } end
function Object:EnableKeyboard() end
function Object:EnableMouse() end
function Object:Raise() end
function Object:CreateTexture(name, layer)
    local t = newObject("Texture", name, self)
    t._layer = layer or "ARTWORK"
    t._coords = { 0, 1, 0, 1 }
    table.insert(self._regions, t)
    return t
end
function Object:CreateFontString(name, layer)
    local f = newObject("FontString", name, self)
    f._layer = layer or "ARTWORK"
    table.insert(self._regions, f)
    return f
end

-- models
function Object:SetModel(m) self._model = m end
function Object:GetModel() return self._model end
function Object:ClearModel() self._model = nil end
function Object:SetSequence() end
function Object:SetCamera() end
function Object:SetFogColor() end
function Object:SetFogNear() end
function Object:SetFogFar() end
function Object:ClearFog() end
function Object:SetGlow() end
function Object:ResetLights() end
function Object:AddCharacterLight() end
function Object:AddLight() end
function Object:AddPetLight() end

-- textures
function Object:SetTexture(a, g, b, alpha)
    if type(a) == "number" then self._file = nil; self._color = { a, g, b, alpha }; return 1 end
    if a == nil then self._file = nil; return 1 end
    if not MOCK.hasFile(a) then return nil end
    self._file = a
    return 1
end
function Object:GetTexture() return self._file end
-- SetTexCoord(left, right, top, bottom) or the eight corner coordinates (ULx, ULy, LLx, LLy, URx, URy, LRx, LRy).
function Object:SetTexCoord(...)
    local a = { ... }
    if #a == 8 then self._coords = { a[1], a[7], a[2], a[8] } else self._coords = { a[1], a[2], a[3], a[4] } end
end
function Object:GetTexCoord() local c = self._coords; return c[1], c[3], c[1], c[4], c[2], c[3], c[2], c[4] end
function Object:SetVertexColor(r, g, b, a) self._vertexColor = { r, g, b, a or 1 } end
function Object:GetVertexColor() local c = self._vertexColor or { 1, 1, 1, 1 }; return c[1], c[2], c[3], c[4] end
function Object:SetGradient(o, ...) self._gradient = { o, ... } end
function Object:SetGradientAlpha(o, ...) self._gradient = { o, ... } end
function Object:SetDesaturated(d) self._desaturated = d; return 1 end
function Object:SetBlendMode(m) self._blend = m end
function Object:GetBlendMode() return self._blend or "BLEND" end
function Object:SetDrawLayer(l) self._layer = l end
function Object:GetDrawLayer() return self._layer end

-- font strings
function Object:SetFontObject(f) self._font = f end
function Object:SetFont(path, size, flags)
    if not MOCK.hasFile(path) then return nil end
    self._fontFile = path; self._fontSize = size; self._fontFlags = flags
    return 1
end
function Object:GetFont() return self._fontFile, self._fontSize, self._fontFlags end
function Object:GetFontObject() return self._font end
function Object:SetText(t)
    if self._kind == "EditBox" then
        -- CSimpleEditBox::SetText: no change, no script; Insert keeps at most the max letters.
        t = t or ""
        if self._maxLetters and self._maxLetters > 0 then t = string.sub(t, 1, self._maxLetters) end
        if t == (self._text or "") then return end
        self._text = t
        self:_fire("OnTextChanged", false)
        return
    end
    self._text = t
    if self._fontString then self._fontString._text = t end
end
function Object:GetText()
    if self._kind == "Button" or self._kind == "CheckButton" then return self._fontString and self._fontString._text end
    if self._kind == "EditBox" then return self._text or "" end
    return self._text
end
function Object:SetFormattedText(fmt, ...) self:SetText(string.format(fmt, ...)) end
function Object:GetStringWidth() return #(self._text or "") * 7 end
function Object:SetJustifyH(j) self._justifyH = j end
function Object:GetJustifyH() return self._justifyH or "CENTER" end
function Object:SetJustifyV() end
function Object:SetTextColor(r, g, b, a) self._textColor = { r, g, b, a or 1 } end
function Object:GetTextColor() local c = self._textColor or { 1, 1, 1, 1 }; return c[1], c[2], c[3], c[4] end
function Object:SetShadowColor() end
function Object:SetShadowOffset() end

-- buttons
local STATES = { Normal = "_normalTex", Pushed = "_pushedTex", Disabled = "_disabledTex" }
for state, field in pairs(STATES) do
    Object["Set" .. state .. "Texture"] = function(self, tex)
        if type(tex) == "table" then self[field] = tex; return end
        if tex == nil then self[field] = nil; return end
        if self[field] then self[field]:SetTexture(tex); return end
        if not MOCK.hasFile(tex) then return end
        local t = self:CreateTexture(nil, "ARTWORK")
        t:SetTexture(tex)
        t:SetAllPoints(self)
        self[field] = t
    end
    Object["Get" .. state .. "Texture"] = function(self) return self[field] end
end
function Object:SetHighlightTexture(tex, mode)
    if type(tex) == "table" then self._highlightTex = tex; tex:SetBlendMode(mode or "ADD"); return end
    if self._highlightTex then self._highlightTex:SetTexture(tex); self._highlightTex:SetBlendMode(mode or "ADD"); return end
    if not MOCK.hasFile(tex) then return end
    local t = self:CreateTexture(nil, "HIGHLIGHT"); t:SetTexture(tex); t:SetAllPoints(self); t:SetBlendMode(mode or "ADD")
    self._highlightTex = t
end
function Object:GetHighlightTexture() return self._highlightTex end
function Object:SetCheckedTexture(tex)
    if type(tex) == "table" then self._checkedTex = tex; return end
    if self._checkedTex then self._checkedTex:SetTexture(tex); return end
    if not MOCK.hasFile(tex) then return end
    local t = self:CreateTexture(nil, "OVERLAY"); t:SetTexture(tex); t:SetAllPoints(self); self._checkedTex = t
end
function Object:GetCheckedTexture() return self._checkedTex end
function Object:SetDisabledCheckedTexture(tex)
    if type(tex) == "table" then self._disabledCheckedTex = tex; return end
    if self._disabledCheckedTex then self._disabledCheckedTex:SetTexture(tex); return end
    if not MOCK.hasFile(tex) then return end
    local t = self:CreateTexture(nil, "OVERLAY"); t:SetTexture(tex); t:SetAllPoints(self); self._disabledCheckedTex = t
end
function Object:GetDisabledCheckedTexture() return self._disabledCheckedTex end
local function ensureFontString(self)
    if not self._fontString then self._fontString = self:CreateFontString(nil, "ARTWORK") end
    return self._fontString
end
function Object:SetNormalFontObject(f) self._normalFont = f; ensureFontString(self) end
function Object:SetHighlightFontObject(f) self._highlightFont = f end
function Object:SetDisabledFontObject(f) self._disabledFont = f end
function Object:GetNormalFontObject() return self._normalFont end
function Object:GetHighlightFontObject() return self._highlightFont end
function Object:GetDisabledFontObject() return self._disabledFont end
function Object:SetPushedTextOffset(x, y) self._pushedOffset = { x, y } end
function Object:GetFontString() return self._fontString end
function Object:GetTextWidth() return self._fontString and #(self._fontString._text or "") * 7 or 0 end
function Object:Enable() self._disabled = false end
function Object:Disable() self._disabled = true end
function Object:IsEnabled() return (not self._disabled) and 1 or nil end
function Object:Click(button)
    if self._disabled then return end
    if self._kind == "CheckButton" then self._checked = not self._checked end
    self:_fire("OnClick", button or "LeftButton")
end
function Object:SetChecked(c) self._checked = (c and c ~= 0) and true or false end
function Object:GetChecked() return self._checked and 1 or nil end

-- edit boxes
local focus
function Object:SetFocus()
    if focus == self then return end
    local old = focus
    focus = self
    if old then old:_fire("OnEditFocusLost") end
    self:_fire("OnEditFocusGained")
end
function Object:ClearFocus() if focus == self then focus = nil; self:_fire("OnEditFocusLost") end end
function Object:HasFocus() return focus == self end
function Object:SetTextInsets(...) self._insets = { ... } end
function Object:GetTextInsets() local i = self._insets or {}; return i[1] or 0, i[2] or 0, i[3] or 0, i[4] or 0 end
function Object:HighlightText() end
function Object:SetMaxLetters(n) self._maxLetters = n end
function Object:GetMaxLetters() return self._maxLetters or 0 end
function Object:SetAutoFocus(f) self._autoFocus = f and true or false end
-- Typing: the client inserts the text at the cursor (the end here) and runs OnTextChanged(userInput = true).
function MOCK.type(edit, text)
    local t = (edit._text or "") .. text
    if edit._maxLetters and edit._maxLetters > 0 then t = string.sub(t, 1, edit._maxLetters) end
    if t == (edit._text or "") then return end
    edit._text = t
    edit:_fire("OnTextChanged", true)
end
function MOCK.focus() return focus end
function MOCK.press(edit, script) edit:_fire(script) end

-- fonts
local fonts = {}
local FontObject = setmetatable({}, { __index = Object })
FontObject.__index = FontObject
function FontObject:SetFont(path, size)
    if not MOCK.hasFile(path) then return nil end
    self._fontFile = path; self._fontSize = size
    return 1
end
function FontObject:GetFont() return self._fontFile, self._fontSize end
function CreateFont(name)
    if fonts[name] then return fonts[name] end
    local f = setmetatable({ _kind = "Font", _name = name, _points = {}, _scripts = {}, _regions = {}, _children = {} }, FontObject)
    fonts[name] = f
    if _G[name] ~= nil then table.insert(MOCK.collisions, name) end
    _G[name] = f
    return f
end

-- --------------------------------------------------------------------------------------------- CreateFrame

MOCK.templates = {}
function MOCK.CreateFrame(kind, name, parent, template, id)
    if type(parent) == "string" then parent = _G[parent] end
    -- Script_CreateFrame checks every inherited node before it makes the frame.
    local builders = {}
    for t in string.gmatch(template or "", "[^ ,]+") do
        local builder = MOCK.templates[t]
        if not builder then error('CreateFrame(): Couldn\'t find inherited node "' .. t .. '"', 2) end
        builders[#builders + 1] = builder
    end
    local f = newObject(kind, name, parent)
    if tonumber(id) and tonumber(id) >= 0 then f._id = math.floor(tonumber(id)) end
    f._level = parent and (parent._level or 0) + 1 or 0
    if parent then table.insert(parent._children, f) end
    table.insert(allFrames, f)
    for _, builder in ipairs(builders) do builder(f, name) end
    return f
end
CreateFrame = function(kind, name, parent, template, id) return MOCK.CreateFrame(kind, name, parent, template, id) end

-- --------------------------------------------------------------------------------------------- C++ glue API

local cpp = { acceptedTOS = false, acceptedEULA = false, scanStatus = 0, scanOkay = false, idle = true,
              savedName = "", locale = "enUS", screenWidth = 1365.33, screenHeight = 768 }
MOCK.cpp = cpp

function GetLocale() return cpp.locale end
function GetBuildInfo() return "Version", "Release", "3.3.5", "12340", "Jun 24 2010" end
function GetScreenWidth() return cpp.screenWidth end
function GetScreenHeight() return cpp.screenHeight end
function PlaySound(s) table.insert(MOCK.sounds, s) end
function PlaySoundFile() end
function PlayGlueMusic() end
function PlayGlueAmbience() end
function StopGlueAmbience() end
function StopAllSFX() end
function SetCurrentScreen(s) cpp.screen = s end
function LaunchURL(url) table.insert(MOCK.launched, url) end
function QuitGame() cpp.quit = true end
function Screenshot() end
function message(text) table.insert(MOCK.messages, text) end
function geterrorhandler() return nil end
function GetCurrentKeyBoardFocus() return focus end
function GetSavedAccountName() return cpp.savedName end
function SetSavedAccountName(n) cpp.savedName = n end
function GetSavedAccountList() return "" end
function SetSavedAccountList() end
function GetUsesToken() return false end
function SetUsesToken() end
function GetServerName() return nil end
function IsTrialAccount() return false end
function IsStreamingTrial() return false end
function IsWindowsClient() return true end
function TOSAccepted() return cpp.acceptedTOS and 1 or nil end
function EULAAccepted() return cpp.acceptedEULA and 1 or nil end
function AcceptTOS() cpp.acceptedTOS = true end
function AcceptEULA() cpp.acceptedEULA = true end
function AcceptTerminationWithoutNotice() end
function AcceptScanning() end
function AcceptContest() end
function ShowTOSNotice() return nil end
function ShowEULANotice() return nil end
function TerminationWithoutNoticeAccepted() return 1 end
function ScanningAccepted() return 1 end
function ContestAccepted() return 1 end
-- ScanDLLGlue.cpp: start -> thread fails (BLEAKHOLD(scandll)) -> status 2 -> SCANDLL_ERROR on the next idle.
function ScanDLLStart(versionURL, dllURL)
    assert(type(versionURL) == "string" and type(dllURL) == "string", "Usage: ScanDLLStart(versionURL, dllURL)")
    if cpp.scanStatus ~= 0 then return end
    cpp.scanStatus = 1
    cpp.scanPending = true
end
function MOCK.idle()
    if cpp.scanPending then
        cpp.scanPending = false
        cpp.scanStatus = 2
        if not cpp.dropScanEvent then MOCK.fireEvent("SCANDLL_ERROR", "Scan error") end
    end
end
function ScanDLLContinueAnyway() if cpp.scanStatus == 2 or cpp.scanStatus == 3 then cpp.scanOkay = true end end
function IsScanDLLFinished() return cpp.scanOkay and 1 or nil end
-- CGlueMgr::LoginServerLogin
function DefaultServerLogin(name, password)
    assert(type(name) == "string" and type(password) == "string", "Usage: DefaultServerLogin(\"accountName\", \"password\")")
    local result
    if not cpp.scanOkay then result = "refused: scan"
    elseif not cpp.acceptedTOS then result = "refused: tos"
    elseif not cpp.acceptedEULA then result = "refused: eula"
    elseif not cpp.idle then result = "refused: busy"
    elseif name == "" then result = "dialog: LOGIN_ENTER_NAME"
    elseif password == "" then result = "dialog: LOGIN_ENTER_PASSWORD"
    else result = "logon " .. string.upper(name) end
    table.insert(MOCK.logins, result)
    if result:sub(1, 5) == "logon" then MOCK.fireEvent("OPEN_STATUS_DIALOG", "CANCEL") end
end
function StatusDialogClick() end
function CancelLogin() end

-- character creation (CharacterCreation_Scripts.cpp)
local races = {}
MOCK.races = races
function MOCK.setRaces(list) races.list = list; races.selected = 1; races.sex = 2 end
function GetAvailableRaces()
    local out = {}
    for _, r in ipairs(races.list) do out[#out + 1] = r.name; out[#out + 1] = r.file; out[#out + 1] = 1 end
    return unpack(out)
end
function GetFactionForRace(i)
    local r = races.list[i]
    if not r then return nil, nil end
    return r.faction, r.faction
end
function GetSelectedRace() return races.selected end
function SetSelectedRace(i) races.selected = i end
function GetSelectedSex() return races.sex end
function SetSelectedSex(s) races.sex = s end
function GetNameForRace() local r = races.list[races.selected]; return r.name, r.file end
local PROXY = { HighElf = "BloodElf", Eredar = "Draenei", Gnome = "Dwarf", Troll = "Orc" }
function GetCreateBackgroundModel() local f = races.list[races.selected].file; return PROXY[f] or f end
function SetCharCustomizeBackground(path) races.background = path end
function SetCharSelectBackground() end
function ResetCharCustomize() end
MOCK.created = {}
function CreateCharacter(name) table.insert(MOCK.created, name or false) end
function GetRandomName() return "Arannis" end
function PaidChange_GetName() return MOCK.paidName end
function GetAvailableClasses() return "Warrior", "WARRIOR", 1 end
function GetSelectedClass() return "Warrior", "WARRIOR", 1 end
function IsRaceClassValid() return true end
function SetCharacterCreateFacing() end
function GetHairCustomization() return "HAIR" end
function GetFacialHairCustomization() return "HAIR" end
