"""WDT and WDL writers.

WDT (CMap::LoadWdt reads it sequentially): MVER(18), MPHD (32 bytes), MAIN (64 x 64 entries of {flags, asyncId},
entry 64 * ty + tx, flag 0x1 = the tile has an ADT), then an empty MWMO as Blizzard's terrain maps have (only read
when MPHD flag 0x1, global WMO, is set). MPHD flags = 0:
- 0x1 (global WMO) off: this is a terrain map;
- 0x2 (MCCV vertex colours) off: no MCCV is written;
- 0x4 (big alpha) off: the alpha maps are 4-bit (2048 bytes); with 0x4 the client would expect 8-bit maps
  (CMapRenderChunk::CreateShaderTexture genFormat 2) and needs MCNK 0x8000 on every chunk;
- 0x8 (doodad refs sorted by size) off: CWorldScene::CullDoodadsExterior would stop early on unsorted refs.

WDL (CMapLowDetail::Load): MVER(18), MWMO, MWID, MODF (all empty), MAOF (4096 absolute offsets of each tile's MARE
chunk, 0 = no tile, index 64 * ty + tx), then per tile MARE (17 x 17 heights at chunk corners, then 16 x 16 at
chunk centres, int16 yards) and MAHO (16 rows of 16 bits, set = chunk drawn in the second, culled pass; MapForge
sets it for chunks that are all hole).
"""

from __future__ import annotations

import struct

from . import coords
from .adt import VERSION, chunk


def build_wdt(spec) -> bytes:
    main = bytearray(64 * 64 * 8)
    for tx, ty in spec.tiles:
        struct.pack_into("<II", main, (64 * ty + tx) * 8, 1, 0)
    return (chunk("MVER", struct.pack("<I", VERSION)) + chunk("MPHD", bytes(32)) + chunk("MAIN", bytes(main))
            + chunk("MWMO", b""))


def _i16(h: float) -> int:
    n = int(h + 0.5) if h >= 0.0 else -int(-h + 0.5)
    return -32768 if n < -32768 else 32767 if n > 32767 else n


def build_wdl(spec, grid, holes_by_tile: dict) -> bytes:
    out = bytearray()
    out += chunk("MVER", struct.pack("<I", VERSION))
    out += chunk("MWMO", b"") + chunk("MWID", b"") + chunk("MODF", b"")
    maof_pos = len(out)
    out += chunk("MAOF", bytes(4096 * 4))
    offsets = [0] * 4096
    for tx, ty in spec.tiles:
        r0 = ty * coords.LATTICE_PER_TILE
        c0 = tx * coords.LATTICE_PER_TILE
        heights = []
        for r in range(17):
            for c in range(17):
                heights.append(_i16(grid.get(r0 + 16 * r, c0 + 16 * c)))
        for r in range(16):
            for c in range(16):
                heights.append(_i16(grid.get(r0 + 16 * r + 8, c0 + 16 * c + 8)))
        offsets[64 * ty + tx] = len(out)
        out += chunk("MARE", struct.pack("<545h", *heights))
        holes = holes_by_tile.get((tx, ty), {})
        rows = []
        for iy in range(16):
            bits = 0
            for ix in range(16):
                if holes.get((ix, iy), 0) == 0xFFFF:
                    bits |= 1 << ix
            rows.append(bits)
        out += chunk("MAHO", struct.pack("<16H", *rows))
    out[maof_pos + 8:maof_pos + 8 + 4096 * 4] = struct.pack("<4096I", *offsets)
    return bytes(out)
