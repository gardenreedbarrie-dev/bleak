#ifndef WOW_COMMON_BLEAKHOLDRACES_H
#define WOW_COMMON_BLEAKHOLDRACES_H

#include <cstdint>

// BLEAKHOLD(races): Bleakhold adds two playable races, High Elf (Alliance) and Eredar (Horde). Their race ids
// depend on the game data: RaceForge's build adds them after the stock ChrRaces rows (1-11 playable, 12-21 the
// creature display races) as 22 and 23, while the Bleakhold realm's own race patch puts them in the stock slots 15
// and 19 (Skeleton and Taunka in the stock data). So the client knows them by their ChrRaces clientFileString,
// "HighElf" and "Eredar", and never by id. Most of the client reads races from the tables; these are for the few
// places that sized arrays or picked files by race id.

// Race ids the client can hold. The race masks are 32 bits wide (1 << race for /who and helmet geosets), so 31
// is the highest id any race can have.
static const uint32_t BLEAKHOLD_RACE_CAPACITY = 32;

// Finds the Bleakhold races in the loaded ChrRaces table. ClientDBInitialize calls it once, after the tables are
// loaded.
void BleakholdRacesInitialize();

// The stock race whose models, scenes and sounds a Bleakhold race borrows where the game data has none of its
// own: Blood Elf (10) for the ChrRaces row named "HighElf", Draenei (11) for "Eredar" (the name in any case). Any
// other race is its own, and so is every race before BleakholdRacesInitialize and in game data without those rows.
uint32_t BleakholdProxyRace(uint32_t race);

#endif
