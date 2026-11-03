"""19314 BackBarSW, the Stormwind back bar, CAFE.SPEC.md section 5.8.1. M5.

The long cabinet behind the barista that the espresso machine, the grinder and the syrup rack stand on, front
(+X) toward the barista. It is CounterSW's twin (counter_sw.py: the same marble slab, walnut, gold and royal-blue
enamel, and the same two tile textures), and what makes a player name it at a glance is:
- a run of cupboards: six whole bays between the corner posts, each a row of two drawers with brass bar pulls
  (0.16 x 0.06) over a pair of doors whose royal-blue panels are raised (real geometry, 0.02 proud, gilded
  bevels) inside walnut frames, with brass knobs (0.076 across); slim fluted walnut pilasters (0.10 wide, 0.035
  proud) under gold capitals stand on the bay edges, so the face has the counter's carved rhythm;
- the café cue on the barista face: the two end bays (never under a machine's front) are open shelves in place
  of the doors, a royal-blue back wall with two rows of white porcelain cups on saucers (0.12 tall, a blue band
  and a gold rim line) standing on two gilt shelf lips (geometry, 0.04 proud and 0.05 tall);
- the thick white marble slab the machines stand on (0.09 thick, overhanging 0.08 toward the barista) on the
  counter's two-step plinth;
- the backsplash along the back: one calm row of large white glazed tiles (0.25 yd), each with a royal-blue
  line inset round it and a blue dot on every grout cross, under a walnut cap rail with a gold bead (0.06
  tall), 0.31 tall in all, so the machines stand out in front of it;
- gold lion medallions (0.25 across, the backsplash's full height) in the gaps the machines leave;
- charm: a pyramid of upturned blue-banded cups (0.12 across) on a stack of saucers at the -Y end and a
  striped bar towel draped over the slab's front edge at the +Y end.
The back (-X, toward the wall or the street) repeats the counter's fascia: blue enamel bays with the gold cup
between gilded walnut pilasters. 6.0 (Y) x 0.8 (X) x 1.05 yd, the backsplash to 1.36 (render_size; the
collision box keeps the 1.05 bar height the machines stand on).

Textures: the `panels` and `top` tiles are CounterSW's own files (section 5.8: "shares CounterSW textures"):
the tile specs carry owner "CounterSW", so the M2 points at CounterSW's BH_Cafe_CounterSW_Panels.blp and
_Top.blp and the client loads one copy; the marble, enamel and walnut match the counter exactly. The ends, posts,
plinth, shelves and their lips, door panels and their gilt bevels are on the tiles; the capitals, medallions,
cups and towel share a baked 256² atlas.

Placement (section 3.12.3, the back bar at F 4.8 turned 180 degrees): the espresso machine covers Y -0.65..0.65,
the grinder Y -2.25..-1.75 and the syrup rack Y 1.3..2.7 with its back at X -0.35, so the backsplash is 0.045
thick (X -0.40..-0.355), the medallions sit at Y -2.5, -1.2 and 0.98 (clear of the grinder at -2.25), the cups
at Y -2.76 (beside the medallion, not in front of it) and the towel at Y 2.85.

Deviations from the section 5.8.1 design ("the same materials, with cupboard doors and a 0.3 yd backsplash"):
- drawers over the doors, raised door panels, the pilasters, the open shelves of cups in the end bays, lion
  medallions on the backsplash, the cups and the towel are additions; the backsplash is 0.31 (the cap rail is
  0.06 so it reads; the tiles keep their 0.25);
- the slab overhangs 0.08 toward the barista and 0.05 at the back, as on the counter;
- the street side keeps flat painted fascia bays (no raised panels or foot rail) behind shallower pilasters
  (0.035 proud, single-step capitals): it faces the wall or the street, and the 0.05 slab overhang there has
  no room for the counter's stepped capitals; the barista face's pilasters are as shallow and narrower (0.10),
  so they stay clear of the drawers and doors.
"""

import math

from .. import build as B
from .. import geom as G
from .. import tex as T
from . import counter_sw as CS

NAME = "BackBarSW"
DISPLAY = 19314

W, D, H = 6.0, 0.8, 1.05
FRONT_X = 0.32                            # the barista face: 0.08 under the slab (slim pilasters on this side)
SPLASH_TOP = 1.36
CAP_H = 0.06                              # the cap rail, tall enough to read; the tiles under it stay 0.25
SPLASH_X0, SPLASH_X1 = -0.40, -0.355      # behind the syrup rack's back (X -0.35)
CAP_X1 = -0.345
BODY_W = 5.88
BAY_Y = BODY_W / 2 - CS.POST + CS.POST_OUT          # 2.86: the corner posts' inner faces
BAYS = 6
BAY_W = 2 * BAY_Y / BAYS                             # 0.953: six whole bays between the corner posts
BACK_PILASTERS = tuple(-BAY_Y + BAY_W * k for k in range(1, BAYS))
PIL_D_BACK = 0.035
PIL_W_FRONT = 0.10                        # the barista face's pilasters: clear of the drawers and doors (0.067 in)
SHELF_BAYS = (0, BAYS - 1)                # the end bays are open shelves of cups (counter_sw.shelf_bay)
LIP_D = 0.04                              # the shelves' gilt lips stand 0.04 proud, counter_sw.LIP_H tall
MED_R = 0.125
MEDALLIONS = (-2.5, -1.2, 0.98)
CUPS = (0.08, -2.76)
TOWEL_Y, TOWEL_W = 2.85, 0.22
DOOR_D = 0.02                             # the raised door panels stand 0.02 proud


# ------------------------------------------------------------------------------------------------ paints

def p_porcelain(ctx, seed, p):
    """Upturned cups and the saucer stack: white porcelain; the cups have a royal-blue band 0.03 tall with a gold
    line just above their rims (now at the bottom), the saucers a blue rim line on every saucer."""
    c = T.g_ceramic(ctx, seed, {})
    x, y, z = ctx.pos
    lz = z - H
    if ctx.part == "cup_saucers":
        if math.hypot(ctx.n[0], ctx.n[1]) > 0.5 and (lz % 0.0125) < 0.004:
            c = T.mix(c, CS.ENAMEL, 0.85)
        return c
    base = min(CUP_AT, key=lambda q: (x - q[0]) ** 2 + (y - q[1]) ** 2 + (z - q[2]) ** 2)[2]
    k = z - base
    if math.hypot(ctx.n[0], ctx.n[1]) > 0.4:
        if 0.008 <= k <= 0.038:
            c = T.mix(CS.ENAMEL, T.scale(CS.ENAMEL, 1.3), T.clamp01(ctx.n[0] * 0.5 + 0.5))
        elif 0.038 < k <= 0.046:
            c = T.hexc("E8B848")
    return c


def p_towel(ctx, seed, p):
    """A cream cotton bar towel: two royal-blue stripes near each end, a soft weave, a short fringe at the
    hanging end, darker folds where it bends over the slab's edge."""
    c = T.mix(T.hexc("F2EAD6"), T.hexc("E2D6BC"), T.noise(ctx.s * 30.0, ctx.t * 30.0, seed))
    L = ctx.ch
    for e in (0.06, L - 0.07):
        for o in (-0.018, 0.018):
            if abs(ctx.t - (e + o)) < 0.009:
                c = T.mix(CS.ENAMEL, T.hexc("4A72B8"), 0.3)
    if ctx.t > L - 0.02:
        q = (ctx.s % 0.02) / 0.02
        c = T.mix(c, T.hexc("6A5A40"), 0.6 if q < 0.4 else 0.0)
    if abs(ctx.t - BEND_T) < 0.03:
        c = T.scale(c, 0.82 + 0.18 * abs(ctx.t - BEND_T) / 0.03)
    return c


# -------------------------------------------------------------------------------------------- geometry

def ribbon(path, y0, y1, thick, name="ribbon"):
    """A thin cloth strip: `path` [(x, z), ...] is its inner face (the side lying on the slab), the outer face
    is `thick` further out along each point's normal in the XZ plane; the strip runs from y0 to y1. Closed
    (outer, inner, both sides, both ends), CCW outward. Charts: outer and inner (s across, t along)."""
    n = len(path)
    nrm = []
    for i in range(n):
        a, b = path[max(0, i - 1)], path[min(n - 1, i + 1)]
        tx, tz = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(tx, tz) or 1.0
        nrm.append((-tz / ln, tx / ln))
    arc = [0.0]
    for i in range(1, n):
        arc.append(arc[-1] + math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]))
    outer = [(p[0] + q[0] * thick, p[1] + q[1] * thick) for p, q in zip(path, nrm)]
    m = G.Mesh()
    w = y1 - y0
    for surf, pts, sign in ((m.chart(w, arc[-1], name + "_outer"), outer, 1), (m.chart(w, arc[-1], name + "_inner"),
                                                                              path, -1)):
        rows = [(m.vert((x, y0, z), (0.0, 0.0, 1.0), surf, 0.0, arc[i]),
                 m.vert((x, y1, z), (0.0, 0.0, 1.0), surf, w, arc[i])) for i, (x, z) in enumerate(pts)]
        for i in range(n - 1):
            (a0, a1), (b0, b1) = rows[i], rows[i + 1]
            if sign > 0:
                m.tri(a0, b0, b1)
                m.tri(a0, b1, a1)
            else:
                m.tri(a0, b1, b0)
                m.tri(a0, a1, b1)
    side = m.chart(arc[-1], thick, name + "_side")
    for y, sign in ((y0, 1), (y1, -1)):
        vi = [m.vert((x, y, z), (0.0, -sign, 0.0), side, arc[i], 0.0) for i, (x, z) in enumerate(path)]
        vo = [m.vert((x, y, z), (0.0, -sign, 0.0), side, arc[i], thick) for i, (x, z) in enumerate(outer)]
        for i in range(n - 1):
            if sign > 0:
                m.tri(vi[i], vi[i + 1], vo[i + 1])
                m.tri(vi[i], vo[i + 1], vo[i])
            else:
                m.tri(vi[i], vo[i + 1], vi[i + 1])
                m.tri(vi[i], vo[i], vo[i + 1])
    for i, sign in ((0, -1), (n - 1, 1)):
        a = m.vert((path[i][0], y0, path[i][1]), (0.0, 0.0, 1.0), side, 0.0, 0.0)
        b = m.vert((path[i][0], y1, path[i][1]), (0.0, 0.0, 1.0), side, w, 0.0)
        c = m.vert((outer[i][0], y1, outer[i][1]), (0.0, 0.0, 1.0), side, w, thick)
        d = m.vert((outer[i][0], y0, outer[i][1]), (0.0, 0.0, 1.0), side, 0.0, thick)
        if sign > 0:
            m.tri(a, b, c)
            m.tri(a, c, d)
        else:
            m.tri(a, c, b)
            m.tri(a, d, c)
    return G.recompute_normals(m, 50.0)


# the towel's inner face: across the slab top, round the slab's bevelled front corner (centre X 0.365,
# Z 1.015, radius counter_sw.SLAB_BEVEL 0.035) at radius 0.038, then down the front
_BR = CS.SLAB_BEVEL + 0.003
_CORNER = [(D / 2 - CS.SLAB_BEVEL + _BR * math.cos(math.radians(a)),
            H - CS.SLAB_BEVEL + _BR * math.sin(math.radians(a))) for a in (90, 60, 30, 0)]
TOWEL_PATH = [(0.17, H + 0.003)] + _CORNER + [(D / 2 + 0.003, 0.95), (D / 2 + 0.001, 0.84)]
BEND_T = (D / 2 - CS.SLAB_BEVEL - 0.17) + _BR * math.pi / 4
# upturned cups (x, y, base z): three on the saucer stack, one on top of them
_STACK_H = 0.05
CUP_R, CUP_H = 0.06, 0.085
CUP_AT = [(CUPS[0] + math.cos(math.radians(a)) * 0.07, CUPS[1] + math.sin(math.radians(a)) * 0.07,
           H + _STACK_H) for a in (0, 120, 240)] + [(CUPS[0], CUPS[1], H + _STACK_H + CUP_H - 0.004)]


def upturned_cup():
    """A porcelain cup upside down: rim (r 0.06) at the bottom, foot (r 0.038) on top, the foot closed."""
    return G.lathe([(CUP_R, 0.0), (CUP_R * 0.87, CUP_H * 0.76), (0.038, CUP_H), (0.0, CUP_H)], 8)


def door_panels():
    """The raised door panels on the barista face: on both leaves of every bay but the shelf bays, the footprint
    inside the walnut door frame, its front 0.02 proud and DOOR_BEAD smaller all round (the gilt bevels stand on
    the painted bead), as (fronts, bevels)."""
    fronts, bevels = [], []
    z1 = CS.BODY_Z1 - (CS.DOORS[0] + CS.DOOR_FR)
    z0 = CS.BODY_Z1 - (CS.DOORS[1] - CS.DOOR_FR)
    for k in range(BAYS):
        if k in SHELF_BAYS:
            continue
        for u0, u1 in CS.DOOR_U:
            y0 = -BAY_Y + (k + u0 + CS.DOOR_FR) * BAY_W
            y1 = -BAY_Y + (k + u1 - CS.DOOR_FR) * BAY_W
            f, b = CS.raised_panel(FRONT_X, 1, y0, y1, z0, z1, DOOR_D, CS.DOOR_BEAD)
            fronts.append(f)
            bevels.append(b)
    return G.merge(fronts), G.merge(bevels)


def front_faces():
    """The barista face of the carcass in three quads, so the two end bays read the tile's shelf band and the
    four between them its door band (map_face stretches each over its whole bays)."""
    out = []
    edges = (-BODY_W / 2, -BAY_Y + BAY_W, BAY_Y - BAY_W, BODY_W / 2)
    for i in range(3):
        y0, y1 = edges[i], edges[i + 1]
        q = G.translate(G.box(y1 - y0, FRONT_X - CS.BACK_X, CS.FACE_H, faces="+x", z0=CS.BODY_Z0),
                        (FRONT_X + CS.BACK_X) / 2, (y0 + y1) / 2, 0.0)
        band = CS.BAND_D if i == 1 else CS.BAND_S
        out.append(CS.retile(q, CS.map_face(band, CS.BAND_F, CS.BODY_Z1, BAY_Y, BAY_W)))
    back = G.translate(G.box(BODY_W, FRONT_X - CS.BACK_X, CS.FACE_H, faces="-x", z0=CS.BODY_Z0),
                       (FRONT_X + CS.BACK_X) / 2, 0.0, 0.0)
    out.append(CS.retile(back, CS.map_face(CS.BAND_D, CS.BAND_F, CS.BODY_Z1, BAY_Y, BAY_W)))
    return G.merge(out)


def shelf_lips():
    """The gilt lips of the open shelves in the two end bays: under each shelf top of counter_sw.SHELVES, a bar
    across the opening (0.01 into its frame each side) LIP_D proud and counter_sw.LIP_H tall, on the `top` tile's
    gilt strip (front and ends across the strip, the top a narrow run of it)."""
    out = []
    u0, u1 = CS.DOOR_U[0][0], CS.DOOR_U[1][1]
    for k in SHELF_BAYS:
        y0 = -BAY_Y + (k + u0) * BAY_W - 0.01
        y1 = -BAY_Y + (k + u1) * BAY_W + 0.01
        for sv in CS.SHELVES:
            zt = CS.BODY_Z1 - sv
            lip = G.translate(G.box(y1 - y0, LIP_D, CS.LIP_H, faces="+x +y -y +z", z0=zt - CS.LIP_H),
                              FRONT_X + LIP_D / 2, (y0 + y1) / 2, 0.0)

            def fn(p, name, zt=zt):
                if name == "+z":
                    return (p[1], CS.GOLD_T + 0.005 + (p[0] - FRONT_X) * 0.5)
                along = p[1] if name == "+x" else p[0]
                return (along, CS.GOLD_T + (zt - p[2]) / CS.LIP_H * CS.GOLD_TH)
            out.append(CS.retile(lip, fn))
    return G.merge(out)


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (W, D, H)
    d.render_size = (W, D, SPLASH_TOP)
    d.budget = 900
    d.kind = "counter"
    d.atlas = {"atlas": 256}
    d.tiles = {k: dict(v, owner="CounterSW") for k, v in CS.tiles().items()}   # the counter's own files
    add = d.add
    hw = BODY_W / 2

    # the marble slab
    add(B.Part("slab", CS.slab_mesh(W, D, -D / 2, D / 2), texture="top"))

    # the carcass: cupboard bays toward the barista with open shelves of cups in the two end bays, fascia bays at
    # the back (six whole bays between the corner posts on both), the ends on their own band: all on the panels
    # tile
    add(B.Part("carcass", front_faces(), texture="panels"))
    ends = G.translate(G.box(BODY_W, FRONT_X - CS.BACK_X, CS.FACE_H, faces="+y -y", z0=CS.BODY_Z0),
                       (FRONT_X + CS.BACK_X) / 2, 0.0, 0.0)
    add(B.Part("ends", CS.retile(ends, CS.map_end(FRONT_X, CS.BACK_X)), texture="panels"))
    add(B.Part("shelf_lips", shelf_lips(), texture="top"))

    # the raised door panels: fronts on the door band (enamel), gilt bevels on the top tile's strip
    fronts, bevels = door_panels()
    add(B.Part("door_panels", CS.retile(fronts, CS.map_face(CS.BAND_D, CS.BAND_F, CS.BODY_Z1, BAY_Y, BAY_W)),
               texture="panels"))
    add(B.Part("panel_bevels", CS.map_strip(bevels), texture="top"))

    # the counter's two-step plinth, corner posts, the pilasters on both faces' bay edges (slim ones toward the
    # barista) and the gold capitals
    toe, torus = CS.plinth(BODY_W, FRONT_X, CS.BACK_X)
    add(B.Part("plinth_toe", toe, texture="top"))
    add(B.Part("plinth_torus", torus, texture="top"))
    posts = G.merge([CS.corner_posts(FRONT_X, CS.BACK_X, hw, CS.BODY_Z0, CS.BODY_Z1),
                     CS.pilasters(CS.BACK_X, -1, BACK_PILASTERS, PIL_D_BACK),
                     CS.pilasters(FRONT_X, 1, BACK_PILASTERS, PIL_D_BACK, PIL_W_FRONT)])
    add(B.Part("posts", posts, texture="top"))
    caps = G.merge([CS.capitals(CS.BACK_X, -1, BACK_PILASTERS, PIL_D_BACK, two_step=False),
                    CS.capitals(FRONT_X, 1, BACK_PILASTERS, PIL_D_BACK, two_step=False, width=PIL_W_FRONT),
                    CS.corner_capitals(FRONT_X, CS.BACK_X, hw, (True, False))])
    add(B.Part("capitals", caps, paint=CS.p_gold, seed=15, weight=0.6))

    # the backsplash: glazed tiles on both faces (it stands free when the café is not against a wall)
    sx = (SPLASH_X0 + SPLASH_X1) / 2
    splash = G.translate(G.box(W, SPLASH_X1 - SPLASH_X0, SPLASH_TOP - CAP_H - H, faces="+x -x +y -y", z0=H),
                         sx, 0.0, 0.0)
    z_top = SPLASH_TOP - CAP_H

    def splash_map(p, name):
        along = p[1] if name == "+x" else (-p[1] if name == "-x" else p[0])
        return (along + W / 2, CS.BAND_B + (z_top - p[2]))
    add(B.Part("splash", CS.retile(splash, splash_map), texture="panels"))
    cap = G.translate(G.box(W, CAP_X1 - SPLASH_X0, CAP_H, faces="+x -x +y -y +z -z", z0=z_top),
                      (SPLASH_X0 + CAP_X1) / 2, 0.0, 0.0)
    add(B.Part("cap_rail", CS.retile(cap, CS.map_moulding(SPLASH_TOP, CAP_H)), texture="top"))

    # gold lion medallions on the backsplash, in the gaps between the machines, as tall as the tiles
    meds = []
    for y in MEDALLIONS:
        meds.append(G.transform(G.cylinder(MED_R, 0.022, 12, (False, True)),
                                G.mat_chain(G.mat_translate(SPLASH_X1 - 0.002, y, H + (z_top - H) / 2),
                                            G.MAT_DISC_FRONT)))
    meds = G.merge(meds)
    for ch in meds.charts:
        ch.weight = 2.6 if ch.name == "cyl_top" else 0.5
    add(B.Part("medallions", meds, paint=CS.p_gold, seed=17, decals={k: CS.d_medallion for k, ch in
                                                                   enumerate(meds.charts) if ch.name == "cyl_top"}))

    # charm: upturned cups on a stack of saucers, a striped bar towel over the slab's front edge
    stack = G.lathe([(0.12, 0.0), (0.12, _STACK_H - 0.006), (0.1, _STACK_H), (0.0, _STACK_H)], 10)
    add(B.Part("cup_saucers", G.translate(stack, CUPS[0], CUPS[1], H), paint=p_porcelain, seed=21, weight=0.9,
               ao_floor=0.75))
    cups = G.merge([G.translate(upturned_cup(), x, y, z) for x, y, z in CUP_AT])
    add(B.Part("cups", cups, paint=p_porcelain, seed=23, weight=1.2, ao_floor=0.75))
    towel = ribbon(TOWEL_PATH, TOWEL_Y - TOWEL_W / 2, TOWEL_Y + TOWEL_W / 2, 0.009, "towel")
    add(B.Part("towel", towel, paint=p_towel, seed=25, weight=1.2, ao_floor=0.7))

    d.collision = G.hull_box(W, D, H)
    return d
