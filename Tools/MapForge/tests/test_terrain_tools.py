"""CLI, preview PNG, sample spec, and (optionally) AzerothCore's real extractor.

The extractor test runs only when MAPFORGE_AC_EXTRACTOR points at a built map_extractor (and, optionally,
MAPFORGE_AC_VMAP4 at a vmap4_extractor); see terrain/ac_crosscheck.py.
"""

import copy
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_terrain_support import GOLDEN_SPEC, TOOL_DIR, built

from terrain import build as tbuild
from terrain import validate as tvalidate
from terrain.spec import load_spec


def read_png(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    chunks = []
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        crc = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])[0]
        assert crc == zlib.crc32(tag + body) & 0xFFFFFFFF, tag
        chunks.append((tag, body))
        pos += 12 + length
    return chunks


class TestPreview(unittest.TestCase):
    def test_png_is_valid(self):
        result, _ = built("golden", GOLDEN_SPEC)
        out = tempfile.mkdtemp()
        try:
            tbuild.write(result, out, force=True, preview=True)
            for name in ("preview.png", "heightmap.png"):
                chunks = read_png(os.path.join(out, name))
                self.assertEqual([c[0] for c in chunks], [b"IHDR", b"IDAT", b"IEND"])
                w, h, depth, ctype = struct.unpack(">IIBB", chunks[0][1][:10])
                self.assertEqual((w, h, depth, ctype), (257, 257, 8, 2))
                raw = zlib.decompress(chunks[1][1])
                self.assertEqual(len(raw), h * (1 + 3 * w))
                self.assertTrue(all(raw[r * (1 + 3 * w)] == 0 for r in range(h)))
        finally:
            shutil.rmtree(out)


class TestCli(unittest.TestCase):
    def test_build_and_validate_cli(self):
        out = tempfile.mkdtemp()
        spec_path = os.path.join(out, "spec.json")
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(GOLDEN_SPEC, f)
        try:
            code = subprocess.run([sys.executable, "-I", os.path.join(TOOL_DIR, "terrain", "build.py"), spec_path,
                                   os.path.join(out, "o"), "--quiet", "--no-preview"]).returncode
            self.assertEqual(code, 0)
            again = subprocess.run([sys.executable, "-I", os.path.join(TOOL_DIR, "terrain", "build.py"), spec_path,
                                    os.path.join(out, "o"), "--quiet", "--no-preview"], capture_output=True)
            self.assertEqual(again.returncode, 2)  # refuses to overwrite without --force
            run = subprocess.run([sys.executable, "-I", os.path.join(TOOL_DIR, "terrain", "validate.py"),
                                  os.path.join(out, "o"), "--json"], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout)
            doc = json.loads(run.stdout)
            self.assertEqual(doc["errors"], [])
            self.assertEqual(doc["summary"]["map"], "GoldenT")
        finally:
            shutil.rmtree(out)

    def test_validator_exit_code_on_error(self):
        out = tempfile.mkdtemp()
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = tvalidate.main([out, "--quiet"])
            self.assertEqual(code, 1)
        finally:
            shutil.rmtree(out)


SAMPLES = ("royale_v2.json", "royale_v1.json", "royale_draft.json")  # the first is the default (README)
# the packaging config each sample is built with (README "Build on the VPS"); the rest use v1's
SAMPLE_CONFIGS = {"royale_v2.json": "bleakhold_royale_v2.json"}


class TestSampleSpec(unittest.TestCase):
    def test_sample_specs_load(self):
        for name in SAMPLES:
            with self.subTest(name):
                spec = load_spec(os.path.join(TOOL_DIR, "specs", name))
                self.assertEqual(spec.directory, "BleakholdRoyale")
                self.assertEqual(len(spec.tiles), 9)
                self.assertEqual(spec.warnings, [])  # real kit paths, no TODO placeholders
                self.assertTrue(any(f["type"] == "border" for f in spec.features))
                self.assertFalse(spec.holes)  # ground everywhere for the parachute drop
        names = {p["name"] for p in load_spec(os.path.join(TOOL_DIR, "specs", "royale_draft.json")).pois}
        for poi in ("keep", "village", "watchtower", "crypt", "ford_camp"):
            self.assertIn(poi, names)

    def test_readme_builds_the_default_spec(self):
        with open(os.path.join(TOOL_DIR, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        self.assertIn(f"terrain/build.py Tools/MapForge/specs/{SAMPLES[0]}", readme)

    def test_sample_specs_match_packaging_config(self):
        # package.py refuses terrain whose directory or MCNK area ids differ from its config.
        for name in SAMPLES:
            with self.subTest(name):
                cfg_name = SAMPLE_CONFIGS.get(name, "bleakhold_royale.json")
                with open(os.path.join(TOOL_DIR, cfg_name), encoding="utf-8") as f:
                    cfg = json.load(f)
                allowed = {cfg["zone"]["id"]} | {z["id"] for z in cfg["zone"].get("subzones", [])}
                spec = load_spec(os.path.join(TOOL_DIR, "specs", name))
                self.assertEqual(spec.directory, cfg["map"]["directory"])
                self.assertEqual(spec.map_id, cfg["map"]["id"])
                self.assertIn(spec.area_id, allowed)
                self.assertTrue({a for a, _ in spec.areas} <= allowed)


@unittest.skipUnless(os.environ.get("MAPFORGE_AC_EXTRACTOR"), "set MAPFORGE_AC_EXTRACTOR to a built map_extractor")
class TestAzerothCoreExtractor(unittest.TestCase):
    def crosscheck(self, out, *extra):
        sys.path.insert(0, os.path.join(TOOL_DIR, "terrain"))
        import ac_crosscheck
        args = [out, "--extractor", os.environ["MAPFORGE_AC_EXTRACTOR"], *extra]
        if os.environ.get("MAPFORGE_AC_VMAP4"):
            args += ["--vmap4", os.environ["MAPFORGE_AC_VMAP4"]]
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = ac_crosscheck.main(args)
        return code, buf.getvalue()

    def test_extractor_accepts_and_matches(self):
        _, out = built("golden", GOLDEN_SPEC)
        code, log = self.crosscheck(out)
        self.assertEqual(code, 0, log)

    def test_per_chunk_and_per_reach_water_levels(self):
        # A river stepping down at two falls into a lake, a pond of another liquid type, partial chunks: every wet
        # cell's level comes through map_extractor at its own height.
        from test_terrain_water import WATER_SPEC
        _, out = built("water", WATER_SPEC)
        code, log = self.crosscheck(out)
        self.assertEqual(code, 0, log)

    def test_server_copy_without_modern_doodads(self):
        from test_terrain_assets import ASSET_SPEC, make_resolution
        from terrain.extra_assets import Resolution
        tmp = tempfile.mkdtemp()
        try:
            res = Resolution.load(make_resolution(os.path.join(tmp, "res")))
            tbuild.write(tbuild.build_from_dict(copy.deepcopy(ASSET_SPEC), res), os.path.join(tmp, "out"),
                         preview=False)
            code, log = self.crosscheck(os.path.join(tmp, "out"))
            self.assertEqual(code, 0, log)
            self.assertIn("server's extract copy", log)
            code, log = self.crosscheck(os.path.join(tmp, "out"), "--client")
            self.assertEqual(code, 0, log)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main(verbosity=2)
