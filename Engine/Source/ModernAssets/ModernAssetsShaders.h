#ifndef ENGINE_SOURCE_MODERNASSETS_MODERNASSETSSHADERS_H
#define ENGINE_SOURCE_MODERNASSETS_MODERNASSETSSHADERS_H

#include <cstdint>

// BLEAKHOLD(heightblend): a shader file compiled into the client.
struct ModernAssetsEmbeddedShader {
    const char* m_name;
    const uint8_t* m_data;
    uint32_t m_size;
};

// WarcraftXL's extended terrain pixel shaders (ThirdParty/WarcraftXL/shaders/pixel/ps_3_0), generated into
// ModernAssetsTerrainShaders.cpp at configure time.
extern const ModernAssetsEmbeddedShader g_modernAssetsTerrainShaders[];
extern const uint32_t g_modernAssetsTerrainShaderCount;

#endif
