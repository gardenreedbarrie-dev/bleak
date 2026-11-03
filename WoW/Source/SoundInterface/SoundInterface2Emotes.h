#ifndef WOW_SOURCE_SOUNDINTERFACE_SOUNDINTERFACE2EMOTES_H
#define WOW_SOURCE_SOUNDINTERFACE_SOUNDINTERFACE2EMOTES_H

#include <cstddef>
#include <cstdint>
#include "WoW/Common/BleakholdRaces.h"

struct TEXTEMOTELOOKUP {
    /* 0000 */ int32_t m_soundIds[BLEAKHOLD_RACE_CAPACITY][2]; // BLEAKHOLD(races): was [22]
    /* 0100 */ int32_t m_emotesTextId; // 0x00B0 with [22]

    TEXTEMOTELOOKUP();
};

#endif
