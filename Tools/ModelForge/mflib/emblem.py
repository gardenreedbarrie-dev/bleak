"""Original emblem shapes (CAFE.SPEC.md section 5.5.2), as SVG paths in a 100 x 100 box (y down).

These are shapes defined here, not the Alliance or Horde logos: `lion_head` is a front-facing stylised mane disc
with ears and a muzzle, `tusk_crest` two curved tusks around a steaming cup. Each emblem is a list of layers
(name, path, mode, height): mode "fill" or ("stroke", width); height drives the painted relief (render_relief).
"""

import math

from . import raster2d as R
from . import tex as T


def _polar_path(n, r_lo, r_hi, cx=50.0, cy=52.0, samples=10, phase=-math.pi / 2, curl=0.72):
    """A tufted ring: n flame-shaped tufts between radius r_lo (valleys) and r_hi (tips)."""
    pts = []
    for i in range(n):
        for k in range(samples):
            x = k / samples
            f = (x / curl) ** 1.15 if x < curl else (1.0 - (x - curl) / (1.0 - curl)) ** 0.75
            a = phase + 2 * math.pi * (i + x) / n
            r = r_lo + (r_hi - r_lo) * f
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return "M" + " L".join("%.2f %.2f" % p for p in pts) + " Z"


def _gear_path(teeth, r_out, r_in, cx=50.0, cy=50.0, hole=0.0):
    pts = []
    for i in range(teeth):
        a0 = 2 * math.pi * i / teeth
        step = 2 * math.pi / teeth
        for frac, r in ((0.0, r_in), (0.12, r_out), (0.45, r_out), (0.57, r_in)):
            a = a0 + step * frac
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    d = "M" + " L".join("%.2f %.2f" % p for p in pts) + " Z"
    return d


def _mirror(d):
    """Mirrors an absolute M/L/C/H/V/Z path about x = 50."""
    toks = d.replace(",", " ").split()
    out = []
    i = 0
    cmd = None
    while i < len(toks):
        t = toks[i]
        if t[0].isalpha():
            cmd = t[0]
            rest = t[1:]
            out.append(cmd)
            if rest:
                toks.insert(i + 1, rest)
            i += 1
            continue
        if cmd in ("M", "L", "C"):
            x, y = float(toks[i]), float(toks[i + 1])
            out.append("%g %g" % (100 - x, y))
            i += 2
        elif cmd == "H":
            out.append("%g" % (100 - float(t)))
            i += 1
        elif cmd == "V":
            out.append(t)
            i += 1
        else:
            i += 1
    return " ".join(out)


EAR_L = "M27 36 C20 26 22 14 31 12 C38 12 43 18 42 27 Z"
EAR_L_IN = "M30 30 C27 24 28 18 32 17 C36 17 38 21 37 26 Z"
EYE_L = "M32 47 C36 43 42 43 46 48 C42 51 36 51 32 47 Z"
BROW_L = "M30 42 C36 37 43 38 48 44"

EMBLEMS = {
    "lion_head": [
        ("mane", _polar_path(14, 34.0, 48.0), "fill", 0.45),
        ("mane_inner", _polar_path(14, 29.0, 38.0, phase=-math.pi / 2 + 0.22), "fill", 0.58),
        ("ear_l", EAR_L, "fill", 0.62),
        ("ear_r", _mirror(EAR_L), "fill", 0.62),
        ("ear_l_in", EAR_L_IN, "dark", 0.4),
        ("ear_r_in", _mirror(EAR_L_IN), "dark", 0.4),
        ("face", "M50 20 C64 20 76 26 78 40 C80 54 74 66 64 76 C58 82 54 86 50 86 C46 86 42 82 36 76 "
                 "C26 66 20 54 22 40 C24 26 36 20 50 20 Z", "fill", 0.78),
        ("bridge", "M45 44 L55 44 L57 62 L43 62 Z", "fill", 0.9),
        ("muzzle_l", "M37 71 a7 7 0 1 0 14 0 a7 7 0 1 0 -14 0", "fill", 0.95),
        ("muzzle_r", "M49 71 a7 7 0 1 0 14 0 a7 7 0 1 0 -14 0", "fill", 0.95),
        ("brow_l", BROW_L, ("stroke", 3.2), 0.3),
        ("brow_r", _mirror(BROW_L), ("stroke", 3.2), 0.3),
        ("eye_l", EYE_L, "dark", 0.25),
        ("eye_r", _mirror(EYE_L), "dark", 0.25),
        ("nose", "M42 60 C46 58 54 58 58 60 C57 66 53 69 50 69 C47 69 43 66 42 60 Z", "dark", 0.3),
        ("mouth", "M41 79 C45 82 55 82 59 79 M50 69 V76", ("stroke", 2.6), 0.3),
    ],
    "tusk_crest": [
        ("tusk_l", "M44 90 C20 82 8 58 16 22 C22 48 30 66 48 78 Z", "fill", 0.7),
        ("tusk_r", "M56 90 C80 82 92 58 84 22 C78 48 70 66 52 78 Z", "fill", 0.7),
        ("cup", "M32 46 H68 L64 72 C62 80 56 82 50 82 C44 82 38 80 36 72 Z", "fill", 0.85),
        ("handle", "M66 52 C78 52 78 66 64 66", ("stroke", 4.0), 0.85),
        ("steam", "M42 38 C38 32 46 28 42 20 M50 38 C46 32 54 28 50 18 M58 38 C54 32 62 28 58 20",
         ("stroke", 3.2), 0.6),
    ],
    "cup": [
        ("saucer", "M18 80 C30 88 70 88 82 80 C70 76 30 76 18 80 Z", "fill", 0.6),
        ("cup", "M26 44 H74 L70 70 C68 78 60 82 50 82 C40 82 32 78 30 70 Z", "fill", 0.85),
        ("handle", "M72 50 C86 50 86 66 70 66", ("stroke", 5.0), 0.85),
        ("steam", "M40 36 C36 28 46 24 40 14 M54 36 C50 28 60 24 54 12", ("stroke", 4.0), 0.6),
    ],
    "leaf": [
        ("leaf", "M50 90 C18 72 16 36 50 10 C84 36 82 72 50 90 Z", "fill", 0.8),
        ("vein", "M50 86 V20 M50 64 L36 52 M50 64 L64 52 M50 46 L38 36 M50 46 L62 36", ("stroke", 3.0), 0.4),
    ],
    "glass": [
        ("glass", "M32 30 H68 L62 88 H38 Z", "fill", 0.75),
        ("cream", "M30 32 C30 16 70 16 70 32 Z", "fill", 0.9),
        ("straw", "M58 22 L70 4", ("stroke", 5.0), 0.85),
        ("cherry", "M44 14 a6 6 0 1 0 12 0 a6 6 0 1 0 -12 0", "fill", 0.95),
    ],
    "gear": [
        ("gear", _gear_path(12, 46, 36), "fill", 0.75),
        ("hub", "M36 50 a14 14 0 1 0 28 0 a14 14 0 1 0 -28 0", "dark", 0.3),
    ],
    "bolt": [
        ("bolt", "M58 6 L24 56 H46 L38 94 L76 40 H54 Z", "fill", 0.85),
    ],
}


def layer_masks(name, w, h, inset=0.0):
    """{layer name: (Mask, mode, height)} for an emblem scaled into a w x h box."""
    s = min(w, h) / (100.0 + 2 * inset)
    ox = (w - 100 * s) / 2
    oy = (h - 100 * s) / 2
    out = []
    for lname, d, mode, height in EMBLEMS[name]:
        m = R.Mask(w, h)
        polys = R.xform_polys(R.parse(d), s, s, ox, oy)
        if isinstance(mode, tuple):
            R.stroke(m, polys, mode[1] * s)
        else:
            R.fill(m, polys)
        out.append((lname, m, mode, height))
    return out


def silhouette(name, w, h):
    m = R.Mask(w, h)
    for _ln, lm, _mode, _hh in layer_masks(name, w, h):
        m.max_with(lm)
    return m


def render_relief(name, w, h, palette, light=(-0.55, -0.75, 0.6), strength=2.2, blur_px=None, outline=True):
    """A painted relief: per-texel height from the layers (dark layers are recesses), blurred, shaded by a
    light from the top-left; colours from palette {"base", "raised", "top", "dark", "outline"}.
    Returns an Img whose alpha is the emblem's coverage."""
    layers = layer_masks(name, w, h)
    hmap = [0.0] * (w * h)
    col = [None] * (w * h)
    cov = [0.0] * (w * h)
    for lname, m, mode, height in layers:
        dark = mode == "dark" or (isinstance(mode, tuple) and height < 0.5)
        c = palette["dark"] if dark else (palette["top"] if height >= 0.88 else (
            palette["raised"] if height >= 0.6 else palette["base"]))
        for i, a in enumerate(m.a):
            if a <= 0:
                continue
            hmap[i] = hmap[i] + (height - hmap[i]) * a
            col[i] = c if col[i] is None else T.mix(col[i], c, a)
            cov[i] = max(cov[i], a)
    hm = R.Mask(w, h)
    hm.a = hmap
    hb = R.blur(hm, blur_px if blur_px is not None else max(1, w // 64))
    lx, ly, lz = light
    ln = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / ln, ly / ln, lz / ln
    img = T.Img(w, h, (0, 0, 0, 0))
    sil = R.Mask(w, h)
    sil.a = cov
    ring = R.dilate(sil, max(1, w // 96)) if outline else None
    for y in range(h):
        for x in range(w):
            i = y * w + x
            gx = (hb.get(x + 1, y) - hb.get(x - 1, y)) * 0.5 * w / 16.0
            gy = (hb.get(x, y + 1) - hb.get(x, y - 1)) * 0.5 * h / 16.0
            nx, ny, nz = -gx * strength, -gy * strength, 1.0
            nn = math.sqrt(nx * nx + ny * ny + nz * nz)
            d = (nx * lx + ny * ly + nz * lz) / nn
            k = 0.55 + 0.75 * max(0.0, d)
            if col[i] is not None:
                c = T.light(col[i], k)
                img.set(x, y, c, cov[i])
            if ring is not None and ring.a[i] > cov[i]:
                a = ring.a[i]
                if col[i] is None:
                    img.set(x, y, palette.get("outline", palette["dark"]), a)
                else:
                    img.blend(x, y, palette.get("outline", palette["dark"]), (a - cov[i]))
                    img.a[i] = max(img.a[i], a)
    return img
