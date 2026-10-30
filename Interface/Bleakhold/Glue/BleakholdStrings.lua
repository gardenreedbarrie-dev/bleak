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

-- Their racials (the server's mod-bleakhold and Tools/RaceForge's races.json): CharacterCreate.lua lists every
-- ABILITY_INFO_<FILE><n> from 1 up to the first missing one above the race's description.
ABILITY_INFO_HIGHELF1 = ABILITY_INFO_HIGHELF1 or "- Wind Blessed: melee, ranged and spell haste increased by 3%."
ABILITY_INFO_HIGHELF2 = ABILITY_INFO_HIGHELF2 or "- Walk on Air: in the air, glide for 10 sec and steer it by turning."
ABILITY_INFO_EREDAR1 = ABILITY_INFO_EREDAR1 or "- Elemental Insight: damage dealt versus Elementals increased by 5%."
ABILITY_INFO_EREDAR2 = ABILITY_INFO_EREDAR2
    or "- Read Ley Line: health and mana regeneration increased by 100% for 30 sec, or 2 min while resting."

-- Character creation: the name boxes (BleakholdNames.lua).
BLEAKHOLD_FIRST_NAME = BLEAKHOLD_FIRST_NAME or "First Name"
BLEAKHOLD_LAST_NAME = BLEAKHOLD_LAST_NAME or "Last Name"

-- Character creation and the paid customization screen: the appearance rows (BleakholdCustomize.lua). The stock rows
-- keep their stock names; these name the rows Bleakhold adds when the realm's tables have marks and glowing eyes.
BLEAKHOLD_CUSTOMIZE_EYES = BLEAKHOLD_CUSTOMIZE_EYES or "Eyes"
BLEAKHOLD_CUSTOMIZE_MARKINGS = BLEAKHOLD_CUSTOMIZE_MARKINGS or "Markings"
BLEAKHOLD_CUSTOMIZE_MARK_COLOUR = BLEAKHOLD_CUSTOMIZE_MARK_COLOUR or "Mark Colour"
BLEAKHOLD_CUSTOMIZE_NO_MARKINGS = BLEAKHOLD_CUSTOMIZE_NO_MARKINGS or "No markings"
BLEAKHOLD_CUSTOMIZE_DEFAULT_EYES = BLEAKHOLD_CUSTOMIZE_DEFAULT_EYES or "Race default"
BLEAKHOLD_CUSTOMIZE_GLOWING = BLEAKHOLD_CUSTOMIZE_GLOWING or "glowing"
BLEAKHOLD_CUSTOMIZE_PAINT = BLEAKHOLD_CUSTOMIZE_PAINT or "paint"
-- The tooltip of a row: what each input does.
BLEAKHOLD_CUSTOMIZE_HINT = BLEAKHOLD_CUSTOMIZE_HINT
    or "Mouse wheel: step. Shift-click an arrow: 5 at a time. Right-click: a random one."
BLEAKHOLD_CUSTOMIZE_LOCK = BLEAKHOLD_CUSTOMIZE_LOCK or "Lock: Randomize leaves this row as it is."
-- The skin groups the row's number is coloured by (the curation's plain, marked and fel skins; glowing ones).
BLEAKHOLD_CUSTOMIZE_GROUP_MARKED = BLEAKHOLD_CUSTOMIZE_GROUP_MARKED or "Marked or tattooed"
BLEAKHOLD_CUSTOMIZE_GROUP_FEL = BLEAKHOLD_CUSTOMIZE_GROUP_FEL or "Fel"
BLEAKHOLD_CUSTOMIZE_GROUP_GLOWING = BLEAKHOLD_CUSTOMIZE_GROUP_GLOWING or "Glowing"

-- true: on a paid customization (the Appearance Artist's change at login) the name boxes are greyed out and keep the
-- character's name; the server refuses a new name there anyway (mod-bleakhold, Bleakhold.Appearance.AllowNameChange).
BLEAKHOLD_LOCK_CUSTOMIZE_NAME = BLEAKHOLD_LOCK_CUSTOMIZE_NAME ~= false
BLEAKHOLD_CUSTOMIZE_NAME_LOCKED = BLEAKHOLD_CUSTOMIZE_NAME_LOCKED or "The name stays as it is on this screen."
