"""Race mask rules and config validation."""

import os
import random
import sqlite3
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from rflib import config as configmod  # noqa: E402
from rflib import masks  # noqa: E402

ALLIANCE = 1101
HORDE = 690


def make_masks():
    return masks.FactionMasks(alliance=ALLIANCE, horde=HORDE)


def race(**overrides):
    data = {"id": 22, "name": "High Elf", "client_file_string": "HighElf", "template_race": 10, "faction": "alliance", "faction_race": 1}
    data.update(overrides)
    return configmod.parse_race(data, 0)


class MaskRuleTests(unittest.TestCase):
    def test_high_elf(self):
        high_elf = race()
        fm = make_masks()
        cases = {
            0: False,  # every race already
            0xFFFFFFFF: False,
            ALLIANCE: True,  # Language: Common and other Alliance-wide masks
            HORDE: False,  # Language: Orcish, although Blood Elves have it
            ALLIANCE | HORDE: True,  # every playable race
            512: True,  # Blood Elf only: racials, Thalassian
            512 | 2: True,
            1024: False,  # Draenei only
            (1 << 11) | (1 << 12): False,  # creature races only
            ALLIANCE | (1 << 15): True,  # Alliance plus a creature race bit
            1 << 21: False,  # already set
        }

        for mask, expected in cases.items():
            self.assertEqual(masks.wants_bit(mask, high_elf, fm, 10, True), expected, hex(mask))

    def test_eredar(self):
        eredar = race(id=23, name="Eredar", client_file_string="Eredar", template_race=11, faction="horde", faction_race=2)
        fm = make_masks()
        self.assertTrue(masks.wants_bit(HORDE, eredar, fm, 11, True))
        self.assertFalse(masks.wants_bit(ALLIANCE, eredar, fm, 11, True))
        self.assertTrue(masks.wants_bit(1024, eredar, fm, 11, True))
        self.assertTrue(masks.wants_bit(1024 | 2, eredar, fm, 11, True))
        self.assertFalse(masks.wants_bit(512, eredar, fm, 11, True))

    def test_template_only_policy(self):
        high_elf = race()
        fm = make_masks()
        self.assertTrue(masks.wants_bit(HORDE, high_elf, fm, 10, False))
        self.assertFalse(masks.wants_bit(ALLIANCE, high_elf, fm, 10, False))

    def test_sql_condition_matches_python_rule(self):
        # The SQL written for the server must pick exactly the masks the DBC pass picks.
        db = sqlite3.connect(":memory:")
        rng = random.Random(1234)
        samples = [0, 0xFFFFFFFF, ALLIANCE, HORDE, ALLIANCE | HORDE, 512, 1024, 1, 2, 1 << 21, 1 << 22, ALLIANCE | (1 << 21)]
        samples += [rng.getrandbits(12) for _ in range(300)] + [rng.getrandbits(32) for _ in range(100)]
        db.execute("CREATE TABLE t (`raceMask` INTEGER)")
        db.executemany("INSERT INTO t VALUES (?)", [(m,) for m in samples])

        for subject in (race(), race(id=23, name="Eredar", client_file_string="Eredar", template_race=11, faction="horde", faction_race=2)):
            for wide in (True, False):
                for source in (subject.template_race, subject.faction_race):
                    condition = masks.sql_condition("raceMask", subject, make_masks(), source, wide)
                    picked = {row[0] for row in db.execute(f"SELECT raceMask FROM t WHERE {condition}")}
                    expected = {m for m in samples if masks.wants_bit(m, subject, make_masks(), source, wide)}
                    self.assertEqual(picked, expected, (subject.name, wide, source))


class ConfigTests(unittest.TestCase):
    def test_default_config_loads(self):
        config = configmod.load(os.path.join(TOOL_DIR, "races.json"))
        self.assertEqual([(r.id, r.name, r.faction, r.template_race) for r in config.races], [(22, "High Elf", "alliance", 10), (23, "Eredar", "horde", 11)])
        self.assertEqual(config.races[0].client_file_string, "HighElf")
        self.assertEqual((config.races[0].start.map, config.races[0].start.zone), (0, 12))
        self.assertEqual((config.races[1].start.map, config.races[1].start.zone), (1, 14))

    def test_bad_configs_are_rejected(self):
        bad = [
            {"id": 32},
            {"id": 0},
            {"id": 25},  # a Pandaren id in later clients
            {"name": "Pandaren"},
            {"client_file_string": "PandarenX"},
            {"client_file_string": "High Elf"},
            {"client_file_string": "FourteenLetter"},
            {"faction": "neutral"},
            {"classes": [1, 10]},  # Monk
            {"names": {"xxXX": "Name"}},
            {"required_expansion": 3},
            {"id": True},
        ]

        for overrides in bad:
            with self.subTest(overrides=overrides), self.assertRaises(configmod.ConfigError):
                race(**overrides)

    def test_localized_names(self):
        subject = race(names={"deDE": "Hochelf"})
        names = subject.localized_names("name")
        self.assertEqual(len(names), 16)
        self.assertEqual(names[0], "High Elf")
        self.assertEqual(names[3], "Hochelf")
        self.assertEqual(names[9:], [""] * 7)
        self.assertEqual(subject.localized_names("nameFemale"), [])

    def test_duplicates_rejected(self):
        one = {"id": 22, "name": "A", "client_file_string": "A", "template_race": 10, "faction": "alliance", "faction_race": 1}

        with self.assertRaises(configmod.ConfigError):
            configmod.parse({"races": [one, dict(one, client_file_string="B")]})

        with self.assertRaises(configmod.ConfigError):
            configmod.parse({"races": [one, dict(one, id=23)]})

        with self.assertRaises(configmod.ConfigError):
            configmod.parse({"races": [one], "policy": {"reputation_from": "someone"}})


if __name__ == "__main__":
    unittest.main()
