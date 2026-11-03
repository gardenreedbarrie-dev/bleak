// BleakFx storm wall, pixel shader: a translucent purple curtain on the edge of the Bleakhold Royale storm, of slow
// billows and drifting cloud with long streaks rising through them, brighter at its foot and where it meets the
// ground, fading out at the top and close to the camera, partly fogged so that it stays readable far off; or the next
// circle's ring, a pale band on the ground. Alpha-blended over the world after the liquids, never writing depth.
#include "bh_common.hlsli"

sampler2D s_noise : register(s0);   // BleakFxStormNoise: r billows, g cloud, b grain, a ridges
sampler2D s_depth : register(s1);   // the frame's view depth in yards (R32F, bh_depthcopy_ps) when g_storm.y is 1

float4 g_scroll : register(c205);       // noise offsets: x the billows (up), yz the cloud (across, up), w the streaks
float4 g_storm : register(c206);        // x moving (0 - 1), y the depth copy is there, z strength, w 0 wall, 1 ring
float4 g_stormFog : register(c207);     // rgb the fog colour, w the view depth where the fog starts
float4 g_stormScreen : register(c208);  // x 1 / (fog end - fog start), y the view depth the pass draws from (the
                                        // horizon's: the world's far plane), zw 1 / the size of the depth copy

static const float3 kDeep = float3(0.357, 0.165, 0.525);    // #5B2A86
static const float3 kGlow = float3(0.710, 0.494, 0.863);    // #B57EDC, the Bleakhold purple
static const float3 kVein = float3(0.788, 0.635, 0.961);    // #C9A2F5
static const float3 kRing = float3(0.902, 0.851, 1.0);      // #E6D9FF
static const float kSink = 24.0;        // BleakStorm::kSinkYards
static const float kRingSink = 4.0;     // BleakStorm::kRingSinkYards

struct PSIn {
    float3 noise : TEXCOORD0;
    float4 shape : TEXCOORD1;
    float2 weights : TEXCOORD2;
    float2 pixel : VPOS;
};

// The noise on the wall: its projections onto the y-z and x-z planes, weighted by the wall's direction, with the
// contrast the blend takes away put back. scale: noise tiles per tile of the world position, across and up.
float4 WallNoise(float3 p, float2 w, float2 scale, float2 offset) {
    float4 a = tex2D(s_noise, p.yz * scale + offset);
    float4 b = tex2D(s_noise, p.xz * scale + offset);
    float4 n = a * w.x + b * w.y;
    return saturate(0.5 + (n - 0.5) * rsqrt(max(dot(w, w), 0.25)));
}

float4 main(PSIn i) : COLOR {
    float above = i.shape.x;
    float below = i.shape.y;
    float z = i.shape.z;
    float ring = g_storm.w;

    // Big billows rise slowly, the cloud drifts across and up, the streaks (stretched upwards) rise fast. The
    // scales go with the offsets BleakFx::RenderStorm sets.
    float4 billows = WallNoise(i.noise, i.weights, float2(0.35, 0.25), float2(0.0, g_scroll.x));
    float4 cloud = WallNoise(i.noise, i.weights, float2(0.9, 0.8), g_scroll.yz);
    float4 streaks = WallNoise(i.noise, i.weights, float2(2.2, 0.12), float2(0.0, g_scroll.w));

    // The wall: purple cloud lit from within, with faint threads of light.
    float body = saturate(billows.r * 0.6 + cloud.g * 0.4 + streaks.b * 0.35 - 0.2);
    float vein = smoothstep(0.7, 0.95, cloud.a) * streaks.r * 0.4;
    float3 color = lerp(kDeep, kGlow, body);
    color = lerp(color, kVein, vein * 0.6);
    float rise = saturate(1.0 - max(above, 0.0) / 200.0);
    float alpha = (0.4 + 0.35 * body + 0.2 * vein) * (0.7 + 0.3 * rise);

    // Brighter at its foot, softly into the ground (where the depth test hides most of what is below it), gone at
    // the top.
    float foot = exp2(-max(above, 0.0) * 0.07);
    color = lerp(color, kGlow * 1.2, foot * 0.55);
    alpha += foot * 0.22;
    alpha *= smoothstep(-kSink, 0.0, above) * smoothstep(0.0, 140.0, below);

    // The ring: strongest on the ground, gone at its top, shimmering a little.
    float up = saturate(above / max(above + below, 0.01));
    float ringAlpha = 0.6 * (1.0 - up) * (1.0 - up) * smoothstep(-kRingSink, 0.0, above) * (0.7 + 0.3 * cloud.g);
    color = lerp(color, kRing, ring);
    alpha = lerp(alpha, ringAlpha, ring);

    // While the storm moves it glows a little more.
    color *= 1.0 + 0.18 * g_storm.x;
    alpha *= 1.0 + 0.12 * g_storm.x;

    // Denser seen edge-on (more of the curtain in the line of sight); see-through close to the camera, so that
    // standing in it does not fill the screen.
    alpha *= lerp(1.6, 1.0, saturate(i.shape.w));
    alpha *= saturate((z - 1.0) / 6.0);

    // With the depth copy: a bright seam where the wall meets the ground or anything else, and a soft last half
    // yard in place of a hard line.
    float scene = tex2Dlod(s_depth, float4((i.pixel + 0.5) * g_stormScreen.zw, 0.0, 0.0)).r;
    float gap = g_storm.y > 0.5 ? max(scene - z, 0.0) : 1000.0;
    float seam = exp2(-gap * 1.5);
    color = lerp(color, kVein * 1.25, seam * 0.7 * (1.0 - ring));
    alpha = (alpha + seam * 0.3) * saturate(gap * 2.0);

    // Partly fogged: far off the wall takes on the fog's colour but stays visible.
    float fog = saturate((z - g_stormFog.w) * g_stormScreen.x);
    color = lerp(color, g_stormFog.rgb, fog * 0.55);
    alpha *= 1.0 - 0.45 * fog;

    // The horizon's pass begins before the world's far plane: the world's pass has drawn what is nearer.
    clip(z - g_stormScreen.y);
    return float4(saturate(color), min(saturate(alpha), 0.85) * g_storm.z);
}
