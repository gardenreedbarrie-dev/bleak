#include "Engine/Source/Gx/BleakDepth.h"
#include "Engine/Source/Gx/BleakDepthD3d9.h"
#include "Engine/Source/Gx/CGxDevice/CGxDevice.h"
#include "Engine/Source/Gx/CGxDeviceD3d/CGxDeviceD3d.h"
#include "Engine/Source/Gx/CGxDeviceD3d9Ex/CGxDeviceD3d9Ex.h"
#include "Engine/Source/Gx/CGxTexFlags.h"
#include "Engine/Source/Gx/Gx.h"

BleakDepthD3d9 g_bleakDepthD3d9;
CGxTex* g_bleakDepthHandle;

static void NullTexUserFunc(EGxTexCommand command, uint32_t width, uint32_t height, uint32_t face, uint32_t level, void* userArg, uint32_t& texelStrideInBytes, const void*& texels) {
}

bool GxBleakDepthSet(bool enable) {
    CGxDevice* device = g_theGxDevicePtr;

    if (!device) {
        return false;
    }

    switch (device->DeviceApi()) {
        case GxApi_D3d9: {
            CGxDeviceD3d* d3d = static_cast<CGxDeviceD3d*>(device);

            if (enable) {
                return BleakDepthAttach(d3d);
            }

            BleakDepthDetach(d3d);
            return false;
        }

        case GxApi_D3d9Ex: {
            CGxDeviceD3d9Ex* d3d = static_cast<CGxDeviceD3d9Ex*>(device);

            if (enable) {
                return BleakDepthAttach(d3d);
            }

            BleakDepthDetach(d3d);
            return false;
        }

        default:
            return false;
    }
}

CGxTex* GxBleakDepthTexture() {
    if (!g_bleakDepthD3d9.texture) {
        return nullptr;
    }

    // Never created or uploaded: the devices' ISetTexture binds the INTZ texture for it.
    if (!g_bleakDepthHandle) {
        CGxTexFlags flags(GxTex_Nearest, GxTex_Clamp, GxTex_Clamp);

        if (!GxTexCreate(GxTex_2d, 8, 8, 0, GxTex_Argb8888, GxTex_Argb8888, flags, nullptr, NullTexUserFunc, "BleakFx::Depth", g_bleakDepthHandle)) {
            g_bleakDepthHandle = nullptr;
        }
    }

    return g_bleakDepthHandle;
}

void GxBleakDepthDestroyHandle() {
    if (g_bleakDepthHandle) {
        GxTexDestroy(g_bleakDepthHandle);
        g_bleakDepthHandle = nullptr;
    }
}
