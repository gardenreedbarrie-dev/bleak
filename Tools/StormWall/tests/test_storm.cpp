// Tests of the storm wall's maths (Engine/Source/BleakFx/BleakStorm.cpp) and noise (BleakFxStormNoise.cpp), and of
// the storm on the minimap (held against a copy of the client's own minimap quads); run_tests.sh builds and runs them:
//   test_storm <dir>    <dir> holds circle_cases.csv, the cases Tools/UiLint/tests/test_royale.lua runs R.Circle on
#include "Engine/Source/BleakFx/BleakFxStormNoise.h"
#include "Engine/Source/BleakFx/BleakStorm.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
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

    bool Near(double a, double b, double tolerance) {
        return fabs(a - b) <= tolerance;
    }

    const double kPi = 3.14159265358979323846;
    const double kRecvAt = 1000.25;

    // A camera at `eye` (world) looking along the horizontal direction `yaw` (radians from +x towards +y), level,
    // with a 90 degree wide view, as a row-vector view-projection from positions relative to `origin`; Direct3D style
    // (clip z from 0 at the near plane to w at the far plane).
    void Camera(const double origin[3], const double eye[3], double yaw, double out[16]) {
        // View: x right, y up, z forward (left-handed, like the client's).
        double f[3] = { cos(yaw), sin(yaw), 0.0 };
        double up[3] = { 0.0, 0.0, 1.0 };
        double r[3] = { up[1] * f[2] - up[2] * f[1], up[2] * f[0] - up[0] * f[2], up[0] * f[1] - up[1] * f[0] };
        double e[3] = { eye[0] - origin[0], eye[1] - origin[1], eye[2] - origin[2] };
        double view[16] = {
            r[0], up[0], f[0], 0.0,
            r[1], up[1], f[1], 0.0,
            r[2], up[2], f[2], 0.0,
            -(e[0] * r[0] + e[1] * r[1] + e[2] * r[2]), -(e[0] * up[0] + e[1] * up[1] + e[2] * up[2]), -(e[0] * f[0] + e[1] * f[1] + e[2] * f[2]), 1.0,
        };
        double n = 0.2, far = 1277.0, aspect = 16.0 / 9.0;
        double sx = 1.0, sy = aspect;   // tan(45 degrees) = 1 across
        double proj[16] = {
            sx, 0.0, 0.0, 0.0,
            0.0, sy, 0.0, 0.0,
            0.0, 0.0, far / (far - n), 1.0,
            0.0, 0.0, -n * far / (far - n), 0.0,
        };

        for (int i = 0; i < 4; i++) {
            for (int j = 0; j < 4; j++) {
                double sum = 0.0;

                for (int k = 0; k < 4; k++) {
                    sum += view[i * 4 + k] * proj[k * 4 + j];
                }

                out[i * 4 + j] = sum;
            }
        }
    }

    // A point (relative to the origin) is in the view (any distance: the wall shows beyond the far plane).
    bool InView(const double m[16], double x, double y, double z) {
        double c[4];

        for (int k = 0; k < 4; k++) {
            c[k] = x * m[k] + y * m[4 + k] + z * m[8 + k] + m[12 + k];
        }

        return c[3] > 1e-3 && fabs(c[0]) <= c[3] && fabs(c[1]) <= c[3];
    }

    std::vector<std::string> Split(const std::string& line) {
        std::vector<std::string> fields;
        size_t start = 0;

        for (;;) {
            size_t comma = line.find(',', start);
            fields.push_back(line.substr(start, comma == std::string::npos ? std::string::npos : comma - start));

            if (comma == std::string::npos) {
                return fields;
            }

            start = comma + 1;
        }
    }

    void TestCircleCases(const std::string& dir) {
        std::string path = dir + "/circle_cases.csv";
        FILE* f = fopen(path.c_str(), "r");

        if (!f) {
            perror(path.c_str());
            exit(2);
        }

        char buffer[512];
        int cases = 0;

        while (fgets(buffer, sizeof(buffer), f)) {
            std::string line(buffer);

            while (!line.empty() && (line.back() == '\n' || line.back() == '\r')) {
                line.pop_back();
            }

            if (line.empty() || line[0] == '#') {
                continue;
            }

            std::vector<std::string> v = Split(line);

            if (v.size() != 14) {
                printf("FAIL: circle_cases.csv: %s has %zu fields\n", line.c_str(), v.size());
                s_failed++;
                continue;
            }

            BleakStorm::State s = {};
            s.mapId = 901;
            s.cur.x = atof(v[1].c_str());
            s.cur.y = atof(v[2].c_str());
            s.cur.r = atof(v[3].c_str());
            s.hasNext = !v[4].empty() && !v[5].empty() && !v[6].empty();
            s.next.x = atof(v[4].c_str());
            s.next.y = atof(v[5].c_str());
            s.next.r = atof(v[6].c_str());
            s.recvAt = kRecvAt;
            s.shrinkStartMs = v[7].empty() ? 0.0 : atof(v[7].c_str());
            s.hasShrink = !v[8].empty();
            s.shrinkEndMs = atof(v[8].c_str());
            s.expiresAt = kRecvAt + 1000.0;
            std::string what = "circle case " + v[0];
            Check(BleakStorm::Sanitize(s), (what + ": accepted").c_str());

            bool moving = false;
            BleakStorm::Circle c = BleakStorm::CircleAt(s, kRecvAt + atof(v[9].c_str()), &moving);
            Check(Near(c.x, atof(v[10].c_str()), 1e-3) && Near(c.y, atof(v[11].c_str()), 1e-3) && Near(c.r, atof(v[12].c_str()), 1e-3), what.c_str());
            Check(moving == (v[13] == "1"), (what + ": moving").c_str());
            Check(BleakStorm::CircleAt(s, kRecvAt + atof(v[9].c_str()), nullptr).r == c.r, (what + ": without moving").c_str());
            cases++;
        }

        fclose(f);
        Check(cases >= 15, "circle_cases.csv has its cases");
    }

    BleakStorm::State Valid() {
        BleakStorm::State s = {};
        s.mapId = 901;
        s.cur = { -267.0, -267.0, 320.0 };
        s.hasNext = true;
        s.next = { -200.0, -300.0, 180.0 };
        s.recvAt = kRecvAt;
        s.hasShrink = true;
        s.shrinkStartMs = 10000.0;
        s.shrinkEndMs = 30000.0;
        s.expiresAt = kRecvAt + 30.0;
        return s;
    }

    void TestSanitize() {
        const double nan = std::numeric_limits<double>::quiet_NaN();
        const double inf = std::numeric_limits<double>::infinity();
        BleakStorm::State s = Valid();
        Check(BleakStorm::Sanitize(s), "a ROYS circle is accepted");

        double* fields[] = { &s.cur.x, &s.cur.y, &s.cur.r, &s.next.x, &s.next.y, &s.next.r, &s.recvAt, &s.shrinkStartMs, &s.shrinkEndMs, &s.expiresAt };
        const double bad[] = { nan, inf, -inf };

        for (size_t i = 0; i < sizeof(fields) / sizeof(fields[0]); i++) {
            for (double b : bad) {
                s = Valid();
                *fields[i] = b;
                Check(!BleakStorm::Sanitize(s), "NaN and infinities are refused");
            }
        }

        s = Valid();
        s.cur.x = 17068.0;
        Check(!BleakStorm::Sanitize(s), "x beyond a map is refused");
        s = Valid();
        s.next.y = -17100.0;
        Check(!BleakStorm::Sanitize(s), "next y beyond a map is refused");
        s = Valid();
        s.cur.r = -1.0;
        Check(!BleakStorm::Sanitize(s), "a negative radius is refused");
        s = Valid();
        s.cur.r = 20001.0;
        Check(!BleakStorm::Sanitize(s), "a radius over 20000 is refused");
        s = Valid();
        s.cur.r = 0.0;
        Check(BleakStorm::Sanitize(s), "radius 0 (closed) is accepted");
        s = Valid();
        s.shrinkEndMs = 86400001.0;
        Check(!BleakStorm::Sanitize(s), "a shrink over a day is refused");
        s = Valid();
        s.shrinkStartMs = -1.0;
        Check(!BleakStorm::Sanitize(s), "a negative shrink start is refused");
        s = Valid();
        s.recvAt = -5.0;
        Check(!BleakStorm::Sanitize(s), "a negative recvAt is refused");

        // Without a next circle the shrink fields mean nothing; garbage in them is still refused.
        s = Valid();
        s.hasNext = false;
        s.next.x = 99999.0;
        Check(BleakStorm::Sanitize(s) && !s.hasShrink && s.next.x == s.cur.x, "no next circle: no shrink, next = cur");
        s = Valid();
        s.shrinkEndMs = 0.0;
        Check(BleakStorm::Sanitize(s) && !s.hasShrink, "shrinkEndMs 0: no shrink");

        s = Valid();
        Check(!BleakStorm::Stale(s, kRecvAt + 29.9), "fresh for 30 s");
        Check(BleakStorm::Stale(s, kRecvAt + 30.1), "stale after 30 s");
        s.expiresAt = nan;
        Check(BleakStorm::Stale(s, kRecvAt), "a NaN expiry is stale");
    }

    void TestEdgeAndSegments() {
        BleakStorm::Circle c = { 100.0, -50.0, 200.0 };
        Check(Near(BleakStorm::EdgeDistance(c, 100.0, -50.0), -200.0, 1e-9), "edge distance at the centre");
        Check(Near(BleakStorm::EdgeDistance(c, 400.0, -50.0), 100.0, 1e-9), "edge distance outside");
        Check(Near(BleakStorm::EdgeDistance(c, 100.0, 100.0), -50.0, 1e-9), "edge distance inside");

        Check(BleakStorm::Segments(0.0) == 0 && BleakStorm::Segments(0.99) == 0, "a circle under a yard draws nothing");
        Check(BleakStorm::Segments(std::numeric_limits<double>::quiet_NaN()) == 0, "a NaN radius draws nothing");
        Check(BleakStorm::Segments(1.0) == BleakStorm::kMinSegments, "small circles get the minimum");
        Check(BleakStorm::Segments(20000.0) == BleakStorm::kMaxSegments, "huge circles get the maximum");
        uint32_t previous = 0;
        bool growing = true, close = true, spaced = true;

        for (double r = 1.0; r <= 1400.0; r += 0.5) {
            uint32_t n = BleakStorm::Segments(r);
            growing = growing && n >= previous;
            close = close && BleakStorm::MaxChordError(r, n) <= 0.25;
            spaced = spaced && (n == BleakStorm::kMinSegments || n == BleakStorm::kMaxSegments || 2.0 * kPi * r / n <= BleakStorm::kColumnYards + 1e-9);
            previous = n;
        }

        Check(growing, "segments grow with the radius");
        Check(close, "the wall is within a quarter yard of the true circle up to r 1400");
        Check(BleakStorm::MaxChordError(BleakStorm::kMaxRadius, BleakStorm::Segments(BleakStorm::kMaxRadius)) <= 0.25, "and on the largest circle");
        Check(spaced, "columns at most kColumnYards apart");
        Check(BleakStorm::MaxChordError(1080.0, BleakStorm::Segments(1080.0)) < 0.02, "the first circle is round to 2 cm");

        double x, y;
        BleakStorm::ColumnPosition(c, 64, 64, x, y);
        double x0, y0;
        BleakStorm::ColumnPosition(c, 64, 0, x0, y0);
        Check(x == x0 && y == y0, "the last column is the first one exactly");
        BleakStorm::ColumnPosition(c, 64, 16, x, y);
        Check(Near(x, 100.0, 1e-9) && Near(y, 150.0, 1e-9), "a quarter round is +y");
    }

    void TestCulling() {
        double origin[3] = { 1000.0, -2000.0, 50.0 };
        double eye[3] = { 1000.0, -2000.0, 52.0 };
        BleakStorm::Circle c = { 1000.0, -2000.0, 300.0 };
        uint32_t n = BleakStorm::Segments(c.r);
        std::vector<uint8_t> visible(n);
        bool noFalseDrops = true;
        bool someDropped = true;
        bool facing = true;

        for (int k = 0; k < 8; k++) {
            double yaw = k * kPi / 4.0 + 0.1;
            double m[16];
            Camera(origin, eye, yaw, m);
            uint32_t count = BleakStorm::CullSegments(c, n, origin, m, eye[2] - 800.0, eye[2] + 1000.0, visible.data());
            uint32_t counted = 0;

            for (uint32_t i = 0; i < n; i++) {
                counted += visible[i];

                if (visible[i]) {
                    continue;
                }

                // A dropped segment: no point of it (between the culling heights) may be in the view.
                for (int a = 0; a <= 8; a++) {
                    double angle = 2.0 * kPi * (i + a / 8.0) / n;
                    double px = c.x + c.r * cos(angle) - origin[0];
                    double py = c.y + c.r * sin(angle) - origin[1];

                    for (int h = 0; h <= 8; h++) {
                        double pz = eye[2] - 800.0 + h * 1800.0 / 8.0 - origin[2];
                        noFalseDrops = noFalseDrops && !InView(m, px, py, pz);
                    }
                }
            }

            Check(count == counted, "CullSegments counts what it marks");
            // From the middle with a 90 degree view, about a quarter of the ring (plus the partial segments).
            someDropped = someDropped && count < n / 2 && count > n / 8;

            // The segment straight ahead is there.
            uint32_t ahead = static_cast<uint32_t>(yaw / (2.0 * kPi) * n) % n;
            facing = facing && visible[ahead];
        }

        Check(noFalseDrops, "no visible part of the wall is culled");
        Check(someDropped, "the part behind the camera is culled");
        Check(facing, "the wall ahead is kept");

        // Outside the circle, looking away from it: nothing; looking at it: both sides of it.
        double outEye[3] = { 1000.0 + 600.0, -2000.0, 52.0 };
        double m[16];
        Camera(origin, outEye, 0.0, m);
        Check(BleakStorm::CullSegments(c, n, origin, m, outEye[2] - 800.0, outEye[2] + 1000.0, visible.data()) == 0, "looking away from the circle: nothing");
        Camera(origin, outEye, kPi, m);
        uint32_t seen = BleakStorm::CullSegments(c, n, origin, m, outEye[2] - 800.0, outEye[2] + 1000.0, visible.data());
        Check(seen > n / 3 && visible[0] && visible[n / 2], "looking at the circle from outside: its near and far side");
    }

    // The part of the wall past the world's far plane goes into the horizon's depth range (World.cpp's
    // s_horizonMinZ, s_horizonMaxZ), which ends where the sky's begins (DayNight.cpp's s_skyMinZ).
    void TestHorizon() {
        Check(BleakStorm::HorizonPass(777.0, 4.0 * 777.0), "the default horizon reaches past the far plane");
        Check(BleakStorm::HorizonPass(183.0, 4.0 * 183.0), "so does the shortest view distance's");
        Check(!BleakStorm::HorizonPass(777.0, 777.0), "a horizon ending at the far plane: one pass");
        Check(!BleakStorm::HorizonPass(777.0, 600.0), "a horizon short of the far plane: one pass");
        Check(!BleakStorm::HorizonPass(50.0, 400.0), "no horizon starting at the camera");
        Check(!BleakStorm::HorizonPass(std::numeric_limits<double>::quiet_NaN(), 3000.0), "NaN far plane");
        Check(!BleakStorm::HorizonPass(777.0, std::numeric_limits<double>::infinity()), "infinite horizon");

        const double worldMaxZ = 0.94;   // CWorld::s_unk_ADEEE4, the world's viewport
        const double horizonMinZ = 0.998046875;
        const double horizonMaxZ = 0.9990234375;
        const double skyMinZ = 0.9990234375;
        const double step = 1.0 / 16777216.0;   // a 24-bit depth buffer
        double world = worldMaxZ * BleakStorm::kWorldFarClamp;
        double horizon = horizonMinZ + (horizonMaxZ - horizonMinZ) * BleakStorm::kHorizonFarClamp;
        Check(world < horizonMinZ, "the world's clamp stays in front of the horizon and the sky");
        Check(horizon < skyMinZ - 8.0 * step, "the horizon's clamp stays in front of the sky by many depth steps");
        Check(horizonMinZ + (horizonMaxZ - horizonMinZ) * BleakStorm::kWorldFarClamp > skyMinZ - 2.0 * step, "the world's clamp would not do there");
        Check(BleakStorm::kHorizonFarClamp > 0.0 && BleakStorm::kWorldFarClamp > 0.0, "0 means clipped at the far plane");
    }

    void TestEye() {
        double origin[3] = { 16000.0, -16500.0, 120.0 };
        double eye[3] = { 16012.5, -16480.25, 131.0 };
        bool found = true;

        for (int k = 0; k < 6; k++) {
            double m[16];
            float view[16];
            // Camera() builds the view-projection; the view alone is the same with an identity projection.
            double yaw = k * 1.1 - 2.0;
            double f[3] = { cos(yaw), sin(yaw), 0.0 };
            double r[3] = { -f[1], f[0], 0.0 };
            double e[3] = { eye[0] - origin[0], eye[1] - origin[1], eye[2] - origin[2] };
            double rows[16] = {
                r[0], 0.0, f[0], 0.0,
                r[1], 0.0, f[1], 0.0,
                r[2], 1.0, f[2], 0.0,
                -(e[0] * r[0] + e[1] * r[1] + e[2] * r[2]), -e[2], -(e[0] * f[0] + e[1] * f[1] + e[2] * f[2]), 1.0,
            };

            for (int i = 0; i < 16; i++) {
                view[i] = static_cast<float>(rows[i]);
                m[i] = rows[i];
            }

            double got[3];
            BleakStorm::EyeFromView(view, got);
            found = found && Near(got[0], e[0], 1e-3) && Near(got[1], e[1], 1e-3) && Near(got[2], e[2], 1e-3);

            // And that point goes to the origin of view space.
            double v0 = got[0] * m[0] + got[1] * m[4] + got[2] * m[8] + m[12];
            double v2 = got[0] * m[2] + got[1] * m[6] + got[2] * m[10] + m[14];
            found = found && Near(v0, 0.0, 1e-3) && Near(v2, 0.0, 1e-3);
        }

        Check(found, "the camera from the view matrix");
    }

    void TestFillUnknown() {
        float v[8] = { 10.0f, 0.0f, 0.0f, 40.0f, 0.0f, 0.0f, 0.0f, 0.0f };
        uint8_t known[8] = { 1, 0, 0, 1, 0, 0, 0, 0 };
        BleakStorm::FillUnknown(v, known, 8, -99.0f);
        Check(Near(v[1], 20.0, 1e-4) && Near(v[2], 30.0, 1e-4), "between two known values: a straight line");
        Check(Near(v[4], 34.0, 1e-4) && Near(v[7], 16.0, 1e-4), "around the end of the ring");
        Check(v[0] == 10.0f && v[3] == 40.0f, "known values stay");

        float one[4] = { 0.0f, 5.0f, 0.0f, 0.0f };
        uint8_t oneKnown[4] = { 0, 1, 0, 0 };
        BleakStorm::FillUnknown(one, oneKnown, 4, -99.0f);
        Check(one[0] == 5.0f && one[2] == 5.0f && one[3] == 5.0f, "one known value: all take it");

        float none[3] = { 1.0f, 2.0f, 3.0f };
        uint8_t noneKnown[3] = { 0, 0, 0 };
        BleakStorm::FillUnknown(none, noneKnown, 3, -7.0f);
        Check(none[0] == -7.0f && none[1] == -7.0f && none[2] == -7.0f, "none known: the fallback");
    }

    void TestBuild() {
        // A map corner far from 0, so that the origin really matters.
        double origin[3] = { 16000.0, -16500.0, 120.0 };
        double eye[3] = { 3.0, -2.0, 4.0 };
        BleakStorm::Circle c = { 16010.0, -16490.0, 250.0 };
        uint32_t n = BleakStorm::Segments(c.r);
        std::vector<uint8_t> visible(n, 0);
        std::vector<float> ground(n + 1);

        for (uint32_t i = 0; i <= n; i++) {
            ground[i] = 100.0f + 20.0f * static_cast<float>(sin(i * 0.3));
        }

        // Two runs: segments 0..9 and the last three (which end at column n, column 0 again).
        for (uint32_t i = 0; i < 10; i++) {
            visible[i] = 1;
        }

        visible[n - 3] = visible[n - 2] = visible[n - 1] = 1;
        std::vector<BleakStorm::Vertex> vertices(BleakStorm::kMaxVertices);
        std::vector<uint16_t> indices(BleakStorm::kMaxIndices);
        uint32_t indexCount = 0;
        uint32_t count = BleakStorm::Build(c, BleakStorm::Kind_Wall, n, visible.data(), ground.data(), origin, eye, vertices.data(), BleakStorm::kMaxVertices, indices.data(), BleakStorm::kMaxIndices, indexCount);
        Check(count == 2 * (11 + 4), "two runs: 11 and 4 columns, two vertices each");
        Check(indexCount == 6 * 13, "six indices per visible segment");

        bool onCircle = true, heights = true, shape = true, normals = true, inRange = true;
        double eyeZ = origin[2] + eye[2];

        for (uint32_t v = 0; v < count; v++) {
            const BleakStorm::Vertex& p = vertices[v];
            double wx = p.pos[0] + origin[0], wy = p.pos[1] + origin[1], wz = p.pos[2] + origin[2];
            onCircle = onCircle && Near(BleakStorm::EdgeDistance(c, wx, wy), 0.0, 2e-3);
            double nx = (wx - c.x) / c.r, ny = (wy - c.y) / c.r;
            normals = normals && Near(p.normal[0], nx, 1e-4) && Near(p.normal[1], ny, 1e-4) && p.normal[2] == 0.0f;
            // Bottom vertices are even, top ones odd.
            double g = wz - p.shape[0];
            double top = v & 1 ? wz : wz + p.shape[1];
            heights = heights && (v & 1 ? Near(wz - g, std::max(BleakStorm::kHeightYards, eyeZ + BleakStorm::kAboveCameraYards - g), 1e-3) : Near(wz - g, -BleakStorm::kSinkYards, 1e-3));
            shape = shape && (v & 1 ? p.shape[1] == 0.0f : Near(top - wz, BleakStorm::kSinkYards + std::max(BleakStorm::kHeightYards, eyeZ + BleakStorm::kAboveCameraYards - g), 1e-3));
        }

        for (uint32_t i = 0; i < indexCount; i++) {
            inRange = inRange && indices[i] < count;
        }

        Check(onCircle, "every vertex is on the circle");
        Check(normals, "normals point out of the circle");
        Check(heights, "from kSinkYards below the ground to kHeightYards above it");
        Check(shape, "the shape: yards above the ground, yards below the top");
        Check(inRange, "indices point at vertices");

        // Each segment's two triangles span its two columns: a bottom and a top of each.
        bool quads = true;

        for (uint32_t s = 0; s < indexCount / 6; s++) {
            const uint16_t* q = &indices[s * 6];
            quads = quads && q[0] % 2 == 0 && q[1] == q[0] + 1 && q[2] % 2 == 0 && q[2] != q[0] && q[4] == q[2] + 1 && q[3] == q[1] && q[5] == q[2];
        }

        Check(quads, "two triangles per segment over its two columns");

        // The ring: low, taller further from the camera.
        ground.assign(n + 1, 10.0f);
        std::fill(visible.begin(), visible.end(), 1);
        double ringEye[3] = { c.x - origin[0], c.y - origin[1], 12.0 - origin[2] };
        count = BleakStorm::Build(c, BleakStorm::Kind_Ring, n, visible.data(), ground.data(), origin, ringEye, vertices.data(), BleakStorm::kMaxVertices, indices.data(), BleakStorm::kMaxIndices, indexCount);
        Check(count == 2 * (n + 1) && indexCount == 6 * n, "a whole ring: one run");
        double ringTop = 10.0 + std::max(BleakStorm::kRingYards, c.r * BleakStorm::kRingPerYard);
        Check(Near(vertices[1].pos[2] + origin[2], ringTop, 1e-3) && Near(vertices[0].pos[2] + origin[2], 10.0 - BleakStorm::kRingSinkYards, 1e-3), "the ring's height");
        Check(vertices[2 * n].pos[0] == vertices[0].pos[0] && vertices[2 * n].pos[1] == vertices[0].pos[1], "the ring closes without a crack");

        // Too small buffers, nothing visible, nothing to draw.
        count = BleakStorm::Build(c, BleakStorm::Kind_Wall, n, visible.data(), ground.data(), origin, eye, vertices.data(), 10, indices.data(), BleakStorm::kMaxIndices, indexCount);
        Check(count == 0 && indexCount == 0, "too few vertices: nothing");
        count = BleakStorm::Build(c, BleakStorm::Kind_Wall, n, visible.data(), ground.data(), origin, eye, vertices.data(), BleakStorm::kMaxVertices, indices.data(), 12, indexCount);
        Check(count == 0 && indexCount == 0, "too few indices: nothing");
        std::fill(visible.begin(), visible.end(), 0);
        count = BleakStorm::Build(c, BleakStorm::Kind_Wall, n, visible.data(), ground.data(), origin, eye, vertices.data(), BleakStorm::kMaxVertices, indices.data(), BleakStorm::kMaxIndices, indexCount);
        Check(count == 0 && indexCount == 0, "nothing visible: nothing");
        BleakStorm::Circle tiny = { c.x, c.y, 0.5 };
        std::fill(visible.begin(), visible.end(), 1);
        count = BleakStorm::Build(tiny, BleakStorm::Kind_Wall, n, visible.data(), ground.data(), origin, eye, vertices.data(), BleakStorm::kMaxVertices, indices.data(), BleakStorm::kMaxIndices, indexCount);
        Check(count == 0 && indexCount == 0, "a closed circle: nothing");

        // The largest wall fits the buffers, and its indices fit 16 bits.
        BleakStorm::Circle big = { 0.0, 0.0, 20000.0 };
        uint32_t bigN = BleakStorm::Segments(big.r);
        std::vector<uint8_t> all(bigN, 1);
        std::vector<float> flat(bigN + 1, 0.0f);
        double zero[3] = { 0.0, 0.0, 0.0 };
        count = BleakStorm::Build(big, BleakStorm::Kind_Wall, bigN, all.data(), flat.data(), zero, zero, vertices.data(), BleakStorm::kMaxVertices, indices.data(), BleakStorm::kMaxIndices, indexCount);
        Check(count == BleakStorm::kMaxVertices && indexCount == BleakStorm::kMaxIndices && count <= 0x10000, "the largest wall fits");

        Check(BleakStorm::Fraction(2.75) == 0.75 && BleakStorm::Fraction(-0.25) == 0.75, "fractions wrap below 0");
    }

    void TestNoise() {
        const uint8_t* t = BleakFxStormNoise::Levels();
        const uint32_t n = BleakFxStormNoise::kSize;
        Check(BleakFxStormNoise::LevelSize(BleakFxStormNoise::kLevels - 1) == 1, "the last level is 1x1");
        Check(BleakFxStormNoise::LevelOffset(1) == n * n * 4 && BleakFxStormNoise::LevelOffset(2) == n * n * 5, "level offsets");
        Check(BleakFxStormNoise::Levels() == t, "made once");

        // Tileable: the step across the edge is no larger than steps inside (value noise is smooth).
        int worstInside[4] = { 0, 0, 0, 0 };
        int worstEdge[4] = { 0, 0, 0, 0 };
        int low[4] = { 255, 255, 255, 255 };
        int high[4] = { 0, 0, 0, 0 };

        for (uint32_t y = 0; y < n; y++) {
            for (uint32_t x = 0; x < n; x++) {
                for (uint32_t c = 0; c < 4; c++) {
                    int v = t[(y * n + x) * 4 + c];
                    int right = t[(y * n + (x + 1) % n) * 4 + c];
                    int down = t[(((y + 1) % n) * n + x) * 4 + c];
                    int step = std::max(abs(v - right), abs(v - down));
                    int& worst = (x == n - 1 || y == n - 1) ? worstEdge[c] : worstInside[c];
                    worst = std::max(worst, step);
                    low[c] = std::min(low[c], v);
                    high[c] = std::max(high[c], v);
                }
            }
        }

        for (uint32_t c = 0; c < 4; c++) {
            Check(worstEdge[c] <= worstInside[c] + 2, "the noise tiles without a seam");
            Check(low[c] <= 5 && high[c] >= 250, "each channel spans the whole range");
        }

        // Mip levels are the average of the level above (alpha: the ridges; any channel will do).
        const uint8_t* l1 = t + BleakFxStormNoise::LevelOffset(1);
        int expect = (t[0 * 4 + 2] + t[1 * 4 + 2] + t[n * 4 + 2] + t[(n + 1) * 4 + 2] + 2) / 4;
        Check(l1[2] == expect, "level 1 is the box filter of level 0");

        // The same bytes on every machine: a checksum of level 0.
        uint32_t sum = 2166136261u;

        for (uint32_t i = 0; i < n * n * 4; i++) {
            sum = (sum ^ t[i]) * 16777619u;
        }

        printf("noise checksum %08x\n", sum);
    }
}

namespace {
    // A copy of the client's minimap quads in its own float arithmetic (WoW/Source/Ui/MinimapFrame.cpp:
    // MinimapWorldToTileCoords, MinimapUpdatePosition, MINIMAPTILE::UpdateQuad and BuildQuad), to hold the storm
    // overlay against. Rect has CRect's fields in CRect's order.
    struct Rect {
        float minY;
        float minX;
        float maxY;
        float maxX;
    };

    const Rect kStockQuads[4] = {
        { 0.0f, 0.0f, 0.5f, 0.5f },
        { 0.5f, 0.0f, 1.0f, 0.5f },
        { 0.5f, 0.5f, 1.0f, 1.0f },
        { 0.0f, 0.5f, 0.5f, 1.0f },
    };
    const uint32_t kStockZoomTiles[6] = { 14, 12, 10, 8, 6, 4 };
    const float kStockViewRadius[6] = { 233.3f, 200.0f, 166.7f, 133.3f, 100.0f, 66.7f };

    struct StockQuad {
        bool built;
        Rect rect;
        float vertices[4][2];
        float mask[4][2];
    };

    struct Stock {
        int32_t baseTile[2];
        float centerX;
        float centerY;
        float scale;
        StockQuad quads[4];
    };

    void StockTileCoords(float px, float py, int32_t tile[2]) {
        float y = (17066.666f - py) * 0.0018750001f;
        float x = 0.0018750001f * (17066.666f - px);

        if (y < 0.0f) {
            y = y - 1.0f;
        }

        tile[0] = static_cast<int32_t>(y);
        tile[1] = x >= 0.0f ? static_cast<int32_t>(x) : static_cast<int32_t>(x - 1.0f);
    }

    void StockBuildQuad(StockQuad& q, const Rect& rect, float scale, const Rect& bounds, float layoutScale, float width) {
        float size = scale * 2.0f;
        float inv = 1.0f / size;
        q.mask[0][0] = (rect.minX - bounds.minX) * inv;
        q.mask[0][1] = (rect.maxY - bounds.minY) * inv;
        q.mask[1][0] = (rect.maxX - bounds.minX) * inv;
        q.mask[1][1] = (rect.maxY - bounds.minY) * inv;
        q.mask[2][0] = (rect.minX - bounds.minX) * inv;
        q.mask[2][1] = (rect.minY - bounds.minY) * inv;
        q.mask[3][0] = (rect.maxX - bounds.minX) * inv;
        q.mask[3][1] = (rect.minY - bounds.minY) * inv;
        float vertexInv = 1.0f / size;
        float extent = layoutScale * width;
        float left = (rect.minX - bounds.minX) * vertexInv * extent;
        float right = vertexInv * (rect.maxX - bounds.minX) * extent;
        float top = extent - vertexInv * (rect.maxY - bounds.minY) * extent;
        float bottom = extent - (rect.minY - bounds.minY) * vertexInv * extent;
        float corners[4][2] = { { left, top }, { right, top }, { left, bottom }, { right, bottom } };
        memcpy(q.vertices, corners, sizeof(corners));
        q.rect = rect;
    }

    void StockUpdateQuad(StockQuad& q, uint32_t index, float centerX, float centerY, float scale, float layoutScale, float width) {
        q.built = false;
        Rect bounds = { centerY - scale, centerX - scale, centerY + scale, centerX + scale };
        float minY = bounds.minY, minX = bounds.minX, maxY = bounds.maxY, maxX = bounds.maxX;
        const Rect& quad = kStockQuads[index];

        if (maxX >= quad.maxY) {
            maxX = quad.maxY;
        }

        if (quad.maxX <= maxY) {
            maxY = quad.maxX;
        }

        if (quad.minY >= minX) {
            minX = quad.minY;
        }

        if (quad.minX >= minY) {
            minY = quad.minX;
        }

        Rect rect = { minY, minX, maxY, maxX };

        if (quad.minX < maxY && quad.maxX > minY && maxX > quad.minY && quad.maxY > minX) {
            StockBuildQuad(q, rect, scale, bounds, layoutScale, width);
            q.built = true;
        }
    }

    // MinimapUpdatePosition outdoors, without the tile textures.
    Stock StockMinimap(float px, float py, uint32_t zoom, float layoutScale, float width) {
        Stock st = {};
        StockTileCoords(px + 266.66666f, py + 266.66666f, st.baseTile);
        float originX = 17066.666f - st.baseTile[1] * 533.33331f;
        float originY = 17066.666f - 533.33331f * st.baseTile[0];
        float inv = 1.0f / 1066.6666f;
        uint32_t halfTiles = kStockZoomTiles[zoom] >> 1;
        st.centerX = (originY - py) * inv;
        st.centerY = (originX - px) / 1066.6666f;
        st.scale = inv * (halfTiles * 33.333332f);

        for (uint32_t i = 0; i < 4; i++) {
            StockUpdateQuad(st.quads[i], i, st.centerX, st.centerY, st.scale, layoutScale, width);
        }

        return st;
    }

    BleakStorm::MinimapSpace SpaceOf(const Stock& st, double px, double py, double layoutScale, double width) {
        BleakStorm::MinimapSpace s = {};
        s.x = px;
        s.y = py;
        s.centerX = st.centerX;
        s.centerY = st.centerY;
        s.scale = st.scale;
        s.extent = static_cast<float>(layoutScale) * static_cast<float>(width);
        s.layoutScale = layoutScale;
        return s;
    }

    // A space for the overlay's geometry tests: the camera target at (x, y), outdoor zoom `zoom`, a minimap
    // `width` UI units wide at `layoutScale`.
    BleakStorm::MinimapSpace Space(double x, double y, uint32_t zoom, double layoutScale, double width) {
        return SpaceOf(StockMinimap(static_cast<float>(x), static_cast<float>(y), zoom, static_cast<float>(layoutScale), static_cast<float>(width)), x, y, layoutScale, width);
    }

    struct Mesh {
        std::vector<BleakStorm::MinimapVertex> vertices;
        std::vector<uint16_t> indices;
        BleakStorm::MinimapMesh mesh;

        Mesh() : vertices(BleakStorm::kMinimapMaxVertices), indices(BleakStorm::kMinimapMaxIndices) {
            mesh = { vertices.data(), BleakStorm::kMinimapMaxVertices, 0, indices.data(), BleakStorm::kMinimapMaxIndices, 0 };
        }
    };

    struct Layers {
        Mesh m[BleakStorm::Minimap_Layers];
        BleakStorm::MinimapMesh meshes[BleakStorm::Minimap_Layers];

        bool Build(const BleakStorm::MinimapSpace& space, const BleakStorm::Circle& cur, bool shade, const BleakStorm::Circle* next, double pixel = 0.0) {
            bool any = false;

            for (uint32_t i = 0; i < BleakStorm::Minimap_Layers; i++) {
                any = BleakStorm::BuildMinimap(space, static_cast<BleakStorm::MinimapLayer>(i), cur, shade, next, pixel, m[i].mesh) || any;
                meshes[i] = m[i].mesh;
            }

            return any;
        }
    };

    bool InTriangle(double px, double py, const float* a, const float* b, const float* c) {
        double d1 = (px - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (py - b[1]);
        double d2 = (px - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (py - c[1]);
        double d3 = (px - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (py - a[1]);
        bool negative = d1 < 0.0 || d2 < 0.0 || d3 < 0.0;
        bool positive = d1 > 0.0 || d2 > 0.0 || d3 > 0.0;
        return !(negative && positive);
    }

    bool Covered(const BleakStorm::MinimapMesh& mesh, double vx, double vy) {
        for (uint32_t i = 0; i + 2 < mesh.indexCount; i += 3) {
            if (InTriangle(vx, vy, mesh.vertices[mesh.indices[i]].pos, mesh.vertices[mesh.indices[i + 1]].pos, mesh.vertices[mesh.indices[i + 2]].pos)) {
                return true;
            }
        }

        return false;
    }

    // A vertex's distance from the circle's centre in yards (vertex space is the world turned and scaled).
    double YardsFrom(const BleakStorm::MinimapSpace& space, const BleakStorm::MinimapVertex& v, double cx, double cy) {
        double ox, oy;
        BleakStorm::MinimapToVertex(space, cx, cy, ox, oy);
        double perYard = space.extent / (2.0 * space.scale * BleakStorm::kMinimapTileYards);
        return sqrt((v.pos[0] - ox) * (v.pos[0] - ox) + (v.pos[1] - oy) * (v.pos[1] - oy)) / perYard;
    }

    // The hatch's texture coordinates at a world point (the first vertex of a band around it, of inner radius 0).
    void HatchAt(const BleakStorm::MinimapSpace& space, double x, double y, float out[2]) {
        Mesh probe;
        BleakStorm::BandShape hard = { 0.0, false, false, false };
        BleakStorm::MinimapBand(space, x, y, 0.0, 1.0, 0.0, 1.0, 1, hard, probe.mesh);
        out[0] = probe.vertices[0].tex[0];
        out[1] = probe.vertices[0].tex[1];
    }

    bool IndicesInRange(const BleakStorm::MinimapMesh& mesh) {
        bool ok = mesh.indexCount % 3 == 0 && mesh.vertexCount <= mesh.vertexCapacity && mesh.indexCount <= mesh.indexCapacity;

        for (uint32_t i = 0; i < mesh.indexCount; i++) {
            ok = ok && mesh.indices[i] < mesh.vertexCount;
        }

        return ok;
    }

    void TestMinimapSpace() {
        const double positions[][2] = { { -267.0, -267.0 }, { 100.5, 820.25 }, { 16000.0, -16500.0 }, { -5000.3, 3000.7 }, { 532.9, -1.2 } };
        bool vertices = true, masks = true, tiles = true, indexes = true, centre = true, edges = true, ratio = true;
        int quads = 0;

        for (const double* p : positions) {
            for (uint32_t zoom = 0; zoom < 6; zoom++) {
                for (double layoutScale : { 1.0, 1.37, 0.64 }) {
                    double width = 140.0;
                    Stock st = StockMinimap(static_cast<float>(p[0]), static_cast<float>(p[1]), zoom, static_cast<float>(layoutScale), static_cast<float>(width));
                    BleakStorm::MinimapSpace s = SpaceOf(st, p[0], p[1], layoutScale, width);
                    Check(BleakStorm::MinimapSpaceValid(s), "a stock minimap gives a valid space");
                    const double Q = BleakStorm::kMinimapTileYards;

                    // Every corner of every quad the client builds: our vertex and mask for that world point are
                    // BuildQuad's own.
                    for (uint32_t i = 0; i < 4; i++) {
                        const StockQuad& q = st.quads[i];

                        if (!q.built) {
                            continue;
                        }

                        quads++;
                        const float corners[4][2] = { { q.rect.minX, q.rect.maxY }, { q.rect.maxX, q.rect.maxY }, { q.rect.minX, q.rect.minY }, { q.rect.maxX, q.rect.minY } };

                        for (uint32_t k = 0; k < 4; k++) {
                            // Tile space back to the world: X grows east (-y), Y south (-x).
                            double wy = p[1] - (corners[k][0] - st.centerX) * Q;
                            double wx = p[0] - (corners[k][1] - st.centerY) * Q;
                            double vx, vy, u, v;
                            BleakStorm::MinimapToVertex(s, wx, wy, vx, vy);
                            BleakStorm::MinimapToMask(s, wx, wy, u, v);
                            vertices = vertices && Near(vx, q.vertices[k][0], 2e-3) && Near(vy, q.vertices[k][1], 2e-3);
                            masks = masks && Near(u, q.mask[k][0], 1e-5) && Near(v, q.mask[k][1], 1e-5);
                        }
                    }

                    // The camera target is the quads' centre; the mask's middle.
                    double vx, vy, u, v;
                    BleakStorm::MinimapToVertex(s, p[0], p[1], vx, vy);
                    BleakStorm::MinimapToMask(s, p[0], p[1], u, v);
                    centre = centre && Near(vx, s.extent * 0.5, 1e-6) && Near(vy, s.extent * 0.5, 1e-6) && Near(u, 0.5, 1e-9) && Near(v, 0.5, 1e-9);

                    // One view radius north is the top edge's middle, west the left edge's, south the bottom's.
                    double r = BleakStorm::MinimapViewYards(s);
                    BleakStorm::MinimapToVertex(s, p[0] + r, p[1], vx, vy);
                    BleakStorm::MinimapToMask(s, p[0] + r, p[1], u, v);
                    edges = edges && Near(vx, s.extent * 0.5, 1e-6) && Near(vy, s.extent, 1e-6) && Near(u, 0.5, 1e-9) && Near(v, 0.0, 1e-9);
                    BleakStorm::MinimapToVertex(s, p[0], p[1] + r, vx, vy);
                    edges = edges && Near(vx, 0.0, 1e-6) && Near(vy, s.extent * 0.5, 1e-6);
                    BleakStorm::MinimapToVertex(s, p[0] - r, p[1], vx, vy);
                    edges = edges && Near(vx, s.extent * 0.5, 1e-6) && Near(vy, 0.0, 1e-6);

                    // The tile a point is in, as the client's own (17066.666 - pos) * 0.001875 has it; and the
                    // absolute tile space MinimapUpdatePosition measures from its origin.
                    for (double off : { -401.0, -12.5, 7.25, 333.0 }) {
                        double wx = p[0] + off;
                        double wy = p[1] - 0.6 * off;
                        double tx, ty;
                        BleakStorm::MinimapToTile(s, wx, wy, tx, ty);
                        double originY = 17066.666 - 533.33331 * st.baseTile[0];
                        double originX = 17066.666 - 533.33331 * st.baseTile[1];
                        tiles = tiles && Near(tx, (originY - wy) / 1066.6666, 2e-5) && Near(ty, (originX - wx) / 1066.6666, 2e-5);
                        int32_t tile[2];
                        StockTileCoords(static_cast<float>(wx), static_cast<float>(wy), tile);
                        double fx = st.baseTile[0] + 2.0 * tx;
                        double fy = st.baseTile[1] + 2.0 * ty;

                        if (fabs(fx - floor(fx + 0.5)) > 1e-3 && fabs(fy - floor(fy + 0.5)) > 1e-3) {
                            indexes = indexes && tile[0] == static_cast<int32_t>(floor(fx)) && tile[1] == static_cast<int32_t>(floor(fy));
                        }

                        // Vertex and mask agree everywhere: u = x / extent, v = 1 - y / extent.
                        BleakStorm::MinimapToVertex(s, wx, wy, vx, vy);
                        BleakStorm::MinimapToMask(s, wx, wy, u, v);
                        masks = masks && Near(u, vx / s.extent, 1e-9) && Near(v, 1.0 - vy / s.extent, 1e-9);
                    }

                    // The view radius is the zoom table's (Royale's RM.Geometry tables, MinimapFrame.cpp:194-197).
                    ratio = ratio && Near(BleakStorm::MinimapViewYards(s), kStockViewRadius[zoom], 0.05) && Near(BleakStorm::MinimapYardsPerUnit(s) * width * 0.5, kStockViewRadius[zoom], 0.05);
                }
            }
        }

        Check(quads > 100, "the stock quads were built");
        Check(vertices, "MinimapToVertex is BuildQuad's vertex for each quad corner");
        Check(masks, "MinimapToMask is BuildQuad's m_maskCoords");
        Check(tiles, "MinimapToTile is MinimapUpdatePosition's tile space");
        Check(indexes, "and lands in MinimapWorldToTileCoords's tile");
        Check(centre, "the camera target is the centre of the quads");
        Check(edges, "a view radius north is the top edge's middle, west the left, south the bottom");
        Check(ratio, "the view radius is the outdoor zoom table's");

        // The rotating minimap turns the view around the frame's centre by -facing (CGMinimapFrame::Render,
        // C44Matrix::Rotation about +z: counter-clockwise). The vertices stay the same; whatever lies ahead of the
        // player then points up.
        bool ahead = true;
        BleakStorm::MinimapSpace s = Space(-267.0, -267.0, 3, 1.0, 140.0);

        for (int k = 0; k < 12; k++) {
            double facing = k * 0.55 - 3.0;
            double vx, vy;
            BleakStorm::MinimapToVertex(s, s.x + 50.0 * cos(facing), s.y + 50.0 * sin(facing), vx, vy);
            double rx = vx - s.extent * 0.5, ry = vy - s.extent * 0.5;
            double c = cos(-facing), sn = sin(-facing);
            double ux = rx * c - ry * sn, uy = rx * sn + ry * c;
            ahead = ahead && Near(ux, 0.0, 1e-6) && uy > 0.0;
        }

        Check(ahead, "with the minimap rotating, the facing points up");

        BleakStorm::MinimapSpace bad = s;
        bad.scale = 0.0;
        Check(!BleakStorm::MinimapSpaceValid(bad), "a space of scale 0 is refused");
        bad = s;
        bad.extent = std::numeric_limits<double>::quiet_NaN();
        Check(!BleakStorm::MinimapSpaceValid(bad), "a NaN extent is refused");
    }

    void TestMinimapArcs() {
        double start;
        Check(Near(BleakStorm::ArcWithin(0.0, 0.0, 50.0, 0.0, 0.0, 60.0, start), 2.0 * kPi, 1e-12), "a circle around the view: all of it");
        Check(BleakStorm::ArcWithin(0.0, 0.0, 80.0, 0.0, 0.0, 60.0, start) == 0.0, "a circle beyond the view all round: none");
        Check(BleakStorm::ArcWithin(0.0, 0.0, 50.0, 500.0, 0.0, 60.0, start) == 0.0, "far away: none");
        Check(BleakStorm::ArcWithin(0.0, 0.0, 0.0, 1.0, 0.0, 60.0, start) == 0.0, "radius 0: none");
        bool ends = true;

        for (int k = 0; k < 10; k++) {
            double r = 30.0 + 90.0 * k, a = 0.7 * k - 2.0, d = r + 25.0 - 5.0 * k;
            double px = 10.0 + d * cos(a), py = -20.0 + d * sin(a);
            double span = BleakStorm::ArcWithin(10.0, -20.0, r, px, py, 60.0, start);
            ends = ends && span > 0.0 && span < 2.0 * kPi;

            for (double t : { start, start + span }) {
                double qx = 10.0 + r * cos(t), qy = -20.0 + r * sin(t);
                ends = ends && Near(sqrt((qx - px) * (qx - px) + (qy - py) * (qy - py)), 60.0, 1e-6);
            }

            double mid = start + span * 0.5;
            ends = ends && Near(cos(mid), cos(a), 1e-9) && Near(sin(mid), sin(a), 1e-9);
        }

        Check(ends, "the arc's ends are `reach` from the view, its middle towards it");

        Check(Near(BleakStorm::DiscAngles(0.0, 0.0, 30.0, 0.0, 60.0, start), 2.0 * kPi, 1e-12), "the centre in view: every angle");
        double span = BleakStorm::DiscAngles(0.0, 0.0, 200.0, 100.0, 60.0, start);
        double d = sqrt(200.0 * 200.0 + 100.0 * 100.0);
        Check(Near(span, 2.0 * asin(60.0 / d), 1e-12), "the disc's angles");
        bool tangent = true;

        for (double t : { start, start + span }) {
            // The distance from the view's centre to the ray at angle t is the reach.
            tangent = tangent && Near(fabs(200.0 * sin(t) - 100.0 * cos(t)), 60.0, 1e-9);
        }

        Check(tangent, "its sides touch the disc");

        bool close = true, growing = true;
        uint32_t previous = 0;

        for (double r = 0.5; r < 4000.0; r *= 1.07) {
            uint32_t n = BleakStorm::ArcSegments(r, 2.0 * kPi);
            close = close && (n == BleakStorm::kMinimapMaxSegments || r * (1.0 - cos(kPi / n)) <= BleakStorm::kMinimapChordUnits + 1e-12);
            growing = growing && n >= previous;
            previous = n;
        }

        Check(close, "circles within a tenth of a unit of the true circle");
        Check(growing, "more segments for larger circles");
        Check(BleakStorm::ArcSegments(100.0, 0.0) == 0 && BleakStorm::ArcSegments(0.0, 1.0) == 0, "no arc: no segments");
        Check(BleakStorm::ArcSegments(1e-3, 0.1) == 1, "a tiny circle: one");
        Check(BleakStorm::DashCount(1.0) == BleakStorm::kMinimapMinDashes, "small circles get the fewest dashes");
        double big = 900.0;
        uint32_t n = BleakStorm::DashCount(big);
        Check(Near(2.0 * kPi * big / n, BleakStorm::kMinimapDashUnits + BleakStorm::kMinimapGapUnits, 0.05), "dashes keep their length on the screen");
    }

    void TestMinimapStorm() {
        // The island's first circles seen from a minimap 140 units wide, at every zoom and UI scale.
        bool covered = true, clean = true, ranges = true, keyline = true, widths = true, dashes = true, nextOn = true, fits = true;
        int sampled = 0, outside = 0;

        for (uint32_t zoom = 0; zoom < 6; zoom += 1) {
            for (double layoutScale : { 1.0, 0.64, 1.5 }) {
                for (int place = 0; place < 7; place++) {
                    BleakStorm::Circle cur = { -267.0, -267.0, 860.0 - 120.0 * place };
                    BleakStorm::Circle next = { -200.0, -300.0, cur.r * 0.6 };
                    // Inside near the edge, on it, outside near it, far outside, at the centre.
                    const double offsets[7] = { -40.0, 0.0, 30.0, 150.0, -cur.r, -90.0, 600.0 };
                    double a = 0.9 * place + 0.3;
                    double px = cur.x + (cur.r + offsets[place]) * cos(a);
                    double py = cur.y + (cur.r + offsets[place]) * sin(a);
                    BleakStorm::MinimapSpace s = Space(px, py, zoom, layoutScale, 140.0);
                    Layers layers;
                    layers.Build(s, cur, true, &next);
                    double unitYards = BleakStorm::MinimapYardsPerUnit(s);

                    for (uint32_t i = 0; i < BleakStorm::Minimap_Layers; i++) {
                        ranges = ranges && IndicesInRange(layers.meshes[i]);
                    }

                    // Sample the frame's square turned any way (its circumscribed disc): every point well outside
                    // the circle is shaded, none well inside.
                    double half = BleakStorm::MinimapViewYards(s) * sqrt(2.0);

                    for (int gy = -12; gy <= 12; gy++) {
                        for (int gx = -12; gx <= 12; gx++) {
                            double wx = px + half * gx / 12.0, wy = py + half * gy / 12.0;

                            if (gx * gx + gy * gy > 144) {
                                continue;
                            }

                            double edge = BleakStorm::EdgeDistance(cur, wx, wy);
                            double vx, vy;
                            BleakStorm::MinimapToVertex(s, wx, wy, vx, vy);
                            sampled++;

                            if (edge > 0.25 * unitYards) {
                                outside++;
                                covered = covered && Covered(layers.meshes[BleakStorm::Minimap_Shade], vx, vy);
                            } else if (edge < -0.25 * unitYards) {
                                clean = clean && !Covered(layers.meshes[BleakStorm::Minimap_Shade], vx, vy);
                            }
                        }
                    }

                    // No shade vertex inside the circle; the edge and its keyline at their widths in UI units.
                    const BleakStorm::MinimapMesh& sh = layers.meshes[BleakStorm::Minimap_Shade];

                    for (uint32_t v = 0; v < sh.vertexCount && sh.vertexCount != 4; v++) {
                        clean = clean && YardsFrom(s, sh.vertices[v], cur.x, cur.y) >= cur.r * (1.0 - 1e-6) - 1e-3;
                    }

                    const BleakStorm::MinimapMesh& edge = layers.meshes[BleakStorm::Minimap_Edge];
                    const BleakStorm::MinimapMesh& line = layers.meshes[BleakStorm::Minimap_EdgeOutline];
                    bool inView = BleakStorm::ArcWithin(cur.x, cur.y, cur.r, px, py, BleakStorm::MinimapViewYards(s), a) > 0.0;
                    keyline = keyline && (!inView || (edge.indexCount && line.indexCount && edge.vertexCount == line.vertexCount));

                    for (uint32_t v = 0; v < edge.vertexCount; v++) {
                        double r = YardsFrom(s, edge.vertices[v], cur.x, cur.y);
                        double expect = cur.r + (v & 1 ? 1.0 : -1.0) * BleakStorm::kMinimapEdgeUnits * unitYards;
                        widths = widths && Near(r, expect, 2e-3 * unitYards + 1e-4 * cur.r);
                        double o = YardsFrom(s, line.vertices[v], cur.x, cur.y);
                        double outer = cur.r + (v & 1 ? 1.0 : -1.0) * (BleakStorm::kMinimapEdgeUnits + BleakStorm::kMinimapOutlineUnits) * unitYards;
                        widths = widths && Near(o, outer, 2e-3 * unitYards + 1e-4 * cur.r);
                    }

                    // The next circle's dashes lie on it, at their width.
                    const BleakStorm::MinimapMesh& nx = layers.meshes[BleakStorm::Minimap_Next];

                    for (uint32_t v = 0; v < nx.vertexCount; v++) {
                        double r = YardsFrom(s, nx.vertices[v], next.x, next.y);
                        dashes = dashes && Near(r, next.r + (v & 1 ? 1.0 : -1.0) * BleakStorm::kMinimapNextUnits * unitYards, 2e-3 * unitYards + 1e-4 * next.r);
                    }

                    bool nextInView = BleakStorm::ArcWithin(next.x, next.y, next.r, px, py, BleakStorm::MinimapViewYards(s), a) > 0.0;
                    nextOn = nextOn && (!nextInView || (nx.indexCount && layers.meshes[BleakStorm::Minimap_NextOutline].indexCount));

                    for (uint32_t i = 0; i < BleakStorm::Minimap_Layers; i++) {
                        fits = fits && layers.meshes[i].vertexCount < BleakStorm::kMinimapMaxVertices;
                    }
                }
            }
        }

        Check(sampled > 10000 && outside > 2000, "the samples reach the storm");
        Check(covered, "every point of the view outside the circle is shaded");
        Check(clean, "no shade inside the circle");
        Check(ranges, "indices point at vertices, whole triangles");
        Check(keyline, "an edge in view has its keyline");
        Check(widths, "edge and keyline at their widths in UI units");
        Check(dashes, "the dashes lie on the next circle");
        Check(nextOn, "a next circle in view is drawn");
        Check(fits, "every layer fits its buffer");

        // A dash is kMinimapDashUnits long on the screen, its keyline kMinimapOutlineUnits more at each end.
        BleakStorm::MinimapSpace s = Space(0.0, 0.0, 5, 1.0, 140.0);
        BleakStorm::Circle cur = { 0.0, 0.0, 400.0 };
        BleakStorm::Circle next = { 10.0, 5.0, 40.0 };
        Layers layers;
        Check(layers.Build(s, cur, true, &next), "something to draw");
        const BleakStorm::MinimapMesh& nx = layers.meshes[BleakStorm::Minimap_Next];
        const BleakStorm::MinimapMesh& no = layers.meshes[BleakStorm::Minimap_NextOutline];
        double perUnit = s.layoutScale;
        uint32_t n = BleakStorm::DashCount(40.0 / BleakStorm::MinimapYardsPerUnit(s));
        uint32_t columns = (nx.vertexCount / 2) / n;
        Check(nx.vertexCount == no.vertexCount && nx.vertexCount % (2 * n) == 0 && columns >= 2, "a whole next circle in view: every dash, each with its keyline");
        const float* a0 = nx.vertices[1].pos;
        const float* a1 = nx.vertices[2 * (columns - 1) + 1].pos;
        const float* b0 = no.vertices[1].pos;
        const float* b1 = no.vertices[2 * (columns - 1) + 1].pos;
        double dashLength = sqrt((a1[0] - a0[0]) * (a1[0] - a0[0]) + (a1[1] - a0[1]) * (a1[1] - a0[1])) / perUnit;
        double lineLength = sqrt((b1[0] - b0[0]) * (b1[0] - b0[0]) + (b1[1] - b0[1]) * (b1[1] - b0[1])) / perUnit;
        Check(dashLength > 4.0 && dashLength < 6.5, "a dash about kMinimapDashUnits long");
        Check(lineLength > dashLength + 1.5, "its keyline longer at both ends");
        Check(layers.meshes[BleakStorm::Minimap_Shade].indexCount == 0, "deep inside: no shade");

        // Inside a circle far from its edge, nothing; the lobby gets no shade; a closed storm shades everything.
        BleakStorm::Circle huge = { 0.0, 0.0, 1500.0 };
        Check(!layers.Build(s, huge, true, nullptr), "far inside the circle: nothing to draw");
        BleakStorm::Circle away = { 3000.0, 0.0, 300.0 };
        Check(layers.Build(s, away, true, nullptr) && layers.meshes[BleakStorm::Minimap_Shade].vertexCount == 4 && layers.meshes[BleakStorm::Minimap_Edge].indexCount == 0, "far outside: the whole view is shaded");
        Check(!layers.Build(s, away, false, nullptr), "the lobby, far outside: nothing");
        BleakStorm::Circle lobby = { 0.0, 200.0, 150.0 };
        Check(layers.Build(s, lobby, false, nullptr) && layers.meshes[BleakStorm::Minimap_Shade].indexCount == 0 && layers.meshes[BleakStorm::Minimap_Edge].indexCount, "the lobby: the edge, no shade");
        BleakStorm::Circle closed = { 0.0, 0.0, 0.0 };
        Check(layers.Build(s, closed, true, nullptr) && layers.meshes[BleakStorm::Minimap_Shade].vertexCount == 4 && layers.meshes[BleakStorm::Minimap_Edge].indexCount == 0, "a closed storm: all shade, no edge");
        BleakStorm::Circle same = cur;
        layers.Build(s, cur, true, &same);
        Check(layers.meshes[BleakStorm::Minimap_Next].indexCount == 0, "the storm on the next circle: no dashes");

        // A whole ring closes on its first column exactly.
        BleakStorm::Circle ring = { 20.0, -10.0, 30.0 };
        layers.Build(s, ring, true, nullptr);
        const BleakStorm::MinimapMesh& e = layers.meshes[BleakStorm::Minimap_Edge];
        Check(e.vertexCount >= 4 && memcmp(&e.vertices[0], &e.vertices[e.vertexCount - 2], 2 * sizeof(BleakStorm::MinimapVertex)) == 0, "a whole edge closes without a crack");

        // The hatch is fixed to the ground: one world point keeps its texture coordinates, give or take whole
        // repeats, as the minimap moves; one repeat is kMinimapHatchUnits on the screen.
        BleakStorm::MinimapSpace s2 = Space(37.3, -81.9, 5, 1.0, 140.0);
        float t1[2], t2[2], t3[2];
        HatchAt(s, 12.5, -7.75, t1);
        HatchAt(s2, 12.5, -7.75, t2);
        double du = t2[0] - t1[0], dv = t2[1] - t1[1];
        Check(Near(du, floor(du + 0.5), 1e-3) && Near(dv, floor(dv + 0.5), 1e-3) && fabs(du) + fabs(dv) > 0.5, "the hatch stays on the ground");
        double unit = BleakStorm::MinimapYardsPerUnit(s);
        HatchAt(s, 12.5, -7.75 - BleakStorm::kMinimapHatchUnits * unit, t3);
        Check(Near(t3[0] - t1[0], 1.0, 1e-4) && Near(t3[1], t1[1], 1e-6), "the hatch repeats every kMinimapHatchUnits");

        // Soft lines: with a pixel of 0.7 vertex units, the edge has four rows a column, fading from 0 to 1 across
        // one pixel centred on each side; dashes fade at their ends too; a band thinner than a pixel peaks lower.
        const double pixel = 0.7;
        layers.Build(s, ring, true, &next, pixel);
        const BleakStorm::MinimapMesh& soft = layers.meshes[BleakStorm::Minimap_Edge];
        double perYardSoft = s.extent / (2.0 * s.scale * BleakStorm::kMinimapTileYards);
        double halfEdge = BleakStorm::kMinimapEdgeUnits * s.layoutScale / perYardSoft;
        double f = pixel / perYardSoft;
        bool rows = soft.vertexCount % 4 == 0 && soft.vertexCount > 8;

        for (uint32_t v = 0; v + 3 < soft.vertexCount; v += 4) {
            const BleakStorm::MinimapVertex* q = &soft.vertices[v];
            rows = rows && q[0].fade == 0.0f && q[1].fade == 1.0f && q[2].fade == 1.0f && q[3].fade == 0.0f;
            rows = rows && Near(YardsFrom(s, q[0], ring.x, ring.y), ring.r - halfEdge - 0.5 * f, 1e-3);
            rows = rows && Near(YardsFrom(s, q[1], ring.x, ring.y), ring.r - halfEdge + 0.5 * f, 1e-3);
            rows = rows && Near(YardsFrom(s, q[2], ring.x, ring.y), ring.r + halfEdge - 0.5 * f, 1e-3);
            rows = rows && Near(YardsFrom(s, q[3], ring.x, ring.y), ring.r + halfEdge + 0.5 * f, 1e-3);
        }

        Check(rows, "soft sides: a pixel's fade centred on each side of the edge");
        Check(soft.indexCount == (soft.vertexCount / 4 - 1) * 18, "three strips a segment");
        const BleakStorm::MinimapMesh& softDash = layers.meshes[BleakStorm::Minimap_Next];
        const BleakStorm::MinimapMesh& softLine = layers.meshes[BleakStorm::Minimap_NextOutline];
        bool capped = softDash.vertexCount > 0 && softDash.vertexCount == softLine.vertexCount;
        uint32_t perDash = 4 * (columns + 2);
        capped = capped && softDash.vertexCount % perDash == 0;

        for (uint32_t d = 0; capped && d < softDash.vertexCount; d += perDash) {
            for (uint32_t r = 0; r < 4; r++) {
                capped = capped && softDash.vertices[d + r].fade == 0.0f && softDash.vertices[d + perDash - 4 + r].fade == 0.0f;
            }

            capped = capped && softDash.vertices[d + 5].fade == 1.0f;
        }

        Check(capped, "soft dashes: their ends fade too, and keylines match them");
        BleakStorm::MinimapMesh thin = layers.m[0].mesh;
        thin.vertexCount = thin.indexCount = 0;
        BleakStorm::BandShape soft3 = { 3.0, false, false, false };
        Check(BleakStorm::MinimapBand(s, 0.0, 0.0, 10.0, 11.0, 0.0, 1.0, 4, soft3, thin) && Near(thin.vertices[1].fade, 1.0 / 3.0, 1e-6) && thin.vertices[1].pos[0] == thin.vertices[2].pos[0], "a band thinner than its fade peaks lower, in its middle");
        BleakStorm::MinimapMesh full = layers.m[0].mesh;
        full.vertexCapacity = 7;
        full.vertexCount = full.indexCount = 0;
        Check(!BleakStorm::MinimapBand(s, 0.0, 0.0, 10.0, 11.0, 0.0, 1.0, 4, soft3, full) && full.vertexCount == 0, "a band that does not fit: nothing");
        Check(!layers.Build(s, ring, true, &next, std::numeric_limits<double>::quiet_NaN()), "a NaN pixel: nothing");

        // The storm's front: from the edge kMinimapGlowUnits into the storm, fading out; not in the lobby.
        layers.Build(s, ring, true, nullptr, pixel);
        const BleakStorm::MinimapMesh& glow = layers.meshes[BleakStorm::Minimap_Glow];
        double glowYards = BleakStorm::kMinimapGlowUnits * BleakStorm::MinimapYardsPerUnit(s);
        bool front = glow.vertexCount >= 4 && glow.vertexCount % 2 == 0;

        for (uint32_t v = 0; v + 1 < glow.vertexCount; v += 2) {
            front = front && glow.vertices[v].fade == 1.0f && glow.vertices[v + 1].fade == 0.0f;
            front = front && Near(YardsFrom(s, glow.vertices[v], ring.x, ring.y), ring.r, 1e-3) && Near(YardsFrom(s, glow.vertices[v + 1], ring.x, ring.y), ring.r + glowYards, 1e-3);
        }

        Check(front, "the storm's front fades out from the edge into the storm");
        layers.Build(s, ring, false, nullptr, pixel);
        Check(layers.meshes[BleakStorm::Minimap_Glow].indexCount == 0 && layers.meshes[BleakStorm::Minimap_Edge].indexCount > 0, "the lobby: no front either");
        layers.Build(s, closed, true, nullptr, pixel);
        Check(layers.meshes[BleakStorm::Minimap_Glow].indexCount == 0, "a closed storm: no front");
    }

    void TestHatch() {
        const uint8_t* t = BleakStorm::HatchLevels();
        const uint32_t n = BleakStorm::kHatchSize;
        Check(BleakStorm::HatchLevels() == t, "the hatch is made once");
        Check(BleakStorm::HatchLevelSize(BleakStorm::kHatchLevels - 1) == 1 && BleakStorm::HatchLevelOffset(1) == n * n * 4, "the hatch's levels");
        uint32_t sum = 0, white = 0, seam = 0, inside = 0;

        for (uint32_t y = 0; y < n; y++) {
            for (uint32_t x = 0; x < n; x++) {
                const uint8_t* p = t + (y * n + x) * 4;
                sum += p[3];
                white += p[0] == 255 && p[1] == 255 && p[2] == 255;
                // Tileable: across the edge the alpha steps no more than inside.
                int right = t[(y * n + (x + 1) % n) * 4 + 3];
                int down = t[(((y + 1) % n) * n + x) * 4 + 3];
                uint32_t step = static_cast<uint32_t>(std::max(abs(p[3] - right), abs(p[3] - down)));
                uint32_t& worst = (x == n - 1 || y == n - 1) ? seam : inside;
                worst = std::max(worst, step);
            }
        }

        double coverage = sum / (255.0 * n * n);
        Check(Near(coverage, 0.25, 0.01), "a quarter of the hatch is covered");
        Check(white == n * n, "the hatch is white; its lines are in alpha");
        Check(seam <= inside, "the hatch tiles without a seam");
        const uint8_t* last = t + BleakStorm::HatchLevelOffset(BleakStorm::kHatchLevels - 1);
        Check(Near(last[3], 64.0, 2.0), "its smallest level is a quarter grey");
        const uint8_t* l1 = t + BleakStorm::HatchLevelOffset(1);
        int expect = (t[3] + t[7] + t[n * 4 + 3] + t[(n + 1) * 4 + 3] + 2) / 4;
        Check(l1[3] == expect, "each level is the box filter of the one above");
    }
}

int main(int argc, char** argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: test_storm <dir with circle_cases.csv>\n");
        return 2;
    }

    TestCircleCases(argv[1]);
    TestSanitize();
    TestEdgeAndSegments();
    TestCulling();
    TestHorizon();
    TestEye();
    TestFillUnknown();
    TestBuild();
    TestNoise();
    TestMinimapSpace();
    TestMinimapArcs();
    TestMinimapStorm();
    TestHatch();
    printf("%d checks, %d failed\n", s_checks, s_failed);
    printf(s_failed ? "FAIL\n" : "PASS\n");
    return s_failed ? 1 : 0;
}
