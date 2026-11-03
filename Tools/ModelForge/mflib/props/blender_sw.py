"""19304 BlenderSW, the Gnomish Whirligig (Stormwind milkshake blender), CAFE.SPEC.md section 5.8.1.

A countertop milkshake blender in polished copper and brass, royal-blue enamel and walnut, shaped so a player
names it at a glance: a tall flared glass jar, three-quarters full of pink shake under a pale froth crown, with a
big walnut grip on brass straps at its side (+Y, the barista's right hand), standing in a knurled brass collar on
a chunky tapered motor base with two big brass control knobs on cream dial scales at the front. Gnomish charm on
top: a two-blade brass propeller with royal-blue tips spins over the lid behind a copper nose cone, a toy
plane's nose. Chunky Warcraft proportions: a walnut base board with a brass trim strip, the base's blue enamel
panels framed in riveted copper (the espresso machine and grinder family look) with a gold lion medallion on each
side panel, a domed blue enamel lid on a brass rim. 0.35 (Y) x 0.35 (X) x 0.7 yd, front (+X) toward the barista.

Deviations from the section 5.8.1 design, for recognizability and the readability rule (>= 0.06 yd):
- the jar takes half the height (0.34 yd, r 0.09 flaring to 0.123) and the shake fills it to 0.5, so the pink
  mass is the biggest colour on the model; the grip (8 sides, r 0.033, so 0.061-0.066 across from every side,
  0.26 long) sticks out sideways on chunky brass straps (0.05 x 0.06, riveted, in the collar's darker brass) so
  the jar reads as a blender jug from the front as well as from the 3/4 views;
- the base is royal-blue enamel panels in a riveted copper frame, not a plain copper base: the Stormwind blue
  makes it read as the espresso machine's sibling, and the copper frame keeps the design's copper;
- the two brass dials are chunky knobs (r 0.037) on painted cream dial scales (r 0.054) with bold ticks, so the
  base reads as an appliance's control panel; the knobs point at different speeds;
- the propeller is upright and faces the barista square (a toy plane's propeller: span 0.30, leaf-shaped
  blades 0.03 wide at the root, 0.068 past mid-length, tapering to a round blue tip, at an 8 degree pitch), so
  its two blades read face-on at eye height instead of edge-on and the 3/4 views see its nose cone's point from
  the side; the polished copper nose cone (0.07-0.076 across, wider than the blade roots, with a gold tip) gives
  the hub a colour and a bulge of its own, so the propeller does not read as a gold bow tie on the lid; the
  pitch is shallow so both blades face the sun (at 25 degrees one blade turned into its own shadow and the
  propeller read as a gold-and-black smudge); it is level, because a tilted one would dip into the lid under the
  0.7 height, and the crown is flattened to 0.638 so the nose cone clears it;
- the collision is a gable-topped box (section 5.2.6: every machine has a sloped or peaked top), not a flat box;
- the glass body is alpha 0.28 (71, the bottom of section 5.2.5's 70-110), the clearest the rule allows, so
  the pink shows through it at every distance;
- added: the walnut base board (the family look), the knurled brass collar the jar locks into, the lion
  medallions (0.14 yd), the pale froth crown on the shake and two painted measuring ticks on the glass (0.024
  tall, about 3 texels: close-range charm that fades to a pale smudge past about 8 yd).
"""

import math

from .. import build as B
from .. import emblem as E
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "BlenderSW"
DISPLAY = 19304

ENAMEL = T.hexc("2E4E8C")

BOARD_H = 0.04                      # the walnut base board
BOARD_SINK = 0.01 * (1.0 - math.sqrt(0.5))   # its rounded lower edge would float this far over the bar
BASE_W = 0.32                       # the motor base's foot (square)
BASE_Z0, BASE_Z1 = BOARD_H, 0.235
TAPER = 0.12
FRAME = 0.032                       # the copper frame round the base's enamel panels
COLLAR_Z1 = 0.282                   # the brass collar's top, where the jar stands
JAR = [(0.088, 0.262), (0.09, 0.285), (0.112, 0.53), (0.12, 0.585), (0.123, 0.598)]   # the glass wall (r, z)
SHAKE_TOP = 0.505
LID_Z0, LID_RIM, LID_TOP = 0.592, 0.616, 0.638   # the lid's foot, the top of its brass rim band, its crown
PROP_Z = 0.678                      # the propeller's hub (its nose cone clears the crown)
PROP_TWIST = 8.0                    # each blade's pitch about its own length (shallow: both blades catch the sun)
PROP_YAW = 0.0                      # the propeller faces the barista square (the 3/4 views see the nose's point)
PROP_AXIS = (math.cos(PROP_YAW), math.sin(PROP_YAW), 0.0)
BLADE_L = 0.15                      # each blade's length from the hub
BLADE_ROOT, BLADE_W = 0.03, 0.068  # its width at the root and at its widest, past mid-length
NOSE_R, NOSE_L = 0.038, 0.065       # the copper nose cone (8 sides: 0.07 across the flats, wider than the
                                    # blade roots, so the hub bulges like a plane's spinner instead of pinching)
GRIP_Y = 0.155                      # the walnut grip's axis
GRIP_R = 0.033
GRIP_Z0, GRIP_Z1 = 0.302, 0.562
STRAPS = (0.36, 0.505)              # the brass straps' centres (their corners stay inside the grip's round ends)
STRAP_W, STRAP_H = 0.05, 0.06
STRAP_BRASS = dict(light_c=T.hexc("F0D27A"), base=T.hexc("B8902E"), dark=T.hexc("4A2A06"), bounce=T.hexc("8E6420"))
KNOB_YS = (-0.066, 0.066)           # the knobs' centres along the base front (untapered), right knob +Y
KNOB_Z = 0.13
KNOB_R = 0.037
DIAL_R = 0.054                      # the cream dial scale round each knob
KNOB_DEG = (-50.0, 65.0)            # each knob's pointer, clockwise from up (seen from the front)


def _taper_at(z):
    return 1.0 - TAPER * (z - BASE_Z0) / (BASE_Z1 - BASE_Z0)


LEAN = math.atan(BASE_W / 2 * TAPER / (BASE_Z1 - BASE_Z0))   # the base front leans back by this much


def _knob_frames():
    """(centre on the base front, axis, up, right) of each knob in model space."""
    f = _taper_at(KNOB_Z)
    axis = (math.cos(LEAN), 0.0, math.sin(LEAN))
    up = (-math.sin(LEAN), 0.0, math.cos(LEAN))
    return [((BASE_W / 2 * f, ys * f, KNOB_Z), axis, up, (0.0, 1.0, 0.0)) for ys in KNOB_YS]


KNOBS = _knob_frames()


# ----------------------------------------------------------------------------------------------- paints

def p_board(ctx, seed, p):
    """Walnut with a brass trim strip along the front edge."""
    c = T.g_wood(ctx, seed, {"kind": "walnut"})
    if ctx.chart == "+x" and ctx.t < 0.02:
        c = T.g_brass(ctx, seed + 3, {"streak": False})
    return c


def p_base(ctx, seed, p):
    """Royal-blue enamel panels in a riveted copper frame (the frame covers the rounded edges), a dark inset
    line inside it; the top is copper under the collar."""
    if ctx.chart == "+z":
        c = T.g_copper(ctx, seed, {"streak": False, "patina": 0.1})
        r = math.hypot(ctx.pos[0], ctx.pos[1])
        if r < 0.125:
            c = T.mix(c, T.hexc("2A0E04"), T.smoothstep(0.125, 0.112, r) * 0.6)    # the collar's shadow
        return c
    e = T.edge_dist(ctx)
    if e < FRAME:
        c = T.g_copper(ctx, seed, {"streak": True, "patina": 0.12})
        return T.frame_rivets(ctx, c, FRAME * 0.5, 0.085, 0.014)
    c = T.g_enamel(ctx, seed + 5, {"color": ENAMEL, "chips": 1, "chip_r": 0.02, "gloss": 0.35})
    if e < FRAME + 0.008:
        c = T.scale(c, 0.5)
    return c


def p_knobs(ctx, seed, p):
    """Brass knobs: knurled sides (bold dark grooves), a lit cap with a dark pointer showing the speed."""
    x, y, z = ctx.pos
    k = 0 if y < 0 else 1
    (cx, cy, cz), axis, up, right = KNOBS[k]
    q = (x - cx, y - cy, z - cz)
    u, v = G.dot(q, right), G.dot(q, up)
    c = T.g_brass(ctx, seed, {"streak": True, "hotspot": 0.7, "patina": 0.05})
    if G.dot(ctx.n, axis) < 0.75:
        a = math.atan2(v, u)
        if abs(((a * 12 / (2 * math.pi)) % 1.0) - 0.5) < 0.2:
            c = T.mix(c, T.hexc("4A2A06"), 0.6)
        return c
    deg = math.radians(KNOB_DEG[k])
    d = (math.sin(deg), math.cos(deg))
    along = u * d[0] + v * d[1]
    across = abs(-u * d[1] + v * d[0])
    if -0.004 < along < KNOB_R * 0.85 and across < 0.0055:
        c = T.mix(T.hexc("2A1404"), T.hexc("5A3010"), T.clamp01(along / KNOB_R))
    return c


def p_collar(ctx, seed, p):
    """The brass collar the jar locks into: a lit flange, a knurled band of dark grooves round its upper part
    and a dark seam where the glass goes in."""
    c = T.g_brass(ctx, seed, {"streak": True, "hotspot": 0.5, "patina": 0.08})
    z = ctx.pos[2]
    if z > BASE_Z1 + 0.018:
        a = math.atan2(ctx.pos[1], ctx.pos[0])
        if abs(((a * 20 / (2 * math.pi)) % 1.0) - 0.5) < 0.18:
            c = T.mix(c, T.hexc("3A2006"), 0.55)
    if z > COLLAR_Z1 - 0.005:
        c = T.mix(c, T.hexc("1A0E04"), 0.6)
    return c


def p_jar(ctx, seed, p):
    """Clear glass with g_glass's streaks and darker rims, as clear as section 5.2.5 allows so the shake shows its
    pink, and two painted white measuring ticks on the front left: a long one (0.075) and a short one (0.045),
    0.024 tall, long and thin so they read as a scale and not as labels (close-range charm: about 3 texels tall,
    they fade to a pale smudge past about 8 yd)."""
    c = T.g_glass(ctx, seed, {"tint": T.hexc("EEF4F2"), "alpha": 0.28})
    z = ctx.pos[2]
    if 0.33 < ctx.u < 0.45:
        for tz, u1 in ((0.38, 0.45), (0.45, 0.40)):
            if abs(z - tz) < 0.012 and ctx.u < u1:
                return (0.98, 0.97, 0.94, 0.92)
    return c


def p_shake(ctx, seed, p):
    """A strawberry shake: pink with lighter swirls under a pale froth crown, a band about 0.02 deep with a bubbly
    lower edge, so the top reads as a drink and not as a solid."""
    c = T.g_shake(ctx, seed, {"color": T.hexc("F6789C"), "top": SHAKE_TOP, "froth_d": 0.03})
    x, y, z = ctx.pos
    edge = SHAKE_TOP - 0.021 + 0.012 * (T.fbm3(x * 45.0, y * 45.0, z * 8.0, seed + 7, 2) - 0.5)
    k = T.smoothstep(edge - 0.003, edge + 0.002, z)
    return T.mix(c, T.mix(T.hexc("FFF4F2"), T.hexc("F8C8D4"), T.smoothstep(edge + 0.012, edge, z)), k * 0.9)


def p_lid(ctx, seed, p):
    """A brass rim band on the glass, a domed royal-blue enamel cap with a lit crown, a gold boss and the gold post
    of the propeller."""
    z = ctx.pos[2]
    r = math.hypot(ctx.pos[0], ctx.pos[1])
    if z < LID_RIM + 0.003:
        c = T.g_brass(ctx, seed, {"streak": True, "hotspot": 0.4})
        if z < LID_Z0 + 0.008:
            c = T.mix(c, T.hexc("3A2006"), 0.5)
        return c
    if r < 0.04:
        return T.g_gold(ctx, seed + 1, {"streak": False})
    c = T.g_enamel(ctx, seed + 2, {"color": ENAMEL, "chips": 0, "gloss": 0.2})
    if r > 0.105:
        c = T.mix(c, T.hexc("101C34"), 0.5)
    return c


def p_straps(ctx, seed, p):
    """The grip straps in the collar's darker brass, so they read as metal hardware: dark lines along their
    edges and one bold rivet on the front and back faces, in the gap between the glass and the grip."""
    c = T.g_brass(ctx, seed, {"streak": True, "hotspot": 0.5, "patina": 0.08, "palette": STRAP_BRASS})
    if T.edge_dist(ctx) < 0.008:
        c = T.mix(c, T.hexc("2E1804"), 0.65)
    if ctx.chart in ("+x", "-x"):
        x, y, z = ctx.pos
        zc = min(STRAPS, key=lambda s: abs(s - z))
        yc = (_jar_r(zc) + GRIP_Y - 0.021) / 2       # midway between the glass and the grip's side at x 0.025
        dx = y - yc if ctx.chart == "+x" else yc - y
        c = T.rivet_dot(c, dx, zc - z, 0.01)
    return c


def p_grip(ctx, seed, p):
    c = T.g_wood(ctx, seed, {"kind": "dark", "along": "t"})
    return T.mix(c, T.hexc("9A6640"), T.clamp01(ctx.n[2]) * 0.4)


def p_propeller(ctx, seed, p):
    """A polished copper nose cone with a gold tip and a gold ring at its back (a colour of its own, so the hub
    reads apart from the blades); brass blades with royal-blue painted tips behind a gold line (a toy plane's
    propeller)."""
    q = (ctx.pos[0], ctx.pos[1], ctx.pos[2] - PROP_Z)
    h = G.dot(q, PROP_AXIS)                                          # along the axis, from the hub
    r = G.length(G.sub(q, G.mul(PROP_AXIS, h)))                      # distance from the propeller's axis
    if r < NOSE_R + 0.001:
        if h > NOSE_L - 0.018 or h < -0.004:
            return T.g_gold(ctx, seed + 1, {"streak": True, "hotspot": 0.8})
        return T.g_copper(ctx, seed + 2, {"streak": True, "hotspot": 0.8, "patina": 0.0})
    c = T.g_brass(ctx, seed, {"streak": False, "hotspot": 0.4, "patina": 0.04})
    if r > BLADE_L * 0.8:
        c = T.g_enamel(ctx, seed + 3, {"color": ENAMEL, "chips": 0, "gloss": 0.2})
    elif r > BLADE_L * 0.72:
        c = T.hexc("F2CC5A")
    return c


# ---------------------------------------------------------------------------------------------- decals

def d_dials(w, h):
    """The base front: a cream dial scale round each knob, with bold ticks over a 240 degree sweep (the last one
    red) inside a dark ring."""
    img = T.Img(w, h, (0, 0, 0, 0))
    ppy = w / BASE_W                      # pixels per yard on this chart
    for ys in KNOB_YS:
        cx = (BASE_W / 2 + ys) * ppy
        cy = (BASE_Z1 - KNOB_Z) * ppy
        r = DIAL_R * ppy
        if r < 3:
            continue
        P2.ring(img, cx, cy, r * 0.94, r * 1.06, T.hexc("1A1006"))
        P2.ring(img, cx, cy, 0.0, r * 0.94, T.hexc("F2EAD4"))
        for k in range(5):
            a = math.radians(-120.0 + 60.0 * k)
            col = T.hexc("C83A28") if k == 4 else T.hexc("3A2410")
            x0, y0 = cx + math.sin(a) * r * 0.7, cy - math.cos(a) * r * 0.7
            x1, y1 = cx + math.sin(a) * r * 0.92, cy - math.cos(a) * r * 0.92
            P2.line(img, x0, y0, x1, y1, max(1.0, r * 0.13), col)
    return img


def d_medallion(w, h):
    """A gold lion medallion on a side panel: a dark bevel ring, a lit gold ring, the lion in relief."""
    img = T.Img(w, h, (0, 0, 0, 0))
    s = int(min(w, h) * 0.7)
    if s < 6:
        return img
    cx, cy = w // 2, h // 2
    P2.ring(img, cx, cy, s * 0.5, s * 0.545, T.hexc("3A2006"))
    P2.ring(img, cx, cy, s * 0.45, s * 0.5, T.hexc("F6D676"))
    rel = E.render_relief("lion_head", int(s * 0.86), int(s * 0.86), P2.GOLD_RELIEF)
    P2.composite(img, rel, cx - rel.w // 2, cy - rel.h // 2)
    return img


# ------------------------------------------------------------------------------------------------ parts

def _jar_r(z):
    """The glass wall's radius at height z."""
    for (r0, z0), (r1, z1) in zip(JAR, JAR[1:]):
        if z0 <= z <= z1:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return JAR[-1][0]


def _paddle(L, root, w):
    """One propeller blade outline along +X from the hub, a leaf: a slender root swelling to its widest past
    mid-length, then tapering to a round tip (CCW). (Widest at the tip, two blades read as a bow tie.)"""
    return [(0.012, -root / 2), (L * 0.55, -w / 2), (L * 0.86, -w * 0.4), (L, -w * 0.13),
            (L, w * 0.13), (L * 0.86, w * 0.4), (L * 0.55, w / 2), (0.012, root / 2)]


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (0.35, 0.35, 0.7)
    d.budget = 800
    d.kind = "machine"
    d.atlas = {"atlas": 256}
    d.max_height = 0.95
    d.sloped_top = True
    add = d.add

    # the walnut base board, a brass trim strip along its front edge (sunk so its rounded lower edge meets the bar)
    board = G.box(0.35, 0.35, BOARD_H + BOARD_SINK, 0.01, faces="+x -x +y -y +z", z0=-BOARD_SINK)
    for ch in board.charts:
        ch.weight = {"+z": 0.4, "-x": 0.3, "+x": 1.0}.get(ch.name, 0.6)
    add(B.Part("board", board, paint=p_board, seed=11))

    # the motor base: a tapered box, blue enamel panels framed in riveted copper; dial scales on the front,
    # lion medallions on the sides
    base = G.box(BASE_W, BASE_W, BASE_Z1 - BASE_Z0 + 0.009, 0.03, faces="+x -x +y -y +z", z0=BASE_Z0 - 0.009)
    base = G.taper(base, TAPER, BASE_Z0, BASE_Z1)
    for ch in base.charts:
        ch.weight = {"+x": 1.5, "-x": 0.5, "+z": 0.35}.get(ch.name, 1.0)
    add(B.Part("base", base, paint=p_base, seed=21,
               decals={"+x": d_dials, "+y": d_medallion, "-y": d_medallion}))

    # two chunky brass knobs on the front, square to its lean
    kprof = [(KNOB_R, 0.0), (KNOB_R * 0.9, 0.028), (KNOB_R * 0.62, 0.036), (0.0, 0.037)]
    knobs = []
    for (c, axis, _up, _right) in KNOBS:
        m = G.mat_chain(G.mat_translate(c[0] - 0.006, c[1], c[2]), G.mat_disc_facing(axis))
        knobs.append(G.transform(G.lathe(kprof, 8), m))
    add(B.Part("knobs", G.merge(knobs), paint=p_knobs, seed=31, weight=1.6, ao_floor=0.7))

    # the knurled brass collar the jar locks into
    collar = G.lathe([(0.114, BASE_Z1 - 0.006), (0.114, BASE_Z1 + 0.012), (0.104, BASE_Z1 + 0.02),
                      (0.099, COLLAR_Z1)], 12)
    add(B.Part("collar", collar, paint=p_collar, seed=41, weight=0.9))

    # the glass jar, one shell drawn on both sides (section 5.2.5's glass1, so the far wall shows above the
    # shake), and the shake in it (a real gap between them, so the glass reads as a shell)
    add(B.Part("jar", G.lathe(JAR, 14), "glass1", paint=p_jar, seed=51, weight=0.8, ao_floor=1.0))
    # (smooth up to 60 degrees, so the flared wall takes the shoulder's up-tilted normals and catches the sun; its
    # foot stands hidden in the collar)
    shake = G.lathe([(0.084, 0.275), (0.104, 0.493), (0.097, SHAKE_TOP)], 12, cap_top=True, angle=60.0)
    add(B.Part("shake", shake, paint=p_shake, seed=53, weight=1.1, ao_floor=0.9))

    # the lid: a brass rim band on the glass under a domed blue enamel cap
    lid = G.lathe([(0.131, LID_Z0), (0.131, LID_RIM), (0.1, 0.629), (0.04, LID_TOP)], 12, cap_bottom=True,
                  cap_top=True)
    # (the propeller's post stands on the lid's gold boss and takes its paint)
    lid = G.merge([lid, G.cylinder(0.018, PROP_Z - LID_TOP + 0.004, 6, False, z0=LID_TOP - 0.004)])
    add(B.Part("lid", lid, paint=p_lid, seed=61, weight=0.8))

    # the handle on the right-hand side (+Y): two chunky brass straps from the glass (closed at the glass end,
    # which shows through it) and a walnut grip
    straps = []
    for z in STRAPS:
        r_wall = _jar_r(z) - 0.006
        L = GRIP_Y - r_wall
        straps.append(G.translate(G.box(L, STRAP_W, STRAP_H, faces="+x -x -y +z -z"), 0.0, r_wall + L / 2,
                                  z - STRAP_H / 2))
    # (weighted up so their edge lines and rivets get enough texels to read)
    add(B.Part("straps", G.merge(straps), paint=p_straps, seed=71, weight=1.2))
    grip = G.translate(G.capsule(GRIP_R, GRIP_Z1 - GRIP_Z0, 8, 2), 0.0, GRIP_Y, GRIP_Z0)
    add(B.Part("grip", grip, paint=p_grip, seed=73, weight=1.0))

    # the gnomish propeller over the lid on its post: a copper nose cone pointing at the barista (closed at its
    # back, so the side views do not look through the hub) and two pitched leaf-shaped brass blades with blue tips
    nose = G.transform(G.lathe([(NOSE_R, -0.01), (NOSE_R * 0.8, 0.026), (0.0, NOSE_L)], 8, cap_bottom=True),
                       G.mat_chain(G.mat_translate(0.0, 0.0, PROP_Z), G.mat_disc_facing(PROP_AXIS)))
    blade = G.extrude(_paddle(BLADE_L, BLADE_ROOT, BLADE_W), 0.01)
    blade = G.transform(blade, G.mat_chain(G.mat_rot_x(math.radians(PROP_TWIST)), G.mat_translate(0, 0, -0.005)))
    blades = [nose]
    for k in range(2):
        m = G.mat_chain(G.mat_translate(0.0, 0.0, PROP_Z), G.mat_rot_z(PROP_YAW), G.mat_translate(0.004, 0.0, 0.0),
                        G.mat_rot_x(math.pi * k), G.MAT_EXTRUDE_FRONT)
        blades.append(G.transform(blade, m))
    add(B.Part("propeller", G.merge(blades), paint=p_propeller, seed=83, weight=1.2, ao_floor=0.85))

    # collision: walls to 0.45, a gable roof to 0.7 (roof n.z 0.57 < 0.6428: too steep to stand on)
    d.collision = G.hull_gable(0.35, 0.35, 0.45, 0.7)
    d.particles = []
    return d
