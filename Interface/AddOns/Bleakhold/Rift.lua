-- Bleakhold: Activities > Eclipse Rift, the old window's page (old BleakholdActivities.lua :352-404) in its anatomy
-- (Activities.lua A.Page): what the rift is, the best floor solo, duo, trio and as a group and the checkpoint in the
-- stat column, the rewards (with their tooltips), how it works, the floor to start at (floor 1 or right after a
-- checkpoint) and Enter / Leave. Our extras: the run in progress (floor, boss, time, deaths, score), the last run's
-- summary with its rewards, the Rift rank and a link to the Rift leaderboard.
--
-- Data: the old page's BHMP U (Legacy.lua: bests by group size, checkpoint, level, open, the floor now, the floor
-- count; X and a Rift floor's S keep the floor now true, since the server sends no U on leaving); our RIFT / RIFTE for
-- the run and the last run (RIFTE asks for U again).
-- Actions: the old commands, as the old page sent them (.rift enter <floor> | leave: Legacy.RiftEnter, RiftLeave), so
-- the player picks the start floor; a party member who is not the leader follows the party (.rift enter, the server's
-- follow path: Legacy.RiftFollow); Leaderboard opens ours.
-- Rules as the server has them (mod-bleakhold bh_rift.cpp): up to 5 players (never a raid group), the party leader
-- opens it and the others follow, everyone at Rift.MinLevel (U's sixth field), out of dungeons and battlegrounds; a
-- floor is one boss, its portal leads deeper; every 5th floor is a checkpoint, and a run starts at floor 1 or right
-- after one reached; a floor pays Mythic Coins (more the deeper, double on a new best for the group size, within the
-- weekly cap), every 5th floor a Mythical Cache, and a small chance at a Mythic-only look; the whole party down
-- collapses the rift.
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local S = ns.S
local A = ns.Activities
local L = ns.Legacy

local floor, max, min = math.floor, math.max, math.min

local P = A.Page("rift", {
    title = "The Eclipse Rift",
    desc = "An endless rift through the dungeons of Azeroth. Enter alone or with up to 5 players, land somewhere "
        .. "inside a dungeon, then find and defeat its marked boss. Each victory opens a portal one floor deeper.\n\n"
        .. "Deeper floors make every enemy stronger and the rewards better. Every 5th floor is a checkpoint you can "
        .. "start from later.",
})
ns.Rift = P

P.CHECKPOINT_EVERY = 5                    -- bh_rift.cpp: floor - floor % 5, "(floor - 1) % 5 == 0" to start
P.startFloor = nil                        -- the floor chosen in the dropdown (nil: the highest start)

------------------------------------------------------------------------------------------------------
-- The stat column (old :355-356) and the rank
------------------------------------------------------------------------------------------------------
P.bests = {}
for i, label in ipairs({ "Best Solo", "Best Duo", "Best Trio", "Best Group" }) do
    P.bests[i] = P:Stat(i, label)
end
P.checkpoint = P:Stat(5, "Checkpoint")
P.rank = P:Stat(6, "Rift Rank")

------------------------------------------------------------------------------------------------------
-- Potential rewards (old :357-365) and how it works (old :366-368)
------------------------------------------------------------------------------------------------------
P:Section("Potential Rewards", A.PAD, -206)
P.REWARDS = {
    { "INV_Misc_Coin_17", "Mythic Coins", "Every floor pays Mythic Coins, more the deeper you go - double on a new "
        .. "best floor for your group size. They count toward the week's Mythic Coin cap." },
    { "INV_Box_04", "Rift Cache", "Every 5th floor: a Mythic item for your class from one of your Mythical Caches "
        .. "(shared with Mythic+), better the deeper you go." },
    { "INV_Misc_Bag_10", "Mythic-only Looks", "A small chance on every floor, growing as you go deeper, to unlock a "
        .. "Mythic-only transmog look for your wardrobe." },
}
P.rewardIcons = {}
for i, rw in ipairs(P.REWARDS) do
    local a = UI.Icon(P, 38, rw[1])
    a:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD + (i - 1) * 46, -228)
    a:EnableMouse(true)
    a.tipLines = { rw[2], { rw[3], C.text, true } }
    a:SetScript("OnEnter", function(self)
        UI.ShowTooltip(self, self.tipLines)
    end)
    a:SetScript("OnLeave", function()
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    P.rewardIcons[i] = a
end

P:Section("How it works", A.PAD, -286)
P.how = UI.Para(P, 11, "CCCCCC", A.DESC_W)
P.how:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD, -308)
P.how:SetText("- you land near the floor's boss, warded for a few seconds\n"
    .. "- enemies are tuned to your party size: solo is possible\n"
    .. "- your party leader opens the portal to the next floor\n"
    .. "- if the whole party falls, the rift collapses - start again from your checkpoint\n"
    .. "- leave any time with Leave the Eclipse Rift below")

------------------------------------------------------------------------------------------------------
-- The run in progress or the last run (our extra)
------------------------------------------------------------------------------------------------------
P.runTitle = P:Section("Your Last Run", A.PAD, -406)
P.runLines = {}
for i = 1, 6 do
    local l = UI.Text(P, i == 1 and 13 or 11, i == 1 and C.text or C.dim)
    l:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD, -428 - (i == 1 and 0 or (4 + (i - 1) * 16)))
    UI.OneLine(l, A.DESC_W)
    P.runLines[i] = l
end

------------------------------------------------------------------------------------------------------
-- Start floor, Enter / Leave (old :369-389), the leaderboard
------------------------------------------------------------------------------------------------------
P.dd = UI.Dropdown(P, 150, function(v)
    P.startFloor = tonumber(v)
end)
P.dd:SetPoint("BOTTOMRIGHT", P, "BOTTOMRIGHT", -18, 58)
P.floorLabel = UI.Label(P, "Start at floor", 12)
P.floorLabel:SetPoint("RIGHT", P.dd, "LEFT", -8, 0)

P.enter = UI.Button(P, 230, 30, "Enter the Eclipse Rift", "red", 12)
P.enter:SetPoint("BOTTOMRIGHT", P, "BOTTOMRIGHT", -18, 18)
P.board = UI.Button(P, 120, 26, "Leaderboard", "red", 12)
P.board:SetPoint("BOTTOMRIGHT", P.enter, "BOTTOMLEFT", -8, 2)
P.board:SetScript("OnClick", function()
    UI.Open("leaderboards-rift")
end)
P.note = UI.Text(P, 11, C.dim)
P.note:SetPoint("BOTTOMLEFT", P, "BOTTOMLEFT", A.PAD, 24)
P.note:SetWidth(380)

-- The floors a run may start at: 1, then right after each checkpoint reached (6, 11, ...).
function P.StartFloors()
    local out = { 1 }
    local cp = L.rift.checkpoint or 0
    local f = 1 + P.CHECKPOINT_EVERY
    while f <= cp + 1 and #out < 200 do
        out[#out + 1] = f
        f = f + P.CHECKPOINT_EVERY
    end
    return out
end

-- In a run: the floor (our RIFT while it runs, else the old U's floor now), or nil. Every floor is inside a dungeon
-- and the rift's exit is in the open world, so outside an instance there is no run, whatever an older message said
-- (the demo's sample run aside: it has no dungeon to be in).
function P.RunFloor()
    if not (IsInInstance() or Comm.demo) then
        return nil
    end
    local rf = S.rift
    if rf and rf.state == 1 then
        return rf.floor or L.rift.inFloor
    end
    if (L.rift.inFloor or 0) > 0 then
        return L.rift.inFloor
    end
    return nil
end

-- A party member who is not its leader: the leader opens the rift, the others follow it (RiftEnter's follow path,
-- checked before the leader rule: a member who was away or relogged goes to the party's floor).
function P.IsFollower()
    local raid = GetNumRaidMembers and GetNumRaidMembers() or 0
    local party = GetNumPartyMembers and GetNumPartyMembers() or 0
    return raid == 0 and party > 0 and not (IsPartyLeader and IsPartyLeader())
end
P.FOLLOW_NOTE = "Your party leader opens the rift; if it is already open, this takes you to your party."

-- What keeps the player from opening the rift (or following the party into it), as the server checks it (RiftEnter),
-- or nil. Also the Bleakhold Royale and 1v1 arena queues, which .rift enter does not check (a player on a Rift floor
-- drops out of the Royale queue at its proposal), worded as the bridge's QJOIN refuses.
function P.EnterBlock()
    local r = L.rift
    if r.known and not r.on then
        return "The Eclipse Rift is closed right now."
    end
    local level = UnitLevel and UnitLevel("player") or 0
    if r.known and level > 0 and level < (r.minLevel or 0) then
        return "Opens at level " .. r.minLevel .. "."
    end
    local queued = A.OtherQueueBlock()
    if queued then
        return queued
    end
    local inInstance, kind = IsInInstance()
    if inInstance and (kind == "party" or kind == "raid" or kind == "pvp" or kind == "arena") then
        return "Leave the dungeon or battleground first."
    end
    -- the player's own state (RiftEnter checks every member who goes in, the leader as "You")
    if UnitAffectingCombat and UnitAffectingCombat("player") then
        return "You are in combat."
    end
    if UnitIsDeadOrGhost and UnitIsDeadOrGhost("player") then
        return "You are dead."
    end
    if UnitOnTaxi and UnitOnTaxi("player") then
        return "You are busy (battleground or flight)."
    end
    if (GetNumRaidMembers and GetNumRaidMembers() or 0) > 0 then
        return "The rift takes at most 5 players - leave the raid group first."
    end
    -- the leader's opening (a follower only goes after the party): never a Dungeon Finder group, and every member,
    -- near or far, at the rift's level
    if not P.IsFollower() then
        if A.InDungeonFinderGroup() then
            return "Leave the Dungeon Finder group first."
        end
        if r.known and (r.minLevel or 0) > 0 then
            for i = 1, GetNumPartyMembers and GetNumPartyMembers() or 0 do
                local unit = "party" .. i
                local lvl = UnitLevel and UnitLevel(unit) or 0
                if lvl > 0 and lvl < r.minLevel then
                    local name = UnitName and UnitName(unit)
                    return U.Safe(name or "A party member") .. " needs to be level " .. r.minLevel .. "."
                end
            end
        end
    end
    return nil
end

local function canCommand()
    return L.CanCommand() or Comm.demo and true or false
end

P.enter:SetScript("OnClick", function()
    if P.RunFloor() then
        L.RiftLeave()
        return
    end
    local sent
    if P.IsFollower() then
        sent = L.RiftFollow()
    else
        sent = L.RiftEnter(P.ChosenFloor())
    end
    if sent then
        if PlaySoundFile then
            PlaySoundFile("Sound\\Doodad\\InstancePortal_PurpleDifficulty.wav")
        end
        A.frame:Hide()
    end
end)

-- The chosen start floor, kept to one the server takes (old :392).
function P.ChosenFloor()
    local floors = P.StartFloors()
    local want = P.startFloor or floors[#floors]
    for _, f in ipairs(floors) do
        if f == want then
            return f
        end
    end
    P.startFloor = nil
    return floors[#floors]
end

function P:RefreshFloors()
    local items = {}
    for _, f in ipairs(P.StartFloors()) do
        items[#items + 1] = { value = f, text = f > 1 and ("Floor " .. f .. "  (checkpoint " .. (f - 1) .. ")")
            or "Floor 1" }
    end
    P.dd:SetItems(items)
    local f = P.ChosenFloor()
    P.dd:SetValue(f, true)
    P.dd.label:SetText("Floor " .. f)
end

function P:RefreshRun()
    local rf = S.rift
    local lines = {}
    local runFloor = P.RunFloor()
    if runFloor then
        P.runTitle:SetText("Your Run")
        lines[1] = "Floor " .. runFloor .. ((rf and rf.bossName) and ("  -  " .. U.Safe(rf.bossName)) or "")
        local parts = {}
        local e = P.Elapsed()
        if e then parts[#parts + 1] = "Time " .. U.Clock(e) end
        if rf and rf.deaths then parts[#parts + 1] = rf.deaths .. (rf.deaths == 1 and " death" or " deaths") end
        if rf and rf.groupSize then parts[#parts + 1] = rf.groupSize == 1 and "solo" or ("group of " .. rf.groupSize) end
        lines[2] = table.concat(parts, "  -  ")
        if rf and rf.score then lines[3] = "Score " .. U.Commas(rf.score) end
    else
        P.runTitle:SetText("Your Last Run")
        local sm = rf and rf.summary
        if sm then
            lines[1] = (sm.floor and ("Reached floor " .. sm.floor) or "Run over") .. (sm.newBest and "  -  new best!" or "")
            local parts = {}
            if sm.timeMs then parts[#parts + 1] = "Time " .. U.Clock(sm.timeMs / 1000) end
            if sm.score then parts[#parts + 1] = "Score " .. U.Commas(sm.score) end
            if sm.rank then parts[#parts + 1] = "Rank " .. sm.rank end
            lines[#lines + 1] = table.concat(parts, "  -  ")
            for _, rw in ipairs(sm.rewards) do
                if #lines < #P.runLines then
                    lines[#lines + 1] = "|cffffd100+|r " .. U.Safe(rw)
                end
            end
        else
            lines[1] = "No run yet"
        end
    end
    for i, l in ipairs(P.runLines) do
        l:SetText(lines[i] or "")
    end
end

-- The run's time, counted on from the last RIFT (anchored to GetTime()).
function P.Elapsed()
    local rf = S.rift
    if not rf or rf.state ~= 1 or not rf.elapsedMs then
        return nil
    end
    return rf.elapsedMs / 1000 + (GetTime() - (rf.elapsedAt or GetTime()))
end

function P:RefreshStats()
    local r = L.rift
    for i, v in ipairs(P.bests) do
        local b = r.best[i] or 0
        v:SetText(b > 0 and tostring(b) or "-")
    end
    if not r.known and S.rift and S.rift.bestFloor and S.rift.bestFloor > 0 then
        -- before the old U: our RIFT's best floor (the best of the group size played, else overall)
        P.bests[1]:SetText(tostring(S.rift.bestFloor))
    end
    P.checkpoint:SetText((r.checkpoint or 0) > 0 and ("floor " .. r.checkpoint) or "-")
    local rank = S.rift and S.rift.rank
    if rank then
        P.rank:SetText(tostring(rank))
        P.rank:Show()
        P.rank.label:Show()
    else
        P.rank:Hide()
        P.rank.label:Hide()
    end
end

function P:Refresh()
    P:RefreshStats()
    P:RefreshFloors()
    P:RefreshRun()
    local r = L.rift
    local runFloor = P.RunFloor()
    local party = (GetNumPartyMembers and GetNumPartyMembers() or 0) > 0
    if runFloor then
        P.enter:SetLabel("Leave the Eclipse Rift")
        P.enter:SetActive(canCommand())
        P.note:SetText("You are on floor |cffff9a3c" .. runFloor .. "|r.")
        P.dd:SetActive(false)
    else
        local follower = P.IsFollower()
        P.enter:SetLabel(follower and "Follow your party" or (party and "Enter with your party")
            or "Enter Solo Eclipse Rift")
        local block = P.EnterBlock()
        P.enter:SetActive(not block and canCommand())
        -- the floor is the leader's choice (a follower goes to the party's floor)
        P.dd:SetActive(not block and not follower and true or false)
        if block then
            P.note:SetText(block)
        elseif follower then
            P.note:SetText(P.FOLLOW_NOTE)
        elseif not r.known then
            P.note:SetText((Comm.ready or Comm.outdated or L.seen or Comm.demo) and "Asking the server..." or "Waiting for the server...")
        else
            P.note:SetText(r.floors .. " different floors are waiting.")
        end
    end
end

function P:Tick()
    if P.RunFloor() then
        P:RefreshRun()
    end
end

function P:OnOpen()
    L.Request()
    Comm.Get("RIFT")
end

-- The run is over: the server sends no new U then (only X), so ask for it again (bests, checkpoint, the floor now).
ns.On("RIFT_END", function()
    L.Request(true)
    if P:IsVisible() then
        P:Refresh()
    end
end)
