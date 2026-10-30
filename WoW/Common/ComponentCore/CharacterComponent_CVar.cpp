#include <cstdint>
#include "WoW/Common/ComponentCore/CharacterComponent.h"
#include "Engine/Source/ConsoleBase/ConsoleVar.h"
#include "Engine/Source/ConsoleBase/Types.h"

// STATIC: 0x00B2F9EC
CVar* CCharacterComponent::g_componentTextureLevelVar;

// STATIC: 0x00B2F9F0
CVar* CCharacterComponent::g_componentThreadVar;

// STATIC: 0x00B2F9F4
CVar* CCharacterComponent::g_componentCompressVar;

// BLEAKHOLD(glow): glowing marks. bleakGlow and bleakGlowStrength are read by the bake (CharacterComponent.cpp) and
// by the glow draw (Engine/Source/Model2/M2Glow.h, through CVar::Lookup); bleakMarksDump writes the bakes to Logs.
CVar* CCharacterComponent::s_bleakGlowVar;
CVar* CCharacterComponent::s_bleakGlowStrengthVar;
CVar* CCharacterComponent::s_bleakMarksDumpVar;
int32_t CCharacterComponent::s_bleakGlowChanged;

// VERIFY: 00bba183 auto
// OFFSET: 0x008A1420
bool ComponentVarHandler(CVar* var, const char* oldValue, const char* value, void* arg) {
    return true;
}

// BLEAKHOLD(glow): a change of bleakGlow is handled by CCharacterComponent::GlowSweep on the next frame (glow
// textures and `_Glow` files let go of, or looked for again).
static bool BleakGlowVarHandler(CVar* var, const char* oldValue, const char* value, void* arg) {
    CCharacterComponent::s_bleakGlowChanged = 1;
    return true;
}

// BLEAKHOLD(glow)
void CCharacterComponent::RegisterBleakGlowCVars() {
    CCharacterComponent::s_bleakGlowVar = CVar::Register("bleakGlow", "Glowing marks on characters (1 on, 0 off)", 0x1, "1", &BleakGlowVarHandler, CATEGORY_GRAPHICS, false, nullptr, false);
    CCharacterComponent::s_bleakGlowStrengthVar = CVar::Register("bleakGlowStrength", "Brightness of glowing marks (0 - 1)", 0x1, "1", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    CCharacterComponent::s_bleakMarksDumpVar = CVar::Register("bleakMarksDump", "Write character texture bakes to Logs\\BleakMarks_*.tga (1 on, at most 64 a session)", 0x0, "0", nullptr, CATEGORY_DEBUG, false, nullptr, false);
}
