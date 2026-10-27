#ifndef ENGINE_SOURCE_BLEAKFX_BLEAKFXSTORMNOISE_H
#define ENGINE_SOURCE_BLEAKFX_BLEAKFXSTORMNOISE_H

#include <cstdint>

// BLEAKHOLD(storm): the noise texture of the storm wall (Shaders/bh_storm_ps.hlsl), made in code: tileable value
// noise, four octaves in each channel: red large billows, green finer cloud, blue fine grain, alpha ridged veins
// (bright thin lines where a noise crosses its middle). Bytes are in Direct3D A8R8G8B8 order (b, g, r, a).
namespace BleakFxStormNoise {
    const uint32_t kSize = 128;
    const uint32_t kLevels = 8;

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
