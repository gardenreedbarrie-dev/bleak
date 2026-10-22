#ifndef ENGINE_SOURCE_MODERNASSETS_MODERNASSETS_H
#define ENGINE_SOURCE_MODERNASSETS_MODERNASSETS_H

#include <cstdint>

class SFileImpl;

// BLEAKHOLD(modernassets): models, map objects, terrain and textures authored for newer clients (Legion
// and later: MD21 models, split ADT tiles, uncompressed BLPs, ...) are converted to the 3.3.5a formats
// as they are opened. The conversions are WarcraftXL's (ThirdParty/WarcraftXL, GPL-3.0-or-later).

// The inner version a converted model carries until Model2 finishes it: the 3.3.5a version (264) with this
// bit set. CM2Shared::FinishLoading clears the bit and marks the model as converted.
static const uint32_t MODERN_ASSETS_STAGED_VERSION_BIT = 0x40000000;

// Called by SFile::OpenEx for every file it opens. A file that needs converting is read whole, converted,
// and turned into an SFILE_MEMORY file holding the converted bytes; any other file is left as it is.
void ModernAssetsFilterOpenedFile(const char* name, SFileImpl* file);

// BLEAKHOLD(heightblend): what modern terrain tiles say about one of their textures. Tiles carry it per texture
// (MTXP and MHID in the _tex0 file); the merge keeps it in trailing ATHB/ATSC tables that the client's own tile
// loader never reads, and the client collects it here when the tile is opened.
struct ModernAssetsTerrainTexture {
    float m_heightScale;        // height map contribution (0 = none)
    float m_heightOffset;       // added to the height before scaling (1 = none)
    uint32_t m_tilingExponent;  // the texture tiles 1 << m_tilingExponent times wider
    char m_heightTexture[260];  // the _h height map, empty when the texture has none
};

// Changes every time a tile describes a terrain texture not seen before (0: none yet).
uint32_t ModernAssetsTerrainTextureGeneration();

// What modern tiles say about `texture` (a terrain texture path, with or without its .blp extension).
bool ModernAssetsGetTerrainTexture(const char* texture, ModernAssetsTerrainTexture* out);

// Serves WarcraftXL's extended terrain pixel shaders (Shaders\Pixel\ps_3_0\Terrain1-3) in place of the stock
// ones from now on. With every height-blend constant at zero they draw exactly like the stock shaders.
void ModernAssetsSetTerrainShaders(int32_t enabled);

// Whether the extended terrain shaders were served since the last call to ModernAssetsSetTerrainShaders.
int32_t ModernAssetsTerrainShadersServed();

#endif
