#ifndef WOW_SOURCE_WORLDCLIENT_MAPTERRAINTILING_H
#define WOW_SOURCE_WORLDCLIENT_MAPTERRAINTILING_H

#include <cstdint>

class C4Vector;
class CMapArea;
class CMapRenderChunk;

// BLEAKHOLD(terraintiling): modern terrain tiles give each texture its own tiling (MTXP), where the 3.3.5a
// terrain draws every layer at one tiling. The tile merge keeps those exponents in a table after the chunks the
// client reads (see ModernAssetsForEachTileTiling); the terrain draw applies them per layer. Only the tile that
// names a texture changes how it tiles, so stock tiles draw exactly as before.
namespace MapTerrainTiling {

// When all of a chunk's layers draw at once: widens layer i's tiling (texScale[1 + i]) for each of `layers`.
void ScaleTiling(CMapRenderChunk* chunk, C4Vector* texScale, uint32_t layers);

// When a chunk draws one layer per pass: uploads that layer's tiling to the one layer slot the pass samples.
// Does nothing for a chunk whose tile has no tiling table.
void UploadLayerTiling(CMapRenderChunk* chunk, uint32_t layer);

// Called when a tile is destroyed: forgets what was read from it.
void ForgetArea(CMapArea* area);

}

#endif
