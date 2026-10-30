"""19307 KettleStoveOrg, the Spirit-Fire Kettle (Orgrimmar tea station), CAFE.SPEC.md section 5.8.1.

A gunmetal cast-iron kettle on a squat iron tripod over a stone hearth, with flames licking up round the kettle's
belly, a glowing fire mouth and embers drifting up, shaped so it reads as "the kettle on the fire" at a glance from
the front three-quarter view: the squat kettle shows its whole profile (a gooseneck spout to the right, -Y, and an
iron bail handle with a bone grip arching over the lid, in the same plane), steam puffs from the spout, and the
fire is bright in two places (the tongues round the kettle and the mouth). Orgrimmar and hand-made, in the family
of the Tusk-o-Matic: a hearth of crooked grey-brown stones with rough capstones on its corners, a red lacquer iron
lintel riveted over an arched fire mouth with the tusk crest in bone on it, a boar's pair of ivory tusks rising from the
jamb corners to frame the mouth, a goblin heat gauge on the hearth's side, a squat tripod (an iron ring under the
kettle, three thick legs of forged bar down to cast clawed feet, the front ones with a hard elbow under an iron
collar, red lacquer bands under painted iron collars), and a hammered-iron kettle with a riveted red band and an
iron spike for a lid knob. 0.85 (Y) x 0.65 (X) x 1.0 yd, front
(+X) toward the barista.

What makes a player name it at 4-15 yd (front three-quarter view), and how big each cue is:
- the kettle: a squat gunmetal body 0.45 across and 0.25 tall on the tripod (0.49-0.74), its spout 0.25 long
  (0.09-0.05 thick), its bail handle 0.3 wide rising 0.26 over the shoulder with a bone grip 0.07 thick, a red
  band 0.055 tall round the belly; steam from the spout tip;
- the fire: flame tongues rising from the coal bed under the kettle (0.36-0.69), the outer ones licking up past
  its belly, and the arched fire mouth (0.34 x 0.32, its top corners rounded off in soot) glowing orange from
  the coals up, all of it under the lintel; embers rising in front of the
  mouth (the embers emitter); both glow at night;
- the hearth: 0.58 x 0.49 x 0.38 of big grey-brown stones (0.17 x 0.12 slabs; the dark iron and red family,
  not orange brick), four capstones (0.13 across at the back, 0.11 at the front) on its corners, the mouth
  framed by two jamb stones and the lintel over it (0.58 x 0.13, its crest 0.12 tall);
- the stand: an iron ring (0.06 thick) under the kettle and three legs 0.09-0.08 thick that never rise above it:
  the front ones a shoulder sloping down outward to a hard elbow under an iron collar (0.12 across), then
  straight down to cast feet (knuckles 0.11, three talons 0.06 long on the front feet), so they read as a forged
  frame, not as arms;
- Orgrimmar: the red lacquer lintel with rivets and the bone crest, the ivory tusks (0.09 thick at the root,
  0.45 tall), the red leg bands, the riveted red kettle band, the spiked lid knob (0.06 x 0.09), the goblin
  gauge (0.15 across) on the back half of the hearth's left side, turned toward the front three-quarter view so
  it shows past the front leg.

Deviations from the section 5.8.1 design, for the cues and the section 5.8 size (0.85 x 0.65 x 1.0):
- the tripod stands on the floor round the hearth (not on it): its front legs come down beside the mouth and its
  back leg behind the hearth, and its top is a ring under the kettle's belly, not a trivet plate;
- the fire box is a stone hearth with a front mouth and a coal bed on top (not an open pit), so the fire shows
  from the front; the flames above it are two crossed glow cards (unlit, additive, painted so their edges add
  nothing; the wide one's outer tongues lick up past the kettle's belly), and the mouth is a glow panel whose
  bottom rows are the coals;
- the lintel is a riveted iron plate in red lacquer over the mouth (0.33-0.46), rising 0.08 over the hearth so the
  crest is 0.12 tall (the Tusk-o-Matic's red panel and bone crest) and the whole fire mouth shows under it; added
  for Orgrimmar: the tusks, the capstones, the gauge, the spiked lid knob, the red bands;
- the back foot's talons rake sideways (a back-pointing claw would leave the 0.65 depth);
- textures: the atlas and Steam, no Fire: the embers use the Steam puff, because the Fire sprite's opaque bright
  base would read as a hard-edged square at 0.07 yd; they peak bigger than the section 5.2.7 preset (scale 0.035
  mid-rise, not 0.02: the client draws a quad of +-scale, so 0.07 yd sparks meet the 0.06 readability rule; 0.02
  gives 0.04), and they fade in from alpha 0 (the preset is brightest at birth), so no glowing ball hangs at the
  spawn line;
- the kettle's spout points right (-Y) and its bail handle arches in the spout's plane, so the front views see
  the kettle's profile.
"""

import math

from .. import build as B
from .. import emblem as E
from .. import emitters as EM
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T

NAME = "KettleStoveOrg"
DISPLAY = 19307

LACQUER = T.hexc("B5402F")
LACQUER_DK = T.hexc("9C2A1F")
STONE = T.hexc("8C8073")              # grey-brown stone (orange clay read as brick)
CAST = dict(light_c=T.hexc("767A84"), base=T.hexc("2A2B31"), dark=T.hexc("0C0C10"), bounce=T.hexc("3A2E26"),
            patina=T.hexc("5A3422"))     # black cast iron: darker than tex's iron
MORTAR = T.hexc("3E3630")
SOOT = T.hexc("14110E")
HI, LO = T.IRON_RIVET_HI, T.IRON_RIVET_LO

BOX_X0, BOX_X1 = -0.235, 0.09         # the hearth body (its front face is the back of the mouth)
BOX_W, BOX_H = 0.58, 0.38
JAMB_X0, JAMB_X1 = 0.08, 0.23         # the jamb stones in front of it
MOUTH_W2, MOUTH_H = 0.17, 0.32        # the fire mouth: half width, height (an arch: its top corners in soot)
LINTEL_X1 = 0.25                      # the lintel plate's front
PLATE_D = 0.035                       # the plate's thickness (a beam behind it carries the hearth top)
LINTEL_Z0, LINTEL_Z1 = 0.33, 0.46     # the plate, over the mouth: it rises 0.08 over the hearth (crest 0.12 tall)
KX, KY = -0.04, 0.0                   # the kettle's axis
KZ = 0.49                             # the kettle's base
KS = 1.1                              # the kettle's scale (its profile is drawn at 1.0)
RING_Z, RING_R, RING_T = 0.525, 0.22, 0.03    # the tripod's ring: height, radius, tube radius
LEGS = (                              # (foot (x, y), elbow (x, y, z) or None, talon directions (degrees, 0 = +X))
    ((0.13, 0.38), (0.105, 0.335, 0.455), (-30.0, 0.0, 30.0)),
    ((0.13, -0.38), (0.105, -0.335, 0.455), (-30.0, 0.0, 30.0)),
    ((-0.285, 0.0), None, (100.0, 260.0)),   # the back leg drops; its talons rake sideways, inside the depth
)
KNUCKLE_R, KNUCKLE_Z = 0.055, 0.05
FLAME_Z0, FLAME_Z1 = 0.36, 0.72
GAUGE = ((-0.16, BOX_W / 2 - 0.004, 0.235), (0.45, 0.85, 0.27), 0.075)   # case back centre, facing, radius


# ----------------------------------------------------------------------------------------------- paints

def p_stone(ctx, seed, p):
    """Big grey-brown stones (each slab its own tone) with dark mortar joints, soot only round the mouth and a
    little along the hearth's top edge, and the bed of coals on the box's top face inside a rim of stone."""
    x, y, z = ctx.pos
    if ctx.part == "fire_box" and ctx.chart == "+z":
        e = T.edge_dist(ctx)
        if e > 0.06:
            c = T.g_embers(ctx, seed + 7, {"size": 0.045})
            return T.mix(c, T.hexc("FF9A40"), T.smoothstep(0.1, 0.2, e) * 0.25)
    c = T.g_slabs(ctx, seed, {"color": STONE, "mortar": MORTAR, "slab": (0.17, 0.12), "joint": 0.02,
                              "cracks": 0.3})
    c = T.scale(c, 1.25)                         # lifted: the hearth sits low, where the bake is darkest
    # soot: within 0.05 of the mouth (the jambs' inner faces and front edges), and a band along the top edge
    k = 0.0
    if x > BOX_X1 - 0.02 and abs(y) < MOUTH_W2 + 0.05:
        k = T.smoothstep(MOUTH_W2 + 0.05, MOUTH_W2 - 0.01, abs(y)) * 0.9
    if ctx.part == "fire_box" and ctx.chart == "+x":
        k = 1.0
    k = max(k, T.smoothstep(BOX_H - 0.05, BOX_H, z) * 0.12)
    v = T.fbm3(x * 9.0, y * 9.0, z * 9.0, seed + 3, 3)
    return T.mix(c, SOOT, T.clamp01(k * (0.6 + 0.5 * v)))


def _fire(u, y, seed, tongues=3.0):
    """Flame intensity k (0..1) and colour at u across and y up (0 at the bed) of a fire chart (tex.g_fire_glow's
    tongues over a coal bed)."""
    tong = 0.5 + 0.5 * math.sin(u * 2.0 * math.pi * tongues + T.fbm(u * 3.0, y * 2.0, seed, 2) * 3.0)
    height = 0.42 + 0.5 * tong * (0.6 + 0.4 * T.fbm(u * 5.0, 0.3, seed + 1, 2))
    k = T.clamp01(1.0 - y / height)
    k *= 0.75 + 0.55 * T.fbm(u * 6.0, y * 4.0, seed + 2, 2)
    coal = T.smoothstep(0.24, 0.0, y) * (0.65 + 0.35 * T.noise(u * 14.0, y * 6.0, seed + 3))
    k = T.clamp01(max(k, coal))
    c = T.ramp([(0.0, T.hexc("4A0A02")), (0.3, T.hexc("B02A06")), (0.55, T.hexc("FF6A10")),
                (0.8, T.hexc("FFB040")), (1.0, T.hexc("FFF0B0"))], k)
    return k, c


# The flame tongues: (centre across the card, half width at the widest, height), as fractions of the card, each
# ending inside the card so no flame is cut off by its edge. The wide card faces the front: its outer tongues rise
# beside the kettle and lick up its belly, the inner ones show under it. The narrow card runs front to back, for
# the side views.
TONGUES_WIDE = ((0.11, 0.08, 0.9), (0.2, 0.1, 0.6), (0.34, 0.1, 0.42), (0.5, 0.11, 0.4), (0.66, 0.1, 0.42),
                (0.8, 0.1, 0.62), (0.89, 0.08, 0.85))   # every tongue ends 0.03 inside the card
TONGUES_NARROW = ((0.12, 0.1, 0.75), (0.36, 0.12, 0.45), (0.62, 0.12, 0.42), (0.87, 0.1, 0.7))


def p_flames(ctx, seed, p):
    """The flame cards over the coal bed (glow: unlit, additive): separate teardrop tongues of flame (swelling
    above the bed, narrowing to a wavering tip), yellow-white at the core, orange, then deep red at the edge,
    with black between them and above, so the cards' outlines add nothing."""
    u, y = ctx.u, T.clamp01(1.0 - ctx.v)
    tongues = TONGUES_WIDE if abs(ctx.n[0]) > 0.7 else TONGUES_NARROW
    best = 0.0
    for k, (uc, w, h) in enumerate(tongues):
        if y >= h:
            continue
        q = y / h
        sway = (T.noise(y * 4.0, k * 1.7, seed) - 0.5) * 0.08 * q
        half = w * (math.sqrt(q / 0.22) if q < 0.22 else ((1.0 - q) / 0.78) ** 0.8)
        d = abs(u - uc - sway)
        if d < half:
            best = max(best, (1.0 - d / half) ** 0.6 * (1.0 - q * 0.5))
    k = T.clamp01(max(best, T.smoothstep(0.07, 0.0, y) * 0.8))
    # the card fades to black toward its sides and top, so no texel near its edge adds light (the coal line
    # along the bottom showed as hard-edged bars at the card's ends)
    k *= T.smoothstep(0.0, 0.14, u) * T.smoothstep(1.0, 0.86, u) * T.smoothstep(1.0, 0.9, y)
    if k <= 0.0:
        return (0.0, 0.0, 0.0)
    c = T.ramp([(0.0, T.hexc("5A0C02")), (0.3, T.hexc("C8320A")), (0.6, T.hexc("FF7A18")), (0.85, T.hexc("FFC050")),
                (1.0, T.hexc("FFF4C0"))], k)
    return T.scale(c, T.smoothstep(0.0, 0.3, k))


def p_mouth(ctx, seed, p):
    """The glow at the back of the fire mouth: the whole mouth glows deep orange, brighter tongues rise from
    the coals along its bottom, and it darkens into soot toward the lintel. The coals stop at FFB040 and the
    bottom rows fade to an ember red, so the floor of the mouth is not a pale line."""
    u, y = ctx.u, 1.0 - ctx.v
    # the arch: above 0.68 of the height the opening narrows to a round top; outside it, black (the soot
    # backing shows through the additive panel)
    if y > 0.68:
        q = ((u - 0.5) / 0.5) ** 2 + ((y - 0.68) / 0.32) ** 2
        if q >= 1.0:
            return (0.0, 0.0, 0.0)
        arch = T.smoothstep(1.0, 0.8, q)
    else:
        arch = 1.0
    k, c = _fire(u, y, seed, 2.5)
    k = 0.35 + 0.65 * k
    if y < 0.12:
        k = min(k, 0.8)
    c = T.ramp([(0.35, T.hexc("A02808")), (0.6, T.hexc("FF6A10")), (0.8, T.hexc("FFB040")),
                (1.0, T.hexc("FFF0B0"))], k)
    f = T.smoothstep(1.0, 0.7, y) * 0.6 + 0.4
    f *= 0.35 + 0.65 * T.smoothstep(0.0, 0.1, y)
    return T.scale(c, f * arch * T.smoothstep(0.0, 0.08, u) * T.smoothstep(1.0, 0.92, u))


def cast_iron(ctx, seed, rust=0.2, streak=0.45):
    return T.metal(ctx, seed, {"streak_k": streak, "patina": rust}, CAST["light_c"], CAST["base"], CAST["dark"],
                   CAST["bounce"], CAST["patina"], rust)


def p_iron(ctx, seed, p):
    return cast_iron(ctx, seed, 0.3)


def p_legs(ctx, seed, p):
    """Dark iron legs, each with a red lacquer band (0.05) on its upright under a dark iron collar with a lit
    upper lip (painted bands by height: the legs are upright there)."""
    c = cast_iron(ctx, seed, 0.35)
    z = ctx.pos[2]
    if 0.3 <= z < 0.35:
        c = T.g_lacquer(ctx, seed + 3, {"color": LACQUER, "worn": 0.4})
        return T.scale(c, 0.6) if z < 0.306 else c
    if 0.35 <= z < 0.378:
        c = T.scale(cast_iron(ctx, seed + 5, 0.1, 0.6), 0.75)
        return T.mix(c, T.hexc("B8BCC4"), 0.4) if z > 0.37 else c
    return c


def p_collar(ctx, seed, p):
    """The forged collars over the front legs' elbows: dark iron with a lit upper lip."""
    c = T.scale(cast_iron(ctx, seed, 0.1, 0.6), 0.75)
    return T.mix(c, T.hexc("B8BCC4"), T.smoothstep(0.3, 0.8, ctx.n[2]) * 0.35)


def p_claws(ctx, seed, p):
    """Cast iron feet: a knuckle with talons, lighter and worn toward the tips (they point down to the floor)."""
    c = cast_iron(ctx, seed, 0.2)
    return T.mix(c, T.hexc("B0B4BC"), T.smoothstep(0.035, 0.0, ctx.pos[2]) * 0.6)


def p_bone(ctx, seed, p):
    return T.g_bone(ctx, seed, {"kind": "ivory", "root": 0})


def p_grip(ctx, seed, p):
    return T.g_bone(ctx, seed, {"kind": "bone", "along": "t"})


def p_lintel(ctx, seed, p):
    """The lintel plate: iron in red lacquer, as the Tusk-o-Matic's apron: the front a lacquer field in a
    riveted dark iron border (0.03); its edges and underside dark iron, the underside over the mouth black with
    soot. The beam behind it (part "lintel_beam") is sooty iron with a row of rivets on its top."""
    e = T.edge_dist(ctx)
    if ctx.part == "lintel" and ctx.chart == "+x":
        if e < 0.03:
            c = T.g_iron(ctx, seed + 1, {"rust": 0.2})
            return T.frame_rivets(ctx, c, 0.015, 0.075, 0.011, HI, LO)
        c = T.g_lacquer(ctx, seed + 5, {"color": LACQUER, "gloss": 0.35})
        return T.scale(c, 0.5) if e < 0.038 else c
    c = T.g_iron(ctx, seed + 2, {"rust": 0.25, "streak": False})
    if ctx.chart == "+z" and ctx.part == "lintel_beam":
        c = T.rivet_lines(ctx, c, rows=(ctx.ch * 0.5,), step=0.075, r=0.011, hi=HI, lo=LO)
        return T.mix(c, SOOT, T.smoothstep(0.05, 0.0, ctx.t) * 0.6)
    if ctx.chart == "-z":
        return T.mix(c, SOOT, 0.75)
    return c


def p_gauge(ctx, seed, p):
    """The gauge's case and bezel: goblin brass, dull and patchy."""
    return T.g_brass(ctx, seed, {"patina": 0.35, "streak_k": 0.6})


def p_kettle(ctx, seed, p):
    """Hammered gunmetal cast iron (the lit dents read at 15 yd), sooty toward the bottom, with a red lacquer
    band round the belly (a dark lip over and under it) and painted rivets along the band."""
    c = T.scale(T.g_hammered_iron(ctx, seed, {"rust": 0.12, "dent": 0.045, "streak_k": 0.55}), 0.8)
    z = (ctx.pos[2] - KZ) / KS
    if ctx.part == "kettle":
        if 0.095 < z < 0.145 and abs(ctx.n[2]) < 0.6:
            c = T.g_lacquer(ctx, seed + 3, {"color": LACQUER_DK, "worn": 0.4})
            if z < 0.1 or z > 0.14:
                c = T.scale(c, 0.55)
            phi = math.atan2(ctx.pos[1] - KY, ctx.pos[0] - KX)
            step = 2 * math.pi / 14
            a0 = (math.floor(phi / step) + 0.5) * step
            c = T.rivet_dot(c, (phi - a0) * 0.205 * KS, (0.12 - z) * KS, 0.012, HI, LO)
        c = T.mix(c, SOOT, T.smoothstep(0.06, 0.0, z) * 0.75)
    return c


def p_lid(ctx, seed, p):
    return cast_iron(ctx, seed, 0.1, 0.6)


# ---------------------------------------------------------------------------------------------- decals

def d_crest(w, h):
    """The tusk crest in bone on the lintel's red lacquer front, 0.12 tall on the 0.13 plate (it overlaps the
    riveted border like a badge riveted over it)."""
    img = T.Img(w, h, (0, 0, 0, 0))
    s = int(h * 0.94)
    if s > 8:
        P2.composite(img, E.render_relief("tusk_crest", s, s, P2.BONE_RELIEF), (w - s) // 2, (h - s) // 2)
    return img


def d_gauge(w, h):
    """The goblin heat gauge: green, yellow and red bands, the needle well into the red."""
    return P2.gauge_face(w, h, {"needle_deg": 105.0})


# ------------------------------------------------------------------------------------------------ parts

def _stone(w, d, h, x, y, z0, seed, faces="+x -x +y -y +z", tilt=0.0, bevel=0.025, amp=0.008):
    """A big rough stone block: rounded edges, a little wobble, an optional lean about X."""
    m = G.box(w, d, h, bevel, faces=faces, z0=0.0)
    m = G.wobble(m, amp, seed, 5.0)
    if tilt:
        m = G.transform(m, G.mat_rot_x(tilt))
    return G.translate(m, x, y, z0)


def _card(w, h, z0, angle, dx=0.0):
    """A vertical quad (one chart "+x", both sides drawn by the glow preset) through the kettle's axis, or dx
    behind it."""
    q = G.box(w, 0.002, h, faces="+x", z0=z0)
    return G.transform(q, G.mat_chain(G.mat_translate(KX + dx, KY, 0.0), G.mat_rot_z(angle)))


def _kettle():
    """The squat cast-iron kettle around its axis, base at z 0: body, lid, spiked knob, spout (toward -Y), the
    handle's two ears, the bail handle arching in the YZ plane and its bone grip. Returns meshes, the spout's
    tip and its direction."""
    prof = [(0.12, 0.0), (0.172, 0.02), (0.2, 0.062), (0.205, 0.1), (0.192, 0.148), (0.158, 0.192),
            (0.114, 0.22), (0.104, 0.228)]
    body = G.lathe(prof, 16, name="kettle")
    lid = G.lathe([(0.112, 0.22), (0.114, 0.23), (0.09, 0.246), (0.0, 0.254)], 10, name="lid")
    knob = G.merge([G.cylinder(0.034, 0.02, 6, False, z0=0.246), G.spike((0.0, 0.0, 0.262), (0.0, 0.0, 1.0),
                                                                         0.03, 0.09, 6)])
    root = (0.0, -0.15, 0.06)
    tip = (0.0, -0.36, 0.228)
    path = G.bezier_path(root, (0.0, -0.255, 0.06), (0.0, -0.29, 0.17), tip, 6)
    spout = G.sweep(path, lambda t: 0.04 - 0.016 * t, 8, caps=(False, True), name="spout")
    hz, hr = 0.29, 0.135
    arc = G.arc_path((0.0, 0.0, hz), hr, math.pi, 0.0, 7, ("y", "z"))
    hpath = G.polyline_join([(0.0, -hr, 0.2)], arc, [(0.0, hr, 0.2)])
    handle = G.sweep(hpath, 0.016, 6, name="handle")
    ears = [G.translate(G.box(0.055, 0.045, 0.055, faces="+x -x +y -y +z", z0=0.17), 0.0, s * hr, 0.0)
            for s in (1, -1)]
    grip = G.transform(G.capsule(0.032, 0.16, 6, 2), G.mat_chain(G.mat_translate(0.0, -0.08, hz + hr),
                                                                 G.mat_rot_x(-math.pi / 2)))
    return {"body": body, "lid": lid, "knob": knob, "spout": spout, "handle": G.merge([handle] + ears),
            "grip": grip, "tip": tip, "dir": G.norm(G.sub(path[-1], path[-2]))}


def _leg(foot, elbow):
    """A tripod leg that never rises above the ring, forged from straight bar: from inside the ring (its end
    hidden in the ring and the kettle's belly) a shoulder sloping down outward to a hard elbow outside the
    hearth's corner, then straight down, splayed a little outward, into the foot's knuckle. The back leg's foot
    is under the ring, so it simply drops. Returns the leg and the elbow's position and bend axis (or None)."""
    fx, fy = foot
    a = math.atan2(fy - KY, fx - KX)
    r0 = RING_R - 0.02 if elbow else RING_R + 0.01
    p0 = (KX + math.cos(a) * r0, KY + math.sin(a) * r0, RING_Z)
    knuckle = (fx, fy, KNUCKLE_Z + 0.01)
    path = [p0, elbow, knuckle] if elbow else [p0, knuckle]
    leg = G.sweep(path, lambda t: 0.045 - 0.006 * t, 6, caps=(True, False))
    if not elbow:
        return leg, None
    axis = G.norm(G.add(G.norm(G.sub(elbow, p0)), G.norm(G.sub(knuckle, elbow))))
    return leg, (elbow, axis)


def _claw(foot, angles, length=0.06):
    """A cast iron foot: a squat knuckle and a talon along each of `angles` (degrees round Z), raking down to the
    floor."""
    fx, fy = foot
    knuckle = G.transform(G.sphere(KNUCKLE_R, 6, 3), G.mat_chain(G.mat_translate(fx, fy, KNUCKLE_Z),
                                                                G.mat_scale(1.0, 1.0, 0.85)))
    talons = []
    for deg in angles:
        a = math.radians(deg)
        dv = (math.cos(a) * 0.91, math.sin(a) * 0.91, -0.42)
        base = (fx + dv[0] * 0.035, fy + dv[1] * 0.035, KNUCKLE_Z + dv[2] * 0.035)
        talons.append(G.spike(base, dv, 0.028, length, 5))
    return knuckle, G.merge(talons)


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (0.85, 0.65, 1.0)
    d.budget = 1600
    d.kind = "station"
    d.atlas = {"atlas": 256}
    d.sloped_top = True
    add = d.add

    # the stone hearth: a body (its top face is the coal bed), two jamb stones, four rough capstones on the
    # corners (they break the box's outline into stacked stones; the front two smaller, clear of the front legs).
    # The body and the jambs start 1 cm under the floor, so their rounded bottom edges leave no gap.
    body = G.box(BOX_W, BOX_X1 - BOX_X0, BOX_H + 0.01, 0.03, faces="+x -x +y -y +z", z0=-0.01)
    body = G.translate(G.wobble(body, 0.008, 3, 5.0), (BOX_X0 + BOX_X1) / 2, 0.0, 0.0)
    for ch in body.charts:
        ch.weight = {"+z": 0.9, "+x": 0.4, "-x": 0.35}.get(ch.name, 1.0)
    add(B.Part("fire_box", body, paint=p_stone, seed=11, ao_floor=0.8))
    jw = BOX_W / 2 - MOUTH_W2
    jd = JAMB_X1 - JAMB_X0
    jambs = [_stone(jw, jd, MOUTH_H + 0.02, (JAMB_X0 + JAMB_X1) / 2, s * (MOUTH_W2 + jw / 2), -0.01, 13 + k,
                    "+x +y -y +z", s * 0.03) for k, s in enumerate((1, -1))]
    add(B.Part("jambs", G.merge(jambs), paint=p_stone, seed=15, weight=1.1, ao_floor=0.8))
    caps = []
    for k, (cx, cy, turn, cs) in enumerate(((BOX_X0 + 0.068, 0.222, 0.08, 0.13), (BOX_X0 + 0.068, -0.222, -0.06, 0.13),
                                            (0.015, 0.205, -0.07, 0.11), (0.015, -0.205, 0.05, 0.11))):
        m = G.wobble(G.box(cs, cs, 0.07, faces="+x -x +y -y +z"), 0.012, 50 + k, 6.0)
        caps.append(G.translate(G.transform(m, G.mat_rot_z(turn)), cx, cy, BOX_H - 0.012))
    add(B.Part("capstones", G.merge(caps), paint=p_stone, seed=17, weight=0.9, ao_floor=0.8))

    # the lintel over the mouth: a riveted iron plate in red lacquer with the bone tusk crest, rising over the
    # hearth's top like a fender (the coal bed shows behind it), on an iron beam flush with the hearth's top. A
    # plain closed slab (a 1 cm bevel is under a pixel at 10 yd): its back closes the strip over the beam
    lintel = G.box(BOX_W, PLATE_D, LINTEL_Z1 - LINTEL_Z0, faces="+x -x +y -y +z -z", z0=LINTEL_Z0)
    lintel = G.translate(G.wobble(lintel, 0.003, 19, 5.0), LINTEL_X1 - PLATE_D / 2, 0.0, 0.0)
    for ch in lintel.charts:
        ch.weight = {"+x": 1.6}.get(ch.name, 0.4)
    add(B.Part("lintel", lintel, paint=p_lintel, seed=19, decals={"+x": d_crest}))
    bd = LINTEL_X1 - PLATE_D - JAMB_X0 + 0.004
    beam = G.box(BOX_W - 0.01, bd, BOX_H - LINTEL_Z0 + 0.003, faces="+y -y +z -z", z0=LINTEL_Z0)
    beam = G.translate(beam, JAMB_X0 + bd / 2, 0.0, 0.0)
    beam.set_weight(0.5)
    add(B.Part("lintel_beam", beam, paint=p_lintel, seed=20))

    # the fire: a glow panel at the back of the mouth (its bottom rows are the coals) on a soot-black backing
    # (the hearth's rounded bottom edge would leave a gap under the additive panel), and flame cards over the bed
    back = G.translate(G.box(2 * MOUTH_W2, 0.004, MOUTH_H, faces="+x"), BOX_X1 + 0.005, 0.0, 0.0)
    back.set_weight(0.2)
    add(B.Part("mouth_back", back, paint=("flat", {"color": SOOT}), seed=22))
    mouth = G.translate(G.box(2 * MOUTH_W2, 0.004, MOUTH_H, faces="+x"), BOX_X1 + 0.008, 0.0, 0.0)
    mouth.set_weight(1.3)
    add(B.Part("fire_mouth", mouth, "glow", paint=p_mouth, seed=21, ao_floor=1.0))
    # (the wide card 0.025 behind the kettle's axis, clear of the front capstones)
    cards = [_card(0.6, FLAME_Z1 - FLAME_Z0, FLAME_Z0, 0.0, -0.025),
             _card(0.36, FLAME_Z1 - FLAME_Z0, FLAME_Z0, math.pi / 2)]
    flames = G.merge(cards)
    flames.set_weight(1.0)
    add(B.Part("flames", flames, "glow", paint=p_flames, seed=25, ao_floor=1.0))

    # the boar's tusks rising from the ground at the jamb corners, framing the mouth, tips in toward the crest
    tusks = [G.horn((JAMB_X1 + 0.048, s * 0.27, 0.0), (JAMB_X1 + 0.03, s * 0.16, LINTEL_Z1), (0.25, s, 0.0),
                    0.2, 0.046, 0.008, 6, 6) for s in (1, -1)]
    add(B.Part("tusks", G.merge(tusks), paint=p_bone, seed=27, weight=1.0))

    # the goblin heat gauge on the back half of the hearth's left side, turned toward the front three-quarter
    # view (past the front leg) and tilted up: a closed brass case (its back sunk into the stones, where the
    # turn lifts it off the wall), its dial on the cap, a bezel
    gc, gf, gr = GAUGE
    gm = G.mat_chain(G.mat_translate(*gc), G.mat_disc_facing(G.norm(gf)))
    case = G.transform(G.cylinder(gr, 0.05, 8, True, z0=-0.02), gm)
    for ch in case.charts:
        ch.weight = 2.4 if ch.name == "cyl_top" else 0.5
    add(B.Part("gauge", case, paint=p_gauge, seed=29, ao_floor=0.7, decals={"cyl_top": d_gauge}))
    bezel = G.transform(G.lathe([(gr - 0.006, 0.026), (gr + 0.012, 0.032), (gr - 0.004, 0.042)], 8), gm)
    add(B.Part("gauge_bezel", bezel, paint=p_gauge, seed=30, weight=0.5))

    # the tripod: an iron ring under the kettle's belly, three squat legs (the front ones forged with a hard
    # elbow under an iron collar) down to clawed cast feet
    ring = G.translate(G.torus(RING_R, RING_T, 12, 4), KX, KY, RING_Z)
    add(B.Part("ring", ring, paint=p_iron, seed=31, weight=0.8))
    legs, collars, knuckles, talons = [], [], [], []
    for foot, elbow, angles in LEGS:
        leg, joint = _leg(foot, elbow)
        legs.append(leg)
        if joint:
            at, axis = joint
            band = G.lathe([(0.04, -0.03), (0.06, 0.0), (0.04, 0.03)], 8)
            collars.append(G.transform(band, G.mat_chain(G.mat_translate(*at), G.mat_disc_facing(axis))))
        kn, tl = _claw(foot, angles)
        knuckles.append(kn)
        talons.append(tl)
    add(B.Part("legs", G.merge(legs), paint=p_legs, seed=33, weight=0.9))
    add(B.Part("leg_collars", G.merge(collars), paint=p_collar, seed=35, weight=0.6))
    add(B.Part("claws", G.merge(knuckles + talons), paint=p_claws, seed=37, weight=0.7, ao_floor=0.5))

    # the cast-iron kettle on the ring: hammered gunmetal with a riveted red band, a bone grip
    k = _kettle()

    def place(m):
        return G.transform(m, G.mat_chain(G.mat_translate(KX, KY, KZ), G.mat_scale(KS)))
    add(B.Part("kettle", place(k["body"]), paint=p_kettle, seed=41, weight=1.5))
    add(B.Part("kettle_spout", place(k["spout"]), paint=p_kettle, seed=43, weight=1.2))
    add(B.Part("kettle_lid", place(G.merge([k["lid"], k["knob"]])), paint=p_lid, seed=45, weight=1.0))
    add(B.Part("kettle_handle", place(k["handle"]), paint=p_iron, seed=47, weight=0.8))
    add(B.Part("kettle_grip", place(k["grip"]), paint=p_grip, seed=49, weight=1.0))

    # collision: one hull over the stand and box, a gable roof too steep to stand on (n.z 0.63)
    d.collision = G.hull_gable(0.85, 0.65, 0.6, 1.0)

    tip, tdir = k["tip"], k["dir"]
    d.particles = [
        # on the spout tip: the preset is born small, faintly visible and in a narrow cone, so the plume leaves
        # the spout instead of floating beside it
        EM.kettle_steam((KX + (tip[0] + tdir[0] * 0.005) * KS, KY + (tip[1] + tdir[1] * 0.005) * KS,
                         KZ + (tip[2] + tdir[2] * 0.005) * KS)),
        # sparks born on the mouth floor in front of the jambs (clear of the lintel's face at 0.25), rising
        # between the tusks across the crest and dying before the kettle: invisible and small at birth (no
        # glowing ball at the spawn line), brightest and biggest mid-rise over the crest (0.07 yd)
        EM.embers((JAMB_X1 + 0.035, 0.0, 0.06), width=0.01, length=0.2, latitude=0.3, alphas=(0, 32767, 0),
                  scales=((0.02, 0.02), (0.035, 0.035), (0.0, 0.0)), emission_rate=12.0),
    ]
    return d
