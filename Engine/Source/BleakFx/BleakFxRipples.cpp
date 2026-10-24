#include "Engine/Source/BleakFx/BleakFxRipples.h"
#include <cmath>
#include <cstring>

namespace {
    const uint32_t kWaves = 48;
    const float kTwoPi = 6.2831853f;

    uint8_t s_texels[BleakFxRipples::kSize * BleakFxRipples::kSize * 4 * 4 / 3 + 64];
    bool s_made;

    // A small fixed generator: the texture is the same on every machine.
    uint32_t s_seed = 0x2545F491u;

    float Random() {
        s_seed = s_seed * 1664525u + 1013904223u;
        return static_cast<float>(s_seed >> 8) / 16777216.0f;
    }

    uint8_t ToByte(float v) {
        float b = v * 255.0f + 0.5f;
        return static_cast<uint8_t>(b < 0.0f ? 0.0f : (b > 255.0f ? 255.0f : b));
    }

    void Make() {
        const uint32_t n = BleakFxRipples::kSize;

        // Waves with whole numbers of periods across the tile so that it repeats seamlessly. Most travel within
        // 60 degrees of the wind, short ones a little more freely; amplitude falls with the wave number.
        float kx[kWaves], ky[kWaves], amplitude[kWaves], phase[kWaves];

        for (uint32_t w = 0; w < kWaves; w++) {
            float spread = w < kWaves * 3 / 4 ? 1.05f : 2.2f;
            float angle = 0.35f + (Random() - 0.5f) * spread;
            float length = 2.0f + Random() * Random() * 14.0f;
            int32_t ix = static_cast<int32_t>(floorf(cosf(angle) * length + 0.5f));
            int32_t iy = static_cast<int32_t>(floorf(sinf(angle) * length + 0.5f));

            if (ix == 0 && iy == 0) {
                ix = 1;
            }

            kx[w] = static_cast<float>(ix);
            ky[w] = static_cast<float>(iy);
            amplitude[w] = (0.6f + 0.4f * Random()) / powf(kx[w] * kx[w] + ky[w] * ky[w], 0.8f);
            phase[w] = Random() * kTwoPi;
        }

        static float height[BleakFxRipples::kSize * BleakFxRipples::kSize];
        static float slopeX[BleakFxRipples::kSize * BleakFxRipples::kSize];
        static float slopeY[BleakFxRipples::kSize * BleakFxRipples::kSize];
        float maxHeight = 0.0f;
        float maxSlope = 0.0f;

        for (uint32_t y = 0; y < n; y++) {
            for (uint32_t x = 0; x < n; x++) {
                float h = 0.0f, dx = 0.0f, dy = 0.0f;

                for (uint32_t w = 0; w < kWaves; w++) {
                    float theta = kTwoPi * (kx[w] * x + ky[w] * y) / n + phase[w];
                    h += amplitude[w] * sinf(theta);
                    float c = amplitude[w] * cosf(theta) * kTwoPi / n;
                    dx += c * kx[w];
                    dy += c * ky[w];
                }

                uint32_t i = y * n + x;
                height[i] = h;
                slopeX[i] = dx;
                slopeY[i] = dy;
                maxHeight = fabsf(h) > maxHeight ? fabsf(h) : maxHeight;
                float s = sqrtf(dx * dx + dy * dy);
                maxSlope = s > maxSlope ? s : maxSlope;
            }
        }

        // Level 0: the steepest slope becomes about 40 degrees; foam where the crests are highest.
        float slopeScale = 0.85f / maxSlope;
        uint8_t* out = s_texels;

        for (uint32_t i = 0; i < n * n; i++) {
            float nx = -slopeX[i] * slopeScale;
            float ny = -slopeY[i] * slopeScale;
            float inv = 1.0f / sqrtf(nx * nx + ny * ny + 1.0f);
            float crest = height[i] / maxHeight;
            float foam = (crest - 0.35f) / 0.5f;
            out[i * 4 + 0] = ToByte(inv * 0.5f + 0.5f);
            out[i * 4 + 1] = ToByte(ny * inv * 0.5f + 0.5f);
            out[i * 4 + 2] = ToByte(nx * inv * 0.5f + 0.5f);
            out[i * 4 + 3] = ToByte(foam < 0.0f ? 0.0f : (foam > 1.0f ? 1.0f : foam));
        }

        // Smaller levels: 2x2 box filter, which wraps like the texture does.
        for (uint32_t level = 1; level < BleakFxRipples::kLevels; level++) {
            uint32_t size = BleakFxRipples::LevelSize(level);
            uint32_t parentSize = BleakFxRipples::LevelSize(level - 1);
            const uint8_t* parent = s_texels + BleakFxRipples::LevelOffset(level - 1);
            uint8_t* level0 = s_texels + BleakFxRipples::LevelOffset(level);

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

uint32_t BleakFxRipples::LevelOffset(uint32_t level) {
    uint32_t offset = 0;

    for (uint32_t i = 0; i < level; i++) {
        offset += LevelSize(i) * LevelSize(i) * 4;
    }

    return offset;
}

const uint8_t* BleakFxRipples::Levels() {
    if (!s_made) {
        Make();
        s_made = true;
    }

    return s_texels;
}
