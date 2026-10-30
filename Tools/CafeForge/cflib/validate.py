"""cafeforge.py validate (and the checks every build ends with, section 6.5): the written archives re-read, as the
players' clients will read them once they are installed.

The view is the realm's patch folder with each archive of OUT/client in the place it will take (a new patch-4.MPQ
added), in the client's archive order (Tools/MapForge/dbc/patches.py), for every combination of the launcher's packs.
On it:
- every written archive passes the client reader's checks (MpqPack's verify), reads back the files the build put
  in, and keeps every file of the archive it replaces (but the café files it was meant to drop);
- the plan made again on that view has nothing left to do: every combination's copy of every café table holds every
  café row field for field (the display rows' boxes are ModelForge's bounds), no id is taken, no copy must move, and
  patch-4.MPQ carries CafeForge's marker. That is cflib/plan.py itself, so a build and its check can never disagree;
- the café's archive holds every model, skin, texture and icon with the sha256 ModelForge built it with, the
  addon's marker texture (a BLP the client loads), and a marker file whose sha256 list is the archive's contents;
- in every combination, what each café spell points at is there: its icon, visual, cast-time, duration and range
  rows (RaceForge's forge.spell_reference_problems);
- the server SQL reads back as the rows it was made from, field for field (cflib/sqlout.py), and the check SQL is
  there.

Run on its own (`validate --out OUT`), it reads OUT/plan.json (where the build got its patch folder, server DBCs and
art from) and OUT/install.json. An archive that `raceforge.py install` already moved into the patch folder is checked
there; any other change of the patch folder since the build is a failure ("build again"). A failure also marks
install.json as not passed, so install refuses the folder.
"""

import json
import os
import shutil
import sys
import tempfile

from . import archive as artmod
from . import config as cfgmod
from . import marker, schemas, sqlout
from . import plan as planmod

import mpqpack  # noqa: E402  (Tools/MpqPack)
from rflib import install, update  # noqa: E402  (Tools/RaceForge)
from rflib.forge import spell_reference_problems  # noqa: E402
from rflib.validate import Validation  # noqa: E402

PLAN_FILE = cfgmod.PLAN_FILE
REFERENCE = ("Spell", "SpellIcon") + cfgmod.REFERENCE_TABLES


class ValidateError(Exception):
    pass


def _open(path, client_path, group, pack, opened):
    patches = update.patch_tools()
    archive = patches.Archive(path, client_path, group, pack)
    try:
        archive.reader = patches.PatchArchive(path)
        opened.append(archive.reader)
    except (mpqpack.MpqError, OSError, ValueError) as ex:
        archive.error = "cannot be opened (%s)" % ex
    return archive


def view_of(patchset, overlays):
    """(PatchSet, readers to close) of the patch folder with overlays {client path: file} in place."""
    patches = update.patch_tools()
    left = {k.lower(): (k, v) for k, v in overlays.items()}
    archives, opened = [], []
    for a in patchset.archives:
        item = left.pop(a.client_path.lower(), None)
        archives.append(a if item is None else _open(item[1], a.client_path, a.group, a.pack, opened))
    for client_path, path in left.values():
        archives.append(_open(path, client_path, 1, patches.pack_of(client_path, patchset.packs), opened))
    archives.sort(key=patches.Archive.rank)
    return patches.PatchSet(archives, dict(patchset.packs), patchset.folder), opened


def _close(readers):
    for reader in readers:
        try:
            reader.close()
        except Exception:  # noqa: BLE001
            pass


def files_text(n):
    return "1 file" if n == 1 else "%d files" % n


def check_written(result, written, before):
    """The archives as written: the reader's checks, the planned files read back, the replaced archive's files kept."""
    for w in written:
        with mpqpack.MpqArchive(w.path) as a:
            report = a.verify()
            result.expect(not report.problems, "%s: passes the client reader's checks" % w.name,
                          "; ".join(report.problems[:5]))
            bad = []
            for name in w.files:
                try:
                    same = a.read(name) == w.planned_bytes(name)
                except mpqpack.MpqError:
                    same = False
                if not same:
                    bad.append(name)
            result.expect(not bad, "%s: the %s the build put in read back as written" % (
                w.name, files_text(len(w.files))), ", ".join(bad[:5]))
            original = before.find(w.name) if before is not None and not w.new else None
            if original is not None and original.reader is not None:
                gone = {mpqpack.name_key(n) for n in w.dropped}
                old = {mpqpack.name_key(n) for n in original.reader.names()} - gone
                new = {mpqpack.name_key(n) for n in a.names()}
                result.expect(old <= new, "%s: every other file of the realm's archive is still there (%d before, %d "
                              "after%s)" % (w.name, len(old), len(new), ", %d café files dropped" % len(gone)
                                            if gone else ""), "%d missing" % len(old - new))


def check_own(result, cfg, view, art, work_dir):
    """The café's archive: the art with ModelForge's sha256, the marker texture and the marker file."""
    own = view.find(cfg.own)
    if own is None or own.reader is None:
        result.add("FAIL", "%s is in the patch folder (or the build's client folder)" % cfg.own,
                   own.error if own is not None else "it is in neither")
        return
    bad = []
    for name, sha in sorted(art.sha.items()):
        try:
            if marker.sha256_of(own.read(name)) != sha:
                bad.append(name)
        except Exception:  # noqa: BLE001 - PatchError: reported
            bad.append(name)
    result.expect(not bad, "%s: the %d models, skins, textures and icons are ModelForge's (sha256)"
                  % (own.name, len(art.sha)), ", ".join(bad[:5]))
    path = os.path.join(work_dir, "marker-check.blp")
    try:
        with open(path, "wb") as f:
            f.write(own.read(cfgmod.MARKER_TEXTURE))
        problems = marker.blp_problems(path)
    except Exception as ex:  # noqa: BLE001
        problems = [str(ex)]
    result.expect(not problems, "%s: the addon's marker %s loads in the client" % (own.name, cfgmod.MARKER_TEXTURE),
                  "; ".join(problems))
    try:
        text = own.read(cfgmod.MARKER_FILE).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        text = ""
    parsed = marker.parse_marker(text)
    if parsed is None:
        result.add("FAIL", "%s: %s is CafeForge's marker" % (own.name, cfgmod.MARKER_FILE),
                   "missing or not CafeForge's")
        return
    special = {mpqpack.name_key(n) for n in mpqpack.SPECIAL_FILES + (cfgmod.MARKER_FILE,)}
    contents = {mpqpack.name_key(n): n for n in own.reader.names() if mpqpack.name_key(n) not in special}
    listed = {mpqpack.name_key(n): sha for n, sha in parsed["files"].items()}
    differ = sorted(set(contents) ^ set(listed))
    for key, name in contents.items():
        if key in listed and marker.sha256_of(own.read(name)) != listed[key]:
            differ.append(key)
    result.expect(not differ, "%s: its marker lists the archive's %d files with their sha256" % (own.name,
                                                                                                 len(contents)),
                  ", ".join(k.decode("utf-8", "replace") if isinstance(k, bytes) else str(k) for k in differ[:5]))


def check_references(result, cfg, view, stock_dir, rows):
    """What every café spell points at, in every combination's copies."""
    for label, packs_on in view.configurations():
        tables = {}
        for name in REFERENCE:
            try:
                table, _ = update.read_table(name, view, stock_dir, packs_on)
            except Exception:  # noqa: BLE001 - reported by the plan
                table = None
            if table is not None:
                tables[name] = table
        spells = tables.get("Spell")
        if spells is None:
            result.add("FAIL", "%s: Spell.dbc can be read" % label)
            continue
        by_id = spells.by_id()
        problems = []
        for s in cfg.spells:
            row = by_id.get(s.id)
            if row is None:
                problems.append("spell %d is missing" % s.id)
                continue
            found, skipped = spell_reference_problems(rows.defs[s.id], row, tables)
            problems += found + ["not checked: %s" % k for k in skipped]
        result.expect(not problems, "%s: what the %d café spells point at is there (icon, visual, cast time, duration, "
                      "range)" % (label, len(cfg.spells)), "; ".join(problems[:5]))


def check(cfg, view, stock_dir, art, sql_text, check_text, written=(), before=None, work_dir=None):
    """(Validation, the plan made again on the view)."""
    result = Validation()
    work = work_dir or tempfile.mkdtemp(prefix="cafeforge-validate-")
    try:
        check_written(result, written, before)
        after = planmod.make_plan(cfg, view, stock_dir, art.bounds)
        result.expect(not after.problems, "the plan on the players' view: nothing in the way",
                      "; ".join(after.problems[:5]))
        for name in cfgmod.TABLES:
            sources = after.sources.get(name) or []
            result.expect(bool(sources), "%s: a copy for every player" % schemas.file_name(name))
            for s in sources:
                done = not s.result.changed and not s.result.ours and not s.result.problems
                result.expect(done, "%s: %s in %s holds the café's %d rows" % (
                    ", ".join(s.labels), schemas.file_name(name), s.where(), len(after.rows.ids(name))),
                    s.result.summary())
        result.expect(not after.targets and not after.drops, "nothing is left to write or to move",
                      ", ".join(sorted(after.targets)) or ", ".join(sorted(after.drops)))
        result.expect(after.own_state == "the café's", "%s carries CafeForge's marker" % cfg.own, after.own_state)
        check_own(result, cfg, view, art, work)
        if after.rows.defs:
            check_references(result, cfg, view, stock_dir, after.rows)
        if after.rows.defs and after.rows.bounds is not None:
            problems, checked = sqlout.sql_problems(sql_text or "", after.rows)
            result.expect(not problems, "server SQL: reads back as the client rows field for field (%s)"
                          % "; ".join(checked), "; ".join(problems[:5]))
        result.expect(bool(check_text) and "SELECT" in check_text, "server/%s: the read-only check of the world "
                      "database" % sqlout.CHECK_FILE)
    finally:
        if work_dir is None:
            shutil.rmtree(work, ignore_errors=True)
    return result, after


def summary_lines(result):
    lines = ["[%s] %s%s" % (c.status, c.name, " -- %s" % c.detail if c.detail and c.status != "PASS" else "")
             for c in result.checks]
    return lines + ["%d checks, %d failed" % (len(result.checks), len(result.failed))]


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def run(args):
    """cafeforge.py validate --out OUT. Returns the exit code."""
    out_dir = os.path.abspath(args.out)
    try:
        with open(os.path.join(out_dir, PLAN_FILE), encoding="utf-8") as f:
            recorded = json.load(f)
        manifest = install.load_manifest(out_dir)
        if manifest is None:
            raise ValidateError("%s has no %s" % (out_dir, install.INSTALL_FILE))
        cfg = cfgmod.load(args.config, None)
    except (OSError, ValueError) as ex:
        print("error: %s is not an output folder of cafeforge.py build (%s)" % (out_dir, ex), file=sys.stderr)
        return 1
    except (ValidateError, install.InstallError, cfgmod.ConfigError) as ex:
        print("error: %s" % ex, file=sys.stderr)
        return 1
    cfg.optional_packs = dict(recorded.get("packs") or {})
    art = artmod.load_art(recorded["art"], cfg)
    if art.problems:
        print("error: the art the build shipped is not there any more: %s" % "; ".join(art.problems[:3]),
              file=sys.stderr)
        return 1
    patches = update.patch_tools()
    try:
        patchset = patches.PatchSet.scan(recorded["patches"], cfg.optional_packs)
    except patches.PatchError as ex:
        print("error: %s" % ex, file=sys.stderr)
        return 1
    problems, overlays = [], {}
    for item in manifest["archives"]:
        src = os.path.join(out_dir, "client", *install.safe_rel(item["rel"]))
        dest = os.path.realpath(os.path.join(patchset.folder, *install.safe_rel(item["rel"])))
        if os.path.isfile(src):
            read = (item.get("size"), item.get("mtime_ns"))
            if item["origin"] == "patches" and (not os.path.isfile(dest) or install.fingerprint(dest) != read):
                problems.append("%s changed since the build read it: build again" % dest)
            elif item["origin"] == "new" and os.path.lexists(dest):
                problems.append("%s is there now, the build wrote it new: build again" % dest)
            overlays[item["client_path"]] = src
        elif not (os.path.isfile(dest) and install.fingerprint(dest) == (item.get("out_size"),
                                                                           item.get("out_mtime_ns"))):
            problems.append("%s is not in %s and %s is not the archive the build wrote" % (item["rel"], out_dir,
                                                                                          dest))
    view, opened = view_of(patchset, overlays)
    try:
        result, _ = check(cfg, view, recorded.get("dbc"), art,
                          read_text(os.path.join(out_dir, "server", "sql", sqlout.SQL_FILE)),
                          read_text(os.path.join(out_dir, "server", sqlout.CHECK_FILE)))
        for archive in opened:
            report = archive.verify()
            result.expect(not report.problems, "%s: passes the client reader's checks" % archive.path,
                          "; ".join(report.problems[:5]))
    finally:
        _close(opened)
        patchset.close()
    for p in problems:
        result.add("FAIL", p)
    print("\n".join(summary_lines(result)))
    if result.failed and manifest.get("checks_passed"):
        install.write_manifest(out_dir, manifest.get("tool", ""), manifest.get("patches", ""), manifest.get("client"),
                               manifest["archives"], False)
        print("install.json: marked as failed, so raceforge.py install refuses this folder until a build passes")
    return 1 if result.failed else 0
