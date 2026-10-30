"""19302 GrinderSW, the Stormwind coffee grinder, CAFE.SPEC.md section 5.8.1.

A hand-cranked burr grinder in walnut, polished brass and royal-blue enamel, shaped so a player names it at a
glance: a big glass hopper bulb heaped with warm roasted beans on top, a large brass crank wheel with a walnut
handle on a crank arm standing up past its top on the side (+Y, the barista's right hand), and a drawer full of
fresh grounds pulled half open at the front. Chunky Warcraft proportions: a walnut base board with a brass trim
strip, a tapered box of enamel panels framed in riveted brass with a gold lion medallion over the drawer (and lions
on the back and the other side), a brass burr housing with a copper band, a domed brass lid with a round gold knob,
a small glass jar of beans on the board beside the drawer and one big bean spilled in front of the wheel. 0.5 (Y) x
0.5 (X) x 0.85 yd, front (+X) toward the barista.

Deviations from the section 5.8.1 design, for recognizability and the readability rule (>= 0.06 yd):
- the crank wheel is 0.16 yd in radius (not 0.12), with a 0.06 yd rim tube and six 0.048 yd spokes, so it reads
  at 10 yd in the 3/4 views; a brass crank arm (0.036 thick) runs over one spoke from the hub out past the rim
  (70 degrees up from the front, to 0.22 from the axle), and the walnut handle sticks out sideways at its end,
  so the arm and grip read as a crank (not a ship's wheel) and stand in silhouette over the box line even when
  the wheel is seen edge-on from straight in front;
- the hopper and the jar are single glass shells drawn from both sides (the glass1 preset), so their far walls
  above the beans read as glass too;
- the box is royal-blue enamel framed in riveted brass on a 0.5 x 0.5 walnut base board (section 5.8.1: a walnut
  and brass box), the family look of the Royal Brass Engine;
- the box is 0.32 x 0.30 x 0.33 (not 0.35 cubed) and stands toward the back of the base board and to the
  barista's left, which makes room for the wheel at the side and the bean jar at the front;
- the hopper bulb is wider than the box (r 0.166) and the beans inside come up to its shoulder with a heaped top,
  so the dark bean mass shows through the glass from eye height;
- added: the grounds drawer (the café cue of "ground coffee here"), the lion medallion on the box front, a
  turned gold knob on the lid (a ball 0.07 across on a collar, EspressoSW's finial vocabulary; a spiked crown
  read as Orgrimmar spikes at game distance) and the spilled bean (charm; the bean is 0.075 yd long, exaggerated
  so it reads).
"""

import math

from .. import build as B
from .. import emblem as E
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "GrinderSW"
DISPLAY = 19302

ENAMEL = T.hexc("2E4E8C")
# a deeper, warmer brass for the wheel and the lid (thin and domed parts wash out to lemon in the plain brass)
WHEEL_BRASS = {"base": T.hexc("B87A18"), "light_c": T.hexc("FFD878"), "dark": T.hexc("4A2604"),
               "bounce": T.hexc("A0601A")}
GROUNDS = T.hexc("6A4024")
GLASS_ALPHA = 0.28                  # the glass body: section 5.2.5's 70-110 alpha range starts at 0.275

BOARD_H = 0.045                     # the walnut base board
BX, BY = -0.075, -0.07              # box centre (x, y)
BOX_W, BOX_D = 0.32, 0.30
BOX_Z0, BOX_Z1 = BOARD_H, 0.375
TAPER = 0.06
FRONT_X = BX + BOX_D / 2            # box front at its foot
NECK_Z = 0.462                      # where the glass hopper sits in the burr housing
HOP_TOP = 0.748                     # the hopper rim, under the lid
BEAN_TOP = 0.722                    # the top of the bean heap
LID_TOP = 0.797
WHEEL_R = 0.16
WHEEL_Y = 0.128                     # the wheel's plane (the thick rim clears the box side by 1 cm)
WHEEL_Z = 0.24
HANDLE_DEG = 70.0                   # the crank arm's angle, from +X toward +Z (up in silhouette)
ARM_LEN = 0.22                      # the crank arm: hub to the handle, past the rim (R 0.16)
DRAWER = dict(w=0.17, d=0.13, h=0.095, z0=0.062, out=0.07)     # well out: its face clears the jar at yaw -26
JAR = (0.192, -0.194)               # the bean jar, front left, in the board's corner (the drawer shows past it)
JAR_R, JAR_H = 0.056, 0.15
SPILLED = ((0.205, 0.035, BOARD_H + 0.0145), 25.0)   # one big bean spilled on the board: centre, turn about Z
BEAN_SIZE = (0.042, 0.026, 0.018)   # its half axes (a 6-sided ellipsoid: about 0.075 yd long)

# the hopper's outer wall, bottom to top (r, z)
HOPPER = [(0.068, NECK_Z), (0.125, 0.515), (0.152, 0.56), (0.166, 0.615), (0.166, 0.675),
          (0.157, 0.725), (0.148, HOP_TOP)]


# ----------------------------------------------------------------------------------------------- paints

def p_board(ctx, seed, p):
    """Walnut with a brass trim strip along the front edge."""
    c = T.g_wood(ctx, seed, {"kind": "walnut"})
    if ctx.chart == "+x" and ctx.t < 0.022:
        c = T.g_brass(ctx, seed + 3, {"streak": False})
        if ctx.t > 0.016:
            c = T.scale(c, 0.5)
    return c


def p_box(ctx, seed, p):
    """Enamel panels framed in brass (the espresso machine's family look): the frame covers the rounded edges
    and carries bold rivets, a dark inset line runs inside it. The top is brass, under the burr housing."""
    e = T.edge_dist(ctx)
    if ctx.chart == "+z":
        return T.g_brass(ctx, seed, {"streak": False, "patina": 0.1})
    frame = 0.034
    if e < frame:
        c = T.g_brass(ctx, seed, {"streak": True, "patina": 0.12})
        return T.frame_rivets(ctx, c, frame * 0.5, 0.1, 0.0125)
    c = T.g_enamel(ctx, seed + 5, {"color": ENAMEL, "chips": 1, "chip_r": 0.024, "gloss": 0.35})
    if e < frame + 0.009:
        c = T.scale(c, 0.5)
    return c


def p_housing(ctx, seed, p):
    """The burr housing: brass with a copper band round its waist and a painted shadow under the flange lip."""
    z = ctx.pos[2]
    if 0.408 <= z <= 0.432:
        c = T.g_copper(ctx, seed + 1, {"patina": 0.1})
        if z > 0.426:
            c = T.mix(c, T.hexc("FFC08A"), 0.35)
        elif z < 0.413:
            c = T.mix(c, T.hexc("3A1406"), 0.45)
        return c
    c = T.g_brass(ctx, seed, {"streak": True, "patina": 0.08, "hotspot": 0.8})
    d = (BOX_Z1 + 0.016) - z
    if 0.0 < d < 0.02 and math.hypot(ctx.n[0], ctx.n[1]) > 0.6:
        c = T.mix(c, T.scale(c, 0.45), (1.0 - d / 0.02) * 0.7)
    return c


def p_hopper(ctx, seed, p):
    """Clear glass with the painted streaks and darker rims of g_glass, at the thin end of the section 5.2.5
    body alpha (70-110) so the beans show; a brass band where it meets the burr housing."""
    if ctx.pos[2] < NECK_Z + 0.014:
        c = T.g_brass(ctx, seed, {"streak": False})
        return (c[0], c[1], c[2], 1.0)
    return T.g_glass(ctx, seed, {"tint": T.hexc("ECEEE6"), "alpha": GLASS_ALPHA})


def p_beans(ctx, seed, p):
    """Big roasted beans, lit brighter than the plain bean paint (the glass in front greys them, so they are
    painted a warm mid-brown) and brightest on the heap's top, seen through the lid gap."""
    c = T.saturate(T.g_beans(ctx, seed, {"size": 0.064}), 1.5)
    z = ctx.pos[2]
    c = T.scale(c, 1.0 + 0.4 * T.smoothstep(NECK_Z, BEAN_TOP, z))
    if ctx.n[2] > 0.5:
        c = T.mix(c, T.scale(c, 1.3), 0.4)
    return c


def p_gold(ctx, seed, p):
    return T.g_gold(ctx, seed, p)


def p_lid(ctx, seed, p):
    """A domed brass lid in the wheel's warm brass: a lit crown and a dark lip line where it overhangs the
    glass."""
    c = T.g_brass(ctx, seed, {"streak": True, "streak_k": 0.4, "patina": 0.08, "hotspot": 0.5,
                              "palette": WHEEL_BRASS})
    if ctx.pos[2] < HOP_TOP + 0.005:
        c = T.mix(c, T.hexc("3A2006"), 0.55)
    return c


def p_wheel(ctx, seed, p):
    """A deep, warm brass crank wheel (the thin rim would wash out to lemon with the plain brass highlights),
    the outer face of the rim a shade darker than its lit front, a gold hub."""
    x, y, z = ctx.pos
    if math.hypot(x - BX, z - WHEEL_Z) < 0.043:
        return T.g_gold(ctx, seed + 1, {"streak": False})
    c = T.g_brass(ctx, seed, {"streak": False, "patina": 0.06, "hotspot": 0.3, "palette": WHEEL_BRASS})
    if ctx.n[1] > 0.6:
        c = T.scale(c, 0.85)
    return c


def p_dark_walnut(ctx, seed, p):
    c = T.g_wood(ctx, seed, {"kind": "dark", "along": "t"})
    return T.mix(c, T.hexc("9A6640"), T.clamp01(ctx.n[2]) * 0.4)


def p_drawer(ctx, seed, p):
    """Walnut drawer: a raised panel on its front, the top heaped with fresh grounds inside a walnut rim. Only
    the front strip of the top (as far as the drawer is pulled out) is seen, so the mound is centred there."""
    if ctx.chart == "+z":
        out = DRAWER["out"]
        e = min(ctx.s, ctx.cw - ctx.s, ctx.ch - ctx.t)          # t runs toward the front (+X)
        if e < 0.012:
            return T.g_wood(ctx, seed, {"kind": "walnut"})
        # ground coffee: a soft mound, lit in the middle, with broad darker clumps (low frequency for the mips)
        cx, cy = ctx.cw / 2.0, ctx.ch - out * 0.5
        r = math.hypot((ctx.s - cx) / (cx - 0.012), (ctx.t - cy) / (out * 0.5 + 0.01))
        v = T.fbm(ctx.s * 30.0, ctx.t * 30.0, seed, 2)
        c = T.mix(T.scale(GROUNDS, 1.35), T.scale(GROUNDS, 0.7), T.smoothstep(0.2, 1.0, r))
        c = T.mix(c, T.scale(c, 0.72), T.smoothstep(0.5, 0.75, v) * 0.6)
        if e < 0.018:
            c = T.mix(c, T.hexc("1A0C04"), 0.6)
        return c
    c = T.g_wood(ctx, seed, {"kind": "walnut"})
    if ctx.chart == "+x":
        c = T.inset_panel(ctx, c, 0.018, 0.008)
    return c


def p_spilled_bean(ctx, seed, p):
    """The spilled bean: glossy dark brown, lit on top, with the dark crease along its back."""
    (cx, cy, cz), turn = SPILLED
    a = math.radians(turn)
    qx, qy, qz = ctx.pos[0] - cx, ctx.pos[1] - cy, ctx.pos[2] - cz
    lx = (qx * math.cos(a) + qy * math.sin(a)) / BEAN_SIZE[0]
    ly = (-qx * math.sin(a) + qy * math.cos(a)) / BEAN_SIZE[1]
    lz = qz / BEAN_SIZE[2]
    c = T.mix(T.hexc("2A1408"), T.hexc("6A3C1E"), T.clamp01(lz * 0.6 + 0.45))
    c = T.mix(c, T.hexc("B07C50"), T.smoothstep(0.55, 0.95, lz) * T.smoothstep(0.7, 0.0, abs(ly + 0.35)) * 0.4)
    if lz > 0.0 and abs(ly - 0.12 * math.sin(lx * 2.5)) < 0.17 and abs(lx) < 0.85:
        c = T.mix(c, T.hexc("140804"), 0.85)
    return c


def p_jar(ctx, seed, p):
    return T.g_glass(ctx, seed, {"tint": T.hexc("DCEEEA"), "alpha": GLASS_ALPHA})


def p_jar_lid(ctx, seed, p):
    return T.g_brass(ctx, seed, {"streak": True, "hotspot": 0.9})


# ---------------------------------------------------------------------------------------------- decals

def d_medallion(w, h):
    """The box front: a round gold lion medallion with a dark bevel ring, centred over the drawer."""
    img = T.Img(w, h, (0, 0, 0, 0))
    s = int(min(w, h) * 0.5)
    if s < 6:
        return img
    cx, cy = w // 2, int(h * 0.36)
    P2.ring(img, cx, cy, s * 0.5, s * 0.58, T.hexc("3A2006"))
    P2.ring(img, cx, cy, s * 0.46, s * 0.5, T.hexc("F6D676"))
    rel = E.render_relief("lion_head", int(s * 0.86), int(s * 0.86), P2.GOLD_RELIEF)
    P2.composite(img, rel, cx - rel.w // 2, cy - rel.h // 2)
    return img


def d_side_crest(w, h):
    """A gold lion on the back and left side panels."""
    img = T.Img(w, h, (0, 0, 0, 0))
    s = int(min(w, h) * 0.5)
    if s < 6:
        return img
    rel = E.render_relief("lion_head", s, s, P2.GOLD_RELIEF)
    P2.composite(img, rel, (w - s) // 2, (h - s) // 2)
    return img


# ------------------------------------------------------------------------------------------------ parts

def _wheel(R, r, n, hub_r, spoke_w, spoke_t):
    """geom.wheel without the faces nobody sees: a torus rim, n spokes without end caps (they run into the
    rim and the hub) and a hub with only its outer cap, in the XY plane with the outer side toward +Z."""
    rim = G.torus(R, r, 12, 4)
    bars = []
    L = R - r * 0.3 - hub_r * 0.6           # the open spoke ends sit 6 mm deep inside the rim's diamond tube
    for i in range(n):
        bar = G.box(spoke_w, L, spoke_t, faces="+y -y +z -z", z0=-spoke_t / 2)
        bar = G.translate(bar, hub_r * 0.6 + L / 2, 0.0, 0.0)
        bars.append(G.transform(bar, G.mat_rot_z(2 * math.pi * i / n + math.pi / 2)))
    hub = G.cylinder(hub_r, spoke_t * 1.8, 8, (False, True), z0=-spoke_t * 0.9)
    return G.merge([rim] + bars + [hub])


def _knob(z0):
    """The finial: a turned gold knob on the lid, a flared collar under a ball 0.07 across with a small pointed
    top (EspressoSW's turned-gold vocabulary; it reads as a round knob at 8-10 yd)."""
    prof = [(0.04, z0), (0.042, z0 + 0.008), (0.022, z0 + 0.018), (0.03, z0 + 0.03), (0.036, z0 + 0.046),
            (0.028, z0 + 0.064), (0.0, z0 + 0.074)]
    return G.lathe(prof, 8)


def _jar(r, h):
    """A low-poly bean jar (kit.jar's shape on 8 sides, fewer rings): straight glass walls with a rounded
    shoulder, the beans heaped inside to just under the shoulder, a domed brass screw lid."""
    glass = G.lathe([(0.0, 0.0), (r * 0.92, 0.0), (r, h * 0.08), (r, h * 0.8), (r * 0.86, h * 0.94),
                     (r * 0.84, h)], 8)
    ci = r * 0.88
    contents = G.lathe([(ci, 0.004), (ci, h * 0.72), (ci * 0.6, h * 0.8), (0.0, h * 0.83)], 8)
    lid = G.lathe([(r * 0.9, h - 0.008), (r * 0.92, h + 0.022), (r * 0.62, h + 0.03), (0.0, h + 0.031)], 8)
    return {"glass": glass, "contents": contents, "lid": lid}


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (0.5, 0.5, 0.85)
    d.budget = 1200
    d.kind = "machine"
    d.atlas = {"atlas": 256}
    d.max_height = 0.95
    d.sloped_top = True
    add = d.add

    # the walnut base board, brass trim strip along its front edge
    board = G.box(0.5, 0.5, BOARD_H, faces="+x -x +y -y +z")
    for ch in board.charts:
        ch.weight = {"+z": 0.55, "-x": 0.3}.get(ch.name, 0.7)
    add(B.Part("board", board, paint=p_board, seed=11))

    # the box: tapered, enamel panels in a riveted brass frame; the lion medallion over the drawer
    box = G.box(BOX_W, BOX_D, BOX_Z1 - BOX_Z0, 0.025, faces="+x -x +y -y +z", z0=BOX_Z0)
    box = G.translate(G.taper(box, TAPER, BOX_Z0, BOX_Z1), BX, BY, 0.0)
    for ch in box.charts:
        ch.weight = {"+x": 1.3, "-x": 0.5, "+z": 0.35}.get(ch.name, 0.9)
    add(B.Part("box", box, paint=p_box, seed=21,
               decals={"+x": d_medallion, "-y": d_side_crest, "-x": d_side_crest}))

    # the burr housing on the box: a flange, a bell narrowing to the hopper's neck, a copper waist band
    hz = BOX_Z1
    housing = G.lathe([(0.142, hz - 0.006), (0.142, hz + 0.014), (0.118, 0.398), (0.118, 0.426),
                       (0.09, 0.448), (0.07, NECK_Z + 0.006)], 12)
    add(B.Part("housing", G.translate(housing, BX, BY, 0.0), paint=p_housing, seed=31, weight=1.1))

    # the glass hopper bulb with the bean heap inside it (a real gap, so the glass reads as a shell)
    hopper = G.lathe(HOPPER, 14)
    add(B.Part("hopper", G.translate(hopper, BX, BY, 0.0), "glass1", paint=p_hopper, seed=41, weight=0.7))
    k = 0.92
    beans = [(0.062, NECK_Z + 0.008)] + [(r * k, z) for r, z in HOPPER[1:5]] + [(0.12, 0.703), (0.0, BEAN_TOP)]
    add(B.Part("beans", G.translate(G.lathe(beans, 10), BX, BY, 0.0), paint=p_beans, seed=43, weight=1.35,
               ao_floor=0.7))

    # the domed brass lid and its gold knob
    lid = G.lathe([(0.15, HOP_TOP - 0.008), (0.158, HOP_TOP + 0.006), (0.15, HOP_TOP + 0.02),
                   (0.09, LID_TOP - 0.006), (0.0, LID_TOP)], 14)
    add(B.Part("lid", G.translate(lid, BX, BY, 0.0), paint=p_lid, seed=51, weight=0.8))
    add(B.Part("finial", G.translate(_knob(LID_TOP - 0.004), BX, BY, 0.0), paint=p_gold, seed=53, weight=0.9,
               ao_floor=0.75))                  # the collar stays gold against the lid, not a dark ring

    # the crank wheel on the right-hand side (+Y): a 0.06 yd rim, six chunky spokes, a hub on a short axle into
    # the box, and a brass crank arm over one spoke out past the rim with the walnut handle at its end, so it
    # stands over the box line
    to_side = G.mat_chain(G.mat_translate(BX, WHEEL_Y, WHEEL_Z), G.mat_rot_x(-math.pi / 2))
    wheel = G.transform(_wheel(WHEEL_R, 0.03, 6, 0.04, 0.048, 0.03), to_side)
    axle = G.transform(G.cylinder(0.024, 0.085, 6, (True, False), z0=-0.032), G.mat_chain(
        G.mat_translate(BX, WHEEL_Y, WHEEL_Z), G.mat_rot_x(math.pi / 2)))      # from 1 cm inside the box to the hub
    a = math.radians(HANDLE_DEG)
    hx, hz2 = BX + math.cos(a) * ARM_LEN, WHEEL_Z + math.sin(a) * ARM_LEN
    ay = WHEEL_Y + 0.03                                              # the arm lies on the spokes' outer face
    arm = G.sweep([(BX, ay, WHEEL_Z), (hx, ay, hz2)], 0.018, 6, caps=(True, True), up=(0.0, 1.0, 0.0))
    add(B.Part("crank_wheel", G.merge([wheel, axle, arm]), paint=p_wheel, seed=61, weight=1.1))
    grip = G.transform(G.capsule(0.031, 0.108, 6), G.mat_chain(      # its end at y 0.26 sets the 0.51 width
        G.mat_translate(hx, WHEEL_Y + 0.024, hz2), G.mat_rot_x(-math.pi / 2)))
    add(B.Part("crank_handle", grip, paint=p_dark_walnut, seed=63, weight=1.0))

    # the grounds drawer, pulled half out of the box front, and its brass knob
    dw = DRAWER
    drawer = G.box(dw["w"], dw["d"], dw["h"], faces="+x +y -y +z", z0=dw["z0"])
    drawer = G.translate(drawer, FRONT_X + dw["out"] - dw["d"] / 2, BY, 0.0)
    for ch in drawer.charts:
        ch.weight = {"+z": 1.3, "+x": 1.1}.get(ch.name, 0.5)
    add(B.Part("drawer", drawer, paint=p_drawer, seed=71))
    knob = G.sphere(0.03, 6, 4)
    add(B.Part("drawer_knob", G.translate(knob, FRONT_X + dw["out"] + 0.018, BY, dw["z0"] + dw["h"] * 0.5),
               paint=p_gold, seed=73, weight=0.6, ao_floor=0.7))

    # a small glass jar of beans with a brass lid on the board beside the drawer
    jar = _jar(JAR_R, JAR_H)
    jx, jy = JAR
    add(B.Part("jar_beans", G.translate(jar["contents"], jx, jy, BOARD_H), paint=p_beans, seed=81, weight=0.9,
               ao_floor=0.7))
    add(B.Part("jar_lid", G.translate(jar["lid"], jx, jy, BOARD_H), paint=p_jar_lid, seed=83, weight=0.6))
    add(B.Part("jar", G.translate(jar["glass"], jx, jy, BOARD_H), "glass1", paint=p_jar, seed=85, weight=0.5))

    # a big roasted bean spilled on the board in front of the wheel
    (cx, cy, cz), turn = SPILLED
    sx, sy, sz = BEAN_SIZE
    bean = G.transform(G.sphere(sx, 6, 3), G.mat_chain(G.mat_translate(cx, cy, cz), G.mat_rot_z(math.radians(turn)),
                                                     G.mat_scale(1.0, sy / sx, sz / sx)))
    add(B.Part("spilled_bean", bean, paint=p_spilled_bean, seed=87, weight=1.4, ao_floor=0.75))

    # collision: walls to 0.5, a gable roof to 0.85 (roof n.z 0.58 < 0.6428: too steep to stand on)
    d.collision = G.hull_gable(0.5, 0.5, 0.5, 0.85)
    d.particles = []
    return d
