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
- mountains: a range along the edge of the tile range (see Mountains): a steep cliff at its foot, then layered
            ridges with noise-shaped peaks, saddles and terraced ledges up to the edge
- lake:     (spec `lakes`) a basin under the water level inside the shape (low ground on the shelf is raised
            toward the shore line, so the shore meets it), the shore blended to just above it outside, islands
            raised out of it
- river_reaches: (spec `rivers`) a channel under each reach's water level, stepping down at the waterfalls, the
            banks blended to just above the water; where the ground is lower than the channel, the bed and banks
            are built up (an embanked channel), except inside lakes
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


class Mountains:
    """A mountain range along the whole edge of the tile range.

    For a point, d is its distance in from the tile edge, measured to a rectangle with rounded corners
    (`corner_radius`) and moved by the `jitter` noise, so the foot of the range wanders. Points with d >= width are
    the valley. Going out from the foot (t = width - d yards into the range, u = t / width from 0 at the foot to 1 at
    the edge):

    - cliff = cliff_height * smoothstep(t / cliff_width): a wall at the foot, steeper than the client's walkable
      50 degrees, all the way round;
    - E in [lowest, highest] peak height, from low-frequency noise: the range rises and falls along the map;
    - ridges: `layers` ridge lines across the band (foothills nearest the valley, the back range highest near the
      edge), each a bump (1 - s^2)^2 across the band times its own ridged noise r = max(0, 1 - 1.7 |n|)^1.5, whose
      sharp crests run every way, so peaks, spurs and dips alternate; `saddles` sets how far the dips go down
      (crest = 1 - saddles * (1 - r));
    - M = (E - cliff_height) * ramp(u) * (0.3 * massif(u) + 0.7 * max(ridges)): the mass rises behind the cliff, so
      the highest crests reach E above the foot;
    - ledges: M terraced into shelves `step` yards high (a fraction `flat` of each step level), at heights that a
      slow noise shifts (no contour rings) and only where a noise mask allows (`coverage`).

    Only +, -, *, /, sqrt and floor, so the same spec gives the same heights everywhere.
    """

    def __init__(self, f: dict, bounds, seed: int):
        self.x0, self.x1, self.y0, self.y1 = bounds
        self.width = f["width"]
        self.hmin, self.hmax = f["height"]
        self.cliff_h = f["cliff_height"]
        self.cliff_w = f["cliff_width"]
        self.layers = f["layers"]
        self.saddles = f["saddles"]
        self.ledges = f["ledges"]
        self.jitter_amp = f["jitter"]
        half = min(self.x1 - self.x0, self.y1 - self.y0) * 0.5
        self.radius = min(max(f["corner_radius"], self.width + self.jitter_amp + self.cliff_w), half)
        r = self.radius
        self.core = (self.x0 + r, self.x1 - r, self.y0 + r, self.y1 - r)
        base = (seed * 7349 + f["seed"] * 2731 + 101) & 0xFFFFFFFF
        self.jitter = Fbm(base ^ 0x1F, f["jitter_scale"], f["jitter"], 3) if f["jitter"] > 0.0 else None
        scale = f["peak_scale"]
        self.envelope = Fbm(base ^ 0x2E, scale * 3.5, 1.0, 2)
        self.ridges = [Fbm((base + 977 * (k + 1)) & 0xFFFFFFFF, scale * (1.0 + 0.18 * k), 1.0, 3, 0.45)
                       for k in range(self.layers)]
        self.ledge_mask = Fbm(base ^ 0x3D, scale * 2.0, 1.0, 2) if self.ledges else None
        self.ledge_phase = Fbm(base ^ 0x4C, scale * 1.5, 1.0, 2) if self.ledges else None
        n = self.layers
        self.layer_shape = []
        for k in range(n):
            centre = 0.3 + 0.6 * k / (n - 1) if n > 1 else 0.6
            self.layer_shape.append((centre, 0.55 / n + 0.18, 0.55 + 0.45 * (k + 1) / n))

    def inside_distance(self, x: float, y: float) -> float:
        """Distance in from the tile edge, with the corners rounded (no jitter)."""
        cx0, cx1, cy0, cy1 = self.core
        dx = cx0 - x if x < cx0 else x - cx1 if x > cx1 else 0.0
        dy = cy0 - y if y < cy0 else y - cy1 if y > cy1 else 0.0
        if dx == 0.0:
            q = dy
        elif dy == 0.0:
            q = dx
        else:
            q = math.sqrt(dx * dx + dy * dy)
        return self.radius - q

    def depth(self, x: float, y: float) -> float:
        """Yards into the range beyond its foot (t); negative in the valley."""
        d = self.inside_distance(x, y)
        if d - self.jitter_amp >= self.width:
            return self.width - d + self.jitter_amp
        if self.jitter is not None:
            d += self.jitter(x, y)
        return self.width - d

    def apply(self, x: float, y: float, h: float) -> float:
        t = self.depth(x, y)
        if t <= 0.0:
            return h
        width = self.width
        u = t / width
        if u > 1.0:
            u = 1.0
        cliff = self.cliff_h * coords.smoothstep(t / self.cliff_w)
        e = 0.5 + self.envelope(x, y) * 1.1
        e = 0.0 if e < 0.0 else 1.0 if e > 1.0 else e
        peak = self.hmin + (self.hmax - self.hmin) * e
        ridge = 0.0
        for k, (centre, half_width, amp) in enumerate(self.layer_shape):
            s = (u - centre) / half_width
            if s <= -1.0 or s >= 1.0:
                continue
            bump = (1.0 - s * s) * (1.0 - s * s)
            r = 1.0 - 1.7 * abs(self.ridges[k](x, y))
            r = 0.0 if r < 0.0 else r * math.sqrt(r)
            v = amp * bump * (1.0 - self.saddles * (1.0 - r))
            if v > ridge:
                ridge = v
        ramp = coords.smoothstep(u / 0.3)
        mass = (peak - self.cliff_h) * ramp * (0.3 * coords.smoothstep(u / 0.75) + 0.7 * ridge)
        if self.ledges is not None and mass > 0.0:
            step = self.ledges["step"]
            flat = self.ledges["flat"]
            phase = self.ledge_phase(x, y)
            q = mass / step + phase
            whole = math.floor(q)
            frac = q - whole
            rise = 0.0 if frac <= flat else (frac - flat) / (1.0 - flat)
            terraced = (whole + rise - phase) * step
            cover = self.ledges["coverage"]
            mask = coords.smoothstep((self.ledge_mask(x, y) - (0.6 - 1.2 * cover)) / 0.25 + 0.5)
            mass += (terraced - mass) * mask * ramp
        return h + cliff + mass


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
        if kind == "mountains":
            return _Feature("mountains", None, {"range": Mountains(f, self.bounds, self.seed)})
        if kind == "lake":
            lake = f["lake"]
            x0, x1, y0, y1 = lake["shape"].bbox()
            reach = lake["shore"]
            return _Feature("lake", (x0 - reach, x1 + reach, y0 - reach, y1 + reach), dict(lake))
        if kind == "river_reaches":
            river = f["river"]
            path = river["path"]
            x0, x1, y0, y1 = path.bbox
            reach = path.half + river["bank"]
            return _Feature("river_reaches", (x0 - reach, x1 + reach, y0 - reach, y1 + reach),
                            {"path": path, "half": path.half, "bank": river["bank"], "depth": river["depth"],
                             "freeboard": river["freeboard"], "lakes": [lk["shape"] for lk in f["lakes"]]})
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
            elif kind == "mountains":
                h = d["range"].apply(x, y, h)
            elif kind == "lake":
                h = self._lake(d, x, y, h)
            elif kind == "river_reaches":
                h = self._river_reaches(d, x, y, h)
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

    @staticmethod
    def _lake(d: dict, x: float, y: float, h: float) -> float:
        shape = d["shape"]
        level = d["level"]
        edge = level + d["freeboard"]
        out = shape.distance(x, y)
        if out > 0.0:
            # The shore: blend toward `freeboard` above the water at the shape's edge (raising low ground into a
            # bank, lowering high ground into a beach).
            if out >= d["shore"]:
                return h
            return edge + (h - edge) * coords.smoothstep(out / d["shore"])
        k = coords.smoothstep(shape.inside_distance(x, y) / d["shelf"])
        bottom = edge - (d["depth"] + d["freeboard"]) * k
        if bottom < h:
            h = bottom
        else:
            # Ground already below the basin: keep it (deeper water), but raise the shelf toward the shore line so
            # the bottom meets the shore outside without a step.
            h += (bottom - h) * (1.0 - k)
        for isl in d["islands"]:
            dx = x - isl["center"][0]
            dy = y - isl["center"][1]
            u2 = (dx * dx + dy * dy) / (isl["radius"] * isl["radius"])
            if u2 < 1.0:
                top = level - d["depth"] + (isl["height"] + d["depth"]) * (1.0 - u2) * (1.0 - u2)
                if top > h:
                    h = top
        return h

    @staticmethod
    def _river_reaches(d: dict, x: float, y: float, h: float) -> float:
        path = d["path"]
        dist, seg, t = path.nearest(x, y)
        half = d["half"]
        if dist >= half + d["bank"]:
            return h
        level = path.terrain_level(path.arc(seg, t))
        edge = level + d["freeboard"]
        if dist <= half:
            # Channel: a rounded bed `depth` below the water at the centre line, up to the bank lip at the edge,
            # built up where the ground is lower (but never inside a lake, which is deeper already).
            sn = dist / half
            bottom = edge - (d["depth"] + d["freeboard"]) * (1.0 - sn * sn)
            if bottom < h or not any(s.contains(x, y) for s in d["lakes"]):
                return bottom
            return h
        target = edge + (h - edge) * coords.smoothstep((dist - half) / d["bank"])
        if target > h and any(s.contains(x, y) for s in d["lakes"]):
            return h  # no banks raised inside a lake: the river runs into it
        return target

    def raw(self, x: float, y: float) -> float:
        return self._eval(x, y)

    def mountain_depth(self, x: float, y: float) -> float | None:
        """Yards into the deepest mountain range at a point (negative in the valley), or None without mountains."""
        best = None
        for feat in self.features:
            if feat.kind == "mountains":
                t = feat.data["range"].depth(x, y)
                if best is None or t > best:
                    best = t
        return best

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
