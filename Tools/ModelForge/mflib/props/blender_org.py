"""19305 BlenderOrg, the Shake-Shredder (Orgrimmar milkshake blender), CAFE.SPEC.md section 5.8.1.

A countertop milkshake blender in dark iron, red lacquer, ivory and rough timber, shaped so a player names it at a
glance: a tall glass jar full of pink shake, an iron hoop round its waist and a curved ivory tusk for a handle (+Y,
the barista's right hand), and inside it a big toothed saw blade standing upright at the bottom of the jar,
half-buried in the shake with its top teeth breaking the froth, pink on its teeth and splattered up the glass. The
jar stands in a spiked iron collar on a squat riveted iron motor base: the tusk crest in bone relief and two big red
mushroom buttons on the front, red lacquer side panels, a goblin gauge (needle in the red) on the right and a rusty
exhaust pipe with a red band curving up the left to a brass trumpet mouth, black with soot inside. A red lacquer lid
on a riveted iron band with an iron spike on top. Orcish proportions: a crooked plank board, a heavy tapered base
with a slight wobble. 0.4 (Y) x 0.4 (X) x 0.75 yd, front (+X) toward the barista.

Deviations from the section 5.8.1 design, for recognizability and the readability rule (>= 0.06 yd):
- the saw blade (an extruded 6-tooth blade, r 0.11 with teeth 0.045 deep) stands upright, facing the barista and
  turned 15 degrees toward the usual 3/4 view, low in the jar (its centre at 0.47, its foot 0.05 over the floor) and
  half-buried in the shake: a disc lying flat at the bottom would be hidden by the shake and seen edge-on at eye
  height, while the upright blade's top teeth break the surface where it belongs, low in the jar (a blade floating
  in the upper half read as a mistake); the glass in front of it is splattered only at the waterline. The teeth are
  dark steel with only their points filed bright, so the toothed outline reads against the pale far wall of the
  glass behind it (the jar is section 5.2.5's single-shell glass1, drawn on both sides), and a dark iron hub with a
  ring of six bright bolts inside a red lacquer ring and a bright steel ring make the disc a saw, with no dark pupil
  in a coloured iris to read as an eye; the shake stands at 0.5 so 0.08 of the blade (its top teeth) shows above the
  froth;
- the handle is a curved ivory tusk in two riveted iron clamps (not a plain grip), the Orgrimmar cue on the jar
  itself; the top clamp hangs from the lid band, a lug of the lid, so it does not read as a loose block;
- the exhaust pipe is 0.07 across (r 0.035), its trumpet mouth 0.108, with an inner wall and a plug at its
  throat painted soot-black, so it reads as a sooty goblin exhaust (not a hose) and never shows the floor
  through it; the trumpet's foot is a sleeve a little wider than the pipe, so the pipe's corners never poke out;
- the exhaust pipe has 6 sides (section 5.4 asks 8 at r 0.03-0.1) for the budget: 8 sides would cost 28
  triangles, giving 910 > 900; at r 0.035 it is still 0.061 across the flats;
- the base is 0.24 tall (the crest and the two buttons share its front: crest above, buttons below), so the jar
  is 0.33 of the 0.75 height, and the lid's spike makes the top;
- the collision is a gable-topped box (section 5.2.6: every machine has a sloped or peaked top), not a flat box;
- the collar and lid lathes have 10 sides (section 5.4 asks 12-16 at r 0.1-0.3): the 900 triangles go to the
  silhouette (the saw, the tusk, the exhaust trumpet with its inner wall); at 10 yd the difference is 2 mm. The
  shake has the jar's 12 sides, lined up with them, so it fills the glass like a liquid 4 mm inside the wall
  (a 10-sided shake in the 12-sided jar left a gap of 1 cm or more at its flats and read as a pink cake);
- the glass body is alpha 0.28 (71, the bottom of section 5.2.5's 70-110), the clearest the rule allows, with
  BlenderSW's near-neutral tint (a warm tint read as murky amber over the pink) and a bright band under the lid,
  so the saw and the shake show through it;
- the iron hoop has no painted rivets; the collar's and the lid band's rivets (r 0.017 and 0.016, about 5 texels
  across) are close-range charm that fades past about 8 yd, as the hoop's would;
- added: the plank board, the spiked collar (four iron spikes), the iron hoop, the gauge, the lid spike and the
  painted splatter on the glass and the saw (soft round splats, 0.03-0.05 across on the glass and 0.02-0.03 on
  the saw, 3-6 texels with an edge fading over one, so they read as drops and not as pixel crosses).
"""

import math

from .. import build as B
from .. import emblem as E
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "BlenderOrg"
DISPLAY = 19305

RED = T.hexc("B5402F")
DARK_RED = T.hexc("9C2A1F")
SHAKE_C = T.hexc("F6809E")

BOARD_H = 0.045
BASE_W = 0.34                       # the motor base's foot (square)
BASE_Z0, BASE_Z1 = BOARD_H, 0.285
SINK = 0.009                        # the base's rounded foot sinks into the board by this much
TAPER = 0.14
FRAME = 0.028                       # the riveted iron frame round the base's panels
COLLAR_Z1 = 0.335
JAR = [(0.1, 0.31), (0.102, 0.335), (0.122, 0.58), (0.13, 0.628), (0.133, 0.64)]   # the glass wall (r, z)
HOOP_Z = 0.37
SHAKE_TOP = 0.5
SAW_C = (0.0, 0.0, 0.47)            # the saw blade's centre: low in the jar, its top teeth through the froth
SAW_TEETH = 6
SAW_R, SAW_R_IN = 0.11, 0.065       # tooth points, gullets: teeth 0.045 deep and about 0.11 wide
SAW_FACING = math.radians(15.0)
SAW_RIGHT = (-math.sin(SAW_FACING), math.cos(SAW_FACING), 0.0)   # across the blade's face, seen from the front
LID_Z0, LID_BAND, LID_TOP = 0.628, 0.034, 0.684   # the lid's foot, its riveted iron band, its crown
CREST_Z, CREST_S = 0.212, 0.108     # the tusk crest on the base front: centre height, size
BUTTON_YS = (-0.072, 0.072)         # the red buttons along the base front (untapered)
BUTTON_Z = 0.106
BUTTON_R = 0.04
GAUGE_Z, GAUGE_R = 0.165, 0.05
TUSK = ((0.0, 0.112, 0.385), (0.0, 0.126, 0.6))   # the tusk handle: root (bottom) and tip (top)
EXHAUST_X = 0.03                    # the exhaust pipe's plane, a little forward so the 3/4 views see it
EXHAUST_R = 0.035


def _taper_at(z):
    return 1.0 - TAPER * (z - BASE_Z0) / (BASE_Z1 - BASE_Z0)


LEAN = math.atan(BASE_W / 2 * TAPER / (BASE_Z1 - BASE_Z0))   # the base faces lean in by this much


def _button_frames():
    """(centre on the base front, axis, up, right) of each button in model space."""
    f = _taper_at(BUTTON_Z)
    axis = (math.cos(LEAN), 0.0, math.sin(LEAN))
    up = (-math.sin(LEAN), 0.0, math.cos(LEAN))
    return [((BASE_W / 2 * f, ys * f, BUTTON_Z), axis, up, (0.0, 1.0, 0.0)) for ys in BUTTON_YS]


BUTTONS = _button_frames()


def _exhaust_path():
    """The exhaust pipe out of the left-hand side panel: an elbow, then a curve up and back to the mouth."""
    ex, ey = EXHAUST_X, -0.143
    return G.polyline_join(
        [(ex, -0.12, 0.15)],
        G.arc_path((ex, ey, 0.18), 0.028, -math.pi / 2, -math.pi, 2, ("y", "z")),
        G.bezier_path((ex, -0.171, 0.24), (ex, -0.171, 0.42), (ex - 0.005, -0.17, 0.49), (ex - 0.04, -0.162, 0.53),
                      3))


EXHAUST_PATH = _exhaust_path()
MOUTH_AT = EXHAUST_PATH[-1]         # the trumpet mouth's foot and axis (it points up and back)
MOUTH_AXIS = G.norm(G.sub(EXHAUST_PATH[-1], EXHAUST_PATH[-2]))
GAUGE_AT = (0.0, BASE_W / 2 * _taper_at(GAUGE_Z) - 0.004, GAUGE_Z)
GAUGE_FACING = G.norm((0.3, 1.0, 0.25))     # turned toward the front and up, a goblin's idea of square


# ----------------------------------------------------------------------------------------------- paints

def p_board(ctx, seed, p):
    return T.g_planks(ctx, seed, {"kind": "timber", "count": 1, "nails": True, "ragged": 0.02})


def p_base(ctx, seed, p):
    """A riveted hammered-iron frame round the panels: dark hammered iron on the front (the bone crest and the
    red buttons stand out on it), red lacquer on the sides, plain iron at the back; the top is sooty iron with
    the collar's shadow."""
    if ctx.chart == "+z":
        c = T.g_iron(ctx, seed, {"rust": 0.15})
        r = math.hypot(ctx.pos[0], ctx.pos[1])
        return T.mix(c, T.hexc("140C08"), T.smoothstep(0.15, 0.13, r) * 0.65)
    e = T.edge_dist(ctx)
    if e < FRAME:
        c = T.g_hammered_iron(ctx, seed, {"rust": 0.12, "dent": 0.05})
        return T.frame_rivets(ctx, T.scale(c, 1.1), FRAME * 0.5, 0.08, 0.0125, T.IRON_RIVET_HI, T.IRON_RIVET_LO)
    if ctx.chart in ("+y", "-y"):
        c = T.g_lacquer(ctx, seed + 7, {"color": RED, "worn": 0.5})
    elif ctx.chart == "+x":
        c = T.g_hammered_iron(ctx, seed + 3, {"rust": 0.08, "dent": 0.045})
    else:
        c = T.g_iron(ctx, seed + 3, {"rust": 0.25})
    if e < FRAME + 0.009:
        c = T.mix(c, T.hexc("120806"), 0.6)
    return c


def p_buttons(ctx, seed, p):
    """Big red mushroom buttons: glossy red lacquer domes with a hot highlight up to the left, in dark iron
    bezels."""
    x, y, z = ctx.pos
    (cx, cy, cz), axis, up, right = BUTTONS[0 if y < 0 else 1]
    q = (x - cx, y - cy, z - cz)
    h = G.dot(q, axis)
    if h < 0.012:
        return T.g_iron(ctx, seed, {"rust": 0.1})
    c = T.g_lacquer(ctx, seed + 1, {"color": T.hexc("D23A26"), "worn": 0.0, "gloss": 0.5})
    u, v = G.dot(q, right), G.dot(q, up)
    k = math.hypot(u + 0.012, v - 0.014)
    c = T.mix(c, T.hexc("FFD8C8"), T.smoothstep(0.016, 0.004, k) * 0.85)
    return c


def p_gauge(ctx, seed, p):
    """A brass gauge case; its cap is the cream dial (the decal paints the face over it)."""
    if ctx.chart.endswith("_top"):
        return T.hexc("F0E8D0")
    return T.g_brass(ctx, seed, {"streak": True, "patina": 0.3})


def p_exhaust(ctx, seed, p):
    """Rusty iron with a bold red lacquer band (dark lips a texel or two wide), sooty toward the mouth."""
    z = ctx.pos[2]
    if 0.383 < z < 0.433:
        c = T.g_lacquer(ctx, seed + 1, {"color": RED, "worn": 0.4})
        if z < 0.395 or z > 0.421:
            c = T.scale(c, 0.55)
        return c
    c = T.scale(T.g_iron(ctx, seed, {"rust": 0.35, "hotspot": 0.5}), 1.15)
    return T.mix(c, T.hexc("1A1612"), T.smoothstep(0.44, 0.53, z) * 0.7)


def p_mouth(ctx, seed, p):
    """The exhaust's flared mouth: a goblin's bright brass trumpet, soot-black inside (the inner wall and the
    plug at its throat) and smudged round the lip."""
    q = G.sub(ctx.pos, MOUTH_AT)
    h = G.dot(q, MOUTH_AXIS)
    radial = G.sub(q, G.mul(MOUTH_AXIS, h))
    r = G.length(radial)
    if G.dot(ctx.n, radial) < 0.0 or (G.dot(ctx.n, MOUTH_AXIS) > 0.9 and r < 0.031):
        v = T.fbm3(ctx.pos[0] * 40.0, ctx.pos[1] * 40.0, ctx.pos[2] * 40.0, seed + 3, 2)
        return T.mix(T.hexc("16120E"), T.hexc("3A2A1C"), v * 0.6)
    c = T.g_brass(ctx, seed, {"streak": True, "patina": 0.3, "hotspot": 0.6})
    return T.mix(c, T.hexc("16120E"), T.smoothstep(0.024, 0.036, h) * 0.5)


def p_collar(ctx, seed, p):
    """The iron collar: hammered, eight big rivets round its waist, two between each pair of spikes."""
    c = T.g_hammered_iron(ctx, seed, {"rust": 0.15, "dent": 0.04})
    a = math.atan2(ctx.pos[1], ctx.pos[0]) - math.pi / 8
    step = 2 * math.pi / 8
    d_arc = abs(((a + step / 2) % step) - step / 2) * 0.134
    dz = ctx.pos[2] - (BASE_Z1 + 0.018)
    return T.rivet_dot(c, d_arc, -dz, 0.017, T.IRON_RIVET_HI, T.IRON_RIVET_LO)


def p_spikes(ctx, seed, p):
    """Iron spikes, lit along their upper sides."""
    c = T.g_iron(ctx, seed, {"rust": 0.1, "hotspot": 0.9})
    return T.mix(c, T.hexc("B8BCC4"), T.clamp01(ctx.n[2]) * 0.3)


def _splats(a, b, cell, seed, keep, b0, b1, r0, r1, soft, n=1, wrap=0, skip=None):
    """Soft, slightly oval splats of shake on a surface with coordinates (a, b) in yd: per `cell` along a, n
    candidates at a random a in the cell and a random b between b0 and b1, each kept with probability `keep`,
    radius r0 at b0 shrinking to r1 at b1 (+-20 %, up to 12 % out of round). wrap: the number of cells round a
    closed surface; skip(a, b) drops a candidate. Returns the coverage 0-1. The edge fades over `soft` yd (a
    texel or more): a splat a few texels across with a hard or lobed edge reads as a pixel cross or a heart."""
    ia = math.floor(a / cell)
    cov = 0.0
    for ci in (ia - 1, ia, ia + 1):
        key = ci % wrap if wrap else ci
        for j in range(n):
            h = [T.noise3(key, j, k, seed) for k in range(5)]       # (a lattice point of noise3 is its hash)
            if h[0] > keep:
                continue
            ca = (ci + h[1]) * cell
            cb = b0 + (b1 - b0) * h[2]
            if skip and skip(ca, cb):
                continue
            r = (r0 + (r1 - r0) * h[2]) * (0.8 + 0.4 * h[3])
            d = math.hypot(a - ca, b - cb)
            if d > r * 1.25 + soft:
                continue
            rr = r * (1.0 + 0.12 * math.sin(2.0 * math.atan2(b - cb, a - ca) + 6.3 * h[4]))   # a little oval
            cov = max(cov, T.smoothstep(rr + soft * 0.5, rr - soft * 0.5, d))
    return cov


JAR_SPLAT_N = 14                    # splat cells round the jar
JAR_SPLAT_R = 2 * math.pi * 0.1146 / JAR_SPLAT_N


def p_jar(ctx, seed, p):
    """Clear glass with BlenderSW's near-neutral tint, g_glass's streaks and darker rims and a bright band under
    the lid (the jar's rim); pink shake splattered up the inside
    over the surface by the spinning saw: soft round splats 0.03-0.05 across behind and beside the blade (the
    glass packs at about 115 texels/yd, and a splat under 5 texels across breaks up into a pixel cross), and in
    front of it only low bumps of pink at the waterline, clear of the hub."""
    c = T.g_glass(ctx, seed, {"tint": T.hexc("EEF4F2"), "alpha": 0.28})
    x, y, z = ctx.pos
    if JAR[-2][1] - 0.022 < z < JAR[-2][1] - 0.004:
        return (0.97, 0.99, 1.0, 0.72)                  # the bright rim under the lid
    dz = z - SHAKE_TOP
    if not -0.02 < dz < 0.1:
        return c
    arc = math.atan2(y, x) * JAR_SPLAT_R / (2 * math.pi / JAR_SPLAT_N)    # arc length round the jar

    def off_saw(ca):                # the candidate's angle from the blade's facing
        a = ca / JAR_SPLAT_R * (2 * math.pi / JAR_SPLAT_N) - SAW_FACING
        return abs((a + math.pi) % (2 * math.pi) - math.pi)

    # in front (within 0.9 rad of the facing, but not over the hub): splats sunk in the shake, so only their caps
    # rise above the waterline (1.3 cm at most); behind and beside: splats up the glass to 0.06
    cov = max(_splats(arc, dz, JAR_SPLAT_R, seed + 5, 0.7, -0.02, -0.014, 0.016, 0.016, 0.009, 1, JAR_SPLAT_N,
                      lambda ca, cb: not 0.45 < off_saw(ca) < 0.9),
              _splats(arc, dz, JAR_SPLAT_R, seed + 6, 0.5, 0.0, 0.06, 0.025, 0.015, 0.009, 2, JAR_SPLAT_N,
                      lambda ca, cb: off_saw(ca) < 0.9))
    if cov <= 0.0:
        return c
    s = T.mix(SHAKE_C, T.scale(SHAKE_C, 0.82), cov * 0.5)
    k = cov * 0.95
    return (c[0] + (s[0] - c[0]) * k, c[1] + (s[1] - c[1]) * k, c[2] + (s[2] - c[2]) * k, c[3] + (0.93 - c[3]) * k)


def p_hoop(ctx, seed, p):
    """The iron hoop round the jar: a lit upper lip, a dark lower one (too thin for rivets that hold at mip 1)."""
    c = T.g_iron(ctx, seed, {"rust": 0.2})
    z = ctx.pos[2]
    if z > HOOP_Z + 0.006:
        c = T.mix(c, T.hexc("A4A8B0"), 0.3)
    elif z < HOOP_Z - 0.008:
        c = T.mix(c, T.hexc("101014"), 0.4)
    return c


def p_shake(ctx, seed, p):
    """A pink shake churned to a froth at the top."""
    return T.g_shake(ctx, seed, {"color": SHAKE_C, "top": SHAKE_TOP, "froth_d": 0.035})


STEEL = dict(light_c=T.hexc("D4DAE2"), base=T.hexc("6E747E"), dark=T.hexc("24282E"), bounce=T.hexc("5A5650"),
             patina=T.hexc("6A4A30"))


def _saw_paint(ctx, seed, r, u, v):
    """The saw blade's metal at distance r from its centre, (u, v) across its face (v up)."""
    if r < 0.036:
        # the dark iron hub with a ring of six bright bolts on a 0.022 circle, a flange (no single dark centre, so
        # never a pupil; four bolts, with the lower ones at the waterline, read as a little face)
        c = T.g_iron(ctx, seed + 1, {"rust": 0.05, "hotspot": 0.4})
        a = math.atan2(v, u) - math.pi / 2
        a = math.pi / 2 + round(a / (math.pi / 3)) * (math.pi / 3)
        return T.rivet_dot(c, u - 0.022 * math.cos(a), 0.022 * math.sin(a) - v, 0.0075, T.IRON_RIVET_HI,
                           T.IRON_RIVET_LO)
    c = T.metal(ctx, seed, {"streak": False, "hotspot": 0.3}, STEEL["light_c"], STEEL["base"], STEEL["dark"],
                STEEL["bounce"], STEEL["patina"], 0.1)
    if r > SAW_R - 0.012:
        return T.mix(c, T.hexc("F4F8FC"), 0.8)       # the filed points
    if r > SAW_R_IN - 0.004:
        return T.scale(c, 0.45)                      # the dark teeth
    if 0.051 < r < 0.061:
        return T.mix(c, T.hexc("E8ECF0"), 0.6)       # a bright ring inside the gullets
    if 0.039 < r < 0.051:
        return T.g_lacquer(ctx, seed + 2, {"color": RED, "worn": 0.2})   # a red lacquer ring inside it
    return T.scale(c, 0.8)


def p_saw(ctx, seed, p):
    """The saw blade: dark steel teeth with only their points filed bright (the toothed outline reads against the
    pale far wall of the glass behind it), a bright steel ring inside the gullets with a red lacquer ring inside
    that, a dark iron hub with a ring of six bright bolts; soft pink splats of shake cling to the blade just above
    the froth, off the hub."""
    q = G.sub(ctx.pos, SAW_C)
    r = G.length(q)
    u, v = G.dot(q, SAW_RIGHT), q[2]
    c = _saw_paint(ctx, seed, r, u, v)
    cov = _splats(u, ctx.pos[2] - SHAKE_TOP, 0.035, seed + 9, 0.75, -0.003, 0.02, 0.014, 0.01, 0.005,
                  skip=lambda ca, cb: math.hypot(ca, cb + SHAKE_TOP - SAW_C[2]) < 0.05)
    return T.mix(c, T.mix(SHAKE_C, T.hexc("FFF0F4"), 0.25), cov)


def p_lid(ctx, seed, p):
    """An iron rim band with eight big rivets under a red lacquer cap; an iron boss for the spike."""
    z = ctx.pos[2]
    r = math.hypot(ctx.pos[0], ctx.pos[1])
    if z < LID_Z0 + LID_BAND + 0.001:
        c = T.g_iron(ctx, seed, {"rust": 0.15})
        a = math.atan2(ctx.pos[1], ctx.pos[0])
        step = 2 * math.pi / 8
        d_arc = abs(((a + step / 2) % step) - step / 2) * 0.142
        return T.rivet_dot(c, d_arc, -(z - LID_Z0 - LID_BAND / 2), 0.016, T.IRON_RIVET_HI, T.IRON_RIVET_LO)
    if r < 0.05:
        return T.g_iron(ctx, seed + 2, {"rust": 0.1})
    return T.g_lacquer(ctx, seed + 1, {"color": DARK_RED, "worn": 0.5})


def p_straps(ctx, seed, p):
    """Iron clamp bands round the tusk: a lit top, a bold rivet on each side face."""
    c = T.g_iron(ctx, seed, {"rust": 0.2})
    if ctx.chart == "+z":
        return T.mix(c, T.hexc("A4A8B0"), 0.3)
    if ctx.chart in ("+x", "-x"):
        return T.rivet_dot(c, ctx.s - ctx.cw / 2, ctx.t - ctx.ch / 2, 0.012, T.IRON_RIVET_HI, T.IRON_RIVET_LO)
    return c


def p_tusk(ctx, seed, p):
    return T.g_bone(ctx, seed, {"kind": "ivory", "root": 0, "cracks": 2})


# ---------------------------------------------------------------------------------------------- decals

def d_front(w, h):
    """The base front: the tusk crest in bone relief over the buttons."""
    img = T.Img(w, h, (0, 0, 0, 0))
    ppy = w / BASE_W
    s = int(CREST_S * ppy)
    if s < 6:
        return img
    rel = E.render_relief("tusk_crest", s, s, P2.BONE_RELIEF)
    P2.composite(img, rel, (w - s) // 2, int((BASE_Z1 - CREST_Z) * ppy - s / 2))
    return img


def d_gauge(w, h):
    return P2.gauge_face(w, h, {"needle_deg": 105.0})


# ------------------------------------------------------------------------------------------------ parts

def _saw_outline(teeth, r_out, r_in):
    """A circular saw blade: each tooth a ramp from the gullet up to its point, then a straight drop (CCW)."""
    pts = []
    step = 2 * math.pi / teeth
    for i in range(teeth):
        a = step * i
        pts.append((math.cos(a) * r_in, math.sin(a) * r_in))
        b = a + step * 0.78
        pts.append((math.cos(b) * r_out, math.sin(b) * r_out))
    return pts


def _spike(base, direction, r, h, sides):
    """geom.spike without its base cap (it sits in the collar or the lid, where nobody sees it)."""
    m = G.cone(r, 0.0, h, sides, caps=False)
    return G.transform(m, G.mat_chain(G.mat_translate(*base), G.mat_look(direction)))


def _jar_r(z):
    """The glass wall's radius at height z."""
    for (r0, z0), (r1, z1) in zip(JAR, JAR[1:]):
        if z0 <= z <= z1:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return JAR[-1][0]


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (0.4, 0.4, 0.75)
    d.budget = 900
    d.kind = "machine"
    d.atlas = {"atlas": 256}
    d.max_height = 0.95
    d.sloped_top = True
    add = d.add

    # the crooked plank board: geom.planks' boards without their hidden bottoms, standing 3 mm up so the wobble
    # keeps them above the floor
    boards = []
    bw = (0.4 - 0.012 * 2) / 3
    for i in range(3):
        b = G.box(0.4, bw, BOARD_H - 0.003, faces="+x -x +y -y +z", z0=0.003)
        b = G.plank_edges(G.translate(b, -0.2 + bw / 2 + i * (bw + 0.012), 0.0, 0.0), 5 + 7 * i, 0.02, "y",
                          inward=True)
        boards.append(G.wobble(b, 0.003, 5 + 13 * i))
    add(B.Part("board", G.merge(boards), paint=p_board, seed=11, weight=0.5))

    # the motor base: tapered, a little crooked, a riveted iron frame round its panels; the crest on the front
    base = G.box(BASE_W, BASE_W, BASE_Z1 - BASE_Z0 + SINK, 0.03, faces="+x -x +y -y +z", z0=BASE_Z0 - SINK)
    base = G.wobble(G.taper(base, TAPER, BASE_Z0, BASE_Z1), 0.004, 7)
    for ch in base.charts:
        ch.weight = {"+x": 1.5, "-x": 0.45, "+z": 0.35}.get(ch.name, 0.9)
    add(B.Part("base", base, paint=p_base, seed=21, decals={"+x": d_front}))

    # two big red mushroom buttons under the crest, square to the front's lean
    bprof = [(BUTTON_R, 0.0), (BUTTON_R * 0.92, 0.02), (BUTTON_R * 0.6, 0.04), (0.0, 0.046)]
    buttons = []
    for (c, axis, _up, _right) in BUTTONS:
        m = G.mat_chain(G.mat_translate(c[0] - 0.006, c[1], c[2]), G.mat_disc_facing(axis))
        buttons.append(G.transform(G.lathe(bprof, 8), m))
    add(B.Part("buttons", G.merge(buttons), paint=p_buttons, seed=31, weight=1.6, ao_floor=0.7))

    # a goblin gauge on the right-hand side panel, cocked toward the barista
    gm = G.mat_chain(G.mat_translate(*GAUGE_AT), G.mat_disc_facing(GAUGE_FACING))
    gauge = G.transform(G.cylinder(GAUGE_R, 0.03, 10, (False, True)), gm)
    add(B.Part("gauge", gauge, paint=p_gauge, seed=33, decals={"cyl_top": d_gauge}, weight=2.2, ao_floor=0.7))

    # the exhaust out of the left-hand side panel: an elbow, a pipe curving up and back, a flared brass trumpet
    # with an inner wall down to a plug at its throat, so nobody looks through it from above or behind
    pipe = G.sweep(EXHAUST_PATH, EXHAUST_R, 6)
    at_mouth = G.mat_chain(G.mat_translate(*MOUTH_AT), G.mat_look(MOUTH_AXIS))
    # (the foot's 8-gon flats, 0.035 out, cover the pipe's 6-gon corners)
    mouth = G.transform(G.lathe([(0.038, -0.012), (0.054, 0.030), (0.047, 0.037), (0.04, 0.022), (0.03, 0.006)], 8,
                                cap_top=True), at_mouth)
    add(B.Part("exhaust", pipe, paint=p_exhaust, seed=35, weight=0.9))
    add(B.Part("exhaust_mouth", mouth, paint=p_mouth, seed=37, weight=0.9, ao_floor=0.6))

    # the iron collar the jar stands in, with four spikes on the diagonals, and the lid's spike
    collar = G.lathe([(0.132, BASE_Z1 - 0.006), (0.134, BASE_Z1 + 0.036), (0.11, COLLAR_Z1)], 10)
    add(B.Part("collar", collar, paint=p_collar, seed=41, weight=0.9))
    spikes = []
    for k in range(4):
        # (the base sits deep in the collar wall, so its open ring never shows above the shoulder)
        a = math.pi / 4 + k * math.pi / 2
        out = (math.cos(a), math.sin(a), -0.12)
        spikes.append(_spike((math.cos(a) * 0.12, math.sin(a) * 0.12, BASE_Z1 + 0.01), out, 0.03, 0.085, 5))
    spikes.append(_spike((0.0, 0.0, LID_TOP - 0.004), (0.0, 0.0, 1.0), 0.034, 0.07, 6))
    add(B.Part("spikes", G.merge(spikes), paint=p_spikes, seed=43, weight=0.7))

    # the glass jar, its iron hoop, the shake and the saw blade standing up out of it
    # (one shell drawn on both sides, section 5.2.5's glass1: the far wall shows behind the saw)
    add(B.Part("jar", G.lathe(JAR, 12), "glass1", paint=p_jar, seed=51, weight=0.8, ao_floor=1.0))
    hr = _jar_r(HOOP_Z)
    hoop = G.lathe([(hr - 0.002, HOOP_Z - 0.017), (hr + 0.013, HOOP_Z), (hr - 0.002, HOOP_Z + 0.017)], 12)
    add(B.Part("hoop", hoop, paint=p_hoop, seed=53, weight=0.7))
    # the shake fills the jar like a liquid: the jar's 12 sides lined up with its own, 4 mm inside the glass, a
    # 2 mm froth crown on top; its foot stands hidden in the collar (smooth up to 60 degrees, so the wall takes
    # the crown's up-tilted normals and catches the sun)
    shake = G.lathe([(_jar_r(0.32) - 0.004, 0.32), (_jar_r(SHAKE_TOP - 0.01) - 0.004, SHAKE_TOP - 0.01),
                     (_jar_r(SHAKE_TOP) - 0.0065, SHAKE_TOP)], 12, cap_top=True, angle=60.0)
    add(B.Part("shake", shake, paint=p_shake, seed=55, weight=1.0, ao_floor=0.9))
    saw = G.extrude(_saw_outline(SAW_TEETH, SAW_R, SAW_R_IN), 0.012)
    facing = (math.cos(SAW_FACING), math.sin(SAW_FACING), 0.0)
    saw = G.transform(saw, G.mat_chain(G.mat_translate(*SAW_C), G.mat_extrude_facing(facing),
                                       G.mat_translate(0.0, 0.0, -0.006)))
    add(B.Part("saw", saw, paint=p_saw, seed=57, weight=1.4, ao_floor=0.6))

    # the lid: a riveted iron rim band under a red lacquer cap
    lid = G.lathe([(0.142, LID_Z0), (0.142, LID_Z0 + LID_BAND), (0.112, LID_Z0 + LID_BAND + 0.012), (0.045, LID_TOP)],
                  10, cap_bottom=True, cap_top=True)
    # (texels go to the band's rivets rather than to the underside, which only shows through the glass)
    for ch in lid.charts:
        ch.weight = 0.4 if ch.name.endswith("_bottom") else 1.0
    add(B.Part("lid", lid, paint=p_lid, seed=61))

    # the handle on the right-hand side (+Y): a curved ivory tusk held to the glass by two iron clamp bands
    # (closed at the glass end, which shows through it); the top one hangs from the lid band, a lug of the lid
    root, tip = TUSK
    tusk = G.horn(root, tip, (0.0, 1.0, 0.0), 0.4, 0.03, 0.016, steps=6, sides=6, cap=False)
    add(B.Part("tusk", tusk, paint=p_tusk, seed=71, weight=1.1))
    straps = []
    for k, (x, y, z) in enumerate(TUSK):
        r_wall = _jar_r(z) - 0.006
        L = y + 0.024 - r_wall
        z0 = z - 0.0225 if k == 0 else LID_Z0 - 0.045
        straps.append(G.translate(G.box(L, 0.06, 0.045, faces="+x -x +y -y +z -z"), x, r_wall + L / 2, z0))
    # (weighted up so their painted rivets get enough texels to read)
    add(B.Part("straps", G.merge(straps), paint=p_straps, seed=73, weight=1.4))

    # collision: walls to 0.5, a gable roof to 0.75 (roof n.z 0.62 < 0.6428: too steep to stand on)
    d.collision = G.hull_gable(0.4, 0.4, 0.5, 0.75)
    d.particles = []
    return d
