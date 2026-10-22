#ifndef WOW_SOURCE_WORLDCLIENT_MAPHEIGHTBLEND_H
#define WOW_SOURCE_WORLDCLIENT_MAPHEIGHTBLEND_H

#include <cstdint>

class C4Vector;
class CMapRenderChunk;

// BLEAKHOLD(heightblend): height-based blending of terrain layers, for textures that modern tiles describe
// (a ported version of WarcraftXL's wxl-modern-adt HeightBlend.cpp). The extended terrain pixel shaders
// (served by Engine/Source/ModernAssets) read each layer's height map from s9..s12 and its blend shape from
// c22..c25; all-zero constants draw exactly like the stock shaders.
namespace MapHeightBlend {

// terrainHeightBlend and terrainHeightBlendSharpness.
extern int32_t s_enabled;
extern float s_sharpness;

// Before a single-pass terrain chunk is drawn: binds the height maps of its layers and uploads their blend
// constants, or the neutral constants when the chunk has nothing to blend.
void BindChunk(CMapRenderChunk* chunk, int32_t heightMaps);

// After the draw: unbinds what BindChunk bound and leaves the neutral constants standing.
void UnbindChunk(CMapRenderChunk* chunk);

// Widens each layer's tiling (layer i at texScale[1 + i]) by the tiling the texture's tile asked for.
void ScaleTiling(CMapRenderChunk* chunk, C4Vector* texScale);

}

#endif
