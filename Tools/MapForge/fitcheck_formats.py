"""Readers for the fit check (fitcheck.py): terrain heights from 3.3.5 ADTs, split modern root ADTs and AzerothCore's
server .map files, plus Map.dbc / AreaTable.dbc and WDT tile lists. Python 3 standard library only.

Coordinates (the client's and the server's, see terrain/coords.py): world X points north, Y west. A map is a 64 x 64
grid of tiles of 533.3333 yd with its corner at X = Y = 17066.6667 (32 tiles from the centre). The server names a
tile's file `{map:03}{gx:02}{gy:02}.map` with gx = int(32 - x / 533.3333) (the ADT's second number, ty) and
gy = int(32 - y / 533.3333) (the ADT's first number, tx): `<Dir>_<tx>_<ty>.adt` is `{map}{ty}{tx}.map`.

Every source becomes a TileGrid: the 129 x 129 outer (V9) and 128 x 128 inner (V8) heights of one tile, as the
server holds them (GridTerrainData::LoadHeightData), with the chunk holes and area ids. An ADT is turned into the
grid the way map_extractor's ConvertADT does it (MCNK base height + MCVT, heights below -500 raised to -500, a tile
flatter than 0.005 yd stored flat), so "new ground" is what the server would read after extracting the new files.
TileGrid.height() is GridTerrainData::getHeight: the same cell and triangle choice, and the same hole test.

Water: a .map's MLIQ section, and what ConvertADT would write from a 3.3.5 ADT's MCLQ and MH2O, become a
LiquidGrid; LiquidGrid.cells() is the water the world server reads from it per cell (GridTerrainData::GetLiquidData:
the chunk's liquid entry and flags, the cell's level), so two tiles' water can be compared cell by cell.

A 3.3.5 ADT that map_extractor would refuse (adt.cpp prepareLoadedData: MVER 18, MHDR of 64 bytes, MCIN where
MHDR.offsMCIN points, an MCNK at every MCIN slot, an MCVT of 580 bytes at offsMCVT, an MCLQ at offsMCLQ, MH2O and
MFBO where MHDR points) raises ExtractorRefusal: the extractor would write no .map file for it (or crash on it).

A file cut short or damaged raises FormatError (never struct.error), so the fit check can note it and go on.
"""

from __future__ import annotations

import functools
import math
import os
import re
import struct
from array import array

TILE_SIZE = 1600.0 / 3.0  # SIZE_OF_GRIDS
CHUNK_SIZE = TILE_SIZE / 16.0
MAP_RESOLUTION = 128
ZERO = 32.0 * TILE_SIZE
CENTER_GRID_ID = 32
INVALID_HEIGHT = -100000.0  # GridTerrainData.h
MIN_HEIGHT_CLAMP = -500.0  # map_extractor CONF_use_minHeight
FLAT_DELTA = 0.005  # map_extractor CONF_flat_height_delta_limit

MAP_HEIGHT_NO_HEIGHT = 0x1
MAP_HEIGHT_AS_INT16 = 0x2
MAP_HEIGHT_AS_INT8 = 0x4
MAP_HEIGHT_HAS_FLIGHT_BOUNDS = 0x8
MAP_AREA_NO_AREA = 0x1

MCNK_HIGH_RES_HOLES = 0x10000
# Split roots: the Bleakhold client merges them with wxl::modern::adt::Options::highResHoles off
# (Engine/Source/ModernAssets/ModernAssets.cpp AdtOptions), so AdtMerge keeps the low-res holes at 0x3C.
SPLIT_HIGH_RES_HOLES = False
NAN = float("nan")

ROOT_ADT_RE = re.compile(r"^(?P<name>.+)_(?P<tx>\d{1,2})_(?P<ty>\d{1,2})\.adt$", re.IGNORECASE)
MAP_FILE_RE = re.compile(r"^(?P<map>\d{3,})(?P<gx>\d{2})(?P<gy>\d{2})\.map$", re.IGNORECASE)


class FormatError(Exception):
    pass


class ExtractorRefusal(FormatError):
    """map_extractor would not convert this ADT: loadFile prints "Error loading" and ConvertADT writes no .map file
    for it, or (crash) the extractor crashes on it, which ends the whole extraction. why: what is wrong, in words."""

    def __init__(self, where: str, why: str, crash: bool = False):
        self.where, self.why, self.crash = where, why, crash
        if crash:
            text = (f"{where}: map_extractor would crash on it ({why}); that ends the whole extraction, and no .map "
                    f"file is written for it")
        else:
            text = f"{where}: map_extractor would refuse it ({why}), so it writes no .map file for it"
        super().__init__(text)

    def short(self) -> str:
        """The message without the file name."""
        return str(self)[len(self.where) + 2:]


def _damage_is_format_error(fn):
    """struct.unpack_from at an offset read from the file raises struct.error (not a ValueError) when the file is
    cut short or damaged; turn that, and the like, into a FormatError naming the file."""

    @functools.wraps(fn)
    def wrapper(src, *args, **kwargs):
        try:
            return fn(src, *args, **kwargs)
        except (struct.error, ValueError, IndexError, OverflowError) as e:
            if isinstance(src, (bytes, bytearray)):
                where = kwargs.get("name") or (args[2] if len(args) > 2 and args[2] else "<adt>")
            else:
                where = src
            raise FormatError(f"{where}: cut short or damaged ({e})") from e

    return wrapper


# ----------------------------------------------------------------------------------------------- coordinates

def grid_of(x: float, y: float) -> tuple[int, int]:
    """(gx, gy) of the server's file for a world point (Acore::ComputeGridCoord: int() truncates, then max 0)."""
    return (max(0, int(CENTER_GRID_ID - x / TILE_SIZE)), max(0, int(CENTER_GRID_ID - y / TILE_SIZE)))


def tile_of(x: float, y: float) -> tuple[int, int]:
    """ADT tile (tx, ty) holding a world point."""
    gx, gy = grid_of(x, y)
    return (gy, gx)


def tile_top_left(tx: int, ty: int) -> tuple[float, float]:
    """World (x, y) of a tile's north-west corner."""
    return (ZERO - ty * TILE_SIZE, ZERO - tx * TILE_SIZE)


def vertex_world(tx: int, ty: int, row: float, col: float) -> tuple[float, float]:
    """World (x, y) of V9 grid point (row, col) of a tile (row along -X, col along -Y; 128 cells per tile)."""
    top_x, top_y = tile_top_left(tx, ty)
    return (top_x - row * TILE_SIZE / MAP_RESOLUTION, top_y - col * TILE_SIZE / MAP_RESOLUTION)


def map_file_name(map_id: int, tx: int, ty: int) -> str:
    return f"{map_id:03}{ty:02}{tx:02}.map"


# ----------------------------------------------------------------------------------------------- the grid

class TileGrid:
    """One tile's heights in the server's layout.

    kind: "flat" (one height), "uint8", "uint16" (stored integers with base + step) or "float".
    v9[row * 129 + col], v8[row * 128 + col]: stored values (ints for uint8/uint16; floats, NaN = no chunk).
    holes: 256 per-chunk masks of 64 bits (bit = square row * 8 + col; a 3.3.5 low-res bit covers 2 x 2 squares),
    or None. areas: 256 area ids (chunk iy * 16 + ix), or None. liquid: a LiquidGrid, or None (no water); when
    liquid_note is set the water was not read at all (it is unknown).
    """

    __slots__ = ("tx", "ty", "kind", "base", "mult", "v9", "v8", "holes", "areas", "source", "notes", "issues",
                 "liquid", "liquid_note")

    def __init__(self, tx, ty, kind, base, mult, v9, v8, holes, areas, source="", notes=None, issues=None,
                 liquid=None, liquid_note=None):
        self.tx, self.ty = tx, ty
        self.kind = kind
        self.base = base
        self.mult = mult
        self.v9 = v9
        self.v8 = v8
        self.holes = holes
        self.areas = areas
        self.source = source
        self.notes = notes or []
        self.issues = issues or {}  # what was odd about the file: {issue: number of chunks}
        self.liquid = liquid  # LiquidGrid, or None: no water
        self.liquid_note = liquid_note  # why the water was not read (it is then unknown, not "none")

    @property
    def step(self) -> float:
        """The rounding step of the stored heights: map_extractor packs a tile with less than 2 yd of relief as uint8
        and one with less than 2048 yd as uint16, int((h - min) * steps / relief + 0.5), so a stored height can be off
        by half a step (1500 yd of relief: 0.0114 yd). 0 for float and flat grids."""
        return self.mult if self.kind in ("uint8", "uint16") else 0.0

    # GridTerrainData::isHole
    def is_hole(self, row: int, col: int) -> bool:
        if self.holes is None:
            return False
        mask = self.holes[(row >> 3) * 16 + (col >> 3)]
        return bool(mask and (mask >> ((row & 7) * 8 + (col & 7))) & 1)

    def v9_height(self, i: int) -> float:
        if self.kind == "flat":
            return self.base
        v = self.v9[i]
        return v if self.kind == "float" else v * self.mult + self.base

    def v8_height(self, i: int) -> float:
        if self.kind == "flat":
            return self.base
        v = self.v8[i]
        return v if self.kind == "float" else v * self.mult + self.base

    def height(self, x: float, y: float) -> float | None:
        """GridTerrainData::getHeight at world (x, y), or None where the server gets INVALID_HEIGHT (a hole)."""
        if self.kind == "flat":
            return self.base  # getHeightFromFlat: no hole test
        fx = MAP_RESOLUTION * (32 - x / TILE_SIZE)
        fy = MAP_RESOLUTION * (32 - y / TILE_SIZE)
        x_int = int(fx)
        y_int = int(fy)
        fx -= x_int
        fy -= y_int
        x_int &= MAP_RESOLUTION - 1
        y_int &= MAP_RESOLUTION - 1
        if self.is_hole(x_int, y_int):
            return None
        v9, v8 = self.v9, self.v8
        h5 = 2 * v8[x_int * 128 + y_int]
        if fx + fy < 1:
            if fx > fy:
                h1 = v9[x_int * 129 + y_int]
                h2 = v9[(x_int + 1) * 129 + y_int]
                a, b, c = h2 - h1, h5 - h1 - h2, h1
            else:
                h1 = v9[x_int * 129 + y_int]
                h3 = v9[x_int * 129 + y_int + 1]
                a, b, c = h5 - h1 - h3, h3 - h1, h1
        else:
            if fx > fy:
                h2 = v9[(x_int + 1) * 129 + y_int]
                h4 = v9[(x_int + 1) * 129 + y_int + 1]
                a, b, c = h2 + h4 - h5, h4 - h2, h5 - h4
            else:
                h3 = v9[x_int * 129 + y_int + 1]
                h4 = v9[(x_int + 1) * 129 + y_int + 1]
                a, b, c = h4 - h3, h3 + h4 - h5, h5 - h4
        h = a * fx + b * fy + c
        if self.kind != "float":
            h = h * self.mult + self.base
        if h != h:  # NaN: the ADT had no MCNK there
            return None
        return float(h)

    def area_at(self, x: float, y: float) -> int | None:
        """GridTerrainData::getArea (the 16 x 16 chunk area ids)."""
        if self.areas is None:
            return None
        lx = int(16 * (32 - x / TILE_SIZE)) & 15
        ly = int(16 * (32 - y / TILE_SIZE)) & 15
        return self.areas[lx * 16 + ly]

    def chunk_area(self, iy: int, ix: int) -> int | None:
        return None if self.areas is None else self.areas[iy * 16 + ix]


def _lowres_to_highres(mask16: int) -> int:
    out = 0
    if not mask16:
        return 0
    for hy in range(4):
        for hx in range(4):
            if mask16 >> (4 * hy + hx) & 1:
                for r in (2 * hy, 2 * hy + 1):
                    for c in (2 * hx, 2 * hx + 1):
                        out |= 1 << (r * 8 + c)
    return out


# ----------------------------------------------------------------------------------------------- water

# map_extractor System.cpp: the liquid flags of a chunk, and the MLIQ header flags
LIQ_WATER, LIQ_OCEAN, LIQ_MAGMA, LIQ_SLIME, LIQ_DARK = 0x01, 0x02, 0x04, 0x08, 0x10
LIQ_UNKNOWN = 0x100  # an MH2O chunk's flags when no LiquidType.dbc says its sound bank (never in a .map)
MAP_LIQUID_NO_TYPE = 0x1
MAP_LIQUID_NO_HEIGHT = 0x2
FLAT_LIQUID_DELTA = 0.001  # CONF_flat_liquid_delta_limit
DRY_LEVEL = MIN_HEIGHT_CLAMP  # ConvertADT writes -500 for every cell of the liquid box without water
LIQ_FLAG_NAMES = ((LIQ_WATER, "water"), (LIQ_OCEAN, "ocean"), (LIQ_MAGMA, "magma"), (LIQ_SLIME, "slime"),
                  (LIQ_DARK, "dark"))


class LiquidGrid:
    """One tile's water as its .map file holds it (map_liquidHeader and its data): per chunk a liquid entry and
    flags (256, chunk row * 16 + column), a box of cells (off_x, off_y = first column and row, width x height) with
    one level per cell (heights, row by row) or one level for all (heights None). flags_known: False when an MH2O
    chunk's flags could not be worked out (no LiquidType.dbc); then only entries and levels are compared."""

    __slots__ = ("entry", "flags", "off_x", "off_y", "width", "height", "level", "heights", "flags_known")

    def __init__(self, entry, flags, off_x, off_y, width, height, level, heights, flags_known=True):
        self.entry, self.flags = list(entry), list(flags)
        self.off_x, self.off_y, self.width, self.height = off_x, off_y, width, height
        self.level = level
        self.heights = heights
        self.flags_known = flags_known

    def same_data(self, other: "LiquidGrid") -> bool:
        return (self.entry == other.entry and self.flags == other.flags and
                (self.off_x, self.off_y, self.width, self.height) == (other.off_x, other.off_y, other.width,
                                                                       other.height) and
                self.level == other.level and
                (self.heights is None) == (other.heights is None) and
                (self.heights is None or list(self.heights) == list(other.heights)))

    def cells(self) -> list:
        """The water the world server reads, per cell (row * 128 + column, rows along -X as the heights):
        (entry, flags, level), or None where it finds none (GridTerrainData::GetLiquidData: a chunk without a
        liquid entry or flags, a cell outside the box, or a cell ConvertADT marked dry with -500)."""
        out = [None] * (MAP_RESOLUTION * MAP_RESOLUTION)
        wet = [bool(e or f) for e, f in zip(self.entry, self.flags)]
        if not any(wet):
            return out
        for lr in range(self.height):
            row = lr + self.off_y
            if row >= MAP_RESOLUTION:
                break
            for lc in range(self.width):
                col = lc + self.off_x
                if col >= MAP_RESOLUTION:
                    break
                ci = (row >> 3) * 16 + (col >> 3)
                if not wet[ci]:
                    continue
                level = self.heights[lr * self.width + lc] if self.heights is not None else self.level
                if level <= DRY_LEVEL + 1e-3:
                    continue
                out[row * MAP_RESOLUTION + col] = (self.entry[ci], self.flags[ci], level)
        return out


def liquid_flag_names(flags: int) -> str:
    if flags & LIQ_UNKNOWN:
        return "unknown"
    return "+".join(n for bit, n in LIQ_FLAG_NAMES if flags & bit) or "none"


def pack_liquid(show, entry, flags, height, flags_known=True) -> LiquidGrid | None:
    """ConvertADT's "Pack liquid data" on its working arrays: show (128 x 128 cells, row * 128 + column), entry
    and flags (256 chunks), height (129 x 129 vertices, row * 129 + column). None: it writes no MLIQ section."""
    first_e, first_f = entry[0], flags[0]
    full_type = any(e != first_e or f != first_f for e, f in zip(entry, flags))
    if first_f == 0 and not full_type:
        return None
    min_x = min_y = 255
    max_x = max_y = 0
    max_h, min_h = -20000.0, 20000.0
    for y in range(MAP_RESOLUTION):
        for x in range(MAP_RESOLUTION):
            if show[y * MAP_RESOLUTION + x]:
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
                h = height[y * 129 + x]
                max_h, min_h = max(max_h, h), min(min_h, h)
            else:
                height[y * 129 + x] = DRY_LEVEL
                min_h = min(min_h, DRY_LEVEL)
    width = (max_x - min_x + 2) & 0xFF  # uint8, as the header stores it
    rows = (max_y - min_y + 2) & 0xFF
    hflags = 0
    if max_h == min_h or max_h - min_h < FLAT_LIQUID_DELTA:
        hflags |= MAP_LIQUID_NO_HEIGHT
    if not full_type:
        entry, flags = [first_e] * 256, [first_f] * 256
    heights = None
    if not hflags & MAP_LIQUID_NO_HEIGHT:
        heights = [height[(r + min_y) * 129 + min_x + c] if (r + min_y) < 129 and min_x + c < 129 else 0.0
                   for r in range(rows) for c in range(width)]
    return LiquidGrid(entry, flags, min_x, min_y, width, rows, min_h, heights, flags_known)


def read_liquid_types(path: str) -> dict[int, int]:
    """{liquid type id: its sound bank} from LiquidType.dbc (field 0 and 3), as ReadLiquidTypeTableDBC reads it:
    0 water, 1 ocean, 2 magma, 3 slime."""
    recs, _strings, fields = read_dbc(path)
    if fields < 4:
        raise FormatError(f"{path}: too few fields for LiquidType.dbc")
    return {r[0]: r[3] for r in recs}


# ----------------------------------------------------------------------------------------------- server .map

@_damage_is_format_error
def read_map_file(path: str, tx: int | None = None, ty: int | None = None) -> TileGrid:
    """An AzerothCore .map file (map_fileheader version 9), in every storage form map_extractor writes."""
    with open(path, "rb") as f:
        d = f.read()
    if len(d) < 44:
        raise FormatError(f"{path}: too short for a .map header")
    (magic, version, _build, area_ofs, _area_size, height_ofs, _hsize, liq_ofs, _liq_size, holes_ofs,
     holes_size) = struct.unpack_from("<4s10I", d, 0)
    if magic != b"MAPS" or version != 9:
        raise FormatError(f"{path}: not a version 9 .map file (magic {magic!r}, version {version})")
    if tx is None or ty is None:
        m = MAP_FILE_RE.match(os.path.basename(path))
        if m:
            ty, tx = int(m.group("gx")), int(m.group("gy"))
    areas = None
    if area_ofs:
        amagic, aflags, garea = struct.unpack_from("<4sHH", d, area_ofs)
        if amagic != b"AREA":
            raise FormatError(f"{path}: bad AREA section")
        if aflags & MAP_AREA_NO_AREA:
            areas = [garea] * 256
        else:
            areas = list(struct.unpack_from("<256H", d, area_ofs + 8))
    if not height_ofs:
        raise FormatError(f"{path}: no height section")
    hmagic, hflags, grid_h, grid_max = struct.unpack_from("<4sIff", d, height_ofs)
    if hmagic != b"MHGT":
        raise FormatError(f"{path}: bad MHGT section")
    p = height_ofs + 16
    if hflags & MAP_HEIGHT_NO_HEIGHT:
        kind, mult, v9, v8 = "flat", 0.0, None, None
    elif hflags & MAP_HEIGHT_AS_INT16:
        kind = "uint16"
        mult = (grid_max - grid_h) / 65535
        v9 = array("H")
        v9.frombytes(d[p:p + 129 * 129 * 2])
        v8 = array("H")
        v8.frombytes(d[p + 129 * 129 * 2:p + 129 * 129 * 2 + 128 * 128 * 2])
    elif hflags & MAP_HEIGHT_AS_INT8:
        kind = "uint8"
        mult = (grid_max - grid_h) / 255
        v9 = array("B", d[p:p + 129 * 129])
        v8 = array("B", d[p + 129 * 129:p + 129 * 129 + 128 * 128])
    else:
        kind, mult = "float", 1.0
        v9 = array("f")
        v9.frombytes(d[p:p + 129 * 129 * 4])
        v8 = array("f")
        v8.frombytes(d[p + 129 * 129 * 4:p + 129 * 129 * 4 + 128 * 128 * 4])
    if v9 is not None and (len(v9) != 129 * 129 or len(v8) != 128 * 128):
        raise FormatError(f"{path}: the {kind} height section is cut short")
    if v9 is not None and array("H").itemsize != 2:  # pragma: no cover - every platform Python runs on
        raise FormatError("array('H') is not 16-bit here")
    if struct.pack("=H", 1) != struct.pack("<H", 1):  # pragma: no cover - big-endian host
        for a in (v9, v8):
            if a is not None and a.typecode != "B":
                a.byteswap()
    holes = None
    if holes_ofs and holes_size:
        low = struct.unpack_from("<256H", d, holes_ofs)
        if any(low):
            holes = [_lowres_to_highres(m) for m in low]
    liquid = _read_mliq(d, liq_ofs, path) if liq_ofs else None
    return TileGrid(tx, ty, kind, float(grid_h), mult, v9, v8, holes, areas, source=path, liquid=liquid)


def _read_mliq(d: bytes, ofs: int, path: str) -> LiquidGrid:
    """The MLIQ section as GridTerrainData::LoadLiquidData reads it."""
    magic, lflags, gflags, gentry, off_x, off_y, width, rows, level = struct.unpack_from("<4sBBHBBBBf", d, ofs)
    if magic != b"MLIQ":
        raise FormatError(f"{path}: bad MLIQ section")
    q = ofs + 16
    if lflags & MAP_LIQUID_NO_TYPE:
        entry, flags = [gentry] * 256, [gflags] * 256
    else:
        entry = list(struct.unpack_from("<256H", d, q))
        flags = list(struct.unpack_from("<256B", d, q + 512))
        q += 512 + 256
    heights = None
    if not lflags & MAP_LIQUID_NO_HEIGHT:
        heights = list(struct.unpack_from(f"<{width * rows}f", d, q))
    if lflags & MAP_LIQUID_NO_TYPE and not gflags:
        entry = [0] * 256  # GetLiquidData reads no water at all without flags (and no per-chunk table)
    return LiquidGrid(entry, flags, off_x, off_y, width, rows, level, heights)


def scan_map_folder(folder: str) -> dict[int, dict[tuple[int, int], str]]:
    """{map id: {(tx, ty): path}} of every .map file in a server maps folder."""
    out: dict[int, dict[tuple[int, int], str]] = {}
    if not os.path.isdir(folder):
        return out
    for name in os.listdir(folder):
        m = MAP_FILE_RE.match(name)
        if m:
            gx, gy = int(m.group("gx")), int(m.group("gy"))
            out.setdefault(int(m.group("map")), {})[(gy, gx)] = os.path.join(folder, name)
    return out


# ----------------------------------------------------------------------------------------------- ADTs

def _iff(data: bytes, start: int = 0, end: int | None = None):
    """Top-level IFF chunks: (magic as read in reverse, i.e. 'MCNK', payload offset, size)."""
    end = len(data) if end is None else end
    pos = start
    while pos + 8 <= end:
        magic = data[pos:pos + 4][::-1]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        yield magic, pos + 8, size
        pos += 8 + size


_PLAUSIBLE = re.compile(rb"^[A-Z0-9]{4}$")


def _mcvt_at(d: bytes, mcnk_pos: int, mcnk_end: int, ofs_height: int) -> int | None:
    """Payload offset of the MCVT the header's offset points at, or None when it points at none."""
    p = mcnk_pos + ofs_height
    if ofs_height and p + 8 + 580 <= mcnk_end + 8 and d[p:p + 4] == b"TVCM":
        return p + 8
    return None


def _find_mcvt(d: bytes, mcnk_pos: int, mcnk_end: int) -> int | None:
    """Payload offset of the MCNK's MCVT found without the header offset: walk the sub-chunks by size (the 3.3.5
    MCNR's 13 bytes not counted in its size are stepped over), else scan."""
    pos = mcnk_pos + 8 + 128
    while pos + 8 <= mcnk_end:
        magic = d[pos:pos + 4]
        if not _PLAUSIBLE.match(magic):
            break
        size = struct.unpack_from("<I", d, pos + 4)[0]
        if magic == b"TVCM":
            return pos + 8 if size >= 580 and pos + 8 + 580 <= mcnk_end else None
        nxt = pos + 8 + size
        if magic == b"RNCM" and size == 435 and not _PLAUSIBLE.match(d[nxt:nxt + 4] or b"????"):
            nxt += 13
        pos = nxt
    i = d.find(b"TVCM", mcnk_pos + 8 + 128, mcnk_end)
    if i >= 0 and struct.unpack_from("<I", d, i + 4)[0] >= 580 and i + 8 + 580 <= mcnk_end:
        return i + 8
    return None


def _u32(d: bytes, pos: int) -> int:
    return struct.unpack_from("<I", d, pos)[0]


def _u64_padded(d: bytes, pos: int) -> int:
    """A u64 read the way map_extractor reads it (whatever follows; zeros past the end of the file)."""
    return int.from_bytes(d[pos:pos + 8].ljust(8, b"\0"), "little")


def _magic_at(d: bytes, pos: int) -> str:
    raw = d[pos:pos + 4][::-1] if 0 <= pos <= len(d) - 4 else b""
    return raw.decode("latin-1") if _PLAUSIBLE.match(raw or b"?") else (raw.hex() or "nothing")


def _check_335(d: bytes, where: str) -> tuple[int, list[int]]:
    """map_extractor's checks of a 3.3.5 ADT, in its order (FileLoader, ADT_file, adt_MHDR, adt_MCIN, adt_MCNK,
    adt_MCVT, adt_MCLQ, adt_MH2O, adt_MFBO prepareLoadedData), then what makes ConvertADT crash. Returns (MHDR
    payload offset, the MCNK chunk start of each MCIN slot); raises ExtractorRefusal."""
    n = len(d)

    def refuse(why):
        raise ExtractorRefusal(where, why)

    def crash(why):
        raise ExtractorRefusal(where, why, crash=True)

    def expect(pos, magic, what):
        if pos < 0 or pos + 8 > n:
            refuse(f"{what} points outside the file")
        if d[pos:pos + 4] != magic[::-1].encode():
            refuse(f"{what} points at '{_magic_at(d, pos)}', not at an {magic}")

    if n < 12:
        raise FormatError(f"{where}: too short for an ADT")
    version = _u32(d, 8)
    if version != 18:
        refuse(f"MVER version {version}, not 18")
    mhdr = 8 + _u32(d, 4)
    expect(mhdr, "MHDR", "the chunk after MVER")
    if _u32(d, mhdr + 4) != 64:
        refuse(f"MHDR size {_u32(d, mhdr + 4)}, not 64")
    hp = mhdr + 8
    if hp + 64 > n:
        raise FormatError(f"{where}: cut short in MHDR")
    mhdr_flags, ofs_mcin = _u32(d, hp), _u32(d, hp + 4)
    ofs_mfbo, ofs_mh2o = _u32(d, hp + 36), _u32(d, hp + 40)
    cells = []
    if ofs_mcin:
        mcin = hp + ofs_mcin
        expect(mcin, "MCIN", "MHDR's MCIN offset")
        if mcin + 8 + 256 * 16 > n:
            refuse("the MCIN is cut short")
        for slot in range(256):
            ofs = _u32(d, mcin + 8 + slot * 16)
            if not ofs:
                cells.append(None)
                continue
            # adt_MCIN::getMCNK: (MCIN chunk) + offsMCNK - 84, so the offsets count from a file whose MCIN is at 84
            mcnk = mcin + ofs - 84
            what = f"MCIN slot {slot} (chunk {slot % 16},{slot // 16})"
            expect(mcnk, "MCNK", what)
            if mcnk + 8 + 128 > n:
                refuse(f"{what}: its MCNK header is cut short")
            ofs_mcvt, ofs_mclq = _u32(d, mcnk + 8 + 0x14), _u32(d, mcnk + 8 + 0x60)
            if ofs_mcvt:
                expect(mcnk + ofs_mcvt, "MCVT", f"the MCVT offset of chunk {slot % 16},{slot // 16}")
                size = _u32(d, mcnk + ofs_mcvt + 4)
                if size != 580:
                    refuse(f"the MCVT of chunk {slot % 16},{slot // 16} says {size} bytes, not 580")
            if ofs_mclq:
                expect(mcnk + ofs_mclq, "MCLQ", f"the MCLQ offset of chunk {slot % 16},{slot // 16}")
            cells.append(mcnk)
    if ofs_mh2o:
        expect(hp + ofs_mh2o, "MH2O", "MHDR's MH2O offset")
    if ofs_mfbo and mhdr_flags & 1:
        expect(hp + ofs_mfbo, "MFBO", "MHDR's MFBO offset (MHDR flag 0x1)")
    if not ofs_mcin:
        crash("MHDR has no MCIN offset, so ConvertADT reads its chunk table from the MHDR itself")
    empty = [i for i, c in enumerate(cells) if c is None]
    if empty:
        crash(f"MCIN slot {empty[0]} (chunk {empty[0] % 16},{empty[0] // 16}) is empty"
              + (f", and {len(empty) - 1} more" if len(empty) > 1 else "") +
              ": ConvertADT reads every chunk's area id")
    return hp, cells


def _liquid_335(d: bytes, hp: int, cells: list[int], liquid_types: dict | None, where: str, issue):
    """The water ConvertADT would write for this tile (its MCLQ, then MH2O, loops and the packing), or None."""
    show = bytearray(MAP_RESOLUTION * MAP_RESOLUTION)
    entry = [0] * 256
    flags = [0] * 256
    height = [0.0] * (129 * 129)
    any_water = False
    for slot, mcnk in enumerate(cells):
        i, j = slot // 16, slot % 16
        ofs, size = _u32(d, mcnk + 8 + 0x60), _u32(d, mcnk + 8 + 0x64)
        if not ofs or size <= 8:
            continue
        any_water = True
        q = mcnk + ofs
        fl = d[q + 16 + 648:q + 16 + 648 + 64]
        if len(fl) < 64:
            raise FormatError(f"{where}: the MCLQ of chunk {j},{i} is cut short")
        for y in range(8):
            for x in range(8):
                f = fl[y * 8 + x]
                if f != 0x0F:
                    show[(i * 8 + y) * MAP_RESOLUTION + j * 8 + x] = 1
                    if f & 0x80:
                        flags[slot] |= LIQ_DARK
        c_flag = _u32(d, mcnk + 8)
        if c_flag & 0x04:
            entry[slot] = 1
            flags[slot] |= LIQ_WATER
        if c_flag & 0x08:
            entry[slot] = 2
            flags[slot] |= LIQ_OCEAN
        if c_flag & 0x10:
            entry[slot] = 3
            flags[slot] |= LIQ_MAGMA
        for y in range(9):
            for x in range(9):
                height[(i * 8 + y) * 129 + j * 8 + x] = struct.unpack_from("<f", d, q + 16 + (y * 9 + x) * 8 + 4)[0]
    ofs_mh2o = _u32(d, hp + 40)
    flags_known = True
    if ofs_mh2o:
        base = hp + ofs_mh2o + 8  # adt_MH2O offsets count from its payload
        for i in range(16):
            for j in range(16):
                slot = i * 16 + j
                o_inst, used, o_attr = struct.unpack_from("<3I", d, base + slot * 12)
                if not (used and o_inst):
                    continue
                any_water = True
                (ltype, vfmt, _lo, _hi, ox, oy, w, h, o_bits,
                 o_vert) = struct.unpack_from("<HHffBBBBII", d, base + o_inst)
                deep = _u64_padded(d, base + o_attr + 8) if o_attr else 0xFFFFFFFFFFFFFFFF
                mask = _u64_padded(d, base + o_bits) if o_bits else 0xFFFFFFFFFFFFFFFF
                outside = False
                for y in range(h):
                    cy = i * 8 + y + oy
                    for x in range(w):
                        cx = j * 8 + x + ox
                        if mask & 1:
                            if cy < MAP_RESOLUTION and cx < MAP_RESOLUTION:
                                show[cy * MAP_RESOLUTION + cx] = 1
                            else:
                                outside = True
                        mask >>= 1
                entry[slot] = ltype
                if liquid_types is None:
                    flags[slot] |= LIQ_UNKNOWN
                    flags_known = False
                elif ltype not in liquid_types:
                    raise ExtractorRefusal(where, f"the MH2O water of chunk {j},{i} has liquid type {ltype}, which "
                                                  f"LiquidType.dbc does not have: LiquidTypes.at throws", crash=True)
                else:
                    bank = liquid_types[ltype]
                    flags[slot] |= {0: LIQ_WATER, 1: LIQ_OCEAN | (LIQ_DARK if deep else 0), 2: LIQ_MAGMA,
                                    3: LIQ_SLIME}.get(bank, 0)
                    if bank not in (0, 1, 2, 3):
                        issue(f"whose MH2O liquid type has sound bank {bank}, which map_extractor does not know "
                              f"(no water flags)")
                pos = 0
                for y in range(h + 1):
                    cy = i * 8 + y + oy
                    for x in range(w + 1):
                        cx = j * 8 + x + ox
                        if not o_vert or vfmt not in (0, 1):
                            lvl = 0.0  # adt_MH2O::GetLiquidHeight
                        else:
                            lvl = struct.unpack_from("<f", d, base + o_vert + pos * 4)[0]
                        if cy < 129 and cx < 129:
                            height[cy * 129 + cx] = lvl
                        else:
                            outside = True
                        pos += 1
                if outside:
                    issue("whose MH2O water reaches past the tile (map_extractor writes past its arrays there)")
    if not any_water:
        return None, True
    return pack_liquid(show, entry, flags, height, flags_known), flags_known


@_damage_is_format_error
def read_adt(path_or_bytes, tx: int | None = None, ty: int | None = None, name: str = "",
             high_res_holes: bool = SPLIT_HIGH_RES_HOLES, liquid_types: dict | None = None) -> TileGrid:
    """A root ADT, 3.3.5 single-file (MVER MHDR MCIN ... MCNK x 256) or split modern (no MCIN; the MCNKs follow
    each other in the root file; _tex0/_obj0/_obj1/_lod files are not read). Heights = MCNK position z + MCVT.

    3.3.5, as map_extractor reads it: first its checks (_check_335; a file it would refuse or crash on raises
    ExtractorRefusal); the chunk table is where MHDR.offsMCIN points, and MCIN slot i is chunk row i / 16, column
    i % 16 (the header's IndexX/IndexY are not read); the MCVT is where offsMCVT (0x14) points, and a chunk
    without one (offset 0) is flat at its base height; the holes are the 16-bit mask at 0x3C. Flag 0x10000
    (high-res holes, added after 3.3.5) is ignored, as the 3.3.5 client and ConvertADT ignore it. The water is what
    ConvertADT writes from MCLQ and MH2O (liquid_types: LiquidType.dbc's {id: sound bank}; without it an MH2O
    chunk's flags are unknown). Split roots, as the Bleakhold client's AdtMerge turns them into 3.3.5 tiles: the
    n-th MCNK is chunk n (its header indices are rewritten from that), the MCVT is found among the sub-chunks, and
    the holes are the low-res mask unless high_res_holes (AdtMerge's option, off in Bleakhold) and flag 0x10000
    are both set; their water is not read (liquid_note says so)."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        d = bytes(path_or_bytes)
        where = name or "<adt>"
    else:
        where = path_or_bytes
        with open(path_or_bytes, "rb") as f:
            d = f.read()
        if tx is None or ty is None:
            m = ROOT_ADT_RE.match(os.path.basename(path_or_bytes))
            if m:
                tx, ty = int(m.group("tx")), int(m.group("ty"))
    if tx is None or ty is None:
        raise FormatError(f"{where}: tile numbers unknown (the file is not named <map>_<x>_<y>.adt)")
    if d[:4] != b"REVM":
        raise FormatError(f"{where}: not an ADT (no MVER)")
    has_mcin = False
    mcnks: list[tuple[int, int]] = []
    for magic, pos, size in _iff(d):
        if magic == b"MCIN":
            has_mcin = True
        elif magic == b"MCNK":
            mcnks.append((pos - 8, pos + size))
    mhdr = 8 + _u32(d, 4) if len(d) >= 8 else 0
    ofs_mcin = _u32(d, mhdr + 12) if d[mhdr:mhdr + 4] == b"RDHM" and mhdr + 16 <= len(d) else 0
    entries: list[tuple[int, int, int]] = []  # (place: MCIN slot or order in the file, chunk start, chunk end)
    issues: dict[str, int] = {}

    def issue(text):
        issues[text] = issues.get(text, 0) + 1

    liquid = None
    liquid_note = None
    if has_mcin or ofs_mcin:
        layout = "3.3.5"
        hp, cells = _check_335(d, where)
        for i, start in enumerate(cells):
            entries.append((i, start, start + 8 + _u32(d, start + 4)))
        liquid, _known = _liquid_335(d, hp, cells, liquid_types, where, issue)
    else:
        layout = "split"
        for i, (start, end) in enumerate(mcnks[:256]):
            entries.append((i, start, end))
        liquid_note = "the water of split ADTs is not read"
    if not entries:
        raise FormatError(f"{where}: no MCNK chunks")
    v9 = array("f", [NAN]) * (129 * 129)
    v8 = array("f", [NAN]) * (128 * 128)
    holes = [0] * 256
    areas = [0] * 256

    top_x, top_y = tile_top_left(tx, ty)
    seen = set()
    for order, start, end in entries:
        p = start + 8
        if p + 128 > len(d):
            continue
        ix, iy = order % 16, order // 16
        flags, hix, hiy = struct.unpack_from("<3I", d, p)
        ofs_height = struct.unpack_from("<I", d, p + 0x14)[0]
        area_id = struct.unpack_from("<I", d, p + 0x34)[0]
        low_holes = struct.unpack_from("<H", d, p + 0x3C)[0]
        pos_x, pos_y, pos_z = struct.unpack_from("<3f", d, p + 0x68)
        seen.add((ix, iy))
        if (hix, hiy) != (ix, iy):
            issue("whose header index is not their " + ("MCIN slot" if layout == "3.3.5" else "place in the file") +
                  " (the place counts, as " + ("map_extractor" if layout == "3.3.5" else "the client's merge") +
                  " reads it)")
        if abs(pos_x - (top_x - iy * CHUNK_SIZE)) > 0.5 or abs(pos_y - (top_y - ix * CHUNK_SIZE)) > 0.5:
            issue("whose position does not match their place")
        hires = bool(flags & MCNK_HIGH_RES_HOLES)
        if layout == "3.3.5":
            if hires:
                issue("with flag 0x10000 (high-res holes), which the 3.3.5 client and map_extractor ignore: the "
                      "16-bit holes and the MCVT offset are read")
            # _check_335 made sure an offset points at an MCVT of 580 bytes; ConvertADT reads nothing else
            mcvt = start + ofs_height + 8 if ofs_height else None
        else:
            mcvt = None if hires else _mcvt_at(d, start, end, ofs_height)
            if mcvt is None:
                mcvt = _find_mcvt(d, start, end)
        if mcvt is None:
            # ConvertADT: V9/V8 start at the base height and the MCVT is added only when there is one
            issue("without an MCVT: flat at their base height, as map_extractor makes them")
            hs = (0.0,) * 145
        else:
            hs = struct.unpack_from("<145f", d, mcvt)
        base = pos_z
        for r in range(9):
            row = (iy * 8 + r) * 129 + ix * 8
            k = r * 17
            for c in range(9):
                v9[row + c] = base + hs[k + c]
        for r in range(8):
            row = (iy * 8 + r) * 128 + ix * 8
            k = r * 17 + 9
            for c in range(8):
                v8[row + c] = base + hs[k + c]
        if layout == "split" and hires:
            if high_res_holes:
                holes[iy * 16 + ix] = struct.unpack_from("<Q", d, p + 0x14)[0]
            else:
                holes[iy * 16 + ix] = _lowres_to_highres(low_holes)
                issue("with high-res holes (flag 0x10000); the Bleakhold client's merge keeps the low-res holes, "
                      "so those are used")
        else:
            holes[iy * 16 + ix] = _lowres_to_highres(low_holes)
        areas[iy * 16 + ix] = area_id & 0xFFFF
    if len(seen) < 256:
        issues["missing (no ground there)"] = 256 - len(seen)
    notes = [f"{n} chunk(s) {text}" for text, n in issues.items()]
    g = finish_grid(tx, ty, v9, v8, holes, areas, source=where, notes=notes, layout=layout, issues=issues)
    g.liquid, g.liquid_note = liquid, liquid_note
    return g


def finish_grid(tx, ty, v9, v8, holes, areas, source="", notes=None, layout="", issues=None) -> TileGrid:
    """map_extractor's packing decisions on float heights: raise everything below -500 to -500 when the tile goes
    below it, and store a tile flatter than 0.005 yd as one height (whose lookup ignores holes; the holes are
    written all the same, so they are kept)."""
    finite = [h for h in v9 if h == h] + [h for h in v8 if h == h]
    if not finite:
        raise FormatError(f"{source}: no heights")
    lo, hi = min(finite), max(finite)
    if lo < MIN_HEIGHT_CLAMP:
        for a in (v9, v8):
            for i, h in enumerate(a):
                if h < MIN_HEIGHT_CLAMP:
                    a[i] = MIN_HEIGHT_CLAMP
        lo = MIN_HEIGHT_CLAMP
        hi = max(hi, MIN_HEIGHT_CLAMP)
    note = list(notes or [])
    if layout:
        note.insert(0, f"layout {layout}")
    kept = holes if any(holes) else None
    if hi - lo < FLAT_DELTA and len(finite) == len(v9) + len(v8):
        return TileGrid(tx, ty, "flat", lo, 0.0, None, None, kept, areas, source=source, notes=note, issues=issues)
    return TileGrid(tx, ty, "float", 0.0, 1.0, v9, v8, kept, areas, source=source, notes=note, issues=issues)


def root_adts(folder: str, map_name: str | None = None) -> dict[tuple[int, int], str]:
    """{(tx, ty): path} of the root ADTs in a map folder (the split files' _tex0/_obj0/_obj1/_lod are left out)."""
    out = {}
    for name in os.listdir(folder):
        m = ROOT_ADT_RE.match(name)
        if not m:
            continue
        stem = m.group("name")
        if map_name is not None and stem.lower() != map_name.lower():
            continue
        out[(int(m.group("tx")), int(m.group("ty")))] = os.path.join(folder, name)
    return out


def is_root_adt_name(file_name: str, map_name: str) -> tuple[int, int] | None:
    m = ROOT_ADT_RE.match(file_name)
    if not m or m.group("name").lower() != map_name.lower():
        return None
    return int(m.group("tx")), int(m.group("ty"))


@_damage_is_format_error
def read_wdt_tiles(path: str) -> tuple[set[tuple[int, int]], int]:
    """(tiles the WDT's MAIN marks as present, MPHD flags). A WMO-only map has no tiles (MPHD flag 0x1)."""
    with open(path, "rb") as f:
        d = f.read()
    tiles = set()
    mphd = 0
    for magic, pos, size in _iff(d):
        if magic == b"MPHD" and size >= 4:
            mphd = struct.unpack_from("<I", d, pos)[0]
        elif magic == b"MAIN" and size >= 64 * 64 * 8:
            for i in range(64 * 64):
                if struct.unpack_from("<I", d, pos + i * 8)[0] & 1:
                    tiles.add((i % 64, i // 64))
    return tiles, mphd


# ----------------------------------------------------------------------------------------------- DBCs

@_damage_is_format_error
def read_dbc(path: str) -> tuple[list[tuple], bytes, int]:
    """(records as tuples of uint32, string block, field count) of a WDBC file."""
    with open(path, "rb") as f:
        d = f.read()
    if d[:4] != b"WDBC":
        raise FormatError(f"{path}: not a WDBC file")
    n, fields, rec_size, str_size = struct.unpack_from("<4I", d, 4)
    if rec_size != fields * 4:
        raise FormatError(f"{path}: record size {rec_size} is not 4 x {fields} fields")
    body = 20
    recs = [struct.unpack_from(f"<{fields}I", d, body + i * rec_size) for i in range(n)]
    strings = d[body + n * rec_size:body + n * rec_size + str_size]
    return recs, strings, fields


def dbc_string(block: bytes, ofs: int) -> str:
    if ofs <= 0 or ofs >= len(block):
        return ""
    end = block.find(b"\0", ofs)
    return block[ofs:end if end >= 0 else len(block)].decode("utf-8", "replace")


def read_map_dbc(path: str) -> dict[int, str]:
    """{map id: Directory} (Map.dbc field 0 and 1)."""
    recs, strings, fields = read_dbc(path)
    if fields < 2:
        raise FormatError(f"{path}: too few fields for Map.dbc")
    return {r[0]: dbc_string(strings, r[1]) for r in recs}


def read_area_dbc(path: str) -> dict[int, tuple[int, str]]:
    """{area id: (zone id, name)} from AreaTable.dbc (3.3.5: field 2 = parent zone, 11-26 = the names); a zone's
    zone id is its own."""
    recs, strings, fields = read_dbc(path)
    out = {}
    for r in recs:
        name = ""
        for k in range(11, min(27, fields)):
            name = dbc_string(strings, r[k])
            if name:
                break
        zone = r[2] if fields > 2 and r[2] else r[0]
        out[r[0]] = (zone, name)
    return out


def finite(v) -> bool:
    return v is not None and not math.isnan(v)
