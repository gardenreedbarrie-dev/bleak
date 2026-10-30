"""Original emblem shapes (CAFE.SPEC.md sections 5.5.1 and 5.5.2), as SVG paths in a 100 x 100 box (y down).

These are shapes defined here, not the Alliance or Horde logos: `lion_head` is a front-facing stylised mane disc
with ears and a muzzle, `tusk_crest` two curved tusks with leather wraps around a steaming cup on a saucer. Each
emblem is a list of layers (name, path, mode, height): mode "fill", "dark" (a recess) or ("stroke", width);
height drives the painted relief (render_relief).

Also here:
- the flavour glyphs of the syrup bottles (section 5.5.1): drop, flower, leaf, bean, berry, cinnamon, mint,
  swirl, plus cactus (the Orgrimmar cactus apple) and cream (the whipped-cream canister), in GLYPHS, rendered
  by paint2d.label; SYRUPS is the shelf order with each bottle's colour and glyph;
- LINE_ICONS: line art for chalkboards and plates (the family icons coffee, tea, shake, and line versions of
  lion_head and tusk_crest), rendered by line_mask and composited with font.chalk_mask or paint2d.paint_mask.
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
# tusk_crest: a tusk rising from the bottom centre up the left side, its tip curling in over the cup; the lit
# ridge along its outer curve; two leather wraps near its root
TUSK_L = "M47 94 C22 90 6 70 7 44 C8 26 16 12 28 6 C22 20 19 32 21 46 C23 64 32 76 50 82 Z"
RIDGE_L = "M40 89 C22 84 12 66 12 46 C12 32 17 20 24 11"
WRAP_L = "M24 79 L33 70 M30 85 L38 76"
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
        ("tusk_l", TUSK_L, "fill", 0.6),
        ("tusk_r", _mirror(TUSK_L), "fill", 0.6),
        ("ridge_l", RIDGE_L, ("stroke", 3.0), 0.78),
        ("ridge_r", _mirror(RIDGE_L), ("stroke", 3.0), 0.78),
        ("wrap_l", WRAP_L, ("stroke", 4.2), 0.42),
        ("wrap_r", _mirror(WRAP_L), ("stroke", 4.2), 0.42),
        ("saucer", "M20 86 C32 93 68 93 80 86 C68 81 32 81 20 86 Z", "fill", 0.66),
        ("cup", "M29 44 H71 L67 70 C65 79 58 83 50 83 C42 83 35 79 33 70 Z", "fill", 0.86),
        ("handle", "M68 50 C82 50 82 68 65 68", ("stroke", 5.0), 0.86),
        ("rim", "M29 44 H71", ("stroke", 3.2), 0.97),
        ("band", "M31.5 56 H68.5", ("stroke", 4.4), 0.4),
        ("steam", "M40 36 C36 29 44 25 40 16 M50 36 C46 28 54 24 50 12 M60 36 C56 29 64 25 60 16",
         ("stroke", 3.8), 0.6),
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


def _flower_path(petals=5, r_in=12.0, r_out=44.0, cx=50.0, cy=50.0, samples=60, phase=-math.pi / 2):
    """A flower outline: `petals` round petals between radius r_in and r_out."""
    pts = []
    for k in range(samples * petals // 5):
        a = phase + 2 * math.pi * k / (samples * petals // 5)
        f = abs(math.cos(petals * (a - phase) / 2.0)) ** 0.7
        r = r_in + (r_out - r_in) * f
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return "M" + " L".join("%.2f %.2f" % p for p in pts) + " Z"


def _circle(cx, cy, r):
    return "M%g %g a%g %g 0 1 0 %g 0 a%g %g 0 1 0 %g 0" % (cx - r, cy, r, r, 2 * r, r, r, -2 * r)


def _spiral_path(turns=2.25, r0=6.0, r1=40.0, cx=50.0, cy=52.0, samples=60):
    pts = []
    for k in range(samples + 1):
        f = k / float(samples)
        a = -math.pi / 2 + f * turns * 2 * math.pi
        r = r0 + (r1 - r0) * f
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return "M" + " L".join("%.2f %.2f" % p for p in pts)


def _ellipse_path(cx, cy, rx, ry, rot_deg=0.0, n=36):
    a0 = math.radians(rot_deg)
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        x, y = math.cos(a) * rx, math.sin(a) * ry
        pts.append((cx + x * math.cos(a0) - y * math.sin(a0), cy + x * math.sin(a0) + y * math.cos(a0)))
    return "M" + " L".join("%.2f %.2f" % p for p in pts) + " Z"


# The syrup bottles' flavour glyphs (section 5.5.1): one big shape each, read on a colour band at a glance.
# "fill" layers take the glyph colour, "dark" layers cut back to the band colour (paint2d.label).
GLYPHS = {
    "drop": [
        ("drop", "M50 6 C50 6 20 44 20 64 C20 82 33 94 50 94 C67 94 80 82 80 64 C80 44 50 6 50 6 Z", "fill", 0.8),
        ("shine", "M33 66 C33 56 38 48 44 40", ("stroke", 6.0), 0.3),
    ],
    "flower": [
        ("petals", _flower_path(5, 14.0, 46.0), "fill", 0.8),
        ("heart", _circle(50, 50, 11), "dark", 0.3),
    ],
    "bean": [
        ("bean", _ellipse_path(50, 50, 30, 42, 28), "fill", 0.8),
        ("crease", "M60 14 C42 32 60 64 40 86", ("stroke", 7.0), 0.3),
    ],
    "berry": [
        ("b1", _circle(36, 62, 18), "fill", 0.8),
        ("b2", _circle(64, 62, 18), "fill", 0.8),
        ("b3", _circle(50, 40, 18), "fill", 0.85),
        ("stem", "M50 22 C50 14 54 8 60 4", ("stroke", 5.0), 0.7),
        ("leaf", "M50 20 C38 8 24 10 18 18 C28 24 40 26 50 20 Z", "fill", 0.7),
        ("glint", _circle(44, 36, 4) + " " + _circle(30, 58, 4) + " " + _circle(58, 58, 4), "dark", 0.3),
    ],
    "cinnamon": [
        ("stick_a", "M16 72 L64 24", ("stroke", 20.0), 0.8),
        ("stick_b", "M36 88 L84 40", ("stroke", 18.0), 0.75),
        ("curl_a", "M64 24 m-5 0 a5 5 0 1 0 10 0 a4 4 0 1 0 -7 1", ("stroke", 3.6), 0.3),
        ("curl_b", "M84 40 m-4 0 a4 4 0 1 0 8 0 a3 3 0 1 0 -6 1", ("stroke", 3.4), 0.3),
        ("seam", "M24 70 L58 36 M44 86 L76 54", ("stroke", 3.0), 0.3),
    ],
    "mint": [
        ("leaf_a", "M50 94 C24 82 12 52 24 22 C30 36 46 40 52 56 C58 72 56 84 50 94 Z", "fill", 0.8),
        ("leaf_b", "M54 90 C64 70 66 48 84 30 C90 52 84 76 54 90 Z", "fill", 0.8),
        ("veins", "M48 90 C40 70 32 48 26 28 M60 82 C68 66 74 52 82 36", ("stroke", 4.0), 0.3),
    ],
    "swirl": [
        ("swirl", _spiral_path(), ("stroke", 12.0), 0.8),
    ],
    "cactus": [
        ("pad", _ellipse_path(38, 62, 24, 32, -18), "fill", 0.75),
        ("fruit", "M66 92 C52 92 46 80 48 66 C50 52 56 42 66 40 C76 42 82 52 84 66 C86 80 80 92 66 92 Z",
         "fill", 0.85),
        ("crown", "M58 42 L60 30 L66 38 L72 30 L74 42 Z", "fill", 0.85),
        ("spines", _circle(30, 50, 3.0) + " " + _circle(44, 60, 3.0) + " " + _circle(28, 72, 3.0) + " "
         + _circle(60, 62, 3.0) + " " + _circle(72, 72, 3.0) + " " + _circle(62, 82, 3.0), "dark", 0.3),
    ],
    "cream": [
        ("rosette", _flower_path(8, 30.0, 46.0, samples=40), "fill", 0.8),
        ("swirl", _spiral_path(1.6, 3.0, 22.0, 50.0, 50.0, 40), ("stroke", 5.5), 0.3),
    ],
}

# Section 5.8.1: the Stormwind rack's bottles in shelf order (the Orgrimmar rack swaps berry for the two-tone
# cactus apple, 88C070 / D46A8C). key: (colour, glyph, second colour or None).
SYRUPS = [
    ("honey", "E0A030", "drop", None), ("vanilla", "F0E6C8", "flower", None), ("caramel", "A0602A", "swirl", None),
    ("cinnamon", "B5502A", "cinnamon", None), ("chocolate", "4A2A1A", "bean", None),
    ("berry", "D46A8C", "berry", None), ("mint", "7FD1B9", "mint", None), ("cream", "FFFFFF", "cream", None),
]
SYRUPS_ORG = [row if row[0] != "berry" else ("cactus", "88C070", "cactus", "D46A8C") for row in SYRUPS]

# Line art for chalkboards and plates: (path, mode) with mode ("stroke", width) or "fill" (dots, eyes).
LINE_ICONS = {
    "coffee": [
        ("M20 82 C32 90 68 90 80 82", ("stroke", 5.0)),
        ("M26 42 H74 L70 68 C68 77 60 81 50 81 C40 81 32 77 30 68 Z", ("stroke", 5.0)),
        ("M72 48 C86 48 86 66 69 66", ("stroke", 5.0)),
        ("M40 34 C36 26 46 22 40 12 M54 34 C50 26 60 22 54 10", ("stroke", 4.5)),
    ],
    "tea": [
        ("M50 92 C18 74 16 38 50 10 C84 38 82 74 50 92 Z", ("stroke", 5.0)),
        ("M50 92 V22 M50 66 L36 54 M50 66 L64 54 M50 46 L39 37 M50 46 L61 37", ("stroke", 4.0)),
    ],
    "shake": [
        ("M30 34 H70 L63 90 H37 Z", ("stroke", 5.0)),
        ("M28 34 C26 18 40 12 50 18 C60 12 74 18 72 34", ("stroke", 5.0)),
        ("M58 22 L72 4", ("stroke", 5.0)),
        ("M33 52 H67", ("stroke", 3.5)),
        (_circle(44, 12, 6), "fill"),
    ],
}


def _line_from_emblem(name, strokes, fills, width):
    """Line art from an emblem's own paths: the outlines of `strokes` layers and the fills of `fills`."""
    out = []
    for lname, d, mode, _h in EMBLEMS[name]:
        if lname in strokes:
            out.append((d, ("stroke", mode[1] if isinstance(mode, tuple) else width)))
        elif lname in fills:
            out.append((d, "fill"))
    return out


def layer_masks(name, w, h, inset=0.0, table=None):
    """{layer name: (Mask, mode, height)} for an emblem (or a glyph, with table=GLYPHS) scaled into w x h."""
    s = min(w, h) / (100.0 + 2 * inset)
    ox = (w - 100 * s) / 2
    oy = (h - 100 * s) / 2
    out = []
    for lname, d, mode, height in (table or EMBLEMS)[name]:
        m = R.Mask(w, h)
        polys = R.xform_polys(R.parse(d), s, s, ox, oy)
        if isinstance(mode, tuple):
            R.stroke(m, polys, mode[1] * s)
        else:
            R.fill(m, polys)
        out.append((lname, m, mode, height))
    return out


def silhouette(name, w, h):
    """Union of every layer of an emblem, or of a flavour glyph."""
    table = EMBLEMS if name in EMBLEMS else GLYPHS
    m = R.Mask(w, h)
    for _ln, lm, _mode, _hh in layer_masks(name, w, h, table=table):
        m.max_with(lm)
    return m


def line_mask(name, w, h, width=None, inset=4.0):
    """Coverage of a LINE_ICONS entry scaled into a w x h box; width (in 100-unit icon space) overrides every
    stroke width, for a heavier chalk line."""
    s = min(w, h) / (100.0 + 2 * inset)
    ox = (w - 100 * s) / 2
    oy = (h - 100 * s) / 2
    m = R.Mask(w, h)
    for d, mode in LINE_ICONS[name]:
        polys = R.xform_polys(R.parse(d), s, s, ox, oy)
        if mode == "fill":
            R.fill(m, polys)
        else:
            R.stroke(m, polys, (width or mode[1]) * s)
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


# The tea leaf glyph is the family icon's leaf; the line versions of the two crests come from their own paths.
GLYPHS["leaf"] = EMBLEMS["leaf"]
LINE_ICONS["lion_head"] = _line_from_emblem("lion_head", ("mane", "face", "ear_l", "ear_r", "mouth", "brow_l",
                                                          "brow_r"), ("eye_l", "eye_r", "nose"), 3.5)
LINE_ICONS["tusk_crest"] = _line_from_emblem("tusk_crest", ("tusk_l", "tusk_r", "saucer", "cup", "handle", "steam"),
                                             (), 3.5)
