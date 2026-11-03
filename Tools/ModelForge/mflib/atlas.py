"""Chart packing (CAFE.SPEC.md section 5.5, "Atlases and gutters").

Every chart (geom.Chart, measured in yards) gets a rectangle in the texture at one texel density, scaled by its
weight. Rectangles are snapped to 4-texel DXT blocks and separated by gutters of at least 8 px at 512, 4 px at
256 and 2 px at 128 (rounded up to whole blocks here, so islands never share a DXT block or, down to mip 2, a
mip texel); mips.py fills the gutters by edge dilation. The density is the largest one at which a shelf packing
succeeds (binary search), so the atlas is used fully and deterministically.
"""

import math

BLOCK = 4


def gutter_for(size):
    s = max(size)
    if s >= 512:
        return 8
    if s >= 256:
        return 4
    return 2


def _up(v, q=BLOCK):
    return int(math.ceil(v / q - 1e-9)) * q


class Placement:
    __slots__ = ("x", "y", "w", "h", "sx", "sy")

    def __init__(self, x, y, w, h, sx, sy):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.sx, self.sy = sx, sy   # texels per yard along s and t

    def uv(self, s, t, size):
        return ((self.x + s * self.sx) / size[0], (self.y + t * self.sy) / size[1])


def _sizes(charts, density, gut, size):
    out = []
    maxw = size[0] - 2 * gut
    maxh = size[1] - 2 * gut
    for ch in charts:
        d = density * ch.weight
        w = _up(max(ch.min_px, ch.w * d))
        h = _up(max(ch.min_px, ch.h * d))
        if w > maxw or h > maxh:   # a chart too big for the atlas keeps its aspect at a lower density
            k = min(maxw / w, maxh / h)
            w = max(BLOCK, int(w * k) // BLOCK * BLOCK)
            h = max(BLOCK, int(h * k) // BLOCK * BLOCK)
        out.append((w, h))
    return out


def _shelf(sizes, size, gut, reserved):
    """Shelf packing, tallest first; returns {index: (x, y)} or None."""
    order = sorted(range(len(sizes)), key=lambda i: (-sizes[i][1], -sizes[i][0], i))
    margin = _up(gut / 2) if gut >= BLOCK else BLOCK
    step = _up(gut)
    W, H = size
    pos = {}
    x = margin
    y = margin
    shelf_h = 0
    for i in order:
        w, h = sizes[i]
        placed = False
        while not placed:
            if x + w + margin > W:
                y += shelf_h + step
                x = margin
                shelf_h = 0
            if y + h + margin > H:
                return None
            clash = None
            for rx, ry, rw, rh in reserved:
                if x < rx + rw + step and rx < x + w + step and y < ry + rh + step and ry < y + h + step:
                    clash = (rx, ry, rw, rh)
                    break
            if clash:
                x = clash[0] + clash[2] + step
                continue
            pos[i] = (x, y)
            x += w + step
            shelf_h = max(shelf_h, h)
            placed = True
    return pos


def pack(charts, size=(512, 512), gutter=None):
    """Places every chart. Returns ([Placement per chart], density in texels per yard)."""
    gut = gutter if gutter is not None else gutter_for(size)
    gut = max(BLOCK, _up(gut)) if gut >= BLOCK else gut
    placements = [None] * len(charts)
    reserved = []
    free = []
    for i, ch in enumerate(charts):
        if ch.fixed:
            x, y, w, h = ch.fixed
            placements[i] = Placement(x, y, w, h, w / ch.w, h / ch.h)
            reserved.append((x, y, w, h))
        else:
            free.append(i)
    sub = [charts[i] for i in free]
    if not sub:
        return placements, 0.0
    area = sum(c.w * c.h * c.weight * c.weight for c in sub) or 1e-6
    hi = math.sqrt(size[0] * size[1] / area) * 1.5
    lo = 0.0
    best = None
    for _ in range(40):
        mid = (lo + hi) / 2
        sizes = _sizes(sub, mid, gut, size)
        pos = _shelf(sizes, size, gut, reserved)
        if pos is not None:
            lo = mid
            best = (mid, sizes, pos)
        else:
            hi = mid
        if hi - lo < 0.25:
            break
    if best is None:
        sizes = _sizes(sub, 1e-3, gut, size)
        pos = _shelf(sizes, size, gut, reserved)
        if pos is None:
            raise ValueError("charts do not fit a %dx%d atlas even at minimum size" % size)
        best = (1e-3, sizes, pos)
    density, sizes, pos = best
    for k, i in enumerate(free):
        w, h = sizes[k]
        x, y = pos[k]
        placements[i] = Placement(x, y, w, h, w / charts[i].w, h / charts[i].h)
    return placements, density
