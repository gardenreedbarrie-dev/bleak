// BLEAKHOLD(terraintiling): per-texture tiling of modern terrain tiles, after WarcraftXL's wxl-modern-adt.
//
// Copyright (C) 2026 WarcraftXL (feature), Bleakhold (port)
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
// The exponents are read from the chunk's own tile and looked up by the layer's MTEX index, so a texture name
// shared with a stock tile, or loaded as its "_s" specular file, cannot pick up another tile's tiling. Tiles,
// chunks and the terrain draw all live on the main thread.

#include "WoW/Source/WorldClient/MapTerrainTiling.h"
#include "Engine/Source/Gx/Gx.h"
#include "Engine/Source/ModernAssets/ModernAssets.h"
#include "Engine/Source/Tempest/C4Vector.h"
#include "WoW/Source/WorldClient/MapArea.h"
#include "WoW/Source/WorldClient/MapChunk.h"
#include "WoW/Source/WorldClient/MapRenderChunk.h"
#include "WoW/Source/WorldClient/Types.h"
#include <cctype>
#include <cstddef>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

struct AreaTiling {
    const void* m_fileBuffer;
    int32_t m_fileSize;
    // Exponent per MTEX index; empty when the tile has no tiling table.
    std::vector<uint8_t> m_exponents;
};

std::unordered_map<const CMapArea*, AreaTiling> s_areas;

std::string NormalizeName(const char* name) {
    std::string normalized;

    for (const char* c = name; *c; c++) {
        normalized += *c == '/' ? '\\' : static_cast<char>(tolower(static_cast<unsigned char>(*c)));
    }

    return normalized;
}

void CollectExponent(void* user, const char* texture, uint32_t exponent) {
    auto* exponents = static_cast<std::unordered_map<std::string, uint8_t>*>(user);
    exponents->emplace(NormalizeName(texture), static_cast<uint8_t>(exponent & 0xF));
}

const AreaTiling* GetAreaTiling(CMapArea* area) {
    auto it = s_areas.find(area);

    if (it != s_areas.end() && it->second.m_fileBuffer == area->m_fileBuffer && it->second.m_fileSize == area->m_fileSize) {
        return &it->second;
    }

    AreaTiling& tiling = s_areas[area];
    tiling.m_fileBuffer = area->m_fileBuffer;
    tiling.m_fileSize = area->m_fileSize;
    tiling.m_exponents.clear();

    if (!area->m_fileBuffer || area->m_fileSize <= 0) {
        return &tiling;
    }

    std::unordered_map<std::string, uint8_t> byName;
    ModernAssetsForEachTileTiling(area->m_fileBuffer, static_cast<uint32_t>(area->m_fileSize), &CollectExponent, &byName);

    if (byName.empty()) {
        return &tiling;
    }

    tiling.m_exponents.assign(area->m_textures.m_count, 0);

    for (uint32_t i = 0; i < area->m_textures.m_count; i++) {
        const char* name = area->m_textures.m_data[i].m_textureName;
        auto found = name ? byName.find(NormalizeName(name)) : byName.end();

        if (found != byName.end()) {
            tiling.m_exponents[i] = found->second;
        }
    }

    return &tiling;
}

// The tile a render chunk draws: both map chunks of a render chunk sit side by side in one tile.
CMapArea* ChunkArea(CMapRenderChunk* chunk) {
    CMapChunk* mapChunk = chunk->m_mapChunks[0];

    if (!mapChunk) {
        return nullptr;
    }

    CMapBaseObjLink* link = mapChunk->m_parentLinkList.Head();
    return link ? static_cast<CMapArea*>(link->m_ref) : nullptr;
}

// The divisor layer `layer` of `chunk` takes, or 0 when the chunk's tile has no tiling table.
float LayerDivisor(const AreaTiling* tiling, CMapRenderChunk* chunk, uint32_t layer) {
    if (!tiling || tiling->m_exponents.empty() || layer >= chunk->m_layersCount) {
        return 0.0f;
    }

    uint32_t textureId = static_cast<uint32_t>(chunk->m_layers[layer].m_textureId);

    if (textureId >= tiling->m_exponents.size()) {
        return 1.0f;
    }

    return static_cast<float>(1u << tiling->m_exponents[textureId]);
}

const AreaTiling* ChunkTiling(CMapRenderChunk* chunk) {
    CMapArea* area = ChunkArea(chunk);
    return area ? GetAreaTiling(area) : nullptr;
}

}

namespace MapTerrainTiling {

void ScaleTiling(CMapRenderChunk* chunk, C4Vector* texScale, uint32_t layers) {
    const AreaTiling* tiling = ChunkTiling(chunk);

    for (uint32_t i = 0; i < layers; i++) {
        float divisor = LayerDivisor(tiling, chunk, i);

        if (divisor > 1.0f) {
            texScale[1 + i].x /= divisor;
            texScale[1 + i].y /= divisor;
        }
    }
}

void UploadLayerTiling(CMapRenderChunk* chunk, uint32_t layer) {
    const AreaTiling* tiling = ChunkTiling(chunk);
    float divisor = LayerDivisor(tiling, chunk, layer);

    if (divisor <= 0.0f) {
        return;
    }

    // The same base SetVertexShader writes for every layer slot.
    CMapRenderChunk::SVertexShaderConstants& consts = CMapRenderChunk::s_vertexShaderConsts;
    consts.m_texScale[1].x = -CMapChunk::s_geoToTex / divisor;
    consts.m_texScale[1].y = -CMapChunk::s_geoToTex / divisor;
    consts.m_texScale[1].z = 0.0f;
    consts.m_texScale[1].w = 0.0f;

    uint32_t reg = static_cast<uint32_t>(offsetof(CMapRenderChunk::SVertexShaderConstants, m_texScale) / sizeof(C4Vector)) + 1;
    GxShaderConstantsSet(GxSh_Vertex, reg, &consts.m_texScale[1].x, 1);
}

void ForgetArea(CMapArea* area) {
    s_areas.erase(area);
}

}
