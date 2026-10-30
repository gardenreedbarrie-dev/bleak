"""19319 ChalkboardOrg, the Grinding Tusk menu board (Orgrimmar), CAFE.SPEC.md section 5.8.1.

An orcish street sign that reads as a café menu at a glance: a board of tarred planks, black as slate and
chalked all over ("The" / "Grinding" / "Tusk" in large serif chalk letters, the coffee, tea and shake icons in
pastel chalk over "Coffee · Tea · Shakes", and "Strong brews for strong backs." in orange chalk, between two
rows of chalk teeth), stood between two rough timber posts on skid feet, the posts slashed with red war paint.
Two iron straps, riveted to the posts and wrapped round the board, hold the planks, and two iron spikes are
driven through the top one; above them the posts rise into rope lashings that hold two big ivory tusks, curving
up and inward round the crest: a round plaque in red lacquer with an iron rim and the tusk_crest carved in bone.
0.95 (Y) x 0.5 (X) x 1.45 yd, front (+X) toward the customers.

What makes a player name it (front three-quarter view, 4-15 yd; sizes at 10 yd, about 95 px a yard):
- a dark writing board (0.69 x 0.81) framed by two light timber posts 0.12 wide: a blackboard on legs;
- big chalk words: "Grinding" and "Tusk" at a cap height of 0.096 yd (9 px), white on black;
- the family icons in pastel chalk (about 0.085 yd) and two rows of chalk teeth;
- two ivory tusks (0.1 thick at the root, about 0.35 long) round a red crest plaque (0.27 across): Orgrimmar;
- iron straps (0.055) with bold rivets, two iron spikes (0.064 x 0.085), rope lashings and red claw slashes
  of war paint on the posts: rough, strong, hand-made.

Deviations from section 5.8.1:
- the planks are tarred black and chalked directly (no separate slate), and the posts stand at the board's
  sides, so the timber frames the dark board as a chalkboard frame would;
- "the tusk_crest carved at the top" is a carved plaque on the board's top, painted bone on red lacquer so it
  reads from 15 yd, with two real tusks round it (the crest in three dimensions);
- the title is "The" / "Grinding" / "Tusk" on three lines (a small "The" between chalk swashes), and the long
  line goes on two lines, so everything is large enough to read;
- the face texture (512 x 1024) holds the writing board at its own aspect (512 x 604, so the chalk is neither
  stretched nor blurred by anisotropic mips) and the plaque and straps in the rest of it;
- added for the Orgrimmar look: the iron straps and spikes, the rope lashings, the war paint;
- the collision hull is a gable rather than a flat box, so nobody stands on the sign.

The chalk menu layout is ChalkboardSW's (chalkboard_sw.chalk_menu).
"""

import math

from .. import build as B
from .. import emblem as E
from .. import geom as G
from .. import paint2d as P2
from .. import tex as T
from .chalkboard_sw import chalk_menu

NAME = "ChalkboardOrg"
DISPLAY = 19319

LACQUER = T.hexc("B5402F")
LACQUER_DARK = T.hexc("9C2A1F")
TAR = T.hexc("2A2622")
CHALK = T.hexc("F2EFE6")       # near-white ink: the title must hold under night light
CHALK_ORANGE = T.hexc("F4B088")
CHALK_BONE = T.hexc("EAD8B0")

W, D, H = 0.95, 0.5, 1.45
SKID_H, SKID_W = 0.09, 0.12
POST, POST_Y = 0.12, 0.408          # posts: square section, centres at Y +-POST_Y (outer faces at +-0.468)
POST_TOP = 1.27
BOARD_HW = POST_Y - POST / 2        # the board fills the gap between the posts (half width 0.348)
BOARD_T = 0.05
BOARD_X = 0.02                      # the board's centre: its front 0.015 behind the posts' front faces
BOARD_Z0, BOARD_Z1 = 0.25, 1.24     # plank ends (ragged inward by up to RAGGED)
RAGGED = 0.035
PLANKS, GAP = 4, 0.012
STRAP_H = 0.055
FACE_HW = BOARD_HW - 0.005
FACE_Z0, FACE_Z1 = 0.345, 1.155     # the chalked area between the straps
FACE_W, FACE_H = 2 * FACE_HW, FACE_Z1 - FACE_Z0
FACE_PX = (512, int(round(512 * FACE_H / FACE_W / 4.0)) * 4)
FACE_X = BOARD_X + BOARD_T / 2 + 0.006   # the chalked face, just in front of the (wobbly) planks
STRAP_X0, STRAP_X1 = BOARD_X - BOARD_T / 2 - 0.008, POST / 2 + 0.018   # straps: round the board, over the posts
PLAQUE_R, PLAQUE_T = 0.14, 0.04
PLAQUE_C = (STRAP_X1 + PLAQUE_T, 0.0, 1.30)                     # front centre: on the top strap
LASH_Z0, LASH_H = 1.185, 0.085


def _plank_bounds():
    """[(y0, y1)] of each plank, from -Y to +Y."""
    pw = (2 * BOARD_HW - GAP * (PLANKS - 1)) / PLANKS
    return [(-BOARD_HW + i * (pw + GAP), -BOARD_HW + i * (pw + GAP) + pw) for i in range(PLANKS)]


SEAMS = [b[1] + GAP / 2 + FACE_HW for b in _plank_bounds()[:-1]]     # plank gaps in face s (yd from the left)


# ----------------------------------------------------------------------------------------------- face

def g_tar(ctx, seed, p):
    """Tarred planks under the chalk: near-black boards, each its own tone, with long grain streaks, dark gaps
    with a lit lip on their right, and a haze of wiped chalk in broad eraser swipes."""
    s, t = ctx.s, ctx.t
    seams = p.get("seams", SEAMS)
    i = sum(1 for q in seams if s > q)
    tone = T._h(i, 3, 5, seed)
    c = T.mix(T.scale(TAR, 0.85), T.scale(TAR, 1.25), tone)
    c = T.mix(c, T.scale(TAR, 1.35), T.fbm(s * 3.0, t * 2.0, seed + 1, 3) * 0.5)
    g = T.noise((s + i * 0.37) * 30.0, t * 1.6, seed + 2)
    c = T.mix(c, T.scale(TAR, 0.62), T.smoothstep(0.55, 0.85, g) * 0.55)
    sw = T.noise(s * 1.2, t * 4.0 + T.noise(s * 2.0, t * 2.0, seed + 4) * 2.0, seed + 5)
    c = T.mix(c, T.hexc("B8BCB4"), T.smoothstep(0.55, 0.92, sw) * 0.13)
    for q in seams:
        d = s - q
        if abs(d) < GAP / 2:
            return T.scale(TAR, 0.25)
        if GAP / 2 <= d < GAP / 2 + 0.007:
            c = T.mix(c, T.hexc("6A5A48"), 0.45)
        elif -GAP / 2 - 0.006 < d < -GAP / 2:
            c = T.scale(c, 0.6)
    return c


def tar_bg(w, h, seed):
    return T.image_lowres(g_tar, w, h, seed, {"seams": SEAMS}, (FACE_W, FACE_H), factor=2)


def d_front(w, h):
    """The Grinding Tusk menu, chalked on the planks."""
    return chalk_menu(w, h, 5, {
        "bg": tar_bg, "border": "teeth", "teeth_rows": (0.075, 0.925), "border_c": CHALK_BONE,
        "title": [("The", "small"), ("Grinding", "big"), ("Tusk", "big")], "big_cap": 0.12,
        "small_c": CHALK_ORANGE, "icons": ["coffee", "tea", "shake"], "icon_size": 0.105,
        "caption": "Coffee · Tea · Shakes", "lines": ["Strong brews for strong backs."], "line_c": CHALK_ORANGE,
        "top": 0.12, "bottom": 0.11})


def d_plaque(w, h):
    """The crest plaque: a hammered iron rim with eight bold rivets round a red lacquer field, the tusk crest
    carved in it and picked out in bone."""
    img = T.Img(w, h, (0, 0, 0, 0))
    cx, cy, r0 = w / 2.0, h / 2.0, min(w, h) / 2.0 * 0.97
    for y in range(h):
        for x in range(w):
            dx, dy = (x + 0.5 - cx) / r0, (y + 0.5 - cy) / r0
            d = math.hypot(dx, dy)
            if d > 1.0:
                continue
            lit = T.clamp01(0.5 - (dx * 0.55 + dy * 0.8) * 0.5)
            if d > 0.8:
                c = T.mix(T.hexc("2A2A30"), T.hexc("6A6C74"), lit * 0.8 + 0.1 * T.noise(x * 0.3, y * 0.3, 3))
                a = math.atan2(dy, dx)
                step = 2 * math.pi / 8
                da = ((a + step / 2) % step) - step / 2
                rd = math.hypot(da * 0.9, d - 0.9) / 0.075
                if rd < 1.0:
                    c = T.mix(T.hexc("3A3A40"), T.hexc("C8CCD4"), T.clamp01(0.6 - dy * 0.8 - dx * 0.4) * (1 - rd))
                elif d < 0.83:
                    c = T.scale(c, 0.5)
            else:
                c = T.mix(T.scale(LACQUER_DARK, 0.8), T.mix(LACQUER, T.hexc("E07A5A"), 0.35), lit * (1.0 - d * 0.4))
                if d > 0.76:
                    c = T.scale(c, 0.55)
            img.set(x, y, c, 1.0)
    s = int(min(w, h) * 0.66)
    if s > 8:
        P2.composite(img, E.render_relief("tusk_crest", s, s, P2.BONE_RELIEF), (w - s) // 2, int((h - s) * 0.42))
    return img


# ----------------------------------------------------------------------------------------------- paints

WAR_PAINT_Z = (0.56, 0.84)          # the red claw slashes on the posts' fronts


def _claw(ctx, c, seed):
    """Orcish war paint on a post's front: three red claw slashes, each a stroke that tapers at both ends,
    with a rough dry-brush edge."""
    z = ctx.pos[2]
    z0, z1 = WAR_PAINT_Z
    if not z0 - 0.02 < z < z1 + 0.02:
        return c
    u = ctx.s / ctx.cw - 0.5                  # across the face, -0.5..0.5
    v = (z - z0) / (z1 - z0)                   # up the slashes, 0..1
    best = 1.0
    for k in (-1, 0, 1):
        x = u - k * 0.3 - (v - 0.5) * 0.55     # leaning slashes
        half = 0.07 * math.sin(math.pi * T.clamp01(v))
        if half > 0:
            best = min(best, abs(x) / half)
    if best < 1.0:
        n = T.noise(ctx.s * 90.0, z * 40.0, seed + 9)
        if best < 0.75 + 0.3 * n:
            return T.mix(T.mix(LACQUER, LACQUER_DARK, n * 0.6), c, 0.12)
    return c


def p_timber(ctx, seed, p):
    """Rough light timber for the posts and skids, grain along the length, darker end grain, and red war paint
    on the posts' fronts."""
    c = T.g_planks(ctx, seed, {"kind": "timber", "count": 1, "knots": 1, "ragged": 0.0})
    if ctx.chart in ("+z", "-z") and ctx.part != "skids":
        c = T.mix(c, T.hexc("4A3018"), 0.5)
    if ctx.part == "posts" and ctx.chart == "+x":
        c = _claw(ctx, c, seed)
    return c


def p_planks(ctx, seed, p):
    """The planks: tarred black on their ends (the chalked front is the face texture), the lighter end grain
    showing where the tar wore off; rough dark timber on the back."""
    if ctx.chart == "-x":
        return T.g_planks(ctx, seed, {"kind": "orgdark", "count": 1, "knots": 1})
    c = T.mix(T.g_planks(ctx, seed, {"kind": "orgdark", "count": 1, "knots": 0}), TAR, 0.55)
    if ctx.chart in ("+z", "-z"):
        c = T.mix(c, T.hexc("7A5A38"), 0.45)
    return c


def p_strap(ctx, seed, p):
    """Hammered iron straps: lit top lip, dark bottom edge, a bold rivet at every plank and post."""
    c = T.g_hammered_iron(ctx, seed, {"dent": 0.04, "rust": 0.1})
    if ctx.chart != "+x":
        return T.scale(c, 0.8)
    if ctx.t < 0.008:
        c = T.mix(c, T.hexc("B4B8C0"), 0.35)
    elif ctx.t > STRAP_H - 0.008:
        c = T.scale(c, 0.55)
    y = ctx.pos[1]
    cols = [-POST_Y, POST_Y] + [(a + b) / 2 for a, b in _plank_bounds()]
    yc = min(cols, key=lambda q: abs(q - y))
    return T.rivet_dot(c, y - yc, ctx.t - STRAP_H / 2, 0.014, T.IRON_RIVET_HI, T.IRON_RIVET_LO)


def p_spike(ctx, seed, p):
    """Dark iron spikes, lit along their upper flanks, the points worn bright."""
    c = T.g_iron(ctx, seed, {"rust": 0.15})
    c = T.mix(c, T.hexc("A8ACB4"), T.clamp01(ctx.n[2] + 0.2) * 0.35)
    return c


def p_plaque(ctx, seed, p):
    """The plaque's edge and back: dark hammered iron."""
    return T.g_hammered_iron(ctx, seed, {"dent": 0.035, "rust": 0.12})


def p_tusk(ctx, seed, p):
    return T.g_bone(ctx, seed, {"kind": "ivory", "root": 0})


def p_lashing(ctx, seed, p):
    """Rope coils wound round the post tops: four turns, each a lit round with dark grooves between."""
    pitch = LASH_H / 4.0
    q = (ctx.t % pitch) / pitch
    prof = math.sin(math.pi * q)
    base = T.hexc("B08A52")
    c = T.mix(T.scale(base, 0.35), base, T.smoothstep(0.0, 0.6, prof))
    tw = ((ctx.s * 3.0 / pitch + q * 1.5) % 1.0)
    c = T.scale(c, 0.85 + 0.25 * T.smoothstep(0.2, 0.5, tw) * T.smoothstep(0.9, 0.6, tw))
    return T.mix(c, T.hexc("F0DCB0"), T.smoothstep(0.75, 1.0, prof) * 0.25)


# ------------------------------------------------------------------------------------------------ parts

def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (W, D, H)
    d.budget = 300
    d.kind = "chalkboard"
    d.atlas = {"atlas": 256, "face": (512, 1024)}
    d.tex_flags = {"face": 0}
    d.sloped_top = True
    add = d.add

    # skid feet under the posts, ragged at both ends
    skids = []
    for k, sy in enumerate((1, -1)):
        sk = G.box(SKID_W, D, SKID_H - 0.006, faces="+x -x +y -y +z", z0=0.006)   # wobble stays above the floor
        sk = G.plank_edges(sk, 21 + k, 0.03, "x", inward=True)
        skids.append(G.translate(G.wobble(sk, 0.006, 23 + k), 0.0, sy * POST_Y, 0.0))
    add(B.Part("skids", G.merge(skids), paint=p_timber, seed=11))

    # posts, chopped tops
    posts = []
    for k, sy in enumerate((1, -1)):
        po = G.box(POST, POST, POST_TOP - SKID_H, faces="+x -x +y -y +z", z0=SKID_H)
        po = G.plank_edges(po, 31 + k, 0.025, "z", inward=True)
        posts.append(G.translate(G.wobble(po, 0.006, 33 + k, 4.0), 0.0, sy * POST_Y, 0.0))
    posts = G.merge(posts)
    for ch in posts.charts:
        ch.weight = 0.9 if ch.name in ("+x", "+y", "-y") else 0.5
    add(B.Part("posts", posts, paint=p_timber, seed=13))

    # the plank board between the posts; its front is the chalked face
    planks = []
    for k, (y0, y1) in enumerate(_plank_bounds()):
        pl = G.box(y1 - y0, BOARD_T, BOARD_Z1 - BOARD_Z0, faces="+x -x +z -z", z0=BOARD_Z0)
        pl = G.plank_edges(pl, 41 + 3 * k, RAGGED, "z", inward=True)
        planks.append(G.translate(G.wobble(pl, 0.003, 43 + k), BOARD_X, (y0 + y1) / 2, 0.0))
    planks = G.merge(planks)
    for ch in planks.charts:
        ch.weight = {"-x": 0.5, "+x": 0.15}.get(ch.name, 0.8)
    add(B.Part("planks", planks, paint=p_planks, seed=15))
    face = G.translate(G.box(FACE_W, 0.002, FACE_H, faces="+x", z0=FACE_Z0), FACE_X - 0.001, 0.0, 0.0)
    G.uv_region(face, (0, 0) + FACE_PX)
    add(B.Part("chalk_face", face, texture="face", paint=("flat", {}), seed=17, decals={"+x": d_front}))

    # iron straps across the posts and planks, above and below the chalk
    straps = [G.translate(G.box(W - 0.004, STRAP_X1 - STRAP_X0, STRAP_H, z0=z0),
                          (STRAP_X0 + STRAP_X1) / 2, 0.0, 0.0) for z0 in (FACE_Z0 - STRAP_H, FACE_Z1)]
    add(B.Part("straps", G.merge(straps), texture="face", paint=p_strap, seed=19))

    # two iron spikes driven through the top strap into the posts, points forward
    zs = FACE_Z1 + STRAP_H / 2
    spikes = [G.spike((STRAP_X1 - 0.004, sy * POST_Y, zs), (1.0, 0.0, 0.18), 0.032, 0.085) for sy in (1, -1)]
    add(B.Part("spikes", G.merge(spikes), paint=p_spike, seed=27, ao_floor=0.7))

    # the crest plaque on the board's top, between the tusks
    plaque = G.extrude(G.circle_polygon(PLAQUE_R, 12, math.pi / 12), PLAQUE_T, 0.0, True, name="plaque")
    plaque = G.transform(plaque, G.mat_chain(G.mat_translate(PLAQUE_C[0] - PLAQUE_T, 0.0, PLAQUE_C[2]),
                                             G.MAT_EXTRUDE_FRONT))
    for ch in plaque.charts:
        ch.weight = {"plaque_front": 1.0, "plaque_side": 0.4}.get(ch.name, 0.3)
    add(B.Part("plaque", plaque, texture="face", paint=p_plaque, seed=21, decals={"plaque_front": d_plaque}))

    # rope lashings round the post tops; the tusks rise out of them, curving up and inward round the crest
    lash = [G.translate(G.box(POST + 0.018, POST + 0.018, LASH_H, faces="+x -x +y -y", z0=LASH_Z0), 0.0,
                        sy * POST_Y, 0.0) for sy in (1, -1)]
    add(B.Part("lashings", G.merge(lash), paint=p_lashing, seed=23, weight=1.2))
    tusks = []
    for sy in (1, -1):
        root = (0.0, sy * POST_Y, POST_TOP - 0.03)
        tip = (0.03, sy * 0.17, H - 0.004)
        tusks.append(G.horn(root, tip, (0.0, sy * 1.0, 0.35), 0.3, 0.05, 0.0, 5, 6, cap=False))
    add(B.Part("tusks", G.merge(tusks), paint=p_tusk, seed=25, weight=1.3))

    d.collision = G.hull_gable(W, D, 1.0, H)
    d.particles = []
    return d
