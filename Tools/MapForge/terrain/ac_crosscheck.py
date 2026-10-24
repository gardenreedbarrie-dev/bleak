"""Cross-check terrain output with AzerothCore's own map_extractor (and optionally vmap4_extractor).

    python3 -I Tools/MapForge/terrain/ac_crosscheck.py OUT_DIR --extractor PATH/map_extractor [--map-id 9000]
        [--vmap4 PATH/vmap4_extractor] [--work DIR] [--keep]

It builds a minimal fake client folder: Data/enUS/locale-enUS.MPQ (packed with Tools/MpqPack) holding
component.wow-enUS.txt (build 12340), a made-up DBFilesClient\\Map.dbc with one row (the map id and directory),
a made-up DBFilesClient\\LiquidType.dbc (ids 1-21, type 0-3 like the stock table's first four rows) and the map's
World\\Maps files. No Blizzard data is involved. It runs `map_extractor -e 1 -f 0` (maps only, float heights) and
reads the .map files it writes (format of map_fileheader in src/tools/map_extractor/System.cpp, version 9), then
compares them with the ADTs as validate.py parses them: every height (V9/V8 grids), the area ids, holes and liquid
cells and levels. With --vmap4 it also runs vmap4_extractor (which walks every top-level ADT chunk by size) and
checks that it processed each tile.

Exit code 0 = the extractor accepted every tile and everything matches.
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "MpqPack"))

import validate  # noqa: E402
from mpqpack import build_archive  # noqa: E402


def make_dbc(fields: int, records: list[list], strings: list[str]) -> bytes:
    """A WDBC file. Records hold ints, or str (stored in the string block)."""
    block = bytearray(b"\0")
    offsets = {}
    for s in strings:
        if s not in offsets:
            offsets[s] = len(block)
            block += s.encode("ascii") + b"\0"
    body = bytearray()
    for rec in records:
        if len(rec) != fields:
            raise ValueError("field count")
        for v in rec:
            body += struct.pack("<I", offsets[v] if isinstance(v, str) else v)
    return b"WDBC" + struct.pack("<4I", len(records), fields, fields * 4, len(block)) + bytes(body) + bytes(block)


def build_fake_client(out_dir: str, client_dir: str, map_name: str, map_id: int) -> None:
    folder, name = validate.find_map(out_dir, map_name)
    files = []
    for f in sorted(os.listdir(folder)):
        with open(os.path.join(folder, f), "rb") as fh:
            files.append((f"World\\Maps\\{name}\\{f}", fh.read()))
    # ReadBuild takes the first version="..."; no XML declaration, or its version="1.0" would win.
    files.append(("component.wow-enUS.txt", b'<component.wow version="12340" locale="enUS"/>\r\n'))
    files.append(("DBFilesClient\\Map.dbc", make_dbc(2, [[map_id, name]], [name])))
    liquid_types = [[i, f"Liquid{i}", 0, {1: 0, 2: 1, 3: 2, 4: 3}.get(i, 0)] for i in range(1, 22)]
    files.append(("DBFilesClient\\LiquidType.dbc", make_dbc(4, liquid_types, [r[1] for r in liquid_types])))
    # vmap4_extractor exits without GameObjectDisplayInfo.dbc; an empty table satisfies it.
    files.append(("DBFilesClient\\GameObjectDisplayInfo.dbc", make_dbc(19, [], [])))
    locale = os.path.join(client_dir, "Data", "enUS")
    os.makedirs(locale, exist_ok=True)
    with open(os.path.join(locale, "locale-enUS.MPQ"), "wb") as fh:
        fh.write(build_archive(files))


def read_map_file(path: str) -> dict:
    with open(path, "rb") as f:
        d = f.read()
    hdr = struct.unpack_from("<4s10I", d, 0)
    if hdr[0] != b"MAPS" or hdr[1] != 9:
        raise ValueError(f"{path}: not a v9 .map file")
    (_, _, build, area_ofs, _, height_ofs, _, liquid_ofs, _, holes_ofs, holes_size) = hdr
    out = {"build": build}
    magic, aflags, garea = struct.unpack_from("<4sHH", d, area_ofs)
    if magic != b"AREA":
        raise ValueError("bad AREA")
    if aflags & 1:
        out["areas"] = [[garea] * 16 for _ in range(16)]
    else:
        flat = struct.unpack_from("<256H", d, area_ofs + 8)
        out["areas"] = [list(flat[r * 16:(r + 1) * 16]) for r in range(16)]
    magic, hflags, gh, gmax = struct.unpack_from("<4sIff", d, height_ofs)
    if magic != b"MHGT":
        raise ValueError("bad MHGT")
    p = height_ofs + 16
    if hflags & 1:
        v9 = [[gh] * 129 for _ in range(129)]
        v8 = [[gh] * 128 for _ in range(128)]
    elif hflags & 6:
        raise ValueError("run map_extractor with -f 0 (float heights)")
    else:
        f9 = struct.unpack_from(f"<{129 * 129}f", d, p)
        f8 = struct.unpack_from(f"<{128 * 128}f", d, p + 129 * 129 * 4)
        v9 = [list(f9[r * 129:(r + 1) * 129]) for r in range(129)]
        v8 = [list(f8[r * 128:(r + 1) * 128]) for r in range(128)]
    out["v9"] = v9
    out["v8"] = v8
    out["liquid"] = None
    if liquid_ofs:
        magic, lflags, lliq, ltype, ox, oy, w, h, level = struct.unpack_from("<4sBBHBBBBf", d, liquid_ofs)
        if magic != b"MLIQ":
            raise ValueError("bad MLIQ")
        q = liquid_ofs + 16
        liq = {"flags": lflags, "liquid_flags": lliq, "type": ltype, "x": ox, "y": oy, "w": w, "h": h,
               "level": level, "entry": None, "cell_flags": None, "heights": None}
        if not lflags & 1:
            liq["entry"] = struct.unpack_from("<256H", d, q)
            liq["cell_flags"] = struct.unpack_from("<256B", d, q + 512)
            q += 512 + 256
        if not lflags & 2:
            liq["heights"] = struct.unpack_from(f"<{w * h}f", d, q)
        out["liquid"] = liq
    out["holes"] = None
    if holes_ofs and holes_size:
        out["holes"] = struct.unpack_from("<256H", d, holes_ofs)
    return out


def compare(rep: validate.Report, maps_dir: str, map_id: int) -> list[str]:
    problems = []
    for (tx, ty), info in sorted(rep.adts.items()):
        path = os.path.join(maps_dir, f"{map_id:03}{ty:02}{tx:02}.map")
        if not os.path.exists(path):
            problems.append(f"tile {tx},{ty}: map_extractor wrote no {os.path.basename(path)}")
            continue
        m = read_map_file(path)
        if m["build"] != 12340:
            problems.append(f"{path}: build {m['build']}")
        worst = 0.0
        for (cx, cy), ch in info.chunks.items():
            hs = ch["heights"]
            for r in range(9):
                for c in range(9):
                    worst = max(worst, abs(m["v9"][cy * 8 + r][cx * 8 + c] - hs[r * 17 + c]))
            for r in range(8):
                for c in range(8):
                    worst = max(worst, abs(m["v8"][cy * 8 + r][cx * 8 + c] - hs[r * 17 + 9 + c]))
            if m["areas"][cy][cx] != (ch["area"] & 0xFFFF):
                problems.append(f"tile {tx},{ty} chunk {cx},{cy}: area {m['areas'][cy][cx]} != {ch['area']}")
            hole = m["holes"][cy * 16 + cx] if m["holes"] else 0
            if hole != ch["holes"]:
                problems.append(f"tile {tx},{ty} chunk {cx},{cy}: holes 0x{hole:X} != 0x{ch['holes']:X}")
        if worst > 1e-4:
            problems.append(f"tile {tx},{ty}: extracted heights differ by up to {worst:.5f}")
        liq = m["liquid"]
        if info.mh2o and liq is None:
            problems.append(f"tile {tx},{ty}: the ADT has water but the .map has none")
        if liq is not None:
            if not info.mh2o:
                problems.append(f"tile {tx},{ty}: the .map has water the ADT does not have")
            levels = {round(inst["max"], 3) for inst in info.mh2o.values()}
            for (cx, cy), inst in info.mh2o.items():
                entry = liq["entry"][cy * 16 + cx] if liq["entry"] else liq["type"]
                if entry != inst["type"]:
                    problems.append(f"tile {tx},{ty} chunk {cx},{cy}: liquid entry {entry} != {inst['type']}")
                flags = liq["cell_flags"][cy * 16 + cx] if liq["cell_flags"] else liq["liquid_flags"]
                if not flags & 0x01 and inst["type"] in (1, 5, 9, 13, 17):
                    problems.append(f"tile {tx},{ty} chunk {cx},{cy}: liquid flags 0x{flags:X} lack water")
            if liq["flags"] & 2:
                if round(liq["level"], 3) not in levels:
                    problems.append(f"tile {tx},{ty}: flat liquid level {liq['level']} not in {sorted(levels)}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run AzerothCore's map_extractor on MapForge output and compare.")
    ap.add_argument("out", help="MapForge output folder (holding World/Maps/<Dir>)")
    ap.add_argument("--extractor", required=True, help="path of a built map_extractor")
    ap.add_argument("--vmap4", help="path of a built vmap4_extractor (optional)")
    ap.add_argument("--map", help="map directory name")
    ap.add_argument("--map-id", type=int, default=9000)
    ap.add_argument("--work", help="work folder (default: a temporary one)")
    ap.add_argument("--keep", action="store_true", help="keep the work folder")
    args = ap.parse_args(argv)

    rep = validate.validate_map(args.out, args.map)
    if not rep.ok:
        print("validate.py reports errors; fix those first:")
        for e in rep.errors[:20]:
            print(f"  {e}")
        return 1
    work = args.work or tempfile.mkdtemp(prefix="mapforge-ac-")
    os.makedirs(work, exist_ok=True)
    client = os.path.join(work, "client")
    output = os.path.join(work, "extracted")
    for d in (client, output):
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)
    build_fake_client(args.out, client, args.map, args.map_id)
    run = subprocess.run([os.path.abspath(args.extractor), "-e", "1", "-f", "0", "-i", client, "-o", output],
                         cwd=work, capture_output=True, text=True, timeout=600)
    log = run.stdout + run.stderr
    with open(os.path.join(work, "map_extractor.log"), "w", encoding="utf-8") as fh:
        fh.write(log)
    problems = []
    if run.returncode != 0:
        problems.append(f"map_extractor exited with {run.returncode}")
    for line in log.splitlines():
        if "Error loading" in line or "Can't" in line or "Wrong liquid" in line or "No such file" in line:
            problems.append(f"map_extractor: {line.strip()}")
    problems += compare(rep, os.path.join(output, "maps"), args.map_id)
    tiles = len(rep.adts)
    if args.vmap4:
        vwork = os.path.join(work, "vmap")
        if os.path.exists(vwork):
            shutil.rmtree(vwork)
        os.makedirs(vwork)
        vrun = subprocess.run([os.path.abspath(args.vmap4), "-d", os.path.join(client, "Data")], cwd=vwork,
                              capture_output=True, text=True, timeout=600, input="\n")
        vlog = vrun.stdout + vrun.stderr
        with open(os.path.join(work, "vmap4_extractor.log"), "w", encoding="utf-8") as fh:
            fh.write(vlog)
        if f"Processing Map {args.map_id}" not in vlog:
            problems.append("vmap4_extractor did not process the map (see vmap4_extractor.log)")
        print(f"vmap4_extractor exit {vrun.returncode}; log in {os.path.join(work, 'vmap4_extractor.log')}")
    print(f"map_extractor exit {run.returncode}; {tiles} tiles compared; log in "
          f"{os.path.join(work, 'map_extractor.log')}")
    for p in problems:
        print(f"PROBLEM {p}")
    if not problems:
        print("OK: AzerothCore's extractor accepted every tile; heights, areas, holes and liquids match the ADTs")
    if not args.keep and not args.work:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
