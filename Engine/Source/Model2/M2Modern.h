#ifndef ENGINE_SOURCE_MODEL2_M2MODERN_H
#define ENGINE_SOURCE_MODEL2_M2MODERN_H

#include <cstdint>

class CM2Shared;
class M2SkinSection;

// BLEAKHOLD(modernassets): the in-client half of the modern model support. Engine/Source/ModernAssets
// converts a modern model file to the 3.3.5a layout as it is opened; what has to happen on the parsed model
// (the skin's material contract, the per-draw bone budget, index starts past 65535) is done here.

// CM2Shared::m_modernFlags
enum {
    M2MODERN_CONVERTED = 0x1, // converted from a modern file when it was opened
    M2MODERN_TAGGED = 0x2,    // converted ahead of time by the WarcraftXL converter (WXLC trailer)
};

// Called by CM2Shared::FinishLoading before the model is parsed: finishes the version of a converted model
// and records where the model came from in m_modernFlags.
void M2ModernPrepareModel(CM2Shared* shared);

// Called by CM2Shared::FinishLoadingSkinProfile once the skin is parsed, before InitializeSkinProfile.
// Splits every skin section that draws with more bones than the device holds per draw, and rebuilds the
// material contract a converted model's skin leaves out. `skinSize` is the skin buffer size.
void M2ModernFinalizeSkin(CM2Shared* shared, uint32_t skinSize);

// The first index of a section read from a skin file. Skins past 65535 indices spell it
// (level << 16) | indexStart, level being the high half of m_skinSectionId; the pair is taken only when the
// range it names lies inside the skin's index array, because older skins use level as a LOD marker.
uint32_t M2SkinSectionIndexStart(const M2SkinSection& section, uint32_t skinIndexCount);

// The geoset id of a section read from a skin file: the low half of m_skinSectionId when its high half is an
// index start (see M2SkinSectionIndexStart), the whole field otherwise.
uint32_t M2SkinSectionGeosetId(const M2SkinSection& section, uint32_t skinIndexCount);

// The first index of a section the client built itself (CM2Shared::m_skinSections after SetIndices, the
// sections of an optimized model): always (level << 16) | indexStart.
uint32_t M2BuiltSectionIndexStart(const M2SkinSection& section);

// Writes the first index of a section the client builds itself, keeping the low half of m_skinSectionId.
void M2SetBuiltSectionIndexStart(M2SkinSection& section, uint32_t indexStart);

// The low half of m_skinSectionId, where the client keeps its own section and batch-range indices.
uint32_t M2BuiltSectionId(const M2SkinSection& section);

#endif
