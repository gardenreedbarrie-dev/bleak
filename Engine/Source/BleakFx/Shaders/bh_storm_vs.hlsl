// BleakFx storm wall, vertex shader: the Bleakhold Royale storm wall and the next circle's ring (BleakStorm.h), in the
// world pass, with the world's projection and, past its far plane, the horizon's. Vertices (GxVBF_PNT) are relative to
// the origin the world is drawn from. Vertex constants c249 and c251 - c255: clear of the stock ones (c0 - c57, the
// bones c31 - c223, the shadows c224 - c235), of the grass wind (c240 - c248) and of the full-screen passes (c250).
float4 g_eye : register(c249);          // xyz the camera, relative to the origin; w the far clamp (see main)
float4 g_viewProj[4] : register(c251);  // relative position to clip space (row vectors)
float4 g_noise : register(c255);        // xyz the origin in noise tiles (only the fraction), w noise tiles per yard

struct VSIn {
    float3 pos : POSITION;
    float3 normal : NORMAL;
    float2 shape : TEXCOORD0;   // yards above the ground under the column, yards below the column's top
};

struct VSOut {
    float4 pos : POSITION;
    float3 noise : TEXCOORD0;   // the world position in noise tiles
    float4 shape : TEXCOORD1;   // xy the vertex's shape, z view depth, w how squarely the wall faces the camera
    float2 weights : TEXCOORD2; // the weights of the two noise projections (by the wall's direction)
};

VSOut main(VSIn i) {
    VSOut o;
    float4 clip = i.pos.x * g_viewProj[0] + i.pos.y * g_viewProj[1] + i.pos.z * g_viewProj[2] + g_viewProj[3];
    // Beyond the far plane: with g_eye.w > 0 the wall still shows, kept at that fraction of the far plane in front of
    // the sky (the horizon's pass, or the world's when no horizon is drawn); with 0 it is clipped there, for the
    // horizon's pass to draw (BleakFx::RenderStorm).
    if (g_eye.w > 0.0) {
        clip.z = min(clip.z, clip.w * g_eye.w);
    }
    o.pos = clip;
    o.noise = i.pos * g_noise.w + g_noise.xyz;
    float2 toEye = g_eye.xy - i.pos.xy;
    float facing = abs(dot(toEye, i.normal.xy)) / max(length(toEye), 0.001);
    o.shape = float4(i.shape, clip.w, facing);
    // A wall facing along x shows the noise of the y-z plane, one facing along y that of the x-z plane.
    o.weights = i.normal.xy * i.normal.xy;
    return o;
}
