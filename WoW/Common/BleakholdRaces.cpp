// BLEAKHOLD(races): the Bleakhold races, found by their ChrRaces clientFileString (BleakholdRaces.h).

#include "WoW/Common/BleakholdRaces.h"
#include <cstring>
#include "Engine/Source/Storm/H/storm.h"
#include "WoW/Source/DB/DBClient/DBClient.h"
#include "WoW/Source/DB/Rec/ChrRacesRec.h"

namespace {
    struct BleakholdRace {
        const char* clientFileString;
        uint8_t proxyRace;
    };

    const BleakholdRace kBleakholdRaces[] = {
        { "HighElf", 10 }, // Blood Elf
        { "Eredar", 11 },  // Draenei
    };

    // The proxy race of each race id; 0 for a race that is its own. Written once by BleakholdRacesInitialize, before
    // anything reads it.
    uint8_t s_proxyRaces[BLEAKHOLD_RACE_CAPACITY];
}

void BleakholdRacesInitialize() {
    memset(s_proxyRaces, 0, sizeof(s_proxyRaces));

    // Race 0 is no race, and a race past the capacity cannot be held by the client at all.
    for (uint32_t race = 1; race < BLEAKHOLD_RACE_CAPACITY; race++) {
        const ChrRacesRec* rec = g_chrRacesDB.GetRecord(static_cast<int32_t>(race));

        if (!rec || !rec->m_clientFileString) {
            continue;
        }

        for (const BleakholdRace& bleakholdRace : kBleakholdRaces) {
            if (!SStrCmpI(rec->m_clientFileString, bleakholdRace.clientFileString, STORM_MAX_STR)) {
                s_proxyRaces[race] = bleakholdRace.proxyRace;
                break;
            }
        }
    }
}

uint32_t BleakholdProxyRace(uint32_t race) {
    if (race < BLEAKHOLD_RACE_CAPACITY && s_proxyRaces[race]) {
        return s_proxyRaces[race];
    }

    return race;
}
