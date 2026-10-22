#ifndef ENGINE_SOURCE_BLEAKFX_BLEAKFX_H
#define ENGINE_SOURCE_BLEAKFX_BLEAKFX_H

#include <cstdint>
#include "Engine/Source/Tempest/C3Vector.h"
#include "Engine/Source/Tempest/CImVector.h"

// BLEAKHOLD(bleakfx): post-processing of the 3D world after it is drawn and before the interface: ambient occlusion
// and light shafts from the depth buffer, bloom, clarity (local contrast), colour grading, vignette, FXAA and
// contrast-adaptive sharpening; and water with reflections, refraction and colour by depth. The shaders
// (Shaders/*.hlsl, ps_3_0 and vs_3_0) are compiled with fxc at build time and created from memory, so they need no
// game files. Runs on the Direct3D 9 devices with shader model 3 only;
// anywhere else the frame stays exactly as the stock client draws it. The settings are the bleakFx* console
// variables. The depth effects also need multisampling off (Engine/Source/Gx/BleakDepth.h).
namespace BleakFx {
    // What the world's light looks like this frame (DayNight).
    struct WorldLight {
        // The glow band of the current light, 0..1: zones Blizzard made glowier get a little more bloom.
        float zoneGlow;
        // World-space direction towards the sun, and the colour of its light. sunVisible: the sky shows the sun (no
        // zone skybox covers it).
        C3Vector sunDirection;
        CImVector sunColor;
        bool sunVisible;
        // Distance (yards) where the fog is complete; the ambient occlusion fades out before it.
        float fogEnd;
        // The sky overhead and at the horizon: what the water reflects where nothing is in the way.
        CImVector skyZenith;
        CImVector skyHorizon;
    };

    // One water surface CMaterialWater draws.
    struct WaterDraw {
        // World position of the camera (the liquid's camera-relative origin).
        C3Vector cameraPos;
        // The stock fog of the draw (Liquid::VSConstants m_fog x and y): fog = saturate(view z * scale + offset).
        float fogScale;
        float fogOffset;
    };

    // Registers the console variables. Called by every world frame; registering twice keeps the values.
    void Init();

    // Frees the textures and puts the automatic depth buffer back (the world frame goes away). The shaders stay for
    // the next world frame.
    void Destroy();

    // Whether the bloom stands in for the stock full screen glow (CGWorldFrame then sets the stock glow amount to
    // 0 and keeps its underwater and drunk blur).
    bool ReplacesStockGlow();

    // Before the world is drawn: switches the readable depth buffer on or off and notes the camera and the light.
    void BeginWorld(const WorldLight& light);

    // Before the transparent liquids (CWorldScene::RenderLiquidPass): copies the frame and its depth for the water.
    void BeginLiquids();

    // In CMaterialWater::Render, in place of the stock water shaders: binds BleakFx's water shaders (they read the
    // same constants), its textures and constants. Returns false when the stock shaders should draw (BleakFx water
    // off, not supported, or no frame copy this frame).
    bool BindWater(const WaterDraw& draw);

    // After the world is drawn, before the interface: processes the back buffer. Only a world that fills the window
    // is processed; one drawn into part of it (a resized WorldFrame) stays as drawn.
    void RenderWorld();
}

#endif
