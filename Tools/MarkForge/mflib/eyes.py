r"""Eye sprites: the model's own deathKnightEyeGlow.blp recoloured, one per race, sex and eye colour.

The client draws geoset 1703 with the texture the model names for it (usually Character\<Race>\<Sex>\
deathKnightEyeGlow.blp, a 32x32 DXT5 radial glow; the package has two different ones). Bleakhold.exe draws those
batches with a face row's third texture instead (the contract), so a sprite must keep the layout the model's UVs
expect: the same size, the same encoding (the contract), the same alpha. Only the colour changes:

    intensity  I = the brightest channel of the source texel (0..1)
    whiteness  w = how far the source texel's colour is toward white beyond the sprite's own typical whiteness
               (its bright core), 0..1
    colour     I x mix(c', white, eye_core x w), c' = the eye colour with its brightest channel at 1

so the glow keeps its falloff and its hot centre and takes the new hue. The sprites are made on the VPS from the
client's own file: they are derived game art and are never committed.
"""

from __future__ import annotations

import numpy as np

from . import MarkForgeError
from .archive import blp_info, decode_blp
from .draw import hexrgb


def recolour(src_rgba: np.ndarray, hex_colour: str, core: float = 0.55) -> np.ndarray:
    """(H, W, 4) uint8 -> (H, W, 4) uint8 with the alpha untouched."""
    rgb = src_rgba[..., :3].astype(np.float64) / 255.0
    a = src_rgba[..., 3]
    hi = rgb.max(-1)
    lo = rgb.min(-1)
    white = np.where(hi > 1e-6, lo / np.maximum(hi, 1e-6), 0.0)
    strong = a > 64
    base = float(np.median(white[strong])) if strong.any() else float(np.median(white))
    w = np.clip((white - base) / max(1.0 - base, 1e-6), 0.0, 1.0)
    c = hexrgb(hex_colour)
    cn = c / max(float(c.max()), 1e-6)
    out = hi[..., None] * (cn[None, None, :] * (1 - core * w[..., None]) + core * w[..., None])
    res = np.empty_like(src_rgba)
    res[..., :3] = np.clip(np.round(out * 255), 0, 255).astype(np.uint8)
    res[..., 3] = a
    return res


def sprite_blp(src_data: bytes, hex_colour: str, core: float = 0.55) -> bytes:
    """A recoloured copy of the source sprite in the source's own size and encoding."""
    import blpconvert
    info = blp_info(src_data)
    w, h = info["width"], info["height"]
    rgba = recolour(decode_blp(src_data), hex_colour, core)
    img = blpconvert.Image(w, h, bytearray(rgba.tobytes()))
    if info["encoding"] == 2:
        fmt = {0: "dxt1", 7: "dxt5"}.get(info["preferred"])
        if fmt is None:
            raise MarkForgeError(f"eye sprite source has DXT preferredFormat {info['preferred']}; only DXT1 and DXT5 "
                                 "are written")
    elif info["encoding"] == 1:
        fmt = "pal8"
        if info["alpha"] != 8:
            raise MarkForgeError(f"eye sprite source is a palette texture with alphaSize {info['alpha']}; "
                                 "pal8 writes 8")
    elif info["encoding"] == 3:
        fmt = "bgra"
    else:
        raise MarkForgeError(f"eye sprite source has colorEncoding {info['encoding']}")
    return encode(img, fmt, bool(info["mips"] & 0xF))


def encode(img, fmt: str, mips: bool) -> bytes:
    """blpconvert's encoder into bytes (it writes files; a temporary file keeps it unchanged)."""
    import os
    import tempfile
    import blpconvert
    fd, path = tempfile.mkstemp(suffix=".blp")
    os.close(fd)
    try:
        blpconvert.convert(img, path, fmt, mips, jobs=1)
        with open(path, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def synthetic_source(size: int = 32) -> bytes:
    """Our own stand-in for a deathKnightEyeGlow layout (fixture mode and tests): a radial glow, pale cyan with a
    white core, DXT5 with mips, like the client's files."""
    import blpconvert
    y, x = np.mgrid[0:size, 0:size]
    r = np.hypot(x - size / 2 + 0.5, y - size / 2 + 0.5) / (size / 2)
    a = np.clip(np.exp(-(r / 0.35) ** 2) * 1.05, 0, 1)
    core = np.clip(1 - r / 0.25, 0, 1)
    rgb = np.stack([0.18 + 0.6 * core, 0.7 + 0.25 * core, np.ones_like(r)], -1) * np.clip(0.4 + a, 0, 1)[..., None]
    rgba = np.dstack([np.clip(rgb, 0, 1) * 255, a * 255]).round().astype(np.uint8)
    return encode(blpconvert.Image(size, size, bytearray(rgba.tobytes())), "dxt5", True)
