// ModelForge native harness (CAFE.SPEC.md section 5.3): runs the 3.3.5a client's own M2 relocation code on a
// built model, then walks the client's loader and first-draw paths with bounds checks instead of crashes.
//
//   g++ -std=c++17 -O1 -I <bleak repo> m2init_harness.cpp -o m2init_harness
//   m2init_harness FILE.m2 [FILE.m2 ...]        (each FILE's skin is FILE without .m2 + "00.skin")
//
// Layouts come from Engine/Source/Model2/M2Data.h (included, not copied). The M2Init templates below are copied
// from Engine/Source/Model2/M2Shared.cpp (138-276, 692-709, 791-809, 1263-1500, 1541-1555); the checks after them
// restate, line by line, what CM2Shared::Initialize / FinishLoadingSkinProfile / InitializeSkinProfile /
// SetIndices / SubstituteSimpleShaders (M2Shared.cpp), CM2SceneRender::SetupTextures (CM2SceneRender.cpp:95-130),
// CM2Model::InitializeLoaded's particle setup (M2Model.cpp:7281-7530), FindSequenceIndex (M2Model.cpp:1154), the
// particle part-track sampling (ParticleSystem2.cpp:85-188, 672-697) and the transparent-batch depth sort's
// m_boneMatrices[m_centerBoneIndex] (M2Scene.cpp:1890-1894) read. Exit code 0 = every model passed.

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "Engine/Source/Model2/M2Data.h"

static uint32_t s_sequenceIndex = 0xFFFFFFFF;
static uint8_t* s_sequenceData = nullptr;

// ------------------------------------------------------------------------- copied from M2Shared.cpp:138-276

template <class T>
int32_t M2Init(uint8_t* base, uint32_t size, const M2Data& data, M2Array<T>& array) {
    if (s_sequenceIndex == 0xFFFFFFFF) {
        if (array.m_offset > size || array.m_offset + sizeof(T) * array.m_count > size) {
            return 0;
        }

        array.Relocate(base);
    }

    return 1;
}

template <class T>
int32_t M2Init(uint8_t* base, uint32_t size, const M2Data& data, M2Array<M2Array<T> >& array) {
    if (s_sequenceIndex == 0xFFFFFFFF) {
        if (array.m_offset > size || array.m_offset + sizeof(M2Array<T>) * array.m_count > size) {
            return 0;
        }

        array.Relocate(base);
    }

    for (uint32_t i = 0; i < array.m_count; i++) {
        if (!M2Init(base, size, data, array[i])) {
            return 0;
        }
    }

    return 1;
}

int32_t M2Init(uint8_t* base, uint32_t size, const M2Data& data, M2TrackBase& track) {
    if (s_sequenceIndex == 0xFFFFFFFF) {
        if (track.m_loopIndex == 0xFFFF) {
            track.m_sequenceTimes.Relocate(base);

            for (uint32_t i = 0; i < track.m_sequenceTimes.m_count; i++) {
                if (data.m_sequences[i].m_flags & 0x20) {
                    track.m_sequenceTimes[i].Relocate(base);
                }
            }
        } else if (!M2Init(base, size, data, track.m_sequenceTimes)) {
            return 0;
        }
    } else if (s_sequenceIndex < track.m_sequenceTimes.m_count) {
        track.m_sequenceTimes[s_sequenceIndex].Relocate(s_sequenceData);
    }

    return 1;
}

template <class T>
int32_t M2Init(uint8_t* base, uint32_t size, const M2Data& data, M2Track<T>& track) {
    if (s_sequenceIndex == 0xFFFFFFFF) {
        if (track.m_loopIndex == 0xFFFF) {
            track.m_sequenceTimes.Relocate(base);

            for (uint32_t i = 0; i < track.m_sequenceTimes.m_count; i++) {
                if (data.m_sequences[i].m_flags & 0x20) {
                    track.m_sequenceTimes[i].Relocate(base);
                }
            }
        } else if (!M2Init(base, size, data, track.m_sequenceTimes)) {
            return 0;
        }

        if (track.m_loopIndex == 0xFFFF) {
            track.m_sequenceKeys.Relocate(base);

            for (uint32_t i = 0; i < track.m_sequenceTimes.m_count; i++) {
                if (data.m_sequences[i].m_flags & 0x20) {
                    track.m_sequenceKeys[i].Relocate(base);
                }
            }
        } else if (!M2Init(base, size, data, track.m_sequenceKeys)) {
            return 0;
        }
    } else {
        if (s_sequenceIndex < track.m_sequenceTimes.m_count) {
            track.m_sequenceTimes[s_sequenceIndex].Relocate(s_sequenceData);
        }

        if (s_sequenceIndex < track.m_sequenceKeys.m_count) {
            track.m_sequenceKeys[s_sequenceIndex].Relocate(s_sequenceData);
        }
    }

    return 1;
}

template <>
int32_t M2Init<M2Sequence>(uint8_t* base, uint32_t size, const M2Data& data, M2Array<M2Sequence>& array) {
    if (s_sequenceIndex == 0xFFFFFFFF) {
        if (array.m_offset > size || array.m_offset + sizeof(M2Sequence) * array.m_count > size) {
            return 0;
        }

        array.Relocate(base);
    }

    for (uint32_t i = 0; i < array.m_count; i++) {
        M2Sequence* sequence = &array[i];

        if (sequence->m_flags & 1) {
            sequence->m_flags |= 0x80;
        }

        switch (sequence->m_id) {
            case 0: case 4: case 5: case 13: case 41: case 42: case 43: case 44: case 45: case 69: case 119:
            case 120: case 143: case 223:
                sequence->m_flags &= ~1u;
                break;
            default:
                break;
        }
    }

    return 1;
}

// ---------------------------------------------------------------- copied from M2Shared.cpp:692-709, 791-809

template <>
int32_t M2Init<M2Texture>(uint8_t* base, uint32_t size, const M2Data& data, M2Array<M2Texture>& array) {
    if (s_sequenceIndex == 0xFFFFFFFF) {
        if (array.m_offset > size || array.m_offset + sizeof(M2Texture) * array.m_count > size) {
            return 0;
        }

        array.Relocate(base);
    }

    for (uint32_t i = 0; i < array.m_count; i++) {
        if (!M2Init(base, size, data, array[i].m_filename)) {
            return 0;
        }
    }

    return 1;
}

template <>
int32_t M2Init<M2Event>(uint8_t* base, uint32_t size, const M2Data& data, M2Array<M2Event>& array) {
    if (s_sequenceIndex == 0xFFFFFFFF) {
        if (array.m_offset > size || array.m_offset + sizeof(M2Event) * array.m_count > size) {
            return 0;
        }

        array.Relocate(base);
    }

    for (uint32_t i = 0; i < array.m_count; i++) {
        if (!M2Init(base, size, data, array[i].m_enabled)) {
            return 0;
        }
    }

    return 1;
}

// ------------------------------------------------------------------------- copied from M2Shared.cpp:1263-1500

#define M2INIT_ELEMENTS(TYPE, BODY)                                                                          \
    template <>                                                                                             \
    int32_t M2Init<TYPE>(uint8_t* base, uint32_t size, const M2Data& data, M2Array<TYPE>& array) {          \
        if (s_sequenceIndex == 0xFFFFFFFF) {                                                                \
            if (array.m_offset > size || array.m_offset + sizeof(TYPE) * array.m_count > size) {            \
                return 0;                                                                                   \
            }                                                                                               \
            array.Relocate(base);                                                                           \
        }                                                                                                   \
        for (uint32_t i = 0; i < array.m_count; i++) {                                                      \
            TYPE* e = &array[i];                                                                            \
            (void)e;                                                                                        \
            if (!(BODY)) {                                                                                  \
                return 0;                                                                                   \
            }                                                                                               \
        }                                                                                                   \
        return 1;                                                                                           \
    }

M2INIT_ELEMENTS(M2Color, M2Init(base, size, data, e->m_color) && M2Init(base, size, data, e->m_alpha))
M2INIT_ELEMENTS(M2TextureWeight, M2Init(base, size, data, e->m_weight))
M2INIT_ELEMENTS(M2CompBone, M2Init(base, size, data, e->m_translationTrack) && M2Init(base, size, data, e->m_rotationTrack) && M2Init(base, size, data, e->m_scaleTrack))
M2INIT_ELEMENTS(M2TextureTransform, M2Init(base, size, data, e->m_translation) && M2Init(base, size, data, e->m_rotation) && M2Init(base, size, data, e->m_scaling))
M2INIT_ELEMENTS(M2Attachment, M2Init(base, size, data, e->m_animateAttached))
M2INIT_ELEMENTS(M2Light, M2Init(base, size, data, e->m_ambientColor) && M2Init(base, size, data, e->m_ambientIntensity) && M2Init(base, size, data, e->m_diffuseColor) && M2Init(base, size, data, e->m_diffuseIntensity) && M2Init(base, size, data, e->m_attenuationStart) && M2Init(base, size, data, e->m_attenuationEnd) && M2Init(base, size, data, e->m_visibility))
M2INIT_ELEMENTS(M2Camera, M2Init(base, size, data, e->m_positions) && M2Init(base, size, data, e->m_targetPositions) && M2Init(base, size, data, e->m_roll))
M2INIT_ELEMENTS(M2Ribbon, M2Init(base, size, data, e->m_textureIndices) && M2Init(base, size, data, e->m_materialIndices) && M2Init(base, size, data, e->m_colorTrack) && M2Init(base, size, data, e->m_alphaTrack) && M2Init(base, size, data, e->m_heightAboveTrack) && M2Init(base, size, data, e->m_heightBelowTrack) && M2Init(base, size, data, e->m_textureSlotTrack) && M2Init(base, size, data, e->m_visibilityTrack))

int32_t M2Init(uint8_t* base, uint32_t size, const M2Data& data, M2Particle& particle) {
    return M2Init(base, size, data, particle.m_geometryMdl) && M2Init(base, size, data, particle.m_recursionMdl) && M2Init(base, size, data, particle.m_speedTrack) && M2Init(base, size, data, particle.m_variationTrack) && M2Init(base, size, data, particle.m_latitudeTrack) && M2Init(base, size, data, particle.m_longitudeTrack) && M2Init(base, size, data, particle.m_gravityTrack) && M2Init(base, size, data, particle.m_lifeTrack) && M2Init(base, size, data, particle.m_emissionRateTrack) && M2Init(base, size, data, particle.m_widthTrack) && M2Init(base, size, data, particle.m_lengthTrack) && M2Init(base, size, data, particle.m_zsourceTrack) && M2Init(base, size, data, particle.m_colorTrack.m_times) && M2Init(base, size, data, particle.m_colorTrack.m_values) && M2Init(base, size, data, particle.m_alphaTrack.m_times) && M2Init(base, size, data, particle.m_alphaTrack.m_values) && M2Init(base, size, data, particle.m_scaleTrack.m_times) && M2Init(base, size, data, particle.m_scaleTrack.m_values) && M2Init(base, size, data, particle.m_headCellTrack.m_times) && M2Init(base, size, data, particle.m_headCellTrack.m_values) && M2Init(base, size, data, particle.m_tailCellTrack.m_times) && M2Init(base, size, data, particle.m_tailCellTrack.m_values) && M2Init(base, size, data, particle.m_spline) && M2Init(base, size, data, particle.m_visibilityTrack);
}

M2INIT_ELEMENTS(M2Particle, M2Init(base, size, data, *e))

// ------------------------------------------------------------------------- copied from M2Shared.cpp:1541-1555

int32_t M2Init(uint8_t* base, uint32_t size, M2Data& data) {
    if (reinterpret_cast<uint8_t*>(&data) < base || reinterpret_cast<uint8_t*>(&data + 1) > base + size) {
        return 0;
    }

    if (data.m_magic != 0x3032444D) {
        return 0;
    }

    if (data.m_version < 0x108 || data.m_version > 0x108) {
        return 0;
    }

    return M2Init(base, size, data, data.m_name) && M2Init(base, size, data, data.m_loops) && M2Init(base, size, data, data.m_sequences) && M2Init(base, size, data, data.m_sequenceIdxHashById) && M2Init(base, size, data, data.m_bones) && M2Init(base, size, data, data.m_boneIndicesById) && M2Init(base, size, data, data.m_vertices) && M2Init(base, size, data, data.m_colors) && M2Init(base, size, data, data.m_textures) && M2Init(base, size, data, data.m_textureWeights) && M2Init(base, size, data, data.m_textureTransforms) && M2Init(base, size, data, data.m_textureIndicesById) && M2Init(base, size, data, data.m_materials) && M2Init(base, size, data, data.m_boneCombos) && M2Init(base, size, data, data.m_textureCombos) && M2Init(base, size, data, data.m_textureCoordCombos) && M2Init(base, size, data, data.m_textureWeightCombos) && M2Init(base, size, data, data.m_textureTransformCombos) && M2Init(base, size, data, data.m_collisionIndices) && M2Init(base, size, data, data.m_collisionPositions) && M2Init(base, size, data, data.m_collisionFaceNormals) && M2Init(base, size, data, data.m_attachments) && M2Init(base, size, data, data.m_attachmentIndicesById) && M2Init(base, size, data, data.m_events) && M2Init(base, size, data, data.m_lights) && M2Init(base, size, data, data.m_cameras) && M2Init(base, size, data, data.m_cameraIndicesById) && M2Init(base, size, data, data.m_ribbons) && M2Init(base, size, data, data.m_particles) && (!(data.m_flags & 8) || M2Init(base, size, data, data.m_textureCombinerCombos));
}

// ------------------------------------------------------------------------------------- the client's walks

static int g_failures = 0;
static const char* g_file = "";

#define FAIL(...)                                    \
    do {                                             \
        std::printf("FAIL %s: ", g_file);            \
        std::printf(__VA_ARGS__);                    \
        std::printf("\n");                           \
        g_failures++;                                \
    } while (0)

static std::vector<uint8_t> ReadFile(const std::string& path, bool& ok) {
    std::vector<uint8_t> out;
    FILE* f = std::fopen(path.c_str(), "rb");
    ok = f != nullptr;
    if (!f) {
        return out;
    }
    std::fseek(f, 0, SEEK_END);
    long n = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    out.resize(static_cast<size_t>(n));
    ok = std::fread(out.data(), 1, out.size(), f) == out.size();
    std::fclose(f);
    return out;
}

static uint8_t* Aligned(const std::vector<uint8_t>& bytes) {
    // SIMD::AllocA16 in the client; the file buffer is 16-byte aligned
    void* p = nullptr;
    if (posix_memalign(&p, 16, bytes.size() + 16) != 0) {
        return nullptr;
    }
    std::memcpy(p, bytes.data(), bytes.size());
    return static_cast<uint8_t*>(p);
}

template <class T>
static bool InRange(const M2Array<T>& a, uint32_t index) {
    return index < a.m_count;
}

static const uint32_t s_skinProfileBoneCounts[4] = { 256, 64, 53, 21 };  // M2Shared.cpp:31

template <class T>
static void CheckTrack(const M2Data* data, const M2Track<T>& track, const char* what) {
    // CM2Model::FindKey (M2Model.cpp:2330-2350)
    if (!track.m_sequenceTimes.m_count) {
        return;
    }
    if (track.m_loopIndex != 0xFFFF && track.m_loopIndex >= data->m_loops.m_count) {
        FAIL("%s: FindKey reads m_loops[%u] of %u", what, track.m_loopIndex, data->m_loops.m_count);
    }
    if (track.m_sequenceTimes.m_count > data->m_sequences.m_count) {
        FAIL("%s: %u time arrays for %u sequences (M2Init indexed m_sequences out of range)", what,
             track.m_sequenceTimes.m_count, data->m_sequences.m_count);
    }
}

static bool CheckModel(const std::string& m2path) {
    g_file = m2path.c_str();
    int before = g_failures;
    bool ok = false;
    std::vector<uint8_t> bytes = ReadFile(m2path, ok);
    if (!ok) {
        FAIL("cannot read the file");
        return false;
    }
    uint8_t* base = Aligned(bytes);
    uint32_t size = static_cast<uint32_t>(bytes.size());
    if (size < sizeof(M2Data)) {
        FAIL("file shorter than M2Data (0x%zx)", sizeof(M2Data));
        return false;
    }
    M2Data* data = reinterpret_cast<M2Data*>(base);

    // CM2Shared::FinishLoading (M2Shared.cpp:1737-1771)
    if (!M2Init(base, size, *data)) {
        FAIL("M2Init failed: \"Corrupt model data\"");
        return false;
    }
    data->m_flags &= ~0x60u;

    // CM2Shared::Initialize (M2Shared.cpp:1664-1734): skin profile, textures
    uint32_t profile = 0xFFFFFFFF;
    for (uint32_t maxBones : { 256u, 64u }) {  // without shaders; with a 256-constant vertex shader device
        profile = 0xFFFFFFFF;
        if (data->m_numSkinProfiles == 0 || data->m_numSkinProfiles > 4) {
            FAIL("numSkinProfiles %u: s_skinProfileBoneCounts[4 - n + i] is out of range", data->m_numSkinProfiles);
            return false;
        }
        for (uint32_t i = 0; i < data->m_numSkinProfiles; i++) {
            if (s_skinProfileBoneCounts[4 - data->m_numSkinProfiles + i] <= maxBones) {
                profile = i;
                break;
            }
        }
        if (profile == 0xFFFFFFFF) {
            FAIL("\"Failed to choose skin profile\" (maxBones %u)", maxBones);
            return false;
        }
    }
    for (uint32_t i = 0; i < data->m_textures.m_count; i++) {
        M2Texture& t = data->m_textures[i];
        if (t.m_type == 0 && t.m_filename.m_count <= 1) {
            FAIL("texture %u has no file name (drawn solid white)", i);
        }
        if (t.m_filename.m_count && t.m_filename.Data()[t.m_filename.m_count - 1] != '\0') {
            FAIL("texture %u file name is not NUL terminated (TextureCreate reads past it)", i);
        }
    }

    // FinishLoadingSkinProfile (M2Shared.cpp:1308-1340): MakeSkinFileName + M2Init on the skin arrays
    std::string skinPath = m2path.substr(0, m2path.size() - 3);
    char suffix[16];
    std::snprintf(suffix, sizeof(suffix), "%02u.skin", profile);
    skinPath += suffix;
    std::vector<uint8_t> skinBytes = ReadFile(skinPath, ok);
    if (!ok) {
        FAIL("\"Model2: File not found: %s\"", skinPath.c_str());
        return false;
    }
    uint8_t* sbase = Aligned(skinBytes);
    uint32_t ssize = static_cast<uint32_t>(skinBytes.size());
    if (ssize < sizeof(M2SkinProfile)) {
        FAIL("skin shorter than M2SkinProfile");
        return false;
    }
    M2SkinProfile* skin = reinterpret_cast<M2SkinProfile*>(sbase);
    if (!M2Init(sbase, ssize, *data, skin->m_vertices) || !M2Init(sbase, ssize, *data, skin->m_indices) || !M2Init(sbase, ssize, *data, skin->m_bones) || !M2Init(sbase, ssize, *data, skin->m_skinSections) || !M2Init(sbase, ssize, *data, skin->m_batches)) {
        FAIL("\"Corrupt skin profile data\"");
        return false;
    }

    // InitializeSkinProfile (M2Shared.cpp:1137-1262)
    if (skin->m_boneCountMax < 1) {
        FAIL("boneCountMax 0");
    }
    for (uint32_t i = 0; i < skin->m_skinSections.m_count; i++) {
        M2SkinSection& s = skin->m_skinSections[i];
        if (s.m_boneCount == 0) {
            FAIL("section %u boneCount 0: m_boneCountMax / m_boneCount divides by zero", i);
            continue;
        }
        if (s.m_skinSectionId >> 16) {
            FAIL("section %u skinSectionId high bits 0x%X (read as a wide index start)", i, s.m_skinSectionId >> 16);
        }
        // CM2Scene depth-sorts transparent (or fading) batches through
        // model->m_boneMatrices[section->m_centerBoneIndex] (M2Scene.cpp:1890, 1894), one matrix per bone
        // (M2Model.cpp:7084), with no bound check
        if (s.m_centerBoneIndex >= data->m_bones.m_count) {
            FAIL("section %u centerBoneIndex %u: m_boneMatrices[%u] of %u", i, s.m_centerBoneIndex,
                 s.m_centerBoneIndex, data->m_bones.m_count);
        }
        uint32_t end = s.m_vertexStart + s.m_vertexCount;
        if (end > skin->m_vertices.m_count) {
            FAIL("section %u vertices %u..%u past %u skin vertices", i, s.m_vertexStart, end, skin->m_vertices.m_count);
            continue;
        }
        if (skin->m_bones.m_count < end) {
            FAIL("section %u reads skin bones[%u] of %u", i, end - 1, skin->m_bones.m_count);
            continue;
        }
        for (uint32_t j = s.m_vertexStart; j < end; j++) {
            if (!InRange(data->m_vertices, skin->m_vertices[j])) {
                FAIL("skin vertex %u -> model vertex %u of %u", j, skin->m_vertices[j], data->m_vertices.m_count);
                break;
            }
            for (uint32_t k = 0; k < s.m_boneInfluences && k < 4; k++) {
                uint32_t combo = s.m_boneComboIndex + skin->m_bones[j].b[k];
                if (!InRange(data->m_boneCombos, combo)) {
                    FAIL("section %u vertex %u: boneCombos[%u] of %u", i, j, combo, data->m_boneCombos.m_count);
                    j = end;
                    break;
                }
                if (data->m_boneCombos[combo] >= data->m_bones.m_count) {
                    FAIL("boneCombos[%u] = %u past %u bones", combo, data->m_boneCombos[combo], data->m_bones.m_count);
                    j = end;
                    break;
                }
            }
        }
        // SetIndices (M2Shared.cpp:340-388): indices[j] - vertexStart for a non-shared buffer
        uint32_t start = s.m_indexStart;  // M2SkinSectionIndexStart with level 0
        if (start + s.m_indexCount > skin->m_indices.m_count) {
            FAIL("section %u indices %u..%u past %u", i, start, start + s.m_indexCount, skin->m_indices.m_count);
            continue;
        }
        for (uint32_t j = 0; j < s.m_indexCount; j++) {
            uint16_t v = skin->m_indices[start + j];
            uint16_t local = static_cast<uint16_t>(v - s.m_vertexStart);
            if (local >= s.m_vertexCount) {
                FAIL("section %u index %u = %u leaves its vertex range %u+%u", i, start + j, v, s.m_vertexStart,
                     s.m_vertexCount);
                break;
            }
        }
    }
    if (skin->m_indices.m_count % 3) {
        FAIL("%u indices: not a triangle list", skin->m_indices.m_count);
    }

    // SubstituteSimpleShaders (M2Shared.cpp:638-690), GetEffect, CM2SceneRender::SetupTextures
    for (uint32_t i = 0; i < skin->m_batches.m_count; i++) {
        M2Batch& b = skin->m_batches[i];
        if (b.m_skinSectionIndex >= skin->m_skinSections.m_count) {
            FAIL("batch %u section %u of %u", i, b.m_skinSectionIndex, skin->m_skinSections.m_count);
        }
        if (!InRange(data->m_materials, b.m_materialIndex)) {
            FAIL("batch %u m_materials[%u] of %u", i, b.m_materialIndex, data->m_materials.m_count);
            continue;
        }
        if (data->m_materials[b.m_materialIndex].m_blendMode > 6) {
            FAIL("material %u blendMode %u: s_blendModes has 7 entries", b.m_materialIndex,
                 data->m_materials[b.m_materialIndex].m_blendMode);
        }
        uint32_t tcount = b.m_textureCount ? b.m_textureCount : 1;
        for (uint32_t k = 0; k < tcount; k++) {
            if (!InRange(data->m_textureCoordCombos, b.m_textureCoordComboIndex + k)) {
                FAIL("batch %u textureCoordCombos[%u] of %u", i, b.m_textureCoordComboIndex + k,
                     data->m_textureCoordCombos.m_count);
            }
            if (!InRange(data->m_textureCombos, b.m_textureComboIndex + k)) {
                FAIL("batch %u textureCombos[%u] of %u", i, b.m_textureComboIndex + k, data->m_textureCombos.m_count);
            } else if (data->m_textureCombos[b.m_textureComboIndex + k] >= data->m_textures.m_count) {
                FAIL("batch %u texture %u of %u (no texture bound)", i, data->m_textureCombos[b.m_textureComboIndex + k],
                     data->m_textures.m_count);
            }
            if (!InRange(data->m_textureTransformCombos, b.m_textureTransformComboIndex + k)) {
                FAIL("batch %u textureTransformCombos[%u] of %u", i, b.m_textureTransformComboIndex + k,
                     data->m_textureTransformCombos.m_count);
            }
        }
        if (!InRange(data->m_textureWeightCombos, b.m_textureWeightComboIndex)) {
            FAIL("batch %u textureWeightCombos[%u] of %u", i, b.m_textureWeightComboIndex,
                 data->m_textureWeightCombos.m_count);
        } else {
            uint16_t w = data->m_textureWeightCombos[b.m_textureWeightComboIndex];
            if (!InRange(data->m_textureWeights, w)) {
                FAIL("batch %u texture weight %u of %u", i, w, data->m_textureWeights.m_count);
            } else {
                M2Track<fixed16>& t = data->m_textureWeights[w].m_weight;
                if (!t.m_sequenceKeys.m_count || !t.m_sequenceKeys[0].m_count) {
                    FAIL("batch %u texture weight %u has no key: invisible", i, w);
                } else if (t.m_sequenceKeys[0][0].m_value == 0) {
                    FAIL("batch %u texture weight %u is 0: invisible", i, w);
                }
            }
        }
        if (b.m_colorIndex != 0xFFFF && b.m_colorIndex >= data->m_colors.m_count) {
            FAIL("batch %u colour %u of %u", i, b.m_colorIndex, data->m_colors.m_count);
        }
    }

    // CM2Model::FindSequenceIndex (M2Model.cpp:1154-1194) for Stand (0) and every id a GO can ask for
    for (uint32_t id = 0; id < 506; id++) {
        uint32_t hashCount = data->m_sequenceIdxHashById.m_count;
        if (!hashCount) {
            break;
        }
        uint32_t slot = id % hashCount;
        uint32_t index = data->m_sequenceIdxHashById[slot];
        uint32_t steps = 0;
        if (index != 0xFFFF) {
            for (uint32_t step = 1; index < data->m_sequences.m_count && data->m_sequences[index].m_id != id; step++) {
                slot = (slot + step * step) % hashCount;
                index = data->m_sequenceIdxHashById[slot];
                if (index == 0xFFFF) {
                    break;
                }
                if (++steps > 4 * hashCount * hashCount + 16) {
                    FAIL("FindSequenceIndex(%u) never ends (sequenceIdxHashById without a reachable 0xFFFF)", id);
                    id = 506;
                    break;
                }
            }
            if (index != 0xFFFF && index >= data->m_sequences.m_count) {
                FAIL("FindSequenceIndex(%u) reads m_sequences[%u] of %u", id, index, data->m_sequences.m_count);
                break;
            }
        }
    }
    if (!data->m_sequences.m_count) {
        FAIL("no sequences");
    }
    if (!data->m_bones.m_count) {
        FAIL("no bones");
    }

    // tracks read by FindKey
    for (uint32_t i = 0; i < data->m_textureWeights.m_count; i++) {
        CheckTrack(data, data->m_textureWeights[i].m_weight, "texture weight");
    }
    for (uint32_t i = 0; i < data->m_bones.m_count; i++) {
        CheckTrack(data, data->m_bones[i].m_translationTrack, "bone translation");
        CheckTrack(data, data->m_bones[i].m_rotationTrack, "bone rotation");
        CheckTrack(data, data->m_bones[i].m_scaleTrack, "bone scale");
    }

    // CM2Model::InitializeLoaded, particles (M2Model.cpp:7281-7530)
    for (uint32_t i = 0; i < data->m_particles.m_count; i++) {
        M2Particle& p = data->m_particles[i];
        if (p.m_emitterType < 1 || p.m_emitterType > 3) {
            FAIL("particle %u emitterType %u: no emitter is created and the null pointer is used", i, p.m_emitterType);
        }
        M2Track<float>* tracks[] = { &p.m_speedTrack, &p.m_variationTrack, &p.m_latitudeTrack, &p.m_longitudeTrack, &p.m_gravityTrack, &p.m_lifeTrack, &p.m_emissionRateTrack, &p.m_widthTrack, &p.m_lengthTrack, &p.m_zsourceTrack };
        for (M2Track<float>* t : tracks) {
            CheckTrack(data, *t, "particle track");
        }
        // `particleData->m_emissionRateTrack.m_sequenceKeys[0].m_count` (7313)
        if (!p.m_emissionRateTrack.m_sequenceKeys.m_count || !p.m_emissionRateTrack.m_sequenceKeys[0].m_count) {
            FAIL("particle %u emissionRate has no key: the emitter never emits", i);
        }
        if (p.m_textureIndex >= data->m_textures.m_count) {
            FAIL("particle %u m_shared->m_textures[%u] of %u (M2Model.cpp:7470)", i, p.m_textureIndex, data->m_textures.m_count);
        }
        if (p.m_boneIndex >= data->m_bones.m_count) {
            FAIL("particle %u bone %u of %u", i, p.m_boneIndex, data->m_bones.m_count);
        }
        // SetParticleStyle(flags & 0x20000, flags & 0x40000, ...) (7410; ParticleSystem2.cpp:301-332)
        uint32_t verts = ((p.m_flags & 0x20000) ? 4 : 0) + ((p.m_flags & 0x40000) ? 4 : 0);
        if (!verts) {
            FAIL("particle %u flags 0x%X: m_vertsPerParticle 0, the draw divides by it (0x4000 / 0)", i, p.m_flags);
        }
        // SetTextureDimensions (ParticleSystem2.cpp:281-297)
        uint32_t rows = p.m_rows, cols = p.m_cols;
        if ((rows & (rows - 1)) || (cols & (cols - 1)) || !rows || !cols) {
            FAIL("particle %u rows %u cols %u: SetTextureDimensions refuses them", i, rows, cols);
        }
        if (p.m_blendMode > 6) {
            FAIL("particle %u blend %u leaves the material unset", i, p.m_blendMode);
        }
        // InterpolateAllTracks (ParticleSystem2.cpp:672-697) samples colour, alpha and scale for every live
        // particle: one value is used as is, otherwise PartTrackKeys (115-140) takes key indices from the
        // times, and with no times PartTrackSearch (85-112) starts at hi = 0xFFFFFFFF and reads times[0x7FFFFFFF]
        struct { const char* name; uint32_t times; uint32_t values; } parts[] = {
            { "colour", p.m_colorTrack.m_times.m_count, p.m_colorTrack.m_values.m_count },
            { "alpha", p.m_alphaTrack.m_times.m_count, p.m_alphaTrack.m_values.m_count },
            { "scale", p.m_scaleTrack.m_times.m_count, p.m_scaleTrack.m_values.m_count },
        };
        for (auto& t : parts) {
            if (!t.values) {
                FAIL("particle %u %s track %u times, %u values: %s", i, t.name, t.times, t.values,
                     t.times ? "PartTrackKeys indexes past the values" : "PartTrackSearch reads times[0x7FFFFFFF]");
            } else if (t.values != 1 && (t.times < 2 || t.values < t.times)) {
                FAIL("particle %u %s track %u times, %u values: PartTrackKeys indexes past them", i, t.name, t.times,
                     t.values);
            }
        }
        // head/tail cells are sampled only when they have times (689-697), through PartTrackSample<uint16_t>
        // (178-188)
        struct { const char* name; uint32_t times; uint32_t values; } cells[] = {
            { "head cell", p.m_headCellTrack.m_times.m_count, p.m_headCellTrack.m_values.m_count },
            { "tail cell", p.m_tailCellTrack.m_times.m_count, p.m_tailCellTrack.m_values.m_count },
        };
        for (auto& t : cells) {
            if (t.times && t.values != 1 && (t.times < 2 || t.values < t.times)) {
                FAIL("particle %u %s track %u times, %u values: PartTrackSample<uint16_t> reads past the values", i,
                     t.name, t.times, t.values);
            }
        }
    }

    bool passed = g_failures == before;
    if (passed) {
        std::printf("OK %s: %u vertices, %u indices, %u sections, %u batches, %u textures, %u particles\n", g_file,
                    data->m_vertices.m_count, skin->m_indices.m_count, skin->m_skinSections.m_count,
                    skin->m_batches.m_count, data->m_textures.m_count, data->m_particles.m_count);
    }
    std::free(base);
    std::free(sbase);
    return passed;
}

int main(int argc, char** argv) {
    static_assert(sizeof(M2Data) == 0x138, "M2Data");
    static_assert(sizeof(M2Particle) == 0x1DC, "M2Particle");
    static_assert(sizeof(M2Vertex) == 0x30, "M2Vertex");
    static_assert(sizeof(M2SkinProfile) == 0x30, "M2SkinProfile");
    if (argc < 2) {
        std::printf("usage: m2init_harness FILE.m2 [...]\n");
        return 2;
    }
    for (int i = 1; i < argc; i++) {
        CheckModel(argv[i]);
    }
    return g_failures ? 1 : 0;
}
