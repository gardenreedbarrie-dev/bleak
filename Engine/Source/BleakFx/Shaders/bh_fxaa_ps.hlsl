// FXAA, after the algorithm of FXAA 3.11 "quality" by Timothy Lottes (NVIDIA): finds the local edge direction from
// luma, walks along the edge to both ends and blends across it by the distance to the nearer end.
// Input: gamma colour with luma in alpha, linear filtering.
#include "bh_common.hlsli"

sampler2D s_color : register(s0);
float4 g_fxaa : register(c200); // x subpixel amount, y edge threshold, z edge threshold minimum

float LumaAt(float2 uv) {
    return Fetch(s_color, uv).a;
}

float4 main(float2 uv : TEXCOORD0) : COLOR {
    float2 rcp = g_texel0.xy;
    float4 rgbyM = Fetch(s_color, uv);
    float lumaM = rgbyM.a;
    float lumaS = LumaAt(uv + float2(0.0, rcp.y));
    float lumaE = LumaAt(uv + float2(rcp.x, 0.0));
    float lumaN = LumaAt(uv - float2(0.0, rcp.y));
    float lumaW = LumaAt(uv - float2(rcp.x, 0.0));

    float rangeMax = max(max(lumaN, lumaW), max(lumaE, max(lumaS, lumaM)));
    float rangeMin = min(min(lumaN, lumaW), min(lumaE, min(lumaS, lumaM)));
    float range = rangeMax - rangeMin;

    [branch]
    if (range < max(g_fxaa.z, rangeMax * g_fxaa.y)) {
        return rgbyM;
    }

    float lumaNW = LumaAt(uv - rcp);
    float lumaSE = LumaAt(uv + rcp);
    float lumaNE = LumaAt(uv + float2(rcp.x, -rcp.y));
    float lumaSW = LumaAt(uv + float2(-rcp.x, rcp.y));

    // Is the edge horizontal or vertical?
    float edgeHorz = abs(lumaNW - 2.0 * lumaW + lumaSW) + 2.0 * abs(lumaN - 2.0 * lumaM + lumaS) + abs(lumaNE - 2.0 * lumaE + lumaSE);
    float edgeVert = abs(lumaNW - 2.0 * lumaN + lumaNE) + 2.0 * abs(lumaW - 2.0 * lumaM + lumaE) + abs(lumaSW - 2.0 * lumaS + lumaSE);
    bool horzSpan = edgeHorz >= edgeVert;

    // Subpixel blend amount from the 3x3 low-pass against the centre.
    float lowpass = (2.0 * (lumaN + lumaS + lumaW + lumaE) + (lumaNW + lumaNE + lumaSW + lumaSE)) / 12.0;
    float subpix = saturate(abs(lowpass - lumaM) / range);
    subpix = (-2.0 * subpix + 3.0) * subpix * subpix;
    subpix = subpix * subpix * g_fxaa.x;

    // Which side of the pixel is the edge on?
    float luma1 = horzSpan ? lumaN : lumaW;
    float luma2 = horzSpan ? lumaS : lumaE;
    float gradient1 = luma1 - lumaM;
    float gradient2 = luma2 - lumaM;
    bool side1 = abs(gradient1) >= abs(gradient2);
    float gradientScaled = 0.25 * max(abs(gradient1), abs(gradient2));
    float stepLength = horzSpan ? rcp.y : rcp.x;
    float lumaLocalAverage;

    if (side1) {
        stepLength = -stepLength;
        lumaLocalAverage = 0.5 * (luma1 + lumaM);
    } else {
        lumaLocalAverage = 0.5 * (luma2 + lumaM);
    }

    float2 edgeUv = uv;
    if (horzSpan) {
        edgeUv.y += stepLength * 0.5;
    } else {
        edgeUv.x += stepLength * 0.5;
    }

    // Walk along the edge in both directions until the luma leaves the edge's average.
    float2 offset = horzSpan ? float2(rcp.x, 0.0) : float2(0.0, rcp.y);
    float2 uv1 = edgeUv - offset;
    float2 uv2 = edgeUv + offset;
    float lumaEnd1 = LumaAt(uv1) - lumaLocalAverage;
    float lumaEnd2 = LumaAt(uv2) - lumaLocalAverage;
    bool reached1 = abs(lumaEnd1) >= gradientScaled;
    bool reached2 = abs(lumaEnd2) >= gradientScaled;

    static const float kSteps[10] = { 1.5, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 4.0, 8.0, 8.0 };

    [unroll]
    for (int i = 0; i < 10; i++) {
        [branch]
        if (!reached1 || !reached2) {
            if (!reached1) {
                uv1 -= offset * kSteps[i];
                lumaEnd1 = LumaAt(uv1) - lumaLocalAverage;
                reached1 = abs(lumaEnd1) >= gradientScaled;
            }
            if (!reached2) {
                uv2 += offset * kSteps[i];
                lumaEnd2 = LumaAt(uv2) - lumaLocalAverage;
                reached2 = abs(lumaEnd2) >= gradientScaled;
            }
        }
    }

    float distance1 = horzSpan ? (uv.x - uv1.x) : (uv.y - uv1.y);
    float distance2 = horzSpan ? (uv2.x - uv.x) : (uv2.y - uv.y);
    bool nearer1 = distance1 < distance2;
    float distanceFinal = min(distance1, distance2);
    float spanLength = distance1 + distance2;

    // Only blend if the nearer end turns the same way as the centre.
    bool centreSmaller = (lumaM - lumaLocalAverage) < 0.0;
    bool correctVariation = ((nearer1 ? lumaEnd1 : lumaEnd2) < 0.0) != centreSmaller;
    float pixelOffset = correctVariation ? (0.5 - distanceFinal / spanLength) : 0.0;
    pixelOffset = max(pixelOffset, subpix);

    float2 finalUv = uv;
    if (horzSpan) {
        finalUv.y += pixelOffset * stepLength;
    } else {
        finalUv.x += pixelOffset * stepLength;
    }
    return float4(Fetch(s_color, finalUv).rgb, lumaM);
}
