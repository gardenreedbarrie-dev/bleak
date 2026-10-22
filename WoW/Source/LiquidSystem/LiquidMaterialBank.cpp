#include "Liquid.h"
#include "Engine/Source/Gx/CGxDevice/CGxDevice.h"
#include "Engine/Source/Gx/CGxDevice/CGxShader.h"
#include "Engine/Source/Services/SysMessage.h"
#include "WoW/Source/DB/WowClientDB.h"
#include "WoW/Source/DB/Rec/LiquidTypeRec.h"

// STATIC: 0x00D43B24
TSGrowableArray<Liquid::IMaterial*> Liquid::CMaterialBank::s_materials;

// VERIFY: 8e2d4258 manual
// OFFSET: 0x008A1F50
void Liquid::CMaterialBank::Destroy() {
    for (uint32_t i = 0; i < Liquid::CMaterialBank::s_materials.Count(); i++) {
        if (Liquid::CMaterialBank::s_materials[i]) {
            Liquid::CMaterialBank::s_materials[i]->Release();
        }
    }

    Liquid::CMaterialBank::s_materials.SetCount(0);
}

// VERIFY: 5f91fa25 auto
// OFFSET: 0x008A4280
void Liquid::ClearMaterials() {
    Liquid::s_procWaterAllocator.Clear(".?AVCMaterialProcWater@Liquid@@", SLOG_OBJECT, 1);
    Liquid::s_procWaterFFPAllocator.Clear(".?AVCMaterialProcWaterFFP@Liquid@@", SLOG_OBJECT, 1);
    Liquid::s_waterAllocator.Clear(".?AVCMaterialWater@Liquid@@", SLOG_OBJECT, 1);
    Liquid::s_waterNoSpecAllocator.Clear(".?AVCMaterialWaterNoSpec@Liquid@@", SLOG_OBJECT, 1);
    Liquid::s_waterFFPAllocator.Clear(".?AVCMaterialWaterFFP@Liquid@@", SLOG_OBJECT, 1);
    Liquid::s_magmaAllocator.Clear(".?AVCMaterialMagma@Liquid@@", SLOG_OBJECT, 1);
    Liquid::s_magmaFFPAllocator.Clear(".?AVCMaterialMagmaFFP@Liquid@@", SLOG_OBJECT, 1);
}

// BLEAKHOLD(procwater): the liquid type whose material and settings draw `liquidType`. With the proceduralWater
// CVar on, ordinary water and ocean (1, 2, 5, 6, 9, 10) draw with the procedural water the client ships for
// testing (liquid type 100: depth-tinted, refracting), the same rows modders copy type 100 over in
// LiquidType.dbc. Only the look changes: the liquid keeps its own type for sound, particles and swimming.
// The swap is skipped unless type 100 is that procedural material and its shaders load, so the setting can
// never leave water undrawn.
uint32_t Liquid::GetRenderLiquidType(uint32_t liquidType) {
    static const uint32_t s_proceduralWaterType = 100;

    if (!Liquid::s_proceduralWater) {
        return liquidType;
    }

    switch (liquidType) {
        case 1:
        case 2:
        case 5:
        case 6:
        case 9:
        case 10:
            break;
        default:
            return liquidType;
    }

    LiquidTypeRec* typeRec = Liquid::s_liquidTypeDB ? Liquid::s_liquidTypeDB->GetRecord(s_proceduralWaterType) : nullptr;

    if (!typeRec || typeRec->m_materialID != 3) {
        return liquidType;
    }

    if (!Liquid::CMaterialBank::GetMaterial(s_proceduralWaterType)) {
        return liquidType;
    }

    CGxShader* pixelShader = Liquid::CMaterialProcWater::s_pixelShader;

    if (!pixelShader || !pixelShader->Valid()) {
        return liquidType;
    }

    for (uint32_t i = 0; i < 4; i++) {
        CGxShader* vertexShader = Liquid::CMaterialProcWater::s_vertexShaders[i];

        if (!vertexShader || !vertexShader->Valid()) {
            return liquidType;
        }
    }

    return s_proceduralWaterType;
}

// VERIFY: 85245160 auto
// OFFSET: 0x008A1FA0
Liquid::IMaterial* Liquid::CMaterialBank::GetMaterial(uint32_t liquidType) {
    LiquidTypeRec* typeRec;

    while (true) {
        if (!Liquid::s_materialBankRefCount) {
            return nullptr;
        }

        typeRec = Liquid::s_liquidTypeDB->GetRecord(liquidType);

        if (typeRec) {
            break;
        }

        SysMsgPrintf(STATUS_ERROR, 2, "Material Bank: Liquid type [%d] not found, defaulting to water!", liquidType);
        liquidType = 1;
    }

    uint32_t materialId = typeRec->m_materialID;

    if (materialId < Liquid::CMaterialBank::s_materials.Count() && Liquid::CMaterialBank::s_materials.m_data[materialId]) {
        return Liquid::CMaterialBank::s_materials.m_data[materialId];
    }

    bool vertexShaders = g_theGxDevicePtr->Caps().m_shaderTargets[GxSh_Vertex] >= 1;
    bool shaders = Liquid::s_shadersEnabled && vertexShaders && g_theGxDevicePtr->Caps().m_shaderTargets[GxSh_Pixel] >= 3;

    Liquid::IMaterial* material = nullptr;

    switch (materialId) {
        case 1:
            if (shaders) {
                if (Liquid::s_specularEnabled) {
                    material = Liquid::CMaterialWater::Create();
                } else {
                    material = Liquid::CMaterialWaterNoSpec::Create();
                }
            } else {
                material = Liquid::CMaterialWaterFFP::Create();
            }
            break;

        case 2:
            if (shaders) {
                material = Liquid::CMaterialMagma::Create();
            } else {
                material = Liquid::CMaterialMagmaFFP::Create();
            }
            break;

        case 3:
            if (shaders) {
                material = Liquid::CMaterialProcWater::Create();
            } else {
                material = Liquid::CMaterialProcWaterFFP::Create();
            }
            break;
    }

    Liquid::CMaterialBank::s_materials.GrowToFit(materialId, 1);
    Liquid::CMaterialBank::s_materials.m_data[materialId] = material;

    return material;
}
