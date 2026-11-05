#!/usr/bin/env python3
"""Read a WMO's real geometry out of the client's archives: bounding box, groups, doodad sets, entrances.

MapForge places a WMO by world position and facing, but without the model it has to guess the footprint
("bounds_source": "radius" in the terrain manifest) and it cannot know where the model's floor sits or which
way its door faces. This prints what the file itself says, so a spec can carry real numbers:

  - MOHD: the root bounding box (min/max). Its Z tells where the floor is relative to the placement origin:
    a WMO placed at world z Z has its lowest point at Z + bbox_min_z, so to stand a floor ON the ground the
    placement z is (ground - bbox_min_z). Its X/Y give the footprint radius the terrain pad has to clear.
  - MODS/MODN: the doodad sets (the `doodad_set` field picks one).
  - MOGI/MOGN: each group's name, bounding box and flags, with the indoor/outdoor bit. The groups that sit at
    the edge of the root box are the ends of the model: they are where a door can be.

WMO axes are the model's own (X right, Y up, Z forward in file order for the bbox as stored); this prints the
raw values, and also the horizontal extent and height read the way MapForge's world uses them.

Usage (on the VPS, with the real client):
    python3 -I wmo_info.py <client Data folder> "World\\wmo\\Dungeon\\KL_OnyxiasLair\\KL_OnyxiasLair_B.wmo"
    python3 -I wmo_info.py <Data> <path> --groups        # also every group's box
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

MPQPACK_DIR = os.environ.get("MPQPACK_DIR", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MPQPACK_DIR)

try:
    import mpqpack
except Exception as exc:  # pragma: no cover
    sys.exit(f"could not import mpqpack from {MPQPACK_DIR}: {exc}")

# The CRC-tolerant reader: Blizzard's files carry a sector-CRC block that mpqpack.py's own reader refuses.
try:
    from list_client_files import read_block_crc_tolerant

    mpqpack.MpqArchive.read_block = read_block_crc_tolerant
except Exception:
    print("note: list_client_files.py not next to this script; retail archives may fail to read", file=sys.stderr)


def chunks(data: bytes):
    """Yield (tag, payload). Chunk tags are stored reversed, so MOHD is written 'DHOM'."""
    off = 0
    while off + 8 <= len(data):
        tag = data[off:off + 4][::-1].decode("ascii", "replace")
        size = struct.unpack_from("<I", data, off + 4)[0]
        payload = data[off + 8:off + 8 + size]
        yield tag, payload
        off += 8 + size


def zero_terminated(block: bytes) -> list[str]:
    return [s.decode("utf-8", "replace") for s in block.split(b"\0") if s]


def find_file(data_dir: str, want: str) -> bytes | None:
    want_l = want.lower().replace("/", "\\")
    archives = []
    for root, _d, files in os.walk(data_dir):
        for f in files:
            if f.lower().endswith(".mpq"):
                archives.append(os.path.join(root, f))
    # Later patches override the base archives, so read patches last and keep the last hit.
    archives.sort(key=lambda p: ("patch" in os.path.basename(p).lower(), os.path.basename(p).lower()))
    found = None
    for path in archives:
        try:
            a = mpqpack.MpqArchive(path)
            if a.has_file(want) or a.has_file(want_l):
                found = a.read(want if a.has_file(want) else want_l)
                print(f"  (from {os.path.basename(path)})", file=sys.stderr)
        except Exception:
            continue
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("wmo", help="client path of the ROOT wmo, e.g. World\\wmo\\...\\X.wmo")
    ap.add_argument("--groups", action="store_true", help="print every group's box and flags")
    args = ap.parse_args()

    raw = find_file(args.data_dir, args.wmo)
    if raw is None:
        return print(f"not found in any archive: {args.wmo}") or 2

    print(f"{args.wmo}   ({len(raw)} bytes)")

    group_names: list[str] = []
    doodad_sets: list[tuple[str, int, int]] = []
    groups: list[tuple[int, float, float, float, float, float, float, int]] = []

    for tag, payload in chunks(raw):
        if tag == "MOHD" and len(payload) >= 64:
            (n_tex, n_grp, n_portal, n_light, n_dd_name, n_dd_def, n_dd_set,
             amb, wmo_id) = struct.unpack_from("<9I", payload, 0)
            bb = struct.unpack_from("<6f", payload, 36)
            lo, hi = bb[0:3], bb[3:6]
            print(f"\n  groups {n_grp}  portals {n_portal}  lights {n_light}  "
                  f"doodads {n_dd_def} in {n_dd_set} set(s)  wmoID {wmo_id}")
            print(f"  bbox min  ({lo[0]:10.3f}, {lo[1]:10.3f}, {lo[2]:10.3f})")
            print(f"  bbox max  ({hi[0]:10.3f}, {hi[1]:10.3f}, {hi[2]:10.3f})")
            size = [hi[i] - lo[i] for i in range(3)]
            print(f"  size      ({size[0]:10.3f}, {size[1]:10.3f}, {size[2]:10.3f})")
            # MapForge needs a horizontal footprint radius and the floor offset.
            radius = max(abs(lo[0]), abs(hi[0]), abs(lo[1]), abs(hi[1]))
            print(f"\n  --> footprint radius (for the spec's 'radius'): {radius:.1f}")
            print(f"  --> lowest point is {lo[2]:.3f} from the origin: to stand the model's bottom on ground G,")
            print(f"      place it at z = G - ({lo[2]:.3f}) = G + {-lo[2]:.3f}")
            print(f"  --> the terrain pad must be flat for at least {radius:.0f} yards around the anchor")
        elif tag == "MOGN":
            group_names = zero_terminated(payload)
        elif tag == "MODN":
            pass
        elif tag == "MODS":
            for i in range(len(payload) // 32):
                name = payload[i * 32:i * 32 + 20].split(b"\0")[0].decode("utf-8", "replace")
                start, count = struct.unpack_from("<II", payload, i * 32 + 20)
                doodad_sets.append((name, start, count))
        elif tag == "MOGI":
            for i in range(len(payload) // 32):
                flags = struct.unpack_from("<I", payload, i * 32)[0]
                box = struct.unpack_from("<6f", payload, i * 32 + 4)
                name_off = struct.unpack_from("<i", payload, i * 32 + 28)[0]
                groups.append((flags, *box, name_off))

    if doodad_sets:
        print("\n  doodad sets (the spec's 'doodad_set' is the index):")
        for i, (name, start, count) in enumerate(doodad_sets):
            print(f"    {i}: {name!r:24} {count} doodads")

    if groups:
        indoor = sum(1 for g in groups if g[0] & 0x2000)
        print(f"\n  {len(groups)} group(s): {indoor} indoor, {len(groups) - indoor} outdoor")
        if args.groups:
            raw_names = raw  # names are resolved by offset into MOGN
            mogn = b""
            for tag, payload in chunks(raw_names):
                if tag == "MOGN":
                    mogn = payload
                    break
            for i, (flags, x0, y0, z0, x1, y1, z1, noff) in enumerate(groups):
                nm = ""
                if mogn and 0 <= noff < len(mogn):
                    nm = mogn[noff:].split(b"\0")[0].decode("utf-8", "replace")
                kind = "indoor " if flags & 0x2000 else "outdoor"
                print(f"    {i:3} {kind} {nm[:28]:28} "
                      f"x {x0:8.1f}..{x1:8.1f}  y {y0:8.1f}..{y1:8.1f}  z {z0:7.1f}..{z1:7.1f}")
    elif group_names:
        print(f"\n  group names: {', '.join(group_names[:8])}{' ...' if len(group_names) > 8 else ''}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
