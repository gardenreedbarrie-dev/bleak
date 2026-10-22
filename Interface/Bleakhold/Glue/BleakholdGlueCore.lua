-- Bleakhold glue: shared helpers.
--
-- The client loads Interface\Bleakhold\Glue\BleakholdGlue.toc right after the stock Interface\GlueXML\GlueXML.toc
-- on every glue load (WoW/Source/Glue/CGlueMgr.cpp, BLEAKHOLD(loginui)). The stock frames and functions
-- therefore already exist; these files only restyle and extend them and never replace a Blizzard file. Every
-- step is guarded: when a stock frame is missing or a texture or font cannot be loaded, that step is skipped
-- and the stock screen keeps working.

BleakholdGlue = {}
local BH = BleakholdGlue

BH.PATH = "Interface\\Bleakhold\\Glue\\"
BH.TEXTURES = BH.PATH .. "Textures\\"
BH.FONT_REGULAR = BH.PATH .. "Fonts\\Marcellus-Regular.ttf"
BH.FONT_SMALLCAPS = BH.PATH .. "Fonts\\MarcellusSC-Regular.ttf"
BH.FONT_FALLBACK = "Fonts\\FRIZQT__.TTF"
BH.FONT_FALLBACK_SMALLCAPS = "Fonts\\MORPHEUS.TTF"

-- The design boards are drawn for a 1080-pixel-high screen; the glue screen is 768 units high.
BH.SCALE = 768 / 1080

function BH.px(value)
    return value * BH.SCALE
end

-- ------------------------------------------------------------------------------------------------- errors

-- Errors are caught per step so one failing step cannot take the rest of the screen (or the login) with it.
-- They are kept in BLEAKHOLD_GLUE_ERRORS and passed to the error handler when there is one; errors raised
-- while a file loads are rethrown at the end of that file so that they reach Logs\GlueXML.log.
BLEAKHOLD_GLUE_ERRORS = {}
local pendingErrors = {}

function BH.Try(fn, ...)
    local ok, err = pcall(fn, ...)

    if not ok then
        err = tostring(err)
        BLEAKHOLD_GLUE_ERRORS[#BLEAKHOLD_GLUE_ERRORS + 1] = err
        pendingErrors[#pendingErrors + 1] = err

        local handler = geterrorhandler and geterrorhandler()

        if type(handler) == "function" then
            pcall(handler, err)
        end
    end

    return ok, err
end

-- Called at the end of each Bleakhold file.
function BH.FlushLoadErrors(file)
    if #pendingErrors > 0 then
        local text = file .. ": " .. table.concat(pendingErrors, "\n")
        pendingErrors = {}
        error(text, 0)
    end
end

-- ------------------------------------------------------------------------------------------------ colours

function BH.Color(hex, alpha)
    hex = string.gsub(hex, "#", "")
    local r = tonumber(string.sub(hex, 1, 2), 16) / 255
    local g = tonumber(string.sub(hex, 3, 4), 16) / 255
    local b = tonumber(string.sub(hex, 5, 6), 16) / 255
    return r, g, b, alpha or 1
end

-- ------------------------------------------------------------------------------------------------- fonts

BH.fonts = {}

-- spec: smallCaps, size (design px), color (hex), shadow (hex, or nil), shadowX/shadowY (design px),
-- justifyH. Falls back to the stock fonts when the Marcellus files are missing.
function BH.Font(name, spec)
    local font = CreateFont(name)
    local size = BH.px(spec.size)
    local file = spec.smallCaps and BH.FONT_SMALLCAPS or BH.FONT_REGULAR

    if not font:SetFont(file, size) then
        font:SetFont(spec.smallCaps and BH.FONT_FALLBACK_SMALLCAPS or BH.FONT_FALLBACK, size)
    end

    font:SetTextColor(BH.Color(spec.color))

    if spec.shadow then
        font:SetShadowColor(BH.Color(spec.shadow))
        font:SetShadowOffset(BH.px(spec.shadowX or 0), -BH.px(spec.shadowY or 1))
    else
        font:SetShadowColor(0, 0, 0, 0)
        font:SetShadowOffset(0, 0)
    end

    if spec.justifyH then
        font:SetJustifyH(spec.justifyH)
    end

    BH.fonts[name] = font
    return font
end

-- --------------------------------------------------------------------------------------------------- art

-- Atlas geometry, in texels. Tools/BlpConvert/make_login_art.py draws these files; keep the two in step.
-- margin: design pixels the region reaches past the widget on each side (shadows and glows).
BH.ART = {
    background = { file = "LoginBackground", width = 2048, height = 1024, imageAspect = 1920 / 1080 },
    logo = { file = "LoginLogo", width = 2048, height = 512, region = { 0, 0, 1280, 320 } },
    field = { file = "LoginField", width = 1024, height = 1024, x = 32, y = 38, w = 960, h = 180, rowStep = 256, margin = 20,
              rows = { idle = 0, focus = 1, glow = 2 } },
    primary = { file = "LoginButtonPrimary", width = 1024, height = 1024, x = 188, y = 20, w = 648, h = 216, rowStep = 256, margin = 24,
                rows = { normal = 0, hover = 1, pressed = 2, disabled = 3 } },
    menu = { file = "LoginButtonMenu", width = 1024, height = 512, rowStep = 128, margin = 2,
             columns = { wide = { x = 22, y = 16, w = 468, h = 96 }, narrow = { x = 562, y = 16, w = 412, h = 96 } },
             rows = { normal = 0, hover = 1, pressed = 2 } },
    checkbox = { file = "LoginCheckBox", width = 512, height = 128, x = 8, y = 8, w = 112, h = 112, columnStep = 128, margin = 3,
                 cells = { box = 0, check = 1, hover = 2 } },
    dialog = { file = "LoginDialog", width = 512, height = 512, margin = 32, corner = 112 },
}

local artLoaded = {}
local probe

-- True when the texture file can be loaded (loose file or archive). The answer is cached; the probe load
-- stays in the client's texture cache, so the real use costs nothing extra.
function BH.HasArt(file)
    if artLoaded[file] == nil then
        if not probe then
            local holder = CreateFrame("Frame")
            holder:Hide()
            probe = holder:CreateTexture()
        end

        artLoaded[file] = probe:SetTexture(BH.TEXTURES .. file) and true or false
        probe:SetTexture(nil)
    end

    return artLoaded[file]
end

function BH.ArtPath(art)
    return BH.TEXTURES .. art.file
end

-- Texture coordinates (left, right, top, bottom) of a texel rectangle in an atlas.
function BH.Coords(art, x, y, w, h)
    return x / art.width, (x + w) / art.width, y / art.height, (y + h) / art.height
end

function BH.RowCoords(art, row)
    return BH.Coords(art, art.x, art.y + art.rowStep * row, art.w, art.h)
end

function BH.MenuCoords(column, row)
    local art = BH.ART.menu
    local c = art.columns[column]
    return BH.Coords(art, c.x, c.y + art.rowStep * row, c.w, c.h)
end

function BH.CheckCoords(cell)
    local art = BH.ART.checkbox
    return BH.Coords(art, art.x + art.columnStep * cell, art.y, art.w, art.h)
end

-- Sets a texture from an atlas; false (and nothing changed) when the file is missing.
function BH.SetArt(texture, art, left, right, top, bottom)
    if not texture or not BH.HasArt(art.file) or not texture:SetTexture(BH.ArtPath(art)) then
        return false
    end

    texture:SetTexCoord(left or 0, right or 1, top or 0, bottom or 1)
    return true
end

-- Anchors a region to cover `frame` plus a margin (design px) on every side.
function BH.Outset(region, frame, margin)
    local m = BH.px(margin)
    region:ClearAllPoints()
    region:SetPoint("TOPLEFT", frame, "TOPLEFT", -m, m)
    region:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", m, -m)
end

-- A solid colour (or a vertical gradient from `top` to `bottom`) for when the art is missing.
function BH.Solid(texture, top, bottom, alpha)
    texture:SetTexture(1, 1, 1, alpha or 1)

    if bottom then
        local r1, g1, b1 = BH.Color(bottom)
        local r2, g2, b2 = BH.Color(top)
        texture:SetGradient("VERTICAL", r1, g1, b1, r2, g2, b2)
    else
        texture:SetVertexColor(BH.Color(top))
    end
end

-- ---------------------------------------------------------------------------------------------- buttons

local function setCoords(texture, coords)
    if texture and coords then
        texture:SetTexCoord(coords[1], coords[2], coords[3], coords[4])
    end
end

local function onButtonEnter(button)
    if button:IsEnabled() == 1 then
        setCoords(button:GetNormalTexture(), button.bleakholdHover)
    end
end

local function onButtonLeave(button)
    setCoords(button:GetNormalTexture(), button.bleakholdNormal)
end

-- Restyles a stock button with atlas art, keeping the button (and its scripts) itself.
-- spec.art: an entry of BH.ART; spec.normal/hover/pressed/disabled: texture coordinates {l, r, t, b};
-- spec.margin: design px the art reaches past the button (nil: the art fills the button);
-- spec.fonts: {normal, highlight, disabled} font objects; spec.desaturateDisabled: grey the normal art.
-- Hover swaps the normal texture's coordinates (a highlight texture would cover the pressed state).
-- Returns false, changing nothing, when the art file is missing.
function BH.SkinButton(button, spec)
    if not button or not BH.HasArt(spec.art.file) then
        return false
    end

    local path = BH.ArtPath(spec.art)
    button:SetNormalTexture(path)
    button:SetPushedTexture(path)
    button:SetDisabledTexture(path)

    local function place(texture, coords)
        if texture then
            setCoords(texture, coords)

            if spec.margin then
                BH.Outset(texture, button, spec.margin)
            else
                texture:ClearAllPoints()
                texture:SetAllPoints(button)
            end
        end
    end

    place(button:GetNormalTexture(), spec.normal)
    place(button:GetPushedTexture(), spec.pressed or spec.normal)
    place(button:GetDisabledTexture(), spec.disabled or spec.normal)

    local disabled = button:GetDisabledTexture()

    if disabled then
        disabled:SetDesaturated(spec.desaturateDisabled and 1 or nil)
    end

    local highlight = button:GetHighlightTexture()

    if highlight then
        highlight:SetAlpha(0)
    end

    button.bleakholdNormal = spec.normal
    button.bleakholdHover = spec.hover or spec.normal

    if not button.bleakholdHooked then
        button.bleakholdHooked = true
        BH.HookScript(button, "OnEnter", onButtonEnter)
        BH.HookScript(button, "OnLeave", onButtonLeave)
    end

    if spec.fonts then
        button:SetNormalFontObject(spec.fonts[1])
        button:SetHighlightFontObject(spec.fonts[2] or spec.fonts[1])
        button:SetDisabledFontObject(spec.fonts[3] or spec.fonts[1])
    end

    button:SetPushedTextOffset(0, -BH.px(spec.pushedOffset or 2))

    local text = button:GetFontString()

    if text then
        text:ClearAllPoints()
        text:SetPoint("CENTER", button, "CENTER", 0, 0)
    end

    return true
end

-- ----------------------------------------------------------------------------------------------- frames

-- Finds the unnamed regions of a frame: kind "Texture" whose file contains `match`, or "FontString" whose
-- text equals `match`.
function BH.FindRegions(frame, kind, match)
    local found = {}

    if not frame or not frame.GetRegions then
        return found
    end

    local regions = { frame:GetRegions() }

    for i = 1, #regions do
        local region = regions[i]

        if region and region.GetObjectType and region:GetObjectType() == kind then
            if kind == "FontString" then
                if match and region:GetText() == match then
                    found[#found + 1] = region
                end
            else
                local file = region:GetTexture()

                if match and type(file) == "string" and string.find(string.lower(file), string.lower(match), 1, true) then
                    found[#found + 1] = region
                end
            end
        end
    end

    return found
end

-- Runs fn after a frame script, without replacing the stock handler.
function BH.HookScript(frame, script, fn)
    if not frame then
        return
    end

    local function hook(...)
        BH.Try(fn, ...)
    end

    if frame.HookScript and frame:GetScript(script) then
        frame:HookScript(script, hook)
    else
        frame:SetScript(script, hook)
    end
end

-- Wraps a global function: before(...) and after(...) run around the original and can never stop it.
function BH.WrapGlobal(name, before, after)
    local original = _G[name]

    if type(original) ~= "function" then
        return false
    end

    _G[name] = function(...)
        if before then
            BH.Try(before, ...)
        end

        local a, b, c, d = original(...)

        if after then
            BH.Try(after, ...)
        end

        return a, b, c, d
    end

    return true
end

BH.FlushLoadErrors("BleakholdGlueCore.lua")
