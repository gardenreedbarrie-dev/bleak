"""The café's server SQL (section 6.6): the generated DBC rev, the read-only check of the world database, and `sql`.

The rev holds the server's copies of the café's client rows: spell_dbc (100900-100959), gameobjectdisplayinfo_dbc
(19300-19339) and chartitles_dbc (190-191), every column in client column order (AzerothCore's DBCDatabaseLoader
reads `SELECT *` over its fmt; the columns are those of bleakserv's data/sql/base/db_world). Each row is built once,
from the same SpellDef, title or display as the client's copies (cflib/dbcrows.py), so the server and every client
read the same row; `validate` reads the SQL back and compares it field for field (RaceForge's spells.parse_sql_rows
and compare_row). Each block is deleted before its rows go in, so the file can be applied again; it names no time,
so a build that changes nothing writes the same text and write_rev finds it already there. SpellIcon has no
server table (the server never reads it).

The check (OUT/server/cafe_check.sql, run by bleakserv's deploy/cafe/check-cafe-db.sh) only reads: every row it
prints sits in one of the café's id blocks and is not the café's own (another spell, display, template, item, text or
title, or another use of the café's titles), which the café's SQL would replace. Its names are the ones the module's
04_bleakhold_cafe_templates.sql writes (cflib/gen.py, from the same catalogue), and those of the café's own SQL of
earlier versions (--earlier-sql: the deployed module SQL and the earlier revs): a renamed spell, piece, NPC or item, an
edited text or a new model path finds the old row in the database, and that row is the café's, not someone else's.

`sql` writes the rev alone, for a dev realm before any client patch exists (milestone M4): the spells' cast-time,
duration and range rows come from --dbc (and --patches when given), the displays' boxes from ModelForge's manifest
when --art is given, else from cafe.json's sizes.
"""

import os
import re
import socket
import sys

from . import catalog
from . import config as cfgmod
from . import dbcrows, gen
from . import plan as planmod

from rflib import spells as spellmod  # noqa: E402  (Tools/RaceForge)
from rflib import update  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402

SQL_FILE = "bleakhold_cafe_dbc.sql"
CHECK_FILE = "cafe_check.sql"
# AzerothCore's locale order of the *_Lang_* columns (the client's 16 slots, then the flags column).
SQL_LOCALES = ("enUS", "enGB", "koKR", "frFR", "deDE", "enCN", "zhCN", "enTW", "zhTW", "esES", "esMX", "ruRU", "ptPT",
               "ptBR", "itIT", "Unk")
DISPLAY_COLUMNS = ((("ID", "i"), ("ModelName", "s")) + tuple(("Sound_%d" % i, "i") for i in range(1, 11))
                   + tuple(("GeoBox%s%s" % (m, a), "f") for m in ("Min", "Max") for a in "XYZ")
                   + (("ObjectEffectPackageID", "i"),))
TITLE_COLUMNS = ((("ID", "i"), ("Condition_ID", "i"))
                 + tuple(("Name_Lang_%s" % loc, "s") for loc in SQL_LOCALES) + (("Name_Lang_Mask", "u"),)
                 + tuple(("Name1_Lang_%s" % loc, "s") for loc in SQL_LOCALES) + (("Name1_Lang_Mask", "u"),)
                 + (("Mask_ID", "i"),))
# table -> (server table, its columns in client order, the cafe.json id block)
SERVER = {
    "Spell": ("spell_dbc", spellmod.SERVER_SPELL_COLUMNS, "spells"),
    "GameObjectDisplayInfo": ("gameobjectdisplayinfo_dbc", DISPLAY_COLUMNS, "displays"),
    "CharTitles": ("chartitles_dbc", TITLE_COLUMNS, "titles"),
}
WHAT = {"Spell": "On Shift, the step spells, the buffs and markers", "GameObjectDisplayInfo": "the new art's models",
        "CharTitles": "the titles"}


class SqlError(Exception):
    pass


def server_rows(rows, name):
    """(table, [row]) of the café's rows of a table, built into an empty copy of its layout."""
    from . import schemas  # noqa: PLC0415

    table = DbcTable.empty(schemas.get(name))
    return table, [rows.build(name, table, row_id) for row_id in rows.ids(name)]


def label(rows, name, row_id):
    return rows.label(name, row_id).split(" ", 2)[-1]


def dbc_sql(rows, ids, where, host=None):
    """The rev: rows is a dbcrows.Rows with bounds; ids cafe.json's id blocks; where: what the header says about the
    client copies ("the client copies are in Patch-R.MPQ and patch-4.MPQ")."""
    host = host or socket.gethostname()
    blocks = ", ".join("%s %d-%d" % (SERVER[n][0], ids[SERVER[n][2]][0], ids[SERVER[n][2]][1]) for n in SERVER)
    out = update.comment(
        "Bleakhold café (mod-bleakhold-ui, The Lion's Roast and The Grinding Tusk): the server's copies of the café's "
        "client DBC rows, the same rows as the client's Spell.dbc, GameObjectDisplayInfo.dbc and CharTitles.dbc. Made "
        "by CafeForge (Tools/CafeForge) on %s from cafe.json and the realm's own DBCs; %s. Every id was checked free "
        "first (cafeforge.py doctor and the build's plan). Id blocks: %s; each block is deleted before its rows go in, "
        "so the file can be applied again. Commit it to bleakserv's data/sql/updates/pending_db_world/ under the same "
        "name, unchanged." % (host, where, blocks))
    for name, (table_name, columns, block) in SERVER.items():
        table, made = server_rows(rows, name)
        lo, hi = ids[block]
        out += [""] + update.comment("%s: %s (%d rows)" % (table_name, WHAT[name], len(made)))
        out.append("DELETE FROM `%s` WHERE `ID` BETWEEN %d AND %d;" % (table_name, lo, hi))
        out.append(spellmod.insert_sql(table_name, columns, [spellmod.sql_values(table, r, columns) for r in made],
                                       [label(rows, name, r[0]) for r in made]))
    return "\n".join(out) + "\n"


def sql_problems(text, rows):
    """Every row of the rev read back against the row it was made from, field for field: (problems, checked)."""
    problems, checked = [], []
    for name, (table_name, columns, _) in SERVER.items():
        table, made = server_rows(rows, name)
        try:
            back = spellmod.parse_sql_rows(text, table_name)
        except spellmod.SpellError as ex:
            problems.append("%s: %s" % (table_name, ex))
            continue
        expected = {r[0]: r for r in made}
        if sorted(back) != sorted(expected):
            problems.append("%s holds rows %s, the café has %s" % (table_name, sorted(back), sorted(expected)))
        for row_id, row in sorted(expected.items()):
            if row_id in back:
                problems += ["%s %d: %s" % (table_name, row_id, d) for d in
                             spellmod.compare_row(table, row, back[row_id], columns)]
        checked.append("%s: %d rows (%d columns)" % (table_name, len(made), len(columns)))
    return problems, checked


# ------------------------------------------------------------------------------------------------ the check

def _texts(values):
    return ", ".join(gen.sql_str(v) for v in values)


def _between(column, block):
    return "`%s` BETWEEN %d AND %d" % (column, block[0], block[1])


# The tables of the check whose rows the café's earlier SQL wrote: (table, id column, the column the check compares).
EARLIER_COLUMNS = (("spell_dbc", "ID", "Name_Lang_enUS"), ("spell_custom_attr", "spell_id", "spell_id"),
                   ("gameobjectdisplayinfo_dbc", "ID", "ModelName"), ("gameobject_template", "entry", "name"),
                   ("creature_template", "entry", "name"), ("item_template", "entry", "name"),
                   ("npc_text", "ID", "text0_0"), ("chartitles_dbc", "ID", "Name_Lang_enUS"))


def _literal(raw):
    """A value of an INSERT as the database holds it: NULL, a number, or a text with gen.sql_str's escapes undone."""
    if raw.upper() == "NULL":
        return None
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        out, body, i = [], raw[1:-1], 0
        while i < len(body):
            if body[i] == "\\" and i + 1 < len(body):
                out.append(body[i + 1])
                i += 2
            elif body[i] == raw[0] and i + 1 < len(body) and body[i + 1] == raw[0]:
                out.append(raw[0])
                i += 2
            else:
                out.append(body[i])
                i += 1
        return "".join(out)
    try:
        return int(raw)
    except ValueError:
        return raw


def earlier_values(paths, ids):
    """{table: {value}} of the café's own SQL under paths (files or folders, searched below): a file counts when its
    head names CafeForge (the module's 04_bleakhold_cafe_templates.sql and every DBC rev CafeForge wrote, as doctor
    reads them). Only rows inside the café's id blocks count. The INSERTs are read with RaceForge's reader of the rev
    (comments between the rows, quotes, escapes)."""
    from . import doctor  # noqa: PLC0415

    blocks = {"spell_dbc": "spells", "spell_custom_attr": "spells", "gameobjectdisplayinfo_dbc": "displays",
              "gameobject_template": "gameobjects", "creature_template": "creatures", "item_template": "items",
              "npc_text": "npcText", "chartitles_dbc": "titles"}
    wanted = {t: (i, v, ids[blocks[t]]) for t, i, v in EARLIER_COLUMNS}
    files = []
    for path in paths:
        if os.path.isfile(path):
            files.append(path)
        for folder, dirs, names in os.walk(path):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            files += [os.path.join(folder, n) for n in sorted(names) if n.lower().endswith(".sql")]
    out = {t: set() for t in wanted}
    for path in files:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                if doctor.OWN_SQL_MARK not in f.read(800):
                    continue
                f.seek(0)
                text = f.read()
        except OSError:
            continue
        position = 0
        while True:
            match = spellmod._INSERT_HEAD.search(text, position)
            if not match:
                break
            rows, position = spellmod._split_values(text, match.end())
            if match.group(1) not in wanted:
                continue
            id_column, value_column, (lo, hi) = wanted[match.group(1)]
            columns = [c.strip().strip("`") for c in match.group(2).replace("\n", " ").split(",")]
            if id_column not in columns or value_column not in columns:
                continue
            at, vat = columns.index(id_column), columns.index(value_column)
            for values in rows:
                try:
                    row_id = int(values[at])
                except (ValueError, IndexError):
                    continue
                if lo <= row_id <= hi and vat < len(values):
                    out[match.group(1)].add(_literal(values[vat]))
    return out


def check_sql(doc, cfg, earlier=None):
    """OUT/server/cafe_check.sql: read-only; prints nothing when the café's ids are free or the café's own (this
    version's rows, and with `earlier` (earlier_values) the rows of the café's earlier versions)."""
    earlier = earlier or {}

    def plus(table, values):
        return sorted(set(values) | {v for v in earlier.get(table, ()) if v is not None}, key=str)

    ids = doc["ids"]
    gos = plus("gameobject_template", {r[3] for r in gen.go_rows(doc)})
    creatures = plus("creature_template", {r[6] for r in gen.creature_rows(doc)[0]})
    items = plus("item_template", {r[gen.item_rows(doc)[0].index("name")] for r in gen.item_rows(doc)[1]})
    texts = plus("npc_text", {t["text"] for t in doc["npcText"]})
    titles = plus("chartitles_dbc", [t.name for t in cfg.titles])
    title_ids = ", ".join(str(t.id) for t in cfg.titles)
    masks = ", ".join(str(t.mask) for t in cfg.titles)
    lines = update.comment(
        "The Bleakhold café's read-only check of the world database, made by CafeForge (cafeforge.py build) from "
        "cafe.json. Run it with  bash /root/bleakserv/deploy/cafe/check-cafe-db.sh <this file>. Every row it prints "
        "sits in one of the café's id blocks and is not the café's own, so the café's SQL would replace it; no rows: "
        "check passed. It changes nothing.")
    lines.append("SET NAMES utf8mb4;")
    statements = [
        ("spell", "ID", "spell_dbc", "%s AND COALESCE(`Name_Lang_enUS`,'') NOT IN (%s)" % (
            _between("ID", ids["spells"]), _texts(plus("spell_dbc", {s.name for s in cfg.spells})))),
        ("spell-attr", "spell_id", "spell_custom_attr", "%s AND `spell_id` NOT IN (%s)" % (
            _between("spell_id", ids["spells"]), ", ".join(str(s) for s in plus(
                "spell_custom_attr", gen.NEVER_SAVED) if isinstance(s, int)))),
        ("display", "ID", "gameobjectdisplayinfo_dbc", "%s AND COALESCE(`ModelName`,'') NOT IN (%s)" % (
            _between("ID", ids["displays"]), _texts(plus("gameobjectdisplayinfo_dbc",
                                                          {d.model for d in cfg.displays})))),
        ("go-uses-display", "entry", "gameobject_template", "`displayId` BETWEEN %d AND %d AND `entry` NOT BETWEEN "
         "%d AND %d" % (ids["displays"][0], ids["displays"][1], ids["gameobjects"][0], ids["gameobjects"][1])),
        ("go", "entry", "gameobject_template", "%s AND COALESCE(`name`,'') NOT IN (%s)" % (
            _between("entry", ids["gameobjects"]), _texts(gos))),
        ("npc", "entry", "creature_template", "%s AND COALESCE(`name`,'') NOT IN (%s)" % (
            _between("entry", ids["creatures"]), _texts(creatures))),
        ("item", "entry", "item_template", "%s AND COALESCE(`name`,'') NOT IN (%s)" % (
            _between("entry", ids["items"]), _texts(items))),
        ("text", "ID", "npc_text", "%s AND COALESCE(`text0_0`,'') NOT IN (%s)" % (
            _between("ID", ids["npcText"]), _texts(texts))),
        ("title", "ID", "chartitles_dbc", "(`ID` IN (%s) OR `Mask_ID` IN (%s)) AND COALESCE(`Name_Lang_enUS`,'') "
         "NOT IN (%s)" % (title_ids, masks, _texts(titles))),
        ("title-use", "ID", "quest_template", "`RewardTitle` IN (%s)" % title_ids),
        ("title-use", "ID", "achievement_reward", "`TitleA` IN (%s) OR `TitleH` IN (%s)" % (title_ids, title_ids)),
    ]
    for tag, column, table, where in statements:
        extra = ", `name`" if table in ("gameobject_template", "creature_template", "item_template") else ""
        # broken only after the commas between values, never inside a text (gen.split_long)
        lines += gen.split_long("SELECT '%s', `%s`%s FROM `%s` WHERE %s;" % (tag, column, extra, table, where))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------- the rev file

# The first line of every café rev (dbc_sql's header), as bleakserv's deploy/cafe/build-cafe.sh finds them; a rev
# written again after others ends with a note line of this beginning (build-cafe.sh writes the same note).
REV_MARK = "Bleakhold café (mod-bleakhold-ui, The Lion's Roast and The Grinding Tusk): the server's copies"
AGAIN_NOTE = "-- Written again by "


def _rows_of(text):
    """A rev's text without the note of a copy written again (the rows and the header)."""
    return "".join(line for line in text.splitlines(True) if not line.startswith(AGAIN_NOTE))


def _name_key(name):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name)]


def cafe_revs(folder):
    """The café's revs in a folder, in the order ac-db-import applies them (by name): [(path, text)]."""
    out = []
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder), key=_name_key):
        path = os.path.join(folder, name)
        if not name.lower().endswith(".sql") or not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        if REV_MARK in text.split("\n", 1)[0]:
            out.append((path, text))
    return out


def write_rev(target, text):
    """The rev into the server's generated-SQL folder (or a .sql path): RaceForge's update.write_rev, except that a
    folder's newest café rev decides. The same rows as the newest: nothing written. The same rows as an older one only
    (an A -> B -> A history): ac-db-import applied that file before B and never runs it again, so a new rev goes in,
    with a note line that makes it a file of its own (update-bleakhold-ui.sh refuses a renamed copy). (path, written)"""
    if target.lower().endswith(".sql"):
        return update.write_rev(target, text)
    revs = cafe_revs(target)
    if revs and _rows_of(revs[-1][1]) == text:
        return revs[-1][0], False
    again = [path for path, other in revs if _rows_of(other) == text]
    if again:
        note = "%scafeforge.py: the same rows as %s, after %s.\n" % (AGAIN_NOTE, os.path.basename(again[-1]),
                                                                       os.path.basename(revs[-1][0]))
        return update.write_rev(target, text + note)
    return update.write_rev(target, text)


# ------------------------------------------------------------------------------------------- the sql command

def size_bounds(doc):
    """{display: (min, max)} from cafe.json's sizes, W (Y) x D (X) x H around the piece's base: the server's box
    until ModelForge's bounds exist (it only decides interaction range, which the café's pieces do not need)."""
    lo, hi = doc["ids"]["displays"]
    out = {}
    for go in doc["gameobjects"]:
        display, size = go.get("display"), go.get("size")
        if catalog.is_int(display) and lo <= display <= hi and size:
            w, d, h = (float(v) for v in size)
            out[display] = ((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h))
    return out


def run(args):
    """cafeforge.py sql. Returns the exit code."""
    from . import archive  # noqa: PLC0415

    try:
        cfg = cfgmod.load(args.config, args.packs_from)
        doc = catalog.load(args.config)
    except (cfgmod.ConfigError, catalog.CatalogError) as ex:
        print("error: %s" % ex, file=sys.stderr)
        return 1
    patches = update.patch_tools()
    try:
        patchset = (patches.PatchSet.scan(args.patches, cfg.optional_packs) if args.patches
                    else patches.PatchSet([], dict(cfg.optional_packs), "(no --patches)"))
    except patches.PatchError as ex:
        print("error: %s" % ex, file=sys.stderr)
        return 1
    try:
        bounds = size_bounds(doc)
        source = "cafe.json's sizes (no art given)"
        if args.art:
            art = archive.load_art(args.art, cfg)
            bounds.update(art.bounds)
            source = "ModelForge's manifest (%s)%s" % (art.folder, "; cafe.json's sizes for %s" % ", ".join(
                art.missing_models) if art.missing_models else "")
        plan = planmod.make_plan(cfg, patchset, args.dbc, bounds)
        if plan.problems:
            print("%d problem(s): no SQL was written" % len(plan.problems), file=sys.stderr)
            for p in plan.problems:
                print("  - " + p, file=sys.stderr)
            return 1
        text = dbc_sql(plan.rows, cfg.ids, "no client copies (cafeforge.py sql: the server rows alone; the "
                                           "displays' boxes from %s)" % source)
        problems, _ = sql_problems(text, plan.rows)
        if problems:
            print("error: the SQL does not read back as its rows: %s" % "; ".join(problems[:5]), file=sys.stderr)
            return 1
        try:
            path, wrote = write_rev(args.out, text)
        except (update.UpdateError, OSError) as ex:
            print("error: %s" % ex, file=sys.stderr)
            return 1
        if args.check_out:
            with open(args.check_out, "w", encoding="utf-8", newline="\n") as f:
                f.write(check_sql(doc, cfg, earlier_values(args.earlier_sql, doc["ids"])))
            print("Check SQL: %s" % os.path.abspath(args.check_out))
    finally:
        patchset.close()
    for idx in sorted(plan.indices.values(), key=lambda i: (i.column, isinstance(i.wanted, str), i.wanted)):
        print("  " + idx.text())
    print("Server SQL: %s (%s)" % (path, "written" if wrote else "already there with the same SQL: nothing written"))
    return 0
