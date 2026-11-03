// Clears a target to 0 (for passes that discard pixels).
float4 main(float2 uv : TEXCOORD0) : COLOR {
    return float4(0.0, 0.0, 0.0, 0.0);
}
