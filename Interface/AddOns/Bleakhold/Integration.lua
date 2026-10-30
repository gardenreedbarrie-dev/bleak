-- Bleakhold: AddicatUI, Bleakhold's interface addon. AddicatUI gets a launcher (one micro menu button whose
-- flyout opens the Bleakhold windows) and the movers (ns.Movers) for its editor mode. Bleakhold keeps owning
-- every saved position (BleakholdCharDB): the editor moves a frame only through its mover, which saves the
-- spot where Bleakhold always kept it, so with AddicatUI gone everything stays put and nothing is stored twice.
-- Registered once both are loaded, in either load order; without AddicatUI this file does nothing.
local ADDON, ns = ...
local UI = ns.UI
local C = UI.C

local I = {}
ns.Integration = I

-- The windows the launcher lists, in micro menu order. glyph names a UI.GLYPHS cell, emote an emote cell.
I.WINDOWS = {
    { key = "activities", title = "Activities", glyph = "star", binding = "BLEAKHOLD_ACTIVITIES",
      text = "Tasks, the dungeon board, your keystone and the Eclipse Rift.", window = "BleakholdActivitiesFrame" },
    { key = "collections", title = "Collections", glyph = "layers", binding = "BLEAKHOLD_COLLECTIONS",
      text = "Transmog, legacy sets, mounts and pets.", window = "BleakholdCollectionsFrame" },
    { key = "animations", title = "Animations", emote = "dance", binding = "BLEAKHOLD_ANIMATIONS",
      text = "Dances and emotes, and the emote wheel.", window = "BleakholdCollectionsFrame", tab = "animations" },
    { key = "season", title = "Season", glyph = "banner", binding = "BLEAKHOLD_SEASON",
      text = "The season's war effort and its rewards.", window = "BleakholdSeasonFrame" },
    { key = "leaderboards", title = "Leaderboards", glyph = "trophy", binding = "BLEAKHOLD_LEADERBOARDS",
      text = "Mythic keys, the Eclipse Rift, raid echoes and server firsts.", window = "BleakholdLeaderboardsFrame" },
    { key = "graphics", title = "Graphics", emote = "sparkle", binding = "BLEAKHOLD_GRAPHICS",
      text = "Bleakhold's graphics presets and settings.", window = "BleakholdGraphics" },
    -- not a window: what the minimap's Make camp orb does (the orbs are off while this launcher lists the windows),
    -- listed while the realm has camping on, its tooltip line with the cooldown
    { key = "camp", title = "Make camp", glyph = "flame", binding = "BLEAKHOLD_MAKECAMP",
      text = function() return ns.Camp.MakeCampText() end,
      action = function() ns.Camp.MakeCamp() end,
      shown = function() return ns.Camp.CampAvailable() end },
}

I.TITLE = "Bleakhold"
I.TEXT = "Activities, collections, the season and the leaderboards."
I.GLYPH = "shield"

local function art(w)
    local file, l, r, t, b
    if w.emote then
        file, l, r, t, b = UI.EmoteGlyphArt(w.emote)
    else
        file, l, r, t, b = UI.GlyphArt(w.glyph)
    end
    local cr, cg, cb = UI.Rgb(C.goldLight)
    return { file = file, coords = { l, r, t, b }, color = { cr, cg, cb } }
end

function I.IsOpen(w)
    if not w.window then
        return false
    end
    local win = UI.windows[w.window]
    if not (win and win:IsShown()) then
        return false
    end
    if w.window == "BleakholdCollectionsFrame" then
        local onAnimations = ns.Collections and ns.Collections.tab == "animations"
        return (w.tab == "animations") == (onAnimations and true or false)
    end
    return true
end

-- What AddicatUI.RegisterMicroMenuLauncher takes. description is a string or a function (read on hover), shown a
-- function (the flyout lists the entry while it returns true; read each time the flyout opens).
function I.LauncherSpec()
    local entries = {}
    for _, w in ipairs(I.WINDOWS) do
        entries[#entries + 1] = {
            key = w.key, title = w.title, description = w.text, binding = w.binding, icon = art(w),
            open = w.action or function()
                UI.Open(w.key, true)
            end,
            isOpen = function()
                return I.IsOpen(w)
            end,
            shown = w.shown,
        }
    end
    return {
        id = "bleakhold", title = I.TITLE, description = I.TEXT, icon = art({ glyph = I.GLYPH }), entries = entries,
    }
end

-- AddicatUI calls the movers inside pcall; SafeCall still counts and reports a broken one here.
local function guarded(m)
    local spec = { name = m.name, title = m.title, frame = m.frame }
    for _, key in ipairs({ "begin", "finish", "move", "reset", "isDefault", "visible" }) do
        local fn = m[key]
        if fn then
            spec[key] = function(...)
                local out
                ns.SafeCall(function(...)
                    out = fn(...)
                end, ...)
                return out
            end
        end
    end
    return spec
end

function I.Register(aui)
    if type(aui) ~= "table" then
        return
    end
    if not I.launcher and type(aui.RegisterMicroMenuLauncher) == "function" then
        I.launcher = true
        ns.SafeCall(aui.RegisterMicroMenuLauncher, I.LauncherSpec())
    end
    local editor = aui.EditorMode
    if not I.movers and type(editor) == "table" and type(editor.RegisterExternalFrame) == "function" then
        I.movers = true
        for _, m in ipairs(ns.Movers) do
            ns.SafeCall(editor.RegisterExternalFrame, editor, guarded(m))
        end
    end
end

-- AddicatUI loads first (OptionalDeps in the TOC); ADDON_LOADED covers the other order.
I.Register(_G.AddicatUI)
ns.RegisterEvent("ADDON_LOADED", function(event, name)
    if name == "AddicatUI" then
        I.Register(_G.AddicatUI)
    end
end)
