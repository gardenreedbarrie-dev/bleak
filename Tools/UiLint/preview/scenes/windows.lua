-- Scenes of the Bleakhold windows as the addon builds them today, in demo mode (Comm.Inject fixtures, Demo.lua):
--
--   Tools/UiLint/preview/render.sh Tools/UiLint/preview/scenes/windows.lua activities out.png --stock <art> \
--       --journal <Journal pictures>
--
-- Each scene opens one window with UI.Open and returns it, so only that window is drawn. Add scenes here as windows
-- change; a scene is function(M, ns, RS, env, P) (see README.md).
local S = {}

local function demo(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
end

-- open(key) in demo mode, then return the named window (all visible frames when it does not exist)
local function window(key, name, after)
    return function(M, ns, RS, env, P)
        demo(M, ns)
        ns.UI.Open(key)
        M.Advance(0.5)
        if after then after(M, ns, env, P) end
        return env[name]
    end
end

S.activities = window("tasks", "BleakholdActivitiesFrame")
S.dungeons = window("dungeons", "BleakholdActivitiesFrame")
S.keys = window("keys", "BleakholdActivitiesFrame")
S.rift = window("rift", "BleakholdActivitiesFrame")
S.heroic = window("heroic", "BleakholdActivitiesFrame")
S.group = window("group", "BleakholdActivitiesFrame")
S.royale = window("royale", "BleakholdActivitiesFrame")
S.arena = window("arena", "BleakholdActivitiesFrame")
S.collections = window("collections", "BleakholdCollectionsFrame")
S.animations = window("animations", "BleakholdCollectionsFrame")
S.season = window("season", "BleakholdSeasonFrame")
S.leaderboards = window("leaderboards", "BleakholdLeaderboardsFrame")
S.graphics = window("graphics", "BleakholdGraphics")

-- the stock dialog (StaticPopup.xml as the mock builds it) with the old addon's riding offer
S.popup = function(M, ns, RS, env, P)
    env.StaticPopupDialogs.BLEAKHOLD_PREVIEW = {
        text = "You can ride now!\n\nApprentice Riding (60%% speed) and your first mount for %s?",
        button1 = "Buy", button2 = "Later", timeout = 0, whileDead = 1, hideOnEscape = 1,
    }
    env.StaticPopup_Show("BLEAKHOLD_PREVIEW", "4 gold")
    return env.StaticPopup1
end

return S
