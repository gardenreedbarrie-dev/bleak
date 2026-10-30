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

-- GlobalStrings.lua's SPELL_FAILED_NOT_ON_GROUND, before the addon loads (a stand-in for the client's text).
local GROUND_STOCK = "Cannot use on the ground"
local function stockGroundError(M)
    M.env.SPELL_FAILED_NOT_ON_GROUND = GROUND_STOCK
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
    -- fed is also the café's coffee (section 21): the tooltip names both, never food alone
    H.contains(table.concat(M.env.GameTooltip.__lines or {}, "\n"), "from food or caf\195\169 coffee", "fed's sources")
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

test("camp: camp_nofire and camp_mounted show the server's own reason", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    -- camp_nofire has two causes: no fire to stand at (CAMP O), no fire of one's own (CAMP P)
    H.send(M, "ERR", { { "CAMP", "e", "camp_nofire", "You have no campfire to pack up." } })
    H.eq(errorsShown(M, "You have no campfire to pack up."), 1, "the pack-up reason")
    H.send(M, "ERR", { { "CAMP", "f", "camp_nofire", "This fire is going out." } })
    H.eq(errorsShown(M, "This fire is going out."), 1)
    -- camp_mounted also covers a ship, falling and flying without a mount
    H.send(M, "ERR", { { "CAMP", "g", "camp_mounted",
        "Stand on solid ground to make camp: not mounted, flying, falling, on a vehicle or a ship." } })
    H.eq(errorsShown(M, "flying, falling, on a vehicle or a ship."), 1, "the whole server sentence")
    H.eq(errorsShown(M, "not at a campfire") + errorsShown(M, "Get off your mount"), 0, "no blanket sentence")
    -- a refusal without a sentence still gets one that fits every cause
    H.send(M, "ERR", { { "CAMP", "h", "camp_nofire", "" } })
    H.eq(errorsShown(M, "You need a campfire for that."), 1)
    H.send(M, "ERR", { { "CAMP", "i", "camp_mounted", "" } })
    H.eq(errorsShown(M, "Stand on solid ground to make camp."), 1)
end)

test("camp: repair_skill on a camping-only realm points at a camp anvil, locally and from the server", function(M, ns)
    FX.connect(M, H, CAMP_ONLY)
    campst(M, {})
    M.Advance(0.3)
    M.env.SlashCmdList.BLEAKHOLDREPAIR("")
    M.Advance(0.3)
    H.ok(not H.lastIntent(M, "REPAIR"), "refused locally")
    local text = "You can only repair at a campfire with a blacksmith's anvil."
    H.eq(errorsShown(M, text), 1, "the local refusal")
    H.send(M, "ERR", { { "REPAIR", "j", "repair_skill", "Repair at a campfire with an anvil." } })
    H.eq(errorsShown(M, text), 2, "the server's refusal reads the same")
    H.eq(errorsShown(M, "Blacksmithing skill"), 0, "more skill cannot help with field repair off")
end)

test("camp: repair_skill on a field-repair-only realm asks for Blacksmithing skill, not a campfire", function(M, ns)
    FX.connect(M, H, { [6] = 2048 })
    campst(M, {})
    M.Advance(0.3)
    M.env.SlashCmdList.BLEAKHOLDREPAIR("")
    M.Advance(0.3)
    H.ok(not H.lastIntent(M, "REPAIR"), "refused locally")
    H.eq(errorsShown(M, "You need more Blacksmithing skill to repair here."), 1)
    H.send(M, "ERR", { { "REPAIR", "k", "repair_skill", "You cannot repair here: you need Blacksmithing 75." } })
    H.eq(errorsShown(M, "You need more Blacksmithing skill to repair here."), 2, "the server's refusal too")
    H.eq(errorsShown(M, "campfire"), 0, "no camp anvil without camping")
end)

test("camp: before HELLO is answered the actions say the realm is not connected, not that it is off", function(M, ns)
    -- no HELLO answer yet: every feature bit reads as off
    M.env.SlashCmdList.BLEAKHOLDMAKECAMP("")
    M.env.SlashCmdList.BLEAKHOLDMAKECAMP("pack")
    M.env.SlashCmdList.BLEAKHOLDGLIDE("")
    M.env.SlashCmdList.BLEAKHOLDREPAIR("")
    M.env.BleakholdGlide()
    M.Advance(0.5)
    H.eq(printed(M, "Not connected to the realm."), 5, "each action explains")
    H.eq(printed(M, "turned off"), 0, "no feature is said to be off")
    H.ok(not H.lastIntent(M, "CAMP") and not H.lastIntent(M, "GLIDE") and not H.lastIntent(M, "REPAIR"), "nothing sent")
    -- once the realm answers, the same command makes camp
    FX.connect(M, H, ALL_BITS)
    M.env.SlashCmdList.BLEAKHOLDMAKECAMP("")
    M.Advance(0.3)
    H.eq(H.lastIntent(M, "CAMP").payload, "M")
end)

test("camp: an outdated addon says so before any feature check", function(M, ns)
    H.hello(M, { [1] = 3, [2] = 2 })
    H.ok(ns.Comm.outdated)
    M.env.SlashCmdList.BLEAKHOLDMAKECAMP("")
    M.env.SlashCmdList.BLEAKHOLDGLIDE("")
    M.env.SlashCmdList.BLEAKHOLDREPAIR("")
    H.eq(printed(M, "Your Bleakhold addon is out of date."), 3)
    H.eq(printed(M, "turned off"), 0)
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
    H.eq(gb.icon:GetTexture(), "Interface\\Icons\\Spell_Magic_FeatherFall", "the spellbook racial's icon (races.json 100801)")
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
    local tip = table.concat(M.env.GameTooltip.__lines or {}, "\n")
    H.contains(tip, "Bind a key", "binding hint")
    H.contains(tip, "Walk on Air", "the spell's name")
    H.contains(tip, "Glide through the air, steering your descent. Does not gain altitude.", "Forever's tooltip")
    H.ok(not tip:find("10 sec", 1, true), "no fixed seconds (BleakholdUi.Glide.Duration may differ)")
    H.contains(tip, "its time runs from the moment you use it", "the wait for a ledge counts")
    H.contains(tip, "Ready", "the cooldown line")
    M.Fire(gb, "OnLeave")
end)

test("camp: Walk on Air: the glide bar shows the server's glide, counts down and goes when it lands", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    local bar = ns.Camp.glideBar
    campst(M, { [10] = 0 })
    M.Advance(0.3)
    H.ok(M.env.BleakholdGlideButton:IsShown() and not bar:IsShown(), "no glide running: no bar")
    -- GLIDE accepted while falling: cooldown 90 and a glide of 10 s
    M.falling = true
    campst(M, { [10] = 90, [13] = 10 })
    M.Advance(0.3)
    H.ok(bar:IsShown(), "the bar while gliding")
    H.contains(bar.text:GetText(), "Walk on Air", "named")
    H.contains(bar.text:GetText(), "9.", "about 9.7 s left")
    M.Fire(M.env.BleakholdGlideButton, "OnEnter")
    H.contains(table.concat(M.env.GameTooltip.__lines or {}, "\n"), "Gliding: 10 sec left", "the tooltip tells the glide")
    M.Fire(M.env.BleakholdGlideButton, "OnLeave")
    M.Advance(3)
    H.contains(bar.text:GetText(), "6.", "counts down locally")
    local v = bar:GetValue()
    H.ok(v > 0.6 and v < 0.75, "progress about 0.67, got " .. tostring(v))
    -- lands: the bar goes at once, before the server's CAMPST
    M.falling = false
    M.Advance(0.2)
    H.ok(not bar:IsShown(), "landed: no bar")
    campst(M, { [10] = 86, [13] = 6 })   -- a CAMPST sent before the server saw the landing
    M.Advance(0.3)
    H.ok(not bar:IsShown(), "still landed")
    campst(M, { [10] = 86 })              -- the server ended the glide
    M.Advance(0.3)
    H.ok(not bar:IsShown(), "no glide")
    H.eq(M.env.BleakholdGlideButton.cd:GetText(), "01:26", "the cooldown on the button")
end)

test("camp: Walk on Air: a hop keeps the bar of a glide waiting for a ledge; it runs out by itself", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    local bar = ns.Camp.glideBar
    campst(M, { [10] = 90, [13] = 10 })   -- GLIDE on the ground: the glide waits for a ledge
    M.Advance(0.3)
    H.ok(bar:IsShown(), "waiting glide shown")
    M.falling = true                       -- a hop: shorter than a second in the air
    M.Advance(0.6)
    M.falling = false
    M.Advance(0.3)
    H.ok(bar:IsShown(), "a hop does not end it (the server keeps it too)")
    M.falling = true                       -- over a ledge: a real glide
    M.Advance(2)
    H.ok(bar:IsShown(), "gliding")
    M.Advance(7.5)
    H.ok(not bar:IsShown(), "ran out")
    -- a new glide starts the bar over (the next GLIDE after a game master's reset)
    M.falling = false
    campst(M, { [10] = 90, [13] = 10 })
    M.Advance(0.3)
    H.ok(bar:IsShown(), "a new glide")
    H.contains(bar.text:GetText(), "9.")
end)

test("camp: Walk on Air: a jump the server did not count keeps the glide; the next fall shows the bar", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    local bar = ns.Camp.glideBar
    local gb = M.env.BleakholdGlideButton
    campst(M, { [10] = 90, [13] = 10 })   -- GLIDE on the ground: the glide waits for a ledge
    M.Advance(0.3)
    H.ok(bar:IsShown(), "waiting glide shown")
    M.falling = true                       -- a running jump down a slope: over a second in the air, under 2.5 yd
    M.Advance(1.2)
    M.falling = false
    M.Advance(0.3)
    H.ok(not bar:IsShown(), "the client guesses a landing")
    campst(M, { [10] = 88, [13] = 8 })     -- the server still holds the waiting glide
    M.Advance(0.3)
    H.ok(not bar:IsShown(), "still guessed landed on the ground")
    M.falling = true                       -- over a real ledge: the server's glide starts
    M.Advance(0.5)
    H.ok(bar:IsShown(), "a new fall brings the bar back (the hidden bar has no OnUpdate of its own)")
    H.contains(bar.text:GetText(), "Walk on Air")
    M.Fire(gb, "OnEnter")
    H.contains(table.concat(M.env.GameTooltip.__lines or {}, "\n"), "Gliding: ", "the tooltip's Gliding line")
    M.Fire(gb, "OnLeave")
    M.Advance(2)
    H.ok(bar:IsShown(), "gliding")
    M.falling = false
    M.Advance(0.3)
    H.ok(not bar:IsShown(), "landed")
    campst(M, { [10] = 85 })               -- the server ended it
    M.Advance(0.3)
    M.falling = true
    M.Advance(0.5)
    H.ok(not bar:IsShown(), "no glide: a fall shows nothing")
end)

test("camp: the Glide key works in mid-air, and the new GLIDE refusals read as sentences", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    campst(M, { [10] = 0 })
    M.Advance(0.3)
    M.falling = true
    M.env.BleakholdGlide()
    M.Advance(0.3)
    H.ok(H.lastIntent(M, "GLIDE"), "GLIDE sent while falling")
    for code, text in pairs({ glide_mounted = "while mounted", glide_flying = "already flying", glide_water = "in water",
        glide_rooted = "rooted, stunned", glide_ground = "only glide while falling" }) do
        H.send(M, "ERR", { { "GLIDE", "c", code, "" } })
        H.ok(errorsShown(M, text) >= 1, code)
    end
end)

test("camp: Walk on Air in the spellbook: the Glide button makes way, the glide bar stays, the ground error is worded",
    function(M, ns)
    FX.connect(M, H, ALL_BITS)
    local gb, bar = M.env.BleakholdGlideButton, ns.Camp.glideBar
    campst(M, { [10] = 0 })
    M.Advance(0.3)
    H.ok(gb:IsShown(), "no spell yet: the Glide button")
    -- the server teaches the spell at login (mod-bleakhold-ui, BleakholdUi.Glide.CastSpell)
    local known = {}
    M.env.IsSpellKnown = function(id) return known[id] and 1 or nil end
    known[ns.Camp.GLIDE_SPELL] = true
    H.eq(ns.Camp.GLIDE_SPELL, 100801, "races.json's spellbook racial")
    M.FireEvent("LEARNED_SPELL_IN_TAB", 1)
    H.ok(not gb:IsShown(), "the action bar's Walk on Air replaces the Glide button")
    -- the cast on the ground fails with SPELL_FAILED_NOT_ON_GROUND: worded for the glide while the spell is known
    H.contains(M.env.SPELL_FAILED_NOT_ON_GROUND, "To glide: jump", "worded for the glide")
    H.contains(M.env.SPELL_FAILED_NOT_ON_GROUND, "You must be in the air for that.", "and still true for an item")
    -- a glide (cast from the action bar): the bar still shows where the button was, and counts down
    M.falling = true
    campst(M, { [10] = 90, [13] = 10 })
    M.Advance(0.3)
    H.ok(bar:IsShown() and not gb:IsShown(), "the glide bar without the button")
    H.eq(bar:GetParent(), M.env.UIParent, "the bar is not the button's child")
    local _, rel = bar:GetPoint(1)
    H.eq(rel, gb, "placed over the button's spot")
    M.Advance(2)
    H.contains(bar.text:GetText(), "7.", "counts down")
    M.falling = false
    M.Advance(0.3)
    H.ok(not bar:IsShown(), "landed")
    campst(M, { [10] = 85 })
    M.Advance(0.3)
    H.ok(not bar:IsShown() and not gb:IsShown())
    -- /glide and the key still glide (the server shares the cooldown with the spell)
    M.Advance(90)
    M.env.BleakholdGlide()
    M.Advance(0.3)
    H.ok(H.lastIntent(M, "GLIDE"), "the key binding still sends GLIDE")
    -- the editor still shows the button to place
    ns.Camp.glidePreview = true
    ns.Camp.RefreshGlide()
    H.ok(gb:IsShown(), "editor preview")
    ns.Camp.glidePreview = nil
    ns.Camp.RefreshGlide()
    H.ok(not gb:IsShown())
    -- the spell taken again (another race, the glide off): the button comes back
    known[ns.Camp.GLIDE_SPELL] = nil
    M.FireEvent("SPELLS_CHANGED")
    H.ok(gb:IsShown(), "the Glide button is back")
    H.eq(M.env.SPELL_FAILED_NOT_ON_GROUND, GROUND_STOCK, "no spell: the client's own ground error again")
end, { before = stockGroundError })

-- Who does not know Walk on Air keeps the client's own text: the server's item_only_for_flight gives the same cast
-- result for Arcane Charges (34475) used off the Isle of Quel'Danas flight, any race.
test("camp: without Walk on Air the ground error stays the client's own", function(M, ns)
    FX.connect(M, H, ALL_BITS)
    M.env.IsSpellKnown = function() return nil end
    M.FireEvent("SPELLS_CHANGED")
    M.FireEvent("PLAYER_ENTERING_WORLD")
    M.Advance(0.3)
    H.eq(M.env.SPELL_FAILED_NOT_ON_GROUND, GROUND_STOCK, "not reworded for an Arcane Charges player")
    campst(M, { [10] = 0 })   -- a glider without the spell yet (the Glide button): still the stock text
    M.Advance(0.3)
    H.ok(M.env.BleakholdGlideButton:IsShown())
    H.eq(M.env.SPELL_FAILED_NOT_ON_GROUND, GROUND_STOCK)
end, { before = stockGroundError })

test("camp: a High Elf who logs in knowing Walk on Air gets the glide wording at once", function(M, ns)
    H.contains(M.env.SPELL_FAILED_NOT_ON_GROUND, "To glide: jump", "worded from the first world entry")
end, { before = function(M)
    stockGroundError(M)
    M.env.IsSpellKnown = function(id) return id == 100801 and 1 or nil end
end })

-- The spellbook's Walk on Air known: the Glide button is hidden, and with it its 0.25 s OnUpdate.
local function knowGlideSpell(M, ns)
    M.env.IsSpellKnown = function(id) return id == ns.Camp.GLIDE_SPELL and 1 or nil end
    M.FireEvent("SPELLS_CHANGED")
end

test("camp: Walk on Air in the spellbook: thrown off again after a guessed landing, the glide bar comes back",
    function(M, ns)
    FX.connect(M, H, ALL_BITS)
    knowGlideSpell(M, ns)
    local gb, bar = M.env.BleakholdGlideButton, ns.Camp.glideBar
    M.falling = true
    campst(M, { [10] = 90, [13] = 10 })    -- cast from the action bar while falling
    M.Advance(1.5)
    H.ok(bar:IsShown() and not gb:IsShown(), "gliding: the bar, no button")
    M.falling = false                       -- a roof, for a moment: the client guesses a landing
    M.Advance(0.3)
    H.ok(not bar:IsShown(), "guessed landed")
    M.falling = true                        -- the server held the glide (a push on its way) and throws them off again
    M.Advance(0.3)
    H.ok(bar:IsShown(), "the bar is back, with the Glide button hidden")
    H.ok(not gb:IsShown(), "the button stays out of the way")
    H.contains(bar.text:GetText(), "Walk on Air")
    M.Advance(1.5)
    M.falling = false
    M.Advance(0.3)
    H.ok(not bar:IsShown(), "landed")
    campst(M, { [10] = 85 })                -- the server ended it
    M.falling = true
    M.Advance(1)
    H.ok(not bar:IsShown(), "no glide: a fall shows nothing")
end)

test("camp: Walk on Air in the spellbook: a waiting glide after a long slide still shows its bar off the ledge",
    function(M, ns)
    FX.connect(M, H, ALL_BITS)
    knowGlideSpell(M, ns)
    local gb, bar = M.env.BleakholdGlideButton, ns.Camp.glideBar
    campst(M, { [10] = 90, [13] = 10 })    -- cast on the ground: the glide waits for a ledge
    M.Advance(0.3)
    H.ok(bar:IsShown() and not gb:IsShown(), "waiting glide shown, no button")
    M.falling = true                        -- a slide down a slope: over a second in the air, under 2.5 yd
    M.Advance(1.2)
    M.falling = false
    M.Advance(0.3)
    H.ok(not bar:IsShown(), "the client guesses a landing")
    M.Advance(1)
    H.ok(not bar:IsShown(), "on the ground: stays down")
    M.falling = true                        -- over a real ledge: the server's glide starts, no new CAMPST
    M.Advance(0.5)
    H.ok(bar:IsShown(), "the real glide has its bar")
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
    H.eq(f.place[1].label:GetText(), "Place Alchemy Set", "an alchemy set, not a real Alchemy Lab")
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
