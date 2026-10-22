// Contrast-adaptive sharpening, after AMD FidelityFX CAS (MIT): sharpens less where the local contrast is already
// high, so edges do not ring and noise is not boosted.
#include "bh_common.hlsli"

sampler2D s_color : register(s0);
float4 g_cas : register(c200); // x sharpness 0..1

float3 Tap(float2 uv, float2 offset) {
    return Fetch(s_color, uv + offset * g_texel0.xy).rgb;
}

float4 main(float2 uv : TEXCOORD0) : COLOR {
    float3 a = Tap(uv, float2(-1, -1)), b = Tap(uv, float2(0, -1)), c = Tap(uv, float2(1, -1));
    float3 d = Tap(uv, float2(-1, 0)), e = Tap(uv, float2(0, 0)), f = Tap(uv, float2(1, 0));
    float3 g = Tap(uv, float2(-1, 1)), h = Tap(uv, float2(0, 1)), i = Tap(uv, float2(1, 1));

    // Soft min and max: the cross plus the whole 3x3.
    float3 minRgb = min(min(min(d, e), min(f, b)), h);
    minRgb += min(minRgb, min(min(a, c), min(g, i)));
    float3 maxRgb = max(max(max(d, e), max(f, b)), h);
    maxRgb += max(maxRgb, max(max(a, c), max(g, i)));

    float3 amp = saturate(min(minRgb, 2.0 - maxRgb) / max(maxRgb, 1e-4));
    amp = sqrt(amp);
    float peak = -1.0 / lerp(8.0, 5.0, saturate(g_cas.x));
    float3 w = amp * peak;
    float3 result = ((b + d + f + h) * w + e) / (1.0 + 4.0 * w);
    return float4(saturate(result), 1.0);
}
