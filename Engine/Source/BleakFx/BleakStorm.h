#ifndef ENGINE_SOURCE_BLEAKFX_BLEAKSTORM_H
#define ENGINE_SOURCE_BLEAKFX_BLEAKSTORM_H

#include <cstdint>

// BLEAKHOLD(storm): the maths of the Bleakhold Royale storm wall, with no Gx or game code so that it builds and is
// tested on any machine (Tools/StormWall/tests). WoW/Source/Ui/BleakholdStorm.cpp feeds it the circle the addon sends
// (BleakholdStorm_Set) and this frame's camera; BleakFx::RenderStorm draws what it builds. Positions are world yards
// (x north, y west, z up); the vertices are relative to the origin the world is drawn from.
namespace BleakStorm {
    // What a circle may hold: positions of a map (docs/BleakholdProtocol.md: |x|, |y| <= 17067), a radius, and the
    // shrink times of ROYS in ms (at most a day, like the addon's parser).
    const double kMaxCoordinate = 17067.0;
    const double kMaxRadius = 20000.0;
    const double kMaxShrinkMs = 86400000.0;
    // A circle no Set renewed for this long is forgotten (the addon itself gives up after 25 s without ROYS).
    const double kStaleSeconds = 30.0;
    // A circle smaller than this draws nothing (the final circle closes to 0, overtime has none).
    const double kMinRadius = 1.0;

    // The wall: about one column per kColumnYards of the edge, kMinSegments..kMaxSegments around; each column from
    // kSinkYards below the ground under it (no gap shows on a slope) to kHeightYards above it, and at least
    // kAboveCameraYards above the camera.
    const double kColumnYards = 12.0;
    const uint32_t kMinSegments = 48;
    const uint32_t kMaxSegments = 720;
    const double kSinkYards = 24.0;
    const double kHeightYards = 260.0;
    const double kAboveCameraYards = 150.0;
    // The next circle's ring: a low band from kRingSinkYards below the ground to kRingYards above it, taller further
    // off (kRingPerYard per yard from the camera) so that it stays a few pixels high.
    const double kRingSinkYards = 4.0;
    const double kRingYards = 2.5;
    const double kRingPerYard = 0.012;
    // The culling tests the wall between these heights around the camera's.
    const double kCullBelowYards = 800.0;
    const double kCullAboveYards = 1000.0;
    // Past the world's far plane (the camera's farZ) the low-detail horizon is drawn with a projection of its own, from
    // kHorizonOverlapYards before that plane on, into a depth range of its own between the world's and the sky's
    // (CWorldScene::BuildHorizonProjection and RenderHorizon). The wall draws its part out there the same way, so that
    // the horizon's terrain hides it where it stands in front of it.
    const double kHorizonOverlapYards = 50.0;
    // What lies past the far plane of the projection the wall is drawn with is kept at this fraction of it (clip z of
    // w), in front of the sky: in the world's pass when no horizon pass follows it, else in the horizon's pass. The
    // horizon's depth range ends where the sky's begins, so there the margin is many steps of a 24-bit depth buffer.
    const double kWorldFarClamp = 0.99999;
    const double kHorizonFarClamp = 0.999;

    // At most two vertices per column and six indices per segment.
    const uint32_t kMaxVertices = 2 * (kMaxSegments + 1);
    const uint32_t kMaxIndices = 6 * kMaxSegments;

    struct Circle {
        double x;
        double y;
        double r;
    };

    // The storm as BleakholdStorm_Set gets it: the fields of ROYS that the addon's R.Circle reads (Royale.lua).
    struct State {
        int32_t mapId;
        Circle cur;
        bool hasNext;
        Circle next;
        // GetTime() (seconds) when the ROYS arrived; the shrink runs from shrinkStartMs to shrinkEndMs after it.
        double recvAt;
        // R.Circle only shrinks with a next circle and a shrinkEndMs above 0 (shrinkStartMs: 0 when ROYS has none).
        bool hasShrink;
        double shrinkStartMs;
        double shrinkEndMs;
        // GetTime() after which the circle is forgotten.
        double expiresAt;
        // No purple over the world while the camera is outside the circle: the lobby, which lies outside circle 0
        // but out of the storm's reach.
        bool noTint;
    };

    // False when a field is not a finite number or is out of range. Without a next circle there is no shrink.
    bool Sanitize(State& state);

    // The circle at `now` (GetTime() seconds), as R.Circle has it: cur until the shrink starts, then moving
    // linearly to next until it ends, then next. moving (may be nullptr): it moves now.
    Circle CircleAt(const State& state, double now, bool* moving);

    bool Stale(const State& state, double now);

    // Distance from (x, y) to the edge of c: negative inside (R.OutsideBy).
    double EdgeDistance(const Circle& c, double x, double y);

    // Segments around a circle of radius r (0 when it is too small to draw), and how far a segment's middle is from
    // the true circle.
    uint32_t Segments(double radius);
    double MaxChordError(double radius, uint32_t segments);

    // Column i of `segments` (column `segments` is column 0 again).
    void ColumnPosition(const Circle& c, uint32_t segments, uint32_t column, double& x, double& y);

    // Which segments can be on the screen. viewProj (16 values, row vectors, C44Matrix order a0 .. d3) takes a point
    // relative to `origin` into clip space; each segment is tested as the four corners of its two columns between
    // zLow and zHigh (world z). Conservative: only a segment wholly beyond one side of the view is dropped (none
    // for being too far: the wall shows beyond the far plane). visible[i] for the segment from column i to i + 1;
    // returns how many are visible.
    uint32_t CullSegments(const Circle& c, uint32_t segments, const double origin[3], const double viewProj[16], double zLow, double zHigh, uint8_t* visible);

    // Whether the wall needs the horizon pass: the horizon (its projection from farZ - kHorizonOverlapYards to
    // horizonFar) reaches past the world's far plane farZ. The horizon's projection differs from the world's in its
    // depth only, so the segments CullSegments keeps for the world are the ones the horizon pass needs.
    bool HorizonPass(double farZ, double horizonFar);

    // Fills the heights not `known` among count values arranged in a ring from the nearest known ones on both
    // sides (linearly between them); with none known, all become `fallback`.
    void FillUnknown(float* values, const uint8_t* known, uint32_t count, float fallback);

    // A vertex: position relative to the origin, the circle's outward normal (horizontal), and its shape: yards
    // above the ground under its column and yards below its column's top.
    struct Vertex {
        float pos[3];
        float normal[3];
        float shape[2];
    };

    enum Kind {
        Kind_Wall = 0,
        Kind_Ring = 1,
    };

    // The triangles (a list, 6 indices per segment) of the visible segments of circle c. ground[i]: the ground z
    // under column i, for i in 0 .. segments (read for the columns of visible segments only). eye: the camera,
    // relative to origin. Returns the vertex count and sets indexCount; 0 for both when nothing is visible or the
    // buffers are too small.
    uint32_t Build(const Circle& c, Kind kind, uint32_t segments, const uint8_t* visible, const float* ground, const double origin[3], const double eye[3], Vertex* vertices, uint32_t vertexCapacity, uint16_t* indices, uint32_t indexCapacity, uint32_t& indexCount);

    // Where a view matrix (16 values, row vectors, C44Matrix order a0 .. d3; a rotation and a translation, no scale)
    // puts the camera: the point it takes to the origin of view space, in the coordinates the matrix starts from.
    void EyeFromView(const float view[16], double eye[3]);

    // The fraction of `value` (for texture offsets that wrap at 1).
    double Fraction(double value);
}

#endif
