"""CafeForge's command line and what it stands on: `data --check` on a clean tree, the DBC layouts against the
client's record classes (and the sibling tools' copies of the same tables), and patch-4.MPQ in RaceForge's registry
of taken archive names.

    python3 -I Tools/CafeForge/tests/run_tests.py
"""

import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.dont_write_bytecode = True
if TOOL not in sys.path:
    sys.path.insert(0, TOOL)

from cflib import config, schemas  # noqa: E402

from rflib import patchnames, schema_access  # noqa: E402

CAFEFORGE = os.path.join(TOOL, "cafeforge.py")
TAKEN = os.path.join(config.TOOLS_DIR, "RaceForge", patchnames.TAKEN_FILE)


def run(*args):
    return subprocess.run([sys.executable, "-I", CAFEFORGE, *args], capture_output=True, text=True)


class Command(unittest.TestCase):
    def test_data_check_on_a_clean_tree(self):
        r = run("data", "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("generated files are up to date", r.stdout)

    def test_unknown_command(self):
        self.assertEqual(run("nope").returncode, 2)

    def test_no_bytecode_in_the_tool(self):
        run("schemas", "--check")
        self.assertFalse([d for d, _, _ in os.walk(TOOL) if os.path.basename(d) == "__pycache__"])


class Layouts(unittest.TestCase):
    @unittest.skipUnless(schemas.default_rec_dir(), "WoW/Source/DB/Rec not in this checkout")
    def test_generated_schemas_match_the_client(self):
        r = run("schemas", "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(schemas.__file__, encoding="utf-8") as f:
            self.assertEqual(f.read(), schemas.module_text(schemas.default_rec_dir()),
                             "run cafeforge.py schemas --write")

    def test_sizes(self):
        # section 6.4: GameObjectDisplayInfo 19 columns / 76 bytes, CharTitles 37 / 148, SpellIcon 2 / 8
        for name, columns, size in (("GameObjectDisplayInfo", 19, 76), ("CharTitles", 37, 148), ("SpellIcon", 2, 8)):
            schema = schemas.get(name)
            self.assertEqual((schema.num_columns, schema.row_size), (columns, size), name)

    def test_the_same_layouts_as_the_sibling_tools(self):
        sys.path.append(os.path.join(config.TOOLS_DIR, "MapForge"))
        from dbc import layout  # noqa: E402  (Tools/MapForge)
        self.assertEqual(schemas.get("GameObjectDisplayInfo").columns, layout.get("GameObjectDisplayInfo").columns)
        self.assertEqual(schemas.get("SpellIcon").columns, schema_access.get("SpellIcon").columns)
        for name in ("Spell",) + config.REFERENCE_TABLES:
            self.assertIs(schemas.get(name), schema_access.get(name), name)


class Registry(unittest.TestCase):
    def test_patch_4_is_registered(self):
        taken = patchnames.load_taken(TAKEN)
        self.assertIn(patchnames.name_key(config.OWN_ARCHIVE), taken)
        self.assertIn("CafeForge", taken[patchnames.name_key(config.OWN_ARCHIVE)])
        self.assertNotIn("4", patchnames.free_characters(taken))

    def test_patch_4_sorts_between_the_stock_and_the_lettered_patches(self):
        patches = __import__("rflib.update", fromlist=["patch_tools"]).patch_tools()
        key = patches.sort_key
        self.assertLess(key("Data\\patch-3.MPQ"), key("Data\\patch-4.MPQ"))
        self.assertLess(key("Data\\patch-4.MPQ"), key("Data\\patch-A.MPQ"))
        self.assertLess(key("Data\\patch-4.MPQ"), key("Data\\Patch-Y.MPQ"))


class Ci(unittest.TestCase):
    """Section 7.5 C: CI (the checks job of build.yml) runs every café gate on every push."""

    def test_build_yml_runs_every_cafe_gate(self):
        with open(os.path.join(os.path.dirname(config.TOOLS_DIR), ".github", "workflows", "build.yml"),
                  encoding="utf-8") as f:
            workflow = f.read()
        for line in ("bash Tools/UiLint/check.sh", "bash Server/mod-bleakhold-ui/tests/run_tests.sh",
                     "python3 -I Tools/ModelForge/tests/run_tests.py", "python3 -I Tools/CafeForge/tests/run_tests.py",
                     "python3 -I Tools/CafeForge/cafeforge.py data --check"):
            self.assertIn(line, workflow)


if __name__ == "__main__":
    unittest.main()
