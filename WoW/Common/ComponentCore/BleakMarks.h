#ifndef WOW_COMMON_COMPONENTCORE_BLEAKMARKS_H
#define WOW_COMMON_COMPONENTCORE_BLEAKMARKS_H

#include <cmath>
#include <cstddef>
#include <cstdint>

// BLEAKHOLD(glow): glowing marks and eyes, the parts that need no game code, so that
// Tools/MarkForge/tests/test_marks_core.cpp can test them with the host compiler. CharacterComponent.cpp uses them.
//
// The data side is the "Bleakhold appearance data contract" in Tools/RaceForge/README.md:
// - features byte = look * B + base (look 0 none, 1-12 = 4 designs x 3 colours), face byte = base + 40 * eye;
// - a features row's third texture is the mark: a 512 x 512 palettized atlas of all ten sections, pasted after the
//   face and underwear and before the features, scalp and items; `<mark>_Glow.blp` beside it is its emitted light;
// - a face row's third texture is the eye sprite, drawn on geoset 1703.
//
// The glow bake replays the colour bake's layer list into a second, smaller texture (the pass rule, GlowLayer below)
// and the model draws it a second time, additive and unlit (Engine/Source/Model2/M2Glow.h, the glow-draw side, which
// also reads bleakGlow and bleakGlowStrength and fades the glow out between 45 and 60 yards).
namespace BleakMarks {

// ---- Encodings ----

static const uint32_t kByteMax = 255;
static const uint32_t kEyeStride = 40;          // face = base + 40 * eye
static const uint32_t kEyeCount = 6;            // 0 the race's own, 1-3 race colours, 4 Blood Red, 5 Unholy Green
static const uint32_t kFirstDeathKnightEye = 4; // eyes 4 and 5 are for Death Knights only (flags 0x5)
static const uint32_t kDesignCount = 4;
static const uint32_t kColourCount = 3;
static const uint32_t kLookCount = 1 + kDesignCount * kColourCount; // 13: look 0 is no mark

struct FaceValue {
    uint32_t base; // the package's face variation, 0-39
    uint32_t eye;  // 0-5
};

struct FeatureValue {
    uint32_t base;   // the package's feature, 0 .. B-1
    uint32_t look;   // 0 no mark, 1-12
    uint32_t design; // 1-4, 0 without a mark
    uint32_t colour; // 1-3, 0 without a mark
};

inline bool DecodeFace(uint32_t value, FaceValue* out) {
    if (value > kByteMax || value / kEyeStride >= kEyeCount) {
        return false;
    }

    out->base = value % kEyeStride;
    out->eye = value / kEyeStride;
    return true;
}

inline bool EncodeFace(uint32_t base, uint32_t eye, uint32_t* value) {
    if (base >= kEyeStride || eye >= kEyeCount || base + kEyeStride * eye > kByteMax) {
        return false;
    }

    *value = base + kEyeStride * eye;
    return true;
}

// look = 3 * (design - 1) + colour, design and colour from 1.
inline uint32_t LookFor(uint32_t design, uint32_t colour) {
    if (design < 1 || design > kDesignCount || colour < 1 || colour > kColourCount) {
        return 0;
    }

    return kColourCount * (design - 1) + colour;
}

// `baseCount` is B, the race and sex's number of package features (CharacterFacialHairStyles rows before the marks).
inline bool DecodeFeature(uint32_t value, uint32_t baseCount, FeatureValue* out) {
    if (!baseCount || value > kByteMax || value / baseCount >= kLookCount) {
        return false;
    }

    out->base = value % baseCount;
    out->look = value / baseCount;
    out->design = out->look ? (out->look - 1) / kColourCount + 1 : 0;
    out->colour = out->look ? (out->look - 1) % kColourCount + 1 : 0;
    return true;
}

inline bool EncodeFeature(uint32_t base, uint32_t look, uint32_t baseCount, uint32_t* value) {
    if (!baseCount || base >= baseCount || look >= kLookCount) {
        return false;
    }

    uint32_t v = look * baseCount + base;

    if (v > kByteMax) {
        return false;
    }

    *value = v;
    return true;
}

// A CharSections texture name that is set (the DBC gives "" for an empty one).
inline bool HasTexture(const char* name) {
    return name && *name;
}

// ---- Names ----

static const uint32_t kNameMax = 260; // the client's path buffers, terminator included

inline char LowerAscii(char c) {
    return (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : c;
}

// The `_Glow` file of a texture: "X.blp" -> "X_Glow.blp" (the extension in any case), "X" -> "X_Glow". False when
// it does not fit in `outSize` (terminator included), for an empty name, and for a name that is a `_Glow` file
// itself (a glow has no glow).
inline bool GlowName(const char* name, char* out, size_t outSize) {
    if (!name || !*name || !out || !outSize) {
        return false;
    }

    size_t length = 0;

    while (name[length]) {
        length++;
    }

    size_t stem = length;

    if (length >= 4 && name[length - 4] == '.' && LowerAscii(name[length - 3]) == 'b' && LowerAscii(name[length - 2]) == 'l' && LowerAscii(name[length - 1]) == 'p') {
        stem = length - 4;
    }

    static const char kSuffix[] = "_glow";

    if (stem >= 5) {
        bool glow = true;

        for (size_t i = 0; i < 5; i++) {
            if (LowerAscii(name[stem - 5 + i]) != kSuffix[i]) {
                glow = false;
                break;
            }
        }

        if (glow) {
            return false;
        }
    }

    if (length + 5 + 1 > outSize) {
        return false;
    }

    static const char kGlow[] = "_Glow";
    size_t o = 0;

    for (size_t i = 0; i < stem; i++) {
        out[o++] = name[i];
    }

    for (size_t i = 0; i < 5; i++) {
        out[o++] = kGlow[i];
    }

    for (size_t i = stem; i < length; i++) {
        out[o++] = name[i];
    }

    out[o] = '\0';
    return true;
}

// FNV-1a (64 bit) of a file name as the archives compare names: case-insensitive, '/' the same as '\'.
// Never 0 (0 marks an empty NameSet slot).
inline uint64_t NameHash(const char* name) {
    uint64_t hash = 14695981039346656037ull;

    for (const char* c = name; c && *c; c++) {
        char ch = *c == '/' ? '\\' : LowerAscii(*c);
        hash ^= static_cast<uint8_t>(ch);
        hash *= 1099511628211ull;
    }

    return hash ? hash : 1;
}

// A small set of name hashes with one byte each: the `_Glow` exists-cache and the logged-once set. `N` is a power of
// two; when it is three quarters full it forgets everything and starts again (so it never grows and never fails).
template <uint32_t N>
class NameSet {
    public:
    static_assert(N >= 4 && (N & (N - 1)) == 0, "NameSet size must be a power of two");

    NameSet() {
        this->Clear();
    }

    void Clear() {
        for (uint32_t i = 0; i < N; i++) {
            this->m_keys[i] = 0;
            this->m_values[i] = 0;
        }

        this->m_count = 0;
    }

    uint32_t Count() const {
        return this->m_count;
    }

    bool Find(uint64_t key, uint8_t* value) const {
        key = key ? key : 1;

        for (uint32_t i = static_cast<uint32_t>(key) & (N - 1), n = 0; n < N; i = (i + 1) & (N - 1), n++) {
            if (this->m_keys[i] == key) {
                if (value) {
                    *value = this->m_values[i];
                }

                return true;
            }

            if (!this->m_keys[i]) {
                return false;
            }
        }

        return false;
    }

    // Adds or replaces. Returns true when the key was not there before.
    bool Insert(uint64_t key, uint8_t value) {
        key = key ? key : 1;

        if (this->m_count + 1 > N / 4 * 3) {
            this->Clear();
        }

        for (uint32_t i = static_cast<uint32_t>(key) & (N - 1);; i = (i + 1) & (N - 1)) {
            if (this->m_keys[i] == key) {
                this->m_values[i] = value;
                return false;
            }

            if (!this->m_keys[i]) {
                this->m_keys[i] = key;
                this->m_values[i] = value;
                this->m_count++;
                return true;
            }
        }
    }

    private:
    uint64_t m_keys[N];
    uint8_t m_values[N];
    uint32_t m_count;
};

// ---- Texture size and format guards ----

// What the texture cache knows of a loaded BLP (TCTEXTUREINFO plus the colour encoding).
struct TextureFacts {
    uint32_t width;
    uint32_t height;
    uint32_t mipCount;  // the cache's count, always the full chain of the size (TextureCalcMipCount)
    uint32_t alphaBits; // 0, 1, 4 or 8
    bool palettized;    // colorEncoding 1
};

enum Verdict {
    kPasteMip = 0,   // paste 1:1 from mip level `mip` of the source
    kPasteScale = 1, // smaller than the target both ways: the client's 2x scale paste
    kSkipFormat,     // empty, not palettized where a palette is needed, or an alpha size the client cannot paste
    kSkipSize,       // the size would make the client loop for ever, or read outside the texture
    kSkipMips,       // fewer mip levels than the paste starts at
    kSkipTarget,     // more mip levels than the destination has: the client would write past its mip chain
    kSkipBounds,     // a mip level the paste reads lies outside the file
};

struct PastePlan {
    Verdict verdict;
    uint32_t mip;
};

inline bool PastePlanOk(const PastePlan& plan) {
    return plan.verdict == kPasteMip || plan.verdict == kPasteScale;
}

inline const char* VerdictName(Verdict verdict) {
    switch (verdict) {
        case kPasteMip:
            return "ok";
        case kPasteScale:
            return "scaled";
        case kSkipFormat:
            return "format (not palettized, empty, or alpha size not 0/1/4/8)";
        case kSkipSize:
            return "size (not the target size x 2^k, too small to read, or over 16 mip levels)";
        case kSkipMips:
            return "too few mip levels";
        case kSkipTarget:
            return "more mip levels than the character texture";
        case kSkipBounds:
            return "a mip level lies outside the file";
    }

    return "?";
}

inline bool AlphaBitsKnown(uint32_t alphaBits) {
    return alphaBits == 0 || alphaBits == 1 || alphaBits == 4 || alphaBits == 8;
}

// Mip levels the texture cache keeps offsets for (BLPHeader::m_mipOffsets[16]). A header side of 65536 or more makes a
// chain of 17 levels or more (TextureCalcMipCount has no cap), and level 16 on would be read from past the offsets,
// so the plans refuse such a texture (kSkipSize) instead of pasting part of it.
const uint32_t kCacheMipLevels = 16;

// Mip levels of a square power-of-two texture of `size`: log2(size) + 1 (the client's mip chains go down to 1x1).
inline uint32_t MipCountFor(uint32_t size) {
    uint32_t count = 1;

    while (size > 1) {
        size >>= 1;
        count++;
    }

    return count;
}

// The k with value == target << k, or -1.
inline int32_t PowerOfTwoMultiple(uint32_t value, uint32_t target) {
    if (!target || value < target) {
        return -1;
    }

    int32_t k = 0;

    while (value > target) {
        if (value & 1) {
            return -1;
        }

        value >>= 1;
        k++;
    }

    return value == target ? k : -1;
}

// The client's own mip pick, `while (width != target) { width >>= 1; level++; }`: the level it stops at, or -1 when
// it never stops (no level's width, halved and rounded down, is the target).
inline int32_t ClientMipLevel(uint32_t width, uint32_t target) {
    int32_t level = 0;

    while (width != target) {
        if (width < target) {
            return -1;
        }

        width >>= 1;
        level++;
    }

    return level;
}

// PasteToSection: a texture made for one section (read from its top left) into a section of `sectionWidth` x
// `sectionHeight` of a character texture of `dstSize` squared. Mirrors the client: smaller both ways scales 2x,
// otherwise `while (width != sectionWidth) width >>= 1` picks the mip (ClientMipLevel), which never ends when no
// halving gives the section width. Only what would hang or read or write out of bounds is refused; a taller texture
// than needed pastes as before (its lower rows unused). The VPS gate (RaceForge) is stricter: width and height the
// section's x 2^k with the same k.
inline PastePlan PlanSectionPaste(const TextureFacts& t, uint32_t sectionWidth, uint32_t sectionHeight, uint32_t dstSize) {
    PastePlan plan = { kSkipFormat, 0 };

    if (!t.width || !t.height || !t.mipCount || !sectionWidth || !sectionHeight) {
        return plan;
    }

    if (t.mipCount > kCacheMipLevels) {
        plan.verdict = kSkipSize;
        return plan;
    }

    uint32_t dstMips = MipCountFor(dstSize);

    if (t.width < sectionWidth && t.height < sectionHeight) {
        // The scale paste reads source texels up to half the section both ways, then pastes the source's mips from
        // level 0 into the destination's from level 1.
        if (t.width * 2 < sectionWidth || t.height * 2 < sectionHeight) {
            plan.verdict = kSkipSize;
        } else if (t.mipCount + 1 > dstMips) {
            plan.verdict = kSkipTarget;
        } else {
            plan.verdict = kPasteScale;
        }

        return plan;
    }

    int32_t k = ClientMipLevel(t.width, sectionWidth);

    if (k < 0 || (t.height >> k) < sectionHeight) {
        plan.verdict = kSkipSize;
    } else if (static_cast<uint32_t>(k) >= t.mipCount) {
        plan.verdict = kSkipMips;
    } else if (t.mipCount - k > dstMips) {
        plan.verdict = kSkipTarget;
    } else {
        plan.verdict = kPasteMip;
        plan.mip = k;
    }

    return plan;
}

// PasteFromSkin: an atlas pasted opaque (the skin), a section's rectangle read at the section's own place, so the
// texture at the chosen mip must reach the rectangle's right and bottom edges (`rectRight`, `rectBottom`, in
// destination texels). The client's loop here is `while (width != dstSize)`.
inline PastePlan PlanSkinPaste(const TextureFacts& t, uint32_t rectRight, uint32_t rectBottom, uint32_t dstSize) {
    PastePlan plan = { kSkipFormat, 0 };

    if (!t.width || !t.height || !t.mipCount || !dstSize) {
        return plan;
    }

    if (t.mipCount > kCacheMipLevels) {
        plan.verdict = kSkipSize;
        return plan;
    }

    uint32_t dstMips = MipCountFor(dstSize);

    if (t.width < dstSize && t.height < dstSize) {
        if (t.width * 2 < rectRight || t.height * 2 < rectBottom) {
            plan.verdict = kSkipSize;
        } else if (t.mipCount + 1 > dstMips) {
            plan.verdict = kSkipTarget;
        } else {
            plan.verdict = kPasteScale;
        }

        return plan;
    }

    int32_t k = ClientMipLevel(t.width, dstSize);

    if (k < 0 || (t.width >> k) < rectRight || (t.height >> k) < rectBottom) {
        plan.verdict = kSkipSize;
    } else if (static_cast<uint32_t>(k) >= t.mipCount) {
        plan.verdict = kSkipMips;
    } else if (t.mipCount - k > dstMips) {
        plan.verdict = kSkipTarget;
    } else {
        plan.verdict = kPasteMip;
        plan.mip = k;
    }

    return plan;
}

// PasteAtlasLayer (marks and `_Glow` files, a path of our own, so held to the file rules): palettized, square, the
// destination size x 2^k exactly (never scaled up), with alpha 0, 1, 4 or 8. Levels past the destination's chain are simply not read.
inline PastePlan PlanAtlasPaste(const TextureFacts& t, uint32_t dstSize) {
    PastePlan plan = { kSkipFormat, 0 };

    if (!t.width || !t.height || !t.mipCount || !t.palettized || !AlphaBitsKnown(t.alphaBits)) {
        return plan;
    }

    if (t.mipCount > kCacheMipLevels) {
        plan.verdict = kSkipSize;
        return plan;
    }

    int32_t k = t.width == t.height ? PowerOfTwoMultiple(t.width, dstSize) : -1;

    if (k < 0) {
        plan.verdict = kSkipSize;
    } else if (static_cast<uint32_t>(k) >= t.mipCount) {
        plan.verdict = kSkipMips;
    } else {
        plan.verdict = kPasteMip;
        plan.mip = k;
    }

    return plan;
}

// Bytes a palettized mip level holds: one index per texel, then the alpha bits.
inline uint32_t PalMipBytes(uint32_t width, uint32_t height, uint32_t level, uint32_t alphaBits) {
    uint32_t w = width >> level;
    uint32_t h = height >> level;
    uint32_t n = (w ? w : 1) * (h ? h : 1);

    return n + (n * alphaBits + 7) / 8;
}

// Whether mip levels `first` .. `last` (inclusive) of a palettized BLP lie inside its `fileSize` bytes, from its
// header's mip offsets. A `last` of kCacheMipLevels or more is refused, never cut down: the paste would read that
// level too. `requireOffsets`: a level with offset 0 (missing from the file; the cache then reads the header) is
// refused too. Stock textures with a missing small level paste as before, so the client asks
// that only of marks and `_Glow` files, whose rules say every level is there.
inline bool MipsReadable(const uint32_t offsets[16], uint32_t fileSize, const TextureFacts& t, uint32_t first, uint32_t last, bool requireOffsets) {
    if (last >= kCacheMipLevels || first > last) {
        return false;
    }

    for (uint32_t level = first; level <= last; level++) {
        uint32_t offset = offsets[level];

        if (requireOffsets && !offset) {
            return false;
        }

        uint64_t end = static_cast<uint64_t>(offset) + PalMipBytes(t.width, t.height, level, t.alphaBits);

        if (end > fileSize) {
            return false;
        }
    }

    return true;
}

// ---- Pixels ----

// One alpha value (0-255) of texel `index` of a mip level's alpha plane.
inline uint32_t AlphaAt(const uint8_t* alpha, uint32_t alphaBits, uint32_t index) {
    switch (alphaBits) {
        case 1:
            return (alpha[index >> 3] >> (index & 7)) & 1 ? 255 : 0;

        case 4: {
            uint32_t nibble = (alpha[index >> 1] >> (4 * (index & 1))) & 0xF;
            return nibble | (nibble << 4);
        }

        case 8:
            return alpha[index];

        default:
            return 255;
    }
}

// The client's blend of a palette colour over a BGRA texel (CCharacterComponent::PasteTransparent8Bit).
inline void BlendTexel(uint8_t* dst, const uint8_t* bgr, uint32_t a) {
    dst[3] = 0xFF;
    dst[2] = static_cast<uint8_t>(((255 - a) * dst[2] + a * bgr[2]) >> 8);
    dst[1] = static_cast<uint8_t>(((255 - a) * dst[1] + a * bgr[1]) >> 8);
    dst[0] = static_cast<uint8_t>(((255 - a) * dst[0] + a * bgr[0]) >> 8);
}

// One mip level of a palettized texture: `width` x `height` indices, then the alpha plane.
struct PalMip {
    const uint8_t* indices;
    uint32_t width;
    uint32_t height;
    uint32_t alphaBits;
};

// Pastes the rectangle (x, y, w, h) of an atlas mip level at the same place of a BGRA destination whose row 0 starts
// at `dst` (`dstStride` bytes a row): alpha 0 copies, alpha 1/4/8 blends. `palette` is 256 BGRx entries (the
// texture's own, or the black or scaled copy the glow bake passes). The rectangle is clipped to the mip level.
inline void PasteAtlasRect(const PalMip& src, const uint8_t* palette, uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint8_t* dst, uint32_t dstStride) {
    if (x >= src.width || y >= src.height) {
        return;
    }

    if (w > src.width - x) {
        w = src.width - x;
    }

    if (h > src.height - y) {
        h = src.height - y;
    }

    const uint8_t* alpha = src.indices + src.width * src.height;

    for (uint32_t row = y; row < y + h; row++) {
        const uint8_t* line = src.indices + row * src.width;
        uint8_t* out = dst + row * dstStride + 4 * x;

        for (uint32_t col = x; col < x + w; col++, out += 4) {
            const uint8_t* bgr = palette + 4 * line[col];

            if (!src.alphaBits) {
                out[0] = bgr[0];
                out[1] = bgr[1];
                out[2] = bgr[2];
                out[3] = 0xFF;
                continue;
            }

            uint32_t a = AlphaAt(alpha, src.alphaBits, row * src.width + col);

            if (a) {
                BlendTexel(out, bgr, a);
            }
        }
    }
}

// Fills a rectangle of a BGRA destination with one colour (BGRA bytes 0-3 of `bgra`).
inline void FillRect(uint8_t* dst, uint32_t dstStride, uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint32_t bgra) {
    for (uint32_t row = y; row < y + h; row++) {
        uint8_t* out = dst + row * dstStride + 4 * x;

        for (uint32_t col = 0; col < w; col++, out += 4) {
            out[0] = static_cast<uint8_t>(bgra);
            out[1] = static_cast<uint8_t>(bgra >> 8);
            out[2] = static_cast<uint8_t>(bgra >> 16);
            out[3] = static_cast<uint8_t>(bgra >> 24);
        }
    }
}

// ---- Palettes ----

inline void BlackPalette(uint8_t out[1024]) {
    for (uint32_t i = 0; i < 1024; i++) {
        out[i] = 0;
    }
}

// ---- The pass rule ----

// What one layer of the colour bake pastes into the glow bake, in the colour bake's own order (each section starts
// black):
// - a layer whose texture has a usable `_Glow` file pastes that file with its alpha (bleakGlowStrength is applied
//   when it is drawn, Engine/Source/Model2/M2Glow.h, so a strength change needs no new bake);
// - every other layer pastes black through its own alpha: opaque layers (faces, most skins) black the section out,
//   armour, hair and plain ink darken what glows beneath them exactly where they cover it in colour.
enum GlowLayerMode {
    kGlowNone = 0,    // no layer here
    kGlowEmit = 1,    // paste the `_Glow` file
    kGlowOcclude = 2, // paste black through the layer's alpha
};

inline GlowLayerMode GlowLayer(bool hasLayer, bool glowUsable) {
    if (!hasLayer) {
        return kGlowNone;
    }

    return glowUsable ? kGlowEmit : kGlowOcclude;
}

// A component bakes a glow texture only with glow on, a skin of its own (not an NPC's baked one) and at least one
// `_Glow` file among its layers. Everything else costs nothing.
inline bool WantsGlow(bool enabled, bool npcSkin, uint32_t glowLayers) {
    return enabled && !npcSkin && glowLayers > 0;
}

// Whether a rectangle of a BGRA image holds any light (a texel with red, green or blue above 0): the sections a
// glow texture is drawn on (CM2Model::SetGlowTexture's mask).
inline bool AnyLight(const uint8_t* bgra, uint32_t stride, uint32_t x, uint32_t y, uint32_t w, uint32_t h) {
    for (uint32_t row = y; row < y + h; row++) {
        const uint8_t* texel = bgra + row * stride + 4 * x;

        for (uint32_t col = 0; col < w; col++, texel += 4) {
            if (texel[0] | texel[1] | texel[2]) {
                return true;
            }
        }
    }

    return false;
}

// ---- Memory budget and distance ----

static const uint32_t kGlowMaxSize = 256;             // glow textures are 256 x 256 at most (CRITIC 18)
static const uint32_t kGlowBudgetBytes = 8u << 20;    // all glow textures together
// A character gets a glow texture within this camera distance and keeps it until beyond the second. The draw has
// faded the glow out completely at 60 yards (M2Glow::kFadeEndYards), so nothing pops when a texture comes or goes.
static const float kGlowNearYards = 60.0f;
static const float kGlowFarYards = 70.0f;

// The glow texture's size for a character texture of `componentSize` (128, 256 or 512).
inline uint32_t GlowSize(uint32_t componentSize) {
    return componentSize < kGlowMaxSize ? componentSize : kGlowMaxSize;
}

// Bytes of a square texture with all its mips: DXT1 (8 bytes per 4x4 block, one block at least) or 16-bit RGB565.
inline uint32_t TextureBytes(uint32_t size, bool dxt1) {
    uint32_t bytes = 0;

    for (uint32_t s = size; s; s >>= 1) {
        if (dxt1) {
            uint32_t blocks = s / 4 ? s / 4 : 1;
            bytes += blocks * blocks * 8;
        } else {
            bytes += s * s * 2;
        }
    }

    return bytes;
}

inline bool GlowFits(uint32_t usedBytes, uint32_t addBytes, uint32_t budgetBytes) {
    return addBytes <= budgetBytes && usedBytes <= budgetBytes - addBytes;
}

// In range of the camera, with a margin so a character at the edge does not switch on and off: `distanceSq` is the
// squared distance in yards, `wasInRange` the last answer.
inline bool InGlowRange(float distanceSq, bool wasInRange) {
    float limit = wasInRange ? kGlowFarYards : kGlowNearYards;

    return distanceSq == distanceSq && distanceSq <= limit * limit;
}

// The camera distance the glow reads (CM2Model::m_scaleSq) is current only while the scene animates the model: it is 0
// until the first animation, and the world scene does not animate a culled unit beyond about 33 yards
// (CWorldScene::UpdateSortedModels) while its component still bakes. So every decision below also takes the scene
// frames since the model was last animated: its CM2Model::m_frameStamp (kNeverAnimated before the first) against its
// scene's CM2Scene::m_frameStamp.
static const uint32_t kNeverAnimated = 0xFFFFFFFFu;
static const uint32_t kGlowFreshFrames = 2; // a distance at most this many frames old is current

inline uint32_t FramesSinceAnimated(uint32_t modelStamp, uint32_t sceneStamp) {
    return modelStamp == kNeverAnimated ? kNeverAnimated : sceneStamp - modelStamp;
}

inline bool DistanceFresh(uint32_t framesSince) {
    return framesSince <= kGlowFreshFrames;
}

// The range answer to keep for next time (InGlowRange's `wasInRange`): a fresh distance decides, a stale one leaves it.
inline bool GlowRangeAfter(uint32_t framesSince, float distanceSq, bool wasInRange) {
    return DistanceFresh(framesSince) ? InGlowRange(distanceSq, wasInRange) : wasInRange;
}

// Whether a character may get a glow texture: only by a fresh distance in range. A character the scene has not
// measured lately is not 0 yards away.
inline bool GlowMayCreate(uint32_t framesSince, float distanceSq, bool wasInRange) {
    return DistanceFresh(framesSince) && InGlowRange(distanceSq, wasInRange);
}

// Whether a character must let go of its glow texture: only by a fresh distance beyond range. With a stale one it keeps
// it, so turning the camera back to it does not bake it again; only characters last measured in range hold budget.
inline bool GlowMustDrop(uint32_t framesSince, float distanceSq, bool wasInRange) {
    return DistanceFresh(framesSince) && !InGlowRange(distanceSq, wasInRange);
}

// The budget is full and a character with a fresh distance in range has no glow texture (the candidate): who gives
// theirs up. First holders the scene has not measured lately (it does not draw them), the longest unmeasured first;
// then holders farther than the candidate by more than kGlowEvictMarginYards, the farthest first (the margin keeps two
// characters at about the same distance from taking it from each other in turn). Nobody nearer gives theirs up.
static const float kGlowEvictMarginYards = 5.0f;

struct GlowHolder {
    uint32_t framesSince; // FramesSinceAnimated
    float distanceSq;     // the last distance the scene measured (squared yards)
};

inline bool MayEvict(const GlowHolder& holder, float candidateSq) {
    if (!DistanceFresh(holder.framesSince)) {
        return true;
    }

    float limit = std::sqrt(candidateSq > 0.0f ? candidateSq : 0.0f) + kGlowEvictMarginYards;

    return !(holder.distanceSq <= limit * limit); // a NaN distance is out of range (InGlowRange)
}

// Whether holder `a` gives its texture up before holder `b`.
inline bool EvictsBefore(const GlowHolder& a, const GlowHolder& b) {
    bool aFresh = DistanceFresh(a.framesSince);
    bool bFresh = DistanceFresh(b.framesSince);

    if (aFresh != bFresh) {
        return !aFresh;
    }

    if (!aFresh) {
        return a.framesSince > b.framesSince;
    }

    float aSq = a.distanceSq == a.distanceSq ? a.distanceSq : 3.0e38f;
    float bSq = b.distanceSq == b.distanceSq ? b.distanceSq : 3.0e38f;

    return aSq > bSq;
}

// Walks a list (`first`, then `next(item)` until null) and returns the holder that gives its texture up for a candidate
// at `candidateSq`, or null when nobody may. `holderOf(item, holder)` fills in a holder and returns false for an item
// with no glow texture (the candidate itself among them).
template <typename Item, typename Next, typename HolderOf>
inline Item* PickEviction(Item* first, Next next, HolderOf holderOf, float candidateSq) {
    Item* best = nullptr;
    GlowHolder bestHolder = { 0, 0.0f };

    for (Item* item = first; item; item = next(item)) {
        GlowHolder holder = { 0, 0.0f };

        if (!holderOf(item, holder) || !MayEvict(holder, candidateSq)) {
            continue;
        }

        if (!best || EvictsBefore(holder, bestHolder)) {
            best = item;
            bestHolder = holder;
        }
    }

    return best;
}

// ---- The glow texture's device callback ----

// The row stride (bytes) the callback latches for a mip `width` texels wide: rows of 4x4 DXT1 blocks (8 bytes each, one
// block at least) or of 32-bit ARGB texels.
inline uint32_t GlowLatchStride(uint32_t width, bool dxt1) {
    if (dxt1) {
        uint32_t blocks = width / 4;
        return 8 * (blocks ? blocks : 1);
    }

    return 4 * width;
}

// The bytes a device reads from one latched mip: the stride times its rows (of blocks, for DXT1).
inline uint32_t GlowLatchBytes(uint32_t width, uint32_t height, bool dxt1) {
    uint32_t rows = dxt1 ? (height / 4 ? height / 4 : 1) : height;

    return GlowLatchStride(width, dxt1) * rows;
}

// A glow texture the component has let go of may still be held by a copy of its model (a PlayerModel's DuplicateModel
// takes it, M2Glow::TakeSourceGlow). Its device callback must never be null: CGxDeviceD3d::ITexForceRecreation calls
// it unchecked when the device recreates its textures. Nor may it latch nothing: the OpenGL upload reads whatever
// texels it latches. So it latches black from a static buffer this big, enough for the largest mip of either format.
static const uint32_t kGlowBlackBytes = 4 * kGlowMaxSize * kGlowMaxSize;

// ---- Dumps (bleakMarksDump) ----

// An 18-byte header of an uncompressed 32-bit BGRA TGA, rows top to bottom.
inline void TgaHeader(uint8_t out[18], uint32_t width, uint32_t height) {
    for (uint32_t i = 0; i < 18; i++) {
        out[i] = 0;
    }

    out[2] = 2;
    out[12] = static_cast<uint8_t>(width);
    out[13] = static_cast<uint8_t>(width >> 8);
    out[14] = static_cast<uint8_t>(height);
    out[15] = static_cast<uint8_t>(height >> 8);
    out[16] = 32;
    out[17] = 0x28;
}

// One DXT1 block to 16 BGRA texels, row by row.
inline void DecodeDxt1Block(const uint8_t block[8], uint8_t out[64]) {
    uint32_t c0 = block[0] | (block[1] << 8);
    uint32_t c1 = block[2] | (block[3] << 8);
    uint8_t colors[4][4];

    for (uint32_t i = 0; i < 2; i++) {
        uint32_t c = i ? c1 : c0;
        uint32_t r = (c >> 11) & 0x1F;
        uint32_t g = (c >> 5) & 0x3F;
        uint32_t b = c & 0x1F;
        colors[i][0] = static_cast<uint8_t>((b << 3) | (b >> 2));
        colors[i][1] = static_cast<uint8_t>((g << 2) | (g >> 4));
        colors[i][2] = static_cast<uint8_t>((r << 3) | (r >> 2));
        colors[i][3] = 0xFF;
    }

    for (uint32_t ch = 0; ch < 3; ch++) {
        if (c0 > c1) {
            colors[2][ch] = static_cast<uint8_t>((2 * colors[0][ch] + colors[1][ch]) / 3);
            colors[3][ch] = static_cast<uint8_t>((colors[0][ch] + 2 * colors[1][ch]) / 3);
        } else {
            colors[2][ch] = static_cast<uint8_t>((colors[0][ch] + colors[1][ch]) / 2);
            colors[3][ch] = 0;
        }
    }

    colors[2][3] = 0xFF;
    colors[3][3] = c0 > c1 ? 0xFF : 0;
    uint32_t indices = block[4] | (block[5] << 8) | (block[6] << 16) | (static_cast<uint32_t>(block[7]) << 24);

    for (uint32_t i = 0; i < 16; i++) {
        const uint8_t* c = colors[(indices >> (2 * i)) & 3];

        for (uint32_t ch = 0; ch < 4; ch++) {
            out[4 * i + ch] = c[ch];
        }
    }
}

} // namespace BleakMarks

#endif
