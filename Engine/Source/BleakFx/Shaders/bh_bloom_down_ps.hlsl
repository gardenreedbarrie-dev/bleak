// Bloom, next levels: 13-tap downsample of the level above (Jimenez 2014).
#include "bh_common.hlsli"

sampler2D s_level : register(s0);

float4 Tap(float2 uv, float2 offset) {
    float4 c = Fetch(s_level, uv + offset * g_texel0.xy);
    return c * c;
}

float4 main(float2 uv : TEXCOORD0) : COLOR {
    float4 a = Tap(uv, float2(-2, -2)), b = Tap(uv, float2(0, -2)), c = Tap(uv, float2(2, -2));
    float4 d = Tap(uv, float2(-1, -1)), e = Tap(uv, float2(1, -1));
    float4 f = Tap(uv, float2(-2, 0)), g = Tap(uv, float2(0, 0)), h = Tap(uv, float2(2, 0));
    float4 i = Tap(uv, float2(-1, 1)), j = Tap(uv, float2(1, 1));
    float4 k = Tap(uv, float2(-2, 2)), l = Tap(uv, float2(0, 2)), m = Tap(uv, float2(2, 2));

    // Both the glow (rgb) and the clarity base (alpha) are stored as square roots.
    float4 sum = (d + e + i + j) * 0.125;
    sum += (a + c + k + m) * 0.03125;
    sum += (b + f + h + l) * 0.0625;
    sum += g * 0.125;

    return sqrt(saturate(sum));
}
