r"""Designs as data: designs/<RaceFile>.json -> line cores and halos on the model's charts.

A design is a list of elements. Every element names its chart ("on": arm, torso, leg or face), a kind and its
places in design coordinates (coords.py): arm/leg [t, a] (a in turns, 0 the outer line, +0.25 the front),
torso [t, s] (s 0 front midline .. 1 back midline), face [x, y] in eye separations. Sizes are body units (bu) on the
body and eye separations on the face. Common keys:

    w        stroke half-width (default 0.35)          glow     halo strength 0..1 (default 1)
    strength core strength 0..1 (default 1)             fill     interior level of filled shapes (default 0.7)
    rim      rim half-width of filled shapes           sex      "Male" or "Female": only on that sex

Kinds (keys beyond the common ones):

    line           pts, smooth (Catmull-Rom), taper [w0, w1], closed
    ring           at, r                               arc       at, r, from, to (degrees, 0 = +U, 90 = +V)
    shape          shape (disc crescent star diamond leaf triangle sun almond square), at, r, rot, n, inner,
                   thick, len, wid, rays, ray_len
    column         from, to, count, shape {...}, phases (moon phases), scale [s0, s1], link (half-width)
    band           limbs: t, motif (dots diamonds teeth wave chevrons crosses runes knot ticks squares), n (repeats
                   around: an integer, so it is seamless), size, rails, gap, seed
    helix          limbs: from, to (t), turns, strands, phase
    crack          at, dir (degrees), len, seed, branches, jag
    vine           pts, amp, period, leaf {len, wid, every}
    dip            limbs: t (the edge), ragged, freq (integer lobes around), seed, drips, drip_len, toward (+1: to the
                   end of the limb, -1: toward the body)
    script         from, to, count, h, wid, seed      constellation  area [[p0], [p1]], count, seed, link, r
    sunburst       at, rays, r0, r1, disc              circuit   area, count, seed, node
    claws          from, to, count, spacing, curve     zigzag    pts, amp, period
    rune           at, h, wid, seed                    spiral    at, r, turns
    chevron        at, wid, h, rot                     stripes   from, to, count, len, angle, taper

Every motif is our own: the runes are glyphs from a fixed seed (a stem and two or three branches on a 3x4 grid),
the cracks a seeded random walk, the knots two phase-shifted strands with gaps where they cross.

Limbs are periodic: a shape is measured in U relative to its own anchor, wrapped by the ring length of the texel's
row, so it is continuous across the inner wrap seam; band, helix and dip repeat an integer number of times around.
"""

from __future__ import annotations

import json
import math
import os
import random
import re

import numpy as np

from . import TOOL, MarkForgeError
from .coords import wrap

DESIGN_DIR = os.path.join(TOOL, "designs")
KINDS = {"line", "ring", "arc", "shape", "column", "band", "helix", "crack", "vine", "dip", "script", "constellation",
         "sunburst", "circuit", "claws", "zigzag", "rune", "spiral", "chevron", "stripes"}
SHAPES = {"disc", "crescent", "star", "diamond", "leaf", "triangle", "sun", "almond", "square"}
MOTIFS = {"dots", "diamonds", "teeth", "wave", "chevrons", "crosses", "runes", "knot", "ticks", "squares"}
CHARTS = {"arm", "torso", "leg", "face"}
KEY = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
MIN_HALF_TEXELS = 1.25  # 2.5 texels full width at 512: lines survive the 256 bake


# --- loading ------------------------------------------------------------------------------------------------------


def load_race(race_file: str, folder: str = DESIGN_DIR) -> dict:
    path = os.path.join(folder, race_file + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise MarkForgeError(f"{path}: {e}") from None
    problems = check_race(data, race_file)
    if problems:
        raise MarkForgeError(f"{path}: " + "; ".join(problems[:5]))
    return data


def check_race(data: dict, race_file: str) -> list[str]:
    out = []
    if data.get("race") != race_file:
        out.append(f"race is {data.get('race')!r}, the file name says {race_file!r}")
    designs = data.get("designs")
    if not isinstance(designs, list) or len(designs) != 4:
        return out + ["needs exactly 4 designs"]
    keys = set()
    for i, d in enumerate(designs):
        where = f"design {i + 1}"
        if not KEY.match(str(d.get("key", ""))):
            out.append(f"{where}: key {d.get('key')!r} is not letters and digits")
        if d.get("key") in keys:
            out.append(f"{where}: key {d.get('key')} repeats")
        keys.add(d.get("key"))
        if not d.get("name") or not d.get("lore"):
            out.append(f"{where}: needs a name and a lore line")
        els = d.get("elements")
        if not isinstance(els, list) or not els:
            out.append(f"{where}: no elements")
            continue
        for j, e in enumerate(els):
            if e.get("kind") not in KINDS:
                out.append(f"{where} element {j + 1}: unknown kind {e.get('kind')!r}")
            if e.get("on") not in CHARTS:
                out.append(f"{where} element {j + 1}: unknown chart {e.get('on')!r}")
            if e.get("kind") in ("band", "helix", "dip") and e.get("on") not in ("arm", "leg"):
                out.append(f"{where} element {j + 1}: {e.get('kind')} goes round a limb (arm or leg)")
            if e.get("kind") == "band" and e.get("motif") not in MOTIFS:
                out.append(f"{where} element {j + 1}: unknown motif {e.get('motif')!r}")
            if e.get("kind") == "band" and int(e.get("n", 0)) != e.get("n", 0):
                out.append(f"{where} element {j + 1}: band n must be an integer (seamless)")
            if e.get("kind") == "shape" and e.get("shape") not in SHAPES:
                out.append(f"{where} element {j + 1}: unknown shape {e.get('shape')!r}")
            if e.get("sex") not in (None, "Male", "Female"):
                out.append(f"{where} element {j + 1}: sex is Male or Female")
    return out


# --- distance kernel (1D arrays of texel coordinates in metres) ---------------------------------------------------


def seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    if L2 < 1e-18:
        return np.hypot(px - ax, py - ay), np.zeros_like(px)
    t = np.clip(((px - ax) * vx + (py - ay) * vy) / L2, 0.0, 1.0)
    return np.hypot(px - ax - t * vx, py - ay - t * vy), t


def polyline_dist(px, py, pts):
    """Distance to a polyline and the arc-length fraction (0..1) of the closest point."""
    pts = np.asarray(pts, np.float64)
    d = np.full(px.shape, np.inf)
    s = np.zeros(px.shape)
    seglen = np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))
    total = max(float(seglen.sum()), 1e-12)
    acc = 0.0
    for k in range(len(pts) - 1):
        dk, tk = seg_dist(px, py, pts[k, 0], pts[k, 1], pts[k + 1, 0], pts[k + 1, 1])
        better = dk < d
        d = np.where(better, dk, d)
        s = np.where(better, (acc + tk * seglen[k]) / total, s)
        acc += seglen[k]
    return d, s


def poly_sdf(px, py, pts):
    """Signed distance to a closed polygon (negative inside)."""
    pts = np.asarray(pts, np.float64)
    closed = np.vstack([pts, pts[:1]])
    d, _ = polyline_dist(px, py, closed)
    inside = np.zeros(px.shape, bool)
    for k in range(len(pts)):
        (x0, y0), (x1, y1) = closed[k], closed[k + 1]
        cond = (y0 > py) != (y1 > py)
        xi = x0 + (py - y0) * (x1 - x0) / np.where(y1 - y0 == 0, 1e-12, y1 - y0)
        inside ^= cond & (px < xi)
    return np.where(inside, -d, d)


def catmull(pts, per=12):
    pts = [tuple(p) for p in pts]
    if len(pts) < 3:
        return pts
    ext = [pts[0]] + pts + [pts[-1]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = (np.array(ext[i + k], np.float64) for k in (-1, 0, 1, 2))
        for j in range(per):
            t = j / per
            out.append(tuple(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                                    (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t)))
    out.append(pts[-1])
    return out


def rot2(x, y, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


def shape_sdf(px, py, cx, cy, spec, unit):
    """A filled shape centred at (cx, cy) metres; sizes in units (bu or es) times unit."""
    kind = spec.get("shape", "disc")
    r = float(spec.get("r", 1.0)) * unit
    rot = float(spec.get("rot", 0.0))
    lx, ly = rot2(px - cx, py - cy, -rot)
    if kind == "disc":
        return np.hypot(lx, ly) - r
    if kind == "crescent":
        thick = float(spec.get("thick", 0.45))
        off = r * (1.0 - thick) * 1.15
        return np.maximum(np.hypot(lx, ly) - r, -(np.hypot(lx - off, ly) - r * 0.98))
    if kind == "almond":  # a lens pointed left and right
        wid = float(spec.get("wid", 0.45)) * r
        R = (r * r + wid * wid) / (2 * wid)
        return np.maximum(np.hypot(lx, ly - (R - wid)) - R, np.hypot(lx, ly + (R - wid)) - R)
    if kind == "leaf":
        L = float(spec.get("len", 2.0 * r / unit)) * unit
        W = float(spec.get("wid", 0.8 * r / unit)) * unit
        R = (L * L / 4 + W * W / 4) / W
        return np.maximum(np.hypot(lx, ly - (R - W / 2)) - R, np.hypot(lx, ly + (R - W / 2)) - R)
    n = int(spec.get("n", 4 if kind in ("diamond", "square") else 3 if kind == "triangle" else 5))
    if kind == "star":
        inner = float(spec.get("inner", 0.45))
        pts = [(r * (1 if k % 2 == 0 else inner) * math.sin(math.pi * k / n),
                -r * (1 if k % 2 == 0 else inner) * math.cos(math.pi * k / n)) for k in range(2 * n)]
        return poly_sdf(lx, ly, pts)
    if kind == "diamond":
        wid = float(spec.get("wid", 0.6))
        return poly_sdf(lx, ly, [(0, -r), (r * wid, 0), (0, r), (-r * wid, 0)])
    if kind == "square":
        return np.maximum(np.abs(lx), np.abs(ly)) - r
    if kind == "triangle":
        pts = [(r * math.sin(2 * math.pi * k / 3), -r * math.cos(2 * math.pi * k / 3)) for k in range(3)]
        return poly_sdf(lx, ly, pts)
    if kind == "sun":
        rays = int(spec.get("rays", 8))
        rl = float(spec.get("ray_len", 0.8)) * r
        ang = np.arctan2(ly, lx)
        rr = np.hypot(lx, ly)
        q = np.abs(wrap(ang, 2 * math.pi / rays)) * rr
        ray = np.maximum(q - 0.12 * r * np.clip(1 - (rr - r) / rl, 0, 1), np.maximum(r * 0.9 - rr, rr - r - rl))
        return np.minimum(rr - r * 0.7, ray)
    raise MarkForgeError(f"unknown shape {kind}")


def rune_strokes(seed, w, h):
    """An original angular glyph from a seed: a stem plus 2-3 branches on a 3x4 anchor grid."""
    rnd = random.Random(seed)
    gx = [-w / 2, 0, w / 2]
    gy = [-h / 2, -h / 6, h / 6, h / 2]
    strokes = [[(0, -h / 2), (0, h / 2)]]
    for _ in range(rnd.choice((2, 3))):
        a = (0, rnd.choice(gy))
        b = (rnd.choice((gx[0], gx[2])), rnd.choice(gy))
        if rnd.random() < 0.5:
            strokes.append([a, b])
        else:
            strokes.append([a, b, (b[0], rnd.choice(gy))])
    return strokes


# --- the canvas of one chart ----------------------------------------------------------------------------------------


class Canvas:
    """core and halo over one region's texels. Strokes and fills are max-combined."""

    def __init__(self, charts, region_name):
        self.ch = charts
        self.name = "head" if region_name == "face" else region_name
        self.r = charts.regions[self.name]
        n = len(self.r)
        self.core = np.zeros(n)
        self.halo = np.zeros(n)
        self.aa_all = 1.0 * self.r.texel_local  # anti-aliasing by the local texel size (stretched UVs are coarse)
        self.unit = charts.unit(self.name)

    # coordinates of the texels, the limbs relative to an anchor so one element never sees the wrap seam
    def coords(self, anchor_u=0.0, vlo=-np.inf, vhi=np.inf):
        r = self.r
        sel = np.nonzero((r.V >= vlo) & (r.V <= vhi))[0]
        U, V = r.U[sel], r.V[sel]
        if r.period is not None:
            U = anchor_u + wrap(U - anchor_u, r.period[sel])
        return sel, U, V

    def half_width(self, w):
        return max(float(w) * self.unit, MIN_HALF_TEXELS * self.r.texel)

    def add_stroke(self, sel, d, w, strength=1.0, glow=1.0, sigma=None):
        """d: distance (metres) on the selected texels; w: half-width in metres (scalar or array)."""
        if sigma is None:
            # the face is small and close to the camera: a tight halo there
            if self.name == "head":
                sigma = 1.5 * np.asarray(w) + self.r.texel
            else:
                sigma = 3.5 * np.asarray(w) + 2 * self.r.texel
        aa = self.aa_all[sel]
        # never thinner than 2.5 local texels: where the UVs are stretched a thin line would alias (and step across a
        # seam, whose two sides sample it on different grids)
        w = np.maximum(w, MIN_HALF_TEXELS * self.r.texel_local[sel])
        core = strength * np.clip((w + aa - d) / (2 * aa), 0, 1)
        halo = strength * glow * np.exp(-np.maximum(d - w, 0) / sigma)
        self.core[sel] = np.maximum(self.core[sel], core)
        self.halo[sel] = np.maximum(self.halo[sel], halo)

    def add_fill(self, sel, sd, level=0.7, rim=None, strength=1.0, glow=1.0):
        rim = rim if rim is not None else MIN_HALF_TEXELS * self.r.texel
        aa = self.aa_all[sel]
        rim = np.maximum(rim, MIN_HALF_TEXELS * self.r.texel_local[sel])
        inside = level * np.clip((aa - sd) / (2 * aa), 0, 1)
        edge = np.clip((rim + aa - np.abs(sd)) / (2 * aa), 0, 1)
        core = strength * np.maximum(inside, edge)
        sigma = 1.4 * self.unit if self.name != "head" else 0.035 * self.unit
        halo = strength * glow * np.exp(-np.maximum(sd, 0) / sigma)
        self.core[sel] = np.maximum(self.core[sel], core)
        self.halo[sel] = np.maximum(self.halo[sel], halo)


# --- evaluating elements --------------------------------------------------------------------------------------------


class Painter:
    def __init__(self, charts, sex_name):
        self.ch = charts
        self.sex = sex_name
        self.canvases = {}

    def canvas(self, on):
        if on not in self.canvases:
            self.canvases[on] = Canvas(self.ch, on)
        return self.canvases[on]

    def m(self, on, pts):
        """Design points -> metres."""
        name = "head" if on == "face" else on
        return self.ch.to_metres(name, pts)

    def paint(self, design):
        for i, e in enumerate(design["elements"]):
            if e.get("sex") and e["sex"] != self.sex:
                continue
            try:
                getattr(self, "k_" + e["kind"])(e, self.canvas(e["on"]))
            except MarkForgeError:
                raise
            except Exception as ex:  # a design error names its element
                raise MarkForgeError(f"design {design.get('key')}: element {i + 1} ({e['kind']}): {ex}") from ex
        return self.canvases

    # helpers
    def _strokes(self, e, cv, polylines, w=None, taper=None):
        """Paint polylines given in metres (each an (n, 2) array)."""
        w = self._w(e, cv) if w is None else w
        reach = 6 * (w + 3.5 * w + 2 * cv.r.texel)
        allp = np.vstack(polylines)
        anchor = float(np.mean(allp[:, 0]))
        sel, U, V = cv.coords(anchor, allp[:, 1].min() - reach, allp[:, 1].max() + reach)
        if not len(sel):
            return
        best_d = np.full(len(sel), np.inf)
        best_w = np.full(len(sel), w)
        for pl in polylines:
            d, s = polyline_dist(U, V, pl)
            if taper is not None:
                ww = np.maximum(cv.half_width(taper[0]) + (cv.half_width(taper[1]) - cv.half_width(taper[0])) * s,
                                MIN_HALF_TEXELS * cv.r.texel)
                score = d - ww
                better = score < best_d - best_w
            else:
                ww = w
                better = d < best_d
            best_d = np.where(better, d, best_d)
            best_w = np.where(better, ww, best_w)
        cv.add_stroke(sel, best_d, best_w, float(e.get("strength", 1.0)), float(e.get("glow", 1.0)))

    def _w(self, e, cv, key="w", default=0.35):
        return cv.half_width(e.get(key, default))

    def _fill_shape(self, e, cv, centre_m, spec):
        unit = cv.unit
        r = float(spec.get("r", 1.0)) * unit
        reach = r * 3 + 6 * 1.4 * unit
        sel, U, V = cv.coords(float(centre_m[0]), centre_m[1] - reach, centre_m[1] + reach)
        if not len(sel):
            return
        sd = shape_sdf(U, V, float(centre_m[0]), float(centre_m[1]), spec, unit)
        rim = spec.get("rim", e.get("rim"))
        if rim is None:
            rim = 0.12 * float(spec.get("r", 1.0))  # a rim in proportion to the shape
        cv.add_fill(sel, sd, float(spec.get("fill", e.get("fill", 0.7))), cv.half_width(rim),
                    float(e.get("strength", 1.0)), float(e.get("glow", 1.0)))

    def _local(self, on, at, du, dv):
        """A point offset (du, dv) in units from a design point, in metres (for stamps built in metres)."""
        c = self.m(on, [at])[0]
        u = self.ch.unit("head" if on == "face" else on)
        return np.array([c[0] + du * u, c[1] + dv * u])

    # kinds
    def k_line(self, e, cv):
        pts = e["pts"]
        if e.get("smooth"):
            pts = catmull(pts)
        if e.get("closed"):
            pts = list(pts) + [pts[0]]
        self._strokes(e, cv, [self.m(e["on"], pts)], taper=e.get("taper"))

    def k_zigzag(self, e, cv):
        base = self.m(e["on"], catmull(e["pts"]) if e.get("smooth") else e["pts"])
        amp, period = float(e.get("amp", 1.0)) * cv.unit, float(e.get("period", 3.0)) * cv.unit
        seg = np.hypot(*np.diff(base, axis=0).T)
        total = float(seg.sum())
        n = max(2, int(round(2 * total / period)))
        out = []
        for i in range(n + 1):
            s = total * i / n
            k = int(np.searchsorted(np.cumsum(seg), s, side="left"))
            k = min(k, len(seg) - 1)
            s0 = float(np.cumsum(seg)[k] - seg[k])
            f = (s - s0) / max(seg[k], 1e-12)
            p = base[k] + (base[k + 1] - base[k]) * f
            dvec = (base[k + 1] - base[k]) / max(seg[k], 1e-12)
            nrm = np.array([-dvec[1], dvec[0]])
            out.append(p + nrm * amp * (1 if i % 2 else -1) * (0 if i in (0, n) else 1))
        self._strokes(e, cv, [np.array(out)])

    def k_ring(self, e, cv):
        c = self.m(e["on"], [e["at"]])[0]
        r = float(e.get("r", 1.0)) * cv.unit
        a = np.linspace(0, 2 * math.pi, 49)
        self._strokes(e, cv, [np.stack([c[0] + r * np.cos(a), c[1] + r * np.sin(a)], -1)])

    def k_arc(self, e, cv):
        c = self.m(e["on"], [e["at"]])[0]
        r = float(e.get("r", 1.0)) * cv.unit
        a = np.radians(np.linspace(float(e.get("from", 0)), float(e.get("to", 180)), 33))
        self._strokes(e, cv, [np.stack([c[0] + r * np.cos(a), c[1] + r * np.sin(a)], -1)], taper=e.get("taper"))

    def k_spiral(self, e, cv):
        c = self.m(e["on"], [e["at"]])[0]
        r = float(e.get("r", 1.0)) * cv.unit
        turns = float(e.get("turns", 2.0))
        a = np.linspace(0, 2 * math.pi * turns, int(40 * turns) + 2)
        rr = r * a / a[-1]
        self._strokes(e, cv, [np.stack([c[0] + rr * np.cos(a), c[1] + rr * np.sin(a)], -1)])

    def k_shape(self, e, cv):
        c = self.m(e["on"], [e["at"]])[0]
        self._fill_shape(e, cv, c, e)

    def k_chevron(self, e, cv):
        c = self.m(e["on"], [e["at"]])[0]
        wid, h = float(e.get("wid", 2.0)) * cv.unit, float(e.get("h", 1.2)) * cv.unit
        pts = np.array([rot2(-wid / 2, -h / 2, e.get("rot", 0)), rot2(0, h / 2, e.get("rot", 0)),
                        rot2(wid / 2, -h / 2, e.get("rot", 0))]) + c
        self._strokes(e, cv, [pts])

    def k_rune(self, e, cv):
        c = self.m(e["on"], [e["at"]])[0]
        h, wid = float(e.get("h", 3.0)) * cv.unit, float(e.get("wid", 2.0)) * cv.unit
        self._strokes(e, cv, [np.array(st) + c for st in rune_strokes(int(e.get("seed", 1)), wid, h)])

    def k_column(self, e, cv):
        p0, p1 = np.asarray(e["from"], float), np.asarray(e["to"], float)
        n = int(e.get("count", 3))
        spec = dict(e.get("shape", {"shape": "disc", "r": 0.8}))
        sc = e.get("scale", [1.0, 1.0])
        centres = []
        for i in range(n):
            f = i / max(1, n - 1)
            p = p0 + (p1 - p0) * f
            c = self.m(e["on"], [p])[0]
            centres.append(c)
            s = dict(spec)
            s["r"] = float(spec.get("r", 0.8)) * (sc[0] + (sc[1] - sc[0]) * f)
            if e.get("phases"):
                # waxing crescent -> full -> waning: the crescent turns and thickens toward the middle
                ph = f * 2 - 1
                if abs(ph) < 0.2:
                    s["shape"] = "disc"
                else:
                    s["shape"] = "crescent"
                    s["thick"] = 0.25 + 0.5 * (1 - abs(ph))
                    s["rot"] = float(spec.get("rot", 0)) + (0 if ph < 0 else 180)
            self._fill_shape(e, cv, c, s)
        if e.get("link"):
            lw = cv.half_width(e["link"])
            r0 = float(spec.get("r", 0.8)) * cv.unit * 1.25
            segs = []
            for a, b in zip(centres, centres[1:]):
                v = b - a
                L = float(np.hypot(*v))
                if L > 2 * r0:
                    segs.append(np.array([a + v * r0 / L, b - v * r0 / L]))
            if segs:
                self._strokes(e, cv, segs, w=lw)

    def k_band(self, e, cv):
        on = e["on"]
        reg = cv.r
        vc = float(self.m(on, [[e["t"], 0]])[0][1])
        size = float(e.get("size", 1.0)) * cv.unit
        n = int(e["n"])
        motif = e["motif"]
        gap = float(e.get("gap", 1.4 * e.get("size", 1.0))) * cv.unit
        reach = gap + size * 2 + 8 * cv.unit
        sel, U, V = cv.coords(0.0, vc - reach, vc + reach)
        if not len(sel):
            return
        C = reg.period[sel]
        # integer repeats around: seamless at the chart's wrap. The phase puts the inner line (U = +-C/2, where the
        # models' UV wrap seam runs) between two motifs (a knot's crossing gaps away from it), so no crisp edge lands
        # on the UV seam
        ph = np.mod(U / C * n - n / 2.0 + (0.25 if motif == "knot" else 0.0), 1.0)
        cell = C / n
        du = (ph - 0.5) * cell  # metres from the cell centre
        dv = V - vc
        w = self._w(e, cv)
        st, gl = float(e.get("strength", 1.0)), float(e.get("glow", 1.0))
        rails = e.get("rails", 0)
        if rails:
            rw = cv.half_width(rails)
            for off in (-gap, gap):
                cv.add_stroke(sel, np.abs(dv - off), rw, st, gl)
        if motif == "dots":
            cv.add_fill(sel, np.hypot(du, dv) - size * 0.5, float(e.get("fill", 1.0)), w, st, gl)
        elif motif == "squares":
            cv.add_fill(sel, np.maximum(np.abs(du), np.abs(dv)) - size * 0.45, float(e.get("fill", 0.8)), w, st, gl)
        elif motif == "diamonds":
            cv.add_fill(sel, (np.abs(du) / 0.6 + np.abs(dv)) - size * 0.6, float(e.get("fill", 0.8)), w, st, gl)
        elif motif == "crosses":
            d = np.minimum(np.maximum(np.abs(du), np.abs(dv) - size * 0.6),
                           np.maximum(np.abs(dv), np.abs(du) - size * 0.6))
            cv.add_stroke(sel, d, w, st, gl)
        elif motif == "ticks":
            cv.add_stroke(sel, np.maximum(np.abs(du), np.abs(dv) - size * 0.6), w, st, gl)
        elif motif in ("teeth", "wave", "chevrons"):
            x = ph  # 0..1 across the cell
            if motif == "teeth":
                y = (np.abs(x - 0.5) * 2 - 0.5) * size
            elif motif == "wave":
                y = 0.5 * size * np.sin(2 * math.pi * x)
            else:
                y = (0.5 - np.abs(x - 0.5) * 2) * size * 0.8
            # distance to the curve measured perpendicular to its local slope
            slope = {"teeth": 2 * size / cell, "wave": math.pi * size / cell, "chevrons": 1.6 * size / cell}[motif]
            if motif == "wave":
                slope = slope * np.abs(np.cos(2 * math.pi * x))
            d = np.abs(dv - y) / np.sqrt(1 + slope ** 2)
            cv.add_stroke(sel, d, w, st, gl)
            if motif == "chevrons":
                cv.add_stroke(sel, np.abs(dv - y - size * 0.7) / np.sqrt(1 + slope ** 2), w, st, gl)
        elif motif == "knot":
            # two strands, half a cell out of phase; at each crossing the strand that is "under" breaks
            a1 = 0.55 * size * np.sin(2 * math.pi * ph)
            a2 = -a1
            slope = math.pi * 1.1 * size / cell * np.abs(np.cos(2 * math.pi * ph))
            d1 = np.abs(dv - a1) / np.sqrt(1 + slope ** 2)
            d2 = np.abs(dv - a2) / np.sqrt(1 + slope ** 2)
            # crossings at ph = 0 and 0.5: strand 1 over at 0, strand 2 over at 0.5
            near0 = np.abs(wrap(ph, 1.0)) * cell
            near5 = np.abs(ph - 0.5) * cell
            gapw = w * 2.6
            d1 = np.where(near5 < gapw, np.inf, d1)
            d2 = np.where(near0 < gapw, np.inf, d2)
            cv.add_stroke(sel, np.minimum(d1, d2), w, st, gl)
        elif motif == "runes":
            # one glyph per cell, all from one seed so every cell matches (seamless); alternating mirror
            d = np.full(len(sel), np.inf)
            k = np.floor(U / C * n - n / 2.0).astype(int)
            for idx, strokes in enumerate((rune_strokes(int(e.get("seed", 7)), size * 0.7, size * 1.6),
                                           rune_strokes(int(e.get("seed", 7)) + 1, size * 0.7, size * 1.6))):
                m = (np.mod(k, 2) == idx)
                for stp in strokes:
                    dd, _ = polyline_dist(du, dv, np.array(stp))
                    d = np.where(m, np.minimum(d, dd), d)
            cv.add_stroke(sel, d, w, st, gl)

    def k_helix(self, e, cv):
        on = e["on"]
        v0 = float(self.m(on, [[e["from"], 0]])[0][1])
        v1 = float(self.m(on, [[e["to"], 0]])[0][1])
        turns = float(e.get("turns", 1.0))
        strands = int(e.get("strands", 1))
        w = self._w(e, cv)
        sel, U, V = cv.coords(0.0, min(v0, v1) - 4 * cv.unit, max(v0, v1) + 4 * cv.unit)
        if not len(sel):
            return
        C = cv.r.period[sel]
        f = np.clip((V - v0) / (v1 - v0), 0, 1)
        target = float(e.get("phase", 0.0)) + turns * f
        ph = np.mod(U / C - target, 1.0 / strands) * strands  # 0..1 per strand
        du = np.minimum(ph, 1 - ph) * C / strands
        slope = turns * C / max(abs(v1 - v0), 1e-6)
        d = du / np.sqrt(1 + slope ** 2)
        ends = np.maximum(v0 - V, V - v1) if v1 > v0 else np.maximum(v1 - V, V - v0)
        d = np.maximum(d, ends)
        cv.add_stroke(sel, d, w, float(e.get("strength", 1.0)), float(e.get("glow", 1.0)))
        leaf = e.get("leaf")
        if leaf:
            # leaves on alternate sides of the strand, each its own stamp (anchored where it sits)
            t0, t1 = float(e["from"]), float(e["to"])
            every = float(leaf.get("every", 0.15))
            k = 0
            t = t0 + every / 2
            while t < t1:
                f = (t - t0) / (t1 - t0)
                for j in range(strands):
                    a = float(e.get("phase", 0.0)) + turns * f + j / strands
                    side = 1 if k % 2 == 0 else -1
                    c = self.m(on, [[t, a]])[0]
                    ang = math.degrees(math.atan2(1.0, turns * float(cv.r.period.mean()) / max(abs(v1 - v0), 1e-6)))
                    lv = float(leaf.get("len", 2.0)) * cv.unit
                    off = np.array([side * 0.55 * lv, 0.0])
                    self._fill_shape(e, cv, c + off, {"shape": "leaf", "len": leaf.get("len", 2.0),
                                                      "wid": leaf.get("wid", 0.8), "r": leaf.get("len", 2.0) / 2,
                                                      "rot": side * (90 - ang) * 0.6, "fill": leaf.get("fill", 0.6)})
                t += every
                k += 1

    def k_dip(self, e, cv):
        """A limb dipped in paint from an edge to its end: the edge is ragged by integer lobes around the limb."""
        on = e["on"]
        vedge = float(self.m(on, [[e["t"], 0]])[0][1])
        toward = int(e.get("toward", 1))
        sel, U, V = cv.coords(0.0)
        C = cv.r.period[sel]
        rnd = random.Random(int(e.get("seed", 3)))
        amp = float(e.get("ragged", 1.5)) * cv.unit
        freq = int(e.get("freq", 5))
        edge = np.zeros(len(sel))
        for k in range(1, 4):
            ph = rnd.random() * 2 * math.pi
            edge += amp / k * np.sin(2 * math.pi * freq * k * U / C + ph)
        drips = int(e.get("drips", 0))
        dl = float(e.get("drip_len", 4.0)) * cv.unit
        for j in range(drips):
            a0 = rnd.random()
            width = (0.04 + 0.03 * rnd.random())
            dist_turns = np.abs(wrap(U / C - a0, 1.0))
            lobe = np.clip(1 - dist_turns / width, 0, 1) ** 0.5
            edge -= lobe * dl * (0.6 + 0.4 * rnd.random())
        sd = (vedge + edge - V) * toward  # negative inside the dipped part
        cv.add_fill(sel, sd, float(e.get("fill", 0.85)), cv.half_width(e.get("rim", 0.3)),
                    float(e.get("strength", 1.0)), float(e.get("glow", 1.0)))

    def k_crack(self, e, cv):
        rnd = random.Random(int(e.get("seed", 1)))
        start = self.m(e["on"], [e["at"]])[0]
        jag = float(e.get("jag", 0.5))
        lines = []

        def walk(p, ang, length_units, depth):
            pts = [p.copy()]
            # the step count comes from the design's own numbers, never from metres: len / 1.2 is often a whole
            # number (24 -> 20, 18 -> 15), and a last-bit difference in the model's unit (another numpy, another
            # CPU) must not add a step, which would change every later random draw of the walk
            steps = max(3, int(round(length_units / 1.2, 6)))
            step = length_units * cv.unit / steps
            for i in range(steps):
                ang += rnd.uniform(-jag, jag) * 0.9
                p = p + step * np.array([math.cos(ang), math.sin(ang)])
                pts.append(p.copy())
                if depth < int(e.get("branches", 2)) and rnd.random() < 0.18:
                    walk(p.copy(), ang + rnd.choice((-1, 1)) * rnd.uniform(0.5, 1.0), length_units * 0.45,
                         depth + 1)
            lines.append(np.array(pts))

        walk(np.array(start, float), math.radians(float(e.get("dir", 90))), float(e.get("len", 12.0)), 0)
        self._strokes(e, cv, lines, taper=e.get("taper", [e.get("w", 0.35), e.get("w", 0.35) * 0.5]))

    def k_vine(self, e, cv):
        base = self.m(e["on"], catmull(e["pts"]))
        amp, period = float(e.get("amp", 1.5)) * cv.unit, float(e.get("period", 10.0)) * cv.unit
        seg = np.hypot(*np.diff(base, axis=0).T)
        cum = np.concatenate([[0], np.cumsum(seg)])
        n = max(8, int(cum[-1] / (0.6 * cv.unit)))
        s = np.linspace(0, cum[-1], n)
        pts, leaves = [], []
        for si in s:
            k = min(int(np.searchsorted(cum, si, side="right")) - 1, len(seg) - 1)
            f = (si - cum[k]) / max(seg[k], 1e-12)
            p = base[k] + (base[k + 1] - base[k]) * f
            dvec = (base[k + 1] - base[k]) / max(seg[k], 1e-12)
            nrm = np.array([-dvec[1], dvec[0]])
            pts.append(p + nrm * amp * math.sin(2 * math.pi * si / period))
        self._strokes(e, cv, [np.array(pts)])
        leaf = e.get("leaf")
        if leaf:
            every = float(leaf.get("every", 0.5)) * period
            side = 1
            si = every / 2
            while si < cum[-1]:
                k = min(int(np.searchsorted(cum, si, side="right")) - 1, len(seg) - 1)
                f = (si - cum[k]) / max(seg[k], 1e-12)
                p = base[k] + (base[k + 1] - base[k]) * f
                dvec = (base[k + 1] - base[k]) / max(seg[k], 1e-12)
                nrm = np.array([-dvec[1], dvec[0]])
                p = p + nrm * amp * math.sin(2 * math.pi * si / period)
                ang = math.degrees(math.atan2(dvec[1], dvec[0])) + side * 50
                c = p + side * nrm * float(leaf.get("len", 2.0)) * cv.unit * 0.55
                self._fill_shape(e, cv, c, {"shape": "leaf", "len": leaf.get("len", 2.0), "wid": leaf.get("wid", 0.8),
                                            "rot": ang, "r": leaf.get("len", 2.0) / 2,
                                            "fill": leaf.get("fill", 0.6)})
                side = -side
                si += every

    def k_script(self, e, cv):
        p0, p1 = np.asarray(e["from"], float), np.asarray(e["to"], float)
        n = int(e.get("count", 6))
        h, wid = float(e.get("h", 2.4)) * cv.unit, float(e.get("wid", 1.4)) * cv.unit
        lines = []
        for i in range(n):
            c = self.m(e["on"], [p0 + (p1 - p0) * (i + 0.5) / n])[0]
            lines += [np.array(st) + c for st in rune_strokes(int(e.get("seed", 11)) * 100 + i, wid, h)]
        self._strokes(e, cv, lines)

    def k_constellation(self, e, cv):
        rnd = random.Random(int(e.get("seed", 5)))
        (a0, b0), (a1, b1) = e["area"]
        n = int(e.get("count", 6))
        stars = []
        for _ in range(n):
            stars.append(self.m(e["on"], [[a0 + (a1 - a0) * rnd.random(), b0 + (b1 - b0) * rnd.random()]])[0])
        stars.sort(key=lambda p: (p[1], p[0]))
        for k, c in enumerate(stars):
            self._fill_shape(e, cv, c, {"shape": "star", "n": 4, "inner": 0.35, "r": float(e.get("r", 0.9)) *
                                        (1.0 if k % 3 else 1.5), "fill": 1.0})
        if e.get("link", True):
            r = float(e.get("r", 0.9)) * cv.unit * 1.6
            segs = []
            for a, b in zip(stars, stars[1:]):
                v = b - a
                L = float(np.hypot(*v))
                if L > 2.5 * r:
                    segs.append(np.array([a + v * r / L, b - v * r / L]))
            if segs:
                self._strokes(e, cv, segs, w=cv.half_width(e.get("w", 0.18)))

    def k_sunburst(self, e, cv):
        c = self.m(e["on"], [e["at"]])[0]
        rays = int(e.get("rays", 12))
        r0, r1 = float(e.get("r0", 2.0)) * cv.unit, float(e.get("r1", 6.0)) * cv.unit
        lines = []
        for k in range(rays):
            a = 2 * math.pi * k / rays + math.radians(float(e.get("rot", 0)))
            rr = r1 if k % 2 == 0 else r0 + (r1 - r0) * 0.6
            ray = np.array([math.cos(a), math.sin(a)])
            lines.append(np.array([c + r0 * ray, c + rr * ray]))
        self._strokes(e, cv, lines, taper=[e.get("w", 0.35), e.get("w", 0.35) * 0.4])
        if e.get("disc"):
            self._fill_shape(e, cv, c, {"shape": "disc", "r": float(e["disc"]), "fill": e.get("fill", 0.6)})

    def k_circuit(self, e, cv):
        rnd = random.Random(int(e.get("seed", 9)))
        (a0, b0), (a1, b1) = e["area"]
        lines = []
        nodes = []
        grid = float(e.get("grid", 0.12))
        for _ in range(int(e.get("count", 4))):
            p = [a0 + (a1 - a0) * rnd.random(), b0 + (b1 - b0) * rnd.random()]
            pts = [list(p)]
            for _k in range(rnd.randint(2, 4)):
                axis = rnd.randint(0, 1)
                span = (b1 - b0) if axis == 0 else (a1 - a0)
                p[1 - axis] = min(max(p[1 - axis] + rnd.choice((-1, 1)) * grid * span * rnd.randint(1, 3),
                                      min(a0, a1) if axis else min(b0, b1)), max(a0, a1) if axis else max(b0, b1))
                pts.append(list(p))
            lines.append(self.m(e["on"], pts))
            nodes += [lines[-1][0], lines[-1][-1]]
        self._strokes(e, cv, lines)
        for c in nodes:
            self._fill_shape(e, cv, c, {"shape": "disc", "r": float(e.get("node", 0.7)), "fill": 0.25,
                                        "rim": e.get("w", 0.35)})

    def k_claws(self, e, cv):
        p0 = self.m(e["on"], [e["from"]])[0]
        p1 = self.m(e["on"], [e["to"]])[0]
        n = int(e.get("count", 3))
        sp = float(e.get("spacing", 1.6)) * cv.unit
        curve = float(e.get("curve", 1.0)) * cv.unit
        v = p1 - p0
        L = float(np.hypot(*v))
        dvec = v / max(L, 1e-12)
        nrm = np.array([-dvec[1], dvec[0]])
        lines = []
        for k in range(n):
            off = (k - (n - 1) / 2) * sp
            t = np.linspace(0, 1, 16)
            pts = p0[None, :] + v[None, :] * t[:, None] + nrm[None, :] * (off + curve * np.sin(math.pi * t)[:, None])
            lines.append(pts)
        self._strokes(e, cv, lines, taper=e.get("taper", [e.get("w", 0.45), 0.1]))

    def k_stripes(self, e, cv):
        p0, p1 = np.asarray(e["from"], float), np.asarray(e["to"], float)
        n = int(e.get("count", 4))
        L = float(e.get("len", 6.0)) * cv.unit
        ang = math.radians(float(e.get("angle", 0)))
        lines = []
        for i in range(n):
            c = self.m(e["on"], [p0 + (p1 - p0) * i / max(1, n - 1)])[0]
            d = np.array([math.cos(ang), math.sin(ang)])
            lines.append(np.array([c - d * L / 2, c + d * L / 2]))
        for ln in lines:
            self._strokes(e, cv, [ln], taper=e.get("taper"))


def paint_design(charts, design, sex_name):
    """core and halo atlases (N, N) of one design on one model."""
    from .atlas import N
    p = Painter(charts, sex_name)
    canvases = p.paint(design)
    core = np.zeros((N, N))
    halo = np.zeros((N, N))
    for cv in canvases.values():
        r = cv.r
        core[r.ys, r.xs] = np.maximum(core[r.ys, r.xs], cv.core)
        halo[r.ys, r.xs] = np.maximum(halo[r.ys, r.xs], cv.halo)
    return core, halo
