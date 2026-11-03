"""The emoji catalogue (emojis.json), the files generated from it and the committed art. Standard library only."""

import copy
import hashlib
import json
import os
import re
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)                          # Tools/EmojiForge
REPO = os.path.dirname(os.path.dirname(TOOL_DIR))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import emojiforge  # noqa: E402

# The keys of ids 0, 1, 2, ... as released. Ids go on the wire and saved wheels hold emoji:<key>, so this list only
# ever grows: append each new emoji here and to emojis.json, never reorder, rename or remove one.
FROZEN_KEYS = [
    "joy", "rofl", "sob", "heart_eyes", "in_love", "cool", "thinking", "scream", "rage", "clown",
    "skull", "smirk", "eye_roll", "grimace", "nerd", "money_face", "angel", "melting", "pleading", "huff",
    "monocle", "cowboy", "party_face", "sleeping", "mind_blown", "freezing", "overheated", "sick", "devil", "ghost",
    "alien", "robot", "wink", "flushed", "shush", "zany", "salute", "kiss", "frog", "puppy",
    "kitty", "see_no_evil", "unicorn", "dragon", "banana", "popcorn", "cheers", "pizza", "moai", "eyes",
    "fire", "hundred", "heart", "broken_heart", "sparkles", "thumbs_up", "thumbs_down", "clap", "pray", "muscle",
    "tada", "crown", "trophy", "swords", "zzz", "anger", "boom", "siren", "money_bag", "gift",
    "bullseye", "poop", "music", "gg", "ez", "lol", "rip", "omg", "wow", "nice",
    "brb", "afk", "glhf",
]


def raw_catalogue():
    with open(emojiforge.CATALOGUE, "r", encoding="utf-8") as f:
        return json.load(f)


class CatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = emojiforge.load_catalogue(emojiforge.CATALOGUE)

    def problems(self, data):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "emojis.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            with self.assertRaises(emojiforge.CatalogueError) as cm:
                emojiforge.load_catalogue(path)
        return cm.exception.problems

    def assertProblem(self, data, pattern):
        problems = self.problems(data)
        self.assertTrue(any(re.search(pattern, p) for p in problems),
                        "no problem matches %r in %r" % (pattern, problems))
        return problems

    def broken(self, change):
        data = raw_catalogue()
        change(data)
        return data

    def test_real_catalogue_loads(self):
        self.assertEqual(len(self.cat["emojis"]), 83)
        self.assertEqual(self.cat["kitBase"], 900000)
        self.assertEqual(self.cat["maxEmojis"], 256)
        self.assertEqual(sum(1 for e in self.cat["emojis"] if "noto" in e), 73)
        self.assertEqual([e["text"] for e in self.cat["emojis"] if "text" in e],
                         ["GG", "EZ", "LOL", "RIP", "OMG", "WOW", "NICE", "BRB", "AFK", "GLHF"])

    def test_norm(self):
        self.assertEqual(emojiforge.norm("  :Heart Eyes:  "), "heart_eyes")
        self.assertEqual(emojiforge.norm("heart_eyes"), "heart_eyes")
        self.assertEqual(emojiforge.norm("See  No\tEvil"), "see_no_evil")

    def test_gap_in_ids(self):
        self.assertProblem(self.broken(lambda d: d["emojis"].pop(5)), r"id 6, .*expected 5")

    def test_duplicate_key(self):
        self.assertProblem(self.broken(lambda d: d["emojis"][1].update(key="joy")), r"duplicate key 'joy'")

    def test_bad_key(self):
        self.assertProblem(self.broken(lambda d: d["emojis"][1].update(key="Rofl!")), r"key 'Rofl!' must match")
        self.assertProblem(self.broken(lambda d: d["emojis"][1].update(key="a" * 25)), r"must match")
        self.assertProblem(self.broken(lambda d: d["emojis"][1].update(key="rofl\n")), r"must match")

    def test_noto_and_text(self):
        self.assertProblem(self.broken(lambda d: d["emojis"][0].update(text="JOY")), r"exactly one of noto and text")
        self.assertProblem(self.broken(lambda d: d["emojis"][0].pop("noto")), r"exactly one of noto and text")

    def test_bad_sources(self):
        self.assertProblem(self.broken(lambda d: d["emojis"][0].update(noto="1F602")), r"noto '1F602'")
        self.assertProblem(self.broken(lambda d: d["emojis"][73].update(text="gg")), r"text 'gg'")
        self.assertProblem(self.broken(lambda d: d["emojis"][73].update(text="TOOLONG")), r"text 'TOOLONG'")

    def test_unknown_group(self):
        self.assertProblem(self.broken(lambda d: d["emojis"][2].update(group="people")),
                           r"group 'people' is not in groups")

    def test_unknown_field(self):
        self.assertProblem(self.broken(lambda d: d["emojis"][0].update(colour="red")), r"unknown field 'colour'")
        self.assertProblem(self.broken(lambda d: d.update(extra=1)), r"catalogue: unknown field 'extra'")
        self.assertProblem(self.broken(lambda d: d["font"].update(size=12)), r"font: unknown field 'size'")
        self.assertProblem(self.broken(lambda d: d["groups"][0].update(icon="x")), r"unknown field 'icon'")

    def test_too_many_entries(self):
        def grow(d):
            d["emojis"] = [{"id": i, "key": "e%d" % i, "name": "E %d" % i, "group": "text", "text": "A"}
                           for i in range(257)]
        self.assertProblem(self.broken(grow), r"257 entries; at most 256")

    def test_name_is_another_key(self):
        self.assertProblem(self.broken(lambda d: d["emojis"][1].update(name="Joy")),
                           r"name 'Joy' is the key of emojis\[0\]")

    def test_names_with_the_same_norm(self):
        self.assertProblem(self.broken(lambda d: d["emojis"][1].update(name="tears of joy")),
                           r"'Tears of Joy', 'tears of joy' are the same name")

    def test_bad_name(self):
        self.assertProblem(self.broken(lambda d: d["emojis"][1].update(name="Rolling: Laughing")),
                           r"name 'Rolling: Laughing'")
        self.assertProblem(self.broken(lambda d: d["emojis"][1].update(name="")), r"name ''")

    def test_changed_art_size(self):
        self.assertProblem(self.broken(lambda d: d["art"].update(size=128)), r"^art must be")

    def test_changed_texture(self):
        self.assertProblem(self.broken(lambda d: d.update(texture="Interface\\Emoji\\Emoji%03d")), r"^texture must be")

    def test_changed_constants(self):
        self.assertProblem(self.broken(lambda d: d.update(kitBase=900001)), r"^kitBase must be")
        self.assertProblem(self.broken(lambda d: d.update(maxEmojis=255)), r"^maxEmojis must be")
        self.assertProblem(self.broken(lambda d: d["noto"].update(commit="e20cbc2b")), r"noto.commit")
        self.assertProblem(self.broken(lambda d: d["font"].update(file="fonts/Missing.ttf")), r"font.file")
        self.assertProblem(self.broken(lambda d: d["font"].update(fill="ffd228")), r"font.fill")

    def test_reports_every_problem(self):
        def two(d):
            d["emojis"][1]["key"] = "joy"
            d["emojis"][2]["group"] = "people"
        problems = self.problems(self.broken(two))
        self.assertTrue(any("duplicate key" in p for p in problems), problems)
        self.assertTrue(any("not in groups" in p for p in problems), problems)

    def test_ids_are_append_only(self):
        keys = [e["key"] for e in self.cat["emojis"]]
        self.assertEqual(keys[:len(FROZEN_KEYS)], FROZEN_KEYS,
                         "an emoji was reordered, renamed or removed; ids are append-only (append new ones to "
                         "emojis.json and FROZEN_KEYS)")
        self.assertEqual(len(keys), len(FROZEN_KEYS), "append the new emojis to FROZEN_KEYS too")

    def test_generated_files_are_current(self):
        self.assertEqual(emojiforge.generate(self.cat, check=True), [],
                         "run python3 -I Tools/EmojiForge/emojiforge.py generate")

    def test_generated_text(self):
        for rel, render in emojiforge.GENERATED.items():
            text = render(self.cat)
            self.assertTrue(text.endswith("\n") and "\r" not in text, rel)
        lua = emojiforge.render_lua(self.cat)
        self.assertIn('{ id = 0, key = "joy", name = "Tears of Joy", group = "faces", '
                      'texture = "Interface\\\\Bleakhold\\\\Emoji\\\\Emoji000" },', lua)
        self.assertEqual(lua.count("{ id = "), 83)
        header = emojiforge.render_server_header(self.cat)
        self.assertIn("inline constexpr uint32_t EmojiCatalogueCount = 83;", header)
        key_lines = header.split("EmojiCatalogueKeys")[1].split("{\n", 1)[1].split("\n    };")[0].splitlines()
        self.assertTrue(all(line.startswith('        "') and len(line) <= 100 for line in key_lines), key_lines)
        self.assertEqual(re.findall(r'"([a-z0-9_]+)"', "\n".join(key_lines)), FROZEN_KEYS)

    def test_crlf_checkout_is_not_stale(self):
        with tempfile.TemporaryDirectory() as d:
            saved = emojiforge.REPO
            try:
                emojiforge.REPO = d
                self.assertEqual(sorted(emojiforge.generate(self.cat)), sorted(emojiforge.GENERATED))
                path = emojiforge.repo_path("Interface/Bleakhold/Emoji/NOTICE.md")
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
                with open(path, "w", encoding="utf-8", newline="\r\n") as f:
                    f.write(text)
                self.assertEqual(emojiforge.generate(self.cat, check=True), [])
                with open(path, "a", encoding="utf-8") as f:
                    f.write("edited by hand\n")
                self.assertEqual(emojiforge.generate(self.cat, check=True), ["Interface/Bleakhold/Emoji/NOTICE.md"])
            finally:
                emojiforge.REPO = saved

    def test_art_is_complete(self):
        self.assertEqual(emojiforge.check_art(self.cat), [])

    def test_check_art_finds_problems(self):
        cat = copy.deepcopy(self.cat)
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "Emoji000.blp"), "wb") as f:
                with open(os.path.join(emojiforge.EMOJI_DIR, "Emoji000.blp"), "rb") as src:
                    f.write(src.read())
            open(os.path.join(d, "Emoji099.blp"), "wb").close()
            cat["emojis"] = cat["emojis"][:2]
            problems = emojiforge.check_art(cat, d)
        self.assertTrue(any("Emoji001.blp (rofl) is missing" in p for p in problems), problems)
        self.assertTrue(any("Emoji099.blp is not in the catalogue" in p for p in problems), problems)
        self.assertTrue(any("LICENSE-Apache-2.0.txt is missing" in p for p in problems), problems)
        self.assertFalse(any("Emoji000" in p for p in problems), problems)

    def test_font_matches_the_catalogue(self):
        with open(os.path.join(TOOL_DIR, self.cat["font"]["file"]), "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), self.cat["font"]["sha256"])

    def test_notice(self):
        with open(os.path.join(REPO, "Interface", "Bleakhold", "Emoji", "NOTICE.md"), "r", encoding="utf-8") as f:
            notice = f.read()
        self.assertIn(self.cat["noto"]["commit"], notice)
        for name in ("LICENSE-OFL-NotoEmoji.txt", "LICENSE-Apache-2.0.txt", "LICENSE-OFL-Bangers.txt"):
            self.assertIn(name, notice)
        self.assertIn("| Emoji000.blp | joy | Tears of Joy | Noto emoji_u1f602.png |", notice)
        self.assertIn('| Emoji082.blp | glhf | GLHF | text "GLHF", Bangers |', notice)

    def test_patterns(self):
        patterns = emojiforge.noto_patterns(self.cat)
        self.assertEqual(patterns[:2], ["/LICENSE", "/README.md"])
        self.assertEqual(len(patterns), 2 + 73)
        self.assertIn("/3D/png/512/emoji_u2764.png", patterns)


if __name__ == "__main__":
    unittest.main()
