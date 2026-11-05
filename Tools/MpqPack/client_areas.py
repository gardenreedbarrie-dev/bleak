#!/usr/bin/env python3
"""Look up AreaTable rows (id, map, parent, flags, ambience, music, light, name) in the client's own archives.

A map config copies a "template" area's ambience, music and flags (bleakhold_*.json: zone.template), and an id
written from memory that happens to exist builds without error but plays the wrong music. This prints the real rows,
with the map each belongs to, so the id can be read instead of remembered:

    python3 -I client_areas.py <client Data folder> 'molten|onyxia|ragefire|blackrock'
    python3 -I client_areas.py <client Data folder> --id 215

The newest archive that holds DBFilesClient\\AreaTable.dbc wins (patches over base), as the client resolves it. Reads
the retail archives through the same CRC-tolerant block reader as wmo_info.py (imported from it, so keep the two
files together). Nothing is written.

AreaTable.dbc, 3.3.5a (36 fields, 144-byte records): 0 id, 1 continentID (the map), 2 parentAreaID, 3 areaBit,
4 flags, 5-6 sound provider, 7 ambienceID, 8 zoneMusic, 9 introSound, 10 explorationLevel, 11-27 areaName (16 locale
strings + a flags word; field 11 is enUS), 28 factionGroupMask, 29-32 liquidTypeID, 33 minElevation,
34 ambientMultiplier, 35 lightID.
"""
from __future__ import annotations

import argparse
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.environ.get("MPQPACK_DIR", HERE))

import wmo_info  # noqa: E402  (installs the CRC-tolerant block reader on mpqpack.MpqArchive)

mpqpack = wmo_info.mpqpack

DBC = "DBFilesClient\\AreaTable.dbc"
FIELDS = 36
NAME_FIELD = 11


def read_dbc(data: bytes):
    """(records, strings) of a WDBC file; each record is a tuple of FIELDS uint32."""
    if data[:4] != b"WDBC":
        raise ValueError("not a WDBC file")
    count, fields, size, strsize = struct.unpack_from("<4I", data, 4)
    if fields != FIELDS or size != FIELDS * 4:
        raise ValueError(f"unexpected AreaTable layout: {fields} fields, {size}-byte records (3.3.5a has {FIELDS}, "
                         f"{FIELDS * 4})")
    body = 20
    strings = data[body + count * size:body + count * size + strsize]
    rows = [struct.unpack_from(f"<{fields}I", data, body + i * size) for i in range(count)]
    return rows, strings


def cstr(strings: bytes, off: int) -> str:
    if off <= 0 or off >= len(strings):
        return ""
    return strings[off:strings.index(b"\0", off)].decode("utf-8", "replace")


def find_dbc(data_dir: str) -> tuple[bytes | None, str]:
    archives = []
    for root, _d, files in os.walk(data_dir):
        for f in files:
            if f.lower().endswith(".mpq"):
                archives.append(os.path.join(root, f))
    # patches override the base archives: read them last and keep the last hit
    archives.sort(key=lambda p: ("patch" in os.path.basename(p).lower(), os.path.basename(p).lower()))
    found, where = None, ""
    for path in archives:
        try:
            a = mpqpack.MpqArchive(path)
            if a.has_file(DBC):
                found, where = a.read(DBC), os.path.basename(path)
        except Exception:
            continue
    return found, where


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", help="the client's Data folder")
    ap.add_argument("pattern", nargs="?", help="case-insensitive regex on the area name")
    ap.add_argument("--id", type=int, help="print this area id (and its parent chain) instead")
    args = ap.parse_args()
    if args.pattern is None and args.id is None:
        ap.error("give a name pattern or --id")

    raw, where = find_dbc(args.data_dir)
    if raw is None:
        return print(f"{DBC} not found in any archive under {args.data_dir}") or 2
    rows, strings = read_dbc(raw)
    print(f"{len(rows)} areas (from {where})\n", file=sys.stderr)
    by_id = {r[0]: r for r in rows}
    pat = re.compile(args.pattern, re.I) if args.pattern else None

    print(f"{'id':>6} {'map':>5} {'parent':>6} {'flags':>10} {'ambience':>8} {'music':>6} {'light':>6}  name")
    shown = 0
    for r in rows:
        name = cstr(strings, r[NAME_FIELD])
        if (args.id is not None and r[0] != args.id) or (pat and not pat.search(name)):
            continue
        parent = cstr(strings, by_id[r[2]][NAME_FIELD]) if r[2] in by_id else ""
        print(f"{r[0]:>6} {r[1]:>5} {r[2]:>6} {'0x%08X' % r[4]:>10} {r[7]:>8} {r[8]:>6} {r[35]:>6}  {name}"
              + (f"   (in {parent})" if parent else ""))
        shown += 1
    print(f"\n{shown} row(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
