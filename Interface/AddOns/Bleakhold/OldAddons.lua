-- Bleakhold: the old addons a player may have installed by hand from the website (PLAN 5). BleakholdActivities,
-- BleakholdUI and BleakholdChat are built in now (Activities here, the interface in AddicatUI, two-word names in
-- Chat.lua). The launcher never deletes files it did not install, so a copy can still be there. BleakholdUI counts only
-- while AddicatUI is loaded (it is optional, PLAN 8): without it nothing else draws the old addon's mark, spec panel,
-- dock and game-menu credit, so that copy is left on. While one of the others is loaded:
--   * once per character the stock dialog asks "These are now built into Bleakhold. Turn the old copies off?": "Turn
--     off" disables each of them for this character (DisableAddOn) and reloads the interface; "Not now" leaves them
--     (/bh oldaddons asks again).
--   * until then the old Activities window never shows, so there is one window, not two: its frame is parked under a
--     hidden frame with its scripts off; the name BleakholdActivitiesFrame (ESC's UISpecialFrames, macros) points at
--     ours again; the Dungeon Finder's ToggleLFDParentFrame, which it replaced at login, is the game's own again (it
--     kept that as its frame's origLFD); /act and /activities and the two dialogs it shares names with (the riding
--     offer, Leave dungeon) are ours again. Its event frame has no name and keeps reading BHMP: harmless, it only
--     fills its own tables.
--   * an old BleakholdChat (it loads after us) replaced ChatEdit_ExtractTellTarget without calling the one before it,
--     so its split ("/w Thrall hi there" whispers "Thrall hi") ran instead of Chat.lua's: ours is put back (Chat.lua
--     kept the stock function from before the old copy loaded, so it still falls back to the game's). Its
--     ChatEdit_ParseText wrapper only sets editBox.bhSending, which nothing reads then.
--   * an old BleakholdUI next to AddicatUI registers /bhui as AddicatUI does; the chat frame finds one of the two by
--     table order, so the old entry runs AddicatUI's command too (its own wrote BleakholdUICharDB and brought back a
--     second BLEAKHOLD mark).
-- Both load orders: the old addon loaded first leaves its frame under the global name before Activities.lua makes
-- ours (O.before, read when this file loads); loaded after ours, its ADDON_LOADED hands it over.
local ADDON, ns = ...

local O = {}
ns.OldAddons = O

O.NAMES = { "BleakholdActivities", "BleakholdUI", "BleakholdChat" }
-- An old addon whose features live in another addon: it is replaced only while that one is loaded (the others are
-- built into Bleakhold itself, which is always on).
O.REPLACED_BY = { BleakholdUI = "AddicatUI" }
O.WINDOW = "BleakholdActivitiesFrame"
O.DIALOG = "BLEAKHOLD_OLD_ADDONS"
O.TEXT = "These are now built into Bleakhold:\n%s\n\nTurn the old copies off? The interface reloads."
O.ASK_AFTER = 3          -- seconds after entering the world

-- The old addon's window, if it made one before ours (Activities.lua makes ours after this file).
O.before = BleakholdActivitiesFrame

local function loaded(name)
    return IsAddOnLoaded and IsAddOnLoaded(name) and true or false
end

-- The old addons loaded now whose features something loaded replaces, in O.NAMES order: the ones to turn off.
function O.Loaded()
    local list = {}
    for _, name in ipairs(O.NAMES) do
        local by = O.REPLACED_BY[name]
        if loaded(name) and (not by or loaded(by)) then
            list[#list + 1] = name
        end
    end
    return list
end

-- The old addons loaded now that stay on because what replaces them is not loaded, in O.NAMES order.
function O.Kept()
    local list = {}
    for _, name in ipairs(O.NAMES) do
        local by = O.REPLACED_BY[name]
        if loaded(name) and by and not loaded(by) then
            list[#list + 1] = name
        end
    end
    return list
end

local function ours()
    return ns.Activities and ns.Activities.frame
end

local parking
-- Park the old window: hidden for good (a hidden parent keeps a later Show from showing it), its scripts off (its
-- OnShow said .act commands and played sounds).
function O.Park(f)
    if type(f) ~= "table" or f == ours() or f == O.parked then
        return false
    end
    if not parking then
        parking = CreateFrame("Frame", nil, UIParent)
        parking:Hide()
    end
    for _, script in ipairs({ "OnShow", "OnHide", "OnUpdate" }) do
        f:SetScript(script, nil)
    end
    f:Hide()
    f:SetParent(parking)
    O.parked = f
    return true
end

-- Take back what the old Activities window took: its frame out of sight, our names, the game's Dungeon Finder.
function O.TakeBack()
    local old = BleakholdActivitiesFrame
    if old ~= ours() then
        O.Park(old)
    end
    O.Park(O.before)
    local mine = ours()
    if mine and BleakholdActivitiesFrame ~= mine then
        BleakholdActivitiesFrame = mine
    end
    local A = ns.Activities
    if A and A.SlashCommand and SlashCmdList[A.SLASH_ID] ~= A.SlashCommand then
        SlashCmdList[A.SLASH_ID] = A.SlashCommand
    end
    if ns.Legacy then
        ns.Legacy.InstallDialogs()
    end
    -- the stock function the old window kept (a FrameXML function, not a global of ours: lint's rule against writing
    -- other globals is about adding taint, and this undoes the old addon's)
    local orig = O.parked and O.parked.origLFD
    if type(orig) == "function" and ToggleLFDParentFrame ~= orig then
        _G.ToggleLFDParentFrame = orig
    end
end

-- Chat.lua's whisper-target handling, back in place of an old BleakholdChat's.
function O.TakeBackChat()
    local mine = ns.Chat and ns.Chat.ExtractTellTarget
    if type(mine) == "function" and type(ChatEdit_ExtractTellTarget) == "function"
        and ChatEdit_ExtractTellTarget ~= mine then
        _G.ChatEdit_ExtractTellTarget = mine
        return true
    end
    return false
end

-- The old BleakholdUI's /bhui entry runs AddicatUI's command (only while AddicatUI is loaded: without it the old
-- copy is the Bleakhold interface and keeps its own command).
function O.TakeBackBhui()
    local aui = loaded("AddicatUI") and _G.AddicatUI
    local run = type(aui) == "table" and type(aui.BleakholdCommands) == "table" and aui.BleakholdCommands.Run
    if type(run) == "function" and SlashCmdList.BLEAKHOLDUI and SlashCmdList.BLEAKHOLDUI ~= run then
        SlashCmdList.BLEAKHOLDUI = run
        return true
    end
    return false
end

function O.Check()
    if IsAddOnLoaded and IsAddOnLoaded("BleakholdActivities") or O.before then
        O.TakeBack()
    end
    if loaded("BleakholdChat") then
        O.TakeBackChat()
    end
    if loaded("BleakholdUI") then
        O.TakeBackBhui()
    end
end

------------------------------------------------------------------------------------------------------
-- The question, once per character
------------------------------------------------------------------------------------------------------
function O.TurnOff(list)
    for _, name in ipairs(list or O.Loaded()) do
        if DisableAddOn then
            DisableAddOn(name)
        end
    end
    if ReloadUI then
        ReloadUI()
    end
end

function O.InstallDialog()
    StaticPopupDialogs[O.DIALOG] = {
        text = O.TEXT, button1 = "Turn off", button2 = "Not now", timeout = 0, whileDead = 1, hideOnEscape = 1,
        preferredIndex = 3,
        OnAccept = function()
            O.TurnOff()
        end,
    }
end
O.InstallDialog()

-- Ask now (force: even if this character was asked before). Answers true when the dialog shows.
function O.Ask(force)
    local list = O.Loaded()
    if #list == 0 then
        return false
    end
    if not force and ns.cdb.oldAddonsAsked then
        return false
    end
    ns.cdb.oldAddonsAsked = true
    return StaticPopup_Show(O.DIALOG, table.concat(list, ", ")) ~= nil
end

ns.RegisterEvent("ADDON_LOADED", function(event, name)
    if name == "BleakholdActivities" then
        O.TakeBack()
    elseif name == "BleakholdChat" then
        O.TakeBackChat()
    elseif name == "BleakholdUI" then
        O.TakeBackBhui()
    end
end)

ns.RegisterEvent("PLAYER_LOGIN", function()
    O.Check()
end)

-- After every addon's PLAYER_LOGIN (the old window takes ToggleLFDParentFrame there), and the question a moment later.
ns.RegisterEvent("PLAYER_ENTERING_WORLD", function()
    O.Check()
    ns.After(O.ASK_AFTER, function()
        O.Ask(false)
    end)
end)

ns.AddCommand("oldaddons", "turn off the old Bleakhold addons from the website (now built in)", function()
    if not O.Ask(true) then
        local kept = O.Kept()
        if #kept > 0 then
            ns.Print(table.concat(kept, ", ")
                .. " stays on: its features are built into AddicatUI, which is turned off.")
        else
            ns.Print("No old Bleakhold addons are loaded.")
        end
    end
end)
