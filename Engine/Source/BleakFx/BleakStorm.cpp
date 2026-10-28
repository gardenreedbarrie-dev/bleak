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

// ---------------------------------------------------------------------------------------------------- the minimap

namespace {
    const double kTwoPi = 2.0 * kPi;

    // Vertex units in a yard, at the space's zoom.
    double VertexPerYard(const BleakStorm::MinimapSpace& space) {
        return space.extent / (2.0 * space.scale * BleakStorm::kMinimapTileYards);
    }

    // The hatch's texture coordinates of a world point: one repeat per kMinimapHatchUnits, counted from a whole
    // number of repeats from the world's origin near the position (so the hatch stays where it is on the ground as
    // the minimap moves, and the numbers stay small), along the vertex space's axes (u east, v south).
    void HatchCoords(const BleakStorm::MinimapSpace& space, double x, double y, float tex[2]) {
        double period = BleakStorm::kMinimapHatchUnits * BleakStorm::MinimapYardsPerUnit(space);
        double anchorX = period * floor(space.x / period);
        double anchorY = period * floor(space.y / period);
        tex[0] = static_cast<float>((anchorY - y) / period);
        tex[1] = static_cast<float>((anchorX - x) / period);
    }

    void SetVertex(const BleakStorm::MinimapSpace& space, double x, double y, float fade, BleakStorm::MinimapVertex& out) {
        double vx, vy, u, v;
        BleakStorm::MinimapToVertex(space, x, y, vx, vy);
        BleakStorm::MinimapToMask(space, x, y, u, v);
        out.pos[0] = static_cast<float>(vx);
        out.pos[1] = static_cast<float>(vy);
        out.pos[2] = 0.0f;
        out.mask[0] = static_cast<float>(u);
        out.mask[1] = static_cast<float>(v);
        out.fade = fade;
        HatchCoords(space, x, y, out.tex);
    }

    void Clear(BleakStorm::MinimapMesh& mesh) {
        mesh.vertexCount = 0;
        mesh.indexCount = 0;
    }

    // Two triangles over the square of half side `half` yards around (x, y): the whole view is in the storm.
    bool Square(const BleakStorm::MinimapSpace& space, double x, double y, double half, BleakStorm::MinimapMesh& mesh) {
        if (mesh.vertexCount + 4 > mesh.vertexCapacity || mesh.indexCount + 6 > mesh.indexCapacity) {
            return false;
        }

        uint32_t base = mesh.vertexCount;
        SetVertex(space, x - half, y - half, 1.0f, mesh.vertices[base]);
        SetVertex(space, x - half, y + half, 1.0f, mesh.vertices[base + 1]);
        SetVertex(space, x + half, y - half, 1.0f, mesh.vertices[base + 2]);
        SetVertex(space, x + half, y + half, 1.0f, mesh.vertices[base + 3]);
        const uint16_t quad[6] = { 0, 1, 2, 1, 3, 2 };

        for (uint32_t i = 0; i < 6; i++) {
            mesh.indices[mesh.indexCount + i] = static_cast<uint16_t>(base + quad[i]);
        }

        mesh.vertexCount += 4;
        mesh.indexCount += 6;
        return true;
    }

    // The dashes of the next circle within reach of the view; `grow` UI units bigger all round for their keylines.
    // Dashes and keylines come out column for column alike: the same dashes, the same segments.
    bool Dashes(const BleakStorm::MinimapSpace& space, const BleakStorm::Circle& c, double growUnits, double reach, double feather, BleakStorm::MinimapMesh& mesh) {
        double perYard = VertexPerYard(space);
        double unitYards = space.layoutScale / perYard;
        double radiusUnits = c.r * perYard / space.layoutScale;
        uint32_t n = BleakStorm::DashCount(radiusUnits);
        double keyline = (BleakStorm::kMinimapNextUnits + BleakStorm::kMinimapOutlineUnits) * unitYards;
        double start;
        double span = n ? BleakStorm::ArcWithin(c.x, c.y, c.r, space.x, space.y, reach + keyline, start) : 0.0;

        if (span <= 0.0) {
            return false;
        }

        double step = kTwoPi / n;
        double dash = step * BleakStorm::kMinimapDashUnits / (BleakStorm::kMinimapDashUnits + BleakStorm::kMinimapGapUnits);
        double outline = BleakStorm::kMinimapOutlineUnits / radiusUnits;
        double grow = growUnits / radiusUnits;
        int64_t first = 0;
        int64_t last = static_cast<int64_t>(n) - 1;

        if (span < kTwoPi) {
            // Every dash whose keyline overlaps the arc.
            first = static_cast<int64_t>(floor((start - outline - dash) / step));
            last = static_cast<int64_t>(ceil((start + span + outline) / step));

            if (last - first + 1 >= static_cast<int64_t>(n)) {
                first = 0;
                last = static_cast<int64_t>(n) - 1;
            }
        }

        uint32_t segments = BleakStorm::ArcSegments(radiusUnits, dash + 2.0 * outline);
        segments = segments > BleakStorm::kMinimapDashSegments ? BleakStorm::kMinimapDashSegments : segments;
        double half = (BleakStorm::kMinimapNextUnits + growUnits) * unitYards;
        BleakStorm::BandShape shape = { feather, true, false, false };
        uint32_t built = 0;

        for (int64_t k = first; k <= last && built < BleakStorm::kMinimapMaxDashes; k++, built++) {
            double rIn = c.r - half;

            if (!BleakStorm::MinimapBand(space, c.x, c.y, rIn < 0.0 ? 0.0 : rIn, c.r + half, static_cast<double>(k) * step - grow, dash + 2.0 * grow, segments, shape, mesh)) {
                return false;
            }
        }

        return true;
    }
}

bool BleakStorm::MinimapSpaceValid(const MinimapSpace& space) {
    return Finite(space.x) && Finite(space.y) && Finite(space.centerX) && Finite(space.centerY) && Finite(space.scale) && Finite(space.extent) && Finite(space.layoutScale) && space.scale > 0.0 && space.extent > 0.0 && space.layoutScale > 0.0;
}

void BleakStorm::MinimapToTile(const MinimapSpace& space, double x, double y, double& tileX, double& tileY) {
    // centerX = (origin.y - position.y) / s_tileSize and centerY = (origin.x - position.x) / s_tileSize, so a point
    // is the center plus its offset from the position, with the same signs.
    tileX = space.centerX + (space.y - y) / kMinimapTileYards;
    tileY = space.centerY + (space.x - x) / kMinimapTileYards;
}

void BleakStorm::MinimapToVertex(const MinimapSpace& space, double x, double y, double& vx, double& vy) {
    double tileX, tileY;
    MinimapToTile(space, x, y, tileX, tileY);
    double inv = 1.0 / (space.scale * 2.0);
    double boundsMinX = space.centerX - space.scale;
    double boundsMinY = space.centerY - space.scale;
    // BuildQuad: left = (rect.minX - bounds.minX) * vertexInv * extent, top = extent - vertexInv * (rect.maxY -
    // bounds.minY) * extent.
    vx = (tileX - boundsMinX) * inv * space.extent;
    vy = space.extent - inv * (tileY - boundsMinY) * space.extent;
}

void BleakStorm::MinimapToMask(const MinimapSpace& space, double x, double y, double& u, double& v) {
    double tileX, tileY;
    MinimapToTile(space, x, y, tileX, tileY);
    double inv = 1.0 / (space.scale * 2.0);
    // BuildQuad: m_maskCoords = ((rect.x - bounds.minX) * inv, (rect.y - bounds.minY) * inv).
    u = (tileX - (space.centerX - space.scale)) * inv;
    v = (tileY - (space.centerY - space.scale)) * inv;
}

double BleakStorm::MinimapViewYards(const MinimapSpace& space) {
    return space.scale * kMinimapTileYards;
}

double BleakStorm::MinimapYardsPerUnit(const MinimapSpace& space) {
    return space.layoutScale / VertexPerYard(space);
}

double BleakStorm::ArcWithin(double cx, double cy, double r, double x, double y, double reach, double& start) {
    start = 0.0;

    if (!(r > 0.0) || !(reach > 0.0) || !Finite(r) || !Finite(reach)) {
        return 0.0;
    }

    double dx = x - cx;
    double dy = y - cy;
    double d = sqrt(dx * dx + dy * dy);

    if (!Finite(d)) {
        return 0.0;
    }

    if (d < 1e-9) {
        return r <= reach ? kTwoPi : 0.0;
    }

    // A point of the circle at angle a from the direction of (x, y) is sqrt(d^2 + r^2 - 2 d r cos a) away.
    double k = (d * d + r * r - reach * reach) / (2.0 * d * r);

    if (k <= -1.0) {
        return kTwoPi;
    }

    if (k >= 1.0) {
        return 0.0;
    }

    double half = acos(k);
    start = atan2(dy, dx) - half;
    return 2.0 * half;
}

double BleakStorm::DiscAngles(double cx, double cy, double x, double y, double reach, double& start) {
    start = 0.0;
    double dx = x - cx;
    double dy = y - cy;
    double d = sqrt(dx * dx + dy * dy);

    if (!(reach > 0.0) || !Finite(d) || !Finite(reach)) {
        return 0.0;
    }

    if (d <= reach) {
        return kTwoPi;
    }

    double half = asin(reach / d);
    start = atan2(dy, dx) - half;
    return 2.0 * half;
}

uint32_t BleakStorm::ArcSegments(double radiusUnits, double span) {
    if (!(span > 0.0) || !(radiusUnits > 0.0) || !Finite(radiusUnits) || !Finite(span)) {
        return 0;
    }

    // A segment of angle t is at most r (1 - cos(t / 2)) from the circle; at most a quarter turn each.
    double most = radiusUnits > kMinimapChordUnits ? 2.0 * acos(1.0 - kMinimapChordUnits / radiusUnits) : kPi;
    most = most < kPi * 0.5 ? most : kPi * 0.5;
    double n = ceil(span / most - 1e-9);

    if (n < 1.0) {
        return 1;
    }

    return n > kMinimapMaxSegments ? kMinimapMaxSegments : static_cast<uint32_t>(n);
}

uint32_t BleakStorm::DashCount(double radiusUnits) {
    if (!(radiusUnits > 0.0) || !Finite(radiusUnits)) {
        return 0;
    }

    double n = floor(kTwoPi * radiusUnits / (kMinimapDashUnits + kMinimapGapUnits) + 0.5);

    if (n < kMinimapMinDashes) {
        return kMinimapMinDashes;
    }

    // Far more than the screen can show; only those in view are built.
    return n > 1000000.0 ? 1000000 : static_cast<uint32_t>(n);
}

bool BleakStorm::MinimapBand(const MinimapSpace& space, double cx, double cy, double rIn, double rOut, double start, double span, uint32_t segments, const BandShape& shape, MinimapMesh& mesh) {
    if (!segments || !(span > 0.0) || !(rOut > rIn) || rIn < 0.0 || !Finite(start) || !Finite(span) || !(shape.feather >= 0.0)) {
        return false;
    }

    bool whole = span >= kTwoPi;
    span = whole ? kTwoPi : span;
    bool soft = shape.feather > 0.0 && !shape.fadeOut;
    bool ends = soft && shape.featherEnds && !whole;
    // Rows from the inside out: the soft sides fade from 0 to `peak` across `feather`, centred on rIn and rOut (a
    // band thinner than that peaks lower, at its middle).
    double radii[4];
    float fades[4];
    uint32_t rows = soft ? 4 : 2;
    double f = shape.feather;

    if (soft) {
        double width = rOut - rIn;
        float peak = width >= f ? 1.0f : static_cast<float>(width / f);
        double mid = 0.5 * (rIn + rOut);
        radii[0] = rIn - 0.5 * f;
        radii[1] = width >= f ? rIn + 0.5 * f : mid;
        radii[2] = width >= f ? rOut - 0.5 * f : mid;
        radii[3] = rOut + 0.5 * f;
        radii[0] = radii[0] < 0.0 ? 0.0 : radii[0];
        fades[0] = 0.0f;
        fades[1] = peak;
        fades[2] = peak;
        fades[3] = 0.0f;
    } else {
        radii[0] = rIn;
        radii[1] = rOut;
        fades[0] = 1.0f;
        fades[1] = shape.fadeOut ? 0.0f : 1.0f;
    }

    // Columns: the solid ones, and at soft ends one more at each end with nothing left of the alpha. A soft end
    // fades across `feather` at the band's middle radius, centred on the end.
    double endAngle = ends ? f / (0.5 * (rIn + rOut) > f ? 0.5 * (rIn + rOut) : f) : 0.0;
    double solidStart = start;
    double solidSpan = span;
    float endPeak = 1.0f;

    if (ends) {
        if (span > endAngle) {
            solidStart = start + 0.5 * endAngle;
            solidSpan = span - endAngle;
        } else {
            endPeak = static_cast<float>(span / endAngle);
            solidStart = start + 0.5 * span;
            solidSpan = 0.0;
        }
    }

    uint32_t columns = segments + 1 + (ends ? 2 : 0);
    uint32_t vertexCount = columns * rows;
    uint32_t indexCount = (columns - 1) * (rows - 1) * 6;

    if (mesh.vertexCount + vertexCount > mesh.vertexCapacity || mesh.indexCount + indexCount > mesh.indexCapacity || mesh.vertexCount + vertexCount > 0x10000) {
        return false;
    }

    // The outer side's corners out to rOut / cos(half a segment) when it must cover the circle of rOut.
    double outerScale = shape.outerCircumscribed ? 1.0 / cos(0.5 * span / segments) : 1.0;
    uint32_t base = mesh.vertexCount;

    for (uint32_t i = 0; i < columns; i++) {
        MinimapVertex* column = mesh.vertices + base + rows * i;

        if (whole && i == segments) {
            // The ring closes on its first column exactly, so no crack shows.
            for (uint32_t r = 0; r < rows; r++) {
                column[r] = mesh.vertices[base + r];
            }

            continue;
        }

        double angle;
        float scale = 1.0f;

        if (ends && i == 0) {
            angle = start - 0.5 * endAngle;
            scale = 0.0f;
        } else if (ends && i == columns - 1) {
            angle = start + span + 0.5 * endAngle;
            scale = 0.0f;
        } else {
            uint32_t j = ends ? i - 1 : i;
            angle = solidStart + solidSpan * j / segments;
            scale = endPeak;
        }

        double ca = cos(angle);
        double sa = sin(angle);

        for (uint32_t r = 0; r < rows; r++) {
            double radius = r == rows - 1 ? radii[r] * outerScale : radii[r];
            SetVertex(space, cx + radius * ca, cy + radius * sa, fades[r] * scale, column[r]);
        }
    }

    uint16_t* out = mesh.indices + mesh.indexCount;

    for (uint32_t i = 0; i + 1 < columns; i++) {
        for (uint32_t r = 0; r + 1 < rows; r++) {
            uint16_t in0 = static_cast<uint16_t>(base + rows * i + r);
            uint16_t out0 = static_cast<uint16_t>(in0 + 1);
            uint16_t in1 = static_cast<uint16_t>(in0 + rows);
            uint16_t out1 = static_cast<uint16_t>(in1 + 1);
            out[0] = in0;
            out[1] = out0;
            out[2] = in1;
            out[3] = out0;
            out[4] = out1;
            out[5] = in1;
            out += 6;
        }
    }

    mesh.vertexCount += vertexCount;
    mesh.indexCount += indexCount;
    return true;
}

bool BleakStorm::BuildMinimap(const MinimapSpace& space, MinimapLayer layer, const Circle& cur, bool shade, const Circle* next, double pixel, MinimapMesh& mesh) {
    Clear(mesh);

    if (!MinimapSpaceValid(space) || !Finite(cur.x) || !Finite(cur.y) || !Finite(cur.r) || !(pixel >= 0.0) || !Finite(pixel)) {
        return false;
    }

    double perYard = VertexPerYard(space);
    double unitYards = space.layoutScale / perYard;
    double reach = MinimapViewYards(space) * kMinimapReach;
    double feather = pixel / perYard;
    double dx = space.x - cur.x;
    double dy = space.y - cur.y;
    double d = sqrt(dx * dx + dy * dy);
    bool closed = !(cur.r >= kMinRadius);
    bool ok = false;

    if (layer == Minimap_Shade) {
        // Everything in view outside the circle; its inside side lies under the edge, so it can be hard.
        if (!shade) {
            return false;
        }

        if (closed || d - cur.r >= reach) {
            ok = Square(space, space.x, space.y, reach, mesh);
        } else if (d + reach > cur.r) {
            double start;
            double span = DiscAngles(cur.x, cur.y, space.x, space.y, reach, start);
            BandShape shape = { 0.0, false, true, false };
            ok = MinimapBand(space, cur.x, cur.y, cur.r, d + reach, start, span, ArcSegments(cur.r * perYard / space.layoutScale, span), shape, mesh);
        }
    } else if (layer == Minimap_Glow) {
        // The storm's front, from the edge outwards, where the circle is in view (with the shade only).
        if (!shade || closed) {
            return false;
        }

        double glow = kMinimapGlowUnits * unitYards;
        double start;
        double span = ArcWithin(cur.x, cur.y, cur.r, space.x, space.y, reach + glow, start);
        BandShape shape = { 0.0, false, false, true };
        uint32_t segments = ArcSegments((cur.r + glow) * perYard / space.layoutScale, span);
        ok = segments && MinimapBand(space, cur.x, cur.y, cur.r, cur.r + glow, start, span, segments, shape, mesh);
    } else if (layer == Minimap_EdgeOutline || layer == Minimap_Edge) {
        // The edge and its keyline, where the circle is in view, over the same arc in the same segments.
        if (closed) {
            return false;
        }

        double keyline = (kMinimapEdgeUnits + kMinimapOutlineUnits) * unitYards;
        double half = layer == Minimap_Edge ? kMinimapEdgeUnits * unitYards : keyline;
        double start;
        double span = ArcWithin(cur.x, cur.y, cur.r, space.x, space.y, reach + keyline, start);
        uint32_t segments = ArcSegments((cur.r + keyline) * perYard / space.layoutScale, span);
        BandShape shape = { feather, false, false, false };
        double rIn = cur.r - half;
        ok = segments && MinimapBand(space, cur.x, cur.y, rIn < 0.0 ? 0.0 : rIn, cur.r + half, start, span, segments, shape, mesh);
    } else if (layer == Minimap_NextOutline || layer == Minimap_Next) {
        // The next circle, dashed, unless the storm stands on it already.
        if (!next || !Finite(next->x) || !Finite(next->y) || !Finite(next->r) || !(next->r >= kMinRadius)) {
            return false;
        }

        double apart = sqrt((next->x - cur.x) * (next->x - cur.x) + (next->y - cur.y) * (next->y - cur.y));

        if (fabs(next->r - cur.r) <= unitYards && apart <= unitYards) {
            return false;
        }

        ok = Dashes(space, *next, layer == Minimap_NextOutline ? kMinimapOutlineUnits : 0.0, reach, feather, mesh);
    }

    if (!ok) {
        Clear(mesh);
    }

    return mesh.indexCount > 0;
}

namespace {
    // Every level of the hatch: 32 x 32 down to 1 x 1, four bytes a texel.
    static_assert(BleakStorm::kHatchSize == 32 && BleakStorm::kHatchLevels == 6, "the hatch's levels");
    const uint32_t kHatchBytes = 4 * (32 * 32 + 16 * 16 + 8 * 8 + 4 * 4 + 2 * 2 + 1 * 1);
    uint8_t s_hatch[kHatchBytes];
    bool s_hatchMade;

    // How much of the texel at (x, y) the stripe covers: (u + v) mod kHatchSize below a quarter of it, so lines run
    // from the bottom left to the top right with v down; 8 x 8 samples per texel.
    uint8_t HatchCoverage(uint32_t x, uint32_t y) {
        const uint32_t samples = 8;
        const double width = BleakStorm::kHatchSize * 0.25;
        uint32_t inside = 0;

        for (uint32_t sy = 0; sy < samples; sy++) {
            for (uint32_t sx = 0; sx < samples; sx++) {
                double s = x + (sx + 0.5) / samples + y + (sy + 0.5) / samples;
                double m = fmod(s, static_cast<double>(BleakStorm::kHatchSize));
                inside += m < width ? 1 : 0;
            }
        }

        return static_cast<uint8_t>((inside * 255 + samples * samples / 2) / (samples * samples));
    }
}

uint32_t BleakStorm::HatchLevelSize(uint32_t level) {
    uint32_t size = kHatchSize >> level;
    return size ? size : 1;
}

uint32_t BleakStorm::HatchLevelOffset(uint32_t level) {
    uint32_t offset = 0;

    for (uint32_t i = 0; i < level && i < kHatchLevels; i++) {
        offset += HatchLevelSize(i) * HatchLevelSize(i) * 4;
    }

    return offset;
}

const uint8_t* BleakStorm::HatchLevels() {
    if (s_hatchMade) {
        return s_hatch;
    }

    // White everywhere (so the edges of the lines blend to white, not black); the lines are in alpha.
    for (uint32_t y = 0; y < kHatchSize; y++) {
        for (uint32_t x = 0; x < kHatchSize; x++) {
            uint8_t* p = s_hatch + (y * kHatchSize + x) * 4;
            p[0] = p[1] = p[2] = 255;
            p[3] = HatchCoverage(x, y);
        }
    }

    // Each level the box filter of the one above.
    for (uint32_t level = 1; level < kHatchLevels; level++) {
        const uint8_t* above = s_hatch + HatchLevelOffset(level - 1);
        uint8_t* here = s_hatch + HatchLevelOffset(level);
        uint32_t size = HatchLevelSize(level);
        uint32_t aboveSize = HatchLevelSize(level - 1);

        for (uint32_t y = 0; y < size; y++) {
            for (uint32_t x = 0; x < size; x++) {
                for (uint32_t c = 0; c < 4; c++) {
                    uint32_t sum = above[((2 * y) * aboveSize + 2 * x) * 4 + c] + above[((2 * y) * aboveSize + 2 * x + 1) * 4 + c] + above[((2 * y + 1) * aboveSize + 2 * x) * 4 + c] + above[((2 * y + 1) * aboveSize + 2 * x + 1) * 4 + c];
                    here[(y * size + x) * 4 + c] = static_cast<uint8_t>((sum + 2) / 4);
                }
            }
        }
    }

    s_hatchMade = true;
    return s_hatch;
}
