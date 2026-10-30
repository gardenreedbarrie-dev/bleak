"""The generated files (cflib/gen.py): fresh, byte-reproducible, and each one checked by what reads it: the C++
header compiled core-free with the module's warning flags, the Lua file run by the client's own Lua 5.1 (wowlua,
when Tools/UiLint has built it), the SQL applied twice to SQLite and held to bleakserv's base schema and SQL
codestyle when a bleakserv checkout sits next to this repository.

    python3 -I -m unittest discover -s Tools/CafeForge/tests -p "test_*.py"
"""

import contextlib
import copy
import io
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.dont_write_bytecode = True
if TOOL not in sys.path:
    sys.path.insert(0, TOOL)

from cflib import REPO  # noqa: E402
from cflib import catalog as C  # noqa: E402
from cflib import gen as G  # noqa: E402

DOC = C.load()
SERVER_SRC = os.environ.get("CAFEFORGE_SERVER_SRC") or os.path.join(os.path.dirname(REPO), "bleakserv")
BASE_SQL = os.path.join(SERVER_SRC, "data", "sql", "base", "db_world")
CODESTYLE = os.path.join(SERVER_SRC, "apps", "codestyle", "codestyle-sql.py")
WOWLUA = os.path.join(REPO, "Tools", "UiLint", "build", "wowlua")
CXX = [c for c in ("g++", "clang++") if shutil.which(c)]


def base_columns(table):
    """The column names of a table in bleakserv's data/sql/base/db_world/<table>.sql, in order."""
    with open(os.path.join(BASE_SQL, table + ".sql"), encoding="utf-8") as f:
        text = f.read()
    body = text[text.index("CREATE TABLE"):text.index("ENGINE")]
    return [m.group(1) for m in re.finditer(r"^\s*`([^`]+)`\s+\w+", body, re.M)]


def sql_tables(text):
    """{table: [columns]} of every INSERT of the generated SQL."""
    out = {}
    for m in re.finditer(r"INSERT INTO `(\w+)` \((.*?)\) VALUES", text, re.S):
        out[m.group(1)] = re.findall(r"`(\w+)`", m.group(2))
    return out


class Fresh(unittest.TestCase):
    def test_committed_files_are_up_to_date(self):
        self.assertEqual(G.generate(DOC, check=True), [], "run python3 -I Tools/CafeForge/cafeforge_data.py")

    def test_check_mode_of_the_script(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(TOOL, "cafeforge_data.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("up to date", r.stdout)

    def test_byte_reproducible(self):
        for rel, render in G.GENERATED.items():
            a = render(DOC)
            b = render(copy.deepcopy(C.load()))
            self.assertEqual(a, b, rel)
            self.assertTrue(a.endswith("\n") and not a.endswith("\n\n"), rel)
            self.assertNotIn("\r", a, rel)
            self.assertNotIn("\t", a, rel)
            self.assertFalse([n for n, line in enumerate(a.split("\n"), 1) if line != line.rstrip()], rel)

    def test_generate_writes_then_detects_stale_and_ignores_crlf(self):
        root = tempfile.mkdtemp(prefix="cafeforge-gen-")
        try:
            self.assertEqual(sorted(G.generate(DOC, repo=root)), sorted(G.GENERATED))
            self.assertEqual(G.generate(DOC, check=True, repo=root), [])
            path = G.repo_path(G.LUA_PATH, root)
            with open(path, encoding="utf-8", newline="") as f:
                text = f.read()
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text.replace("\n", "\r\n"))
            self.assertEqual(G.generate(DOC, check=True, repo=root), [])
            doc = copy.deepcopy(DOC)
            doc["recipes"][0]["names"]["1"][0] = "Cathedral Blackest"     # in the header and the Lua file
            self.assertEqual(sorted(G.generate(doc, check=True, repo=root)), [G.LUA_PATH, G.HEADER_PATH])
            doc["personas"][0]["name"] = "Sergeant Corwin Ashgrove the Second"   # also in the SQL
            self.assertEqual(sorted(G.generate(doc, check=True, repo=root)), sorted(G.GENERATED))
            self.assertEqual(G.generate(DOC, check=True, repo=root), [])
        finally:
            shutil.rmtree(root)


class Header(unittest.TestCase):
    TEXT = G.render_header(DOC)

    def test_core_free_ascii_and_short_lines(self):
        includes = re.findall(r"#include\s+(\S+)", self.TEXT)
        self.assertEqual(includes, ["<array>", "<cstddef>", "<cstdint>", "<string_view>"])
        self.assertTrue(all(ord(ch) < 128 for ch in self.TEXT), "the header is ASCII (UTF-8 text as escapes)")
        self.assertEqual([n for n, line in enumerate(self.TEXT.split("\n"), 1) if len(line) > 120], [])
        self.assertIn("do not edit", self.TEXT[:600])
        self.assertIn("namespace Bleakhold::CafeData", self.TEXT)

    def test_utf8_escapes(self):
        self.assertEqual(G.cpp_str("Café · 9"), '"Caf\\303\\251 \\302\\267 9"')
        self.assertEqual(G.cpp_str('say "hi"'), '"say \\"hi\\""')

    @unittest.skipUnless(CXX, "no C++ compiler")
    def test_compiles_core_free_and_holds_the_catalogue(self):
        """Built with the module's flags (and clang's extra ones) and run: counts, lookups, a layout row, UTF-8."""
        work = tempfile.mkdtemp(prefix="cafeforge-cxx-")
        src = os.path.join(work, "t.cpp")
        with open(src, "w", encoding="utf-8") as f:
            f.write(r'''#include "BleakholdCafeData.h"
#include <cstdio>
#include <cstring>
#include <string>
using namespace Bleakhold;
static_assert(CafeData::FindAction(3)->kind == 'H' && CafeData::FindAction(3)->goldHi == 850, "Pull Shot");
static_assert(CafeData::FindRecipe(219)->stepCount == 8 && CafeData::FindRecipe(219)->lines == 6, "M6");
static_assert(CafeData::StationIndex('G') == 0 && CafeData::StationIndex('V') == 6, "stations");
static_assert(CafeData::Personas[CafeData::PersonaIndex(909367)].enabled == false, "Maz'reth disabled");
int main()
{
    unsigned recipes = 0, layout1 = 0, chairs = 0;
    for (auto const& r : CafeData::Recipes)
        recipes += r.steps[r.stepCount - 1] == CafeData::ActionServe ? 1u : 0u;
    for (auto const& p : CafeData::Layout)
    {
        layout1 += p.cafeId == 1 ? 1u : 0u;
        chairs += p.role.substr(0, 6) == "chair_" ? 1u : 0u;
    }
    CafeData::Cafe const* sw = CafeData::FindCafe(1);
    bool utf8 = std::strcmp(CafeData::FindStaff(909303)->subname.data(), "Caf\xC3\xA9 Goods") == 0;
    std::printf("%u %u %u %u %zu %d %s\n", recipes, layout1, chairs, unsigned(CafeData::Personas.size()),
                CafeData::GameObjects.size(), utf8 ? 1 : 0, std::string(sw->name).c_str());
    return 0;
}
''')
        try:
            for cxx in CXX:
                flags = ["-std=c++17", "-Wall", "-Wextra", "-Wshadow", "-Werror"]
                if "clang" in cxx:
                    flags += ["-Wconversion", "-Wsign-conversion", "-Wpedantic"]
                exe = os.path.join(work, "t_" + cxx.replace("+", "x"))
                r = subprocess.run([cxx] + flags + ["-I", os.path.dirname(G.repo_path(G.HEADER_PATH)), src, "-o", exe],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, cxx + "\n" + r.stderr)
                out = subprocess.run([exe], capture_output=True, text=True).stdout.split()
                self.assertEqual(out[:6], ["38", "60", "24", "50", "44", "1"], cxx)
                self.assertEqual(" ".join(out[6:]), "The Lion's Roast")
        finally:
            shutil.rmtree(work)

    def test_layout_rows_match_the_catalogue(self):
        rows = G.layout_rows(DOC)
        self.assertEqual(len(rows), len(C.cafe_layout(DOC, 1)) + len(C.cafe_layout(DOC, 2)))
        self.assertEqual(G.rad(180), 3.1415927)
        self.assertEqual(G.rad(-90), -1.5707963)
        counter = next(r for r, _fp, _go in rows if r["role"] == "counter" and r["cafe"] == 1)
        self.assertIn('{ 1, 1, "counter", \'V\', 909312, false, 0, 0.8f, 0.0f, 0.0f, 3.1415927f, true,', self.TEXT)
        self.assertEqual(counter["work"], [[-0.8, -0.35], [-0.8, 0.35]])


class Lua(unittest.TestCase):
    TEXT = G.render_lua(DOC)

    def test_shape(self):
        self.assertTrue(self.TEXT.startswith("-- Bleakhold: the café catalogue. Generated by"))
        self.assertIn("local ADDON, ns = ...\n\nns.CafeData = {", self.TEXT)
        for key in ("cafes", "families", "stationOrder", "stations", "actions", "tiers", "recipes", "levels", "spells",
                    "models"):
            self.assertIn("\n    %s = {" % key, self.TEXT)
        self.assertNotRegex(self.TEXT.lower(), r"pandaren|\bmonk\b")

    @unittest.skipUnless(os.access(WOWLUA, os.X_OK), "wowlua not built (Tools/UiLint/build_wowlua.sh)")
    def test_runs_in_the_client_lua(self):
        work = tempfile.mkdtemp(prefix="cafeforge-lua-")
        try:
            data = os.path.join(work, "CafeData.lua")
            with open(data, "w", encoding="utf-8", newline="\n") as f:
                f.write(self.TEXT)
            probe = os.path.join(work, "probe.lua")
            with open(probe, "w", encoding="utf-8") as f:
                f.write('''local chunk = assert(host_loadfile(arg[1]))
local ns = {}
chunk("Bleakhold", ns)
local d = ns.CafeData
local n = 0
for _ in pairs(d.recipes) do n = n + 1 end
print(n, #d.stationOrder, d.recipes[213].name, d.actions[3].gold[2], d.actions[21].hordeName, d.spells.coffee[2],
    d.cafes[1].tagline, d.levels[10].xp)
''')
            r = subprocess.run([WOWLUA, "-p", data], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = subprocess.run([WOWLUA, probe, data], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(r.stdout.strip().split("\t"),
                             ["38", "7", "Eversong Sunleaf", "850", "Cactus Apple", "100931",
                              "Coffee · Tea · Shakes, by the Cathedral steps", "5640"])
        finally:
            shutil.rmtree(work)


class Sql(unittest.TestCase):
    TEXT = G.render_sql(DOC)

    def schema(self):
        """CREATE TABLEs for SQLite: bleakserv's base columns when the checkout is there, else gen's own lists."""
        tables = sql_tables(self.TEXT)
        out = []
        for t, cols in tables.items():
            if os.path.isdir(BASE_SQL):
                cols = base_columns(t)
            out.append("CREATE TABLE `%s` (%s);" % (t, ", ".join("`%s`" % c for c in cols)))
        return "\n".join(out)

    def test_every_insert_follows_its_range_delete(self):
        lines = self.TEXT.split("\n")
        owned = {t: (k, lo, hi) for t, k, lo, hi in G.OWNED}
        seen = []
        for i, line in enumerate(lines):
            if line.startswith("INSERT INTO"):
                t = re.match(r"INSERT INTO `(\w+)`", line).group(1)
                k, lo, hi = owned[t]
                self.assertEqual(lines[i - 1], "DELETE FROM `%s` WHERE `%s` BETWEEN %d AND %d;" % (t, k, lo, hi))
                seen.append(t)
        self.assertEqual(seen, [t for t, *_ in G.OWNED])
        self.assertEqual(len(re.findall(r"^DELETE", self.TEXT, re.M)), len(G.OWNED))

    def test_applies_twice_to_sqlite(self):
        db = sqlite3.connect(":memory:")
        db.executescript(self.schema())
        for _ in range(2):
            db.executescript(self.TEXT)
        count = {t: db.execute("SELECT COUNT(*) FROM `%s`" % t).fetchone()[0] for t, *_ in G.OWNED}
        models = sum(1 if p["kind"] == "named" else min(4, len(p["displays"])) for p in DOC["personas"]) + 10
        self.assertEqual(count, {"gameobject_template": 68, "gameobject_template_addon": 68, "creature_template": 60,
                                 "creature_template_model": models, "creature_template_addon": 10,
                                 "spell_custom_attr": 3, "item_template": 5, "npc_text": 9})
        self.assertEqual(db.execute("SELECT `name`, `size`, `Data0`, `Data1` FROM `gameobject_template` "
                                    "WHERE `entry` = 909334").fetchone(), ("Gnomish Whirligig Blender", 0.5, 1, 1))
        self.assertEqual(db.execute("SELECT `type`, `Data0`, `Data1` FROM `gameobject_template` "
                                    "WHERE `entry` = 909371").fetchone(), (7, 1, 1))
        self.assertEqual(db.execute("SELECT `name`, `faction`, `unit_flags`, `flags_extra`, `AIName` FROM "
                                    "`creature_template` WHERE `entry` = 909334").fetchone(),
                         ("Aldous Penn", 35, 0x302, 2, "NullCreatureAI"))
        self.assertEqual(db.execute("SELECT `npcflag`, `ScriptName`, `faction` FROM `creature_template` "
                                    "WHERE `entry` = 909305").fetchone(), (1, "npc_bh_cafe_owner", 35))
        self.assertEqual(db.execute("SELECT `npcflag`, `faction` FROM `creature_template` "
                                    "WHERE `entry` = 909309").fetchone(), (0, 29))
        self.assertEqual(db.execute("SELECT `emote` FROM `creature_template_addon` WHERE `entry` IN (909307, 909308) "
                                    "ORDER BY `entry`").fetchall(), [(173,), (69,)])
        self.assertEqual(db.execute("SELECT MAX(`Idx`) FROM `creature_template_model`").fetchone()[0], 3)
        self.assertEqual(db.execute("SELECT `CreatureDisplayID` FROM `creature_template_model` "
                                    "WHERE `CreatureID` = 909367").fetchall(), [(19182,)])
        self.assertEqual(db.execute("SELECT `spell_id`, `attributes` FROM `spell_custom_attr` ORDER BY 1").fetchall(),
                         [(100900, 0x01000000), (100936, 0x01000000), (100937, 0x01000000)])
        self.assertEqual(db.execute("SELECT `InventoryType`, `bonding`, `maxcount`, `SellPrice`, `armor` FROM "
                                    "`item_template` WHERE `entry` = 909380").fetchone(), (20, 1, 1, 0, 0))
        self.assertEqual(db.execute("SELECT `text0_0` FROM `npc_text` WHERE `ID` = 909300").fetchone()[0],
                         C.by_key(DOC["npcText"], "id")[909300]["text"])
        names = [r[0] for r in db.execute("SELECT `name` FROM `gameobject_template` ORDER BY `entry`")]
        self.assertIn("Lion's Roast Grinder", names)
        self.assertIn("Café marker: station spot", names)

    @unittest.skipUnless(os.path.isdir(BASE_SQL), "bleakserv checkout not found")
    def test_column_lists_are_the_base_schema(self):
        for table, cols in sql_tables(self.TEXT).items():
            base = base_columns(table)
            if table == "npc_text":
                self.assertEqual([c for c in base if c in cols], cols, table)
            else:
                self.assertEqual(cols, base, table)

    @unittest.skipUnless(os.path.isfile(CODESTYLE), "bleakserv checkout not found")
    def test_bleakserv_sql_codestyle(self):
        """bleakserv's codestyle-sql.py checks, except the template-delete guard: module SQL owns its id ranges and
        deletes them first by design (as the bleakserv War Herald rev does)."""
        with open(CODESTYLE, encoding="utf-8") as f:
            source = f.read()
        source = source[:source.index("# Collect all files from matching directories")]
        lint = type(sys)("codestyle_sql")
        exec(compile(source, "codestyle-sql.py", "exec"), lint.__dict__)  # noqa: S102
        work = tempfile.mkdtemp(prefix="cafeforge-sql-")
        try:
            path = os.path.join(work, "04.sql")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(self.TEXT)
            with open(path, encoding="utf-8") as f, contextlib.redirect_stdout(io.StringIO()) as out:
                for check in (lint.multiple_blank_lines_check, lint.trailing_whitespace_check, lint.sql_check,
                              lint.semicolon_check, lint.backtick_check, lint.non_innodb_engine_check):
                    check(f, path)
            self.assertFalse(lint.error_handler, out.getvalue())
        finally:
            shutil.rmtree(work)

    def test_quotes_are_doubled(self):
        self.assertIn("'Lion''s Roast Grinder'", self.TEXT)
        self.assertEqual(G.sql_str("it's"), "'it''s'")
        self.assertEqual(G.sql_val(None), "NULL")


if __name__ == "__main__":
    unittest.main()
