#ifndef ENGINE_SOURCE_MODEL2_M2GLOW_H
#define ENGINE_SOURCE_MODEL2_M2GLOW_H

#include <cmath>
#include <cstdint>

// BLEAKHOLD(glow): the rules of the glow pass for glowing marks.
//
// A model with a glow texture (CM2Model::SetGlowTexture; CCharacterComponent bakes it from the `_Glow` files of the
// CharSections textures it pastes, with armour and hair pasted black over it) draws each of its skin batches (texture
// type 1, the baked CharacterBaseSkin) a second time: the glow texture in place of the skin, unlit, additive (M2 blend
// 4, the blend of the eye glow), without writing depth and pulled a little towards the camera so it never loses the
// depth test against the skin it lies on. Black texels add nothing, so only the marks show, at night as by day, and
// what they add to the frame is what BleakFx's bloom picks up (it thresholds the frame's brightest channel).
//
// CM2Scene::Animate adds the glow elements (M2Element flag kElementFlag) next to the skin elements, into the
// transparent passes; CM2Scene::ComputeElementShaders and CM2SceneRender::DrawBatch give them one of the fixed glow
// materials, CM2SceneRender::SetupTextures binds the glow texture. A model without a glow texture costs one null check
// per frame. Self-contained (no engine headers) so that Tools/GlowDraw/tests can build it on its own.

namespace M2Glow {

// M2Element::m_flags bit of a glow element. The stock bits: 0x1 depth-only copy of a depth-sorted batch, 0x2 clipped at
// the water plane, 0x4 drawn from the model's optimized geometry.
const uint32_t kElementFlag = 0x8;

// ---------------------------------------------------------------------------------------------------- materials

// M2Material::m_flags bits (as CM2SceneRender::SetupLighting and SetupMaterial read them).
const uint16_t kMaterialUnlit = 0x1;
const uint16_t kMaterialUnfogged = 0x2;
const uint16_t kMaterialTwoSided = 0x4;
const uint16_t kMaterialNoDepthTest = 0x8;
const uint16_t kMaterialNoDepthWrite = 0x10;

// The base material's bits a glow material keeps, so the glow is fogged, culled and depth tested like the skin under
// it.
const uint16_t kKeptMaterialFlags = kMaterialUnfogged | kMaterialTwoSided | kMaterialNoDepthTest;

// M2 blend mode 4: GxBlend_Add, source x source alpha + destination.
const uint16_t kBlendMode = 4;

// The glow materials are fixed objects (the renderer's state cache compares material pointers): one for each
// combination of the kept bits.
const uint32_t kMaterialCount = 8;

constexpr uint32_t MaterialSlot(uint16_t baseFlags) {
    return static_cast<uint32_t>(baseFlags & kKeptMaterialFlags) >> 1;
}

constexpr uint16_t MaterialFlags(uint32_t slot) {
    return static_cast<uint16_t>(((slot << 1) & kKeptMaterialFlags) | kMaterialUnlit | kMaterialNoDepthWrite);
}

// ---------------------------------------------------------------------------------------------------- batches

// M2Texture::m_type of the character's baked skin.
const uint32_t kSkinTextureType = 1;
const uint32_t kNoTexture = 0xFFFFFFFF;

struct BatchInfo {
    uint32_t textureType;   // M2Texture::m_type of the batch's first texture, kNoTexture when it has none
    uint16_t textureCount;  // M2Batch::m_textureCount
    uint16_t materialLayer; // M2Batch::m_materialLayer
    uint16_t shader;        // M2Batch::m_shader
    uint16_t baseBlend;     // blend mode of the batch's base material (the layer-0 material)
    bool projected;         // drawn as a projected texture (batch flag 0x4 with a projection callback)
};

// Whether a batch is drawn again with the glow: the skin, sampled once with plain texture coordinates through an
// opaque or modulating combiner (Combiners_Opaque or Combiners_Mod, which give texture x colour), over an opaque or
// alpha-keyed base.
inline bool IsGlowBatch(const BatchInfo& batch) {
    if (batch.projected || batch.textureType != kSkinTextureType || batch.textureCount != 1) {
        return false;
    }

    if (batch.materialLayer != 0 || batch.baseBlend > 1) {
        return false;
    }

    // 0x8000: the fixed combinations of CM2Shared::GetEffect; 0x80: the first texture is sphere mapped.
    if (batch.shader & 0x8080) {
        return false;
    }

    uint32_t combiner = (batch.shader >> 4) & 7;
    return combiner == 0 || combiner == 1;
}

// ---------------------------------------------------------------------------------------------------- sections

// The character texture's sections (CCharacterComponent::s_sectionInfoRaw) at the 512 layout: arm upper, arm lower,
// hand, torso upper, torso lower, leg upper, leg lower, foot, head upper, head lower. SetGlowTexture takes a mask of
// the sections that hold any glow (bit i: section i); a batch whose texture coordinates touch none of them is not
// drawn again.
const uint32_t kSectionCount = 10;
const uint32_t kAllSections = (1u << kSectionCount) - 1;
const float kLayoutSize = 512.0f;

struct SectionRect {
    uint16_t x;
    uint16_t y;
    uint16_t width;
    uint16_t height;
};

const SectionRect kSections[kSectionCount] = {
    { 0, 0, 256, 128 },
    { 0, 128, 256, 128 },
    { 0, 256, 256, 64 },
    { 256, 0, 256, 128 },
    { 256, 128, 256, 64 },
    { 256, 192, 256, 128 },
    { 256, 320, 256, 128 },
    { 256, 448, 256, 64 },
    { 0, 320, 256, 64 },
    { 0, 384, 256, 128 },
};

// How far texture coordinates may stray outside 0..1 and still count as inside (rounding in exported models).
const float kUvSlack = 1.0f / 256.0f;

// Half a texel at 512: coordinates on a section's border do not count for its neighbour.
const float kUvEdge = 0.5f / kLayoutSize;

// The bounds of a batch's texture coordinates, and the sections they touch.
struct UvBounds {
    float minU = 0.0f;
    float minV = 0.0f;
    float maxU = 0.0f;
    float maxV = 0.0f;
    uint32_t count = 0;
    bool outside = false;

    void Add(float u, float v) {
        // Tiling coordinates, NaN or infinity: the batch may sample anywhere.
        if (!(u >= -kUvSlack && u <= 1.0f + kUvSlack && v >= -kUvSlack && v <= 1.0f + kUvSlack)) {
            this->outside = true;
            return;
        }

        if (!this->count) {
            this->minU = this->maxU = u;
            this->minV = this->maxV = v;
        } else {
            this->minU = u < this->minU ? u : this->minU;
            this->maxU = u > this->maxU ? u : this->maxU;
            this->minV = v < this->minV ? v : this->minV;
            this->maxV = v > this->maxV ? v : this->maxV;
        }

        this->count++;
    }

    // No coordinates: no sections. Coordinates outside the texture, or bounds so thin they touch no section's
    // inside: all of them (always drawing is the safe side).
    uint32_t Sections() const {
        if (this->outside) {
            return kAllSections;
        }

        if (!this->count) {
            return 0;
        }

        uint32_t mask = 0;

        for (uint32_t i = 0; i < kSectionCount; i++) {
            const SectionRect& rect = kSections[i];
            float x0 = rect.x / kLayoutSize;
            float y0 = rect.y / kLayoutSize;
            float x1 = (rect.x + rect.width) / kLayoutSize;
            float y1 = (rect.y + rect.height) / kLayoutSize;

            bool acrossU = this->minU < x1 - kUvEdge && this->maxU > x0 + kUvEdge;
            bool acrossV = this->minV < y1 - kUvEdge && this->maxV > y0 + kUvEdge;

            if (acrossU && acrossV) {
                mask |= 1u << i;
            }
        }

        return mask ? mask : kAllSections;
    }
};

// ---------------------------------------------------------------------------------------------------- strength

// bleakGlowStrength when the CVar does not exist. The strength scales the glow element's alpha, which GxBlend_Add
// multiplies the glow by, so it ends at 1 (full glow texture).
const float kDefaultStrength = 1.0f;

// The glow fades out with the model's distance from the camera (CM2Model::m_scaleSq is its square, in yards): full up
// to kFadeStartYards, none from kFadeEndYards. Past that the marks are a few pixels and fog takes them anyway.
const float kFadeStartYards = 45.0f;
const float kFadeEndYards = 60.0f;

// The stock batch loop's cut-off for batches too faint to draw.
const float kMinAlpha = 0.000099999997f;

// The strength the draw uses: 0 when bleakGlow is 0, else bleakGlowStrength within 0..1 (the default when it is not
// a number).
inline float Strength(int32_t enabled, float strength) {
    if (!enabled) {
        return 0.0f;
    }

    if (!std::isfinite(strength)) {
        return kDefaultStrength;
    }

    return strength < 0.0f ? 0.0f : (strength > 1.0f ? 1.0f : strength);
}

inline float DistanceFade(float distanceSq) {
    if (!(distanceSq >= 0.0f)) {
        return 0.0f;
    }

    if (distanceSq <= kFadeStartYards * kFadeStartYards) {
        return 1.0f;
    }

    if (distanceSq >= kFadeEndYards * kFadeEndYards) {
        return 0.0f;
    }

    return (kFadeEndYards - std::sqrt(distanceSq)) / (kFadeEndYards - kFadeStartYards);
}

// The factor a model's glow elements take on top of their batch's alpha; below kMinAlpha the model draws no glow.
inline float ModelAlpha(float strength, float distanceSq) {
    return strength * DistanceFade(distanceSq);
}

// ---------------------------------------------------------------------------------------------------- depth

// GxRs_PolygonOffset while a glow element draws. Direct3D 9 takes it as D3DRS_DEPTHBIAS = -value, in depth-buffer
// units (24-bit depth: 1e-6 is about 17 steps): enough to cover the difference between the lit and the unlit vertex
// shader's depth, small enough (about 1 cm at 50 yards with the 0.2 near plane) that armour in front of the skin
// still hides the glow.
const float kDepthBias = 1.0e-6f;

// ---------------------------------------------------------------------------------------------------- model calls

// CM2ModelCall::m_type of the calls a model queues while it loads (the stock ones are 0 to 14).
const uint32_t kCallSetGlowTexture = 0x100;
const uint32_t kCallReplaceTextureAtIndex = 0x101;
const uint32_t kCallReplaceGeosetTexture = 0x102;

// Whether a queued call holds a texture handle in m_args[1], which is closed when the call is dropped or run. Stock:
// only ReplaceTexture (type 0).
inline bool CallHoldsTexture(uint32_t type) {
    return type == 0 || type == kCallSetGlowTexture || type == kCallReplaceTextureAtIndex ||
        type == kCallReplaceGeosetTexture;
}

// ---------------------------------------------------------------------------------------------------- copies

// A copy made by CM2Scene::DuplicateModel (the interface's PlayerModel frames: character pane, inspect, dressing room;
// portraits; and the copies of a copied model's attached children) holds its source only until it has loaded:
// CM2Model::InitializeLoaded copies the source's textures and geoset visibility, then lets go of it (m_model30 =
// nullptr) before the copy is first drawn. InitializeLoaded calls this there, before it lets go: a copy that has no
// glow of its own takes its source's, with a handle of its own (`duplicate`, HandleDuplicate), and does not follow
// the source after that, just as it does not follow its textures. A glow given to the copy itself is a call queued
// while it loaded; those run later in InitializeLoaded and replace this one. Returns whether the copy took it.
template <typename Model, typename Duplicate>
inline bool TakeSourceGlow(Model& copy, const Model* source, Duplicate duplicate) {
    if (!source || copy.m_bleakGlowTexture || !source->m_bleakGlowTexture) {
        return false;
    }

    copy.m_bleakGlowTexture = duplicate(source->m_bleakGlowTexture);
    copy.m_bleakGlowSections = copy.m_bleakGlowTexture ? source->m_bleakGlowSections : 0;
    return copy.m_bleakGlowTexture != nullptr;
}

// ---------------------------------------------------------------------------------------------------- geoset textures

// One texture unit of one batch: the geoset of the batch's skin section and the texture index (M2Data::m_textures) the
// unit samples, kNoTexture when it is out of range.
struct BatchTexture {
    uint32_t geoset;
    uint32_t texture;
};

// The texture indices that geoset `geoset` uses and no other geoset does (ReplaceGeosetTexture changes only those, so
// the swap never reaches other parts of the model). Writes up to outMax distinct indices in order of first use and
// returns how many it wrote.
inline uint32_t GeosetOnlyTextures(const BatchTexture* items, uint32_t count, uint32_t geoset, uint32_t* out,
    uint32_t outMax) {
    uint32_t written = 0;

    for (uint32_t i = 0; i < count && written < outMax; i++) {
        uint32_t texture = items[i].texture;

        if (items[i].geoset != geoset || texture == kNoTexture) {
            continue;
        }

        bool seen = false;

        for (uint32_t j = 0; j < written && !seen; j++) {
            seen = out[j] == texture;
        }

        bool shared = false;

        for (uint32_t j = 0; j < count && !shared; j++) {
            shared = items[j].texture == texture && items[j].geoset != geoset;
        }

        if (!seen && !shared) {
            out[written++] = texture;
        }
    }

    return written;
}

} // namespace M2Glow

#endif
