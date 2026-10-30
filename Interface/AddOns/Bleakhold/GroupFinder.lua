-- Bleakhold: Activities > Group Finder, the old window's page (old BleakholdActivities.lua :434-441) in its anatomy
-- (Activities.lua A.Page): the game's own Dungeon Finder one click away (the I key opens Activities now), and where to
-- find people for the rest. Our extras: the Dungeon Journey's queue one click away, and the player's queue (the same
-- as the Dungeon Journey page shows: Dungeons.lua) with Leave queue.
-- Rules as the server has them (mod-bleakhold): the Eclipse Rift has no group finder, its party leader takes up to 4
-- others in (bh_rift.cpp RiftEnter); Journey queues match players of a level range and are announced to the realm
-- (bh_dungeon.cpp JoinLobby, Bleakhold.Journey.AnnounceQueues).
local ADDON, ns = ...
local U, UI, Comm = ns.U, ns.UI, ns.Comm
local C = UI.C
local A = ns.Activities

local P = A.Page("group", {
    desc = "Looking for people? Queue a Dungeon Journey run with Find Group and the server matches you with players "
        .. "of your level, or use the classic Dungeon Finder for random WotLK dungeons.",
})
ns.GroupFinder = P

P.finder = UI.Button(P, 230, 30, "Open the classic Dungeon Finder", "red", 12)
P.finder:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD, -128)
P.finder:SetScript("OnClick", function()
    A.OpenDungeonFinder()
end)
P.finder.tooltip = A.FinderTooltip

P.tips = UI.Para(P, 12, "D9D9D9", A.DESC_W)
P.tips:SetPoint("TOPLEFT", P, "TOPLEFT", A.PAD, -176)
P.tips:SetText("- Mythic+ groups: |cffffd100/join lfg|r and post your keystone\n"
    .. "- Eclipse Rift: invite up to 4 friends, then press Enter with your party\n"
    .. "- Journey queues are announced to the whole realm")

-- the Dungeon Journey's own queue, a click away too
P.journey = UI.Button(P, 230, 30, "Find a Dungeon Journey group", "red", 12)
P.journey:SetPoint("TOPLEFT", P.tips, "BOTTOMLEFT", 0, -24)
P.journey:SetScript("OnClick", function()
    A.Show("dungeons")
end)

-- the player's queue
P.queueTitle = P:Section("Your Queue", A.PAD, -320)
P.queueStatus = UI.Text(P, 12, C.text)
P.queueStatus:SetPoint("TOPLEFT", P.queueTitle, "BOTTOMLEFT", 0, -8)
UI.OneLine(P.queueStatus, A.DESC_W)
P.leave = UI.Button(P, 120, 22, "Leave queue", "red", 12)
P.leave:SetPoint("TOPLEFT", P.queueStatus, "BOTTOMLEFT", 0, -10)
P.leave:SetScript("OnClick", function()
    Comm.Send("QLEAVE")
end)

local STATES = { [1] = "In queue", [2] = "Group found", [3] = "In a run" }

function P:Refresh()
    local D = ns.Dungeons
    local st, qs = D.QueueState()
    if st == 0 then
        P.queueStatus:SetText("|cff808080Not in a queue.|r")
    else
        local what
        if qs then
            what = D.QueueWhat(qs)
        else
            local j = ns.Legacy.journey
            local o = j.byKey[j.queuedKey]
            what = o and o.name or "Dungeon Journey"
        end
        local head = STATES[st] or ""
        if st == 3 and qs and (qs.kind == "B" or qs.kind == "A") then
            head = "In a match"
        end
        UI.SetText(P.queueStatus, head .. ": " .. what)
    end
    if Comm.ready and (st == 1 or st == 2) then
        P.leave:Show()
    else
        P.leave:Hide()
    end
end

function P:OnOpen()
    Comm.Get("QUEUE")
end
