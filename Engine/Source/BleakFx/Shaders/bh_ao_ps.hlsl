// Ambient occlusion and contact shadows at half size from the depth buffer.
// Ambient occlusion after "Scalable Ambient Obscurance" (McGuire, Mara, Luebke, HPG 2012): samples on a spiral around
// the pixel, rotated per pixel, count how much nearby geometry rises above the surface's tangent plane. Contact
// shadows: a short ray towards the sun, marched through the depth buffer; geometry in front of the ray within a
// thickness casts a shadow. Normals come from the depth itself. Output: red the occlusion, green the sunlight (1 lit).
#include "bh_common.hlsli"

sampler2D s_depth : register(s0);
float4 g_ao : register(c200);     // x radius (yards), y intensity, z bias (per yard of view depth), w pixels per yard at depth 1
float4 g_fade : register(c201);   // x fade start (yards), y fade end
float4 g_sun : register(c202);    // xyz towards the sun (view space), w 1: contact shadows on
float4 g_shadow : register(c203); // x ray length (yards), y thickness (yards), z thickness per yard of view depth, w fade end (yards)

static const int kSamples = 12;
static const float kTurns = 7.0;
static const int kSteps = 16;

float3 PositionAt(float2 uv) {
    return ViewPosition(uv, LinearDepth(Fetch(s_depth, uv).r));
}

float2 ScreenUv(float3 q) {
    return float2(q.x / (q.z * g_proj.x) * 0.5 + 0.5, 0.5 - q.y / (q.z * g_proj.y) * 0.5);
}

float Occlusion(float3 p, float3 n, float2 uv, float2 pixel) {
    float radius = g_ao.x;
    float screenRadius = radius * g_ao.w / p.z;
    float2 t = g_texel0.xy;
    float angle0 = Ign(pixel) * 6.2831853;
    float bias = g_ao.z * p.z;
    float radius2 = radius * radius;
    float sum = 0.0;

    [loop]
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
    ao = screenRadius < 1.0 ? 1.0 : ao;

    // Surfaces seen edge-on (distant ground) have too little depth precision: their occlusion fades out.
    ao = lerp(1.0, ao, saturate(-dot(n, p) / length(p) * 5.0));
    return lerp(ao, 1.0, saturate((p.z - g_fade.x) / max(g_fade.y - g_fade.x, 1.0)));
}

float Sunlight(float3 p, float3 n, float2 pixel) {
    float3 l = g_sun.xyz;

    // Lifted off the surface so the ray does not hit its own pixel; jittered along the ray against banding.
    float3 start = p + n * (0.03 + 0.004 * p.z);
    float jitter = Ign(pixel + float2(37.0, 11.0));
    float thickness = g_shadow.y + g_shadow.z * p.z;
    float shadow = 0.0;

    [loop]
    for (int i = 0; i < kSteps; i++) {
        float t = (i + jitter) / kSteps;
        t *= t;
        float3 q = start + l * (t * g_shadow.x);
        float2 quv = ScreenUv(q);
        float inside = all(quv == saturate(quv)) && q.z > 0.5 ? 1.0 : 0.0;
        float behind = q.z - LinearDepth(Fetch(s_depth, quv).r);
        float hit = behind > 0.0 && behind < thickness ? inside : 0.0;
        shadow = max(shadow, hit * (1.0 - t * t));
    }

    // Surfaces facing away from the sun are shaded by the stock lighting already; surfaces seen edge-on and far away
    // ones have too little depth precision for the rays.
    shadow *= saturate(dot(n, l) * 4.0);
    shadow *= saturate(-dot(n, p) / length(p) * 5.0);
    shadow *= saturate(1.0 - p.z / g_shadow.w);
    return 1.0 - shadow;
}

float4 main(float2 uv : TEXCOORD0, float2 pixel : VPOS) : COLOR {
    // This target is half the depth buffer's size, so its pixel centres fall on the depth buffer's texel edges, where
    // point sampling may pick either texel; the centre of one texel keeps the neighbours below distinct.
    uv = (floor(uv * g_texel0.zw) + 0.5) * g_texel0.xy;
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

    float ao = 1.0;
    float sun = 1.0;

    [branch]
    if (g_ao.y > 0.0) {
        ao = Occlusion(p, n, uv, pixel);
    }

    [branch]
    if (g_sun.w > 0.0) {
        sun = Sunlight(p, n, pixel);
    }

    return float4(ao, sun, 1.0, 1.0);
}
