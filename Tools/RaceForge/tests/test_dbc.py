"""WDBC reading and writing."""

import os
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from rflib import schema_access  # noqa: E402
from rflib.dbc import DbcError, DbcTable  # noqa: E402
from tests import synth  # noqa: E402


class DbcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = synth.build_tables()

    def test_unchanged_tables_write_back_identical(self):
        for name, data in self.tables.items():
            table = DbcTable.from_bytes(data, schema_access.get(name), name)
            self.assertEqual(table.to_bytes(), data, name)
            self.assertFalse(table.is_modified(), name)

    def test_header_must_match_the_client(self):
        data = bytearray(self.tables["ChrRaces"])
        struct.pack_into("<I", data, 8, 68)

        with self.assertRaisesRegex(DbcError, "68 columns, the client expects 69"):
            DbcTable.from_bytes(bytes(data), schema_access.get("ChrRaces"))

        data = bytearray(self.tables["ChrRaces"])
        struct.pack_into("<I", data, 12, 272)

        with self.assertRaisesRegex(DbcError, "row size 272"):
            DbcTable.from_bytes(bytes(data), schema_access.get("ChrRaces"))

        with self.assertRaisesRegex(DbcError, "cut off"):
            DbcTable.from_bytes(self.tables["ChrRaces"][:-10], schema_access.get("ChrRaces"))

        with self.assertRaisesRegex(DbcError, "not a WDBC"):
            DbcTable.from_bytes(b"WDB2" + self.tables["ChrRaces"][4:], schema_access.get("ChrRaces"))

    def test_header_layout(self):
        table = DbcTable.from_bytes(self.tables["CharBaseInfo"], schema_access.get("CharBaseInfo"))
        data = table.to_bytes()
        magic, records, fields, record_size, string_size = struct.unpack_from("<4sIIII", data)
        self.assertEqual((magic, fields, record_size), (b"WDBC", 2, 2))
        self.assertEqual(len(data), 20 + records * 2 + string_size)

    def test_strings_are_appended_and_reused(self):
        table = DbcTable.from_bytes(self.tables["ChrRaces"], schema_access.get("ChrRaces"))
        original = bytes(table.strings)
        row = table.rows[0]
        existing = table.get_str(row, "clientFileString")
        self.assertEqual(table.add_string(existing), table.get(row, "clientFileString"))
        self.assertEqual(table.add_string(""), 0)

        offset = table.add_string("HighElf")
        self.assertEqual(offset, len(original))
        self.assertEqual(table.add_string("HighElf"), offset)
        self.assertEqual(bytes(table.strings[:len(original)]), original)  # old offsets stay valid

        table.set_str(row, "clientFileString", "Ünïcødé")
        self.assertEqual(table.get_str(row, "clientFileString"), "Ünïcødé")

        reread = DbcTable.from_bytes(table.to_bytes(), schema_access.get("ChrRaces"))
        self.assertEqual(reread.get_str(reread.rows[0], "clientFileString"), "Ünïcødé")
        self.assertEqual(reread.get_str(reread.rows[1], "clientFileString"), table.get_str(table.rows[1], "clientFileString"))

    def test_values(self):
        table = DbcTable.from_bytes(self.tables["CharStartOutfit"], schema_access.get("CharStartOutfit"))
        row = table.rows[0]
        self.assertEqual(table.get_signed(row, "itemID[10]"), -1)
        table.set(row, "raceID", 22)
        self.assertEqual(table.get(row, "raceID"), 22)

        with self.assertRaises(DbcError):
            table.set(row, "raceID", 300)

        table.set(row, "itemID[10]", -5)
        self.assertEqual(table.get_signed(row, "itemID[10]"), -5)

        barber = DbcTable.from_bytes(self.tables["BarberShopStyle"], schema_access.get("BarberShopStyle"))
        self.assertAlmostEqual(barber.float_value(barber.rows[0], "costModifier"), 1.0)

    def test_generated_ids(self):
        table = DbcTable.from_bytes(self.tables["CharacterFacialHairStyles"], schema_access.get("CharacterFacialHairStyles"))
        self.assertEqual(table.max_id(), len(table.rows) - 1)
        self.assertEqual(table.ids(), set(range(len(table.rows))))


if __name__ == "__main__":
    unittest.main()
