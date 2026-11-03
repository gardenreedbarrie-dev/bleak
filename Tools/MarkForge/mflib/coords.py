r"""Per-island charts of the atlas in metres, and the body landmarks designs are placed by.

    arm  (AU+AL+HA)  U around the limb, periodic (0 = the outer line, + toward the front, +-C/2 the inner line),
                     V down the arm from the shoulder; both from 3D (the angle around and the length along the limb's
                     axis), never from the UV rows, so they agree on both sides of the wrap seam
    torso (body rows above the crotch row)  U from the front midline (0) to the back midline (G, the half girth),
                     V down from the neck; both edges are mirror lines, left and right share every texel
    leg  (body rows from the crotch row to the foot)  U around the leg like the arm, V continuing down the body
    head (FU+FL)     a front decal: x = |lateral| / eye separation, y = (up - eye height) / eye separation

Design coordinates (designs.py) are landmark based, so one design fits every model:

    arm   t: 0 shoulder, 1 elbow (row 128, the AU/AL border), 2 wrist (row 256, AL/HA), 3 fingertips;  a: turns
    torso t: 0 neck (row 0), 1 lower chest (row 128, TU/TL), 2 waist (row 192, TL/LU), 3 crotch;  s: 0 front
          midline .. 1 back midline (fraction of the half girth)
    leg   t: 0 crotch, 1 knee (row 320, LU/LL), 2 ankle (row 448, LL/FO);  a: turns
    face  x, y in eye separations

Sizes are body units (bu: 1/100 of the neck-to-crotch length) on the body and eye separations (es) on the face.

The outer line of a limb is the lateral direction around its axis, which is smooth by construction (the art study's
prototype took it per row and showed dot jitter near the ankle).
"""

from __future__ import annotations

import numpy as np

from .atlas import ISLAND_ARM, ISLAND_BODY, ISLAND_HEAD, N


def wrap(a, c):
    return (a + c / 2) % c - c / 2


class Region:
    """The texels of one chart: flat atlas indices and their (U, V) in metres."""

    def __init__(self, name, ys, xs, U, V, period=None, girth=None, texel=1e-3):
        self.name = name
        self.ys, self.xs = ys, xs
        self.U, self.V = U, V
        self.period = period  # per texel ring length (arm, leg), None for torso and head
        self.girth = girth  # per texel half girth (torso)
        self.texel = texel  # metres per texel (median)

    def __len__(self):
        return len(self.ys)


class Charts:
    def __init__(self, at, eye, eye_sep):
        self.at = at
        P = at.pos.copy()
        P[..., 1] = np.abs(P[..., 1])
        self.P = P
        self.eye = np.asarray(eye, np.float64)
        self.eye_sep = float(eye_sep)
        valid = at.painted
        self.U = np.full((N, N), np.nan)
        self.V = np.full((N, N), np.nan)
        self.ring = np.zeros(N)  # per arm row: ring length
        self.leg_ring = np.zeros(N)  # per body row below the crotch: ring length
        self.girth = np.zeros(N)  # per torso row: half girth
        self.crotch = at.crotch
        self._row_v_cache = {}
        arm = valid & (at.island_ext == ISLAND_ARM)
        body = valid & (at.island_ext == ISLAND_BODY)
        self.C_tex = np.full((N, N), np.nan)  # ring length at every limb texel's V
        self._limb(arm, 0, 256, range(0, 320), self.ring)
        self._torso(body, range(0, self.crotch))
        self._limb(body, 256, 512, range(self.crotch, 448), self.leg_ring, v_from=self.crotch)
        self._landmarks()
        self._face(valid & (at.island_ext == ISLAND_HEAD))
        self.texel_map = self._symmetric(self._texel_map(at.geo >= 0), valid)
        self.regions = self._regions(valid)

    # --- charts ---

    def _row_v(self, mask, rows, c0, c1, start=0.0):
        acc, prev = start, None
        out = {}
        for v in rows:
            if not mask[v, c0:c1].any():
                continue
            if prev is not None:
                both = mask[v, c0:c1] & mask[prev, c0:c1]
                if both.any():
                    d = np.linalg.norm(self.P[v, c0:c1][both] - self.P[prev, c0:c1][both], axis=1)
                    acc += float(np.median(d))
            out[v] = acc
            prev = v
        return out

    def _limb(self, mask, c0, c1, rows, ring, v_from=None):
        """The chart of a limb from 3D alone, so it is continuous wherever the UV layout puts its wrap seam (the two
        sides of that seam sit on different rows near the shoulder):
            axis  the curve through the rows' centroids, smoothed over 9 rows
            V     arc length along the axis at the texel's closest point
            U     the angle around the axis, from the outer direction toward the front, times the ring length at that
                  V / 2 pi: 0 the outer line, +-C/2 the inner line, C the ring length. The outer direction is the
                  lateral axis turned with the limb, (0, -Tz, Ty) for the axis direction T: +lateral for a hanging
                  limb, +up for an arm held out in the rest pose (it faces outward once the arm hangs)
        ring[] keeps the row's ring length (the arc length along its texels plus the closing gap)."""
        rows = [v for v in rows if mask[v, c0:c1].sum() >= 4]
        if len(rows) < 3:
            return
        start = 0.0
        if v_from is not None and not np.isnan(self.V[v_from - 1, 256:]).all():
            start = float(np.nanmedian(self.V[v_from - 1, 256:]))
        cents = np.array([self.P[v, np.nonzero(mask[v, c0:c1])[0] + c0].mean(0) for v in rows])
        k = 4
        sm = np.array([cents[max(0, i - k):i + k + 1].mean(0) for i in range(len(cents))])
        a, b = sm[:-1], sm[1:]
        ab = b - a
        L = np.linalg.norm(ab, axis=1)
        L2 = np.maximum(L * L, 1e-18)
        cum = np.concatenate([[0.0], np.cumsum(L)])
        rowmask = np.zeros(N, bool)
        rowmask[rows] = True
        ys, xs = np.nonzero(mask[:, c0:c1] & rowmask[:, None])
        xs = xs + c0
        pts = self.P[ys, xs]
        V = np.zeros(len(pts))
        theta = np.zeros(len(pts))
        forward = np.array([1.0, 0.0, 0.0])
        for i in range(0, len(pts), 2048):
            p = pts[i:i + 2048]
            # plain products and a sum over the 3 coordinates, not einsum: einsum's summation (and FMA) differs
            # between numpy versions, and a last-bit change here moves texels at a joint of the axis between two
            # segments (whose tangents differ)
            t = np.clip(((p[:, None, :] - a[None, :, :]) * ab[None, :, :]).sum(-1) / L2[None, :], 0, 1)
            closest = a[None, :, :] + t[..., None] * ab[None, :, :]
            d2 = ((p[:, None, :] - closest) ** 2).sum(-1)
            j = np.argmin(d2, axis=1)
            tj = t[np.arange(len(p)), j]
            V[i:i + 2048] = cum[j] + tj * L[j]
            T = ab[j] / np.maximum(L[j], 1e-12)[:, None]
            c = a[j] + tj[:, None] * ab[j]
            r = p - c
            r = r - (r * T).sum(1)[:, None] * T
            # the outer direction turns with the limb: (0, -Tz, Ty) is +lateral for a limb hanging down and +up for
            # an arm held out to the side (the HD models' rest pose), the side that faces outward when it hangs
            O = np.stack([np.zeros(len(T)), -T[:, 2], T[:, 1]], 1)
            O = O - (O * T).sum(1)[:, None] * T
            O /= np.maximum(np.linalg.norm(O, axis=1), 1e-12)[:, None]
            F = np.cross(T, O)
            F = np.where(((F @ forward) < 0)[:, None], -F, F)
            theta[i:i + 2048] = np.arctan2((r * F).sum(1), (r * O).sum(1))
        # ring length per row (texel arc length + closing gap), as a function of V
        rv, rc = [], []
        for v in rows:
            us = np.nonzero(mask[v, c0:c1])[0] + c0
            q = self.P[v, us]
            C = float(np.linalg.norm(np.diff(q, axis=0), axis=1).sum() + np.linalg.norm(q[-1] - q[0]))
            ring[v] = C
            sel = ys == v
            if sel.any():
                rv.append(float(np.median(V[sel])))
                rc.append(C)
        order = np.argsort(rv, kind="stable")  # rows past the axis ends tie (V clamped): keep them in row order
        rv, rc = np.array(rv)[order], np.array(rc)[order]
        # smooth the ring length over V (rows near the shoulder are partial rings)
        rcs = np.array([np.median(rc[max(0, i - 4):i + 5]) for i in range(len(rc))])
        Cv = np.interp(V, rv, rcs)
        self.U[ys, xs] = theta / (2 * np.pi) * Cv
        self.V[ys, xs] = V + start
        self._ring_v = getattr(self, "_ring_v", {})
        self._ring_v[(c0, rows[0])] = (rv + start, rcs)
        self.C_tex[ys, xs] = Cv

    def _torso(self, mask, rows):
        vmap = self._row_v(mask, list(rows), 256, 512)
        for v, vv in vmap.items():
            us = np.nonzero(mask[v, 256:512])[0] + 256
            if len(us) < 2:
                continue
            p = self.P[v, us]
            du = np.linalg.norm(np.diff(p, axis=0), axis=1)
            ucum = np.concatenate([[0.0], np.cumsum(du)])
            G = float(ucum[-1])
            if p[0, 0] < p[-1, 0]:  # the first texel must be the front midline
                ucum = G - ucum
            self.U[v, us] = ucum
            self.V[v, us] = vv
            self.girth[v] = G

    def _landmarks(self):
        def row_v(r, c0, c1):
            for d in range(0, 12):
                for rr in (r - d, r + d):
                    if 0 <= rr < N:
                        vals = self.V[rr, c0:c1]
                        if not np.isnan(vals).all():
                            return float(np.nanmedian(vals))
            return float("nan")

        arm_tip = float(np.nanmax(self.V[:320, :256]))
        self.arm_knots = [0.0, row_v(128, 0, 256), row_v(255, 0, 256), arm_tip]
        self.torso_knots = [row_v(0, 256, 512), row_v(128, 256, 512), row_v(192, 256, 512),
                            row_v(self.crotch - 1, 256, 512)]
        self.leg_knots = [row_v(self.crotch, 256, 512), row_v(320, 256, 512), row_v(447, 256, 512)]
        self.bu = (self.torso_knots[3] - self.torso_knots[0]) / 100.0
        self.landmarks = {
            "arm": self.arm_knots, "torso": self.torso_knots, "leg": self.leg_knots, "bu": self.bu,
            "eye": [float(v) for v in self.eye], "eye_sep": self.eye_sep, "crotch_row": int(self.crotch),
        }

    def _face(self, head):
        s = max(self.eye_sep, 1e-4)
        P = self.P
        self.FX = np.where(head, P[..., 1] / s, np.nan)
        self.FY = np.where(head, (P[..., 2] - self.eye[2]) / s, np.nan)
        self.facing = np.where(head, np.clip(self.at.nrm[..., 0], 0, 1), 0.0)

    def _regions(self, valid):
        out = {}
        Y, X = np.mgrid[0:N, 0:N]
        isl = self.at.island_ext
        defs = {
            "arm": valid & (isl == ISLAND_ARM) & ~np.isnan(self.U),
            "torso": valid & (isl == ISLAND_BODY) & (Y < self.crotch) & ~np.isnan(self.U),
            "leg": valid & (isl == ISLAND_BODY) & (Y >= self.crotch) & (Y < 448) & ~np.isnan(self.U),
            "head": valid & (isl == ISLAND_HEAD),
        }
        for name, m in defs.items():
            ys, xs = np.nonzero(m)
            if name == "head":
                U, V = self.FX[ys, xs] * self.eye_sep, self.FY[ys, xs] * self.eye_sep
                period, girth = None, None
            else:
                U, V = self.U[ys, xs], self.V[ys, xs]
                period = self.C_tex[ys, xs] if name in ("arm", "leg") else None
                girth = self.girth[ys] if name == "torso" else None
            reg = Region(name, ys, xs, U, V, period, girth, self._texel(m))
            reg.texel_local = self.texel_map[ys, xs]
            out[name] = reg
        return out

    def _texel_map(self, valid):
        """Metres per texel at every texel: the larger of its spacings to the right and below (a UV layout stretched
        in one direction is coarse in that direction), smoothed over 3x3, floored at half the median."""
        P = self.P
        out = np.zeros((N, N))
        dx = np.zeros((N, N))
        dy = np.zeros((N, N))
        mx = valid[:, 1:] & valid[:, :-1]
        my = valid[1:, :] & valid[:-1, :]
        dx[:, :-1] = np.where(mx, np.linalg.norm(P[:, 1:] - P[:, :-1], axis=-1), 0)
        dy[:-1, :] = np.where(my, np.linalg.norm(P[1:, :] - P[:-1, :], axis=-1), 0)
        dx[:, 1:] = np.maximum(dx[:, 1:], dx[:, :-1])
        dy[1:, :] = np.maximum(dy[1:, :], dy[:-1, :])
        out = np.maximum(dx, dy)
        med = float(np.median(out[valid & (out > 0)])) if (valid & (out > 0)).any() else 1e-3
        # a jump over a seam or a fold is not a texel: cap at 4x the median
        out = np.clip(out, 0.5 * med, 4 * med)
        pad = np.pad(out, 1, mode="edge")
        sm = sum(pad[1 + a:1 + a + N, 1 + b:1 + b + N] for a in (-1, 0, 1) for b in (-1, 0, 1)) / 9.0
        sm = np.where(valid, sm, np.nan)
        # the extrapolated border takes its inside neighbours' size (its own neighbours may be another triangle's)
        for _ in range(3):
            pad = np.pad(sm, 1, constant_values=np.nan)
            nb = np.stack([pad[1 + a:1 + a + N, 1 + b:1 + b + N] for a, b in ((0, 1), (0, -1), (1, 0), (-1, 0))])
            fill = np.nanmax(np.where(np.isnan(nb), -np.inf, nb), axis=0)
            sm = np.where(np.isnan(sm) & np.isfinite(fill), fill, sm)
        return np.where(np.isnan(sm), med, sm)

    def _symmetric(self, tex, valid):
        """The texel size as a smooth function of the 3D point. The two sides of a seam are one 3D point with two UV
        layouts; a width or an anti-aliasing taken from one side's UV spacing would differ across the seam. So: the
        largest size in each 3D cell (4 median texels) and its 26 neighbours, interpolated trilinearly between cell
        centres, which is continuous in 3D and the same on both sides."""
        out = tex.copy()
        for isl in (ISLAND_ARM, ISLAND_BODY, ISLAND_HEAD):
            m = valid & (self.at.island_ext == isl)
            if not m.any():
                continue
            ys, xs = np.nonzero(m)
            q = self.P[ys, xs]
            t = tex[ys, xs]
            cell = 4.0 * float(np.median(t))
            # the lowest point sits in the middle of a cell, never on a cell border where the last bit of `cell`
            # (another numpy, another CPU) would decide its cell
            lo = q.min(0) - 2.5 * cell
            c = np.floor((q - lo) / cell).astype(np.int64)
            dims = c.max(0) + 4

            def key(cc):
                return (cc[..., 0] * dims[1] + cc[..., 1]) * dims[2] + cc[..., 2]

            k = key(c)
            uk, inv = np.unique(k, return_inverse=True)
            cmax = np.zeros(len(uk))
            np.maximum.at(cmax, inv, t)
            dil = cmax.copy()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        nk = uk + (dx * dims[1] + dy) * dims[2] + dz
                        j = np.clip(np.searchsorted(uk, nk), 0, len(uk) - 1)
                        dil = np.where(uk[j] == nk, np.maximum(dil, cmax[j]), dil)
            own = dil[inv]
            f = (q - lo) / cell - 0.5
            base = np.floor(f).astype(np.int64)
            fr = f - base
            acc = np.zeros(len(q))
            for ox in (0, 1):
                for oy in (0, 1):
                    for oz in (0, 1):
                        cc = base + np.array([ox, oy, oz])
                        nk = key(cc)
                        j = np.clip(np.searchsorted(uk, nk), 0, len(uk) - 1)
                        val = np.where(uk[j] == nk, dil[j], own)
                        wgt = (fr[:, 0] if ox else 1 - fr[:, 0]) * (fr[:, 1] if oy else 1 - fr[:, 1]) * \
                            (fr[:, 2] if oz else 1 - fr[:, 2])
                        acc += wgt * val
            out[ys, xs] = acc
        return out

    def _texel(self, m):
        a = self.P[:, 1:][m[:, 1:] & m[:, :-1]]
        b = self.P[:, :-1][m[:, 1:] & m[:, :-1]]
        if not len(a):
            return 1e-3
        return float(np.median(np.linalg.norm(a - b, axis=1)))

    # --- design coordinates -> metres ---

    @staticmethod
    def _interp(knots, t):
        t = np.asarray(t, np.float64)
        k = np.asarray(knots, np.float64)
        idx = np.clip(np.floor(t).astype(int), 0, len(k) - 2)
        f = t - idx
        return k[idx] + (k[idx + 1] - k[idx]) * f

    def v_of(self, region, t):
        knots = {"arm": self.arm_knots, "torso": self.torso_knots, "leg": self.leg_knots}[region]
        return self._interp(knots, t)

    def row_of_v(self, region, v):
        """The atlas row of the region whose V is nearest (for the ring length / girth at a point)."""
        if region not in self._row_v_cache:
            col = slice(0, 256) if region == "arm" else slice(256, 512)
            vals = self.V[:, col]
            ok = ~np.isnan(vals).all(axis=1)
            rows = np.full(N, np.nan)
            rows[ok] = np.nanmedian(vals[ok], axis=1)
            r = np.arange(N)
            sel = {"arm": r < 320, "torso": r < self.crotch, "leg": (r >= self.crotch) & (r < 448)}[region]
            rows[~sel] = np.nan
            self._row_v_cache[region] = rows
        rows = self._row_v_cache[region]
        return int(np.nanargmin(np.abs(rows - v)))

    def to_metres(self, region, pts):
        """Design points of a region -> (U, V) metres. arm/leg (t, a turns), torso (t, s), face (x, y) es."""
        pts = np.asarray(pts, np.float64).reshape(-1, 2)
        if region == "head":
            return pts * self.eye_sep
        V = self.v_of(region, pts[:, 0])
        out = np.zeros_like(pts)
        out[:, 1] = V
        for i, v in enumerate(V):
            if region in ("arm", "leg"):
                out[i, 0] = pts[i, 1] * self.ring_at(region, v)
            else:
                out[i, 0] = pts[i, 1] * self.girth[self.row_of_v(region, v)]
        return out

    def ring_at(self, region, v):
        key = (0, min(k[1] for k in self._ring_v if k[0] == 0)) if region == "arm" else \
            (256, min(k[1] for k in self._ring_v if k[0] == 256))
        rv, rc = self._ring_v[key]
        return float(np.interp(v, rv, rc))

    def unit(self, region):
        """Metres per size unit: bu on the body, eye separations on the face."""
        return self.eye_sep if region == "head" else self.bu
