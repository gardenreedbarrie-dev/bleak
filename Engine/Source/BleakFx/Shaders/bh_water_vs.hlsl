// BleakFx water, vertex shader. Draws what vsLiquidWater draws: the stock water's vertices (GxVBF_PNCT2) and
// constants (Liquid::VSConstants, uploaded by Liquid::SetShaderConstants), all row vectors.
float4 g_projection[4] : register(c0);
float4 g_modelView[4] : register(c5);
float4 g_texTransforms[24] : register(c9);

struct VSIn {
    float3 pos : POSITION;
    float3 normal : NORMAL;
    float4 color : COLOR0;
    float2 uv0 : TEXCOORD0;
    float2 uv1 : TEXCOORD1;
};

struct VSOut {
    float4 pos : POSITION;
    float3 view : TEXCOORD0;      // view-space position (camera at the origin)
    float3 normal : TEXCOORD1;    // view-space surface normal
    float3 tangent : TEXCOORD2;   // view-space model x and y axes
    float3 bitangent : TEXCOORD3;
    float4 uv : TEXCOORD4;        // z the stock depth coordinate, w 1 for interior (map object) water
    float4 color : TEXCOORD5;     // vertex colour: the tint of interior water
};

VSOut main(VSIn i) {
    VSOut o;
    float4 view = i.pos.x * g_modelView[0] + i.pos.y * g_modelView[1] + i.pos.z * g_modelView[2] + g_modelView[3];
    o.pos = view.x * g_projection[0] + view.y * g_projection[1] + view.z * g_projection[2] + g_projection[3];
    o.view = view.xyz;
    o.normal = i.normal.x * g_modelView[0].xyz + i.normal.y * g_modelView[1].xyz + i.normal.z * g_modelView[2].xyz;
    o.tangent = g_modelView[0].xyz;
    o.bitangent = g_modelView[1].xyz;
    // texTransforms[1] scales the depth coordinate by its b1 (CMaterialWater::Render).
    o.uv = float4(i.uv0, i.uv1.y * g_texTransforms[5].y, i.uv1.x);
    o.color = i.color;
    return o;
}
