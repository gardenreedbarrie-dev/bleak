// Applies the depth effects to the frame: ambient occlusion and light shafts.
#include "bh_common.hlsli"

sampler2D s_scene : register(s0);
sampler2D s_ao : register(s1);
sampler2D s_rays : register(s2);
float4 g_fx : register(c200);       // x ambient occlusion strength, y light shaft strength
float4 g_sunColor : register(c201); // rgb colour of the light shafts (linear)

float4 main(float2 uv : TEXCOORD0) : COLOR {
    float3 c = ToLinear(Fetch(s_scene, uv).rgb);
    float ao = Fetch(s_ao, uv).r;
    c *= lerp(1.0, ao, g_fx.x);

    float3 rays = BloomDecode(Fetch(s_rays, uv).rgb) * g_sunColor.rgb * g_fx.y;
    float3 headroom = max(1.0 - c, 1e-4);
    c += headroom * (1.0 - exp(-rays / headroom));
    return float4(ToGamma(c), 1.0);
}
