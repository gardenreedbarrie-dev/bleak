r"""From a design's line core and halo to the two files of a look, and the checks that fail the build.

Profiles (per element, designs.py): core = hard-edged line from the distance field (anti-aliased over one local
texel), halo = exp(-(d - w) / sigma) with sigma = 3.5 w + 2 texels (1.5 w + 1 texel on the face). Then over the atlas:

    fade   0 inside keep-out zones and the garment mask, rising from 4.5 to 10.5 texels away from them (7.5 on the
           face; so even the 128 mip keeps them clean); 0 at cut seams rising over 10 texels; on the head times the
           forward-facing amount; 0 on the feet. Wrap seams are not faded: the charts are periodic there.
    gutter 2 texels past the islands' borders take the nearest inside value (texture filtering at UV borders)

A glowing colour c (palette ramp of 256 entries, entry i at core i / 255):
    mark   colour mix(c, white, 0.45 core), alpha clip(0.92 core + 0.35 halo)
    _Glow  colour mix(c / max(c), white, 0.35 core): the emitted light, its peak channel 255 so bloom catches it;
           the same palette indices and the same alpha bytes as the mark at every level (the contract: the glow bake
           pastes it through the mark's alpha)
A paint colour (no _Glow): colour c x (0.86 .. 1.0) by a fixed grain, alpha clip(core) x opacity x (0.9 .. 1.0).

Mips: alpha is box-filtered, the ramp position alpha-weighted, then both are rounded per level, down to 1x1. Fully
transparent texels keep index 0 (the base colour), so filtering never darkens edges.
"""

from __future__ import annotations

import math

import numpy as np

from . import MarkForgeError
from .atlas import ISLAND_ARM, ISLAND_BODY, ISLAND_HEAD, N, SECTIONS, distance_3d, island_distance, island_of

DEAD = 4.5  # texels of nothing next to a keep-out zone or garment
RAMP = 6.0  # then a ramp to full strength
HEAD_RAMP = 3.0
CUT_DEAD = 1.5  # texels of nothing at a cut seam, then a gentle ramp (both sides fade to 0: continuous)
CUT_RAMP = 10.0


def hexrgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float64) / 255.0


def fade_field(at, charts, garment: np.ndarray | None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(fade, blocked, dead): the strength multiplier over the atlas, the texels that must hold no ink at all
    (keep-out, garment, feet), and the wider zone within DEAD atlas texels of them that stays empty too."""
    blocked = at.keepout.copy() if at.keepout is not None else np.zeros((N, N), bool)
    if garment is not None:
        blocked |= garment
    X, Y = np.meshgrid(np.arange(N), np.arange(N))
    feet = (at.island_ext == ISLAND_BODY) & (Y >= 448)
    blocked |= feet
    pos_island = island_of(X, Y)
    d_atlas = island_distance(blocked, np.where(at.painted | blocked, pos_island, -2), DEAD + RAMP + 1)
    d = d_atlas
    # on the limbs and the body use the 3D distance, the same on both sides of a wrap seam
    P = at.pos.copy()
    P[..., 1] = np.abs(P[..., 1])
    seeds = {}
    for isl in (ISLAND_ARM, ISLAND_BODY):
        m = blocked & at.painted & (at.island_ext == isl)
        seeds[isl] = P[m]
    d3 = distance_3d(at, seeds, DEAD + RAMP + 1)
    d = np.where(np.isin(at.island_ext, (ISLAND_ARM, ISLAND_BODY)), d3, d)
    ramp = np.where(at.island_ext == ISLAND_HEAD, HEAD_RAMP, RAMP)  # the face is small: a shorter ramp there
    fade = np.clip((d - DEAD) / ramp, 0.0, 1.0)
    # and never ink within DEAD atlas texels of a blocked one, whatever the 3D spacing: a 2x2 or 4x4 block of the
    # 256 and 128 levels that holds a blocked texel then averages zeros only
    d_dead = island_distance(blocked, pos_island, DEAD + 1)  # every texel of the island, inked by the gutter or not
    fade[d_dead < DEAD] = 0.0
    fade = np.where(at.painted, fade, 0.0)
    fade *= np.clip((at.cut_dist - CUT_DEAD) / CUT_RAMP, 0.0, 1.0)
    head = at.island_ext == ISLAND_HEAD
    fade = np.where(head, fade * np.clip(charts.facing * 2.5, 0.0, 1.0), fade)
    fade[blocked] = 0.0
    dead = blocked | (d_dead < DEAD)
    return fade, blocked, dead


def gutter(field: np.ndarray, valid: np.ndarray, blocked: np.ndarray, steps: int = 2) -> np.ndarray:
    """Extend values from the island texels into the invalid ones next to them (same island by position), never
    into blocked texels."""
    X, Y = np.meshgrid(np.arange(N), np.arange(N))
    isl = island_of(X, Y)
    out = field.copy()
    have = valid.copy()
    for _ in range(steps):
        pad_v = np.pad(out, 1)
        pad_h = np.pad(have, 1)
        pad_i = np.pad(isl, 1, constant_values=-1)
        acc = np.zeros_like(out)
        cnt = np.zeros_like(out)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nv = pad_v[1 + dy:1 + dy + N, 1 + dx:1 + dx + N]
            nh = pad_h[1 + dy:1 + dy + N, 1 + dx:1 + dx + N] & (pad_i[1 + dy:1 + dy + N, 1 + dx:1 + dx + N] == isl)
            acc += np.where(nh, nv, 0.0)
            cnt += nh
        new = ~have & (cnt > 0) & ~blocked
        out = np.where(new, acc / np.maximum(cnt, 1), out)
        have = have | new
    return out


def grain(seed: int = 1709) -> np.ndarray:
    """A fixed paint grain 0..1 over the atlas (value noise at about 3 texels)."""
    rs = np.random.RandomState(seed)
    small = rs.rand(N // 4 + 2, N // 4 + 2)
    y = (np.arange(N) + 0.5) / 4.0
    y0 = np.floor(y).astype(int)
    fy = y - y0
    rows = small[y0] * (1 - fy)[:, None] + small[y0 + 1] * fy[:, None]
    cols = rows[:, y0] * (1 - fy)[None, :] + rows[:, y0 + 1] * fy[None, :]
    return cols


_GRAIN = None


class Look:
    """The level data of one look: palette indices and alpha per mip level, plus the two palettes."""

    def __init__(self, t_levels, a_levels, palette, glow_palette):
        self.t_levels = t_levels  # list of uint8 arrays (h, w)
        self.a_levels = a_levels
        self.palette = palette  # list of (r, g, b)
        self.glow_palette = glow_palette  # None for paint

    def blp(self, glow=False) -> bytes:
        import blpconvert
        pal = self.glow_palette if glow else self.palette
        return blpconvert.pack_pal8(N, N, pal, [t.tobytes() for t in self.t_levels],
                                    [a.tobytes() for a in self.a_levels], True)


def mip_chain(t: np.ndarray, a: np.ndarray):
    """Rounded uint8 levels from float ramp positions t and alpha a (both 0..1) at 512."""
    t_levels, a_levels = [], []
    tw = t * a
    while True:
        t = np.where(a > 0, tw / np.maximum(a, 1e-12), 0.0)
        t_levels.append(np.clip(np.round(t * 255), 0, 255).astype(np.uint8))
        a_levels.append(np.clip(np.round(a * 255), 0, 255).astype(np.uint8))
        if a.shape[0] == 1 and a.shape[1] == 1:
            break
        h, w = a.shape
        a = a.reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))
        tw = tw.reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))
    return t_levels, a_levels


def compose(core: np.ndarray, halo: np.ndarray, colour: dict) -> Look:
    """The look of one design (faded core and halo) in one colour of palettes.json."""
    global _GRAIN
    c = hexrgb(colour["hex"])
    if colour.get("glow"):
        alpha = np.clip(0.92 * core + 0.35 * halo, 0, 1)
        t = np.clip(core, 0, 1)
        ramp = np.linspace(0, 1, 256)[:, None]
        pal = np.round(255 * (c[None, :] * (1 - 0.45 * ramp) + 0.45 * ramp)).astype(int)
        cn = c / max(float(c.max()), 1e-6)
        gpal = np.round(255 * (cn[None, :] * (1 - 0.35 * ramp) + 0.35 * ramp)).astype(int)
        glow_palette = [tuple(int(v) for v in row) for row in gpal]
    else:
        if _GRAIN is None:
            _GRAIN = grain()
        opacity = float(colour.get("opacity", 0.9))
        alpha = np.clip(core, 0, 1) * opacity * (0.9 + 0.1 * _GRAIN)
        t = _GRAIN
        ramp = np.linspace(0, 1, 256)[:, None]
        pal = np.round(255 * c[None, :] * (0.86 + 0.14 * ramp)).astype(int)
        glow_palette = None
    palette = [tuple(int(v) for v in row) for row in pal]
    t_levels, a_levels = mip_chain(t, alpha)
    return Look(t_levels, a_levels, palette, glow_palette)


def design_fields(at, charts, painted_core, painted_halo, fade, dead):
    """Faded core and halo with their 2-texel gutter; nothing ever lands in the dead zone (the gutter neither)."""
    core = gutter(painted_core * fade, at.painted, dead)
    halo = gutter(painted_halo * fade, at.painted, dead)
    core[dead] = 0.0
    halo[dead] = 0.0
    return core, halo


# --- checks --------------------------------------------------------------------------------------------------------


def bilinear(field: np.ndarray, u: float, v: float) -> float:
    x, y = u - 0.5, v - 0.5
    x0, y0 = int(math.floor(x)), int(math.floor(y))
    fx, fy = x - x0, y - y0
    x0c, x1c = min(max(x0, 0), N - 1), min(max(x0 + 1, 0), N - 1)
    y0c, y1c = min(max(y0, 0), N - 1), min(max(y0 + 1, 0), N - 1)
    return float(field[y0c, x0c] * (1 - fx) * (1 - fy) + field[y0c, x1c] * fx * (1 - fy) +
                 field[y1c, x0c] * (1 - fx) * fy + field[y1c, x1c] * fx * fy)


def head_only(seam) -> bool:
    """Both sides of the seam in the head island: a cut of the head's own (cut_distance leaves those unfaded)."""
    return all(int(island_of((u0 + u1) / 2, (v0 + v1) / 2)) == ISLAND_HEAD for (u0, v0), (u1, v1) in (seam.a, seam.b))


def seam_report(at, field: np.ndarray, kinds=("wrap",), head_cuts: bool | None = None) -> dict:
    """The largest difference of a field across seams: each seam edge sampled at 1/4, 1/2 and 3/4 on both of its UV
    sides, texels a little inside each side (the sample of the client's filter). head_cuts: None every seam of the
    kinds, False all but the head's own cuts (head_only()), True only those."""
    worst, worst_at, samples, inked = 0.0, None, 0, 0
    for s in at.seams:
        if s.kind not in kinds:
            continue
        if head_cuts is not None and head_only(s) != head_cuts:
            continue
        for f in (0.25, 0.5, 0.75):
            vals = []
            for (u0, v0), (u1, v1) in (s.a, s.b):
                vals.append(bilinear(field, u0 + (u1 - u0) * f, v0 + (v1 - v0) * f))
            samples += 1
            if max(vals) > 0.05:
                inked += 1
                dlt = max(vals) - min(vals)
                if dlt > worst:
                    worst, worst_at = dlt, [list(s.a), list(s.b)]
    return {"kinds": list(kinds), "samples": samples, "with_ink": inked, "max": round(worst, 4), "worst": worst_at}


def ink_inside(look: Look, mask: np.ndarray, levels: int = 3) -> list[int]:
    """Texels with alpha > 0 inside a mask, at the first `levels` mip levels (a coarse texel counts as inside when
    any of its texels is)."""
    out = []
    m = mask
    for i in range(levels):
        a = look.a_levels[i]
        out.append(int(((a > 0) & m).sum()))
        h, w = m.shape
        m = m.reshape(h // 2, 2, w // 2, 2).any(axis=(1, 3))
    return out


def sections_with_ink(look: Look) -> list[str]:
    a = look.a_levels[0]
    return [k for k, (x, y, w, h) in SECTIONS.items() if (a[y:y + h, x:x + w] > 0).any()]


def coverage(look: Look) -> float:
    return round(float((look.a_levels[0] > 0).mean()) * 100, 2)


def check_minimum(look: Look, key: str):
    if not (look.a_levels[0] > 0).any():
        raise MarkForgeError(f"{key}: the look has no ink at all")


# --- the contract's file rules ---------------------------------------------------------------------------------------

def _read(out, texture):
    """The bytes of a client path from a staging folder (out/files/<path>), or from a reader: a callable
    texture -> bytes or None (build checks its files in memory, before anything is written)."""
    import os
    if callable(out):
        return out(texture)
    path = os.path.join(out, "files", *texture.split("\\"))
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def mark_problems(data: bytes, where: str) -> list[str]:
    """A mark: BLP2, palette, alphaSize 8, 512 x 512, every level (10), each exactly indices + alpha, decodable."""
    from .archive import blp_info, decode_blp
    try:
        h = blp_info(data)
    except MarkForgeError as e:
        return [f"{where}: {e}"]
    out = []
    if (h["encoding"], h["alpha"]) != (1, 8):
        out.append(f"{where}: colorEncoding {h['encoding']} alphaSize {h['alpha']}, the contract wants 1 and 8")
    if (h["width"], h["height"]) != (N, N):
        out.append(f"{where}: {h['width']}x{h['height']}, the contract wants {N}x{N}")
    if not h["mips"] & 0xF:
        out.append(f"{where}: hasMips is 0, the contract wants every level")
    for i in range(10):
        n = max(1, N >> i) ** 2
        if h["sizes"][i] != 2 * n:
            out.append(f"{where}: level {i} has {h['sizes'][i]} bytes, {2 * n} expected")
        elif h["offsets"][i] + h["sizes"][i] > len(data):
            out.append(f"{where}: level {i} lies past the end of the file")
    if not out:
        try:
            decode_blp(data, 9)
        except MarkForgeError as e:
            out.append(f"{where}: {e}")
    return out


def glow_problems(mark: bytes, glow: bytes, where: str) -> list[str]:
    """_Glow: the mark's header fields and its alpha bytes at every level, byte for byte."""
    from .archive import blp_info
    out = mark_problems(glow, where)
    if out:
        return out
    hm, hg = blp_info(mark), blp_info(glow)
    for k in ("encoding", "alpha", "preferred", "mips", "width", "height", "offsets", "sizes"):
        if hm[k] != hg[k]:
            out.append(f"{where}: header field {k} differs from the mark's")
    if not out:
        for i in range(10):
            n = max(1, N >> i) ** 2
            o = hm["offsets"][i]
            if mark[o + n:o + 2 * n] != glow[o + n:o + 2 * n]:
                out.append(f"{where}: alpha of level {i} differs from the mark's")
                break
    return out


def validate_mark(out, m) -> list[str]:
    import hashlib
    probs = []
    data = _read(out, m["texture"])
    if data is None:
        return [f"{m['texture']}: missing"]
    if hashlib.sha1(data).hexdigest() != m["sha1"]:
        probs.append(f"{m['texture']}: SHA-1 differs from the manifest")
    probs += mark_problems(data, m["texture"])
    if m.get("glow"):
        g = _read(out, m["glow_texture"]) if m.get("glow_texture") else None
        if g is None:
            probs.append(f"{m.get('glow_texture')}: missing (the colour glows)")
        else:
            if hashlib.sha1(g).hexdigest() != m["glow_sha1"]:
                probs.append(f"{m['glow_texture']}: SHA-1 differs from the manifest")
            probs += glow_problems(data, g, m["glow_texture"])
    elif m.get("glow_texture"):
        probs.append(f"{m['texture']}: a paint colour with a _Glow file")
    return probs


def validate_eye(out, e, source) -> list[str]:
    import hashlib
    from .archive import blp_info, decode_blp
    data = _read(out, e["texture"])
    if data is None:
        return [f"{e['texture']}: missing"]
    probs = []
    if hashlib.sha1(data).hexdigest() != e["sha1"]:
        probs.append(f"{e['texture']}: SHA-1 differs from the manifest")
    try:
        h = blp_info(data)
        decode_blp(data)
    except MarkForgeError as ex:
        return probs + [f"{e['texture']}: {ex}"]
    if source:
        want = (source.get("width"), source.get("height"), source.get("encoding"), source.get("preferred"))
        preferred = h["preferred"] if h["encoding"] == 2 else source.get("preferred")
        have = (h["width"], h["height"], h["encoding"], preferred)
        if None not in want and want != have:
            probs.append(f"{e['texture']}: {have} but the model's own sprite is {want} (width, height, encoding, "
                         "preferredFormat)")
    return probs
