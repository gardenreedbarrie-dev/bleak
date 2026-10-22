// BLEAKHOLD(grasswind): wind in the grass and blades that part around the player, for the stock detail-doodad
// vertex shaders (CDetailDoodad). Ported from WarcraftXL's wxl-grasswind (GrassWind.cpp, by iThorgrim): the stock
// vs_3_0 bytecode gets a motion block after the view transform; it displaces each blade in the world plane by two
// travelling sine waves and a push away from the player, weighted by the blade's own height (its texture v).
//
// Copyright (C) 2026 WarcraftXL (grass motion), Bleakhold (bytecode patching, client integration)
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.

#ifndef ENGINE_SOURCE_GX_BLEAKGRASSWIND_H
#define ENGINE_SOURCE_GX_BLEAKGRASSWIND_H

#include <cstdint>
#include <cstring>
#include <vector>

// The motion block reads vertex constants c240 - c248 (BleakGrassWindConstants). With the strength 0 and no
// parting, it adds exactly nothing: the grass is drawn as by the stock shader.
const uint32_t BLEAKGRASSWIND_FIRST_CONSTANT = 240;
const uint32_t BLEAKGRASSWIND_CONSTANT_COUNT = 9;

// The patched shader for a stock detail-doodad vs_3_0 shader of `size` bytes, or false (and `patched` untouched)
// when `code` is not one: another shader model, no view transform where the block goes ("add r0, r0, c3"), no
// texture coordinate 0, no free temporary registers, or the stock shader already uses c240 - c248 or relative
// addressing. A patched shader is refused too, so patching twice changes nothing. The patched shader carries the
// stock bytecode in a comment for BleakGrassWindStock.
bool BleakGrassWindPatch(const uint8_t* code, uint32_t size, std::vector<uint8_t>& patched);

// The stock bytecode a patched shader carries, or false when `code` is not a patched shader.
bool BleakGrassWindStock(const uint8_t* code, uint32_t size, std::vector<uint8_t>& stock);

// What the wind looks like this frame.
struct BleakGrassWindInput {
    // World position of the origin of the shader's view space: the camera.
    float camera[3];
    // World position of the player's feet; hasPlayer false: no parting.
    float player[3];
    bool hasPlayer;
    // A steady clock in seconds.
    double seconds;
    // 0 still, 1 the default breeze, 2 a strong wind.
    float strength;
    // Blades lean away from the player.
    bool parting;
};

// The constants c240 - c248 for the patched shaders.
void BleakGrassWindConstants(const BleakGrassWindInput& input, float constants[BLEAKGRASSWIND_CONSTANT_COUNT][4]);

// Device side: a patched shader the device refuses gets its stock bytecode back, so the grass is still drawn.
// Returns true when `code` (a TSGrowableArray<uint8_t>) was replaced.
template <class Array>
bool BleakGrassWindRestore(Array& code) {
    std::vector<uint8_t> stock;

    if (!BleakGrassWindStock(code.m_data, code.Count(), stock)) {
        return false;
    }

    code.SetCount(static_cast<uint32_t>(stock.size()));
    memcpy(code.m_data, stock.data(), stock.size());
    return true;
}

#endif
