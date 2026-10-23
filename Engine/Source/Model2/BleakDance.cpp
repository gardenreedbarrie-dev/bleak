#include "Engine/Source/Model2/BleakDance.h"
#include <algorithm>
#include <cmath>
#include <cstring>

namespace BleakDance {

const char* const JOINT_NAMES[JOINT_COUNT] = {
    "Hips", "Spine", "Spine2", "Chest", "Neck", "Head",
    "ClavL", "UpperArmL", "ForearmL", "HandL",
    "ClavR", "UpperArmR", "ForearmR", "HandR",
    "ThighL", "CalfL", "FootL", "ToeL",
    "ThighR", "CalfR", "FootR", "ToeR",
};

const int8_t JOINT_PARENT[JOINT_COUNT] = {
    -1, 0, 1, 2, 3, 4,
    3, 6, 7, 8,
    3, 10, 11, 12,
    0, 14, 15, 16,
    0, 18, 19, 20,
};

const float JOINT_REST[JOINT_COUNT][3] = {
    { 0.0f, 0.0f, 1.0f }, { 0.0f, 0.0f, 1.11f }, { 0.0f, 0.0f, 1.23f }, { 0.0f, 0.0f, 1.37f }, { 0.0f, 0.0f, 1.66f }, { 0.0f, 0.0f, 1.78f },
    { 0.0f, 0.04f, 1.61f }, { 0.0f, 0.25f, 1.57f }, { 0.0f, 0.605f, 1.57f }, { 0.0f, 0.895f, 1.57f },
    { 0.0f, -0.04f, 1.61f }, { 0.0f, -0.25f, 1.57f }, { 0.0f, -0.605f, 1.57f }, { 0.0f, -0.895f, 1.57f },
    { 0.0f, 0.115f, 1.0f }, { 0.0f, 0.115f, 0.58f }, { 0.0f, 0.115f, 0.105f }, { 0.21f, 0.115f, 0.02f },
    { 0.0f, -0.115f, 1.0f }, { 0.0f, -0.115f, 0.58f }, { 0.0f, -0.115f, 0.105f }, { 0.21f, -0.115f, 0.02f },
};

// The foot points from the ankle to the toe: normalize(0.21, 0, -0.085).
const float FOOT_X = 0.92698359f;
const float FOOT_Z = -0.37520764f;

const float JOINT_DIRECTION[JOINT_COUNT][3] = {
    { 0.0f, 0.0f, 1.0f }, { 0.0f, 0.0f, 1.0f }, { 0.0f, 0.0f, 1.0f }, { 0.0f, 0.0f, 1.0f }, { 0.0f, 0.0f, 1.0f }, { 0.0f, 0.0f, 1.0f },
    { 0.0f, 1.0f, 0.0f }, { 0.0f, 1.0f, 0.0f }, { 0.0f, 1.0f, 0.0f }, { 0.0f, 1.0f, 0.0f },
    { 0.0f, -1.0f, 0.0f }, { 0.0f, -1.0f, 0.0f }, { 0.0f, -1.0f, 0.0f }, { 0.0f, -1.0f, 0.0f },
    { 0.0f, 0.0f, -1.0f }, { 0.0f, 0.0f, -1.0f }, { FOOT_X, 0.0f, FOOT_Z }, { 1.0f, 0.0f, 0.0f },
    { 0.0f, 0.0f, -1.0f }, { 0.0f, 0.0f, -1.0f }, { FOOT_X, 0.0f, FOOT_Z }, { 1.0f, 0.0f, 0.0f },
};

const float JOINT_ROLL[JOINT_COUNT][3] = {
    { 1.0f, 0.0f, 0.0f }, { 1.0f, 0.0f, 0.0f }, { 1.0f, 0.0f, 0.0f }, { 1.0f, 0.0f, 0.0f }, { 1.0f, 0.0f, 0.0f }, { 1.0f, 0.0f, 0.0f },
    { 1.0f, 0.0f, 0.0f }, { 1.0f, 0.0f, 0.0f }, { 1.0f, 0.0f, 0.0f }, { 1.0f, 0.0f, 0.0f },
    { 1.0f, 0.0f, 0.0f }, { 1.0f, 0.0f, 0.0f }, { 1.0f, 0.0f, 0.0f }, { 1.0f, 0.0f, 0.0f },
    { 1.0f, 0.0f, 0.0f }, { 1.0f, 0.0f, 0.0f }, { 0.0f, 0.0f, 1.0f }, { 0.0f, 0.0f, 1.0f },
    { 1.0f, 0.0f, 0.0f }, { 1.0f, 0.0f, 0.0f }, { 0.0f, 0.0f, 1.0f }, { 0.0f, 0.0f, 1.0f },
};

namespace {
    // Map tuning, the same as dflib/retarget.py.
    const float kSamePivot = 1e-3f;
    const float kSideFraction = 0.04f;
    const float kFootFraction = 0.25f;

    // Key bones (M2 key-bone lookup ids).
    const uint32_t kKeyArmL = 0;
    const uint32_t kKeyArmR = 1;
    const uint32_t kKeyShoulderL = 2;
    const uint32_t kKeyShoulderR = 3;
    const uint32_t kKeySpineLow = 4;
    const uint32_t kKeyHead = 6;
    const uint32_t kKeyFingersR[5] = { 8, 9, 10, 11, 12 };
    const uint32_t kKeyFingersL[5] = { 13, 14, 15, 16, 17 };
    const uint32_t kKeyRoot = 26;

    // Pack layout.
    const size_t kHeaderSize = 12;
    const size_t kEntrySize = 24;
    const uint32_t kValuesPerFrame = 3 + JOINT_COUNT * 4;
    const uint32_t kMaxFrames = 8192;
    const size_t kMaxKey = 32;

    Vec3 V(const float* f) {
        Vec3 v = { f[0], f[1], f[2] };
        return v;
    }

    Vec3 Add(const Vec3& a, const Vec3& b) {
        Vec3 v = { a.x + b.x, a.y + b.y, a.z + b.z };
        return v;
    }

    Vec3 Sub(const Vec3& a, const Vec3& b) {
        Vec3 v = { a.x - b.x, a.y - b.y, a.z - b.z };
        return v;
    }

    Vec3 Scale(const Vec3& a, float s) {
        Vec3 v = { a.x * s, a.y * s, a.z * s };
        return v;
    }

    float Dot(const Vec3& a, const Vec3& b) {
        return a.x * b.x + a.y * b.y + a.z * b.z;
    }

    Vec3 Cross(const Vec3& a, const Vec3& b) {
        Vec3 v = { a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x };
        return v;
    }

    float Length(const Vec3& a) {
        return std::sqrt(Dot(a, a));
    }

    Vec3 NormalizeV(const Vec3& a) {
        float n = Length(a);

        if (n < 1e-12f) {
            Vec3 v = { 1.0f, 0.0f, 0.0f };
            return v;
        }

        return Scale(a, 1.0f / n);
    }

    float Distance(const Vec3& a, const Vec3& b) {
        return Length(Sub(a, b));
    }

    // The rotation whose columns are x, y, z.
    Quat FromBasis(const Vec3& x, const Vec3& y, const Vec3& z) {
        float m00 = x.x, m10 = x.y, m20 = x.z;
        float m01 = y.x, m11 = y.y, m21 = y.z;
        float m02 = z.x, m12 = z.y, m22 = z.z;
        float t = m00 + m11 + m22;
        Quat q;

        if (t > 0.0f) {
            float s = std::sqrt(t + 1.0f) * 2.0f;
            q = { (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25f * s };
        } else if (m00 > m11 && m00 > m22) {
            float s = std::sqrt(1.0f + m00 - m11 - m22) * 2.0f;
            q = { 0.25f * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s };
        } else if (m11 > m22) {
            float s = std::sqrt(1.0f + m11 - m00 - m22) * 2.0f;
            q = { (m01 + m10) / s, 0.25f * s, (m12 + m21) / s, (m02 - m20) / s };
        } else {
            float s = std::sqrt(1.0f + m22 - m00 - m11) * 2.0f;
            q = { (m02 + m20) / s, (m12 + m21) / s, 0.25f * s, (m10 - m01) / s };
        }

        return Normalize(q);
    }

    Quat Axis(const Vec3& axis, float radians) {
        Vec3 a = NormalizeV(axis);
        float s = std::sin(radians * 0.5f);
        Quat q = { a.x * s, a.y * s, a.z * s, std::cos(radians * 0.5f) };
        return q;
    }

    Quat Between(const Vec3& from, const Vec3& to) {
        Vec3 a = NormalizeV(from);
        Vec3 b = NormalizeV(to);
        float d = Dot(a, b);

        if (d > 0.999999f) {
            return IDENTITY;
        }

        if (d < -0.999999f) {
            Vec3 axis = Cross(a, Vec3 { 1.0f, 0.0f, 0.0f });

            if (Length(axis) < 1e-6f) {
                axis = Cross(a, Vec3 { 0.0f, 1.0f, 0.0f });
            }

            return Axis(axis, 3.14159265f);
        }

        Vec3 c = Cross(a, b);
        return Normalize(Quat { c.x, c.y, c.z, 1.0f + d });
    }

    bool Frame(const Vec3& primary, const Vec3& secondary, Vec3& x, Vec3& y, Vec3& z) {
        x = NormalizeV(primary);
        y = Sub(secondary, Scale(x, Dot(secondary, x)));

        if (Length(y) < 1e-6f) {
            return false;
        }

        y = NormalizeV(y);
        z = Cross(x, y);
        return true;
    }

    // The rotation taking the frame (fromPrimary, fromSecondary) onto (toPrimary, toSecondary).
    Quat FromFrames(const Vec3& fromPrimary, const Vec3& fromSecondary, const Vec3& toPrimary, const Vec3& toSecondary) {
        Vec3 ax, ay, az, bx, by, bz;

        if (!Frame(fromPrimary, fromSecondary, ax, ay, az) || !Frame(toPrimary, toSecondary, bx, by, bz)) {
            return Between(fromPrimary, toPrimary);
        }

        return Normalize(Mul(FromBasis(bx, by, bz), Conjugate(FromBasis(ax, ay, az))));
    }

    uint16_t Read16(const uint8_t* p) {
        return static_cast<uint16_t>(p[0] | (p[1] << 8));
    }

    uint32_t Read32(const uint8_t* p) {
        return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) | (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
    }

    Quat DecodeQuat(const int16_t* v) {
        return Normalize(Quat { v[0] / 32767.0f, v[1] / 32767.0f, v[2] / 32767.0f, v[3] / 32767.0f });
    }

    // --------------------------------------------------------------------------------------------- rig search

    struct Bones {
        const RigBone* bones;
        uint32_t count;

        int32_t Parent(int32_t i) const {
            int32_t p = this->bones[i].parent;
            return p >= 0 && static_cast<uint32_t>(p) < this->count ? p : -1;
        }

        const Vec3& Pivot(int32_t i) const {
            return this->bones[i].pivot;
        }

        // i, its parent, ... up to the root (cycles are cut).
        std::vector<int32_t> Ancestors(int32_t i) const {
            std::vector<int32_t> out;

            while (i >= 0 && out.size() <= this->count) {
                out.push_back(i);
                i = this->Parent(i);
            }

            return out;
        }

        int32_t Lca(const std::vector<int32_t>& ids) const {
            std::vector<int32_t> first = this->Ancestors(ids[0]);

            for (int32_t a : first) {
                bool everywhere = true;

                for (size_t k = 1; k < ids.size() && everywhere; k++) {
                    std::vector<int32_t> other = this->Ancestors(ids[k]);
                    everywhere = std::find(other.begin(), other.end(), a) != other.end();
                }

                if (everywhere) {
                    return a;
                }
            }

            return -1;
        }

        // top .. bottom, both included; empty when bottom does not descend from top.
        std::vector<int32_t> Path(int32_t top, int32_t bottom) const {
            std::vector<int32_t> out;
            int32_t i = bottom;

            while (i >= 0 && i != top && out.size() <= this->count) {
                out.push_back(i);
                i = this->Parent(i);
            }

            if (i != top) {
                out.clear();
                return out;
            }

            out.push_back(top);
            std::reverse(out.begin(), out.end());
            return out;
        }
    };

    Quat Align(const Bones& b, int32_t bone, const Vec3& toward, uint32_t joint) {
        Vec3 d = Sub(toward, b.Pivot(bone));

        if (Length(d) < 1e-6f) {
            return IDENTITY;
        }

        Vec3 roll = V(JOINT_ROLL[joint]);
        return FromFrames(d, roll, V(JOINT_DIRECTION[joint]), roll);
    }

    bool Fail(Rig& rig, const char* reason) {
        rig.ok = false;
        rig.reason = reason;
        rig.rules.clear();
        return false;
    }

    void SetRule(Rig& rig, int32_t bone, RuleKind kind, uint32_t joint, float fraction, const Quat& align) {
        Rule& r = rig.rules[bone];
        r.kind = kind;
        r.joint = static_cast<uint8_t>(joint);
        r.owner = 0;
        r.fraction = fraction;
        r.align = align;
    }

    void SetRigid(Rig& rig, int32_t bone, int32_t owner) {
        Rule& r = rig.rules[bone];
        r.kind = RULE_RIGID;
        r.joint = 0;
        r.owner = static_cast<uint16_t>(owner);
        r.fraction = 0.0f;
        r.align = IDENTITY;
    }

    Quat SpineRotation(const Quat* rotations, float fraction) {
        if (fraction <= 0.5f) {
            return Slerp(rotations[Spine], rotations[Spine2], fraction * 2.0f);
        }

        return Slerp(rotations[Spine2], rotations[Chest], (fraction - 0.5f) * 2.0f);
    }
}

// --------------------------------------------------------------------------------------------------- the maths

Quat Mul(const Quat& a, const Quat& b) {
    Quat q = {
        a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
        a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
        a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
        a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
    };
    return q;
}

Quat Conjugate(const Quat& q) {
    Quat c = { -q.x, -q.y, -q.z, q.w };
    return c;
}

Quat Normalize(const Quat& q) {
    float n = std::sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w);

    if (n < 1e-12f) {
        return IDENTITY;
    }

    Quat r = { q.x / n, q.y / n, q.z / n, q.w / n };
    return r;
}

Quat Slerp(const Quat& a, const Quat& b0, float t) {
    Quat b = b0;
    float d = a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w;

    if (d < 0.0f) {
        b = { -b.x, -b.y, -b.z, -b.w };
        d = -d;
    }

    if (d > 0.9995f) {
        return Normalize(Quat { a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t, a.w + (b.w - a.w) * t });
    }

    float th = std::acos(std::min(1.0f, d));
    float s = std::sin(th);
    float wa = std::sin((1.0f - t) * th) / s;
    float wb = std::sin(t * th) / s;
    return Quat { a.x * wa + b.x * wb, a.y * wa + b.y * wb, a.z * wa + b.z * wb, a.w * wa + b.w * wb };
}

Vec3 Rotate(const Quat& q, const Vec3& v) {
    Vec3 u = { q.x, q.y, q.z };
    Vec3 t = Scale(Cross(u, v), 2.0f);
    return Add(Add(v, Scale(t, q.w)), Cross(u, t));
}

// ---------------------------------------------------------------------------------------------------- clips

bool Pack::Load(const uint8_t* data, size_t size, std::string* error) {
    this->m_buffer.clear();
    this->m_clips.clear();

    auto fail = [&](const char* why) {
        if (error) {
            *error = why;
        }

        this->m_buffer.clear();
        this->m_clips.clear();
        return false;
    };

    if (!data || size < kHeaderSize || std::memcmp(data, "BHDC", 4) != 0) {
        return fail("not a dance pack");
    }

    if (Read16(data + 4) != 1) {
        return fail("unknown pack version");
    }

    if (Read16(data + 6) != JOINT_COUNT) {
        return fail("wrong joint count");
    }

    uint32_t count = Read16(data + 8);

    if (kHeaderSize + count * kEntrySize > size) {
        return fail("clip table past the end");
    }

    this->m_buffer.assign(data, data + size);
    const uint8_t* base = this->m_buffer.data();

    for (uint32_t i = 0; i < count; i++) {
        const uint8_t* e = base + kHeaderSize + i * kEntrySize;
        Clip clip;
        clip.id = Read16(e);
        clip.flags = Read16(e + 2);
        clip.frameCount = Read16(e + 4);
        clip.fps = Read16(e + 6);
        clip.bpm100 = Read16(e + 8);
        uint32_t keyLength = Read16(e + 10);
        uint32_t keyOffset = Read32(e + 12);
        uint32_t dataOffset = Read32(e + 16);
        uint32_t dataSize = Read32(e + 20);

        if (clip.id > MAX_DANCE_ID || this->Find(clip.id)) {
            return fail("bad or repeated clip id");
        }

        if (clip.frameCount < 2 || clip.frameCount > kMaxFrames || clip.fps < 1 || clip.fps > 120) {
            return fail("bad frame count or rate");
        }

        if (keyLength < 1 || keyLength > kMaxKey || keyOffset > size || keyLength > size - keyOffset) {
            return fail("bad key");
        }

        for (uint32_t k = 0; k < keyLength; k++) {
            char c = static_cast<char>(base[keyOffset + k]);

            if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_')) {
                return fail("bad key");
            }
        }

        if (dataSize != clip.frameCount * kValuesPerFrame * 2 || (dataOffset & 1) || dataOffset > size || dataSize > size - dataOffset) {
            return fail("bad frame data");
        }

        clip.key.assign(reinterpret_cast<const char*>(base + keyOffset), keyLength);
        clip.frames = reinterpret_cast<const int16_t*>(base + dataOffset);
        this->m_clips.push_back(clip);
    }

    return true;
}

const Clip* Pack::Find(uint16_t id) const {
    for (const Clip& clip : this->m_clips) {
        if (clip.id == id) {
            return &clip;
        }
    }

    return nullptr;
}

uint32_t ClipLengthMs(const Clip& clip) {
    return clip.fps ? static_cast<uint32_t>(clip.frameCount * 1000u / clip.fps) : 0;
}

void SampleClip(const Clip& clip, uint32_t timeMs, Vec3& hips, Quat rotations[JOINT_COUNT]) {
    uint64_t scaled = static_cast<uint64_t>(timeMs) * clip.fps;
    uint32_t whole = static_cast<uint32_t>(scaled / 1000u);
    float frac = static_cast<float>(scaled % 1000u) / 1000.0f;
    uint32_t f0, f1;

    if (clip.flags & CLIP_LOOPS) {
        f0 = whole % clip.frameCount;
        f1 = (f0 + 1) % clip.frameCount;
    } else if (whole + 1 >= clip.frameCount) {
        f0 = f1 = clip.frameCount - 1u;
        frac = 0.0f;
    } else {
        f0 = whole;
        f1 = whole + 1;
    }

    const int16_t* a = clip.frames + f0 * kValuesPerFrame;
    const int16_t* b = clip.frames + f1 * kValuesPerFrame;
    hips.x = (a[0] + (b[0] - a[0]) * frac) / 8192.0f;
    hips.y = (a[1] + (b[1] - a[1]) * frac) / 8192.0f;
    hips.z = (a[2] + (b[2] - a[2]) * frac) / 8192.0f;

    for (uint32_t j = 0; j < JOINT_COUNT; j++) {
        rotations[j] = Slerp(DecodeQuat(a + 3 + j * 4), DecodeQuat(b + 3 + j * 4), frac);
    }
}

// ------------------------------------------------------------------------------------------------------ rig

bool BuildRig(const RigBone* bones, uint32_t boneCount, const uint16_t* keyBones, uint32_t keyBoneCount, Rig& rig) {
    rig = Rig();
    rig.rules.assign(boneCount, Rule { RULE_NONE, 0, 0, 0.0f, IDENTITY });
    Bones b = { bones, boneCount };

    auto kb = [&](uint32_t k) -> int32_t {
        if (k < keyBoneCount && keyBones[k] < boneCount) {
            return keyBones[k];
        }

        return -1;
    };

    int32_t root = kb(kKeyRoot);
    int32_t spineLow = kb(kKeySpineLow);
    int32_t head = kb(kKeyHead);
    int32_t clav[2] = { kb(kKeyShoulderL), kb(kKeyShoulderR) };
    int32_t upper[2] = { kb(kKeyArmL), kb(kKeyArmR) };

    if (root < 0 || spineLow < 0 || head < 0 || clav[0] < 0 || clav[1] < 0 || upper[0] < 0 || upper[1] < 0) {
        return Fail(rig, "missing key bones");
    }

    std::vector<int32_t> spineAncestors = b.Ancestors(spineLow);

    if (root == spineLow || std::find(spineAncestors.begin(), spineAncestors.end(), root) == spineAncestors.end()) {
        return Fail(rig, "SpineLow is not below Root");
    }

    int32_t chest = b.Lca({ clav[0], clav[1] });
    std::vector<int32_t> spine = chest >= 0 ? b.Path(spineLow, chest) : std::vector<int32_t>();

    if (spine.empty()) {
        return Fail(rig, "no spine from SpineLow to the shoulders");
    }

    std::vector<int32_t> neckPath = b.Path(chest, head);

    if (neckPath.size() < 2) {
        return Fail(rig, "the head is not below the chest");
    }

    std::vector<int32_t> neck(neckPath.begin() + 1, neckPath.end() - 1);
    float hipHeight = b.Pivot(root).z;

    if (hipHeight <= 1e-3f) {
        return Fail(rig, "Root is at or below the ground");
    }

    struct Arm {
        int32_t clav, upper, forearm, hand;
        std::vector<int32_t> chain;
    } arms[2];

    for (int side = 0; side < 2; side++) {
        const uint32_t* fingers = side == 0 ? kKeyFingersL : kKeyFingersR;
        std::vector<int32_t> f;

        for (int k = 0; k < 5; k++) {
            int32_t x = kb(fingers[k]);

            if (x >= 0) {
                f.push_back(x);
            }
        }

        if (f.size() < 2) {
            return Fail(rig, "not enough finger key bones");
        }

        int32_t hand = b.Lca(f);

        if (hand < 0 || b.Path(clav[side], upper[side]).empty()) {
            return Fail(rig, "arm chain broken");
        }

        std::vector<int32_t> chain = b.Path(upper[side], hand);

        if (chain.size() < 3) {
            return Fail(rig, "no forearm");
        }

        int32_t forearm = -1;
        float best = -1.0f;

        for (size_t k = 1; k + 1 < chain.size(); k++) {
            int32_t x = chain[k];
            float dist = Distance(b.Pivot(x), b.Pivot(upper[side]));

            if (Distance(b.Pivot(x), b.Pivot(hand)) > kSamePivot && dist > best) {
                forearm = x;
                best = dist;
            }
        }

        if (forearm < 0) {
            return Fail(rig, "no forearm");
        }

        arms[side] = { clav[side], upper[side], forearm, hand, chain };
    }

    // Legs: below Root but outside the upper body, the lowest animated bone on each side.
    std::vector<std::vector<int32_t>> children(boneCount);

    for (uint32_t i = 0; i < boneCount; i++) {
        int32_t p = b.Parent(static_cast<int32_t>(i));

        if (p >= 0) {
            children[p].push_back(static_cast<int32_t>(i));
        }
    }

    std::vector<uint8_t> upperBody(boneCount, 0);
    std::vector<int32_t> stack(1, spineLow);

    while (!stack.empty()) {
        int32_t x = stack.back();
        stack.pop_back();

        if (!upperBody[x]) {
            upperBody[x] = 1;
            stack.insert(stack.end(), children[x].begin(), children[x].end());
        }
    }

    std::vector<int32_t> lower;
    std::vector<uint8_t> seen(boneCount, 0);
    stack.assign(1, root);

    while (!stack.empty()) {
        int32_t x = stack.back();
        stack.pop_back();

        if (upperBody[x] || seen[x]) {
            continue;
        }

        seen[x] = 1;
        lower.push_back(x);
        stack.insert(stack.end(), children[x].begin(), children[x].end());
    }

    std::sort(lower.begin(), lower.end());

    struct Leg {
        std::vector<std::vector<int32_t>> pelvis;
        std::vector<std::vector<int32_t>> groups;
    } legs[2];
    int legCount = 0;

    for (int side = 0; side < 2; side++) {
        float sign = side == 0 ? 1.0f : -1.0f;
        int32_t low = -1;
        float lowZ = 0.0f, lowX = 0.0f;

        for (int32_t x : lower) {
            if (!bones[x].animated || sign * b.Pivot(x).y <= kSideFraction * hipHeight) {
                continue;
            }

            float z = std::round(b.Pivot(x).z * 10000.0f) / 10000.0f;
            float fwd = b.Pivot(x).x;

            if (low < 0 || z < lowZ || (z == lowZ && fwd > lowX)) {
                low = x;
                lowZ = z;
                lowX = fwd;
            }
        }

        if (low < 0 || b.Pivot(low).z > kFootFraction * hipHeight) {
            break;
        }

        std::vector<int32_t> chain = b.Path(root, low);
        std::vector<std::vector<int32_t>> groups;

        for (size_t k = 1; k < chain.size(); k++) {
            int32_t x = chain[k];

            if (!groups.empty() && Distance(b.Pivot(x), b.Pivot(groups.back().back())) < kSamePivot) {
                groups.back().push_back(x);
            } else {
                groups.push_back(std::vector<int32_t>(1, x));
            }
        }

        int hip = -1;

        for (size_t k = 0; k < groups.size(); k++) {
            if (sign * b.Pivot(groups[k].back()).y > kSideFraction * hipHeight) {
                hip = static_cast<int>(k);
                break;
            }
        }

        if (hip < 0 || static_cast<int>(groups.size()) - hip < 4) {
            break;
        }

        legs[side].pelvis.assign(groups.begin(), groups.begin() + hip);
        legs[side].groups.assign(groups.begin() + hip, groups.end());
        legCount++;
    }

    rig.hasLegs = legCount == 2;

    SetRule(rig, root, RULE_ROOT, Hips, 0.0f, IDENTITY);
    std::vector<float> marks(1, 0.0f);
    float total = 0.0f;

    for (size_t k = 0; k + 1 < spine.size(); k++) {
        total += Distance(b.Pivot(spine[k + 1]), b.Pivot(spine[k]));
        marks.push_back(total);
    }

    int32_t neckBase = neck.empty() ? head : neck[0];

    for (size_t k = 0; k < spine.size(); k++) {
        int32_t next = k + 1 < spine.size() ? spine[k + 1] : neckBase;
        float fraction = total > 1e-6f ? marks[k] / total : (k ? 1.0f : 0.0f);
        SetRule(rig, spine[k], RULE_SPINE, Spine, fraction, Align(b, spine[k], b.Pivot(next), Spine));
    }

    for (size_t k = 0; k < neck.size(); k++) {
        int32_t next = k + 1 < neck.size() ? neck[k + 1] : head;
        float fraction = (k + 1.0f) / (neck.size() + 1.0f);
        SetRule(rig, neck[k], RULE_NECK, Neck, fraction, Align(b, neck[k], b.Pivot(next), Neck));
    }

    SetRule(rig, head, RULE_MAP, Head, 0.0f, IDENTITY);

    for (int side = 0; side < 2; side++) {
        const Arm& a = arms[side];
        uint32_t jc = side == 0 ? ClavL : ClavR;
        SetRule(rig, a.clav, RULE_MAP, jc, 0.0f, Align(b, a.clav, b.Pivot(a.upper), jc));
        SetRule(rig, a.upper, RULE_MAP, jc + 1, 0.0f, Align(b, a.upper, b.Pivot(a.forearm), jc + 1));
        Quat forearmAlign = Align(b, a.forearm, b.Pivot(a.hand), jc + 2);
        SetRule(rig, a.forearm, RULE_MAP, jc + 2, 0.0f, forearmAlign);
        SetRule(rig, a.hand, RULE_MAP, jc + 3, 0.0f, forearmAlign);
        bool pastForearm = false;

        for (size_t k = 1; k + 1 < a.chain.size(); k++) {
            int32_t x = a.chain[k];

            if (x == a.forearm) {
                pastForearm = true;
                continue;
            }

            if (rig.rules[x].kind == RULE_NONE) {
                SetRigid(rig, x, pastForearm ? a.forearm : a.upper);
            }
        }
    }

    if (rig.hasLegs) {
        float thighs = 0.0f;

        for (int side = 0; side < 2; side++) {
            const Leg& leg = legs[side];
            uint32_t jt = side == 0 ? ThighL : ThighR;

            for (const std::vector<int32_t>& g : leg.pelvis) {
                for (int32_t x : g) {
                    SetRule(rig, x, RULE_PELVIS, Hips, 0.0f, IDENTITY);
                }
            }

            const std::vector<int32_t>& hip = leg.groups.front();
            const std::vector<int32_t>& knee = leg.groups[1];
            const std::vector<int32_t>& ankle = leg.groups[leg.groups.size() - 2];
            const std::vector<int32_t>& toe = leg.groups.back();
            SetRule(rig, hip.back(), RULE_MAP, jt, 0.0f, Align(b, hip.back(), b.Pivot(knee.back()), jt));
            SetRule(rig, knee.back(), RULE_MAP, jt + 1, 0.0f, Align(b, knee.back(), b.Pivot(ankle.back()), jt + 1));
            Quat footAlign = Align(b, ankle.back(), b.Pivot(toe.back()), jt + 2);
            SetRule(rig, ankle.back(), RULE_MAP, jt + 2, 0.0f, footAlign);
            SetRule(rig, toe.back(), RULE_MAP, jt + 3, 0.0f, footAlign);

            for (const std::vector<int32_t>* g : { &hip, &knee, &ankle, &toe }) {
                for (size_t k = 0; k + 1 < g->size(); k++) {
                    SetRule(rig, (*g)[k], RULE_STILL, 0, 0.0f, IDENTITY);
                }
            }

            for (size_t k = 2; k + 2 < leg.groups.size(); k++) {
                for (int32_t x : leg.groups[k]) {
                    SetRigid(rig, x, knee.back());
                }
            }

            thighs += b.Pivot(hip.back()).z;
        }

        rig.scale = thighs / 2.0f;
    } else {
        rig.scale = hipHeight;
    }

    for (uint32_t i = 0; i < boneCount; i++) {
        const Rule& r = rig.rules[i];

        if (r.kind == RULE_NONE) {
            continue;
        }

        if (!bones[i].animated) {
            return Fail(rig, "a mapped bone is not animated");
        }

        if (r.kind == RULE_RIGID && (r.owner >= boneCount || rig.rules[r.owner].kind == RULE_NONE || rig.rules[r.owner].kind == RULE_RIGID)) {
            return Fail(rig, "rigid bone without an owner");
        }
    }

    rig.root = root;
    rig.ok = true;
    return true;
}

void PoseBones(const Rig& rig, const Vec3& hips, const Quat rotations[JOINT_COUNT], Quat* targets, Vec3& offset) {
    uint32_t count = static_cast<uint32_t>(rig.rules.size());

    for (uint32_t i = 0; i < count; i++) {
        const Rule& r = rig.rules[i];

        switch (r.kind) {
            case RULE_MAP:
            case RULE_ROOT:
            case RULE_PELVIS:
                targets[i] = Mul(rotations[r.joint], r.align);
                break;

            case RULE_SPINE:
                targets[i] = Mul(SpineRotation(rotations, r.fraction), r.align);
                break;

            case RULE_NECK:
                targets[i] = Mul(Slerp(rotations[Neck], rotations[Head], r.fraction * 0.5f), r.align);
                break;

            default:
                targets[i] = IDENTITY;
                break;
        }
    }

    for (uint32_t i = 0; i < count; i++) {
        if (rig.rules[i].kind == RULE_RIGID) {
            targets[i] = targets[rig.rules[i].owner];
        }
    }

    offset = Scale(Sub(hips, V(JOINT_REST[Hips])), rig.scale);
}

// -------------------------------------------------------------------------------------------------- the loop

Quat OverrideBone(const Rig& rig, uint32_t bone, const Quat& parentWorld, const Quat* targets, const Vec3& offset,
                  const Quat& stockRotation, const Vec3& stockTranslation, float weight, Quat& rotation,
                  Vec3& translation) {
    const Rule& r = rig.rules[bone];
    Quat dance = IDENTITY;
    Vec3 move = { 0.0f, 0.0f, 0.0f };

    if (r.kind != RULE_STILL) {
        dance = Normalize(Mul(Conjugate(parentWorld), targets[bone]));
    }

    if (static_cast<int32_t>(bone) == rig.root) {
        move = Rotate(Conjugate(parentWorld), offset);
    }

    if (weight >= 1.0f) {
        rotation = dance;
        translation = move;
    } else {
        float w = weight > 0.0f ? weight : 0.0f;
        rotation = Slerp(Normalize(stockRotation), dance, w);
        translation = Add(stockTranslation, Scale(Sub(move, stockTranslation), w));
    }

    return Normalize(Mul(parentWorld, rotation));
}

}
