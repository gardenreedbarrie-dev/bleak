"""The DBC layouts must be the client's: rflib/schemas.py is checked against WoW/Source/DB/Rec."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from rflib import recparse, schema_access  # noqa: E402

REC_DIR = recparse.default_rec_dir()

SAMPLE_HEADER = """
class SampleRec {
    public:
    static const int32_t s_numColumns = 25;
    static const int32_t s_rowSize = 94;
    static const bool s_generatedID = false;

    /* 0000 */ int32_t m_id;
    /* 0004 */ int8_t m_small;
    /* 0005 */ int8_t m_other;
    /* 0008 */ float m_scale [2];
    /* 0010 */ const char* m_path;
    /* 0014 */ const char* m_name;
    /* 0018 */ int32_t m_values [2];
};
"""

SAMPLE_SOURCE = """
const char* SampleRec::GetFilename() {
    return "DBFilesClient\\\\Sample.dbc";
}

bool SampleRec::Read(SFileImpl* file, const char* stringBuffer) {
    uint32_t pathOffset;
    uint32_t nameOffset[16];
    uint32_t nameFlags;

    int32_t idRead = SFileReadFile(file, &this->m_id, sizeof(this->m_id), nullptr, nullptr, 0);
    int32_t smallRead = SFileReadFile(file, &this->m_small, sizeof(this->m_small), nullptr, nullptr, 0);
    int32_t otherRead = SFileReadFile(file, &this->m_other, sizeof(this->m_other), nullptr, nullptr, 0);
    int32_t scaleRead = SFileReadFile(file, this->m_scale, sizeof(this->m_scale), nullptr, nullptr, 0);
    int32_t pathRead = SFileReadFile(file, &pathOffset, sizeof(pathOffset), nullptr, nullptr, 0);
""" + "".join(f"    int32_t nameRead{i} = SFileReadFile(file, &nameOffset[{i}], sizeof(nameOffset[{i}]), nullptr, nullptr, 0);\n" for i in range(16)) + """
    int32_t nameFlagsRead = SFileReadFile(file, &nameFlags, sizeof(nameFlags), nullptr, nullptr, 0);
    int32_t valuesRead0 = SFileReadFile(file, &this->m_values[0], sizeof(this->m_values[0]), nullptr, nullptr, 0);
    int32_t valuesRead1 = SFileReadFile(file, &this->m_values[1], sizeof(this->m_values[1]), nullptr, nullptr, 0);

    if (!idRead) {
        return false;
    }

    return true;
}
"""


class ParserTests(unittest.TestCase):
    def test_every_read_form(self):
        schema = recparse.parse_rec(SAMPLE_HEADER, SAMPLE_SOURCE, "Sample")
        self.assertEqual(schema.filename, "DBFilesClient\\Sample.dbc")
        self.assertEqual([c.kind for c in schema.columns[:6]], ["int", "byte", "byte", "float", "float", "str"])
        self.assertEqual(schema.localized_fields(), ["name"])
        self.assertEqual(schema.columns[6].name, "name[0]")
        self.assertEqual(schema.columns[22].name, "name_flags")
        self.assertEqual(schema.field_columns("values"), [23, 24])
        self.assertEqual(schema.struct_format(), "<IBB" + "I" * 22)

    def test_count_mismatch_is_an_error(self):
        with self.assertRaises(recparse.RecParseError):
            recparse.parse_rec(SAMPLE_HEADER.replace("s_numColumns = 25", "s_numColumns = 26"), SAMPLE_SOURCE, "Sample")

        with self.assertRaises(recparse.RecParseError):
            recparse.parse_rec(SAMPLE_HEADER.replace("s_rowSize = 94", "s_rowSize = 96"), SAMPLE_SOURCE, "Sample")


@unittest.skipUnless(REC_DIR, "WoW/Source/DB/Rec of the decompilation not found")
class ClientRecTests(unittest.TestCase):
    def test_every_client_table_parses(self):
        tables = recparse.load_all(REC_DIR)
        # 241 Rec classes in the 3.3.5a decompilation; each one's columns add up to its s_numColumns/s_rowSize.
        self.assertGreaterEqual(len(tables), 240)

        for name, schema in tables.items():
            self.assertEqual(len(schema.columns), schema.num_columns, name)
            self.assertEqual(schema.computed_row_size(), schema.row_size, name)

    def test_generated_schemas_match_the_client(self):
        with open(os.path.join(TOOL_DIR, "rflib", "schemas.py"), encoding="utf-8") as f:
            self.assertEqual(f.read(), recparse.emit_schemas_module(REC_DIR), "run `raceforge.py schemas --write`")


class KnownLayoutTests(unittest.TestCase):
    def test_layouts_the_client_aborts_on(self):
        expected = {
            "ChrRaces": (69, 276, False),
            "CharBaseInfo": (2, 2, True),
            "CharStartOutfit": (77, 296, False),
            "CharSections": (10, 40, False),
            "CharHairGeosets": (6, 24, False),
            "CharacterFacialHairStyles": (8, 32, True),
            "NameGen": (4, 16, False),
            "BarberShopStyle": (40, 160, False),
            "EmotesTextSound": (5, 20, False),
            "VocalUISounds": (7, 28, False),
            "SkillRaceClassInfo": (8, 32, False),
            "SkillLineAbility": (14, 56, False),
            "TalentTab": (24, 96, False),
            "DanceMoves": (24, 96, False),
            "Faction": (57, 228, False),
            "FactionTemplate": (14, 56, False),
            "FactionGroup": (20, 80, False),
            "HelmetGeosetVisData": (8, 32, False),
            "CreatureDisplayInfo": (16, 64, False),
            "CreatureModelData": (28, 112, False),
        }

        for name, (columns, row_size, generated) in expected.items():
            schema = schema_access.get(name)
            self.assertEqual((schema.num_columns, schema.row_size, schema.generated_id), (columns, row_size, generated), name)

    def test_chrraces_columns(self):
        schema = schema_access.get("ChrRaces")
        self.assertEqual(schema.index("factionID"), 2)
        self.assertEqual(schema.index("clientPrefix"), 6)
        self.assertEqual(schema.index("baseLanguage"), 7)
        self.assertEqual(schema.index("clientFileString"), 11)
        self.assertEqual(schema.index("cinematicSequenceID"), 12)
        self.assertEqual(schema.index("alliance"), 13)
        self.assertEqual(schema.index("name[0]"), 14)
        self.assertEqual(schema.index("requiredExpansion"), 68)
        self.assertEqual(schema.localized_fields(), ["name", "nameFemale", "nameMale"])

    def test_byte_columns(self):
        outfit = schema_access.get("CharStartOutfit")
        self.assertEqual([c.size for c in outfit.columns[:5]], [4, 1, 1, 1, 1])
        self.assertEqual([c.kind for c in schema_access.get("CharBaseInfo").columns], ["byte", "byte"])


if __name__ == "__main__":
    unittest.main()
