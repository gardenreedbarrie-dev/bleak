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
RACIALS = (90500, 90501, 90502)
WALK_ON_AIR = 100800


def run_tool(*args):
    return subprocess.run([sys.executable, "-I", os.path.join(TOOL_DIR, "raceforge.py"), *args], capture_output=True, text=True)


def races_json() -> dict:
    with open(os.path.join(TOOL_DIR, "races.json"), encoding="utf-8") as f:
        return json.load(f)


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


def archive_table(archive_path: str, name: str) -> DbcTable:
    with mpqpack.MpqArchive(archive_path) as archive:
        return DbcTable.from_bytes(archive.read(update.archive_file(name)), schema_access.get(name))


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
    """A realm that runs the races without the racials (RaceForge's earlier patch-R), updated in place."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.stock = os.path.join(cls.tmp.name, "stock")
        synth.write_folder(cls.stock)
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
        return run_tool("update", "--patches", self.patches, "--dbc", self.stock, "--out", os.path.join(self.work, out), "--force", *extra)

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
        data = races_json()
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
        config = configmod.load(os.path.join(TOOL_DIR, "races.json"))

        for name in ("SkillRaceClassInfo", "SkillLineAbility", "Spell"):
            self.assertEqual(update.copy_problems(name, archive_table(os.path.join(client, "Patch-R.MPQ"), name), config), [], name)

    def test_bad_spell_field_or_sql_is_an_error_message(self):
        # a column Spell.dbc does not have: refused before --force clears the earlier output
        self.assertEqual(self.update().returncode, 0)
        data = races_json()
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
        self.assertIn("has no race [22, 23]: install the races first", result.stderr)

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

        self.assertEqual(len(found), 1, f"one world-database file holds the racials: {sorted(found)}")
        text = next(iter(found.values()))
        rows = spellmod.parse_sql_rows(text, "spell_dbc")
        table = DbcTable.empty(schema_access.get("Spell"))

        for spell_id in config.server_sql_spell_ids():
            row = spellmod.build_row(table, config.spells[spell_id])
            self.assertIn(spell_id, rows)
            self.assertEqual(spellmod.compare_row(table, row, rows[spell_id]), [], spell_id)

        self.assertNotIn(WALK_ON_AIR, rows)  # mod-bleakhold-ui's own SQL holds it
        self.assertIn("spell_bh_read_ley_line", text)
        ok, output = lint_sql(text)
        self.assertTrue(ok, output)

    def test_mod_bleakhold_table(self):
        path = os.path.join(SERVER_SRC, "modules", "mod-bleakhold", "src", "bh_racials_rules.h")

        if not os.path.isfile(path):
            self.skipTest("mod-bleakhold's bh_racials_rules.h not found")

        with open(path, encoding="utf-8") as f:
            header = f.read()

        constants = {name: int(value) for name, value in re.findall(r"inline constexpr uint\d+_t (\w+) = (\d+);", header)}
        rows = re.findall(r"\{ (RACE_\w+), (SKILL_\w+), \{ (\w+), (\w+) \}, (\w+) \}", header)
        value = lambda token: constants.get(token, 0) if not token.isdigit() else int(token)  # noqa: E731
        config = configmod.load(os.path.join(TOOL_DIR, "races.json"))
        table = {value(r[0]): ([value(r[1])], [s for s in (value(r[2]), value(r[3])) if s], value(r[4])) for r in rows}
        expected = {race.id: (race.drop_skill_lines, race.racial_spells, config.action_bar_spell(race)) for race in config.races}
        self.assertEqual(table, expected)


if __name__ == "__main__":
    unittest.main()
