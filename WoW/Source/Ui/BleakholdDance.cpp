// BLEAKHOLD(dance): the game side of the Bleakhold dances (BleakholdDance.h). Spell_C.cpp hands kits
// BLEAKHOLD_DANCE_KIT_BASE + N to OnKit; CGWorldFrame::OnLayerUpdate calls OnWorldLayerUpdate once a frame.

#include "WoW/Source/Ui/BleakholdDance.h"
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <new>
#include <vector>
#include "Engine/Source/BlizzardCore/SFile2-Core.h"
#include "Engine/Source/ConsoleBase/ConsoleVar.h"
#include "Engine/Source/ConsoleBase/Types.h"
#include "Engine/Source/FrameScript/FrameScript.h"
#include "Engine/Source/Model2/M2Dance.h"
#include "Engine/Source/Model2/M2Model.h"
#include "Engine/Source/Os/TimeManager.h"
#include "Engine/Source/SoundEngine/SoundEngine.h"
#include "Engine/Source/Storm/H/storm.h"
#include "Engine/Source/lua-5.1/src/lua.h"
#include "WoW/Common/BleakholdDance.h"
#include "WoW/Source/Object/ObjectClient/Object_C.h"
#include "WoW/Source/Object/ObjectClient/Unit_C.h"
#include "WoW/Source/ObjectMgrClient/ObjectMgrClient.h"
#include "WoW/Source/SoundInterface/SoundInterface2.h"
#include "WoW/Source/WowSvcs/WowSvcsClient/FriendList.h"

namespace {
    struct Dancer {
        WOWGUID guid;
        const BleakDance::Clip* clip;
        uint32_t startMs;          // OsGetAsyncTimeMs at clip time 0
        uint32_t kitMs;            // the last kit
        const CM2Model* model;     // the model it was started on; compared, never used
        bool sawState;             // the emote state said dance at least once
        bool local;                // started by BleakholdDance_PlayLocal, not by the server
        C3Vector startPosition;
        SESound* music;
    };

    std::vector<Dancer> s_dancers;
    CVar* s_dancesCVar;
    CVar* s_musicCVar;
    CVar* s_musicVolumeCVar;

    // The kit can arrive before the emote state; without the state after this long the dance stops.
    const uint32_t kStateGraceMs = 2500;
    // A loop kit only moves a dance that is further than this out of step.
    const uint32_t kResyncMs = 400;
    const uint32_t kFadeInMs = 250;
    const uint32_t kFadeOutMs = 300;
    const float kMusicFadeOut = 0.6f;
    const float kMusicMinDistance = 6.0f;
    const float kMusicMaxDistance = 40.0f;
    // A dance started without the server ends when the player moves this far (yards).
    const float kLocalMoveLimit = 0.15f;
    const size_t kMaxDancers = 64;

    const char kMusicFolder[] = "Interface\\Bleakhold\\Dances\\Music\\";
    const char* const kMusicExtensions[] = { ".mp3", ".ogg", ".wav" };

    struct MusicPath {
        uint16_t id;
        char path[96];      // "" when the dance has no music file
    };

    std::vector<MusicPath> s_musicPaths;

    bool Enabled() {
        return !s_dancesCVar || s_dancesCVar->m_intValue != 0;
    }

    // The music file of a dance (copied to `out`); false when it has none. Looked up once per dance.
    bool MusicFile(const BleakDance::Clip* clip, char* out, size_t size) {
        const MusicPath* found = nullptr;

        for (const MusicPath& m : s_musicPaths) {
            if (m.id == clip->id) {
                found = &m;
                break;
            }
        }

        if (!found) {
            MusicPath m;
            m.id = clip->id;
            m.path[0] = '\0';

            for (const char* ext : kMusicExtensions) {
                char path[96];
                SStrPrintf(path, sizeof(path), "%s%s%s", kMusicFolder, clip->key.c_str(), ext);

                if (SFile::FileExists(path)) {
                    SStrCopy(m.path, path, sizeof(m.path));
                    break;
                }
            }

            s_musicPaths.push_back(m);
            found = &s_musicPaths.back();
        }

        if (!found->path[0]) {
            return false;
        }

        if (out) {
            SStrCopy(out, found->path, static_cast<uint32_t>(size));
        }

        return true;
    }

    float MusicVolume() {
        if (!s_musicVolumeCVar) {
            return 0.8f;
        }

        float v = s_musicVolumeCVar->m_floatValue;
        return v >= 0.0f ? (v <= 1.0f ? v : 1.0f) : 0.0f;
    }

    void StopMusic(Dancer& d, bool immediate) {
        if (d.music) {
            d.music->Stop(immediate ? 1 : 0, immediate ? 0.0f : kMusicFadeOut);
            delete d.music;
            d.music = nullptr;
        }
    }

    void StartMusic(Dancer& d, const C3Vector& position) {
        StopMusic(d, true);

        if (!s_musicCVar || !s_musicCVar->m_intValue || !SE2::IsInitialized()) {
            return;
        }

        static CVar* s_enableAll = CVar::Lookup("Sound_EnableAllSound");
        static CVar* s_enableSFX = CVar::Lookup("Sound_EnableSFX");

        if (!s_enableAll || !s_enableAll->m_intValue || !s_enableSFX || !s_enableSFX->m_intValue) {
            return;
        }

        char file[96];

        if (!MusicFile(d.clip, file, sizeof(file))) {
            return;
        }

        SESound* sound = new (std::nothrow) SESound();

        if (!sound) {
            return;
        }

        if (!sound->Create3D(file, 1, nullptr, nullptr, false, true, 100, 1, 360.0f, 360.0f, 1.0f, nullptr)) {
            delete sound;
            return;
        }

        sound->Set3DPosition(position);
        sound->Set3DMinMaxDistance(kMusicMinDistance, kMusicMaxDistance);
        sound->SetChannelGroup(SI2::s_channelGroupNames[0], true);
        SI2SoundUserData* userData = new (SMemAlloc(sizeof(SI2SoundUserData), __FILE__, __LINE__, 0)) SI2SoundUserData();

        if (userData) {
            userData->m_name = "<BLEAKHOLD DANCE>";
            sound->SetUserData(userData);
        }

        sound->SetVolume(MusicVolume());
        sound->AttachToObject(d.guid.m_guid);
        sound->SetFadeInTime(0.2f);
        sound->Play();
        d.music = sound;
    }

    Dancer* Find(const WOWGUID& guid) {
        for (Dancer& d : s_dancers) {
            if (d.guid == guid) {
                return &d;
            }
        }

        return nullptr;
    }

    CGUnit_C* UnitOf(const WOWGUID& guid) {
        return static_cast<CGUnit_C*>(ClntObjMgrObjectPtr(guid, TYPEMASK_UNIT, __FILE__, __LINE__));
    }

    // Stops a dancer's dance on the unit's current model (never on a model the unit no longer has).
    void Stop(Dancer& d, CGUnit_C* unit, bool immediate) {
        if (unit && unit->m_worldModel && unit->m_worldModel == d.model) {
            M2DanceStop(unit->m_worldModel, immediate ? 0 : kFadeOutMs);
        }

        StopMusic(d, immediate);
    }

    void Remove(size_t index) {
        s_dancers.erase(s_dancers.begin() + static_cast<std::ptrdiff_t>(index));
    }

    void Start(const WOWGUID& guid, const BleakDance::Clip* clip, bool local) {
        CGUnit_C* unit = UnitOf(guid);

        if (!unit || !unit->m_worldModel) {
            return;
        }

        uint32_t now = OsGetAsyncTimeMs();
        Dancer* d = Find(guid);

        if (d) {
            d->kitMs = now;
            d->local = d->local && local;

            if (d->clip == clip && d->model == unit->m_worldModel) {
                // A loop kit: the dancer is at the start of a loop now. Only a dance well out of step moves.
                uint32_t length = BleakDance::ClipLengthMs(*clip);
                uint32_t at = M2DanceLoopTime(unit->m_worldModel);
                uint32_t off = length ? (at < length - at ? at : length - at) : 0;

                if (off > kResyncMs) {
                    M2DanceStart(unit->m_worldModel, clip, kFadeInMs, 0);
                    d->startMs = now;
                }

                return;
            }

            bool sameClip = d->clip == clip;
            d->clip = clip;
            d->startMs = now;
            d->model = unit->m_worldModel;
            M2DanceStart(unit->m_worldModel, clip, kFadeInMs, 0);

            if (!sameClip || !d->music) {
                StartMusic(*d, unit->GetPosition());
            }

            return;
        }

        if (s_dancers.size() >= kMaxDancers) {
            return;
        }

        Dancer n;
        n.guid = guid;
        n.clip = clip;
        n.startMs = now;
        n.kitMs = now;
        n.model = unit->m_worldModel;
        n.sawState = false;
        n.local = local;
        n.startPosition = unit->GetPosition();
        n.music = nullptr;
        s_dancers.push_back(n);
        M2DanceStart(unit->m_worldModel, clip, kFadeInMs, 0);
        StartMusic(s_dancers.back(), n.startPosition);
    }

    // False when the dancer is done (the dance is then stopped).
    bool Update(Dancer& d, uint32_t now) {
        CGUnit_C* unit = UnitOf(d.guid);

        if (!unit) {
            StopMusic(d, false);
            return false;
        }

        if (!Enabled() || unit->IsMounted() || unit->IsInVehicle() || unit->IsDeadOrGhost() || !unit->m_worldModel) {
            Stop(d, unit, false);
            return false;
        }

        if (d.local) {
            C3Vector delta = unit->GetPosition() - d.startPosition;

            if (delta.x * delta.x + delta.y * delta.y + delta.z * delta.z > kLocalMoveLimit * kLocalMoveLimit) {
                Stop(d, unit, false);
                return false;
            }
        } else {
            bool dancing = unit->m_unit && unit->m_unit->m_unitNpcEmotestate == BLEAKHOLD_EMOTE_STATE_DANCE;

            if (dancing) {
                d.sawState = true;
            } else if (d.sawState || now - d.kitMs > kStateGraceMs) {
                Stop(d, unit, false);
                return false;
            }
        }

        if (unit->m_worldModel != d.model || !M2DancePlaying(unit->m_worldModel)) {
            // A new model (a display change) joins the dance where it is.
            d.model = unit->m_worldModel;
            M2DanceStart(unit->m_worldModel, d.clip, kFadeInMs, now - d.startMs);
        }

        if (d.music) {
            d.music->Set3DPosition(unit->GetPosition());
            d.music->SetVolume(MusicVolume());
        }

        return true;
    }

    // ------------------------------------------------------------------------------------------------ Lua

    // BleakholdDance_Info(id) -> key, seconds, bpm, hasMusic; nil when this client has no such dance.
    int32_t Script_Info(lua_State* L) {
        const BleakDance::Clip* clip = lua_isnumber(L, 1) ? M2DanceFindClip(static_cast<uint32_t>(lua_tonumber(L, 1))) : nullptr;

        if (!clip) {
            lua_pushnil(L);
            return 1;
        }

        lua_pushstring(L, clip->key.c_str());
        lua_pushnumber(L, BleakDance::ClipLengthMs(*clip) / 1000.0);
        lua_pushnumber(L, clip->bpm100 / 100.0);

        if (MusicFile(clip, nullptr, 0)) {
            lua_pushboolean(L, 1);
        } else {
            lua_pushnil(L);
        }

        return 4;
    }

    // BleakholdDance_Status() -> "" when the dance pack loaded, else why not.
    int32_t Script_Status(lua_State* L) {
        lua_pushstring(L, M2DancePackStatus());
        return 1;
    }

    // BleakholdDance_PlayLocal(id) -> true when the player dances it here only (no realm, a preview); it ends when the
    // player moves.
    int32_t Script_PlayLocal(lua_State* L) {
        const BleakDance::Clip* clip = lua_isnumber(L, 1) ? M2DanceFindClip(static_cast<uint32_t>(lua_tonumber(L, 1))) : nullptr;
        WOWGUID player = ClntObjMgrGetActivePlayer();

        if (!clip || !player || !Enabled()) {
            lua_pushnil(L);
            return 1;
        }

        Start(player, clip, true);
        Dancer* d = Find(player);

        if (d) {
            CGUnit_C* unit = UnitOf(player);

            if (unit) {
                d->startPosition = unit->GetPosition();
            }

            lua_pushboolean(L, 1);
        } else {
            lua_pushnil(L);
        }

        return 1;
    }

    // BleakholdDance_Playing() -> id, seconds into the loop of the player's dance; nil when the player does not dance
    // one.
    int32_t Script_Playing(lua_State* L) {
        Dancer* d = Find(ClntObjMgrGetActivePlayer());
        CGUnit_C* unit = d ? UnitOf(d->guid) : nullptr;

        if (!d || !unit || !unit->m_worldModel || !M2DancePlaying(unit->m_worldModel)) {
            lua_pushnil(L);
            return 1;
        }

        lua_pushnumber(L, d->clip->id);
        lua_pushnumber(L, M2DanceLoopTime(unit->m_worldModel) / 1000.0);
        return 2;
    }

    // BleakholdDance_StopLocal() ends a dance BleakholdDance_PlayLocal started.
    int32_t Script_StopLocal(lua_State* L) {
        WOWGUID player = ClntObjMgrGetActivePlayer();

        for (size_t i = 0; i < s_dancers.size(); i++) {
            if (s_dancers[i].guid == player && s_dancers[i].local) {
                Stop(s_dancers[i], UnitOf(player), false);
                Remove(i);
                break;
            }
        }

        return 0;
    }

    // BleakholdDance_RigStatus() -> "" when the player's model can dance, else why not (for /bh dance debug).
    int32_t Script_RigStatus(lua_State* L) {
        CGUnit_C* unit = UnitOf(ClntObjMgrGetActivePlayer());
        lua_pushstring(L, unit && unit->m_worldModel ? M2DanceRigStatus(unit->m_worldModel) : "no player model");
        return 1;
    }

    struct ScriptFunction {
        const char* name;
        int32_t (*function)(lua_State*);
    };

    const ScriptFunction kScriptFunctions[] = {
        { "BleakholdDance_Info", &Script_Info },
        { "BleakholdDance_Status", &Script_Status },
        { "BleakholdDance_PlayLocal", &Script_PlayLocal },
        { "BleakholdDance_StopLocal", &Script_StopLocal },
        { "BleakholdDance_Playing", &Script_Playing },
        { "BleakholdDance_RigStatus", &Script_RigStatus },
    };
}

void CGBleakholdDance::InitializeGame() {
    // Flags 0: saved in Config.wtf, never deleted. setCommand false, so Lua's GetCVar/SetCVar find them.
    s_dancesCVar = CVar::Register("bleakDances", "Show Bleakhold dances", 0, "1", CGBleakholdDance::DancesCallback, CATEGORY_GAME, false, nullptr, false);
    s_musicCVar = CVar::Register("bleakDanceMusic", "Play the music of Bleakhold dances", 0, "1", nullptr, CATEGORY_SOUND, false, nullptr, false);
    s_musicVolumeCVar = CVar::Register("bleakDanceMusicVolume", "Volume of dance music (0 to 1)", 0, "0.8", nullptr, CATEGORY_SOUND, false, nullptr, false);
}

void CGBleakholdDance::ShutdownGame() {
    CGBleakholdDance::ClearAll();
    s_musicPaths.clear();
}

void CGBleakholdDance::ClearAll() {
    for (Dancer& d : s_dancers) {
        Stop(d, UnitOf(d.guid), true);
    }

    s_dancers.clear();
}

bool CGBleakholdDance::DancesCallback(CVar* var, const char* oldValue, const char* value, void* arg) {
    if (value && SStrToInt(value) == 0) {
        CGBleakholdDance::ClearAll();
    }

    return true;
}

void CGBleakholdDance::OnKit(const WOWGUID& guid, uint32_t dance) {
    if (!Enabled()) {
        return;
    }

    // Like chat from them, nobody on the ignore list dances for this player.
    if (FriendList::s_friendList && FriendList::s_friendList->IsIgnored(guid, true)) {
        return;
    }

    const BleakDance::Clip* clip = M2DanceFindClip(dance);

    if (clip) {
        Start(guid, clip, false);
    }
}

void CGBleakholdDance::OnWorldLayerUpdate() {
    uint32_t now = OsGetAsyncTimeMs();

    for (size_t i = 0; i < s_dancers.size();) {
        if (Update(s_dancers[i], now)) {
            i++;
        } else {
            Remove(i);
        }
    }

    M2DancePrepareAll();
}

void CGBleakholdDance::RegisterScriptFunctions() {
    for (const ScriptFunction& f : kScriptFunctions) {
        FrameScript_RegisterFunction(f.name, f.function);
    }
}

void CGBleakholdDance::UnregisterScriptFunctions() {
    for (const ScriptFunction& f : kScriptFunctions) {
        FrameScript_UnregisterFunction(f.name);
    }
}
