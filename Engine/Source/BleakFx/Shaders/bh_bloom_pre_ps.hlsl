// Bloom, first step: the frame (gamma) to half size, linear light above a soft threshold in rgb, and the plain
// (unthresholded) luma in alpha, which the pyramid carries along as the blurred base for the clarity effect.
// 13-tap downsample with a Karis average against flicker from single bright pixels (Jimenez, "Next Generation Post
// Processing in Call of Duty: Advanced Warfare", 2014).
#include "bh_common.hlsli"

sampler2D s_scene : register(s0);
float4 g_threshold : register(c200); // x threshold (linear), y knee (0..1 of the threshold)

float3 Tap(float2 uv, float2 offset) {
    return ToLinear(Fetch(s_scene, uv + offset * g_texel0.xy).rgb);
}

float KarisWeight(float3 c) {
    return 1.0 / (1.0 + Luma(c));
}

float3 SoftThreshold(float3 c) {
    float brightness = max(c.r, max(c.g, c.b));
    float knee = g_threshold.x * g_threshold.y + 1e-4;
    float soft = clamp(brightness - g_threshold.x + knee, 0.0, 2.0 * knee);
    soft = soft * soft / (4.0 * knee);
    return c * (max(soft, brightness - g_threshold.x) / max(brightness, 1e-4));
}

float4 main(float2 uv : TEXCOORD0) : COLOR {
    float3 a = Tap(uv, float2(-2, -2)), b = Tap(uv, float2(0, -2)), c = Tap(uv, float2(2, -2));
    float3 d = Tap(uv, float2(-1, -1)), e = Tap(uv, float2(1, -1));
    float3 f = Tap(uv, float2(-2, 0)), g = Tap(uv, float2(0, 0)), h = Tap(uv, float2(2, 0));
    float3 i = Tap(uv, float2(-1, 1)), j = Tap(uv, float2(1, 1));
    float3 k = Tap(uv, float2(-2, 2)), l = Tap(uv, float2(0, 2)), m = Tap(uv, float2(2, 2));

    float3 box0 = (d + e + i + j) * 0.25;
    float3 box1 = (a + b + f + g) * 0.25;
    float3 box2 = (b + c + g + h) * 0.25;
    float3 box3 = (f + g + k + l) * 0.25;
    float3 box4 = (g + h + l + m) * 0.25;

    float w0 = KarisWeight(box0) * 0.5;
    float w1 = KarisWeight(box1) * 0.125;
    float w2 = KarisWeight(box2) * 0.125;
    float w3 = KarisWeight(box3) * 0.125;
    float w4 = KarisWeight(box4) * 0.125;
    float3 sum = (box0 * w0 + box1 * w1 + box2 * w2 + box3 * w3 + box4 * w4) / (w0 + w1 + w2 + w3 + w4);

    float3 average = box0 * 0.5 + (box1 + box2 + box3 + box4) * 0.125;
    return float4(BloomEncode(SoftThreshold(sum)), sqrt(saturate(Luma(average))));
}
