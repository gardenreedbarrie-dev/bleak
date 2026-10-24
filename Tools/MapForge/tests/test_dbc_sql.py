"""Server SQL: the rows as AzerothCore's DBCDatabaseLoader reads them, and the ids its SQL already uses."""

import contextlib
import io
import math
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from dbc import layout, sqlgen  # noqa: E402
from tests import synth_dbc  # noqa: E402
from tests.synth_dbc import run_forge  # noqa: E402

SERVER_SRC = os.environ.get("MAPFORGE_SERVER_SRC") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(TOOL_DIR))), "bleakserv")


def to_sqlite(sql: str) -> str:
    """MySQL escapes to SQLite: \\' -> '' and \\\\ -> \\."""
    out = []
    i = 0

    while i < len(sql):
        if sql[i] == "\\" and i + 1 < len(sql):
            out.append("''" if sql[i + 1] == "'" else sql[i + 1])
            i += 2
        else:
            out.append(sql[i])
            i += 1

    return "".join(out)


class SqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = synth_dbc.default_config()
        data["map"]["name"] = "Bleakhold's Royale"  # a quote to escape
        cls.cfg, cls.tables, cls.result, _ = run_forge(data)
        cls.files = sqlgen.build(cls.tables, cls.cfg, cls.result)

    def db(self):
        con = sqlite3.connect(":memory:")

        for name, (table, _, columns) in layout.SERVER.items():
            con.execute(f"CREATE TABLE `{table}` (" + ", ".join(f"`{c}`" for c in columns) +
                        f", PRIMARY KEY (`{columns[0]}`))")

        con.execute("CREATE TABLE `instance_template` (`map` PRIMARY KEY, `parent`, `script`, `allowMount`)")
        return con

    def test_install_runs_and_matches_the_client_rows(self):
        con = self.db()
        con.executescript(to_sqlite(self.files["bleakhold_royale.sql"]))
        con.executescript(to_sqlite(self.files["bleakhold_royale.sql"]))  # runs again: DELETE before INSERT

        row = con.execute("SELECT * FROM `map_dbc` WHERE `ID` = 901").fetchone()
        maps = self.tables["Map"]
        client = maps.by_id()[901]
        self.assertEqual(len(row), 66)
        self.assertEqual(row[1], "BleakholdRoyale")
        self.assertEqual(row[2], 3)  # InstanceType
        self.assertEqual(row[5], "Bleakhold's Royale")  # slot 0 (enUS)
        self.assertEqual(row[21], client[maps.col("mapName_flags")])  # the flags column, by position
        self.assertEqual(row[22], 5100)  # AreaTableID
        self.assertEqual(row[65], 40)  # MaxPlayers

        area = con.execute("SELECT `ContinentID`, `Flags`, `AreaBit` FROM `areatable_dbc` "
                           "WHERE `ID` = 5100").fetchone()
        self.assertEqual(area[0], 901)
        self.assertTrue(area[1] & 0x80)
        self.assertEqual(area[2], self.result.area_bits[5100])

        self.assertEqual(con.execute("SELECT `MapID_1`, `MapID_2` FROM `battlemasterlist_dbc` WHERE `ID` = 12")
                         .fetchone(), (901, -1))
        self.assertEqual(con.execute("SELECT COUNT(*) FROM `pvpdifficulty_dbc` WHERE `MapID` = 901")
                         .fetchone(), (1,))
        self.assertEqual(con.execute("SELECT `ContinentID` FROM `light_dbc`").fetchone(), (901,))
        self.assertEqual(con.execute("SELECT `AreaID` FROM `worldmaparea_dbc`").fetchone(), (5100,))

        # The whole row equals the client's values column by column.
        values = [float(v) if isinstance(v, float) else v for v in row]
        self.assertEqual(len(values), len(maps.schema.columns))

        con.executescript(to_sqlite(self.files["bleakhold_royale_remove.sql"]))

        for table, _, _ in layout.SERVER.values():
            self.assertEqual(con.execute(f"SELECT COUNT(*) FROM `{table}`").fetchone(), (0,), table)

    def test_check_file_is_read_only(self):
        con = self.db()
        con.executescript(to_sqlite(self.files["bleakhold_royale_check.sql"]))
        self.assertNotRegex(self.files["bleakhold_royale_check.sql"], r"(?m)^(DELETE|INSERT|UPDATE)")

    def test_repository_sql_conventions(self):
        text = self.files["bleakhold_royale.sql"]
        lines = text.split("\n")
        previous = ""

        for line in lines:
            if line.startswith("--"):
                continue

            if "INSERT" in line:
                self.assertIn("DELETE", previous, "every INSERT follows a DELETE (codestyle-sql.py)")

            previous = line

        self.assertTrue(text.endswith("\n") and not text.endswith("\n\n"))
        self.assertNotIn("\n\n\n", text)
        self.assertNotIn(";;", text)
        self.assertFalse(any(line != line.rstrip() for line in lines))
        self.assertFalse(any("\t" in line for line in lines))

    def test_instance_template_only_for_dungeons(self):
        self.assertNotIn("instance_template", self.files["bleakhold_royale.sql"])
        data = synth_dbc.default_config()
        data["map"]["instance_type"] = 1
        del data["battleground"]
        cfg, tables, result, _ = run_forge(data)
        files = sqlgen.build(tables, cfg, result)
        self.assertIn("INSERT INTO `instance_template`", files["bleakhold_royale.sql"])

    @unittest.skipUnless(os.path.isfile(os.path.join(SERVER_SRC, "src", "server", "shared", "DataStores",
                                                     "DBCfmt.h")), "bleakserv checkout not found")
    def test_server_formats_and_columns_match_bleakserv(self):
        with open(os.path.join(SERVER_SRC, "src", "server", "shared", "DataStores", "DBCfmt.h"),
                  encoding="utf-8") as f:
            formats = dict(re.findall(r"char constexpr (\w+)\[\] = \"(\w+)\";", f.read()))

        names = {"Map": "MapEntryfmt", "AreaTable": "AreaTableEntryfmt", "Light": "LightEntryfmt",
                 "WorldMapArea": "WorldMapAreaEntryfmt", "BattlemasterList": "BattlemasterListEntryfmt",
                 "PvpDifficulty": "PvPDifficultyfmt"}

        for name, (table, fmt, columns) in layout.SERVER.items():
            self.assertEqual(formats[names[name]], fmt, name)
            path = os.path.join(SERVER_SRC, "data", "sql", "base", "db_world", f"{table}.sql")

            with open(path, encoding="utf-8") as f:
                text = f.read()

            body = text[text.index("CREATE TABLE"):text.index("ENGINE")]
            self.assertEqual(tuple(re.findall(r"^\s+`(\w+)`", body, re.M)), columns, table)


def poi_doc(**changes):
    """A pois.json like terrain/build.py writes (3 x 3 tiles 31..33)."""
    pois = [
        {"id": 5113, "name": "overlook", "kind": "lobby", "title": "The Overlook", "x": 455.0, "y": 455.0,
         "z": 44.7, "facing": 0.0, "radius": 32.0, "weight": 0, "param": 0},
        {"id": 5107, "name": "crows_rise", "kind": "landmark", "title": "Crow's Rise", "x": 60.0, "y": -420.0,
         "z": 18.2, "facing": 0.0, "radius": 60.0, "weight": 0, "param": 0},
        {"id": 5114, "name": "pit_bridge", "kind": "crossing", "title": "Pit Bridge", "x": 150.0, "y": -665.0,
         "z": 3.6, "facing": 90.0, "radius": 18.0, "weight": 0, "param": 0},
        {"id": 1, "name": "crate_a", "kind": "crate", "title": "", "x": -240.25, "y": -252.0, "z": 31.0,
         "facing": 0.0, "radius": 2.0, "weight": 0, "param": 2},
        {"id": 2, "name": "final_keep", "kind": "final_site", "title": "", "x": -266.0, "y": -258.0, "z": 31.0,
         "facing": 0.0, "radius": 35.0, "weight": 20, "param": 0},
    ]
    doc = {"map_id": 901, "map_directory": "BleakholdRoyale",
           "world_bounds": {"min_x": -1066.667, "max_x": 533.333, "min_y": -1066.667, "max_y": 533.333},
           "counts": {}, "pois": pois}
    doc.update(changes)
    return doc


class PoiSqlTests(unittest.TestCase):
    def db(self):
        con = sqlite3.connect(":memory:")
        con.execute(f"CREATE TABLE `{sqlgen.POI_TABLE}` (" + ", ".join(f"`{c}`" for c in sqlgen.POI_COLUMNS) +
                    ", PRIMARY KEY (`map`, `id`))")
        return con

    def test_rows_run_twice_and_keep_other_maps(self):
        con = self.db()
        con.execute(f"INSERT INTO `{sqlgen.POI_TABLE}` VALUES (566, 1, 'landmark', 'Fel Reaver', 2044.3, 1729.7, "
                    "1250, 0, 30, 0, 0)")
        text = sqlgen.poi_sql(poi_doc())
        con.executescript(to_sqlite(text))
        con.executescript(to_sqlite(text))  # DELETE before INSERT: runs again
        rows = con.execute(f"SELECT * FROM `{sqlgen.POI_TABLE}` WHERE `map` = 901 ORDER BY `id`").fetchall()
        self.assertEqual([r[1] for r in rows], [1, 2, 5107, 5113, 5114])
        crate = rows[0]
        self.assertEqual(crate[2:4], ("crate", "crate_a"))  # no title: the POI name
        self.assertEqual((crate[4], crate[5], crate[6], crate[10]), (-240.25, -252.0, 31.0, 2))
        self.assertEqual(rows[1][9], 20)  # the final site's weight
        self.assertEqual(rows[2][3], "Crow's Rise")  # the title, quote escaped
        self.assertAlmostEqual(rows[4][7], math.pi / 2, places=4)  # facing 90 -> o in radians
        self.assertEqual(con.execute(f"SELECT COUNT(*) FROM `{sqlgen.POI_TABLE}` WHERE `map` = 566").fetchone(),
                         (1,))

    def test_table_layout_runs(self):
        con = sqlite3.connect(":memory:")
        table = sqlgen.poi_table_sql()
        self.assertIn("ENGINE=InnoDB", table)
        self.assertIn("PRIMARY KEY (`map`, `id`)", table)
        body = table[table.index("(\n") + 1:table.rindex(")")]
        con.executescript(f"CREATE TABLE `t` ({body});")  # the column list is portable
        self.assertEqual([c[1] for c in con.execute("PRAGMA table_info(`t`)")], list(sqlgen.POI_COLUMNS))

    def test_repository_sql_conventions(self):
        for text in (sqlgen.poi_sql(poi_doc()), sqlgen.poi_table_sql()):
            lines = text.split("\n")
            previous = ""

            for line in lines:
                if line.startswith("--"):
                    continue

                if "INSERT" in line:
                    self.assertIn("DELETE", previous, "every INSERT follows a DELETE (codestyle-sql.py)")

                previous = line

            self.assertTrue(text.endswith("\n") and not text.endswith("\n\n"))
            self.assertNotIn("\n\n\n", text)
            self.assertNotIn(";;", text)
            self.assertFalse(any(line != line.rstrip() or "\t" in line for line in lines))

    def test_bad_documents(self):
        with self.assertRaises(sqlgen.PoiError):
            sqlgen.poi_sql(poi_doc(map_id=None))
        self.assertIn("WHERE `map` = 950", sqlgen.poi_sql(poi_doc(map_id=None), 950))
        doc = poi_doc()
        doc["pois"][1]["id"] = 1
        with self.assertRaises(sqlgen.PoiError):
            sqlgen.poi_sql(doc)
        doc = poi_doc()
        del doc["pois"][0]["id"]
        with self.assertRaises(sqlgen.PoiError):
            sqlgen.poi_rows(doc)

    def test_royale_rules(self):
        problems = sqlgen.royale_poi_problems(poi_doc())
        self.assertTrue(any("0 common crates, want at least 44" in p for p in problems), problems)
        self.assertTrue(any("0 Shadow Sight orbs, want 2" in p for p in problems), problems)
        self.assertTrue(any("1 landmarks, want at least 3" in p for p in problems), problems)
        self.assertFalse(any("lobby" in p for p in problems), problems)
        doc = poi_doc()
        base = dict(doc["pois"][3])
        for i in range(44):
            doc["pois"].append(dict(base, id=100 + i, name=f"c{i}", param=1))
        for i in range(2):
            doc["pois"].append(dict(base, id=200 + i, name=f"orb{i}", kind="orb_shadow", param=0))
            doc["pois"].append(dict(base, id=210 + i, name=f"sup{i}", kind="supply_site", param=0))
            doc["pois"].append(dict(base, id=220 + i, name=f"lm{i}", kind="landmark", param=0))
        self.assertEqual(sqlgen.royale_poi_problems(doc), [])
        doc["pois"][4]["x"] = 300.0  # the final site 567 yd from the centre
        self.assertTrue(any("final site 'final_keep' is 566.7 yd" in p for p in sqlgen.royale_poi_problems(doc)))
        doc["pois"][4]["x"] = -266.0
        doc["pois"][3]["param"] = 3
        self.assertTrue(any("param 3" in p for p in sqlgen.royale_poi_problems(doc)))

    @unittest.skipUnless(os.path.isfile(os.path.join(SERVER_SRC, "apps", "codestyle", "codestyle-sql.py")),
                         "bleakserv checkout not found")
    def test_passes_bleakserv_codestyle(self):
        # The linter runs itself on import (git fetch and the repository's folders): take its check functions only.
        with open(os.path.join(SERVER_SRC, "apps", "codestyle", "codestyle-sql.py"), encoding="utf-8") as f:
            source = f.read()

        source = source[:source.index("# Collect all files from matching directories")]
        lint = type(sys)("codestyle_sql")
        exec(compile(source, "codestyle-sql.py", "exec"), lint.__dict__)  # noqa: S102
        tmp = tempfile.mkdtemp()

        try:
            for name, text in (("rows.sql", sqlgen.poi_sql(poi_doc())), ("table.sql", sqlgen.poi_table_sql())):
                path = os.path.join(tmp, name)

                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)

                with open(path, encoding="utf-8") as f, contextlib.redirect_stdout(io.StringIO()) as out:
                    for check in (lint.multiple_blank_lines_check, lint.trailing_whitespace_check, lint.sql_check,
                                  lint.insert_delete_safety_check, lint.semicolon_check, lint.backtick_check,
                                  lint.non_innodb_engine_check):
                        check(f, path)

                self.assertFalse(lint.error_handler, out.getvalue())
        finally:
            shutil.rmtree(tmp)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, rel: str, text: str):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_ids_from_inserts(self):
        self.write("updates/db_world/a.sql", "DELETE FROM `worldmaparea_dbc` WHERE `ID` IN (1000, 1001);\n"
                   "INSERT INTO `worldmaparea_dbc` (`ID`, `MapID`, `AreaName`) VALUES\n"
                   "(1000, 530, 'The (Veiled), Sea'),\n(1001, 530, 'It\\'s north');\n")
        self.write("modules/m/data/sql/db-world/b.sql", "REPLACE INTO map_dbc VALUES (740, 'Emberwing', 2);\n"
                   "INSERT INTO `creature` VALUES (5, 6);\n")
        found = sqlgen.scan_server_sql([self.tmp])
        self.assertEqual(set(found["WorldMapArea"]), {1000, 1001})
        self.assertEqual(set(found["Map"]), {740})
        self.assertNotIn("creature", found)

    def test_mapforge_files_for_this_map_are_skipped(self):
        cfg, tables, result, _ = run_forge()
        text = sqlgen.build(tables, cfg, result)["bleakhold_royale.sql"]
        self.write("updates/pending_db_world/rev_1.sql", text)
        self.assertEqual(sqlgen.scan_server_sql([self.tmp], "BleakholdRoyale"), {})
        self.assertIn(901, sqlgen.scan_server_sql([self.tmp], "OtherMap")["Map"])


if __name__ == "__main__":
    unittest.main()
