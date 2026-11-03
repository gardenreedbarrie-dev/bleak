"""19321 MugOrg, the Orgrimmar clay mug (a table prop), CAFE.SPEC.md section 5.8.1.

A chunky hand-thrown clay mug, shaped so a player names it at a glance from a table or the pickup counter: a tall
tankard body on a heavy riveted iron foot band with a thick rolled lip, dark strong brew under a ring of foam inside
a dark rim line, red glaze poured over the rim with a wavy edge and running down a band of light sandy clay in long
fat drips that end in round beads, and a big closed handle that is an ivory tusk: lashed with leather at its thick
root just under the rim, it bows out and down and its point rejoins the wall near the foot. Orgrimmar charm: the
tusk crest painted on the front in ivory on a dark red roundel, the iron band, a slight hand-made wobble. 0.2 (Y) x
0.2 (X) x 0.22 yd (about 1.6x real size, in line with the stock tankards).

Cues and their size at 10 yd (about 95 px per yard): the body (0.18 across, 0.22 tall, 12 sides), the red glaze
(a band about 0.05 deep, five runs 0.04-0.05 wide and 0.11-0.15 long ending in beads 0.06-0.075 across, on light
clay), the tusk (a closed D reaching about 0.07 out from the wall, 0.064 thick at its lashed root under the rim
and 0.028 where its point goes into the wall near the foot, a hole about 0.05 x 0.12), the iron foot (0.028 tall,
eight rivets), the brew (0.13 across, a foam ring 0.02 wide inside a dark rim line), the crest (0.10).

Deviations from the section 5.8.1 design, for recognizability and the size:
- the handle is a tusk (ivory, tapered, leather-lashed), not clay, so it shows in its own colour against the clay
  and reads as Orgrimmar; it is a closed handle (a free point hooking off the rim read as a horn stuck on the
  side);
- it points 135 degrees round from the front (back and to the left): a handle on +Y would not fit the 0.2 x 0.2
  footprint with a 0.18 body, and at 135 degrees both extents come to about 0.21 and the tusk is seen side-on from
  the hero and game views (about 18-26 degrees); the model is shifted so the footprint is centred on the origin;
- the foot ring is a riveted iron band (painted), the Orgrimmar iron cue;
- the wobble (0.006) is under section 5.4's 0.5-2 cm: more would push the 0.2 footprint out; the brew is a fan
  over the wobbled inner wall's own ring, so it closes the mug at any wobble;
- added: the tusk crest roundel, the leather lashing and the foam ring.
"""

import math

from .. import build as B
from .. import emblem as E
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "MugOrg"
DISPLAY = 19321

CLAY = T.hexc("C88A4E")       # warm, darker clay: the ivory tusk and the red glaze stand out on it
LIGHT_CLAY = T.hexc("E6C08E")  # the light sandy band the drips run down (the red reads on it at 15 yd)
GLAZE = T.hexc("9E1E14")
RIM_LINE = T.hexc("3A100A")    # the dark inner wall round the brew: the rim line seen from above
LACQUER = T.hexc("B5402F")
LEATHER = T.hexc("5A3420")
IRON = T.hexc("3A3634")
IVORY = T.hexc("F0E2C0")

# the body: the foot ring, a step in, a barrel belly, the rolled lip, the inner wall down to the brew
BODY = [(0.093, 0.0), (0.091, 0.028), (0.081, 0.04), (0.087, 0.205), (0.078, 0.222), (0.066, 0.198)]
TOP = 0.222
BREW_Z = 0.198
WOBBLE = 0.006                 # hand-thrown: enough to break the turned 12-gon at the rim
FOOT_Z = 0.028                 # the iron band: everything below this
GLAZE_BAND = 0.05              # the glaze's depth down the outside of the rim
# the glaze runs: (angle from the front in degrees, half width, length from the rim), at least 0.02 wide so
# they hold at mip 1 on the body chart; the two beside the crest run long (both show in the 3/4 views) and pass
# clear of its 33-degree half angle, their beads beside it
DRIPS = ((58.0, 0.024, 0.15), (112.0, 0.025, 0.15), (180.0, 0.02, 0.11), (-122.0, 0.023, 0.14),
         (-60.0, 0.024, 0.145))
HANDLE_DEG = 135.0             # the handle's direction from +X toward +Y
# the tusk's centre line in its vertical plane (distance from the mug's axis, z): the fat root inside the upper
# wall under the rim, bowing out and down, the point going back into the wall near the foot (both open ends stay
# buried through the wobble): a closed handle
TUSK = ((0.058, 0.188), (0.168, 0.212), (0.168, 0.035), (0.062, 0.058))
TUSK_R = (0.032, 0.014)        # the root's and the point's radius: a hefty grip, a blunt point
WRAP = (0.03, 0.2)             # the leather lashing, along the tusk's chart (v)
CREST_D = 0.10                 # the painted crest's size (yd)
CREST_Z = 0.098                # its centre height, on the bare clay under the glaze


def _wall_r(z):
    """The outer wall's radius at height z (BODY's outer segments, up to the lip)."""
    for (r0, z0), (r1, z1) in zip(BODY[:5], BODY[1:5]):
        if z0 <= z <= z1:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return BODY[4][0]


def _profile_t(profile, z):
    """The lathe chart's t (yd from the profile's last point) of the outer-wall point at height z, and the
    chart's height."""
    arc = [0.0]
    for (r0, z0), (r1, z1) in zip(profile, profile[1:]):
        arc.append(arc[-1] + math.hypot(r1 - r0, z1 - z0))
    for k, ((r0, z0), (r1, z1)) in enumerate(zip(profile, profile[1:])):
        if z0 <= z <= z1 and z1 > z0:
            return arc[-1] - (arc[k] + (arc[k + 1] - arc[k]) * (z - z0) / (z1 - z0)), arc[-1]
    return 0.0, arc[-1]


# ----------------------------------------------------------------------------------------------- paints

def _glazed(ctx, seed, cx, cy):
    """How the red glaze covers this texel: (covered, pool) with pool 0..1 where the glaze runs thick (drip
    edges, beads). The glaze is poured over the rim: inside fully, a band GLAZE_BAND deep outside with a wavy
    edge, and the DRIPS runs, flaring where they leave the band (so they do not read as T-bars), narrowing as
    they run and ending in round beads."""
    x, y, z = ctx.pos
    rx, ry = x - cx, y - cy
    rr = math.hypot(rx, ry) or 1.0
    if (ctx.n[0] * rx + ctx.n[1] * ry) / rr < -0.25:
        return True, 0.0                 # the inner wall
    d = TOP - z
    a = math.atan2(ry, rx)
    edge = GLAZE_BAND + (T.noise(a * 3.0, 0.5, seed) - 0.5) * 0.024
    if d < edge:
        return True, T.smoothstep(edge - 0.008, edge, d) * 0.5
    for deg, w, L in DRIPS:
        da = (a - math.radians(deg) + math.pi) % (2.0 * math.pi) - math.pi
        s = da * 0.086 + (T.noise(d * 30.0, deg, seed + 4) - 0.5) * w * 0.5    # yd along the wall, wavering
        bead = L - 1.2 * w
        if edge - 0.006 <= d <= bead:
            k = T.clamp01((d - edge) / max(bead - edge, 1e-3))
            hw = w * (0.8 + 0.8 * T.smoothstep(0.3, 0.0, k))
            if abs(s) < hw:
                return True, T.smoothstep(hw * 0.4, hw, abs(s)) * 0.6
        if math.hypot(s, (d - bead) * 0.85) < 1.5 * w:
            return True, 0.75
    return False, 0.0


def _iron_band(ctx, a, z):
    """The riveted iron foot band: dark iron lit toward the light, a bright top edge, eight rivets."""
    lit = T.clamp01(0.5 + 0.5 * (ctx.n[0] * 0.7 - ctx.n[1] * 0.4))
    c = T.mix(T.scale(IRON, 0.75), T.scale(IRON, 1.5), lit)
    c = T.mix(c, T.hexc("8A8076"), T.smoothstep(FOOT_Z - 0.006, FOOT_Z, z) * 0.6)
    step = 2.0 * math.pi / 8.0
    ak = (math.floor(a / step) + 0.5) * step
    return T.rivet_dot(c, (a - ak) * BODY[0][0], -(z - FOOT_Z * 0.5), 0.0105, hi=T.hexc("FFE0A0"),
                       lo=T.hexc("1A1614"))


def mug_paint(cx, cy):
    """The body's paint for a mug centred at (cx, cy): warm clay with dark speckles, darker toward the foot,
    deep red glaze poured over the rim (a glossy, lit band; darker where it pools in the runs and beads), the
    iron foot band."""
    def p_mug(ctx, seed, p):
        x, y, z = ctx.pos
        glazed, pool = _glazed(ctx, seed, cx, cy)
        if glazed:
            rx, ry = x - cx, y - cy
            rr = math.hypot(rx, ry) or 1.0
            if (ctx.n[0] * rx + ctx.n[1] * ry) / rr < -0.25:
                # the inner wall: a dark line round the brew, so the coffee surface reads from above
                return T.mix(RIM_LINE, GLAZE, T.smoothstep(BREW_Z + 0.012, TOP, z) * 0.5)
            c = T.mix(GLAZE, T.scale(GLAZE, 0.55), pool)
            c = T.mix(c, LACQUER, T.smoothstep(-0.1, 0.8, ctx.n[2]) * 0.4)
            lit = T.clamp01(ctx.n[0] * 0.6 + ctx.n[1] * 0.5)
            c = T.mix(c, T.hexc("E8785A"), T.smoothstep(0.55, 0.85, lit) * 0.45)
            if ctx.curv > 0:
                c = T.mix(c, T.hexc("F09070"), T.clamp01(ctx.curv) * 0.35)
            return c
        if z < FOOT_Z:
            return _iron_band(ctx, math.atan2(y - cy, x - cx), z)
        c = T.mix(T.scale(CLAY, 0.86), T.scale(CLAY, 1.08), T.fbm3(x * 9.0, y * 9.0, z * 9.0, seed + 2, 2))
        # a light sandy band from the belly up, under the glaze: the red drips run down it in high contrast
        c = T.mix(c, LIGHT_CLAY, T.smoothstep(0.07, 0.11, z) * 0.7)
        # the lower 40 % shades down toward the foot (the clay reads round, not flat cardboard)
        c = T.scale(c, 1.0 - 0.2 * T.smoothstep(0.11, 0.04, z))
        sp = T.noise3(x * 70.0, y * 70.0, z * 70.0, seed + 3)
        c = T.mix(c, T.hexc("5A3218"), T.smoothstep(0.8, 0.9, sp) * 0.5)
        if z < 0.042:
            c = T.scale(c, 0.78)         # the shadowed step above the band
        return c
    return p_mug


def p_brew(ctx, seed, p):
    """Strong dark coffee, a ring of tan foam round the edge (a soft, lumpy edge: a fine noise reads as
    stitching) with a few bubbles."""
    cr = min(ctx.cw, ctx.ch) / 2.0
    X = (ctx.s - ctx.cw / 2.0) / cr
    Y = (ctx.t - ctx.ch / 2.0) / cr
    r = math.hypot(X, Y)
    c = T.mix(T.hexc("5A3218"), T.hexc("24120A"), T.smoothstep(0.0, 0.55, r))
    foam = T.smoothstep(0.6, 0.78, r + (T.noise(ctx.s * 22.0, ctx.t * 22.0, seed) - 0.5) * 0.14)
    c = T.mix(c, T.hexc("C89A68"), foam * 0.85)
    b = T.noise(ctx.s * 140.0, ctx.t * 140.0, seed + 1)
    if r > 0.5 and b > 0.72:
        c = T.mix(c, T.hexc("F0D8B0"), T.smoothstep(0.72, 0.85, b) * 0.6)
    return c


def p_tusk(ctx, seed, p):
    """Ivory with age cracks and a darker root, a bright point; a stitched leather lashing round its root."""
    c = T.g_bone(ctx, seed, {"kind": "ivory", "root": 0, "cracks": 2})
    c = T.mix(c, T.hexc("FFF8E8"), T.smoothstep(0.7, 1.0, ctx.v) * 0.4)
    if WRAP[0] < ctx.v < WRAP[1]:
        c = T.g_leather(ctx, seed + 3, {"color": LEATHER})
        k = (ctx.v - WRAP[0]) / (WRAP[1] - WRAP[0])
        # cross-stitched lashing: two dark grooves and a pale thong crossing them
        if abs(k - 0.08) < 0.07 or abs(k - 0.92) < 0.07:
            c = T.scale(c, 0.55)
        q = (ctx.u * 2.0 + k * 1.5) % 1.0
        if abs(q - 0.5) < 0.14 and 0.15 < k < 0.85:
            c = T.mix(c, T.hexc("D8B488"), 0.85)
    return c


# ---------------------------------------------------------------------------------------------- decals

# the crest's layers (emblem.EMBLEMS["tusk_crest"]) in high contrast on the dark red roundel
CREST_TONES = {"tusk_l": IVORY, "tusk_r": IVORY, "ridge_l": T.hexc("FFF8E8"), "ridge_r": T.hexc("FFF8E8"),
               "wrap_l": T.hexc("8A5A30"), "wrap_r": T.hexc("8A5A30"), "band": T.hexc("6E1A12")}


def d_crest(t_mid, t_total):
    """The tusk crest roundel: a dark ring, a dark red disc and the crest in ivory (tusks, cup, saucer, steam)
    with leather wraps, centred at t_mid of t_total yd down the body's chart. A decal for paint2d.wrap_front."""
    def draw(w, h):
        img = T.Img(w, h, (0, 0, 0, 0))
        ppy = h / t_total
        s = int(CREST_D * ppy)
        if s < 6:
            return img
        cx, cy = w / 2.0, t_mid * ppy
        P2.ring(img, cx, cy, 0.0, s * 0.5, T.hexc("2E0A06"))
        P2.ring(img, cx, cy, 0.0, s * 0.43, T.hexc("6E1A12"))
        rs = max(4, int(s * 0.8))
        for lname, m, _mode, _hh in E.layer_masks("tusk_crest", rs, rs):
            P2.paint_mask(img, m, CREST_TONES.get(lname, IVORY), int(cx - rs / 2.0), int(cy - rs / 2.0))
        return img
    return draw


# ------------------------------------------------------------------------------------------------ parts

def _settle(mesh):
    """Puts a wobbled mesh's foot back on the table: the foot ring's vertices (the only ones within WOBBLE of
    z 0) flat on it, so no part of the foot floats."""
    out = mesh.copy()
    out.p = [(x, y, 0.0 if z < WOBBLE * 1.01 else z) for x, y, z in mesh.p]
    return out


def _brew(body, cx, cy):
    """The brew surface: a fan over the wobbled inner wall's own bottom ring (BODY's last point, found by
    position: no other ring comes within 0.019 of it), so it closes the mug exactly at any wobble (twelve
    corners, ten triangles); one disc chart centred on (cx, cy), seen from above with s along +Y and t along +X,
    as geom.disc's."""
    r_in, z_in = BODY[-1]
    ring = {}
    for x, y, z in body.p:
        if abs(z - z_in) < 2.0 * WOBBLE and abs(math.hypot(x - cx, y - cy) - r_in) < 2.0 * WOBBLE:
            ring[(round(x, 6), round(y, 6), round(z, 6))] = (x, y, z)
    pts = sorted(ring.values(), key=lambda q: math.atan2(q[1] - cy, q[0] - cx))
    r = max(math.hypot(x - cx, y - cy) for x, y, _z in pts)
    mesh = G.Mesh()
    ch = mesh.chart(2.0 * r, 2.0 * r, "brew")
    vs = [mesh.vert(p, (0.0, 0.0, 1.0), ch, p[1] - cy + r, p[0] - cx + r) for p in pts]
    for i in range(1, len(vs) - 1):
        mesh.tri(vs[0], vs[i], vs[i + 1])
    return mesh


def _tusk(cx, cy):
    """The tusk handle: from its root in the upper wall out, down and back into the wall near the foot (a cubic
    curve in the vertical plane at HANDLE_DEG), tapering from TUSK_R[0] to TUSK_R[1]."""
    a = math.radians(HANDLE_DEG)

    def at(q):
        return (cx + math.cos(a) * q[0], cy + math.sin(a) * q[0], q[1])
    path = G.bezier_path(at(TUSK[0]), at(TUSK[1]), at(TUSK[2]), at(TUSK[3]), 5)
    r0, r1 = TUSK_R
    return G.sweep(path, lambda t: r0 * (1.0 - t) ** 0.9 + r1 * t, 6, name="tusk")


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (0.2, 0.2, 0.22)
    d.budget = 200
    d.kind = "table"
    d.atlas = {"atlas": 128}
    add = d.add

    # centre the footprint: the body's foot on the front and right, the tusk on the back and left
    (x0, y0, _z0), (x1, y1, _z1) = _tusk(0.0, 0.0).bounds()
    r = BODY[0][0] + WOBBLE
    cx, cy = -(min(x0, -r) + max(x1, r)) / 2.0, -(min(y0, -r) + max(y1, r)) / 2.0

    # the body: a hand-thrown lathe with a slight wobble, the crest on its front
    body = _settle(G.wobble(G.lathe(BODY, 12), WOBBLE, seed=7, freq=14.0))
    body = G.translate(body, cx, cy, 0.0)
    brew = _brew(body, cx, cy)
    t_mid, t_total = _profile_t(BODY, CREST_Z)
    span = CREST_D * 1.25 / (2.0 * math.pi * BODY[0][0])
    add(B.Part("mug", body, paint=mug_paint(cx, cy), seed=11, weight=1.6, ao_floor=0.75,
               decals={0: P2.wrap_front(d_crest(t_mid, t_total), span)}))

    # the brew, closing the inner wall's ring
    add(B.Part("brew", brew, paint=p_brew, seed=21, weight=1.0, ao_floor=0.85))

    # the tusk handle
    add(B.Part("handle", _tusk(cx, cy), paint=p_tusk, seed=31, weight=1.0, ao_floor=0.75))

    d.collision = ([], [])
    d.particles = []
    return d
