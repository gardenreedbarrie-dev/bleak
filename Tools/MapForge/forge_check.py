#!/usr/bin/env python3
"""Check a map's DBC config against the realm's real DBCs in seconds, before a full build.

    python3 -I Tools/MapForge/forge_check.py --config bleakhold_crucible.json --dbc /root/mapforge-crucible/dbc \
        [--spec specs/crucible_v1.json] [--areas 'molten|onyxia|searing|burning']

It runs the same forge package.py build runs (dbc/forge.py) on the tables in --dbc, entirely in memory: nothing is
written, no archive or SQL is made. A config mistake (a skybox the client does not have, a template id that is not
there, a map id or directory already taken) then shows in a second instead of after the whole build. The --dbc
folder is the one a build pulls (build-royale.sh's step 3 leaves it in <work folder>/dbc).

It also prints what the choices in the config can be made from:
  - every map's default light (a Light row at 0,0,0): what light.params_from_map can copy;
  - with --areas, the AreaTable rows whose name matches: what zone.template can copy (music, ambience, flags).

Exit code: 0 the forge accepts the config, 1 it does not (the reason is printed), 2 it could not run.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from dbc import SIBLINGS  # noqa: E402,F401  (extends sys.path with the sibling tools)
from dbc import config as configmod  # noqa: E402
from dbc import forge as forgemod  # noqa: E402
from rflib.dbc import to_signed  # noqa: E402

import package  # noqa: E402  (read_tables: the same table loading as the build)


def in_tools(path: str) -> str:
    return path if os.path.isabs(path) or os.path.exists(path) else os.path.join(HERE, path)


def default_lights(light) -> dict[int, int]:
    """{map id: light id} of every map's default light (DayNight::LightLoad: the last row at 0,0,0 counts)."""
    out = {}
    for r in light.rows:
        if all(light.get(r, f"gameCoords[{i}]") in (0, 0x80000000) for i in range(3)):
            out[light.get_signed(r, "continentID")] = to_signed(r[0])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--dbc", required=True, help="a folder of the realm's DBCs (a build's <work folder>/dbc)")
    ap.add_argument("--spec", help="the terrain spec, for world_map_area bounds 'auto' (its tiles)")
    ap.add_argument("--areas", help="also list AreaTable rows whose name matches this regex (zone.template choices)")
    args = ap.parse_args()

    try:
        cfg = configmod.load(in_tools(args.config))
        required, optional = forgemod.tables_needed(cfg)
        for extra in ("Light", "AreaTable", "Map"):
            if extra not in required and extra not in optional:
                optional.append(extra)
        tables, notes = package.read_tables(args.dbc, required, optional)
    except Exception as e:  # noqa: BLE001 (any failure to load is a 'could not run')
        print(f"could not run: {e}")
        return 2

    maps = {to_signed(r[0]): tables["Map"].get_str(r, "directory") for r in tables["Map"].rows}

    if "Light" in tables:
        lights = default_lights(tables["Light"])
        print("maps with a default light (light.params_from_map can copy these):")
        for mid in (409, 249, 389, 229, 230, 469, 0, 1, 571):
            if mid in maps:
                mark = f"light {lights[mid]}" if mid in lights else "NO default light"
                print(f"  {mid:>4}  {maps[mid]:<24} {mark}")
        print(f"  ({len(lights)} maps in all have a default light)")
        print()

    if args.areas:
        at = tables["AreaTable"]
        pat = re.compile(args.areas, re.I)
        print("AreaTable rows (zone.template can copy their music, ambience and flags):")
        print(f"  {'id':>5} {'map':>4}  {'flags':<40} name")
        for r in at.rows:
            names = at.get_loc(r, "areaName")
            name = next((n for n in names if n), "")
            if pat.search(name):
                flags = ",".join(configmod.flag_names(at.get(r, "flags"))) or "-"
                print(f"  {to_signed(r[0]):>5} {at.get_signed(r, 'continentID'):>4}  {flags[:40]:<40} {name}")
        print()

    wdt = None
    if args.spec:
        from terrain.spec import load_spec
        wdt = set(load_spec(in_tools(args.spec)).tiles)

    # The same two stages as package.py build: the forge, then the verification of the rows it wrote (forge.check,
    # which is where a flag kept from the zone template is refused).
    input_bytes = {name: table.to_bytes() for name, table in tables.items()}
    try:
        result = forgemod.Forge(tables, cfg, None, wdt).run()
    except forgemod.ForgeError as e:
        print(f"FORGE REFUSES THE CONFIG: {e}")
        return 1
    written = sorted(result.changes)
    output_bytes = {name: tables[name].to_bytes() for name in written}
    problems = forgemod.check({n: input_bytes[n] for n in written}, output_bytes, cfg, result)
    for n in notes + list(result.notes):
        print(f"  note: {n}")
    for w in result.warnings:
        print(f"  warning: {w}")
    if problems:
        print("THE ROWS THE FORGE WROTE FAIL THE BUILD'S CHECK:")
        for p_ in problems:
            print(f"  - {p_}")
        return 1
    print(f"OK: the forge accepts the config and its rows pass the build's check ({', '.join(written)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
