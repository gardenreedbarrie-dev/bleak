-- wowlua tests.lua <harness dir> <glue dir> <scenario>
local HARNESS, GLUE, SCENARIO = arg[1], arg[2], arg[3]
local function dofile(path) return assert(host_loadfile(path))() end
local function exists(path) return host_readfile(path) ~= nil end
dofile(HARNESS .. "/mock.lua")

local failures, checks = 0, 0
local function check(cond, msg)
    checks = checks + 1
    if not cond then failures = failures + 1; print("  FAIL: " .. msg) end
end
local function near(a, b) return a and b and math.abs(a - b) < 0.01 end
local function px(v) return v * 768 / 1080 end

-- Files the client can open: everything shipped in the glue folder (unless the scenario removes the art).
local GLUE_PATH = "Interface\\Bleakhold\\Glue\\"
local ART = { "LoginBackground", "LoginLogo", "LoginField", "LoginButtonPrimary", "LoginButtonMenu", "LoginCheckBox", "LoginDialog" }
local noArt = SCENARIO:find("noart") ~= nil
for _, name in ipairs(ART) do
    check(exists(GLUE .. "/Textures/" .. name .. ".blp"), "texture file exists: " .. name)
    if not noArt then MOCK.addFile(GLUE_PATH .. "Textures\\" .. name) end
end
if not noArt then
    MOCK.addFile(GLUE_PATH .. "Fonts\\Marcellus-Regular.ttf")
    MOCK.addFile(GLUE_PATH .. "Fonts\\MarcellusSC-Regular.ttf")
end
MOCK.addFile("Fonts\\FRIZQT__.TTF"); MOCK.addFile("Fonts\\MORPHEUS.TTF")

dofile(HARNESS .. "/stock.lua")

if SCENARIO == "login-stockignoresscan" then
    -- A stock handler that does not continue past the scan error by itself.
    function AccountLogin_OnEvent(event) end
end
if SCENARIO == "login-noscanevent" then MOCK.cpp.dropScanEvent = true end

-- Load the TOC exactly as FrameXML_CreateFrames reads it: skip '#' lines, paths relative to the TOC.
local toc = assert(host_readfile(GLUE .. "/BleakholdGlue.toc"))
local entries = {}
for line in toc:gmatch("[^\r\n]+") do
    if line:sub(1, 1) ~= "#" then entries[#entries + 1] = line:gsub("%s+$", "") end
end
check(#entries == 6, "TOC lists 6 files")
for _, entry in ipairs(entries) do
    local path = GLUE .. "/" .. entry:gsub("\\", "/")
    check(exists(path), "TOC entry resolves: " .. entry)
    if SCENARIO == "login-autoaccept" and entry == "BleakholdLogin.lua" then BLEAKHOLD_AUTO_ACCEPT_AGREEMENTS = true end
    if entry == "BleakholdLogin.lua" and SCENARIO:find("^login") and SCENARIO ~= "login-classic" then
        BLEAKHOLD_LOGIN_SCREEN = "bleakhold"
    end
    if SCENARIO == "names-off" and entry == "BleakholdNames.lua" then BLEAKHOLD_TWO_NAMES = false end
    local ok, err = pcall(dofile, path)
    check(ok, "loads without error: " .. entry .. (ok and "" or (" -> " .. tostring(err))))
end
check(#MOCK.collisions == 0, "no global name collisions: " .. table.concat(MOCK.collisions, ", "))
check(#BLEAKHOLD_GLUE_ERRORS == 0, "no caught errors after load: " .. table.concat(BLEAKHOLD_GLUE_ERRORS, " | "))

-- ------------------------------------------------------------------------------------------------ login

local function loginScenario()
    local art = not noArt
    check(BleakholdGlue ~= nil, "BleakholdGlue namespace exists")
    -- background / model
    if art then
        check(AccountLogin._model == nil, "stock 3D scene cleared")
        check(BleakholdLoginBackdrop and BleakholdLoginBackdrop:GetFrameLevel() < AccountLoginUI:GetFrameLevel(), "painting is below AccountLoginUI")
        check(BleakholdLoginBackdrop:GetFrameLevel() > AccountLogin:GetFrameLevel(), "painting is above the ModelFFX")
        check(TOSFrame:GetFrameLevel() > BleakholdLoginBackdrop:GetFrameLevel(), "agreement frame above the painting")
        check(BleakholdLoginLogo:GetTexture() ~= nil, "logo texture set")
    else
        check(AccountLogin._model ~= nil, "no art: stock 3D scene kept")
        check(AccountLoginAccountEdit:GetBackdrop() ~= nil, "no art: stock field backdrop kept")
        check(BleakholdLoginLogoText ~= nil and BleakholdLoginLogoText:GetText() == "Bleakhold", "no art: text logo shown")
        check(BleakholdLoginInputFont._fontFile == "Fonts\\FRIZQT__.TTF", "no art: input font falls back to FRIZQT")
    end

    -- First show: agreements, then the scan.
    SetGlueScreen("login")
    if SCENARIO == "login-autoaccept" then
        check(not TOSFrame:IsShown(), "auto-accept: no agreement screen")
    else
        check(TOSFrame:IsShown() and not AccountLoginUI:IsShown(), "EULA screen first")
        TOSAccept:Click()
        check(TOSFrame:IsShown() and TOSFrame.noticeType == "TOS", "then the Terms of Use")
        TOSAccept:Click()
    end
    check(MOCK.cpp.scanStatus == 1, "scan started (ScanDLLStart)")
    MOCK.idle()
    if SCENARIO == "login-noscanevent" or SCENARIO == "login-stockignoresscan" then
        if SCENARIO == "login-noscanevent" then
            check(not IsScanDLLFinished(), "no scan event: gate still closed before login")
            AccountLoginUI:Show() -- the user would be stuck without the UI; show it to reach the button
        end
    else
        check(IsScanDLLFinished(), "scan error answered with ScanDLLContinueAnyway")
        check(AccountLoginUI:IsShown(), "login form shown after the scan")
    end
    if SCENARIO == "login-stockignoresscan" then
        check(IsScanDLLFinished(), "Bleakhold handler continued past the scan error")
        check(AccountLoginUI:IsShown(), "Bleakhold handler showed the login form")
    end

    -- Layout (design px -> UI units).
    local _, _, _, x, y = AccountLoginAccountEdit:GetPoint(1)
    check(near(y, -px(649)), "account field top at design 649 (got " .. tostring(y and y / (768 / 1080)) .. ")")
    _, _, _, x, y = AccountLoginPasswordEdit:GetPoint(1)
    check(AccountLoginPasswordEdit:GetNumPoints() == 1 and near(y, -px(752)), "password field: one anchor, top at design 752")
    _, _, _, x, y = AccountLoginLoginButton:GetPoint(1)
    check(AccountLoginLoginButton:GetNumPoints() == 1 and near(y, -px(832)), "login button top at design 832")
    check(near(AccountLoginAccountEdit:GetWidth(), px(440)) and near(AccountLoginAccountEdit:GetHeight(), px(50)), "field size 440x50")
    local p, rel, rp
    p, rel, rp, x, y = AccountLoginExitButton:GetPoint(1)
    check(p == "BOTTOMRIGHT" and near(x, -px(44)) and near(y, px(40)), "Quit bottom-right")
    p, rel, rp, x, y = AccountLoginCinematicsButton:GetPoint(1)
    check(near(y, px(40 + 3 * 54)), "Cinematics top of the right column")
    check(AccountLoginCinematicsButton:IsShown() and AccountLoginCreditsButton:IsShown(), "Cinematics and Credits shown")
    p, rel, rp, x, y = AccountLoginManageAccountButton:GetPoint(1)
    check(p == "BOTTOMLEFT" and near(y, px(40 + 17 + 20 + 54)), "Manage Account above Community Site")
    check(not AccountLoginTOSButton:IsShown() and not AccountLoginLogo:IsShown(), "stock TOS button and WotLK logo hidden")
    check(not MOCK.stockRegions.blizzLogo:IsShown() and not MOCK.stockRegions.disclaimer:IsShown(), "Blizzard logo and disclaimer hidden")
    check(AccountLoginVersion:GetText() == "Version 3.3.5 (12340)", "version line: " .. tostring(AccountLoginVersion:GetText()))
    if art then
        check(AccountLoginAccountEdit:GetBackdrop() == nil, "stock field backdrop removed")
        check(AccountLoginLoginButton:GetNormalTexture():GetTexture():find("LoginButtonPrimary") ~= nil, "login button uses the primary art")
        check(AccountLoginLoginButton:GetHighlightTexture():GetAlpha() == 0, "stock highlight hidden")
        check(BleakholdLoginSubtitle:GetText() == "Wrath of the Lich King Extra", "subtitle")
    end
    check(AccountLoginSaveAccountNameText:GetText() == "Remember account name", "checkbox caption")

    -- Focus: account first (no saved name), Tab moves to the password.
    check(MOCK.focus() == AccountLoginAccountEdit, "account field focused")
    if art then
        check(AccountLoginAccountEdit.bleakholdGlow:IsShown(), "focused field glows")
        local l, r, t, b = unpack(AccountLoginAccountEdit.bleakholdFrame._coords)
        check(near(t, (256 + 38) / 1024), "focused field uses the focus row")
    end
    MOCK.press(AccountLoginAccountEdit, "OnTabPressed")
    check(MOCK.focus() == AccountLoginPasswordEdit, "Tab moves to the password")
    if art then
        check(not AccountLoginAccountEdit.bleakholdGlow:IsShown() and AccountLoginPasswordEdit.bleakholdGlow:IsShown(), "glow follows focus")
    end

    -- Disabled until both fields have text.
    check(AccountLoginLoginButton:IsEnabled() == nil, "Login disabled while empty")
    AccountLoginAccountEdit:SetText("Adventurer")
    check(AccountLoginLoginButton:IsEnabled() == nil, "Login disabled without a password")
    AccountLoginPasswordEdit:SetText("dragonfire")
    check(AccountLoginLoginButton:IsEnabled() == 1, "Login enabled with both")

    -- Remember the name.
    AccountLoginSaveAccountName:SetChecked(1)
    AccountLoginLoginButton:Click()
    check(MOCK.logins[#MOCK.logins] == "logon ADVENTURER", "Login button reaches DefaultServerLogin past the gate: " .. tostring(MOCK.logins[#MOCK.logins]))
    check(MOCK.cpp.savedName == "Adventurer", "account name remembered")
    check(AccountLoginPasswordEdit:GetText() == "" and AccountLoginLoginButton:IsEnabled() == nil, "password wiped, button disabled again")

    -- Connecting dialog and progress.
    check(GlueDialog:IsShown() and GlueDialog.which == "CANCEL", "connecting dialog shown")
    MOCK.fireEvent("OPEN_STATUS_DIALOG", "CANCEL", LOGIN_STATE_CONNECTING)
    local bar = BleakholdDialogProgress
    check(bar:IsShown(), "progress bar shown while connecting")
    check(near(bar.target, 0.15), "progress target for Connecting")
    local h0 = GlueDialogBackground:GetHeight()
    check(near(h0, 16 + 20 + 8 + GlueDialogButton1:GetHeight() + 16 + px(30)), "dialog grew for the bar")
    MOCK.fireEvent("UPDATE_STATUS_DIALOG", LOGIN_STATE_AUTHENTICATING)
    check(near(bar.target, 0.45), "progress target for Authenticating")
    for i = 1, 60 do GlueDialog:_fire("OnUpdate", 1 / 30) end
    check(bar.value > 0.3 and bar.value <= 0.97, "progress advances smoothly (" .. bar.value .. ")")
    if art then
        check(GlueDialogButton1:GetNormalTexture():GetTexture():find("LoginButtonMenu") ~= nil, "Cancel uses the menu art after OnUpdate")
    else
        check(GlueDialogButton1:GetNormalTexture():GetTexture():find("Glue%-Panel") ~= nil, "no art: stock dialog buttons kept")
    end
    -- Failed login.
    MOCK.fireEvent("OPEN_STATUS_DIALOG", "OKAY", LOGIN_UNKNOWN_ACCOUNT)
    check(not bar:IsShown(), "no bar on the failed-login dialog")
    check(GlueDialogText:GetText():find("bleakhold.com") ~= nil, "failed-login text is Bleakhold's")
    if art then
        check(GlueDialogButton1:GetNormalTexture():GetTexture():find("LoginButtonPrimary") ~= nil, "Okay uses the primary art")
        check(GlueDialogBackground:GetBackdrop() == nil and #BleakholdGlue.Dialog.pieces >= 9, "dialog 9-slice frame")
        local corner = BleakholdGlue.Dialog.pieces[4]
        check(math.abs(corner:GetWidth() - BleakholdGlue.px(56)) < 0.01, "dialog corners at the design size (art at 2x)")
    end
    GlueDialogButton1:Click()
    check(not GlueDialog:IsShown(), "Okay closes the dialog")

    -- Enter key in the password field.
    AccountLoginPasswordEdit:SetText("dragonfire")
    MOCK.press(AccountLoginPasswordEdit, "OnEnterPressed")
    check(MOCK.logins[#MOCK.logins] == "logon ADVENTURER", "Enter logs in")
    AccountLogin_OnKeyDown("ENTER")
    check(MOCK.logins[#MOCK.logins] == "dialog: LOGIN_ENTER_PASSWORD", "Enter with an empty password reaches the client's own message")

    -- Links.
    AccountLoginManageAccountButton:Click()
    check(MOCK.launched[#MOCK.launched] == BLEAKHOLD_ACCOUNT_URL, "Manage Account opens Bleakhold's page")
    AccountLoginCommunityButton:Click()
    check(MOCK.launched[#MOCK.launched] == BLEAKHOLD_COMMUNITY_URL, "Community Site opens Bleakhold's page")
    BleakholdLoginSiteLink:Click()
    check(MOCK.launched[#MOCK.launched] == "https://bleakhold.com", "bleakhold.com link")
    AccountLoginExitButton:Click()
    check(MOCK.cpp.quit, "Quit quits")

    -- Leave for character select: the painting fades with the form; coming back restores it and the
    -- remembered name ticks the box.
    GlueFrameFadeOut(AccountLoginUI, 0.5)
    local fading = false
    for _, f in ipairs(FADEFRAMES) do if f == BleakholdLoginBackdrop then fading = true end end
    check(not art or fading, "painting fades with the form")
    AccountLogin:Hide()
    AccountLoginSaveAccountName:SetChecked(0)
    AccountLoginTokenEdit._shown = true
    SetGlueScreen("login")
    check(AccountLoginSaveAccountName:GetChecked() == 1, "remembered name ticks the box")
    check(MOCK.focus() == AccountLoginPasswordEdit, "saved name: password focused")
    _, _, _, x, y = AccountLoginTokenEdit:GetPoint(1)
    check(y ~= nil, "authenticator field placed")
    local _, _, _, _, accountY = AccountLoginAccountEdit:GetPoint(1)
    check(accountY > -px(649), "form moved up for the authenticator field")
    local _, _, _, _, buttonY = AccountLoginLoginButton:GetPoint(1)
    check(-buttonY / (768 / 1080) + 60 + 22 + 22 <= 980.01, "form ends above the footer")

    check(#BLEAKHOLD_GLUE_ERRORS == 0, "no caught errors: " .. table.concat(BLEAKHOLD_GLUE_ERRORS, " | "))
    check(#MOCK.messages == 0, "no message() popups")
end

-- The classic screen (the default): the stock 3D scene and form stay, the gates and links still work.
local function classicScenario()
    check(BLEAKHOLD_LOGIN_SCREEN == "classic", "classic is the default login screen")
    check(AccountLogin._model ~= nil, "classic: stock 3D scene kept")
    check(BleakholdLoginBackdrop == nil and BleakholdLoginLogo == nil and BleakholdLoginSiteLink == nil, "classic: no painting, logo or link")
    check(AccountLoginAccountEdit:GetBackdrop() ~= nil, "classic: stock field backdrop kept")
    check(AccountLoginLoginButton:GetNormalTexture():GetTexture():find("Glue%-Panel") ~= nil, "classic: stock Login button art kept")

    SetGlueScreen("login")
    check(TOSFrame:IsShown() and not AccountLoginUI:IsShown(), "classic: EULA screen first")
    TOSAccept:Click()
    TOSAccept:Click()
    MOCK.idle()
    check(IsScanDLLFinished(), "classic: scan error answered with ScanDLLContinueAnyway")
    check(AccountLoginUI:IsShown(), "classic: login form shown after the scan")
    check(AccountLoginLogo:IsShown(), "classic: the logo stays (a login patch replaces its texture)")
    check(not AccountLoginTOSButton:IsShown() and not AccountLoginUpgradeAccountButton:IsShown(), "classic: Blizzard account buttons hidden")

    check(AccountLoginLoginButton:IsEnabled() == nil, "classic: Login disabled while empty")
    AccountLoginAccountEdit:SetText("Adventurer")
    AccountLoginPasswordEdit:SetText("dragonfire")
    check(AccountLoginLoginButton:IsEnabled() == 1, "classic: Login enabled with both")
    AccountLoginLoginButton:Click()
    check(MOCK.logins[#MOCK.logins] == "logon ADVENTURER", "classic: Login reaches DefaultServerLogin past the gate: " .. tostring(MOCK.logins[#MOCK.logins]))

    AccountLoginManageAccountButton:Click()
    check(MOCK.launched[#MOCK.launched] == BLEAKHOLD_ACCOUNT_URL, "classic: Manage Account opens Bleakhold's page")
    AccountLogin:Hide()
    AccountLoginTOSButton:Show()
    SetGlueScreen("login")
    check(not AccountLoginTOSButton:IsShown(), "classic: hidden again on the next show")

    check(#BLEAKHOLD_GLUE_ERRORS == 0, "no caught errors: " .. table.concat(BLEAKHOLD_GLUE_ERRORS, " | "))
    check(#MOCK.messages == 0, "no message() popups")
end

-- ---------------------------------------------------------------------------------------------- races

local STOCK = {
    { name = "Human", file = "Human", faction = "Alliance" }, { name = "Dwarf", file = "Dwarf", faction = "Alliance" },
    { name = "Night Elf", file = "NightElf", faction = "Alliance" }, { name = "Gnome", file = "Gnome", faction = "Alliance" },
    { name = "Draenei", file = "Draenei", faction = "Alliance" },
    { name = "Orc", file = "Orc", faction = "Horde" }, { name = "Undead", file = "Scourge", faction = "Horde" },
    { name = "Tauren", file = "Tauren", faction = "Horde" }, { name = "Troll", file = "Troll", faction = "Horde" },
    { name = "Blood Elf", file = "BloodElf", faction = "Horde" },
}

local function racesScenario(count, female)
    local list = {}
    for i = 1, 5 do list[#list + 1] = STOCK[i] end
    if count >= 12 then list[#list + 1] = { name = "High Elf", file = "HighElf", faction = "Alliance" } end
    for i = 6, 10 do list[#list + 1] = STOCK[i] end
    if count >= 12 then list[#list + 1] = { name = "Eredar", file = "Eredar", faction = "Horde" } end
    if count >= 13 then list[#list + 1] = { name = "Stranger", file = "Stranger", faction = "Horde" } end
    MOCK.setRaces(list)
    if female then SetSelectedSex(SEX_FEMALE) end

    check(MAX_RACES >= 12, "MAX_RACES raised to 12 (" .. tostring(MAX_RACES) .. ")")
    check(CharacterCreateRaceButton11 and CharacterCreateRaceButton12, "race buttons 11 and 12 created from the stock template")
    check(CharacterCreateRaceButton12:GetID() == 12 and CharacterCreateRaceButton12NormalTexture ~= nil, "button 12 has its id and textures")
    check(RACE_ICON_TCOORDS.HIGHELF_MALE[1] == 0.5 and RACE_ICON_TCOORDS.HIGHELF_MALE[3] == 0.25, "High Elf icon = Blood Elf icon")
    check(RACE_ICON_TCOORDS.EREDAR_FEMALE[3] == 0.5, "Eredar female icon = Draenei female icon")
    check(GlueAmbienceTracks.HIGHELF == "GlueScreenBloodElf" and RaceLights.EREDAR == RaceLights.DRAENEI, "scene aliases")

    SetGlueScreen("charcreate")
    check(#MOCK.messages == 0, "no 'Too many races!' (" .. table.concat(MOCK.messages, ",") .. ")")
    check(CharacterCreate.numRaces == #list, "all races enumerated")
    for i = 1, #list do
        check(_G["CharacterCreateRaceButton" .. i]:IsShown(), "race button " .. i .. " shown")
    end
    for i = #list + 1, MAX_RACES do
        check(not _G["CharacterCreateRaceButton" .. i]:IsShown(), "race button " .. i .. " hidden")
    end

    local alliance, horde = 0, 0
    for _, r in ipairs(list) do if r.faction == "Horde" then horde = horde + 1 else alliance = alliance + 1 end end
    local rows = math.max(alliance, horde)
    local pitch = 59
    if rows > 5 then pitch = math.min(59, (59 * 4 + 20) / (rows - 1)) end
    local a, h = 0, 0
    for i = 1, #list do
        local b = _G["CharacterCreateRaceButton" .. i]
        local p, rel, rp, x, y = b:GetPoint(1)
        local row
        if list[i].faction == "Horde" then h = h + 1; row = h; check(x == 50, "button " .. i .. " in the Horde column")
        else a = a + 1; row = a; check(x == -50, "button " .. i .. " in the Alliance column") end
        check(b:GetNumPoints() == 1 and p == "TOP" and near(y, -61 - (row - 1) * pitch), "button " .. i .. " row " .. row .. " y=" .. tostring(y))
        check(-61 - (row - 1) * pitch - 38 > -376, "button " .. i .. " stays above the gender buttons")
    end
    if count == 10 then
        -- Same place the stock chain puts them: TOP -61, then 21 below the previous 38-high button.
        local _, _, _, _, y5 = CharacterCreateRaceButton5:GetPoint(1)
        check(near(y5, -61 - 4 * 59), "10 races: stock positions kept")
    end

    -- Select the Bleakhold races.
    local sexName = female and "FEMALE" or "MALE"
    for i, r in ipairs(list) do
        if r.file == "HighElf" or r.file == "Eredar" then
            _G["CharacterCreateRaceButton" .. i]:Click()
            check(GetSelectedRace() == i, r.name .. " selected by its button")
            check(CharacterCreateRaceText:GetText():find(r.file == "HighElf" and "Quel'Thalas" or "Argus") ~= nil, r.name .. " description shown")
            local proxy = r.file == "HighElf" and "BLOODELF" or "DRAENEI"
            local c = CharacterCreateRaceIcon._coords
            check(c[1] == RACE_ICON_TCOORDS[proxy .. "_" .. sexName][1] and c[3] == RACE_ICON_TCOORDS[proxy .. "_" .. sexName][3], r.name .. " portrait icon")
            check(MOCK.races.background:find(r.file == "HighElf" and "UI_BloodElf" or "UI_Draenei") ~= nil, r.name .. " background scene")
        end
    end
    if count >= 13 then
        CharacterCreateRaceButton13:Click()
        check(GetSelectedRace() == 13, "unknown 13th race selectable without errors")
    end
    SetCharacterGender(female and SEX_MALE or SEX_FEMALE)
    check(#MOCK.messages == 0, "gender switch enumerates without errors")
    check(#BLEAKHOLD_GLUE_ERRORS == 0, "no caught errors: " .. table.concat(BLEAKHOLD_GLUE_ERRORS, " | "))
end

-- ------------------------------------------------------------------------------------------------ names

local function namesScenario()
    local first, last = CharacterCreateNameEdit, BleakholdLastNameEdit
    MOCK.setRaces({ STOCK[1], { name = "High Elf", file = "HighElf", faction = "Alliance" }, STOCK[6] })

    if SCENARIO == "names-off" then
        check(last == nil, "off: no last name box")
        SetGlueScreen("charcreate")
        first:SetText("Arthas")
        CharacterCreate_Okay()
        check(MOCK.created[1] == "Arthas", "off: stock name passed on")
        return
    end

    check(last ~= nil and last:GetObjectType() == "EditBox", "last name box created")
    check(last:GetParent() == first:GetParent(), "same parent as the stock box")
    check(first:GetMaxLetters() == 25 and last:GetMaxLetters() == 12, "first box takes a whole name, last box 12 letters")
    check(last._autoFocus == false, "last name box does not take the focus on show")
    check(first:GetWidth() == 130 and last:GetWidth() == 130 and last:GetHeight() == first:GetHeight(), "box sizes")
    local p, rel, rp, x = first:GetPoint(1)
    check(first:GetNumPoints() == 1 and p == "RIGHT" and rel == BleakholdNameAnchor and rp == "CENTER" and x == -2, "first box left of centre")
    p, rel, rp, x = last:GetPoint(1)
    check(p == "LEFT" and rel == BleakholdNameAnchor and rp == "CENTER" and x == 2, "last box right of centre")
    local ap, arel, arp, ax, ay = BleakholdNameAnchor:GetPoint(1)
    check(ap == "BOTTOM" and arel == CharacterCreate and arp == "BOTTOM" and ax == 0 and ay == 55 and BleakholdNameAnchor:GetWidth() == 160,
          "anchor takes the stock box's place")
    local _, randomRel = CharacterCreateRandomName:GetPoint(1)
    check(randomRel == BleakholdNameAnchor, "Randomize button stays under the pair")
    local stockLabel = select(1, first:GetRegions())
    check(stockLabel and stockLabel:GetText() == "First Name" and stockLabel:GetWidth() == 130, "stock label says First Name")
    check(BleakholdLastNameEditLabel and BleakholdLastNameEditLabel:GetText() == "Last Name", "last name label")
    check(BleakholdLastNameEditLabel:GetFontObject() == GlueFontNormalLarge and last:GetFontObject() == GlueEditBoxFont, "fonts copied")
    check(last:GetBackdrop() and last:GetBackdrop().edgeFile == first:GetBackdrop().edgeFile, "backdrop copied")
    check(select(1, last:GetBackdropBorderColor()) == 0.5, "border colour copied")
    local listed = false
    for _, v in pairs(FRAMES_TO_BACKDROP_COLOR) do if v == "BleakholdLastNameEdit" then listed = true end end
    check(listed, "faction backdrop colour list includes the last name box")
    check(CharacterRenameEditBox:GetMaxLetters() == 25, "rename box takes a full name")

    if SCENARIO == "names-paid" then
        PAID_SERVICE_TYPE = 1; PAID_SERVICE_CHARACTER_ID = 3
        MOCK.paidName = "Christopher Ravencrest"
        SetGlueScreen("charcreate")
        check(first:GetText() == "Christopher" and last:GetText() == "Ravencrest", "paid change splits the character's name")
        CharacterCreate_Okay()
        GlueDialog_OnClick(1)
        check(MOCK.created[1] == "Christopher Ravencrest", "paid change confirmation sends the full name: " .. tostring(MOCK.created[1]))
        MOCK.paidName = "Jaina"
        SetGlueScreen("login"); SetGlueScreen("charcreate")
        check(first:GetText() == "Jaina" and last:GetText() == "", "single paid name: empty last name")
        return
    end

    SetGlueScreen("charcreate")
    check(last:IsVisible(), "last name box visible with the screen")
    check(first:GetText() == "" and last:GetText() == "", "boxes start empty")
    local horde = 0
    for _, v in pairs({ last:GetBackdropColor() }) do horde = horde + v end
    CharacterCreateRaceButton3:Click()
    check(select(1, last:GetBackdropColor()) == 0.19, "Horde backdrop colour applied to the last name box")

    -- Typing.
    first:SetFocus()
    MOCK.type(first, "Arthas")
    MOCK.press(first, "OnTabPressed")
    check(MOCK.focus() == last, "Tab moves to the last name")
    MOCK.press(last, "OnTabPressed")
    check(MOCK.focus() == first, "Tab moves back to the first name")
    MOCK.type(first, " ")
    check(first:GetText() == "Arthas" and MOCK.focus() == last, "space in the first name moves to the last name")
    MOCK.type(last, "Menethil")
    MOCK.press(last, "OnEnterPressed")
    check(MOCK.created[1] == "Arthas Menethil", "Enter in the last name creates First Last: " .. tostring(MOCK.created[1]))
    MOCK.type(last, " X")
    check(last:GetText() == "MenethilX", "no spaces in the last name: " .. last:GetText())

    -- Pasting both names into the first box.
    first:SetText(""); last:SetText("")
    MOCK.type(first, "Jaina Proudmoore")
    check(first:GetText() == "Jaina" and last:GetText() == "Proudmoore", "pasted name split: " .. first:GetText() .. "|" .. last:GetText())
    first:SetText(""); last:SetText("")
    MOCK.type(first, "Christophernus")
    check(first:GetText() == "Christophern", "one word keeps 12 letters: " .. first:GetText())
    first:SetText(""); last:SetText("")
    MOCK.type(first, "Zo\195\171lle Brightwater")
    check(first:GetText() == "Zo\195\171lle" and last:GetText() == "Brightwater", "UTF-8 first name split")
    check(BleakholdGlue.Utf8Truncate("\195\169\195\169\195\169", 2) == "\195\169\195\169", "UTF-8 truncation counts letters")
    first:SetText(""); last:SetText("Kept")
    MOCK.type(first, "Anduin Wrynn")
    check(first:GetText() == "Anduin" and last:GetText() == "Kept", "a last name already typed is kept")

    -- Single name, and the stock Enter key in the first box.
    first:SetText("Thrall"); last:SetText("")
    MOCK.press(first, "OnEnterPressed")
    check(MOCK.created[2] == "Thrall", "single name passed on unchanged")
    first:SetText("  "); last:SetText("Doe")
    CharacterCreate_Okay()
    check(first:GetText() == "" and MOCK.created[3] == "", "no first name: nothing joined (the server answers no name)")
    check(BleakholdGlue.FullName(42) == 42 and BleakholdGlue.FullName(nil) == nil, "FullName passes non-strings through")

    -- Randomize.
    CharacterCreateRaceButton2:Click()
    CharacterCreateRandomName:Click()
    check(first:GetText() == "Arannis", "stock random first name")
    local surname = last:GetText()
    check(surname ~= "" and #surname <= 12 and not surname:find("%s"), "random surname: " .. surname)
    local parts = BleakholdGlue.SURNAME_PARTS.HIGHELF
    local themed = false
    for _, start in ipairs(parts[1]) do if surname:sub(1, #start) == start then themed = true end end
    check(themed, "High Elf surname from the High Elf parts")
    for race, list in pairs(BleakholdGlue.SURNAME_PARTS) do
        for _, a in ipairs(list[1]) do
            for _, b in ipairs(list[2]) do
                local n = a .. b
                if #n <= 12 and not n:lower():find("(%a)%1%1") then
                    check(n:find("^%u%l+$") ~= nil, race .. " surname is one capitalised word: " .. n)
                end
            end
        end
        local i = 0
        local name = BleakholdGlue.RandomSurname(race, function(n) i = i + 1; return n end)
        check(#name <= 12, race .. " fallback surname fits: " .. name)
    end

    -- Leaving and coming back clears the last name.
    SetGlueScreen("login"); SetGlueScreen("charcreate")
    check(last:GetText() == "", "new character: last name cleared")
    first:Hide()
    check(not last:IsShown(), "last name box hides with the first")
    first:Show()
    check(last:IsShown(), "and shows with it")
    check(#BLEAKHOLD_GLUE_ERRORS == 0, "no caught errors: " .. table.concat(BLEAKHOLD_GLUE_ERRORS, " | "))
end

local ok, err = pcall(function()
    if SCENARIO == "login-classic" then classicScenario()
    elseif SCENARIO:find("^login") then loginScenario()
    elseif SCENARIO:find("^names") then namesScenario()
    elseif SCENARIO == "races12" then racesScenario(12)
    elseif SCENARIO == "races12-female" then racesScenario(12, true)
    elseif SCENARIO == "races10" then racesScenario(10)
    elseif SCENARIO == "races13" then racesScenario(13)
    elseif SCENARIO == "races12-noart" then racesScenario(12)
    else error("unknown scenario " .. SCENARIO) end
end)
check(ok, "scenario ran to the end" .. (ok and "" or (": " .. tostring(err))))
print(string.format("%-24s %3d checks, %d failed", SCENARIO, checks, failures))
if failures > 0 then host_exit(1) end
