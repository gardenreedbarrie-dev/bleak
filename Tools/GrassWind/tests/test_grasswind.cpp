// Tests of Engine/Source/Gx/BleakGrassWind.cpp (run_tests.sh builds and runs them):
//   test_grasswind <dir>                          the patcher on the stand-in shader and on made-up bytecode
//   test_grasswind --constants <s> <k> <out.bin>  writes c240 - c248 for time s and strength k (emulate.py)
#include "Engine/Source/Gx/BleakGrassWind.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {
    int s_failed = 0;
    int s_checks = 0;

    void Check(bool ok, const char* what) {
        s_checks++;

        if (!ok) {
            s_failed++;
            printf("FAIL: %s\n", what);
        }
    }

    std::vector<uint8_t> ReadFile(const std::string& path) {
        std::vector<uint8_t> data;
        FILE* f = fopen(path.c_str(), "rb");

        if (!f) {
            perror(path.c_str());
            exit(2);
        }

        fseek(f, 0, SEEK_END);
        long size = ftell(f);
        fseek(f, 0, SEEK_SET);
        data.resize(static_cast<size_t>(size));

        if (size && fread(data.data(), 1, data.size(), f) != data.size()) {
            exit(2);
        }

        fclose(f);
        return data;
    }

    std::vector<uint8_t> Bytes(const std::vector<uint32_t>& tokens) {
        std::vector<uint8_t> bytes(tokens.size() * 4);
        memcpy(bytes.data(), tokens.data(), bytes.size());
        return bytes;
    }

    bool Patches(const std::vector<uint32_t>& tokens) {
        std::vector<uint8_t> code = Bytes(tokens);
        std::vector<uint8_t> patched;
        return BleakGrassWindPatch(code.data(), static_cast<uint32_t>(code.size()), patched);
    }

    // A minimal shader the patcher accepts: dcl_texcoord v3, add r0, r0, c3, mov o0, r0, end.
    std::vector<uint32_t> Minimal() {
        return {
            0xFFFE0300,
            0x0200001F, 0x80000005, 0x900F0003,
            0x0200001F, 0x80000000, 0xE00F0000,
            0x03000002, 0x800F0000, 0x80E40000, 0xA0E40003,
            0x02000001, 0xE00F0000, 0x80E40000,
            0x0000FFFF,
        };
    }
}

int main(int argc, char** argv) {
    if (argc == 5 && !strcmp(argv[1], "--constants")) {
        BleakGrassWindInput input = {};
        input.camera[0] = 100.5f;
        input.camera[1] = -2000.25f;
        input.camera[2] = 50.0f;
        input.player[0] = 103.0f;
        input.player[1] = -1996.0f;
        input.player[2] = 48.0f;
        input.hasPlayer = true;
        input.parting = atof(argv[3]) > 0.0;
        input.seconds = atof(argv[2]);
        input.strength = static_cast<float>(atof(argv[3]));
        float constants[BLEAKGRASSWIND_CONSTANT_COUNT][4];
        BleakGrassWindConstants(input, constants);
        FILE* f = fopen(argv[4], "wb");

        if (!f || fwrite(constants, sizeof(constants), 1, f) != 1) {
            return 2;
        }

        fclose(f);
        return 0;
    }

    if (argc != 2) {
        printf("usage: test_grasswind <tests dir>\n");
        return 1;
    }

    std::string dir = argv[1];
    std::vector<uint8_t> stock = ReadFile(dir + "/standin_vs.cso");
    std::vector<uint8_t> expected = ReadFile(dir + "/standin_vs_patched.cso");

    // The stand-in: patched exactly as Microsoft's assembler encodes the block (standin_vs_patched.cso).
    std::vector<uint8_t> patched;
    Check(BleakGrassWindPatch(stock.data(), static_cast<uint32_t>(stock.size()), patched), "the stand-in is patched");
    Check(patched == expected, "the patched stand-in is the expected bytecode");

    std::vector<uint8_t> twice;
    Check(!BleakGrassWindPatch(patched.data(), static_cast<uint32_t>(patched.size()), twice), "a patched shader is not patched again");

    std::vector<uint8_t> back;
    Check(BleakGrassWindStock(patched.data(), static_cast<uint32_t>(patched.size()), back) && back == stock, "the stock bytecode comes back");
    Check(!BleakGrassWindStock(stock.data(), static_cast<uint32_t>(stock.size()), back), "a stock shader carries no stock bytecode");

    // The restore helper on a growable array.
    struct Array {
        std::vector<uint8_t> v;
        uint8_t* m_data;
        uint32_t Count() { return static_cast<uint32_t>(v.size()); }
        void SetCount(uint32_t n) { v.resize(n); m_data = v.data(); }
    } array;
    array.SetCount(static_cast<uint32_t>(patched.size()));
    memcpy(array.m_data, patched.data(), patched.size());
    Check(BleakGrassWindRestore(array) && array.v == stock, "BleakGrassWindRestore puts the stock bytecode back");
    Check(!BleakGrassWindRestore(array) && array.v == stock, "BleakGrassWindRestore leaves a stock shader alone");

    // Made-up bytecode.
    std::vector<uint32_t> minimal = Minimal();
    Check(Patches(minimal), "the minimal shader is patched");

    std::vector<uint32_t> vs20 = minimal;
    vs20[0] = 0xFFFE0200;
    Check(!Patches(vs20), "vs_2_0 is left alone");

    std::vector<uint32_t> noAnchor = minimal;
    noAnchor[10] = 0xA0E40002;
    Check(!Patches(noAnchor), "no add r0, r0, c3: left alone");

    std::vector<uint32_t> swapped = minimal;
    swapped[9] = 0xA0E40003;
    swapped[10] = 0x80E40000;
    Check(Patches(swapped), "add r0, c3, r0 is the anchor too");

    std::vector<uint32_t> noTexcoord = minimal;
    noTexcoord[2] = 0x80000003;
    Check(!Patches(noTexcoord), "no texture coordinate 0: left alone");

    std::vector<uint32_t> texcoordX = minimal;
    texcoordX[3] = 0x90010003;
    Check(!Patches(texcoordX), "texture coordinate without y: left alone");

    std::vector<uint32_t> ownConstant = minimal;
    ownConstant[13] = 0xA0E400F5;
    Check(!Patches(ownConstant), "the stock shader reads c245: left alone");

    std::vector<uint32_t> ownDef = minimal;
    ownDef.insert(ownDef.begin() + 1, { 0x05000051, 0xA00F00F0, 0, 0, 0, 0 });
    Check(!Patches(ownDef), "the stock shader defines c240: left alone");

    std::vector<uint32_t> relative = minimal;
    relative[13] = 0xA0E42000;
    relative.insert(relative.begin() + 14, 0xB0000000);
    relative[11] = 0x03000001;
    Check(!Patches(relative), "relative addressing: left alone");

    std::vector<uint32_t> manyTemps = minimal;
    manyTemps.insert(manyTemps.end() - 1, { 0x02000001, 0x800F001D, 0x80E40000 });
    Check(!Patches(manyTemps), "r29 in use (no four free temporaries): left alone");

    std::vector<uint32_t> fewTemps = minimal;
    fewTemps.insert(fewTemps.end() - 1, { 0x02000001, 0x800F001B, 0x80E40000 });
    Check(Patches(fewTemps), "r27 in use: r28 - r31 are free");

    std::vector<uint32_t> truncated(minimal.begin(), minimal.end() - 4);
    Check(!Patches(truncated), "no end token: left alone");

    std::vector<uint32_t> cut(minimal.begin(), minimal.begin() + 9);
    Check(!Patches(cut), "an instruction runs past the end: left alone");

    std::vector<uint8_t> odd = Bytes(minimal);
    odd.pop_back();
    Check(!BleakGrassWindPatch(odd.data(), static_cast<uint32_t>(odd.size()), patched), "a size that is no multiple of 4: left alone");
    Check(!BleakGrassWindPatch(nullptr, 0, patched), "no code: left alone");

    std::vector<uint8_t> badStock = expected;
    uint32_t hugeSize = 0x7FFFFFFF;
    memcpy(badStock.data() + 12, &hugeSize, 4);
    Check(!BleakGrassWindStock(badStock.data(), static_cast<uint32_t>(badStock.size()), back), "a stock size past the comment is refused");

    // Constants: strength 0 and no parting move nothing.
    BleakGrassWindInput still = {};
    still.seconds = 1234.5;
    float c[BLEAKGRASSWIND_CONSTANT_COUNT][4];
    BleakGrassWindConstants(still, c);
    Check(c[4][0] == 0.0f && c[4][1] == 0.0f && c[5][0] == 0.0f && c[5][1] == 0.0f, "strength 0: no wave amplitude");
    Check(c[3][0] == 0.0f && c[3][1] == 0.0f, "no player: no parting force");
    Check(c[8][0] == 1.0f && c[3][3] > -0.5f && c[3][3] <= 0.5f && c[8][3] > -0.5f && c[8][3] <= 0.5f, "phases in cycles, reduced");

    printf("%d checks, %d failed\n", s_checks, s_failed);
    return s_failed ? 1 : 0;
}
