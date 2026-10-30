// SMAA pass 1: the luma edges of the frame (s0) in red and green. Pixels without an edge are discarded, so the
// target is cleared first (bh_clear_ps).
#include "bh_smaa_common.hlsli"

sampler2D s_color : register(s0);

float4 main(float2 uv : TEXCOORD0) : COLOR {
    float4 offset[3];
    SMAAEdgeDetectionVS(uv, offset);
    return float4(SMAALumaEdgeDetectionPS(uv, offset, s_color), 0.0, 0.0);
}
