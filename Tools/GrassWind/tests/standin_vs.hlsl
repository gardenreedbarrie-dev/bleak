// Stand-in for the stock detail-doodad vertex shader (written for these tests, compiled with
// fxc /T vs_3_0 /E main /Fo standin_vs.cso standin_vs.hlsl): worldView rows in c0-c3, projection c4-c7,
// fog c8, fade c9, sun c10-c12; position, normal, colour and texture coordinate inputs.
#pragma pack_matrix(row_major)
float4x4 g_worldView : register(c0);
float4x4 g_proj : register(c4);
float4 g_fog : register(c8);
float4 g_fade : register(c9);
float4 g_sunDir : register(c10);
float4 g_ambient : register(c11);
float4 g_diffuse : register(c12);

struct VSIn { float4 pos : POSITION; float3 normal : NORMAL; float4 color : COLOR0; float2 uv : TEXCOORD0; };
struct VSOut { float4 pos : POSITION; float4 color : COLOR0; float2 uv : TEXCOORD0; float fog : FOG; };

VSOut main(VSIn i) {
    VSOut o;
    float4 v = mul(float4(i.pos.xyz, 1.0), g_worldView);
    o.pos = mul(v, g_proj);
    float3 n = normalize(mul(i.normal, (float3x3)g_worldView));
    float light = saturate(dot(n, g_sunDir.xyz));
    o.color = float4(i.color.rgb * (g_ambient.rgb + g_diffuse.rgb * light), saturate(v.z * g_fade.x + g_fade.y));
    o.uv = i.uv;
    o.fog = saturate(v.z * g_fog.x + g_fog.y);
    return o;
}
