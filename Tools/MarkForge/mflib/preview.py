r"""Previews: the texture sheet and front/back renders by day and by night. They show game art (the model and the
skin samples), so they are written only to a scratch or staging folder, never to the repository.

The render is a plain software rasteriser of the naked body (the type-1 geosets), lit by one sun (day: ambient 0.42
+ 0.7 Lambert) or by moonlight (night: 0.10 + 0.22), with the mark's colour layer composited into the skin the way
the client does (skin, underwear, face, mark) and the _Glow layer added unlit at night, then a blur of the emitted
light for bloom. The eye geoset 1703 is drawn with its sprite additively when an eye sprite is given.
"""

from __future__ import annotations

import struct
import zlib

import numpy as np

from .atlas import N, SECTIONS

# 5x7 bitmap font: each glyph seven rows of five bits
_FONT = {
    "A": "01110 10001 10001 11111 10001 10001 10001", "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01111 10000 10000 10000 10000 10000 01111", "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111", "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01111 10000 10000 10011 10001 10001 01111", "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "01110 00100 00100 00100 00100 00100 01110", "J": "00111 00010 00010 00010 00010 10010 01100",
    "K": "10001 10010 10100 11000 10100 10010 10001", "L": "10000 10000 10000 10000 10000 10000 11111",
    "M": "10001 11011 10101 10101 10001 10001 10001", "N": "10001 11001 10101 10011 10001 10001 10001",
    "O": "01110 10001 10001 10001 10001 10001 01110", "P": "11110 10001 10001 11110 10000 10000 10000",
    "Q": "01110 10001 10001 10001 10101 10010 01101", "R": "11110 10001 10001 11110 10100 10010 10001",
    "S": "01111 10000 10000 01110 00001 00001 11110", "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110", "V": "10001 10001 10001 10001 10001 01010 00100",
    "W": "10001 10001 10001 10101 10101 10101 01010", "X": "10001 10001 01010 00100 01010 10001 10001",
    "Y": "10001 10001 01010 00100 00100 00100 00100", "Z": "11111 00001 00010 00100 01000 10000 11111",
    "0": "01110 10001 10011 10101 11001 10001 01110", "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111", "3": "11110 00001 00001 01110 00001 00001 11110",
    "4": "00010 00110 01010 10010 11111 00010 00010", "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110", "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110", "9": "01110 10001 10001 01111 00001 00010 01100",
    "-": "00000 00000 00000 11111 00000 00000 00000", ".": "00000 00000 00000 00000 00000 01100 01100",
    ",": "00000 00000 00000 00000 01100 00100 01000", ":": "00000 01100 01100 00000 01100 01100 00000",
    "#": "01010 11111 01010 01010 01010 11111 01010", "/": "00001 00010 00010 00100 01000 01000 10000",
    "(": "00010 00100 01000 01000 01000 00100 00010", ")": "01000 00100 00010 00010 00010 00100 01000",
    "'": "00100 00100 01000 00000 00000 00000 00000", "+": "00000 00100 00100 11111 00100 00100 00000",
    " ": "00000 00000 00000 00000 00000 00000 00000", "|": "00100 00100 00100 00100 00100 00100 00100",
}


def text(img: np.ndarray, x: int, y: int, s: str, colour=(230, 230, 230), scale: int = 2):
    """Draws text into an (H, W, 3) uint8 or float picture in place."""
    col = np.array(colour, img.dtype if img.dtype != np.uint8 else np.uint8)
    cx = x
    for ch in s.upper():
        rows = _FONT.get(ch, _FONT[" "]).split()
        for r, bits in enumerate(rows):
            for c, b in enumerate(bits):
                if b == "1":
                    y0, x0 = y + r * scale, cx + c * scale
                    if 0 <= y0 < img.shape[0] - scale and 0 <= x0 < img.shape[1] - scale:
                        img[y0:y0 + scale, x0:x0 + scale] = col
        cx += 6 * scale


def write_png(path: str, rgb: np.ndarray):
    """(H, W, 3) or (H, W, 4) uint8 to a PNG (standard library + numpy)."""
    rgb = np.ascontiguousarray(rgb.astype(np.uint8))
    h, w, c = rgb.shape
    raw = np.zeros((h, w * c + 1), np.uint8)
    raw[:, 1:] = rgb.reshape(h, w * c)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6 if c == 4 else 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw.tobytes(), 6)))
        f.write(chunk(b"IEND", b""))


def blur(img: np.ndarray, sigma: float) -> np.ndarray:
    r = int(3 * sigma) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    out = img.copy()
    for axis in (0, 1):
        pad = [(0, 0)] * img.ndim
        pad[axis] = (r, r)
        p = np.pad(out, pad, mode="edge")
        acc = np.zeros_like(out)
        for i, kv in enumerate(k):
            sl = [slice(None)] * img.ndim
            sl[axis] = slice(i, i + out.shape[axis])
            acc += kv * p[tuple(sl)]
        out = acc
    return out


def resize_nearest(img: np.ndarray, w: int, h: int) -> np.ndarray:
    ys = (np.arange(h) * img.shape[0] / h).astype(int)
    xs = (np.arange(w) * img.shape[1] / w).astype(int)
    return img[ys][:, xs]


def resize_box(img: np.ndarray, factor: int) -> np.ndarray:
    h, w = img.shape[:2]
    return img[:h - h % factor, :w - w % factor].reshape(h // factor, factor, w // factor, factor, -1).mean(axis=(1, 3))


# --- composing the character texture ------------------------------------------------------------------------------


def paste(base: np.ndarray, layer: np.ndarray, section: str):
    """Alpha-paste an RGBA layer (0..1, the section's size at 512) into a section of an RGB atlas, in place."""
    x, y, w, h = SECTIONS[section]
    if layer.shape[:2] != (h, w):
        f = layer.shape[0] // h
        layer = resize_box(layer, f) if f > 1 else resize_nearest(layer, w, h)
    a = layer[..., 3:4]
    base[y:y + h, x:x + w] = base[y:y + h, x:x + w] * (1 - a) + layer[..., :3] * a


def compose_albedo(skin: np.ndarray, face_lower=None, face_upper=None, torso=None, pelvis=None, mark=None):
    """skin (512, 512, 3|4) 0..1; the other layers RGBA 0..1. The client's order: skin, underwear, face, mark."""
    out = skin[..., :3].copy()
    if pelvis is not None:
        paste(out, pelvis, "LU")
    if torso is not None:
        paste(out, torso, "TU")
    if face_lower is not None:
        paste(out, face_lower, "FL")
    if face_upper is not None:
        paste(out, face_upper, "FU")
    if mark is not None:
        a = mark[..., 3:4]
        out = out * (1 - a) + mark[..., :3] * a
    return out


def look_rgba(look, glow=False, level=0) -> np.ndarray:
    pal = np.array(look.glow_palette if glow else look.palette, np.float64) / 255.0
    rgb = pal[look.t_levels[level]]
    a = look.a_levels[level].astype(np.float64) / 255.0
    return np.dstack([rgb, a])


# --- rendering ----------------------------------------------------------------------------------------------------


def arms_down(P: np.ndarray, Nn: np.ndarray, UV: np.ndarray, angle: float = -72.0):
    """The rest pose holds the arms out to the side; a preview lowers them (a rigid turn about the forward axis at
    the shoulder, eased over the top rows of the arm island) so the outer line of the arm faces outward as in game.
    No skinning: the shoulder joint stretches a little, which a preview can live with."""
    P = P.copy()
    Nn = Nn.copy()
    arm = (UV[:, 0] < 0.5) & (UV[:, 1] < 0.625)
    for side in (1, -1):
        m = arm & (np.sign(P[:, 1]) == side)
        top = m & (UV[:, 1] < 0.04)
        wrist = m & (np.abs(UV[:, 1] - 0.5) < 0.012)
        if not top.any() or not wrist.any():
            continue
        pv = P[top].mean(0)
        d = P[wrist].mean(0) - pv
        a0 = np.degrees(np.arctan2(d[2], abs(d[1])))
        phi = np.radians(angle - a0) * side
        e = np.clip(UV[m, 1] / 0.1, 0, 1)
        w = e * e * (3 - 2 * e)
        ph = phi * w
        c, s_ = np.cos(ph), np.sin(ph)
        y, z = P[m, 1] - pv[1], P[m, 2] - pv[2]
        P[m, 1] = pv[1] + y * c - z * s_
        P[m, 2] = pv[2] + y * s_ + z * c
        ny, nz = Nn[m, 1].copy(), Nn[m, 2].copy()
        Nn[m, 1] = ny * c - nz * s_
        Nn[m, 2] = ny * s_ + nz * c
    return P, Nn


def render(model, albedo: np.ndarray, emissive: np.ndarray | None, view: str, night: bool, size=(300, 520),
           eye_sprite: np.ndarray | None = None, eye_colour_boost: float = 1.0, pose: str = "arms_down") -> np.ndarray:
    tris, _ = model.body_tris()
    P = model.pos.copy()
    P[:, 0] *= model.forward
    Nn = model.nrm.copy()
    Nn[:, 0] *= model.forward
    UV = model.uv
    if pose == "arms_down":
        P, Nn = arms_down(P, Nn, UV)
    sign = 1 if view == "front" else -1
    if view == "side":  # from the left (+y), the face to the right
        sx = P[:, 0]
        depth = P[:, 1]
        sign = 1
    else:
        sx = -P[:, 1] * sign
        depth = P[:, 0] * sign
    W, H = size
    used = np.unique(tris)
    zmin, zmax = P[used, 2].min(), P[used, 2].max()
    scale = (H - 16) / (zmax - zmin)
    cx = (sx[used].max() + sx[used].min()) / 2
    X = (sx - cx) * scale + W / 2
    Y = (zmax - P[:, 2]) * scale + 8
    zbuf = np.full((H, W), -np.inf)
    gu = np.zeros((H, W))
    gv = np.zeros((H, W))
    gn = np.zeros((H, W, 3))
    hit = np.zeros((H, W), bool)

    def raster(tri_list, cb):
        for tri in tri_list:
            xs, ys, zs = X[tri], Y[tri], depth[tri]
            x0, x1 = int(max(0, np.floor(xs.min()))), int(min(W - 1, np.ceil(xs.max())))
            y0, y1 = int(max(0, np.floor(ys.min()))), int(min(H - 1, np.ceil(ys.max())))
            if x1 < x0 or y1 < y0:
                continue
            den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
            if abs(den) < 1e-12:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / den
            w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / den
            w2 = 1 - w0 - w1
            ins = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if ins.any():
                cb(tri, x0, x1, y0, y1, w0, w1, w2, ins, zs)

    def body(tri, x0, x1, y0, y1, w0, w1, w2, ins, zs):
        z = w0 * zs[0] + w1 * zs[1] + w2 * zs[2]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        upd = ins & (z > sub)
        if not upd.any():
            return
        sub[upd] = z[upd]
        for arr, comp in ((gu, 0), (gv, 1)):
            val = w0 * UV[tri[0], comp] + w1 * UV[tri[1], comp] + w2 * UV[tri[2], comp]
            arr[y0:y1 + 1, x0:x1 + 1][upd] = val[upd]
        n = w0[..., None] * Nn[tri[0]] + w1[..., None] * Nn[tri[1]] + w2[..., None] * Nn[tri[2]]
        gn[y0:y1 + 1, x0:x1 + 1][upd] = n[upd]
        hit[y0:y1 + 1, x0:x1 + 1][upd] = True

    raster(tris, body)
    ui = np.clip((gu * N).astype(int), 0, N - 1)
    vi = np.clip((gv * N).astype(int), 0, N - 1)
    alb = albedo[vi, ui]
    n = gn / (np.linalg.norm(gn, axis=-1, keepdims=True) + 1e-9)
    L = np.array([0.75 * sign, -0.35 * sign, 0.55]) if view != "side" else np.array([0.45, 0.75, 0.5])
    L /= np.linalg.norm(L)
    ndl = np.clip((n * L).sum(-1), 0, 1)
    glow_img = np.zeros((H, W, 3))
    if emissive is not None:
        glow_img = np.where(hit[..., None], emissive[vi, ui], 0.0)
    if night:
        img = alb * (0.10 + 0.22 * ndl)[..., None] + glow_img * 1.2
        bg = np.array([0.02, 0.025, 0.05])
    else:
        img = alb * (0.42 + 0.7 * ndl)[..., None] + glow_img * 0.35
        bg = np.array([0.16, 0.16, 0.18])
    img = np.where(hit[..., None], img, bg)
    # eye glow: geoset 1703 additively with its sprite, depth tested against the body, front view only matters
    if eye_sprite is not None and 1703 in model.eye_tris:
        spr = eye_sprite.astype(np.float64)
        add = np.zeros((H, W, 3))

        def eyes(tri, x0, x1, y0, y1, w0, w1, w2, ins, zs):
            z = w0 * zs[0] + w1 * zs[1] + w2 * zs[2]
            sub = zbuf[y0:y1 + 1, x0:x1 + 1]
            vis = ins & (z >= sub - 0.02)
            if not vis.any():
                return
            u = w0 * UV[tri[0], 0] + w1 * UV[tri[1], 0] + w2 * UV[tri[2], 0]
            v = w0 * UV[tri[0], 1] + w1 * UV[tri[1], 1] + w2 * UV[tri[2], 1]
            sh, sw = spr.shape[:2]
            ix = np.clip((np.mod(u, 1.0) * sw).astype(int), 0, sw - 1)
            iy = np.clip((np.mod(v, 1.0) * sh).astype(int), 0, sh - 1)
            px = spr[iy, ix]
            add[y0:y1 + 1, x0:x1 + 1][vis] += (px[..., :3] * px[..., 3:4])[vis] * eye_colour_boost

        raster(model.eye_tris[1703], eyes)
        img = img + add
        glow_img = glow_img + add
    if night:
        img = img + 0.9 * blur(np.clip(glow_img, 0, 1), 5.0)
    else:
        img = img + 0.25 * blur(np.clip(glow_img, 0, 1), 4.0)
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def crop_head(img: np.ndarray, model, view_size, frac=0.22) -> np.ndarray:
    """The top part of a render (the head), enlarged 2x."""
    H, W = img.shape[:2]
    h = int(H * frac)
    part = img[:h, W // 4: 3 * W // 4]
    return np.repeat(np.repeat(part, 2, 0), 2, 1)


def atlas_sheet(albedo: np.ndarray, glow: np.ndarray, title: str, lines: list[str]) -> np.ndarray:
    """The texture sheet: the composited atlas with section frames, the glow layer, and a caption."""
    a = (np.clip(albedo, 0, 1) * 255).astype(np.uint8)
    a = np.repeat(np.repeat(a, 3, 0), 3, 1)[::2, ::2]  # 768
    for k, (x, y, w, h) in SECTIONS.items():
        x0, y0, x1, y1 = int(x * 1.5), int(y * 1.5), int((x + w) * 1.5) - 1, int((y + h) * 1.5) - 1
        a[y0, x0:x1] = (255, 220, 0)
        a[y1, x0:x1] = (255, 220, 0)
        a[y0:y1, x0] = (255, 220, 0)
        a[y0:y1, x1] = (255, 220, 0)
        text(a, x0 + 4, y0 + 4, k, (255, 220, 0), 2)
    g = resize_nearest((np.clip(glow, 0, 1) * 255).astype(np.uint8), 384, 384)
    sheet = np.full((768, 768 + 384 + 16, 3), 18, np.uint8)
    sheet[:, :768] = a
    sheet[:384, 784:784 + 384] = g[:384, :384]
    text(sheet, 784, 396, title[:40], (240, 240, 240), 2)
    for i, ln in enumerate(lines[:20]):
        text(sheet, 784, 424 + i * 18, ln[:48], (170, 170, 170), 1 if len(ln) > 30 else 2)
    return sheet


def model_sheet(views: list[np.ndarray], title: str, labels: list[str]) -> np.ndarray:
    H, W = views[0].shape[:2]
    sheet = np.full((H + 30, len(views) * (W + 8), 3), 12, np.uint8)
    for i, v in enumerate(views):
        sheet[30:30 + H, i * (W + 8):i * (W + 8) + W] = v
        text(sheet, i * (W + 8) + 4, 34, labels[i] if i < len(labels) else "", (200, 200, 200), 1)
    text(sheet, 6, 8, title[:100], (235, 235, 235), 2)
    return sheet
