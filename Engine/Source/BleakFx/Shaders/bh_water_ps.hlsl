// BleakFx water, pixel shader: ripples from a code-made normal texture, refraction of the ground under the
// water, the zone's own water colours by real depth (the stock depth gradient), reflections traced in screen space
// with the sky as fallback, Fresnel, sun glints, foam at the shore and a soft shoreline, then the stock fog.
#include "bh_common.hlsli"

sampler2D s_depthGradient : register(s0);  // stock: water colour (rgb) and opacity (a), shallow (v = 0) to deep (v = 1)
sampler2D s_scene : register(s2);          // the frame before the transparent liquids
sampler2D s_sceneDepth : register(s3);     // its view depth in yards (R32F)
sampler2D s_ripples : register(s4);        // BleakFxRipples: normal (rgb), foam (a)

// Stock pixel constants (Liquid::PSConstants): c0-c3 model-view-projection, c4 fog colour, c5 camera position.
float4 g_fogColor : register(c4);

float4 g_water0 : register(c180);       // x time (s), y depth available, z refraction, w screen-space reflections
float4 g_sunView : register(c181);      // xyz towards the sun (view space), w strength (0 below the horizon)
float4 g_sunColor : register(c182);     // rgb sun colour (linear), w glint strength
float4 g_skyZenith : register(c183);    // rgb (linear)
float4 g_skyHorizon : register(c184);   // rgb (linear)
float4 g_sceneTexel : register(c185);   // 1/w, 1/h, w, h of the frame
float4 g_waterProj : register(c186);    // proj[0][0], proj[1][1]
float4 g_water1 : register(c187);       // x ripple strength, y foam, z yards to the deepest colour, w reflection
float4 g_upView : register(c188);       // world up in view space
float4 g_viewToWorld[3] : register(c189); // the view-space x, y and z axes in world space
float4 g_rippleA : register(c192);      // xy offset, z scale (per yard)
float4 g_rippleB : register(c193);      // xy offset, z scale (per yard)
float4 g_rippleRot : register(c194);    // rotation of layer B: cos, sin, -sin, cos
float4 g_fog : register(c195);          // stock fog: f = saturate(view z * x + y)

static const float kNoDepth = 1.0e6;

struct PSIn {
    float3 view : TEXCOORD0;
    float3 normal : TEXCOORD1;
    float3 tangent : TEXCOORD2;
    float3 bitangent : TEXCOORD3;
    float4 uv : TEXCOORD4;
    float4 color : TEXCOORD5;
    float2 pixel : VPOS;
};

float2 Project(float3 q) {
    return float2(q.x * g_waterProj.x / q.z * 0.5 + 0.5, 0.5 - q.y * g_waterProj.y / q.z * 0.5);
}

float SceneDepth(float2 uv) {
    return g_water0.y > 0.5 ? tex2Dlod(s_sceneDepth, float4(uv, 0.0, 0.0)).r : kNoDepth;
}

float3 SkyColor(float3 r) {
    float e = dot(r, g_upView.xyz);
    return lerp(g_skyHorizon.rgb, g_skyZenith.rgb, sqrt(saturate(e)));
}

// Marches the reflected ray through the depth buffer. rgb the colour where it hits, a how much to trust it.
// No break in the loop: fxc emits `break_ne x, x` for it, which a literal reading of the bytecode never takes.
float4 TraceReflection(float3 p, float3 r) {
    float t = 0.5;
    float previous = 0.0;
    float low = 0.0;
    float high = 0.0;
    bool searching = true;
    bool found = false;

    [loop]
    for (int k = 0; k < 22; k++) {
        [branch]
        if (searching) {
            float3 q = p + r * t;
            float2 uv = Project(q);
            bool outside = q.z < 0.5 || uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0;
            float behind = q.z - SceneDepth(saturate(uv));

            // Behind the surface, but not so far that the ray passed behind an object instead of into it.
            bool hit = !outside && behind > 0.0 && behind < max(t * 0.3, 1.0);
            found = found || hit;
            low = hit ? previous : low;
            high = hit ? t : high;
            searching = !outside && !hit;
            previous = t;
            t = t * 1.32 + 0.35;
        }
    }

    [branch]
    if (!found) {
        return float4(0.0, 0.0, 0.0, 0.0);
    }

    [unroll]
    for (int s = 0; s < 5; s++) {
        float mid = (low + high) * 0.5;
        float3 m = p + r * mid;
        bool inside = m.z - SceneDepth(saturate(Project(m))) > 0.0;
        high = inside ? mid : high;
        low = inside ? low : mid;
    }

    float2 uv = saturate(Project(p + r * high));
    float edge = saturate(min(min(uv.x, 1.0 - uv.x), min(uv.y, 1.0 - uv.y)) * 8.0);
    float fade = edge * saturate(1.5 - high / 160.0);
    return float4(ToLinear(tex2Dlod(s_scene, float4(uv, 0.0, 0.0)).rgb), fade);
}

float4 main(PSIn i) : COLOR {
    float3 p = i.view;
    float distance = length(p);
    float3 v = -p / distance;
    float3 up = normalize(i.normal);
    bool below = dot(v, up) < 0.0;
    up = below ? -up : up;

    // Ripples: two layers of the tile in world space, the second turned and at another scale, both drifting.
    float3 world = p.x * g_viewToWorld[0].xyz + p.y * g_viewToWorld[1].xyz + p.z * g_viewToWorld[2].xyz;
    float2 uvA = world.xy * g_rippleA.z + g_rippleA.xy;
    float2 turned = float2(dot(world.xy, g_rippleRot.xy), dot(world.xy, g_rippleRot.zw));
    float2 uvB = turned * g_rippleB.z + g_rippleB.xy;
    float4 rippleA = tex2D(s_ripples, uvA);
    float4 rippleB = tex2D(s_ripples, uvB);
    float3 nA = rippleA.xyz * 2.0 - 1.0;
    float3 nB = rippleB.xyz * 2.0 - 1.0;
    float strength = g_water1.x * saturate(1.3 - distance / 400.0);
    float2 slope = (nA.xy + nB.xy) * strength;
    float3 tangent = normalize(i.tangent);
    float3 bitangent = normalize(i.bitangent);
    float3 n = normalize(up + tangent * slope.x + bitangent * slope.y);

    float2 screen = (i.pixel + 0.5) * g_sceneTexel.xy;
    float cosView = abs(dot(v, up));

    // Water depth below this pixel, along the view ray and straight down.
    float behind = SceneDepth(screen);
    bool haveDepth = g_water0.y > 0.5;
    float pathLength = haveDepth ? max(behind - p.z, 0.0) * distance / p.z : i.uv.z * g_water1.z / max(cosView, 0.2);
    float vertical = pathLength * cosView;

    // Refraction: the ground seen through the ripples; never pulls in something that stands in front of the water.
    float2 offset = slope * g_water0.z * saturate(vertical * 0.6) / (1.0 + p.z * 0.03);
    float2 refractedUv = screen + offset;
    float refractedDepth = SceneDepth(refractedUv);
    if (refractedDepth < p.z) {
        refractedUv = screen;
        refractedDepth = behind;
    }
    float3 refracted = ToLinear(tex2Dlod(s_scene, float4(refractedUv, 0.0, 0.0)).rgb);
    if (haveDepth) {
        vertical = max(refractedDepth - p.z, 0.0) * distance / p.z * cosView;
    }

    // The zone's water colour and opacity for this depth (the stock depth gradient; interior water: its right half,
    // tinted by the vertex colour).
    float depthCoord = haveDepth ? saturate(vertical / g_water1.z) : saturate(i.uv.z);
    float4 gradient = tex2Dlod(s_depthGradient, float4(i.uv.w > 0.5 ? 0.75 : 0.25, depthCoord, 0.0, 0.0));
    float3 waterColor = ToLinear(gradient.rgb * i.color.rgb);
    float3 body = lerp(refracted, waterColor, gradient.a);

    // Reflection: what the ripples point at on the screen, else the sky.
    float3 r = reflect(-v, n);
    float3 reflection = SkyColor(r);
    if (g_water0.w > 0.5 && haveDepth && !below) {
        float4 hit = TraceReflection(p, r);
        reflection = lerp(reflection, hit.rgb, hit.a);
    }

    float cosN = saturate(dot(n, v));
    float fresnel = (0.02 + 0.98 * pow(1.0 - cosN, 5.0)) * g_water1.w;
    float3 color = lerp(body, reflection, below ? 0.0 : fresnel);

    // Sun glints (GGX).
    float3 l = g_sunView.xyz;
    float3 h = normalize(l + v);
    float nh = saturate(dot(n, h));
    float nl = saturate(dot(n, l));
    float a2 = 0.012;
    float d = nh * nh * (a2 - 1.0) + 1.0;
    float glint = a2 / (3.14159 * d * d) * nl * (0.02 + 0.98 * pow(1.0 - saturate(dot(h, v)), 5.0));
    color += g_sunColor.rgb * min(glint, 12.0) * g_sunColor.w * g_sunView.w * (below ? 0.0 : 1.0);

    // Foam where the water is shallow, broken up by the foam pattern of both ripple layers.
    float shore = haveDepth ? saturate(1.0 - vertical / 0.9) : 0.0;
    float foamPattern = saturate((rippleA.a + rippleB.a) * 1.4 + shore * 0.6 - 0.3);
    float foam = shore * shore * foamPattern * g_water1.y;
    float3 foamColor = waterColor * 0.3 + (g_sunColor.rgb * nl * g_sunView.w + g_skyZenith.rgb) * 0.6;
    color = lerp(color, foamColor, saturate(foam));

    // The stock fog (FFP fog does not apply to ps_3_0).
    float fog = saturate(p.z * g_fog.x + g_fog.y);
    color = lerp(ToLinear(g_fogColor.rgb), color, fog);

    // Soft shoreline: the water fades out over its last few inches.
    float alpha = haveDepth ? saturate(vertical * 5.0) : 1.0;
    return float4(ToGamma(color), alpha);
}
