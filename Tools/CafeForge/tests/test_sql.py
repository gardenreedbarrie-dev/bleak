"""The server SQL (section 6.6): the generated DBC rev (applied twice to SQLite, read back field for field, the
columns of bleakserv's base schema, bleakserv's SQL codestyle), the read-only check of the world database (every
column it names in bleakserv's base schema; on SQLite it finds the rows that are not the café's and only those), and
the `sql` command.

    python3 -I Tools/CafeForge/tests/run_tests.py
"""

import contextlib
import copy
import io
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.dont_write_bytecode = True
for path in (TOOL, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

import cafe_synth as S  # noqa: E402
from cflib import REPO, catalog, config, doctor, gen, sqlout  # noqa: E402
from cflib import plan as planmod  # noqa: E402

from rflib import spells as spellmod  # noqa: E402
from rflib import update  # noqa: E402

CAFEFORGE = os.path.join(TOOL, "cafeforge.py")
DOC = catalog.load()
CFG = config.from_doc(DOC, S.PACKS)
SERVER_SRC = os.environ.get("CAFEFORGE_SERVER_SRC") or os.path.join(os.path.dirname(REPO), "bleakserv")
BASE_SQL = os.path.join(SERVER_SRC, "data", "sql", "base", "db_world")
CODESTYLE = os.path.join(SERVER_SRC, "apps", "codestyle", "codestyle-sql.py")
BOUNDS = {d.id: S.model_bounds(d.id) for d in CFG.displays}


def base_columns(table):
    """The column names of a table in bleakserv's data/sql/base/db_world/<table>.sql, in order."""
    with open(os.path.join(BASE_SQL, table + ".sql"), encoding="utf-8") as f:
        text = f.read()
    body = text[text.index("CREATE TABLE"):text.index("ENGINE")]
    return [m.group(1) for m in re.finditer(r"^\s*`([^`]+)`\s+\w+", body, re.M)]


def for_sqlite(text):
    """MySQL text literals as SQLite reads them: the generated SQL escapes only backslashes (\\\\) and quotes ('');
    SQLite keeps a backslash as it is. SET NAMES is MySQL's only."""
    return "\n".join(line for line in text.replace("\\\\", "\\").splitlines() if not line.startswith("SET NAMES"))


def check_db(text):
    """An SQLite database with the tables and columns the check text names (the first table of each statement)."""
    db = sqlite3.connect(":memory:")
    tables = {}
    for statement in [st.strip() for st in text.split(";\n") if "SELECT" in st]:
        table = re.search(r"FROM `(\w+)`", statement).group(1)
        tables.setdefault(table, set()).update(re.findall(r"`(\w+)`", re.sub(r"'(?:[^']|'')*'", "''", statement)))
    for table, columns in tables.items():
        columns.discard(table)
        db.execute("CREATE TABLE `%s` (%s)" % (table, ", ".join("`%s`" % c for c in sorted(columns))))
    return db


def insert_rows(db, rows):
    for table, row in rows:
        db.execute("INSERT INTO `%s` (%s) VALUES (%s)" % (table, ", ".join("`%s`" % c for c in row),
                                                          ", ".join("?" for _ in row)), list(row.values()))


def check_finds(db, text):
    found = []
    for statement in for_sqlite(text).split(";\n"):
        if "SELECT" in statement:
            found += [tuple(r) for r in db.execute(statement.strip().rstrip(";"))]
    return sorted(found, key=str)


def own_rows(doc, cfg):
    """The café's rows as the module SQL and the rev write them."""
    ours = [("spell_dbc", {"ID": s.id, "Name_Lang_enUS": s.name}) for s in cfg.spells]
    ours += [("spell_custom_attr", {"spell_id": s}) for s in gen.NEVER_SAVED]
    ours += [("gameobjectdisplayinfo_dbc", {"ID": d.id, "ModelName": d.model}) for d in cfg.displays]
    ours += [("gameobject_template", {"entry": r[0], "displayId": r[2], "name": r[3]}) for r in gen.go_rows(doc)]
    ours += [("creature_template", {"entry": r[0], "name": r[6]}) for r in gen.creature_rows(doc)[0]]
    names, items = gen.item_rows(doc)
    ours += [("item_template", {"entry": r[0], "name": r[names.index("name")]}) for r in items]
    ours += [("npc_text", {"ID": t["id"], "text0_0": t["text"]}) for t in doc["npcText"]]
    ours += [("chartitles_dbc", {"ID": t.id, "Mask_ID": t.mask, "Name_Lang_enUS": t.name}) for t in cfg.titles]
    return ours


def made_rows(tmp):
    """The café's rows as a build makes them, on made-up stock DBCs."""
    ps = update.patch_tools().PatchSet([], dict(CFG.optional_packs), tmp)
    plan = planmod.make_plan(CFG, ps, S.write_stock(os.path.join(tmp, "dbc")), BOUNDS)
    assert not plan.problems, plan.problems
    return plan.rows


class Rev(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="cafeforge-sql-")
        cls.rows = made_rows(cls.tmp)
        cls.text = sqlout.dbc_sql(cls.rows, CFG.ids, "the client copies are in patch-4.MPQ", host="testhost")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_reads_back_field_for_field(self):
        problems, checked = sqlout.sql_problems(self.text, self.rows)
        self.assertEqual(problems, [])
        self.assertEqual(checked, ["spell_dbc: 36 rows (234 columns)",
                                   "gameobjectdisplayinfo_dbc: 24 rows (19 columns)",
                                   "chartitles_dbc: 2 rows (37 columns)"])
        broken = self.text.replace("'Pull Shot'", "'Pull Shoot'", 1)
        problems, _ = sqlout.sql_problems(broken, self.rows)
        self.assertTrue(any(p.startswith("spell_dbc 100903: ") for p in problems), problems)

    def test_the_same_text_every_time(self):
        self.assertEqual(sqlout.dbc_sql(self.rows, CFG.ids, "the client copies are in patch-4.MPQ", host="testhost"),
                         self.text)
        self.assertIn("CafeForge", self.text[:800])   # doctor's scan of the server SQL takes it as the café's own
        self.assertIn("on testhost", self.text)

    def test_blocks_are_deleted_first(self):
        for table, lo, hi in (("spell_dbc", 100900, 100959), ("gameobjectdisplayinfo_dbc", 19300, 19339),
                              ("chartitles_dbc", 190, 191)):
            delete = "DELETE FROM `%s` WHERE `ID` BETWEEN %d AND %d;\nINSERT INTO `%s` (" % (table, lo, hi, table)
            self.assertIn(delete, self.text)
        self.assertTrue(all(len(line) <= 120 for line in self.text.splitlines() if line.startswith("--")))

    def test_applies_twice_to_sqlite(self):
        db = sqlite3.connect(":memory:")
        for table, columns, _ in sqlout.SERVER.values():
            kinds = {"s": "TEXT", "f": "REAL"}
            db.execute("CREATE TABLE `%s` (%s, PRIMARY KEY (`ID`))" % (table, ", ".join(
                "`%s` %s" % (c, kinds.get(k, "INTEGER")) for c, k in columns)))
        db.execute("INSERT INTO `spell_dbc` (`ID`, `Name_Lang_enUS`) VALUES (100950, 'An older café spell')")
        db.execute("INSERT INTO `spell_dbc` (`ID`, `Name_Lang_enUS`) VALUES (5, 'Someone else''s')")
        for _ in range(2):
            db.executescript(for_sqlite(self.text))
        count = {t: db.execute("SELECT COUNT(*) FROM `%s`" % t).fetchone()[0] for t, _, _ in sqlout.SERVER.values()}
        self.assertEqual(count, {"spell_dbc": 37, "gameobjectdisplayinfo_dbc": 24, "chartitles_dbc": 2})
        self.assertIsNone(db.execute("SELECT 1 FROM `spell_dbc` WHERE `ID` = 100950").fetchone())  # its block goes
        self.assertEqual(db.execute("SELECT `Name_Lang_enUS`, `CastingTimeIndex`, `DurationIndex`, `RangeIndex`, "
                                    "`AttributesEx`, `AttributesEx4` FROM `spell_dbc` WHERE `ID` = 100903").fetchone(),
                         ("Pull Shot", 1, 3, 1, 4, 0x08000000))
        self.assertEqual(db.execute("SELECT `ModelName`, `GeoBoxMaxZ` FROM `gameobjectdisplayinfo_dbc` WHERE `ID` = "
                                    "19306").fetchone()[0],
                         "World\\Bleakhold\\Cafe\\KettleStoveSW\\BH_Cafe_KettleStoveSW.m2")
        self.assertEqual(db.execute("SELECT `Name_Lang_enUS`, `Name1_Lang_enUS`, `Name_Lang_enGB`, `Mask_ID` FROM "
                                    "`chartitles_dbc` WHERE `ID` = 191").fetchone(),
                         ("%s, Café Legend", "%s, Café Legend", "", 161))

    @unittest.skipUnless(os.path.isdir(BASE_SQL), "bleakserv checkout not found")
    def test_columns_are_bleakserv_s(self):
        for table, columns, _ in sqlout.SERVER.values():
            self.assertEqual([c for c, _ in columns], base_columns(table), table)

    @unittest.skipUnless(os.path.isfile(CODESTYLE), "bleakserv checkout not found")
    def test_bleakserv_sql_codestyle(self):
        """The rev is committed to bleakserv's pending_db_world unchanged: every check of its codestyle-sql.py."""
        with open(CODESTYLE, encoding="utf-8") as f:
            source = f.read()
        source = source[:source.index("# Collect all files from matching directories")]
        lint = type(sys)("codestyle_sql")
        exec(compile(source, "codestyle-sql.py", "exec"), lint.__dict__)  # noqa: S102
        path = os.path.join(self.tmp, "rev_1.sql")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(self.text)
        with open(path, encoding="utf-8") as f, contextlib.redirect_stdout(io.StringIO()) as out:
            for check in (lint.multiple_blank_lines_check, lint.trailing_whitespace_check, lint.sql_check,
                          lint.insert_delete_safety_check, lint.semicolon_check, lint.backtick_check,
                          lint.non_innodb_engine_check):
                check(f, path)
        self.assertFalse(lint.error_handler, out.getvalue())


class Check(unittest.TestCase):
    TEXT = sqlout.check_sql(DOC, CFG)

    def statements(self):
        return [s.strip() for s in self.TEXT.split(";\n") if "SELECT" in s]

    def test_read_only(self):
        body = "\n".join(line for line in self.TEXT.splitlines() if not line.startswith("--"))
        self.assertFalse(re.search(r"\b(INSERT|UPDATE|DELETE|REPLACE|DROP|ALTER|CREATE)\b", body))
        self.assertEqual(len(self.statements()), 11)

    def test_texts_are_never_broken(self):
        for text in [t["text"] for t in DOC["npcText"]] + ["Café marker: queue, order and pickup"]:
            self.assertIn(gen.sql_str(text), self.TEXT)

    @unittest.skipUnless(os.path.isdir(BASE_SQL), "bleakserv checkout not found")
    def test_every_column_is_in_bleakserv_s_base_schema(self):
        for statement in self.statements():
            table = re.search(r"FROM `(\w+)`", statement).group(1)
            columns = base_columns(table)
            names = re.findall(r"`(\w+)`", re.sub(r"'(?:[^']|'')*'", "''", statement))
            for name in names:
                self.assertIn(name, columns + [table], "%s.%s" % (table, name))

    def test_finds_what_is_not_the_cafe_s_on_sqlite(self):
        db = check_db(self.TEXT)
        ours = own_rows(DOC, CFG)
        others = [("spell_dbc", {"ID": 100950, "Name_Lang_enUS": "Someone Else"}),
                  ("spell_custom_attr", {"spell_id": 100905}),
                  ("gameobjectdisplayinfo_dbc", {"ID": 19339, "ModelName": "World\\Made\\Up\\Other.m2"}),
                  ("gameobject_template", {"entry": 1000, "displayId": 19305, "name": "Uses our display"}),
                  ("gameobject_template", {"entry": 909379, "displayId": 1, "name": "Someone's Object"}),
                  ("creature_template", {"entry": 909379, "name": None}),
                  ("item_template", {"entry": 909389, "name": "Other Item"}),
                  ("npc_text", {"ID": 909319, "text0_0": "Other text"}),
                  ("chartitles_dbc", {"ID": 50, "Mask_ID": 160, "Name_Lang_enUS": "%s the Clashing"}),
                  ("quest_template", {"ID": 7, "RewardTitle": 190}),
                  ("achievement_reward", {"ID": 8, "TitleA": 0, "TitleH": 191})]
        insert_rows(db, ours + others)
        self.assertEqual(check_finds(db, self.TEXT), sorted([
            ("spell", 100950), ("spell-attr", 100905), ("display", 19339),
            ("go-uses-display", 1000, "Uses our display"), ("go", 909379, "Someone's Object"),
            ("npc", 909379, None), ("item", 909389, "Other Item"), ("text", 909319), ("title", 50),
            ("title-use", 7), ("title-use", 8)], key=str))


class Versions(unittest.TestCase):
    """A new version of the café meets the rows of the version the database holds: the check counts them as the
    café's when it reads that version's SQL (--earlier-sql), and the rev of an A, B, A history is written again."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cafeforge-versions-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def v2(self):
        doc = copy.deepcopy(DOC)
        next(w for w in doc["dbc"]["spells"] if w["spell"]["id"] == 100900)["spell"]["name"] = "On Shift II"
        doc["npcText"][0]["text"] += " Mind the new chairs."
        next(s for s in doc["staff"] if s["entry"] == 909300)["name"] = "Rosalind Thornbury-Vale"
        for g in doc["gameobjects"]:
            if g.get("name") == "Café Table":
                g["name"] = "Oak Table"
        for i in doc["items"]:
            if i.get("name") == "Apprentice's Apron":
                i["name"] = "Apprentice's Café Apron"
        return doc, config.from_doc(doc, S.PACKS)

    def write_v1(self):
        """What the server has of v1: the module's template SQL and the café rev."""
        module = os.path.join(self.tmp, "ac", "modules", "mod-bleakhold-ui", "data", "sql", "db-world")
        os.makedirs(module)
        with open(os.path.join(module, "04_bleakhold_cafe_templates.sql"), "w", encoding="utf-8") as f:
            f.write(gen.render_sql(DOC))
        revs = os.path.join(self.tmp, "gen", "pending_db_world")
        os.makedirs(revs)
        with open(os.path.join(revs, "rev_1.sql"), "w", encoding="utf-8") as f:
            f.write(sqlout.dbc_sql(made_rows(self.tmp), CFG.ids, "the client copies are in patch-4.MPQ"))
        return [os.path.join(self.tmp, "ac"), os.path.join(self.tmp, "gen")]

    def test_v1_rows_meet_a_v2_check(self):
        doc, cfg = self.v2()
        bare = sqlout.check_sql(doc, cfg)
        db = check_db(bare)
        insert_rows(db, own_rows(DOC, CFG) + [("spell_dbc", {"ID": 100950, "Name_Lang_enUS": "Someone Else"})])
        # before: the café's own v1 rows stopped the v2 deploy (and the DBC ones for good: the rev is written later)
        found = check_finds(db, bare)
        for row in (("spell", 100900), ("spell", 100950), ("text", 909300), ("npc", 909300, "Rosalind Thornbury"),
                    ("go", 909362, "Café Table"), ("item", 909380, "Apprentice's Apron")):
            self.assertIn(row, found)
        earlier = sqlout.earlier_values(self.write_v1(), doc["ids"])
        self.assertIn("On Shift", earlier["spell_dbc"])
        self.assertIn("Rosalind Thornbury", earlier["creature_template"])
        self.assertIn(100900, earlier["spell_custom_attr"])
        checked = sqlout.check_sql(doc, cfg, earlier)
        self.assertEqual(check_finds(db, checked), [("spell", 100950)])   # someone else's row is still found
        # a file without CafeForge's head is never the café's
        other = os.path.join(self.tmp, "other.sql")
        with open(other, "w", encoding="utf-8") as f:
            f.write("INSERT INTO `spell_dbc` (`ID`, `Name_Lang_enUS`) VALUES (100950, 'Someone Else');\n")
        self.assertNotIn("Someone Else", sqlout.earlier_values([other], doc["ids"])["spell_dbc"])

    def test_a_b_a_writes_a_rev_of_its_own(self):
        gen_dir = os.path.join(self.tmp, "pending_db_world")
        a = sqlout.dbc_sql(made_rows(self.tmp), CFG.ids, "the client copies are in patch-4.MPQ", host="h")
        b = a.replace("'Pull Shot'", "'Pull Shot II'", 1)
        first, wrote = sqlout.write_rev(gen_dir, a)
        self.assertTrue(wrote)
        self.assertEqual(sqlout.write_rev(gen_dir, a), (first, False))   # the same rows: nothing written
        second, wrote = sqlout.write_rev(gen_dir, b)
        self.assertTrue(wrote)
        third, wrote = sqlout.write_rev(gen_dir, a)                      # before: "already there" (rev_A), B stayed
        self.assertTrue(wrote)
        self.assertNotIn(third, (first, second))
        with open(third, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith(a))
        self.assertIn("-- Written again by cafeforge.py: the same rows as %s, after %s." % (
            os.path.basename(first), os.path.basename(second)), text)
        # the newest, its note aside, holds these rows now: nothing more
        self.assertEqual(sqlout.write_rev(gen_dir, a), (third, False))
        self.assertEqual(len([n for n in os.listdir(gen_dir) if n.endswith(".sql")]), 3)
        self.assertEqual([os.path.basename(p) for p, _ in sqlout.cafe_revs(gen_dir)],
                         [os.path.basename(p) for p in (first, second, third)])


class Command(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cafeforge-sqlcmd-")
        self.dbc = S.write_stock(os.path.join(self.tmp, "dbc"))
        self.gen = os.path.join(self.tmp, "gen")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sql(self, *extra):
        return subprocess.run([sys.executable, "-I", CAFEFORGE, "sql", "--dbc", self.dbc, "--out", self.gen, *extra],
                              capture_output=True, text=True)

    def rev(self):
        (name,) = os.listdir(self.gen)
        with open(os.path.join(self.gen, name), encoding="utf-8") as f:
            return f.read()

    def test_server_rows_alone(self):
        check = os.path.join(self.tmp, "check.sql")
        r = self.sql("--check-out", check)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("(written)", r.stdout)
        self.assertIn("  castMs 1500 -> SpellCastTimes 6 (1500 ms)", r.stdout)
        self.assertTrue(os.path.isfile(check))
        text = self.rev()
        self.assertIn("cafe.json's sizes", " ".join(text.split()))
        back = spellmod.parse_sql_rows(text, "gameobjectdisplayinfo_dbc")
        go = next(g for g in DOC["gameobjects"] if g.get("display") == 19300)
        w, d, h = go["size"]
        self.assertEqual([round(float(back[19300][c]), 5) for c in ("GeoBoxMinX", "GeoBoxMaxY", "GeoBoxMaxZ")],
                         [round(-d / 2, 5), round(w / 2, 5), round(h, 5)])
        r = self.sql()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("already there with the same SQL: nothing written", r.stdout)
        self.assertEqual(len(os.listdir(self.gen)), 1)

    def test_with_the_art_and_the_patches(self):
        art = S.write_art(os.path.join(self.tmp, "art"), CFG, skip_models=("TipJar",))
        patches = os.path.join(self.tmp, "patches")
        S.write_patch(patches, "patch-R.MPQ", {"SpellCastTimes": S.stock_tables(
            cast_times=tuple(r for r in S.CAST_TIMES if r[1] != 1500) + ((9, 1500),))["SpellCastTimes"]})
        r = self.sql("--art", art, "--patches", patches)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("  castMs 1500 -> SpellCastTimes 9 (1500 ms)", r.stdout)       # the realm's copy decides
        text = self.rev()
        header = " ".join(line[3:] for line in text.splitlines() if line.startswith("-- "))
        self.assertIn("ModelForge's manifest", header)
        self.assertIn("cafe.json's sizes for TipJar", header)
        back = spellmod.parse_sql_rows(text, "gameobjectdisplayinfo_dbc")
        self.assertAlmostEqual(float(back[19306]["GeoBoxMaxZ"]), S.model_bounds(19306)[1][2], places=6)

    def test_a_taken_id_writes_nothing(self):
        S.write_stock(self.dbc, S.stock_tables(spells=[(100903, "Someone Else")]))
        r = self.sql()
        self.assertEqual(r.returncode, 1)
        self.assertIn("id 100903 is taken by 'Someone Else'", r.stderr)
        self.assertFalse(os.path.exists(self.gen))

    def test_doctor_skips_the_rev(self):
        self.assertEqual(self.sql().returncode, 0)
        self.assertEqual(doctor.scan_server_sql([self.gen], CFG.ids), {})


if __name__ == "__main__":
    unittest.main()
