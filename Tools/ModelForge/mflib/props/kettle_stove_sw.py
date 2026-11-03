"""19306 KettleStoveSW, the Bluefire Kettle (Stormwind tea station), CAFE.SPEC.md section 5.8.1.

A royal-blue enamel kettle steaming on a black iron kitchen stove with a fire burning behind its door, shaped so
it reads as "the tea kettle" at a glance from the front three-quarter view: the kettle shows its whole profile
(a gooseneck spout to its left, +Y, and an arched brass handle with a walnut grip over the lid, both in the
same plane), steam puffs from the spout, and the arched fire door glows orange behind two dark grate bars with
blue roots at the foot of the flames and the fire flickering in it. Stormwind and human-made: a black iron range on
four cabriole legs with brass paw feet, royal-blue enamel panels framed in riveted brass on its front and sides
(a gold lion medallion on each side, a brass oven thermometer beside the door), a brass guard rail round the
front and sides with a blue-and-cream tea towel over it, a gold lion over the fire window and on the kettle, a
brass-rimmed cooktop with a porcelain teacup waiting by the kettle, and a jointed black stovepipe with brass
collars and a rain cap. 0.8 (Y) x 0.6 (X) x 1.1 yd (the pipe to 1.7), front (+X) toward the barista.

What makes a player name it at 4-15 yd (front three-quarter view), and how big each cue is:
- the kettle: a squat round body 0.39 across and 0.22 tall in bright royal-blue enamel (a lighter, glossier
  blue than the panels, so it stands out from the stove), sitting high on the cooktop (0.72-1.09), half the
  stove's width;
- its profile: a gooseneck spout 0.22 long and 0.09-0.05 thick to the side, an arched handle 0.22 wide rising
  0.18 over the shoulder (brass 0.038 thick, a knob ball 0.065) with a walnut grip 0.067 thick; steam from the
  spout tip, faintly visible already at the tip;
- the fire: an arched door 0.38 x 0.385 on the stove front whose window (0.30 x 0.255) glows orange over three
  blue flame roots (0.02-0.08 tall) behind two dark iron bars (0.034) and a sill, with the fire flickering in it
  (the second emitter); it glows at night too;
- the stove: a black iron box 0.7 x 0.41 x 0.55 on four legs (0.12 tall, 0.07 thick) under a cooktop slab
  0.76 x 0.47, and a chunky stovepipe 0.16 across rising behind the kettle, jogging back at a jointed elbow (two
  brass collars 0.2 across) to a rain cap at 1.7 (0.2 across);
- Stormwind and charm: the blue enamel front and side panels (a gold lion 0.2 across on each side), the brass
  guard rail (0.06 thick, on 0.06 brackets) round three sides, the tea towel (0.13 x 0.23), the oven
  thermometer (0.11 across), the lions on the door (0.085) and the kettle (0.15), the teacup (0.1 across, saucer
  0.15).

Deviations from the section 5.8.1 numbers, for the cues and the section 5.8 size (0.6 deep, pipe to 1.7):
- the kettle is r 0.194 (not 0.16), so it reads first; its handle arches over the lid in the spout's plane
  (not a crosswise bail), and the spout points to the side (+Y), so the front views see the classic kettle
  profile instead of a spout aimed at the camera;
- the body is 0.7 x 0.41 x 0.55 (0.12-0.67, on legs; not 0.7 x 0.55 x 0.7) under a 0.05 cooktop, so the kettle
  ends at 1.09; the stovepipe is r 0.08 (not 0.07, so it is as chunky as the body), rises from the cooktop's
  back right corner (not from the back wall) and jogs back and out at a jointed elbow halfway up, which keeps
  its rain cap inside the 0.6 depth;
- the body's front and side panels are royal-blue enamel in riveted brass frames, with black iron round them
  (legs, cooktop, door, pipe), so the station carries Stormwind's blue and brass, not only the kettle;
- the brass rails are a guard rail round the front and both sides, carrying a tea towel; the teacup and the
  oven thermometer (a shallow brass case, its dial painted on the cap) are additions;
- the fire is a glow window (the glow material on the atlas, the flames painted so that their edges add
  nothing, saturated blue roots at the foot of the flames for the name) behind geometry grate bars, plus an
  unlit additive emitter as the flicker, born on the bars' axis just over the sill;
- textures: the atlas and Steam, no Fire (section 5.8 lists Fire): the flicker uses the Steam puff tinted orange,
  because the shared Fire sprite has an opaque bright bottom row, which draws a hard white bar across the window
  wherever a sprite is; the soft puff has no edge, so the flicker is a soft glow over the painted flames, and
  where a camera-facing sprite leans out of the door in a side view it is a faint glow, not a cut-off flame;
- collision: a gable over the stove and kettle and a peaked 8-sided prism round the stovepipe (section 5.8
  says "box + pipe cylinder"), so no facet on top is flat enough to stand on (section 5.2.6).
"""

import math

from .. import build as B
from .. import emblem as E
from .. import emitters as EM
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "KettleStoveSW"
DISPLAY = 19306

ENAMEL = T.hexc("2E4E8C")
KETTLE_BLUE = T.hexc("3E6DC2")        # the kettle's enamel, brighter than the panels: it reads first
CREAM = T.hexc("F1E6CC")
STOVE_BLACK = dict(light_c=T.hexc("A8ACB8"), base=T.hexc("2C2D33"), dark=T.hexc("0E0E12"),
                   bounce=T.hexc("3A3028"), patina=T.hexc("4A3626"))

BODY_X0, BODY_X1 = -0.20, 0.21        # body back and front (X)
BODY_W = 0.70
BODY_Z0, BODY_Z1 = 0.12, 0.67
TOP_X0, TOP_X1 = -0.22, 0.25          # cooktop slab
TOP_W = 0.76
TOP_Z1 = 0.72
KX, KY = 0.035, -0.035                 # kettle axis
KR = 0.18                              # kettle body radius before KS
KS = 1.08                              # the kettle's scale (its profile is drawn at 1.0)
DOOR_Y, DOOR_W = 0.0, 0.38
DOOR_Z0, DOOR_Z1 = 0.165, 0.55
DOOR_D = 0.03
WIN_Y, WIN_Z0, WIN_Z1 = 0.15, 0.185, 0.44  # window half width, bottom, top (its top is an arch)
BARS_Y, BAR_R = (-0.055, 0.055), 0.017     # the grate bars across the window
FIRE_Z = 0.25                          # the fire glows' birth height, just over the sill (0.202)
RAIL_X, RAIL_Y, RAIL_Z, RAIL_R = 0.256, 0.378, 0.6, 0.03
RAIL_BACK = -0.12                      # where the side rails end
PIPE_R = 0.08                          # chunky: 0.16 across
PIPE_BASE = (-0.122, -0.272)           # where the pipe leaves the cooktop (1 cm clear of the kettle's belly)
PIPE_TOP = (-0.198, -0.292)            # its axis above the elbow
PIPE_J0, PIPE_J1 = 1.05, 1.17          # the elbow's two joints (brass collars)
CAP_Z0, CAP_Z1, CAP_R = 1.615, 1.70, 0.1
TOWEL_Y0, TOWEL_Y1 = 0.20, 0.33        # the tea towel on the front rail, clear of the door
TOWEL_Z0 = 0.37                        # its hem
CUP_AT = (0.165, 0.27)                 # the teacup on the cooktop
THERMO = (-0.258, 0.45, 0.054)         # the oven thermometer on the front panel: Y, z, radius


# ----------------------------------------------------------------------------------------------- paints

def stove_iron(ctx, seed, p=None):
    """Stove black: blued black iron with painted metal bands, a little warm rust in the recesses."""
    return T.metal(ctx, seed, {"streak_k": 0.45, "patina": 0.1}, STOVE_BLACK["light_c"], STOVE_BLACK["base"],
                   STOVE_BLACK["dark"], STOVE_BLACK["bounce"], STOVE_BLACK["patina"], 0.08)


def p_body(ctx, seed, p):
    """Black iron framed in brass round royal-blue enamel: the side faces carry a wide iron margin with a dark
    groove, a lit brass trim and the panel with its gold lion decal; the front a riveted brass frame, a dark
    groove and an enamel field round the door; the back is plain iron."""
    c = stove_iron(ctx, seed)
    e = T.edge_dist(ctx)
    if ctx.chart in ("+y", "-y"):
        if e < 0.03:
            return T.frame_rivets(ctx, T.g_brass(ctx, seed + 1, {"streak": False, "patina": 0.1}), 0.016, 0.1,
                                  0.012)
        if e < 0.075:
            c = T.inset_panel(ctx, c, 0.055, 0.012)
            return c
        if e < 0.088:
            return T.g_brass(ctx, seed + 2, {"streak": False})
        c = T.g_enamel(ctx, seed + 5, {"color": ENAMEL, "chips": 2, "chip_r": 0.025, "gloss": 0.4})
        if e < 0.098:
            c = T.scale(c, 0.55)
        return c
    if ctx.chart == "+x":
        if e < 0.026:
            return T.frame_rivets(ctx, T.g_brass(ctx, seed + 1, {"streak": False, "patina": 0.1}), 0.013, 0.1,
                                  0.011)
        if e < 0.036:
            return T.scale(c, 0.45)               # the groove between the frame and the enamel
        c = T.g_enamel(ctx, seed + 7, {"color": ENAMEL, "chips": 2, "chip_r": 0.022, "gloss": 0.35})
        return T.scale(c, 0.6) if e < 0.044 else c
    return c


def p_top(ctx, seed, p):
    """The cooktop: polished black iron with a brass edge; on the top face, the hob plate rings under the
    kettle and round the stovepipe collar (a lit lip, a dark groove)."""
    if ctx.chart != "+z":
        c = T.g_brass(ctx, seed + 1, {"streak": True, "patina": 0.08})
        return T.mix(c, T.hexc("FFE9A0"), 0.15) if ctx.t < 0.012 else c
    c = stove_iron(ctx, seed)
    c = T.mix(c, T.hexc("6A6E78"), 0.2)
    x, y = ctx.pos[0], ctx.pos[1]
    for cx, cy, rr in ((KX, KY, 0.235), (PIPE_BASE[0], PIPE_BASE[1], PIPE_R + 0.04)):
        d = math.hypot(x - cx, y - cy) - rr
        if d < -0.016:
            c = T.scale(c, 0.8)                   # the hob plate, a shade darker than the top
        elif d < 0.0:
            c = T.scale(c, 0.42)                  # its groove
        elif d < 0.014:
            c = T.mix(c, T.hexc("C4C8D4"), 0.45)  # the lit lip outside it
    if T.edge_dist(ctx) < 0.022:
        c = T.mix(T.g_brass(ctx, seed + 2, {"streak": False}), T.hexc("FFE9A0"), 0.2)
    return c


def p_iron(ctx, seed, p):
    return stove_iron(ctx, seed)


def p_brass(ctx, seed, p):
    return T.g_brass(ctx, seed, p)


def p_gold(ctx, seed, p):
    return T.g_gold(ctx, seed, p)


def p_feet(ctx, seed, p):
    """Brass paw feet: three dark toe grooves facing out from the stove's centre."""
    c = T.g_brass(ctx, seed, {"patina": 0.15})
    x, y, z = ctx.pos
    a = math.atan2(ctx.n[1], ctx.n[0]) - math.atan2(y, x)
    a = (a + math.pi) % (2 * math.pi) - math.pi
    if abs(a) < 1.2 and z > 0.012:
        g = abs(math.sin(a * 2.5))
        if g < 0.25:
            c = T.mix(c, T.hexc("3A2006"), (1.0 - g / 0.25) * 0.75)
    return c


def p_door(ctx, seed, p):
    """The fire door: black iron with a brass rim and a riveted inner frame line round the window."""
    c = stove_iron(ctx, seed)
    if ctx.chart.endswith("_side"):
        return T.g_brass(ctx, seed + 1, {"streak": False})
    if T.edge_dist(ctx) < 0.024:
        return T.frame_rivets(ctx, T.g_brass(ctx, seed + 1, {"streak": False, "patina": 0.1}), 0.012, 0.08,
                              0.011)
    return c


def _fire(u, y, seed, tongues=3.0):
    """Flame intensity k (0..1) and colour at u across and y up (0 at the bed) of a fire chart: a bed of coals
    along the bottom and tongues of flame rising from it (tex.g_fire_glow's shape)."""
    tong = 0.5 + 0.5 * math.sin(u * 2.0 * math.pi * tongues + T.fbm(u * 3.0, y * 2.0, seed, 2) * 3.0)
    height = 0.42 + 0.5 * tong * (0.6 + 0.4 * T.fbm(u * 5.0, 0.3, seed + 1, 2))
    k = T.clamp01(1.0 - y / height)
    k *= 0.75 + 0.55 * T.fbm(u * 6.0, y * 4.0, seed + 2, 2)
    coal = T.smoothstep(0.24, 0.0, y) * (0.65 + 0.35 * T.noise(u * 14.0, y * 6.0, seed + 3))
    k = T.clamp01(max(k, coal))
    c = T.ramp([(0.0, T.hexc("4A0A02")), (0.3, T.hexc("B02A06")), (0.55, T.hexc("FF6A10")),
                (0.8, T.hexc("FFB040")), (1.0, T.hexc("FFF0B0"))], k)
    return k, c


def p_window(ctx, seed, p):
    """The fire window (glow: unlit, additive, so black adds nothing): flames over a coal bed, faded to black
    toward an arched top and the sides, so the window's outline is the arch, not the quad. "Bluefire": just
    over the sill (it covers the chart's bottom 0.07) the roots of the flames burn a saturated blue instead of
    orange, taller under the tall tongues (the same tongue phase as _fire) and only in the middle 70 %, so they
    read as the feet of three flames, not as a blue stripe."""
    u, v = ctx.u, ctx.v
    x = (u - 0.5) * 2.0
    arch = 0.42                                  # the top 42 % of the window is the arch
    if v < arch:
        q = math.hypot(x, (arch - v) / arch)
        m = T.smoothstep(1.0, 0.86, q)
    else:
        m = T.smoothstep(1.0, 0.86, abs(x))
    m *= T.smoothstep(1.0, 0.94, v)
    y = 1.0 - v
    k, c = _fire(u, y, seed)
    k = 0.4 + 0.6 * k                            # the whole window glows; the tongues burn brighter
    c = T.ramp([(0.4, T.hexc("B8300A")), (0.6, T.hexc("FF6A10")), (0.8, T.hexc("FFB040")),
                (1.0, T.hexc("FFF0B0"))], k)
    tong = 0.5 + 0.5 * math.sin(u * 2.0 * math.pi * 3.0 + T.fbm(u * 3.0, y * 2.0, seed, 2) * 3.0)
    top = 0.16 + 0.16 * tong                     # the blue rises highest under the tall tongues
    b = T.smoothstep(0.07, 0.11, y) * T.smoothstep(top + 0.05, top - 0.04, y)
    b *= T.smoothstep(0.85, 0.65, abs(x))
    blue = T.ramp([(0.4, T.hexc("1E50E8")), (0.75, T.hexc("2E6BFF")), (1.0, T.hexc("7AA8FF"))], k)
    c = T.mix(c, blue, b * 0.95)
    return T.scale(c, m * (0.85 + 0.15 * k))


def p_kettle(ctx, seed, p):
    """Royal-blue enamel with a gloss band on the shoulder, a gold pinstripe round the belly, a darker sooty
    foot ring and a few chips; the spout is the same enamel."""
    c = T.g_enamel(ctx, seed, {"color": KETTLE_BLUE, "chips": 2, "chip_r": 0.02, "gloss": 0.6})
    if ctx.part == "kettle":
        z = (ctx.pos[2] - TOP_Z1) / KS
        if 0.112 < z < 0.123 and ctx.n[2] < 0.75:
            c = T.mix(T.g_gold(ctx, seed + 3, {"streak": False}), T.hexc("FFF0A0"), 0.2)
        elif z < 0.022:
            c = T.mix(c, T.hexc("101418"), T.smoothstep(0.022, 0.0, z) * 0.7)
    return c


def p_lid(ctx, seed, p):
    """Cream enamel lid with a blue rim."""
    c = T.g_enamel(ctx, seed, {"color": CREAM, "chips": 1, "chip_r": 0.015, "gloss": 0.3})
    r = math.hypot(ctx.pos[0] - KX, ctx.pos[1] - KY) / KS
    if r > 0.078:
        c = T.mix(c, KETTLE_BLUE, 0.9)
    return c


def p_walnut(ctx, seed, p):
    c = T.g_wood(ctx, seed, {"kind": "walnut", "along": "t"})
    return T.mix(c, T.hexc("A06A40"), T.clamp01(ctx.n[2]) * 0.4)


def p_towel(ctx, seed, p):
    """A blue-and-cream checked tea towel: broad checks (0.045), a darker blue stripe near each end, a cream
    fringe band at the hem; the folds over the rail are darker."""
    x, y, z = ctx.pos
    a, b = y / 0.045, z / 0.045
    ca, cb = int(math.floor(a)) % 2, int(math.floor(b)) % 2
    c = CREAM if (ca + cb) % 2 == 0 else T.mix(CREAM, ENAMEL, 0.75 if ca and cb else 0.45)
    c = T.mix(c, T.scale(c, 0.85), T.noise(y * 30.0, z * 30.0, seed) * 0.4)
    if z < TOWEL_Z0 + 0.03:
        c = T.mix(CREAM, T.hexc("D8CAA8"), T.noise(y * 60.0, 0.0, seed + 1))
    elif z < TOWEL_Z0 + 0.05:
        c = T.mix(ENAMEL, T.scale(ENAMEL, 1.2), 0.3)
    if ctx.n[0] < -0.3:
        c = T.scale(c, 0.7)
    return c


def p_pipe(ctx, seed, p):
    """The stovepipe: stove black, sooty toward the top (its brass is the collars and the band under the cap)."""
    c = stove_iron(ctx, seed)
    return T.mix(c, T.hexc("141210"), T.smoothstep(1.25, 1.6, ctx.pos[2]) * 0.55)


def cup_paints(base_z, at):
    """White porcelain with a royal-blue band and a gold line under it on the outer wall (by height and facing,
    so the inside stays white), a saucer with a blue rim, amber tea with a lighter middle."""
    cx, cy = at

    def p_cup(ctx, seed, p):
        c = T.g_ceramic(ctx, seed, {})
        x, y, z = ctx.pos
        rx, ry = x - cx, y - cy
        rr = math.hypot(rx, ry) or 1.0
        lz = z - base_z
        if (ctx.n[0] * rx + ctx.n[1] * ry) / rr > 0.2 or ctx.n[2] < -0.5:
            if 0.044 <= lz <= 0.066:
                c = T.mix(ENAMEL, T.scale(ENAMEL, 1.3), T.clamp01(ctx.n[0] * 0.5 + 0.5))
            elif 0.038 <= lz < 0.044:
                c = T.hexc("E8B848")
        return c

    def p_saucer(ctx, seed, p):
        c = T.g_ceramic(ctx, seed, {})
        if math.hypot(ctx.pos[0] - cx, ctx.pos[1] - cy) > 0.056 and ctx.n[2] > 0.0:
            c = T.mix(c, ENAMEL, 0.85)
        return c

    def p_tea(ctx, seed, p):
        r = math.hypot(ctx.pos[0] - cx, ctx.pos[1] - cy)
        return T.mix(T.hexc("C8762A"), T.hexc("7A3A12"), T.smoothstep(0.008, 0.032, r))

    return p_cup, p_saucer, p_tea


# ---------------------------------------------------------------------------------------------- decals

def d_side_lion(w, h):
    """A gold lion medallion in the middle of each enamel side panel."""
    img = T.Img(w, h, (0, 0, 0, 0))
    s = int(min(w, h) * 0.52)
    if s >= 8:
        P2.composite(img, E.render_relief("lion_head", s, s, P2.GOLD_RELIEF), (w - s) // 2, (h - s) // 2 - h // 20)
    return img


def d_door(w, h):
    """The gold lion in the door's arch, over the glowing window."""
    img = T.Img(w, h, (0, 0, 0, 0))
    s = int(min(w, h) * 0.22)
    if s >= 8:
        P2.composite(img, E.render_relief("lion_head", s, s, P2.GOLD_RELIEF), (w - s) // 2, int(h * 0.075))
    return img


def d_kettle_crest(w, h):
    s = int(min(w, h) * 0.75)
    img = T.Img(w, h, (0, 0, 0, 0))
    if s >= 8:
        P2.composite(img, E.render_relief("lion_head", s, s, P2.GOLD_RELIEF), (w - s) // 2, int(h * 0.3))
    return img


def d_thermo(w, h):
    """The oven thermometer's face (the case's cap): a lit brass bezel round a cream dial with royal-blue, gold
    and red bands, 0-12 ticks and a red needle in the gold (the fire is lit)."""
    img = T.Img(w, h, (0, 0, 0, 0))
    cx, cy = w / 2.0, h / 2.0
    r_out = min(w, h) / 2.0
    r_in = r_out * 0.78
    lit, mid, dark = T.hexc("FFE9A0"), T.hexc("C89A3A"), T.hexc("5A3A0C")
    for y in range(h):
        for x in range(w):
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            d = math.hypot(dx, dy)
            if d > r_out + 0.5 or d < r_in - 0.5:
                continue
            k = T.clamp01(0.5 - (dx + dy) / (2.0 * r_out) * 0.9)       # lit toward the top left
            c = T.mix(dark, mid, k * 1.6) if k < 0.62 else T.mix(mid, lit, (k - 0.62) / 0.38)
            img.set(x, y, c, T.clamp01(r_out + 0.5 - d))
    dial = int(2 * r_in + 1)
    if dial >= 6:
        face = P2.gauge_face(dial, dial, {"needle_deg": 35.0, "bands": [(0.0, 0.45, ENAMEL),
                                                                          (0.45, 0.78, T.hexc("E8B848")),
                                                                          (0.78, 1.0, T.hexc("C83A28"))]})
        P2.composite(img, face, int(cx - dial / 2.0), int(cy - dial / 2.0))
    return img


# ------------------------------------------------------------------------------------------------ parts

def _arch(w2, z0, z1, n=6):
    """A door outline in the door's plane (x = Y, y = Z): straight sides from z0, a round arch on top."""
    r = w2
    zc = z1 - r
    pts = [(w2, z0)]
    for k in range(n + 1):
        a = math.pi * k / n
        pts.append((math.cos(a) * r, zc + math.sin(a) * r))
    pts.append((-w2, z0))
    return pts


def _leg(x, y):
    """A cabriole leg from under the body's corner, kicking out to a brass paw foot."""
    sx, sy = (1 if x > 0 else -1), (1 if y > 0 else -1)
    path = [(x, y, BODY_Z0 + 0.02), (x + sx * 0.006, y + sy * 0.008, 0.085), (x + sx * 0.02, y + sy * 0.028, 0.05)]
    leg = G.sweep(path, lambda t: 0.034 - 0.008 * t, 6, caps=(False, False))
    foot = G.translate(G.dome(0.036, 0.052, 2, 6), x + sx * 0.024, y + sy * 0.03, 0.0)
    return leg, foot


def _rail_path():
    """The guard rail: from the back of the left side, along it, round the front corner, across the front and
    back along the right side (rounded corners)."""
    rc = 0.05
    left = [(RAIL_BACK, RAIL_Y, RAIL_Z), (RAIL_X - rc, RAIL_Y, RAIL_Z)]
    c1 = G.arc_path((RAIL_X - rc, RAIL_Y - rc, RAIL_Z), rc, math.pi / 2, 0.0, 2, ("x", "y"))
    c2 = G.arc_path((RAIL_X - rc, -RAIL_Y + rc, RAIL_Z), rc, 0.0, -math.pi / 2, 2, ("x", "y"))
    right = [(RAIL_X - rc, -RAIL_Y, RAIL_Z), (RAIL_BACK, -RAIL_Y, RAIL_Z)]
    return G.polyline_join(left, c1, c2, right)


def _towel():
    """The tea towel folded over the front rail: a back flap between the rail and the stove, a roll over the
    rail and a longer front flap hanging free, slightly kicked out at the hem."""
    w = TOWEL_Y1 - TOWEL_Y0
    yc = (TOWEL_Y0 + TOWEL_Y1) / 2
    t = 0.012
    back = G.translate(G.box(w, t, RAIL_Z - 0.5, faces="+x -x +y -y -z", z0=0.5), RAIL_X - RAIL_R - t / 2 - 0.002,
                       yc, 0.0)
    roll = G.transform(G.cylinder(RAIL_R + t, w, 8, False, z0=-w / 2),
                       G.mat_chain(G.mat_translate(RAIL_X, yc, RAIL_Z), G.mat_rot_x(math.pi / 2)))
    hang = RAIL_Z - TOWEL_Z0
    front = G.box(w, t, hang, faces="+x -x +y -y -z", z0=-hang)
    front = G.transform(front, G.mat_chain(G.mat_translate(RAIL_X + RAIL_R + t / 2 + 0.002, yc, RAIL_Z),
                                           G.mat_rot_y(math.radians(-2))))
    return G.merge([back, roll, front])


def _kettle():
    """The kettle around its own axis, base at z 0: body, lid, knob, spout (toward +Y), arched handle and grip
    (in the YZ plane, over the lid). Returns the meshes and the spout's tip and direction."""
    prof = [(0.135, 0.0), (0.165, 0.016), (KR, 0.06), (0.176, 0.098), (0.155, 0.142), (0.125, 0.176),
            (0.098, 0.198), (0.09, 0.205)]
    body = G.lathe(prof, 16, name="kettle")
    lid = G.lathe([(0.097, 0.197), (0.1, 0.207), (0.084, 0.221), (0.048, 0.231), (0.0, 0.234)], 10, name="lid")
    knob = G.merge([G.cylinder(0.014, 0.02, 6, False, z0=0.228), G.sphere(0.03, 6, 3, z0=0.236)])
    root = (0.0, 0.13, 0.055)
    tip = (0.0, 0.335, 0.232)
    path = G.bezier_path(root, (0.0, 0.245, 0.062), (0.0, 0.272, 0.16), tip, 6)
    spout = G.sweep(path, lambda t: 0.04 - 0.017 * t, 8, caps=(False, True), name="spout")
    hz, hr = 0.215, 0.1
    arc = G.arc_path((0.0, 0.0, hz), hr, math.pi, 0.0, 6, ("y", "z"))
    hpath = G.polyline_join([(0.0, -hr, 0.168)], arc, [(0.0, hr, 0.168)])
    handle = G.sweep(hpath, 0.0175, 6, name="handle")
    grip = G.transform(G.capsule(0.031, 0.15, 8, 2), G.mat_chain(G.mat_translate(0.0, -0.075, hz + hr),
                                                                G.mat_rot_x(-math.pi / 2)))
    d = G.norm(G.sub(path[-1], path[-2]))
    return {"body": body, "lid": lid, "knob": knob, "spout": spout, "handle": handle,
            "grip": grip, "tip": tip, "dir": d}


def _teacup():
    """A porcelain teacup (1.5x real size) with a loop handle toward +Y, on a saucer, base at z 0: a real wall
    so the bake does not see the inner wall through the outer one. The tea sits just over the inner cone (which
    runs from z+0.048 at the middle to z+0.058 at r 0.041), leaving a thin white rim. Returns (cup, saucer,
    tea surface)."""
    sh = 0.012
    saucer = G.lathe([(0.0, 0.0), (0.052, 0.0), (0.074, 0.01), (0.071, sh), (0.0, sh * 0.8)], 8, name="saucer")
    z = sh * 0.8
    cup = G.lathe([(0.0, z), (0.031, z), (0.047, z + 0.05), (0.05, z + 0.062), (0.041, z + 0.058),
                   (0.0, z + 0.048)], 8, name="cup")
    ring = G.torus(0.02, 0.015, 6, 4, arc=math.pi * 1.2, start=-math.pi * 0.6, name="handle")
    handle = G.transform(ring, G.mat_chain(G.mat_translate(0.0, 0.05, z + 0.035), G.mat_rot_z(math.pi / 2),
                                           G.mat_rot_x(math.pi / 2)))
    tea = G.disc(0.034, 8, z + 0.0575, name="tea")
    return G.merge([cup, handle]), saucer, tea


def _peaked_prism(r, wall_h, top_h, x, y, sides=8):
    """A collision prism round the stovepipe with a pointed roof: walls to wall_h, the apex at top_h, so no
    facet is walkable (the roof's normals' z under 0.6428 when (top_h - wall_h) / apothem > 1.2); 4 * sides - 2
    triangles, closed and wound outward like geom.hull_cylinder."""
    pos = []
    for z in (0.0, wall_h):
        for i in range(sides):
            a = 2.0 * math.pi * i / sides
            pos.append((x + math.cos(a) * r, y + math.sin(a) * r, z))
    pos.append((x, y, top_h))
    apex = len(pos) - 1
    tris = []
    for i in range(sides):
        j = (i + 1) % sides
        tris += [(i, j, sides + j), (i, sides + j, sides + i), (sides + i, sides + j, apex)]
    for i in range(1, sides - 1):
        tris.append((0, i + 1, i))
    return pos, tris


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (0.8, 0.6, 1.1)
    d.render_size = (0.8, 0.6, 1.7)
    d.collision_size = (0.8, 0.6, 1.7)
    d.budget = 1600
    d.kind = "station"
    d.atlas = {"atlas": 256}
    d.sloped_top = True
    add = d.add
    bx = (BODY_X0 + BODY_X1) / 2
    bd = BODY_X1 - BODY_X0

    # legs: cabriole legs under the body's corners on brass paw feet
    legs, feet = [], []
    for x in (BODY_X1 - 0.05, BODY_X0 + 0.05):
        for y in (BODY_W / 2 - 0.05, -BODY_W / 2 + 0.05):
            leg, foot = _leg(x, y)
            legs.append(leg)
            feet.append(foot)
    add(B.Part("legs", G.merge(legs), paint=p_iron, seed=11, weight=0.4))
    add(B.Part("feet", G.merge(feet), paint=p_feet, seed=12, weight=0.4, ao_floor=0.6))

    # body: a black iron box with brass-framed blue enamel panels on the front and sides
    body = G.box(BODY_W, bd, BODY_Z1 - BODY_Z0, 0.03, faces="+x -x +y -y -z", z0=BODY_Z0)
    body = G.translate(body, bx, 0.0, 0.0)
    for ch in body.charts:
        ch.weight = {"+x": 1.1, "-x": 0.15, "-z": 0.15}.get(ch.name, 1.0)
    add(B.Part("body", body, paint=p_body, seed=21, decals={"+y": d_side_lion, "-y": d_side_lion}))

    # cooktop: a slab with a brass edge, overhanging the body
    top = G.box(TOP_W, TOP_X1 - TOP_X0, TOP_Z1 - BODY_Z1, faces="+x -x +y -y +z", z0=BODY_Z1)
    top = G.translate(top, (TOP_X0 + TOP_X1) / 2, 0.0, 0.0)
    for ch in top.charts:
        ch.weight = {"+z": 0.8, "-x": 0.15}.get(ch.name, 0.6)
    add(B.Part("cooktop", top, paint=p_top, seed=31))

    # the fire door: an arch-topped iron plate in a brass rim, the glow window, two iron grate bars and a sill
    door = G.extrude(_arch(DOOR_W / 2, DOOR_Z0, DOOR_Z1), DOOR_D, 0.008, back=False)
    door = G.transform(door, G.mat_chain(G.mat_translate(BODY_X1 - 0.004, DOOR_Y, 0.0), G.MAT_EXTRUDE_FRONT))
    for ch in door.charts:
        ch.weight = 1.8 if ch.name.endswith("_front") else 0.5
    add(B.Part("door", door, paint=p_door, seed=41, decals={"extrude_front": d_door}))
    fx = BODY_X1 - 0.004 + DOOR_D
    win = G.box(2 * WIN_Y, 0.004, WIN_Z1 - WIN_Z0, faces="+x", z0=WIN_Z0)
    win = G.translate(win, fx + 0.002, DOOR_Y, 0.0)
    win.set_weight(2.0)                          # the main cue: twice the texels of the body
    add(B.Part("fire_window", win, "glow", paint=p_window, seed=43, ao_floor=1.0))
    bars = []
    for y in BARS_Y:
        bars.append(G.translate(G.cylinder(BAR_R, WIN_Z1 - WIN_Z0 + 0.02, 6, (False, True), z0=WIN_Z0 - 0.01),
                                fx + 0.012, DOOR_Y + y, 0.0))
    sill = G.transform(G.cylinder(BAR_R, 2 * WIN_Y + 0.03, 6, True, z0=-WIN_Y - 0.015),
                       G.mat_chain(G.mat_translate(fx + 0.012, DOOR_Y, WIN_Z0), G.mat_rot_x(-math.pi / 2)))
    add(B.Part("grate", G.merge(bars + [sill]), paint=p_iron, seed=45, weight=0.7))
    # door handle: a brass knob on the door's right rim (only its edge reaches the window's faded side)
    knob = G.translate(G.sphere(0.031, 6, 3), fx + 0.02, DOOR_Y - DOOR_W / 2 + 0.02, 0.32)
    add(B.Part("door_knob", knob, paint=p_gold, seed=47, weight=0.5, ao_floor=0.7))
    # the oven thermometer left of the door: a shallow brass case, its dial on the cap (many texels: it is a
    # 0.11 dial on a 256 atlas)
    ty, tz, tr = THERMO
    thermo = G.transform(G.cylinder(tr, 0.02, 10, (False, True)),
                         G.mat_chain(G.mat_translate(BODY_X1 - 0.004, ty, tz), G.MAT_DISC_FRONT))
    add(B.Part("thermometer", thermo, paint=p_brass, seed=49, weight=3.0, ao_floor=0.7,
               decals={"cyl_top": d_thermo}))

    # the brass guard rail round the front and sides, on four brackets, and the tea towel over it
    rail = G.sweep(_rail_path(), RAIL_R, 6, caps=(True, True))
    brackets = []
    bk = 0.06                                    # the brackets' square section
    for y in (0.27, -0.27):
        brackets.append(G.translate(G.box(bk, RAIL_X - BODY_X1 + 0.01, bk, faces="+x +y -y +z -z",
                                          z0=RAIL_Z - bk / 2),
                                    (RAIL_X + BODY_X1) / 2 - 0.005, y, 0.0))
    for s in (1, -1):
        brackets.append(G.translate(G.box(RAIL_Y - BODY_W / 2 + 0.01, bk, bk, faces="+x -x +y -y +z",
                                          z0=RAIL_Z - bk / 2),
                                    RAIL_BACK + 0.03, s * (RAIL_Y + BODY_W / 2 - 0.01) / 2, 0.0))
    add(B.Part("rail", G.merge([rail] + brackets), paint=p_brass, seed=51, weight=0.6))
    add(B.Part("towel", _towel(), paint=p_towel, seed=53, weight=0.9, ao_floor=0.6))

    # the stovepipe: a collar on the cooktop, a straight pipe with a jointed elbow (brass collars over its two
    # joints) jogging back and out, and the rain cap sitting on the pipe's top
    bxp, byp = PIPE_BASE
    txp, typ = PIPE_TOP
    path = [(bxp, byp, TOP_Z1 - 0.02), (bxp, byp, PIPE_J0), (txp, typ, PIPE_J1), (txp, typ, CAP_Z0 + 0.004)]
    pipe = G.sweep(path, PIPE_R, 8)
    add(B.Part("pipe", pipe, paint=p_pipe, seed=61, weight=0.5))
    rc = PIPE_R + 0.02

    def collar(x, y, z):
        return G.translate(G.lathe([(PIPE_R - 0.002, z - 0.03), (rc, z), (PIPE_R - 0.002, z + 0.03)], 8), x, y, 0.0)
    base = G.translate(G.lathe([(PIPE_R + 0.02, TOP_Z1 - 0.005), (PIPE_R + 0.022, TOP_Z1 + 0.03),
                                (PIPE_R + 0.004, TOP_Z1 + 0.045)], 8), bxp, byp, 0.0)
    band = G.translate(G.lathe([(PIPE_R + 0.003, CAP_Z0 - 0.06), (PIPE_R + 0.016, CAP_Z0 - 0.04),
                                (PIPE_R + 0.003, CAP_Z0 - 0.015)], 8), txp, typ, 0.0)
    add(B.Part("pipe_brass", G.merge([base, collar(bxp, byp, PIPE_J0), collar(txp, typ, PIPE_J1), band]),
               paint=p_brass, seed=63, weight=0.4))
    hat = G.translate(G.lathe([(0.03, CAP_Z0 + 0.012), (CAP_R, CAP_Z0), (CAP_R * 0.92, CAP_Z0 + 0.016),
                               (0.0, CAP_Z1)], 8), txp, typ, 0.0)
    add(B.Part("pipe_cap", hat, paint=p_iron, seed=65, weight=0.5))

    # the kettle on the hob: blue enamel body and spout, cream lid, brass knob and handle, walnut grip
    k = _kettle()

    def place(m):
        return G.transform(m, G.mat_chain(G.mat_translate(KX, KY, TOP_Z1), G.mat_scale(KS)))
    body_k = place(k["body"])
    add(B.Part("kettle", body_k, paint=p_kettle, seed=71, weight=2.2,
               decals={0: P2.wrap_front(d_kettle_crest, 0.16)}))
    add(B.Part("kettle_spout", place(k["spout"]), paint=p_kettle, seed=73, weight=1.8))
    add(B.Part("kettle_lid", place(k["lid"]), paint=p_lid, seed=75, weight=1.0))
    add(B.Part("kettle_handle", place(G.merge([k["handle"], k["knob"]])), paint=p_brass, seed=77, weight=0.8))
    add(B.Part("kettle_grip", place(k["grip"]), paint=p_walnut, seed=79, weight=0.9))

    # a teacup on its saucer at the cooktop's front left corner, under the spout's side
    cup, saucer, tea = _teacup()
    cx, cy = CUP_AT
    p_cup, p_saucer, p_tea = cup_paints(TOP_Z1, CUP_AT)
    add(B.Part("teacup", G.translate(cup, cx, cy, TOP_Z1), paint=p_cup, seed=81, weight=1.2, ao_floor=0.75))
    add(B.Part("saucer", G.translate(saucer, cx, cy, TOP_Z1), paint=p_saucer, seed=83, weight=0.8, ao_floor=0.75))
    add(B.Part("tea", G.translate(tea, cx, cy, TOP_Z1), paint=p_tea, seed=85, weight=0.5, ao_floor=0.7))

    # collision: the stove and kettle under a gable roof (n.z 0.62), the stovepipe in a peaked prism on its
    # upper axis (roof n.z 0.62): both too steep to stand on
    d.collision = G.merge_hulls(G.hull_gable(0.8, 0.6, 0.72, 1.1), _peaked_prism(0.085, 1.6, 1.7, txp, typ))

    tip = k["tip"]
    tdir = k["dir"]
    steam_at = (KX + (tip[0] + tdir[0] * 0.005) * KS, KY + (tip[1] + tdir[1] * 0.005) * KS,
                TOP_Z1 + (tip[2] + tdir[2] * 0.005) * KS)
    d.particles = [
        # on the spout tip: the preset is born small, faintly visible and in a narrow cone, so the plume leaves
        # the spout instead of floating beside it
        EM.kettle_steam(steam_at),
        # the fire's flicker in the window: soft orange glows (the Steam puff, tinted; unlit, additive) born on
        # the bars' axis line just over the sill, spread across the window (the client draws a quad of +-scale,
        # spawned over width along X and length along Y), so every glow stays inside the window's lower half;
        # 0.04 at mid-life keeps what leans out of the door in a side view small
        B.ParticleDef((fx + 0.012, DOOR_Y, FIRE_Z), "Steam", flags=0x20001, blend=4, speed=0.04,
                      variation=0.4, latitude=0.15, gravity=-0.10, life=0.6, emission_rate=12.0,
                      width=0.0, length=0.16, colors=((255.0, 165.0, 70.0),) * 3, alphas=(0, 22000, 0),
                      scales=((0.03, 0.03), (0.04, 0.04), (0.02, 0.02))),
    ]
    return d
