"""The patch marker: a tiny texture MapForge draws itself (no game data) and packs into the map archive.

An addon cannot list archive contents, but `Texture:SetTexture(path)` only succeeds for a file the client can open,
so a file that exists nowhere else proves the player has this map's patch (royale-spec.md 1 and 8: the Royale card
stays disabled without it). The picture: a purple storm ring around a gold core on a transparent background, 32 x 32,
DXT5 with every mip level (Tools/BlpConvert).
"""

from __future__ import annotations

import blpconvert  # noqa: E402  (Tools/BlpConvert, added to sys.path by the dbc package)

SIZE = 32
RING = (138, 43, 226)
CORE = (255, 196, 60)


def _coverage(distance: float, inner: float, outer: float) -> float:
    """1 inside [inner, outer], fading to 0 over one pixel outside it."""
    if distance < inner:
        return max(0.0, 1.0 - (inner - distance))
    if distance > outer:
        return max(0.0, 1.0 - (distance - outer))
    return 1.0


def marker_image() -> blpconvert.Image:
    img = blpconvert.Image(SIZE, SIZE)
    centre = SIZE / 2.0

    for y in range(SIZE):
        for x in range(SIZE):
            dx = x + 0.5 - centre
            dy = y + 0.5 - centre
            d = (dx * dx + dy * dy) ** 0.5
            ring = _coverage(d, 10.5, 14.0)
            core = _coverage(d, -1.0, 5.0)
            alpha = max(ring, core)
            rgb = CORE if core >= ring else RING
            i = (y * SIZE + x) * 4
            img.data[i:i + 4] = bytes((rgb[0], rgb[1], rgb[2], int(alpha * 255.0 + 0.5)))

    return img


def write_marker_blp(path: str) -> str:
    """Write the marker as a BLP2 file the 3.3.5a client loads; returns path."""
    blpconvert.convert(marker_image(), path, fmt="dxt5", jobs=1)
    return path
