#ifndef WOW_COMMON_BLEAKHOLDRACES_H
#define WOW_COMMON_BLEAKHOLDRACES_H

#include <cstdint>

// BLEAKHOLD(races): Bleakhold adds two playable races after the stock ChrRaces rows (1-11 playable, 12-21 the
// creature display races): High Elf (Alliance) and Eredar (Horde). Most of the client reads races from the
// tables; these are for the few places that sized arrays or picked files by race id.

// Race ids the client can hold. The race masks are 32 bits wide (1 << race for /who and helmet geosets), so 31
// is the highest id any race can have.
static const uint32_t BLEAKHOLD_RACE_CAPACITY = 32;

static const uint32_t BLEAKHOLD_RACE_HIGHELF = 22;
static const uint32_t BLEAKHOLD_RACE_EREDAR = 23;

// The stock race whose models, scenes and sounds a Bleakhold race borrows where the game data has none of its
// own: Blood Elf for High Elf, Draenei for Eredar. Any other race is its own.
inline uint32_t BleakholdProxyRace(uint32_t race) {
    switch (race) {
        case BLEAKHOLD_RACE_HIGHELF:
            return 10;
        case BLEAKHOLD_RACE_EREDAR:
            return 11;
        default:
            return race;
    }
}

#endif
