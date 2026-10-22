// Ambient occlusion at half size from the depth buffer, after "Scalable Ambient Obscurance" (McGuire, Mara, Luebke,
// HPG 2012): samples on a spiral around the pixel, rotated per pixel, count how much nearby geometry rises above the
// surface's tangent plane. Normals come from the depth itself.
#include "bh_common.hlsli"

sampler2D s_depth : register(s0);
float4 g_ao : register(c200);    // x radius (yards), y intensity, z bias (per yard of view depth), w pixels per yard at depth 1
float4 g_fade : register(c201);  // x fade start (yards), y fade end

static const int kSamples = 12;
static const float kTurns = 7.0;

float3 PositionAt(float2 uv) {
    return ViewPosition(uv, LinearDepth(Fetch(s_depth, uv).r));
}

float4 main(float2 uv : TEXCOORD0, float2 pixel : VPOS) : COLOR {
    float depth = Fetch(s_depth, uv).r;

    [branch]
    if (depth >= g_sky.x) {
        return float4(1.0, 1.0, 1.0, 1.0);
    }

    float3 p = ViewPosition(uv, LinearDepth(depth));

    // Normal from the neighbours on the side with the smaller depth step, so edges do not smear.
    float2 t = g_texel0.xy;
    float3 right = PositionAt(uv + float2(t.x, 0.0)) - p;
    float3 left = p - PositionAt(uv - float2(t.x, 0.0));
    float3 down = PositionAt(uv + float2(0.0, t.y)) - p;
    float3 up = p - PositionAt(uv - float2(0.0, t.y));
    float3 dx = abs(right.z) < abs(left.z) ? right : left;
    float3 dy = abs(down.z) < abs(up.z) ? down : up;
    float3 n = normalize(cross(dy, dx));
    n = dot(n, p) > 0.0 ? -n : n;

    float radius = g_ao.x;
    float screenRadius = radius * g_ao.w / p.z;

    [branch]
    if (screenRadius < 1.0) {
        return float4(1.0, 1.0, 1.0, 1.0);
    }

    float angle0 = Ign(pixel) * 6.2831853;
    float bias = g_ao.z * p.z;
    float radius2 = radius * radius;
    float sum = 0.0;

    [unroll]
    for (int i = 0; i < kSamples; i++) {
        float alpha = (i + 0.5) / kSamples;
        float angle = alpha * kTurns * 6.2831853 + angle0;
        float2 offset = float2(cos(angle), sin(angle)) * (alpha * screenRadius) * t;
        float3 v = PositionAt(uv + offset) - p;
        float vv = dot(v, v);
        float vn = dot(v, n);
        float f = max(radius2 - vv, 0.0);
        sum += f * f * f * max((vn - bias) / (vv + 0.01), 0.0);
    }

    float ao = max(0.0, 1.0 - sum * g_ao.y * 5.0 / (radius2 * radius2 * radius2 * kSamples));
    ao = lerp(ao, 1.0, saturate((p.z - g_fade.x) / max(g_fade.y - g_fade.x, 1.0)));
    return float4(ao, ao, ao, 1.0);
}
