"""Texture-space light bake (CAFE.SPEC.md section 5.5, "The bake").

1. Every UV island is rasterized in texel space: each covered texel gets its model-space position and normal,
   its chart coordinates, part and chart (islands are unique, so no texel belongs to two places).
2. Light terms, multiplied into the painted colour:
   (a) ambient occlusion from 32 cosine-weighted rays per sample against the model's own triangles and the floor
       plane z = 0 (the bar top or the floor), through a uniform grid accelerator, with a fixed seed. Samples
       are taken every `ao_step` texels inside each island and interpolated within the island (occlusion is
       low-frequency); islands smaller than the step are sampled per texel;
   (b) a vertical gradient (about +15 % at the top, -25 % at the base) and a key light from above;
   (c) convex-edge highlights and concave-edge darkening: from the smooth normals' curvature and from the
       dihedral angle of hard edges (the curvature value also drives the paints' edge wear);
   (d) contact darkening near z = 0, on top of what the occlusion rays find where parts meet.
3. --no-bake skips all of it (light factor 1, no curvature or occlusion): the unbaked copy for the owner's
   bake on/off comparison.
Deterministic: every random direction comes from a hash of the sample index.
"""

import math
import multiprocessing
import os

from . import geom as G

AO_RAYS = 32
AO_DIST = 0.22
KEY_DIR = G.norm((0.35, 0.25, 1.0))


# ------------------------------------------------------------------------------------------- rasterize

class TexelData:
    """Per-texel arrays for one atlas (index = y * w + x). Empty texels have chart -1."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        n = w * h
        self.chart = [-1] * n
        self.part = [-1] * n
        self.pos = [None] * n
        self.nrm = [None] * n
        self.st = [None] * n
        self.curv = [0.0] * n
        self.score = [-1e9] * n
        self.ao = [1.0] * n

    def covered(self):
        return [i for i, c in enumerate(self.chart) if c >= 0]


def vertex_curvature(mesh):
    """Mean curvature-like value per vertex from the smooth normals: k = <n_j - n_i, p_j - p_i> / |p_j - p_i|^2
    averaged over the vertex's edges (positive on convex rounds, about 1/radius)."""
    acc = [0.0] * len(mesh.p)
    cnt = [0] * len(mesh.p)
    for tri in mesh.t:
        for k in range(3):
            i, j = tri[k], tri[(k + 1) % 3]
            pi, pj = mesh.p[i], mesh.p[j]
            d = G.sub(pj, pi)
            ll = G.dot(d, d)
            if ll < 1e-12:
                continue
            kv = G.dot(G.sub(mesh.n[j], mesh.n[i]), d) / ll
            acc[i] += kv
            acc[j] += kv
            cnt[i] += 1
            cnt[j] += 1
    return [acc[i] / cnt[i] if cnt[i] else 0.0 for i in range(len(acc))]


def hard_edges(mesh, angle=35.0):
    """{(tri index, edge k): signed strength} for edges whose neighbour face turns by more than `angle` degrees.
    Edge k joins vertex k and k+1. Positive = convex."""
    def key(p):
        return (round(p[0], 5), round(p[1], 5), round(p[2], 5))
    emap = {}
    for ti, tri in enumerate(mesh.t):
        for k in range(3):
            a, b = key(mesh.p[tri[k]]), key(mesh.p[tri[(k + 1) % 3]])
            emap.setdefault((min(a, b), max(a, b)), []).append((ti, k))
    fn = [G.norm(G.face_normal(mesh, t)) for t in mesh.t]
    cent = [G.mul(G.add(G.add(mesh.p[t[0]], mesh.p[t[1]]), mesh.p[t[2]]), 1 / 3.0) for t in mesh.t]
    cos_t = math.cos(math.radians(angle))
    out = {}
    for _e, users in emap.items():
        if len(users) != 2:
            continue
        (t0, k0), (t1, k1) = users
        c = G.dot(fn[t0], fn[t1])
        if c > cos_t:
            continue
        ang = math.acos(max(-1.0, min(1.0, c)))
        strength = min(1.0, ang / (math.pi / 2))
        # convex when the other face's centroid lies behind this face's plane
        p0 = mesh.p[mesh.t[t0][k0]]
        convex = G.dot(fn[t0], G.sub(cent[t1], p0)) < 0
        sgn = 1.0 if convex else -1.0
        out[(t0, k0)] = sgn * strength
        out[(t1, k1)] = sgn * strength
    return out


def rasterize(td, mesh, uvs_px, part_id, chart_offset, curv_scale=0.022, edge_width=0.018):
    """Rasterizes one part (mesh with per-vertex texel-space uvs) into td. Conservative by half a texel:
    edge texels go to the triangle that contains them most."""
    vk = vertex_curvature(mesh)
    hard = hard_edges(mesh)
    w, h = td.w, td.h
    for ti, (ia, ib, ic) in enumerate(mesh.t):
        (ax, ay), (bx, by), (cx, cy) = uvs_px[ia], uvs_px[ib], uvs_px[ic]
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(area) < 1e-9:
            continue
        x0 = max(0, int(math.floor(min(ax, bx, cx) - 1)))
        x1 = min(w - 1, int(math.ceil(max(ax, bx, cx) + 1)))
        y0 = max(0, int(math.floor(min(ay, by, cy) - 1)))
        y1 = min(h - 1, int(math.ceil(max(ay, by, cy) + 1)))
        inv = 1.0 / area
        # edge lengths in texels, for the conservative margin
        la = math.hypot(cx - bx, cy - by) or 1.0
        lb = math.hypot(ax - cx, ay - cy) or 1.0
        lc = math.hypot(bx - ax, by - ay) or 1.0
        pa, pb, pc = mesh.p[ia], mesh.p[ib], mesh.p[ic]
        na, nb, nc = mesh.n[ia], mesh.n[ib], mesh.n[ic]
        sa, sb, sc = mesh.st[ia], mesh.st[ib], mesh.st[ic]
        ka, kb, kc = vk[ia], vk[ib], vk[ic]
        chart = chart_offset + mesh.c[ia]
        # model-space altitudes for the hard-edge falloff
        area3 = G.length(G.cross(G.sub(pb, pa), G.sub(pc, pa)))
        e_len = [G.length(G.sub(pb, pa)), G.length(G.sub(pc, pb)), G.length(G.sub(pa, pc))]
        edges = [hard.get((ti, k), 0.0) for k in range(3)]
        any_edge = any(edges)
        for y in range(y0, y1 + 1):
            py = y + 0.5
            for x in range(x0, x1 + 1):
                px = x + 0.5
                wa = ((bx - px) * (cy - py) - (by - py) * (cx - px)) * inv
                wb = ((cx - px) * (ay - py) - (cy - py) * (ax - px)) * inv
                wc = 1.0 - wa - wb
                # signed distance (texels) to each edge: w_k * altitude_k
                da = wa * abs(area) / la
                db = wb * abs(area) / lb
                dc = wc * abs(area) / lc
                score = min(da, db, dc)
                if score < -0.75:
                    continue
                i = y * w + x
                if score <= td.score[i]:
                    continue
                if score < 0:
                    # clamp to the triangle for interpolation
                    wa, wb, wc = max(wa, 0.0), max(wb, 0.0), max(wc, 0.0)
                    s = wa + wb + wc
                    wa, wb, wc = wa / s, wb / s, wc / s
                td.score[i] = score
                td.chart[i] = chart
                td.part[i] = part_id
                td.pos[i] = (pa[0] * wa + pb[0] * wb + pc[0] * wc, pa[1] * wa + pb[1] * wb + pc[1] * wc,
                             pa[2] * wa + pb[2] * wb + pc[2] * wc)
                td.nrm[i] = G.norm((na[0] * wa + nb[0] * wb + nc[0] * wc, na[1] * wa + nb[1] * wb + nc[1] * wc,
                                    na[2] * wa + nb[2] * wb + nc[2] * wc))
                td.st[i] = (sa[0] * wa + sb[0] * wb + sc[0] * wc, sa[1] * wa + sb[1] * wb + sc[1] * wc)
                cv = (ka * wa + kb * wb + kc * wc) * curv_scale
                if any_edge:
                    # edge k joins vertex k, k+1: its distance is the opposite vertex's weight * altitude
                    for k, wgt in ((0, wc), (1, wa), (2, wb)):
                        if edges[k]:
                            alt = area3 / (e_len[k] or 1.0)
                            d = wgt * alt
                            if d < edge_width:
                                cv += edges[k] * (1.0 - d / edge_width) ** 1.5
                td.curv[i] = max(-1.0, min(1.0, cv))


# ----------------------------------------------------------------------------------------- ray casting

class RayGrid:
    """Uniform grid over the occluder triangles; any-hit queries with a maximum distance."""

    def __init__(self, tris, cell=0.05):
        self.tris = []
        for a, b, c in tris:
            e1 = G.sub(b, a)
            e2 = G.sub(c, a)
            if G.length(G.cross(e1, e2)) < 1e-10:
                continue
            self.tris.append((a, e1, e2))
        pts = [p for t in tris for p in t] or [(0.0, 0.0, 0.0)]
        self.lo = tuple(min(p[i] for p in pts) - 1e-3 for i in range(3))
        self.hi = tuple(max(p[i] for p in pts) + 1e-3 for i in range(3))
        self.cell = cell
        self.n = tuple(max(1, int(math.ceil((self.hi[i] - self.lo[i]) / cell))) for i in range(3))
        self.cells = {}
        for ti, (a, e1, e2) in enumerate(self.tris):
            b = G.add(a, e1)
            c = G.add(a, e2)
            mn = [min(a[i], b[i], c[i]) for i in range(3)]
            mx = [max(a[i], b[i], c[i]) for i in range(3)]
            i0 = [max(0, int((mn[i] - self.lo[i]) / cell)) for i in range(3)]
            i1 = [min(self.n[i] - 1, int((mx[i] - self.lo[i]) / cell)) for i in range(3)]
            for ix in range(i0[0], i1[0] + 1):
                for iy in range(i0[1], i1[1] + 1):
                    for iz in range(i0[2], i1[2] + 1):
                        self.cells.setdefault((ix, iy, iz), []).append(ti)

    def hit(self, o, d, tmax):
        lo, cell, n = self.lo, self.cell, self.n
        # clip the ray to the grid box
        t0, t1 = 0.0, tmax
        for i in range(3):
            if abs(d[i]) < 1e-12:
                if o[i] < lo[i] or o[i] > self.hi[i]:
                    return False
                continue
            ta = (lo[i] - o[i]) / d[i]
            tb = (self.hi[i] - o[i]) / d[i]
            if ta > tb:
                ta, tb = tb, ta
            t0 = max(t0, ta)
            t1 = min(t1, tb)
            if t0 > t1:
                return False
        p = (o[0] + d[0] * t0, o[1] + d[1] * t0, o[2] + d[2] * t0)
        ix = min(n[0] - 1, max(0, int((p[0] - lo[0]) / cell)))
        iy = min(n[1] - 1, max(0, int((p[1] - lo[1]) / cell)))
        iz = min(n[2] - 1, max(0, int((p[2] - lo[2]) / cell)))
        step = [1 if d[i] > 0 else -1 for i in range(3)]
        tdelta = [abs(cell / d[i]) if abs(d[i]) > 1e-12 else 1e30 for i in range(3)]
        idx = [ix, iy, iz]
        tnext = []
        for i in range(3):
            if abs(d[i]) < 1e-12:
                tnext.append(1e30)
            else:
                edge = lo[i] + (idx[i] + (1 if d[i] > 0 else 0)) * cell
                tnext.append((edge - o[i]) / d[i])
        tested = set()
        tris = self.tris
        cells = self.cells
        ox, oy, oz = o
        dx, dy, dz = d
        while True:
            lst = cells.get((idx[0], idx[1], idx[2]))
            if lst:
                for ti in lst:
                    if ti in tested:
                        continue
                    tested.add(ti)
                    a, e1, e2 = tris[ti]
                    # Moller-Trumbore
                    px = dy * e2[2] - dz * e2[1]
                    py = dz * e2[0] - dx * e2[2]
                    pz = dx * e2[1] - dy * e2[0]
                    det = e1[0] * px + e1[1] * py + e1[2] * pz
                    if -1e-12 < det < 1e-12:
                        continue
                    inv = 1.0 / det
                    sx, sy, sz = ox - a[0], oy - a[1], oz - a[2]
                    u = (sx * px + sy * py + sz * pz) * inv
                    if u < 0.0 or u > 1.0:
                        continue
                    qx = sy * e1[2] - sz * e1[1]
                    qy = sz * e1[0] - sx * e1[2]
                    qz = sx * e1[1] - sy * e1[0]
                    v = (dx * qx + dy * qy + dz * qz) * inv
                    if v < 0.0 or u + v > 1.0:
                        continue
                    t = (e2[0] * qx + e2[1] * qy + e2[2] * qz) * inv
                    if 1e-5 < t < tmax:
                        return True
            # advance
            if tnext[0] < tnext[1] and tnext[0] < tnext[2]:
                k = 0
            elif tnext[1] < tnext[2]:
                k = 1
            else:
                k = 2
            if tnext[k] > t1:
                return False
            idx[k] += step[k]
            if idx[k] < 0 or idx[k] >= n[k]:
                return False
            tnext[k] += tdelta[k]


def _hammersley(n):
    out = []
    for i in range(n):
        u = (i + 0.5) / n
        bits = i
        bits = ((bits << 16) | (bits >> 16)) & 0xFFFFFFFF
        bits = (((bits & 0x55555555) << 1) | ((bits & 0xAAAAAAAA) >> 1)) & 0xFFFFFFFF
        bits = (((bits & 0x33333333) << 2) | ((bits & 0xCCCCCCCC) >> 2)) & 0xFFFFFFFF
        bits = (((bits & 0x0F0F0F0F) << 4) | ((bits & 0xF0F0F0F0) >> 4)) & 0xFFFFFFFF
        bits = (((bits & 0x00FF00FF) << 8) | ((bits & 0xFF00FF00) >> 8)) & 0xFFFFFFFF
        v = bits / 4294967296.0
        r = math.sqrt(u)
        a = 2 * math.pi * v
        out.append((r * math.cos(a), r * math.sin(a), math.sqrt(max(0.0, 1 - u))))
    return out


DIRS = _hammersley(AO_RAYS)


def _hash01(i, salt):
    h = (i * 2654435761 + salt * 40503) & 0xFFFFFFFF
    h = ((h ^ (h >> 16)) * 0x45D9F3B) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65536.0


def ao_at(grid, p, n, idx, floor=True, dist=AO_DIST):
    t = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    tx = G.norm(G.cross(n, t))
    ty = G.cross(n, tx)
    rot = _hash01(idx, 7) * 2 * math.pi
    cr, sr = math.cos(rot), math.sin(rot)
    o = (p[0] + n[0] * 0.003, p[1] + n[1] * 0.003, p[2] + n[2] * 0.003)
    hits = 0
    for lx, ly, lz in DIRS:
        rx = lx * cr - ly * sr
        ry = lx * sr + ly * cr
        d = (tx[0] * rx + ty[0] * ry + n[0] * lz, tx[1] * rx + ty[1] * ry + n[1] * lz,
             tx[2] * rx + ty[2] * ry + n[2] * lz)
        if floor and d[2] < -1e-6 and o[2] >= 0.0 and -o[2] / d[2] < dist:
            hits += 1
            continue
        if grid.hit(o, d, dist):
            hits += 1
    return 1.0 - hits / float(len(DIRS))


_JOB = {}


def _ao_chunk(args):
    lo, hi = args
    job = _JOB
    out = []
    for k in range(lo, hi):
        i, p, n = job["samples"][k]
        out.append(ao_at(job["grid"], p, n, i, job["floor"]))
    return out


def compute_ao(td, occluder_tris, step=4, floor=True, jobs=None):
    """Fills td.ao for every covered texel."""
    grid = RayGrid(occluder_tris)
    w = td.w
    samples = []
    sample_at = {}
    half = step // 2
    for i in td.covered():
        x, y = i % w, i // w
        if x % step == half and y % step == half:
            sample_at[i] = len(samples)
            samples.append((i, td.pos[i], td.nrm[i]))
    # texels without a same-chart grid sample nearby get their own sample
    extra = []
    for i in td.covered():
        if i in sample_at:
            continue
        x, y = i % w, i // w
        gx0 = ((x - half) // step) * step + half
        gy0 = ((y - half) // step) * step + half
        found = False
        for gy in (gy0, gy0 + step):
            for gx in (gx0, gx0 + step):
                if 0 <= gx < w and 0 <= gy < td.h:
                    j = gy * w + gx
                    if j in sample_at and td.chart[j] == td.chart[i]:
                        found = True
        if not found:
            extra.append(i)
    for i in extra:
        sample_at[i] = len(samples)
        samples.append((i, td.pos[i], td.nrm[i]))
    values = _run(samples, grid, floor, jobs)
    for i, k in sample_at.items():
        td.ao[i] = values[k]
    for i in td.covered():
        if i in sample_at:
            continue
        x, y = i % w, i // w
        gx0 = ((x - half) // step) * step + half
        gy0 = ((y - half) // step) * step + half
        acc = 0.0
        wsum = 0.0
        for gy in (gy0, gy0 + step):
            for gx in (gx0, gx0 + step):
                if not (0 <= gx < w and 0 <= gy < td.h):
                    continue
                j = gy * w + gx
                if j in sample_at and td.chart[j] == td.chart[i]:
                    wx = 1.0 - abs(x - gx) / step
                    wy = 1.0 - abs(y - gy) / step
                    wgt = max(1e-4, wx * wy)
                    acc += values[sample_at[j]] * wgt
                    wsum += wgt
        td.ao[i] = acc / wsum if wsum else 1.0
    return len(samples)


def _run(samples, grid, floor, jobs):
    global _JOB
    n = len(samples)
    if n == 0:
        return []
    _JOB = {"samples": samples, "grid": grid, "floor": floor}
    jobs = jobs or os.cpu_count() or 1
    chunk = max(64, n // (jobs * 8) + 1)
    ranges = [(a, min(n, a + chunk)) for a in range(0, n, chunk)]
    if jobs > 1 and n > 256 and "fork" in multiprocessing.get_all_start_methods():
        ctx = multiprocessing.get_context("fork")
        with ctx.Pool(jobs) as pool:
            parts = pool.map(_ao_chunk, ranges)
    else:
        parts = [_ao_chunk(r) for r in ranges]
    out = []
    for p in parts:
        out.extend(p)
    _JOB = {}
    return out


# ---------------------------------------------------------------------------------------- light factor

def light_factor(p, n, ao, curv, zmin, zmax, enable=True, contact=0.035, occ_min=0.0):
    """The baked light multiplier for one texel (1.0 when the bake is off). occ_min floors the occlusion term
    (a part's ao_floor: small light-coloured parts such as porcelain stay light in a crowded corner)."""
    if not enable:
        return 1.0
    zr = (p[2] - zmin) / (zmax - zmin) if zmax > zmin else 0.5
    zr = 0.0 if zr < 0 else (1.0 if zr > 1 else zr)
    grad = 0.75 + 0.40 * (zr * zr * (3 - 2 * zr))
    key = 0.80 + 0.30 * max(0.0, G.dot(n, KEY_DIR)) - 0.12 * max(0.0, -n[2])
    occ = max(occ_min, 0.30 + 0.70 * (ao ** 1.3))
    cv = 1.0 + (0.22 * curv if curv > 0 else 0.30 * curv)
    cont = 1.0
    if p[2] < contact:
        cont = 0.72 + 0.28 * (p[2] / contact)
    return grad * key * occ * cv * cont
