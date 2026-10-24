// Full-screen quad for every BleakFx pass. The vertices come in clip space; c250.xy moves them by half a pixel
// (-1/w, 1/h) so that D3D9 pixel centres meet texel centres.
float4 g_halfPixel : register(c250);

struct VSIn {
    float3 pos : POSITION;
    float2 uv : TEXCOORD0;
};

struct VSOut {
    float4 pos : POSITION;
    float2 uv : TEXCOORD0;
};

VSOut main(VSIn i) {
    VSOut o;
    o.pos = float4(i.pos.xy + g_halfPixel.xy, 0.0, 1.0);
    o.uv = i.uv;
    return o;
}
