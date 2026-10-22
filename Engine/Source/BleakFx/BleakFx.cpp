#include "Engine/Source/BleakFx/BleakFx.h"
#include <cmath>
#include <cstring>
#include <vector>
#include "BleakFxShaders.h"
#include "Engine/Source/BleakFx/BleakFxRipples.h"
#include "Engine/Source/ConsoleBase/ConsoleVar.h"
#include "Engine/Source/ConsoleBase/Types.h"
#include "Engine/Source/Gx/BleakDepth.h"
#include "Engine/Source/Gx/BleakGrassWind.h"
#include "Engine/Source/Gx/CGxDevice/CGxDevice.h"
#include "Engine/Source/Gx/CGxDevice/CGxShader.h"
#include "Engine/Source/Gx/CGxTex.h"
#include "Engine/Source/Gx/CGxTexFlags.h"
#include "Engine/Source/Gx/Gx.h"
#include "Engine/Source/Os/TimeManager.h"
#include "Engine/Source/Tempest/C2iVector.h"
#include "Engine/Source/Tempest/C2Vector.h"
#include "Engine/Source/Tempest/C44Matrix.h"
#include "Engine/Source/Tempest/CRect.h"
#include "ThirdParty/SMAA/AreaTex.h"
#include "ThirdParty/SMAA/SearchTex.h"

namespace {
    // Shader constant registers, as in Shaders/bh_common.hlsli and bh_fullscreen_vs.hlsl.
    const uint32_t kPsWater = 180;
    const uint32_t kPsParams = 200;
    const uint32_t kPsSky = 217;
    const uint32_t kPsProjection = 218;
    const uint32_t kPsInputTexel = 222;
    const uint32_t kPsOutputTexel = 223;
    const uint32_t kVsHalfPixel = 250;

    const uint32_t kMaxBloomLevels = 6;
    const int32_t kMinTargetSize = 8;
    const uint32_t kMaxInputs = 3;

    enum PixelShader {
        Ps_BloomPre,
        Ps_BloomDown,
        Ps_BloomUp,
        Ps_Composite,
        Ps_Fxaa,
        Ps_Cas,
        Ps_Ao,
        Ps_AoBlur,
        Ps_RaysMask,
        Ps_RaysBlur,
        Ps_DepthFx,
        Ps_DepthCopy,
        Ps_Water,
        Ps_Clear,
        Ps_SmaaEdge,
        Ps_SmaaWeights,
        Ps_SmaaBlend,
        Ps_Count,
    };

    struct Target {
        CGxTex* tex;
        int32_t width;
        int32_t height;
    };

    struct Settings {
        float bloom;
        float bloomThreshold;
        float clarity;
        float contrast;
        float saturation;
        float vibrance;
        float vignette;
        float warmth;
        float brightness;
        float shadows;
        bool fxaa;
        bool smaa;
        float sharpen;
        float ao;
        float aoRadius;
        float sunShafts;
    };

    CVar* s_cvarEnable;
    CVar* s_cvarBloom;
    CVar* s_cvarBloomThreshold;
    CVar* s_cvarClarity;
    CVar* s_cvarContrast;
    CVar* s_cvarSaturation;
    CVar* s_cvarVibrance;
    CVar* s_cvarVignette;
    CVar* s_cvarWarmth;
    CVar* s_cvarBrightness;
    CVar* s_cvarShadows;
    CVar* s_cvarAntiAliasing;
    CVar* s_cvarSharpen;
    CVar* s_cvarAo;
    CVar* s_cvarAoRadius;
    CVar* s_cvarSunShafts;
    CVar* s_cvarWater;
    CVar* s_cvarWaterRipples;
    CVar* s_cvarWaterReflections;
    CVar* s_cvarGrassWind;
    CVar* s_cvarGrassParting;

    // Created once and kept as long as the device: CGxDevice::ShaderDestroy frees a CGxShader but not its Direct3D
    // shader, and the device recreates the Direct3D shaders after a reset by itself.
    CGxShader* s_vertexShader;
    CGxShader* s_waterVertexShader;
    CGxShader* s_pixelShaders[Ps_Count];
    bool s_shadersCreated;

    // s_scene and s_post take turns holding the frame between passes.
    Target s_scene;
    Target s_post;
    Target s_bloomDown[kMaxBloomLevels];
    Target s_bloomUp[kMaxBloomLevels];
    Target s_ao[2];
    Target s_rays[2];
    // The frame and its view depth before the transparent liquids, for the water.
    Target s_waterScene;
    Target s_waterDepth;
    CGxTex* s_rippleTex;
    // SMAA: its blending weights (full size), and its area and search textures. Made when SMAA is first used.
    Target s_smaaWeights;
    CGxTex* s_smaaArea;
    CGxTex* s_smaaSearch;
    bool s_smaaFailed;
    uint32_t s_bloomLevels;
    int32_t s_width;
    int32_t s_height;
    bool s_targetsFailed;

    // Whether the last frame went through the chain with bloom, which then stands in for the stock glow.
    bool s_bloomRan;

    // From BeginWorld: the readable depth buffer is in use, the camera the world is drawn with, and its light.
    bool s_depthReady;
    C44Matrix s_projection;
    C44Matrix s_view;
    BleakFx::WorldLight s_light;

    // From RenderWorld: the sky showed the sun.
    bool s_sunVisible;

    // A pass could not draw into its target this frame: the passes after it do not draw either.
    bool s_passFailed;

    // From BeginLiquids: the water may draw this frame (the frame is copied), and with depth.
    bool s_waterReady;
    bool s_waterDepthReady;

    // From RenderWorld: the depth range of the world's viewport.
    float s_worldMinZ;
    float s_worldMaxZ;

    // The full-screen quad in clip space, as a strip: top left, top right, bottom left, bottom right.
    C3Vector s_quadPos[4] = { C3Vector(-1.0f, 1.0f, 0.0f), C3Vector(1.0f, 1.0f, 0.0f), C3Vector(-1.0f, -1.0f, 0.0f), C3Vector(1.0f, -1.0f, 0.0f) };
    C2Vector s_quadTex[4] = { C2Vector(0.0f, 0.0f), C2Vector(1.0f, 0.0f), C2Vector(0.0f, 1.0f), C2Vector(1.0f, 1.0f) };
    uint16_t s_quadIndices[4] = { 0, 1, 2, 3 };
    CGxBatch s_quadBatch = { GxPrim_TriangleStrip, 0, 4, 0, 3 };

    void NullTexUserFunc(EGxTexCommand command, uint32_t width, uint32_t height, uint32_t face, uint32_t level, void* userArg, uint32_t& texelStrideInBytes, const void*& texels) {
    }

    float Clamp(float value, float min, float max) {
        return value < min ? min : (value > max ? max : value);
    }

    float CVarFloat(CVar* var, float min, float max) {
        return var ? Clamp(var->m_floatValue, min, max) : min;
    }

#if BLEAKFX_HAVE_SHADERS
    CGxShader* CreateShader(EGxShTarget target, const char* name, const uint8_t* code, uint32_t size) {
        TSHashTable<CGxShader, HASHKEY_STRI>& list = g_theGxDevicePtr->m_shaderList[target];
        CGxShader* shader = list.Ptr(name);

        if (!shader) {
            shader = list.New(name, 0, 0);
            shader->m_target = target;
            shader->m_code.SetCount(size);
            memcpy(shader->m_code.m_data, code, size);
            shader->m_loaded = 0;
        }

        shader->m_refCount++;
        return shader;
    }
#endif

    bool ShadersValid() {
#if BLEAKFX_HAVE_SHADERS
#define BLEAKFX_SHADER(name) g_bleakFxShader_##name, sizeof(g_bleakFxShader_##name)
        if (!s_shadersCreated) {
            s_shadersCreated = true;
            s_vertexShader = CreateShader(GxSh_Vertex, "BleakFx:Fullscreen", BLEAKFX_SHADER(bh_fullscreen_vs));
            s_pixelShaders[Ps_BloomPre] = CreateShader(GxSh_Pixel, "BleakFx:BloomPre", BLEAKFX_SHADER(bh_bloom_pre_ps));
            s_pixelShaders[Ps_BloomDown] = CreateShader(GxSh_Pixel, "BleakFx:BloomDown", BLEAKFX_SHADER(bh_bloom_down_ps));
            s_pixelShaders[Ps_BloomUp] = CreateShader(GxSh_Pixel, "BleakFx:BloomUp", BLEAKFX_SHADER(bh_bloom_up_ps));
            s_pixelShaders[Ps_Composite] = CreateShader(GxSh_Pixel, "BleakFx:Composite", BLEAKFX_SHADER(bh_composite_ps));
            s_pixelShaders[Ps_Fxaa] = CreateShader(GxSh_Pixel, "BleakFx:Fxaa", BLEAKFX_SHADER(bh_fxaa_ps));
            s_pixelShaders[Ps_Cas] = CreateShader(GxSh_Pixel, "BleakFx:Cas", BLEAKFX_SHADER(bh_cas_ps));
            s_pixelShaders[Ps_Ao] = CreateShader(GxSh_Pixel, "BleakFx:Ao", BLEAKFX_SHADER(bh_ao_ps));
            s_pixelShaders[Ps_AoBlur] = CreateShader(GxSh_Pixel, "BleakFx:AoBlur", BLEAKFX_SHADER(bh_ao_blur_ps));
            s_pixelShaders[Ps_RaysMask] = CreateShader(GxSh_Pixel, "BleakFx:RaysMask", BLEAKFX_SHADER(bh_rays_mask_ps));
            s_pixelShaders[Ps_RaysBlur] = CreateShader(GxSh_Pixel, "BleakFx:RaysBlur", BLEAKFX_SHADER(bh_rays_blur_ps));
            s_pixelShaders[Ps_DepthFx] = CreateShader(GxSh_Pixel, "BleakFx:DepthFx", BLEAKFX_SHADER(bh_depthfx_ps));
            s_pixelShaders[Ps_DepthCopy] = CreateShader(GxSh_Pixel, "BleakFx:DepthCopy", BLEAKFX_SHADER(bh_depthcopy_ps));
            s_pixelShaders[Ps_Water] = CreateShader(GxSh_Pixel, "BleakFx:Water", BLEAKFX_SHADER(bh_water_ps));
            s_pixelShaders[Ps_Clear] = CreateShader(GxSh_Pixel, "BleakFx:Clear", BLEAKFX_SHADER(bh_clear_ps));
            s_pixelShaders[Ps_SmaaEdge] = CreateShader(GxSh_Pixel, "BleakFx:SmaaEdge", BLEAKFX_SHADER(bh_smaa_edge_ps));
            s_pixelShaders[Ps_SmaaWeights] = CreateShader(GxSh_Pixel, "BleakFx:SmaaWeights", BLEAKFX_SHADER(bh_smaa_weights_ps));
            s_pixelShaders[Ps_SmaaBlend] = CreateShader(GxSh_Pixel, "BleakFx:SmaaBlend", BLEAKFX_SHADER(bh_smaa_blend_ps));
            s_waterVertexShader = CreateShader(GxSh_Vertex, "BleakFx:WaterVs", BLEAKFX_SHADER(bh_water_vs));
        }
#undef BLEAKFX_SHADER

        // Valid() creates the Direct3D shader the first time and again after a device reset.
        if (!s_vertexShader->Valid() || !s_waterVertexShader->Valid()) {
            return false;
        }

        for (uint32_t i = 0; i < Ps_Count; i++) {
            if (!s_pixelShaders[i]->Valid()) {
                return false;
            }
        }

        return true;
#else
        return false;
#endif
    }

    bool DeviceSupported() {
        EGxApi api = g_theGxDevicePtr->DeviceApi();

        if (api != GxApi_D3d9 && api != GxApi_D3d9Ex) {
            return false;
        }

        const CGxCaps& caps = g_theGxDevicePtr->Caps();

        // ps_3_0 and vs_3_0 (the gxFixedFunction settings lower these), any texture size, 8-bit render targets.
        return caps.m_shaderTargets[GxSh_Pixel] == 4 && caps.m_shaderTargets[GxSh_Vertex] == 3 && caps.m_texTarget[GxTex_NonPow2] == 1 && caps.m_rttFormat[GxTex_Argb8888];
    }

    bool Enabled() {
        return s_cvarEnable && s_cvarEnable->m_intValue && g_theGxDevicePtr && g_theGxDevicePtr->m_context && DeviceSupported();
    }

    void DestroyTarget(Target& target) {
        if (target.tex) {
            GxTexDestroy(target.tex);
        }

        target.tex = nullptr;
        target.width = 0;
        target.height = 0;
    }

    void DestroyTargets() {
        DestroyTarget(s_scene);
        DestroyTarget(s_post);

        for (uint32_t i = 0; i < kMaxBloomLevels; i++) {
            DestroyTarget(s_bloomDown[i]);
            DestroyTarget(s_bloomUp[i]);
        }

        for (uint32_t i = 0; i < 2; i++) {
            DestroyTarget(s_ao[i]);
            DestroyTarget(s_rays[i]);
        }

        DestroyTarget(s_waterScene);
        DestroyTarget(s_waterDepth);
        DestroyTarget(s_smaaWeights);
        s_smaaFailed = false;

        s_bloomLevels = 0;
        s_width = 0;
        s_height = 0;
        s_targetsFailed = false;
    }

    bool CreateTarget(Target& target, int32_t width, int32_t height, const char* name, EGxTexFormat format = GxTex_Argb8888, EGxTexFilter filter = GxTex_Linear) {
        CGxTexFlags flags(filter, GxTex_Clamp, GxTex_Clamp, 0, 0, 1, 1);

        if (!GxTexCreate(GxTex_NonPow2, width, height, 0, format, format, flags, nullptr, NullTexUserFunc, name, target.tex)) {
            target.tex = nullptr;
            return false;
        }

        target.width = width;
        target.height = height;
        return true;
    }

    // Makes the targets for a back buffer of width x height. On failure everything is freed and nothing is tried
    // again until the size changes.
    bool EnsureTargets(int32_t width, int32_t height) {
        if (width == s_width && height == s_height) {
            return !s_targetsFailed;
        }

        DestroyTargets();
        s_width = width;
        s_height = height;

        // The depth effects run at half (ambient occlusion) and quarter (light shafts) size.
        bool ok = CreateTarget(s_scene, width, height, "BleakFx::Scene") && CreateTarget(s_post, width, height, "BleakFx::Post")
            && CreateTarget(s_waterScene, width, height, "BleakFx::WaterScene")
            && width / 4 >= kMinTargetSize && height / 4 >= kMinTargetSize
            && CreateTarget(s_ao[0], width / 2, height / 2, "BleakFx::Ao") && CreateTarget(s_ao[1], width / 2, height / 2, "BleakFx::Ao")
            && CreateTarget(s_rays[0], width / 4, height / 4, "BleakFx::Rays") && CreateTarget(s_rays[1], width / 4, height / 4, "BleakFx::Rays");

        int32_t levelWidth = width;
        int32_t levelHeight = height;

        while (ok && s_bloomLevels < kMaxBloomLevels) {
            levelWidth /= 2;
            levelHeight /= 2;

            if (levelWidth < kMinTargetSize || levelHeight < kMinTargetSize) {
                break;
            }

            ok = CreateTarget(s_bloomDown[s_bloomLevels], levelWidth, levelHeight, "BleakFx::BloomDown") && CreateTarget(s_bloomUp[s_bloomLevels], levelWidth, levelHeight, "BleakFx::BloomUp");
            s_bloomLevels++;
        }

        // The water's depth copy is optional (R32F render targets).
        if (ok && g_theGxDevicePtr->Caps().m_rttFormat[GxTex_R32F]) {
            CreateTarget(s_waterDepth, width, height, "BleakFx::WaterDepth", GxTex_R32F, GxTex_Nearest);
        }

        if (!ok || s_bloomLevels < 2) {
            DestroyTargets();
            s_width = width;
            s_height = height;
            s_targetsFailed = true;
            return false;
        }

        return true;
    }

    void SetPsVector(uint32_t reg, float x, float y, float z, float w) {
        float value[4] = { x, y, z, w };
        GxShaderConstantsSet(GxSh_Pixel, reg, value, 1);
    }

    // Draws the full-screen quad with pixel shader `ps` into `output` (nullptr: the back buffer), with `inputs` on
    // texture stages 0.. and their texel sizes in c222 - N.
    void RunPass(PixelShader ps, const Target* output, const Target* const* inputs, uint32_t count) {
        // After a failed pass the next ones would read a target holding nothing.
        if (s_passFailed) {
            return;
        }

        GxRenderTargetSet(GxBuffers_Color, output ? output->tex : nullptr, 0);

        // The device makes a target when it is first set; when it cannot, it draws into the back buffer instead.
        if (output && (output->tex->m_needsCreation || (!output->tex->m_apiSpecificData && !output->tex->m_apiSpecificData2))) {
            s_passFailed = true;
            return;
        }

        GxXformSetViewport(0.0f, 1.0f, 0.0f, 1.0f, 0.0f, 1.0f);

        float width = static_cast<float>(output ? output->width : s_width);
        float height = static_cast<float>(output ? output->height : s_height);

        float halfPixel[4] = { -1.0f / width, 1.0f / height, 0.0f, 0.0f };
        GxShaderConstantsSet(GxSh_Vertex, kVsHalfPixel, halfPixel, 1);
        SetPsVector(kPsOutputTexel, 1.0f / width, 1.0f / height, width, height);

        for (uint32_t i = 0; i < kMaxInputs; i++) {
            const Target* input = i < count ? inputs[i] : nullptr;
            GxRsSet(static_cast<EGxRenderState>(GxRs_Texture0 + i), input ? input->tex : nullptr);

            if (input) {
                SetPsVector(kPsInputTexel - i, 1.0f / input->width, 1.0f / input->height, static_cast<float>(input->width), static_cast<float>(input->height));
            }
        }

        GxRsSet(GxRs_PixelShader, s_pixelShaders[ps]);
        GxPrimVertexPtr(4, s_quadPos, sizeof(C3Vector), nullptr, 0, nullptr, 0, s_quadTex, sizeof(C2Vector), nullptr, 0);
        GxPrimIndexPtr(4, s_quadIndices);
        GxDraw(&s_quadBatch, 1);
    }

    void ReadSettings(Settings& settings, float zoneGlow) {
        // Zones made glowier by their light settings get up to a quarter more bloom, darker ones a quarter less.
        float glowScale = 0.75f + 0.5f * Clamp(zoneGlow, 0.0f, 1.0f);

        settings.bloom = CVarFloat(s_cvarBloom, 0.0f, 2.0f) * glowScale;
        settings.bloomThreshold = CVarFloat(s_cvarBloomThreshold, 0.0f, 1.0f);
        settings.clarity = CVarFloat(s_cvarClarity, 0.0f, 1.0f);
        settings.contrast = CVarFloat(s_cvarContrast, 0.0f, 1.0f);
        settings.saturation = CVarFloat(s_cvarSaturation, 0.0f, 2.0f);
        settings.vibrance = CVarFloat(s_cvarVibrance, -1.0f, 1.0f);
        settings.vignette = CVarFloat(s_cvarVignette, 0.0f, 1.0f);
        settings.warmth = CVarFloat(s_cvarWarmth, -1.0f, 1.0f);
        settings.brightness = CVarFloat(s_cvarBrightness, 0.5f, 1.5f);
        settings.shadows = CVarFloat(s_cvarShadows, -0.05f, 0.1f);
        int32_t antiAliasing = s_cvarAntiAliasing ? s_cvarAntiAliasing->m_intValue : 0;
        settings.fxaa = antiAliasing == 1;
        settings.smaa = antiAliasing == 2;
        settings.sharpen = CVarFloat(s_cvarSharpen, 0.0f, 1.0f);
        settings.ao = CVarFloat(s_cvarAo, 0.0f, 1.0f);
        settings.aoRadius = CVarFloat(s_cvarAoRadius, 0.25f, 5.0f);
        settings.sunShafts = CVarFloat(s_cvarSunShafts, 0.0f, 1.0f);
    }

    // Whether a viewport (0 - 1 of the window, as GxXformViewport gives it) covers the whole window.
    bool FillsWindow(float minX, float maxX, float minY, float maxY) {
        const float slack = 0.001f;
        return minX <= slack && minY <= slack && maxX >= 1.0f - slack && maxY >= 1.0f - slack;
    }

    // The depth effects, and the water's reflections, foam and soft shoreline.
    bool WantsDepth() {
        return CVarFloat(s_cvarAo, 0.0f, 1.0f) > 0.0f || CVarFloat(s_cvarSunShafts, 0.0f, 1.0f) > 0.0f || (s_cvarWater && s_cvarWater->m_intValue);
    }

    // Where the sun is on the screen: uv in x and y, and in z how strongly it shines into the view (0 when it is
    // behind the camera, below the horizon or far off the screen).
    void SunOnScreen(const C3Vector& direction, float result[3]) {
        result[0] = 0.5f;
        result[1] = 0.5f;
        result[2] = 0.0f;

        // A direction has no translation: only the 3x3 parts of the row-vector view and projection matrices.
        const C44Matrix& v = s_view;
        const C44Matrix& p = s_projection;
        float vx = direction.x * v.a0 + direction.y * v.b0 + direction.z * v.c0;
        float vy = direction.x * v.a1 + direction.y * v.b1 + direction.z * v.c1;
        float vz = direction.x * v.a2 + direction.y * v.b2 + direction.z * v.c2;
        float cx = vx * p.a0 + vy * p.b0 + vz * p.c0;
        float cy = vx * p.a1 + vy * p.b1 + vz * p.c1;
        float cw = vx * p.a3 + vy * p.b3 + vz * p.c3;

        if (cw <= 0.001f) {
            return;
        }

        float nx = cx / cw;
        float ny = cy / cw;
        float offScreen = fabsf(nx) > fabsf(ny) ? fabsf(nx) : fabsf(ny);

        result[0] = nx * 0.5f + 0.5f;
        result[1] = 0.5f - ny * 0.5f;
        result[2] = Clamp((1.6f - offScreen) / 0.6f, 0.0f, 1.0f) * Clamp(direction.z * 6.0f, 0.0f, 1.0f);
    }

    // A perspective projection with a far plane is needed to turn depth back into distance.
    bool PerspectiveProjection(const C44Matrix& p) {
        return p.a0 != 0.0f && p.b1 != 0.0f && p.d3 == 0.0f && fabsf(1.0f - p.c2) >= 1e-6f;
    }

    // Sets c218 and c217 of the depth shaders (bh_common.hlsli) for projection p and a world drawn into the depth range
    // [minZ, maxZ] of its viewport. Returns false when p cannot turn depth back into distance.
    bool SetDepthConstants(const C44Matrix& p, float minZ, float maxZ) {
        if (!PerspectiveProjection(p) || !(maxZ > minZ)) {
            return false;
        }

        // The projection gives c2 + d2 / z for view depth z, which the viewport maps into [minZ, maxZ]: the world is
        // drawn into [0, 0.94] (CWorld::s_unk_ADEEE4), the horizon and the sky beyond it. The depth buffer then holds
        // c2' + d2' / z.
        float range = maxZ - minZ;
        float c2 = minZ + range * p.c2;
        float d2 = range * p.d2;
        float farPlane = p.d2 / (1.0f - p.c2);
        SetPsVector(kPsProjection, 1.0f / p.a0, 1.0f / p.b1, c2, d2);

        // Open sky: beyond 60% of the far plane, or no world at all (horizon, sky, never drawn: maxZ and up).
        SetPsVector(kPsSky, c2 + d2 / (0.6f * farPlane), maxZ, 0.0f, 0.0f);
        return true;
    }

    // Ambient occlusion and light shafts into s_post. Returns false (and draws nothing) when there is nothing to do.
    bool RenderDepthEffects(const Settings& settings, const BleakFx::WorldLight& light) {
        Target depth = { GxBleakDepthTexture(), s_width, s_height };
        const C44Matrix& p = s_projection;

        if (!depth.tex) {
            return false;
        }

        float sun[3];
        SunOnScreen(light.sunDirection, sun);

        bool ao = settings.ao > 0.0f;
        bool rays = settings.sunShafts > 0.0f && s_sunVisible && sun[2] > 0.0f;

        if ((!ao && !rays) || !SetDepthConstants(p, s_worldMinZ, s_worldMaxZ)) {
            return false;
        }

        const Target* inputs[3];

        if (ao) {
            float fadeEnd = light.fogEnd > 0.0f && light.fogEnd * 0.8f < 160.0f ? light.fogEnd * 0.8f : 160.0f;
            float pixelsPerYard = 0.5f * s_height * fabsf(p.b1);

            inputs[0] = &depth;
            SetPsVector(kPsParams + 0, settings.aoRadius, 1.6f, 0.0012f, pixelsPerYard);
            SetPsVector(kPsParams + 1, fadeEnd * 0.4f, fadeEnd, 0.0f, 0.0f);
            RunPass(Ps_Ao, &s_ao[0], inputs, 1);

            inputs[1] = &depth;
            inputs[0] = &s_ao[0];
            SetPsVector(kPsParams, 1.0f / s_ao[0].width, 0.0f, 0.05f, 0.0f);
            RunPass(Ps_AoBlur, &s_ao[1], inputs, 2);

            inputs[0] = &s_ao[1];
            SetPsVector(kPsParams, 0.0f, 1.0f / s_ao[0].height, 0.05f, 0.0f);
            RunPass(Ps_AoBlur, &s_ao[0], inputs, 2);
        }

        if (rays) {
            inputs[0] = &s_scene;
            inputs[1] = &depth;
            SetPsVector(kPsParams, sun[0], sun[1], sun[2], 0.22f);
            RunPass(Ps_RaysMask, &s_rays[0], inputs, 2);

            inputs[0] = &s_rays[0];
            SetPsVector(kPsParams + 1, 0.9f, 0.95f, 0.0f, 0.0f);
            RunPass(Ps_RaysBlur, &s_rays[1], inputs, 1);

            inputs[0] = &s_rays[1];
            SetPsVector(kPsParams + 1, 0.4f, 0.9f, 0.0f, 0.0f);
            RunPass(Ps_RaysBlur, &s_rays[0], inputs, 1);
        }

        // An unused input still needs a texture; its strength is 0.
        inputs[0] = &s_scene;
        inputs[1] = ao ? &s_ao[0] : &s_scene;
        inputs[2] = rays ? &s_rays[0] : &s_scene;
        float r = light.sunColor.r / 255.0f;
        float g = light.sunColor.g / 255.0f;
        float b = light.sunColor.b / 255.0f;
        SetPsVector(kPsParams + 0, ao ? settings.ao : 0.0f, rays ? settings.sunShafts : 0.0f, 0.0f, 0.0f);
        SetPsVector(kPsParams + 1, r * r, g * g, b * b, 1.0f);
        RunPass(Ps_DepthFx, &s_post, inputs, 3);
        return true;
    }

    void RenderBloom(const Settings& settings, const Target* frame) {
        const Target* inputs[2];

        inputs[0] = frame;
        SetPsVector(kPsParams, settings.bloomThreshold, 0.5f, 0.0f, 0.0f);
        RunPass(Ps_BloomPre, &s_bloomDown[0], inputs, 1);

        for (uint32_t i = 1; i < s_bloomLevels; i++) {
            inputs[0] = &s_bloomDown[i - 1];
            RunPass(Ps_BloomDown, &s_bloomDown[i], inputs, 1);
        }

        // Back up the pyramid: each level blends the tent-filtered smaller level into its own downsample.
        SetPsVector(kPsParams, 1.0f, 1.5f, 0.0f, 0.0f);
        const Target* smaller = &s_bloomDown[s_bloomLevels - 1];

        for (int32_t i = static_cast<int32_t>(s_bloomLevels) - 2; i >= 0; i--) {
            inputs[0] = smaller;
            inputs[1] = &s_bloomDown[i];
            RunPass(Ps_BloomUp, &s_bloomUp[i], inputs, 2);
            smaller = &s_bloomUp[i];
        }
    }

    // SMAA's area texture (two channels) and search texture (one channel) as A8R8G8B8, bytes b, g, r, a: the data
    // in red and green (bh_smaa_common.hlsli).
    void SmaaAreaTexUserFunc(EGxTexCommand command, uint32_t width, uint32_t height, uint32_t face, uint32_t level, void* userArg, uint32_t& texelStrideInBytes, const void*& texels) {
        static uint8_t s_texels[AREATEX_WIDTH * AREATEX_HEIGHT * 4];
        static bool s_made;

        if (command != GxTex_Latch) {
            return;
        }

        if (!s_made) {
            for (uint32_t i = 0; i < AREATEX_WIDTH * AREATEX_HEIGHT; i++) {
                s_texels[i * 4 + 0] = 0;
                s_texels[i * 4 + 1] = areaTexBytes[i * 2 + 1];
                s_texels[i * 4 + 2] = areaTexBytes[i * 2 + 0];
                s_texels[i * 4 + 3] = 255;
            }

            s_made = true;
        }

        texels = s_texels;
        texelStrideInBytes = AREATEX_WIDTH * 4;
    }

    void SmaaSearchTexUserFunc(EGxTexCommand command, uint32_t width, uint32_t height, uint32_t face, uint32_t level, void* userArg, uint32_t& texelStrideInBytes, const void*& texels) {
        static uint8_t s_texels[SEARCHTEX_WIDTH * SEARCHTEX_HEIGHT * 4];
        static bool s_made;

        if (command != GxTex_Latch) {
            return;
        }

        if (!s_made) {
            for (uint32_t i = 0; i < SEARCHTEX_WIDTH * SEARCHTEX_HEIGHT; i++) {
                s_texels[i * 4 + 0] = 0;
                s_texels[i * 4 + 1] = 0;
                s_texels[i * 4 + 2] = searchTexBytes[i];
                s_texels[i * 4 + 3] = 255;
            }

            s_made = true;
        }

        texels = s_texels;
        texelStrideInBytes = SEARCHTEX_WIDTH * 4;
    }

    // SMAA's resources for the current targets; false when they cannot be made (FXAA then stands in).
    bool EnsureSmaa() {
        if (s_smaaFailed) {
            return false;
        }

        CGxTexFlags flags(GxTex_Linear, GxTex_Clamp, GxTex_Clamp, 0, 0, 0, 1);

        if (!s_smaaArea && !GxTexCreate(GxTex_NonPow2, AREATEX_WIDTH, AREATEX_HEIGHT, 0, GxTex_Argb8888, GxTex_Argb8888, flags, nullptr, SmaaAreaTexUserFunc, "BleakFx::SmaaArea", s_smaaArea)) {
            s_smaaArea = nullptr;
        }

        if (!s_smaaSearch && !GxTexCreate(GxTex_2d, SEARCHTEX_WIDTH, SEARCHTEX_HEIGHT, 0, GxTex_Argb8888, GxTex_Argb8888, flags, nullptr, SmaaSearchTexUserFunc, "BleakFx::SmaaSearch", s_smaaSearch)) {
            s_smaaSearch = nullptr;
        }

        if (!s_smaaWeights.tex) {
            CreateTarget(s_smaaWeights, s_width, s_height, "BleakFx::SmaaWeights");
        }

        s_smaaFailed = !s_smaaArea || !s_smaaSearch || !s_smaaWeights.tex;
        return !s_smaaFailed;
    }

    void RenderChain(const Settings& settings, const BleakFx::WorldLight& light) {
        // The frame is in s_scene; each pass writes into the other of s_scene and s_post, the last one into the back
        // buffer.
        Target* frame = &s_scene;
        Target* spare = &s_post;

        if (s_depthReady && RenderDepthEffects(settings, light)) {
            frame = &s_post;
            spare = &s_scene;
        }

        bool pyramid = settings.bloom > 0.0f || settings.clarity > 0.0f;

        if (pyramid) {
            RenderBloom(settings, frame);
        }

        bool sharpen = settings.sharpen > 0.0f;
        bool smaa = settings.smaa && EnsureSmaa();
        bool fxaa = settings.fxaa || (settings.smaa && !smaa);
        const Target* inputs[3];

        // Without the pyramid the frame stands in for it; bloom and clarity are then 0 and do not read it.
        inputs[0] = frame;
        inputs[1] = pyramid ? &s_bloomUp[0] : frame;
        float lift = settings.shadows;
        float warm = settings.warmth * 0.06f;
        SetPsVector(kPsParams + 0, pyramid ? settings.bloom : 0.0f, settings.contrast, settings.saturation, settings.vibrance);
        SetPsVector(kPsParams + 1, settings.vignette, 1.0f, pyramid ? settings.clarity : 0.0f, 0.42f);
        SetPsVector(kPsParams + 2, lift, lift, lift * 1.5f, 0.0f);
        SetPsVector(kPsParams + 3, settings.brightness, settings.brightness, settings.brightness, 1.0f);
        SetPsVector(kPsParams + 4, 1.0f + warm, 1.0f, 1.0f - warm, 1.0f);
        RunPass(Ps_Composite, fxaa || smaa || sharpen ? spare : nullptr, inputs, 2);

        Target* composed = spare;

        if (smaa) {
            // The edges go into the frame's target, free after the composite. The edge pass discards the pixels
            // without an edge, so the target is cleared first.
            RunPass(Ps_Clear, frame, inputs, 0);
            inputs[0] = composed;
            RunPass(Ps_SmaaEdge, frame, inputs, 1);

            Target area = { s_smaaArea, AREATEX_WIDTH, AREATEX_HEIGHT };
            Target search = { s_smaaSearch, SEARCHTEX_WIDTH, SEARCHTEX_HEIGHT };
            inputs[0] = frame;
            inputs[1] = &area;
            inputs[2] = &search;
            RunPass(Ps_SmaaWeights, &s_smaaWeights, inputs, 3);

            inputs[0] = composed;
            inputs[1] = &s_smaaWeights;
            RunPass(Ps_SmaaBlend, sharpen ? frame : nullptr, inputs, 2);
            composed = frame;
        } else if (fxaa) {
            inputs[0] = composed;
            SetPsVector(kPsParams, 0.75f, 0.125f, 0.0312f, 0.0f);
            RunPass(Ps_Fxaa, sharpen ? frame : nullptr, inputs, 1);
            composed = frame;
        }

        if (sharpen) {
            inputs[0] = composed;
            SetPsVector(kPsParams, settings.sharpen, 0.0f, 0.0f, 0.0f);
            RunPass(Ps_Cas, nullptr, inputs, 1);
        }
    }

    void RippleTexUserFunc(EGxTexCommand command, uint32_t width, uint32_t height, uint32_t face, uint32_t level, void* userArg, uint32_t& texelStrideInBytes, const void*& texels) {
        if (command != GxTex_Latch) {
            return;
        }

        uint32_t clamped = level < BleakFxRipples::kLevels ? level : BleakFxRipples::kLevels - 1;
        texels = BleakFxRipples::Levels() + BleakFxRipples::LevelOffset(clamped);
        texelStrideInBytes = BleakFxRipples::LevelSize(clamped) * 4;
    }

    // The ripple texture, made the first time the water draws (a managed texture: it survives device resets).
    CGxTex* RippleTexture() {
        if (!s_rippleTex) {
            CGxTexFlags flags(GxTex_LinearMipLinear, GxTex_Wrap, GxTex_Wrap, 0, 0, 0, 1);

            if (!GxTexCreate(GxTex_2d, BleakFxRipples::kSize, BleakFxRipples::kSize, 0, GxTex_Argb8888, GxTex_Argb8888, flags, nullptr, RippleTexUserFunc, "BleakFx::Ripples", s_rippleTex)) {
                s_rippleTex = nullptr;
            }
        }

        return s_rippleTex;
    }

    bool WindowSize(int32_t& width, int32_t& height) {
        const CRect& window = g_theGxDevicePtr->DeviceDefWindow();
        width = static_cast<int32_t>(window.maxX - window.minX);
        height = static_cast<int32_t>(window.maxY - window.minY);
        return width >= kMinTargetSize && height >= kMinTargetSize;
    }

    float Linear(uint8_t channel) {
        float c = channel / 255.0f;
        return c * c;
    }

    double Fraction(double value) {
        return value - floor(value);
    }
}

void BleakFx::Init() {
    s_cvarEnable = CVar::Register("bleakFx", "Bleakhold post-processing of the 3D world", 0x1, "1", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarBloom = CVar::Register("bleakFxBloom", "Bloom strength (0 - 2, 0 = off)", 0x1, "0.35", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarBloomThreshold = CVar::Register("bleakFxBloomThreshold", "Brightness where bloom starts (0 - 1)", 0x1, "0.8", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarClarity = CVar::Register("bleakFxClarity", "Local contrast (0 - 1)", 0x1, "0.35", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarContrast = CVar::Register("bleakFxContrast", "Filmic contrast curve (0 - 1)", 0x1, "0.18", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarSaturation = CVar::Register("bleakFxSaturation", "Colour saturation (0 - 2, 1 = unchanged)", 0x1, "1.05", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarVibrance = CVar::Register("bleakFxVibrance", "Saturation of dull colours (-1 - 1)", 0x1, "0.25", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarVignette = CVar::Register("bleakFxVignette", "Darker screen corners (0 - 1)", 0x1, "0.18", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarWarmth = CVar::Register("bleakFxWarmth", "Colour temperature (-1 cool - 1 warm)", 0x1, "0.3", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarBrightness = CVar::Register("bleakFxBrightness", "Midtone brightness (0.5 - 1.5, 1 = unchanged)", 0x1, "1", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarShadows = CVar::Register("bleakFxShadows", "Shadow lift (-0.05 - 0.1)", 0x1, "0.012", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarAntiAliasing = CVar::Register("bleakFxAA", "Post-process anti-aliasing (0 off, 1 FXAA, 2 SMAA)", 0x1, "2", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarSharpen = CVar::Register("bleakFxSharpen", "Contrast-adaptive sharpening (0 - 1, 0 = off)", 0x1, "0.25", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarAo = CVar::Register("bleakFxAO", "Ambient occlusion strength (0 - 1, 0 = off; needs multisampling off)", 0x1, "0.6", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarAoRadius = CVar::Register("bleakFxAORadius", "Ambient occlusion radius in yards (0.25 - 5)", 0x1, "1.5", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarSunShafts = CVar::Register("bleakFxSunShafts", "Light shafts from the sun (0 - 1, 0 = off; needs multisampling off)", 0x1, "0.4", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarWater = CVar::Register("bleakFxWater", "Water with reflections, refraction and colour by depth (1 on, 0 the stock water)", 0x1, "1", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarWaterRipples = CVar::Register("bleakFxWaterRipples", "Water ripple strength (0 - 0.4)", 0x1, "0.12", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarGrassWind = CVar::Register("bleakFxGrassWind", "Wind in the grass (0 still - 2, 1 = a breeze)", 0x1, "1", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarGrassParting = CVar::Register("bleakFxGrassParting", "Grass bends away from the player (1 on, 0 off)", 0x1, "1", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
    s_cvarWaterReflections = CVar::Register("bleakFxWaterReflections", "Water reflects the world, not only the sky (1 on, 0 off; needs multisampling off)", 0x1, "1", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
}

void BleakFx::Destroy() {
    DestroyTargets();

    if (s_rippleTex) {
        GxTexDestroy(s_rippleTex);
        s_rippleTex = nullptr;
    }

    if (s_smaaArea) {
        GxTexDestroy(s_smaaArea);
        s_smaaArea = nullptr;
    }

    if (s_smaaSearch) {
        GxTexDestroy(s_smaaSearch);
        s_smaaSearch = nullptr;
    }

    s_waterReady = false;
    s_waterDepthReady = false;
    GxBleakDepthSet(false);
    GxBleakDepthDestroyHandle();
    s_bloomRan = false;
    s_depthReady = false;
}

void BleakFx::BeginLiquids() {
    s_waterReady = false;
    s_waterDepthReady = false;

    if (!Enabled() || !s_cvarWater || !s_cvarWater->m_intValue || !ShadersValid()) {
        return;
    }

    // The world draws into the back buffer and fills the window (the water maps the whole window); never copy
    // anything else.
    CGxTex* renderTarget;
    g_theGxDevicePtr->DeviceGetRenderTarget(GxBuffers_Color, renderTarget);
    float minX, maxX, minY, maxY, minZ, maxZ;
    GxXformViewport(minX, maxX, minY, maxY, minZ, maxZ);
    int32_t width, height;

    if (renderTarget || !FillsWindow(minX, maxX, minY, maxY) || !WindowSize(width, height) || !EnsureTargets(width, height)) {
        return;
    }

    C2iVector origin = { 0, 0 };
    C2iVector size = { width, height };

    if (!GxTexCopy(s_waterScene.tex, origin, origin, size, 0, 0)) {
        return;
    }

    s_waterReady = true;

    // The depth as view depth in yards, from the readable depth buffer (which stays bound for the world).
    Target depth = { GxBleakDepthTexture(), s_width, s_height };

    if (!s_depthReady || !depth.tex || !s_waterDepth.tex || !PerspectiveProjection(s_projection) || !(maxZ > minZ)) {
        return;
    }

    g_theGxDevicePtr->RsPush();
    GxRsSet(GxRs_BlendingMode, GxBlend_Opaque);
    GxRsSet(GxRs_AlphaRef, 0);
    GxRsSet(GxRs_DepthTest, 0);
    GxRsSet(GxRs_DepthWrite, 0);
    GxRsSet(GxRs_ColorWrite, 15);
    GxRsSet(GxRs_Culling, 0);
    GxRsSet(GxRs_Fog, 0);
    GxRsSet(GxRs_Lighting, 0);
    GxRsSet(GxRs_ScissorTest, 0);
    GxRsSet(GxRs_ClipPlaneMask, 0);
    GxRsSet(GxRs_VertexShader, s_vertexShader);

    const Target* inputs[1] = { &depth };
    SetDepthConstants(s_projection, minZ, maxZ);
    s_passFailed = false;
    RunPass(Ps_DepthCopy, &s_waterDepth, inputs, 1);

    g_theGxDevicePtr->RsPop();
    GxRenderTargetSet(GxBuffers_Color, nullptr, 0);
    GxXformSetViewport(minX, maxX, minY, maxY, minZ, maxZ);

    // Without its target the water goes on without depth (not tried again until the targets are made again).
    if (s_passFailed) {
        DestroyTarget(s_waterDepth);
        s_passFailed = false;
        return;
    }

    s_waterDepthReady = true;
}

bool BleakFx::BindWater(const WaterDraw& draw) {
    if (!s_waterReady || !Enabled() || !s_cvarWater || !s_cvarWater->m_intValue || !ShadersValid()) {
        return false;
    }

    CGxTex* ripples = RippleTexture();

    if (!ripples) {
        return false;
    }

    C44Matrix v;
    GxXformView(v);
    const C44Matrix& p = g_theGxDevicePtr->m_projNative;

    // Stages 0 and 1 hold the stock textures (depth gradient, animated surface).
    g_theGxDevicePtr->RsSet(GxRs_VertexShader, s_waterVertexShader);
    g_theGxDevicePtr->RsSet(GxRs_PixelShader, s_pixelShaders[Ps_Water]);
    g_theGxDevicePtr->RsSet(GxRs_Texture2, s_waterScene.tex);
    g_theGxDevicePtr->RsSet(GxRs_Texture3, s_waterDepthReady ? s_waterDepth.tex : s_waterScene.tex);
    g_theGxDevicePtr->RsSet(GxRs_Texture4, ripples);

    // The ripple speeds below make whole cycles in 1000 seconds, so the clock wraps there without a jump.
    double seconds = (OsGetAsyncTimeMs() % 1000000u) / 1000.0;
    bool reflections = s_cvarWaterReflections && s_cvarWaterReflections->m_intValue;
    SetPsVector(kPsWater + 0, static_cast<float>(seconds), s_waterDepthReady ? 1.0f : 0.0f, 0.04f, reflections ? 1.0f : 0.0f);

    // Directions have no translation: the 3x3 part of the row-vector view matrix.
    const C3Vector& sun = s_light.sunDirection;
    float sx = sun.x * v.a0 + sun.y * v.b0 + sun.z * v.c0;
    float sy = sun.x * v.a1 + sun.y * v.b1 + sun.z * v.c1;
    float sz = sun.x * v.a2 + sun.y * v.b2 + sun.z * v.c2;
    SetPsVector(kPsWater + 1, sx, sy, sz, draw.sunVisible ? Clamp(sun.z * 6.0f, 0.0f, 1.0f) : 0.0f);
    SetPsVector(kPsWater + 2, Linear(s_light.sunColor.r), Linear(s_light.sunColor.g), Linear(s_light.sunColor.b), 0.6f);
    SetPsVector(kPsWater + 3, Linear(s_light.skyZenith.r), Linear(s_light.skyZenith.g), Linear(s_light.skyZenith.b), 0.0f);
    SetPsVector(kPsWater + 4, Linear(s_light.skyHorizon.r), Linear(s_light.skyHorizon.g), Linear(s_light.skyHorizon.b), 0.0f);
    SetPsVector(kPsWater + 5, 1.0f / s_width, 1.0f / s_height, static_cast<float>(s_width), static_cast<float>(s_height));
    SetPsVector(kPsWater + 6, p.a0, p.b1, 0.0f, 0.0f);
    SetPsVector(kPsWater + 7, CVarFloat(s_cvarWaterRipples, 0.0f, 0.4f), 1.0f, 4.67f, 1.0f);

    float upLength = sqrtf(v.c0 * v.c0 + v.c1 * v.c1 + v.c2 * v.c2);
    upLength = upLength > 0.0f ? upLength : 1.0f;
    SetPsVector(kPsWater + 8, v.c0 / upLength, v.c1 / upLength, v.c2 / upLength, 0.0f);

    // View to world: the transpose of the view rotation (orthonormal).
    SetPsVector(kPsWater + 9, v.a0, v.b0, v.c0, 0.0f);
    SetPsVector(kPsWater + 10, v.a1, v.b1, v.c1, 0.0f);
    SetPsVector(kPsWater + 11, v.a2, v.b2, v.c2, 0.0f);

    // Two ripple layers in world space; the shader adds the camera-relative part, so the large world
    // coordinates are reduced here, in double precision.
    const double scaleA = 1.0 / 7.0;
    const double scaleB = 1.0 / 4.3;
    const double angle = 0.9;
    double cosB = cos(angle);
    double sinB = sin(angle);
    double camX = draw.cameraPos.x;
    double camY = draw.cameraPos.y;
    double turnedX = camX * cosB + camY * sinB;
    double turnedY = -camX * sinB + camY * cosB;
    SetPsVector(kPsWater + 12, static_cast<float>(Fraction(camX * scaleA + seconds * 0.031)), static_cast<float>(Fraction(camY * scaleA + seconds * 0.017)), static_cast<float>(scaleA), 0.0f);
    SetPsVector(kPsWater + 13, static_cast<float>(Fraction(turnedX * scaleB - seconds * 0.023)), static_cast<float>(Fraction(turnedY * scaleB + seconds * 0.041)), static_cast<float>(scaleB), 0.0f);
    SetPsVector(kPsWater + 14, static_cast<float>(cosB), static_cast<float>(sinB), static_cast<float>(-sinB), static_cast<float>(cosB));
    SetPsVector(kPsWater + 15, draw.fogScale, draw.fogOffset, 0.0f, 0.0f);
    return true;
}

void BleakFx::PatchGrassShaders(CGxShader** shaders, uint32_t count) {
    if (!g_theGxDevicePtr || !DeviceSupported()) {
        return;
    }

    for (uint32_t i = 0; i < count; i++) {
        CGxShader* shader = shaders[i];

        // Only code the device has not made a shader of yet (Valid() makes it from m_code).
        if (!shader || shader->m_loaded || !shader->m_code.Count()) {
            continue;
        }

        std::vector<uint8_t> patched;

        if (BleakGrassWindPatch(shader->m_code.m_data, shader->m_code.Count(), patched)) {
            shader->m_code.SetCount(static_cast<uint32_t>(patched.size()));
            memcpy(shader->m_code.m_data, patched.data(), patched.size());
        }
    }
}

void BleakFx::SetGrassWind(const C3Vector& camera, const C3Vector* player) {
    if (!g_theGxDevicePtr || !DeviceSupported()) {
        return;
    }

    bool on = Enabled();
    C44Matrix v;
    GxXformView(v);

    // The world position the grass shaders' view space starts from: the camera, moved by what the view matrix
    // translates (the grass batches are placed relative to the camera, CWorldScene::RenderDetailDoodads).
    BleakGrassWindInput input;
    input.camera[0] = camera.x - (v.d0 * v.a0 + v.d1 * v.a1 + v.d2 * v.a2);
    input.camera[1] = camera.y - (v.d0 * v.b0 + v.d1 * v.b1 + v.d2 * v.b2);
    input.camera[2] = camera.z - (v.d0 * v.c0 + v.d1 * v.c1 + v.d2 * v.c2);
    input.hasPlayer = player != nullptr;
    input.player[0] = player ? player->x : 0.0f;
    input.player[1] = player ? player->y : 0.0f;
    input.player[2] = player ? player->z : 0.0f;
    input.seconds = OsGetAsyncTimeMs() / 1000.0;
    input.strength = on ? CVarFloat(s_cvarGrassWind, 0.0f, 2.0f) : 0.0f;
    input.parting = on && s_cvarGrassParting && s_cvarGrassParting->m_intValue;

    float constants[BLEAKGRASSWIND_CONSTANT_COUNT][4];
    BleakGrassWindConstants(input, constants);
    GxShaderConstantsSet(GxSh_Vertex, BLEAKGRASSWIND_FIRST_CONSTANT, &constants[0][0], BLEAKGRASSWIND_CONSTANT_COUNT);
}

bool BleakFx::ReplacesStockGlow() {
    return s_bloomRan;
}

void BleakFx::BeginWorld(const WorldLight& light) {
    s_light = light;
    s_waterReady = false;
    s_waterDepthReady = false;

    bool enabled = Enabled();
    s_depthReady = GxBleakDepthSet(enabled && WantsDepth() && ShadersValid());

    if (s_depthReady) {
        s_projection = g_theGxDevicePtr->m_projNative;
        GxXformView(s_view);
    }
}

void BleakFx::RenderWorld(bool sunVisible) {
    s_bloomRan = false;
    s_sunVisible = sunVisible;

    // The frame copy is this world pass's; nothing drawn after it may use it.
    s_waterReady = false;
    s_waterDepthReady = false;

    if (!Enabled()) {
        return;
    }

    // Only the frame in the back buffer, never a world drawn into a texture.
    CGxTex* renderTarget;
    g_theGxDevicePtr->DeviceGetRenderTarget(GxBuffers_Color, renderTarget);

    if (renderTarget) {
        return;
    }

    int32_t width, height;

    // The world's viewport: the effects map the whole window.
    float minX, maxX, minY, maxY, minZ, maxZ;
    GxXformViewport(minX, maxX, minY, maxY, minZ, maxZ);

    if (!FillsWindow(minX, maxX, minY, maxY) || !WindowSize(width, height) || !ShadersValid() || !EnsureTargets(width, height)) {
        return;
    }

    C2iVector origin = { 0, 0 };
    C2iVector size = { width, height };

    if (!GxTexCopy(s_scene.tex, origin, origin, size, 0, 0)) {
        return;
    }

    Settings settings;
    ReadSettings(settings, s_light.zoneGlow);
    s_worldMinZ = minZ;
    s_worldMaxZ = maxZ;

    g_theGxDevicePtr->RsPush();
    GxRsSet(GxRs_BlendingMode, GxBlend_Opaque);
    GxRsSet(GxRs_AlphaRef, 0);
    GxRsSet(GxRs_DepthTest, 0);
    GxRsSet(GxRs_DepthWrite, 0);
    GxRsSet(GxRs_ColorWrite, 15);
    GxRsSet(GxRs_Culling, 0);
    GxRsSet(GxRs_Fog, 0);
    GxRsSet(GxRs_Lighting, 0);
    GxRsSet(GxRs_ScissorTest, 0);
    GxRsSet(GxRs_ClipPlaneMask, 0);
    GxRsSet(GxRs_VertexShader, s_vertexShader);

    s_passFailed = false;
    RenderChain(settings, s_light);
    s_bloomRan = settings.bloom > 0.0f && !s_passFailed;

    g_theGxDevicePtr->RsPop();
    GxRenderTargetSet(GxBuffers_Color, nullptr, 0);
    GxXformSetViewport(minX, maxX, minY, maxY, minZ, maxZ);

    // A target the device could not make: the frame stays as the world drew it, and BleakFx stays off until the
    // window size changes.
    if (s_passFailed) {
        DestroyTargets();
        s_width = width;
        s_height = height;
        s_targetsFailed = true;
        s_passFailed = false;
    }
}
