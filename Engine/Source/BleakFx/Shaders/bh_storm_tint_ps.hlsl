// BleakFx storm wall: a faint purple over the world while the camera is in the Bleakhold Royale storm, drawn with the
// full-screen quad and alpha blending after the wall.
float4 g_tint : register(c205);     // rgb the colour, a its strength

float4 main(float2 uv : TEXCOORD0) : COLOR {
    return g_tint;
}
