// Bloom, way back up: 9-tap tent filter of the smaller level, blended into this level's downsample.
#include "bh_common.hlsli"

sampler2D s_smaller : register(s0);
sampler2D s_level : register(s1);
float4 g_up : register(c200); // x tent radius (texels of the smaller level), y weight of the smaller level

float4 Tap(float2 uv, float2 offset) {
    float4 c = Fetch(s_smaller, uv + offset * g_texel0.xy * g_up.x);
    return c * c;
}

float4 main(float2 uv : TEXCOORD0) : COLOR {
    float4 sum = Tap(uv, float2(0, 0)) * 4.0;
    sum += (Tap(uv, float2(-1, 0)) + Tap(uv, float2(1, 0)) + Tap(uv, float2(0, -1)) + Tap(uv, float2(0, 1))) * 2.0;
    sum += Tap(uv, float2(-1, -1)) + Tap(uv, float2(1, -1)) + Tap(uv, float2(-1, 1)) + Tap(uv, float2(1, 1));
    sum *= 1.0 / 16.0;

    float4 level = Fetch(s_level, uv);
    level *= level;
    return sqrt(saturate((level + sum * g_up.y) / (1.0 + g_up.y)));
}
