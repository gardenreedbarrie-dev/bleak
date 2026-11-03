"""19315 BackBarOrg, the Orgrimmar back bar, CAFE.SPEC.md section 5.8.1. M5.

The long cabinet behind the barista that the Tusk-o-Matic, the grinder and the syrup rack stand on, front (+X)
toward the barista and, across the counter, every customer. It is CounterOrg's twin (counter_org.py: the same
crooked dark plank top, timber, iron and red lacquer, and the same two tile textures), and what makes a player
name it at a glance is:
- the backsplash: a pointed palisade of eighteen rough timber stakes (a third of a yard each) standing along the
  back, every third one red lacquer worn back to the timber, lashed together with one rope 0.06 tall, their
  points alternating 0.10 and 0.13 above shoulders 0.28 over the top and leaning a little each way, so the line
  reads hand-cut: the Orgrimmar palisade in silhouette (a sawtooth at 30 yd), 0.41 above the top;
- a run of cupboards: six whole bays, each two red-lacquered drawers with bone bar pulls (a red band along the
  whole front) over two calm doors of three upright dark planks a leaf, with two iron strap hinges (0.07 tall,
  spear ends, outlined dark) and an iron ring pull with a bone-white highlight (0.08 across);
- the café cue on the barista face: the two end bays (never under a machine's front) are open shelves in place
  of the doors, a back wall of dark boards with two rows of chunky red-glazed clay mugs (0.13 tall, 0.11 wide,
  a bone-white glaze band with drips round the rim, handles toward +Y) on two rough timber shelf lips (geometry,
  0.04 proud and 0.05 tall, with rope wraps at their ends);
- a red crest shield (0.34 across, the counter's tusk_crest in bone) in the middle of the front, over the
  drawer row: the Orgrimmar focal point the counter has between its tusks;
- the thick, crooked plank top the machines stand on (three dark boards 0.1 thick, flush, so no machine sinks
  into a proud board; ragged, staggered ends, dark gaps, nails);
- a goblin gadget at the -Y end: a riveted copper pressure tank (0.24 across, 0.5 long) on iron saddles, a big
  pressure gauge on its front (yellow and red bands, the needle in the red) and a red valve wheel on top (a rim
  0.06 thick on crossed spokes 0.05 wide), piped into the palisade.
The back (-X) repeats the counter's fascia: hide bays laced into plank frames, iron straps, crooked posts; the
palisade shows its other face (the same paint, mirrored). 6.0 (Y) x 0.85 (X) x 1.05 yd, the stake points to 1.46
(render_size; the collision box keeps the 1.05 bar height).

Textures: the `panels` and `top` tiles are CounterOrg's own files (section 5.8: "shares CounterOrg"): the tile
specs carry owner "CounterOrg", so the M2 points at CounterOrg's _Panels.blp and _Top.blp and the hide, timber and
iron match the counter exactly.
The palisade's faces read the panels tile's palisade band and its sawn edges the cut band; the shelves read the
shelf band; the posts and the ends are on the top tile; the shield, the shelf lips and the gadget share a baked
256² atlas.

Placement (section 3.12.3, the back bar at F 4.8 turned 180 degrees): the Tusk-o-Matic covers Y -0.7..0.7, the
grinder Y -2.275..-1.725 and the syrup rack Y 1.275..2.725 with its back at X -0.375, so the palisade is 0.045
thick (X -0.425..-0.38) and the tank spans Y -2.91..-2.41. The shield is on the front face, under the top, and
the shelves are below it: the machines never cover them.

Deviations from the section 5.8.1 design ("the same materials, with cupboard doors and a 0.3 yd backsplash"):
- the backsplash is a palisade 0.41 tall at its highest point (0.28 at the shoulders): a flat 0.3 panel read as
  a strip of red tiles, and the points are what says Orgrimmar; the machines, up to 0.95 above the top, still
  stand in front of it;
- the shield, the open shelves of mugs and the goblin tank are additions (Orgrimmar's red lacquer, a café cue
  and a goblin gadget); the hide rag of the first drafts read as a block of paper from 8 yd and is gone.
"""

import math

from .. import build as B
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T
from . import counter_org as CO
from . import counter_sw as CS

NAME = "BackBarOrg"
DISPLAY = 19315

W, D, H = 6.0, 0.85, 1.05
SPLASH_X0, SPLASH_X1 = -0.425, -0.38      # behind the syrup rack's back (X -0.375)
STAKES = 18                               # a third of a yard each: the seams fall on the tile's thirds
TOP = H + CO.STAKE_SHOULDER + max(CO.STAKE_TIPS)    # 1.46, the highest points
BODY_W = 5.78                             # the boards overhang the corner posts by up to 0.06 at the ends
BAY_Y = BODY_W / 2 - CO.POST + CO.POST_OUT          # 2.80: the corner posts' inner faces
BAYS = 6
BAY_W = 2 * BAY_Y / BAYS                             # 0.933: six whole bays between the corner posts
BACK_POSTS = tuple(-BAY_Y + BAY_W * k for k in range(1, BAYS))
SHELF_BAYS = (0, BAYS - 1)                # the end bays are open shelves of mugs (counter_org.shelf_bay)
LIP_D = 0.04                              # the shelves' timber lips stand 0.04 proud, counter_org.SHELF_LIP_H tall
# the lips' ends along Y (0.01 into the opening's frame each side), per shelf bay
LIPS = tuple((-BAY_Y + (k + CO.LEAVES[0][0]) * BAY_W - 0.01, -BAY_Y + (k + CO.LEAVES[1][1]) * BAY_W + 0.01)
             for k in SHELF_BAYS)
EVEN_BOARDS = ((D - 2 * CO.BOARD_GAP) / 3.0,) * 3   # three boards 0.27 wide, flush (the machines span all three)
SHIELD_R, SHIELD_Z = 0.17, 0.765          # on the front's middle, over the drawer row, 0.015 under the top
TANK = (-0.22, -2.66)                     # the tank's centre (x, y) on the top
TANK_R, TANK_L = 0.12, 0.5
TANK_Z = H + 0.035 + TANK_R               # its axis, on saddles 0.035 tall
GAUGE_R, WHEEL_R = 0.09, 0.08


# ------------------------------------------------------------------------------------------------ paints

def p_tank(ctx, seed, p):
    """The pressure tank: copper with green patina, two riveted iron bands round it."""
    c = T.g_copper(ctx, seed, {"patina": 0.3})
    y = ctx.pos[1] - TANK[1]
    for by in (-TANK_L * 0.3, TANK_L * 0.3):
        if abs(y - by) < 0.026:
            c = T.g_iron(ctx, seed + 1, {"rust": 0.2})
            phi = math.atan2(ctx.pos[2] - TANK_Z, ctx.pos[0] - TANK[0])
            a0 = round(phi / (math.pi / 6)) * (math.pi / 6)
            return T.rivet_dot(c, (phi - a0) * TANK_R, y - by, 0.013, T.IRON_RIVET_HI, T.IRON_RIVET_LO)
    return c


def p_lip(ctx, seed, p):
    """The shelves' lips: rough dark timber with the grain along them, lit on top, and a rope wrap near each end
    (diagonal strands, dark grooves, lit toward the barista)."""
    c = T.scale(T.g_wood(ctx, seed, {"kind": "timber", "along": "long"}), 0.7)
    c = T.mix(c, T.hexc("B08860"), T.clamp01(ctx.n[2]) * 0.3)
    _x, y, z = ctx.pos
    d = min(min(abs(y - a), abs(y - b)) for a, b in LIPS)
    if 0.02 < d < 0.075:
        q = ((y + z * 0.6) / 0.016) % 1.0
        rope = T.mix(T.hexc("4A3820"), T.hexc("C8A468"), math.sin(math.pi * q))
        c = T.scale(rope, 0.8 + 0.3 * T.clamp01(ctx.n[2] + ctx.n[0] * 0.5))
    return c


def p_iron(ctx, seed, p):
    return T.g_iron(ctx, seed, {"rust": 0.25})


def p_red(ctx, seed, p):
    return T.g_lacquer(ctx, seed, {"color": CO.LACQUER, "worn": 0.5})


def p_brass(ctx, seed, p):
    return T.g_brass(ctx, seed, {"patina": 0.2})


# ---------------------------------------------------------------------------------------------- decals

def d_gauge(w, h):
    """The goblin gauge: green, yellow and red bands, the needle well into the red."""
    return P2.gauge_face(w, h, {"needle_deg": 62.0})


def d_shield(w, h):
    return CO.d_shield(w, h)


# ------------------------------------------------------------------------------------------------ parts

def palisade():
    """The backsplash: one pointed palisade of STAKES stakes as a single extruded outline (39 points: the bottom
    edge sunk 0.01 into the back board, the two end shoulders, and a point and a seam per stake), 0.045 thick and
    stood up across the back. The shoulders are counter_org.STAKE_SHOULDER above the top, the points alternate
    counter_org.STAKE_TIPS tall and lean counter_org.STAKE_LEAN off their stakes' middles by their place in the
    tile. Both faces read the panels tile's palisade band at the same s (the street side sees it mirrored), the
    sawn edges (the extrusion's belt: s along the outline, t across its depth) the cut band."""
    w = W / STAKES
    zs = H + CO.STAKE_SHOULDER
    outline = [(-W / 2, H - 0.01), (W / 2, H - 0.01), (W / 2, zs)]
    for i in range(STAKES - 1, -1, -1):
        y0 = -W / 2 + i * w
        outline.append((y0 + w / 2 + CO.STAKE_LEAN[i % 3], zs + CO.STAKE_TIPS[i % 2]))
        outline.append((y0, zs))
    m = G.extrude(outline, SPLASH_X1 - SPLASH_X0, 0.0, True, "palisade")
    m = G.transform(m, G.mat_chain(G.mat_translate(SPLASH_X0, 0.0, 0.0), G.mat_extrude_facing((1.0, 0.0, 0.0))))
    z_top = H + CO.SPLASH_H
    for v in range(len(m.p)):
        name = m.charts[m.c[v]].name
        if name == "palisade_side":
            m.st[v] = (m.st[v][0], CO.BAND_C + m.st[v][1])
        else:
            m.st[v] = (m.p[v][1] + W / 2, CO.BAND_B + (z_top - m.p[v][2]))
    return m


def front_faces():
    """The carcass's long faces: the barista face in three quads, so the two end bays read the tile's shelf band
    and the four between them its door band (map_face stretches each over its whole bays), and the street face
    on the fascia band."""
    out = []
    edges = (-BODY_W / 2, -BAY_Y + BAY_W, BAY_Y - BAY_W, BODY_W / 2)
    for i in range(3):
        y0, y1 = edges[i], edges[i + 1]
        q = G.translate(G.box(y1 - y0, CO.FRONT_X - CO.BACK_X, CO.FACE_H, faces="+x", z0=CO.BODY_Z0),
                        (CO.FRONT_X + CO.BACK_X) / 2, (y0 + y1) / 2, 0.0)
        band = CO.BAND_D if i == 1 else CO.BAND_S
        out.append(CS.retile(q, CS.map_face(band, CO.BAND_F, CO.BODY_Z1, BAY_Y, BAY_W)))
    back = G.translate(G.box(BODY_W, CO.FRONT_X - CO.BACK_X, CO.FACE_H, faces="-x", z0=CO.BODY_Z0),
                       (CO.FRONT_X + CO.BACK_X) / 2, 0.0, 0.0)
    out.append(CS.retile(back, CS.map_face(CO.BAND_D, CO.BAND_F, CO.BODY_Z1, BAY_Y, BAY_W)))
    return G.merge(out)


def shelf_lips():
    """The rough timber lips of the open shelves in the two end bays: under each shelf top of counter_sw.SHELVES,
    a bar across the opening (LIPS) LIP_D proud and counter_org.SHELF_LIP_H tall, its back sunk 0.004 into the
    face so the light wobble never opens a gap."""
    out = []
    n = 0
    for y0, y1 in LIPS:
        for sv in CS.SHELVES:
            zt = CO.BODY_Z1 - sv
            lip = G.translate(G.box(y1 - y0, LIP_D + 0.004, CO.SHELF_LIP_H, faces="+x +y -y +z",
                                    z0=zt - CO.SHELF_LIP_H), CO.FRONT_X + (LIP_D - 0.004) / 2, (y0 + y1) / 2, 0.0)
            out.append(G.wobble(lip, 0.004, 41 + 7 * n))
            n += 1
    return G.merge(out)


def valve_wheel():
    """The tank's valve wheel at the origin in the XY plane: a rim 0.06 thick (8 sides, 3 rings) and two crossed
    bars 0.05 wide and 0.03 thick through its middle, the four spokes (their ends hidden in the rim)."""
    rim = G.torus(WHEEL_R, 0.03, 8, 3)
    span = 2 * WHEEL_R - 0.03
    bars = [G.box(0.05, span, 0.03, faces="+y -y +z -z", z0=-0.015),
            G.box(span, 0.05, 0.03, faces="+x -x +z -z", z0=-0.015)]
    return G.merge([rim] + bars)


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (W, D, H)
    d.render_size = (W, D, TOP)
    d.budget = 900
    d.kind = "counter"
    d.atlas = {"atlas": 256}
    d.tiles = {k: dict(v, owner="CounterOrg") for k, v in CO.tiles().items()}   # the counter's own files
    add = d.add
    hw = BODY_W / 2

    # the plank top, its three boards flush (and the dark plate under its gaps)
    add(B.Part("top", CO.plank_top(W, D, 53, EVEN_BOARDS, (0.0, 0.0, 0.0)), texture="top"))

    # the carcass: plank cupboards toward the barista with open shelves of mugs in the two end bays, hide fascia
    # bays at the back (the panels tile, six whole bays between the corner posts), the ends (the top tile)
    add(B.Part("carcass", front_faces(), texture="panels"))
    ends = G.translate(G.box(BODY_W, CO.FRONT_X - CO.BACK_X, CO.FACE_H, faces="+y -y", z0=CO.BODY_Z0),
                       (CO.FRONT_X + CO.BACK_X) / 2, 0.0, 0.0)
    add(B.Part("ends", CS.retile(ends, CS.map_end(CO.FRONT_X, CO.BACK_X, CO.END_T, CO.END_W, CO.BODY_Z1,
                                                  CO.END_TH / CO.FACE_H)), texture="top"))
    add(B.Part("shelf_lips", shelf_lips(), paint=p_lip, seed=33, weight=0.8, ao_floor=0.6))

    # the riveted iron plinth and the crooked posts (corners, and the back's bay edges)
    plinth = G.translate(G.box(BODY_W + 0.1, CO.PLINTH_X1 - CO.PLINTH_X0, CO.PLINTH_H, faces="+x -x +y -y +z"),
                         (CO.PLINTH_X0 + CO.PLINTH_X1) / 2, 0.0, 0.0)
    add(B.Part("plinth", CS.retile(plinth, CO.map_iron(CO.PLINTH_H)), texture="top"))
    add(B.Part("posts", G.merge([CO.corner_posts(CO.FRONT_X, CO.BACK_X, hw, 61),
                                 CO.face_posts(CO.FRONT_X, CO.BACK_X, (), BACK_POSTS, seed=67)]), texture="top"))

    # the red crest shield in the middle of the front, over the drawer row
    shield = G.transform(G.cylinder(SHIELD_R, 0.035, 16, (False, True)),
                         G.mat_chain(G.mat_translate(CO.FRONT_X - 0.002, 0.0, SHIELD_Z), G.MAT_DISC_FRONT))
    for ch in shield.charts:
        ch.weight = 2.4 if ch.name == "cyl_top" else 0.6
    add(B.Part("shield", shield, paint=CO.p_shield_side, seed=19, decals={"cyl_top": d_shield}))

    # the backsplash: the pointed palisade (its faces and sawn edges on the panels tile)
    add(B.Part("palisade", palisade(), texture="panels"))

    # the goblin pressure tank: a copper drum along Y on two iron saddles, a gauge on its front, a red valve
    # wheel on a stem on top, a pipe from its back buried in the palisade
    tx, ty = TANK
    prof = [(0.0, -TANK_L / 2), (0.07, -TANK_L / 2 + 0.012), (TANK_R, -TANK_L / 2 + 0.06),
            (TANK_R, TANK_L / 2 - 0.06), (0.07, TANK_L / 2 - 0.012), (0.0, TANK_L / 2)]
    tank = G.transform(G.lathe(prof, 12), G.mat_chain(G.mat_translate(tx, ty, TANK_Z), G.mat_rot_x(-math.pi / 2)))
    add(B.Part("tank", tank, paint=p_tank, seed=21, weight=1.3))
    saddles = [G.translate(G.box(0.06, TANK_R * 1.7, 0.07, faces="+x -x +y -y +z", z0=H), tx, ty + o, 0.0)
               for o in (-TANK_L * 0.3, TANK_L * 0.3)]
    stem = G.translate(G.cylinder(0.03, 0.07, 6, False, z0=TANK_Z + TANK_R - 0.01), tx, ty + 0.08, 0.0)
    pipe = G.sweep([(tx - TANK_R + 0.01, ty - 0.1, TANK_Z), (tx - TANK_R - 0.03, ty - 0.1, TANK_Z),
                    (SPLASH_X1 - 0.015, ty - 0.1, TANK_Z + 0.02)], 0.024, 6, caps=(False, False))
    add(B.Part("tank_iron", G.merge(saddles + [stem, pipe]), paint=p_iron, seed=23, weight=0.7))
    wheel = G.translate(valve_wheel(), tx, ty + 0.08, TANK_Z + TANK_R + 0.06)
    add(B.Part("valve_wheel", wheel, paint=p_red, seed=25, weight=1.0))
    gface = (1.0, 0.0, 0.18)
    gc = (tx + TANK_R - 0.014, ty - 0.04, TANK_Z + 0.005)
    gauge = G.transform(G.cylinder(GAUGE_R, 0.03, 12, (False, True)), G.mat_chain(G.mat_translate(*gc),
                                                                                  G.mat_disc_facing(gface)))
    for ch in gauge.charts:
        ch.weight = 2.6 if ch.name == "cyl_top" else 0.6
    add(B.Part("gauge", gauge, paint=p_brass, seed=27, decals={"cyl_top": d_gauge}))
    bezel = G.transform(G.torus(GAUGE_R + 0.003, 0.016, 8, 3), G.mat_chain(G.mat_translate(*gc),
                                                                           G.mat_disc_facing(gface),
                                                                           G.mat_translate(0.0, 0.0, 0.03)))
    add(B.Part("gauge_bezel", bezel, paint=p_brass, seed=29, weight=0.6))

    d.collision = G.hull_box(W, D, H)
    return d
