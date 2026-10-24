"""Texture weights, per-chunk layer choice and the 4-bit alpha maps.

Weights start as 100% of the first texture and every rule "paints over" them in spec order:
w = w * (1 - c) + c * one_hot(rule.texture), where the coverage c is the product of the rule's conditions
(shape with fade, slope ramp, height band, noise mask) and its strength. Weights are evaluated on the half-unit
lattice (17 x 17 points per chunk, shared with the neighbours).

Per chunk the client takes at most four layers (MCLY, CMapRenderChunk::CreateLayer fills a 4-slot array): the
textures with the largest total weight, the largest as layer 0. Layer 0 has no alpha map; layers 1-3 carry 64 x 64
4-bit alpha (2048 bytes, two texels per byte, the first texel in the low nibble: UnpackAlphaShadowBitsFixed4444 in
MapRenderChunk.cpp). The layers blend in order, colour = lerp(colour, layer k, alpha k), so for target weights w the
alpha of layer k is w_k / (w_0 + ... + w_k).
"""

from __future__ import annotations

from array import array

from . import coords
from .noise import Fbm

MIN_LAYER_WEIGHT = 0.04
_TEXEL = [(int((t + 0.5) / 4.0), (t + 0.5) / 4.0 - int((t + 0.5) / 4.0)) for t in range(64)]


class _Rule:
    __slots__ = ("texture", "strength", "shape", "fade", "slope", "height", "noise", "noise_threshold",
                 "noise_fade")

    def __init__(self, r: dict, seed: int, index: int):
        self.texture = r["texture"]
        self.strength = r["strength"]
        self.shape = r["shape"]
        self.fade = r["fade"]
        self.slope = r["slope"]
        self.height = r["height"]
        self.noise = None
        if r["noise"] is not None:
            n = r["noise"]
            self.noise = Fbm((seed * 131 + n["seed"] * 977 + index * 13 + 5) & 0xFFFFFFFF, n["scale"], 1.0,
                             n["octaves"])
            self.noise_threshold = n["threshold"]
            self.noise_fade = n["fade"]

    def coverage(self, x: float, y: float, h: float, nz: float) -> float:
        c = self.strength
        if self.shape is not None:
            d = self.shape.distance(x, y)
            if d > 0.0:
                if self.fade <= 0.0 or d >= self.fade:
                    return 0.0
                c *= 1.0 - coords.smoothstep(d / self.fade)
        if self.height is not None:
            lo, hi, fade = self.height
            d = lo - h if h < lo else h - hi if h > hi else 0.0
            if d > 0.0:
                if fade <= 0.0 or d >= fade:
                    return 0.0
                c *= 1.0 - coords.smoothstep(d / fade)
        if self.slope is not None:
            c_lo, c_hi = self.slope
            c *= coords.smoothstep((c_lo - nz) / (c_lo - c_hi))
            if c <= 0.0:
                return 0.0
        if self.noise is not None:
            n = self.noise(x, y)
            c *= coords.smoothstep((n - self.noise_threshold) / self.noise_fade + 0.5)
        return c


class TexturePainter:
    def __init__(self, spec, grid):
        self.spec = spec
        self.grid = grid
        self.count = len(spec.textures)
        self.rules = [_Rule(r, spec.seed, i) for i, r in enumerate(spec.texture_rules)]

    def weights_for_tile(self, tx: int, ty: int) -> list[array]:
        """Per texture, the weights on the tile's 257 x 257 lattice points (row-major)."""
        n = self.count
        size = coords.LATTICE_PER_TILE + 1
        out = [array("d", bytes(8 * size * size)) for _ in range(n)]
        r0 = ty * coords.LATTICE_PER_TILE
        c0 = tx * coords.LATTICE_PER_TILE
        grid = self.grid
        rules = self.rules
        w = [0.0] * n
        i = 0
        for r in range(size):
            row = r0 + r
            x = coords.lattice_x(row)
            for c in range(size):
                col = c0 + c
                for k in range(n):
                    w[k] = 0.0
                w[0] = 1.0
                if rules:
                    y = coords.lattice_y(col)
                    h = grid.get(row, col)
                    nz = grid.normal(row, col)[2]
                    for rule in rules:
                        cov = rule.coverage(x, y, h, nz)
                        if cov <= 0.0:
                            continue
                        keep = 1.0 - cov
                        for k in range(n):
                            w[k] *= keep
                        w[rule.texture] += cov
                for k in range(n):
                    out[k][i] = w[k]
                i += 1
        return out


class ChunkTexturing:
    __slots__ = ("layers", "alpha", "low_quality", "weights", "dropped")

    def __init__(self, layers, alpha, low_quality, weights, dropped=()):
        self.layers = layers  # texture indices, layer 0 first
        self.alpha = alpha  # bytes (2048) for layers 1..3
        self.low_quality = low_quality  # 16 bytes, MCNK +0x40
        self.weights = weights  # per layer, 17 x 17 renormalized weights (row-major lists), for the preview
        self.dropped = dropped  # textures above MIN_LAYER_WEIGHT that did not fit into the 4 layers


def _upsample(block: list[list[float]]) -> list[list[float]]:
    """17 x 17 lattice values -> 64 x 64 texel centres (bilinear)."""
    rows = [[r[i0] + (r[i0 + 1] - r[i0]) * f for (i0, f) in _TEXEL] for r in block]
    out = []
    for j0, f in _TEXEL:
        a = rows[j0]
        b = rows[j0 + 1]
        out.append([a[k] + (b[k] - a[k]) * f for k in range(64)])
    return out


def _nibble(v: float) -> int:
    n = int(v * 15.0 + 0.5)
    return 0 if n < 0 else 15 if n > 15 else n


def pack_alpha_4bit(block: list[list[float]]) -> bytes:
    lo = min(min(r) for r in block)
    hi = max(max(r) for r in block)
    if _nibble(lo) == _nibble(hi):
        n = _nibble(lo)
        return bytes([n | (n << 4)]) * 2048
    out = bytearray(2048)
    i = 0
    for row in _upsample(block):
        for k in range(0, 64, 2):
            out[i] = _nibble(row[k]) | (_nibble(row[k + 1]) << 4)
            i += 1
    return bytes(out)


def texture_chunk(weights: list[array], ix: int, iy: int) -> ChunkTexturing:
    """Choose the layers of chunk (ix, iy) of a tile and build their alpha maps."""
    size = coords.LATTICE_PER_TILE + 1
    n = len(weights)
    base_r = iy * coords.LATTICE_PER_CHUNK
    base_c = ix * coords.LATTICE_PER_CHUNK
    idx = [(base_r + r) * size + base_c + c for r in range(17) for c in range(17)]
    totals = []
    for k in range(n):
        wk = weights[k]
        vals = [wk[i] for i in idx]
        if max(vals) >= MIN_LAYER_WEIGHT:
            totals.append((-sum(vals), k))
    if not totals:
        totals = [(0.0, 0)]
    totals.sort()
    chosen = [k for _, k in totals[:4]]
    dropped = tuple(sorted(k for _, k in totals[4:]))
    layers = [chosen[0]] + sorted(chosen[1:])

    # Renormalize over the chosen layers.
    lw = [[weights[k][i] for i in idx] for k in layers]
    for p in range(289):
        s = 0.0
        for row in lw:
            s += row[p]
        if s <= 0.0:
            lw[0][p] = 1.0
            for row in lw[1:]:
                row[p] = 0.0
        else:
            inv = 1.0 / s
            for row in lw:
                row[p] *= inv

    alpha = []
    prefix = list(lw[0])
    for row in lw[1:]:
        a = [0.0] * 289
        for p in range(289):
            s = prefix[p] + row[p]
            a[p] = row[p] / s if s > 0.0 else 0.0
            prefix[p] = s
        alpha.append(pack_alpha_4bit([a[r * 17:(r + 1) * 17] for r in range(17)]))

    lq = bytearray(16)
    for cy in range(8):
        value = 0
        for cx in range(8):
            p = (2 * cy + 1) * 17 + (2 * cx + 1)
            best = 0
            for k in range(1, len(lw)):
                if lw[k][p] > lw[best][p]:
                    best = k
            value |= best << (2 * cx)
        lq[2 * cy] = value & 0xFF
        lq[2 * cy + 1] = value >> 8
    return ChunkTexturing(layers, alpha, bytes(lq), lw, dropped)
