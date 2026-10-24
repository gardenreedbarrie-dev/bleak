"""ADT writer: one monolithic 3.3.5a tile, laid out like Blizzard's and WarcraftXL's AdtMerge.

File: MVER(18) MHDR MCIN MTEX MMDX MMID MWMO MWID MDDF MODF [MH2O] MCNK x 256 MTXF.

- MHDR (64 bytes) at file offset 12; its offsets are relative to its payload (file offset 20) (CMapArea::
  ProcessIffChunks). MCIN must start at file offset 84: AzerothCore's adt_MCIN::getMCNK subtracts 84.
- MCIN entry i = 16 * iy + ix: absolute offset of the MCNK chunk header and its size including the 8 header bytes.
- MCNK: the 128-byte header, then MCVT MCNR MCLY MCRF MCAL MCLQ MCSE. The client walks these sub-chunks by size
  (CMapChunk::ProcessIffChunks); AzerothCore uses the header offsets (relative to the MCNK chunk start, header
  included). MCNR declares 435 bytes and is followed by 13 padding bytes (the client resets its size to 448); MCAL's
  size must equal sizeAlpha - 8 (the client resets it to that); MCLQ is empty with sizeLiquid = 8 (> 8 would make
  the client read an old-style liquid).
- MCNK flags: 0x8000 (do_not_fix_alpha_map), so the client reads the full 64 x 64 4-bit alpha maps
  (UnpackAlphaShadowBitsFixed4444) instead of 63 x 63 with a copied last row and column. No MCSH (flag 0x1 off).
"""

from __future__ import annotations

import struct

from . import coords
from .texturing import texture_chunk
from .water import build_mh2o, water_for_chunk

MCNK_FLAG_DO_NOT_FIX_ALPHA = 0x8000
MCLY_USE_ALPHA = 0x100
VERSION = 18


def chunk(magic: str, payload: bytes, declared: int | None = None) -> bytes:
    """IFF chunk: the magic stored reversed (little-endian FourCC), size, payload."""
    size = len(payload) if declared is None else declared
    return magic[::-1].encode("ascii") + struct.pack("<I", size) + payload


def _names(models: list[str]) -> tuple[bytes, bytes, dict[str, int]]:
    blob = bytearray()
    offsets = bytearray()
    index: dict[str, int] = {}
    for name in models:
        if name in index:
            continue
        index[name] = len(index)
        offsets += struct.pack("<I", len(blob))
        blob += name.encode("ascii") + b"\0"
    return bytes(blob), bytes(offsets), index


def _int8(v: float) -> int:
    n = int(v * 127.0 + (0.5 if v >= 0.0 else -0.5))
    return -127 if n < -127 else 127 if n > 127 else n


def _holes_for_chunk(spec, top_x: float, top_y: float) -> int:
    if not spec.holes:
        return 0
    mask = 0
    for hy in range(4):
        for hx in range(4):
            x = top_x - (2 * hy + 1) * coords.UNIT_SIZE
            y = top_y - (2 * hx + 1) * coords.UNIT_SIZE
            if any(s.contains(x, y) for s in spec.holes):
                mask |= 1 << (4 * hy + hx)
    return mask


def _area_for_chunk(spec, top_x: float, top_y: float) -> int:
    x = top_x - coords.CHUNK_SIZE * 0.5
    y = top_y - coords.CHUNK_SIZE * 0.5
    for area_id, shape in spec.areas:
        if shape.contains(x, y):
            return area_id
    return spec.area_id


class TileResult:
    def __init__(self):
        self.data = b""
        self.texturing = {}  # (ix, iy) -> ChunkTexturing
        self.water = {}  # (ix, iy) -> ChunkWater
        self.holes = {}  # (ix, iy) -> mask
        self.textures: list[int] = []  # spec texture index per MTEX entry
        self.doodads = []  # Resolved, in MDDF order
        self.wmos = []  # Resolved, in MODF order


def build_adt(ctx, tx: int, ty: int) -> TileResult:
    spec = ctx.spec
    grid = ctx.grid
    res = TileResult()
    weights = ctx.painter.weights_for_tile(tx, ty)

    tex_chunks = {}
    used_textures: set[int] = set()
    for iy in range(16):
        for ix in range(16):
            t = texture_chunk(weights, ix, iy)
            tex_chunks[(ix, iy)] = t
            used_textures.update(t.layers)
    res.texturing = tex_chunks
    res.textures = sorted(used_textures)
    tex_slot = {k: i for i, k in enumerate(res.textures)}

    doodads = [d for d in ctx.doodads if (tx, ty) in d.footprint]
    wmos = [w for w in ctx.wmos if (tx, ty) in w.footprint]
    res.doodads = doodads
    res.wmos = wmos
    mmdx, mmid, m2_index = _names([d.model for d in doodads])
    mwmo, mwid, wmo_index = _names([w.model for w in wmos])

    mddf = bytearray()
    chunk_doodads: dict[tuple[int, int], list[int]] = {}
    for i, d in enumerate(doodads):
        mddf += struct.pack("<II3f3fHH", m2_index[d.model], d.uid, *d.file_pos, *d.rotation, d.scale_u16, d.flags)
        for c in d.footprint[(tx, ty)]:
            chunk_doodads.setdefault(c, []).append(i)
    modf = bytearray()
    chunk_wmos: dict[tuple[int, int], list[int]] = {}
    for i, w in enumerate(wmos):
        lo, hi = w.extents
        modf += struct.pack("<II3f3f3f3fHHHH", wmo_index[w.model], w.uid, *w.file_pos, *w.rotation, *lo, *hi,
                            w.flags, w.doodad_set, w.name_set, w.scale_u16)
        for c in w.footprint[(tx, ty)]:
            chunk_wmos.setdefault(c, []).append(i)

    waters = []
    for iy in range(16):
        for ix in range(16):
            cw = water_for_chunk(spec, grid, tx, ty, ix, iy, ctx.warnings)
            waters.append(cw)
            if cw is not None:
                res.water[(ix, iy)] = cw
    mh2o = build_mh2o(waters)

    mtex = b"".join(spec.textures[k].path.encode("ascii") + b"\0" for k in res.textures)
    mtxf = b"".join(struct.pack("<I", spec.textures[k].mtxf_flags) for k in res.textures)

    out = bytearray()
    out += chunk("MVER", struct.pack("<I", VERSION))
    mhdr_pos = len(out)
    out += chunk("MHDR", bytes(64))
    mhdr_data = mhdr_pos + 8
    mcin_pos = len(out)
    out += chunk("MCIN", bytes(256 * 16))
    ofs = {}
    for magic, payload in (("MTEX", mtex), ("MMDX", mmdx), ("MMID", mmid), ("MWMO", mwmo), ("MWID", mwid),
                           ("MDDF", bytes(mddf)), ("MODF", bytes(modf))):
        ofs[magic] = len(out)
        out += chunk(magic, payload)
    if mh2o:
        ofs["MH2O"] = len(out)
        out += chunk("MH2O", mh2o)

    mcin = bytearray()
    for iy in range(16):
        for ix in range(16):
            start = len(out)
            data = _build_mcnk(ctx, tx, ty, ix, iy, tex_chunks[(ix, iy)], tex_slot,
                               sorted(chunk_doodads.get((ix, iy), [])), sorted(chunk_wmos.get((ix, iy), [])), res)
            out += data
            mcin += struct.pack("<IIII", start, len(data), 0, 0)
    out[mcin_pos + 8:mcin_pos + 8 + len(mcin)] = mcin

    ofs["MTXF"] = len(out)
    out += chunk("MTXF", mtxf)

    def rel(name):
        return ofs[name] - mhdr_data if name in ofs else 0

    mhdr = struct.pack("<12I", 0, mcin_pos - mhdr_data, rel("MTEX"), rel("MMDX"), rel("MMID"), rel("MWMO"),
                       rel("MWID"), rel("MDDF"), rel("MODF"), 0, rel("MH2O"), rel("MTXF"))
    out[mhdr_data:mhdr_data + len(mhdr)] = mhdr
    # +0x30 mamp_value = 0: 64 x 64 alpha maps (the client uses 64 >> mamp_value); +0x31..0x3F zero.
    res.data = bytes(out)
    return res


def _build_mcnk(ctx, tx, ty, ix, iy, tex, tex_slot, doodad_refs, wmo_refs, res) -> bytes:
    spec = ctx.spec
    grid = ctx.grid
    top_x, top_y = coords.chunk_top_left(tx, ty, ix, iy)
    row0 = (ty * 16 + iy) * coords.LATTICE_PER_CHUNK
    col0 = (tx * 16 + ix) * coords.LATTICE_PER_CHUNK

    # Vertex order of MCVT/MCNR: per row r, 9 outer vertices, then (r < 8) 8 inner ones.
    lattice = []
    for r in range(9):
        for c in range(9):
            lattice.append((row0 + 2 * r, col0 + 2 * c))
        if r < 8:
            for c in range(8):
                lattice.append((row0 + 2 * r + 1, col0 + 2 * c + 1))
    heights = [grid.get(r, c) for r, c in lattice]
    base = heights[0]
    mcvt = struct.pack("<145f", *[h - base for h in heights])
    nrm = bytearray()
    for r, c in lattice:
        n = grid.normal(r, c)
        nrm += struct.pack("<bbb", _int8(n[0]), _int8(n[1]), _int8(n[2]))
    nrm += bytes(13)

    mcly = bytearray()
    for i, k in enumerate(tex.layers):
        flags = 0 if i == 0 else MCLY_USE_ALPHA
        mcly += struct.pack("<IIII", tex_slot[k], flags, 0 if i == 0 else (i - 1) * 2048, spec.textures[k].effect_id)
    mcal = b"".join(tex.alpha)
    mcrf = struct.pack(f"<{len(doodad_refs) + len(wmo_refs)}I", *doodad_refs, *wmo_refs)

    holes = _holes_for_chunk(spec, top_x, top_y)
    res.holes[(ix, iy)] = holes
    area = _area_for_chunk(spec, top_x, top_y)

    subs = []
    ofs = {}
    pos = 8 + 128
    for magic, payload, declared in (("MCVT", mcvt, None), ("MCNR", bytes(nrm), 435), ("MCLY", bytes(mcly), None),
                                     ("MCRF", mcrf, None), ("MCAL", mcal, None), ("MCLQ", b"", None),
                                     ("MCSE", b"", None)):
        ofs[magic] = pos
        data = chunk(magic, payload, declared)
        subs.append(data)
        pos += len(data)

    header = struct.pack(
        "<15IHH16s6I3f3I",
        MCNK_FLAG_DO_NOT_FIX_ALPHA, ix, iy, len(tex.layers), len(doodad_refs),
        ofs["MCVT"], ofs["MCNR"], ofs["MCLY"], ofs["MCRF"], ofs["MCAL"], len(mcal) + 8, 0, 0,
        area, len(wmo_refs), holes, 0, tex.low_quality,
        0, 0, ofs["MCSE"], 0, ofs["MCLQ"], 8,
        top_x, top_y, base,
        0, 0, 0)
    assert len(header) == 128
    return chunk("MCNK", header + b"".join(subs))
