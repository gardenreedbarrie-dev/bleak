"""The client's map coordinate system, and deterministic math helpers.

Axis convention (what the 3.3.5a client and AzerothCore use; `.gps` in game prints the same numbers):

- world X points north, world Y points west, world Z points up; all in yards;
- the map is a 64 x 64 grid of tiles of TILE_SIZE = 1600 / 3 = 533.3333 yards, centred on world (0, 0): the
  grid's corner is at X = Y = ZERO = 32 * TILE_SIZE = 17066.6667 (CMapChunk::Create, CMap::PrepareArea);
- tile (tx, ty) is the file `<Dir>_<tx>_<ty>.adt` and MAIN entry 64 * ty + tx. tx counts along -Y (west to east)
  and ty along -X (north to south); tile (32, 32) has its north-west corner at world (0, 0);
- a tile holds 16 x 16 chunks (CHUNK_SIZE = 33.3333), chunk (ix, iy) is MCIN entry 16 * iy + ix, ix along -Y,
  iy along -X;
- a chunk holds 9 x 9 outer and 8 x 8 inner height vertices, UNIT_SIZE = 4.1667 apart (CMapChunk::
  InitializeVertexGrid): outer (r, c) sits at (top.x - r * UNIT_SIZE, top.y - c * UNIT_SIZE) and inner (r, c) half a
  unit further in both directions.

MapForge evaluates the terrain on one global "half-unit lattice": lattice row R and column C are the world point
X = ZERO - R * HALF_UNIT, Y = ZERO - C * HALF_UNIT with HALF_UNIT = TILE_SIZE / 256. Outer vertices are the points
with both indices even, inner vertices the points with both odd. Every chunk and tile edge vertex is the same
lattice point for both neighbours, which is why shared edges match exactly.

Model placements (MDDF, MODF) use the file's own axis order (CMap::CreateDoodadDef):
file = (ZERO - worldY, worldZ, ZERO - worldX).

The math helpers avoid the C library's transcendental functions so the output does not depend on the platform's
libm: only +, -, *, / and sqrt (which IEEE 754 rounds exactly) are used.
"""

from __future__ import annotations

import math

TILE_SIZE = 1600.0 / 3.0
CHUNK_SIZE = TILE_SIZE / 16.0
UNIT_SIZE = CHUNK_SIZE / 8.0
HALF_UNIT = TILE_SIZE / 256.0
ZERO = 32.0 * TILE_SIZE

LATTICE_PER_TILE = 256
LATTICE_PER_CHUNK = 16
LATTICE_ORIGIN = 32 * LATTICE_PER_TILE  # lattice index of world 0

HEIGHT_QUANTUM = 1.0 / 64.0
HEIGHT_LIMIT = 16384.0


def lattice_x(row: int) -> float:
    """World X of lattice row `row` (exact: (8192 - row) * 25 / 12)."""
    return (LATTICE_ORIGIN - row) * 25.0 / 12.0


def lattice_y(col: int) -> float:
    """World Y of lattice column `col`."""
    return (LATTICE_ORIGIN - col) * 25.0 / 12.0


def world_to_lattice(x: float, y: float) -> tuple[float, float]:
    """Fractional lattice (row, col) of a world point."""
    return (LATTICE_ORIGIN - x * 12.0 / 25.0, LATTICE_ORIGIN - y * 12.0 / 25.0)


def tile_of(x: float, y: float) -> tuple[int, int]:
    """Tile (tx, ty) holding a world point."""
    return (int(math.floor(32.0 - y / TILE_SIZE)), int(math.floor(32.0 - x / TILE_SIZE)))


def tile_bounds(tx: int, ty: int) -> tuple[float, float, float, float]:
    """(min_x, max_x, min_y, max_y) of a tile in world coordinates."""
    max_x = lattice_x(ty * LATTICE_PER_TILE)
    max_y = lattice_y(tx * LATTICE_PER_TILE)
    return (max_x - TILE_SIZE, max_x, max_y - TILE_SIZE, max_y)


def chunk_top_left(tx: int, ty: int, ix: int, iy: int) -> tuple[float, float]:
    """World (x, y) of a chunk's first vertex, as CMapChunk::Create computes it."""
    return (lattice_x((ty * 16 + iy) * LATTICE_PER_CHUNK), lattice_y((tx * 16 + ix) * LATTICE_PER_CHUNK))


def world_to_file(x: float, y: float, z: float) -> tuple[float, float, float]:
    """World position -> MDDF/MODF position."""
    return (ZERO - y, z, ZERO - x)


def file_to_world(px: float, py: float, pz: float) -> tuple[float, float, float]:
    """MDDF/MODF position -> world position (CMap::CreateDoodadDef)."""
    return (ZERO - pz, ZERO - px, py)


def quantize_height(h: float) -> float:
    """Round a height to HEIGHT_QUANTUM.

    Multiples of 1/64 below 2^17 are exact float32 values, so base + offset in the client's float32 arithmetic gives
    back the same number on both sides of every chunk edge.
    """
    return math.floor(h / HEIGHT_QUANTUM + 0.5) * HEIGHT_QUANTUM


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def smoothstep(t: float) -> float:
    """Cubic ease 0..1 (clamped)."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def _sin_poly(r: float) -> float:
    # Taylor series of sin around 0 for |r| <= pi/4; the error is below 1e-16.
    r2 = r * r
    term = r
    total = r
    for n in range(1, 12):
        term = -term * r2 / ((2 * n) * (2 * n + 1))
        total += term
    return total


def _cos_poly(r: float) -> float:
    r2 = r * r
    term = 1.0
    total = 1.0
    for n in range(1, 12):
        term = -term * r2 / ((2 * n - 1) * (2 * n))
        total += term
    return total


_PI = 3.141592653589793


def dsin(deg: float) -> float:
    """sin of an angle in degrees, using only exact IEEE operations."""
    a = math.fmod(deg, 360.0)
    if a < 0.0:
        a += 360.0
    octant = int(a // 45.0)
    rem = a - octant * 45.0
    if octant % 2 == 1:
        rem = rem - 45.0
    r = rem * _PI / 180.0
    # a = octant * 45 + rem (rem in [-45, 45)); rotate by multiples of 90 degrees.
    quarter = (octant + 1) // 2
    if quarter % 4 == 0:
        return _sin_poly(r)
    if quarter % 4 == 1:
        return _cos_poly(r)
    if quarter % 4 == 2:
        return -_sin_poly(r)
    return -_cos_poly(r)


def dcos(deg: float) -> float:
    """cos of an angle in degrees, using only exact IEEE operations."""
    return dsin(deg + 90.0)
