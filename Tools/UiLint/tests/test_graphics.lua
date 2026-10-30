-- Graphics window: the bleakFx* console variables of the Bleakhold client.
local DEFAULTS = {
    bleakFx = "1", bleakFxAA = "2", bleakFxAO = "0.6", bleakFxAORadius = "1.5", bleakFxSunShafts = "0.4",
    bleakFxBloom = "0.35", bleakFxBloomThreshold = "0.8", bleakFxClarity = "0.35", bleakFxContrast = "0.18",
    bleakFxSaturation = "1.05", bleakFxVibrance = "0.25", bleakFxWarmth = "0.3", bleakFxBrightness = "1",
    bleakFxShadows = "0.012", bleakFxVignette = "0.18", bleakFxSharpen = "0.25", gxMultisample = "1",
    bleakFxWater = "1", bleakFxWaterReflections = "1", bleakFxWaterRipples = "0.12",
    bleakFxGrassWind = "1", bleakFxGrassParting = "1", bleakFxContactShadows = "0.6",
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
    H.ok(not G.frame.toggles[1].enabled and not G.frame.toggles[2]:IsEnabled(), "anti-aliasing and the checks off")
    H.eq(G.frame.general:GetHeight(), 88 + 32, "the General box holds the note's row")
    H.eq(G.frame:GetHeight(), 672 + 32, "and the window grows with it")
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
    H.eq(G.frame.general:GetHeight(), 88, "no note: the General box is its two rows")
    H.eq(G.frame:GetHeight(), 672)
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

    -- anti-aliasing: a dropdown (a list row calls SetValue); the on/off variables: check buttons
    local aa, water, parting = G.frame.toggles[1], G.frame.toggles[2], G.frame.toggles[4]
    H.eq(aa.label:GetText(), "FXAA", "Classic+ uses FXAA")
    aa:SetValue(2)
    H.eq(M.cvars.bleakFxAA, "2")
    H.eq(aa.label:GetText(), "SMAA")
    aa:SetValue(0)
    H.eq(M.cvars.bleakFxAA, "0")
    H.eq(aa.label:GetText(), "Off")
    aa:SetValue(1)
    M.cvars.bleakFxAA = "7"
    G.Refresh()
    H.eq(aa.label:GetText(), "Off", "an unknown value reads as the first state")
    H.ok(water:GetChecked(), "Modern water is on")
    water:Click()
    H.eq(M.cvars.bleakFxWater, "0")
    H.ok(not water:GetChecked(), "and its check clears")
    M.cvars.bleakFxWater = "2"
    G.Refresh()
    H.ok(water:GetChecked(), "any value but 0 is on")
    water:Click()
    H.eq(M.cvars.bleakFxWater, "0")
    parting:Click()
    H.eq(M.cvars.bleakFxGrassParting, "0")
    H.ok(not parting:GetChecked())
    drag(M, sliderFor(G, "bleakFxGrassWind"), 1.66)
    H.eq(M.cvars.bleakFxGrassWind, "1.7", "snapped to the step")
    H.eq(G.CurrentPreset(), "custom")
    G.frame.reset:Click()
    H.eq(G.CurrentPreset(), "bleakhold")
    H.eq(M.cvars.bleakFxAA, "2")
    H.eq(M.cvars.bleakFxWater, "1")
    H.eq(M.cvars.bleakFxGrassWind, "1")
    H.eq(M.cvars.bleakFxGrassParting, "1")
end)

test("graphics: off greys the sliders; multisampling note", function(M, ns)
    bleakholdClient(M)
    local G = ns.Graphics
    ns.UI.Open("graphics")
    G.frame.preset:SetValue("off")
    H.eq(M.cvars.bleakFx, "0")
    H.eq(G.CurrentPreset(), "off")
    H.ok(not G.frame.sliders[1].slider:IsEnabled(), "sliders off")
    H.ok(not G.frame.toggles[3]:IsEnabled(), "the checks off")
    H.ok(G.frame.toggles[3]:GetDisabledCheckedTexture():IsShown(), "a checked one shows the greyed check")
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

test("graphics: the on/off variables are stock check buttons beside the lists, as the Video options", function(M, ns)
    bleakholdClient(M)
    local G = ns.Graphics
    ns.UI.Open("graphics")
    local aa = G.frame.toggles[1]
    H.eq(aa.title:GetText(), "Anti-aliasing")
    local _, rel = aa.title:GetPoint(1)
    H.eq(rel, G.frame.preset, "right of the preset")
    for i = 2, 4 do
        local b = G.frame.toggles[i]
        H.eq(b:GetObjectType(), "CheckButton", G.TOGGLES[i].label)
        H.eq(b:GetWidth(), 24)
        H.eq(b:GetNormalTexture():GetTexture(), "Interface\\Buttons\\UI-CheckBox-Up")
        H.eq(b:GetPushedTexture():GetTexture(), "Interface\\Buttons\\UI-CheckBox-Down")
        H.eq(b:GetHighlightTexture():GetTexture(), "Interface\\Buttons\\UI-CheckBox-Highlight")
        H.eq(b:GetHighlightTexture():GetBlendMode(), "ADD")
        H.eq(b:GetCheckedTexture():GetTexture(), "Interface\\Buttons\\UI-CheckBox-Check")
        H.eq(b.label:GetText(), G.TOGGLES[i].label)
        local r, g, bl = b.label:GetTextColor()
        H.ok(r == 1 and math.abs(g - 0.82) < 0.01 and bl == 0, "a gold label")
        H.eq(select(5, b:GetPoint(1)), -50, "all on one row")
    end
end)

test("graphics: Glowing marks switches bleakGlow, on its own beside the other checks", function(M, ns)
    local G = ns.Graphics
    ns.UI.Open("graphics")
    local glow = G.frame.glow
    H.eq(glow:GetObjectType(), "CheckButton")
    H.eq(glow.label:GetText(), "Glowing marks")
    H.eq(select(5, glow:GetPoint(1)), -50, "on the row of the checks")
    H.ok(not glow:IsEnabled(), "a client without bleakGlow: off")
    glow:Click()
    H.eq(M.cvars.bleakGlow, nil, "nothing set")
    -- the exe registers bleakGlow (default on); the post-processing switch does not touch it
    bleakholdClient(M)
    M.cvars.bleakGlow = "1"
    G.Refresh()
    H.ok(glow:IsEnabled() and glow:GetChecked(), "on")
    glow:Click()
    H.eq(M.cvars.bleakGlow, "0")
    H.ok(not glow:GetChecked(), "and its check clears")
    G.frame.preset:SetValue("off")
    H.ok(glow:IsEnabled(), "Off (stock look) leaves the glow switch alone")
    H.eq(M.cvars.bleakGlow, "0", "and its value")
    glow:Click()
    H.eq(M.cvars.bleakGlow, "1")
    for _, p in ipairs(G.PRESETS) do
        H.eq(p.values.bleakGlow, nil, p.key .. " does not set the glow")
    end
    -- four checks fit in the General box
    local last = glow.label:GetStringWidth() + 24 + 2 + 12 + 3 * 148
    H.ok(last <= G.frame.general:GetWidth(), "the glow check fits: " .. last .. " of " .. G.frame.general:GetWidth())
end)
