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

-- A realm patch's own character creation screen in place of the stock one (custom.lua).
if SCENARIO:find("^custom") or SCENARIO == "races12-nudged" or SCENARIO == "races12-scaled" then
    dofile(HARNESS .. "/custom.lua")
    MOCK.raceGlue = assert(MOCK.raceGlues[SCENARIO], "no custom screen for " .. SCENARIO)
end

dofile(HARNESS .. "/stock.lua")
-- The stock customization rows and the option lists behind them (Bleakhold.exe's functions for the picker-* scenarios).
dofile(HARNESS .. "/customize_stock.lua")(SCENARIO)

-- A realm patch's own two-names screen (names_realm.lua): its boxes exist before the Bleakhold glue loads.
if SCENARIO:find("^names%-realm") then
    dofile(HARNESS .. "/names_realm.lua")
    MOCK.nameGlue = assert(MOCK.nameGlues[SCENARIO], "no two-names screen for " .. SCENARIO)
    MOCK.nameGlue.setup()
end
MOCK.stockCreateCharacter = CreateCharacter

-- Anchors as GetPoint lists them, to compare later.
local function anchorList(region)
    local out = {}
    for i = 1, region:GetNumPoints() do out[i] = { region:GetPoint(i) } end
    return out
end
local screenAnchors = {}
if MOCK.raceGlue then
    for i = 1, MOCK.raceGlue.count do screenAnchors[i] = anchorList(_G["CharacterCreateRaceButton" .. i]) end
end
-- The name box, the Randomize button and the realm's own second box as the screen made them.
local nameBefore = {
    first = anchorList(CharacterCreateNameEdit), firstWidth = CharacterCreateNameEdit:GetWidth(),
    firstLetters = CharacterCreateNameEdit:GetMaxLetters(), random = anchorList(CharacterCreateRandomName),
    label = select(1, CharacterCreateNameEdit:GetRegions()):GetText(), backdropList = #FRAMES_TO_BACKDROP_COLOR,
}
if MOCK.nameGlue and MOCK.nameGlue.last() then
    nameBefore.last = anchorList(MOCK.nameGlue.last())
    nameBefore.lastLetters = MOCK.nameGlue.last():GetMaxLetters()
end

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
check(#entries == 8, "TOC lists 8 files")
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

-- The client's order (CCharacterCreation::Initialize): every Alliance race, then every Horde race, by id.
local function raceList(count)
    local list = {}
    for i = 1, 5 do list[#list + 1] = STOCK[i] end
    if count >= 12 then list[#list + 1] = { name = "High Elf", file = "HighElf", faction = "Alliance" } end
    for i = 6, 10 do list[#list + 1] = STOCK[i] end
    if count >= 12 then list[#list + 1] = { name = "Eredar", file = "Eredar", faction = "Horde" } end
    if count >= 13 then list[#list + 1] = { name = "Stranger", file = "Stranger", faction = "Horde" } end
    return list
end

local function sameAnchorList(a, b)
    if #a ~= #b then return false end
    for i = 1, #a do
        for k = 1, 5 do
            local x, y = a[i][k], b[i][k]
            if type(x) == "number" then
                if not near(x, y) then return false end
            elseif x ~= y then return false end
        end
    end
    return true
end
local function describeAnchors(list)
    local out = {}
    for _, a in ipairs(list) do
        local rel = a[2] and (a[2]:GetName() or "?") or "screen"
        out[#out + 1] = string.format("%s %s %s %.2f %.2f", tostring(a[1]), rel, tostring(a[3]), a[4] or 0, a[5] or 0)
    end
    return table.concat(out, "; ")
end
local function centerX(b) local l, _, w = MOCK.rect(b); return l and l + w / 2 end
local function overlap(a, b)
    local al, ab, aw, ah = MOCK.rect(a)
    local bl, bb, bw, bh = MOCK.rect(b)
    return al < bl + bw - 0.01 and bl < al + aw - 0.01 and ab < bb + bh - 0.01 and bb < ab + ah - 0.01
end
-- Every shown race button 1..n is laid out, and no two of them cover each other.
local function checkPlacedApart(n, label)
    for i = 1, n do
        local a = _G["CharacterCreateRaceButton" .. i]
        check(MOCK.rect(a) ~= nil, label .. "button " .. i .. " is placed")
        for j = i + 1, n do
            local b = _G["CharacterCreateRaceButton" .. j]
            if MOCK.rect(a) and MOCK.rect(b) then
                check(not overlap(a, b), label .. "buttons " .. i .. " and " .. j .. " do not overlap")
            end
        end
    end
end

local function racesScenario(count, female)
    local list = raceList(count)
    MOCK.setRaces(list)
    if female then SetSelectedSex(SEX_FEMALE) end

    check(MAX_RACES >= 12, "MAX_RACES raised to 12 (" .. tostring(MAX_RACES) .. ")")
    check(CharacterCreateRaceButton11 and CharacterCreateRaceButton12, "race buttons 11 and 12 created from the stock template")
    check(CharacterCreateRaceButton12:GetID() == 12 and CharacterCreateRaceButton12NormalTexture ~= nil, "button 12 has its id and textures")
    check(RACE_ICON_TCOORDS.HIGHELF_MALE[1] == 0.5 and RACE_ICON_TCOORDS.HIGHELF_MALE[3] == 0.25, "High Elf icon = Blood Elf icon")
    check(RACE_ICON_TCOORDS.EREDAR_FEMALE[3] == 0.5, "Eredar female icon = Draenei female icon")
    check(GlueAmbienceTracks.HIGHELF == "GlueScreenBloodElf" and RaceLights.EREDAR == RaceLights.DRAENEI, "scene aliases")

    local kind = BleakholdGlue.RaceScreenKind()
    check(kind == "stock", "the stock screen is recognised: " .. tostring(kind))
    SetGlueScreen("charcreate")
    check(#MOCK.messages == 0, "no 'Too many races!' (" .. table.concat(MOCK.messages, ",") .. ")")
    check(CharacterCreate.numRaces == #list, "all races enumerated")
    checkPlacedApart(#list, "stock: ")
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
            local abilities = CharacterCreateRaceAbilityText:GetText() or ""
            local own = r.file == "HighElf" and { "Wind Blessed", "Walk on Air" } or { "Elemental Insight", "Read Ley Line" }
            check(abilities:find(own[1], 1, true) and abilities:find(own[2], 1, true), r.name .. " racials listed: " .. abilities)
            check(not abilities:find("Stock racial", 1, true), r.name .. " lists none of the template race's racials")
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

-- A realm patch's own screen (custom.lua): its buttons stay where it put them, the added ones continue the column of
-- their faction, nothing overlaps, and every race still works.
local function customScenario()
    local glue = MOCK.raceGlue
    local list = raceList(12)
    local prefix = "CharacterCreateRaceButton"
    MOCK.setRaces(list)
    local kind = BleakholdGlue.RaceScreenKind()
    check(kind == glue.kind, "screen recognised as " .. glue.kind .. ": " .. tostring(kind))
    check(MAX_RACES >= 12, "MAX_RACES raised to 12 (" .. tostring(MAX_RACES) .. ")")
    for i = 1, 12 do check(_G[prefix .. i] ~= nil, "race button " .. i .. " exists") end
    if glue.count >= 12 then
        check(_G[prefix .. 13] == nil, "a screen with twelve buttons gets none added")
        for i = 1, 12 do check(_G[prefix .. i].screenMade, "button " .. i .. " is the screen's own") end
    end

    local function verify(when)
        local label = when .. ": "
        check(#MOCK.messages == 0, label .. "no message() popups (" .. table.concat(MOCK.messages, ",") .. ")")
        check(CharacterCreate.numRaces == 12, label .. "all races enumerated")
        for i = 1, 12 do check(_G[prefix .. i]:IsShown(), label .. "race button " .. i .. " shown") end
        if glue.keepsOwn then
            for i = 1, glue.count do
                local now = anchorList(_G[prefix .. i])
                check(sameAnchorList(now, screenAnchors[i]),
                      label .. "the screen's button " .. i .. " not moved: " .. describeAnchors(now))
            end
        end
        if glue.ownLayout then
            for i = 1, 12 do
                local want, now = glue.ownLayout(i), anchorList(_G[prefix .. i])
                check(#now == 1 and sameAnchorList(now, { { want[1], _G[want[2]], want[3], want[4], want[5] } }),
                      label .. "button " .. i .. " where the screen's own code put it: " .. describeAnchors(now))
            end
        end
        checkPlacedApart(12, label)
        local leftmostHorde = math.huge
        for i, r in ipairs(list) do
            if r.faction == "Horde" then
                leftmostHorde = math.min(leftmostHorde, centerX(_G[prefix .. i]) or -math.huge)
            end
        end
        for _, i in ipairs(glue.left) do
            local x = centerX(_G[prefix .. i])
            check(x and x + _G[prefix .. i]:GetWidth() / 2 < leftmostHorde,
                  label .. "Alliance button " .. i .. " left of every Horde button")
        end
        for i, want in pairs(glue.added) do
            local now, list = anchorList(_G[prefix .. i]), {}
            for _, a in ipairs(type(want[1]) == "table" and want or { want }) do
                list[#list + 1] = { a[1], _G[a[2]], a[3], a[4], a[5] }
            end
            check(sameAnchorList(now, list),
                  label .. "added button " .. i .. " continues its column: " .. describeAnchors(now))
        end
        if glue.scale then
            for i = 1, 12 do
                local scale = _G[prefix .. i]:GetScale()
                check(near(scale, glue.scale),
                      label .. "button " .. i .. " at the screen's scale " .. glue.scale .. ": " .. scale)
            end
        end
        -- The Horde column: one step between each button, one edge.
        local c = glue.column
        local function top(i) local _, b, _, h = MOCK.rect(_G[prefix .. i]); return b + h end
        local function right(i) local l, _, w = MOCK.rect(_G[prefix .. i]); return l + w end
        local step = top(c[1]) - top(c[2])
        for k = 2, #c - 1 do
            local what = label .. "Horde column: button " .. c[k + 1]
            check(near(top(c[k]) - top(c[k + 1]), step), what .. " one step under " .. c[k])
            check(near(right(c[k + 1]), right(c[1])), what .. " on the column's edge")
        end
    end

    SetGlueScreen("charcreate")
    verify("shown")

    if glue.kind == "stock" then
        -- Laid out like the stock screen, from the offsets read back.
        local stockPitch = 38 + glue.gap
        local pitch = math.min(stockPitch, (stockPitch * 4 + 20) / 5)
        local rows = { Alliance = 0, Horde = 0 }
        for i, r in ipairs(list) do
            rows[r.faction] = rows[r.faction] + 1
            local p, rel, rp, x, y = _G[prefix .. i]:GetPoint(1)
            local wantY = glue.y - (rows[r.faction] - 1) * pitch
            check(p == "TOP" and rel == CharacterCreateRaceFrame and near(x, glue.x[r.faction]) and near(y, wantY),
                  "stock screen: button " .. i .. " in its faction's column, row " .. rows[r.faction])
        end
    end

    if glue.idAtLoad then
        for _, i in ipairs({ 11, 12 }) do
            local b = _G[prefix .. i]
            check(b.idAtLoad == i,
                  "added button " .. i .. ": its template's OnLoad saw its id (" .. tostring(b.idAtLoad) .. ")")
        end
    end

    if glue.parts then
        local model = CharacterCreateRaceButton1
        local function count(...) return select("#", ...) end
        for _, i in ipairs({ 11, 12 }) do
            local b = _G[prefix .. i]
            local name = b:GetName()
            local what = "added button " .. i
            local portrait, ring, label = _G[name .. "Portrait"], _G[name .. "Ring"], _G[name .. "Name"]
            check(portrait and ring and label, what .. " has the screen's named parts")
            check(portrait:GetParent() == b and portrait:GetTexture() ~= nil,
                  what .. ": its own portrait, filled by the screen's code")
            local _, ringTo = ring:GetPoint(1)
            check(ringTo == portrait, what .. ": the ring is centred on its own portrait")
            check(label:GetText() == list[i].name, what .. " named by the screen's code: " .. tostring(label:GetText()))
            check(b:GetWidth() == 72 and b:GetHeight() == 72, what .. " is the screen's size")
            local hover = b:GetHighlightTexture()
            check(hover and hover:GetTexture() == "Interface\\Glues\\BleakTest\\Hover",
                  what .. " has the hover texture")
            check(b:GetScript("OnClick") ~= nil, what .. " has a click script")
            -- named child frames, and their own named regions
            local selection, glow = _G[name .. "Selection"], _G[name .. "SelectionGlow"]
            local portraitModel = _G[name .. "Model"]
            check(selection and selection:GetObjectType() == "Frame" and selection:GetParent() == b,
                  what .. ": its own Selection frame")
            check(selection and selection:GetWidth() == 90 and selection:GetFrameLevel() == b:GetFrameLevel() + 2,
                  what .. ": the Selection frame's size and level")
            local p, rel = selection:GetPoint(1)
            check(p == "CENTER" and rel == portrait, what .. ": the Selection frame centred on its own portrait")
            check(glow and glow:GetParent() == selection and glow:GetTexture() == "Interface\\Glues\\BleakTest\\Glow",
                  what .. ": the Selection frame has its glow")
            check(glow and select(2, glow:GetPoint(1)) == selection, what .. ": the glow fills its own Selection frame")
            check(portraitModel and portraitModel:GetObjectType() == "Model" and portraitModel:GetParent() == b
                  and select(2, portraitModel:GetPoint(1)) == portrait, what .. ": its own portrait model")
            check(portraitModel and portraitModel:GetModel() == "Character\\" .. list[i].file .. "\\Portrait.m2",
                  what .. ": the portrait model set by the screen's code")
            if glue.parts.whole then
                check(count(b:GetRegions()) == count(model:GetRegions()),
                      what .. " has every region of the screen's buttons")
                check(count(b:GetChildren()) == count(model:GetChildren()),
                      what .. " has every child frame of the screen's buttons")
                local sparkle
                for _, child in ipairs({ b:GetChildren() }) do if child:GetName() == nil then sparkle = child end end
                check(sparkle and count(sparkle:GetRegions()) == 1 and select(2, sparkle:GetPoint(1)) == ring,
                      what .. ": the unnamed sparkle frame, on its own ring")
            end
        end
    end

    -- Every race can be picked, the Bleakhold races with their own texts.
    for i, r in ipairs(list) do
        _G[prefix .. i]:Click()
        check(GetSelectedRace() == i, r.name .. " selected by its button")
    end
    _G[prefix .. 6]:Click()
    check(CharacterCreateRaceText:GetText():find("Quel'Thalas", 1, true) ~= nil, "High Elf description shown")
    _G[prefix .. 12]:Click()
    check(CharacterCreateRaceText:GetText():find("Argus", 1, true) ~= nil, "Eredar description shown")
    if glue.parts then
        for i = 1, 12 do
            check((_G[prefix .. i .. "Selection"]:IsShown() ~= nil) == (i == 12),
                  "the screen's code shows only button 12's selection: " .. i)
        end
    end
    verify("after clicks")
    SetCharacterGender(SEX_FEMALE)
    verify("after a gender switch")
    SetGlueScreen("login"); SetGlueScreen("charcreate")
    verify("shown again")
    check(#BLEAKHOLD_GLUE_ERRORS == 0, "no caught errors: " .. table.concat(BLEAKHOLD_GLUE_ERRORS, " | "))
end

-- ------------------------------------------------------------------------------------------------ names

-- The edit boxes among CharacterCreate's frames, at any depth.
local function screenEditBoxes()
    local out = {}
    local function walk(f)
        if f:GetObjectType() == "EditBox" then out[#out + 1] = f end
        for _, c in ipairs({ f:GetChildren() }) do walk(c) end
    end
    walk(CharacterCreate)
    return out
end

local function lastLog()
    return BLEAKHOLD_GLUE_LOG[#BLEAKHOLD_GLUE_LOG] or ""
end

local function namesScenario()
    local first = CharacterCreateNameEdit
    MOCK.setRaces({ STOCK[1], { name = "High Elf", file = "HighElf", faction = "Alliance" }, STOCK[6] })

    if SCENARIO == "names-off" then
        check(BleakholdLastNameEdit == nil, "off: no last name box")
        check(BleakholdGlue.namesPath == "off" and lastLog():find("names: off", 1, true), "off: the path is logged: " .. lastLog())
        SetGlueScreen("charcreate")
        check(BleakholdLastNameEdit == nil, "off: still no last name box once shown")
        first:SetText("Arthas")
        CharacterCreate_Okay()
        check(MOCK.created[1] == "Arthas", "off: stock name passed on")
        return
    end

    -- Nothing is added before the screen first shows: that show decides.
    check(BleakholdGlue.namesPath == "waiting", "waits for the screen's first show: " .. tostring(BleakholdGlue.namesPath))
    check(BleakholdLastNameEdit == nil and CreateCharacter == MOCK.stockCreateCharacter, "nothing added before it shows")
    check(CharacterRenameEditBox:GetMaxLetters() == 25, "rename box takes a full name")

    if SCENARIO == "names-paid" then
        PAID_SERVICE_TYPE = 1; PAID_SERVICE_CHARACTER_ID = 3
        MOCK.paidName = "Christopher Ravencrest"
    end
    SetGlueScreen("charcreate")
    local last = BleakholdLastNameEdit
    check(BleakholdGlue.namesPath == "bleakhold", "stock screen: Bleakhold's boxes: " .. tostring(BleakholdGlue.namesPath))
    check(lastLog():find("names: bleakhold", 1, true) ~= nil, "the path is logged: " .. lastLog())
    check(BleakholdGlue.ScreenSecondNameBox() == nil, "Bleakhold's own box and label never count as the screen's: "
          .. tostring(BleakholdGlue.ScreenSecondNameBox()))

    check(last ~= nil and last:GetObjectType() == "EditBox", "last name box created")
    check(#screenEditBoxes() == 2, "two name boxes on the screen: " .. #screenEditBoxes())
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

    if SCENARIO == "names-paid" then
        check(first:GetText() == "Christopher" and last:GetText() == "Ravencrest", "paid change splits the character's name")
        CharacterCreate_Okay()
        GlueDialog_OnClick(1)
        check(MOCK.created[1] == "Christopher Ravencrest", "paid change confirmation sends the full name: " .. tostring(MOCK.created[1]))
        MOCK.paidName = "Jaina"
        SetGlueScreen("login"); SetGlueScreen("charcreate")
        check(first:GetText() == "Jaina" and last:GetText() == "", "single paid name: empty last name")
        return
    end

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

-- A realm patch's own two-names screen (names_realm.lua): Bleakhold adds no box, moves and restyles none of the
-- screen's, and the name the screen's own code builds reaches CreateCharacter unchanged.
local function realmNamesScenario()
    local glue = MOCK.nameGlue
    local first = CharacterCreateNameEdit
    MOCK.setRaces({ STOCK[1], { name = "High Elf", file = "HighElf", faction = "Alliance" }, STOCK[6] })
    check(BleakholdGlue.namesPath == "waiting", "waits for the screen's first show: " .. tostring(BleakholdGlue.namesPath))

    local function untouched(when)
        local label = when .. ": "
        check(BleakholdGlue.namesPath == "realm", label .. "the realm's path: " .. tostring(BleakholdGlue.namesPath))
        check(tostring(BleakholdGlue.namesWhy):find(glue.why) ~= nil, label .. "found by " .. glue.why .. ": "
              .. tostring(BleakholdGlue.namesWhy))
        check(BleakholdLastNameEdit == nil and BleakholdNameAnchor == nil and BleakholdLastNameEditLabel == nil,
              label .. "no Bleakhold box, anchor or label")
        local boxes = screenEditBoxes()
        local inScreen = glue.last():GetParent() ~= GlueParent
        check(#boxes == (inScreen and 2 or 1), label .. "one set of name boxes: " .. #boxes .. " edit boxes on the screen")
        check(sameAnchorList(anchorList(first), nameBefore.first), label .. "first name box not moved: "
              .. describeAnchors(anchorList(first)))
        check(first:GetWidth() == nameBefore.firstWidth and first:GetMaxLetters() == nameBefore.firstLetters,
              label .. "first name box keeps its size and letters")
        check(select(1, first:GetRegions()):GetText() == nameBefore.label, label .. "its label stays the screen's: "
              .. tostring(select(1, first:GetRegions()):GetText()))
        check(sameAnchorList(anchorList(glue.last()), nameBefore.last), label .. "the screen's last name box not moved")
        check(glue.last():GetMaxLetters() == nameBefore.lastLetters, label .. "the screen's last name box keeps its letters")
        check(sameAnchorList(anchorList(CharacterCreateRandomName), nameBefore.random), label .. "Randomize not moved")
        check(#FRAMES_TO_BACKDROP_COLOR == nameBefore.backdropList, label .. "the backdrop colour list is the screen's")
        check(CreateCharacter == MOCK.stockCreateCharacter, label .. "CreateCharacter is not wrapped")
    end

    SetGlueScreen("charcreate")
    -- (a box the screen's OnShow makes exists only now: its anchors are the ones it was made with)
    check(glue.last() ~= nil, "the screen's own last name box exists")
    nameBefore.last = nameBefore.last or anchorList(glue.last())
    nameBefore.lastLetters = nameBefore.lastLetters or glue.last():GetMaxLetters()
    untouched("shown")
    check(lastLog():find("names: realm", 1, true) ~= nil, "the path is logged: " .. lastLog())

    -- The screen's own code builds the name.
    first:SetText("Arthas"); glue.last():SetText("Menethil")
    CharacterCreate_Okay()
    check(MOCK.created[#MOCK.created] == "Arthas Menethil", "the screen's code sends First Last: "
          .. tostring(MOCK.created[#MOCK.created]))
    first:SetText("Jaina"); glue.last():SetText("")
    CharacterCreate_Okay()
    check(MOCK.created[#MOCK.created] == "Jaina", "a single name passes as it is: " .. tostring(MOCK.created[#MOCK.created]))
    MOCK.type(first, " Proudmoore")
    check(first:GetText():sub(1, 6) == "Jaina " and glue.last():GetText() == "",
          "typing is not split into the screen's boxes: " .. first:GetText() .. "|" .. glue.last():GetText())
    glue.last():SetText("Kept")
    CharacterCreateRandomName:Click()
    check(first:GetText() == "Arannis" and glue.last():GetText() == "Kept", "Randomize does only what the screen does")

    SetGlueScreen("login"); SetGlueScreen("charcreate")
    untouched("shown again")
    SetCharacterGender(SEX_FEMALE)
    check(#BLEAKHOLD_GLUE_ERRORS == 0, "no caught errors: " .. table.concat(BLEAKHOLD_GLUE_ERRORS, " | "))
    check(#MOCK.collisions == 0, "no global name collisions: " .. table.concat(MOCK.collisions, ", "))
end

local ok, err = pcall(function()
    if SCENARIO == "login-classic" then classicScenario()
    elseif SCENARIO:find("^login") then loginScenario()
    elseif MOCK.nameGlue then realmNamesScenario()
    elseif SCENARIO:find("^names") then namesScenario()
    elseif SCENARIO:find("^picker") then
        -- the appearance rows (BleakholdCustomize.lua): Tools/UiLint/tests/test_customize_glue.lua
        dofile(HARNESS .. "/../tests/test_customize_glue.lua")({ check = check, scenario = SCENARIO, harness = HARNESS })
    elseif SCENARIO == "races12" then racesScenario(12)
    elseif SCENARIO == "races12-female" then racesScenario(12, true)
    elseif SCENARIO == "races10" then racesScenario(10)
    elseif SCENARIO == "races13" then racesScenario(13)
    elseif SCENARIO == "races12-noart" then racesScenario(12)
    elseif MOCK.raceGlue then customScenario()
    else error("unknown scenario " .. SCENARIO) end
end)
check(ok, "scenario ran to the end" .. (ok and "" or (": " .. tostring(err))))
print(string.format("%-24s %3d checks, %d failed", SCENARIO, checks, failures))
if failures > 0 then host_exit(1) end
