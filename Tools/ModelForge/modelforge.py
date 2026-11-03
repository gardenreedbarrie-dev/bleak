#!/usr/bin/env python3
"""ModelForge: original procedural M2 props for the Bleakhold café (CAFE.SPEC.md section 5). Standard library only;
run with python3 -I.

    modelforge.py build --all --out DIR [--preview] [--no-particles] [--no-bake] [--tex-scale F] [--only A,B]
    modelforge.py check FILE.m2 [--parts FILE.parts.json] [--client PATH]   JSON summary, exit 1 on any invariant
    modelforge.py render FILE.m2 --root DIR --out PNG [--mode orbit|overlay|game] [--yaw D] [--distance YD]
    modelforge.py icons --out DIR [--models DIR]     the 14 64x64 spell icons (section 5.7)
    modelforge.py manifest --out DIR                 DIR/manifest.json from the files built in DIR
    modelforge.py preview --scene sw|org --out DIR [--scene-only]   section 5.6 modes 2-5 for the models in DIR
    modelforge.py testpatch --out DIR [--only A,B] [--from DIR] [--icons]   DIR/patch-4.MPQ for the in-game look
    modelforge.py models                             the registered models, the broken modules, what is missing

Models are discovered: every mflib/props/*.py that defines NAME and build (mflib/props/__init__.py). `build
--quick` (with --preview) renders only the hero shot, two orbits, the 8 yd game view and the silhouette.

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
        broken = props.broken_for(names)
    else:
        names = list(props.REGISTRY)
        broken = dict(props.BROKEN)
    if broken:
        for mod, tb in sorted(broken.items()):
            print("mflib/props/%s.py does not load:\n%s" % (mod, tb))
        raise SystemExit("broken model module(s): %s" % ", ".join(sorted(broken)))
    bad = [n for n in names if n not in props.REGISTRY]
    if bad:
        built = ", ".join(props.REGISTRY)
        planned = ", ".join(n for n, *_r in props.CATALOGUE if n not in props.REGISTRY)
        raise SystemExit("not buildable yet: %s (registered: %s; not written yet: %s; a model is a file "
                         "mflib/props/<snake_name>.py that defines NAME and build)" % (", ".join(bad), built,
                                                                                         planned or "none"))
    return names


def cmd_models(args):
    for name, mod in props.REGISTRY.items():
        cat = SZ.catalogue().get(name)
        print("%-16s %-24s %s" % (name, mod.__name__.split(".")[-1] + ".py",
                                  "display %d, budget %d" % (cat["display"], cat["budget"]) if cat else "test model"))
    for mod in sorted(props.BROKEN):
        print("BROKEN           %-24s %s" % (mod + ".py", props.BROKEN[mod].strip().splitlines()[-1]))
    missing = [n for n, *_r in props.CATALOGUE if n not in props.REGISTRY]
    if missing:
        print("not written yet: %s" % ", ".join("%s (%s.py)" % (n, props.module_name(n)) for n in missing))
    return 1 if props.BROKEN else 0


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
            nob = os.path.join(out, "nobake", name) if args.preview and not args.quick else None
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
            previews(out, built, args.jobs, None, args.previews, args.quick)
    finally:
        B.shutdown()
    print("done in %.1fs" % (time.time() - t0))
    return 0


def previews(out, built, jobs=None, scene=None, pdir=None, quick=False):
    """Per-model PNGs and contact sheets, then the scene (scene None: "org" when every built café model is an
    Orgrimmar one, else "sw"). quick: the short view set and no scene."""
    pdir = os.path.abspath(pdir) if pdir else os.path.join(out, "previews")
    os.makedirs(pdir, exist_ok=True)
    index = []
    parsed = {}
    for res in built:
        name = res.defn.name
        nob = None if quick else next(iter(res.nobake.values()), None)
        base_z = SZ.KINDS.get(res.defn.kind, SZ.KINDS["machine"])["base_z"]
        labels = P.model_previews(name, res.m2, os.path.join(out, "files"), pdir, nob, jobs, base_z=base_z,
                                  quick=quick)
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
        P.contact_sheet(rest, sheet, 4, (400, 300), "%s  -  ModelForge preview" % name,
                        hero=hero[0] if hero else None)
        index.append((sheet, "%s contact sheet" % name))
        print("  %s" % sheet)
    if scene is None:
        cafe = [n for n in parsed if n != "Cube"]
        scene = "org" if any(n.endswith("Org") for n in cafe) and not any(n.endswith("SW") for n in cafe) else "sw"
    if not quick:
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
    """Section 5.6 mode 4: the whole café (scene_<city>.png) and the bar close up (scene_<city>_bar.png) in the
    city's day light. Returns the (path, label) of the whole-café view; both are printed."""
    pdir = pdir or os.path.join(out, "previews")
    cat = {n: v["size"] for n, v in SZ.catalogue().items()}
    tx = RD.TextureSet(os.path.join(out, "files"))
    light = RD.PRESETS["sw_day" if scene == "sw" else "org_day"]
    models = {k: v for k, v in parsed.items() if k != "Cube"}
    first = None
    for view, size in (("", (1600, 1000)), ("bar", (1280, 800))):
        frame, source = P.scene_view(models, tx, cat, SZ.CAFE_JSON, size, light, scene, view)
        path = os.path.join(pdir, "scene_%s%s.png" % (scene, "_" + view if view else ""))
        P._save(frame, path)
        print("  scene %s%s (%s layout): %s" % (scene, " " + view if view else "", source, path))
        first = first or (path, "scene %s (%s)" % (scene, source))
    return first


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


def _built_m2(src, name, jobs):
    """The parsed model `name` from the build in `src`, built there first (full size) when it is missing."""
    m2 = B.disk_path(src, B.client_dir(name) + "\\BH_Cafe_" + name + ".m2")
    if not os.path.exists(m2):
        print("%s: not built in %s, building it" % (name, src))
        res = B.build_prop(props.REGISTRY[name].build({}), src, 1.0, True, True, jobs, True, print)
        if res.check[1]:
            raise SystemExit("%s fails m2check" % name)
        m2 = res.m2
    return P.load(m2)


def cmd_icons(args):
    """The section 5.7 icons: DIR/files/Interface/Icons/BH_Cafe_<Name>.blp, PNG previews and a sheet in
    DIR/icons (or --previews), and the manifest's "icons" list."""
    import blpconvert  # noqa: E402  Tools/BlpConvert (read-only)
    from mflib import icons as IC
    out = os.path.abspath(args.out)
    src = os.path.abspath(args.models) if args.models else out
    only = [n.strip() for n in args.only.split(",")] if args.only else IC.icon_names()
    bad = [n for n in only if n not in IC.icon_names()]
    if bad:
        raise SystemExit("unknown icon(s): %s (icons: %s)" % (", ".join(bad), ", ".join(IC.icon_names())))
    rows = [r for r in IC.ICONS if r[1] in only]
    need = sorted({r[2]["model"] for r in rows if "model" in r[2]})
    if need:
        _names(argparse.Namespace(only=",".join(need)))   # raises on a broken or missing model module
    try:
        parsed = {name: _built_m2(src, name, args.jobs) for name in need}
    finally:
        B.shutdown()
    tx = RD.TextureSet(os.path.join(src, "files"))
    pdir = os.path.abspath(args.previews) if args.previews else os.path.join(out, "icons")
    os.makedirs(pdir, exist_ok=True)
    icons, files, cells = [], [], []
    for icon_id, name, _spec in rows:
        t = time.time()
        img, _bbox = IC.render_icon(name, parsed, tx)
        cpath = IC.client_path(name)
        dpath = IC.write_icon(img, B.disk_path(out, cpath))
        png = os.path.join(pdir, "BH_Cafe_%s.png" % name)
        blpconvert.write_png(png, blpconvert.decode_blp(dpath, 0))   # what ships: the DXT1 level 0
        icons.append({"id": icon_id, "path": cpath})
        files.append((cpath, dpath))
        cells.append((icon_id, name, png))
        print("  %d %-8s %s  %.1fs" % (icon_id, name, dpath, time.time() - t))
    sheet = IC.sheet(cells, os.path.join(pdir, "icons-sheet.png"))
    print("  sheet: %s" % sheet)
    man = os.path.join(out, "manifest.json")
    if os.path.exists(man):
        with open(man) as f:
            doc = json.load(f)
        keep = [i for i in doc.get("icons", []) if i["id"] not in {e["id"] for e in icons}]
        doc["icons"] = sorted(keep + icons, key=lambda e: e["id"])
        doc.setdefault("files", {}).update({c: B._sha(d) for c, d in files})
        with open(man, "w") as f:
            json.dump(doc, f, indent=2, sort_keys=True)
            f.write("\n")
    else:
        man = B.write_manifest(out, [], files, icons)
    print("manifest: %s" % man)
    return 0


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
    if args.scene_only:
        pdir = os.path.abspath(args.previews) if args.previews else os.path.join(out, "previews")
        os.makedirs(pdir, exist_ok=True)
        scene_preview(out, {r.defn.name: P.load(r.m2) for r in built}, args.scene, pdir)
        return 0
    previews(out, built, args.jobs, args.scene, args.previews, args.quick)
    return 0


def _built_files(src, name):
    """The client and disk paths of a model already built in `src` (m2, skin and the textures it names), after
    checking it again with m2check."""
    m2c = B.client_dir(name) + "\\BH_Cafe_" + name + ".m2"
    m2d = B.disk_path(src, m2c)
    if not os.path.exists(m2d):
        raise SystemExit("%s is not built in %s (run build first, or drop --from)" % (name, src))
    ppath = os.path.join(src, "parts", name + ".parts.json")
    pm = json.load(open(ppath)) if os.path.exists(ppath) else None
    m, fnd, summ = C.check_files(m2d, pm, m2c)
    if not summ["ok"]:
        raise SystemExit("%s fails m2check: %s" % (name, fnd.items[0]["msg"] if fnd else "see check"))
    skin_c = m2c[:-3] + "00.skin"
    out = [(m2c, m2d), (skin_c, B.disk_path(src, skin_c))]
    out += [(t["path"], B.disk_path(src, t["path"])) for t in m["textures"]]
    for c, d in out:
        if not os.path.exists(d):
            raise SystemExit("%s: %s is missing in %s" % (name, c, src))
    return out


def cmd_testpatch(args):
    """DIR/patch-4.MPQ for the owner's in-game look (section 5.9): any set of models (--only; default every
    registered model, the lettered cube included), built at full size into DIR/stage, or taken from an existing
    build with --from; --icons adds the section 5.7 icons. Models and textures only, no DBC rows."""
    import mpqpack  # noqa: E402  Tools/MpqPack (read-only)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    stage = os.path.abspath(args.src) if args.src else os.path.join(out, "stage")
    os.makedirs(stage, exist_ok=True)
    names = _names(args)
    files = []
    try:
        for name in names:
            if args.src:
                files += _built_files(stage, name)
                continue
            res = B.build_prop(props.REGISTRY[name].build({}), stage, 1.0, True, True, args.jobs, True, print)
            if res.check[1]:
                raise SystemExit("%s fails m2check" % name)
            files += res.files
    finally:
        B.shutdown()
    if args.icons:
        from mflib import icons as IC
        if not all(os.path.exists(B.disk_path(stage, IC.client_path(n))) for n in IC.icon_names()):
            cmd_icons(argparse.Namespace(out=stage, models=None, only=None, previews=None, jobs=args.jobs))
        files += [(IC.client_path(n), B.disk_path(stage, IC.client_path(n))) for n in IC.icon_names()]
    marker = os.path.join(out, "cafeforge.txt")
    with open(marker, "w") as f:
        f.write("test\n")
    items = sorted({c: d for c, d in files}.items())
    items.append(("Bleakhold\\Cafe\\cafeforge.txt", marker))
    path = os.path.join(out, "patch-4.MPQ")
    st = mpqpack.write_archive_streaming(path, items)
    print("%s: %d models (%s)%s, %d files, %d bytes. Copy it into ONE Windows client's Data\\ folder by hand "
          "(never the VPS patches folder) and remove it before the M6 install." % (
              path, len(names), ", ".join(names), " and %d icons" % len(IC.ICONS) if args.icons else "",
              st.file_count, st.archive_size))
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
    b.add_argument("--quick", action="store_true", help="with --preview: hero, two orbits, 8 yd, silhouette")
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
    i.add_argument("--models", help="the build to render the model icons from (default DIR; missing models are "
                                    "built there)")
    i.add_argument("--only", help="comma-separated icon names (default all 14)")
    i.add_argument("--previews", help="where the PNG previews and the sheet go (default DIR/icons)")
    i.add_argument("--jobs", type=int, default=None)
    mf = sub.add_parser("manifest")
    mf.add_argument("--out", required=True)
    pv = sub.add_parser("preview")
    pv.add_argument("--scene", choices=["sw", "org"], default="sw")
    pv.add_argument("--out", required=True)
    pv.add_argument("--only")
    pv.add_argument("--jobs", type=int, default=None)
    pv.add_argument("--previews", help="where the preview PNGs go (default DIR/previews)")
    pv.add_argument("--quick", action="store_true")
    pv.add_argument("--scene-only", action="store_true", help="only the scene renders, not every model's views")
    tp = sub.add_parser("testpatch")
    tp.add_argument("--only", help="comma-separated model names (default every registered model)")
    tp.add_argument("--out", required=True)
    tp.add_argument("--from", dest="src", help="package the models already built in this DIR (no rebuild)")
    tp.add_argument("--icons", action="store_true", help="add the section 5.7 icons")
    tp.add_argument("--jobs", type=int, default=None)
    sub.add_parser("models")
    args = ap.parse_args(argv)
    return {"build": cmd_build, "check": cmd_check, "render": cmd_render, "icons": cmd_icons,
            "manifest": cmd_manifest, "preview": cmd_preview, "testpatch": cmd_testpatch,
            "models": cmd_models}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
