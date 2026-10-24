"""Procedural height field, evaluated on the global half-unit lattice (see coords.py).

h(x, y) = base + sum(noise layers), then every feature in spec order:

- hill:     h += height * falloff(distance / radius)   (smooth (1-u^2)^2, cone 1-u, dome sqrt(1-u^2))
- flatten:  blend h toward a target height inside a shape, fading out over `falloff` yards (plateaus, base pads);
            height null = the terrain height at the shape's centre before this feature; `offset` is added to the
            target (a mesa: height null, offset +25, mode raise)
- river:    carve to `bed` inside width/2, blend back to the terrain over `bank` yards
- ramp:     blend toward the straight line from `from` to `to` (z null = terrain height there before the ramp)
- border:   add `height` near the edge of the tile range (cliffs, or a sunken shore with a negative height): full
            within `inset` yards of the edge (+- `jitter` noise for a natural line), fading out over `width`
- clamp:    clamp to [min, max]

Heights are quantized to 1/64 yard (coords.quantize_height) so every shared edge vertex is bit-identical in the
client's float32 arithmetic.
"""

from __future__ import annotations

import math
from array import array

from . import coords
from .noise import Fbm
from .shapes import Polyline, _segment_distance


class _Feature:
    __slots__ = ("kind", "bbox", "data")

    def __init__(self, kind: str, bbox, data: dict):
        self.kind = kind
        self.bbox = bbox  # (min_x, max_x, min_y, max_y) or None = everywhere
        self.data = data


class HeightField:
    def __init__(self, spec):
        self.base = spec.base_height
        self.bounds = spec.world_bounds()
        self.seed = spec.seed
        self.noise = [Fbm((spec.seed * 31 + n["seed"] * 1009 + i * 7) & 0xFFFFFFFF, n["scale"], n["amplitude"],
                          n["octaves"], n["persistence"], n["lacunarity"]) for i, n in enumerate(spec.noise)]
        self.features: list[_Feature] = []
        for f in spec.features:
            self.features.append(self._compile(f))
        # Resolve "terrain height here" targets in order; each one only sees the features before it.
        for i, feat in enumerate(self.features):
            d = feat.data
            if feat.kind == "flatten":
                if d["height"] is None:
                    rx, ry = d["shape"].reference_point()
                    d["height"] = self._eval(rx, ry, i)
                d["height"] += d["offset"]
            elif feat.kind == "ramp":
                if d["z0"] is None:
                    d["z0"] = self._eval(d["x0"], d["y0"], i)
                if d["z1"] is None:
                    d["z1"] = self._eval(d["x1"], d["y1"], i)

    def _compile(self, f: dict) -> _Feature:
        kind = f["type"]
        if kind == "hill":
            cx, cy = f["center"]
            r = f["radius"]
            return _Feature("hill", (cx - r, cx + r, cy - r, cy + r),
                            {"cx": cx, "cy": cy, "r": r, "h": f["height"], "shape": f["shape"]})
        if kind == "flatten":
            x0, x1, y0, y1 = f["shape"].bbox()
            fo = f["falloff"]
            return _Feature("flatten", (x0 - fo, x1 + fo, y0 - fo, y1 + fo),
                            {"shape": f["shape"], "height": f["height"], "offset": f.get("offset", 0.0),
                             "falloff": fo, "mode": f["mode"]})
        if kind == "river":
            line = Polyline(list(f["path"]), f["width"])
            x0, x1, y0, y1 = line.bbox()
            b = f["bank"]
            return _Feature("river", (x0 - b, x1 + b, y0 - b, y1 + b),
                            {"line": line, "half": f["width"] * 0.5, "bank": b, "bed": f["bed"]})
        if kind == "ramp":
            (ax, ay, az), (bx, by, bz) = f["from"], f["to"]
            reach = f["width"] * 0.5 + f["falloff"]
            bbox = (min(ax, bx) - reach, max(ax, bx) + reach, min(ay, by) - reach, max(ay, by) + reach)
            return _Feature("ramp", bbox,
                            {"x0": ax, "y0": ay, "z0": az, "x1": bx, "y1": by, "z1": bz, "half": f["width"] * 0.5,
                             "falloff": f["falloff"]})
        if kind == "border":
            noise = None
            if f["jitter"] > 0.0:
                noise = Fbm((self.seed * 53 + f["seed"] * 389 + 11) & 0xFFFFFFFF, f["jitter_scale"], f["jitter"], 3)
            return _Feature("border", None, {"inset": f["inset"], "width": f["width"], "height": f["height"],
                                             "noise": noise})
        if kind == "clamp":
            return _Feature("clamp", None, {"min": f["min"], "max": f["max"]})
        raise ValueError(kind)

    @staticmethod
    def _blend_weight(d: float, falloff: float) -> float:
        if d <= 0.0:
            return 1.0
        if falloff <= 0.0 or d >= falloff:
            return 0.0
        return 1.0 - coords.smoothstep(d / falloff)

    def _eval(self, x: float, y: float, upto: int | None = None) -> float:
        h = self.base
        for n in self.noise:
            h += n(x, y)
        feats = self.features if upto is None else self.features[:upto]
        for feat in feats:
            bb = feat.bbox
            if bb is not None and (x < bb[0] or x > bb[1] or y < bb[2] or y > bb[3]):
                continue
            d = feat.data
            kind = feat.kind
            if kind == "hill":
                dx = x - d["cx"]
                dy = y - d["cy"]
                u2 = (dx * dx + dy * dy) / (d["r"] * d["r"])
                if u2 >= 1.0:
                    continue
                if d["shape"] == "smooth":
                    k = (1.0 - u2) * (1.0 - u2)
                elif d["shape"] == "cone":
                    k = 1.0 - math.sqrt(u2)
                else:
                    k = math.sqrt(1.0 - u2)
                h += d["h"] * k
            elif kind == "flatten":
                w = self._blend_weight(d["shape"].distance(x, y), d["falloff"])
                if w <= 0.0:
                    continue
                t = d["height"]
                if d["mode"] == "raise" and h >= t:
                    continue
                if d["mode"] == "lower" and h <= t:
                    continue
                h += (t - h) * w
            elif kind == "river":
                dist = d["line"].center_distance(x, y)
                half = d["half"]
                target = h if h < d["bed"] else d["bed"]
                if dist <= half:
                    h = target
                elif d["bank"] > 0.0 and dist < half + d["bank"]:
                    s = coords.smoothstep((dist - half) / d["bank"])
                    h = target + (h - target) * s
            elif kind == "ramp":
                dist, t = _segment_distance(x, y, d["x0"], d["y0"], d["x1"], d["y1"])
                w = self._blend_weight(dist - d["half"], d["falloff"])
                if w <= 0.0:
                    continue
                z = d["z0"] + (d["z1"] - d["z0"]) * t
                h += (z - h) * w
            elif kind == "border":
                bx0, bx1, by0, by1 = self.bounds
                inside = min(x - bx0, bx1 - x, y - by0, by1 - y)
                inset = d["inset"]
                if d["noise"] is not None:
                    inset += d["noise"](x, y)
                t = (inside - inset) / d["width"]
                if t < 1.0:
                    h += d["height"] * (1.0 - coords.smoothstep(t))
            else:
                lo = d["min"]
                hi = d["max"]
                h = lo if h < lo else hi if h > hi else h
        return h

    def raw(self, x: float, y: float) -> float:
        return self._eval(x, y)

    def lattice(self, row: int, col: int) -> float:
        h = coords.quantize_height(self._eval(coords.lattice_x(row), coords.lattice_y(col)))
        return coords.clamp(h, -coords.HEIGHT_LIMIT, coords.HEIGHT_LIMIT)


class LatticeGrid:
    """Quantized heights for the spec's tile range plus a one-point border (for normals and slopes)."""

    def __init__(self, spec, field: HeightField):
        self.row0 = spec.ty0 * coords.LATTICE_PER_TILE - 1
        self.col0 = spec.tx0 * coords.LATTICE_PER_TILE - 1
        self.rows = (spec.ty1 - spec.ty0 + 1) * coords.LATTICE_PER_TILE + 3
        self.cols = (spec.tx1 - spec.tx0 + 1) * coords.LATTICE_PER_TILE + 3
        self.h = array("d", bytes(8 * self.rows * self.cols))
        i = 0
        for r in range(self.rows):
            x = coords.lattice_x(self.row0 + r)
            for c in range(self.cols):
                v = coords.quantize_height(field.raw(x, coords.lattice_y(self.col0 + c)))
                self.h[i] = coords.clamp(v, -coords.HEIGHT_LIMIT, coords.HEIGHT_LIMIT)
                i += 1

    def get(self, row: int, col: int) -> float:
        return self.h[(row - self.row0) * self.cols + (col - self.col0)]

    def gradient(self, row: int, col: int) -> tuple[float, float]:
        """(dh/dX, dh/dY) at a lattice point, central differences over one half unit."""
        cols = self.cols
        i = (row - self.row0) * cols + (col - self.col0)
        h = self.h
        inv = 1.0 / (2.0 * coords.HALF_UNIT)
        # Row - 1 lies one half unit further north (+X); column - 1 further west (+Y).
        return ((h[i - cols] - h[i + cols]) * inv, (h[i - 1] - h[i + 1]) * inv)

    def normal(self, row: int, col: int) -> tuple[float, float, float]:
        gx, gy = self.gradient(row, col)
        inv = 1.0 / math.sqrt(gx * gx + gy * gy + 1.0)
        return (-gx * inv, -gy * inv, inv)

    def ground_height(self, x: float, y: float) -> float:
        """Height of the triangulated surface at a world point, as the client and server see it.

        Each 4.17-yard quad is split into four triangles around its inner vertex (CMapChunk::CreateIndices).
        """
        u, v = coords.world_to_lattice(x, y)
        qr = int(math.floor(u / 2.0))
        qc = int(math.floor(v / 2.0))
        fu = u / 2.0 - qr
        fv = v / 2.0 - qc
        r0 = qr * 2
        c0 = qc * 2
        if not (self.row0 <= r0 and r0 + 2 < self.row0 + self.rows and self.col0 <= c0
                and c0 + 2 < self.col0 + self.cols):
            raise ValueError(f"point ({x:.2f}, {y:.2f}) is outside the map's tiles")
        h_tl = self.get(r0, c0)
        h_tr = self.get(r0, c0 + 2)
        h_bl = self.get(r0 + 2, c0)
        h_br = self.get(r0 + 2, c0 + 2)
        h_c = self.get(r0 + 1, c0 + 1)
        # (fu, fv) in [0,1)^2, fu along rows, fv along columns; centre at (0.5, 0.5).
        if fu <= fv and fu + fv <= 1.0:  # north triangle: tl, tr, centre
            a, b, pa, pb = h_tl, h_tr, (0.0, 0.0), (0.0, 1.0)
        elif fu >= fv and fu + fv >= 1.0:  # south: bl, br
            a, b, pa, pb = h_bl, h_br, (1.0, 0.0), (1.0, 1.0)
        elif fu > fv:  # west: tl, bl
            a, b, pa, pb = h_tl, h_bl, (0.0, 0.0), (1.0, 0.0)
        else:  # east: tr, br
            a, b, pa, pb = h_tr, h_br, (0.0, 1.0), (1.0, 1.0)
        # Barycentric interpolation over (centre, pa, pb).
        cu, cv = 0.5, 0.5
        det = (pa[0] - cu) * (pb[1] - cv) - (pb[0] - cu) * (pa[1] - cv)
        la = ((fu - cu) * (pb[1] - cv) - (pb[0] - cu) * (fv - cv)) / det
        lb = ((pa[0] - cu) * (fv - cv) - (fu - cu) * (pa[1] - cv)) / det
        return h_c + (a - h_c) * la + (b - h_c) * lb
