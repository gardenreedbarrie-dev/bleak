"""Deterministic 2D gradient noise (Perlin style) on an integer hash.

Same seed and coordinates give the same value on every platform: the hash is integer arithmetic and the
interpolation uses only +, -, * (no libm calls).
"""

from __future__ import annotations

import math

_M32 = 0xFFFFFFFF
_D = math.sqrt(0.5)
_GRADIENTS = ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0), (_D, _D), (-_D, _D), (_D, -_D), (-_D, -_D))


def hash32(ix: int, iy: int, seed: int) -> int:
    h = ((ix * 0x27D4EB2D) ^ (iy * 0x165667B1) ^ (seed * 0x9E3779B1)) & _M32
    h ^= h >> 15
    h = (h * 0x85EBCA6B) & _M32
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & _M32
    h ^= h >> 16
    return h


def hash_unit(ix: int, iy: int, seed: int) -> float:
    """Hash to [0, 1)."""
    return hash32(ix, iy, seed) / 4294967296.0


class GradientNoise:
    """One octave of 2D gradient noise in [-1, 1] (roughly; extremes near +-0.7 are rare)."""

    __slots__ = ("seed", "_cache")

    def __init__(self, seed: int):
        self.seed = seed & _M32
        self._cache: dict[tuple[int, int], tuple[float, float]] = {}

    def _grad(self, ix: int, iy: int) -> tuple[float, float]:
        key = (ix, iy)
        g = self._cache.get(key)
        if g is None:
            g = _GRADIENTS[hash32(ix, iy, self.seed) & 7]
            if len(self._cache) > 200000:
                self._cache.clear()
            self._cache[key] = g
        return g

    def __call__(self, x: float, y: float) -> float:
        x0 = math.floor(x)
        y0 = math.floor(y)
        fx = x - x0
        fy = y - y0
        ix = int(x0)
        iy = int(y0)
        g00 = self._grad(ix, iy)
        g10 = self._grad(ix + 1, iy)
        g01 = self._grad(ix, iy + 1)
        g11 = self._grad(ix + 1, iy + 1)
        n00 = g00[0] * fx + g00[1] * fy
        n10 = g10[0] * (fx - 1.0) + g10[1] * fy
        n01 = g01[0] * fx + g01[1] * (fy - 1.0)
        n11 = g11[0] * (fx - 1.0) + g11[1] * (fy - 1.0)
        u = fx * fx * fx * (fx * (fx * 6.0 - 15.0) + 10.0)
        v = fy * fy * fy * (fy * (fy * 6.0 - 15.0) + 10.0)
        a = n00 + (n10 - n00) * u
        b = n01 + (n11 - n01) * u
        return (a + (b - a) * v) * 1.41421356


class Fbm:
    """Fractal sum of octaves: amplitude * sum(p^i * noise(x * l^i / scale)) / sum(p^i)."""

    def __init__(self, seed: int, scale: float, amplitude: float, octaves: int = 1, persistence: float = 0.5,
                 lacunarity: float = 2.0, offset: float = 0.0):
        self.scale = float(scale)
        self.amplitude = float(amplitude)
        self.offset = float(offset)
        self.octaves = []
        weight = 1.0
        freq = 1.0
        total = 0.0
        for i in range(int(octaves)):
            self.octaves.append((GradientNoise(seed * 7919 + i * 104729 + 17), freq / self.scale, weight))
            total += weight
            weight *= persistence
            freq *= lacunarity
        self.norm = 1.0 / total if total else 0.0

    def __call__(self, x: float, y: float) -> float:
        s = 0.0
        for noise, freq, weight in self.octaves:
            # Offset each octave so lattice points of different octaves do not line up.
            s += weight * noise(x * freq + 0.371, y * freq + 0.619)
        return self.offset + self.amplitude * s * self.norm
