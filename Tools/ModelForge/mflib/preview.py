"""The preview modes of CAFE.SPEC.md section 5.6 and the owner's contact sheet.

  1 orbit        4 yaws x 20 degrees pitch, fitted to the bounding sphere, 45 degree FOV, 512 px; plus the
                 overlay view (collision wireframe red, bounds yellow) and the bake on/off pair
  2 game view    a 1920 x 1080 equivalent, 60 degree vertical FOV, eye at 1.7 yd, at 4, 8 and 15 yd, trilinear
                 mips by footprint: the crop around the model at the real pixel size, plus a 3x zoom of it
  3 lighting     SW day, SW night, Org day (and Org night for the Orgrimmar pieces), game view at 6 yd
  4 scene        the café layout (cafe.json `layout` when present, else the section 3.12.3 default) with every
                 piece placed, grey proxies for what is not built yet, gnome / human / tauren capsules
  5 silhouette   a black silhouette at 30 yd (game scale) and a UV texel-density heatmap
"""

import json
import math
import multiprocessing
import os

import blpconvert as B  # noqa: E402

from . import font as F
from . import geom as G
from . import m2check as C
from . import render as RD

GAME_W, GAME_H, GAME_FOV = 1920, 1080, 60.0
EYE = 1.7


def load(m2_path):
    with open(m2_path, "rb") as f:
        data = f.read()
    skin_path = os.path.splitext(m2_path)[0] + "00.skin"
    with open(skin_path, "rb") as f:
        skin = f.read()
    m, fnd = C.parse(data, skin, m2_path)
    if fnd:
        raise ValueError("%s does not pass m2check: %s" % (m2_path, fnd.items[0]["msg"]))
    return m


def geometry_bounds(m):
    pts = [v[0] for v in m["vertices"]]
    lo = tuple(min(p[i] for p in pts) for i in range(3))
    hi = tuple(max(p[i] for p in pts) for i in range(3))
    return lo, hi


def _save(frame, path, zoom=1):
    img = frame.to_image()
    if zoom > 1:
        img = upscale(img, zoom)
    B.write_png(path, img)
    return path


def upscale(img, k):
    out = B.Image(img.width * k, img.height * k)
    for y in range(out.height):
        sy = y // k
        for x in range(out.width):
            sx = x // k
            o = 4 * (y * out.width + x)
            s = 4 * (sy * img.width + sx)
            out.data[o:o + 4] = img.data[s:s + 4]
    return out


# ------------------------------------------------------------------------------------------- the views

def orbit_view(m, textures, yaw_deg, pitch_deg=20.0, size=512, ss=2, lighting=None, overlay=False,
               override_tex=None, particles=True, background=None):
    lo, hi = geometry_bounds(m)
    c = tuple((lo[i] + hi[i]) / 2 for i in range(3))
    r = max(G.length(G.sub(v[0], c)) for v in m["vertices"])
    fov = 45.0
    dist = r / math.sin(math.radians(fov / 2)) * 1.02
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    eye = (c[0] + math.cos(yaw) * math.cos(pitch) * dist, c[1] + math.sin(yaw) * math.cos(pitch) * dist,
           c[2] + math.sin(pitch) * dist)
    cam = RD.Camera(eye, c, fov, size, size, ss)
    frame = RD.Frame(cam, lighting or RD.PRESETS["neutral"], background or "flat")
    ds = RD.model_drawables(m, textures, None, override_tex)
    if particles:
        ds += RD.particle_drawables(m, textures, None, cam)
    RD.draw_scene(frame, ds)
    if overlay:
        RD.overlay_collision(frame, m)
        b = m["bounds"]
        RD.overlay_bounds(frame, b["min"], b["max"])
    return frame


def backbar_proxies(base_z, width=6.0, depth=0.8, wall_x=-1.6):
    """A back bar to stand the machine on (the real BackBarSW is M5): walnut body, marble top, floor, and the wall
    behind. A floor-standing piece (base_z near 0) gets only the floor and the wall, `wall_x` behind it."""
    floor = G.box(30.0, 30.0, 0.02, z0=-0.02)
    wall = G.box(30.0, 0.2, 3.5, z0=0.0)
    out = [(floor, (0.42, 0.40, 0.38), G.mat_identity()), (wall, (0.62, 0.56, 0.48), G.mat_translate(wall_x, 0.0, 0.0))]
    if base_z > 0.3:
        bar = G.box(width, depth, base_z - 0.04, 0.02, z0=0.0)
        top = G.box(width + 0.04, depth + 0.06, 0.04, 0.01, z0=base_z - 0.04)
        out = [(bar, (0.36, 0.22, 0.14), G.mat_translate(-0.1, 0.0, 0.0)),
               (top, (0.86, 0.84, 0.8), G.mat_translate(-0.1, 0.0, 0.0))] + out
    return out


def _wall_x(lo):
    """The proxy wall stands just behind the model (it is 1.6 yd behind a back-bar machine's origin)."""
    return min(-1.6, lo[0] - 0.6)


def game_view(m, textures, distance, lighting=None, base_z=1.05, yaw_deg=18.0, ss=2, override_tex=None,
              margin=0.35):
    """The model on a bar top at base_z, seen by a player standing `distance` yd in front (eye 1.7 yd)."""
    lo, hi = geometry_bounds(m)
    tgt = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, base_z + (lo[2] + hi[2]) / 2)
    yaw = math.radians(yaw_deg)
    eye = (tgt[0] + math.cos(yaw) * distance, tgt[1] + math.sin(yaw) * distance, EYE)
    full = RD.Camera(eye, tgt, GAME_FOV, GAME_W, GAME_H, ss)
    # window: the model's projected box plus a margin
    corners = [(x, y, z + base_z) for x in (lo[0] - margin, hi[0] + margin) for y in (lo[1] - margin, hi[1] + margin)
               for z in (lo[2] - margin * 0.5, hi[2] + margin)]
    xs, ys = [], []
    for p in corners:
        v = full.view(p)
        if v[2] <= 0.05:
            continue
        sx, sy, _ = full.project(v)
        xs.append(sx / ss)
        ys.append(sy / ss)
    x0 = max(0, int(min(xs)))
    x1 = min(GAME_W, int(math.ceil(max(xs))))
    y0 = max(0, int(min(ys)))
    y1 = min(GAME_H, int(math.ceil(max(ys))))
    cam = RD.Camera(eye, tgt, GAME_FOV, GAME_W, GAME_H, ss, (x0, y0, x1, y1))
    lit = lighting or RD.PRESETS["sw_day"]
    frame = RD.Frame(cam, lit)
    xf = G.mat_translate(0.0, 0.0, base_z)
    ds = []
    for mesh, col, mx in backbar_proxies(base_z, wall_x=_wall_x(lo)):
        ds.append(RD.mesh_drawable(mesh, col, mx, tag=2))
    ds += RD.model_drawables(m, textures, xf, override_tex)
    ds += RD.particle_drawables(m, textures, xf, cam)
    RD.draw_scene(frame, ds)
    return frame


def hero_view(m, textures, lighting=None, size=(960, 640), base_z=1.05, distance=None, yaw_deg=26.0, ss=2):
    """A game-like screenshot: the machine on the back bar (or a floor piece on the floor), eye height 1.7 yd, a
    narrow lens, zone lighting. The distance fits the model (about 2.35 yd for EspressoSW)."""
    lo, hi = geometry_bounds(m)
    if distance is None:
        r = 0.5 * math.sqrt(sum((hi[i] - lo[i]) ** 2 for i in range(3)))
        distance = max(0.8, 2.6 * r)
    tgt = ((lo[0] + hi[0]) / 2 + 0.05, (lo[1] + hi[1]) / 2, base_z + (lo[2] + hi[2]) / 2 - 0.02)
    yaw = math.radians(yaw_deg)
    corners = [(x, y, z + base_z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    for _step in range(12):
        # back off until the whole model is in frame (a tall crest, finial or lid spike is not cut off)
        eye = (tgt[0] + math.cos(yaw) * distance, tgt[1] + math.sin(yaw) * distance, max(EYE, tgt[2] + 0.2))
        cam = RD.Camera(eye, tgt, 34.0, size[0], size[1], ss)
        pr = [cam.project(cam.view(p)) for p in corners if cam.view(p)[2] > 0.05]
        if all(0.03 * size[1] * ss <= q[1] <= 0.97 * size[1] * ss and 0 <= q[0] <= size[0] * ss for q in pr):
            break
        distance *= 1.08
    frame = RD.Frame(cam, lighting or RD.PRESETS["sw_day"])
    xf = G.mat_translate(0.0, 0.0, base_z)
    ds = [RD.mesh_drawable(mesh, col, mx, tag=2) for mesh, col, mx in backbar_proxies(base_z, wall_x=_wall_x(lo))]
    ds += RD.model_drawables(m, textures, xf)
    ds += RD.particle_drawables(m, textures, xf, cam)
    RD.draw_scene(frame, ds)
    return frame


def silhouette_view(m, distance=30.0, base_z=1.05):
    lo, hi = geometry_bounds(m)
    tgt = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, base_z + (lo[2] + hi[2]) / 2)
    eye = (tgt[0] + distance * math.cos(math.radians(18)), tgt[1] + distance * math.sin(math.radians(18)), EYE)
    full = RD.Camera(eye, tgt, GAME_FOV, GAME_W, GAME_H, 1)
    pts = [(x, y, z + base_z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    sx = [full.project(full.view(p))[0] for p in pts]
    sy = [full.project(full.view(p))[1] for p in pts]
    pad = 6
    win = (int(min(sx)) - pad, int(min(sy)) - pad, int(max(sx)) + pad + 1, int(max(sy)) + pad + 1)
    cam = RD.Camera(eye, tgt, GAME_FOV, GAME_W, GAME_H, 2, win)
    frame = RD.Frame(cam, RD.PRESETS["neutral"], (1.0, 1.0, 1.0))
    xf = G.mat_translate(0.0, 0.0, base_z)
    for d in RD.model_drawables(m, RD.TextureSet("/nonexistent"), xf):
        d.tex = None
        d.color = (0.0, 0.0, 0.0)
        d.flags |= 1
        d.blend = 0 if d.blend <= 1 else d.blend
        if d.blend == 0:
            RD.draw(frame, d)
    return frame


def density_view(m, size=512):
    """Orbit view coloured by UV texel density (texels per yard, atlas textures only): blue low, red high."""
    sk = m["skin"]
    verts = m["vertices"]
    lo, hi = geometry_bounds(m)
    c = tuple((lo[i] + hi[i]) / 2 for i in range(3))
    r = max(G.length(G.sub(v[0], c)) for v in verts)
    dist = r / math.sin(math.radians(22.5)) * 1.02
    yaw, pitch = math.radians(35), math.radians(20)
    eye = (c[0] + math.cos(yaw) * math.cos(pitch) * dist, c[1] + math.sin(yaw) * math.cos(pitch) * dist,
           c[2] + math.sin(pitch) * dist)
    cam = RD.Camera(eye, c, 45.0, size, size, 2)
    frame = RD.Frame(cam, RD.PRESETS["neutral"], "flat")
    dens = []
    for b in sk["batches"]:
        if b["textureCoordComboIndex"] != 0:
            continue
        sec = sk["sections"][b["skinSectionIndex"]]
        idx = sk["indices"][sec["indexStart"]:sec["indexStart"] + sec["indexCount"]]
        for k in range(0, len(idx), 3):
            pa, _n, ua, _ = verts[sk["lookup"][idx[k]]]
            pb, _n, ub, _ = verts[sk["lookup"][idx[k + 1]]]
            pc, _n, uc, _ = verts[sk["lookup"][idx[k + 2]]]
            wa = G.length(G.cross(G.sub(pb, pa), G.sub(pc, pa))) / 2
            ta = abs((ub[0] - ua[0]) * (uc[1] - ua[1]) - (ub[1] - ua[1]) * (uc[0] - ua[0])) / 2 * 512 * 512
            if wa > 1e-8:
                dens.append(((pa, pb, pc), math.sqrt(ta / wa)))
    if not dens:
        return frame
    vals = sorted(v for _t, v in dens)
    med = vals[len(vals) // 2]
    for (pa, pb, pc), v in dens:
        # a chart squeezed to no area (v 0) shows as the lowest density, not a crash
        k = max(0.0, min(1.0, 0.5 + math.log2(v / med) / 3.0)) if v > 0 and med > 0 else 0.0
        col = (min(1.0, 2 * k), 1.0 - abs(2 * k - 1.0), min(1.0, 2 * (1 - k)))
        n = G.norm(G.cross(G.sub(pb, pa), G.sub(pc, pa)))
        d = RD.Drawable([pa, pb, pc], [n, n, n], [(0, 0)] * 3, [(0, 1, 2)], None, 0, 0, False, col)
        RD.draw(frame, d)
    return frame


# ------------------------------------------------------------------------------------------------ scene

DEFAULT_LAYOUT = [
    # role, model name (SW), F, L, U, turn degrees: section 3.12.3, every piece of the default layout (the stock
    # tables, stools and keg tables become grey proxies) plus the table props that stand on it
    ("counter", "CounterSW", 0.8, 0.0, 0.0, 180), ("tipjar", "TipJar", 0.8, 1.6, 1.05, 180),
    ("station_B", "BlenderSW", 0.8, -2.0, 1.05, 0), ("backbar", "BackBarSW", 4.8, 0.0, 0.0, 180),
    ("station_E", "EspressoSW", 4.75, 0.0, 1.05, 180), ("station_G", "GrinderSW", 4.7, 2.0, 1.05, 180),
    ("station_S", "SyrupRackSW", 4.95, -2.0, 1.05, 180), ("station_K", "KettleStoveSW", 2.4, 5.2, 0.0, -90),
    ("station_C", "ColdBoxSW", 2.4, -5.2, 0.0, 90), ("chalkboard", "ChalkboardSW", -2.0, 2.8, 0.0, 180),
    # the counter cup stands over the pickup spot (L -1.6), on the counter's customer edge
    ("pickup_cup", "CupSW", 0.55, -1.6, 1.05, 200),
    ("table_1", None, -4.0, -5.5, 0.0, 0), ("table_2", None, -4.0, -11.5, 0.0, 0),
    ("table_3", None, -10.0, -5.5, 0.0, 0), ("table_4", None, -10.0, -11.5, 0.0, 0),
    ("parasol_1", "ParasolSW", -10.0, -5.5, 0.0, 0), ("parasol_2", "ParasolSW", -10.0, -11.5, 0.0, 0),
    ("kegtable_1", None, -14.0, -5.5, 0.0, 0), ("kegtable_2", None, -14.0, -11.5, 0.0, 0),
    # served drinks on the tables (stock tables are 0.75 high in the proxies)
    ("table_cup", "CupSW", -4.25, -5.3, 0.75, 150), ("table_shake", "ShakeGlass", -3.8, -5.75, 0.75, 0),
    ("table_shake", "ShakeGlass", -10.2, -11.3, 0.75, 0), ("table_cup", "CupSW", -9.8, -11.75, 0.75, 30),
]
# Stools round the tables (section 3.7.4: T1, T2 at +-1.1 F; T3, T4 also at +-1.1 L), facing their table.
for _tf, _tl, _four in ((-4.0, -5.5, False), (-4.0, -11.5, False), (-10.0, -5.5, True), (-10.0, -11.5, True)):
    for _df, _dl in ((1.1, 0.0), (-1.1, 0.0)) + (((0.0, 1.1), (0.0, -1.1)) if _four else ()):
        DEFAULT_LAYOUT.append(("chair", None, _tf + _df, _tl + _dl, 0.0, 0))
PROXY_SIZES = {"table": (1.2, 1.2, 0.75), "chair": (0.5, 0.5, 0.55), "kegtable": (0.9, 0.9, 1.1)}
CAPSULES = [  # (height, colour, F, L): work spots, queue, seats (gnome 1.0, human 1.9, tauren 2.8)
    (1.9, (0.85, 0.75, 0.6), 4.0, 0.35), (1.0, (0.6, 0.8, 0.6), 4.0, -0.35), (2.8, (0.5, 0.35, 0.25), 4.0, 2.0),
    (1.9, (0.85, 0.75, 0.6), 2.75, 4.4), (1.9, (0.6, 0.6, 0.85), 2.05, -4.4), (1.0, (0.6, 0.8, 0.6), 1.6, -2.35),
    (1.9, (0.6, 0.6, 0.85), -1.5, 0.0), (1.0, (0.6, 0.8, 0.6), -3.0, 0.3), (2.8, (0.5, 0.35, 0.25), -4.5, 0.6),
    (1.9, (0.85, 0.75, 0.6), -2.9, -5.5), (2.8, (0.5, 0.35, 0.25), -11.1, -11.5), (1.0, (0.6, 0.8, 0.6), -10.0, -4.4),
]
# In the bar close-up the stand-ins at the espresso machine's +L spot and the grinder's spot step aside along the
# aisle (to between the stations), so the hero machine and the grinder stand unobstructed from the camera.
BAR_ASIDE = {(4.0, 0.35): (4.0, 1.05), (4.0, 2.0): (4.0, 2.8)}
# The scene cameras: the whole café fitted from above its tables corner (yaw, pitch, vertical FOV: the bar at the
# back, the tables in front), and the bar close up (eye, target, vertical FOV). The close-up looks from the cold
# box's side (-L), so its line of sight to the espresso machine, the hero, passes over the gnome at the machine's
# -L work spot instead of through the human at the +L one, and the machine stands unobstructed.
SCENE_VIEWS = {
    "": ("fit", 212.0, 42.0, 30.0),
    "bar": ((-4.4, -5.6, 5.0), (2.6, 0.5, 0.9), 54.0),
}


def _fit_camera(points, yaw_deg, pitch_deg, fov, size, fill=0.9):
    """A camera looking from (yaw, pitch) whose frame holds `points` (filling `fill` of the tighter side)."""
    c = [sum(p[i] for p in points) / len(points) for i in range(3)]
    ya, pa = math.radians(yaw_deg), math.radians(pitch_deg)
    d = (math.cos(ya) * math.cos(pa), math.sin(ya) * math.cos(pa), math.sin(pa))
    r = max(G.length(G.sub(p, c)) for p in points)
    dist = r / math.sin(math.radians(fov / 2))
    tgt = list(c)
    for _it in range(4):
        eye = tuple(tgt[i] + d[i] * dist for i in range(3))
        cam = RD.Camera(eye, tuple(tgt), fov, size[0], size[1], 1)
        pr = [cam.project(cam.view(p)) for p in points]
        xs, ys = [q[0] for q in pr], [q[1] for q in pr]
        # re-centre (a pixel is 2 tan(fov/2) dist / height yards at the target) and re-fit the distance
        k = 2 * cam.t * dist / size[1]
        dx = ((min(xs) + max(xs)) / 2 - size[0] / 2) * k
        dy = ((min(ys) + max(ys)) / 2 - size[1] / 2) * k
        tgt = [tgt[i] + cam.xv[i] * dx - cam.yv[i] * dy for i in range(3)]
        span = max((max(xs) - min(xs)) / size[0], (max(ys) - min(ys)) / size[1])
        dist *= span / fill
    eye = tuple(tgt[i] + d[i] * dist for i in range(3))
    return RD.Camera(eye, tuple(tgt), fov, size[0], size[1], 2)


def org_name(name):
    """The Orgrimmar piece standing where a Stormwind one stands in the default layout."""
    if not name:
        return name
    if name == "CupSW":
        return "MugOrg"
    return name[:-2] + "Org" if name.endswith("SW") else name


def scene_layout(cafe_json=None, scene="sw"):
    if cafe_json and os.path.exists(cafe_json):
        try:
            with open(cafe_json) as f:
                doc = json.load(f)
            from .props import CATALOGUE
            by_display = {disp: name for name, disp, _size, _budget in CATALOGUE}
            pieces = []
            gos = {g.get("entry"): g for g in doc.get("gameobjects", [])}
            for row in doc.get("layout", []):
                ent = row.get("entry")
                if isinstance(ent, dict):
                    ent = ent.get("1" if scene == "sw" else "2", ent.get("1"))
                go = gos.get(ent, {})
                name = by_display.get(go.get("display"), go.get("name"))
                pieces.append((row.get("role"), name, row.get("f", 0.0), row.get("l", 0.0),
                               row.get("u", 0.0) or 0.0, row.get("turn", 0), go.get("size") or go.get("footprint")))
            if pieces:
                return pieces, "cafe.json"
        except (ValueError, OSError):
            pass
    rows = DEFAULT_LAYOUT if scene == "sw" else [(r, org_name(n)) + tuple(rest) for r, n, *rest in DEFAULT_LAYOUT]
    return [p + (None,) for p in rows], "default (section 3.12.3)"


def scene_view(models, textures, catalogue, cafe_json=None, size=(1024, 640), lighting=None, scene="sw", view=""):
    """models: {name: parsed m2} of the built models; catalogue: {name: (W, D, H)} for proxies; scene: "sw" or
    "org" (the default layout with the Orgrimmar pieces); view: a SCENE_VIEWS key ("" the whole café, "bar")."""
    pieces, source = scene_layout(cafe_json, scene)
    sv = SCENE_VIEWS[view]
    if sv[0] == "fit":
        pts = []
        for role, name, f, l, u, _turn, size_ in pieces:
            dims = catalogue.get(name) or size_ or PROXY_SIZES.get((role or "").split("_")[0]) or (0.5, 0.5, 1.0)
            hw = max(dims[0], dims[1]) / 2
            pts += [(f + dx * hw, l + dy * hw, u + z) for dx in (-1, 1) for dy in (-1, 1)
                    for z in (0.0, dims[2] if len(dims) > 2 else 1.0)]
        pts += [(f, l, h) for h, _col, f, l in CAPSULES]
        cam = _fit_camera(pts, sv[1], sv[2], sv[3], size)
    else:
        cam = RD.Camera(sv[0], sv[1], sv[2], size[0], size[1], 2)
    base = lighting or RD.PRESETS["sw_day"]
    lit = RD.Lighting(base.ambient, base.diffuse, G.norm((0.55, -0.45, -0.7)), None, base.sky, base.name)
    frame = RD.Frame(cam, lit)
    ds = []
    floor = G.box(60.0, 60.0, 0.02, z0=-0.02)
    ds.append(RD.mesh_drawable(floor, (0.5, 0.48, 0.44), G.mat_identity()))
    for role, name, f, l, u, turn, size_ in pieces:
        xf = G.mat_chain(G.mat_translate(f, l, u), G.mat_rot_z(math.radians(turn)))
        if name in models:
            ds += RD.model_drawables(models[name], textures, xf)
            ds += RD.particle_drawables(models[name], textures, xf, cam)
            continue
        dims = None
        kind = (role or "").split("_")[0]
        if name in catalogue:
            dims = catalogue[name]
        elif size_:
            dims = (size_[0], size_[1], size_[2] if len(size_) > 2 else 0.75)
        elif kind in PROXY_SIZES:
            dims = PROXY_SIZES[kind]
        if not dims:
            continue
        w, d, h = dims
        if kind == "parasol":
            pole = G.cylinder(0.05, h * 0.95)
            canopy = G.cone(w / 2, 0.05, 0.6, 16, z0=h - 0.7)
            ds.append(RD.mesh_drawable(pole, (0.55, 0.55, 0.55), xf))
            ds.append(RD.mesh_drawable(canopy, (0.62, 0.62, 0.66), xf))
            continue
        if kind == "table":
            top = G.cylinder(w / 2, 0.06, 16, z0=h - 0.06)
            leg = G.cylinder(0.08, h - 0.06, 8)
            ds.append(RD.mesh_drawable(G.merge([top, leg]), (0.58, 0.58, 0.6), xf))
            continue
        ds.append(RD.mesh_drawable(G.box(w, d, h, 0.02), (0.58, 0.58, 0.6), xf))
    for hgt, col, f, l in CAPSULES:
        if view == "bar":
            f, l = BAR_ASIDE.get((f, l), (f, l))
        cap = G.capsule(min(0.35, hgt * 0.17), hgt, 10)
        ds.append(RD.mesh_drawable(cap, col, G.mat_translate(f, l, 0.0)))
    RD.draw_scene(frame, ds)
    return frame, source


# -------------------------------------------------------------------------------------- contact sheet

def contact_sheet(panels, path, cols=3, cell=(420, 300), title=None, bg=(24, 26, 31), hero=None):
    """panels: [(png path, label)]. Images are fitted into cells (nearest scaling) with a label under each;
    `hero` (a panel) takes the top-left 2 x 2 cells."""
    lab_h = 22
    gap = 8
    top = 40 if title else 8
    occupied = set()
    slots = []
    if hero:
        occupied |= {(0, 0), (0, 1), (1, 0), (1, 1)}
        slots.append((hero, 0, 0, 2))
    r = c = 0
    for pnl in panels:
        while (r, c) in occupied:
            c += 1
            if c >= cols:
                c = 0
                r += 1
        slots.append((pnl, r, c, 1))
        occupied.add((r, c))
    rows = max(rr + span for _p, rr, _c, span in slots)
    W = cols * cell[0] + (cols + 1) * gap
    H = top + rows * (cell[1] + lab_h + gap) + gap
    sheet = B.Image(W, H)
    d = sheet.data
    for i in range(W * H):
        d[4 * i:4 * i + 4] = bytes((bg[0], bg[1], bg[2], 255))
    if title:
        _text(sheet, title, 10, 10, 3, (235, 210, 150))
    for (path_, label), rr, cc, span in slots:
        img = B.read_png(path_)
        cw = span * cell[0] + (span - 1) * gap
        ch = span * cell[1] + (span - 1) * (gap + lab_h)
        cx = gap + cc * (cell[0] + gap)
        cy = top + rr * (cell[1] + lab_h + gap)
        sc = min(cw / img.width, ch / img.height)
        w, h = max(1, int(img.width * sc)), max(1, int(img.height * sc))
        ox, oy = cx + (cw - w) // 2, cy + (ch - h) // 2
        for y in range(h):
            sy = min(img.height - 1, int(y / sc))
            for x in range(w):
                sx = min(img.width - 1, int(x / sc))
                s = 4 * (sy * img.width + sx)
                o = 4 * ((oy + y) * W + ox + x)
                d[o:o + 3] = img.data[s:s + 3]
                d[o + 3] = 255
        _text(sheet, label, cx + 2, cy + ch + 4, 2, (200, 204, 210))
    B.write_png(path, sheet)
    return path


def _text(img, text, x, y, scale, color):
    safe = "".join(ch if (ch in F.PIXEL_GLYPHS or ch == " ") else "?" for ch in text)
    for cx, cy in F.pixel_cells(safe):
        for yy in range(scale):
            for xx in range(scale):
                X, Y = x + cx * scale + xx, y + cy * scale + yy
                if 0 <= X < img.width and 0 <= Y < img.height:
                    o = 4 * (Y * img.width + X)
                    img.data[o:o + 3] = bytes(color)


def write_index(out_dir, entries):
    rows = "\n".join('<figure><img src="%s" alt="%s"><figcaption>%s</figcaption></figure>' % (
        os.path.basename(p), lab, lab) for p, lab in entries)
    html = ("<!doctype html><meta charset=utf-8><title>ModelForge previews</title>"
            "<style>body{background:#181a1f;color:#ccd;font:14px sans-serif}figure{display:inline-block;"
            "margin:8px}img{max-width:640px;display:block}</style>\n" + rows + "\n")
    path = os.path.join(out_dir, "index.html")
    with open(path, "w") as f:
        f.write(html)
    return path


# ------------------------------------------------------------------------------------------- run views

_VJOB = {}


def _run_view(spec):
    kind, args, path, zoom = spec
    job = _VJOB
    m = job["m"]
    tx = job["tex"]
    bz = job.get("base_z", 1.05)
    if kind == "orbit":
        frame = orbit_view(m, tx, *args)
    elif kind == "orbit_nobake":
        frame = orbit_view(m, tx, args[0], override_tex=job.get("nobake"))
    elif kind == "overlay":
        frame = orbit_view(m, tx, args[0], overlay=True, particles=False)
    elif kind == "game":
        frame = game_view(m, tx, args[0], RD.PRESETS[args[1]], base_z=bz)
    elif kind == "hero":
        frame = hero_view(m, tx, RD.PRESETS[args[0]], base_z=bz)
    elif kind == "silhouette":
        frame = silhouette_view(m, base_z=bz)
    elif kind == "density":
        frame = density_view(m)
    else:
        raise ValueError(kind)
    _save(frame, path)
    if zoom > 1:
        _save(frame, path.replace(".png", "_x%d.png" % zoom), zoom)
    return path


def render_views(m, textures, specs, nobake=None, jobs=None, base_z=1.05):
    global _VJOB
    _VJOB = {"m": m, "tex": textures, "nobake": nobake, "base_z": base_z}
    jobs = jobs or os.cpu_count() or 1
    if jobs > 1 and len(specs) > 1 and "fork" in multiprocessing.get_all_start_methods():
        ctx = multiprocessing.get_context("fork")
        with ctx.Pool(min(jobs, len(specs))) as pool:
            res = pool.map(_run_view, specs, chunksize=1)
    else:
        res = [_run_view(s) for s in specs]
    _VJOB = {}
    return res


QUICK = ("hero shot, SW day", "hero shot, Org day",
         "orbit yaw 30", "orbit yaw 210", "game view 8 yd", "silhouette 30 yd")


def model_previews(name, m2_path, root, out_dir, nobake_atlas=None, jobs=None, modes=(1, 2, 3, 5), base_z=1.05,
                   quick=False):
    """Writes the per-model PNGs; returns [(path, label)]. base_z: the height the piece stands at (1.05 on the
    back bar or counter, 0 on the floor; sizes.KINDS). quick: only the QUICK views (hero, two orbits, the 8 yd
    game view and the silhouette), for fast iteration."""
    os.makedirs(out_dir, exist_ok=True)
    m = load(m2_path)
    tx = RD.TextureSet(root)
    over = None
    if nobake_atlas:
        atlas_client = [t["path"] for t in m["textures"] if t["path"].lower().endswith("_atlas.blp")]
        if atlas_client:
            over = {atlas_client[0].lower(): RD.Texture(nobake_atlas, 3)}
    specs = []
    labels = []
    # the hero and game views stand the piece in its own city's day light (an Orgrimmar piece in org_day)
    city, city_lab = ("org_day", "Org day") if name.endswith("Org") else ("sw_day", "SW day")

    def add(kind, args, fn, label, zoom=1):
        if quick and label not in QUICK:
            return
        p = os.path.join(out_dir, fn)
        specs.append((kind, args, p, zoom))
        labels.append((p, label))
    if 2 in modes:
        add("hero", (city,), "%s_hero.png" % name, "hero shot, %s" % city_lab)
    if 1 in modes:
        for k, yaw in enumerate((30, 120, 210, 300)):
            add("orbit", (yaw, 20.0), "%s_orbit_%d.png" % (name, yaw), "orbit yaw %d" % yaw)
        add("overlay", (30,), "%s_overlay.png" % name, "collision + bounds")
        if over:
            add("orbit_nobake", (30,), "%s_bake_off.png" % name, "bake OFF (yaw 30)")
    if 2 in modes:
        for dist in (4, 8, 15):
            add("game", (dist, city), "%s_game_%dyd.png" % (name, dist), "game view %d yd" % dist, 3)
    if 3 in modes:
        presets = [("sw_day", "SW day"), ("sw_night", "SW night"), ("org_day", "Org day")]
        if name.endswith("Org"):
            presets.append(("org_night", "Org night"))      # every Orgrimmar piece is checked in its own night
        for preset, lab in presets:
            add("game", (6, preset), "%s_light_%s.png" % (name, preset), "lighting %s, 6 yd" % lab, 2)
    if 5 in modes:
        add("silhouette", (), "%s_silhouette30.png" % name, "silhouette 30 yd", 4)
        add("density", (), "%s_density.png" % name, "texel density")
    render_views(m, tx, specs, over, jobs, base_z)
    return labels
