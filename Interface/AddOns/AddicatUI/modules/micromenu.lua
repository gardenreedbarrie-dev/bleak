-- Copyright (c) 2026 NeticSoul. Licensed under the MIT License; see LICENSE.
-- Portions adapted from DragonflightUI (MIT, (c) 2022 Karl-HeinzSchneider); see THIRD_PARTY_NOTICES.

local addon = select(2, ...)
local config = addon.config
local L = addon.L

-- ============================================================================
-- SERVER DETECTION & MODULE STATE
-- ============================================================================

-- Detect if we are on an Ascension server by checking for one of its custom buttons.
-- This is the most reliable method.
local isAscensionServer = (_G.PathToAscensionMicroButton ~= nil)

local MicromenuModule = {
    initialized = false,
    applied = false,
    originalStates = {}, -- Store original states for restoration
    registeredEvents = {}, -- Track registered events
    hooks = {}, -- Track hooked functions
    stateDrivers = {}, -- Track state drivers
    frames = {}, -- Track created frames
    eventFrames = {} -- Track event handler frames
}

-- Register with ModuleRegistry (if available)
if addon.RegisterModule then
    addon:RegisterModule("micromenu", MicromenuModule,
        addon.L["Micro Menu"],
        addon.L["Micro menu and bags system styling and positioning"])
end

-- ============================================================================
-- CONFIGURATION FUNCTIONS
-- ============================================================================

local function IsModuleEnabled()
    return addon:IsModuleEnabled("micromenu")
end

local function GetLFGTooltipPosition()
    local pos = addon.db and addon.db.profile and addon.db.profile.widgets and addon.db.profile.widgets.lfgframe
        and addon.db.profile.widgets.lfgframe.tooltip_position
    if pos == "TOP" or pos == "BOTTOM" or pos == "LEFT" or pos == "RIGHT" then
        return pos
    end
    return "TOP"
end

local function GetLFDStatusAnchorSpec(position)
    if position == "BOTTOM" then
        return "TOP", "BOTTOM", 0, -30
    elseif position == "LEFT" then
        return "RIGHT", "LEFT", -24, 0
    elseif position == "RIGHT" then
        return "LEFT", "RIGHT", 24, 0
    end

    -- Default/current behavior.
    return "BOTTOM", "TOP", 0, 30
end

-- ============================================================================
-- SECTION 1: LOCALS AND CONSTANTS
-- ============================================================================

local pairs, gsub, hooksecurefunc = pairs, string.gsub, hooksecurefunc
local _G, UIParent = _G, UIParent

-- Performance constants
local PERFORMANCEBAR_LOW_LATENCY = 200;
local PERFORMANCEBAR_MEDIUM_LATENCY = 300;

local MainMenuBarBackpackButton, HelpMicroButton, KeyRingButton =
    _G.MainMenuBarBackpackButton, _G.HelpMicroButton, _G.KeyRingButton

local function SyncKeyRingToKeys()
    if not KeyRingButton then return end
    local wanted = HasKey() and true or false
    local shown = KeyRingButton:IsShown() and true or false
    if wanted ~= shown then
        if wanted then
            KeyRingButton:Show()
        else
            KeyRingButton:Hide()
        end
    end
end

local function MicroButtonFor(stem)
    return _G[stem .. "MicroButton"]
end

local EIGHTH_STEM, NINTH_STEM = "Collections", "PVP"
if isAscensionServer then
    EIGHTH_STEM, NINTH_STEM = "PathToAscension", "Challenges"
end

-- One button for another addon's windows, with a flyout listing them (Bleakhold registers its launcher through
-- addon.RegisterMicroMenuLauncher). MICRO_BUTTONS is captured below, so it exists from the start and stays
-- suppressed, out of the strip, until a launcher is registered and the option allows it.
local launcherButton = CreateFrame("Button", "AddicatUI_LauncherMicroButton", UIParent)
launcherButton:SetSize(32, 40)
launcherButton:SetPoint("CENTER")
launcherButton:Hide()
launcherButton.addicatUISuppressed = true
-- layoutMicroButtons re-points these; the highlight one carries the glyph, the others stay empty.
launcherButton:SetNormalTexture("")
launcherButton:SetPushedTexture("")
launcherButton:SetHighlightTexture("")
launcherButton:RegisterForClicks("LeftButtonUp")

-- A nil slot for a button missing at load keeps # at the full count; Professions follows Character, as in
-- Forever. The launcher sits after the stock panels, before the game menu.
local MICRO_BUTTONS = {
    MicroButtonFor("Character"), MicroButtonFor("Profession"), MicroButtonFor("Spellbook"), MicroButtonFor("Talent"),
    MicroButtonFor("Achievement"), MicroButtonFor("QuestLog"), MicroButtonFor("Socials"),
    MicroButtonFor("LFD"), MicroButtonFor(EIGHTH_STEM), MicroButtonFor(NINTH_STEM), launcherButton,
    MicroButtonFor("MainMenu"), (MicroButtonFor("Help")),
}


-- The strip's default anchor allows for an eleventh button, which Pets & Mounts now supplies.
local function HasCollectionsButton()
    return _G.CollectionsMicroButton ~= nil
end

local bagslots = {_G.CharacterBag0Slot, _G.CharacterBag1Slot, _G.CharacterBag2Slot, _G.CharacterBag3Slot};

-- State tracking
local originalBlizzardHandlers = {}
local MainMenuMicroButtonMixin = {};

-- ============================================================================
-- SECTION 2: ATLAS COORDINATES
-- ============================================================================

local MicromenuAtlas = {
    ["UI-HUD-MicroMenu-Achievements-Disabled"] = {0.000976562, 0.0634766, 0.00195312, 0.162109},
    ["UI-HUD-MicroMenu-Achievements-Down"] = {0.000976562, 0.0634766, 0.166016, 0.326172},
    ["UI-HUD-MicroMenu-Achievements-Mouseover"] = {0.000976562, 0.0634766, 0.330078, 0.490234},
    ["UI-HUD-MicroMenu-Achievements-Up"] = {0.000976562, 0.0634766, 0.494141, 0.654297},

    ["UI-HUD-MicroMenu-GameMenu-Disabled"] = {0.129883, 0.192383, 0.330078, 0.490234},
    ["UI-HUD-MicroMenu-GameMenu-Down"] = {0.129883, 0.192383, 0.494141, 0.654297},
    ["UI-HUD-MicroMenu-GameMenu-Mouseover"] = {0.129883, 0.192383, 0.658203, 0.818359},
    ["UI-HUD-MicroMenu-GameMenu-Up"] = {0.129883, 0.192383, 0.822266, 0.982422},

    ["UI-HUD-MicroMenu-Groupfinder-Disabled"] = {0.194336, 0.256836, 0.00195312, 0.162109},
    ["UI-HUD-MicroMenu-Groupfinder-Down"] = {0.194336, 0.256836, 0.166016, 0.326172},
    ["UI-HUD-MicroMenu-Groupfinder-Mouseover"] = {0.194336, 0.256836, 0.330078, 0.490234},
    ["UI-HUD-MicroMenu-Groupfinder-Up"] = {0.194336, 0.256836, 0.494141, 0.654297},

    ["UI-HUD-MicroMenu-GuildCommunities-Disabled"] = {0.194336, 0.256836, 0.658203, 0.818359},
    ["UI-HUD-MicroMenu-GuildCommunities-Down"] = {0.194336, 0.256836, 0.822266, 0.982422},
    ["UI-HUD-MicroMenu-GuildCommunities-Mouseover"] = {0.258789, 0.321289, 0.658203, 0.818359},
    ["UI-HUD-MicroMenu-GuildCommunities-Up"] = {0.258789, 0.321289, 0.822266, 0.982422},

    ["UI-HUD-MicroMenu-Questlog-Disabled"] = {0.323242, 0.385742, 0.494141, 0.654297},
    ["UI-HUD-MicroMenu-Questlog-Down"] = {0.323242, 0.385742, 0.658203, 0.818359},
    ["UI-HUD-MicroMenu-Questlog-Mouseover"] = {0.323242, 0.385742, 0.822266, 0.982422},
    ["UI-HUD-MicroMenu-Questlog-Up"] = {0.387695, 0.450195, 0.00195312, 0.162109},

    ["UI-HUD-MicroMenu-SpecTalents-Disabled"] = {0.387695, 0.450195, 0.822266, 0.982422},
    ["UI-HUD-MicroMenu-SpecTalents-Down"] = {0.452148, 0.514648, 0.00195312, 0.162109},
    ["UI-HUD-MicroMenu-SpecTalents-Mouseover"] = {0.452148, 0.514648, 0.166016, 0.326172},
    ["UI-HUD-MicroMenu-SpecTalents-Up"] = {0.452148, 0.514648, 0.330078, 0.490234},

    ["UI-HUD-MicroMenu-SpellbookAbilities-Disabled"] = {0.452148, 0.514648, 0.494141, 0.654297},
    ["UI-HUD-MicroMenu-SpellbookAbilities-Down"] = {0.452148, 0.514648, 0.658203, 0.818359},
    ["UI-HUD-MicroMenu-SpellbookAbilities-Mouseover"] = {0.452148, 0.514648, 0.822266, 0.982422},
    ["UI-HUD-MicroMenu-SpellbookAbilities-Up"] = {0.516602, 0.579102, 0.00195312, 0.162109},

    ["UI-HUD-MicroMenu-Shop-Disabled"] = {0.387695, 0.450195, 0.166016, 0.326172},
    ["UI-HUD-MicroMenu-Shop-Down"] = {0.387695, 0.450195, 0.494141, 0.654297},
    ["UI-HUD-MicroMenu-Shop-Mouseover"] = {0.387695, 0.450195, 0.330078, 0.490234},
    ["UI-HUD-MicroMenu-Shop-Up"] = {0.387695, 0.450195, 0.658203, 0.818359}
}

-- Add server-specific atlas data
if isAscensionServer then
    MicromenuAtlas["UI-HUD-MicroMenu-Challenges-Disabled"] = {0.000976562, 0.0634766, 0.658203, 0.818359}
    MicromenuAtlas["UI-HUD-MicroMenu-Challenges-Down"] = {0.000976562, 0.0634766, 0.822266, 0.982422}
    MicromenuAtlas["UI-HUD-MicroMenu-Challenges-Mouseover"] = {0.0654297, 0.12793, 0.00195312, 0.162109}
    MicromenuAtlas["UI-HUD-MicroMenu-Challenges-Up"] = {0.0654297, 0.12793, 0.166016, 0.326172}
    MicromenuAtlas["UI-HUD-MicroMenu-PathToAscension-Disabled"] = {0.0654297, 0.12793, 0.658203, 0.818359}
    MicromenuAtlas["UI-HUD-MicroMenu-PathToAscension-Down"] = {0.0654297, 0.12793, 0.822266, 0.982422}
    MicromenuAtlas["UI-HUD-MicroMenu-PathToAscension-Mouseover"] = {0.129883, 0.192383, 0.00195312, 0.162109}
    MicromenuAtlas["UI-HUD-MicroMenu-PathToAscension-Up"] = {0.129883, 0.192383, 0.166016, 0.326172}
else
    MicromenuAtlas["UI-HUD-MicroMenu-Collections-Disabled"] = {0.0654297, 0.12793, 0.658203, 0.818359}
    MicromenuAtlas["UI-HUD-MicroMenu-Collections-Down"] = {0.0654297, 0.12793, 0.822266, 0.982422}
    MicromenuAtlas["UI-HUD-MicroMenu-Collections-Mouseover"] = {0.129883, 0.192383, 0.00195312, 0.162109}
    MicromenuAtlas["UI-HUD-MicroMenu-Collections-Up"] = {0.129883, 0.192383, 0.166016, 0.326172}
end

-- The fifth field names the file: AddicatUI's colour sheet predates the professions icon.
local PROFESSIONS_MICRO = 'Interface\\AddOns\\AddicatUI_Art\\Textures\\Professions\\MicroButton'
MicromenuAtlas["UI-HUD-MicroMenu-Professions-Up"] = {0, 0.25, 0, 0.3203125, PROFESSIONS_MICRO}
MicromenuAtlas["UI-HUD-MicroMenu-Professions-Down"] = {0.25, 0.5, 0, 0.3203125, PROFESSIONS_MICRO}
MicromenuAtlas["UI-HUD-MicroMenu-Professions-Mouseover"] = {0.5, 0.75, 0, 0.3203125, PROFESSIONS_MICRO}
MicromenuAtlas["UI-HUD-MicroMenu-Professions-Disabled"] = {0.75, 1, 0, 0.3203125, PROFESSIONS_MICRO}


-- ============================================================================
-- SECTION 3: UTILITY FUNCTIONS
-- ============================================================================

-- Database persistence helpers
local function GetBagCollapseState()
    if addon.db and addon.db.profile and addon.db.profile.micromenu then
        return addon.db.profile.micromenu.bags_collapsed
    end
    return false
end

local function SetBagCollapseState(collapsed)
    if addon.db and addon.db.profile and addon.db.profile.micromenu then
        addon.db.profile.micromenu.bags_collapsed = collapsed
    end
end

local function ShouldForceCollapsedSecondaryInvisible()
    local actionbars = addon.db and addon.db.profile and addon.db.profile.actionbars
    if not actionbars then
        return false
    end

    local visibilityEnabled = actionbars.bag_show_on_hover or actionbars.bag_show_in_combat
    if not visibilityEnabled then
        return false
    end

    local hiddenAlpha = actionbars.bag_visibility_hidden_alpha
    if hiddenAlpha == nil then
        hiddenAlpha = actionbars.visibility_hidden_alpha
    end

    return (tonumber(hiddenAlpha) or 0) > 0
end

-- Bag icon refresh helper.
-- In 3.3.5a, item textures can be temporarily unavailable right after reload;
-- avoid clearing/hiding valid icon data on transient nil returns.
local function RefreshBagSlotIcons()
    local collapsed = GetBagCollapseState()
    local forceHideCollapsed = collapsed and ShouldForceCollapsedSecondaryInvisible()
    for _, bagButton in pairs(bagslots) do
        if bagButton then
            local icon = _G[bagButton:GetName() .. 'IconTexture']
            if icon then
                local inventorySlot = bagButton:GetID()
                local bagLink = GetInventoryItemLink("player", inventorySlot)
                local itemTexture = GetInventoryItemTexture("player", inventorySlot)

                if bagLink then
                    if itemTexture then
                        icon:SetTexture(itemTexture)
                    end

                    icon:Show()
                    icon:SetAlpha(forceHideCollapsed and 0 or 1)
                    pcall(function()
                        icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
                    end)
                else
                    icon:SetTexture("Interface\\PaperDoll\\UI-PaperDoll-Slot-Bag")
                    icon:Show()
                    icon:SetAlpha(0)
                end
            end
        end
    end
end

local function ScheduleBagSlotIconRefreshes()
    RefreshBagSlotIcons()

    if addon.core and addon.core.ScheduleTimer then
        addon.core:ScheduleTimer(function()
            if IsModuleEnabled() then
                RefreshBagSlotIcons()
            end
        end, 0.2)

        addon.core:ScheduleTimer(function()
            if IsModuleEnabled() then
                RefreshBagSlotIcons()
            end
        end, 1.0)
    end
end

-- Adjusts icon alpha for all bag slots to reflect empty/filled state.
-- Blizzard's default handler already updates IconTexture on BAG_UPDATE, so
-- only the alpha fade needs to be applied here.
local PAPERDOLL_BAG_PLACEHOLDER = "interface\\paperdoll\\ui-paperdoll-slot-bag"
local function UpdateBagSlotAlpha()
    local collapsed = GetBagCollapseState()
    local forceHideCollapsed = collapsed and ShouldForceCollapsedSecondaryInvisible()
    for i = 1, #bagslots do
        local bagButton = bagslots[i]
        if bagButton then
            local normalTexture = bagButton:GetNormalTexture()
            if normalTexture then
                normalTexture:SetAlpha(0)
                normalTexture:Hide()
            end

            local icon = _G[bagButton:GetName() .. 'IconTexture']
            if icon then
                local inventorySlot = bagButton:GetID()
                local bagLink = inventorySlot and GetInventoryItemLink("player", inventorySlot) or nil
                local tex = icon:GetTexture()
                local texPath = tex and tostring(tex):lower() or nil
                -- Primary source of truth: equipped bag link.
                -- Texture path is a fallback signal for placeholder visuals.
                local isEmpty = (not bagLink)
                if not isEmpty and texPath and texPath:find(PAPERDOLL_BAG_PLACEHOLDER, 1, true) then
                    isEmpty = true
                end

                if not isEmpty then
                    icon:SetAlpha(forceHideCollapsed and 0 or 1)
                else
                    icon:SetAlpha(0)
                end
            end
        end
    end
end

local collapsedSecondaryFadeDriver

local function StopCollapsedSecondaryFade()
    if collapsedSecondaryFadeDriver then
        collapsedSecondaryFadeDriver:SetScript("OnUpdate", nil)
    end
end

local function ApplyCollapsedSecondaryAlpha(alpha)
    alpha = tonumber(alpha) or 0
    if alpha < 0 then
        alpha = 0
    elseif alpha > 1 then
        alpha = 1
    end

    for i = 1, #bagslots do
        local bags = bagslots[i]
        if bags then
            bags:SetAlpha(alpha)

            if bags.customBorder then
                bags.customBorder:SetAlpha(alpha)
            end
            if bags.background then
                bags.background:SetAlpha(alpha)
            end

            local icon = _G[bags:GetName() .. 'IconTexture']
            if icon then
                local inventorySlot = bags:GetID()
                local bagLink = inventorySlot and GetInventoryItemLink("player", inventorySlot) or nil
                icon:SetAlpha(bagLink and alpha or 0)
            end
        end
    end
end

function addon.RefreshCollapsedSecondaryBagsVisibility(shouldShow)
    if not IsModuleEnabled() then
        return
    end

    local actionbars = addon.db and addon.db.profile and addon.db.profile.actionbars
    if not actionbars or not GetBagCollapseState() then
        StopCollapsedSecondaryFade()
        return
    end

    local visibilityEnabled = actionbars.bag_show_on_hover or actionbars.bag_show_in_combat
    local hiddenAlpha = actionbars.bag_visibility_hidden_alpha
    if hiddenAlpha == nil then
        hiddenAlpha = actionbars.visibility_hidden_alpha
    end
    hiddenAlpha = tonumber(hiddenAlpha) or 0

    if (not visibilityEnabled) or hiddenAlpha > 0 then
        StopCollapsedSecondaryFade()
        return
    end

    if not shouldShow then
        StopCollapsedSecondaryFade()
        ApplyCollapsedSecondaryAlpha(0)
        return
    end

    local startAlpha = 0
    if bagslots[1] and bagslots[1].GetAlpha then
        startAlpha = bagslots[1]:GetAlpha() or 0
    end
    if startAlpha >= 0.99 then
        StopCollapsedSecondaryFade()
        ApplyCollapsedSecondaryAlpha(1)
        return
    end

    if not collapsedSecondaryFadeDriver then
        collapsedSecondaryFadeDriver = CreateFrame("Frame")
    end

    local elapsed = 0
    local duration = 2
    collapsedSecondaryFadeDriver:SetScript("OnUpdate", function(_, delta)
        elapsed = elapsed + delta
        local progress = elapsed / duration

        if progress >= 1 then
            ApplyCollapsedSecondaryAlpha(1)
            StopCollapsedSecondaryFade()
            return
        end

        local alpha = startAlpha + ((1 - startAlpha) * progress)
        ApplyCollapsedSecondaryAlpha(alpha)
    end)
end

-- Atlas helpers
local function GetAtlasKey(buttonName)
    local buttonMap
    if isAscensionServer then
        buttonMap = {
            character = nil, -- Uses portrait
            profession = "UI-HUD-MicroMenu-Professions",
            spellbook = "UI-HUD-MicroMenu-SpellbookAbilities",
            talent = "UI-HUD-MicroMenu-SpecTalents",
            achievement = "UI-HUD-MicroMenu-Achievements",
            questlog = "UI-HUD-MicroMenu-Questlog",
            socials = "UI-HUD-MicroMenu-GuildCommunities",
            lfd = "UI-HUD-MicroMenu-Groupfinder",
            pathtoascension = "UI-HUD-MicroMenu-PathToAscension",
            challenges = "UI-HUD-MicroMenu-Challenges",
            mainmenu = "UI-HUD-MicroMenu-Shop",
            help = "UI-HUD-MicroMenu-GameMenu"
        }
    else
        buttonMap = {
            character = nil,
            profession = "UI-HUD-MicroMenu-Professions",
            spellbook = "UI-HUD-MicroMenu-SpellbookAbilities",
            talent = "UI-HUD-MicroMenu-SpecTalents",
            achievement = "UI-HUD-MicroMenu-Achievements",
            questlog = "UI-HUD-MicroMenu-Questlog",
            socials = "UI-HUD-MicroMenu-GuildCommunities",
            lfd = "UI-HUD-MicroMenu-Groupfinder",
            collections = "UI-HUD-MicroMenu-Collections",
            pvp = nil,
            mainmenu = "UI-HUD-MicroMenu-Shop",
            help = "UI-HUD-MicroMenu-GameMenu"
        }
    end
    return buttonMap[buttonName]
end

local function GetColoredTextureCoords(buttonName, textureType)
    local atlasKey = GetAtlasKey(buttonName)
    if not atlasKey then
        return nil
    end

    local coordsKey = atlasKey .. "-" .. textureType
    local coords = MicromenuAtlas[coordsKey]
    if coords and type(coords) == "table" and #coords >= 4 then
        return coords
    end
    return nil
end

-- Handler management
local function CaptureOriginalHandlers(button)
    local buttonName = button:GetName()
    if not originalBlizzardHandlers[buttonName] then
        originalBlizzardHandlers[buttonName] = {
            OnEnter = button:GetScript('OnEnter'),
            OnLeave = button:GetScript('OnLeave')
        }
    end
end

local function RestoreOriginalHandlers(button)
    local buttonName = button:GetName()
    local handlers = originalBlizzardHandlers[buttonName]
    if handlers then
        if handlers.OnEnter then
            button:SetScript('OnEnter', handlers.OnEnter)
        end
        if handlers.OnLeave then
            button:SetScript('OnLeave', handlers.OnLeave)
        end
    end
end

-- Character/PVP: GetButtonState/GetChecked are unreliable; use panel visibility.
local function IsSpecialMicroButtonActive(button, buttonName)
    if not button then return false end

    if buttonName == "Character" then
        return (_G.CharacterFrame and _G.CharacterFrame:IsVisible() and true or false)
            or (_G.PaperDollFrame and _G.PaperDollFrame:IsVisible() and true or false)
    elseif buttonName == "PVP" then
        -- GetChecked is the PvP flag, not panel-open; GetButtonState is also unreliable.
        return (_G.PVPFrame and _G.PVPFrame:IsVisible() and true or false)
            or (_G.PVPParentFrame and _G.PVPParentFrame:IsVisible() and true or false)
            or (_G.BattlefieldFrame and _G.BattlefieldFrame:IsVisible() and true or false)
            or (_G.HonorFrame and _G.HonorFrame:IsVisible() and true or false)
    end

    return button.GetButtonState and button:GetButtonState() == "PUSHED"
end

local function ApplyMicroButtonPushed(button, pushed)
    if not MicromenuModule.applied or not IsModuleEnabled() then
        return
    end
    if not button or not button.addicatUIState or button.addicatUILastState == pushed then
        return
    end

    button.addicatUILastState = pushed
    button.addicatUIState.pushed = pushed
    if button.HandleAddicatUIState then
        button.HandleAddicatUIState()
    end
end

local function SyncSpecialMicroButtonState(button, buttonName)
    if button and button.addicatUIState then
        ApplyMicroButtonPushed(button, IsSpecialMicroButtonActive(button, buttonName) and true or false)
    end
end

local function UpdateCharacterPortraitVisibility()
    if not MicromenuModule.applied or not IsModuleEnabled() then
        return
    end

    if MicroButtonPortrait then
        if addon and addon.db and addon.db.profile and addon.db.profile.micromenu and
            addon.db.profile.micromenu.grayscale_icons then
            MicroButtonPortrait:Hide()
            MicroButtonPortrait:SetAlpha(0)
        else
            MicroButtonPortrait:Show()
            -- Keep portrait valid after late Blizzard refreshes.
            SetPortraitTexture(MicroButtonPortrait, "player")
            -- Don't set alpha here — the SetPushed/SetNormal hooks and
            -- HandleAddicatUIState manage it to avoid race conditions.
        end
    end

    -- Kill Blizzard's native button textures every time UpdateMicroButtons
    -- runs. Blizzard restores them internally; we must re-clear each pass.
    -- Only in colored mode — grayscale uses native textures with atlas.
    local charBtn = _G.CharacterMicroButton
    local useGrayscaleForClear = addon and addon.db and addon.db.profile and addon.db.profile.micromenu and addon.db.profile.micromenu.grayscale_icons
    if charBtn and not useGrayscaleForClear then
        local nt = charBtn:GetNormalTexture()
        if nt then nt:SetTexture(nil) end
        local pt = charBtn:GetPushedTexture()
        if pt then pt:SetTexture(nil) end
        local ht = charBtn:GetHighlightTexture()
        if ht then ht:SetTexture(nil) end
    end

    -- Refresh character highlight so it stays in sync.
    -- Character button background can be hidden by late startup passes.
    local useGrayscale = addon and addon.db and addon.db.profile and addon.db.profile.micromenu and addon.db.profile.micromenu.grayscale_icons
    if charBtn and not useGrayscale and charBtn.AddicatUICharHighlight then
        SetPortraitTexture(charBtn.AddicatUICharHighlight, "player")
        -- Read current portrait TexCoord instead of hardcoding normal coords.
        -- Blizzard shifts the crop for pushed/normal state; we must match it.
        charBtn.AddicatUICharHighlight:SetTexCoord(MicroButtonPortrait:GetTexCoord())
        charBtn.AddicatUICharHighlight:SetBlendMode('ADD')
        charBtn.AddicatUICharHighlight:SetAlpha(0.5)
        charBtn.AddicatUICharHighlight:SetAllPoints(MicroButtonPortrait)
    end
    if charBtn and charBtn.AddicatUIBackground then
        local microTexture = 'Interface\\AddOns\\AddicatUI_Art\\Textures\\Micromenu\\uimicromenu2x'

        -- Rehydrate texture data in case a late UI pass stripped it.
        charBtn.AddicatUIBackground:SetTexture(microTexture)
        charBtn.AddicatUIBackground:SetTexCoord(0.0654297, 0.12793, 0.330078, 0.490234)
        if charBtn.AddicatUIBackgroundPushed then
            charBtn.AddicatUIBackgroundPushed:SetTexture(microTexture)
            charBtn.AddicatUIBackgroundPushed:SetTexCoord(0.0654297, 0.12793, 0.494141, 0.654297)
        end

        if useGrayscale then
            charBtn.AddicatUIBackground:Hide()
            if charBtn.AddicatUIBackgroundPushed then
                charBtn.AddicatUIBackgroundPushed:Hide()
            end
        else
            if charBtn.addicatUIState and charBtn.addicatUIState.pushed and charBtn.AddicatUIBackgroundPushed then
                charBtn.AddicatUIBackground:Hide()
                charBtn.AddicatUIBackgroundPushed:Show()
            else
                charBtn.AddicatUIBackground:Show()
                if charBtn.AddicatUIBackgroundPushed then
                    charBtn.AddicatUIBackgroundPushed:Hide()
                end
            end
        end
    elseif charBtn and not (addon and addon.db and addon.db.profile and addon.db.profile.micromenu and addon.db.profile.micromenu.grayscale_icons) then
        -- Late safety net: if background was removed, recreate it for colored mode.
        local microTexture = 'Interface\\AddOns\\AddicatUI_Art\\Textures\\Micromenu\\uimicromenu2x'
        local dx, dy = -1, 1
        local offX, offY = charBtn:GetPushedTextOffset()
        local sizeX, sizeY = charBtn:GetSize()

        local bg = charBtn:CreateTexture(nil, 'BACKGROUND')
        bg:SetTexture(microTexture)
        bg:SetSize(sizeX, sizeY + 1)
        bg:SetTexCoord(0.0654297, 0.12793, 0.330078, 0.490234)
        bg:SetPoint('CENTER', dx, dy)
        charBtn.AddicatUIBackground = bg

        local bgPushed = charBtn:CreateTexture(nil, 'BACKGROUND')
        bgPushed:SetTexture(microTexture)
        bgPushed:SetSize(sizeX, sizeY + 1)
        bgPushed:SetTexCoord(0.0654297, 0.12793, 0.494141, 0.654297)
        bgPushed:SetPoint('CENTER', dx + offX, dy + offY)
        bgPushed:Hide()
        charBtn.AddicatUIBackgroundPushed = bgPushed

        charBtn.AddicatUIBackground:Show()
    end
end
-- ============================================================================
-- APPLY/RESTORE SYSTEM
-- ============================================================================

local function StoreOriginalMicroButtonStates()
    -- Store original positions and parents for all micro buttons
    for _, button in pairs(MICRO_BUTTONS) do
        if button then -- Check if button exists (e.g. PVPMicroButton might not)
            local buttonName = button:GetName()
            if not MicromenuModule.originalStates[buttonName] then
                MicromenuModule.originalStates[buttonName] = {
                    parent = button:GetParent(),
                    points = {},
                    size = {button:GetSize()},
                    shown = button:IsShown(),
                    scripts = {
                        OnEnter = button:GetScript('OnEnter'),
                        OnLeave = button:GetScript('OnLeave'),
                        OnClick = button:GetScript('OnClick'),
                        OnUpdate = button:GetScript('OnUpdate')
                    },
                    textures = {
                        normal = button:GetNormalTexture() and button:GetNormalTexture():GetTexture(),
                        pushed = button:GetPushedTexture() and button:GetPushedTexture():GetTexture(),
                        highlight = button:GetHighlightTexture() and button:GetHighlightTexture():GetTexture(),
                        disabled = button:GetDisabledTexture() and button:GetDisabledTexture():GetTexture()
                    },
                    SetPoint = button.SetPoint
                }
                -- Store all anchor points
                for i = 1, button:GetNumPoints() do
                    local point, relativeTo, relativePoint, x, y = button:GetPoint(i)
                    table.insert(MicromenuModule.originalStates[buttonName].points, {point, relativeTo, relativePoint, x, y})
                end
            end
        end
    end

    -- Store bag button states
    MicromenuModule.originalStates.MainMenuBarBackpackButton = {
        parent = MainMenuBarBackpackButton:GetParent(),
        points = {},
        size = {MainMenuBarBackpackButton:GetSize()},
        SetPoint = MainMenuBarBackpackButton.SetPoint
    }
    for i = 1, MainMenuBarBackpackButton:GetNumPoints() do
        local point, relativeTo, relativePoint, x, y = MainMenuBarBackpackButton:GetPoint(i)
        table.insert(MicromenuModule.originalStates.MainMenuBarBackpackButton.points,
            {point, relativeTo, relativePoint, x, y})
    end

    -- Store bag slots states
    for idx, bagSlot in pairs(bagslots) do
        local slotName = bagSlot:GetName()
        MicromenuModule.originalStates[slotName] = {
            parent = bagSlot:GetParent(),
            points = {},
            size = {bagSlot:GetSize()}
        }
        for i = 1, bagSlot:GetNumPoints() do
            local point, relativeTo, relativePoint, x, y = bagSlot:GetPoint(i)
            table.insert(MicromenuModule.originalStates[slotName].points, {point, relativeTo, relativePoint, x, y})
        end
    end

    -- Store KeyRingButton state
    if KeyRingButton then
        MicromenuModule.originalStates.KeyRingButton = {
            parent = KeyRingButton:GetParent(),
            points = {},
            size = {KeyRingButton:GetSize()}
        }
        for i = 1, KeyRingButton:GetNumPoints() do
            local point, relativeTo, relativePoint, x, y = KeyRingButton:GetPoint(i)
            table.insert(MicromenuModule.originalStates.KeyRingButton.points, {point, relativeTo, relativePoint, x, y})
        end
    end

    -- Store LFG frame states
    if MiniMapLFGFrame then
        MicromenuModule.originalStates.MiniMapLFGFrame = {
            points = {},
            scale = MiniMapLFGFrame:GetScale()
        }
        for i = 1, MiniMapLFGFrame:GetNumPoints() do
            local point, relativeTo, relativePoint, x, y = MiniMapLFGFrame:GetPoint(i)
            table.insert(MicromenuModule.originalStates.MiniMapLFGFrame.points, {point, relativeTo, relativePoint, x, y})
        end
    end

    -- Store LFDSearchStatus state
    if LFDSearchStatus then
        MicromenuModule.originalStates.LFDSearchStatus = {
            parent = LFDSearchStatus:GetParent(),
            points = {}
        }
        for i = 1, LFDSearchStatus:GetNumPoints() do
            local point, relativeTo, relativePoint, x, y = LFDSearchStatus:GetPoint(i)
            table.insert(MicromenuModule.originalStates.LFDSearchStatus.points, {point, relativeTo, relativePoint, x, y})
        end
    end
end

local function RestoreMicromenuSystem()
    if not MicromenuModule.applied then
        return
    end

    -- Unregister all state drivers
    for name, data in pairs(MicromenuModule.stateDrivers) do
        if data.frame then
            if InCombatLockdown() then
                if addon.CombatQueue then
                    addon.CombatQueue:Add("micromenu_restore_state_driver_" .. tostring(name), function()
                        if data.frame and data.state then
                            UnregisterStateDriver(data.frame, data.state)
                        end
                    end)
                end
            else
                UnregisterStateDriver(data.frame, data.state)
            end
        end
    end
    MicromenuModule.stateDrivers = {}

    -- Restore micro buttons to original state
    for _, button in pairs(MICRO_BUTTONS) do
        if button then
            local buttonName = button:GetName()
            local original = MicromenuModule.originalStates[buttonName]

            if original then
                -- Restore SetPoint function if it was nooped
                if original.SetPoint then
                    button.SetPoint = original.SetPoint
                end

                -- Restore parent
                if original.parent then
                    button:SetParent(original.parent)
                end

                -- Clear and restore points
                button:ClearAllPoints()
                for _, pointData in ipairs(original.points) do
                    local point, relativeTo, relativePoint, x, y = unpack(pointData)
                    if relativeTo then
                        button:SetPoint(point, relativeTo, relativePoint, x, y)
                    else
                        button:SetPoint(point, relativePoint, x, y)
                    end
                end

                -- Restore size
                if original.size then
                    button:SetSize(unpack(original.size))
                end

                -- AddicatUI's own buttons (Collections, Professions) start hidden and have no stock slot to go back to.
                if not original.shown then
                    button:Hide()
                end

                -- Restore textures
                if original.textures then
                    if original.textures.normal and button:GetNormalTexture() then
                        button:GetNormalTexture():SetTexture(original.textures.normal)
                    end
                    if original.textures.pushed and button:GetPushedTexture() then
                        button:GetPushedTexture():SetTexture(original.textures.pushed)
                    end
                    if original.textures.highlight and button:GetHighlightTexture() then
                        button:GetHighlightTexture():SetTexture(original.textures.highlight)
                    end
                    if original.textures.disabled and button:GetDisabledTexture() then
                        button:GetDisabledTexture():SetTexture(original.textures.disabled)
                    end
                end

                -- Restore scripts
                if original.scripts then
                    for scriptName, scriptFunc in pairs(original.scripts) do
                        button:SetScript(scriptName, scriptFunc)
                    end
                end

                -- Clean up AddicatUI custom textures
                if button.AddicatUIBackground then
                    button.AddicatUIBackground:Hide()
                    button.AddicatUIBackground = nil
                end
                if button.AddicatUIBackgroundPushed then
                    button.AddicatUIBackgroundPushed:Hide()
                    button.AddicatUIBackgroundPushed = nil
                end
                if button.AddicatUICharHighlight then
                    button.AddicatUICharHighlight:Hide()
                    button.AddicatUICharHighlight = nil
                end
                if button.AddicatUIPVPIcon then
                    button.AddicatUIPVPIcon:Hide()
                    button.AddicatUIPVPIcon = nil
                end

                if button == _G.CharacterMicroButton and MicroButtonPortrait then
                    MicroButtonPortrait:Show()
                    MicroButtonPortrait:SetAlpha(1)
                end

                button.addicatUIState = nil
                button.addicatUIPanelPushed = nil
                button.addicatUILastState = nil
                button.HandleAddicatUIState = nil
            end
        end
    end

    -- Restore MainMenuBarBackpackButton
    if MicromenuModule.originalStates.MainMenuBarBackpackButton then
        local original = MicromenuModule.originalStates.MainMenuBarBackpackButton

        if original.SetPoint then
            MainMenuBarBackpackButton.SetPoint = original.SetPoint
        end

        if original.parent then
            MainMenuBarBackpackButton:SetParent(original.parent)
        end

        MainMenuBarBackpackButton:ClearAllPoints()
        for _, pointData in ipairs(original.points) do
            local point, relativeTo, relativePoint, x, y = unpack(pointData)
            if relativeTo then
                MainMenuBarBackpackButton:SetPoint(point, relativeTo, relativePoint, x, y)
            else
                MainMenuBarBackpackButton:SetPoint(point, relativePoint, x, y)
            end
        end

        if original.size then
            MainMenuBarBackpackButton:SetSize(unpack(original.size))
        end
    end

    -- Restore bag slots
    for idx, bagSlot in pairs(bagslots) do
        local slotName = bagSlot:GetName()
        local original = MicromenuModule.originalStates[slotName]

        if original then
            if original.parent then
                bagSlot:SetParent(original.parent)
            end

            bagSlot:ClearAllPoints()
            for _, pointData in ipairs(original.points) do
                local point, relativeTo, relativePoint, x, y = unpack(pointData)
                if relativeTo then
                    bagSlot:SetPoint(point, relativeTo, relativePoint, x, y)
                else
                    bagSlot:SetPoint(point, relativePoint, x, y)
                end
            end

            if original.size then
                bagSlot:SetSize(unpack(original.size))
            end
        end
    end

    -- Restore KeyRingButton
    if KeyRingButton and MicromenuModule.originalStates.KeyRingButton then
        local original = MicromenuModule.originalStates.KeyRingButton

        if original.parent then
            KeyRingButton:SetParent(original.parent)
        end

        KeyRingButton:ClearAllPoints()
        for _, pointData in ipairs(original.points) do
            local point, relativeTo, relativePoint, x, y = unpack(pointData)
            if relativeTo then
                KeyRingButton:SetPoint(point, relativeTo, relativePoint, x, y)
            else
                KeyRingButton:SetPoint(point, relativePoint, x, y)
            end
        end

        if original.size then
            KeyRingButton:SetSize(unpack(original.size))
        end
    end

    -- Restore LFG frame
    if MiniMapLFGFrame and MicromenuModule.originalStates.MiniMapLFGFrame then
        local original = MicromenuModule.originalStates.MiniMapLFGFrame

        MiniMapLFGFrame:ClearAllPoints()
        for _, pointData in ipairs(original.points) do
            local point, relativeTo, relativePoint, x, y = unpack(pointData)
            if relativeTo then
                MiniMapLFGFrame:SetPoint(point, relativeTo, relativePoint, x, y)
            else
                MiniMapLFGFrame:SetPoint(point, relativePoint, x, y)
            end
        end

        if original.scale then
            MiniMapLFGFrame:SetScale(original.scale)
        end

        -- Restore border
        if MiniMapLFGFrameBorder then
            MiniMapLFGFrameBorder:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
        end
    end

    -- Restore LFDSearchStatus
    if LFDSearchStatus and MicromenuModule.originalStates.LFDSearchStatus then
        local original = MicromenuModule.originalStates.LFDSearchStatus

        if original.parent then
            LFDSearchStatus:SetParent(original.parent)
        end

        LFDSearchStatus:ClearAllPoints()
        for _, pointData in ipairs(original.points) do
            local point, relativeTo, relativePoint, x, y = unpack(pointData)
            if relativeTo then
                LFDSearchStatus:SetPoint(point, relativeTo, relativePoint, x, y)
            else
                LFDSearchStatus:SetPoint(point, relativePoint, x, y)
            end
        end
    end

    -- Hide custom frames
    if _G.AddicatUI_MicroButtonBar then
        _G.AddicatUI_MicroButtonBar:Hide()
    end
    if _G.AddicatUI_BagButtonBar then
        _G.AddicatUI_BagButtonBar:Hide()
    end
    if addon.BagsToggle then
        addon.BagsToggle:Hide()
    end

    -- Unregister all event frames
    for _, frame in pairs(MicromenuModule.eventFrames) do
        if frame and frame.UnregisterAllEvents then
            frame:UnregisterAllEvents()
        end
    end
    MicromenuModule.eventFrames = {}

    -- Hide cancels the latency AceTimer via OnHide before we drop the ref.
    local latencyBar = MicromenuModule.frames.latencyIndicator
    if latencyBar then
        latencyBar:Hide()
    end

    MicromenuModule.frames = {}
    MicromenuModule.hooks = {}
    MicromenuModule.applied = false
    addon.ReanchorLFDSearchStatus = nil

    if UpdateMicroButtons then
        UpdateMicroButtons()
    end
end

-- WeakAuras/PlayerModel init can invalidate MicroButtonPortrait; re-apply on Blizzard refresh.
if UpdateMicroButtons then
    hooksecurefunc("UpdateMicroButtons", function()
        SyncSpecialMicroButtonState(_G.CharacterMicroButton, "Character")
        SyncSpecialMicroButtonState(_G.PVPMicroButton, "PVP")
        UpdateCharacterPortraitVisibility()
    end)
end



-- ============================================================================
-- MICRO MENU INTERNALS
-- ============================================================================
-- Frames and per-login state are created by ApplyMicromenuSystem(); they are declared
-- here so the functions below close over them at file scope.

local hidePendingTime = nil
local charPushHooksRegistered = false
local MICRO_LAYOUT_BASE_Y = 55
local hideFramesScheduler, bagsBar

local function HideUnwantedBagFrames()
    -- Process all secondary bag slots
    for i, bags in pairs(bagslots) do
        local bagName = bags:GetName()

        local possibleFrames = {bagName .. "Background", bagName .. "Border", bagName .. "Frame",
                                bagName .. "Texture", bagName .. "NormalTexture", bagName .. "Highlight", bagName .. "Glow", bagName .. "Green",
                                bagName .. "NormalTexture2", bagName .. "IconBorder", bagName .. "Flash",
                                bagName .. "NewItemTexture", bagName .. "Shine", bagName .. "NewItemGlow"}

        for _, frameName in pairs(possibleFrames) do
            local frame = _G[frameName]
            if frame and frame.Hide then
                frame:Hide()
                if frame.SetAlpha then
                    frame:SetAlpha(0)
                end
            end
        end

        local normalTexture = bags:GetNormalTexture()
        if normalTexture then
            normalTexture:SetAlpha(0)
            normalTexture:Hide()
        end

        -- Hide problematic texture regions
        local numRegions = bags:GetNumRegions()
        for j = 1, numRegions do
            local region = select(j, bags:GetRegions())
            if region and region:GetObjectType() == "Texture" then
                -- Keep AddicatUI managed textures visible; only suppress
                -- Blizzard default layers.
                if region == bags.customBorder or region == bags.background then
                    region:Show()
                    if region.SetAlpha then
                        region:SetAlpha(1)
                    end
                else
                local texture = region:GetTexture()
                if texture then
                    local textureLower = tostring(texture):lower()
                    
                    -- Skip item icons - don't hide them
                    if textureLower:find("interface\\icons\\") then
                        -- This is an item icon - don't hide it
                    else
                        -- Hide only UI elements, not icons
                        if textureLower:find("background") or textureLower:find("border") or textureLower:find("frame") or
                            textureLower:find("highlight") or textureLower:find("green") or textureLower:find("glow") or
                            textureLower:find("flash") or textureLower:find("shine") then
                            region:Hide()
                            if region.SetAlpha then
                                region:SetAlpha(0)
                            end
                        end
                    end
                end
                end
            end
        end
    end

    -- Handle KeyRing with same approach
    if KeyRingButton then
        local keyRingName = KeyRingButton:GetName()
        local possibleFrames = {keyRingName .. "Background", keyRingName .. "Border", keyRingName .. "Frame",
                                keyRingName .. "Texture", keyRingName .. "Highlight", keyRingName .. "Glow",
                                keyRingName .. "Green", keyRingName .. "NormalTexture2",
                                keyRingName .. "IconBorder", keyRingName .. "Flash", keyRingName .. "Shine",
                                keyRingName .. "NewItemGlow"}

        for _, frameName in pairs(possibleFrames) do
            local frame = _G[frameName]
            if frame and frame.Hide then
                frame:Hide()
                if frame.SetAlpha then
                    frame:SetAlpha(0)
                end
            end
        end
    end
end

local function ScheduleHideFrames(delay)
    local target = GetTime() + (delay or 0)
    if hidePendingTime and hidePendingTime <= target then
        return -- an earlier execution is already pending
    end
    hidePendingTime = target

    if not hideFramesScheduler:GetScript("OnUpdate") then
        hideFramesScheduler:SetScript("OnUpdate", function(self)
            if hidePendingTime and GetTime() >= hidePendingTime then
                HideUnwantedBagFrames()
                hidePendingTime = nil
                self:SetScript("OnUpdate", nil)
            end
        end)
    end
end

local function SetupPVPButton(button)
    -- Mirror the Character button pattern:
    -- Instead of fighting WoW's internal NormalTexture alpha management,
    -- we create our own ARTWORK texture (AddicatUIPVPIcon) that we control
    -- exclusively, just like Character uses MicroButtonPortrait.
    local microTexture = 'Interface\\AddOns\\AddicatUI_Art\\Textures\\Micromenu\\micropvp'
    local englishFaction = UnitFactionGroup('player')
    local backgroundTexture = 'Interface\\AddOns\\AddicatUI_Art\\Textures\\Micromenu\\uimicromenu2x'
    local buttonWidth, buttonHeight = button:GetSize()
    local dx, dy = -1, 1
    local offX, offY = button:GetPushedTextOffset()
    local sizeX, sizeY = buttonWidth, buttonHeight

    -- ---- Icon layer: our own ARTWORK texture, never touched by WoW's button system ----
    if not button.AddicatUIPVPIcon then
        local icon = button:CreateTexture(nil, 'ARTWORK')
        button.AddicatUIPVPIcon = icon
    end

    local icon = button.AddicatUIPVPIcon
    if englishFaction == 'Alliance' then
        icon:SetTexture(microTexture)
        icon:SetTexCoord(0, 118 / 256, 0, 151 / 256)
    elseif englishFaction == 'Horde' then
        icon:SetTexture(microTexture)
        icon:SetTexCoord(118 / 256, 236 / 256, 0, 151 / 256)
    else
        -- Faction unknown: use atlas grayscale fallback
        icon:SetAtlasTexture('ui-hud-micromenu-pvp-up-2x')
    end
    icon:ClearAllPoints()
    icon:SetPoint('CENTER', button, 'CENTER', 0, 0)
    icon:SetSize(buttonWidth, buttonHeight)
    icon:SetAlpha(1.0)
    icon:Show()

    -- ---- Hover highlight: reuse GetHighlightTexture() with faction texture + BlendMode ADD
    -- WoW shows/hides this automatically on mouse enter/leave.
    local highlightTexture = button:GetHighlightTexture()
    if highlightTexture then
        if englishFaction == 'Alliance' then
            highlightTexture:SetTexture(microTexture)
            highlightTexture:SetTexCoord(0, 118 / 256, 0, 151 / 256)
        elseif englishFaction == 'Horde' then
            highlightTexture:SetTexture(microTexture)
            highlightTexture:SetTexCoord(118 / 256, 236 / 256, 0, 151 / 256)
        else
            highlightTexture:SetAtlasTexture('ui-hud-micromenu-pvp-mouseover-2x')
        end
        highlightTexture:ClearAllPoints()
        highlightTexture:SetAllPoints(button)
        highlightTexture:SetBlendMode('ADD')
        highlightTexture:SetAlpha(0.5)
    end

    -- ---- Background slot texture ----
    if not button.AddicatUIBackground then
        local bg = button:CreateTexture(nil, 'BACKGROUND')
        bg:SetTexture(backgroundTexture)
        bg:SetSize(sizeX, sizeY + 1)
        bg:SetTexCoord(0.0654297, 0.12793, 0.330078, 0.490234)
        bg:SetPoint('CENTER', dx, dy)
        button.AddicatUIBackground = bg

        local bgPushed = button:CreateTexture(nil, 'BACKGROUND')
        bgPushed:SetTexture(backgroundTexture)
        bgPushed:SetSize(sizeX, sizeY + 1)
        bgPushed:SetTexCoord(0.0654297, 0.12793, 0.494141, 0.654297)
        bgPushed:SetPoint('CENTER', dx + offX, dy + offY)
        bgPushed:Hide()
        button.AddicatUIBackgroundPushed = bgPushed
    else
        button.AddicatUIBackground:SetTexture(backgroundTexture)
        button.AddicatUIBackground:SetTexCoord(0.0654297, 0.12793, 0.330078, 0.490234)
        button.AddicatUIBackground:ClearAllPoints()
        button.AddicatUIBackground:SetPoint('CENTER', dx, dy)
        button.AddicatUIBackground:SetSize(sizeX, sizeY + 1)

        if button.AddicatUIBackgroundPushed then
            button.AddicatUIBackgroundPushed:SetTexture(backgroundTexture)
            button.AddicatUIBackgroundPushed:SetTexCoord(0.0654297, 0.12793, 0.494141, 0.654297)
            button.AddicatUIBackgroundPushed:ClearAllPoints()
            button.AddicatUIBackgroundPushed:SetPoint('CENTER', dx + offX, dy + offY)
            button.AddicatUIBackgroundPushed:SetSize(sizeX, sizeY + 1)
        end
    end

    -- ---- State tracking ----
    button.addicatUIState = button.addicatUIState or {}
    button.addicatUIState.pushed = IsSpecialMicroButtonActive(button, "PVP")
    button.addicatUILastState = button.addicatUIState.pushed

    -- ---- State handler: only manipulates AddicatUIPVPIcon ----
    button.HandleAddicatUIState = function()
        local pvpIcon = button.AddicatUIPVPIcon
        local state = button.addicatUIState
        local hlTex = button:GetHighlightTexture()
        if state and state.pushed then
            if pvpIcon then
                pvpIcon:ClearAllPoints()
                pvpIcon:SetPoint('CENTER', button, 'CENTER', offX, offY)
                pvpIcon:SetAlpha(0.7)
            end
            if button.AddicatUIBackground then
                button.AddicatUIBackground:Hide()
            end
            if button.AddicatUIBackgroundPushed then
                button.AddicatUIBackgroundPushed:Show()
            end
            -- Shift highlight to match icon pushed displacement
            if hlTex then
                hlTex:ClearAllPoints()
                hlTex:SetPoint('TOPLEFT', button, 'TOPLEFT', offX, offY)
                hlTex:SetPoint('BOTTOMRIGHT', button, 'BOTTOMRIGHT', offX, offY)
            end
        else
            if pvpIcon then
                pvpIcon:ClearAllPoints()
                pvpIcon:SetPoint('CENTER', button, 'CENTER', 0, 0)
                pvpIcon:SetAlpha(1.0)
            end
            if button.AddicatUIBackground then
                button.AddicatUIBackground:Show()
            end
            if button.AddicatUIBackgroundPushed then
                button.AddicatUIBackgroundPushed:Hide()
            end
            if hlTex then
                hlTex:ClearAllPoints()
                hlTex:SetAllPoints(button)
            end
        end
    end

    -- ---- Mouse feedback (immediate response on click) ----
    if not button.AddicatUIStateHooks then
        button:HookScript('OnMouseDown', function(self)
            if self.addicatUIState then
                self.addicatUIState.pushed = true
            end
            if self.HandleAddicatUIState then
                self.HandleAddicatUIState()
            end
        end)
        button:HookScript('OnMouseUp', function(self)
            local currentState = IsSpecialMicroButtonActive(self, "PVP")
            self.addicatUILastState = currentState
            if self.addicatUIState then
                self.addicatUIState.pushed = currentState
            end
            if self.HandleAddicatUIState then
                self.HandleAddicatUIState()
            end
        end)
        button.AddicatUIStateHooks = true
    end

    -- Apply initial state
    button.HandleAddicatUIState()
end

-- ============================================================================
-- ADDON LAUNCHER (launcherButton and its flyout)
-- ============================================================================
-- spec = { id, title, description, icon, entries = { { title, description, binding, icon, open, isOpen, shown } } }
-- icon = { file, coords = { left, right, top, bottom }, color = { r, g, b } }; the owner's callbacks run in pcall.
-- An entry's description may be a function (read on hover), and shown a function: the flyout lists the entry only
-- while it returns true (read each time the flyout opens; a failing one counts as shown).

local launcher
local launcherFlyout
local LAUNCHER_CHROME = 'Interface\\AddOns\\AddicatUI_Art\\Textures\\Micromenu\\uimicromenu2x'
local FLYOUT_ROW, FLYOUT_ICON, FLYOUT_PAD_X, FLYOUT_PAD_Y, FLYOUT_MIN_WIDTH, FLYOUT_GAP = 22, 16, 12, 10, 150, 4

local function CallLauncher(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, result = pcall(fn, ...)
    if not ok then
        geterrorhandler()(result)
        return nil
    end
    return result
end

local function PaintLauncherIcon(texture, icon, gray)
    local c = icon and icon.coords
    if not (icon and type(icon.file) == "string" and c) then
        texture:SetTexture(nil)
        return
    end
    texture:SetTexture(icon.file)
    texture:SetTexCoord(c[1] or 0, c[2] or 1, c[3] or 0, c[4] or 1)
    local color = icon.color
    if gray then
        texture:SetVertexColor(0.8, 0.8, 0.8)
    elseif color then
        texture:SetVertexColor(color[1] or 1, color[2] or 1, color[3] or 1)
    else
        texture:SetVertexColor(1, 1, 1)
    end
    texture:SetDesaturated(gray and true or false)
end

-- What every stock micro button shows: the name with its key in brackets, then the newbie line.
local function ShowLauncherTooltip(owner, title, binding, description)
    local text = title or ""
    if binding and MicroButtonTooltipText then text = MicroButtonTooltipText(text, binding) end
    GameTooltip_AddNewbieTip(owner, text, 1.0, 1.0, 1.0, description)
end

local function EntryShown(entry)
    if type(entry.shown) ~= "function" then return true end
    local ok, result = pcall(entry.shown)
    if not ok then
        geterrorhandler()(result)
        return true
    end
    return result and true or false
end

local function EntryText(entry)
    if type(entry.description) == "function" then return CallLauncher(entry.description) end
    return entry.description
end

local function BindingLabel(binding)
    local key = binding and GetBindingKey(binding)
    if not key then return nil end
    if GetBindingText then return GetBindingText(key, "KEY_", 1) end
    return key
end

local function LayoutFlyout(flyout)
    local entries = (launcher and launcher.entries) or {}
    flyout.title:SetText(launcher and launcher.title or "")
    local width = flyout.title:GetStringWidth() + 8
    local y = FLYOUT_PAD_Y + FLYOUT_ROW
    local index = 0
    for _, entry in ipairs(entries) do
        if EntryShown(entry) then
            index = index + 1
            local row = flyout.rows[index] or flyout.NewRow(index)
            row.entry = entry
            PaintLauncherIcon(row.icon, entry.icon, false)
            row.text:SetText(entry.title or "")
            local key = BindingLabel(entry.binding)
            row.detail:SetText(key or "")
            row.text:SetPoint("RIGHT", key and row.detail or row, key and "LEFT" or "RIGHT", key and -12 or 0, 0)
            row:ClearAllPoints()
            row:SetPoint("TOPLEFT", flyout, "TOPLEFT", FLYOUT_PAD_X, -y)
            row:SetPoint("RIGHT", flyout, "RIGHT", -FLYOUT_PAD_X, 0)
            row:UnlockHighlight()
            if CallLauncher(entry.isOpen) then row:LockHighlight() end
            row:Show()
            local w = FLYOUT_ICON + 6 + row.text:GetStringWidth() + 8
            if key then w = w + 12 + row.detail:GetStringWidth() end
            width = math.max(width, w)
            y = y + FLYOUT_ROW
        end
    end
    for unused = index + 1, #flyout.rows do flyout.rows[unused]:Hide() end
    flyout:SetSize(math.max(FLYOUT_MIN_WIDTH, width) + FLYOUT_PAD_X * 2, y + FLYOUT_PAD_Y)
end

-- Opens away from the screen edge the button is nearest to, like the strip's own LFG tooltip.
local function PlaceFlyout(flyout)
    flyout:ClearAllPoints()
    local x, y = launcherButton:GetCenter()
    local ux, uy = UIParent:GetCenter()
    local scale = launcherButton:GetEffectiveScale() / UIParent:GetEffectiveScale()
    local below = y and uy and y * scale > uy
    local leftward = x and ux and x * scale > ux
    local horizontal = leftward and "RIGHT" or "LEFT"
    if below then
        flyout:SetPoint("TOP" .. horizontal, launcherButton, "BOTTOM" .. horizontal, 0, -FLYOUT_GAP)
    else
        flyout:SetPoint("BOTTOM" .. horizontal, launcherButton, "TOP" .. horizontal, 0, FLYOUT_GAP)
    end
end

local function EnsureFlyout()
    if launcherFlyout then return launcherFlyout end
    local flyout = CreateFrame("Frame", "AddicatUI_LauncherFlyout", UIParent)
    flyout:SetFrameStrata("DIALOG")
    flyout:SetClampedToScreen(true)
    flyout:EnableMouse(true)
    flyout:Hide()
    local forever = addon.ForeverUI
    if forever and forever.SkinMenuBackground then
        forever.SkinMenuBackground(flyout, "bg")
    else
        flyout:SetBackdrop({
            bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
            edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
            tile = true, tileSize = 16, edgeSize = 16,
            insets = { left = 5, right = 5, top = 5, bottom = 5 },
        })
        flyout:SetBackdropColor(0.05, 0.05, 0.05, 0.95)
        flyout:SetBackdropBorderColor(0.5, 0.5, 0.5)
    end

    flyout.title = flyout:CreateFontString(nil, "ARTWORK", "GameFontNormal")
    flyout.title:SetPoint("TOPLEFT", flyout, "TOPLEFT", FLYOUT_PAD_X + 2, -FLYOUT_PAD_Y - 4)
    flyout.rows = {}

    function flyout.NewRow(index)
        local row = CreateFrame("Button", nil, flyout)
        row:SetHeight(FLYOUT_ROW)
        local highlight = row:CreateTexture(nil, "BACKGROUND")
        highlight:SetTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight")
        highlight:SetBlendMode("ADD")
        highlight:SetAllPoints(row)
        row:SetHighlightTexture(highlight)
        row.icon = row:CreateTexture(nil, "ARTWORK")
        row.icon:SetSize(FLYOUT_ICON, FLYOUT_ICON)
        row.icon:SetPoint("LEFT", row, "LEFT", 2, 0)
        row.text = row:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
        row.text:SetJustifyH("LEFT")
        row.text:SetPoint("LEFT", row.icon, "RIGHT", 6, 0)
        row.detail = row:CreateFontString(nil, "ARTWORK", "GameFontDisableSmall")
        row.detail:SetJustifyH("RIGHT")
        row.detail:SetPoint("RIGHT", row, "RIGHT", 0, 0)
        row:RegisterForClicks("LeftButtonUp")
        row:SetScript("OnClick", function(self)
            PlaySound("igMainMenuOptionCheckBoxOn")
            flyout:Hide()
            CallLauncher(self.entry and self.entry.open)
        end)
        row:SetScript("OnEnter", function(self)
            local entry = self.entry
            if entry then ShowLauncherTooltip(self, entry.title, entry.binding, EntryText(entry)) end
        end)
        row:SetScript("OnLeave", function() GameTooltip:Hide() end)
        flyout.rows[index] = row
        return row
    end

    -- Closed by a press anywhere else (the button toggles it itself), by Escape, or with the strip.
    flyout:SetScript("OnUpdate", function(self)
        if not launcherButton:IsVisible() then
            self:Hide()
            return
        end
        local down = IsMouseButtonDown() and true or false
        local fresh = down and not self.wasDown
        self.wasDown = down
        if fresh and not self:IsMouseOver() and not launcherButton:IsMouseOver() then
            self:Hide()
        end
    end)
    flyout:SetScript("OnShow", function(self)
        self.wasDown = IsMouseButtonDown() and true or false
        ApplyMicroButtonPushed(launcherButton, true)
    end)
    flyout:SetScript("OnHide", function()
        ApplyMicroButtonPushed(launcherButton, false)
    end)
    if UISpecialFrames then tinsert(UISpecialFrames, "AddicatUI_LauncherFlyout") end
    launcherFlyout = flyout
    return flyout
end

local function ToggleLauncherFlyout()
    local flyout = EnsureFlyout()
    if flyout:IsShown() then
        flyout:Hide()
        PlaySound("igMainMenuClose")
        return
    end
    if GameTooltip:IsOwned(launcherButton) then GameTooltip:Hide() end
    LayoutFlyout(flyout)
    PlaceFlyout(flyout)
    flyout:Show()
    PlaySound("igMainMenuOpen")
end

launcherButton:SetScript("OnClick", ToggleLauncherFlyout)
launcherButton:SetScript("OnEnter", function(self)
    if launcherFlyout and launcherFlyout:IsShown() then return end
    if launcher then ShowLauncherTooltip(self, launcher.title, nil, launcher.description) end
end)
launcherButton:SetScript("OnLeave", function() GameTooltip:Hide() end)

-- The skin pass for the launcher: chrome like its neighbours, the owner's glyph as its own ARTWORK texture
-- (the PVP button's pattern), the glyph again as the additive highlight; pushed while the flyout is open.
local function SetupLauncherButton(button, useGrayscale)
    local icon = launcher and launcher.icon
    local offX, offY = button:GetPushedTextOffset()
    offX, offY = offX or 0, offY or 0
    local sizeX, sizeY = button:GetSize()
    local glyphSize = useGrayscale and 12 or 20

    local glyph = button.AddicatUILauncherIcon or button:CreateTexture(nil, "ARTWORK")
    button.AddicatUILauncherIcon = glyph
    PaintLauncherIcon(glyph, icon, useGrayscale)
    glyph:SetSize(glyphSize, glyphSize)
    glyph:Show()

    local highlight = button:GetHighlightTexture()
    if highlight then
        PaintLauncherIcon(highlight, icon, useGrayscale)
        highlight:ClearAllPoints()
        highlight:SetSize(glyphSize, glyphSize)
        highlight:SetPoint("CENTER", glyph, "CENTER", 0, 0)
    end

    if useGrayscale then
        if button.AddicatUIBackground then button.AddicatUIBackground:Hide() end
        if button.AddicatUIBackgroundPushed then button.AddicatUIBackgroundPushed:Hide() end
    else
        local bg = button.AddicatUIBackground or button:CreateTexture(nil, 'BACKGROUND')
        button.AddicatUIBackground = bg
        bg:SetTexture(LAUNCHER_CHROME)
        bg:SetTexCoord(0.0654297, 0.12793, 0.330078, 0.490234)
        bg:ClearAllPoints()
        bg:SetSize(sizeX, sizeY + 1)
        bg:SetPoint('CENTER', -1, 1)
        local bgPushed = button.AddicatUIBackgroundPushed or button:CreateTexture(nil, 'BACKGROUND')
        button.AddicatUIBackgroundPushed = bgPushed
        bgPushed:SetTexture(LAUNCHER_CHROME)
        bgPushed:SetTexCoord(0.0654297, 0.12793, 0.494141, 0.654297)
        bgPushed:ClearAllPoints()
        bgPushed:SetSize(sizeX, sizeY + 1)
        bgPushed:SetPoint('CENTER', -1 + offX, 1 + offY)
    end

    local open = launcherFlyout and launcherFlyout:IsShown() and true or false
    button.addicatUIState = button.addicatUIState or {}
    button.addicatUIState.pushed = open
    button.addicatUILastState = open
    button.HandleAddicatUIState = function()
        local pushed = button.addicatUIState and button.addicatUIState.pushed
        glyph:ClearAllPoints()
        glyph:SetPoint('CENTER', button, 'CENTER', pushed and offX or 0, (pushed and offY or 0) + 1)
        glyph:SetAlpha(pushed and 0.75 or 1)
        if not useGrayscale then
            if pushed then
                button.AddicatUIBackground:Hide()
                button.AddicatUIBackgroundPushed:Show()
            else
                button.AddicatUIBackground:Show()
                button.AddicatUIBackgroundPushed:Hide()
            end
        end
    end
    button.HandleAddicatUIState()

    if not button.AddicatUIStateHooks then
        button:HookScript('OnMouseDown', function(self)
            ApplyMicroButtonPushed(self, true)
        end)
        button:HookScript('OnMouseUp', function(self)
            ApplyMicroButtonPushed(self, launcherFlyout and launcherFlyout:IsShown() and true or false)
        end)
        button.AddicatUIStateHooks = true
    end

    -- Hovering it reveals a hover-faded strip like its neighbours (mainbars lists the stock names only).
    -- The flyout stays out of that list: a fade must never turn its mouse off while it is open.
    if addon.VisibilityFade and addon.VisibilityFade.AddHoverFrames then
        addon.VisibilityFade.AddHoverFrames("micro", { button })
    end
end

-- Shown only with a launcher registered and the option on (micromenu.show_launcher).
local function SyncLauncherSuppression()
    local mm = addon.db and addon.db.profile and addon.db.profile.micromenu
    local wanted = launcher ~= nil and not (mm and mm.show_launcher == false)
    launcherButton.addicatUISuppressed = (not wanted) or nil
    if not wanted then
        if launcherFlyout then launcherFlyout:Hide() end
        launcherButton:Hide()
    end
    return wanted
end

local function SetupCharacterButton(button)
    -- STEP 1: Use Blizzard's native portrait
    local portraitTexture = MicroButtonPortrait
    if not portraitTexture then
        return
    end
    portraitTexture:ClearAllPoints()
    portraitTexture:SetPoint('CENTER', button, 'CENTER', 0, -0.5)
    portraitTexture:SetSize(18, 24)
    portraitTexture:SetAlpha(1)

    -- Hide Blizzard's native normal/pushed/highlight textures so they
    -- don't bleed through as a background after /reload.  We use our
    -- own AddicatUIBackground/BackgroundPushed instead.
    local nt = button:GetNormalTexture()
    if nt then nt:SetTexture(nil) end
    local pt = button:GetPushedTexture()
    if pt then pt:SetTexture(nil) end
    local ht = button:GetHighlightTexture()
    if ht then ht:SetTexture(nil) end
    local dt = button:GetDisabledTexture()
    if dt then dt:SetTexture(nil) end

    -- STEP 2: Hover highlight — OVERLAY with ADD blend.
    -- Uses SetPortraitTexture directly (not GetTexture clone, which returns
    -- nil for 3D portrait renders). SetAllPoints(portraitTexture) guarantees
    -- identical position/size — same technique as AddicatUIPortraitDim.
    local function RefreshCharHighlight(btn)
        local hl = btn.AddicatUICharHighlight
        if not hl then return end
        SetPortraitTexture(hl, "player")
        hl:SetTexCoord(MicroButtonPortrait:GetTexCoord())
        hl:SetBlendMode('ADD')
        hl:SetAlpha(1)
        hl:SetAllPoints(MicroButtonPortrait)
    end

    if not button.AddicatUICharHighlight then
        local hl = button:CreateTexture(nil, 'OVERLAY')
        hl:SetAllPoints(portraitTexture)
        hl:Hide()
        button.AddicatUICharHighlight = hl

        button:HookScript('OnEnter', function(self)
            if self.AddicatUICharHighlight then
                RefreshCharHighlight(self)
                self.AddicatUICharHighlight:Show()
            end
        end)
        button:HookScript('OnLeave', function(self)
            if self.AddicatUICharHighlight then
                self.AddicatUICharHighlight:Hide()
            end
        end)
    end

    -- Global function hooks: must re-register every reload (Lua state resets).
    -- Sync highlight TexCoord and force portrait alpha=1 so Blizzard's
    -- SetPushed/SetNormal don't darken the portrait.
    if not charPushHooksRegistered then
        hooksecurefunc('CharacterMicroButton_SetPushed', function()
            if not MicromenuModule.applied or not IsModuleEnabled() then
                return
            end

            local isGS = addon and addon.db and addon.db.profile
                and addon.db.profile.micromenu and addon.db.profile.micromenu.grayscale_icons
            if isGS then return end
            MicroButtonPortrait:SetAlpha(0.7)
            local nt = button:GetNormalTexture()
            if nt then nt:SetTexture(nil) end
            local pt = button:GetPushedTexture()
            if pt then pt:SetTexture(nil) end
            local hl = button.AddicatUICharHighlight
            if hl and hl:IsShown() then
                hl:SetTexCoord(MicroButtonPortrait:GetTexCoord())
            end
        end)
        hooksecurefunc('CharacterMicroButton_SetNormal', function()
            if not MicromenuModule.applied or not IsModuleEnabled() then
                return
            end

            local isGS = addon and addon.db and addon.db.profile
                and addon.db.profile.micromenu and addon.db.profile.micromenu.grayscale_icons
            if isGS then return end
            MicroButtonPortrait:SetAlpha(1)
            local nt = button:GetNormalTexture()
            if nt then nt:SetTexture(nil) end
            local pt = button:GetPushedTexture()
            if pt then pt:SetTexture(nil) end
            local hl = button.AddicatUICharHighlight
            if hl and hl:IsShown() then
                hl:SetTexCoord(MicroButtonPortrait:GetTexCoord())
            end
        end)
        charPushHooksRegistered = true
    end
    RefreshCharHighlight(button)
    button.AddicatUICharHighlight:Hide()

    -- Keep highlight in sync when portrait model updates (first login).
    if not button.AddicatUIPortraitEventRegistered then
        button:RegisterEvent("UNIT_PORTRAIT_UPDATE")
        button:HookScript("OnEvent", function(self, event, unit)
            if event == "UNIT_PORTRAIT_UPDATE" and unit == "player" then
                local isGrayscale = addon and addon.db and addon.db.profile
                    and addon.db.profile.micromenu and addon.db.profile.micromenu.grayscale_icons
                if isGrayscale then return end
                RefreshCharHighlight(self)
            end
        end)
        button.AddicatUIPortraitEventRegistered = true
    end

    -- STEP 3: Background only (like other buttons)
    if not button.AddicatUIBackground then
        local microTexture = 'Interface\\AddOns\\AddicatUI_Art\\Textures\\Micromenu\\uimicromenu2x'
        local dx, dy = -1, 1
        local offX, offY = button:GetPushedTextOffset()
        local sizeX, sizeY = button:GetSize()

        local bg = button:CreateTexture(nil, 'BACKGROUND')
        bg:SetTexture(microTexture)
        bg:SetSize(sizeX, sizeY + 1)
        bg:SetTexCoord(0.0654297, 0.12793, 0.330078, 0.490234)
        bg:SetPoint('CENTER', dx, dy)
        button.AddicatUIBackground = bg

        local bgPushed = button:CreateTexture(nil, 'BACKGROUND')
        bgPushed:SetTexture(microTexture)
        bgPushed:SetSize(sizeX, sizeY + 1)
        bgPushed:SetTexCoord(0.0654297, 0.12793, 0.494141, 0.654297)
        bgPushed:SetPoint('CENTER', dx + offX, dy + offY)
        bgPushed:Hide()
        button.AddicatUIBackgroundPushed = bgPushed

        -- STEP 3: Initialize state tracking properties
        button.addicatUIState = {
            pushed = IsSpecialMicroButtonActive(button, "Character")
        }
        button.addicatUILastState = button.addicatUIState.pushed

        button.HandleAddicatUIState = function()
            local state = button.addicatUIState
            if state and state.pushed then
                MicroButtonPortrait:SetAlpha(0.7)
                bg:Hide()
                bgPushed:Show()
            else
                MicroButtonPortrait:SetAlpha(1)
                bg:Show()
                bgPushed:Hide()
            end
        end

        button.HandleAddicatUIState()
    else
        -- Re-apply geometry/visibility every pass to survive late Blizzard updates.
        local microTexture = 'Interface\\AddOns\\AddicatUI_Art\\Textures\\Micromenu\\uimicromenu2x'
        local dx, dy = -1, 1
        local offX, offY = button:GetPushedTextOffset()
        local sizeX, sizeY = button:GetSize()

        button.AddicatUIBackground:SetTexture(microTexture)
        button.AddicatUIBackground:SetTexCoord(0.0654297, 0.12793, 0.330078, 0.490234)
        button.AddicatUIBackground:ClearAllPoints()
        button.AddicatUIBackground:SetPoint('CENTER', dx, dy)
        button.AddicatUIBackground:SetSize(sizeX, sizeY + 1)

        if button.AddicatUIBackgroundPushed then
            button.AddicatUIBackgroundPushed:SetTexture(microTexture)
            button.AddicatUIBackgroundPushed:SetTexCoord(0.0654297, 0.12793, 0.494141, 0.654297)
            button.AddicatUIBackgroundPushed:ClearAllPoints()
            button.AddicatUIBackgroundPushed:SetPoint('CENTER', dx + offX, dy + offY)
            button.AddicatUIBackgroundPushed:SetSize(sizeX, sizeY + 1)
        end

        button.addicatUIState = button.addicatUIState or { pushed = false }

        -- Delegate to the existing handler for consistent state application
        if button.HandleAddicatUIState then
            button.HandleAddicatUIState()
        end
    end
end

function MainMenuMicroButtonMixin:SetupBagButtons()
    MicromenuModule.hooks = MicromenuModule.hooks or {}

    local BORDER_GLOW = "bag-border-highlight-2x"
    local BACKPACK_GLOW = "bag-main-highlight-2x"

    local BUTTON_FACE_ORDER = { "Normal", "Pushed", "Highlight", "Checked" }
    local SLOT_FACE_ORDER = { "Highlight", "Checked", "Pushed", "Normal" }

    -- A face missing from the table is set to nil.
    local function ResetFaces(button, order, faces)
        for _, face in ipairs(order) do
            button["Set" .. face .. "Texture"](button, faces[face])
        end
    end

    local function StretchAdditive(region, owner)
        region:SetAllPoints(owner)
        region:SetBlendMode("ADD")
    end

    local function StyleBorderGlows(button)
        local hover = button:GetHighlightTexture()
        StretchAdditive(hover, button)
        hover:SetAlpha(0.4)
        hover:SetAtlasTexture(BORDER_GLOW, true)

        local pressed = button:GetCheckedTexture()
        StretchAdditive(pressed, button)
        pressed:SetDrawLayer("OVERLAY", 7)
        pressed:SetAtlasTexture(BORDER_GLOW)
    end

    local function DressIconAndCount(button)
        local buttonName = button:GetName()
        local icon = _G[buttonName .. "IconTexture"]
        if icon then
            icon:ClearAllPoints()
            icon:SetPoint("TOPRIGHT", button, "TOPRIGHT", -5, -2.9)
            icon:SetPoint("BOTTOMLEFT", button, "BOTTOMLEFT", 2.9, 5)
            pcall(icon.SetTexCoord, icon, 0.08, 0.92, 0.08, 0.92)
        end
        local stackCount = _G[buttonName .. "Count"]
        if stackCount then
            stackCount:SetSinglePoint("CENTER", button, "CENTER", 0, -10)
            stackCount:SetDrawLayer("OVERLAY")
        end
    end

    local backpack = MainMenuBarBackpackButton
    backpack:SetSize(50, 50)
    ResetFaces(backpack, BUTTON_FACE_ORDER, { Highlight = "", Checked = "" })
    StretchAdditive(backpack:GetHighlightTexture(), backpack)
    backpack:GetHighlightTexture():SetAtlasTexture(BACKPACK_GLOW)
    local backpackChecked = backpack:GetCheckedTexture()
    StretchAdditive(backpackChecked, backpack)
    backpackChecked:SetDrawLayer("OVERLAY", 7)
    backpackChecked:SetAtlasTexture(BACKPACK_GLOW)
    _G.MainMenuBarBackpackButtonIconTexture:SetAtlasTexture("bag-main-2x")
    _G.MainMenuBarBackpackButtonCount:SetSinglePoint("CENTER", backpack, "BOTTOM", 0, 14)
    CharacterBag0Slot:SetSinglePoint("RIGHT", backpack, "LEFT", -14, -2)

    if KeyRingButton then
        KeyRingButton:SetSize(34, 34)
        KeyRingButton:SetSinglePoint("RIGHT", CharacterBag3Slot, "LEFT", -4, 0)
        ResetFaces(KeyRingButton, BUTTON_FACE_ORDER, { Normal = "", Highlight = "", Checked = "" })
        KeyRingButton:GetNormalTexture():SetAtlasTexture("bag-reagent-border-2x")
        StyleBorderGlows(KeyRingButton)
    end

    -- Bagster replaces ContainerFrame_OnShow checked sync; highlight backpack/bag slots instead
    local function SyncKeyRingButton()
        if addon.BagsterModule and addon.BagsterModule.BagsterModule
            and addon.BagsterModule.BagsterModule.applied
            and addon.BagsterHighlightMainMenuBags then
            addon.BagsterHighlightMainMenuBags()
            return
        end
        if KeyRingButton then
            KeyRingButton:SetChecked(IsBagOpen(-2) and 1 or nil)
        end
    end

    if not MicromenuModule.hooks.KeyRingSyncHooks then
        hooksecurefunc("ToggleKeyRing", SyncKeyRingButton)
        hooksecurefunc("CloseAllBags", function()
            if addon.BagsterModule and addon.BagsterModule.BagsterModule
                and addon.BagsterModule.BagsterModule.applied
                and addon.BagsterHighlightMainMenuBags then
                addon.BagsterHighlightMainMenuBags()
                return
            end
            if KeyRingButton then
                KeyRingButton:SetChecked(nil)
            end
        end)
        hooksecurefunc("ContainerFrame_OnHide", SyncKeyRingButton)
        MicromenuModule.hooks.KeyRingSyncHooks = true
    end

    if KeyRingButton then
        DressIconAndCount(KeyRingButton)
    end

    for _, slot in ipairs(bagslots) do
        ResetFaces(slot, SLOT_FACE_ORDER, { Normal = "", Highlight = "", Checked = "" })
        slot:SetSize(28, 28)

        local plate = slot:GetNormalTexture()
        if plate then
            plate:SetAlpha(0)
            plate:Hide()
        end
        StyleBorderGlows(slot)
        DressIconAndCount(slot)

        local ring = slot.customBorder
        if not ring then
            ring = slot:CreateTexture(nil, "OVERLAY")
            ring:SetPoint("CENTER", slot, "CENTER")
            ring:SetAtlasTexture("bag-border-2x", true)
            slot.customBorder = ring
        end

        local backdrop = slot.background
        if not backdrop then
            backdrop = slot:CreateTexture(nil, "BACKGROUND")
            backdrop:SetSize(ring:GetWidth(), ring:GetHeight())
            backdrop:SetPoint("CENTER", slot, "CENTER")
            backdrop:SetTexture(addon._dir .. "Bags\\bagslots2x")
            backdrop:SetTexCoord(295 / 512, 356 / 512, 64 / 128, 125 / 128)
            slot.background = backdrop
        end

        for _, layer in ipairs({ ring, backdrop }) do
            layer:Show()
            layer:SetAlpha(1)
        end
    end

    if not bagsBar.registeredInEditor then
        -- Calculate overlay size to exactly match the visible bag elements.
        -- Layout (right to left from backpack right edge):
        --   Backpack(50) + gap(14) + 4xBag(28)+3xgap(4) = 188
        --   + KeyRing gap(4) + KeyRing(34) = 226
        -- Keep the editor frame at max width so gaining the keyring after
        -- a reload does not shift center-anchored saved positions.
        local bagsOverlayWidth = 226
        local bagsOverlayHeight = 54

        -- Create container frame using the standard system
        local bagsFrame = addon.CreateUIFrame(bagsOverlayWidth, bagsOverlayHeight, "BagsBar")

        -- Apply position from database or use default
        local bagsConfig = addon.db and addon.db.profile.widgets and addon.db.profile.widgets.bagsbar
        if bagsConfig and bagsConfig.anchor then
            bagsFrame:SetPoint(bagsConfig.anchor or "BOTTOMRIGHT", UIParent, bagsConfig.anchor or "BOTTOMRIGHT",
                bagsConfig.posX or -3, bagsConfig.posY or 45)
        else
            bagsFrame:SetPoint("BOTTOMRIGHT", UIParent, "BOTTOMRIGHT", -3, 45)
        end

        -- Anchor backpack to the RIGHT edge of the overlay.
        -- The backpack is 50px wide; anchoring its RIGHT to the frame's
        -- RIGHT edge aligns it flush.  All other bags chain LEFT of the
        -- backpack, so the whole row fits perfectly inside the frame.
        MainMenuBarBackpackButton:SetParent(UIParent)
        MainMenuBarBackpackButton:ClearAllPoints()
        MainMenuBarBackpackButton:SetPoint("RIGHT", bagsFrame, "RIGHT", 0, 0)

        -- Hook so bags follow the container when it moves
        bagsFrame:HookScript("OnDragStop", function(self)
            MainMenuBarBackpackButton:ClearAllPoints()
            MainMenuBarBackpackButton:SetPoint("RIGHT", self, "RIGHT", 0, 0)
        end)

        bagsFrame:HookScript("OnShow", function(self)
            MainMenuBarBackpackButton:ClearAllPoints()
            MainMenuBarBackpackButton:SetPoint("RIGHT", self, "RIGHT", 0, 0)
        end)

        -- Defensive maintenance hook. Throttled to avoid per-frame work when the
        -- backpack button is already anchored correctly.
        bagsFrame._duiBackpackCheckElapsed = 0
        bagsFrame:HookScript("OnUpdate", function(self, elapsed)
            self._duiBackpackCheckElapsed = self._duiBackpackCheckElapsed + elapsed
            if self._duiBackpackCheckElapsed < 0.2 then
                return
            end

            self._duiBackpackCheckElapsed = 0
            if not MainMenuBarBackpackButton:GetPoint() then
                MainMenuBarBackpackButton:ClearAllPoints()
                MainMenuBarBackpackButton:SetPoint("RIGHT", self, "RIGHT", 0, 0)
            end
        end)

        addon:RegisterEditableFrame({
            name = "bagsbar",
            frame = bagsFrame,
            blizzardFrame = MainMenuBarBackpackButton,
            configPath = {"widgets", "bagsbar"},
            module = addon.BagsModule or {}
        })

        bagsBar.registeredInEditor = true

    end

    HideUnwantedBagFrames()
    -- A single deferred pass handles any late-created child textures
    -- (e.g. addons styling bag slots after us). The debounced scheduler
    -- collapses any additional calls to a single execution.
    ScheduleHideFrames(1.0)
end

function MainMenuMicroButtonMixin:bagbuttons_reposition()
    local bagScale = addon.db and addon.db.profile and addon.db.profile.bags and addon.db.profile.bags.scale or 1.0
    MainMenuBarBackpackButton:SetScale(bagScale)
    local bagsWidget = addon:GetEditableFrameInfo("bagsbar")
    if bagsWidget then addon.SetEditorBoxScale(bagsWidget.frame, bagScale, "RIGHT") end

    CharacterBag0Slot:SetSinglePoint('RIGHT', MainMenuBarBackpackButton, 'LEFT', -14, -2)

    if not GetBagCollapseState() then
        StopCollapsedSecondaryFade()
        -- Expanded state
        for i, bags in pairs(bagslots) do
            bags:Show()
            bags:SetAlpha(1)
            bags:SetFrameLevel(MainMenuBarBackpackButton:GetFrameLevel())
            bags:SetScale(1.0)
            bags:SetSize(28, 28)

            if i == 1 then
                -- Already positioned above
            elseif i == 2 then
                bags:SetSinglePoint('RIGHT', CharacterBag0Slot, 'LEFT', -4, 0)
            elseif i == 3 then
                bags:SetSinglePoint('RIGHT', CharacterBag1Slot, 'LEFT', -4, 0)
            elseif i == 4 then
                bags:SetSinglePoint('RIGHT', CharacterBag2Slot, 'LEFT', -4, 0)
            end

            if bags.customBorder then
                bags.customBorder:SetAlpha(1)
            end
            if bags.background then
                bags.background:SetAlpha(1)
            end
        end

        if KeyRingButton then
            KeyRingButton:SetSinglePoint('RIGHT', CharacterBag3Slot, 'LEFT', -4, 0)
            KeyRingButton:SetFrameLevel(MainMenuBarBackpackButton:GetFrameLevel())
            KeyRingButton:SetScale(1.0)
            KeyRingButton:SetSize(34, 34)
        end
    else
        -- Collapsed state - bags behind main bag
        local forceHideCollapsed = ShouldForceCollapsedSecondaryInvisible()
        if forceHideCollapsed then
            StopCollapsedSecondaryFade()
        end
        for i, bags in pairs(bagslots) do
            bags:Show()
            bags:SetAlpha(forceHideCollapsed and 0 or 1)
            bags:ClearAllPoints()
            bags:SetPoint('CENTER', MainMenuBarBackpackButton, 'CENTER', 0, 0)
            bags:SetFrameLevel(MainMenuBarBackpackButton:GetFrameLevel() - 1)

            if bags.customBorder then
                bags.customBorder:SetAlpha(forceHideCollapsed and 0 or 1)
            end
            if bags.background then
                bags.background:SetAlpha(forceHideCollapsed and 0 or 1)
            end

            local icon = _G[bags:GetName() .. 'IconTexture']
            if icon then
                icon:SetAlpha(forceHideCollapsed and 0 or 1)
            end
        end

        if KeyRingButton then
            KeyRingButton:ClearAllPoints()
            KeyRingButton:SetPoint('CENTER', MainMenuBarBackpackButton, 'CENTER', 0, 0)
            KeyRingButton:SetFrameLevel(MainMenuBarBackpackButton:GetFrameLevel() - 1)
        end

        if not forceHideCollapsed and addon.RefreshCollapsedSecondaryBagsVisibility and _G.AddicatUI_BagButtonBar then
            addon.RefreshCollapsedSecondaryBagsVisibility((_G.AddicatUI_BagButtonBar:GetAlpha() or 1) > 0.01)
        end
    end

end

function MainMenuMicroButtonMixin:bagbuttons_refresh()
    if _G.AddicatUI_BagButtonBar then
        for _, bags in pairs(bagslots) do
            if bags:GetParent() ~= _G.AddicatUI_BagButtonBar then
                bags:SetParent(_G.AddicatUI_BagButtonBar);
            end
        end
    end

    self:SetupBagButtons();

    SyncKeyRingToKeys()

    -- Update bag slot icons with delayed stabilization for reload timing.
    ScheduleBagSlotIconRefreshes()

    HideUnwantedBagFrames()
end

local function MigrateMicroIconSpacingToPadding()
    local mm = addon.db and addon.db.profile and addon.db.profile.micromenu
    if not mm or mm.spacing_is_padding then
        return
    end
    mm.spacing_is_padding = true
    -- Old values were origin-to-origin stride; convert once to edge padding.
    if mm.grayscale and mm.grayscale.icon_spacing ~= nil then
        mm.grayscale.icon_spacing = mm.grayscale.icon_spacing - 14
    end
    if mm.normal and mm.normal.icon_spacing ~= nil then
        mm.normal.icon_spacing = mm.normal.icon_spacing - 32
    end
end

-- addicatUISuppressed marks a button whose own module has been switched off. Skipping it here as well
-- as in the skin pass is what closes the gap it would otherwise leave in the strip.
local function CollectPresentMicroButtons()
    SyncLauncherSuppression()
    local list = {}
    for i = 1, #MICRO_BUTTONS do
        if MICRO_BUTTONS[i] and not MICRO_BUTTONS[i].addicatUISuppressed then
            list[#list + 1] = MICRO_BUTTONS[i]
        end
    end
    return list
end

local function GetMicroLayoutMetrics(config, useGrayscale, numButtons)
    local buttonWidth = useGrayscale and 14 or 32
    local buttonHeight = useGrayscale and 19 or 40
    local pad = tonumber(config.icon_spacing)
    if pad == nil then
        pad = useGrayscale and 1 or -6
    end
    local hStep = buttonWidth + pad
    local vStep = buttonHeight + pad
    local columns = math.floor(tonumber(config.columns) or 12)
    if columns < 1 then
        columns = 1
    end
    if numButtons < 1 then
        return buttonWidth, buttonHeight, hStep, vStep, 1, 1, buttonWidth, buttonHeight
    end
    if columns > numButtons then
        columns = numButtons
    end
    local rows = math.ceil(numButtons / columns)
    local totalWidth = columns * buttonWidth + (columns - 1) * pad
    local totalHeight = rows * buttonHeight + (rows - 1) * pad
    return buttonWidth, buttonHeight, hStep, vStep, columns, rows, totalWidth, totalHeight
end

local function LayoutMicroButtons()
    local menu = _G.AddicatUI_MicroButtonBar
    if not menu or not addon.db or not addon.db.profile or not addon.db.profile.micromenu then
        return
    end

    MigrateMicroIconSpacingToPadding()

    local useGrayscale = addon.db.profile.micromenu.grayscale_icons
    local config = addon.db.profile.micromenu[useGrayscale and "grayscale" or "normal"]
    if not config then
        return
    end

    local buttons = CollectPresentMicroButtons()
    local numButtons = #buttons
    if config.invert_order and numButtons > 1 then
        local reversed = {}
        for i = numButtons, 1, -1 do
            reversed[#reversed + 1] = buttons[i]
        end
        buttons = reversed
    end

    local _, _, hStep, vStep, columns, _, totalWidth, totalHeight =
        GetMicroLayoutMetrics(config, useGrayscale, numButtons)

    for i = 1, numButtons do
        local button = buttons[i]
        local idx = i - 1
        local x = (idx % columns) * hStep
        local y = MICRO_LAYOUT_BASE_Y + math.floor(idx / columns) * vStep

        if button.SetPoint == addon._noop then
            button.SetPoint = UIParent.SetPoint
        end
        button:ClearAllPoints()
        button:SetPoint("BOTTOMLEFT", menu, "BOTTOMRIGHT", x, y)
        button.SetPoint = addon._noop
    end

    local menuScale = config.scale_menu or 1
    local overlayWidth = (totalWidth + 10) * menuScale
    local overlayHeight = (totalHeight + 10) * menuScale
    local menuOffX = -(totalWidth / 2)
    local menuOffY = -(MICRO_LAYOUT_BASE_Y + totalHeight / 2)

    menu.editorOffX = menuOffX
    menu.editorOffY = menuOffY

    if menu.editorFrame and not InCombatLockdown() then
        menu.editorFrame:SetSize(overlayWidth, overlayHeight)
        menu:ClearAllPoints()
        menu:SetPoint("BOTTOMRIGHT", menu.editorFrame, "CENTER", menuOffX, menuOffY)
    end
end

-- A client shipping its own micro button can be short a state texture (#473: Whitemane's
-- CollectionsMicroButton has no disabled one), and the getter then returns nil.
local function SetMicroStateTexture(button, getter, setter, path, coords)
    if not (coords and #coords >= 4) then return end
    local tex = button[getter](button)
    if not tex then
        button[setter](button, path)
        tex = button[getter](button)
        if not tex then return end
    end
    tex:SetTexture(coords[5] or path)
    tex:SetTexCoord(coords[1], coords[2], coords[3], coords[4])
    tex:ClearAllPoints()
    tex:SetAllPoints(button)
end

local function layoutMicroButtons(xOffset)
    MigrateMicroIconSpacingToPadding()

    local useGrayscale = addon.db.profile.micromenu.grayscale_icons
    local configMode = useGrayscale and "grayscale" or "normal"
    local config = addon.db.profile.micromenu[configMode]

    local menuScale = config.scale_menu

    local menu = _G.AddicatUI_MicroButtonBar
    if not menu then
        menu = CreateFrame('Frame', 'AddicatUI_MicroButtonBar', UIParent)
    end
    menu:SetScale(menuScale)
    menu:SetSize(10, 10)

    local presentButtons = CollectPresentMicroButtons()
    local numButtons = #presentButtons
    local _, _, _, _, _, _, totalWidth, totalHeight =
        GetMicroLayoutMetrics(config, useGrayscale, numButtons)

    local overlayWidth = (totalWidth + 10) * menuScale
    local overlayHeight = (totalHeight + 10) * menuScale

    -- Offsets must stay unscaled: WoW multiplies SetPoint by the frame's own scale.
    local menuOffX = -(totalWidth / 2)
    local menuOffY = -(MICRO_LAYOUT_BASE_Y + totalHeight / 2)

    if not menu.registeredInEditor then
        -- PATTERN: Overlay = position anchor, real UI anchored TO overlay
        -- Same as PlayerFrame, TargetFrame, CastBar, etc.
        local microMenuFrame = addon.CreateUIFrame(overlayWidth, overlayHeight, "MicroMenu")

        -- Position the OVERLAY from saved config or defaults
        local microMenuConfig = addon.db and addon.db.profile.widgets and addon.db.profile.widgets.micromenu
        if microMenuConfig and microMenuConfig.posX and microMenuConfig.posY then
            microMenuFrame:SetPoint(microMenuConfig.anchor or "BOTTOMRIGHT", UIParent,
                microMenuConfig.anchor or "BOTTOMRIGHT",
                microMenuConfig.posX, microMenuConfig.posY)
        else
            microMenuFrame:SetPoint("BOTTOMRIGHT", UIParent, "BOTTOMRIGHT",
                xOffset + config.x_position, config.y_position)
        end

        -- Anchor the REAL menu TO the overlay (fixed offset based on button geometry)
        menu:SetParent(UIParent)
        menu:ClearAllPoints()
        menu:SetPoint("BOTTOMRIGHT", microMenuFrame, "CENTER", menuOffX, menuOffY)

        -- Store reference and offsets for re-anchoring
        menu.editorFrame = microMenuFrame
        menu.editorOffX = menuOffX
        menu.editorOffY = menuOffY

        addon:RegisterEditableFrame({
            name = "micromenu",
            frame = microMenuFrame,
            blizzardFrame = menu,
            configPath = {"widgets", "micromenu"},
            module = addon.MicroMenuModule or {},
            onHide = function()
                -- Re-anchor menu when leaving editor mode (overlay may have been dragged)
                menu:ClearAllPoints()
                menu:SetPoint("BOTTOMRIGHT", microMenuFrame, "CENTER",
                    menu.editorOffX or menuOffX, menu.editorOffY or menuOffY)
            end
        })

        menu.registeredInEditor = true
    else
        -- Subsequent calls: re-anchor to existing overlay
        if menu.editorFrame then
            menu:ClearAllPoints()
            menu:SetPoint("BOTTOMRIGHT", menu.editorFrame, "CENTER", menuOffX, menuOffY)
            menu.editorFrame:SetSize(overlayWidth, overlayHeight)
            menu.editorOffX = menuOffX
            menu.editorOffY = menuOffY
        end
    end

    -- Above MainMenuBarArtFrame (MainMenuBar+1), whose classic art otherwise covers the buttons.
    menu:SetFrameLevel(MainMenuBar:GetFrameLevel() + 2)

    for i = 1, #MICRO_BUTTONS do
        local button = MICRO_BUTTONS[i]
        if button and not button.addicatUISuppressed then
            local buttonName = button:GetName():gsub('MicroButton', '')
            local name = string.lower(buttonName);

            CaptureOriginalHandlers(button)

            button:StripOwnTextures()
            CharacterMicroButton:SetDisabledTexture ''

            button:SetParent(menu)

            if useGrayscale then
                button:SetSize(14, 19)
            else
                button:SetSize(32, 40)
            end

            button.SetPoint = addon._noop
            button:SetHitRectInsets(0, 0, 0, 0)

            button:EnableMouse(true)
            button:Show()

            local isCharacterButton = (buttonName == "Character")
            local isPVPButton = (buttonName == "PVP")

            local upCoords = not isCharacterButton and not isPVPButton and GetColoredTextureCoords(name, "Up") or nil
            local shouldUseGrayscale = useGrayscale or (not isPVPButton and not upCoords and not isCharacterButton)

            if button == launcherButton then
                SetupLauncherButton(button, useGrayscale)
            elseif shouldUseGrayscale then
                -- Grayscale icons
                local normalTexture = button:GetNormalTexture()
                local pushedTexture = button:GetPushedTexture()
                local disabledTexture = button:GetDisabledTexture()
                local highlightTexture = button:GetHighlightTexture()

                -- Ensure colored-only backgrounds do not bleed into grayscale mode.
                if button.AddicatUIBackground then
                    button.AddicatUIBackground:Hide()
                end
                if button.AddicatUIBackgroundPushed then
                    button.AddicatUIBackgroundPushed:Hide()
                end
                if button.AddicatUIHover then
                    button.AddicatUIHover:Hide()
                end

                if normalTexture then
                    normalTexture:SetAtlasTexture('ui-hud-micromenu-' .. name .. '-up-2x')
                end
                if pushedTexture then
                    pushedTexture:SetAtlasTexture('ui-hud-micromenu-' .. name .. '-down-2x')
                end
                if disabledTexture then
                    disabledTexture:SetAtlasTexture('ui-hud-micromenu-' .. name .. '-disabled-2x')
                end
                if highlightTexture then
                    highlightTexture:SetAtlasTexture('ui-hud-micromenu-' .. name .. '-mouseover-2x')
                end
            elseif isPVPButton then
                SetupPVPButton(button)
            elseif isCharacterButton then
                SetupCharacterButton(button)
            else
                -- Colored icons
                local microTexture = 'Interface\\AddOns\\AddicatUI_Art\\Textures\\Micromenu\\uimicromenu2x'

                local downCoords = GetColoredTextureCoords(name, "Down")
                local disabledCoords = GetColoredTextureCoords(name, "Disabled")
                local mouseoverCoords = GetColoredTextureCoords(name, "Mouseover")

                SetMicroStateTexture(button, 'GetNormalTexture', 'SetNormalTexture', microTexture, upCoords)
                SetMicroStateTexture(button, 'GetPushedTexture', 'SetPushedTexture', microTexture, downCoords)
                SetMicroStateTexture(button, 'GetDisabledTexture', 'SetDisabledTexture', microTexture, disabledCoords)
                SetMicroStateTexture(button, 'GetHighlightTexture', 'SetHighlightTexture', microTexture, mouseoverCoords)

                -- Add/update background (colored mode only)
                if not button.AddicatUIBackground then
                    local backgroundTexture = 'Interface\\AddOns\\AddicatUI_Art\\Textures\\Micromenu\\uimicromenu2x'
                    local dx, dy = -1, 1
                    local offX, offY = button:GetPushedTextOffset()
                    local sizeX, sizeY = button:GetSize()

                    -- Use anonymous textures; named globals collide across buttons.
                    local bg = button:CreateTexture(nil, 'BACKGROUND')
                    bg:SetTexture(backgroundTexture)
                    bg:SetSize(sizeX, sizeY + 1)
                    bg:SetTexCoord(0.0654297, 0.12793, 0.330078, 0.490234)
                    bg:SetPoint('CENTER', dx, dy)
                    button.AddicatUIBackground = bg

                    local bgPushed = button:CreateTexture(nil, 'BACKGROUND')
                    bgPushed:SetTexture(backgroundTexture)
                    bgPushed:SetSize(sizeX, sizeY + 1)
                    bgPushed:SetTexCoord(0.0654297, 0.12793, 0.494141, 0.654297)
                    bgPushed:SetPoint('CENTER', dx + offX, dy + offY)
                    bgPushed:Hide()
                    button.AddicatUIBackgroundPushed = bgPushed

                    local pushedNow = button:GetButtonState() == "PUSHED"
                    button.addicatUIState = {
                        pushed = pushedNow
                    }
                    button.addicatUILastState = pushedNow
                    -- Panel-open state from SetButtonState; mouse-hold is transient on the C side.
                    button.addicatUIPanelPushed = pushedNow

                    button.HandleAddicatUIState = function()
                        local state = button.addicatUIState
                        local hlTex = button:GetHighlightTexture()
                        if state and state.pushed then
                            button.AddicatUIBackground:Hide()
                            button.AddicatUIBackgroundPushed:Show()
                            if hlTex then
                                hlTex:ClearAllPoints()
                                hlTex:SetPoint('TOPLEFT', button, 'TOPLEFT', offX, offY)
                                hlTex:SetPoint('BOTTOMRIGHT', button, 'BOTTOMRIGHT', offX, offY)
                            end
                        else
                            button.AddicatUIBackground:Show()
                            button.AddicatUIBackgroundPushed:Hide()
                            if hlTex then
                                hlTex:ClearAllPoints()
                                hlTex:SetAllPoints(button)
                            end
                        end
                    end
                    button.HandleAddicatUIState()

                    -- MainMenu Blizzard OnUpdate must keep running; re-skin only if art drifts.
                    local origOnUpdate = button:GetScript('OnUpdate')
                    if buttonName == "MainMenu" and origOnUpdate then
                        local normalTexture = button:GetNormalTexture()
                        local guardPath = normalTexture and normalTexture:GetTexture()

                        local function ReapplyColoredArt(self)
                            local nt = self:GetNormalTexture()
                            if nt and upCoords then
                                nt:SetTexture(microTexture)
                                nt:SetTexCoord(upCoords[1], upCoords[2], upCoords[3], upCoords[4])
                                guardPath = nt:GetTexture()
                            end
                            local pt = self:GetPushedTexture()
                            if pt and downCoords then
                                pt:SetTexture(microTexture)
                                pt:SetTexCoord(downCoords[1], downCoords[2], downCoords[3], downCoords[4])
                            end
                            local dt = self:GetDisabledTexture()
                            if dt and disabledCoords then
                                dt:SetTexture(microTexture)
                                dt:SetTexCoord(disabledCoords[1], disabledCoords[2], disabledCoords[3], disabledCoords[4])
                            end
                            local ht = self:GetHighlightTexture()
                            if ht and mouseoverCoords then
                                ht:SetTexture(microTexture)
                                ht:SetTexCoord(mouseoverCoords[1], mouseoverCoords[2], mouseoverCoords[3], mouseoverCoords[4])
                            end
                        end

                        button:SetScript('OnUpdate', function(self, elapsed)
                            origOnUpdate(self, elapsed)

                            local nt = self:GetNormalTexture()
                            if not guardPath or not nt or nt:GetTexture() ~= guardPath then
                                ReapplyColoredArt(self)
                            end
                        end)
                    end

                    if not button.AddicatUIStateHooks then
                        button:HookScript("OnMouseDown", function(self)
                            ApplyMicroButtonPushed(self, true)
                        end)
                        button:HookScript("OnMouseUp", function(self)
                            ApplyMicroButtonPushed(self, self.addicatUIPanelPushed and true or false)
                        end)
                        button.AddicatUIStateHooks = true
                    end

                    if not button.AddicatUISetButtonStateHooked then
                        hooksecurefunc(button, "SetButtonState", function(self, state)
                            self.addicatUIPanelPushed = (state == "PUSHED")
                            ApplyMicroButtonPushed(self, self.addicatUIPanelPushed)
                        end)
                        button.AddicatUISetButtonStateHooked = true
                    end
                else
                    -- Re-apply size/position/visibility in case a late Blizzard pass altered regions.
                    local backgroundTexture = 'Interface\\AddOns\\AddicatUI_Art\\Textures\\Micromenu\\uimicromenu2x'
                    local dx, dy = -1, 1
                    local offX, offY = button:GetPushedTextOffset()
                    local sizeX, sizeY = button:GetSize()
                    button.AddicatUIBackground:SetTexture(backgroundTexture)
                    button.AddicatUIBackground:SetTexCoord(0.0654297, 0.12793, 0.330078, 0.490234)
                    button.AddicatUIBackground:ClearAllPoints()
                    button.AddicatUIBackground:SetPoint('CENTER', dx, dy)
                    button.AddicatUIBackground:SetSize(sizeX, sizeY + 1)
                    button.AddicatUIBackground:Show()

                    button.AddicatUIBackgroundPushed:SetTexture(backgroundTexture)
                    button.AddicatUIBackgroundPushed:SetTexCoord(0.0654297, 0.12793, 0.494141, 0.654297)
                    button.AddicatUIBackgroundPushed:ClearAllPoints()
                    button.AddicatUIBackgroundPushed:SetPoint('CENTER', dx + offX, dy + offY)
                    button.AddicatUIBackgroundPushed:SetSize(sizeX, sizeY + 1)
                    if button.addicatUIState and button.addicatUIState.pushed then
                        button.AddicatUIBackground:Hide()
                        button.AddicatUIBackgroundPushed:Show()
                    else
                        button.AddicatUIBackgroundPushed:Hide()
                    end
                end
            end

            local highlightTexture = button:GetHighlightTexture()
            if highlightTexture then
                highlightTexture:SetBlendMode('ADD')
                highlightTexture:SetAlpha(1)
            end

            button:EnableMouse(true)

            if buttonName ~= "Character" then
                RestoreOriginalHandlers(button)
            end
        end
    end
    LayoutMicroButtons()
    UpdateCharacterPortraitVisibility()

    -- Latency strip on HelpMicroButton: green / yellow / red from GetNetStats.
    local showLatency = addon.db.profile.micromenu.show_latency_indicator
    if showLatency and HelpMicroButton then
        if not MicromenuModule.frames.latencyIndicator then
            local latencyBar = CreateFrame("StatusBar", "AddicatUIPerformanceBar", HelpMicroButton)

            latencyBar:SetStatusBarTexture(addon._dir .. "Micromenu\\ui-mainmenubar-performancebar")
            latencyBar:SetStatusBarColor(0, 1, 0)
            latencyBar:GetStatusBarTexture():SetBlendMode("ADD")
            latencyBar:GetStatusBarTexture():SetDrawLayer("OVERLAY")

            latencyBar:EnableMouse(true)
            latencyBar:SetScript("OnEnter", function(self)
                GameTooltip:SetOwner(self, "ANCHOR_TOP")
                local _, _, latency = GetNetStats()
                latency = latency or 0
                GameTooltip:AddLine(L and L["Network"] or "Network", 1, 1, 1)
                GameTooltip:AddDoubleLine(L and L["Latency"] or "Latency", latency .. " ms", 1, 1, 1, 1, 1, 0)
                GameTooltip:Show()
            end)
            latencyBar:SetScript("OnLeave", function()
                GameTooltip:Hide()
            end)

            local function UpdateLatencyColor(self)
                local _, _, latency = GetNetStats()
                latency = latency or 0
                if latency > PERFORMANCEBAR_MEDIUM_LATENCY then
                    self:SetStatusBarColor(1, 0, 0)
                elseif latency > PERFORMANCEBAR_LOW_LATENCY then
                    self:SetStatusBarColor(1, 1, 0)
                else
                    self:SetStatusBarColor(0, 1, 0)
                end
            end

            latencyBar:SetScript("OnShow", function(self)
                UpdateLatencyColor(self)
                if not self.duiLatencyTimer and addon.core then
                    self.duiLatencyTimer = addon.core:ScheduleRepeatingTimer(UpdateLatencyColor,
                        PERFORMANCEBAR_UPDATE_INTERVAL or 10, self)
                end
            end)
            latencyBar:SetScript("OnHide", function(self)
                if self.duiLatencyTimer and addon.core then
                    addon.core:CancelTimer(self.duiLatencyTimer, true)
                    self.duiLatencyTimer = nil
                end
            end)

            -- Created shown; Hide so the Show() below fires OnShow and starts the timer.
            latencyBar:Hide()

            MicromenuModule.frames.latencyIndicator = latencyBar
        end

        local bar = MicromenuModule.frames.latencyIndicator
        bar:SetParent(HelpMicroButton)
        bar:SetFrameStrata(HelpMicroButton:GetFrameStrata())
        bar:SetFrameLevel(math.max(1, HelpMicroButton:GetFrameLevel() - 1))

        local barW, barH, offX, offY
        if useGrayscale then
            barW, barH = 13, 36
            offX, offY = 0, -3
        else
            barW, barH = 22, 60
            offX, offY = 1, -6.5
        end

        bar:ClearAllPoints()
        bar:SetSize(barW, barH)
        bar:SetPoint("BOTTOM", HelpMicroButton, "BOTTOM", offX, offY)
        -- Only rows 57-59 (x 4-27) of the 32x64 art are drawn; the rest must not catch hovers.
        bar:SetHitRectInsets(barW * 4 / 32, barW * 4 / 32, barH * 57 / 64, barH * 4 / 64)

        bar:Show()
    elseif MicromenuModule.frames.latencyIndicator then
        MicromenuModule.frames.latencyIndicator:Hide()
    end
end

function addon.RefreshBagsPosition()
    if not _G.AddicatUI_BagButtonBar then
        return
    end

    local scale = addon.db and addon.db.profile and addon.db.profile.bags and addon.db.profile.bags.scale
    if scale then
        _G.AddicatUI_BagButtonBar:SetScale(scale)
        MainMenuBarBackpackButton:SetScale(scale)
    end

    local frameInfo = addon:GetEditableFrameInfo("bagsbar")
    if frameInfo then addon.SetEditorBoxScale(frameInfo.frame, scale or 1, "RIGHT") end
    if frameInfo and frameInfo.frame then
        -- Apply position from database or use default
        local bagsConfig = addon.db and addon.db.profile.widgets and addon.db.profile.widgets.bagsbar
        if bagsConfig and bagsConfig.anchor then
            frameInfo.frame:ClearAllPoints()
            frameInfo.frame:SetPoint(bagsConfig.anchor or "BOTTOMRIGHT", UIParent,
                bagsConfig.anchor or "BOTTOMRIGHT", bagsConfig.posX or -3, bagsConfig.posY or 45)
        else
            frameInfo.frame:ClearAllPoints()
            frameInfo.frame:SetPoint("BOTTOMRIGHT", UIParent, "BOTTOMRIGHT", -3, 45)
        end

        -- Ensure bags follow the container — backpack flush to the
        -- RIGHT edge, all other bags chain leftward from it.
        MainMenuBarBackpackButton:ClearAllPoints()
        MainMenuBarBackpackButton:SetPoint("RIGHT", frameInfo.frame, "RIGHT", 0, 0)
    else
        -- Fallback to previous method if no container
        if not addon.db or not addon.db.profile or not addon.db.profile.bags then
            return
        end

        local bagsConfig = addon.db.profile.bags
        _G.AddicatUI_BagButtonBar:SetScale(bagsConfig.scale)

        local originalSetPoint = MainMenuBarBackpackButton.SetPoint
        if MainMenuBarBackpackButton.SetPoint == addon._noop then
            MainMenuBarBackpackButton.SetPoint = UIParent.SetPoint
        end

        MainMenuBarBackpackButton:ClearAllPoints()
        MainMenuBarBackpackButton:SetPoint('BOTTOMRIGHT', UIParent, 'BOTTOMRIGHT', bagsConfig.x_position,
            bagsConfig.y_position)

        if originalSetPoint == addon._noop then
            MainMenuBarBackpackButton.SetPoint = originalSetPoint
        end
    end
end

function addon.RefreshMicromenuVehicle()
    if not _G.AddicatUI_MicroButtonBar then
        return
    end

    if InCombatLockdown() then
        if addon.CombatQueue then
            addon.CombatQueue:Add("micromenu_refresh_vehicle", addon.RefreshMicromenuVehicle)
        end
        return
    end

    if addon.db.profile.micromenu.hide_on_vehicle then
        RegisterStateDriver(_G.AddicatUI_MicroButtonBar, 'visibility', '[vehicleui] hide;show')
    else
        UnregisterStateDriver(_G.AddicatUI_MicroButtonBar, 'visibility')
    end
end

function addon.RefreshBagsVehicle()
    if not _G.AddicatUI_BagButtonBar then
        return
    end

    if InCombatLockdown() then
        if addon.CombatQueue then
            addon.CombatQueue:Add("micromenu_refresh_bags_vehicle", addon.RefreshBagsVehicle)
        end
        return
    end

    if addon.db.profile.micromenu.hide_on_vehicle then
        RegisterStateDriver(_G.AddicatUI_BagButtonBar, 'visibility', '[vehicleui] hide;show')
    else
        UnregisterStateDriver(_G.AddicatUI_BagButtonBar, 'visibility')
    end
end

function addon.RefreshMicromenu()
if not addon.db or not addon.db.profile or not addon.db.profile.micromenu then
    return
end

if not _G.AddicatUI_MicroButtonBar then
    return
end

local useGrayscale = addon.db.profile.micromenu.grayscale_icons
local configMode = useGrayscale and "grayscale" or "normal"
local config = addon.db.profile.micromenu[configMode]

-- Scale only: the editor overlay owns the position.
_G.AddicatUI_MicroButtonBar:SetScale(config.scale_menu)

LayoutMicroButtons()

addon.RefreshMicromenuVehicle()
UpdateCharacterPortraitVisibility()
end

-- For a button switched back on while playing: RefreshMicromenu only re-places, it never skins.
function addon.RefreshMicromenuButtons()
    if not MicromenuModule.applied or not IsModuleEnabled() or not _G.AddicatUI_MicroButtonBar then
        return
    end
    layoutMicroButtons(HasCollectionsButton() and -180 or -166)
    addon.RefreshMicromenu()
end

-- The micro menu option, a profile switch or a late registration: in or out of the strip, skinned when back.
function addon.RefreshMicroMenuLauncher(live)
    if not SyncLauncherSuppression() then
        if addon.RefreshMicromenu then addon.RefreshMicromenu() end
    elseif live and IsLoggedIn() then
        addon.RefreshMicromenuButtons()
    end
end

-- Whether a launcher has its place in the strip: the micro menu module on and its option (show_launcher) not off.
-- Bleakhold reads it to keep its minimap buttons off while the launcher lists its windows.
function addon.MicroMenuLauncherAvailable()
    local mm = addon.db and addon.db.profile and addon.db.profile.micromenu
    return (IsModuleEnabled() and not (mm and mm.show_launcher == false)) and true or false
end

-- Another addon's launcher (Bleakhold's); one at a time, a second id replaces the first. Returns true when taken.
function addon.RegisterMicroMenuLauncher(spec)
    if type(spec) ~= "table" or type(spec.entries) ~= "table" then
        return false
    end
    launcher = spec
    if launcherFlyout then launcherFlyout:Hide() end
    -- Before login the first skin pass picks it up; after it, combat has to end first.
    if IsLoggedIn() then
        if InCombatLockdown() and addon.CombatQueue then
            addon.CombatQueue:Add("micromenu_launcher", function() addon.RefreshMicroMenuLauncher(true) end)
        else
            addon.RefreshMicroMenuLauncher(true)
        end
    else
        SyncLauncherSuppression()
    end
    return true
end

function addon.RefreshBags()
    if not _G.AddicatUI_BagButtonBar then
        return
    end

    addon.RefreshBagsPosition();

    if MainMenuMicroButtonMixin.bagbuttons_refresh then
        MainMenuMicroButtonMixin:bagbuttons_refresh();
    end

    local arrow = addon.BagsToggle
    if arrow then
        local folded = GetBagCollapseState()
        arrow:PaintFold(folded)
        arrow:SetChecked(folded and true or nil)
    end

    MainMenuMicroButtonMixin:bagbuttons_reposition()
    addon.RefreshBagsVehicle();
end

local function ApplyLFGFrameStyle()
    MiniMapLFGFrameIcon:SetScale(1.5)
    MiniMapLFGFrameBorder:SetTexture(nil)
    MiniMapLFGFrame.eye.texture:SetTexture(addon._dir .. 'Micromenu\\uigroupfinderflipbookeye.tga')
end

local function ReanchorLFDStatus()
    if not LFDSearchStatus or not MiniMapLFGFrame then
        return
    end
    local point, relativePoint, xOff, yOff = GetLFDStatusAnchorSpec(GetLFGTooltipPosition())
    LFDSearchStatus:ClearAllPoints()
    LFDSearchStatus:SetPoint(point, MiniMapLFGFrame, relativePoint, xOff, yOff)
end

local function ApplyMicromenuSystem()
    if MicromenuModule.applied or not IsModuleEnabled() then
        return
    end

    -- Store original states first
    StoreOriginalMicroButtonStates()

    -- Debounced: a burst of cleanup requests collapses into one pass at the earliest requested time.
    hideFramesScheduler = CreateFrame("Frame")

    _G.AddicatUI_BagButtonBar = CreateFrame('Frame', 'AddicatUI_BagButtonBar', UIParent);
    bagsBar = _G.AddicatUI_BagButtonBar;
    KeyRingButton:SetParent(_G.CharacterBag3Slot);

    local foldToggle = addon.BagsToggle
        or CreateFrame("CheckButton", "AddicatUI_BagsToggle", MainMenuBarBackpackButton)
    addon.BagsToggle = foldToggle
    foldToggle:SetSize(12, 18)
    foldToggle:SetPoint("RIGHT", MainMenuBarBackpackButton, "LEFT", 0, -2)
    foldToggle:SetNormalTexture("")
    foldToggle:SetPushedTexture("")
    foldToggle:SetHighlightTexture("")
    foldToggle:RegisterForClicks("LeftButtonUp")
    foldToggle:Show()

    local foldFaces = {
        foldToggle:GetNormalTexture(), foldToggle:GetPushedTexture(), foldToggle:GetHighlightTexture(),
    }
    function foldToggle:PaintFold(folded)
        local atlas = folded and "bag-arrow-2x" or "bag-arrow-invert-2x"
        for _, face in ipairs(foldFaces) do
            face:SetAtlasTexture(atlas)
        end
    end

    -- A CheckButton flips its checked state before OnClick runs, so GetChecked is the new state.
    foldToggle:SetScript("OnClick", function(self)
        local folded = self:GetChecked() and true or false
        self:PaintFold(folded)
        SetBagCollapseState(folded)
        MainMenuMicroButtonMixin:bagbuttons_reposition()
        if not folded then
            UpdateBagSlotAlpha()
            ScheduleBagSlotIconRefreshes()
        end
    end)

    -- LFG Frame customization

    ApplyLFGFrameStyle()

    -- Keep Blizzard's LFD status text/layout ownership intact. We only
    -- re-anchor around the eye and avoid reparenting to prevent text regressions.

    addon.ReanchorLFDSearchStatus = ReanchorLFDStatus

    ReanchorLFDStatus()
    if not MicromenuModule.hooks.LFDSearchStatus_Update then
        hooksecurefunc("LFDSearchStatus_Update", ReanchorLFDStatus)
        MicromenuModule.hooks.LFDSearchStatus_Update = true
    end

    -- ============================================================================
    -- EVENT HANDLERS
    -- ============================================================================

    addon.package:Subscribe(function(_, eventName)
        if not IsModuleEnabled() then return end
        if eventName == "BAG_UPDATE" then
            SyncKeyRingToKeys()
            UpdateBagSlotAlpha()
        end
    end, "BAG_UPDATE")

    -- The Collections button takes the eleventh slot, so the strip starts further left.
    local function ResolveMicroStripOffset()
        if not HasCollectionsButton() then
            return -166
        end
        local collections = _G.CollectionsMicroButton
        if collections then
            collections:UnregisterEvent("UPDATE_BINDINGS")
        end
        return -180
    end

    addon.package:Subscribe(function(self, event)
        if not IsModuleEnabled() then return end

        ScheduleBagSlotIconRefreshes()

        if KeyRingButton and HasKey() then
            KeyRingButton:Show()
        end

        HideUnwantedBagFrames()
    end, 'PLAYER_ENTERING_WORLD');

    addon.package:Subscribe(function()
        local xOffset = ResolveMicroStripOffset()

        layoutMicroButtons(xOffset);

        if addon.RefreshBags then
            addon.RefreshBags();
        end

        addon.core:ScheduleTimer(function()
            -- Check if frames need to be registered
            if _G.AddicatUI_MicroButtonBar and not _G.AddicatUI_MicroButtonBar.registeredInEditor then
                -- Force re-setup to register frames
                layoutMicroButtons(xOffset)
            end

            if _G.AddicatUI_BagButtonBar and not _G.AddicatUI_BagButtonBar.registeredInEditor then
                -- Force bags setup
                if MainMenuMicroButtonMixin.SetupBagButtons then
                    MainMenuMicroButtonMixin:SetupBagButtons()
                end
            end
        end, 0.5)
    end, 'PLAYER_LOGIN');

    -- Mark as applied
    MicromenuModule.applied = true

    -- Execute setup immediately only after login; pre-login passes can produce transient bad geometry.
    if IsLoggedIn() then
        local xOffset = ResolveMicroStripOffset()

        layoutMicroButtons(xOffset)

        if MainMenuMicroButtonMixin.SetupBagButtons then
            MainMenuMicroButtonMixin:SetupBagButtons()
        end

        if addon.RefreshBags then
            addon.RefreshBags()
        end

        if addon.RefreshMicromenu then
            addon.RefreshMicromenu()
        end

        -- Late stabilization pass for startup race conditions.
        addon.core:ScheduleTimer(function()
            if IsModuleEnabled() then
                layoutMicroButtons(xOffset)
                if addon.RefreshMicromenu then addon.RefreshMicromenu() end
                if addon.RefreshBags then addon.RefreshBags() end
            end
        end, 0.2)
    end

    -- Setup all hooks
    if not MicromenuModule.hooks.MiniMapLFG_UpdateIsShown then
        MicromenuModule.hooks.MiniMapLFG_UpdateIsShown = true
        hooksecurefunc('MiniMapLFG_UpdateIsShown', function()
            if IsModuleEnabled() then
                ApplyLFGFrameStyle()
            end
        end)
    end

    addon.package:Subscribe(function(self, event, slotID)
        if not IsModuleEnabled() then return end

        -- Bag slot swaps (equipped container changes) must refresh icons explicitly.
        -- Container 0 is the backpack (no inventory slot); equipped bags are 1-4.
        if slotID and slotID >= ContainerIDToInventoryID(1) and slotID <= ContainerIDToInventoryID(4) then
            if MainMenuMicroButtonMixin.SetupBagButtons then
                MainMenuMicroButtonMixin:SetupBagButtons()
            end
            RefreshBagSlotIcons()
            UpdateBagSlotAlpha()
            HideUnwantedBagFrames()
        end
    end, 'PLAYER_EQUIPMENT_CHANGED')
end

-- ============================================================================
-- PUBLIC API
-- ============================================================================

function addon.RefreshMicromenuSystem()
    if IsModuleEnabled() then
        if not MicromenuModule.applied then
            ApplyMicromenuSystem()
        end
        -- Refresh settings if already applied
        if addon.RefreshMicromenu then
            addon.RefreshMicromenu()
        end
        if addon.RefreshBags then
            addon.RefreshBags()
        end
    else
        if addon:ShouldDeferModuleDisable("micromenu", MicromenuModule) then
            return
        end
        RestoreMicromenuSystem()
    end
end

-- Keep all the existing refresh functions as they are
-- They will only work when the module is enabled
-- ============================================================================
-- Function to load default widget settings
-- ============================================================================

local function LoadDefaultWidgetSettings()
    -- Ensure widget configuration exists
    if not addon.db.profile.widgets then
        addon.db.profile.widgets = {}
    end

    if not addon.db.profile.widgets.micromenu then
        -- Calculate default position based on current configuration
        local useGrayscale = addon.db.profile.micromenu and addon.db.profile.micromenu.grayscale_icons
        local configMode = useGrayscale and "grayscale" or "normal"
        local config = addon.db.profile.micromenu and addon.db.profile.micromenu[configMode]

        if config then
            local xOffset = HasCollectionsButton() and -180 or -166
            addon.db.profile.widgets.micromenu = {
                anchor = "BOTTOMRIGHT",
                posX = xOffset + config.x_position,
                posY = config.y_position
            }
        else
            -- Absolute fallback
            addon.db.profile.widgets.micromenu = {
                anchor = "BOTTOMRIGHT",
                posX = -166,
                posY = 4
            }
        end
    end
end
-- ============================================================================
-- INITIALIZATION
-- ============================================================================

local function Initialize()
    if MicromenuModule.initialized then
        return
    end

    -- Ensure default widget coordinates exist before module setup runs.
    LoadDefaultWidgetSettings()

    -- Only apply if module is enabled
    if IsModuleEnabled() then
        -- Wait for PLAYER_LOGIN to apply system
        addon.package:Subscribe(function()
            ApplyMicromenuSystem()
        end, 'PLAYER_LOGIN')
    end

    MicromenuModule.initialized = true
end

-- Auto-initialize when addon loads
local initFrame = CreateFrame("Frame")
initFrame:RegisterEvent("ADDON_LOADED")
initFrame:SetScript("OnEvent", function(self, event, addonName)
    if addonName == "AddicatUI" then
        Initialize()
        self:UnregisterAllEvents()
    end
end)
