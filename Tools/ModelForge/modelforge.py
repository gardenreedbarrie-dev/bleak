#!/usr/bin/env python3
"""ModelForge: original procedural M2 props for the Bleakhold café (CAFE.SPEC.md section 5). Standard library only;
run with python3 -I.

    modelforge.py build --all --out DIR [--preview] [--no-particles] [--no-bake] [--tex-scale F] [--only A,B]
    modelforge.py check FILE.m2 [--parts FILE.parts.json] [--client PATH]   JSON summary, exit 1 on any invariant
    modelforge.py render FILE.m2 --root DIR --out PNG [--mode orbit|overlay|game] [--yaw D] [--distance YD]
    modelforge.py icons --out DIR                    the 64x64 spell icons (section 5.7; M5)
    modelforge.py manifest --out DIR                 DIR/manifest.json from the files built in DIR
    modelforge.py preview --scene sw|org --out DIR   section 5.6 modes 2-5 for the models built in DIR
    modelforge.py testpatch --only Cube,EspressoSW --out DIR   DIR/patch-4.MPQ for the M2 art smoke test

Output tree: DIR/files/World/Bleakhold/Cafe/<Name>/BH_Cafe_<Name>.m2 (+ 00.skin, _Atlas.blp),
DIR/files/World/Bleakhold/Cafe/Shared/*.blp, DIR/previews/*.png (+ index.html), DIR/parts/*.parts.json,
DIR/manifest.json. Everything is deterministic: the same sources give byte-identical files.
"""

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from mflib import build as B  # noqa: E402
from mflib import m2check as C  # noqa: E402
from mflib import preview as P  # noqa: E402
from mflib import props  # noqa: E402
from mflib import render as RD  # noqa: E402
from mflib import sizes as SZ  # noqa: E402

DEFAULT_MODELS = ["Cube", "EspressoSW"]


def _names(args):
    if getattr(args, "only", None):
        names = [n.strip() for n in args.only.split(",") if n.strip()]
    else:
        names = list(props.REGISTRY)
    bad = [n for n in names if n not in props.REGISTRY]
    if bad:
        built = ", ".join(props.REGISTRY)
        planned = ", ".join(n for n, *_r in props.CATALOGUE if n not in props.REGISTRY)
        raise SystemExit("not buildable yet: %s (M1 builds %s; M5 adds %s)" % (", ".join(bad), built, planned))
    return names


def cmd_build(args):
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    entries = []
    files = []
    t0 = time.time()
    built = []
    try:
        for name in _names(args):
            mod = props.REGISTRY[name]
            print("%s:" % name)
            t = time.time()
            nob = os.path.join(out, "nobake", name) if args.preview else None
            res = B.build_prop(mod.build({}), out, args.tex_scale, not args.no_bake, not args.no_particles,
                               args.jobs, not args.no_cache, print, nob)
            m, fnd, summ = res.check
            if fnd:
                for e in fnd.items:
                    print("  ERROR %s: %s" % (e["code"], e["msg"]))
                raise SystemExit("%s fails m2check" % name)
            c = summ["counts"]
            print("  %d triangles (budget %d), %d sections, %d textures, %d particles, %d collision triangles,"
                  " %.1fs" % (c["triangles"], res.defn.budget, c["sections"], c["textures"], c["particles"],
                              c["collisionTriangles"], time.time() - t))
            print("  modelFrame %s" % json.dumps(res.manifest["modelFrame"]))
            entries.append(res.manifest)
            files += res.files
            built.append(res)
        names = C.check_unique_names([(r.m2, r.check[0].get("name")) for r in built])
        if names:
            raise SystemExit("model names: " + "; ".join(names))
        man = B.write_manifest(out, entries, files)
        print("manifest: %s" % man)
        if args.preview:
            previews(out, built, args.jobs, "sw", args.previews)
    finally:
        B.shutdown()
    print("done in %.1fs" % (time.time() - t0))
    return 0


def previews(out, built, jobs=None, scene="sw", pdir=None):
    pdir = os.path.abspath(pdir) if pdir else os.path.join(out, "previews")
    os.makedirs(pdir, exist_ok=True)
    index = []
    parsed = {}
    for res in built:
        name = res.defn.name
        nob = next(iter(res.nobake.values()), None)
        labels = P.model_previews(name, res.m2, os.path.join(out, "files"), pdir, nob, jobs)
        parsed[name] = P.load(res.m2)
        if nob:
            # the baked twin of the bake-off view, at the same yaw
            on = os.path.join(pdir, "%s_bake_on.png" % name)
            P._save(P.orbit_view(parsed[name], RD.TextureSet(os.path.join(out, "files")), 30), on)
            labels.append((on, "bake ON (yaw 30)"))
        index += labels
        sheet = os.path.join(pdir, "%s-sheet.png" % name)
        order = sorted(labels, key=lambda pl: _sheet_rank(pl[1]))
        hero = [pl for pl in order if pl[1].startswith("hero")]
        rest = [pl for pl in order if not pl[1].startswith("hero") and os.path.exists(pl[0])]
        P.contact_sheet(rest, sheet, 4, (400, 300), "%s  -  ModelForge preview (M1 draft)" % name,
                        hero=hero[0] if hero else None)
        index.append((sheet, "%s contact sheet" % name))
        print("  %s" % sheet)
    sc = scene_preview(out, parsed, scene, pdir)
    index.append(sc)
    P.write_index(pdir, index)
    return index


def _sheet_rank(label):
    order = ["game view 4", "game view 8", "game view 15", "orbit yaw 30", "orbit yaw 120", "orbit yaw 210",
             "orbit yaw 300", "lighting sw_day", "lighting sw_night", "lighting org_day", "bake ON", "bake OFF",
             "collision", "silhouette", "texel density"]
    for k, o in enumerate(order):
        if label.startswith(o):
            return k
    return len(order)


def scene_preview(out, parsed, scene="sw", pdir=None):
    pdir = pdir or os.path.join(out, "previews")
    cat = {n: v["size"] for n, v in SZ.catalogue().items()}
    tx = RD.TextureSet(os.path.join(out, "files"))
    light = RD.PRESETS["sw_day" if scene == "sw" else "org_day"]
    frame, source = P.scene_view({k: v for k, v in parsed.items() if k != "Cube"}, tx, cat, SZ.CAFE_JSON,
                                 lighting=light)
    path = os.path.join(pdir, "scene_%s.png" % scene)
    P._save(frame, path)
    print("  scene (%s layout): %s" % (source, path))
    return (path, "scene %s (%s)" % (scene, source))


def cmd_check(args):
    pm = None
    if args.parts:
        with open(args.parts) as f:
            pm = json.load(f)
    m, fnd, summ = C.check_files(args.file, pm, args.client)
    print(C.dumps(summ))
    return 0 if summ["ok"] else 1


def cmd_render(args):
    m = P.load(args.file)
    tx = RD.TextureSet(args.root)
    if args.mode == "game":
        frame = P.game_view(m, tx, args.distance, RD.PRESETS[args.light])
    else:
        frame = P.orbit_view(m, tx, args.yaw, args.pitch, args.size, overlay=args.mode == "overlay",
                             lighting=RD.PRESETS[args.light])
    P._save(frame, args.out)
    print(args.out)
    return 0


def cmd_icons(args):
    print("icons: the 64x64 SpellIcon art (section 5.7) is M5 work (section 7.4); nothing was written to %s"
          % args.out)
    return 2


def cmd_manifest(args):
    out = os.path.abspath(args.out)
    entries = []
    files = []
    for name in DEFAULT_MODELS + [n for n in props.REGISTRY if n not in DEFAULT_MODELS]:
        m2c = B.client_dir(name) + "\\BH_Cafe_" + name + ".m2"
        m2d = B.disk_path(out, m2c)
        if not os.path.exists(m2d):
            continue
        defn = props.REGISTRY[name].build({})
        ppath = os.path.join(out, "parts", name + ".parts.json")
        pm = json.load(open(ppath)) if os.path.exists(ppath) else None
        m, fnd, summ = C.check_files(m2d, pm, m2c)
        res = B.Built()
        res.defn = defn
        res.textures = [(t["path"], B.disk_path(out, t["path"])) for t in m["textures"]]
        skin_c = m2c[:-3] + "00.skin"
        entries.append(B.manifest_entry(defn, res, summ, m2c, skin_c))
        files += [(m2c, m2d), (skin_c, B.disk_path(out, skin_c))] + res.textures
    if not entries:
        raise SystemExit("no built models under %s (run build first)" % out)
    print(B.write_manifest(out, entries, files))
    return 0


def cmd_preview(args):
    out = os.path.abspath(args.out)
    built = []
    for name in _names(args):
        m2c = B.client_dir(name) + "\\BH_Cafe_" + name + ".m2"
        m2d = B.disk_path(out, m2c)
        if not os.path.exists(m2d):
            print("skipping %s: not built in %s" % (name, out))
            continue
        res = B.Built()
        res.defn = props.REGISTRY[name].build({})
        res.m2 = m2d
        built.append(res)
    if not built:
        raise SystemExit("nothing built in %s (run build first)" % out)
    previews(out, built, args.jobs, args.scene, args.previews)
    return 0


def cmd_testpatch(args):
    import mpqpack  # noqa: E402  Tools/MpqPack (read-only)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    stage = os.path.join(out, "stage")
    files = []
    try:
        for name in _names(args):
            res = B.build_prop(props.REGISTRY[name].build({}), stage, 1.0, True, True, args.jobs, True, print)
            if res.check[1]:
                raise SystemExit("%s fails m2check" % name)
            files += res.files
    finally:
        B.shutdown()
    marker = os.path.join(stage, "cafeforge.txt")
    with open(marker, "w") as f:
        f.write("test\n")
    items = sorted({c: d for c, d in files}.items())
    items.append(("Bleakhold\\Cafe\\cafeforge.txt", marker))
    path = os.path.join(out, "patch-4.MPQ")
    st = mpqpack.write_archive_streaming(path, items)
    print("%s: %d files, %d bytes. Copy it into ONE Windows client's Data\\ folder by hand (never the VPS patches "
          "folder) and remove it before the M6 install." % (path, st.file_count, st.archive_size))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="modelforge.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--all", action="store_true", help="every model ModelForge can build (the default)")
    b.add_argument("--only", help="comma-separated model names")
    b.add_argument("--out", required=True)
    b.add_argument("--preview", action="store_true")
    b.add_argument("--previews", help="where the preview PNGs go (default DIR/previews)")
    b.add_argument("--no-particles", action="store_true")
    b.add_argument("--no-bake", action="store_true")
    b.add_argument("--no-cache", action="store_true")
    b.add_argument("--tex-scale", type=float, default=1.0)
    b.add_argument("--jobs", type=int, default=None)
    c = sub.add_parser("check")
    c.add_argument("file")
    c.add_argument("--parts")
    c.add_argument("--client", help="the model's client path, for the MapForge cross-check")
    r = sub.add_parser("render")
    r.add_argument("file")
    r.add_argument("--root", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--mode", choices=["orbit", "overlay", "game"], default="orbit")
    r.add_argument("--yaw", type=float, default=30.0)
    r.add_argument("--pitch", type=float, default=20.0)
    r.add_argument("--size", type=int, default=512)
    r.add_argument("--distance", type=float, default=8.0)
    r.add_argument("--light", choices=sorted(RD.PRESETS), default="neutral")
    i = sub.add_parser("icons")
    i.add_argument("--out", required=True)
    mf = sub.add_parser("manifest")
    mf.add_argument("--out", required=True)
    pv = sub.add_parser("preview")
    pv.add_argument("--scene", choices=["sw", "org"], default="sw")
    pv.add_argument("--out", required=True)
    pv.add_argument("--only")
    pv.add_argument("--jobs", type=int, default=None)
    pv.add_argument("--previews", help="where the preview PNGs go (default DIR/previews)")
    tp = sub.add_parser("testpatch")
    tp.add_argument("--only", default="Cube,EspressoSW")
    tp.add_argument("--out", required=True)
    tp.add_argument("--jobs", type=int, default=None)
    args = ap.parse_args(argv)
    return {"build": cmd_build, "check": cmd_check, "render": cmd_render, "icons": cmd_icons,
            "manifest": cmd_manifest, "preview": cmd_preview, "testpatch": cmd_testpatch}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
