-- Copyright (c) 2026 NeticSoul. Licensed under the MIT License; see LICENSE.

--[[
================================================================================
AddicatUI Options - Core
================================================================================
This file provides the options registration system and initialization.
Inspired by the ElvUI_OptionsUI pattern - accesses AddicatUI addon via global.
================================================================================
]]

-- Access the main AddicatUI addon (exposed globally in AddicatUI/core.lua)
local addon = AddicatUI

-- Initialize localization before any fallback/error path uses it.
-- Load-on-demand, so unlike AddicatUI/config.lua this always sees the stored override.
local activeLocale = addon and addon.GetActiveLocale and addon.GetActiveLocale()
local L = LibStub("AceLocale-3.0-AddicatUI"):GetLocale("AddicatUI", activeLocale)
local LO = LibStub("AceLocale-3.0-AddicatUI"):GetLocale("AddicatUI_Options", activeLocale)

if not addon then
    print("|cFFFF0000[AddicatUI_Options]|r " .. ((LO and LO["Error: AddicatUI addon not found!"]) or "Error: AddicatUI addon not found!"))
    return
end

addon.LO = LO  -- Expose for other option files

-- ============================================================================
-- STATIC POPUP FOR RELOAD
-- ============================================================================

StaticPopupDialogs["ADDICATUI_RELOAD_UI"] = {
    text = LO["Changing this setting requires a UI reload to apply correctly."],
    button1 = LO["Reload UI"],
    button2 = LO["Not Now"],
    OnAccept = function()
        ReloadUI()
    end,
    timeout = 0,
    whileDead = 1,
    hideOnEscape = 1,
    preferredIndex = 3
}

StaticPopupDialogs["ADDICATUI_DELETE_PROFILE"] = {
    text = LO["Are you sure you want to delete the profile '%s'? This cannot be undone."],
    button1 = LO["Delete"],
    button2 = LO["Not Now"],
    OnAccept = function(self)
        local profileName = self.data
        if profileName and addon.db then
            addon.db:DeleteProfile(profileName, true)
            -- Left set, the next new character would recreate it empty.
            if addon.GetDefaultProfileKey and addon:GetDefaultProfileKey() == profileName then
                addon:SetDefaultProfileKey(nil)
            end
            addon:Print((LO["Deleted profile: "] or "Deleted profile: ") .. profileName)
            if addon.OptionsPanel then
                addon.OptionsPanel:SelectTab("profiles")
            end
        end
    end,
    timeout = 0,
    whileDead = 1,
    hideOnEscape = 1,
    preferredIndex = 3
}

-- ============================================================================
-- INITIALIZE OPTIONS (called after all option files are loaded)
-- ============================================================================

function addon:InitializeOptions()
    -- Register a minimal BlizzOptions entry that redirects to the custom panel
    addon.Options.args.open_panel = {
        type = "execute",
        name = "|cff1784d1" .. (LO["Open AddicatUI Settings"] or "Open AddicatUI Settings") .. "|r",
        desc = LO["Open the AddicatUI configuration panel."] or "Open the AddicatUI configuration panel.",
        func = function()
            local AceConfigDialog = LibStub("AceConfigDialog-3.0")
            if AceConfigDialog then
                AceConfigDialog:Close("AddicatUI")
            end
            if addon.OptionsPanel then
                addon.OptionsPanel:Toggle()
            end
        end,
        order = 1,
        width = "full"
    }
    addon.Options.args.info = {
        type = "description",
        name = "\n" .. (LO["Use /addicatui to open the full settings panel."] or "Use /addicatui to open the full settings panel."),
        order = 2
    }

    LibStub("AceConfig-3.0"):RegisterOptionsTable("AddicatUI", addon.Options)
    LibStub("AceConfigDialog-3.0"):AddToBlizOptions("AddicatUI", "AddicatUI")

    addon.OptionsLoaded = true
end

-- Initialize when this addon finishes loading
local initFrame = CreateFrame("Frame")
initFrame:RegisterEvent("ADDON_LOADED")
initFrame:SetScript("OnEvent", function(self, event, loadedAddon)
    if loadedAddon == "AddicatUI_Options" then
        addon:InitializeOptions()
        self:UnregisterAllEvents()
    end
end)
