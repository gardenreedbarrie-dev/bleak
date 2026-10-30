"""End to end: synthetic stock DBCs -> raceforge.py build -> patched DBCs, SQL, MPQ and report."""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)
MPQPACK_DIR = os.path.join(os.path.dirname(TOOL_DIR), "MpqPack")

for path in (TOOL_DIR, MPQPACK_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from rflib import schema_access, spells as spellmod  # noqa: E402
from rflib.dbc import DbcTable, to_signed  # noqa: E402
from tests import synth  # noqa: E402

HIGH_ELF_BIT = 1 << 21
EREDAR_BIT = 1 << 22


def run_tool(*args):
    return subprocess.run([sys.executable, "-I", os.path.join(TOOL_DIR, "raceforge.py"), *args], capture_output=True, text=True)


def read(out_dir, name, kind="client"):
    folder = os.path.join(out_dir, "client", "DBFilesClient") if kind == "client" else os.path.join(out_dir, "server", "dbc")
    return DbcTable.read(os.path.join(folder, f"{name}.dbc"), schema_access.get(name))


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.stock = os.path.join(cls.tmp.name, "stock")
        cls.out = os.path.join(cls.tmp.name, "out")
        synth.write_folder(cls.stock, lower_case_names=True)  # extracted names vary in case
        cls.result = run_tool("build", "--dbc", cls.stock, "--out", cls.out, "--mpq")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_build_succeeds(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertRegex(self.result.stdout, r"\d+ checks, 0 failed")

        with open(os.path.join(self.out, "report.txt"), encoding="utf-8") as f:
            report = f.read()

        self.assertNotIn("[FAIL]", report)

    def test_chr_races_rows(self):
        races = read(self.out, "ChrRaces")
        rows = races.by_id()
        stock = DbcTable.read(os.path.join(self.stock, "chrraces.dbc"), schema_access.get("ChrRaces")).by_id()
        high_elf, eredar = rows[22], rows[23]

        self.assertEqual(len(rows), 23)
        self.assertEqual(races.get_str(high_elf, "clientFileString"), "HighElf")
        self.assertEqual(races.get_str(eredar, "clientFileString"), "Eredar")
        self.assertEqual(races.get_str(high_elf, "clientPrefix"), "Be")
        self.assertEqual(races.get_str(eredar, "clientPrefix"), "Dr")
        self.assertEqual(races.get_loc(high_elf, "name")[:9], ["High Elf"] * 9)
        self.assertEqual(races.get_loc(eredar, "name")[:9], ["Eredar"] * 9)

        # Alliance High Elf: Human's faction template, BaseLanguage 7, Alliance column 0; Horde Eredar: Orc's, 1, 1.
        self.assertEqual(races.get(high_elf, "factionID"), synth.faction_template_id(1))
        self.assertEqual((races.get(high_elf, "baseLanguage"), races.get(high_elf, "alliance")), (7, 0))
        self.assertEqual(races.get(eredar, "factionID"), synth.faction_template_id(2))
        self.assertEqual((races.get(eredar, "baseLanguage"), races.get(eredar, "alliance")), (1, 1))

        for row, template in ((high_elf, 10), (eredar, 11)):
            self.assertFalse(races.get(row, "flags") & 1)
            self.assertEqual(races.get(row, "cinematicSequenceID"), 0)
            self.assertEqual((races.get(row, "maleDisplayID"), races.get(row, "femaleDisplayID")), synth.display_ids(template))
            self.assertEqual(races.get(row, "requiredExpansion"), 1)
            self.assertEqual(races.get(row, "resSicknessSpellID"), races.get(stock[template], "resSicknessSpellID"))
            self.assertEqual(races.get_str(row, "hairCustomization"), races.get_str(stock[template], "hairCustomization"))

        # German Blood Elves have gendered names; the High Elf gets its own name there, not "Blutelfe".
        self.assertEqual(races.get_loc(high_elf, "nameFemale")[3], "High Elf")
        self.assertEqual(races.get_loc(high_elf, "nameFemale")[0], "")
        self.assertEqual(races.get_loc(eredar, "nameFemale"), [""] * 16)

    def test_dependent_rows(self):
        base = read(self.out, "CharBaseInfo")
        self.assertEqual([base.get(r, "classID") for r in base.rows if base.get(r, "raceID") == 22], list(synth.CLASSES[10]))
        self.assertEqual([base.get(r, "classID") for r in base.rows if base.get(r, "raceID") == 23], list(synth.CLASSES[11]))

        sections = read(self.out, "CharSections")
        new_rows = [r for r in sections.rows if sections.get(r, "raceID") == 22]
        template_rows = [r for r in sections.rows if sections.get(r, "raceID") == 10]
        self.assertEqual(len(new_rows), len(template_rows))
        self.assertEqual([sections.get_str(r, "textureName[0]") for r in new_rows], [sections.get_str(r, "textureName[0]") for r in template_rows])

        for table_name in ("CharSections", "CharStartOutfit", "CharHairGeosets", "NameGen", "BarberShopStyle", "EmotesTextSound", "VocalUISounds"):
            table = read(self.out, table_name)
            ids = [to_signed(r[0]) for r in table.rows]
            self.assertEqual(len(ids), len(set(ids)), table_name)

        outfits = read(self.out, "CharStartOutfit")
        self.assertEqual(sum(1 for r in outfits.rows if outfits.get(r, "raceID") == 23), 2 * len(synth.CLASSES[11]))

    def test_masks(self):
        skills = read(self.out, "SkillRaceClassInfo")
        by_skill = {skills.get(r, "skillID"): skills.get(r, "raceMask") for r in skills.rows}

        def has(skill, bit):
            return bool(by_skill[skill] & bit)

        self.assertTrue(has(synth.SKILL_COMMON, HIGH_ELF_BIT))
        self.assertFalse(has(synth.SKILL_COMMON, EREDAR_BIT))
        self.assertTrue(has(synth.SKILL_ORCISH, EREDAR_BIT))
        self.assertFalse(has(synth.SKILL_ORCISH, HIGH_ELF_BIT))
        self.assertTrue(has(synth.SKILL_THALASSIAN, HIGH_ELF_BIT))
        self.assertTrue(has(synth.SKILL_DRAENEI_LANGUAGE, EREDAR_BIT))
        # races.json drops the template racials: no bit in Racial - Blood Elf (756) or Racial - Draenei (760)
        self.assertFalse(has(synth.SKILL_RACIAL_BLOODELF, HIGH_ELF_BIT))
        self.assertFalse(has(synth.SKILL_RACIAL_DRAENEI, EREDAR_BIT))
        self.assertEqual(by_skill[synth.SKILL_RACIAL_BLOODELF], 1 << 9)
        self.assertEqual(by_skill[synth.SKILL_RACIAL_DRAENEI], 1 << 10)
        self.assertTrue(has(synth.SKILL_SWORDS, HIGH_ELF_BIT) and has(synth.SKILL_SWORDS, EREDAR_BIT))
        self.assertTrue(has(synth.SKILL_CROSSBOWS, EREDAR_BIT) and not has(synth.SKILL_CROSSBOWS, HIGH_ELF_BIT))
        self.assertTrue(has(synth.SKILL_SHAMAN, EREDAR_BIT))
        self.assertEqual(by_skill[synth.SKILL_RIDING], 0)
        self.assertEqual(by_skill[synth.SKILL_NPC_ONLY], (1 << 11) | (1 << 12))
        self.assertEqual(by_skill[synth.SKILL_EVERYTHING], 0xFFFFFFFF)

        abilities = read(self.out, "SkillLineAbility")
        by_spell = {abilities.get(r, "spell"): abilities.get(r, "raceMask") for r in abilities.rows}
        self.assertTrue(by_spell[32182] & HIGH_ELF_BIT and not by_spell[32182] & EREDAR_BIT)  # Alliance-wide spell
        self.assertTrue(by_spell[2825] & EREDAR_BIT and not by_spell[2825] & HIGH_ELF_BIT)  # Horde-wide spell
        self.assertTrue(by_spell[50000] & EREDAR_BIT and not by_spell[50000] & HIGH_ELF_BIT)  # excluded for the Horde
        self.assertEqual(by_spell[50001], 0)
        self.assertEqual(by_spell[28730], 1 << 9)  # the Blood Elf racial stays the Blood Elf's
        self.assertEqual(by_spell[28880], 1 << 10)

        factions = read(self.out, "Faction")
        rows = factions.by_id()

        def rep(fid, i):
            return factions.get(rows[fid], f"reputationRaceMask[{i}]")

        self.assertTrue(rep(72, 0) & HIGH_ELF_BIT)  # starts like a Human with the Human city
        self.assertFalse(rep(911, 0) & HIGH_ELF_BIT)  # not with the Blood Elf city's racial standing
        self.assertTrue(rep(911, 2) & HIGH_ELF_BIT)  # but as an Alliance race there
        self.assertTrue(rep(76, 0) & EREDAR_BIT)
        self.assertFalse(rep(930, 0) & EREDAR_BIT)
        self.assertEqual([rep(1, i) for i in range(4)], [0, 0, 0, 0])

        helmets = read(self.out, "HelmetGeosetVisData")
        rows = helmets.by_id()
        self.assertEqual(helmets.get(rows[1], "hideGeoset[0]"), (1 << 10) | (1 << 22))
        self.assertEqual(helmets.get(rows[2], "hideGeoset[1]"), (1 << 11) | (1 << 23))
        self.assertEqual(helmets.get(rows[4], "hideGeoset[0]"), 1 << 1)

        talents = read(self.out, "TalentTab")
        self.assertEqual([talents.get(r, "raceMask") for r in talents.rows][:2], [0, 0])

    def test_client_and_server_copies(self):
        client = sorted(os.listdir(os.path.join(self.out, "client", "DBFilesClient")))
        server = sorted(os.listdir(os.path.join(self.out, "server", "dbc")))
        self.assertEqual(client, server)
        self.assertIn("ChrRaces.dbc", client)
        self.assertNotIn("CreatureDisplayInfo.dbc", client)  # read only
        self.assertNotIn("SoundFilter.dbc", client)

        for name in client:
            with open(os.path.join(self.out, "client", "DBFilesClient", name), "rb") as a, open(os.path.join(self.out, "server", "dbc", name), "rb") as b:
                self.assertEqual(a.read(), b.read(), name)

    def test_mpq(self):
        import mpqpack

        archive = mpqpack.MpqArchive(os.path.join(self.out, "client", "patch-R.MPQ"))
        report = archive.verify()
        self.assertEqual(report.problems, [])
        self.assertTrue(report.lookup_mode.startswith("listfile"))
        names = sorted(archive.names())
        self.assertEqual(names, sorted("DBFilesClient\\" + n for n in os.listdir(os.path.join(self.out, "client", "DBFilesClient"))))

        with open(os.path.join(self.out, "client", "DBFilesClient", "ChrRaces.dbc"), "rb") as f:
            self.assertEqual(archive.read("DBFilesClient\\ChrRaces.dbc"), f.read())

    def test_validate_command(self):
        result = run_tool("validate", "--dbc", self.stock, "--out", self.out, "--mpq", os.path.join(self.out, "client", "patch-R.MPQ"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rerun_on_own_output_is_refused(self):
        # The stock folder with RaceForge's output copied over it, as data/dbc looks after the first install.
        patched = os.path.join(self.tmp.name, "patched")
        shutil.copytree(self.stock, patched)

        for name in os.listdir(os.path.join(self.out, "server", "dbc")):
            for existing in os.listdir(patched):
                if existing.lower() == name.lower():
                    os.remove(os.path.join(patched, existing))

            shutil.copyfile(os.path.join(self.out, "server", "dbc", name), os.path.join(patched, name))

        result = run_tool("build", "--dbc", patched, "--out", os.path.join(self.tmp.name, "again"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already has race 22", result.stderr)

    def test_existing_output_needs_force(self):
        result = run_tool("build", "--dbc", self.stock, "--out", self.out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--force", result.stderr)

    def test_sql_on_a_model_world_database(self):
        # SQLite stands in for MySQL: same tables and columns as AzerothCore's world database, with the generated
        # statements translated where the dialects differ (INSERT/UPDATE IGNORE, LEFT).
        if sqlite3.sqlite_version_info < (3, 44):
            self.skipTest("needs SQLite 3.44 or newer for concat()")

        db = sqlite3.connect(":memory:")
        db.executescript("""
            CREATE TABLE player_race_stats (Race INTEGER PRIMARY KEY, Strength INT, Agility INT, Stamina INT, Intellect INT, Spirit INT);
            CREATE TABLE playercreateinfo (race INT, class INT, map INT, zone INT, position_x REAL, position_y REAL, position_z REAL, orientation REAL, PRIMARY KEY (race, class));
            CREATE TABLE playercreateinfo_action (race INT, class INT, button INT, action INT, type INT, PRIMARY KEY (race, class, button));
            CREATE TABLE playercreateinfo_item (race INT, class INT, itemid INT, amount INT, Note TEXT, PRIMARY KEY (race, class, itemid));
            CREATE TABLE playercreateinfo_skills (raceMask INT, classMask INT, skill INT, rank INT, comment TEXT, PRIMARY KEY (raceMask, classMask, skill));
            CREATE TABLE playercreateinfo_spell_custom (racemask INT, classmask INT, Spell INT, Note TEXT, PRIMARY KEY (racemask, classmask, Spell));
            CREATE TABLE playercreateinfo_cast_spell (raceMask INT, classMask INT, spell INT, note TEXT);
            CREATE TABLE player_totem_model (TotemID INT, RaceID INT, ModelID INT, PRIMARY KEY (TotemID, RaceID));
            CREATE TABLE player_shapeshift_model (ShapeshiftID INT, RaceID INT, CustomizationID INT, GenderID INT, ModelID INT, PRIMARY KEY (ShapeshiftID, RaceID, CustomizationID, GenderID));
            CREATE TABLE creature_model_info (DisplayID INT PRIMARY KEY, BoundingRadius REAL, CombatReach REAL, Gender INT, DisplayID_Other_Gender INT);
            CREATE TABLE quest_template (ID INT PRIMARY KEY, AllowableRaces INT);
            CREATE TABLE item_template (entry INT PRIMARY KEY, AllowableRace INT);
            CREATE TABLE spell_area (spell INT, area INT, quest_start INT, aura_spell INT, racemask INT, gender INT, PRIMARY KEY (spell, area, quest_start, aura_spell, racemask, gender));
            CREATE TABLE mail_level_reward (level INT, raceMask INT, mailTemplateId INT, senderEntry INT, PRIMARY KEY (level, raceMask));
            CREATE TABLE conditions (SourceTypeOrReferenceId INT, ConditionTypeOrReference INT, ConditionValue1 INT, PRIMARY KEY (SourceTypeOrReferenceId, ConditionTypeOrReference, ConditionValue1));

            INSERT INTO player_race_stats VALUES (10, -3, 2, 0, 3, -2), (11, 1, -3, 0, 0, 2);
            INSERT INTO playercreateinfo VALUES (10, 2, 530, 3431, 1, 2, 3, 4), (10, 6, 609, 4298, 5, 6, 7, 8), (11, 7, 530, 3526, 1, 2, 3, 4), (11, 6, 609, 4298, 5, 6, 7, 8);
            INSERT INTO playercreateinfo_action VALUES (10, 2, 0, 6603, 0), (10, 2, 1, 28730, 0), (11, 7, 0, 6603, 0), (11, 7, 3, 28880, 0);
            INSERT INTO playercreateinfo_skills VALUES
                (1101, 0, 98, 0, 'Language: Common'), (690, 0, 109, 0, 'Language: Orcish'),
                (512, 0, 137, 0, 'Language: Thalassian'), (1024, 0, 759, 0, 'Language: Draenei'),
                (512, 0, 756, 0, 'Racial - Blood Elf'), (1024, 0, 760, 0, 'Racial - Draenei'),
                (0, 1, 26, 0, 'Arms'), (1791, 2, 594, 0, 'Holy'), (1024, 1, 226, 0, 'Crossbows');
            INSERT INTO player_totem_model VALUES (1, 11, 19074), (2, 11, 19073), (1, 2, 4589);
            INSERT INTO quest_template VALUES (1, 0), (2, 1101), (3, 690), (4, 1), (5, 2), (6, 512), (7, 1791);
            INSERT INTO item_template VALUES (1, -1), (2, 1101), (3, 690), (4, 512), (21020, 512), (21110, 1024);
            INSERT INTO mail_level_reward VALUES (20, 1101, 1, 1), (20, 690, 2, 2);
            INSERT INTO conditions VALUES (1, 16, 1101), (1, 16, 690), (2, 15, 1101);
        """)
        types = {"s": "TEXT", "f": "REAL"}
        db.execute("CREATE TABLE spell_dbc (" + ", ".join(f"{n} {types.get(k, 'INT')}" for n, k in spellmod.SERVER_SPELL_COLUMNS) + ", PRIMARY KEY (ID))")

        def run(filename):
            with open(os.path.join(self.out, "server", "sql", filename), encoding="utf-8") as f:
                text = f.read()

            text = text.replace("INSERT IGNORE INTO", "INSERT OR IGNORE INTO").replace("UPDATE IGNORE", "UPDATE OR IGNORE")
            text = re.sub(r"LEFT\((CONCAT\([^;]*?\)), 255\)", r"substr(\1, 1, 255)", text)
            db.executescript(text)

        def skills(bit):
            return sorted(row[0] for row in db.execute("SELECT skill FROM playercreateinfo_skills WHERE raceMask = ?", (bit,)))

        for _ in range(2):  # running a second time changes nothing
            run("bleakhold_races.sql")

            self.assertEqual(db.execute("SELECT Strength, Agility, Stamina, Intellect, Spirit FROM player_race_stats WHERE Race = 22").fetchone(), (-3, 2, 0, 3, -2))
            starts = dict((row[0], row[1:]) for row in db.execute("SELECT class, map, zone FROM playercreateinfo WHERE race = 22"))
            self.assertEqual(sorted(starts), list(synth.CLASSES[10]))
            self.assertEqual(starts[2], (0, 12))  # Northshire
            self.assertEqual(starts[6], (609, 4298))  # Ebon Hold
            self.assertEqual(db.execute("SELECT map, zone FROM playercreateinfo WHERE race = 23 AND class = 7").fetchone(), (1, 14))  # Valley of Trials
            # the template's racial button goes for the High Elf, and takes Read Ley Line for the Eredar
            self.assertEqual(sorted(db.execute("SELECT class, button, action FROM playercreateinfo_action WHERE race = 22")), [(2, 0, 6603)])
            self.assertEqual(sorted(db.execute("SELECT class, button, action, type FROM playercreateinfo_action WHERE race = 23")), [(7, 0, 6603, 0), (7, 3, 90502, 0)])

            self.assertEqual(skills(HIGH_ELF_BIT), [98, 137, 594])  # Common, Thalassian, all-race Holy; no Blood Elf racial
            self.assertEqual(skills(EREDAR_BIT), [109, 226, 594, 759])  # Orcish, Crossbows, Holy, Draenei; no Draenei racial
            self.assertEqual(sorted(db.execute("SELECT TotemID, ModelID FROM player_totem_model WHERE RaceID = 23")), [(1, 19074), (2, 19073)])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM playercreateinfo_skills").fetchone()[0], 9 + 3 + 4)
            self.assertEqual(sorted(db.execute("SELECT racemask, classmask, Spell FROM playercreateinfo_spell_custom")),
                             [(HIGH_ELF_BIT, 0, 90500), (EREDAR_BIT, 0, 90501), (EREDAR_BIT, 0, 90502)])
            # the racials' spell_dbc rows; Walk on Air's belongs to mod-bleakhold-ui's own SQL
            rows = {r[0]: r for r in db.execute("SELECT ID, Name_Lang_enUS, NameSubtext_Lang_enUS, EffectAura_1, EffectBasePoints_1, EffectMiscValue_1, "
                                                "EffectAura_2, DurationIndex, RecoveryTime, SpellIconID, SpellVisualID_1, EffectChainAmplitude_1 FROM spell_dbc")}
            self.assertEqual(sorted(rows), [90500, 90501, 90502])
            self.assertEqual(rows[90500][1:7], ("Wind Blessed", "Racial Passive", 193, 2, 0, 0))
            self.assertEqual(rows[90501][1:7], ("Elemental Insight", "Racial Passive", 168, 4, 8, 0))
            self.assertEqual(rows[90502][1:], ("Read Ley Line", "Racial", 88, 99, 0, 110, 9, 120000, 2158, 4279, 1.0))

        run("bleakhold_races_content_masks.sql")
        quests = dict(db.execute("SELECT ID, AllowableRaces FROM quest_template"))
        self.assertEqual(quests[1], 0)
        self.assertEqual(quests[2], 1101 | HIGH_ELF_BIT)  # Alliance quests
        self.assertEqual(quests[3], 690 | EREDAR_BIT)  # Horde quests
        self.assertEqual(quests[4], 1 | HIGH_ELF_BIT)  # Human quests: the High Elf starts in the Human zone
        self.assertEqual(quests[5], 2 | EREDAR_BIT)
        self.assertEqual(quests[6], 512)  # Blood Elf quests stay Blood Elf
        self.assertEqual(quests[7], 1791 | HIGH_ELF_BIT | EREDAR_BIT)

        items = dict(db.execute("SELECT entry, AllowableRace FROM item_template"))
        self.assertEqual(items[1], -1)
        self.assertEqual(items[2], 1101 | HIGH_ELF_BIT)
        self.assertEqual(items[3], 690 | EREDAR_BIT)
        self.assertEqual(items[4], 512)
        self.assertEqual(items[21020], 512 | HIGH_ELF_BIT)  # part of the cloned Blood Elf start outfit
        self.assertEqual(items[21110], 1024 | EREDAR_BIT)

        self.assertEqual(sorted(r[0] for r in db.execute("SELECT raceMask FROM mail_level_reward")), sorted([1101 | HIGH_ELF_BIT, 690 | EREDAR_BIT]))
        self.assertEqual(sorted(db.execute("SELECT ConditionTypeOrReference, ConditionValue1 FROM conditions")),
                         sorted([(15, 1101), (16, 690 | EREDAR_BIT), (16, 1101 | HIGH_ELF_BIT)]))

        run("bleakhold_races_remove.sql")
        self.assertEqual(skills(HIGH_ELF_BIT), [])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM spell_dbc").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM playercreateinfo WHERE race IN (22, 23)").fetchone()[0], 0)
        self.assertEqual(dict(db.execute("SELECT ID, AllowableRaces FROM quest_template")), {1: 0, 2: 1101, 3: 690, 4: 1, 5: 2, 6: 512, 7: 1791})
        self.assertEqual(dict(db.execute("SELECT entry, AllowableRace FROM item_template"))[1], -1)


class OptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stock = os.path.join(self.tmp.name, "stock")

    def tearDown(self):
        self.tmp.cleanup()

    def write_config(self, mutate):
        with open(os.path.join(TOOL_DIR, "races.json"), encoding="utf-8") as f:
            data = json.load(f)

        mutate(data)
        path = os.path.join(self.tmp.name, "races.json")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        return path

    def test_missing_required_table(self):
        synth.write_folder(self.stock, skip=("CharSections",))
        result = run_tool("build", "--dbc", self.stock, "--out", os.path.join(self.tmp.name, "out"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CharSections.dbc", result.stderr)

    def test_missing_optional_tables(self):
        synth.write_folder(self.stock, skip=("HelmetGeosetVisData", "CreatureDisplayInfo", "ItemDisplayInfo", "NameGen"))
        out = os.path.join(self.tmp.name, "out")
        result = run_tool("build", "--dbc", self.stock, "--out", out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("HelmetGeosetVisData.dbc not found", result.stdout)
        self.assertIn("[SKIP]", result.stdout)

    def test_class_subset_and_own_displays(self):
        synth.write_folder(self.stock)
        out = os.path.join(self.tmp.name, "out")

        def mutate(data):
            data["races"][0]["classes"] = [2, 8]
            data["races"][1]["male_display_id"] = 7002  # another race's display, which exists
            data["races"][1]["names"] = {"deDE": "Eredar (de)"}

        result = run_tool("build", "--dbc", self.stock, "--out", out, "--config", self.write_config(mutate))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        base = read(out, "CharBaseInfo")
        self.assertEqual([base.get(r, "classID") for r in base.rows if base.get(r, "raceID") == 22], [2, 8])
        races = read(out, "ChrRaces")
        self.assertEqual(races.get(races.by_id()[23], "maleDisplayID"), 7002)
        self.assertEqual(races.get_loc(races.by_id()[23], "name")[3], "Eredar (de)")

        with open(os.path.join(out, "server", "sql", "bleakhold_races.sql"), encoding="utf-8") as f:
            sql = f.read()

        self.assertIn("(22, 8, 0, 12,", sql)
        self.assertNotIn("(22, 3, 0, 12,", sql)
        self.assertIn("SELECT 7002, `BoundingRadius`", sql)

    def test_bad_config_against_data(self):
        synth.write_folder(self.stock)

        for mutate, message in (
            (lambda d: d["races"][0].update(classes=[1]), "not playable by template race"),
            (lambda d: d["races"][0].update(faction_race=2), "is not on the alliance side"),
            (lambda d: d["races"][0].update(template_race=9), "not a playable race"),
            (lambda d: d["races"][0].update(client_file_string="Human"), "already used"),
            (lambda d: d["races"][0].update(faction_template=synth.faction_template_id(2)), "faction_template 5002 is not on the alliance side"),
        ):
            result = run_tool("build", "--dbc", self.stock, "--out", os.path.join(self.tmp.name, "out"), "--config", self.write_config(mutate))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(message, result.stderr)

    def test_unsorted_stock_char_sections_get_sorted(self):
        synth.write_folder(self.stock)
        path = os.path.join(self.stock, "CharSections.dbc")
        table = DbcTable.read(path, schema_access.get("CharSections"))
        table.rows.reverse()
        table.write(path)

        out = os.path.join(self.tmp.name, "out")
        result = run_tool("build", "--dbc", self.stock, "--out", out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("the table was sorted", result.stdout)

    def test_extra_files_in_the_archive(self):
        import mpqpack

        synth.write_folder(self.stock)
        extra = os.path.join(self.tmp.name, "extra")
        skeleton = os.path.join(extra, "World", "Generic", "PassiveDoodads", "DeathSkeletons")
        os.makedirs(skeleton)

        with open(os.path.join(skeleton, "HighElfMaleDeathSkeleton.m2"), "wb") as f:
            f.write(b"MD20 not a real model")

        out = os.path.join(self.tmp.name, "out")
        result = run_tool("build", "--dbc", self.stock, "--out", out, "--mpq-extra", extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        archive = mpqpack.MpqArchive(os.path.join(out, "client", "patch-R.MPQ"))
        self.assertEqual(archive.read("World\\Generic\\PassiveDoodads\\DeathSkeletons\\HighElfMaleDeathSkeleton.m2"), b"MD20 not a real model")
        self.assertTrue(archive.has_file("DBFilesClient\\ChrRaces.dbc"))
        self.assertEqual(archive.verify().problems, [])

        # An extra DBC that RaceForge also writes is refused instead of silently replaced.
        os.makedirs(os.path.join(extra, "DBFilesClient"))

        with open(os.path.join(extra, "DBFilesClient", "ChrRaces.dbc"), "wb") as f:
            f.write(b"x")

        result = run_tool("build", "--dbc", self.stock, "--out", out, "--force", "--mpq-extra", extra)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ChrRaces.dbc", result.stderr)

    def test_schemas_command(self):
        result = run_tool("schemas", "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
