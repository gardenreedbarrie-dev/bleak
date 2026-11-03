// Final look: clarity, bloom, colour grading, filmic contrast, vignette and dither. Output is gamma with the luma in alpha for
// FXAA. The frame is already display-referred (8-bit), so nothing here clips: bloom is added so that it saturates
// smoothly towards white, and the contrast curve keeps black and white where they are.
#include "bh_common.hlsli"

sampler2D s_scene : register(s0);
sampler2D s_bloom : register(s1);

float4 g_tone : register(c200);     // x bloom intensity, y contrast (0 = off), z saturation, w vibrance
float4 g_color : register(c201);    // x vignette amount, y dither (in 1/255 steps), z clarity, w contrast pivot
float4 g_lift : register(c202);     // rgb lift (raises the shadows, gamma space)
float4 g_gamma : register(c203);    // rgb gamma (>1 brightens the midtones)
float4 g_gain : register(c204);     // rgb gain (white balance and overall gain)

float4 main(float2 uv : TEXCOORD0, float2 pixel : VPOS) : COLOR {
    float3 c = ToLinear(Fetch(s_scene, uv).rgb);
    float4 pyramid = Fetch(s_bloom, uv);

    // Clarity: local contrast against the blurred luma of the pyramid, strongest in the midtones.
    float base = pyramid.a * pyramid.a;
    float luma0 = Luma(c);
    float ratio = clamp((luma0 + 0.02) / (base + 0.02), 0.5, 2.0);
    float midtones = saturate(4.0 * sqrt(luma0) * (1.0 - sqrt(luma0)));
    c *= lerp(1.0, pow(ratio, g_color.z), midtones);

    // Additive for faint glow, never past white: c + (1 - c) * (1 - e^(-b / (1 - c))).
    float3 bloom = BloomDecode(pyramid.rgb) * g_tone.x;
    float3 headroom = max(1.0 - c, 1e-4);
    c += headroom * (1.0 - exp(-bloom / headroom));

    float luma = Luma(c);
    float chroma = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
    float saturation = g_tone.z * (1.0 + g_tone.w * (1.0 - saturate(chroma * 2.0)));
    c = max(lerp(luma.xxx, c, saturation), 0.0);

    // Filmic S-curve through black, the pivot and white.
    float3 g = saturate(ToGamma(c));
    float pivot = g_color.w;
    float k = 1.0 + g_tone.y;
    float3 low = pivot * pow(max(g / pivot, 1e-6), k);
    float3 high = 1.0 - (1.0 - pivot) * pow(max((1.0 - g) / (1.0 - pivot), 1e-6), k);
    g = g < pivot ? low : high;
    g = g_gain.rgb * (g + g_lift.rgb * (1.0 - g));
    g = pow(saturate(g), 1.0 / g_gamma.rgb);

    float2 centred = (uv - 0.5) * float2(g_outTexel.z * g_outTexel.y, 1.0);
    float vignette = 1.0 - g_color.x * smoothstep(0.35, 1.1, dot(centred, centred) * 2.0);
    g *= vignette;

    g += (Ign(pixel) - 0.5) * g_color.y / 255.0;
    g = saturate(g);
    return float4(g, Luma(g));
}
