"""19317 ParasolOrg, the Grinding Tusk Canopy (Orgrimmar table parasol), CAFE.SPEC.md section 5.8.1.

A red hide canopy on a lashed timber tripod, shaped like the roof of an Orgrimmar hut so it reads as "a Horde
sunshade" at a glance from the front three-quarter view and from a stool under it: six irregular panels of red
hide in two tones, stretched over timber ribs into a straight tent cone and sagging between them, a rim of hanging
hide strips with bone beads, a big ivory tusk curling up and out at the end of every rib, and the hide gathered at
the apex under a rope band with a dark iron spike and three bone tips. Three crooked timber poles stand as a real
tripod round the table (their feet 1.4 apart), leaning in past the table's edge to meet under the apex, lashed
with rope where they cross. From a stool under it the hide glows a warm light red with the light
through it, crossed by the timber ribs and their pale laced seams, and the tusk crest painted on the darker panels
shows through as a dark silhouette; from a third-person camera above, those panels carry the crest in bone.
Ø 2.8 x 3.3 yd; nothing of the canopy hangs below 2.9, so a tauren (about 2.8) walks under it.

What makes a player name it at 4-15 yd, and how big each cue is (about 95 px per yard at 10 yd):
- the red hide cone: 2.5 across the hide (2.8 to the tusk tips), panels about 1.25 wide at the rim, a straight
  cone from the apex (3.27) to the rib ends (2.98-3.0), each panel sagging 0.04-0.055 between its ribs, so the
  cone rises 0.27-0.33 over the hide's edge;
- the hanging strips: hide strips 0.06 wide with gaps between them, 0.09 long at the rib ends (their bottoms held
  at 2.905 where the panels sag), a bone bead at the end of every third one;
- the tusks: six ivory tusks about 0.5 long, 0.14 thick at the root, curling up and out to the 2.8 extent at
  3.28-3.3. Their rope-wrapped roots lie along the rib ends and ride over the hide's corners;
- the tripod: three timber poles 0.13 thick, feet 0.8 from the centre (1.39 apart), leaning in to meet under
  the apex; rope bands about 0.35 across where they cross (2.85) and at the hub (3.06);
- Orgrimmar: red hide in B5402F and 9C2A1F with cross-laced seams (strokes 0.05 wide, an X every 0.2), dark
  hammered iron, tusks and bone, rough timber 0.07 wide in the ribs, rope, the tusk crest (0.58 across) on the
  three darker panels.

Deviations from the section 5.8.1 design, for the table and its four stools (section 3.12.3: the parasol stands
through the table centre, stools at 1.1 yd on the four sides) and the size (Ø 2.8 x 3.3, rim >= 2.9):
- the tripod's feet stand at 45, 165 and 285 degrees, between the stools, and the poles bow out a little (0.06
  at mid-height) so they pass 0.05 outside a 1.2 table's edge at its height (0.75);
- the cone rises 0.27-0.33 (not 0.4): the rim limit and the 3.3 height leave no more; the straight cone (not a
  steep peak), the panel sag, the strips and the up-curled tusks give it its depth from the side;
- the "sag between the poles" is between the six ribs (the hide hangs from them), the rib ends at varied
  radii and heights; the ribs at 345, 105, 165 and 285 degrees carry the tusks that set the 2.8 extents;
- added: the hanging strips with bone beads (cutout), the tusk crest on the darker panels and its silhouette
  through the hide below (a decal on the underside's strips), the iron spike crown;
- collision: a slanted three-sided prism round the lower 2 yd of each pole (section 5.2.6: poles only, <= 32
  triangles; 24);
- the underside is painted as a warm light hide lit through (sandy orange mid-panel, red-brown at the ribs and
  the rim) with pale laced seams along the ribs, and its normals lean up toward the sky: a downward face gets
  only the ambient light in game, which turned the underside into a dark disc from a chair; panel charts are
  packed in strips with every other panel upside down, as in ParasolSW.
"""

import math

from .. import build as B
from .. import emblem as E
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "ParasolOrg"
DISPLAY = 19317

TAU = 2.0 * math.pi
RED = T.hexc("B5402F")
RED_DK = T.hexc("9C2A1F")
ROPE = T.hexc("B8955A")

# the six ribs: angle (degrees), hide corner radius, corner height (alternating, the hide is hand-made); every
# rib carries a full tusk, and those at 345/105/165/285 set the 2.8 extents (the diagonal ribs are shorter)
RIBS = ((345.0, 1.29, 2.99), (47.0, 1.21, 2.98), (105.0, 1.29, 3.0), (165.0, 1.29, 2.98), (222.0, 1.23, 2.99),
        (285.0, 1.29, 2.98))
SAGS = (0.05, 0.04, 0.055, 0.045, 0.05, 0.04)    # each panel's sag at the hem, between its two ribs
PINCH = 0.025                                     # the hem pulls in between the rib ends
APEX_Z = 3.27                                     # the hide's apex, under the gather
PEAK = 1.0                                        # the hide's profile exponent: 1, a straight cone
RINGS = (0.0, 0.4, 0.75, 1.0)
COLS = 3
GAP = 0.014                                       # underside shell under the top
WOB = 0.009                                       # the hide's hand-made unevenness (the same for every layer)
HEM, HEM_FLARE = 0.09, 0.03                       # the hanging strips: depth, flare at their bottom
HEM_MIN = 2.905                                   # nothing hangs lower (rim >= 2.9, section 5.8.1)
RIB_W, RIB_D = 0.035, 0.05                        # rib half width (0.07 wide) and depth under the hide
TUSK_R = 1.449                                    # tusk tip radius (the four axis ribs set the 2.8 extents)
TUSK_ROOT = 0.25                                  # tusk roots this far in from the rib end, along the rib
POLE_R = 0.065
POLES = (45.0, 165.0, 285.0)                      # the tripod feet's angles (degrees), between the stools
# a pole's path (radius from the axis, height): a straight lean from the foot to the apex, bowed out by up to
# 0.06 (0.8 (1 - z / 3.1) + 0.06 sin(pi z / 3.1)), so it passes 0.05 outside a 1.2 table's edge
POLE_PATH = ((0.8, 0.0), (0.669, 0.65), (0.51, 1.35), (0.323, 2.05), (0.127, 2.7), (0.05, 3.1))
LASH_Z = (2.85, 3.06)                             # rope bands where the poles cross, and at the hub
GATHER_Z1 = 3.28                                  # the hide gathered round the apex under a rope band (top)
SPIKE_Z0 = 3.23                                   # the iron spike crown, from inside the gather to the top
TOP_Z = 3.31


def _rib_angle(i):
    return math.radians(RIBS[i % 6][0])


def _span(i):
    """(a0, a1) of panel i: from rib i to rib i + 1 (increasing)."""
    a0 = _rib_angle(i)
    a1 = _rib_angle(i + 1)
    while a1 <= a0:
        a1 += TAU
    return a0, a1


def _rim_r(i, u):
    """The hem's radius in panel i at u: the straight line between the two rib ends, pulled in a little."""
    a0, a1 = _span(i)
    r0, r1 = RIBS[i % 6][1], RIBS[(i + 1) % 6][1]
    a = a0 + (a1 - a0) * u
    line = r0 * r1 * math.sin(a1 - a0) / (r0 * math.sin(a - a0) + r1 * math.sin(a1 - a))
    return line * (1.0 - PINCH * math.sin(math.pi * u))


def _wob(x, y):
    """The hide's unevenness: a height offset by position, the same for both shells, the hem and the ribs."""
    return (T.noise(x * 2.2 + 3.0, y * 2.2, 5) - 0.5) * 2.0 * WOB


def _zf(i, u, t):
    """The hide's height in panel i at (u, t): from the apex to the corners (each rib its own height), sagging
    between the ribs, most at the hem."""
    z0, z1 = RIBS[i % 6][2], RIBS[(i + 1) % 6][2]
    zc = z0 + (z1 - z0) * u
    return APEX_Z + (zc - APEX_Z) * t ** PEAK - SAGS[i % 6] * math.sin(math.pi * u) * t ** 1.6


def _panel(x, y):
    """(panel index, u) of a point from its angle round the axis."""
    a = math.atan2(y, x)
    for i in range(6):
        a0, a1 = _span(i)
        q = (a - a0) % TAU
        if q < a1 - a0:
            return i, q / (a1 - a0)
    return 0, 0.0


def _hide_color(i):
    return RED if i % 2 == 0 else RED_DK


# ----------------------------------------------------------------------------------------------- paints

def p_top(ctx, seed, p):
    """Red hide in two tones: mottled, darker blotches, scuffs; cross-laced seams along the ribs; a dark burnt
    hem."""
    x, y, z = ctx.pos
    i, u = _panel(x, y)
    rr = math.hypot(x, y)
    base = _hide_color(i)
    v = T.fbm(x * 2.2 + i * 1.7, y * 2.2, seed, 3)
    spots = T.smoothstep(0.6, 0.72, T.fbm(x * 3.5 + 3.0, y * 3.5, seed + 1, 2))
    c = T.mix(T.scale(base, 0.86), T.scale(base, 1.14), v)
    c = T.mix(c, T.scale(base, 0.62), spots * 0.45)
    sc = T.smoothstep(0.72, 0.86, T.noise(x * 1.6, y * 5.0, seed + 2))
    c = T.mix(c, T.mix(base, T.hexc("E8B890"), 0.45), sc * 0.3)
    a0, a1 = _span(i)
    d_rib = min(u, 1.0 - u) * (a1 - a0) * rr
    if d_rib < 0.05 and rr > 0.2:
        c = T.mix(c, T.scale(base, 0.55), T.smoothstep(0.05, 0.012, d_rib) * 0.6)
        # lacing: X stitches of pale thong across the seam, 0.2 apart, the strokes 0.05 wide (about 2.7 texels;
        # 0.03 strokes blurred into a pale band); k is measured across the seam, the strokes cross it at 27 deg
        q = (rr % 0.2) / 0.2 - 0.5
        k = min(abs(d_rib - abs(q) * 0.1), abs(d_rib - (0.5 - abs(q)) * 0.1))
        if d_rib < 0.05 and k < 0.028:
            c = T.mix(T.hexc("E2C89A"), T.hexc("8A6A44"), T.clamp01(k / 0.028))
    d_rim = _rim_r(i, u) - rr
    if d_rim < 0.09:
        c = T.mix(c, T.scale(base, 0.45), T.smoothstep(0.09, 0.0, d_rim) * 0.6)
    if ctx.curv > 0:
        c = T.mix(c, T.mix(base, T.hexc("FFD0B0"), 0.4), T.clamp01(ctx.curv) * 0.3)
    return c


def p_under(ctx, seed, p):
    """The hide seen from the stools, lit through: a warm sandy orange mid-panel (F4A26A / E89058 on the two
    tones) down to red-brown (B4583A / A04A30) at the ribs and the rim, with paler thin patches and soft veins,
    pale laced seams along every rib (an X every 0.2), and a darker ring round the hub."""
    x, y, z = ctx.pos
    i, u = _panel(x, y)
    rr = math.hypot(x, y)
    a0, a1 = _span(i)
    lit = T.hexc("F4A26A") if i % 2 == 0 else T.hexc("E89058")
    dark = T.hexc("B4583A") if i % 2 == 0 else T.hexc("A04A30")
    glow = math.sin(math.pi * u) ** 0.7 * T.smoothstep(0.1, 0.55, rr)
    c = T.mix(dark, lit, 0.4 + 0.6 * glow)
    c = T.scale(c, 0.92 + 0.14 * T.fbm(x * 2.5, y * 2.5 + 7.0, seed, 3))
    # thinner and thicker hide: pale flesh-side patches and soft veins show against the light
    pale = T.smoothstep(0.62, 0.75, T.fbm(x * 3.0 + 9.0, y * 3.0, seed + 1, 2))
    c = T.mix(c, T.hexc("FFD0A0"), pale * 0.35 * glow)
    vein = abs(T.noise(x * 3.0 + i, y * 3.0, seed + 3) - 0.5)
    c = T.mix(c, T.hexc("8A3A20"), T.smoothstep(0.03, 0.0, vein) * 0.3)
    d_rib = min(u, 1.0 - u) * (a1 - a0) * rr
    if _rim_r(i, u) - rr < 0.08:
        c = T.mix(c, dark, 0.6)
    if d_rib < 0.07 and rr > 0.2:
        c = T.mix(c, T.hexc("7A3020"), T.smoothstep(0.07, 0.02, d_rib) * 0.4)
        # the seam's lacing, as on the top: pale thong crossing it every 0.2
        q = (rr % 0.2) / 0.2 - 0.5
        k = min(abs(d_rib - abs(q) * 0.1), abs(d_rib - (0.5 - abs(q)) * 0.1))
        if d_rib < 0.05 and k < 0.026:
            c = T.mix(T.hexc("F2DCB0"), T.hexc("9A7A50"), T.clamp01(k / 0.026))
    return T.mix(c, T.hexc("6A3018"), T.smoothstep(0.32, 0.1, rr) * 0.6)


def p_hem(ctx, seed, p):
    """The hanging strips (cutout): red hide cut into strips 0.06 wide with 0.03 gaps, under a dark fold, each
    ending in a ragged point, a darker edge down both sides, and a fat bone bead (0.07) on every third one.
    Painted from the texel's height under the hem's top (t) and the hem's real depth there (D: 0.09 at the rib
    ends, less where its bottom is held at HEM_MIN), so the strips keep their size where the hem is shortened."""
    s = ctx.s
    i, u = _panel(ctx.pos[0], ctx.pos[1])
    ztop, zb = _hem_edge(i, u)
    D = ztop - zb
    t = ztop - ctx.pos[2]
    base = _hide_color(i)
    c = T.mix(T.scale(base, 0.85), T.scale(base, 1.12), T.fbm(s * 4.0, t * 4.0 + i, seed, 2))
    if t < 0.018:
        c = T.scale(base, 0.5)                      # the fold over the strips
        return (c[0], c[1], c[2], 1.0)
    pitch = 0.09
    k = int(math.floor((s + 0.02 * i) / pitch))
    q = (s + 0.02 * i) - (k + 0.5) * pitch          # across the strip, 0 at its middle
    end = D * (0.82 + 0.18 * T.noise(k * 1.7 + i, 0.5, seed + 1))
    if k % 3 == 0:
        bz = max(0.04, end - 0.03)
        db = math.hypot(q, t - bz)
        if db < 0.035:
            cc = T.mix(T.hexc("FFF4DC"), T.hexc("9A8A64"), T.clamp01(0.5 + (t - bz) / 0.035 * 0.5 + q / 0.035 * 0.3))
            return (cc[0], cc[1], cc[2], 1.0)
    half = 0.03 * T.clamp01((end - t) / 0.03 + 0.15)    # the strip narrows to a point at its end
    if abs(q) > half or t > end:
        return (c[0], c[1], c[2], 0.0)
    c = T.mix(c, T.scale(base, 0.45), T.smoothstep(half - 0.012, half, abs(q)) * 0.7)
    return (c[0], c[1], c[2], 1.0)


def p_timber(ctx, seed, p):
    """Rough dark timber with bark streaks along the length and a lit top."""
    c = T.g_wood(ctx, seed, {"kind": "timber", "along": "t"})
    c = T.mix(c, T.hexc("3A2414"), T.smoothstep(0.55, 0.8, T.noise(ctx.s * 6.0, ctx.t * 1.2, seed + 3)) * 0.5)
    return T.mix(c, T.hexc("B48858"), T.clamp01(ctx.n[2]) * 0.2)


def p_rib(ctx, seed, p):
    """Timber ribs, rope-wrapped where the tusk is lashed on at the rib end."""
    rr = math.hypot(ctx.pos[0], ctx.pos[1])
    i, u = _panel(ctx.pos[0], ctx.pos[1])
    if rr > RIBS[(i + (1 if u > 0.5 else 0)) % 6][1] - 0.13:      # the nearest rib's end
        return T.g_rope(ctx, seed + 2, {"color": ROPE, "pitch": 0.08, "along": "t"})
    return p_timber(ctx, seed, p)


def p_tusk(ctx, seed, p):
    """Ivory tusks: the root, lashed along the rib end over the hide's corner, is wound in rope up to where the
    tusk leaves the rib end; past it, ivory with age cracks."""
    i, u = _panel(ctx.pos[0], ctx.pos[1])
    r_end = RIBS[(i + (1 if u > 0.5 else 0)) % 6][1]                 # the tusk's rib end
    if math.hypot(ctx.pos[0], ctx.pos[1]) - r_end < -0.02:
        return T.g_rope(ctx, seed + 1, {"color": ROPE, "pitch": 0.07, "along": "t"})
    return T.g_bone(ctx, seed, {"kind": "ivory", "root": 0, "cracks": 2})


def p_bone(ctx, seed, p):
    return T.g_bone(ctx, seed, {"kind": "bone", "cracks": 1})


def p_rope(ctx, seed, p):
    return T.g_rope(ctx, seed, {"color": ROPE, "pitch": 0.09, "along": "s"})


def p_pole(ctx, seed, p):
    c = p_timber(ctx, seed, p)
    z = ctx.pos[2]
    return T.mix(c, T.scale(c, 0.55), T.smoothstep(0.25, 0.0, z) * 0.6)


def p_gather(ctx, seed, p):
    """The hide gathered round the apex: dark pleats at the bottom, bound with a rope band at the top."""
    z = ctx.pos[2]
    if z > GATHER_Z1 - 0.04:
        return T.g_rope(ctx, seed + 1, {"color": ROPE, "pitch": 0.07, "along": "s"})
    c = T.g_hide(ctx, seed, {"color": RED_DK})
    a = math.atan2(ctx.pos[1], ctx.pos[0])
    return T.mix(c, T.scale(RED_DK, 0.4), T.smoothstep(0.5, 1.0, math.sin(a * 7.0)) * 0.5)


def p_spike(ctx, seed, p):
    """The spike crown: dark hammered iron, sooty at the foot, a worn bright point."""
    c = T.g_hammered_iron(ctx, seed, {"dent": 0.03})
    k = T.clamp01((ctx.pos[2] - SPIKE_Z0) / (TOP_Z - SPIKE_Z0))
    return T.mix(T.scale(c, 0.7), T.mix(c, T.hexc("B8B0A0"), 0.35), k ** 2)


# ---------------------------------------------------------------------------------------------- decals

def d_crests(chart_w, chart_h, chord, slots, t_c=0.6, diam=0.58, shadow=False):
    """The tusk crest painted in bone on the darker panels of one canopy strip chart: centred 0.6 of the way
    down the panel, 0.58 across; panels in odd slots lie upside down in the strip, so theirs is flipped. With
    shadow, the same crest as the stools see it through the hide: a soft dark silhouette on the underside's
    strip (the same layout; the crest is symmetric, so seen from below it is not mirrored)."""
    def draw(w, h):
        img = T.Img(w, h, (0.0, 0.0, 0.0, 0.0))
        kx, ky = w / chart_w, h / chart_h
        size = int(diam * min(kx, ky))
        if size < 10:
            return img
        if shadow:
            m = E.silhouette("tusk_crest", size, size)
            rel = T.Img(size, size, (0.23, 0.06, 0.03, 0.0))
            rel.a = [a * 0.6 for a in m.a]
        else:
            rel = E.render_relief("tusk_crest", size, size, P2.BONE_RELIEF)
        for slot in slots:
            cx = (slot * chord / 2.0 + chord / 2.0) * kx
            flip = slot % 2 == 1
            cy = (1.0 - t_c if flip else t_c) * chart_h * ky
            ox, oy = int(round(cx - size / 2.0)), int(round(cy - size / 2.0))
            for y in range(size):
                for x in range(size):
                    a = rel.a[y * size + x]
                    if a <= 0.0:
                        continue
                    X, Y = ox + x, oy + (size - 1 - y if flip else y)
                    if 0 <= X < w and 0 <= Y < h:
                        img.blend(X, Y, (rel.r[y * size + x], rel.g[y * size + x], rel.b[y * size + x]), a)
                        img.a[Y * w + X] = max(img.a[Y * w + X], a)
        return img
    return draw


# -------------------------------------------------------------------------------------------- geometry

def _strip_shell(name, rings, cols, up, per_strip=3, z_off=0.0):
    """A canopy shell of the six panels as one mesh, its panels packed in strips of `per_strip` with every other
    panel upside down (two triangular panels share a parallelogram of texture). Every panel is mapped to the
    same slot size (the largest chord and slant), so the irregular ones stretch a little. The paints use the
    texel's position (_panel), not s/t."""
    n = 6
    chords, slants = [], []
    for i in range(n):
        a0, a1 = _span(i)
        r0, r1 = RIBS[i][1], RIBS[(i + 1) % n][1]
        chords.append(math.hypot(math.cos(a1) * r1 - math.cos(a0) * r0, math.sin(a1) * r1 - math.sin(a0) * r0))
        slants.append(math.hypot(_rim_r(i, 0.5), APEX_Z - _zf(i, 0.5, 1.0)))
    c, hgt = max(chords), max(slants)
    m = G.Mesh()
    nstrips = (n + per_strip - 1) // per_strip
    charts = [m.chart((per_strip + 1) * c / 2.0, hgt, "%s%d" % (name, q)) for q in range(nstrips)]
    for i in range(n):
        a0, a1 = _span(i)
        slot = i % per_strip
        ch = charts[i // per_strip]
        grid = {}
        for k, t in enumerate(rings):
            for j in range(cols + 1):
                u = j / float(cols)
                a = a0 + (a1 - a0) * u
                rr = _rim_r(i, u) * t
                x, y = math.cos(a) * rr, math.sin(a) * rr
                z = _zf(i, u, t) + _wob(x, y) + z_off
                s = slot * c / 2.0 + c / 2.0 + (u - 0.5) * c * t
                tt = hgt * t if slot % 2 == 0 else hgt * (1.0 - t)
                grid[(k, j)] = m.vert((x, y, z), (0.0, 0.0, 1.0 if up else -1.0), ch, s, tt)
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
    return G.recompute_normals(m, 35.0), c


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
    """An inverted-V rib hanging under the hide along `path` (points on the underside): two faces down to a keel
    `d` below, `w` either side, the outer end capped (its own chart space past the length)."""
    m = G.Mesh()
    total = sum(G.length(G.sub(path[k + 1], path[k])) for k in range(len(path) - 1))
    hw = math.hypot(w, d)
    ch = m.chart(2.0 * hw, total + hw, name)
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
    l1, k1, r1, _kp = rows[-1]
    tang = G.norm(G.sub(path[-1], path[-2]))
    cap = [m.vert(m.p[v], tang, ch, s, total + (hw if v == k1 else 0.0)) for v, s in ((l1, 0.0), (k1, hw),
                                                                                      (r1, 2 * hw))]
    _tri_out(m, cap[0], cap[1], cap[2], G.sub(path[-1], tang))
    return G.recompute_normals(m, 50.0)


def _hem_tops(i):
    """The hem's top edge in panel i: (angle, radius, height) at each of its COLS + 1 columns."""
    a0, a1 = _span(i)
    tops = []
    for j in range(COLS + 1):
        u = j / float(COLS)
        a = a0 + (a1 - a0) * u
        rr = _rim_r(i, u) + 0.004
        x, y = math.cos(a) * rr, math.sin(a) * rr
        tops.append((a, rr, _zf(i, u, 1.0) + _wob(x, y) + 0.004))
    return tops


_HEM_TOPS = {}                                    # panel -> _hem_tops(panel), for the hem's paint


def _hem_edge(i, u):
    """(top, bottom) height of the hem in panel i at u, linear between the columns as the mesh is."""
    tops = _HEM_TOPS.get(i)
    if tops is None:
        tops = _HEM_TOPS[i] = _hem_tops(i)
    q = min(COLS - 1e-9, max(0.0, u * COLS))
    j = int(q)
    f = q - j
    z0, z1 = tops[j][2], tops[j + 1][2]
    b0, b1 = max(HEM_MIN, z0 - HEM), max(HEM_MIN, z1 - HEM)
    return z0 + (z1 - z0) * f, b0 + (b1 - b0) * f


def _hem():
    """The hanging hem: per panel a band of hide hanging from the top shell's hem (following its sag), flaring
    out a little toward its ragged bottom; one chart per panel, s along the hem (left to right seen from
    outside), t down the slant (so the chart has the hem's real size). Its bottom stays at or above HEM_MIN
    (tauren walk under it)."""
    m = G.Mesh()
    for i in range(6):
        tops = _hem_tops(i)
        length = 0.0
        for j in range(COLS):
            (a, r, _z), (b, r2, _z2) = tops[j], tops[j + 1]
            length += math.hypot(math.cos(b) * r2 - math.cos(a) * r, math.sin(b) * r2 - math.sin(a) * r)
        ch = m.chart(length, math.hypot(HEM, HEM_FLARE), "hem%d" % i)
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
            zb = max(HEM_MIN, z - HEM)
            rb = rr + HEM_FLARE
            bot = m.vert((math.cos(a) * rb, math.sin(a) * rb, zb), out_n, ch, acc, math.hypot(z - zb, HEM_FLARE))
            cols.append((top, bot))
        for j in range(COLS):
            (tl, bl), (tr, br) = cols[j], cols[j + 1]
            m.tri(tl, bl, br)
            m.tri(tl, br, tr)
    return G.recompute_normals(m, 60.0)


def _pole_path(deg):
    """One timber pole along POLE_PATH: from its foot on the floor, bowed out over the table's edge, leaning in
    and turning a little round the axis to its top between the hide's two shells under the gather."""
    pts = []
    for k, (r, z) in enumerate(POLE_PATH):
        a = math.radians(deg + 4.0 * k)
        pts.append((math.cos(a) * r, math.sin(a) * r, z))
    return pts


def _hull_pole(deg, r=0.1, z1=2.0):
    """A slanted three-sided prism hull round a pole from the floor to z1, following its lean: 8 triangles."""
    pts = _pole_path(deg)
    top = None
    for p0, p1 in zip(pts, pts[1:]):
        if p0[2] <= z1 <= p1[2]:
            f = (z1 - p0[2]) / (p1[2] - p0[2])
            top = tuple(p0[k] + (p1[k] - p0[k]) * f for k in range(3))
    pos = []
    for cx, cy, z in (pts[0], top):
        for i in range(3):
            a = TAU * i / 3 + math.radians(deg)
            pos.append((cx + math.cos(a) * r, cy + math.sin(a) * r, z))
    tris = []
    for i in range(3):
        j = (i + 1) % 3
        tris += [(i, j, 3 + j), (i, 3 + j, 3 + i)]
    tris += [(0, 2, 1), (3, 4, 5)]
    return pos, tris


def _pole_r_at(z):
    """A pole centre's distance from the axis at height z (POLE_PATH, linear between its points)."""
    for (r0, z0), (r1, z1) in zip(POLE_PATH, POLE_PATH[1:]):
        if z0 <= z <= z1:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return POLE_PATH[-1][0]


def _band(z, r_in, r_out, h, sides=6):
    """A rope band round the poles: a bulging ring of two segments."""
    return G.lathe([(r_in, z - h / 2.0), (r_out, z), (r_in, z + h / 2.0)], sides, name="band")


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (2.8, 2.8, 3.3)
    d.budget = 800
    d.kind = "parasol"
    d.collision_max = 32
    d.atlas = {"atlas": 256, "under": 256}
    add = d.add

    # the hide: two shells packed in strips, the crest on the darker panels (1, 3, 5), the ragged hem
    top, chord = _strip_shell("top", RINGS, COLS, True)
    cw, chh = top.charts[0].w, top.charts[0].h
    add(B.Part("canopy", top, paint=p_top, seed=11, weight=1.15,
               decals={"top0": d_crests(cw, chh, chord, (1,)), "top1": d_crests(cw, chh, chord, (0, 2))}))
    under, _c = _strip_shell("under", RINGS, COLS, False, z_off=-GAP)
    # its normals lean up toward the sky (the light through the hide): a face pointing down gets only the
    # ambient light, and the underside read as a dark disc from a chair
    under.n = [G.norm((n[0] * 0.5, n[1] * 0.5, 0.75)) for n in under.n]
    add(B.Part("canopy_under", under, texture="under", paint=p_under, seed=13, ao_floor=0.85,
               decals={"under0": d_crests(cw, chh, chord, (1,), shadow=True),
                       "under1": d_crests(cw, chh, chord, (0, 2), shadow=True)}))
    add(B.Part("hem", _hem(), "cutout", paint=p_hem, seed=15, weight=1.4))

    # the crown: the hide gathered round the apex under a rope band, a dark iron spike rising out of it, and
    # three bone tips splaying out of the gather over the three lighter panels (clear of the crests)
    zb = APEX_Z + (sum(r[2] for r in RIBS) / 6.0 - APEX_Z) * (0.16 / 1.27) ** PEAK - GAP * 0.5 - WOB
    gather = G.lathe([(0.16, zb), (0.08, GATHER_Z1), (0.03, GATHER_Z1 + 0.005)], 6, name="gather")
    add(B.Part("gather", gather, paint=p_gather, seed=17, weight=1.2))
    spike = G.cone(0.075, 0.0, TOP_Z - SPIKE_Z0, 6, caps=(False, False), z0=SPIKE_Z0)
    add(B.Part("spike", spike, paint=p_spike, seed=18, weight=1.2))
    tips = []
    for i in (0, 2, 4):
        a0, a1 = _span(i)
        a = (a0 + a1) / 2.0
        root = (math.cos(a) * 0.05, math.sin(a) * 0.05, SPIKE_Z0)
        tip = (math.cos(a) * 0.3, math.sin(a) * 0.3, 3.28)
        tips.append(G.horn(root, tip, (math.cos(a), math.sin(a), -0.5), 0.15, 0.05, 0.0, 2, 5, cap=False))
    add(B.Part("bone_tips", G.merge(tips), paint=p_bone, seed=19, weight=1.0))

    # under the hide: six timber ribs from the hub to the rib ends, an ivory tusk lashed to each end
    ribs, tusks = [], []
    for i, (deg, r_c, z_c) in enumerate(RIBS):
        a = math.radians(deg)
        side = (-math.sin(a), math.cos(a), 0.0)
        pts = []
        for t in (0.12, 0.4, 0.75, 1.0):
            rr = r_c * t
            x, y = math.cos(a) * rr, math.sin(a) * rr
            pts.append((x, y, _zf(i, 0.0, t) + _wob(x, y) - GAP - 0.003))
        ribs.append(_rib(pts, side, RIB_W, RIB_D))
        # every tusk full size: its root lashed along the rib end (riding over the hide's corner, up to 0.063
        # above it: sunk under it, the tusk's bottom would hang under 2.9), its tip curling up to the 2.8
        # extent at 3.28-3.3 (the diagonal ribs' tips stay inside the bounds at the same radius)
        r0 = r_c - TUSK_ROOT
        root = (math.cos(a) * r0, math.sin(a) * r0, z_c - 0.016)
        tip = (math.cos(a) * TUSK_R, math.sin(a) * TUSK_R, 3.28 + 0.02 * (i % 2))
        bend = (math.cos(a), math.sin(a), -0.6)
        tusks.append(G.horn(root, tip, bend, 0.32, 0.07, 0.0, 3, 6, cap=True))    # 6 sides: the silhouette cue
    add(B.Part("ribs", G.merge(ribs), texture="under", paint=p_rib, seed=21, weight=0.8))
    add(B.Part("tusks", G.merge(tusks), paint=p_tusk, seed=23, weight=1.3))

    # the tripod: three crooked timber poles, their feet 1.4 apart round the table, meeting under the apex,
    # lashed with rope where they cross and at the hub
    poles = []
    for k, deg in enumerate(POLES):
        pole = G.wobble(G.sweep(_pole_path(deg), POLE_R, 5, caps=(False, False)), 0.01, 31 + k)
        pole.p = [(x, y, max(0.0, z)) for x, y, z in pole.p]     # the feet stand flat on the floor
        poles.append(G.recompute_normals(pole, 50.0))
    add(B.Part("poles", G.merge(poles), paint=p_pole, seed=31, weight=0.6))
    bands = []
    for z in LASH_Z:
        rc = _pole_r_at(z)
        bands.append(_band(z, rc + POLE_R - 0.014, rc + POLE_R + 0.022, 0.09, 7))
    add(B.Part("lashings", G.merge(bands), paint=p_rope, seed=33, weight=1.0))

    # collision: a slanted three-sided prism round the lower 2 yd of each pole (section 5.2.6: poles only, <= 32)
    d.collision = G.merge_hulls(*[_hull_pole(deg) for deg in POLES])
    d.particles = []
    return d
