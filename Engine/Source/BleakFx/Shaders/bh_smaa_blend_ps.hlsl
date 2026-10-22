// SMAA pass 3: the frame (s0) blended with its neighbours by the weights (s1).
#include "bh_smaa_common.hlsli"

sampler2D s_color : register(s0);
sampler2D s_weights : register(s1);

float4 main(float2 uv : TEXCOORD0) : COLOR {
    float4 offset;
    SMAANeighborhoodBlendingVS(uv, offset);
    return SMAANeighborhoodBlendingPS(uv, offset, s_color, s_weights);
}
