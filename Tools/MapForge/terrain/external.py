#!/usr/bin/env python3
"""Stage a ready-made (hand-authored) map's terrain for package.py build, instead of generating it.

MapForge normally generates terrain from a spec (terrain/build.py). A map made in another editor (Noggit, say)
already has its ADT/WDT/WDL, so there is nothing to generate: this reads those files and writes the same output
package.py build consumes -- World/Maps/<directory>/ with the files, plus terrain_manifest.json -- so the DBC
forge, the archive placement (package.py doctor) and install-map.sh all run unchanged.

    python3 -I Tools/MapForge/terrain/external.py --src <folder with the .wdt/.wdl/.adt> \
        --directory Guildhaven --out <output folder> [--map-id 725]

It takes only the terrain files (never a Map.dbc or any other DBC: those belong to the realm and are handled by
the forge, which adds this map's one row to the players' current table). The ADT doodads/WMOs are placed inside
the ADT itself (MDDF/MODF), so the client draws them with no server spawns; the manifest's placements are empty.

What it checks:
  - exactly one <name>.wdt, an optional <name>.wdl, and one or more <name>_XX_YY.adt, all for the same <name>;
  - every ADT tile (XX, YY) is marked present in the WDT's MAIN table, and every present tile has its ADT;
  - the MCNK area ids actually used by the terrain (package.py build then checks they are the config's, 0 aside).

The files keep their names; the client resolves World\\Maps\\<Directory>\\... case-insensitively, so a lower-case
guildhaven.wdt answers the extractor's Guildhaven.wdt. Nothing from <src> is executed or imported.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import sys


class ExternalError(Exception):
    pass


def _chunks(data: bytes):
    """Yield (tag, offset_of_body, size) for each IFF chunk; WoW stores the 4-char tag reversed in the file."""
    i, n = 0, len(data)
    while i + 8 <= n:
        tag = data[i:i + 4][::-1].decode("ascii", "replace")
        size = struct.unpack_from("<I", data, i + 4)[0]
        body = i + 8
        if body + size > n:
            raise ExternalError(f"chunk {tag!r} at {i} runs past the end of the file")
        yield tag, body, size
        i = body + size


def wdt_tiles(data: bytes) -> set[tuple[int, int]]:
    """The (x, y) tiles the WDT's MAIN table marks present (flag 0x1). MAIN is a 64x64 grid, row-major by y."""
    for tag, body, size in _chunks(data):
        if tag == "MAIN":
            if size < 64 * 64 * 8:
                raise ExternalError(f"MAIN is {size} bytes, a 64x64 grid needs {64 * 64 * 8}")
            present = set()
            for idx in range(64 * 64):
                flags = struct.unpack_from("<I", data, body + idx * 8)[0]
                if flags & 0x1:
                    present.add((idx % 64, idx // 64))  # (x, y): column, row
            return present
    raise ExternalError("no MAIN chunk: not a WDT, or an unexpected layout")


def adt_area_ids(data: bytes) -> set[int]:
    """The area ids in an ADT's 256 MCNK chunks (areaid is at offset 0x34 in each MCNK's 128-byte header)."""
    out = set()
    for tag, body, size in _chunks(data):
        if tag == "MCNK" and size >= 0x38:
            out.add(struct.unpack_from("<I", data, body + 0x34)[0])
    return out


def _one(files: list[str], ext: str, where: str) -> str | None:
    hits = [f for f in files if f.lower().endswith(ext)]
    if len(hits) > 1:
        raise ExternalError(f"{where}: more than one {ext} file ({', '.join(sorted(hits))}); expected one map")
    return hits[0] if hits else None


def stage(src: str, directory: str, out: str, map_id: int | None) -> dict:
    if not os.path.isdir(src):
        raise ExternalError(f"{src}: not a folder")

    # The terrain files may sit at the top of src or under a World/Maps/<anything> subtree; find the folder that
    # holds the .wdt and take the files from there.
    holder = None
    for root, _dirs, names in os.walk(src):
        if any(n.lower().endswith(".wdt") for n in names):
            if holder is not None:
                raise ExternalError(f"{src}: .wdt files in more than one folder; point --src at the map's own folder")
            holder = root
    if holder is None:
        raise ExternalError(f"{src}: no .wdt found")

    names = [n for n in sorted(os.listdir(holder)) if os.path.isfile(os.path.join(holder, n))]
    wdt = _one(names, ".wdt", holder)
    wdl = _one(names, ".wdl", holder)
    adts = [n for n in names if n.lower().endswith(".adt")]
    if not wdt:
        raise ExternalError(f"{holder}: no .wdt")
    if not adts:
        raise ExternalError(f"{holder}: no .adt tiles")

    stem = wdt[:-4].lower()
    bad = [n for n in adts if not n.lower().startswith(stem + "_")]
    if bad:
        raise ExternalError(f"{holder}: ADT(s) not named {stem}_XX_YY.adt: {', '.join(bad)}")
    if wdl and wdl[:-4].lower() != stem:
        raise ExternalError(f"{holder}: the WDL {wdl} does not match the WDT {wdt}")

    # Parse tiles from the ADT names and cross-check against the WDT's MAIN table.
    adt_tiles: dict[tuple[int, int], str] = {}
    for n in adts:
        parts = n[:-4].split("_")
        try:
            x, y = int(parts[-2]), int(parts[-1])
        except (ValueError, IndexError):
            raise ExternalError(f"{holder}: cannot read tile coords from {n}")
        adt_tiles[(x, y)] = n

    with open(os.path.join(holder, wdt), "rb") as f:
        present = wdt_tiles(f.read())
    missing_adt = sorted(present - set(adt_tiles))
    extra_adt = sorted(set(adt_tiles) - present)
    if missing_adt:
        raise ExternalError(f"the WDT marks tiles present with no ADT file: {missing_adt}")
    if extra_adt:
        raise ExternalError(f"ADT files for tiles the WDT does not mark present: {extra_adt}")

    areas: set[int] = set()
    for (x, y), n in adt_tiles.items():
        with open(os.path.join(holder, n), "rb") as f:
            areas |= adt_area_ids(f.read())

    # Lay the files out exactly where package.py build's read_terrain expects them.
    dest = os.path.join(out, "World", "Maps", directory)
    os.makedirs(dest, exist_ok=True)
    staged = []
    for n in [wdt] + ([wdl] if wdl else []) + adts:
        shutil.copy2(os.path.join(holder, n), os.path.join(dest, n))
        staged.append(n)

    manifest = {
        "generator": "external",
        "map_id": map_id,
        "directory": directory,
        "tiles": sorted([list(t) for t in present]),
        "area_ids": sorted(areas),
        "server_tiles": None,     # no modern/HD swap: the client ADT is also the server copy
        "extra_files": [],        # no extra modern assets to inject
        "placements": [],         # doodads/WMOs are baked into the ADT (MDDF/MODF), drawn client-side
        "files": staged,
    }
    with open(os.path.join(out, "terrain_manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", required=True, help="a folder holding the map's .wdt/.wdl/.adt (searched recursively)")
    ap.add_argument("--directory", required=True, help="the map's World\\Maps\\ folder and its Map.dbc Directory")
    ap.add_argument("--out", required=True, help="output folder (gets World/Maps/<directory>/ + terrain_manifest.json)")
    ap.add_argument("--map-id", type=int, help="recorded in the manifest for reference (the config sets the real id)")
    args = ap.parse_args()
    try:
        m = stage(args.src, args.directory, args.out, args.map_id)
    except ExternalError as e:
        print(f"external terrain: {e}", file=sys.stderr)
        return 1
    print(f"staged {len(m['files'])} file(s) for {args.directory}: tiles {m['tiles']}, area ids {m['area_ids']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
