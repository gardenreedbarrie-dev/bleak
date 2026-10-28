"""Shared test fixtures: builds the M1 models once per test run into a temporary directory."""

import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
REPO = os.path.normpath(os.path.join(TOOL, "..", ".."))
sys.dont_write_bytecode = True
if TOOL not in sys.path:
    sys.path.insert(0, TOOL)

from mflib import build as B  # noqa: E402
from mflib import geom as G  # noqa: E402
from mflib import m2write as W  # noqa: E402
from mflib import props  # noqa: E402
from mflib import skinwrite as S  # noqa: E402

_STATE = {}


def workdir():
    if "dir" not in _STATE:
        _STATE["dir"] = tempfile.mkdtemp(prefix="modelforge-test-")
    return _STATE["dir"]


def cleanup():
    d = _STATE.pop("dir", None)
    if d and os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
    B.shutdown()


def built(name):
    """The Built result of a full build of `name` (cube and EspressoSW: textures at full size, section 5.9)."""
    key = "built:" + name
    if key not in _STATE:
        res = B.build_prop(props.REGISTRY[name].build({}), workdir(), 1.0, True, True, None, False,
                           lambda *_a: None)
        _STATE[key] = res
    return _STATE[key]


def read(path):
    with open(path, "rb") as f:
        return f.read()


def tiny_model(particles=True, name="BH_Cafe_Tiny"):
    """A small valid model (a beveled box, one emitter, a box hull) as (m2 bytes, skin bytes, M2Model, Skin)."""
    mesh = G.box(0.5, 0.5, 0.5, 0.05)
    mod = W.M2Model(name)
    for p, n, st in zip(mesh.p, mesh.n, mesh.st):
        mod.vertices.append((p, n, (st[0], st[1])))
    mod.textures = [("World\\Bleakhold\\Cafe\\Tiny\\BH_Cafe_Tiny_Atlas.blp", 3),
                    ("World\\Bleakhold\\Cafe\\Shared\\BH_Cafe_Steam.blp", 0)]
    mod.materials = [(0, 0)]
    if particles:
        mod.particles = [W.Particle((0.0, 0.0, 0.5), 1)]
    pos = [(-0.25, -0.25, 0), (0.25, -0.25, 0), (0.25, 0.25, 0), (-0.25, 0.25, 0), (-0.25, -0.25, 0.5),
           (0.25, -0.25, 0.5), (0.25, 0.25, 0.5), (-0.25, 0.25, 0.5)]
    tris = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7),
            (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    mod.collision_positions = pos
    mod.collision_tris = tris
    mod.collision_normals = B.hull_normals(pos, tris)
    skin = S.Skin(len(mesh.p))
    skin.indices = [i for t in mesh.t for i in t]
    skin.sections = [S.Section(0, 0, len(mesh.p), 0, len(skin.indices), (0, 0, 0.25), (0, 0, 0.25), 0.45)]
    skin.batches = [S.Batch(0, 0, 0)]
    return W.write_m2(mod), S.write_skin(skin), mod, skin


def header_array(data, off):
    return struct.unpack_from("<II", data, off)


def patch(data, off, fmt, *vals):
    b = bytearray(data)
    struct.pack_into(fmt, b, off, *vals)
    return bytes(b)


def native_harness():
    """Compiles tests/native/m2init_harness.cpp once; returns the binary path or None without g++."""
    if "harness" in _STATE:
        return _STATE["harness"]
    exe = None
    gxx = shutil.which("g++")
    if gxx:
        exe = os.path.join(workdir(), "m2init_harness")
        src = os.path.join(HERE, "native", "m2init_harness.cpp")
        r = subprocess.run([gxx, "-std=c++17", "-O1", "-w", "-I", REPO, src, "-o", exe], capture_output=True,
                           text=True)
        if r.returncode != 0:
            raise RuntimeError("m2init_harness does not compile:\n" + r.stderr[-4000:])
    _STATE["harness"] = exe
    return exe


def run_harness(*m2_paths):
    exe = native_harness()
    r = subprocess.run([exe] + list(m2_paths), capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr
