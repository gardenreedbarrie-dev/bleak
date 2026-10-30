-- Bleakhold: the Bleakhold Royale style kit ("Stormforged bronze"). Every Royale screen builds its plates, text,
-- numerals, titles, icons, motion and sounds here, so the look and its rules live in one place:
--
--   palette    RS.C: dark iron, bronze and parchment; storm violet only for the storm, white for the next circle,
--              ember for danger, gold for the player and rewards. Functions take a token name or a hex string.
--   pixels     RS.PxPerUnit(region) = the region's effective scale x the screen's height in pixels / 768. In this
--              engine GetEffectiveScale is only the layout scale (UI scale times frame scales, no resolution
--              factor, CSimpleFrame_Scripts.cpp), so the height comes from Bleakhold.exe's BleakholdUI_ScreenPixels
--              (the g_heightPixels the font rasteriser uses, right also in a resized window, where the client sends
--              no DISPLAY_SIZE_CHANGED with a UI scale on), else from the gxResolution CVar (cached until
--              DISPLAY_SIZE_CHANGED or CVAR_UPDATE; GetCurrentResolution only parses that CVar too). RS.Snap rounds
--              a length to whole physical pixels.
--   text       the engine rasterises a glyph at no more than 32 physical px and stretches it above that
--              (GxuFontFont.cpp), so RS.Font clamps every size to RS.MaxTextUnits; engraved labels and headings
--              (Marcellus SC, OFL, in Fonts\) are never under 12 px and use FRIZQT under 13 px, where Marcellus's
--              hinting goes soft; a font the client refuses (SetFont answers nil) falls back to FRIZQT. Sizes are
--              applied again when the screen, the UI scale or the HUD scale changes. Character names: FRIZQT only
--              (Marcellus is Latin only).
--   art        all of it is ours (Tools/BlpConvert/make_royale_hud_art.py writes Art\Royale and RoyaleArtData.lua,
--              whose metrics this file lays out from): 9-slice plates, metal numerals on one shared baseline, titles
--              baked in neutral silver and tinted at run time, icons. Interface textures have no mipmaps
--              (CSimpleRender.cpp), so numerals and icons pick the atlas drawn for the displayed size and are never
--              minified more than about 2.2 times. No Royale texture is set before its frame first shows
--              (RS.LazyTexture): a player who never queues loads none of it.
--   rotation   Texture:SetRotation replaces all four texcoords with a radius-1 square (CSimpleTexture_Scripts.cpp):
--              it drops an atlas cell and stretches on a non-square region. It is used only on the standalone square
--              textures of RS.ROTATABLE (transparent border), in square regions of visual x sqrt(2) (RS.Rotatable).
--              Animations go on textures only: FontStrings ignore scale and rotation.
--   motion     RS.Tween for one-shot entrances and exits: one parentless driver frame, shown only while a tween runs
--              (a hidden frame gets no OnUpdate, so it sleeps for free), timed by GetTime. RS.Loop for looping
--              ambient motion (AnimationGroups the engine plays at frame rate). /bh royale motion off
--              (royaleMotion) makes every tween jump to its end and keeps the loops off.
--   sound      RS.Play (stock kits by name) and RS.PlayFile (Sounds\Royale, the _quiet set while the announcer's
--              Quiet is on); /bh royale sounds off (royaleSounds) silences both. 3.3.5a cannot stop a sound, so each
--              file is exactly as long as its moment.
--   HUD scale  RS.HudScale() (/bh royale scale 0.8-1.4, royaleHudScale) on every root frame given to
--              RS.RegisterRoot.
local ADDON, ns = ...
local U, UI = ns.U, ns.UI
local DATA = ns.RoyaleArt

local type, pairs, ipairs, next, tostring, tonumber, setmetatable = type, pairs, ipairs, next, tostring, tonumber,
    setmetatable
local floor, ceil, max, min, abs, cos, sqrt, pi = math.floor, math.ceil, math.max, math.min, math.abs, math.cos,
    math.sqrt, math.pi
local strformat = string.format

local RS = {}
ns.RoyaleStyle = RS

------------------------------------------------------------------------------------------------------
-- Palette and constants
------------------------------------------------------------------------------------------------------
RS.C = {
    ironTop = "1E2127", ironBottom = "121418",                   -- plate fill (baked)
    bronzeHi = "F3DDA4", bronze = "C9A25A", bronzeLo = "7A5A2C", bronzeDeep = "3B2A14",
    parchment = "F2E8D0", ash = "BDB4A0", smoke = "8A8273",      -- primary, secondary, tertiary text
    gold = "E5C07B",                                             -- the player: own pin, kills, rewards
    storm = "A66BE0", stormLight = "D7B6FF", stormDeep = "4B2A6E",
    safe = "FFFFFF",                                             -- the next circle
    ember = "FF7A3D",                                            -- danger: the last seconds, storm damage
    blood = "E5604F",                                            -- errors, the lobby ring
    beast = "8FD14F",                                            -- the boss
    steel = "C8D0DA",                                            -- ELIMINATED
    ink = "1A120A",                                              -- text on the gold button face
    mapLabel = "F4EBD0",
    orbSpeed = "6CC6D9", orbRestore = "7FD47F", orbBerserk = "FF9D3B",
}

RS.FONT_BODY = "Fonts\\FRIZQT__.TTF"
RS.FONT_SC = "Interface\\AddOns\\Bleakhold\\Fonts\\MarcellusSC-Regular.ttf"
RS.SOUND_DIR = "Interface\\AddOns\\Bleakhold\\Sounds\\Royale\\"
-- the files of Sounds\Royale (Tools/Announcer/make_royale_sfx.py), each also as <name>_quiet
RS.SOUNDS = { "tick", "tick3", "tick2", "tick1", "kill", "wind", "canopy", "land" }

RS.MAX_TEXT_PX = 32          -- the font rasteriser's ceiling (GxuFontFont.cpp)
RS.LABEL_MIN_PX = 12         -- engraved labels never smaller
RS.SC_MIN_PX = 13            -- Marcellus SC from this size, FRIZQT below
RS.NUMERAL_L_PX = 144        -- NumeralsL (cap 288) from this displayed cap, NumeralsM (cap 144) from
RS.NUMERAL_M_PX = 72         --   this one, NumeralsS (cap 64) below: each at most about 2x minified
RS.ICON_LARGE_PX = 40        -- Icons (64-px cells) from this size, IconsSmall (32-px cells) below
RS.TITLE_MIN_CAP = 21        -- Titles (cap 64) shown smaller would be minified past 2.2x at 1080p
RS.INSET = 12                -- a plate's content inset
RS.GAP = 8
RS.HUD_SCALE_MIN, RS.HUD_SCALE_MAX = 0.8, 1.4
RS.SQRT2 = sqrt(2)
-- the standalone square art SetRotation may turn (each with a transparent border)
RS.ROTATABLE = { Notch = true, You = true, Arrow = true, EdgeTick = true }

-- A token of RS.C or a hex string -> hex.
function RS.Hex(c)
    return RS.C[c] or c
end

function RS.Rgb(c, alpha)
    local r, g, b = U.Hex(RS.C[c] or c)
    return r, g, b, alpha or 1
end

-- "|cffRRGGBB" + text + "|r" for already-safe text.
function RS.Color(c, text)
    return U.Color(RS.C[c] or c, text)
end

-- Every region the kit made, by kind, so a change of screen or scale can lay them out again (weak keys).
local function weak()
    return setmetatable({}, { __mode = "k" })
end
local made = { fonts = weak(), numerals = weak(), titles = weak(), icons = weak(), plates = weak(),
    hairlines = weak() }
RS.made = made

------------------------------------------------------------------------------------------------------
-- Pixels
------------------------------------------------------------------------------------------------------
local cachedHeight

-- The screen's (window's) height in physical pixels.
function RS.ScreenHeight()
    if BleakholdUI_ScreenPixels then
        local _, h = BleakholdUI_ScreenPixels()
        h = tonumber(h)
        if h and h > 0 then
            return h
        end
    end
    if not cachedHeight then
        local res = GetCVar and GetCVar("gxResolution")
        local h = type(res) == "string" and tonumber(res:match("^%s*%d+%s*[xX]%s*(%d+)"))
        cachedHeight = (h and h > 0) and h or 768
    end
    return cachedHeight
end

-- The frame whose scale a region uses (textures and font strings have no GetEffectiveScale of their own).
local function frameOf(region)
    if region and region.GetEffectiveScale then
        return region
    end
    return region and region.GetParent and region:GetParent() or UIParent
end

function RS.PxPerUnit(region)
    local f = frameOf(region)
    local s = f and f:GetEffectiveScale() or 1
    return s * RS.ScreenHeight() / 768
end

function RS.Snap(v, region)
    local s = RS.PxPerUnit(region)
    return floor(v * s + 0.5) / s
end

function RS.MaxTextUnits(region)
    return RS.MAX_TEXT_PX / RS.PxPerUnit(region)
end

------------------------------------------------------------------------------------------------------
-- Lazy textures: a Royale texture is set when its root frame first shows
------------------------------------------------------------------------------------------------------
-- The root of a region: the highest frame above it that is the kit's (anonymous or Bleakhold*), below the first
-- named frame that is not (UIParent, WorldFrame, Minimap, WorldMapDetailFrame, ...).
local function rootOf(region)
    local f = frameOf(region)
    while f do
        local p = f:GetParent()
        if not p then
            return f
        end
        local name = p:GetName()
        if name and not name:find("^Bleakhold") then
            return f
        end
        f = p
    end
end
RS.RootOf = rootOf

local lazy = weak()   -- root -> { loaded = bool, pending = { texture -> path } }

local function applyTexture(tex, path)
    if tex.rsWrap then
        tex:SetTexture(path, true)     -- tiled (the storm hatch): texcoords beyond 0-1 repeat
    else
        tex:SetTexture(path)
    end
    tex.rsLoaded = true
    if tex.rsAngle then
        tex:SetRotation(tex.rsAngle)   -- after the file, so the client (and the tests) see which art turns
    end
    if tex.rsDesat then
        tex:SetDesaturated(true)       -- a new file put the Normal shader back (RS.Desaturate)
    end
end

-- Greys `tex` (on) or gives its colour back. Every Royale region goes through this rather than SetDesaturated: the
-- client's SetTexture puts the Normal pixel shader back whenever it loads a new file (CSimpleTexture::SetTexture,
-- Engine/Source/Frame/CSimpleRender.cpp), and SetDesaturated works through that shader, so a region greyed before
-- its lazy file arrives, or before RS.Icon swaps its atlas, would show in full colour. The state stays on the region
-- and applyTexture puts it back after every file.
function RS.Desaturate(tex, on)
    on = on and true or false
    tex.rsDesat = on or nil
    tex:SetDesaturated(on)
end

local function flush(st)
    st.loaded = true
    for tex, path in pairs(st.pending) do
        applyTexture(tex, path)
    end
    st.pending = {}
end

local function lazyState(root)
    local st = lazy[root]
    if st then
        return st
    end
    st = { loaded = false, pending = {} }
    lazy[root] = st
    local function onShow()
        if not st.loaded or next(st.pending) then
            flush(st)
        end
    end
    -- The root's own OnShow, plus a child that sees the root become visible even if a later SetScript("OnShow")
    -- replaces the hook (the client runs a shown child's OnShow when its parent turns visible).
    root:HookScript("OnShow", onShow)
    local watcher = CreateFrame("Frame", nil, root)
    watcher:SetScript("OnShow", onShow)
    return st
end

-- Sets `path` on `tex` now if its root has shown (or is visible), else when it first shows; `wrap` tiles it.
-- SetTexture keeps a texture's texcoords, vertex colour and blend mode, so those can be set before; its rotation and
-- desaturation are put back after the file (RS.Desaturate).
function RS.LazyTexture(tex, path, wrap)
    tex.rsPath = path
    if wrap ~= nil then
        tex.rsWrap = wrap and true or nil
    end
    local root = rootOf(tex)
    if not root then
        applyTexture(tex, path)
        return
    end
    local st = lazyState(root)
    if st.loaded or root:IsVisible() then
        st.loaded = true
        st.pending[tex] = nil
        applyTexture(tex, path)
    else
        tex.rsLoaded = nil
        st.pending[tex] = path
    end
end

------------------------------------------------------------------------------------------------------
-- Text
------------------------------------------------------------------------------------------------------
-- face: "sc" (Marcellus SC) or "body" (FRIZQT); min: the smallest size in physical px; sc faces fall back to FRIZQT
-- under RS.SC_MIN_PX.
RS.ROLES = {
    label = { face = "sc", flags = "", min = RS.LABEL_MIN_PX, shadow = { 1, -1, 0.9 }, color = "ash" },
    heading = { face = "sc", flags = "OUTLINE", min = RS.LABEL_MIN_PX, shadow = { 0, -1, 0.9 }, color = "parchment" },
    value = { face = "body", flags = "OUTLINE", shadow = { 1, -1, 0.5 }, color = "parchment" },
    body = { face = "body", flags = "", shadow = { 1, -1, 0.85 }, color = "parchment" },
    map = { face = "body", flags = "OUTLINE", shadow = { 1, -1, 0.5 }, color = "mapLabel" },
}

-- Sets the role's face on `fs` at `size` units, clamped to the rasteriser's 32 px (and raised to 12 px for labels).
-- Returns the size used, in units.
function RS.Font(fs, role, size)
    local r = RS.ROLES[role] or RS.ROLES.body
    local ppu = RS.PxPerUnit(fs)
    local units = min(size or 12, RS.MAX_TEXT_PX / ppu)
    local path = RS.FONT_BODY
    if r.face == "sc" then
        units = max(units, r.min / ppu)
        if units * ppu >= RS.SC_MIN_PX - 1e-6 then
            path = RS.FONT_SC
        end
    end
    fs.rsRole, fs.rsSize, fs.rsUnits = role, size, units
    if not fs:SetFont(path, units, r.flags) and path ~= RS.FONT_BODY then
        fs:SetFont(RS.FONT_BODY, units, r.flags)
    end
    fs:SetShadowOffset(r.shadow[1], r.shadow[2])
    fs:SetShadowColor(0, 0, 0, r.shadow[3])
    made.fonts[fs] = true
    return units
end

-- The one constructor for Royale FontStrings: role (label, heading, value, body, map), size in units, colour (token
-- or hex; the role's colour by default), justify (LEFT by default), layer (OVERLAY by default).
function RS.Text(parent, role, size, color, justify, layer)
    local fs = parent:CreateFontString(nil, layer or "OVERLAY")
    RS.Font(fs, role, size)
    local r = RS.ROLES[role] or RS.ROLES.body
    fs:SetTextColor(RS.Rgb(color or r.color))
    fs:SetJustifyH(justify or "LEFT")
    return fs
end

------------------------------------------------------------------------------------------------------
-- Plates (9-slice), hairlines, shine
------------------------------------------------------------------------------------------------------
local SLICES = { "tl", "t", "tr", "l", "c", "r", "bl", "b", "br" }

local Plate = {}
Plate.__index = Plate

function Plate:Layout()
    local c = RS.Snap(self.corner, self.frame)
    for _, k in ipairs({ "tl", "tr", "bl", "br" }) do
        self.pieces[k]:SetSize(c, c)
    end
end

-- c: a token, a hex string or { r, g, b }.
function Plate:SetColor(c, alpha)
    local r, g, b, a
    if type(c) == "table" then
        r, g, b, a = c[1], c[2], c[3], alpha or c[4] or 1
    else
        r, g, b, a = RS.Rgb(c or "safe", alpha)
    end
    for _, t in pairs(self.pieces) do
        t:SetVertexColor(r, g, b, a)
    end
end

function Plate:SetAlpha(a)
    for _, t in pairs(self.pieces) do
        t:SetAlpha(a)
    end
end

function Plate:SetDesaturated(on)
    for _, t in pairs(self.pieces) do
        RS.Desaturate(t, on)
    end
end

function Plate:Show()
    for _, t in pairs(self.pieces) do
        t:Show()
    end
end

function Plate:Hide()
    for _, t in pairs(self.pieces) do
        t:Hide()
    end
end

-- Nine textures of a 9-slice art piece over `frame` (the BleakholdDialog.lua slicing). kind: Plate (corners at 16
-- units), PlateTab, Button, ButtonGlow (8), LabelHalo (6); opts.layer (BACKGROUND), opts.blend, opts.corner (units).
-- The frame is the art's whole extent: each piece's soft drop shadow lies inside it, the visible rim starts
-- edge texels in. Returns a plate: .pieces, .fillInset (units from the frame's edge to the iron fill inside the rim
-- and the corner chamfer), :SetColor(token, alpha) to tint it (e.g. stormDeep for the storm tab), :SetAlpha.
-- The frame must be at least two corners wide and tall.
function RS.Plate(frame, kind, opts)
    kind = kind or "Plate"
    opts = opts or {}
    local sl = DATA.slices[kind]
    assert(sl, "RS.Plate: unknown plate " .. tostring(kind))
    local p = setmetatable({ frame = frame, kind = kind, pieces = {}, corner = opts.corner or sl.cornerUnits }, Plate)
    local mx, my = sl.margin / sl.w, sl.margin / sl.h
    local us, vs = { 0, mx, 1 - mx, 1 }, { 0, my, 1 - my, 1 }
    for row = 1, 3 do
        for col = 1, 3 do
            local t = frame:CreateTexture(nil, opts.layer or "BACKGROUND")
            t:SetTexCoord(us[col], us[col + 1], vs[row], vs[row + 1])
            if opts.blend then
                t:SetBlendMode(opts.blend)
            end
            RS.LazyTexture(t, DATA.files[kind])
            t.rsArt = kind
            p.pieces[SLICES[(row - 1) * 3 + col]] = t
        end
    end
    local q = p.pieces
    q.tl:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, 0)
    q.tr:SetPoint("TOPRIGHT", frame, "TOPRIGHT", 0, 0)
    q.bl:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 0, 0)
    q.br:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 0, 0)
    q.t:SetPoint("TOPLEFT", q.tl, "TOPRIGHT", 0, 0)
    q.t:SetPoint("BOTTOMRIGHT", q.tr, "BOTTOMLEFT", 0, 0)
    q.b:SetPoint("TOPLEFT", q.bl, "TOPRIGHT", 0, 0)
    q.b:SetPoint("BOTTOMRIGHT", q.br, "BOTTOMLEFT", 0, 0)
    q.l:SetPoint("TOPLEFT", q.tl, "BOTTOMLEFT", 0, 0)
    q.l:SetPoint("BOTTOMRIGHT", q.bl, "TOPRIGHT", 0, 0)
    q.r:SetPoint("TOPLEFT", q.tr, "BOTTOMLEFT", 0, 0)
    q.r:SetPoint("BOTTOMRIGHT", q.br, "TOPRIGHT", 0, 0)
    q.c:SetPoint("TOPLEFT", q.tl, "BOTTOMRIGHT", 0, 0)
    q.c:SetPoint("BOTTOMRIGHT", q.br, "TOPLEFT", 0, 0)
    p.edgeInset = sl.edge * p.corner / sl.margin
    p.fillInset = (sl.edge + sl.rim + sl.chamfer) * p.corner / sl.margin
    p:Layout()
    made.plates[p] = true
    return p
end

-- A line one physical pixel thick (bronze hairline separators), `length` units long.
function RS.Hairline(parent, length, color, vertical, layer, alpha)
    local t = parent:CreateTexture(nil, layer or "BORDER")
    t:SetTexture(UI.WHITE)
    t:SetVertexColor(RS.Rgb(color or "bronzeLo", alpha))
    t.rsLength, t.rsVertical = length, vertical and true or false
    local px = 1 / RS.PxPerUnit(t)
    if vertical then
        t:SetSize(px, length)
    else
        t:SetSize(length, px)
    end
    made.hairlines[t] = true
    return t
end

-- The shine streak of a plate: ShineStrip (ADD) over the plate's iron fill, between its rim and corners, showing a
-- clear part of the strip until RS.Sweep slides its texcoord window across (3.3.5 clips nothing outside a
-- ScrollFrame, so the streak never moves; only its texcoords do, and nothing is drawn outside the plate). The window
-- is half the strip, so the streak crosses about a third of the plate at a time; beyond the strip's ends the clamped
-- edge texels are clear. `alpha` 0.6.
RS.SHINE_FROM, RS.SHINE_TO = { 0.6, 1.1, 0, 1 }, { -0.1, 0.4, 0, 1 }

function RS.Shine(p, alpha)
    local f = p.frame
    local t = f:CreateTexture(nil, "BORDER")
    t:SetBlendMode("ADD")
    t:SetPoint("TOPLEFT", f, "TOPLEFT", p.fillInset, -p.fillInset)
    t:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -p.fillInset, p.fillInset)
    t:SetTexCoord(RS.SHINE_TO[1], RS.SHINE_TO[2], RS.SHINE_TO[3], RS.SHINE_TO[4])
    t:SetAlpha(alpha or 0.6)
    RS.LazyTexture(t, DATA.files.ShineStrip)
    t.rsArt = "ShineStrip"
    p.shine = t
    return t
end

-- One sweep, left to right, after `delay` (0.1 s) over `duration` (0.6 s).
function RS.Sweep(shine, delay, duration)
    return RS.Tween(shine, "texcoord", RS.SHINE_FROM, RS.SHINE_TO, duration or 0.6, "inOutSine",
        { delay = delay or 0.1 })
end

------------------------------------------------------------------------------------------------------
-- Buttons
------------------------------------------------------------------------------------------------------
-- gold: bronze face, dark engraved text; iron: plate face, parchment text; ghost: a soft dark pill, bronze text. The
-- glow (ButtonGlow, ADD) is tinted warm; a pressed face is darkened a little under it, so the press reads as pushed.
RS.BUTTONS = {
    gold = { face = "Button", text = "ink", shadow = { 0, -1, 1, 0.94, 0.78, 0.35 } },
    iron = { face = "PlateTab", text = "parchment", shadow = { 1, -1, 0, 0, 0, 0.85 } },
    ghost = { face = "LabelHalo", faceAlpha = 0.75, text = "bronzeHi", shadow = { 1, -1, 0, 0, 0, 0.85 } },
}
RS.BUTTON_GLOW = { hover = 0.35, press = 0.6, color = "bronzeHi", pressedFace = 0.8 }

local function buttonFace(b, kind)
    b.faces = b.faces or {}
    local p = b.faces[kind]
    if not p then
        p = RS.Plate(b, kind)
        b.faces[kind] = p
    end
    return p
end

local function applyButton(b)
    local st = RS.BUTTONS[b.style] or RS.BUTTONS.iron
    for kind, p in pairs(b.faces) do
        if kind ~= st.face then
            p:Hide()
        end
    end
    local face = buttonFace(b, st.face)
    face:Show()
    face:SetDesaturated(not b.enabled)
    face:SetAlpha((st.faceAlpha or 1) * (b.enabled and 1 or 0.55))
    local shade = (b.pressed and b.enabled) and RS.BUTTON_GLOW.pressedFace or 1
    face:SetColor({ shade, shade, shade })
    local glow = not b.enabled and 0 or (b.pressed and RS.BUTTON_GLOW.press) or (b.hovered and RS.BUTTON_GLOW.hover)
        or 0
    b.glow:SetAlpha(glow)
    local s = st.shadow
    b.label:SetTextColor(RS.Rgb(b.enabled and st.text or "smoke"))
    b.label:SetShadowOffset(s[1], s[2])
    b.label:SetShadowColor(s[3], s[4], s[5], s[6])
    if b.icon then
        RS.Desaturate(b.icon, not b.enabled)
    end
    local dy = (b.pressed and b.enabled) and -1 or 0
    if b.dy ~= dy then
        b.dy = dy
        b.label:ClearAllPoints()
        b.label:SetPoint("LEFT", b, "LEFT", b.iconRoom or 6, dy)
        b.label:SetPoint("RIGHT", b, "RIGHT", -6, dy)
        if b.icon then
            b.icon:ClearAllPoints()
            if b.label:GetText() and b.label:GetText() ~= "" then
                b.icon:SetPoint("LEFT", b, "LEFT", 6, dy)
            else
                b.icon:SetPoint("CENTER", b, "CENTER", 0, dy)
            end
        end
    end
end

-- A Royale button (style gold, iron or ghost) with UI.Button's API, so callers stay as they are: b:SetLabel,
-- b:SetStyle, b:SetActive, b.tooltip (a function returning UI.ShowTooltip lines), b:SetIcon(name, size).
-- Hover lights the glow at 0.35, a press at 0.6 and moves the label one unit down.
function RS.Button(parent, w, h, label, style, size)
    local b = CreateFrame("Button", nil, parent)
    b:SetSize(w, h)
    b.style = RS.BUTTONS[style] and style or "iron"
    b.enabled = true
    b.faces = {}
    buttonFace(b, RS.BUTTONS[b.style].face)
    b.glow = RS.Plate(b, "ButtonGlow", { layer = "ARTWORK", blend = "ADD" })
    b.glow:SetColor(RS.BUTTON_GLOW.color)
    b.label = RS.Text(b, "body", size or 13, nil, "CENTER")
    b.label:SetText(label or "")
    b:RegisterForClicks("LeftButtonUp")
    b:SetScript("OnEnter", function(self)
        self.hovered = true
        applyButton(self)
        if self.tooltip then
            UI.ShowTooltip(self, self.tooltip())
        end
    end)
    b:SetScript("OnLeave", function(self)
        self.hovered, self.pressed = false, false
        applyButton(self)
        if self.tooltip and GameTooltip then
            GameTooltip:Hide()
        end
    end)
    b:SetScript("OnMouseDown", function(self)
        self.pressed = true
        applyButton(self)
    end)
    b:SetScript("OnMouseUp", function(self)
        self.pressed = false
        applyButton(self)
    end)
    function b:SetLabel(text)
        self.label:SetText(text or "")
        self.dy = nil
        applyButton(self)
    end
    function b:SetStyle(st)
        self.style = RS.BUTTONS[st] and st or "iron"
        applyButton(self)
    end
    function b:SetActive(on)
        self.enabled = on and true or false
        if on then
            self:Enable()
        else
            self:Disable()
            self.pressed = false
        end
        applyButton(self)
    end
    function b:SetIcon(name, iconSize)
        iconSize = iconSize or min(h - 8, 16)
        if not self.icon then
            self.icon = RS.Icon(self, name, iconSize, "OVERLAY")
        else
            self.icon:SetIcon(name)
            self.icon:SetIconSize(iconSize)
        end
        self.iconRoom = (self.label:GetText() or "") ~= "" and (iconSize + 10) or 6
        self.dy = nil
        applyButton(self)
    end
    applyButton(b)
    return b
end

------------------------------------------------------------------------------------------------------
-- Icons, single art, rotatables
------------------------------------------------------------------------------------------------------
local function applyIcon(t)
    local cells = DATA.icons.cells
    local cell = cells[t.rsIcon] or cells.warning
    local large = t.rsSize * RS.PxPerUnit(t) >= RS.ICON_LARGE_PX
    t:SetTexCoord(cell[1], cell[2], cell[3], cell[4])
    t.rsArt = large and "Icons" or "IconsSmall"
    if t.rsPath ~= (large and DATA.icons.file or DATA.icons.small) then
        RS.LazyTexture(t, large and DATA.icons.file or DATA.icons.small)
    end
end

local function iconSetIcon(t, name)
    t.rsIcon = name
    applyIcon(t)
end

local function iconSetSize(t, size)
    t.rsSize = size
    t:SetSize(size, size)
    applyIcon(t)
end

-- An icon of the atlas (names in RoyaleArtData.lua icons.cells), `size` units square: the Icons cell when it shows
-- at 40 physical px or more, else the IconsSmall cell drawn for small sizes. t:SetIcon(name), t:SetIconSize(size).
function RS.Icon(parent, name, size, layer)
    local t = parent:CreateTexture(nil, layer or "ARTWORK")
    t.rsIcon, t.rsSize = name, size
    t.SetIcon, t.SetIconSize = iconSetIcon, iconSetSize
    t:SetSize(size, size)
    applyIcon(t)
    made.icons[t] = true
    return t
end

-- A texture of one Art\Royale file (RoyaleArtData.lua files), optionally a cell { u0, u1, v0, v1 } of it, or tiled
-- (`wrap`, the storm hatch).
function RS.Art(parent, name, w, h, layer, cell, wrap)
    local path = DATA.files[name]
    assert(path, "RS.Art: unknown art " .. tostring(name))
    local t = parent:CreateTexture(nil, layer or "ARTWORK")
    if w then
        t:SetSize(w, h or w)
    end
    if cell then
        t:SetTexCoord(cell[1], cell[2], cell[3], cell[4])
    end
    RS.LazyTexture(t, path, wrap)
    t.rsArt = name
    return t
end

local function rotatableSetAngle(t, a)
    t.rsAngle = a
    if t.rsLoaded then
        t:SetRotation(a)
    end
end

-- One of RS.ROTATABLE, turned with t:SetAngle(radians, counter-clockwise like SetRotation), shown `visual` units big
-- in a square region of visual x sqrt(2) (SetRotation shows the whole texture at 1/sqrt(2) of the region).
function RS.Rotatable(parent, name, visual, layer)
    assert(RS.ROTATABLE[name], "RS.Rotatable: " .. tostring(name) .. " is not rotatable art")
    local t = parent:CreateTexture(nil, layer or "ARTWORK")
    local side = visual * RS.SQRT2
    t:SetSize(side, side)
    t.rsArt, t.rsVisual = name, visual
    t.SetAngle = rotatableSetAngle
    RS.LazyTexture(t, DATA.rotatable[name])
    t:SetAngle(0)
    return t
end

------------------------------------------------------------------------------------------------------
-- Numerals: digit strings of the baked metal atlases, on the shared baseline
------------------------------------------------------------------------------------------------------
-- The atlas for a cap of `px` displayed pixels that has every character of `text` (only NumeralsS has # and /).
local function numeralAtlas(px, text)
    local order
    if px >= RS.NUMERAL_L_PX then
        order = { "NumeralsL", "NumeralsM", "NumeralsS" }
    elseif px >= RS.NUMERAL_M_PX then
        order = { "NumeralsM", "NumeralsS" }
    else
        order = { "NumeralsS" }
    end
    for _, name in ipairs(order) do
        local glyphs = DATA.atlases[name].glyphs
        local all = true
        for i = 1, #text do
            if not glyphs[text:sub(i, i)] then
                all = false
                break
            end
        end
        if all then
            return name
        end
    end
    return "NumeralsS"
end
RS.NumeralAtlas = numeralAtlas

-- Lays out a layer's string: the layer frame is the ink box plus the dark stroke on every side, its vertical middle
-- the cap's middle; each glyph's quad hangs from the shared baseline as RoyaleArtData.lua describes.
local function layoutLayer(f)
    local n = f.owner
    local text = f.text or ""
    local cap = f.cap or n.cap
    f.atlas = numeralAtlas(cap * RS.PxPerUnit(n), text)
    local at = DATA.atlases[f.atlas]
    local c = cap * (f.rsZoom or 1)
    local k = c / at.cap
    local qw, qh, top, stroke = at.cellW * k, at.cellH * k, at.baseline * k, (at.stroke or 0) * k
    local pens, glyphs, pen, inkL, inkR = {}, {}, 0, nil, nil
    for i = 1, #text do
        local g = at.glyphs[text:sub(i, i)]
        if g then
            glyphs[#glyphs + 1], pens[#pens + 1] = g, pen
            inkL = inkL or (pen + g.inkL * c)
            inkR = pen + g.inkR * c
            pen = pen + g.advance * c
        end
    end
    local left = (inkL or 0) - stroke
    local width = inkR and (inkR - inkL + 2 * stroke) or 0
    f:SetSize(max(width, 0.01), c + 2 * stroke)
    local path = f.isGlow and at.glow or at.file
    for i, g in ipairs(glyphs) do
        local t = f.texs[i]
        if not t then
            t = f:CreateTexture(nil, "ARTWORK")
            if f.isGlow then
                t:SetBlendMode("ADD")
            end
            f.texs[i] = t
        end
        t:ClearAllPoints()
        t:SetPoint("TOPLEFT", f, "BOTTOMLEFT", pens[i] - g.ox * c - left, top + stroke)
        t:SetSize(qw, qh)
        t:SetTexCoord(g.u0, g.u1, g.v0, g.v1)
        t:SetVertexColor(RS.Rgb(f.isGlow and n.glowColor or n.tint, f.isGlow and 1 or n.tintAlpha))
        if t.rsPath ~= path then
            RS.LazyTexture(t, path)
        end
        t.rsArt = f.isGlow and (f.atlas .. "Glow") or f.atlas
        t:Show()
    end
    for i = #glyphs + 1, #f.texs do
        f.texs[i]:Hide()
    end
    return width, c + 2 * stroke
end

local function layerSetZoom(f, z)
    f.rsZoom = z
    layoutLayer(f)
end

local Numeral = {}

local function newLayer(n, isGlow, level)
    local f = CreateFrame("Frame", nil, n)
    f.owner, f.isGlow, f.texs, f.text, f.rsZoom = n, isGlow, {}, "", 1
    f.SetZoom = layerSetZoom
    f:SetFrameLevel(n:GetFrameLevel() + level)
    f:SetPoint(n.justify, n, n.justify, 0, 0)
    return f
end

-- The cur layer's value at the numeral's cap; the frame takes the cur string's size at zoom 1.
function Numeral.Relayout(n)
    local zoom = n.cur.rsZoom
    n.cur.cap, n.glow.cap = n.cap, n.cap
    n.cur.rsZoom = 1
    local w, h = layoutLayer(n.cur)
    n:SetSize(max(w, 0.01), h)
    n.cur.rsZoom = zoom
    if zoom ~= 1 then
        layoutLayer(n.cur)
    end
    n.glow.rsZoom = zoom
    layoutLayer(n.glow)
    n.atlas = n.cur.atlas
    if n.old:IsShown() and n.old.text ~= "" then
        layoutLayer(n.old)
    end
end

function Numeral.SetValue(n, v)
    local s = v == nil and "" or tostring(v)
    n.value = s
    n.cur.text, n.glow.text = s, s
    n:Relayout()
end

function Numeral.GetValue(n)
    return n.value
end

-- The current digits move to the old layer (keeping their cap, zoom and place) for a cross-fade, and `v` becomes
-- the current value. Tween n.old (alpha, zoom) and n.cur (offset, alpha, zoom) from there.
function Numeral.Swap(n, v)
    local old = n.old
    RS.Stop(old)
    old.text, old.cap, old.rsZoom = n.cur.text, n.cur.cap, n.cur.rsZoom
    old:ClearAllPoints()
    old:SetPoint(n.justify, n, n.justify, 0, 0)
    old:SetAlpha(n.cur:GetAlpha())
    old:Show()
    layoutLayer(old)
    n:SetValue(v)
end

function Numeral.ClearOld(n)
    RS.Stop(n.old)
    n.old.text = ""
    n.old:Hide()
end

function Numeral.SetCap(n, cap)
    n.cap = cap
    n:Relayout()
end

function Numeral.SetZoom(n, z)
    n.cur.rsZoom, n.glow.rsZoom = z, z
    n.rsZoom = z
    layoutLayer(n.cur)
    layoutLayer(n.glow)
end

function Numeral.SetGlowColor(n, c)
    n.glowColor = c
    for _, t in ipairs(n.glow.texs) do
        t:SetVertexColor(RS.Rgb(c))
    end
end

-- The glow behind the digits (a halo, the default) or over them (ADD on the metal: the digits flare, e.g. ember for the
-- last seconds).
function Numeral.SetGlowOver(n, over)
    n.glowOver = over and true or false
    n.glow:SetFrameLevel(n:GetFrameLevel() + (n.glowOver and 4 or 1))
end

-- A multiply tint on the metal (white keeps the baked gold).
function Numeral.SetTint(n, c, alpha)
    n.tint, n.tintAlpha = c or "safe", alpha or 1
    for _, layer in ipairs({ n.cur, n.old }) do
        for _, t in ipairs(layer.texs) do
            t:SetVertexColor(RS.Rgb(n.tint, n.tintAlpha))
        end
    end
end

-- A number in the baked metal numerals: a frame the size of the string (ink plus stroke; its vertical middle is the
-- cap's middle), so anchoring its CENTER centres the number and its RIGHT right-aligns it. The atlas follows the
-- displayed cap (NumeralsL from 144 px, NumeralsM from 72 px, else NumeralsS). opts: cap (units, 34), justify
-- (CENTER, LEFT or RIGHT: the point the digit layers hang from, so a changing width keeps that side), value,
-- glowColor (gold), glowOver (false). Layers: n.cur (the digits), n.old (the outgoing digits of n:Swap), n.glow (an
-- ADD glow of the cur digits, behind them or over them, alpha 0 until tweened). n:SetValue(v), n:Swap(v),
-- n:SetCap(units), n:SetZoom(f), n:SetGlowColor(c), n:SetGlowOver(on), n:SetTint(c).
function RS.Numeral(parent, opts)
    opts = opts or {}
    local n = CreateFrame("Frame", nil, parent)
    for k, fn in pairs(Numeral) do
        n[k] = fn
    end
    n.cap = opts.cap or 34
    n.justify = (opts.justify == "LEFT" or opts.justify == "RIGHT") and opts.justify or "CENTER"
    n.glowColor = opts.glowColor or "gold"
    n.tint, n.tintAlpha, n.rsZoom = "safe", 1, 1
    n.value = ""
    n.glow = newLayer(n, true, 1)
    n.old = newLayer(n, false, 2)
    n.cur = newLayer(n, false, 3)
    n.glow:SetAlpha(0)
    n:SetGlowOver(opts.glowOver)
    n.old:Hide()
    made.numerals[n] = true
    n:SetValue(opts.value)
    return n
end

------------------------------------------------------------------------------------------------------
-- Titles and DROP!
------------------------------------------------------------------------------------------------------
local function layoutTitle(f)
    local t = DATA.titles[f.title]
    assert(t, "RS.Title: unknown title " .. tostring(f.title))
    local at = DATA.atlases.Titles
    local s = at.stroke / at.cap
    local c = f.cap * (f.rsZoom or 1)
    f:SetSize((t.inkW + 2 * s) * f.cap, (1 + 2 * s) * f.cap)
    for _, tex in ipairs({ f.tex, f.glow }) do
        tex:SetSize(t.w * c, t.h * c)
        tex:SetTexCoord(t.u0, t.u1, t.v0, t.v1)
    end
end

local function titleSetCap(f, cap)
    if not cap or cap < RS.TITLE_MIN_CAP then
        error(strformat("RS.Title: cap %s is under %d units (Titles would be minified past 2.2x)", tostring(cap),
            RS.TITLE_MIN_CAP), 2)
    end
    f.cap = cap
    layoutTitle(f)
end

local function titleSetTitle(f, name)
    f.title = name
    layoutTitle(f)
end

local function titleSetZoom(f, z)
    f.rsZoom = z
    layoutTitle(f)
end

local function titleSetColor(f, c, alpha)
    f.tex:SetVertexColor(RS.Rgb(c or "parchment", alpha))
end

local function titleSetGlowColor(f, c)
    f.glow:SetVertexColor(RS.Rgb(c or "gold"))
end

-- A fixed title of the Titles atlas (names in RoyaleArtData.lua titles), `cap` units (21 or more), tinted `color`.
-- A frame the size of the ink box plus stroke, the cap's middle at its middle. f.tex the title, f.glow its ADD glow
-- (alpha 0). f:SetTitle(name), f:SetCap(units), f:SetZoom(f), f:SetColor(c), f:SetGlowColor(c).
function RS.Title(parent, name, cap, color)
    local f = CreateFrame("Frame", nil, parent)
    f.title, f.rsZoom = name, 1
    f.glow = f:CreateTexture(nil, "BORDER")
    f.glow:SetBlendMode("ADD")
    f.glow:SetPoint("CENTER", f, "CENTER", 0, 0)
    f.glow:SetAlpha(0)
    f.tex = f:CreateTexture(nil, "ARTWORK")
    f.tex:SetPoint("CENTER", f, "CENTER", 0, 0)
    f.SetTitle, f.SetCap, f.SetZoom = titleSetTitle, titleSetCap, titleSetZoom
    f.SetColor, f.SetGlowColor = titleSetColor, titleSetGlowColor
    RS.LazyTexture(f.tex, DATA.atlases.Titles.file)
    RS.LazyTexture(f.glow, DATA.atlases.Titles.glow)
    f.tex.rsArt, f.glow.rsArt = "Titles", "TitlesGlow"
    titleSetCap(f, cap)
    f:SetColor(color)
    f:SetGlowColor(color)
    made.titles[f] = true
    return f
end

local function layoutDropWord(f)
    local at = DATA.atlases.DropWord
    local g = at.glyphs["DROP!"]
    local s = at.stroke / at.cap
    local c = f.cap * (f.rsZoom or 1)
    f:SetSize((g.inkR - g.inkL + 2 * s) * f.cap, (1 + 2 * s) * f.cap)
    local pen = -(g.inkL + g.inkR) / 2 * c
    for _, tex in ipairs({ f.tex, f.glow }) do
        tex:ClearAllPoints()
        tex:SetPoint("TOPLEFT", f, "CENTER", pen - g.ox * c, -c / 2 + at.baseline / at.cap * c)
        tex:SetSize(at.cellW / at.cap * c, at.cellH / at.cap * c)
        tex:SetTexCoord(g.u0, g.u1, g.v0, g.v1)
    end
end

local function dropSetCap(f, cap)
    f.cap = cap
    layoutDropWord(f)
end

local function dropSetZoom(f, z)
    f.rsZoom = z
    layoutDropWord(f)
end

-- DROP! in the gold metal, `cap` units (96): a frame the size of the ink box plus stroke, centred on the word.
-- f.tex, f.glow (ADD, alpha 0, tinted gold); f:SetCap(units), f:SetZoom(f), f:SetGlowColor(c).
function RS.DropWord(parent, cap)
    local f = CreateFrame("Frame", nil, parent)
    f.cap, f.rsZoom = cap or 96, 1
    f.glow = f:CreateTexture(nil, "BORDER")
    f.glow:SetBlendMode("ADD")
    f.glow:SetAlpha(0)
    f.tex = f:CreateTexture(nil, "ARTWORK")
    f.SetCap, f.SetZoom, f.SetGlowColor = dropSetCap, dropSetZoom, titleSetGlowColor
    RS.LazyTexture(f.tex, DATA.atlases.DropWord.file)
    RS.LazyTexture(f.glow, DATA.atlases.DropWord.glow)
    f.tex.rsArt, f.glow.rsArt = "DropWord", "DropWordGlow"
    f:SetGlowColor("gold")
    layoutDropWord(f)
    return f
end

------------------------------------------------------------------------------------------------------
-- Motion: RS.Tween (one-shot) and RS.Loop (AnimationGroups)
------------------------------------------------------------------------------------------------------
RS.EASE = {
    linear = function(t) return t end,
    outCubic = function(t) local u = 1 - t return 1 - u * u * u end,
    inCubic = function(t) return t * t * t end,
    inOutSine = function(t) return 0.5 - 0.5 * cos(pi * t) end,
    outBack = function(t) local s, u = 1.7, t - 1 return 1 + (s + 1) * u * u * u + s * u * u end,
}

function RS.Motion()
    return ns.Option("royaleMotion", true) ~= false
end

-- "offset" tweens move a region from where its owner anchored it (its rest): the anchors as they were when the
-- first offset tween started, kept while the region is where the last tween left it. When the owner anchors it
-- somewhere else, the next tween starts from there.
local anchors = weak()

local function restOf(r)
    local p, rel, rp, x, y = r:GetPoint(1)
    if not p then
        return nil
    end
    local st = anchors[r]
    if st and st.points[1] then
        local q = st.points[1]
        if q[1] == p and q[2] == rel and q[3] == rp and #st.points == r:GetNumPoints()
            and abs(q[4] + st.dx - (x or 0)) < 0.001 and abs(q[5] + st.dy - (y or 0)) < 0.001 then
            return st
        end
    end
    st = { points = {}, dx = 0, dy = 0 }
    for i = 1, r:GetNumPoints() do
        local a, b, c, d, e = r:GetPoint(i)
        st.points[i] = { a, b, c, d or 0, e or 0 }
    end
    anchors[r] = st
    return st
end

local function setOffset(r, st, dx, dy)
    r:ClearAllPoints()
    for _, q in ipairs(st.points) do
        r:SetPoint(q[1], q[2], q[3], q[4] + dx, q[5] + dy)
    end
    st.dx, st.dy = dx, dy
end

local function clamp01(v)
    return v < 0 and 0 or (v > 1 and 1 or v)
end

local KINDS = {
    alpha = {
        get = function(r) return r:GetAlpha() end,
        set = function(r, v) r:SetAlpha(clamp01(v)) end,
    },
    size = {
        get = function(r) return { r:GetWidth(), r:GetHeight() } end,
        set = function(r, v) r:SetSize(max(v[1], 0.01), max(v[2], 0.01)) end,
    },
    offset = {
        start = function(tw) tw.anchor = restOf(tw.region) return tw.anchor ~= nil end,
        get = function(r, tw) return { tw.anchor.dx, tw.anchor.dy } end,
        set = function(r, v, tw) setOffset(r, tw.anchor, v[1], v[2]) end,
    },
    angle = {
        start = function(tw) return tw.region.SetAngle ~= nil end,
        get = function(r) return r.rsAngle or 0 end,
        set = function(r, v) r:SetAngle(v) end,
    },
    texcoord = {
        get = function(r) local ulx, uly, _, lly, urx = r:GetTexCoord() return { ulx, urx, uly, lly } end,
        set = function(r, v) r:SetTexCoord(v[1], v[2], v[3], v[4]) end,
    },
    vertexColor = {
        get = function(r)
            if r:IsObjectType("FontString") then
                return { r:GetTextColor() }
            end
            return { r:GetVertexColor() }
        end,
        set = function(r, v)
            if r:IsObjectType("FontString") then
                r:SetTextColor(v[1], v[2], v[3], v[4] and clamp01(v[4]))
            else
                r:SetVertexColor(v[1], v[2], v[3], v[4] and clamp01(v[4]))
            end
        end,
    },
    number = {
        start = function(tw) return type(tw.opts.set) == "function" end,
        set = function(r, v, tw) tw.opts.set(v) end,
    },
    zoom = {
        start = function(tw) return tw.region.SetZoom ~= nil end,
        get = function(r) return r.rsZoom or 1 end,
        set = function(r, v) r:SetZoom(max(v, 0.01)) end,
    },
}
RS.TWEEN_KINDS = KINDS

local function lerp(a, b, t)
    if type(b) == "table" then
        local out = {}
        for i = 1, #b do
            local x = a[i] or b[i]
            out[i] = x + (b[i] - x) * t
        end
        return out
    end
    return a + (b - a) * t
end

-- A colour token or hex for a vertexColor tween -> { r, g, b, a }.
local function colorValue(v)
    if type(v) == "string" then
        return { RS.Rgb(v) }
    end
    return v
end

local tweens = {}
local driver = CreateFrame("Frame", "BleakholdRoyaleTweens")
driver:Hide()
RS.driver = driver

local function finishTween(tw)
    tw.dead = true
    tw.k.set(tw.region, tw.to, tw)
    if tw.onDone then
        ns.SafeCall(tw.onDone, tw.region)
    end
end

local function compact()
    for i = #tweens, 1, -1 do
        if tweens[i].dead then
            table.remove(tweens, i)
        end
    end
    if #tweens == 0 then
        driver:Hide()
    end
end

driver:SetScript("OnUpdate", function()
    local now = GetTime()
    local done
    for _, tw in ipairs(tweens) do
        if not tw.dead and now >= tw.start then
            local t = tw.dur > 0 and (now - tw.start) / tw.dur or 1
            if t >= 1 then
                tw.dead = true
                done = done or {}
                done[#done + 1] = tw
                ns.SafeCall(tw.k.set, tw.region, tw.to, tw)
            elseif not ns.SafeCall(tw.k.set, tw.region, lerp(tw.from, tw.to, tw.ease(t)), tw) then
                tw.dead = true
            end
        end
    end
    if done then
        for _, tw in ipairs(done) do
            if tw.onDone then
                ns.SafeCall(tw.onDone, tw.region)
            end
        end
    end
    compact()
end)

-- Tweens one property of `region` from `from` (nil = its value now) to `to` over `duration` s:
--   alpha        a number (Texture, FontString, Frame)
--   size         { w, h }
--   offset       { dx, dy } added to the anchors the owner gave the region (0,+12 -> 0 is an entrance)
--   angle        radians, RS.Rotatable textures only
--   texcoord     { left, right, top, bottom } (the shine sweep)
--   vertexColor  { r, g, b[, a] } or a colour token (SetTextColor on a FontString)
--   number       a plain number handed to opts.set(v) (the end card's count-up); region is any key for RS.Stop
--   zoom         a factor on the size of an RS.Numeral (or one of its layers), RS.Title or RS.DropWord
-- ease: linear, outCubic (default), inCubic, inOutSine, outBack (s = 1.7). opts: delay (s; `from` applies at once),
-- onDone(region), set (for number). A new tween of the same region and kind replaces the running one (its onDone is
-- dropped). With reduced motion every tween jumps to its end at once.
function RS.Tween(region, kind, from, to, duration, ease, opts)
    local k = KINDS[kind]
    assert(k, "RS.Tween: unknown kind " .. tostring(kind))
    opts = opts or {}
    RS.Stop(region, kind)
    if kind == "vertexColor" then
        from, to = colorValue(from), colorValue(to)
    end
    local tw = { region = region, kind = kind, k = k, to = to, dur = duration or 0, opts = opts, onDone = opts.onDone,
        ease = type(ease) == "function" and ease or RS.EASE[ease or "outCubic"] or RS.EASE.linear }
    if k.start and not k.start(tw) then
        assert(kind ~= "angle", "RS.Tween: angle tweens only on RS.Rotatable textures")
        assert(kind ~= "number", "RS.Tween: a number tween needs opts.set")
        assert(kind ~= "zoom", "RS.Tween: zoom tweens only on RS.Numeral, RS.Title and RS.DropWord")
        tw.dead = true
        if tw.onDone then
            ns.SafeCall(tw.onDone, region)
        end
        return tw
    end
    if from == nil then
        assert(k.get, "RS.Tween: a " .. kind .. " tween needs a start value")
        from = k.get(region, tw)
    end
    tw.from = from
    if not RS.Motion() or (tw.dur <= 0 and not opts.delay) then
        finishTween(tw)
        return tw
    end
    k.set(region, from, tw)
    tw.start = GetTime() + (opts.delay or 0)
    tweens[#tweens + 1] = tw
    driver:Show()
    return tw
end

-- Is a tween of `region` (of `kind`, or any) running?
function RS.Busy(region, kind)
    for _, tw in ipairs(tweens) do
        if not tw.dead and tw.region == region and (not kind or tw.kind == kind) then
            return true
        end
    end
    return false
end

local loops = weak()   -- region -> { kind -> AnimationGroup }

-- Stops the tweens of `region` (of `kind`, or all; "loop" or nil also stops its loops). With `finish` each one
-- jumps to its end and runs its onDone.
function RS.Stop(region, kind, finish)
    local list = {}
    for _, tw in ipairs(tweens) do
        if not tw.dead and tw.region == region and (not kind or tw.kind == kind) then
            tw.dead = true
            list[#list + 1] = tw
        end
    end
    if finish then
        for _, tw in ipairs(list) do
            finishTween(tw)
        end
    end
    if #list > 0 then
        compact()
    end
    if (not kind or kind == "loop") and loops[region] then
        for _, g in pairs(loops[region]) do
            g:Stop()
        end
    end
end

-- Every running tween jumps to its end (reduced motion switched on).
function RS.FinishAll()
    local list = {}
    for _, tw in ipairs(tweens) do
        if not tw.dead then
            tw.dead = true
            list[#list + 1] = tw
        end
    end
    for _, tw in ipairs(list) do
        finishTween(tw)
    end
    compact()
end

local function alphaLoop(g, r, opts, from, to, duration)
    from, to = opts.from or from, opts.to or to
    local a = g:CreateAnimation("Alpha")
    a:SetChange(to - from)
    a:SetDuration(opts.duration or duration)
    a:SetSmoothing("IN_OUT")
    g:SetLooping("BOUNCE")
    g.rsFrom = from
end

local function rotation(g, deg, duration, order, smoothing, origin)
    local a = g:CreateAnimation("Rotation")
    a:SetDegrees(deg)
    a:SetDuration(duration)
    a:SetOrder(order)
    a:SetSmoothing(smoothing)
    a:SetOrigin(origin[1], origin[2] or 0, origin[3] or 0)
    return a
end

local LOOPS = {
    -- gems and glows breathing (opts.from 0.5, opts.to 1, 0.9 s)
    pulse = function(g, r, opts) alphaLoop(g, r, opts, 0.5, 1, 0.9) end,
    -- the speed lines' cross-fade (the other variant runs from/to swapped)
    shimmer = function(g, r, opts) alphaLoop(g, r, opts, 0.16, 0.28, 0.45) end,
    -- the canopy swinging +-opts.degrees (6) over opts.duration (1.6 s), around opts.origin ({ "CENTER" })
    sway = function(g, r, opts)
        local d, t, o = opts.degrees or 6, opts.duration or 1.6, opts.origin or { "CENTER" }
        rotation(g, d, t / 4, 1, "OUT", o)
        rotation(g, -2 * d, t / 2, 2, "IN_OUT", o)
        rotation(g, d, t / 4, 3, "IN", o)
        g:SetLooping("REPEAT")
    end,
    -- a slow turn, clockwise, one revolution per opts.duration (60 s): the next circle's dashes during a shrink
    spin = function(g, r, opts)
        rotation(g, -360, opts.duration or 60, 1, "NONE", opts.origin or { "CENTER" })
        g:SetLooping("REPEAT")
    end,
}

-- A looping ambient animation of `region` (an AnimationGroup, made once per region and kind): pulse, shimmer, sway,
-- spin. It plays only while motion is on; RS.Stop(region, "loop") or RS.StopLoop stops it (the region then snaps
-- back to its own state, which the engine keeps under the animation).
function RS.Loop(region, kind, opts)
    local build = LOOPS[kind]
    assert(build, "RS.Loop: unknown loop " .. tostring(kind))
    assert(not ((kind == "sway" or kind == "spin") and region:IsObjectType("FontString")),
        "RS.Loop: font strings ignore rotation (CScriptRegion.cpp)")
    opts = opts or {}
    local set = loops[region]
    if not set then
        set = {}
        loops[region] = set
    end
    local g = set[kind]
    if not g then
        g = region:CreateAnimationGroup()
        build(g, region, opts)
        set[kind] = g
    end
    if g.rsFrom then
        region:SetAlpha(g.rsFrom)
    end
    if RS.Motion() then
        g:Play()
    else
        g:Stop()
    end
    return g
end

function RS.StopLoop(region, kind)
    local g = loops[region] and loops[region][kind]
    if g then
        g:Stop()
    end
end

function RS.SetMotion(on)
    ns.db.options.royaleMotion = on and true or false
    if not on then
        RS.FinishAll()
        for _, set in pairs(loops) do
            for _, g in pairs(set) do
                g:Stop()
            end
        end
    end
end

------------------------------------------------------------------------------------------------------
-- Clock, sounds, HUD scale
------------------------------------------------------------------------------------------------------
-- The one clock format, M:SS (0:05, 1:40, 12:03): seconds rounded up, as a countdown shows them (`down` rounds down,
-- for a time that has passed). Negative or not a number: 0:00.
function RS.Clock(sec, down)
    sec = tonumber(sec) or 0
    if sec ~= sec or sec < 0 then
        sec = 0
    end
    sec = down and floor(sec + 1e-6) or ceil(sec - 1e-6)
    return strformat("%d:%02d", floor(sec / 60), sec % 60)
end

function RS.Sounds()
    return ns.Option("royaleSounds", true) ~= false
end

function RS.SetSounds(on)
    ns.db.options.royaleSounds = on and true or false
end

-- A stock sound kit by name (SoundEntries.dbc), unless Royale sounds are off.
function RS.Play(kit)
    if RS.Sounds() and PlaySound then
        PlaySound(kit)
        return true
    end
    return false
end

local function quiet()
    local A = ns.Announcer
    if A and A.Quiet then
        return A.Quiet()
    end
    return ns.Option("announcerQuiet", false) and true or false
end

-- One of RS.SOUNDS from Sounds\Royale: the _quiet copy (-9 dB) while the announcer's Quiet is on.
function RS.PlayFile(name)
    if not (RS.Sounds() and PlaySoundFile) then
        return false
    end
    PlaySoundFile(RS.SOUND_DIR .. name .. (quiet() and "_quiet" or "") .. ".wav")
    return true
end

local roots = {}

function RS.HudScale()
    local v = tonumber(ns.Option("royaleHudScale", 1)) or 1
    return U.Clamp(v, RS.HUD_SCALE_MIN, RS.HUD_SCALE_MAX)
end

-- A Royale root frame: it gets the HUD scale now and on every change.
function RS.RegisterRoot(f)
    for _, r in ipairs(roots) do
        if r == f then
            f:SetScale(RS.HudScale())
            return f
        end
    end
    roots[#roots + 1] = f
    f:SetScale(RS.HudScale())
    return f
end

-- /bh royale scale: 0.8-1.4 in steps of 0.01; applies it to every root, lays the kit out again for the new pixel
-- sizes and fires ROYALE_HUD_SCALE (docking depends on it). Returns the scale set, or nil for a bad value.
function RS.SetHudScale(v)
    v = tonumber(v)
    if not v or v ~= v then
        return nil
    end
    v = U.Clamp(floor(v * 100 + 0.5) / 100, RS.HUD_SCALE_MIN, RS.HUD_SCALE_MAX)
    ns.db.options.royaleHudScale = v
    for _, f in ipairs(roots) do
        f:SetScale(v)
    end
    RS.Refresh()
    ns.Fire("ROYALE_HUD_SCALE", v)
    return v
end

------------------------------------------------------------------------------------------------------
-- A new screen size, UI scale or HUD scale: sizes that depend on physical pixels are applied again
------------------------------------------------------------------------------------------------------
function RS.Refresh()
    cachedHeight = nil
    for fs in pairs(made.fonts) do
        RS.Font(fs, fs.rsRole, fs.rsSize)
    end
    for n in pairs(made.numerals) do
        n:Relayout()
    end
    for t in pairs(made.icons) do
        applyIcon(t)
    end
    for p in pairs(made.plates) do
        p:Layout()
    end
    for t in pairs(made.hairlines) do
        local px = 1 / RS.PxPerUnit(t)
        if t.rsVertical then
            t:SetSize(px, t.rsLength)
        else
            t:SetSize(t.rsLength, px)
        end
    end
end

ns.RegisterEvent("DISPLAY_SIZE_CHANGED", function()
    RS.Refresh()
end)

-- 3.3.5 has no UI_SCALE_CHANGED: the options panel's SetCVar(cvar, value, event) signals CVAR_UPDATE (with its own
-- event name, not the CVar's), after the CVar's handler has rescaled UIParent.
ns.RegisterEvent("CVAR_UPDATE", function()
    RS.Refresh()
end)

ns.On("DB_READY", function()
    local s = RS.HudScale()
    for _, f in ipairs(roots) do
        f:SetScale(s)
    end
    RS.Refresh()
end)
