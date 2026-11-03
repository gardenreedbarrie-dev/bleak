#ifndef WOW_COMMON_BLEAKHOLDDANCE_H
#define WOW_COMMON_BLEAKHOLDDANCE_H

#include <cstdint>

// BLEAKHOLD(dance): Bleakhold dances. The server starts dance N on a unit with SMSG_PLAY_SPELL_VISUAL kit
// BLEAKHOLD_DANCE_KIT_BASE + N (docs/BleakholdProtocol.md, section 14) and sets the unit's emote state to
// EMOTE_STATE_DANCE, so a stock client shows the stock dance. The Bleakhold client plays clip N of
// Interface\Bleakhold\Dances\Dances.bdc (Tools/DanceForge) on the unit for as long as that emote state lasts, with
// the dance's music when Interface\Bleakhold\Dances\Music\<key>.mp3 (or .ogg, .wav) exists. While the unit keeps
// dancing the server sends the kit again at the start of every loop, which lets a client that arrives later join
// in step.
static const uint32_t BLEAKHOLD_DANCE_KIT_BASE = 910000;
static const uint32_t BLEAKHOLD_DANCE_MAX = 1024;
static const uint32_t BLEAKHOLD_EMOTE_STATE_DANCE = 10;

// The dance a spell visual kit stands for; false for an ordinary kit (kits below the base wrap around).
inline bool BleakholdDanceFromKit(uint32_t kitId, uint32_t* dance) {
    uint32_t n = kitId - BLEAKHOLD_DANCE_KIT_BASE;

    if (n >= BLEAKHOLD_DANCE_MAX) {
        return false;
    }

    *dance = n;
    return true;
}

#endif
