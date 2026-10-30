r"""The character model as the component compositor uses it.

A character's body is the geometry of its M2 whose batches sample texture type 1 (the per-character composite,
CharacterBaseSkin). Which geosets a naked character shows is ComponentData's default list (WoW/Source/Glue/
ComponentData.cpp: 0, then x01 of groups 1-18 with 702 for the ears) plus every id above 2000, which GeosRenderPrep
never hides (SetGeometryVisible(0, 2000, 0) in WoW/Common/ComponentCore/CharacterComponent.cpp). Hair styles
(group 0, ids 1-99) are left out: they change with the hair style.

The eye-glow geosets 1702 (the race's own glow, texture type 8) and 1703 (Death Knight glow, a fixed file: usually
Character\<Race>\<Sex>\deathKnightEyeGlow.blp) are read for the eye centres and for the eye sprite layout.

The M2 is parsed by Tools/ModelForge/mflib/m2check.py (loaded by file path: both tools name their package mflib).
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
import os
from dataclasses import dataclass, field

import numpy as np

from . import REPO, MarkForgeError

DEFAULT_GEOSETS = {0, 101, 201, 301, 401, 501, 601, 702, 801, 901, 1001, 1101, 1201, 1301, 1401, 1501, 1601, 1701,
                   1801}
EYE_GEOSETS = (1702, 1703)
_m2check = None


def m2check():
    global _m2check
    if _m2check is None:
        path = os.path.join(REPO, "Tools", "ModelForge", "mflib", "m2check.py")
        if not os.path.isfile(path):
            raise MarkForgeError(f"{path} is missing: MarkForge reads models with ModelForge's parser")
        spec = importlib.util.spec_from_file_location("markforge_m2check", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _m2check = mod
    return _m2check


def naked_visible(geoset: int) -> bool:
    return geoset in DEFAULT_GEOSETS or geoset > 2000


@dataclass
class Model:
    name: str
    sha1: str
    pos: np.ndarray  # (N, 3) rest pose; x forward (the sign is in .forward), y lateral (left +), z up
    nrm: np.ndarray  # (N, 3)
    uv: np.ndarray  # (N, 2) in 0..1, v down
    skin_tris: dict = field(default_factory=dict)  # geoset id -> (T, 3) vertex indices of type-1 batches
    eye_tris: dict = field(default_factory=dict)  # 1702/1703 -> (T, 3)
    eye_texture: str | None = None  # the file the 1703 batches sample
    eye_texture_slot: int | None = None  # its index in the model's texture list (for ReplaceTextureAtIndex)
    forward: float = 1.0  # sign of x toward the face

    def body_geosets(self) -> list[int]:
        return sorted(g for g in self.skin_tris if naked_visible(g))

    def body_tris(self) -> tuple[np.ndarray, np.ndarray]:
        """(T, 3) triangles of the naked body (type-1 batches of visible geosets) and (T,) their geoset ids."""
        tris, geos = [], []
        for g in self.body_geosets():
            t = self.skin_tris[g]
            tris.append(t)
            geos.append(np.full(len(t), g, np.int32))
        if not tris:
            raise MarkForgeError(f"{self.name}: no naked geoset samples texture type 1 (the character skin)")
        return np.concatenate(tris), np.concatenate(geos)

    def eye_centres(self) -> np.ndarray | None:
        """(forward, |lateral|, up) of the eye-glow geosets' vertices (1703, else 1702), averaged over both eyes."""
        for g in (1703, 1702):
            t = self.eye_tris.get(g)
            if t is not None and len(t):
                p = self.pos[np.unique(t)]
                return np.array([p[:, 0].mean() * self.forward, np.abs(p[:, 1]).mean(), p[:, 2].mean()])
        return None


def load(m2: bytes, skin: bytes, name: str) -> Model:
    m, _findings = m2check().parse(m2, skin, name)
    if "vertices" not in m or "skin" not in m or not m["skin"].get("ok"):
        raise MarkForgeError(f"{name}: the model or its 00.skin does not parse")
    verts = m["vertices"]
    pos = np.array([v[0] for v in verts], np.float64)
    nrm = np.array([v[1] for v in verts], np.float64)
    uv = np.array([v[2] for v in verts], np.float64)
    sk = m["skin"]
    lookup = np.array(sk["lookup"], np.int64)
    indices = np.array(sk["indices"], np.int64)
    textures = m["textures"]
    combos = m["textureCombos"]
    model = Model(name, hashlib.sha1(m2).hexdigest(), pos, nrm, uv)
    seen = set()
    for b in sk["batches"]:
        si = b["skinSectionIndex"]
        sec = sk["sections"][si]
        gid = sec["id"]
        try:
            tex_index = combos[b["textureComboIndex"]]
            tex = textures[tex_index]
        except (IndexError, KeyError):
            continue
        tri = lookup[indices[sec["indexStart"]:sec["indexStart"] + sec["indexCount"]]].reshape(-1, 3)
        if gid in EYE_GEOSETS:
            if (si, "eye") not in seen:
                seen.add((si, "eye"))
                prev = model.eye_tris.get(gid)
                model.eye_tris[gid] = tri if prev is None else np.concatenate([prev, tri])
            if gid == 1703 and tex["type"] == 0 and tex["path"]:
                model.eye_texture = tex["path"]
                model.eye_texture_slot = tex_index
            continue
        if tex["type"] != 1 or (si, "skin") in seen:
            continue
        seen.add((si, "skin"))
        prev = model.skin_tris.get(gid)
        model.skin_tris[gid] = tri if prev is None else np.concatenate([prev, tri])
    # the face looks along +x or -x: the head's normals say which
    tris, _ = model.body_tris()
    used = np.unique(tris)
    top = used[pos[used, 2] > pos[used, 2].min() + 0.85 * np.ptp(pos[used, 2])]
    if len(top):
        model.forward = 1.0 if nrm[top, 0].mean() >= 0 else -1.0
    return model


def load_files(m2_path: str, skin_path: str | None = None) -> Model:
    if skin_path is None:
        skin_path = os.path.splitext(m2_path)[0] + "00.skin"
    with open(m2_path, "rb") as f:
        m2 = f.read()
    with open(skin_path, "rb") as f:
        skin = f.read()
    return load(m2, skin, os.path.basename(m2_path))


# --- a synthetic body of tubes (tests and --fixture: our own geometry, no game data) -------------------------------


def tube_body(seed_name: str = "TubeBody", detail: float = 1.0) -> Model:
    """A humanoid made of tubes and an ellipsoid head, laid out in the HD character atlas the way the real models
    are (Tools/MarkForge/README.md): the arm island wraps (u 0 meets u 255 on the inner arm), the torso rows go from
    the front midline (u 256) round the left side to the back midline (u 511) and the right half shares them
    mirrored, the leg rows wrap (u 256 meets u 511 on the inner leg) below the crotch row 252, the head is a front
    decal in FU+FL with two eye cuts and a mouth cut, and geoset 1703 holds two eye-glow quads."""
    pos, nrm, uv = [], [], []
    tris = {0: [], 401: [], 1301: []}

    def add(p, n, t):
        pos.append(p)
        nrm.append(n)
        uv.append(t)
        return len(pos) - 1

    def grid(nu, nv, f, geo, mirror=False):
        """f(i/nu, j/nv) -> (pos, normal, (u, v) texels); quads into triangles; mirrored copy shares the UVs."""
        nu, nv = max(4, int(round(nu * detail))), max(2, int(round(nv * detail)))
        for side in ((1, -1) if mirror else (1,)):
            idx = np.zeros((nv + 1, nu + 1), int)
            for j in range(nv + 1):
                for i in range(nu + 1):
                    p, n, t = f(i / nu, j / nv)
                    p = np.array(p, float)
                    n = np.array(n, float)
                    p[1] *= side
                    n[1] *= side
                    idx[j, i] = add(p, n, (t[0] / 512.0, t[1] / 512.0))
            for j in range(nv):
                for i in range(nu):
                    a, b, c, d = idx[j, i], idx[j, i + 1], idx[j + 1, i + 1], idx[j + 1, i]
                    if side > 0:
                        tris[geo] += [(a, b, c), (a, c, d)]
                    else:
                        tris[geo] += [(a, c, b), (a, d, c)]

    # arms: shoulder (z 1.45) -> elbow (row 128) -> wrist (row 256) -> fingertips (row 318); the seam on the inner side
    def arm(fu, fv):
        z = 1.45 - 0.82 * fv
        r = 0.055 - 0.02 * fv
        th = math.pi + 2 * math.pi * fu  # starts on the inner side (-y), +theta toward the front
        y = 0.27 + r * math.cos(th)
        x = r * math.sin(th)
        return (x, y, z), (math.sin(th), math.cos(th), 0.0), (1 + 253.0 * fu, 1 + 316.0 * fv)

    grid(48, 64, arm, 0, mirror=True)

    # torso: neck (z 1.55) to crotch (z 0.95), half ring front midline -> left side -> back midline
    def torso(fu, fv):
        z = 1.55 - 0.6 * fv
        rx, ry = 0.12, 0.17 - 0.03 * math.sin(math.pi * fv)
        th = math.pi / 2 - math.pi * fu  # +pi/2 front (x+), through the left side (y+), to -pi/2 back
        x, y = rx * math.sin(th), ry * math.cos(th)
        # u: front midline at 256, back at 511; the left side: cos(th) > 0 -> y > 0 for every row
        return (x, abs(y), z), (math.sin(th), abs(math.cos(th)), 0.0), (256.5 + 254.0 * fu, 1 + 250.0 * fv)

    grid(40, 40, torso, 0, mirror=True)

    # legs: crotch (row 252) to ankle (row 447), then the foot rows; wrap seam on the inner side
    def leg(fu, fv):
        z = 0.95 - 0.85 * fv
        r = 0.08 - 0.035 * fv
        th = math.pi + 2 * math.pi * fu
        x, y = r * math.sin(th), 0.1 + r * math.cos(th)
        return (x, y, z), (math.sin(th), math.cos(th), 0.0), (256.5 + 254.5 * fu, 253 + 194.0 * fv)

    grid(48, 48, leg, 1301, mirror=True)

    def foot(fu, fv):
        z = 0.1 - 0.08 * fv
        r = 0.045
        th = math.pi + 2 * math.pi * fu
        x, y = 0.02 + r * math.sin(th), 0.1 + r * math.cos(th)
        return (x, y, z), (math.sin(th), math.cos(th), 0.0), (256.5 + 254.5 * fu, 449 + 61.0 * fv)

    grid(24, 6, foot, 1301, mirror=True)

    # head: the front of an ellipsoid as a decal over FU+FL; eye and mouth cuts left out
    eye_z, eye_lat = 1.70, 0.035
    hidx = {}
    nu, nv = max(8, int(round(40 * detail))), max(8, int(round(48 * detail)))
    for j in range(nv + 1):
        for i in range(nu + 1):
            lat = -0.08 + 0.16 * i / nu
            zz = 1.80 - 0.22 * j / nv
            e = (lat / 0.085) ** 2 + ((zz - 1.69) / 0.13) ** 2
            x = 0.09 * math.sqrt(max(0.05, 1 - e))
            n = np.array([x / 0.09 ** 2, lat / 0.085 ** 2, (zz - 1.69) / 0.13 ** 2])
            n /= np.linalg.norm(n)
            hidx[j, i] = add((x, lat, zz), tuple(n), ((8 + 240.0 * i / nu) / 512.0, (322 + 188.0 * j / nv) / 512.0))
    for j in range(nv):
        for i in range(nu):
            lat = -0.08 + 0.16 * (i + 0.5) / nu
            zz = 1.80 - 0.22 * (j + 0.5) / nv
            in_eye = abs(abs(lat) - eye_lat) < 0.012 and abs(zz - eye_z) < 0.004
            in_mouth = abs(lat) < 0.02 and abs(zz - (eye_z - 0.08)) < 0.0025
            if in_eye or in_mouth:
                continue
            a, b, c, d = hidx[j, i], hidx[j, i + 1], hidx[j + 1, i + 1], hidx[j + 1, i]
            tris[0] += [(a, b, c), (a, c, d)]
    # eye-glow quads (geoset 1703) just in front of the eye cuts, UV 0..1 over the sprite
    eye_t = []
    for s in (1, -1):
        q = []
        for (du, dv) in ((0, 0), (1, 0), (1, 1), (0, 1)):
            lat = s * eye_lat + (du - 0.5) * 0.02
            zz = eye_z + (0.5 - dv) * 0.02
            q.append(add((0.095, lat, zz), (1.0, 0.0, 0.0), (du, dv)))
        eye_t += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    P = np.array(pos)
    m = Model(seed_name, hashlib.sha1(P.tobytes()).hexdigest(), P, np.array(nrm), np.array(uv))
    m.skin_tris = {g: np.array(t, np.int64) for g, t in tris.items() if t}
    m.eye_tris = {1703: np.array(eye_t, np.int64)}
    m.eye_texture = "Character\\Fixture\\deathKnightEyeGlow.blp"
    m.eye_texture_slot = 0
    m.forward = 1.0
    return m
