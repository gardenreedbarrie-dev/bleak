// Water, before the transparent liquids: the depth buffer as view depth in yards (R32F) for the water's
// refraction, colour by depth and reflections. No world (horizon, sky, never drawn): far away.
#include "bh_common.hlsli"

sampler2D s_depth : register(s0);

float4 main(float2 uv : TEXCOORD0) : COLOR {
    float d = Fetch(s_depth, uv).r;
    float z = d >= g_sky.y ? 1.0e6 : LinearDepth(d);
    return float4(z, z, z, 1.0);
}
