// SMAA 1x (ThirdParty/SMAA, MIT; Jimenez et al.) for BleakFx: Direct3D 9 shader model 3, luma edges, the High
// preset. The area and search textures are A8R8G8B8 here (Gx has no A8L8), with their data in red and green.
#ifndef BH_SMAA_COMMON_HLSLI
#define BH_SMAA_COMMON_HLSLI

#include "bh_common.hlsli"

#define SMAA_RT_METRICS g_outTexel
#define SMAA_HLSL_3
#define SMAA_PRESET_HIGH
#define SMAA_AREATEX_SELECT(sample) sample.rg
#define SMAA_SEARCHTEX_SELECT(sample) sample.r
#include "../../../../ThirdParty/SMAA/SMAA.hlsl"

#endif
