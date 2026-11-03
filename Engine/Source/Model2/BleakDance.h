#ifndef ENGINE_SOURCE_MODEL2_BLEAKDANCE_H
#define ENGINE_SOURCE_MODEL2_BLEAKDANCE_H

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

// BLEAKHOLD(dance): Bleakhold dances, played on any character model without new animations in its M2.
//
// A dance clip moves a canonical 22-joint skeleton (a T-pose in units of the hip-joint height, WoW axes: +x forward,
// +y left, +z up): every frame holds the hips position and each joint's world rotation relative to that rest pose.
// BuildRig maps the joints onto a model's bones from its key bones and bind pose (no bone names exist in an M2), and
// while a dance plays the model's bone loop (CM2Model::AnimateMT) replaces the local transform of every mapped bone,
// so the bone ends up with the clip's world rotation whatever its parents do. Bones the rig does not map (fingers,
// face, hair, cloth, tails) keep the animation that plays underneath. Tools/DanceForge writes the clips (the
// reference implementation of this file is Tools/DanceForge/dflib/retarget.py; the tests compare both).
//
// Self-contained (no engine headers) so that the tests can build it on its own.

namespace BleakDance {

const uint32_t JOINT_COUNT = 22;

struct Vec3 {
    float x;
    float y;
    float z;
};

struct Quat {
    float x;
    float y;
    float z;
    float w;
};

enum Joint {
    Hips, Spine, Spine2, Chest, Neck, Head,
    ClavL, UpperArmL, ForearmL, HandL,
    ClavR, UpperArmR, ForearmR, HandR,
    ThighL, CalfL, FootL, ToeL,
    ThighR, CalfR, FootR, ToeR,
};

// The canonical skeleton (Tools/DanceForge/dflib/skeleton.py holds the same numbers).
extern const char* const JOINT_NAMES[JOINT_COUNT];
extern const int8_t JOINT_PARENT[JOINT_COUNT];
extern const float JOINT_REST[JOINT_COUNT][3];
extern const float JOINT_DIRECTION[JOINT_COUNT][3];
extern const float JOINT_ROLL[JOINT_COUNT][3];

// ---------------------------------------------------------------------------------------------------- clips

// One dance of a pack. `frames` points into the pack's buffer: frameCount frames of 3 + 22 * 4 int16 values (the
// hips position / 8192, then x, y, z, w of every joint's rotation / 32767).
struct Clip {
    uint16_t id;
    uint16_t flags;
    uint16_t frameCount;
    uint16_t fps;
    uint16_t bpm100;
    std::string key;
    const int16_t* frames;
};

const uint16_t CLIP_LOOPS = 1;
const uint16_t MAX_DANCE_ID = 1023;

// A dance pack file (Interface\Bleakhold\Dances\Dances.bdc, written by DanceForge):
//   char magic[4] "BHDC", uint16 version 1, uint16 jointCount 22, uint16 clipCount, uint16 0,
//   clipCount entries of 24 bytes: uint16 id, flags, frameCount, fps, bpm100, keyLength, uint32 keyOffset,
//   dataOffset, dataSize (offsets from the start of the file), then the keys and the frame data. Little-endian.
class Pack {
    public:
    // Replaces the contents with the pack in `data`; false (and empty) when the file is not a valid pack.
    bool Load(const uint8_t* data, size_t size, std::string* error);
    const Clip* Find(uint16_t id) const;
    const std::vector<Clip>& Clips() const { return this->m_clips; }

    private:
    std::vector<uint8_t> m_buffer;
    std::vector<Clip> m_clips;
};

// Length of a clip in milliseconds.
uint32_t ClipLengthMs(const Clip& clip);

// The hips position and the joints' world rotations `timeMs` after the clip started (looping clips wrap, the others
// hold their last frame).
void SampleClip(const Clip& clip, uint32_t timeMs, Vec3& hips, Quat rotations[JOINT_COUNT]);

// ------------------------------------------------------------------------------------------------------ rig

// What BuildRig needs of a model's bone. animated: the client animates the bone (M2 bone flags 0x280) and it is no
// billboard and has no spherical or cylindrical transform (flags 0x7F).
struct RigBone {
    int32_t parent;
    Vec3 pivot;
    bool animated;
};

enum RuleKind : uint8_t {
    RULE_NONE,
    RULE_MAP,       // a joint's rotation
    RULE_SPINE,     // between Spine, Spine2 and Chest at `fraction`
    RULE_NECK,      // between Neck and Head at `fraction`
    RULE_RIGID,     // the rotation of bone `owner` (a bone between two mapped ones)
    RULE_PELVIS,    // the hips rotation
    RULE_ROOT,      // the hips rotation and the hips offset
    RULE_STILL,     // no rotation of its own (a twin of the next bone at the same pivot)
};

struct Rule {
    RuleKind kind;
    uint8_t joint;
    uint16_t owner;
    float fraction;
    Quat align;     // bind pose onto the canonical rest pose
};

struct Rig {
    bool ok = false;
    bool hasLegs = false;
    std::string reason;
    std::vector<Rule> rules;    // one per bone
    int32_t root = -1;
    float scale = 1.0f;         // model units per canonical hip height
};

// Maps the canonical skeleton onto `bones` (parents before children). keyBones[k] is the bone of key bone k (the
// M2's key-bone lookup; values outside the bone list mean none). Fails (rig.ok false, rig.reason) for models that
// are not humanoid enough: no hands with finger key bones, no spine from SpineLow to the shoulders, and so on. A
// model without two legs (a naga's tail) gets a rig for the upper body only.
bool BuildRig(const RigBone* bones, uint32_t boneCount, const uint16_t* keyBones, uint32_t keyBoneCount, Rig& rig);

// Model-space rotation of every mapped bone (targets[bone], for bones whose rule is not RULE_NONE or RULE_STILL)
// and the hips offset in model units, from one sample of a clip.
void PoseBones(const Rig& rig, const Vec3& hips, const Quat rotations[JOINT_COUNT], Quat* targets, Vec3& offset);

// -------------------------------------------------------------------------------------------------- the loop

// The local rotation and translation a mapped bone gets: `parentWorld` is the model-space rotation of its parent as
// the loop computed it, `stockRotation` and `stockTranslation` what the animation underneath gives the bone, weight
// 0..1 fades the dance in and out. Returns the bone's model-space rotation, which the loop keeps for its children.
Quat OverrideBone(const Rig& rig, uint32_t bone, const Quat& parentWorld, const Quat* targets, const Vec3& offset,
                  const Quat& stockRotation, const Vec3& stockTranslation, float weight, Quat& rotation,
                  Vec3& translation);

// ------------------------------------------------------------------------------------------------- the maths

Quat Mul(const Quat& a, const Quat& b);
Quat Conjugate(const Quat& q);
Quat Normalize(const Quat& q);
Quat Slerp(const Quat& a, const Quat& b, float t);
Vec3 Rotate(const Quat& q, const Vec3& v);
const Quat IDENTITY = { 0.0f, 0.0f, 0.0f, 1.0f };

}

#endif
