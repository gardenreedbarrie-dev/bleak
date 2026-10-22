// BLEAKHOLD(heightblend): height-based blending of terrain layers, a port of WarcraftXL's wxl-modern-adt
// render/HeightBlend.cpp onto the client's own terrain draw.
//
// Copyright (C) 2026 WarcraftXL (feature and shaders), Bleakhold (port)
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.
//
// What a layer contributes is decided by its TEXTURE and nothing else: two neighbouring chunks that share a
// texture must publish the same numbers for it, or the difference shows as a straight line along their
// border. So the height data and the sharpness are per layer, and a layer without a height map keeps the
// neutral zeros instead of the whole chunk falling back.

#include "WoW/Source/WorldClient/MapHeightBlend.h"
#include "Engine/Source/Gx/CGxDevice/CGxDevice.h"
#include "Engine/Source/Gx/Gx.h"
#include "Engine/Source/ModernAssets/ModernAssets.h"
#include "Engine/Source/Services/Texture.h"
#include "Engine/Source/Tempest/C4Vector.h"
#include "WoW/Source/WorldClient/Map.h"
#include "WoW/Source/WorldClient/MapRenderChunk.h"
#include <string>
#include <unordered_map>

namespace {

// The extended shaders read the blend from c22..c25: per layer height scale, (height offset - 1), sharpness,
// and in .x of the last one the renormalize strength. All zero is the plain weighted sum.
struct HeightBlendConstants {
    float m_scale[4];
    float m_bias[4];
    float m_sharpness[4];
    float m_shape[4];
};

const uint32_t s_constantsRegister = 22;
const uint32_t s_constantsCount = sizeof(HeightBlendConstants) / (4 * sizeof(float));

// A layer blends by height only when there is another layer to blend with.
const uint32_t s_minLayers = 2;
const uint32_t s_maxLayers = 4;

struct LayerInfo {
    std::string m_name;
    uint32_t m_generation;
    int32_t m_found;
    float m_heightScale;
    float m_heightOffset;
    uint32_t m_tilingExponent;
    CTexture* m_heightTexture;
};

// Keyed by the layer texture; the name is kept so a texture object reused for another file is noticed.
std::unordered_map<CTexture*, LayerInfo> s_layers;

// Height maps, shared by every layer that names them, kept for the session.
std::unordered_map<std::string, CTexture*> s_heightTextures;

uint32_t s_boundMask;

CTexture* HeightTexture(const char* name) {
    auto it = s_heightTextures.find(name);

    if (it != s_heightTextures.end()) {
        return it->second;
    }

    CTexture* texture = CMap::LoadTexture(name);
    s_heightTextures.emplace(name, texture);

    return texture;
}

const LayerInfo* GetLayer(CTexture* texture, uint32_t generation) {
    if (!texture) {
        return nullptr;
    }

    auto it = s_layers.find(texture);

    if (it == s_layers.end() || it->second.m_generation != generation || it->second.m_name != texture->m_filename) {
        LayerInfo& info = s_layers[texture];
        info.m_name = texture->m_filename;
        info.m_generation = generation;
        info.m_heightTexture = nullptr;

        ModernAssetsTerrainTexture description;
        info.m_found = ModernAssetsGetTerrainTexture(texture->m_filename, &description);

        if (info.m_found) {
            info.m_heightScale = description.m_heightScale;
            info.m_heightOffset = description.m_heightOffset;
            info.m_tilingExponent = description.m_tilingExponent;

            if (description.m_heightTexture[0]) {
                info.m_heightTexture = HeightTexture(description.m_heightTexture);
            }
        }

        return info.m_found ? &info : nullptr;
    }

    return it->second.m_found ? &it->second : nullptr;
}

void UploadConstants(const HeightBlendConstants& constants) {
    GxShaderConstantsSet(GxSh_Pixel, s_constantsRegister, constants.m_scale, s_constantsCount);
}

}

namespace MapHeightBlend {

int32_t s_enabled = 1;
float s_sharpness = 2.0f;

void BindChunk(CMapRenderChunk* chunk, int32_t heightMaps) {
    s_boundMask = 0;

    // The stock shaders read none of this.
    if (!ModernAssetsTerrainShadersServed()) {
        return;
    }

    HeightBlendConstants constants = {};
    uint32_t generation = ModernAssetsTerrainTextureGeneration();
    uint32_t layers = chunk->m_layersCount;

    // A reflective (environment-mapped) first layer is left to the stock blend, as WarcraftXL does.
    if (heightMaps && s_enabled && generation && layers >= s_minLayers && layers <= s_maxLayers && !(chunk->m_renderFlags & 0x4)) {
        for (uint32_t i = 0; i < layers; i++) {
            const LayerInfo* info = GetLayer(chunk->m_layers[i].m_texture, generation);

            if (!info || !info->m_heightTexture) {
                continue;
            }

            CGxTex* gxTex = TextureGetGxTex(info->m_heightTexture, 0, nullptr);

            if (!gxTex) {
                continue;
            }

            constants.m_scale[i] = info->m_heightScale;
            constants.m_bias[i] = info->m_heightOffset - 1.0f;
            constants.m_sharpness[i] = s_sharpness;

            g_theGxDevicePtr->RsSet(static_cast<EGxRenderState>(GxRs_Texture9 + i), gxTex);
            GxTexSetWrap(gxTex, GxTex_Wrap, GxTex_Wrap);
            s_boundMask |= 1 << i;
        }

        // Renormalizing rebalances the layers against each other, so it is only asked for once a layer
        // actually carries height.
        if (s_boundMask) {
            constants.m_shape[0] = 1.0f;
        }
    }

    // Uploaded for every chunk, so a chunk with nothing to blend never sees what another draw left in c22..c25.
    UploadConstants(constants);
}

void UnbindChunk(CMapRenderChunk* chunk) {
    (void)chunk;

    if (!s_boundMask) {
        return;
    }

    for (uint32_t i = 0; i < s_maxLayers; i++) {
        if (s_boundMask & (1 << i)) {
            g_theGxDevicePtr->RsSet(static_cast<EGxRenderState>(GxRs_Texture9 + i), static_cast<CGxTex*>(nullptr));
        }
    }

    HeightBlendConstants neutral = {};
    UploadConstants(neutral);
    s_boundMask = 0;
}

void ScaleTiling(CMapRenderChunk* chunk, C4Vector* texScale) {
    uint32_t generation = ModernAssetsTerrainTextureGeneration();

    if (!s_enabled || !generation) {
        return;
    }

    uint32_t layers = chunk->m_layersCount < s_maxLayers ? chunk->m_layersCount : s_maxLayers;

    for (uint32_t i = 0; i < layers; i++) {
        const LayerInfo* info = GetLayer(chunk->m_layers[i].m_texture, generation);

        if (!info || !info->m_tilingExponent) {
            continue;
        }

        float divisor = static_cast<float>(1u << (info->m_tilingExponent & 0xF));
        texScale[1 + i].x /= divisor;
        texScale[1 + i].y /= divisor;
    }
}

}
