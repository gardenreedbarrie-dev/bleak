// BLEAKHOLD(modernassets): the in-client half of the modern model support.
//
// The bone-budget split and the skin material rebuild are ports of WarcraftXL's BoneBudget.cpp and Skin.cpp
// (wxl-modern-assets, src/common and src/models/m2) onto the client's own model structures. WarcraftXL patches
// the 32-bit client and stores new arrays by pointer; here every new array is placed in the model or skin
// buffer itself, because M2Array holds a 32-bit offset relative to itself.
//
// Copyright (C) 2026 WarcraftXL (algorithms), Bleakhold (port)
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

#include "Engine/Source/Model2/M2Modern.h"
#include "Engine/Source/Base/SIMD.h"
#include "Engine/Source/Gx/CGxDevice/CGxDevice.h"
#include "Engine/Source/Model2/M2Data.h"
#include "Engine/Source/Model2/M2Shared.h"
#include "Engine/Source/ModernAssets/ModernAssets.h"
#include "ThirdParty/WarcraftXL/include/core/Logger.hpp"
#include "ThirdParty/WarcraftXL/shared/common/Text.hpp"
#include "ThirdParty/WarcraftXL/shared/common/WxlTag.hpp"
#include <algorithm>
#include <cstring>
#include <unordered_map>
#include <vector>

namespace {

// The vertex shader keeps the bone palette from constant register 31 on, three registers per bone.
const uint32_t s_bonePaletteRegister = 31;

// The client's own palette size at 256 constants: the shadow matrices live at c224..c235, so the palette has
// to end below them (WarcraftXL's 75 assumes its own shaders). Devices with fewer constants get fewer.
const uint32_t s_maxBonesPerDraw = 64;

// A skin with more sections or batches than this is treated as malformed.
const uint32_t s_maxBatches = 0x4000;

// A packed blend-bit pair below this, a modern shader-effect index from it on.
const uint16_t s_modernShaderMin = 0x8000;

const uint32_t s_skinU16Max = 0xFFFF;

// The live arrays of one skin and its model, copied out so they can be rewritten before any of it is
// committed back.
struct M2ModernWork {
    std::vector<uint16_t> m_vertices;
    std::vector<ubyte4> m_bones;
    std::vector<uint16_t> m_indices;
    std::vector<M2SkinSection> m_sections;
    std::vector<M2Batch> m_batches;
    std::vector<uint16_t> m_boneCombos;
    std::vector<uint16_t> m_textureCoordCombos;
    std::vector<uint16_t> m_textureCombinerCombos;
    std::vector<uint16_t> m_textureTransformCombos;

    bool m_geometryChanged = false;
    bool m_sectionsChanged = false;
    bool m_batchesChanged = false;
    bool m_boneCombosChanged = false;
    bool m_textureCoordCombosChanged = false;
    bool m_textureCombinerCombosChanged = false;
    bool m_textureTransformCombosChanged = false;
};

// The contiguous run of new sections one original section became.
struct M2SplitRun {
    uint16_t m_first;
    uint16_t m_count;
};

uint32_t SectionLevel(const M2SkinSection& section) {
    return section.m_skinSectionId >> 16;
}

void SetSectionLevel(M2SkinSection& section, uint32_t level) {
    section.m_skinSectionId = (section.m_skinSectionId & 0xFFFF) | (level << 16);
}

// Drops the section from drawing: no geometry, one bone (the native finalize divides by the bone count).
void ParkSection(M2SkinSection& section) {
    SetSectionLevel(section, 0);
    section.m_vertexStart = 0;
    section.m_vertexCount = 0;
    section.m_indexStart = 0;
    section.m_indexCount = 0;
    section.m_boneComboIndex = 0;
    section.m_centerBoneIndex = 0;
}

// Character and item-component skins can pass 65535 indices, so their section level is the high half of a
// 32-bit index start instead of the legacy LOD marker.
bool UsesExtendedIndexStart(const char* name) {
    return wxl::modern::assets::common::text::StartsWithCI(name, "character\\") || wxl::modern::assets::common::text::StartsWithCI(name, "item\\objectcomponents\\");
}

uint32_t FullIndexStart(const M2SkinSection& section, bool extended) {
    return extended ? ((SectionLevel(section) << 16) | section.m_indexStart) : section.m_indexStart;
}

uint32_t MaxBonesPerDraw() {
    uint32_t constants = g_theGxDevicePtr ? g_theGxDevicePtr->Caps().m_shaderConstants[GxSh_Vertex] : 0;

    if (constants < s_bonePaletteRegister + 3) {
        return s_maxBonesPerDraw;
    }

    // The same reservation as CM2Shared::Initialize.
    uint32_t bones = (constants > 0xC0 ? constants - 64 : constants - 32) / 3;
    return std::min(s_maxBonesPerDraw, bones);
}

// Whether any drawn section of the live skin uses more bones than one draw holds (the condition
// SplitSections splits on), checked before anything is copied.
bool NeedsSplit(const char* name, uint32_t maxBones, const M2SkinProfile* skin) {
    bool extended = UsesExtendedIndexStart(name);

    for (uint32_t i = 0; i < skin->m_skinSections.m_count; i++) {
        const M2SkinSection& section = skin->m_skinSections[i];

        if ((extended || SectionLevel(section) == 0) && section.m_boneCount > maxBones) {
            return true;
        }
    }

    return false;
}

// Port of common::bones::SplitSubmeshes: partitions every drawn section whose bone palette is over the
// per-draw ceiling into sections that each fit, each with its own boneCombos slice, its own vertex block
// (bones remapped onto the slice) and its own triangle block. False leaves `work` untouched.
bool SplitSections(const char* name, uint32_t maxBones, M2ModernWork& work, std::vector<M2SplitRun>& splitMap, uint32_t& splitCount) {
    const std::vector<uint16_t>& boneCombos = work.m_boneCombos;
    uint32_t boneComboCount = static_cast<uint32_t>(boneCombos.size());

    if (!boneComboCount || boneComboCount > 0x10000 || work.m_vertices.empty() || work.m_indices.empty() || work.m_bones.size() < work.m_vertices.size()) {
        return false;
    }

    bool extended = UsesExtendedIndexStart(name);
    bool needsSplit = false;

    for (const M2SkinSection& section : work.m_sections) {
        if ((extended || SectionLevel(section) == 0) && section.m_boneCount > maxBones) {
            needsSplit = true;
            break;
        }
    }

    if (!needsSplit) {
        return false;
    }

    uint32_t vertexCount = static_cast<uint32_t>(work.m_vertices.size());
    uint32_t indexCount = static_cast<uint32_t>(work.m_indices.size());

    std::vector<uint16_t> newVertices;
    std::vector<ubyte4> newBones;
    std::vector<uint16_t> newIndices;
    std::vector<uint16_t> newBoneCombos(boneCombos);
    std::vector<M2SkinSection> newSections;
    std::vector<uint16_t> origins;

    newVertices.reserve(vertexCount);
    newBones.reserve(vertexCount);
    newIndices.reserve(indexCount);

    splitCount = 0;

    for (uint32_t si = 0; si < work.m_sections.size(); si++) {
        M2SkinSection section = work.m_sections[si];

        // A level > 0 section is a sub-batch the client cannot draw: kept as one parked placeholder so the
        // batch re-point stays 1:1.
        if (SectionLevel(section) > 0 && !extended) {
            ParkSection(section);
            section.m_boneCount = 1;
            section.m_boneInfluences &= 0xFF;
            newSections.push_back(section);
            origins.push_back(static_cast<uint16_t>(si));
            continue;
        }

        uint32_t sourceIndexStart = FullIndexStart(section, extended);

        if (sourceIndexStart > indexCount || section.m_indexCount > indexCount - sourceIndexStart) {
            WLOG_WARN("modern-assets: '%s' section %u index window past the skin's index count, skipping bone split", name, si);
            return false;
        }

        uint32_t triCount = section.m_indexCount / 3;
        uint32_t comboBase = section.m_boneComboIndex;
        uint32_t emittedSections = 0;

        std::vector<uint16_t> globals;
        uint32_t triStart = 0;

        // Emits triangles [triFrom, triTo) as one section.
        auto emit = [&](uint32_t triFrom, uint32_t triTo, std::vector<uint16_t>& sectionGlobals) -> bool {
            if (triFrom >= triTo) {
                return true;
            }

            std::sort(sectionGlobals.begin(), sectionGlobals.end());

            uint32_t comboIndex = static_cast<uint32_t>(newBoneCombos.size());

            if (comboIndex > s_skinU16Max) {
                return false;
            }

            newBoneCombos.insert(newBoneCombos.end(), sectionGlobals.begin(), sectionGlobals.end());

            uint32_t vertexStart = static_cast<uint32_t>(newVertices.size());
            uint32_t indexStart = static_cast<uint32_t>(newIndices.size());

            if (vertexStart > s_skinU16Max || (!extended && indexStart > s_skinU16Max) || (extended && (indexStart >> 16) > s_skinU16Max)) {
                return false;
            }

            std::unordered_map<uint16_t, uint16_t> remap;

            for (uint32_t t = triFrom; t < triTo; t++) {
                for (uint32_t k = 0; k < 3; k++) {
                    uint16_t vertex = work.m_indices[sourceIndexStart + t * 3 + k];

                    if (vertex >= vertexCount) {
                        return false;
                    }

                    auto it = remap.find(vertex);
                    uint16_t newVertex;

                    if (it == remap.end()) {
                        uint32_t next = static_cast<uint32_t>(newVertices.size());

                        if (next > s_skinU16Max) {
                            return false;
                        }

                        newVertex = static_cast<uint16_t>(next);
                        remap.emplace(vertex, newVertex);
                        newVertices.push_back(work.m_vertices[vertex]);

                        ubyte4 bones;

                        for (uint32_t j = 0; j < 4; j++) {
                            uint32_t combo = comboBase + work.m_bones[vertex].b[j];
                            uint16_t global = combo < boneComboCount ? boneCombos[combo] : sectionGlobals[0];
                            auto lower = std::lower_bound(sectionGlobals.begin(), sectionGlobals.end(), global);
                            bones.b[j] = static_cast<uint8_t>(lower != sectionGlobals.end() && *lower == global ? lower - sectionGlobals.begin() : 0);
                        }

                        newBones.push_back(bones);
                    } else {
                        newVertex = it->second;
                    }

                    newIndices.push_back(newVertex);
                }
            }

            uint32_t sectionVertexCount = static_cast<uint32_t>(newVertices.size()) - vertexStart;
            uint32_t sectionIndexCount = static_cast<uint32_t>(newIndices.size()) - indexStart;

            if (sectionVertexCount > s_skinU16Max || sectionIndexCount > s_skinU16Max) {
                return false;
            }

            M2SkinSection split = section;
            split.m_vertexStart = static_cast<uint16_t>(vertexStart);
            split.m_vertexCount = static_cast<uint16_t>(sectionVertexCount);
            SetSectionLevel(split, extended ? indexStart >> 16 : 0);
            split.m_indexStart = static_cast<uint16_t>(indexStart & s_skinU16Max);
            split.m_indexCount = static_cast<uint16_t>(sectionIndexCount);
            split.m_boneCount = static_cast<uint16_t>(sectionGlobals.size());
            split.m_boneComboIndex = static_cast<uint16_t>(comboIndex);
            newSections.push_back(split);
            origins.push_back(static_cast<uint16_t>(si));
            emittedSections++;

            return true;
        };

        for (uint32_t t = 0; t < triCount; t++) {
            uint16_t triangleBones[12];
            int32_t triangleBoneCount = 0;

            for (uint32_t k = 0; k < 3; k++) {
                uint16_t vertex = work.m_indices[sourceIndexStart + t * 3 + k];

                if (vertex >= vertexCount) {
                    return false;
                }

                for (uint32_t j = 0; j < 4; j++) {
                    uint32_t combo = comboBase + work.m_bones[vertex].b[j];
                    uint16_t global = combo < boneComboCount ? boneCombos[combo] : 0;

                    if (std::find(triangleBones, triangleBones + triangleBoneCount, global) == triangleBones + triangleBoneCount && triangleBoneCount < 12) {
                        triangleBones[triangleBoneCount++] = global;
                    }
                }
            }

            size_t unionSize = globals.size();

            for (int32_t e = 0; e < triangleBoneCount; e++) {
                if (std::find(globals.begin(), globals.end(), triangleBones[e]) == globals.end()) {
                    unionSize++;
                }
            }

            if (unionSize > maxBones && t > triStart) {
                if (!emit(triStart, t, globals)) {
                    return false;
                }

                globals.clear();
                triStart = t;
            }

            for (int32_t e = 0; e < triangleBoneCount; e++) {
                if (std::find(globals.begin(), globals.end(), triangleBones[e]) == globals.end()) {
                    globals.push_back(triangleBones[e]);
                }
            }
        }

        if (!emit(triStart, triCount, globals)) {
            return false;
        }

        if (emittedSections == 0) {
            M2SkinSection empty = section;
            empty.m_vertexCount = 0;
            empty.m_indexCount = 0;
            empty.m_boneCount = 1;
            newSections.push_back(empty);
            origins.push_back(static_cast<uint16_t>(si));
        } else if (emittedSections > 1) {
            splitCount += emittedSections - 1;
        }
    }

    if (newVertices.size() > s_skinU16Max || newSections.size() > s_maxBatches) {
        return false;
    }

    splitMap.assign(work.m_sections.size(), M2SplitRun { 0, 0 });

    for (uint32_t i = 0; i < newSections.size(); i++) {
        uint16_t origin = origins[i];

        if (origin >= splitMap.size()) {
            continue;
        }

        if (splitMap[origin].m_count == 0) {
            splitMap[origin].m_first = static_cast<uint16_t>(i);
        }

        splitMap[origin].m_count++;
    }

    work.m_vertices.swap(newVertices);
    work.m_bones.swap(newBones);
    work.m_indices.swap(newIndices);
    work.m_sections.swap(newSections);
    work.m_boneCombos.swap(newBoneCombos);
    work.m_geometryChanged = true;
    work.m_sectionsChanged = true;
    work.m_boneCombosChanged = true;

    return true;
}

// Port of common::bones::RepointBatchesAfterSplit: points each existing batch at every section its
// original section became.
void RepointBatches(const std::vector<M2SplitRun>& splitMap, M2ModernWork& work) {
    if (splitMap.empty() || work.m_batches.empty()) {
        return;
    }

    std::vector<M2Batch> batches;
    batches.reserve(work.m_batches.size());

    for (const M2Batch& batch : work.m_batches) {
        M2SplitRun run = { batch.m_skinSectionIndex, 1 };

        if (batch.m_skinSectionIndex < splitMap.size()) {
            run = splitMap[batch.m_skinSectionIndex];
        }

        for (uint16_t s = 0; s < run.m_count; s++) {
            M2Batch repointed = batch;
            repointed.m_skinSectionIndex = static_cast<uint16_t>(run.m_first + s);
            batches.push_back(repointed);
        }
    }

    if (batches.empty() || batches.size() > s_maxBatches) {
        return;
    }

    work.m_batches.swap(batches);
    work.m_batchesChanged = true;
}

uint16_t LookupSingle(std::vector<uint16_t>& lookup, int16_t value) {
    uint16_t v = static_cast<uint16_t>(value);

    for (size_t n = 0; n < lookup.size(); n++) {
        if (lookup[n] == v) {
            return static_cast<uint16_t>(n);
        }
    }

    lookup.push_back(v);

    return static_cast<uint16_t>(lookup.size() - 1);
}

// Appends an adjacent pair, reusing an overlapping tail, so that [base] == a and [base + 1] == b.
uint16_t LookupPair(std::vector<uint16_t>& lookup, int16_t a, int16_t b) {
    uint16_t va = static_cast<uint16_t>(a);
    uint16_t vb = static_cast<uint16_t>(b);

    for (size_t n = 0; n + 1 < lookup.size(); n++) {
        if (lookup[n] == va && lookup[n + 1] == vb) {
            return static_cast<uint16_t>(n);
        }
    }

    size_t size = lookup.size();

    if (size > 1 && lookup[size - 1] == va) {
        lookup.push_back(vb);
        return static_cast<uint16_t>(size - 1);
    }

    lookup.push_back(va);
    lookup.push_back(vb);

    return static_cast<uint16_t>(size);
}

// Finds or appends a (blend1, blend2) pair in textureCombinerCombos.
uint16_t BlendOverride(std::vector<uint16_t>& combos, uint16_t blend1, uint16_t blend2) {
    for (size_t n = 0; n + 1 < combos.size(); n += 2) {
        if (combos[n] == blend1 && combos[n + 1] == blend2) {
            return static_cast<uint16_t>(n);
        }
    }

    uint16_t base = static_cast<uint16_t>(combos.size());
    combos.push_back(blend1);
    combos.push_back(blend2);

    return base;
}

uint16_t NextLookup(uint16_t base, uint32_t count) {
    uint32_t next = static_cast<uint32_t>(base) + 1;
    return next < count ? static_cast<uint16_t>(next) : base;
}

// Port of skin::FixSubmeshes: parks LOD sections, clamps drawn sections' bone counts to the ceiling and to
// the boneCombos bounds, and marks sections without geometry.
void FixSections(uint32_t maxBones, bool extended, M2ModernWork& work, std::vector<uint8_t>& badSections) {
    uint32_t indexCount = static_cast<uint32_t>(work.m_indices.size());
    uint32_t boneComboCount = static_cast<uint32_t>(work.m_boneCombos.size());

    badSections.assign(work.m_sections.size(), 0);

    for (uint32_t i = 0; i < work.m_sections.size(); i++) {
        M2SkinSection& section = work.m_sections[i];

        if (SectionLevel(section) > 0 && !extended) {
            ParkSection(section);
        } else if (section.m_indexCount != 0) {
            uint32_t start = FullIndexStart(section, extended);

            if (start > indexCount || section.m_indexCount > indexCount - start) {
                WLOG_WARN("modern-assets: section %u index window past the skin's index count, parking", i);
                ParkSection(section);
            }
        }

        if (section.m_indexCount == 0) {
            if (section.m_boneCount < 1) {
                section.m_boneCount = 1;
            }

            badSections[i] = 1;
        } else {
            uint32_t cap = maxBones;
            uint32_t byCombo = boneComboCount > section.m_boneComboIndex ? boneComboCount - section.m_boneComboIndex : 1;

            if (byCombo < cap) {
                cap = byCombo;
            }

            if (cap < 1) {
                cap = 1;
            }

            if (section.m_boneCount > cap) {
                section.m_boneCount = static_cast<uint16_t>(cap);
            }

            if (section.m_boneCount < 1) {
                section.m_boneCount = 1;
            }

            if (section.m_boneInfluences == 0) {
                section.m_boneInfluences = 1;
            }
        }

        section.m_boneInfluences &= 0xFF;
    }

    work.m_sectionsChanged = true;
}

// Port of skin::DecodeBlendBits: turns a packed blend-bit shader id into the fixed-function blend the
// client understands and synthesizes its texture-coordinate combo entries.
void DecodeBlendBits(M2Batch& batch, uint16_t shader, uint16_t textureCount, M2ModernWork& work) {
    uint16_t blend1 = (shader >> 4) & 0x7;
    uint16_t blend2 = shader & 0x7;

    bool twoTextures = textureCount > 1 && (shader & 0x4000) && blend1 != 0 && blend2 != 0;
    uint16_t savedShader = 0;

    if (twoTextures) {
        savedShader = BlendOverride(work.m_textureCombinerCombos, blend1, blend2);
    } else {
        textureCount = 1;
    }

    batch.m_flags &= 0x10;
    batch.m_shader = savedShader;

    if (textureCount == 1) {
        int16_t t0 = (shader & 0x80) ? -1 : 0;
        batch.m_textureCoordComboIndex = LookupSingle(work.m_textureCoordCombos, t0);
    } else {
        int16_t t0;
        int16_t t1;

        if (shader & 0x80) {
            t0 = -1;
            t1 = (shader & 0x8) ? -1 : 0;
        } else {
            t0 = 0;
            t1 = (shader & 0x8) ? -1 : ((shader & 0x4000) ? 1 : 0);
        }

        batch.m_textureCoordComboIndex = LookupPair(work.m_textureCoordCombos, t0, t1);
    }

    batch.m_textureCount = textureCount < 2 ? textureCount : 2;
}

// Port of skin::EnvSplit: splits one modern environment batch into a primary and a second pass over the
// same geometry. False when the low byte is not an environment split.
bool EnvSplit(uint16_t low, uint16_t shader, M2Batch primary, uint32_t weightComboCount, uint32_t transformComboCount, std::vector<M2Batch>& out, M2ModernWork& work) {
    M2Batch follower = primary;
    follower.m_materialIndex = static_cast<uint16_t>(primary.m_materialIndex + 1);
    follower.m_materialLayer = 1;
    follower.m_textureCount = 1;

    switch (low) {
        case 0:
        case 3:
        case 9:
        case 17:
        case 24: {
            primary.m_textureCount = 2;
            uint16_t blend = BlendOverride(work.m_textureCombinerCombos, 1, 4);
            uint16_t coord = LookupPair(work.m_textureCoordCombos, 0, -1);
            primary.m_shader = blend;
            primary.m_textureCoordComboIndex = coord;
            follower.m_shader = blend;
            follower.m_textureCoordComboIndex = coord;
            out.push_back(primary);
            out.push_back(follower);
            return true;
        }

        case 1:
        case 15: {
            primary.m_textureCount = 1;
            primary.m_shader = 0;
            follower.m_shader = 0;
            follower.m_textureComboIndex = static_cast<uint16_t>(primary.m_textureComboIndex + 1);

            if (static_cast<uint32_t>(primary.m_textureWeightComboIndex) + 1 < weightComboCount) {
                follower.m_textureWeightComboIndex = static_cast<uint16_t>(primary.m_textureWeightComboIndex + 1);
            }

            follower.m_textureTransformComboIndex = NextLookup(primary.m_textureTransformComboIndex, transformComboCount);

            int16_t t1 = shader == 0x8001 ? -1 : 1;
            uint16_t coord = LookupPair(work.m_textureCoordCombos, 0, t1);
            primary.m_textureCoordComboIndex = coord;
            follower.m_textureCoordComboIndex = static_cast<uint16_t>(coord + 1);
            out.push_back(primary);
            out.push_back(follower);
            return true;
        }

        case 2: {
            uint16_t blend = BlendOverride(work.m_textureCombinerCombos, 1, 3);
            uint16_t coord = LookupPair(work.m_textureCoordCombos, 0, -1);
            primary.m_shader = blend;
            primary.m_textureCoordComboIndex = coord;
            follower.m_shader = blend;
            follower.m_textureCoordComboIndex = coord;
            out.push_back(primary);
            out.push_back(follower);
            return true;
        }

        default: {
            return false;
        }
    }
}

// Port of skin::DownConvertBatch: reshapes one batch into one batch, or a primary and follower for an
// environment split. Leaves m_skinSectionIndex to the caller.
void DownConvertBatch(M2Batch batch, uint32_t weightComboCount, uint32_t transformComboCount, std::vector<M2Batch>& piece, M2ModernWork& work) {
    uint16_t shader = batch.m_shader;
    uint16_t textureCount = batch.m_textureCount;
    batch.m_flags &= 0x10;

    if (shader >= s_modernShaderMin) {
        // Effect indices 0..2 are Diffuse_T1_Env effects the client draws natively, at index + 1 (0 is
        // "no shader"): one two-texture batch.
        uint16_t effect = shader & 0x7FFF;

        if (effect <= 2) {
            batch.m_shader = static_cast<uint16_t>(s_modernShaderMin | (effect + 1));
            batch.m_textureCount = 2;
            batch.m_textureCoordComboIndex = LookupPair(work.m_textureCoordCombos, 0, -1);
            batch.m_flags &= 0x10;
            piece.push_back(batch);
            return;
        }

        uint16_t low = shader & 0xFF;

        if (EnvSplit(low, shader, batch, weightComboCount, transformComboCount, piece, work)) {
            return;
        }

        switch (low) {
            case 5:
            case 8:
            case 10:
            case 12:
            case 16:
            case 23:
                shader = 0;
                textureCount = 1;
                break;

            case 21:
                shader = 0x4011;
                textureCount = 2;
                break;

            default:
                shader = 0x0010;
                textureCount = 1;
                break;
        }
    }

    if (shader < s_modernShaderMin) {
        DecodeBlendBits(batch, shader, textureCount, work);
    } else {
        batch.m_textureCount = textureCount < 2 ? textureCount : 2;
    }

    piece.push_back(batch);
}

// Port of skin::FixTexUnits: rebuilds the batch array, each original batch emitted for every section its
// original section became; a batch on a section without geometry is reduced to a no-draw batch.
void FixBatches(const std::vector<uint8_t>& badSections, const std::vector<M2SplitRun>& splitMap, uint32_t weightComboCount, uint32_t transformComboCount, M2ModernWork& work) {
    std::vector<M2Batch> batches;
    batches.reserve(work.m_batches.size());

    for (const M2Batch& source : work.m_batches) {
        M2SplitRun run = { source.m_skinSectionIndex, 1 };

        if (source.m_skinSectionIndex < splitMap.size()) {
            run = splitMap[source.m_skinSectionIndex];
        }

        std::vector<M2Batch> piece;
        DownConvertBatch(source, weightComboCount, transformComboCount, piece, work);

        for (uint16_t s = 0; s < run.m_count; s++) {
            uint16_t sectionIndex = static_cast<uint16_t>(run.m_first + s);
            bool bad = sectionIndex < badSections.size() && badSections[sectionIndex];

            for (const M2Batch& p : piece) {
                M2Batch batch = p;
                batch.m_skinSectionIndex = sectionIndex;

                if (bad) {
                    batch.m_shader = 0x8000;
                }

                batches.push_back(batch);
            }
        }
    }

    work.m_batches.swap(batches);
    work.m_batchesChanged = true;
}

// Port of skin::EnsureTextureTransformLookup: a model with texture transforms but no transform lookup gets
// an identity lookup long enough for every batch that indexes it.
void EnsureTextureTransformLookup(const char* name, const M2Data* data, M2ModernWork& work) {
    uint32_t transformCount = data->m_textureTransforms.m_count;

    if (!transformCount || !work.m_textureTransformCombos.empty()) {
        return;
    }

    uint32_t needed = transformCount;

    for (const M2Batch& batch : work.m_batches) {
        uint32_t base = batch.m_textureTransformComboIndex;

        if (base == 0xFFFF) {
            continue;
        }

        uint32_t count = batch.m_textureCount ? batch.m_textureCount : 1;

        if (base <= 0xFFFF - count && needed < base + count) {
            needed = base + count;
        }
    }

    work.m_textureTransformCombos.resize(needed);

    for (uint32_t i = 0; i < needed; i++) {
        work.m_textureTransformCombos[i] = i < transformCount ? static_cast<uint16_t>(i) : 0xFFFF;
    }

    work.m_textureTransformCombosChanged = true;

    WLOG_INFO("modern-assets: '%s' synthesized %u texture-transform lookup entries", name, needed);
}

// Port of skin::FixRenderFlags: blend modes past the client's 0..6 become Add, and render flags above the
// client's five are dropped.
void FixRenderFlags(M2Data* data) {
    for (uint32_t i = 0; i < data->m_materials.m_count; i++) {
        M2Material& material = data->m_materials[i];

        if (material.m_blendMode > 6) {
            material.m_blendMode = 4;
            material.m_flags |= 0x5;
        }

        material.m_flags &= 0x1F;
    }
}

// Port of skin::Rebuild: the material and texture-unit contract a modern skin leaves out.
void RebuildSkin(const char* name, uint32_t maxBones, M2Data* data, const std::vector<M2SplitRun>& splitMap, M2ModernWork& work) {
    if (work.m_batches.size() > s_maxBatches) {
        WLOG_WARN("modern-assets: '%s' skin batch count %zu exceeds the cap, clamping", name, work.m_batches.size());
        work.m_batches.resize(s_maxBatches);
    }

    // The rebuild synthesizes these from the batches; the arrays the file carries are not used.
    work.m_textureCoordCombos.clear();
    work.m_textureCombinerCombos.clear();

    uint32_t weightComboCount = data->m_textureWeightCombos.m_count;
    EnsureTextureTransformLookup(name, data, work);
    uint32_t transformComboCount = static_cast<uint32_t>(work.m_textureTransformCombos.size());

    std::vector<uint8_t> badSections;
    FixSections(maxBones, UsesExtendedIndexStart(name), work, badSections);
    FixBatches(badSections, splitMap, weightComboCount, transformComboCount, work);

    work.m_textureCoordCombosChanged = !work.m_textureCoordCombos.empty();
    work.m_textureCombinerCombosChanged = !work.m_textureCombinerCombos.empty();

    FixRenderFlags(data);
}

template <class T>
void CopyArray(const M2Array<T>& array, std::vector<T>& out) {
    out.assign(array.Data(), array.Data() + array.m_count);
}

uint32_t Align16(uint32_t value) {
    return (value + 15) & ~15u;
}

// Lays the changed arrays out after `size` bytes of an existing buffer.
class M2ModernTail {
    public:
    M2ModernTail(uint32_t size) : m_size(Align16(size)) {
    }

    template <class T>
    uint32_t Reserve(const std::vector<T>& array) {
        uint32_t offset = this->m_size;
        this->m_size = Align16(this->m_size + static_cast<uint32_t>(sizeof(T) * array.size()));
        return offset;
    }

    uint32_t Size() const {
        return this->m_size;
    }

    private:
    uint32_t m_size;
};

template <class T>
void PlaceArray(uint8_t* base, uint32_t offset, const std::vector<T>& source, M2Array<T>& array) {
    T* data = reinterpret_cast<T*>(base + offset);

    if (!source.empty()) {
        memcpy(data, source.data(), sizeof(T) * source.size());
    }

    array.m_count = static_cast<uint32_t>(source.size());
    array.Set(source.empty() ? nullptr : data);
}

// Moves the skin into a buffer with the changed skin arrays appended.
bool CommitSkin(CM2Shared* shared, uint32_t skinSize, const M2ModernWork& work) {
    if (!work.m_geometryChanged && !work.m_sectionsChanged && !work.m_batchesChanged) {
        return true;
    }

    M2ModernTail tail(skinSize);
    uint32_t vertices = work.m_geometryChanged ? tail.Reserve(work.m_vertices) : 0;
    uint32_t bones = work.m_geometryChanged ? tail.Reserve(work.m_bones) : 0;
    uint32_t indices = work.m_geometryChanged ? tail.Reserve(work.m_indices) : 0;
    uint32_t sections = work.m_sectionsChanged ? tail.Reserve(work.m_sections) : 0;
    uint32_t batches = work.m_batchesChanged ? tail.Reserve(work.m_batches) : 0;

    uint8_t* buffer = static_cast<uint8_t*>(SIMD::AllocA16(tail.Size(), __FILE__, __LINE__));

    if (!buffer) {
        return false;
    }

    memcpy(buffer, shared->m_skinData, skinSize);
    memset(buffer + skinSize, 0, tail.Size() - skinSize);

    // M2Array offsets are relative to the array itself, so the copied header still reaches the copied data.
    M2SkinProfile* skin = reinterpret_cast<M2SkinProfile*>(buffer);

    if (work.m_geometryChanged) {
        PlaceArray(buffer, vertices, work.m_vertices, skin->m_vertices);
        PlaceArray(buffer, bones, work.m_bones, skin->m_bones);
        PlaceArray(buffer, indices, work.m_indices, skin->m_indices);
    }

    if (work.m_sectionsChanged) {
        PlaceArray(buffer, sections, work.m_sections, skin->m_skinSections);
    }

    if (work.m_batchesChanged) {
        PlaceArray(buffer, batches, work.m_batches, skin->m_batches);
    }

    SIMD::FreeA16(shared->m_skinData);
    shared->m_skinData = skin;

    return true;
}

// Moves the model into a buffer with the changed model arrays appended.
bool CommitModel(CM2Shared* shared, const M2ModernWork& work) {
    if (!work.m_boneCombosChanged && !work.m_textureCoordCombosChanged && !work.m_textureCombinerCombosChanged && !work.m_textureTransformCombosChanged) {
        return true;
    }

    uint32_t fileSize = shared->m_fileSize;
    M2ModernTail tail(fileSize);
    uint32_t boneCombos = work.m_boneCombosChanged ? tail.Reserve(work.m_boneCombos) : 0;
    uint32_t coordCombos = work.m_textureCoordCombosChanged ? tail.Reserve(work.m_textureCoordCombos) : 0;
    uint32_t combinerCombos = work.m_textureCombinerCombosChanged ? tail.Reserve(work.m_textureCombinerCombos) : 0;
    uint32_t transformCombos = work.m_textureTransformCombosChanged ? tail.Reserve(work.m_textureTransformCombos) : 0;

    uint8_t* buffer = static_cast<uint8_t*>(SIMD::AllocA16(tail.Size(), __FILE__, __LINE__));

    if (!buffer) {
        return false;
    }

    memcpy(buffer, shared->m_data, fileSize);
    memset(buffer + fileSize, 0, tail.Size() - fileSize);

    M2Data* data = reinterpret_cast<M2Data*>(buffer);

    if (work.m_boneCombosChanged) {
        PlaceArray(buffer, boneCombos, work.m_boneCombos, data->m_boneCombos);
    }

    if (work.m_textureCoordCombosChanged) {
        PlaceArray(buffer, coordCombos, work.m_textureCoordCombos, data->m_textureCoordCombos);
    }

    if (work.m_textureCombinerCombosChanged) {
        PlaceArray(buffer, combinerCombos, work.m_textureCombinerCombos, data->m_textureCombinerCombos);
        data->m_flags |= 8;
    }

    if (work.m_textureTransformCombosChanged) {
        PlaceArray(buffer, transformCombos, work.m_textureTransformCombos, data->m_textureTransformCombos);
    }

    SIMD::FreeA16(shared->m_data);
    shared->m_data = data;
    shared->m_fileSize = tail.Size();

    return true;
}

}

void M2ModernPrepareModel(CM2Shared* shared) {
    M2Data* data = shared->m_data;
    shared->m_modernFlags = 0;

    if (!data || shared->m_fileSize < 8 || data->m_magic != 0x3032444D) {
        return;
    }

    if ((data->m_version & MODERN_ASSETS_STAGED_VERSION_BIT) && (data->m_version & ~MODERN_ASSETS_STAGED_VERSION_BIT) == 0x108) {
        data->m_version = 0x108;
        shared->m_modernFlags |= M2MODERN_CONVERTED;
        return;
    }

    uint32_t tagFlags = 0;

    if (wxl::modern::assets::common::tag::Read(reinterpret_cast<const uint8_t*>(data), shared->m_fileSize, tagFlags) && tagFlags) {
        shared->m_modernFlags |= M2MODERN_TAGGED;
    }
}

void M2ModernFinalizeSkin(CM2Shared* shared, uint32_t skinSize) {
    M2Data* data = shared->m_data;
    M2SkinProfile* skin = shared->m_skinData;

    if (!data || !skin) {
        return;
    }

    const char* name = shared->m_fileName;
    uint32_t maxBones = MaxBonesPerDraw();
    bool converted = (shared->m_modernFlags & M2MODERN_CONVERTED) != 0;

    // InitializeSkinProfile sizes co-instance batches from this, and the batched doodad and shadow draws write
    // instances * bones matrices from c31 without another check. Stock picks a profile that already fits;
    // a modern skin carries whatever the retail file says (often 256).
    if (skin->m_boneCountMax > maxBones) {
        skin->m_boneCountMax = maxBones;
    }

    // Otherwise a 3.3.5a model whose sections all fit a draw is left as it was loaded.
    if (!converted && !NeedsSplit(name, maxBones, skin)) {
        return;
    }

    M2ModernWork work;
    CopyArray(skin->m_vertices, work.m_vertices);
    CopyArray(skin->m_bones, work.m_bones);
    CopyArray(skin->m_indices, work.m_indices);
    CopyArray(skin->m_skinSections, work.m_sections);
    CopyArray(skin->m_batches, work.m_batches);
    CopyArray(data->m_boneCombos, work.m_boneCombos);
    CopyArray(data->m_textureCoordCombos, work.m_textureCoordCombos);
    CopyArray(data->m_textureTransformCombos, work.m_textureTransformCombos);

    if (data->m_flags & 8) {
        CopyArray(data->m_textureCombinerCombos, work.m_textureCombinerCombos);
    }

    // The per-draw bone budget belongs to the client, so the split runs for every model.
    std::vector<M2SplitRun> splitMap;
    uint32_t splitCount = 0;
    bool split = SplitSections(name, maxBones, work, splitMap, splitCount) && splitCount > 0;

    if (split) {
        WLOG_INFO("modern-assets: '%s' bone split produced %u extra section(s)", name, splitCount);
    }

    if (converted) {
        RebuildSkin(name, maxBones, data, splitMap, work);
    } else if (split) {
        RepointBatches(splitMap, work);
    } else if (!work.m_sectionsChanged) {
        return;
    }

    if (!CommitSkin(shared, skinSize, work) || !CommitModel(shared, work)) {
        WLOG_WARN("modern-assets: '%s' out of memory finishing the skin", name);
    }
}

uint32_t M2SkinSectionIndexStart(const M2SkinSection& section, uint32_t skinIndexCount) {
    uint32_t wide = (SectionLevel(section) << 16) | section.m_indexStart;

    // Phrased as a subtraction so a garbage level cannot wrap the bound it is checked against.
    if (wide <= skinIndexCount && section.m_indexCount <= skinIndexCount - wide) {
        return wide;
    }

    return section.m_indexStart;
}

uint32_t M2SkinSectionGeosetId(const M2SkinSection& section, uint32_t skinIndexCount) {
    if (SectionLevel(section) && M2SkinSectionIndexStart(section, skinIndexCount) != section.m_indexStart) {
        return section.m_skinSectionId & 0xFFFF;
    }

    return section.m_skinSectionId;
}

uint32_t M2BuiltSectionIndexStart(const M2SkinSection& section) {
    return (SectionLevel(section) << 16) | section.m_indexStart;
}

void M2SetBuiltSectionIndexStart(M2SkinSection& section, uint32_t indexStart) {
    SetSectionLevel(section, indexStart >> 16);
    section.m_indexStart = static_cast<uint16_t>(indexStart);
}

uint32_t M2BuiltSectionId(const M2SkinSection& section) {
    return section.m_skinSectionId & 0xFFFF;
}
