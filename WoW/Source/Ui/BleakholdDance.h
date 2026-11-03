#ifndef WOW_SOURCE_UI_BLEAKHOLDDANCE_H
#define WOW_SOURCE_UI_BLEAKHOLDDANCE_H

#include <cstdint>
#include "WoW/Source/Object/WGUID.h"

struct CVar;

// BLEAKHOLD(dance): who dances which Bleakhold dance (WoW/Common/BleakholdDance.h). A kit from the server starts a
// dance on a unit; OnWorldLayerUpdate (from CGWorldFrame::OnLayerUpdate) keeps it on the unit's current model while
// the unit's emote state says dance, plays the dance's music at the unit and stops both when the emote state goes
// (the server clears it when the unit moves, turns or dies). The engine side, which moves the bones, is
// Engine/Source/Model2/M2Dance.h. Units are looked up by GUID every frame.
class CGBleakholdDance {
    public:
    static void InitializeGame();
    static void ShutdownGame();
    // No dance carries over a logout or a far teleport.
    static void ClearAll();
    // From the SMSG_PLAY_SPELL_VISUAL handler.
    static void OnKit(const WOWGUID& unit, uint32_t dance);
    static void OnWorldLayerUpdate();
    static void RegisterScriptFunctions();
    static void UnregisterScriptFunctions();
    static bool DancesCallback(CVar* var, const char* oldValue, const char* value, void* arg);
};

#endif
