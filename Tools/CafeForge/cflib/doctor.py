"""cafeforge.py doctor: what a café build would do on this realm, read-only (section 6.5).

Per table and pack combination it shows the winning archive, its highest id and what happens to the café's ids
there (free, already the café's, taken), the CharTitles masks in use, the cast-time, duration and range rows the
spells resolve to, the SpellVisual rows they need, the archives a build rebuilds with their sizes against the free
space, and the rows the server's SQL already has in the café's id blocks. Nothing is written. The exit code is 1 when
anything would stop a build (every problem is listed), else 0.
"""

import json
import os
import sys

from . import config as cfgmod
from . import dbcrows
from . import plan as planmod

import mpqpack  # noqa: E402  (Tools/MpqPack, on sys.path through cflib.config)
from rflib import skins, update  # noqa: E402  (Tools/RaceForge)

# The server tables whose rows the café owns, with the column that holds the id and the cafe.json id block.
SQL_IDS = (
    ("spell_dbc", "ID", "spells"),
    ("spell_custom_attr", "spell_id", "spells"),
    ("gameobjectdisplayinfo_dbc", "ID", "displays"),
    ("chartitles_dbc", "ID", "titles"),
    ("gameobject_template", "entry", "gameobjects"),
    ("gameobject_template_addon", "entry", "gameobjects"),
    ("creature_template", "entry", "creatures"),
    ("creature_template_addon", "entry", "creatures"),
    ("creature_template_model", "CreatureID", "creatures"),
    ("item_template", "entry", "items"),
    ("npc_text", "ID", "npcText"),
)
# A file whose head names CafeForge is the café's own (04_bleakhold_cafe_templates.sql, the generated DBC rev).
OWN_SQL_MARK = "CafeForge"
GB = 1024 ** 3
MB = 1024 ** 2


def scan_server_sql(roots, ids):
    """{table: {id: file}} of the rows the .sql files under roots insert into the café's id blocks, without the
    café's own files. MapForge's dbc/sqlgen.py reads the INSERT statements (its scan_server_sql does the same for
    the map's tables)."""
    from dbc import sqlgen  # noqa: E402  (Tools/MapForge, on sys.path through cflib.config)

    wanted = {table: (column.lower(), ids[block]) for table, column, block in SQL_IDS}
    found = {}
    for root in roots:
        for folder, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for filename in sorted(files):
                if not filename.lower().endswith(".sql"):
                    continue
                path = os.path.join(folder, filename)
                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except OSError:
                    continue
                if OWN_SQL_MARK in text[:800] or not any(t in text for t in wanted):
                    continue
                for match in sqlgen._INSERT.finditer(text):
                    table = match.group(1).lower()
                    if table not in wanted:
                        continue
                    column, (lo, hi) = wanted[table]
                    names = [n.strip().strip("`").lower() for n in (match.group(2) or "").strip("()").split(",")]
                    at = names.index(column) if column in names else 0
                    for values in sqlgen._tuples(text, match.end()):
                        try:
                            row_id = int(values[at].strip("'\""))
                        except (ValueError, IndexError):
                            continue
                        if lo <= row_id <= hi:
                            found.setdefault(table, {}).setdefault(row_id, os.path.relpath(path, root))
    return found


def read_bounds(path):
    """{display: (min, max)} of a ModelForge manifest.json (section 5.9)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for model in data.get("models") or []:
        bounds = model.get("bounds") or {}
        out[int(model["display"])] = (tuple(float(v) for v in bounds["min"]), tuple(float(v) for v in bounds["max"]))
    return out


def unpacked_size(archive):
    """Bytes of an archive's files unpacked (what a rebuild stages), as RaceForge skins.space_needed counts them."""
    reader = archive.reader
    return sum(b.file_size for b in reader.blocks if b.flags & mpqpack.FILE_EXISTS) if reader else 0


def size_text(n):
    return "%.1f GB" % (n / GB) if n >= GB else "%.1f MB" % (n / MB)


def rebuilds(plan, patchset):
    """(name, archive or None) of every archive a build writes: the winners that get rows, and the café's own."""
    names = []
    for sources in plan.sources.values():
        for s in sources:
            if s.result.changed and not s.result.problems:
                target = s.target(plan.own)
                if target not in names:
                    names.append(target)
    if plan.own not in names:
        names.append(plan.own)  # the models, icons and markers always go there
    order = {a.name: i for i, a in enumerate(patchset.archives)}
    names.sort(key=lambda n: order.get(n, -1))
    return [(n, patchset.find(n)) for n in names]


def report(cfg, plan, patchset, args, sql_found, out):
    say = out.append
    say("CafeForge doctor (read-only): %s" % patchset.folder)
    say("Archives (lowest first): " + (", ".join(a.name + (" (pack %s)" % a.pack if a.pack else "")
                                                for a in patchset.archives) or "none"))
    say("Pack combinations: %s" % ", ".join(plan.configurations))
    say("Café archive: %s (%s)" % (plan.own, plan.own_state))
    say("")
    say("Reference tables (every pack on): " + ", ".join("%s.dbc from %s" % (n, w) for n, w in
                                                         plan.reference_where.items()))
    say("Spell rows the wrapper resolves to:")
    for idx in sorted(plan.indices.values(), key=lambda i: (i.column, isinstance(i.wanted, str), i.wanted)):
        say("  " + idx.text())
    visuals = sorted({s.data.get("visual") or 0 for s in cfg.spells} - {0})
    if "SpellVisual" in plan.references:
        have = plan.references["SpellVisual"].ids()
        say("SpellVisual rows: " + ", ".join("%d %s" % (v, "present" if v in have else "MISSING") for v in visuals))
    say("")
    say("Tables:")
    for name, sources in plan.sources.items():
        ids = plan.rows.ids(name)
        for s in sources:
            say("  " + plan.line(s))
            say("      max id %d; café ids %d-%d" % (s.max_id, ids[0], ids[-1]))
            for note in s.result.notes:
                if not note.endswith((": free", ": already there", ": the café's", ": added")):
                    say("      " + note)
            if name == "CharTitles":
                table = dbcrows.table_from(s.original, name, s.where())
                masks = {table.get_signed(r, "maskID") for r in table.rows}
                say("      masks in use: highest %s; %s" % (max(masks) if masks else "none", ", ".join(
                    "%d %s" % (t.mask, "in use" if t.mask in masks else "free") for t in cfg.titles)))
    for name in plan.drops:
        say("  %s: the café's earlier copy in %s loads over a realm archive's; a build takes it out"
            % (name, plan.own))
    say("")
    total = skins.SPACE_MARGIN
    staging = 0
    lines = []
    for name, archive in rebuilds(plan, patchset):
        # each archive is written whole, with its new copies of the tables; the largest one's files are staged
        total += sum(len(d) for d in plan.targets.get(name, {}).values())
        if archive is None:
            lines.append("%s (new)" % name)
            continue
        size = os.path.getsize(archive.path)
        total += size
        staging = max(staging, unpacked_size(archive))
        lines.append("%s (%s)" % (name, size_text(size)))
    say("Archives a build writes: " + ", ".join(lines))
    where = args.out or os.getcwd()
    free = skins.free_space(where)
    # an earlier build's output there: `build --force` removes it before it writes, so its space counts (forge.py)
    earlier = skins.entries_size(args.out, cfgmod.OUT_ENTRIES) if args.out else 0
    replaced = " and %s of an earlier build there, which a build replaces" % size_text(earlier) if earlier else ""
    need = total + staging
    say("Free space at %s: %s%s; a build needs about %s plus the café's art" % (where, size_text(free), replaced,
                                                                               size_text(need)))
    if free + earlier < need:
        plan.problems.append("%s has %s free%s, a build needs about %s" % (where, size_text(free), replaced,
                                                                            size_text(need)))
    say("")
    if args.server_sql:
        say("Server SQL (%s):" % ", ".join(args.server_sql))
        if not sql_found:
            say("  no other rows in the café's id blocks")
        for table, rows in sorted(sql_found.items()):
            for row_id, path in sorted(rows.items()):
                plan.problems.append("%s %d is in the server's SQL (%s): the café's ids must be free" % (table, row_id,
                                                                                                       path))
        if sql_found:
            say("  %d row(s) in the café's id blocks (below)" % sum(len(r) for r in sql_found.values()))
        say("")
    for w in plan.warnings:
        say("warning: " + w)
    if plan.problems:
        say("%d problem(s): a build would stop" % len(plan.problems))
        for p in plan.problems:
            say("  - " + p)
    else:
        say("No problems: cafeforge.py build can run.")


def run(args):
    """cafeforge.py doctor. Returns the exit code."""
    try:
        cfg = cfgmod.load(args.config, args.packs_from)
    except cfgmod.ConfigError as ex:
        print("error: %s" % ex, file=sys.stderr)
        return 1
    patches = update.patch_tools()
    try:
        patchset = patches.PatchSet.scan(args.patches, cfg.optional_packs)
    except patches.PatchError as ex:
        print("error: %s" % ex, file=sys.stderr)
        return 1
    try:
        bounds = read_bounds(args.manifest) if args.manifest else None
        plan = planmod.make_plan(cfg, patchset, args.dbc, bounds)
        sql_found = scan_server_sql(args.server_sql, cfg.ids) if args.server_sql else {}
        out = []
        report(cfg, plan, patchset, args, sql_found, out)
    except (OSError, ValueError, KeyError) as ex:
        print("error: %s" % ex, file=sys.stderr)
        return 1
    finally:
        patchset.close()
    print("\n".join(out))
    return 1 if plan.problems else 0

