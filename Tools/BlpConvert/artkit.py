"""Shared drawing helpers of the Bleakhold art generators (make_login_art.py, make_royale_hud_art.py).

Pillow only. Every helper is deterministic: the same inputs give the same bytes, which the generators' --check
modes rely on. make_login_art.py must keep writing byte-identical files after any change here (its art is
committed), so change behaviour only by adding new helpers.
"""

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
except ImportError:
    raise SystemExit("artkit.py needs Pillow: pip install Pillow")

SS = 4  # supersampling for anti-aliased polygons


def rgb(hexstr, alpha=255):
    hexstr = hexstr.lstrip("#")
    return (int(hexstr[0:2], 16), int(hexstr[2:4], 16), int(hexstr[4:6], 16), alpha)


def lerp(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def gradient_v(w, h, stops, y0=0, span=None):
    """Vertical gradient image; stops are (position 0..1, colour) over rows y0..y0+span."""
    span = span or h
    img = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = min(1.0, max(0.0, (y - y0 + 0.5) / span))
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                colour = lerp(c0, c1, 0.0 if p1 == p0 else (t - p0) / (p1 - p0))
                break
        else:
            colour = stops[-1][1] if t > stops[-1][0] else stops[0][1]
        draw.line([(0, y), (w, y)], fill=colour)
    return img


def mask_polygon(size, points):
    w, h = size
    big = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(big).polygon([(px * SS, py * SS) for px, py in points], fill=255)
    return big.resize((w, h), Image.LANCZOS)


def paint(canvas, fill, mask):
    """Composites `fill` (RGBA, canvas-sized) onto canvas through the coverage mask (L)."""
    layer = fill.copy()
    layer.putalpha(ImageChops.multiply(fill.getchannel("A"), mask))
    return Image.alpha_composite(canvas, layer)


def shadow(size, mask, dx, dy, sigma, colour):
    """CSS drop-shadow: the shape's silhouette moved, blurred and tinted."""
    m = Image.new("L", size, 0)
    m.paste(mask, (int(round(dx)), int(round(dy))))
    if sigma > 0:
        m = m.filter(ImageFilter.GaussianBlur(sigma))
    layer = Image.new("RGBA", size, colour[:3] + (0,))
    layer.putalpha(Image.eval(m, lambda v: v * colour[3] // 255))
    return layer


# ------------------------------------------------------------------------------------------- Royale additions
# The Bleakhold Royale generators (make_royale_hud_art.py, make_royale_art.py) shade art from height fields and
# distance fields with numpy; make_login_art.py never calls these, so it keeps needing Pillow alone.

import struct  # noqa: E402

try:
    import numpy as np
except ImportError:  # only the Royale generators need it
    np = None


def need_numpy(tool):
    if np is None:
        raise SystemExit("%s needs numpy: pip install numpy" % tool)


def tga_bytes(img, rle=True):
    """A Pillow RGBA or RGB image as TGA bytes: 32-bit BGRA (8 alpha bits) or 24-bit BGR, bottom-up rows, image
    type 10 (run-length encoded) or 2. The client decodes both (Engine/Source/Images/tga.cpp, LoadImageData and
    RLEDecompressImage) and flips the rows itself (SetTopDown). Runs never cross a row, as the TGA spec asks; the
    encoding depends only on the pixels, so the same picture always gives the same bytes."""
    if img.mode not in ("RGBA", "RGB"):
        raise ValueError("tga_bytes: RGBA or RGB only, not %s" % img.mode)
    depth = 32 if img.mode == "RGBA" else 24
    bpp = depth // 8
    w, h = img.size
    head = struct.pack("<BBBHHBHHHHBB", 0, 0, 10 if rle else 2, 0, 0, 0, 0, 0, w, h, depth, 8 if depth == 32 else 0)
    raw = img.tobytes()
    if depth == 32:
        a = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4)[::-1][:, :, [2, 1, 0, 3]]
    else:
        a = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)[::-1][:, :, [2, 1, 0]]
    a = np.ascontiguousarray(a)
    if not rle:
        return head + a.tobytes()
    out = bytearray(head)
    for row in a:
        rb = row.tobytes()
        key = np.zeros(w, dtype=np.uint32)
        for c in range(bpp):
            key |= row[:, c].astype(np.uint32) << (8 * c)
        change = np.flatnonzero(key[1:] != key[:-1]) + 1
        starts = np.concatenate(([0], change))
        ends = np.concatenate((change, [w]))
        raw_from = None  # start of a pending raw stretch
        for s, e in zip(starts.tolist(), ends.tolist()):
            if e - s >= 2:
                if raw_from is not None:
                    _tga_raw(out, rb, raw_from, s, bpp)
                    raw_from = None
                n = e - s
                while n > 0:
                    k = min(128, n)
                    if k == 1:  # a lone pixel left over from a long run
                        out.append(0)
                    else:
                        out.append(0x80 | (k - 1))
                    out += rb[s * bpp:(s + 1) * bpp]
                    n -= k
            elif raw_from is None:
                raw_from = s
        if raw_from is not None:
            _tga_raw(out, rb, raw_from, w, bpp)
    return bytes(out)


def _tga_raw(out, rb, s, e, bpp):
    while s < e:
        k = min(128, e - s)
        out.append(k - 1)
        out += rb[s * bpp:(s + k) * bpp]
        s += k


def write_tga(path, img, rle=True):
    with open(path, "wb") as f:
        f.write(tga_bytes(img, rle))


def read_tga_size(path):
    with open(path, "rb") as f:
        head = f.read(18)
    w, h, depth = struct.unpack("<HHB", head[12:17])
    return w, h, depth


def to_float(img):
    """Pillow image -> float32 array 0..1 (H, W) or (H, W, C)."""
    return np.asarray(img, dtype=np.float32) / 255.0


def to_image(a):
    """float array 0..1 (H, W), (H, W, 3) or (H, W, 4) -> Pillow L, RGB or RGBA (round half to even)."""
    return Image.fromarray(np.clip(np.rint(np.asarray(a, dtype=np.float64) * 255.0), 0, 255).astype(np.uint8))


def gauss_kernel(sigma):
    r = max(1, int(np.ceil(sigma * 3.0)))
    x = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    return (k / k.sum()).astype(np.float32), r


def gblur(a, sigma, wrap=False):
    """Separable Gaussian blur of a float array (H, W) or (H, W, C); outside the picture counts as 0, or the picture
    repeats (wrap=True, for tiling textures)."""
    if sigma <= 0:
        return a.copy()
    k, r = gauss_kernel(sigma)
    out = a.astype(np.float32)
    for axis in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[axis] = (r, r)
        p = np.pad(out, pad, mode="wrap" if wrap else "constant")
        acc = np.zeros_like(out)
        n = out.shape[axis]
        for i in range(2 * r + 1):
            sl = [slice(None)] * out.ndim
            sl[axis] = slice(i, i + n)
            acc += k[i] * p[tuple(sl)]
        out = acc
    return out


def edt(inside, reach):
    """Euclidean distance (pixels) from every True pixel to the nearest False pixel, exact up to `reach` and
    clamped there; 0 on False pixels. Two separable min-plus passes over squared distances, truncated to
    `reach` (exact below it, since the nearest pixel then lies within `reach` on both axes)."""
    big = float((reach + 1) ** 2 * 2)
    f = np.where(inside, big, 0.0).astype(np.float32)
    g = f.copy()
    for k in range(1, reach + 1):
        kk = float(k * k)
        np.minimum(g[:, k:], f[:, :-k] + kk, out=g[:, k:])
        np.minimum(g[:, :-k], f[:, k:] + kk, out=g[:, :-k])
    d = g.copy()
    for k in range(1, reach + 1):
        kk = float(k * k)
        np.minimum(d[k:, :], g[:-k, :] + kk, out=d[k:, :])
        np.minimum(d[:-k, :], g[k:, :] + kk, out=d[:-k, :])
    return np.minimum(np.sqrt(d), float(reach))


def light_dir(azimuth_deg=315.0, altitude_deg=45.0):
    """A unit light vector in image space (x right, y down, z towards the viewer); azimuth 315 = from the top left."""
    az, alt = np.radians(azimuth_deg), np.radians(altitude_deg)
    return np.array([np.sin(az) * np.cos(alt), -np.cos(az) * np.cos(alt), np.sin(alt)], dtype=np.float64)


def shade(height, light=None, spec_power=0.0):
    """Lambert shading of a height field (pixel units), normalised so flat ground is 1.0; with spec_power also a
    Blinn specular term (0..1). Returns (diffuse, specular)."""
    light = light_dir() if light is None else light
    gy, gx = np.gradient(height.astype(np.float32))
    nz = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0)
    nx, ny = -gx * nz, -gy * nz
    lam = np.maximum(0.0, nx * light[0] + ny * light[1] + nz * light[2]) / light[2]
    if spec_power <= 0:
        return lam, np.zeros_like(lam)
    hv = light + np.array([0.0, 0.0, 1.0])
    hv = hv / np.linalg.norm(hv)
    spec = np.maximum(0.0, nx * hv[0] + ny * hv[1] + nz * hv[2]) ** spec_power
    return lam, spec


def lit(colour, diffuse, specular=None, lift=0.55, gloss=0.0):
    """Colour (H, W, 3) under a normalised diffuse term: darker below 1.0, screened towards white above it (metal
    highlights go pale, not just brighter), plus `gloss` times the specular term."""
    d = diffuse[..., None]
    out = np.where(d <= 1.0, colour * d, colour + (1.0 - colour) * np.minimum(1.0, (d - 1.0)) * lift)
    if specular is not None and gloss > 0:
        out = out + (1.0 - out) * (specular[..., None] * gloss)
    return np.clip(out, 0.0, 1.0)


def ramp(t, stops):
    """Maps t (array 0..1) through colour stops [(pos, (r, g, b) 0..255), ...] -> (H, W, 3) float 0..1."""
    t = np.clip(t, 0.0, 1.0)
    pos = np.array([p for p, _ in stops], dtype=np.float32)
    cols = np.array([c[:3] for _, c in stops], dtype=np.float32) / 255.0
    out = np.empty(t.shape + (3,), dtype=np.float32)
    for c in range(3):
        out[..., c] = np.interp(t, pos, cols[:, c])
    return out


def over(dst, src):
    """Porter-Duff 'over' of straight-alpha float RGBA arrays."""
    sa = src[..., 3:4]
    da = dst[..., 3:4]
    oa = sa + da * (1.0 - sa)
    rgb_ = np.where(oa > 1e-6, (src[..., :3] * sa + dst[..., :3] * da * (1.0 - sa)) / np.maximum(oa, 1e-6), 0.0)
    return np.concatenate([rgb_, oa], axis=-1)


def layer(colour, alpha):
    """A straight-alpha RGBA array from a colour (H, W, 3) or (r, g, b) 0..255 and an alpha array."""
    if not hasattr(colour, "shape"):  # (r, g, b[, a]) 0..255
        colour = np.broadcast_to(np.array(colour[:3], dtype=np.float32) / 255.0, alpha.shape + (3,))
    elif colour.ndim == 1:  # a float triple 0..1
        colour = np.broadcast_to(colour[:3].astype(np.float32), alpha.shape + (3,))
    return np.concatenate([colour, alpha[..., None]], axis=-1).astype(np.float32)


def reduce(a, k):
    """Box-downsamples a straight-alpha float RGBA array by an integer factor, averaging colour weighted by alpha
    (no dark fringes); (H, W) arrays are plain averages."""
    if k == 1:
        return a
    h, w = a.shape[0] // k, a.shape[1] // k
    if a.ndim == 2:
        return a[:h * k, :w * k].reshape(h, k, w, k).mean(axis=(1, 3))
    a = a[:h * k, :w * k]
    alpha = a[..., 3]
    pre = a[..., :3] * alpha[..., None]
    pre = pre.reshape(h, k, w, k, 3).mean(axis=(1, 3))
    al = alpha.reshape(h, k, w, k).mean(axis=(1, 3))
    col = np.where(al[..., None] > 1e-6, pre / np.maximum(al[..., None], 1e-6), 0.0)
    return np.concatenate([col, al[..., None]], axis=-1).astype(np.float32)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)
