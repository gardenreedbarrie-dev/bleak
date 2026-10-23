-- Bleakhold glue: strings and settings. Loaded after the stock GlueXML, so anything set here overrides the
-- stock value (see BleakholdGlue.toc).

-- Links on the login screen. LaunchURL opens them in the system browser.
BLEAKHOLD_URL = "https://bleakhold.com"
BLEAKHOLD_URL_TEXT = "bleakhold.com"
BLEAKHOLD_ACCOUNT_URL = BLEAKHOLD_URL
BLEAKHOLD_COMMUNITY_URL = BLEAKHOLD_URL

BLEAKHOLD_SUBTITLE = "Wrath of the Lich King Extra"

-- "classic": the stock login screen with its 3D scene and form, which a login patch restyles (WoW Forever's
-- patch-J.MPQ puts the old Dark Portal there); Bleakhold only hides the Blizzard account buttons. "bleakhold":
-- the Bleakhold painting, logo and form.
BLEAKHOLD_LOGIN_SCREEN = "classic"

-- true: character creation has a First Name and a Last Name box (the server's mod-two-names accepts "First
-- Last"); false: the stock single name box.
BLEAKHOLD_TWO_NAMES = true

-- true: accept the stock EULA, Terms of Use and the other agreement screens without showing them. The login
-- itself needs the EULA and the Terms of Use accepted (CGlueMgr::LoginServerLogin); with false the stock
-- agreement screen asks once, as before.
BLEAKHOLD_AUTO_ACCEPT_AGREEMENTS = false

-- true: the Login button stays disabled until both the account name and the password have text.
BLEAKHOLD_LOGIN_NEEDS_INPUT = true

local locale = GetLocale and GetLocale() or "enUS"

if locale == "enUS" or locale == "enGB" then
    BLEAKHOLD_REMEMBER_ACCOUNT = "Remember account name"

    -- Shown by CGlueMgr::DisplayLoginStatus, which reads the string by its global name. The usual cores
    -- answer a wrong password with the unknown-account result, so both say the same.
    LOGIN_UNKNOWN_ACCOUNT = "The account name or password is incorrect. Check both and try again, or reset your password on bleakhold.com."
    LOGIN_INCORRECT_PASSWORD = LOGIN_UNKNOWN_ACCOUNT
end

-- Character creation: the Bleakhold races. CharacterCreate.lua reads RACE_INFO_<FILE> (and an optional
-- RACE_INFO_<FILE>_FEMALE), <FILE>_DISABLED for the tooltip of a race the account cannot play, and optional
-- ABILITY_INFO_<FILE>1, 2, ... lines.
RACE_INFO_HIGHELF = RACE_INFO_HIGHELF or "When Silvermoon turned to fel magic to feed its hunger, not every elf of Quel'Thalas followed. The high elves kept the old ways and the old oaths, and stood with the Alliance that their ancestors helped to found. Few in number and proud of it, they fight with bow, blade and the disciplined arcane arts of a people who refuse to become what their kin have chosen."
HIGHELF_DISABLED = HIGHELF_DISABLED or "Your account cannot create a High Elf."
RACE_INFO_EREDAR = RACE_INFO_EREDAR or "Not every eredar who stayed on Argus bowed to Sargeras. Some broke from the Legion on their own terms, trusting neither the naaru nor their draenei kin. The Horde, which knows the price of fel power better than most, judges them by their deeds rather than their blood, and the exiles have repaid that trust with iron discipline and a hard-won mastery of their own strength."
EREDAR_DISABLED = EREDAR_DISABLED or "Your account cannot create an Eredar."

-- Character creation: the name boxes (BleakholdNames.lua).
BLEAKHOLD_FIRST_NAME = BLEAKHOLD_FIRST_NAME or "First Name"
BLEAKHOLD_LAST_NAME = BLEAKHOLD_LAST_NAME or "Last Name"
