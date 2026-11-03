// Tests of Engine/Source/Model2/BleakDance.cpp (run_tests.py builds and runs it; the Python side compares):
//   dance_core_test --selftest                 pack validation and sampling on packs made here
//   dance_core_test --rig <skeleton.txt>       the rig and the bone loop's local transforms, as text
//   dance_core_test --pack <file.bdc> <id> <ms>...   samples of a clip, as text
#include "Engine/Source/Model2/BleakDance.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

using namespace BleakDance;

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

    void Put16(std::vector<uint8_t>& b, size_t at, uint32_t v) {
        b[at] = static_cast<uint8_t>(v & 0xFF);
        b[at + 1] = static_cast<uint8_t>((v >> 8) & 0xFF);
    }

    void Put32(std::vector<uint8_t>& b, size_t at, uint32_t v) {
        Put16(b, at, v & 0xFFFF);
        Put16(b, at + 2, v >> 16);
    }

    // A pack with one clip of `frames` frames: frame f has hips x = f / 8 and joint 0 turned f * 10 degrees about z.
    std::vector<uint8_t> MakePack(uint32_t frames, uint32_t fps, const char* key, uint16_t flags) {
        const uint32_t values = 3 + JOINT_COUNT * 4;
        size_t keyLength = strlen(key);
        size_t keyOffset = 12 + 24;
        size_t dataOffset = keyOffset + keyLength;
        dataOffset += dataOffset & 1;
        size_t dataSize = frames * values * 2;
        std::vector<uint8_t> b(dataOffset + dataSize, 0);
        memcpy(b.data(), "BHDC", 4);
        Put16(b, 4, 1);
        Put16(b, 6, JOINT_COUNT);
        Put16(b, 8, 1);
        Put16(b, 12, 7);
        Put16(b, 14, flags);
        Put16(b, 16, frames);
        Put16(b, 18, fps);
        Put16(b, 20, 12000);
        Put16(b, 22, static_cast<uint32_t>(keyLength));
        Put32(b, 24, static_cast<uint32_t>(keyOffset));
        Put32(b, 28, static_cast<uint32_t>(dataOffset));
        Put32(b, 32, static_cast<uint32_t>(dataSize));
        memcpy(b.data() + keyOffset, key, keyLength);

        for (uint32_t f = 0; f < frames; f++) {
            size_t at = dataOffset + f * values * 2;
            Put16(b, at, static_cast<uint16_t>(static_cast<int16_t>(f * 1024)));

            for (uint32_t j = 0; j < JOINT_COUNT; j++) {
                float half = j == 0 ? f * 10.0f * 3.14159265f / 360.0f : 0.0f;
                int16_t q[4] = { 0, 0, static_cast<int16_t>(std::lround(std::sin(half) * 32767.0f)), static_cast<int16_t>(std::lround(std::cos(half) * 32767.0f)) };

                for (int k = 0; k < 4; k++) {
                    Put16(b, at + 6 + (j * 4 + k) * 2, static_cast<uint16_t>(q[k]));
                }
            }
        }

        return b;
    }

    float AngleZ(const Quat& q) {
        return 2.0f * std::atan2(q.z, q.w) * 180.0f / 3.14159265f;
    }

    void SelfTest() {
        Pack pack;
        std::string error;
        std::vector<uint8_t> good = MakePack(4, 10, "spin_test", CLIP_LOOPS);
        Check(pack.Load(good.data(), good.size(), &error), "a valid pack loads");
        const Clip* clip = pack.Find(7);
        Check(clip && clip->key == "spin_test" && clip->frameCount == 4 && clip->fps == 10, "the clip's fields");
        Check(clip && ClipLengthMs(*clip) == 400, "the clip lasts 400 ms");
        Check(!pack.Find(8), "an unknown id is not found");

        if (clip) {
            Vec3 hips;
            Quat r[JOINT_COUNT];
            SampleClip(*clip, 150, hips, r);
            Check(std::fabs(hips.x - 0.1875f) < 1e-3f, "hips are interpolated between frames");
            Check(std::fabs(AngleZ(r[0]) - 15.0f) < 0.05f, "rotations are interpolated between frames");
            SampleClip(*clip, 350, hips, r);
            Check(std::fabs(hips.x - 0.1875f) < 1e-3f && std::fabs(AngleZ(r[0]) - 15.0f) < 0.05f, "a loop wraps from the last frame to the first");
            SampleClip(*clip, 400 + 150, hips, r);
            Check(std::fabs(AngleZ(r[0]) - 15.0f) < 0.05f, "the second loop repeats the first");
        }

        std::vector<uint8_t> once = MakePack(4, 10, "once", 0);
        Check(pack.Load(once.data(), once.size(), &error), "a clip that does not loop loads");
        clip = pack.Find(7);

        if (clip) {
            Vec3 hips;
            Quat r[JOINT_COUNT];
            SampleClip(*clip, 5000, hips, r);
            Check(std::fabs(hips.x - 0.375f) < 1e-3f, "a clip that does not loop holds its last frame");
        }

        struct Bad {
            const char* what;
            size_t at;
            int value;      // -1: truncate the file to `at`
        } bad[] = {
            { "bad magic", 0, 'X' },
            { "unknown version", 4, 2 },
            { "wrong joint count", 6, 21 },
            { "clip table past the end", 8, 200 },
            { "id above the limit", 12, 0x07FF },
            { "one frame", 16, 1 },
            { "no frame rate", 18, 0 },
            { "frame rate too high", 18, 121 },
            { "key past the end", 22, 0x7FFF },
            { "empty key", 22, 0 },
            { "key with a capital", 36, 'S' },
            { "data size wrong", 32, 1 },
            { "odd data offset", 28, 47 },
            { "data past the end", 0, -1 },
        };

        for (const Bad& b : bad) {
            std::vector<uint8_t> data = good;

            if (b.value < 0) {
                data.resize(data.size() - 1);
            } else if (b.at == 0 || b.at == 36) {
                data[b.at] = static_cast<uint8_t>(b.value);
            } else {
                Put16(data, b.at, static_cast<uint32_t>(b.value));
            }

            Pack p;
            bool loaded = p.Load(data.data(), data.size(), &error);
            Check(!loaded && p.Clips().empty(), b.what);
        }

        Check(!pack.Load(nullptr, 0, &error) && pack.Clips().empty(), "no data");
        std::vector<uint8_t> twice = good;
        Check(pack.Load(twice.data(), 12, &error) == false, "a header without its table");

        // Slerp and rotation helpers.
        Quat a = { 0.0f, 0.0f, 0.0f, 1.0f };
        Quat b = { 0.0f, 0.0f, std::sin(1.0f), std::cos(1.0f) };
        Quat m = Slerp(a, b, 0.5f);
        Check(std::fabs(m.z - std::sin(0.5f)) < 1e-5f, "slerp halfway");
        Vec3 v = Rotate(Quat { 0.0f, 0.0f, std::sin(3.14159265f / 4.0f), std::cos(3.14159265f / 4.0f) }, Vec3 { 1.0f, 0.0f, 0.0f });
        Check(std::fabs(v.x) < 1e-5f && std::fabs(v.y - 1.0f) < 1e-5f, "a quarter turn about z takes x to y");
    }

    bool ReadSkeleton(const char* path, std::vector<RigBone>& bones, std::vector<uint16_t>& keys, std::vector<std::vector<float>>& frames) {
        std::ifstream in(path);
        std::string word;
        size_t n;

        if (!(in >> word >> n) || word != "bones") {
            return false;
        }

        bones.resize(n);

        for (RigBone& b : bones) {
            int animated;
            in >> b.parent >> b.pivot.x >> b.pivot.y >> b.pivot.z >> animated;
            b.animated = animated != 0;
        }

        if (!(in >> word >> n) || word != "keys") {
            return false;
        }

        keys.resize(n);

        for (uint16_t& k : keys) {
            unsigned v;
            in >> v;
            k = static_cast<uint16_t>(v);
        }

        if (!(in >> word >> n) || word != "frames") {
            return false;
        }

        frames.assign(n, std::vector<float>(3 + JOINT_COUNT * 4));

        for (std::vector<float>& f : frames) {
            for (float& x : f) {
                in >> x;
            }
        }

        return static_cast<bool>(in);
    }

    int RigMode(const char* path) {
        std::vector<RigBone> bones;
        std::vector<uint16_t> keys;
        std::vector<std::vector<float>> frames;

        if (!ReadSkeleton(path, bones, keys, frames)) {
            printf("bad input\n");
            return 2;
        }

        Rig rig;
        BuildRig(bones.data(), static_cast<uint32_t>(bones.size()), keys.data(), static_cast<uint32_t>(keys.size()), rig);
        printf("ok %d\n", rig.ok ? 1 : 0);
        printf("reason %s\n", rig.ok ? "-" : rig.reason.c_str());

        if (!rig.ok) {
            return 0;
        }

        printf("root %d scale %.6f legs %d\n", rig.root, rig.scale, rig.hasLegs ? 1 : 0);

        for (size_t i = 0; i < rig.rules.size(); i++) {
            const Rule& r = rig.rules[i];

            if (r.kind != RULE_NONE) {
                printf("rule %zu %d %d %d %.6f %.6f %.6f %.6f %.6f\n", i, r.kind, r.joint, r.kind == RULE_RIGID ? r.owner : 0, r.fraction, r.align.x, r.align.y, r.align.z, r.align.w);
            }
        }

        std::vector<Quat> targets(bones.size()), world(bones.size());

        for (size_t f = 0; f < frames.size(); f++) {
            const std::vector<float>& v = frames[f];
            Vec3 hips = { v[0], v[1], v[2] };
            Quat rotations[JOINT_COUNT];

            for (uint32_t j = 0; j < JOINT_COUNT; j++) {
                rotations[j] = Normalize(Quat { v[3 + j * 4], v[4 + j * 4], v[5 + j * 4], v[6 + j * 4] });
            }

            Vec3 offset;
            PoseBones(rig, hips, rotations, targets.data(), offset);
            printf("frame %zu\n", f);

            for (size_t i = 0; i < bones.size(); i++) {
                int32_t p = bones[i].parent;
                Quat parentWorld = p >= 0 && static_cast<size_t>(p) < i ? world[p] : IDENTITY;
                Quat rotation = IDENTITY;
                Vec3 translation = { 0.0f, 0.0f, 0.0f };

                if (rig.rules[i].kind == RULE_NONE) {
                    world[i] = parentWorld;
                } else {
                    world[i] = OverrideBone(rig, static_cast<uint32_t>(i), parentWorld, targets.data(), offset, IDENTITY, translation, 1.0f, rotation, translation);
                }

                printf("local %zu %.6f %.6f %.6f %.6f %.6f %.6f %.6f\n", i, rotation.x, rotation.y, rotation.z, rotation.w, translation.x, translation.y, translation.z);
            }
        }

        return 0;
    }

    int PackMode(int argc, char** argv) {
        std::ifstream in(argv[2], std::ios::binary);
        std::vector<uint8_t> data((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        Pack pack;
        std::string error;

        if (!pack.Load(data.data(), data.size(), &error)) {
            printf("error %s\n", error.c_str());
            return 0;
        }

        const Clip* clip = pack.Find(static_cast<uint16_t>(atoi(argv[3])));

        if (!clip) {
            printf("missing\n");
            return 0;
        }

        printf("clip %s %u %u %u %u\n", clip->key.c_str(), clip->frameCount, clip->fps, clip->bpm100, ClipLengthMs(*clip));

        for (int k = 4; k < argc; k++) {
            Vec3 hips;
            Quat r[JOINT_COUNT];
            SampleClip(*clip, static_cast<uint32_t>(atoi(argv[k])), hips, r);
            printf("sample %s %.6f %.6f %.6f", argv[k], hips.x, hips.y, hips.z);

            for (uint32_t j = 0; j < JOINT_COUNT; j++) {
                printf(" %.6f %.6f %.6f %.6f", r[j].x, r[j].y, r[j].z, r[j].w);
            }

            printf("\n");
        }

        return 0;
    }
}

int main(int argc, char** argv) {
    if (argc == 2 && !strcmp(argv[1], "--selftest")) {
        SelfTest();
        printf("%d checks, %d failed\n", s_checks, s_failed);
        return s_failed ? 1 : 0;
    }

    if (argc == 3 && !strcmp(argv[1], "--rig")) {
        return RigMode(argv[2]);
    }

    if (argc >= 4 && !strcmp(argv[1], "--pack")) {
        return PackMode(argc, argv);
    }

    printf("usage: dance_core_test --selftest | --rig <skeleton.txt> | --pack <file.bdc> <id> <ms>...\n");
    return 1;
}
