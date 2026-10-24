"""2D regions in world coordinates: circle, rect, polygon, polyline (a path with a width).

Every shape answers `distance(x, y)`: 0 inside, the distance to the region outside. Specs write a shape as a
one-key object, e.g. {"circle": {"center": [x, y], "radius": r}}.
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
        pts = self.points
        best = math.inf
        for i in range(len(pts)):
            a = pts[i]
            b = pts[(i + 1) % len(pts)]
            d, _ = _segment_distance(x, y, a[0], a[1], b[0], b[1])
            if d < best:
                best = d
        return best

    def bbox(self):
        return self._bbox

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
