#ifndef WOW_COMMON_BLEAKHOLDEMOJI_H
#define WOW_COMMON_BLEAKHOLDEMOJI_H

#include <cstdint>

// BLEAKHOLD(emoji): emoji bubbles. The server shows emoji N above a unit's head with SMSG_PLAY_SPELL_VISUAL kit
// BLEAKHOLD_EMOJI_KIT_BASE + N (docs/BleakholdProtocol.md, section 13); those kits never reach SpellVisualKit. The
// art is Interface\Bleakhold\Emoji\EmojiNNN.blp (Tools/EmojiForge); a missing file shows nothing.
static const uint32_t BLEAKHOLD_EMOJI_KIT_BASE = 900000;
static const uint32_t BLEAKHOLD_EMOJI_MAX = 256;
static const char BLEAKHOLD_EMOJI_TEXTURE[] = "Interface\\Bleakhold\\Emoji\\Emoji%03u";

// Timeline of one bubble, in ms from the moment it appears.
static const uint32_t BLEAKHOLD_EMOJI_POP_MS = 120;        // grows from 0 to BLEAKHOLD_EMOJI_POP_SCALE
static const uint32_t BLEAKHOLD_EMOJI_SETTLE_MS = 250;     // back to full size
static const uint32_t BLEAKHOLD_EMOJI_HOLD_MS = 2750;      // the fade starts
static const uint32_t BLEAKHOLD_EMOJI_LIFETIME_MS = 3250;  // the fade ends and the bubble is removed
static const float BLEAKHOLD_EMOJI_POP_SCALE = 1.25f;

// The emoji a spell visual kit stands for; false for an ordinary kit (kits below the base wrap around).
inline bool BleakholdEmojiFromKit(uint32_t kitId, uint32_t* emoji) {
    uint32_t n = kitId - BLEAKHOLD_EMOJI_KIT_BASE;

    if (n >= BLEAKHOLD_EMOJI_MAX) {
        return false;
    }

    *emoji = n;
    return true;
}

// Size (fraction of the full size), alpha (0..1) and rise (0..1 of the full rise) at ageMs; false once it is over.
// The pop eases out to BLEAKHOLD_EMOJI_POP_SCALE and settles back with a smoothstep; the fade rises as it goes.
inline bool BleakholdEmojiPose(uint32_t ageMs, float* scale, float* alpha, float* rise) {
    if (ageMs >= BLEAKHOLD_EMOJI_LIFETIME_MS) {
        return false;
    }

    *scale = 1.0f;
    *alpha = 1.0f;
    *rise = 0.0f;

    if (ageMs < BLEAKHOLD_EMOJI_POP_MS) {
        float u = 1.0f - static_cast<float>(ageMs) / static_cast<float>(BLEAKHOLD_EMOJI_POP_MS);
        *scale = BLEAKHOLD_EMOJI_POP_SCALE * (1.0f - u * u);
    } else if (ageMs < BLEAKHOLD_EMOJI_SETTLE_MS) {
        float s = static_cast<float>(ageMs - BLEAKHOLD_EMOJI_POP_MS) / static_cast<float>(BLEAKHOLD_EMOJI_SETTLE_MS - BLEAKHOLD_EMOJI_POP_MS);
        *scale = BLEAKHOLD_EMOJI_POP_SCALE - (BLEAKHOLD_EMOJI_POP_SCALE - 1.0f) * s * s * (3.0f - 2.0f * s);
    } else if (ageMs >= BLEAKHOLD_EMOJI_HOLD_MS) {
        float v = static_cast<float>(ageMs - BLEAKHOLD_EMOJI_HOLD_MS) / static_cast<float>(BLEAKHOLD_EMOJI_LIFETIME_MS - BLEAKHOLD_EMOJI_HOLD_MS);
        *alpha = 1.0f - v;
        *rise = v;
    }

    return true;
}

#endif
