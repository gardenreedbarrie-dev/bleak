"""rflib/remap.py: existing characters onto the merged tables. The mapping (Death Knight skin and face pairs, hair
colours, the clones), and the SQL run on a model of the characters database in SQLite: the remap, run twice, the
corpses, the restore that only touches values still remapped, the marks rollback and the hidden-row counts."""

import os
import re
import sqlite3
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from rflib import appearance as ap  # noqa: E402
from rflib import remap, schema_access  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402
from tests import synth_customize as sc  # noqa: E402


def table(package: bool) -> DbcTable:
    return DbcTable.from_bytes(sc.tables(package, realm=not package)["CharSections"], schema_access.get("CharSections"))


def renamed(cs: DbcTable) -> DbcTable:
    """The package's rows as customize writes them: on Character\\Ascension\\ names."""
    for row in cs.rows:
        for slot in range(3):
            name = cs.get_str(row, f"textureName[{slot}]")

            if name:
                cs.set_str(row, f"textureName[{slot}]", ap.ascension_name(name))

    return cs


def merged() -> DbcTable:
    cs = renamed(table(True))
    clones = []

    for clone, source in ap.CLONES.items():
        for row in cs.rows:
            if cs.get(row, "raceID") == source:
                new = list(row)
                cs.set(new, "raceID", clone)
                clones.append(new)

    cs.rows += clones
    return cs


def lite(sql: str) -> str:
    """MySQL's DROP TEMPORARY TABLE (which, unlike DROP TABLE, never commits) as SQLite has it."""
    return sql.replace("DROP TEMPORARY TABLE", "DROP TABLE")


CHARACTERS = """CREATE TABLE `characters` (`guid` INT PRIMARY KEY, `race` INT, `class` INT, `gender` INT, `skin` INT,
`face` INT, `hairStyle` INT, `hairColor` INT, `facialStyle` INT, `at_login` INT DEFAULT 0);
CREATE TABLE `corpse` (`guid` INT PRIMARY KEY, `bytes1` INT, `bytes2` INT);"""


def corpse_bytes(race, gender, skin, face, style, colour, facial):
    return (race << 8) | (gender << 16) | (skin << 24), face | (style << 8) | (colour << 16) | (facial << 24)


class MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = table(False)
        cls.merged = merged()
        cls.maps = remap.compute_all(cls.base, cls.merged)

    @staticmethod
    def maps_with_tables():
        """The synthetic realm and package with the hair and features geosets."""
        realm, package = sc.tables(False, realm=True), sc.tables(True)
        load = {n: (DbcTable.from_bytes(realm[n], schema_access.get(n)),
                    DbcTable.from_bytes(package[n], schema_access.get(n)))
                for n in ("CharHairGeosets", "CharacterFacialHairStyles")}
        return remap.compute_all(table(False), merged(), clones={},
                                 base_hair=load["CharHairGeosets"][0], merged_hair=load["CharHairGeosets"][1],
                                 base_facial=load["CharacterFacialHairStyles"][0],
                                 merged_facial=load["CharacterFacialHairStyles"][1])

    def test_death_knight_pairs(self):
        m = self.maps[(10, 0, True)]
        # old DK skin 4 (texture _04) is new skin 8; its faces 0 and 2 exist there, face 1 does not
        self.assertEqual(m.pairs[(4, 0)], (8, 0, True))
        self.assertEqual(m.pairs[(4, 2)], (8, 2, True))
        self.assertEqual(m.pairs[(4, 1)], (8, 0, False), "the nearest face on the Death Knight skin; customize")
        self.assertEqual(m.pairs[(6, 2)], (10, 2, True))

    def test_players_keep_their_numbers(self):
        m = self.maps[(10, 0, False)]
        self.assertEqual(m.moved, {})
        self.assertEqual(m.pairs[(3, 2)], (3, 2, True))
        self.assertNotIn((4, 0), m.pairs, "a player never had a Death Knight skin")

    def test_hair_colours(self):
        self.assertEqual(self.maps[(1, 1, False)].hair_colours, {1: 2, 2: 1}, "the package swapped them")
        self.assertEqual(self.maps[(1, 1, True)].hair_colours, {1: 2, 2: 1})
        self.assertEqual(self.maps[(10, 1, False)].hair_colours, {}, "Death Knight colour 3 stays 3")

    def test_clones_take_their_sources_mapping(self):
        for clone, source in ap.CLONES.items():
            for sex in (0, 1):
                for dk in (False, True):
                    self.assertEqual(self.maps[(clone, sex, dk)].pairs, self.maps[(source, sex, dk)].pairs)

        self.assertEqual(remap.clone_problems(self.base), [])
        broken = table(False)
        broken.rows = [r for r in broken.rows if not (broken.get(r, "raceID") == 15 and broken.get(r, "baseSection") == 1)]
        self.assertTrue(remap.clone_problems(broken))

    def test_original_names(self):
        name = "Character\\BloodElf\\Male\\BloodElfMaleSkin00_00.blp"
        for wrapped in (name, ap.ascension_name(name), ap.rebuilt_name("0123456789abc", name),
                        "Character\\BleakholdSkins\\HighElf\\0123456789\\" + ap.ascension_name(name)):
            self.assertEqual(ap.original_name(wrapped), name, wrapped)


class SqlTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(CHARACTERS)
        people = [
            # guid, race, class, gender, skin, face, style, colour, facial
            (1, 10, 6, 0, 4, 0, 1, 0, 2),  # Blood Elf Death Knight: skin 4 face 0 -> 8, 0
            (2, 10, 6, 0, 4, 1, 0, 1, 0),  # face 1 does not exist on the new Death Knight skin: 8, 0 + customize
            (3, 10, 2, 0, 3, 2, 2, 2, 1),  # a paladin: unchanged
            (4, 1, 1, 1, 2, 1, 0, 1, 0),  # Human female: hair colour 1 -> 2
            (5, 1, 1, 1, 2, 1, 0, 2, 0),  # and 2 -> 1 (a swap, not a chain)
            (6, 15, 6, 1, 5, 2, 0, 0, 0),  # High Elf Death Knight: Blood Elf's mapping, 5 -> 9
        ]
        self.db.executemany("INSERT INTO characters VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)", people)
        b1, b2 = corpse_bytes(10, 0, 4, 0, 1, 0, 2)
        self.db.execute("INSERT INTO corpse VALUES (1, ?, ?)", (b1, b2))
        b1, b2 = corpse_bytes(1, 1, 2, 1, 0, 1, 0)
        self.db.execute("INSERT INTO corpse VALUES (4, ?, ?)", (b1, b2))
        maps = remap.compute_all(table(False), merged())
        self.db.executescript(remap.tables_sql())
        self.remap = lite(remap.remap_sql(maps, "run1"))
        self.restore = remap.restore_sql("run1")

    def tearDown(self):
        self.db.close()

    def looks(self):
        return {row[0]: row[1:] for row in self.db.execute(
            "SELECT guid, skin, face, hairStyle, hairColor, facialStyle, at_login FROM characters ORDER BY guid")}

    def corpses(self):
        return {g: (b1, b2) for g, b1, b2 in self.db.execute("SELECT guid, bytes1, bytes2 FROM corpse")}

    def test_remap_twice_then_restore(self):
        before = self.looks()
        corpses_before = self.corpses()
        self.db.executescript(self.remap)
        after = self.looks()
        self.assertEqual(after[1], (8, 0, 1, 0, 2, 0))
        self.assertEqual(after[2], (8, 0, 0, 1, 0, remap.AT_LOGIN_CUSTOMIZE))
        self.assertEqual(after[3], before[3])
        self.assertEqual(after[4][3], 2)
        self.assertEqual(after[5][3], 1)
        self.assertEqual(after[6][:2], (9, 2))
        self.assertEqual(self.corpses()[1], corpse_bytes(10, 0, 8, 0, 1, 0, 2))
        self.assertEqual(self.corpses()[4], corpse_bytes(1, 1, 2, 1, 0, 2, 0))

        self.db.executescript(self.remap)
        self.assertEqual(self.looks(), after, "a second run changes nothing")

        # a player changes their look after the remap: the restore leaves that column alone
        self.db.execute("UPDATE characters SET skin = 9 WHERE guid = 1")
        self.db.executescript(self.restore)
        restored = self.looks()
        self.assertEqual(restored[1][0], 9, "changed since: kept")
        self.assertEqual(restored[1][1:5], before[1][1:5])

        for guid in (3, 4, 5, 6):
            self.assertEqual(restored[guid][:5], before[guid][:5], guid)

        self.assertEqual(restored[2][5], 0, "the customize the remap gave is taken back with the look")
        self.assertEqual(self.corpses(), corpses_before)
        self.db.executescript(self.restore)
        self.assertEqual(self.looks(), restored, "a second restore changes nothing")

    def test_restore_takes_back_only_the_customize_the_remap_set(self):
        # guid 2 (no exact face on the new Death Knight skin) gets a customize from the remap; guid 7 the same, but
        # it had one waiting already (a GM's, the Appearance Artist's): that one stays after the restore
        self.db.execute("INSERT INTO characters VALUES (7, 10, 6, 0, 4, 1, 0, 1, 0, 9)")
        before = self.looks()
        self.db.executescript(self.remap)
        after = self.looks()
        self.assertEqual(after[2][5], remap.AT_LOGIN_CUSTOMIZE)
        self.assertEqual(after[7][5], 9)
        self.assertEqual(self.db.execute(f"SELECT guid FROM {remap.SET_CUSTOMIZE} WHERE run = 'run1'").fetchall(),
                         [(2,)], "only the character whose bit the remap set")
        self.db.executescript(self.remap)
        self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {remap.SET_CUSTOMIZE}").fetchone(), (1,),
                         "a second run notes nothing more")
        self.db.executescript(self.restore)
        restored = self.looks()
        self.assertEqual(restored[2], before[2], "look and at_login of before")
        self.assertEqual(restored[2][5], 0)
        self.assertEqual(restored[7][5], 9, "a customize that waited before the remap stays (and the 1 with it)")
        self.db.executescript(self.restore)
        self.assertEqual(self.looks(), restored, "a second restore changes nothing")

    def test_a_used_customize_is_not_taken_back_twice(self):
        self.db.executescript(self.remap)
        self.db.execute("UPDATE characters SET at_login = 0 WHERE guid = 2")  # used at the next login
        self.db.executescript(self.restore)
        self.assertEqual(self.looks()[2][5], 0, "nothing to take off; never below zero")

    def test_the_remap_file_commits_nothing_on_its_own(self):
        # MySQL commits implicitly at every CREATE / DROP / ALTER TABLE that is not TEMPORARY: inside the transaction
        # customize.sh wraps the file in, one would commit the work before it and leave the rest to fail alone
        maps = remap.compute_all(table(False), merged())
        sql = remap.remap_sql(maps, "run1")
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        ddl = re.compile(r"^(?:--[^\n]*\n)*\s*(CREATE|DROP|ALTER|RENAME|TRUNCATE)\b(?!\s+TEMPORARY)", re.I)
        self.assertFalse([s[:80] for s in statements if ddl.match(s)])
        self.assertIn("DROP TEMPORARY TABLE IF EXISTS `bh_remap_pair`", sql)
        self.assertNotIn("DROP TABLE", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS `bh_appearance_backup`", remap.tables_sql())
        restore = remap.restore_sql("run1")
        first_dml = next(i for i, s in enumerate(restore.split(";")) if re.search(r"^\s*UPDATE", s, re.M))
        self.assertFalse([s for s in restore.split(";")[first_dml:] if ddl.match(s.strip())],
                         "the restore's creates come before its first change")

    def test_marks_rollback(self):
        self.db.execute("UPDATE characters SET facialStyle = 1 * 3 * 4 + 2, face = 81 WHERE guid = 3")
        self.db.execute("UPDATE corpse SET bytes2 = ? WHERE guid = 1", (corpse_bytes(10, 0, 4, 81, 1, 0, 14)[1],))
        self.db.executescript(remap.marks_rollback_sql({(10, 0): 3}))
        self.assertEqual(self.looks()[3][1], 1)
        self.assertEqual(self.looks()[3][4], 2)
        self.assertEqual(self.corpses()[1][1], corpse_bytes(10, 0, 4, 1, 1, 0, 2)[1])

    def counts(self, sql):
        return [self.db.execute(line).fetchone() for line in sql.splitlines() if line.startswith("SELECT")]

    def test_hidden_counts(self):
        counts = self.counts(remap.hidden_count_sql([(10, 0, "skin", 3), (1, 1, "face", 1, 2)]))
        self.assertEqual([c[:4] for c in counts], [(1, 1, "face", 1), (10, 0, "skin", 3)])
        self.assertEqual([c[-1] for c in counts], [2, 1])
        counts = self.counts(remap.hidden_count_sql([(1, 1, "face", 1, 3)]))
        self.assertEqual([c[-1] for c in counts], [0], "face 1 is hidden on skin 3 only; both are on skin 2")

        with self.assertRaisesRegex(ValueError, "skin colour"):
            remap.hidden_count_sql([(1, 1, "face", 1)])

    def test_a_face_hidden_on_one_skin_counts_only_that_skin(self):
        # the curation's Draenei male faces at skin 16 (every variation): an ordinary Draenei male is not on them
        hidden = [(11, 0, "face", v, 16) for v in range(20)]
        sql = remap.hidden_count_sql(hidden)
        self.db.execute("DELETE FROM characters")
        self.db.execute("INSERT INTO characters VALUES (10, 11, 1, 0, 3, 2, 0, 0, 0, 0)")
        self.assertEqual(sum(c[-1] for c in self.counts(sql)), 0, "skin 3 face 2: nothing hidden")
        self.db.execute(f"INSERT INTO characters VALUES (11, 11, 1, 0, 16, {2 + ap.EYE_STRIDE}, 0, 0, 0, 0)")
        counts = self.counts(sql)
        self.assertEqual(sum(c[-1] for c in counts), 1, "skin 16, face 2 with an eye: on a hidden row")
        self.assertEqual([c[:4] for c in counts if c[-1]], [(11, 0, "face", 2)])
        self.assertEqual(len(counts), 20, "one count per face")

    def test_run_id_is_checked(self):
        with self.assertRaises(ValueError):
            remap.restore_sql("x'; DROP TABLE characters; --")


def meaning_tables(values: int, blank: int, styles: int = 2):
    """A Human male: features 0..values-1 (value `blank` blank: no textures, no geosets) and hair styles 0..styles-1,
    each at hair colours 0 and 1. Returns (CharSections, CharHairGeosets, CharacterFacialHairStyles)."""
    cs = sc.synth.Packer("CharSections")
    hair = sc.synth.Packer("CharHairGeosets")
    facial = sc.synth.Packer("CharacterFacialHairStyles")
    ids = iter(range(1, 1000))
    feature = 1

    for value in range(values):
        is_blank = value == blank
        facial.add(raceID=1, sexID=0, variationID=value, **{"geoset[0]": 0 if is_blank else feature})

        for colour in (0, 1):
            names = ("", "") if is_blank else (f"Character\\Human\\Male\\HumanMaleFacialLowerHair{feature:02d}_"
                                               f"{colour:02d}.blp", "")
            cs.add(id=next(ids), raceID=1, sexID=0, baseSection=ap.FEATURES, flags=0x1, variationIndex=value,
                   colorIndex=colour, **{f"textureName[{i}]": n for i, n in enumerate(names)})

        feature += 0 if is_blank else 1

    for style in range(styles):
        hair.add(id=style + 1, raceID=1, sexID=0, variationID=style, geosetID=style + 1, showscalp=1)

        for colour in (0, 1):
            cs.add(id=next(ids), raceID=1, sexID=0, baseSection=ap.HAIR, flags=0x1, variationIndex=style,
                   colorIndex=colour, **{"textureName[0]": f"Character\\Human\\Hair00_{colour:02d}.blp"})

    def load(packer):
        return DbcTable.from_bytes(packer.pack(), schema_access.get(packer.name))

    return load(cs), load(hair), load(facial)


class MeaningTests(unittest.TestCase):
    """Hair styles and features keep their meaning, or the change is reported and refused (or moved, accepted)."""

    def maps(self, base, merged):
        (b_cs, b_hair, b_facial), (m_cs, m_hair, m_facial) = base, merged
        return remap.compute_all(b_cs, m_cs, races=(1,), clones={}, base_hair=b_hair, merged_hair=m_hair,
                                 base_facial=b_facial, merged_facial=m_facial)

    def test_the_synthetic_package_changes_nothing(self):
        for m in MappingTests.maps_with_tables().values():
            self.assertEqual((m.changed_styles, m.changed_features), ({}, {}), (m.race, m.sex, m.dk))

    def test_a_blank_features_value_moving_from_9_to_18_is_refused_or_moved(self):
        # the package inserts nine features at 9: the old blank 9 is now 18, and 9 is a beard
        maps = self.maps(meaning_tables(10, 9), meaning_tables(19, 18))
        m = maps[(1, 0, False)]
        self.assertEqual(sorted(m.changed_features), [9])
        why, same = m.changed_features[9]
        self.assertIn("texture 0 none ->", why)
        self.assertEqual(same, 18, "the merged value that is blank like the old 9")
        self.assertEqual(m.changed_styles, {})

        problems = remap.meaning_problems(maps, set())
        self.assertEqual(len(problems), 2, problems)  # a player and a Death Knight
        self.assertIn("features value 9 changed its meaning", problems[0])
        self.assertIn("accepted_changes", problems[0])
        self.assertEqual(m.features, {}, "not accepted: nothing moves")

        self.assertEqual(remap.meaning_problems(maps, {(1, 0, "feature", 9)}), [])
        self.assertEqual(m.features, {9: (18, False)})

        db = sqlite3.connect(":memory:")
        db.executescript(CHARACTERS)
        db.executemany("INSERT INTO characters VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                       [(1, 1, 1, 0, 0, 0, 1, 1, 9), (2, 1, 6, 0, 0, 0, 1, 1, 9), (3, 1, 1, 0, 0, 0, 1, 1, 3)])
        db.execute("INSERT INTO corpse VALUES (1, ?, ?)", corpse_bytes(1, 0, 0, 0, 1, 1, 9))
        db.executescript(remap.tables_sql() + lite(remap.remap_sql(maps, "r")))
        looks = {g: (f, a) for g, f, a in db.execute("SELECT guid, facialStyle, at_login FROM characters")}
        self.assertEqual(looks, {1: (18, 0), 2: (18, 0), 3: (3, 0)}, "the blank beard follows, nothing else moves")
        self.assertEqual(db.execute("SELECT bytes1, bytes2 FROM corpse").fetchone(), corpse_bytes(1, 0, 0, 0, 1, 1, 18))
        db.executescript(remap.restore_sql("r"))
        self.assertEqual([r[0] for r in db.execute("SELECT facialStyle FROM characters ORDER BY guid")], [9, 9, 3])
        self.assertEqual(db.execute("SELECT bytes2 FROM corpse").fetchone()[0], corpse_bytes(1, 0, 0, 0, 1, 1, 9)[1])
        db.close()

        counted = remap.hidden_count_sql([], [(1, 0, "facialStyle", 9)])
        self.assertIn("`facialStyle` = 9", counted)

    def test_an_accepted_change_without_an_equal_value_gets_a_customize(self):
        maps = self.maps(meaning_tables(10, 9), meaning_tables(10, -1))  # 9 is a beard now, no blank anywhere
        self.assertIsNone(maps[(1, 0, False)].changed_features[9][1])
        self.assertEqual(remap.meaning_problems(maps, {(1, 0, "feature", 9)}), [])
        db = sqlite3.connect(":memory:")
        db.executescript(CHARACTERS)
        db.execute("INSERT INTO characters VALUES (1, 1, 1, 0, 0, 0, 1, 1, 9, 0)")
        db.executescript(remap.tables_sql() + lite(remap.remap_sql(maps, "r")))
        self.assertEqual(db.execute("SELECT facialStyle, at_login FROM characters").fetchone(),
                         (9, remap.AT_LOGIN_CUSTOMIZE))
        db.close()

    def counts_after_remap(self, maps, people):
        """remap_characters.sql, then count_hidden.sql with the accepted changes customize counts, on one database."""
        from rflib import realm_customize as rc

        db = sqlite3.connect(":memory:")
        db.executescript(CHARACTERS)
        db.executemany("INSERT INTO characters VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)", people)
        db.executescript(remap.tables_sql() + lite(remap.remap_sql(maps, "r")))
        sql = remap.hidden_count_sql([], rc.accepted_looks(maps))
        counts = [db.execute(line).fetchone() for line in sql.splitlines() if line.startswith("SELECT")]
        looks = {g: (f, a) for g, f, a in db.execute("SELECT guid, facialStyle, at_login FROM characters")}
        db.close()
        return sql, counts, looks

    def test_count_hidden_is_zero_after_the_remap_of_a_kept_value(self):
        # 9 is a beard now and no merged value means the old 9: the characters stay on 9 with a customize
        maps = self.maps(meaning_tables(10, 9), meaning_tables(10, -1))
        self.assertEqual(remap.meaning_problems(maps, {(1, 0, "feature", 9)}), [])
        sql, counts, looks = self.counts_after_remap(maps, [(1, 1, 1, 0, 0, 0, 1, 1, 9), (2, 1, 6, 0, 0, 0, 1, 1, 9)])
        self.assertEqual(looks, {1: (9, remap.AT_LOGIN_CUSTOMIZE), 2: (9, remap.AT_LOGIN_CUSTOMIZE)})
        self.assertEqual([c for c in counts if c[-1]], [], sql)
        self.assertNotIn("`facialStyle` = 9", sql, "a kept value is not counted")

    def test_count_hidden_is_zero_after_the_remap_of_a_moved_value(self):
        maps = self.maps(meaning_tables(10, 9), meaning_tables(19, 18))
        self.assertEqual(remap.meaning_problems(maps, {(1, 0, "feature", 9)}), [])
        sql, counts, looks = self.counts_after_remap(maps, [(1, 1, 1, 0, 0, 0, 1, 1, 9), (2, 1, 6, 0, 0, 0, 1, 1, 9),
                                                            (3, 1, 1, 0, 0, 0, 1, 1, 3)])
        self.assertEqual(looks, {1: (18, 0), 2: (18, 0), 3: (3, 0)})
        self.assertEqual(len(counts), 2, "one count for players, one for Death Knights")
        self.assertIn("`facialStyle` = 9 AND `class` <> 6", sql)
        self.assertIn("`facialStyle` = 9 AND `class` = 6", sql)
        self.assertEqual([c for c in counts if c[-1]], [], sql)

    def test_a_change_accepted_only_for_death_knights_counts_only_death_knights(self):
        maps = self.maps(meaning_tables(10, 9), meaning_tables(19, 18))
        remap.meaning_problems(maps, {(1, 0, "feature", 9)})
        player = maps[(1, 0, False)]
        player.features.clear()  # as if the change were only in the Death Knight mapping
        sql, counts, looks = self.counts_after_remap(maps, [(1, 1, 1, 0, 0, 0, 1, 1, 9), (2, 1, 6, 0, 0, 0, 1, 1, 9)])
        self.assertEqual(looks, {1: (9, 0), 2: (18, 0)}, "the remap moves only the Death Knight")
        self.assertEqual(len(counts), 1, sql)
        self.assertEqual([c for c in counts if c[-1]], [], "the player on 9 is not a Death Knight")

    def test_a_swap_of_accepted_values_is_not_counted(self):
        from rflib import realm_customize as rc

        maps = self.maps(meaning_tables(10, 9), meaning_tables(19, 18))
        m = maps[(1, 0, False)]
        m.features = {4: (5, False), 5: (4, False), 6: (7, False), 9: (9, True)}
        self.assertEqual(rc.accepted_looks({(1, 0, False): m}), [(1, 0, "facialStyle", 6, False)],
                         "4 and 5 swap (each holds the other's characters), 9 is kept: only 6 is empty afterwards")

    def test_a_missing_or_regeoset_hair_style_is_refused(self):
        base = meaning_tables(3, 2, styles=3)
        cs, hair, facial = meaning_tables(3, 2, styles=3)
        cs.rows = [r for r in cs.rows if not (cs.get(r, "baseSection") == ap.HAIR and cs.get(r, "variationIndex") == 2)]
        hair.rows = [r for r in hair.rows if hair.get(r, "variationID") != 2]
        hair.set(hair.rows[1], "geosetID", 7)  # style 1 now shows another geoset
        maps = self.maps(base, (cs, hair, facial))
        m = maps[(1, 0, False)]
        self.assertEqual(m.missing_styles, [2])
        self.assertEqual(sorted(m.changed_styles), [1, 2])
        self.assertIn("geosets (2, 1) -> (7, 1)", m.changed_styles[1][0])
        self.assertIn("missing", m.changed_styles[2][0])
        problems = remap.meaning_problems(maps, set())
        self.assertTrue(any("hair style 2 changed its meaning" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
