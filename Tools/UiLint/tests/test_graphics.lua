-- Graphics window: the bleakFx* console variables of the Bleakhold client.
local DEFAULTS = {
    bleakFx = "1", bleakFxAA = "1", bleakFxAO = "0.6", bleakFxAORadius = "1.5", bleakFxSunShafts = "0.4",
    bleakFxBloom = "0.35", bleakFxBloomThreshold = "0.8", bleakFxClarity = "0.35", bleakFxContrast = "0.18",
    bleakFxSaturation = "1.05", bleakFxVibrance = "0.25", bleakFxWarmth = "0.3", bleakFxBrightness = "1",
    bleakFxShadows = "0.012", bleakFxVignette = "0.18", bleakFxSharpen = "0.25", gxMultisample = "1",
    bleakFxWater = "1", bleakFxWaterReflections = "1", bleakFxWaterRipples = "0.12",
}

-- Registers the client's variables with their defaults (Engine/Source/BleakFx/BleakFx.cpp).
local function bleakholdClient(M)
    for k, v in pairs(DEFAULTS) do
        M.cvars[k] = v
    end
end

local function sliderFor(G, cvar)
    for _, holder in ipairs(G.frame.sliders) do
        if holder.def.cvar == cvar then
            return holder
        end
    end
end

-- What the client does when a slider moves.
local function drag(M, holder, value)
    holder.slider:SetValue(value)
    M.Fire(holder.slider, "OnValueChanged", value)
end

test("graphics: every slider and preset names a client variable", function(M, ns)
    local G = ns.Graphics
    for _, t in ipairs(G.TOGGLES) do
        H.ok(DEFAULTS[t.cvar], "toggle variable " .. t.cvar)
    end
    for _, s in ipairs(G.SLIDERS) do
        H.ok(DEFAULTS[s.cvar], "slider variable " .. s.cvar)
        H.ok(s.min < s.max and s.step > 0, s.cvar .. " range")
        local d = tonumber(DEFAULTS[s.cvar])
        H.ok(d >= s.min and d <= s.max, s.cvar .. " default in range")
    end
    for _, p in ipairs(G.PRESETS) do
        for name, value in pairs(p.values) do
            H.ok(DEFAULTS[name], p.key .. ": " .. name)
            local s = sliderFor(G, name)
            if s then
                H.ok(value >= s.def.min and value <= s.def.max, p.key .. ": " .. name .. " in range")
                H.eq(G.Snap(s.def, value), value, p.key .. ": " .. name .. " on the slider's steps")
            end
        end
    end
end)

test("graphics: a stock client only gets the note", function(M, ns)
    local G = ns.Graphics
    H.ok(not G.Available(), "no bleakFx variable")
    ns.UI.Open("graphics")
    H.ok(G.frame:IsShown(), "window opens")
    H.contains(G.frame.note:GetText(), "no Bleakhold graphics")
    H.ok(not G.frame.sliders[1].slider:IsEnabled(), "sliders off")
    H.ok(not G.frame.preset.enabled, "preset off")
    M.said = {}
    M.env.SlashCmdList.BLEAKHOLD("graphics cinematic")
    H.eq(M.cvars.bleakFx, nil, "nothing set")
end)

test("graphics: defaults are the Bleakhold preset; presets and sliders set the variables", function(M, ns)
    bleakholdClient(M)
    local G = ns.Graphics
    ns.UI.Open("graphics")
    H.eq(G.CurrentPreset(), "bleakhold")
    H.eq(G.frame.preset.label:GetText(), "Bleakhold")
    H.eq(G.frame.note:GetText(), "")
    local ao = sliderFor(G, "bleakFxAO")
    H.eq(ao.slider:GetValue(), 0.6)
    H.eq(ao.value:GetText(), "0.6")
    H.eq(sliderFor(G, "bleakFxAORadius").value:GetText(), "1.5 yd")

    M.env.SlashCmdList.BLEAKHOLD("graphics cinematic")
    H.eq(M.cvars.bleakFxBloom, "0.6")
    H.eq(M.cvars.bleakFxAO, "0.85")
    H.eq(G.CurrentPreset(), "cinematic")
    H.eq(G.frame.preset.label:GetText(), "Cinematic")

    drag(M, sliderFor(G, "bleakFxBloom"), 0.7312)
    H.eq(M.cvars.bleakFxBloom, "0.75", "snapped to the step")
    H.eq(G.CurrentPreset(), "custom")
    H.eq(G.frame.preset.label:GetText(), "Custom")

    G.frame.preset:SetValue("classic")
    H.eq(M.cvars.bleakFxClarity, "0.2")
    H.eq(G.CurrentPreset(), "classic")

    G.frame.toggles[1]:Click()
    H.eq(M.cvars.bleakFxAA, "0")
    H.eq(G.frame.toggles[1].label:GetText(), "Anti-aliasing: off")
    G.frame.toggles[2]:Click()
    H.eq(M.cvars.bleakFxWater, "0")
    H.eq(G.frame.toggles[2].label:GetText(), "Modern water: off")
    H.eq(G.CurrentPreset(), "custom")
    G.frame.reset:Click()
    H.eq(G.CurrentPreset(), "bleakhold")
    H.eq(M.cvars.bleakFxAA, "1")
    H.eq(M.cvars.bleakFxWater, "1")
end)

test("graphics: off greys the sliders; multisampling note", function(M, ns)
    bleakholdClient(M)
    local G = ns.Graphics
    ns.UI.Open("graphics")
    G.frame.preset:SetValue("off")
    H.eq(M.cvars.bleakFx, "0")
    H.eq(G.CurrentPreset(), "off")
    H.ok(not G.frame.sliders[1].slider:IsEnabled(), "sliders off")
    H.eq(M.cvars.bleakFxAO, "0.6", "the other values stay for later")
    M.env.SlashCmdList.BLEAKHOLD("graphics bleakhold")
    H.eq(M.cvars.bleakFx, "1")
    H.ok(G.frame.sliders[1].slider:IsEnabled(), "sliders on")
    M.cvars.gxMultisample = "4"
    G.Refresh()
    H.contains(G.frame.note:GetText(), "multisampling off")
    ns.UI.Open("graphics", true)
    H.ok(not G.frame:IsShown(), "toggles closed")
end)
