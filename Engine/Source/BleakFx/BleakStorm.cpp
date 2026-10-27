#include "Engine/Source/BleakFx/BleakStorm.h"
#include <cmath>

namespace {
    const double kPi = 3.14159265358979323846;

    bool Finite(double value) {
        return std::isfinite(value);
    }

    bool CircleValid(const BleakStorm::Circle& c) {
        return Finite(c.x) && Finite(c.y) && Finite(c.r) && fabs(c.x) <= BleakStorm::kMaxCoordinate && fabs(c.y) <= BleakStorm::kMaxCoordinate && c.r >= 0.0 && c.r <= BleakStorm::kMaxRadius;
    }

    bool MsValid(double ms) {
        return Finite(ms) && ms >= 0.0 && ms <= BleakStorm::kMaxShrinkMs;
    }

    // A clip-space point (row vector times viewProj).
    void Clip(const double m[16], double x, double y, double z, double out[4]) {
        for (uint32_t k = 0; k < 4; k++) {
            out[k] = x * m[k] + y * m[4 + k] + z * m[8 + k] + m[12 + k];
        }
    }
}

bool BleakStorm::Sanitize(State& state) {
    if (!CircleValid(state.cur) || !Finite(state.recvAt) || state.recvAt < 0.0 || !Finite(state.expiresAt)) {
        return false;
    }

    if (state.hasNext && !CircleValid(state.next)) {
        return false;
    }

    if (state.hasShrink && (!MsValid(state.shrinkStartMs) || !MsValid(state.shrinkEndMs))) {
        return false;
    }

    if (!state.hasNext) {
        state.next = state.cur;
        state.hasShrink = false;
    }

    // R.Circle: "m.nextR and e and e > 0".
    if (!state.hasShrink || state.shrinkEndMs <= 0.0) {
        state.hasShrink = false;
        state.shrinkStartMs = 0.0;
        state.shrinkEndMs = 0.0;
    }

    return true;
}

BleakStorm::Circle BleakStorm::CircleAt(const State& state, double now, bool* moving) {
    if (moving) {
        *moving = false;
    }

    if (state.hasNext && state.hasShrink && state.shrinkEndMs > 0.0) {
        double t = (now - state.recvAt) * 1000.0;
        double s = state.shrinkStartMs;
        double e = state.shrinkEndMs;

        if (t >= e) {
            return state.next;
        }

        if (t > s && e > s) {
            double k = (t - s) / (e - s);
            Circle c;
            c.x = state.cur.x + (state.next.x - state.cur.x) * k;
            c.y = state.cur.y + (state.next.y - state.cur.y) * k;
            c.r = state.cur.r + (state.next.r - state.cur.r) * k;

            if (moving) {
                *moving = true;
            }

            return c;
        }
    }

    return state.cur;
}

bool BleakStorm::Stale(const State& state, double now) {
    return !(now <= state.expiresAt);
}

double BleakStorm::EdgeDistance(const Circle& c, double x, double y) {
    double dx = x - c.x;
    double dy = y - c.y;
    return sqrt(dx * dx + dy * dy) - c.r;
}

uint32_t BleakStorm::Segments(double radius) {
    if (!(radius >= kMinRadius)) {
        return 0;
    }

    double n = ceil(2.0 * kPi * radius / kColumnYards);

    if (n < kMinSegments) {
        return kMinSegments;
    }

    return n > kMaxSegments ? kMaxSegments : static_cast<uint32_t>(n);
}

double BleakStorm::MaxChordError(double radius, uint32_t segments) {
    return segments ? radius * (1.0 - cos(kPi / segments)) : radius;
}

void BleakStorm::ColumnPosition(const Circle& c, uint32_t segments, uint32_t column, double& x, double& y) {
    // Column `segments` is column 0 exactly, so the ring closes without a crack.
    double angle = segments && column < segments ? 2.0 * kPi * column / segments : 0.0;
    x = c.x + c.r * cos(angle);
    y = c.y + c.r * sin(angle);
}

uint32_t BleakStorm::CullSegments(const Circle& c, uint32_t segments, const double origin[3], const double viewProj[16], double zLow, double zHigh, uint8_t* visible) {
    uint32_t count = 0;
    double clip[2][2][4];
    double x, y;
    ColumnPosition(c, segments, 0, x, y);
    Clip(viewProj, x - origin[0], y - origin[1], zLow - origin[2], clip[0][0]);
    Clip(viewProj, x - origin[0], y - origin[1], zHigh - origin[2], clip[0][1]);

    for (uint32_t i = 0; i < segments; i++) {
        uint32_t a = i & 1;
        uint32_t b = a ^ 1;
        ColumnPosition(c, segments, i + 1, x, y);
        Clip(viewProj, x - origin[0], y - origin[1], zLow - origin[2], clip[b][0]);
        Clip(viewProj, x - origin[0], y - origin[1], zHigh - origin[2], clip[b][1]);

        // The view: -w <= x <= w, -w <= y <= w, and in front of the camera (w > 0). The segment is dropped when
        // all four corners are beyond the same one of these planes; a plane is a half-space in clip space, so then
        // the whole segment is.
        bool out[5] = { true, true, true, true, true };

        for (uint32_t k = 0; k < 4; k++) {
            const double* p = clip[k < 2 ? a : b][k & 1];
            out[0] = out[0] && p[0] < -p[3];
            out[1] = out[1] && p[0] > p[3];
            out[2] = out[2] && p[1] < -p[3];
            out[3] = out[3] && p[1] > p[3];
            out[4] = out[4] && p[3] <= 1e-3;
        }

        bool shown = !(out[0] || out[1] || out[2] || out[3] || out[4]);
        visible[i] = shown ? 1 : 0;
        count += shown ? 1 : 0;
    }

    return count;
}

bool BleakStorm::HorizonPass(double farZ, double horizonFar) {
    return Finite(farZ) && Finite(horizonFar) && farZ - kHorizonOverlapYards > 0.0 && horizonFar > farZ;
}

void BleakStorm::FillUnknown(float* values, const uint8_t* known, uint32_t count, float fallback) {
    uint32_t first = count;

    for (uint32_t i = 0; i < count; i++) {
        if (known[i]) {
            first = i;
            break;
        }
    }

    if (first == count) {
        for (uint32_t i = 0; i < count; i++) {
            values[i] = fallback;
        }

        return;
    }

    // From each known value to the next one around the ring, the unknown ones between them on a straight line.
    uint32_t from = first;

    do {
        uint32_t to = (from + 1) % count;
        uint32_t gap = 1;

        while (!known[to]) {
            to = (to + 1) % count;
            gap++;
        }

        for (uint32_t step = 1; step < gap; step++) {
            float k = static_cast<float>(step) / static_cast<float>(gap);
            values[(from + step) % count] = values[from] + (values[to] - values[from]) * k;
        }

        from = to;
    } while (from != first);
}

uint32_t BleakStorm::Build(const Circle& c, Kind kind, uint32_t segments, const uint8_t* visible, const float* ground, const double origin[3], const double eye[3], Vertex* vertices, uint32_t vertexCapacity, uint16_t* indices, uint32_t indexCapacity, uint32_t& indexCount) {
    indexCount = 0;

    if (!segments || segments > kMaxSegments || !(c.r >= kMinRadius)) {
        return 0;
    }

    uint32_t vertexCount = 0;
    // The vertex of the current run's last column (a column is shared by the two segments it ends and starts).
    uint32_t last = 0;
    bool open = false;
    double eyeZ = origin[2] + eye[2];

    for (uint32_t i = 0; i < segments; i++) {
        if (!visible[i]) {
            open = false;
            continue;
        }

        if (vertexCount + (open ? 2 : 4) > vertexCapacity || indexCount + 6 > indexCapacity) {
            indexCount = 0;
            return 0;
        }

        for (uint32_t column = open ? i + 1 : i; column <= i + 1; column++) {
            double x, y;
            ColumnPosition(c, segments, column, x, y);
            double g = ground[column];
            double bottom, top;

            if (kind == Kind_Ring) {
                double dx = x - (origin[0] + eye[0]);
                double dy = y - (origin[1] + eye[1]);
                double height = sqrt(dx * dx + dy * dy) * kRingPerYard;
                bottom = g - kRingSinkYards;
                top = g + (height > kRingYards ? height : kRingYards);
            } else {
                bottom = g - kSinkYards;
                top = g + kHeightYards;
                top = top > eyeZ + kAboveCameraYards ? top : eyeZ + kAboveCameraYards;
            }

            double angle = column < segments ? 2.0 * kPi * column / segments : 0.0;
            float nx = static_cast<float>(cos(angle));
            float ny = static_cast<float>(sin(angle));
            float px = static_cast<float>(x - origin[0]);
            float py = static_cast<float>(y - origin[1]);
            Vertex& b = vertices[vertexCount];
            Vertex& t = vertices[vertexCount + 1];
            b.pos[0] = t.pos[0] = px;
            b.pos[1] = t.pos[1] = py;
            b.pos[2] = static_cast<float>(bottom - origin[2]);
            t.pos[2] = static_cast<float>(top - origin[2]);
            b.normal[0] = t.normal[0] = nx;
            b.normal[1] = t.normal[1] = ny;
            b.normal[2] = t.normal[2] = 0.0f;
            b.shape[0] = static_cast<float>(bottom - g);
            b.shape[1] = static_cast<float>(top - bottom);
            t.shape[0] = static_cast<float>(top - g);
            t.shape[1] = 0.0f;
            vertexCount += 2;
        }

        // Column i's bottom and top, then column i + 1's.
        uint32_t base = open ? last : vertexCount - 4;
        uint16_t b0 = static_cast<uint16_t>(base);
        uint16_t t0 = static_cast<uint16_t>(base + 1);
        uint16_t b1 = static_cast<uint16_t>(vertexCount - 2);
        uint16_t t1 = static_cast<uint16_t>(vertexCount - 1);
        uint16_t* out = indices + indexCount;
        out[0] = b0;
        out[1] = t0;
        out[2] = b1;
        out[3] = t0;
        out[4] = t1;
        out[5] = b1;
        indexCount += 6;
        last = vertexCount - 2;
        open = true;
    }

    if (!indexCount) {
        return 0;
    }

    return vertexCount;
}

void BleakStorm::EyeFromView(const float view[16], double eye[3]) {
    // eye * R + t = 0 with R the rotation rows a, b, c and t the row d: eye = -t * R^T (R is orthonormal).
    for (uint32_t i = 0; i < 3; i++) {
        eye[i] = -(static_cast<double>(view[12]) * view[i * 4] + static_cast<double>(view[13]) * view[i * 4 + 1] + static_cast<double>(view[14]) * view[i * 4 + 2]);
    }
}

double BleakStorm::Fraction(double value) {
    return value - floor(value);
}
