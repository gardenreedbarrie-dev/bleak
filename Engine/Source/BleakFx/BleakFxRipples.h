#ifndef ENGINE_SOURCE_BLEAKFX_BLEAKFXRIPPLES_H
#define ENGINE_SOURCE_BLEAKFX_BLEAKFXRIPPLES_H

#include <cstdint>

// BLEAKHOLD(bleakfx): the ripple texture of BleakFx's water, made in code: a tileable wave height field as normals
// (rgb = normal * 0.5 + 0.5, z up) with a foam pattern in alpha. Bytes are in Direct3D A8R8G8B8 order (b, g, r, a).
namespace BleakFxRipples {
    const uint32_t kSize = 256;
    const uint32_t kLevels = 9;

    // Width (and height) of mip level `level`.
    inline uint32_t LevelSize(uint32_t level) {
        uint32_t size = kSize >> level;
        return size ? size : 1;
    }

    // The texels of every level, level 0 first (kSize * kSize * 4 bytes, then a quarter of that, ...). Made on
    // the first call; the result stays valid.
    const uint8_t* Levels();

    // Offset of level `level` in Levels().
    uint32_t LevelOffset(uint32_t level);
}

#endif
