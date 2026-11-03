"""19308 ColdBoxSW, the Lion's Roast Cold Box (Stormwind ice-cream station), CAFE.SPEC.md section 5.8.1.

An oak ice chest turned ice-cream dipping cabinet, shaped so it reads as "the ice cream" at a glance from the
front three-quarter view: three white porcelain tubs heaped with scoops (vanilla, chocolate, berry) sit in
crushed ice under a frosted glass hood that slopes down toward the barista, a giant waffle cone with a pink scoop
and a cherry crowns the hood, and frost mist spills down the front past a fringe of icicles. Stormwind and
human-made: an oak plank chest bound in polished brass (chunky brass corner posts with gold ball finials, a
riveted top band and straps, brass strap hinges at the back, a brass hood frame and grab handle), a royal-blue
enamel plaque framed in gold with the cone between two gold lions on the front, royal-blue lion medallions in
gold rims on both ends, and a royal-blue enamel back wall inside the hood that makes the scoops pop. 1.1 (Y) x
0.7 (X) x 0.8 yd (the hood and the crest to 0.98), front (+X) toward the barista.

What makes a player name it at 4-15 yd (front three-quarter view, and the +Y end the tables see), and how big
each cue is:
- the ice cream: three scoops, each a round ball 0.17 across on a scalloped heap 0.3 across that spills over
  its tub's rim, 0.18 over the rim; cream yellow, chocolate brown and pink with berry bits, seen
  through the glass (clear in the middle of each pane, frost only round the edges) against the blue back wall;
  the porcelain tubs show 0.06 over the ice, with a royal-blue band, and a white lip 0.02 wide round each heap;
- the cone crest: a waffle cone 0.175 long (0.13 across its mouth) in a gold cup 0.054 tall, with a pink scoop
  0.16 across on a drip lip and a red cherry 0.08 across, 0.35 tall in all, on top of the hood's back rail: the
  silhouette of an ice-cream sign, from the front and from the ends;
- the chest: a low, wide oak chest 1.02 x 0.6 on brass corner posts (0.085 square, gold ball finials 0.1)
  with a glass hood (front lip at 0.4, back rail 0.06 tall at 0.645), a round-cornered brass grab handle 0.41
  wide and 0.066 thick on the lip;
- cold: icicles 0.1-0.17 long (0.064-0.072 thick) under the lip, a crisp white cap of rime on the chest's top
  band and the finials, frost round the glass panes, crushed ice round the tubs, and the frost mist sinking off
  the lip's top edge between the handle and the front posts (two emitters, small puffs);
- Stormwind: the royal-blue plaque (0.52 x 0.22) with the cone between two gold lion heads (0.13), the lion
  medallions (0.22) on the ends, polished brass everywhere, the blue back wall, the porcelain tubs.

Deviations from the section 5.8.1 design and the section 5.8 size (H 0.8 +- 2 cm):
- the hood and the crest rise to 0.98 (render_size; the collision box keeps 1.1 x 0.7 x 0.8, as counter_sw and
  kettle_stove_sw do, its top sloping down to 0.42 over the front lip with the glass): the scoops need 0.18
  over their rims under the glass and the crest needs a cone that reads as a cone;
- the frosted glass lid is a hood sloping 24 degrees toward the front (glass on the top and both ends), not a
  flat lid: from 4-15 yd at eye height a flat lid is seen almost edge-on and hides the tubs; the hood shows
  them, and its panes are frosted only round their edges;
- the chest is low (its deck at 0.29) so the scoops sit high under the hood;
- the tubs are porcelain (not plain cylinders) heaped with scoops;
- added: the cone crest, the icicles, the crushed ice round the tubs, the blue plaque with the cone and lions,
  the end medallions, the blue back wall and the grab handle; the brass corner caps are full-height corner
  posts.
"""

import math

from .. import build as B
from .. import emblem as E
from .. import geom as G
from .. import paint2d as P2
from .. import raster2d as R
from .. import tex as T
from . import _cold_box as CB

NAME = "ColdBoxSW"
DISPLAY = 19308

ENAMEL = T.hexc("2E4E8C")
# the frame's brass: espresso_sw's brass family (tex.BRASS) a shade deeper, so flat posts and rails read as the
# same polished metal as the Royal Brass Engine's frame and not as flat lemon yellow
FRAME_BRASS = {"base": T.hexc("C08A24"), "light_c": T.hexc("FFE08A"), "dark": T.hexc("4A2A06"),
               "bounce": T.hexc("A0661A")}
# a brighter gold relief than paint2d.GOLD_RELIEF for the plaque's lions, and a brighter one still for the end
# medallions, which sit in the shade of the ends (from the tables a darker lion read as a dark disc)
LION_GOLD = {"base": T.hexc("C8901E"), "raised": T.hexc("F0C040"), "top": T.hexc("FFF0A8"),
             "dark": T.hexc("6A4010"), "outline": T.hexc("2E1806")}
LION_GOLD_END = dict(LION_GOLD, raised=T.hexc("F8D060"), top=T.hexc("FFF8C8"))

FOOT_Z = 0.045                  # the chest's underside: it stands on its corner posts
DECK_Z = 0.29                   # the chest's top, crushed ice round the tubs
BODY_W, BODY_D = 1.02, 0.60     # the chest box (Y, X)
POST = 0.085                    # brass corner posts, square
POST_X, POST_Y = 0.3075, 0.5075  # their centres (extents X +-0.35, Y +-0.55)
HOOD_W = 0.95                   # the glass hood between its end panes (Y)
LIP_X0, LIP_X1 = 0.23, 0.30     # the brass front lip (X), flush with the chest front
XF, XB = 0.26, -0.27            # the hood's glass line: front and back (X)
ZF, ZB = 0.37, 0.61             # its height at the front lip and at the back rail
SLOPE = math.atan2(ZB - ZF, XF - XB)
TUB_X, TUB_R = -0.11, 0.145
TUB_Z0, TUB_Z1 = DECK_Z - 0.03, DECK_Z + 0.06   # the porcelain tubs: 0.06 of each shows over the ice
TUBS = ((-0.31, "vanilla"), (0.0, "chocolate"), (0.31, "berry"))
FRONT_TOP = ZF + 0.045          # the front posts' tops (just over the lip)
RAIL_TOP = ZB + 0.035           # the back rail's top: the cone's cup stands on it
BACK_TOP = RAIL_TOP + 0.02      # the back posts' tops
CREST_X = -0.255                # the cone crest's axis (on the rail, a little forward of its middle)
CONE_TIP, CONE_L, CONE_R = RAIL_TOP - 0.012, 0.175, 0.064
SCOOP_Z = CONE_TIP + CONE_L     # the crest scoop's base (the cone's mouth)
CREST_BALL = 0.078
MEDAL_R, MEDAL_Z = 0.11, 0.17   # the lion medallions on the ends


def lid_z(x):
    """Height of the glass line at x (the hood slopes down toward the front)."""
    return ZF + (XF - x) / (XF - XB) * (ZB - ZF)


# ----------------------------------------------------------------------------------------------- paints

def p_chest(ctx, seed, p):
    """Oak planks bound in brass: a riveted top band under the rime, a bottom band, two straps on the front and
    the strap hinges at the back; the top face is crushed ice."""
    if ctx.chart == "+z":
        return CB.p_ice(ctx, seed, p)
    c = T.g_planks(ctx, seed, {"kind": "oak", "count": 4, "gap": 0.02, "ragged": 0.0, "knots": 1})
    t, s, ch = ctx.t, ctx.s, ctx.ch
    brass = brass_frame(ctx, seed + 3)
    band = None
    if t < 0.045:
        band = (0.0225, True)
    elif t > ch - 0.04:
        band = (ch - 0.02, True)
    y = ctx.pos[1]
    strap = None
    if ctx.chart == "+x" and abs(abs(y) - 0.34) < 0.03:
        strap = s + math.copysign(0.34, y) - y          # the strap's centre line in chart s
    if ctx.chart == "-x" and abs(abs(y) - 0.3) < 0.03 and t < 0.17:
        strap = s - (math.copysign(0.3, y) - y)
    if strap is not None:
        band = (strap, False)
    if band is not None:
        c = brass
        row, horiz = band
        if horiz:
            c = T.rivet_lines(ctx, c, rows=(row,), step=0.18, r=0.03)
            if abs(t - row) > 0.016:
                c = T.mix(c, T.scale(c, 0.6), 0.5)      # the band's dark edges
        else:
            c = T.rivet_lines(ctx, c, cols=(row,), step=0.15, r=0.03, phase=0.075)
    if ctx.chart == "+x":
        # the front keeps a crisp cap of rime on its top band only, so the oak planks and the brass straps
        # below it read as wood and metal at 4-8 yd (full rime there turned the corners into a grey smudge)
        k = CB.top_frost(ctx, seed, 0.02) * (1.0 if t < 0.045 else 0.5)
    else:
        k = CB.top_frost(ctx, seed)
    return CB.frost(ctx, c, k, seed + 11)


def brass_frame(ctx, seed):
    """Polished brass for flat frame parts, painted as espresso_sw paints its frame: the brass bands and streaks,
    a value ramp down each face (lit at the top, a darker recess toward the bottom), a dark groove inside a
    bright highlight along every chart edge, and patina in the recesses."""
    c = T.g_brass(ctx, seed, {"streak": True, "patina": 0.12, "palette": FRAME_BRASS})
    if ctx.ch > 0.0:
        c = T.scale(c, 1.08 - 0.3 * T.clamp01(ctx.t / max(ctx.ch, 1e-6)) * (1.0 - abs(ctx.n[2])))
    e = T.edge_dist(ctx)
    if e < 0.008:
        return T.mix(c, FRAME_BRASS["light_c"], 0.55 * (1.0 - e / 0.008))
    if e < 0.016:
        return T.mix(c, FRAME_BRASS["dark"], 0.45)
    return c


def p_brass(ctx, seed, p):
    """Polished brass, only flecked with rime where it faces straight up: the frame must read as gold brass."""
    c = brass_frame(ctx, seed)
    return CB.frost(ctx, c, T.smoothstep(0.85, 0.98, ctx.n[2]) * 0.25, seed + 5)


def p_gold(ctx, seed, p):
    return T.g_gold(ctx, seed, {"patina": 0.05})


def p_gold_snow(ctx, seed, p):
    """Gold balls on the posts with a cap of snow."""
    return CB.frost(ctx, T.g_gold(ctx, seed, {"patina": 0.05}), T.smoothstep(0.55, 0.9, ctx.n[2]), seed + 1)


def p_back_wall(ctx, seed, p):
    """Royal-blue enamel behind the scoops (inside the hood), rimed along its edges; plain oak behind."""
    if ctx.chart != "+x":
        c = T.g_planks(ctx, seed, {"kind": "oak", "count": 2, "gap": 0.02, "ragged": 0.0})
        return CB.frost(ctx, c, CB.top_frost(ctx, seed), seed + 3)
    c = T.g_enamel(ctx, seed, {"color": ENAMEL, "chips": 0, "gloss": 0.3})
    e = T.edge_dist(ctx)
    k = T.smoothstep(0.05, 0.0, e + (T.fbm(ctx.s * 9.0, ctx.t * 9.0, seed + 1, 2) - 0.5) * 0.04)
    return CB.frost(ctx, c, k, seed + 2)


def p_tub(ctx, seed, p):
    """White porcelain tubs: a bright rolled lip and a royal-blue band under it."""
    c = T.g_ceramic(ctx, seed, {"color": T.hexc("F4F0E6")})
    z = ctx.pos[2]
    if z > TUB_Z1 - 0.01:
        c = T.mix(c, T.hexc("FFFFFF"), 0.4)
    elif TUB_Z1 - 0.04 < z < TUB_Z1 - 0.015:
        c = T.mix(ENAMEL, T.scale(ENAMEL, 1.3), T.clamp01(ctx.n[2] + 0.5))
    return c


def p_scoop(ctx, seed, p):
    """The three tubs' ice cream (each painted round its own ball) and the crest's pink scoop."""
    if ctx.part == "crest_scoop":
        return CB.scoop(ctx, seed, "berry", (CREST_X, 0.0, SCOOP_Z + 0.05))
    y = ctx.pos[1]
    k = min(range(3), key=lambda i: abs(y - TUBS[i][0]))
    cy, name = TUBS[k]
    return CB.scoop(ctx, seed + 7 * k, name, (TUB_X - 0.015, cy, TUB_Z1 + CB.HEAP_BALL), chips=4)


def p_cherry(ctx, seed, p):
    c = T.mix(T.hexc("8A0E16"), T.hexc("D8222C"), T.clamp01(ctx.n[2] * 0.6 + 0.5))
    hl = T.clamp01(-ctx.n[0] * 0.3 + ctx.n[2] * 0.8 + ctx.n[1] * 0.4)
    return T.mix(c, T.hexc("FFD8D8"), T.smoothstep(0.85, 1.0, hl) * 0.8)


def p_plaque(ctx, seed, p):
    c = T.g_enamel(ctx, seed, {"color": ENAMEL, "chips": 0, "gloss": 0.4})
    if not ctx.chart.endswith("_front"):
        c = T.g_gold(ctx, seed + 1, {"patina": 0.05})
    return c


def p_medal(ctx, seed, p):
    """The end medallions: royal-blue enamel in a bright gold rim 0.015 wide (the lion is the decal); the edge
    of the disc is gold."""
    if not ctx.chart.endswith("_front"):
        return T.g_gold(ctx, seed + 1, {"patina": 0.03})
    d = math.hypot(ctx.s - ctx.cw / 2, ctx.t - ctx.ch / 2)
    c = T.g_enamel(ctx, seed, {"color": ENAMEL, "chips": 0, "gloss": 0.35})
    if d > MEDAL_R * math.cos(math.pi / 10) - 0.017:
        c = T.mix(T.hexc("E8B848"), T.hexc("FFE8A0"), T.clamp01(0.5 - (ctx.t - ctx.ch / 2) / MEDAL_R))
    return c


def p_glass(ctx, seed, p):
    """Frosted glass (section 5.2.5): a pale body of alpha 0.28 (71) that leaves the scoops readable, frost
    feathering in from the frame (a bold white rim 0.03 wide, so the closed lid reads at 15 yd), a few broad ferns
    at the corners, and sheen streaks up to alpha 0.75 (191). The top is one clear pane, its streaks running across
    the slope, a broad one and two thin ones high up where the sky would catch them: from every eye-height view the
    balls show through the glass 0.2-0.72 of the way up the slope, so nothing above 0.74 crosses a scoop. Any line
    down the slope does from the queue, even one between the tubs (as the frosted pane lines did): seen from 37-54
    degrees, a scoop shows 0.1-0.2 yd to the side of the glass straight over it. Diagonal streaks on the end
    panes."""
    x, y, z = ctx.pos
    ca = math.cos(SLOPE)
    if ctx.part == "glass_top":
        e = min((XF - x) / ca, (x - XB) / ca, HOOD_W / 2 - abs(y))
        u = (y + HOOD_W / 2) / HOOD_W
        v = (XF - x) / (XF - XB)
    else:
        e = min(z - DECK_Z, XF - x, x - XB, (lid_z(x) - z) * ca)
        u = (XF - x) / (XF - XB)
        v = (z - DECK_Z) / (ZB - DECK_Z)
    f = T.fbm(x * 18.0 + y * 7.0, y * 18.0 + z * 11.0, seed, 3)
    k = T.smoothstep(0.055, 0.0, e + (f - 0.5) * 0.05)
    fern = 1.0 - abs(T.noise(x * 10.0 + y * 3.0, y * 10.0 + z * 4.0, seed + 1) - 0.5) * 2.0
    fern = T.smoothstep(0.8, 0.96, fern) * T.smoothstep(0.12, 0.02, e)
    # a bold white frost rim inside the frame (0.03 solid, feathering out to 0.075) so the closed glass top
    # reads at 8-15 yd: the faint one left the box looking like an open tray
    k = max(k, T.smoothstep(0.075, 0.03, e + (f - 0.5) * 0.03))
    c = T.mix(T.hexc("CFE8F8"), (1.0, 1.0, 1.0), T.clamp01(k * 0.9 + fern * 0.6))
    a = 0.3 + 0.62 * T.clamp01(k + fern * 0.5)
    top = ctx.part == "glass_top"
    for c0, wd in (((0.88, 0.03), (0.8, 0.012), (0.95, 0.012)) if top else ((0.22, 0.06), (0.34, 0.03))):
        d = abs(v + (u - 0.5) * 0.04 - c0) if top else abs((u * 0.8 + v * 0.6) - c0)
        if d < wd:
            kk = T.smoothstep(wd, 0.0, d)
            c = T.mix(c, (1.0, 1.0, 1.0), kk * 0.8)
            a = max(a, 0.3 + 0.45 * kk)
    return (c[0], c[1], c[2], a)


# ---------------------------------------------------------------------------------------------- decals

def d_plaque(w, h):
    """The front plaque: a gold rule inside the royal-blue field, the ice-cream cone big in the middle between
    two gold lion heads, and a small snowflake in each corner."""
    img = T.Img(w, h, (0, 0, 0, 0))
    bw = max(1, int(min(w, h) * 0.05))
    for y in range(h):
        for x in range(w):
            e = min(x, w - 1 - x, y, h - 1 - y)
            if 2 * bw <= e < 3 * bw:
                img.set(x, y, T.hexc("F2CC66"), 1.0)
            elif 3 * bw <= e < 3 * bw + max(1, bw // 2):
                img.set(x, y, T.hexc("16284A"), 0.7)
    f = h * 0.07
    if f >= 3:
        m = 3.5 * bw + f
        for fx, fy in ((m, m), (w - m, m), (m, h - m), (w - m, h - m)):
            _snowflake(img, fx, fy, f)
    s = int(h * 0.86)
    if s >= 8:
        CB.cone_icon(img, (w - s) // 2, (h - s) // 2, s)
    ls = int(h * 0.6)               # 0.13 yd of the plaque's 0.22
    if ls >= 8:
        for fx in (0.2, 0.8):
            rel = E.render_relief("lion_head", ls, ls, LION_GOLD)
            P2.composite(img, rel, int(w * fx - ls / 2), int(h * 0.5 - ls / 2))
    return img


def _snowflake(img, cx, cy, r):
    m = R.Mask(img.w, img.h)
    for k in range(3):
        a = math.pi / 2 + k * math.pi / 3
        dx, dy = math.cos(a) * r, math.sin(a) * r
        R.stroke(m, [[(cx - dx, cy - dy), (cx + dx, cy + dy)]], max(1.2, r * 0.24))
        for sgn in (1, -1):
            px, py = cx + dx * 0.55 * sgn, cy + dy * 0.55 * sgn
            for b in (0.6, -0.6):
                bx, by = math.cos(a + b) * r * 0.35 * sgn, math.sin(a + b) * r * 0.35 * sgn
                R.stroke(m, [[(px, py), (px + bx, py + by)]], max(1.0, r * 0.18))
    P2.paint_mask(img, R.dilate(m, 1), T.hexc("16284A"), alpha=0.6)
    P2.paint_mask(img, m, T.hexc("F4FAFF"))


def side_lion(w, h):
    """A bright gold lion head filling 0.8 of an end medallion."""
    img = T.Img(w, h, (0, 0, 0, 0))
    s = int(min(w, h) * 0.8)
    if s < 8:
        return img
    rel = E.render_relief("lion_head", s, s, LION_GOLD_END)
    P2.composite(img, rel, int(w * 0.5 - s / 2), int(h * 0.5 - s / 2))
    return img


# ------------------------------------------------------------------------------------------------ parts

def _on_slope(mesh, x0, x1, y, lift=0.0):
    """A mesh built flat (centred on the origin, X along the slope) laid on the glass line between x0 and x1
    (x0 > x1) at y, lifted `lift` along the glass normal."""
    xm = (x0 + x1) / 2
    nx, nz = math.sin(SLOPE), math.cos(SLOPE)
    return G.transform(mesh, G.mat_chain(G.mat_translate(xm + nx * lift, y, lid_z(xm) + nz * lift),
                                         G.mat_rot_y(SLOPE)))


def _finial(r, sides):
    """A gold ball open at the bottom: its lowest ring sinks just under the post top, so the bottom cap would
    never be seen. The ring's corners turn 15 degrees off the post's faces to stay inside them."""
    prof = [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for a in (-30.0, 30.0)] + [(0.0, r)]
    return G.lathe(prof, sides, smooth=True, angle=89.0, seam=math.pi / 12, name="sphere")


def _mitred_sweep(path, r, sides):
    """G.sweep with each bend's ring widened by 1 / cos(half the bend), so a corner keeps the tube's thickness
    instead of pinching (a ring set square to the bisector is narrower by that factor)."""
    k = [1.0]
    for i in range(1, len(path) - 1):
        a = G.norm(G.sub(path[i], path[i - 1]))
        b = G.norm(G.sub(path[i + 1], path[i]))
        k.append(1.0 / math.cos(math.acos(max(-1.0, min(1.0, G.dot(a, b)))) / 2))
    k.append(1.0)
    arcl = [0.0]
    for i in range(1, len(path)):
        arcl.append(arcl[-1] + G.length(G.sub(path[i], path[i - 1])))
    ts = [a / arcl[-1] for a in arcl]
    return G.sweep(path, lambda t: r * k[min(range(len(ts)), key=lambda i: abs(ts[i] - t))], sides)


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (1.1, 0.7, 0.8)
    d.render_size = (1.1, 0.7, 0.98)
    d.budget = 1200
    d.kind = "station"
    d.atlas = {"atlas": 256}
    add = d.add

    # the chest: oak planks bound in brass (a light wobble: hand-made), crushed ice on its top. No bevel: its
    # upright edges stand inside the corner posts and its top front edge under the lip
    body = G.box(BODY_W, BODY_D, DECK_Z - FOOT_Z, faces="+x -x +y -y +z", z0=FOOT_Z)
    body = G.wobble(body, 0.005, 11)
    for ch in body.charts:
        ch.weight = {"-x": 0.6, "+z": 0.7, "+x": 1.7, "+y": 1.4, "-y": 1.4}.get(ch.name, 1.0)    # crisp planks
    add(B.Part("chest", body, paint=p_chest, seed=11))

    # chunky brass corner posts: the front pair ends just over the lip, the back pair over the back rail
    posts, finials = [], []
    for sx in (1, -1):
        top = FRONT_TOP if sx > 0 else BACK_TOP
        for sy in (1, -1):
            posts.append(G.translate(G.box(POST, POST, top, faces="+x -x +y -y +z"), sx * POST_X, sy * POST_Y,
                                     0.0))
            finials.append(G.translate(_finial(0.05, 6), sx * POST_X, sy * POST_Y, top + 0.021))
    add(B.Part("posts", G.merge(posts), paint=p_brass, seed=21, weight=0.7))
    add(B.Part("finials", G.merge(finials), paint=p_gold_snow, seed=23, weight=0.6, ao_floor=0.6))

    # the front plaque: royal-blue enamel in a gold edge, with the cone between two gold lions
    pw, ph = 0.52, 0.22
    r0 = 0.035
    outline = []
    for cx, cy, a0 in ((pw / 2 - r0, ph / 2 - r0, 0.0), (-pw / 2 + r0, ph / 2 - r0, 90.0),
                       (-pw / 2 + r0, -ph / 2 + r0, 180.0), (pw / 2 - r0, -ph / 2 + r0, 270.0)):
        for k in range(3):
            a = math.radians(a0 + 90.0 * k / 2)
            outline.append((cx + math.cos(a) * r0, cy + math.sin(a) * r0))
    plaque = G.extrude(outline, 0.022, 0.006, back=False)
    plaque = G.transform(plaque, G.mat_chain(G.mat_translate(BODY_D / 2 - 0.002, 0.0, FOOT_Z + 0.015 + ph / 2),
                                             G.MAT_EXTRUDE_FRONT))
    for ch in plaque.charts:
        ch.weight = 2.6 if ch.name.endswith("_front") else 0.4
    add(B.Part("plaque", plaque, paint=p_plaque, seed=31, decals={"extrude_front": d_plaque}))

    # the lion medallions on both ends (the +Y end faces the tables in the café layout)
    medals = []
    for sy in (1, -1):
        m = G.extrude(G.circle_polygon(MEDAL_R, 10, math.pi / 10), 0.02, 0.0, back=False)
        medals.append(G.transform(m, G.mat_chain(G.mat_translate(0.0, sy * (BODY_W / 2 - 0.006), MEDAL_Z),
                                                 G.mat_extrude_facing((0.0, float(sy), 0.0)))))
    medals = G.merge(medals)
    for ch in medals.charts:
        ch.weight = 3.0 if ch.name.endswith("_front") else 0.4
    add(B.Part("medallions", medals, paint=p_medal, seed=33, decals={"extrude_front": side_lion}, ao_floor=0.5))

    # the glass hood: a sloping top and the two end panes, single shells, frosted round their edges
    wy = HOOD_W / 2
    top = CB.poly([(XF, -wy, lid_z(XF)), (XF, wy, lid_z(XF)), (XB, wy, lid_z(XB)), (XB, -wy, lid_z(XB))],
                  (math.sin(SLOPE), 0.0, math.cos(SLOPE)), "glass_top")
    top.set_weight(0.7)
    add(B.Part("glass_top", top, "glass1", paint=p_glass, seed=41))
    ends = G.merge([CB.poly([(XB, sy * wy, DECK_Z), (XF, sy * wy, DECK_Z), (XF, sy * wy, ZF), (XB, sy * wy, ZB)],
                            (0.0, float(sy), 0.0), "glass_end") for sy in (1, -1)])
    ends.set_weight(0.6)
    add(B.Part("glass_ends", ends, "glass1", paint=p_glass, seed=43))

    # the hood's brass frame: the front lip, the back rail and the chunky sloping end rails (no muntins: the
    # panes are split by painted frost lines, so nothing cages the scoops)
    lw = 2 * POST_Y - POST + 0.004
    lip = G.translate(G.box(lw, LIP_X1 - LIP_X0, ZF + 0.03 - DECK_Z, faces="+x -x +z", z0=DECK_Z),
                      (LIP_X0 + LIP_X1) / 2, 0.0, 0.0)
    back = G.translate(G.box(lw, 0.08, RAIL_TOP - (ZB - 0.025), faces="+x -x +z", z0=ZB - 0.025), XB, 0.0, 0.0)
    L = (XF - XB) / math.cos(SLOPE)
    sides = [_on_slope(G.box(0.065, L, 0.05, faces="+x +y -y +z"), XF, XB, sy * (wy - 0.005), -0.006)
             for sy in (1, -1)]
    add(B.Part("hood_frame", G.merge([lip, back] + sides), paint=p_brass, seed=45, weight=0.7))

    # the grab handle standing off the lip, its corners rounded (and mitred, so they do not pinch)
    hx, hz = LIP_X1 + 0.038, (DECK_Z + ZF + 0.03) / 2
    hpath = [(LIP_X1 - 0.006, -0.18, hz), (hx - 0.022, -0.18, hz), (hx - 0.006, -0.174, hz), (hx, -0.158, hz),
             (hx, 0.158, hz), (hx - 0.006, 0.174, hz), (hx - 0.022, 0.18, hz), (LIP_X1 - 0.006, 0.18, hz)]
    add(B.Part("handle", _mitred_sweep(hpath, 0.03, 6), paint=p_brass, seed=47, weight=0.6))

    # the royal-blue back wall inside the hood (the scoops show against it)
    wall = G.translate(G.box(HOOD_W, 0.03, ZB - DECK_Z, faces="+x -x", z0=DECK_Z), XB - 0.012, 0.0, 0.0)
    wall.set_weight(0.7)
    add(B.Part("back_wall", wall, paint=p_back_wall, seed=49))

    # the three porcelain tubs sunk in the ice, each heaped with ice cream: a scalloped skirt that stops inside
    # the tub's white lip, a crease and a round scoop on top that leans back, away from the glass
    rims, heaps = [], []
    for k, (ty, _name) in enumerate(TUBS):
        rims.append(G.translate(G.cylinder(TUB_R, TUB_Z1 - TUB_Z0, 12, False, z0=TUB_Z0), TUB_X, ty, 0.0))
        lid = CB.rim_cap(TUB_X, ty, TUB_Z1, TUB_R, 12, "tub_lip")
        lid.set_weight(0.5)
        rims.append(lid)
        heaps.append(G.translate(CB.heap(TUB_Z1, 12, 61 + k, 0.5 * k), TUB_X, ty, 0.0))
    add(B.Part("tubs", G.merge(rims), paint=p_tub, seed=51, weight=1.6))
    add(B.Part("ice_cream", G.merge(heaps), paint=p_scoop, seed=53, weight=1.6, ao_floor=0.6))

    # the cone crest on the back rail: a gold cup, the waffle cone, a pink scoop on a drip lip, a cherry
    cup = G.translate(G.lathe([(0.024, RAIL_TOP - 0.004), (0.042, RAIL_TOP + 0.02), (0.032, RAIL_TOP + 0.05)],
                              8), CREST_X, 0.0, 0.0)
    add(B.Part("cone_cup", cup, paint=p_gold, seed=55, weight=0.6))
    cone = G.translate(G.cone(0.005, CONE_R, CONE_L, 8, caps=False, z0=CONE_TIP), CREST_X, 0.0, 0.0)
    add(B.Part("cone", cone, paint=CB.p_waffle, seed=57, weight=1.8))
    scoop, top_z = CB.crest_scoop(SCOOP_Z, CREST_BALL, 10)
    add(B.Part("crest_scoop", G.translate(scoop, CREST_X, 0.0, 0.0), paint=p_scoop, seed=59, weight=1.8))
    cherry = G.translate(G.sphere(0.04, 6, 4), CREST_X + 0.006, 0.0, top_z + 0.018)
    add(B.Part("cherry", cherry, paint=p_cherry, seed=61, weight=1.2, ao_floor=0.7))

    # icicles hanging from the lip's edge, left and right of the plaque
    ics = []
    for k, (y, ln) in enumerate(((-0.43, 0.12), (-0.365, 0.165), (-0.3, 0.1), (0.3, 0.11), (0.365, 0.17),
                                 (0.43, 0.125))):
        r = 0.032 + 0.004 * ((k * 7) % 3) / 2.0
        ics.append(G.translate(G.cone(0.0, r, ln, 5, caps=(False, True), z0=-ln), LIP_X1 - 0.004, y,
                               DECK_Z + 0.004))
    add(B.Part("icicles", G.merge(ics), paint=CB.p_icicle, seed=63, weight=0.6, ao_floor=0.7))

    # the collision box, its top sloping down to the front lip with the glass
    d.collision = CB.hull_wedge(1.1, 0.7, 0.8, ZF + 0.05)

    # frost mist rolling off the front lip's top edge between the handle and the front posts (Y 0.32-0.44 clear
    # of both), 6 cm in front of the lip face; it sinks down past the icicles
    d.particles = [CB.mist(LIP_X1 + 0.04, y, ZF + 0.02) for y in (0.23, -0.23)]     # along the whole front lip
    return d
