"""19312 CounterSW, the Stormwind serving counter, CAFE.SPEC.md section 5.8.1. M5.

A long, waist-high bar counter in walnut, royal-blue enamel, gold and white marble, front (+X) toward the
customers. What makes a player name it at a glance, from the front three-quarter view at 4-15 yd:
- the counter silhouette: a long body under a thick, overhanging white marble slab (0.09 thick, a 0.035 round on
  its edges, 0.105 over the fascia: a bright band of about 9 px at 10 yd with a painted dark line under it) on a
  two-step plinth;
- a brass foot rail along the customer side (0.06 thick, on the gold base blocks, ball finials resting on the
  corner posts' blocks): the bright line along the foot that says "bar counter" from 15 yd;
- the fascia: five bays of raised royal-blue enamel panels (real geometry, 0.03 proud, with gilded bevels) in
  painted gold frames (0.06) between chunky walnut pilasters (0.18 wide, 0.09 proud, the front corner posts as
  proud) standing on gold base blocks under stepped gold capitals (0.13 tall, the upper step reaching the slab's
  edge); each panel carries a gold steaming cup in relief (0.28 tall: about 27 px at 10 yd), and so do the
  ends (0.25 tall);
- a big brass service bell on the slab (0.37 across its base, 0.27 tall: about 30 px at 10 yd) with a chunky
  gold plunger (a 0.06 stem under a 0.08 ball);
- a gold lion medallion (0.40 across) on the centre panel, under the customer's eye;
- charm: a two-tier gold cake stand (0.42 across, on a rod 0.06 thick) with five iced cakes in pink,
  chocolate, mint and lemon and a pink layer cake crowned with a cherry (0.064 across).
The barista's side (-X) shows drawers with brass bar pulls (0.16 x 0.06) and double cupboard doors. The marble is
warm white with bold grey veins (0.03-0.04 wide, about 2.5 a yard along the slab) that still show at the 15 yd
mip. 5.0 (Y) x 0.8 (X) x 1.05 yd.

Textures (section 5.8: "256² (wrap) + 256² marble"): three of them. Two repeating tiles act as trim sheets and
are shared with BackBarSW (back_bar_sw.py builds byte-identical files from the same functions), and a baked
256² atlas carries the small parts:
- `panels` (256 x 1024, wrap, 256 texels a yard both ways): one bay across, five bands down (fascia bays,
  cupboard-door bays, the back bar's tiled backsplash, the back bar's open shelves of cups, the carcass ends).
  The long faces and the raised panels' fronts are mapped into their band with the bay stretched to fit between
  the corner posts (map_face), so every bay is whole; the ends read their band unstretched (map_end);
- `top` (256 x 512, wrap): marble (the slab), the foot rail's brass, the plinth's gold bead and walnut torus,
  the walnut toe, the posts' fluted faces and plain sides, and the gilt strip of the panel bevels and the back
  bar's shelf lips. Its marble repeats exactly across the tile, so the tile's seam blend leaves no ghost veins,
  and the slab reads it stretched by 1.618 so the bold vein never lines up with the bays;
- `atlas` (256², baked): capitals, base blocks, medallion, rail finials, bell and cake stand (the capitals, the
  base blocks and the finials weighted up, so they come closer to the walnut tiles beside them).
Tiles are not baked, so their paint carries the bake's gradient, key light, the shadow under the slab and the
contact at the plinth.

Deviations from the section 5.8.1 design:
- the tiles are 256 x 1024 and 256 x 512 (section 5.8 says 256²): a bay band is 0.86 yd tall, so a square tile
  gave the horizontal rails and frames half the texels of the vertical ones; the panels tile also holds the
  back bar's shelf and backsplash bands and the ends, the top tile the rail and plinth bands beside the marble;
  there is a third texture, the atlas;
- the bell sits at +Y 0.6 as designed, but 2.5x real size (r 0.15) so it reads at 10 yd; the render height is
  the cherry on the cake stand (render_size), the collision box keeps the 1.05 counter height; the rail's
  finials stand 0.015 beyond the slab, so the render depth is 0.815;
- raised panels between pilasters, a lion medallion on the centre bay, a foot rail and a stepped plinth (the
  design has plain framed panels): a counter 5 yd long needs relief, a rhythm and a focal point;
- the slab overhangs the fascia 0.105 (0.015 over the pilasters) and the back 0.05 (the design's 4 cm
  everywhere), so the marble edge throws a shadow line that reads at distance and the capitals fit under it;
- the cake stand is an addition (charm; it stands clear of the tip jar, the blender, the pickup cup and the
  lanterns of section 3.12.3). A glass cloche over the cakes was tried first: from 8 yd it read as a second,
  grey bell.
"""

import math

from .. import build as B
from .. import emblem as E
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "CounterSW"
DISPLAY = 19312

ENAMEL = T.hexc("2E4E8C")

W, D, H = 5.0, 0.8, 1.05
RENDER_D = 0.815                          # the rail finials stand 0.015 beyond the slab (render_size)
SLAB_H = 0.09
SLAB_Z0 = H - SLAB_H                      # 0.96
SLAB_BEVEL = 0.035
TOE_H, TORUS_H = 0.06, 0.04               # the plinth: a walnut toe under a gold-beaded walnut torus
PLINTH_H = TOE_H + TORUS_H
TOE_OUT, TORUS_OUT = 0.05, 0.03           # how far the two steps stand proud of the carcass faces
BODY_Z0, BODY_Z1 = PLINTH_H, SLAB_Z0      # the carcass faces, 0.86 tall
FACE_H = BODY_Z1 - BODY_Z0
FRONT_X, BACK_X = 0.295, -0.35            # carcass faces: the slab overhangs 0.105 in front (0.015 over the
                                          # pilasters), 0.05 behind
BODY_W = 4.88
POST, POST_OUT = 0.12, 0.04               # square corner posts, standing 0.04 proud of both faces
BAY_Y = BODY_W / 2 - POST + POST_OUT      # 2.36: the corner posts' inner faces, where the end bays stop
BAYS = 5
BAY_W = 2 * BAY_Y / BAYS                  # 0.944: five whole bays between the corner posts
PILASTERS = tuple(-BAY_Y + BAY_W * k for k in range(1, BAYS))   # bay edges: +-0.472, +-1.416
PIL_W, PIL_D = 0.18, 0.09                 # chunky pilasters; the front corner posts stand as proud
CAP_LO, CAP_HI = 0.07, 0.06               # two-step capitals, the upper step wider and reaching the slab's edge
BASE_W, BASE_D, BASE_H = 0.20, 0.105, 0.07  # gold base blocks on the plinth, under the pilasters
RAIL_X, RAIL_Z, RAIL_R = FRONT_X + 0.085, 0.175, 0.03
RAIL_Y = BAY_Y - 0.05                     # the finials rest on the corner posts' base blocks
KNOB_R = 0.04
BELL = (0.17, 0.6)                        # section 5.8.1: the bell at +Y 0.6
BELL_R = 0.15
CAKES = (0.1, -0.95)                      # the cake stand (clear of the order spot and the tip jar at -1.6)
END_W = FRONT_X - BACK_X                  # 0.645: the carcass ends, painted unstretched on the `end` band

# The `panels` tile (256 x 1024 wrap): one bay across, five bands down, in tile yards (256 texels a yard both
# ways). Band edges are padded by repeating the band's own edge rows, so filtering and mips never pull in the
# neighbouring band.
PANEL_TILE = (1.0, 4.0)
BAND_F, BAND_D, BAND_B, BAND_S, BAND_E = 0.015, 0.905, 1.795, 2.075, 2.965
SPLASH_H = 0.25
PANEL_BANDS = ((BAND_F, FACE_H, "fascia"),       # the counter front's bays
               (BAND_D, FACE_H, "doors"),        # cupboard bays: the barista sides
               (BAND_B, SPLASH_H, "splash"),     # the back bar's tiled backsplash
               (BAND_S, FACE_H, "shelves"),      # the back bar's two open end bays of cups
               (BAND_E, FACE_H, "end"))          # the carcass ends, END_W across, 1 u = 1 yd
# The `top` tile (256 x 512 wrap), in yards down: marble, the rail's round, the bead and torus, the toe, the
# posts' fluted faces and plain sides (s up the post), the gilt strip of the panel bevels, marble again.
TOP_TILE = (1.0, 2.0)
MARBLE_T = 0.01
RAIL_T, RAIL_TH = 0.88, 0.19              # the tube's circumference (r 0.03) at full scale
MOULD_T, MOULD_H = 1.10, 0.05
TOE_T = 1.18
POST_T, POST_TW = 1.27, PIL_W
SIDE_T, SIDE_TW = 1.48, PIL_D
GOLD_T, GOLD_TH = 1.60, 0.04
TOP_BANDS = ((MARBLE_T, 0.84, "marble"), (RAIL_T, RAIL_TH, "rail"), (MOULD_T, MOULD_H, "mould"),
             (TOE_T, TOE_H, "toe"), (POST_T, POST_TW, "post"), (SIDE_T, SIDE_TW, "side"), (GOLD_T, GOLD_TH, "gold"),
             (1.67, 0.33, "marble"))

# a fascia bay (u in tile units across the bay, v in yards down): walnut stiles and rails, the painted gold
# frame, the enamel field and the raised panel's footprint RAISE inside it (u, v)
STILE, RAIL_T_, RAIL_B_, FRAME = 0.106, 0.11, 0.12, 0.064
RAISE_U, RAISE_V = 0.032, 0.03
PANEL_D, PANEL_BEVEL = 0.03, 0.02         # the raised panels stand 0.03 proud, with 0.02 bevels
CUP_BOX = 0.36                            # the cup relief's square (yd); the cup and its steam fill 0.28 of it
END_CUP = 0.32                            # the ends' narrower fields take a smaller cup (0.25 tall)
# a door bay: the drawer row and the double doors (v ranges from the top of the face), door frames
DRAWERS = (0.07, 0.25)
DOORS = (0.30, 0.80)
DOOR_U = ((0.07, 0.495), (0.505, 0.93))
DOOR_FR, DOOR_BEAD = 0.055, 0.03          # the walnut door frame; the gold bead (the raised door panel's bevel)
GAP = 0.013
PULL_L, PULL_H, KNOB_PR = 0.16, 0.06, 0.038   # brass drawer bars and door knobs that read at 8 yd
# a shelf bay (the door bay's drawers over an opening in place of the doors): the shelf tops (v from the face's
# top; the gilt lips, geometry in back_bar_sw.py, hang LIP_H below each), the painted cups on them
SHELF_YD = 0.953                          # BackBarSW's bay width (back_bar_sw.BAY_W): yards per u on this band
SHELVES = (0.55, 0.77)
LIP_H = 0.05                              # the lower compartment keeps 0.17 for the 0.12 cups
CUP_ROWS = ((0.1025, 0.3075, 0.5125, 0.7175), (0.17, 0.41, 0.65))   # cup axes, yd from the opening's left edge


# ----------------------------------------------------------------------------------------------- helpers

def _ctx(ctx, s, t, cw, ch, n=(1.0, 0.0, 0.0)):
    """A context for a sub-rectangle of the texel's chart (a panel, a door), so a generator's gloss band, chips
    and inset lines follow that rectangle. Noise still comes from the texel's own position."""
    return T.Ctx(s, t, ctx.pos, n, ctx.curv, 1.0, cw, ch, ctx.chart, ctx.part)


def _moulding_n(side, k):
    """The normal across a raised moulding (k 0 at its outer edge, 1 at its inner edge) on a front face; side:
    the strip's outward direction in the face plane, (right, up). Outer bevel, flat top, inner bevel."""
    sl = 0.9 if k < 0.35 else (-0.9 if k > 0.65 else 0.0)
    return G.norm((1.0, side[0] * sl, side[1] * sl))


def _walnut(ctx, seed, vertical):
    """Walnut with its grain along the board: raw chart coordinates, so the grain runs on across tile edges."""
    sub = _ctx(ctx, ctx.s, ctx.t, 1.0, 1.0)
    return T.g_wood(sub, seed, {"kind": "walnut", "along": "t" if vertical else "s"})


def _gold(ctx, seed, n):
    return T.g_gold(_ctx(ctx, ctx.s, ctx.t, 1.0, 1.0, n), seed, {"streak": False, "patina": 0.04, "hotspot": 0})


def _brass_knob(c, du, dv, r):
    """A painted brass knob seen from the front at offset (du, dv) yd (dv downward): lit upper left, a dark rim
    and a drop shadow toward the lower right. Outside it, c is returned unchanged."""
    d = math.hypot(du, dv)
    if d < r:
        k = T.clamp01(0.62 - (du + dv) / r * 0.5)
        c0 = T.mix(T.hexc("8A5A12"), T.hexc("F2C85A"), k)
        return T.mix(c0, T.hexc("FFF4C0"), T.smoothstep(0.55, 0.15, math.hypot(du + r * 0.35, dv + r * 0.35) / r))
    if d < r * 1.25:
        return T.mix(c, T.hexc("2A1606"), 0.7)
    sd = math.hypot(du - r * 0.4, dv - r * 0.5)
    if sd < r * 1.3:
        return T.mix(c, T.scale(c, 0.5), T.smoothstep(r * 1.3, r * 0.8, sd) * 0.6)
    return c


def _face_light(z, v, bottom):
    """What the bake gives a front face of a floor piece at height z (bake.light_factor's gradient and key
    light), with the shadow under the slab over the top of the face (v from the face's top) and the contact
    shadow `bottom` yd above the face's lower edge."""
    zr = T.clamp01(z / 1.2)
    k = (0.75 + 0.40 * zr * zr * (3 - 2 * zr)) * 0.92
    k *= 1.0 - 0.42 * T.smoothstep(0.10, 0.0, v)
    k *= 1.0 - 0.45 * T.smoothstep(0.026, 0.016, v)      # the crisp dark line right under the slab's edge
    k *= 1.0 - 0.3 * T.smoothstep(0.06, 0.0, bottom)
    return k


def _band(t, bands, period):
    """(kind, v, h) of the band of a trim-sheet tile nearest t: bands are (t0, h, kind) rows top to bottom, v the
    depth into the band clamped to it, so a texel in the padding repeats the nearer band's edge row; past the
    last band the tile wraps to the first one's top row."""
    for i, (t0, h, kind) in enumerate(bands):
        nxt = bands[i + 1][0] if i + 1 < len(bands) else period + bands[0][0]
        if t < (t0 + h + nxt) / 2:
            return kind, min(max(t - t0, 0.0), h), h
    return bands[0][2], 0.0, bands[0][1]


def _pnoise(x, y, px, py, seed):
    """Value noise that repeats every px cells along x and py cells along y, so a tile painted with it has no
    seam for tex.tile_image's edge blend to hide (and no ghost of the blend)."""
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    ux = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
    uy = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
    a = T._h(ix % px, iy % py, 0, seed)
    b = T._h((ix + 1) % px, iy % py, 0, seed)
    c = T._h(ix % px, (iy + 1) % py, 0, seed)
    d = T._h((ix + 1) % px, (iy + 1) % py, 0, seed)
    top = a + (b - a) * ux
    return top + (c + (d - c) * ux - top) * uy


def _pfbm(x, y, px, py, seed, octaves=3):
    """Three octaves of _pnoise, each repeating on the same tile."""
    s, n, a, f = 0.0, 0.0, 1.0, 1
    for o in range(octaves):
        s += a * _pnoise(x * f, y * f, px * f, py * f, seed + 31 * o)
        n += a
        a *= 0.5
        f *= 2
    return s / n


_CUP = []


def _cup_relief():
    """The gold steaming-cup relief of the fascia panels, rendered once per process (emblem `cup`)."""
    if not _CUP:
        _CUP.append(E.render_relief("cup", 96, 96, P2.GOLD_RELIEF))
    return _CUP[0]


def _sample(img, fx, fy):
    """A bilinear sample of an Img at (fx, fy) in 0..1 across it, or None outside it."""
    if not (0.0 <= fx < 1.0 and 0.0 <= fy < 1.0):
        return None
    x, y = fx * img.w - 0.5, fy * img.h - 0.5
    x0, y0 = max(0, int(math.floor(x))), max(0, int(math.floor(y)))
    x1, y1 = min(img.w - 1, x0 + 1), min(img.h - 1, y0 + 1)
    ax, ay = T.clamp01(x - x0), T.clamp01(y - y0)
    q = [img.get(x0, y0), img.get(x1, y0), img.get(x0, y1), img.get(x1, y1)]
    return tuple((q[0][i] * (1 - ax) + q[1][i] * ax) * (1 - ay) + (q[2][i] * (1 - ax) + q[3][i] * ax) * ay
                 for i in range(4))


# ------------------------------------------------------------------------------------------ bay painters

def fascia_bay(ctx, seed, u, v, bw, bh, emblem=True, yd=BAY_W, cup=CUP_BOX):
    """One bay of the counter front, unlit: walnut stiles (vertical grain) and rails, a painted gold frame, the
    royal-blue enamel field with a dark groove at the gold, a darker recess round the raised panel's footprint
    with the panel's shadow below and right of it, and (emblem) the gold steaming cup in the panel's middle.
    u across (0..bw) and v down (0..bh), in tile units across (yd yards each, so the cup keeps its shape) and
    yards down; `cup` the relief's square in yards. The ends use it too (no raised panel there: the recess reads
    as a painted one)."""
    dl, dr, dt, db = u - STILE, bw - STILE - u, v - RAIL_T_, bh - RAIL_B_ - v
    e = min(dl, dr, dt, db)
    if e < 0.0:
        c = _walnut(ctx, seed, min(dl, dr) < 0.0 and dt > -0.02 and db > -0.02)
        # the frame's shadow on the walnut below it and to its right
        if e > -0.016 and (db < 0.0 or dr < 0.0) and min(dl, dt) > -0.016:
            c = T.mix(c, T.scale(c, 0.45), T.smoothstep(-0.016, 0.0, e) * 0.8)
        elif e > -0.008:
            c = T.mix(c, T.hexc("D8B070"), 0.25)
        return c
    if e < FRAME:
        side = (0.0, 1.0) if e == dt else ((0.0, -1.0) if e == db else ((-1.0, 0.0) if e == dl else (1.0, 0.0)))
        return _gold(ctx, seed + 2, _moulding_n(side, e / FRAME))
    pu, pv = u - STILE - FRAME, v - RAIL_T_ - FRAME
    pw, ph = bw - 2 * (STILE + FRAME), bh - RAIL_T_ - RAIL_B_ - 2 * FRAME
    sub = _ctx(ctx, pu, pv, pw, ph)
    c = T.g_enamel(sub, seed + 5, {"color": ENAMEL, "chips": 0, "gloss": 0.3})
    ri = min(pu - RAISE_U, pw - RAISE_U - pu, pv - RAISE_V, ph - RAISE_V - pv)
    if ri < 0.0:
        # the recess round the raised panel; its shadow falls to the right and below (light from upper left)
        c = T.scale(c, 0.8)
        if pu > pw - RAISE_U - 0.004 or pv > ph - RAISE_V - 0.004:
            c = T.mix(c, T.hexc("0A1226"), 0.55 * T.smoothstep(-0.03, -0.004, ri))
    if e < FRAME + 0.012:
        c = T.mix(c, T.hexc("0E1830"), 0.7)
    if emblem:
        rel = _sample(_cup_relief(), (pu - pw / 2) / (cup / yd) + 0.5, (pv - ph / 2) / cup + 0.5)
        if rel and rel[3] > 0.0:
            c = T.mix(c, rel[:3], rel[3])
    return c


def door_bay(ctx, seed, u, v, bw):
    """One bay of cupboards, unlit: a row of two drawers with brass bar pulls over a pair of walnut doors with
    gold-beaded royal-blue panels and brass knobs, dark gaps with a lit lower lip, walnut carcass between. The
    bead is DOOR_BEAD wide: where BackBarSW raises the door panels, their gilded bevels stand on it."""
    for i, (u0, u1) in enumerate(DOOR_U):
        for v0, v1, door in ((DRAWERS[0], DRAWERS[1], False), (DOORS[0], DOORS[1], True)):
            if not (u0 - GAP <= u <= u1 + GAP and v0 - GAP <= v <= v1 + GAP):
                continue
            if u < u0 or u > u1 or v < v0 or v > v1:
                return T.hexc("140A04") if v < v1 else T.hexc("A07448")      # the gap, its lit lower lip
            lu, lv, lw, lh = u - u0, v - v0, u1 - u0, v1 - v0
            sub = _ctx(ctx, lu, lv, lw, lh)
            if not door:
                c = _walnut(ctx, seed + 7, False)
                c = T.inset_panel(sub, c, 0.022, 0.012, True)
                # the brass bar pull: lit along its top, dark below, its shadow on the drawer front
                du, dv = lu - lw / 2, lv - lh / 2
                ph = PULL_H / 2
                if abs(du) < PULL_L / 2 and abs(dv) < ph:
                    k = T.clamp01(0.7 - dv / ph * 0.6)
                    c = T.mix(T.hexc("8A5A12"), T.hexc("FFE89A"), k)
                    if abs(du) > PULL_L / 2 - 0.012:
                        c = T.scale(c, 0.7)                  # the posts that hold the bar off the drawer
                elif abs(du) < PULL_L / 2 + 0.006 and ph <= dv < ph + 0.014:
                    c = T.scale(c, 0.5)
                return c
            fr, bd = DOOR_FR, DOOR_BEAD
            e = min(lu, lw - lu, lv, lh - lv)
            if e < fr:
                c = _walnut(ctx, seed + 9, min(lu, lw - lu) < fr and fr < lv < lh - fr)
                if e < 0.01:
                    c = T.mix(c, T.hexc("C89A60"), 0.35)
            elif e < fr + bd:
                ed = (lu, lw - lu, lv, lh - lv)
                k = ed.index(e)
                side = ((-1.0, 0.0), (1.0, 0.0), (0.0, 1.0), (0.0, -1.0))[k]
                c = _gold(ctx, seed + 4, _moulding_n(side, (e - fr) / bd))
            else:
                pan = _ctx(ctx, lu - fr - bd, lv - fr - bd, lw - 2 * (fr + bd), lh - 2 * (fr + bd))
                c = T.g_enamel(pan, seed + 6 + i, {"color": ENAMEL, "chips": 0, "gloss": 0.3})
                if e < fr + bd + 0.012:
                    c = T.mix(c, T.hexc("0E1830"), 0.6)
            ku = (lw - 0.055) if i == 0 else 0.055
            return _brass_knob(c, lu - ku, lv - 0.24, KNOB_PR)
    return _walnut(ctx, seed, u < DOOR_U[0][0] or u > DOOR_U[1][1])


def _cup_paint(c, dx, h, shadow):
    """A white porcelain cup on its saucer painted on a wall, seen from the front: dx yd right of its axis, h yd
    above the shelf. Lit from the upper left: a grey core shadow down its right side, a royal-blue band, a gold
    rim line, the handle on the right. With `shadow` it returns the cup's drop shadow on the wall instead (the
    caller offsets dx and h). Outside the cup, c is returned unchanged."""
    if h < 0.0:
        return c
    if h < 0.016 and abs(dx) < 0.076 - (0.016 - h) * 0.8:
        if shadow:
            return T.scale(c, 0.55)
        return T.mix(T.hexc("9A9EAC"), T.hexc("FFFFFF"), T.smoothstep(0.0, 0.016, h) * 0.9)
    if 0.016 <= h < 0.12:
        f = (h - 0.016) / 0.104
        hw = 0.040 + 0.017 * f
        if abs(dx) < hw:
            if shadow:
                return T.scale(c, 0.55)
            k = dx / hw
            col = T.mix(T.hexc("FFFFFC"), T.hexc("A8AEC2"), T.smoothstep(-0.3, 1.0, k))
            if 0.048 < h < 0.074:
                col = T.mix(T.mix(ENAMEL, T.hexc("5A82C8"), 0.4), T.scale(ENAMEL, 0.6), T.smoothstep(-0.3, 1.0, k))
            elif 0.106 < h < 0.113:
                col = T.mix(T.hexc("FFE08A"), T.hexc("8A6018"), T.smoothstep(-0.3, 1.0, k))
            return col
        hd = math.hypot(dx - 0.064, h - 0.07)
        if dx > 0.0 and 0.013 < hd < 0.03:
            if shadow:
                return T.scale(c, 0.55)
            return T.mix(T.hexc("F4F4F0"), T.hexc("9A9EAC"), T.clamp01((h - 0.07) / -0.03 * 0.5 + 0.5))
    return c


def shelf_bay(ctx, seed, u, v):
    """One bay of open shelves (BackBarSW's two end bays), unlit: the door bay's drawer row over an opening in the
    walnut carcass where the doors would be. Inside: a royal-blue back wall in shadow (darkest under each shelf),
    walnut reveals, and on each of the two shelves a row of white porcelain cups on saucers, 0.12 tall, with
    their drop shadows; the shelves' gilt lips are geometry (back_bar_sw.py). u in tile units (SHELF_YD yards
    each), v in yards down."""
    u0, u1 = DOOR_U[0][0], DOOR_U[1][1]
    v0, v1 = DOORS
    if v < v0 - GAP or v > v1 + 0.03 or u < u0 - 0.03 or u > u1 + 0.03:
        return door_bay(ctx, seed, u, v, 1.0)
    e = min(u - u0, u1 - u, v - v0, v1 - v)
    if e < 0.0:
        # the opening's edge: walnut with a lit arris round it
        c = _walnut(ctx, seed + 3, u < u0 or u > u1)
        return T.mix(c, T.hexc("C89A60"), 0.4) if e > -0.01 else c
    # the reveals: the opening's inner walls seen in perspective (the top one in shadow, the left one lit)
    if v - v0 < 0.035 and v - v0 <= min(u - u0, u1 - u):
        return T.scale(_walnut(ctx, seed + 5, False), 0.35)
    if u - u0 < 0.03:
        return T.scale(_walnut(ctx, seed + 5, True), 0.75)
    if u1 - u < 0.03:
        return T.scale(_walnut(ctx, seed + 5, True), 0.45)
    # the shelf boards behind the lips
    if SHELVES[0] <= v < SHELVES[0] + LIP_H or v > SHELVES[1]:
        return T.scale(_walnut(ctx, seed + 5, False), 0.5)
    # the back wall: blue enamel, darkest just under the shelf above each compartment
    k = 0 if v < SHELVES[0] else 1
    top = v0 if k == 0 else SHELVES[0] + LIP_H
    shade = 0.45 + 0.35 * T.smoothstep(0.0, 0.12, v - top)
    c = T.scale(T.mix(ENAMEL, T.hexc("3A64A8"), 0.25 * T.noise(ctx.s * 9.0, ctx.t * 9.0, seed + 7)), shade)
    # the cups, their drop shadows first (toward the lower right)
    x, h = (u - u0) * SHELF_YD, SHELVES[k] - v
    for cx in CUP_ROWS[k]:
        c = _cup_paint(c, x - cx - 0.018, h + 0.012, True)
    for cx in CUP_ROWS[k]:
        c = _cup_paint(c, x - cx, h, False)
    return c


def splash_bay(ctx, seed, u, v):
    """The back bar's backsplash, unlit: one row of large glazed tiles 0.25 yd square, white with a single
    royal-blue line 0.02 wide inset round each and a blue dot on every grout cross (half dots along the slab
    and the cap rail), grey grout, each tile with its own glaze sheen. Calm, so the machines stand out in
    front of it."""
    ts = 0.25
    i = int(math.floor(u / ts))
    lu, lv = u - i * ts, v
    g = 0.008
    dc = min(math.hypot(lu - a, lv - b) for a in (0.0, ts) for b in (0.0, ts))
    if dc < 0.03:
        return T.mix(ENAMEL, T.hexc("6F95D0"), T.clamp01(0.45 - (lu + lv - ts) / 0.06) * 0.5)
    if min(lu, ts - lu, lv, ts - lv) < g / 2:
        return T.hexc("8A8A86")
    white = T.mix(T.hexc("F4F0E4"), T.hexc("E4E6EC"), T._h(i, 1, 3, seed))
    c = T.mix(white, T.hexc("FFFFFF"), T.smoothstep(0.08, 0.0, lv) * 0.3)
    c = T.scale(c, 0.96 + 0.05 * T.noise(ctx.s * 7.0, ctx.t * 7.0, seed))
    e = min(lu, ts - lu, lv, ts - lv)
    if 0.03 <= e < 0.05:
        c = T.mix(ENAMEL, T.hexc("3F6FB5"), 0.25)
    return c


def mould_band(ctx, seed, v):
    """The bead-and-torus moulding (the plinth's upper step, the back bar's cap rail), unlit, v down from its
    top (0..MOULD_H): a round gold bead lit on top, a dark groove, a walnut torus lit above and dark below."""
    if v < 0.016:
        return _gold(ctx, seed + 2, G.norm((1.0, 0.0, 1.2 - v / 0.016 * 2.4)))
    if v < 0.021:
        return T.hexc("1A0E06")
    c = _walnut(ctx, seed, False)
    k = (v - 0.021) / (MOULD_H - 0.021)
    c = T.mix(c, T.hexc("B88A58"), T.smoothstep(0.5, 0.1, k) * 0.35)
    return T.mix(c, T.scale(c, 0.5), T.smoothstep(0.55, 1.0, k) * 0.55)


def toe_band(ctx, seed, v):
    """The plinth's walnut toe, unlit, v down from its top (0..TOE_H): a lit chamfer along the top edge, then
    walnut darkening to the floor."""
    c = _walnut(ctx, seed, False)
    if v < 0.008:
        return T.mix(c, T.hexc("C09060"), 0.4)
    return T.mix(c, T.scale(c, 0.55), T.smoothstep(0.02, TOE_H, v) * 0.45)


def rail_band(ctx, seed, k):
    """The foot rail's polished brass round, unlit: k 0..1 round the tube from its top (0.25 faces the
    customers, 0.5 the floor), shaded by the tube's own normal."""
    a = k * 2.0 * math.pi
    n = (math.sin(a), 0.0, math.cos(a))
    c = T.g_brass(_ctx(ctx, ctx.s, ctx.t, 1.0, 1.0, n), seed, {"streak": True, "patina": 0.05, "hotspot": 0.9})
    return T.scale(c, 0.85 + 0.25 * max(0.0, n[2]) - 0.25 * max(0.0, -n[2]))


def post_band(ctx, seed, s, k, fluted):
    """A walnut post face (pilasters and corner posts), unlit: s down the post from under the slab, k 0..1
    across it; grain up the post, three dark flutes with lit edges on the fluted faces, a gold collar at the
    foot (under the base blocks where they stand), and the light the bake would give."""
    c = _walnut(ctx, seed, False)
    if not fluted:
        c = T.scale(c, 0.86)
    elif 0.1 < s < FACE_H - 0.1:
        for f in (0.3, 0.5, 0.7):
            d = abs(k - f)
            if d < 0.067:
                c = T.mix(c, T.hexc("1A0E06"), 0.75 * T.smoothstep(0.067, 0.02, d))
            elif d < 0.107 and k > f:
                c = T.mix(c, T.hexc("C09060"), 0.4)
    if s > FACE_H - 0.05:
        c = _gold(ctx, seed + 1, G.norm((1.0, 0.0, 0.4 if s < FACE_H - 0.04 else -0.6)))
    return T.light(c, _face_light(BODY_Z1 - s, s, FACE_H - s))


def gold_strip(ctx, seed, v):
    """The gilt strip of the raised panels' bevels (v across it): polished gold with a soft sheen down the
    middle; the client's light shades each bevel by its slope."""
    c = _gold(ctx, seed, (1.0, 0.0, 0.3))
    return T.mix(c, T.hexc("FFF2B0"), T.smoothstep(GOLD_TH * 0.5, 0.0, abs(v - GOLD_TH * 0.5)) * 0.25)


def marble(ctx, seed):
    """Warm white marble that repeats exactly on the `top` tile: soft warm-grey clouds; bold grey veins running
    diagonally across the slab (about 2.5 a yard along it, which reads the tile stretched by 1.618), wandering,
    swelling and fading out in places, with a soft halo and about 0.035 wide where they are strongest, so they
    hold at the 15 yd mip (2-3 px) and the slab reads as stone, not white plastic; a fainter family crossing
    them, and hairline veins."""
    x, z = ctx.s / TOP_TILE[0], ctx.t / TOP_TILE[1] * 2.0        # one cell of the repeating noise per yard
    base = T.hexc("F0E8D8")
    c = T.mix(base, T.hexc("D8D0C2"), T.smoothstep(0.45, 0.8, _pfbm(x * 3.0, z * 3.0, 3, 6, seed + 1)) * 0.6)
    # whole multiples of x and half multiples of z keep each family on the tile's repeat; on the slab theta's
    # gradient is about 11 a yard, so |sin| < 0.19 is 0.035 yd across
    for fx, fz, warp, core, amt, f0, sd in ((4.0, 2.5, 3.8, 0.19, 0.75, 0.3, 0), (2.0, -1.5, 2.6, 0.08, 0.3, 0.5, 10)):
        w = _pfbm(x * 2.0, z * 2.0, 2, 4, seed + sd)
        v = abs(math.sin(math.pi * (fx * x + fz * z) + w * warp))
        fade = T.smoothstep(f0, f0 + 0.3, _pfbm(x * 2.0, z * 2.0, 2, 4, seed + 3 + sd, 2))
        c = T.mix(c, T.hexc("B6B2AE"), T.smoothstep(core * 3.0, core, v) * 0.3 * fade)
        c = T.mix(c, T.hexc("767884"), T.smoothstep(core * 1.3, core * 0.5, v) * amt * fade)
    w2 = _pfbm(x * 4.0, z * 4.0, 4, 8, seed + 2, 2)
    v2 = abs(math.sin(math.pi * (2.0 * x - 0.5 * z) + w2 * 2.4))
    return T.mix(c, T.hexc("A4A2A8"), T.smoothstep(0.04, 0.0, v2) * 0.2)


# ------------------------------------------------------------------------------------------- tile paints

def p_panels(ctx, seed, p):
    """The `panels` tile (counters and back bars of Stormwind): the band nearest the texel's t, with that band's
    edge rows repeated in the padding, and the light the bake would have given."""
    u = ctx.s % PANEL_TILE[0]
    kind, v, _h = _band(ctx.t % PANEL_TILE[1], PANEL_BANDS, PANEL_TILE[1])
    if kind == "splash":
        k = _face_light(H + SPLASH_H - v, v * 0.6, SPLASH_H - v) * 1.05
        return T.light(splash_bay(ctx, seed + 40, u, v), k)
    if kind == "fascia":
        c = fascia_bay(ctx, seed, u, v, PANEL_TILE[0], FACE_H)
    elif kind == "doors":
        c = door_bay(ctx, seed + 20, u, v, PANEL_TILE[0])
    elif kind == "shelves":
        c = shelf_bay(ctx, seed + 20, u, v)
    else:
        # the ends: END_W yd across from the tile's left edge; the rest of the row repeats the nearer edge column
        # (the left one past the middle of the spare width, which is what wraps round to it)
        ue = u if u <= END_W else (END_W if u < (END_W + PANEL_TILE[0]) / 2 else 0.0)
        c = fascia_bay(ctx, seed + 60, ue, v, END_W, FACE_H, yd=1.0, cup=END_CUP)
    return T.light(c, _face_light(BODY_Z1 - v, v, FACE_H - v))


def p_top(ctx, seed, p):
    """The `top` tile: the band nearest the texel's t (its edge rows repeated in the padding): marble (the slab,
    lit like a top face), the rail's brass round, the bead-and-torus and toe bands (lit like low front faces),
    the post faces and the bevels' gilt strip."""
    kind, v, h = _band(ctx.t % TOP_TILE[1], TOP_BANDS, TOP_TILE[1])
    if kind == "marble":
        return T.light(marble(ctx, seed), 1.06)
    if kind == "rail":
        return T.light(rail_band(ctx, seed + 3, v / RAIL_TH), 0.98)
    if kind == "mould":
        return T.light(mould_band(ctx, seed + 5, v), _face_light(0.3, 1.0, 1.0) * 1.05)
    if kind == "toe":
        return T.light(toe_band(ctx, seed + 7, v), _face_light(0.1, 1.0, TOE_H - v) * 1.05)
    if kind in ("post", "side"):
        return post_band(ctx, seed + 9, min(ctx.s % TOP_TILE[0], FACE_H), v / h, kind == "post")
    return T.light(gold_strip(ctx, seed + 11, v), 1.0)


def tiles():
    """The two tile textures of the Stormwind counters (BackBarSW uses the same specs: the same bytes)."""
    return {"panels": {"paint": p_panels, "size": (256, 1024), "yards": PANEL_TILE, "seed": 31},
            "top": {"paint": p_top, "size": (256, 512), "yards": TOP_TILE, "seed": 37}}


def retile(mesh, fn):
    """Rewrites every vertex's chart (s, t) to fn(position, chart name), in tile yards: the trim-sheet mapping
    of a part on a tile (build.py maps uv = st / yards)."""
    for v in range(len(mesh.p)):
        mesh.st[v] = fn(mesh.p[v], mesh.charts[mesh.c[v]].name)
    return mesh


def map_face(front_band, back_band, z_top, bay_y, bay_w):
    """The tile mapping of a carcass's long faces (and of anything raised on them): the +x face reads left to
    right along +Y, the -x face along -Y, with the bays stretched to fill the 2 * bay_y between the corner
    posts' inner faces (a whole number of bay_w bays, one tile across each); t is the band plus the depth
    below z_top."""
    def fn(p, name):
        if name == "+x":
            return ((p[1] + bay_y) / bay_w, front_band + (z_top - p[2]))
        return ((bay_y - p[1]) / bay_w, back_band + (z_top - p[2]))
    return fn


def map_moulding(z_top, h):
    """The tile mapping of a bead-and-torus moulding h tall (the plinth's upper step, a cap rail): its faces
    stretched over the moulding band, its top face onto the walnut torus (t still runs a little with X: a
    chart with no area in the texture breaks the preview's texel-density view)."""
    def fn(p, name):
        along = p[1] if name in ("+x", "+z", "-z") else (-p[1] if name == "-x" else (
            p[0] if name == "-y" else -p[0]))
        if name in ("+z", "-z"):
            return (along, MOULD_T + MOULD_H * 0.7 + p[0] * 0.02)
        return (along, MOULD_T + min(MOULD_H, max(0.0, (z_top - p[2]) * MOULD_H / h)))
    return fn


def map_toe():
    """The tile mapping of the plinth's toe: its faces into the toe band, its top ledge onto the lit chamfer."""
    def fn(p, name):
        along = p[1] if name in ("+x", "+z") else (-p[1] if name == "-x" else (p[0] if name == "-y" else -p[0]))
        if name == "+z":
            return (along, TOE_T + 0.002 + p[0] * 0.01)
        return (along, TOE_T + min(TOE_H, max(0.0, TOE_H - p[2])))
    return fn


def map_tube(mesh, t0, th):
    """The tile mapping of a tube swept along Y (the foot rail): s along Y, t round the tube into the band
    [t0, t0 + th] (from the sweep chart's own s, so the seam column keeps its own end of the band)."""
    for v in range(len(mesh.p)):
        ch = mesh.charts[mesh.c[v]]
        mesh.st[v] = (mesh.p[v][1], t0 + mesh.st[v][0] / ch.w * th)
    return mesh


def map_post(mesh, fluted, post=(POST_T, POST_TW), side=(SIDE_T, SIDE_TW)):
    """The tile mapping of upright boxes on the post bands (pilasters, corner posts): s down the post (the box
    chart's own t), t across the face into the `post` band (t0, width) for the faces named in `fluted` and into
    the plain `side` band for the others (CounterOrg passes its own bands)."""
    for v in range(len(mesh.p)):
        ch = mesh.charts[mesh.c[v]]
        s0, t0 = mesh.st[v]
        b0, bw = post if ch.name in fluted else side
        mesh.st[v] = (t0, b0 + s0 / ch.w * bw)
    return mesh


def map_end(front_x, back_x, band=BAND_E, end_w=END_W, z_top=BODY_Z1, k=1.0):
    """The tile mapping of a carcass's two end faces: across each end as seen from outside (the +y end reads
    toward -X), stretched over end_w tile yards, so a slightly wider end reuses the band; t the band plus k times
    the depth below z_top (CounterOrg squeezes its ends into a shorter band)."""
    sc = end_w / (front_x - back_x)

    def fn(p, name):
        s = (front_x - p[0]) if name == "+y" else (p[0] - back_x)
        return (s * sc, band + (z_top - p[2]) * k)
    return fn


def map_strip(mesh):
    """The tile mapping of the raised panels' bevels on the gilt strip: s along each bevel's long side, t across
    it."""
    for v in range(len(mesh.p)):
        ch = mesh.charts[mesh.c[v]]
        s0, t0 = mesh.st[v]
        a, b = (s0, t0) if ch.w >= ch.h else (t0, s0)
        mesh.st[v] = (a, GOLD_T + min(GOLD_TH, b))
    return mesh


def slab_mesh(w, d, x0, x1):
    """The marble slab: a bevelled box (its underside too: a gnome sees under the overhang) on the `top` tile's
    marble. Every face reads the marble stretched by 1.618 along the slab, so the tile's bold vein repeats out
    of step with the bays (it would line up with the pilasters)."""
    slab = G.translate(G.box(w, d, SLAB_H, SLAB_BEVEL, 1, z0=SLAB_Z0), (x0 + x1) / 2, 0.0, 0.0)

    def fn(p, name):
        if name in ("+z", "-z"):
            return (p[1] / 1.618, MARBLE_T + p[0] - x0)
        along = p[1] if name == "+x" else (-p[1] if name == "-x" else p[0])
        return (along / 1.618, MARBLE_T + 0.3 + H - p[2])
    return retile(slab, fn)


# --------------------------------------------------------------------------------------------- atlas paints

def p_gold(ctx, seed, p):
    return T.g_gold(ctx, seed, {"patina": 0.05})


def p_brass(ctx, seed, p):
    return T.g_brass(ctx, seed, {"streak": True, "patina": 0.06, "hotspot": 0.9})


def p_dark_walnut(ctx, seed, p):
    return T.scale(T.g_wood(ctx, seed, {"kind": "walnut"}), 0.62)


def p_cakes(ctx, seed, p):
    """The cakes: sponge sides with a filling line (three layers on the layer cake), thick domed icing with a
    wavy drip edge, all in saturated colours (never white on the white marble), and the red cherry."""
    x, y, z = ctx.pos
    if math.hypot(x - CHERRY[0], y - CHERRY[1], z - CHERRY[2]) < CHERRY_R * 1.4:
        k = T.clamp01(0.55 - ((x - CHERRY[0]) * 0.3 + (CHERRY[1] - y) * 0.3 + (z - CHERRY[2])) / CHERRY_R * 0.5)
        return T.mix(T.hexc("8A0A16"), T.hexc("FF6A6A"), k)
    k = min(range(len(CAKE_AT)), key=lambda i: (x - CAKE_AT[i][0]) ** 2 + (y - CAKE_AT[i][1]) ** 2 +
            (z - CAKE_AT[i][2] - CAKE_AT[i][4] / 2) ** 2)
    cx, cy, z0, r, h, icing, layers = CAKE_AT[k]
    lz = (z - z0) / h
    drip = 0.3 + 0.1 * math.sin(math.atan2(y - cy, x - cx) * 7.0 + k * 1.7)
    if ctx.n[2] > 0.55 or lz > 1.0 - drip:
        c = icing
        if ctx.n[2] > 0.55:
            c = T.mix(c, T.mix(icing, T.hexc("FFFFFF"), 0.35), T.smoothstep(0.6, 1.0, ctx.n[2]) * 0.5)
        return c
    choc = icing == ICINGS[1]
    c = T.hexc("6A3A20") if choc else T.hexc("E8B878")
    for f in ((0.42,) if layers == 1 else (0.24, 0.5)):
        if abs(lz - f) < 0.06:
            c = T.hexc("5A3020") if not choc and layers > 1 else T.hexc("FFE6C8")
    return c


# the cake stand: a gold lathe (foot, lower plate r 0.21, rod, upper plate r 0.14); cakes as
# (x, y, base z, r, h, icing, layers) in model space
STAND_LO, STAND_HI = 0.052, 0.199
ICINGS = (T.hexc("F06292"), T.hexc("5A3020"), T.hexc("7FD1B9"), T.hexc("F2D45C"))
LOWER = (0, 2, 1, 2, 3)                   # pink, mint, chocolate (at the back), mint, lemon round the plate
CAKE_AT = ([(CAKES[0] + math.cos(a) * 0.13, CAKES[1] + math.sin(a) * 0.13, H + STAND_LO, 0.06, 0.078,
             ICINGS[LOWER[i]], 1) for i, a in enumerate(math.radians(18 + 72 * k) for k in range(5))] +
           [(CAKES[0], CAKES[1], H + STAND_HI, 0.085, 0.112, ICINGS[0], 3)])
CHERRY_R = 0.032
CHERRY = (CAKES[0], CAKES[1], H + STAND_HI + 0.112 + CHERRY_R * 0.8)


# ---------------------------------------------------------------------------------------------- decals

def d_medallion(w, h):
    """The lion medallion's face: a royal-blue field with a soft radial sheen inside a gold rim with eight
    painted rivets (0.18 of the radius across, so they hold 8 texels and more at mip 0), the lion_head in gold
    relief."""
    img = T.Img(w, h, (0, 0, 0, 0))
    cx, cy, R = w / 2.0, h / 2.0, min(w, h) / 2.0
    for y in range(h):
        for x in range(w):
            dx, dy = (x + 0.5 - cx) / R, (y + 0.5 - cy) / R
            r = math.hypot(dx, dy)
            if r > 1.0:
                continue
            if r > 0.8:
                k = T.clamp01(0.55 - (dx + dy) * 0.45)
                c = T.mix(T.hexc("9A6418"), T.hexc("FFE89A"), k)
                if r < 0.83 or r > 0.97:
                    c = T.scale(c, 0.6)
            else:
                c = T.mix(T.hexc("3A64A8"), T.scale(ENAMEL, 0.8), T.smoothstep(0.0, 0.8, math.hypot(dx + 0.3,
                                                                                                    dy + 0.3)))
            img.set(x, y, c, 1.0)
    for i in range(8):
        a = math.pi / 8 + i * math.pi / 4
        rx, ry = cx + math.cos(a) * R * 0.895, cy + math.sin(a) * R * 0.895
        rr = R * 0.09
        for y in range(int(ry - rr * 2), int(ry + rr * 2) + 1):
            for x in range(int(rx - rr * 2), int(rx + rr * 2) + 1):
                if 0 <= x < w and 0 <= y < h:
                    c = img.get(x, y)
                    img.set(x, y, T.rivet_dot(c[:3], (x + 0.5 - rx) / R * 0.17, (y + 0.5 - ry) / R * 0.17,
                                              rr / R * 0.17), c[3])
    s = int(R * 1.5)
    if s > 8:
        P2.composite(img, E.render_relief("lion_head", s, s, P2.GOLD_RELIEF), int(cx - s / 2), int(cy - s / 2))
    return img


# ------------------------------------------------------------------------------------------------ parts

def _quad(m, pts, name):
    """One flat quad, pts (bl, br, tr, tl) counter-clockwise seen from outside, as its own chart (s along the
    bottom edge, t down from the top)."""
    bl = pts[0]
    su = G.norm(G.sub(pts[1], bl))
    n = G.norm(G.cross(G.sub(pts[1], bl), G.sub(pts[3], bl)))
    up = G.cross(n, su)
    ss = [G.dot(G.sub(q, bl), su) for q in pts]
    uu = [G.dot(G.sub(q, bl), up) for q in pts]
    s0, top = min(ss), max(uu)
    ch = m.chart(max(ss) - s0, top - min(uu), name)
    vi = [m.vert(q, n, ch, s - s0, top - u) for q, s, u in zip(pts, ss, uu)]
    m.tri(vi[0], vi[1], vi[2])
    m.tri(vi[0], vi[2], vi[3])


def raised_panel(face_x, sx, y0, y1, z0, z1, depth, bevel, front_name=None):
    """A raised panel on a long face (sx +1: the +x face, -1: the -x face): a frustum whose footprint is
    y0..y1 x z0..z1 on the face plane and whose front stands `depth` proud, `bevel` smaller all round.
    Returns (front, bevels): the front quad (chart named after the face, for map_face) and the four bevels.
    Each bevel quad starts on its long outer edge, so its chart's s runs along the bevel and map_strip's t across
    it (started on the short slanted edge, s ran diagonally and one triangle a side had no texture area)."""
    def w(a, b, d):
        # face-local (a right, b up, d out) to model space; for the -x face "right" is -Y
        return (face_x + sx * d, sx * a, b)
    a0, a1 = sorted((sx * y0, sx * y1))
    i = bevel
    fb = [w(a0 + i, z0 + i, depth), w(a1 - i, z0 + i, depth), w(a1 - i, z1 - i, depth), w(a0 + i, z1 - i, depth)]
    bb = [w(a0, z0, 0.0), w(a1, z0, 0.0), w(a1, z1, 0.0), w(a0, z1, 0.0)]
    front, bevels = G.Mesh(), G.Mesh()
    _quad(front, fb, front_name or ("+x" if sx > 0 else "-x"))
    _quad(bevels, [fb[3], fb[2], bb[2], bb[3]], "top")
    _quad(bevels, [bb[0], bb[1], fb[1], fb[0]], "bottom")
    _quad(bevels, [bb[3], bb[0], fb[0], fb[3]], "left")
    _quad(bevels, [bb[1], bb[2], fb[2], fb[1]], "right")
    return front, bevels


def fascia_panels(face_x, sx, bays):
    """The raised enamel panels of the fascia bays on one long face (the footprint RAISE inside each bay's
    painted field), as (fronts, bevels)."""
    fronts, bevels = [], []
    u0 = STILE + FRAME + RAISE_U
    z1 = BODY_Z1 - (RAIL_T_ + FRAME + RAISE_V)
    z0 = BODY_Z0 + RAIL_B_ + FRAME + RAISE_V
    for k in range(bays):
        y0 = -BAY_Y + (k + u0) * BAY_W
        y1 = -BAY_Y + (k + 1 - u0) * BAY_W
        f, b = raised_panel(face_x, sx, y0, y1, z0, z1, PANEL_D, PANEL_BEVEL)
        fronts.append(f)
        bevels.append(b)
    return G.merge(fronts), G.merge(bevels)


def corner_rects(front_x, back_x, half_w, front_out=POST_OUT):
    """The four corner posts' footprints (x0, x1, y0, y1, sx, sy), front pair first: POST wide along Y, standing
    POST_OUT proud of the ends and of the back face and front_out proud of the front face (CounterSW's front
    posts stand as proud as its pilasters)."""
    out = []
    for x, sx, o in ((front_x, 1, front_out), (back_x, -1, POST_OUT)):
        xa, xb = x + sx * o, x - sx * (POST - POST_OUT)
        for sy in (1, -1):
            ya, yb = sy * (half_w + POST_OUT), sy * (half_w + POST_OUT - POST)
            out.append((min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb), sx, sy))
    return out


def _rect_box(r, grow, h, z0, faces, x_lim=None):
    """An upright box on a footprint r grown by `grow` all round (its X clipped to x_lim, the slab's edges)."""
    x0, x1, y0, y1 = r[0] - grow, r[1] + grow, r[2] - grow, r[3] + grow
    if x_lim:
        x0, x1 = max(x0, x_lim[0]), min(x1, x_lim[1])
    return G.translate(G.box(y1 - y0, x1 - x0, h, faces=faces, z0=z0), (x0 + x1) / 2, (y0 + y1) / 2, 0.0)


def corner_posts(front_x, back_x, half_w, z0, z1, front_out=POST_OUT):
    """Walnut posts on the four carcass corners (corner_rects) on the `top` tile's post bands: the two outer faces
    fluted, the two facing the carcass (of which only a strip shows, but without them the ends show see-through
    slivers) plain."""
    out = []
    for r in corner_rects(front_x, back_x, half_w, front_out):
        b = _rect_box(r, 0.0, z1 - z0, z0, "+x -x +y -y")
        out.append(map_post(b, ("+x" if r[4] > 0 else "-x", "+y" if r[5] > 0 else "-y")))
    return G.merge(out)


def pilasters(face_x, sx, ys, depth=PIL_D, width=PIL_W):
    """Walnut pilasters on one long face (sx +1: +x, -1: -x) at the given Y (bay edges), `depth` proud and
    `width` wide, on the `top` tile's post bands (the front fluted, the sides plain)."""
    sgn = "+" if sx > 0 else "-"
    return G.merge([map_post(G.translate(G.box(width, depth, FACE_H, faces=sgn + "x +y -y", z0=BODY_Z0),
                                         face_x + sx * depth / 2, y, 0.0), (sgn + "x",)) for y in ys])


def capitals(face_x, sx, ys, depth=PIL_D, two_step=True, width=PIL_W):
    """Gold capitals under the slab on the pilasters (`width` wide) of one long face: a lower step 0.01 proud of
    the pilaster all round and, with two_step, a wider upper step reaching the slab's front edge (0.02 wider
    each side). The top step keeps its top face: it shows in the wedge under the slab's rounded edge."""
    out = []
    sgn = "+" if sx > 0 else "-"
    if not two_step:
        h = CAP_LO + CAP_HI
        return G.merge([G.translate(G.box(width + 0.02, depth + 0.01, h, faces=sgn + "x +y -y +z -z",
                                          z0=BODY_Z1 - h), face_x + sx * (depth + 0.01) / 2, y, 0.0) for y in ys])
    for y in ys:
        out.append(G.translate(G.box(width + 0.02, depth + 0.01, CAP_LO, faces=sgn + "x +y -y -z",
                                     z0=BODY_Z1 - CAP_HI - CAP_LO), face_x + sx * (depth + 0.01) / 2, y, 0.0))
        out.append(G.translate(G.box(width + 0.06, depth + 0.015, CAP_HI, faces=sgn + "x +y -y +z",
                                     z0=BODY_Z1 - CAP_HI), face_x + sx * (depth + 0.015) / 2, y, 0.0))
    return G.merge(out)


def corner_capitals(front_x, back_x, half_w, two_step=(True, True), front_out=POST_OUT):
    """Gold capitals on the corner posts (front, back): a step 0.01 proud all round, and with two_step a
    wider upper step reaching the slab's front edge and end. The side facing into the carcass is left out (it
    is inside)."""
    out = []
    lim = (-D / 2, D / 2)
    for r in corner_rects(front_x, back_x, half_w, front_out):
        sides = "%sx +y -y" % ("+" if r[4] > 0 else "-")
        if two_step[0 if r[4] > 0 else 1]:
            out.append(_rect_box(r, 0.01, CAP_LO, BODY_Z1 - CAP_HI - CAP_LO, sides + " -z", lim))
            out.append(_rect_box(r, 0.02, CAP_HI, BODY_Z1 - CAP_HI, sides + " +z", lim))
        else:
            out.append(_rect_box(r, 0.01, CAP_LO + CAP_HI, BODY_Z1 - CAP_HI - CAP_LO, sides + " +z -z", lim))
    return G.merge(out)


def base_blocks(face_x, sx, ys, corners_half_w=None, front_out=POST_OUT):
    """Gold base blocks on the plinth under the pilasters of one long face and, with corners_half_w, under
    that face's two corner posts (reaching as far forward as the pilasters' blocks, so the foot rail's finials
    rest on them)."""
    sgn = "+" if sx > 0 else "-"
    out = [G.translate(G.box(BASE_W, BASE_D, BASE_H, faces=sgn + "x +y -y +z", z0=PLINTH_H),
                       face_x + sx * BASE_D / 2, y, 0.0) for y in ys]
    if corners_half_w is not None:
        rects = corner_rects(face_x, -face_x, corners_half_w, front_out)
        for r in (rects[:2] if sx > 0 else rects[2:]):
            x0, x1 = r[0] - 0.01, r[1] + 0.01
            x0, x1 = (x0, max(x1, face_x + BASE_D)) if sx > 0 else (min(x0, face_x - BASE_D), x1)
            out.append(_rect_box((x0, x1, r[2] - 0.01, r[3] + 0.01), 0.0, BASE_H, PLINTH_H, "+x -x +y -y +z"))
    return G.merge(out)


def plinth(body_w, front_x, back_x):
    """The two-step plinth: the walnut toe (TOE_OUT proud of the carcass all round) under the gold-beaded torus
    (TORUS_OUT proud), each on its band of the `top` tile."""
    toe = G.translate(G.box(body_w + 2 * TOE_OUT, front_x - back_x + 2 * TOE_OUT, TOE_H, faces="+x -x +y -y +z"),
                      (front_x + back_x) / 2, 0.0, 0.0)
    torus = G.translate(G.box(body_w + 2 * TORUS_OUT, front_x - back_x + 2 * TORUS_OUT, TORUS_H,
                              faces="+x -x +y -y +z", z0=TOE_H), (front_x + back_x) / 2, 0.0, 0.0)
    return retile(toe, map_toe()), retile(torus, map_moulding(PLINTH_H, TORUS_H))


def bell_parts(r, sides):
    """The service bell: a dark walnut base ring showing about 0.02 round the dome, a polished brass dome and a
    chunky gold plunger (a stem 0.06 thick under a ball 0.08 across). Base at z 0. Returns (base, dome,
    button)."""
    bh = r * 0.22
    base = G.lathe([(r * 1.22, 0.0), (r * 1.18, bh), (r * 0.98, bh)], sides - 2)
    dome = G.dome(r, r * 0.85, 3, sides, z0=bh)
    top = bh + r * 0.85
    button = G.merge([G.cylinder(0.03, 0.05, 6, False, z0=top - 0.01),
                      G.translate(G.sphere(0.04, 6, 3), 0.0, 0.0, top + 0.07)])
    return base, dome, button


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (W, D, H)
    d.render_size = (W, RENDER_D, CHERRY[2] + CHERRY_R)       # the cherry on the cake stand
    d.budget = 1000
    d.kind = "counter"
    d.atlas = {"atlas": 256}
    d.tiles = tiles()
    add = d.add
    hw = BODY_W / 2

    # the marble slab, overhanging the carcass (0.105 in front, 0.05 behind, 0.06 at the ends)
    add(B.Part("slab", slab_mesh(W, D, -D / 2, D / 2), texture="top"))

    # the carcass: the fascia bays in front, the cupboard bays behind, the ends on their own band (all on the
    # panels tile)
    fmap = map_face(BAND_F, BAND_D, BODY_Z1, BAY_Y, BAY_W)
    long_faces = G.box(BODY_W, FRONT_X - BACK_X, FACE_H, faces="+x -x", z0=BODY_Z0)
    long_faces = G.translate(long_faces, (FRONT_X + BACK_X) / 2, 0.0, 0.0)
    add(B.Part("carcass", retile(long_faces, fmap), texture="panels"))
    ends = G.translate(G.box(BODY_W, FRONT_X - BACK_X, FACE_H, faces="+y -y", z0=BODY_Z0),
                       (FRONT_X + BACK_X) / 2, 0.0, 0.0)
    add(B.Part("ends", retile(ends, map_end(FRONT_X, BACK_X)), texture="panels"))

    # the raised enamel panels: their fronts read the fascia band (enamel and the gold cup), the bevels are gilt
    fronts, bevels = fascia_panels(FRONT_X, 1, BAYS)
    add(B.Part("raised_panels", retile(fronts, fmap), texture="panels"))
    add(B.Part("panel_bevels", map_strip(bevels), texture="top"))

    # the two-step plinth: walnut toe, gold-beaded torus (the top tile's toe and moulding bands)
    toe, torus = plinth(BODY_W, FRONT_X, BACK_X)
    add(B.Part("plinth_toe", toe, texture="top"))
    add(B.Part("plinth_torus", torus, texture="top"))

    # corner posts and chunky fascia pilasters (0.09 proud, the front corner posts as proud) on gold base blocks,
    # stepped gold capitals under the slab
    posts = G.merge([corner_posts(FRONT_X, BACK_X, hw, BODY_Z0, BODY_Z1, PIL_D), pilasters(FRONT_X, 1, PILASTERS)])
    add(B.Part("posts", posts, texture="top"))
    caps = G.merge([capitals(FRONT_X, 1, PILASTERS), corner_capitals(FRONT_X, BACK_X, hw, (True, False), PIL_D)])
    add(B.Part("capitals", caps, paint=p_gold, seed=15, weight=0.9))
    add(B.Part("base_blocks", base_blocks(FRONT_X, 1, PILASTERS, hw, PIL_D), paint=p_gold, seed=16, weight=0.8))

    # the brass foot rail along the customer side, resting in the base blocks, with gold ball finials
    rail = G.sweep([(RAIL_X, -RAIL_Y, RAIL_Z), (RAIL_X, RAIL_Y, RAIL_Z)], RAIL_R, 8)
    add(B.Part("foot_rail", map_tube(rail, RAIL_T, RAIL_TH), texture="top"))
    knobs = [G.translate(G.sphere(KNOB_R, 6, 3), RAIL_X, s * RAIL_Y, RAIL_Z) for s in (1, -1)]
    add(B.Part("rail_knobs", G.merge(knobs), paint=p_gold, seed=18, weight=0.8, ao_floor=0.75))

    # the lion medallion on the centre panel
    med_z = BODY_Z1 - (RAIL_T_ + FACE_H - RAIL_B_) / 2
    med = G.transform(G.cylinder(0.2, 0.032, 16, (False, True)),
                      G.mat_chain(G.mat_translate(FRONT_X + PANEL_D - 0.002, 0.0, med_z), G.MAT_DISC_FRONT))
    for ch in med.charts:
        ch.weight = 2.2 if ch.name == "cyl_top" else 0.6
    add(B.Part("medallion", med, paint=p_gold, seed=17, decals={"cyl_top": d_medallion}))

    # the service bell: a dark walnut base ring, a polished brass dome and a gold plunger
    base, dome, button = bell_parts(BELL_R, 14)
    bx, by = BELL
    add(B.Part("bell_base", G.translate(base, bx, by, H), paint=p_dark_walnut, seed=21, weight=0.7))
    add(B.Part("bell", G.translate(dome, bx, by, H), paint=p_brass, seed=23, weight=1.2, ao_floor=0.7))
    add(B.Part("bell_button", G.translate(button, bx, by, H), paint=p_gold, seed=25, weight=0.8, ao_floor=0.7))

    # the two-tier cake stand: a gold lathe (foot, lower plate, a rod 0.06 thick, upper plate), five cakes below
    # and a layer cake with a cherry on top
    cx, cy = CAKES
    stand = G.lathe([(0.1, 0.0), (0.035, 0.035), (0.21, STAND_LO - 0.004), (0.03, STAND_LO + 0.006),
                     (0.03, STAND_HI - 0.012), (0.14, STAND_HI - 0.004), (0.0, STAND_HI + 0.004)], 12)
    add(B.Part("cake_stand", G.translate(stand, cx, cy, H), paint=p_gold, seed=27, weight=0.7, ao_floor=0.65))
    cakes = []
    for x, y, z0, r, h, _icing, layers in CAKE_AT:
        prof = [(r, 0.0), (r, h * 0.7), (0.0, h)] if layers == 1 else [(r, 0.0), (r, h * 0.8), (r * 0.7, h * 0.97),
                                                                      (0.0, h)]
        cakes.append(G.translate(G.lathe(prof, 8), x, y, z0))
    cakes.append(G.translate(G.sphere(CHERRY_R, 6, 3), *CHERRY))
    add(B.Part("cakes", G.merge(cakes), paint=p_cakes, seed=29, weight=1.0, ao_floor=0.75))

    d.collision = G.hull_box(W, D, H)
    return d
