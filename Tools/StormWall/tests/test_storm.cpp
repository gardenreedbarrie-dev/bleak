// Tests of the storm wall's maths (Engine/Source/BleakFx/BleakStorm.cpp) and noise (BleakFxStormNoise.cpp);
// run_tests.sh builds and runs them:
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
    printf("%d checks, %d failed\n", s_checks, s_failed);
    printf(s_failed ? "FAIL\n" : "PASS\n");
    return s_failed ? 1 : 0;
}
