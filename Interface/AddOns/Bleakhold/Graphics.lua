-- Bleakhold: graphics settings. The Bleakhold client draws the world through its own post-processing
-- (Engine/Source/BleakFx: ambient occlusion, light shafts, bloom, clarity, colour grading, FXAA, sharpening);
-- this window sets its bleakFx* console variables, with presets. The client saves them in Config.wtf. A stock
-- client has none of these variables: the window then only says so.
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
}

-- Presets set every slider plus the master switch and anti-aliasing. "bleakhold" is the client default.
G.PRESETS = {
    { key = "off", text = "Off (stock look)", values = { bleakFx = 0 } },
    { key = "classic", text = "Classic+", values = {
        bleakFx = 1, bleakFxAA = 1, bleakFxAO = 0.4, bleakFxAORadius = 1.25, bleakFxSunShafts = 0.25, bleakFxBloom = 0.2,
        bleakFxClarity = 0.2, bleakFxContrast = 0.08, bleakFxSaturation = 1, bleakFxVibrance = 0.1, bleakFxWarmth = 0.1,
        bleakFxBrightness = 1, bleakFxShadows = 0, bleakFxVignette = 0.08, bleakFxSharpen = 0.2 } },
    { key = "bleakhold", text = "Bleakhold", values = {
        bleakFx = 1, bleakFxAA = 1, bleakFxAO = 0.6, bleakFxAORadius = 1.5, bleakFxSunShafts = 0.4, bleakFxBloom = 0.35,
        bleakFxClarity = 0.35, bleakFxContrast = 0.18, bleakFxSaturation = 1.05, bleakFxVibrance = 0.25, bleakFxWarmth = 0.3,
        bleakFxBrightness = 1, bleakFxShadows = 0.012, bleakFxVignette = 0.18, bleakFxSharpen = 0.25 } },
    { key = "cinematic", text = "Cinematic", values = {
        bleakFx = 1, bleakFxAA = 1, bleakFxAO = 0.85, bleakFxAORadius = 2, bleakFxSunShafts = 0.7, bleakFxBloom = 0.6,
        bleakFxClarity = 0.45, bleakFxContrast = 0.3, bleakFxSaturation = 1.1, bleakFxVibrance = 0.35, bleakFxWarmth = 0.4,
        bleakFxBrightness = 1, bleakFxShadows = 0.02, bleakFxVignette = 0.3, bleakFxSharpen = 0.35 } },
}

-- Whether this client has the Bleakhold graphics (registered variables are the only ones GetCVar finds).
function G.Available()
    return GetCVar ~= nil and GetCVar("bleakFx") ~= nil
end

local function cvarNumber(name, default)
    local v = G.Available() and tonumber(GetCVar(name)) or nil
    return v or default
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
local W, H = 640, 560
local f = UI.Window("BleakholdGraphics", W, H, "Graphics", "star")
f:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
G.frame = f
local content = f.content
local syncing = false

local presetLabel = UI.Text(content, 12, C.mute)
presetLabel:SetPoint("TOPLEFT", content, "TOPLEFT", 20, -18)
presetLabel:SetText("PRESET")
f.preset = UI.Dropdown(content, 190, function(value)
    if not syncing and value ~= "custom" then
        G.ApplyPreset(value)
    end
end)
f.preset:SetPoint("LEFT", presetLabel, "RIGHT", 10, 0)

f.aa = UI.Button(content, 150, 26, "", "dark", 12)
f.aa:SetPoint("LEFT", f.preset, "RIGHT", 12, 0)
f.aa:SetScript("OnClick", function()
    G.Set("bleakFxAA", cvarNumber("bleakFxAA", 1) == 1 and 0 or 1)
    G.Refresh()
end)
f.aa.tooltip = function()
    return { "Anti-aliasing (FXAA)", "Smooths jagged edges after the world is drawn. Works with multisampling off." }
end

f.reset = UI.Button(content, 110, 26, "Defaults", "ghost", 12)
f.reset:SetPoint("TOPRIGHT", content, "TOPRIGHT", -20, -12)
f.reset:SetScript("OnClick", function()
    G.ApplyPreset("bleakhold")
end)

f.note = UI.Text(content, 12, C.orange, "body", "LEFT")
f.note:SetPoint("TOPLEFT", content, "TOPLEFT", 20, -50)
f.note:SetPoint("TOPRIGHT", content, "TOPRIGHT", -20, -50)
f.note:SetHeight(32)

f.sliders = {}
local COLS, COL_W, ROW_H = 2, 280, 52
for i, s in ipairs(G.SLIDERS) do
    local col, row = (i - 1) % COLS, floor((i - 1) / COLS)
    local holder = CreateFrame("Frame", nil, content)
    holder:SetSize(COL_W, ROW_H)
    holder:SetPoint("TOPLEFT", content, "TOPLEFT", 20 + col * (COL_W + 40), -92 - row * ROW_H)
    holder.label = UI.Text(holder, 12, C.mid)
    holder.label:SetPoint("TOPLEFT", holder, "TOPLEFT", 0, 0)
    holder.label:SetText(s.label)
    holder.value = UI.Text(holder, 12, C.goldLight, "body", "RIGHT")
    holder.value:SetPoint("TOPRIGHT", holder, "TOPRIGHT", 0, 0)

    local slider = CreateFrame("Slider", nil, holder)
    slider:SetOrientation("HORIZONTAL")
    slider:SetSize(COL_W, 16)
    slider:SetPoint("TOPLEFT", holder, "TOPLEFT", 0, -20)
    slider:SetMinMaxValues(s.min, s.max)
    slider:SetValueStep(s.step)
    slider:EnableMouse(true)
    local track = UI.Solid(slider, C.track, "BACKGROUND")
    track:SetPoint("LEFT", slider, "LEFT", 0, 0)
    track:SetPoint("RIGHT", slider, "RIGHT", 0, 0)
    track:SetHeight(4)
    local thumb = UI.Solid(slider, C.gold, "OVERLAY")
    thumb:SetSize(10, 16)
    slider:SetThumbTexture(thumb)
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
    f.aa:SetActive(on)
    f.aa:SetLabel(cvarNumber("bleakFxAA", 1) == 1 and "Anti-aliasing: on" or "Anti-aliasing: off")
    if not available then
        f.note:SetText("This client has no Bleakhold graphics. Install the Bleakhold client to use them.")
    elseif on and (tonumber(GetCVar("gxMultisample") or "1") or 1) > 1 then
        f.note:SetText("Ambient occlusion and light shafts need multisampling off: Video options, Multisampling 1x. "
            .. "Anti-aliasing here replaces it.")
    else
        f.note:SetText("")
    end
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
