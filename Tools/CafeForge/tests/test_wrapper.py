"""The café spell wrapper (section 6.3): cafe.json's RaceForge SpellDefs inside {"spell", "castMs", "durationMs",
"range"}, the three wrapper keys resolved by value from the SpellCastTimes, SpellDuration and SpellRange copies, and
the rows RaceForge's spells.build_row makes of them (with their spell_dbc SQL read back field for field).

    python3 -I Tools/CafeForge/tests/run_tests.py
"""

import copy
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.dont_write_bytecode = True
for path in (TOOL, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

import cafe_synth as S  # noqa: E402
from cflib import catalog, config, dbcrows, schemas  # noqa: E402

from rflib import spells as spellmod  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402

DOC = catalog.load()
CFG = config.from_doc(DOC)
PULL_SHOT = 100903     # a timed step: a channel
GRIND_BEANS = 100901   # a tap step: a cast
ON_SHIFT = 100900
BUZZ = 100930


def wrapper(spell_id):
    return copy.deepcopy(next(w for w in DOC["dbc"]["spells"] if w["spell"]["id"] == spell_id))


def resolved(tables=None):
    indices, problems = dbcrows.resolve_indices(CFG, tables or S.stock_tables())
    return indices, problems


class Wrapper(unittest.TestCase):
    def refused(self, data, text):
        with self.assertRaises(config.ConfigError) as cm:
            config.parse_wrapper(data, 3)
        self.assertIn(text, str(cm.exception))

    def test_every_cafe_json_spell_parses(self):
        self.assertEqual(sorted(s.id for s in CFG.spells), catalog.CAFE_SPELLS)
        self.assertEqual({s.data["cast_by"] for s in CFG.spells}, {"server"})
        self.assertEqual({s.range for s in CFG.spells}, {"self"})

    def test_wrapper_key_inside_spell_is_refused(self):
        data = wrapper(PULL_SHOT)
        data["spell"]["castMs"] = 0
        self.refused(data, "unknown keys ['castMs']")

    def test_unknown_column_in_fields_is_refused(self):
        data = wrapper(PULL_SHOT)
        data["spell"]["fields"]["attributesEx9"] = 1
        self.refused(data, "fields.attributesEx9: Spell.dbc has no such column")

    def test_unknown_wrapper_key_is_refused(self):
        data = wrapper(PULL_SHOT)
        data["cast"] = 0
        self.refused(data, "unknown keys ['cast']")

    def test_resolved_column_in_fields_is_refused(self):
        for key, column in config.RESOLVED.items():
            data = wrapper(PULL_SHOT)
            data["spell"]["fields"][column] = 1
            self.refused(data, "fields.%s is set by CafeForge from the wrapper's %s" % (column, key))

    def test_wrapper_values_are_checked(self):
        for key, value, text in (("castMs", -1, "castMs must be"), ("durationMs", -2, "durationMs must be"),
                                 ("castMs", 1.5, "castMs must be"), ("range", "melee", "range must be")):
            data = wrapper(PULL_SHOT)
            data[key] = value
            self.refused(data, text)
        data = wrapper(PULL_SHOT)
        del data["spell"]
        self.refused(data, "needs \"spell\"")

    def test_cast_by_must_be_server(self):
        data = wrapper(PULL_SHOT)
        data["spell"]["cast_by"] = "race"
        self.refused(data, "cast_by must be \"server\"")

    def test_managed_and_text_columns_stay_raceforge_s(self):
        data = wrapper(PULL_SHOT)
        data["spell"]["fields"]["spellIconID"] = 1
        self.refused(data, "fields.spellIconID: set by RaceForge")


class Resolve(unittest.TestCase):
    def test_exact_rows(self):
        indices, problems = resolved()
        self.assertEqual(problems, [])
        self.assertTrue(all(i.exact for i in indices.values()))
        self.assertEqual(indices[("castingTimeIndex", 0)].index, 1)
        self.assertEqual(indices[("castingTimeIndex", 1500)].index, 6)
        self.assertEqual(indices[("durationIndex", 0)].index, 0)     # no aura: no duration row
        self.assertEqual(indices[("durationIndex", -1)].index, 6)    # On Shift: infinite
        self.assertEqual(indices[("durationIndex", 3600000)].index, 5)
        self.assertEqual(indices[("rangeIndex", "self")].index, 1)

    def test_nearest_cast_time_with_a_warning(self):
        tables = S.stock_tables(cast_times=tuple(r for r in S.CAST_TIMES if r[1] != 1200))
        indices, problems = resolved(tables)
        self.assertEqual(problems, [])
        idx = indices[("castingTimeIndex", 1200)]
        self.assertFalse(idx.exact)
        self.assertEqual((idx.index, idx.value), (4, 1000))           # 1000 is 200 ms away, 1500 is 300
        self.assertIn("the nearest: no exact row", idx.text())

    def test_per_level_rows_are_not_taken(self):
        tables = S.stock_tables()
        t = tables["SpellCastTimes"]
        row = S.new_row(t, 9)
        t.set(row, "base", 1700)
        t.set(row, "perLevel", 10)
        t.rows.append(row)
        indices, _ = resolved(tables)
        self.assertNotIn(9, [i.index for i in indices.values() if i.table == "SpellCastTimes"])

    def test_missing_rows_are_problems(self):
        tables = S.stock_tables(durations=tuple(r for r in S.DURATIONS if r[1] != -1))
        _, problems = resolved(tables)
        self.assertIn("SpellDuration.dbc has no row for an infinite (-1) duration", problems)
        tables = S.stock_tables()
        tables["SpellRange"].rows = [r for r in tables["SpellRange"].rows if r[0] != 1]
        _, problems = resolved(tables)
        self.assertIn("SpellRange.dbc has no row for a \"self\" range (0 yd)", problems)
        tables = S.stock_tables()
        del tables["SpellCastTimes"]
        _, problems = resolved(tables)
        self.assertTrue(any(p.startswith("SpellCastTimes.dbc is in no patch") for p in problems), problems)

    def test_another_combination_must_mean_the_same(self):
        indices, _ = resolved()
        other = S.stock_tables(cast_times=tuple((i, 1700 if ms == 1500 else ms) for i, ms in S.CAST_TIMES))
        problems = dbcrows.index_problems(indices, other, "no packs")
        self.assertEqual(problems, ["SpellCastTimes 6 holds another value in the copy no packs read (castMs 1500)"])
        self.assertEqual(dbcrows.index_problems(indices, S.stock_tables(), "no packs"), [])


class Rows(unittest.TestCase):
    def setUp(self):
        indices, _ = resolved()
        self.defs = dbcrows.spell_defs(CFG, indices)
        self.table = DbcTable.empty(schemas.get("Spell"))

    def row(self, spell_id):
        return spellmod.build_row(self.table, self.defs[spell_id])

    def test_resolved_into_fields_then_parse_spell(self):
        pull = self.defs[PULL_SHOT]
        self.assertEqual((pull.fields["castingTimeIndex"], pull.fields["durationIndex"], pull.fields["rangeIndex"]),
                         (1, 3, 1))
        grind = self.defs[GRIND_BEANS]
        self.assertEqual((grind.fields["castingTimeIndex"], grind.fields["durationIndex"]), (6, 0))
        self.assertEqual(self.defs[ON_SHIFT].fields["durationIndex"], 6)

    def test_channel_row(self):
        t, row = self.table, self.row(PULL_SHOT)
        self.assertEqual(t.get_str(row, "name[0]"), "Pull Shot")
        self.assertEqual(t.get_str(row, "name[1]"), "")                         # text_locales ["enUS"]
        self.assertEqual(t.get(row, "spellVisualID[0]"), 654)
        self.assertEqual(t.get(row, "spellIconID"), 19301)
        self.assertEqual(t.get(row, "attributes"), 0x10000000)                   # A0_PEACEFUL
        self.assertEqual(t.get(row, "attributesEx"), 0x4)                        # a channel
        self.assertEqual(t.get(row, "attributesExD"), 0x08000000)                # the forced cast bar
        self.assertEqual((t.get(row, "interruptFlags"), t.get(row, "channelInterruptFlags")), (0x0B, 0x0A))
        self.assertEqual((t.get(row, "effect[0]"), t.get(row, "implicitTargetA[0]")), (3, 1))
        self.assertEqual((t.get(row, "castingTimeIndex"), t.get(row, "durationIndex"), t.get(row, "rangeIndex")),
                         (1, 3, 1))
        self.assertEqual(t.get(row, "procChance"), 101)                          # RaceForge's defaults

    def test_buff_row(self):
        t, row = self.table, self.row(BUZZ)
        self.assertEqual((t.get(row, "effect[0]"), t.get(row, "effectAura[0]")), (6, 4))
        self.assertEqual(t.get(row, "durationIndex"), 5)
        self.assertEqual(t.get(row, "attributesExC"), 0x00100000)

    def test_spell_sql_reads_back_the_same(self):
        rows = [self.row(s.id) for s in CFG.spells]
        sql = spellmod.spell_sql(self.table, rows)
        back = spellmod.parse_sql_rows(sql, "spell_dbc")
        self.assertEqual(sorted(back), catalog.CAFE_SPELLS)
        for row in rows:
            self.assertEqual(spellmod.compare_row(self.table, row, back[row[0]]), [])


if __name__ == "__main__":
    unittest.main()
