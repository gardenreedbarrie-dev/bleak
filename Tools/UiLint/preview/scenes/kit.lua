-- The Bleakhold kit (Interface/AddOns/Bleakhold/Widgets.lua) piece by piece, in every state, and the kit's own frames
-- (the dialog) plus the windows that have no scene in windows.lua (the case window, the toast):
--
--   Tools/UiLint/preview/render.sh Tools/UiLint/preview/scenes/kit.lua kitsheet out.png --stock <stock art> \
--       --size 1500x940 --ui-scale 0.817
--
-- Scenes: kitsheet (every piece: buttons of each style normal / hover / pushed / disabled, held choices, page arrows,
-- tabs, rows, the close button, the slider, nav rows, ring portraits, class circles, marks, icons and item
-- buttons, panels, the selected card, tags, rewards, affixes, progress bars, the scroll bar, dropdowns closed and
-- open, text colours, stat labels, column headers and wrapped text, in a window of the kit), dialog (UI.Confirm),
-- prompt (UI.Prompt, with the input box), case (the case window with a case), toast (a toast).
local S = {}

local function demo(M)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(1)
end

local STATES = { "Normal", "Hover", "Pushed", "Disabled" }

-- put a kit button in a state: hover runs OnEnter (and lights the HIGHLIGHT layer), pushed runs OnMouseDown
local function setState(M, P, b, state)
    if state == "Hover" then
        P.hover(b)
    elseif state == "Pushed" then
        P.hover(b)
        M.Fire(b, "OnMouseDown", "LeftButton")
    elseif state == "Disabled" then
        b:SetActive(false)
    end
end

S.kitsheet = function(M, ns, RS, env, P)
    local UI = ns.UI
    local C = UI.C
    M.missingTextures["Interface\\Icons\\INV_No_Such_Icon"] = true
    M.items[32837] = { name = "Gold Glaive" }
    return P.run(function()
        local W, H = 1440, 860
        local win = UI.Window("BleakholdKitSheet", W, H, "Bleakhold Kit", "star")
        win:ClearAllPoints()
        win:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
        win:Show()
        local c = win.content
        local function label(text, x, y)
            local t = UI.Heading(c, text)
            t:SetPoint("TOPLEFT", c, "TOPLEFT", x, y)
            return t
        end
        local function note(parent, text, x, y, color)
            local t = UI.Text(parent, 10, color or C.dim)
            t:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
            t:SetText(text)
            return t
        end

        -- buttons: each style in its four states
        label("Buttons (normal, hover, pushed, disabled)", 16, -10)
        local rows = {
            { "Red panel button", "dark", 150, 22 },
            { "Dialog (StaticPopup)", "dialog", 128, 21 },
            { "Small (ghost): minor actions", "ghost", 130, 20 },
        }
        for r, def in ipairs(rows) do
            local y = -34 - (r - 1) * 30
            note(c, def[1], 16, y - 6)
            for i, s in ipairs(STATES) do
                local b = UI.Button(c, def[3], def[4], s, def[2])
                b:SetPoint("TOPLEFT", c, "TOPLEFT", 200 + (i - 1) * (def[3] + 12), y)
                setState(M, P, b, s)
            end
        end
        note(c, "Choices: the chosen one held down, lit", 860, -40)
        local modes = {}
        for i, m in ipairs({ "Normal", "Heroic", "Mythic" }) do
            local b = UI.Button(c, 90, 22, m, i == 3 and "tabOn" or "tab")
            b:SetPoint("TOPLEFT", c, "TOPLEFT", 1060 + (i - 1) * 94, -34)
            modes[i] = b
        end
        note(c, "Page arrows (spellbook)", 860, -76)
        local prev = UI.PageButton(c, "Prev")
        prev:SetPoint("TOPLEFT", c, "TOPLEFT", 1060, -66)
        prev:SetActive(false)
        local page = UI.Text(c, 12, C.text, "body", "CENTER")
        page:SetPoint("LEFT", prev, "RIGHT", 4, 0)
        page:SetWidth(90)
        page:SetText("Page 1 / 13")
        local nextB = UI.PageButton(c, "Next")
        nextB:SetPoint("LEFT", page, "RIGHT", 4, 0)
        P.hover(nextB)

        -- tab strip on a panel, list rows, the close button
        label("Tab strip (strip / stripOn), list rows (row / rowOn), close button", 16, -132)
        local stripPanel = UI.Box(c, 520, 70, C.panel, C.border)
        stripPanel:SetPoint("TOPLEFT", c, "TOPLEFT", 16, -184)
        local tabs = { { "Transmog (412)", "strip" }, { "Legacy Sets", "stripOn" }, { "Mounts", "strip" },
            { "Pets", "strip" } }
        local prevTab
        for i, t in ipairs(tabs) do
            local b = UI.Button(c, 100, 24, t[1], t[2])
            if prevTab then
                b:SetPoint("BOTTOMLEFT", prevTab, "BOTTOMRIGHT", -8, 0)
            else
                b:SetPoint("BOTTOMLEFT", stripPanel, "TOPLEFT", 8, -2)
            end
            prevTab = b
            if i == 3 then P.hover(b) end
        end
        note(stripPanel, "The open tab's legs cover the panel's edge; Mounts under the cursor", 12, -14)
        local list = UI.Box(c, 220, 82, C.deep, C.strong, 0.92, "panel")
        list:SetPoint("TOPLEFT", c, "TOPLEFT", 560, -170)
        for i, t in ipairs({ { "All dungeons", "row" }, { "Scholomance", "rowOn" }, { "Stratholme", "row" },
            { "Dire Maul", "row" } }) do
            local r = UI.Button(list, 204, 18, t[1], t[2], 12)
            r.label:ClearAllPoints()
            r.label:SetPoint("LEFT", r, "LEFT", 22, 0)
            r.label:SetJustifyH("LEFT")
            r:SetPoint("TOPLEFT", list, "TOPLEFT", 8, -5 - (i - 1) * 18)
            if i == 3 then P.hover(r) end
        end
        for i, s in ipairs(STATES) do
            local x = UI.CloseButton(c, function() end)
            x:SetPoint("TOPLEFT", c, "TOPLEFT", 810 + (i - 1) * 40, -180)
            if s == "Hover" then
                P.hover(x)
            elseif s == "Pushed" then
                x:SetButtonState("PUSHED")
            elseif s == "Disabled" then
                x:SetActive(false)
            end
        end
        note(c, "normal  hover  pushed  disabled", 812, -214)
        -- slider
        local slider = UI.Slider(c, 200, "Bloom", "0", "1")
        slider:SetPoint("TOPLEFT", c, "TOPLEFT", 1010, -196)
        slider:SetMinMaxValues(0, 1)
        slider:SetValue(0.35)
        slider.value:SetText("0.35")

        -- nav rows, ring portraits, marks
        label("Nav rows, ring portraits, class circles, marks, icons", 16, -268)
        local navs = { { "dungeon", "Dungeon Journey", "tab" }, { "key", "Mythic+ Dungeons", "tabOn" },
            { "rift", "Eclipse Rift", "tab" } }
        for i, n in ipairs(navs) do
            local b = UI.IconButton(c, 204, 66, n[1], n[2], n[3])
            b:SetPoint("TOPLEFT", c, "TOPLEFT", 16, -292 - (i - 1) * 70)
            if i == 3 then P.hover(b) end
        end
        local badges = { { 62, "trophy" }, { 46, "shield" }, { 40, "chest" } }
        local x = 240
        for _, d in ipairs(badges) do
            local b = UI.Badge(c, d[1], d[2], C.chip, C.gold)
            b:SetPoint("TOPLEFT", c, "TOPLEFT", x, -298)
            x = x + d[1] + 18
        end
        local locked = UI.Badge(c, 46, "mount", C.panel, C.teal)
        locked:SetPoint("TOPLEFT", c, "TOPLEFT", x, -298)
        locked:SetLocked(true)
        note(c, "Badges 62 / 46 / 40; locked (greyed)", 240, -372)
        local classes = { "WARRIOR", "PALADIN", "HUNTER", "ROGUE" }
        for i, cl in ipairs(classes) do
            local p = UI.ClassPortrait(c, 36, cl)
            p:SetPoint("TOPLEFT", c, "TOPLEFT", 240 + (i - 1) * 42, -396)
            p:SetChosen(i == 2)
        end
        note(c, "Class circles (Paladin chosen)", 240, -444)
        local marks = { { "yellow" }, { "green" }, { "red" }, { "gray" } }
        for i, m in ipairs(marks) do
            local d = UI.StatusDot(c, 14, m[1])
            d:SetPoint("TOPLEFT", c, "TOPLEFT", 240 + (i - 1) * 20, -468)
        end
        local r1 = UI.Radio(c, 16, true)
        r1:SetPoint("TOPLEFT", c, "TOPLEFT", 330, -467)
        local r2 = UI.Radio(c, 16, false)
        r2:SetPoint("TOPLEFT", c, "TOPLEFT", 350, -467)
        local ck = UI.Check(c, 20)
        ck:SetPoint("TOPLEFT", c, "TOPLEFT", 376, -465)
        local done = UI.Text(c, 12, C.teal)
        done:SetPoint("LEFT", ck, "RIGHT", 2, 0)
        done:SetText("Complete")
        note(c, "Indicator balls, radio (checked / not), done", 240, -490)
        local icons = { "INV_Misc_Key_15", "Spell_Holy_BorrowedTime", "INV_Misc_Bag_10", "INV_No_Such_Icon" }
        for i, ic in ipairs(icons) do
            local q = UI.Icon(c, 36, ic)
            q:SetPoint("TOPLEFT", c, "TOPLEFT", 16 + (i - 1) * 44, -510)
        end
        local item = UI.ItemButton(c, 36, "INV_Chest_Plate03")
        item:SetPoint("TOPLEFT", c, "TOPLEFT", 200, -510)
        local item2 = UI.ItemButton(c, 36, "INV_Gauntlets_10")
        item2:SetPoint("TOPLEFT", item, "TOPRIGHT", 12, 0)
        item2:SetCollected(false)
        note(c, "UI.Icon (missing: the question mark); item buttons (collected, not)", 16, -552)

        -- panels, selection, tags, bars
        label("Panels, the selected card, tags, rewards, affixes, progress bars", 800, -268)
        local panel = UI.Box(c, 200, 90, C.card, C.border)
        panel:SetPoint("TOPLEFT", c, "TOPLEFT", 800, -292)
        note(panel, "UI.Box: the tooltip panel", 10, -10, C.text)
        local small = UI.Box(c, 200, 30, C.chip, C.chipBorder)
        small:SetPoint("TOPLEFT", panel, "TOPRIGHT", 14, 0)
        note(small, "A small box: 1 px edge", 8, -10, C.text)
        local fill = UI.Box(c, 200, 30, C.zebra)
        fill:SetPoint("TOPLEFT", small, "BOTTOMLEFT", 0, -8)
        note(fill, "No border: a plain fill", 8, -10, C.text)
        local selected = UI.Box(c, 170, 44, C.card, C.border)
        selected:SetPoint("TOPLEFT", small, "TOPRIGHT", 14, 0)
        UI.Select(selected, true)
        note(selected, "UI.Select: the chosen card", 10, -14, C.text)
        local doneCard = UI.Box(c, 170, 40, C.card, C.border)
        doneCard:SetPoint("TOPLEFT", selected, "BOTTOMLEFT", 0, -6)
        local dck = UI.Check(doneCard, 20)
        dck:SetPoint("TOPRIGHT", doneCard, "TOPRIGHT", -6, -6)
        local dtx = UI.Text(doneCard, 12, C.teal)
        dtx:SetPoint("TOPLEFT", doneCard, "TOPLEFT", 10, -12)
        dtx:SetText("Complete")
        local reset = UI.Pill(c, "", C.text, 11)
        reset:SetValue("7 h 11 min", "Daily reset")
        reset:SetPoint("TOPLEFT", c, "TOPLEFT", 800, -400)
        local live = UI.Pill(c, "Live", C.teal, 11)
        live:SetPoint("LEFT", reset, "RIGHT", 16, 0)
        local bounty = UI.Pill(c, "Bounty", C.orange, 11)
        bounty:SetPoint("LEFT", live, "RIGHT", 16, 0)
        local affixes = { "Fortified", "Bolstering", "Volcanic", "Necrotic" }
        local prevA
        for i, a in ipairs(affixes) do
            local ic = UI.AffixIcon(c, 26)
            ic:SetAffix(a, UI.AFFIX_LEVELS[i])
            if prevA then
                ic:SetPoint("LEFT", prevA, "RIGHT", 4, 0)
            else
                ic:SetPoint("TOPLEFT", c, "TOPLEFT", 1110, -394)
            end
            prevA = ic
        end
        local rw = UI.Reward(c, 16, 11)
        rw:SetReward("C", 150)
        rw:SetPoint("TOPLEFT", c, "TOPLEFT", 800, -428)
        local rw2 = UI.Reward(c, 16, 11)
        rw2:SetReward("I", 1, 32837)
        rw2:SetPoint("LEFT", rw, "RIGHT", 16, 0)
        local rw3 = UI.Reward(c, 16, 11)
        rw3:SetReward("S", 120)
        rw3:SetPoint("LEFT", rw2, "RIGHT", 16, 0)
        local bars = { { 0.7, nil, "14 / 20" }, { 0.8, nil, "80%" }, { 0.39, C.gold, "2,140 / 5,500" },
            { 1, nil, "3 / 3" } }
        for i, bd in ipairs(bars) do
            local bar = UI.Bar(c, 240, 14, bd[2])
            bar:SetPoint("TOPLEFT", c, "TOPLEFT", 806 + ((i - 1) % 2) * 270, -462 - math.floor((i - 1) / 2) * 30)
            bar:SetProgress(bd[1], bd[3])
        end
        note(c, "The achievement progress bar: green, gold for currency; the count inside", 800, -526)

        -- scroll, dropdowns, text
        label("Scroll bar (whole rows), dropdowns (closed, open), text, labels, column headers", 16, -580)
        local box = UI.Box(c, 240, 150, C.card, C.border)
        box:SetPoint("TOPLEFT", c, "TOPLEFT", 16, -604)
        local sf = UI.Scroll(box)
        sf:SetPoint("TOPLEFT", box, "TOPLEFT", 8, -10)
        -- a list viewport of whole rows (7 x 18), scrolled a row at a time
        sf:SetSize(214, 7 * 18)
        for i = 1, 14 do
            local t = UI.Text(sf.child, 12, i % 2 == 0 and C.text or C.dim)
            t:SetPoint("TOPLEFT", sf.child, "TOPLEFT", 4, -(i - 1) * 18 - 2)
            t:SetText("List entry " .. i)
        end
        sf:SetContentHeight(14 * 18)
        sf:SetStep(18)
        sf:SetVerticalScroll(54)
        sf:SetContentHeight(14 * 18)
        local items = { { value = 0, text = "All classes" }, { value = 1, text = "Warrior" },
            { value = 2, text = "Paladin" }, { value = 8, text = "Mage" } }
        local closed = UI.Dropdown(c, 170, function() end)
        closed:SetPoint("TOPLEFT", c, "TOPLEFT", 290, -610)
        closed:SetItems(items)
        closed:SetValue(1, true)
        local hovered = UI.Dropdown(c, 170, function() end)
        hovered:SetPoint("TOPLEFT", closed, "BOTTOMLEFT", 0, -10)
        hovered:SetItems(items)
        hovered:SetValue(0, true)
        P.hover(hovered)
        local open = UI.Dropdown(c, 170, function() end)
        open:SetPoint("TOPLEFT", c, "TOPLEFT", 490, -610)
        open:SetItems(items)
        open:SetValue(2, true)
        open:Click()
        local texts = {
            { "Gold Title 22", 22, C.gold }, { "Section Heading 14 (UI.Heading)", 14, C.gold },
            { "White body text, 12: timed dungeons with weekly affixes.", 12, C.text },
            { "Secondary grey (dim)", 12, C.dim }, { "Stock grey (mute)", 12, C.mute },
            { "Green: done, good", 12, C.teal }, { "Red: errors", 12, C.red }, { "Orange: warnings", 12, C.orange },
            { "Epic purple", 12, C.purple },
        }
        local ty = -604
        for _, t in ipairs(texts) do
            local fs = UI.Text(c, t[2], t[3])
            fs:SetPoint("TOPLEFT", c, "TOPLEFT", 720, ty)
            fs:SetText(t[1])
            ty = ty - t[2] - 8
        end
        local quality = UI.Text(c, 12, C.text)
        quality:SetPoint("TOPLEFT", c, "TOPLEFT", 1080, -604)
        quality:SetText("|cff9d9d9dPoor|r  |cffffffffCommon|r  |cff1eff00Uncommon|r\n|cff0070ddRare|r  "
            .. "|cffa335eeEpic|r  |cffff8000Legendary|r")
        quality:SetSpacing(4)
        -- a table: column headers (WhoFrameColumnHeaderTemplate) over rows of the 1 px row look
        local cols = { { "Rank", 48 }, { "Group", 150 }, { "Time Left", 90 } }
        local hx = 1080
        for _, col in ipairs(cols) do
            local h = UI.ColumnHeader(c, col[2], col[1])
            h:SetPoint("TOPLEFT", c, "TOPLEFT", hx, -652)
            hx = hx + col[2] - 2
        end
        for i, row in ipairs({ { "1", "Ashbringer's Own", "14:22" }, { "2", "Night Watch", "15:07" } }) do
            local r = UI.Box(c, 284, 22, C.card, C.border)
            r:SetPoint("TOPLEFT", c, "TOPLEFT", 1080, -678 - (i - 1) * 24)
            local xs = { 8, 54, 202 }
            for k, v in ipairs(row) do
                local t = UI.Text(r, 12, k == 2 and C.text or C.dim)
                t:SetPoint("LEFT", r, "LEFT", xs[k], 0)
                t:SetText(v)
            end
        end
        -- a stat label (gold 12, Title Case) and its white value, and a wrapped description (UI.Para)
        local stat = UI.Label(c, "Board changes in")
        stat:SetPoint("TOPLEFT", c, "TOPLEFT", 1080, -736)
        local statV = UI.Text(c, 12, C.text)
        statV:SetPoint("LEFT", stat, "RIGHT", 6, 0)
        statV:SetText("3 d 4 h")
        local para = UI.Para(c, 12, C.text, 300)
        para:SetPoint("TOPLEFT", c, "TOPLEFT", 1080, -758)
        para:SetText("UI.Para: timed dungeons with weekly affixes; each level makes the enemies stronger.")
        return { win, open.menu }
    end)
end

S.dialog = function(M, ns, RS, env, P)
    demo(M)
    ns.UI.Confirm("Reroll this task for 50 Mythic Coins?\nThe server checks the price again.", function() end,
        "Reroll")
    return env.BleakholdDialog
end

S.prompt = function(M, ns, RS, env, P)
    demo(M)
    ns.UI.Prompt("Name this outfit:", "Raid night", function() end, "Save", 24)
    return env.BleakholdDialog
end

S.toast = function(M, ns, RS, env, P)
    demo(M)
    ns.Toast.Push({ kicker = "Task Complete", title = "Key sweeper", sub = "20 Mythic Coins are waiting in Tasks" })
    M.Advance(1)
    return env.BleakholdToastFrame
end

S.case = function(M, ns, RS, env, P)
    demo(M)
    M.items[32837] = { name = "Gold Glaive" }
    M.items[32838] = { name = "Rainbow Glaive" }
    M.items[32839] = { name = "Ashen Blade" }
    M.items[990001] = { name = "Glaive Case" }
    ns.Demo.Push("CASE", { { 990001, "Glaive Case", "Unlock it to receive one of the items below.", "", "" },
        { 32837, 1, 1200, 4 }, { 32838, 2, 400, 5 }, { 32839, 1, 2400, 3 } })
    ns.Cases.Open(990001)
    M.Advance(0.5)
    return env.BleakholdCaseFrame
end

return S
