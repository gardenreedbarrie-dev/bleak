#!/usr/bin/env python3
"""Check the models a map places for the data that crashes the x64 client in CM2Scene::Animate.

    python3 -I Tools/WowClient/m2_check.py --data <client Data folder> [--patches <realm patches folder>] \
        --adt <map.adt> [--adt ...] [--near X,Y,RADIUS] [--all]

CM2Scene::Animate (Engine/Source/Model2/M2Scene.cpp) walks every drawn model's skin batches and indexes its tables
with the batch's numbers, unchecked: the skin sections (m_skinSectionIndex), the materials (m_materialIndex, and
m_materialIndex - m_materialLayer), the transparency combos (m_textureWeightComboIndex, then the weight it names),
and the bone matrices (the section's m_centerBoneIndex). A model whose .skin does not belong to its .m2 (a model
converted from a later expansion, or an HD pack's .m2 next to the old .skin) has numbers past those tables. The
32-bit client read a little past them and lived; the x64 build reads far outside and dies (ACCESS_VIOLATION, like
the earlier "more than four skin profiles" crash in CM2Shared::GetSkinProfileIndex).

Each model is read the way the players' client reads it: the realm patches first (every optional pack on, the
launcher's load order: MapForge's dbc/patches.py), then the client's own archives. Its first skin profile
(<model>00.skin) is checked against the .m2. Output: one line per model with a problem (and, with --all, the clean
ones), the problem, and the nearest placement to --near. Nothing is written.

Layouts: Engine/Source/Model2/M2Data.h (M2Data, M2SkinProfile, M2Batch 24 bytes, M2SkinSection 48 bytes).
"""
from __future__ import annotations

import argparse
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "MapForge"))
sys.path.insert(0, os.path.join(TOOLS, "MpqPack"))

from dbc import SIBLINGS  # noqa: E402,F401  (sys.path for the sibling tools)
from dbc.patches import PatchArchive, PatchSet  # noqa: E402

BASE_ORDER = ("patch-3.MPQ", "patch-2.MPQ", "patch.MPQ", "lichking.MPQ", "expansion.MPQ", "common-2.MPQ",
              "common.MPQ")
ORIGIN = 17066.666


class Client:
    """Files as the players' client resolves them: the realm patches (all packs on), then the base archives."""

    def __init__(self, data: str, patches: str | None):
        self.order: list = []
        if patches:
            ps = PatchSet.scan(patches, None)
            for a in reversed(ps.archives):     # highest priority first
                if a.reader is not None:
                    self.order.append((f"patches/{a.name}", a.reader))
        for name in BASE_ORDER:
            for root in (data, os.path.join(data, "Data")):
                p = os.path.join(root, name)
                if os.path.isfile(p):
                    try:
                        self.order.append((name, PatchArchive(p)))
                    except Exception:
                        pass
                    break

    def read(self, path: str) -> tuple[bytes | None, str]:
        for name, a in self.order:
            try:
                if a.has_file(path):
                    return a.read(path), name
            except Exception:
                continue
        return None, ""


def arr(d: bytes, off: int) -> tuple[int, int]:
    return struct.unpack_from("<2I", d, off)


def check_model(client: Client, path: str) -> tuple[list[str], str]:
    m2, src = client.read(path)
    if m2 is None:
        return ["model file not in the client (it is just not drawn)"], ""
    problems = []
    if m2[:4] == b"MD21":
        return [f"chunked MD21 model (a later expansion's format) from {src}"], src
    if m2[:4] != b"MD20":
        return [f"not an M2 (magic {m2[:4]!r}) from {src}"], src
    version = struct.unpack_from("<I", m2, 4)[0]
    if version != 264:
        problems.append(f"version {version}, not 264 (a converted model)")
    if len(m2) < 0x130:
        return problems + ["header too short"], src
    n_bones = arr(m2, 0x2C)[0]
    n_profiles = struct.unpack_from("<I", m2, 0x44)[0]
    n_colors = arr(m2, 0x48)[0]
    n_weights = arr(m2, 0x58)[0]
    n_materials = arr(m2, 0x70)[0]
    tex_combos = arr(m2, 0x80)[0]
    wc_count, wc_off = arr(m2, 0x90)
    if wc_off + 2 * wc_count > len(m2):
        problems.append("transparency combo table runs past the file")
        weight_combos = []
    else:
        weight_combos = list(struct.unpack_from(f"<{wc_count}H", m2, wc_off))
    if n_profiles == 0:
        return problems + ["no skin profile"], src
    skin_path = path[:-3] + "00.skin"
    skin, skin_src = client.read(skin_path)
    if skin is None:
        return problems + [f"{skin_path.split(chr(92))[-1]} missing"], src
    if skin[:4] != b"SKIN":
        return problems + ["skin without SKIN magic"], src
    # A skin and model resolving from different archives is normal for stock models (an HD pack's patch.MPQ carries
    # the .m2, the .skin still answers from a base archive) and is not itself a crash. It is only noted below, and
    # then only when a real out-of-range batch or section is also found -- that mismatch alone is no longer a problem.
    n_sec, sec_off = arr(skin, 0x1C)
    n_bat, bat_off = arr(skin, 0x24)
    if sec_off + 48 * n_sec > len(skin) or bat_off + 24 * n_bat > len(skin):
        return problems + ["skin tables run past the file"], src
    centers = [struct.unpack_from("<H", skin, sec_off + 48 * s + 0x12)[0] for s in range(n_sec)]
    for s, cb in enumerate(centers):
        if cb >= max(n_bones, 1):
            problems.append(f"section {s} centre bone {cb} >= {n_bones} bones")
            break
    for b in range(n_bat):
        (flags, prio, shader, sec, geoset, color, mat, layer, texcount, texcombo, coordcombo, wcombo,
         tcombo) = struct.unpack_from("<BbHHHHHHHHHHH", skin, bat_off + 24 * b)
        if shader == 0x8000:
            continue
        bad = []
        if sec >= n_sec:
            bad.append(f"skin section {sec} >= {n_sec}")
        if mat >= n_materials:
            bad.append(f"material {mat} >= {n_materials}")
        if layer > mat:
            bad.append(f"material layer {layer} > material {mat} (index goes negative)")
        if texcount:
            if wcombo >= len(weight_combos):
                bad.append(f"transparency combo {wcombo} >= {len(weight_combos)}")
            elif weight_combos[wcombo] >= n_weights:
                bad.append(f"transparency weight {weight_combos[wcombo]} >= {n_weights}")
            if texcombo + texcount > tex_combos:
                bad.append(f"texture combo {texcombo}+{texcount} > {tex_combos}")
        if bad:
            problems.append(f"batch {b}: " + ", ".join(bad))
            if len(problems) >= 4:
                break
    _ = n_colors
    if problems and skin_src != src:
        problems.append(f"(skin from {skin_src}, model from {src})")
    return problems, src


def adt_models(path: str):
    """{model path: [(world x, y, z, scale)]} of the doodads an ADT draws (MDDF entries some MCRF references)."""
    d = open(path, "rb").read()
    i, C, M = 0, {}, []
    while i + 8 <= len(d):
        t = d[i:i + 4][::-1].decode("ascii", "replace")
        n = struct.unpack_from("<I", d, i + 4)[0]
        (M.append(i) if t == "MCNK" else C.setdefault(t, (i + 8, n)))
        i += 8 + n
    b, n = C["MMDX"]
    names, o = {}, 0
    for raw in d[b:b + n].split(b"\0"):
        names[o] = raw.decode("latin-1")
        o += len(raw) + 1
    mb, mn = C["MMID"]
    mmid = struct.unpack_from(f"<{mn // 4}I", d, mb)
    refs = set()
    for s in M:
        q = s + 8
        nd, nw = struct.unpack_from("<I", d, q + 0x10)[0], struct.unpack_from("<I", d, q + 0x38)[0]
        j = s + struct.unpack_from("<I", d, q + 0x20)[0]
        refs |= set(struct.unpack_from(f"<{nd + nw}I", d, j + 8)[:nd])
    db, dn = C["MDDF"]
    out: dict[str, list] = {}
    for k in range(dn // 36):
        if k not in refs:
            continue
        nid = struct.unpack_from("<I", d, db + k * 36)[0]
        x, y, z = struct.unpack_from("<3f", d, db + k * 36 + 8)
        sc = struct.unpack_from("<H", d, db + k * 36 + 32)[0] / 1024
        name = names[mmid[nid]]
        name = name[:-4] + ".m2" if name.lower().endswith(".mdx") else name
        out.setdefault(name, []).append((ORIGIN - z, ORIGIN - x, y, sc))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", required=True, help="the client's Data folder (base archives)")
    ap.add_argument("--patches", help="the realm's patch folder (the launcher's patches/)")
    ap.add_argument("--adt", action="append", required=True, help="an ADT whose drawn doodads to check")
    ap.add_argument("--near", help="X,Y,RADIUS: also mark the placements this close to a point (a crash position)")
    ap.add_argument("--all", action="store_true", help="list the clean models too")
    args = ap.parse_args()
    client = Client(args.data, args.patches)
    print(f"{len(client.order)} archives, highest priority first: "
          f"{', '.join(n for n, _ in client.order[:6])}{' ...' if len(client.order) > 6 else ''}")
    models: dict[str, list] = {}
    for a in args.adt:
        for k, v in adt_models(a).items():
            models.setdefault(k, []).extend(v)
    near = None
    if args.near:
        nx, ny, nr = (float(v) for v in args.near.split(","))
        near = (nx, ny, nr)
    bad = 0
    for path in sorted(models):
        problems, src = check_model(client, path)
        places = models[path]
        dist = min(math.dist(p[:2], near[:2]) for p in places) if near else None
        tag = f" | nearest {dist:.0f} yd" if near else ""
        close = " <== NEAR" if near and dist <= near[2] else ""
        if problems:
            bad += 1
            print(f"BAD  {path}  [{src}] x{len(places)}{tag}{close}\n       " + "\n       ".join(problems))
        elif args.all:
            print(f"ok   {path}  [{src}] x{len(places)}{tag}")
    print(f"\n{len(models)} models checked, {bad} with a problem")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
