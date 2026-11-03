r"""Synthetic marks for the client team: no game data, only our own geometry and patterns.

    Character\BleakholdMarks\Fixture\SectionGrid.blp (+ _Glow)  every section framed, crossed and labelled in its
                                                                own colour: shows that each of the ten rectangles is
                                                                pasted to its place at levels 7, 8 and 9
    Character\BleakholdMarks\<Race>\<Sex>\<Design>_<Colour>.blp  the race's real designs drawn on the tube body
                                                                (model.tube_body), so rows can name real paths
    Character\BleakholdEyes\<Race>\<Sex>\Eye_<Colour>.blp        eye sprites recoloured from a synthetic 32x32 glow
    Character\BleakholdMarks\Fixture\Bad\*.blp                   broken files: each one's BAD entry says what the exe
                                                                does with it (skips the layer and logs once, or
                                                                pastes it: the VPS gates catch those)

The tube body's UVs are not a real model's: on a real character the tube-body looks land in the right sections but
not on the right body parts. They are for the paste, the glow bake and the guards, not for looks.
"""

from __future__ import annotations

import hashlib
import struct

import numpy as np

from .atlas import N, SECTIONS

SKIP = "skipped: the exe skips the layer and logs once (Logs\\BleakholdMarks.log), never hangs or paints green"

# name -> (why it is bad, what Bleakhold.exe does with it). What the exe decides from a file's facts is held against
# BleakMarks.h by tests/test_marks_core.cpp (tests/fixture_bad_facts.inc, made by tests/make_fixture_facts.py)
BAD = {
    "NotPalettized": ("DXT5 512x512: the compositor cannot paste it (TextureCacheGetPal returns nothing)", SKIP),
    "WrongSize384": ("palette 384x384: not the character texture's size x 2^k at any level (256 or 512)", SKIP),
    "NotSquare": ("palette 512x256", SKIP),
    "NoMips": ("palette 512x512 with hasMips 0: one level, the others have no offset", SKIP),
    "MissingLevel": ("palette 512x512 whose 1x1 level is missing (offset and size 0)", SKIP),
    "Alpha2": ("palette 512x512 with alphaSize 2 (the client knows 0, 1, 4 and 8)", SKIP),
    "Truncated": ("a palette 512x512 file cut off after 4096 bytes", SKIP),
    "GlowAlphaMismatch": ("a valid mark whose _Glow has different alpha bytes",
                          "pasted, its _Glow too: the exe checks only the _Glow's size and alphaSize, so the VPS gate "
                          "(markforge.py validate, glow_problems) is what catches differing alpha bytes"),
    "GlowSizeMismatch": ("a valid mark whose _Glow is 256x256",
                         "the mark is pasted; its _Glow is skipped and logged once (not the mark's size), so the "
                         "mark bakes black through its alpha in the glow texture"),
}


def level_count(width: int, height: int) -> int:
    """TextureCalcMipCount: the texture cache's mip count, always the full chain of the size."""
    n = 1
    while width > 1 or height > 1:
        width, height, n = max(1, width >> 1), max(1, height >> 1), n + 1
    return n


def _pack_any(width: int, height: int, colour=(255, 0, 255)) -> bytes:
    """A palette BLP2 of any size (blpconvert.pack_pal8 takes powers of two only): every level of the chain, index 0
    everywhere, alpha 255 (8-bit)."""
    import blpconvert
    levels = level_count(width, height)
    offsets, sizes, blobs = [0] * 16, [0] * 16, []
    pos = blpconvert.BLP_HEADER_SIZE
    for i in range(levels):
        n = max(1, width >> i) * max(1, height >> i)
        blobs.append(bytes(n) + b"\xff" * n)
        offsets[i], sizes[i] = pos, 2 * n
        pos += 2 * n
    header = struct.pack("<4sIBBBBII16I16I", b"BLP2", 1, 1, 8, 8, 1, width, height, *(offsets + sizes))
    pal = bytearray(1024)
    pal[0:4] = bytes((colour[2], colour[1], colour[0], 0))
    return header + bytes(pal) + b"".join(blobs)


def sha1(b):
    return hashlib.sha1(b).hexdigest()


def _levels_from(index: np.ndarray, alpha: np.ndarray):
    """Mip chain: alpha box-filtered, indices taken from the top-left texel (fixture patterns only)."""
    t_levels, a_levels = [index.astype(np.uint8)], [alpha.astype(np.uint8)]
    a = alpha.astype(np.float64)
    idx = index
    while a.shape[0] > 1 or a.shape[1] > 1:
        h, w = a.shape
        a = a.reshape(max(1, h // 2), 2 if h > 1 else 1, max(1, w // 2), 2 if w > 1 else 1).mean(axis=(1, 3))
        idx = idx[::2 if h > 1 else 1, ::2 if w > 1 else 1]
        t_levels.append(idx.astype(np.uint8))
        a_levels.append(np.round(a).astype(np.uint8))
    return t_levels, a_levels


def _pack(t_levels, a_levels, palette, mips=True):
    import blpconvert
    h, w = a_levels[0].shape
    return blpconvert.pack_pal8(w, h, palette, [t.tobytes() for t in t_levels], [a.tobytes() for a in a_levels], mips)


def section_grid():
    from .preview import text
    hues = [(255, 80, 80), (255, 170, 60), (240, 230, 70), (120, 230, 90), (60, 200, 230), (90, 120, 255),
            (180, 100, 255), (255, 90, 200), (220, 220, 220), (140, 255, 220)]
    index = np.zeros((N, N), np.uint8)
    alpha = np.zeros((N, N), np.uint8)
    for k, (name, (x, y, w, h)) in enumerate(SECTIONS.items()):
        base = 1 + 2 * k
        index[y:y + h, x:x + w] = base
        alpha[y:y + h, x:x + w] = 40
        lines = np.zeros((h, w), bool)
        lines[:3, :] = lines[-3:, :] = True
        lines[:, :3] = lines[:, -3:] = True
        yy, xx = np.mgrid[0:h, 0:w]
        lines |= np.abs(yy / h - xx / w) < 2.0 / min(w, h)
        canvas = np.zeros((h, w, 3), np.uint8)
        text(canvas, 10, 10, name, (255, 255, 255), max(2, h // 20))
        lines |= canvas[..., 0] > 0
        index[y:y + h, x:x + w][lines] = base + 1
        alpha[y:y + h, x:x + w][lines] = 255
    pal = [(0, 0, 0)]
    gpal = [(0, 0, 0)]
    for c in hues:
        pal += [tuple(int(v * 0.6) for v in c), c]
        gpal += [tuple(int(v * 0.25) for v in c), c]
    t_levels, a_levels = _levels_from(index, alpha)
    return _pack(t_levels, a_levels, pal), _pack(t_levels, a_levels, gpal)


def bad_files(good_mark: bytes, good_glow: bytes):
    import blpconvert
    out = {}
    img = blpconvert.Image(N, N, bytearray(np.tile(np.array([200, 80, 255, 128], np.uint8), N * N).tobytes()))
    from .eyes import encode
    out["NotPalettized"] = encode(img, "dxt5", True)
    out["WrongSize384"] = _pack_any(384, 384)
    small = np.zeros((256, 256), np.uint8)
    small_glow = _pack(*_levels_from(small, np.full((256, 256), 255, np.uint8)), [(255, 0, 255)])
    ns = np.zeros((256, 512), np.uint8)
    out["NotSquare"] = _pack(*_levels_from(ns, np.full((256, 512), 255, np.uint8)), [(255, 0, 255)])
    t, a = _levels_from(np.zeros((N, N), np.uint8), np.full((N, N), 255, np.uint8))
    out["NoMips"] = _pack(t[:1], a[:1], [(255, 0, 255)], mips=False)
    full = bytes(_pack(t, a, [(255, 0, 255)]))
    missing = bytearray(full)
    struct.pack_into("<I", missing, 0x14 + 4 * 9, 0)  # offsets[9] = 0 and sizes[9] = 0: the 1x1 level is missing
    struct.pack_into("<I", missing, 0x54 + 4 * 9, 0)
    out["MissingLevel"] = bytes(missing)
    a2 = bytearray(full)
    a2[9] = 2  # alphaSize 2, which no BLP has (the client pastes 0, 1, 4 and 8)
    out["Alpha2"] = bytes(a2)
    out["Truncated"] = full[:4096]
    out["GlowAlphaMismatch"] = good_mark
    g = bytearray(good_glow)
    off = struct.unpack_from("<I", g, 0x14)[0]
    g[off + N * N:off + N * N + 4096] = bytes(255 - b for b in g[off + N * N:off + N * N + 4096])
    out["GlowAlphaMismatch_Glow"] = bytes(g)
    out["GlowSizeMismatch"] = good_mark
    out["GlowSizeMismatch_Glow"] = small_glow
    return out


def header_facts(data: bytes) -> dict:
    """What the texture cache knows of a BLP2 (BleakMarks::TextureFacts, the mip offsets and the file size)."""
    _, _, encoding, alpha, _, _, width, height = struct.unpack_from("<4sIBBBBII", data)
    return {"width": width, "height": height, "mip_count": level_count(width, height), "alpha_bits": alpha,
            "palettized": encoding == 1, "offsets": list(struct.unpack_from("<16I", data, 0x14)), "size": len(data)}


def bad_facts(files: dict) -> list[dict]:
    """The facts of every Bad file and what the exe does with it: "layer" (pasted or skipped, at both character
    texture sizes) for a mark, "glow" (used or skipped) for a _Glow next to its mark."""
    out = []
    for name, (_, expect) in BAD.items():
        data = files[f"Character\\BleakholdMarks\\Fixture\\Bad\\{name}.blp"]
        out.append({"name": name, "kind": "layer", "paste": not expect.startswith("skipped"), **header_facts(data)})
        glow = files.get(f"Character\\BleakholdMarks\\Fixture\\Bad\\{name}_Glow.blp")
        if glow is not None:
            mark = header_facts(data)
            facts = header_facts(glow)
            used = facts["palettized"] and all(facts[k] == mark[k] for k in ("width", "height", "alpha_bits"))
            out.append({"name": name + "_Glow", "kind": "glow", "paste": used, "mark": name, **facts})
    return out


def facts_cpp(files: dict) -> str:
    """tests/fixture_bad_facts.inc: the Bad files' facts as C++ initialisers (no art, numbers only)."""
    lines = ["// Made by Tools/MarkForge/tests/make_fixture_facts.py from the fixture's Bad files: do not edit.",
             "// { name, glow, width, height, mipCount, alphaBits, palettized, size, offsets[16], pastes,",
             "//   mark width, mark height, mark alphaBits (a _Glow's mark) }"]
    marks = {f["name"]: f for f in bad_facts(files) if f["kind"] == "layer"}
    for f in bad_facts(files):
        m = marks.get(f.get("mark", ""), f)
        lines.append(f'{{ "{f["name"]}", {str(f["kind"] == "glow").lower()}, {f["width"]}, {f["height"]}, '
                     f'{f["mip_count"]}, {f["alpha_bits"]}, {str(f["palettized"]).lower()}, {f["size"]},')
        lines.append("  { " + ", ".join(str(o) for o in f["offsets"][:8]) + ",")
        lines.append("    " + ", ".join(str(o) for o in f["offsets"][8:]) + " },")
        lines.append(f'  {str(f["paste"]).lower()}, {m["width"]}, {m["height"]}, {m["alpha_bits"]} }},')
    return "\n".join(lines) + "\n"


def build(races_spec: str):
    """(files {path: bytes}, manifest) of the fixture."""
    import markforge as MF
    from . import archive as AR, designs as D, draw as W, eyes as E, model as M
    pal, races = MF.load_data()
    files = {}
    grid, grid_glow = section_grid()
    files["Character\\BleakholdMarks\\Fixture\\SectionGrid.blp"] = grid
    files["Character\\BleakholdMarks\\Fixture\\SectionGrid_Glow.blp"] = grid_glow
    for name, data in bad_files(grid, grid_glow).items():
        files[f"Character\\BleakholdMarks\\Fixture\\Bad\\{name}.blp"] = data
    eye_src = E.synthetic_source()
    files["Character\\BleakholdEyes\\Fixture\\deathKnightEyeGlow.blp"] = eye_src
    body = M.tube_body()
    garment = synthetic_garment()
    race_sexes = []
    gates = {"seam_max": 0.0, "keepout_ink": 0, "garment_ink": 0, "blocked_ink": 0, "failures": []}
    for race, rf, sex in MF.parse_races(races_spec):
        sex_name = AR.SEXES[sex]
        p = MF.prepare(None, race, sex, None, False, model_obj=body, garment=garment)
        rep = {"designs": []}
        marks = MF.make_looks(p, rf, sex_name, races[rf], rep, files, gates)
        eyes, src = MF.make_eyes(None, p, rf, sex_name, pal, races[rf], files, fixture_src=eye_src)
        race_sexes.append({"race": race, "race_file": rf, "sex": sex, "sex_name": sex_name, "model": body.name,
                           "model_sha1": body.sha1, "skin_sha1": body.sha1, "eye_geoset": True, "eye_source": src,
                           "marks": marks, "eyes": eyes})
    gates["failures"] += MF.manifest_problems(race_sexes, files.get)
    manifest = {
        "format": MF.FORMAT, "fixture": True, "markforge_version": __import__("mflib").VERSION,
        "catalogue_version": MF.load_json(MF.CATALOGUE).get("version") if MF.os.path.isfile(MF.CATALOGUE) else None,
        "note": "Synthetic: drawn on MarkForge's tube body, not a real model. For the exe's paste, glow and guards.",
        "section_grid": {"texture": "Character\\BleakholdMarks\\Fixture\\SectionGrid.blp",
                         "glow_texture": "Character\\BleakholdMarks\\Fixture\\SectionGrid_Glow.blp",
                         "sha1": sha1(grid), "glow_sha1": sha1(grid_glow)},
        "bad_files": [{"texture": f"Character\\BleakholdMarks\\Fixture\\Bad\\{k}.blp", "why": why,
                       "expect": expect} for k, (why, expect) in BAD.items()],
        "looks_per_design": 3, "designs_per_race": 4,
        "gates": {"passed": not gates["failures"], "seam_max": round(gates["seam_max"], 4), "seam_limit": MF.SEAM_LIMIT,
                  "keepout_ink": gates["keepout_ink"], "garment_ink": gates["garment_ink"]},
        "race_sexes": race_sexes,
    }
    return files, manifest


def synthetic_garment():
    """A band over the chest (TU) and the hips (LU), the shape the package's underwear has."""
    g = np.zeros((N, N), bool)
    g[60:110, 256:420] = True
    g[200:250, 256:512] = True
    return g
