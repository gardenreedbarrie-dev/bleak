"""19309 ColdBoxOrg, the Frost-Rune Cold Box (Orgrimmar ice-cream station), CAFE.SPEC.md section 5.8.1.

A crooked timber ice chest lined with stone and chilled by a glowing frost rune, shaped so it reads as "the ice
cream" at a glance from the front three-quarter view: three wooden buckets heaped with scoops (kodo milk, dark
chocolate, cactus apple) sit in crushed ice under a lid that is a sloping slab of clear blue ice, a big pale blue
frost-rune crystal glows in an iron claw in the middle of the back rail, a big waffle cone with a cactus-apple
scoop stands in a spiked iron cup at the rail's -Y end, a red war-shield with the cone painted on it hangs on the
front between a boar's pair of ivory tusks, and frost mist rolls over the front lip and sinks.
Orgrimmar and hand-made: rough timber planks bound with riveted black iron, crooked iron corner posts banded in
red lacquer under tall spikes, a lip of blue-grey stone slabs (the lining shows on the back wall inside the lid
too), the ice held down by two wide red lacquer straps across it, a red lacquer back rail with a stitched hide
flap; red roundels on the ends (a bone tusk crest on the left, the cone on the right) over painted rope
handles. 1.1 (Y) x 0.75 (X) x 0.85 yd (the lid and the crest
to 0.96), front (+X) toward the barista.

What makes a player name it at 4-15 yd (front three-quarter view, and the +Y end the tables see), and how big
each cue is:
- the ice cream: three scoops, each a round ball 0.17 across on a scalloped heap 0.3 across that spills over
  its bucket, 0.18 over the rim; kodo cream, dark brown and pink with bold green seeds, seen through the ice
  lid (clear in the middle, frosted and cracked only round its edges) against the grey stone lining, each heap
  ringed by its bucket's iron hoop;
- the frost rune, the hero of the top: a hexagonal crystal 0.12 across and 0.25 tall, ice blue, glowing pale
  blue (9FD8FF, the glow material: it shines at night), centred on the back rail in a small iron claw of three
  talons (0.068 thick at the root);
- the cone crest, the peak of the silhouette: a waffle cone 0.16 long (0.124 across its mouth) with a
  cactus-apple scoop 0.16 across and a green cactus fruit 0.08 across on top, in an iron cup 0.06 tall with
  three spikes, at the back rail's -Y end; it rises over the crystal, so from the tables (the +Y end) it shows
  above it;
- the war-shield on the front: 0.38 across, a dark iron rim, a ring of red lacquer 0.06 wide and a bone disc
  0.2 across with the cone painted on it (0.21 tall), framed by the tusks (0.084 thick at the root, 0.35 tall);
- the chest: a low, wide timber chest 0.99 x 0.62 on black iron corner posts (0.07 square, spikes 0.14 tall
  over red bands), a stone lip 0.085 deep and the ice slab in an iron frame (rails 0.065 wide) sloping up to
  the red back rail at 0.635;
- cold: icicles 0.085-0.12 long under the lip, patches of rime on the top faces, crushed ice round the buckets,
  the frost mist born along the whole front lip, rolling over it and sinking down the front (two emitters, small
  puffs);
- Orgrimmar: the tusks, the spikes, the red straps (0.07 wide), back rail, post bands, shield ring and
  roundels (0.2), the hide flap, the bone tusk crest on the left end.

Deviations from the section 5.8.1 design and the section 5.8 size (H 0.85 +- 2 cm):
- the lid and the crest rise to 0.96 (render_size; the collision box keeps 1.1 x 0.75 x 0.85, its top sloping
  down to 0.45 over the stone lip with the ice): the scoops need 0.18 over their rims under the ice and the
  crest stands on the back rail;
- the lid is a slab of ice (glass, frosted toward its edges, painted cracks in the frosted margin only) sloping
  17 degrees toward the front in an iron frame, as on ColdBoxSW: from 4-15 yd at eye height a flat lid hides the
  tubs. The section 5.8 table lists no glass for this model; the ice is the frosted lid of section 5.8.1;
- the stone slab lining shows as the front lip and the back wall inside the lid (the chest's outside is timber),
  and the tubs are wooden buckets in crushed ice;
- the frost rune crystal is an opaque icy core inside a glowing shell (the glow material alone is additive and
  would vanish against a bright sky), standing in an iron claw in the middle of the back rail, not on the lid
  (the ice slab); the goblin gauge that stood beside it is gone, so the crystal and the cone read alone;
- added: the cone crest, the war-shield, the tusks, the spikes, the red straps, back rail, post bands and end
  roundels, the hide flap, the painted rope handles, the icicles and the crushed ice.
"""

import math

from .. import build as B
from .. import emblem as E
from .. import geom as G
from .. import paint2d as P2
from .. import raster2d as R
from .. import tex as T
from . import _cold_box as CB

NAME = "ColdBoxOrg"
DISPLAY = 19309

LACQUER = T.hexc("B5402F")
LACQUER_DK = T.hexc("9C2A1F")
STONE = T.hexc("666C78")            # cold blue-grey stone
MORTAR = T.hexc("24262C")
CAST = dict(light_c=T.hexc("5E626C"), base=T.hexc("26272D"), dark=T.hexc("0A0A0E"), bounce=T.hexc("3A3430"),
            patina=T.hexc("4A3A30"))     # black iron, a shade darker than the Orgrimmar kettle's: it reads black
                                         # under the rime
RUNE = T.hexc("9FD8FF")
ROPE = T.hexc("B49660")
HI, LO = T.IRON_RIVET_HI, T.IRON_RIVET_LO

FOOT_Z = 0.06                   # the chest's underside: it stands on its corner posts
DECK_Z = 0.31                   # the chest's top, crushed ice round the buckets
BODY_W, BODY_D = 0.99, 0.62     # the chest box (Y, X)
POST = 0.07                     # iron corner posts, square
POST_X, POST_Y = 0.325, 0.51    # their centres (extents X +-0.36, Y +-0.545)
HOOD_W = 0.95                   # the ice lid between its end panes (Y)
LIP_X0, LIP_X1 = 0.27, 0.355    # the stone lip (X)
XF, XB = 0.31, -0.28            # the ice slab's underside line: front and back (X)
ZF, ZB = 0.40, 0.585            # its height at the front lip and at the back rail
SLOPE = math.atan2(ZB - ZF, XF - XB)
ICE_T = 0.03                    # the slab's thickness
STRAP_X = (0.275, -0.21)        # the two red straps across the ice: over its front edge and its back margin
                                # (along the slope they hid the scoops from the queue: seen from 37-54 degrees,
                                # a scoop 0.1 under the ice shows 0.12-0.16 to the side, right under a strap)
TUB_X, TUB_R = -0.11, 0.145
TUB_Z0, TUB_Z1 = 0.29, 0.34     # each bucket's visible rim
TUBS = ((-0.3, "kodo"), (0.0, "dark_chocolate"), (0.3, "cactus"))
RAIL_TOP = ZB + 0.05            # the red back rail's top
FRONT_TOP = ZF + 0.035          # the front posts' tops
BACK_TOP = RAIL_TOP + 0.015     # the back posts' tops
CREST_X, CREST_Y = -0.265, -0.33   # the cone crest's axis, at the back rail's -Y end
CONE_TIP, CONE_L, CONE_R = RAIL_TOP - 0.012, 0.16, 0.062
SCOOP_Z = CONE_TIP + CONE_L
CREST_BALL = 0.076
CRYSTAL_X, CRYSTAL_Y = -0.255, 0.0   # the rune crystal's axis, centred on the back rail
CRYSTAL_Z0 = RAIL_TOP - 0.01
CRYSTAL_Z1 = CRYSTAL_Z0 + 0.25  # its top at 0.875, under the crest's scoop: the cone stays the peak
SHIELD_X, SHIELD_R, SHIELD_Z = 0.378, 0.19, 0.21    # the war-shield: its face, radius and middle
TUSK_ROOT, TUSK_TIP = (0.34, 0.30, 0.03), (0.356, 0.20, 0.375)   # the +Y tusk (the -Y one is mirrored)
ROUNDEL_R, ROUNDEL_Z = 0.1, 0.205   # the red roundels on the ends
HANDLE_Z = 0.255                # the painted rope handles: the eye bolts' height


def lid_z(x):
    """Height of the ice slab's underside at x (it slopes down toward the front)."""
    return ZF + (XF - x) / (XF - XB) * (ZB - ZF)


# ----------------------------------------------------------------------------------------------- paints

def cast_iron(ctx, seed, rust=0.08):
    return T.metal(ctx, seed, {"streak_k": 0.45, "patina": rust}, CAST["light_c"], CAST["base"], CAST["dark"],
                   CAST["bounce"], CAST["patina"], rust)


def _rope_handle(ctx, seed, c):
    """A rope handle painted on an end of the chest: a thick three-strand rope hanging in a U from two iron eye
    bolts at x +-0.2 (it passes under the roundel)."""
    x, z = ctx.pos[0], ctx.pos[2]
    for bx in (0.2, -0.2):
        if math.hypot(x - bx, z - HANDLE_Z) < 0.03:
            return T.rivet_dot(cast_iron(ctx, seed + 5), x - bx, HANDLE_Z - z, 0.03, HI, LO)
    if z > HANDLE_Z:
        return c
    qx, qz = x / 0.2, (z - HANDLE_Z) / 0.165
    q = math.hypot(qx, qz)
    across = (q - 1.0) * 0.18
    if abs(across) > 0.024:
        if 0.024 < across < 0.034:
            return T.scale(c, 0.6)                        # the rope's shadow on the timber
        return c
    along = math.atan2(qz, qx) * 0.18
    f = ((along + across * 0.8) / 0.032) % 1.0
    r = T.mix(T.scale(ROPE, 0.4), ROPE, T.smoothstep(0.0, 0.6, math.sin(math.pi * f)))
    return T.mix(r, T.scale(ROPE, 1.25), T.smoothstep(0.0, -0.02, across) * 0.35)


def p_chest(ctx, seed, p):
    """Rough timber planks with nail heads, bound with black iron: a riveted band along the top (under the rime)
    and the bottom, two riveted straps on the front, the rope handles painted on the ends; the top face is
    crushed ice."""
    if ctx.chart == "+z":
        return CB.p_ice(ctx, seed, p)
    c = T.g_planks(ctx, seed, {"kind": "timber", "count": 3, "gap": 0.024, "ragged": 0.025, "knots": 1,
                               "nails": True})
    c = T.mix(c, T.hexc("5A2E1A"), 0.25)          # Durotar timber: darker and redder than oak
    t, s, ch = ctx.t, ctx.s, ctx.ch
    y = ctx.pos[1]
    band = None
    if t < 0.042:
        band = (0.021, True)
    elif t > ch - 0.036:
        band = (ch - 0.018, True)
    if ctx.chart == "+x" and abs(abs(y) - 0.36) < 0.03:
        band = (s + math.copysign(0.36, y) - y, False)
    if band is not None:
        row, horiz = band
        c = cast_iron(ctx, seed + 3, 0.12)
        if horiz:
            c = T.rivet_lines(ctx, c, rows=(row,), step=0.14, r=0.02, hi=HI, lo=LO)
        else:
            c = T.rivet_lines(ctx, c, cols=(row,), step=0.12, r=0.02, hi=HI, lo=LO, phase=0.06)
    if ctx.chart in ("+y", "-y"):
        c = _rope_handle(ctx, seed, c)
    return CB.frost(ctx, c, CB.top_frost(ctx, seed, 0.03) * 0.8, seed + 11)


def p_iron(ctx, seed, p):
    """Black iron with patches of rime where it faces straight up (the iron must still read black)."""
    c = cast_iron(ctx, seed)
    return CB.frost(ctx, c, T.smoothstep(0.8, 0.98, ctx.n[2]) * 0.32, seed + 5)


def p_posts(ctx, seed, p):
    """Black iron posts, each banded in red lacquer under its spike."""
    x, z = ctx.pos[0], ctx.pos[2]
    top = FRONT_TOP if x > 0 else BACK_TOP
    if z > top - 0.065 and abs(ctx.n[2]) < 0.5:
        c = T.g_lacquer(ctx, seed + 2, {"color": LACQUER, "worn": 0.5})
        if abs(z - (top - 0.0325)) > 0.024:
            c = T.mix(c, cast_iron(ctx, seed + 3), 0.85)  # thin iron edges round the band
        return c
    return p_iron(ctx, seed, p)


def p_stone(ctx, seed, p):
    """The stone lining: big blue-grey slabs with dark joints, only lightly rimed so they read as stone."""
    c = T.g_slabs(ctx, seed, {"color": STONE, "mortar": MORTAR, "slab": (0.26, 0.14), "joint": 0.016,
                              "cracks": 0.3})
    return CB.frost(ctx, c, T.smoothstep(0.7, 0.98, ctx.n[2]) * 0.2, seed + 3)


def p_back_wall(ctx, seed, p):
    """Stone slabs inside the lid (rimed round the edges), timber behind."""
    if ctx.chart != "+x":
        c = T.g_planks(ctx, seed, {"kind": "timber", "count": 2, "gap": 0.024, "ragged": 0.0})
        return T.mix(c, T.hexc("5A2E1A"), 0.25)
    c = T.g_slabs(ctx, seed, {"color": T.scale(STONE, 0.9), "mortar": MORTAR, "slab": (0.24, 0.1),
                              "joint": 0.016, "cracks": 0.25})
    e = T.edge_dist(ctx)
    k = T.smoothstep(0.05, 0.0, e + (T.fbm(ctx.s * 9.0, ctx.t * 9.0, seed + 1, 2) - 0.5) * 0.04)
    return CB.frost(ctx, c, k * 1.2, seed + 2)


def p_back_rail(ctx, seed, p):
    """The back rail: red lacquer on its front and top with bold iron rivets, a stitched hide flap over the
    middle of its front (behind the crest), black iron behind."""
    if ctx.chart == "-x":
        return cast_iron(ctx, seed + 1)
    y = ctx.pos[1]
    if ctx.chart == "+x" and abs(y) < 0.19:
        c = T.g_hide(ctx, seed, {"color": T.hexc("8A5A3A"), "edge": 0.008, "scuffs": 0.4})
        return T.stitches(ctx, c, margin=0.012, step=0.04, width=0.012, edges="lrt")
    c = T.g_lacquer(ctx, seed, {"color": LACQUER, "worn": 0.6})
    if ctx.chart == "+x":
        c = T.rivet_lines(ctx, c, rows=(ctx.ch / 2,), step=0.14, r=0.02, hi=HI, lo=LO)
    return c


def p_lacquer(ctx, seed, p):
    """Red lacquer straps across the ice: worn to the iron at the edges, a row of bold rivets along them."""
    c = T.g_lacquer(ctx, seed, {"color": LACQUER, "worn": 0.7})
    if abs(ctx.n[2]) > 0.5:
        c = T.rivet_lines(ctx, c, rows=(ctx.ch / 2,), step=0.14, r=0.02, hi=HI, lo=LO)
    return c


def p_bucket(ctx, seed, p):
    """Wooden buckets: upright staves of alternating tone with dark seams and an iron hoop at the rim, whose top
    shows as a lightly rimed iron ring round each heap."""
    if ctx.chart == "bucket_lip":
        return CB.frost(ctx, cast_iron(ctx, seed + 1), 0.4, seed + 2)
    x, y, z = ctx.pos
    ty = min(TUBS, key=lambda tb: abs(y - tb[0]))[0]
    phi = math.atan2(y - ty, x - TUB_X)
    k = phi / (2 * math.pi) * 12.0
    i = math.floor(k)
    q = k - i
    c = T.mix(T.hexc("8A5A32"), T.hexc("A8784A"), CB._hash(i, 3, seed))
    if q < 0.1:
        c = T.hexc("3A2414")
    if z > TUB_Z1 - 0.022:
        c = cast_iron(ctx, seed + 1)
        if z > TUB_Z1 - 0.007:
            c = CB.frost(ctx, c, 1.0, seed + 2)
    return c


def p_scoop(ctx, seed, p):
    """The buckets' ice cream (each painted round its own ball) and the crest's cactus-apple scoop."""
    if ctx.part == "crest_scoop":
        return CB.scoop(ctx, seed, "cactus", (CREST_X, CREST_Y, SCOOP_Z + 0.05), chips=4)
    y = ctx.pos[1]
    k = min(range(3), key=lambda i: abs(y - TUBS[i][0]))
    cy, name = TUBS[k]
    return CB.scoop(ctx, seed + 7 * k, name, (TUB_X - 0.015, cy, TUB_Z1 + CB.HEAP_BALL), chips=4)


def p_cactus_fruit(ctx, seed, p):
    """The green cactus fruit on the crest: lit on top, a pale highlight toward the light."""
    c = T.mix(T.hexc("2E6A22"), T.hexc("6AAE48"), T.clamp01(ctx.n[2] * 0.6 + 0.55))
    hl = T.clamp01(ctx.n[0] * 0.3 + ctx.n[2] * 0.8 - ctx.n[1] * 0.3)
    return T.mix(c, T.hexc("D8F0B0"), T.smoothstep(0.85, 1.0, hl) * 0.7)


# The ice slab's two cracks, in (y, distance down the slope from the back) yd: a point, the direction's angle
# and the half length. Both run down the frosted side margins between the straps, clear of the scoops.
CRACKS = ((-0.43, 0.32, 1.5, 0.16), (0.43, 0.29, 1.38, 0.14))


def p_ice_lid(ctx, seed, p):
    """A slab of clear blue ice (section 5.2.5): a body of alpha 0.28 (71) that the scoops read through, white
    frost feathering in from the frame, two bold cracks with lit lips and a dark blue shadow in the frosted
    margin only, two sheen streaks up to alpha 0.75 (191), the slab's cut edges thick white."""
    x, y, z = ctx.pos
    ca = math.cos(SLOPE)
    if ctx.part == "ice_lid":
        if abs(ctx.n[2]) < 0.6:
            c = T.mix(T.hexc("BFE2F6"), (1.0, 1.0, 1.0), 0.6)
            return (c[0], c[1], c[2], 0.9)
        e = min((XF - x) / ca, (x - XB) / ca, HOOD_W / 2 - abs(y))
        u, v = (y + HOOD_W / 2) / HOOD_W, (XF - x) / (XF - XB)
    else:
        e = min(z - DECK_Z, XF - x, x - XB, (lid_z(x) - z) * ca)
        u, v = (XF - x) / (XF - XB), (z - DECK_Z) / (ZB - DECK_Z)
    f = T.fbm(x * 16.0 + y * 7.0, y * 16.0 + z * 11.0, seed, 3)
    k = T.smoothstep(0.06, 0.0, e + (f - 0.5) * 0.05)
    c = T.mix(T.hexc("94C8EC"), (1.0, 1.0, 1.0), T.clamp01(k * 0.9))
    a = 0.28 + 0.6 * k
    if ctx.part == "ice_lid":
        margin = T.smoothstep(0.1, 0.03, e)
        if margin > 0.0:
            d_slope = (x - XB) / ca
            for j, (cy, cs, ang, half) in enumerate(CRACKS):
                dy, ds = y - cy, d_slope - cs
                along = dy * math.cos(ang) + ds * math.sin(ang)
                if abs(along) > half:
                    continue
                across = -dy * math.sin(ang) + ds * math.cos(ang)
                across += (T.noise(along * 12.0, j * 3.1, seed + 4) - 0.5) * 0.03
                fade = margin * T.smoothstep(half, half * 0.6, abs(along))
                if abs(across) < 0.018:
                    c = T.mix(c, (1.0, 1.0, 1.0), 0.9 * fade)
                    a = max(a, 0.85 * fade + a * (1.0 - fade))
                elif 0.018 <= across < 0.03:
                    c = T.mix(c, T.hexc("2A5A8C"), 0.7 * fade)
                    a = max(a, 0.6 * fade + a * (1.0 - fade))
    for c0, wd in ((0.24, 0.06), (0.35, 0.03)):
        d = abs((u * 0.8 + v * 0.6) - c0)
        if d < wd:
            kk = T.smoothstep(wd, 0.0, d)
            c = T.mix(c, (1.0, 1.0, 1.0), kk * 0.8)
            a = max(a, 0.3 + 0.45 * kk)
    return (c[0], c[1], c[2], a)


def p_crystal(ctx, seed, p):
    """The crystal's opaque core: icy blue facets, lit on the side toward the light, ice blue even where lit (a
    paper-white top made it the brightest thing on the chest in daylight); the glow shell lights it at night."""
    nx, ny, nz = ctx.n
    lit = T.clamp01(nx * 0.45 - ny * 0.3 + nz * 0.5 + 0.45)
    return T.ramp([(0.0, T.hexc("2A6A9C")), (0.5, T.hexc("6AB4E6")), (1.0, T.hexc("A8D8F8"))], lit)


def p_rune_glow(ctx, seed, p):
    return T.g_frost_rune(ctx, seed, {"color": RUNE, "facets": 6})


def p_tusk(ctx, seed, p):
    """Ivory tusks with a stained root and a rope binding a little above it."""
    c = T.g_bone(ctx, seed, {"kind": "ivory", "root": 0, "cracks": 2})
    if 0.12 < ctx.v < 0.26:
        q = (ctx.t + ctx.s * 0.12) / 0.026          # turns of rope wound round the tusk
        f = q - math.floor(q)
        c = T.mix(T.scale(ROPE, 0.35), ROPE, T.smoothstep(0.0, 0.6, math.sin(math.pi * f)))
        c = T.mix(c, T.scale(ROPE, 1.2), T.smoothstep(0.0, 0.9, ctx.n[2]) * 0.4)
    return c


def p_shield(ctx, seed, p):
    """The war-shield and the end roundels: red lacquer faces (their iron rims are in the decals), black iron
    edges."""
    if not ctx.chart.endswith("_front"):
        return cast_iron(ctx, seed + 1)
    return T.g_lacquer(ctx, seed, {"color": LACQUER, "worn": 0.6})


# ---------------------------------------------------------------------------------------------- decals

ICON_ORG = {"cone": T.hexc("C88848"), "grid": T.hexc("5A3414"), "low": T.hexc("FFF4E2"),
            "low_hi": T.hexc("FFFFFF"), "top": T.hexc("E07898"), "top_hi": T.hexc("FFC0D0"),
            "cherry": T.hexc("6AAE48"), "outline": T.hexc("140A06")}


def _iron_rim(img, cx, cy, r, rivets=10):
    """A dark iron rim with a lit inner edge and bold rivets round a disc decal."""
    P2.ring(img, cx, cy, r * 0.84, r * 1.0, T.hexc("2A2A30"))
    P2.ring(img, cx, cy, r * 0.84, r * 0.88, T.hexc("6A6E78"))
    for k in range(rivets):
        a = 2 * math.pi * k / rivets
        m = R.Mask(img.w, img.h)
        R.disc(m, cx + math.sin(a) * r * 0.92, cy - math.cos(a) * r * 0.92, max(1.0, r * 0.06))
        P2.paint_mask(img, m, T.hexc("B8BCC4"))


def d_shield(w, h):
    """The war-shield's face (and the right roundel's): a dark iron rim with bold rivets, a broad ring of red
    lacquer (0.32 of the radius: the front's red), a bone-white disc in the middle and the ice-cream cone (a
    cactus-apple scoop) painted on it, its tip and top just breaking onto the red."""
    img = T.Img(w, h, (0, 0, 0, 0))
    cx, cy = w / 2.0, h / 2.0
    r = min(w, h) / 2.0
    _iron_rim(img, cx, cy, r)
    disc = R.Mask(w, h)
    R.disc(disc, cx, cy, r * 0.52)
    P2.paint_mask(img, R.dilate(disc, max(1, int(r * 0.04))), T.hexc("1A0E08"), alpha=0.8)
    P2.paint_mask(img, disc, T.hexc("E6D4A8"))
    s = int(r * 1.1)
    if s >= 8:
        CB.cone_icon(img, int(cx - s / 2), int(cy - s / 2), s, ICON_ORG)
    return img


def d_end_crest(w, h):
    """The left roundel's face: the tusk crest carved in bone on the red lacquer, in an iron rim."""
    img = T.Img(w, h, (0, 0, 0, 0))
    cx, cy = w / 2.0, h / 2.0
    r = min(w, h) / 2.0
    _iron_rim(img, cx, cy, r, 8)
    s = int(r * 1.6)
    if s >= 8:
        rel = E.render_relief("tusk_crest", s, s, P2.BONE_RELIEF)
        P2.composite(img, rel, int(cx - s / 2), int(cy - s / 2))
    return img


# ------------------------------------------------------------------------------------------------ parts

def _on_slope(mesh, x0, x1, y, lift=0.0):
    """A mesh built flat (centred on the origin, X along the slope) laid on the ice line between x0 and x1
    (x0 > x1) at y, lifted `lift` along the slab's normal."""
    xm = (x0 + x1) / 2
    nx, nz = math.sin(SLOPE), math.cos(SLOPE)
    return G.transform(mesh, G.mat_chain(G.mat_translate(xm + nx * lift, y, lid_z(xm) + nz * lift),
                                         G.mat_rot_y(SLOPE)))


def _open_spike(base, direction, r, h):
    """G.spike without its base cap: the base sits in a post top, a collar or a cup wall and faces down or in,
    so no eye-height view ever looks into it."""
    return G.transform(G.cone(r, 0.0, h, 5, caps=False), G.mat_chain(G.mat_translate(*base), G.mat_look(direction)))


def _roundel(sy):
    """A red roundel on an end of the chest, facing +-Y (its back sunk into the crooked timber)."""
    m = G.extrude(G.circle_polygon(ROUNDEL_R, 10, math.pi / 10), 0.03, 0.0, back=False)
    m = G.transform(m, G.mat_chain(G.mat_translate(0.0, sy * (BODY_W / 2 - 0.012), ROUNDEL_Z),
                                   G.mat_extrude_facing((0.0, float(sy), 0.0))))
    for ch in m.charts:
        ch.weight = 2.4 if ch.name.endswith("_front") else 0.4
    return m


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (1.1, 0.75, 0.85)
    d.render_size = (1.1, 0.75, 0.96)
    d.budget = 1200
    d.kind = "station"
    d.atlas = {"atlas": 256}
    add = d.add

    # the chest: rough timber bound in black iron, visibly crooked; crushed ice on its top
    body = G.box(BODY_W, BODY_D, DECK_Z - FOOT_Z, faces="+x -x +y -y +z", z0=FOOT_Z)
    body = G.wobble(body, 0.012, 11, 4.0)
    for ch in body.charts:
        ch.weight = {"-x": 0.5, "+z": 0.7, "+x": 1.6, "+y": 1.5, "-y": 1.5}.get(ch.name, 1.0)     # crisp planks
    add(B.Part("chest", body, paint=p_chest, seed=11))

    # black iron corner posts banded in red, visibly crooked, each crowned with a tall spike sunk into its top
    # (the back pair stand up past the back rail)
    posts, spikes = [], []
    for sx in (1, -1):
        top = FRONT_TOP if sx > 0 else BACK_TOP
        for sy in (1, -1):
            px, py = sx * POST_X, sy * POST_Y
            posts.append(G.translate(G.box(POST, POST, top, faces="+x -x +y -y +z"), px, py, 0.0))
            spikes.append(_open_spike((px, py, top - 0.015), (0.12 * sx, 0.12 * sy, 1.0), 0.045, 0.14))
    posts = G.wobble(G.merge(posts), 0.01, 21)
    posts.p = [(x, y, 0.0 if z < 0.02 else z) for x, y, z in posts.p]     # the feet stay on the floor
    posts = G.recompute_normals(posts, 40.0)
    add(B.Part("posts", posts, paint=p_posts, seed=21, weight=0.7))
    add(B.Part("spikes", G.merge(spikes), paint=p_iron, seed=23, weight=0.5))

    # the stone lip along the front (the lining's top), the iron rails along the slab's sides and the red
    # back rail
    lw = 2 * POST_Y - POST + 0.004
    lip = G.translate(G.box(lw, LIP_X1 - LIP_X0, FRONT_TOP - DECK_Z, faces="+x -x +z", z0=DECK_Z),
                      (LIP_X0 + LIP_X1) / 2, 0.0, 0.0)
    lip = G.wobble(lip, 0.004, 31)
    add(B.Part("stone_lip", lip, paint=p_stone, seed=31, weight=0.8))
    L = (XF - XB) / math.cos(SLOPE)
    rails = [_on_slope(G.box(0.065, L, 0.04, faces="+x +y -y +z"), XF, XB, sy * (HOOD_W / 2 - 0.0075), -0.004)
             for sy in (1, -1)]
    add(B.Part("iron_frame", G.merge(rails), paint=p_iron, seed=33, weight=0.7))
    back = G.translate(G.box(lw, 0.075, RAIL_TOP - (ZB - 0.012), faces="+x -x +z", z0=ZB - 0.012), XB, 0.0, 0.0)
    add(B.Part("back_rail", back, paint=p_back_rail, seed=34, weight=1.5))

    # the lining inside the lid: a stone back wall
    wall = G.translate(G.box(HOOD_W, 0.03, ZB - DECK_Z, faces="+x -x", z0=DECK_Z), XB - 0.014, 0.0, 0.0)
    wall.set_weight(0.7)
    add(B.Part("back_wall", wall, paint=p_back_wall, seed=35))

    # the lid: a slab of ice on the slope, its end panes (single shells), two wide red lacquer straps across it
    # (over the side rails)
    slab = _on_slope(G.box(HOOD_W, L, ICE_T, faces="+x +y -y +z"), XF, XB, 0.0)
    slab.set_weight(1.0)
    add(B.Part("ice_lid", slab, "glass", paint=p_ice_lid, seed=41))
    wy = HOOD_W / 2
    ends = G.merge([CB.poly([(XB, sy * wy, DECK_Z), (XF, sy * wy, DECK_Z), (XF, sy * wy, ZF), (XB, sy * wy, ZB)],
                            (0.0, float(sy), 0.0), "ice_end") for sy in (1, -1)])
    ends.set_weight(0.6)
    add(B.Part("ice_ends", ends, "glass1", paint=p_ice_lid, seed=43))
    straps = [_on_slope(G.box(HOOD_W + 0.05, 0.07, 0.025, faces="+x +y -y +z"), sx, sx, 0.0, ICE_T)
              for sx in STRAP_X]
    add(B.Part("straps", G.merge(straps), paint=p_lacquer, seed=45, weight=0.8))

    # the three buckets in the ice, heaped with ice cream: a scalloped skirt over the rim, a crease and a
    # round scoop on top that leans back from the lid
    rims, heaps = [], []
    for k, (ty, _name) in enumerate(TUBS):
        rims.append(G.translate(G.cylinder(TUB_R, TUB_Z1 - TUB_Z0, 12, False, z0=TUB_Z0), TUB_X, ty, 0.0))
        lid = CB.rim_cap(TUB_X, ty, TUB_Z1, TUB_R, 12, "bucket_lip")
        lid.set_weight(0.5)
        rims.append(lid)
        heaps.append(G.translate(CB.heap(TUB_Z1, 10, 71 + k, 0.6 * k), TUB_X, ty, 0.0))
    add(B.Part("buckets", G.merge(rims), paint=p_bucket, seed=51, weight=0.6))
    add(B.Part("ice_cream", G.merge(heaps), paint=p_scoop, seed=53, weight=1.6, ao_floor=0.6))

    # the cone crest at the back rail's -Y end: a spiked iron cup, the waffle cone, a cactus-apple scoop and a
    # green cactus fruit on top
    cup = G.translate(G.lathe([(0.026, RAIL_TOP - 0.004), (0.046, RAIL_TOP + 0.022), (0.038, RAIL_TOP + 0.056)],
                              6), CREST_X, CREST_Y, 0.0)
    prongs = []
    for k in range(3):
        a = math.pi / 3 + 2 * math.pi * k / 3
        ca, sa = math.cos(a), math.sin(a)
        prongs.append(_open_spike((CREST_X + ca * 0.04, CREST_Y + sa * 0.04, RAIL_TOP + 0.03),
                                  (ca * 0.8, sa * 0.8, 0.6), 0.034, 0.07))
    add(B.Part("crest_cup", G.merge([cup] + prongs), paint=p_iron, seed=55, weight=0.6))
    cone = G.translate(G.cone(0.005, CONE_R, CONE_L, 8, caps=False, z0=CONE_TIP), CREST_X, CREST_Y, 0.0)
    add(B.Part("cone", cone, paint=CB.p_waffle, seed=56, weight=1.8))
    scoop, top_z = CB.crest_scoop(SCOOP_Z, CREST_BALL, 8)
    add(B.Part("crest_scoop", G.translate(scoop, CREST_X, CREST_Y, 0.0), paint=p_scoop, seed=57, weight=1.8))
    fruit = G.translate(G.sphere(0.04, 6, 4), CREST_X + 0.006, CREST_Y, top_z + 0.02)
    add(B.Part("cactus_fruit", fruit, paint=p_cactus_fruit, seed=58, weight=1.2, ao_floor=0.7))

    # the frost rune, centred on the back rail: an iron collar with three talons gripping a hexagonal crystal
    # (an opaque icy core and a glowing shell over it)
    cz0 = CRYSTAL_Z0
    collar = G.translate(G.lathe([(0.05, RAIL_TOP - 0.004), (0.062, RAIL_TOP + 0.012), (0.05, RAIL_TOP + 0.03)],
                                 6), CRYSTAL_X, CRYSTAL_Y, 0.0)
    talons = []
    for k in range(3):
        a = math.pi / 3 + 2 * math.pi * k / 3
        ca, sa = math.cos(a), math.sin(a)
        base = (CRYSTAL_X + ca * 0.06, CRYSTAL_Y + sa * 0.06, RAIL_TOP + 0.02)
        talons.append(_open_spike(base, (-ca * 0.32, -sa * 0.32, 1.0), 0.034, 0.11))
    add(B.Part("rune_claw", G.merge([collar] + talons), paint=p_iron, seed=59, weight=0.6))
    # a hexagonal prism 0.12 across and 0.25 tall with pointed ends; the core leaves out the shell's lowest ring,
    # which is down in the collar
    cprof = [(0.0, cz0), (0.05, cz0 + 0.035), (0.06, cz0 + 0.065), (0.06, CRYSTAL_Z1 - 0.075), (0.0, CRYSTAL_Z1)]
    core = G.recompute_normals(G.lathe([(r * 0.93, z) for r, z in cprof[:1] + cprof[2:]], 6, smooth=False,
                                       seam=0.0, name="crystal"), 25.0)
    shell = G.recompute_normals(G.lathe(cprof, 6, smooth=False, seam=0.0, name="crystal"), 25.0)
    add(B.Part("rune_core", G.translate(core, CRYSTAL_X, CRYSTAL_Y, 0.0), paint=p_crystal, seed=60, weight=1.2,
               ao_floor=0.8))
    add(B.Part("rune_glow", G.translate(shell, CRYSTAL_X, CRYSTAL_Y, 0.0), "glow", paint=p_rune_glow, seed=61,
               weight=1.4, ao_floor=1.0))

    # a boar's pair of ivory tusks rising from the floor round the war-shield, bowing outward
    tusks = []
    for sy in (1, -1):
        r0 = (TUSK_ROOT[0], sy * TUSK_ROOT[1], TUSK_ROOT[2])
        r1 = (TUSK_TIP[0], sy * TUSK_TIP[1], TUSK_TIP[2])
        tusks.append(G.horn(r0, r1, (0.15, float(sy), 0.0), 0.24, 0.042, 0.0, 4, 6))
    add(B.Part("tusks", G.merge(tusks), paint=p_tusk, seed=62, weight=0.9))

    # the red war-shield on the front, with the cone: a thick boss standing out of the chest in front of the
    # stone lip
    shield = G.extrude(G.circle_polygon(SHIELD_R, 12), 0.08, 0.008, back=False)
    shield = G.transform(shield, G.mat_chain(G.mat_translate(SHIELD_X - 0.08, 0.0, SHIELD_Z),
                                             G.MAT_EXTRUDE_FRONT))
    for ch in shield.charts:
        ch.weight = 2.4 if ch.name.endswith("_front") else 0.4
    add(B.Part("shield", shield, paint=p_shield, seed=65, decals={"extrude_front": d_shield}))

    # the end roundels: the bone tusk crest on the +Y end, toward the seated customers (they see the cone on
    # the crest over it), the cone on the -Y end
    add(B.Part("roundel_left", _roundel(1), paint=p_shield, seed=63, decals={"extrude_front": d_end_crest},
               ao_floor=0.5))
    add(B.Part("roundel_right", _roundel(-1), paint=p_shield, seed=64, decals={"extrude_front": d_shield},
               ao_floor=0.5))

    # icicles under the stone lip, outside the tusks
    ics = []
    for k, (y, ln) in enumerate(((-0.455, 0.1), (-0.395, 0.12), (0.395, 0.115), (0.455, 0.085))):
        r = 0.03 + 0.004 * ((k * 7) % 3) / 2.0
        ics.append(G.translate(G.cone(0.0, r, ln, 5, caps=(False, True), z0=-ln), LIP_X1 - 0.026, y,
                               DECK_Z + 0.004))
    add(B.Part("icicles", G.merge(ics), paint=CB.p_icicle, seed=69, weight=0.6, ao_floor=0.7))

    # the collision box, its top sloping down to the stone lip with the ice
    d.collision = CB.hull_wedge(1.1, 0.75, 0.85, FRONT_TOP + 0.015)
    # frost mist rolling off the stone lip's top edge between the tusks and the front posts (Y 0.34-0.46 clear
    # of both), 6 cm in front of the lip face; it sinks down past the icicles
    d.particles = [CB.mist(LIP_X1 + 0.04, y, FRONT_TOP) for y in (0.24, -0.24)]   # along the whole front lip
    return d
