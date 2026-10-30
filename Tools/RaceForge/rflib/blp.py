r"""BLP2 textures as the 3.3.5a client reads them, for `raceforge.py skins`: parse, decode and recolour in place.

Layout (BLPHeader, Engine/Source/BLPFile/Types.h): 'BLP2', formatVersion 1, colorEncoding, alphaSize,
preferredFormat, hasMips, width, height, 16 mip offsets, 16 mip sizes, then 1024 bytes that hold the palette (256
B, G, R, pad entries) for colorEncoding 1. CBLPFile::Source checks the magic and the version and takes
CalcLevelCount(width, height) levels when hasMips & 0xF is set, else one (Engine/Source/Images/MippedImg.cpp); level
i is mipSizes[i] bytes at mipOffsets[i], and a level of size 0 fails the texture (CBLPFile::Lock2).

What the client makes of the data:
- colorEncoding 1: one palette index per pixel, then the alpha, alphaSize (0, 1, 4 or 8) bits per pixel
  (CBLPFile::DecompPalARGB8888). The palette's pad byte is never read.
- colorEncoding 2: DXT blocks; preferredFormat says which (TextureGetTextureFormats, Engine/Source/Services/
  Texture.cpp): 0 DXT1, 1 DXT3, 7 DXT5. A DXT1 block is in four-colour mode when its first endpoint is greater than
  the second, else in three-colour mode with index 3 transparent; DXT3 and DXT5 colour blocks are always four-colour.
- colorEncoding 3: B, G, R, A bytes per pixel.
- colorEncoding 0 is JPEG, which the client does not decode ("JPEG decompresion not enabled").

recolour() changes colours only: the file keeps its size, its header (apart from the palette) and every alpha value.
Anything this module does not know stops with BlpError, which names the texture and its format.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

HEADER = struct.Struct("<4sIBBBBII16I16I")
PALETTE_OFFSET = HEADER.size  # 0x94
HEADER_SIZE = PALETTE_OFFSET + 1024  # 0x494, where the mip data of the files Blizzard's tools write starts
DXT_KINDS = {0: "DXT1", 1: "DXT3", 7: "DXT5"}  # preferredFormat -> block type
BLOCK_BYTES = {"DXT1": 8, "DXT3": 16, "DXT5": 16}
# Index remaps for a colour block whose endpoints swap places: four-colour mode 0<->1, 2<->3 (every index XOR 1);
# DXT1 three-colour mode 0<->1 with 2 (the midpoint) and 3 (transparent) where they are.
FOUR_COLOUR_SWAP = 0x55555555


class BlpError(Exception):
    pass


@dataclass
class Level:
    index: int
    width: int
    height: int
    offset: int
    size: int  # mipSizes[i]
    expected: int  # what the client reads of it (CalcLevelSize, or pixels plus alpha for a palette)

    @property
    def used(self) -> int:
        """The bytes of the level that hold pixels: never more than its size."""
        return min(self.size, self.expected)


@dataclass
class BlpInfo:
    kind: str  # "palette", "DXT1", "DXT3", "DXT5", "BGRA"
    encoding: int
    alpha_size: int
    preferred: int
    width: int
    height: int
    levels: list[Level] = field(default_factory=list)
    missing: int = 0  # levels CalcLevelCount wants that the header leaves out (size 0)

    @property
    def has_alpha(self) -> bool:
        return self.alpha_size > 0

    def describe(self) -> str:
        alpha = f", alpha {self.alpha_size} bits" if self.alpha_size else ""
        return f"{self.width}x{self.height} {self.kind}{alpha}, {len(self.levels)} level(s)"


def level_count(width: int, height: int) -> int:
    """CalcLevelCount for a 2D texture."""
    levels = 1

    while width > 1 or height > 1:
        levels += 1
        width = max(1, width >> 1)
        height = max(1, height >> 1)

    return levels


def level_size(kind: str, width: int, height: int, alpha_size: int) -> int:
    """The bytes the client reads for one level of width x height (CalcLevelSize; palette: indices then alpha)."""
    if kind in BLOCK_BYTES:
        return max(4, width) * max(4, height) * (4 if kind == "DXT1" else 8) // 8

    if kind == "BGRA":
        return width * height * 4

    pixels = width * height
    return pixels + (pixels * alpha_size + 7) // 8


def format_name(encoding: int, alpha_size: int, preferred: int) -> str:
    return f"colorEncoding {encoding}, alphaSize {alpha_size}, preferredFormat {preferred}"


def parse(data: bytes, where: str) -> BlpInfo:
    """The texture's format and levels, checked the way the client reads them; BlpError for anything else."""
    if len(data) < HEADER.size:
        raise BlpError(f"{where}: {len(data)} bytes, too short for a BLP2 header")

    magic, version, encoding, alpha_size, preferred, has_mips, width, height, *rest = HEADER.unpack_from(data)
    offsets, sizes = rest[:16], rest[16:]

    if magic == b"BLP1":
        raise BlpError(f"{where}: a BLP1 texture (the older format with JPEG or palette data); only BLP2 is recoloured")

    if magic != b"BLP2" or version != 1:
        raise BlpError(f"{where}: not a BLP2 texture (magic {magic!r}, version {version})")

    if encoding == 0:
        raise BlpError(f"{where}: a JPEG BLP2 texture (colorEncoding 0), which the client does not decode; it is not "
                       "recoloured")

    if encoding == 1:
        if alpha_size not in (0, 1, 4, 8):
            raise BlpError(f"{where}: palette texture with alphaSize {alpha_size} "
                           f"({format_name(encoding, alpha_size, preferred)}); the client knows 0, 1, 4 and 8")

        kind = "palette"

        if len(data) < HEADER_SIZE:
            raise BlpError(f"{where}: palette texture cut off inside its palette ({len(data)} bytes)")
    elif encoding == 2:
        kind = DXT_KINDS.get(preferred, "")

        if not kind:
            raise BlpError(f"{where}: DXT texture with preferredFormat {preferred} "
                           f"({format_name(encoding, alpha_size, preferred)}); only 0 (DXT1), 1 (DXT3) and 7 "
                           "(DXT5) are recoloured")
    elif encoding == 3:
        kind = "BGRA"
    else:
        raise BlpError(f"{where}: unknown colorEncoding {encoding} ({format_name(encoding, alpha_size, preferred)})")

    if not width or not height:
        raise BlpError(f"{where}: {width}x{height} texture")

    if width == 6 * height:
        raise BlpError(f"{where}: {width}x{height} loads as a cube map; skin textures are not, and it is not "
                       "recoloured")

    info = BlpInfo(kind, encoding, alpha_size, preferred, width, height)
    count = level_count(width, height) if has_mips & 0xF else 1

    for i in range(min(count, 16)):
        if not sizes[i]:
            # CBLPFile::Lock2 fails at a missing level; the in-place path stops there too
            info.missing = count - i
            break

        w, h = max(1, width >> i), max(1, height >> i)
        level = Level(i, w, h, offsets[i], sizes[i], level_size(kind, w, h, alpha_size))

        if level.offset < PALETTE_OFFSET or level.offset + level.size > len(data):
            raise BlpError(f"{where}: level {i} (offset {level.offset}, {level.size} bytes) lies outside the file "
                           f"({len(data)} bytes)")

        info.levels.append(level)

    if not info.levels:
        raise BlpError(f"{where}: level 0 has size 0 ({info.describe()})")

    # Every byte is recoloured once: two levels on the same bytes are one, two that only overlap cannot be done.
    spans = sorted({(lv.offset, lv.used) for lv in info.levels})

    for (a_off, a_len), (b_off, b_len) in zip(spans, spans[1:]):
        if b_off < a_off + a_len:
            raise BlpError(f"{where}: levels overlap (bytes {a_off}+{a_len} and {b_off}+{b_len}); it is not recoloured")

    return info


def unique_levels(info: BlpInfo) -> list[Level]:
    """The levels with bytes of their own: a level on the same bytes as an earlier one is left out."""
    seen, out = set(), []

    for level in info.levels:
        if (level.offset, level.used) not in seen:
            seen.add((level.offset, level.used))
            out.append(level)

    return out


# --- decoding ----------------------------------------------------------------------------------------------------


def expand565(value: int) -> tuple[int, int, int]:
    r, g, b = value >> 11, (value >> 5) & 63, value & 31
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def colour_palette(c0: int, c1: int, four: bool) -> list[tuple[int, int, int, int]]:
    """The four RGBA entries of a colour block."""
    p0, p1 = expand565(c0), expand565(c1)

    if four:
        p2 = tuple((2 * a + b) // 3 for a, b in zip(p0, p1))
        p3 = tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))
        return [p0 + (255,), p1 + (255,), p2 + (255,), p3 + (255,)]

    p2 = tuple((a + b) // 2 for a, b in zip(p0, p1))
    return [p0 + (255,), p1 + (255,), p2 + (255,), (0, 0, 0, 0)]


def dxt5_alphas(block: bytes) -> list[int]:
    a0, a1 = block[0], block[1]

    if a0 > a1:
        table = [a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
    else:
        table = [a0, a1] + [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255]

    bits = int.from_bytes(block[2:8], "little")
    return [table[(bits >> (3 * k)) & 7] for k in range(16)]


def decode(data: bytes, where: str, level_index: int = 0) -> tuple[int, int, bytearray]:
    """One level as (width, height, RGBA bytes, rows top to bottom), the way the client sees it."""
    info = parse(data, where)

    if level_index >= len(info.levels):
        raise BlpError(f"{where}: has no level {level_index}")

    level = info.levels[level_index]
    w, h = level.width, level.height
    raw = data[level.offset:level.offset + level.used]
    out = bytearray(w * h * 4)

    if info.kind == "palette":
        if len(raw) < level.expected:
            raise BlpError(f"{where}: level {level_index} has {len(raw)} bytes, the client reads {level.expected}")

        palette = data[PALETTE_OFFSET:PALETTE_OFFSET + 1024]
        n = w * h
        indices = bytes(raw[:n])
        alpha = raw[n:]

        # the palette's R, G and B through each index (bytes.translate: one table lookup per pixel)
        for channel, offset in ((0, 2), (1, 1), (2, 0)):
            out[channel::4] = indices.translate(bytes(palette[offset::4]))

        if info.alpha_size == 0:
            out[3::4] = b"\xff" * n
        elif info.alpha_size == 8:
            out[3::4] = bytes(alpha[:n])
        else:
            for i in range(n):
                if info.alpha_size == 1:
                    out[4 * i + 3] = 255 if alpha[i >> 3] >> (i & 7) & 1 else 0
                else:
                    out[4 * i + 3] = ((alpha[i >> 1] >> (4 * (i & 1))) & 0xF) * 17

        return w, h, out

    if info.kind == "BGRA":
        if len(raw) < level.expected:
            raise BlpError(f"{where}: level {level_index} has {len(raw)} bytes, the client reads {level.expected}")

        out[0::4] = raw[2::4]
        out[1::4] = raw[1::4]
        out[2::4] = raw[0::4]
        out[3::4] = raw[3::4] if info.alpha_size else b"\xff" * (w * h)
        return w, h, out

    step = BLOCK_BYTES[info.kind]
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)

    if len(raw) < bw * bh * step:
        raise BlpError(f"{where}: level {level_index} has {len(raw)} bytes, {bw * bh} {info.kind} blocks need "
                       f"{bw * bh * step}")

    for by in range(bh):
        for bx in range(bw):
            block = raw[(by * bw + bx) * step:(by * bw + bx + 1) * step]

            if info.kind == "DXT1":
                c0, c1, bits = struct.unpack_from("<HHI", block)
                pal = colour_palette(c0, c1, c0 > c1)
                alphas = None
            else:
                c0, c1, bits = struct.unpack_from("<HHI", block, 8)
                pal = colour_palette(c0, c1, True)

                if info.kind == "DXT3":
                    explicit = int.from_bytes(block[:8], "little")
                    alphas = [((explicit >> (4 * k)) & 0xF) * 17 for k in range(16)]
                else:
                    alphas = dxt5_alphas(block)

            for k in range(16):
                x, y = bx * 4 + (k & 3), by * 4 + (k >> 2)

                if x < w and y < h:
                    texel = pal[(bits >> (2 * k)) & 3]
                    o = (y * w + x) * 4
                    out[o:o + 4] = bytes(texel[:3] + ((alphas[k] if alphas else texel[3]),))

    return w, h, out


# --- recolouring -------------------------------------------------------------------------------------------------


def recolour_block(c0: int, c1: int, bits: int, n0: int, n1: int, dxt1: bool) -> tuple[int, int, int]:
    """A colour block with new endpoints n0, n1 (the old ones through the colour map) in the mode it had: when the
    order of the endpoints flips, they swap places and the indices follow; a four-colour block whose endpoints become
    equal gets one of them moved by 1 in blue, so that c0 > c1 stays true (equal endpoints would make a DXT1 block
    three-colour, its index 3 transparent)."""
    four = c0 > c1 or not dxt1

    if c0 > c1 and n0 < n1 or c0 < c1 and n0 > n1:
        n0, n1 = n1, n0

        if four:
            bits ^= FOUR_COLOUR_SWAP
        else:
            # three-colour mode: 0 <-> 1 (high bit clear), 2 and 3 stay
            bits ^= ~(bits >> 1) & FOUR_COLOUR_SWAP

    if c0 > c1 and n0 == n1:
        if n0 & 0x1F < 0x1F:
            n0 += 1
        else:
            n1 -= 1

    return n0, n1, bits & 0xFFFFFFFF


def recolour(data: bytes, colours, where: str) -> bytes:
    """The texture with every colour through `colours` (rgb(r, g, b) -> (r, g, b) and c565(value) -> value), in its
    own format: the palette of a palette texture, both endpoints of every colour block of every level of a DXT texture,
    every pixel of every level of a BGRA texture. Sizes, the header and the alpha stay."""
    info = parse(data, where)
    out = bytearray(data)

    if info.kind == "palette":
        for i in range(256):
            o = PALETTE_OFFSET + 4 * i
            r, g, b = colours.rgb(out[o + 2], out[o + 1], out[o])
            out[o], out[o + 1], out[o + 2] = b, g, r

        return bytes(out)

    for level in unique_levels(info):
        start, end = level.offset, level.offset + level.used

        if info.kind == "BGRA":
            for o in range(start, end - 3, 4):
                r, g, b = colours.rgb(out[o + 2], out[o + 1], out[o])
                out[o], out[o + 1], out[o + 2] = b, g, r

            continue

        step = BLOCK_BYTES[info.kind]
        colour = 0 if info.kind == "DXT1" else 8
        dxt1 = info.kind == "DXT1"

        for o in range(start + colour, end - 7, step):
            c0, c1, bits = struct.unpack_from("<HHI", out, o)
            n0, n1, bits = recolour_block(c0, c1, bits, colours.c565(c0), colours.c565(c1), dxt1)
            struct.pack_into("<HHI", out, o, n0, n1, bits)

    return bytes(out)


def opaque(data: bytes, where: str) -> bool:
    """Whether every texel the client draws of the texture's first level is fully opaque: no alpha bits (alphaSize 0)
    or every alpha 255."""
    info = parse(data, where)

    if info.alpha_size == 0 and info.kind != "DXT1":
        return True

    _, _, rgba = decode(data, where)
    return rgba[3::4] == b"\xff" * (len(rgba) // 4)


def palette_texture(original: bytes, where: str, palette: list[tuple[int, int, int]], levels: list[bytes]) -> bytes:
    """A palette texture without alpha (alphaSize 0) with the original's header (magic, version, preferredFormat,
    hasMips, size) but its own palette (up to 256 R, G, B entries) and levels (one index per pixel each, as many as
    the original has, level i (width >> i) x (height >> i)), laid out as Blizzard's tools write them: the header,
    the palette, then the levels."""
    info = parse(original, where)
    magic, version, _, _, preferred, has_mips, width, height = HEADER.unpack_from(original)[:8]

    if not 1 <= len(palette) <= 256:
        raise BlpError(f"{where}: a palette has 1 to 256 entries, not {len(palette)}")

    if len(levels) != len(info.levels):
        raise BlpError(f"{where}: {len(levels)} levels, the original has {len(info.levels)}")

    offsets, sizes = [0] * 16, [0] * 16
    pos = HEADER_SIZE

    for i, level in enumerate(levels):
        w, h = max(1, width >> i), max(1, height >> i)

        if len(level) != w * h or (level and max(level) >= len(palette)):
            raise BlpError(f"{where}: level {i} has {len(level)} indices for {w}x{h} pixels, or names an entry past "
                           f"the {len(palette)} of the palette")

        offsets[i], sizes[i] = pos, len(level)
        pos += len(level)

    pal = bytearray(1024)

    for i, (r, g, b) in enumerate(palette):
        pal[4 * i:4 * i + 4] = bytes((b, g, r, 0))

    header = HEADER.pack(magic, version, 1, 0, preferred, has_mips, width, height, *offsets, *sizes)
    return header + bytes(pal) + b"".join(bytes(level) for level in levels)


def check(data: bytes, where: str, width: int, height: int) -> list[str]:
    """Problems of a written texture: it must parse as the client reads it, have the given size, and decode."""
    try:
        info = parse(data, where)
    except BlpError as e:
        return [str(e)]

    problems = []

    if (info.width, info.height) != (width, height):
        problems.append(f"{where}: {info.width}x{info.height}, the source is {width}x{height}")

    for level in info.levels:
        if level.size < level.expected:
            problems.append(f"{where}: level {level.index} has {level.size} bytes, the client reads {level.expected}")

    try:
        decode(data, where)
    except BlpError as e:
        problems.append(str(e))

    return problems
