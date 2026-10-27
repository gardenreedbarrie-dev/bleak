"""Made-up textures and a made-up realm for the skins tests (no Blizzard data: every pixel, name and row is invented).

The BLP2 files are written here with struct directly (the DXT encoders are Tools/BlpConvert's), so the tests check
rflib/blp.py against an independent writer. skin_texture() paints a texture shaped like a fair elf skin: a warm skin
gradient with soft shading (redder shadows, yellower highlights, as painted skin is), pink lips, a green iris with a
dark pupil, a grey-white eye white and a dark-red cloth patch.

make_realm() lays out a game folder and a patch folder the way the launcher does: client/Data with a base archive
holding the textures and a locale archive holding the stock tables, and the realm's Patch-R.MPQ whose ChrRaces holds
High Elf in slot 15 (a copy of the Blood Elf's row) and whose CharSections gives race 15 copies of the Blood Elf's rows,
naming the same textures.
"""

from __future__ import annotations

import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)
TOOLS_DIR = os.path.dirname(TOOL_DIR)

for _path in (TOOL_DIR, os.path.join(TOOLS_DIR, "MpqPack"), os.path.join(TOOLS_DIR, "BlpConvert")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import blpconvert  # noqa: E402
import mpqpack  # noqa: E402

from rflib import recolor, schema_access  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402
from tests import synth  # noqa: E402

HEADER = struct.Struct("<4sIBBBBII16I16I")
HIGH_ELF = 15
BLOOD_ELF = 10
# Made-up fair skin tones, lightest first, one per synthetic skin colour index (the last one a Death Knight's).
TONES = [(246, 222, 206), (232, 192, 164), (210, 160, 128), (214, 210, 214)]
# A fair skin and the eye's green, as the recolour tests use them.
SKIN = (232, 192, 164)
GREEN = (60, 168, 72)


# --- pictures ------------------------------------------------------------------------------------------------------


def skin_texture(width: int, height: int, tone: tuple[int, int, int], features: str = "all") -> bytearray:
    """RGBA rows, top to bottom. features: "all", "body" (skin and cloth), "lower" (skin and lips), "upper" (skin and
    an eye)."""
    out = bytearray(width * height * 4)
    L, C, h = recolor.lch(recolor.srgb8_to_oklab(*tone))

    for y in range(height):
        for x in range(width):
            u, v = (x + 0.5) / width, (y + 0.5) / height
            shade = (0.12 * math.sin(u * 9.0) * math.sin(v * 7.0) + 0.08 * (0.5 - v)
                     - 0.25 * ((u - 0.5) ** 2 + (v - 0.5) ** 2))
            C2 = C * (1 - 0.8 * shade)
            h2 = math.radians(h + 60 * shade)
            rgb = recolor.oklab_to_srgb8(L * (1 + 0.55 * shade), C2 * math.cos(h2), C2 * math.sin(h2))

            if features in ("all", "lower") and ((u - 0.5) / 0.14) ** 2 + ((v - 0.78) / 0.05) ** 2 < 1:
                rgb = tuple(int(c * (0.9 + 0.1 * (1 - v))) for c in (214, 118, 126))

            if features in ("all", "upper") and ((u - 0.32) / 0.11) ** 2 + ((v - 0.35) / 0.06) ** 2 < 1:
                rgb = (226, 224, 218)
                d = math.hypot(u - 0.32, v - 0.35)

                if d < 0.05:
                    rgb = (18, 40, 22) if d < 0.02 else (28, 96, 38) if d > 0.04 else GREEN

            if features in ("all", "body") and 0.62 < u < 0.92 and 0.08 < v < 0.30:
                k = 0.85 + 0.15 * math.sin(u * 60) * math.sin(v * 60)
                rgb = (int(112 * k), int(24 * k), int(30 * k))

            o = 4 * (y * width + x)
            out[o:o + 4] = bytes(rgb) + b"\xff"

    return out


def with_alpha_edge(rgba: bytearray, width: int, height: int) -> bytearray:
    """The same picture with a transparent left column and a half-transparent second one."""
    out = bytearray(rgba)

    for y in range(height):
        out[4 * (y * width) + 3] = 0
        out[4 * (y * width + 1) + 3] = 100

    return out


def downsample(width: int, height: int, rgba: bytes) -> tuple[int, int, bytes]:
    image = blpconvert.downsample(blpconvert.Image(width, height, bytearray(rgba)))
    return image.width, image.height, bytes(image.data)


def chain(width: int, height: int, rgba: bytes, mips: bool) -> list[tuple[int, int, bytes]]:
    levels = [(width, height, bytes(rgba))]

    while mips and (levels[-1][0] > 1 or levels[-1][1] > 1):
        levels.append(downsample(*levels[-1]))

    return levels


# --- BLP2 writers --------------------------------------------------------------------------------------------------


def blp_file(encoding: int, alpha_size: int, preferred: int, width: int, height: int, blobs: list[bytes],
             palette: bytes = b"", mips: bool = True) -> bytes:
    offsets, sizes = [0] * 16, [0] * 16
    pos = HEADER.size + 1024

    for i, blob in enumerate(blobs):
        offsets[i], sizes[i] = pos, len(blob)
        pos += len(blob)

    header = HEADER.pack(b"BLP2", 1, encoding, alpha_size, preferred, 1 if mips else 0, width, height, *offsets, *sizes)
    return header + palette.ljust(1024, b"\0") + b"".join(blobs)


def blp_bgra(width: int, height: int, rgba: bytes, mips: bool = True) -> bytes:
    blobs = []

    for w, h, data in chain(width, height, rgba, mips):
        blob = bytearray(len(data))
        blob[0::4], blob[1::4], blob[2::4], blob[3::4] = data[2::4], data[1::4], data[0::4], data[3::4]
        blobs.append(bytes(blob))

    return blp_file(3, 8, 2, width, height, blobs, mips=mips)


def blp_palette(width: int, height: int, rgba: bytes, alpha_size: int = 8, mips: bool = True) -> bytes:
    """A palette texture: the colours of every level quantized to at most 256, each pixel its nearest entry."""
    levels = chain(width, height, rgba, mips)
    step = 1

    while True:
        colours = sorted({tuple(min(255, (c // step) * step + step // 2) for c in data[o:o + 3])
                          for _, _, data in levels for o in range(0, len(data), 4)})

        if len(colours) <= 256:
            break

        step *= 2

    index = {c: i for i, c in enumerate(colours)}
    palette = b"".join(bytes((b, g, r, 0)) for r, g, b in colours)
    blobs = []

    for w, h, data in levels:
        indices = bytes(index[tuple(min(255, (c // step) * step + step // 2) for c in data[o:o + 3])]
                        for o in range(0, len(data), 4))
        alphas = data[3::4]

        if alpha_size == 0:
            alpha = b""
        elif alpha_size == 1:
            alpha = bytes(sum((1 << k) for k in range(8) if i + k < len(alphas) and alphas[i + k] >= 128)
                          for i in range(0, len(alphas), 8))
        elif alpha_size == 4:
            alpha = bytes((alphas[i] >> 4) | ((alphas[i + 1] >> 4) << 4 if i + 1 < len(alphas) else 0)
                          for i in range(0, len(alphas), 2))
        else:
            alpha = bytes(alphas)

        blobs.append(indices + alpha)

    return blp_file(1, alpha_size, 2, width, height, blobs, palette, mips)


def blocks_of(width: int, height: int, rgba: bytes) -> list[tuple[list, list]]:
    """The 4x4 blocks of a level: ([(r, g, b)] * 16, [alpha] * 16), edge texels repeated."""
    out = []

    for by in range(max(1, (height + 3) // 4)):
        for bx in range(max(1, (width + 3) // 4)):
            px, alphas = [], []

            for y in range(4):
                for x in range(4):
                    sx, sy = min(width - 1, bx * 4 + x), min(height - 1, by * 4 + y)
                    o = 4 * (sy * width + sx)
                    px.append(tuple(rgba[o:o + 3]))
                    alphas.append(rgba[o + 3])

            out.append((px, alphas))

    return out


def blp_dxt(width: int, height: int, rgba: bytes, kind: str, mips: bool = True) -> bytes:
    """DXT1 (opaque), DXT3 or DXT5 with Tools/BlpConvert's block encoders."""
    blobs = []

    for w, h, data in chain(width, height, rgba, mips):
        blob = bytearray()

        for px, alphas in blocks_of(w, h, data):
            if kind == "DXT3":
                blob += sum((a >> 4) << (4 * k) for k, a in enumerate(alphas)).to_bytes(8, "little")
            elif kind == "DXT5":
                blob += blpconvert.encode_alpha_block(alphas)

            blob += blpconvert.encode_color_block(px)

        blobs.append(bytes(blob))

    preferred, alpha_size = {"DXT1": (0, 0), "DXT3": (1, 8), "DXT5": (7, 8)}[kind]
    return blp_file(2, alpha_size, preferred, width, height, blobs, mips=mips)


def blp_blocks(width: int, height: int, kind: str, blocks: list[bytes], alpha_size: int | None = None) -> bytes:
    """One level of hand-made blocks (no mips)."""
    preferred, default_alpha = {"DXT1": (0, 1), "DXT3": (1, 8), "DXT5": (7, 8)}[kind]
    alpha = default_alpha if alpha_size is None else alpha_size
    return blp_file(2, alpha, preferred, width, height, [b"".join(blocks)], mips=False)


def pack565(r: int, g: int, b: int) -> int:
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | (b * 31 + 127) // 255


def dxt1_block(c0: int, c1: int, indices: list[int]) -> bytes:
    return struct.pack("<HHI", c0, c1, sum(i << (2 * k) for k, i in enumerate(indices)))


# --- the realm -----------------------------------------------------------------------------------------------------


def write_mpq(path: str, files: dict[str, bytes]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mpqpack.write_archive(path, sorted(files.items()))


def texture_for(name: str, colour: int, section: int, slot: int) -> bytes:
    """A made-up texture for one of the Blood Elf's texture names, in a format that varies with the colour."""
    tone = TONES[colour % len(TONES)]

    if section == 0:
        size, features = (32, 32), ("body" if slot == 0 else "lower")
    elif section == 1:
        size, features = (16, 16), ("lower" if slot == 0 else "upper")
    else:
        size, features = (16, 16), "body"

    rgba = skin_texture(*size, tone, features)
    kind = ("palette", "DXT1", "BGRA", "DXT5")[(colour + slot + section) % 4]

    if kind == "palette":
        return blp_palette(*size, rgba, alpha_size=0)

    if kind == "BGRA":
        return blp_bgra(*size, rgba)

    return blp_dxt(*size, rgba, kind)


def stock_tables() -> dict[str, bytes]:
    """synth's tables, with the Blood Elf's face rows given an upper texture too (the client's face rows have two)."""
    tables = synth.build_tables()
    sections = DbcTable.from_bytes(tables["CharSections"], schema_access.get("CharSections"))

    for row in sections.rows:
        if sections.get(row, "raceID") == BLOOD_ELF and sections.get(row, "baseSection") == 1:
            sections.set_str(row, "textureName[1]", sections.get_str(row, "textureName[0]").replace("_0.blp", "_1.blp"))

    tables["CharSections"] = sections.to_bytes()
    return tables


def realm_tables(stock: dict[str, bytes]) -> dict[str, bytes]:
    """The realm's race patch: High Elf in ChrRaces slot 15 (the Blood Elf's row under HighElf), CharSections with race
    15's rows replaced by copies of the Blood Elf's (new ids, the same textures, still sorted)."""
    races = DbcTable.from_bytes(stock["ChrRaces"], schema_access.get("ChrRaces"))
    by_id = races.by_id()
    row = list(by_id[BLOOD_ELF])
    races.set(row, "id", HIGH_ELF)
    races.set_str(row, "clientFileString", "HighElf")
    races.rows[races.rows.index(by_id[HIGH_ELF])] = row

    sections = DbcTable.from_bytes(stock["CharSections"], schema_access.get("CharSections"))
    next_id = sections.max_id() + 1
    clones = []

    for source in sections.rows:
        if sections.get(source, "raceID") == BLOOD_ELF:
            clone = list(source)
            sections.set(clone, "id", next_id)
            sections.set(clone, "raceID", HIGH_ELF)
            clones.append(clone)
            next_id += 1

    at = next(i for i, r in enumerate(sections.rows) if sections.get(r, "raceID") == HIGH_ELF)
    sections.rows = [r for r in sections.rows if sections.get(r, "raceID") != HIGH_ELF]
    sections.rows[at:at] = clones
    return {"ChrRaces": races.to_bytes(), "CharSections": sections.to_bytes()}


def blood_elf_textures(stock: dict[str, bytes], sections_wanted=(0, 1, 4)) -> dict[str, bytes]:
    """A made-up texture for every texture name of the Blood Elf's rows of the given sections."""
    sections = DbcTable.from_bytes(stock["CharSections"], schema_access.get("CharSections"))
    files = {}

    for row in sections.rows:
        section = sections.get(row, "baseSection")

        if sections.get(row, "raceID") != BLOOD_ELF or section not in sections_wanted:
            continue

        for slot in range(3):
            name = sections.get_str(row, f"textureName[{slot}]")

            if name and name not in files:
                files[name] = texture_for(name, sections.get(row, "colorIndex"), section, slot)

    return files


def make_realm(root: str) -> dict:
    """root/client/Data (common.MPQ: the textures; enUS/locale-enUS.MPQ: the stock tables) and root/patches/Patch-R.MPQ
    (the realm's race patch). Returns the paths and the tables."""
    stock = stock_tables()
    realm = realm_tables(stock)
    textures = blood_elf_textures(stock)
    data = os.path.join(root, "client", "Data")
    patches = os.path.join(root, "patches")
    os.makedirs(patches, exist_ok=True)
    write_mpq(os.path.join(data, "common.MPQ"), {**textures, "Interface\\Glues\\Base.blp": b"made up"})
    write_mpq(os.path.join(data, "enUS", "locale-enUS.MPQ"),
              {f"DBFilesClient\\{n}.dbc": stock[n] for n in ("ChrRaces", "CharSections")})
    write_mpq(os.path.join(patches, "Patch-R.MPQ"), {"DBFilesClient\\ChrRaces.dbc": realm["ChrRaces"],
                                                     "DBFilesClient\\CharSections.dbc": realm["CharSections"],
                                                     "Interface\\Glues\\Custom.blp": b"the realm's own"})
    return {"client": os.path.join(root, "client"), "data": data, "patches": patches, "stock": stock, "realm": realm,
            "textures": textures}
