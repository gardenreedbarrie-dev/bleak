#ifndef WOW_SOURCE_UI_BLEAKHOLDMARKS_H
#define WOW_SOURCE_UI_BLEAKHOLDMARKS_H

// BLEAKHOLD(marks): the Lua side of glowing marks by player GUID (mod-bleakhold-ui protocol section 22). The addon
// (Marks.lua) turns each player's chosen mark and eye colour into two texture paths and hands them over with
// BleakholdMarks_Set; the map is WoW/Common/ComponentCore/BleakMarkOwners.h, read by CCharacterComponent's
// LoadMarkLayer and GeosRenderPrep, and every change rebuilds that GUID's components
// (CCharacterComponent::BleakMarksChanged). FrameXML only, never glue. No native raises a Lua error: bad arguments
// return the failure value.
class CGBleakholdMarks {
    public:
    static void RegisterScriptFunctions();
    static void UnregisterScriptFunctions();
    // Logout (CGGameUI::Shutdown): no entries carry over to another character; no rebuild, and the names stay. Not on
    // a far teleport: the server does not send the list again then.
    static void Reset();
};

#endif
