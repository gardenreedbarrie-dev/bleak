-- Bleakhold glue: the shared GlueDialog in the Bleakhold style (Kit board: brass octagon, dark well, menu-style
-- buttons, a red primary button for single-button notices, and a progress bar while connecting).
--
-- GlueDialog serves every glue screen, so the style applies everywhere. The stock dialog code is untouched:
-- GlueDialog_Show still sizes and fills the dialog, and the C++ status events (OPEN/UPDATE/CLOSE_STATUS_DIALOG)
-- still drive it. Without the art files the stock look stays.

local BH = BleakholdGlue

local PROGRESS_WIDTH = 300 -- design px
local PROGRESS_HEIGHT = 8
local PROGRESS_SPACE = 30 -- extra dialog height while the bar shows

-- Steps of the connection (the status text names the step; the client reports no real percentage).
local PROGRESS_STEPS = {
    LOGIN_STATE_CONNECTING = 0.15,
    LOGIN_STATE_HANDSHAKING = 0.30,
    LOGIN_STATE_AUTHENTICATING = 0.45,
    LOGIN_STATE_CHECKINGVERSIONS = 0.55,
    LOGIN_STATE_AUTHENTICATED = 0.65,
    RESPONSE_CONNECTED = 0.70,
    REALM_LIST_IN_PROGRESS = 0.78,
    GAME_SERVER_LOGIN = 0.86,
    CHAR_LIST_RETRIEVING = 0.94,
}

local dialog = {}
BH.Dialog = dialog

local function buttons()
    return { GlueDialogButton1, GlueDialogButton2, GlueDialogButton3 }
end

-- ------------------------------------------------------------------------------------------------ frame

local function buildFrame()
    local art = BH.ART.dialog
    local bg = GlueDialogBackground

    if not bg or not BH.HasArt(art.file) then
        return false
    end

    bg:SetBackdrop(nil)

    -- The art is drawn at twice the design size: the 112-texel corners are 56 design px, and the brass edge
    -- (64 texels in) then meets the dialog's edge, art.margin = 32 design px outside it.
    local m = BH.px(art.margin)
    local c = BH.px(art.corner / 2)
    local t0, t1, t2, t3 = 0, art.corner, art.width - art.corner, art.width
    local cuts = { t0 / art.width, t1 / art.width, t2 / art.width, t3 / art.width }
    local pieces = {}

    local function piece(col, row)
        local texture = bg:CreateTexture(nil, "BACKGROUND")
        BH.SetArt(texture, art, cuts[col], cuts[col + 1], cuts[row], cuts[row + 1])
        pieces[row * 3 + col] = texture
        return texture
    end

    local tl, tr, bl, br = piece(1, 1), piece(3, 1), piece(1, 3), piece(3, 3)
    tl:SetSize(c, c)
    tl:SetPoint("TOPLEFT", bg, "TOPLEFT", -m, m)
    tr:SetSize(c, c)
    tr:SetPoint("TOPRIGHT", bg, "TOPRIGHT", m, m)
    bl:SetSize(c, c)
    bl:SetPoint("BOTTOMLEFT", bg, "BOTTOMLEFT", -m, -m)
    br:SetSize(c, c)
    br:SetPoint("BOTTOMRIGHT", bg, "BOTTOMRIGHT", m, -m)

    local top = piece(2, 1)
    top:SetPoint("TOPLEFT", tl, "TOPRIGHT")
    top:SetPoint("BOTTOMRIGHT", tr, "BOTTOMLEFT")
    local bottom = piece(2, 3)
    bottom:SetPoint("TOPLEFT", bl, "TOPRIGHT")
    bottom:SetPoint("BOTTOMRIGHT", br, "BOTTOMLEFT")
    local left = piece(1, 2)
    left:SetPoint("TOPLEFT", tl, "BOTTOMLEFT")
    left:SetPoint("BOTTOMRIGHT", bl, "TOPRIGHT")
    local right = piece(3, 2)
    right:SetPoint("TOPLEFT", tr, "BOTTOMLEFT")
    right:SetPoint("BOTTOMRIGHT", br, "TOPRIGHT")
    local centre = piece(2, 2)
    centre:SetPoint("TOPLEFT", tl, "BOTTOMRIGHT")
    centre:SetPoint("BOTTOMRIGHT", br, "TOPLEFT")

    dialog.pieces = pieces
    return true
end

-- ---------------------------------------------------------------------------------------------- buttons

-- Content coordinates of an atlas cell, without its shadow margin, so the art fills the button exactly.
local function contentCoords(art, x, y, w, h)
    local inset = art.margin * 2 -- the art is drawn at twice the design size
    return { BH.Coords(art, x + inset, y + inset, w - 2 * inset, h - 2 * inset) }
end

local function styleButton(button, primary)
    if not button then
        return
    end

    if primary then
        local art = BH.ART.primary
        local function cell(row)
            return contentCoords(art, art.x, art.y + art.rowStep * row, art.w, art.h)
        end

        button:SetSize(BH.px(184), BH.px(50))
        BH.SkinButton(button, { art = art, normal = cell(0), hover = cell(1), pressed = cell(2), disabled = cell(3),
                                fonts = dialog.primaryFonts })
    else
        local art = BH.ART.menu
        local c = art.columns.narrow
        local function cell(row)
            return contentCoords(art, c.x, c.y + art.rowStep * row, c.w, c.h)
        end

        button:SetSize(BH.px(182), BH.px(44))
        BH.SkinButton(button, { art = art, normal = cell(0), hover = cell(1), pressed = cell(2), desaturateDisabled = true,
                                fonts = dialog.menuFonts })
    end
end

local function buildButtons()
    if not BH.HasArt(BH.ART.menu.file) or not BH.HasArt(BH.ART.primary.file) then
        return false
    end

    dialog.menuFonts = {
        BH.Font("BleakholdDialogButtonFont", { size = 18, color = "#ffd100", shadow = "#000000", shadowY = 1 }),
        BH.Font("BleakholdDialogButtonHoverFont", { size = 18, color = "#ffffff", shadow = "#000000", shadowY = 1 }),
        BH.Font("BleakholdDialogButtonDisabledFont", { size = 18, color = "#7a7060" }),
    }
    dialog.primaryFonts = {
        BH.Font("BleakholdDialogPrimaryFont", { smallCaps = true, size = 22, color = "#ffeab6", shadow = "#2a0602", shadowY = 2 }),
        BH.Font("BleakholdDialogPrimaryHoverFont", { smallCaps = true, size = 22, color = "#fff4d4", shadow = "#2a0602", shadowY = 2 }),
        BH.Font("BleakholdDialogPrimaryDisabledFont", { smallCaps = true, size = 22, color = "#9a9080" }),
    }

    for _, button in ipairs(buttons()) do
        styleButton(button, false)
    end

    return true
end

-- --------------------------------------------------------------------------------------------- progress

local function buildProgress()
    local bg = GlueDialogBackground
    local bar = CreateFrame("Frame", "BleakholdDialogProgress", bg)
    bar:SetSize(BH.px(PROGRESS_WIDTH), BH.px(PROGRESS_HEIGHT))
    bar:Hide()

    local border = bar:CreateTexture(nil, "BACKGROUND")
    border:SetAllPoints(bar)
    BH.Solid(border, "#5a3e1e")

    local well = bar:CreateTexture(nil, "BORDER")
    well:SetPoint("TOPLEFT", bar, "TOPLEFT", BH.px(1), -BH.px(1))
    well:SetPoint("BOTTOMRIGHT", bar, "BOTTOMRIGHT", -BH.px(1), BH.px(1))
    BH.Solid(well, "#050302")

    local fill = bar:CreateTexture(nil, "ARTWORK")
    fill:SetPoint("TOPLEFT", well, "TOPLEFT")
    fill:SetPoint("BOTTOMLEFT", well, "BOTTOMLEFT")
    fill:SetWidth(1)
    BH.Solid(fill, "#ffb35c", "#c8461a")
    fill:Hide()

    bar.fill = fill
    bar.innerWidth = BH.px(PROGRESS_WIDTH - 2)
    bar.value = 0
    bar.target = 0
    dialog.progress = bar

    dialog.steps = {}

    for name, value in pairs(PROGRESS_STEPS) do
        local text = _G[name]

        if type(text) == "string" and text ~= "" then
            dialog.steps[text] = value
        end
    end
end

local function setProgressValue(bar, value)
    bar.value = value
    local width = bar.innerWidth * math.max(0, math.min(1, value))

    if width < 0.5 then
        bar.fill:Hide()
    else
        bar.fill:SetWidth(width)
        bar.fill:Show()
    end
end

local function progressWanted()
    return GlueDialog.which == "CANCEL" and AccountLogin and AccountLogin:IsShown()
end

-- Positions the bar under the text and makes room for it; called after every stock resize.
local function placeProgress(text)
    local bar = dialog.progress

    if not bar then
        return
    end

    if not progressWanted() then
        bar:Hide()
        return
    end

    local step = text and dialog.steps[text]

    if not bar:IsShown() then
        bar.target = 0.05
        setProgressValue(bar, 0)
    end

    if step and step > bar.target then
        bar.target = step
    end

    bar:ClearAllPoints()
    bar:SetPoint("TOP", GlueDialogText, "BOTTOM", 0, -BH.px(14))
    bar:Show()
    GlueDialogBackground:SetHeight(GlueDialogBackground:GetHeight() + BH.px(PROGRESS_SPACE))
end

function dialog.UpdateProgress(elapsed)
    local bar = dialog.progress

    if not bar or not bar:IsShown() then
        return
    end

    elapsed = elapsed or 0

    -- Creep a little past the last step so a slow step still shows life, but never reach the end.
    local ceiling = math.min(0.97, bar.target + 0.08)
    bar.target = math.min(ceiling, bar.target + elapsed * 0.01)
    setProgressValue(bar, bar.value + (bar.target - bar.value) * math.min(1, elapsed * 4))
end

-- ----------------------------------------------------------------------------------------------- show

local function beforeShow(which)
    if dialog.textFont and GlueDialogText then
        -- The connecting dialog shows the step as a gold title; every other dialog a light message.
        GlueDialogText:SetFontObject(which == "CANCEL" and dialog.titleFont or dialog.textFont)
    end

    if dialog.buttonsStyled then
        local info = GlueDialogTypes and GlueDialogTypes[which]
        local primary = (info and info.button1 and not info.button2 and which ~= "CANCEL") and true or false

        if primary ~= dialog.primary then
            dialog.primary = primary
            styleButton(GlueDialogButton1, primary)
        end
    end
end

local function afterShow(which, text)
    placeProgress(text)
end

local function afterEvent(self, event, arg1)
    if event == "UPDATE_STATUS_DIALOG" and arg1 and arg1 ~= "" then
        placeProgress(arg1)
    end
end

-- -------------------------------------------------------------------------------------------- install

local function install()
    if not GlueDialog or not GlueDialogBackground then
        return
    end

    dialog.textFont = BH.Font("BleakholdDialogTextFont", { size = 20, color = "#f6efe0", shadow = "#000000", shadowY = 1 })
    dialog.titleFont = BH.Font("BleakholdDialogTitleFont", { size = 23, color = "#ffd100", shadow = "#000000", shadowY = 1 })

    if buildFrame() then
        dialog.buttonsStyled = buildButtons()
    end

    buildProgress()

    -- The stock OnUpdate swaps the button textures to the red or blue glue art every frame (and does
    -- nothing else). With the Bleakhold buttons it is no longer run, so they keep their art on every screen.
    local stockOnUpdate = GlueDialog:GetScript("OnUpdate")

    GlueDialog:SetScript("OnUpdate", function(self, elapsed)
        if stockOnUpdate and not dialog.buttonsStyled then
            stockOnUpdate(self, elapsed)
        end

        BH.Try(dialog.UpdateProgress, elapsed)
    end)

    BH.WrapGlobal("GlueDialog_Show", beforeShow, afterShow)
    BH.HookScript(GlueDialog, "OnEvent", afterEvent)
    BH.HookScript(GlueDialog, "OnHide", function()
        if dialog.progress then
            dialog.progress:Hide()
        end
    end)
end

BH.Try(install)

BH.FlushLoadErrors("BleakholdDialog.lua")
