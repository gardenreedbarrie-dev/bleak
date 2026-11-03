"""The café spell icons of CAFE.SPEC.md section 5.7: 64 x 64 DXT1 `Interface\\Icons\\BH_Cafe_<Name>.blp`, used by
the SpellIcon rows 19300-19313 (19314-19319 are spare).

Full-bleed painted objects, as the stock icons are: the object on a coloured radial gradient, the important
content inside the central 85 % (UIs crop about 7 % per edge), a 2 px darkened edge and no baked frame (the
action button, the spellbook and the buff frame draw their own border). Each icon is one of:

- a built café model ("model"), rendered by the preview rasterizer from a front three-quarter view with its baked
  atlas under a warm key light from the upper left, framed on the whole model or on a box of it (the kettle on
  its stove, a stretch of counter with the bell and the cake stand);
- a small mesh scene ("mesh", the teacup), flat-coloured and lit the same way;
- a painted relief ("paint": the apron, the crown, the speed bolt), the emblem.render_relief shading with a
  colour per layer;
- and painted overlays on top of the first two (the tea leaf and its steam, the sleepy "Zz").

The stations show their Stormwind piece (one SpellIcon serves both cafés); everything is drawn at 4 x (256 px,
2 x supersampled) and box-filtered to 64, so the result is deterministic and byte-identical between runs.
"""

import math
import os

import blpconvert as BC  # noqa: E402  Tools/BlpConvert (read-only)

from . import emblem as E
from . import font as F
from . import geom as G
from . import kit as K
from . import mips as MP
from . import paint2d as P2
from . import raster2d as R
from . import render as RD
from . import tex as T

SIZE = 64
FILL = 0.85          # the important content stays inside the central 85 % (section 5.7)
EDGE = (0.55, 0.8)   # the outer two rows of pixels are darkened by these factors
FOV = 28.0

# The key light: from the camera's upper left, a little warm; a high ambient so the shadow side keeps its colour.
LIGHT = RD.Lighting((0.5, 0.5, 0.56), (0.9, 0.84, 0.74), G.norm((-0.55, 0.15, -0.82)), None,
                    ((0.3, 0.3, 0.3), (0.3, 0.3, 0.3)), "icon")


def _c(h):
    return T.hexc(h)


# --------------------------------------------------------------------------------------------- shapes

# Painted reliefs in a 100 x 100 box (y down): (path, mode, height, colour). mode "fill" or ("stroke", width);
# height drives the shading (0.2 low, 1.0 high), as in emblem.render_relief.
CROWN = [
    ("M14 72 L20 28 L36 52 L50 18 L64 52 L80 28 L86 72 Z", "fill", 0.7, _c("E0A82C")),
    ("M14 66 L86 66 L84 86 L16 86 Z", "fill", 0.9, _c("F0C040")),
    ("M14 66 L86 66", ("stroke", 2.4), 1.0, _c("FFE8A0")),
    (E._circle(20, 25, 6), "fill", 1.0, _c("F8DC80")),
    (E._circle(50, 15, 7), "fill", 1.0, _c("F8DC80")),
    (E._circle(80, 25, 6), "fill", 1.0, _c("F8DC80")),
    (E._circle(32, 76, 5), "fill", 1.0, _c("C8283A")),
    (E._circle(50, 76, 6), "fill", 1.0, _c("2E5EC8")),
    (E._circle(68, 76, 5), "fill", 1.0, _c("C8283A")),
    (E._circle(50, 48, 6.5), "fill", 1.0, _c("2E9E5A")),
]

# The barista's apron (the On Shift aura): a coffee-brown bib apron with cream straps and ties, a pocket and a
# cream cup on the bib.
APRON = [
    ("M38 24 C36 6 64 6 62 24", ("stroke", 5.5), 0.5, _c("E8D8B0")),
    ("M20 52 C8 56 6 68 12 80", ("stroke", 5.0), 0.5, _c("E8D8B0")),
    ("M80 52 C92 56 94 68 88 80", ("stroke", 5.0), 0.5, _c("E8D8B0")),
    ("M34 20 L66 20 L68 44 C80 46 84 50 84 56 L80 92 C68 97 32 97 20 92 L16 56 C16 50 20 46 32 44 Z",
     "fill", 0.7, _c("7A4A2A")),
    ("M30 62 L70 62 L68 84 L32 84 Z", "fill", 0.85, _c("8E5A34")),
    ("M30 62 L70 62", ("stroke", 2.2), 1.0, _c("E8D8B0")),
    ("M50 62 L50 84", ("stroke", 1.6), 0.3, _c("4A2A14")),
    ("M41 27 L59 27 L57 40 C55 43 45 43 43 40 Z", "fill", 1.0, _c("F2E6C8")),
    ("M58 30 C64 30 64 37 58 37", ("stroke", 2.6), 1.0, _c("F2E6C8")),
]

# Café Sprint (the hidden run-speed helper): a golden bolt with motion streaks behind it.
BOLT = [
    ("M8 34 H34", ("stroke", 5.0), 0.4, _c("F4F0E0")),
    ("M4 50 H28", ("stroke", 5.0), 0.4, _c("F4F0E0")),
    ("M10 66 H32", ("stroke", 5.0), 0.4, _c("F4F0E0")),
    ("M62 4 L28 56 L50 56 L38 96 L82 38 L58 38 L72 4 Z", "fill", 0.9, _c("F6C230")),
    ("M62 4 L28 56 L50 56", ("stroke", 2.0), 1.0, _c("FFF0A0")),
]

# The tea leaf over the teacup and its steam (Tea), and the sleepy steam of the cold cup (Tired).
LEAF = [
    ("M14 86 C10 50 38 18 88 12 C84 58 60 88 14 86 Z", "fill", 0.8, _c("5AAE3A")),
    ("M14 86 C34 64 56 40 82 18", ("stroke", 3.2), 0.3, _c("2E6A1C")),
    ("M40 62 L34 44 M56 46 L52 30 M42 62 L60 62 M58 44 L72 42", ("stroke", 2.2), 0.4, _c("3A7E26")),
]
STEAM = [
    ("M34 96 C14 80 44 66 30 48 C18 32 40 22 30 4", ("stroke", 6.0), 0.6, _c("F8F8F4")),
    ("M64 96 C46 82 78 68 64 50 C52 36 74 26 66 10", ("stroke", 5.0), 0.6, _c("F8F8F4")),
]


def _tea_scene():
    """The Tea icon's mesh scene: a porcelain teacup of amber tea on its saucer (kit.cup), flat-coloured."""
    parts = K.cup(top_r=0.075, height=0.08, saucer_r=0.13, sides=24, fill=0.84)
    cols = {"cup": _c("F4F0E6"), "handle": _c("F4F0E6"), "saucer": _c("E8E2D2"), "coffee": _c("B4661C")}
    band = G.lathe([(0.0745, 0.07), (0.0782, 0.082), (0.0778, 0.086), (0.0742, 0.074)], 24, name="band")
    out = [(m, cols[k]) for k, m in parts.items() if not k.startswith("at_")]
    out.append((band, _c("2E4E8C")))   # a royal-blue band under the rim
    return out


# ------------------------------------------------------------------------------------------ the icons

# (SpellIcon id, name, spec). The section 5.7 table, in order. Spec keys:
#   bg: (centre colour, edge colour) of the radial background;
#   model: the café model to render, with yaw / pitch (degrees) and box ((lo), (hi)) to frame instead of the
#          whole model, particles (draw its emitters);
#   mesh: a function returning [(Mesh, colour)];
#   paint: relief layers drawn in the central 85 %;
#   over: [(layers, (x0, y0, x1, y1) as fractions of the icon, alpha)] painted on top;
#   zz: draw the sleepy "Zz";
#   rim: a warm rim light along the object's top and right silhouette, so it separates from the background;
#   light: a render.PRESETS name instead of the icon light.
ICONS = [
    # the five station icons that were all brown (Grinder, Espresso, Kettle, Shelf, Coffee) each get their own
    # background hue, so they stay apart on an action bar: teal, royal blue, warm orange, plum, cream
    (19300, "Grinder", {"model": "GrinderSW", "yaw": 26, "pitch": 14, "bg": ("46B4AA", "0A3436"), "rim": True}),
    # Espresso: cropped tight on one group (its lever, the portafilter and the cup under the spout), which turned
    # to mush at 64 px when the whole machine was framed
    (19301, "Espresso", {"model": "EspressoSW", "yaw": 24, "pitch": 12,
                         "box": ((0.02, 0.12, 0.13), (0.5, 0.47, 0.76)), "bg": ("5A8AD8", "0E1C4A"),
                         "rim": True}),
    (19302, "Kettle", {"model": "KettleStoveSW", "yaw": 30, "pitch": 22, "particles": True,
                       "box": ((-0.24, -0.3, 0.6), (0.34, 0.26, 1.16)), "bg": ("E89A48", "5A200C")}),
    (19303, "ColdBox", {"model": "ColdBoxSW", "yaw": 28, "pitch": 26, "bg": ("9AD8F0", "1E4A78")}),
    (19304, "Blender", {"model": "BlenderSW", "yaw": 26, "pitch": 14, "bg": ("F0A8C8", "6A2048")}),
    (19305, "Shelf", {"model": "SyrupRackSW", "yaw": 24, "pitch": 12,
                      "box": ((-0.2, -0.46, 0.04), (0.22, 0.42, 0.86)), "bg": ("B070B8", "2A0C34")}),
    (19306, "Counter", {"model": "CounterSW", "yaw": 30, "pitch": 18,
                        "box": ((-0.1, 0.25, 0.95), (0.42, 0.95, 1.36)), "bg": ("B8C8E0", "1E2E58")}),
    (19307, "Coffee", {"model": "CupSW", "yaw": 26, "pitch": 30, "particles": True, "bg": ("F2DEB4", "7A5432")}),
    (19308, "Tea", {"mesh": _tea_scene, "yaw": 26, "pitch": 30, "bg": ("A8D888", "1E4A1E"),
                    "over": [(STEAM, (0.2, 0.0, 0.62, 0.42), 0.75), (LEAF, (0.56, 0.08, 0.95, 0.47), 1.0)]}),
    (19309, "Shake", {"model": "ShakeGlass", "yaw": 26, "pitch": 14, "bg": ("FFC8E0", "8A2858")}),
    (19310, "Shift", {"paint": APRON, "bg": ("78A8E0", "142A5A")}),
    (19311, "Tired", {"model": "CupSW", "yaw": 26, "pitch": 30, "light": "sw_night", "zz": True,
                      "bg": ("6A6A9A", "141428")}),
    (19312, "Crown", {"paint": CROWN, "bg": ("D04A3A", "4A0A10")}),
    (19313, "Speed", {"paint": BOLT, "bg": ("F0884A", "6A1A0A")}),
]
SPARE = range(19314, 19320)


def icon_names():
    return [name for _i, name, _s in ICONS]


def models_needed():
    """The café models the icons render (built first by `modelforge.py icons` when missing)."""
    return sorted({s["model"] for _i, _n, s in ICONS if "model" in s})


def client_path(name):
    return "Interface\\Icons\\BH_Cafe_%s.blp" % name


# ------------------------------------------------------------------------------------------- painting

def _background(w, h, bg):
    """A radial gradient: the centre colour at the middle (a little above it), the edge colour at the corners."""
    c0, c1 = _c(bg[0]), _c(bg[1])
    img = T.Img(w, h, (0.0, 0.0, 0.0, 1.0))
    for y in range(h):
        for x in range(w):
            dx = (x + 0.5) / w - 0.5
            dy = (y + 0.5) / h - 0.44
            k = T.smoothstep(0.0, 0.74, math.sqrt(dx * dx + dy * dy) * 1.18)
            img.set(x, y, T.mix(c0, c1, k), 1.0)
    return img


def relief(layers, w, h, light=(-0.55, -0.75, 0.6), strength=2.4, outline=_c("1A0E06")):
    """A painted relief like emblem.render_relief, with a colour per layer: [(path, mode, height, colour)] in a
    100-unit box scaled into w x h. Returns an Img whose alpha is the coverage."""
    s = min(w, h) / 100.0
    ox, oy = (w - 100 * s) / 2, (h - 100 * s) / 2
    n = w * h
    hmap = [0.0] * n
    col = [None] * n
    cov = [0.0] * n
    for d, mode, height, colour in layers:
        m = R.Mask(w, h)
        polys = R.xform_polys(R.parse(d), s, s, ox, oy)
        if isinstance(mode, tuple):
            R.stroke(m, polys, mode[1] * s)
        else:
            R.fill(m, polys)
        for i, a in enumerate(m.a):
            if a <= 0:
                continue
            hmap[i] += (height - hmap[i]) * a
            col[i] = colour if col[i] is None else T.mix(col[i], colour, a)
            cov[i] = max(cov[i], a)
    hm = R.Mask(w, h)
    hm.a = hmap
    hb = R.blur(hm, max(1, w // 48))
    ln = math.sqrt(sum(v * v for v in light))
    lx, ly, lz = (v / ln for v in light)
    sil = R.Mask(w, h)
    sil.a = cov
    ring = R.dilate(sil, max(1, w // 80))
    img = T.Img(w, h, (0.0, 0.0, 0.0, 0.0))
    for y in range(h):
        for x in range(w):
            i = y * w + x
            gx = (hb.get(x + 1, y) - hb.get(x - 1, y)) * 0.5 * w / 16.0
            gy = (hb.get(x, y + 1) - hb.get(x, y - 1)) * 0.5 * h / 16.0
            nx, ny, nz = -gx * strength, -gy * strength, 1.0
            nn = math.sqrt(nx * nx + ny * ny + nz * nz)
            k = 0.55 + 0.75 * max(0.0, (nx * lx + ny * ly + nz * lz) / nn)
            # a soft top-to-bottom falloff, as the bake's gradient (section 5.5)
            k *= 1.08 - 0.22 * (y / float(h))
            if col[i] is not None:
                img.set(x, y, T.light(col[i], k), cov[i])
            if ring.a[i] > cov[i]:
                a = ring.a[i]
                if col[i] is None:
                    img.set(x, y, outline, a)
                else:
                    img.blend(x, y, outline, a - cov[i])
                    img.a[i] = max(img.a[i], a)
    return img


def _paint_over(img, layers, rect, alpha=1.0):
    x0, y0, x1, y1 = rect
    w, h = int(round((x1 - x0) * img.w)), int(round((y1 - y0) * img.h))
    rel = relief(layers, w, h)
    rel.a = [a * alpha for a in rel.a]
    P2.composite(img, rel, int(round(x0 * img.w)), int(round(y0 * img.h)))


def _zz(img):
    """The sleepy "Zz" of Tired: two cream capitals with a dark outline, top right."""
    for text, cap, fx, fy in (("Z", 0.2, 0.58, 0.08), ("z", 0.15, 0.8, 0.02)):
        c = cap * img.h
        m = F.vector_mask(text.upper(), c, weight=0.2, serif=False)
        F.two_tone(img, m, _c("F4ECD0"), _c("1A1428"), int(fx * img.w), int(fy * img.h),
                   outline_px=max(1, img.w // 64), shadow=(0, 0))


# ------------------------------------------------------------------------------------------ rendering

def _points(m, box):
    if box:
        lo, hi = box
        return [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    verts = m["vertices"]
    step = max(1, len(verts) // 4000)
    return [v[0] for v in verts[::step]]


def _camera(points, yaw, pitch, size, ss):
    """A camera from the front three-quarter view whose window frames `points` in the central FILL of a square
    `size` x `size` image."""
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    c = tuple((lo[i] + hi[i]) / 2 for i in range(3))
    r = max(0.05, max(G.length(G.sub(p, c)) for p in points))
    dist = r / math.sin(math.radians(FOV / 2)) * 1.1
    ya, pa = math.radians(yaw), math.radians(pitch)
    eye = (c[0] + math.cos(ya) * math.cos(pa) * dist, c[1] + math.sin(ya) * math.cos(pa) * dist,
           c[2] + math.sin(pa) * dist)
    ref = RD.Camera(eye, c, FOV, 1000, 1000, 1)
    xs, ys = [], []
    for p in points:
        v = ref.view(p)
        if v[2] > 0.05:
            sx, sy, _z = ref.project(v)
            xs.append(sx)
            ys.append(sy)
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    k = size * FILL / span
    cx, cy = (min(xs) + max(xs)) / 2 * k, (min(ys) + max(ys)) / 2 * k
    wx, wy = int(round(cx - size / 2)), int(round(cy - size / 2))
    return RD.Camera(eye, c, FOV, 1000 * k, 1000 * k, ss, (wx, wy, wx + size, wy + size))


def _draw_3d(spec, models, textures, size, ss):
    """The rendered object over the background, as an Img of size x size."""
    if "model" in spec:
        m = models[spec["model"]]
        cam = _camera(_points(m, spec.get("box")), spec["yaw"], spec["pitch"], size, ss)
    else:
        scene = spec["mesh"]()
        pts = [p for mesh, _c0 in scene for p in mesh.p]
        cam = _camera(pts, spec["yaw"], spec["pitch"], size, ss)
    lit = RD.PRESETS[spec["light"]] if spec.get("light") else LIGHT
    lit = RD.Lighting(lit.ambient, lit.diffuse, lit.direction, None, lit.sky, lit.name)
    frame = RD.Frame(cam, lit, (0.0, 0.0, 0.0))
    bg = _background(frame.w, frame.h, spec["bg"])
    frame.r, frame.g, frame.b = list(bg.r), list(bg.g), list(bg.b)
    if "model" in spec:
        ds = RD.model_drawables(m, textures)
        if spec.get("particles"):
            ds += RD.particle_drawables(m, textures, None, cam)
    else:
        ds = [RD.mesh_drawable(mesh, col) for mesh, col in scene]
    RD.draw_scene(frame, ds)
    if spec.get("rim"):
        _rim_light(frame)
    img = T.Img(frame.w, frame.h)
    img.r, img.g, img.b = frame.r, frame.g, frame.b
    img.a = [1.0] * (frame.w * frame.h)
    return _shrink(img, size), frame.coverage_bbox()


def _rim_light(frame, color=(1.0, 0.95, 0.82), k=0.6):
    """A rim light from behind, upper right: every covered pixel within about 1.5 icon pixels of the background
    toward the top or the right is brightened toward a warm white, strongest at the silhouette."""
    w, h, mask = frame.w, frame.h, frame.mask
    reach = max(2, w // 40)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if not mask[i]:
                continue
            best = 0.0
            for d in range(1, reach + 1):
                for dx, dy in ((d, 0), (0, -d), (d, -d)):
                    X, Y = x + dx, y + dy
                    if X >= w or Y < 0 or not mask[Y * w + X]:
                        best = 1.0 - (d - 1) / float(reach)
                        break
                if best:
                    break
            if best:
                f = k * best
                frame.r[i] += (color[0] - frame.r[i]) * f
                frame.g[i] += (color[1] - frame.g[i]) * f
                frame.b[i] += (color[2] - frame.b[i]) * f


def _shrink(img, size):
    """Box filter to size x size (img is a whole multiple of it)."""
    k = img.w // size
    if k <= 1:
        return img
    out = T.Img(size, size)
    inv = 1.0 / (k * k)
    for y in range(size):
        for x in range(size):
            r = g = b = 0.0
            for dy in range(k):
                base = (y * k + dy) * img.w + x * k
                for dx in range(k):
                    r += img.r[base + dx]
                    g += img.g[base + dx]
                    b += img.b[base + dx]
            out.set(x, y, (r * inv, g * inv, b * inv), 1.0)
    return out


def _edge(img):
    """Darkens the outer EDGE rows (section 5.7: at most a 1-2 px darkened edge, no frame)."""
    w, h = img.w, img.h
    for y in range(h):
        for x in range(w):
            d = min(x, y, w - 1 - x, h - 1 - y)
            if d < len(EDGE):
                i = y * w + x
                k = EDGE[d]
                img.r[i] *= k
                img.g[i] *= k
                img.b[i] *= k
    return img


def render_icon(name, models, textures, size=256):
    """The icon `name` as a SIZE x SIZE Img, drawn at `size` px (a multiple of SIZE). models: {model name: parsed
    m2}; textures: a render.TextureSet over the built files. Also returns the object's bbox at `size` px (the
    covered pixels of the 3D object, or of the painted relief), for the 85 % check."""
    spec = next(s for _i, n, s in ICONS if n == name)
    if "paint" in spec:
        img = _background(size, size, spec["bg"])
        inner = int(round(size * FILL))
        rel = relief(spec["paint"], inner, inner)
        off = (size - inner) // 2
        P2.composite(img, rel, off, off)
        bb = _alpha_bbox(rel)
        bbox = (bb[0] + off, bb[1] + off, bb[2] + off, bb[3] + off) if bb else None
    else:
        img, bb = _draw_3d(spec, models, textures, size, 2)
        bbox = tuple(v // 2 for v in bb) if bb else None
    for layers, rect, alpha in spec.get("over", ()):
        _paint_over(img, layers, rect, alpha)
    if spec.get("zz"):
        _zz(img)
    return _edge(_shrink(img, SIZE)), bbox


def _alpha_bbox(img, thr=0.05):
    xs = [i % img.w for i, a in enumerate(img.a) if a > thr]
    ys = [i // img.w for i, a in enumerate(img.a) if a > thr]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def write_icon(img, path):
    """The DXT1 BLP with its full mip chain (64 x 64: 7 levels)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    MP.write(path, img.to_image(), "dxt1")
    return path


def sheet(entries, path):
    """A preview sheet: every icon (entries [(id, name, 64 px PNG path)]) at 2 x, labelled with its SpellIcon id
    and name."""
    from . import preview as PV
    cells = []
    for icon_id, name, png in entries:
        big = os.path.splitext(png)[0] + "_x2.png"
        BC.write_png(big, PV.upscale(BC.read_png(png), 2))
        cells.append((big, "%d %s" % (icon_id, name)))
    PV.contact_sheet(cells, path, 7, (150, 160), "Cafe icons (section 5.7), 64 px shown at 2x")
    return path
