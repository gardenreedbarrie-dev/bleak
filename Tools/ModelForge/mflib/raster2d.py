"""2D coverage masks for lettering, emblems and decals.

Strokes use the analytic anti-aliased stroke rasterizer of Tools/UiLint/make_art.py (Canvas.stroke, imported
read-only, section 5.5.2) and its SVG path parser; fills are a scanline rasterizer with the nonzero rule and
supersampled rows, written here (make_art.py has no polygon fill).
"""

import math

import make_art  # noqa: E402  Tools/UiLint (read-only), on sys.path through mflib/__init__.py


class Mask:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.a = [0.0] * (w * h)

    def get(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.a[y * self.w + x]
        return 0.0

    def sample(self, fx, fy):
        """Bilinear sample at pixel coordinates (pixel centres at +0.5)."""
        x = fx - 0.5
        y = fy - 0.5
        x0, y0 = math.floor(x), math.floor(y)
        tx, ty = x - x0, y - y0
        a = self.get(x0, y0) * (1 - tx) + self.get(x0 + 1, y0) * tx
        b = self.get(x0, y0 + 1) * (1 - tx) + self.get(x0 + 1, y0 + 1) * tx
        return a * (1 - ty) + b * ty

    def max_with(self, other):
        for i in range(len(self.a)):
            if other.a[i] > self.a[i]:
                self.a[i] = other.a[i]
        return self

    def subtract(self, other):
        for i in range(len(self.a)):
            self.a[i] = max(0.0, self.a[i] - other.a[i])
        return self

    def multiply(self, other):
        for i in range(len(self.a)):
            self.a[i] *= other.a[i]
        return self

    def copy(self):
        m = Mask(self.w, self.h)
        m.a = list(self.a)
        return m

    def coverage(self):
        return sum(self.a) / max(1, len(self.a))

    def bbox(self, thr=0.05):
        xs, ys = [], []
        for y in range(self.h):
            row = self.a[y * self.w:(y + 1) * self.w]
            for x, v in enumerate(row):
                if v > thr:
                    xs.append(x)
                    ys.append(y)
        if not xs:
            return None
        return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def parse(d):
    return make_art.parse_path(d)


def xform_polys(polys, sx, sy, ox, oy):
    return [[(ox + x * sx, oy + y * sy) for x, y in poly] for poly in polys]


def fill(mask, polys, ss=4):
    """Nonzero-rule fill of closed polygons (pixel coordinates) into the mask (max blend)."""
    edges = []
    for poly in polys:
        n = len(poly)
        if n < 3:
            continue
        for i in range(n):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % n]
            if y0 == y1:
                continue
            wnd = 1 if y1 > y0 else -1
            if y0 > y1:
                x0, y0, x1, y1 = x1, y1, x0, y0
            edges.append((y0, y1, x0, (x1 - x0) / (y1 - y0), wnd))
    if not edges:
        return mask
    ymin = max(0, int(math.floor(min(e[0] for e in edges))))
    ymax = min(mask.h - 1, int(math.ceil(max(e[1] for e in edges))))
    w = mask.w
    for py in range(ymin, ymax + 1):
        row = [0.0] * (w + 2)
        for sy in range(ss):
            yy = py + (sy + 0.5) / ss
            xs = []
            for y0, y1, x0, dx, wnd in edges:
                if y0 <= yy < y1:
                    xs.append((x0 + (yy - y0) * dx, wnd))
            if not xs:
                continue
            xs.sort()
            acc = 0
            for k in range(len(xs) - 1):
                acc += xs[k][1]
                if acc == 0:
                    continue
                a, b = xs[k][0], xs[k + 1][0]
                if b <= 0 or a >= w:
                    continue
                a = max(a, 0.0)
                b = min(b, float(w))
                ia, ib = int(a), int(b)
                if ia == ib:
                    row[ia] += (b - a) / ss
                    continue
                row[ia] += (ia + 1 - a) / ss
                for x in range(ia + 1, ib):
                    row[x] += 1.0 / ss
                if ib < w:
                    row[ib] += (b - ib) / ss
        base = py * w
        for x in range(w):
            v = row[x]
            if v > 0:
                v = 1.0 if v > 1.0 else v
                if v > mask.a[base + x]:
                    mask.a[base + x] = v
    return mask


def stroke(mask, polys, width):
    """Anti-aliased round-capped strokes (make_art.Canvas.stroke) into the mask (max blend)."""
    c = make_art.Canvas(mask.w, mask.h)
    c.stroke(polys, 1.0, 0.0, 0.0, width)
    for i, v in enumerate(c.a):
        if v > mask.a[i]:
            mask.a[i] = v
    return mask


def path_fill(mask, d, sx, sy, ox, oy, ss=4):
    return fill(mask, xform_polys(parse(d), sx, sy, ox, oy), ss)


def path_stroke(mask, d, width, sx, sy, ox, oy):
    return stroke(mask, xform_polys(parse(d), sx, sy, ox, oy), width)


def disc(mask, cx, cy, r):
    x0, x1 = max(0, int(cx - r - 1)), min(mask.w, int(cx + r + 2))
    y0, y1 = max(0, int(cy - r - 1)), min(mask.h, int(cy + r + 2))
    for y in range(y0, y1):
        for x in range(x0, x1):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            v = r - d + 0.5
            if v > 0:
                v = 1.0 if v > 1 else v
                i = y * mask.w + x
                if v > mask.a[i]:
                    mask.a[i] = v
    return mask


def blur(mask, radius):
    """Separable box blur (two passes ~ a soft tent)."""
    if radius <= 0:
        return mask.copy()
    w, h = mask.w, mask.h
    src = mask.a
    for _ in range(2):
        tmp = [0.0] * (w * h)
        for y in range(h):
            row = src[y * w:(y + 1) * w]
            pre = [0.0]
            for v in row:
                pre.append(pre[-1] + v)
            for x in range(w):
                a = max(0, x - radius)
                b = min(w, x + radius + 1)
                tmp[y * w + x] = (pre[b] - pre[a]) / (b - a)
        out = [0.0] * (w * h)
        for x in range(w):
            pre = [0.0]
            for y in range(h):
                pre.append(pre[-1] + tmp[y * w + x])
            for y in range(h):
                a = max(0, y - radius)
                b = min(h, y + radius + 1)
                out[y * w + x] = (pre[b] - pre[a]) / (b - a)
        src = out
    m = Mask(w, h)
    m.a = src
    return m


def dilate(mask, r):
    """Grey dilation by a square of radius r."""
    w, h = mask.w, mask.h
    tmp = [0.0] * (w * h)
    for y in range(h):
        for x in range(w):
            tmp[y * w + x] = max(mask.a[y * w + max(0, x - r): y * w + min(w, x + r + 1)])
    out = Mask(w, h)
    for x in range(w):
        col = [tmp[y * w + x] for y in range(h)]
        for y in range(h):
            out.a[y * w + x] = max(col[max(0, y - r):min(h, y + r + 1)])
    return out
