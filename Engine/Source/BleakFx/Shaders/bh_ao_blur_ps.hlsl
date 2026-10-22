// Edge-aware blur of the ambient occlusion, one direction per pass: a Gaussian whose taps lose their weight where
// the depth jumps, so the occlusion of a wall does not bleed onto the character in front of it.
#include "bh_common.hlsli"

sampler2D s_ao : register(s0);
sampler2D s_depth : register(s1);
float4 g_blur : register(c200); // xy step in uv (one texel of the AO target along the blur direction), z depth tolerance

static const float kWeights[5] = { 0.2270270, 0.1945946, 0.1216216, 0.0540541, 0.0162162 };

float4 main(float2 uv : TEXCOORD0) : COLOR {
    float z = LinearDepth(Fetch(s_depth, uv).r);
    float sum = Fetch(s_ao, uv).r * kWeights[0];
    float weight = kWeights[0];

    [unroll]
    for (int i = 1; i < 5; i++) {
        float2 offset = g_blur.xy * i;
        float zA = LinearDepth(Fetch(s_depth, uv + offset).r);
        float zB = LinearDepth(Fetch(s_depth, uv - offset).r);
        float wA = kWeights[i] * saturate(1.0 - abs(zA - z) / (z * g_blur.z));
        float wB = kWeights[i] * saturate(1.0 - abs(zB - z) / (z * g_blur.z));
        sum += Fetch(s_ao, uv + offset).r * wA + Fetch(s_ao, uv - offset).r * wB;
        weight += wA + wB;
    }

    float ao = sum / weight;
    return float4(ao, ao, ao, 1.0);
}
