"""19310 SyrupRackSW, the Stormwind syrup rack on the back bar, CAFE.SPEC.md section 5.8.1.

A two-tier walnut bar shelf of café syrups in polished brass, royal-blue enamel and white porcelain, shaped so a
player names it at a glance: a row of eight tall syrup bottles in eight loud colours (honey gold, vanilla cream,
caramel, cinnamon, chocolate, berry pink, mint and the white whipped-cream canister), each crowned by a brass
syrup pump (a collar, a stem and an L-shaped spout head), each with a colour band and one big flavour glyph,
standing against a royal-blue enamel back so every colour pops; a brass gallery rail holds them in. Above them,
on a shallower upper tier, a jar of coffee beans, a jar of sugar cubes, a stack of saucers and two porcelain
cups on saucers; on the scrolled crest, a brass "SYRUPS" plate with a gold lion at each end. Chunky Warcraft
proportions: a bullnosed plinth and shelf with brass lips, scrolled side uprights with recessed panels and gold
lions on royal-blue roundels, gold ball finials, all with a light hand-made wobble. Charm: honey, caramel and
chocolate have run down over their bottles' shoulders to the label. 1.4 (Y) x 0.4 (X) x 0.9 yd, front (+X)
toward the barista.

Deviations from the section 5.8.1 design, for recognizability and the readability rule (>= 0.06 yd):
- every syrup bottle carries a pump (a brass collar, a 0.04 stem and a 0.11 yd spout head), the cue that tells
  café syrups from a potion or liquor shelf; the heads fan outward from the middle of the row, 50-77 degrees off
  the front (the left four to the left, the right three to the right, so no two heads point at each other), so
  every head shows its L profile from the front and from either three-quarter view (a head turned toward the
  camera reads as a plain post); the bottles are about 1.1-1.2x real height
  (0.28-0.37 yd of glass, 0.38-0.47 with the pump) rather than 1.5x, so both tiers and the plate fit the 0.9 yd
  height;
- each bottle is an opaque body full of syrup under a clear glass neck (section 5.2.5: contents opaque), so the
  bottles sort with the depth buffer from every side; the syrup is painted as if lit from behind (bright in the
  middle, deep at the edges) with glass streaks, so it still reads as glass from 15 yd; the bean and sugar jars
  are built the same way (opaque contents, a glass shoulder);
- the honey bottle is a hexagonal (honeycomb) prism; the label is painted on the bottle (a band all round, the
  glyph on the front) instead of a separate band mesh, which keeps the eight bottles inside the budget;
- the cream canister's band is royal blue with a white rosette (a white band would vanish on the white body);
- the back is royal-blue enamel framed in walnut, not plain walnut, so the dark chocolate and caramel bottles
  read against it; the upper tier is set back (0.28 deep) so it never hides the pump heads;
- added on the upper tier: the saucer stack (the "spare jars" are the bean and sugar jars), two flared tiers of
  0.033 yd, so its outline steps like stacked saucers rather than a bowl.
"""

import math

from .. import build as B
from .. import emblem as E
from .. import font as F
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "SyrupRackSW"
DISPLAY = 19310

ENAMEL = T.hexc("2E4E8C")
WIDTH, DEPTH, HEIGHT = 1.4, 0.4, 0.9
SIDE_T = 0.07
INNER = WIDTH / 2 - SIDE_T          # the uprights' inner faces at y = +-0.63
PLINTH_H = 0.06
SHELF_Z0, SHELF_Z1 = 0.55, 0.595    # the upper tier board
SHELF_FRONT = 0.115
BACK_X0, BACK_X1 = -0.196, -0.165   # the enamel back panel (its rear 4 mm inside the uprights' rear faces)
PLINTH_X = 0.194                    # the plinth's front, 6 mm inside the uprights' front faces (no z-fight)
UPRIGHT_TOP = 0.77
BOTTLE_X = 0.03
RAIL_X, RAIL_Z, RAIL_R = 0.166, PLINTH_H + 0.04, 0.018    # low enough to clear every label glyph
PLATE_W, PLATE_Z0, PLATE_Z1 = 0.56, 0.752, 0.882
TIER_X = -0.01                      # the upper tier's items stand on this line
WOBBLE = 0.005                      # section 5.4: light wobble on Stormwind wood

# The syrup bottles (shelf order and colours from emblem.SYRUPS): profile (r, z) from the foot up to the open
# neck under the pump collar (the last segment is the clear glass neck, the rest the syrup-filled body), the
# painted label band (z0, z1) on the widest straight part, clear of the gallery rail, and the side count (the
# honey bottle is a hexagonal honeycomb prism).
BOTTLES = {
    "honey": ([(0.072, 0.0), (0.072, 0.18), (0.055, 0.222), (0.028, 0.25), (0.026, 0.285)], (0.055, 0.16), 6),
    "vanilla": ([(0.055, 0.0), (0.055, 0.215), (0.046, 0.255), (0.023, 0.282), (0.022, 0.37)], (0.065, 0.17), 8),
    "caramel": ([(0.062, 0.0), (0.062, 0.235), (0.054, 0.257), (0.025, 0.271), (0.024, 0.345)], (0.07, 0.175), 8),
    "cinnamon": ([(0.07, 0.0), (0.057, 0.225), (0.032, 0.27), (0.023, 0.284), (0.022, 0.335)], (0.05, 0.155), 8),
    "chocolate": ([(0.07, 0.0), (0.07, 0.19), (0.059, 0.23), (0.033, 0.252), (0.031, 0.3)], (0.055, 0.16), 8),
    "berry": ([(0.046, 0.0), (0.068, 0.022), (0.072, 0.055), (0.072, 0.165), (0.05, 0.215), (0.023, 0.25),
               (0.022, 0.325)], (0.06, 0.16), 8),
    "mint": ([(0.064, 0.0), (0.064, 0.155), (0.052, 0.195), (0.06, 0.228), (0.026, 0.272), (0.023, 0.34)],
             (0.045, 0.145), 8),
}
CAN_BODY = [(0.061, 0.0), (0.061, 0.24), (0.054, 0.262), (0.037, 0.273)]
CAN_BAND = (0.065, 0.17)
# pump heads (degrees about the stem, from +X; shelf order honey to mint), fanned outward from the middle of the
# row and a little uneven, hand-set: honey turns less, so its spout clears the upright
PUMP_YAW = (-52.0, -74.0, -68.0, -76.0, 72.0, 77.0, 68.0)
# syrup run down a bottle's shoulder (bottle key: angle from +X round the bottle, z of its bead above the foot,
# just over the label band), clear of the glass streaks (GLINTS), so a run never merges into one
DRIPS = {"honey": (0.35, 0.165), "caramel": (-0.05, 0.18), "chocolate": (0.3, 0.165)}
# the upper tier (all 1.2x the real size): jar profile (the last segment is the glass shoulder under the lid),
# the saucer stack (two flared tiers of STACK_STEP), the cups and their saucers
JAR = [(0.067, 0.0), (0.072, 0.01), (0.072, 0.08), (0.06, 0.11)]
STACK_R, STACK_STEP = 0.092, 0.033
CUP_R, CUP_H, SAUCER_R, SAUCER_H = 0.068, 0.096, 0.095, 0.014

# the uprights' side silhouette (x, z), scrolled back toward the top
UPRIGHT = [(-0.2, 0.0), (0.2, 0.0), (0.2, 0.075), (0.178, 0.12), (0.17, 0.44), (0.155, 0.51), (0.128, 0.55),
           (0.125, 0.61), (0.09, 0.68), (0.02, 0.735), (-0.1, UPRIGHT_TOP), (-0.2, UPRIGHT_TOP)]
# the back panel's crest (y, z), right half from the upright inward; a flat tablet carries the plate
CREST = [(INNER + 0.005, 0.755), (0.5, 0.762), (0.42, 0.775), (0.37, 0.8), (0.35, 0.845), (0.333, 0.885),
         (0.305, HEIGHT)]
FINIAL_X = -0.15
# vertical glass highlights round a bottle or jar: (azimuth from +X, half width), radians; the broad one faces
# the key light (front, -Y); the middle of the front stays clear for the syrup's colour
GLINTS = ((-0.5, 0.17), (1.05, 0.12))


# ----------------------------------------------------------------------------------------------- paints

def _lip(ctx, seed, c, front, z_top, depth=0.032):
    """A brass trim lip on a board's bullnosed front edge (the top `depth` of its front)."""
    x, _y, z = ctx.pos
    if x > front - 0.03 and z > z_top - depth:
        return T.g_brass(ctx, seed + 3, {"streak": False, "patina": 0.08})
    return c


def p_plinth(ctx, seed, p):
    return _lip(ctx, seed, T.g_wood(ctx, seed, {"kind": "walnut"}), PLINTH_X, PLINTH_H)


def p_shelf(ctx, seed, p):
    c = T.g_wood(ctx, seed, {"kind": "walnut"})
    return _lip(ctx, seed, c, SHELF_FRONT, SHELF_Z1, 0.03)


def p_upright(ctx, seed, p):
    """Walnut, the grain upright; each end face carries a broad recessed panel (a field that darkens over 4 cm,
    no thin bevel lines, which would be finer than a texel) round the lion medallion."""
    c = T.g_wood(ctx, seed, {"kind": "walnut", "along": "t"})
    if not ctx.chart.endswith(("_front", "_back")):
        return c
    x, _y, z = ctx.pos
    e = min(x + 0.165, 0.14 - x, z - 0.1, 0.47 - z)
    if e > 0.0:
        c = T.scale(c, 1.0 - 0.24 * T.smoothstep(0.0, 0.04, e))
    return c


def p_back(ctx, seed, p):
    """The back panel: walnut framing two royal-blue enamel fields (one per tier), darker toward their edges, so
    the bottles and cups stand out against blue; the crest is plain walnut under the plate."""
    c = T.g_wood(ctx, seed, {"kind": "walnut"})
    if ctx.chart != "back_front":
        return c
    _x, y, z = ctx.pos
    for z0, z1 in ((PLINTH_H + 0.01, SHELF_Z0 - 0.005), (SHELF_Z1 + 0.005, 0.74)):
        e = min(INNER - 0.035 - abs(y), z - z0, z1 - z)
        if e >= 0.0:
            ev = T.g_enamel(ctx, seed + 5, {"color": ENAMEL, "chips": 0, "gloss": 0.25})
            return T.mix(ev, T.scale(ENAMEL, 0.55), T.smoothstep(0.03, 0.0, e) * 0.5)
    return c


def p_brass(ctx, seed, p):
    return T.g_brass(ctx, seed, p)


def p_gold(ctx, seed, p):
    return T.g_gold(ctx, seed, p)


def p_plate(ctx, seed, p):
    return T.g_brass(ctx, seed, {"streak": False, "patina": 0.05, "freq": 6.0})


def p_pump_head(ctx, seed, p):
    """Brass pump heads, darker under the arm and on the spout's tip."""
    c = T.g_brass(ctx, seed, {"streak": False, "patina": 0.06})
    if ctx.n[2] < -0.5:
        c = T.scale(c, 0.55)
    return c


def azimuth(ctx, seam=math.pi):
    """The texel's angle round a lathe's axis, from +X (radians). A split_lathe front chart runs from -Y round
    the front to +Y, its back chart from +Y round the back; a whole lathe's chart starts at its seam."""
    if ctx.chart.endswith("_front"):
        return (ctx.u - 0.5) * math.pi
    if ctx.chart.endswith("_back"):
        return (ctx.u + 0.5) * math.pi
    return seam + ctx.u * 2 * math.pi


def glint(ctx, c, a, seam=math.pi, glints=GLINTS, strength=0.75):
    """Vertical highlight streaks (glints, as GLINTS) on a round glass chart, as tex.g_glass: (colour, alpha);
    strength: how far the middle of a streak goes toward white."""
    az = azimuth(ctx, seam)
    for centre, wdt in glints:
        d = abs((az - centre + math.pi) % (2 * math.pi) - math.pi)
        if d < wdt:
            k = T.smoothstep(wdt, 0.0, d)
            c = T.mix(c, (1.0, 1.0, 1.0), k * strength)
            a = max(a, 0.72 + 0.18 * k)
    return c, a


def _drip(ctx, color, centre, drip):
    """The colour of a run of syrup at this texel, or None: from the neck down over the shoulder to a fat bead
    just above the label (drip (angle from +X round the bottle, z of the bead); centre the bottle's axis). It is
    painted as a raised run on the glass, lighter and glossier than the syrup inside: a rich core and a broad
    pale gloss over its half toward the key light (3 texels and more), so it reads as wet syrup, not a crack."""
    x, y, z = ctx.pos
    phi = math.atan2(y - centre[1], x - centre[0])
    off = (phi - drip[0]) * math.hypot(x - centre[0], y - centre[1])
    w = 0.015 + 0.002 * math.sin(z * 90.0)        # half width: a 0.03 yd run, wavering
    by = z - drip[1]
    bead = math.hypot(off, by * 0.8)
    if (abs(off) < w and by > 0.0) or bead < 0.02:
        core = T.scale(T.saturate(color, 1.3), 0.85)
        gloss = T.mix(T.saturate(color, 1.2), (1.0, 0.97, 0.86), 0.75)
        lit = -off / w if by > 0.0 else -(off + by * 0.5) / 0.02     # 1 on the edge toward -Y (the light)
        return T.mix(core, gloss, T.smoothstep(-0.3, 0.5, lit))
    return None


def syrup_paint(color, top_z, centre, drip=None):
    """A bottle body full of syrup (opaque). The syrup is painted as if lit from behind: bright and warm in the
    middle of the bottle as seen from the front, deep and saturated toward its edges, darker toward the foot;
    glass streak highlights over it and the thick glass foot. drip: a run of syrup over the shoulder (_drip)."""
    lit = T.mix(T.saturate(color, 1.2), (1.0, 0.98, 0.9), 0.2)
    deep = T.scale(T.saturate(color, 1.3), 0.6)

    def p(ctx, seed, _p):
        if drip:
            d = _drip(ctx, color, centre, drip)
            if d is not None:
                return d
        side = abs(ctx.n[1])
        c = T.mix(lit, color, T.smoothstep(0.1, 0.55, side))
        c = T.mix(c, deep, T.smoothstep(0.55, 0.97, side) * 0.85)
        c = T.mix(c, T.scale(c, 0.8), T.smoothstep(0.05, 0.2, top_z - ctx.pos[2]) * 0.4)
        c, _a = glint(ctx, c, 1.0)
        if ctx.v > 0.96:
            c = T.mix(c, T.hexc("6E8A86"), 0.5)
        return c
    return p


def neck_paint(bottles):
    """The bottles' clear glass necks (one single-shell glass part): pale glass at alpha 0.3 with streak
    highlights and a darker rim at each end, and the start of the syrup runs. bottles: [(y, colour, drip)]."""
    def p(ctx, seed, _p):
        by, color, drip = min(bottles, key=lambda b: abs(b[0] - ctx.pos[1]))
        if drip:
            d = _drip(ctx, color, (BOTTLE_X, by), drip)
            if d is not None:
                return (d[0], d[1], d[2], 1.0)
        c, a = glint(ctx, T.hexc("E6F4F0"), 0.3, -math.pi / 2)
        if min(ctx.v, 1.0 - ctx.v) < 0.15:
            c = T.mix(c, T.hexc("6E8A86"), 0.5)
            a = max(a, 0.6)
        return (c[0], c[1], c[2], a)
    return p


def p_can(ctx, seed, p):
    return T.g_enamel(ctx, seed, {"color": T.hexc("F2EEE4"), "chips": 0, "gloss": 0.5})


def p_silver(ctx, seed, p):
    return T.g_silver(ctx, seed, p)


def _sugar(ctx, seed):
    """Sugar cubes in a jar: staggered white cubes (0.045 yd, 3 texels and more), each lit on its upper face,
    with blue-grey gaps."""
    cell = 0.045
    row = math.floor(ctx.t / cell)
    off = ((row * 0.618 + seed * 0.137) % 1.0) * cell     # each row staggered
    fx = ((ctx.s + off) / cell) % 1.0
    fy = (ctx.t / cell) % 1.0
    e = min(fx, 1.0 - fx, fy, 1.0 - fy)
    c = T.mix(T.hexc("B8BCD0"), T.hexc("FBF8F0"), T.smoothstep(0.04, 0.16, e))
    if fy < 0.3 and e > 0.06:
        c = T.mix(c, (1.0, 1.0, 1.0), 0.4)
    return c


def jar_paint(kind):
    """A jar's contents, coffee beans or sugar cubes (opaque), with the glass streaks over them."""
    def p(ctx, seed, _p):
        c = T.g_beans(ctx, seed, {"size": 0.034}) if kind == "beans" else _sugar(ctx, seed)
        c, _a = glint(ctx, c, 1.0)
        return c
    return p


def p_jar_glass(ctx, seed, p):
    return T.g_bottle_glass(ctx, seed, {"tint": T.hexc("E6F4F0"), "alpha": 0.3})


def cup_paint(base_z, centres):
    """White porcelain cups with a bold royal-blue band (0.03 yd) on the upper outer wall (by height and
    facing, so the inside stays white), on saucers with a royal-blue rim."""
    def p(ctx, seed, _p):
        c = T.g_ceramic(ctx, seed, {})
        x, y, z = ctx.pos
        cx, cy = min(centres, key=lambda q: (x - q[0]) ** 2 + (y - q[1]) ** 2)
        rx, ry = x - cx, y - cy
        rr = math.hypot(rx, ry) or 1.0
        lz = z - base_z
        if lz < 0.001 and rr > SAUCER_R - 0.017:
            return T.mix(ENAMEL, T.scale(ENAMEL, 1.3), T.clamp01(ctx.n[2]))     # the saucer's blue rim
        if rr < CUP_R + 0.004 and (ctx.n[0] * rx + ctx.n[1] * ry) / rr > 0.2 and 0.048 <= lz <= 0.078:
            c = T.mix(ENAMEL, T.scale(ENAMEL, 1.3), T.clamp01(ctx.n[0] * 0.5 + 0.5))
        return c
    return p


def p_porcelain(ctx, seed, p):
    return T.g_ceramic(ctx, seed, {})


def stack_paint(base_z, x0, y0):
    """A stack of saucers in two flared tiers: white porcelain, each tier shaded from a cool shadow under its
    flare to a lit rim (a ramp over the whole 0.033 yd tier, no thin lines), and the ring of each tier seen from
    above in royal blue (0.022 yd and more), so the stack reads as saucers, not a bowl."""
    def p(ctx, seed, _p):
        c = T.g_ceramic(ctx, seed, {})
        x, y, z = ctx.pos
        if ctx.n[2] > 0.7:
            if math.hypot(x - x0, y - y0) > STACK_R - 0.024:
                c = T.mix(ENAMEL, T.scale(ENAMEL, 1.35), T.clamp01(ctx.n[0] * 0.5 + 0.5))
            return c
        k = ((z - base_z) % STACK_STEP) / STACK_STEP
        return T.mix(T.mix(c, T.hexc("9AA6C4"), 0.45), c, T.smoothstep(0.0, 0.7, k))
    return p


# ---------------------------------------------------------------------------------------------- decals

def arc_table(prof):
    """(total length, arc(z)) of a lathe profile as geom.lathe measures it, so a decal can find a height on the
    side chart (t = total - arc, from the top)."""
    pts = []
    for r, z in prof:
        if not pts or math.hypot(r - pts[-1][0], z - pts[-1][1]) > 1e-9:
            pts.append((r, z))
    arc = [0.0]
    for k in range(1, len(pts)):
        arc.append(arc[-1] + math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]))

    def at(z):
        for k in range(len(pts) - 1):
            (_r0, z0), (_r1, z1) = pts[k], pts[k + 1]
            if z1 > z0 and z0 <= z <= z1:
                return arc[k] + (z - z0) / (z1 - z0) * (arc[k + 1] - arc[k])
        return arc[-1]
    return arc[-1], at


def label_decal(prof, band, color, glyph, color2=None, with_glyph=True):
    """A syrup label painted on one half of a bottle body (a split_lathe chart): the colour band across the
    chart between band (z0, z1) and, on the front chart, the flavour glyph (paint2d.label) in its middle (the
    model's front, +X). The band sits on the widest part, where the chart's s density equals its t density, so
    the glyph keeps its aspect."""
    total, at = arc_table(prof)
    v0 = (total - at(band[1])) / total
    v1 = (total - at(band[0])) / total

    def f(w, h):
        img = T.Img(w, h, (0, 0, 0, 0))
        y0 = int(round(v0 * h))
        bh = max(1, int(round(v1 * h)) - y0)
        p = {"color": color, "glyph": glyph, "glyph_scale": 0.84}
        if color2 is not None:
            p["color2"] = color2
        P2.composite(img, P2.label(w, bh, dict(p, glyph=None)), 0, y0)
        if with_glyph:
            gw = min(w, bh)
            P2.composite(img, P2.label(gw, bh, p), (w - gw) // 2, y0)
        return img
    return f


def d_plate(w, h):
    """The crest plate: a dark inset frame round a royal-blue enamel field with "SYRUPS" in condensed two-tone
    cream capitals, and a gold lion head in relief on the blue at each end (half the plate's height, so the
    word gets the width: cap 0.066 yd on the full-size atlas)."""
    img = T.Img(w, h, (0, 0, 0, 0))
    bw = max(1, int(min(w, h) * 0.06))
    for y in range(h):
        for x in range(w):
            e = min(x, y, w - 1 - x, h - 1 - y)
            if bw <= e < 2 * bw:
                img.set(x, y, T.hexc("4A2E0C"), 0.9)
            elif e < bw:
                img.set(x, y, T.hexc("F6DA88"), 0.35)
            else:
                k = 0.9 + 0.22 * (1.0 - (y - 2 * bw) / float(max(1, h - 4 * bw)))
                img.set(x, y, T.scale(ENAMEL, k), 1.0)
    ls = int(h * 0.5)
    lx, ly = 2 * bw + max(1, bw), (h - ls) // 2
    fx0, fx1 = lx + ls + bw, w - lx - ls - bw     # the word's box between the lions (no pin lines: one texel)
    try:
        cap = F.fit_cap("SYRUPS", fx1 - fx0 - 2 * bw, h - 4 * bw, min_cap=4.0, squeeze=0.85)
        m = F.vector_mask("SYRUPS", cap, squeeze=0.85)
        F.two_tone(img, m, T.hexc("FBEAB0"), T.hexc("120C04"), fx0 + (fx1 - fx0 - m.w) // 2, (h - m.h) // 2, 1,
                   (1, 1), T.hexc("0A0804"))
    except ValueError:
        if min(w, h) >= 64:
            raise           # at full size a text that does not fit is an error (section 5.5.1)
    if ls > 6:
        rel = E.render_relief("lion_head", ls, ls, P2.GOLD_RELIEF)
        P2.composite(img, rel, lx, ly)
        P2.composite(img, rel, w - lx - ls, ly)
    return img


def side_lion(center_u, center_v, size_k):
    """A gold lion head on a royal-blue enamel roundel ringed in gold, on an upright's end face (the extrude cap
    chart), centred at (u, v): gold on blue reads against the walnut, where gold alone went dim."""
    def f(w, h):
        img = T.Img(w, h, (0, 0, 0, 0))
        s = int(min(w, h) * size_k)
        if s > 6:
            cx, cy = center_u * w, center_v * h
            P2.ring(img, cx, cy, 0.0, s * 0.62, T.hexc("D8A838"))
            P2.ring(img, cx, cy, 0.0, s * 0.62 - max(1.5, s * 0.09), ENAMEL)
            ls = int(s * 0.88)
            rel = E.render_relief("lion_head", ls, ls, P2.GOLD_RELIEF)
            P2.composite(img, rel, int(cx - ls / 2.0), int(cy - ls / 2.0))
        return img
    return f


# ------------------------------------------------------------------------------------------------ parts

# extrude() builds along +Z from a polygon in its XY plane; this turns it so the polygon lies in the model's XZ
# plane (x stays x, the polygon's y becomes z) and the depth runs along -Y (a proper rotation, so the winding
# holds); the result is then centred on Y.
_XZ = ((1.0, 0.0, 0.0, 0.0), (0.0, 0.0, -1.0, 0.0), (0.0, 1.0, 0.0, 0.0))


def _xz_extrude(poly, width, y=0.0, name="extrude"):
    """A board or panel whose side silhouette is `poly` [(x, z)], `width` yd along Y, centred on y. Charts: the
    belt (around the silhouette, t along Y), `<name>_front` (the -Y end) and `<name>_back` (the +Y end)."""
    m = G.extrude(poly, width, name=name)
    return G.transform(m, G.mat_chain(G.mat_translate(0.0, y + width / 2.0, 0.0), _XZ))


def _strip(profile, charts, y0, y1, weights):
    """The visible skin of a long board: the polyline `profile` [(x, z)] swept along Y from y0 to y1, two
    triangles a segment, outward to the right of the walking direction (a board's back, bottom and ends hidden
    in the uprights are left out). charts[k] names segment k's chart; consecutive segments share it (s along
    Y, t along the profile); weights {chart: texel weight}."""
    m = G.Mesh()
    ids, used = {}, {}
    lens = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(profile, profile[1:])]
    for k, ((xa, za), (xb, zb)) in enumerate(zip(profile, profile[1:])):
        name = charts[k]
        if name not in ids:
            total = sum(L for L, nm in zip(lens, charts) if nm == name)
            ids[name] = m.chart(y1 - y0, total, name)
            m.charts[ids[name]].weight = weights.get(name, 1.0)
            used[name] = 0.0
        ch = ids[name]
        t0 = used[name]
        t1 = t0 + lens[k]
        used[name] = t1
        n = G.norm((zb - za, 0.0, -(xb - xa)))
        a0 = m.vert((xa, y0, za), n, ch, 0.0, t0)
        a1 = m.vert((xa, y1, za), n, ch, y1 - y0, t0)
        b0 = m.vert((xb, y0, zb), n, ch, 0.0, t1)
        b1 = m.vert((xb, y1, zb), n, ch, y1 - y0, t1)
        if G.dot(G.cross(G.sub(m.p[b0], m.p[a0]), G.sub(m.p[b1], m.p[a0])), n) > 0:
            m.tri(a0, b0, b1)
            m.tri(a0, b1, a1)
        else:
            m.tri(a0, b1, b0)
            m.tri(a0, a1, b1)
    return G.recompute_normals(m, 50.0)


def hand_made(mesh, amp, seed):
    """A light wobble (section 5.4), then every vertex clamped back inside the mesh's own box and the foot set
    back on its base (no vertex but the foot's lies within amp of it), so the piece keeps its catalogue size,
    stands flat and does not poke through its neighbours."""
    (x0, y0, z0), (x1, y1, z1) = mesh.bounds()
    m = G.wobble(mesh, amp, seed)
    m.p = [(min(max(x, x0), x1), min(max(y, y0), y1), z0 if z < z0 + amp + 1e-6 else min(z, z1)) for x, y, z in m.p]
    return G.recompute_normals(m, 40.0)


def split_lathe(prof, sides, front_w, back_w, name="lathe", crisp=False):
    """geom.lathe in two charts, so the half nobody sees takes few texels: `<name>_front` runs from -Y round the
    front (+X, u 0.5) to +Y, `<name>_back` from +Y round the back to -Y; weights front_w and back_w. The same
    triangles as the lathe (its seam at -Y; the vertices on the two seams are doubled). sides must be even;
    crisp: flat facets (the honey hexagon, whose flat face then looks to the front)."""
    m = G.lathe(prof, sides, seam=-math.pi / 2, name=name)
    if crisp:
        m = G.recompute_normals(m, 40.0)
    full = m.charts[0]
    half = full.w / 2.0
    out = G.Mesh()
    ids = (out.chart(half, full.h, name + "_front"), out.chart(half, full.h, name + "_back"))
    out.charts[ids[0]].weight = front_w
    out.charts[ids[1]].weight = back_w
    remap = {}
    for tri in m.t:
        k = 1 if min(m.st[v][0] for v in tri) > half - 1e-9 else 0
        new = []
        for v in tri:
            if (v, k) not in remap:
                s, t = m.st[v]
                remap[(v, k)] = out.vert(m.p[v], m.n[v], ids[k], s - half * k, t)
            new.append(remap[(v, k)])
        out.tri(*new)
    return out


# a pump head's side view (x forward from the stem, z up from the arm's underside): a 0.036 arm with a spout
# turned down 0.04 at its front end
PUMP_HEAD = [(-0.022, 0.0), (0.058, 0.0), (0.058, -0.04), (0.088, -0.04), (0.088, 0.036), (-0.022, 0.036)]


def pump(x, y, neck_r, zt, yaw_deg):
    """A syrup pump on a neck top at zt: a capped collar, a 0.04 stem and an L head (0.04 wide) pointing yaw_deg
    off +X; its top is 0.096 above the neck."""
    collar = G.lathe([(neck_r + 0.012, zt - 0.024), (neck_r + 0.012, zt + 0.012), (0.0, zt + 0.018)], 6,
                     name="collar")
    stem = G.cylinder(0.02, 0.052, 5, False, z0=zt + 0.012)
    head = _xz_extrude(PUMP_HEAD, 0.04, 0.0, "head")
    head = G.transform(head, G.mat_chain(G.mat_rot_z(math.radians(yaw_deg)), G.mat_translate(0.0, 0.0, zt + 0.06)))
    return (G.translate(G.merge([collar, stem]), x, y, 0.0), G.translate(head, x, y, 0.0))


def centres(widths, lo, hi):
    """Centres for items of the given widths spread from lo to hi with equal gaps (ends included)."""
    gap = (hi - lo - sum(widths)) / (len(widths) + 1)
    out = []
    y = lo + gap
    for wd in widths:
        out.append(y + wd / 2.0)
        y += wd + gap
    return out


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (WIDTH, DEPTH, HEIGHT)
    d.budget = 1600
    d.collision_max = 48
    d.atlas = {"atlas": 256}
    d.kind = "rack"
    d.max_height = 0.95
    d.sloped_top = True
    add = d.add

    # the carcass: scrolled side uprights, a bullnosed plinth and upper tier with brass lips, the enamel back
    yc = WIDTH / 2 - SIDE_T / 2
    uprights = G.merge([_xz_extrude(UPRIGHT, SIDE_T, -yc, "upright"), _xz_extrude(UPRIGHT, SIDE_T, yc, "upright")])
    uprights = hand_made(uprights, WOBBLE, 12)
    uprights.t = [t for t in uprights.t if max(uprights.p[v][2] for v in t) > 1e-6]     # the feet on the bar
    # charts: [belt, -Y end, +Y end] per upright (charts 1 and 5 are the outer faces, which carry the lion
    # roundels and face a three-quarter camera; 2 and 4 the plain inner faces)
    for k, ch in enumerate(uprights.charts):
        ch.weight = (0.45, 1.1, 0.45, 0.45, 0.45, 1.1)[k]
    lion_u = (-0.015 + 0.2) / 0.4
    lion_v = (UPRIGHT_TOP - 0.285) / UPRIGHT_TOP
    add(B.Part("uprights", uprights, paint=p_upright, seed=11,
               decals={1: side_lion(lion_u, lion_v, 0.55), 5: side_lion(1.0 - lion_u, lion_v, 0.55)}))
    span = INNER + 0.01
    plinth = _strip([(PLINTH_X, 0.0), (PLINTH_X, 0.038), (PLINTH_X - 0.008, 0.054), (PLINTH_X - 0.022, PLINTH_H),
                     (BACK_X1 - 0.005, PLINTH_H)],
                    ["plinth_front", "plinth_front", "plinth_front", "plinth_top"], -span, span,
                    {"plinth_front": 0.9, "plinth_top": 0.5})
    add(B.Part("plinth", plinth, paint=p_plinth, seed=13))
    shelf = _strip([(BACK_X1 - 0.005, SHELF_Z0), (SHELF_FRONT - 0.012, SHELF_Z0), (SHELF_FRONT, SHELF_Z0 + 0.012),
                    (SHELF_FRONT, SHELF_Z1 - 0.014), (SHELF_FRONT - 0.01, SHELF_Z1), (BACK_X1 - 0.005, SHELF_Z1)],
                   ["shelf_under", "shelf_edge", "shelf_edge", "shelf_edge", "shelf_top"], -span, span,
                   {"shelf_under": 0.15, "shelf_edge": 1.0, "shelf_top": 0.55})
    shelf = hand_made(shelf, WOBBLE, 16)
    add(B.Part("shelf", shelf, paint=p_shelf, seed=15))
    poly = [(-INNER - 0.005, PLINTH_H - 0.005), (INNER + 0.005, PLINTH_H - 0.005)] + CREST
    poly += [(-y, z) for y, z in CREST[::-1]]
    back = G.extrude(poly, BACK_X1 - BACK_X0, name="back")
    back = G.transform(back, G.mat_chain(G.mat_translate(BACK_X0, 0.0, 0.0), G.MAT_EXTRUDE_FRONT))
    back = hand_made(back, WOBBLE, 18)
    for ch in back.charts:
        ch.weight = {"back_front": 0.6, "back_back": 0.05}.get(ch.name, 0.35)
    add(B.Part("back", back, paint=p_back, seed=17))

    # the crest plate: a rounded brass tablet in front of the crest
    pw2, ph2, cr = PLATE_W / 2, (PLATE_Z1 - PLATE_Z0) / 2, 0.02
    plate_poly = [(pw2, -ph2 + cr), (pw2, ph2 - cr), (pw2 - cr, ph2), (-pw2 + cr, ph2), (-pw2, ph2 - cr),
                  (-pw2, -ph2 + cr), (-pw2 + cr, -ph2), (pw2 - cr, -ph2)]
    plate = G.extrude(plate_poly, 0.022, 0.007, back=False, name="plate")
    plate = G.transform(plate, G.mat_chain(G.mat_translate(BACK_X1 - 0.004, 0.0, (PLATE_Z0 + PLATE_Z1) / 2),
                                           G.MAT_EXTRUDE_FRONT))
    for ch in plate.charts:
        ch.weight = 3.0 if ch.name == "plate_front" else 0.5
    add(B.Part("plate", plate, paint=p_plate, seed=19, decals={"plate_front": d_plate}))

    # gold ball finials on the uprights, a brass gallery rail across the lower tier
    ball = [(0.024, UPRIGHT_TOP - 0.006), (0.036, UPRIGHT_TOP + 0.03), (0.027, UPRIGHT_TOP + 0.064),
            (0.0, UPRIGHT_TOP + 0.08)]
    finials = [G.translate(G.lathe(ball, 6), FINIAL_X, s * yc, 0.0) for s in (1, -1)]
    add(B.Part("finials", G.merge(finials), paint=p_gold, seed=21, weight=0.6))
    rail = G.sweep([(RAIL_X, -INNER - 0.004, RAIL_Z), (RAIL_X, INNER + 0.004, RAIL_Z)], RAIL_R, 6)
    add(B.Part("rail", rail, paint=p_brass, seed=23, weight=0.5))

    # the syrups: seven bottles with pumps and the whipped-cream canister, in shelf order. A bottle is an opaque
    # body full of syrup (its unseen back half on a small chart) under a clear neck; the necks are one glass part
    keys = [row[0] for row in E.SYRUPS]
    widths = [2 * max(r for r, _z in (BOTTLES[k][0] if k in BOTTLES else CAN_BODY)) for k in keys]
    ys = centres(widths, -INNER, INNER)
    stems, heads, necks, neck_info = [], [], [], []
    can_y = ys[-1]
    for k, ((key, hexcol, glyph, col2), y) in enumerate(zip(E.SYRUPS, ys)):
        if key not in BOTTLES:
            can_y = y
            continue
        color = T.hexc(hexcol)
        prof, band, sides = BOTTLES[key]
        body_prof = prof[:-1]
        body = G.translate(split_lathe(body_prof, sides, 2.0, 0.4, "body", sides == 6), BOTTLE_X, y, PLINTH_H)
        neck = G.lathe(prof[-2:], sides, seam=-math.pi / 2, name="neck")
        necks.append(G.translate(neck, BOTTLE_X, y, PLINTH_H))
        drip = DRIPS.get(key)
        if drip:
            drip = (drip[0], PLINTH_H + drip[1])
        neck_info.append((y, color, drip))
        c2 = T.hexc(col2) if col2 else None
        add(B.Part("bottle_" + key, body, paint=syrup_paint(color, PLINTH_H + body_prof[-1][1], (BOTTLE_X, y), drip),
                   seed=31 + k, ao_floor=0.85,
                   decals={0: label_decal(body_prof, band, color, glyph, c2),
                           1: label_decal(body_prof, band, color, glyph, c2, False)}))
        s, h = pump(BOTTLE_X, y, prof[-1][0], PLINTH_H + prof[-1][1], PUMP_YAW[k % len(PUMP_YAW)])
        stems.append(s)
        heads.append(h)
    add(B.Part("bottle_necks", G.merge(necks), "glass1", paint=neck_paint(neck_info), seed=39, weight=1.0))
    add(B.Part("pump_stems", G.merge(stems), paint=p_brass, seed=41, weight=0.6))
    add(B.Part("pump_heads", G.merge(heads), paint=p_pump_head, seed=43, weight=0.9))

    # the whipped-cream canister: white enamel, a silver head and a nozzle tilted toward the barista
    can = G.translate(split_lathe(CAN_BODY, 8, 1.8, 0.4, "can"), BOTTLE_X, can_y, PLINTH_H)
    add(B.Part("cream_can", can, paint=p_can, seed=45, ao_floor=0.7,
               decals={0: label_decal(CAN_BODY, CAN_BAND, ENAMEL, "cream"),
                       1: label_decal(CAN_BODY, CAN_BAND, ENAMEL, "cream", None, False)}))
    hz = PLINTH_H + CAN_BODY[-1][1]
    head = G.translate(G.lathe([(0.04, hz - 0.012), (0.042, hz + 0.024), (0.0, hz + 0.036)], 8, name="can_head"),
                       BOTTLE_X, can_y, 0.0)
    nozzle = G.lathe([(0.018, 0.0), (0.022, 0.035), (0.0, 0.09)], 6, name="nozzle")
    nozzle = G.transform(nozzle, G.mat_chain(G.mat_translate(BOTTLE_X + 0.006, can_y, hz + 0.03),
                                             G.mat_rot_y(math.radians(28))))
    add(B.Part("cream_head", G.merge([head, nozzle]), paint=p_silver, seed=47, weight=0.7))

    # the upper tier, spread evenly: a bean jar and a sugar jar with brass lids, a stack of saucers in two flared
    # tiers, two cups on saucers. The jars' contents are opaque bodies with a heaped top; their glass shoulders
    # are one glass part
    tz = SHELF_Z1
    jy0, jy1, stack_y, cy0, cy1 = centres([2 * JAR[1][0]] * 2 + [2 * STACK_R] + [2 * SAUCER_R] * 2,
                                          -INNER + 0.03, INNER - 0.03)
    shoulders, lids = [], []
    for k, (jy, kind) in enumerate(((jy0, "beans"), (jy1, "sugar"))):
        jar = G.translate(G.lathe(JAR[:-1] + [(0.0, JAR[-2][1] + 0.008)], 8, name="jar"), TIER_X, jy, tz)
        add(B.Part("jar_" + kind, jar, paint=jar_paint(kind), seed=51 + k, weight=1.2, ao_floor=0.7))
        shoulders.append(G.translate(G.lathe(JAR[-2:], 8, name="jar_glass"), TIER_X, jy, tz))
        lid = G.lathe([(0.066, 0.104), (0.071, 0.124), (0.031, 0.134), (0.0, 0.15)], 8, name="lid")
        lids.append(G.translate(lid, TIER_X, jy, tz))
    add(B.Part("jar_glass", G.merge(shoulders), "glass1", paint=p_jar_glass, seed=53, weight=0.8))
    add(B.Part("jar_lids", G.merge(lids), paint=p_brass, seed=55, weight=0.6))
    tier = [(STACK_R - 0.01, 0.0), (STACK_R, STACK_STEP), (0.0, STACK_STEP)]
    stack = G.merge([G.translate(G.lathe(tier, 8, name="stack"), TIER_X, stack_y, tz + k * STACK_STEP)
                     for k in range(2)])
    add(B.Part("saucer_stack", stack, paint=stack_paint(tz, TIER_X, stack_y), seed=56, weight=1.2, ao_floor=0.7))
    cup_xy = [(TIER_X + 0.01, cy0), (TIER_X - 0.005, cy1)]
    cprof = [(0.042, 0.0), (CUP_R, CUP_H), (CUP_R - 0.009, CUP_H - 0.004), (0.0, 0.036)]
    cups = [G.translate(G.lathe(cprof, 8, name="cup"), x, y, tz + SAUCER_H) for x, y in cup_xy]
    saucers = [G.translate(G.lathe([(SAUCER_R - 0.006, 0.0), (SAUCER_R, SAUCER_H), (0.0, SAUCER_H - 0.002)], 8,
                                   name="saucer"), x, y, tz) for x, y in cup_xy]
    add(B.Part("cups", G.merge(cups + saucers), paint=cup_paint(tz + SAUCER_H, cup_xy), seed=57, weight=1.2,
               ao_floor=0.7))
    handles = []
    for x, y in cup_xy:
        z0 = tz + SAUCER_H
        path = [(x, y + CUP_R - 0.012, z0 + 0.079), (x, y + CUP_R + 0.029, z0 + 0.074),
                (x, y + CUP_R + 0.036, z0 + 0.041), (x, y + CUP_R - 0.017, z0 + 0.026)]
        handles.append(G.sweep(path, 0.014, 4))
    add(B.Part("cup_handles", G.merge(handles), paint=p_porcelain, seed=59, weight=0.5, ao_floor=0.7))

    # collision: walls to 0.62, a gable roof to 0.9 (roof n.z 0.58 < 0.6428: too steep to stand on)
    d.collision = G.hull_gable(WIDTH, DEPTH, 0.62, HEIGHT)
    d.particles = []
    return d
