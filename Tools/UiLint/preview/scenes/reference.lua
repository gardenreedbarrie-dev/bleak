-- Reference scenes: the old BleakholdActivities window (the owner's addon "UI by Addicated", its Mythic+ page as in the
-- owner's screenshot) rebuilt from stock 3.3.5a textures, without FrameXML templates, the way the Bleakhold kit builds
-- its widgets. Render it next to a new window to compare the look:
--
--   Tools/UiLint/preview/render.sh Tools/UiLint/preview/scenes/reference.lua old_activities out.png \
--       --stock <stock art> --journal <Journal pictures>
--
-- Scenes: old_activities (as in the screenshot), old_activities_hover (the cursor over the Mythic button and the
-- Eclipse Rift row), old_buttons (the red button stretched and in slices, the close button and ring icons in every
-- state, a tooltip-backdrop panel).
local S = { standalone = { old_activities = true, old_activities_hover = true, old_buttons = true } }

local FONT = "Fonts\\FRIZQT__.TTF"
local JOURNAL = "Interface\\AddOns\\Bleakhold\\Art\\Journal\\"
local W, H = 940, 620

-- the old window, built in the game's environment (P.run); returns the frame and its parts
local function build()
    local function fs(parent, size, r, g, b, flags, layer)
        local t = parent:CreateFontString(nil, layer or "OVERLAY")
        t:SetFont(FONT, size, flags or "")
        t:SetTextColor(r or 1, g or 1, b or 1)
        t:SetShadowOffset(1, -1)
        t:SetShadowColor(0, 0, 0, 1)
        t:SetJustifyH("LEFT")
        return t
    end
    local function gold(parent, size) return fs(parent, size, 1, 0.82, 0) end
    local function ringIcon(parent, size, icon)
        local f = CreateFrame("Frame", nil, parent)
        f:SetSize(size, size)
        f.icon = f:CreateTexture(nil, "ARTWORK")
        f.icon:SetSize(size * 0.62, size * 0.62)
        f.icon:SetPoint("TOPLEFT", size * 0.2, -size * 0.18)
        SetPortraitToTexture(f.icon, "Interface\\Icons\\" .. icon)
        f.ring = f:CreateTexture(nil, "OVERLAY")
        f.ring:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
        f.ring:SetSize(size * 1.7, size * 1.7)
        f.ring:SetPoint("TOPLEFT", 0, 0)
        return f
    end
    local function squareIcon(parent, size, icon)
        local f = CreateFrame("Frame", nil, parent)
        f:SetSize(size, size)
        f:SetBackdrop({ edgeFile = "Interface\\Buttons\\WHITE8X8", edgeSize = 1 })
        f:SetBackdropBorderColor(0, 0, 0, 1)
        f.icon = f:CreateTexture(nil, "ARTWORK")
        f.icon:SetPoint("TOPLEFT", 1, -1)
        f.icon:SetPoint("BOTTOMRIGHT", -1, 1)
        f.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
        f.icon:SetTexture("Interface\\Icons\\" .. icon)
        return f
    end
    -- the red panel button without a template. "stretched": UIPanelButtonTemplate as 3.3.5a has it and the owner's
    -- screenshot shows it (one texture per state over the whole button, U 0-0.625, V 0-0.6875, so the caps widen
    -- with the button); "slices": UIPanelButtonTemplate2 (12 px caps, U 0-0.09375 / 0.09375-0.53125 /
    -- 0.53125-0.625). Highlight in ADD; label gold, white under the cursor, grey disabled.
    local SLICES = { { 0, 0.09375 }, { 0.09375, 0.53125 }, { 0.53125, 0.625 } }
    local function button(parent, w, h, text, style)
        local b = CreateFrame("Button", nil, parent)
        b:SetSize(w, h)
        if style == "slices" then
            local function slices(file, layer, blend)
                local t = {}
                for i, u in ipairs(SLICES) do
                    local x = b:CreateTexture(nil, layer)
                    x:SetTexture(file)
                    x:SetTexCoord(u[1], u[2], 0, 0.6875)
                    if blend then x:SetBlendMode(blend) end
                    if i == 1 then
                        x:SetPoint("TOPLEFT") x:SetPoint("BOTTOMLEFT") x:SetWidth(12)
                    elseif i == 3 then
                        x:SetPoint("TOPRIGHT") x:SetPoint("BOTTOMRIGHT") x:SetWidth(12)
                    end
                    t[i] = x
                end
                t[2]:SetPoint("TOPLEFT", t[1], "TOPRIGHT")
                t[2]:SetPoint("BOTTOMRIGHT", t[3], "BOTTOMLEFT")
                return t
            end
            local sets = { NORMAL = slices("Interface\\Buttons\\UI-Panel-Button-Up", "BACKGROUND"),
                PUSHED = slices("Interface\\Buttons\\UI-Panel-Button-Down", "BACKGROUND"),
                DISABLED = slices("Interface\\Buttons\\UI-Panel-Button-Disabled", "BACKGROUND") }
            slices("Interface\\Buttons\\UI-Panel-Button-Highlight", "HIGHLIGHT", "ADD")
            b.paintSlices = function(state)
                for k, set in pairs(sets) do
                    for _, x in ipairs(set) do if k == state then x:Show() else x:Hide() end end
                end
            end
        else
            for _, st in ipairs({ { "SetNormalTexture", "Up" }, { "SetPushedTexture", "Down" },
                { "SetDisabledTexture", "Disabled" }, { "SetHighlightTexture", "Highlight" } }) do
                b[st[1]](b, "Interface\\Buttons\\UI-Panel-Button-" .. st[2])
            end
            for _, t in ipairs({ b:GetNormalTexture(), b:GetPushedTexture(), b:GetDisabledTexture(),
                b:GetHighlightTexture() }) do
                t:SetTexCoord(0, 0.625, 0, 0.6875)
            end
        end
        b.label = fs(b, 12, 1, 0.82, 0)
        b.label:SetJustifyH("CENTER")
        b.label:SetText(text)
        function b:Paint(state)
            if self.paintSlices then self.paintSlices(state) else self:SetButtonState(state) end
            if state == "DISABLED" then
                self.label:SetTextColor(0.5, 0.5, 0.5)
            elseif self.hot then
                self.label:SetTextColor(1, 1, 1)
            else
                self.label:SetTextColor(1, 0.82, 0)
            end
            self.label:ClearAllPoints()
            if state == "PUSHED" then self.label:SetPoint("CENTER", 1, -1) else self.label:SetPoint("CENTER", 0, 1) end
        end
        b:SetScript("OnEnter", function(self) self.hot = true self:Paint(self:GetButtonState()) end)
        b:SetScript("OnLeave", function(self) self.hot = nil self:Paint(self:GetButtonState()) end)
        b:Paint("NORMAL")
        return b
    end
    -- UIPanelCloseButton's art as state textures (32 x 32)
    local function closeButton(parent)
        local c = CreateFrame("Button", nil, parent)
        c:SetSize(32, 32)
        c:SetNormalTexture("Interface\\Buttons\\UI-Panel-MinimizeButton-Up")
        c:SetPushedTexture("Interface\\Buttons\\UI-Panel-MinimizeButton-Down")
        c:SetDisabledTexture("Interface\\Buttons\\UI-Panel-MinimizeButton-Disabled")
        c:SetHighlightTexture("Interface\\Buttons\\UI-Panel-MinimizeButton-Highlight", "ADD")
        return c
    end
    local function panelBox(f)
        f:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
            edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border", tile = true, tileSize = 16, edgeSize = 16,
            insets = { left = 4, right = 4, top = 4, bottom = 4 } })
        f:SetBackdropColor(0.02, 0.02, 0.04, 0.88)
        f:SetBackdropBorderColor(0.45, 0.45, 0.5, 1)
    end

    local F = CreateFrame("Frame", "BleakholdOldActivitiesReference", UIParent)
    F:SetSize(W, H)
    F:SetPoint("CENTER", 0, 20)
    F:SetFrameStrata("HIGH")
    F:SetBackdrop({ bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background-Dark",
        edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border", tile = true, tileSize = 32, edgeSize = 32,
        insets = { left = 11, right = 12, top = 12, bottom = 11 } })
    F.bar = F:CreateTexture(nil, "ARTWORK")
    F.bar:SetTexture(0, 0, 0, 0.55)
    F.bar:SetPoint("TOPLEFT", 64, -12)
    F.bar:SetPoint("TOPRIGHT", -12, -12)
    F.bar:SetHeight(26)
    F.title = gold(F, 14)
    F.title:SetPoint("TOP", 26, -18)
    F.title:SetJustifyH("CENTER")
    F.title:SetText("Mythic+ Dungeons")
    F.portrait = ringIcon(F, 62, "Spell_Holy_BorrowedTime")
    F.portrait:SetPoint("TOPLEFT", -6, 8)
    F.portrait:SetFrameLevel(F:GetFrameLevel() + 5)
    F.close = closeButton(F)
    F.close:SetPoint("TOPRIGHT", -4, -4)

    local NAV = {
        { "journey", "Dungeon Journey", "Achievement_Dungeon_ClassicDungeonMaster" },
        { "mplus", "Mythic+ Dungeons", "Spell_Holy_BorrowedTime" },
        { "rift", "Eclipse Rift", "Ability_Druid_EclipseOrange" },
        { "heroic", "Heroic Dungeons", "Achievement_Dungeon_HEROIC_GloryoftheRaider" },
        { "group", "Group Finder", "INV_Misc_GroupNeedMore" },
    }
    F.nav = CreateFrame("Frame", nil, F)
    F.nav:SetPoint("TOPLEFT", 18, -46)
    F.nav:SetSize(216, H - 64)
    panelBox(F.nav)
    F.navButtons = {}
    for i, n in ipairs(NAV) do
        local b = CreateFrame("Button", nil, F.nav)
        b:SetSize(204, 66)
        b:SetPoint("TOPLEFT", 6, -6 - (i - 1) * 70)
        b.id = n[1]
        b.bg = b:CreateTexture(nil, "BACKGROUND")
        b.bg:SetAllPoints()
        b.bg:SetTexture("Interface\\Buttons\\WHITE8X8")
        b.edge = CreateFrame("Frame", nil, b)
        b.edge:SetAllPoints()
        b.edge:SetBackdrop({ edgeFile = "Interface\\Buttons\\WHITE8X8", edgeSize = 1 })
        b.edge:SetBackdropBorderColor(0.45, 0.68, 1, 1)
        b.line = b:CreateTexture(nil, "ARTWORK")
        b.line:SetTexture(1, 1, 1, 0.08)
        b.line:SetHeight(1)
        b.line:SetPoint("BOTTOMLEFT")
        b.line:SetPoint("BOTTOMRIGHT")
        b.ring = ringIcon(b, 50, n[3])
        b.ring:SetPoint("LEFT", 6, -2)
        b.label = fs(b, 13, 0.92, 0.88, 0.78)
        b.label:SetPoint("LEFT", 66, 0)
        b.label:SetText(n[2])
        b.hl = b:CreateTexture(nil, "HIGHLIGHT")
        b.hl:SetAllPoints()
        b.hl:SetTexture(1, 1, 1, 0.05)
        F.navButtons[i] = b
    end
    function F:Select(id)
        for _, b in ipairs(self.navButtons) do
            local sel = b.id == id
            b.bg:SetGradientAlpha("HORIZONTAL", sel and 0.16 or 0.09, sel and 0.32 or 0.1, sel and 0.65 or 0.13,
                sel and 0.95 or 0.85, sel and 0.05 or 0.04, sel and 0.12 or 0.04, sel and 0.3 or 0.06,
                sel and 0.15 or 0.2)
            if sel then b.edge:Show() else b.edge:Hide() end
            b.label:SetTextColor(sel and 1 or 0.92, sel and 0.82 or 0.88, sel and 0 or 0.78)
        end
    end

    -- content: the dungeon picture on the right, fading into the dark
    F.content = CreateFrame("Frame", nil, F)
    F.content:SetPoint("TOPLEFT", 244, -46)
    F.content:SetPoint("BOTTOMRIGHT", -18, 18)
    panelBox(F.content)
    local CH = H - 64
    F.art = F.content:CreateTexture(nil, "BORDER")
    F.art:SetPoint("TOPRIGHT", -5, -5)
    F.art:SetSize((CH - 10) * 390 / 423, CH - 10)
    F.art:SetVertexColor(0.85, 0.82, 0.8)
    F.art:SetTexture(JOURNAL .. "bg_SCHOLOMANCE")
    F.art:SetTexCoord(0, 0.76171875, 0, 0.826171875)
    F.fade = F.content:CreateTexture(nil, "ARTWORK")
    F.fade:SetTexture("Interface\\Buttons\\WHITE8X8")
    F.fade:SetPoint("TOPLEFT", F.art, "TOPLEFT", 0, 0)
    F.fade:SetPoint("BOTTOMLEFT", F.art, "BOTTOMLEFT", 0, 0)
    F.fade:SetWidth(260)
    F.fade:SetGradientAlpha("HORIZONTAL", 0.02, 0.02, 0.04, 1, 0.02, 0.02, 0.04, 0)
    F.shade = F.content:CreateTexture(nil, "ARTWORK")
    F.shade:SetTexture("Interface\\Buttons\\WHITE8X8")
    F.shade:SetPoint("TOPLEFT", 5, -5)
    F.shade:SetPoint("BOTTOMRIGHT", F.fade, "BOTTOMLEFT", 0, 0)
    F.shade:SetVertexColor(0.02, 0.02, 0.04, 1)

    -- the Mythic+ page with the week of the screenshot
    local p = CreateFrame("Frame", nil, F.content)
    p:SetAllPoints()
    p.title = gold(p, 22)
    p.title:SetPoint("TOPLEFT", 20, -18)
    p.title:SetText("Mythic+ Dungeons")
    p.desc = fs(p, 12, 1, 1, 1)
    p.desc:SetPoint("TOPLEFT", 20, -50)
    p.desc:SetWidth(390)
    p.desc:SetSpacing(3)
    p.desc:SetText("Timed dungeons with weekly affixes. Finish a Mythic 0 dungeon for your first keystone, then "
        .. "right-click the key inside its dungeon. Beat the timer to upgrade it.")
    p.keyIcon = squareIcon(p, 44, "INV_Misc_Key_15")
    p.keyIcon:SetPoint("TOPLEFT", 20, -122)
    p.keyText = fs(p, 15, 1, 1, 1)
    p.keyText:SetPoint("TOPLEFT", p.keyIcon, "TOPRIGHT", 10, -4)
    p.keyText:SetWidth(330)
    p.keyText:SetText("No keystone")
    p.keySub = fs(p, 11, 0.75, 0.75, 0.75)
    p.keySub:SetPoint("TOPLEFT", p.keyText, "BOTTOMLEFT", 0, -4)
    p.keySub:SetWidth(330)
    p.keySub:SetText("Defeat the final boss of a Mythic 0 dungeon to get one.")
    local function section(text, x, y)
        local t = gold(p, 14)
        t:SetPoint("TOPLEFT", x, y)
        t:SetText(text)
    end
    section("This Week's Affixes", 20, -184)
    local AFFIXES = { { "Ability_Warrior_Rampage", "+2" }, { "Ability_Druid_ChallangingRoar", "+4" },
        { "Spell_Shadow_CreepingPlague", "+7" }, { "Spell_Frost_WizardMark", "+10" },
        { "Spell_Holy_SummonChampion", "+14" }, { "Spell_Holy_DivineIntervention", "+14" } }
    for i, a in ipairs(AFFIXES) do
        local x = squareIcon(p, 34, a[1])
        x:SetPoint("TOPLEFT", 20 + (i - 1) * 40, -206)
        x.lvl = fs(x, 9, 1, 1, 1, "OUTLINE")
        x.lvl:SetPoint("BOTTOMRIGHT", -1, 2)
        x.lvl:SetText(a[2])
    end
    section("Season Dungeons", 20, -258)
    local DUNGEONS = { { "Scarlet Monastery: Armory", "SCARLETMONASTERY" },
        { "Scarlet Monastery: Cathedral", "SCARLETMONASTERY" }, { "Stratholme: Main Gate", "STRATHOLME" },
        { "Stratholme: Service Entrance", "STRATHOLME" }, { "Scholomance", "SCHOLOMANCE" },
        { "Blackrock Depths: Upper City", "BLACKROCKDEPTHS" }, { "Lower Blackrock Spire", "BLACKROCKSPIRE" },
        { "Dire Maul: West", "DIREMAUL" }, { "Zul'Farrak", "ZULFARRAK" }, { "Shadow Labyrinth", "AUCHINDOUN" },
        { "Utgarde Pinnacle", "UTGARDEPINNACLE" }, { "Halls of Lightning", "HALLSOFLIGHTNING" } }
    for i, d in ipairs(DUNGEONS) do
        local col, row = (i - 1) % 2, math.floor((i - 1) / 2)
        local r = CreateFrame("Frame", nil, p)
        r:SetSize(206, 40)
        r:SetPoint("TOPLEFT", 18 + col * 214, -280 - row * 44)
        r:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8X8", edgeFile = "Interface\\Buttons\\WHITE8X8",
            edgeSize = 1 })
        r:SetBackdropColor(0.04, 0.04, 0.06, 0.9)
        r:SetBackdropBorderColor(0.25, 0.25, 0.3, 1)
        r.thumb = r:CreateTexture(nil, "ARTWORK")
        r.thumb:SetSize(64, 36)
        r.thumb:SetPoint("LEFT", 2, 0)
        r.thumb:SetTexture(JOURNAL .. "btn_" .. d[2])
        r.thumb:SetTexCoord(0, 0.6796875, 0, 0.75)
        r.name = fs(r, 11, 1, 1, 1)
        r.name:SetPoint("LEFT", r.thumb, "RIGHT", 8, 0)
        r.name:SetWidth(100)
        r.name:SetText(d[1])
        r.best = fs(r, 14, 1, 0.82, 0, "OUTLINE")
        r.best:SetPoint("RIGHT", -8, 0)
        r.best:SetJustifyH("RIGHT")
        r.best:SetText("|cff606060-|r")
    end
    p.mythic = button(p, 190, 26, "Set difficulty: Mythic", "stretched")
    p.mythic:SetPoint("BOTTOMRIGHT", -18, 18)
    F.page = p
    F:Select("mplus")
    F.kit = { button = button, closeButton = closeButton, ringIcon = ringIcon, squareIcon = squareIcon,
        panelBox = panelBox, fs = fs }
    return F
end

S.old_activities = function(M, ns, RS, env, P)
    return P.run(build)
end

S.old_activities_hover = function(M, ns, RS, env, P)
    local F = P.run(build)
    P.hover(F.page.mythic)
    P.hover(F.navButtons[3])
    P.hover(F.close)
    return F
end

-- the kit's pieces in every state, at 2x: the red button stretched (top row) and in slices (second row), the close
-- button, ring icons (the last one desaturated) and a tooltip-backdrop panel
S.old_buttons = function(M, ns, RS, env, P)
    local F = P.run(build)
    F:Hide()
    local K = F.kit
    return P.run(function()
        local host = CreateFrame("Frame", nil, UIParent)
        host:SetSize(700, 250)
        host:SetPoint("CENTER")
        host:SetScale(2)
        host:SetBackdrop({ bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background-Dark", tile = true,
            tileSize = 32 })
        local STATES = { "NORMAL", "HOVER", "PUSHED", "DISABLED" }
        local ICONS = { "Achievement_Dungeon_ClassicDungeonMaster", "Spell_Holy_BorrowedTime",
            "Ability_Druid_EclipseOrange", "INV_Misc_GroupNeedMore" }
        for i, s in ipairs(STATES) do
            for row, style in ipairs({ "stretched", "slices" }) do
                local b = K.button(host, 150, 24, s:sub(1, 1) .. s:sub(2):lower(), style)
                b:SetPoint("TOPLEFT", 20 + (i - 1) * 165, -16 - (row - 1) * 34)
                if s == "HOVER" then
                    P.hover(b)
                elseif s == "PUSHED" then
                    b:Paint("PUSHED")
                elseif s == "DISABLED" then
                    b:Disable()
                    b:Paint("DISABLED")
                end
            end
            local c = K.closeButton(host)
            c:SetPoint("TOPLEFT", 20 + (i - 1) * 165, -90)
            if s == "PUSHED" then c:SetButtonState("PUSHED") elseif s == "DISABLED" then c:Disable()
            elseif s == "HOVER" then P.hover(c) end
            local r = K.ringIcon(host, 50, ICONS[i])
            r:SetPoint("TOPLEFT", 70 + (i - 1) * 165, -84)
            if s == "DISABLED" then r.icon:SetDesaturated(true) end
        end
        local panel = CreateFrame("Frame", nil, host)
        panel:SetSize(660, 40)
        panel:SetPoint("BOTTOMLEFT", 20, 14)
        K.panelBox(panel)
        local t = K.fs(panel, 12, 1, 1, 1)
        t:SetPoint("LEFT", 12, 0)
        t:SetText("A tooltip-backdrop panel: Mythic 0, +10, 1234567890")
        return host
    end)
end

return S
