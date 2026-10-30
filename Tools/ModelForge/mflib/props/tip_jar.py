"""19323 TipJar, the tip jar on the counter (a table prop for both cafés), CAFE.SPEC.md section 5.8.1.

An open glass jar half full of coins, shaped so a customer names it at a glance from the queue: a squat mason jar
(a heavy heel, straight walls, a round shoulder, a thick rolled rim round an open mouth) in clear, faintly
blue-grey glass drawn on both sides, with a bright highlight round the rim. Inside, a bed of mixed gold and silver
coins fills the bottom, and six separate chunky coins lie on it, tilted every which way against each other and the
glass, so the jar is about half full and empty glass shows above them; one more coin leans on the rim and sticks
out of the mouth, the "someone just tipped" cue. A cream paper label on the front says "TIPS" in dark vector
capitals inside a dark border. Neutral, so it serves both cafés. 0.25 (Y) x 0.25 (X) x 0.3 yd (the rim at 0.245,
the leaning coin to 0.283), front (+X) toward the customers.

Cues and their size at 10 yd (about 95 px per yard): the jar's silhouette (0.24 across, 0.245 tall) with the rolled
rim (0.025 thick, white-lit), the empty glass above the coins (0.11 tall), the coins (0.076 across, 0.015 thick:
gold D4A82A and silver C8CCD4), the leaning coin over the rim (0.08), the label (0.12 x 0.075, letters about 0.05
tall inside a dark border 3 px wide at mip 0).

Deviations from section 5.2.5, for recognizability:
- the glass body is a little clearer than alpha 70-110 (about 50: alpha 0.2) with two narrow streaks at about
  150, so the coins read through it at full strength; the rolled rim is near-opaque white glass (alpha 0.8 at its
  lit top), which is what makes the mouth read as open glass at 15 yd;
- the coins are cutout (alpha 255, both sides drawn) with only their top face closed: a coin's top face seen from
  below stands in for its bottom face, which keeps eight coins in the 300-triangle budget;
- the label is its own opaque patch on the front (a curved quad strip just outside the glass, its normals tilted
  toward the sky as cup_sw's are), with its own, denser chart, so "TIPS" stays sharp in the 128 atlas; it sits low,
  over the coin bed, so the coins above it and the empty glass over them stay in view.
"""

import math

from .. import build as B
from .. import font as F
from .. import geom as G
from .. import tex as T

NAME = "TipJar"
DISPLAY = 19323

PAPER = T.hexc("FFF2D0")
INK = T.hexc("3A1C0E")
BORDER = T.hexc("2E1A10")       # the label's dark border: it holds the label's shape at 8 yd
RED = T.hexc("A8402A")          # a thin red line inside the border
GOLD, SILVER = T.hexc("D4A82A"), T.hexc("C8CCD4")
COINS = (GOLD, SILVER)
GAP = T.hexc("6A4A1E")          # the gaps between the coins of the bed: dark enough to part them
GLINT = T.hexc("FFF8DC")
TINT = T.hexc("D6E2EA")         # the glass: a light blue-grey
TINT_DARK = T.hexc("5A6874")    # its outline bands

# the jar (r, z): a straight wall (its heel a painted dark band), a round shoulder into a short neck, then the
# rolled rim (its own chart) bulging out round the open mouth
JAR_BODY = [(0.12, 0.0), (0.12, 0.178), (0.094, 0.214)]
RIM = [(0.094, 0.214), (0.113, 0.229), (0.09, 0.245)]
JAR_R = 0.12
RIM_Z = 0.245
HEEL_Z = 0.022                  # the outline band at the heel: the glass below this
SHOULDER = (0.178, 0.214)       # the outline band over the shoulder (z)
GLASS_STREAKS = ((0.3, 0.022), (0.68, 0.012))   # (u round the jar, half width): u 0.5 is the front
# the coin bed: a low drum just inside the glass with a shallow cone on top, painted as coin faces
BED = [(0.113, 0.004), (0.113, 0.052), (0.0, 0.07)]
BED_R = 0.113
LIFT = 0.55                     # how far the label's and the bed wall's normals tilt toward the sky
# the label on the front: angular half width, bottom and top (z), its radius just outside the glass
LABEL_A = math.radians(30.0)
LABEL_Z = (0.03, 0.105)
LABEL_R = JAR_R + 0.0035
# the loose coins: (x, y, z of the centre, tilt in degrees, tilt azimuth in degrees, metal 0 gold / 1 silver). Six
# lie on the bed, leaning on it, on each other and on the glass, their faces turned toward the front; the last one
# leans back against the far side of the rim, its face toward the customers over the mouth
COIN_R, COIN_T = 0.038, 0.015
LOOSE = [
    (0.012, 0.018, 0.08, 12.0, 200.0, 0),
    (0.058, 0.04, 0.09, 38.0, 20.0, 1),
    (0.03, -0.058, 0.096, 55.0, -40.0, 0),
    (-0.052, 0.046, 0.104, 62.0, 160.0, 0),
    (-0.06, -0.03, 0.098, 48.0, 200.0, 1),
    (0.004, -0.004, 0.118, 24.0, 60.0, 0),
    (-0.068, 0.022, 0.246, 75.0, 18.0, 0),
]
# the light's direction in the model (from the front, the right and above), for painted highlights
LIGHT = (0.4, -0.3, 0.85)


def _hash(i, j, k, seed):
    """A deterministic value in [0, 1) for an integer cell."""
    h = (i * 374761393 + j * 668265263 + k * 2147483647 + seed * 144665) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65536.0


def _metal(c, light):
    """A coin metal's colour: the albedo, lit toward `light` (0..1) with a warm white highlight."""
    return T.mix(T.scale(c, 0.78), T.mix(c, (1.0, 0.97, 0.86), 0.35), light)


def _coin_faces(u, v, cells, wrap, r_range, seed, lu, lv):
    """Overlapping coin faces on a jittered grid over the 2D coordinates (u, v) in yd: cells (cu, cv) per coin,
    `wrap` columns round (0 = no wrap), radii in r_range, the light toward (lu, lv) in the same plane; gold and
    silver about half and half. The top coin covering the texel wins; each has a raised rim lit toward the light,
    a dark groove inside it and a field shading toward its centre. Dark gaps between the coins."""
    cu, cv = cells
    gi, gj = int(math.floor(u / cu)), int(math.floor(v / cv))
    best = None
    for i in (gi - 1, gi, gi + 1):
        hi = i % wrap if wrap else i
        for j in (gj - 1, gj, gj + 1):
            ccu = (i + 0.2 + 0.6 * _hash(hi, j, 4, seed)) * cu
            ccv = (j + 0.2 + 0.6 * _hash(hi, j, 5, seed)) * cv
            r = r_range[0] + (r_range[1] - r_range[0]) * _hash(hi, j, 6, seed)
            d = math.hypot(u - ccu, v - ccv)
            if d < r:
                h = _hash(hi, j, 7, seed)
                if best is None or h > best[0]:
                    best = (h, d / r, int(_hash(hi, j, 8, seed) < 0.45), (u - ccu) / r, (v - ccv) / r)
    if best is None:
        return GAP
    _h, q, k, du, dv = best
    c = COINS[k]
    if q > 0.76:
        toward = (du * lu + dv * lv) / (q or 1.0)
        return _metal(c, T.clamp01(0.55 + 0.45 * toward))
    if q > 0.64:
        return T.scale(c, 0.62)
    return _metal(c, 0.4 + 0.35 * (1.0 - q))


# ----------------------------------------------------------------------------------------------- paints

def p_jar(ctx, seed, p):
    """Clear glass with a light blue-grey tint and two narrow vertical streaks; darker outline bands at the heel
    and over the shoulder hold the jar's outline on a bright counter. The rolled rim (its own chart) is bright
    white glass, nearly opaque along its lit top, so the open mouth reads at 15 yd."""
    z = ctx.pos[2]
    if ctx.chart.endswith("_rim"):
        top = T.smoothstep(RIM[0][1], RIM[1][1] + 0.004, z)
        c = T.mix(T.hexc("C8D6E0"), (1.0, 1.0, 1.0), 0.45 + 0.55 * top)
        return (c[0], c[1], c[2], 0.55 + 0.3 * top)
    if z < HEEL_Z or SHOULDER[0] < z < SHOULDER[1]:
        return (TINT_DARK[0], TINT_DARK[1], TINT_DARK[2], 0.5)
    c, a = TINT, 0.2
    for centre, wdt in GLASS_STREAKS:
        k = T.smoothstep(wdt, 0.0, abs(ctx.u - centre))
        c = T.mix(c, (1.0, 1.0, 1.0), k)
        a = max(a, 0.6 * k)
    return (c[0], c[1], c[2], a)


def p_bed(ctx, seed, p):
    """The coin bed: round its wall (behind the glass) big coin faces on a jittered grid of twelve columns; on its
    shallow cone, faces in plan."""
    x, y, z = ctx.pos
    if z < BED[1][1] - 1e-4:
        a = math.atan2(y, x)
        la = -math.sin(a) * LIGHT[0] + math.cos(a) * LIGHT[1]
        n = math.hypot(la, LIGHT[2]) or 1.0
        return _coin_faces(a * BED_R, z, (2.0 * math.pi * BED_R / 12.0, 0.05), 12, (0.032, 0.038), seed,
                           la / n, LIGHT[2] / n)
    n = math.hypot(LIGHT[0], LIGHT[1])
    return _coin_faces(x, y, (0.06, 0.06), 0, (0.032, 0.04), seed + 1, LIGHT[0] / n, LIGHT[1] / n)


def coin_paint(k):
    """Paint for loose coins of metal k: a lit raised rim, a darker groove, a raised inner ring and a centre boss
    (both lit toward the light) and a glint on the rim's lit side; milled edges."""
    base = COINS[k]

    def p_coin(ctx, seed, p):
        if ctx.chart.endswith("_top"):
            cr = min(ctx.cw, ctx.ch) / 2.0
            X = (ctx.s - ctx.cw / 2.0) / cr
            Y = (ctx.t - ctx.ch / 2.0) / cr
            q = math.hypot(X, Y)
            toward = T.clamp01(0.5 + 0.5 * (Y * 0.8 - X * 0.6) / (q or 1.0))
            if q > 0.78:
                c = _metal(base, 0.35 + 0.6 * toward)
                return T.mix(c, GLINT, 0.8) if toward > 0.88 else c
            if q > 0.64:
                return T.scale(base, 0.5)
            if 0.4 < q < 0.52 or q < 0.18:
                return _metal(base, 0.45 + 0.5 * toward)
            return _metal(base, 0.3)
        lit = _metal(base, 0.6)
        return T.scale(lit, 0.62) if int(ctx.s / 0.008) % 2 else lit
    return p_coin


# ---------------------------------------------------------------------------------------------- decals

def d_label(w, h):
    """The paper label: a dark border (painted by pixel distance from the edge, about 7 % of the label's height,
    at least 2 px), a thin red line inside it, cream paper and "TIPS" in dark brown condensed vector capitals with
    a cream outline."""
    img = T.Img(w, h, (0, 0, 0, 0))
    bw = max(2, int(round(h * 0.07)))
    for y in range(h):
        for x in range(w):
            d = min(x, y, w - 1 - x, h - 1 - y)
            n = T.noise(x * 0.15, y * 0.15, 3)
            c = T.mix(T.scale(PAPER, 0.92), PAPER, 0.6 + 0.4 * n)
            if d < bw:
                c = T.mix(BORDER, T.hexc("5A3A24"), 0.3 * n)
            elif h >= 20 and d == bw + 1:
                c = RED
            img.set(x, y, c, 1.0)
    m_in = bw + (3 if h >= 20 else 1)
    try:
        cap = F.fit_cap("TIPS", w - 2 * m_in, h - 2 * m_in, weight=0.15, min_cap=4.0, squeeze=0.85)
        m = F.vector_mask("TIPS", cap, weight=0.15, squeeze=0.85)
        F.two_tone(img, m, INK, T.hexc("FFF4D8"), (w - m.w) // 2, (h - m.h) // 2, 1, None)
    except ValueError:
        if min(w, h) >= 32:
            raise           # at full size a text that does not fit is an error (section 5.5.1)
    return img


# ------------------------------------------------------------------------------------------------ parts

def _label_mesh(r, cols=4):
    """The label: a strip of `cols` flat quads round the front at radius r from -LABEL_A to +LABEL_A, between
    the LABEL_Z heights; one chart, s from -Y to +Y (left to right as seen from the front), t down; its normals
    tilted LIFT toward the sky."""
    m = G.Mesh()
    z0, z1 = LABEL_Z
    width = r * 2.0 * LABEL_A
    ch = m.chart(width, z1 - z0, "label")
    top, bot = [], []
    for i in range(cols + 1):
        a = -LABEL_A + 2.0 * LABEL_A * i / cols
        n = (math.cos(a), math.sin(a), 0.0)
        s = width * i / cols
        nn = G.norm((n[0] * (1.0 - LIFT), n[1] * (1.0 - LIFT), LIFT))
        top.append(m.vert((r * n[0], r * n[1], z1), nn, ch, s, 0.0))
        bot.append(m.vert((r * n[0], r * n[1], z0), nn, ch, s, z1 - z0))
    for i in range(cols):
        m.tri(top[i], bot[i], bot[i + 1])
        m.tri(top[i], bot[i + 1], top[i + 1])
    return m


def _coin(x, y, z, tilt, az, sides=8):
    """One chunky coin: an 8-sided drum with its top face (a fan from one rim vertex, sides - 2 triangles),
    centred on (x, y, z), tilted `tilt` degrees toward the azimuth `az` (degrees from +X)."""
    coin = G.cylinder(COIN_R, COIN_T, sides, False, z0=-COIN_T / 2.0)
    ch = coin.chart(2 * COIN_R, 2 * COIN_R, "coin_top")
    ring = []
    for i in range(sides):
        a = math.pi + 2.0 * math.pi * i / sides
        cx, cy = math.cos(a) * COIN_R, math.sin(a) * COIN_R
        ring.append(coin.vert((cx, cy, COIN_T / 2.0), (0.0, 0.0, 1.0), ch, cy + COIN_R, cx + COIN_R))
    for i in range(1, sides - 1):
        coin.tri(ring[0], ring[i], ring[i + 1])
    a = math.radians(az)
    return G.transform(coin, G.mat_chain(G.mat_translate(x, y, z), G.mat_rot_z(a), G.mat_rot_y(math.radians(tilt))))


def _lift(mesh, k):
    """Tilts the outward-facing normals of a lathe's wall up toward the sky by k (cup_sw's trick), so the coins
    read bright through the glass."""
    out = mesh.copy()
    ns = []
    for (x, y, z), n in zip(mesh.p, mesh.n):
        rr = math.hypot(x, y) or 1.0
        if (n[0] * x + n[1] * y) / rr > 0.3:
            n = G.norm((n[0] * (1.0 - k), n[1] * (1.0 - k), n[2] * (1.0 - k) + k))
        ns.append(n)
    out.n = ns
    return out


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (0.25, 0.25, 0.3)
    d.budget = 300
    d.kind = "table"
    d.atlas = {"atlas": 128}
    add = d.add

    # the coin bed in the bottom of the jar
    add(B.Part("coin_bed", _lift(G.lathe(BED, 12), LIFT), paint=p_bed, seed=11, weight=1.2, ao_floor=0.9))

    # the loose coins: six on the bed, one leaning on the rim; gold and silver in their own parts
    for k, name in ((0, "coins_gold"), (1, "coins_silver")):
        coins = [_coin(x, y, z, tilt, az) for x, y, z, tilt, az, m in LOOSE if m == k]
        add(B.Part(name, G.merge(coins), "cutout", paint=coin_paint(k), seed=21 + k, weight=1.6, ao_floor=0.85))

    # the label on the front
    add(B.Part("label", _label_mesh(LABEL_R), paint=("flat", {"color": PAPER}), seed=31, weight=3.0, ao_floor=0.9,
               decals={"label": d_label}))

    # the jar: one shell of glass, both sides drawn (glass1), so the far wall and the whole rim ring show
    jar = G.merge([G.lathe(JAR_BODY, 12, name="jar"), G.lathe(RIM, 12, name="jar_rim")])
    add(B.Part("jar", jar, "glass1", paint=p_jar, seed=41, weight=0.8, ao_floor=1.0))

    d.collision = ([], [])
    d.particles = []
    return d
