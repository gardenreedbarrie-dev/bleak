#ifndef ENGINE_SOURCE_GX_BLEAKDEPTH_H
#define ENGINE_SOURCE_GX_BLEAKDEPTH_H

#include <cstdint>

class CGxTex;

// BLEAKHOLD(bleakfx): a depth buffer the post-processing can read. On the Direct3D 9 devices without
// multisampling, an INTZ depth texture stands in for the back buffer's automatic depth buffer; the stock rendering
// does not notice the difference. Elsewhere there is none and these functions do nothing.

// Called before the world is drawn (the world clears the depth buffer first). Makes the readable depth buffer the
// back buffer's depth buffer (enable) or puts the automatic one back. Returns whether the readable one is in use.
bool GxBleakDepthSet(bool enable);

// The texture to bind with GxRs_TextureN to sample the depth buffer (z/w in red, point filtered), or nullptr when
// there is no readable depth buffer.
CGxTex* GxBleakDepthTexture();

// Frees the handle GxBleakDepthTexture made (BleakFx::Destroy).
void GxBleakDepthDestroyHandle();

#endif
