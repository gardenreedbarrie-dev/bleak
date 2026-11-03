"""19303 GrinderOrg, the Orgrimmar coffee grinder, CAFE.SPEC.md section 5.8.1.

A hand-cranked burr grinder in dark cast iron, red lacquer, bone and rough timber, shaped so a player names it at
a glance: a wide open iron funnel hopper on top (a flared spiked rim 0.4 across over a long cone narrowing into the
burr drum) with roasted beans heaped just over its rim, an L-shaped crank on the side (+Y, the barista's right
hand: an iron arm 0.25 long out of a spiked hub, a bone knob sticking out sideways at its end) turning in front of
a red saw-toothed gear guard, and a chute at the front pouring a stream of grounds into a timber catch tub.
Orcish proportions: a crooked plank base board, a squat riveted iron box with red lacquer panels carrying the
tusk crest in carved bone, a riveted burr drum with a red band and a goblin pressure gauge (needle in the red),
and two ivory tusks curving up out of the funnel's sides. The hopper leans 7 degrees toward the barista, crooked
as orc work is, which also turns the bean heap toward the viewer. 0.55 (Y) x 0.55 (X) x 0.9 yd, front (+X)
toward the barista.

Deviations from the section 5.8.1 design, for recognizability and the readability rule (>= 0.06 yd):
- the box is black iron with red lacquer panels carrying the tusk crest in bone relief on the front, the back and
  the left side (section 5.8.1: a cast-iron box with rivets), on a base board of three crooked timber planks;
- the funnel is tall (0.35, its rim at 0.79) so its cone reads from eye height, and painted in three bands: dark
  iron, a wide red hoop and bright worn iron under the lip; the beans rise only 0.05 over the rim (a heap higher
  than the funnel read as a brazier or a fruit bowl), with seven big single beans (0.09 yd long) lying on it;
- the crank is a real L: a heavy bright iron arm (0.25 long, 0.044 thick) leaning 55 degrees up toward the
  barista from a spiked hub, and a bone knob (0.115 long) at its end pointing out sideways, in silhouette from
  both 3/4 views; the 12-point saw star (r 0.17, teeth 0.06 deep, red lacquer with bright iron teeth) is the gear
  guard behind it;
- added: the two tusks on the funnel (the Orgrimmar silhouette at 30 yd), the chute, the falling stream of grounds
  and the timber catch tub (0.19 across, 0.075 tall), the goblin gauge and one big bean spilled on the board.
"""

import math

from .. import build as B
from .. import emblem as E
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "GrinderOrg"
DISPLAY = 19303

RED = T.hexc("B5402F")
DARK_RED = T.hexc("9C2A1F")
GROUNDS = T.hexc("6A4024")
BRIGHT_IRON = T.hexc("A8ACB4")

BOARD_H = 0.05
BX, BY = -0.06, -0.05               # box centre (x, y)
BOX_W, BOX_D = 0.31, 0.29
BOX_Z0, BOX_Z1 = BOARD_H, 0.37
TAPER = 0.05
FRONT_X = BX + BOX_D / 2            # box front at its foot
DRUM_Z1 = 0.44                      # the burr drum's top, where the funnel starts
RIM_Z = 0.79                        # the funnel's rim
RIM_R = 0.2
HEAP_TOP = 0.84                     # the beans rise 0.05 over the rim
TILT = math.radians(7.0)            # the hopper leans toward the barista (crooked orc work; the beans face front)
GEAR_R = 0.17
GEAR_ROOT = 0.11                    # the saw teeth's root: 0.06 yd deep teeth (the readability floor)
GEAR_T = 0.045                      # the gear guard's thickness
GEAR_Y = BY + BOX_W / 2 - 0.021     # the gear guard's back, set into the box side (no slit under the taper)
GEAR_Z = 0.215
CRANK_R = 0.25                      # the crank arm's length, hub to knob
CRANK_DEG = 55.0                    # the arm's angle from +X toward +Z (up toward the barista: a clear diagonal)
ARM_R = 0.022                       # the arm's radius (0.044 thick)
TUB = (0.18, BY)                    # the grounds tub on the board, under the chute
TUB_R, TUB_H = 0.095, 0.075
GROUNDS_Z = BOARD_H + TUB_H - 0.008     # the grounds' edge, just under the tub's rim
STREAM_TOP = 0.19                  # the stream's top end, on the chute's axis just inside its mouth

# the funnel's outer wall, bottom to top (r, z), ending in a rolled lip; the bean heap over its rim
FUNNEL = [(0.075, DRUM_Z1 - 0.008), (0.09, 0.48), (0.13, 0.6), (0.172, 0.71), (0.193, 0.765), (RIM_R + 0.01, RIM_Z),
          (RIM_R - 0.012, RIM_Z + 0.012)]
HEAP = [(RIM_R - 0.008, RIM_Z + 0.008), (0.16, 0.818), (0.1, 0.834), (0.0, HEAP_TOP)]
# big single beans: on the heap (angle round the hopper from +X in degrees, radius, turn of the bean's long axis
# from the slope), most of them on the front half and some near the top so they break the heap's outline, and
# spilled (model position, turn about Z); every one is a 0.09 yd ellipsoid
HEAP_BEANS = ((0.0, 0.04, 20.0), (25.0, 0.11, 70.0), (-25.0, 0.1, -30.0), (50.0, 0.15, 10.0),
              (-50.0, 0.155, 50.0), (110.0, 0.09, 30.0), (-120.0, 0.12, 60.0))
SPILLED_BEANS = (((0.215, 0.105, BOARD_H + 0.015), 30.0),)
BEAN_SIZE = (0.045, 0.03, 0.021)    # half axes of a big bean: long, side, up


def _heap_z(r):
    """The bean heap's height at radius r (upright frame) and its slope dz/dr (negative: it falls outward)."""
    for (r0, z0), (r1, z1) in zip(HEAP, HEAP[1:]):
        if r1 <= r <= r0:
            return z1 + (z0 - z1) * (r - r1) / ((r0 - r1) or 1.0), (z0 - z1) / ((r0 - r1) or 1.0)
    return HEAP[0][1], 0.0


def _leaned(p, direction=False):
    """A point (or a direction) of the hopper's upright frame in model space: turned by TILT about the Y axis
    through (BX, DRUM_Z1)."""
    c, s = math.cos(TILT), math.sin(TILT)
    if direction:
        return (c * p[0] + s * p[2], p[1], -s * p[0] + c * p[2])
    dx, dz = p[0] - BX, p[2] - DRUM_Z1
    return (BX + c * dx + s * dz, p[1], DRUM_Z1 - s * dx + c * dz)


def _bean_frames():
    """(centre, long axis, side axis, up axis) of every big bean in model space."""
    out = []
    for deg, r, turn in HEAP_BEANS:
        a, t = math.radians(deg), math.radians(turn)
        z, slope = _heap_z(r)
        radial = (math.cos(a), math.sin(a), 0.0)
        tangent = (-math.sin(a), math.cos(a), 0.0)
        down = G.norm((radial[0], radial[1], slope))         # down the heap's slope
        up = G.norm(G.cross(tangent, down))
        if up[2] < 0:
            up = G.mul(up, -1.0)
        long_ = G.norm(G.add(G.mul(down, math.cos(t)), G.mul(tangent, math.sin(t))))
        centre = (BX + radial[0] * r, BY + radial[1] * r, z + BEAN_SIZE[2] * 0.6)
        long_, up = _leaned(long_, True), _leaned(up, True)
        out.append((_leaned(centre), long_, G.cross(up, long_), up))
    for centre, turn in SPILLED_BEANS:
        t = math.radians(turn)
        long_ = (math.cos(t), math.sin(t), 0.0)
        out.append((centre, long_, (-long_[1], long_[0], 0.0), (0.0, 0.0, 1.0)))
    return out


BEAN_FRAMES = _bean_frames()


# ----------------------------------------------------------------------------------------------- paints

def _upright(ctx):
    """The texel's position and normal with the hopper's lean taken out (paints of the tilted parts are laid
    out in the hopper's own frame)."""
    x, y, z = ctx.pos
    dx, dz = x - BX, z - DRUM_Z1
    c, s = math.cos(TILT), math.sin(TILT)
    n = ctx.n
    return ((BX + c * dx - s * dz, y, DRUM_Z1 + s * dx + c * dz),
            (c * n[0] - s * n[2], n[1], s * n[0] + c * n[2]))


def p_board(ctx, seed, p):
    return T.g_planks(ctx, seed, {"kind": "timber", "count": 1, "nails": True, "ragged": 0.02})


def p_box(ctx, seed, p):
    """Hammered black iron with a riveted frame round red lacquer panels (the crests go on them); the right
    side stays black iron so the red gear guard stands out on it, and the top is plain iron under the drum."""
    if ctx.chart == "+z":
        return T.g_iron(ctx, seed, {"rust": 0.15})
    c = T.g_hammered_iron(ctx, seed, {"rust": 0.12, "dent": 0.05})
    e = T.edge_dist(ctx)
    frame = 0.036
    if ctx.chart != "+y" and e > frame:
        c = T.g_lacquer(ctx, seed + 7, {"color": RED, "worn": 0.5})
        if e < frame + 0.01:
            c = T.mix(c, T.hexc("1A0A06"), 0.6)
        return c
    if e < frame:
        c = T.frame_rivets(ctx, T.scale(c, 1.08), frame * 0.5, 0.09, 0.0135, T.IRON_RIVET_HI, T.IRON_RIVET_LO)
    return c


def p_drum(ctx, seed, p):
    """The riveted burr drum: iron with a dark red lacquer band round its middle and a rivet row on its rim."""
    z = ctx.pos[2]
    if 0.403 <= z <= 0.43 and math.hypot(ctx.n[0], ctx.n[1]) > 0.6:
        c = T.g_lacquer(ctx, seed + 3, {"color": DARK_RED, "worn": 0.6})
        if z < 0.408 or z > 0.425:
            c = T.scale(c, 0.55)
        return c
    c = T.g_iron(ctx, seed, {"rust": 0.2})
    if math.hypot(ctx.n[0], ctx.n[1]) > 0.6 and z < 0.4:
        phi = math.atan2(ctx.pos[1] - BY, ctx.pos[0] - BX)
        step = 2 * math.pi / 14
        da = (((phi + step / 2) % step) - step / 2) * 0.145
        c = T.rivet_dot(c, da, 0.375 - z, 0.0125, T.IRON_RIVET_HI, T.IRON_RIVET_LO)
    return c


def p_funnel(ctx, seed, p):
    """The iron funnel in three value bands, so it is not one black cone: dark hammered iron below, a wide red
    lacquer hoop round its middle, and bright iron worn by the scoop under the rolled lip, with a rivet row."""
    (x, y, z), n = _upright(ctx)
    c = T.g_hammered_iron(ctx, seed, {"rust": 0.25, "dent": 0.05})
    # the cone's wall faces down and out, into metal()'s dark horizon band: lifted toward a mid iron, with a
    # broad lit streak toward the key light, so the cone keeps its shape from eye height and at night
    c = T.mix(c, T.hexc("7C8088"), 0.3 + 0.25 * T._azimuth_streak(n, 0.55, 0.6))
    if z > RIM_Z - 0.012:
        return T.mix(c, BRIGHT_IRON, 0.4 * T.clamp01(n[2] + 0.6))
    if z > RIM_Z - 0.04:
        c = T.mix(c, BRIGHT_IRON, 0.35)
        if z < RIM_Z - 0.036:
            c = T.scale(c, 0.6)
        phi = math.atan2(y - BY, x - BX)
        step = 2 * math.pi / 16
        da = (((phi + step / 2) % step) - step / 2) * 0.19
        return T.rivet_dot(c, da, RIM_Z - 0.022 - z, 0.0125, T.IRON_RIVET_HI, T.IRON_RIVET_LO)
    if 0.62 <= z <= 0.69:
        c = T.g_lacquer(ctx, seed + 3, {"color": RED, "worn": 0.5})
        if z < 0.626 or z > 0.684:
            c = T.scale(c, 0.5)
    return c


def p_beans(ctx, seed, p):
    """Big roasted beans heaped over the rim, a warm mid-brown that stands out from the iron (the near-black
    gaps between the beans lifted to a dark roast brown, so the heap stays light at 15 yd), a little darker
    toward the rim."""
    c = T.mix(T.saturate(T.g_beans(ctx, seed, {"size": 0.074}), 0.76), T.hexc("4A2812"), 0.2)
    (_x, _y, z), _n = _upright(ctx)
    return T.scale(c, 1.1 + 0.2 * T.smoothstep(RIM_Z, HEAP_TOP, z))


def p_big_bean(ctx, seed, p):
    """A single big roasted bean: glossy warm brown, lit on its upper side, with the dark centre crease along
    its long axis on top."""
    x, y, z = ctx.pos
    best = min(BEAN_FRAMES, key=lambda f: (x - f[0][0]) ** 2 + (y - f[0][1]) ** 2 + (z - f[0][2]) ** 2)
    c0, lg, sd, up = best
    q = (x - c0[0], y - c0[1], z - c0[2])
    ly, lz = G.dot(q, sd) / BEAN_SIZE[1], G.dot(q, up) / BEAN_SIZE[2]
    lx = G.dot(q, lg) / BEAN_SIZE[0]
    c = T.mix(T.hexc("3A1E0E"), T.hexc("7A4626"), T.clamp01(lz * 0.6 + 0.45))
    c = T.mix(c, T.hexc("C8935E"), T.smoothstep(0.55, 0.95, lz) * T.smoothstep(0.7, 0.0, abs(ly + 0.35)) * 0.4)
    if lz > 0.0 and abs(ly - 0.12 * math.sin(lx * 2.5)) < 0.17 and abs(lx) < 0.85:
        c = T.mix(c, T.hexc("140804"), 0.85)
    return c


def p_chute(ctx, seed, p):
    """The iron chute; its open mouth (the end cap) is dark inside, full of grounds."""
    c = T.g_iron(ctx, seed, {"rust": 0.2})
    if ctx.chart.endswith("_cap"):
        d = math.hypot(ctx.s - ctx.cw / 2, ctx.t - ctx.ch / 2) / (ctx.cw / 2)
        return T.mix(T.scale(GROUNDS, 0.45), c, T.smoothstep(0.6, 0.85, d))
    return c


def p_crank(ctx, seed, p):
    """The crank: iron worn bright by the hand (lighter than the box), so the arm reads against the red gear."""
    c = T.g_iron(ctx, seed, {"rust": 0.05})
    return T.mix(c, T.hexc("B4B8C0"), 0.3 + 0.2 * T.clamp01(ctx.n[2]))


def p_spike(ctx, seed, p):
    """Iron spikes with bright, filed tips."""
    c = T.g_iron(ctx, seed, {"rust": 0.1})
    return T.mix(c, T.hexc("C8CCD4"), T.smoothstep(0.35, 0.0, ctx.v) * 0.45)


def p_gear(ctx, seed, p):
    """The saw-star gear guard in red lacquer, its teeth worn to bright iron (the saw outline then separates
    from the red box at 8-15 yd) behind a dark line, with a painted iron hub ring."""
    x, z = ctx.pos[0] - BX, ctx.pos[2] - GEAR_Z
    r = math.hypot(x, z)
    if r > GEAR_ROOT + 0.005:
        return T.mix(T.g_iron(ctx, seed + 2, {"rust": 0.1}), BRIGHT_IRON, 0.5)
    c = T.g_lacquer(ctx, seed, {"color": RED, "worn": 0.6})
    if r > GEAR_ROOT - 0.005:
        c = T.mix(c, T.hexc("2C2826"), 0.6)
    elif r < 0.07 and ctx.chart.endswith("_front"):
        c = T.g_iron(ctx, seed + 1, {"rust": 0.1})
        if r > 0.058:
            c = T.scale(c, 0.55)
    return c


def p_bone(ctx, seed, p):
    return T.g_bone(ctx, seed, {"root": 0, "cracks": 2})


def p_grip(ctx, seed, p):
    """The bone grip with two dark leather wraps."""
    c = T.g_bone(ctx, seed, {"kind": "bone", "cracks": 1})
    if 0.22 < ctx.v < 0.3 or 0.7 < ctx.v < 0.78:
        c = T.mix(T.hexc("4A2A18"), T.hexc("7A4A2A"), T.clamp01(ctx.n[2] + 0.5))
    return c


def p_tub(ctx, seed, p):
    """The grounds tub: straight rough timber staves with dark gaps and end grain on the rim, bound by one
    black iron hoop with a lit upper edge and painted rivets."""
    c = T.g_planks(ctx, seed, {"kind": "timber", "along": "t", "width": 0.055, "gap": 0.006, "ragged": 0.0,
                               "knots": 0})
    x, y, z = ctx.pos
    rx, ry = x - TUB[0], y - TUB[1]
    rr = math.hypot(rx, ry) or 1.0
    outward = (ctx.n[0] * rx + ctx.n[1] * ry) / rr
    hz = BOARD_H + TUB_H * 0.45            # the hoop's middle
    if outward > 0.5 and abs(z - hz) <= 0.012:
        c = T.g_iron(ctx, seed + 1, {"rust": 0.25})
        if z > hz + 0.008:
            c = T.mix(c, BRIGHT_IRON, 0.4)
        elif z < hz - 0.008:
            c = T.scale(c, 0.55)
        phi = math.atan2(ry, rx)
        step = 2 * math.pi / 10
        da = (((phi + step / 2) % step) - step / 2) * TUB_R
        c = T.rivet_dot(c, da, hz - z, 0.0065, T.IRON_RIVET_HI, T.IRON_RIVET_LO)
    elif ctx.n[2] > 0.7:
        c = T.mix(c, T.hexc("C49868"), 0.25)           # the end grain on the rim, lit
    return c


def p_grounds(ctx, seed, p):
    """Fresh coarse grounds, nearly flat in the tub: broad darker clumps, coarse light specks, and a shadow
    where they meet the staves."""
    x, y, _z = ctx.pos
    v = T.fbm(x * 30.0, y * 30.0, seed, 2)
    c = T.mix(T.scale(GROUNDS, 1.2), T.scale(GROUNDS, 0.8), T.smoothstep(0.4, 0.75, v))
    sp = T.fbm(x * 70.0 + 31.0, y * 70.0 + 17.0, seed + 5, 1)
    c = T.mix(c, T.hexc("9A6A40"), T.smoothstep(0.62, 0.74, sp) * 0.8)
    rr = math.hypot(x - TUB[0], y - TUB[1])
    return T.mix(c, T.scale(c, 0.55), T.smoothstep(TUB_R - 0.03, TUB_R - 0.01, rr))


def p_stream(ctx, seed, p):
    """The falling stream of grounds: streaky warm brown, lighter down its lit side, and darker in its top 30%
    where it leaves the chute's shadowed mouth (so it reads as pouring out, not as a cone standing in the tub)."""
    c = T.mix(GROUNDS, T.scale(GROUNDS, 0.7), T.smoothstep(0.4, 0.7, T.noise(ctx.s * 60.0, ctx.t * 12.0, seed)))
    c = T.mix(c, T.hexc("9A6A40"), T.clamp01(ctx.n[0] * 0.5 + ctx.n[1] * 0.2) * 0.35)
    k = T.smoothstep(STREAM_TOP - 0.03, STREAM_TOP - 0.012, ctx.pos[2])
    return T.mix(c, T.scale(c, 0.55), k)


def p_gauge_case(ctx, seed, p):
    return T.g_brass(ctx, seed, {"streak": True, "patina": 0.3})


# ---------------------------------------------------------------------------------------------- decals

def d_crest(w, h):
    """The tusk crest in carved bone on the box's red lacquer front (ivory tusks on red read as tusks at 8 yd;
    iron relief read as a cage), in its upper part (the chute and the tub cover the bottom)."""
    img = T.Img(w, h, (0, 0, 0, 0))
    s = int(min(w * 0.72, h * 0.52))
    if s < 6:
        return img
    rel = E.render_relief("tusk_crest", s, s, P2.BONE_RELIEF)
    P2.composite(img, rel, (w - s) // 2, int(h * 0.05))
    return img


def d_side_crest(w, h):
    """A smaller bone tusk crest centred on the left and back panels."""
    img = T.Img(w, h, (0, 0, 0, 0))
    s = int(min(w, h) * 0.55)
    if s < 6:
        return img
    rel = E.render_relief("tusk_crest", s, s, P2.BONE_RELIEF)
    P2.composite(img, rel, (w - s) // 2, (h - s) // 2)
    return img


def d_gauge(w, h):
    """A goblin gauge: the needle hard in the red."""
    return P2.gauge_face(w, h, {"needle_deg": 105.0, "numbers": False,
                                "bands": [(0.0, 0.4, T.hexc("4FA04A")), (0.4, 0.7, T.hexc("E8C030")),
                                          (0.7, 1.0, T.hexc("C83A28"))]})


# ------------------------------------------------------------------------------------------------ parts

def _boards(w, d, h, n, gap, seed, ragged, wobble_amp):
    """geom.planks with the boards running front to back (axis "x"), but without their undersides (they lie on
    the bar top, nobody sees them) and with the wobbled bottoms clamped to z 0."""
    out = []
    bw = (w - gap * (n - 1)) / n
    for i in range(n):
        c = -w / 2 + bw / 2 + i * (bw + gap)
        b = G.translate(G.box(bw, d, h, faces="+x -x +y -y +z"), 0.0, c, 0.0)
        b = G.plank_edges(b, seed + 7 * i, ragged, "x", inward=True)
        b = G.wobble(b, wobble_amp, seed + 13 * i)
        b.p = [(x, y, max(0.0, z)) for x, y, z in b.p]
        out.append(b)
    return G.merge(out)


def _along_y(mesh_z, x, y, z):
    """A mesh built along +Z, turned to point along +Y and moved to (x, y, z)."""
    return G.transform(mesh_z, G.mat_chain(G.mat_translate(x, y, z), G.mat_rot_x(-math.pi / 2)))


def _bean(frame):
    """One big bean at its real size: an ellipsoid lathe round its long axis (so its chart is measured on the
    bean itself), squashed to its height and laid along the frame (centre, long, side, up)."""
    (cx, cy, cz), lg, sd, up = frame
    L, S, U = BEAN_SIZE
    prof = [(math.cos(-math.pi / 2 + math.pi * k / 3) * S, math.sin(-math.pi / 2 + math.pi * k / 3) * L)
            for k in range(4)]
    prof[0], prof[-1] = (0.0, -L), (0.0, L)
    m = ((sd[0], up[0], lg[0], cx), (sd[1], up[1], lg[1], cy), (sd[2], up[2], lg[2], cz))
    return G.transform(G.lathe(prof, 6, angle=89.0), G.mat_chain(m, G.mat_scale(1.0, U / S, 1.0)))


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (0.55, 0.55, 0.9)
    d.budget = 1200
    d.kind = "machine"
    d.atlas = {"atlas": 256}
    d.max_height = 0.95
    d.sloped_top = True
    add = d.add

    # the base board: three crooked timber planks running front to back
    board = _boards(0.55, 0.55, BOARD_H, 3, gap=0.012, seed=5, ragged=0.018, wobble_amp=0.003)
    for ch in board.charts:
        ch.weight = {"+z": 0.6}.get(ch.name, 0.35)
    add(B.Part("board", board, paint=p_board, seed=11))

    # the box: squat cast iron, a little tapered and crooked, riveted frame, a red lacquer front with the crest
    box = G.box(BOX_W, BOX_D, BOX_Z1 - BOX_Z0, 0.03, faces="+x -x +y -y +z", z0=BOX_Z0)
    box = G.wobble(G.taper(box, TAPER, BOX_Z0, BOX_Z1), 0.006, seed=21)
    box = G.translate(box, BX, BY, 0.0)
    for ch in box.charts:
        ch.weight = {"+x": 1.8, "-x": 0.45, "+z": 0.3}.get(ch.name, 0.85)
    add(B.Part("box", box, paint=p_box, seed=21, decals={"+x": d_crest, "-y": d_side_crest, "-x": d_side_crest}))

    # the burr drum on the box, and the funnel hopper rising out of it
    drum = G.lathe([(0.15, BOX_Z1 - 0.008), (0.15, 0.392), (0.128, 0.402), (0.128, 0.43), (0.095, DRUM_Z1)], 12)
    add(B.Part("drum", G.translate(drum, BX, BY, 0.0), paint=p_drum, seed=31, weight=1.0))
    lean = G.mat_chain(G.mat_translate(BX, BY, DRUM_Z1), G.mat_rot_y(TILT), G.mat_translate(0.0, 0.0, -DRUM_Z1))
    funnel = G.wobble(G.lathe(FUNNEL, 12), 0.004, seed=33)
    add(B.Part("funnel", G.transform(funnel, lean), paint=p_funnel, seed=33, weight=1.0))

    # the bean heap, overflowing the rim, and the big single beans on it (and the one spilled on the board)
    heap = G.wobble(G.lathe(HEAP, 12), 0.008, seed=41, freq=9.0)
    add(B.Part("beans", G.transform(heap, lean), paint=p_beans, seed=41, weight=1.35, ao_floor=0.7))
    big = G.merge([_bean(f) for f in BEAN_FRAMES])
    add(B.Part("big_beans", big, paint=p_big_bean, seed=47, weight=1.4, ao_floor=0.75))

    # the spiked rim: six iron spikes at the front, the back and the four diagonals (the tusks take the sides)
    spikes = []
    for deg in (0.0, 55.0, 125.0, 180.0, 235.0, 305.0):
        a = math.radians(deg)
        radial = (math.cos(a), math.sin(a), 0.0)
        base = (radial[0] * (RIM_R - 0.004), radial[1] * (RIM_R - 0.004), RIM_Z - 0.004)
        tilt = 0.85
        direction = (radial[0] * math.cos(tilt), radial[1] * math.cos(tilt), math.sin(tilt))
        spikes.append(G.spike(base, direction, 0.034, 0.085))
    add(B.Part("rim_spikes", G.transform(G.merge(spikes), lean), paint=p_spike, seed=43, weight=0.7))

    # two ivory tusks curving up out of the funnel's sides, outside the rim, tips turned in over the beans
    tusks = []
    for s in (1, -1):
        root = (-0.01, s * 0.155, 0.68)
        tip = (0.0, s * 0.15, 0.906)
        tusks.append(G.horn(root, tip, (0.0, s * 1.0, -0.2), 0.32, 0.046, 0.0, steps=5, sides=6))
    add(B.Part("tusks", G.transform(G.merge(tusks), lean), paint=p_bone, seed=45, weight=0.9))

    # the gear guard on the right-hand side (+Y): a thick 12-point saw star, red with bright iron teeth
    star = G.extrude(G.star_polygon(12, GEAR_R, GEAR_ROOT), GEAR_T)
    gear = G.transform(star, G.mat_chain(G.mat_translate(BX, GEAR_Y, GEAR_Z), G.mat_extrude_facing((0, 1, 0))))
    add(B.Part("gear_guard", gear, paint=p_gear, seed=51, weight=1.0))

    # the crank, an L in front of the gear guard: a spiked iron hub, a heavy bright arm leaning up toward the
    # barista, and the bone knob at its end pointing out sideways (in silhouette from both 3/4 views)
    hy = GEAR_Y + GEAR_T
    hub = _along_y(G.cylinder(0.042, 0.05, 8, (False, True)), BX, hy, GEAR_Z)
    a = math.radians(CRANK_DEG)
    ay = hy + 0.02
    ex, ez = BX + math.cos(a) * CRANK_R, GEAR_Z + math.sin(a) * CRANK_R
    arm = G.sweep([(BX, ay, GEAR_Z), (ex, ay, ez)], ARM_R, 6, caps=(True, True), up=(0.0, 1.0, 0.0))
    add(B.Part("crank", G.merge([hub, arm]), paint=p_crank, seed=53, weight=1.0))
    nut = G.spike((BX, ay + ARM_R - 0.004, GEAR_Z), (0.0, 1.0, 0.0), 0.03, 0.07)
    add(B.Part("crank_spike", nut, paint=p_spike, seed=55, weight=0.6))
    grip = _along_y(G.capsule(0.032, 0.115, 6, rings=2), ex, ay + 0.015, ez)    # its end at y 0.279 sets the width
    add(B.Part("crank_grip", grip, paint=p_grip, seed=57, weight=1.0))

    # the chute out of the box front, sloping down over the tub, and the stream of grounds falling from its
    # mouth into the timber tub
    tx, ty = TUB
    chute = G.sweep([(FRONT_X - 0.03, BY, 0.225), (FRONT_X + 0.025, BY, 0.218), (tx - 0.012, BY, 0.186)], 0.03,
                    6, caps=(False, True))
    add(B.Part("chute", chute, paint=p_chute, seed=61, weight=1.3))     # the dark mouth gets 5 texels
    # (the stream's open ends sit under the grounds and inside the chute; 0.068 to 0.052 yd across, a column
    # of grounds rather than a cone)
    stream = G.sweep([(tx, ty, GROUNDS_Z - 0.008), (tx - 0.015, ty, STREAM_TOP)], lambda t: 0.034 - 0.008 * t, 6)
    add(B.Part("stream", stream, paint=p_stream, seed=67, weight=1.0, ao_floor=0.8))
    tub = G.lathe([(TUB_R - 0.008, BOARD_H), (TUB_R, BOARD_H + TUB_H), (TUB_R - 0.012, BOARD_H + TUB_H),
                   (TUB_R - 0.012, GROUNDS_Z - 0.002)], 8)
    add(B.Part("tub", G.translate(tub, tx, ty, 0.0), paint=p_tub, seed=63, weight=1.1, ao_floor=0.7))
    grounds = G.lathe([(TUB_R - 0.011, GROUNDS_Z), (0.0, GROUNDS_Z + 0.005)], 8)
    add(B.Part("grounds", G.translate(grounds, tx, ty, 0.0), paint=p_grounds, seed=65, weight=1.2,
               ao_floor=0.75))

    # a goblin pressure gauge on the drum, facing the barista and turned a little toward the crank side
    gdir = G.norm((1.0, 0.45, 0.25))
    gc = (BX + gdir[0] * 0.12, BY + gdir[1] * 0.12, 0.415)
    m = G.mat_chain(G.mat_translate(*gc), G.mat_disc_facing(gdir))
    case = G.transform(G.cylinder(0.055, 0.035, 8, (False, True)), m)
    add(B.Part("gauge", case, paint=p_gauge_case, seed=71, decals={"cyl_top": d_gauge}, weight=2.0))

    # collision: walls to 0.5, a gable roof to 0.9 (roof n.z 0.57 < 0.6428: well clear of walkable)
    d.collision = G.hull_gable(0.55, 0.55, 0.5, 0.9)
    d.particles = []
    return d
