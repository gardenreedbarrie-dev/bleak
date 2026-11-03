"""Shared test fixtures: the models under test, built once per run into a temporary directory.

Every registered model (mflib/props, discovered) is tested. Environment:
  MF_MODELS=GrinderSW,GrinderOrg   test only these models (the library tests still run): a builder's quick loop
  MF_JOBS=2                        worker processes for the bake and the paint (default 2; the output is the
                                   same for any value)
The cube and EspressoSW are built with textures at full size (section 5.9), the others at --tex-scale 0.125."""

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

FULL = ("Cube", "EspressoSW")   # textures at full size (section 5.9); golden hashes kept from M1
CI_SCALE = 0.125


def selected_models():
    """The models under test: MF_MODELS (comma-separated) or every registered model."""
    env = os.environ.get("MF_MODELS", "").strip()
    if not env:
        return list(props.REGISTRY)
    return [n.strip() for n in env.split(",") if n.strip()]


def limited():
    return bool(os.environ.get("MF_MODELS", "").strip())


def selection_problems():
    """Why a selected model cannot be tested (unknown name, broken module), as messages."""
    out = []
    for name in selected_models():
        if name in props.REGISTRY:
            continue
        mod = props.module_name(name)
        if mod in props.BROKEN:
            out.append("%s: mflib/props/%s.py does not load:\n%s" % (name, mod, props.BROKEN[mod]))
        else:
            out.append("%s is not registered (no mflib/props/%s.py defining NAME = %r and build)" % (name, mod, name))
    return out


def tested_models():
    """The selected models that are registered (the others fail test_props.Registry)."""
    return [n for n in selected_models() if n in props.REGISTRY]


def tex_scale(name):
    return 1.0 if name in FULL else CI_SCALE


def jobs():
    try:
        return max(1, int(os.environ.get("MF_JOBS", "2")))
    except ValueError:
        return 2


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
    """The Built result of a full build of `name` (bake and particles on; textures at tex_scale(name)). A build
    that raises raises again for every test that asks, without building twice."""
    key = "built:" + name
    if key not in _STATE:
        try:
            _STATE[key] = B.build_prop(props.REGISTRY[name].build({}), workdir(), tex_scale(name), True, True, jobs(),
                                       False, lambda *_a: None)
        except Exception as e:  # noqa: BLE001
            _STATE[key] = e
    res = _STATE[key]
    if isinstance(res, Exception):
        raise res
    return res


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
