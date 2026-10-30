"""build, validate, art and the archives (sections 6.2-6.5, 6.10) on synthetic patch sets and art: patch-4.MPQ new
and rebuilt, the winning realm copies rebuilt in place, a re-run that changes nothing, a renamed asset dropped, the
refusals before anything is written, install.json's fingerprints, the checks, and ModelForge's real output for the
models it builds today.

    python3 -I Tools/CafeForge/tests/run_tests.py
"""

import contextlib
import io
import json
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
from cflib import archive, catalog, config, forge, marker, schemas, sqlout  # noqa: E402
from cflib import plan as planmod  # noqa: E402

import mpqpack  # noqa: E402
from rflib import install, update  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402

CAFEFORGE = os.path.join(TOOL, "cafeforge.py")
CFG = config.from_doc(catalog.load(), S.PACKS)
SPELL = schemas.archive_file("Spell")
TITLES = schemas.archive_file("CharTitles")
ICONS = schemas.archive_file("SpellIcon")
DISPLAYS = schemas.archive_file("GameObjectDisplayInfo")
ESPRESSO_ATLAS = "World\\Bleakhold\\Cafe\\EspressoSW\\BH_Cafe_EspressoSW_Atlas.blp"


def quiet(*_args):
    pass


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cafeforge-build-")
        self.patches = os.path.join(self.tmp, "patches")
        os.makedirs(self.patches)
        self.dbc = S.write_stock(os.path.join(self.tmp, "dbc"))
        self.art = S.write_art(os.path.join(self.tmp, "art"), CFG)
        self.out = os.path.join(self.tmp, "out")
        self.gen = os.path.join(self.tmp, "gen", "pending_db_world")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_tool(self, *args):
        return subprocess.run([sys.executable, "-I", CAFEFORGE, *args], capture_output=True, text=True)

    def build(self, *extra, art=None):
        return self.run_tool("build", "--patches", self.patches, "--dbc", self.dbc, "--out", self.out, "--art",
                             art or self.art, "--server-sql-out", self.gen, *extra)

    def install(self):
        self.assertEqual(install.run(self.out, self.patches, say=quiet), 0)

    def archive(self, *parts):
        return mpqpack.MpqArchive(os.path.join(*parts))

    def realm_patch(self):
        S.write_patch(self.patches, "patch-R.MPQ", {"Spell": S.spell_table([(90170, "Made Up Backpack")])},
                      files={"Interface\\Made\\Up.blp": b"made up"})

    def manifest(self):
        with open(os.path.join(self.out, "install.json"), encoding="utf-8") as f:
            return json.load(f)

    # --- a first build

    def test_first_build(self):
        self.realm_patch()
        r = self.build()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for line in ("Spell.dbc from patch-R.MPQ -> patch-R.MPQ (36 added)",
                     "GameObjectDisplayInfo.dbc: no patch (stock) -> patch-4.MPQ (24 added)",
                     "CharTitles.dbc: no patch (stock) -> patch-4.MPQ (2 added)",
                     "SpellIcon.dbc: no patch (stock) -> patch-4.MPQ (14 added)",
                     "written: %s (new; " % os.path.join(self.out, "client", "patch-4.MPQ"),
                     " checks, 0 failed", "Server SQL rev: %s%srev_" % (self.gen, os.sep), ".sql (written)"):
            self.assertIn(line, r.stdout)
        with self.archive(self.out, "client", "patch-4.MPQ") as a:
            names = {mpqpack.name_key(n) for n in a.names()}
            for name in [DISPLAYS, TITLES, ICONS, config.MARKER_FILE, config.MARKER_TEXTURE, ESPRESSO_ATLAS,
                         "Interface\\Icons\\BH_Cafe_Grinder.blp", S.SHARED_TEXTURE]:
                self.assertIn(mpqpack.name_key(name), names, name)
            self.assertNotIn(SPELL.lower(), {n.lower() for n in a.names()})           # patch-R's copy wins
            self.assertFalse([n for n in a.names() if "\\Cube\\" in n])               # ModelForge's test cube stays out
            parsed = marker.parse_marker(a.read(config.MARKER_FILE).decode("utf-8"))
            self.assertEqual(parsed["tool"], "CafeForge")
            self.assertEqual(parsed["files"][ESPRESSO_ATLAS], marker.sha256_of(a.read(ESPRESSO_ATLAS)))
            self.assertEqual(marker.blp_problems(os.path.join(self.art, "files", "Interface", "Icons",
                                                               "BH_Cafe_Grinder.blp")), [])
        with self.archive(self.out, "client", "patch-R.MPQ") as a:
            self.assertEqual(a.read("Interface\\Made\\Up.blp"), b"made up")            # the realm's files stay
            spells = DbcTable.from_bytes(a.read(SPELL), schemas.get("Spell"))
            self.assertEqual(spells.get_str(spells.by_id()[100903], "name[0]"), "Pull Shot")
            self.assertIn(90170, spells.ids())
        data = self.manifest()
        self.assertTrue(data["checks_passed"])
        entries = {e["rel"]: e for e in data["archives"]}
        self.assertEqual(sorted(entries), ["patch-4.MPQ", "patch-R.MPQ"])
        self.assertEqual(entries["patch-4.MPQ"]["origin"], "new")
        realm = os.path.join(self.patches, "patch-R.MPQ")
        self.assertEqual((entries["patch-R.MPQ"]["size"], entries["patch-R.MPQ"]["mtime_ns"]),
                         install.fingerprint(realm))
        for name in ("report.txt", "plan.json", os.path.join("server", "cafe_check.sql"),
                     os.path.join("server", "sql", sqlout.SQL_FILE)):
            self.assertTrue(os.path.isfile(os.path.join(self.out, name)), name)
        self.assertEqual(len(os.listdir(self.gen)), 1)

    def test_manifest_bounds_in_both_rows(self):
        self.realm_patch()
        self.assertEqual(self.build().returncode, 0)
        with self.archive(self.out, "client", "patch-4.MPQ") as a:
            table = DbcTable.from_bytes(a.read(DISPLAYS), schemas.get("GameObjectDisplayInfo"))
        row = table.by_id()[19306]
        low, high = S.model_bounds(19306)
        self.assertEqual([round(table.float_value(row, "geoBoxMax[%d]" % i), 4) for i in range(3)], high)
        self.assertEqual([round(table.float_value(row, "geoBoxMin[%d]" % i), 4) for i in range(3)], low)
        with open(os.path.join(self.out, "server", "sql", sqlout.SQL_FILE), encoding="utf-8") as f:
            sql = f.read()
        back = __import__("rflib.spells", fromlist=["parse_sql_rows"]).parse_sql_rows(sql, "gameobjectdisplayinfo_dbc")
        self.assertAlmostEqual(float(back[19306]["GeoBoxMaxZ"]), high[2], places=6)
        self.assertEqual(back[19306]["ModelName"],
                         "'World\\\\Bleakhold\\\\Cafe\\\\KettleStoveSW\\\\BH_Cafe_KettleStoveSW.m2'")

    def test_spell_dbc_in_patch_r_and_the_hd_pack(self):
        self.realm_patch()
        S.write_patch(self.patches, "Patch-Y.MPQ", {"Spell": S.spell_table([(90171, "Made Up HD")])})
        r = self.build()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("all packs: Spell.dbc from Patch-Y.MPQ -> Patch-Y.MPQ (36 added)", r.stdout)
        self.assertIn("no packs: Spell.dbc from patch-R.MPQ -> patch-R.MPQ (36 added)", r.stdout)
        self.assertEqual(sorted(os.listdir(os.path.join(self.out, "client"))),
                         ["Patch-Y.MPQ", "patch-4.MPQ", "patch-R.MPQ"])
        self.assertIn("all packs: what the 36 café spells point at is there", self.report())
        self.assertIn("no packs: what the 36 café spells point at is there", self.report())

    def test_locale_patch_winner_goes_to_its_place(self):
        S.write_patch(self.patches, os.path.join("enUS", "patch-enUS-8.MPQ"),
                      {"SpellIcon": S.stock_tables()["SpellIcon"]})
        r = self.build()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("SpellIcon.dbc from patch-enUS-8.MPQ -> patch-enUS-8.MPQ (14 added)", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "client", "enUS", "patch-enUS-8.MPQ")))
        self.assertIn("enUS/patch-enUS-8.MPQ", [e["rel"] for e in self.manifest()["archives"]])
        self.install()
        self.assertTrue(os.path.isfile(os.path.join(self.patches, "patch-4.MPQ")))

    def report(self):
        with open(os.path.join(self.out, "report.txt"), encoding="utf-8") as f:
            return f.read()

    # --- the next builds

    def test_rerun_after_install_changes_nothing(self):
        self.realm_patch()
        self.assertEqual(self.build().returncode, 0)
        self.install()
        r = self.build("--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for line in ("Spell.dbc from patch-R.MPQ -> patch-R.MPQ (already up to date)",
                     "GameObjectDisplayInfo.dbc from patch-4.MPQ -> patch-4.MPQ (already up to date)",
                     "patch-4.MPQ: already up to date (nothing written)",
                     "(already there with the same SQL: nothing written)",
                     "No archive to install"):
            self.assertIn(line, r.stdout)
        self.assertEqual(self.manifest()["archives"], [])
        self.assertEqual(len(os.listdir(self.gen)), 1)
        self.assertTrue(os.path.isdir(os.path.join(self.out, "old-patches")))  # --force keeps the install's backups
        self.assertEqual(install.run(self.out, self.patches, say=quiet), 0)       # "Nothing to do"

    def test_renamed_asset_is_dropped_from_patch_4(self):
        self.realm_patch()
        self.assertEqual(self.build().returncode, 0)
        self.install()
        shutil.rmtree(self.art)
        S.write_art(self.art, CFG, texture_suffix={"EspressoSW": "Atlas2"})
        r = self.build("--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # the new atlas added, the old one dropped, the marker file (its sha256 list) changed, the rest the same
        self.assertIn("written: %s (1 added, 1 changed, 87 the same, 1 dropped)" % os.path.join(
            self.out, "client", "patch-4.MPQ"), r.stdout)
        self.assertNotIn("patch-R.MPQ (", r.stdout.split("Spell.dbc")[0])
        with self.archive(self.out, "client", "patch-4.MPQ") as a:
            names = {n.lower() for n in a.names()}
        self.assertNotIn(ESPRESSO_ATLAS.lower(), names)
        self.assertIn(ESPRESSO_ATLAS.replace("_Atlas", "_Atlas2").lower(), names)
        self.assertIn(DISPLAYS.lower(), names)                                     # its kept copies stay
        self.assertEqual([e["rel"] for e in self.manifest()["archives"]], ["patch-4.MPQ"])
        self.install()
        self.assertEqual(self.run_tool("validate", "--out", self.out).returncode, 0)

    def test_a_realm_copy_below_patch_4_takes_over(self):
        # patch-4 holds the stock SpellIcon.dbc of the first build; then the realm ships a locale patch with its own
        # copy. patch-4 loads over every locale patch, so its copy goes and the realm's gets the rows.
        self.assertEqual(self.build().returncode, 0)
        self.install()
        S.write_patch(self.patches, os.path.join("enUS", "patch-enUS-8.MPQ"),
                      {"SpellIcon": S.stock_tables()["SpellIcon"]})
        r = self.build("--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("SpellIcon.dbc from patch-enUS-8.MPQ -> patch-enUS-8.MPQ (14 added)", r.stdout)
        self.assertIn("written: %s (0 added, 1 changed, 88 the same, 1 dropped)" % os.path.join(
            self.out, "client", "patch-4.MPQ"), r.stdout)
        with self.archive(self.out, "client", "patch-4.MPQ") as a:
            self.assertNotIn(ICONS.lower(), {n.lower() for n in a.names()})
            self.assertIn(TITLES.lower(), {n.lower() for n in a.names()})
        self.install()
        self.assertEqual(self.run_tool("validate", "--out", self.out).returncode, 0)

    def test_changed_bounds_update_the_display_rows(self):
        self.assertEqual(self.build().returncode, 0)
        self.install()
        with open(os.path.join(self.art, archive.MANIFEST), encoding="utf-8") as f:
            data = json.load(f)
        data["models"][1]["bounds"]["max"][2] = 9.5
        with open(os.path.join(self.art, archive.MANIFEST), "w", encoding="utf-8") as f:
            json.dump(data, f)
        r = self.build("--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("GameObjectDisplayInfo.dbc from patch-4.MPQ -> patch-4.MPQ (1 updated, 23 up to date)",
                      r.stdout)
        self.assertEqual(len(os.listdir(self.gen)), 2)                             # the rows changed: a new rev

    # --- refusals: nothing is written

    def refused(self, r, text):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(text, r.stderr)

    def test_patch_4_without_the_marker_is_refused(self):
        S.write_patch(self.patches, "patch-4.MPQ", files={"Interface\\Made\\Up.blp": b"made up"})
        self.refused(self.build(), "was not written by CafeForge")
        self.assertFalse(os.path.exists(self.out))

    def test_incomplete_art_is_refused(self):
        art = S.write_art(os.path.join(self.tmp, "art2"), CFG, skip_models=("TipJar",), skip_icons=("BH_Cafe_Tea",))
        r = self.build(art=art)
        self.refused(r, "ModelForge built 23 of the 24 café models; missing: TipJar")
        self.assertIn("13 of the 14 café icons", r.stderr)
        self.assertFalse(os.path.exists(self.out))

    def test_changed_art_file_is_refused(self):
        with open(archive.disk_path(self.art, ESPRESSO_ATLAS), "ab") as f:
            f.write(b"!")
        self.refused(self.build(), "changed since ModelForge built it")

    def test_other_manifests_are_refused(self):
        art = S.write_art(os.path.join(self.tmp, "art2"), CFG, version=2)
        self.refused(self.build(art=art), "is not a manifest of ModelForge version 1")
        with open(os.path.join(self.art, archive.MANIFEST), encoding="utf-8") as f:
            data = json.load(f)
        data["models"][1]["m2"] = "World\\Bleakhold\\Cafe\\Other\\BH_Cafe_Other.m2"
        with open(os.path.join(self.art, archive.MANIFEST), "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.refused(self.build(), "display 19300 (EspressoSW): ModelForge's model is World\\Bleakhold\\Cafe\\Other")

    def test_a_plan_problem_is_refused_before_the_art(self):
        S.write_patch(self.patches, "patch-R.MPQ", {"Spell": S.spell_table([(100903, "Someone Else")])})
        r = self.build(art=os.path.join(self.tmp, "nowhere"))
        self.refused(r, "id 100903 is taken by 'Someone Else'")
        self.assertNotIn("art", r.stderr.split("problem(s)")[0])

    def test_earlier_output_needs_force(self):
        self.assertEqual(self.build().returncode, 0)
        self.refused(self.build(), "already holds output")

    def test_out_inside_the_patch_folder_is_refused(self):
        self.out = os.path.join(self.patches, "out")
        self.refused(self.build(), "the launcher would publish it")

    def test_too_little_space_is_refused(self):
        self.realm_patch()
        args = ["build", "--patches", self.patches, "--dbc", self.dbc, "--out", self.out, "--art", self.art]
        saved = forge.skins.free_space
        forge.skins.free_space = lambda folder: 1024
        err = io.StringIO()
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                rc = __import__("cafeforge").main(args)
        finally:
            forge.skins.free_space = saved
        self.assertEqual(rc, 1)
        self.assertIn("needs", err.getvalue())
        self.assertIn("(patch-R.MPQ, patch-4.MPQ), has 0.0 GB", err.getvalue())
        self.assertFalse(os.path.exists(os.path.join(self.out, "client")))

    def test_a_failed_check_writes_no_rev_and_blocks_install(self):
        self.realm_patch()
        saved = forge.sqlout.dbc_sql
        forge.sqlout.dbc_sql = lambda *a, **k: saved(*a, **k).replace("'Pull Shot'", "'Pull Shoot'", 1)
        args = ["build", "--patches", self.patches, "--dbc", self.dbc, "--out", self.out, "--art", self.art,
                "--server-sql-out", self.gen]
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = __import__("cafeforge").main(args)
        finally:
            forge.sqlout.dbc_sql = saved
        self.assertEqual(rc, 1)
        self.assertIn("FAILED: server SQL: reads back as the client rows", out.getvalue())
        self.assertIn("Server SQL rev: not written (a check failed)", out.getvalue())
        self.assertFalse(os.path.exists(self.gen))
        self.assertFalse(self.manifest()["checks_passed"])
        with self.assertRaises(install.InstallError):
            install.run(self.out, self.patches, say=quiet)

    # --- install.json, validate

    def test_install_refuses_a_patch_folder_that_changed(self):
        self.realm_patch()
        self.assertEqual(self.build().returncode, 0)
        S.write_patch(self.patches, "patch-R.MPQ", {"Spell": S.spell_table([(90172, "Made Up Later")])})
        with self.assertRaises(install.InstallError) as cm:
            install.run(self.out, self.patches, say=quiet)
        self.assertIn("changed since the tool read it", str(cm.exception))
        r = self.run_tool("validate", "--out", self.out)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("changed since the build read it: build again", r.stdout)
        self.assertIn("install.json: marked as failed", r.stdout)
        self.assertFalse(self.manifest()["checks_passed"])

    def test_validate_before_and_after_install(self):
        self.realm_patch()
        self.assertEqual(self.build().returncode, 0)
        for when in ("before", "after"):
            r = self.run_tool("validate", "--out", self.out)
            self.assertEqual(r.returncode, 0, when + r.stdout + r.stderr)
            self.assertIn(" checks, 0 failed", r.stdout)
            self.assertIn("every player: SpellIcon.dbc in patch-4.MPQ holds the café's 14 rows", r.stdout)
            if when == "before":
                self.install()
        self.assertFalse(os.path.exists(os.path.join(self.out, "client", "patch-4.MPQ")))  # install moved it
        os.remove(os.path.join(self.patches, "patch-4.MPQ"))
        r = self.run_tool("validate", "--out", self.out)
        self.assertEqual(r.returncode, 1)
        self.assertIn("patch-4.MPQ is not in", r.stdout)

    def test_restore_takes_the_cafe_out_again(self):
        self.realm_patch()
        before = install.fingerprint(os.path.join(self.patches, "patch-R.MPQ"))
        self.assertEqual(self.build().returncode, 0)
        self.install()
        self.assertEqual(install.run(self.out, self.patches, restore=True, say=quiet), 0)
        self.assertFalse(os.path.exists(os.path.join(self.patches, "patch-4.MPQ")))
        self.assertEqual(install.fingerprint(os.path.join(self.patches, "patch-R.MPQ")), before)


class Art(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cafeforge-art-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_synthetic_art(self):
        art = archive.load_art(S.write_art(os.path.join(self.tmp, "art"), CFG), CFG)
        self.assertEqual(art.problems, [])
        self.assertEqual(art.summary(CFG), "24 of 24 café models, 14 of 14 icons")
        self.assertEqual(sorted(art.bounds), [d.id for d in CFG.displays])
        self.assertEqual(art.notes, ["not shipped: Cube (display None is not a café piece)"])
        self.assertFalse([n for n in art.files if "Cube" in n])
        self.assertEqual(archive.find_art(self.tmp), os.path.join(self.tmp, "art"))

    def test_marker_texture(self):
        a = marker.write_marker_blp(os.path.join(self.tmp, "a.blp"))
        b = marker.write_marker_blp(os.path.join(self.tmp, "b.blp"))
        self.assertEqual(marker.blp_problems(a), [])
        with open(a, "rb") as fa, open(b, "rb") as fb:
            self.assertEqual(fa.read(), fb.read())                                 # the same bytes every run
        self.assertEqual(marker.blp_problems(os.path.join(self.tmp, "nowhere.blp"))[:1] != [], True)

    def test_marker_file(self):
        text = marker.marker_text({"B\\x.blp": "2" * 64, "a\\y.m2": "1" * 64}, built="then", host="here")
        parsed = marker.parse_marker(text)
        self.assertEqual((parsed["tool"], parsed["version"], parsed["built"], parsed["host"]),
                         ("CafeForge", 1, "then", "here"))
        self.assertEqual(parsed["files"], {"B\\x.blp": "2" * 64, "a\\y.m2": "1" * 64})
        self.assertIsNone(marker.parse_marker("test\n"))                           # ModelForge's test patch
        self.assertNotEqual(text.strip().lower(), "test")

    @unittest.skipUnless(os.path.isfile(archive.MODELFORGE), "Tools/ModelForge not in this checkout")
    def test_modelforge_today(self):
        """ModelForge's real build of the models it has today (EspressoSW): read, checked, shipped with the made-up
        rest, and its bounds in the display row; with ModelForge's output alone a build refuses (M5 not done)."""
        out = os.path.join(self.tmp, "real")
        r = subprocess.run([sys.executable, "-I", CAFEFORGE, "art", "--out", out, "--only", "EspressoSW",
                            "--tex-scale", "0.125", "--jobs", "1"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("(1 of 24 café models, 0 of 14 icons)", r.stdout)
        self.assertIn("ModelForge built 1 of the 24 café models", r.stdout)
        real = os.path.join(out, "art")
        self.assertTrue(os.path.isfile(os.path.join(real, archive.MARKERS, "Marker.blp")))
        art = archive.load_art(real, CFG)
        self.assertEqual(art.models, {19300: "EspressoSW"})
        with open(os.path.join(real, archive.MANIFEST), encoding="utf-8") as f:
            data = json.load(f)
        (entry,) = [m for m in data["models"] if m["display"] == 19300]
        self.assertEqual(art.bounds[19300], (tuple(entry["bounds"]["min"]), tuple(entry["bounds"]["max"])))
        for name in [entry["m2"], entry["skin"]] + entry["textures"]:
            self.assertEqual(art.sha[name], data["files"][name], name)

        # the made-up art for everything else, ModelForge's EspressoSW in it
        mixed = S.write_art(os.path.join(self.tmp, "mixed"), CFG, skip_models=("EspressoSW",))
        with open(os.path.join(mixed, archive.MANIFEST), encoding="utf-8") as f:
            merged = json.load(f)
        merged["models"].append(entry)
        for name in [entry["m2"], entry["skin"]] + entry["textures"]:
            dest = archive.disk_path(mixed, name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(archive.disk_path(real, name), dest)
            merged["files"][name] = data["files"][name]
        with open(os.path.join(mixed, archive.MANIFEST), "w", encoding="utf-8") as f:
            json.dump(merged, f)
        patches = os.path.join(self.tmp, "patches")
        os.makedirs(patches)
        dbc = S.write_stock(os.path.join(self.tmp, "dbc"))
        build = os.path.join(self.tmp, "out")
        r = subprocess.run([sys.executable, "-I", CAFEFORGE, "build", "--patches", patches, "--dbc", dbc, "--out",
                            build, "--art", real], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ModelForge built 1 of the 24 café models", r.stderr)
        r = subprocess.run([sys.executable, "-I", CAFEFORGE, "build", "--patches", patches, "--dbc", dbc, "--out",
                            build, "--art", mixed], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with mpqpack.MpqArchive(os.path.join(build, "client", "patch-4.MPQ")) as a:
            with open(archive.disk_path(real, entry["m2"]), "rb") as f:
                self.assertEqual(a.read(entry["m2"]), f.read())
            table = DbcTable.from_bytes(a.read(DISPLAYS), schemas.get("GameObjectDisplayInfo"))
        row = table.by_id()[19300]
        self.assertEqual(table.get_str(row, "modelName"), entry["m2"])
        for i in range(3):
            self.assertAlmostEqual(table.float_value(row, "geoBoxMax[%d]" % i), entry["bounds"]["max"][i], places=5)


class Space(unittest.TestCase):
    def test_each_archive_whole_its_staging_and_the_new_files(self):
        tmp = tempfile.mkdtemp(prefix="cafeforge-space-")
        try:
            patches = os.path.join(tmp, "patches")
            S.write_patch(patches, "patch-R.MPQ", {"Spell": S.spell_table()}, files={"Big.bin": b"x" * 100000})
            ps = update.patch_tools().PatchSet.scan(patches, CFG.optional_packs)
            try:
                bounds = {d.id: S.model_bounds(d.id) for d in CFG.displays}
                plan = planmod.make_plan(CFG, ps, S.write_stock(os.path.join(tmp, "dbc")), bounds)
                own = archive.OwnPlan({"x": b"y" * 10}, [], False, None)
                realm = ps.find("patch-R.MPQ")
                unpacked = sum(b.file_size for b in realm.reader.blocks if b.flags & mpqpack.FILE_EXISTS)
                spell = len(plan.targets["patch-R.MPQ"][SPELL])
                self.assertEqual(archive.space_needed(plan, ps, own), archive.skins.SPACE_MARGIN + 2 * spell
                                 + os.path.getsize(realm.path) + unpacked + 2 * 10)
                self.assertGreater(unpacked, 100000)
                own.up_to_date = True
                self.assertEqual(archive.space_needed(plan, ps, own), archive.skins.SPACE_MARGIN + 2 * spell
                                 + os.path.getsize(realm.path) + unpacked)
            finally:
                ps.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
