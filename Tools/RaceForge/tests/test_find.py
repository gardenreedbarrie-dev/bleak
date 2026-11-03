"""raceforge.py find: which archive the client reads a file from, per pack combination, on a made-up game folder and
patch folder (every archive, name and line here is invented): the winner and the holders, --grep (context, the line
limit, a binary file), --out, --list, a file nowhere, a path a shell has mangled, alternate.MPQ, and an archive
without a listfile."""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)
TOOLS_DIR = os.path.dirname(TOOL_DIR)

for _path in (TOOL_DIR, os.path.join(TOOLS_DIR, "MpqPack")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from rflib import find  # noqa: E402
from tests import synth_skins as ss  # noqa: E402

TOOL = os.path.join(TOOL_DIR, "raceforge.py")
XML = "Interface\\GlueXML\\CharacterCreate.xml"
LUA = "Interface\\GlueXML\\CharacterCreate.lua"

STOCK_XML = b"""<Ui>
  <CheckButton name="CharacterCreateRaceButton1" inherits="CharacterCreateRaceButtonTemplate" id="1">
    <Anchors>
      <Anchor point="TOP"><Offset><AbsDimension x="-50" y="-61"/></Offset></Anchor>
    </Anchors>
  </CheckButton>
</Ui>
"""


def custom_xml() -> bytes:
    lines = ["<Ui>"]

    for i in range(1, 11):
        header = "BleakTestAllianceHeader" if i <= 5 else "BleakTestHordeHeader"
        lines += [f'  <CheckButton name="CharacterCreateRaceButton{i}" inherits="BigPortraitTemplate" id="{i}">',
                  "    <Anchors>",
                  f'      <Anchor point="TOP" relativeTo="{header}" relativePoint="BOTTOM">',
                  f'        <Offset><AbsDimension x="0" y="{-12 - ((i - 1) % 5) * 76}"/></Offset>',
                  "      </Anchor>",
                  "    </Anchors>",
                  "  </CheckButton>"]

    return ("\r\n".join(lines + ["</Ui>"]) + "\r\n").encode()


def run_tool(*args):
    return subprocess.run([sys.executable, "-I", TOOL, *args], capture_output=True, text=True, check=False)


class FindTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.client = os.path.join(self.tmp, "client")
        data = os.path.join(self.client, "Data")
        self.patches = os.path.join(self.tmp, "patches")
        os.makedirs(self.patches)
        ss.write_mpq(os.path.join(data, "common.MPQ"), {"Interface\\Glues\\Base.blp": b"made up"})
        ss.write_mpq(os.path.join(data, "enUS", "locale-enUS.MPQ"), {
            XML: STOCK_XML, LUA: b"MAX_RACES = 10;\n", "Interface\\GlueXML\\GlueParent.lua": b"-- stock parent\n"})
        ss.write_mpq(os.path.join(data, "patch-3.MPQ"), {"Interface\\GlueXML\\GlueParent.lua": b"-- patched parent\n"})
        ss.write_mpq(os.path.join(self.patches, "Patch-R.MPQ"), {LUA: b"MAX_RACES = 12;\n-- the realm's race patch\n"})
        # an HD pack archive (races.json's optional pack "hd"): the modern character creation screen
        ss.write_mpq(os.path.join(self.patches, "Patch-Y.MPQ"), {
            XML: custom_xml(), "Interface\\Glues\\Portrait.blp": b"BLP2\0\1\0\0" + bytes(range(256)) * 4,
            "Interface\\GlueXML\\Many.lua": "".join(f"local RaceButton{i} = {i}\n" for i in range(300)).encode()})

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def find(self, *args):
        return run_tool("find", "--patches", self.patches, "--client", self.client, *args)

    def test_winner_and_holders(self):
        result = self.find("Interface/GlueXML/CharacterCreate.xml")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[:4], [
            XML,
            "  all packs (hd): from Patch-Y.MPQ (patches, hd pack)",
            "    in, lowest first: enUS/locale-enUS.MPQ (game), Patch-Y.MPQ (patches, hd pack)",
            "  no packs: from enUS/locale-enUS.MPQ (game)",
        ])
        result = self.find("interface\\glueXML\\characterCreate.LUA")
        self.assertIn("  all packs (hd): from Patch-R.MPQ (patches)", result.stdout)
        self.assertIn("  no packs: from Patch-R.MPQ (patches)", result.stdout)
        result = self.find("Interface/GlueXML/GlueParent.lua")
        self.assertIn("  no packs: from patch-3.MPQ (game)", result.stdout)
        self.assertIn("    in, lowest first: enUS/locale-enUS.MPQ (game), patch-3.MPQ (game)", result.stdout)

    def test_grep(self):
        result = self.find("Interface/GlueXML/CharacterCreate.xml", "--grep", "racebutton1\"", "--grep", "x=\"-50\"",
                           "--after", "3")
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        self.assertIn('"racebutton1"" or "x="-50"" in the copy of Patch-Y.MPQ (all packs (hd)):', out)
        self.assertIn('   2: <CheckButton name="CharacterCreateRaceButton1" inherits="BigPortraitTemplate" id="1">', out)
        self.assertIn('   5  <Offset><AbsDimension x="0" y="-12"/></Offset>', out)
        self.assertIn("in the copy of enUS/locale-enUS.MPQ (no packs):", out)
        self.assertIn('  4: <Anchor point="TOP"><Offset><AbsDimension x="-50" y="-61"/></Offset></Anchor>', out)
        self.assertNotIn("CharacterCreateRaceButton2", out)

    def test_grep_limit_and_binary(self):
        result = self.find("Interface/GlueXML/Many.lua", "--grep", "RaceButton")
        shown = [line for line in result.stdout.splitlines() if ": local RaceButton" in line]
        self.assertEqual(len(shown), find.MAX_LINES)
        self.assertIn(f"... {300 - find.MAX_LINES} more matching lines not shown", result.stdout)
        result = self.find("Interface/Glues/Portrait.blp", "--grep", "BLP")
        self.assertEqual(result.returncode, 1)
        self.assertIn("  not a text file", result.stdout)

    def test_out(self):
        folder = os.path.join(self.tmp, "dump") + os.sep
        result = self.find("Interface/GlueXML/CharacterCreate.xml", "--out", folder)
        self.assertEqual(result.returncode, 0, result.stderr)

        with open(os.path.join(folder, "CharacterCreate.xml"), "rb") as fh:
            self.assertEqual(fh.read(), custom_xml())

        with open(os.path.join(folder, "CharacterCreate-2.xml"), "rb") as fh:
            self.assertEqual(fh.read(), STOCK_XML)

        self.assertIn("from Patch-Y.MPQ, for all packs (hd))", result.stdout)
        self.assertIn("from enUS/locale-enUS.MPQ, for no packs)", result.stdout)
        out = os.path.join(self.tmp, "one.lua")
        result = self.find("Interface/GlueXML/CharacterCreate.lua", "--out", out)

        with open(out, "rb") as fh:
            self.assertEqual(fh.read(), b"MAX_RACES = 12;\n-- the realm's race patch\n")

        self.assertFalse(os.path.exists(os.path.join(self.tmp, "one-2.lua")), "one copy for every combination")

    def test_list(self):
        result = self.find("--list", "Interface/GlueXML/")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertIn("Interface\\GlueXML\\ for all packs (hd): 4 files, 3 from the patches folder (*)", lines)
        rows = {line[2:].split()[0]: line for line in lines if line[:2] in ("* ", "  ") and "MPQ" in line}
        self.assertTrue(rows["CharacterCreate.xml"].startswith("* "))
        self.assertIn("Patch-Y.MPQ   (no packs: enUS/locale-enUS.MPQ)", rows["CharacterCreate.xml"])
        self.assertTrue(rows["CharacterCreate.lua"].startswith("* "))
        self.assertNotIn("(no packs", rows["CharacterCreate.lua"])
        self.assertTrue(rows["GlueParent.lua"].startswith("  ") and rows["GlueParent.lua"].endswith("patch-3.MPQ"))
        self.assertIn("(no packs: none)", rows["Many.lua"])
        # a path and --list in one run
        result = self.find("Interface/GlueXML/CharacterCreate.xml", "--list", "Interface\\Glues")
        self.assertIn("Interface\\Glues\\ for all packs (hd): 2 files, 1 from the patches folder (*)", result.stdout)

    def test_not_found_and_mangled_path(self):
        result = self.find("Interface/GlueXML/Nowhere.xml")
        self.assertEqual(result.returncode, 1)
        self.assertIn("  not in any archive the client loads", result.stdout)
        result = self.find("InterfaceGlueXMLCharacterCreate.xml")
        self.assertEqual(result.returncode, 1)
        self.assertIn("a shell drops the backslashes", result.stdout)
        result = self.find()
        self.assertEqual(result.returncode, 1)
        self.assertIn("give a file path", result.stderr)
        result = self.find("--list", "Interface/GlueXML", "--grep", "x")
        self.assertIn("--grep and --out need a file path", result.stderr)
        # an unquoted --list Interface\GlueXML, as a shell passes it on
        result = self.find("--list", "InterfaceGlueXML")
        self.assertEqual(result.returncode, 1)
        self.assertIn("note: InterfaceGlueXML has no folder in it: a shell drops the backslashes", result.stdout)
        result = self.find("--list", "Interface")
        self.assertNotIn("a shell drops the backslashes", result.stdout)

    def test_alternate_above_every_patch(self):
        ss.write_mpq(os.path.join(self.client, "Data", "alternate.MPQ"), {XML: b"<Ui/>\n"})
        result = self.find("Interface/GlueXML/CharacterCreate.xml")
        self.assertIn("  all packs (hd): from alternate.MPQ (game)", result.stdout)
        self.assertIn("  no packs: from alternate.MPQ (game)", result.stdout)
        self.assertNotIn("this tool does not read it", result.stdout)

    def test_archive_without_listfile(self):
        game = find.open_game(self.client, self.patches, {"hd": ["Data/Patch-Y.MPQ"]}, None)

        try:
            reader = game.patchset.find("Patch-Y.MPQ").reader
            has_file = reader.has_file
            reader.has_file = lambda name: False if name == find.mpqpack.LISTFILE else has_file(name)
            names, unlisted = find.listed(game, "Interface/GlueXML")
            self.assertEqual(unlisted, ["Patch-Y.MPQ (patches, hd pack)"])
            self.assertNotIn("Interface\\GlueXML\\Many.lua", names)
            self.assertIn("Interface\\GlueXML\\CharacterCreate.xml", names)  # the game folder's copy is listed
            out = io.StringIO()

            with redirect_stdout(out):
                find.list_folder(game, "Interface/GlueXML")

            self.assertIn("note: Patch-Y.MPQ (patches, hd pack) has no listfile", out.getvalue())
            # by name it is still found
            found = find.locate(game, XML)
            self.assertEqual(found[0].winner.name, "Patch-Y.MPQ")
        finally:
            game.close()

    def test_grep_lines(self):
        lines = ["a", "match one", "b", "c", "d", "match two", "e"]
        out, left = find.grep(lines, ["MATCH"], after=1)
        self.assertEqual(out, ["2: match one", "3  b", "--", "6: match two", "7  e"])
        self.assertEqual(left, 0)
        # no "--" without --after
        self.assertEqual(find.grep(lines, ["MATCH"]), (["2: match one", "6: match two"], 0))
        # the limit counts the "--" lines too, and what it leaves out is every match not shown
        many = [f"match {i}" if i % 3 == 0 else f"other {i}" for i in range(900)]
        out, left = find.grep(many, ["match"], after=1)
        self.assertEqual(len(out), find.MAX_LINES)
        self.assertIn("--", out)
        self.assertNotEqual(out[-1], "--")
        self.assertEqual(sum(1 for line in out if ": match" in line) + left, 300)

    def test_line_numbers_are_the_editors(self):
        # a Windows-1252 ellipsis (0x85, NEL in Latin-1), a form feed, U+2028: none ends a line
        for data in (b"-- Bleak\x85 glue\nlocal a = 1\nMAX_RACES = 12\n", b"line1\nx\x0cy\nMAX_RACES = 12\n",
                     "-- a\u2028b\nlocal a = 1\nMAX_RACES = 12\n".encode()):
            lines = find.text_lines(data)
            self.assertEqual(len(lines), 3, lines)
            self.assertEqual(find.grep(lines, ["MAX_RACES"]), (["3: MAX_RACES = 12"], 0))
        self.assertEqual(find.text_lines(b"-- Bleak\x85 glue\n")[0], "-- Bleak\u2026 glue")
        self.assertEqual(find.text_lines(b"a\r\nb\rc\n\nd"), ["a", "b", "c", "", "d"])
        self.assertEqual(find.text_lines(b""), [])
        self.assertIsNone(find.text_lines(b"\x00\x01binary"))
        self.assertEqual(find.text_lines(b"\xef\xbb\xbfone\r\ntwo"), ["one", "two"])
        self.assertEqual(find.archive_path("/Interface//GlueXML/x.xml"), "Interface\\GlueXML\\x.xml")
        args = SimpleNamespace(path=None, list=None, grep=None, out=None, after=0)

        with self.assertRaises(find.FindError):
            find.run(args)


if __name__ == "__main__":
    unittest.main()
