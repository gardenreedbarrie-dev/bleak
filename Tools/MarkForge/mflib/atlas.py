r"""The 512x512 component atlas of one model: what every texel is on the body.

Section rectangles at the 512 layout (s_sectionInfoRaw, WoW/Common/ComponentCore/CharacterComponent.cpp:171):

    AU arm upper (0,0) 256x128     TU torso upper (256,0) 256x128
    AL arm lower (0,128) 256x128   TL torso lower (256,128) 256x64
    HA hand (0,256) 256x64         LU leg upper (256,192) 256x128
    FU face upper (0,320) 256x64   LL leg lower (256,320) 256x128
    FL face lower (0,384) 256x128  FO foot (256,448) 256x64

Islands (measured on the HD models, see Tools/MarkForge/README.md): the arm island is AU+AL+HA (its u wraps around
the arm: u=0 meets u=255 on the inner arm), the body island is TU..FO (above the crotch row u=256 is the front
midline and u=511 the back midline, both mirror lines; below it u=256 meets u=511 on the inner leg), the head
island is FU+FL. Left and right share every body texel.

Seams are found the way the client's mesh has them: an edge between the same two 3D points that appears with
different UVs. A seam between the two ends of one island's rows is a wrap seam (continuity is gated); every other
seam, and every open mesh border away from the mirror plane, is a cut (marks fade out before it).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import MarkForgeError

N = 512
SECTIONS = {
    "AU": (0, 0, 256, 128), "AL": (0, 128, 256, 128), "HA": (0, 256, 256, 64),
    "FU": (0, 320, 256, 64), "FL": (0, 384, 256, 128),
    "TU": (256, 0, 256, 128), "TL": (256, 128, 256, 64), "LU": (256, 192, 256, 128),
    "LL": (256, 320, 256, 128), "FO": (256, 448, 256, 64),
}
SECTION_ORDER = ["AU", "AL", "HA", "TU", "TL", "LU", "LL", "FO", "FU", "FL"]  # the client's section enum order
ISLAND_ARM, ISLAND_BODY, ISLAND_HEAD = 1, 2, 3
HEAD_CUT_GUTTER = 4.0  # atlas texels next to a head-to-other-island cut also measured in the atlas (cut_distance)
NEIGHBOURS = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
              (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142))


def island_of(x, y):
    """Island id of atlas texel columns/rows (arrays or scalars)."""
    x = np.asarray(x)
    y = np.asarray(y)
    return np.where(x >= 256, ISLAND_BODY, np.where(y < 320, ISLAND_ARM, ISLAND_HEAD))


@dataclass
class Seam:
    kind: str  # "wrap", "cut" or "hand" (finger seams: continuous charts, not gated)
    a: tuple  # ((u0, v0), (u1, v1)) in texels: one side
    b: tuple  # the other side (same 3D edge)
    p: tuple = ()  # the edge's two 3D end points (x forward, |y|, z)


@dataclass
class Atlas:
    pos: np.ndarray  # (N, N, 3): x forward (sign applied), |y|-folded lateral is NOT applied here, z up
    nrm: np.ndarray
    geo: np.ndarray  # (N, N) geoset id, -1 where no body triangle lands
    cnt: np.ndarray  # how many triangles land on the texel (2 = mirrored)
    island: np.ndarray  # (N, N) 0 none, 1 arm, 2 body, 3 head
    seams: list = field(default_factory=list)
    open_edges: list = field(default_factory=list)  # ((u0, v0), (u1, v1)) borders with no partner, off the mirror plane
    open_points: list = field(default_factory=list)  # their 3D end points
    crotch: int = N
    cut_dist: np.ndarray | None = None  # texels to the nearest cut seam / open border, within the island
    keepout: np.ndarray | None = None  # bool: eyes, mouth, other geometry
    keepout_parts: dict = field(default_factory=dict)
    holes: list = field(default_factory=list)
    ext: np.ndarray | None = None  # texels within 1.6 texels outside the islands, with extrapolated pos/nrm
    island_ext: np.ndarray | None = None  # island of valid and ext texels

    @property
    def painted(self) -> np.ndarray:
        """Texels a design is evaluated on: the islands plus their extrapolated border."""
        return (self.geo >= 0) | self.ext

    @property
    def valid(self) -> np.ndarray:
        return self.geo >= 0


# --- rasterising --------------------------------------------------------------------------------------------------


def rasterise(model, tris=None, geos=None) -> Atlas:
    """Every naked body triangle into the atlas: per texel (centre sampled) the rest-pose position and normal. Where
    mirrored triangles share a texel the left (+y) one is kept."""
    if tris is None:
        tris, geos = model.body_tris()
    pos = np.zeros((N, N, 3), np.float64)
    nrm = np.zeros((N, N, 3), np.float64)
    geo = np.full((N, N), -1, np.int32)
    cnt = np.zeros((N, N), np.int32)
    P = model.pos.copy()
    P[:, 0] *= model.forward
    Nn = model.nrm.copy()
    Nn[:, 0] *= model.forward
    UV = model.uv * N
    for tri, g in zip(tris, geos):
        uv = UV[tri]
        x0, y0 = np.floor(uv.min(0)).astype(int)
        x1, y1 = np.ceil(uv.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, N), min(y1, N)
        if x1 <= x0 or y1 <= y0:
            continue
        a, b, c = uv
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        w0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        w1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        W = np.stack([w0, w1, w2], -1)[inside]
        yy = (ys[inside] - 0.5).astype(int)
        xx = (xs[inside] - 0.5).astype(int)
        p = W @ P[tri]
        n = W @ Nn[tri]
        keep = (cnt[yy, xx] == 0) | (p[:, 1] > pos[yy, xx, 1])
        pos[yy[keep], xx[keep]] = p[keep]
        nrm[yy[keep], xx[keep]] = n[keep]
        geo[yy[keep], xx[keep]] = g
        np.add.at(cnt, (yy, xx), 1)
    X, Y = np.meshgrid(np.arange(N), np.arange(N))
    island = np.where(geo >= 0, island_of(X, Y), 0).astype(np.int8)
    at = Atlas(pos, nrm, geo, cnt, island)
    extend_border(at, P, Nn, UV, tris)
    at.crotch = find_crotch(at)
    find_seams(at, model, tris)
    at.cut_dist = cut_distance(at)
    return at


def extend_border(at: Atlas, P, Nn, UV, tris, reach: float = 1.6):
    """Texels just outside the islands (within reach texels of a triangle, same island by position) get the
    position and normal of the nearest triangle's plane extended: designs are evaluated there too, so the texture
    filter, which reads half a texel past a UV border, sees the value the other side of a seam has at that 3D point
    instead of a copy (a crisp edge across a seam would otherwise step by a texel)."""
    best = np.full((N, N), np.inf)
    ext_pos = np.zeros((N, N, 3))
    ext_nrm = np.zeros((N, N, 3))
    for tri in tris:
        uv = UV[tri]
        x0, y0 = np.floor(uv.min(0) - reach).astype(int)
        x1, y1 = np.ceil(uv.max(0) + reach).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, N), min(y1, N)
        if x1 <= x0 or y1 <= y0:
            continue
        a, b, c = uv
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        w0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        w1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        w2 = 1 - w0 - w1
        outside = (w0 < -1e-6) | (w1 < -1e-6) | (w2 < -1e-6)
        if not outside.any():
            continue
        # UV distance of each texel centre to the triangle (to its nearest edge)
        d = np.full(xs.shape, np.inf)
        for p0, p1 in ((a, b), (b, c), (c, a)):
            v = p1 - p0
            L2 = float(v @ v) or 1e-12
            t = np.clip(((xs - p0[0]) * v[0] + (ys - p0[1]) * v[1]) / L2, 0, 1)
            d = np.minimum(d, np.hypot(xs - p0[0] - t * v[0], ys - p0[1] - t * v[1]))
        yy = (ys - 0.5).astype(int)
        xx = (xs - 0.5).astype(int)
        cx, cy = uv.mean(0)
        same = island_of(xx, yy) == int(island_of(cx, cy))
        take = outside & (d <= reach) & same & (at.geo[yy, xx] < 0) & (d < best[yy, xx])
        if not take.any():
            continue
        W = np.stack([w0, w1, w2], -1)[take]
        ty, tx = yy[take], xx[take]
        best[ty, tx] = d[take]
        ext_pos[ty, tx] = W @ P[tri]
        ext_nrm[ty, tx] = W @ Nn[tri]
    ext = np.isfinite(best)
    at.ext = ext
    at.pos[ext] = ext_pos[ext]
    at.nrm[ext] = ext_nrm[ext]
    X, Y = np.meshgrid(np.arange(N), np.arange(N))
    at.island_ext = np.where((at.geo >= 0) | ext, island_of(X, Y), 0).astype(np.int8)


def find_crotch(at: Atlas) -> int:
    """First body row below the waist whose two end texels are the same 3D point for 8 rows running: from there down
    the body island's u=256 and u=511 ends meet on the inner leg (wrap); above they are the midlines (mirror)."""
    run = 0
    body = at.island == ISLAND_BODY
    for v in range(160, 448):
        us = np.nonzero(body[v])[0]
        ok = False
        if len(us) > 4:
            p0, p1 = at.pos[v, us[0]].copy(), at.pos[v, us[-1]].copy()
            p0[1], p1[1] = abs(p0[1]), abs(p1[1])
            scale = max(1e-6, np.linalg.norm(at.pos[v, us].max(0) - at.pos[v, us].min(0)))
            ok = np.linalg.norm(p1 - p0) < 0.12 * scale
        run = run + 1 if ok else 0
        if run == 8:
            return v - 7
    raise MarkForgeError("no crotch row found: the body island does not wrap around the legs as the HD layout does")


def find_seams(at: Atlas, model, tris):
    P = model.pos.copy()
    P[:, 0] *= model.forward
    UV = model.uv * N
    scale = float(np.ptp(P[np.unique(tris), 2])) or 1.0
    q = 1e4 / scale  # 3D points match to 1/10000 of the body height
    keyp = np.round(P * q).astype(np.int64)
    edges = {}
    for tri in tris:
        for k in range(3):
            i, j = tri[k], tri[(k + 1) % 3]
            ki, kj = tuple(keyp[i]), tuple(keyp[j])
            if kj < ki:
                i, j, ki, kj = j, i, kj, ki
            ua = (round(float(UV[i, 0]), 2), round(float(UV[i, 1]), 2))
            ub = (round(float(UV[j, 0]), 2), round(float(UV[j, 1]), 2))
            edges.setdefault((ki, kj), []).append(((ua, ub), (P[i] + P[j]) / 2, (P[i], P[j])))
    at.seams, at.open_edges = [], []
    mirror_tol = 0.004 * scale
    at.open_points = []
    for (ki, kj), lst in edges.items():
        uvs = sorted({uv for uv, _, _ in lst})
        ends = tuple(np.array([q[0], abs(q[1]), q[2]]) for q in lst[0][2])
        if len(uvs) == 1:
            if len(lst) == 1 and abs(lst[0][1][1]) > mirror_tol:
                at.open_edges.append(uvs[0])
                at.open_points.append(ends)
            continue
        for x in range(len(uvs)):
            for y in range(x + 1, len(uvs)):
                a, b = uvs[x], uvs[y]
                if max(abs(a[k][c] - b[k][c]) for k in (0, 1) for c in (0, 1)) < 1.5:
                    continue  # split vertices a texel apart (a geoset border): continuous, not a seam
                at.seams.append(Seam(seam_kind(at, a, b), a, b, ends))


def seam_kind(at: Atlas, a, b) -> str:
    """wrap: the two ends of one island's rows (arm u 0/255, leg rows u 256/511); cut: anything else."""
    ma = ((a[0][0] + a[1][0]) / 2, (a[0][1] + a[1][1]) / 2)
    mb = ((b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2)
    ia, ib = int(island_of(ma[0], ma[1])), int(island_of(mb[0], mb[1]))
    if ia != ib:
        return "cut"
    if abs(ma[1] - mb[1]) > 6:
        return "cut"
    if ia == ISLAND_ARM and ma[1] >= 256 and mb[1] >= 256:
        return "hand"  # between the fingers: reported, not gated (gloves cover the hand section)
    if ia == ISLAND_ARM and ma[1] < 320 and abs(ma[0] - mb[0]) > 128:
        return "wrap"
    if ia == ISLAND_BODY and min(ma[1], mb[1]) >= at.crotch - 2 and abs(ma[0] - mb[0]) > 128:
        return "wrap"
    return "cut"


def _segment_texels(segs, step=0.35):
    pts = []
    for (u0, v0), (u1, v1) in segs:
        n = max(2, int(np.hypot(u1 - u0, v1 - v0) / step) + 1)
        t = np.linspace(0, 1, n)
        pts.append(np.stack([u0 + (u1 - u0) * t, v0 + (v1 - v0) * t], -1))
    if not pts:
        return np.zeros((0, 2), int)
    p = np.concatenate(pts)
    return np.clip(np.floor(p).astype(int), 0, N - 1)


def island_distance(seed: np.ndarray, island: np.ndarray, limit: float) -> np.ndarray:
    """Approximate Euclidean distance (texels, 8-neighbour chamfer) from the seed texels, spreading only between
    texels of the same island; capped at limit."""
    dist = np.where(seed, 0.0, np.inf)
    pad = 1
    isl = np.pad(island, pad, constant_values=-1)
    for _ in range(int(np.ceil(limit / 1.0)) + 1):
        d = np.pad(dist, pad, constant_values=np.inf)
        best = dist.copy()
        for dy, dx, w in NEIGHBOURS:
            nb = d[pad + dy:pad + dy + N, pad + dx:pad + dx + N]
            same = isl[pad + dy:pad + dy + N, pad + dx:pad + dx + N] == island
            best = np.minimum(best, np.where(same, nb + w, np.inf))
        if np.array_equal(best, dist):
            break
        dist = best
    return np.minimum(dist, limit)


def distance_3d(at: Atlas, seeds_by_island: dict, limit: float) -> np.ndarray:
    """Per texel of each island given: the 3D distance (in that island's texels) to the nearest seed point of its
    own island, capped at limit. 3D, so both sides of a wrap seam (one 3D point, two places in the atlas) get the
    same value and a fade made from it stays continuous across the seam."""
    out = np.full((N, N), float(limit))
    P = at.pos.copy()
    P[..., 1] = np.abs(P[..., 1])
    for isl, pts in seeds_by_island.items():
        m = (at.island_ext == isl)
        if not m.any():
            continue
        ys, xs = np.nonzero(m)
        q = P[ys, xs]
        # the island's texel size: median distance between horizontal neighbours
        nb = m[:, 1:] & m[:, :-1]
        texel = float(np.median(np.linalg.norm(P[:, 1:][nb] - P[:, :-1][nb], axis=1))) if nb.any() else 1e-3
        if not len(pts):
            continue
        pts = np.asarray(pts, np.float64)
        best = nearest_within(q, pts, limit * texel)
        out[ys, xs] = np.minimum(np.sqrt(best) / texel, limit)
    return out


def nearest_within(q: np.ndarray, pts: np.ndarray, radius: float) -> np.ndarray:
    """Squared distance from each query point to its nearest seed, for seeds within radius (inf beyond): a uniform
    grid of cells the size of the radius, each query looking at its 27 neighbour cells."""
    best = np.full(len(q), np.inf)
    if not len(pts) or not len(q):
        return best
    cell = max(radius, 1e-9)
    lo = np.minimum(q.min(0), pts.min(0))
    qc = np.floor((q - lo) / cell).astype(np.int64)
    pc = np.floor((pts - lo) / cell).astype(np.int64)
    dims = np.maximum(qc.max(0), pc.max(0)) + 3
    key = lambda c: (c[:, 0] * dims[1] + c[:, 1]) * dims[2] + c[:, 2]
    pk = key(pc + 1)
    order = np.argsort(pk, kind="stable")
    pk_sorted = pk[order]
    qk = key(qc + 1)
    for cell_key in np.unique(qk):
        qi = np.nonzero(qk == cell_key)[0]
        c = qc[qi[0]] + 1
        cand = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    k = ((c[0] + dx) * dims[1] + (c[1] + dy)) * dims[2] + (c[2] + dz)
                    a = np.searchsorted(pk_sorted, k, "left")
                    b = np.searchsorted(pk_sorted, k, "right")
                    if b > a:
                        cand.append(order[a:b])
        if not cand:
            continue
        cp = pts[np.concatenate(cand)]
        for i in range(0, len(qi), 4096):
            sub = qi[i:i + 4096]
            d2 = ((q[sub, None, :] - cp[None, :, :]) ** 2).sum(-1)
            best[sub] = d2.min(1)
    return best


def _edge_points(ends, step):
    a, b = ends
    n = max(2, int(np.linalg.norm(b - a) / step) + 1)
    t = np.linspace(0, 1, n)[:, None]
    return a[None, :] + (b - a)[None, :] * t


def cut_distance(at: Atlas, limit: float = 24.0) -> np.ndarray:
    """Distance to the nearest cut seam or open border (3D, in the island's own texels): the arm and body islands to
    every cut seam and open border of theirs; the head island only to the cut seams it shares with another island
    (the chin and neck, the temples where a body-island piece of the head starts), so a face design fades out in 3D
    there as the body side does. The head's own open edges (the eye cuts, the mouth) have keep-out zones, and a cut
    with both sides in the head is continuous: neither is faded (distance = limit)."""
    P = at.pos.copy()
    P[..., 1] = np.abs(P[..., 1])
    body = at.geo >= 0
    texel = float(np.median(np.linalg.norm(P[:, 1:][body[:, 1:] & body[:, :-1]] -
                                           P[:, :-1][body[:, 1:] & body[:, :-1]], axis=1)))
    seeds = {ISLAND_ARM: [], ISLAND_BODY: [], ISLAND_HEAD: []}

    def island(side):
        (u0, v0), (u1, v1) = side
        return int(island_of((u0 + u1) / 2, (v0 + v1) / 2))

    head_sides = []  # the head island's UV side of each cut it shares with another island
    for s in at.seams:
        if s.kind != "cut":
            continue
        pts = _edge_points(s.p, texel * 0.7)
        for side, isl, other in ((s.a, island(s.a), island(s.b)), (s.b, island(s.b), island(s.a))):
            if isl in (ISLAND_ARM, ISLAND_BODY):
                seeds[isl].append(pts)
            elif isl == ISLAND_HEAD and other != ISLAND_HEAD:
                seeds[isl].append(pts)
                head_sides.append(side)
    for p, uv in zip(at.open_points, at.open_edges):
        isl = island(uv)
        if isl in (ISLAND_ARM, ISLAND_BODY):
            seeds[isl].append(_edge_points(p, texel * 0.7))
    seeds = {k: (np.concatenate(v) if v else np.zeros((0, 3))) for k, v in seeds.items()}
    out = distance_3d(at, seeds, limit)
    if head_sides:
        # and in the atlas, within a few texels: the gutter texels next to such a cut hold positions extrapolated
        # off the mesh, which can lie far from the cut in 3D though the client's filter reads them at the seam (only
        # that close, so the fade stays the 3D one, the same on both sides of the head's own cuts, everywhere else)
        seed = np.zeros((N, N), bool)
        t = _segment_texels(head_sides)
        seed[t[:, 1], t[:, 0]] = True
        X, Y = np.meshgrid(np.arange(N), np.arange(N))
        flat = island_distance(seed, island_of(X, Y), HEAD_CUT_GUTTER)
        near = (at.island_ext == ISLAND_HEAD) & (flat < HEAD_CUT_GUTTER)
        out[near] = np.minimum(out[near], flat[near])
    return out


# --- keep-out zones ------------------------------------------------------------------------------------------------


def head_holes(at: Atlas) -> list:
    """Uncovered regions inside the head island that the outside cannot reach: eye cuts, the mouth. Each is
    (texel count, centre row, centre column, width, height)."""
    from collections import deque
    x0, y0, x1, y1 = 0, 320, 256, 512
    inv = at.island[y0:y1, x0:x1] != ISLAND_HEAD
    H, W = inv.shape
    seen = np.zeros_like(inv)
    q = deque()
    for x in range(W):
        for y in (0, H - 1):
            if inv[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    for y in range(H):
        for x in (0, W - 1):
            if inv[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < H and 0 <= xx < W and inv[yy, xx] and not seen[yy, xx]:
                seen[yy, xx] = True
                q.append((yy, xx))
    holes = inv & ~seen
    lab = np.zeros(holes.shape, np.int32)
    out = []
    n = 0
    for y in range(H):
        for x in range(W):
            if holes[y, x] and not lab[y, x]:
                n += 1
                lab[y, x] = n
                q.append((y, x))
                pts = []
                while q:
                    cy, cx = q.popleft()
                    pts.append((cy, cx))
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        yy, xx = cy + dy, cx + dx
                        if 0 <= yy < H and 0 <= xx < W and holes[yy, xx] and not lab[yy, xx]:
                            lab[yy, xx] = n
                            q.append((yy, xx))
                pts = np.array(pts)
                out.append((len(pts), float(pts[:, 0].mean() + y0), float(pts[:, 1].mean() + x0),
                            int(np.ptp(pts[:, 1])) + 1, int(np.ptp(pts[:, 0])) + 1))
    return sorted(out, reverse=True)


def keepout_zones(at: Atlas, eye, eye_sep: float, other_cover: np.ndarray | None = None,
                  eye_axes: tuple = (0.6, 0.34, 0.27), mouth: tuple = (0.62, 0.22)) -> np.ndarray:
    """Texels no mark may touch:
    eyes   an ellipsoid around each eye centre (half axes forward, lateral, up in eye separations): lids, eyeballs,
           the eye cut, the Night Elf glow orbs (eyeball geometry);
    mouth  an ellipse (half width, half height in eye separations) around the mouth hole's 3D centre: the lips.
    Texels that only item geosets sample are counted (keepout_parts["other"]) but not kept out."""
    P = at.pos.copy()
    P[..., 1] = np.abs(P[..., 1])
    head = at.island_ext == ISLAND_HEAD
    e = np.asarray(eye, np.float64)
    ax = np.asarray(eye_axes, np.float64) * eye_sep
    eyes = head & ((((P - e[None, None, :]) / ax[None, None, :]) ** 2).sum(-1) < 1.0)
    parts = {"eyes": eyes}
    at.holes = head_holes(at)
    mouth_mask = np.zeros_like(eyes)
    Y, X = np.mgrid[0:N, 0:N]
    hx, hy = X[head], Y[head]
    centre, half_w = None, mouth[0] * eye_sep
    for count, cy, cx, w, h in at.holes:
        if count < 4 or not len(hx):
            continue
        k = int(np.argmin((hx - cx) ** 2 + (hy - cy) ** 2))
        c = P[hy[k], hx[k]]
        if c[1] < 0.3 * eye_sep and e[2] - 1.6 * eye_sep < c[2] < e[2] - 0.35 * eye_sep:
            ring = head & (np.abs(Y - cy) <= h / 2 + 3) & (np.abs(X - cx) <= w / 2 + 3)
            half_w = max(half_w, float(P[ring][:, 1].max()) + 0.12 * eye_sep)
            centre = c
            break
    if centre is None:
        # no mouth hole in the mesh (a closed mouth): the lips sit about 0.9 eye separations below the eyes
        near = head & (P[..., 1] < 0.15 * eye_sep) & (np.abs(P[..., 2] - (e[2] - 0.9 * eye_sep)) < 0.1 * eye_sep)
        if near.any():
            centre = np.array([P[near][:, 0].max(), 0.0, e[2] - 0.9 * eye_sep])
    if centre is not None:
        ell = (P[..., 1] / half_w) ** 2 + ((P[..., 2] - centre[2]) / (mouth[1] * eye_sep)) ** 2
        mouth_mask = head & (ell < 1.0) \
            & (P[..., 0] > centre[0] - 0.4 * eye_sep)
        parts["mouth_centre"] = [round(float(v), 4) for v in centre]
    parts["mouth"] = mouth_mask
    keep = eyes | mouth_mask
    if other_cover is not None:
        # reported only: item geosets (gloves, boots, robes) sample texels the item's own texture covers
        parts["other"] = other_cover & ~at.valid
    at.keepout = keep
    at.keepout_parts = parts
    return keep


def other_geometry_cover(model) -> np.ndarray:
    """Texels sampled by type-1 triangles of geosets a naked character does not show (gloves, boots, robes,
    hair-style scalps)."""
    from .model import naked_visible
    tris = [t for g, t in model.skin_tris.items() if not naked_visible(g)]
    if not tris:
        return np.zeros((N, N), bool)
    tris = np.concatenate(tris)
    at = rasterise_cover(model, tris)
    return at


def rasterise_cover(model, tris) -> np.ndarray:
    cover = np.zeros((N, N), bool)
    UV = model.uv * N
    for tri in tris:
        uv = UV[tri]
        x0, y0 = np.floor(uv.min(0)).astype(int)
        x1, y1 = np.ceil(uv.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, N), min(y1, N)
        if x1 <= x0 or y1 <= y0:
            continue
        a, b, c = uv
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        w0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        w1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (1 - w0 - w1 >= -1e-6)
        cover[y0:y1, x0:x1] |= inside
    return cover


# --- the garment mask --------------------------------------------------------------------------------------------


STOCK_ALPHA = 0.10  # an underwear with at least this share of transparent texels is the stock kind (layered)


def _opaque(underwear_rgba: np.ndarray) -> tuple[np.ndarray, bool]:
    """(the texels that count, whether it is the stock kind): an underwear with alpha counts its opaque texels only
    (alpha >= 128; transparent ones decode as black and are no colour); the stock kind, layered over the skin, has
    many transparent texels, and its opaque ones are the cloth."""
    if underwear_rgba.shape[-1] == 4 and (underwear_rgba[..., 3] < 255).any():
        opaque = underwear_rgba[..., 3] >= 128
        return opaque, float(1.0 - opaque.mean()) >= STOCK_ALPHA
    return np.ones(underwear_rgba.shape[:2], bool), False


def _difference(underwear_rgba: np.ndarray, skin_rgba: np.ndarray) -> np.ndarray:
    uw = underwear_rgba.astype(np.float64)
    sk = skin_rgba.astype(np.float64)
    return np.abs(uw[..., :3] - sk[..., :3]).max(-1)


def garment_from(underwear_rgba: np.ndarray, skin_rgba: np.ndarray, floor: float = 22.0) -> tuple[np.ndarray, float]:
    """Where an underwear texture is cloth, not skin: the package's NakedTorso/NakedPelvis are opaque copies of the
    skin with the garment painted in. Both arrays are one section (H, W, 4) at the same size. A texel is garment when
    its colour differs from the skin's by more than max(floor, median + 4 * MAD), the median and MAD taken over the
    texels that already look like skin (difference <= 2 * floor; floor alone when there are too few of them), so the
    threshold is the skin copy's noise whatever share of the section the cloth covers, and a copy that is a shade off
    everywhere is not all garment. An underwear with alpha counts its opaque texels only; the stock kind (layered over
    the skin, many transparent texels) is cloth wherever it is opaque. Cleaned by a 3x3 majority and grown by 2
    texels."""
    opaque, stock = _opaque(underwear_rgba)
    if stock:
        g, thr = opaque.copy(), floor
    else:
        d = _difference(underwear_rgba, skin_rgba)
        skin_like = opaque & (d <= 2.0 * floor)
        if skin_like.sum() >= max(16, 0.05 * opaque.sum()):
            ds = d[skin_like]
            med = float(np.median(ds))
            mad = float(np.median(np.abs(ds - med)))
            thr = max(floor, med + 4.0 * mad)
        else:
            thr = floor
        g = (d > thr) & opaque
    # 3x3 majority, then grow by 2
    pad = np.pad(g, 1)
    votes = sum(pad[1 + dy:1 + dy + g.shape[0], 1 + dx:1 + dx + g.shape[1]].astype(int)
                for dy in (-1, 0, 1) for dx in (-1, 0, 1))
    g = votes >= 5
    for _ in range(2):
        pad = np.pad(g, 1)
        g = g | pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]
    return g, thr


def garment_reference_pct(underwear_rgba: np.ndarray, skin_rgba: np.ndarray, floor: float = 22.0) -> float:
    """The garment gate's yardstick: the share (%) of the section's opaque texels that differ from the skin by more
    than the floor above the skin copy's own offset (the median difference of the texels that look like skin), so a
    copy a shade off everywhere counts nothing. A mask far below it lost the cloth (its threshold went up)."""
    opaque, _ = _opaque(underwear_rgba)
    d = _difference(underwear_rgba, skin_rgba)
    skin_like = opaque & (d <= 2.0 * floor)
    offset = float(np.median(d[skin_like])) if skin_like.any() else 0.0
    return 100.0 * float(((d > floor + offset) & opaque).mean())


def place_section(mask: np.ndarray, name: str) -> np.ndarray:
    """A section-sized mask (any power-of-two size) in a full 512 atlas mask."""
    x, y, w, h = SECTIONS[name]
    out = np.zeros((N, N), bool)
    if mask.shape != (h, w):
        fy, fx = h // mask.shape[0], w // mask.shape[1]
        if fy < 1 or fx < 1 or fy * mask.shape[0] != h or fx * mask.shape[1] != w:
            # larger than the section: any texel of the block counts
            sy, sx = mask.shape[0] // h, mask.shape[1] // w
            mask = mask.reshape(h, sy, w, sx).any(axis=(1, 3))
        else:
            mask = np.repeat(np.repeat(mask, fy, 0), fx, 1)
    out[y:y + h, x:x + w] = mask
    return out


def section_of(name: str, img: np.ndarray) -> np.ndarray:
    """The rectangle of a section from a full 512-layout picture (resampled by block averaging when smaller)."""
    x, y, w, h = SECTIONS[name]
    s = img.shape[0] / N
    if s == 1:
        return img[y:y + h, x:x + w]
    xs, ys, ws, hs = int(x * s), int(y * s), max(1, int(w * s)), max(1, int(h * s))
    return img[ys:ys + hs, xs:xs + ws]
