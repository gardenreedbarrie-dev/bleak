"""19311 SyrupRackOrg, the Orgrimmar syrup rack on the back bar, CAFE.SPEC.md section 5.8.1.

A crooked two-tier rack of rough timber, leather, bone and dark iron holding the café syrups, shaped so a player
names it at a glance: the same row of eight loud syrup bottles as in Stormwind (honey, vanilla, caramel,
cinnamon, chocolate, the two-tone cactus apple, mint and the whipped-cream canister), but blown thick and crude,
each leaning a little, each crowned by a goblin syrup pump (an iron collar and stem, a red-lacquered spout head)
and each with a narrow rawhide tag hung from its neck on twine (the flavour glyph burnt in), so the syrup's
colour shows all round it, standing against a pale stretched hide laced to the posts. Orcish build: two thick
timber back posts with rope lashings and iron bands, crowned by chunky ivory tusks with leather-wrapped roots;
two stub front posts capped with iron spikes; plank tiers, the shelf's front edge in red lacquer and the base's
front in iron, both studded with big rivets; a palisade of sharpened timber stakes with charred points above the
shelf; the upper tier hung from the crossbeam on two leather straps, carrying red-glazed clay mugs, a crock and a
keg of coffee beans; on the crossbeam a red lacquer plank sign, "SYRUPS" in bone-white capitals between two
carved tusk crests. The cream canister is a goblin gadget (chipped white enamel over riveted iron, with a
brass-rimmed pressure gauge). 1.45 (Y) x 0.45 (X) x 0.9 yd, front (+X) toward the barista.

Deviations from the section 5.8.1 design, for recognizability and the readability rule (>= 0.06 yd):
- every syrup bottle carries a pump (the café cue, as in Stormwind), here a goblin one with a red head; the
  bottles are opaque painted glass (the section 5.8 row has no bottle glass for this rack), syrup-coloured with a
  light-through middle, crude bubbles and a smoky green neck, so the colours read from 15 yd; they lean 1-3
  degrees but are not wobbled (section 5.4: no deformers on glass);
- the hide tags are painted on the bottles (a 0.085 yd tag with a burnt edge and its twine), not separate
  meshes, which keeps the eight bottles inside the budget; their glyph is burnt dark into tan hide rather than
  drawn on a colour band, which still reads at the few texels a 256 atlas gives a tag, and the syrup round the
  narrow tag carries the colour;
- the cactus apple is two layered syrups (green over pink);
- the "leather straps" are the two straps the upper tier hangs from (no strap across the bottles: it hid their
  feet);
- added for the Orgrimmar silhouette: the tusks on the back posts, the iron spikes on the front posts, the sign
  standing on the crossbeam (the tusk crests at its ends), the hanging straps of the upper tier, the bean keg;
- the back is a pale stretched hide under the shelf (so the dark syrups read against it, the Orgrimmar
  counterpart of Stormwind's blue enamel): a skin-shaped panel bowed back a little in the middle, laced to the
  back posts by four broad rawhide thongs a side over a dark timber backboard, which shows as shadow round the
  skin; above the shelf a palisade of sharpened timber stakes with gaps between them and charred points, which
  rise behind the sign (the Orgrimmar outline at 30 yd);
- the pump heads fan outward from the middle of the row, as in Stormwind, so every head shows its L profile from
  the front and from either three-quarter view.
"""

import math

from .. import build as B
from .. import emblem as E
from .. import font as F
from .. import geom as G
from .. import paint2d as P2
from .. import raster2d as R
from .. import tex as T
from . import syrup_rack_sw as SW

NAME = "SyrupRackOrg"
DISPLAY = 19311

RED = T.hexc("B5402F")
DARK_RED = T.hexc("9C2A1F")
BONE_C = T.hexc("F2E6C8")
HIDE = T.hexc("DCAE74")             # pale rawhide: luma 110+ after the bake
THONG = T.hexc("E6CC96")            # paler rawhide lacing
TWINE = T.hexc("D2B47C")
WIDTH, DEPTH, HEIGHT = 1.45, 0.45, 0.9
BASE_H = 0.06
POST_B, BPX = 0.09, -0.18           # back posts: square side, x centre
BPY = WIDTH / 2 - POST_B / 2        # their y centre (+-0.68)
POST_TOP = 0.71
POST_F, FPX = 0.08, DEPTH / 2 - 0.04    # front stub posts
FPY = WIDTH / 2 - POST_F / 2
FRONT_TOP = 0.3
BAND_Z = 0.3                        # the iron band round each back post
INNER = BPY - POST_B / 2            # 0.635: the posts' inner faces
SHELF_Z0, SHELF_Z1 = 0.55, 0.6
SHELF_X0, SHELF_X1 = -0.2, 0.1
BEAM_X, BEAM_D, BEAM_Z0, BEAM_Z1 = -0.1625, 0.065, 0.655, 0.71
SIGN_W, SIGN_X0, SIGN_X1, SIGN_Z1 = 0.70, -0.178, -0.143, 0.86
BOARD_X0, BOARD_X1 = -0.225, -0.198
HIDE_X = BOARD_X1 + 0.002           # the stretched hide's plane
HIDE_Y = INNER - 0.05               # its legs, 0.05 in from the back posts
HIDE_Z0, HIDE_Z1 = BASE_H + 0.03, SHELF_Z0 - 0.03
# the skin's outline (y, z), counter-clockwise seen from the front: stretched out at the four legs and pulled in
# between them, a little uneven
HIDE_EDGE = ((-HIDE_Y, HIDE_Z0), (-0.27, HIDE_Z0 + 0.014), (0.05, HIDE_Z0 + 0.008), (0.33, HIDE_Z0 + 0.016),
             (HIDE_Y, HIDE_Z0), (HIDE_Y - 0.019, 0.22), (HIDE_Y - 0.015, 0.39), (HIDE_Y, HIDE_Z1),
             (0.3, HIDE_Z1 - 0.016), (-0.02, HIDE_Z1 - 0.01), (-0.31, HIDE_Z1 - 0.018), (-HIDE_Y, HIDE_Z1),
             (-HIDE_Y + 0.017, 0.4), (-HIDE_Y + 0.02, 0.21))
HIDE_SAG = 0.01                     # the middle of the skin bows back (section 5.4: deformed hide)
BACKBOARD_X = -0.212                # the dark board behind the hide: inside the posts, 4 mm behind the bowed skin
TAB_Z = (0.142, 0.25, 0.358, 0.466)     # the lacing thongs (their middles), four a side
TAB_H, TAB_STEP = 0.05, 0.12        # thong width; their spacing along the shared chart
BOTTLE_X = 0.02
TIER_X = -0.05
WOBBLE = 0.01                       # section 5.4: Orgrimmar timber and iron, 1-2 cm

# Crude bottle shapes (r, z) from the foot to the open neck, the hide tag's span (z0, z1) at the top of the
# straight body, just under the shoulder (so syrup shows below, beside and above it), and a lean (degrees toward
# +X, toward +Y) about the foot: blown thick by orcs, none quite straight.
BOTTLES = {
    "honey": ([(0.06, 0.0), (0.074, 0.04), (0.076, 0.12), (0.062, 0.18), (0.03, 0.215), (0.028, 0.27)],
              (0.065, 0.165), (2.0, -3.0)),
    "vanilla": ([(0.058, 0.0), (0.058, 0.2), (0.044, 0.25), (0.024, 0.275), (0.023, 0.36)], (0.09, 0.19),
                (-1.5, 2.0)),
    "caramel": ([(0.07, 0.0), (0.07, 0.16), (0.058, 0.205), (0.034, 0.225), (0.032, 0.3)], (0.05, 0.15),
                (1.0, 2.5)),
    "cinnamon": ([(0.072, 0.0), (0.06, 0.2), (0.03, 0.255), (0.026, 0.32)], (0.08, 0.18), (-2.0, -2.0)),
    "chocolate": ([(0.06, 0.0), (0.072, 0.07), (0.072, 0.15), (0.058, 0.2), (0.032, 0.23), (0.03, 0.29)],
                  (0.045, 0.145), (2.5, 1.5)),
    "cactus": ([(0.046, 0.0), (0.07, 0.025), (0.074, 0.16), (0.05, 0.21), (0.024, 0.245), (0.023, 0.32)],
               (0.055, 0.155), (-1.0, -2.5)),
    "mint": ([(0.064, 0.0), (0.064, 0.15), (0.052, 0.19), (0.06, 0.225), (0.026, 0.268), (0.024, 0.335)],
             (0.045, 0.145), (1.5, 3.0)),
}
CAN_BODY = [(0.062, 0.0), (0.062, 0.235), (0.054, 0.258), (0.038, 0.27)]
CAN_TAG = (0.11, 0.21)
TAG_W = 0.085
# pump heads (degrees about the stem, from +X; shelf order honey to mint), fanned outward from the middle of the
# row like Stormwind's; honey (leaning toward the post) turns less, so its spout clears it
PUMP_YAW = (-40.0, -72.0, -66.0, -75.0, 70.0, 76.0, 64.0)
# the bottles' glass streaks: softer than Stormwind's and the broad one wider, so they read as glass, not paint
GLINTS = ((-0.5, 0.25), (1.05, 0.12))
# the palisade's sharpened stakes above the shelf (rising behind the beam and the sign): peak z, peak offset in y
BOARD_TOPS = ((0.835, 0.008), (0.88, -0.01), (0.85, 0.006), (0.885, 0.01), (0.862, -0.006), (0.882, 0.009),
              (0.828, -0.008))
# the upper tier (1.2x the real size): crock, lid and keg profiles, the mugs
CROCK = [(0.07, 0.0), (0.079, 0.045), (0.072, 0.1), (0.06, 0.112)]
CROCK_LID = [(0.064, 0.106), (0.068, 0.122), (0.0, 0.146)]
KEG_R, KEG_H = 0.08, 0.14
MUG_R, MUG_H = 0.066, 0.12
HANDLE_R = 0.045                    # the mugs' D handles: arc radius


# ----------------------------------------------------------------------------------------------- paints

def p_post(ctx, seed, p):
    """Rough timber, the grain upright, with rope lashings where the crossbeam and the shelf meet the back posts,
    a broad iron band round the middle (0.08 yd, 5 texels: a rivet on it would be a texel) and an iron band at
    the foot."""
    c = T.g_wood(ctx, seed, {"kind": "timber", "along": "t"})
    z = ctx.pos[2]
    for z0, z1 in ((BEAM_Z0 - 0.02, BEAM_Z1 + 0.012), (SHELF_Z0 - 0.025, SHELF_Z1 + 0.01)):
        if z0 <= z <= z1 and ctx.pos[0] < 0.0:
            return T.g_rope(ctx, seed + 3, {"along": "s", "pitch": 0.12, "color": T.hexc("B89458")})
    if abs(z - BAND_Z) < 0.04 and ctx.chart in ("+x", "-x", "+y", "-y"):
        return T.g_iron(ctx, seed + 7, {"rust": 0.2, "streak": False})
    if z < 0.045:
        c = T.g_iron(ctx, seed + 5, {"rust": 0.2, "streak": False})
    return c


def p_front_post(ctx, seed, p):
    c = T.g_wood(ctx, seed, {"kind": "timber", "along": "t"})
    z = ctx.pos[2]
    if z > FRONT_TOP - 0.05 or z < 0.045:
        c = T.g_iron(ctx, seed + 5, {"rust": 0.2, "streak": False})   # iron caps
    return c


def p_base(ctx, seed, p):
    """Timber planks; the front board's face is an iron band studded with big rivets (0.048 yd heads, 3 texels
    and more), as on the back bar's plinth."""
    if ctx.chart == "+x" and ctx.pos[0] > 0.1:
        c = T.g_iron(ctx, seed + 5, {"rust": 0.25, "streak": False})
        return T.rivet_lines(ctx, c, rows=(ctx.ch / 2,), step=0.12, r=0.024, hi=T.IRON_RIVET_HI,
                             lo=T.IRON_RIVET_LO)
    return T.g_planks(ctx, seed, {"kind": "timber", "count": 1, "nails": True, "knots": 1})


def p_shelf(ctx, seed, p):
    """Timber planks; the front edge is dark red lacquer studded with big iron rivets (its chart is dense
    enough for 0.044 yd heads to keep 5 texels)."""
    if ctx.chart == "+x" and ctx.pos[0] > 0.05:
        c = T.g_lacquer(ctx, seed + 5, {"color": DARK_RED, "worn": 0.6})
        return T.rivet_lines(ctx, c, rows=(ctx.ch / 2,), step=0.12, r=0.022, hi=T.IRON_RIVET_HI,
                             lo=T.IRON_RIVET_LO)
    return T.g_planks(ctx, seed, {"kind": "timber", "count": 1, "nails": True, "knots": 1})


def p_wall(ctx, seed, p):
    """The palisade: rough timber stakes, lighter than the crossbeam so the crock, keg and mugs read against
    them, each point charred black over its top 0.07 yd (found by the stake under the texel)."""
    c = T.g_planks(ctx, seed, {"kind": "timber", "count": 1, "nails": True, "ragged": 0.02})
    _x, y, z = ctx.pos
    k = min(len(BOARD_TOPS) - 1, max(0, int((y + INNER) / (2 * INNER) * len(BOARD_TOPS))))
    return T.scale(c, 1.0 - 0.55 * T.smoothstep(BOARD_TOPS[k][0] - 0.08, BOARD_TOPS[k][0] - 0.06, z))


def _hide_edge(y, z):
    """Distance (yd) from (y, z) on the hide's plane to the skin's outline (HIDE_EDGE)."""
    best = 1.0
    for k in range(len(HIDE_EDGE)):
        (y0, z0), (y1, z1) = HIDE_EDGE[k - 1], HIDE_EDGE[k]
        dy, dz = y1 - y0, z1 - z0
        f = max(0.0, min(1.0, ((y - y0) * dy + (z - z0) * dz) / (dy * dy + dz * dz)))
        best = min(best, math.hypot(y - y0 - f * dy, z - z0 - f * dz))
    return best


def _tab_shadow(y, z):
    """True where a lacing thong casts its shadow (a 0.015 yd band under it) near the hide's sides."""
    if abs(y) < HIDE_Y - 0.04:
        return False
    return any(-0.015 < (tz - TAB_H / 2) - z < 0.0 for tz in TAB_Z)


def p_hide(ctx, seed, p):
    """The stretched skin behind the bottles, painted broad (nothing finer than 0.05 yd, 4 texels): pale rawhide
    varied +-8% in big soft patches, brightest in the taut middle and darker over its outer 0.09 yd, with an
    uneven burnt rim; a shadow band under each lacing thong. The thongs (their own chart): pale rawhide, lit on
    top and shaded underneath, darker where they wrap the post."""
    _x, y, z = ctx.pos
    if ctx.chart == "tabs":
        c = T.mix(T.scale(THONG, 0.72), T.mix(THONG, (1.0, 0.97, 0.9), 0.15), T.smoothstep(0.85, 0.2, ctx.t / TAB_H))
        return T.scale(c, 1.0 - 0.25 * T.smoothstep(INNER - 0.03, INNER, abs(y)))
    c = T.scale(HIDE, 0.92 + 0.16 * T.fbm(ctx.s * 2.5, ctx.t * 2.5, seed, 3))
    e = _hide_edge(y, z)
    c = T.scale(c, 1.08 - 0.36 * T.smoothstep(0.09, 0.0, e))
    e += (T.noise(ctx.s * 9.0, ctx.t * 9.0, seed + 3) - 0.5) * 0.024
    c = T.mix(c, T.scale(HIDE, 0.4), T.smoothstep(0.035, 0.005, e) * 0.8)
    if _tab_shadow(y, z):
        c = T.scale(c, 0.6)
    return c


def p_backboard(ctx, seed, p):
    """The dark timber board behind the hide: it shows round the skin and between the thongs as shadow."""
    c = T.scale(T.g_planks(ctx, seed, {"kind": "orgdark", "count": 3, "ragged": 0.0}), 0.8)
    if ctx.chart == "+x" and _tab_shadow(ctx.pos[1], ctx.pos[2]):
        c = T.scale(c, 0.6)
    return c


def p_beam(ctx, seed, p):
    c = T.g_planks(ctx, seed, {"kind": "timber", "count": 1, "ragged": 0.0})
    y = abs(ctx.pos[1])
    if SIGN_W / 2 - 0.05 < y < SIGN_W / 2 - 0.005:
        return T.g_rope(ctx, seed + 3, {"pitch": 0.1, "color": T.hexc("B89458")})   # the sign's lashings
    return c


def p_sign(ctx, seed, p):
    return T.g_lacquer(ctx, seed, {"color": RED, "worn": 0.7})


def p_tusk(ctx, seed, p):
    """Ivory with age cracks; a dark leather wrap binds the root to the post (the first 0.03 yd of the tusk sits
    in the post top, the wrap shows above it)."""
    c = T.g_bone(ctx, seed, {"kind": "ivory", "root": 0, "cracks": 2})
    if ctx.t < 0.08:
        w = T.g_leather(ctx, seed + 3, {"color": T.hexc("4A2A16")})
        return T.mix(w, T.hexc("A07850"), T.smoothstep(0.3, 0.9, ctx.n[2]) * 0.3)
    return c


def p_iron(ctx, seed, p):
    return T.g_iron(ctx, seed, {"rust": 0.25})


def p_hanger(ctx, seed, p):
    """The upper tier's hanging straps: dark oiled leather, a little lit along its upper face."""
    c = T.g_leather(ctx, seed, {"color": T.hexc("3A2010")})
    if ctx.n[2] > 0.5:
        c = T.mix(c, T.hexc("C08A5A"), 0.12)
    return c


def p_pump_head(ctx, seed, p):
    """Goblin pump heads: red lacquer, darker underneath."""
    c = T.g_lacquer(ctx, seed, {"color": RED, "worn": 0.5})
    if ctx.n[2] < -0.5:
        c = T.scale(c, 0.55)
    return c


def bottle_paint(color, level_z, color2=None, split_z=None):
    """Thick orc-blown glass, painted opaque: syrup up to level_z, bright and saturated where light comes through
    the middle of the bottle seen from the front, deep only at the very edges, with a few broad pale bubbles;
    above it a smoky green neck; the glass streak highlights over both. color2: a second syrup layered under
    split_z (the cactus apple's pink under its green)."""
    def tones(col):
        return col, T.mix(T.saturate(col, 1.3), (1.0, 0.97, 0.88), 0.08), T.scale(T.saturate(col, 1.3), 0.72)
    upper, lower = tones(color), tones(color2 if color2 is not None else color)

    def p(ctx, seed, _p):
        x, y, z = ctx.pos
        side = abs(ctx.n[1])
        if z <= level_z:
            col, lit, deep = lower if split_z is not None and z < split_z else upper
            c = T.mix(lit, col, T.smoothstep(0.3, 0.75, side))
            c = T.mix(c, deep, T.smoothstep(0.72, 1.0, side) * 0.85)
            if level_z - z < 0.01:
                c = T.mix(c, (1.0, 1.0, 0.92), 0.45)
            b = T.noise3(x * 25.0, y * 25.0, z * 25.0, seed + 9)
            c = T.mix(c, T.mix(col, (1.0, 1.0, 1.0), 0.6), T.smoothstep(0.75, 0.9, b) * 0.5)
        else:
            c = T.mix(T.hexc("B4CCBE"), T.hexc("46584E"), T.smoothstep(0.25, 0.95, side))
        c, _a = SW.glint(ctx, c, 1.0, glints=GLINTS, strength=0.45)
        return c
    return p


def p_can(ctx, seed, p):
    """A goblin cream canister: white enamel over iron, chipped, with a riveted seam."""
    c = T.g_enamel(ctx, seed, {"color": T.hexc("EEE8DA"), "chips": 4, "chip_r": 0.02, "gloss": 0.4})
    return T.rivet_lines(ctx, c, rows=(0.022,), step=0.06, r=0.012, hi=T.IRON_RIVET_HI, lo=T.IRON_RIVET_LO)


def mug_paint(top_z, centres, radius):
    """Clay mugs: red glaze poured thick over the top two-thirds with short drips, a bare clay foot (tex.g_glaze,
    round each mug's own axis); the handles glazed all over in the mugs' own red, lit a little on top."""
    def p(ctx, seed, _p):
        if ctx.chart.startswith("sweep"):
            return T.scale(DARK_RED, 0.95 + 0.15 * T.clamp01(ctx.n[2]))
        x, y, _z = ctx.pos
        cx, cy = min(centres, key=lambda q: (x - q[0]) ** 2 + (y - q[1]) ** 2)
        return T.g_glaze(ctx, seed, {"top": top_z, "center": (cx, cy), "radius": radius, "glaze": DARK_RED,
                                     "drip": 0.02, "band": 0.07})
    return p


def p_clay(ctx, seed, p):
    return T.g_glaze(ctx, seed, {"color": T.hexc("A8784E"), "glaze": T.hexc("3E2A1E"), "band": 0.03, "drip": 0.04})


def keg_paint(base_z, height):
    """A little bean keg: four broad timber staves (dark seams of 0.025 yd, 2-3 texels), two solid iron hoops
    (0.039 yd), a heap of beans on top."""
    def p(ctx, seed, _p):
        if ctx.n[2] > 0.6 and ctx.pos[2] > base_z + height - 0.012:
            return T.g_beans(ctx, seed, {"size": 0.03})
        c = T.g_wood(ctx, seed, {"kind": "timber", "along": "t"})
        if (ctx.u * 4.0) % 1.0 < 0.2:
            c = T.scale(c, 0.5)
        lz = (ctx.pos[2] - base_z) / height
        for hz in (0.2, 0.8):
            if abs(lz - hz) < 0.14:
                c = T.g_iron(ctx, seed + 3, {"rust": 0.3, "streak": False})
        return c
    return p


def p_crock_lid(ctx, seed, p):
    return T.g_wood(ctx, seed, {"kind": "orgdark"})


# ---------------------------------------------------------------------------------------------- decals

def _tag_poly(tw, th):
    """A luggage-tag outline (clipped top corners, a slightly ragged hide edge) in a tw x th box, clockwise in
    image space."""
    pts = [(0.24, 0.0), (0.76, 0.0), (1.0, 0.2), (0.98, 0.62), (1.0, 1.0), (0.55, 0.97), (0.0, 1.0), (0.02, 0.6),
           (0.0, 0.2)]
    return [(x * tw, y * th) for x, y in pts]


def tag_decal(prof, span, glyph, neck_z, width=TAG_W):
    """A rawhide tag painted on the middle of a bottle's front chart (split_lathe; u 0.5 is the model's front):
    tan hide with a burnt edge (2 px and more) and the flavour glyph burnt in dark brown, hung on light twine
    from a loop round the neck (light, so it reads as string, not as a crack). width: the tag's width in yd at
    the widest radius, where the chart keeps its aspect."""
    total, at = SW.arc_table(prof)
    rmax = max(r for r, _z in prof)
    v0 = (total - at(span[1])) / total
    v1 = (total - at(span[0])) / total
    vn = (total - at(neck_z)) / total
    hide = T.hexc("D2A468")
    burnt = T.hexc("3A2210")

    def f(w, h):
        img = T.Img(w, h, (0, 0, 0, 0))
        y0 = int(round(v0 * h))
        th = max(2, int(round(v1 * h)) - y0)
        tw = max(2, int(round(width / (math.pi * rmax) * w)))     # the front chart is half the circumference
        x0 = (w - tw) // 2
        lw = max(2.0, h * 0.008)
        yn = vn * h
        P2.line(img, 0.0, yn, float(w), yn, lw, TWINE)                    # the twine loop round the neck
        P2.line(img, w / 2.0, yn, w / 2.0, y0 + th * 0.1, lw, TWINE)      # down to the tag
        m = R.Mask(tw, th)
        R.fill(m, [_tag_poly(tw, th)])
        inner = R.Mask(tw, th)
        inset = max(2.0, tw * 0.1)
        R.fill(inner, [[(inset + x * (tw - 2 * inset) / tw, inset + y * (th - 2 * inset) / th)
                        for x, y in _tag_poly(tw, th)]])
        for i, a in enumerate(m.a):
            if a <= 0:
                continue
            x, y = i % tw, i // tw
            c = T.mix(T.scale(hide, 0.86), T.scale(hide, 1.08), T.noise(x * 0.35, y * 0.35, 5))
            if inner.a[i] < 0.5:
                c = T.mix(c, burnt, 0.5)                                          # burnt rawhide edge
            img.blend(x0 + x, y0 + y, c, a)
            j = (y0 + y) * w + x0 + x
            img.a[j] = max(img.a[j], a)
        # the glyph, burnt in (it may bite half a texel into the burnt edge, so it stays 0.06 yd across): its
        # "dark" detail layers stay hide-coloured
        gs = int(round(min(tw - 2 * inset + 1, th * 0.66)))
        if gs >= 4:
            gx, gy = x0 + (tw - gs) // 2, y0 + int(th * 0.24)
            for _n, gm, mode, height in E.layer_masks(glyph, gs, gs, table=E.GLYPHS):
                cut = mode == "dark" or (isinstance(mode, tuple) and height < 0.5)
                P2.paint_mask(img, gm, hide if cut else burnt, gx, gy)
        return img
    return f


def twine_decal(prof, neck_z):
    """The twine loop on the back half of a bottle's neck (the back chart of split_lathe)."""
    total, at = SW.arc_table(prof)
    vn = (total - at(neck_z)) / total

    def f(w, h):
        img = T.Img(w, h, (0, 0, 0, 0))
        P2.line(img, 0.0, vn * h, float(w), vn * h, max(2.0, h * 0.008), TWINE)
        return img
    return f


def d_sign(w, h):
    """The plank sign: "SYRUPS" in condensed bone-white capitals with a dark outline, a carved bone tusk crest
    at each end (0.62 of the sign's height, so the word gets the width), a dark burnt border."""
    img = T.Img(w, h, (0, 0, 0, 0))
    bw = max(1, int(min(w, h) * 0.07))
    for y in range(h):
        for x in range(w):
            e = min(x, y, w - 1 - x, h - 1 - y)
            if e < bw:
                img.set(x, y, T.hexc("3A1208"), 0.75)
    cs = int(h * 0.62)
    cx, cy = bw + max(1, bw // 2), (h - cs) // 2
    fx0, fx1 = cx + cs + bw, w - cx - cs - bw
    try:
        cap = F.fit_cap("SYRUPS", fx1 - fx0, h - 2 * bw, min_cap=4.0, squeeze=0.85)
        m = F.vector_mask("SYRUPS", cap, squeeze=0.85)
        ox, oy = fx0 + (fx1 - fx0 - m.w) // 2, (h - m.h) // 2
        # two_tone only blends colour: make the lettering, its outline and shadow opaque on the clear decal
        halo = R.dilate(m, max(1, int(cap / 24)))
        for i, a in enumerate(halo.a):
            x, y = ox + i % m.w, oy + i // m.w
            if a > 0 and 0 <= x < w and 0 <= y < h and img.a[y * w + x] < a:
                img.set(x, y, T.hexc("1A0A04"), a)
        F.two_tone(img, m, BONE_C, T.hexc("1A0A04"), ox, oy, 1, (1, 1), T.hexc("140804"))
    except ValueError:
        if min(w, h) >= 64:
            raise           # at full size a text that does not fit is an error (section 5.5.1)
    if cs > 6:
        rel = E.render_relief("tusk_crest", cs, cs, P2.BONE_RELIEF)
        P2.composite(img, rel, cx, cy)
        P2.composite(img, rel, w - cx - cs, cy)
    return img


def p_gauge(ctx, seed, p):
    """The can's gauge: a brass case (its dial is the cap's decal)."""
    return T.g_brass(ctx, seed, {"streak": False, "patina": 0.1})


def d_gauge(w, h):
    """The can's dial in a thick brass rim (a fifth of its radius), so it reads as a gauge, not a blob."""
    img = T.Img(w, h, (0, 0, 0, 0))
    r = min(w, h) / 2.0
    P2.ring(img, w / 2.0, h / 2.0, r * 0.78, r, T.hexc("D0A040"))
    m = max(1, int(round(r * 0.22)))
    P2.composite(img, P2.gauge_face(w - 2 * m, h - 2 * m, {"needle_deg": 60.0, "numbers": False}), m, m)
    return img


# ------------------------------------------------------------------------------------------------ parts

def _in_size(mesh):
    """Clamps a wobbled frame part back inside the rack's footprint (1.45 x 0.45, on the bar), so the render
    keeps its catalogue size and stands flat."""
    hx, hy = DEPTH / 2, WIDTH / 2
    mesh.p = [(min(max(x, -hx), hx), min(max(y, -hy), hy), max(z, 0.0)) for x, y, z in mesh.p]
    return G.recompute_normals(mesh, 40.0)


def _without(mesh, names):
    """The mesh without the faces on the charts named in `names` (faces nobody sees), and without the charts and
    vertices they leave unused."""
    out = G.Mesh()
    keep = [t for t in mesh.t if mesh.charts[mesh.c[t[0]]].name not in names]
    cmap, vmap = {}, {}
    for t in keep:
        for v in t:
            if v not in vmap:
                c = mesh.c[v]
                if c not in cmap:
                    cmap[c] = len(out.charts)
                    out.charts.append(mesh.charts[c].copy())
                vmap[v] = out.vert(mesh.p[v], mesh.n[v], cmap[c], *mesh.st[v])
        out.t.append(tuple(vmap[v] for v in t))
    return out


def _hide():
    """The stretched skin and its lacing: a fan round the skin's middle (pushed back HIDE_SAG, so it bows like a
    laced hide) to its outline HIDE_EDGE, front face only (the backboard closes the rack behind it); four rawhide
    thongs a side, from over the skin's edge into the back posts, rising a little toward the post, on one shared
    chart laid out along s."""
    m = G.Mesh()
    ch = m.chart(2 * HIDE_Y, HIDE_Z1 - HIDE_Z0, "hide")
    m.charts[ch].weight = 1.4           # the biggest surface in the front view: 4 texels per 0.05 yd
    nx = (1.0, 0.0, 0.0)
    mid = m.vert((HIDE_X - HIDE_SAG, 0.0, (HIDE_Z0 + HIDE_Z1) / 2), nx, ch, HIDE_Y, (HIDE_Z1 - HIDE_Z0) / 2)
    ring = [m.vert((HIDE_X, y, z), nx, ch, y + HIDE_Y, HIDE_Z1 - z) for y, z in HIDE_EDGE]
    for k in range(len(ring)):
        m.tri(mid, ring[k], ring[(k + 1) % len(ring)])
    tc = m.chart(2 * len(TAB_Z) * TAB_STEP, TAB_H, "tabs")
    m.charts[tc].weight = 1.4
    x = HIDE_X + 0.005
    for k, (side, tz) in enumerate((sd, tz) for sd in (1, -1) for tz in TAB_Z):
        y_in, y_out = side * (HIDE_Y - 0.035), side * (INNER + 0.012)
        z_in, z_out = tz - TAB_H / 2, tz - TAB_H / 2 + 0.008
        L = abs(y_out - y_in)
        q = {}
        for end, (y, z) in (("in", (y_in, z_in)), ("out", (y_out, z_out))):
            sv = k * TAB_STEP + (L if end == "out" else 0.0)
            q[end] = (m.vert((x, y, z), nx, tc, sv, TAB_H), m.vert((x, y, z + TAB_H), nx, tc, sv, 0.0))
        (lb, lt), (rb, rt) = (q["in"], q["out"]) if side > 0 else (q["out"], q["in"])
        m.tri(lb, rb, rt)
        m.tri(lb, rt, lt)
    return G.recompute_normals(m, 40.0)


def _beam(w, d, h, x, y, z0, seed, faces="+x -x +y -y +z -z"):
    """A rough timber box, crooked by the Orgrimmar wobble; its foot stays flat on z0 (so it stands on the bar)."""
    m = G.wobble(G.translate(G.box(w, d, h, faces=faces, z0=z0), x, y, 0.0), WOBBLE, seed)
    m.p = [(p[0], p[1], z0) if p[2] < z0 + WOBBLE + 0.002 else p for p in m.p]
    return _in_size(m)


def _lean_mat(x, y, deg_x, deg_y):
    """Tilts about the foot point (x, y, BASE_H): deg_x toward +X, deg_y toward +Y."""
    return G.mat_chain(G.mat_translate(x, y, BASE_H), G.mat_rot_y(math.radians(deg_x)),
                       G.mat_rot_x(math.radians(-deg_y)), G.mat_translate(-x, -y, -BASE_H))


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (WIDTH, DEPTH, HEIGHT)
    d.budget = 1600
    d.collision_max = 48
    d.atlas = {"atlas": 256}
    d.kind = "rack"
    d.max_height = 0.95
    d.sloped_top = True
    add = d.add

    # the frame: thick back posts with tusks, stub front posts with iron spikes, a crossbeam
    # (a post's -x face looks at the wall behind the rack: few texels)
    posts = G.merge([_beam(POST_B, POST_B, POST_TOP, BPX, s * BPY, 0.0, 3 + k, "+x -x +y -y +z")
                     for k, s in enumerate((1, -1))])
    for ch in posts.charts:
        ch.weight = 0.3 if ch.name == "-x" else 1.1
    add(B.Part("back_posts", posts, paint=p_post, seed=11))
    fposts = G.merge([_beam(POST_F, POST_F, FRONT_TOP, FPX, s * FPY, 0.0, 7 + k, "+x -x +y -y +z")
                      for k, s in enumerate((1, -1))])
    for ch in fposts.charts:
        ch.weight = 0.3 if ch.name == "-x" else 0.8
    add(B.Part("front_posts", fposts, paint=p_front_post, seed=13))
    spikes = [G.spike((FPX, s * FPY, FRONT_TOP - 0.004), (0.15, s * 0.12, 1.0), 0.04, 0.13) for s in (1, -1)]
    add(B.Part("spikes", G.merge(spikes), paint=p_iron, seed=15, weight=0.5))
    tusks = [G.horn((BPX + 0.01, s * (BPY - 0.016), POST_TOP - 0.03), (BPX + 0.12, s * (BPY - 0.004), HEIGHT - 0.004),
                    (1.0, s * 0.15, -0.6), 0.32, 0.06, 0.0, 4, 6) for s in (1, -1)]
    add(B.Part("tusks", G.merge(tusks), paint=p_tusk, seed=17, weight=0.8))
    beam = _beam(2 * INNER + 0.04, BEAM_D, BEAM_Z1 - BEAM_Z0, BEAM_X, 0.0, BEAM_Z0, 19, "+x -x +z -z")
    for ch in beam.charts:
        ch.weight = 0.1 if ch.name == "-x" else 0.7     # its back lies against the palisade
    add(B.Part("crossbeam", beam, paint=p_beam, seed=19))

    # the sign standing on the crossbeam (its foot sunk into the crooked beam)
    sign = G.translate(G.box(SIGN_W, SIGN_X1 - SIGN_X0, SIGN_Z1 - BEAM_Z1 + 0.02, faces="+x -x +y -y +z",
                             z0=BEAM_Z1 - 0.02), (SIGN_X0 + SIGN_X1) / 2, 0.0, 0.0)
    for ch in sign.charts:
        ch.weight = {"+x": 2.8, "-x": 0.2}.get(ch.name, 0.6)
    add(B.Part("sign", sign, paint=p_sign, seed=21, decals={"+x": d_sign}))

    # the tiers: two thick planks at the base (the front one iron-faced), the hide stretched behind the bottles
    # over a dark backboard, a palisade of sharpened stakes above the shelf, the hanging upper tier (its front
    # edge red lacquer). In geom.planks the boards stack back to front, six charts each: chart 6 is the front
    # board's face (weights are set before the base's bottom faces, which stand on the bar, are dropped).
    base = G.planks(2 * INNER + 0.05, DEPTH - 0.02, BASE_H, 2, "y", seed=23, ragged=0.012)
    base = G.translate(base, 0.01, 0.0, 0.0)
    base.p = [(q[0], q[1], 0.0) if q[2] < 0.006 else q for q in base.p]
    for k, ch in enumerate(base.charts):
        ch.weight = 1.2 if k == 6 else {"+z": 0.6, "+x": 0.3}.get(ch.name, 0.2)
    add(B.Part("base", _without(base, ("-z",)), paint=p_base, seed=23))
    add(B.Part("hide", _hide(), paint=p_hide, seed=24, ao_floor=0.9))
    board = G.box(2 * INNER + 0.04, 0.003, SHELF_Z0 + 0.005, faces="+x -x")
    board = G.translate(board, BACKBOARD_X, 0.0, 0.0)
    for ch in board.charts:
        ch.weight = 0.3 if ch.name == "+x" else 0.05
    add(B.Part("backboard", board, paint=p_backboard, seed=26))
    n = len(BOARD_TOPS)
    bw = (2 * INNER) / n
    boards = []
    for k, (top, off) in enumerate(BOARD_TOPS):
        y0 = -INNER + bw * k + 0.015           # 0.03 yd gaps between the stakes
        y1 = y0 + bw - 0.03
        ym = (y0 + y1) / 2 + off
        poly = [(y0, SHELF_Z0), (y1, SHELF_Z0), (y1, top - 0.1 - off), (ym, top), (y0, top - 0.1 + off)]
        b = G.extrude(poly, BOARD_X1 - BOARD_X0, name="board")
        boards.append(G.transform(b, G.mat_chain(G.mat_translate(BOARD_X0, 0.0, 0.0), G.MAT_EXTRUDE_FRONT)))
    wall = G.wobble(G.merge(boards), WOBBLE, 25)
    wall.p = [(q[0], q[1], SHELF_Z0) if q[2] < SHELF_Z0 + WOBBLE + 0.002 else q for q in wall.p]
    wall = _in_size(wall)
    for ch in wall.charts:
        ch.weight = {"board_front": 0.6, "board_back": 0.05}.get(ch.name, 0.25)
    add(B.Part("wall", wall, paint=p_wall, seed=25, ao_floor=0.5))
    shelf = G.planks(2 * INNER + 0.02, SHELF_X1 - SHELF_X0, SHELF_Z1 - SHELF_Z0, 2, "y", seed=27, ragged=0.012,
                     z0=SHELF_Z0)
    shelf = G.translate(shelf, (SHELF_X0 + SHELF_X1) / 2, 0.0, 0.0)
    for k, ch in enumerate(shelf.charts):
        ch.weight = 2.4 if k == 6 else {"+z": 0.55, "+x": 0.2, "-z": 0.3}.get(ch.name, 0.15)
    add(B.Part("shelf", shelf, paint=p_shelf, seed=27))

    # leather: two straps hang the upper tier's front from the crossbeam
    hangs = []
    for s in (1, -1):
        a = (BEAM_X + BEAM_D / 2 - 0.004, s * (INNER - 0.06), BEAM_Z0 + 0.03)
        b = (SHELF_X1 - 0.01, s * (INNER - 0.06), SHELF_Z1 - 0.005)
        L = math.hypot(b[0] - a[0], b[2] - a[2])
        ang = math.atan2(b[2] - a[2], b[0] - a[0])
        strap = G.box(0.06, L, 0.016, faces="+y -y +z -z", z0=-0.008)
        strap = G.transform(strap, G.mat_chain(G.mat_translate((a[0] + b[0]) / 2, a[1], (a[2] + b[2]) / 2),
                                               G.mat_rot_y(-ang)))
        hangs.append(strap)
    add(B.Part("hangers", G.merge(hangs), paint=p_hanger, seed=29, weight=0.6))

    # the syrups: seven crude bottles with goblin pumps and hide tags, and the cream canister. Each bottle leans
    # about its foot and is then let down until its highest foot point rests on the base
    keys = [row[0] for row in E.SYRUPS_ORG]
    widths = [2 * max(r for r, _z in (BOTTLES[k][0] if k in BOTTLES else CAN_BODY)) for k in keys]
    ys = SW.centres(widths, -INNER, INNER)
    stems, heads = [], []
    can_y = ys[-1]
    for k, ((key, hexcol, glyph, col2), y) in enumerate(zip(E.SYRUPS_ORG, ys)):
        if key not in BOTTLES:
            can_y = y
            continue
        color = T.hexc(hexcol)
        prof, span, (lx, ly) = BOTTLES[key]
        glass = G.translate(SW.split_lathe(prof, 8, 2.7, 0.4, "glass"), BOTTLE_X, y, BASE_H)
        foot = [i for i, q in enumerate(glass.p) if abs(q[2] - BASE_H) < 1e-9]
        lean = _lean_mat(BOTTLE_X, y, lx, ly)
        glass = G.transform(glass, lean)
        drop = max(glass.p[i][2] for i in foot) - BASE_H
        glass = G.translate(glass, 0.0, 0.0, -drop)
        neck = prof[-2][1]
        c2 = T.hexc(col2) if col2 else None
        level = BASE_H + neck - 0.008
        add(B.Part("bottle_" + key, glass, paint=bottle_paint(color, level, c2, (BASE_H + level) / 2), seed=41 + k,
                   ao_floor=0.8, decals={0: tag_decal(prof, span, glyph, neck), 1: twine_decal(prof, neck)}))
        s, h = SW.pump(BOTTLE_X, y, prof[-1][0], BASE_H + prof[-1][1], PUMP_YAW[k % len(PUMP_YAW)])
        stems.append(G.translate(G.transform(s, lean), 0.0, 0.0, -drop))
        heads.append(G.translate(G.transform(h, lean), 0.0, 0.0, -drop))
    add(B.Part("pump_stems", G.merge(stems), paint=p_iron, seed=51, weight=0.6))
    add(B.Part("pump_heads", G.merge(heads), paint=p_pump_head, seed=53, weight=0.9))

    # the goblin cream canister: chipped white enamel, a hide tag, an iron head and nozzle, a brass-rimmed gauge
    # tilted up toward the barista (the can's front chart as dense as the bottles', so the tag's glyph keeps
    # 0.06 yd; the dial's dense enough for its bands and needle)
    can = G.translate(SW.split_lathe(CAN_BODY, 8, 2.7, 0.4, "can"), BOTTLE_X, can_y, BASE_H)
    add(B.Part("cream_can", can, paint=p_can, seed=55, ao_floor=0.7,
               decals={0: tag_decal(CAN_BODY, CAN_TAG, "cream", CAN_BODY[-2][1]),
                       1: twine_decal(CAN_BODY, CAN_BODY[-2][1])}))
    hz = BASE_H + CAN_BODY[-1][1]
    head = G.translate(G.lathe([(0.042, hz - 0.012), (0.044, hz + 0.024), (0.0, hz + 0.036)], 8, name="can_head"),
                       BOTTLE_X, can_y, 0.0)
    nozzle = G.lathe([(0.018, 0.0), (0.022, 0.035), (0.0, 0.09)], 6, name="nozzle")
    nozzle = G.transform(nozzle, G.mat_chain(G.mat_translate(BOTTLE_X - 0.01, can_y, hz + 0.03),
                                             G.mat_rot_y(math.radians(-24))))
    add(B.Part("cream_head", G.merge([head, nozzle]), paint=p_iron, seed=57, weight=0.7))
    gauge = G.transform(G.cylinder(0.045, 0.02, 8, (False, True)), G.mat_chain(
        G.mat_translate(BOTTLE_X + 0.05, can_y, hz + 0.012), G.mat_disc_facing((1.0, 0.0, 0.2))))
    for ch in gauge.charts:
        ch.weight = 3.0 if ch.name == "cyl_top" else 0.6
    add(B.Part("can_gauge", gauge, paint=p_gauge, seed=59, decals={"cyl_top": d_gauge}))

    # the upper tier, spread evenly: a lidded crock, a keg of beans, two red-glazed clay mugs (handles to +Y)
    tz = SHELF_Z1
    handle = 0.05
    crock_y, keg_y, m0, m1 = SW.centres([2 * CROCK[1][0], 2 * KEG_R] + [2 * MUG_R + handle] * 2,
                                        -INNER + 0.03, INNER - 0.03)
    crock = G.translate(G.lathe(CROCK, 8, name="crock"), TIER_X, crock_y, tz)
    add(B.Part("crock", crock, paint=p_clay, seed=61, weight=1.0, ao_floor=0.7))
    lid = G.translate(G.lathe(CROCK_LID, 8, name="lid"), TIER_X, crock_y, tz)
    add(B.Part("crock_lid", lid, paint=p_crock_lid, seed=63, weight=0.6))
    keg = G.lathe([(KEG_R - 0.012, 0.0), (KEG_R, KEG_H * 0.5), (KEG_R - 0.012, KEG_H), (0.0, KEG_H - 0.008)], 8,
                  name="keg")
    keg = G.translate(keg, TIER_X, keg_y, tz)
    add(B.Part("keg", keg, paint=keg_paint(tz, KEG_H), seed=65, weight=1.8, ao_floor=0.7))
    mug_xy = [(TIER_X + 0.02, m0 - handle / 2), (TIER_X + 0.005, m1 - handle / 2)]
    mprof = [(MUG_R, 0.0), (MUG_R * 0.94, MUG_H * 0.9), (MUG_R, MUG_H), (0.0, MUG_H * 0.55)]
    mugs = [G.translate(G.lathe(mprof, 8, name="mug"), x, y, tz) for x, y in mug_xy]
    # rounded D handles: a half circle in the YZ plane, both ends buried in the wall
    handles = [G.sweep(G.arc_path((x, y + MUG_R - 0.015, tz + 0.057), HANDLE_R, -math.pi / 2, math.pi / 2, 4,
                                  ("y", "z")), 0.017, 5) for x, y in mug_xy]
    add(B.Part("mugs", G.merge(mugs + handles), paint=mug_paint(tz + MUG_H, mug_xy, MUG_R), seed=67, weight=1.2,
               ao_floor=0.7))

    # collision: walls to 0.6, a gable roof to 0.9 (roof n.z 0.6 < 0.6428: too steep to stand on)
    d.collision = G.hull_gable(WIDTH, DEPTH, 0.6, HEIGHT)
    d.particles = []
    return d
