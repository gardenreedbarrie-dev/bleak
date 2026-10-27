#ifndef WOW_SOURCE_UI_BLEAKHOLDSTORM_H
#define WOW_SOURCE_UI_BLEAKHOLDSTORM_H

// BLEAKHOLD(storm): the Bleakhold Royale storm in the world. The addon (RoyaleHud.lua) hands over the circle of each
// ROYS with BleakholdStorm_Set; every frame the circle is moved exactly as the addon's R.Circle moves it, and
// BleakFx::RenderStorm draws a translucent purple wall on its edge, a pale ring on the ground where the next circle
// will be, and a faint purple over the world while the camera is in the storm (not from the lobby, which the addon
// marks with Set's noTint). Nothing is drawn without a circle, on another map, 30 s after the last Set, or with the
// bleakStormWall CVar at 0. The maths is Engine/Source/BleakFx/BleakStorm.h.
class CGBleakholdStorm {
    public:
    static void InitializeGame();
    static void ShutdownGame();
    // No circle carries over a logout or a far teleport (the addon sends it again within seconds).
    static void ClearAll();
    // From CGWorldFrame::OnWorldRender, in the world pass right after the liquids and before the transparent models
    // and particles of the camera's side of the water, which blend over the wall.
    static void OnWorldRender();
    static void RegisterScriptFunctions();
    static void UnregisterScriptFunctions();
};

#endif
