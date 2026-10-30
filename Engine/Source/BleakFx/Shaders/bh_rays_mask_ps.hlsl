// Light shafts, first step (quarter size): the bright sky around the sun, where the depth buffer shows open sky.
#include "bh_common.hlsli"

sampler2D s_scene : register(s0);
sampler2D s_depth : register(s1);
float4 g_sun : register(c200); // xy sun position (uv), z strength (0 = sun not visible), w size of the glow (uv)

float4 main(float2 uv : TEXCOORD0) : COLOR {
    // Four depth taps per quarter-size pixel: thin branches still let light through in part.
    float2 t = g_texel1.xy;
    float sky = 0.0;
    sky += Fetch(s_depth, uv + float2(-t.x, -t.y)).r >= g_sky.x ? 0.25 : 0.0;
    sky += Fetch(s_depth, uv + float2(t.x, -t.y)).r >= g_sky.x ? 0.25 : 0.0;
    sky += Fetch(s_depth, uv + float2(-t.x, t.y)).r >= g_sky.x ? 0.25 : 0.0;
    sky += Fetch(s_depth, uv + float2(t.x, t.y)).r >= g_sky.x ? 0.25 : 0.0;

    float2 toSun = (uv - g_sun.xy) * float2(g_outTexel.z * g_outTexel.y, 1.0);
    float glow = exp(-dot(toSun, toSun) / (g_sun.w * g_sun.w));
    float3 c = ToLinear(Fetch(s_scene, uv).rgb);
    float bright = saturate((Luma(c) - 0.35) * 2.0);
    return float4(BloomEncode(c * sky * glow * bright * g_sun.z), 1.0);
}
