"""19300 EspressoSW, the Royal Brass Engine (Stormwind hero machine), CAFE.SPEC.md section 5.8.1. M1 draft.

Polished brass and copper, royal-blue enamel, a lion crest. Chunky Warcraft proportions: a walnut plinth, a
tapered enamel body framed in riveted brass with four turned corner posts and a three-sided cup rail, a tall
domed brass boiler with three copper hoops (a bold base band, a thin strap, a shoulder band) crowned by a gold
lion finial (a lobed 3D mane with ears, a painted face), two copper group heads with walnut-handled
portafilters, a pressure gauge on the boiler front, the heraldic maker's plate (a "ROYAL BRASS" chief over the
lion), a chrome steam wand (left, +Y) and hot-water tap (right, -Y), a bronze drip tray with a bold grille and
two porcelain cups on the warmer. 1.3 (Y) x 0.7 (X; 0.9 with the handles) x 0.9 yd, front (+X) toward the
barista.

Deviations from the section 5.8.1 numbers, forced by the section 5.8 size (H 0.9 +- 2 cm, which the design
numbers overshoot by 0.08 before the finial) and the readability rule (>= 0.06 yd):
- plinth 0.11 and body 0.28 tall (not 0.12 and 0.4), so the boiler can be a 0.17 cylinder under a 0.165 dome
  (0.69 of its radius, not a full hemisphere) and the lion finial still ends at 0.91;
- the finial is a little under the design size so it fits that height: head r 0.058, a seven-lobed mane torus
  (major r 0.056, minor 0.026, the lobes reaching 0.092) with a lobed back cap, ears r 0.024 above the mane;
- the hoops differ in width (0.044, 0.024 and 0.036 tall); the gauge (r 0.082) sits on a stem on the boiler front
  over the thin middle strap, which frees the body front for the heraldic plate (0.30 x 0.24);
- the group heads stand at Y +-0.30 (not +-0.22) so the portafilters clear the plate in the 3/4 views;
- the drip tray is 0.05 tall (not 0.04) so its dark front band reads at eye height;
- the cup rail runs on three sides, so the front stays clear.
"""

import math

from .. import build as B
from .. import emblem as E
from .. import font as F
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "EspressoSW"
DISPLAY = 19300

ENAMEL = T.hexc("2E4E8C")

FEET_H = 0.03
PLINTH_H = 0.11
BODY_Z0, BODY_Z1 = 0.11, 0.39
BODY_X = -0.06            # body centre on X
BODY_D, BODY_W = 0.55, 1.1
TAPER = 0.07
BOILER_R = 0.24
CYL_Z0, CYL_Z1 = 0.405, 0.575
DOME_TOP = 0.74
HEAD_Z = 0.818
# copper hoops: (centre z, half height, depth out of the boiler wall)
HOOPS = ((0.427, 0.022, 0.015), (0.492, 0.012, 0.010), (0.556, 0.018, 0.013))
GH_Y = 0.30               # group heads at Y +-GH_Y
CUP_Y = 0.37
CUP_Z0 = BODY_Z1 + 0.011
TRAY_H = 0.05

MANE = dict(light_c=T.hexc("FFD27A"), base=T.hexc("B8741A"), dark=T.hexc("4A2604"), bounce=T.hexc("A0601A"),
            patina=T.hexc("7A6A2A"))
MANE_C = (BODY_X - 0.012, 0.0, HEAD_Z)       # the mane's centre; its axis is +X
MANE_LOBES = 7
HEAD_R = 0.058
HEAD_C = (BODY_X + 0.014, 0.0, HEAD_Z - 0.004)
SNOUT_R = 0.03
SNOUT_C = (BODY_X + 0.064, 0.0, HEAD_Z - 0.026)
EAR_R, EAR_DEG = 0.09, 40.0                    # ears: distance from the mane centre, angle from vertical


# ----------------------------------------------------------------------------------------------- paints

def p_walnut(ctx, seed, p):
    c = T.g_wood(ctx, seed, {"kind": "walnut"})
    if ctx.chart == "+x" and ctx.t < 0.034:
        # the brass trim strip along the plinth's front edge
        c = T.g_brass(ctx, seed + 3, {"streak": False})
        if ctx.t > 0.027:
            c = T.scale(c, 0.5)
    return c


def frame_rivets(ctx, c, m, step, r, top=None, hi=T.hexc("FFF2B4"), lo=T.hexc("3A2006")):
    """Bold painted rivets centred on a frame band m yd in from every chart edge, evenly spaced (about `step`)
    along each side with one in every corner: a lit core, a dark rim and a soft drop shadow (section 5.5: at
    least 8 texels across at mip 0). top: explicit rivet positions on the top row (s offsets from the chart's
    centre), for a face whose regular spacing would put every rivet behind something."""
    s, t, cw, ch = ctx.s, ctx.t, ctx.cw, ctx.ch
    best = None
    rows = [((cw - 2 * m, s, t, (m, ch - m)), None), ((ch - 2 * m, t, s, (m, cw - m)), None)]
    if top is not None:
        rows[0] = ((cw - 2 * m, s, t, (ch - m,)), None)
        rows.append(((0.0, s, t, (m,)), [cw / 2 + o for o in top]))
    for (span, along, across, fixed), explicit in rows:
        if explicit is None:
            n = max(1, int(round(span / step)))
            st = span / n
            k = min(n, max(0, int(round((along - m) / st))))
            a0 = m + k * st
        else:
            a0 = min(explicit, key=lambda q: abs(q - along))
        for f in fixed:
            d = math.hypot(along - a0, across - f)
            if best is None or d < best[0]:
                # (distance, offset right, offset down) in chart terms
                best = (d, s - (a0 if along is s else f), t - (f if along is s else a0))
    d, dx, dy = best
    if d < r:
        k = T.clamp01(0.55 - dy / r * 0.55 - dx / r * 0.25)
        return T.mix(T.scale(c, 0.78), hi, k * 0.9)
    if d < r * 1.55:
        return T.mix(c, lo, T.smoothstep(r * 1.55, r, d) * 0.75)
    sd = math.hypot(dx - r * 0.35, dy - r * 0.45)
    if sd < r * 1.5:
        return T.mix(c, T.scale(c, 0.55), T.smoothstep(r * 1.5, r, sd) * 0.5)
    return c


def p_body(ctx, seed, p):
    """Enamel panels framed in brass: the frame covers the rounded edges and carries bold rivets, a dark inset
    line runs inside it. The top face is the brass cup-warmer tray."""
    e = min(ctx.s, ctx.cw - ctx.s, ctx.t, ctx.ch - ctx.t)
    if ctx.chart == "+z":
        c = T.g_brass(ctx, seed, {"streak": False, "patina": 0.1})
        if 0.05 < e < 0.062:
            c = T.scale(c, 0.55)
        return c
    frame = 0.042
    if e < frame:
        c = T.g_brass(ctx, seed, {"streak": True, "patina": 0.12})
        # the front's top row sits in the gaps between the plate, the group heads and the posts
        top = (-0.43, -0.18, 0.18, 0.43) if ctx.chart == "+x" else None
        return frame_rivets(ctx, c, frame * 0.5, 0.125, 0.0145, top)
    c = T.g_enamel(ctx, seed + 5, {"color": ENAMEL, "chips": 2, "chip_r": 0.03, "gloss": 0.35})
    if e < frame + 0.01:
        c = T.scale(c, 0.5)
    return c


def p_boiler(ctx, seed, p):
    c = T.g_brass(ctx, seed, {"streak": True, "streak_w": 0.5, "streak_k": 0.75, "patina": 0.04, "freq": 3.0,
                              "hotspot": 0.9})
    z = ctx.pos[2]
    # painted shadows under the hoops (light from above)
    for hz, hh, _d in HOOPS:
        d = (hz - hh) - z
        if 0.0 < d < 0.04:
            c = T.mix(c, T.scale(c, 0.42), (1.0 - d / 0.04) ** 1.4 * 0.8)
    return c


def p_hoop(ctx, seed, p):
    """Copper hoops: a lit upper lip, a dark lower edge; the bold base band carries twelve big bolts."""
    c = T.g_copper(ctx, seed, {"patina": 0.12})
    x, y, z = ctx.pos
    hz, hh, _d = min(HOOPS, key=lambda h: abs(h[0] - z))
    q = (z - hz) / hh
    if q > 0.55:
        c = T.mix(c, T.hexc("FFC08A"), T.smoothstep(0.55, 0.9, q) * 0.45)
    elif q < -0.6:
        c = T.mix(c, T.hexc("3A1406"), T.smoothstep(-0.6, -0.95, q) * 0.55)
    if hz == HOOPS[0][0] and math.hypot(ctx.n[0], ctx.n[1]) > 0.5:
        phi = math.atan2(y, x - BODY_X)
        step = 2 * math.pi / 12
        d_arc = abs(((phi + step / 2) % step) - step / 2) * (BOILER_R + 0.015)
        d = math.hypot(d_arc, z - hz)
        r = 0.0135
        if d < r:
            k = T.clamp01(0.55 + (z - hz) / r * 0.5)
            c = T.mix(T.hexc("6A2A0C"), T.hexc("FFD0A0"), k)
        elif d < r * 1.5:
            c = T.mix(c, T.hexc("2E1004"), T.smoothstep(r * 1.5, r, d) * 0.7)
    return c


def p_lion(ctx, seed, p):
    """The finial's face, painted on the gold: eyes with a glint, heavy brows, a dark nose pad, a mouth line."""
    c = T.g_gold(ctx, seed, {"patina": 0.05})
    x, y, z = ctx.pos
    k = HEAD_R / 0.064
    dh = math.sqrt((x - HEAD_C[0]) ** 2 + (y - HEAD_C[1]) ** 2 + (z - HEAD_C[2]) ** 2)
    ds = math.sqrt((x - SNOUT_C[0]) ** 2 + (y - SNOUT_C[1]) ** 2 + (z - SNOUT_C[2]) ** 2)
    dark = T.hexc("3A1E06")
    if abs(dh - HEAD_R) < 0.004 and x - HEAD_C[0] > 0.025 * k:
        ly, lz = abs(y) / k, (z - HEAD_C[2]) / k
        e = math.hypot((ly - 0.026) / 1.5, lz - 0.012)
        if e < 0.0085:
            c = dark if not (ly < 0.026 and lz > 0.014) else T.hexc("FFF4C0")
        brow = lz - (0.027 - 0.25 * abs(ly - 0.024))
        if 0.008 < ly < 0.046 and abs(brow) < 0.0045:
            c = T.mix(c, dark, 0.85)
        if ly < 0.012 and 0.0 < lz < 0.03:
            c = T.mix(c, T.hexc("FFF0A8"), 0.35)     # lit bridge of the nose
    elif abs(ds - SNOUT_R) < 0.004 and x - SNOUT_C[0] > 0.011:
        lz = z - SNOUT_C[2]
        if lz > 0.007 and abs(y) < 0.016:
            c = T.mix(c, dark, 0.9)                   # nose pad
        elif lz < -0.011 and abs(y) < 0.02:
            c = T.mix(c, dark, 0.7)                   # mouth
    return c


def p_mane(ctx, seed, p):
    """Antique gold, darker and redder than the face: deep valleys between the seven lobes, lit crests, every
    other lobe a shade warmer, so the mane reads as tufts from the front, the side and the back."""
    c = T.metal(ctx, seed, {"patina": 0.08}, MANE["light_c"], MANE["base"], MANE["dark"], MANE["bounce"],
                MANE["patina"], 0.08)
    x, y, z = ctx.pos
    if z > DOME_TOP + 0.03 or x < MANE_C[0] - 0.005:
        qy, qz = y - MANE_C[1], z - MANE_C[2]
        rho = math.hypot(qy, qz)
        if rho > 0.012:
            phi = math.atan2(qz, qy)
            v = math.cos(MANE_LOBES * (phi - math.pi / 2))
            lobe = int(math.floor((phi - math.pi / 2) * MANE_LOBES / (2 * math.pi) + 0.5)) % 2
            if lobe:
                c = T.mix(c, T.hexc("C8601A"), 0.18)
            back = T.clamp01(-ctx.n[0])
            c = T.mix(c, T.scale(MANE["dark"], 0.9), T.smoothstep(-0.25, -0.9, v) * (0.75 - 0.35 * back))
            c = T.mix(c, MANE["light_c"], back * 0.18 * T.clamp01(ctx.n[2] + 0.8))
            c = T.mix(c, MANE["light_c"], T.smoothstep(0.55, 0.95, v) * 0.3 * T.clamp01(ctx.n[2] + 0.6))
    return c


def p_ear(ctx, seed, p):
    """Ears in the mane's antique gold with a dark inner ear facing front."""
    c = T.metal(ctx, seed, {"patina": 0.05}, MANE["light_c"], MANE["base"], MANE["dark"], MANE["bounce"],
                MANE["patina"], 0.05)
    if ctx.n[0] > 0.55:
        c = T.mix(c, T.hexc("5A2A08"), T.smoothstep(0.55, 0.85, ctx.n[0]) * 0.8)
    return c


def p_gold(ctx, seed, p):
    return T.g_gold(ctx, seed, p)


def p_brass(ctx, seed, p):
    return T.g_brass(ctx, seed, p)


def p_copper(ctx, seed, p):
    return T.g_copper(ctx, seed, p)


def p_dark_walnut(ctx, seed, p):
    c = T.g_wood(ctx, seed, {"kind": "dark", "along": "t"})
    return T.mix(c, T.hexc("9A6640"), T.clamp01(ctx.n[2]) * 0.4)


def p_iron(ctx, seed, p):
    return T.g_iron(ctx, seed, {"rust": 0.05})


def p_cup(ctx, seed, p):
    """White porcelain with a bold royal-blue band and a gold line under it on the upper outer wall (painted by
    height and facing, so the inside stays white)."""
    c = T.g_ceramic(ctx, seed, {})
    x, y, z = ctx.pos
    lz = z - CUP_Z0
    ry = y - (CUP_Y if y > 0 else -CUP_Y)
    rx = x - BODY_X
    rr = math.hypot(rx, ry) or 1.0
    outward = (ctx.n[0] * rx + ctx.n[1] * ry) / rr
    if outward > 0.2:
        if 0.03 <= lz <= 0.052:
            c = T.mix(ENAMEL, T.scale(ENAMEL, 1.25), T.clamp01(ctx.n[0] * 0.5 + 0.5))
        elif 0.024 <= lz < 0.03:
            c = T.hexc("E8B848")
    return c


def p_coffee(ctx, seed, p):
    """Crema with a darker rim and a pale heart-ish swirl in the middle."""
    r = math.hypot(ctx.pos[0] - BODY_X, abs(ctx.pos[1]) - CUP_Y)
    c = T.mix(T.hexc("D8B98A"), T.hexc("6A3C1C"), T.smoothstep(0.02, 0.04, r))
    return T.mix(c, T.hexc("F4E6C8"), T.smoothstep(0.014, 0.004, r) * 0.8)


def p_saucer(ctx, seed, p):
    c = T.g_ceramic(ctx, seed, {})
    r = math.hypot(ctx.pos[0] - BODY_X, abs(ctx.pos[1]) - CUP_Y)
    if r > 0.058 and ctx.n[2] > 0.0:
        c = T.mix(c, ENAMEL, 0.85)      # a blue rim
    return c


def p_dial_case(ctx, seed, p):
    if ctx.chart.endswith("_top"):
        return T.hexc("F4EFE2")
    return T.g_brass(ctx, seed, {"streak": True})


def p_plate(ctx, seed, p):
    return T.g_brass(ctx, seed, {"streak": False, "patina": 0.05, "freq": 6.0})


BRONZE = dict(light_c=T.hexc("E0A860"), base=T.hexc("7A4A20"), dark=T.hexc("2A1608"), bounce=T.hexc("5A3418"),
              patina=T.hexc("4A5A3A"))


def p_tray(ctx, seed, p):
    """Dark bronze with a bright brass rim; the front edge (what players see at eye height) is a dark recessed
    band between two lit brass lips."""
    c = T.metal(ctx, seed, {"streak": False}, BRONZE["light_c"], BRONZE["base"], BRONZE["dark"], BRONZE["bounce"],
                BRONZE["patina"], 0.1)
    brass = T.g_brass(ctx, seed + 1, {"streak": False, "patina": 0.05})
    if ctx.chart == "+z":
        e = min(ctx.s, ctx.cw - ctx.s, ctx.t, ctx.ch - ctx.t)
        if e < 0.02:
            return T.mix(brass, T.hexc("FFE79A"), 0.25)
        return c
    if ctx.chart == "+x":
        if ctx.t < 0.012 or ctx.t > ctx.ch - 0.01:
            return T.mix(brass, T.hexc("FFE79A"), 0.3 if ctx.t < 0.012 else 0.0)
        return T.mix(T.hexc("1E140A"), c, 0.25)
    return c


# ---------------------------------------------------------------------------------------------- decals

def _shield(w2=0.15, top=0.12, mid=-0.02, bottom=-0.12, steps=6):
    """A heater shield outline (flat top, straight sides, curving to a point), CCW."""
    right = []
    for k in range(steps + 1):
        t = k / float(steps)
        right.append((w2 * (1.0 - t ** 2.2) ** 0.8, mid - (mid - bottom) * t))
    pts = [(0.0, bottom)] + right[::-1][1:] + [(w2, top), (-w2, top)]
    pts += [(-x, y) for x, y in right[:-1]]
    return pts


SHIELD = _shield()


def _inside(poly, x, y):
    c = False
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            c = not c
    return c


def _edge_dist(poly, x, y):
    best = 1e9
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        L = dx * dx + dy * dy or 1e-12
        t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / L))
        best = min(best, math.hypot(x - (x0 + t * dx), y - (y0 + t * dy)))
    return best


def d_plate(w, h):
    """The heraldic maker's plate: an inset frame that follows the shield, a royal-blue chief with "ROYAL BRASS"
    across the top and the lion in gold relief below it (text at the top, so the portafilter caps, which project
    onto the plate's lower corners in the 3/4 views, never cover it)."""
    xs = [q[0] for q in SHIELD]
    ys = [q[1] for q in SHIELD]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    poly = [((q[0] - x0) / (x1 - x0) * w, (y1 - q[1]) / (y1 - y0) * h) for q in SHIELD]
    img = T.Img(w, h, (0, 0, 0, 0))
    bw = max(2, int(min(w, h) * 0.035))
    dist = [0.0] * (w * h)
    for y in range(h):
        for x in range(w):
            if not _inside(poly, x + 0.5, y + 0.5):
                dist[y * w + x] = -1.0
                continue
            e = _edge_dist(poly, x + 0.5, y + 0.5)
            dist[y * w + x] = e
            if bw <= e < 2 * bw:
                img.set(x, y, T.hexc("5A3A12"), 0.85)
            elif e < bw:
                img.set(x, y, T.hexc("F2D27A"), 0.35)
    banner_h = int(h * 0.25)
    by0 = 2 * bw
    for y in range(by0, by0 + banner_h):
        for x in range(w):
            if dist[y * w + x] >= 2 * bw:
                img.set(x, y, T.scale(T.hexc("2C4A86"), 0.9 + 0.2 * (1 - (y - by0) / float(banner_h))), 1.0)
    for x in range(w):
        for yy in (by0 + banner_h, by0 + banner_h + 1):
            if 0 <= yy < h and dist[yy * w + x] >= 2 * bw:
                img.set(x, yy, T.hexc("F6D676"), 1.0)
    try:
        cap = F.fit_cap("ROYAL BRASS", w - 6 * bw, banner_h * 0.92, min_cap=4.0)
        m = F.vector_mask("ROYAL BRASS", cap)
        F.two_tone(img, m, T.hexc("FBE7A1"), T.hexc("1A1006"), (w - m.w) // 2, by0 + (banner_h - m.h) // 2, 1,
                   (1, 1), T.hexc("0A0804"))
    except ValueError:
        if min(w, h) >= 64:
            raise           # at full size a text that does not fit is an error (section 5.5.1)
    top = by0 + banner_h + 2
    es = int(min(w - 6 * bw, (h - top - 2 * bw)) * 0.98)
    if es > 8:
        rel = E.render_relief("lion_head", es, es, P2.GOLD_RELIEF)
        P2.composite(img, rel, (w - es) // 2, top + max(0, (h - top - 2 * bw - es) // 3))
    return img


def d_gauge(w, h):
    return P2.gauge_face(w, h, {"needle_deg": -90.0})


def d_grille(w, h):
    """Eight bold slots (about 0.06 yd each) in near-black between bronze bars."""
    return P2.grille(w, h, {"slots": 8, "margin": 0.16, "duty": 0.62, "dark": T.hexc("140C06")})


def d_side_crest(w, h):
    """A gold lion medallion centred on each side panel."""
    img = T.Img(w, h, (0, 0, 0, 0))
    s = int(min(w, h) * 0.5)
    rel = E.render_relief("lion_head", s, s, P2.GOLD_RELIEF)
    P2.composite(img, rel, (w - s) // 2, (h - s) // 2)
    return img


# ------------------------------------------------------------------------------------------------ parts

def _post(x, y):
    prof = [(0.05, BODY_Z0), (0.04, BODY_Z0 + 0.03), (0.035, 0.365), (0.048, 0.385), (0.03, 0.405),
            (0.05, 0.445), (0.03, 0.482), (0.0, 0.492)]
    return G.translate(G.lathe(prof, 8), x, y, 0.0)


def _hoop(z, hh, d, sides=16):
    """An outward band on the boiler wall (only the visible outer half of a torus): a lathe of four points."""
    r0 = BOILER_R - 0.004
    prof = [(r0, z - hh), (BOILER_R + d * 0.9, z - hh * 0.5), (BOILER_R + d * 0.9, z + hh * 0.5), (r0, z + hh)]
    return G.lathe(prof, sides, angle=80.0, name="hoop")


def _lobed(mesh, center, n, amp, phase=math.pi / 2):
    """Pushes a mesh in and out around the X axis through `center` with n rounded lobes (the radial distance
    in the YZ plane scaled by 1 + amp cos(n (phi - phase))), then re-smooths its normals."""
    out = mesh.copy()
    pts = []
    for x, y, z in out.p:
        qy, qz = y - center[1], z - center[2]
        phi = math.atan2(qz, qy)
        f = 1.0 + amp * math.cos(n * (phi - phase))
        pts.append((x, center[1] + qy * f, center[2] + qz * f))
    out.p = pts
    return G.recompute_normals(out, 75.0)


def _cross(r, w):
    """A plus-shaped polygon (four spokes) of arm length r and width w."""
    h = w / 2
    return [(h, h), (r, h), (r, -h), (h, -h), (h, -r), (-h, -r), (-h, -h), (-r, -h), (-r, h), (-h, h), (-h, r),
            (h, r)]


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (1.3, 0.7, 0.9)
    d.depth_with_handles = 0.9
    d.budget = 4000
    d.collision_max = 120
    d.atlas = {"atlas": 512}
    d.kind = "machine"
    d.max_height = 0.95
    d.sloped_top = True
    add = d.add

    # plinth: walnut, rounded edges, on four brass bun feet (low-poly: they hide under the plinth)
    plinth = G.box(1.3, 0.7, PLINTH_H - FEET_H, 0.025, z0=FEET_H)
    for ch in plinth.charts:
        ch.weight = {"-x": 0.45, "+z": 0.75, "-z": 0.2}.get(ch.name, 0.85)
    add(B.Part("plinth", plinth, paint=p_walnut, seed=11))
    bun = [(0.0, 0.0), (0.044, 0.004), (0.054, 0.018), (0.042, FEET_H + 0.006)]
    feet = [G.translate(G.lathe(bun, 6), sx * 0.27, sy * 0.57, 0.0) for sx in (1, -1) for sy in (1, -1)]
    add(B.Part("feet", G.merge(feet), paint=p_gold, seed=13, weight=0.4))

    # body: tapered enamel box framed in riveted brass
    body = G.box(BODY_W, BODY_D, BODY_Z1 - BODY_Z0, 0.04, faces="+x -x +y -y +z", z0=BODY_Z0)
    body = G.taper(body, TAPER, BODY_Z0, BODY_Z1)
    body = G.translate(body, BODY_X, 0.0, 0.0)
    for ch in body.charts:
        ch.weight = {"+x": 1.35, "-x": 0.55, "+z": 0.6}.get(ch.name, 1.0)
    add(B.Part("body", body, paint=p_body, seed=21, decals={"+y": d_side_crest, "-y": d_side_crest}))
    fx = BODY_X + BODY_D / 2       # body front at its foot

    # corner posts and the three-sided cup rail
    px0, px1 = BODY_X - BODY_D / 2 + 0.045, fx - 0.04
    py = BODY_W / 2 - 0.04
    add(B.Part("posts", G.merge([_post(px1, py), _post(px1, -py), _post(px0, py), _post(px0, -py)]),
               paint=p_gold, seed=31, weight=0.9))
    rz = 0.445
    rails = [G.sweep([(px1, py, rz), (px0, py, rz)], 0.016, 6), G.sweep([(px1, -py, rz), (px0, -py, rz)], 0.016, 6),
             G.sweep([(px0, py, rz), (px0, -py, rz)], 0.016, 6)]
    add(B.Part("rail", G.merge(rails), paint=p_brass, seed=33, weight=0.6))

    # boiler: flange, cylinder, tall elliptic dome (painted brass, not sphere-mapped)
    prof = [(0.262, 0.375), (0.262, 0.398), (0.25, 0.404), (BOILER_R, CYL_Z0), (BOILER_R, CYL_Z1)]
    dome_h = DOME_TOP - CYL_Z1
    for k in range(1, 6):
        a = (math.pi / 2) * k / 5
        prof.append((BOILER_R * math.cos(a) if k < 5 else 0.0, CYL_Z1 + dome_h * math.sin(a)))
    add(B.Part("boiler", G.translate(G.lathe(prof, 20), BODY_X, 0.0, 0.0), paint=p_boiler, seed=41, weight=1.2))
    hoops = [G.translate(_hoop(hz, hh, dd), BODY_X, 0.0, 0.0) for hz, hh, dd in HOOPS]
    add(B.Part("hoops", G.merge(hoops), paint=p_hoop, seed=43, weight=1.2))

    # lion finial: pedestal, a lobed mane torus facing +X with a lobed back cap, head, muzzle, ears
    ped = G.translate(G.lathe([(0.074, DOME_TOP - 0.02), (0.058, DOME_TOP + 0.004), (0.036, DOME_TOP + 0.018),
                               (0.032, DOME_TOP + 0.03), (0.0, DOME_TOP + 0.034)], 10), BODY_X, 0.0, 0.0)
    to_front = G.mat_chain(G.mat_translate(*MANE_C), G.mat_rot_y(math.pi / 2))
    mane = G.transform(G.torus(0.056, 0.026, 21, 5), to_front)
    mane = _lobed(mane, MANE_C, MANE_LOBES, 0.12)
    cap = G.transform(G.dome(0.086, 0.05, 3, 14), G.mat_chain(G.mat_translate(*MANE_C),
                                                              G.mat_rot_y(-math.pi / 2)))
    cap = _lobed(cap, MANE_C, MANE_LOBES, 0.1)
    head = G.translate(G.sphere(HEAD_R, 10, 6), *HEAD_C)
    snout = G.translate(G.sphere(SNOUT_R, 8, 4), *SNOUT_C)
    ears = []
    for s in (1, -1):
        a = math.radians(EAR_DEG)
        ear = G.transform(G.sphere(0.024, 8, 4), G.mat_chain(
            G.mat_translate(MANE_C[0] + 0.016, s * math.sin(a) * EAR_R, MANE_C[2] + math.cos(a) * EAR_R),
            G.mat_rot_x(-s * a), G.mat_scale(0.5, 0.95, 1.15)))
        ears.append(ear)
    add(B.Part("finial_mane", G.merge([mane, cap, ped]), paint=p_mane, seed=51, weight=1.5))
    add(B.Part("finial_head", G.merge([head, snout]), paint=p_lion, seed=53, weight=1.9))
    add(B.Part("finial_ears", G.merge(ears), paint=p_ear, seed=55, weight=1.5))

    # group heads (copper bells on brass brackets), iron baskets, walnut handles
    gh, brackets, baskets, handles = [], [], [], []
    for s in (1, -1):
        y = s * GH_Y
        gprof = [(0.05, 0.258), (0.064, 0.268), (0.071, 0.288), (0.068, 0.31), (0.06, 0.325), (0.074, 0.345),
                 (0.088, 0.362), (0.088, 0.382), (0.0, 0.385)]
        gh.append(G.translate(G.lathe(gprof, 10), fx + 0.08, y, 0.0))
        brackets.append(G.translate(G.box(0.1, 0.09, 0.045, faces="+x +y -y +z -z", z0=0.345), fx + 0.03, y, 0.0))
        baskets.append(G.translate(G.cylinder(0.058, 0.042, 10, (True, False)), fx + 0.08, y, 0.218))
        hdl = G.capsule(0.035, 0.215, 6)
        hdl = G.transform(hdl, G.mat_chain(G.mat_translate(fx + 0.1, y, 0.238), G.mat_rot_y(math.radians(96))))
        handles.append(hdl)
    add(B.Part("group_heads", G.merge(gh), paint=p_copper, seed=61, weight=1.1))
    add(B.Part("brackets", G.merge(brackets), paint=p_brass, seed=62, weight=0.6))
    add(B.Part("baskets", G.merge(baskets), paint=p_iron, seed=63, weight=0.7))
    add(B.Part("handles", G.merge(handles), paint=p_dark_walnut, seed=65))
    tips = []
    for s_ in (1, -1):
        d_ = (math.sin(math.radians(96)), 0.0, math.cos(math.radians(96)))
        tip = (fx + 0.1 + d_[0] * 0.21, s_ * GH_Y, 0.238 + d_[2] * 0.21)
        tips.append(G.translate(G.sphere(0.037, 8, 4), *tip))
    add(B.Part("handle_caps", G.merge(tips), paint=p_gold, seed=66, weight=0.5))

    # copper pipes from the boiler down into the group heads
    pipes = []
    for s in (1, -1):
        path = G.bezier_path((BODY_X + 0.1, s * 0.18, 0.47), (BODY_X + 0.26, s * 0.27, 0.53),
                             (fx + 0.06, s * GH_Y, 0.47), (fx + 0.08, s * GH_Y, 0.383), 7)
        pipes.append(G.sweep(path, 0.019, 6))
    add(B.Part("pipes", G.merge(pipes), paint=p_copper, seed=67, weight=0.7))

    # pressure gauge on a copper stem from the boiler front, tilted up: brass case, dial decal, brass bezel
    gz = 0.50
    tilt = G.mat_rot_y(math.radians(-12))
    gpos = G.mat_translate(BODY_X + BOILER_R + 0.035, 0.0, gz)
    case = G.transform(G.cylinder(0.082, 0.04, 16, (False, True)), G.mat_chain(gpos, tilt, G.MAT_DISC_FRONT))
    add(B.Part("gauge_case", case, paint=p_dial_case, seed=71, decals={"cyl_top": d_gauge}, weight=2.4))
    bezel = G.transform(G.torus(0.084, 0.016, 16, 4), G.mat_chain(gpos, tilt, G.MAT_DISC_FRONT,
                                                                  G.mat_translate(0, 0, 0.04)))
    stem = G.transform(G.cylinder(0.02, 0.06, 6, False), G.mat_chain(
        G.mat_translate(BODY_X + BOILER_R - 0.02, 0.0, gz), G.MAT_DISC_FRONT))
    add(B.Part("gauge_bezel", G.merge([bezel, stem]), paint=p_brass, seed=73, weight=0.8))

    # maker's plate: a heater shield leaning back with the body's taper
    plate = G.extrude(SHIELD, 0.022, 0.007)
    lean = math.atan(TAPER * BODY_D / 2 / (BODY_Z1 - BODY_Z0))
    plate = G.transform(plate, G.mat_chain(G.mat_translate(fx - 0.013, 0.0, 0.243), G.mat_rot_y(-lean),
                                           G.MAT_EXTRUDE_FRONT))
    for ch in plate.charts:
        ch.weight = 3.2 if ch.name.endswith("_front") else 0.5
    add(B.Part("plate", plate, paint=p_plate, seed=81, decals={"extrude_front": d_plate}))

    # steam wand (left, +Y) with its valve wheel; hot-water tap (right, -Y): thin chrome, sphere mapped
    wx = fx - 0.09
    side = BODY_W / 2
    wand_path = G.polyline_join(
        [(wx, side - 0.02, 0.345)],
        G.arc_path((wx, side + 0.035, 0.305), 0.04, math.pi / 2, 0.0, 4, ("y", "z"))[1:],
        [(wx + 0.01, side + 0.075, 0.22)],
        G.arc_path((wx + 0.045, side + 0.075, 0.19), 0.04, math.pi, math.pi * 1.25, 2, ("x", "z"))[1:],
        [(wx + 0.06, side + 0.078, 0.155)])
    wand = G.sweep(wand_path, lambda t: 0.024 - 0.006 * t, 6, caps=(False, True))
    tap_path = G.polyline_join(
        [(wx, -side + 0.02, 0.33)],
        G.arc_path((wx, -side - 0.03, 0.29), 0.04, math.pi / 2, math.pi, 4, ("y", "z"))[1:],
        [(wx + 0.005, -side - 0.07, 0.21)])
    tap = G.sweep(tap_path, 0.022, 6, caps=(False, True))
    add(B.Part("wand", wand, "chrome", "ChromeEnv"))
    add(B.Part("tap", tap, "chrome", "ChromeEnv"))
    wheel_m = G.mat_chain(G.mat_translate(wx, side + 0.03, 0.39), G.mat_rot_x(math.pi / 2))
    wheel = G.merge([
        G.transform(G.torus(0.05, 0.012, 12, 4), wheel_m),
        G.transform(G.extrude(_cross(0.05, 0.016), 0.014), G.mat_chain(wheel_m, G.mat_translate(0, 0, -0.007),
                                                                         G.mat_rot_z(math.pi / 4))),
        G.transform(G.cylinder(0.018, 0.04, 6, False), G.mat_chain(G.mat_translate(wx, side - 0.01, 0.39),
                                                                   G.mat_rot_x(-math.pi / 2)))])
    add(B.Part("valve_wheel", wheel, paint=p_brass, seed=91, weight=0.6))
    knob = G.translate(G.sphere(0.032, 6, 4), wx, -side - 0.012, 0.375)
    add(B.Part("tap_knob", knob, paint=p_gold, seed=93, weight=0.6))

    # drip tray: dark bronze, a bold painted grille, a dark front band between brass lips
    tray = G.box(0.9, 0.19, TRAY_H, 0.01, z0=PLINTH_H, faces="+x -x +y -y +z")
    tray = G.translate(tray, 0.245, 0.0, 0.0)
    for ch in tray.charts:
        ch.weight = {"+z": 0.9, "+x": 1.0}.get(ch.name, 0.4)
    add(B.Part("drip_tray", tray, paint=p_tray, seed=95, decals={"+z": d_grille}))

    # porcelain cups (1.5x real size) on the warmer, with saucers; a real wall thickness, so the bake does not
    # see the inner wall poking through the outer one
    cups, saucers = [], []
    for s in (1, -1):
        cprof = [(0.0, 0.0), (0.03, 0.0), (0.047, 0.06), (0.049, 0.066), (0.043, 0.063), (0.033, 0.026),
                 (0.0, 0.024)]
        cups.append(G.translate(G.lathe(cprof, 10), BODY_X, s * CUP_Y, CUP_Z0))
        sprof = [(0.0, 0.0), (0.05, 0.0), (0.069, 0.009), (0.066, 0.012), (0.0, 0.009)]
        saucers.append(G.translate(G.lathe(sprof, 10), BODY_X, s * CUP_Y, BODY_Z1))
    add(B.Part("cups", G.merge(cups), paint=p_cup, seed=97, weight=1.6, ao_floor=0.8))
    coffee = [G.translate(G.lathe([(0.0, 0.05), (0.0405, 0.05)][::-1], 10, cap_top=False), BODY_X, s * CUP_Y,
                          CUP_Z0) for s in (1, -1)]
    add(B.Part("coffee", G.merge(coffee), paint=p_coffee, seed=98, weight=0.7, ao_floor=0.6))
    add(B.Part("saucers", G.merge(saucers), paint=p_saucer, seed=99, weight=0.8, ao_floor=0.8))

    # boiler safety valve on the dome (the vent wisp rises from it)
    vx, vy = BODY_X - 0.13, 0.10
    rho = math.hypot(vx - BODY_X, vy)
    vz = CYL_Z1 + dome_h * math.sin(math.acos(min(1.0, rho / BOILER_R))) - 0.01
    vent = G.translate(G.lathe([(0.026, vz - 0.02), (0.026, vz + 0.03), (0.034, vz + 0.035), (0.034, vz + 0.045),
                                (0.0, vz + 0.05)], 8), vx, vy, 0.0)
    add(B.Part("vent", vent, paint=p_brass, seed=101, weight=0.6))

    # collision: walls to 0.45, a gable roof to 0.9 (roof n.z 0.61 < 0.6428: too steep to stand on)
    hx, hy, wz, top = 0.35, 0.65, 0.45, 0.9
    pos = [(-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0), (-hx, -hy, wz), (hx, -hy, wz), (hx, hy, wz),
           (-hx, hy, wz), (0.0, -hy, top), (0.0, hy, top)]
    tris = [(0, 2, 1), (0, 3, 2),             # bottom
            (1, 2, 6), (1, 6, 5),             # front (+X)
            (3, 0, 4), (3, 4, 7),             # back (-X)
            (0, 1, 5), (0, 5, 4), (4, 5, 8),  # right (-Y) with its gable
            (2, 3, 7), (2, 7, 6), (6, 7, 9),  # left (+Y) with its gable
            (5, 6, 9), (5, 9, 8),             # front roof
            (7, 4, 8), (7, 8, 9)]             # back roof
    d.collision = (pos, tris)

    tip = wand_path[-1]
    d.particles = [
        B.ParticleDef((tip[0], tip[1], tip[2] - 0.02), "Steam"),
        B.ParticleDef((vx, vy, vz + 0.05), "Steam", speed=0.18, variation=0.3, latitude=0.2, gravity=-0.1,
                      life=1.4, emission_rate=4.0, scales=((0.03, 0.03), (0.1, 0.1), (0.18, 0.18)),
                      alphas=(0, 12000, 0)),
    ]
    d.model_frame = {"position": [0, 0, -0.35], "scale": 1.6, "facing": 0.4}
    return d
