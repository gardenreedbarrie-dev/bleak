#!/usr/bin/env python3
r"""MarkForge: Bleakhold's glowing body marks and eye sprites, drawn from each character model's own UVs.

    markforge.py build   (--client DATA --patches DIR [--config F] [--locale L] [--combination LABEL]
                          | --package DIR [--package DIR ...])
                         --out STAGING [--races NightElf:Female,Orc,...] [--no-eyes] [--preview] [--check]
    markforge.py preview (source as build) --out DIR --look Race:Sex:Design:Colour [--skin N] [--eye Colour]
    markforge.py fixture --out DIR [--races Race:Sex,...] [--check]
    markforge.py validate STAGING
    markforge.py doctor

build reads the client's own models, eye sprites, CharSections and underwear (on the VPS: the launcher's client and
patches, as RaceForge's skins and find see them; in a dev session: a package checkout with --package) and writes, for
every race and sex of the twelve playable races, the 12 looks of designs/<RaceFile>.json in the colours of
palettes.json, the eye sprites, marks_manifest.json (what raceforge.py customize --marks reads) and report.json, to
STAGING only:

    STAGING/files/Character/BleakholdMarks/<RaceFile>/<Sex>/<Design>_<Colour>.blp  (+ _Glow.blp for glowing colours)
    STAGING/files/Character/BleakholdEyes/<RaceFile>/<Sex>/Eye_<Colour>.blp
    STAGING/marks_manifest.json, STAGING/report.json, STAGING/previews/ (with --preview)

The output is derived from game files: STAGING must lie outside the repository, and nothing it holds is ever
committed. --check makes everything again in memory and compares it byte for byte with STAGING (exit 1 on any
difference). Gates (exit 1, manifest gates.passed false): glow difference across wrap seams above 0.1, any ink
inside a keep-out zone (eyes, mouth, eyeball/glow-orb geometry) or the garment mask of any visible skin colour at the
512, 256 and 128 levels, a visible skin colour whose skin, pelvis or torso texture was not read (a --package build
reads on past it; a --client build stops), any file breaking the contract's file rules. The manifest names its
source ("game" or "folder"), the --races asked for (races_requested) and each race-sex's garment_missing;
raceforge.py customize --marks takes only a "game" manifest with garment_missing 0 everywhere and all 24
race-sexes. numpy is required (the VPS check tests for it).

fixture writes synthetic marks for the client team (no game data: a section test grid and designs drawn on a tube
body, plus deliberately broken files for the exe's guards) with a fixture manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True

import mflib  # noqa: E402
from mflib import MarkForgeError  # noqa: E402

FORMAT = "bleakhold-marks/1"
SEAM_LIMIT = 0.1
CATALOGUE = os.path.join(mflib.REPO, "Tools", "RaceForge", "customize", "catalogue.json")
PALETTES = os.path.join(HERE, "palettes.json")
RACE_ORDER = ["Human", "Orc", "Dwarf", "NightElf", "Scourge", "Tauren", "Gnome", "Troll", "BloodElf", "Draenei",
              "HighElf", "Eredar"]


# --- data ---------------------------------------------------------------------------------------------------------


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise MarkForgeError(f"{path}: {e}") from None


def load_data(designs_dir=None):
    from mflib import designs as D
    pal = load_json(PALETTES)
    races = {}
    for rf in RACE_ORDER:
        if rf not in pal.get("races", {}):
            raise MarkForgeError(f"{PALETTES}: no race {rf}")
        races[rf] = {"palette": pal["races"][rf], "designs": D.load_race(rf, designs_dir or D.DESIGN_DIR)}
    return pal, races


def catalogue_problems(pal, races, path=CATALOGUE) -> list[str]:
    """Keys, names, hex values, glow flags and the order of designs, colours and eyes must be the catalogue's."""
    if not os.path.isfile(path):
        return []
    cat = load_json(path)
    out = []
    for rf in RACE_ORDER:
        c = cat.get("races", {}).get(rf)
        if c is None:
            out.append(f"{rf}: not in the catalogue")
            continue
        mine_d = [(d["key"], d["name"]) for d in races[rf]["designs"]["designs"]]
        cat_d = [(d["key"], d["name"]) for d in c["designs"]]
        if mine_d != cat_d:
            out.append(f"{rf} designs {mine_d} != catalogue {cat_d}")
        p = races[rf]["palette"]
        mine_c = [(x["key"], x["name"], x["hex"].upper(), bool(x["glow"])) for x in p["colours"]]
        cat_c = [(x["key"], x["name"], x["hex"].upper(), bool(x["glow"])) for x in c["colours"]]
        if mine_c != cat_c:
            out.append(f"{rf} colours {mine_c} != catalogue {cat_c}")
        mine_e = [(x["key"], x["name"], x["hex"].upper()) for x in p["eyes"]]
        cat_e = [(x["key"], x["name"], x["hex"].upper()) for x in c["eyes"]]
        if mine_e != cat_e:
            out.append(f"{rf} eyes {mine_e} != catalogue {cat_e}")
    mine_dk = [(x["eye"], x["key"], x["name"], x["hex"].upper()) for x in pal["death_knight_eyes"]]
    cat_dk = [(x["eye"], x["key"], x["name"], x["hex"].upper()) for x in cat.get("death_knight_eyes", [])]
    if mine_dk != cat_dk:
        out.append(f"death knight eyes {mine_dk} != catalogue {cat_dk}")
    return out


def parse_races(spec: str | None):
    """'NightElf:Female,Orc' -> [(race_id, race_file, sex), ...] in the build order."""
    from mflib.archive import RACES
    by_file = {v[0]: k for k, v in RACES.items()}
    want = None
    if spec:
        want = set()
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            rf, _, sx = part.partition(":")
            if rf not in by_file:
                raise MarkForgeError(f"--races: {rf} is not one of {', '.join(RACE_ORDER)}")
            sexes = {"Male": [0], "Female": [1], "": [0, 1]}.get(sx)
            if sexes is None:
                raise MarkForgeError(f"--races: {part}: the sex is Male or Female")
            for s in sexes:
                want.add((rf, s))
    out = []
    for rf in RACE_ORDER:
        for s in (0, 1):
            if want is None or (rf, s) in want:
                out.append((by_file[rf], rf, s))
    return out


def mark_path(rf, sex_name, design_key, colour_key, glow=False):
    return f"Character\\BleakholdMarks\\{rf}\\{sex_name}\\{design_key}_{colour_key}{'_Glow' if glow else ''}.blp"


def eye_path(rf, sex_name, colour_key):
    return f"Character\\BleakholdEyes\\{rf}\\{sex_name}\\Eye_{colour_key}.blp"


def sha1(b):
    return hashlib.sha1(b).hexdigest()


def rounded(obj, digits=6):
    """A copy with every float rounded (metres to the micrometre): report.json must not record the last bits of
    numpy's arithmetic, which differ between numpy versions and CPUs, or --check would compare those."""
    if isinstance(obj, float):
        return round(obj, digits)
    if isinstance(obj, dict):
        return {k: rounded(v, digits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [rounded(v, digits) for v in obj]
    return obj


# --- one race and sex ---------------------------------------------------------------------------------------------


class Prepared:
    pass


def prepare(source, race, sex, rows, strict, model_obj=None, garment=None, log=print):
    """Model, atlas, keep-out zones, charts, garment mask and fade of one race and sex."""
    import numpy as np
    from mflib import archive as AR, atlas as A, coords as C, draw as W, model as M
    p = Prepared()
    p.race, p.sex = race, sex
    if model_obj is None:
        m2_name, skin_name = AR.model_paths(source, race, sex)
        m2 = source.read(m2_name)
        sk = source.read(skin_name)
        p.model = M.load(m2, sk, m2_name)
        p.model_name, p.model_sha1, p.skin_sha1 = m2_name, sha1(m2), sha1(sk)
    else:
        p.model = model_obj
        p.model_name, p.model_sha1, p.skin_sha1 = model_obj.name, model_obj.sha1, model_obj.sha1
    eye = p.model.eye_centres()
    if eye is None:
        raise MarkForgeError(f"{p.model_name}: no eye-glow geoset (1702/1703): the face cannot be placed")
    p.eye, p.eye_sep = eye, 2 * float(eye[1])
    p.atlas = A.rasterise(p.model)
    A.keepout_zones(p.atlas, eye, p.eye_sep, A.other_geometry_cover(p.model))
    p.charts = C.Charts(p.atlas, eye, p.eye_sep)
    if garment is not None:
        p.garment, p.garment_report = garment, [{"synthetic": True}]
    elif rows is not None:
        p.garment, p.garment_report = AR.garment_union(source, rows, race, sex)
        missing = [r for r in p.garment_report
                   if "skipped" in r or any(isinstance(r.get(k), str) for k in ("pelvis", "torso"))]
        if missing and strict:
            raise MarkForgeError(f"race {race} sex {sex}: {len(missing)} visible skin colour(s) have a skin or "
                                 f"underwear texture that cannot be read (first: {missing[0]}); the garment mask "
                                 "must cover every visible skin colour")
        p.garment_missing = len(missing)
    else:
        p.garment, p.garment_report = np.zeros((A.N, A.N), bool), []
    p.fade, p.blocked, p.dead = W.fade_field(p.atlas, p.charts, p.garment)
    return p


def make_looks(p, rf, sex_name, race_data, report_rs, files, gates):
    """The 12 looks of a race and sex: files (path -> bytes), manifest entries, report and gate figures."""
    import numpy as np
    from mflib import designs as D, draw as W
    entries = []
    colours = race_data["palette"]["colours"]
    blocked = p.blocked
    keep = p.atlas.keepout
    garment = p.garment
    for di, design in enumerate(race_data["designs"]["designs"]):
        core0, halo0 = D.paint_design(p.charts, design, sex_name)
        core, halo = W.design_fields(p.atlas, p.charts, core0, halo0, p.fade, p.dead)
        glowf = np.clip(core + 0.45 * halo, 0, 1)
        seam_glow = W.seam_report(p.atlas, glowf)
        seam_core = W.seam_report(p.atlas, np.clip(core, 0, 1))
        seam_cut = W.seam_report(p.atlas, glowf, ("cut",), head_cuts=False)
        seam_head = W.seam_report(p.atlas, glowf, ("cut",), head_cuts=True)
        worst = max(seam_glow["max"], seam_core["max"])
        gates["seam_max"] = max(gates["seam_max"], worst)
        drep = {"design": design["key"], "seam_wrap_glow": seam_glow, "seam_wrap_core": seam_core,
                "seam_cut_glow": {k: seam_cut[k] for k in ("samples", "with_ink", "max")},
                "seam_head_cut_glow": {k: seam_head[k] for k in ("samples", "with_ink", "max", "worst")}, "looks": []}
        if worst > SEAM_LIMIT:
            gates["failures"].append(f"{rf} {sex_name} {design['key']}: glow differs by {worst:.3f} across a wrap seam "
                                     f"(limit {SEAM_LIMIT})")
        # a cut seam the build fades (the neck, the chin, the temples, the limbs' cuts) fades the design out in 3D on
        # both sides: a design that still differs there ends in a hard line. Not gated: hand seams (gloves cover the
        # hand section) and the head's own cuts, which are left unfaded (reported as seam_head_cut_glow)
        gates["seam_cut_max"] = max(gates.get("seam_cut_max", 0.0), seam_cut["max"])
        if seam_cut["max"] > SEAM_LIMIT:
            gates["failures"].append(f"{rf} {sex_name} {design['key']}: glow differs by {seam_cut['max']:.3f} across "
                                     f"a cut seam (limit {SEAM_LIMIT}; at {seam_cut['worst']})")
        for ci, colour in enumerate(colours):
            look_no = 3 * di + ci + 1
            look = W.compose(core, halo, colour)
            W.check_minimum(look, f"{rf} {sex_name} {design['key']} {colour['key']}")
            ink_keep = W.ink_inside(look, keep)
            ink_garment = W.ink_inside(look, garment)
            ink_blocked = W.ink_inside(look, blocked)
            gates["keepout_ink"] += sum(ink_keep)
            gates["garment_ink"] += sum(ink_garment)
            gates["blocked_ink"] += sum(ink_blocked)
            if sum(ink_blocked):
                gates["failures"].append(f"{rf} {sex_name} {design['key']} {colour['key']}: ink inside keep-out or "
                                         f"garment texels (levels 0-2: {ink_blocked})")
            path = mark_path(rf, sex_name, design["key"], colour["key"])
            data = look.blp(False)
            files[path] = data
            gpath, gdata = None, None
            if colour.get("glow"):
                gpath = mark_path(rf, sex_name, design["key"], colour["key"], True)
                gdata = look.blp(True)
                files[gpath] = gdata
            entries.append({
                "look": look_no, "design": di + 1, "design_key": design["key"], "design_name": design["name"],
                "colour": ci + 1, "colour_key": colour["key"], "colour_name": colour["name"], "hex": colour["hex"],
                "glow": bool(colour.get("glow")), "texture": path, "sha1": sha1(data), "size": len(data),
                "glow_texture": gpath, "glow_sha1": sha1(gdata) if gdata else None,
                "barber_name": f"{design['name']}, {colour['name']}",
                "sections": W.sections_with_ink(look), "coverage_pct": W.coverage(look),
            })
            drep["looks"].append({"look": look_no, "colour": colour["key"], "ink_keepout": ink_keep,
                                  "ink_garment": ink_garment, "coverage_pct": W.coverage(look)})
        report_rs["designs"].append(drep)
    return entries


def make_eyes(source, p, rf, sex_name, pal, race_data, files, fixture_src=None):
    from mflib import eyes as E
    if 1703 not in p.model.eye_tris:
        return [], None
    src_name = p.model.eye_texture
    if fixture_src is not None:
        src = fixture_src
    else:
        if not src_name:
            raise MarkForgeError(f"{p.model_name}: geoset 1703 samples no file texture")
        src = source.read(src_name)
    out = []
    cols = [dict(c, eye=i + 1, dk_only=False) for i, c in enumerate(race_data["palette"]["eyes"])] + \
        [dict(c, dk_only=True) for c in pal["death_knight_eyes"]]
    for c in cols:
        data = E.sprite_blp(src, c["hex"], float(pal.get("eye_core", 0.55)))
        path = eye_path(rf, sex_name, c["key"])
        files[path] = data
        out.append({"eye": c["eye"], "key": c["key"], "name": c["name"], "hex": c["hex"], "dk_only": c["dk_only"],
                    "texture": path, "sha1": sha1(data), "size": len(data)})
    from mflib.archive import blp_info
    info = blp_info(src)
    return out, {"texture": src_name, "sha1": sha1(src), "slot": p.model.eye_texture_slot, "width": info["width"],
                 "height": info["height"], "encoding": info["encoding"], "preferred": info["preferred"]}


# --- output -------------------------------------------------------------------------------------------------------


def repo_root_of(path):
    p = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(p, ".git")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def check_out_dir(out):
    root = repo_root_of(out)
    if root is not None and os.path.abspath(root) == os.path.abspath(mflib.REPO):
        raise MarkForgeError(f"--out {out} is inside the repository ({root}): marks are made from game files and are "
                             "never committed; give a folder outside it")
    if root is not None:
        raise MarkForgeError(f"--out {out} is inside a git checkout ({root}); give a folder outside any repository")


def dumps(obj) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=False, ensure_ascii=False) + "\n").encode("utf-8")


def emit(out, files: dict, extra: dict, check: bool) -> int:
    """Write (or with check compare) STAGING/files/<path> and the extra top-level files. Returns problems found."""
    want = {}
    for name, data in files.items():
        want[os.path.join("files", *name.split("\\"))] = data
    for name, data in extra.items():
        want[name] = data
    if check:
        problems = []
        for rel, data in sorted(want.items()):
            full = os.path.join(out, rel)
            try:
                with open(full, "rb") as f:
                    have = f.read()
            except OSError:
                problems.append(f"missing: {rel}")
                continue
            if have != data:
                problems.append(f"differs: {rel}")
        files_dir = os.path.join(out, "files")
        if os.path.isdir(files_dir):
            for dirpath, _, names in os.walk(files_dir):
                for n in names:
                    rel = os.path.relpath(os.path.join(dirpath, n), out)
                    if rel not in want:
                        problems.append(f"extra: {rel}")
        for p in problems[:30]:
            print("CHECK " + p)
        print(f"check: {len(want)} files compared, {len(problems)} problem(s)")
        return len(problems)
    os.makedirs(out, exist_ok=True)
    files_dir = os.path.join(out, "files")
    # stale files of an earlier run are removed (a look that was renamed must not linger)
    if os.path.isdir(files_dir):
        for dirpath, _, names in os.walk(files_dir):
            for n in names:
                rel = os.path.relpath(os.path.join(dirpath, n), out)
                if rel not in want:
                    os.remove(os.path.join(dirpath, n))
    for rel, data in sorted(want.items()):
        full = os.path.join(out, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        tmp = full + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, full)
    return 0


# --- sources ------------------------------------------------------------------------------------------------------


class Overlay:
    """Several folder sources, later ones winning (a package checkout plus a dev folder)."""

    def __init__(self, roots):
        from mflib.archive import FolderSource
        self.sources = [FolderSource(r) for r in roots]
        self.kind = "folder"

    def _pick(self, name):
        for s in reversed(self.sources):
            if s.has(name):
                return s
        return None

    def has(self, name):
        return self._pick(name) is not None

    def read(self, name):
        s = self._pick(name)
        if s is None:
            raise MarkForgeError(f"{name}: in none of {', '.join(x.root for x in self.sources)}")
        return s.read(name)


def open_source(args):
    if getattr(args, "client", None):
        from mflib.archive import GameSource
        if not args.patches:
            raise MarkForgeError("--client needs --patches")
        return GameSource(args.client, args.patches, args.config, args.locale, args.combination)
    if getattr(args, "package", None):
        return Overlay(args.package)
    raise MarkForgeError("give the client (--client and --patches) or a package folder (--package)")


# --- commands -----------------------------------------------------------------------------------------------------


def cmd_build(args) -> int:
    from mflib import archive as AR
    mflib.need_numpy()
    if not args.check:
        check_out_dir(args.out)
    pal, races = load_data()
    probs = [] if args.no_catalogue else catalogue_problems(pal, races)
    if probs:
        raise MarkForgeError("palettes.json / designs differ from the appearance catalogue "
                             f"({CATALOGUE}): " + "; ".join(probs[:4]))
    source = open_source(args)
    strict = source.kind == "game"
    rows = AR.char_sections(source)
    targets = parse_races(args.races)
    files, manifest_rs, report_rs_all = {}, [], []
    gates = {"seam_max": 0.0, "seam_cut_max": 0.0, "keepout_ink": 0, "garment_ink": 0, "blocked_ink": 0,
             "failures": []}
    t0 = time.time()
    previews = []
    try:
        for race, rf, sex in targets:
            sex_name = AR.SEXES[sex]
            t = time.time()
            p = prepare(source, race, sex, rows, strict)
            gates["failures"] += [f"{rf} {sex_name}: garment: {m}" for m in AR.garment_problems(p.garment_report)]
            if not p.garment_report:
                gates["failures"].append(f"{rf} {sex_name}: garment: no visible skin colour in CharSections, so no "
                                         "underwear is in the garment mask")
            rep = {"race": race, "race_file": rf, "sex": sex, "model": p.model_name,
                   "landmarks": rounded(p.charts.landmarks),
                   "keepout": {k: int(v.sum()) for k, v in p.atlas.keepout_parts.items() if hasattr(v, "sum")},
                   "mouth_centre": p.atlas.keepout_parts.get("mouth_centre"),
                   "garment_pct": round(100 * float(p.garment.mean()), 2), "garment": p.garment_report,
                   "seams": {"wrap": sum(1 for s in p.atlas.seams if s.kind == "wrap"),
                             "cut": sum(1 for s in p.atlas.seams if s.kind == "cut")},
                   "designs": []}
            marks = make_looks(p, rf, sex_name, races[rf], rep, files, gates)
            eyes, eye_src = ([], None) if args.no_eyes else make_eyes(source, p, rf, sex_name, pal, races[rf], files)
            manifest_rs.append({"race": race, "race_file": rf, "sex": sex, "sex_name": sex_name,
                                "garment_missing": getattr(p, "garment_missing", 0),
                                "model": p.model_name, "model_sha1": p.model_sha1, "skin_sha1": p.skin_sha1,
                                "eye_geoset": 1703 in p.model.eye_tris, "eye_source": eye_src,
                                "marks": marks, "eyes": eyes})
            report_rs_all.append(rep)
            print(f"{rf} {sex_name}: 12 looks, {len(eyes)} eye sprite(s), garment {rep['garment_pct']}%, "
                  f"worst wrap seam {max(d['seam_wrap_glow']['max'] for d in rep['designs']):.3f} "
                  f"({time.time() - t:.1f}s)")
            if args.preview and not args.check:
                # only the race-sex: a Prepared holds about 55 MB (the float atlas fields), all 24 kept until the
                # previews would be 1.3 GB on a VPS whose MySQL and world server still run; write_previews makes
                # each one again, one at a time
                previews.append((race, rf, sex, sex_name, races[rf]))
            del p
    finally:
        if hasattr(source, "close"):
            source.close()
    # the contract's file rules, on the bytes about to be written: a file that breaks them fails the gate (and the
    # manifest says so) before anything reaches STAGING
    gates["failures"] += manifest_problems(manifest_rs, files.get)
    gates["passed"] = not gates["failures"]
    gates["seam_limit"] = SEAM_LIMIT
    gates["seam_max"] = round(gates["seam_max"], 4)
    gates["seam_cut_max"] = round(gates["seam_cut_max"], 4)
    manifest = {
        "format": FORMAT, "markforge_version": mflib.VERSION,
        "catalogue_version": load_json(CATALOGUE).get("version") if os.path.isfile(CATALOGUE) else None,
        "source": source.kind, "races_requested": args.races or "all", "looks_per_design": 3, "designs_per_race": 4,
        "gates": {k: gates[k] for k in ("passed", "seam_max", "seam_limit", "keepout_ink", "garment_ink")},
        "race_sexes": manifest_rs,
    }
    report = {"format": FORMAT + "-report", "gates": gates, "race_sexes": report_rs_all}
    extra = {"marks_manifest.json": dumps(manifest), "report.json": dumps(report)}
    rc = emit(args.out, files, extra, args.check)
    if not args.check:
        problems = validate_folder(args.out)  # the written copy, read back
        if problems:
            gates["failures"] += problems
            gates["passed"] = False
        print(f"wrote {len(files)} files to {args.out} ({time.time() - t0:.0f}s)")
        if previews:
            write_previews(args.out, previews, source_for_previews(args), rows)
    for f in gates["failures"][:20]:
        print("GATE " + f)
    print("RESULT " + ("ok" if gates["passed"] and not rc else "FAILED"))
    return 0 if gates["passed"] and not rc else 1


def source_for_previews(args):
    return open_source(args)


def preview_layers(source, rows, race, sex, colour=None):
    """Skin, face (variation 0) and underwear of one skin colour (default the first visible), RGBA 0..1."""
    import numpy as np
    from mflib import archive as AR
    rr = AR.rows_race(source, race)
    skins = AR.visible_skins(rows, rr, sex)
    if not skins:
        raise MarkForgeError(f"race {race} sex {sex}: no visible skin colour")
    pick = [s for s in skins if colour is None or s["colour"] == colour]
    if not pick:
        raise MarkForgeError(f"skin colour {colour} is not a visible one ({[s['colour'] for s in skins]})")
    s = pick[0]

    def rd(name):
        if not name:
            return None
        try:
            return AR.decode_blp(source.read(name)).astype(np.float64) / 255
        except MarkForgeError:
            return None

    face = None
    for r in rows:
        key = (r["raceID"], r["sexID"], r["baseSection"], r["variationIndex"], r["colorIndex"])
        if key == (rr, sex, 1, 0, s["colour"]):
            face = r
    layers = {"skin": rd(s["skin"]), "pelvis": rd(s["pelvis"]), "torso": rd(s["torso"]),
              "face_lower": rd(face["textures"][0]) if face else None,
              "face_upper": rd(face["textures"][1]) if face else None}
    if layers["skin"] is None:
        raise MarkForgeError(f"{s['skin']}: cannot be read for the preview")
    return layers, s["colour"]


def render_look_sheets(p, look, layers, title, eye_sprite=None, lines=()):
    import numpy as np
    from mflib import preview as PV
    mark = PV.look_rgba(look, False)
    albedo = PV.compose_albedo(layers["skin"], layers.get("face_lower"), layers.get("face_upper"),
                               layers.get("torso"), layers.get("pelvis"), mark)
    if look.glow_palette is not None:
        g = PV.look_rgba(look, True)
        emissive = g[..., :3] * g[..., 3:4]
    else:
        emissive = None
    spr = eye_sprite.astype(np.float64) / 255 if eye_sprite is not None else None
    views = [PV.render(p.model, albedo, emissive, v, n, eye_sprite=spr) for n in (False, True)
             for v in ("front", "back", "side")]
    heads = [PV.crop_head(views[0], p.model, None), PV.crop_head(views[3], p.model, None)]
    hh = max(h.shape[0] for h in heads)
    head_panel = np.full((hh, sum(h.shape[1] for h in heads) + 8, 3), 12, np.uint8)
    x = 0
    for h in heads:
        head_panel[:h.shape[0], x:x + h.shape[1]] = h
        x += h.shape[1] + 8
    model_sheet = PV.model_sheet(views + [head_panel] if head_panel.shape[0] == views[0].shape[0] else views,
                                 title, ["day front", "day back", "day side", "night front", "night back",
                                         "night side"])
    glow_img = emissive if emissive is not None else mark[..., :3] * mark[..., 3:4]
    tex_sheet = PV.atlas_sheet(albedo, glow_img, title, list(lines))
    return tex_sheet, model_sheet, head_panel


def write_previews(out, previews, source, rows):
    """The contact sheets of the race-sexes built, after the gated output is written: each race-sex prepared again
    (about 10 s) and let go before the next, so one Prepared is alive at a time."""
    from mflib import draw as W, preview as PV
    pdir = os.path.join(out, "previews")
    os.makedirs(pdir, exist_ok=True)
    for race, rf, sex, sex_name, race_data in previews:
        try:
            p = prepare(source, race, sex, rows, strict=False)
            layers, col = preview_layers(source, rows, race, sex)
        except MarkForgeError as e:
            print(f"preview {rf} {sex_name}: {e}")
            continue
        from mflib import designs as D
        for design in race_data["designs"]["designs"]:
            colour = race_data["palette"]["colours"][0]
            core0, halo0 = D.paint_design(p.charts, design, sex_name)
            core, halo = W.design_fields(p.atlas, p.charts, core0, halo0, p.fade, p.dead)
            look = W.compose(core, halo, colour)
            title = f"{rf} {sex_name} - {design['name']} - {colour['name']} {colour['hex']}"
            tex, mod, _ = render_look_sheets(p, look, layers, title, lines=[f"skin colour {col}"])
            base = os.path.join(pdir, f"{rf}_{sex_name}_{design['key']}")
            PV.write_png(base + "_sheet.png", tex)
            PV.write_png(base + "_model.png", mod)
        del p
    if hasattr(source, "close"):
        source.close()


def cmd_preview(args) -> int:
    import numpy as np
    from mflib import archive as AR, designs as D, draw as W, eyes as E, preview as PV
    mflib.need_numpy()
    check_out_dir(args.out)
    pal, races = load_data()
    try:
        rf, sex_name, dkey, ckey = args.look.split(":")
    except ValueError:
        raise MarkForgeError("--look Race:Sex:Design:Colour, for example "
                             "NightElf:Female:MoonwellSigils:EluneBlue") from None
    by_file = {v[0]: k for k, v in AR.RACES.items()}
    if rf not in by_file or sex_name not in ("Male", "Female"):
        raise MarkForgeError(f"--look: unknown race or sex in {args.look}")
    race, sex = by_file[rf], (1 if sex_name == "Female" else 0)
    design = next((d for d in races[rf]["designs"]["designs"] if d["key"] == dkey), None)
    colour = next((c for c in races[rf]["palette"]["colours"] if c["key"] == ckey), None)
    if design is None or colour is None:
        raise MarkForgeError(f"--look: {rf} has no design {dkey} or colour {ckey}")
    source = open_source(args)
    rows = AR.char_sections(source)
    p = prepare(source, race, sex, rows, strict=False)
    core0, halo0 = D.paint_design(p.charts, design, sex_name)
    core, halo = W.design_fields(p.atlas, p.charts, core0, halo0, p.fade, p.dead)
    look = W.compose(core, halo, colour)
    layers, skin_col = preview_layers(source, rows, race, sex, args.skin)
    spr, eye_name = None, None
    if args.eye:
        cols = races[rf]["palette"]["eyes"] + pal["death_knight_eyes"]
        ec = next((c for c in cols if c["key"] == args.eye), None)
        if ec is None:
            raise MarkForgeError(f"--eye: {rf} has no eye colour {args.eye}")
        src = source.read(p.model.eye_texture)
        spr = E.recolour(AR.decode_blp(src), ec["hex"], float(pal.get("eye_core", 0.55)))
        eye_name = ec["name"]
    glowf = np.clip(core + 0.45 * halo, 0, 1)
    seam = W.seam_report(p.atlas, glowf)
    title = f"{rf} {sex_name} - {design['name']} - {colour['name']} {colour['hex']}"
    if eye_name:
        title += f" - eyes {eye_name}"
    lines = [f"skin colour {skin_col}", f"wrap seam max {seam['max']:.3f} ({seam['with_ink']} inked samples)",
             f"ink in keep-out (levels 0-2) {W.ink_inside(look, p.atlas.keepout)}",
             f"ink in garment (levels 0-2) {W.ink_inside(look, p.garment)}",
             f"garment {100 * float(p.garment.mean()):.1f}% of the atlas", f"coverage {W.coverage(look)}%",
             f"sections {' '.join(W.sections_with_ink(look))}"]
    tex, mod, head = render_look_sheets(p, look, layers, title, spr, lines)
    os.makedirs(args.out, exist_ok=True)
    base = os.path.join(args.out, f"{rf}_{sex_name}_{dkey}_{ckey}" + (f"_eyes{args.eye}" if args.eye else ""))
    PV.write_png(base + "_sheet.png", tex)
    PV.write_png(base + "_model.png", mod)
    PV.write_png(base + "_head.png", head)
    for ln in lines:
        print(ln)
    print(f"wrote {base}_sheet.png, _model.png, _head.png")
    if hasattr(source, "close"):
        source.close()
    return 0


def cmd_fixture(args) -> int:
    import numpy as np
    from mflib import fixture as FX
    mflib.need_numpy()
    if not args.check:
        check_out_dir(args.out)
    files, manifest = FX.build(args.races or "NightElf:Female")
    rc = emit(args.out, files, {"marks_manifest.json": dumps(manifest)}, args.check)
    if not args.check:
        print(f"wrote {len(files)} fixture files to {args.out}")
    return 1 if rc else 0


def manifest_problems(race_sexes, source) -> list[str]:
    """The contract's file rules for every mark, _Glow and eye sprite a manifest lists, and its SHA-1s. source is
    a staging folder or a reader (client path -> bytes or None)."""
    from mflib import draw as W
    problems = []
    for rs in race_sexes:
        for m in rs.get("marks", []):
            problems += W.validate_mark(source, m)
        for e in rs.get("eyes", []):
            problems += W.validate_eye(source, e, rs.get("eye_source"))
    return problems


def validate_folder(out) -> list[str]:
    """The contract's file rules for every file of a staging folder, and the manifest against the files."""
    man_path = os.path.join(out, "marks_manifest.json")
    if not os.path.isfile(man_path):
        return [f"{man_path}: missing"]
    return manifest_problems(load_json(man_path).get("race_sexes", []), out)


def cmd_validate(args) -> int:
    problems = validate_folder(args.staging)
    for p in problems[:50]:
        print("PROBLEM " + p)
    print(f"validate: {len(problems)} problem(s)")
    return 1 if problems else 0


def cmd_doctor(args) -> int:
    ok = True
    try:
        import numpy
        print(f"numpy {numpy.__version__}: ok")
    except ImportError:
        print("numpy: MISSING (apt install python3-numpy)")
        ok = False
    for rel in ("Tools/ModelForge/mflib/m2check.py", "Tools/BlpConvert/blpconvert.py",
                "Tools/RaceForge/rflib/skins.py"):
        p = os.path.join(mflib.REPO, rel)
        print(f"{rel}: {'ok' if os.path.isfile(p) else 'MISSING'}")
        ok &= os.path.isfile(p)
    try:
        pal, races = load_data()
        probs = catalogue_problems(pal, races)
        print(f"designs and palettes: ok ({len(races)} races); catalogue: {'ok' if not probs else probs[0]}")
        ok &= not probs
    except MarkForgeError as e:
        print(f"designs/palettes: {e}")
        ok = False
    print("RESULT " + ("ok" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bleakhold glowing marks and eye sprites from the client's own models.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def source_args(p):
        p.add_argument("--client", help="the client's Data folder (the launcher's base)")
        p.add_argument("--patches", help="the launcher's patches folder (over --client)")
        p.add_argument("--config", help="RaceForge config (the launcher's optional packs)")
        p.add_argument("--locale")
        p.add_argument("--combination", help="read one pack combination only (default: all must agree)")
        p.add_argument("--package", action="append", help="a folder of client paths (dev); repeat, later wins")

    b = sub.add_parser("build")
    source_args(b)
    b.add_argument("--out", required=True)
    b.add_argument("--races", help="Race[:Sex],... (default: all twelve races, both sexes)")
    b.add_argument("--no-eyes", action="store_true")
    b.add_argument("--preview", action="store_true",
                   help="also write previews to OUT/previews (game art: scratch only)")
    b.add_argument("--check", action="store_true", help="compare with OUT byte for byte instead of writing")
    b.add_argument("--no-catalogue", action="store_true", help="skip the catalogue comparison (tests)")
    pv = sub.add_parser("preview")
    source_args(pv)
    pv.add_argument("--out", required=True)
    pv.add_argument("--look", required=True)
    pv.add_argument("--skin", type=int)
    pv.add_argument("--eye")
    fx = sub.add_parser("fixture")
    fx.add_argument("--out", required=True)
    fx.add_argument("--races", help="Race:Sex,... to write tube-body looks for (default NightElf:Female)")
    fx.add_argument("--check", action="store_true")
    v = sub.add_parser("validate")
    v.add_argument("staging")
    sub.add_parser("doctor")
    args = ap.parse_args(argv)
    try:
        return {"build": cmd_build, "preview": cmd_preview, "fixture": cmd_fixture, "validate": cmd_validate,
                "doctor": cmd_doctor}[args.cmd](args)
    except MarkForgeError as e:
        print(f"markforge: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
