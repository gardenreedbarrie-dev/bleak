"""19313 CounterOrg, the Orgrimmar serving counter, CAFE.SPEC.md section 5.8.1. M5.

A long, waist-high counter of rough dark timber, red hide, black iron and bone, front (+X) toward the customers.
What makes a player name it at a glance, from the front three-quarter view at 4-15 yd:
- the counter silhouette: a long body under a top of three thick, crooked dark planks of different widths (0.1
  thick; a narrow front board 0.21 wide standing 0.015 proud as a lip toward the customers, ragged ends
  staggered by 0.04, dark gaps of 0.02 between them, nailed down) on a riveted iron plinth;
- the fascia: five whole bays of red-brown hide stretched in dark plank frames, laced to the frame with chunky
  leather thongs (0.06 wide, every 0.12) and daubed with a bone-white war-paint jaw of five fangs, crossed by
  two riveted iron straps (0.07 tall) that run the whole length, between crooked timber posts (0.14 wide)
  banded where the straps cross;
- a pair of big ivory tusks (0.17 thick at the root, 1.45 long) rising from the plinth on the centre bay's edges,
  set into the face, and arching inward, lashed with leather where they pass through the top's front board,
  their blunt points 0.4 apart at 1.40 over the counter's edge: the tusk crest of the café sign, made solid;
- a round red-lacquered shield with the tusk_crest in bone relief and an iron rim between them (0.38 across);
- a bronze bell hanging in a yoke of two knuckled ivory bone uprights (stained bands at the knuckles, dark
  roots) under a timber crossbar (0.36 wide, 0.41 tall, the bell 0.24 across its flared lip, a clapper under
  it): "ring for service" in silhouette;
- two iron spikes (0.22 tall) on iron plates at the top's front corners, and charm: a hessian sack of roasted
  beans (0.32 across its low belly, 0.35 tall), pinched at the neck by a dark drawstring under a floppy lip
  gathered into five folds and tilted toward the customers, beans heaped above it, a faded red coffee-cup
  stencil on its belly.
The barista's side (-X) shows red-lacquered drawers with bone pulls over calm doors of three dark planks a leaf,
with iron strap hinges with spear ends and ring pulls. 5.0 (Y) x 0.85 (X) x 1.05 yd.

Textures (the plan of CounterSW, counter_sw.py): two repeating tiles used as trim sheets and shared with
BackBarOrg (back_bar_org.py builds byte-identical files from the same functions), and a baked 256² atlas:
- `panels` (256 x 1024, wrap): one bay across, five bands down (hide fascia bays, plank cupboard bays, the back
  bar's palisade, the back bar's open shelves of mugs, the palisade's sawn edges), mapped with the bays
  stretched to fill the space between the corner posts, so every bay is whole;
- `top` (256 x 512, wrap): the three plank boards (one band per board, so each has its own tone and grain), the
  riveted iron band of the plinth and the back bar's cap, the posts' front faces and sides (s down the post) and
  the carcass ends (a fascia bay END_W wide, squeezed 0.82 tall into its band);
- `atlas` (256², baked): the tusks and their lashings, the shield, the bell and its yoke, the plates and spikes,
  the sack and the beans (the tusks weighted up, the thin plates, the spikes and the crossbar down).
Tiles are not baked, so their paint carries the bake's gradient, key light and contact shadows.

Deviations from the section 5.8.1 design ("dark timber, hide panels with stitching, iron bands, a bone-handled
bell"):
- section 5.8 lists one 256² texture for CounterOrg; a 5 yd counter needs the repeating tiles of CounterSW to
  hold its detail, so it has the same three;
- the bell hangs in a bone yoke (the bone is the frame, not a handle): a bone-handled hand bell read as a bottle
  or a salt shaker from 8 yd;
- the tusks, the shield, the corner spikes and the bean sack are additions (the tusks and shield carry the
  Orgrimmar read that CounterSW gets from its lion medallion); the yoke rises to 1.47 and the tusk points to 1.40
  above the floor, the tusks' root lashings stand 0.011 beyond the footprint (render_size 5.0 x 0.86 x
  1.47), the collision box keeps 5.0 x 0.85 x 1.05;
- the hide panels are laced with thongs across the gap to the frame (the design's "stitching"): stitches
  along the hide's edge vanish at 10 yd, thongs 0.06 wide do not;
- only the front board stands proud (never below the others), and it starts at X 0.215, beyond everything that
  stands on the counter (section 3.12.3: the tip jar, the pickup cup and the blender, which reaches X 0.202),
  so nothing placed floats or sinks into it;
- section 5.4's wobble (1-2 cm) is 1.2 cm on the posts (held inside the footprint at the back) but 0.4 cm on
  the boards, which carry the placed pieces, and the carcass and plinth are straight boxes.
"""

import math

from .. import build as B
from .. import emblem as E
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T
from . import counter_sw as CS

NAME = "CounterOrg"
DISPLAY = 19313

HIDE = T.hexc("8E3A22")
LACQUER = T.hexc("B5402F")
LACQUER_DARK = T.hexc("9C2A1F")
BONE_PAINT = T.hexc("E6D6B0")
BRONZE = dict(light_c=T.hexc("E8B070"), base=T.hexc("8A5424"), dark=T.hexc("2E1808"), bounce=T.hexc("6A3A18"),
              patina=T.hexc("4E6A4A"))

W, D, H = 5.0, 0.85, 1.05
RENDER_D, RENDER_H = 0.86, 1.47           # the tusks' root lashings in front; the yoke and the tusk points
TOP_H = 0.10
TOP_Z0 = H - TOP_H                        # 0.95
PLINTH_H = 0.10
BODY_Z0, BODY_Z1 = PLINTH_H, TOP_Z0       # the carcass faces, 0.85 tall
FACE_H = BODY_Z1 - BODY_Z0
FRONT_X, BACK_X = 0.35, -0.375            # the planks overhang 0.075 in front, 0.05 behind
BODY_W = 4.78                             # the boards overhang the corner posts by up to 0.06 at the ends
PLINTH_X0, PLINTH_X1 = -0.405, 0.39
POST, POST_OUT = 0.14, 0.05               # square corner posts, 0.05 proud of both faces
BAY_Y = BODY_W / 2 - POST + POST_OUT      # 2.30: the corner posts' inner faces
BAYS = 5
BAY_W = 2 * BAY_Y / BAYS                  # 0.92: five whole bays between the corner posts
PILASTERS = (-(BAY_Y - BAY_W), BAY_Y - BAY_W)   # timber posts on the outer bay edges (+-1.38); the tusks stand
                                                # on the centre bay's edges (+-0.46)
PIL_W, PIL_D = 0.14, 0.05
END_W = FRONT_X - BACK_X                  # 0.725
BOARDS = 3
BOARD_GAP = 0.02
BOARD_WIDTHS = (0.21, 0.33, 0.27)         # front, middle, back: the front board starts at X 0.215
BOARD_DZ = (0.015, 0.0, 0.0)              # how far each board stands above 1.05: only the front lip
BOARD_ENDS = ((0.0, 0.04), (0.04, 0.0), (0.02, 0.02))   # how far each board's -Y and +Y ends stop short of 2.5
BELL = (0.29, 0.75)                       # on the front board, clear of the tusks and of the pickup cup at +1.6
YOKE_W, YOKE_H = 0.30, 0.41               # the bone uprights' spacing and height
BELL_Z = H + BOARD_DZ[0] - 0.003          # the yoke's foot, on the front board
SACK = (0.0, -0.95)                       # on the middle board, clear of the tip jar at -1.6
TUSK_ROOT = (0.34, BAY_W / 2, 0.06)       # (x, |y|, z) of the tusk roots, on the centre bay's edges, set into
                                          # the face so the tusks stay inside the footprint
TUSK_END = (0.354, 0.252, 1.315)          # where the horn ends; its point runs on TUSK_POINT along the tangent
TUSK_POINT = 0.10
TUSK_R0, TUSK_R1 = 0.085, 0.035
POST_WOBBLE = 0.012                       # section 5.4's crooked timber, on the posts (they carry nothing)
# the bean sack's profile (r, z) from its foot to the rolled lip: the widest point low, a pinched neck
SACK_PROFILE = ((0.13, 0.0), (0.16, 0.07), (0.15, 0.15), (0.12, 0.2), (0.09, 0.23), (0.12, 0.27), (0.10, 0.29))
SACK_NECK, SACK_TILT = 0.23, 10.0         # the neck's height; the floppy lip above it tilts toward the customers

# The `panels` tile (256 x 1024 wrap): one bay across, five bands down (tile yards), as on CounterSW.
PANEL_TILE = (1.0, 4.0)
BAND_F, BAND_D, BAND_B, BAND_S, BAND_C = 0.015, 0.895, 1.775, 2.225, 3.105
SPLASH_H = 0.42                           # the back bar's palisade, from the top boards to above its points
CUT_H = 0.06                              # the palisade's sawn edges (its extrusion belt, 0.045 deep)
PANEL_BANDS = ((BAND_F, FACE_H, "fascia"), (BAND_D, FACE_H, "doors"), (BAND_B, SPLASH_H, "splash"),
               (BAND_S, FACE_H, "shelves"), (BAND_C, CUT_H, "cut"))
# The `top` tile (256 x 512 wrap), yards down: one band per plank board, the iron band, the posts' front faces
# and sides (s down the post), the carcass ends squeezed into END_TH.
TOP_TILE = (1.0, 2.0)
BOARD_W = 0.285
BOARD_T = (0.005, 0.30, 0.595)
IRON_T, IRON_H = 0.905, 0.1
POST_T, POST_TW = 1.035, POST
SIDE_T, SIDE_TW = 1.205, PIL_D
END_T, END_TH = 1.285, 0.70
TOP_BANDS = ((BOARD_T[0], BOARD_W, "board0"), (BOARD_T[1], BOARD_W, "board1"), (BOARD_T[2], BOARD_W, "board2"),
             (IRON_T, IRON_H, "iron"), (POST_T, POST_TW, "post"), (SIDE_T, SIDE_TW, "side"),
             (END_T, END_TH, "end"))

# a fascia bay: the iron straps (v ranges from the top of the face), the hide panel and its lacing thongs
STRAPS = ((0.05, 0.12), (0.70, 0.77))
HIDE_U, HIDE_V = (0.15, 0.85), (0.17, 0.65)
LACE_STEP, LACE_W, LACE_REACH = 0.12, 0.06, 0.06
# a cupboard bay: drawers, doors (v ranges), the two leaves (u ranges), the gaps between a leaf's three planks
# (yd), the hinges
DRAWERS = (0.05, 0.20)
DOORS = (0.25, 0.80)
LEAVES = ((0.06, 0.495), (0.505, 0.94))
LEAF_GAP = 0.02
HINGE_H, HINGE_V = 0.07, (0.06, 0.42)     # strap hinges 0.07 tall, their tops down each leaf
GAP = 0.014
# a shelf bay (the drawers over an opening in place of the doors): the shelf tops are counter_sw.SHELVES (v from
# the face's top), the timber lips (geometry in back_bar_org.py) hang SHELF_LIP_H below each; the painted mugs
SHELF_YD = 0.933                          # BackBarOrg's bay width (back_bar_org.BAY_W): yards per u on this band
SHELF_LIP_H = 0.05
MUG_W, MUG_H = 0.11, 0.13
MUG_ROWS = ((0.1025, 0.3075, 0.5125, 0.7175), (0.17, 0.41, 0.65))   # mug axes, yd from the opening's left edge
# the back bar's palisade (the splash band): three stakes a tile yard, so a stake's seams fall on the tile's
# thirds; the shoulders STAKE_SHOULDER above the top boards, points alternating STAKE_TIPS tall, each point
# STAKE_LEAN off its stake's middle (by its place in the tile, so the paint's facets meet the geometry's tips);
# every third stake (RED_STAKE) red lacquer; a rope lashing LASH (above the boards) across them all
STAKE_W = 1.0 / 3.0
STAKE_SHOULDER = 0.28
STAKE_TIPS = (0.10, 0.13)
STAKE_LEAN = (0.02, -0.015, 0.01)
RED_STAKE = 1
LASH = (0.06, 0.12)


# ----------------------------------------------------------------------------------------------- helpers

def _ctx(ctx, s, t, cw, ch, n=(1.0, 0.0, 0.0)):
    return T.Ctx(s, t, ctx.pos, n, ctx.curv, 1.0, cw, ch, ctx.chart, ctx.part)


def _timber(ctx, seed, vertical, kind="orgdark", width=0.2, offset=0.0):
    """Rough planks: boards `width` yd wide across the grain (vertical: upright boards), a dark gap between
    them with a lit lip, each board its own tone. Structure from the wrapped coordinates, grain from the raw
    ones (so it runs on across tile edges)."""
    a, b = (ctx.t, ctx.s) if vertical else (ctx.s, ctx.t)
    i = math.floor((b + offset) / width)
    q = (b + offset) / width - i
    sub = _ctx(ctx, ctx.s, ctx.t, 1.0, 1.0)
    c = T.g_wood(sub, seed + int(i) % 7, {"kind": kind, "along": "t" if vertical else "s"})
    c = T.scale(c, 0.86 + 0.24 * T._h(int(i) % 997, 3, 5, seed))
    if q < 0.05:
        return T.mix(T.hexc("120A06"), c, q / 0.05 * 0.3)
    if q < 0.12:
        c = T.mix(c, T.hexc("A07448"), (0.12 - q) / 0.07 * 0.3)
    elif q > 0.9:
        c = T.mix(c, T.scale(c, 0.6), (q - 0.9) / 0.1 * 0.6)
    return c


def _iron_strap(ctx, seed, along, across, h, step=0.125):
    """A riveted hammered-iron strap: `across` 0..h from its top edge, `along` its length; a bright lit top lip,
    a dark lower edge, a rivet every `step` yd on its centre line."""
    sub = _ctx(ctx, ctx.s, ctx.t, 1.0, 1.0)
    c = T.g_hammered_iron(sub, seed, {"rust": 0.15})
    k = T.clamp01(across / h)
    if k < 0.18:
        c = T.mix(c, T.hexc("9EA2AA"), (0.18 - k) / 0.18 * 0.75)
    elif k > 0.82:
        c = T.mix(c, T.hexc("0C0C10"), (k - 0.82) / 0.18 * 0.7)
    a0 = round((along - step / 2) / step) * step + step / 2
    return T.rivet_dot(c, along - a0, across - h / 2, h * 0.24, T.IRON_RIVET_HI, T.IRON_RIVET_LO)


def _hinge(ctx, seed, x, dv, reach):
    """An iron strap hinge seen from the front, x yd from the hinge edge and dv from its centre line: a strap
    HINGE_H tall to `reach`, then a spear head 0.05 long a little wider than the strap; a 2-texel dark outline
    round it all (it stands out on dark planks and on hide), the strap's lit lip and rivets. None outside."""
    hh = HINGE_H / 2
    if x < reach:
        half = hh
    elif x < reach + 0.05:
        f = (x - reach) / 0.05
        half = hh + 0.014 * f / 0.3 if f < 0.3 else (hh + 0.014) * (1.0 - f) / 0.7
    else:
        return None
    if abs(dv) >= half:
        return None
    if half - abs(dv) < 0.008 or x < 0.006:
        return T.hexc("0C0C10")
    return _iron_strap(ctx, seed, x, dv + hh, HINGE_H, 0.09)


def _ring_pull(c, du, dv, r=0.04):
    """A painted iron ring pull hanging from a small plate: the ring lit bone-white at the top, its shadow below
    (0.08 across)."""
    d = math.hypot(du, dv - r * 0.6)
    if abs(du) < r * 0.55 and -r * 0.75 < dv < -r * 0.1:
        return T.mix(T.hexc("3A3A40"), T.hexc("8A8C94"), T.clamp01(0.5 - dv / r))
    if abs(d - r) < r * 0.28:
        k = T.clamp01(0.55 - (dv - r * 0.6) / r * 0.6)
        c = T.mix(T.hexc("1A1A1E"), T.hexc("A8ACB4"), k)
        return T.mix(c, BONE_PAINT, T.smoothstep(0.75, 1.0, k) * 0.8)
    if abs(math.hypot(du - r * 0.2, dv - r * 0.8) - r) < r * 0.3:
        return T.mix(c, T.hexc("08060A"), 0.55)
    return c


def _face_light(z, v, bottom):
    """The light the bake would give a front face of a floor piece at height z, with the shadow under the top's
    overhang (v from the face's top) and contact `bottom` yd above the face's lower edge."""
    zr = T.clamp01(z / 1.2)
    k = (0.75 + 0.40 * zr * zr * (3 - 2 * zr)) * 0.95
    k *= 1.0 - 0.42 * T.smoothstep(0.10, 0.0, v)
    k *= 1.0 - 0.3 * T.smoothstep(0.06, 0.0, bottom)
    return k


def _hide_panel(ctx, seed, c, u, v, box, fangs, k, reach):
    """A red-brown hide with burnt, ragged edges stretched over box (u0, u1, v0, v1: u in the caller's units, v in
    yards down), laced to the planks with chunky leather thongs (LACE_W wide every LACE_STEP, a little slanted,
    lit along the top) reaching `reach` beyond its left and right edges into dark lacing holes, daubed with a
    bone-white war-paint jaw of `fangs` fangs at scale k. c, the planks under it, is returned (with the hide's
    shadow) where neither the hide nor a thong is."""
    hu0, hu1, hv0, hv1 = box
    rag = (T.noise(u * 14.0, v * 14.0, seed + 5) - 0.5) * 0.025
    e = min(u - hu0, hu1 - u, v - hv0, hv1 - v) + rag
    side = min(u - hu0, hu1 - u)
    if hv0 + 0.03 < v < hv1 - 0.03 and -reach < side < 0.03:
        q = ((v - hv0 - LACE_STEP / 2) % LACE_STEP) / LACE_STEP - 0.5      # 0 on a thong's centre line
        x = -side / reach                   # 0 at the hide's edge, 1 at the lacing hole
        half = LACE_W / 2 / LACE_STEP
        d = q - (x - 0.5) * 0.2
        if abs(d) < half and side < 0.022:
            if x > 0.8:
                return T.hexc("100804")     # the hole the thong runs into
            return T.mix(T.hexc("4A2A12"), T.hexc("C09060"), T.clamp01(0.55 - d / half * 0.6))
    if e < 0.0:
        if e > -0.012:
            c = T.mix(c, T.hexc("120A06"), 0.6)        # the hide's shadow on the planks
        return c
    sub = _ctx(ctx, u - hu0, v - hv0, hu1 - hu0, hv1 - hv0)
    c = T.g_hide(sub, seed + 7, {"color": HIDE, "edge": 0.04, "scuffs": 0.5})
    # the war paint: a bone-white jaw line with fangs hanging from it, daubed by hand
    lu = (u - hu0) / (hu1 - hu0)
    jaw = hv0 + (hv1 - hv0) * 0.36
    paint = T.mix(BONE_PAINT, T.scale(BONE_PAINT, 0.8), T.noise(u * 40.0, v * 40.0, seed + 9))
    wob = (T.noise(u * 9.0, 3.0, seed + 11) - 0.5) * 0.012 * k
    if abs(v - jaw - wob) < max(0.014, 0.02 * k) and 0.07 < lu < 0.93:
        return paint
    q = (lu - 0.1) * fangs / 0.8
    if 0.0 < q < fangs and v > jaw:
        f = abs(q - math.floor(q) - 0.5) * 2.0          # 0 at a fang's centre, 1 between fangs
        if f < 0.62 and v - jaw < 0.17 * k * (1.0 - f / 0.62):
            return paint
    return c


# ------------------------------------------------------------------------------------------ bay painters

def fascia_bay(ctx, seed, u, v, bw, bh):
    """One bay of the counter front, unlit: upright dark planks, two riveted iron straps across the whole bay,
    a red-brown hide laced to the planks with a five-fang war-paint jaw. u across (0..bw), v down (0..bh). The
    ends use it too (bw their width in yards)."""
    for v0, v1 in STRAPS:
        if v0 <= v < v1:
            return _iron_strap(ctx, seed + 3, u, v - v0, v1 - v0)
    c = _timber(ctx, seed, True)
    hu0, hu1 = HIDE_U[0] * bw, bw - (1.0 - HIDE_U[1]) * bw
    if bw < 0.9:
        hu0, hu1 = 0.12, bw - 0.12
    return _hide_panel(ctx, seed, c, u, v, (hu0, hu1) + HIDE_V, 5, 1.0, LACE_REACH)


def _leaf(ctx, seed, lu, lv, lw, lh, i):
    """A door leaf, unlit: three upright dark planks with LEAF_GAP dark gaps between them and ragged ends (the
    dark behind shows through), each plank its own tone, a lit left arris and a shadowed right edge. lu, lw
    across in tile units, lv, lh down in yards; i the leaf."""
    pw = lw / 3.0
    j = min(2, int(lu / pw))
    x = lu - j * pw
    gap = LEAF_GAP / BAY_W
    x0 = gap if j > 0 else 0.0
    if x < x0:
        return T.hexc("0C0604")
    top = 0.006 + 0.016 * T._h(j, i, 3, seed) + 0.008 * T.noise(lu * 40.0, j * 3.0 + i, seed + 1)
    bottom = 0.006 + 0.014 * T._h(j, i, 4, seed) + 0.008 * T.noise(lu * 40.0, j * 3.0 + i + 7.0, seed + 2)
    if lv < top or lh - lv < bottom:
        return T.hexc("0C0604")
    c = T.g_wood(_ctx(ctx, ctx.s, ctx.t, 1.0, 1.0), seed + 3 * j + i, {"kind": "timber", "along": "t"})
    c = T.mix(T.scale(c, 0.64 + 0.14 * T._h(j, i, 5, seed)), T.hexc("4A2214"), 0.12)
    if x - x0 < 0.012:
        c = T.mix(c, T.hexc("A07448"), 0.3)
    elif pw - x < 0.012:
        c = T.scale(c, 0.6)
    return c


def door_bay(ctx, seed, u, v):
    """One bay of cupboards, unlit: two red-lacquered drawers (worn to the timber at the edges) with bone bar
    pulls over two doors; each leaf three upright dark planks (_leaf) with two iron strap hinges with spear ends
    and an iron ring pull at the meeting edge; dark gaps. Calm on purpose: the fangs belong to the customer face
    (fascia_bay), so the back bar reads as planks and iron under its crest shield."""
    for i, (u0, u1) in enumerate(LEAVES):
        for v0, v1, door in ((DRAWERS[0], DRAWERS[1], False), (DOORS[0], DOORS[1], True)):
            if not (u0 - GAP <= u <= u1 + GAP and v0 - GAP <= v <= v1 + GAP):
                continue
            if u < u0 or u > u1 or v < v0 or v > v1:
                return T.hexc("0C0604") if v < v1 else T.hexc("6A4A30")
            lu, lv, lw, lh = u - u0, v - v0, u1 - u0, v1 - v0
            if not door:
                sub = _ctx(ctx, lu, lv, lw, lh)
                c = T.g_lacquer(sub, seed + 7 + i, {"color": LACQUER if i == 0 else LACQUER_DARK, "gloss": 0.3})
                c = T.scale(c, 1.15)                     # so the red holds under night light
                wear = T.noise(ctx.s * 11.0, ctx.t * 11.0, seed + 8)
                if min(lu, lw - lu, lv, lh - lv) < 0.012 + 0.03 * wear:
                    c = T.mix(c, T.hexc("4A2A16"), 0.75)
                du, dv = lu - lw / 2, lv - lh / 2
                if abs(du) < 0.075 and abs(dv) < 0.018 - 0.1 * max(0.0, abs(du) - 0.06):
                    c = T.mix(T.hexc("7A6A48"), T.hexc("FFF4D6"), T.clamp01(0.62 - dv / 0.018 * 0.6))
                elif abs(du) < 0.08 and 0.018 <= dv < 0.032:
                    c = T.scale(c, 0.5)
                return c
            c = _leaf(ctx, seed + 9, lu, lv, lw, lh, i)
            outer = lu if i == 0 else lw - lu                # from the hinge edge
            for hv in HINGE_V:
                hc = _hinge(ctx, seed + 11, outer, lv - hv - HINGE_H / 2, lw * 0.6)
                if hc is not None:
                    return hc
            ku = lw - 0.06 if i == 0 else 0.06
            return _ring_pull(c, lu - ku, lv - lh * 0.5)
    return _timber(ctx, seed, True)


def palisade(ctx, seed, u, v):
    """The back bar's palisade, unlit: u across the tile (three stakes a yard), v down from the band's top (H +
    SPLASH_H). Raw dark timber stakes with grain up them, rounded by the light (lit left of the middle, dark
    toward the right edge), a dark seam 0.02 wide between them; every third stake red lacquer, worn back to the
    timber along its edges; above the shoulders the points' two axe-cut facets in fresher timber (the left one
    lit, split under the geometry's tip); one rope lashing across them all, dipping darker where it wraps each
    stake, with its shadow under it. No rivets and no square board tops: the points are geometry."""
    j = min(2, int(u / STAKE_W))
    x = u - j * STAKE_W                     # 0..STAKE_W across the stake
    if min(x, STAKE_W - x) < 0.01:
        return T.hexc("1A0E06")
    c = T.g_wood(_ctx(ctx, ctx.s, ctx.t, 1.0, 1.0), seed + j, {"kind": "timber", "along": "t"})
    c = T.scale(c, (0.66, 0.72, 0.62)[j])
    point = v < SPLASH_H - STAKE_SHOULDER
    if point:
        # the axe-cut facets: fresher timber, the left one toward the light
        c = T.mix(c, T.hexc("9A7048"), 0.25)
        c = T.scale(c, 1.12 if x < STAKE_W / 2 + STAKE_LEAN[j] else 0.66)
    elif j == RED_STAKE:
        lac = T.g_lacquer(_ctx(ctx, x, v, STAKE_W, SPLASH_H, (1.0, 0.0, 0.0)), seed + 7, {"color": LACQUER,
                                                                                          "gloss": 0.2, "worn": 0})
        lac = T.mix(lac, LACQUER_DARK, T.smoothstep(0.15, SPLASH_H, v) * 0.6)
        # worn back to the timber along the edges and raggedly under the point (no square-cut band)
        wear = T.noise(ctx.s * 14.0, ctx.t * 5.0, seed + 9)
        rag = T.noise(ctx.s * 40.0, 2.0, seed + 10)
        if min(x, STAKE_W - x) > 0.03 + 0.06 * wear * wear and v > SPLASH_H - STAKE_SHOULDER + 0.03 + 0.07 * rag:
            c = lac
    if not point:
        f = x / STAKE_W
        c = T.scale(c, 0.6 + 0.52 * math.sin(math.pi * f) - 0.2 * f)         # the stake's round: a log
    lv = SPLASH_H - v                        # height above the top boards
    if LASH[0] <= lv < LASH[1]:
        rope = T.g_rope(_ctx(ctx, ctx.s, LASH[1] - lv, 1.0, LASH[1] - LASH[0]), seed + 11,
                        {"color": T.hexc("B8955A"), "pitch": 0.1})
        return T.scale(rope, 0.62 if min(x, STAKE_W - x) < 0.03 else 1.0)
    if LASH[0] - 0.02 <= lv < LASH[0]:
        c = T.scale(c, 0.5 + 0.5 * (LASH[0] - lv) / 0.02)                     # the rope's shadow
    return c


def cut_band(ctx, seed, v):
    """The palisade's sawn edges (the extrusion belt: s along the outline, v across its 0.045 depth from the
    front), unlit: fresher timber with the grain along the cut and a darker back arris."""
    c = T.scale(T.g_wood(_ctx(ctx, ctx.s, ctx.t, 1.0, 1.0), seed, {"kind": "timber", "along": "s"}), 0.86)
    return T.mix(c, T.scale(c, 0.6), T.smoothstep(0.03, 0.045, v) * 0.5)


def _mug_paint(c, dx, h, shadow):
    """A chunky red-glazed clay mug painted on a shelf's back wall, seen from the front: dx yd right of its axis,
    h yd above the shelf. Lit from the upper left: the glaze (B5402F) with a dark core shadow down its right
    side, a bone-white glaze band round the rim with drips running down from it, the bare clay foot, the handle
    on the right (+Y). With `shadow` it returns the mug's drop shadow on the wall instead (the caller offsets dx
    and h). Outside the mug, c is returned unchanged."""
    if h < 0.0 or h > MUG_H:
        return c
    hw = MUG_W / 2 + 0.006 * math.sin(math.pi * h / MUG_H)            # a little barrel-bellied
    if abs(dx) < hw:
        if shadow:
            return T.scale(c, 0.5)
        k = T.smoothstep(-0.4, 1.0, dx / hw)
        if h < 0.014:
            return T.mix(T.hexc("B08058"), T.hexc("4A2E1A"), k)            # the bare clay foot
        if h > MUG_H - 0.03 - 0.03 * max(0.0, math.sin(dx * 95.0 + 0.7)) ** 4:
            col = T.mix(T.hexc("F4E8C8"), T.hexc("8A7A5A"), k)          # the bone-white rim glaze and drips
            return T.scale(col, 0.72) if h > MUG_H - 0.008 else col
        return T.mix(T.mix(LACQUER, T.hexc("E8805E"), 0.35), T.scale(LACQUER_DARK, 0.5), k)
    hd = math.hypot(dx - (hw + 0.016), h - MUG_H * 0.5)
    if dx > 0.0 and 0.016 < hd < 0.036:
        if shadow:
            return T.scale(c, 0.5)
        return T.mix(T.hexc("C85038"), T.scale(LACQUER_DARK, 0.5), T.clamp01(0.5 - (h - MUG_H * 0.5) / 0.036 * 0.5))
    return c


def shelf_bay(ctx, seed, u, v):
    """One bay of open shelves (BackBarOrg's two end bays), unlit: the door bay's red drawer row over an opening in
    the planks where the doors would be. Inside: a back wall of dark horizontal boards in shadow (darkest under
    each shelf), timber reveals, the shelf boards behind the lips, and on the two shelves rows of red-glazed clay
    mugs (four, then three, 0.13 tall) with their drop shadows; the lips are geometry (back_bar_org.py). u in
    tile units (SHELF_YD yards each), v in yards down."""
    u0, u1 = LEAVES[0][0], LEAVES[1][1]
    v0, v1 = DOORS
    if v < v0 - GAP or v > v1 + 0.03 or u < u0 - 0.03 or u > u1 + 0.03:
        return door_bay(ctx, seed, u, v)
    e = min(u - u0, u1 - u, v - v0, v1 - v)
    if e < 0.0:
        # the opening's frame: upright planks with a lit arris round it
        c = _timber(ctx, seed + 3, True)
        return T.mix(c, T.hexc("A07448"), 0.35) if e > -0.01 else c
    # the reveals: the opening's inner walls seen in perspective (the top one in shadow, the left one lit)
    if v - v0 < 0.035 and v - v0 <= min(u - u0, u1 - u):
        return T.scale(_timber(ctx, seed + 5, False, "timber", 0.5), 0.3)
    if u - u0 < 0.03:
        return T.scale(_timber(ctx, seed + 5, True, "timber", 0.5), 0.7)
    if u1 - u < 0.03:
        return T.scale(_timber(ctx, seed + 5, True, "timber", 0.5), 0.42)
    if CS.SHELVES[0] <= v < CS.SHELVES[0] + SHELF_LIP_H or v > CS.SHELVES[1]:
        return T.scale(_timber(ctx, seed + 5, False, "timber", 0.5), 0.45)
    # the back wall: dark boards, darkest just under the shelf above each compartment
    k = 0 if v < CS.SHELVES[0] else 1
    top = v0 if k == 0 else CS.SHELVES[0] + SHELF_LIP_H
    c = T.scale(_timber(ctx, seed + 7, False, "orgdark", 0.11), 0.45 + 0.4 * T.smoothstep(0.0, 0.14, v - top))
    x, h = (u - u0) * SHELF_YD, CS.SHELVES[k] - v
    for cx in MUG_ROWS[k]:
        c = _mug_paint(c, x - cx - 0.018, h + 0.012, True)
    for cx in MUG_ROWS[k]:
        c = _mug_paint(c, x - cx, h, False)
    return c


def board(ctx, seed, k, v):
    """One plank of the top, unlit: dark rough timber with the grain along it (raw coordinates), its own tone,
    worn a little lighter in the middle where the cups slide, darker rounded long edges, a knot, and two nails
    every yard."""
    sub = _ctx(ctx, ctx.s, ctx.t, 1.0, 1.0, (0.0, 0.0, 1.0))
    c = T.g_wood(sub, seed + 11 * k, {"kind": "timber"})
    c = T.scale(c, (0.64, 0.74, 0.69)[k])
    c = T.mix(c, T.hexc("A07A4E"), T.smoothstep(0.3, 0.0, abs(v / BOARD_W - 0.5)) * 0.12)
    e = min(v, BOARD_W - v)
    if e < 0.03:
        c = T.mix(c, T.scale(c, 0.5), (0.03 - e) / 0.03 * 0.65)
    u = ctx.s % 1.0
    ku = (0.3, 0.72, 0.15)[k]
    kd = math.hypot((u - ku) / 1.8, v - BOARD_W * 0.45) / 0.016
    if kd < 1.0:
        c = T.mix(T.hexc("3A2210"), T.scale(c, 0.8), kd)
    elif kd < 1.7:
        c = T.mix(c, T.hexc("B08860"), (1.7 - kd) / 0.7 * 0.3)
    for nv in (0.05, BOARD_W - 0.05):
        du = ((u + 0.5) % 1.0) - 0.5
        c = T.rivet_dot(c, du, v - nv, 0.014, T.IRON_RIVET_HI, T.IRON_RIVET_LO)
    return c


def post_face(ctx, seed, s, k, front):
    """A crooked timber post's face (posts on the bay edges, corner posts), lit: dark grain up the post (s down it
    from the top), an iron band where each fascia strap crosses it (they wrap the posts too), a few hatchet nicks;
    k 0..1 across the face, front: an outward face (the sides are a little darker)."""
    sub = _ctx(ctx, ctx.s, ctx.t, 1.0, 1.0)
    c = T.g_wood(sub, seed, {"kind": "orgdark", "along": "s"})
    for v0, v1 in STRAPS:
        if v0 - 0.01 <= s < v1 + 0.01:
            c = _iron_strap(ctx, seed + 3, k * (POST_TW if front else SIDE_TW), s - v0 + 0.01, v1 - v0 + 0.02, 0.07)
            break
    else:
        nick = T.noise(ctx.s * 6.0, ctx.t * 30.0, seed + 5)
        if nick > 0.8:
            c = T.mix(c, T.hexc("A07448"), (nick - 0.8) * 2.5)
    if not front:
        c = T.scale(c, 0.85)
    return T.light(c, _face_light(BODY_Z1 - s, s, FACE_H - s))


# ------------------------------------------------------------------------------------------- tile paints

def p_panels(ctx, seed, p):
    """The `panels` tile (counters and back bars of Orgrimmar): the band nearest the texel's t, its edge rows
    repeated in the padding, and the light the bake would give."""
    u = ctx.s % PANEL_TILE[0]
    kind, v, _h = CS._band(ctx.t % PANEL_TILE[1], PANEL_BANDS, PANEL_TILE[1])
    if kind == "splash":
        return T.light(palisade(ctx, seed + 40, u, v), _face_light(H + SPLASH_H - v, 1.0, SPLASH_H - v) * 1.05)
    if kind == "cut":
        return T.light(cut_band(ctx, seed + 50, v), 1.02)
    if kind == "fascia":
        c = fascia_bay(ctx, seed, u, v, 1.0, FACE_H)
    elif kind == "doors":
        c = door_bay(ctx, seed + 20, u, v)
    else:
        c = shelf_bay(ctx, seed + 20, u, v)
    return T.light(c, _face_light(BODY_Z1 - v, v, FACE_H - v))


def p_top(ctx, seed, p):
    """The `top` tile: the three boards (lit as a top face), the riveted iron band, the post faces and the ends
    (a fascia bay END_W yd across from the tile's left edge, the rest of its rows repeating the nearer edge
    column, its depth squeezed into END_TH)."""
    kind, v, h = CS._band(ctx.t % TOP_TILE[1], TOP_BANDS, TOP_TILE[1])
    if kind.startswith("board"):
        return T.light(board(ctx, seed, int(kind[-1]), v), 1.04)
    if kind == "iron":
        return T.light(_iron_strap(ctx, seed + 5, ctx.s % 1.0, v, IRON_H), _face_light(0.5, 1.0, IRON_H - v) * 1.1)
    if kind in ("post", "side"):
        return post_face(ctx, seed + 9, min(ctx.s % TOP_TILE[0], FACE_H), v / h, kind == "post")
    u = ctx.s % TOP_TILE[0]
    ue = u if u <= END_W else (END_W if u < (END_W + TOP_TILE[0]) / 2 else 0.0)
    vv = v * FACE_H / END_TH
    return T.light(fascia_bay(ctx, seed + 13, ue, vv, END_W, FACE_H), _face_light(BODY_Z1 - vv, vv, FACE_H - vv))


def tiles():
    """The two tile textures of the Orgrimmar counters (BackBarOrg uses the same specs: the same bytes)."""
    return {"panels": {"paint": p_panels, "size": (256, 1024), "yards": PANEL_TILE, "seed": 41},
            "top": {"paint": p_top, "size": (256, 512), "yards": TOP_TILE, "seed": 43}}


def map_iron(z_top):
    """The tile mapping of an iron band (the plinth): the depth below z_top into the iron band; a top face onto
    the band's bright top lip, clear of the rivet row (t still runs a little with X, so the chart has an area in
    the texture)."""
    def fn(p, name):
        along = p[1] if name in ("+x", "+z") else (-p[1] if name == "-x" else p[0])
        if name == "+z":
            return (along, IRON_T + 0.006 + (p[0] + 0.45) * 0.01)
        return (along, IRON_T + min(IRON_H, max(0.0, z_top - p[2])))
    return fn


def map_posts(mesh, outer):
    """The `top` tile mapping of timber posts (CS.map_post with this tile's bands): the faces named in `outer` on
    the post band, the others on the side band."""
    return CS.map_post(mesh, outer, (POST_T, POST_TW), (SIDE_T, SIDE_TW))


def plank_top(w, d, seed, widths=BOARD_WIDTHS, dz=BOARD_DZ):
    """The top: three crooked boards `widths` wide (front, middle, back) with BOARD_GAP gaps (geom.plank_edges
    inward and a light wobble, as geom.planks), each standing dz above 1.05, their ends staggered by BOARD_ENDS,
    each on its own band of the `top` tile (the long edges and ends read the same board); and a dark plate just
    under them, so the gaps show shadow, not the floor through an open carcass."""
    out = []
    x0 = -d / 2
    for i in range(BOARDS):
        k = BOARDS - 1 - i            # the front board reads band 0
        bw = widths[k]
        y0, y1 = -w / 2 + BOARD_ENDS[k][0], w / 2 - BOARD_ENDS[k][1]
        zt = H + dz[k]
        b = G.translate(G.box(y1 - y0, bw, zt - TOP_Z0, faces="+x -x +y -y +z -z", z0=TOP_Z0), x0 + bw / 2,
                        (y0 + y1) / 2, 0.0)
        b = G.plank_edges(b, seed + 7 * i, 0.012, "y", inward=True)
        b = G.wobble(b, 0.004, seed + 13 * i)

        def fn(p, name, x0=x0, bw=bw, k=k, zt=zt):
            if name in ("+z", "-z"):
                return (p[1] + 0.37 * k, BOARD_T[k] + min(BOARD_W, max(0.0, (p[0] - x0) * BOARD_W / bw)))
            along = p[1] if name in ("+x", "-x") else p[0]
            return (along + 0.37 * k, BOARD_T[k] + 0.02 + (zt - p[2]) * 0.5)
        out.append(CS.retile(b, fn))
        x0 += bw + BOARD_GAP
    under = G.translate(G.box(w - 0.1, d - 0.06, 0.01, faces="+z", z0=TOP_Z0 - 0.002), 0.0, 0.0, 0.0)
    out.append(CS.retile(under, lambda p, name: (p[1], IRON_T + IRON_H * 0.95 + p[0] * 0.01)))
    return G.merge(out)


# --------------------------------------------------------------------------------------------- atlas paints

def p_tusk(ctx, seed, p):
    return T.g_bone(ctx, seed, {"root": 0, "cracks": 3})


def p_tusk_wrap(ctx, seed, p):
    """Leather wraps and lashings round the tusks, with a lit top edge and dark thong grooves round them."""
    c = T.g_leather(ctx, seed, {"color": T.hexc("5A2E18")})
    c = T.mix(c, T.hexc("A06A40"), T.clamp01(ctx.n[2]) * 0.4)
    if (ctx.t % 0.024) < 0.006:
        c = T.scale(c, 0.55)
    return c


def p_shield_side(ctx, seed, p):
    return T.g_hammered_iron(ctx, seed, {"rust": 0.2})


def p_plate(ctx, seed, p):
    """The iron corner plates: hammered iron with a rivet in each corner."""
    c = T.g_hammered_iron(ctx, seed, {"rust": 0.2})
    if ctx.chart == "+z":
        c = T.rivet_lines(ctx, c, rows=(0.025, ctx.ch - 0.025), step=ctx.cw - 0.05, r=0.014,
                          hi=T.IRON_RIVET_HI, lo=T.IRON_RIVET_LO, phase=0.025)
    return c


def p_spike(ctx, seed, p):
    """Iron spikes: dark iron, polished toward the point."""
    c = T.g_iron(ctx, seed, {"rust": 0.15})
    return T.mix(c, T.hexc("C8CCD4"), T.smoothstep(H + 0.08, H + 0.24, ctx.pos[2]) * 0.5)


def p_bronze(ctx, seed, p):
    return T.metal(ctx, seed, {"patina": 0.15, "hotspot": 0.8}, BRONZE["light_c"], BRONZE["base"], BRONZE["dark"],
                   BRONZE["bounce"], BRONZE["patina"], 0.15)


def p_bone(ctx, seed, p):
    """The yoke's uprights: ivory like the tusks (BONE_PAINT), with stained knuckle bands 0.06 tall where the
    swollen foot meets the shaft and just under the crossbar (the top joint itself is behind it), stained knuckle
    ends over the bar and a dark root end on the board, so they read as knuckled bone, not white posts."""
    c = T.g_bone(ctx, seed, {"color": BONE_PAINT, "cracks": 2})
    lz = ctx.pos[2] - BELL_Z
    for jz in (0.06, 0.29):
        d = abs(lz - jz)
        if d < 0.03:
            c = T.mix(c, T.hexc("6A4E2C"), 0.75 * T.smoothstep(0.03, 0.01, d))
    if lz > YOKE_H - 0.03:
        c = T.mix(c, T.hexc("8A6A40"), 0.4)
    if lz < 0.03:
        c = T.mix(c, T.hexc("4A3420"), 0.6 * T.smoothstep(0.03, 0.0, lz))
    return c


def p_crossbar(ctx, seed, p):
    """The yoke's crossbar: dark rough timber, lashed to the uprights with leather near its ends."""
    c = T.g_wood(ctx, seed, {"kind": "orgdark", "along": "s"})
    y = ctx.pos[1] - BELL[1]
    for e in (-YOKE_W / 2, YOKE_W / 2):
        if abs(y - e) < 0.045:
            c = T.g_leather(ctx, seed + 1, {"color": T.hexc("5A2E18")})
            if (y - e) % 0.02 < 0.005:
                c = T.scale(c, 0.55)
    return c


def _sack_neck_t():
    """The neck's place down the sack's lathe chart (t runs from the lip down the profile)."""
    pts = SACK_PROFILE
    k = next(i for i, q in enumerate(pts) if q[1] >= SACK_NECK)
    return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(k, len(pts) - 1))


def p_sack(ctx, seed, p):
    """The bean sack: light hessian (C8A878) with a coarse basket weave (0.02 cells) and broad folds down from the
    neck, a little darker where it slumps onto the board; a dark drawstring band 0.06 tall cinched round the
    neck, the cord's twist in it; the gathered lip above it a shade darker (the bake lights its top)."""
    c = T.mix(T.hexc("D6BA8C"), T.hexc("A8875A"), T.noise(ctx.s * 5.0, ctx.t * 5.0, seed))
    wu, wv = ctx.s / 0.02, ctx.t / 0.02
    fu, fv = wu - math.floor(wu), wv - math.floor(wv)
    over = (math.floor(wu) + math.floor(wv)) % 2 == 0
    c = T.scale(c, 0.84 + 0.2 * math.sin(math.pi * (fu if over else fv)))
    c = T.scale(c, 0.8 + 0.3 * T.noise(ctx.s * 9.0, ctx.t * 1.5, seed + 3))
    lz = ctx.pos[2] - H
    if lz < 0.04:
        c = T.scale(c, 0.8 + 0.2 * lz / 0.04)
    d = ctx.t - _sack_neck_t()
    if abs(d) < 0.03:
        q = (ctx.s / 0.035 + d / 0.03 * 0.5) % 1.0
        cord = T.mix(T.hexc("2A1A0E"), T.hexc("6A4A2A"), math.sin(math.pi * q))
        return T.scale(cord, 0.7 + 0.3 * T.smoothstep(0.03, 0.0, abs(d)))
    if d < 0.0:
        c = T.scale(c, 0.84)                # the gathered lip: the bake's key light already lifts its top
    elif d < 0.05:
        c = T.scale(c, 0.7 + 0.3 * d / 0.05)                            # bunched under the cord
    return c


def p_beans(ctx, seed, p):
    """Roasted beans heaped in the sack's mouth (each about 0.055 x 0.04), their tops lit from 6A3A1C to B07040
    so the heap reads against the hessian."""
    c = T.g_beans(ctx, seed, {"size": 0.055})
    if T.lum(c) < 0.1:
        return c
    k = T.clamp01(ctx.n[2] * 0.9 + 0.1)
    return T.mix(c, T.mix(T.hexc("6A3A1C"), T.hexc("B07040"), k), 0.45)


# ---------------------------------------------------------------------------------------------- decals

def d_sack(w, h):
    """The sack's stencil on its front: the coffee-cup line icon in faded red paint on the low belly (the side
    chart runs from the lip down to the foot; the belly is 0.38-0.74 of it)."""
    def draw(sw, sh):
        img = T.Img(sw, sh, (0, 0, 0, 0))
        size = min(sw, int(sh * 0.36))
        if size < 12:
            return img
        P2.paint_mask(img, E.line_mask("coffee", size, size, 10.0), LACQUER_DARK, (sw - size) // 2, int(sh * 0.38),
                      0.85)
        return img
    return P2.wrap_front(draw, 0.32)(w, h)


def d_shield(w, h):
    """The shield's face: red lacquer with a darker rim band and a soft lit upper left, a hammered-iron rim with
    eight rivets, the tusk_crest in bone relief."""
    img = T.Img(w, h, (0, 0, 0, 0))
    cx, cy, R = w / 2.0, h / 2.0, min(w, h) / 2.0
    for y in range(h):
        for x in range(w):
            dx, dy = (x + 0.5 - cx) / R, (y + 0.5 - cy) / R
            r = math.hypot(dx, dy)
            if r > 1.0:
                continue
            if r > 0.84:
                k = T.clamp01(0.5 - (dx + dy) * 0.4 + 0.15 * T.noise(x * 0.3, y * 0.3, 3))
                c = T.mix(T.hexc("1E1E22"), T.hexc("9EA2AA"), k)
                if r < 0.86 or r > 0.98:
                    c = T.scale(c, 0.5)
            else:
                c = T.mix(T.mix(LACQUER, T.hexc("E07858"), 0.35), LACQUER_DARK,
                          T.smoothstep(0.0, 1.0, math.hypot(dx + 0.35, dy + 0.35)))
                if r > 0.74:
                    c = T.scale(c, 0.72)
            img.set(x, y, c, 1.0)
    for i in range(8):
        a = i * math.pi / 4
        rx, ry = cx + math.cos(a) * R * 0.92, cy + math.sin(a) * R * 0.92
        rr = R * 0.06
        for y in range(int(ry - rr * 2), int(ry + rr * 2) + 1):
            for x in range(int(rx - rr * 2), int(rx + rr * 2) + 1):
                if 0 <= x < w and 0 <= y < h:
                    c = img.get(x, y)
                    img.set(x, y, T.rivet_dot(c[:3], (x + 0.5 - rx) / R * 0.19, (y + 0.5 - ry) / R * 0.19,
                                              rr / R * 0.19, T.IRON_RIVET_HI, T.IRON_RIVET_LO), c[3])
    s = int(R * 1.45)
    if s > 8:
        P2.composite(img, E.render_relief("tusk_crest", s, s, P2.BONE_RELIEF), int(cx - s / 2), int(cy - s / 2 +
                                                                                                    R * 0.02))
    return img


# ------------------------------------------------------------------------------------------------ parts

def crooked(mesh, seed, half_d=D / 2):
    """A timber post made crooked (geom.wobble by POST_WOBBLE, section 5.4's 1-2 cm), its X held inside the
    footprint (+-half_d): the back corner posts stand flush with the top's back edge, and a wobble past it would
    only grow the render depth."""
    m = G.wobble(mesh, POST_WOBBLE, seed)
    m.p = [(min(half_d, max(-half_d, x)), y, z) for x, y, z in m.p]
    return G.recompute_normals(m, 40.0)


def corner_posts(front_x, back_x, half_w, seed):
    """Crooked square timber posts on the four carcass corners, POST_OUT proud of both faces, on the `top` tile's
    post bands (the two outer faces on the post band)."""
    out = []
    k = 0
    for x, sx in ((front_x, 1), (back_x, -1)):
        for sy in (1, -1):
            cx, cy = x - sx * (POST / 2 - POST_OUT), sy * (half_w - POST / 2 + POST_OUT)
            b = G.translate(G.box(POST, POST, FACE_H, faces="+x -x +y -y", z0=BODY_Z0), cx, cy, 0.0)
            b = crooked(b, seed + k)
            out.append(map_posts(b, ("+x" if sx > 0 else "-x", "+y" if sy > 0 else "-y")))
            k += 1
    return G.merge(out)


def face_posts(front_x, back_x, front=(), back=(), seed=1):
    """Crooked timber posts on the carcass faces at the given Y (bay edges), on the `top` tile's post bands (the
    outer face on the post band, the sides on the side band)."""
    out = []
    k = 0
    for x, sx, ys in ((front_x, 1, front), (back_x, -1, back)):
        sgn = "+" if sx > 0 else "-"
        for y in ys:
            b = G.translate(G.box(PIL_W, PIL_D, FACE_H, faces=sgn + "x +y -y", z0=BODY_Z0), x + sx * PIL_D / 2, y,
                            0.0)
            out.append(map_posts(crooked(b, seed + 17 * k), (sgn + "x",)))
            k += 1
    return G.merge(out) if out else None


def tusk_path():
    """The +Y tusk's centre line: the horn's quadratic Bezier (geom.horn's bow) from TUSK_ROOT to TUSK_END, as
    (points, the end tangent, the root-to-end length)."""
    p0 = (TUSK_ROOT[0], TUSK_ROOT[1], TUSK_ROOT[2])
    d = G.sub(TUSK_END, p0)
    L = G.length(d)
    dn = G.mul(d, 1.0 / L)
    bend = (0.0, 1.0, -0.15)
    b = G.norm(G.sub(bend, G.mul(dn, G.dot(bend, dn))))
    mid = G.add(G.lerp(p0, TUSK_END, 0.5), G.mul(b, 0.2 * L))
    return G.bezier2_path(p0, mid, TUSK_END, 32), G.norm(G.sub(TUSK_END, mid))


def _on_path(path, z):
    """The point of a path at height z (linear between its samples), its tangent and its fraction of the arc."""
    arc = [0.0]
    for i in range(1, len(path)):
        arc.append(arc[-1] + G.length(G.sub(path[i], path[i - 1])))
    for i in range(1, len(path)):
        if path[i][2] >= z:
            f = (z - path[i - 1][2]) / (path[i][2] - path[i - 1][2])
            p = G.lerp(path[i - 1], path[i], f)
            return p, G.norm(G.sub(path[i], path[i - 1])), (arc[i - 1] + f * (arc[i] - arc[i - 1])) / arc[-1]
    return path[-1], G.norm(G.sub(path[-1], path[-2])), 1.0


def tusks():
    """The two ivory tusks and their leather, as (tusks, leather). Each tusk is one tube swept along geom.horn's
    curve (8 steps, tapering TUSK_R0 to TUSK_R1) and on along its end tangent into a blunt point TUSK_POINT long;
    no caps (the root is inside the plinth and the face, the point closes to 0.006). The leather: a wrap at the
    root, one at 0.40 and the lashing where the tusk passes through the top's front board."""
    path, tan = tusk_path()
    horn = path[::4]
    tip = G.add(TUSK_END, G.mul(tan, TUSK_POINT))
    arc = [0.0]
    for i in range(1, len(horn)):
        arc.append(arc[-1] + G.length(G.sub(horn[i], horn[i - 1])))
    k = arc[-1] / (arc[-1] + TUSK_POINT)            # the horn's share of the swept length

    def radius(t):
        if t <= k:
            return TUSK_R0 + (TUSK_R1 - TUSK_R0) * t / k
        return TUSK_R1 + (0.006 - TUSK_R1) * (t - k) / (1.0 - k)
    horns, leather = [], []
    for s in (1, -1):
        def flip(p, s=s):
            return (p[0], s * p[1], p[2])
        horns.append(G.sweep([flip(q) for q in horn + [tip]], radius, 8, name="horn"))
        for z, h in ((PLINTH_H + 0.045, 0.07), (0.40, 0.05), (0.985, 0.07)):
            p, t, f = _on_path(path, z)
            r = TUSK_R0 + (TUSK_R1 - TUSK_R0) * f + 0.013
            leather.append(G.transform(G.cylinder(r, h, 8, False, z0=-h / 2),
                                       G.mat_chain(G.mat_translate(*flip(p)), G.mat_look(flip(t)))))
    return G.merge(horns), G.merge(leather)


def bell_parts():
    """The bell yoke, at the origin on the board: two knuckled bone uprights YOKE_W apart (r 0.032-0.046), a
    timber crossbar through them under the knuckles, a flared bronze bell hanging from its middle (0.24 across
    the lip, its mouth a hollow, not a hole) and a clapper ball under the lip. Returns (bones, crossbar, bell,
    clapper)."""
    up = G.lathe([(0.046, 0.0), (0.034, 0.05), (0.032, 0.33), (0.046, 0.385), (0.0, YOKE_H)], 6)
    bones = G.merge([G.translate(up, 0.0, s * YOKE_W / 2, 0.0) for s in (1, -1)])
    bar_z = YOKE_H - 0.09
    bar = G.translate(G.box(YOKE_W + 0.12, 0.06, 0.06, faces="+x -x +y -y +z -z", z0=bar_z), 0.0, 0.0, 0.0)
    bar = G.plank_edges(bar, 5, 0.015, "y", inward=True)
    mouth = bar_z - 0.155
    bell = G.lathe([(0.0, 0.05), (0.1, 0.0), (0.122, 0.012), (0.085, 0.05), (0.07, 0.115), (0.05, 0.145),
                    (0.0, 0.156)], 10)
    clapper = G.sphere(0.032, 6, 3, z0=mouth - 0.045)
    return bones, bar, G.translate(bell, 0.0, 0.0, mouth), clapper


def _gather(mesh):
    """Gathers the sack's lip into five folds (on its ten sides, every other column in and out by 12 %), easing
    in above the neck: a sack's bunched mouth, which no pot has."""
    out = mesh.copy()
    pts = []
    for x, y, z in mesh.p:
        k = 1.0 + 0.12 * math.cos(5.0 * math.atan2(y, x)) * T.smoothstep(SACK_NECK, SACK_NECK + 0.04, z)
        pts.append((x * k, y * k, z))
    out.p = pts
    return G.recompute_normals(out, 40.0)


def _flop(mesh):
    """Tilts what is above the sack's neck by up to SACK_TILT degrees toward +X (the customers), easing in from
    just under the neck: the floppy rolled lip, and the beans heaped in it."""
    out = mesh.copy()
    pts = []
    for x, y, z in mesh.p:
        a = math.radians(SACK_TILT) * T.smoothstep(SACK_NECK - 0.04, SACK_NECK + 0.03, z)
        ca, sa = math.cos(a), math.sin(a)
        pts.append((x * ca + (z - SACK_NECK) * sa, y, SACK_NECK - x * sa + (z - SACK_NECK) * ca))
    out.p = pts
    return G.recompute_normals(out, 40.0)


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (W, D, H)
    d.render_size = (W, RENDER_D, RENDER_H)
    d.budget = 1000
    d.kind = "counter"
    d.atlas = {"atlas": 256}
    d.tiles = tiles()
    add = d.add
    hw = BODY_W / 2

    # the plank top (and the dark plate under its gaps)
    add(B.Part("top", plank_top(W, D, 51), texture="top"))

    # the carcass: hide fascia bays in front, plank cupboards behind (the panels tile), the ends (the top tile)
    long_faces = G.translate(G.box(BODY_W, FRONT_X - BACK_X, FACE_H, faces="+x -x", z0=BODY_Z0),
                             (FRONT_X + BACK_X) / 2, 0.0, 0.0)
    add(B.Part("carcass", CS.retile(long_faces, CS.map_face(BAND_F, BAND_D, BODY_Z1, BAY_Y, BAY_W)),
               texture="panels"))
    ends = G.translate(G.box(BODY_W, FRONT_X - BACK_X, FACE_H, faces="+y -y", z0=BODY_Z0),
                       (FRONT_X + BACK_X) / 2, 0.0, 0.0)
    add(B.Part("ends", CS.retile(ends, CS.map_end(FRONT_X, BACK_X, END_T, END_W, BODY_Z1, END_TH / FACE_H)),
               texture="top"))

    # the riveted iron plinth, crooked timber posts (the top tile's post bands)
    plinth = G.translate(G.box(BODY_W + 0.1, PLINTH_X1 - PLINTH_X0, PLINTH_H, faces="+x -x +y -y +z"),
                         (PLINTH_X0 + PLINTH_X1) / 2, 0.0, 0.0)
    add(B.Part("plinth", CS.retile(plinth, map_iron(PLINTH_H)), texture="top"))
    add(B.Part("posts", G.merge([corner_posts(FRONT_X, BACK_X, hw, 61), face_posts(FRONT_X, BACK_X, PILASTERS,
                                                                                   seed=67)]), texture="top"))

    # the two tusks: from the plinth on the centre bay's edges, arching in over the counter's edge, lashed with
    # leather at the root, halfway up and where they pass the top's front board
    horns, leather = tusks()
    add(B.Part("tusks", horns, paint=p_tusk, seed=71, weight=1.7))
    add(B.Part("tusk_wraps", leather, paint=p_tusk_wrap, seed=73, weight=0.7))

    # the crest shield on the centre bay
    shield = G.transform(G.cylinder(0.19, 0.035, 16, (False, True)),
                         G.mat_chain(G.mat_translate(FRONT_X - 0.002, 0.0, BODY_Z0 + FACE_H * 0.5), G.MAT_DISC_FRONT))
    for ch in shield.charts:
        ch.weight = 2.2 if ch.name == "cyl_top" else 0.6
    add(B.Part("shield", shield, paint=p_shield_side, seed=75, decals={"cyl_top": d_shield}))

    # the bell in its bone yoke on the front board
    bones, bar, bell, clapper = bell_parts()
    bx, by = BELL
    bz = BELL_Z
    add(B.Part("bell_yoke", G.translate(bones, bx, by, bz), paint=p_bone, seed=83, weight=1.2, ao_floor=0.7))
    add(B.Part("bell_bar", G.translate(bar, bx, by, bz), paint=p_crossbar, seed=89, weight=0.7, ao_floor=0.7))
    add(B.Part("bell", G.translate(G.merge([bell, clapper]), bx, by, bz), paint=p_bronze, seed=81, weight=1.4,
               ao_floor=0.7))

    # iron corner plates on the front board's ends, each with a spike standing up
    plates, spikes = [], []
    zf = H + BOARD_DZ[0]
    y_lo, y_hi = -W / 2 + BOARD_ENDS[0][0], W / 2 - BOARD_ENDS[0][1]
    for sy, cy in ((1, y_hi - 0.095), (-1, y_lo + 0.095)):
        cx = D / 2 - 0.085
        plates.append(G.translate(G.box(0.15, 0.15, 0.014, faces="+x -x +y -y +z", z0=zf - 0.002), cx, cy, 0.0))
        spikes.append(G.spike((cx, cy, zf + 0.012), (0.12, sy * 0.12, 1.0), 0.05, 0.22, 6))
    add(B.Part("corner_plates", G.merge(plates), paint=p_plate, seed=77, weight=0.4))
    add(B.Part("spikes", G.merge(spikes), paint=p_spike, seed=79, weight=0.6))

    # charm: a hessian sack of roasted beans on the middle board: a low belly, a pinched neck, a gathered, floppy
    # lip tilted toward the customers (no bottom: it stands on the board), a lumpy heap of beans in its mouth
    ox, oy = SACK
    sack = G.wobble(_flop(_gather(G.lathe(SACK_PROFILE, 10))), 0.015, 91)
    for ch in sack.charts:
        ch.weight = 1.1
    add(B.Part("sack", G.translate(sack, ox, oy, H - 0.004), paint=p_sack, seed=85, ao_floor=0.6,
               decals={0: d_sack}))
    beans = G.lathe([(0.105, 0.265), (0.085, 0.31), (0.045, 0.335), (0.0, 0.345)], 10)
    beans = G.wobble(G.wobble(_flop(beans), 0.015, 91), 0.008, 93, 14.0)
    add(B.Part("beans", G.translate(beans, ox, oy, H - 0.004), paint=p_beans, seed=87, weight=1.4, ao_floor=0.7))

    d.collision = G.hull_box(W, D, H)
    return d
