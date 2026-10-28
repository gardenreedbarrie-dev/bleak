#ifndef WOW_SOURCE_UI_BLEAKHOLDSTORM_H
#define WOW_SOURCE_UI_BLEAKHOLDSTORM_H

#include <cstdint>

// BLEAKHOLD(storm): the Bleakhold Royale storm in the world. The addon (RoyaleHud.lua) hands over the circle of each
// ROYS with BleakholdStorm_Set; every frame the circle is moved exactly as the addon's R.Circle moves it, and
// BleakFx::RenderStorm draws a translucent purple wall on its edge, a pale ring on the ground where the next circle
// will be, and a faint purple over the world while the camera is in the storm (not from the lobby, which the addon
// marks with Set's noTint). Nothing is drawn without a circle, on another map, 30 s after the last Set, or with the
// bleakStormWall CVar at 0. The maths is Engine/Source/BleakFx/BleakStorm.h.
//
// The same circle is drawn on the minimap (CGMinimapFrame::Render, over the tiles and under their mask and rotation):
// a hatched purple shade outside it, its edge as a line with a dark keyline, and the next circle dashed white; not
// indoors, and not with the bleakStormMinimap CVar at 0. Lua also gets BleakholdUI_ScreenPixels,
// BleakholdStorm_MinimapViewRadius and BleakholdStorm_Altitude for the addon's own drawing (Royale*.lua).
class CGxTex;
class C2Vector;
class C3Vector;

class CGBleakholdStorm {
    public:
    static void InitializeGame();
    static void ShutdownGame();
    // No circle carries over a logout or a far teleport (the addon sends it again within seconds).
    static void ClearAll();
    // From CGWorldFrame::OnWorldRender, in the world pass right after the liquids and before the transparent models
    // and particles of the camera's side of the water, which blend over the wall.
    static void OnWorldRender();
    // From CGMinimapFrame::Render each time it builds its tile quads (MinimapUpdate's position, center and scale,
    // and the frame's layoutScale and width): the space the storm is drawn in there. Only those frames set center and
    // scale, so the space is kept for the frames in between.
    static void SetMinimapSpace(const C3Vector& position, const C2Vector& center, float scale, float layoutScale, float width);
    // From CGMinimapFrame::Render right after the tiles, with the rotated view still set (outdoors only): the storm
    // over them, through the minimap's mask texture, at the frame's effective alpha (0-255).
    static void OnMinimapRender(CGxTex* mask, uint8_t alpha);
    static void RegisterScriptFunctions();
    static void UnregisterScriptFunctions();
};

#endif
