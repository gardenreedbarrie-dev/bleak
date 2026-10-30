"""Shared pieces of the two cold boxes, ColdBoxSW and ColdBoxOrg (CAFE.SPEC.md section 5.8.1): the rime and
crushed-ice paints, the icicles, the ice-cream paint and colours, the heaped scoop, the tub's lip and the cone
crest shapes, the sloped collision box, the frost mist, the ice-cream cone icon and a flat-polygon builder. Not a
model: the leading underscore keeps it out of discovery, so each cold box depends on this module and not on the
other one.

Painted detail follows the section 5.5 rule as far as a 256 atlas allows: the cold boxes pack at 59-65 texels/yd
(about 100 on the scoops, whose charts are weighted 1.6), so chips on the scoops are 0.04 yd across (4 texels
there), ice lumps 0.09 yd, and nothing is a fine fleck."""

import math

from .. import emitters as EM
from .. import geom as G
from .. import paint2d as P2
from .. import raster2d as R
from .. import tex as T

FROST = T.hexc("F2FAFF")
FROST_BLUE = T.hexc("A8CCEC")
ICE = T.hexc("BCD8F0")          # crushed ice: a cool blue-white that the pale scoops stand out from
ICE_GAP = T.hexc("6E98C2")

# Ice-cream flavours: (base, light, dark, chip colour or None, gloss)
FLAVOURS = {
    "vanilla": (T.hexc("F6D27E"), T.hexc("FFF0C0"), T.hexc("B07E3C"), None, 0.5),
    "chocolate": (T.hexc("74401F"), T.hexc("9E5E30"), T.hexc("3A1A0A"), None, 0.5),
    "berry": (T.hexc("EC86A2"), T.hexc("FFC4D4"), T.hexc("B04466"), T.hexc("8A1638"), 0.5),
    # Orgrimmar: kodo milk (a cream that stays cream under the blue ice, about D2CDAD through it, where a
    # white one turned into a blue-white snowball), a darker chocolate, cactus apple with green seeds
    "kodo": (T.hexc("EBCF94"), T.hexc("FFF0C8"), T.hexc("A8844E"), None, 0.4),
    "dark_chocolate": (T.hexc("5A2A14"), T.hexc("84401C"), T.hexc("2A1006"), None, 0.7),
    "cactus": (T.hexc("E07898"), T.hexc("FFB8CC"), T.hexc("A8405E"), T.hexc("4E9A34"), 0.5),
}
CHIP_R = 0.02                   # chips and seeds: 0.04 yd across (4+ texels at the scoops' density)


# ----------------------------------------------------------------------------------------------- noise

def _hash(ix, iy, seed):
    h = (ix * 374761393 + iy * 668265263 + seed * 144665) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def _cells(s, t, size, seed):
    """Voronoi over chart (s, t): (distance to the nearest site, to the second one, the nearest cell's hash),
    in cell units."""
    gx, gy = s / size, t / size
    ix, iy = math.floor(gx), math.floor(gy)
    f1, f2, h1 = 9.0, 9.0, 0.0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            cx, cy = ix + dx, iy + dy
            px = cx + 0.15 + 0.7 * _hash(cx, cy, seed)
            py = cy + 0.15 + 0.7 * _hash(cx, cy, seed + 1)
            d = math.hypot(gx - px, gy - py)
            if d < f1:
                f1, f2, h1 = d, f1, _hash(cx, cy, seed + 2)
            elif d < f2:
                f2 = d
    return f1, f2, h1


# ----------------------------------------------------------------------------------------------- paints

def frost(ctx, c, k, seed):
    """White rime over colour c where k (0..1) is high: a crisp, ragged edge (no grey half-mix over the metal
    or the wood), white with pale blue hollows."""
    if k <= 0.0:
        return c
    x, y, z = ctx.pos
    v = T.fbm3(x * 14.0, y * 14.0, z * 14.0, seed, 2)
    f = T.mix(FROST, FROST_BLUE, T.smoothstep(0.55, 0.85, v) * 0.7)
    return T.mix(c, f, T.smoothstep(0.38, 0.62, k + (v - 0.5) * 0.45))


def top_frost(ctx, seed, depth=0.05):
    """How much rime a texel carries: on faces turned up, and creeping `depth` yd down from the top of a side
    face in ragged drips (from the face's top chart edge, t = 0)."""
    k = T.smoothstep(0.35, 0.85, ctx.n[2])
    if abs(ctx.n[2]) < 0.5 and ctx.chart in ("+x", "-x", "+y", "-y"):
        drip = depth * (0.45 + 0.9 * T.noise(ctx.s * 22.0, 0.5, seed + 7) ** 2)
        k = max(k, T.smoothstep(drip, drip * 0.4, ctx.t))
    return k


def p_ice(ctx, seed, p):
    """Crushed ice: big faceted lumps (0.09 yd, each lit on its upper left) with blue gaps between them."""
    f1, f2, h = _cells(ctx.s, ctx.t, 0.09, seed)
    c = T.mix(ICE, T.hexc("F4FAFF"), 0.15 + 0.6 * h)
    c = T.mix(c, T.hexc("FFFFFF"), T.smoothstep(0.4, 0.0, f1) * 0.45)
    return T.mix(ICE_GAP, c, T.smoothstep(0.06, 0.25, f2 - f1))


def p_icicle(ctx, seed, p):
    """Icicles: pale blue ice with a bright streak down the lit side and a white root (the chart runs from the
    root, t = 0, to the tip)."""
    c = T.mix(T.hexc("86B8E2"), T.hexc("F0FAFF"), T.clamp01(ctx.n[0] * 0.5 + ctx.n[1] * 0.4 + 0.45))
    if ctx.chart.endswith("_top"):
        return FROST
    return T.mix(c, FROST, T.smoothstep(0.3, 0.05, ctx.v))


def scoop(ctx, seed, flavour, centre, chips=0):
    """Ice cream painted soft and creamy so it reads as scoops (not as bread or a pastry): the flavour's colour
    with a broad lit crown and a cool shaded underside, a glossy highlight toward the light, faint curls where
    the scoop rolled, and up to `chips` bold chips (berry bits, cactus seeds) on the front half.
    centre: (x, y, z) of the scoop's ball."""
    base, light, dark, chip, gloss = FLAVOURS[flavour]
    x, y, z = ctx.pos
    cx, cy, zc = centre
    nx, ny, nz = ctx.n
    c = T.mix(base, light, T.smoothstep(0.1, 0.95, nz) * 0.3)
    c = T.mix(c, T.mix(dark, T.hexc("5A5E8A"), 0.2), T.smoothstep(-0.1, -0.85, nz) * 0.5)
    hl = nx * 0.38 - ny * 0.22 + nz * 0.9
    c = T.mix(c, T.mix(light, (1.0, 1.0, 1.0), 0.5), T.smoothstep(0.86, 0.99, hl) * gloss)
    phi = math.atan2(y - cy, x - cx)
    curl = math.sin((z - zc) * 80.0 + phi * 1.2 + T.noise(phi * 2.0, z * 20.0, seed) * 1.8)
    c = T.mix(c, dark, T.smoothstep(0.75, 1.0, curl) * 0.12)
    c = T.mix(c, light, T.smoothstep(-0.7, -1.0, curl) * 0.10)
    c = T.scale(c, 1.0 - 0.14 * T.smoothstep(zc - 0.04, zc - 0.08, z))   # the skirt under the ball, a shade
                                                                          # deeper (the bake lights its top)
    if chip is not None and chips:
        rr = max(math.hypot(x - cx, y - cy), 0.02)
        for j in range(chips):
            pj = (_hash(j, 5, seed) - 0.5) * 2.6           # spread over the front half (+X is phi 0)
            zj = zc + (_hash(j, 6, seed) - 0.4) * 0.12
            dphi = (phi - pj + math.pi) % (2.0 * math.pi) - math.pi
            d = math.hypot(dphi * rr, (z - zj) * 1.2)
            if d < CHIP_R:
                c = T.mix(c, chip, 0.9 * T.smoothstep(CHIP_R, CHIP_R * 0.55, d))
                if d < CHIP_R * 0.45 and dphi < 0.0:
                    c = T.mix(c, light, 0.25)                # a lit edge on the chip
    return c


def p_waffle(ctx, seed, p):
    """A waffle cone (on the cone's lathe chart: u around, t down from the mouth): toasted tan with a bold
    diamond grid of darker grooves and lit squares, and a pale rolled rim."""
    a = ctx.u * 8.0
    b = (ctx.ch - ctx.t) * 26.0
    u, v = (a + b) % 1.0, (a - b) % 1.0
    g = min(u, 1.0 - u, v, 1.0 - v)
    c = T.mix(T.hexc("C98A44"), T.hexc("ECBE76"), T.smoothstep(0.08, 0.32, g))
    c = T.mix(T.hexc("6E4018"), c, T.smoothstep(0.04, 0.12, g))
    if ctx.t < 0.016:
        c = T.mix(c, T.hexc("F2CC8C"), 0.5)
    return c


# ----------------------------------------------------------------------------------------------- shapes

def poly(pts, outward, name="poly"):
    """A flat convex polygon facing `outward` (one chart in yards: s along its first edge)."""
    n = G.norm(G.cross(G.sub(pts[1], pts[0]), G.sub(pts[2], pts[0])))
    if G.dot(n, outward) < 0:
        pts = pts[::-1]
        n = G.mul(n, -1.0)
    u = G.norm(G.sub(pts[1], pts[0]))
    v = G.cross(n, u)
    st = [(G.dot(G.sub(q, pts[0]), u), -G.dot(G.sub(q, pts[0]), v)) for q in pts]
    s0, t0 = min(a for a, _ in st), min(b for _, b in st)
    m = G.Mesh()
    ch = m.chart(max(a for a, _ in st) - s0, max(b for _, b in st) - t0, name)
    ids = [m.vert(q, n, ch, a - s0, b - t0) for q, (a, b) in zip(pts, st)]
    for k in range(1, len(ids) - 1):
        m.tri(ids[0], ids[k], ids[k + 1])
    return m


def scallop(mesh, cx, cy, z_top, n, amp, drop, phase=0.0):
    """A drippy skirt: below z_top, pushes the mesh out and down in n rounded lobes round (cx, cy) (radius
    times 1 + amp cos(n phi), and down by `drop` under each lobe), fading out toward z_top."""
    out = mesh.copy()
    zb = min(q[2] for q in mesh.p)
    pts = []
    for x, y, z in mesh.p:
        if z < z_top:
            f = T.smoothstep(z_top, zb + (z_top - zb) * 0.3, z)
            w = math.cos(n * (math.atan2(y - cy, x - cx) - phase))
            k = 1.0 + amp * w * f
            x, y = cx + (x - cx) * k, cy + (y - cy) * k
            z -= drop * max(0.0, w) * f
        pts.append((x, y, z))
    out.p = pts
    return out


def lean_back(mesh, z0, z1, dx):
    """Shifts the mesh back (-X) by up to dx, from nothing at z0 to all of it at z1 (a scoop leaning away
    from the glass)."""
    out = mesh.copy()
    out.p = [(x - dx * T.smoothstep(z0, z1, z), y, z) for x, y, z in mesh.p]
    return out


# A heaped tub, relative to its rim (r, dz): a scalloped skirt that stops 0.02 inside the rim (so a ring of the
# tub's lip shows round every heap), a crease (the neck) and a round scoop on top, 0.17 across, its top 0.183
# over the rim.
HEAP = [(0.122, -0.005), (0.13, 0.013), (0.118, 0.033), (0.072, 0.046), (0.083, 0.078), (0.078, 0.128),
        (0.045, 0.168), (0.0, 0.183)]
HEAP_BALL = 0.098               # the ball's middle over the rim (for the paint)


def heap(rim_z, sides, seed, phase=0.0, lean=0.025):
    """One tub's ice cream around the Z axis (translate it onto its tub): the HEAP profile lathed, the skirt
    scalloped into six drips, the scoop leaning back from the glass, roughened, and smooth-shaded (normals
    recomputed after every deformer, so no facet reads)."""
    m = G.lathe([(r, rim_z + dz) for r, dz in HEAP], sides, angle=70.0, name="heap", seam=math.pi + phase)
    m = scallop(m, 0.0, 0.0, rim_z + 0.035, 6, 0.06, 0.006, phase)
    m = lean_back(m, rim_z + 0.04, rim_z + HEAP[-1][1], lean)
    return G.recompute_normals(G.wobble(m, 0.005, seed, 9.0), 80.0)


def rim_cap(x, y, z, r, sides, name="rim"):
    """A flat lid on a tub's rim (z), as one polygon of sides - 2 triangles, its corners on the rim of
    G.cylinder(r, ..., sides) at (x, y): the heap covers its middle, so only a ring 0.02 wide shows round the
    heap, the tub's lip."""
    pts = [(x + r * math.cos(math.pi + 2 * math.pi * k / sides), y + r * math.sin(math.pi + 2 * math.pi * k / sides),
            z) for k in range(sides)]
    return poly(pts, (0.0, 0.0, 1.0), name)


def crest_scoop(z0, ball_r, sides):
    """The crest's scoop around the Z axis, sitting in a cone mouth at z0: a drip lip over the rim and a round
    ball (ball_r) on it. Returns (mesh, its top z)."""
    k = ball_r / 0.085
    prof = [(0.05 * k, z0 - 0.012), (0.08 * k, z0 + 0.004), (0.089 * k, z0 + 0.02 * k),
            (0.085 * k, z0 + 0.055 * k), (0.068 * k, z0 + 0.094 * k), (0.038 * k, z0 + 0.118 * k),
            (0.0, z0 + 0.127 * k)]
    m = G.lathe(prof, sides, angle=70.0, name="scoop")
    m = scallop(m, 0.0, 0.0, z0 + 0.03 * k, 7, 0.07, 0.012)
    return G.recompute_normals(m, 80.0), z0 + 0.127 * k


def hull_wedge(w, d, h, front_z):
    """The collision box of section 5.2.6 (W along Y, D along X, H) with its top sloping from h at the back down
    to front_z over the front edge: it follows the glass, so no one stands in mid-air over the lid. Still 12
    triangles, still h tall."""
    pos, tris = G.hull_box(w, d, h)
    pos[5], pos[6] = (d / 2.0, -w / 2.0, front_z), (d / 2.0, w / 2.0, front_z)
    return pos, tris


def mist(x, y, z, length=0.44):
    """Frost mist (section 5.2.7, frost mist variant) born along half of the front lip: a strip `length` (Y) x
    0.03 (X) centred at (x, y, z) just past the lip's top edge (two of them cover the whole lip), with almost no
    speed and a strong positive gravity, so the puffs roll over the edge and sink down the front instead of
    hanging at the corners as stationary blobs. Small puffs (0.03 growing to 0.1) already faintly visible at
    birth: the client has no soft particles, so bigger puffs, or puffs nearer the chest face, are cut off against
    it in hard straight lines."""
    return EM.frost_mist((x, y, z), length=length, width=0.03, speed=0.01, variation=0.5, gravity=0.3, life=1.8,
                         emission_rate=9.0, alphas=(5000, 9000, 0),
                         scales=((0.03, 0.03), (0.07, 0.07), (0.1, 0.1)))


# ----------------------------------------------------------------------------------------------- decals

# The ice-cream cone icon in a 100-unit box: a waffle cone, a scoop with a drip lip, a second scoop and a
# topping (original drawing).
CONE_ICON = "M31 50 L69 50 L50 97 Z"
LIP_BUMPS = [(31, 52), (39, 55), (47, 53), (55, 56), (63, 53), (70, 51)]
ICON_COLORS = {"outline": T.hexc("1A1008"), "cone": T.hexc("D49650"), "grid": T.hexc("7A4A1C"),
               "low": T.hexc("F4E4B8"), "low_hi": T.hexc("FFFBEC"), "top": T.hexc("EE7C9C"),
               "top_hi": T.hexc("FFC8D6"), "cherry": T.hexc("D01E28")}


def _circle(cx, cy, r, n=28):
    pts = ["M%.2f %.2f" % (cx + r, cy)]
    for k in range(1, n):
        a = 2 * math.pi * k / n
        pts.append("L%.2f %.2f" % (cx + math.cos(a) * r, cy + math.sin(a) * r))
    return " ".join(pts) + " Z"


def cone_icon(img, ox, oy, s, colors=None):
    """Paints the cone icon into img in an s x s box at (ox, oy): a dark outline round the whole shape, then
    the cone with its waffle grid, the two scoops (each with a lit crown) and the topping. colors: overrides
    of ICON_COLORS (each café paints it in its own colours)."""
    col = dict(ICON_COLORS, **(colors or {}))
    k = s / 100.0

    def mask(d):
        m = R.Mask(img.w, img.h)
        R.path_fill(m, d, k, k, ox, oy)
        return m
    cone = mask(CONE_ICON)
    van = mask(_circle(50, 43, 20))
    for bx, by in LIP_BUMPS:
        van.max_with(mask(_circle(bx, by, 5.5)))
    pink = mask(_circle(50, 25, 17))
    cherry = mask(_circle(52, 7, 6))
    union = cone.copy().max_with(van).max_with(pink).max_with(cherry)
    P2.paint_mask(img, R.dilate(union, max(1, int(s * 0.03))), col["outline"])
    P2.paint_mask(img, cone, col["cone"])
    grid = R.Mask(img.w, img.h)
    for q in range(-3, 6):
        R.path_stroke(grid, "M%d 40 L%d 100" % (20 + q * 12, 50 + q * 12), 3.2 * k, k, k, ox, oy)
        R.path_stroke(grid, "M%d 40 L%d 100" % (80 - q * 12, 50 - q * 12), 3.2 * k, k, k, ox, oy)
    grid.multiply(cone)
    P2.paint_mask(img, grid, col["grid"])
    P2.paint_mask(img, van, col["low"])
    P2.paint_mask(img, pink, col["top"])
    P2.paint_mask(img, mask(_circle(45, 20, 7)), col["top_hi"], alpha=0.8)
    P2.paint_mask(img, mask(_circle(44, 38, 6)), col["low_hi"], alpha=0.8)
    P2.paint_mask(img, cherry, col["cherry"])
    P2.paint_mask(img, mask(_circle(50, 5, 2.2)), T.hexc("FFD0D0"))
