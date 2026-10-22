#ifndef ENGINE_SOURCE_BLEAKFX_BLEAKFX_H
#define ENGINE_SOURCE_BLEAKFX_BLEAKFX_H

#include <cstdint>
#include "Engine/Source/Tempest/C3Vector.h"
#include "Engine/Source/Tempest/CImVector.h"

// BLEAKHOLD(bleakfx): post-processing of the 3D world after it is drawn and before the interface: ambient occlusion
// and light shafts from the depth buffer, bloom, clarity (local contrast), colour grading, vignette, FXAA and
// contrast-adaptive sharpening. The shaders (Shaders/*.hlsl, ps_3_0 and vs_3_0) are compiled with fxc at build time
// and created from memory, so they need no game files. Runs on the Direct3D 9 devices with shader model 3 only;
// anywhere else the frame stays exactly as the stock client draws it. The settings are the bleakFx* console
// variables. The depth effects also need multisampling off (Engine/Source/Gx/BleakDepth.h).
namespace BleakFx {
    // What the world's light looks like this frame (DayNight).
    struct WorldLight {
        // The glow band of the current light, 0..1: zones Blizzard made glowier get a little more bloom.
        float zoneGlow;
        // World-space direction towards the sun, and the colour of its light.
        C3Vector sunDirection;
        CImVector sunColor;
        // Distance (yards) where the fog is complete; the ambient occlusion fades out before it.
        float fogEnd;
    };

    // Registers the console variables. Called by every world frame; registering twice keeps the values.
    void Init();

    // Frees the textures and shaders and puts the automatic depth buffer back (the world frame goes away).
    void Destroy();

    // Whether the bloom stands in for the stock full screen glow (CGWorldFrame then sets the stock glow amount to
    // 0 and keeps its underwater and drunk blur).
    bool ReplacesStockGlow();

    // Before the world is drawn: switches the readable depth buffer on or off and notes the camera.
    void BeginWorld();

    // After the world is drawn, before the interface: processes the back buffer.
    void RenderWorld(const WorldLight& light);
}

#endif
