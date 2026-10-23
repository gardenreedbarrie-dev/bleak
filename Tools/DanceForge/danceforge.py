#!/usr/bin/env python3
"""DanceForge: the Bleakhold dances, from choreography to the files the client, the addon and the server read.

    python3 -I danceforge.py generate [--check]     DanceData.lua, BleakholdDance.h and the music README
    python3 -I danceforge.py pack [--out FILE]      the clip pack (default Interface/Bleakhold/Dances/Dances.bdc)
    python3 -I danceforge.py check                  catalogue, every dance, generated files, pack round trip
    python3 -I danceforge.py list                   the dances with their tempo and length

dances.json is the catalogue: id, key, name, slash command, category and the choreography (module:function in
dances/) of every dance. Ids go on the wire (DANCE <id>, then SMSG_PLAY_SPELL_VISUAL kit 910000 + id), saved emote
wheels hold dance:<key> and music files are named after the key, so the catalogue is append-only: never renumber,
rename or remove a dance. Standard library only; run it with -I.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.dont_write_bytecode = True  # keep the repository free of __pycache__
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from dflib import catalogue as C  # noqa: E402
from dflib import choreo  # noqa: E402
from dflib import pack as P  # noqa: E402

CATALOGUE = os.path.join(HERE, "dances.json")
DANCES_DIR = os.path.join(HERE, "dances")
DEFAULT_PACK = os.path.join(REPO, "Interface", "Bleakhold", "Dances", "Dances.bdc")
# The largest turn of a joint between two frames of a clip (degrees); faster than this reads as a jump.
MAX_STEP = 72.0


def _load():
    cat = C.load(CATALOGUE)
    return cat, C.build(cat, DANCES_DIR)


def cmd_generate(args):
    cat, built = _load()
    stale = []
    for path, text in C.outputs(REPO, cat, built).items():
        data = text.encode("utf-8")
        old = open(path, "rb").read() if os.path.exists(path) else None
        if old == data:
            continue
        stale.append(os.path.relpath(path, REPO))
        if not args.check:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
    if args.check:
        for s in stale:
            print("stale: %s (run danceforge.py generate)" % s)
        return 1 if stale else 0
    for s in stale:
        print("wrote %s" % s)
    return 0


def cmd_pack(args):
    cat, built = _load()
    data = C.write_pack(cat, built)
    out = args.out or DEFAULT_PACK
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "wb") as f:
        f.write(data)
    print("wrote %s: %d dances, %d bytes" % (out, len(cat["dances"]), len(data)))
    return 0


def cmd_check(args):
    try:
        cat, built = _load()
    except C.CatalogueError as e:
        print("catalogue: %s" % e)
        return 1
    rc = 0
    for d in cat["dances"]:
        dance = built[d["key"]]
        frames = dance.sample(cat["fps"])
        step = choreo.check_loop(frames)
        if step > MAX_STEP:
            print("%s: a joint turns %.0f degrees between two frames (limit %.0f)" % (d["key"], step, MAX_STEP))
            rc = 1
        if not 1.0 <= dance.seconds <= 60.0:
            print("%s: a loop must last 1 to 60 seconds" % d["key"])
            rc = 1
    data = C.write_pack(cat, built)
    clips = P.read(data)
    if [c["id"] for c in clips] != [d["id"] for d in cat["dances"]]:
        print("pack: the clips do not match the catalogue")
        rc = 1
    gen = argparse.Namespace(check=True)
    if cmd_generate(gen):
        rc = 1
    if rc == 0:
        print("%d dances, pack %d bytes: ok" % (len(cat["dances"]), len(data)))
    return rc


def cmd_list(args):
    cat, built = _load()
    for d in cat["dances"]:
        dance = built[d["key"]]
        print("%3d %-20s %-22s /%-16s %-8s %5g bpm %6.2f s" % (d["id"], d["key"], d["name"], d["command"],
                                                              d["category"], dance.bpm,
                                                              C.loop_ms(dance, cat["fps"]) / 1000.0))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--check", action="store_true")
    p = sub.add_parser("pack")
    p.add_argument("--out")
    sub.add_parser("check")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    return {"generate": cmd_generate, "pack": cmd_pack, "check": cmd_check, "list": cmd_list}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
