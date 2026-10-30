"""No game art in this repository. It is public on GitHub: Blizzard's and Ascension's textures, models, tables and
archives, and pictures made from them (renders, contact sheets, screenshots), never go into it. They stay on the
realm's server, where the tools make what the players get (Tools/RaceForge, Tools/MarkForge).

    python3 -I tests/test_no_game_art.py

checks every file git tracks and every new file it does not ignore, and runs the checker's own tests. A file breaks
the rules when

- it is game data (.blp .m2 .skin .anim .dbc .db2 .mpq .mdx .m3 .wmo .adt .wdt .wdl .bls, in any letter case), or
  starts like one (BLP, MD20/MD21, MPQ, WDBC/WDB2/WDC1-3, SKIN, MDLX, REVM) whatever its name, outside OWN_ART;
- it is a picture (.png .jpg .jpeg .tga .bmp .dds .gif .webp .tif .tiff .ico) outside OWN_ART and PICTURES;
- it is larger than SIZE_CAP outside BIG_FILES.

Add an entry only for files the project made itself (or third-party documentation pictures), with what made them.
Patterns: * is any part of a file or folder name, **/ any folders, {a,b} either. Standard library only.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GAME_DATA = (".blp", ".m2", ".skin", ".anim", ".dbc", ".db2", ".mpq", ".mdx", ".m3", ".wmo", ".adt", ".wdt", ".wdl",
             ".bls")
PICTURE = (".png", ".jpg", ".jpeg", ".tga", ".bmp", ".dds", ".gif", ".webp", ".tif", ".tiff", ".ico")
# the first four bytes of the client's file formats (a renamed texture, model, table or archive)
MAGIC = (b"BLP0", b"BLP1", b"BLP2", b"MD20", b"MD21", b"MPQ\x1a", b"MPQ\x1b", b"WDBC", b"WDB2", b"WDC1", b"WDC2",
         b"WDC3", b"SKIN", b"MDLX", b"REVM")
SIZE_CAP = 4 << 20  # bytes

# Our own art in the client's formats (and as pictures): pattern, what made it
OWN_ART = (
    ("Interface/AddOns/Bleakhold/Art/*.tga", "the Bleakhold addon's own sheets (emote wheel, glyphs, disc, white)"),
    ("Interface/AddOns/Bleakhold/Art/Royale/*.{tga,blp}",
     "the Royale HUD and island map: Tools/BlpConvert/make_royale_art.py, make_royale_hud_art.py"),
    ("Interface/Bleakhold/Emoji/Emoji*.blp", "the emoji bubbles: Tools/EmojiForge"),
    ("Interface/Bleakhold/Glue/Textures/Login*.blp", "the login screen: Tools/BlpConvert/make_login_art.py"),
)
# Pictures that are not game art: pattern, what they are
PICTURES = (
    ("Tools/BlpConvert/art/*.jpg", "the login screen's own source art"),
    ("Tools/Launcher/app/icons/*.{png,ico}", "the launcher's icons: Tools/Launcher/app/icons/make_icon.py"),
    ("Tools/Launcher/ui/assets/*.webp", "the launcher window's own pictures"),
    ("waystone.ico", "Bleakhold.exe's icon"),
    ("ThirdParty/freetype/docs/**/*.{png,jpg}", "FreeType's documentation"),
    ("ThirdParty/expat/doc/*.png", "Expat's documentation"),
)
# Files allowed above SIZE_CAP: pattern, why
BIG_FILES: tuple = ()


def pattern_regex(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if c == "*":
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        elif c == "{":
            end = pattern.index("}", i)
            out += "(?:" + "|".join(re.escape(p) for p in pattern[i + 1:end].split(",")) + ")"
            i = end
        else:
            out += re.escape(c)
        i += 1
    return re.compile(out + r"\Z")


def matches(path: str, entries) -> bool:
    return any(pattern_regex(p).match(path) for p, _ in entries)


def repo_files(root: str) -> list[str]:
    """The files git tracks and the new ones it does not ignore (every file but .git's without git)."""
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             check=True, capture_output=True).stdout
        return sorted({p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p})
    except (OSError, subprocess.CalledProcessError):
        files = []
        for top, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d != ".git"]
            files += [os.path.relpath(os.path.join(top, n), root).replace(os.sep, "/") for n in names]
        return sorted(files)


def problems(root: str, files: list[str] | None = None) -> list[str]:
    found = []
    for rel in repo_files(root) if files is None else files:
        path = os.path.join(root, rel)
        try:
            st = os.lstat(path)
        except OSError:
            continue  # deleted in the work tree
        if not os.path.isfile(path) or os.path.islink(path):
            continue
        try:
            with open(path, "rb") as f:
                head = f.read(4)
        except OSError as e:
            found.append(f"{rel}: cannot be read ({e.strerror})")
            continue
        ext = os.path.splitext(rel)[1].lower()
        own = matches(rel, OWN_ART)
        if ext in GAME_DATA and not own:
            found.append(f"{rel}: a {ext} file (game data) outside the list of our own art")
        elif head in MAGIC and not own:
            found.append(f"{rel}: starts like a game file ({head!r}) outside the list of our own art")
        elif ext in PICTURE and not own and not matches(rel, PICTURES):
            found.append(f"{rel}: a picture outside the lists of our own art and pictures (renders, contact sheets and "
                         "screenshots of game art stay out of the repository)")
        if st.st_size > SIZE_CAP and not matches(rel, BIG_FILES):
            found.append(f"{rel}: {st.st_size} bytes, more than {SIZE_CAP} (game data? else add it to BIG_FILES)")
    return found


class Repository(unittest.TestCase):
    def test_no_game_art(self):
        found = problems(ROOT)
        self.assertEqual(found, [], "\n" + "\n".join(found) + "\n(tests/test_no_game_art.py: what the rules are)")

    def test_every_entry_is_used(self):
        """An entry that matches nothing is a typo or a leftover."""
        files = repo_files(ROOT)
        for entries in (OWN_ART, PICTURES, BIG_FILES):
            for pattern, why in entries:
                rx = pattern_regex(pattern)
                self.assertTrue(any(rx.match(f) for f in files), f"{pattern} ({why}) matches no file")


class Checker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="no-game-art-")
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, rel: str, data: bytes = b"text\n"):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return rel

    def check(self, *rels):
        return problems(self.root, list(rels))

    def test_patterns(self):
        rx = pattern_regex("A/**/*.{png,jpg}")
        self.assertTrue(rx.match("A/x.png") and rx.match("A/b/c/x.jpg"))
        self.assertFalse(rx.match("A/x.tga") or rx.match("B/A/x.png") or rx.match("A/x.png.txt"))
        self.assertFalse(pattern_regex("A/*.tga").match("A/B/x.tga"))

    def test_game_data_in_any_case(self):
        for name in ("HumanMaleSkin00_00.BLP", "HumanMale.M2", "HumanMale00.skin", "HumanMale0060-00.Anim",
                     "CharSections.dbc", "patch-6.MPQ", "Model.MDX", "Map.wmo", "Map_32_32.adt"):
            rel = self.put(f"Character/Human/Male/{name}")
            self.assertEqual(len(self.check(rel)), 1, name)

    def test_renamed_game_file(self):
        for head in (b"BLP2", b"MD20", b"MPQ\x1a", b"WDBC", b"SKIN"):
            rel = self.put("Tools/x/fixture.bin", head + b"\0" * 60)
            self.assertIn("starts like a game file", " ".join(self.check(rel)))

    def test_own_art_passes(self):
        rels = [self.put("Interface/Bleakhold/Emoji/Emoji000.blp", b"BLP2" + b"\0" * 60),
                self.put("Interface/AddOns/Bleakhold/Art/Royale/Ring.blp", b"BLP2" + b"\0" * 60),
                self.put("Interface/AddOns/Bleakhold/Art/Glyphs.tga")]
        self.assertEqual(self.check(*rels), [])
        # not a subfolder of an entry, not another name
        bad = [self.put("Interface/AddOns/Bleakhold/Art/Royale/Sub/Ring.blp"),
               self.put("Interface/Bleakhold/Emoji/Other.blp")]
        self.assertEqual(len(self.check(*bad)), 2)

    def test_pictures(self):
        sheet = self.put("Tools/MarkForge/previews/NightElf-Female.png")
        shot = self.put("docs/screenshot.JPG")
        self.assertEqual(len(self.check(sheet, shot)), 2)
        self.assertEqual(self.check(self.put("Tools/Launcher/app/icons/32x32.png")), [])

    def test_size_cap(self):
        rel = self.put("Tools/x/big.bin", b"\0" * (SIZE_CAP + 1))
        self.assertIn("more than", " ".join(self.check(rel)))
        self.assertEqual(self.check(self.put("Tools/x/small.bin", b"\0" * 1024)), [])

    def test_git_lists_new_files_but_not_ignored_ones(self):
        try:
            subprocess.run(["git", "init", "-q", self.root], check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("git is not installed")
        self.put(".gitignore", b"out/\n")
        self.put("out/Character/HumanMale.m2")
        self.put("Character/HumanMale.m2")
        found = problems(self.root)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].startswith("Character/HumanMale.m2:"))


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(
        sys.modules[__name__]))
    sys.exit(0 if result.wasSuccessful() else 1)
