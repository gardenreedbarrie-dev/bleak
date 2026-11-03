"""cafeforge.py build (section 6.5): the art, the plan, the forged archives, the server SQL and the checks, into one
output folder that RaceForge's tool-agnostic `install` puts into the realm's patch folder.

    OUT/art/                      ModelForge's output (cafeforge.py art; kept between builds, its cache with it)
    OUT/client/<archive>          every archive that changes, at its place in the patch folder (client/enUS/...)
    OUT/server/sql/bleakhold_cafe_dbc.sql    the server's DBC rows (cflib/sqlout.py)
    OUT/server/cafe_check.sql     the read-only check of the world database (deploy/cafe/check-cafe-db.sh)
    OUT/install.json              for raceforge.py install: each archive with the file it replaces as the build read
                                  it; checks_passed only once every check passed
    OUT/plan.json                 where the build read from (for cafeforge.py validate)
    OUT/report.txt                everything below, with every check

Nothing is written before every refusal has been looked for: the plan without the art (a taken id, a mask clash, a
patch-4.MPQ that is not the café's, café paths in another archive, an unreadable archive, ...), an earlier output
without --force, the art (every café model and icon, unchanged since ModelForge built it), the plan with the art's
bounds, and the free space. Then --force clears the earlier output (never OUT/art, never the backups of an install
in OUT/old-patches), install.json is written as unfinished, the archives are written, the SQL, and the checks run on
the archives as the players will read them (cflib/validate.py). Only when every check passed is install.json marked
as passed and, with --server-sql-out, the rev put into the server's generated-SQL folder (sqlout.write_rev: a new
rev_<nanoseconds>.sql, or nothing when the newest café rev there holds the same text).
"""

import json
import os
import shutil
import sys
import tempfile
import time

from . import archive as artmod
from . import catalog
from . import config as cfgmod
from . import plan as planmod
from . import sqlout
from . import validate as valmod

from rflib import install, skins, update  # noqa: E402  (Tools/RaceForge)

TOOL_NAME = "cafeforge.py build"
OUT_ENTRIES = cfgmod.OUT_ENTRIES
RACEFORGE = os.path.join(cfgmod.TOOLS_DIR, "RaceForge", "raceforge.py")
PUBLISH = "bash /root/bleakserv/deploy/launcher/publish.sh"
CHECK_DB = "bash /root/bleakserv/deploy/cafe/check-cafe-db.sh"


class BuildError(Exception):
    pass


def inside(path, folder):
    real = os.path.realpath(folder)
    try:
        return os.path.commonpath([os.path.realpath(path), real]) == real
    except ValueError:  # another drive
        return False


def refuse_problems(what, problems):
    raise BuildError("%s: %d problem(s), nothing was written:\n%s" % (what, len(problems),
                                                                      "\n".join("  - " + p for p in problems)))


def earlier_output(out_dir):
    return [e for e in OUT_ENTRIES if os.path.exists(os.path.join(out_dir, e))]


def where_text(plan):
    """The archives that hold the café's client copies once installed (the rev's header): stable from one build to
    the next, so a build that changes nothing writes the same SQL."""
    names = sorted({s.target(plan.own) for sources in plan.sources.values() for s in sources}, key=str.lower)
    return "the client copies are in %s" % " and ".join(names) if names else "no client copies"


def report_text(cfg, args, plan, art, written, own, result, sql_path, check_path, rev, rev_error, out_dir):
    lines = ["CafeForge build report", "======================", ""]
    lines.append("Realm patches:     %s" % plan_folder(args))
    lines.append("Server DBCs:       %s" % os.path.abspath(args.dbc))
    lines.append("Art:               %s (%s)" % (art.folder, art.summary(cfg)))
    lines.append("Pack combinations: %s" % ", ".join(plan.configurations))
    lines.append("Café archive:      %s (%s)" % (plan.own, plan.own_state))
    lines += ["", "Spell rows the wrapper resolves to", "----------------------------------"]
    for idx in sorted(plan.indices.values(), key=lambda i: (i.column, isinstance(i.wanted, str), i.wanted)):
        lines.append("  " + idx.text())
    lines += ["", "Where each table goes", "---------------------"]
    lines += ["  " + line for line in plan.table_lines(done=True)]
    for name in sorted(plan.drops):
        lines.append("  %s: the café's earlier copy in %s goes (a realm patch's copy decides now)" % (name, plan.own))
    for w in plan.warnings:
        lines.append("  warning: " + w)
    for note in art.notes:
        lines.append("  art: " + note)
    lines += ["", "Archives", "--------"]
    lines += [w.text() for w in written]
    if own.up_to_date:
        lines.append("%s: already up to date (nothing written)" % plan.own)
    if not written:
        lines.append("no archive changes: every copy is up to date")
    lines += ["", "Checks", "------"]
    lines += valmod.summary_lines(result)
    lines += ["", "Server", "------"]
    lines.append("Server SQL: %s" % sql_path)
    lines.append("Check SQL:  %s" % check_path)
    if args.server_sql_out:
        if rev is not None:
            lines.append("Server SQL rev: %s (%s)" % (rev[0], "written" if rev[1] else
                                                      "already there with the same SQL: nothing written"))
        elif rev_error:
            lines.append("Server SQL rev: not written (%s)" % rev_error)
        else:
            lines.append("Server SQL rev: not written to %s (a check failed)" % args.server_sql_out)
    lines += ["", "Next steps", "----------"] + next_steps(args, out_dir, written, result)
    return "\n".join(lines) + "\n"


def next_steps(args, out_dir, written, result):
    if result.failed:
        return ["Some checks failed: do not install this output. Fix what the checks say, then build again."]
    steps = ["1. The world database check (read-only): %s %s; echo \"exit code: $?\"" % (
        CHECK_DB, os.path.join(out_dir, "server", sqlout.CHECK_FILE))]
    if written:
        steps.append("2. The archives into the patch folder: python3 -I %s install --from %s --patches %s" % (
            RACEFORGE, out_dir, plan_folder(args)))
        steps.append("3. Publish them: %s" % PUBLISH)
    else:
        steps.append("2. No archive to install: the patch folder already holds the café's copies.")
    steps.append("Then the server: cd /root/bleakserv && bash deploy/update-bleakhold-ui.sh --check")
    return steps


def plan_folder(args):
    return os.path.abspath(args.patches)


def run(args, say=print):
    """cafeforge.py build. Returns the exit code."""
    try:
        return _run(args, say)
    except (BuildError, artmod.ArtError) as ex:
        print("error: %s" % ex, file=sys.stderr)
        return 1


def _run(args, say):
    try:
        cfg = cfgmod.load(args.config, args.packs_from)
        doc = catalog.load(args.config)
    except (cfgmod.ConfigError, catalog.CatalogError) as ex:
        raise BuildError(str(ex)) from None
    out_dir = os.path.abspath(args.out)
    for flag, folder in (("--patches", args.patches), ("--dbc", args.dbc)):
        if inside(out_dir, folder):
            raise BuildError("--out %s is inside %s %s%s; give a folder elsewhere" % (
                out_dir, flag, folder, ": the launcher would publish it" if flag == "--patches" else ""))
    if not os.path.isdir(args.dbc):
        raise BuildError("--dbc %s is not a folder (the server's data/dbc)" % args.dbc)
    patches = update.patch_tools()
    try:
        patchset = patches.PatchSet.scan(args.patches, cfg.optional_packs)
    except patches.PatchError as ex:
        raise BuildError(str(ex)) from None
    try:
        return _build(args, cfg, doc, out_dir, patchset, say)
    finally:
        patchset.close()


def _build(args, cfg, doc, out_dir, patchset, say):
    # the archives as read, for install.json: install refuses a file that changed since
    read_at = {a.client_path.lower(): install.fingerprint(a.path) for a in patchset.archives}
    first = planmod.make_plan(cfg, patchset, args.dbc)
    if first.problems:
        refuse_problems("the plan (cafeforge.py doctor shows the same)", first.problems)
    entries = earlier_output(out_dir)
    if entries and not args.force:
        raise BuildError("%s already holds output (%s); use --force to replace it" % (out_dir, ", ".join(entries)))

    if args.art:
        art = artmod.load_art(args.art, cfg)
    else:
        art = artmod.make_art(out_dir, cfg, args.preview, args.only, args.tex_scale, args.jobs, say=say)
    if inside(art.folder, args.patches):
        raise BuildError("the art folder %s is inside --patches %s" % (art.folder, args.patches))
    say("art: %s (%s)" % (art.folder, art.summary(cfg)))
    if art.problems:
        refuse_problems("the art", art.problems)

    plan = planmod.make_plan(cfg, patchset, args.dbc, art.bounds)
    problems = plan.problems + artmod.rebuild_problems(plan, patchset)
    if problems:
        refuse_problems("the plan with the art's bounds", problems)
    # the marker texture is drawn outside OUT: a refusal below leaves an earlier output folder as it was
    work = tempfile.mkdtemp(prefix="cafeforge-own-")
    try:
        own = artmod.plan_own(plan, patchset, art, work)
        with open(own.files[cfgmod.MARKER_TEXTURE], "rb") as f:
            own.files[cfgmod.MARKER_TEXTURE] = f.read()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    need = artmod.space_needed(plan, patchset, own)
    free = skins.free_space(out_dir) + skins.entries_size(out_dir, OUT_ENTRIES)
    if need > free:
        archives = [t for t in plan.targets if t.lower() != plan.own.lower()] + ([] if own.up_to_date else [plan.own])
        raise BuildError("--out %s needs %s free for the archives (%s), has %s" % (
            out_dir, skins.gb(need), ", ".join(archives), skins.gb(free)))

    # only now: a refusal above leaves an earlier output folder as it was (the art apart)
    update.clean_out_dir(out_dir, True, OUT_ENTRIES)
    # until the run is complete, install refuses this folder (a full disk or Ctrl-C leaves it unfinished)
    install.write_manifest(out_dir, TOOL_NAME, patchset.folder, None, [], False)
    write_plan_file(out_dir, args, cfg, patchset, art, plan)
    for line in plan.table_lines(done=True):
        say(line)
    try:
        written = artmod.write_archives(plan, patchset, own, out_dir, say=lambda text: None)
    except artmod.ArtError as ex:
        raise BuildError(str(ex)) from None
    for w in written:
        say(w.text())
    if own.up_to_date:
        say("%s: already up to date (nothing written)" % plan.own)

    sql_dir = os.path.join(out_dir, "server", "sql")
    os.makedirs(sql_dir, exist_ok=True)
    sql_text = sqlout.dbc_sql(plan.rows, cfg.ids, where_text(plan))
    sql_path = os.path.join(sql_dir, sqlout.SQL_FILE)
    with open(sql_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(sql_text)
    check_text = sqlout.check_sql(doc, cfg, sqlout.earlier_values(args.earlier_sql, doc["ids"]))
    check_path = os.path.join(out_dir, "server", sqlout.CHECK_FILE)
    with open(check_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(check_text)

    view, opened = valmod.view_of(patchset, {w.client_path: w.path for w in written})
    work = os.path.join(out_dir, "staging")
    os.makedirs(work, exist_ok=True)
    try:
        result, _ = valmod.check(cfg, view, args.dbc, art, sql_text, check_text, written, patchset, work)
    finally:
        valmod._close(opened)
        shutil.rmtree(work, ignore_errors=True)

    rev, rev_error = None, ""
    # A rev reaches the server with the next update-bleakhold-ui.sh: only when every check passed.
    if args.server_sql_out and not result.failed:
        try:
            rev = sqlout.write_rev(args.server_sql_out, sql_text)
        except (update.UpdateError, OSError) as ex:
            rev_error = str(ex)

    entries = []
    for w in written:
        archive = patchset.find(w.name) if not w.new else None
        rel = os.path.relpath(w.path, os.path.join(out_dir, "client")).replace(os.sep, "/")
        if archive is not None:
            size, mtime_ns = read_at[archive.client_path.lower()]
            entries.append(install.entry(rel, archive.client_path, "patches", archive.path, size, mtime_ns, w.path))
        else:
            entries.append(install.entry(rel, w.client_path, "new", "", None, None, w.path))
    install.write_manifest(out_dir, TOOL_NAME, patchset.folder, None, entries, not result.failed and not rev_error)
    text = report_text(cfg, args, plan, art, written, own, result, sql_path, check_path, rev, rev_error, out_dir)
    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    for check in result.failed:
        say("FAILED: %s%s" % (check.name, " -- %s" % check.detail if check.detail else ""))
    say("%d checks, %d failed (report: %s)" % (len(result.checks), len(result.failed),
                                               os.path.join(out_dir, "report.txt")))
    if args.server_sql_out:
        if rev is not None:
            say("Server SQL rev: %s (%s)" % (rev[0], "written" if rev[1] else
                                             "already there with the same SQL: nothing written"))
        else:
            say("Server SQL rev: not written (%s)" % (rev_error or "a check failed"))
    else:
        say("Server SQL: %s" % sql_path)
    if result.failed or rev_error:
        if rev_error:
            print("error: %s" % rev_error, file=sys.stderr)
        print("Some checks failed: do not install this output.", file=sys.stderr)
        return 1
    for line in next_steps(args, out_dir, written, result):
        say(line)
    return 0


def write_plan_file(out_dir, args, cfg, patchset, art, plan):
    data = {"_readme": "For cafeforge.py validate: where this build read the realm's patches, the server's DBCs and "
                       "the art from.",
            "tool": TOOL_NAME, "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "patches": os.path.realpath(patchset.folder), "dbc": os.path.realpath(args.dbc),
            "art": os.path.realpath(art.folder), "packs": cfg.optional_packs, "own": plan.own,
            "configurations": plan.configurations, "tables": plan.table_lines(done=True)}
    install.write_json(os.path.join(out_dir, valmod.PLAN_FILE), data)

