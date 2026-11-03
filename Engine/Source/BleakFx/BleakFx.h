#ifndef ENGINE_SOURCE_BLEAKFX_BLEAKFX_H
#define ENGINE_SOURCE_BLEAKFX_BLEAKFX_H

#include <cstdint>
#include "Engine/Source/BleakFx/BleakStorm.h"
#include "Engine/Source/Tempest/C3Vector.h"
#include "Engine/Source/Tempest/C44Matrix.h"
#include "Engine/Source/Tempest/CImVector.h"

class CGxShader;

// BLEAKHOLD(bleakfx): post-processing of the 3D world after it is drawn and before the interface: ambient occlusion
// and light shafts from the depth buffer, bloom, clarity (local contrast), colour grading, vignette, SMAA or FXAA and
// contrast-adaptive sharpening; water with reflections, refraction and colour by depth; and the wall of the Bleakhold
// Royale storm (BleakStorm.h). The shaders
// (Shaders/*.hlsl, ps_3_0 and vs_3_0) are compiled with fxc at build time and created from memory, so they need no
// game files. Runs on the Direct3D 9 devices with shader model 3 only;
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
        // The ambient and the direct (diffuse) light of the outdoors: their ratio is what a contact shadow leaves.
        CImVector ambient;
        CImVector diffuse;
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
        // The sky shows the sun (DayNight::BleakSunDrawn): no skybox of the zone or of the WMO covers it.
        bool sunVisible;
    };

    // BLEAKHOLD(storm): one frame of the Bleakhold Royale storm wall (WoW/Source/Ui/BleakholdStorm.h).
    struct StormDraw {
        // The wall on the storm's edge and the next circle's ring (BleakStorm::Build); either may be empty.
        const BleakStorm::Vertex* wall;
        uint32_t wallVertexCount;
        const uint16_t* wallIndices;
        uint32_t wallIndexCount;
        const BleakStorm::Vertex* ring;
        uint32_t ringVertexCount;
        const uint16_t* ringIndices;
        uint32_t ringIndexCount;
        // The world position the vertices are relative to, the camera relative to it, and the view and projection
        // the world is drawn with (from a position relative to the origin into clip space).
        double origin[3];
        float eye[3];
        C44Matrix viewProj;
        // Past the world's far plane farZ (a view depth), when horizon (BleakStorm::HorizonPass): the view and the
        // horizon's projection, and the depth range the horizon is drawn into (CWorldScene::RenderHorizon).
        bool horizon;
        C44Matrix horizonViewProj;
        float horizonMinZ;
        float horizonMaxZ;
        float farZ;
        // A steady clock that runs faster while the storm moves (seconds), and how much it moves (0 - 1).
        double phase;
        float moving;
        // How strongly the wall shows (0 - 1), and the purple over the whole world while the camera is in the storm
        // (0 none).
        float strength;
        float tint;
        // The world's fog: its colour, and the view depths where it starts and where it is complete.
        CImVector fogColor;
        float fogStart;
        float fogEnd;
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

    // BLEAKHOLD(grasswind): CDetailDoodad::Initialize, after the stock grass vertex shaders are loaded: writes the
    // wind into them (Engine/Source/Gx/BleakGrassWind.h). Shaders that are not the expected stock ones stay as they
    // are.
    void PatchGrassShaders(CGxShader** shaders, uint32_t count);

    // CDetailDoodad::InitializeRenderState, before the grass is drawn: this frame's wind (none while BleakFx is off
    // or bleakFxGrassWind is 0). camera: World::GetCamPos(); player: the active player's position, or nullptr.
    void SetGrassWind(const C3Vector& camera, const C3Vector* player);

    // After the world is drawn, before the interface: processes the back buffer. Only a world that fills the window
    // is processed; one drawn into part of it (a resized WorldFrame) stays as drawn. sunVisible: the sky showed the
    // sun (DayNight::BleakSunDrawn, after the world is drawn: a WMO's skybox is chosen while it is drawn); skyShown:
    // the sky was drawn at all (outdoors), so the sun lights the world even behind a skybox.
    void RenderWorld(bool sunVisible, bool skyShown);

    // BLEAKHOLD(storm): "" when this device draws the storm wall, else why not: "device" (not Direct3D 9 with shader
    // model 3) or "shaders" (built without them, or the driver refused them). Independent of the bleakFx switch: the
    // wall shows the game's state, it is not a look.
    const char* StormSupport();

    // In the world pass, after the liquids and before the transparent models and particles on the camera's side of
    // the water (CGWorldFrame::OnWorldRender): draws the wall and the ring with the depth test and no depth writes,
    // alpha-blended, up to the world's far plane and, with draw.horizon, past it the way the horizon is drawn; then
    // the tint. The soft foot needs the readable depth buffer (BleakFx on, multisampling off): the water's copy of
    // this frame, else a copy made here. Never into a texture target.
    void RenderStorm(const StormDraw& draw);
}

#endif
