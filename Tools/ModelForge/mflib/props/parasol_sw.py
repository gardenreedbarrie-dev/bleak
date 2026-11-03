"""19316 ParasolSW, the Lion's Roast Parasol (Stormwind table parasol), CAFE.SPEC.md section 5.8.1.

A café parasol in royal blue and cream over a table, shaped so it reads as "a café umbrella" at a glance from
the front three-quarter view and from a chair under it: a wide, shallow octagonal dome of eight panels in
alternating blue and cream (the eight stripes), a scalloped valance at the rim with gold trim and tassels, a
vented top tier under a fat gold ball finial, and one brass pole on a weighted base. Seated players see the
underside: the panels glowing warm with the light through the cloth (the royal-blue lion medallion printed on
the cream panels showing through as a lion face in a thin ring), eight walnut ribs, and the flat brass struts that hold
them open, meeting at a runner on the pole. From a third-person camera above, each cream panel carries the lion
medallion: a royal-blue roundel in a broad gold ring with the gold lion in relief. Ø 2.8 x 3.2 yd; the pole
stands through the table centre (section 3.12.3), so the base is low and compact.

What makes a player name it at 4-15 yd, and how big each cue is (about 95 px per yard at 10 yd):
- the striped canopy: 2.8 across, the cloth rim at 2.68 at the ribs (2.65 between them), apex under the vent at
  3.0; each panel 1.04 wide at the rim;
- the scalloped valance: 0.14 deep, two scallops 0.52 wide per panel and a fat gold tassel bead (0.08) between
  them; its hem is the lowest cloth, at 2.51 or above, so a draenei (about 2.35) walks under it. Its gold top
  binding (0.032) and scallop piping (0.03) are trim, not cues: at mip 1 they blur into a gold edge;
- the brass pole: 0.12 thick with two turned brass collars (0.18 tall: a bright highlight line, gold, dark gold
  edges), from a royal-blue enamel base (0.66 across, 0.13 high) with a brass rim;
- the mechanism under the canopy: walnut ribs 0.064 wide hanging 0.045 under the cloth, eight flat brass struts
  (0.06 wide, broad face down) from a runner collar (0.17 across);
- the vented top: a second tier 1.0 across over a dark slot 0.067 tall at the ribs and 0.073 mid-panel (under
  a thin gold binding), crowned by a gold ball finial 0.17 across whose top sets the 3.2 height;
- Stormwind: royal blue, cream and gold; the lion medallions (0.46 across, a gold ring 0.04 wide) on the four
  cream panels; the octagonal royal-blue enamel base with four crisp gold bosses (0.1).

Deviations from the section 5.8.1 design:
- a vented top tier (not in the design) gives the classic market-umbrella silhouette at 15 yd and hides the
  apex; the gold finial sits on it, so the main canopy's apex is at 3.0 and the finial ends at 3.2;
- the canopy is a gentle dome (three rings, steeper toward the rim), not a straight cone; "rim >= 2.5" is read
  strictly, as in ParasolOrg: nothing hangs under 2.5, so the cloth rim is at 2.65-2.68 and the valance hangs
  from it (the dome rises 0.32);
- the pole is r 0.06, not 0.05: a 0.1 pole over 2.7 yd read spindly next to the chunky canopy;
- the pole's collision hull (8 sides, r 0.08) rises to 2.6 and ends in a point at 2.75 (30 triangles), so a
  player who jumps from the table finds nothing flat to stand on;
- ribs, struts and a runner are modelled under the canopy for the seated view; the brass rib tips stick out of
  the rim and set the 2.8 extent (a detail, too small to be a cue);
- the stripes are whole panels (8 panels, 8 stripes); the panel charts of each shell are packed two strips of
  four, with every other panel upside down, so the triangular panels use about half the texture space they
  would as rectangles (both shells and the vent); the paints find the panel from the texel's position;
- added: the lion medallions on the cream panels (the top is what the third-person camera sees most), and
  the lion printed through the cloth on the underside (a royal-blue decal on the underside's strips);
- the underside's cream is painted as a warm tan canvas with a high floor under the glow: a downward face gets
  only the ambient light in game and the bake darkens it again, so it renders at about a third of its paint
  value; a warm tan reads as shaded canvas there, a pale cream as dingy grey.
"""
import math

from .. import build as B
from .. import emblem as E
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "ParasolSW"
DISPLAY = 19316

TAU = 2.0 * math.pi
BLUE = T.hexc("3F6FB5")
CREAM = T.hexc("F1E6CC")
ENAMEL = T.hexc("2E4E8C")
GOLD = T.hexc("E8B848")
GOLD_DK = T.hexc("8A5A12")

N = 8                                  # panels (ribs at k * 45 degrees: rib tips on the X and Y axes)
PANEL_A = TAU / N
RIM_R = 1.36                           # the cloth's rim radius at the ribs
TIP_R = 1.40                           # the rib tips: the 2.8 extent
PINCH = 0.03                           # the rim curves in between the ribs (a taut panel)
APEX_Z, RIM_Z = 3.0, 2.68
RINGS = (0.0, 0.4, 0.75, 1.0)          # ring radii as fractions of the rim radius
COLS = 3                               # columns per panel (the billow)
BILLOW = 0.03                          # each panel sags this much between its ribs at the rim
GAP = 0.014                            # the underside shell sits this far under the top
VALANCE = 0.14                         # valance depth (its hem at 2.51 or above)
FLARE = 0.022                          # the valance flares out this much at its hem
RIB_W, RIB_D = 0.032, 0.045            # rib half width and depth under the cloth (0.064 wide)
VENT_R, VENT_Z0, VENT_Z1 = 0.50, 2.99, 3.09   # the vent tier: rim radius, rim height, apex
POLE_R = 0.06
BASE_R, BASE_H = 0.33, 0.13
RUN_Z = 2.3                            # the runner, where the struts meet the pole
STRUT_T = 0.45                         # struts meet the ribs at this ring fraction
STRUT_W, STRUT_H = 0.06, 0.024         # the flat strut bars: width (broad face down) and thickness
CROWN_Z = 2.86
TOP_Z = 3.2


def _zprof(t):
    """The canopy's height at ring fraction t: a gentle dome, steeper toward the rim."""
    return APEX_Z - (APEX_Z - RIM_Z) * t ** 1.3


def _panel(x, y):
    """(panel index, u across the panel 0..1) of a point, from its angle round the pole."""
    q = (math.atan2(y, x) % TAU) / PANEL_A
    i = int(math.floor(q))
    return i % N, q - i


def _rim_r(u):
    return RIM_R * (1.0 - PINCH * math.sin(math.pi * u))


# ----------------------------------------------------------------------------------------------- paints

def _cloth(i):
    return BLUE if i % 2 == 0 else CREAM


def p_top(ctx, seed, p):
    """Blue and cream cloth, sun-bleached toward the apex, stitched seams along the ribs, a hem near the rim."""
    x, y, z = ctx.pos
    i, u = _panel(x, y)
    rr = math.hypot(x, y)
    c = _cloth(i)
    v = T.fbm(x * 2.5 + 7.0, y * 2.5, seed, 3)
    c = T.scale(c, 0.93 + 0.12 * v)
    t = rr / RIM_R
    c = T.mix(c, (1.0, 0.98, 0.92), T.smoothstep(0.55, 0.0, t) * (0.16 if i % 2 == 0 else 0.06))
    d_rib = min(u, 1.0 - u) * PANEL_A * rr
    seam = T.scale(c, 0.55) if i % 2 == 0 else T.hexc("A88C60")
    if d_rib < 0.024:
        c = T.mix(c, seam, 0.75 * T.smoothstep(0.024, 0.008, d_rib) + 0.1)
    elif d_rib < 0.045:
        c = T.mix(c, (1.0, 1.0, 1.0), 0.12)
    d_rim = _rim_r(u) - rr
    if d_rim < 0.07:
        c = T.mix(c, T.scale(c, 0.8), 0.6)
        if 0.045 < d_rim < 0.06:
            c = T.mix(c, seam, 0.7)
    if ctx.curv > 0:
        c = T.mix(c, (1.0, 1.0, 1.0), T.clamp01(ctx.curv) * 0.3)
    return c


def p_under(ctx, seed, p):
    """The underside seen from the chairs: the cloth glowing with the light through it (brightest mid-panel),
    dark seams and rib shadows along the ribs, a doubled hem at the rim and a shaded crown."""
    x, y, z = ctx.pos
    i, u = _panel(x, y)
    rr = math.hypot(x, y)
    d_rib = min(u, 1.0 - u) * PANEL_A * rr
    glow = math.sin(math.pi * u) ** 0.6 * T.smoothstep(0.05, 0.5, rr / RIM_R)
    if i % 2 == 0:
        c = T.mix(T.hexc("24447E"), T.hexc("6A9EF0"), 0.5 + 0.5 * glow)
        dark = T.hexc("24447E")
    else:
        # a warm tan canvas with a high floor (0.7): a downward face gets only the bluish ambient light in game
        # and renders at about a third of its paint, where a pale cream turns dingy grey and a tan reads as
        # shaded canvas (red over blue about 1.6)
        dark = T.hexc("C89A60")
        c = T.mix(dark, T.hexc("FFD9A0"), 0.7 + 0.3 * glow)
        c = T.mix(c, T.hexc("FFD088"), 0.15 * glow)     # warm sunlight through the cloth
    v = T.fbm(x * 2.0, y * 2.0 + 3.0, seed, 3)
    c = T.scale(c, 0.92 + 0.14 * v)
    if d_rib < 0.07:
        c = T.mix(c, dark, T.smoothstep(0.07, 0.0, d_rib) * 0.35)
    if d_rib < 0.012:
        c = T.mix(c, T.scale(dark, 0.6), 0.7)
    d_rim = _rim_r(u) - rr
    if d_rim < 0.075:
        c = T.mix(c, dark, 0.45)
        if d_rim < 0.012:
            c = T.mix(c, GOLD_DK, 0.5)
    c = T.mix(c, T.scale(dark, 0.7), T.smoothstep(0.25, 0.05, rr) * 0.45)
    return c


def _ellipse_edge(dx, dy, rx, ry):
    """(inside, distance to the edge in yards, roughly) of a point (dx, dy) against an ellipse."""
    q = math.sqrt((dx / rx) ** 2 + (dy / ry) ** 2)
    return q < 1.0, (1.0 - q) * min(rx, ry)


def p_valance(ctx, seed, p):
    """The scalloped valance (cutout): solid cloth with a gold top binding, two scallops per panel edged in
    gold piping, and a gold tassel hanging between the scallops. Alpha 0 outside the cloth. The binding (0.032)
    and the piping (0.03) are trim, about 2.6 texels at the valance's density (they blur into a gold edge from
    about 15 yd); the tassel bead (0.08) is the gold cue. Wider piping would swallow the cloth of scallops only
    0.09 deep."""
    s, t, L, D = ctx.s, ctx.t, ctx.cw, ctx.ch
    i, _u = _panel(ctx.pos[0], ctx.pos[1])
    c = _cloth(i)
    c = T.scale(c, 0.92 + 0.12 * T.fbm(s * 3.0, t * 3.0 + i, seed, 2))
    gold = T.mix(GOLD, (1.0, 0.95, 0.7), T.smoothstep(0.3, 0.9, T.noise(s * 14.0, t * 14.0, seed + 3)) * 0.4)
    n = 2
    w = L / n
    band = 0.045                                    # the binding (0.032) and the dark line under it
    lobe = D - band - 0.008
    k = min(n - 1, max(0, int(s / w)))
    sc = (k + 0.5) * w
    if t < band:
        inside, edge = True, 1.0
    else:
        inside, edge = _ellipse_edge(s - sc, t - band, w * 0.5, lobe)
    # tassels between the scallops: a cord and a bead
    for j in range(1, n):
        sj = j * w
        if abs(s - sj) < 0.02 and band - 0.01 < t < D - 0.05:
            return (gold[0] * 0.85, gold[1] * 0.85, gold[2] * 0.85, 1.0)
        db = math.hypot(s - sj, (t - (D - 0.04)) * 0.8)
        if db < 0.04:
            k2 = T.clamp01(0.6 - (t - (D - 0.04)) / 0.04 * 0.5 - (s - sj) / 0.04 * 0.3)
            return T.mix(T.scale(GOLD_DK, 1.1), (1.0, 0.94, 0.66), k2) + (1.0,)
    if not inside:
        return (c[0], c[1], c[2], 0.0)
    if t < 0.032:
        c = T.mix(gold, T.scale(gold, 0.6), T.smoothstep(0.01, 0.032, t))
    elif t < 0.042:
        c = T.scale(c, 0.6)
    if t >= band - 0.012 and edge < 0.03:
        c = T.mix(gold, T.scale(gold, 0.55), T.smoothstep(0.012, 0.03, edge) * 0.8)
    return (c[0], c[1], c[2], 1.0)


def p_vent(ctx, seed, p):
    """The vent tier's cloth (as the top) and its skirt: a dark slot under a gold binding."""
    if ctx.chart == "skirt":
        # the skirt shows about 0.08 under the tier: a thin gold binding over a solid dark slot (0.067 at the
        # ribs, 0.073 mid-panel), the vent's gap; scallop lobes on it ate half the slot
        t = ctx.t
        if t < 0.012:
            return T.mix(GOLD, T.scale(GOLD, 0.6), t / 0.012)
        return T.hexc("1A2238")
    return p_top(ctx, seed, p)


def p_rib(ctx, seed, p):
    """Walnut ribs with brass tips past the rim."""
    rr = math.hypot(ctx.pos[0], ctx.pos[1])
    if rr > RIM_R - 0.02:
        return T.g_brass(ctx, seed + 1, {"streak": False, "patina": 0.05})
    c = T.g_wood(ctx, seed, {"kind": "walnut", "along": "t"})
    return T.mix(c, T.hexc("A06A40"), T.clamp01(-ctx.n[2]) * 0.3)


def p_brass(ctx, seed, p):
    return T.g_brass(ctx, seed, {"patina": 0.08})


def p_gold(ctx, seed, p):
    return T.g_gold(ctx, seed, {"patina": 0.05})


def p_pole(ctx, seed, p):
    """Brass pole: a polished streak, two turned collars of polished brass (a pale highlight line 0.04 tall, gold
    out to 0.12, dark gold edges out to 0.18) and a darker foot. Brighter rings rendered as white tape."""
    c = T.g_brass(ctx, seed, {"patina": 0.1, "streak_w": 0.5})
    z = ctx.pos[2]
    for zc in (1.35, 2.1):
        d = abs(z - zc)
        if d < 0.02:
            c = T.hexc("FFF4C0")
        elif d < 0.06:
            c = GOLD
        elif d < 0.09:
            c = GOLD_DK
    return T.mix(c, T.scale(c, 0.7), T.smoothstep(0.6, 0.15, z) * 0.5)


def p_base(ctx, seed, p):
    """The weighted base: royal-blue enamel over cast iron with a brass rim and collar and four crisp gold bosses
    (0.1 across: solid gold, a dark rim 0.012 wide, a highlight dot toward the pole)."""
    x, y, z = ctx.pos
    if z < 0.042 or z > BASE_H - 0.012:
        return T.g_brass(ctx, seed + 1, {"patina": 0.12})
    c = T.g_enamel(ctx, seed, {"color": ENAMEL, "chips": 2, "chip_r": 0.03, "gloss": 0.35})
    a = math.atan2(y, x)
    rr = math.hypot(x, y)
    da = ((a % (math.pi / 2)) - math.pi / 4) * rr     # across, from the nearest boss (at 45 degrees and so on)
    dr = rr - 0.235                                    # outward (down the slope)
    d = math.hypot(da, dr)
    if d < 0.05:
        if d > 0.038:
            return T.hexc("5A3A08")
        c = GOLD
        if math.hypot(da + 0.008, dr + 0.012) < 0.012:
            c = T.hexc("FFF4C0")
        elif dr > 0.012:
            c = T.scale(GOLD, 0.8)                     # the boss's lower edge, away from the light
    return c


# ---------------------------------------------------------------------------------------------- decals

def d_medallions(chart_w, chart_h, chord, slots, t_c=0.7, diam=0.46, shadow=False):
    """The lion medallions printed on the cream panels of one canopy strip chart (see _strip_shell): a royal-
    blue roundel in a broad gold ring with the gold lion in relief, 0.46 yd across at 0.7 of the way down the
    panel (where the dome turns toward an eye-level viewer). Panels in odd slots lie upside down in the strip
    (apex at the bottom), so their medallion is flipped. With shadow, the print as seated customers see it
    through the sunlit cloth: the lion printed in royal blue, `diam` across, on the underside's strip (the same
    layout; the lion is symmetric, so seen from below it is not mirrored), in a thin ring (0.03) at its edge, so
    it reads as the medallion on the top seen through the cloth (the lion 3/4 of its width, as on the top, so
    the mane does not run into the ring). The mane is a light print, the face left as cloth, the eyes, nose and
    mouth darker; a plain silhouette read as a spiky stain, and with the brows and inner ears too, the face read
    as a sun with sunglasses at the underside's 25 texels."""
    def draw(w, h):
        img = T.Img(w, h, (0.0, 0.0, 0.0, 0.0))
        kx, ky = w / chart_w, h / chart_h
        r = diam * 0.5 * min(kx, ky)
        if r < 5:
            return img
        if shadow:
            # the lion at 3/4 of the print (as on the top medallion), a ring of cloth round it, then the ring
            size = max(4, int(r * 2.0))
            ls = max(4, int(r * 1.5))
            lm = {name: m for name, m, _mode, _h in E.layer_masks("lion_head", ls, ls)}

            def cover(names, i):
                return max(lm[n].a[i] for n in names)

            mane = ("mane", "mane_inner", "ear_l", "ear_r")
            feats = ("eye_l", "eye_r", "nose", "mouth")
            alpha = [0.0] * (size * size)
            lo = (size - ls) // 2
            for i in range(ls * ls):
                a = max(cover(mane, i) * 0.45 * (1.0 - lm["face"].a[i]), cover(feats, i) * 0.5)
                alpha[(i // ls + lo) * size + i % ls + lo] = a
            # the ring at the print's edge: 0.03 wide, its outer edge at diam / 2
            rw = 0.03 * min(kx, ky)
            for k in range(size * size):
                dd = math.hypot(k % size + 0.5 - size / 2.0, k // size + 0.5 - size / 2.0)
                cov = T.clamp01(min(r + 0.5 - dd, dd - (r - rw) + 0.5))
                alpha[k] = max(alpha[k], cov * 0.5)
            for slot in slots:
                cx = (slot * chord / 2.0 + chord / 2.0) * kx
                flip = slot % 2 == 1
                cy = (1.0 - t_c if flip else t_c) * chart_h * ky
                ox, oy = int(round(cx - size / 2.0)), int(round(cy - size / 2.0))
                for y in range(size):
                    for x in range(size):
                        a = alpha[y * size + x]
                        if a <= 0.0:
                            continue
                        X, Y = ox + x, oy + (size - 1 - y if flip else y)
                        if 0 <= X < w and 0 <= Y < h:
                            img.blend(X, Y, ENAMEL, a)
                            img.a[Y * w + X] = max(img.a[Y * w + X], a)
            return img
        size = max(4, int(r * 1.5))
        rel = E.render_relief("lion_head", size, size, P2.GOLD_RELIEF)
        ring = max(1.5, r * 0.18)
        for slot in slots:
            cx = (slot * chord / 2.0 + chord / 2.0) * kx
            flip = slot % 2 == 1
            cy = (1.0 - t_c if flip else t_c) * chart_h * ky
            for y in range(max(0, int(cy - r - 2)), min(h, int(cy + r + 3))):
                for x in range(max(0, int(cx - r - 2)), min(w, int(cx + r + 3))):
                    dx, dy = x + 0.5 - cx, y + 0.5 - cy
                    d = math.hypot(dx, dy)
                    if d > r + 0.5:
                        continue
                    a = T.clamp01(r + 0.5 - d)
                    if d > r - ring:
                        # the gold ring, lit from the top of the panel, a darker gold line where it meets the field
                        up = -dy if not flip else dy
                        c = T.mix(T.hexc("C08A28"), T.hexc("FFE89A"), T.clamp01(0.5 + up / r * 0.6))
                        if d < r - ring + 1.0:
                            c = T.scale(c, 0.7)
                    else:
                        c = T.mix(ENAMEL, T.hexc("5A88D0"), T.clamp01(0.75 - d / r * 0.6))
                    img.blend(x, y, c, a)
                    img.a[y * w + x] = max(img.a[y * w + x], a)
            ox, oy = int(round(cx - size / 2.0)), int(round(cy - size / 2.0))
            for y in range(size):
                for x in range(size):
                    a = rel.a[y * size + x]
                    if a <= 0.0:
                        continue
                    sy = size - 1 - y if flip else y
                    X, Y = ox + x, oy + sy
                    if 0 <= X < w and 0 <= Y < h:
                        img.blend(X, Y, (rel.r[y * size + x], rel.g[y * size + x], rel.b[y * size + x]), a)
        return img
    return draw


# -------------------------------------------------------------------------------------------- geometry

def _mesh_z(t):
    """The canopy's height along a rib as the mesh has it: linear between the rings."""
    for t0, t1 in zip(RINGS, RINGS[1:]):
        if t <= t1:
            return _zprof(t0) + (_zprof(t1) - _zprof(t0)) * (t - t0) / (t1 - t0)
    return _zprof(1.0)


def _strip_shell(name, angs, rings, cols, zf, rim_fn, billow, up, per_strip=4, weight=1.0):
    """A canopy shell of len(angs) panels as one mesh whose panels are packed in strips of `per_strip`: every
    other panel upside down, so two triangular panels share a parallelogram of texture instead of two
    rectangles. angs: rib angles (radians, increasing); rings: ring fractions from the apex (0) to the rim (1);
    zf(t): height; rim_fn(i, u): rim radius of panel i at u; up: the top shell (normals up) or the underside.
    The chart coordinates are in yards like any chart (the paints use ctx.pos, not s/t)."""
    n = len(angs)
    m = G.Mesh()
    chords = []
    slants = []
    for i in range(n):
        a0, a1 = angs[i], angs[(i + 1) % n] + (TAU if i == n - 1 else 0.0)
        r0, r1 = rim_fn(i, 0.0), rim_fn(i, 1.0)
        p0 = (math.cos(a0) * r0, math.sin(a0) * r0)
        p1 = (math.cos(a1) * r1, math.sin(a1) * r1)
        chords.append(math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
        slants.append(math.hypot(rim_fn(i, 0.5), zf(i, 0.5, 0.0) - zf(i, 0.5, 1.0)))
    c = max(chords)
    hgt = max(slants)
    nstrips = (n + per_strip - 1) // per_strip
    charts = [m.chart((per_strip + 1) * c / 2.0, hgt, "%s%d" % (name, q)) for q in range(nstrips)]
    for ch in charts:
        m.charts[ch].weight = weight
    for i in range(n):
        a0, a1 = angs[i], angs[(i + 1) % n] + (TAU if i == n - 1 else 0.0)
        slot = i % per_strip
        ch = charts[i // per_strip]
        grid = {}
        for k, t in enumerate(rings):
            for j in range(cols + 1):
                u = j / float(cols)
                a = a0 + (a1 - a0) * u
                rr = rim_fn(i, u) * t
                z = zf(i, u, t) - billow * math.sin(math.pi * u) * t
                s = slot * c / 2.0 + c / 2.0 + (u - 0.5) * c * t
                tt = hgt * t if slot % 2 == 0 else hgt * (1.0 - t)
                grid[(k, j)] = m.vert((math.cos(a) * rr, math.sin(a) * rr, z), (0.0, 0.0, 1.0 if up else -1.0),
                                      ch, s, tt)
        for k in range(len(rings) - 1):
            for j in range(cols):
                a, b = grid[(k, j)], grid[(k, j + 1)]
                cc, d = grid[(k + 1, j + 1)], grid[(k + 1, j)]
                if up:
                    m.tri(a, d, cc)
                    m.tri(a, cc, b)
                else:
                    m.tri(a, cc, d)
                    m.tri(a, b, cc)
    return G.recompute_normals(m, 30.0)


def _tri_out(m, a, b, c, ref):
    """Adds triangle (a, b, c) wound so its normal points away from the point ref."""
    pa, pb, pc = m.p[a], m.p[b], m.p[c]
    nrm = G.cross(G.sub(pb, pa), G.sub(pc, pa))
    cen = tuple((pa[k] + pb[k] + pc[k]) / 3.0 for k in range(3))
    if G.dot(nrm, G.sub(cen, ref)) < 0:
        m.tri(a, c, b)
    else:
        m.tri(a, b, c)


def _rib(path, side, w, d, name="rib"):
    """An inverted-V rib hanging under the cloth along `path` (points on the cloth's underside): two faces
    from the cloth line down to a keel `d` below it, `w` either side; the outer end is closed (a cap and a top
    over the last segment, where the rib sticks out past the rim)."""
    m = G.Mesh()
    total = sum(G.length(G.sub(path[k + 1], path[k])) for k in range(len(path) - 1))
    hw = math.hypot(w, d)
    ch = m.chart(2.0 * hw, total + hw, name)       # the end cap gets the strip past `total`
    rows = []
    acc = 0.0
    for k, p in enumerate(path):
        if k:
            acc += G.length(G.sub(p, path[k - 1]))
        tang = G.norm(G.sub(path[min(k + 1, len(path) - 1)], path[max(k - 1, 0)]))
        down = G.norm(G.cross(tang, side))
        if down[2] > 0:
            down = G.mul(down, -1.0)
        left, right = G.add(p, G.mul(side, w)), G.sub(p, G.mul(side, w))
        keel = G.add(p, G.mul(down, d))
        rows.append((m.vert(left, side, ch, 0.0, acc), m.vert(keel, down, ch, hw, acc),
                     m.vert(right, G.mul(side, -1.0), ch, 2 * hw, acc), keel))
    for k in range(len(path) - 1):
        l0, k0, r0, kp0 = rows[k]
        l1, k1, r1, kp1 = rows[k + 1]
        ref = G.lerp(path[k], path[k + 1], 0.5)
        ref = G.add(ref, G.mul(G.sub(G.lerp(kp0, kp1, 0.5), ref), 0.3))
        _tri_out(m, l0, k0, k1, ref)
        _tri_out(m, l0, k1, l1, ref)
        _tri_out(m, k0, r0, r1, ref)
        _tri_out(m, k0, r1, k1, ref)
    l0, k0, r0, kp0 = rows[-2]
    l1, k1, r1, kp1 = rows[-1]
    ref = G.lerp(G.lerp(path[-2], path[-1], 0.5), G.lerp(kp0, kp1, 0.5), 0.3)
    tip = path[-1]
    tang = G.norm(G.sub(path[-1], path[-2]))
    cap = [m.vert(m.p[v], tang, ch, s, total + (hw if v == k1 else 0.0)) for v, s in ((l1, 0.0), (k1, hw),
                                                                                      (r1, 2 * hw))]
    _tri_out(m, cap[0], cap[1], cap[2], G.sub(tip, tang))   # end cap
    _tri_out(m, l0, l1, r1, ref)          # top over the last segment
    _tri_out(m, l0, r1, r0, ref)
    return G.recompute_normals(m, 50.0)


def _bar(p0, p1, w, h, name="strut"):
    """A flat bar from p0 to p1, w wide and h thick, its broad faces turned up and down (the side seen from
    under the canopy): four long faces, open ends (they sit in the runner and under a rib). 8 triangles."""
    m = G.Mesh()
    axis = G.norm(G.sub(p1, p0))
    side = G.norm(G.cross((0.0, 0.0, 1.0), axis))
    up = G.cross(axis, side)
    L = G.length(G.sub(p1, p0))
    ch = m.chart(2.0 * (w + h), L, name)
    mid = G.lerp(p0, p1, 0.5)
    s0 = 0.0
    for nrm, span, depth in ((G.mul(up, -1.0), w, h), (side, h, w), (up, w, h), (G.mul(side, -1.0), h, w)):
        # the face's two long edges: its centre line is depth / 2 out along nrm, its edges span / 2 either side
        off = G.mul(nrm, depth * 0.5)
        e = G.mul(G.cross(nrm, axis), span * 0.5)
        vs = []
        for p, t in ((p0, 0.0), (p1, L)):
            c = G.add(p, off)
            vs.append((m.vert(G.sub(c, e), nrm, ch, s0, t), m.vert(G.add(c, e), nrm, ch, s0 + span, t)))
        (a0, b0), (a1, b1) = vs
        _tri_out(m, a0, b0, b1, mid)
        _tri_out(m, a0, b1, a1, mid)
        s0 += span
    return m


def _valance(angs, rim_fn, zf, depth, flare, out=0.004):
    """The valance: per panel, a band hanging from the top shell's rim edge (following its billow), flaring
    out toward the hem; one chart per panel, s along the rim (left to right seen from outside), t down."""
    m = G.Mesh()
    n = len(angs)
    for i in range(n):
        a0, a1 = angs[i], angs[(i + 1) % n] + (TAU if i == n - 1 else 0.0)
        tops = []
        for j in range(COLS + 1):
            u = j / float(COLS)
            a = a0 + (a1 - a0) * u
            rr = rim_fn(i, u) + out
            z = zf(i, u, 1.0) - BILLOW * math.sin(math.pi * u) + 0.004
            tops.append((a, rr, z))
        length = 0.0
        for j in range(COLS):
            (a, r, _z), (b, r2, _z2) = tops[j], tops[j + 1]
            length += math.hypot(math.cos(b) * r2 - math.cos(a) * r, math.sin(b) * r2 - math.sin(a) * r)
        ch = m.chart(length, math.hypot(depth, flare), "valance%d" % i)
        acc = 0.0
        prev = None
        cols = []
        for a, rr, z in tops:
            p = (math.cos(a) * rr, math.sin(a) * rr)
            if prev:
                acc += math.hypot(p[0] - prev[0], p[1] - prev[1])
            prev = p
            out_n = (math.cos(a), math.sin(a), 0.0)
            top = m.vert((p[0], p[1], z), out_n, ch, acc, 0.0)
            rb = rr + flare
            bot = m.vert((math.cos(a) * rb, math.sin(a) * rb, z - depth), out_n, ch, acc, math.hypot(depth, flare))
            cols.append((top, bot))
        for j in range(COLS):
            (tl, bl), (tr, br) = cols[j], cols[j + 1]
            m.tri(tl, bl, br)
            m.tri(tl, br, tr)
    return G.recompute_normals(m, 60.0)


def _vent():
    """The vented top tier: eight flat cloth facets from its apex to a rim 1.0 across, and a short skirt from
    that rim down into the canopy (painted as a dark slot under a thin gold binding): the tier stands about 0.08
    over the canopy, so the slot reads from eye level. The cone has one column per panel, so its rim
    is the same octagon as the 8-sided skirt (no crack between them mid-panel)."""
    angs = [PANEL_A * i for i in range(N)]

    def zf(_i, _u, t):
        return VENT_Z1 - (VENT_Z1 - VENT_Z0) * t

    cone = _strip_shell("vent", angs, (0.0, 1.0), 1, zf, lambda _i, _u: VENT_R, 0.0, True, per_strip=8)
    # the skirt ends inside the gap between the canopy's two shells under it (about 0.045 deep)
    z0 = _mesh_z(VENT_R / RIM_R) - GAP + 0.002
    skirt = G.lathe([(VENT_R - 0.002, z0), (VENT_R - 0.002, VENT_Z0 + 0.002)], N, smooth=True, seam=0.0,
                    name="skirt")
    return G.merge([cone, skirt])


def _hull_spire(r, h, apex, sides=8):
    """An upright n-sided prism hull with a pointed top: walls to h, a point `apex` above them (steeper than the
    walkable 50 degrees when apex / r is over 1.1); 4 * sides - 2 triangles."""
    pos = [(math.cos(TAU * i / sides) * r, math.sin(TAU * i / sides) * r, z) for z in (0.0, h)
           for i in range(sides)]
    pos.append((0.0, 0.0, h + apex))
    tris = []
    for i in range(sides):
        j = (i + 1) % sides
        tris += [(i, j, sides + j), (i, sides + j, sides + i), (sides + i, sides + j, 2 * sides)]
    tris += [(0, i + 1, i) for i in range(1, sides - 1)]
    return pos, tris


def _lathe_at(profile, sides, z_off=0.0, name="lathe"):
    return G.lathe([(r, z + z_off) for r, z in profile], sides, name=name)


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (2.8, 2.8, 3.2)
    d.budget = 700
    d.kind = "parasol"
    d.collision_max = 32
    d.atlas = {"atlas": 256, "under": 256}
    add = d.add
    angs = [PANEL_A * i for i in range(N)]

    def rim_fn(_i, u):
        return _rim_r(u)

    def zf_top(_i, _u, t):
        return _zprof(t)

    def zf_under(_i, _u, t):
        return _zprof(t) - GAP

    # the canopy: two shells, packed in strips; the valance hangs from the top's rim (cutout, two-sided)
    top = _strip_shell("top", angs, RINGS, COLS, zf_top, rim_fn, BILLOW, True)
    chord = 2.0 * RIM_R * math.sin(PANEL_A / 2.0)
    med = d_medallions(top.charts[0].w, top.charts[0].h, chord, (1, 3))
    add(B.Part("canopy", top, paint=p_top, seed=11, weight=1.15, decals={"top0": med, "top1": med}))
    under = _strip_shell("under", angs, RINGS, COLS, zf_under, rim_fn, BILLOW, False)
    shade = d_medallions(top.charts[0].w, top.charts[0].h, chord, (1, 3), diam=0.4, shadow=True)
    add(B.Part("canopy_under", under, texture="under", paint=p_under, seed=13, weight=1.0, ao_floor=0.75,
               decals={"under0": shade, "under1": shade}))
    val = _valance(angs, rim_fn, zf_top, VALANCE, FLARE)
    add(B.Part("valance", val, "cutout", paint=p_valance, seed=15, weight=1.8))

    # the vent tier and the finial: a fat gold ball (0.17 across, sunk 0.06 into the vent's apex), its top at 3.2
    # (a nub on it was under 0.06 across)
    add(B.Part("vent", _vent(), paint=p_vent, seed=17, weight=0.9))
    ball_r = 0.085
    ball = G.sphere(ball_r, 8, 4, z0=TOP_Z - 2 * ball_r)
    add(B.Part("finial", ball, paint=p_gold, seed=19, weight=1.2))

    # under the canopy: eight walnut ribs (brass tips past the rim), the crown, the runner and the struts
    ribs = []
    feet = []
    for a in angs:
        side = (-math.sin(a), math.cos(a), 0.0)
        pts = []
        for t in (0.08,) + RINGS[1:-1]:
            rr = RIM_R * t
            pts.append((math.cos(a) * rr, math.sin(a) * rr, _mesh_z(t) - GAP - 0.002))
        last = pts[-1]
        r_last = RIM_R * RINGS[-2]
        z_rim = _mesh_z(1.0) - GAP - 0.002
        k = (TIP_R - r_last) / (RIM_R - r_last)
        pts.append((math.cos(a) * TIP_R, math.sin(a) * TIP_R, last[2] + (z_rim - last[2]) * k))
        ribs.append(_rib(pts, side, RIB_W, RIB_D))
        ts = STRUT_T
        rr = RIM_R * ts
        zs = _mesh_z(ts) - GAP - RIB_D
        feet.append((math.cos(a) * rr, math.sin(a) * rr, zs))
    add(B.Part("ribs", G.merge(ribs), texture="under", paint=p_rib, seed=21, weight=0.8))
    crown = _lathe_at([(POLE_R + 0.008, CROWN_Z - 0.02), (0.115, CROWN_Z + 0.10)], 8)   # meets the underside
    runner = _lathe_at([(POLE_R + 0.008, RUN_Z - 0.07), (POLE_R + 0.024, RUN_Z), (POLE_R + 0.008, RUN_Z + 0.07)], 8)
    add(B.Part("crown", crown, texture="under", paint=p_brass, seed=23, weight=0.8))
    add(B.Part("runner", runner, texture="under", paint=p_brass, seed=25, weight=0.8))
    struts = []
    for a, foot in zip(angs, feet):
        root = (math.cos(a) * (POLE_R + 0.01), math.sin(a) * (POLE_R + 0.01), RUN_Z + 0.03)
        struts.append(_bar(root, foot, STRUT_W, STRUT_H))
    add(B.Part("struts", G.merge(struts), texture="under", paint=p_brass, seed=27, weight=0.6))

    # the pole and the weighted base
    pole = G.cylinder(POLE_R, CROWN_Z - (BASE_H - 0.02), 10, False, z0=BASE_H - 0.02)
    add(B.Part("pole", pole, paint=p_pole, seed=31, weight=0.5))
    base = G.lathe([(BASE_R, 0.0), (BASE_R, 0.035), (BASE_R - 0.05, 0.068), (0.08, BASE_H - 0.012),
                    (POLE_R + 0.002, BASE_H)], 8, seam=math.pi / 8, name="base")     # closed round the pole
    add(B.Part("base", base, paint=p_base, seed=33, weight=0.7))

    # collision: the pole only (section 5.2.6), with a pointed top a player cannot stand on
    d.collision = _hull_spire(0.08, 2.6, 0.15)
    d.particles = []
    return d
