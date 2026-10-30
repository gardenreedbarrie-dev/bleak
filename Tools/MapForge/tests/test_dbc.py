"""Reading and writing the map tables: round trips, layouts per the client's structs, localized strings."""

import os
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from dbc import layout  # noqa: E402
from tests import synth_dbc  # noqa: E402

from rflib.dbc import DbcError, DbcTable  # noqa: E402

REC_DIR = layout.default_rec_dir()


class LayoutTests(unittest.TestCase):
    def test_counts_and_sizes_the_client_aborts_on(self):
        # WowClientDB_Common::Load aborts on a wrong column count or row size; these are the Rec constants.
        expected = {
            "Map": (66, 264), "AreaTable": (36, 144), "LoadingScreens": (4, 16), "Light": (15, 60),
            "LightParams": (9, 36), "LightSkybox": (3, 12), "WorldMapArea": (11, 44),
            "BattlemasterList": (32, 128), "PvpDifficulty": (6, 24), "MapDifficulty": (23, 92),
            "SoundAmbience": (3, 12), "ZoneMusic": (8, 32), "ZoneIntroMusicTable": (5, 20),
        }

        for name, (columns, row_size) in expected.items():
            schema = layout.get(name)
            self.assertEqual((schema.num_columns, schema.row_size), (columns, row_size), name)
            self.assertEqual(schema.computed_row_size(), row_size, name)
            self.assertFalse(schema.generated_id, name)

    def test_key_columns(self):
        maps = layout.get("Map")
        self.assertEqual(maps.index("directory"), 1)
        self.assertEqual(maps.index("instanceType"), 2)
        self.assertEqual(maps.index("mapName[0]"), 5)
        self.assertEqual(maps.index("areaTableID"), 22)
        self.assertEqual(maps.index("loadingScreenID"), 57)
        self.assertEqual(maps.index("maxPlayers"), 65)
        self.assertEqual(maps.localized_fields(), ["mapName", "mapDescription0", "mapDescription1"])

        areas = layout.get("AreaTable")
        self.assertEqual(areas.index("continentID"), 1)
        self.assertEqual(areas.index("areaBit"), 3)
        self.assertEqual(areas.index("flags"), 4)
        self.assertEqual(areas.index("areaName[0]"), 11)
        self.assertEqual(areas.index("lightID"), 35)

    def test_server_formats_match_the_client_layouts(self):
        # One DBCfmt.h character and one SQL column per client column, in client order.
        for name, (table, fmt, columns) in layout.SERVER.items():
            schema = layout.get(name)
            self.assertEqual(len(fmt), schema.num_columns, name)
            self.assertEqual(len(columns), schema.num_columns, name)
            self.assertTrue(table.endswith("_dbc"), name)

            for column, char in zip(schema.columns, fmt):
                if char == "f":
                    self.assertEqual(column.kind, "float", f"{name}.{column.name}")
                elif char == "s":
                    self.assertTrue(column.is_string, f"{name}.{column.name}")

    @unittest.skipUnless(REC_DIR, "WoW/Source/DB/Rec of the decompilation not found")
    def test_generated_schemas_match_the_client(self):
        with open(os.path.join(TOOL_DIR, "dbc", "schemas.py"), encoding="utf-8") as f:
            self.assertEqual(f.read(), layout.emit_schemas_module(REC_DIR), "run `package.py schemas --write`")


class RoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = synth_dbc.build_tables()

    def test_every_table_writes_back_identical(self):
        for name, data in self.tables.items():
            table = DbcTable.from_bytes(data, layout.get(name), name)
            self.assertEqual(table.to_bytes(), data, name)

    def test_header_fields(self):
        data = self.tables["Map"]
        magic, records, fields, record_size, string_size = struct.unpack_from("<4sIIII", data)
        self.assertEqual((magic, records, fields, record_size), (b"WDBC", 3, 66, 264))
        self.assertEqual(len(data), 20 + records * 264 + string_size)

    def test_wrong_layout_is_refused(self):
        data = bytearray(self.tables["Map"])
        struct.pack_into("<I", data, 8, 65)

        with self.assertRaisesRegex(DbcError, "65 columns, the client expects 66"):
            DbcTable.from_bytes(bytes(data), layout.get("Map"))

        data = bytearray(self.tables["Map"])
        struct.pack_into("<I", data, 12, 260)

        with self.assertRaisesRegex(DbcError, "row size 260"):
            DbcTable.from_bytes(bytes(data), layout.get("Map"))

        with self.assertRaisesRegex(DbcError, "cut off"):
            DbcTable.from_bytes(self.tables["Map"][:-4], layout.get("Map"))

    def test_appending_a_row_keeps_every_existing_row_byte_identical(self):
        before = self.tables["Map"]
        table = DbcTable.from_bytes(before, layout.get("Map"))
        row = list(table.rows[1])
        table.set(row, "id", 901)
        table.set_str(row, "directory", "BleakholdRoyale")
        table.rows.append(row)
        after = table.to_bytes()

        # Header + the original rows are byte-identical (the record count and string size grow); the new row and
        # its strings are appended after them.
        self.assertEqual(after[4:8], struct.pack("<I", 4))
        self.assertEqual(after[8:16], before[8:16])
        self.assertEqual(after[20:20 + 3 * 264], before[20:20 + 3 * 264])
        old_strings = before[20 + 3 * 264:]
        self.assertEqual(after[20 + 4 * 264:20 + 4 * 264 + len(old_strings)], old_strings)

        reread = DbcTable.from_bytes(after, layout.get("Map"))
        self.assertEqual(reread.get_str(reread.rows[3], "directory"), "BleakholdRoyale")
        self.assertEqual(reread.get_str(reread.rows[1], "directory"), "WarsongGulch")

    def test_localized_strings(self):
        table = DbcTable.from_bytes(self.tables["Map"], layout.get("Map"))
        row = table.rows[1]
        self.assertEqual(table.get_loc(row, "mapName"), ["Warsong Gulch"] * 9 + [""] * 7)
        # The flags column is its own column and set_loc leaves it alone.
        flags_index = table.col("mapName_flags")
        self.assertEqual(row[flags_index], synth_dbc.LOC_FLAGS)

        texts = ["Bleakhold Royale"] * 9 + [""] * 7
        texts[2] = "Royale de Bleakhold"
        table.set_loc(row, "mapName", texts)
        self.assertEqual(row[flags_index], synth_dbc.LOC_FLAGS)

        reread = DbcTable.from_bytes(table.to_bytes(), layout.get("Map"))
        self.assertEqual(reread.get_loc(reread.rows[1], "mapName"), texts)
        self.assertEqual(reread.get_str(reread.rows[1], "mapName[2]"), "Royale de Bleakhold")
        # Non-ASCII text survives the round trip as UTF-8.
        texts[8] = "Блекхолд"
        table.set_loc(row, "mapName", texts)
        reread = DbcTable.from_bytes(table.to_bytes(), layout.get("Map"))
        self.assertEqual(reread.get_str(reread.rows[1], "mapName[8]"), "Блекхолд")

    def test_floats_keep_their_bit_pattern(self):
        table = DbcTable.from_bytes(self.tables["AreaTable"], layout.get("AreaTable"))
        self.assertEqual(table.float_value(table.rows[0], "minElevation"), -500.0)
        self.assertEqual(table.to_bytes(), self.tables["AreaTable"])


if __name__ == "__main__":
    unittest.main()
