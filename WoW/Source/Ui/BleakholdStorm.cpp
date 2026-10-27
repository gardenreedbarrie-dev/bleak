// BLEAKHOLD(storm): the game side of the Bleakhold Royale storm wall (BleakholdStorm.h). RoyaleHud.lua calls
// BleakholdStorm_Set with each ROYS; CGWorldFrame::OnWorldRender calls OnWorldRender once a frame, right after the
// liquids.

#include "WoW/Source/Ui/BleakholdStorm.h"
#include <cmath>
#include <cstdint>
#include "Engine/Source/BleakFx/BleakFx.h"
#include "Engine/Source/BleakFx/BleakStorm.h"
#include "Engine/Source/ConsoleBase/ConsoleVar.h"
#include "Engine/Source/ConsoleBase/Types.h"
#include "Engine/Source/FrameScript/FrameScript.h"
#include "Engine/Source/Gx/CGxDevice/CGxDevice.h"
#include "Engine/Source/Gx/Gx.h"
#include "Engine/Source/Os/TimeManager.h"
#include "Engine/Source/Tempest/C2Vector.h"
#include "Engine/Source/Tempest/C3Vector.h"
#include "Engine/Source/Tempest/C44Matrix.h"
#include "Engine/Source/lua-5.1/src/lua.h"
#include "WoW/Source/Object/ObjectClient/Object_C.h"
#include "WoW/Source/Object/ObjectClient/Unit_C.h"
#include "WoW/Source/ObjectMgrClient/ObjectMgrClient.h"
#include "WoW/Source/UIUtil/Camera.h"
#include "WoW/Source/Ui/WorldFrame.h"
#include "WoW/Source/WorldClient/DayNight.h"
#include "WoW/Source/WorldClient/DayNight__DNInfo.h"
#include "WoW/Source/WorldClient/Map.h"
#include "WoW/Source/WorldClient/MapChunk.h"
#include "WoW/Source/WorldClient/World.h"

namespace {
    // The purple over the world in the storm: full strength this far outside the circle (yards).
    const float kTint = 0.12f;
    const double kTintRampYards = 6.0;
    // The wall's motion runs this much faster while the storm moves, which eases in and out over about a second.
    const double kMovingSpeedUp = 0.8;
    const float kMovingEase = 1.5f;
    // The test circle (BleakholdStorm_Test): when it starts to close, and its limits.
    const double kTestDelayMs = 3000.0;
    const double kTestMinRadius = 5.0;
    const double kTestMaxRadius = 2000.0;
    const double kTestMaxSeconds = 600.0;
    // The ground of a column whose area is not loaded, when no column has one: this far below the camera.
    const float kUnknownGroundBelowCamera = 5.0f;

    CVar* s_wallCVar;
    bool s_hasState;
    BleakStorm::State s_state;

    // A steady clock for the wall's motion, and how much the storm moves now (eased).
    double s_phase;
    float s_moving;
    uint32_t s_lastMs;
    bool s_clockRunning;

    // The ground under the columns of one circle, kept while the circle stays where it is.
    struct Columns {
        BleakStorm::Circle circle;
        uint32_t segments;
        float ground[BleakStorm::kMaxSegments + 1];
        uint8_t known[BleakStorm::kMaxSegments + 1];
    };

    Columns s_wallColumns;
    Columns s_ringColumns;

    // This frame's meshes.
    uint8_t s_visible[BleakStorm::kMaxSegments];
    float s_frameGround[BleakStorm::kMaxSegments + 1];
    BleakStorm::Vertex s_wallVertices[BleakStorm::kMaxVertices];
    uint16_t s_wallIndices[BleakStorm::kMaxIndices];
    BleakStorm::Vertex s_ringVertices[BleakStorm::kMaxVertices];
    uint16_t s_ringIndices[BleakStorm::kMaxIndices];

    double Now() {
        return OsGetAsyncTimeMs() * 0.001;
    }

    // 0 off, 1 the wall and the next circle's ring, 2 the wall only.
    int32_t Mode() {
        return s_wallCVar ? s_wallCVar->m_intValue : 1;
    }

    // Why nothing is drawn now ("" when the wall draws), for BleakholdStorm_Status.
    const char* Status() {
        if (Mode() == 0) {
            return "off";
        }

        const char* support = BleakFx::StormSupport();

        if (*support) {
            return support;
        }

        if (!s_hasState || BleakStorm::Stale(s_state, Now())) {
            return "nodata";
        }

        return s_state.mapId == s_mapId ? "" : "map";
    }

    void ForgetColumns(Columns& columns) {
        columns.segments = 0;
    }

    void Clear() {
        s_hasState = false;
        ForgetColumns(s_wallColumns);
        ForgetColumns(s_ringColumns);
    }

    // The ground under (x, y): the terrain, or the water on it where that is higher. CMap::QueryHeight without the
    // map objects and doodads, which cost a hit test each (the wall goes through them; the depth test sorts that
    // out). False where the area is not loaded yet or the terrain has a hole there.
    bool GroundHeight(double x, double y, float& height) {
        if (CMap::bDungeon) {
            return false;
        }

        C3Vector position(static_cast<float>(x), static_cast<float>(y), 0.0f);
        CMapChunk* chunk = nullptr;
        float terrain = 0.0f;
        bool found = CMap::LinkStaticEntityGetChunk(position, &terrain, &chunk);

        if (!chunk) {
            return false;
        }

        // The chunk coordinates QueryHeight hands the liquid.
        C2Vector chunkPos(-(position.y - 17066.666f) * 0.24f, 0.24f * -(position.x - 17066.666f));
        float liquid = 0.0f;

        if (chunk->GetLiquidHeight(chunkPos, &liquid) && (!found || liquid > terrain)) {
            terrain = liquid;
            found = true;
        }

        if (found) {
            height = terrain;
        }

        return found;
    }

    // The visible part of circle c as `kind` into vertices and indices; returns the vertex count.
    uint32_t BuildCircle(const BleakStorm::Circle& c, BleakStorm::Kind kind, Columns& columns, const double origin[3], const double eye[3], const double viewProj[16], BleakStorm::Vertex* vertices, uint16_t* indices, uint32_t& indexCount) {
        indexCount = 0;
        uint32_t segments = BleakStorm::Segments(c.r);
        double eyeZ = origin[2] + eye[2];

        if (!segments || !BleakStorm::CullSegments(c, segments, origin, viewProj, eyeZ - BleakStorm::kCullBelowYards, eyeZ + BleakStorm::kCullAboveYards, s_visible)) {
            return 0;
        }

        if (columns.segments != segments || columns.circle.x != c.x || columns.circle.y != c.y || columns.circle.r != c.r) {
            columns.circle = c;
            columns.segments = segments;

            for (uint32_t i = 0; i <= segments; i++) {
                columns.known[i] = 0;
            }
        }

        // The ground under the columns of the visible segments (the others are not read), asked again each frame
        // while their area loads.
        for (uint32_t i = 0; i <= segments; i++) {
            bool needed = (i < segments && s_visible[i]) || (i > 0 && s_visible[i - 1]);

            if (needed && !columns.known[i]) {
                double x, y;
                BleakStorm::ColumnPosition(c, segments, i, x, y);
                columns.known[i] = GroundHeight(x, y, columns.ground[i]) ? 1 : 0;
            }

            s_frameGround[i] = columns.ground[i];
        }

        BleakStorm::FillUnknown(s_frameGround, columns.known, segments + 1, static_cast<float>(eyeZ) - kUnknownGroundBelowCamera);
        return BleakStorm::Build(c, kind, segments, s_visible, s_frameGround, origin, eye, vertices, BleakStorm::kMaxVertices, indices, BleakStorm::kMaxIndices, indexCount);
    }

    // A number argument, or false (nil, absent, or not a finite number).
    bool Number(lua_State* L, int32_t index, double& value) {
        if (!lua_isnumber(L, index)) {
            return false;
        }

        value = lua_tonumber(L, index);
        return std::isfinite(value);
    }

    // An argument that may be nil: false only when it is there but not a finite number.
    bool OptionalNumber(lua_State* L, int32_t index, double& value, bool& present) {
        present = !lua_isnoneornil(L, index);
        return !present || Number(L, index, value);
    }

    // ------------------------------------------------------------------------------------------------ Lua

    // BleakholdStorm_Set(mapId, curX, curY, curR, nextX, nextY, nextR, recvAt, shrinkStartMs, shrinkEndMs [, noTint])
    // -> true when the circle is taken, else nil (and the circle is forgotten). The fields of ROYS as the addon parsed
    // them: next* and the shrink times may be nil; recvAt is the GetTime() when the ROYS arrived, the shrink times are
    // ms after it. noTint true: no purple over the world outside the circle (the lobby, out of the storm's reach).
    int32_t Script_Set(lua_State* L) {
        BleakStorm::State state = {};
        double mapId = -1.0;
        double nextX = 0.0, nextY = 0.0, nextR = 0.0;
        double start = 0.0, end = 0.0;
        bool hasNextX, hasNextY, hasNextR, hasStart, hasEnd;
        bool ok = Number(L, 1, mapId) && Number(L, 2, state.cur.x) && Number(L, 3, state.cur.y) && Number(L, 4, state.cur.r)
            && OptionalNumber(L, 5, nextX, hasNextX) && OptionalNumber(L, 6, nextY, hasNextY) && OptionalNumber(L, 7, nextR, hasNextR)
            && Number(L, 8, state.recvAt) && OptionalNumber(L, 9, start, hasStart) && OptionalNumber(L, 10, end, hasEnd)
            && mapId >= 0.0 && mapId <= 1000000.0 && mapId == floor(mapId);

        if (ok) {
            state.mapId = static_cast<int32_t>(mapId);
            // A pair or nothing, as the addon has it.
            state.hasNext = hasNextX && hasNextY && hasNextR;
            state.next.x = nextX;
            state.next.y = nextY;
            state.next.r = nextR;
            state.hasShrink = hasEnd;
            state.shrinkStartMs = hasStart ? start : 0.0;
            state.shrinkEndMs = end;
            state.expiresAt = Now() + BleakStorm::kStaleSeconds;
            state.noTint = lua_toboolean(L, 11) != 0;
            ok = BleakStorm::Sanitize(state);
        }

        if (!ok) {
            Clear();
            lua_pushnil(L);
            return 1;
        }

        s_state = state;
        s_hasState = true;
        lua_pushboolean(L, 1);
        return 1;
    }

    // BleakholdStorm_Clear() forgets the circle.
    int32_t Script_Clear(lua_State* L) {
        Clear();
        return 0;
    }

    // BleakholdStorm_Status() -> "" when the wall draws, else why not: "off" (bleakStormWall 0), "device", "shaders",
    // "nodata" (no circle, or none for 30 s) or "map" (the circle is for another map).
    int32_t Script_Status(lua_State* L) {
        lua_pushstring(L, Status());
        return 1;
    }

    // BleakholdStorm_Test([radius [, seconds]]) -> true when a test circle is up: radius yards (60) around the
    // player, closing to half of it, a quarter radius off to the side, over `seconds` (30) from 3 s on, on any map;
    // it stays up 30 s after it has closed. For the owner to look at the wall anywhere.
    int32_t Script_Test(lua_State* L) {
        double radius = 60.0;
        double seconds = 30.0;
        bool present;

        if (!OptionalNumber(L, 1, radius, present) || !OptionalNumber(L, 2, seconds, present)) {
            lua_pushnil(L);
            return 1;
        }

        CGUnit_C* unit = static_cast<CGUnit_C*>(ClntObjMgrObjectPtr(ClntObjMgrGetActivePlayer(), TYPEMASK_UNIT, __FILE__, __LINE__));

        if (!unit || s_mapId < 0) {
            lua_pushnil(L);
            return 1;
        }

        radius = radius < kTestMinRadius ? kTestMinRadius : (radius > kTestMaxRadius ? kTestMaxRadius : radius);
        seconds = seconds < 1.0 ? 1.0 : (seconds > kTestMaxSeconds ? kTestMaxSeconds : seconds);
        C3Vector position = unit->GetPosition();
        double now = Now();

        BleakStorm::State state = {};
        state.mapId = s_mapId;
        state.cur.x = position.x;
        state.cur.y = position.y;
        state.cur.r = radius;
        state.hasNext = true;
        state.next.x = position.x + radius * 0.25;
        state.next.y = position.y;
        state.next.r = radius * 0.5;
        state.recvAt = now;
        state.hasShrink = true;
        state.shrinkStartMs = kTestDelayMs;
        state.shrinkEndMs = kTestDelayMs + seconds * 1000.0;
        state.expiresAt = now + kTestDelayMs / 1000.0 + seconds + BleakStorm::kStaleSeconds;

        if (!BleakStorm::Sanitize(state)) {
            lua_pushnil(L);
            return 1;
        }

        s_state = state;
        s_hasState = true;
        lua_pushboolean(L, 1);
        return 1;
    }

    struct ScriptFunction {
        const char* name;
        int32_t (*function)(lua_State*);
    };

    const ScriptFunction kScriptFunctions[] = {
        { "BleakholdStorm_Set", &Script_Set },
        { "BleakholdStorm_Clear", &Script_Clear },
        { "BleakholdStorm_Status", &Script_Status },
        { "BleakholdStorm_Test", &Script_Test },
    };
}

void CGBleakholdStorm::InitializeGame() {
    // Flags 0: saved in Config.wtf, never deleted. setCommand false, so Lua's GetCVar/SetCVar find it.
    s_wallCVar = CVar::Register("bleakStormWall", "Bleakhold Royale storm wall in the world (0 off, 1 the wall and the next circle, 2 the wall only)", 0, "1", nullptr, CATEGORY_GRAPHICS, false, nullptr, false);
}

void CGBleakholdStorm::ShutdownGame() {
    CGBleakholdStorm::ClearAll();
}

void CGBleakholdStorm::ClearAll() {
    Clear();
}

void CGBleakholdStorm::OnWorldRender() {
    uint32_t nowMs = OsGetAsyncTimeMs();
    double now = nowMs * 0.001;
    double elapsed = s_clockRunning ? (nowMs - s_lastMs) * 0.001 : 0.0;
    elapsed = elapsed > 0.25 ? 0.25 : elapsed;
    s_lastMs = nowMs;
    s_clockRunning = true;

    if (!s_hasState) {
        return;
    }

    if (BleakStorm::Stale(s_state, now)) {
        Clear();
        return;
    }

    int32_t mode = Mode();

    if (mode == 0 || s_state.mapId != s_mapId || *BleakFx::StormSupport() || !g_theGxDevicePtr) {
        return;
    }

    bool moving = false;
    BleakStorm::Circle circle = BleakStorm::CircleAt(s_state, now, &moving);
    float ease = static_cast<float>(elapsed) * kMovingEase;
    s_moving += ((moving ? 1.0f : 0.0f) - s_moving) * (ease < 1.0f ? ease : 1.0f);
    s_phase += elapsed * (1.0 + kMovingSpeedUp * s_moving);

    // The world is drawn relative to s_activeWorldView with the device's view and projection; the camera sits where
    // the view matrix puts the origin of view space (no scale: the transposed rotation undoes it).
    BleakFx::StormDraw draw = {};
    const C3Vector& origin = CWorldScene::s_activeWorldView;
    draw.origin[0] = origin.x;
    draw.origin[1] = origin.y;
    draw.origin[2] = origin.z;
    C44Matrix view;
    GxXformView(view);
    draw.viewProj = view * g_theGxDevicePtr->m_projNative;
    double eye[3];
    BleakStorm::EyeFromView(&view.a0, eye);
    double viewProj[16];
    const float* m = &draw.viewProj.a0;

    for (uint32_t i = 0; i < 16; i++) {
        viewProj[i] = m[i];
    }

    for (uint32_t i = 0; i < 3; i++) {
        draw.eye[i] = static_cast<float>(eye[i]);
    }

    draw.wall = s_wallVertices;
    draw.wallIndices = s_wallIndices;
    draw.wallVertexCount = BuildCircle(circle, BleakStorm::Kind_Wall, s_wallColumns, draw.origin, eye, viewProj, s_wallVertices, s_wallIndices, draw.wallIndexCount);

    // The ring where the storm will close to, unless the wall stands there already (the shrink is over).
    const BleakStorm::Circle& next = s_state.next;
    double apart = sqrt((next.x - circle.x) * (next.x - circle.x) + (next.y - circle.y) * (next.y - circle.y));
    bool ring = mode == 1 && s_state.hasNext && (fabs(next.r - circle.r) > 1.0 || apart > 1.0);
    draw.ring = s_ringVertices;
    draw.ringIndices = s_ringIndices;
    draw.ringVertexCount = ring ? BuildCircle(next, BleakStorm::Kind_Ring, s_ringColumns, draw.origin, eye, viewProj, s_ringVertices, s_ringIndices, draw.ringIndexCount) : 0;

    // In the storm (outside the circle, or anywhere once it has closed): the purple over the world. Not in the lobby,
    // which lies outside circle 0 but takes no storm damage.
    double outside = BleakStorm::EdgeDistance(circle, draw.origin[0] + eye[0], draw.origin[1] + eye[1]);
    draw.tint = outside > 0.0 && !s_state.noTint ? kTint * static_cast<float>(outside < kTintRampYards ? outside / kTintRampYards : 1.0) : 0.0f;

    // Past the world's far plane the low-detail terrain is drawn with the horizon's projection into a depth range of
    // its own (CWorldScene::RenderHorizon); the wall's part out there is drawn the same way, so that the horizon's
    // hills in front of it hide it. The projection goes through the device for its Direct3D form and is put back.
    CGCamera* camera = CGWorldFrame::GetActiveCamera();
    draw.horizon = camera && BleakStorm::HorizonPass(camera->m_farZ, World::s_horizonFarClipScale * World::s_farClip);

    if (draw.horizon) {
        C44Matrix horizon;
        CWorldScene::BuildHorizonProjection(&horizon);
        C44Matrix saved = g_theGxDevicePtr->m_projection;
        g_theGxDevicePtr->XformSetProjection(horizon);
        draw.horizonViewProj = view * g_theGxDevicePtr->m_projNative;
        g_theGxDevicePtr->XformSetProjection(saved);
        CWorldScene::BleakHorizonDepthRange(draw.horizonMinZ, draw.horizonMaxZ);
        draw.farZ = camera->m_farZ;
    }

    draw.phase = s_phase;
    draw.moving = s_moving;
    draw.strength = 1.0f;
    DayNight::DNInfo* dayNight = DayNight::GetInfo();
    draw.fogColor = dayNight->m_fog.m_color;
    draw.fogStart = dayNight->m_fog.m_start;
    draw.fogEnd = dayNight->m_fog.m_end;
    BleakFx::RenderStorm(draw);
}

void CGBleakholdStorm::RegisterScriptFunctions() {
    for (const ScriptFunction& f : kScriptFunctions) {
        FrameScript_RegisterFunction(f.name, f.function);
    }
}

void CGBleakholdStorm::UnregisterScriptFunctions() {
    for (const ScriptFunction& f : kScriptFunctions) {
        FrameScript_UnregisterFunction(f.name);
    }
}
