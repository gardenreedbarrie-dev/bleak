"""doctor and the plan under it (sections 6.4, 6.5) on synthetic patch sets: where each café table goes for every
pack combination, the café's ids in each copy, the refusals (a taken id, a CharTitles mask clash, a patch-4.MPQ that
is not the café's, café paths in another archive, the server SQL's rows in the café's ids) and a re-run that finds
everything already up to date.

    python3 -I Tools/CafeForge/tests/run_tests.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.dont_write_bytecode = True
for path in (TOOL, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

import cafe_synth as S  # noqa: E402
from cflib import catalog, config, doctor, plan as planmod, schemas  # noqa: E402

from rflib import update  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402

CFG = config.from_doc(catalog.load(), S.PACKS)
SPELL = schemas.archive_file("Spell")
TITLES = schemas.archive_file("CharTitles")
ICONS = schemas.archive_file("SpellIcon")
DISPLAYS = schemas.archive_file("GameObjectDisplayInfo")
SERVER_SRC = os.environ.get("CAFEFORGE_SERVER_SRC") or os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(TOOL))), "bleakserv")


def bounds():
    """Made-up manifest bounds for every display: the box of its cafe.json size around the origin."""
    out = {}
    for d in CFG.displays:
        out[d.id] = ((-0.5, -0.5, 0.0), (0.5, 0.5, 1.0 + (d.id - 19300) / 100))
    return out


class PatchSets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cafeforge-doctor-")
        self.patches = os.path.join(self.tmp, "patches")
        os.makedirs(self.patches)
        self.dbc = S.write_stock(os.path.join(self.tmp, "dbc"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def plan(self, cfg=CFG, with_bounds=None):
        ps = update.patch_tools().PatchSet.scan(self.patches, cfg.optional_packs)
        try:
            return planmod.make_plan(cfg, ps, self.dbc, with_bounds)
        finally:
            ps.close()

    def lines(self, plan):
        return plan.table_lines()

    def doctor(self, *extra):
        return subprocess.run([sys.executable, "-I", os.path.join(TOOL, "cafeforge.py"), "doctor", "--patches",
                               self.patches, "--dbc", self.dbc, "--out", self.tmp, *extra],
                              capture_output=True, text=True)

    # --- where the tables go

    def test_spell_dbc_in_patch_r_only(self):
        S.write_patch(self.patches, "patch-R.MPQ", {"Spell": S.spell_table([(90170, "Made Up Backpack")])})
        plan = self.plan()
        self.assertEqual(plan.problems, [])
        self.assertEqual(plan.configurations, ["every player"])
        self.assertIn("Spell.dbc from patch-R.MPQ -> patch-R.MPQ (36 to add)", self.lines(plan))
        self.assertIn("GameObjectDisplayInfo.dbc: no patch (stock) -> patch-4.MPQ (24 to add)", self.lines(plan))
        self.assertIn("CharTitles.dbc: no patch (stock) -> patch-4.MPQ (2 to add)", self.lines(plan))
        self.assertIn("SpellIcon.dbc: no patch (stock) -> patch-4.MPQ (14 to add)", self.lines(plan))
        self.assertEqual(sorted(plan.targets), ["patch-4.MPQ", "patch-R.MPQ"])
        self.assertEqual(sorted(plan.targets["patch-R.MPQ"]), [SPELL])
        # without the manifest the display rows are known by identity only: nothing to write for them yet
        self.assertEqual(sorted(plan.targets["patch-4.MPQ"]), sorted([TITLES, ICONS]))
        self.assertEqual(plan.own_state, "new")

    def test_spell_dbc_in_patch_r_and_the_hd_pack(self):
        S.write_patch(self.patches, "patch-R.MPQ", {"Spell": S.spell_table([(90170, "Made Up Backpack")])})
        S.write_patch(self.patches, "Patch-Y.MPQ", {"Spell": S.spell_table([(90171, "Made Up HD")])})
        plan = self.plan()
        self.assertEqual(plan.problems, [])
        self.assertEqual(plan.configurations, ["all packs", "no packs"])
        self.assertIn("all packs: Spell.dbc from Patch-Y.MPQ -> Patch-Y.MPQ (36 to add)", self.lines(plan))
        self.assertIn("no packs: Spell.dbc from patch-R.MPQ -> patch-R.MPQ (36 to add)", self.lines(plan))
        self.assertEqual(sorted(plan.targets), ["Patch-Y.MPQ", "patch-4.MPQ", "patch-R.MPQ"])

    def test_only_the_pack_holds_it(self):
        # no packs: the stock copy goes into patch-4, which sorts below the pack's Patch-Y and so hides nothing
        S.write_patch(self.patches, "Patch-Y.MPQ", {"Spell": S.spell_table()})
        plan = self.plan()
        self.assertEqual(plan.problems, [])
        self.assertIn("all packs: Spell.dbc from Patch-Y.MPQ -> Patch-Y.MPQ (36 to add)", self.lines(plan))
        self.assertIn("no packs: Spell.dbc: no patch (stock) -> patch-4.MPQ (36 to add)", self.lines(plan))

    def test_café_archive_in_a_pack_is_refused(self):
        cfg = config.from_doc(catalog.load(), {"hd": ["Data/patch-4.MPQ", "Data/Patch-Y.MPQ"]})
        S.write_patch(self.patches, "Patch-Y.MPQ", {"Spell": S.spell_table()})
        plan = self.plan(cfg)
        self.assertTrue(any("patch-4.MPQ is in the optional pack hd" in p for p in plan.problems), plan.problems)

    # --- refusals

    def test_taken_spell_id(self):
        S.write_patch(self.patches, "patch-R.MPQ", {"Spell": S.spell_table([(100903, "Someone Else")])})
        plan = self.plan()
        self.assertEqual(plan.problems, ["patch-R.MPQ (every player): spell 100903 Pull Shot: id 100903 is taken by "
                                         "'Someone Else' (name[0]) in this copy of Spell.dbc"])
        self.assertNotIn("patch-R.MPQ", plan.targets)

    def test_char_titles_mask_clash(self):
        tables = S.stock_tables(titles=((1, 1, "Made Up %s"), (50, 160, "%s the Clashing")))
        S.write_stock(self.dbc, tables)
        plan = self.plan()
        self.assertIn("stock (every player): CharTitles mask 160 (title 190 '%s the Barista') is taken by title 50 "
                      "'%s the Clashing'", plan.problems)

    def test_taken_title_icon_and_display_ids(self):
        tables = S.stock_tables(titles=((191, 7, "%s the Other"),))
        t = tables["SpellIcon"]
        row = S.new_row(t, 19305)
        t.set_str(row, "textureFilename", "Interface\\Icons\\Made_Up_Other")
        t.rows.append(row)
        t = tables["GameObjectDisplayInfo"]
        row = S.new_row(t, 19300)
        t.set_str(row, "modelName", "World\\Made\\Up\\Other.m2")
        t.rows.append(row)
        S.write_stock(self.dbc, tables)
        problems = self.plan().problems
        self.assertEqual(len(problems), 3, problems)
        self.assertTrue(any("title 191 " in p and "taken by '%s the Other'" in p for p in problems), problems)
        self.assertTrue(any("icon 19305 BH_Cafe_Shelf: id 19305 is taken" in p for p in problems), problems)
        self.assertTrue(any("display 19300 EspressoSW: id 19300 is taken" in p for p in problems), problems)

    def test_patch_4_without_the_marker_is_refused(self):
        S.write_patch(self.patches, "patch-4.MPQ", files={"Interface\\Made\\Up.blp": b"made up"})
        plan = self.plan()
        self.assertEqual(plan.own_state, "refused")
        self.assertTrue(any("was not written by CafeForge" in p for p in plan.problems), plan.problems)

    def test_modelforge_test_patch_is_refused(self):
        S.write_patch(self.patches, "patch-4.MPQ", files=S.marker("test\n"))
        plan = self.plan()
        self.assertEqual(plan.own_state, "refused")
        self.assertTrue(any("ModelForge's test patch" in p for p in plan.problems), plan.problems)

    def test_cafe_paths_in_another_archive(self):
        S.write_patch(self.patches, "patch-Z.MPQ", files={"World\\Bleakhold\\Cafe\\EspressoSW\\X.blp": b"made up"})
        plan = self.plan()
        self.assertTrue(any(p.startswith("patch-Z.MPQ already holds café paths") for p in plan.problems),
                        plan.problems)

    def test_missing_visual(self):
        S.write_stock(self.dbc, S.stock_tables(visuals=(1, 92, 180, 327, 654, 3886)))
        problems = self.plan().problems
        self.assertEqual(problems, ["SpellVisual.dbc (stock) has no visual 13785"])

    def test_reference_rows_differ_between_combinations(self):
        tables = S.stock_tables(cast_times=tuple((i, 1700 if ms == 1500 else ms) for i, ms in S.CAST_TIMES))
        S.write_patch(self.patches, "Patch-Y.MPQ", {"SpellCastTimes": S.stock_tables()["SpellCastTimes"]})
        S.write_stock(self.dbc, tables)
        problems = self.plan().problems
        self.assertIn("SpellCastTimes 6 holds another value in the copy no packs read (castMs 1500)", problems)

    def test_unreadable_archive(self):
        with open(os.path.join(self.patches, "patch-T.MPQ"), "wb") as f:
            f.write(b"not an archive")
        problems = self.plan().problems
        self.assertTrue(any(p.startswith("cannot read patch-T.MPQ") for p in problems), problems)

    # --- a second run

    def test_rerun_is_already_up_to_date(self):
        S.write_patch(self.patches, "patch-R.MPQ", {"Spell": S.spell_table([(90170, "Made Up Backpack")])})
        first = self.plan(with_bounds=bounds())
        self.assertEqual(first.problems, [])
        self.assertEqual(sorted(first.targets["patch-4.MPQ"]), sorted([TITLES, ICONS, DISPLAYS]))
        S.write_patch(self.patches, "patch-R.MPQ", {"Spell": first.targets["patch-R.MPQ"][SPELL]})
        files = dict(S.marker())
        files.update(first.targets["patch-4.MPQ"])
        S.write_patch(self.patches, "patch-4.MPQ", files=files)
        again = self.plan(with_bounds=bounds())
        self.assertEqual(again.problems, [])
        self.assertEqual(again.own_state, "the café's")
        self.assertIn("Spell.dbc from patch-R.MPQ -> patch-R.MPQ (already up to date)", self.lines(again))
        self.assertIn("GameObjectDisplayInfo.dbc from patch-4.MPQ -> patch-4.MPQ (already up to date)",
                      self.lines(again))
        self.assertEqual(again.targets, {})
        # without the manifest the café's display rows are recognised, not compared
        self.assertIn("GameObjectDisplayInfo.dbc from patch-4.MPQ -> patch-4.MPQ (24 the café's (bounds at build))",
                      self.lines(self.plan()))

    def test_changed_row_is_updated(self):
        S.write_patch(self.patches, "patch-R.MPQ", {"Spell": S.spell_table()})
        first = self.plan()
        spells = DbcTable.from_bytes(first.targets["patch-R.MPQ"][SPELL], schemas.get("Spell"))
        row = spells.by_id()[100903]
        spells.set(row, "spellVisualID[0]", 92)
        S.write_patch(self.patches, "patch-R.MPQ", {"Spell": spells})
        again = self.plan()
        self.assertIn("Spell.dbc from patch-R.MPQ -> patch-R.MPQ (1 to update, 35 up to date)", self.lines(again))
        notes = [n for s in again.sources["Spell"] for n in s.result.notes if "updated" in n]
        self.assertEqual(notes, ["spell 100903 Pull Shot: updated (spellVisualID[0])"])

    def test_earlier_cafe_copy_over_a_realm_copy(self):
        # patch-4 held the stock SpellIcon.dbc; now the realm's locale patch has its own. patch-4 loads over every
        # locale patch, so the realm's copy decides and patch-4's copy goes (it would hide the realm's changes).
        files = dict(S.marker())
        files[ICONS] = S.stock_tables()["SpellIcon"].to_bytes()
        S.write_patch(self.patches, "patch-4.MPQ", files=files)
        S.write_patch(self.patches, os.path.join("enUS", "patch-enUS-8.MPQ"),
                      {"SpellIcon": S.stock_tables()["SpellIcon"]})
        plan = self.plan()
        self.assertEqual(plan.problems, [])
        self.assertIn("SpellIcon.dbc from patch-enUS-8.MPQ -> patch-enUS-8.MPQ (14 to add)", self.lines(plan))
        self.assertEqual(plan.drops, {ICONS})

    def test_manifest_bounds_go_into_the_display_rows(self):
        plan = self.plan(with_bounds=bounds())
        (source,) = plan.sources["GameObjectDisplayInfo"]
        table = source.forged
        row = table.by_id()[19306]
        self.assertEqual(table.get_str(row, "modelName"),
                         "World\\Bleakhold\\Cafe\\KettleStoveSW\\BH_Cafe_KettleStoveSW.m2")
        self.assertEqual([round(table.float_value(row, "geoBoxMin[%d]" % i), 4) for i in range(3)], [-0.5, -0.5, 0.0])
        self.assertEqual([round(table.float_value(row, "geoBoxMax[%d]" % i), 4) for i in range(3)], [0.5, 0.5, 1.06])
        self.assertEqual([table.get(row, "sound[%d]" % i) for i in range(10)], [0] * 10)

    # --- the server's SQL

    def test_server_sql_rows_in_the_cafe_ids(self):
        sql = os.path.join(self.tmp, "sql")
        os.makedirs(os.path.join(sql, "updates"))
        with open(os.path.join(sql, "updates", "rev_1.sql"), "w") as f:
            f.write("DELETE FROM `spell_dbc` WHERE `ID` = 100905;\n"
                    "INSERT INTO `spell_dbc` (`ID`, `Name_Lang_enUS`) VALUES (100905, 'Made (Up), it''s'), (5, 'x');\n"
                    "INSERT INTO `creature_template` (`name`, `entry`) VALUES ('Someone', 909321);\n")
        with open(os.path.join(sql, "updates", "04_ours.sql"), "w") as f:
            f.write("-- Generated by Tools/CafeForge/cafeforge_data.py\n"
                    "INSERT INTO `gameobject_template` (`entry`) VALUES (909300);\n")
        found = doctor.scan_server_sql([sql], CFG.ids)
        self.assertEqual(found, {"spell_dbc": {100905: os.path.join("updates", "rev_1.sql")},
                                 "creature_template": {909321: os.path.join("updates", "rev_1.sql")}})

    @unittest.skipUnless(os.path.isdir(os.path.join(SERVER_SRC, "data", "sql", "updates")),
                         "bleakserv checkout not found")
    def test_bleakserv_updates_leave_the_cafe_ids_free(self):
        self.assertEqual(doctor.scan_server_sql([os.path.join(SERVER_SRC, "data", "sql", "updates")], CFG.ids), {})

    # --- the command

    def test_doctor_command(self):
        S.write_patch(self.patches, "patch-R.MPQ", {"Spell": S.spell_table()})
        r = self.doctor()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for line in ("Café archive: patch-4.MPQ (new)", "  castMs 1500 -> SpellCastTimes 6 (1500 ms)",
                     "  durationMs -1 -> SpellDuration 6 (-1 ms)", "  range self -> SpellRange 1 ('Self Only')",
                     "  Spell.dbc from patch-R.MPQ -> patch-R.MPQ (36 to add)",
                     "      masks in use: highest 2; 160 free, 161 free",
                     "Archives a build writes: patch-4.MPQ (new), patch-R.MPQ (",
                     "No problems: cafeforge.py build can run."):
            self.assertIn(line, r.stdout)

    def test_an_earlier_build_in_out_counts_as_free_space(self):
        """`build --force` removes its earlier output first (forge.py), so doctor counts it as free too; the art stays
        and does not count. Sparse files: their size counts, they take no disk."""
        import argparse  # noqa: PLC0415
        import contextlib  # noqa: PLC0415
        import io  # noqa: PLC0415

        S.write_patch(self.patches, "patch-R.MPQ", {"Spell": S.spell_table()})
        out_dir = os.path.join(self.tmp, "out")

        def sparse(rel, size):
            path = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.truncate(size)

        def run():
            args = argparse.Namespace(config=catalog.CAFE_JSON, packs_from=config.RACES_JSON, patches=self.patches,
                                      dbc=self.dbc, manifest=None, server_sql=[], out=out_dir)
            text = io.StringIO()
            real = doctor.skins.free_space
            doctor.skins.free_space = lambda where: 1024 * 1024        # 1 MB free on the disk
            try:
                with contextlib.redirect_stdout(text):
                    rc = doctor.run(args)
            finally:
                doctor.skins.free_space = real
            return rc, text.getvalue()

        sparse("art/models/EspressoSW.m2", 600 * 1024 * 1024)        # the art stays: not free
        rc, text = run()
        self.assertEqual(rc, 1, text)
        self.assertIn("out has 1.0 MB free, a build needs about", text.replace(out_dir, "out"))
        sparse("client/patch-R.MPQ", 600 * 1024 * 1024)              # an earlier, uninstalled build
        rc, text = run()
        self.assertEqual(rc, 0, text)
        self.assertIn("1.0 MB and 600.0 MB of an earlier build there, which a build replaces", text)
        self.assertIn("No problems: cafeforge.py build can run.", text)

    def test_doctor_command_fails_on_a_problem(self):
        S.write_patch(self.patches, "patch-R.MPQ", {"Spell": S.spell_table([(100903, "Someone Else")])})
        sql = os.path.join(self.tmp, "sql")
        os.makedirs(sql)
        with open(os.path.join(sql, "x.sql"), "w") as f:
            f.write("INSERT INTO `npc_text` (`ID`, `text0_0`) VALUES (909300, 'made up');\n")
        r = self.doctor("--server-sql", sql)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("2 problem(s): a build would stop", r.stdout)
        self.assertIn("npc_text 909300 is in the server's SQL (x.sql)", r.stdout)
        self.assertIn("id 100903 is taken by 'Someone Else'", r.stdout)
        r = self.doctor("--packs-from", os.path.join(self.tmp, "none.json"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("error: ", r.stderr)


if __name__ == "__main__":
    unittest.main()
