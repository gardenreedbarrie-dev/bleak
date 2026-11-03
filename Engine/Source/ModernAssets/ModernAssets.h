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

// Whether `name` is a texture path a modern terrain tile resolved from a FileDataID.
bool ModernAssetsIsModernTexture(const char* name);

// BLEAKHOLD(terraintiling): the per-texture tiling a merged modern tile carries in a trailing ATSC table, after
// the chunks the client reads. Calls `fn` for each texture the table names in the tile bytes `tile`: the name
// as the tile's MTEX has it (lowercased, backslashes) and its exponent (the texture tiles 1 << exponent times
// wider). A tile without the table calls nothing.
void ModernAssetsForEachTileTiling(const void* tile, uint32_t size, void (*fn)(void* user, const char* texture, uint32_t exponent), void* user);

#endif
