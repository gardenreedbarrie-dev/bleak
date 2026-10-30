// BLEAKHOLD(dance): the engine side of the Bleakhold dances (M2Dance.h). The game decides who dances
// (WoW/Source/Ui/BleakholdDance.cpp); this file owns the clips, the rigs and the per-model state, and the hooks in
// CM2Model::AnimateMT.

#include "Engine/Source/Model2/M2Dance.h"
#include <algorithm>
#include <cstring>
#include <new>
#include <string>
#include "Engine/Source/BlizzardCore/SFile2-Core.h"
#include "Engine/Source/Model2/M2Data.h"
#include "Engine/Source/Model2/M2Model.h"
#include "Engine/Source/Model2/M2Scene.h"
#include "Engine/Source/Model2/M2Shared.h"
#include "Engine/Source/Tempest/C44Matrix.h"
#include "Engine/Source/Tempest/C4Quaternion.h"

// A dance on one model. Changed only on the main thread, outside the scenes' animation.
struct M2DanceState {
    CM2Model* model;
    const BleakDance::Clip* clip;
    uint32_t clipStart;        // scene ms at clip time 0
    const BleakDance::Clip* previous;   // the clip it replaced, faded across into this one
    uint32_t previousStart;
    uint32_t switchTime;       // scene ms the switch started
    uint32_t fadeStart;        // scene ms the fade-in started
    uint32_t fadeIn;
    uint32_t stopTime;         // scene ms the fade-out started; valid while stopping
    uint32_t fadeOut;
    uint32_t pendingOffset;    // clip ms at the start, applied once the model has a scene
    bool timed;                // the times above are set
    bool stopping;
    std::vector<BleakDance::Quat> targets;
    std::vector<BleakDance::Quat> world;
    BleakDance::Vec3 offset;
};

namespace {
    const char kPackFile[] = "Interface\\Bleakhold\\Dances\\Dances.bdc";

    const uint32_t kSwitchMs = 250;

    std::vector<M2DanceState*> s_states;
    BleakDance::Pack* s_pack;
    bool s_packTried;
    std::string s_packStatus = "not loaded";

    // The rigs, which live in their CM2Shared (m_bleakDanceRig); a rig that failed keeps its reason.
    BleakDance::Rig* BuildSharedRig(CM2Shared* shared) {
        M2Data* data = shared->m_data;
        uint32_t count = data->m_bones.m_count;
        std::vector<BleakDance::RigBone> bones(count);

        for (uint32_t i = 0; i < count; i++) {
            const M2CompBone& b = data->m_bones[i];
            bones[i].parent = b.m_parentIndex == 0xFFFF ? -1 : static_cast<int32_t>(b.m_parentIndex);
            bones[i].pivot = { b.m_pivot.x, b.m_pivot.y, b.m_pivot.z };
            bones[i].animated = (b.m_flags & 0x280) && !(b.m_flags & 0x7F);
        }

        std::vector<uint16_t> keys(data->m_boneIndicesById.m_count);

        for (uint32_t k = 0; k < keys.size(); k++) {
            keys[k] = data->m_boneIndicesById[k];
        }

        BleakDance::Rig* rig = new (std::nothrow) BleakDance::Rig();

        if (rig) {
            BleakDance::BuildRig(bones.data(), count, keys.data(), static_cast<uint32_t>(keys.size()), *rig);
        }

        return rig;
    }

    M2DanceState* Find(const CM2Model* model) {
        return model ? model->m_bleakDance : nullptr;
    }

    void Free(M2DanceState* state) {
        if (state->model && state->model->m_bleakDance == state) {
            state->model->m_bleakDance = nullptr;
        }

        s_states.erase(std::remove(s_states.begin(), s_states.end(), state), s_states.end());
        delete state;
    }

    float Smooth(float t) {
        if (t <= 0.0f) {
            return 0.0f;
        }

        if (t >= 1.0f) {
            return 1.0f;
        }

        return t * t * (3.0f - 2.0f * t);
    }

    // 0..1 weight of the dance at scene time `now`.
    float Weight(const M2DanceState* s, uint32_t now) {
        int32_t elapsed = static_cast<int32_t>(now - s->fadeStart);
        float w = elapsed < 0 ? 0.0f : (s->fadeIn ? Smooth(static_cast<float>(elapsed) / static_cast<float>(s->fadeIn)) : 1.0f);

        if (s->stopping) {
            int32_t gone = static_cast<int32_t>(now - s->stopTime);
            float out = s->fadeOut ? 1.0f - Smooth(static_cast<float>(gone) / static_cast<float>(s->fadeOut)) : 0.0f;
            w = std::min(w, out);
        }

        return w;
    }

    uint32_t Wrap(const BleakDance::Clip* clip, uint32_t ms) {
        uint32_t length = BleakDance::ClipLengthMs(*clip);
        return length ? ms % length : 0;
    }
}

const BleakDance::Pack* M2DancePack() {
    if (!s_packTried) {
        s_packTried = true;
        void* data = nullptr;
        uint32_t size = 0;

        // Flag 1 finds loose files too, as the AddOns and glue loaders use it: the pack ships loose in the package's
        // Data folder, and without the flag the client looks only inside MPQ archives.
        if (!SFile::ReadFile(nullptr, kPackFile, &data, &size, 0, 1, nullptr) || !data) {
            s_packStatus = "Interface\\Bleakhold\\Dances\\Dances.bdc is missing";
        } else {
            BleakDance::Pack* pack = new (std::nothrow) BleakDance::Pack();
            std::string error;

            if (pack && pack->Load(static_cast<const uint8_t*>(data), size, &error)) {
                s_pack = pack;
                s_packStatus = "";
            } else {
                delete pack;
                s_packStatus = "Dances.bdc is not a valid dance pack: " + error;
            }

            SFile::Unload(data);
        }
    }

    return s_pack;
}

const char* M2DancePackStatus() {
    M2DancePack();
    return s_packStatus.c_str();
}

const BleakDance::Clip* M2DanceFindClip(uint32_t id) {
    const BleakDance::Pack* pack = M2DancePack();
    return pack && id <= BleakDance::MAX_DANCE_ID ? pack->Find(static_cast<uint16_t>(id)) : nullptr;
}

void M2DanceStart(CM2Model* model, const BleakDance::Clip* clip, uint32_t fadeInMs, uint32_t startOffsetMs) {
    if (!model || !clip) {
        return;
    }

    M2DanceState* s = Find(model);
    uint32_t offset = Wrap(clip, startOffsetMs);

    if (s && s->timed && model->m_scene) {
        // Already dancing: fade across from the clip that plays (or fades out) into the new one.
        uint32_t now = model->m_scene->m_time;
        float weight = Weight(s, now);
        s->previous = s->clip;
        s->previousStart = s->clipStart;
        s->switchTime = now;
        s->clip = clip;
        s->clipStart = now - offset;

        if (s->stopping) {
            // Pick the fade-in up at the weight the fade-out had reached.
            s->stopping = false;
            s->fadeIn = fadeInMs;
            s->fadeStart = now - static_cast<uint32_t>(weight * static_cast<float>(fadeInMs) * 0.5f);
        }

        return;
    }

    if (!s) {
        s = new (std::nothrow) M2DanceState();

        if (!s) {
            return;
        }

        s->model = model;
        s->offset = { 0.0f, 0.0f, 0.0f };
        model->m_bleakDance = s;
        s_states.push_back(s);
    }

    s->clip = clip;
    s->previous = nullptr;
    s->fadeIn = fadeInMs;
    s->stopping = false;
    s->stopTime = 0;
    s->fadeOut = 0;
    s->pendingOffset = 0;
    s->timed = false;

    if (model->m_scene) {
        uint32_t now = model->m_scene->m_time;
        s->clipStart = now - offset;
        s->fadeStart = now;
        s->timed = true;
    } else {
        s->pendingOffset = offset;
    }
}

void M2DanceStop(CM2Model* model, uint32_t fadeOutMs) {
    M2DanceState* s = Find(model);

    if (!s || s->stopping) {
        return;
    }

    if (!fadeOutMs || !model->m_scene || !s->timed) {
        Free(s);
        return;
    }

    s->stopping = true;
    s->stopTime = model->m_scene->m_time;
    s->fadeOut = fadeOutMs;
}

const BleakDance::Clip* M2DancePlaying(const CM2Model* model) {
    M2DanceState* s = Find(model);
    return s && !s->stopping ? s->clip : nullptr;
}

uint32_t M2DanceLoopTime(const CM2Model* model) {
    M2DanceState* s = Find(model);

    if (!s || !s->timed || !model->m_scene) {
        return 0;
    }

    return Wrap(s->clip, model->m_scene->m_time - s->clipStart);
}

const char* M2DanceRigStatus(const CM2Model* model) {
    if (!model || !model->m_shared || !model->m_shared->m_bleakDanceRig) {
        return "";
    }

    const BleakDance::Rig* rig = model->m_shared->m_bleakDanceRig;
    return rig->ok ? "" : rig->reason.c_str();
}

void M2DancePrepareAll() {
    // Copy: Free changes the list.
    std::vector<M2DanceState*> states = s_states;

    for (M2DanceState* s : states) {
        CM2Model* model = s->model;

        if (!s->timed && model->m_scene) {
            uint32_t now = model->m_scene->m_time;
            s->clipStart = now - s->pendingOffset;
            s->fadeStart = now;
            s->pendingOffset = 0;
            s->timed = true;
        }

        if (s->previous && s->timed && model->m_scene && model->m_scene->m_time - s->switchTime >= kSwitchMs) {
            s->previous = nullptr;
        }

        if (s->stopping && model->m_scene && Weight(s, model->m_scene->m_time) <= 0.0f) {
            Free(s);
            continue;
        }

        CM2Shared* shared = model->m_shared;

        if (!shared || !shared->m_data || !(model->m_fFlags & 1)) {
            continue;
        }

        if (!shared->m_bleakDanceRig) {
            shared->m_bleakDanceRig = BuildSharedRig(shared);
        }

        uint32_t count = shared->m_data->m_bones.m_count;

        if (s->targets.size() != count) {
            s->targets.assign(count, BleakDance::IDENTITY);
            s->world.assign(count, BleakDance::IDENTITY);
        }
    }
}

void M2DanceRelease(CM2Model* model) {
    M2DanceState* s = Find(model);

    if (s) {
        Free(s);
    }
}

void M2DanceReleaseRig(BleakDance::Rig* rig) {
    delete rig;
}

bool M2DanceBeginFrame(CM2Model* model, M2DanceFrame& frame) {
    M2DanceState* s = model->m_bleakDance;

    if (!s || !s->clip || !s->timed || !model->m_scene || !model->m_shared) {
        return false;
    }

    const BleakDance::Rig* rig = model->m_shared->m_bleakDanceRig;
    uint32_t count = model->m_shared->m_data ? model->m_shared->m_data->m_bones.m_count : 0;

    if (!rig || !rig->ok || rig->rules.size() != count || s->targets.size() != count || !count) {
        return false;
    }

    uint32_t now = model->m_scene->m_time;
    float weight = Weight(s, now);

    if (weight <= 0.0f) {
        return false;
    }

    BleakDance::Vec3 hips;
    BleakDance::Quat rotations[BleakDance::JOINT_COUNT];
    BleakDance::SampleClip(*s->clip, now - s->clipStart, hips, rotations);
    uint32_t sinceSwitch = now - s->switchTime;

    if (s->previous && sinceSwitch < kSwitchMs) {
        BleakDance::Vec3 oldHips;
        BleakDance::Quat old[BleakDance::JOINT_COUNT];
        BleakDance::SampleClip(*s->previous, now - s->previousStart, oldHips, old);
        float t = Smooth(static_cast<float>(sinceSwitch) / static_cast<float>(kSwitchMs));

        for (uint32_t j = 0; j < BleakDance::JOINT_COUNT; j++) {
            rotations[j] = BleakDance::Slerp(old[j], rotations[j], t);
        }

        hips.x = oldHips.x + (hips.x - oldHips.x) * t;
        hips.y = oldHips.y + (hips.y - oldHips.y) * t;
        hips.z = oldHips.z + (hips.z - oldHips.z) * t;
    }
    BleakDance::PoseBones(*rig, hips, rotations, s->targets.data(), s->offset);

    frame.rig = rig;
    frame.targets = s->targets.data();
    frame.world = s->world.data();
    frame.offset = s->offset;
    frame.weight = weight;
    frame.boneCount = count;
    return true;
}

void M2DanceBone(M2DanceFrame& frame, uint32_t index, const M2CompBone* boneData, const M2ModelBone* bone, uint32_t boneFlags, C44Matrix& local) {
    if (index >= frame.boneCount) {
        return;
    }

    uint16_t parent = boneData->m_parentIndex;
    BleakDance::Quat parentWorld = parent < index ? frame.world[parent] : BleakDance::IDENTITY;
    BleakDance::Quat stock = BleakDance::IDENTITY;

    if (boneData->m_rotationTrack.m_sequenceTimes.m_count) {
        const C4Quaternion& q = bone->m_rotation.m_currentValue;
        stock = { q.x, q.y, q.z, q.w };
    }

    const BleakDance::Rule& rule = frame.rig->rules[index];

    if (rule.kind == BleakDance::RULE_NONE || (boneFlags & 0x7F)) {
        frame.world[index] = BleakDance::Normalize(BleakDance::Mul(parentWorld, stock));
        return;
    }

    BleakDance::Vec3 stockTranslation = { 0.0f, 0.0f, 0.0f };

    if (boneData->m_translationTrack.m_sequenceTimes.m_count) {
        const C3Vector& t = bone->m_translation.m_currentValue;
        stockTranslation = { t.x, t.y, t.z };
    }

    BleakDance::Quat rotation;
    BleakDance::Vec3 translation;
    frame.world[index] = BleakDance::OverrideBone(*frame.rig, index, parentWorld, frame.targets, frame.offset, stock,
                                                  stockTranslation, frame.weight, rotation, translation);

    // The client's own local transform, from the dance's rotation and translation (CM2Model::AnimateMT).
    C4Quaternion q;
    q.x = rotation.x;
    q.y = rotation.y;
    q.z = rotation.z;
    q.w = rotation.w;
    local = C44Matrix(q);
    const C3Vector& pivot = boneData->m_pivot;
    local.d0 = pivot.x + translation.x;
    local.d1 = pivot.y + translation.y;
    local.d2 = pivot.z + translation.z;
    local.Translate(C3Vector(-pivot.x, -pivot.y, -pivot.z));
}

void M2DanceStillBone(M2DanceFrame& frame, uint32_t index, uint16_t parentIndex) {
    if (index < frame.boneCount) {
        frame.world[index] = parentIndex < index ? frame.world[parentIndex] : BleakDance::IDENTITY;
    }
}
