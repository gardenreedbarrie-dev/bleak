"""Mesh library (CAFE.SPEC.md section 5.4).

Conventions (section 5.2.1): 1 unit = 1 yard, +X is the model's front, +Y is left, +Z is up, the origin is the
centre of the footprint at the base. Triangles are counter-clockwise seen from outside: (b - a) x (c - a) points
outward. Every primitive is built that way; the tests check the signed volume of closed meshes.

UVs. Every vertex belongs to one *chart*: a rectangle of the surface measured in yards (Chart.w x Chart.h) with the
vertex at (s, t) inside it, s to the right and t downward as seen from outside (texture rows run top to bottom,
UV (0, 0) is the top-left texel, D3D convention). The atlas packer (atlas.py) later places every chart in the
texture at one texel density, so UV islands are unique by construction (the bake needs that, section 5.5).
"""

import math

TAU = 2.0 * math.pi


# ------------------------------------------------------------------------------------------------ vectors

def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def norm(a):
    ln = length(a)
    if ln < 1e-12:
        return (0.0, 0.0, 1.0)
    return (a[0] / ln, a[1] / ln, a[2] / ln)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


# ----------------------------------------------------------------------------------------------- matrices
# 3x4 affine matrices, row-major: ((r00, r01, r02, tx), (r10, r11, r12, ty), (r20, r21, r22, tz)).

def mat_identity():
    return ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))


def mat_translate(x, y, z):
    return ((1.0, 0.0, 0.0, x), (0.0, 1.0, 0.0, y), (0.0, 0.0, 1.0, z))


def mat_scale(sx, sy=None, sz=None):
    sy = sx if sy is None else sy
    sz = sx if sz is None else sz
    return ((sx, 0.0, 0.0, 0.0), (0.0, sy, 0.0, 0.0), (0.0, 0.0, sz, 0.0))


def mat_rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return ((1.0, 0.0, 0.0, 0.0), (0.0, c, -s, 0.0), (0.0, s, c, 0.0))


def mat_rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return ((c, 0.0, s, 0.0), (0.0, 1.0, 0.0, 0.0), (-s, 0.0, c, 0.0))


def mat_rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return ((c, -s, 0.0, 0.0), (s, c, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))


def mat_mul(a, b):
    """a * b: b is applied first."""
    out = []
    for i in range(3):
        row = []
        for j in range(4):
            v = a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j]
            if j == 3:
                v += a[i][3]
            row.append(v)
        out.append(tuple(row))
    return tuple(out)


def mat_chain(*ms):
    """mat_chain(A, B, C) = A * B * C: C is applied first."""
    out = mat_identity()
    for m in ms:
        out = mat_mul(out, m)
    return out


def mat_apply(m, p):
    return (m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2] + m[0][3],
            m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2] + m[1][3],
            m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2] + m[2][3])


def mat_apply_dir(m, d):
    return (m[0][0] * d[0] + m[0][1] * d[1] + m[0][2] * d[2],
            m[1][0] * d[0] + m[1][1] * d[1] + m[1][2] * d[2],
            m[2][0] * d[0] + m[2][1] * d[1] + m[2][2] * d[2])


def mat_det3(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def mat_normal(m):
    """Inverse transpose of the linear part (as a 3x4 with zero translation), for normals."""
    a = m
    det = mat_det3(a)
    if abs(det) < 1e-18:
        raise ValueError("singular matrix")
    inv = [[0.0] * 3 for _ in range(3)]
    inv[0][0] = (a[1][1] * a[2][2] - a[1][2] * a[2][1]) / det
    inv[0][1] = (a[0][2] * a[2][1] - a[0][1] * a[2][2]) / det
    inv[0][2] = (a[0][1] * a[1][2] - a[0][2] * a[1][1]) / det
    inv[1][0] = (a[1][2] * a[2][0] - a[1][0] * a[2][2]) / det
    inv[1][1] = (a[0][0] * a[2][2] - a[0][2] * a[2][0]) / det
    inv[1][2] = (a[0][2] * a[1][0] - a[0][0] * a[1][2]) / det
    inv[2][0] = (a[1][0] * a[2][1] - a[1][1] * a[2][0]) / det
    inv[2][1] = (a[0][1] * a[2][0] - a[0][0] * a[2][1]) / det
    inv[2][2] = (a[0][0] * a[1][1] - a[0][1] * a[1][0]) / det
    # transpose
    return ((inv[0][0], inv[1][0], inv[2][0], 0.0), (inv[0][1], inv[1][1], inv[2][1], 0.0),
            (inv[0][2], inv[1][2], inv[2][2], 0.0))


def mat_look(forward, up=(0.0, 0.0, 1.0)):
    """Rotation that maps +Z to `forward` (local X goes to the side, local Y to the projected up)."""
    f = norm(forward)
    u = up
    if abs(dot(f, u)) > 0.999:
        u = (1.0, 0.0, 0.0)
    x = norm(cross(u, f))
    y = cross(f, x)
    return ((x[0], y[0], f[0], 0.0), (x[1], y[1], f[1], 0.0), (x[2], y[2], f[2], 0.0))


# --------------------------------------------------------------------------------------------------- mesh

class Chart:
    """A UV island in yards. weight scales its texel density (2.0 = twice the texels per yard)."""

    __slots__ = ("w", "h", "weight", "name", "fixed", "min_px")

    def __init__(self, w, h, weight=1.0, name=""):
        self.w = max(float(w), 1e-4)
        self.h = max(float(h), 1e-4)
        self.weight = weight
        self.name = name
        self.fixed = None   # (x, y, w, h) atlas texels, set by uv_region
        self.min_px = 4

    def copy(self):
        c = Chart(self.w, self.h, self.weight, self.name)
        c.fixed = self.fixed
        c.min_px = self.min_px
        return c


class Mesh:
    """Positions, normals, chart coordinates and triangles. `c[i]` is vertex i's chart, `st[i]` its (s, t)."""

    def __init__(self):
        self.p = []
        self.n = []
        self.c = []
        self.st = []
        self.t = []
        self.charts = []

    def copy(self):
        m = Mesh()
        m.p = list(self.p)
        m.n = list(self.n)
        m.c = list(self.c)
        m.st = list(self.st)
        m.t = list(self.t)
        m.charts = [ch.copy() for ch in self.charts]
        return m

    def chart(self, w, h, name=""):
        self.charts.append(Chart(w, h, 1.0, name))
        return len(self.charts) - 1

    def vert(self, p, n, chart, s, t):
        self.p.append((float(p[0]), float(p[1]), float(p[2])))
        self.n.append(n)
        self.c.append(chart)
        self.st.append((float(s), float(t)))
        return len(self.p) - 1

    def tri(self, a, b, c):
        pa, pb, pc = self.p[a], self.p[b], self.p[c]
        if length(cross(sub(pb, pa), sub(pc, pa))) < 1e-12:
            return  # degenerate (poles of a lathe, collapsed rings)
        self.t.append((a, b, c))

    @property
    def triangles(self):
        return len(self.t)

    def bounds(self):
        if not self.p:
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        xs = [p[0] for p in self.p]
        ys = [p[1] for p in self.p]
        zs = [p[2] for p in self.p]
        return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))

    def set_weight(self, w):
        for ch in self.charts:
            ch.weight = w
        return self


def merge(meshes):
    out = Mesh()
    for m in meshes:
        base = len(out.p)
        cbase = len(out.charts)
        out.p.extend(m.p)
        out.n.extend(m.n)
        out.c.extend(c + cbase for c in m.c)
        out.st.extend(m.st)
        out.t.extend((a + base, b + base, c + base) for a, b, c in m.t)
        out.charts.extend(ch.copy() for ch in m.charts)
    return out


def transform(mesh, m):
    out = mesh.copy()
    nm = mat_normal(m)
    out.p = [mat_apply(m, p) for p in mesh.p]
    out.n = [norm(mat_apply_dir(nm, n)) for n in mesh.n]
    if mat_det3(m) < 0:
        out.t = [(a, c, b) for a, b, c in out.t]
    return out


def translate(mesh, x, y, z):
    return transform(mesh, mat_translate(x, y, z))


def mirror_y(mesh):
    return transform(mesh, mat_scale(1.0, -1.0, 1.0))


def signed_volume(mesh):
    v = 0.0
    for a, b, c in mesh.t:
        v += dot(mesh.p[a], cross(mesh.p[b], mesh.p[c]))
    return v / 6.0


def face_normal(mesh, tri):
    a, b, c = tri
    return cross(sub(mesh.p[b], mesh.p[a]), sub(mesh.p[c], mesh.p[a]))


def _key(p):
    return (round(p[0], 5), round(p[1], 5), round(p[2], 5))


def recompute_normals(mesh, angle=40.0):
    """Normals from the faces, smooth across faces within `angle` degrees (also across chart seams, by welding
    equal positions) and hard beyond. Splits vertices where a corner needs its own normal."""
    cos_t = math.cos(math.radians(angle))
    fn = [face_normal(mesh, t) for t in mesh.t]
    fu = [norm(n) for n in fn]
    groups = {}
    for fi, tri in enumerate(mesh.t):
        for v in tri:
            groups.setdefault(_key(mesh.p[v]), []).append(fi)
    newp, newn, newc, newst = [], [], [], []
    remap = {}
    tris = []
    for fi, tri in enumerate(mesh.t):
        out = []
        for v in tri:
            acc = (0.0, 0.0, 0.0)
            for fj in groups[_key(mesh.p[v])]:
                if dot(fu[fj], fu[fi]) >= cos_t:
                    acc = add(acc, fn[fj])
            n = norm(acc)
            k = (v, round(n[0], 4), round(n[1], 4), round(n[2], 4))
            idx = remap.get(k)
            if idx is None:
                idx = len(newp)
                remap[k] = idx
                newp.append(mesh.p[v])
                newn.append(n)
                newc.append(mesh.c[v])
                newst.append(mesh.st[v])
            out.append(idx)
        tris.append(tuple(out))
    mesh.p, mesh.n, mesh.c, mesh.st, mesh.t = newp, newn, newc, newst, tris
    return mesh


def default_sides(r):
    """Section 5.4 side counts by radius."""
    if r < 0.03:
        return 6
    if r < 0.1:
        return 8
    if r < 0.2:
        return 12
    if r < 0.3:
        return 16
    return 20


# ----------------------------------------------------------------------------------------------- box

BOX_FACES = {
    # name: (normal, s axis (right seen from outside), t axis (down seen from outside))
    "+x": ((1, 0, 0), (0, 1, 0), (0, 0, -1)),
    "-x": ((-1, 0, 0), (0, -1, 0), (0, 0, -1)),
    "+y": ((0, 1, 0), (-1, 0, 0), (0, 0, -1)),
    "-y": ((0, -1, 0), (1, 0, 0), (0, 0, -1)),
    "+z": ((0, 0, 1), (0, 1, 0), (1, 0, 0)),
    "-z": ((0, 0, -1), (0, 1, 0), (-1, 0, 0)),
}


def _lines(half, b, segs):
    if b <= 0 or b >= half:
        return [-half, half]
    out = [-half]
    for k in range(1, segs):
        out.append(-half + b * k / segs)
    out.append(-half + b)
    out.append(half - b)
    for k in range(1, segs):
        out.append(half - b + b * k / segs)
    out.append(half)
    return out


def box(w, d, h, bevel=0.0, segs=1, faces="+x -x +y -y +z -z", z0=0.0):
    """A box W (along Y) x D (along X) x H, base at z0, centred on X and Y. `bevel` rounds every edge and corner
    with radius `bevel` (each half of the round gets `segs` steps); every face is its own chart."""
    hx, hy, hz = d / 2.0, w / 2.0, h / 2.0
    cz = z0 + hz
    b = max(0.0, min(bevel, hx * 0.999, hy * 0.999, hz * 0.999))
    inner = (hx - b, hy - b, hz - b)
    half = (hx, hy, hz)
    mesh = Mesh()
    for name in faces.split():
        nrm, sa, ta = BOX_FACES[name]
        ai = [i for i in range(3) if nrm[i]][0]
        si = [i for i in range(3) if sa[i]][0]
        ti = [i for i in range(3) if ta[i]][0]
        hs, ht, hn = half[si], half[ti], half[ai]
        ls = _lines(hs, b, segs)
        lt = _lines(ht, b, segs)
        ch = mesh.chart(2 * hs, 2 * ht, name)
        idx = {}
        for j, tv in enumerate(lt):
            for i, sv in enumerate(ls):
                q = [0.0, 0.0, 0.0]
                q[ai] = nrm[ai] * hn
                q[si] = sa[si] * sv
                q[ti] = ta[ti] * tv
                inn = [max(-inner[k], min(inner[k], q[k])) for k in range(3)]
                dv = (q[0] - inn[0], q[1] - inn[1], q[2] - inn[2])
                dl = length(dv)
                if b > 0 and dl > 1e-12:
                    nn = (dv[0] / dl, dv[1] / dl, dv[2] / dl)
                    pos = (inn[0] + nn[0] * b, inn[1] + nn[1] * b, inn[2] + nn[2] * b)
                else:
                    nn = (float(nrm[0]), float(nrm[1]), float(nrm[2]))
                    pos = (q[0], q[1], q[2])
                idx[(i, j)] = mesh.vert((pos[0], pos[1], pos[2] + cz), nn, ch, sv + hs, tv + ht)
        for j in range(len(lt) - 1):
            for i in range(len(ls) - 1):
                tl, tr = idx[(i, j)], idx[(i + 1, j)]
                bl, br = idx[(i, j + 1)], idx[(i + 1, j + 1)]
                mesh.tri(bl, br, tr)
                mesh.tri(bl, tr, tl)
    return mesh


# --------------------------------------------------------------------------------------- lathe family

def _disc(mesh, z, r, sides, up, seam, cx=0.0, cy=0.0, name="cap"):
    ch = mesh.chart(2 * r, 2 * r, name)
    n = (0.0, 0.0, 1.0 if up else -1.0)
    if up:
        c = mesh.vert((cx, cy, z), n, ch, r, r)
    else:
        c = mesh.vert((cx, cy, z), n, ch, r, r)
    ring = []
    for i in range(sides):
        a = seam + TAU * i / sides
        x, y = math.cos(a) * r, math.sin(a) * r
        # top seen from above, front (+X) toward the bottom of the image: s along +Y, t along +X
        s, t = (y + r, x + r) if up else (y + r, r - x)
        ring.append(mesh.vert((cx + x, cy + y, z), n, ch, s, t))
    for i in range(sides):
        a, b2 = ring[i], ring[(i + 1) % sides]
        if up:
            mesh.tri(c, a, b2)
        else:
            mesh.tri(c, b2, a)


def lathe(profile, sides=None, smooth=True, cap_bottom=False, cap_top=False, seam=math.pi, angle=40.0,
          name="lathe"):
    """Revolve [(r, z), ...] (ordered so the solid is on the inner side, e.g. bottom to top for an outer wall)
    around +Z. Profile corners sharper than `angle` get a hard edge. Planar caps close the ends when asked."""
    if sides is None:
        sides = default_sides(max(r for r, _ in profile))
    pts = []
    for r, z in profile:
        if not pts or math.hypot(r - pts[-1][0], z - pts[-1][1]) > 1e-9:
            pts.append((float(r), float(z)))
    segn = []
    for k in range(len(pts) - 1):
        dr = pts[k + 1][0] - pts[k][0]
        dz = pts[k + 1][1] - pts[k][1]
        ln = math.hypot(dr, dz) or 1.0
        segn.append((dz / ln, -dr / ln))
    rings = []  # (point index, (nr, nz), arclen)
    arc = [0.0]
    for k in range(1, len(pts)):
        arc.append(arc[-1] + math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]))
    total = arc[-1]
    cos_t = math.cos(math.radians(angle))
    for k in range(len(pts)):
        if k == 0:
            rings.append((k, segn[0], "start"))
        elif k == len(pts) - 1:
            rings.append((k, segn[-1], "end"))
        else:
            a, b = segn[k - 1], segn[k]
            if smooth and a[0] * b[0] + a[1] * b[1] >= cos_t:
                nr, nz = a[0] + b[0], a[1] + b[1]
                ln = math.hypot(nr, nz) or 1.0
                rings.append((k, (nr / ln, nz / ln), "both"))
            else:
                rings.append((k, a, "in"))
                rings.append((k, b, "out"))
    rmax = max(r for r, _ in pts)
    mesh = Mesh()
    ch = mesh.chart(TAU * max(rmax, 1e-3), max(total, 1e-3), name)
    vid = []
    for k, (nr, nz), _role in rings:
        r, z = pts[k]
        row = []
        for i in range(sides + 1):
            a = seam + TAU * i / sides
            ca, sa = math.cos(a), math.sin(a)
            row.append(mesh.vert((ca * r, sa * r, z), (ca * nr, sa * nr, nz), ch,
                                 mesh.charts[ch].w * i / sides, total - arc[k]))
        vid.append((k, row, _role))
    # connect consecutive rings that span a segment
    for q in range(len(vid) - 1):
        k0, r0, role0 = vid[q]
        k1, r1, role1 = vid[q + 1]
        if k0 == k1:
            continue  # hard-edge duplicate pair
        for i in range(sides):
            mesh.tri(r0[i], r0[i + 1], r1[i + 1])
            mesh.tri(r0[i], r1[i + 1], r1[i])
    if cap_bottom and pts[0][0] > 1e-6:
        _disc(mesh, pts[0][1], pts[0][0], sides, False, seam, name=name + "_bottom")
    if cap_top and pts[-1][0] > 1e-6:
        _disc(mesh, pts[-1][1], pts[-1][0], sides, True, seam, name=name + "_top")
    return mesh


def cylinder(r, h, sides=None, caps=True, seam=math.pi, z0=0.0):
    sides = sides or default_sides(r)
    if caps is True:
        caps = (True, True)
    elif caps is False:
        caps = (False, False)
    m = lathe([(r, z0), (r, z0 + h)], sides, cap_bottom=caps[0], cap_top=caps[1], seam=seam, name="cyl")
    return m


def cone(r0, r1, h, sides=None, caps=True, seam=math.pi, z0=0.0):
    sides = sides or default_sides(max(r0, r1))
    if caps is True:
        caps = (True, True)
    elif caps is False:
        caps = (False, False)
    return lathe([(r0, z0), (r1, z0 + h)], sides, cap_bottom=caps[0], cap_top=caps[1], seam=seam, name="cone")


def sphere(r, sides=None, rings=None, z0=None):
    """Sphere centred at the origin (or with its bottom at z0)."""
    sides = sides or default_sides(r)
    rings = rings or max(4, sides // 2)
    zc = 0.0 if z0 is None else z0 + r
    prof = []
    for k in range(rings + 1):
        a = -math.pi / 2 + math.pi * k / rings
        prof.append((max(0.0, math.cos(a) * r) if 0 < k < rings else 0.0, zc + math.sin(a) * r))
    return lathe(prof, sides, smooth=True, angle=89.0, name="sphere")


def capsule(r, length_, sides=None, rings=3):
    """Capsule along +Z from 0 to length_ (end caps included in the length)."""
    sides = sides or default_sides(r)
    body = max(0.0, length_ - 2 * r)
    prof = []
    for k in range(rings + 1):
        a = -math.pi / 2 + (math.pi / 2) * k / rings
        prof.append((math.cos(a) * r if k else 0.0, r + math.sin(a) * r))
    for k in range(rings + 1):
        a = (math.pi / 2) * k / rings
        prof.append((math.cos(a) * r if k < rings else 0.0, r + body + math.sin(a) * r))
    return lathe(prof, sides, smooth=True, angle=89.0, name="capsule")


def dome(r, h, rings=4, sides=None, z0=0.0):
    """Elliptic dome (a squashed hemisphere): radius r at z0 rising to the pole at z0 + h."""
    sides = sides or default_sides(r)
    prof = []
    for k in range(rings + 1):
        a = (math.pi / 2) * k / rings
        prof.append((math.cos(a) * r if k < rings else 0.0, z0 + math.sin(a) * h))
    return lathe(prof, sides, smooth=True, angle=89.0, name="dome")


def torus(R, r, sides=None, rings=5, arc=TAU, rz=None, start=0.0, name="torus"):
    """Torus around +Z in the XY plane. `rz` makes the tube elliptic (half height rz, half depth r)."""
    sides = sides or max(8, default_sides(R))
    rz = r if rz is None else rz
    full = abs(arc - TAU) < 1e-9
    mesh = Mesh()
    ch = mesh.chart(arc * (R + r), TAU * max(r, rz), name)
    cols = sides + 1
    grid = []
    for i in range(cols):
        ph = start + arc * i / sides
        cp, sp = math.cos(ph), math.sin(ph)
        row = []
        for j in range(rings + 1):
            ps = TAU * j / rings
            cs, ss = math.cos(ps), math.sin(ps)
            pos = ((R + r * cs) * cp, (R + r * cs) * sp, rz * ss)
            nn = norm((cs / r * cp, cs / r * sp, ss / rz))
            row.append(mesh.vert(pos, nn, ch, mesh.charts[ch].w * i / sides, mesh.charts[ch].h * (1 - j / rings)))
        grid.append(row)
    for i in range(sides):
        for j in range(rings):
            a, b = grid[i][j], grid[i + 1][j]
            c, d = grid[i + 1][j + 1], grid[i][j + 1]
            mesh.tri(a, b, c)
            mesh.tri(a, c, d)
    if not full:
        pass  # open arcs end inside the parts they join (handles, bands)
    return mesh


# -------------------------------------------------------------------------------------------- sweep

def sweep(path, radius, sides=None, caps=(False, False), up=(0.0, 0.0, 1.0), name="sweep"):
    """A tube along a polyline. radius: a number or f(t) with t in [0, 1] along the path."""
    rf = radius if callable(radius) else (lambda _t, _r=radius: _r)
    pts = [tuple(float(v) for v in p) for p in path]
    n = len(pts)
    arcl = [0.0]
    for i in range(1, n):
        arcl.append(arcl[-1] + length(sub(pts[i], pts[i - 1])))
    total = arcl[-1] or 1.0
    rmax = max(rf(a / total) for a in arcl)
    sides = sides or default_sides(rmax)
    tang = []
    for i in range(n):
        if i == 0:
            t = sub(pts[1], pts[0])
        elif i == n - 1:
            t = sub(pts[-1], pts[-2])
        else:
            t = add(norm(sub(pts[i], pts[i - 1])), norm(sub(pts[i + 1], pts[i])))
        tang.append(norm(t))
    ref = up if abs(dot(norm(up), tang[0])) < 0.95 else (1.0, 0.0, 0.0)
    nrm = norm(sub(ref, mul(tang[0], dot(ref, tang[0]))))
    frames = []
    for i in range(n):
        t = tang[i]
        nrm = norm(sub(nrm, mul(t, dot(nrm, t))))
        frames.append((t, nrm, cross(t, nrm)))
    mesh = Mesh()
    ch = mesh.chart(TAU * rmax, total, name)
    rows = []
    for i in range(n):
        t, nv, bv = frames[i]
        r = rf(arcl[i] / total)
        row = []
        for k in range(sides + 1):
            a = TAU * k / sides
            d = add(mul(nv, math.cos(a)), mul(bv, math.sin(a)))
            row.append(mesh.vert(add(pts[i], mul(d, r)), d, ch, mesh.charts[ch].w * k / sides, arcl[i]))
        rows.append(row)
    for i in range(n - 1):
        r0, r1 = rows[i], rows[i + 1]
        for k in range(sides):
            mesh.tri(r0[k], r0[k + 1], r1[k + 1])
            mesh.tri(r0[k], r1[k + 1], r1[k])
    for end, on in ((0, caps[0]), (n - 1, caps[1])):
        if not on:
            continue
        t, nv, bv = frames[end]
        r = rf(arcl[end] / total)
        out = t if end else mul(t, -1.0)
        cch = mesh.chart(2 * r, 2 * r, name + "_cap")
        c = mesh.vert(pts[end], out, cch, r, r)
        ring = []
        for k in range(sides):
            a = TAU * k / sides
            d = add(mul(nv, math.cos(a)), mul(bv, math.sin(a)))
            ring.append(mesh.vert(add(pts[end], mul(d, r)), out, cch, r + r * math.cos(a), r + r * math.sin(a)))
        for k in range(sides):
            a, b = ring[k], ring[(k + 1) % sides]
            if end:
                mesh.tri(c, a, b)
            else:
                mesh.tri(c, b, a)
    return mesh


def arc_path(center, radius, a0, a1, steps, plane=("x", "z")):
    """Points on a circular arc in a coordinate plane (angles in radians, measured from the first axis)."""
    ax = {"x": 0, "y": 1, "z": 2}
    i, j = ax[plane[0]], ax[plane[1]]
    out = []
    for k in range(steps + 1):
        a = a0 + (a1 - a0) * k / steps
        p = list(center)
        p[i] += math.cos(a) * radius
        p[j] += math.sin(a) * radius
        out.append(tuple(p))
    return out


def bezier_path(p0, p1, p2, p3, steps=8):
    out = []
    for k in range(steps + 1):
        t = k / steps
        u = 1 - t
        out.append(tuple(u * u * u * p0[i] + 3 * u * u * t * p1[i] + 3 * u * t * t * p2[i] + t * t * t * p3[i]
                         for i in range(3)))
    return out


def polyline_join(*paths):
    out = []
    for p in paths:
        for q in p:
            if not out or length(sub(out[-1], q)) > 1e-6:
                out.append(tuple(q))
    return out


# ------------------------------------------------------------------------------------------ extrude

def _area2(poly):
    a = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        a += x0 * y1 - x1 * y0
    return a


def triangulate(poly):
    """Ear clipping for a simple CCW polygon: list of index triples."""
    idx = list(range(len(poly)))
    if _area2(poly) < 0:
        idx.reverse()
    out = []

    def inside(p, a, b, c):
        def s(p1, p2, p3):
            return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
        d1, d2, d3 = s(p, a, b), s(p, b, c), s(p, c, a)
        neg = d1 < 0 or d2 < 0 or d3 < 0
        pos = d1 > 0 or d2 > 0 or d3 > 0
        return not (neg and pos)

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        found = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            cr = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if cr <= 1e-12:
                continue
            if any(inside(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            out.append((i0, i1, i2))
            idx.pop(k)
            found = True
            break
        if not found:
            break
    if len(idx) == 3:
        out.append(tuple(idx))
    return out


def inset_polygon(poly, d):
    """Moves every edge of a CCW polygon inward by d."""
    n = len(poly)
    out = []
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        e1 = (p1[0] - p0[0], p1[1] - p0[1])
        e2 = (p2[0] - p1[0], p2[1] - p1[1])
        l1 = math.hypot(*e1) or 1.0
        l2 = math.hypot(*e2) or 1.0
        n1 = (e1[1] / l1, -e1[0] / l1)
        n2 = (e2[1] / l2, -e2[0] / l2)
        k = 1.0 + n1[0] * n2[0] + n1[1] * n2[1]
        k = max(k, 0.2)
        out.append((p1[0] - d * (n1[0] + n2[0]) / k, p1[1] - d * (n1[1] + n2[1]) / k))
    return out


def extrude(polygon, depth, bevel=0.0, back=True, name="extrude"):
    """Extrudes a CCW polygon (XY) along +Z from 0 to depth; the front cap (z = depth) is inset by `bevel` with
    a chamfer strip. Charts: front, back, sides (one belt)."""
    poly = [(float(x), float(y)) for x, y in polygon]
    if _area2(poly) < 0:
        poly.reverse()
    n = len(poly)
    b = max(0.0, min(bevel, depth * 0.9))
    front = inset_polygon(poly, b) if b > 0 else poly
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    mesh = Mesh()
    per = [0.0]
    for i in range(n):
        per.append(per[-1] + math.hypot(poly[(i + 1) % n][0] - poly[i][0], poly[(i + 1) % n][1] - poly[i][1]))
    zs = depth - b
    cl = b * math.sqrt(2.0)
    # side belt (+ chamfer strip in the same chart); t runs from the front edge (0) back to z = 0
    belt = mesh.chart(per[-1], zs + cl, name + "_side")
    for i in range(n):
        a, c = poly[i], poly[(i + 1) % n]
        fa, fc = front[i], front[(i + 1) % n]
        en = norm((c[1] - a[1], -(c[0] - a[0]), 0.0))
        v0 = mesh.vert((a[0], a[1], 0.0), en, belt, per[i], zs + cl)
        v1 = mesh.vert((c[0], c[1], 0.0), en, belt, per[i + 1], zs + cl)
        v2 = mesh.vert((c[0], c[1], zs), en, belt, per[i + 1], cl)
        v3 = mesh.vert((a[0], a[1], zs), en, belt, per[i], cl)
        mesh.tri(v0, v1, v2)
        mesh.tri(v0, v2, v3)
        if b > 0:
            cn = norm((en[0], en[1], 1.0))
            w0 = mesh.vert((a[0], a[1], zs), cn, belt, per[i], cl)
            w1 = mesh.vert((c[0], c[1], zs), cn, belt, per[i + 1], cl)
            w2 = mesh.vert((fc[0], fc[1], depth), cn, belt, per[i + 1], 0.0)
            w3 = mesh.vert((fa[0], fa[1], depth), cn, belt, per[i], 0.0)
            mesh.tri(w0, w1, w2)
            mesh.tri(w0, w2, w3)
    tris = triangulate(front)
    fch = mesh.chart(x1 - x0, y1 - y0, name + "_front")
    # front seen from +Z: s along +X... (the caller orients the result)
    fv = [mesh.vert((p[0], p[1], depth), (0.0, 0.0, 1.0), fch, p[0] - x0, y1 - p[1]) for p in front]
    for a, b2, c in tris:
        mesh.tri(fv[a], fv[b2], fv[c])
    if back:
        bch = mesh.chart(x1 - x0, y1 - y0, name + "_back")
        bv = [mesh.vert((p[0], p[1], 0.0), (0.0, 0.0, -1.0), bch, x1 - p[0], y1 - p[1]) for p in poly]
        for a, b2, c in triangulate(poly):
            mesh.tri(bv[a], bv[c], bv[b2])
    return recompute_normals(mesh, 40.0)


# Orientations for parts built along +Z that should face the model front (+X), keeping their decal charts
# upright as seen from the front (s to the right = +Y, t downward = -Z):
MAT_EXTRUDE_FRONT = ((0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0))  # extrude(): X->Y, Y->Z
MAT_DISC_FRONT = mat_rot_y(math.pi / 2)  # lathe/cylinder caps: local +Y -> +Y, local +X -> -Z


def star_polygon(points, r_out, r_in, phase=math.pi / 2):
    out = []
    for i in range(points * 2):
        a = phase + math.pi * i / points
        r = r_out if i % 2 == 0 else r_in
        out.append((math.cos(a) * r, math.sin(a) * r))
    return out


def circle_polygon(r, n, phase=0.0):
    return [(math.cos(phase + TAU * i / n) * r, math.sin(phase + TAU * i / n) * r) for i in range(n)]


def spokes(n, R, w, t, r0=0.0, phase=0.0):
    """n flat bars from radius r0 to R in the XY plane, width w, thickness t (centred on z = 0)."""
    parts = []
    for i in range(n):
        a = phase + TAU * i / n
        bar = box(w, R - r0, t, z0=-t / 2)
        bar = translate(bar, (R + r0) / 2, 0.0, 0.0)
        parts.append(transform(bar, mat_rot_z(a)))
    return merge(parts)


# ---------------------------------------------------------------------------------------- deformers

def taper(mesh, k, z0=None, z1=None, cx=0.0, cy=0.0):
    """Scales X and Y about (cx, cy) by 1 - k * u, u going 0..1 from z0 to z1 (default: the mesh's own range)."""
    (_, _, mz0), (_, _, mz1) = mesh.bounds()
    z0 = mz0 if z0 is None else z0
    z1 = mz1 if z1 is None else z1
    span = (z1 - z0) or 1.0
    out = mesh.copy()
    pts = []
    for x, y, z in mesh.p:
        u = max(0.0, min(1.0, (z - z0) / span))
        s = 1.0 - k * u
        pts.append((cx + (x - cx) * s, cy + (y - cy) * s, z))
    out.p = pts
    return recompute_normals(out, 40.0)


def lean(mesh, angle, axis="x"):
    """Shears the mesh so its top moves along +axis by tan(angle) per yard of height."""
    k = math.tan(angle)
    out = mesh.copy()
    if axis == "x":
        out.p = [(x + z * k, y, z) for x, y, z in mesh.p]
    else:
        out.p = [(x, y + z * k, z) for x, y, z in mesh.p]
    return recompute_normals(out, 40.0)


def bend(mesh, angle, axis="x"):
    """Bends the mesh around a horizontal axis so its top turns by `angle` (radians) toward +axis."""
    (x0, y0, z0), (x1, y1, z1) = mesh.bounds()
    h = (z1 - z0) or 1.0
    if abs(angle) < 1e-9:
        return mesh.copy()
    rad = h / angle
    out = mesh.copy()
    pts = []
    for x, y, z in mesh.p:
        a = (z - z0) / h * angle
        off = x if axis == "x" else y
        rr = rad - off
        no = rad - math.cos(a) * rr
        nz = z0 + math.sin(a) * rr
        pts.append((no, y, nz) if axis == "x" else (x, no, nz))
    out.p = pts
    return recompute_normals(out, 40.0)


def _hash3(ix, iy, iz, seed):
    h = (ix * 374761393 + iy * 668265263 + iz * 2147483647 + seed * 144665) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def _vnoise(x, y, z, seed):
    ix, iy, iz = math.floor(x), math.floor(y), math.floor(z)
    fx, fy, fz = x - ix, y - iy, z - iz
    fx, fy, fz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)
    acc = 0.0
    for dz in (0, 1):
        for dy in (0, 1):
            for dx in (0, 1):
                w = (fx if dx else 1 - fx) * (fy if dy else 1 - fy) * (fz if dz else 1 - fz)
                acc += w * _hash3(ix + dx, iy + dy, iz + dz, seed)
    return acc * 2.0 - 1.0


def wobble(mesh, amp, seed=1, freq=6.0):
    """Moves every vertex by up to `amp` yards with smooth noise of its position (seams stay closed), then
    recomputes the normals. Section 5.4: 0.5-2 cm."""
    out = mesh.copy()
    pts = []
    for x, y, z in mesh.p:
        dx = _vnoise(x * freq, y * freq, z * freq, seed)
        dy = _vnoise(x * freq + 17.1, y * freq, z * freq, seed + 1)
        dz = _vnoise(x * freq, y * freq + 31.7, z * freq, seed + 2)
        pts.append((x + dx * amp, y + dy * amp, z + dz * amp))
    out.p = pts
    return recompute_normals(out, 40.0)


def plank_edges(mesh, seed=1, amp=0.01, axis="y"):
    """Irregular board ends: shifts the vertices at the ends of `axis` by noise of the other coordinates."""
    (x0, y0, z0), (x1, y1, z1) = mesh.bounds()
    ai = 0 if axis == "x" else 1
    lo, hi = (x0, x1) if ai == 0 else (y0, y1)
    out = mesh.copy()
    pts = []
    for p in mesh.p:
        q = list(p)
        if abs(p[ai] - lo) < 1e-4 or abs(p[ai] - hi) < 1e-4:
            q[ai] += _vnoise(p[0] * 9 + p[2] * 7, p[1] * 9, p[2] * 9, seed) * amp
        pts.append(tuple(q))
    out.p = pts
    return recompute_normals(out, 40.0)


def sag(mesh, points, depth):
    """Lowers the mesh between support points (XY) by up to `depth`, zero at the supports."""
    out = mesh.copy()
    pts = []
    for x, y, z in mesh.p:
        d = min(math.hypot(x - px, y - py) for px, py in points)
        span = max(math.hypot(points[i][0] - points[j][0], points[i][1] - points[j][1])
                   for i in range(len(points)) for j in range(len(points))) / 2 or 1.0
        u = min(1.0, d / span)
        pts.append((x, y, z - depth * math.sin(u * math.pi / 2)))
    out.p = pts
    return recompute_normals(out, 40.0)


# ------------------------------------------------------------------------------------------ UV helpers

def uv_planar(mesh, axis="z", weight=None, name="planar"):
    """Replaces the charts with one planar projection along `axis` (seen from the + side)."""
    out = mesh.copy()
    (x0, y0, z0), (x1, y1, z1) = mesh.bounds()
    if axis == "z":
        w, h = y1 - y0, x1 - x0
        f = lambda p: (p[1] - y0, p[0] - x0)  # noqa: E731
    elif axis == "x":
        w, h = y1 - y0, z1 - z0
        f = lambda p: (p[1] - y0, z1 - p[2])  # noqa: E731
    else:
        w, h = x1 - x0, z1 - z0
        f = lambda p: (x1 - p[0], z1 - p[2])  # noqa: E731
    out.charts = [Chart(w, h, weight if weight is not None else (mesh.charts[0].weight if mesh.charts else 1.0),
                        name)]
    out.c = [0] * len(out.p)
    out.st = [f(p) for p in out.p]
    return out


def uv_region(mesh, rect):
    """Pins every chart of the mesh into the atlas rectangle rect = (x, y, w, h) texels (the packer then lays
    the charts out inside it)."""
    for ch in mesh.charts:
        ch.fixed = tuple(rect)
    return mesh


def uv_box(mesh, weight=1.0):
    """Re-charts a mesh by box projection: each triangle goes to the face of its dominant normal axis."""
    out = Mesh()
    names = ["+x", "-x", "+y", "-y", "+z", "-z"]
    (x0, y0, z0), (x1, y1, z1) = mesh.bounds()
    dims = {"+x": (y1 - y0, z1 - z0), "-x": (y1 - y0, z1 - z0), "+y": (x1 - x0, z1 - z0),
            "-y": (x1 - x0, z1 - z0), "+z": (y1 - y0, x1 - x0), "-z": (y1 - y0, x1 - x0)}
    cid = {}
    for nm in names:
        cid[nm] = len(out.charts)
        out.charts.append(Chart(dims[nm][0], dims[nm][1], weight, nm))

    def st(nm, p):
        if nm == "+x":
            return (p[1] - y0, z1 - p[2])
        if nm == "-x":
            return (y1 - p[1], z1 - p[2])
        if nm == "+y":
            return (x1 - p[0], z1 - p[2])
        if nm == "-y":
            return (p[0] - x0, z1 - p[2])
        if nm == "+z":
            return (p[1] - y0, p[0] - x0)
        return (p[1] - y0, x1 - p[0])

    remap = {}
    for tri in mesh.t:
        fn = face_normal(mesh, tri)
        ax = max(range(3), key=lambda i: abs(fn[i]))
        nm = ("+" if fn[ax] > 0 else "-") + "xyz"[ax]
        newt = []
        for v in tri:
            k = (v, nm)
            if k not in remap:
                remap[k] = out.vert(mesh.p[v], mesh.n[v], cid[nm], *st(nm, mesh.p[v]))
            newt.append(remap[k])
        out.t.append(tuple(newt))
    # drop unused charts
    used = sorted(set(out.c))
    m = {c: i for i, c in enumerate(used)}
    out.charts = [out.charts[c] for c in used]
    out.c = [m[c] for c in out.c]
    return out


def uv_cyl(mesh, weight=1.0, name="cyl"):
    """One cylindrical chart around +Z (seam at -X)."""
    out = Mesh()
    (x0, y0, z0), (x1, y1, z1) = mesh.bounds()
    r = max(max(abs(x0), abs(x1)), max(abs(y0), abs(y1)), 1e-3)
    w = TAU * r
    out.charts = [Chart(w, z1 - z0, weight, name)]
    for tri in mesh.t:
        angs = []
        for v in tri:
            x, y, _ = mesh.p[v]
            a = math.atan2(y, x) - math.pi
            while a < 0:
                a += TAU
            angs.append(a)
        if max(angs) - min(angs) > math.pi:
            angs = [a + TAU if a < math.pi else a for a in angs]
        ids = []
        for v, a in zip(tri, angs):
            ids.append(out.vert(mesh.p[v], mesh.n[v], 0, a / TAU * w, z1 - mesh.p[v][2]))
        out.t.append(tuple(ids))
    out.charts[0].w = max([w] + [s for s, _ in out.st])
    return out
