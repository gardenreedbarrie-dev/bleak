-- Bleakhold UI - window chrome shared by the quest log and the PvP windows (modules/questlog_skin.lua,
-- modules/pvpframe_skin.lua), open to any other window as AddicatUI.WindowChrome. UI by Addicated.
-- Ported from the Bleakhold UI addon's Chrome.lua. Everything here is AddicatUI's own retail art (its atlas registry,
-- nine-slice layouts, red buttons, minimal scroll bars), looked up at run time: when a piece is missing
-- WindowChrome.chrome() is false and the windows stay WoW's.
local addon = select(2, ...)

local WC = {}
addon.WindowChrome = WC

WC.GOLD = { 0.90, 0.80, 0.50 }
WC.CREDIT = "Bleakhold UI  -  made by Addicated"

-- AddicatUI's atlas entry: { file, width, height, left, right, top, bottom, htile, vtile } or nil
function WC.atlasInfo(name)
    local info = addon.atlasinfo
    return info and info[name]
end

-- apply an atlas to a texture; false (and nothing changed) when AddicatUI does not have it
function WC.atlas(tex, name, useSize)
    local e = WC.atlasInfo(name)
    if not e or not tex then return false end
    tex:SetTexture(e[1])
    tex:SetTexCoord(e[4], e[5], e[6], e[7])
    if tex.SetHorizTile then
        tex:SetHorizTile(e[8] and true or false)
        tex:SetVertTile(e[9] and true or false)
    end
    if useSize then tex:SetSize(e[2], e[3]) end
    return true
end

-- a texture path inside AddicatUI's Textures folder (AddicatUI_Art)
function WC.auiFile(rel)
    return addon._dir and (addon._dir .. rel)
end

-- everything the windows need from AddicatUI; checked once
local ok
function WC.chrome()
    if ok ~= nil then return ok end
    local CP = addon.CharacterPanel
    local NS = _G.AddicatUI_NineSlice
    ok = (addon._dir and addon.atlasinfo and NS and NS.GetLayout and NS.ApplyLayout
        and NS.GetLayout("PortraitFrameTemplate") and NS.GetLayout("InsetFrameTemplate") and addon.SkinRedButton
        and CP and CP.ReskinScrollBar and CP.ModernizeCloseButton
        and WC.atlasInfo("questbg-parchment") and WC.atlasInfo("questlog-main-background")
        and WC.atlasInfo("_UI-Frame-TopTileStreaks")) and true or false
    return ok
end

function WC.nineSlice(frame, layoutName)
    local NS = _G.AddicatUI_NineSlice
    local layout = NS and NS.GetLayout and NS.GetLayout(layoutName)
    if layout then
        NS.ApplyLayout(frame, layout)
        return true
    end
    return false
end

-- hide a frame's own textures (not its children's); keep = { [texture] = true }
function WC.stripTextures(frame, keep)
    for _, r in ipairs({ frame:GetRegions() }) do
        if r:GetObjectType() == "Texture" and not (keep and keep[r]) then
            r:SetTexture(nil)
            r:Hide()
        end
    end
end

-- the AddicatUI window body: rock ground and the worn strip under the title on the window itself, the metal nine-slice
-- (with the portrait ring) on a border frame above the window's content, so child frames (portraits, lists) never
-- draw over the metal
function WC.dressWindow(frame, w, h)
    frame:SetSize(w, h)
    frame:SetHitRectInsets(0, 0, 0, 0)
    local border = CreateFrame("Frame", nil, frame)
    border:SetAllPoints(frame)
    border:SetFrameLevel(frame:GetFrameLevel() + 10)
    border:EnableMouse(false)
    WC.nineSlice(border, "PortraitFrameTemplate")
    frame.bhBorder = border
    local rock = frame:CreateTexture(nil, "BACKGROUND", nil, -6)
    rock:SetTexture(WC.auiFile("UI\\ui-background-rock"))
    rock:SetHorizTile(true)
    rock:SetVertTile(true)
    rock:SetPoint("TOPLEFT", frame, "TOPLEFT", 2, -21)
    rock:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -2, 2)
    local streaks = frame:CreateTexture(nil, "BORDER")
    WC.atlas(streaks, "_UI-Frame-TopTileStreaks")
    streaks:SetHorizTile(true)
    streaks:SetHeight(43)
    streaks:SetPoint("TOPLEFT", frame, "TOPLEFT", 6, -21)
    streaks:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -2, -21)
    frame.bhRock, frame.bhStreaks = rock, streaks
end

-- keep the border (and what must sit on it: title, close button) above content that was raised later
function WC.topLayers(frame)
    local top = frame.bhBorder
    if not top then return end
    local hi = frame:GetFrameLevel()
    local skip = { [top] = true }
    for _, h in ipairs(frame.bhHolders or {}) do skip[h] = true end
    if frame.bhClose then skip[frame.bhClose] = true end
    local function scan(f)
        for _, c in ipairs({ f:GetChildren() }) do
            if not skip[c] then
                hi = math.max(hi, c:GetFrameLevel())
                scan(c)
            end
        end
    end
    scan(frame)
    if top:GetFrameLevel() <= hi then top:SetFrameLevel(hi + 1) end
    for _, h in ipairs(frame.bhHolders or {}) do h:SetFrameLevel(top:GetFrameLevel() + 1) end
    if frame.bhClose then frame.bhClose:SetFrameLevel(top:GetFrameLevel() + 2) end
end

-- the round portrait under the ring (the ring is the nine-slice's top-left corner)
function WC.portrait(frame, tex, file)
    tex = tex or frame:CreateTexture(nil, "BACKGROUND", nil, 1)
    if file then tex:SetTexture(file) end
    tex:ClearAllPoints()
    tex:SetPoint("TOPLEFT", frame, "TOPLEFT", -5, 7)
    tex:SetSize(62, 62)
    tex:SetDrawLayer("BACKGROUND", 1)
    tex:Show()
    return tex
end

-- the window title, centred in the title band, on a holder above the metal frame. `window` is the dressed window when
-- `frame` is one of its tabs (the holder belongs to the tab, so it hides with it)
function WC.title(frame, fs, window)
    window = window or frame
    local h = frame.bhTitleHolder
    if not h then
        h = CreateFrame("Frame", nil, frame)
        h:SetAllPoints(window)
        h:EnableMouse(false)
        frame.bhTitleHolder = h
        window.bhHolders = window.bhHolders or {}
        table.insert(window.bhHolders, h)
    end
    h:SetFrameLevel((window.bhBorder or window):GetFrameLevel() + 2)
    fs:SetParent(h)
    fs:ClearAllPoints()
    fs:SetPoint("TOPLEFT", window, "TOPLEFT", 60, -5)
    fs:SetPoint("TOPRIGHT", window, "TOPRIGHT", -26, -5)
    fs:SetHeight(14)
    fs:SetJustifyH("CENTER")
    fs:Show()
end

-- an inset panel (gold trim + marble ground) as its own frame, so content lifted above it stays on top
function WC.inset(parent, marble)
    local f = CreateFrame("Frame", nil, parent)
    WC.nineSlice(f, "InsetFrameTemplate")
    if marble ~= false then
        local bg = f:CreateTexture(nil, "BACKGROUND")
        bg:SetTexture(WC.auiFile("UI\\ui-background-marble"))
        bg:SetHorizTile(true)
        bg:SetVertTile(true)
        bg:SetAllPoints(f)
        f.bg = bg
    end
    return f
end

function WC.redButton(btn)
    if btn and addon.SkinRedButton then addon.SkinRedButton(btn) end
end

function WC.closeButton(btn, owner)
    local CP = addon.CharacterPanel
    if btn and CP and CP.ModernizeCloseButton then CP.ModernizeCloseButton(btn, owner, 1, 0) end
    if btn and owner then owner.bhClose = btn end
end

-- AddicatUI's minimal scroll bar; `host` is the pane it sits flush inside
function WC.scrollBar(scroll, host, top, x, bottom, steppers)
    local CP = addon.CharacterPanel
    if CP and CP.ReskinScrollBar then CP.ReskinScrollBar(scroll, host, top, x, bottom, steppers) end
end

-- put a reskinned bar back into its lane (Blizzard re-anchors some bars on every show)
function WC.placeScrollBar(scroll, host, top, x, bottom)
    local bar = scroll and _G[(scroll:GetName() or "") .. "ScrollBar"]
    if not bar then return end
    local inset = 7
    bar:ClearAllPoints()
    bar:SetPoint("TOPRIGHT", host, "TOPRIGHT", x or -6, -(inset + (top or 0)))
    bar:SetPoint("BOTTOMRIGHT", host, "BOTTOMRIGHT", x or -6, inset + (bottom or 0))
end

-- a small "by Addicated" line at the bottom edge of a window
function WC.creditLine(frame, y)
    local t = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    t:SetPoint("BOTTOM", frame, "BOTTOM", 0, y or -14)
    t:SetText("Bleakhold UI by Addicated")
    t:SetTextColor(WC.GOLD[1], WC.GOLD[2], WC.GOLD[3], 0.75)
    return t
end
