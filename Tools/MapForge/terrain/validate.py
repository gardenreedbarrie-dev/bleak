"""Strict, independent checker for 3.3.5a (12340) map terrain files: WDT, WDL and ADT.

    python3 -I Tools/MapForge/terrain/validate.py PATH [--map NAME] [--json] [--quiet]

PATH is a folder holding <NAME>.wdt (World/Maps/<NAME>) or an output folder containing World/Maps/<NAME>. The exit
code is 0 when there are no errors; warnings do not fail. A summary is printed (or dumped as JSON).

This file deliberately shares no code with the MapForge writer: it parses the bytes on its own and checks them
against what the readers expect:

- the client (decompiled in WoW/Source/WorldClient): CMap::LoadWdt reads MVER, MPHD (32 bytes) and MAIN (32768
  bytes) in sequence; CMapArea::ProcessIffChunks dereferences the MHDR offsets (relative to the MHDR payload)
  without checks; CMapChunk::ProcessIffChunks walks an MCNK's sub-chunks by size, resetting MCNR's to 448, MCAL's
  to sizeAlpha - 8 and MCLQ's to sizeLiquid - 8 (when sizeLiquid > 8); the alpha decoders read 2048-byte 4-bit maps
  unless MPHD flag 0x4, and abort ("Bad genformat") on 8-bit maps in a chunk without flag 0x8000;
  CMapLowDetail::Load reads the WDL positionally (MWMO, MWID, MODF, then the MAOF payload); Liquid::CAreaData
  reads MH2O;
- AzerothCore's map_extractor (src/tools/map_extractor/adt.h): MHDR size 64, MCIN at file offset 84 (getMCNK
  subtracts 84), all 256 MCNKs present, MCVT size 580, MCLQ magic at ofsMCLQ, MH2O instances, LiquidType ids;
- AzerothCore's vmap4_extractor (adtfile.cpp): walks the top-level chunks by size, maps MDDF/MODF name ids to the
  n-th string of MMDX/MWMO (so MMID/MWID must list the strings in order), dedups by unique id.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys

TILE = 1600.0 / 3.0
CHUNK = TILE / 16.0
UNIT = CHUNK / 8.0
ORIGIN = 32.0 * TILE

KNOWN_ADT = ["MVER", "MHDR", "MCIN", "MTEX", "MMDX", "MMID", "MWMO", "MWID", "MDDF", "MODF", "MH2O", "MCNK", "MFBO",
             "MTXF"]
KNOWN_SUB = {"MCVT", "MCCV", "MCNR", "MCLY", "MCRF", "MCSH", "MCAL", "MCLQ", "MCSE"}


def f32(v: float) -> float:
    return struct.unpack("<f", struct.pack("<f", v))[0]


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []
        self.summary: dict = {}
        self.adts: dict = {}  # (tx, ty) -> AdtInfo
        self.wdt_flags = 0
        self.main: set = set()
        self.wdl: dict = {}  # (tx, ty) -> list of 545 heights

    def error(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")

    @property
    def ok(self) -> bool:
        return not self.errors


class AdtInfo:
    def __init__(self, tx: int, ty: int):
        self.tx = tx
        self.ty = ty
        self.textures: list[str] = []
        self.m2_names: list[str] = []
        self.wmo_names: list[str] = []
        self.mddf: list[dict] = []
        self.modf: list[dict] = []
        self.chunks: dict = {}  # (ix, iy) -> dict
        self.mhdr: dict = {}
        self.top: list = []  # (magic, offset, size)
        self.mh2o: dict = {}  # (ix, iy) -> instance dict
        self.mtxf: list[int] = []


def walk(data: bytes, start: int, end: int):
    """Top-level chunk walk; returns (chunks, stop offset, problem or None)."""
    out = []
    pos = start
    while pos + 8 <= end:
        magic = data[pos:pos + 4][::-1].decode("latin-1")
        size = struct.unpack_from("<I", data, pos + 4)[0]
        if pos + 8 + size > end:
            return out, pos, f"chunk {magic!r} at {pos} (size {size}) runs past the end ({end})"
        out.append((magic, pos, size))
        pos += 8 + size
    if pos != end:
        return out, pos, f"{end - pos} trailing bytes at {pos}"
    return out, pos, None


def cstrings(blob: bytes) -> tuple[list[tuple[int, str]], str | None]:
    """(offset, string) list of a NUL-separated name block."""
    if not blob:
        return [], None
    if blob[-1] != 0:
        return [], "does not end with a NUL"
    out = []
    pos = 0
    while pos < len(blob):
        end = blob.index(b"\0", pos)
        try:
            name = blob[pos:end].decode("ascii")
        except UnicodeDecodeError:
            return out, f"non-ASCII name at {pos}"
        out.append((pos, name))
        pos = end + 1
    return out, None


def parse_wdt(path: str, rep: Report) -> None:
    where = os.path.basename(path)
    with open(path, "rb") as f:
        data = f.read()
    chunks, _, problem = walk(data, 0, len(data))
    if problem:
        rep.error(where, problem)
    names = [c[0] for c in chunks]
    if names[:3] != ["MVER", "MPHD", "MAIN"]:
        rep.error(where, f"must start MVER, MPHD, MAIN (CMap::LoadWdt reads them in order); found {names[:3]}")
        return
    mver, mphd, main = chunks[0], chunks[1], chunks[2]
    if mver[2] != 4 or struct.unpack_from("<I", data, 8)[0] != 18:
        rep.error(where, "MVER must hold version 18")
    if mphd[2] != 32:
        rep.error(where, f"MPHD size {mphd[2]} (the client reads 32 bytes)")
    if main[2] != 64 * 64 * 8:
        rep.error(where, f"MAIN size {main[2]} (the client reads 32768 bytes)")
        return
    flags = struct.unpack_from("<I", data, mphd[1] + 8)[0]
    rep.wdt_flags = flags
    if flags & ~0xF:
        rep.warn(where, f"MPHD flags 0x{flags:X} has bits the 3.3.5a client does not know")
    if flags & 0x1:
        if "MWMO" not in names or "MODF" not in names:
            rep.error(where, "MPHD flag 0x1 (global WMO) needs MWMO and MODF")
        rep.warn(where, "MPHD flag 0x1: a global-WMO map (MapForge writes terrain maps)")
    for i in range(4096):
        eflags = struct.unpack_from("<I", data, main[1] + 8 + i * 8)[0]
        if eflags & 1:
            rep.main.add((i % 64, i // 64))
        if eflags & ~1:
            rep.warn(where, f"MAIN entry {i % 64},{i // 64} has flags 0x{eflags:X} (only 0x1 belongs in the file)")
    if not rep.main:
        rep.error(where, "MAIN lists no tile")
    for name in names[3:]:
        if name not in ("MWMO", "MODF"):
            rep.warn(where, f"unexpected chunk {name}")


def parse_wdl(path: str, rep: Report) -> None:
    where = os.path.basename(path)
    with open(path, "rb") as f:
        data = f.read()
    chunks, _, problem = walk(data, 0, len(data))
    if problem:
        rep.error(where, problem)
    if not chunks or chunks[0][0] != "MVER" or chunks[0][2] != 4:
        rep.error(where, "must start with MVER (size 4)")
        return
    if struct.unpack_from("<I", data, 8)[0] != 18:
        rep.error(where, "MVER must hold version 18")
    idx = 1
    names = [c[0] for c in chunks]
    if len(names) > 1 and names[1] == "MWMO":
        # CMapLowDetail::Load: after MWMO it takes the next chunk as MWID, the next as MODF, then the MAOF payload.
        if names[2:4] != ["MWID", "MODF"]:
            rep.error(where, "MWMO must be followed by MWID and MODF (the client reads them positionally)")
            return
        if chunks[3][2] % 64:
            rep.error(where, "MODF size is not a multiple of 64")
        if chunks[1][2] or chunks[3][2]:
            rep.warn(where, "low-detail WMO list is not empty (MapForge writes none)")
        idx = 4
    if len(chunks) <= idx or chunks[idx][0] != "MAOF":
        rep.error(where, "MAOF must follow MVER or MVER MWMO MWID MODF")
        return
    maof = chunks[idx]
    if maof[2] != 4096 * 4:
        rep.error(where, f"MAOF size {maof[2]}, expected 16384")
        return
    starts = {c[1]: c for c in chunks}
    for i in range(4096):
        ofs = struct.unpack_from("<I", data, maof[1] + 8 + i * 4)[0]
        tile = (i % 64, i // 64)
        if not ofs:
            if tile in rep.main:
                rep.warn(where, f"tile {tile[0]},{tile[1]} is in MAIN but has no low-detail entry")
            continue
        c = starts.get(ofs)
        if c is None or c[0] != "MARE":
            rep.error(where, f"MAOF entry {tile} points at {ofs}, not at a MARE chunk")
            continue
        if c[2] != 545 * 2:
            rep.error(where, f"MARE for {tile} has size {c[2]}, expected 1090")
            continue
        rep.wdl[tile] = list(struct.unpack_from("<545h", data, ofs + 8))
        nxt = ofs + 8 + c[2]
        n = starts.get(nxt)
        if n is not None and n[0] == "MAHO" and n[2] != 32:
            rep.error(where, f"MAHO for {tile} has size {n[2]}, expected 32")
        if tile not in rep.main:
            rep.warn(where, f"low-detail entry for {tile}, which is not in MAIN")


def _expect(rep, where, data, pos, magic) -> bool:
    if pos + 8 > len(data) or data[pos:pos + 4][::-1].decode("latin-1") != magic:
        rep.error(where, f"expected {magic} at offset {pos}")
        return False
    return True


def parse_adt(path: str, tx: int, ty: int, rep: Report) -> AdtInfo | None:
    where = os.path.basename(path)
    info = AdtInfo(tx, ty)
    with open(path, "rb") as f:
        data = f.read()
    top, _, problem = walk(data, 0, len(data))
    info.top = top
    if problem:
        rep.error(where, problem)
    names = [c[0] for c in top]
    for n in names:
        if n not in KNOWN_ADT:
            rep.warn(where, f"unknown top-level chunk {n}")
    if len(top) < 3 or names[0] != "MVER" or names[1] != "MHDR":
        rep.error(where, "must start MVER, MHDR")
        return None
    if top[0][2] != 4 or struct.unpack_from("<I", data, 8)[0] != 18:
        rep.error(where, "MVER must be 4 bytes holding 18")
        return None
    if top[1][1] != 12 or top[1][2] != 64:
        rep.error(where, f"MHDR must be at offset 12 with size 64 (AzerothCore checks the size); "
                         f"found offset {top[1][1]} size {top[1][2]}")
        return None
    hdr = 20
    fields = ["flags", "mcin", "mtex", "mmdx", "mmid", "mwmo", "mwid", "mddf", "modf", "mfbo", "mh2o", "mtxf"]
    vals = struct.unpack_from("<12I", data, hdr)
    mh = dict(zip(fields, vals))
    mh["mamp"] = data[hdr + 0x30]
    info.mhdr = mh
    if mh["mamp"] != 0:
        rep.error(where, f"MHDR mamp_value {mh['mamp']}: alpha maps would be {64 >> mh['mamp']} texels wide")
    if mh["mcin"] != 64:
        rep.error(where, f"MCIN must start at file offset 84 (MHDR.mcin = 64; AzerothCore's getMCNK subtracts 84), "
                         f"found {mh['mcin']}")
    starts = {c[1]: c for c in top}
    found = {}
    for key, magic in (("mcin", "MCIN"), ("mtex", "MTEX"), ("mmdx", "MMDX"), ("mmid", "MMID"), ("mwmo", "MWMO"),
                       ("mwid", "MWID"), ("mddf", "MDDF"), ("modf", "MODF")):
        if not mh[key]:
            rep.error(where, f"MHDR.{key} is 0 (the client dereferences it unconditionally)")
            continue
        c = starts.get(hdr + mh[key])
        if c is None or c[0] != magic:
            rep.error(where, f"MHDR.{key} -> {hdr + mh[key]} is not a {magic} chunk")
            continue
        found[magic] = c
    for key, magic in (("mh2o", "MH2O"), ("mtxf", "MTXF"), ("mfbo", "MFBO")):
        if mh[key]:
            c = starts.get(hdr + mh[key])
            if c is None or c[0] != magic:
                rep.error(where, f"MHDR.{key} -> {hdr + mh[key]} is not a {magic} chunk")
            else:
                found[magic] = c
    if (mh["flags"] & 1) and "MFBO" not in found:
        rep.error(where, "MHDR flag 0x1 (MFBO) without an MFBO chunk")
    if mh["flags"] & ~1:
        rep.warn(where, f"MHDR flags 0x{mh['flags']:X} has unknown bits")
    if "MFBO" in found and found["MFBO"][2] != 36:
        rep.error(where, "MFBO size must be 36")
    for magic in ("MCIN", "MTEX", "MMDX", "MMID", "MWMO", "MWID", "MDDF", "MODF"):
        if magic not in found:
            return None
    order = [n for n in names if n != "MCNK"]
    expect = [n for n in ["MVER", "MHDR", "MCIN", "MTEX", "MMDX", "MMID", "MWMO", "MWID", "MDDF", "MODF", "MH2O",
                          "MFBO", "MTXF"] if n in order]
    if order != expect:
        rep.warn(where, f"chunk order {order} differs from Blizzard's {expect}")

    def payload(magic):
        c = found[magic]
        return data[c[1] + 8:c[1] + 8 + c[2]]

    # Name tables.
    texs, prob = cstrings(payload("MTEX"))
    if prob:
        rep.error(where, f"MTEX {prob}")
    info.textures = [n for _, n in texs]
    for n in info.textures:
        if not n:
            rep.error(where, "MTEX has an empty name")
        elif not n.lower().endswith(".blp"):
            rep.error(where, f"MTEX name {n!r} is not a .blp")
        if "/" in n:
            rep.warn(where, f"MTEX name {n!r} uses '/' (client paths use '\\')")
    if not info.textures:
        rep.error(where, "MTEX is empty; every chunk needs a texture for layer 0")
    for kind, names_magic, ids_magic, exts, attr in (("doodad", "MMDX", "MMID", (".m2", ".mdx"), "m2_names"),
                                                     ("WMO", "MWMO", "MWID", (".wmo",), "wmo_names")):
        blob = payload(names_magic)
        strings, prob = cstrings(blob)
        if prob:
            rep.error(where, f"{names_magic} {prob}")
        ids = payload(ids_magic)
        if len(ids) % 4:
            rep.error(where, f"{ids_magic} size is not a multiple of 4")
        offsets = list(struct.unpack_from(f"<{len(ids) // 4}I", ids))
        by_offset = dict(strings)
        resolved = []
        for i, o in enumerate(offsets):
            if o not in by_offset:
                rep.error(where, f"{ids_magic}[{i}] = {o} is not the start of a {names_magic} string")
                resolved.append("")
            else:
                resolved.append(by_offset[o])
        if [s for _, s in strings] != resolved:
            rep.error(where, f"{ids_magic} must list the {names_magic} strings in order (vmap4_extractor maps name "
                             "ids to the n-th string)")
        for s in resolved:
            if s and not s.lower().endswith(exts):
                rep.error(where, f"{names_magic} name {s!r} should end with {' or '.join(exts)}")
        setattr(info, attr, resolved)

    bx_max = ORIGIN - ty * TILE
    by_max = ORIGIN - tx * TILE
    mddf = payload("MDDF")
    if len(mddf) % 36:
        rep.error(where, "MDDF size is not a multiple of 36")
    for i in range(len(mddf) // 36):
        name_id, uid, px, py, pz, rx, ry, rz, scale, flags = struct.unpack_from("<II3f3fHH", mddf, i * 36)
        wx, wy, wz = ORIGIN - pz, ORIGIN - px, py
        e = {"name_id": name_id, "uid": uid, "pos": (px, py, pz), "world": (wx, wy, wz), "rot": (rx, ry, rz),
             "scale": scale, "flags": flags,
             "name": info.m2_names[name_id] if name_id < len(info.m2_names) else None}
        info.mddf.append(e)
        if name_id >= len(info.m2_names):
            rep.error(where, f"MDDF[{i}] name id {name_id} >= {len(info.m2_names)} MMID entries")
        if uid == 0:
            rep.warn(where, f"MDDF[{i}] unique id 0")
        if scale == 0:
            rep.error(where, f"MDDF[{i}] scale 0")
        if flags & ~0x7:
            rep.warn(where, f"MDDF[{i}] flags 0x{flags:X} beyond 0x7")
        if not all(math.isfinite(v) for v in (px, py, pz, rx, ry, rz)):
            rep.error(where, f"MDDF[{i}] has a non-finite value")
        elif not (bx_max - TILE - TILE <= wx <= bx_max + TILE and by_max - TILE - TILE <= wy <= by_max + TILE):
            rep.warn(where, f"MDDF[{i}] at world ({wx:.1f}, {wy:.1f}) is far from this tile")
    modf = payload("MODF")
    if len(modf) % 64:
        rep.error(where, "MODF size is not a multiple of 64")
    for i in range(len(modf) // 64):
        v = struct.unpack_from("<II3f3f3f3fHHHH", modf, i * 64)
        name_id, uid = v[0], v[1]
        pos, rot, lo, hi = v[2:5], v[5:8], v[8:11], v[11:14]
        flags, doodad_set, name_set, scale = v[14:18]
        e = {"name_id": name_id, "uid": uid, "pos": pos, "world": (ORIGIN - pos[2], ORIGIN - pos[0], pos[1]),
             "rot": rot, "lo": lo, "hi": hi, "flags": flags, "doodad_set": doodad_set, "name_set": name_set,
             "scale": scale, "name": info.wmo_names[name_id] if name_id < len(info.wmo_names) else None}
        info.modf.append(e)
        if name_id >= len(info.wmo_names):
            rep.error(where, f"MODF[{i}] name id {name_id} >= {len(info.wmo_names)} MWID entries")
        if uid == 0:
            rep.warn(where, f"MODF[{i}] unique id 0")
        if any(lo[k] > hi[k] for k in range(3)):
            rep.error(where, f"MODF[{i}] extents min > max")
        elif any(not (lo[k] - 0.01 <= pos[k] <= hi[k] + 0.01) for k in range(3)):
            rep.warn(where, f"MODF[{i}] position is outside its extents")
        if flags & 0x1:
            rep.error(where, f"MODF[{i}] flag 0x1 (destructible): the client skips it (CMapChunk::CreateRefs)")
        if not all(math.isfinite(x) for x in v[2:14]):
            rep.error(where, f"MODF[{i}] has a non-finite value")
    uids = [e["uid"] for e in info.mddf] + [e["uid"] for e in info.modf]
    if len(set(uids)) != len(uids):
        rep.error(where, "a unique id repeats within this tile's MDDF/MODF")

    if "MTXF" in found:
        if found["MTXF"][2] != 4 * len(info.textures):
            rep.error(where, f"MTXF size {found['MTXF'][2]} != 4 x {len(info.textures)} textures")
        else:
            info.mtxf = list(struct.unpack_from(f"<{len(info.textures)}I", payload("MTXF")))
    if "MH2O" in found:
        _parse_mh2o(payload("MH2O"), where, info, rep)

    # MCIN and the chunks.
    mcin = payload("MCIN")
    if len(mcin) != 4096:
        rep.error(where, f"MCIN size {len(mcin)}, expected 4096")
        return info
    seen = set()
    big_alpha = bool(rep.wdt_flags & 0x4)
    for i in range(256):
        ofs, size, flags, async_id = struct.unpack_from("<4I", mcin, i * 16)
        cw = f"{where} chunk {i % 16},{i // 16}"
        if ofs == 0:
            rep.error(cw, "MCIN offset 0 (AzerothCore's extractor needs all 256 chunks)")
            continue
        c = starts.get(ofs)
        if c is None or c[0] != "MCNK":
            rep.error(cw, f"MCIN offset {ofs} is not an MCNK chunk")
            continue
        if ofs in seen:
            rep.error(cw, "MCIN points two entries at the same MCNK")
        seen.add(ofs)
        if size != c[2] + 8:
            rep.warn(cw, f"MCIN size {size} != MCNK size + 8 ({c[2] + 8})")
        if flags or async_id:
            rep.error(cw, "MCIN flags/asyncId must be 0 in the file: the client stores its own state there, and a "
                          "preset flag 0x1 skips the first-use size fix-ups (CMapArea::PrepareChunk)")
        _parse_mcnk(data, c, i, cw, info, rep, big_alpha)
    mcnk_count = names.count("MCNK")
    if mcnk_count != 256:
        rep.error(where, f"{mcnk_count} MCNK chunks, expected 256")
    _check_tile_seams(info, where, rep)
    return info


def _parse_mh2o(p: bytes, where: str, info: AdtInfo, rep: Report) -> None:
    if len(p) < 3072:
        rep.error(where, "MH2O shorter than its 256 chunk headers")
        return
    for i in range(256):
        ofs_inst, layers, ofs_attr = struct.unpack_from("<3I", p, i * 12)
        cw = f"{where} MH2O chunk {i % 16},{i // 16}"
        if not layers:
            continue
        if ofs_inst < 3072 or ofs_inst + 24 * layers > len(p):
            rep.error(cw, "instance offset out of range")
            continue
        if ofs_attr and ofs_attr + 16 > len(p):
            rep.error(cw, "attributes offset out of range")
        for k in range(layers):
            (ltype, fmt, hmin, hmax, xo, yo, w, h, ofs_bits, ofs_verts) = struct.unpack_from("<HHffBBBBII", p,
                                                                                               ofs_inst + 24 * k)
            if not (1 <= ltype <= 21):
                rep.error(cw, f"liquid type {ltype} is not a stock LiquidType id (1..21): the client's record "
                              "lookup is not null-checked and AzerothCore's extractor aborts on a missing row")
            if fmt > 2:
                rep.error(cw, f"vertex format {fmt} (the 3.3.5a client knows 0, 1, 2)")
            if w < 1 or h < 1 or xo + w > 8 or yo + h > 8:
                rep.error(cw, f"liquid rect x {xo}+{w}, y {yo}+{h} does not fit 8 x 8")
                continue
            if hmin > hmax:
                rep.error(cw, "minHeight > maxHeight")
            nbits = (w * h + 7) // 8
            if ofs_bits:
                if ofs_bits + nbits > len(p):
                    rep.error(cw, "exists bitmap out of range")
                elif ofs_bits + 8 > len(p):
                    rep.warn(cw, "exists bitmap shorter than 8 bytes at the end of MH2O (AzerothCore reads a u64)")
            nverts = (w + 1) * (h + 1)
            need = {0: nverts * 5, 1: nverts * 8, 2: nverts}.get(fmt, 0)
            if ofs_verts and ofs_verts + need > len(p):
                rep.error(cw, "vertex data out of range")
            heights = []
            if ofs_verts and fmt in (0, 1) and ofs_verts + 4 * nverts <= len(p):
                heights = list(struct.unpack_from(f"<{nverts}f", p, ofs_verts))
                if any(not (hmin - 0.01 <= v <= hmax + 0.01) for v in heights):
                    rep.warn(cw, "vertex heights outside [minHeight, maxHeight]")
            bits = int.from_bytes(p[ofs_bits:ofs_bits + nbits], "little") if ofs_bits else (1 << (w * h)) - 1
            if k == 0:
                info.mh2o[(i % 16, i // 16)] = {"type": ltype, "format": fmt, "min": hmin, "max": hmax, "x": xo,
                                                "y": yo, "w": w, "h": h, "bits": bits, "heights": heights}


def _parse_mcnk(data: bytes, c, index: int, cw: str, info: AdtInfo, rep: Report, big_alpha: bool) -> None:
    start, size = c[1], c[2]
    if size < 128:
        rep.error(cw, "MCNK shorter than its 128-byte header")
        return
    h = struct.unpack_from("<15IHH16s6I3f3I", data, start + 8)
    (flags, ix, iy, n_layers, n_doodad_refs, ofs_mcvt, ofs_mcnr, ofs_mcly, ofs_mcrf, ofs_mcal, size_alpha, ofs_mcsh,
     size_shadow, area, n_wmo_refs, holes, _pad, lq, pred_tex, n_effect, ofs_mcse, n_snd, ofs_mclq, size_liquid,
     px, py, pz, ofs_mccv, _u1, _u2) = h
    cx, cy = index % 16, index // 16
    rec = {"flags": flags, "layers": [], "area": area, "holes": holes, "pos": (px, py, pz), "lq": lq,
           "n_doodad_refs": n_doodad_refs, "n_wmo_refs": n_wmo_refs, "refs": [], "heights": None, "normals": None,
           "alpha": [], "size_alpha": size_alpha, "sub": {}}
    info.chunks[(cx, cy)] = rec
    if (ix, iy) != (cx, cy):
        rep.error(cw, f"header index {ix},{iy} does not match its MCIN slot")
    exp_x = ORIGIN - (info.ty * 16 + cy) * CHUNK
    exp_y = ORIGIN - (info.tx * 16 + cx) * CHUNK
    if abs(px - exp_x) > 0.01 or abs(py - exp_y) > 0.01:
        rep.warn(cw, f"position ({px:.3f}, {py:.3f}) != expected corner ({exp_x:.3f}, {exp_y:.3f})")
    if not math.isfinite(pz):
        rep.error(cw, "position.z is not finite")
    if flags & ~0xFFFF:
        rep.warn(cw, f"flags 0x{flags:X} beyond 0xFFFF")
    if big_alpha and not (flags & 0x8000):
        rep.error(cw, "MPHD big alpha without MCNK flag 0x8000: the client aborts with 'Bad genformat'")
    if flags & 0x3C and not (size_liquid > 8):
        rep.warn(cw, "old liquid flags (0x4-0x20) set without MCLQ data")

    # Walk the sub-chunks the way CMapChunk::ProcessIffChunks does.
    pos = start + 8 + 128
    remaining = size - 128
    subs = {}
    while remaining > 0:
        if pos + 8 > start + 8 + size:
            rep.error(cw, "sub-chunk header runs past the MCNK")
            break
        magic = data[pos:pos + 4][::-1].decode("latin-1")
        declared = struct.unpack_from("<I", data, pos + 4)[0]
        used = declared
        if magic == "MCNR":
            if declared not in (435, 448):
                rep.error(cw, f"MCNR size {declared}: expected 435 (+13 padding, as Blizzard) or 448")
            used = 448
        elif magic == "MCAL":
            if declared != size_alpha - 8:
                rep.error(cw, f"MCAL size {declared} != sizeAlpha - 8 ({size_alpha - 8}); the client resets it")
            used = size_alpha - 8
        elif magic == "MCLQ" and size_liquid > 8:
            if declared != size_liquid - 8:
                rep.error(cw, f"MCLQ size {declared} != sizeLiquid - 8")
            used = size_liquid - 8
        if magic not in KNOWN_SUB:
            rep.warn(cw, f"unknown sub-chunk {magic}")
        if magic in subs:
            rep.error(cw, f"two {magic} sub-chunks")
        subs[magic] = (pos - start, used)
        remaining -= 8 + used
        pos += 8 + used
    if remaining != 0:
        rep.error(cw, f"sub-chunks overrun the MCNK by {-remaining} bytes")
    rec["sub"] = subs

    def at(ofs, magic, required=True):
        if not ofs:
            if required:
                rep.error(cw, f"header offset for {magic} is 0")
            return None
        s = subs.get(magic)
        if s is None or s[0] != ofs:
            rep.error(cw, f"header offset {ofs} for {magic} does not point at its sub-chunk "
                          f"({'missing' if s is None else s[0]})")
            return None
        return start + ofs + 8

    p = at(ofs_mcvt, "MCVT")
    if p is not None:
        if subs["MCVT"][1] != 580:
            rep.error(cw, f"MCVT size {subs['MCVT'][1]}, expected 580 (AzerothCore checks)")
        else:
            rel = struct.unpack_from("<145f", data, p)
            if not all(math.isfinite(v) for v in rel):
                rep.error(cw, "MCVT has a non-finite height")
            rec["heights"] = [f32(pz + v) for v in rel]
    p = at(ofs_mcnr, "MCNR")
    if p is not None:
        rec["normals"] = [struct.unpack_from("<3b", data, p + 3 * k) for k in range(145)]
        bad = 0
        for n in rec["normals"]:
            length = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
            if not (110.0 <= length <= 140.0) or n[2] <= 0:
                bad += 1
        if bad:
            rep.warn(cw, f"{bad} normals are not unit length (127) or point down")
    p = at(ofs_mcly, "MCLY", required=n_layers > 0)
    n_tex = len(info.textures)
    alpha_size = 4096 if big_alpha else 2048
    if not (1 <= n_layers <= 4):
        (rep.error if n_layers > 4 else rep.warn)(cw, f"{n_layers} layers (the client has 4 slots)")
    mcal_size = subs.get("MCAL", (0, 0))[1]
    if p is not None:
        if subs["MCLY"][1] != 16 * n_layers:
            rep.error(cw, f"MCLY size {subs['MCLY'][1]} != 16 x {n_layers} layers")
        expected_alpha = 0
        spans = []
        tex_ids = []
        for k in range(min(n_layers, 4)):
            tex_id, lflags, ofs_alpha, effect = struct.unpack_from("<4I", data, p + 16 * k)
            rec["layers"].append({"texture": tex_id, "flags": lflags, "ofs": ofs_alpha, "effect": effect})
            tex_ids.append(tex_id)
            if tex_id >= n_tex:
                rep.error(cw, f"layer {k} texture {tex_id} >= {n_tex} MTEX names")
            if k == 0 and lflags & 0x100:
                rep.error(cw, "layer 0 must not use an alpha map")
            if lflags & 0x200 and not big_alpha:
                rep.error(cw, f"layer {k} is RLE-compressed (0x200) but the map is 4-bit (MPHD 0x4 off)")
            if lflags & 0x200 and big_alpha:
                rep.warn(cw, f"layer {k} alpha is RLE-compressed; the client decodes it per 64-texel row, so write "
                             "it uncompressed unless every run stops at a row end")
            if lflags & ~0x7FF:
                rep.warn(cw, f"layer {k} flags 0x{lflags:X} beyond 0x7FF")
            if k > 0 and not (lflags & 0x100):
                rep.warn(cw, f"layer {k} has no alpha map: it covers everything below it")
            if lflags & 0x100 and not (lflags & 0x200):
                if ofs_alpha + alpha_size > mcal_size:
                    rep.error(cw, f"layer {k} alpha at {ofs_alpha} + {alpha_size} runs past MCAL ({mcal_size})")
                else:
                    spans.append((ofs_alpha, ofs_alpha + alpha_size))
                    a = start + subs["MCAL"][0] + 8 + ofs_alpha
                    rec["alpha"].append(data[a:a + alpha_size])
                expected_alpha += alpha_size
        if len(set(tex_ids)) != len(tex_ids):
            rep.warn(cw, "a texture is used by two layers")
        spans.sort()
        for a, b in zip(spans, spans[1:]):
            if b[0] < a[1]:
                rep.error(cw, "alpha maps overlap in MCAL")
        if not big_alpha and mcal_size != expected_alpha:
            rep.warn(cw, f"MCAL holds {mcal_size} bytes, the layers use {expected_alpha}")
    if "MCAL" in subs and ofs_mcal != subs["MCAL"][0]:
        rep.error(cw, f"ofsMCAL {ofs_mcal} does not point at MCAL ({subs['MCAL'][0]})")
    for row in range(8):
        bits = lq[2 * row] | (lq[2 * row + 1] << 8)
        for col in range(8):
            layer = (bits >> (2 * col)) & 3
            if layer >= max(1, n_layers):
                rep.error(cw, f"low-quality texture map cell {col},{row} names layer {layer} of {n_layers} (the "
                              "client reads that layer's ground effect)")
                break
    n_refs = n_doodad_refs + n_wmo_refs
    p = at(ofs_mcrf, "MCRF", required=n_refs > 0)
    if p is not None:
        if subs["MCRF"][1] != 4 * n_refs:
            rep.error(cw, f"MCRF size {subs['MCRF'][1]} != 4 x {n_refs} references")
        else:
            refs = list(struct.unpack_from(f"<{n_refs}I", data, p))
            rec["refs"] = refs
            for r in refs[:n_doodad_refs]:
                if r >= len(info.mddf):
                    rep.error(cw, f"doodad reference {r} >= {len(info.mddf)} MDDF entries")
            for r in refs[n_doodad_refs:]:
                if r >= len(info.modf):
                    rep.error(cw, f"WMO reference {r} >= {len(info.modf)} MODF entries")
    if flags & 0x1:
        p = at(ofs_mcsh, "MCSH")
        if p is not None and subs["MCSH"][1] != 512:
            rep.error(cw, "MCSH size must be 512")
    elif ofs_mcsh and "MCSH" not in subs:
        rep.error(cw, "ofsMCSH points at no MCSH")
    if ofs_mclq:
        at(ofs_mclq, "MCLQ")
    if size_liquid > 8 and "MCLQ" not in subs:
        rep.error(cw, "sizeLiquid > 8 without an MCLQ")
    if n_snd:
        p = at(ofs_mcse, "MCSE")
        if p is not None and subs["MCSE"][1] != 28 * n_snd:
            rep.error(cw, "MCSE size != 28 x sound emitters")
    elif ofs_mcse:
        at(ofs_mcse, "MCSE")
    if ofs_mccv or "MCCV" in subs:
        at(ofs_mccv, "MCCV")
        if not rep.wdt_flags & 0x2:
            rep.warn(cw, "MCCV present but MPHD flag 0x2 is off: the client ignores vertex colours")
    if rec["heights"] and rec["normals"]:
        rec["normal_error"] = _normal_error(rec["heights"], rec["normals"])


def _normal_error(heights, normals) -> float:
    """Largest angle (degrees) between an inner vertex's normal and the plane of its four corners."""
    worst = 0.0
    for r in range(8):
        for c in range(8):
            tl = heights[r * 17 + c]
            tr = heights[r * 17 + c + 1]
            bl = heights[(r + 1) * 17 + c]
            br = heights[(r + 1) * 17 + c + 1]
            dhdx = ((tl + tr) - (bl + br)) / (2.0 * UNIT)
            dhdy = ((tl + bl) - (tr + br)) / (2.0 * UNIT)
            g = (-dhdx, -dhdy, 1.0)
            n = normals[r * 17 + 9 + c]
            gl = math.sqrt(g[0] ** 2 + g[1] ** 2 + g[2] ** 2)
            nl = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
            cosang = (g[0] * n[0] + g[1] * n[1] + g[2] * n[2]) / (gl * nl)
            worst = max(worst, math.degrees(math.acos(max(-1.0, min(1.0, cosang)))))
    return worst


def _check_tile_seams(info: AdtInfo, where: str, rep: Report) -> None:
    worst = 0.0
    for (cx, cy), rec in info.chunks.items():
        hs = rec["heights"]
        if not hs:
            continue
        right = info.chunks.get((cx + 1, cy))
        if right and right["heights"]:
            for r in range(9):
                worst = max(worst, abs(hs[r * 17 + 8] - right["heights"][r * 17]))
        below = info.chunks.get((cx, cy + 1))
        if below and below["heights"]:
            for c in range(9):
                worst = max(worst, abs(hs[136 + c] - below["heights"][c]))
    if worst > 1e-3:
        rep.error(where, f"chunk edges do not match: largest height step {worst:.4f}")
    elif worst > 0.0:
        rep.warn(where, f"chunk edges differ by up to {worst:.6f}")


def _check_map_seams(rep: Report) -> None:
    worst = 0.0
    worst_n = 0
    for (tx, ty), info in rep.adts.items():
        east = rep.adts.get((tx + 1, ty))
        south = rep.adts.get((tx, ty + 1))
        for i in range(16):
            if east:
                a = info.chunks.get((15, i))
                b = east.chunks.get((0, i))
                if a and b and a["heights"] and b["heights"]:
                    for r in range(9):
                        worst = max(worst, abs(a["heights"][r * 17 + 8] - b["heights"][r * 17]))
                        if a["normals"] and b["normals"] and a["normals"][r * 17 + 8] != b["normals"][r * 17]:
                            worst_n += 1
            if south:
                a = info.chunks.get((i, 15))
                b = south.chunks.get((i, 0))
                if a and b and a["heights"] and b["heights"]:
                    for c in range(9):
                        worst = max(worst, abs(a["heights"][136 + c] - b["heights"][c]))
                        if a["normals"] and b["normals"] and a["normals"][136 + c] != b["normals"][c]:
                            worst_n += 1
    if worst > 1e-3:
        rep.error("map", f"tile edges do not match: largest height step {worst:.4f}")
    elif worst > 0.0:
        rep.warn("map", f"tile edges differ by up to {worst:.6f}")
    if worst_n:
        rep.warn("map", f"{worst_n} shared tile-edge vertices have different normals (visible lighting seams)")


def _check_uids(rep: Report) -> None:
    seen: dict = {}
    for (tx, ty), info in sorted(rep.adts.items()):
        for kind, entries in (("doodad", info.mddf), ("wmo", info.modf)):
            for e in entries:
                key = e["uid"]
                ident = (kind, e["name"], tuple(round(v, 3) for v in e["pos"]), tuple(round(v, 3) for v in e["rot"]))
                if key in seen and seen[key][0] != ident:
                    rep.error("map", f"unique id {key} names different placements in tile {seen[key][1]} and "
                                     f"{tx},{ty}: ids are one space across MDDF and MODF (the client keeps only "
                                     "one copy; vmap4_extractor dedups spawns by this id)")
                seen.setdefault(key, (ident, f"{tx},{ty}"))


def _check_wdl_heights(rep: Report) -> None:
    worst = 0.0
    for tile, mare in rep.wdl.items():
        info = rep.adts.get(tile)
        if not info:
            continue
        for r in range(17):
            for c in range(17):
                ch = info.chunks.get((min(c, 15), min(r, 15)))
                if not ch or not ch["heights"]:
                    continue
                vr = 8 if r == 16 else 0
                vc = 8 if c == 16 else 0
                worst = max(worst, abs(mare[r * 17 + c] - ch["heights"][vr * 17 + vc]))
    if worst > 1.0:
        rep.warn("map", f"WDL heights differ from the ADT corners by up to {worst:.2f} yards")


def find_map(path: str, name: str | None) -> tuple[str, str]:
    """(folder holding <name>.wdt, name)."""
    if os.path.isfile(path) and path.lower().endswith(".wdt"):
        return os.path.dirname(path) or ".", os.path.splitext(os.path.basename(path))[0]
    candidates = [path]
    maps = os.path.join(path, "World", "Maps")
    if os.path.isdir(maps):
        candidates += [os.path.join(maps, d) for d in sorted(os.listdir(maps))]
    for folder in candidates:
        if not os.path.isdir(folder):
            continue
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith(".wdt"):
                n = os.path.splitext(f)[0]
                if name is None or n.lower() == name.lower():
                    return folder, n
    raise FileNotFoundError(f"no {name or '*'}.wdt under {path}: a client without the WDT crashes on teleport "
                            "(CMap::LoadWdt calls SErrDisplayAppFatal)")


def _read_dbc_ids(path: str) -> set[int] | None:
    """Column 0 of a WDBC file (every 3.3.5a table keeps its id there)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if len(data) < 20 or data[:4] != b"WDBC":
        return None
    records, fields, size, _strings = struct.unpack_from("<4I", data, 4)
    if size < 4 or 20 + records * size > len(data):
        return None
    return {struct.unpack_from("<I", data, 20 + i * size)[0] for i in range(records)}


def _find_ci(folder: str, name: str) -> str | None:
    if not folder or not os.path.isdir(folder):
        return None
    for sub in ("", "DBFilesClient", "dbc"):
        base = os.path.join(folder, sub) if sub else folder
        if not os.path.isdir(base):
            continue
        for f in os.listdir(base):
            if f.lower() == name.lower():
                return os.path.join(base, f)
    return None


def _check_dbc(rep: Report, dbc: str) -> None:
    """Liquid types, area ids and ground effects against the DBCs the client/server will actually use."""
    liquid = _read_dbc_ids(_find_ci(dbc, "LiquidType.dbc") or "")
    areas = _read_dbc_ids(_find_ci(dbc, "AreaTable.dbc") or "")
    effects = _read_dbc_ids(_find_ci(dbc, "GroundEffectTexture.dbc") or "")
    if liquid is None:
        rep.warn("dbc", "LiquidType.dbc not found or unreadable; liquid types not checked against it")
    if areas is None:
        rep.warn("dbc", "AreaTable.dbc not found or unreadable; area ids not checked against it")
    for (tx, ty), info in sorted(rep.adts.items()):
        for (cx, cy), inst in sorted(info.mh2o.items()):
            if liquid is not None and inst["type"] not in liquid:
                rep.error(f"tile {tx},{ty} chunk {cx},{cy}", f"liquid type {inst['type']} has no LiquidType row")
        bad_areas = sorted({ch["area"] for ch in info.chunks.values()} - (areas or set())) if areas else []
        for a in bad_areas:
            if a:
                rep.error(f"tile {tx},{ty}", f"area id {a} has no AreaTable row (no zone text; a subzone without "
                                             "its parent row crashes the client)")
        if effects is not None:
            used = {layer["effect"] for ch in info.chunks.values() for layer in ch["layers"] if layer["effect"]}
            for e in sorted(used - effects):
                rep.warn(f"tile {tx},{ty}", f"ground effect {e} has no GroundEffectTexture row (no detail doodads)")


class _Assets:
    def __init__(self, root: str):
        self.index = {}
        for base, _dirs, files in os.walk(root):
            for f in files:
                full = os.path.join(base, f)
                self.index[os.path.relpath(full, root).replace(os.sep, "\\").lower()] = full

    def find(self, client_path: str) -> str | None:
        key = client_path.replace("/", "\\").lower()
        hit = self.index.get(key)
        if hit is None and key.endswith(".mdx"):
            hit = self.index.get(key[:-4] + ".m2")
        return hit


def _wmo_box(path: str):
    with open(path, "rb") as f:
        data = f.read()
    pos = 0
    while pos + 8 <= len(data):
        size = struct.unpack_from("<I", data, pos + 4)[0]
        if data[pos:pos + 4] == b"DHOM" and size >= 0x3C:
            v = struct.unpack_from("<6f", data, pos + 8 + 0x24)
            return v[0:3], v[3:6]
        pos += 8 + size
    return None


def _placed_box(world, rot, box):
    """World AABB of a model box turned like CMap::CreateMapObjDef (X by rot.z, Y by rot.x, Z by rot.y + 180)."""
    ax, ay, az = math.radians(rot[2]), math.radians(rot[0]), math.radians(rot[1] + 180.0)
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for x in (box[0][0], box[1][0]):
        for y in (box[0][1], box[1][1]):
            for z in (box[0][2], box[1][2]):
                y1, z1 = y * math.cos(ax) - z * math.sin(ax), y * math.sin(ax) + z * math.cos(ax)
                x2, z2 = x * math.cos(ay) + z1 * math.sin(ay), -x * math.sin(ay) + z1 * math.cos(ay)
                x3, y3 = x2 * math.cos(az) - y1 * math.sin(az), x2 * math.sin(az) + y1 * math.cos(az)
                p = (world[0] + x3, world[1] + y3, world[2] + z2)
                for i in range(3):
                    lo[i] = min(lo[i], p[i])
                    hi[i] = max(hi[i], p[i])
    return lo, hi


def _check_assets(rep: Report, root: str) -> None:
    """With extracted client files: every referenced file exists, _s.blp companions, real WMO extents."""
    assets = _Assets(root)
    done = set()
    for (tx, ty), info in sorted(rep.adts.items()):
        where = f"tile {tx},{ty}"
        flags = info.mtxf if info.mtxf else [0] * len(info.textures)
        for i, tex in enumerate(info.textures):
            if tex.lower() not in done and assets.find(tex) is None:
                rep.error(where, f"texture {tex!r} is not in the client files")
            if i < len(flags) and not flags[i] & 1:
                spec_name = tex[:-4] + "_s.blp"
                if assets.find(spec_name) is None and spec_name.lower() not in done:
                    rep.error(where, f"{spec_name!r} is missing and MTXF flag 1 is off: with specular terrain on, "
                                     "the client loads the _s file instead (CMapArea::LoadTerrainTexture)")
                done.add(spec_name.lower())
            done.add(tex.lower())
        for name in info.m2_names + info.wmo_names:
            if name and name.lower() not in done and assets.find(name) is None:
                rep.error(where, f"model {name!r} is not in the client files")
            done.add(name.lower())
        for i, e in enumerate(info.modf):
            path = assets.find(e["name"] or "")
            box = _wmo_box(path) if path else None
            if box is None:
                continue
            lo, hi = _placed_box(e["world"], e["rot"], box)
            want_lo = (ORIGIN - hi[1], lo[2], ORIGIN - hi[0])
            want_hi = (ORIGIN - lo[1], hi[2], ORIGIN - lo[0])
            err = max(max(abs(a - b) for a, b in zip(want_lo, e["lo"])),
                      max(abs(a - b) for a, b in zip(want_hi, e["hi"])))
            if err > 0.1:
                rep.error(where, f"MODF[{i}] ({e['name']}) extents are off the model's real placed box by "
                                 f"{err:.2f} yards (the client culls by them; vmap4_extractor assigns tiles by them)")


def _check_spanning(rep: Report) -> None:
    """A WMO whose extents reach into another shipped tile must be listed there too, with the same unique id."""
    present = {(tx, ty): {e["uid"] for e in info.modf} for (tx, ty), info in rep.adts.items()}
    for (tx, ty), info in sorted(rep.adts.items()):
        for e in info.modf:
            lo, hi = e["lo"], e["hi"]
            # File extents: x = ORIGIN - worldY, z = ORIGIN - worldX; tiles are TILE wide in those coordinates.
            tx0, tx1 = int(lo[0] // TILE), int(hi[0] // TILE)
            ty0, ty1 = int(lo[2] // TILE), int(hi[2] // TILE)
            for oy in range(ty0, ty1 + 1):
                for ox in range(tx0, tx1 + 1):
                    if (ox, oy) in present and e["uid"] not in present[(ox, oy)]:
                        rep.error(f"tile {tx},{ty}", f"WMO uid {e['uid']} ({e['name']}) reaches into tile {ox},{oy} "
                                                     "but is not listed there; the client only draws it while a "
                                                     "referencing tile is loaded")


def _check_trs(rep: Report, root: str, name: str) -> None:
    """Textures/Minimap/md5translate.trs, when the output ships one."""
    path = None
    for cand in (os.path.join(root, "Textures", "Minimap", "md5translate.trs"),
                 os.path.join(root, "textures", "minimap", "md5translate.trs")):
        if os.path.isfile(cand):
            path = cand
            break
    if path is None:
        return
    with open(path, "rb") as f:
        data = f.read()
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines = lines[:-1]
    if any(not line.endswith(b"\r") for line in lines) or not data.endswith(b"\r\n"):
        rep.error("md5translate.trs", "every line must end with CR LF (LoadMD5Names drops the last entry "
                                      "otherwise)")
    keys = []
    for line in lines:
        text = line.rstrip(b"\r").decode("latin-1")
        if not text or text.startswith("dir:"):
            continue
        keys.append(text.split("\t", 1)[0].lower())
    ours = [k for k in keys if k.startswith(name.lower() + "\\")]
    for tx, ty in sorted(rep.main):
        key = f"{name}\\map{tx}_{ty:02}.blp".lower()
        if key not in keys:
            rep.warn("md5translate.trs", f"no minimap entry for tile {tx},{ty} ({key})")
    if keys and len(ours) == len(keys):
        rep.error("md5translate.trs", "holds only this map's lines: the file is global, so it would replace the "
                                      "stock one and blank every other map's minimap. Build it on the VPS from "
                                      "the stock file plus these lines")


def validate_map(path: str, name: str | None = None, assets: str | None = None, dbc: str | None = None) -> Report:
    """Check a map. `assets` (extracted client files) and `dbc` (a DBC folder) enable the real-data checks."""
    rep = Report()
    try:
        folder, name = find_map(path, name)
    except FileNotFoundError as e:
        rep.error(name or "map", str(e))
        rep.summary = {"map": name, "errors": len(rep.errors), "warnings": 0}
        return rep
    if len(name) >= 64:
        rep.error(name, f"map directory name is {len(name)} characters; vmap4_extractor treats 64 or more as fatal "
                        "(vmapexport.cpp map name buffer)")
    files = {f.lower(): f for f in os.listdir(folder)}
    parse_wdt(os.path.join(folder, files[f"{name.lower()}.wdt"]), rep)
    for (tx, ty) in sorted(rep.main):
        fname = files.get(f"{name.lower()}_{tx}_{ty}.adt")
        if fname is None:
            rep.error(name, f"MAIN flags tile {tx},{ty} but {name}_{tx}_{ty}.adt is missing: the client then opens "
                            "Spells\\ErrorCube.mdx as the tile (CMap::SafeOpen) and crashes")
            continue
        info = parse_adt(os.path.join(folder, fname), tx, ty, rep)
        if info is not None:
            rep.adts[(tx, ty)] = info
    for lower, real in files.items():
        if lower.endswith(".adt") and lower.startswith(name.lower() + "_"):
            try:
                tx, ty = (int(v) for v in lower[len(name) + 1:-4].split("_"))
            except ValueError:
                rep.warn(name, f"unexpected file {real}")
                continue
            if (tx, ty) not in rep.main:
                rep.error(name, f"{real} is not flagged in MAIN: the shipped tiles must exactly match the WDT "
                                "(the client never loads it; the mismatch means a packaging error)")
    wdl = files.get(f"{name.lower()}.wdl")
    if wdl:
        parse_wdl(os.path.join(folder, wdl), rep)
    else:
        rep.warn(name, "no .wdl: the client draws no distant terrain (CMapLowDetail::Load returns)")
    _check_map_seams(rep)
    _check_uids(rep)
    _check_spanning(rep)
    _check_wdl_heights(rep)
    root = os.path.dirname(os.path.dirname(os.path.dirname(folder)))
    _check_trs(rep, root, name)
    if dbc:
        _check_dbc(rep, dbc)
    if assets:
        _check_assets(rep, assets)
    else:
        if any(info.modf for info in rep.adts.values()):
            rep.info.append("MODF extents not compared with the real WMO boxes (pass --assets with extracted "
                            "client files to check them)")
    rep.summary = _summary(name, rep)
    return rep


def _summary(name: str, rep: Report) -> dict:
    tiles = sorted(rep.adts)
    heights = [h for info in rep.adts.values() for ch in info.chunks.values() if ch["heights"] for h in ch["heights"]]
    layer_hist = [0, 0, 0, 0, 0]
    areas = set()
    hole_chunks = 0
    water = 0
    normal_err = 0.0
    textures = set()
    uids = set()
    for info in rep.adts.values():
        textures.update(info.textures)
        water += len(info.mh2o)
        for e in info.mddf + info.modf:
            uids.add(e["uid"])
        for ch in info.chunks.values():
            layer_hist[min(4, len(ch["layers"]))] += 1
            areas.add(ch["area"])
            hole_chunks += 1 if ch["holes"] else 0
            normal_err = max(normal_err, ch.get("normal_error", 0.0))
    return {
        "map": name,
        "mphd_flags": rep.wdt_flags,
        "alpha_format": "8-bit (MPHD 0x4)" if rep.wdt_flags & 0x4 else "4-bit, 2048 bytes per layer",
        "tiles": [list(t) for t in tiles],
        "height_range": [round(min(heights), 3), round(max(heights), 3)] if heights else None,
        "textures": sorted(textures),
        "chunks_by_layer_count": {str(i): layer_hist[i] for i in range(5)},
        "area_ids": sorted(areas),
        "chunks_with_holes": hole_chunks,
        "chunks_with_water": water,
        "doodad_entries": sum(len(i.mddf) for i in rep.adts.values()),
        "wmo_entries": sum(len(i.modf) for i in rep.adts.values()),
        "unique_objects": len(uids),
        "max_normal_error_deg": round(normal_err, 2),
        "wdl_tiles": len(rep.wdl),
        "errors": len(rep.errors),
        "warnings": len(rep.warnings),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check 3.3.5a WDT/WDL/ADT files strictly.")
    ap.add_argument("path", help="folder with <map>.wdt, an output folder with World/Maps/<map>, or a .wdt file")
    ap.add_argument("--map", help="map directory name, when the folder holds several")
    ap.add_argument("--json", action="store_true", help="print the summary, errors and warnings as JSON")
    ap.add_argument("--quiet", action="store_true", help="print only errors")
    ap.add_argument("--assets", help="folder of extracted client files: check that every texture, _s.blp companion "
                                     "and model exists, and MODF extents against the real WMO boxes")
    ap.add_argument("--dbc", help="DBC folder (LiquidType, AreaTable, GroundEffectTexture) to check ids against")
    args = ap.parse_args(argv)
    try:
        rep = validate_map(args.path, args.map, assets=args.assets, dbc=args.dbc)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"summary": rep.summary, "errors": rep.errors, "warnings": rep.warnings}, indent=2))
    else:
        for e in rep.errors:
            print(f"ERROR {e}")
        if not args.quiet:
            for w in rep.warnings:
                print(f"warn  {w}")
            for i in rep.info:
                print(f"note  {i}")
            for k, v in rep.summary.items():
                print(f"{k}: {v}")
        print(f"{len(rep.errors)} errors, {len(rep.warnings)} warnings")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
