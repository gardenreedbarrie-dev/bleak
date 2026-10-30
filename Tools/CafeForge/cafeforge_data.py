#!/usr/bin/env python3
"""CafeForge data: the files made from the café catalogue Tools/CafeForge/cafe.json.

    python3 -I Tools/CafeForge/cafeforge_data.py [--check]

Validates cafe.json (cflib/catalog.py: ids, references, the recipe and level rules, genders, protocol caps and the
default layout's footprint checks), then writes the three generated files (cflib/gen.py):
    Server/mod-bleakhold-ui/src/BleakholdCafeData.h
    Interface/AddOns/Bleakhold/CafeData.lua
    Server/mod-bleakhold-ui/data/sql/db-world/04_bleakhold_cafe_templates.sql
--check only compares them with cafe.json and exits 1 when one is stale (CI). Needs only the standard library.
cafeforge.py data [--check] runs the same (main(argv)).
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # keep the repository free of __pycache__
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from cflib import catalog  # noqa: E402
from cflib import gen  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cafeforge_data.py", description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="only compare; exit 1 when a generated file is stale")
    ap.add_argument("--catalog", default=catalog.CAFE_JSON, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        doc = catalog.load(args.catalog)
    except catalog.CatalogError as ex:
        for p in ex.problems:
            print("cafe.json: %s" % p)
        return 1
    stale = gen.generate(doc, check=args.check)
    for rel in stale:
        if args.check:
            print("stale: %s (run python3 -I Tools/CafeForge/cafeforge_data.py)" % rel)
        else:
            print("wrote %s" % rel)
    if not stale:
        print("generated files are up to date (%d recipes, %d personas, %d layout rows)"
              % (len(doc["recipes"]) * len(doc["cafes"]), len(doc["personas"]), len(gen.layout_rows(doc))))
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
