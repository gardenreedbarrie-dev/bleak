#ifndef ENGINE_SOURCE_GX_BLEAKDEPTHD3D9_H
#define ENGINE_SOURCE_GX_BLEAKDEPTHD3D9_H

// BLEAKHOLD(bleakfx): the readable depth buffer of BleakDepth.h for the two Direct3D 9 devices, which have the same
// members for this. Included by their sources and BleakDepth.cpp only.

#include <cstdint>
#include <windows.h>
#include <d3d9.h>
#include "Engine/Source/Gx/CGxTex.h"
#include "Engine/Source/Gx/Types.h"

struct BleakDepthD3d9 {
    // The INTZ texture while it is the back buffer's depth buffer, and its level 0. The surface has one reference
    // here and one in the device's m_defDepthSurface.
    IDirect3DTexture9* texture;
    IDirect3DSurface9* surface;
    // The automatic depth buffer it stands in for, with the reference m_defDepthSurface had.
    IDirect3DSurface9* autoSurface;
    // INTZ failed on this device: not tried again until the device is reset.
    bool failed;
};

extern BleakDepthD3d9 g_bleakDepthD3d9;
extern CGxTex* g_bleakDepthHandle;

static const D3DFORMAT BLEAKDEPTH_FORMAT_INTZ = static_cast<D3DFORMAT>(MAKEFOURCC('I', 'N', 'T', 'Z'));

// Puts the automatic depth buffer back and frees the INTZ texture. Called before the device resets (Direct3D 9 only
// resets once every D3DPOOL_DEFAULT resource is gone) and when the depth effects are turned off.
template <class Device>
void BleakDepthDetach(Device* device) {
    BleakDepthD3d9& depth = g_bleakDepthD3d9;
    depth.failed = false;

    if (!depth.texture) {
        return;
    }

    if (device->m_defDepthSurface == depth.surface) {
        device->m_defDepthSurface->Release();
        device->m_defDepthSurface = depth.autoSurface;
        depth.autoSurface = nullptr;
    }

    if (device->m_d3dDevice) {
        IDirect3DSurface9* current = nullptr;

        if (SUCCEEDED(device->m_d3dDevice->GetDepthStencilSurface(&current)) && current) {
            if (current == depth.surface) {
                device->m_d3dDevice->SetDepthStencilSurface(device->m_defDepthSurface);
            }

            current->Release();
        }

        for (uint32_t i = 0; i < 16; i++) {
            IDirect3DBaseTexture9* bound = nullptr;

            if (SUCCEEDED(device->m_d3dDevice->GetTexture(i, &bound)) && bound) {
                if (bound == depth.texture) {
                    device->m_d3dDevice->SetTexture(i, nullptr);
                }

                bound->Release();
            }
        }
    }

    if (depth.autoSurface) {
        depth.autoSurface->Release();
        depth.autoSurface = nullptr;
    }

    depth.surface->Release();
    depth.surface = nullptr;
    depth.texture->Release();
    depth.texture = nullptr;
}

template <class Device>
bool BleakDepthAttach(Device* device) {
    BleakDepthD3d9& depth = g_bleakDepthD3d9;

    if (depth.texture) {
        return device->m_defDepthSurface == depth.surface;
    }

    // INTZ cannot be multisampled, and a depth buffer must match the back buffer's multisampling.
    if (depth.failed || !device->m_context || !device->m_d3dDevice || !device->m_defDepthSurface || device->m_format.m_multisampleCount > 1) {
        return false;
    }

    D3DSURFACE_DESC desc;

    if (FAILED(device->m_defDepthSurface->GetDesc(&desc)) || desc.MultiSampleType != D3DMULTISAMPLE_NONE
        || FAILED(device->m_d3d->CheckDeviceFormat(D3DADAPTER_DEFAULT, D3DDEVTYPE_HAL, device->m_devAdapterFormat, D3DUSAGE_DEPTHSTENCIL, D3DRTYPE_TEXTURE, BLEAKDEPTH_FORMAT_INTZ))) {
        depth.failed = true;
        return false;
    }

    IDirect3DTexture9* texture = nullptr;
    IDirect3DSurface9* surface = nullptr;

    if (FAILED(device->m_d3dDevice->CreateTexture(desc.Width, desc.Height, 1, D3DUSAGE_DEPTHSTENCIL, BLEAKDEPTH_FORMAT_INTZ, D3DPOOL_DEFAULT, &texture, nullptr))) {
        depth.failed = true;
        return false;
    }

    if (FAILED(texture->GetSurfaceLevel(0, &surface))) {
        texture->Release();
        depth.failed = true;
        return false;
    }

    depth.texture = texture;
    depth.surface = surface;
    depth.autoSurface = device->m_defDepthSurface;
    surface->AddRef();
    device->m_defDepthSurface = surface;

    // Rendering into the back buffer uses it from now on; a texture target picks it up when it switches back.
    if (!device->m_textureTarget[GxBuffers_Color].m_apiSpecific && !device->m_textureTarget[GxBuffers_Depth].m_apiSpecific) {
        device->m_d3dDevice->SetDepthStencilSurface(surface);
    }

    return true;
}

// ISetTexture: binds the INTZ texture for the handle of GxBleakDepthTexture. Returns false for any other texture.
template <class Device>
bool BleakDepthBindTexture(Device* device, uint32_t tmu, CGxTex* texId) {
    if (!texId || texId != g_bleakDepthHandle) {
        return false;
    }

    device->m_d3dDevice->SetTexture(tmu, g_bleakDepthD3d9.texture);
    device->DsSet(static_cast<typename Device::EDeviceState>(Device::Ds_TssMinFilter0 + tmu), D3DTEXF_POINT);
    device->DsSet(static_cast<typename Device::EDeviceState>(Device::Ds_TssMagFilter0 + tmu), D3DTEXF_POINT);
    device->DsSet(static_cast<typename Device::EDeviceState>(Device::Ds_TssMipFilter0 + tmu), D3DTEXF_NONE);
    device->DsSet(static_cast<typename Device::EDeviceState>(Device::Ds_TssWrapU0 + tmu), D3DTADDRESS_CLAMP);
    device->DsSet(static_cast<typename Device::EDeviceState>(Device::Ds_TssWrapV0 + tmu), D3DTADDRESS_CLAMP);
    device->DsSet(static_cast<typename Device::EDeviceState>(Device::Ds_TssMaxAnisotropy0 + tmu), 1);

    if (tmu < 8) {
        device->m_texEnabled[tmu] = true;
    }

    return true;
}

#endif
