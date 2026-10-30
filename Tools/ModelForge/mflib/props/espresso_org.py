"""19301 EspressoOrg, the Tusk-o-Matic 3000 (Orgrimmar hero machine), CAFE.SPEC.md section 5.8.1.

A two-group lever espresso machine built round a low horizontal black-iron boiler, in dark iron, red lacquer, bone
and rough timber, shaped so it reads as a café machine at a glance, as EspressoSW does: two cocked pull levers
(dark iron shafts, red lacquer grips with bone spike caps) standing well clear above the boiler, portafilters with
hide-wrapped bone handles straight at the barista, a glazed clay cup on a saucer under each spout on an iron grille
drip tray, a chrome steam wand hanging off the left (+Y) end under a red valve wheel, and three mismatched goblin
gauges, the big one standing on a stem between the levers. Orgrimmar, chunky and hand-made: a riveted iron slab on
rough timber runners, a riveted boiler with three red bands and a row of iron spikes along its ridge, strapped onto
timber cradles, a red lacquer apron with the tusk crest carved in bone between the group heads, a boar's pair of
ivory tusks curving up, out and forward from the slab beside the apron, a goblin exhaust stack with a crown of
spikes and smoke at the back left, a red medallion with the crest in bone on each boiler end, and a brass maker's
plate "TUSK-O-MATIC" on the slab front. 1.4 (Y) x 0.75 (X; 0.95 with the handles) x 0.95 yd, front (+X) toward the
barista.

What makes a player name it at 4-15 yd (front three-quarter view), and how big each cue is:
- two pull levers, the highest points of the outline (0.28 dark iron shafts 0.064 thick with a worn bright streak,
  red lacquer grips 0.075 thick, a bone spike cap 0.084 across on top, to about 0.93), against the wall, not the
  boiler; iron and red, so they no longer echo EspressoSW's brass shafts and walnut knobs;
- two group heads (waisted copper bells 0.19 across on iron brackets) with portafilter handles straight at the
  barista, tipped down 12 degrees (0.26 long, 0.06-0.07 thick, dark hide over bone, bone knuckles 0.12 across);
- a cup on a saucer under each spout (cup 0.13 across, 0.09 tall, pale clay with a solid red glaze rim; saucer
  0.16 across);
- a big round pressure gauge on a stem between the levers (dial 0.22 across, needle in the red) and two smaller
  crooked ones on the boiler's shoulders (0.18, 0.16);
- a steam wand (0.064 thick) with its puff of steam beside the machine, under a red valve wheel (0.13 across);
- Orgrimmar: the riveted drum with red bands (0.4 across), ivory tusks (0.17 thick at the root, rising 0.6), ridge
  spikes (0.08 x 0.12), the smoking exhaust stack (0.14 across, its mouth 0.12 under the lever knobs), the bone
  crest on red lacquer (0.27).
The pale bone is kept for the lever caps, the tusks, the crest and the cups; the portafilter handles are dark hide,
and the slab's top and front lip are worn to a bright steel edge, the apron red and the gauge faces a little
brighter, so the machine separates from a dark iron and timber back bar. The exhaust smoke is a mid warm grey
(8A8078, not section 5.2.7's 5A5A5A) and dense at the stack mouth, so it shows against Orgrimmar's brown sky.

Deviations from the section 5.8.1 numbers, for the café cues, the readability rule and a lever-machine outline
(a stepped one: low body, two lever posts, an offset stack; not a dome):
- pull levers over the group heads (not in the design): the lever is what made EspressoSW read as a coffee
  machine, so both heroes share it;
- the boiler is smaller and lower (r 0.20 at z 0.36, not r 0.26 at z 0.45; 0.68 long plus two 0.10 domed caps,
  0.88 in all), set back (x -0.16), so its ridge (0.56) stays under the lever grips; bands at Y 0 and +-0.26 strap
  it onto two 0.08 timber cradles; the ridge spikes are r 0.042 x 0.12 (not 0.035 x 0.11);
- the group heads are EspressoSW's waisted bells, a little fuller (r 0.096), in copper with a red collar on iron
  brackets (iron ones merged with the boiler at 8 yd), at Y +-0.27; the handles point straight at the barista
  (handles turned toward one side went end-on, and vanished, from the other side of the bar);
- the base is a 0.085 iron slab on 0.035 timber runners (0.12 in all);
- the front panel is a 0.22 deep apron box (not 0.06) under the boiler front, so it reads as solid in the 3/4
  views and carries the group heads; the crest is painted relief in bone (iron went black in its shadow);
- the tusks root beside the apron (x 0.03) and curve up, out and forward like a boar's, then back in: a crescent
  in the front view (a straight forward bow read as white cones), tips (r 0.02) at 0.66 and Y +-0.6 beside the
  boiler, not inward over it (tips over the boiler closed the outline into a dome); at most Y +-0.68;
- the gauges: the big one (r 0.11) on a copper stem over the apron, the others (r 0.09, 0.08) on short copper
  pipes (0.06 thick) from the boiler's front shoulders at Y +0.40 and -0.45 (clear of the -Y lever in the 3/4
  view), tilted and twisted; brass, copper and iron bezels;
- the exhaust (r 0.07) stands from the slab beside the boiler's back left end to 0.815, under the lever knobs (a
  stack as tall as the levers made the outline three equal posts: a steam engine), with a sooty throat, its
  collar spikes tilted up 43 degrees, a crown (the kit's flat star tangled with the levers and gauges in the 3/4
  views);
- the steam wand leaves the apron's left end and hangs outboard in front of the tusk, so its plume rises beside
  the machine; the plume is a softer, fainter column than section 5.2.7's wand steam (speed 0.3, life 1.4,
  gravity -0.12, rate 8, latitude 0.3, puffs to 0.26, alpha 9000: about 0.9 yd tall), so the wheel, the tusk and
  the left gauge show through it and it reads as steam, not as a lamp;
- the "TUSK-O-MATIC" plate is on the slab front, where every viewer sees it, not on the side; no pseudo-text;
- the boiler-end medallions are an addition, for the side views;
- wobble: 0.8 cm on the apron, cradles and runners (whose bottoms are put back flat on the bar), 0.4 cm on the
  slab (its 1.40 footprint has 2 cm of tolerance); none on the drip tray, where the saucers stand, or on the
  boiler, whose bands hug it.
"""

import math

from .. import build as B
from .. import emblem as E
from .. import emitters as EM
from .. import font as F
from .. import geom as G
from .. import kit as K
from .. import paint2d as P2
from .. import tex as T

NAME = "EspressoOrg"
DISPLAY = 19301

LACQUER = T.hexc("B5402F")        # the apron, the medallions
LACQUER_DK = T.hexc("9C2A1F")     # the bands, valve wheel, glaze
CLAY = T.hexc("E2CCA2")
SOOT = T.hexc("16130F")
HI, LO = T.IRON_RIVET_HI, T.IRON_RIVET_LO
WORN = T.hexc("C4C6CC")                # iron worn bright at the edges

RUNNER_H = 0.035
BASE_Z1 = 0.12
BASE_W, BASE_D = 1.4, 0.75
BX, BZ, BR = -0.16, 0.36, 0.20    # the boiler: axis along Y through (BX, BZ), radius BR
CYL_Y, CAP_Y = 0.34, 0.44         # cylinder half length; the domed end caps reach +-CAP_Y
BANDS = (-0.26, 0.0, 0.26)        # red bands round the boiler (y)
BAND_HW, BAND_D = 0.032, 0.018    # band half width, depth out of the wall
SPIKES_Y = (-0.33, -0.2, -0.07, 0.07, 0.2, 0.33)
APRON_X0, APRON_X1 = -0.02, 0.2
APRON_W = 0.9
APRON_Z1 = 0.42
GH_X, GH_Y = 0.28, 0.27           # group heads at (GH_X, +-GH_Y)
PF_Z = 0.285                      # portafilter basket bottom; its spout ends 0.023 lower
LEVER_Z = PF_Z + 0.225            # lever pivot over the group head
LEVER_DEG = 18.0                  # cocked lever: up, leaning toward the barista
LEVER_LEN, LEVER_R = 0.28, 0.032
TRAY_X1 = 0.37
TRAY_Z1 = BASE_Z1 + 0.028
SHOT_CUPS = [(GH_X, GH_Y), (GH_X, -GH_Y)]
CUP_R, CUP_H, SAUCER_R = 0.066, 0.088, 0.08
SAUCER_TOP = 0.0096               # kit.cup: the cup's foot stands this high on its saucer
# the +Y tusk's centreline, a cubic Bezier (root, two controls, tip): up, out and forward, the tip turning in
TUSK = ((0.03, 0.56, 0.05), (0.06, 0.655, 0.28), (0.2, 0.65, 0.52), (0.13, 0.6, 0.66))
EXHAUST_AT, EXHAUST_R, EXHAUST_TOP = (-0.27, 0.40), 0.07, 0.78
WAND_R = 0.032
# gauges: (case back centre, facing, radius, bezel metal, needle, dial face, the dial's "up")
GAUGES = (
    ((0.15, 0.0, 0.6), (math.cos(math.radians(12)), 0.0, math.sin(math.radians(12))), 0.11, "brass", 112.0,
     T.hexc("FFF8E8"), (0.0, 0.12, 1.0)),
    ((0.05, 0.40, 0.55), (0.74, 0.5, 0.45), 0.09, "copper", -55.0, T.hexc("FAF4E6"), (0.0, -0.4, 1.0)),
    ((0.06, -0.45, 0.52), (0.93, -0.2, 0.3), 0.08, "iron", 25.0, T.hexc("F8ECC8"), (0.0, 0.45, 1.0)),
)


# ----------------------------------------------------------------------------------------------- paints

def p_runners(ctx, seed, p):
    return T.g_planks(ctx, seed, {"kind": "timber", "count": 1, "nails": True, "ragged": 0.02})


def p_cradles(ctx, seed, p):
    return T.g_planks(ctx, seed, {"kind": "timber", "width": 0.1, "knots": 1})


def p_slab(ctx, seed, p):
    """Dark riveted iron: a rivet frame round every face, a darker top under the soot of the boiler, and its
    edges worn to a bright steel (a lit lip round the top and down the front), so the machine's foot separates
    from the dark iron and timber of the back bar."""
    c = T.g_iron(ctx, seed, {"rust": 0.25, "streak": False})
    e = T.edge_dist(ctx)
    if ctx.chart == "+z":
        c = T.frame_rivets(ctx, T.scale(c, 0.85), 0.035, 0.11, 0.014, HI, LO)
        return T.mix(c, WORN, T.smoothstep(0.022, 0.004, e) * 0.7)
    if ctx.chart in ("+x", "-x", "+y", "-y"):
        c = T.frame_rivets(ctx, c, 0.028, 0.1, 0.013, HI, LO)
        if ctx.t < 0.014:
            c = T.mix(c, WORN, T.smoothstep(0.014, 0.0, ctx.t) * 0.65)     # the worn top lip
    return c


def p_boiler(ctx, seed, p):
    """Riveted iron: soot over the top (darkest along the ridge, clear of the front so the drum reads as iron,
    not a black disc), rivet seams beside every band and round the joints of the domed caps, painted shadows
    along the bands, and a warm heat tint low on the front."""
    c = T.g_iron(ctx, seed, {"rust": 0.12, "streak_k": 0.45, "patina": 0.1})
    x, y, z = ctx.pos
    v = T.fbm3(x * 5.0, y * 5.0, z * 5.0, seed + 3, 3)
    c = T.mix(c, SOOT, T.smoothstep(BZ + 0.5 * BR, BZ + BR, z) * (0.35 + 0.45 * v))
    c = T.mix(c, T.hexc("5A2A1A"), T.smoothstep(BZ - 0.4 * BR, BZ - 0.85 * BR, z) * T.clamp01(ctx.n[0]) * 0.35)
    phi = math.atan2(z - BZ, x - BX)        # 0 at the front, up is positive
    arc = phi * BR
    for by in BANDS:
        d = abs(y - by) - BAND_HW
        if 0.0 <= d < 0.03:
            c = T.mix(c, T.scale(c, 0.45), (1.0 - d / 0.03) ** 1.5 * 0.7)
    rows = [by + s * (BAND_HW + 0.035) for by in BANDS for s in (-1, 1)]
    rows += [j for j in (-CYL_Y + 0.02, CYL_Y - 0.02) if min(abs(j - r) for r in rows) > 0.04]
    ry = min(rows, key=lambda r: abs(y - r))
    if abs(y - ry) < 0.03 and abs(y) <= CYL_Y:
        step = 0.075
        a0 = (math.floor(arc / step) + 0.5) * step
        c = T.rivet_dot(c, -(y - ry), -(arc - a0), 0.014, HI, LO)
    return c


def p_band(ctx, seed, p):
    """Red lacquer bands, worn to the iron on their edges, with a ring of twelve iron bolts."""
    c = T.g_lacquer(ctx, seed, {"color": LACQUER_DK, "worn": 0.5})
    x, y, z = ctx.pos
    by = min(BANDS, key=lambda b: abs(y - b))
    if math.hypot(x - BX, z - BZ) > BR + BAND_D * 0.6:
        phi = math.atan2(z - BZ, x - BX)
        step = 2 * math.pi / 12
        d_arc = abs(((phi + step / 2) % step) - step / 2) * (BR + BAND_D)
        c = T.rivet_dot(c, -(y - by), d_arc if phi % step > step / 2 else -d_arc, 0.013, HI, LO)
    return c


def p_apron(ctx, seed, p):
    """Red lacquer framed in riveted dark iron (the frame covers the rounded edges); the top is an iron plate."""
    e = T.edge_dist(ctx)
    if ctx.chart == "+z":
        c = T.g_iron(ctx, seed, {"rust": 0.15, "streak": False})
        return T.frame_rivets(ctx, c, 0.03, 0.12, 0.013, HI, LO)
    frame = 0.04
    if e < frame:
        c = T.g_iron(ctx, seed + 1, {"rust": 0.2})
        return T.frame_rivets(ctx, c, frame * 0.5, 0.12, 0.0135, HI, LO)
    c = T.scale(T.g_lacquer(ctx, seed + 5, {"color": LACQUER, "gloss": 0.35}), 1.15)  # a brighter red panel
    if e < frame + 0.01:
        c = T.scale(c, 0.45)
    return c


def p_medallion(ctx, seed, p):
    """The boiler-end medallions: a red lacquer face in an iron rim."""
    iron = T.g_iron(ctx, seed + 1, {"rust": 0.2})
    if not ctx.chart.endswith("_top"):
        return iron
    rr = math.hypot(ctx.s - ctx.cw / 2, ctx.t - ctx.ch / 2)
    rim = ctx.cw / 2 - 0.022
    if rr > rim:
        # eight rivets round the rim
        phi = math.atan2(ctx.t - ctx.ch / 2, ctx.s - ctx.cw / 2)
        step = 2 * math.pi / 8
        a0 = round(phi / step) * step
        mid = rim + 0.011
        dx, dy = ctx.s - ctx.cw / 2 - math.cos(a0) * mid, ctx.t - ctx.ch / 2 - math.sin(a0) * mid
        return T.rivet_dot(iron, dx, dy, 0.009, HI, LO)
    c = T.g_lacquer(ctx, seed, {"color": LACQUER, "gloss": 0.3})
    return T.mix(c, T.scale(c, 0.5), T.smoothstep(rim - 0.012, rim, rr))


def p_iron(ctx, seed, p):
    return T.g_iron(ctx, seed, {"rust": 0.2})


def p_hammered(ctx, seed, p):
    return T.g_hammered_iron(ctx, seed, {"rust": 0.15, "dent": 0.04})


def p_group(ctx, seed, p):
    """Goblin copper bells with a red lacquer collar under the shoulder."""
    z = ctx.pos[2]
    if PF_Z + 0.17 <= z <= PF_Z + 0.19:
        return T.g_lacquer(ctx, seed, {"color": LACQUER_DK})
    return T.g_copper(ctx, seed, {"patina": 0.3, "streak_k": 0.5})


def p_brass(ctx, seed, p):
    return T.g_brass(ctx, seed, {"patina": 0.2, "streak_k": 0.6})


def p_lacquer_dk(ctx, seed, p):
    return T.g_lacquer(ctx, seed, {"color": LACQUER_DK, "worn": 0.4})


def _wraps(ctx, c, t, marks):
    """Leather wraps across a bone grip: dark hide bands where t (yd along the grip) falls in a mark."""
    for t0, t1 in marks:
        if t0 <= t <= t1:
            k = (t - t0) / (t1 - t0)
            w = T.g_leather(ctx, 7, {"color": T.hexc("4A2A16")})
            w = T.mix(w, T.hexc("2A160A"), T.smoothstep(0.2, 0.0, min(k, 1 - k)) * 0.7)
            return T.mix(w, T.hexc("A07850"), T.smoothstep(0.3, 0.9, ctx.n[2]) * 0.25)
    return c


def handle_paint(roots):
    """Bone portafilter handles wrapped in dark hide from a bone collar at the root to the bone knuckle end, so
    each reads as a dark stick with a pale knob from either side of the bar. roots: [(root, dir)]."""
    def p_handle(ctx, seed, p):
        c = T.g_bone(ctx, seed, {"kind": "bone", "cracks": 2})
        x, y, z = ctx.pos
        r, hd = min(roots, key=lambda q: (y - q[0][1]) ** 2)
        t = (x - r[0]) * hd[0] + (y - r[1]) * hd[1] + (z - r[2]) * hd[2]
        return _wraps(ctx, c, t, ((0.03, 0.175),))
    return p_handle


def grip_paint(starts, ldir):
    """Lever grips in glossy red lacquer (the Orgrimmar family's red, which no Stormwind piece has) with a dark
    iron ferrule at the bottom and a leather wrap ring in the middle."""
    def p_grip(ctx, seed, p):
        c = T.g_lacquer(ctx, seed, {"color": LACQUER, "gloss": 0.45})
        x, y, z = ctx.pos
        a = min(starts, key=lambda q: (y - q[1]) ** 2)
        t = (x - a[0]) * ldir[0] + (z - a[2]) * ldir[2]
        if t < 0.02:
            return T.mix(T.g_iron(ctx, seed + 3, {"rust": 0.1}), WORN, 0.25)
        return _wraps(ctx, c, t, ((0.06, 0.085),))
    return p_grip


def p_lever(ctx, seed, p):
    """The lever shafts: dark iron with a bright worn streak on the lit side (brass shafts read as EspressoSW's)."""
    c = T.g_iron(ctx, seed, {"rust": 0.15, "streak_k": 0.8})
    return T.mix(c, WORN, T._azimuth_streak(ctx.n, 0.55, 0.5) * 0.35)


def p_cap(ctx, seed, p):
    """The bone spike capping each lever grip, its point lighter."""
    c = T.g_bone(ctx, seed, {"kind": "bone", "cracks": 1})
    return T.mix(c, T.hexc("FFF6E2"), T.smoothstep(0.4, 0.0, ctx.v) * 0.3)


def p_tusk(ctx, seed, p):
    """Ivory with age cracks, a stained root and a leather-and-rope wrap a hand above the root socket."""
    c = T.g_bone(ctx, seed, {"kind": "ivory", "root": 0, "cracks": 4})
    if 0.13 <= ctx.t <= 0.19:
        k = (ctx.t - 0.13) / 0.06
        r = T.g_rope(ctx, seed + 3, {"color": T.hexc("A07A44"), "along": "s", "pitch": 0.06})
        c = T.mix(r, T.scale(r, 0.5), T.smoothstep(0.25, 0.0, min(k, 1 - k)) * 0.6)
    return c


def p_spike(ctx, seed, p):
    """Iron spikes, worn bright toward the points (a cone's t runs from the point down) and lit on top."""
    c = T.g_iron(ctx, seed, {"rust": 0.1})
    if ctx.chart == "cone":
        c = T.mix(c, T.hexc("C4C8D0"), T.smoothstep(0.7, 0.05, ctx.v) * 0.45)
    return T.mix(c, T.hexc("B8BCC4"), T.clamp01(ctx.n[2]) * 0.2)


def p_soot(ctx, seed, p):
    return T.g_soot(ctx, seed, {"top": 0.95, "span": 0.3, "under": T.hexc("3A3634")})


def p_throat(ctx, seed, p):
    return T.mix(T.g_iron(ctx, seed, {"rust": 0.0, "streak": False}), SOOT, 0.85)


def p_copper(ctx, seed, p):
    return T.g_copper(ctx, seed, {"patina": 0.3})


def bezel_paint(metal):
    def p_bezel(ctx, seed, p):
        if metal == "brass":
            return T.g_brass(ctx, seed, {"patina": 0.15})
        if metal == "copper":
            return T.g_copper(ctx, seed, {"patina": 0.25})
        return T.g_iron(ctx, seed, {"rust": 0.35})
    return p_bezel


def p_tray(ctx, seed, p):
    """Dark iron with a lit rim; the front edge a dark band between two lit lips."""
    c = T.g_iron(ctx, seed, {"streak": False, "rust": 0.2})
    if ctx.chart == "+z":
        if T.edge_dist(ctx) < 0.018:
            return T.mix(c, T.hexc("9A9EA8"), 0.35)
        return c
    if ctx.chart == "+x":
        z = ctx.pos[2]
        if z > TRAY_Z1 - 0.008:
            return T.mix(c, T.hexc("A4A8B0"), 0.35)
        if z < BASE_Z1 + 0.002:
            return c
        return T.mix(T.hexc("121214"), c, 0.3)
    return c


def p_plate(ctx, seed, p):
    c = T.g_brass(ctx, seed, {"streak": False, "patina": 0.12, "freq": 6.0})
    if ctx.chart.endswith("_front"):
        cy = ctx.ch / 2
        for cx in (0.025, ctx.cw - 0.025):
            c = T.rivet_dot(c, ctx.s - cx, ctx.t - cy, 0.012, HI, LO)
    return c


def cup_paints(centres, rim_z):
    """Pale clay cups with a solid band of red glaze round the rim (no drips: drips read as spilled paint at
    4 yd), crema in the cup, pale clay saucers with a thin glazed edge."""
    def near(x, y):
        return min(centres, key=lambda c: (x - c[0]) ** 2 + (y - c[1]) ** 2)

    def p_cup(ctx, seed, p):
        cx, cy = near(ctx.pos[0], ctx.pos[1])
        # a drip spacing wider than the cup leaves only the band
        return T.g_glaze(ctx, seed, {"color": CLAY, "glaze": LACQUER_DK, "top": rim_z, "center": (cx, cy),
                                     "radius": CUP_R, "band": 0.018, "drip": 0.0, "spacing": 1.0})

    def p_saucer(ctx, seed, p):
        c = T.g_ceramic(ctx, seed, {"color": CLAY})
        cx, cy = near(ctx.pos[0], ctx.pos[1])
        if math.hypot(ctx.pos[0] - cx, ctx.pos[1] - cy) > SAUCER_R - 0.007:
            c = T.mix(c, LACQUER_DK, 0.85)
        return c

    def p_coffee(ctx, seed, p):
        return T.g_coffee(ctx, seed, {})
    return p_cup, p_saucer, p_coffee


# ---------------------------------------------------------------------------------------------- decals

def d_crest(w, h):
    """The tusk crest carved in bone, centred on the apron front between the group heads: a cream mark (tusks
    round a cup on a saucer) that holds at 8 yd in the shadow under the boiler."""
    img = T.Img(w, h, (0, 0, 0, 0))
    s = int(h * 0.88)
    if s > 8:
        P2.composite(img, E.render_relief("tusk_crest", s, s, P2.BONE_RELIEF), (w - s) // 2, (h - s) // 2)
    return img


def d_medallion(w, h):
    """The tusk crest carved in bone on the boiler-end medallions."""
    img = T.Img(w, h, (0, 0, 0, 0))
    s = int(min(w, h) * 0.74)
    if s > 8:
        P2.composite(img, E.render_relief("tusk_crest", s, s, P2.BONE_RELIEF), (w - s) // 2, (h - s) // 2)
    return img


def d_name(w, h):
    """The maker's plate: a red lacquer band in a dark inset frame, "TUSK-O-MATIC" in cream vector capitals."""
    img = T.Img(w, h, (0, 0, 0, 0))
    bw = max(1, int(h * 0.07))
    side = int(h * 0.75)            # room for the rivets at both ends
    for y in range(h):
        for x in range(w):
            e = min(x, y, w - 1 - x, h - 1 - y)
            if bw <= e < 2 * bw:
                img.set(x, y, T.hexc("4A2E0C"), 0.85)
            elif e >= 2 * bw and side <= x < w - side:
                img.set(x, y, T.scale(LACQUER_DK, 0.85 + 0.25 * (1.0 - y / float(h))), 1.0)
    try:
        cap = F.fit_cap("TUSK-O-MATIC", w - 2 * side - 4 * bw, h - 4 * bw, min_cap=4.0)
        m = F.vector_mask("TUSK-O-MATIC", cap)
        F.two_tone(img, m, T.hexc("F4E6C4"), T.hexc("2A0A04"), (w - m.w) // 2, (h - m.h) // 2, 1, (1, 1),
                   T.hexc("120402"))
    except ValueError:
        if w >= 128:
            raise           # at full size a text that does not fit is an error (section 5.5.1)
    return img


def gauge_decal(needle, face):
    def d_gauge(w, h):
        return P2.gauge_face(w, h, {"needle_deg": needle, "face": face})
    return d_gauge


def d_grille(w, h):
    """Seven bold slots in near-black between iron bars."""
    return P2.grille(w, h, {"slots": 7, "margin": 0.18, "duty": 0.6, "dark": T.hexc("0C0C0E")})


# ------------------------------------------------------------------------------------------------ parts

def _along_y(mesh_z, x, y, z):
    """A mesh built along +Z (centred on z 0), turned to lie along Y and moved to (x, y, z)."""
    return G.transform(mesh_z, G.mat_chain(G.mat_translate(x, y, z), G.mat_rot_x(math.pi / 2)))


def _cross(r, w):
    """A plus-shaped polygon (four spokes) of arm length r and width w."""
    h = w / 2
    return [(h, h), (r, h), (r, -h), (h, -h), (h, -r), (-h, -r), (-h, -h), (-r, -h), (-r, h), (-h, h), (-h, r),
            (h, r)]


def _spike(base, direction, r, h, sides=5, cap=False):
    """geom.spike, by default without its base cap, for spikes whose base is buried in the boiler (no hidden
    triangles or charts); cap=True closes a base that shows (the exhaust crown, seen from below)."""
    m = G.cone(r, 0.0, h, sides, caps=(cap, False))
    return G.transform(m, G.mat_chain(G.mat_translate(*base), G.mat_look(direction)))


def _boiler_mesh():
    """The boiler: a lathe along Y with domed caps (seam at the back, u 0.5 at the front)."""
    prof = []
    dome = CAP_Y - CYL_Y
    for k in range(5):
        a = (math.pi / 2) * k / 4
        prof.append((BR * math.sin(a), -CYL_Y - dome * math.cos(a)))
    for yy in (-0.15, 0.15):
        prof.append((BR, yy))
    for k in range(5):
        a = (math.pi / 2) * (4 - k) / 4
        prof.append((BR * math.sin(a), CYL_Y + dome * math.cos(a)))
    m = G.lathe(prof, 20, angle=60.0, name="boiler")
    return G.transform(m, G.mat_chain(G.mat_translate(BX, 0.0, BZ), G.mat_rot_x(-math.pi / 2)))


def _band(y, sides=16):
    """A band round the boiler (a lathe of four points along Y); 16 sides are enough: the 16-gon's flats stay
    1.4 cm outside the 20-sided drum."""
    r0 = BR - 0.004
    prof = [(r0, -BAND_HW), (BR + BAND_D, -BAND_HW * 0.6), (BR + BAND_D, BAND_HW * 0.6), (r0, BAND_HW)]
    m = G.lathe(prof, sides, angle=80.0, name="band")
    return G.transform(m, G.mat_chain(G.mat_translate(BX, y, BZ), G.mat_rot_x(-math.pi / 2)))


def _drum_r(y):
    """The boiler's radius at y (the domed caps fall away)."""
    if abs(y) <= CYL_Y:
        return BR
    q = (abs(y) - CYL_Y) / (CAP_Y - CYL_Y)
    return BR * math.sqrt(max(0.0, 1.0 - q * q))


def _on_drum(y, toward, inset=0.01):
    """The point on the boiler's surface at y that faces `toward` (a point in front of it), sunk by `inset`."""
    dx, dz = toward[0] - BX, toward[2] - BZ
    k = (_drum_r(y) - inset) / (math.hypot(dx, dz) or 1.0)
    return (BX + dx * k, y, BZ + dz * k)


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (1.4, 0.75, 0.95)
    d.depth_with_handles = 0.95
    d.budget = 4500
    d.collision_max = 120
    d.atlas = {"atlas": 512}
    d.kind = "machine"
    d.max_height = 0.95
    d.sloped_top = True
    add = d.add

    # rough timber runners under a riveted iron slab (no bottoms: they stand on the bar). Their tops sink 1.5 cm
    # into the slab; after the wobble the bottom edge is put back on the bar (z 0), so no slit shows under them
    runners = []
    for k, sy in enumerate((1, -1)):
        r = G.box(0.13, 0.7, RUNNER_H + 0.015, faces="+x -x +y -y +z")
        r = G.wobble(G.plank_edges(r, 31 + k, 0.025, "x", inward=True), 0.008, 33 + k)
        r.p = [(x, yy, 0.0 if z < 0.02 else z) for x, yy, z in r.p]
        runners.append(G.translate(G.recompute_normals(r, 40.0), 0.015, sy * 0.52, 0.0))
    add(B.Part("runners", G.merge(runners), paint=p_runners, seed=11, weight=0.5))
    # closed underneath: the runner gap shows its bottom to a low camera
    slab = G.box(BASE_W, BASE_D, BASE_Z1 - RUNNER_H, 0.02, faces="+x -x +y -y +z -z", z0=RUNNER_H)
    slab = G.wobble(slab, 0.004, 13)
    for ch in slab.charts:
        ch.weight = {"-x": 0.4, "+z": 0.6, "+x": 0.9, "-z": 0.1}.get(ch.name, 0.7)
    add(B.Part("slab", slab, paint=p_slab, seed=12))

    # timber cradles carry the boiler; the outer bands strap it down onto them
    cradles = []
    for sy in (1, -1):
        cr = G.planks(0.1, 0.36, 0.08, 2, "x", seed=41 + sy, ragged=0.015, wobble_amp=0.008, z0=BASE_Z1 - 0.01)
        cradles.append(G.translate(cr, BX, sy * BANDS[2], 0.0))
    add(B.Part("cradles", G.merge(cradles), paint=p_cradles, seed=14, weight=0.6))

    # the boiler: a riveted drum along Y with domed caps, three red bands, a row of ridge spikes
    add(B.Part("boiler", _boiler_mesh(), paint=p_boiler, seed=21, weight=1.0))
    add(B.Part("bands", G.merge([_band(y) for y in BANDS]), paint=p_band, seed=23, weight=1.1))
    spikes = [_spike((BX, y, BZ + _drum_r(y) - 0.015), (0.0, 0.0, 1.0), 0.042, 0.12) for y in SPIKES_Y]
    add(B.Part("spikes", G.merge(spikes), paint=p_spike, seed=25, weight=0.6))
    # a red medallion with the crest carved in bone on each domed end (what the side views show)
    for s in (1, -1):
        med = G.transform(G.cylinder(0.105, 0.035, 16, (False, True)),
                          G.mat_chain(G.mat_translate(BX, s * (CAP_Y - 0.03), BZ),
                                      G.mat_disc_facing((0.0, s, 0.0))))
        add(B.Part("medallion_%s" % ("left" if s > 0 else "right"), med, paint=p_medallion, seed=27 + s,
                   weight=1.5, decals={"cyl_top": d_medallion}))

    # the apron under the boiler front: red lacquer in a riveted iron frame, the crest between the group heads
    # its foot sinks 2.5 cm into the slab, so the wobbled bottom edge never lifts above the wobbled slab top
    apron = G.box(APRON_W, APRON_X1 - APRON_X0, APRON_Z1 - BASE_Z1 + 0.025, 0.025, faces="+x -x +y -y +z",
                  z0=BASE_Z1 - 0.025)
    apron = G.wobble(G.translate(apron, (APRON_X0 + APRON_X1) / 2, 0.0, 0.0), 0.008, 32)
    for ch in apron.charts:
        ch.weight = {"+x": 1.5, "+z": 0.5, "-x": 0.2}.get(ch.name, 0.8)
    add(B.Part("apron", apron, paint=p_apron, seed=31, decals={"+x": d_crest}))

    # two lever group heads: flared copper bells on iron brackets from the apron, portafilters with bone
    # handles toward the barista, and the cocked pull levers (brass arms, bone grips with knuckle ends)
    gh, brackets, baskets, handles, hubs, arms, grips, caps = [], [], [], [], [], [], [], []
    hdeg = math.radians(102)
    ldeg = math.radians(LEVER_DEG)
    ldir = (math.sin(ldeg), 0.0, math.cos(ldeg))
    roots, starts = [], []
    for s in (1, -1):
        y = s * GH_Y
        # EspressoSW's waisted bell (a plain cone read as an upturned flower pot), a little fuller
        gprof = [(0.062, PF_Z + 0.045), (0.074, PF_Z + 0.055), (0.078, PF_Z + 0.08), (0.07, PF_Z + 0.103),
                 (0.064, PF_Z + 0.113), (0.082, PF_Z + 0.138), (0.096, PF_Z + 0.163), (0.096, PF_Z + 0.183),
                 (0.06, PF_Z + 0.198), (0.0, PF_Z + 0.201)]
        gh.append(G.translate(G.lathe(gprof, 10), GH_X, y, 0.0))
        bl = GH_X - APRON_X1 + 0.06
        brackets.append(G.translate(G.box(0.1, bl, 0.075, faces="+x -x +y -y +z -z", z0=APRON_Z1 - 0.005),
                                    GH_X - bl / 2, y, 0.0))
        baskets.append(G.translate(G.cylinder(0.062, 0.045, 10, (True, False)), GH_X, y, PF_Z))
        baskets.append(G.translate(G.cylinder(0.02, 0.026, 6, (True, False)), GH_X, y, PF_Z - 0.023))
        # straight at the barista, tipped down 12 degrees (turned handles hid end-on from one side of the bar)
        hdir = (math.sin(hdeg), 0.0, math.cos(hdeg))
        side = (-hdir[1], hdir[0], 0.0)
        h0 = G.add((GH_X, y, PF_Z + 0.022), G.mul(hdir, 0.035))
        roots.append((h0, hdir))
        baskets.append(G.transform(G.cylinder(0.037, 0.04, 8, (False, True)),
                                   G.mat_chain(G.mat_translate(*h0), G.mat_look(hdir))))
        h1 = G.add(h0, G.mul(hdir, 0.215))
        shaft = G.sweep([h0, G.add(h0, G.mul(hdir, 0.1)), h1],
                        lambda t: 0.031 + 0.006 * (2.0 * t - 1.0) ** 2, 8, caps=(True, True))
        kn = G.add(h1, G.mul(hdir, 0.012))
        knuckles = [G.translate(G.sphere(0.032, 8, 4), *G.add(kn, G.mul(G.norm(side), k * 0.026)))
                    for k in (1, -1)]
        handles += [shaft] + knuckles
        # the lever: an iron hub on the bracket, a brass arm, a hide-wrapped grip ending in one bone knob
        hubs.append(_along_y(G.cylinder(0.036, 0.13, 8, True, z0=-0.065), GH_X, y, LEVER_Z))
        a0 = (GH_X, y, LEVER_Z)
        a1 = (GH_X + ldir[0] * LEVER_LEN, y, LEVER_Z + ldir[2] * LEVER_LEN)
        arms.append(G.sweep([a0, a1], LEVER_R, 8, caps=(True, False), up=(0.0, 1.0, 0.0)))
        g0 = (a1[0] - ldir[0] * 0.02, y, a1[2] - ldir[2] * 0.02)
        starts.append(g0)
        grips.append(G.transform(G.capsule(0.0375, 0.15, 8), G.mat_chain(G.mat_translate(*g0),
                                                                          G.mat_rot_y(ldeg))))
        kc = G.add(g0, G.mul(ldir, 0.13))
        caps.append(G.spike(kc, ldir, 0.042, 0.062, 8))
    add(B.Part("group_heads", G.merge(gh), paint=p_group, seed=61, weight=1.1))
    add(B.Part("brackets", G.merge(brackets), paint=p_iron, seed=62, weight=0.5))
    add(B.Part("baskets", G.merge(baskets), paint=p_iron, seed=63, weight=0.6))
    add(B.Part("handles", G.merge(handles), paint=handle_paint(roots), seed=65, weight=1.2))
    add(B.Part("lever_hubs", G.merge(hubs), paint=p_iron, seed=68, weight=0.5))
    add(B.Part("levers", G.merge(arms), paint=p_lever, seed=69, weight=0.9))
    add(B.Part("lever_grips", G.merge(grips), paint=grip_paint(starts, ldir), seed=70, weight=1.0))
    add(B.Part("lever_caps", G.merge(caps), paint=p_cap, seed=71, weight=0.8))

    # three mismatched goblin gauges, cases closed at the back (the stems leave them in the open): the big one
    # on a copper stem between the levers, two on short copper pipes from the boiler's front shoulders
    # (kit.gauge's case and bezel, with the dial turned about its axis: goblin gauges sit crooked)
    pipes = []
    for k, (c, f, r, metal, needle, face, up) in enumerate(GAUGES):
        f = G.norm(f)
        m = G.mat_chain(G.mat_translate(*c), G.mat_disc_facing(f, up))
        case = G.transform(G.cylinder(r, 0.045, 16, (True, True)), m)
        bezel = G.transform(G.torus(r + 0.004, 0.019 if k == 0 else 0.016, 12, 4),
                            G.mat_chain(m, G.mat_translate(0, 0, 0.045)))
        add(B.Part("gauge%d" % k, case, paint=bezel_paint(metal), seed=80 + k, weight=2.6 if k == 0 else 2.2,
                   decals={"cyl_top": gauge_decal(needle, face)}))
        add(B.Part("gauge%d_bezel" % k, bezel, paint=bezel_paint(metal), seed=84 + k, weight=0.6))
        s_pt = _on_drum(c[1] * 0.9, c)
        out = G.norm(G.sub(c, s_pt))
        path = G.bezier_path(s_pt, G.add(s_pt, G.mul(out, 0.06)), G.sub(c, G.mul(f, 0.06)),
                             G.add(c, G.mul(f, 0.01)), 6 if k == 0 else 5)
        pipes.append(G.sweep(path, 0.03, 8))
    add(B.Part("gauge_pipes", G.merge(pipes), paint=p_copper, seed=88, weight=0.6))

    # the tusks: ivory, sweeping up and forward like a boar's from iron sockets on the slab beside the apron
    tusks, sockets = [], []
    for s in (1, -1):
        p0, c1, c2, p1 = [(q[0], s * q[1], q[2]) for q in TUSK]
        tusks.append(G.sweep(G.bezier_path(p0, c1, c2, p1, 10), lambda t: 0.085 - 0.065 * t, 8, caps=(False, True),
                             name="horn"))
        sockets.append(G.translate(G.lathe([(0.098, BASE_Z1 - 0.01), (0.098, BASE_Z1 + 0.03),
                                            (0.086, BASE_Z1 + 0.05), (0.0, BASE_Z1 + 0.05)], 10),
                                   p0[0] + 0.004, p0[1] + s * 0.004, 0.0))
    add(B.Part("tusks", G.merge(tusks), paint=p_tusk, seed=91, weight=1.1))
    add(B.Part("tusk_sockets", G.merge(sockets), paint=p_hammered, seed=92, weight=0.5))

    # the goblin exhaust stack at the back left, standing from the slab beside the boiler's end: sooty pipe,
    # flared mouth, and a collar of spikes tilted up into a crown (the kit's flat star tangles with the levers
    # and gauges in the 3/4 views); no spike points straight back, to keep the depth
    ex = K.exhaust((EXHAUST_AT[0], EXHAUST_AT[1], BASE_Z1 - 0.01), EXHAUST_TOP - BASE_Z1 + 0.01, EXHAUST_R, 0)
    add(B.Part("exhaust", G.merge([ex["pipe"], ex["mouth"]]), paint=p_soot, seed=95, weight=0.8))
    # a sooty throat closes the open pipe (from above, a tauren saw the bar through it): level with the mouth's
    # inner lip and wider than it, so its edge runs into the flare and no ray passes between them
    throat = G.translate(G.disc(0.064, 8, z=EXHAUST_TOP + 0.1 * EXHAUST_R), EXHAUST_AT[0], EXHAUST_AT[1], 0.0)
    add(B.Part("exhaust_throat", throat, paint=p_throat, seed=94, weight=0.2))
    ring_at = (EXHAUST_AT[0], EXHAUST_AT[1], EXHAUST_TOP - 0.12)
    crown = [_spike(G.add(ring_at, (-math.sin(a) * 0.08, math.cos(a) * 0.08, 0.0)),
                    (-math.sin(a) * math.cos(0.75), math.cos(a) * math.cos(0.75), math.sin(0.75)), 0.03, 0.085,
                    cap=True)
             for a in (math.radians(126 + 72 * i) for i in range(5))]
    collar = G.merge([G.translate(G.torus(EXHAUST_R + 0.006, 0.018, 8, 4), *ring_at)] + crown)
    add(B.Part("exhaust_collar", collar, paint=p_spike, seed=96, weight=0.5))

    # the steam wand (thin chrome, 0.064 thick): out of the apron's left end, forward past the tusk and down,
    # its tip hanging outboard of the drip tray so the steam rises beside the machine; the red valve wheel
    # stands on the end face above its root
    wx, wy = 0.14, APRON_W / 2
    wand_path = G.polyline_join(
        G.bezier_path((wx, wy - 0.01, 0.3), (wx, wy + 0.05, 0.3), (wx + 0.04, wy + 0.06, 0.3),
                      (wx + 0.11, wy + 0.07, 0.295), 5),
        G.bezier_path((wx + 0.11, wy + 0.07, 0.295), (wx + 0.15, wy + 0.07, 0.29), (wx + 0.16, wy + 0.1, 0.25),
                      (wx + 0.17, wy + 0.11, 0.19), 5))
    wand = G.sweep(wand_path, WAND_R, 6, caps=(False, True))
    add(B.Part("wand", wand, "chrome", "IronEnv"))
    wheel_m = G.mat_chain(G.mat_translate(wx, wy + 0.045, 0.425), G.mat_disc_facing((0.0, 1.0, 0.0)))
    wheel = G.merge([
        G.transform(G.torus(0.055, 0.012, 10, 4), wheel_m),
        G.transform(G.extrude(_cross(0.055, 0.016), 0.014), G.mat_chain(wheel_m, G.mat_translate(0, 0, -0.007),
                                                                          G.mat_rot_z(math.pi / 4))),
        G.transform(G.cylinder(0.018, 0.05, 6, True), G.mat_chain(G.mat_translate(wx, wy - 0.01, 0.425),
                                                                   G.mat_disc_facing((0.0, 1.0, 0.0))))])
    add(B.Part("valve_wheel", wheel, paint=p_lacquer_dk, seed=97, weight=0.6))

    # the drip tray in front of the apron: thin dark iron with a bold painted grille. Its foot sinks 2 cm into the
    # slab, under the slab's rounded front edge (from below, a 0.5 cm foot left a slit into the tray)
    tray_d = TRAY_X1 - APRON_X1
    tray = G.box(0.96, tray_d, TRAY_Z1 - BASE_Z1 + 0.02, 0.008, z0=BASE_Z1 - 0.02, faces="+x -x +y -y +z")
    tray = G.translate(tray, APRON_X1 + tray_d / 2, 0.0, 0.0)
    for ch in tray.charts:
        ch.weight = {"+z": 0.9, "+x": 0.9}.get(ch.name, 0.4)
    add(B.Part("drip_tray", tray, paint=p_tray, seed=99, decals={"+z": d_grille}))

    # a glazed clay cup on a saucer under each spout, handles turned out toward the barista's sides
    p_cup, p_saucer, p_coffee = cup_paints(SHOT_CUPS, TRAY_Z1 + SAUCER_TOP + CUP_H)
    cups, saucers, coffee = [], [], []
    for x, y in SHOT_CUPS:
        kc = K.cup(CUP_R, CUP_H, SAUCER_R, False, 8, 0.8, 0.009)
        rot = G.mat_chain(G.mat_translate(x, y, TRAY_Z1), G.mat_rot_z(math.radians(-35 if y > 0 else 215)))
        ring = G.torus(CUP_H * 0.3, 0.012, 7, 4, arc=math.pi * 1.25, start=-math.pi * 0.625)
        handle = G.transform(ring, G.mat_chain(G.mat_translate(0.0, CUP_R * 0.82, SAUCER_TOP + CUP_H * 0.58),
                                               G.mat_rot_z(math.pi / 2), G.mat_rot_x(math.pi / 2)))
        cups.append(G.transform(G.merge([kc["cup"], handle]), rot))
        saucers.append(G.transform(kc["saucer"], rot))
        coffee.append(G.transform(kc["coffee"], rot))
    add(B.Part("shot_cups", G.merge(cups), paint=p_cup, seed=101, weight=1.6, ao_floor=0.8))
    add(B.Part("shot_saucers", G.merge(saucers), paint=p_saucer, seed=103, weight=0.8, ao_floor=0.8))
    add(B.Part("shot_coffee", G.merge(coffee), paint=p_coffee, seed=102, weight=0.6, ao_floor=0.7))

    # the maker's plate on the slab front
    pw, ph = 0.46, 0.07
    plate = G.extrude([(-pw / 2, -ph / 2), (pw / 2, -ph / 2), (pw / 2, ph / 2), (-pw / 2, ph / 2)], 0.012, 0.004)
    plate = G.transform(plate, G.mat_chain(G.mat_translate(BASE_D / 2 - 0.004, 0.0, (RUNNER_H + BASE_Z1) / 2),
                                           G.MAT_EXTRUDE_FRONT))
    for ch in plate.charts:
        ch.weight = 3.0 if ch.name.endswith("_front") else 0.4
    add(B.Part("name_plate", plate, paint=p_plate, seed=105, decals={"extrude_front": d_name}))

    # collision: walls to 0.45, a gable roof to 0.95 (roof n.z 0.6 < 0.6428: too steep to stand on)
    d.collision = G.hull_gable(BASE_W, BASE_D, 0.45, 0.95)

    # the wand plume is a softer, fainter column than section 5.2.7's (see the docstring); the exhaust smoke is
    # the preset
    tip = wand_path[-1]
    d.particles = [EM.steam((tip[0], tip[1], tip[2] - 0.02), speed=0.3, life=1.4, gravity=-0.12, emission_rate=8.0,
                            latitude=0.3, scales=((0.04, 0.04), (0.14, 0.14), (0.26, 0.26)), alphas=(0, 9000, 0)),
                   EM.exhaust_smoke(ex["at_top"], colors=((138.0, 128.0, 120.0),) * 3, alphas=(14000, 20000, 0))]
    d.model_frame = {"position": [0, 0, -0.38], "scale": 1.5, "facing": 0.4}
    return d
