-- Camping (section 16): the Make camp orb and /camp, the camp frame (state, timers, objects, place,
-- repair, pack up), the warmth and food indicator, glide and field repair, and the friendly error texts.
local FX = host_loadfile(repo .. "/Tools/UiLint/tests/fixtures.lua")()

local ALL_BITS = { [6] = 512 + 1024 + 2048 }
local CAMP_ONLY = { [6] = 512 }

local function gets(M)
    local out = {}
    for _, it in ipairs(H.intents(M)) do
        if it.op == "GET" then
            out[#out + 1] = table.concat(it.fields, ",")
        end
    end
    return table.concat(out, ";")
end

local function campst(M, over)
    local r = { "N", 0, 0, 0, 0, 0, 0, {}, {}, "", 0, 0 }
    for k, v in pairs(over or {}) do
        r[k] = v
    end
    H.send(M, "CAMPST", { r })
end

-- A refusal the client tells by itself: in the error frame, like the server's ERR sentences.
local function printed(M, text)
    local n = 0
    for _, c in ipairs(M.chat) do
        if c.frame == M.env.UIErrorsFrame and c.msg:find(text, 1, true) then
            n = n + 1
        end
    end
    return n
end

local function errorsShown(M, text)
    local n = 0
    for _, c in ipairs(M.chat) do
        if c.frame == M.env.UIErrorsFrame and c.msg:find(text, 1, true) then
            n = n + 1
        end
    end
    return n
end

test("camp: no feature bits, no GET CAMPST, everything stays hidden and nothing is sent", function(M, ns)
    FX.connect(M, H)
    M.Advance(1)
    H.ok(not gets(M):find("CAMPST", 1, true), "no GET CAMPST")
    H.ok(not M.env.BleakholdOrb_camp:IsShown(), "no camp orb")
    campst(M, { [1] = "C", [3] = 600, [6] = 1500, [7] = 15 })
    M.Advance(0.5)
    H.ok(not M.env.BleakholdCampFrame:IsShown(), "no camp frame while camping is off")
    local sent = #M.sent
    M.env.SlashCmdList.BLEAKHOLD("camp")
    M.env.BleakholdGlide()
    M.env.SlashCmdList.BLEAKHOLD("repair")
    M.Advance(1)
    H.eq(#M.sent, sent, "nothing goes out")
    H.ok(printed(M, "Camping is turned off") >= 1, "notice printed")
end)

test("camp: feature bit 512 asks for CAMPST and shows the orb; the orb and /camp make camp", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    M.Advance(1)
    H.contains(gets(M), "CAMPST", "GET CAMPST after HELLO")
    local orb = M.env.BleakholdOrb_camp
    H.ok(orb:IsShown(), "camp orb shown")
    orb:Click()
    M.Advance(0.2)
    local it = H.lastIntent(M, "CAMP")
    H.ok(it, "orb sent CAMP")
    H.eq(it.payload, "M", "make camp")
    -- the cooldown starts: the orb shows it and refuses the next try locally
    campst(M, { [5] = 880 })
    M.Advance(2)
    H.ok(orb.cd:IsShown(), "cooldown under the orb")
    H.contains(orb.cd:GetText(), "14:", "about 880 s left")
    local count = H.countIntents(M, "CAMP")
    M.env.SlashCmdList.BLEAKHOLD("camp")
    M.Advance(1)
    H.eq(H.countIntents(M, "CAMP"), count, "no CAMP while on cooldown")
    H.ok(printed(M, "You can make camp again in 14 min") >= 1, "the wait is printed")
end)

test("camp: the camp frame shows resting, timers, place buttons and pack up", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    campst(M, { [1] = "R", [2] = 45, [3] = 870, [4] = 1, [9] = { { 164, 2 }, { 185, 1 } } })
    M.Advance(0.3)
    local f = M.env.BleakholdCampFrame
    H.ok(f:IsShown(), "frame shown at a fire")
    H.eq(f.state:GetText(), "Resting")
    H.contains(f.settle:GetText(), "00:4", "settle countdown")
    H.contains(f.fire:GetText(), "14:", "fire timer")
    H.contains(f.fire:GetText(), "(yours)", "own fire")
    M.Advance(10)
    H.contains(f.settle:GetText(), "00:3", "settle counts down locally")
    H.eq(f.place[1].label:GetText(), "Place Forge", "place by catalogue name (blacksmith tier 2)")
    H.eq(f.place[2].label:GetText(), "Place Cookpot")
    H.ok(not f.place[3]:IsShown(), "only the entries sent")
    H.ok(f.packBtn:IsShown(), "pack up on an own fire")
    H.ok(not f.repairBtn:IsShown(), "no repair without the flag")
    f.place[1]:Click()
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "CAMP").payload, "O,164", "place sends the skill line")
    M.Advance(1.4)
    f.packBtn:Click()
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "CAMP").payload, "P", "pack up")
end)

test("camp: settled state shows objects with tooltips, warmth and repair; leaving hides it", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    local settled = 0
    ns.On("CAMP_SETTLED", function()
        settled = settled + 1
    end)
    -- already settled in the first state (a reload by the fire): no toast
    campst(M, { [1] = "C", [3] = 800 })
    H.eq(settled, 0, "no settle event for the first state")
    campst(M, { [1] = "R", [2] = 1, [3] = 800 })
    campst(M, { [1] = "C", [3] = 800, [6] = 1500, [7] = 15, [8] = { { 164, 2, 1 }, { 171, 1, 0 } }, [11] = 1, [12] = 1 })
    M.Advance(0.3)
    local f = M.env.BleakholdCampFrame
    H.ok(f:IsShown())
    H.eq(f.state:GetText(), "Camping")
    H.eq(settled, 1, "settle event fired once")
    H.ok(ns.Toast.Pending() >= 1, "settle toast queued")
    H.contains(f.warmth:GetText(), "+15% XP", "the XP bonus")
    H.ok(f.objs[1]:IsShown() and f.objs[2]:IsShown() and not f.objs[3]:IsShown(), "two objects")
    H.eq(f.objs[1].icon:GetTexture(), "Interface\\Icons\\Trade_BlackSmithing")
    M.Fire(f.objs[1], "OnEnter")
    local tip = table.concat(M.env.GameTooltip.__lines or {}, "\n")
    H.contains(tip, "Forge", "object name")
    H.contains(tip, "Blacksmithing - Journeyman", "profession and tier")
    H.contains(tip, "repair", "the buff line")
    H.contains(tip, "Placed by you", "own object")
    M.Fire(f.objs[1], "OnLeave")
    H.ok(f.repairBtn:IsShown(), "repair allowed here")
    f.repairBtn:Click()
    M.Advance(0.3)
    H.ok(H.lastIntent(M, "REPAIR"), "repair sent")
    -- leaving the fire hides the frame; the warmth indicator takes over
    campst(M, { [6] = 1200, [7] = 10 })
    M.Advance(0.5)
    H.ok(not f:IsShown(), "frame gone away from the fire")
    H.ok(M.env.BleakholdCampStatus:IsShown(), "warmth indicator shown")
end)

test("camp: the warmth and food indicator counts down and hides when the bonus ends", function(M, ns)
    FX.connect(M, H, CAMP_ONLY)
    local ind = M.env.BleakholdCampStatus
    campst(M, { [6] = 20, [7] = 10 })
    M.Advance(0.5)
    H.ok(ind:IsShown(), "warmth away from a fire")
    H.contains(ind.text:GetText(), "+10% XP")
    M.Advance(25)
    H.ok(not ind:IsShown(), "hidden when the warmth ran out")
    campst(M, { [12] = 1, [7] = 5 })
    M.Advance(0.5)
    H.ok(ind:IsShown(), "well fed alone shows it")
    H.contains(ind.text:GetText(), "Well fed")
    M.Fire(ind, "OnEnter")
    H.contains(table.concat(M.env.GameTooltip.__lines or {}, "\n"), "+5% experience", "tooltip")
    M.Fire(ind, "OnLeave")
    campst(M, {})
    M.Advance(1.2)
    H.ok(not ind:IsShown(), "hidden with nothing to show")
end)

test("camp: glide by binding and /bh glide, with its cooldown; hidden for non-gliders", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    campst(M, { [10] = 5 })
    M.Advance(0.3)
    M.env.BleakholdGlide()
    M.Advance(0.5)
    H.ok(not H.lastIntent(M, "GLIDE"), "no GLIDE while on cooldown")
    H.ok(printed(M, "Glide is not ready yet") >= 1, "the wait is printed")
    M.Advance(6)
    M.env.BleakholdGlide()
    M.Advance(0.5)
    H.ok(H.lastIntent(M, "GLIDE"), "GLIDE when ready")
    -- an empty glide field: this character cannot glide
    campst(M, {})
    M.Advance(1.4)
    local n = H.countIntents(M, "GLIDE")
    M.env.SlashCmdList.BLEAKHOLD("glide")
    M.Advance(0.5)
    H.eq(H.countIntents(M, "GLIDE"), n, "no GLIDE for other races")
    H.ok(printed(M, "Only High Elves can glide") >= 1, "explained")
end)

test("camp: glide feature off refuses locally even with a glide field", function(M, ns)
    FX.connect(M, H, CAMP_ONLY)
    campst(M, { [10] = 0 })
    M.Advance(0.3)
    M.env.BleakholdGlide()
    M.Advance(0.5)
    H.ok(not H.lastIntent(M, "GLIDE"), "feature 1024 off")
end)

test("camp: /repair sends REPAIR when allowed and explains when not", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    campst(M, { [11] = 1 })
    M.Advance(0.3)
    M.env.SlashCmdList.BLEAKHOLD("repair")
    M.Advance(0.5)
    H.ok(H.lastIntent(M, "REPAIR"), "repair sent")
    campst(M, {})
    M.Advance(2.5)
    local n = H.countIntents(M, "REPAIR")
    M.env.SlashCmdList.BLEAKHOLD("repair")
    M.Advance(0.5)
    H.eq(H.countIntents(M, "REPAIR"), n, "not allowed right now")
    H.ok(printed(M, "to repair here") >= 1, "explained")
end)

test("camp: error codes become friendly sentences in the error frame", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    campst(M, { [5] = 880 })
    H.send(M, "ERR", { { "CAMP", "9", "camp_cooldown", "" } })
    H.ok(errorsShown(M, "make camp again in") >= 1, "cooldown text with the time left")
    H.send(M, "ERR", { { "CAMP", "a", "camp_indoors", "" } })
    H.ok(errorsShown(M, "only make camp outdoors") >= 1)
    H.send(M, "ERR", { { "REPAIR", "b", "repair_gold", "" } })
    H.ok(errorsShown(M, "enough money") >= 1)
    H.send(M, "ERR", { { "GLIDE", "c", "glide_race", "" } })
    H.ok(errorsShown(M, "High Elves") >= 1)
    -- an unknown code falls back to the server's sentence, pipes doubled
    H.send(M, "ERR", { { "CAMP", "d", "camp_new_code", "Some |cffff0000new|r reason." } })
    H.ok(errorsShown(M, "Some ||cffff0000new||r reason.") >= 1, "server text, made safe")
end)

test("camp: ERR busy waits a full gap before the next try", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    M.env.SlashCmdList.BLEAKHOLD("camp")
    M.Advance(0.3)
    H.eq(H.countIntents(M, "CAMP"), 1)
    H.send(M, "ERR", { { "CAMP", H.lastIntent(M, "CAMP").seq, "busy", "Give it a moment." } })
    M.env.SlashCmdList.BLEAKHOLD("camp")
    M.Advance(0.3)
    H.eq(H.countIntents(M, "CAMP"), 1, "too soon after busy")
    M.Advance(1.4)
    M.env.SlashCmdList.BLEAKHOLD("camp")
    M.Advance(0.3)
    H.eq(H.countIntents(M, "CAMP"), 2, "allowed after the gap")
end)

test("camp: the movers preview the frame and the indicator with sample content", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    local movers = {}
    for _, m in ipairs(ns.Movers) do
        movers[m.name] = m
    end
    local cm, im = movers.bleakhold_camp, movers.bleakhold_camp_status
    H.ok(cm and im, "both movers registered")
    H.ok(cm.visible() and im.visible(), "visible with feature 512")
    cm.begin()
    H.ok(M.env.BleakholdCampFrame:IsShown(), "sample camp shown")
    H.ok(M.env.BleakholdCampFrame.repairBtn:IsShown(), "sample has the repair button")
    cm.finish()
    H.ok(not M.env.BleakholdCampFrame:IsShown(), "hidden again without live state")
    im.begin()
    H.ok(M.env.BleakholdCampStatus:IsShown(), "sample indicator shown")
    im.finish()
    M.Advance(1.2)
    H.ok(not M.env.BleakholdCampStatus:IsShown())
end)

test("camp: garbage CAMPST never raises and the frame copes", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    for _, payload in ipairs({
        "", "X", "C", "R,abc,-5,2,nan", "C,0,600,1,0,1500,15,164~x~1:~~:999999,185~9",
        "C,0,600,1,0,1500,15," .. string.rep("164~1~1:", 40), "N,,,,,,,,,,,",
        "C,0,2147483647,1,0,2147483647,2147483647,1~1~1,1~1,2147483647,1,1",
    }) do
        for _, fr in ipairs(H.frames("CAMPST", payload, 700)) do
            H.deliver(M, fr)
        end
        M.Advance(0.3)
    end
    H.ok(true, "no Lua errors (the runner checks)")
end)

test("camp: /makecamp, /campfire, /glide and /repair are registered and send their intents", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    H.eq(M.env.SLASH_BLEAKHOLDMAKECAMP1, "/makecamp")
    H.eq(M.env.SLASH_BLEAKHOLDMAKECAMP2, "/campfire")
    H.eq(M.env.SLASH_BLEAKHOLDGLIDE1, "/glide")
    H.eq(M.env.SLASH_BLEAKHOLDREPAIR1, "/repair")
    campst(M, { [10] = 0, [11] = 1 })
    M.env.SlashCmdList.BLEAKHOLDMAKECAMP("")
    M.env.SlashCmdList.BLEAKHOLDGLIDE("")
    M.env.SlashCmdList.BLEAKHOLDREPAIR("")
    M.Advance(0.5)
    H.ok(H.lastIntent(M, "CAMP") and H.lastIntent(M, "GLIDE") and H.lastIntent(M, "REPAIR"), "all three sent")
    H.eq(H.lastIntent(M, "CAMP").payload, "M")
    M.Advance(1.4)
    M.env.SlashCmdList.BLEAKHOLDMAKECAMP("pack")
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "CAMP").payload, "P", "/makecamp pack")
end)

-- The chat box's command lookup (ChatEdit_ParseText walks every SLASH_<name><n> of SlashCmdList): the command must
-- belong to exactly one handler, else the client picks one at random.
local function chat(M, text)
    local cmd, msg = text:match("^(/%S+)%s*(.-)$")
    local env, found = M.env, {}
    for name, fn in pairs(env.SlashCmdList) do
        local i = 1
        while env["SLASH_" .. name .. i] do
            if env["SLASH_" .. name .. i]:upper() == cmd:upper() then
                found[#found + 1] = fn
            end
            i = i + 1
        end
    end
    H.eq(#found, 1, "one handler for " .. cmd)
    return found[1](msg)
end

local function stockLogout(M)
    M.env.SLASH_LOGOUT1 = "/camp"
    M.env.SLASH_LOGOUT2 = "/logout"
    M.env.SlashCmdList.LOGOUT = function()
        M.loggedOut = (M.loggedOut or 0) + 1
    end
end

test("camp: /camp stays the stock logout, even on a camping realm; /makecamp and /campfire make camp", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    for k, v in pairs(M.env) do
        if type(k) == "string" and k:find("^SLASH_") and not k:find("^SLASH_LOGOUT") and type(v) == "string" then
            H.ok(v:lower() ~= "/camp", k .. " must not claim /camp")
        end
    end
    chat(M, "/camp")
    M.Advance(0.3)
    H.eq(M.loggedOut, 1, "stock logout")
    H.ok(not H.lastIntent(M, "CAMP"), "no CAMP from /camp")
    chat(M, "/makecamp")
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "CAMP").payload, "M", "/makecamp made camp")
    M.Advance(1.4)
    chat(M, "/campfire pack")
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "CAMP").payload, "P", "/campfire pack")
    H.eq(M.loggedOut, 1, "neither logs out")
end, { before = stockLogout })

test("camp: without camping on the realm /makecamp explains instead of sending", function(M, ns)
    FX.connect(M, H)
    chat(M, "/makecamp")
    M.Advance(0.3)
    H.ok(not H.lastIntent(M, "CAMP"), "no CAMP")
    H.ok(printed(M, "Camping is turned off") >= 1, "it explains")
    chat(M, "/camp")
    H.eq(M.loggedOut, 1, "/camp is still the stock logout")
end, { before = stockLogout })

test("camp: the Glide button shows for gliders only, counts its cooldown and glides on click", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    local gb = M.env.BleakholdGlideButton
    campst(M, {})
    M.Advance(0.3)
    H.ok(not gb:IsShown(), "empty glide field: no button")
    campst(M, { [10] = 90 })
    M.Advance(0.3)
    H.ok(gb:IsShown(), "a glider gets the button")
    H.eq(gb.icon:GetTexture(), "Interface\\Icons\\Spell_Magic_FeatherFall")
    H.ok(gb.cd:IsShown(), "cooldown on the button")
    H.eq(gb.cd:GetText(), "01:30")
    M.Advance(40)
    H.eq(gb.cd:GetText(), "50", "counts down locally, seconds under a minute")
    local n = H.countIntents(M, "GLIDE")
    gb:Click()
    M.Advance(0.3)
    H.eq(H.countIntents(M, "GLIDE"), n, "no GLIDE on cooldown")
    H.ok(printed(M, "Glide is not ready yet") >= 1)
    M.Advance(51)
    H.ok(not gb.cd:IsShown(), "ready")
    gb:Click()
    M.Advance(0.3)
    H.eq(H.countIntents(M, "GLIDE"), n + 1, "GLIDE when ready")
    M.Fire(gb, "OnEnter")
    H.contains(table.concat(M.env.GameTooltip.__lines or {}, "\n"), "Bind a key", "binding hint")
    M.Fire(gb, "OnLeave")
end)

test("camp: no Glide button while the realm has glide off", function(M, ns)
    FX.connect(M, H, CAMP_ONLY)
    campst(M, { [10] = 0 })
    M.Advance(0.5)
    H.ok(not M.env.BleakholdGlideButton:IsShown())
end)

test("camp: place buttons carry the profession icon; a missing icon falls back to the question mark", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    M.missingTextures["Interface\\Icons\\INV_Inscription_Tradeskill01"] = true
    campst(M, { [1] = "R", [2] = 60, [3] = 900, [9] = { { 171, 3 }, { 773, 1 } }, [8] = { { 773, 2, 0 } } })
    M.Advance(0.3)
    local f = M.env.BleakholdCampFrame
    H.eq(f.place[1].picon:GetTexture(), "Interface\\Icons\\Trade_Alchemy")
    H.eq(f.place[1].label:GetText(), "Place Alchemy Lab")
    H.eq(f.place[2].picon:GetTexture(), "Interface\\Icons\\INV_Misc_QuestionMark", "fallback icon")
    H.eq(f.objs[1].icon:GetTexture(), "Interface\\Icons\\INV_Misc_QuestionMark", "fallback icon for objects too")
    M.Fire(f.place[1], "OnEnter")
    local tip = table.concat(M.env.GameTooltip.__lines or {}, "\n")
    H.contains(tip, "Alchemy - Expert")
    H.contains(tip, "Everyone settled at this fire")
    M.Fire(f.place[1], "OnLeave")
end)

test("camp: a refusal from the local state asks for CAMPST again, so a stale cooldown mends itself", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    campst(M, { [5] = 600 })
    M.Advance(4)
    local before = select(2, gets(M):gsub("CAMPST", ""))
    M.env.SlashCmdList.BLEAKHOLD("camp")
    M.Advance(0.3)
    H.eq(select(2, gets(M):gsub("CAMPST", "")), before + 1, "GET CAMPST after the local refusal")
    campst(M, { [5] = 0 })                       -- a game master reset the cooldown
    M.env.SlashCmdList.BLEAKHOLD("camp")
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "CAMP").payload, "M", "camp made once the state is fresh")
end)

test("camp: no region of the camp UI mixes an edge anchor with a centre anchor on one axis", function(M, ns)
    local FP = { TOPLEFT = { 0, 0 }, TOP = { 0.5, 0 }, TOPRIGHT = { 1, 0 }, LEFT = { 0, 0.5 }, CENTER = { 0.5, 0.5 },
        RIGHT = { 1, 0.5 }, BOTTOMLEFT = { 0, 1 }, BOTTOM = { 0.5, 1 }, BOTTOMRIGHT = { 1, 1 } }
    FX.connect(M, H, ALL_BITS)
    campst(M, { [1] = "R", [2] = 50, [3] = 800, [4] = 1, [6] = 900, [7] = 10, [8] = { { 164, 2, 1 } },
        [9] = { { 185, 1 } }, [10] = 30, [11] = 1, [12] = 1 })
    M.Advance(0.5)
    campst(M, { [6] = 900, [7] = 10, [10] = 30 })
    M.Advance(0.5)
    local roots = { M.env.BleakholdCampFrame, M.env.BleakholdCampStatus, M.env.BleakholdGlideButton, M.env.BleakholdOrb_camp }
    local bad = {}
    local function check(o)
        local pts = o.__points
        if pts and #pts >= 2 then
            local fy, fx = {}, {}
            for _, p in ipairs(pts) do
                fy[FP[p[1]][2]] = true
                fx[FP[p[1]][1]] = true
            end
            if (fy[0.5] and (fy[0] or fy[1])) or (fx[0.5] and (fx[0] or fx[1])) then
                bad[#bad + 1] = tostring(pts[1][6])
            end
        end
        for _, c in ipairs(o.__children or {}) do check(c) end
        for _, r in ipairs(o.__regions or {}) do check(r) end
    end
    for _, r in ipairs(roots) do check(r) end
    H.ok(#bad == 0, #bad .. " mixed anchors: " .. table.concat(bad, ", "))
end)

test("camp: a campfire of the world (fire 0) keeps burning in the frame", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    campst(M, { [1] = "R", [2] = 60, [3] = 0 })
    M.Advance(0.3)
    H.eq(M.env.BleakholdCampFrame.fire:GetText(), "Fire: keeps burning")
end)
