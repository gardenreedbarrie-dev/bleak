"""Golden bytes and determinism for a tiny one-tile map.

The golden values pin the exact output. If the writer changes on purpose, rebuild the GoldenT spec
(test_terrain_support.GOLDEN_SPEC) and update GOLDEN below, after checking the new files with validate.py and the
AzerothCore cross-check (ac_crosscheck.py).
"""

import copy
import hashlib
import struct
import unittest

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_terrain_support import GOLDEN_SPEC, built

from terrain import build as tbuild

GOLDEN = {
    "World/Maps/GoldenT/GoldenT.wdt": "949e7e8dc6ce829b2ac4fd0afd8a26cb1c918931070e3bb523a23bc82890d13b",
    "World/Maps/GoldenT/GoldenT.wdl": "a5700bd0b3e3ce64e9a4c31fecc5cc29abe41ad87287797128fb61df3e65eea3",
    "World/Maps/GoldenT/GoldenT_32_32.adt": "8a328741b3932582ca11425cdf7281640ac1aac51430231fa4761318291c273c",
    "pois.json": "1e4173d7def0354188d9a106553952621f38597edec696d88ad70e13ecfbc7e3",
}
# MVER(18), MHDR(64): flags 0, mcin 64, mtex, mmdx, mmid, mwmo, mwid, mddf, modf, mfbo 0, mh2o, mtxf, mamp 0.
GOLDEN_ADT_HEAD = (
    "5245564d0400000012000000"
    "5244484d40000000"
    "0000000040000000481000009f100000d3100000e310000005110000111100006111000000000000a911000015710a00"
    "00000000000000000000000000000000"
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class TestGolden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result, _ = built("golden", GOLDEN_SPEC)

    def test_file_hashes(self):
        got = {name: digest(data) for name, data in self.result.files.items()}
        self.assertEqual(sorted(got), sorted(GOLDEN))
        for name, want in GOLDEN.items():
            self.assertEqual(got[name], want, name)

    def test_adt_head_bytes(self):
        adt = self.result.files["World/Maps/GoldenT/GoldenT_32_32.adt"]
        self.assertEqual(adt[:84].hex(), GOLDEN_ADT_HEAD)

    def test_wdt_bytes(self):
        # The whole WDT is small enough to state: MVER 18, MPHD 32 zero bytes, MAIN with tile 32,32, empty MWMO.
        wdt = self.result.files["World/Maps/GoldenT/GoldenT.wdt"]
        main = bytearray(32768)
        struct.pack_into("<I", main, 8 * (64 * 32 + 32), 1)
        want = (b"REVM" + struct.pack("<II", 4, 18) + b"DHPM" + struct.pack("<I", 32) + bytes(32) + b"NIAM"
                + struct.pack("<I", 32768) + bytes(main) + b"OMWM" + struct.pack("<I", 0))
        self.assertEqual(wdt, want)


class TestDeterminism(unittest.TestCase):
    def test_same_spec_same_bytes(self):
        a = tbuild.build_from_dict(copy.deepcopy(GOLDEN_SPEC))
        b = tbuild.build_from_dict(copy.deepcopy(GOLDEN_SPEC))
        self.assertEqual(a.files, b.files)

    def test_seed_changes_bytes(self):
        a, _ = built("golden", GOLDEN_SPEC)
        other = copy.deepcopy(GOLDEN_SPEC)
        other["seed"] = 4243
        b = tbuild.build_from_dict(other)
        adt = "World/Maps/GoldenT/GoldenT_32_32.adt"
        self.assertNotEqual(a.files[adt], b.files[adt])
        self.assertEqual(a.files["World/Maps/GoldenT/GoldenT.wdt"], b.files["World/Maps/GoldenT/GoldenT.wdt"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
