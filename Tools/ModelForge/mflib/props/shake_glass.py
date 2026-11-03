"""19322 ShakeGlass, the milkshake glass (a table prop for both cafés), CAFE.SPEC.md section 5.8.1.

A soda-fountain milkshake, shaped so a player names it at a glance from a table or the pickup counter: a tall
fluted sundae glass (a round foot pinched into a stem, a bowl flaring to a wide rim) full of bright strawberry-pink
shake, a big whipped-cream swirl piled over the rim with a strawberry drizzle, a glossy red cherry on its stem
on top, and a thick red-and-white striped bendy straw leaning out of it. Neutral, so it serves both cafés. 0.16
(Y) x 0.16 (X) x 0.5 yd (about 1.6x real size, in line with the stock tankards).

Cues and their size at 10 yd (about 95 px per yard): the glass's tulip silhouette (0.15 across at the rim, 0.3
tall), the pink shake mass (0.13 across at the top, 0.22 tall, seen through the glass), the cream swirl (0.15
across, 0.12 tall, a piped tier under a rounded cone), the cherry (0.064 across), the straw (0.034 thick, 0.33
long, stripes 0.05 wide).

Deviations from the section 5.8.1 design and section 5.2.5, for recognizability and the 300 triangle budget:
- the straw is a bendy straw (its top 0.08 kinks sideways), the soda fountain's own cue, and leans toward +Y and
  the back so it stands clear of the cream and the cherry in the 3/4 views;
- the cream is a round piped tier under a rounded cone, twisted 75 degrees (a soft-serve swirl) on a four-lobed
  lathe (three vertices per lobe, so the ribs stay round instead of creasing), not a wavy lathe alone;
- the fluting is five broad ribs pushed into the glass's ten sides (geom.flutes), so it costs no triangles;
- the stem is a pinch between the foot and the bowl (not a short column), which leaves the triangles for the
  cream;
- the cherry has no stem: a 0.01 yd stem is a hairline at play distance;
- the shake is painted lit (bright toward the light, a vertical gloss streak) and its wall's normals tilt toward
  the sky: it stands upright under a sun from above, behind the glass, and a flat pink would render plum;
- the glass body is clearer than section 5.2.5's alpha 70-110 (about 25: alpha 0.10) and its streaks brighter
  than 180-230 (up to about 250: 0.98), so the pink shows through at full strength and the glass still reads by
  its streaks and its rim;
- added: the strawberry drizzle on the cream and the thick glass foot and stem (clear glass, more opaque than the
  bowl, with a dark outline on the table and a lit top edge, so they read as glass, not metal).
"""

import math

from .. import build as B
from .. import geom as G
from .. import tex as T

NAME = "ShakeGlass"
DISPLAY = 19322

PINK = T.hexc("FF4C76")             # saturated and warm: the bake's cool shadows and the blue ambient on an
                                    # upright wall turn a pastel or bluish pink lilac or plum
CHERRY = T.hexc("C8102A")
STRAW_RED = T.hexc("E02C34")

# the glass: the foot's edge, the stem's pinch, the bowl's bottom, the belly, the rim (r, z)
GLASS = [(0.062, 0.0), (0.017, 0.04), (0.04, 0.085), (0.057, 0.2), (0.074, 0.3)]
RIM_Z = 0.3
FLUTES, FLUTE_AMP = 5, 0.05
# the shake inside the bowl, a hair inside the flutes' valleys
SHAKE = [(0.0, 0.074), (0.032, 0.082), (0.066, 0.296)]
SHAKE_TOP = 0.296
# the whipped cream: a round piped tier (bulge, crease) under a rounded cone to the tip, twisted into a swirl
CREAM = [(0.064, 0.288), (0.077, 0.31), (0.06, 0.342), (0.036, 0.382), (0.0, 0.408)]
CREAM_LOBES, CREAM_AMP = 4, 0.03
CREAM_TWIST = math.radians(75.0)
CHERRY_R = 0.032
CHERRY_C = (0.004, -0.004, 0.43)
# the straw: from inside the shake up through the cream, leaning to +Y and the back, a bend, a short top
STRAW_R = 0.017
STRAW = [(-0.004, 0.0, 0.17), (-0.022, 0.034, 0.415), (-0.03, 0.062, 0.447), (-0.034, 0.066, 0.483)]


def _lift_normals(mesh, k):
    """Tilts a lathe's outward-facing normals up toward the sky by k (0..1): the shake's wall stands upright
    behind the glass under a sun from above and gets mostly the bluish ambient, which turns pink plum; bent
    normals (an old trick for small props) light it as a bright strawberry shake."""
    out = mesh.copy()
    ns = []
    for (x, y, _z), n in zip(mesh.p, mesh.n):
        rr = math.hypot(x, y) or 1.0
        if (n[0] * x + n[1] * y) / rr > 0.3:
            n = G.norm((n[0] * (1.0 - k), n[1] * (1.0 - k), n[2] * (1.0 - k) + k))
        ns.append(n)
    out.n = ns
    return out


# ----------------------------------------------------------------------------------------------- paints

def p_glass(ctx, seed, p):
    """Clear glass with g_glass's vertical streaks and darker rims; a bright rim band; the foot and the stem
    are thick clear glass (more opaque than the bowl), with a dark outline where the foot meets the table and a
    lit band above it, so they read as glass under the shake. The bands are at least 0.02 yd (about 1.5 texels
    on this chart) so they hold."""
    c = T.g_glass(ctx, seed, {"tint": T.hexc("EEF8FF"), "alpha": 0.1})
    z = ctx.pos[2]
    if z < 0.075:
        if z < 0.01:
            return (0.38, 0.47, 0.49, 0.6)
        # two layers of it show (the shell is drawn on both sides), so each is fairly clear
        k = T.clamp01(ctx.n[2] * 0.6 + 0.4)
        c = T.mix((0.9, 0.95, 1.0), (1.0, 1.0, 1.0), k)
        lit = T.smoothstep(0.012, 0.0, abs(z - 0.022))
        return (c[0], c[1], c[2], 0.3 + 0.4 * lit)
    if z > RIM_Z - 0.03:
        return (1.0, 1.0, 1.0, 0.85)
    if c[3] > 0.5:
        return (1.0, 1.0, 1.0, min(1.0, c[3] + 0.08))      # brighter streaks
    return c


def p_shake(ctx, seed, p):
    """A strawberry shake, painted lit as CupSW's band is: deep pink away from the light to pale pink toward
    it, one soft vertical gloss streak on the lit side, g_shake's swirls and pale froth at the top."""
    c = T.g_shake(ctx, seed, {"color": PINK, "top": SHAKE_TOP, "froth_d": 0.02})
    k = T.clamp01(0.5 + 0.5 * (ctx.n[0] * 0.8 + ctx.n[1] * 0.4))
    lit = T.mix(T.scale(PINK, 0.85), T.hexc("FF86A4"), k)
    c = T.mix(c, lit, 0.75)
    x, y, _z = ctx.pos
    a = math.atan2(y, x)
    return T.mix(c, T.hexc("FFE0EC"), T.smoothstep(0.03, 0.0, abs(a - 0.45) * 0.06) * 0.5)


def p_cream(ctx, seed, p):
    """Whipped cream with soft warm grooves along the piped swirl (lighter than g_cream's, so the creases do
    not bake to grey) and a strawberry drizzle running down from the tip."""
    x, y, z = ctx.pos
    a = math.atan2(y, x)
    g = 0.5 + 0.5 * math.cos(CREAM_LOBES * (a - CREAM_TWIST * T.clamp01((z - 0.288) / 0.12)))
    c = T.mix(T.hexc("EEE2E6"), T.hexc("FFFCF6"), T.smoothstep(0.0, 0.6, g))
    c = T.mix(c, (1.0, 1.0, 1.0), T.smoothstep(0.3, 1.0, ctx.n[2]) * 0.35)
    # three drizzle runs: each a band round the swirl that wanders down from the tip
    for k in range(3):
        a0 = k * 2.0 * math.pi / 3.0 + 0.4
        d = (a - a0 - (0.41 - z) * 9.0 + math.pi) % (2.0 * math.pi) - math.pi
        w = 0.32 * T.smoothstep(0.29, 0.36, z)
        if abs(d) < w:
            c = T.mix(T.mix(PINK, T.hexc("B81848"), 0.45), T.hexc("FFB0C8"), T.clamp01(ctx.n[2]) * 0.5)
    return c


def p_cherry(ctx, seed, p):
    """A glossy cherry, deep red underneath, with a bright highlight on top toward the light."""
    c = T.mix(T.scale(CHERRY, 0.55), T.mix(CHERRY, T.hexc("FF4050"), 0.3), T.clamp01(ctx.n[2] * 0.6 + 0.5))
    hl = T.clamp01(ctx.n[0] * 0.4 + ctx.n[1] * 0.3 + ctx.n[2] * 0.75)
    return T.mix(c, T.hexc("FFE0E0"), T.smoothstep(0.8, 0.95, hl) * 0.85)


def p_straw(ctx, seed, p):
    """Red and white candy stripes spiralling round the straw (the sweep chart: t along it, s around), a dark
    open end."""
    if ctx.chart.endswith("_cap"):
        return T.hexc("4A1018")
    q = (ctx.t / 0.10 + ctx.u) % 1.0
    c = STRAW_RED if q < 0.5 else T.hexc("FFF6F0")
    return T.mix(T.scale(c, 0.8), c, T.clamp01(ctx.n[2] * 0.5 + 0.6))


# ------------------------------------------------------------------------------------------------ parts

def _twist(mesh, angle, z0, z1):
    """Turns each vertex about the Z axis by `angle` times its height's fraction between z0 and z1 (a piped
    swirl), then re-smooths the normals."""
    out = mesh.copy()
    pts = []
    for x, y, z in mesh.p:
        a = angle * T.clamp01((z - z0) / (z1 - z0))
        ca, sa = math.cos(a), math.sin(a)
        pts.append((x * ca - y * sa, x * sa + y * ca, z))
    out.p = pts
    return G.recompute_normals(out, 89.0)


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (0.16, 0.16, 0.5)
    d.budget = 300
    d.kind = "table"
    d.atlas = {"atlas": 128}
    add = d.add

    # the shake (opaque, inside the bowl) and the cream swirl piled over the rim
    add(B.Part("shake", _lift_normals(G.lathe(SHAKE, 8), 0.5), paint=p_shake, seed=11, weight=1.2, ao_floor=0.95))
    cream = G.flutes(G.lathe(CREAM, 12), CREAM_LOBES, CREAM_AMP)
    cream = _twist(cream, CREAM_TWIST, CREAM[0][1], CREAM[-1][1])
    add(B.Part("cream", cream, paint=p_cream, seed=21, weight=1.2, ao_floor=0.95))

    # the cherry on the cream's tip: five rings, so it is round, not an octagon with pointed poles
    cherry = G.translate(G.sphere(CHERRY_R, 8, 5), *CHERRY_C)
    add(B.Part("cherry", cherry, paint=p_cherry, seed=31, weight=1.2, ao_floor=0.8))

    # the bendy straw
    straw = G.sweep(STRAW, STRAW_R, 5, caps=(False, True), name="straw")
    add(B.Part("straw", straw, paint=p_straw, seed=41, weight=1.6, ao_floor=0.8))

    # the fluted glass: one shell, so both its sides are drawn (glass1); the shake hides the bowl's far wall
    glass = G.flutes(G.lathe(GLASS, 10), FLUTES, FLUTE_AMP)
    add(B.Part("glass", glass, "glass1", paint=p_glass, seed=51, weight=0.6, ao_floor=1.0))

    d.collision = ([], [])
    d.particles = []
    return d
