// BLEAKHOLD(grasswind): the grass motion block of WarcraftXL's wxl-grasswind for the stock detail-doodad shaders,
// written into their bytecode here (WarcraftXL disassembles, edits the text and reassembles with
// d3dcompiler_47; this client patches the tokens itself and needs no compiler at run time).
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

#include "Engine/Source/Gx/BleakGrassWind.h"
#include <cmath>
#include <cstdlib>

namespace {
    // Shader model 3 bytecode (d3d9types.h).
    const uint32_t kVersionVs30 = 0xFFFE0300;
    const uint32_t kOpcodeMask = 0x0000FFFF;
    const uint32_t kOpComment = 0xFFFE;
    const uint32_t kOpEnd = 0xFFFF;
    const uint32_t kOpDcl = 31;
    const uint32_t kOpDefB = 47;
    const uint32_t kOpDefI = 48;
    const uint32_t kOpDef = 81;
    const uint32_t kRelativeAddressing = 1u << 13;
    const uint32_t kUsageTexcoord = 5;

    const uint32_t kRegTemp = 0;
    const uint32_t kRegInput = 1;
    const uint32_t kRegConst = 2;
    const uint32_t kMaxTemps = 32;

    // "BHGW": the comment that carries the stock bytecode.
    const uint32_t kMarker = 0x57474842;

    // The view transform the block follows: add r0, r0, c3 (worldView rows in c0 - c3, CDetailDoodad).
    const uint32_t kAnchor[4] = { 0x03000002, 0x800F0000, 0x80E40000, 0xA0E40003 };
    const uint32_t kAnchorSwapped[4] = { 0x03000002, 0x800F0000, 0xA0E40003, 0x80E40000 };

    // The motion block of wxl-grasswind (GrassWind.cpp, kMotionInject) with Bleakhold's changes: the constants
    // moved to c240 - c248 (c248.x = 1 replaces the stock shader's c13.y), the wave phases are reduced to
    // [-pi, pi) before sincos, the distance fade uses |view z|, the parting bends the blade from its base like the
    // wind does (upstream moves the whole blade), and no instruction reads two constant registers.
    // pos is the view-space position (r0), uv the texture coordinate input, t0 - t3 free temporaries.
    //   c240 xyz camera (world)                c241 1/cone height, 1/radius, minimum height, epsilon
    //   c242 xyz player (world), w lean        c243 x edge - centre force, y centre force, z radius, w phase 1
    //   c244 xy wave 1 amplitude, zw wave 1 cycles per yard     c245 the same for wave 2
    //   c246 xy jitter frequencies, z jitter (cycles), w distance fade
    //   c247 x 1 - variance / 2, y variance, z -anchor, w 1 / (1 - anchor)    c248 1, 2 pi, -pi, phase 2
    // Phases are in cycles, plus 0.5 for the reduction.
    const char* const kMotionBlock[] = {
        // World position: the view rotation turned back (batches are not rotated), plus the camera.
        "dp3 t0.x, c0, pos",
        "dp3 t0.y, c1, pos",
        "add t0.xy, t0, c240",
        "mov t2.xy, t0",
        "dp3 t1.z, c2, pos",
        "add t1.z, t1.z, c240.z",
        // Parting: a height cone above the player's feet, a force from the centre to the edge of the radius.
        "add t1.z, t1.z, -c242.z",
        "add t1.z, t1.z, -c241.z",
        "mul_sat t2.z, t1.z, c241.x",
        "add t0.xy, t0, -c242",
        "mul t0.z, t0.x, t0.x",
        "mad t0.z, t0.y, t0.y, t0.z",
        "add t0.z, t0.z, c241.w",
        "rsq t0.w, t0.z",
        "mul t1.x, t0.z, t0.w",
        "mul_sat t1.y, t1.x, c241.y",
        "mad t1.y, c243.x, t1.y, c243.y",
        "slt t1.z, t1.x, c243.z",
        "mul t1.y, t1.y, t1.z",
        "mul t1.y, t1.y, t2.z",
        "mul t1.y, t1.y, t0.w",
        "mul t0.xy, t0, t1.y",
        // Bend weight: 0 at the blade's base (v = 1), squared towards the tip, above the anchor; it bends the parting
        // and (less far away) the wind.
        "add t3.z, c248.x, -uv.y",
        "add t3.z, t3.z, c247.z",
        "mul_sat t3.z, t3.z, c247.w",
        "mul t3.z, t3.z, t3.z",
        "mul t0.xy, t0, t3.z",
        "abs t3.w, pos.z",
        "mul t3.w, t3.w, c246.w",
        "add t3.w, t3.w, c248.x",
        "rcp t3.w, t3.w",
        "mul t3.z, t3.z, t3.w",
        // Per-blade jitter of amplitude and phase.
        "mul t1.x, t2.x, c246.x",
        "mad t1.x, t2.y, c246.y, t1.x",
        "frc t1.x, t1.x",
        "mad t0.z, t1.x, c247.y, c247.x",
        "mul t3.z, t3.z, t0.z",
        "mul t1.x, t1.x, c246.z",
        // Two travelling waves.
        "mad t1.y, t2.x, c244.z, t1.x",
        "mad t1.y, t2.y, c244.w, t1.y",
        "add t1.y, t1.y, c243.w",
        "frc t1.y, t1.y",
        "mad t1.y, t1.y, c248.y, c248.z",
        "mad t1.z, t2.x, c245.z, t1.x",
        "mad t1.z, t2.y, c245.w, t1.z",
        "add t1.z, t1.z, c248.w",
        "frc t1.z, t1.z",
        "mad t1.z, t1.z, c248.y, c248.z",
        "sincos t2.xy, t1.y",
        "add t2.w, t2.y, c242.w",
        "sincos t3.xy, t1.z",
        "mul t1.zw, c244.xxxy, t2.wwww",
        "mad t1.zw, c245.xxxy, t3.yyyy, t1",
        "mul t1.zw, t1, t3.zzzz",
        "add t0.xy, t0, t1.zwzw",
        // The world-plane offset back into view space.
        "mul t1.xyz, c0, t0.x",
        "mad t1.xyz, c1, t0.y, t1",
        "add pos.xyz, pos, t1",
    };

    struct Opcode {
        const char* name;
        uint32_t opcode;
        uint32_t sources;
    };

    const Opcode kOpcodes[] = {
        { "mov", 1, 1 }, { "add", 2, 2 }, { "mad", 4, 3 }, { "mul", 5, 2 }, { "rcp", 6, 1 }, { "rsq", 7, 1 },
        { "dp3", 8, 2 }, { "slt", 12, 2 }, { "frc", 19, 1 }, { "abs", 35, 1 }, { "sincos", 37, 1 },
    };

    uint32_t RegisterType(uint32_t param) {
        return ((param >> 28) & 0x7) | ((param >> 8) & 0x18);
    }

    uint32_t RegisterNumber(uint32_t param) {
        return param & 0x7FF;
    }

    uint32_t Param(uint32_t type, uint32_t number) {
        return 0x80000000u | ((type & 0x7) << 28) | ((type & 0x18) << 8) | (number & 0x7FF);
    }

    int32_t Component(char c) {
        switch (c) {
            case 'x':
                return 0;
            case 'y':
                return 1;
            case 'z':
                return 2;
            case 'w':
                return 3;
            default:
                return -1;
        }
    }

    // Registers the block's names stand for.
    struct Names {
        uint32_t position;
        uint32_t texcoord;
        uint32_t firstTemp;
    };

    // One operand of the block: [-]name[.components]. Destinations take the components as a write mask in
    // x, y, z, w order; sources as a swizzle whose last component repeats.
    bool EncodeOperand(const char* text, size_t length, bool destination, const Names& names, uint32_t& token) {
        bool negate = false;

        if (length && text[0] == '-') {
            negate = true;
            text++;
            length--;
        }

        size_t nameLength = 0;

        while (nameLength < length && text[nameLength] != '.') {
            nameLength++;
        }

        if (nameLength == 0) {
            return false;
        }

        if (nameLength == 3 && !strncmp(text, "pos", 3)) {
            token = Param(kRegTemp, names.position);
        } else if (nameLength == 2 && !strncmp(text, "uv", 2)) {
            token = Param(kRegInput, names.texcoord);
        } else if (nameLength == 2 && text[0] == 't' && text[1] >= '0' && text[1] <= '3') {
            token = Param(kRegTemp, names.firstTemp + static_cast<uint32_t>(text[1] - '0'));
        } else if (text[0] == 'c' && nameLength >= 2 && nameLength <= 4) {
            uint32_t number = 0;

            for (size_t i = 1; i < nameLength; i++) {
                if (text[i] < '0' || text[i] > '9') {
                    return false;
                }

                number = number * 10 + static_cast<uint32_t>(text[i] - '0');
            }

            token = Param(kRegConst, number);
        } else {
            return false;
        }

        const char* components = nameLength < length ? text + nameLength + 1 : nullptr;
        size_t count = components ? length - nameLength - 1 : 0;

        if (components && (count == 0 || count > 4)) {
            return false;
        }

        if (destination) {
            if (negate) {
                return false;
            }

            uint32_t mask = 0;
            int32_t last = -1;

            for (size_t i = 0; i < count; i++) {
                int32_t c = Component(components[i]);

                if (c <= last) {
                    return false;
                }

                mask |= 1u << c;
                last = c;
            }

            token |= (components ? mask : 0xFu) << 16;
        } else {
            uint32_t swizzle = 0;

            for (uint32_t i = 0; i < 4; i++) {
                int32_t c = components ? Component(components[i < count ? i : count - 1]) : static_cast<int32_t>(i);

                if (c < 0) {
                    return false;
                }

                swizzle |= static_cast<uint32_t>(c) << (2 * i);
            }

            token |= swizzle << 16;

            if (negate) {
                token |= 1u << 24;
            }
        }

        return true;
    }

    // One line of the block: opcode[_sat] destination, sources.
    bool EncodeInstruction(const char* line, const Names& names, std::vector<uint32_t>& out) {
        const char* space = strchr(line, ' ');

        if (!space) {
            return false;
        }

        size_t nameLength = static_cast<size_t>(space - line);
        bool saturate = nameLength > 4 && !strncmp(space - 4, "_sat", 4);

        if (saturate) {
            nameLength -= 4;
        }

        const Opcode* opcode = nullptr;

        for (const Opcode& candidate : kOpcodes) {
            if (strlen(candidate.name) == nameLength && !strncmp(candidate.name, line, nameLength)) {
                opcode = &candidate;
            }
        }

        if (!opcode) {
            return false;
        }

        uint32_t tokens[4];
        uint32_t operands = 0;
        const char* text = space + 1;

        while (*text) {
            const char* end = strchr(text, ',');
            size_t length = end ? static_cast<size_t>(end - text) : strlen(text);

            if (operands >= 4 || !EncodeOperand(text, length, operands == 0, names, tokens[operands])) {
                return false;
            }

            operands++;
            text += length;

            if (*text == ',') {
                text++;

                if (*text != ' ') {
                    return false;
                }

                text++;
            }
        }

        if (operands != opcode->sources + 1) {
            return false;
        }

        if (saturate) {
            tokens[0] |= 1u << 20;
        }

        out.push_back(opcode->opcode | (operands << 24));
        out.insert(out.end(), tokens, tokens + operands);
        return true;
    }

    bool Matches(const uint32_t* tokens, const uint32_t* pattern) {
        return !memcmp(tokens, pattern, sizeof(uint32_t) * 4);
    }

    double Fraction(double value) {
        return value - floor(value);
    }
}

bool BleakGrassWindPatch(const uint8_t* code, uint32_t size, std::vector<uint8_t>& patched) {
    if (!code || size < 8 || size % 4) {
        return false;
    }

    uint32_t count = size / 4;
    std::vector<uint32_t> tokens(count);
    memcpy(tokens.data(), code, size);

    if (tokens[0] != kVersionVs30) {
        return false;
    }

    // Walk the instructions: where the block goes, what the shader uses.
    uint32_t anchorEnd = 0;
    uint32_t endToken = 0;
    uint32_t maxTemp = 0;
    bool texcoordFound = false;
    uint32_t texcoord = 0;
    uint32_t i = 1;

    while (i < count) {
        uint32_t token = tokens[i];
        uint32_t opcode = token & kOpcodeMask;

        if (opcode == kOpComment) {
            uint32_t length = (token >> 16) & 0x7FFF;

            // An earlier patch: never twice.
            if (length >= 1 && i + 1 < count && tokens[i + 1] == kMarker) {
                return false;
            }

            i += 1 + length;
            continue;
        }

        if (opcode == kOpEnd) {
            endToken = i;
            break;
        }

        uint32_t length = (token >> 24) & 0xF;

        if (i + 1 + length > count) {
            return false;
        }

        const uint32_t* params = tokens.data() + i + 1;

        if (opcode == kOpDcl) {
            if (length != 2) {
                return false;
            }

            uint32_t usage = params[0] & 0x1F;
            uint32_t usageIndex = (params[0] >> 16) & 0xF;
            uint32_t mask = (params[1] >> 16) & 0xF;

            if (RegisterType(params[1]) == kRegInput && usage == kUsageTexcoord && usageIndex == 0) {
                texcoordFound = (mask & 0x2) != 0;
                texcoord = RegisterNumber(params[1]);
            }
        } else if (opcode == kOpDef || opcode == kOpDefI || opcode == kOpDefB) {
            if (length < 1) {
                return false;
            }

            uint32_t number = RegisterNumber(params[0]);

            if (RegisterType(params[0]) == kRegConst && number >= BLEAKGRASSWIND_FIRST_CONSTANT && number < BLEAKGRASSWIND_FIRST_CONSTANT + BLEAKGRASSWIND_CONSTANT_COUNT) {
                return false;
            }
        } else {
            for (uint32_t p = 0; p < length; p++) {
                uint32_t type = RegisterType(params[p]);
                uint32_t number = RegisterNumber(params[p]);

                if (params[p] & kRelativeAddressing) {
                    return false;
                }

                if (type == kRegTemp && number > maxTemp) {
                    maxTemp = number;
                }

                if (type == kRegConst && number >= BLEAKGRASSWIND_FIRST_CONSTANT && number < BLEAKGRASSWIND_FIRST_CONSTANT + BLEAKGRASSWIND_CONSTANT_COUNT) {
                    return false;
                }
            }

            if (!anchorEnd && length == 3 && (Matches(&tokens[i], kAnchor) || Matches(&tokens[i], kAnchorSwapped))) {
                anchorEnd = i + 4;
            }
        }

        i += 1 + length;
    }

    Names names = { 0, texcoord, maxTemp + 1 };

    if (!endToken || !anchorEnd || !texcoordFound || names.firstTemp + 4 > kMaxTemps) {
        return false;
    }

    std::vector<uint32_t> block;

    for (const char* line : kMotionBlock) {
        if (!EncodeInstruction(line, names, block)) {
            return false;
        }
    }

    // The stock bytecode in a comment (at most 0x7FFF tokens).
    uint32_t stockTokens = (size + 3) / 4;
    uint32_t commentLength = 2 + stockTokens;

    if (commentLength > 0x7FFF) {
        return false;
    }

    std::vector<uint32_t> out;
    out.reserve(count + 1 + commentLength + block.size());
    out.push_back(tokens[0]);
    out.push_back(kOpComment | (commentLength << 16));
    out.push_back(kMarker);
    out.push_back(size);
    out.insert(out.end(), tokens.begin(), tokens.end());
    out.insert(out.end(), tokens.begin() + 1, tokens.begin() + anchorEnd);
    out.insert(out.end(), block.begin(), block.end());
    out.insert(out.end(), tokens.begin() + anchorEnd, tokens.end());

    patched.resize(out.size() * 4);
    memcpy(patched.data(), out.data(), patched.size());
    return true;
}

bool BleakGrassWindStock(const uint8_t* code, uint32_t size, std::vector<uint8_t>& stock) {
    if (!code || size < 16 || size % 4) {
        return false;
    }

    uint32_t header[4];
    memcpy(header, code, sizeof(header));
    uint32_t commentLength = (header[1] >> 16) & 0x7FFF;

    if (header[0] != kVersionVs30 || (header[1] & kOpcodeMask) != kOpComment || header[2] != kMarker || commentLength < 2) {
        return false;
    }

    uint32_t stockSize = header[3];

    if (stockSize > (commentLength - 2) * 4 || 16 + stockSize > size) {
        return false;
    }

    stock.assign(code + 16, code + 16 + stockSize);
    return true;
}

void BleakGrassWindConstants(const BleakGrassWindInput& input, float constants[BLEAKGRASSWIND_CONSTANT_COUNT][4]) {
    // wxl-grasswind's default WindSettings and PhysicsSettings.
    const double kTwoPi = 6.283185307179586;
    const double directionDeg = 45.0;
    const double speed = 3.0;
    const double amplitude = 0.06;
    const double wavelength = 18.0;
    const double crossAmplitude = 0.02;
    const double crossWavelength = 6.5;
    const double crossAngleDeg = 35.0;
    const float lean = 0.35f;
    const float variance = 0.6f;
    const float distanceFade = 0.015f;
    const float anchor = 0.3f;
    const float radius = 2.0f;
    const float forceCenter = 0.5f;
    const float forceEdge = 0.0f;
    const float coneHeight = 0.5f;
    const float minHeight = 0.3f;
    const float epsilon = 1.0e-3f;
    const double jitter = 1.7;

    float strength = input.strength > 0.0f ? (input.strength < 2.0f ? input.strength : 2.0f) : 0.0f;
    double a1 = directionDeg * kTwoPi / 360.0;
    double a2 = (directionDeg + crossAngleDeg) * kTwoPi / 360.0;
    double d1[2] = { cos(a1), sin(a1) };
    double d2[2] = { cos(a2), sin(a2) };
    double amp1 = amplitude * strength;
    double amp2 = crossAmplitude * strength;

    // In cycles: the waves travel downwind.
    double phase1 = -Fraction(speed * input.seconds / wavelength);
    double phase2 = -Fraction(speed * 1.37 * input.seconds / crossWavelength);

    bool parting = input.parting && input.hasPlayer;
    float center = parting ? forceCenter : 0.0f;
    float edge = parting ? forceEdge : 0.0f;
    const float* player = input.hasPlayer ? input.player : input.camera;

    const float values[BLEAKGRASSWIND_CONSTANT_COUNT][4] = {
        { input.camera[0], input.camera[1], input.camera[2], 0.0f },
        { 1.0f / coneHeight, 1.0f / radius, minHeight, epsilon },
        { player[0], player[1], player[2], lean },
        { edge - center, center, radius, static_cast<float>(phase1 + 0.5) },
        { static_cast<float>(d1[0] * amp1), static_cast<float>(d1[1] * amp1), static_cast<float>(d1[0] / wavelength), static_cast<float>(d1[1] / wavelength) },
        { static_cast<float>(d2[0] * amp2), static_cast<float>(d2[1] * amp2), static_cast<float>(d2[0] / crossWavelength), static_cast<float>(d2[1] / crossWavelength) },
        { 0.737f, 1.311f, static_cast<float>(jitter / kTwoPi), distanceFade },
        { 1.0f - variance * 0.5f, variance, -anchor, 1.0f / (1.0f - anchor) },
        { 1.0f, static_cast<float>(kTwoPi), static_cast<float>(-kTwoPi / 2.0), static_cast<float>(phase2 + 0.5) },
    };

    memcpy(constants, values, sizeof(values));
}
