"""Tests of the fit check (fitcheck.py, fitcheck_formats.py, fitcheck_source.py, fitcheck_report.py).

Synthetic data only, except where real files are found: ADTs from MapForge's own writer and from small writers here
(3.3.5 single-file with MH2O and MCLQ water, and split modern root), .map files in each storage form map_extractor
writes (written here the way its ConvertADT packs them, with their MLIQ water), made-up Map.dbc/AreaTable.dbc/
LiquidType.dbc rows, and .7z archives made with the system's 7z (skipped when it is missing). When the session
scratchpad holds real map_extractor output (FITCHECK_REAL_DIR), it is compared with the ADTs it was made from; when
it holds a built map_extractor (FITCHECK_MAP_EXTRACTOR), it is run on the test's own ADTs: which ones it refuses, and
the water, heights and holes it writes.
"""

import contextlib
import glob
import hashlib
import io
import json
import math
import os
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

import fitcheck  # noqa: E402
import fitcheck_formats as ff  # noqa: E402
import fitcheck_report as fr  # noqa: E402
import fitcheck_source as fs  # noqa: E402
from terrain import build as tbuild  # noqa: E402
from terrain import validate as tvalidate  # noqa: E402

UNIT = ff.CHUNK_SIZE / 8.0
REAL_DIR = os.environ.get("FITCHECK_REAL_DIR", "")
MAP_EXTRACTOR = os.environ.get("FITCHECK_MAP_EXTRACTOR",
                               os.path.join(REAL_DIR, "ac-tools-build", "src", "tools", "map_extractor")
                               if REAL_DIR else "")
SEVEN_ZIP = fs.find_7z()
# LiquidType.dbc's first rows as the stock 3.3.5 table has them: id 1 water, 2 ocean, 3 magma, 4 slime (field 3, the
# sound bank map_extractor reads); the rest water
LIQUID_ROWS = [(i, f"Liquid{i}", 0, {1: 0, 2: 1, 3: 2, 4: 3}.get(i, 0)) for i in range(1, 22)]
LIQUID_TYPES = {r[0]: r[3] for r in LIQUID_ROWS}


# --------------------------------------------------------------------------------------------- synthetic writers

def tile_lattice(tx, ty, fn):
    """(v9, v8) of a tile from a height function of world (x, y): V9 at the outer vertices, V8 at the inner ones."""
    top_x, top_y = ff.tile_top_left(tx, ty)
    v9 = [fn(top_x - r * UNIT, top_y - c * UNIT) for r in range(129) for c in range(129)]
    v8 = [fn(top_x - (r + 0.5) * UNIT, top_y - (c + 0.5) * UNIT) for r in range(128) for c in range(128)]
    return v9, v8


def mliq(lg):
    """The MLIQ section of a .map file for a LiquidGrid, as ConvertADT stores it (map_liquidHeader, then the entry
    and flags tables unless every chunk is the same, then the levels unless they are all one)."""
    full = len(set(zip(lg.entry, lg.flags))) > 1
    flags = (0 if full else ff.MAP_LIQUID_NO_TYPE) | (ff.MAP_LIQUID_NO_HEIGHT if lg.heights is None else 0)
    out = struct.pack("<4sBBHBBBBf", b"MLIQ", flags, 0 if full else lg.flags[0], 0 if full else lg.entry[0],
                      lg.off_x, lg.off_y, lg.width, lg.height, lg.level)
    if full:
        out += struct.pack("<256H", *lg.entry) + struct.pack("<256B", *lg.flags)
    if lg.heights is not None:
        out += struct.pack(f"<{len(lg.heights)}f", *lg.heights)
    return out


def write_map(path, v9, v8, form="float", holes=None, areas=None, flight=False, liquid=None):
    """A .map file as map_extractor's ConvertADT writes it, in the storage form asked for (liquid: a LiquidGrid)."""
    lo, hi = min(v9 + v8), max(v9 + v8)
    if areas is None or len(set(areas)) == 1:
        area = struct.pack("<4sHH", b"AREA", 1, areas[0] if areas else 0)
    else:
        area = struct.pack("<4sHH", b"AREA", 0, 0) + struct.pack("<256H", *areas)
    flags = {"flat": 1, "uint16": 2, "uint8": 4, "float": 0}[form] | (8 if flight else 0)
    hdr = struct.pack("<4sIff", b"MHGT", flags, lo, hi)
    if form == "float":
        body = struct.pack(f"<{129 * 129}f", *v9) + struct.pack(f"<{128 * 128}f", *v8)
    elif form == "uint16":
        step = 65535 / (hi - lo)
        body = struct.pack(f"<{129 * 129}H", *[int((h - lo) * step + 0.5) for h in v9])
        body += struct.pack(f"<{128 * 128}H", *[int((h - lo) * step + 0.5) for h in v8])
    elif form == "uint8":
        step = 255 / (hi - lo)
        body = bytes(int((h - lo) * step + 0.5) for h in v9) + bytes(int((h - lo) * step + 0.5) for h in v8)
    else:
        body = b""
    height = hdr + body + (struct.pack("<9h", *[500] * 9) + struct.pack("<9h", *[-500] * 9) if flight else b"")
    hole_data = struct.pack("<256H", *holes) if holes and any(holes) else b""
    liq = mliq(liquid) if liquid is not None else b""
    area_ofs = 44
    height_ofs = area_ofs + len(area)
    liq_ofs = height_ofs + len(height) if liq else 0
    holes_ofs = height_ofs + len(height) + len(liq) if hole_data else 0
    head = struct.pack("<4s10I", b"MAPS", 9, 12340, area_ofs, len(area), height_ofs, len(height), liq_ofs, len(liq),
                       holes_ofs, len(hole_data))
    with open(path, "wb") as f:
        f.write(head + area + height + liq + hole_data)


def _chunk(magic, payload, declared=None):
    return magic[::-1].encode() + struct.pack("<I", len(payload) if declared is None else declared) + payload


def _mcnk_header(flags, ix, iy, ofs_height, area, holes, pos, hires=None, mclq=(0, 0)):
    """hires: a 64-bit hole mask written over the height and normal offsets (0x14), as split roots with flag
    0x10000 have it; None writes ofs_height there. mclq: (offsMCLQ, sizeMCLQ) at 0x60."""
    h = bytearray(128)
    struct.pack_into("<3I", h, 0, flags, ix, iy)
    if hires is not None:
        struct.pack_into("<Q", h, 0x14, hires)
    else:
        struct.pack_into("<I", h, 0x14, ofs_height)
    struct.pack_into("<I", h, 0x34, area)
    struct.pack_into("<H", h, 0x3C, holes)
    struct.pack_into("<2I", h, 0x60, *mclq)
    struct.pack_into("<3f", h, 0x68, *pos)
    return bytes(h)


MCLQ_KIND = {"water": 0x04, "ocean": 0x08, "magma": 0x10}  # the MCNK flag ConvertADT turns into entry 1, 2, 3


def _mclq(level, hidden=()):
    """An MCLQ sub-chunk in the 3.3.5 layout (two heights, 9 x 9 (light, height), 8 x 8 flags, 84 bytes); every
    cell shown (flag 0) except hidden ((x, y) cells: 0x0F)."""
    fl = bytearray(64)
    for x, y in hidden:
        fl[y * 8 + x] = 0x0F
    body = struct.pack("<ff", level, level) + b"".join(struct.pack("<If", 0, level) for _ in range(81))
    return _chunk("MCLQ", body + bytes(fl) + bytes(84), declared=0)  # sizeMCLQ in the MCNK header counts


def _mh2o(water):
    """An MH2O chunk: water {(ix, iy): (liquid type, level)}, one instance per chunk over all 8 x 8 cells (no
    exists bitmap), HeightDepth vertices at one level, no attributes."""
    heads = bytearray(256 * 12)
    tail = bytearray()
    for (ix, iy), (ltype, level) in sorted(water.items()):
        inst = 256 * 12 + len(tail)
        tail += struct.pack("<HHffBBBBII", ltype, 0, level, level, 0, 0, 8, 8, 0, inst + 24)
        tail += struct.pack("<81f", *[level] * 81) + bytes(81) + bytes(3)
        struct.pack_into("<III", heads, (iy * 16 + ix) * 12, inst, 1, 0)
    return _chunk("MH2O", bytes(heads) + bytes(tail))


def chunk_heights(tx, ty, ix, iy, fn):
    top_x, top_y = ff.tile_top_left(tx, ty)
    cx, cy = top_x - iy * ff.CHUNK_SIZE, top_y - ix * ff.CHUNK_SIZE
    out = []
    for r in range(9):
        out += [fn(cx - r * UNIT, cy - c * UNIT) for c in range(9)]
        if r < 8:
            out += [fn(cx - (r + 0.5) * UNIT, cy - (c + 0.5) * UNIT) for c in range(8)]
    return cx, cy, out


def adt_335(tx, ty, fn, area=7, holes=None, base_shift=0.0, flags=0, swap_index=False, no_mcvt=(), water=None,
            mclq=None, hires=None):
    """A minimal 3.3.5 single-file ADT: MVER MHDR MCIN MCNK x 256 (MCVT, then MCNR declaring 435 bytes + 13).
    flags: every MCNK's flags (0x10000 keeps the MCVT offset at 0x14, as a converter that copies the flags does);
    swap_index: header IndexX/IndexY swapped (the MCIN slot stays right); no_mcvt: chunks (ix, iy) written without
    an MCVT and with offsMCVT 0; water: MH2O water {(ix, iy): (liquid type, level)} (the chunk at the end, MHDR
    pointing at it); mclq: old-style water {(ix, iy): (kind, level)} with kind a MCLQ_KIND key; hires: {(ix, iy):
    64-bit hole mask} written over 0x14 with flag 0x10000 (a converter that keeps the split layout's header)."""
    out = bytearray(_chunk("MVER", struct.pack("<I", 18)))
    out += _chunk("MHDR", struct.pack("<II", 0, 64) + bytes(56))  # offsMCIN: the MCIN right after it, at 84
    mcin_pos = len(out)
    out += _chunk("MCIN", bytes(256 * 16))
    mcin = bytearray()
    for iy in range(16):
        for ix in range(16):
            cx, cy, hs = chunk_heights(tx, ty, ix, iy, fn)
            base = hs[0] + base_shift
            ofs = 8 + 128
            if (ix, iy) in no_mcvt:
                sub, ofs = b"", 0
            else:
                sub = _chunk("MCVT", struct.pack("<145f", *[h - base for h in hs]))
            sub += _chunk("MCNR", bytes(448), declared=435)
            fl = flags
            lq = (0, 0)
            if mclq and (ix, iy) in mclq:
                kind, level = mclq[(ix, iy)]
                part = _mclq(level)
                lq = (8 + 128 + len(sub), len(part))
                sub += part
                fl |= MCLQ_KIND[kind]
            hole = (holes or {}).get((ix, iy), 0)
            hix, hiy = (iy, ix) if swap_index else (ix, iy)
            hr = (hires or {}).get((ix, iy))
            if hr is not None:
                fl |= ff.MCNK_HIGH_RES_HOLES
            data = _chunk("MCNK", _mcnk_header(fl, hix, hiy, ofs, area, hole, (cx, cy, base), hires=hr, mclq=lq) +
                          sub)
            mcin += struct.pack("<IIII", len(out), len(data), 0, 0)
            out += data
    out[mcin_pos + 8:mcin_pos + 8 + len(mcin)] = mcin
    if water:
        struct.pack_into("<I", out, 20 + 40, len(out) - 20)  # MHDR.offsMH2O, from the MHDR's payload at 20
        out += _mh2o(water)
    return bytes(out)


def map_from_adt(path, data, tx, ty, form="uint16", low_holes=None, liquid_types=None):
    """The .map file map_extractor would write for an ADT (heights, area ids, holes, water), via read_adt."""
    g = ff.read_adt(data, tx, ty, liquid_types=LIQUID_TYPES if liquid_types is None else liquid_types)
    holes = [0] * 256
    for (ix, iy), m in (low_holes or {}).items():
        holes[iy * 16 + ix] = m
    if g.kind == "flat":
        v9, v8 = [g.base] * (129 * 129), [g.base] * (128 * 128)
        form = "flat"
    else:
        v9, v8 = list(g.v9), list(g.v8)
    write_map(path, v9, v8, form, holes=holes, areas=list(g.areas), liquid=g.liquid)
    return g


def adt_split(tx, ty, fn, area=7, hires=None, shuffle=False, low=None):
    """A minimal split modern root ADT: no MCIN; MCNKs in a row; MCCV and a 3.3.5-style MCNR (435 + 13) before the
    MCVT, header height offset left 0 (or the high-res hole mask in its place, with flag 0x10000); low: low-res
    holes at 0x3C."""
    out = bytearray(_chunk("MVER", struct.pack("<I", 18)))
    out += _chunk("MHDR", bytes(64))
    order = [(ix, iy) for iy in range(16) for ix in range(16)]
    if shuffle:
        order = order[::-1]
    for ix, iy in order:
        cx, cy, hs = chunk_heights(tx, ty, ix, iy, fn)
        base = hs[0]
        sub = _chunk("MCCV", bytes(145 * 4)) + _chunk("MCNR", bytes(448), declared=435)
        sub += _chunk("MCVT", struct.pack("<145f", *[h - base for h in hs])) + _chunk("MCSE", b"")
        hr = (hires or {}).get((ix, iy), 0)
        flags = ff.MCNK_HIGH_RES_HOLES if hr else 0
        lo = (low or {}).get((ix, iy), 0)
        out += _chunk("MCNK", _mcnk_header(flags, ix, iy, 0, area, lo, (cx, cy, base), hires=hr if hr else None) + sub)
    out += _chunk("MFBO", bytes(36))
    return bytes(out)


def make_dbc(fields, records, strings):
    block = bytearray(b"\0")
    offsets = {}
    for s in strings:
        if s not in offsets:
            offsets[s] = len(block)
            block += s.encode() + b"\0"
    body = bytearray()
    for rec in records:
        for v in rec:
            body += struct.pack("<I", offsets[v] if isinstance(v, str) else v)
    return b"WDBC" + struct.pack("<4I", len(records), fields, fields * 4, len(block)) + bytes(body) + bytes(block)


def map_dbc(rows):
    """Map.dbc with 66 fields: id, Directory (the rest 0)."""
    recs = [[mid, d] + [0] * 64 for mid, d in rows]
    return make_dbc(66, recs, [d for _m, d in rows])


def liquid_dbc(rows=LIQUID_ROWS):
    """LiquidType.dbc with 4 fields: id, name, flags, sound bank (what map_extractor reads)."""
    return make_dbc(4, [list(r) for r in rows], [r[1] for r in rows])


def area_dbc(rows):
    """AreaTable.dbc with 36 fields: id, map, zone, ..., name at 11."""
    recs = []
    for aid, mid, zone, name in rows:
        r = [aid, mid, zone] + [0] * 33
        r[11] = name
        recs.append(r)
    return make_dbc(36, recs, [r[3] for r in rows])


def wdt(tiles, mphd=0):
    main = bytearray(64 * 64 * 8)
    for tx, ty in tiles:
        struct.pack_into("<I", main, (ty * 64 + tx) * 8, 1)
    return (_chunk("MVER", struct.pack("<I", 18)) + _chunk("MPHD", struct.pack("<I", mphd) + bytes(28)) +
            _chunk("MAIN", bytes(main)))


def put(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def tree_hash(root):
    h = hashlib.sha256()
    for base, _dirs, files in sorted(os.walk(root)):
        for name in sorted(files):
            p = os.path.join(base, name)
            h.update(os.path.relpath(p, root).encode())
            with open(p, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


def gentle(x, y):
    return 40.0 + 0.01 * (x - 0) + 0.02 * (y - 0) + 3.0 * math.sin(x / 37.0) * math.cos(y / 53.0)


def points_in(tx, ty, n=60, seed=1):
    import random
    rnd = random.Random(seed)
    top_x, top_y = ff.tile_top_left(tx, ty)
    return [(top_x - rnd.uniform(0.01, ff.TILE_SIZE - 0.01), top_y - rnd.uniform(0.01, ff.TILE_SIZE - 0.01))
            for _ in range(n)]


# --------------------------------------------------------------------------------------------- formats

class TestMapFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fitcheck-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_names_and_grid(self):
        self.assertEqual(ff.map_file_name(1, 21, 34), "0013421.map")
        self.assertEqual(ff.tile_of(0.1, 0.1), (31, 31))
        self.assertEqual(ff.tile_of(-0.1, -0.1), (32, 32))
        x, y = ff.tile_top_left(32, 48)
        self.assertAlmostEqual(x, ff.ZERO - 48 * ff.TILE_SIZE)
        self.assertEqual(ff.tile_of(x - 1, y - 1), (32, 48))
        m = ff.MAP_FILE_RE.match("90003133.map")
        self.assertEqual((m.group("map"), m.group("gx"), m.group("gy")), ("9000", "31", "33"))

    def test_plane_is_exact(self):
        # the server's triangles reproduce a plane exactly, so every lookup must give the plane's height
        def plane(x, y):
            return 12.5 + 0.03 * x - 0.02 * y

        v9, v8 = tile_lattice(32, 32, plane)
        p = os.path.join(self.tmp, "0003232.map")
        write_map(p, v9, v8, "float")
        g = ff.read_map_file(p)
        self.assertEqual((g.kind, g.tx, g.ty), ("float", 32, 32))
        for x, y in points_in(32, 32, 200):
            self.assertAlmostEqual(g.height(x, y), plane(x, y), delta=0.01)

    def test_every_storage_form(self):
        cases = [("float", gentle, 1e-3), ("uint16", gentle, 0.01),
                 ("uint8", lambda x, y: 5.0 + 0.6 * math.sin(x / 20.0) + 0.5 * math.cos(y / 30.0), 0.01),
                 ("flat", lambda x, y: 3.25, 1e-6)]
        for form, fn, tol in cases:
            with self.subTest(form=form):
                v9, v8 = tile_lattice(31, 33, fn)
                p = os.path.join(self.tmp, f"0013331.{form}.map")
                write_map(p, v9, v8, form, areas=[5] * 256)
                g = ff.read_map_file(p, 31, 33)
                self.assertEqual(g.kind, form)
                ref_p = os.path.join(self.tmp, "ref.map")
                write_map(ref_p, v9, v8, "float")
                ref = ff.read_map_file(ref_p, 31, 33)
                for x, y in points_in(31, 33, 150, seed=2):
                    want = ref.height(x, y) if form != "flat" else 3.25
                    self.assertAlmostEqual(g.height(x, y), want, delta=tol + 0.008 if form == "uint8" else tol)
                self.assertEqual(g.area_at(*points_in(31, 33, 1)[0]), 5)

    def test_vertices_hit_stored_values(self):
        v9, v8 = tile_lattice(30, 30, gentle)
        p = os.path.join(self.tmp, "0003030.map")
        write_map(p, v9, v8, "float")
        g = ff.read_map_file(p)
        for r, c in ((0, 0), (5, 7), (64, 100), (127, 1)):
            x, y = ff.vertex_world(30, 30, r + 1e-4, c + 1e-4)
            self.assertAlmostEqual(g.height(x, y), v9[r * 129 + c], delta=0.01)
            x, y = ff.vertex_world(30, 30, r + 0.5, c + 0.5)
            self.assertAlmostEqual(g.height(x, y), v8[r * 128 + c], delta=0.01)

    def test_holes_flight_bounds_and_areas(self):
        v9, v8 = tile_lattice(32, 32, gentle)
        holes = [0] * 256
        holes[3 * 16 + 5] = 1 << (4 * 1 + 2)  # chunk ix 5, iy 3: low-res hole row 1, col 2
        areas = list(range(256))
        p = os.path.join(self.tmp, "0003232.map")
        write_map(p, v9, v8, "uint16", holes=holes, areas=areas, flight=True)
        g = ff.read_map_file(p)
        # square rows 2-3, cols 4-5 of chunk (5, 3): grid row 3*8+2.., col 5*8+4..
        x, y = ff.vertex_world(32, 32, 3 * 8 + 2.5, 5 * 8 + 4.5)
        self.assertIsNone(g.height(x, y))
        x2, y2 = ff.vertex_world(32, 32, 3 * 8 + 0.5, 5 * 8 + 0.5)
        self.assertIsNotNone(g.height(x2, y2))
        self.assertEqual(g.area_at(x, y), 3 * 16 + 5)
        # a flat tile ignores its holes, as getHeightFromFlat does
        write_map(p, [7.0] * len(v9), [7.0] * len(v8), "flat", holes=holes)
        self.assertEqual(ff.read_map_file(p).height(x, y), 7.0)

    def test_bad_files(self):
        p = os.path.join(self.tmp, "0003232.map")
        put(p, b"MAPS" + struct.pack("<I", 8) + bytes(40))
        with self.assertRaises(ff.FormatError):
            ff.read_map_file(p)
        put(p, b"short")
        with self.assertRaises(ff.FormatError):
            ff.read_map_file(p)
        # an area offset past the end: struct.error inside, a FormatError outside
        put(p, struct.pack("<4s10I", b"MAPS", 9, 12340, 9999, 8, 44, 16, 0, 0, 0, 0))
        with self.assertRaises(ff.FormatError) as e:
            ff.read_map_file(p)
        self.assertIn("cut short or damaged", str(e.exception))


class TestAdts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="fitcheck-adt-")
        spec = {"map": {"directory": "FitT", "tiles": {"x": [31, 32], "y": [32, 32]}}, "seed": 7, "area_id": 12,
                "heightmap": {"base": 10.0, "noise": [{"scale": 90, "amplitude": 8.0, "octaves": 2}],
                              "features": [{"type": "hill", "center": [-200, 300], "radius": 120, "height": 40}]},
                "textures": [{"name": "g", "path": "Tileset\\Made\\Up\\G.blp"}],
                "holes": [{"shape": {"circle": {"center": [-100, -100], "radius": 6}}}]}
        cls.out = os.path.join(cls.tmp, "out")
        tbuild.write(tbuild.build_from_dict(spec), cls.out, force=True, preview=False)
        cls.folder = os.path.join(cls.out, "World", "Maps", "FitT")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_mapforge_adt_matches_validator(self):
        rep = tvalidate.validate_map(self.out)
        self.assertEqual(rep.errors, [])
        for (tx, ty), info in rep.adts.items():
            g = ff.read_adt(os.path.join(self.folder, f"FitT_{tx}_{ty}.adt"))
            self.assertEqual((g.tx, g.ty, g.kind), (tx, ty, "float"))
            self.assertFalse([n for n in g.notes if "position" in n or "missing" in n], g.notes)
            for (cx, cy), ch in info.chunks.items():
                hs = ch["heights"]
                for r in range(9):
                    for c in range(9):
                        self.assertAlmostEqual(g.v9[(cy * 8 + r) * 129 + cx * 8 + c], hs[r * 17 + c], delta=1e-3)
                for r in range(8):
                    for c in range(8):
                        self.assertAlmostEqual(g.v8[(cy * 8 + r) * 128 + cx * 8 + c], hs[r * 17 + 9 + c],
                                               delta=1e-3)
                self.assertEqual(g.chunk_area(cy, cx), ch["area"] & 0xFFFF)
                self.assertEqual(g.holes[cy * 16 + cx] if g.holes else 0, ff._lowres_to_highres(ch["holes"]))
        self.assertTrue(any(ch["holes"] for info in rep.adts.values() for ch in info.chunks.values()))

    def test_adt_and_map_agree(self):
        """The same ground as a 3.3.5 ADT, a split root ADT and a float .map gives the same heights."""
        tmp = tempfile.mkdtemp(dir=self.tmp)
        v9, v8 = tile_lattice(33, 30, gentle)
        write_map(os.path.join(tmp, "0003033.map"), v9, v8, "float")
        m = ff.read_map_file(os.path.join(tmp, "0003033.map"))
        put(os.path.join(tmp, "T_33_30.adt"), adt_335(33, 30, gentle))
        put(os.path.join(tmp, "S_33_30.adt"), adt_split(33, 30, gentle))
        put(os.path.join(tmp, "W_33_30.adt"), adt_335(33, 30, gentle, swap_index=True))
        for name in ("T", "S", "W"):
            g = ff.read_adt(os.path.join(tmp, f"{name}_33_30.adt"))
            self.assertIn("layout " + ("split" if name == "S" else "3.3.5"), g.notes)
            for x, y in points_in(33, 30, 150, seed=3):
                self.assertAlmostEqual(g.height(x, y), m.height(x, y), delta=0.01)
                self.assertAlmostEqual(g.height(x, y), gentle(x, y), delta=0.25)

    def test_split_high_res_holes(self):
        hi = 1 << (2 * 8 + 3)  # square row 2, col 3
        low = 1 << (4 * 1 + 2)  # low-res row 1, col 2: squares rows 2-3, cols 4-5
        data = adt_split(32, 32, gentle, hires={(4, 6): hi}, low={(4, 6): low})
        hi_pt = ff.vertex_world(32, 32, 6 * 8 + 2.5, 4 * 8 + 3.5)
        lo_pt = ff.vertex_world(32, 32, 6 * 8 + 2.5, 4 * 8 + 4.5)
        # the Bleakhold client's merge (highResHoles off) keeps the low-res holes at 0x3C
        g = ff.read_adt(data, 32, 32)
        self.assertIsNotNone(g.height(*hi_pt))
        self.assertIsNone(g.height(*lo_pt))
        self.assertTrue(any("high-res holes" in n for n in g.notes), g.notes)
        self.assertEqual(g.chunk_area(6, 4), 7)
        self.assertAlmostEqual(g.height(*hi_pt), gentle(*hi_pt), delta=0.25)  # the MCVT is found without 0x14
        # with AdtMerge's highResHoles on, the 64-bit mask counts
        g = ff.read_adt(data, 32, 32, high_res_holes=True)
        self.assertIsNone(g.height(*hi_pt))
        self.assertIsNotNone(g.height(*lo_pt))

    def test_335_ignores_the_high_res_flag(self):
        """3.3.5 tiles whose MCNKs still carry flag 0x10000: ConvertADT and the 3.3.5 client read the MCVT offset at
        0x14 and the 16-bit holes at 0x3C, never a 64-bit mask there."""
        low = 1 << (4 * 1 + 2)
        g = ff.read_adt(adt_335(32, 32, gentle, holes={(5, 3): low}, flags=ff.MCNK_HIGH_RES_HOLES), 32, 32)
        ref = ff.read_adt(adt_335(32, 32, gentle, holes={(5, 3): low}), 32, 32)
        self.assertEqual(g.holes, ref.holes)
        self.assertEqual(sum(1 for m in g.holes if m), 1)
        for x, y in points_in(32, 32, 120, seed=5):
            self.assertEqual(g.height(x, y), ref.height(x, y))
        self.assertIsNone(g.height(*ff.vertex_world(32, 32, 3 * 8 + 2.5, 5 * 8 + 4.5)))
        self.assertTrue(any("0x10000" in n and "256 chunk(s)" in n for n in g.notes), g.notes)

    def test_chunks_go_by_their_place(self):
        """3.3.5: the MCIN slot places a chunk (ConvertADT), not the header's IndexX/IndexY. Split: the n-th MCNK is
        chunk n (AdtMerge rewrites the header indices from that)."""
        g = ff.read_adt(adt_335(33, 30, gentle, swap_index=True), 33, 30)
        ref = ff.read_adt(adt_335(33, 30, gentle), 33, 30)
        self.assertEqual(list(g.v9), list(ref.v9))
        self.assertTrue(any("240 chunk(s) whose header index is not their MCIN slot" in n for n in g.notes),
                        g.notes)
        self.assertFalse([n for n in g.notes if "position" in n], g.notes)
        g = ff.read_adt(adt_split(33, 30, gentle, shuffle=True), 33, 30)
        top_x, top_y = ff.tile_top_left(33, 30)
        last = gentle(top_x - 15 * ff.CHUNK_SIZE, top_y - 15 * ff.CHUNK_SIZE)  # chunk (15, 15) comes first
        self.assertAlmostEqual(g.v9[0], last, delta=1e-3)
        self.assertTrue(any("place in the file" in n for n in g.notes), g.notes)
        self.assertTrue(any("position does not match" in n for n in g.notes), g.notes)

    def test_chunk_without_mcvt_is_flat(self):
        """ConvertADT starts every cell at the MCNK's base height and adds the MCVT only when offsMCVT is set."""
        g = ff.read_adt(adt_335(32, 32, gentle, no_mcvt={(3, 4)}), 32, 32)
        top_x, top_y = ff.tile_top_left(32, 32)
        base = gentle(top_x - 4 * ff.CHUNK_SIZE, top_y - 3 * ff.CHUNK_SIZE)
        for r in range(8):  # row and column 8 are the next chunks' first ones (ConvertADT overwrites them too)
            for c in range(8):
                self.assertAlmostEqual(g.v9[(4 * 8 + r) * 129 + 3 * 8 + c], base, delta=1e-3)
                self.assertAlmostEqual(g.v8[(4 * 8 + r) * 128 + 3 * 8 + c], base, delta=1e-3)
        x, y = ff.vertex_world(32, 32, 4 * 8 + 3.3, 3 * 8 + 5.6)
        self.assertAlmostEqual(g.height(x, y), base, delta=1e-3)
        self.assertTrue(any("1 chunk(s) without an MCVT" in n for n in g.notes), g.notes)
        self.assertEqual(g.chunk_area(4, 3), 7)
        # a whole tile without MCVTs at one height is a flat tile, as map_extractor stores it
        everything = {(ix, iy) for ix in range(16) for iy in range(16)}
        g = ff.read_adt(adt_335(32, 32, lambda x, y: 12.0, no_mcvt=everything), 32, 32)
        self.assertEqual((g.kind, g.base), ("flat", 12.0))

    def test_damaged_files_are_format_errors(self):
        data = adt_335(32, 32, gentle)
        last_mcvt = data.rfind(b"TVCM")
        with self.assertRaises(ff.FormatError) as e:
            ff.read_adt(data[:last_mcvt + 200], 32, 32, name="cut.adt")
        self.assertIn("cut.adt: cut short or damaged", str(e.exception))
        p = os.path.join(self.tmp, "cut.wdt")
        put(p, wdt({(1, 1)})[:2000])
        with self.assertRaises(ff.FormatError):
            ff.read_wdt_tiles(p)
        p = os.path.join(self.tmp, "cut.dbc")
        put(p, map_dbc([(0, "Azeroth"), (1, "Kalimdor")])[:60])
        with self.assertRaises(ff.FormatError):
            ff.read_map_dbc(p)

    def test_extractor_refusals(self):
        """map_extractor checks the whole 3.3.5 file before it converts it (adt.cpp prepareLoadedData) and writes no
        .map file when one check fails; a file it would crash on stops the whole extraction. read_adt raises
        ExtractorRefusal for each, never reads such a tile as ground."""
        good = adt_335(32, 32, gentle)
        first = good.find(b"KNCM")  # the first MCNK (chunk 0,0)

        def patched(*edits, data=good):
            d = bytearray(data)
            for pos, fmt, value in edits:
                struct.pack_into(fmt, d, pos, value)
            return bytes(d)

        mcvt = good.find(b"TVCM")
        mcin_slot5 = 84 + 8 + 5 * 16
        cases = {
            "the MCVT of chunk 0,0 says 584 bytes, not 580": patched((mcvt + 4, "<I", 584)),
            "the MCVT offset of chunk 0,0 points at 'MCNR', not at an MCVT":
                patched((first + 8 + 0x14, "<I", 8 + 128 + 8 + 580)),
            "the MCLQ offset of chunk 0,0 points at": patched((first + 8 + 0x60, "<I", 12)),
            "MVER version 17, not 18": patched((8, "<I", 17)),
            "MHDR's MH2O offset points at": patched((20 + 40, "<I", 64)),
            "MHDR's MFBO offset (MHDR flag 0x1) points at": patched((20, "<I", 1), (20 + 36, "<I", 64)),
            "MCIN slot 5 (chunk 5,0) points at": patched((mcin_slot5, "<I", struct.unpack_from("<I", good,
                                                                                               mcin_slot5)[0] + 4)),
            "MHDR size 60, not 64": patched((16, "<I", 60)),
        }
        for why, data in cases.items():
            with self.subTest(why=why):
                with self.assertRaises(ff.ExtractorRefusal) as e:
                    ff.read_adt(data, 32, 32, name="x.adt")
                self.assertIn(why, str(e.exception))
                self.assertFalse(e.exception.crash)
                self.assertTrue(str(e.exception).startswith("x.adt: map_extractor would refuse it ("))
                self.assertIn("writes no .map file", e.exception.short())
        # crashes: an empty MCIN slot (ConvertADT reads every chunk's area id), no MCIN offset at all
        for why, data in (("MCIN slot 5 (chunk 5,0) is empty", patched((mcin_slot5, "<I", 0))),
                          ("MHDR has no MCIN offset", patched((24, "<I", 0)))):
            with self.subTest(why=why):
                with self.assertRaises(ff.ExtractorRefusal) as e:
                    ff.read_adt(data, 32, 32)
                self.assertTrue(e.exception.crash)
                self.assertIn(why, str(e.exception))
                self.assertIn("ends the whole extraction", str(e.exception))
        # an MFBO offset without MHDR flag 0x1 is never looked at; a good file reads
        self.assertEqual(ff.read_adt(patched((20 + 36, "<I", 64)), 32, 32).kind, "float")
        # water of a liquid type LiquidType.dbc does not have: LiquidTypes.at throws
        wet = adt_335(32, 32, gentle, water={(3, 3): (99, 40.0)})
        with self.assertRaises(ff.ExtractorRefusal) as e:
            ff.read_adt(wet, 32, 32, liquid_types=LIQUID_TYPES)
        self.assertTrue(e.exception.crash)
        self.assertIn("liquid type 99", str(e.exception))
        # the realistic case: a converter keeps flag 0x10000 and writes the 64-bit hole mask over 0x14
        conv = adt_335(32, 32, gentle, hires={(4, 6): 1 << (2 * 8 + 3)})
        with self.assertRaises(ff.ExtractorRefusal) as e:
            ff.read_adt(conv, 32, 32)
        self.assertIn("MCVT offset of chunk 4,6", str(e.exception))
        # ... and a mask whose low half is 0 leaves no MCVT offset: flat at the base height, as ConvertADT reads it
        g = ff.read_adt(adt_335(32, 32, gentle, hires={(4, 6): 1 << 40}), 32, 32)
        self.assertTrue(any("1 chunk(s) without an MCVT" in n for n in g.notes), g.notes)

    def test_water_of_335_adts(self):
        """The water ConvertADT would write: MH2O (liquid type -> flags through LiquidType.dbc) and MCLQ (the MCNK
        flags), as the cells the server reads."""
        g = ff.read_adt(adt_335(32, 32, gentle, water={(2, 3): (1, 45.0), (3, 3): (2, 44.0)}), 32, 32,
                        liquid_types=LIQUID_TYPES)
        cells = g.liquid.cells()
        self.assertEqual(sum(1 for c in cells if c), 128)
        self.assertEqual(cells[(3 * 8 + 1) * 128 + 2 * 8 + 1], (1, ff.LIQ_WATER, 45.0))
        self.assertEqual(cells[(3 * 8 + 1) * 128 + 3 * 8 + 1], (2, ff.LIQ_OCEAN | ff.LIQ_DARK, 44.0))
        self.assertIsNone(cells[0])
        self.assertTrue(g.liquid.flags_known)
        # without LiquidType.dbc the flags of MH2O water are unknown, not "none"
        g = ff.read_adt(adt_335(32, 32, gentle, water={(2, 3): (1, 45.0)}), 32, 32)
        self.assertFalse(g.liquid.flags_known)
        # MCLQ water of the same type and level gives the same cells as MH2O water
        a = ff.read_adt(adt_335(32, 32, gentle, mclq={(2, 3): ("water", 45.0)}), 32, 32).liquid.cells()
        b = ff.read_adt(adt_335(32, 32, gentle, water={(2, 3): (1, 45.0)}), 32, 32,
                        liquid_types=LIQUID_TYPES).liquid.cells()
        self.assertEqual(a, b)
        self.assertIsNone(ff.read_adt(adt_335(32, 32, gentle), 32, 32).liquid)
        # a .map's MLIQ reads back as the same cells
        p = os.path.join(self.tmp, "0003232.map")
        g = map_from_adt(p, adt_335(32, 32, gentle, water={(2, 3): (1, 45.0), (9, 9): (3, 20.0)}), 32, 32)
        self.assertEqual(ff.read_map_file(p).liquid.cells(), g.liquid.cells())
        # the water of split roots is not read: unknown, never "no water"
        g = ff.read_adt(adt_split(32, 32, gentle), 32, 32)
        self.assertIsNone(g.liquid)
        self.assertIn("not read", g.liquid_note)

    def test_flat_tile_keeps_its_holes(self):
        """map_extractor writes the holes of a flat tile too, so a flat holed tile read from its ADT and from its
        .map has the same holes (and the lookup ignores them, as getHeightFromFlat does)."""
        hole = {(5, 3): 1 << 6}
        a = ff.read_adt(adt_335(32, 32, lambda x, y: 12.0, holes=hole), 32, 32)
        p = os.path.join(self.tmp, "0003232.map")
        map_from_adt(p, adt_335(32, 32, lambda x, y: 12.0, holes=hole), 32, 32, low_holes=hole)
        m = ff.read_map_file(p)
        self.assertEqual((a.kind, m.kind), ("flat", "flat"))
        self.assertIsNotNone(a.holes)
        self.assertEqual(a.holes, m.holes)
        res = fitcheck.MapResult(0, "A", "a")
        fitcheck.compare_tile(res, (32, 32), m, a, fitcheck.Zones(None), fr.Thresholds())
        self.assertEqual(res.holes_changed, 0)
        self.assertEqual(fr.map_state(res), (fr.SAME, ""))
        self.assertEqual(a.height(*ff.vertex_world(32, 32, 3 * 8 + 6.5, 5 * 8 + 4.5)), 12.0)

    def test_extractor_rules_and_errors(self):
        g = ff.read_adt(adt_335(32, 32, lambda x, y: -900.0 + 0.001 * x), 32, 32)
        self.assertEqual(g.kind, "flat")  # all raised to -500: flat, as map_extractor stores it
        self.assertEqual(g.base, -500.0)
        with self.assertRaises(ff.FormatError):
            ff.read_adt(b"junk", 1, 1)
        with self.assertRaises(ff.FormatError):
            ff.read_adt(adt_335(1, 1, gentle))  # bytes without tile numbers

    def test_wdt_and_dbc(self):
        p = os.path.join(self.tmp, "x.wdt")
        put(p, wdt({(31, 32), (32, 32)}))
        self.assertEqual(ff.read_wdt_tiles(p)[0], {(31, 32), (32, 32)})
        p = os.path.join(self.tmp, "Map.dbc")
        put(p, map_dbc([(0, "Azeroth"), (1, "Kalimdor")]))
        self.assertEqual(ff.read_map_dbc(p), {0: "Azeroth", 1: "Kalimdor"})
        p = os.path.join(self.tmp, "AreaTable.dbc")
        put(p, area_dbc([(12, 0, 0, "Elwynn Forest"), (87, 0, 12, "Goldshire")]))
        self.assertEqual(ff.read_area_dbc(p), {12: (12, "Elwynn Forest"), 87: (12, "Goldshire")})


# --------------------------------------------------------------------------------------------- verdicts

class TestJudge(unittest.TestCase):
    t = fr.Thresholds()

    def test_ground(self):
        self.assertEqual(fr.judge(10.0, 11.4, 10.2, self.t).cls, fr.FINE)
        self.assertEqual(fr.judge(10.0, 11.6, 10.2, self.t).cls, fr.SHIFTED)
        self.assertEqual(fr.judge(10.0, 6.0, 10.2, self.t).cls, fr.SHIFTED)
        v = fr.judge(10.0, 5.9, 10.2, self.t)
        self.assertEqual((v.cls, v.stance), (fr.BROKEN, "ground"))
        self.assertAlmostEqual(v.delta, -4.1)

    def test_floors_and_caves(self):
        # on a floor 20 yd up: a big drop or a rise that stays below its feet does not matter
        self.assertEqual(fr.judge(10.0, -30.0, 30.0, self.t).cls, fr.FINE)
        self.assertEqual(fr.judge(10.0, 29.0, 30.0, self.t).stance, "above")
        self.assertEqual(fr.judge(10.0, 31.0, 30.0, self.t).cls, fr.FINE)
        self.assertEqual(fr.judge(10.0, 33.0, 30.0, self.t).cls, fr.SHIFTED)
        self.assertEqual(fr.judge(10.0, 40.0, 30.0, self.t).cls, fr.BROKEN)
        # in a cave 30 yd under the hill
        self.assertEqual(fr.judge(50.0, 80.0, 20.0, self.t).cls, fr.FINE)
        v = fr.judge(50.0, 10.0, 20.0, self.t)
        self.assertEqual((v.cls, v.stance), (fr.BROKEN, "below"))

    def test_missing_ground(self):
        v = fr.judge(10.0, None, 10.0, self.t)
        self.assertEqual((v.cls, v.stance), (fr.BROKEN, "ground"))  # a new hole under a spawn on the ground
        self.assertIn("hole", v.reason)
        # a new hole under a spawn on a floor or bridge, or over one in a cave: it stands on its model
        v = fr.judge(10.0, None, 30.0, self.t)
        self.assertEqual((v.cls, v.stance), (fr.FINE, "above"))
        self.assertEqual(fr.judge(50.0, None, 20.0, self.t).cls, fr.FINE)
        # no new tile at all: its models go with it
        for z in (10.0, 30.0, -20.0):
            v = fr.judge(10.0, None, z, self.t, new_tile=False)
            self.assertEqual(v.cls, fr.BROKEN)
            self.assertIn("no tile", v.reason)
        self.assertEqual(fr.judge(None, None, 10.0, self.t).cls, fr.NO_GROUND)
        self.assertEqual(fr.judge(None, 5.0, 10.0, self.t).cls, fr.FINE)
        self.assertEqual(fr.judge(None, 20.0, 10.0, self.t).cls, fr.BROKEN)
        with self.assertRaises(ValueError):
            fr.Thresholds(4, 1.5)


# --------------------------------------------------------------------------------------------- the whole run

def bump(x, y):
    """The old ground plus a 10 yd hill (a plateau of 10 at its centre), a 2.5 yd rise and a 30 yd pit."""
    h = gentle(x, y)
    cx, cy = -150.0, -150.0  # tile 32,32 spans x -533..0, y -533..0
    d = math.hypot(x - cx, y - cy)
    if d < 60:
        h += 10.0 if d < 40 else 10.0 * (60 - d) / 20
    d2 = math.hypot(x + 400, y + 150)
    if d2 < 30:
        h += 2.5
    d3 = math.hypot(x + 400, y + 400)
    if d3 < 40:
        h -= 30.0
    return h


class World:
    """A made-up server (maps/ and dbc/ of map 0) and a new pack (world/maps/azeroth) in a temporary folder.

    Server: tiles (32,32) and (33,32) of map 0, and (32,32) of map 1. Pack: azeroth (32,32) with the bump,
    (31,32) new; (33,32) gone; kalimdor (32,32) unchanged; a _tex0 file and DBFilesClient/Map.dbc."""

    def __init__(self, root, layout="335"):
        self.root = root
        self.server = os.path.join(root, "server")
        maps = os.path.join(self.server, "maps")
        os.makedirs(maps)
        for mid, tile in ((0, (32, 32)), (0, (33, 32)), (1, (32, 32))):
            v9, v8 = tile_lattice(tile[0], tile[1], gentle)
            areas = [87] * 128 + [12] * 128 if mid == 0 else [14] * 256
            write_map(os.path.join(maps, ff.map_file_name(mid, *tile)), v9, v8, "uint16", areas=areas)
        put(os.path.join(self.server, "dbc", "Map.dbc"), map_dbc([(0, "Azeroth"), (1, "Kalimdor")]))
        put(os.path.join(self.server, "dbc", "AreaTable.dbc"),
            area_dbc([(12, 0, 0, "Elwynn Forest"), (87, 0, 12, "Goldshire"), (14, 1, 0, "Durotar")]))
        put(os.path.join(self.server, "dbc", "LiquidType.dbc"), liquid_dbc())
        self.pack = os.path.join(root, "pack", "patch-z.MPQ")
        wm = os.path.join(self.pack, "world", "maps")
        writer = adt_335 if layout == "335" else adt_split
        put(os.path.join(wm, "azeroth", "azeroth_32_32.adt"), writer(32, 32, bump, area=87))
        put(os.path.join(wm, "azeroth", "azeroth_31_32.adt"), writer(31, 32, gentle, area=12))
        put(os.path.join(wm, "azeroth", "azeroth_32_32_tex0.adt"), b"REVM not a root file")
        put(os.path.join(wm, "azeroth", "azeroth.wdt"), wdt({(31, 32), (32, 32)}))
        put(os.path.join(wm, "kalimdor", "kalimdor_32_32.adt"), writer(32, 32, gentle, area=14))
        put(os.path.join(wm, "kalimdor", "kalimdor_32_32_obj0.adt"), b"junk")
        put(os.path.join(self.pack, "DBFilesClient", "Map.dbc"), map_dbc([(0, "Azeroth"), (1, "Kalimdor")]))
        self.spawns = os.path.join(root, "spawns.tsv")
        g = gentle
        rows = [
            ("guid", "entry", "kind", "map", "x", "y", "z", "name"),
            (1, 100, "creature", 0, -300.0, -300.0, g(-300, -300), "Calm Wolf"),
            (2, 101, "creature", 0, -150.0, -150.0, g(-150, -150) + 0.3, "Hill Boar"),
            (3, 102, "go", 0, -400.0, -150.0, g(-400, -150), "Mailbox"),
            (4, 103, "creature", 0, -150.0, -140.0, g(-150, -140) + 20.0, "Bridge Guard"),
            (5, 104, "creature", 0, -152.0, -152.0, g(-152, -152) + 5.0, "Buried Bat"),
            (6, 105, "creature", 0, -400.0, -400.0, g(-400, -400) - 20.0, "Cave Kobold"),
            (7, 106, "creature", 0, -100.0, -700.0, g(-100, -700), "Lost Farmer"),
            (8, 107, "go", 0, 100.0, 100.0, 0.0, "Off The Map"),
            (9, 108, "creature", 1, -300.0, -300.0, g(-300, -300), "Durotar Scorpid"),
            (10, 109, "creature", 0, -100.0, 300.0, g(-100, 300), "New Land Deer"),
        ]
        with open(self.spawns, "w") as f:
            for r in rows:
                f.write("\t".join(str(v) for v in r) + "\n")
        self.expect = {1: fr.FINE, 2: fr.BROKEN, 3: fr.SHIFTED, 4: fr.FINE, 5: fr.BROKEN, 6: fr.BROKEN,
                       7: fr.BROKEN, 8: fr.NO_GROUND, 9: fr.FINE, 10: fr.FINE}


def run_cli(*argv):
    buf = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = fitcheck.main([str(a) for a in argv])
    return rc, buf.getvalue() + err.getvalue()


def read_csv(path):
    import csv
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


class TestRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fitcheck-run-")
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def check_world(self, w, out, rc, log):
        self.assertEqual(rc, 1, log)
        rows = read_csv(os.path.join(out, "nonfine_spawns.csv"))
        got = {int(r["guid"]): r["class"] for r in rows}
        for guid, cls in w.expect.items():
            if cls == fr.FINE:
                self.assertNotIn(guid, got, log)
            else:
                self.assertEqual(got.get(guid), cls, f"guid {guid}\n{log}")
        names = {int(r["guid"]): r["name"] for r in rows}
        self.assertEqual(names[2], "Hill Boar")
        with open(os.path.join(out, "summary.txt")) as f:
            summary = f.read()
        self.assertIn("Map 0 Azeroth", summary)
        self.assertIn("Elwynn Forest (12)", summary)  # area 87 (Goldshire) counts for its zone
        self.assertIn("1 only on the server", summary)
        self.assertIn("1 only in the new files", summary)
        self.assertIn("VERDICT: the ground changed", summary)
        self.assertIn("Map 1 Kalimdor", summary)
        self.assertIn("VERDICT: the ground is the same", summary)
        self.assertIn("Hill Boar", summary)
        for mid, name in ((0, "azeroth"), (1, "kalimdor")):
            png = os.path.join(out, f"heatmap_{mid:03}_{name}.png")
            with open(png, "rb") as f:
                self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
        import json
        with open(os.path.join(out, "report.json")) as f:
            rep = json.load(f)
        az = rep["maps"][0]
        self.assertEqual(az["tiles_old_only"], [[33, 32]])
        self.assertEqual(az["tiles_new_only"], [[31, 32]])
        self.assertAlmostEqual(az["terrain"]["max_abs"], 30.0, delta=0.5)
        self.assertEqual(rep["maps"][1]["terrain"]["max_abs"] < 0.05, True)
        self.assertEqual(os.listdir(self.work), [], "the work folder must be empty afterwards")

    def test_folder_source(self):
        w = World(os.path.join(self.tmp, "w"))
        before = (tree_hash(w.server), tree_hash(w.pack))
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0)
        self.check_world(w, out, rc, log)
        self.assertEqual(before, (tree_hash(w.server), tree_hash(w.pack)))

    def test_split_layout_and_map_list(self):
        w = World(os.path.join(self.tmp, "w"), layout="split")
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", os.path.dirname(w.pack), "--server", os.path.join(w.server, "maps"),
                          "--spawns", w.spawns, "--out", out, "--work", self.work, "--min-free-mb", 0,
                          "--maps", "Azeroth,1")
        self.check_world(w, out, rc, log)

    def test_identical_ground_passes(self):
        w = World(os.path.join(self.tmp, "w"))
        out = os.path.join(self.tmp, "report")
        args = ("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out, "--work", self.work,
                "--min-free-mb", 0, "--maps", "kalimdor", "--no-png")
        rc, log = run_cli(*args)
        # the pack carries Azeroth too, which was not asked for: a partial check never exits 0
        self.assertEqual(rc, fitcheck.EXIT_NOT_CHECKED, log)
        self.assertIn("1 fine", log)
        self.assertIn("VERDICT: the ground is the same (heights, holes, area ids and water)", log)
        self.assertIn("  NOT ASKED FOR: 1 more map(s) of the server that the new files carry, so they would change "
                      "too (run again with --maps all): Azeroth (map 0)", log)
        with open(os.path.join(out, "report.json")) as f:
            self.assertEqual(json.load(f)["not_asked"], [{"map_id": 0, "name": "Azeroth"}])
        shutil.rmtree(os.path.join(w.pack, "world", "maps", "azeroth"))
        rc, log = run_cli(*args)
        self.assertEqual(rc, 0, log)
        self.assertNotIn("NOT ASKED FOR", log)

    def test_all_maps(self):
        """--maps all: every map of the server the new files carry, as without --maps."""
        w = World(os.path.join(self.tmp, "w"))
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--maps", "all", "--no-png")
        self.assertEqual(rc, 1, log)
        self.assertIn("  compared: Azeroth (map 0), Kalimdor (map 1)", log)
        self.assertNotIn("NOT ASKED FOR", log)

    def test_old_adts_as_reference(self):
        w = World(os.path.join(self.tmp, "w"))
        old = os.path.join(self.tmp, "old", "world", "maps", "azeroth")
        put(os.path.join(old, "Azeroth_32_32.adt"), adt_335(32, 32, gentle, area=87))
        put(os.path.join(old, "Azeroth_33_32.adt"), adt_335(33, 32, gentle, area=12))
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", w.pack, "--old-adts", os.path.join(self.tmp, "old"), "--map-dbc",
                          os.path.join(w.server, "dbc", "Map.dbc"), "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--maps", "azeroth")
        self.assertEqual(rc, 1, log)
        got = {int(r["guid"]): r["class"] for r in read_csv(os.path.join(out, "nonfine_spawns.csv"))}
        self.assertEqual(got[2], fr.BROKEN)
        self.assertEqual(got[7], fr.BROKEN)

    def test_disk_space_refusal(self):
        w = World(os.path.join(self.tmp, "w"))
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 10 ** 9)
        self.assertEqual(rc, 2)
        self.assertIn("must stay free", log)
        self.assertFalse(os.path.exists(out))
        self.assertEqual(os.listdir(self.work), [])

    def test_unknown_map_and_bad_rows(self):
        w = World(os.path.join(self.tmp, "w"))
        with open(w.spawns, "a") as f:
            f.write("x\ty\n")
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--maps", "nowhere,77", "--no-png")
        self.assertEqual(rc, fitcheck.EXIT_NOT_CHECKED, log)
        with open(os.path.join(out, "summary.txt")) as f:
            s = f.read()
        self.assertIn("'nowhere' is not a Directory of Map.dbc", s)
        self.assertIn("map id 77 is not in Map.dbc", s)
        self.assertIn("2 columns, 7 needed", s)
        self.assertIn("  NOT CHECKED: 'nowhere': not a map of the server's Map.dbc; map id 77: not in", s)
        self.assertNotIn("compared:", s)
        # one known map and one typo: the typo still makes it "not checked"
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--out", out, "--work", self.work,
                          "--min-free-mb", 0, "--maps", "kalimdor,azerot", "--no-png")
        self.assertEqual(rc, fitcheck.EXIT_NOT_CHECKED, log)
        self.assertIn("  compared: Kalimdor (map 1)", log)
        self.assertIn("  NOT CHECKED: 'azerot'", log)

    def test_wmo_only_map_is_not_checked(self):
        """A dungeon made only of a building: no terrain on either side, so nothing is compared (its buildings are
        not): exit code 3 and a NOT CHECKED verdict, never "the ground is the same"."""
        w = World(os.path.join(self.tmp, "w"))
        for path in (os.path.join(w.server, "dbc", "Map.dbc"), os.path.join(w.pack, "DBFilesClient", "Map.dbc")):
            put(path, map_dbc([(0, "Azeroth"), (1, "Kalimdor"), (36, "DeadminesInstance")]))
        put(os.path.join(w.pack, "world", "maps", "deadminesinstance", "deadminesinstance.wdt"), wdt(set(), mphd=1))
        with open(w.spawns, "a") as f:
            f.write("20\t200\tcreature\t36\t-100.0\t-400.0\t60.0\tDefias Miner\n")
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--maps", "deadminesinstance", "--no-png")
        self.assertEqual(rc, fitcheck.EXIT_NOT_CHECKED, log)
        self.assertIn("VERDICT: NOT CHECKED - no terrain on either side (WMO-only); its buildings are not compared",
                      log)
        self.assertNotIn("VERDICT: the ground", log)
        self.assertIn("the new WDT lists no terrain tiles (a WMO-only map)", log)
        with open(os.path.join(out, "report.json")) as f:
            import json
            rep = json.load(f)
        self.assertEqual(rep["exit_code"], 3)
        self.assertEqual(rep["maps"][0]["state"], fr.NOT_CHECKED)
        # with a map that was compared and is the same: still 3
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--maps", "kalimdor,deadminesinstance", "--no-png")
        self.assertEqual(rc, fitcheck.EXIT_NOT_CHECKED, log)
        self.assertIn("  compared: Kalimdor (map 1)", log)
        self.assertIn("  NOT CHECKED: DeadminesInstance (map 36): no terrain on either side", log)
        # a map the new files have nothing of: not checked either
        rmap = os.path.join(w.pack, "world", "maps", "kalimdor")
        shutil.rmtree(rmap)
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--maps", "kalimdor", "--no-png")
        self.assertEqual(rc, fitcheck.EXIT_NOT_CHECKED, log)
        self.assertIn("VERDICT: NOT CHECKED - the new files have no ADT and no WDT for this map", log)
        self.assertIn("1 fine", log)  # its spawns stay where they are: the base client's ground stays

    def test_overlay_keeps_the_base_tiles(self):
        """The pack is a patch-z.MPQ overlay: a tile it does not carry keeps the base client's ADT."""
        w = World(os.path.join(self.tmp, "w"))
        wm = os.path.join(w.pack, "world", "maps", "azeroth")
        put(os.path.join(wm, "azeroth.wdt"), wdt({(31, 32), (32, 32), (33, 32)}))  # lists 33,32 without an ADT
        put(os.path.join(wm, "azeroth_40_40.adt"), adt_335(40, 40, gentle))  # an ADT the WDT does not list
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--maps", "azeroth")
        self.assertEqual(rc, 1, log)  # the hill and the pit still moved
        got = {int(r["guid"]): r["class"] for r in read_csv(os.path.join(out, "nonfine_spawns.csv"))}
        self.assertNotIn(7, got, log)  # the Lost Farmer's tile 33,32 keeps the base ground
        self.assertEqual(got[2], fr.BROKEN)
        import json
        with open(os.path.join(out, "report.json")) as f:
            az = json.load(f)["maps"][0]
        self.assertEqual(az["tiles_base_kept"], [[33, 32]])
        self.assertEqual(az["tiles_old_only"], [])
        self.assertEqual(az["tiles_new_only"], [[31, 32]])
        self.assertIn("1 new ADT(s) that the new WDT does not list are never loaded", log)
        self.assertIn("(40,40)", log)
        self.assertIn("1 not in the new files", log)
        # without a WDT in the pack the base WDT stays: 33,32 is kept, 40,40 is new ground (if the base lists it)
        os.remove(os.path.join(wm, "azeroth.wdt"))
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--maps", "azeroth", "--no-png")
        with open(os.path.join(out, "report.json")) as f:
            az = json.load(f)["maps"][0]
        self.assertEqual(az["tiles_base_kept"], [[33, 32]])
        self.assertEqual(az["tiles_new_only"], [[31, 32], [40, 40]])
        self.assertIn("no WDT for this map", log)
        got = {int(r["guid"]): r["class"] for r in read_csv(os.path.join(out, "nonfine_spawns.csv"))}
        self.assertNotIn(7, got, log)

    def test_new_hole_under_a_floor(self):
        """A new hole in a tile that is there: broken for a spawn on the ground, fine for one on a floor or bridge
        above it or in a cave under it; a hole that changed makes the ground "changed"."""
        root = os.path.join(self.tmp, "h")
        maps = os.path.join(root, "server", "maps")
        os.makedirs(maps)
        v9, v8 = tile_lattice(32, 32, gentle)
        write_map(os.path.join(maps, ff.map_file_name(0, 32, 32)), v9, v8, "uint16", areas=[12] * 256)
        put(os.path.join(root, "server", "dbc", "Map.dbc"), map_dbc([(0, "Azeroth")]))
        hole = 1 << (4 * 1 + 2)  # chunk (5, 3): squares rows 2-3, cols 4-5
        put(os.path.join(root, "pack", "world", "maps", "azeroth", "azeroth_32_32.adt"),
            adt_335(32, 32, gentle, area=12, holes={(5, 3): hole}))
        x, y = ff.vertex_world(32, 32, 3 * 8 + 2.5, 5 * 8 + 4.5)
        g = gentle(x, y)
        spawns = os.path.join(root, "s.tsv")
        with open(spawns, "w") as f:
            f.write(f"1\t1\tcreature\t0\t{x}\t{y}\t{g}\tHole Wolf\n")
            f.write(f"2\t1\tcreature\t0\t{x}\t{y}\t{g + 12}\tBridge Guard\n")
            f.write(f"3\t1\tcreature\t0\t{x}\t{y}\t{g - 15}\tCave Kobold\n")
        out = os.path.join(root, "out")
        rc, log = run_cli("--new", os.path.join(root, "pack"), "--server", os.path.join(root, "server"),
                          "--spawns", spawns, "--out", out, "--work", self.work, "--min-free-mb", 0, "--no-png")
        self.assertEqual(rc, 1, log)
        rows = {int(r["guid"]): r for r in read_csv(os.path.join(out, "nonfine_spawns.csv"))}
        self.assertEqual(set(rows), {1}, log)
        self.assertEqual(rows[1]["class"], fr.BROKEN)
        self.assertIn("cut a hole", rows[1]["reason"])
        self.assertIn("Chunks with other holes: 1", log)
        self.assertIn("VERDICT: the ground changed (holes in 1 chunk(s))", log)
        self.assertIn("2 fine", log)

    def test_rounding_of_steep_tiles_is_not_a_change(self):
        """map_extractor stores a tile with 1500 yd of relief as uint16 with a step of 0.0229 yd, so the server's
        heights are off by up to 0.0114 yd: the same ground must still be "the same" (exit code 0). A real 0.05 yd
        change is still seen."""
        root = os.path.join(self.tmp, "steep")
        maps = os.path.join(root, "server", "maps")
        os.makedirs(maps)
        top_x, top_y = ff.tile_top_left(21, 34)

        def steep(x, y):
            return 100.0 + 1500.0 * (top_x - x) / ff.TILE_SIZE + 3.0 * math.sin(y / 41.0)

        v9, v8 = tile_lattice(21, 34, steep)
        write_map(os.path.join(maps, ff.map_file_name(534, 21, 34)), v9, v8, "uint16", areas=[616] * 256)
        g = ff.read_map_file(os.path.join(maps, ff.map_file_name(534, 21, 34)))
        self.assertEqual(g.kind, "uint16")
        self.assertGreater(g.step / 2, 0.011)
        put(os.path.join(root, "server", "dbc", "Map.dbc"), map_dbc([(534, "HyjalPast")]))
        pack = os.path.join(root, "pack", "world", "maps", "hyjalpast")
        put(os.path.join(pack, "hyjalpast_21_34.adt"), adt_335(21, 34, steep, area=616))
        spawns = os.path.join(root, "s.tsv")
        with open(spawns, "w") as f:
            for i, (x, y) in enumerate(points_in(21, 34, 20)):
                f.write(f"{i}\t1\tcreature\t534\t{x}\t{y}\t{steep(x, y)}\n")
        out = os.path.join(root, "out")
        args = ("--new", os.path.join(root, "pack"), "--server", os.path.join(root, "server"), "--spawns", spawns,
                "--out", out, "--work", self.work, "--min-free-mb", 0, "--no-png")
        rc, log = run_cli(*args)
        self.assertEqual(rc, 0, log)
        self.assertIn("VERDICT: the ground is the same", log)
        import json
        with open(os.path.join(out, "report.json")) as f:
            ts = json.load(f)["maps"][0]["terrain"]
        self.assertGreater(ts["max_abs"], 0.01)  # more than the old fixed limit: the rounding alone
        self.assertEqual((ts["same_tiles"], ts["changed_points"]), (1, 0))

        def raised(x, y):
            return steep(x, y) + (0.05 if math.hypot(x - (top_x - 200), y - (top_y - 200)) < 30 else 0.0)

        put(os.path.join(pack, "hyjalpast_21_34.adt"), adt_335(21, 34, raised, area=616))
        rc, log = run_cli(*args)
        self.assertEqual(rc, 1, log)
        self.assertIn("VERDICT: the ground changed", log)

    def test_damaged_tile_is_a_note(self):
        """One cut ADT in a pack: a NOTE, and the run goes on; a crash is exit code 2, never 1."""
        w = World(os.path.join(self.tmp, "w"))
        p = os.path.join(w.pack, "world", "maps", "azeroth", "azeroth_31_32.adt")
        with open(p, "rb") as f:
            data = f.read()
        put(p, data[:data.rfind(b"TVCM") + 100])
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--maps", "azeroth", "--no-png")
        self.assertEqual(rc, 1, log)
        self.assertNotIn("Traceback", log)
        self.assertIn("NOTE: new tile 31,32 unreadable: ", log)
        self.assertIn("cut short or damaged", log)
        self.assertIn("VERDICT: the ground changed", log)
        with mock.patch.object(fitcheck, "_run", side_effect=RuntimeError("boom")):
            rc, log = run_cli("--new", w.pack, "--server", w.server, "--out", out, "--work", self.work,
                              "--min-free-mb", 0)
        self.assertEqual(rc, fitcheck.EXIT_ERROR, log)
        self.assertIn("ERROR: the fit check stopped on an unexpected problem: RuntimeError: boom", log)
        self.assertEqual(os.listdir(self.work), [])


    def test_refused_tile_is_lost(self):
        """A new ADT map_extractor would refuse gives the server no .map file: its tile is lost and the spawns on it
        are broken, with the reason, never "the same" or merely unreadable."""
        w = World(os.path.join(self.tmp, "w"))
        # kalimdor 32,32: the same ground, but a converter wrote the 64-bit hole mask over offsMCVT
        put(os.path.join(w.pack, "world", "maps", "kalimdor", "kalimdor_32_32.adt"),
            adt_335(32, 32, gentle, area=14, hires={(4, 6): 1 << 19}))
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--maps", "kalimdor", "--no-png")
        self.assertEqual(rc, 1, log)
        self.assertIn("1 new ADT(s) that map_extractor would not convert, so the server would get no .map file for "
                      "them", log)
        self.assertIn("32,32: map_extractor would refuse it (the MCVT offset of chunk 4,6 points outside the file)",
                      log)
        self.assertNotIn("unreadable", log)
        self.assertIn("VERDICT: the ground changed (1 tile(s) lost)", log)
        rows = {int(r["guid"]): r for r in read_csv(os.path.join(out, "nonfine_spawns.csv"))}
        self.assertEqual(rows[9]["class"], fr.BROKEN)
        self.assertIn("map_extractor would refuse the new tile", rows[9]["reason"])
        with open(os.path.join(out, "report.json")) as f:
            k = json.load(f)["maps"][0]
        self.assertEqual(k["tiles_old_only"], [[32, 32]])
        self.assertEqual(k["tiles_refused"][0]["tile"], [32, 32])

    def water_world(self, new_adt, old_water=None, extra=()):
        """A server tile 32,32 of map 0 with a lake (MH2O, chunks 4-6 x 4-6 at 45 yd, made from an ADT the way
        map_extractor makes it), spawns in and next to it, and a pack with new_adt for that tile."""
        root = os.path.join(self.tmp, "water")
        shutil.rmtree(root, ignore_errors=True)
        maps = os.path.join(root, "server", "maps")
        os.makedirs(maps)
        lake = {(ix, iy): (1, 45.0) for ix in range(4, 7) for iy in range(4, 7)} if old_water is None else old_water
        map_from_adt(os.path.join(maps, ff.map_file_name(0, 32, 32)), adt_335(32, 32, gentle, area=12, water=lake),
                     32, 32)
        put(os.path.join(root, "server", "dbc", "Map.dbc"), map_dbc([(0, "Azeroth")]))
        put(os.path.join(root, "server", "dbc", "LiquidType.dbc"), liquid_dbc())
        put(os.path.join(root, "pack", "world", "maps", "azeroth", "azeroth_32_32.adt"), new_adt)
        for name, data in extra:
            put(os.path.join(root, "pack", *name.split("/")), data)
        fish = ff.vertex_world(32, 32, 5 * 8 + 3.5, 5 * 8 + 3.5)
        land = ff.vertex_world(32, 32, 12 * 8 + 3.5, 12 * 8 + 3.5)
        spawns = os.path.join(root, "s.tsv")
        with open(spawns, "w") as f:
            f.write(f"1\t1\tcreature\t0\t{fish[0]}\t{fish[1]}\t43.0\tLake Fish\n")
            f.write(f"2\t1\tcreature\t0\t{land[0]}\t{land[1]}\t{gentle(*land)}\tShore Crab\n")
        out = os.path.join(root, "out")
        rc, log = run_cli("--new", os.path.join(root, "pack"), "--server", os.path.join(root, "server"),
                          "--spawns", spawns, "--out", out, "--work", self.work, "--min-free-mb", 0, "--no-png")
        with open(os.path.join(out, "report.json")) as f:
            return rc, log, json.load(f)["maps"][0]

    def test_water_is_compared(self):
        """The .map files carry the water too (MLIQ): the same terrain with other water is not "the same"."""
        lake = {(ix, iy): (1, 45.0) for ix in range(4, 7) for iy in range(4, 7)}
        rc, log, m = self.water_world(adt_335(32, 32, gentle, area=12, water=lake))
        self.assertEqual(rc, 0, log)
        self.assertIn("VERDICT: the ground is the same (heights, holes, area ids and water)", log)
        self.assertEqual(m["water"]["cells_changed"], 0)
        # the same lake as old-style MCLQ water: what the server reads is the same
        rc, log, m = self.water_world(adt_335(32, 32, gentle, area=12,
                                              mclq={c: ("water", 45.0) for c in lake}))
        self.assertEqual(rc, 0, log)
        # the lake one yard higher: changed, and the fish in it is named
        rc, log, m = self.water_world(adt_335(32, 32, gentle, area=12, water={c: (1, 46.0) for c in lake}))
        self.assertEqual(rc, 1, log)
        self.assertIn("VERDICT: the ground changed (water in 576 cell(s) of 1 tile(s))", log)
        self.assertIn("Water: it differs in 576 cell(s) of 1 tile(s): 0 get water they did not have, 0 lose it, "
                      "576 have another liquid or level; the level moved by up to 1.00 yd", log)
        self.assertIn("Spawns at or in water that differs: 1", log)
        self.assertIn("1 Lake Fish", log)
        self.assertEqual(m["water"]["spawns_in_changed_water"], [1])
        self.assertIn("2 fine", log)  # spawns are still judged by the ground
        # the lake gone, and a new pond somewhere else
        rc, log, m = self.water_world(adt_335(32, 32, gentle, area=12, water={(12, 12): (1, 30.0)}))
        self.assertEqual(rc, 1, log)
        self.assertEqual((m["water"]["lost"], m["water"]["gained"]), (576, 64))
        # magma instead of water at the same level: another liquid
        rc, log, m = self.water_world(adt_335(32, 32, gentle, area=12, water={c: (3, 45.0) for c in lake}))
        self.assertEqual(rc, 1, log)
        self.assertEqual(m["water"]["other"], 576)
        # the heatmap marks the chunks whose water differs
        res = fitcheck.MapResult(0, "Azeroth", "azeroth")
        res.chunk_delta[(32, 32)] = [0.0] * 256
        res.water_chunks[(32, 32)] = {5 * 16 + 5}
        png = os.path.join(self.tmp, "w.png")
        with mock.patch.dict(sys.modules, {"PIL": None}):
            fr.heatmap(png, res, fr.Thresholds())
        with open(png, "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")

    def test_split_water_is_not_checked(self):
        """The water of split roots is not read: the same terrain is "the same" for heights, holes and area ids,
        but the water is NOT CHECKED (exit code 3), and the verdict never says the .map files still fit."""
        rc, log, m = self.water_world(adt_split(32, 32, gentle, area=12))
        self.assertEqual(rc, fitcheck.EXIT_NOT_CHECKED, log)
        self.assertIn("NOT CHECKED: the water of Azeroth (map 0): 1 tile(s) of split ADTs", log)
        self.assertIn("the water of 1 tile(s) was NOT compared (split ADTs), so this does not say the server's .map "
                      "files still fit", log)
        self.assertNotIn("still fit and no spawn moves", log)
        self.assertEqual(m["water"]["tiles_not_compared"], [[32, 32]])

    def test_pack_map_dbc_moves_a_map(self):
        """The client and map_extractor read the pack's Map.dbc: when it names another folder for a map id, the new
        ground of that map is that folder's."""
        w = World(os.path.join(self.tmp, "w"))
        put(os.path.join(w.pack, "DBFilesClient", "Map.dbc"), map_dbc([(0, "Azeroth"), (1, "Kalidar")]))
        put(os.path.join(w.pack, "world", "maps", "kalidar", "kalidar_32_32.adt"), adt_335(32, 32, bump, area=14))
        out = os.path.join(self.tmp, "report")
        args = ("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out, "--work", self.work,
                "--min-free-mb", 0, "--maps", "kalimdor", "--no-png")
        rc, log = run_cli(*args)
        self.assertEqual(rc, 1, log)
        self.assertIn("the new files' Map.dbc reads map 1 from the folder 'Kalidar', not 'Kalimdor'", log)
        self.assertIn("map folders of the new files that no map id of the server is read from: kalimdor", log)
        self.assertIn("VERDICT: the ground changed (heights", log)
        # the folder it moves to lacks the server's tile: lost, not "kept from the base client"
        os.remove(os.path.join(w.pack, "world", "maps", "kalidar", "kalidar_32_32.adt"))
        put(os.path.join(w.pack, "world", "maps", "kalidar", "kalidar_31_32.adt"), adt_335(31, 32, gentle))
        rc, log = run_cli(*args)
        self.assertEqual(rc, 1, log)
        with open(os.path.join(out, "report.json")) as f:
            k = json.load(f)["maps"][0]
        self.assertEqual((k["tiles_old_only"], k["tiles_base_kept"]), ([[32, 32]], []))
        self.assertIn("1 server tile(s) that the new files do not carry in that folder are counted as lost", log)
        rows = {int(r["guid"]): r for r in read_csv(os.path.join(out, "nonfine_spawns.csv"))}
        self.assertIn("reads this map from another folder", rows[9]["reason"])

    def test_pack_map_dbc_drops_a_map(self):
        """A map id the pack's Map.dbc does not have gets no files from map_extractor: every tile of it is lost."""
        w = World(os.path.join(self.tmp, "w"))
        put(os.path.join(w.pack, "DBFilesClient", "Map.dbc"), map_dbc([(0, "Azeroth"), (700, "Kalimdor")]))
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--maps", "kalimdor", "--no-png")
        self.assertEqual(rc, 1, log)
        self.assertIn("the new files' Map.dbc has no row for 1 map(s) of the server that have terrain: map_extractor "
                      "would write no .map files for them, and the client could not load them: Kalimdor (1)", log)
        self.assertIn("VERDICT: the ground changed (the new files' Map.dbc has no map 1 (it gives 'Kalimdor' id "
                      "700)", log)
        rows = {int(r["guid"]): r for r in read_csv(os.path.join(out, "nonfine_spawns.csv"))}
        self.assertEqual(rows[9]["class"], fr.BROKEN)
        self.assertIn("has no map 1", rows[9]["reason"])
        # every map (the default): the dropped one is checked too
        rc, log = run_cli("--new", w.pack, "--server", w.server, "--spawns", w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--no-png")
        self.assertIn("  compared: Azeroth (map 0), Kalimdor (map 1)", log)

    def test_ctrl_c(self):
        """Ctrl-C: one plain line, no traceback, exit code 130, the temporary files gone."""
        w = World(os.path.join(self.tmp, "w"))
        out = os.path.join(self.tmp, "report")
        with mock.patch.object(fitcheck, "_run", side_effect=KeyboardInterrupt):
            rc, log = run_cli("--new", w.pack, "--server", w.server, "--out", out, "--work", self.work,
                              "--min-free-mb", 0)
        self.assertEqual(rc, 130, log)
        self.assertIn("STOPPED (Ctrl-C): nothing was changed; its temporary files are deleted", log)
        self.assertNotIn("Traceback", log)
        self.assertEqual(os.listdir(self.work), [])


class TestScriptAndPng(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fitcheck-script-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_runs_as_isolated_script(self):
        w = World(os.path.join(self.tmp, "w"))
        out = os.path.join(self.tmp, "out")
        run = subprocess.run([sys.executable, "-I", os.path.join(TOOL_DIR, "fitcheck.py"), "--new", w.pack,
                              "--server", w.server, "--spawns", w.spawns, "--out", out, "--work", self.tmp,
                              "--min-free-mb", "0", "--maps", "azeroth"], capture_output=True, text=True,
                             cwd=self.tmp, timeout=300)
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn("4 broken, 1 shifted", run.stdout)
        self.assertEqual(sorted(os.listdir(out)), ["heatmap_000_azeroth.png", "nonfine_spawns.csv", "report.json",
                                                   "summary.txt"])
        self.assertFalse([d for d in os.listdir(self.tmp) if d.startswith("fitcheck-")])

    def test_png_without_pil(self):
        res = fitcheck.MapResult(0, "Azeroth", "azeroth")
        res.chunk_delta[(32, 32)] = [0.0] * 128 + [5.0] * 64 + [-20.0] * 64
        res.old_only.add((33, 32))
        res.spawns.append({"class": fr.BROKEN, "x": -100.0, "y": -100.0})
        real_import = __import__

        def no_pil(name, *a, **k):
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError(name)
            return real_import(name, *a, **k)

        p = os.path.join(self.tmp, "h.png")
        with mock.patch("builtins.__import__", side_effect=no_pil):
            fr.heatmap(p, res, fr.Thresholds())
        with open(p, "rb") as f:
            data = f.read()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        w, h = struct.unpack(">II", data[16:24])
        self.assertEqual((w, h), (32 * 6, 16 * 6))


@unittest.skipUnless(SEVEN_ZIP, "7z is not installed")
class TestSevenZip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fitcheck-7z-test-")
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work)
        self.w = World(os.path.join(self.tmp, "w"))
        # three more azeroth tiles far away, so a small batch budget needs several batches
        wm = os.path.join(self.w.pack, "world", "maps", "azeroth")
        for tx in (40, 41, 42):
            put(os.path.join(wm, f"azeroth_{tx}_40.adt"), adt_335(tx, 40, gentle))
        put(os.path.join(wm, "azeroth.wdt"), wdt({(31, 32), (32, 32), (40, 40), (41, 40), (42, 40)}))
        self.archive = os.path.join(self.tmp, "Maps.7z")
        subprocess.run([SEVEN_ZIP, "a", "-bd", "-mx=1", self.archive, "patch-z.MPQ"],
                       cwd=os.path.dirname(self.w.pack), check=True, capture_output=True)
        with open(self.archive, "rb") as f:
            self.archive_sum = hashlib.sha256(f.read()).hexdigest()
        # a 7z that logs every call and every file list, then runs the real one
        self.log = os.path.join(self.tmp, "7z.log")
        self.wrapper = os.path.join(self.tmp, "bin", "7z")
        os.makedirs(os.path.dirname(self.wrapper))
        with open(self.wrapper, "w") as f:
            f.write(f"""#!/bin/sh
echo "CALL $*" >> {self.log}
for a in "$@"; do
  case "$a" in
    @*) sed 's/^/FILE /' "${{a#@}}" >> {self.log} ;;
    -o*) echo "OUT ${{a#-o}}" >> {self.log} ;;
  esac
done
exec {SEVEN_ZIP} "$@"
""")
        os.chmod(self.wrapper, 0o755)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def log_lines(self):
        with open(self.log) as f:
            return f.read().splitlines()

    def test_selective_extraction(self):
        before = tree_hash(os.path.dirname(self.archive) + "/w")
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", self.archive, "--server", self.w.server, "--spawns", self.w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--batch-mb", 1, "--sevenzip", self.wrapper,
                          "--maps", "azeroth")
        self.assertEqual(rc, 1, log)
        self.assertIn("listing ", log)
        self.assertRegex(log, r"Azeroth: extracting batch 1 of [2-9] \(\d+ tiles, \d+ MB\)")
        self.assertIn("Azeroth: 5 of 5 new tiles done", log)
        self.assertIn("Azeroth: done, changed", log)
        lines = self.log_lines()
        files = [ln[5:] for ln in lines if ln.startswith("FILE ")]
        extracts = [ln for ln in lines if ln.startswith("CALL x")]
        self.assertGreaterEqual(len(extracts), 2, "a 1 MB budget needs more than one batch")
        self.assertEqual(sorted(f for f in files if f.endswith(".adt")),
                         sorted(f"patch-z.MPQ/world/maps/azeroth/azeroth_{t}.adt"
                                for t in ("31_32", "32_32", "40_40", "41_40", "42_40")))
        self.assertIn("patch-z.MPQ/world/maps/azeroth/azeroth.wdt", files)
        self.assertFalse([f for f in files if "tex0" in f or "kalimdor" in f], files)
        for ln in lines:
            if ln.startswith("OUT "):
                self.assertTrue(ln[4:].startswith(self.work + os.sep), ln)
        self.assertEqual(os.listdir(self.work), [])
        self.assertEqual(before, tree_hash(os.path.dirname(self.archive) + "/w"))
        with open(self.archive, "rb") as f:
            self.assertEqual(self.archive_sum, hashlib.sha256(f.read()).hexdigest())
        got = {int(r["guid"]): r["class"] for r in read_csv(os.path.join(out, "nonfine_spawns.csv"))}
        self.assertEqual(got[2], fr.BROKEN)

    def test_map_dbc_from_the_archive(self):
        os.remove(os.path.join(self.w.server, "dbc", "Map.dbc"))
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", self.archive, "--server", self.w.server, "--out", out, "--work", self.work,
                          "--min-free-mb", 0, "--sevenzip", self.wrapper, "--maps", "kalimdor", "--no-png",
                          "--quiet")
        self.assertEqual(rc, fitcheck.EXIT_NOT_CHECKED, log)  # Azeroth is in the archive too, not asked for
        with open(os.path.join(out, "report.json")) as f:
            self.assertEqual(json.load(f)["not_asked"], [{"map_id": 0, "name": "Azeroth"}])
        self.assertIn("the new files' DBFilesClient/Map.dbc", log)
        # --quiet leaves out the summary, not the progress
        self.assertIn("Kalimdor: extracting batch 1 of 1", log)
        self.assertIn("Kalimdor: done, same", log)
        self.assertNotIn("In short:", log)
        files = [ln[5:] for ln in self.log_lines() if ln.startswith("FILE ")]
        self.assertIn("patch-z.MPQ/DBFilesClient/Map.dbc", files)
        self.assertEqual(os.listdir(self.work), [])

    def test_small_maps_in_one_pass(self):
        """Maps that fit one batch together come out of the archive in one 7z pass (each pass over a big solid
        archive takes minutes), and the DBCs in one more."""
        out = os.path.join(self.tmp, "report")
        rc, log = run_cli("--new", self.archive, "--server", self.w.server, "--spawns", self.w.spawns, "--out", out,
                          "--work", self.work, "--min-free-mb", 0, "--sevenzip", self.wrapper, "--maps", "all",
                          "--no-png")
        self.assertEqual(rc, 1, log)
        self.assertIn("extracting 2 maps in one 7z pass (Azeroth, Kalimdor;", log)
        self.assertIn("  compared: Azeroth (map 0), Kalimdor (map 1)", log)
        self.assertEqual(len([ln for ln in self.log_lines() if ln.startswith("CALL x")]), 2, self.log_lines())
        got = {int(r["guid"]): r["class"] for r in read_csv(os.path.join(out, "nonfine_spawns.csv"))}
        self.assertEqual(got[2], fr.BROKEN)
        self.assertNotIn(9, got)
        self.assertEqual(os.listdir(self.work), [])

    def test_sigterm_cleans_up(self):
        """SIGTERM while 7z works: a plain line, exit code 143, and the temporary files are gone."""
        slow = os.path.join(self.tmp, "bin", "slow7z")
        with open(slow, "w") as f:
            f.write(f"""#!/bin/sh
case "$1" in x) touch {self.tmp}/extracting; exec sleep 60 ;; esac
exec {SEVEN_ZIP} "$@"
""")
        os.chmod(slow, 0o755)
        out = os.path.join(self.tmp, "report")
        proc = subprocess.Popen([sys.executable, "-I", os.path.join(TOOL_DIR, "fitcheck.py"), "--new", self.archive,
                                 "--server", self.w.server, "--out", out, "--work", self.work, "--min-free-mb", "0",
                                 "--sevenzip", slow, "--maps", "azeroth"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(300):
                if os.path.exists(os.path.join(self.tmp, "extracting")):
                    break
                time.sleep(0.1)
            self.assertTrue(os.listdir(self.work))
            proc.send_signal(signal.SIGTERM)
            stdout, stderr = proc.communicate(timeout=60)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 128 + signal.SIGTERM, stdout + stderr)
        self.assertIn("STOPPED (SIGTERM): nothing was changed; its temporary files are deleted", stderr)
        self.assertNotIn("Traceback", stderr)
        self.assertEqual(os.listdir(self.work), [])

    def test_extraction_refused_when_disk_is_short(self):
        src = fs.SevenZipSource(self.archive, self.wrapper, min_free=10 * fs.MB, log=lambda m: None)
        mf = src.map_files("azeroth")
        self.assertEqual(len(mf.tiles), 5)
        with mock.patch.object(fs, "free_bytes", return_value=10 * fs.MB + 1000):
            with self.assertRaises(fs.SourceError) as e:
                list(src.batches(mf, self.work, 0, log=lambda m: None))
        self.assertIn("not enough free disk", str(e.exception))
        self.assertFalse([ln for ln in self.log_lines() if ln.startswith("CALL x")])
        self.assertEqual(os.listdir(self.work), [])

    def test_cleanup_after_an_error(self):
        src = fs.SevenZipSource(self.archive, self.wrapper, log=lambda m: None)
        mf = src.map_files("azeroth")
        gen = src.batches(mf, self.work, 1 << 30, log=lambda m: None)
        batch, _wdt = next(gen)
        self.assertTrue(all(p.startswith(self.work) for p in batch.values()))
        self.assertTrue(os.listdir(self.work))
        gen.close()  # the consumer stops (an error, Ctrl-C): the batch's files go
        self.assertEqual(os.listdir(self.work), [])
        mf.tiles[(1, 1)] = "patch-z.MPQ/world/maps/azeroth/azeroth_1_1.adt"
        src.entries[mf.tiles[(1, 1)]] = (10, False)
        with self.assertRaises(fs.SourceError):
            list(src.batches(mf, self.work, 1 << 30, log=lambda m: None))
        self.assertEqual(os.listdir(self.work), [])


class TestListing(unittest.TestCase):
    def test_parse_old_and_new_7z(self):
        text = """7-Zip [64] 16.02
--
Path = Maps.7z
Type = 7z

----------
Path = patch-z.MPQ
Folder = +
Size = 0

Path = patch-z.MPQ/world/maps/azeroth/azeroth_32_48.adt
Folder = -
Size = 1234

Path = patch-z.MPQ\\World\\Maps\\Kalimdor\\Kalimdor_1_2.adt
Size = 5
Attributes = A -rw-r--r--
CRC =
"""
        e = fs.parse_7z_listing(text)
        self.assertEqual(e["patch-z.MPQ"], (0, True))
        self.assertEqual(e["patch-z.MPQ/world/maps/azeroth/azeroth_32_48.adt"], (1234, False))
        self.assertEqual(e["patch-z.MPQ/World/Maps/Kalimdor/Kalimdor_1_2.adt"], (5, False))
        idx = fs._maps_index([p for p, (_s, d) in e.items() if not d])
        self.assertEqual(sorted(idx), ["azeroth", "kalimdor"])


# --------------------------------------------------------------------------------------------- real files

def _same_ground(m, a):
    """The same heights (sampled), area ids and water: the ADT is the one the .map file was made from."""
    if (m.liquid is None) != (a.liquid is None):
        return False
    return (all(abs(a.v9_height(i) - m.v9_height(i)) < 1e-3 for i in range(0, 129 * 129, 97))
            and all(m.chunk_area(iy, ix) == a.chunk_area(iy, ix) for iy in range(16) for ix in range(16))
            and (m.liquid is None or [c and c[::2] for c in m.liquid.cells()] ==
                 [c and c[::2] for c in a.liquid.cells()]))


def _real_pairs():
    """(extracted maps folder, ADT folder) pairs in the scratchpad: map_extractor's output and an ADT folder (of the
    same build) that every tile matches, sampled. Other builds of the same map differ and are passed over."""
    pairs = []
    cands = sorted(glob.glob(os.path.join(REAL_DIR, "*", "*", "World", "Maps", "*")))
    for maps in sorted(glob.glob(os.path.join(REAL_DIR, "*", "*", "extracted", "maps"))):
        index = ff.scan_map_folder(maps)
        if len(index) != 1:
            continue
        (_mid, tiles), = index.items()
        for cand in cands:
            adts = ff.root_adts(cand)
            if not tiles or not set(tiles) <= set(adts):
                continue
            try:
                if all(_same_ground(ff.read_map_file(p), ff.read_adt(adts[t], liquid_types=LIQUID_TYPES))
                       for t, p in tiles.items()):
                    pairs.append((maps, cand))
                    break
            except ff.FormatError:
                continue
    return pairs


@unittest.skipUnless(os.path.isdir(REAL_DIR), "no scratchpad with real files")
class TestRealFiles(unittest.TestCase):
    def test_real_server_maps_read(self):
        files = sorted(glob.glob(os.path.join(REAL_DIR, "acmaps", "*.map")))
        if not files:
            self.skipTest("no acmaps")
        kinds = set()
        grids = {}
        for p in files:
            g = ff.read_map_file(p)
            kinds.add(g.kind)
            grids[(os.path.basename(p)[:3], g.tx, g.ty)] = g
            for x, y in points_in(g.tx, g.ty, 20):
                h = g.height(x, y)
                self.assertTrue(h is None or -600 < h < 3000, (p, h))
        # tiles side by side share their edge vertices
        seams = 0
        for (mid, tx, ty), g in grids.items():
            nb = grids.get((mid, tx, ty + 1))
            if nb is None:
                continue
            for c in range(0, 129, 8):
                self.assertAlmostEqual(g.v9_height(128 * 129 + c), nb.v9_height(c), delta=0.05)
            seams += 1
        self.assertGreater(seams, 0)
        self.assertIn("uint16", kinds)

    def test_real_extractor_output_matches_adt(self):
        pairs = _real_pairs()
        if not pairs:
            self.skipTest("no map_extractor output next to the ADTs it was made from")
        for maps, folder in pairs:
            adts = ff.root_adts(folder)
            index = ff.scan_map_folder(maps)
            (mid, tiles), = index.items()
            for tile, p in tiles.items():
                m = ff.read_map_file(p)
                a = ff.read_adt(adts[tile])
                for x, y in points_in(*tile, 80, seed=tile[0] * 64 + tile[1]):
                    hm, ha = m.height(x, y), a.height(x, y)
                    self.assertEqual(hm is None, ha is None, (p, x, y))
                    if hm is not None:
                        self.assertAlmostEqual(hm, ha, delta=0.01)
                for iy in range(16):
                    for ix in range(16):
                        self.assertEqual(m.chunk_area(iy, ix), a.chunk_area(iy, ix))

    def test_real_fit_check_unchanged(self):
        pairs = _real_pairs()
        if not pairs:
            self.skipTest("no map_extractor output next to the ADTs it was made from")
        maps, folder = pairs[0]
        (mid, tiles), = ff.scan_map_folder(maps).items()
        tmp = tempfile.mkdtemp(prefix="fitcheck-real-")
        try:
            name = os.path.basename(folder)
            dbc = os.path.join(tmp, "Map.dbc")
            put(dbc, map_dbc([(mid, name)]))
            spawns = os.path.join(tmp, "s.tsv")
            with open(spawns, "w") as f:
                for i, (x, y) in enumerate(points_in(*sorted(tiles)[0], 30)):
                    h = ff.read_map_file(tiles[sorted(tiles)[0]]).height(x, y)
                    if h is not None:
                        f.write(f"{i}\t1\tcreature\t{mid}\t{x}\t{y}\t{h}\n")
            out = os.path.join(tmp, "out")
            rc, log = run_cli("--new", folder, "--server", maps, "--map-dbc", dbc, "--spawns", spawns, "--out", out,
                              "--work", tmp, "--min-free-mb", 0, "--no-png")
            self.assertEqual(rc, 0, log)
            self.assertIn("VERDICT: the ground is the same", log)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _extract_with_map_extractor(work, name, map_id, files):
    """Run the real map_extractor on a fake client (Data/enUS/locale-enUS.MPQ, packed with Tools/MpqPack) holding
    files {name in World/Maps/<name>/: bytes}, a Map.dbc row and LiquidType.dbc. Returns ({.map name: path}, exit
    code, output)."""
    sys.path.insert(0, os.path.join(os.path.dirname(TOOL_DIR), "MpqPack"))
    from mpqpack import build_archive
    client, out = os.path.join(work, "client"), os.path.join(work, "extracted")
    for d in (client, out):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    entries = [(f"World\\Maps\\{name}\\{f}", b) for f, b in files.items()]
    entries += [("component.wow-enUS.txt", b'<component.wow version="12340" locale="enUS"/>\r\n'),
                ("DBFilesClient\\Map.dbc", make_dbc(2, [[map_id, name]], [name])),
                ("DBFilesClient\\LiquidType.dbc", liquid_dbc())]
    os.makedirs(os.path.join(client, "Data", "enUS"))
    with open(os.path.join(client, "Data", "enUS", "locale-enUS.MPQ"), "wb") as fh:
        fh.write(build_archive(entries))
    run = subprocess.run([MAP_EXTRACTOR, "-e", "1", "-i", client, "-o", out], cwd=work, capture_output=True,
                         text=True, errors="replace", timeout=600)
    maps = os.path.join(out, "maps")
    got = {f: os.path.join(maps, f) for f in os.listdir(maps)} if os.path.isdir(maps) else {}
    return got, run.returncode, run.stdout + run.stderr


@unittest.skipUnless(os.access(MAP_EXTRACTOR, os.X_OK), "no built map_extractor (FITCHECK_MAP_EXTRACTOR)")
class TestRealExtractor(unittest.TestCase):
    """AzerothCore's own map_extractor on the test's ADTs: what it refuses, and the water, heights and holes it
    writes, must be what fitcheck_formats reads from the same ADTs."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fitcheck-mx-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def extract(self, adt):
        return _extract_with_map_extractor(self.tmp, "FitO", 900, {"FitO.wdt": wdt({(32, 32)}),
                                                                    "FitO_32_32.adt": adt})

    def test_refusals_match(self):
        good = adt_335(32, 32, gentle)
        first = good.find(b"KNCM")
        mcvt = good.find(b"TVCM")

        def patched(pos, value, data=good):
            d = bytearray(data)
            struct.pack_into("<I", d, pos, value)
            return bytes(d)

        refused = [patched(mcvt + 4, 584), patched(first + 8 + 0x14, 8 + 128 + 8 + 580),
                   patched(first + 8 + 0x60, 12), patched(8, 17), patched(20 + 40, 64),
                   adt_335(32, 32, gentle, hires={(4, 6): 1 << 19})]
        for i, data in enumerate(refused):
            with self.subTest(case=i):
                got, _rc, log = self.extract(data)
                self.assertEqual(got, {}, log)
                with self.assertRaises(ff.ExtractorRefusal):
                    ff.read_adt(data, 32, 32, liquid_types=LIQUID_TYPES)
        got, rc, log = self.extract(patched(84 + 8 + 5 * 16, 0))  # an empty MCIN slot: it crashes
        self.assertEqual(got, {}, log)
        self.assertNotEqual(rc, 0)
        with self.assertRaises(ff.ExtractorRefusal) as e:
            ff.read_adt(patched(84 + 8 + 5 * 16, 0), 32, 32)
        self.assertTrue(e.exception.crash)

    def test_water_heights_and_holes_match(self):
        cases = {
            "mh2o": adt_335(32, 32, gentle, holes={(5, 3): 1 << 6},
                            water={(2, 3): (1, 45.0), (3, 3): (2, 44.0), (9, 9): (3, 20.0), (10, 9): (4, 21.5)}),
            "mclq": adt_335(32, 32, gentle, mclq={(2, 3): ("water", 45.0), (3, 3): ("ocean", 44.0),
                                                  (9, 9): ("magma", 20.0)}),
            "both": adt_335(32, 32, gentle, mclq={(2, 3): ("water", 45.0)}, water={(7, 7): (1, 41.0)}),
            "dry": adt_335(32, 32, gentle),
            "flat with a hole": adt_335(32, 32, lambda x, y: 12.0, holes={(5, 3): 1 << 6}),
        }
        for what, data in cases.items():
            with self.subTest(case=what):
                got, rc, log = self.extract(data)
                self.assertEqual(list(got), ["9003232.map"], log)
                m = ff.read_map_file(got["9003232.map"])
                a = ff.read_adt(data, 32, 32, liquid_types=LIQUID_TYPES)
                self.assertEqual(m.kind == "flat", a.kind == "flat")
                self.assertEqual(m.holes, a.holes)
                for x, y in points_in(32, 32, 60, seed=9):
                    hm, ha = m.height(x, y), a.height(x, y)
                    self.assertEqual(hm is None, ha is None)
                    if hm is not None:
                        self.assertAlmostEqual(hm, ha, delta=max(0.01, m.step))
                self.assertEqual(m.liquid is None, a.liquid is None, log)
                if m.liquid is not None:
                    self.assertEqual(m.liquid.cells(), a.liquid.cells())
                res = fitcheck.MapResult(900, "FitO", "FitO")
                fitcheck.compare_tile(res, (32, 32), m, a, fitcheck.Zones(None), fr.Thresholds())
                self.assertEqual(fr.map_state(res), (fr.SAME, ""), res.water)


if __name__ == "__main__":
    unittest.main()
