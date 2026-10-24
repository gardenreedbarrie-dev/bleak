// Light shafts, the streaks: a radial blur towards the sun (two passes with different lengths give smooth rays).
#include "bh_common.hlsli"

sampler2D s_mask : register(s0);
float4 g_sun : register(c200);   // xy sun position (uv)
float4 g_rays : register(c201);  // x length (0..1 of the way to the sun), y decay per sample

static const int kSamples = 16;

float4 main(float2 uv : TEXCOORD0) : COLOR {
    float2 step = (g_sun.xy - uv) * (g_rays.x / kSamples);
    float2 at = uv;
    float3 sum = 0.0;
    float weight = 1.0;
    float total = 0.0;

    [unroll]
    for (int i = 0; i < kSamples; i++) {
        sum += BloomDecode(Fetch(s_mask, at).rgb) * weight;
        total += weight;
        weight *= g_rays.y;
        at += step;
    }

    return float4(BloomEncode(sum / total), 1.0);
}
