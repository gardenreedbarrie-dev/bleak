-- Copyright (c) 2026 NeticSoul. Licensed under the MIT License; see LICENSE.

-- ============================================================================
-- AddicatUI - Centralized Font System
-- Single source of truth for locale-aware font selection.
-- Loaded early (via AddicatUI.xml) so config.lua, database.lua, and all modules
-- can reference addon.Fonts instead of hardcoding font paths.
-- ============================================================================
--
-- WoW 3.3.5a ships different fonts per locale:
--   enUS/deDE/frFR/esES/esMX/ptBR : Fonts\FRIZQT__.TTF  + Fonts\ARIALN.TTF
--   ruRU                           : Fonts\FRIZQT__.TTF (the ruRU build carries Cyrillic)
--   koKR                           : Fonts\2002.TTF (Korean CJK glyphs)
--   zhCN                           : Fonts\ZYKai_T.TTF (Simplified Chinese)
--   zhTW                           : Fonts\bLEI00D.TTF (Traditional Chinese)
--
-- Custom fonts (expressway.ttf, PTSansNarrow.ttf) cover Latin-1, Eastern European
-- and Cyrillic, but carry no CJK glyphs. This module selects the correct system
-- font for each locale, falling back to the custom font when safe.
-- ============================================================================

local addon = select(2, ...)

local _locale = GetLocale()

-- ============================================================================
-- FONT TABLES PER LOCALE
-- ============================================================================

-- CJK/Cyrillic font map: locale -> system font that contains the required glyphs
local LOCALE_SYSTEM_FONTS = {
    koKR = "Fonts\\2002.TTF",
    zhCN = "Fonts\\ZYKai_T.TTF",
    zhTW = "Fonts\\bLEI00D.TTF",
    -- FRIZQT___CYR.TTF only exists from Cataclysm on; SetFont with it fails on a 3.3.5a ruRU client.
    ruRU = "Fonts\\FRIZQT__.TTF",
}

-- Only CJK is beyond the bundled fonts; forcing the client font on ruRU would strip the
-- Latin accents every other shipped language needs, so ruRU is deliberately absent here.
local LOCALE_CJK_FONTS = {
    koKR = LOCALE_SYSTEM_FONTS.koKR,
    zhCN = LOCALE_SYSTEM_FONTS.zhCN,
    zhTW = LOCALE_SYSTEM_FONTS.zhTW,
}

-- Does this locale need a system font instead of custom Latin-only fonts?
local _needsSystemFont = (LOCALE_SYSTEM_FONTS[_locale] ~= nil)

-- ============================================================================
-- RESOLVED FONT PATHS
-- ============================================================================

local Fonts = {}

--- Primary UI font (unit frames, tooltips, game menu, general text).
-- Uses FRIZQT__.TTF on Latin locales, locale-specific font on CJK/Cyrillic.
Fonts.PRIMARY = LOCALE_SYSTEM_FONTS[_locale] or "Fonts\\FRIZQT__.TTF"

--- Action bar font (hotkeys, macros, cooldowns, page numbers).
-- Uses expressway.ttf on Latin and Cyrillic locales for a modern Dragonflight look,
-- falls back to the locale system font on CJK. The Bleakhold theme swaps it (see SetStyle).
Fonts.ACTIONBAR = LOCALE_CJK_FONTS[_locale]
    or [[Interface\AddOns\AddicatUI_Art\Fonts\expressway.ttf]]

--- Narrow UI font (options panel, editor mode labels).
-- PTSansNarrow.ttf on Latin and Cyrillic locales, locale system font on CJK.
Fonts.NARROW = LOCALE_CJK_FONTS[_locale]
    or [[Interface\AddOns\AddicatUI_Options\fonts\PTSansNarrow.ttf]]

--- ARIALN replacement: used where database defaults previously hardcoded ARIALN.
-- On Latin locales ARIALN is fine; on CJK/Cyrillic we substitute the system font.
Fonts.ARIALN = LOCALE_SYSTEM_FONTS[_locale] or "Fonts\\ARIALN.TTF"

--- Whether the current locale requires a system font (CJK or Cyrillic).
Fonts.needsSystemFont = _needsSystemFont

--- The raw locale string (e.g. "enUS", "koKR").
Fonts.locale = _locale

--- Title font (window and menu headers). PRIMARY on the classic look.
Fonts.TITLE = Fonts.PRIMARY

-- ============================================================================
-- THEME STYLES
-- ============================================================================

-- The Bleakhold theme (modules/bleaktheme.lua) draws with the client's own faces, the ones the
-- Bleakhold addon uses: FRIZQT__ body, ARIALN narrow, MORPHEUS titles. CJK and ruRU keep their
-- system font, so every style has the glyphs it needs.
local STYLES = {
    classic = {
        ACTIONBAR = Fonts.ACTIONBAR,
        NARROW = Fonts.NARROW,
        TITLE = Fonts.PRIMARY,
    },
    bleakhold = {
        ACTIONBAR = Fonts.ARIALN,
        NARROW = Fonts.ARIALN,
        TITLE = LOCALE_SYSTEM_FONTS[_locale] or "Fonts\\MORPHEUS.TTF",
    },
}

--- Active style ("classic" until the theme module reads the profile).
Fonts.style = "classic"

--- Point ACTIONBAR, NARROW and TITLE at a style's faces ("bleakhold" or "classic").
-- Text picks these up when it is built, so text that already exists keeps its face until /reload.
function Fonts.SetStyle(style)
    if not STYLES[style] then
        style = "classic"
    end
    local set = STYLES[style]
    Fonts.ACTIONBAR, Fonts.NARROW, Fonts.TITLE = set.ACTIONBAR, set.NARROW, set.TITLE
    Fonts.style = style
end

-- ============================================================================
-- EXPORT
-- ============================================================================

addon.Fonts = Fonts
