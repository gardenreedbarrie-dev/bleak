-- Stand-ins for the stock 3.3.5a GlueXML pieces the Bleakhold glue touches: frames with the stock names and
-- the stock behaviour the Bleakhold code relies on, written for this test (not copied from Blizzard's files).

local function frame(kind, name, parent, w, h, hidden)
    local f = CreateFrame(kind, name, parent)
    if w then f:SetSize(w, h) end
    if hidden then f._shown = false end
    return f
end

-- globals from GlueStrings / GlueParent
ACCOUNT_NAME = "Account Name"; PASSWORD = "Password"; AUTHENTICATOR = "Authenticator"; LOGIN = "Login"
SAVE_ACCOUNT_NAME = "Remember Account Name"; BLIZZ_DISCLAIMER = "Copyright 2004-2010 Blizzard Entertainment"
SHOW_LAUNCHER = "Show Launcher"; VERSION_TEMPLATE = "%s %s (%s) (%s)\n%s"; OKAY = "Okay"; CANCEL = "Cancel"; HELP = "Help"
MANAGE_ACCOUNT = "Manage Account"; COMMUNITY_SITE = "Community Site"; CINEMATICS = "Cinematics"; CREDITS = "Credits"; QUIT = "Quit"
LOGIN_STATE_CONNECTING = "Connecting"; LOGIN_STATE_HANDSHAKING = "Handshaking"; LOGIN_STATE_AUTHENTICATING = "Authenticating"
LOGIN_STATE_AUTHENTICATED = "Authenticated"; LOGIN_STATE_CHECKINGVERSIONS = "Checking version"; RESPONSE_CONNECTED = "Connected"
REALM_LIST_IN_PROGRESS = "Retrieving realm list"; GAME_SERVER_LOGIN = "Logging in to game server"; CHAR_LIST_RETRIEVING = "Retrieving character list"
LOGIN_UNKNOWN_ACCOUNT = "<stock unknown account>"; LOGIN_INCORRECT_PASSWORD = "<stock incorrect password>"
AUTH_NO_TIME_URL = "http://blizzard.example/account"; COMMUNITY_URL = "http://blizzard.example/community"
SCANDLL_URL_LAUNCHER_TXT = "http://launcher.example/launcher.txt"; SCANDLL_URL_WIN32_SCAN_DLL = "http://launcher.example/scan.dll"
SEX_NONE, SEX_MALE, SEX_FEMALE = 1, 2, 3
MALE, FEMALE = "Male", "Female"

-- GlueParent.lua
GlueParent = frame("Frame", "GlueParent", nil, 1365.33, 768)
GlueScreenInfo = { login = "AccountLogin", charcreate = "CharacterCreate" }
FADEFRAMES = {}
CURRENT_GLUE_SCREEN = nil
GlueAmbienceTracks = { BLOODELF = "GlueScreenBloodElf", DRAENEI = "GlueScreenDraenei", HUMAN = "GlueScreenHuman" }
RaceLights = { BLOODELF = { { 1, 0, 0, 0, -1, 1, 0.6, 0.6, 0.7, 1, 0, 0, 0 } }, DRAENEI = { { 1, 0, 0, 0, -1, 1, 0.5, 0.5, 0.6, 1, 0, 0, 0 } } }
CharModelFogInfo = { HUMAN = { r = 0.8, g = 0.65, b = 0.73, far = 222 } }
CharModelGlowInfo = { HUMAN = 0.15 }
function SetGlueScreen(name)
    local newFrame
    for index, value in pairs(GlueScreenInfo) do
        local f = _G[value]
        if f then f:Hide(); if index == name then newFrame = f end end
    end
    if newFrame then newFrame:Show(); CURRENT_GLUE_SCREEN = name end
end
function GlueFrameFade(f, t, mode, fin) f.fadeTimer = 0; f.timeToFade = t; f.mode = mode; if fin then f.finishedFunction = fin end; table.insert(FADEFRAMES, f) end
function GlueFrameFadeIn(f, t, fin) GlueFrameFade(f, t, "IN", fin) end
function GlueFrameFadeOut(f, t, fin) GlueFrameFade(f, t, "OUT", fin) end
function GlueFrameFadeRemoveFrame(f) for i = #FADEFRAMES, 1, -1 do if FADEFRAMES[i] == f then table.remove(FADEFRAMES, i) end end end
function SetBackgroundModel(model, name)
    local upper = string.upper(name)
    SetCharCustomizeBackground("Interface\\Glues\\Models\\UI_" .. name .. "\\UI_" .. name .. ".m2")
    PlayGlueAmbience(GlueAmbienceTracks[upper], 4.0)
    local lights = RaceLights[upper]
    if lights then for _, a in pairs(lights) do model:AddLight(0, unpack(a)) end end
end

-- ------------------------------------------------------------------------------------------- GlueDialog

MAX_NUM_GLUE_DIALOG_BUTTONS = 3
GlueDialog = frame("Frame", "GlueDialog", GlueParent, 1365, 768, true)
GlueDialog._strata = "DIALOG"
GlueDialogBackground = frame("Frame", "GlueDialogBackground", GlueDialog, 512, 120)
GlueDialogBackground:SetBackdrop({ bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background", edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border", tile = true, tileSize = 32, edgeSize = 32 })
GlueDialogText = GlueDialogBackground:CreateFontString("GlueDialogText", "ARTWORK")
GlueDialogText._height = 20
function GlueDialogText:GetHeight() return 20 end
GlueDialogHTML = frame("SimpleHTML", "GlueDialogHTML", GlueDialogBackground, 450, 30, true)
GlueDialogEditBox = frame("EditBox", "GlueDialogEditBox", GlueDialog, 130, 32, true)
GlueDialogAlertIcon = GlueDialogBackground:CreateTexture("GlueDialogAlertIcon", "ARTWORK")
MOCK.addFile("Interface\\Glues\\Common\\Glue-Panel-Button-Up-Blue")
MOCK.addFile("Interface\\Glues\\Common\\Glue-Panel-Button-Down-Blue")
MOCK.addFile("Interface\\Glues\\Common\\Glue-Panel-Button-Highlight-Blue")
MOCK.addFile("Interface\\Glues\\Common\\Glue-Panel-Button-Up")
MOCK.addFile("Interface\\Glues\\Common\\Glue-Panel-Button-Down")
MOCK.addFile("Interface\\Glues\\Common\\Glue-Panel-Button-Highlight")
for i = 1, 3 do
    local b = frame("Button", "GlueDialogButton" .. i, GlueDialogBackground, 200, 40)
    b:SetID(i)
    b:SetNormalTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Up-Blue"); b:GetNormalTexture():SetTexCoord(0, 0.578125, 0, 0.75)
    b:SetPushedTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Down-Blue"); b:GetPushedTexture():SetTexCoord(0, 0.578125, 0, 0.75)
    b:SetHighlightTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Highlight-Blue", "ADD")
    b:SetNormalFontObject(CreateFont("GlueFontNormal"))
    b:SetScript("OnClick", function(self) GlueDialog_OnClick(self:GetID()) end)
end
GlueDialogTypes = {
    CANCEL = { text = "", button1 = CANCEL, OnAccept = function() StatusDialogClick() end },
    OKAY = { text = "", button1 = OKAY, OnAccept = function() StatusDialogClick() end },
    CONNECTION_HELP = { text = "", button1 = HELP, button2 = OKAY },
    SCANDLL_ERROR = { text = "", button1 = "Continue", button2 = QUIT,
                      OnAccept = function() GlueDialog:Hide(); ScanDLLContinueAnyway(); AccountLoginUI:Show() end },
}
function GlueDialog_Show(which, text, data)
    local info = GlueDialogTypes[which]
    if GlueDialog:IsShown() and GlueDialog.which ~= which then GlueDialog:Hide() end
    GlueDialogText:SetText(text or info.text)
    GlueDialogButton1:SetText(info.button1)
    if info.button2 then GlueDialogButton2:SetText(info.button2); GlueDialogButton2:Show() else GlueDialogButton2:Hide() end
    GlueDialogButton3:Hide()
    GlueDialog.which = which
    GlueDialogBackground:SetHeight(16 + GlueDialogText:GetHeight() + 8 + GlueDialogButton1:GetHeight() + 16)
    GlueDialog:Show()
end
function GlueDialog_OnClick(index) GlueDialog:Hide(); local info = GlueDialogTypes[GlueDialog.which]; if index == 1 and info.OnAccept then info.OnAccept() end end
function GlueDialog_OnUpdate(self, elapsed)
    for i = 1, MAX_NUM_GLUE_DIALOG_BUTTONS do
        local button = _G["GlueDialogButton" .. i]
        if CURRENT_GLUE_SCREEN == "login" then
            button:SetNormalTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Up-Blue")
        else
            button:SetNormalTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Up")
        end
    end
end
GlueDialog:SetScript("OnUpdate", function(self, elapsed) GlueDialog_OnUpdate(self, elapsed) end)
GlueDialog:SetScript("OnEvent", function(self, event, arg1, arg2, arg3)
    if event == "OPEN_STATUS_DIALOG" then
        GlueDialog_Show(arg1, arg2, arg3)
    elseif event == "UPDATE_STATUS_DIALOG" and arg1 and #arg1 > 0 then
        GlueDialogText:SetText(arg1)
        GlueDialogBackground:SetHeight(32 + GlueDialogText:GetHeight() + 8 + GlueDialogButton1:GetHeight() + 16)
    elseif event == "CLOSE_STATUS_DIALOG" then
        GlueDialog:Hide()
    end
end)
GlueDialog:RegisterEvent("OPEN_STATUS_DIALOG"); GlueDialog:RegisterEvent("UPDATE_STATUS_DIALOG"); GlueDialog:RegisterEvent("CLOSE_STATUS_DIALOG")

-- --------------------------------------------------------------------------------------------- AccountLogin

AccountLogin = frame("ModelFFX", "AccountLogin", GlueParent, 1365.33, 768, true)
AccountLogin:SetAllPoints(GlueParent)
AccountLoginUI = frame("Frame", "AccountLoginUI", AccountLogin, 1365.33, 768)
AccountLoginUI:SetAllPoints(AccountLogin)
MOCK.addFile("Interface\\Glues\\Mainmenu\\Glues-BlizzardLogo")
local blizzLogo = AccountLoginUI:CreateTexture(nil, "ARTWORK"); blizzLogo:SetTexture("Interface\\Glues\\Mainmenu\\Glues-BlizzardLogo")
local disclaimer = AccountLoginUI:CreateFontString(nil, "ARTWORK"); disclaimer:SetText(BLIZZ_DISCLAIMER)
MOCK.stockRegions = { blizzLogo = blizzLogo, disclaimer = disclaimer }
AccountLoginVersion = AccountLoginUI:CreateFontString("AccountLoginVersion", "ARTWORK")
AccountLoginLogo = AccountLoginUI:CreateTexture("AccountLoginLogo", "OVERLAY")
WorldOfWarcraftRating = AccountLoginUI:CreateTexture("WorldOfWarcraftRating", "OVERLAY"); WorldOfWarcraftRating._shown = false

local function edit(name, label, y, hidden)
    local e = frame("EditBox", name, AccountLoginUI, 200, 37, hidden)
    e:SetPoint("BOTTOM", AccountLoginUI, "BOTTOM", 0, y)
    e:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background", edgeFile = "Interface\\Glues\\Common\\Glue-Tooltip-Border" })
    local l = e:CreateFontString(label == ACCOUNT_NAME and name .. "Label" or nil, "BACKGROUND"); l:SetText(label)
    e:SetScript("OnEscapePressed", function() AccountLogin_Exit() end)
    e:SetScript("OnEnterPressed", function() if TOSFrame:IsShown() then return end AccountLogin_Login() end)
    e:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
    e:SetScript("OnEditFocusLost", function(self) self:HighlightText(0, 0) end)
    return e
end
edit("AccountLoginAccountEdit", ACCOUNT_NAME, 345)
AccountLoginAccountEditFill = AccountLoginAccountEdit:CreateFontString("AccountLoginAccountEditFill", "BACKGROUND")
AccountLoginAccountEdit:SetScript("OnTabPressed", function() AccountLogin_FocusPassword() end)
AccountLoginAccountEdit:HookScript("OnTextChanged", function(self) if self:GetText() ~= "" then AccountLoginAccountEditFill:Hide() else AccountLoginAccountEditFill:Show() end end)
edit("AccountLoginPasswordEdit", PASSWORD, 255)
AccountLoginPasswordEdit:SetScript("OnTabPressed", function() if AccountLoginTokenEdit:IsShown() then AccountLoginTokenEdit:SetFocus() else AccountLogin_FocusAccountName() end end)
edit("AccountLoginTokenEdit", AUTHENTICATOR, 200, true)
AccountLoginTokenEditLabel = AccountLoginTokenEdit._regions[1]; AccountLoginTokenEditLabel._name = "AccountLoginTokenEditLabel"
AccountLoginDropDown = frame("Frame", "AccountLoginDropDown", AccountLoginUI, 200, 32, true)

MOCK.addFile("Interface\\Glues\\Common\\Glue-Panel-Button-Up-Blue")
local function button(name, text, parent, hidden, onclick)
    local b = frame("Button", name, parent or AccountLoginUI, 200, 30, hidden)
    b:SetNormalTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Up-Blue"); b:GetNormalTexture():SetTexCoord(0, 0.578125, 0, 0.75)
    b:SetPushedTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Down-Blue")
    b:SetHighlightTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Highlight-Blue", "ADD")
    b:SetNormalFontObject(CreateFont("GlueFontNormal"))
    b:SetText(text)
    if onclick then b:SetScript("OnClick", onclick) end
    return b
end
button("AccountLoginLoginButton", LOGIN, nil, false, function() AccountLogin_Login() end)
AccountLoginLoginButton:SetPoint("CENTER", AccountLoginPasswordEdit, "TOP", 0, -105)
button("AccountLoginExitButton", QUIT, nil, false, function() AccountLogin_Exit() end)
button("AccountLoginTOSButton", "Terms of Use", nil, false, function() end)
AccountLoginRealmName = AccountLoginTOSButton:CreateFontString("AccountLoginRealmName", "BACKGROUND")
button("AccountLoginCreditsButton", CREDITS, nil, true, function() AccountLogin_Credits() end)
button("AccountLoginCinematicsButton", CINEMATICS, nil, true, function() end)
button("OptionsButton", "Options", nil, false, function() end)
button("AccountLoginCommunityButton", COMMUNITY_SITE, nil, false, function() AccountLogin_LaunchCommunitySite() end)
button("AccountLoginManageAccountButton", MANAGE_ACCOUNT, nil, false, function() AccountLogin_ManageAccount() end)
button("AccountLoginUpgradeAccountButton", "Upgrade", nil, true, function() end)
MOCK.addFile("Interface\\Buttons\\UI-CheckBox-Up"); MOCK.addFile("Interface\\Buttons\\UI-CheckBox-Check"); MOCK.addFile("Interface\\Buttons\\UI-CheckBox-Highlight")
AccountLoginSaveAccountName = frame("CheckButton", "AccountLoginSaveAccountName", AccountLoginUI, 24, 24)
AccountLoginSaveAccountName:SetNormalTexture("Interface\\Buttons\\UI-CheckBox-Up")
AccountLoginSaveAccountName:SetCheckedTexture("Interface\\Buttons\\UI-CheckBox-Check")
AccountLoginSaveAccountName:SetHighlightTexture("Interface\\Buttons\\UI-CheckBox-Highlight", "ADD")
local textHolder = frame("Frame", nil, AccountLoginUI)
AccountLoginSaveAccountNameText = textHolder:CreateFontString("AccountLoginSaveAccountNameText", "ARTWORK")
AccountLoginSaveAccountNameText:SetText(SAVE_ACCOUNT_NAME)
AccountLoginShowLauncher = frame("CheckButton", "AccountLoginShowLauncher", AccountLoginUI, 24, 24, true)
local launcherText = AccountLoginShowLauncher:CreateFontString(nil, "ARTWORK"); launcherText:SetText(SHOW_LAUNCHER)
ServerAlertFrame = frame("Frame", "ServerAlertFrame", AccountLoginUI, 300, 300, true)
TokenEnterDialog = frame("Frame", "TokenEnterDialog", AccountLoginUI, 300, 100, true)
VirtualKeypadFrame = frame("Frame", "VirtualKeypadFrame", AccountLoginUI, 200, 200, true)
TOSFrame = frame("Frame", "TOSFrame", AccountLogin, 600, 500, true)
TOSAccept = button("TOSAccept", "Accept", TOSFrame, false, function()
    if TOSFrame.noticeType == "EULA" then AcceptEULA() elseif TOSFrame.noticeType == "TOS" then AcceptTOS() end
    TOSFrame:Hide(); AccountLogin_ShowUserAgreements()
end)
SurveyNotificationFrame = frame("Frame", "SurveyNotificationFrame", AccountLogin, 400, 300, true)
ConnectionHelpFrame = frame("Frame", "ConnectionHelpFrame", AccountLogin, 400, 300, true)

-- AccountLogin.lua (behaviour of the stock functions)
function AccountLogin_OnLoad(self)
    TOSFrame.noticeType = "EULA"
    self:RegisterEvent("SCANDLL_ERROR")
    self:RegisterEvent("SCANDLL_FINISHED")
    local versionType, buildType, version, internalVersion, date = GetBuildInfo()
    AccountLoginVersion:SetFormattedText(VERSION_TEMPLATE, versionType, version, internalVersion, buildType, date)
    self:SetCamera(0); self:SetSequence(0)
    AccountLogin:SetModel("Interface\\Glues\\Models\\UI_MainMenu_Northrend\\UI_MainMenu_Northrend.m2")
end
function AccountLogin_OnShow(self)
    self:SetSequence(0)
    AccountLogin_ShowUserAgreements()
    local accountName = GetSavedAccountName()
    AccountLoginAccountEdit:SetText(accountName)
    AccountLoginPasswordEdit:SetText("")
    AccountLoginTokenEdit:SetText("")
    AccountLogin_SetupAccountListDDL()
    if accountName == "" then AccountLogin_FocusAccountName() else AccountLogin_FocusPassword() end
    if IsTrialAccount() then AccountLoginUpgradeAccountButton:Show() else AccountLoginUpgradeAccountButton:Hide() end
end
function AccountLogin_FocusPassword() AccountLoginPasswordEdit:SetFocus() end
function AccountLogin_FocusAccountName() AccountLoginAccountEdit:SetFocus() end
function AccountLogin_OnKeyDown(key)
    if key == "ESCAPE" then AccountLogin_Exit()
    elseif key == "ENTER" then
        if not TOSAccepted() then return elseif TOSFrame:IsShown() or ConnectionHelpFrame:IsShown() then return end
        AccountLogin_Login()
    end
end
function AccountLogin_OnEvent(event, arg1, arg2, arg3)
    if event == "SCANDLL_ERROR" then
        GlueDialog:Hide(); ScanDLLContinueAnyway(); AccountLoginUI:Show()
    end
end
function AccountLogin_Login()
    PlaySound("gsLogin")
    DefaultServerLogin(AccountLoginAccountEdit:GetText(), AccountLoginPasswordEdit:GetText())
    AccountLoginPasswordEdit:SetText("")
    if AccountLoginSaveAccountName:GetChecked() then SetSavedAccountName(AccountLoginAccountEdit:GetText()) else SetSavedAccountName(""); SetUsesToken(false) end
end
function AccountLogin_ManageAccount() PlaySound("gsLoginNewAccount"); LaunchURL(AUTH_NO_TIME_URL) end
function AccountLogin_LaunchCommunitySite() PlaySound("gsLoginNewAccount"); LaunchURL(COMMUNITY_URL) end
function AccountLogin_Credits() SetGlueScreen("credits") end
function AccountLogin_Exit() QuitGame() end
function AccountLogin_ShowUserAgreements()
    if not EULAAccepted() then
        AccountLoginUI:Hide(); TOSFrame.noticeType = "EULA"; TOSFrame:Show()
    elseif not TOSAccepted() then
        AccountLoginUI:Hide(); TOSFrame.noticeType = "TOS"; TOSFrame:Show()
    elseif not IsScanDLLFinished() then
        AccountLoginUI:Hide(); TOSFrame:Hide()
        local dllURL = ""
        if IsWindowsClient() then dllURL = SCANDLL_URL_WIN32_SCAN_DLL end
        ScanDLLStart(SCANDLL_URL_LAUNCHER_TXT, dllURL)
    else
        AccountLoginUI:Show(); TOSFrame:Hide()
    end
end
function AccountLogin_SetupAccountListDDL()
    if GetSavedAccountName() ~= "" and GetSavedAccountList() ~= "" then
        AccountLoginPasswordEdit:SetPoint("BOTTOM", 0, 239); AccountLoginLoginButton:SetPoint("BOTTOM", 0, 102); AccountLoginDropDown:Show()
    else
        AccountLoginPasswordEdit:SetPoint("BOTTOM", 0, 259); AccountLoginLoginButton:SetPoint("BOTTOM", 0, 122); AccountLoginDropDown:Hide()
    end
end
AccountLogin:SetScript("OnShow", function(self) AccountLogin_OnShow(self) end)
AccountLogin:SetScript("OnEvent", function(self, event, ...) AccountLogin_OnEvent(event, ...) end)
AccountLoginUI:SetScript("OnShow", function(self) GlueFrameFadeIn(self, 1.5) end)
AccountLogin_OnLoad(AccountLogin)

-- ------------------------------------------------------------------------------------------ CharacterCreate

MAX_RACES = 10
CharacterCreate = frame("Model", "CharacterCreate", GlueParent, 1365, 768, true)
CharacterCreate.numRaces = 0; CharacterCreate.selectedRace = 0
local raceFrame = frame("Frame", "CharacterCreateRaceFrame", CharacterCreate, 256, 512)
MOCK.addFile("Interface\\Glues\\CharacterCreate\\UI-CharacterCreate-Races")
MOCK.templates.CharacterCreateRaceButtonTemplate = function(b, name)
    b:SetSize(38, 38)
    b:SetNormalTexture("Interface\\Glues\\CharacterCreate\\UI-CharacterCreate-Races")
    b:SetPushedTexture("Interface\\Glues\\CharacterCreate\\UI-CharacterCreate-Races")
    _G[name .. "NormalTexture"] = b:GetNormalTexture()
    _G[name .. "PushedTexture"] = b:GetPushedTexture()
    _G[name .. "Text"] = b:CreateFontString(name .. "Text", "ARTWORK")
    b:SetScript("OnClick", function(self) if self.enable then CharacterRace_OnClick(self, self:GetID()) end end)
end
for i = 1, 10 do
    local b = CreateFrame("CheckButton", "CharacterCreateRaceButton" .. i, raceFrame, "CharacterCreateRaceButtonTemplate")
    b:SetID(i)
    if i == 1 then b:SetPoint("TOP", raceFrame, "TOP", -50, -61)
    elseif i == 6 then b:SetPoint("TOP", raceFrame, "TOP", 50, -61)
    else b:SetPoint("TOPLEFT", _G["CharacterCreateRaceButton" .. (i - 1)], "BOTTOMLEFT", 0, -21) end
end
CharacterCreateRaceIcon = CharacterCreate:CreateTexture("CharacterCreateRaceIcon")
CharacterCreateRaceLabel = CharacterCreate:CreateFontString("CharacterCreateRaceLabel")
CharacterCreateRaceText = CharacterCreate:CreateFontString("CharacterCreateRaceText")
CharacterCreateRaceAbilityText = CharacterCreate:CreateFontString("CharacterCreateRaceAbilityText")
RACE_ICON_TCOORDS = {
    HUMAN_MALE = { 0, 0.125, 0, 0.25 }, DWARF_MALE = { 0.125, 0.25, 0, 0.25 }, GNOME_MALE = { 0.25, 0.375, 0, 0.25 }, NIGHTELF_MALE = { 0.375, 0.5, 0, 0.25 },
    TAUREN_MALE = { 0, 0.125, 0.25, 0.5 }, SCOURGE_MALE = { 0.125, 0.25, 0.25, 0.5 }, TROLL_MALE = { 0.25, 0.375, 0.25, 0.5 }, ORC_MALE = { 0.375, 0.5, 0.25, 0.5 },
    HUMAN_FEMALE = { 0, 0.125, 0.5, 0.75 }, DWARF_FEMALE = { 0.125, 0.25, 0.5, 0.75 }, GNOME_FEMALE = { 0.25, 0.375, 0.5, 0.75 }, NIGHTELF_FEMALE = { 0.375, 0.5, 0.5, 0.75 },
    TAUREN_FEMALE = { 0, 0.125, 0.75, 1 }, SCOURGE_FEMALE = { 0.125, 0.25, 0.75, 1 }, TROLL_FEMALE = { 0.25, 0.375, 0.75, 1 }, ORC_FEMALE = { 0.375, 0.5, 0.75, 1 },
    BLOODELF_MALE = { 0.5, 0.625, 0.25, 0.5 }, BLOODELF_FEMALE = { 0.5, 0.625, 0.75, 1 },
    DRAENEI_MALE = { 0.5, 0.625, 0, 0.25 }, DRAENEI_FEMALE = { 0.5, 0.625, 0.5, 0.75 },
}
for _, f in ipairs({ "HUMAN", "DWARF", "GNOME", "NIGHTELF", "TAUREN", "SCOURGE", "TROLL", "ORC", "BLOODELF", "DRAENEI" }) do
    _G["RACE_INFO_" .. f] = "Stock text for " .. f
    _G["ABILITY_INFO_" .. f .. "1"] = "Stock racial of " .. f
end
function SetButtonDesaturated(button, desaturated) if not button then return end local icon = button:GetNormalTexture(); if icon then icon:SetDesaturated(desaturated) end end
function GetFlavorText(tag, sex)
    local primary, secondary = "", "_FEMALE"
    if sex ~= SEX_MALE then primary, secondary = "_FEMALE", "" end
    local text = _G[tag .. primary]
    if text == nil or text == "" then text = _G[tag .. secondary] end
    return text
end
function CharacterCreateEnumerateRaces(...)
    CharacterCreate.numRaces = select("#", ...) / 3
    if CharacterCreate.numRaces > MAX_RACES then message("Too many races!  Update MAX_RACES"); return end
    local gender = GetSelectedSex() == SEX_MALE and "MALE" or "FEMALE"
    local index = 1
    for i = 1, select("#", ...), 3 do
        local coords = RACE_ICON_TCOORDS[string.upper(select(i + 1, ...) .. "_" .. gender)]
        _G["CharacterCreateRaceButton" .. index .. "NormalTexture"]:SetTexCoord(coords[1], coords[2], coords[3], coords[4])
        _G["CharacterCreateRaceButton" .. index .. "PushedTexture"]:SetTexCoord(coords[1], coords[2], coords[3], coords[4])
        local button = _G["CharacterCreateRaceButton" .. index]
        button:Show()
        button.enable = select(i + 2, ...) == 1
        button.name = select(i, ...)
        button.tooltip = button.enable and select(i, ...) or _G[string.upper(select(i + 1, ...) .. "_DISABLED")]
        index = index + 1
    end
    for i = CharacterCreate.numRaces + 1, MAX_RACES do _G["CharacterCreateRaceButton" .. i]:Hide() end
end
function SetCharacterRace(id)
    CharacterCreate.selectedRace = id
    for i = 1, CharacterCreate.numRaces do
        local button = _G["CharacterCreateRaceButton" .. i]
        if i == id then _G["CharacterCreateRaceButton" .. i .. "Text"]:SetText(button.name); button:SetChecked(1)
        else _G["CharacterCreateRaceButton" .. i .. "Text"]:SetText(""); button:SetChecked(0) end
    end
    local name, faction = GetFactionForRace(CharacterCreate.selectedRace)
    local race, fileString = GetNameForRace()
    CharacterCreateRaceLabel:SetText(race)
    fileString = string.upper(fileString)
    local gender = GetSelectedSex() == SEX_MALE and "MALE" or "FEMALE"
    local coords = RACE_ICON_TCOORDS[fileString .. "_" .. gender]
    CharacterCreateRaceIcon:SetTexCoord(coords[1], coords[2], coords[3], coords[4])
    CharacterCreateRaceText:SetText(GetFlavorText("RACE_INFO_" .. string.upper(fileString), GetSelectedSex()) .. "|n|n")
    -- the racial abilities: ABILITY_INFO_<FILE>1, 2, ... up to the first missing one, above the description
    local abilities, n = {}, 1
    while _G["ABILITY_INFO_" .. fileString .. n] do abilities[#abilities + 1] = _G["ABILITY_INFO_" .. fileString .. n]; n = n + 1 end
    CharacterCreateRaceAbilityText:SetText(#abilities > 0 and table.concat(abilities, "\n\n") .. "\n\n" or "")
    local backdropColor = FACTION_BACKDROP_COLOR_TABLE[faction]
    for _, value in pairs(FRAMES_TO_BACKDROP_COLOR) do _G[value]:SetBackdropColor(backdropColor[4], backdropColor[5], backdropColor[6]) end
    SetBackgroundModel(CharacterCreate, GetCreateBackgroundModel())
end
-- Name box (CharacterCreate.xml): a 160x40 EditBox, 12 letters, BOTTOM 0,55, a NAME label above it, the
-- Randomize name button under it; Enter creates, Escape goes back.
NAME = "Name"
FACTION_BACKDROP_COLOR_TABLE = { Alliance = { 0.5, 0.5, 0.5, 0.09, 0.09, 0.19 }, Horde = { 0.5, 0.2, 0.2, 0.19, 0.05, 0.05 } }
FRAMES_TO_BACKDROP_COLOR = { "CharacterCreateNameEdit" }
GlueFontNormalLarge = CreateFont("GlueFontNormalLarge")
GlueEditBoxFont = CreateFont("GlueEditBoxFont")
CharacterCreateNameEdit = frame("EditBox", "CharacterCreateNameEdit", CharacterCreate, 160, 40)
CharacterCreateNameEdit:SetPoint("BOTTOM", CharacterCreate, "BOTTOM", 0, 55)
CharacterCreateNameEdit:SetMaxLetters(12)
CharacterCreateNameEdit:SetFontObject(GlueEditBoxFont)
CharacterCreateNameEdit:SetTextInsets(12, 0, 0, 0)
CharacterCreateNameEdit:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background", edgeFile = "Interface\\Glues\\Common\\Glue-Tooltip-Border",
                                      tile = 1, tileSize = 16, edgeSize = 16, insets = { left = 10, right = 5, top = 4, bottom = 9 } })
CharacterCreateNameEdit:SetBackdropBorderColor(0.5, 0.5, 0.5)
CharacterCreateNameEdit:SetBackdropColor(0.09, 0.09, 0.19)
local nameLabel = CharacterCreateNameEdit:CreateFontString(nil, "BACKGROUND")
nameLabel:SetFontObject(GlueFontNormalLarge); nameLabel:SetSize(160, 64); nameLabel:SetText(NAME)
nameLabel:SetPoint("BOTTOM", CharacterCreateNameEdit, "TOP", 0, -23)
CharacterCreateNameEdit:SetScript("OnEscapePressed", function() CharacterCreate_Back() end)
CharacterCreateNameEdit:SetScript("OnEnterPressed", function() CharacterCreate_Okay() end)
CharacterCreateRandomName = frame("Button", "CharacterCreateRandomName", CharacterCreate, 146, 30)
CharacterCreateRandomName:SetPoint("TOP", CharacterCreateNameEdit, "BOTTOM", 0, 7)
CharacterCreateRandomName:SetScript("OnClick", function() CharacterCreateNameEdit:SetText(GetRandomName()); PlaySound("gsCharacterCreationLook") end)
CharacterRenameEditBox = frame("EditBox", "CharacterRenameEditBox", GlueParent, 130, 32, true)
CharacterRenameEditBox:SetMaxLetters(12)
PAID_SERVICE_CHARACTER_ID = nil; PAID_SERVICE_TYPE = nil
function CharacterCreate_Okay()
    if PAID_SERVICE_TYPE then GlueDialog_Show("CONFIRM_PAID_SERVICE") else CreateCharacter(CharacterCreateNameEdit:GetText()) end
    PlaySound("gsCharacterCreationCreateChar")
end
function CharacterCreate_Back() MOCK.wentBack = true end
GlueDialogTypes["CONFIRM_PAID_SERVICE"] = { text = "Confirm", button1 = "Okay", button2 = "Cancel",
                                            OnAccept = function() CreateCharacter(CharacterCreateNameEdit:GetText()) end }

function CharacterCreate_OnShow()
    for i = 1, MAX_RACES do local button = _G["CharacterCreateRaceButton" .. i]; button:Enable(); SetButtonDesaturated(button, false) end
    if PAID_SERVICE_TYPE then
        CharacterCreateNameEdit:SetText(PaidChange_GetName())
    else
        ResetCharCustomize()
        CharacterCreateNameEdit:SetText("")
    end
    CharacterCreateEnumerateRaces(GetAvailableRaces())
    SetCharacterRace(GetSelectedRace())
    CharacterChangeFixup()
end
function CharacterChangeFixup()
    for i = 1, MAX_RACES do local f = GetFactionForRace(i) end
end
function CharacterRace_OnClick(self, id)
    if GetSelectedRace() ~= id then SetSelectedRace(id); SetCharacterRace(id); CharacterCreateEnumerateRaces(GetAvailableRaces()) end
end
function SetCharacterGender(sex)
    SetSelectedSex(sex)
    CharacterCreateEnumerateRaces(GetAvailableRaces())
    SetCharacterRace(GetSelectedRace())
end
CharacterCreate:SetScript("OnShow", function() CharacterCreate_OnShow() end)
