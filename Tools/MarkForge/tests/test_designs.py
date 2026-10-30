"""The catalogue: twelve races, four original designs each, three colours each, matching the appearance catalogue,
every element valid, every design inking the body."""

import copy
import json
import os
import unittest

import common
import numpy as np

import markforge as MF
from mflib import MarkForgeError, designs as D


class Catalogue(unittest.TestCase):
    def test_twelve_races_load(self):
        pal, races = MF.load_data()
        self.assertEqual(list(races), MF.RACE_ORDER)
        keys = set()
        for rf, r in races.items():
            ds = r["designs"]["designs"]
            self.assertEqual(len(ds), 4, rf)
            self.assertEqual(len(r["palette"]["colours"]), 3, rf)
            self.assertEqual([c["glow"] for c in r["palette"]["colours"]], [True, True, False], rf)
            self.assertEqual(len(r["palette"]["eyes"]), 3, rf)
            for d in ds:
                self.assertTrue(d["lore"].strip())
                keys.add((rf, d["key"]))
        self.assertEqual(len(keys), 48)
        self.assertEqual([e["eye"] for e in pal["death_knight_eyes"]], [4, 5])

    def test_matches_the_appearance_catalogue(self):
        if not os.path.isfile(MF.CATALOGUE):
            self.skipTest("Tools/RaceForge/customize/catalogue.json is not there")
        pal, races = MF.load_data()
        self.assertEqual(MF.catalogue_problems(pal, races), [])

    def test_a_drifted_catalogue_is_refused(self):
        if not os.path.isfile(MF.CATALOGUE):
            self.skipTest("no catalogue")
        pal, races = MF.load_data()
        cat = json.load(open(MF.CATALOGUE))
        cat["races"]["Orc"]["colours"][0]["hex"] = "#000000"
        d = common.temp_dir("cat")
        p = os.path.join(d, "catalogue.json")
        json.dump(cat, open(p, "w"))
        probs = MF.catalogue_problems(pal, races, p)
        self.assertTrue(any("Orc colours" in x for x in probs))

    def test_paths_fit_the_client(self):
        pal, races = MF.load_data()
        for rf, r in races.items():
            for d in r["designs"]["designs"]:
                for c in r["palette"]["colours"]:
                    for sex in ("Male", "Female"):
                        self.assertLessEqual(len(MF.mark_path(rf, sex, d["key"], c["key"], True)), 259)

    def test_check_race_finds_mistakes(self):
        data = D.load_race("Orc")
        bad = copy.deepcopy(data)
        bad["designs"][0]["elements"].append({"on": "torso", "kind": "band", "t": 1, "motif": "dots", "n": 6})
        bad["designs"][1]["elements"].append({"on": "arm", "kind": "band", "t": 1, "motif": "dots", "n": 6.5})
        bad["designs"][2]["key"] = "Fel Scars"
        probs = D.check_race(bad, "Orc")
        self.assertTrue(any("goes round a limb" in p for p in probs))
        self.assertTrue(any("integer" in p for p in probs))
        self.assertTrue(any("letters and digits" in p for p in probs))

    def test_every_kind_is_used_and_every_design_inks(self):
        pal, races = MF.load_data()
        used = set()
        p = common.prepared()
        for rf, r in races.items():
            for d in r["designs"]["designs"]:
                used |= {e["kind"] for e in d["elements"]}
                for sex in ("Male", "Female"):
                    core, halo = D.paint_design(p.charts, d, sex)
                    self.assertGreater(int((core > 0.5).sum()), 30, f"{rf} {d['key']} {sex}")
        self.assertEqual(used, D.KINDS)

    def test_a_crack_does_not_follow_the_last_bit_of_the_unit(self):
        """len / 1.2 is often a whole number (18 -> 15 steps): the unit of another numpy or CPU differs in its last
        bit, and that must not add a step and change every later random draw of the walk (it did, on Dwarf
        female Ember Cracks between numpy 1.26 and 2.x)."""
        import math
        from unittest import mock
        p = common.prepared()
        e = {"on": "torso", "kind": "crack", "at": [0.5, 0.05], "dir": 20, "len": 18, "seed": 63, "branches": 3,
             "jag": 0.6, "w": 0.34}
        walks = []
        # Dwarf female's unit under numpy 2.5 and 1.26: 18 * u / (1.2 * u) is 14.999999999999998 for the first
        for bu in (0.00738204756734592, 0.0073820475673459125, math.nextafter(p.charts.bu, 0.0)):
            got = []
            with mock.patch.object(p.charts, "bu", bu), \
                    mock.patch.object(D.Painter, "_strokes", lambda self, e, cv, lines, **kw: got.append(lines)):
                painter = D.Painter(p.charts, "Male")
                painter.k_crack(e, painter.canvas("torso"))
            walks.append([len(pl) for pl in got[0]])
        self.assertEqual(walks[0][-1], 16)  # the trunk: 15 steps, 16 points
        self.assertEqual(walks[0], walks[1])
        self.assertEqual(walks[0], walks[2])

    def test_an_element_error_names_its_element(self):
        p = common.prepared()
        d = {"key": "Broken", "elements": [{"on": "arm", "kind": "line", "pts": [[0.2]]}]}
        with self.assertRaises(MarkForgeError) as cm:
            D.paint_design(p.charts, d, "Male")
        self.assertIn("element 1", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
