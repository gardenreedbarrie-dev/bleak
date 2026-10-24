"""Server SQL: the rows as AzerothCore's DBCDatabaseLoader reads them, and the ids its SQL already uses."""

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
