// BleakFx shared definitions.
// Pixel constants c192-c223 belong to BleakFx; the stock shaders only use low registers. BleakFx sets c223 to the
// target's texel size and c222 - N to the texel size of the texture on stage N before each pass.
#ifndef BH_COMMON_HLSLI
#define BH_COMMON_HLSLI

float4 g_outTexel : register(c223);
float4 g_texel0 : register(c222);
float4 g_texel1 : register(c221);
float4 g_texel2 : register(c220);
float4 g_texel3 : register(c219);

static const float3 kLumaWeights = float3(0.2126, 0.7152, 0.0722);

float Luma(float3 c) {
    return dot(c, kLumaWeights);
}

// The back buffer holds display (gamma 2.2) values; effects that add light work on linear values.
float3 ToLinear(float3 c) {
    return pow(max(c, 0.0), 2.2);
}

float3 ToGamma(float3 c) {
    return pow(max(c, 0.0), 1.0 / 2.2);
}

// Bloom levels are stored in 8-bit targets as sqrt(linear), which keeps dark glow free of banding.
float3 BloomDecode(float3 c) {
    return c * c;
}

float3 BloomEncode(float3 c) {
    return sqrt(saturate(c));
}

float4 Fetch(sampler2D s, float2 uv) {
    return tex2Dlod(s, float4(uv, 0.0, 0.0));
}

// Interleaved gradient noise (Jimenez 2014): cheap per-pixel noise for dithering.
float Ign(float2 pixel) {
    return frac(52.9829189 * frac(dot(pixel, float2(0.06711056, 0.00583715))));
}

// Depth: the hardware depth buffer (INTZ, z/w in red) and the camera's projection in c218:
// x = 1 / proj[0][0], y = 1 / proj[1][1], z = proj[2][2], w = proj[3][2] (Direct3D, row vectors, w = view z).
float4 g_proj : register(c218);
// x: depth buffer value from which a pixel counts as open sky (far away or never drawn).
float4 g_sky : register(c217);

float LinearDepth(float d) {
    return g_proj.w / (d - g_proj.z);
}

// View-space position (camera at the origin, looking along +z) of the pixel at uv with view depth z.
float3 ViewPosition(float2 uv, float z) {
    float2 ndc = float2(uv.x * 2.0 - 1.0, 1.0 - uv.y * 2.0);
    return float3(ndc * g_proj.xy * z, z);
}

#endif
