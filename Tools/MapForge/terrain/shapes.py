"""2D regions in world coordinates: circle, rect, polygon, polyline (a path with a width).

Every shape answers `distance(x, y)`: 0 inside, the distance to the region outside, and `inside_distance(x, y)`:
how far a point inside lies from the boundary (0 outside). Specs write a shape as a one-key object, e.g.
{"circle": {"center": [x, y], "radius": r}}.
"""

from __future__ import annotations

import math

from .spec_errors import SpecError


def _point(value, where: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise SpecError(f"{where}: expected [x, y]")
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        raise SpecError(f"{where}: expected numbers") from None


def _segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> tuple[float, float]:
    """Distance from p to segment ab, and the clamped parameter t along it."""
    dx = bx - ax
    dy = by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0.0:
        t = 0.0
    else:
        t = ((px - ax) * dx + (py - ay) * dy) / length2
        t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    qx = ax + dx * t - px
    qy = ay + dy * t - py
    return math.sqrt(qx * qx + qy * qy), t


class Shape:
    kind = ""

    def distance(self, x: float, y: float) -> float:
        raise NotImplementedError

    def bbox(self) -> tuple[float, float, float, float]:
        """(min_x, max_x, min_y, max_y)."""
        raise NotImplementedError

    def reference_point(self) -> tuple[float, float]:
        raise NotImplementedError

    def inside_distance(self, x: float, y: float) -> float:
        """Distance from a point inside to the boundary; 0 on or outside it."""
        raise NotImplementedError

    def contains(self, x: float, y: float) -> bool:
        return self.distance(x, y) <= 0.0


class Circle(Shape):
    kind = "circle"

    def __init__(self, center: tuple[float, float], radius: float):
        self.cx, self.cy = center
        self.radius = radius

    def distance(self, x: float, y: float) -> float:
        dx = x - self.cx
        dy = y - self.cy
        d = math.sqrt(dx * dx + dy * dy) - self.radius
        return d if d > 0.0 else 0.0

    def bbox(self):
        r = self.radius
        return (self.cx - r, self.cx + r, self.cy - r, self.cy + r)

    def inside_distance(self, x: float, y: float) -> float:
        dx = x - self.cx
        dy = y - self.cy
        d = self.radius - math.sqrt(dx * dx + dy * dy)
        return d if d > 0.0 else 0.0

    def reference_point(self):
        return (self.cx, self.cy)


class Rect(Shape):
    kind = "rect"

    def __init__(self, lo: tuple[float, float], hi: tuple[float, float]):
        self.x0, self.x1 = min(lo[0], hi[0]), max(lo[0], hi[0])
        self.y0, self.y1 = min(lo[1], hi[1]), max(lo[1], hi[1])

    def distance(self, x: float, y: float) -> float:
        dx = self.x0 - x if x < self.x0 else x - self.x1 if x > self.x1 else 0.0
        dy = self.y0 - y if y < self.y0 else y - self.y1 if y > self.y1 else 0.0
        if dx == 0.0:
            return dy
        if dy == 0.0:
            return dx
        return math.sqrt(dx * dx + dy * dy)

    def bbox(self):
        return (self.x0, self.x1, self.y0, self.y1)

    def inside_distance(self, x: float, y: float) -> float:
        d = min(x - self.x0, self.x1 - x, y - self.y0, self.y1 - y)
        return d if d > 0.0 else 0.0

    def reference_point(self):
        return ((self.x0 + self.x1) * 0.5, (self.y0 + self.y1) * 0.5)


class Polygon(Shape):
    kind = "polygon"

    def __init__(self, points: list[tuple[float, float]]):
        self.points = points
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        self._bbox = (min(xs), max(xs), min(ys), max(ys))

    def _inside(self, x: float, y: float) -> bool:
        inside = False
        pts = self.points
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if (yi > y) != (yj > y):
                xc = xi + (y - yi) * (xj - xi) / (yj - yi)
                if x < xc:
                    inside = not inside
            j = i
        return inside

    def distance(self, x: float, y: float) -> float:
        if self._inside(x, y):
            return 0.0
        return self._edge_distance(x, y)

    def bbox(self):
        return self._bbox

    def _edge_distance(self, x: float, y: float) -> float:
        pts = self.points
        best = math.inf
        for i in range(len(pts)):
            a = pts[i]
            b = pts[(i + 1) % len(pts)]
            d, _ = _segment_distance(x, y, a[0], a[1], b[0], b[1])
            if d < best:
                best = d
        return best

    def inside_distance(self, x: float, y: float) -> float:
        b = self._bbox
        if x < b[0] or x > b[1] or y < b[2] or y > b[3] or not self._inside(x, y):
            return 0.0
        return self._edge_distance(x, y)

    def reference_point(self):
        n = len(self.points)
        return (sum(p[0] for p in self.points) / n, sum(p[1] for p in self.points) / n)


class Polyline(Shape):
    """A path of segments with a full width (a chain of capsules)."""

    kind = "polyline"

    def __init__(self, points: list[tuple[float, float]], width: float):
        self.points = points
        self.half = width * 0.5
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        h = self.half
        self._bbox = (min(xs) - h, max(xs) + h, min(ys) - h, max(ys) + h)

    def center_distance(self, x: float, y: float) -> float:
        pts = self.points
        if len(pts) == 1:
            dx = x - pts[0][0]
            dy = y - pts[0][1]
            return math.sqrt(dx * dx + dy * dy)
        best = math.inf
        for i in range(len(pts) - 1):
            a = pts[i]
            b = pts[i + 1]
            d, _ = _segment_distance(x, y, a[0], a[1], b[0], b[1])
            if d < best:
                best = d
        return best

    def distance(self, x: float, y: float) -> float:
        d = self.center_distance(x, y) - self.half
        return d if d > 0.0 else 0.0

    def inside_distance(self, x: float, y: float) -> float:
        d = self.half - self.center_distance(x, y)
        return d if d > 0.0 else 0.0

    def bbox(self):
        return self._bbox

    def reference_point(self):
        return self.points[len(self.points) // 2]


def parse_shape(obj, where: str) -> Shape:
    if not isinstance(obj, dict) or len(obj) != 1:
        raise SpecError(f"{where}: a shape is one of {{'circle'|'rect'|'polygon'|'polyline': {{...}}}}")
    kind, body = next(iter(obj.items()))
    if not isinstance(body, dict):
        raise SpecError(f"{where}.{kind}: expected an object")
    allowed = {"circle": {"center", "radius"}, "rect": {"min", "max"}, "polygon": {"points"},
               "polyline": {"points", "width"}}
    if kind not in allowed:
        raise SpecError(f"{where}: unknown shape '{kind}' (use circle, rect, polygon or polyline)")
    extra = set(body) - allowed[kind]
    missing = allowed[kind] - set(body)
    if extra:
        raise SpecError(f"{where}.{kind}: unknown keys {sorted(extra)}")
    if missing:
        raise SpecError(f"{where}.{kind}: missing keys {sorted(missing)}")
    if kind == "circle":
        radius = float(body["radius"])
        if radius < 0.0:
            raise SpecError(f"{where}.circle.radius: must be >= 0")
        return Circle(_point(body["center"], f"{where}.circle.center"), radius)
    if kind == "rect":
        return Rect(_point(body["min"], f"{where}.rect.min"), _point(body["max"], f"{where}.rect.max"))
    points = body["points"]
    if not isinstance(points, list):
        raise SpecError(f"{where}.{kind}.points: expected a list")
    pts = [_point(p, f"{where}.{kind}.points[{i}]") for i, p in enumerate(points)]
    if kind == "polygon":
        if len(pts) < 3:
            raise SpecError(f"{where}.polygon.points: needs at least 3 points")
        return Polygon(pts)
    if len(pts) < 1:
        raise SpecError(f"{where}.polyline.points: needs at least 1 point")
    width = float(body["width"])
    if width < 0.0:
        raise SpecError(f"{where}.polyline.width: must be >= 0")
    return Polyline(pts, width)


class RiverPath:
    """A river's centre line from its source to its mouth: one polyline whose segments belong to reaches.

    Each reach holds its water at one level (`levels`, falling downstream); the river steps down where one reach
    meets the next (a waterfall). `nearest` finds the closest segment (the first one on a tie, so the upstream
    reach owns the joint), `level_at` the water level there, and `terrain_level` the level along the arc length
    with each step spread over `fall_run` yards, which the terrain carving follows.
    """

    def __init__(self, points: list[tuple[float, float]], seg_reach: list[int], levels: list[float], width: float,
                 fall_run: float):
        self.points = points
        self.seg_reach = seg_reach
        self.levels = levels
        self.half = width * 0.5
        self.fall_run = fall_run
        self.seg_len = []
        self.cum = [0.0]
        for i in range(len(points) - 1):
            dx = points[i + 1][0] - points[i][0]
            dy = points[i + 1][1] - points[i][1]
            length = math.sqrt(dx * dx + dy * dy)
            self.seg_len.append(length)
            self.cum.append(self.cum[-1] + length)
        # Arc position of each joint: the first point of reach j (j >= 1).
        self.joints = []
        for i in range(1, len(seg_reach)):
            if seg_reach[i] != seg_reach[i - 1]:
                self.joints.append((self.cum[i], seg_reach[i]))
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        self.bbox = (min(xs), max(xs), min(ys), max(ys))

    def nearest(self, x: float, y: float) -> tuple[float, int, float]:
        """(distance to the centre line, segment index, parameter t along it)."""
        pts = self.points
        best = math.inf
        best_i = 0
        best_t = 0.0
        for i in range(len(pts) - 1):
            a = pts[i]
            b = pts[i + 1]
            d, t = _segment_distance(x, y, a[0], a[1], b[0], b[1])
            if d < best:
                best = d
                best_i = i
                best_t = t
        return best, best_i, best_t

    def arc(self, seg: int, t: float) -> float:
        return self.cum[seg] + self.seg_len[seg] * t

    def level_at(self, x: float, y: float) -> float:
        return self.levels[self.seg_reach[self.nearest(x, y)[1]]]

    def terrain_level(self, s: float) -> float:
        level = self.levels[0]
        half_run = self.fall_run * 0.5
        for (sj, reach) in self.joints:
            lower = self.levels[reach]
            if half_run <= 0.0:
                if s >= sj:
                    level = lower
                    continue
                break
            if s >= sj + half_run:
                level = lower
                continue
            if s > sj - half_run:
                k = (s - (sj - half_run)) / self.fall_run
                k = k * k * (3.0 - 2.0 * k)
                level = level + (lower - level) * k
            break
        return level
