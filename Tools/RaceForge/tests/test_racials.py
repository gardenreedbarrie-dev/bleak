"""The racials: races.json's racials and spells, the Spell.dbc rows and their SQL, and `raceforge.py update` on a realm.

The update tests build realm patch folders from made-up DBCs: RaceForge's own earlier patch-R.MPQ (built without the
racials), a later realm patch holding Spell.dbc with a custom row, and an optional pack (Tools/MapForge's rules for
which copy wins). When a bleakserv checkout is next to this repository, the tests also compare the server columns, the
pending world-database file and mod-bleakhold's racial table with races.json.
"""

import contextlib
import io
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
TOOLS_DIR = os.path.dirname(TOOL_DIR)
REPO_ROOT = os.path.dirname(TOOLS_DIR)
MPQPACK_DIR = os.path.join(TOOLS_DIR, "MpqPack")

for path in (TOOL_DIR, MPQPACK_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import mpqpack  # noqa: E402

from rflib import config as configmod  # noqa: E402
from rflib import schema_access, spells as spellmod, update  # noqa: E402
from rflib.dbc import DbcTable, to_signed  # noqa: E402
from tests import synth  # noqa: E402

SERVER_SRC = os.environ.get("RACEFORGE_SERVER_SRC") or os.path.join(os.path.dirname(REPO_ROOT), "bleakserv")
HIGH_ELF_BIT = 1 << 21
EREDAR_BIT = 1 << 22
# The Bleakhold realm: High Elf 15, Eredar 19 (races.json's realm_id), Pandaren 20 and 21 (its own race patch)
REALM_HIGH_ELF_BIT = 1 << 14
REALM_EREDAR_BIT = 1 << 18
REALM_PANDAREN_BIT = 1 << 19
NO_RACE = -2147483648
RACIALS = (90500, 90501, 90502)
WALK_ON_AIR = 100800


def run_tool(*args):
    return subprocess.run([sys.executable, "-I", os.path.join(TOOL_DIR, "raceforge.py"), *args], capture_output=True, text=True)


def races_json() -> dict:
    with open(os.path.join(TOOL_DIR, "races.json"), encoding="utf-8") as f:
        return json.load(f)


def build_ids(data: dict) -> dict:
    """races.json without realm_id: update then works on the races at races.json's ids, as RaceForge's build made them."""
    data = json.loads(json.dumps(data))

    for race in data["races"]:
        race.pop("realm_id", None)

    return data


def without_racials(data: dict) -> dict:
    data = json.loads(json.dumps(data))

    for race in data["races"]:
        race.pop("racials", None)

    data.pop("spells", None)
    return data


def write_json(path: str, data: dict) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    return path


def table_of(path: str, name: str) -> DbcTable:
    return DbcTable.read(path, schema_access.get(name))


def table_of_bytes(archive_path: str, name: str) -> DbcTable:
    return archive_table(archive_path, name)


def archive_table(archive_path: str, name: str) -> DbcTable:
    with mpqpack.MpqArchive(archive_path) as archive:
        return DbcTable.from_bytes(archive.read(update.archive_file(name)), schema_access.get(name))


def sqlite_world(db: sqlite3.Connection):
    """The world tables the racials SQL touches, in SQLite."""
    types = {"s": "TEXT", "f": "REAL"}
    db.execute("CREATE TABLE spell_dbc (" + ", ".join(f"{n} {types.get(k, 'INT')}" for n, k in spellmod.SERVER_SPELL_COLUMNS) + ", PRIMARY KEY (ID))")
    db.execute("CREATE TABLE skillraceclassinfo_dbc (" + ", ".join(f"{n} INT" for n in spellmod.SERVER_SKILL_RACE_CLASS_COLUMNS) + ", PRIMARY KEY (ID))")
    db.execute("CREATE TABLE skilllineability_dbc (" + ", ".join(f"{n} INT" for n in spellmod.SERVER_SKILL_LINE_ABILITY_COLUMNS) + ", PRIMARY KEY (ID))")
    db.executescript("""
        CREATE TABLE playercreateinfo (race INT, class INT, PRIMARY KEY (race, class));
        CREATE TABLE playercreateinfo_action (race INT, class INT, button INT, action INT, type INT, PRIMARY KEY (race, class, button));
        CREATE TABLE playercreateinfo_skills (raceMask INT, classMask INT, skill INT, rank INT, comment TEXT, PRIMARY KEY (raceMask, classMask, skill));
        CREATE TABLE playercreateinfo_spell_custom (racemask INT, classmask INT, Spell INT, Note TEXT, PRIMARY KEY (racemask, classmask, Spell));
        CREATE TABLE playercreateinfo_cast_spell (raceMask INT, classMask INT, spell INT, note TEXT);
        CREATE TABLE spell_script_names (spell_id INT, ScriptName TEXT);
    """)


def lint_module():
    """bleakserv's codestyle-sql.py check functions (the script runs git on import, so only its functions)."""
    with open(os.path.join(SERVER_SRC, "apps", "codestyle", "codestyle-sql.py"), encoding="utf-8") as f:
        source = f.read()

    source = source[:source.index("# Collect all files from matching directories")]
    lint = type(sys)("codestyle_sql")
    exec(compile(source, "codestyle-sql.py", "exec"), lint.__dict__)  # noqa: S102
    return lint


def lint_sql(text: str) -> tuple[bool, str]:
    lint = lint_module()
    folder = tempfile.mkdtemp()

    try:
        path = os.path.join(folder, "rev.sql")

        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

        with open(path, encoding="utf-8") as f, contextlib.redirect_stdout(io.StringIO()) as out:
            for check in (lint.multiple_blank_lines_check, lint.trailing_whitespace_check, lint.sql_check, lint.insert_delete_safety_check,
                          lint.semicolon_check, lint.backtick_check, lint.non_innodb_engine_check):
                check(f, path)

        return not lint.error_handler, out.getvalue()
    finally:
        shutil.rmtree(folder)


class ConfigTests(unittest.TestCase):
    def parse(self, mutate):
        data = races_json()
        mutate(data)
        return configmod.parse(data, "races.json")

    def test_races_json(self):
        config = configmod.load(os.path.join(TOOL_DIR, "races.json"))
        high_elf, eredar = config.races
        self.assertEqual((high_elf.drop_skill_lines, high_elf.racial_spells), ([756], [90500]))
        self.assertEqual((eredar.drop_skill_lines, eredar.racial_spells), ([760], [90501, 90502]))
        self.assertEqual(config.racial_spell_ids(), list(RACIALS))
        self.assertEqual(config.spell_ids(), list(RACIALS) + [WALK_ON_AIR])
        self.assertEqual(config.server_sql_spell_ids(), list(RACIALS))  # Walk on Air's row is mod-bleakhold-ui's
        self.assertEqual(config.action_bar_spell(eredar), 90502)
        self.assertEqual(config.action_bar_spell(high_elf), 0)
        self.assertTrue(config.spells[90500].passive and config.spells[90501].passive and not config.spells[90502].passive)
        self.assertEqual(config.spells[WALK_ON_AIR].cast_by, "server")
        self.assertEqual(config.spells[WALK_ON_AIR].text_locales, ["enUS"])
        self.assertEqual(len(config.spells[90500].text_locales), 9)
        self.assertEqual(config.archives.own, "patch-R.MPQ")
        self.assertIn("hd", config.archives.optional_packs)
        # build adds the races after the stock rows; the Bleakhold realm has them in the stock slots 15 and 19
        self.assertEqual([(r.id, r.realm_id, r.bit) for r in config.races], [(22, 15, 1 << 21), (23, 19, 1 << 22)])
        realm = config.for_realm()
        self.assertEqual([(r.id, r.build_id, r.bit) for r in realm.races], [(15, 22, REALM_HIGH_ELF_BIT), (19, 23, REALM_EREDAR_BIT)])
        self.assertEqual([r.id for r in config.races], [22, 23])  # for_realm() leaves the config alone
        self.assertEqual([r.id for r in configmod.parse(build_ids(races_json())).for_realm().races], [22, 23])

    def test_refusals(self):
        def spell(data, spell_id):
            return next(s for s in data["spells"] if s["id"] == spell_id)

        for mutate, message in (
            (lambda d: d["races"][0]["racials"].update(color="red"), "unknown keys"),
            (lambda d: d["races"][0]["racials"].update(spells=[12345]), "not defined in spells"),
            (lambda d: d["races"][0]["racials"].update(spells=[90500, 90500]), "twice"),
            (lambda d: d["races"][0]["racials"].update(drop_template_skill_lines=[0]), "positive ids"),
            (lambda d: d["races"][0]["racials"].update(spells=[90500, WALK_ON_AIR]), "cast_by server"),
            (lambda d: d["races"][1]["racials"].update(spells=[90501]), "no race lists"),
            (lambda d: d["spells"].append(dict(spell(d, 90500))), "two spells have the id 90500"),
            (lambda d: spell(d, 90500).update(id=0), "id must be between"),
            (lambda d: spell(d, 90500).update(name=" "), "name is empty"),
            (lambda d: spell(d, 90500).update(name="x" * 101), "longer than the 100 bytes"),
            (lambda d: spell(d, 90500).update(colour=1), "unknown keys"),
            (lambda d: spell(d, 90500)["fields"].update(attributes="80"), "must be a number"),
            (lambda d: spell(d, WALK_ON_AIR).update(cast_by="pet"), "cast_by must be"),
            (lambda d: spell(d, WALK_ON_AIR).update(server_row="/etc/passwd"), "inside the repository"),
            (lambda d: spell(d, WALK_ON_AIR).update(server_row="../bleakserv/x.sql"), "inside the repository"),
            (lambda d: spell(d, WALK_ON_AIR).update(text_locales=["xxXX"]), "text_locales"),
            (lambda d: spell(d, WALK_ON_AIR).update(text_locales=[]), "text_locales"),
            (lambda d: d["races"][0].update(realm_id=0), "realm_id must be between 1 and 31"),
            (lambda d: d["races"][0].update(realm_id=32), "realm_id must be between 1 and 31"),
            (lambda d: d["races"][0].update(realm_id=25), "Bleakhold has no Pandaren"),
            (lambda d: d["races"][0].update(realm_id=10), "is the race's template_race or faction_race"),
            (lambda d: d["races"][1].update(realm_id=2), "is the race's template_race or faction_race"),
            (lambda d: d["races"][0].update(realm_id="15"), "must be a whole number"),
            (lambda d: d["races"][1].update(realm_id=15), "two races have the same realm_id"),
            (lambda d: d["races"][1].update(realm_id=None, id=15), "two races have the same realm_id"),
            (lambda d: d.update(archives={"own": "patch-RR.MPQ"}), "archives.own"),
            (lambda d: d.update(archives={"optional_packs": {"hd": "Data/Patch-Y.MPQ"}}), "optional_packs"),
        ):
            with self.subTest(message=message):
                with self.assertRaises(configmod.ConfigError) as caught:
                    self.parse(mutate)

                self.assertIn(message, str(caught.exception))

    def test_without_racials_is_the_old_config(self):
        config = configmod.parse(without_racials(races_json()), "x")
        self.assertEqual(config.spell_ids(), [])
        self.assertEqual([r.drop_skill_lines for r in config.races], [[], []])


class SpellRowTests(unittest.TestCase):
    def setUp(self):
        self.table = DbcTable.empty(schema_access.get("Spell"))
        self.config = configmod.load(os.path.join(TOOL_DIR, "races.json"))

    def test_row_from_races_json(self):
        row = spellmod.build_row(self.table, self.config.spells[90502])
        t = self.table
        self.assertEqual(to_signed(row[0]), 90502)
        self.assertEqual(t.get(row, "procChance"), 101)
        self.assertEqual(to_signed(t.get(row, "equippedItemClass")), -1)
        self.assertEqual([t.float_value(row, f"effectChainAmplitude[{i}]") for i in range(3)], [1.0, 1.0, 1.0])
        self.assertEqual((t.get(row, "effectAura[0]"), t.get(row, "effectBasePoints[0]"), t.get(row, "effectAura[1]")), (88, 99, 110))
        self.assertEqual((t.get(row, "durationIndex"), t.get(row, "recoveryTime"), t.get(row, "spellVisualID[0]"), t.get(row, "spellIconID")), (9, 120000, 4279, 2158))
        self.assertEqual(t.get_loc(row, "name")[:9], ["Read Ley Line"] * 9)
        self.assertEqual(t.get_loc(row, "name")[9:], [""] * 7)
        self.assertEqual(t.get(row, "name_flags"), spellmod.LOC_FLAGS_TEXT)
        self.assertIn("$s1%", t.get_str(row, "description[0]"))

        walk = spellmod.build_row(self.table, self.config.spells[WALK_ON_AIR])
        self.assertEqual(t.get_loc(walk, "name")[:2], ["Walk on Air", ""])  # enUS only, as its server row
        self.assertEqual(t.float_value(walk, "effectBonusCoefficient[0]"), 1.0)

    def test_field_problems(self):
        spell = configmod.SpellDef(id=1, name="x", fields={"nonsense": 1, "id": 5, "name[0]": 1, "attributes": 1.5, "recoveryTime": 1 << 40,
                                                           "speed": 1.5})
        problems = " ".join(spellmod.field_problems(self.table, spell))

        for expected in ("nonsense: Spell.dbc has no such column", "fields.id: set by RaceForge", "fields.name[0]: set by RaceForge",
                         "attributes: a whole number", "recoveryTime: 1099511627776 does not fit"):
            self.assertIn(expected, problems)

        self.assertNotIn("speed", problems)  # a float column takes a fraction

        with self.assertRaises(spellmod.SpellError):
            spellmod.build_row(self.table, spell)

    def test_sql_round_trip_and_comparison(self):
        spell = configmod.SpellDef(id=95000, name="It's a \\ test", description="semi; colon) and 'quotes'", icon=1,
                                   fields={"attributes": 0x80000040, "equippedItemClass": -1, "speed": 2.5, "effectBasePoints[0]": -3})
        row = spellmod.build_row(self.table, spell)
        sql = spellmod.spell_sql(self.table, [row])
        self.assertTrue(all(len(line) <= 120 for line in sql.split("\n") if not line.lstrip().startswith("'")))
        rows = spellmod.parse_sql_rows(sql + "\n-- a comment; with semicolons\nINSERT INTO `other` (`ID`) VALUES (1);\n", "spell_dbc")
        self.assertEqual(list(rows), [95000])
        values = rows[95000]
        self.assertEqual(values["Attributes"], str(0x80000040))  # unsigned column
        self.assertEqual(values["EquippedItemClass"], "-1")  # signed column
        self.assertEqual(values["EffectBasePoints_1"], "-3")
        self.assertEqual(values["Speed"], "2.5")
        self.assertEqual(values["Name_Lang_enUS"], "'It''s a \\\\ test'")
        self.assertEqual(values["Description_Lang_enUS"], "'semi; colon) and ''quotes'''")
        self.assertEqual(spellmod.compare_row(self.table, row, values), [])

        changed = dict(values, EffectBasePoints_1="-2")
        self.assertEqual(spellmod.compare_row(self.table, row, changed), ["EffectBasePoints_1: -3 in the DBC, -2 in the SQL"])
        partial = {k: v for k, v in values.items() if v not in ("0", "''")}
        self.assertTrue(any("missing in the SQL" in d for d in spellmod.compare_row(self.table, row, partial)))
        self.assertEqual(spellmod.compare_row(self.table, row, partial, missing_is_default=True), [])
        self.assertEqual(spellmod.compare_row(self.table, row, dict(values, Speed="2.50")), [])  # same float

    def test_wrapped_tuples_stay_parseable(self):
        values = ["7"] + [str(i) for i in range(299)] + ["'" + "x" * 150 + "'"]
        lines = spellmod.wrap_tuple(values, ");", " -- long")
        self.assertEqual(lines[0], "-- long")
        self.assertTrue(all(len(line) <= 120 for line in lines if "x" * 150 not in line))
        sql = "INSERT INTO `t` (`ID`, " + ", ".join(f"`c{i}`" for i in range(300)) + ") VALUES\n" + "\n".join(lines)
        rows = spellmod.parse_sql_rows(sql, "t")
        self.assertEqual(list(rows), [7])
        self.assertEqual((rows[7]["c0"], rows[7]["c298"], rows[7]["c299"]), ("0", "298", "'" + "x" * 150 + "'"))


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stock = os.path.join(self.tmp.name, "stock")
        synth.write_folder(self.stock)

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, mutate) -> str:
        data = races_json()
        mutate(data)
        return write_json(os.path.join(self.tmp.name, "races.json"), data)

    def build(self, *extra):
        return run_tool("build", "--dbc", self.stock, "--out", os.path.join(self.tmp.name, "out"), "--force", *extra)

    def test_template_racials_kept_without_racials(self):
        config = write_json(os.path.join(self.tmp.name, "old.json"), without_racials(races_json()))
        result = self.build("--config", config)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        skills = table_of(os.path.join(self.tmp.name, "out", "client", "DBFilesClient", "SkillRaceClassInfo.dbc"), "SkillRaceClassInfo")
        by_skill = {skills.get(r, "skillID"): skills.get(r, "raceMask") for r in skills.rows}
        self.assertTrue(by_skill[synth.SKILL_RACIAL_BLOODELF] & HIGH_ELF_BIT)
        self.assertTrue(by_skill[synth.SKILL_RACIAL_DRAENEI] & EREDAR_BIT)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "out", "client", "DBFilesClient", "Spell.dbc")))

    def test_spell_rows_and_report(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = os.path.join(self.tmp.name, "out")
        spells = table_of(os.path.join(out, "client", "DBFilesClient", "Spell.dbc"), "Spell")
        stock = table_of(os.path.join(self.stock, "Spell.dbc"), "Spell")
        self.assertEqual(spells.rows[:len(stock.rows)], stock.rows)  # stock rows untouched, new ones appended
        self.assertEqual(sorted(spells.ids() - stock.ids()), list(RACIALS) + [WALK_ON_AIR])
        self.assertIn("spell_dbc row matches Spell.dbc field for field", result.stdout)
        self.assertIn("02_bleakhold_walk_on_air.sql matches Spell.dbc field for field", result.stdout)

        with open(os.path.join(out, "server", "sql", "bleakhold_races.sql"), encoding="utf-8") as f:
            sql = f.read()

        self.assertEqual(sorted(spellmod.parse_sql_rows(sql, "spell_dbc")), list(RACIALS))
        self.assertIn("NOT IN (756)", sql)

    def test_refusals(self):
        def spell(data, spell_id):
            return next(s for s in data["spells"] if s["id"] == spell_id)

        for mutate, message in (
            (lambda d: spell(d, 90500).update(id=28730) or d["races"][0]["racials"].update(spells=[28730]), "Spell.dbc already has spell 28730"),
            (lambda d: d["races"][0]["racials"].update(drop_template_skill_lines=[760]), "is not a skill line of template race 10"),
            (lambda d: spell(d, 90500).update(icon_name="Ability_Something_Else"), "is Ability_Druid_GaleWinds in SpellIcon.dbc"),
            (lambda d: spell(d, 90502).update(visual=999999), "SpellVisual.dbc has no visual 999999"),
            (lambda d: spell(d, 90502)["fields"].update(durationIndex=777), "SpellDuration.dbc has no row 777"),
            (lambda d: spell(d, 90501).update(icon=0), "no icon"),
            (lambda d: spell(d, 90501)["fields"].update(madeUp=1), "Spell.dbc has no such column"),
        ):
            with self.subTest(message=message):
                result = self.build("--config", self.config(mutate))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

        os.remove(os.path.join(self.stock, "Spell.dbc"))
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing Spell.dbc", result.stderr)

    def test_validate_finds_a_tampered_sql_row(self):
        result = self.build("--mpq")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = os.path.join(self.tmp.name, "out")
        path = os.path.join(out, "server", "sql", "bleakhold_races.sql")

        with open(path, encoding="utf-8") as f:
            sql = f.read()

        tampered = sql.replace("'Wind Blessed'", "'Wind Blest'", 1)
        self.assertNotEqual(tampered, sql)

        with open(path, "w", encoding="utf-8") as f:
            f.write(tampered)

        result = run_tool("validate", "--dbc", self.stock, "--out", out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("[FAIL] racial spell 90500 Wind Blessed: spell_dbc row matches Spell.dbc field for field", result.stdout)


class UpdateTests(unittest.TestCase):
    """A realm that runs the races without the racials (RaceForge's earlier patch-R, races 22 and 23), updated in place
    with races.json at its build ids (no realm_id)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.stock = os.path.join(cls.tmp.name, "stock")
        synth.write_folder(cls.stock)
        cls.config = write_json(os.path.join(cls.tmp.name, "build_ids.json"), build_ids(races_json()))
        cls.old_config = write_json(os.path.join(cls.tmp.name, "old.json"), without_racials(races_json()))
        cls.old = os.path.join(cls.tmp.name, "old")
        result = run_tool("build", "--dbc", cls.stock, "--out", cls.old, "--mpq", "--config", cls.old_config)
        assert result.returncode == 0, result.stdout + result.stderr
        cls.fresh = os.path.join(cls.tmp.name, "fresh")
        result = run_tool("build", "--dbc", cls.stock, "--out", cls.fresh)
        assert result.returncode == 0, result.stdout + result.stderr

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.work = tempfile.mkdtemp(dir=self.tmp.name)
        self.patches = os.path.join(self.work, "patches")
        os.makedirs(self.patches)
        shutil.copyfile(os.path.join(self.old, "client", "patch-R.MPQ"), os.path.join(self.patches, "patch-R.MPQ"))

    def update(self, *extra, out="out"):
        config = () if "--config" in extra else ("--config", self.config)
        return run_tool("update", "--patches", self.patches, "--dbc", self.stock, "--out", os.path.join(self.work, out), "--force", *config, *extra)

    def spell_table_with(self, extra_rows: list[tuple[int, str]]) -> bytes:
        """The stock Spell.dbc plus made-up custom rows (a realm's own spells)."""
        table = table_of(os.path.join(self.stock, "Spell.dbc"), "Spell")

        for spell_id, name in extra_rows:
            row = list(table.rows[0])
            table.set(row, "id", spell_id)
            table.set_loc(row, "name", [name] + [""] * 15)
            table.rows.append(row)

        return table.to_bytes()

    def test_patch_r_only_and_idempotent(self):
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DBFilesClient\\Spell.dbc: the copy in no patch (the stock copy) for every player: stock copy + change, into patch-R.MPQ", result.stdout)
        rebuilt = os.path.join(self.work, "out", "client", "patch-R.MPQ")

        with mpqpack.MpqArchive(rebuilt) as archive, mpqpack.MpqArchive(os.path.join(self.patches, "patch-R.MPQ")) as before:
            self.assertEqual(archive.verify().problems, [])
            self.assertTrue(set(before.names()) <= set(archive.names()))
            self.assertEqual(archive.read("DBFilesClient\\ChrRaces.dbc"), before.read("DBFilesClient\\ChrRaces.dbc"))  # untouched

        # the update gives the same tables as a fresh build from stock with the racials
        for name in ("SkillRaceClassInfo", "SkillLineAbility", "Spell"):
            with open(os.path.join(self.fresh, "client", "DBFilesClient", f"{name}.dbc"), "rb") as f:
                self.assertEqual(archive_table(rebuilt, name).to_bytes(), f.read(), name)

        shutil.copyfile(rebuilt, os.path.join(self.patches, "patch-R.MPQ"))
        again = self.update(out="again")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(again.stdout.count("already up to date"), 3)
        self.assertIn("Client archives: none", again.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.work, "again", "client", "patch-R.MPQ")))

    def test_spell_dbc_in_a_later_realm_patch(self):
        # Patch-Z holds the realm's own Spell.dbc (a custom spell) and a texture: the rows go into Patch-Z's copy.
        mpqpack.write_archive(os.path.join(self.patches, "Patch-Z.MPQ"), [("DBFilesClient\\Spell.dbc", self.spell_table_with([(90170, "Backpack")])),
                                                                        ("Interface\\Icons\\Custom.blp", b"BLP2 made up")])
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("the copy in Patch-Z.MPQ for every player: merged into Patch-Z.MPQ (rebuilt)", result.stdout)
        rebuilt = os.path.join(self.work, "out", "client", "Patch-Z.MPQ")
        spells = archive_table(rebuilt, "Spell")
        self.assertTrue({90170, *RACIALS, WALK_ON_AIR} <= spells.ids())

        with mpqpack.MpqArchive(rebuilt) as archive:
            self.assertEqual(archive.read("Interface\\Icons\\Custom.blp"), b"BLP2 made up")

        # patch-R is rebuilt for the skill tables only, and gets no Spell.dbc (it would lose to Patch-Z)
        with mpqpack.MpqArchive(os.path.join(self.work, "out", "client", "patch-R.MPQ")) as archive:
            self.assertFalse(archive.has_file("DBFilesClient\\Spell.dbc"))

    def test_optional_pack(self):
        # Patch-Y (the HD pack) and patch-T hold different copies: players with the pack read Patch-Y's, the others
        # patch-T's. Both get the rows and keep their own.
        mpqpack.write_archive(os.path.join(self.patches, "Patch-Y.MPQ"), [("DBFilesClient\\Spell.dbc", self.spell_table_with([(90171, "HD")]))])
        mpqpack.write_archive(os.path.join(self.patches, "patch-T.MPQ"), [("DBFilesClient\\Spell.dbc", self.spell_table_with([(90172, "T")]))])
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("the copy in Patch-Y.MPQ for all packs", result.stdout)
        self.assertIn("the copy in patch-T.MPQ for no packs", result.stdout)
        hd = archive_table(os.path.join(self.work, "out", "client", "Patch-Y.MPQ"), "Spell").ids()
        plain = archive_table(os.path.join(self.work, "out", "client", "patch-T.MPQ"), "Spell").ids()
        self.assertTrue({90171, *RACIALS} <= hd and 90172 not in hd)
        self.assertTrue({90172, *RACIALS} <= plain and 90171 not in plain)

    def test_pack_archive_below_own_is_refused(self):
        # Only patch-D (the HD pack, which sorts before patch-R) holds Spell.dbc: the stock copy for the players without
        # the pack would go into patch-R, which the HD players load too, over patch-D's copy. Refused, nothing written.
        mpqpack.write_archive(os.path.join(self.patches, "patch-D.MPQ"), [("DBFilesClient\\Spell.dbc", self.spell_table_with([(90171, "HD")]))])
        result = self.update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no patch holds DBFilesClient\\Spell.dbc for no packs", result.stderr)
        self.assertIn("patch-R.MPQ (archives.own), which loads over patch-D.MPQ", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.work, "out", "client")))

        # archives.own below patch-D but in the HD pack itself (patch-B): the players without the pack would not load it
        data = build_ids(races_json())
        data["archives"]["own"] = "patch-B.MPQ"
        result = self.update("--config", write_json(os.path.join(self.work, "own_in_pack.json"), data))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("patch-B.MPQ (archives.own), which is in the optional pack hd", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.work, "out", "client")))

        # a pack archive that sorts after patch-R (patch-S) keeps winning for the HD players: no refusal
        os.remove(os.path.join(self.patches, "patch-D.MPQ"))
        mpqpack.write_archive(os.path.join(self.patches, "patch-S.MPQ"), [("DBFilesClient\\Spell.dbc", self.spell_table_with([(90171, "HD")]))])
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("the copy in patch-S.MPQ for all packs: merged into patch-S.MPQ (rebuilt)", result.stdout)
        self.assertIn("for no packs: stock copy + change, into patch-R.MPQ", result.stdout)
        hd = archive_table(os.path.join(self.work, "out", "client", "patch-S.MPQ"), "Spell").ids()
        plain = archive_table(os.path.join(self.work, "out", "client", "patch-R.MPQ"), "Spell").ids()
        self.assertTrue({90171, *RACIALS} <= hd)
        self.assertTrue(set(RACIALS) <= plain and 90171 not in plain)

    def test_own_archive_in_another_case(self):
        # The realm's archive is Patch-R.MPQ: the stock Spell.dbc goes into that same archive, next to the skill tables.
        os.rename(os.path.join(self.patches, "patch-R.MPQ"), os.path.join(self.patches, "Patch-R.MPQ"))
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("stock copy + change, into Patch-R.MPQ", result.stdout)
        client = os.path.join(self.work, "out", "client")
        self.assertEqual(os.listdir(client), ["Patch-R.MPQ"])
        config = configmod.parse(build_ids(races_json()))

        for name in ("SkillRaceClassInfo", "SkillLineAbility", "Spell"):
            self.assertEqual(update.copy_problems(name, archive_table(os.path.join(client, "Patch-R.MPQ"), name), config), [], name)

    def test_bad_spell_field_or_sql_is_an_error_message(self):
        # a column Spell.dbc does not have: refused before --force clears the earlier output
        self.assertEqual(self.update().returncode, 0)
        data = build_ids(races_json())
        next(sp for sp in data["spells"] if sp["id"] == 90501)["fields"]["madeUp"] = 1
        result = self.update("--config", write_json(os.path.join(self.work, "bad.json"), data))
        self.assertEqual(result.returncode, 1)
        self.assertIn("error: spell 90501 (Elemental Insight): fields.madeUp: Spell.dbc has no such column", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.work, "out", "report.txt")))

        # an --server-sql file the SQL reader cannot parse
        broken = os.path.join(self.work, "broken.sql")

        with open(broken, "w", encoding="utf-8") as f:
            f.write("INSERT INTO `spell_dbc` (`ID`, `Category`) VALUES\n(90500, 0)\n")

        result = self.update("--server-sql", broken, out="s")
        self.assertEqual(result.returncode, 1)
        self.assertIn("error: an INSERT has no closing ';'", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_ids_taken_or_older(self):
        mpqpack.write_archive(os.path.join(self.patches, "Patch-Z.MPQ"), [("DBFilesClient\\Spell.dbc", self.spell_table_with([(90501, "Someone Else")]))])
        result = self.update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("spell 90501 is taken by 'Someone Else'", result.stderr)

        # an earlier version of the same spell (same name) is replaced
        mpqpack.write_archive(os.path.join(self.patches, "Patch-Z.MPQ"), [("DBFilesClient\\Spell.dbc", self.spell_table_with([(90501, "Elemental Insight")]))])
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("spell 90501 Elemental Insight: updated", result.stdout)

    def test_unreadable_archive_stops_it(self):
        with open(os.path.join(self.patches, "patch-Z.MPQ"), "wb") as f:
            f.write(b"not an archive")

        result = self.update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot read every archive", result.stderr)

    def test_realm_without_the_races(self):
        os.remove(os.path.join(self.patches, "patch-R.MPQ"))
        result = self.update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("High Elf: the realm's ChrRaces.dbc (--dbc, for every player) has no race 22; install the races first", result.stderr)
        self.assertIn("Eredar: the realm's ChrRaces.dbc (--dbc, for every player) has no race 23; install the races first", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.work, "out", "client")))

        # races.json's realm ids (15, 19) on this realm, which has the races at 22 and 23: refused, with where they are
        result = self.update("--config", os.path.join(TOOL_DIR, "races.json"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("High Elf: the realm's ChrRaces.dbc (--dbc, for every player) has Skeleton as race 15, not HighElf", result.stderr)
        shutil.copyfile(os.path.join(self.old, "client", "patch-R.MPQ"), os.path.join(self.patches, "patch-R.MPQ"))
        result = self.update("--config", os.path.join(TOOL_DIR, "races.json"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("(patch-R.MPQ, for every player) has Skeleton as race 15, not HighElf; HighElf is race 22 there: set realm_id 22", result.stderr)
        self.assertIn("has Taunka as race 19, not Eredar; Eredar is race 23 there: set realm_id 23", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_server_sql_comparison(self):
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        with open(os.path.join(self.work, "out", "server", "sql", update.SQL_FILE), encoding="utf-8") as f:
            sql = f.read()

        self.assertEqual(sorted(spellmod.parse_sql_rows(sql, "spell_dbc")), list(RACIALS))
        good = os.path.join(self.work, "good.sql")
        bad = os.path.join(self.work, "bad.sql")

        with open(good, "w", encoding="utf-8") as f:
            f.write(sql + "\n-- the module's own block\nDELETE FROM `spell_script_names` WHERE `spell_id` = 90502;\n")

        with open(bad, "w", encoding="utf-8") as f:
            f.write(sql.replace("(90501, 0, 0, 0, 80,", "(90501, 0, 0, 0, 81,", 1))

        self.assertEqual(self.update("--server-sql", good, out="g").returncode, 0)
        result = self.update("--server-sql", bad, out="b")
        self.assertEqual(result.returncode, 1)
        self.assertIn("spell_dbc 90501: Attributes differ", result.stdout)

    def test_update_sql_on_a_model_world_database(self):
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        db = sqlite3.connect(":memory:")
        sqlite_world(db)
        db.executescript("""
            -- the realm as RaceForge's earlier SQL left it: the races copy the template's racial rows
            INSERT INTO playercreateinfo VALUES (22, 2), (22, 8), (23, 1), (23, 7), (11, 7);
            INSERT INTO playercreateinfo_action VALUES (10, 2, 3, 28730, 0), (22, 2, 3, 28730, 0), (22, 2, 0, 6603, 0),
                (11, 7, 3, 28880, 0), (11, 1, 74, 28880, 0), (23, 7, 3, 28880, 0), (23, 7, 0, 6603, 0), (23, 1, 74, 28880, 0);
            INSERT INTO playercreateinfo_skills VALUES (2097152, 0, 756, 0, 'High Elf: Racial'), (2097152, 0, 98, 0, 'Common'), (4194304, 0, 760, 0, 'Eredar: Racial');
            INSERT INTO playercreateinfo_spell_custom VALUES (2097152, 0, 28730, 'copied');
            INSERT INTO playercreateinfo_cast_spell VALUES (4194304, 0, 28880, 'copied');
            INSERT INTO skillraceclassinfo_dbc VALUES (5, 756, 2097664, 0, 0, 0, 0, 0);
        """)

        with open(os.path.join(self.work, "out", "server", "sql", update.SQL_FILE), encoding="utf-8") as f:
            sql = f.read()

        for _ in range(2):  # running it again changes nothing
            db.executescript(sql)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM spell_dbc").fetchone()[0], 3)
            self.assertEqual(sorted(db.execute("SELECT ID, SkillID, RaceMask FROM skillraceclassinfo_dbc")), [(5, 756, 512), (6, 760, 1024)])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM skilllineability_dbc WHERE (RaceMask & ?) <> 0", (HIGH_ELF_BIT | EREDAR_BIT,)).fetchone()[0], 0)
            self.assertEqual(sorted(db.execute("SELECT raceMask, skill FROM playercreateinfo_skills")), [(2097152, 98)])
            self.assertEqual(sorted(db.execute("SELECT racemask, Spell FROM playercreateinfo_spell_custom")),
                             [(HIGH_ELF_BIT, 90500), (EREDAR_BIT, 90501), (EREDAR_BIT, 90502)])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM playercreateinfo_cast_spell").fetchone()[0], 0)
            self.assertEqual(sorted(db.execute("SELECT race, class, button, action FROM playercreateinfo_action WHERE race IN (22, 23)")),
                             [(22, 2, 0, 6603), (23, 1, 74, 90502), (23, 7, 0, 6603), (23, 7, 3, 90502)])

    @unittest.skipUnless(os.path.isfile(os.path.join(SERVER_SRC, "apps", "codestyle", "codestyle-sql.py")), "bleakserv checkout not found")
    def test_update_sql_passes_bleakserv_codestyle(self):
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        with open(os.path.join(self.work, "out", "server", "sql", update.SQL_FILE), encoding="utf-8") as f:
            ok, output = lint_sql(f.read())

        self.assertTrue(ok, output)

    def test_ids_clause(self):
        self.assertEqual(update.ids_clause("ID", [5]), "`ID` = 5")
        self.assertEqual(update.ids_clause("ID", [7, 5]), "`ID` IN (5, 7)")
        self.assertEqual(update.ids_clause("ID", [1, 2, 3, 9, 20, 21, 22, 23]), "`ID` BETWEEN 1 AND 3 OR `ID` = 9 OR `ID` BETWEEN 20 AND 23")


def bump(table: DbcTable, row_id: int, bits: int):
    row = table.by_id()[row_id]
    table.set(row, "raceMask", table.get(row, "raceMask") | bits)


def clone(table: DbcTable, row_id: int, new_id: int, **values) -> list[int]:
    row = list(table.by_id()[row_id])
    table.set(row, "id", new_id)

    for name, value in values.items():
        table.set(row, name, value)

    table.rows.append(row)
    return row


def realm_tables(stock: str) -> dict[str, bytes]:
    """The Bleakhold realm's own race patch, made up: ChrRaces holds High Elf in slot 15 and Eredar in 19 (Blood Elf's
    and Draenei's rows under their own file strings) and Pandaren in 20 and 21, the stock creature display slots it
    reuses. Its race tool gave the races masks of its own: their bits on the template racial rows and the languages,
    a row of race 15 alone for skill line 756 and one of race 19 alone for 760, a Pandaren bit on a 760 row."""
    races = table_of(os.path.join(stock, "ChrRaces.dbc"), "ChrRaces")
    by_id = races.by_id()

    for slot, template, file_string in ((15, 10, "HighElf"), (19, 11, "Eredar"), (20, 2, "Pandaren"), (21, 1, "Pandaren")):
        row = list(by_id[template])
        races.set(row, "id", slot)
        races.set_str(row, "clientFileString", file_string)
        races.rows[races.rows.index(by_id[slot])] = row

    skills = table_of(os.path.join(stock, "SkillRaceClassInfo.dbc"), "SkillRaceClassInfo")
    bump(skills, 1, REALM_HIGH_ELF_BIT)  # Language: Common
    bump(skills, 2, REALM_EREDAR_BIT)  # Language: Orcish
    bump(skills, 5, REALM_HIGH_ELF_BIT)  # Racial - Blood Elf
    bump(skills, 6, REALM_EREDAR_BIT | REALM_PANDAREN_BIT)  # Racial - Draenei, and the Pandaren
    clone(skills, 5, 13, raceMask=REALM_HIGH_ELF_BIT)
    abilities = table_of(os.path.join(stock, "SkillLineAbility.dbc"), "SkillLineAbility")
    bump(abilities, 3, REALM_HIGH_ELF_BIT)
    bump(abilities, 4, REALM_EREDAR_BIT)
    clone(abilities, 4, 9, spell=59542, raceMask=REALM_EREDAR_BIT)
    return {"ChrRaces": races.to_bytes(), "SkillRaceClassInfo": skills.to_bytes(), "SkillLineAbility": abilities.to_bytes()}


def realm_archive(path: str, tables: dict[str, bytes]):
    mpqpack.write_archive(path, [(update.archive_file(name), data) for name, data in tables.items()]
                          + [("Interface\\Glues\\Custom.blp", b"BLP2 the realm's own")])


class BleakholdRealmTests(unittest.TestCase):
    """The Bleakhold realm: High Elf and Eredar in the stock slots 15 and 19 of its own Patch-R.MPQ (races.json's
    realm_id), the server's data/dbc with the stock ChrRaces and a row of its own, the world database after the
    earlier racials update for races 22 and 23."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.stock = os.path.join(cls.tmp.name, "stock")
        synth.write_folder(cls.stock)
        cls.tables = realm_tables(cls.stock)
        # the server's data/dbc: stock, plus rows only it has (race 15 on a Blood Elf racial row, and alone on another)
        cls.server_dbc = os.path.join(cls.tmp.name, "server-dbc")
        synth.write_folder(cls.server_dbc)

        for name, row_id, new_id, values in (("SkillRaceClassInfo", 5, 50, {"raceMask": (1 << 9) | REALM_HIGH_ELF_BIT}),
                                             ("SkillLineAbility", 3, 60, {"spell": 822, "raceMask": REALM_HIGH_ELF_BIT})):
            path = os.path.join(cls.server_dbc, f"{name}.dbc")
            table = table_of(path, name)
            clone(table, row_id, new_id, **values)
            table.write(path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.work = tempfile.mkdtemp(dir=self.tmp.name)
        self.patches = os.path.join(self.work, "patches")
        os.makedirs(self.patches)
        realm_archive(os.path.join(self.patches, "Patch-R.MPQ"), self.tables)
        self.generated = os.path.join(self.work, "bleakhold-generated-sql", "pending_db_world")

    def update(self, *extra, out="out"):
        return run_tool("update", "--patches", self.patches, "--dbc", self.server_dbc, "--out", os.path.join(self.work, out), "--force", *extra)

    def sql(self, out="out") -> str:
        with open(os.path.join(self.work, out, "server", "sql", update.SQL_FILE), encoding="utf-8") as f:
            return f.read()

    def test_races_15_and_19(self):
        result = self.update("--server-sql-out", self.generated)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ChrRaces.dbc (Patch-R.MPQ, for every player): race 15 is HighElf, race 19 is Eredar", result.stdout)
        self.assertIn("15 High Elf (races.json id 22; the realm has it at 15)", result.stdout)
        self.assertIn("Bleakhold.Racials.HighElfRace = 15", result.stdout)
        self.assertIn("Bleakhold.Racials.EredarRace = 19", result.stdout)
        self.assertIn('BleakholdUi.Glide.Races = "15"', result.stdout)
        self.assertIn("rows 13 were the race's alone: mask 0x80000000, no race", result.stdout)
        self.assertIn("SkillRaceClassInfo.dbc of --dbc (the server's data/dbc): rows [50] give a race a dropped skill line", result.stdout)
        rebuilt = os.path.join(self.work, "out", "client", "Patch-R.MPQ")
        self.assertEqual(os.listdir(os.path.join(self.work, "out", "client")), ["Patch-R.MPQ"])

        with mpqpack.MpqArchive(rebuilt) as archive:
            self.assertEqual(archive.verify().problems, [])
            self.assertEqual(archive.read("DBFilesClient\\ChrRaces.dbc"), self.tables["ChrRaces"])  # untouched
            self.assertEqual(archive.read("Interface\\Glues\\Custom.blp"), b"BLP2 the realm's own")

        # the races' bits go from the dropped skill lines only; the realm's other bits (Blood Elf, Draenei, the
        # Pandaren, the languages) stay; a row of the race alone matches no race
        masks = {i: table_of_bytes(rebuilt, "SkillRaceClassInfo").get(r, "raceMask") for i, r in table_of_bytes(rebuilt, "SkillRaceClassInfo").by_id().items()}
        self.assertEqual(masks[1], synth.ALLIANCE_MASK | REALM_HIGH_ELF_BIT)
        self.assertEqual(masks[2], synth.HORDE_MASK | REALM_EREDAR_BIT)
        self.assertEqual((masks[5], masks[6], masks[13]), (1 << 9, (1 << 10) | REALM_PANDAREN_BIT, 0x80000000))
        abilities = table_of_bytes(rebuilt, "SkillLineAbility")
        self.assertEqual({i: abilities.get(r, "raceMask") for i, r in abilities.by_id().items() if i in (3, 4, 9)}, {3: 1 << 9, 4: 1 << 10, 9: 0x80000000})
        self.assertTrue({*RACIALS, WALK_ON_AIR} <= table_of_bytes(rebuilt, "Spell").ids())
        realm = configmod.load(os.path.join(TOOL_DIR, "races.json")).for_realm()

        for name in ("SkillRaceClassInfo", "SkillLineAbility", "Spell"):
            self.assertEqual(update.copy_problems(name, table_of_bytes(rebuilt, name), realm), [], name)

        # the server rows: the realm's own (and the server's data/dbc row it lacks), without the races' bits
        sql = self.sql()
        rows = spellmod.parse_sql_rows(sql, "skillraceclassinfo_dbc")
        self.assertEqual({i: int(r["RaceMask"]) for i, r in rows.items()}, {5: 512, 6: 1024 | REALM_PANDAREN_BIT, 13: NO_RACE, 50: 512})
        rows = spellmod.parse_sql_rows(sql, "skilllineability_dbc")
        self.assertEqual({i: int(r["RaceMask"]) for i, r in rows.items()}, {3: 512, 4: 1024, 9: NO_RACE, 60: NO_RACE})
        self.assertEqual(sorted(spellmod.parse_sql_rows(sql, "spell_dbc")), list(RACIALS))
        self.assertNotIn(str(HIGH_ELF_BIT) + ",", sql)
        self.assertIn(f"DELETE FROM `playercreateinfo_spell_custom` WHERE `racemask` = {HIGH_ELF_BIT} AND `Spell` = 90500;", sql)
        self.assertIn(f"DELETE FROM `playercreateinfo_spell_custom` WHERE `racemask` = {EREDAR_BIT} AND `Spell` IN (90501, 90502);", sql)
        self.assertIn("DELETE FROM `playercreateinfo_action` WHERE `race` = 23 AND `type` = 0 AND `action` = 90502;", sql)
        self.assertTrue(all(len(line) <= 120 for line in sql.splitlines() if not line.startswith("    'Read the ley lines")), sql)

        # the rev file for update-bleakhold-ui.sh: the same SQL, under a create_sql.sh name
        revs = os.listdir(self.generated)
        self.assertEqual(len(revs), 1)
        self.assertRegex(revs[0], r"^rev_\d{19}\.sql$")

        with open(os.path.join(self.generated, revs[0]), encoding="utf-8") as f:
            self.assertEqual(f.read(), sql)

        self.assertIn(f"Server SQL rev: {os.path.join(self.generated, revs[0])} (written)", result.stdout)

        # on the updated patches: nothing left to change, the same SQL, and no second rev file
        shutil.copyfile(rebuilt, os.path.join(self.patches, "Patch-R.MPQ"))
        again = self.update("--server-sql-out", self.generated, out="again")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(again.stdout.count("already up to date"), 3)
        self.assertEqual(self.sql("again"), sql)
        self.assertEqual(os.listdir(self.generated), revs)
        self.assertIn("already there with the same SQL: nothing written", again.stdout)

    def test_locale_patch_keeps_its_folder(self):
        # the realm's locale patch holds its own Spell.dbc: rebuilt at its place, client/enUS/, for the patch folder's enUS/
        os.makedirs(os.path.join(self.patches, "enUS"))
        spells = table_of(os.path.join(self.stock, "Spell.dbc"), "Spell")
        clone(spells, 668, 90171)
        mpqpack.write_archive(os.path.join(self.patches, "enUS", "patch-enUS-8.MPQ"), [("DBFilesClient\\Spell.dbc", spells.to_bytes())])
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DBFilesClient\\Spell.dbc: the copy in patch-enUS-8.MPQ for every player: merged into patch-enUS-8.MPQ (rebuilt)", result.stdout)
        client = os.path.join(self.work, "out", "client")
        self.assertEqual(sorted(os.listdir(client)), ["Patch-R.MPQ", "enUS"])
        self.assertTrue({90171, *RACIALS, WALK_ON_AIR} <= table_of_bytes(os.path.join(client, "enUS", "patch-enUS-8.MPQ"), "Spell").ids())

    def test_sql_on_the_realm_world_database(self):
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        db = sqlite3.connect(":memory:")
        sqlite_world(db)
        he, er = REALM_HIGH_ELF_BIT, REALM_EREDAR_BIT
        db.executescript(f"""
            -- the realm's own rows: the races at 15 and 19 with copies of the template rows, some sharing a row
            -- with the template race; overrides of its own; and what the earlier update wrote for races 22 and 23
            INSERT INTO playercreateinfo VALUES (15, 2), (15, 8), (19, 1), (19, 7), (10, 2), (11, 7);
            INSERT INTO playercreateinfo_action VALUES (10, 2, 3, 28730, 0), (15, 2, 3, 28730, 0), (15, 2, 0, 6603, 0),
                (11, 7, 3, 28880, 0), (19, 7, 3, 28880, 0), (19, 7, 0, 6603, 0), (19, 1, 74, 28880, 0), (23, 7, 3, 90502, 0);
            INSERT INTO playercreateinfo_skills VALUES ({he | 512}, 0, 756, 0, 'Blood Elf, High Elf'), (512, 0, 756, 0, 'Blood Elf'),
                ({er | 1024}, 0, 760, 0, 'Draenei, Eredar'), ({er}, 1, 760, 0, 'Eredar warrior'), ({he | synth.ALLIANCE_MASK}, 0, 98, 0, 'Common');
            INSERT INTO playercreateinfo_spell_custom VALUES ({HIGH_ELF_BIT}, 0, 90500, 'old'), ({EREDAR_BIT}, 0, 90501, 'old'),
                ({EREDAR_BIT}, 0, 90502, 'old'), ({he}, 0, 28730, 'High Elf'), ({he | 512}, 0, 822, 'Blood Elf, High Elf');
            INSERT INTO playercreateinfo_cast_spell VALUES ({er}, 0, 28880, 'Eredar'), ({er | 1024}, 0, 59542, 'Draenei, Eredar');
            INSERT INTO skillraceclassinfo_dbc VALUES (5, 756, 512, 0, 0, 1, 0, 0), (98, 756, {he}, 0, 0, 1, 0, 0), (99, 756, {he | 512}, 0, 0, 1, 0, 0),
                (100, 98, {he | synth.ALLIANCE_MASK}, 0, 0, 1, 0, 0);
            INSERT INTO skilllineability_dbc VALUES (97, 760, 59999, {er}, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        """)
        sql = self.sql()

        for _ in range(2):  # running it again changes nothing
            db.executescript(sql)
            self.assertEqual(sorted(db.execute("SELECT ID, SkillID, RaceMask FROM skillraceclassinfo_dbc")),
                             [(5, 756, 512), (6, 760, 1024 | REALM_PANDAREN_BIT), (13, 756, NO_RACE), (50, 756, 512), (98, 756, NO_RACE),
                              (99, 756, 512), (100, 98, he | synth.ALLIANCE_MASK)])
            self.assertEqual(sorted(db.execute("SELECT ID, RaceMask FROM skilllineability_dbc")),
                             [(3, 512), (4, 1024), (9, NO_RACE), (60, NO_RACE), (97, NO_RACE)])
            self.assertEqual(sorted(db.execute("SELECT raceMask, classMask, skill, comment FROM playercreateinfo_skills")),
                             [(512, 0, 756, "Blood Elf, High Elf"), (1024, 0, 760, "Draenei, Eredar"), (he | synth.ALLIANCE_MASK, 0, 98, "Common")])
            self.assertEqual(sorted(db.execute("SELECT racemask, Spell FROM playercreateinfo_spell_custom")),
                             [(512, 822), (he, 90500), (er, 90501), (er, 90502)])
            self.assertEqual(sorted(db.execute("SELECT raceMask, spell FROM playercreateinfo_cast_spell")), [(1024, 59542)])
            self.assertEqual(sorted(db.execute("SELECT race, class, button, action FROM playercreateinfo_action")),
                             [(10, 2, 3, 28730), (11, 7, 3, 28880), (15, 2, 0, 6603), (19, 1, 74, 90502), (19, 7, 0, 6603), (19, 7, 3, 90502)])

    def test_races_not_where_races_json_says(self):
        # the realm's patch has the stock ChrRaces: nothing is written
        tables = dict(self.tables)

        with open(os.path.join(self.stock, "ChrRaces.dbc"), "rb") as f:
            tables["ChrRaces"] = f.read()

        realm_archive(os.path.join(self.patches, "Patch-R.MPQ"), tables)
        result = self.update("--server-sql-out", self.generated)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("High Elf: the realm's ChrRaces.dbc (Patch-R.MPQ, for every player) has Skeleton as race 15, not HighElf; "
                      "install the races first", result.stderr)
        self.assertIn("Eredar: the realm's ChrRaces.dbc (Patch-R.MPQ, for every player) has Taunka as race 19, not Eredar", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.work, "out", "client")))
        self.assertFalse(os.path.exists(self.generated))

        # the HD pack's own ChrRaces (Patch-Y) lacks them: the players with the pack would get the racials on other races
        realm_archive(os.path.join(self.patches, "Patch-R.MPQ"), self.tables)
        mpqpack.write_archive(os.path.join(self.patches, "Patch-Y.MPQ"), [("DBFilesClient\\ChrRaces.dbc", tables["ChrRaces"])])
        result = self.update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("High Elf: the realm's ChrRaces.dbc (Patch-Y.MPQ, for all packs) has Skeleton as race 15", result.stderr)
        self.assertNotIn("(Patch-R.MPQ, for no packs) has", result.stderr)

        # a realm_id that is not the race's: refused with the slot that is; an earlier output folder stays as it was
        os.remove(os.path.join(self.patches, "Patch-Y.MPQ"))
        self.assertEqual(self.update().returncode, 0)
        data = races_json()
        data["races"][0]["realm_id"] = 16
        result = self.update("--config", write_json(os.path.join(self.work, "wrong.json"), data))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has Vrykul as race 16, not HighElf; HighElf is race 15 there: set realm_id 15 for High Elf", result.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.work, "out", "client", "Patch-R.MPQ")))
        self.assertTrue(os.path.isfile(os.path.join(self.work, "out", "report.txt")))

    def test_server_sql_out_never_changes_a_file(self):
        target = os.path.join(self.generated, "rev_1793100000000000000.sql")
        os.makedirs(self.generated)

        with open(target, "w", encoding="utf-8") as f:
            f.write("-- applied already\n")

        result = self.update("--server-sql-out", target)
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"error: {target} exists with other content; it is never changed", result.stderr)
        self.assertIn("Server SQL rev: not written", result.stdout)

        with open(target, encoding="utf-8") as f:
            self.assertEqual(f.read(), "-- applied already\n")

        # a new name: written; then the same SQL under another name is not written twice
        named = os.path.join(self.generated, "rev_1793100000000000001.sql")
        self.assertEqual(self.update("--server-sql-out", named).returncode, 0)

        with open(named, encoding="utf-8") as f:
            self.assertEqual(f.read(), self.sql())

        result = self.update("--server-sql-out", os.path.join(self.generated, "rev_1793100000000000002.sql"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"Server SQL rev: {named} (already there with the same SQL: nothing written)", result.stdout)
        self.assertEqual(sorted(os.listdir(self.generated)), ["rev_1793100000000000000.sql", "rev_1793100000000000001.sql"])

        # nothing is written when a check fails
        result = self.update("--server-sql-out", os.path.join(self.work, "elsewhere"), "--server-sql", target)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.work, "elsewhere")))
        self.assertIn("not written to", result.stdout)

    @unittest.skipUnless(os.path.isfile(os.path.join(SERVER_SRC, "apps", "codestyle", "codestyle-sql.py")), "bleakserv checkout not found")
    def test_realm_sql_passes_bleakserv_codestyle(self):
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        ok, output = lint_sql(self.sql())
        self.assertTrue(ok, output)


@unittest.skipUnless(os.path.isfile(os.path.join(SERVER_SRC, "data", "sql", "base", "db_world", "spell_dbc.sql")), "bleakserv checkout not found")
class BleakservTests(unittest.TestCase):
    """races.json against the server: the spell_dbc columns, the pending world-database file, mod-bleakhold's table."""

    def create_table_columns(self, table: str) -> list[tuple[str, str]]:
        with open(os.path.join(SERVER_SRC, "data", "sql", "base", "db_world", f"{table}.sql"), encoding="utf-8") as f:
            text = f.read()

        body = re.search(rf"CREATE TABLE `{table}` \((.*?)\n\) ENGINE", text, re.S).group(1)
        kinds = {("int", False): "i", ("int", True): "u", ("bigint", False): "I", ("bigint", True): "U", ("float", False): "f",
                 ("varchar", False): "s", ("text", False): "s"}
        out = []

        for line in body.split("\n"):
            match = re.match(r"\s*`(\w+)` (\w+)( unsigned)?", line)

            if match:
                out.append((match.group(1), kinds[(match.group(2), bool(match.group(3)))]))

        return out

    def test_server_columns(self):
        self.assertEqual(self.create_table_columns("spell_dbc"), list(spellmod.SERVER_SPELL_COLUMNS))
        self.assertEqual([c for c, _ in self.create_table_columns("skillraceclassinfo_dbc")], list(spellmod.SERVER_SKILL_RACE_CLASS_COLUMNS))
        self.assertEqual([c for c, _ in self.create_table_columns("skilllineability_dbc")], list(spellmod.SERVER_SKILL_LINE_ABILITY_COLUMNS))

    def test_pending_world_file_holds_the_racials(self):
        config = configmod.load(os.path.join(TOOL_DIR, "races.json"))
        found = {}

        for folder in ("pending_db_world", "db_world"):
            base = os.path.join(SERVER_SRC, "data", "sql", "updates", folder)

            for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
                if not name.endswith(".sql"):
                    continue

                with open(os.path.join(base, name), encoding="utf-8") as f:
                    text = f.read()

                if "INSERT INTO `spell_dbc`" in text and 90500 in spellmod.parse_sql_rows(text, "spell_dbc"):
                    found[name] = text

        # the racials' first file, and any realm rev of `update --server-sql-out` that landed here later: each holds the
        # rows races.json describes
        self.assertTrue(found, "a world-database file holds the racials")
        table = DbcTable.empty(schema_access.get("Spell"))

        for name, text in found.items():
            rows = spellmod.parse_sql_rows(text, "spell_dbc")

            for spell_id in config.server_sql_spell_ids():
                row = spellmod.build_row(table, config.spells[spell_id])
                self.assertIn(spell_id, rows, name)
                self.assertEqual(spellmod.compare_row(table, row, rows[spell_id]), [], f"{name}: {spell_id}")

            self.assertNotIn(WALK_ON_AIR, rows, name)  # mod-bleakhold-ui's own SQL holds it
            ok, output = lint_sql(text)
            self.assertTrue(ok, f"{name}: {output}")

        self.assertTrue(any("spell_bh_read_ley_line" in text for text in found.values()))

    def test_mod_bleakhold_table(self):
        path = os.path.join(SERVER_SRC, "modules", "mod-bleakhold", "src", "bh_racials_rules.h")

        if not os.path.isfile(path):
            self.skipTest("mod-bleakhold's bh_racials_rules.h not found")

        with open(path, encoding="utf-8") as f:
            header = f.read()

        constants = {name: int(value) for name, value in re.findall(r"inline constexpr uint\d+_t (\w+) = (\d+);", header)}
        constants.update(highElf=constants["DEFAULT_RACE_HIGH_ELF"], eredar=constants["DEFAULT_RACE_EREDAR"])
        rows = re.findall(r"\{ (highElf|eredar), (SKILL_\w+), \{ (\w+), (\w+) \}, (\w+) \}", header)
        value = lambda token: constants.get(token, 0) if not token.isdigit() else int(token)  # noqa: E731
        # the module's default race ids are the Bleakhold realm's (races.json's realm_id), as `update` targets them
        config = configmod.load(os.path.join(TOOL_DIR, "races.json")).for_realm()
        table = {value(r[0]): ([value(r[1])], [s for s in (value(r[2]), value(r[3])) if s], value(r[4])) for r in rows}
        expected = {race.id: (race.drop_skill_lines, race.racial_spells, config.action_bar_spell(race)) for race in config.races}
        self.assertEqual(table, expected)

        with open(os.path.join(SERVER_SRC, "modules", "mod-bleakhold", "conf", "mod_bleakhold.conf.dist"), encoding="utf-8") as f:
            conf = dict(re.findall(r"(?m)^(Bleakhold\.Racials\.\w+) = (\S+)$", f.read()))

        high_elf, eredar = config.races
        self.assertEqual((conf["Bleakhold.Racials.HighElfRace"], conf["Bleakhold.Racials.EredarRace"]), (str(high_elf.id), str(eredar.id)))


class GlideRaceTests(unittest.TestCase):
    def test_glide_race_is_the_realm_high_elf(self):
        # mod-bleakhold-ui's glide (this repository's Server/mod-bleakhold-ui) defaults to the realm's High Elf
        high_elf = next(r for r in configmod.load(os.path.join(TOOL_DIR, "races.json")).for_realm().races if r.client_file_string == "HighElf")
        ui = os.path.join(REPO_ROOT, "Server", "mod-bleakhold-ui")

        with open(os.path.join(ui, "conf", "mod_bleakhold_ui.conf.dist"), encoding="utf-8") as f:
            self.assertIn(f'\nBleakholdUi.Glide.Races = "{high_elf.id}"\n', f.read())

        with open(os.path.join(ui, "src", "BleakholdCamp.cpp"), encoding="utf-8") as f:
            self.assertIn(f'"BleakholdUi.Glide.Races", "{high_elf.id}"', f.read())

        with open(os.path.join(ui, "src", "BleakholdCamp.h"), encoding="utf-8") as f:
            self.assertIn(f"glideRaces{{ {high_elf.id} }}", f.read())


if __name__ == "__main__":
    unittest.main()
