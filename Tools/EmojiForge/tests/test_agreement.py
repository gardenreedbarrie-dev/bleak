"""The emoji constants agree everywhere: emojis.json, the generated EmojiData.lua and server header, the client
header, the module's protocol code and config, Comm.lua and docs/BleakholdProtocol.md. Standard library only."""

import os
import re
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)                          # Tools/EmojiForge
REPO = os.path.dirname(os.path.dirname(TOOL_DIR))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import emojiforge  # noqa: E402

CONF_COOLDOWN = r"^BleakholdUi\.Emoji\.CooldownMs = (\d+)$"


def read(*parts):
    with open(os.path.join(REPO, *parts), "r", encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def find_int(test, text, pattern, what):
    m = re.search(pattern, text, re.M)
    test.assertIsNotNone(m, "%s not found (%s)" % (what, pattern))
    return int(m.group(1))


def lua_unescape(s):
    return re.sub(r"\\(.)", r"\1", s)


class AgreementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = emojiforge.load_catalogue()
        cls.codec = read("Server", "mod-bleakhold-ui", "src", "protocol", "BleakholdCodec.h")
        cls.client = read("WoW", "Common", "BleakholdEmoji.h")
        cls.server_header = read("Server", "mod-bleakhold-ui", "src", "BleakholdEmoji.h")
        cls.emoji_data = read("Interface", "AddOns", "Bleakhold", "EmojiData.lua")
        cls.comm = read("Interface", "AddOns", "Bleakhold", "Comm.lua")
        cls.doc = read("docs", "BleakholdProtocol.md")

    def lua_emojis(self):
        block = self.emoji_data[self.emoji_data.index("Data.emojis = {"):]
        rows = re.findall(r'^\s*\{ id = (\d+), key = "([^"]*)",.*?texture = "((?:[^"\\]|\\.)*)" \},?$', block, re.M)
        self.assertTrue(rows, "Data.emojis rows in EmojiData.lua")
        return [(int(i), k, lua_unescape(t)) for i, k, t in rows]

    def test_kit_base_and_max(self):
        base, top = self.cat["kitBase"], self.cat["maxEmojis"]
        self.assertEqual((base, top), (900000, 256))
        self.assertEqual(find_int(self, self.codec, r"\bEmojiKitBase = (\d+);", "Proto::EmojiKitBase"), base)
        self.assertEqual(find_int(self, self.codec, r"\bMaxEmojis = (\d+);", "Proto::MaxEmojis"), top)
        client_base = find_int(self, self.client, r"\bBLEAKHOLD_EMOJI_KIT_BASE = (\d+);", "BLEAKHOLD_EMOJI_KIT_BASE")
        self.assertEqual(client_base, base)
        self.assertEqual(find_int(self, self.client, r"\bBLEAKHOLD_EMOJI_MAX = (\d+);", "BLEAKHOLD_EMOJI_MAX"), top)

    def test_texture_format(self):
        texture = self.cat["texture"]
        m = re.search(r'\bBLEAKHOLD_EMOJI_TEXTURE\[\] = "((?:[^"\\]|\\.)*)";', self.client)
        self.assertIsNotNone(m, "BLEAKHOLD_EMOJI_TEXTURE in the client header")
        self.assertEqual(m.group(1).replace("\\\\", "\\").replace("%03u", "%03d"), texture)
        for emoji_id, key, path in self.lua_emojis():
            self.assertEqual(path, texture % emoji_id, "EmojiData texture of " + key)

    def test_comm_and_feature_bit(self):
        top = self.cat["maxEmojis"]
        intents = self.comm[self.comm.index("Comm.INTENTS = {"):]
        intents = intents[:intents.index("\n}")]
        m = re.search(r"^\s*EMOJI = \{ int\((\d+), (\d+)\) \},", intents, re.M)
        self.assertIsNotNone(m, "Comm.INTENTS EMOJI = { int(0, 255) }")
        self.assertEqual((int(m.group(1)), int(m.group(2))), (0, top - 1))
        feature = self.comm[self.comm.index("Comm.FEATURE = {"):]
        feature = feature[:feature.index("}")]
        bit = find_int(self, feature, r"\bEMOJI = (\d+)\b", "Comm.FEATURE.EMOJI")
        self.assertEqual(bit, 64)
        messages = read("Server", "mod-bleakhold-ui", "src", "protocol", "BleakholdMessages.h")
        self.assertEqual(find_int(self, messages, r"\bFeatureEmoji = (\d+),", "FeatureEmoji"), bit)
        self.assertEqual(find_int(self, self.doc, r"\b(\d+) emoji bubbles live\b", "the doc's feature bit"), bit)

    def test_catalogue_everywhere(self):
        entries = [(e["id"], e["key"]) for e in self.cat["emojis"]]
        self.assertEqual([(i, k) for i, k, _ in self.lua_emojis()], entries)
        count = find_int(self, self.server_header, r"\bEmojiCatalogueCount = (\d+);", "EmojiCatalogueCount")
        self.assertEqual(count, len(entries))
        start = self.server_header.index("EmojiCatalogueKeys[EmojiCatalogueCount] = {")
        keys = re.findall(r'"([^"]*)"', self.server_header[start:self.server_header.index("};", start)])
        self.assertEqual(keys, [k for _, k in entries])

    def test_doc(self):
        self.assertIn("\n## 13. Emoji bubbles\n", self.doc)
        self.assertIn("900000", self.doc)
        self.assertIn("| `EMOJI` |", self.doc)

    def test_config(self):
        conf = read("Server", "mod-bleakhold-ui", "conf", "mod_bleakhold_ui.conf.dist")
        mgr = read("Server", "mod-bleakhold-ui", "src", "BleakholdMgr.cpp")
        endpoint = read("Server", "mod-bleakhold-ui", "src", "protocol", "BleakholdEndpoint.h")
        self.assertRegex(conf, r"(?m)^BleakholdUi\.Emoji\.Enable = 1$")
        self.assertIn('GetOption<bool>("BleakholdUi.Emoji.Enable", true)', mgr)
        cooldown = find_int(self, conf, CONF_COOLDOWN, "conf BleakholdUi.Emoji.CooldownMs")
        self.assertEqual(cooldown, 2500)
        self.assertEqual(find_int(self, mgr, r'GetOption<uint32_t>\("BleakholdUi\.Emoji\.CooldownMs", (\d+)\)',
                                  "BleakholdMgr.cpp BleakholdUi.Emoji.CooldownMs"), cooldown)
        self.assertEqual(find_int(self, endpoint, r"\bemojiIntervalMs = (\d+);", "Limits::emojiIntervalMs"), cooldown)
        m = re.search(r"^\| `EMOJI` \| 1 per `BleakholdUi\.Emoji\.CooldownMs` \(([\d.]+) s\)", self.doc, re.M)
        self.assertIsNotNone(m, "the doc's EMOJI rate limit row")
        self.assertEqual(round(float(m.group(1)) * 1000), cooldown)

    def test_addon_waits_at_least_the_server_cooldown(self):
        animations = read("Interface", "AddOns", "Bleakhold", "Animations.lua")
        m = re.search(r"^A\.EMOJI_COOLDOWN = ([\d.]+)", animations, re.M)
        if not m:
            self.skipTest("Animations.lua has no A.EMOJI_COOLDOWN yet")
        conf = read("Server", "mod-bleakhold-ui", "conf", "mod_bleakhold_ui.conf.dist")
        cooldown = find_int(self, conf, CONF_COOLDOWN, "conf BleakholdUi.Emoji.CooldownMs")
        self.assertGreaterEqual(round(float(m.group(1)) * 1000), cooldown)


if __name__ == "__main__":
    unittest.main()
