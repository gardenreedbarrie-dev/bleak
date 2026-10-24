"""Shared fixtures for the terrain tests: small made-up specs, cached builds, an output folder per build.

No Blizzard data: every path below is a made-up name; the tests only check structure.
"""

import copy
import os
import shutil
import sys
import tempfile

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from terrain import build as tbuild  # noqa: E402
from terrain import validate as tvalidate  # noqa: E402

GOLDEN_SPEC = {
    "map": {"directory": "GoldenT", "tiles": {"x": [32, 32], "y": [32, 32]}},
    "seed": 4242,
    "area_id": 77,
    "uid_base": 900,
    "heightmap": {
        "base": 3.0,
        "noise": [{"scale": 140, "amplitude": 4.0, "octaves": 2}],
        "features": [
            {"type": "hill", "center": [-200, -330], "radius": 80, "height": 18},
            {"type": "river", "path": [[0, -60], [-533.3, -120]], "width": 12, "bank": 10, "bed": -1.5},
            {"type": "flatten", "shape": {"circle": {"center": [-400, -400], "radius": 25}}, "height": None,
             "falloff": 15},
        ],
    },
    "textures": [
        {"name": "grass", "path": "Tileset\\Made\\Up\\GrassA.blp", "color": "#3c6e28"},
        {"name": "rock", "path": "Tileset\\Made\\Up\\RockA.blp", "color": "#777777"},
        {"name": "sand", "path": "Tileset\\Made\\Up\\SandA.blp", "color": "#c8b478", "mtxf_flags": 1},
    ],
    "texture_rules": [
        {"texture": "sand", "height": {"max": 0.5, "fade": 2.0}},
        {"texture": "rock", "slope": {"min": 12, "max": 25}},
    ],
    "doodads": [
        {"model": "World\\Made\\Up\\Tree.m2", "position": [-120, -260], "facing": 30, "radius": 6, "scale": 1.25},
        {"model": "World\\Made\\Up\\Rock.m2", "position": [-260, -200, 12.5], "rotation": [5, 40, -3]},
    ],
    "wmos": [
        {"model": "World\\wmo\\Made\\Up\\Hut.wmo", "position": [-400, -400], "facing": 90,
         "bounds": [[-6, -5, -1], [7, 5, 9]]},
    ],
    "water": [{"liquid_type": 1, "height": 0.0, "min_depth": 0.1,
               "shape": {"polyline": {"points": [[0, -60], [-533.3, -120]], "width": 30}}}],
    "holes": [{"shape": {"circle": {"center": [-470, -40], "radius": 6}}}],
    "pois": [{"name": "drop", "kind": "crate_drop", "position": [-300, -100], "radius": 5, "flatten": True}],
}

# 2 x 2 tiles with features that cross the tile edges (heights, a WMO and a doodad on the seams).
SEAM_SPEC = {
    "map": {"directory": "SeamT", "tiles": {"x": [31, 32], "y": [31, 32]}},
    "seed": 99,
    "area_id": 12,
    "areas": [{"area_id": 13, "shape": {"circle": {"center": [200, 200], "radius": 120}}}],
    "heightmap": {
        "base": 20.0,
        "noise": [{"scale": 200, "amplitude": 12, "octaves": 3}, {"scale": 30, "amplitude": 1.5}],
        "features": [
            {"type": "hill", "center": [0, 0], "radius": 160, "height": 35},
            {"type": "border", "inset": 10, "width": 60, "height": 30, "jitter": 8, "jitter_scale": 80},
        ],
    },
    "textures": [
        {"name": "g", "path": "Tileset\\Made\\Up\\G.blp"},
        {"name": "d", "path": "Tileset\\Made\\Up\\D.blp"},
        {"name": "r", "path": "Tileset\\Made\\Up\\R.blp"},
        {"name": "s", "path": "Tileset\\Made\\Up\\S.blp"},
        {"name": "c", "path": "Tileset\\Made\\Up\\C.blp"},
    ],
    "texture_rules": [
        {"texture": "d", "noise": {"scale": 50, "threshold": 0.1, "fade": 0.3}},
        {"texture": "s", "noise": {"scale": 70, "threshold": 0.3, "fade": 0.3, "seed": 4}},
        {"texture": "c", "shape": {"circle": {"center": [0, 0], "radius": 40}}, "fade": 30},
        {"texture": "r", "slope": {"min": 20, "max": 35}},
    ],
    "doodads": [{"model": "World\\Made\\Up\\Big.m2", "position": [0.5, -0.5], "radius": 20}],
    "wmos": [{"model": "World\\wmo\\Made\\Up\\Keep.wmo", "position": [2, 3], "radius": 45}],
}

_CACHE = {}


def spec(base, **changes):
    data = copy.deepcopy(base)
    data.update(changes)
    return data


def built(name: str, data: dict):
    """Build once per test run; returns (BuildResult, output folder)."""
    if name not in _CACHE:
        result = tbuild.build_from_dict(copy.deepcopy(data))
        out = tempfile.mkdtemp(prefix=f"mapforge-{name}-")
        tbuild.write(result, out, force=True, preview=False)
        _CACHE[name] = (result, out)
    return _CACHE[name]


def map_folder(out: str, directory: str) -> str:
    return os.path.join(out, "World", "Maps", directory)


def copy_output(out: str) -> str:
    dst = tempfile.mkdtemp(prefix="mapforge-copy-")
    shutil.copytree(out, dst, dirs_exist_ok=True)
    return dst


def validate(path: str, name=None, **kw):
    return tvalidate.validate_map(path, name, **kw)
