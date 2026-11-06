#!/usr/bin/env python3
"""Show how a dungeon map is built, from the client's own archives: its WDT (tiles or one global WMO), the WMO it
places (name, position, rotation, box), and that WMO's size and groups. Nothing is written.

    python3 -I wdt_info.py <client Data folder> MoltenCore OnyxiaLairInstance OrgrimmarInstance
    python3 -I wdt_info.py <Data> --dbc <folder with Map.dbc> 409 249 389      # map ids instead of folders

A dungeon such as Molten Core has a WDT with no terrain tiles and one global WMO (MPHD flag 0x1, MWMO + MODF): the
whole dungeon is that model. To reuse it inside another map, place the same WMO; a point of the original map (an
entrance or a boss) moves with it by the same offset when the rotation is kept. This prints the numbers for that:
the MODF placement in world coordinates (world X = 17066.666 - pos.z, world Y = 17066.666 - pos.x, Z = pos.y).

Reads through wmo_info.py's CRC-tolerant block reader (keep the two files together).
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import wmo_info  # noqa: E402  (CRC-tolerant reader, find_file, chunks)

ORIGIN = 17066.666


def map_dirs_from_dbc(dbc_dir: str, ids: list[int]) -> dict[int, str]:
    path = os.path.join(dbc_dir, "Map.dbc")
    with open(path, "rb") as f:
        d = f.read()
    count, fields, size, strsize = struct.unpack_from("<4I", d, 4)
    strings = d[20 + count * size:]
    out = {}
    for i in range(count):
        mid, off = struct.unpack_from("<2I", d, 20 + i * size)
        if mid in ids:
            out[mid] = strings[off:strings.index(b"\0", off)].decode("utf-8", "replace")
    return out


def wmo_summary(data_dir: str, name: str) -> None:
    raw = wmo_info.find_file(data_dir, name)
    if raw is None:
        print(f"      (the WMO {name} is not in the archives)")
        return
    groups = indoor = 0
    for tag, p in wmo_info.chunks(raw):
        if tag == "MOHD" and len(p) >= 64:
            n_grp, n_portal = struct.unpack_from("<2I", p, 4)
            lo = struct.unpack_from("<3f", p, 36)
            hi = struct.unpack_from("<3f", p, 48)
            print(f"      WMO box  min ({lo[0]:.1f}, {lo[1]:.1f}, {lo[2]:.1f})  max ({hi[0]:.1f}, {hi[1]:.1f}, "
                  f"{hi[2]:.1f})  size {hi[0] - lo[0]:.0f} x {hi[1] - lo[1]:.0f} x {hi[2] - lo[2]:.0f}")
            print(f"      groups {n_grp}  portals {n_portal}")
        elif tag == "MOGI":
            for i in range(len(p) // 32):
                groups += 1
                indoor += bool(struct.unpack_from("<I", p, i * 32)[0] & 0x2000)
    if groups:
        print(f"      {indoor} indoor group(s), {groups - indoor} outdoor")


def show(data_dir: str, directory: str) -> None:
    path = f"World\\Maps\\{directory}\\{directory}.wdt"
    print(f"\n== {directory}   ({path})")
    raw = wmo_info.find_file(data_dir, path)
    if raw is None:
        print("   not in the archives")
        return
    names: list[str] = []
    tiles = 0
    for tag, p in wmo_info.chunks(raw):
        if tag == "MPHD":
            flags = struct.unpack_from("<I", p, 0)[0]
            print(f"   MPHD flags 0x{flags:x}" + ("  (one global WMO: no terrain)" if flags & 0x1 else ""))
        elif tag == "MAIN":
            tiles = sum(1 for i in range(len(p) // 8) if struct.unpack_from("<I", p, i * 8)[0] & 1)
            print(f"   terrain tiles: {tiles}")
        elif tag == "MWMO":
            names = wmo_info.zero_terminated(p)
            for n in names:
                print(f"   MWMO {n}")
        elif tag == "MODF":
            for k in range(len(p) // 64):
                (nid, uid) = struct.unpack_from("<2I", p, k * 64)
                pos = struct.unpack_from("<3f", p, k * 64 + 8)
                rot = struct.unpack_from("<3f", p, k * 64 + 20)
                lo = struct.unpack_from("<3f", p, k * 64 + 32)
                hi = struct.unpack_from("<3f", p, k * 64 + 44)
                fl, dset, nset = struct.unpack_from("<3H", p, k * 64 + 56)
                wx, wy, wz = ORIGIN - pos[2], ORIGIN - pos[0], pos[1]
                print(f"   MODF #{k}: {names[nid] if nid < len(names) else nid}")
                print(f"      placed at world X {wx:.2f}  Y {wy:.2f}  Z {wz:.2f}   (raw pos {pos[0]:.3f} {pos[1]:.3f} "
                      f"{pos[2]:.3f})")
                print(f"      rotation (deg) {rot[0]:.2f} {rot[1]:.2f} {rot[2]:.2f}   flags 0x{fl:x}  doodad set {dset}")
                print(f"      world box X {ORIGIN - hi[2]:.1f}..{ORIGIN - lo[2]:.1f}  Y {ORIGIN - hi[0]:.1f}.."
                      f"{ORIGIN - lo[0]:.1f}  Z {lo[1]:.1f}..{hi[1]:.1f}")
                if nid < len(names):
                    wmo_summary(data_dir, names[nid])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("data_dir", help="the client's Data folder")
    ap.add_argument("maps", nargs="+", help="map folder names (MoltenCore), or map ids with --dbc")
    ap.add_argument("--dbc", help="a folder holding Map.dbc, to give map ids instead of folder names")
    args = ap.parse_args()
    dirs = args.maps
    if args.dbc:
        ids = [int(m) for m in args.maps]
        found = map_dirs_from_dbc(args.dbc, ids)
        for i in ids:
            print(f"map {i}: {found.get(i, '(not in Map.dbc)')}")
        dirs = [found[i] for i in ids if i in found]
    for d in dirs:
        show(args.data_dir, d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
