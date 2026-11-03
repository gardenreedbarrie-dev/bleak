// SMAA pass 2: the blending weights from the edges (s0), the area texture (s1) and the search texture (s2).
#include "bh_smaa_common.hlsli"

sampler2D s_edges : register(s0);
sampler2D s_area : register(s1);
sampler2D s_search : register(s2);

float4 main(float2 uv : TEXCOORD0) : COLOR {
    float2 pixel;
    float4 offset[3];
    SMAABlendingWeightCalculationVS(uv, pixel, offset);
    return SMAABlendingWeightCalculationPS(uv, pixel, offset, s_edges, s_area, s_search, float4(0.0, 0.0, 0.0, 0.0));
}
