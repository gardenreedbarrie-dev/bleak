"""19320 CupSW, the Stormwind coffee cup (a table prop), CAFE.SPEC.md section 5.8.1.

A porcelain coffee cup on its saucer, in the Stormwind dress of the espresso machine's cups, shaped so a player
names it at a glance from a table or the pickup counter: a wide white cup on a wide saucer (the cup-and-saucer
silhouette), a chunky loop handle turned to show its hole in the usual 3/4 view, a thick royal-blue band right
under a gold rim with a gold lion medallion standing on its front, coffee with a big pale latte-art heart whose
point faces the viewer, and a small steam wisp, so it reads as a hot coffee even when the heart is edge-on. 0.22
(Y) x 0.22 (X) x 0.15 yd (about 1.6x real size, in line with the stock tankards), front (+X) toward the customer.

Cues and their size at 10 yd (about 95 px per yard): the saucer (0.22 across, a royal-blue rim band 0.024 wide
on top and its blue edge), the cup (0.165 across at its flared lip, 0.14 tall), the handle (a loop 0.11 tall, a
tube 0.03 thick, a 0.035 x 0.05 hole), the blue band (0.06 tall) under the gold rim (0.012), the medallion (0.066
across), the latte heart (0.09 across), the steam (about 0.2 tall).

Deviations from the section 5.8.1 design, for recognizability:
- the handle points 115 degrees round from the front (toward +Y and a little back), square to the hero and game
  views' line of sight (about 26 degrees), so its hole shows instead of the handle seen end-on;
- the coffee disc turns 26 degrees with it, so the heart's point faces those views;
- the lion medallion is its own disc part with its own dense chart (on the cup's wrapped 128 chart a lion would
  be a few texels), pressed onto the front facet of the cup as a shallow boss and painted two-tone: a dark-blue
  lion on gold;
- the cup's outer wall has its normals tilted toward the sky and its lower porcelain painted bright white: an
  upright wall under a sun from above renders as grey stoneware otherwise;
- added: the gold rim, the medallion, and the optional tiny steam (emitters.cup_steam, kept short so the bounds
  stay near the cup).
"""

import math

from .. import build as B
from .. import emblem as E
from .. import emitters as EM
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "CupSW"
DISPLAY = 19320

ENAMEL = T.hexc("2E4E8C")
NAVY = T.hexc("1A2C5C")
GOLD = T.hexc("E8B848")
PORCELAIN = T.hexc("F6F1E6")

# the saucer: under the rim, the rim, the dish (r, z); the cup's foot hides the dish's open centre
SAUCER_R = 0.11
SAUCER = [(0.084, 0.0), (SAUCER_R, 0.021), (0.04, 0.0125)]
SAUCER_BAND = 0.086            # the blue band on the saucer's top, out from this radius
# the cup: foot, a steep lower wall (a taper facing more than about 20 degrees down gets no sun and reads as grey
# stoneware), the wall flaring out to the lip (a cup, not a mug), the inner wall sloping down to the coffee (r, z)
CUP = [(0.06, 0.012), (0.068, 0.045), (0.083, 0.15), (0.072, 0.141)]
CUP_SIDES = 12
# the chart's seam beside the handle's root (the handle at 115 degrees covers it from about 103 to 127), not on
# the back where the barista sees it; the vertices stay at 15 + 30k degrees, so a facet, not a ridge, faces the
# front (the medallion sits on it)
CUP_SEAM = math.radians(105.0)
COFFEE_Z = 0.141                # 0.009 under the rim, so the heart shows from the low 3/4 views
LIFT = 0.45                    # how far the outer wall's normals tilt toward the sky (_lift_normals)
LIP_Z = 0.138                  # the gold rim: the outer wall above this
BAND = (0.078, LIP_Z)          # the royal-blue band on the outer wall (z), right under the gold rim
# the handle: a loop square to the usual 3/4 view
VIEW_DEG = 26.0                # the hero shot looks from here (game views from 18)
HANDLE_DEG = VIEW_DEG + 89.0
HANDLE_D, HANDLE_Z = 0.081, 0.080   # the loop's centre: distance from the cup's axis, height
HANDLE_R, HANDLE_TUBE = 0.040, 0.015
HANDLE_ARC = 0.71 * math.pi    # half the loop's arc, from straight out; both ends sink 2 mm into the wall
# the lion medallion: radius, centre height, its gap off the front facet, and how far its centre stands out (a
# shallow boss: the fan's triangles span the facet's two ridges, and a flat disc dips under them)
MEDAL_R, MEDAL_Z, MEDAL_GAP, MEDAL_BOSS = 0.033, 0.107, 0.0025, 0.006


def _profile_r(profile, t):
    """The radius of a lathe profile at chart t (yd from its last point): a flat dish's rings painted by t stay
    round, where the radius of a texel's position dips between the lathe's sides."""
    arc = [0.0]
    for (r0, z0), (r1, z1) in zip(profile, profile[1:]):
        arc.append(arc[-1] + math.hypot(r1 - r0, z1 - z0))
    a = arc[-1] - t
    for k in range(len(profile) - 1):
        if a <= arc[k + 1] or k == len(profile) - 2:
            f = T.clamp01((a - arc[k]) / ((arc[k + 1] - arc[k]) or 1.0))
            return profile[k][0] + (profile[k + 1][0] - profile[k][0]) * f, k
    return profile[-1][0], len(profile) - 2


def _wall_r(z):
    """The cup's outer-wall radius (the lathe's corner radius) at height z."""
    for (r0, z0), (r1, z1) in zip(CUP[:3], CUP[1:3]):
        if z0 <= z <= z1:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return CUP[2][0]


def _wall_x(y, z):
    """How far forward (x) the faceted outer wall reaches at (y, z): the nearest of the front facets' planes
    (the lathe is a convex polygon, so the wall along +X is the minimum over its half-planes)."""
    a = _wall_r(z) * math.cos(math.pi / CUP_SIDES)
    best = 1.0
    for k in range(-2, 3):
        ang = k * 2.0 * math.pi / CUP_SIDES
        best = min(best, (a - y * math.sin(ang)) / math.cos(ang))
    return best


def _lift_normals(mesh, k, z_max):
    """Tilts the outward-facing normals of a lathe's outer wall up toward the sky by k (0..1), below z_max: an
    upright porcelain wall under a sun from above gets mostly the bluish ambient and renders grey; bent normals
    (an old trick for small props) light it as the eye expects a white cup to look."""
    out = mesh.copy()
    ns = []
    for (x, y, z), n in zip(mesh.p, mesh.n):
        rr = math.hypot(x, y) or 1.0
        if z <= z_max + 1e-6 and (n[0] * x + n[1] * y) / rr > 0.3:
            n = G.norm((n[0] * (1.0 - k), n[1] * (1.0 - k), n[2] * (1.0 - k) + k))
        ns.append(n)
    out.n = ns
    return out


# ----------------------------------------------------------------------------------------------- paints

def p_cup(ctx, seed, p):
    """White porcelain: outside, a royal-blue band (lit toward the light) under a gold rim, and a painted bounce
    light from the saucer on the lower wall (it faces away from the sun and would read as grey stoneware);
    inside, white shading a little toward the coffee (by facing, so the inner wall stays white)."""
    c = T.g_ceramic(ctx, seed, {"color": PORCELAIN})
    x, y, z = ctx.pos
    rr = math.hypot(x, y) or 1.0
    outward = (ctx.n[0] * x + ctx.n[1] * y) / rr
    if outward < 0.0:
        return T.mix(c, T.scale(PORCELAIN, 0.78), T.smoothstep(CUP[2][1], COFFEE_Z, z) * 0.5)
    if z > LIP_Z:
        g = T.g_gold(ctx, seed + 1, {"streak": False, "patina": 0.0})
        return T.mix(g, T.hexc("FFF0B0"), T.clamp01(ctx.n[0] * 0.5 + 0.2) * 0.4)
    if z >= BAND[0]:
        k = T.clamp01(0.5 + 0.5 * (ctx.n[0] * 0.8 + ctx.n[1] * 0.4))
        c = T.mix(T.scale(ENAMEL, 0.72), T.scale(ENAMEL, 1.12), k)     # darker: the lifted normals light it
        # a soft gloss streak down the band
        a = math.atan2(y, x)
        return T.mix(c, T.hexc("9AB4E8"), T.smoothstep(0.22, 0.0, abs(a - 0.55)) * 0.35)
    return T.mix(c, (1.0, 1.0, 1.0), 0.5 + 0.5 * T.smoothstep(BAND[0], CUP[0][1], z))


def p_saucer(ctx, seed, p):
    """Porcelain with a royal-blue rim band on the top and a blue edge."""
    c = T.g_ceramic(ctx, seed, {"color": PORCELAIN})
    r, seg = _profile_r(SAUCER, ctx.t)
    if seg == 0:
        # the edge under the rim
        return T.mix(T.scale(ENAMEL, 0.75), T.scale(ENAMEL, 1.15), T.clamp01(ctx.n[0] * 0.5 + 0.5))
    if r > SAUCER_BAND:
        return T.mix(ENAMEL, T.scale(ENAMEL, 1.35), T.smoothstep(SAUCER_BAND, SAUCER_R, r) * 0.6)
    return c


def p_coffee(ctx, seed, p):
    """Golden crema darkening to the rim, a big pale latte-art heart (warm cream, not white: the disc faces up
    into both the bake's key light and the sun, and a white heart loses its edge against the crema) with a crisp
    pointed outline and a darker crema ring round it."""
    return T.g_coffee(ctx, seed, {"heart": True, "outline": True, "crema": T.hexc("A8682E"),
                                  "coffee": T.hexc("3A1A0A"), "milk": T.hexc("F4E6CA")})


def p_medal(ctx, seed, p):
    """Lit gold under the medallion decal (its rim shows between the disc's sides and the decal's circle)."""
    return T.mix(T.scale(GOLD, 0.7), T.hexc("FFE89A"), T.clamp01(0.4 + 0.4 * ctx.n[2]))


# ---------------------------------------------------------------------------------------------- decals

# the lion's layers (emblem.EMBLEMS["lion_head"]) in two tones: the mane, ears and features dark blue on gold
LION_TONES = {"mane": NAVY, "mane_inner": ENAMEL, "ear_l": NAVY, "ear_r": NAVY, "ear_l_in": GOLD,
              "ear_r_in": GOLD, "face": T.hexc("F6D676"), "bridge": T.hexc("FFE89A"),
              "muzzle_l": T.hexc("FFE89A"), "muzzle_r": T.hexc("FFE89A")}


def d_medallion(w, h):
    """The medallion's face: a dark bronze rim, a lit gold field and the lion head in two tones (a dark-blue
    mane and features on a gold face), high contrast so it holds as a crest at about 11 px on screen."""
    img = T.Img(w, h, (0, 0, 0, 0))
    s = min(w, h)
    cx, cy = w / 2.0, h / 2.0
    R = s * 0.46                   # inside the octagon's flats
    P2.ring(img, cx, cy, 0.0, R, T.hexc("5A3608"))
    P2.ring(img, cx, cy, 0.0, R * 0.86, GOLD)
    P2.ring(img, cx, cy, R * 0.74, R * 0.86, T.hexc("FFE89A"), a0=math.pi * 0.9, a1=math.pi * 1.6)
    if s < 12:
        return img
    ls = max(4, int(R * 1.7))
    for lname, m, mode, _hh in E.layer_masks("lion_head", ls, ls):
        col = LION_TONES.get(lname, NAVY)
        P2.paint_mask(img, m, col, int(cx - ls / 2.0), int(cy - ls / 2.0))
    return img


# ------------------------------------------------------------------------------------------------ parts

def _medallion():
    """The medallion: an 8-sided disc faced to the front facet (tilted with the wall), then each vertex pressed
    back to MEDAL_GAP off the faceted wall, so the disc hugs the cup instead of floating past the facet's edges,
    and its centre pushed out MEDAL_BOSS into a shallow boss, so no part of the fan dips under the facet ridges
    it spans (the front facet is only 0.04 wide at the medallion's height)."""
    xc = _wall_x(0.0, MEDAL_Z)
    slope = (_wall_x(0.0, MEDAL_Z + 0.01) - xc) / 0.01
    disc = G.disc(MEDAL_R, 8, 0.0, name="medal")
    disc = G.transform(disc, G.mat_chain(G.mat_translate(xc, 0.0, MEDAL_Z), G.mat_disc_facing((1.0, 0.0, -slope))))
    out = disc.copy()
    out.p = [(_wall_x(y, z) + MEDAL_GAP, y, z) for _x, y, z in disc.p]
    centre = min(range(len(out.p)), key=lambda i: math.hypot(out.p[i][1], out.p[i][2] - MEDAL_Z))
    x, y, z = out.p[centre]
    out.p[centre] = (x + MEDAL_BOSS, y, z)
    return out


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (0.22, 0.22, 0.15)
    d.budget = 200
    d.kind = "table"
    d.atlas = {"atlas": 128}
    add = d.add

    # the saucer: a wide shallow dish with a blue rim
    add(B.Part("saucer", G.lathe(SAUCER, 12), paint=p_saucer, seed=11, weight=0.8, ao_floor=0.85))

    # the cup: porcelain with the blue band and the gold rim
    cup = _lift_normals(G.lathe(CUP, CUP_SIDES, seam=CUP_SEAM), LIFT, CUP[2][1])
    add(B.Part("cup", cup, paint=p_cup, seed=21, weight=1.4, ao_floor=0.95))

    # the lion medallion on the band's front, with its own dense chart
    add(B.Part("medallion", _medallion(), paint=p_medal, seed=25, weight=3.2, ao_floor=0.9,
               decals={"medal": d_medallion}))

    # the coffee, turned so the heart's point faces the usual view; 12 sides of r 0.076 cover the inner wall's
    # ring (apothem 0.0734 against 0.072) at any turn, and its corners stay inside the outer wall
    coffee = G.transform(G.disc(0.076, 12, COFFEE_Z), G.mat_rot_z(math.radians(VIEW_DEG)))
    add(B.Part("coffee", coffee, paint=p_coffee, seed=31, weight=2.4, ao_floor=0.9))

    # the handle: a round loop (an open torus arc, seven segments) whose ends sink into the wall below the
    # coffee, so neither end shows inside the cup
    ring = G.torus(HANDLE_R, HANDLE_TUBE, 7, 4, arc=2.0 * HANDLE_ARC, start=-HANDLE_ARC)
    a = math.radians(HANDLE_DEG)
    handle = G.transform(ring, G.mat_chain(
        G.mat_translate(math.cos(a) * HANDLE_D, math.sin(a) * HANDLE_D, HANDLE_Z), G.mat_rot_z(a),
        G.mat_rot_x(math.pi / 2)))
    add(B.Part("handle", handle, paint=("ceramic", {"color": PORCELAIN}), seed=41, weight=0.9, ao_floor=0.75))

    d.collision = ([], [])
    d.particles = [EM.cup_steam((0.0, 0.0, COFFEE_Z + 0.025), speed=0.08, life=1.0)]
    return d
