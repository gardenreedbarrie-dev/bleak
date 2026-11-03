#ifndef ENGINE_SOURCE_MODEL2_M2DANCE_H
#define ENGINE_SOURCE_MODEL2_M2DANCE_H

#include <cstdint>
#include <vector>
#include "Engine/Source/Model2/BleakDance.h"

class C44Matrix;
class CM2Model;
struct M2DanceState;
class M2CompBone;
class M2ModelBone;

// BLEAKHOLD(dance): plays Bleakhold dance clips (BleakDance.h) on CM2Models.
//
// The game starts and stops a dance on a model from the main thread (M2DanceStart, M2DanceStop) and calls
// M2DancePrepareAll once a frame before the scenes animate; that builds the model's rig the first time (one per
// CM2Shared, kept until the shared model goes) and frees dances that have faded out. CM2Model::AnimateMT, which may run
// on the scene's animation thread, only reads that state: M2DanceBeginFrame samples the clip for the frame, and
// M2DanceBone replaces the local transform of every mapped bone in its bone loop. A model whose bones the rig cannot
// map (creatures, druid forms, vehicles) keeps its own animation.

// The pack the client ships, Interface\Bleakhold\Dances\Dances.bdc, loaded on first use (null when it is missing or
// not a valid pack; the reason goes to M2DancePackStatus).
const BleakDance::Pack* M2DancePack();
const char* M2DancePackStatus();
const BleakDance::Clip* M2DanceFindClip(uint32_t id);

// Starts `clip` on `model` (replacing a dance that plays there), fading it in over fadeInMs; startOffsetMs into the
// clip, so a dance that started elsewhere earlier joins in step.
void M2DanceStart(CM2Model* model, const BleakDance::Clip* clip, uint32_t fadeInMs, uint32_t startOffsetMs);
// Fades the model's dance out over fadeOutMs (0: at once).
void M2DanceStop(CM2Model* model, uint32_t fadeOutMs);
// The clip playing on the model (not fading out), or null.
const BleakDance::Clip* M2DancePlaying(const CM2Model* model);
// Milliseconds into the current loop of the model's dance.
uint32_t M2DanceLoopTime(const CM2Model* model);
// Why the model cannot dance ("" when its rig is fine or not built yet).
const char* M2DanceRigStatus(const CM2Model* model);
void M2DancePrepareAll();
// From ~CM2Model.
void M2DanceRelease(CM2Model* model);
// From ~CM2Shared.
void M2DanceReleaseRig(BleakDance::Rig* rig);

// One frame of a dance inside CM2Model::AnimateMT.
struct M2DanceFrame {
    const BleakDance::Rig* rig;
    const BleakDance::Quat* targets;
    BleakDance::Quat* world;
    BleakDance::Vec3 offset;
    float weight;
    uint32_t boneCount;
};

bool M2DanceBeginFrame(CM2Model* model, M2DanceFrame& frame);
// An animated bone: replaces `local` when the rig maps the bone and keeps the bone's model-space rotation.
void M2DanceBone(M2DanceFrame& frame, uint32_t index, const M2CompBone* boneData, const M2ModelBone* bone, uint32_t boneFlags, C44Matrix& local);
// A bone the client does not animate: it turns with its parent.
void M2DanceStillBone(M2DanceFrame& frame, uint32_t index, uint16_t parentIndex);

#endif
