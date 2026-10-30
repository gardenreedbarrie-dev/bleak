#include "Engine/Source/BleakFx/BleakFxStormNoise.h"
#include <cmath>

namespace {
    const uint32_t kOctaves = 4;

    uint8_t s_texels[BleakFxStormNoise::kSize * BleakFxStormNoise::kSize * 4 * 4 / 3 + 64];
    bool s_made;

    // A lattice value in [0, 1) for cell (x, y) of a lattice `period` cells across, the same on every machine.
    float Lattice(uint32_t x, uint32_t y, uint32_t period, uint32_t seed) {
        uint32_t h = ((x % period) * 0x8DA6B343u) ^ ((y % period) * 0xD8163841u) ^ (seed * 0xCB1AB31Fu);
        h ^= h >> 13;
        h *= 0x5BD1E995u;
        h ^= h >> 15;
        return static_cast<float>(h >> 8) / 16777216.0f;
    }

    float Smooth(float t) {
        return t * t * (3.0f - 2.0f * t);
    }

    // Value noise with `period` cells across the tile, so it repeats seamlessly; at texel (x, y) of the n x n tile.
    float ValueNoise(uint32_t x, uint32_t y, uint32_t n, uint32_t period, uint32_t seed) {
        float fx = static_cast<float>(x) * static_cast<float>(period) / static_cast<float>(n);
        float fy = static_cast<float>(y) * static_cast<float>(period) / static_cast<float>(n);
        uint32_t x0 = static_cast<uint32_t>(fx);
        uint32_t y0 = static_cast<uint32_t>(fy);
        float tx = Smooth(fx - static_cast<float>(x0));
        float ty = Smooth(fy - static_cast<float>(y0));
        float a = Lattice(x0, y0, period, seed);
        float b = Lattice(x0 + 1, y0, period, seed);
        float c = Lattice(x0, y0 + 1, period, seed);
        float d = Lattice(x0 + 1, y0 + 1, period, seed);
        return (a + (b - a) * tx) + ((c + (d - c) * tx) - (a + (b - a) * tx)) * ty;
    }

    // kOctaves octaves from `period` cells up, each half as strong: 0..1.
    float Octaves(uint32_t x, uint32_t y, uint32_t n, uint32_t period, uint32_t seed) {
        float sum = 0.0f;
        float weight = 0.5f;
        float total = 0.0f;

        for (uint32_t o = 0; o < kOctaves; o++) {
            sum += ValueNoise(x, y, n, period << o, seed + o * 101u) * weight;
            total += weight;
            weight *= 0.5f;
        }

        return sum / total;
    }

    uint8_t ToByte(float v) {
        float b = v * 255.0f + 0.5f;
        return static_cast<uint8_t>(b < 0.0f ? 0.0f : (b > 255.0f ? 255.0f : b));
    }

    // Spreads a channel to the full 0..1 range (octave sums bunch up around the middle).
    void Stretch(float* values, uint32_t count) {
        float low = 1.0f;
        float high = 0.0f;

        for (uint32_t i = 0; i < count; i++) {
            low = values[i] < low ? values[i] : low;
            high = values[i] > high ? values[i] : high;
        }

        float scale = high > low ? 1.0f / (high - low) : 0.0f;

        for (uint32_t i = 0; i < count; i++) {
            values[i] = (values[i] - low) * scale;
        }
    }

    void Make() {
        const uint32_t n = BleakFxStormNoise::kSize;
        static float channels[4][BleakFxStormNoise::kSize * BleakFxStormNoise::kSize];

        for (uint32_t y = 0; y < n; y++) {
            for (uint32_t x = 0; x < n; x++) {
                uint32_t i = y * n + x;
                channels[0][i] = Octaves(x, y, n, 2, 11u);
                channels[1][i] = Octaves(x, y, n, 4, 23u);
                channels[2][i] = Octaves(x, y, n, 8, 37u);
                // Ridged: 1 where the noise crosses its middle, falling off fast on both sides.
                float ridge = 1.0f - fabsf(Octaves(x, y, n, 4, 53u) * 2.0f - 1.0f);
                channels[3][i] = ridge * ridge * ridge;
            }
        }

        for (uint32_t c = 0; c < 4; c++) {
            Stretch(channels[c], n * n);
        }

        // Level 0: b, g, r, a = blue, green, red, alpha channel.
        uint8_t* out = s_texels;

        for (uint32_t i = 0; i < n * n; i++) {
            out[i * 4 + 0] = ToByte(channels[2][i]);
            out[i * 4 + 1] = ToByte(channels[1][i]);
            out[i * 4 + 2] = ToByte(channels[0][i]);
            out[i * 4 + 3] = ToByte(channels[3][i]);
        }

        // Smaller levels: 2x2 box filter, which wraps like the texture does.
        for (uint32_t level = 1; level < BleakFxStormNoise::kLevels; level++) {
            uint32_t size = BleakFxStormNoise::LevelSize(level);
            uint32_t parentSize = BleakFxStormNoise::LevelSize(level - 1);
            const uint8_t* parent = s_texels + BleakFxStormNoise::LevelOffset(level - 1);
            uint8_t* level0 = s_texels + BleakFxStormNoise::LevelOffset(level);

            for (uint32_t y = 0; y < size; y++) {
                for (uint32_t x = 0; x < size; x++) {
                    for (uint32_t c = 0; c < 4; c++) {
                        uint32_t x0 = (x * 2) % parentSize, x1 = (x * 2 + 1) % parentSize;
                        uint32_t y0 = (y * 2) % parentSize, y1 = (y * 2 + 1) % parentSize;
                        uint32_t sum = parent[(y0 * parentSize + x0) * 4 + c] + parent[(y0 * parentSize + x1) * 4 + c]
                            + parent[(y1 * parentSize + x0) * 4 + c] + parent[(y1 * parentSize + x1) * 4 + c];
                        level0[(y * size + x) * 4 + c] = static_cast<uint8_t>((sum + 2) / 4);
                    }
                }
            }
        }
    }
}

uint32_t BleakFxStormNoise::LevelOffset(uint32_t level) {
    uint32_t offset = 0;

    for (uint32_t i = 0; i < level; i++) {
        offset += LevelSize(i) * LevelSize(i) * 4;
    }

    return offset;
}

const uint8_t* BleakFxStormNoise::Levels() {
    if (!s_made) {
        Make();
        s_made = true;
    }

    return s_texels;
}
