#!/usr/bin/env python3
"""blpconvert: write BLP2 textures the 3.3.5a (12340) client loads.

Usage:
  blpconvert.py IN OUT.blp [--format dxt1|dxt5|bgra|pal8] [--size WxH | --pad] [--no-mips] [--jobs N]
  blpconvert.py --info FILE.blp [FILE.blp ...]
  blpconvert.py --decode FILE.blp OUT.png [--mip N]

Input: PNG and TGA are read with the standard library. JPEG and anything else need Pillow
(pip install Pillow); without it, convert the picture to PNG first with any tool. --size resamples
(Pillow's Lanczos when installed, otherwise a box/bilinear resampler); --pad puts the picture in the
top-left corner of the next power-of-two canvas instead. Sizes must end up as powers of two: the
client refuses other 2D textures (Engine/Source/Gx/Gx.cpp, GxTexCreate).

Output layout (Engine/Source/BLPFile/Types.h, BLPHeader): 'BLP2', formatVersion 1, colorEncoding,
alphaSize, preferredFormat, hasMips, width, height, 16 mip offsets, 16 mip sizes, a 1024-byte palette
(zero for these encodings), then the mip data from offset 0x494.
  dxt1  colorEncoding 2, alphaSize 0, preferredFormat 0 (PIXEL_DXT1): opaque pictures.
  dxt5  colorEncoding 2, alphaSize 8, preferredFormat 7 (PIXEL_DXT5): pictures with alpha.
  bgra  colorEncoding 3, alphaSize 8, preferredFormat 2 (PIXEL_ARGB8888): uncompressed. The Bleakhold
        client re-encodes this encoding to DXT5 with a fast range-fit encoder when it opens the file
        (ThirdParty/WarcraftXL/host/textures/blp/BlpHost.cpp), so dxt1/dxt5 from here look better.
  pal8  colorEncoding 1, alphaSize 8, preferredFormat 8 (PIXEL_UNSPECIFIED, as in Blizzard's palette
        files): one byte of palette index per texel, then one byte of alpha per texel, with one 256-entry
        palette (B, G, R, 0) in the header for every level. This is the only encoding the character
        texture compositor pastes (TextureCacheGetPal, WoW/Common/TextureCache.cpp; any other encoding
        fills the section with flat green), so character layers (faces, underwear, Bleakhold marks)
        must use it. A picture with 256 colours or fewer keeps them exactly; otherwise a median cut
        picks 256 (deterministic, no dithering) and every level, mips included, maps each texel to
        the nearest entry. pack_pal8() takes ready palette indices and alpha for callers that build
        their own palette (Tools/MarkForge).
With mips (the default) every level down to 1x1 is written: the client walks CalcLevelCount(w, h)
levels (Engine/Source/Images/MippedImg.cpp) and fails the whole texture if one is missing. Never
make a texture six times as wide as it is tall: the client takes that for a cube map.

The DXT encoder fits each 4x4 block along its principal colour axis and refines the endpoints by
least squares; mips are box-filtered with alpha weighting, and colour is pulled into fully
transparent texels so that filtering and DXT never bleed black into edges. Standard library only;
the encode runs in worker processes (--jobs, default: all cores).
"""

import argparse
import os
import struct
import sys
import zlib

BLP_HEADER_SIZE = 0x94 + 1024
PIXEL_DXT1, PIXEL_DXT3, PIXEL_ARGB8888, PIXEL_DXT5, PIXEL_UNSPECIFIED = 0, 1, 2, 7, 8
FORMATS = {
    # name: (colorEncoding, alphaSize, preferredFormat, bytes per 4x4 block or None for BGRA / palette)
    "dxt1": (2, 0, PIXEL_DXT1, 8),
    "dxt5": (2, 8, PIXEL_DXT5, 16),
    "bgra": (3, 8, PIXEL_ARGB8888, None),
    "pal8": (1, 8, PIXEL_UNSPECIFIED, None),
}


class Image:
    """8-bit RGBA picture: data is a bytearray of width*height*4 (R, G, B, A), rows top to bottom."""

    def __init__(self, width, height, data=None):
        self.width = width
        self.height = height
        self.data = data if data is not None else bytearray(width * height * 4)

    def has_alpha(self):
        return any(a != 255 for a in self.data[3::4])


# ---------------------------------------------------------------------------------------------- input

def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_png(path):
    with open(path, "rb") as f:
        blob = f.read()
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("%s: not a PNG file" % path)
    pos = 8
    idat = bytearray()
    palette = trns = None
    width = height = depth = ctype = interlace = None
    while pos < len(blob):
        length, kind = struct.unpack(">I4s", blob[pos:pos + 8])
        chunk = blob[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"PLTE":
            palette = chunk
        elif kind == b"tRNS":
            trns = chunk
        elif kind == b"IDAT":
            idat += chunk
        elif kind == b"IEND":
            break
    if interlace:
        raise ValueError("%s: interlaced PNG is not supported; save it without interlacing" % path)
    if depth not in (8, 16) and not (ctype == 3 and depth in (1, 2, 4)) and not (ctype == 0 and depth in (1, 2, 4)):
        raise ValueError("%s: unsupported PNG bit depth %d" % (path, depth))
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bits_pp = channels * depth
    bpp = max(1, bits_pp // 8)
    stride = (width * bits_pp + 7) // 8
    raw = zlib.decompress(bytes(idat))
    rows = []
    prev = bytearray(stride)
    p = 0
    for _ in range(height):
        ftype = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ftype == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ftype == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                upleft = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, prev[i], upleft)) & 255
        rows.append(line)
        prev = line
    img = Image(width, height)
    out = img.data
    o = 0
    for line in rows:
        if depth == 16:
            line = line[0::2]  # keep the high byte of each sample
        if depth < 8:
            samples = []
            per = 8 // depth
            mask = (1 << depth) - 1
            for byte in line:
                for k in range(per):
                    samples.append((byte >> (8 - depth * (k + 1))) & mask)
            line = samples[:width]
            if ctype == 0:
                scale = 255 // mask
                line = [v * scale for v in line]
        for x in range(width):
            if ctype == 6:
                out[o:o + 4] = line[x * 4:x * 4 + 4]
            elif ctype == 2:
                out[o:o + 3] = line[x * 3:x * 3 + 3]
                out[o + 3] = 255
            elif ctype == 0:
                v = line[x]
                out[o:o + 4] = bytes((v, v, v, 255))
            elif ctype == 4:
                v = line[x * 2]
                out[o:o + 4] = bytes((v, v, v, line[x * 2 + 1]))
            else:
                idx = line[x]
                out[o:o + 3] = palette[idx * 3:idx * 3 + 3]
                out[o + 3] = trns[idx] if trns is not None and idx < len(trns) else 255
            o += 4
    return img


def read_tga(path):
    with open(path, "rb") as f:
        blob = f.read()
    idlen, cmtype, itype = blob[0], blob[1], blob[2]
    width, height, bits, desc = struct.unpack("<HHBB", blob[12:18])
    if cmtype != 0 or itype not in (2, 10) or bits not in (24, 32):
        raise ValueError("%s: only 24/32-bit true-colour TGA is supported" % path)
    bpp = bits // 8
    pos = 18 + idlen
    count = width * height
    pixels = bytearray()
    if itype == 2:
        pixels = bytearray(blob[pos:pos + count * bpp])
    else:
        while len(pixels) < count * bpp:
            head = blob[pos]
            pos += 1
            n = (head & 0x7F) + 1
            if head & 0x80:
                pixels += blob[pos:pos + bpp] * n
                pos += bpp
            else:
                pixels += blob[pos:pos + n * bpp]
                pos += n * bpp
    img = Image(width, height)
    top_down = bool(desc & 0x20)
    for y in range(height):
        sy = y if top_down else height - 1 - y
        for x in range(width):
            s = (sy * width + x) * bpp
            d = (y * width + x) * 4
            img.data[d] = pixels[s + 2]
            img.data[d + 1] = pixels[s + 1]
            img.data[d + 2] = pixels[s]
            img.data[d + 3] = pixels[s + 3] if bpp == 4 else 255
    return img


def _pillow():
    try:
        from PIL import Image as PILImage
        return PILImage
    except ImportError:
        return None


def read_image(path, size=None):
    """Reads any supported picture; with size=(w, h) it is resampled (Pillow when present)."""
    pil = _pillow()
    ext = os.path.splitext(path)[1].lower()
    if pil is not None:
        with pil.open(path) as im:
            im = im.convert("RGBA")
            if size and im.size != size:
                im = im.resize(size, pil.LANCZOS)
            return Image(im.size[0], im.size[1], bytearray(im.tobytes()))
    if ext == ".png":
        img = read_png(path)
    elif ext == ".tga":
        img = read_tga(path)
    else:
        raise SystemExit("%s: reading %s needs Pillow (pip install Pillow), or convert it to PNG first" % (path, ext))
    if size and (img.width, img.height) != size:
        img = resample(img, size[0], size[1])
    return img


def _resample_axis(n_in, n_out, count, get, put):
    """1D resample of `count` lines: box average when shrinking, linear when growing."""
    scale = n_in / n_out
    for line in range(count):
        for o in range(n_out):
            if scale > 1.0:
                start, end = o * scale, (o + 1) * scale
                acc = [0.0, 0.0, 0.0, 0.0]
                total = 0.0
                i = int(start)
                while i < end and i < n_in:
                    w = min(end, i + 1) - max(start, i)
                    px = get(line, i)
                    for c in range(4):
                        acc[c] += px[c] * w
                    total += w
                    i += 1
                put(line, o, [a / total for a in acc])
            else:
                x = (o + 0.5) * scale - 0.5
                i0 = max(0, min(n_in - 1, int(x // 1)))
                i1 = min(n_in - 1, i0 + 1)
                t = max(0.0, min(1.0, x - i0))
                a, b = get(line, i0), get(line, i1)
                put(line, o, [a[c] + (b[c] - a[c]) * t for c in range(4)])


def resample(img, width, height):
    """Plain-Python resampler (the Pillow-free fallback); alpha is not premultiplied."""
    w0, h0 = img.width, img.height
    data = img.data
    tmp = [[None] * width for _ in range(h0)]

    def get_h(y, x):
        o = (y * w0 + x) * 4
        return data[o:o + 4]

    def put_h(y, x, px):
        tmp[y][x] = px

    _resample_axis(w0, width, h0, get_h, put_h)
    out = Image(width, height)

    def get_v(x, y):
        return tmp[y][x]

    def put_v(x, y, px):
        o = (y * width + x) * 4
        out.data[o:o + 4] = bytes(max(0, min(255, int(v + 0.5))) for v in px)

    _resample_axis(h0, height, width, get_v, put_v)
    return out


def is_pow2(n):
    return n > 0 and (n & (n - 1)) == 0


def next_pow2(n):
    p = 1
    while p < n:
        p <<= 1
    return p


def pad_to_pow2(img):
    w, h = next_pow2(img.width), next_pow2(img.height)
    if (w, h) == (img.width, img.height):
        return img
    out = Image(w, h)
    for y in range(img.height):
        out.data[y * w * 4:(y * w + img.width) * 4] = img.data[y * img.width * 4:(y + 1) * img.width * 4]
    return out


# ----------------------------------------------------------------------------------------------- mips

def level_count(width, height):
    """CalcLevelCount (Engine/Source/Images/MippedImg.cpp) for non-cube textures."""
    levels = 1
    while width > 1 or height > 1:
        levels += 1
        width = max(1, width >> 1)
        height = max(1, height >> 1)
    return levels


def downsample(img):
    """Halves a level with a 2x2 (or 2x1) box filter; colour is weighted by alpha."""
    w, h = img.width, img.height
    nw, nh = max(1, w >> 1), max(1, h >> 1)
    out = Image(nw, nh)
    src, dst = img.data, out.data
    sx = 2 if w > 1 else 1
    sy = 2 if h > 1 else 1
    for y in range(nh):
        for x in range(nw):
            r = g = b = a = 0
            rr = gg = bb = 0
            n = 0
            for dy in range(sy):
                row = (y * sy + dy) * w
                for dx in range(sx):
                    o = (row + x * sx + dx) * 4
                    pa = src[o + 3]
                    r += src[o] * pa
                    g += src[o + 1] * pa
                    b += src[o + 2] * pa
                    rr += src[o]
                    gg += src[o + 1]
                    bb += src[o + 2]
                    a += pa
                    n += 1
            o = (y * nw + x) * 4
            if a:
                dst[o] = (r + a // 2) // a
                dst[o + 1] = (g + a // 2) // a
                dst[o + 2] = (b + a // 2) // a
            else:
                dst[o] = rr // n
                dst[o + 1] = gg // n
                dst[o + 2] = bb // n
            dst[o + 3] = (a + n // 2) // n
    return out


def build_mips(img, mips=True):
    levels = [img]
    if mips:
        while levels[-1].width > 1 or levels[-1].height > 1:
            levels.append(downsample(levels[-1]))
    return levels


def fill_transparent(levels):
    """Pull-push: every texel with alpha 0 takes the colour of the coarser level above it, so the
    colour around shapes continues outward instead of turning black. Alpha is untouched."""
    for i in range(len(levels) - 2, -1, -1):
        fine, coarse = levels[i], levels[i + 1]
        fw, fh, cw = fine.width, fine.height, coarse.width
        sx = 2 if fw > coarse.width else 1
        sy = 2 if fh > coarse.height else 1
        fd, cd = fine.data, coarse.data
        for y in range(fh):
            crow = (y // sy) * cw
            for x in range(fw):
                o = (y * fw + x) * 4
                if fd[o + 3] == 0:
                    c = (crow + x // sx) * 4
                    fd[o] = cd[c]
                    fd[o + 1] = cd[c + 1]
                    fd[o + 2] = cd[c + 2]


# ------------------------------------------------------------------------------------------------ DXT

def _expand5(v):
    return (v << 3) | (v >> 2)


def _expand6(v):
    return (v << 2) | (v >> 4)


def _build_single_tables():
    """Best (c0, c1) endpoint pair so that the 2/3 interpolant reproduces each 8-bit value."""
    tables = []
    for bits, expand in ((5, _expand5), (6, _expand6)):
        top = (1 << bits) - 1
        table = []
        for v in range(256):
            centre = v * top // 255
            best = None
            for hi in range(max(0, centre - 3), min(top, centre + 3) + 1):
                e_hi = expand(hi)
                for lo in range(max(0, centre - 3), min(top, centre + 3) + 1):
                    err = abs((2 * e_hi + expand(lo)) // 3 - v) * 4 + abs(hi - lo)
                    if best is None or err < best[0]:
                        best = (err, hi, lo)
            table.append((best[1], best[2]))
        tables.append(table)
    return tables


_SINGLE5 = _SINGLE6 = None


def _single_tables():
    global _SINGLE5, _SINGLE6
    if _SINGLE5 is None:
        _SINGLE5, _SINGLE6 = _build_single_tables()
    return _SINGLE5, _SINGLE6


def _pack565(r, g, b):
    return (r << 11) | (g << 5) | b


def _quant565(c):
    r = max(0, min(31, int(c[0] * 31 / 255 + 0.5)))
    g = max(0, min(63, int(c[1] * 63 / 255 + 0.5)))
    b = max(0, min(31, int(c[2] * 31 / 255 + 0.5)))
    return r, g, b


def _palette(q0, q1):
    c0 = (_expand5(q0[0]), _expand6(q0[1]), _expand5(q0[2]))
    c1 = (_expand5(q1[0]), _expand6(q1[1]), _expand5(q1[2]))
    c2 = tuple((2 * a + b) // 3 for a, b in zip(c0, c1))
    c3 = tuple((a + 2 * b) // 3 for a, b in zip(c0, c1))
    return (c0, c1, c2, c3)


def _assign(px, pal):
    total = 0
    idx = []
    p0, p1, p2, p3 = pal
    for (r, g, b) in px:
        best = 0
        d = (r - p0[0]) ** 2 + (g - p0[1]) ** 2 + (b - p0[2]) ** 2
        e = (r - p1[0]) ** 2 + (g - p1[1]) ** 2 + (b - p1[2]) ** 2
        if e < d:
            d, best = e, 1
        e = (r - p2[0]) ** 2 + (g - p2[1]) ** 2 + (b - p2[2]) ** 2
        if e < d:
            d, best = e, 2
        e = (r - p3[0]) ** 2 + (g - p3[1]) ** 2 + (b - p3[2]) ** 2
        if e < d:
            d, best = e, 3
        idx.append(best)
        total += d
    return idx, total


_WEIGHT0 = (1.0, 0.0, 2.0 / 3.0, 1.0 / 3.0)  # share of c0 in palette entries 0..3


def _least_squares(px, idx):
    aa = ab = bb = 0.0
    ax = [0.0, 0.0, 0.0]
    bx = [0.0, 0.0, 0.0]
    for p, i in zip(px, idx):
        a = _WEIGHT0[i]
        b = 1.0 - a
        aa += a * a
        ab += a * b
        bb += b * b
        for c in range(3):
            ax[c] += a * p[c]
            bx[c] += b * p[c]
    det = aa * bb - ab * ab
    if abs(det) < 1e-6:
        return None
    e0 = [(ax[c] * bb - bx[c] * ab) / det for c in range(3)]
    e1 = [(bx[c] * aa - ax[c] * ab) / det for c in range(3)]
    return e0, e1


def _finish_color(q0, q1, idx):
    """Packs a colour block in four-colour mode (c0 > c1), swapping the endpoints when needed."""
    v0, v1 = _pack565(*q0), _pack565(*q1)
    if v0 < v1:
        v0, v1 = v1, v0
        idx = [(1, 0, 3, 2)[i] for i in idx]
    elif v0 == v1:
        idx = [0] * 16
    bits = 0
    for k, i in enumerate(idx):
        bits |= i << (2 * k)
    return struct.pack("<HHI", v0, v1, bits)


def encode_color_block(px):
    """px: 16 (r, g, b) tuples, row by row. Returns the 8-byte DXT1 colour block."""
    first = px[0]
    if all(p == first for p in px):
        t5, t6 = _single_tables()
        r, g, b = first
        q0 = (t5[r][0], t6[g][0], t5[b][0])
        q1 = (t5[r][1], t6[g][1], t5[b][1])
        if q0 == q1:
            return _finish_color(q0, q1, [0] * 16)
        return _finish_color(q0, q1, [2] * 16)

    n = 16.0
    mr = sum(p[0] for p in px) / n
    mg = sum(p[1] for p in px) / n
    mb = sum(p[2] for p in px) / n
    crr = cgg = cbb = crg = crb = cgb = 0.0
    for r, g, b in px:
        dr, dg, db = r - mr, g - mg, b - mb
        crr += dr * dr
        cgg += dg * dg
        cbb += db * db
        crg += dr * dg
        crb += dr * db
        cgb += dg * db
    # Power iteration for the principal axis, seeded with the bounding-box diagonal.
    vr = max(p[0] for p in px) - min(p[0] for p in px)
    vg = max(p[1] for p in px) - min(p[1] for p in px)
    vb = max(p[2] for p in px) - min(p[2] for p in px)
    if crg < 0:
        vg = -vg
    if crb < 0:
        vb = -vb
    for _ in range(4):
        nr = crr * vr + crg * vg + crb * vb
        ng = crg * vr + cgg * vg + cgb * vb
        nb = crb * vr + cgb * vg + cbb * vb
        m = max(abs(nr), abs(ng), abs(nb))
        if m < 1e-9:
            break
        vr, vg, vb = nr / m, ng / m, nb / m
    lo = hi = None
    for p in px:
        d = p[0] * vr + p[1] * vg + p[2] * vb
        if lo is None or d < lo[0]:
            lo = (d, p)
        if hi is None or d > hi[0]:
            hi = (d, p)
    e0, e1 = hi[1], lo[1]
    best = None
    for _ in range(3):
        q0, q1 = _quant565(e0), _quant565(e1)
        idx, err = _assign(px, _palette(q0, q1))
        if best is None or err < best[0]:
            best = (err, q0, q1, idx)
        if err == 0:
            break
        fit = _least_squares(px, idx)
        if fit is None:
            break
        e0, e1 = fit
    _, q0, q1, idx = best
    return _finish_color(q0, q1, idx)


def _alpha_palette(a0, a1):
    if a0 > a1:
        return [a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
    return [a0, a1] + [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255]


def _alpha_fit(alphas, a0, a1):
    pal = _alpha_palette(a0, a1)
    idx = []
    err = 0
    for a in alphas:
        best_i = 0
        best_d = abs(a - pal[0])
        for i in range(1, 8):
            d = abs(a - pal[i])
            if d < best_d:
                best_i, best_d = i, d
        idx.append(best_i)
        err += best_d * best_d
    return err, idx


def encode_alpha_block(alphas):
    """alphas: 16 values. Returns the 8-byte DXT5 alpha block (eight- or six-value mode)."""
    lo, hi = min(alphas), max(alphas)
    if lo == hi:
        return struct.pack("<BB6s", hi, hi, b"\0" * 6)
    best = _alpha_fit(alphas, hi, lo) + (hi, lo)
    inner = [a for a in alphas if 0 < a < 255]
    if inner and (lo == 0 or hi == 255):
        # Six-value mode (a0 <= a1) spends its two last codes on exact 0 and 255.
        cand = _alpha_fit(alphas, min(inner), max(inner)) + (min(inner), max(inner))
        if cand[0] < best[0]:
            best = cand
    err, idx, a0, a1 = best
    bits = 0
    for k, i in enumerate(idx):
        bits |= i << (3 * k)
    return struct.pack("<BB", a0, a1) + bits.to_bytes(6, "little")


def _encode_rows(args):
    """Worker: encodes a band of whole block rows. data holds only that band's texel rows."""
    data, width, height, fmt = args
    out = bytearray()
    for by in range(max(1, (height + 3) // 4)):
        for bx in range(max(1, (width + 3) // 4)):
            px = []
            alphas = []
            for y in range(4):
                sy = min(height - 1, by * 4 + y)
                for x in range(4):
                    sx = min(width - 1, bx * 4 + x)
                    o = (sy * width + sx) * 4
                    px.append((data[o], data[o + 1], data[o + 2]))
                    alphas.append(data[o + 3])
            if fmt == "dxt5":
                out += encode_alpha_block(alphas)
            out += encode_color_block(px)
    return bytes(out)


def encode_level(img, fmt, pool=None):
    if fmt == "bgra":
        out = bytearray(len(img.data))
        out[0::4] = img.data[2::4]
        out[1::4] = img.data[1::4]
        out[2::4] = img.data[0::4]
        out[3::4] = img.data[3::4]
        return bytes(out)
    rows = max(1, (img.height + 3) // 4)
    if pool is None or rows < 8 or img.height % 4:
        return _encode_rows((bytes(img.data), img.width, img.height, fmt))
    step = max(1, rows // 64)
    line = img.width * 4
    tasks = []
    for r in range(0, rows, step):
        y0, y1 = r * 4, min(img.height, (r + step) * 4)
        tasks.append((bytes(img.data[y0 * line:y1 * line]), img.width, y1 - y0, fmt))
    return b"".join(pool.map(_encode_rows, tasks))


def level_size(level, width, height, fmt):
    """CalcLevelSize (Engine/Source/Images/MippedImg.cpp) for the formats written here; for a palette
    texture the index bytes plus the alpha bits the client reads (CBLPFile::DecompPalARGB8888)."""
    w = max(1, width >> level)
    h = max(1, height >> level)
    if fmt == "bgra":
        return w * h * 4
    if fmt == "pal8":
        return w * h * 2
    if fmt in ("pal0", "pal1", "pal4"):
        bits = int(fmt[3:])
        return w * h + (w * h * bits + 7) // 8
    w, h = max(4, w), max(4, h)
    return w * h * (4 if fmt == "dxt1" else 8) // 8


# --------------------------------------------------------------------------------------- palette (pal8)

def _box_split(box):
    """(range, channel) of the widest channel of a box of ((r, g, b), weight); range 0 when it cannot split."""
    if len(box) < 2:
        return (0, 0)
    best = (0, 0)
    for ch in range(3):
        lo = min(c[ch] for c, _ in box)
        hi = max(c[ch] for c, _ in box)
        if hi - lo > best[0]:
            best = (hi - lo, ch)
    return best


def _median_cut(colours, count):
    """colours: {(r, g, b): weight}. Splits the colour box with the widest channel range at its weighted
    median until there are `count` boxes (or no box can be split); every step is deterministic (ties go to
    the lower channel, then the earlier box). Returns the weighted mean colour of each box."""
    boxes = [sorted(colours.items())]
    splits = [_box_split(boxes[0])]
    while len(boxes) < count:
        i = max(range(len(boxes)), key=lambda k: (splits[k][0], -k))
        width, ch = splits[i]
        if width == 0:
            break
        box = sorted(boxes[i], key=lambda cw: (cw[0][ch], cw[0]))
        total = sum(w for _, w in box)
        acc = 0
        cut = 1
        for k, (_, w) in enumerate(box):
            acc += w
            if acc * 2 >= total:
                cut = k + 1
                break
        cut = max(1, min(len(box) - 1, cut))
        boxes[i:i + 1] = [box[:cut], box[cut:]]
        splits[i:i + 1] = [_box_split(box[:cut]), _box_split(box[cut:])]
    out = []
    for box in boxes:
        total = sum(w for _, w in box) or 1
        out.append(tuple(int((sum(c[ch] * w for c, w in box) + total // 2) // total) for ch in range(3)))
    return out


def _nearest_index(palette, colour):
    r, g, b = colour
    best_i, best_d = 0, None
    for i, (pr, pg, pb) in enumerate(palette):
        d = (r - pr) * (r - pr) + (g - pg) * (g - pg) + (b - pb) * (b - pb)
        if best_d is None or d < best_d:
            best_i, best_d = i, d
            if d == 0:
                break
    return best_i


def _nearest_indices(palette, colours):
    """_nearest_index for many colours; with numpy when it is installed (same answers: integer distances,
    the first of equal entries), else in plain Python."""
    try:
        import numpy as np
    except ImportError:
        return [_nearest_index(palette, c) for c in colours]
    pal = np.array(palette, np.int64)
    out = []
    for k in range(0, len(colours), 4096):
        c = np.array(colours[k:k + 4096], np.int64)
        d = ((c[:, None, :] - pal[None, :, :]) ** 2).sum(-1)
        out.extend(int(i) for i in d.argmin(1))
    return out


def quantize_pal8(levels):
    """One palette for a mip chain of Images: the exact colours when every level together has 256 or fewer
    (sorted), else a median cut of level 0's colours, weighted by alpha + 1 so that the colour bled into
    transparent texels still counts a little. Returns (palette [(r, g, b)] * <=256, [index bytes per level])."""
    seen = {}
    for level in levels:
        d = level.data
        for o in range(0, len(d), 4):
            key = (d[o], d[o + 1], d[o + 2])
            seen[key] = seen.get(key, 0) + d[o + 3] + 1
            if len(seen) > 256:
                break
        if len(seen) > 256:
            break
    if len(seen) <= 256:
        palette = sorted(seen)
    else:
        weights = {}
        d = levels[0].data
        for o in range(0, len(d), 4):
            key = (d[o], d[o + 1], d[o + 2])
            weights[key] = weights.get(key, 0) + d[o + 3] + 1
        palette = _median_cut(weights, 256)
    lookup = {c: i for i, c in enumerate(palette)}
    missing = set()
    for level in levels:
        d = level.data
        for o in range(0, len(d), 4):
            key = (d[o], d[o + 1], d[o + 2])
            if key not in lookup:
                missing.add(key)
    missing = sorted(missing)
    lookup.update(zip(missing, _nearest_indices(palette, missing)))
    indices = []
    for level in levels:
        d = level.data
        out = bytearray(level.width * level.height)
        for p, o in enumerate(range(0, len(d), 4)):
            out[p] = lookup[(d[o], d[o + 1], d[o + 2])]
        indices.append(bytes(out))
    return palette, indices


def pack_pal8(width, height, palette, indices, alphas, mips=True):
    """The bytes of a pal8 BLP2 (colorEncoding 1, alphaSize 8, preferredFormat 8): palette is up to 256
    (r, g, b) entries, indices and alphas one bytes object per level (level i is (width >> i) x (height >> i),
    at least 1x1), every level the client walks present when mips is set. Raises ValueError on any
    inconsistency, so a caller with its own palette (Tools/MarkForge) cannot write a file the client rejects."""
    if not (is_pow2(width) and is_pow2(height)):
        raise ValueError("%dx%d is not a power of two in both dimensions" % (width, height))
    if width == 6 * height:
        raise ValueError("a texture six times as wide as tall loads as a cube map")
    if not 1 <= len(palette) <= 256:
        raise ValueError("a palette has 1 to 256 entries, not %d" % len(palette))
    want = level_count(width, height) if mips else 1
    if len(indices) != want or len(alphas) != want:
        raise ValueError("%d index and %d alpha levels, the client reads %d" % (len(indices), len(alphas), want))
    if want > 16:
        raise ValueError("more than 16 mip levels")
    blobs = []
    for i in range(want):
        n = max(1, width >> i) * max(1, height >> i)
        if len(indices[i]) != n or len(alphas[i]) != n:
            raise ValueError("level %d: %d indices and %d alpha bytes for %d texels" % (i, len(indices[i]), len(alphas[i]), n))
        if max(indices[i]) >= len(palette):
            raise ValueError("level %d names palette entry %d of %d" % (i, max(indices[i]), len(palette)))
        blobs.append(bytes(indices[i]) + bytes(alphas[i]))
    offsets = [0] * 16
    sizes = [0] * 16
    pos = BLP_HEADER_SIZE
    for i, blob in enumerate(blobs):
        offsets[i] = pos
        sizes[i] = len(blob)
        pos += len(blob)
    enc, alpha_size, preferred, _ = FORMATS["pal8"]
    header = struct.pack("<4sIBBBBII16I16I", b"BLP2", 1, enc, alpha_size, preferred, 1 if mips else 0,
                         width, height, *(offsets + sizes))
    pal = bytearray(1024)
    for i, (r, g, b) in enumerate(palette):
        pal[4 * i:4 * i + 4] = bytes((b, g, r, 0))
    blob = header + bytes(pal) + b"".join(blobs)
    assert len(header) + 1024 == BLP_HEADER_SIZE
    return blob


def write_pal8_blp(path, levels, mips=True):
    palette, indices = quantize_pal8(levels)
    alphas = [bytes(level.data[3::4]) for level in levels]
    try:
        blob = pack_pal8(levels[0].width, levels[0].height, palette, indices, alphas, mips)
    except ValueError as e:
        raise SystemExit("%s: %s" % (path, e))
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, path)


# --------------------------------------------------------------------------------------------- output

def write_blp(path, levels, fmt, mips=True, pool=None):
    enc, alpha_size, preferred, _ = FORMATS[fmt]
    width, height = levels[0].width, levels[0].height
    if not (is_pow2(width) and is_pow2(height)):
        raise SystemExit("%s: %dx%d is not a power of two in both dimensions" % (path, width, height))
    if width == 6 * height:
        raise SystemExit("%s: a texture six times as wide as tall loads as a cube map" % path)
    if len(levels) > 16:
        raise SystemExit("%s: more than 16 mip levels" % path)
    if mips and len(levels) != level_count(width, height):
        raise SystemExit("internal error: incomplete mip chain")
    blobs = []
    for i, level in enumerate(levels):
        blob = encode_level(level, fmt, pool)
        if len(blob) != level_size(i, width, height, fmt):
            raise SystemExit("internal error: level %d is %d bytes, expected %d" % (i, len(blob), level_size(i, width, height, fmt)))
        blobs.append(blob)
    offsets = [0] * 16
    sizes = [0] * 16
    pos = BLP_HEADER_SIZE
    for i, blob in enumerate(blobs):
        offsets[i] = pos
        sizes[i] = len(blob)
        pos += len(blob)
    header = struct.pack("<4sIBBBBII16I16I", b"BLP2", 1, enc, alpha_size, preferred, 1 if mips else 0,
                         width, height, *(offsets + sizes))
    header += b"\0" * 1024
    assert len(header) == BLP_HEADER_SIZE
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(header)
        for blob in blobs:
            f.write(blob)
    os.replace(tmp, path)


def convert(img, out_path, fmt=None, mips=True, jobs=None):
    """Encodes an Image (power-of-two) to out_path. fmt None picks dxt5 with alpha, else dxt1."""
    if fmt is None:
        fmt = "dxt5" if img.has_alpha() else "dxt1"
    # Colour is pulled into fully transparent texels through a full chain even without mips.
    chain = build_mips(img, True)
    if fmt != "dxt1":
        fill_transparent(chain)
    levels = chain if mips else chain[:1]
    if fmt == "pal8":
        if not (is_pow2(img.width) and is_pow2(img.height)):
            raise SystemExit("%s: %dx%d is not a power of two in both dimensions" % (out_path, img.width, img.height))
        write_pal8_blp(out_path, levels, mips)
        return fmt
    pool = None
    if jobs != 1:
        import concurrent.futures
        pool = concurrent.futures.ProcessPoolExecutor(max_workers=jobs or os.cpu_count() or 1)
    try:
        write_blp(out_path, levels, fmt, mips, pool)
    finally:
        if pool is not None:
            pool.shutdown()
    return fmt


# ------------------------------------------------------------------------------------- info / decode

def read_blp_header(blob):
    if len(blob) < BLP_HEADER_SIZE:
        raise ValueError("file is shorter than the 0x494-byte BLP2 header")
    fields = struct.unpack("<4sIBBBBII16I16I", blob[:0x94])
    return {
        "magic": fields[0], "version": fields[1], "encoding": fields[2], "alphaSize": fields[3],
        "preferredFormat": fields[4], "hasMips": fields[5], "width": fields[6], "height": fields[7],
        "offsets": list(fields[8:24]), "sizes": list(fields[24:40]),
    }


def check_blp(path):
    """Checks a BLP2 file the way the client reads it; returns (header, list of problems)."""
    with open(path, "rb") as f:
        blob = f.read()
    problems = []
    h = read_blp_header(blob)
    if h["magic"] != b"BLP2" or h["version"] != 1:
        problems.append("CBLPFile::ValidateHeader fails (magic %r, version %d)" % (h["magic"], h["version"]))
    w, hgt = h["width"], h["height"]
    if not (is_pow2(w) and is_pow2(hgt)):
        problems.append("%dx%d is not a power of two" % (w, hgt))
    fmt = None
    if h["encoding"] == 2:
        fmt = {PIXEL_DXT1: "dxt1", PIXEL_DXT5: "dxt5"}.get(h["preferredFormat"])
        if fmt is None:
            problems.append("encoding 2 with preferredFormat %d is not checked by this tool" % h["preferredFormat"])
        elif fmt == "dxt5" and h["alphaSize"] != 8:
            problems.append("DXT5 should have alphaSize 8")
    elif h["encoding"] == 3:
        fmt = "bgra"
        if h["preferredFormat"] != PIXEL_ARGB8888:
            problems.append("encoding 3 should have preferredFormat 2 (PIXEL_ARGB8888)")
    elif h["encoding"] == 1:
        if h["alphaSize"] in (0, 1, 4, 8):
            fmt = "pal%d" % h["alphaSize"]
        else:
            problems.append("palette texture with alphaSize %d (the client knows 0, 1, 4 and 8)" % h["alphaSize"])
    else:
        problems.append("encoding %d is not checked by this tool" % h["encoding"])
    levels = level_count(w, hgt) if h["hasMips"] & 0xF else 1
    for i in range(levels):
        off, size = h["offsets"][i], h["sizes"][i]
        if not size:
            problems.append("level %d of %d is missing (the client then fails the whole texture)" % (i, levels))
            continue
        if off < BLP_HEADER_SIZE or off + size > len(blob):
            problems.append("level %d (offset %d, size %d) lies outside the file" % (i, off, size))
        if fmt and size < level_size(i, w, hgt, fmt):
            problems.append("level %d has %d bytes, CalcLevelSize wants %d" % (i, size, level_size(i, w, hgt, fmt)))
    return h, levels, problems


def _decode_color(block, out, opaque_only):
    c0, c1, bits = struct.unpack("<HHI", block)

    def rgb(v):
        return (_expand5(v >> 11), _expand6((v >> 5) & 63), _expand5(v & 31))

    p0, p1 = rgb(c0), rgb(c1)
    if c0 > c1 or opaque_only:
        pal = [p0 + (255,), p1 + (255,), tuple((2 * a + b) // 3 for a, b in zip(p0, p1)) + (255,),
               tuple((a + 2 * b) // 3 for a, b in zip(p0, p1)) + (255,)]
    else:
        pal = [p0 + (255,), p1 + (255,), tuple((a + b) // 2 for a, b in zip(p0, p1)) + (255,), (0, 0, 0, 0)]
    for k in range(16):
        out.append(pal[(bits >> (2 * k)) & 3])


def decode_blp(path, mip=0):
    with open(path, "rb") as f:
        blob = f.read()
    h = read_blp_header(blob)
    w, hgt = max(1, h["width"] >> mip), max(1, h["height"] >> mip)
    data = blob[h["offsets"][mip]:h["offsets"][mip] + h["sizes"][mip]]
    img = Image(w, hgt)
    if h["encoding"] == 1:
        palette = blob[0x94:0x94 + 1024]
        n = w * hgt
        alpha_size = h["alphaSize"]
        alpha = data[n:]
        for i in range(n):
            p = data[i] * 4
            o = i * 4
            img.data[o] = palette[p + 2]
            img.data[o + 1] = palette[p + 1]
            img.data[o + 2] = palette[p]
            if alpha_size == 8:
                a = alpha[i]
            elif alpha_size == 4:
                a = ((alpha[i >> 1] >> (4 * (i & 1))) & 0xF) * 17
            elif alpha_size == 1:
                a = 255 if (alpha[i >> 3] >> (i & 7)) & 1 else 0
            else:
                a = 255
            img.data[o + 3] = a
        return img
    if h["encoding"] == 3:
        img.data[0::4] = data[2::4][:w * hgt]
        img.data[1::4] = data[1::4][:w * hgt]
        img.data[2::4] = data[0::4][:w * hgt]
        img.data[3::4] = data[3::4][:w * hgt]
        return img
    dxt5 = h["preferredFormat"] == PIXEL_DXT5
    step = 16 if dxt5 else 8
    bw = max(1, (w + 3) // 4)
    pos = 0
    for by in range(max(1, (hgt + 3) // 4)):
        for bx in range(bw):
            block = data[pos:pos + step]
            pos += step
            texels = []
            if dxt5:
                a0, a1 = block[0], block[1]
                pal = _alpha_palette(a0, a1)
                abits = int.from_bytes(block[2:8], "little")
                alphas = [pal[(abits >> (3 * k)) & 7] for k in range(16)]
                _decode_color(block[8:16], texels, True)
                texels = [t[:3] + (alphas[k],) for k, t in enumerate(texels)]
            else:
                _decode_color(block, texels, False)
            for k, t in enumerate(texels):
                x, y = bx * 4 + (k & 3), by * 4 + (k >> 2)
                if x < w and y < hgt:
                    o = (y * w + x) * 4
                    img.data[o:o + 4] = bytes(t)
    return img


def write_png(path, img):
    raw = bytearray()
    stride = img.width * 4
    for y in range(img.height):
        raw.append(0)
        raw += img.data[y * stride:(y + 1) * stride]

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", img.width, img.height, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))


# ----------------------------------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="Write BLP2 textures for the 3.3.5a client.")
    ap.add_argument("input", nargs="?")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--format", choices=sorted(FORMATS),
                    help="default: dxt5 with alpha, dxt1 without; pal8 for character layers (palette, 8-bit alpha)")
    ap.add_argument("--size", help="resample to WxH (powers of two)")
    ap.add_argument("--pad", action="store_true", help="pad to the next power of two instead of resampling")
    ap.add_argument("--no-mips", action="store_true", help="write only the top level")
    ap.add_argument("--jobs", type=int, default=None, help="worker processes (default: all cores)")
    ap.add_argument("--info", nargs="+", metavar="BLP", help="print and check BLP headers")
    ap.add_argument("--decode", nargs=2, metavar=("BLP", "PNG"), help="decode one level to PNG")
    ap.add_argument("--mip", type=int, default=0, help="level for --decode")
    args = ap.parse_args(argv)

    if args.info:
        rc = 0
        for path in args.info:
            h, levels, problems = check_blp(path)
            print("%s: BLP2 v%d encoding %d alphaSize %d preferredFormat %d hasMips %d %dx%d, %d level(s)" % (
                path, h["version"], h["encoding"], h["alphaSize"], h["preferredFormat"], h["hasMips"],
                h["width"], h["height"], levels))
            for p in problems:
                print("  PROBLEM: " + p)
                rc = 1
        return rc
    if args.decode:
        write_png(args.decode[1], decode_blp(args.decode[0], args.mip))
        return 0
    if not args.input or not args.output:
        ap.error("need IN and OUT (or --info / --decode)")
    size = None
    if args.size:
        w, h = (int(v) for v in args.size.lower().split("x"))
        size = (w, h)
    img = read_image(args.input, size)
    if args.pad:
        img = pad_to_pow2(img)
    fmt = convert(img, args.output, args.format, not args.no_mips, args.jobs)
    print("%s: %dx%d %s%s" % (args.output, img.width, img.height, fmt, "" if args.no_mips else " with mips"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
