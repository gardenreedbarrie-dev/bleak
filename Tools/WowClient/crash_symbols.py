#!/usr/bin/env python3
"""Name the functions of a Bleakhold.exe crash, from the build's linker map (CI artifact bleakhold-client-x64-map).

    python3 -I Tools/WowClient/crash_symbols.py <map file | .zip | https URL of the artifact zip> 0001:00159CB4 ...

The client's crash report (<date>_Crash.txt) gives each frame of the crashing thread as a "Logical addr"
(section:offset, e.g. 0001:00159CB4) or as an absolute address; a logical address is what this takes (for an
absolute one: subtract the DBG-MODULE base of Bleakhold.exe, then 0x1000, for section 0001). The map must come from
the SAME build: the report's DBG-MODULE line ends with the exe's link timestamp, and the map's "Timestamp is"
line must show the same number (printed below).

For each address it prints the nearest public or static symbol at or below it, the offset into it, and the
object file (which source file it came from), with a light undecoration of MSVC names (?Name@Class@@... ->
Class::Name). Nothing is written except a downloaded zip kept in memory.
"""
from __future__ import annotations

import bisect
import io
import re
import sys
import urllib.request
import zipfile

LINE = re.compile(r"^\s*([0-9a-fA-F]{4}):([0-9a-fA-F]{8})\s+(\S+)\s+([0-9a-fA-F]{8,16})\s+(?:f\s+)?(?:i\s+)?(\S.*)?$")


def load_text(src: str) -> str:
    if src.startswith(("http://", "https://")):
        with urllib.request.urlopen(src, timeout=120) as r:
            data = r.read()
    else:
        with open(src, "rb") as f:
            data = f.read()
    if data[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(data))
        maps = [n for n in z.namelist() if n.lower().endswith(".map")]
        # Bleakhold.exe's own map, not WowClient64's or a static library's
        maps.sort(key=lambda n: (0 if "bleakhold" in n.lower() else 1, -z.getinfo(n).file_size))
        if not maps:
            sys.exit("no .map file in the zip")
        print(f"(map: {maps[0]} of {', '.join(maps)})")
        data = z.read(maps[0])
    return data.decode("latin-1")


def undecorate(name: str) -> str:
    m = re.match(r"^\?([^@?]+)@((?:[^@]+@)*)@", name)
    if not m:
        return name
    parts = [p for p in m.group(2).split("@") if p]
    return "::".join(list(reversed(parts)) + [m.group(1)])


def main() -> int:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    text = load_text(sys.argv[1])
    stamp = re.search(r"Timestamp is ([0-9a-fA-F]+)\s*\(([^)]*)\)", text)
    if stamp:
        print(f"map timestamp {int(stamp.group(1), 16)} ({stamp.group(2).strip()}) "
              "-- must equal the number at the end of the report's Bleakhold.exe DBG-MODULE line")
    syms: dict[int, list[tuple[int, str, str]]] = {}
    for line in text.splitlines():
        m = LINE.match(line)
        if not m:
            continue
        sec, off = int(m.group(1), 16), int(m.group(2), 16)
        syms.setdefault(sec, []).append((off, m.group(3), (m.group(5) or "").strip()))
    for sec in syms:
        syms[sec].sort()
    for arg in sys.argv[2:]:
        m = re.match(r"^([0-9a-fA-F]{4}):([0-9a-fA-F]{8})$", arg)
        if not m:
            print(f"{arg}: give a logical address like 0001:00159CB4")
            continue
        sec, off = int(m.group(1), 16), int(m.group(2), 16)
        table = syms.get(sec, [])
        i = bisect.bisect_right(table, (off, "￿", "")) - 1
        if i < 0:
            print(f"{arg}: no symbol at or below it")
            continue
        start, name, obj = table[i]
        print(f"{arg}  {undecorate(name)} +0x{off - start:X}   [{obj}]   ({name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
