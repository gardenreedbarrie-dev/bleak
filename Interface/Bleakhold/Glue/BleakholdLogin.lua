-- Bleakhold glue: the login screen (Main board, 1920x1080, and the Kit board's field, button and checkbox
-- states).
--
-- The stock AccountLogin frames stay what they are, with their scripts: the account and password fields, the
-- Login button, the remember-name checkbox and the menu buttons are restyled and moved, the 3D login scene is
-- replaced by the painting, and the logo, subtitle and site link are added. The login flow is the stock one
-- (AccountLogin_Login -> DefaultServerLogin, the agreement screens, ScanDLLStart), with two safety nets for the
-- C++ login gate (CGlueMgr::LoginServerLogin refuses silently unless the scan, the EULA and the Terms of Use
-- are cleared): the failed Scan.dll check is always continued past, also right before a login.

local BH = BleakholdGlue
local px = BH.px

local login = {}
BH.Login = login

-- Layout of the Main board, in design pixels (1920x1080).
local FORM_TOP = 618         -- top of the "Account Name" label
local FORM_BOTTOM = 980      -- a taller form (authenticator field) moves up so it stays above this
local LABEL_HEIGHT = 23
local LABEL_GAP = 8
local FIELD_WIDTH, FIELD_HEIGHT = 440, 50
local FIELD_GAP = 22
local BUTTON_GAP = 30
local PRIMARY_WIDTH, PRIMARY_HEIGHT = 276, 60
local CHECK_GAP = 22
local CHECK_SIZE = 22
local CHECK_TEXT_GAP = 12
local MENU_HEIGHT = 44
local MENU_WIDE, MENU_NARROW = 230, 202
local MENU_GAP = 10
local EDGE_X, EDGE_Y = 44, 40
local VERSION_HEIGHT = 17
local LOGO_X, LOGO_Y = 64, 40
local LINK_BOTTOM = 22

local LEFT_MENU = { "AccountLoginManageAccountButton", "AccountLoginCommunityButton" }
local RIGHT_MENU = { "AccountLoginCinematicsButton", "AccountLoginCreditsButton", "OptionsButton", "AccountLoginExitButton" }
local HIDDEN = { "AccountLoginLogo", "WorldOfWarcraftRating", "AccountLoginTOSButton", "AccountLoginUpgradeAccountButton",
                 "AccountLoginShowLauncher" }

-- ------------------------------------------------------------------------------------------------ fonts

local function buildFonts()
    login.fonts = {
        label = BH.Font("BleakholdLoginLabelFont", { size = 19, color = "#ffd100", shadow = "#000000", shadowY = 1, justifyH = "CENTER" }),
        input = BH.Font("BleakholdLoginInputFont", { size = 21, color = "#f6efe0", shadow = "#000000", shadowY = 1 }),
        primary = BH.Font("BleakholdLoginPrimaryFont", { smallCaps = true, size = 27, color = "#ffeab6", shadow = "#2a0602", shadowY = 2 }),
        primaryHover = BH.Font("BleakholdLoginPrimaryHoverFont", { smallCaps = true, size = 27, color = "#fff4d4", shadow = "#2a0602", shadowY = 2 }),
        primaryDisabled = BH.Font("BleakholdLoginPrimaryDisabledFont", { smallCaps = true, size = 27, color = "#9a9080" }),
        menu = BH.Font("BleakholdLoginMenuFont", { size = 18, color = "#ffd100", shadow = "#000000", shadowY = 1 }),
        menuHover = BH.Font("BleakholdLoginMenuHoverFont", { size = 18, color = "#ffffff", shadow = "#000000", shadowY = 1 }),
        menuDisabled = BH.Font("BleakholdLoginMenuDisabledFont", { size = 18, color = "#7a7060" }),
        check = BH.Font("BleakholdLoginCheckFont", { size = 17, color = "#ffd100", shadow = "#000000", shadowY = 1 }),
        subtitle = BH.Font("BleakholdLoginSubtitleFont", { size = 24, color = "#e9d29b", shadow = "#000000", shadowY = 2 }),
        version = BH.Font("BleakholdLoginVersionFont", { size = 14, color = "#cdbb94", shadow = "#000000", shadowY = 1 }),
        link = BH.Font("BleakholdLoginLinkFont", { size = 15, color = "#d9c79f", shadow = "#000000", shadowY = 1 }),
        linkHover = BH.Font("BleakholdLoginLinkHoverFont", { size = 15, color = "#ffd100", shadow = "#000000", shadowY = 1 }),
        logo = BH.Font("BleakholdLoginLogoFont", { smallCaps = true, size = 64, color = "#e2b768", shadow = "#000000", shadowY = 3 }),
    }
end

-- ------------------------------------------------------------------------------------------- background

-- The painting sits in its own child frame of AccountLogin, above the ModelFFX (which clears the screen in
-- its own ARTWORK pass, CSimpleModelFFX::Render) and below AccountLoginUI and the agreement frames.
local function buildBackdrop()
    local backdrop = CreateFrame("Frame", "BleakholdLoginBackdrop", AccountLogin)
    backdrop:SetAllPoints(AccountLogin)

    local background = backdrop:CreateTexture("BleakholdLoginBackground", "BACKGROUND")
    background:SetAllPoints(backdrop)

    if not BH.SetArt(background, BH.ART.background) then
        -- No painting: keep the stock 3D login scene.
        backdrop:Hide()
        return
    end

    local level = AccountLogin:GetFrameLevel() + 1
    backdrop:SetFrameLevel(level)

    local children = { AccountLogin:GetChildren() }

    for i = 1, #children do
        local child = children[i]

        if child ~= backdrop and child:GetFrameLevel() <= level then
            child:SetFrameLevel(level + 1)
        end
    end

    AccountLogin:ClearModel()
    login.backdrop = backdrop
    login.background = background
end

-- Cover-fit: the 16:9 painting fills the screen and is cropped, never stretched.
function login.FitBackground()
    if not login.background then
        return
    end

    local width, height = AccountLogin:GetWidth(), AccountLogin:GetHeight()

    if not width or not height or width <= 0 or height <= 0 then
        width, height = GetScreenWidth(), GetScreenHeight()
    end

    local screenAspect = width / height
    local imageAspect = BH.ART.background.imageAspect
    local left, right, top, bottom = 0, 1, 0, 1

    if screenAspect > imageAspect then
        local v = (1 - imageAspect / screenAspect) / 2
        top, bottom = v, 1 - v
    else
        local u = (1 - screenAspect / imageAspect) / 2
        left, right = u, 1 - u
    end

    login.background:SetTexCoord(left, right, top, bottom)
end

-- ----------------------------------------------------------------------------------------- logo, footer

local function buildLogo()
    local ui = AccountLoginUI
    local art = BH.ART.logo
    local logo = ui:CreateTexture("BleakholdLoginLogo", "ARTWORK")
    local r = art.region

    if BH.SetArt(logo, art, BH.Coords(art, r[1], r[2], r[3], r[4])) then
        -- The texture starts 16 design px left of and above the logo box (make_login_art.py).
        logo:SetSize(px(r[3] / 2), px(r[4] / 2))
        logo:SetPoint("TOPLEFT", ui, "TOPLEFT", px(LOGO_X - 16), -px(LOGO_Y - 16))
    else
        logo:Hide()
        local text = ui:CreateFontString("BleakholdLoginLogoText", "ARTWORK")
        text:SetFontObject(login.fonts.logo)
        text:SetText("Bleakhold")
        text:SetPoint("TOPLEFT", ui, "TOPLEFT", px(LOGO_X), -px(LOGO_Y + 20))
    end

    local subtitle = ui:CreateFontString("BleakholdLoginSubtitle", "ARTWORK")
    subtitle:SetFontObject(login.fonts.subtitle)
    subtitle:SetJustifyH("LEFT")
    subtitle:SetText(BLEAKHOLD_SUBTITLE or "")
    subtitle:SetPoint("TOPLEFT", ui, "TOPLEFT", px(LOGO_X + 10), -px(LOGO_Y + 134))

    local link = CreateFrame("Button", "BleakholdLoginSiteLink", ui)
    link:SetNormalFontObject(login.fonts.link)
    link:SetHighlightFontObject(login.fonts.linkHover)
    link:SetText(BLEAKHOLD_URL_TEXT or BLEAKHOLD_URL or "")
    local width = link:GetTextWidth()
    link:SetSize(math.max(px(120), (width or 0) + px(16)), px(24))
    link:SetPoint("BOTTOM", ui, "BOTTOM", 0, px(LINK_BOTTOM - 4))
    link:SetScript("OnClick", function()
        PlaySound("gsLoginNewAccount")
        LaunchURL(BLEAKHOLD_URL)
    end)

    if AccountLoginVersion then
        local versionText, _, version, build = GetBuildInfo()
        AccountLoginVersion:SetFontObject(login.fonts.version)
        AccountLoginVersion:SetJustifyH("LEFT")
        AccountLoginVersion:SetFormattedText("%s %s (%s)", versionText or "Version", version or "", build or "")
        AccountLoginVersion:ClearAllPoints()
        AccountLoginVersion:SetPoint("BOTTOMLEFT", ui, "BOTTOMLEFT", px(EDGE_X + 4), px(EDGE_Y))
    end
end

-- Stock pieces the design does not have. Hidden again on every show, since stock code shows some of them.
local function hideStock()
    for _, name in ipairs(HIDDEN) do
        local frame = _G[name]

        if frame then
            frame:Hide()
        end
    end

    for _, region in ipairs(BH.FindRegions(AccountLoginUI, "Texture", "Glues-BlizzardLogo")) do
        region:Hide()
    end

    if BLIZZ_DISCLAIMER then
        for _, region in ipairs(BH.FindRegions(AccountLoginUI, "FontString", BLIZZ_DISCLAIMER)) do
            region:Hide()
        end
    end

    if SHOW_LAUNCHER then
        for _, region in ipairs(BH.FindRegions(AccountLoginShowLauncher, "FontString", SHOW_LAUNCHER)) do
            region:Hide()
        end
    end
end

-- ------------------------------------------------------------------------------------------------ fields

function login.SetFieldFocus(edit, focused)
    local art = BH.ART.field

    if edit.bleakholdArt then
        local row = focused and art.rows.focus or art.rows.idle
        edit.bleakholdFrame:SetTexCoord(BH.RowCoords(art, row))
    end

    if edit.bleakholdGlow then
        if focused then
            edit.bleakholdGlow:Show()
        else
            edit.bleakholdGlow:Hide()
        end
    end

    if focused then
        login.focused = edit
    elseif login.focused == edit then
        login.focused = nil
    end
end

local function hideStockLabels(edit, ...)
    for i = 1, select("#", ...) do
        local text = select(i, ...)

        if text then
            for _, region in ipairs(BH.FindRegions(edit, "FontString", text)) do
                region:Hide()
            end
        end
    end
end

local function skinField(edit, labelText)
    if not edit then
        return
    end

    local art = BH.ART.field
    edit:SetSize(px(FIELD_WIDTH), px(FIELD_HEIGHT))
    edit:SetFontObject(login.fonts.input)
    edit:SetJustifyH("CENTER")
    edit:SetTextInsets(px(36), px(36), 0, 0)

    local glow = edit:CreateTexture(nil, "BACKGROUND")
    local frame = edit:CreateTexture(nil, "BORDER")

    if BH.SetArt(frame, art, BH.RowCoords(art, art.rows.idle)) then
        edit:SetBackdrop(nil)
        BH.Outset(frame, edit, art.margin)
        BH.SetArt(glow, art, BH.RowCoords(art, art.rows.glow))
        BH.Outset(glow, edit, art.margin)
        edit.bleakholdArt = true
        edit.bleakholdGlow = glow
    else
        -- No art: keep the stock backdrop.
        frame:Hide()
    end

    glow:Hide()
    edit.bleakholdFrame = frame

    local label = AccountLoginUI:CreateFontString(nil, "OVERLAY")
    label:SetFontObject(login.fonts.label)
    label:SetText(labelText or "")
    label:SetPoint("BOTTOM", edit, "TOP", 0, px(LABEL_GAP))
    edit.bleakholdLabel = label

    BH.HookScript(edit, "OnEditFocusGained", function(self)
        login.SetFieldFocus(self, true)
    end)
    BH.HookScript(edit, "OnEditFocusLost", function(self)
        login.SetFieldFocus(self, false)
    end)
    BH.HookScript(edit, "OnShow", function(self)
        self.bleakholdLabel:Show()
    end)
    BH.HookScript(edit, "OnHide", function(self)
        self.bleakholdLabel:Hide()
    end)
end

local function buildFields()
    skinField(AccountLoginAccountEdit, ACCOUNT_NAME or "Account Name")
    skinField(AccountLoginPasswordEdit, PASSWORD or "Password")
    skinField(AccountLoginTokenEdit, AUTHENTICATOR or "Authenticator")

    hideStockLabels(AccountLoginAccountEdit, ACCOUNT_NAME)
    hideStockLabels(AccountLoginPasswordEdit, PASSWORD)
    hideStockLabels(AccountLoginTokenEdit, AUTHENTICATOR)

    for _, name in ipairs({ "AccountLoginAccountEditLabel", "AccountLoginTokenEditLabel" }) do
        if _G[name] then
            _G[name]:Hide()
        end
    end

    -- The stock hint text in the empty account field; the client shows and hides it itself.
    if AccountLoginAccountEditFill then
        AccountLoginAccountEditFill:SetAlpha(0)
    end

    if AccountLoginTokenEdit and AccountLoginTokenEdit.bleakholdLabel and not AccountLoginTokenEdit:IsShown() then
        AccountLoginTokenEdit.bleakholdLabel:Hide()
    end

    -- The ember glow of the focused field breathes slowly.
    local pulse = CreateFrame("Frame", nil, AccountLoginUI)
    pulse.elapsed = 0
    pulse:SetScript("OnUpdate", function(self, elapsed)
        self.elapsed = self.elapsed + (elapsed or 0)
        local edit = login.focused

        if edit and edit.bleakholdGlow then
            edit.bleakholdGlow:SetAlpha(0.8 + 0.2 * math.sin(self.elapsed * 2.5))
        end
    end)
end

-- ----------------------------------------------------------------------------------------------- buttons

local function primaryCoords(row)
    return { BH.RowCoords(BH.ART.primary, row) }
end

local function buildButtons()
    local f = login.fonts
    local loginButton = AccountLoginLoginButton

    if loginButton then
        local rows = BH.ART.primary.rows
        loginButton:SetSize(px(PRIMARY_WIDTH), px(PRIMARY_HEIGHT))
        BH.SkinButton(loginButton, {
            art = BH.ART.primary, margin = BH.ART.primary.margin,
            normal = primaryCoords(rows.normal), hover = primaryCoords(rows.hover),
            pressed = primaryCoords(rows.pressed), disabled = primaryCoords(rows.disabled),
            fonts = { f.primary, f.primaryHover, f.primaryDisabled }, pushedOffset = 3,
        })
    end

    local function menu(name, column, width)
        local button = _G[name]

        if not button then
            return
        end

        local rows = BH.ART.menu.rows
        button:SetSize(px(width), px(MENU_HEIGHT))
        BH.SkinButton(button, {
            art = BH.ART.menu, margin = BH.ART.menu.margin,
            normal = { BH.MenuCoords(column, rows.normal) }, hover = { BH.MenuCoords(column, rows.hover) },
            pressed = { BH.MenuCoords(column, rows.pressed) }, desaturateDisabled = true,
            fonts = { f.menu, f.menuHover, f.menuDisabled },
        })
    end

    for _, name in ipairs(LEFT_MENU) do
        menu(name, "wide", MENU_WIDE)
    end

    for _, name in ipairs(RIGHT_MENU) do
        menu(name, "narrow", MENU_NARROW)
    end

    -- The design shows Cinematics and Credits, which the stock screen hides.
    for _, name in ipairs({ "AccountLoginCinematicsButton", "AccountLoginCreditsButton" }) do
        if _G[name] then
            _G[name]:Show()
        end
    end
end

local function buildCheckbox()
    local check = AccountLoginSaveAccountName

    if not check then
        return
    end

    local art = BH.ART.checkbox
    check:SetSize(px(CHECK_SIZE), px(CHECK_SIZE))

    if BH.HasArt(art.file) then
        local path = BH.ArtPath(art)
        local box = { BH.CheckCoords(art.cells.box) }
        local mark = { BH.CheckCoords(art.cells.check) }
        local hover = { BH.CheckCoords(art.cells.hover) }

        local function place(texture, coords)
            if texture then
                texture:SetTexCoord(coords[1], coords[2], coords[3], coords[4])
                BH.Outset(texture, check, art.margin)
            end
        end

        check:SetNormalTexture(path)
        check:SetPushedTexture(path)
        check:SetHighlightTexture(path)
        check:SetCheckedTexture(path)
        check:SetDisabledCheckedTexture(path)
        place(check:GetNormalTexture(), box)
        place(check:GetPushedTexture(), box)
        place(check:GetHighlightTexture(), hover)
        place(check:GetCheckedTexture(), mark)
        place(check:GetDisabledCheckedTexture(), mark)

        local highlight = check:GetHighlightTexture()

        if highlight then
            highlight:SetBlendMode("BLEND")
        end

        local disabledMark = check:GetDisabledCheckedTexture()

        if disabledMark then
            disabledMark:SetDesaturated(1)
        end
    end

    local text = AccountLoginSaveAccountNameText

    if text then
        text:SetFontObject(login.fonts.check)
        text:SetText(BLEAKHOLD_REMEMBER_ACCOUNT or SAVE_ACCOUNT_NAME or "Remember account name")
        text:ClearAllPoints()
        text:SetPoint("LEFT", check, "RIGHT", px(CHECK_TEXT_GAP), 0)
    end
end

-- ------------------------------------------------------------------------------------------------ layout

local function placeTop(frame, y)
    frame:ClearAllPoints()
    frame:SetPoint("TOP", AccountLoginUI, "TOP", 0, -px(y))
end

-- Stacks the form from the top of the "Account Name" label down; also places the corner menus.
function login.Layout()
    local ui = AccountLoginUI
    local account, password, token = AccountLoginAccountEdit, AccountLoginPasswordEdit, AccountLoginTokenEdit
    local dropdown = AccountLoginDropDown
    local showDropdown = dropdown and dropdown:IsShown()
    local showToken = token and token:IsShown()
    local dropdownHeight = showDropdown and (dropdown:GetHeight() / BH.SCALE + 4) or 0

    local fieldBlock = LABEL_HEIGHT + LABEL_GAP + FIELD_HEIGHT
    local height = fieldBlock + dropdownHeight + FIELD_GAP + fieldBlock
    if showToken then
        height = height + FIELD_GAP + fieldBlock
    end
    height = height + BUTTON_GAP + PRIMARY_HEIGHT + CHECK_GAP + CHECK_SIZE

    local y = math.min(FORM_TOP, FORM_BOTTOM - height) + LABEL_HEIGHT + LABEL_GAP

    if account then
        placeTop(account, y)
    end
    y = y + FIELD_HEIGHT

    if showDropdown and account then
        dropdown:ClearAllPoints()
        dropdown:SetPoint("TOP", account, "BOTTOM", 0, -px(4))
        y = y + dropdownHeight
    end

    y = y + FIELD_GAP + LABEL_HEIGHT + LABEL_GAP
    if password then
        placeTop(password, y)
    end
    y = y + FIELD_HEIGHT

    if showToken then
        y = y + FIELD_GAP + LABEL_HEIGHT + LABEL_GAP
        placeTop(token, y)
        y = y + FIELD_HEIGHT
    end

    y = y + BUTTON_GAP
    if AccountLoginLoginButton then
        placeTop(AccountLoginLoginButton, y)
    end
    y = y + PRIMARY_HEIGHT + CHECK_GAP

    local check, text = AccountLoginSaveAccountName, AccountLoginSaveAccountNameText

    if check then
        local textWidth = text and text:GetStringWidth() or 0
        local rowWidth = px(CHECK_SIZE + CHECK_TEXT_GAP) + textWidth
        check:ClearAllPoints()
        check:SetPoint("TOPLEFT", ui, "TOP", -rowWidth / 2, -px(y))
        -- Clicking the caption toggles the box too, as in the design.
        check:SetHitRectInsets(0, -(px(CHECK_TEXT_GAP) + textWidth), 0, 0)
    end

    -- Bottom left: Manage Account over Community Site over the version line.
    local bottom = EDGE_Y + VERSION_HEIGHT + 2 * MENU_GAP

    for i = #LEFT_MENU, 1, -1 do
        local button = _G[LEFT_MENU[i]]

        if button then
            button:ClearAllPoints()
            button:SetPoint("BOTTOMLEFT", ui, "BOTTOMLEFT", px(EDGE_X), px(bottom))
            bottom = bottom + MENU_HEIGHT + MENU_GAP
        end
    end

    -- Bottom right: Cinematics, Credits, Options, Quit from the top down.
    bottom = EDGE_Y

    for i = #RIGHT_MENU, 1, -1 do
        local button = _G[RIGHT_MENU[i]]

        if button then
            button:ClearAllPoints()
            button:SetPoint("BOTTOMRIGHT", ui, "BOTTOMRIGHT", -px(EDGE_X), px(bottom))
            bottom = bottom + MENU_HEIGHT + MENU_GAP
        end
    end
end

function login.UpdateLoginButton()
    local button = AccountLoginLoginButton

    if not BLEAKHOLD_LOGIN_NEEDS_INPUT or not button or not AccountLoginAccountEdit or not AccountLoginPasswordEdit then
        return
    end

    local name = AccountLoginAccountEdit:GetText() or ""
    local password = AccountLoginPasswordEdit:GetText() or ""

    if name ~= "" and password ~= "" then
        button:Enable()
    else
        button:Disable()
    end
end

-- ------------------------------------------------------------------------------------------- login gates

-- Scan.dll can never load in this client (BLEAKHOLD(scandll)), so the scan always ends in SCANDLL_ERROR and
-- the stock handler answers with ScanDLLContinueAnyway. This repeats that answer, in case the event was
-- handled differently, and again right before every login.
function login.ContinuePastScan()
    if IsScanDLLFinished and ScanDLLContinueAnyway and not IsScanDLLFinished() then
        ScanDLLContinueAnyway()
    end
end

local function onScanError()
    login.ContinuePastScan()

    if GlueDialog and GlueDialog:IsShown() and type(GlueDialog.which) == "string" and string.find(GlueDialog.which, "^SCANDLL") then
        GlueDialog:Hide()
    end

    local agreementsDone = (not EULAAccepted or EULAAccepted()) and (not TOSAccepted or TOSAccepted())

    if agreementsDone and AccountLogin and AccountLogin:IsShown() and not (TOSFrame and TOSFrame:IsShown()) then
        AccountLoginUI:Show()
    end
end

local function acceptAgreements()
    if not BLEAKHOLD_AUTO_ACCEPT_AGREEMENTS then
        return
    end

    for _, name in ipairs({ "AcceptEULA", "AcceptTOS", "AcceptTerminationWithoutNotice", "AcceptScanning", "AcceptContest" }) do
        if type(_G[name]) == "function" then
            _G[name]()
        end
    end
end

-- -------------------------------------------------------------------------------------------- show/hide

local function onLoginShow()
    hideStock()

    for _, name in ipairs({ "AccountLoginCinematicsButton", "AccountLoginCreditsButton" }) do
        if _G[name] then
            _G[name]:Show()
        end
    end

    if login.backdrop then
        if GlueFrameFadeRemoveFrame then
            GlueFrameFadeRemoveFrame(login.backdrop)
        end

        login.backdrop:SetAlpha(1)
        AccountLogin:ClearModel()
    end

    if AccountLoginSaveAccountName and GetSavedAccountName and GetSavedAccountName() ~= "" then
        AccountLoginSaveAccountName:SetChecked(1)
    end

    login.FitBackground()
    login.Layout()
    login.UpdateLoginButton()

    local focus = GetCurrentKeyBoardFocus and GetCurrentKeyBoardFocus()

    for _, edit in ipairs({ AccountLoginAccountEdit, AccountLoginPasswordEdit, AccountLoginTokenEdit }) do
        if edit then
            login.SetFieldFocus(edit, focus == edit)
        end
    end
end

-- -------------------------------------------------------------------------------------------- install

local function install()
    if not AccountLogin or not AccountLoginUI then
        return
    end

    buildFonts()
    BH.Try(buildBackdrop)
    BH.Try(buildLogo)
    BH.Try(buildFields)
    BH.Try(buildButtons)
    BH.Try(buildCheckbox)
    BH.Try(hideStock)
    BH.Try(login.Layout)
    BH.Try(acceptAgreements)

    BH.HookScript(AccountLogin, "OnShow", onLoginShow)
    BH.HookScript(AccountLogin, "OnSizeChanged", login.FitBackground)

    for _, edit in ipairs({ AccountLoginAccountEdit, AccountLoginPasswordEdit }) do
        BH.HookScript(edit, "OnTextChanged", login.UpdateLoginButton)
    end

    if AccountLoginTokenEdit then
        BH.HookScript(AccountLoginTokenEdit, "OnShow", login.Layout)
        BH.HookScript(AccountLoginTokenEdit, "OnHide", login.Layout)
    end

    -- Stock code that moves the form (the account-list dropdown) runs before our layout again.
    BH.WrapGlobal("AccountLogin_SetupAccountListDDL", nil, login.Layout)

    -- The safety net for the scan gate, right before the stock login.
    BH.WrapGlobal("AccountLogin_Login", login.ContinuePastScan, login.UpdateLoginButton)

    -- Fade the painting with the form when the screen leaves for character select.
    BH.WrapGlobal("GlueFrameFadeOut", nil, function(frame, timeToFade)
        if frame == AccountLoginUI and login.backdrop and GlueFrameFade then
            GlueFrameFade(login.backdrop, timeToFade, "OUT")
        end
    end)

    local events = CreateFrame("Frame", "BleakholdLoginEvents", AccountLogin)
    events:RegisterEvent("SCANDLL_ERROR")
    events:SetScript("OnEvent", function(self, event)
        BH.Try(onScanError)
    end)
end

-- The menu links open Bleakhold's pages instead of Blizzard's.
function AccountLogin_ManageAccount()
    PlaySound("gsLoginNewAccount")
    LaunchURL(BLEAKHOLD_ACCOUNT_URL or BLEAKHOLD_URL)
end

function AccountLogin_LaunchCommunitySite()
    PlaySound("gsLoginNewAccount")
    LaunchURL(BLEAKHOLD_COMMUNITY_URL or BLEAKHOLD_URL)
end

BH.Try(install)

BH.FlushLoadErrors("BleakholdLogin.lua")
