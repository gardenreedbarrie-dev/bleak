#!/usr/bin/env python3
"""CafeForge: the Bleakhold café's content, DBC rows and client archive (patch-4.MPQ).

    python3 -I Tools/CafeForge/cafeforge.py data [--check]
    python3 -I Tools/CafeForge/cafeforge.py art --out <folder> [--preview]
    python3 -I Tools/CafeForge/cafeforge.py doctor --patches <the realm's patch folder> --dbc <the server's data/dbc>
                                                   [--server-sql <SQL folder>]... [--out <build folder>]
                                                   [--manifest <ModelForge manifest.json>]
    python3 -I Tools/CafeForge/cafeforge.py build --patches <the realm's patch folder> --dbc <the server's data/dbc>
                                                  --out <build folder> [--force] [--preview] [--art <art folder>]
                                                  [--server-sql-out <the server's generated-SQL folder>]
    python3 -I Tools/CafeForge/cafeforge.py validate --out <build folder>
    python3 -I Tools/CafeForge/cafeforge.py sql --dbc <the server's data/dbc> --out <rev file or folder>
                                                [--patches <the realm's patch folder>] [--art <art folder>]
    python3 -I Tools/CafeForge/cafeforge.py schemas [--check | --write]

data generates the files made from cafe.json (cafeforge_data.py: BleakholdCafeData.h, CafeData.lua and the module's
04_bleakhold_cafe_templates.sql); --check only compares (CI). art runs ModelForge (Tools/ModelForge) for the café's
models and icons into <folder>/art and draws the patch markers. doctor shows, read-only, what a build would do on the
realm: for every café table and pack combination the winning archive and what happens to the café's ids there, the
spells' cast-time, duration and range rows, the archives to rebuild and the server SQL's rows in the café's ids.
build does it: the art, the café's rows forged into each table's winning copy, patch-4.MPQ, the server SQL and the
checks; raceforge.py install then puts the archives into the patch folder. validate runs the build's checks again.
sql writes the server's DBC rows alone (a dev realm before a client patch exists). schemas regenerates (or checks)
the café's DBC layouts from the client's record classes (WoW/Source/DB/Rec). Standard library only; the DBC,
archive and spell code is RaceForge's, MapForge's and MpqPack's (imported, never copied). README.md has the runbook.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # keep the repository free of __pycache__

# python3 -I leaves the script's folder off sys.path; cflib.config adds RaceForge, MpqPack and MapForge after it.
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cafeforge_data  # noqa: E402
from cflib import catalog, config, doctor, schemas  # noqa: E402
from cflib import archive, forge, sqlout, validate  # noqa: E402


def cmd_data(args):
    return cafeforge_data.main(["--check"] if args.check else [])


def cmd_doctor(args):
    return doctor.run(args)


def cmd_art(args):
    try:
        cfg = config.load(args.config, None)
        art = archive.make_art(args.out, cfg, args.preview, args.only, args.tex_scale, args.jobs)
    except (config.ConfigError, archive.ArtError) as ex:
        print("error: %s" % ex, file=sys.stderr)
        return 1
    print("art: %s (%s)" % (art.folder, art.summary(cfg)))
    for note in art.notes:
        print("  " + note)
    print("markers: %s" % os.path.join(art.folder, archive.MARKERS))
    if art.problems:
        print("%d problem(s): a build would stop" % len(art.problems))
        for p in art.problems:
            print("  - " + p)
        return 1
    print("The art is complete: cafeforge.py build can ship it.")
    return 0


def cmd_build(args):
    return forge.run(args)


def cmd_validate(args):
    return validate.run(args)


def cmd_sql(args):
    return sqlout.run(args)


def cmd_schemas(args):
    rec_dir = args.rec or schemas.default_rec_dir()
    if rec_dir is None:
        print("error: WoW/Source/DB/Rec is not in this checkout; give --rec", file=sys.stderr)
        return 1
    text = schemas.module_text(rec_dir)
    with open(schemas.__file__, encoding="utf-8") as f:
        current = f.read()
    if text == current:
        print("cflib/schemas.py is up to date (%s)" % ", ".join(schemas.TABLES))
        return 0
    if not args.write:
        print("cflib/schemas.py differs from %s: run cafeforge.py schemas --write" % rec_dir)
        return 1
    with open(schemas.__file__, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("wrote cflib/schemas.py")
    return 0


def art_options(p):
    """ModelForge options for development and the tests (not in the runbook)."""
    p.add_argument("--only", help=argparse.SUPPRESS)
    p.add_argument("--tex-scale", type=float, help=argparse.SUPPRESS)
    p.add_argument("--jobs", type=int, help=argparse.SUPPRESS)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cafeforge.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("data", help="generate the files made from cafe.json (cafeforge_data.py)")
    p.add_argument("--check", action="store_true", help="only compare; exit 1 when a generated file is stale")
    p.set_defaults(func=cmd_data)

    p = sub.add_parser("doctor", help="what a build would do on the realm (read-only)")
    p.add_argument("--patches", required=True, help="the realm's patch folder (or a game's Data folder)")
    p.add_argument("--dbc", required=True, help="the server's data/dbc: the stock copy of a table no patch holds")
    p.add_argument("--server-sql", action="append", default=[], metavar="FOLDER",
                   help="a folder of the server's SQL (bleakserv data/sql, modules); more than once is fine")
    p.add_argument("--out", help="the folder a build will write to (for the free space; default: here)")
    p.add_argument("--manifest", help="ModelForge's manifest.json: compares the display rows' bounds too")
    p.add_argument("--packs-from", default=config.RACES_JSON,
                   help="a JSON file whose archives.optional_packs are the launcher's packs (default: RaceForge's "
                        "races.json)")
    p.add_argument("--config", default=catalog.CAFE_JSON, help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("art", help="ModelForge's café models and icons, and the patch markers, into OUT/art")
    p.add_argument("--out", required=True, help="the build folder (the art goes to its art/)")
    p.add_argument("--preview", action="store_true", help="ModelForge's previews too (OUT/art/previews)")
    art_options(p)
    p.add_argument("--config", default=catalog.CAFE_JSON, help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_art)

    p = sub.add_parser("build", help="the café's archives, server SQL and checks (on the realm's server)")
    p.add_argument("--patches", required=True, help="the realm's patch folder")
    p.add_argument("--dbc", required=True, help="the server's data/dbc: the stock copy of a table no patch holds")
    p.add_argument("--out", required=True, help="the build folder (outside --patches)")
    p.add_argument("--force", action="store_true", help="replace an earlier build in --out (its art/ and the "
                   "backups of an install are kept)")
    p.add_argument("--preview", action="store_true", help="ModelForge's previews too")
    p.add_argument("--art", help="an art folder made before (cafeforge.py art --out ...); default: OUT/art, made now")
    p.add_argument("--server-sql-out", metavar="FOLDER",
                   help="the server's generated-SQL folder: the rev goes there once every check passed")
    p.add_argument("--earlier-sql", action="append", default=[], metavar="PATH",
                   help="the café's SQL of earlier versions (the deployed module SQL, the earlier revs; files or "
                        "folders, repeatable): the database check counts their rows as the café's")
    p.add_argument("--packs-from", default=config.RACES_JSON, help=argparse.SUPPRESS)
    art_options(p)
    p.add_argument("--config", default=catalog.CAFE_JSON, help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("validate", help="the checks of a build, again")
    p.add_argument("--out", required=True, help="the build folder")
    p.add_argument("--config", default=catalog.CAFE_JSON, help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("sql", help="the server's DBC rows alone (a dev realm before a client patch exists)")
    p.add_argument("--dbc", required=True, help="the server's data/dbc")
    p.add_argument("--out", required=True, help="a rev file, or a folder (a new rev_<nanoseconds>.sql goes there)")
    p.add_argument("--patches", help="the realm's patch folder (default: the server's DBCs alone)")
    p.add_argument("--art", help="an art folder (the displays' boxes; default: cafe.json's sizes)")
    p.add_argument("--check-out", metavar="FILE", help="also write the read-only check of the world database here")
    p.add_argument("--earlier-sql", action="append", default=[], metavar="PATH",
                   help="the café's SQL of earlier versions (files or folders, repeatable): the check counts their "
                        "rows as the café's")
    p.add_argument("--packs-from", default=config.RACES_JSON, help=argparse.SUPPRESS)
    p.add_argument("--config", default=catalog.CAFE_JSON, help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_sql)

    p = sub.add_parser("schemas", help="the café's DBC layouts against WoW/Source/DB/Rec")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="only compare (the default)")
    g.add_argument("--write", action="store_true", help="rewrite cflib/schemas.py's generated block")
    p.add_argument("--rec", help="the Rec folder (default: this checkout's)")
    p.set_defaults(func=cmd_schemas)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
