-- Bleakhold: graphics settings. The Bleakhold client draws the world through its own post-processing
-- (Engine/Source/BleakFx: ambient occlusion, light shafts, bloom, clarity, colour grading, FXAA, sharpening),
-- draws water with reflections, refraction and colour by depth, and moves the grass in the wind; this window
-- sets its bleakFx* console variables, with presets. The client saves them in Config.wtf. A stock
-- client has none of these variables: the window then only says so. Stock 3.3.5a look, as the Video options: the
-- Interface Options' boxes (General, Effects), UIDropDownMenu-dressed lists (preset, anti-aliasing), check buttons
-- for the on/off variables, OptionsSliderTemplate's sliders, red panel buttons, Defaults at the bottom left.
local ADDON, ns = ...
local U, UI = ns.U, ns.UI
local C = UI.C

local floor, max, min = math.floor, math.max, math.min

local G = {}
ns.Graphics = G

-- Sliders: console variable, label, range, step, help.
G.SLIDERS = {
    { cvar = "bleakFxAO", label = "Ambient occlusion", min = 0, max = 1, step = 0.05,
      help = "Soft shadows where surfaces meet. Needs multisampling off." },
    { cvar = "bleakFxAORadius", label = "Occlusion radius", min = 0.25, max = 5, step = 0.25, unit = " yd",
      help = "How far the ambient occlusion reaches." },
    { cvar = "bleakFxContactShadows", label = "Contact shadows", min = 0, max = 1, step = 0.05,
      help = "Short shadows from the sun where things meet the ground and each other. Needs multisampling off." },
    { cvar = "bleakFxSunShafts", label = "Light shafts", min = 0, max = 1, step = 0.05,
      help = "Rays of sunlight through trees and buildings. Needs multisampling off." },
    { cvar = "bleakFxBloom", label = "Bloom", min = 0, max = 2, step = 0.05,
      help = "Glow around bright light: the sun, spells, lamps." },
    { cvar = "bleakFxClarity", label = "Clarity", min = 0, max = 1, step = 0.05,
      help = "Local contrast: brings out the detail of the world." },
    { cvar = "bleakFxContrast", label = "Contrast", min = 0, max = 1, step = 0.02,
      help = "A film-like contrast curve." },
    { cvar = "bleakFxSaturation", label = "Saturation", min = 0, max = 2, step = 0.05,
      help = "Colour strength (1 = unchanged)." },
    { cvar = "bleakFxVibrance", label = "Vibrance", min = -1, max = 1, step = 0.05,
      help = "Strengthens dull colours more than strong ones." },
    { cvar = "bleakFxWarmth", label = "Warmth", min = -1, max = 1, step = 0.05,
      help = "Colour temperature: cool blue to warm gold." },
    { cvar = "bleakFxBrightness", label = "Brightness", min = 0.5, max = 1.5, step = 0.02,
      help = "Midtone brightness (1 = unchanged)." },
    { cvar = "bleakFxShadows", label = "Shadow lift", min = -0.05, max = 0.1, step = 0.002,
      help = "Raises or deepens the darkest parts of the picture." },
    { cvar = "bleakFxVignette", label = "Vignette", min = 0, max = 1, step = 0.02,
      help = "Darker screen corners." },
    { cvar = "bleakFxSharpen", label = "Sharpening", min = 0, max = 1, step = 0.05,
      help = "Contrast-adaptive sharpening: crisper textures without halos." },
    { cvar = "bleakFxWaterRipples", label = "Water ripples", min = 0, max = 0.4, step = 0.02,
      help = "How rough the water's surface is: calm mirror to choppy." },
    { cvar = "bleakFxGrassWind", label = "Grass wind", min = 0, max = 2, step = 0.1,
      help = "How strongly the wind moves the grass: 0 still, 1 a breeze, 2 a strong wind." },
}

-- Switches: console variable, label, states, help. One with states is a dropdown of them; one without is a check
-- button (on and off).
G.TOGGLES = {
    { cvar = "bleakFxAA", label = "Anti-aliasing", states = { { 0, "Off" }, { 1, "FXAA" }, { 2, "SMAA" } },
      help = "Smooths jagged edges after the world is drawn: FXAA is the fastest, SMAA the sharpest. Works with "
          .. "multisampling off." },
    { cvar = "bleakFxWater", label = "Modern water",
      help = "Water with reflections, refraction and colour by depth. Off: the stock water." },
    { cvar = "bleakFxWaterReflections", label = "Reflections",
      help = "The water reflects trees, hills and buildings, not only the sky. Needs multisampling off." },
    { cvar = "bleakFxGrassParting", label = "Grass parting",
      help = "The grass bends away from your character as you walk through it." },
}

-- Presets set every slider plus the master switch and anti-aliasing. "bleakhold" is the client default.
G.PRESETS = {
    { key = "off", text = "Off (stock look)", values = { bleakFx = 0 } },
    { key = "classic", text = "Classic+", values = {
        bleakFx = 1, bleakFxAA = 1, bleakFxWater = 1, bleakFxWaterReflections = 1, bleakFxWaterRipples = 0.1,
        bleakFxGrassWind = 0.7, bleakFxGrassParting = 1, bleakFxAO = 0.4, bleakFxAORadius = 1.25,
        bleakFxContactShadows = 0.35,
        bleakFxSunShafts = 0.25, bleakFxBloom = 0.2, bleakFxClarity = 0.2, bleakFxContrast = 0.08,
        bleakFxSaturation = 1, bleakFxVibrance = 0.1, bleakFxWarmth = 0.1, bleakFxBrightness = 1, bleakFxShadows = 0,
        bleakFxVignette = 0.08, bleakFxSharpen = 0.2 } },
    { key = "bleakhold", text = "Bleakhold", values = {
        bleakFx = 1, bleakFxAA = 2, bleakFxWater = 1, bleakFxWaterReflections = 1, bleakFxWaterRipples = 0.12,
        bleakFxGrassWind = 1, bleakFxGrassParting = 1, bleakFxAO = 0.6, bleakFxAORadius = 1.5,
        bleakFxContactShadows = 0.6,
        bleakFxSunShafts = 0.4, bleakFxBloom = 0.35, bleakFxClarity = 0.35, bleakFxContrast = 0.18,
        bleakFxSaturation = 1.05, bleakFxVibrance = 0.25, bleakFxWarmth = 0.3, bleakFxBrightness = 1,
        bleakFxShadows = 0.012, bleakFxVignette = 0.18, bleakFxSharpen = 0.25 } },
    { key = "cinematic", text = "Cinematic", values = {
        bleakFx = 1, bleakFxAA = 2, bleakFxWater = 1, bleakFxWaterReflections = 1, bleakFxWaterRipples = 0.16,
        bleakFxGrassWind = 1.3, bleakFxGrassParting = 1, bleakFxAO = 0.85, bleakFxAORadius = 2,
        bleakFxContactShadows = 0.8,
        bleakFxSunShafts = 0.7, bleakFxBloom = 0.6, bleakFxClarity = 0.45, bleakFxContrast = 0.3,
        bleakFxSaturation = 1.1, bleakFxVibrance = 0.35, bleakFxWarmth = 0.4, bleakFxBrightness = 1,
        bleakFxShadows = 0.02, bleakFxVignette = 0.3, bleakFxSharpen = 0.35 } },
}

-- Whether this client has the Bleakhold graphics (registered variables are the only ones GetCVar finds).
function G.Available()
    return GetCVar ~= nil and GetCVar("bleakFx") ~= nil
end

local function cvarNumber(name, default)
    local v = G.Available() and tonumber(GetCVar(name)) or nil
    return v or default
end

local ON_OFF = { { 0, "off" }, { 1, "on" } }

-- The state of a switch's variable (the first state when the value is none of them), and the next one. On/off
-- switches read any value but 0 as on, like the client.
function G.ToggleState(t)
    local states = t.states or ON_OFF
    local value = cvarNumber(t.cvar, states[#states][1])
    if not t.states then
        value = value ~= 0 and 1 or 0
    end
    for i, state in ipairs(states) do
        if state[1] == value then
            return state, states[i % #states + 1]
        end
    end
    return states[1], states[2]
end

-- Rounded to the slider's step, so that saved values stay short ("0.35", not "0.3500001").
function G.Snap(s, v)
    v = max(s.min, min(s.max, v))
    local n = floor((v - s.min) / s.step + 0.5)
    local snapped = s.min + n * s.step
    return tonumber(string.format("%.4f", snapped))
end

local function format(s, v)
    local text = string.format("%.2f", v)
    text = text:gsub("0+$", ""):gsub("%.$", "")
    return text .. (s.unit or "")
end

function G.Set(name, value)
    if not G.Available() then
        return
    end
    SetCVar(name, tostring(value))
end

-- The preset whose values all match the current variables, or "custom".
function G.CurrentPreset()
    if not G.Available() then
        return nil
    end
    if cvarNumber("bleakFx", 1) == 0 then
        return "off"
    end
    for _, p in ipairs(G.PRESETS) do
        if p.key ~= "off" then
            local same = true
            for name, value in pairs(p.values) do
                if math.abs(cvarNumber(name, -99) - value) > 0.0001 then
                    same = false
                    break
                end
            end
            if same then
                return p.key
            end
        end
    end
    return "custom"
end

function G.ApplyPreset(key)
    for _, p in ipairs(G.PRESETS) do
        if p.key == key then
            for name, value in pairs(p.values) do
                G.Set(name, value)
            end
            G.Refresh()
            return true
        end
    end
    return false
end

------------------------------------------------------------------------------------------------------
-- Window
------------------------------------------------------------------------------------------------------
-- the content (UI.ContentSize) holds the General box (two rows; a third for the note when there is one) and the 8
-- rows of Effects; the window grows by the note's row while it shows
local GENERAL_H, NOTE_H = 88, 32
local W, H = 668, 672
local f = UI.Window("BleakholdGraphics", W, H, "Graphics", "Interface\\Icons\\INV_Misc_Gear_01")
f:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
G.frame = f
local content = f.content
local CW = UI.ContentSize(W, H)
local syncing = false

-- An options box as the Interface Options draw them: a tooltip panel with its title above its top left corner.
local BOX_W = CW - 32
local function optionsBox(title, h)
    local box = UI.Box(content, BOX_W, h, C.panel, C.border, nil, "panel")
    box.title = UI.Text(content, 12, C.gold)
    box.title:SetPoint("BOTTOMLEFT", box, "TOPLEFT", 6, 3)
    box.title:SetText(title)
    return box
end

local general = optionsBox("General", GENERAL_H)
general:SetPoint("TOPLEFT", content, "TOPLEFT", 16, -26)
f.general = general
local presetLabel = UI.Text(general, 12, C.gold)
presetLabel:SetPoint("TOPLEFT", general, "TOPLEFT", 16, -20)
presetLabel:SetText("Preset")
f.preset = UI.Dropdown(general, 190, function(value)
    if not syncing and value ~= "custom" then
        G.ApplyPreset(value)
    end
end)
f.preset:SetPoint("LEFT", presetLabel, "RIGHT", 10, -1)

local function hideHelp()
    if GameTooltip then
        GameTooltip:Hide()
    end
end

-- the switches (f.toggles, in G.TOGGLES' order): anti-aliasing as a dropdown right of the preset, the on/off ones as
-- check buttons on the row under them
f.toggles = {}
local CHECK_COL = 190
local lastDropdown, checks = f.preset, 0
for i, t in ipairs(G.TOGGLES) do
    local b
    if t.states then
        local label = UI.Text(general, 12, C.gold)
        label:SetPoint("LEFT", lastDropdown, "RIGHT", 24, 1)
        label:SetText(t.label)
        b = UI.Dropdown(general, 110, function(value)
            if not syncing then
                G.Set(t.cvar, value)
                G.Refresh()
            end
        end)
        b:SetPoint("LEFT", label, "RIGHT", 10, -1)
        local items = {}
        for _, state in ipairs(t.states) do
            items[#items + 1] = { value = state[1], text = state[2] }
        end
        b:SetItems(items)
        b.title = label
        b.tooltip = function()
            return { t.label, t.help }
        end
        lastDropdown = b
    else
        b = UI.CheckButton(general, t.label, 24)
        b:SetPoint("TOPLEFT", general, "TOPLEFT", 12 + checks * CHECK_COL, -50)
        checks = checks + 1
        b:SetScript("OnClick", function()
            local state = G.ToggleState(t)
            G.Set(t.cvar, state[1] ~= 0 and 0 or 1)
            if PlaySound then
                PlaySound(state[1] ~= 0 and "igMainMenuOptionCheckBoxOff" or "igMainMenuOptionCheckBoxOn")
            end
            G.Refresh()
        end)
        b:SetScript("OnEnter", function(self)
            UI.ShowTooltip(self, { t.label, t.help })
        end)
        b:SetScript("OnLeave", hideHelp)
    end
    b.def = t
    f.toggles[i] = b
end

f.note = UI.Text(general, 12, C.orange, "body", "LEFT")
f.note:SetPoint("TOPLEFT", general, "TOPLEFT", 16, -84)
f.note:SetPoint("TOPRIGHT", general, "TOPRIGHT", -16, -84)
f.note:SetHeight(NOTE_H - 4)
f.note:SetJustifyV("TOP")

-- the Interface Options' buttons: Defaults at the bottom left, the window's own close at the bottom right
f.reset = UI.Button(content, 110, 22, "Defaults", "dark", 12)
f.reset:SetPoint("BOTTOMLEFT", content, "BOTTOMLEFT", 16, 12)
f.reset:SetScript("OnClick", function()
    G.ApplyPreset("bleakhold")
end)
f.done = UI.Button(content, 110, 22, "Close", "dark", 12)
f.done:SetPoint("BOTTOMRIGHT", content, "BOTTOMRIGHT", -16, 12)
f.done:SetScript("OnClick", function()
    f:Hide()
end)

local COLS, COL_W, COL_GAP, ROW_H = 2, 268, 36, 50
local rows = math.ceil(#G.SLIDERS / COLS)
local effects = optionsBox("Effects", 28 + rows * ROW_H)
effects:SetPoint("TOPLEFT", general, "BOTTOMLEFT", 0, -26)
f.effects = effects
f.sliders = {}
for i, s in ipairs(G.SLIDERS) do
    local col, row = (i - 1) % COLS, floor((i - 1) / COLS)
    local holder = CreateFrame("Frame", nil, effects)
    holder:SetSize(COL_W, ROW_H)
    holder:SetPoint("TOPLEFT", effects, "TOPLEFT", 20 + col * (COL_W + COL_GAP), -18 - row * ROW_H)

    -- the options slider: gold title above, the value in white beside it, the range under the ends
    local slider = UI.Slider(holder, COL_W, s.label, format(s, s.min), format(s, s.max))
    slider:SetPoint("TOPLEFT", holder, "TOPLEFT", 0, -16)
    slider:SetMinMaxValues(s.min, s.max)
    slider:SetValueStep(s.step)
    holder.label = slider.title
    holder.value = slider.value
    slider:SetScript("OnValueChanged", function(self, v)
        local snapped = G.Snap(s, v)
        holder.value:SetText(format(s, snapped))
        if not syncing then
            G.Set(s.cvar, snapped)
            f.preset:SetValue(G.CurrentPreset() or "custom", true)
        end
    end)
    slider:SetScript("OnEnter", function(self)
        UI.ShowTooltip(self, { s.label, s.help })
    end)
    slider:SetScript("OnLeave", function()
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    holder.slider = slider
    holder.def = s
    f.sliders[i] = holder
end

local function presetItems()
    local items = {}
    for _, p in ipairs(G.PRESETS) do
        items[#items + 1] = { value = p.key, text = p.text }
    end
    items[#items + 1] = { value = "custom", text = "Custom" }
    return items
end
f.preset:SetItems(presetItems())

-- Puts the variables into the controls (without writing them back).
function G.Refresh()
    syncing = true
    local available = G.Available()
    local on = available and cvarNumber("bleakFx", 1) ~= 0
    for _, holder in ipairs(f.sliders) do
        local s = holder.def
        local v = G.Snap(s, cvarNumber(s.cvar, s.min))
        holder.slider:SetValue(v)
        holder.value:SetText(format(s, v))
        if on then
            holder.slider:Enable()
            holder:SetAlpha(1)
        else
            holder.slider:Disable()
            holder:SetAlpha(0.45)
        end
    end
    f.preset:SetValue(G.CurrentPreset() or "custom", true)
    f.preset:SetActive(available)
    f.reset:SetActive(available)
    for _, b in ipairs(f.toggles) do
        local state = G.ToggleState(b.def)
        if b.def.states then
            b:SetValue(state[1], true)
            UI.SetColor(b.title, on and C.gold or C.mute)
        else
            b:SetChecked(state[1] ~= 0)
        end
        b:SetActive(on)
    end
    local note = ""
    if not available then
        note = "This client has no Bleakhold graphics. Install the Bleakhold client to use them."
    elseif on and (tonumber(GetCVar("gxMultisample") or "1") or 1) > 1 then
        note = "Ambient occlusion, contact shadows, light shafts and water reflections need multisampling off: "
            .. "Video options, Multisampling 1x. Anti-aliasing here replaces it."
    end
    f.note:SetText(note)
    -- the General box holds the note's row only while there is a note; the window grows with it
    local noteRow = note ~= "" and NOTE_H or 0
    general:SetHeight(GENERAL_H + noteRow)
    f:SetHeight(H + noteRow)
    syncing = false
end

f.OnOpen = function()
    G.Refresh()
end

UI.RegisterOpener("graphics", function(toggle)
    if toggle and f:IsShown() then
        f:Hide()
    else
        f:Show()
    end
end)

ns.AddCommand("graphics", "graphics settings (presets: /bh graphics off|classic|bleakhold|cinematic)", function(rest)
    local key = strlower(rest or "")
    if key ~= "" then
        if not G.Available() then
            ns.Print("this client has no Bleakhold graphics")
        elseif G.ApplyPreset(key) then
            ns.Print("graphics preset: " .. key)
        else
            ns.Print("unknown preset: " .. key)
        end
        return
    end
    UI.Open("graphics", true)
end)
