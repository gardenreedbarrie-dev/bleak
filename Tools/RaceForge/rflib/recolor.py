"""The skin colour change of `raceforge.py skins`, in OKLab (Bjorn Ottosson's perceptual colour space, sRGB gamma
correct): what the skin colour of a texture is, which target colour it gets, and how every colour of the texture
moves with it.

A skin texture's colour is the component-wise median (L, a, b) of its opaque pixels of mid lightness (stats()); as
lightness, chroma and hue that is (Lm, Cm, hm). A target (Lt, Ct, ht) comes from the palette (targets()). A colour
(L, C, h) then becomes (Transform.lab()):

    L' = L ** (ln Lt / ln Lm)                 (the gamma clamped to [0.5, 2.5]: Lm becomes Lt, the shading stays)
    C' = Ct * (C / Cm) ** 0.7                 (at most 0.16; see chroma_floor for a nearly grey skin)
    h' = ht + 0.3 * wrap(h - hm)              (hues near the skin's keep part of their spread)

and the result is OKLab's straight line from the old colour to that one, at weight w = w_hue * w_chroma: a colour far
from the skin's hue (more than 35 degrees, nothing beyond 65) or far more colourful than the skin (Cm + 0.07, nothing
beyond Cm + 0.13) moves less or not at all, so green eyes keep their colour. A colour of chroma below 0.35 * Cm, or
below chroma_floor (0.02), has no reliable hue: it counts as skin (w_hue 1) and takes the target hue as it is (h' =
ht). A more colourful one is weighed by its hue, on a skin that is nearly grey (Cm below chroma_floor, a Death
Knight's) too: such a skin's own colours are nearly grey as well and move with it, and its hue is little more than
noise, so a colour on it is weighed against the nearer of that hue and the hue of the race's other skins of the sex
(living_hue()): its lips and blush, near the living skin's hue, move with it, while its green eyes, far from both,
keep their colour. Such a skin's chroma ratio is (C + 0.02 - Cm) / 0.02 instead, so the skin's colour still gets Ct
and greyer and more colourful ones a little less and more (C / Cm would make every faint tint of it fully
colourful). The numbers are skins.json's "transform" (DEFAULTS). Back in sRGB, a colour outside the gamut loses
chroma until it fits.

Everything a Transform does follows from its params(), which name the new textures (skins.py hashes them): the
stats and targets are rounded before use, so the same inputs give the same files on every machine.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

# Bumped whenever the transform or the recolouring of a format changes: the new textures then get new names.
ALGORITHM_VERSION = "raceforge-skins-2"

DEFAULTS = {
    "hue_unreliable_below": 0.35,  # C < this * Cm (or C < chroma_floor): no reliable hue, w_hue = 1
    "hue_full_within": 35.0,  # degrees from hm: w_hue = 1
    "hue_none_beyond": 65.0,  # degrees from hm: w_hue = 0 (linear in between)
    "chroma_full_within": 0.07,  # C <= Cm + this: w_chroma = 1
    "chroma_none_beyond": 0.13,  # C >= Cm + this: w_chroma = 0 (linear in between)
    "gamma_min": 0.5,
    "gamma_max": 2.5,
    "chroma_exponent": 0.7,
    "chroma_floor": 0.02,  # a colour of less chroma has no reliable hue; a skin of less, a gentler chroma ratio
    "chroma_max": 0.16,  # tuned on previews from 0.25: lips and shadows stay violet instead of a bright blue
    "hue_spread": 0.3,  # tuned from 0.6, for the same reason
    "stats_alpha_min": 128,  # pixels with less alpha are not skin (when the texture has alpha)
    "stats_lightness_min": 0.2,  # nor the darkest and the lightest ones (shadows, highlights, eye whites)
    "stats_lightness_max": 0.97,
}

_HEX = re.compile(r"#?([0-9A-Fa-f]{6})")


class RecolorError(Exception):
    pass


# --- sRGB <-> OKLab ----------------------------------------------------------------------------------------------


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


LINEAR = tuple(_to_linear(i / 255) for i in range(256))


def _cbrt(x: float) -> float:
    return math.copysign(abs(x) ** (1 / 3), x)


def linear_to_oklab(r: float, g: float, b: float) -> tuple[float, float, float]:
    l_ = _cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m_ = _cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s_ = _cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def oklab_to_linear(L: float, a: float, b: float) -> tuple[float, float, float]:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    lc, mc, sc = l_ ** 3, m_ ** 3, s_ ** 3
    return (4.0767416621 * lc - 3.3077115913 * mc + 0.2309699292 * sc,
            -1.2684380046 * lc + 2.6097574011 * mc - 0.3413193965 * sc,
            -0.0041960863 * lc - 0.7034186147 * mc + 1.7076147010 * sc)


def srgb8_to_oklab(r: int, g: int, b: int) -> tuple[float, float, float]:
    return linear_to_oklab(LINEAR[r], LINEAR[g], LINEAR[b])


def _in_gamut(rgb: tuple[float, float, float], eps: float = 1e-7) -> bool:
    return all(-eps <= c <= 1 + eps for c in rgb)


def oklab_to_srgb8(L: float, a: float, b: float) -> tuple[int, int, int]:
    """The nearest 8-bit sRGB colour; outside the gamut the chroma shrinks (L and the hue stay) until it fits."""
    L = min(1.0, max(0.0, L))
    rgb = oklab_to_linear(L, a, b)

    if not _in_gamut(rgb):
        lo, hi = 0.0, 1.0

        for _ in range(24):
            mid = (lo + hi) / 2

            if _in_gamut(oklab_to_linear(L, a * mid, b * mid)):
                lo = mid
            else:
                hi = mid

        rgb = oklab_to_linear(L, a * lo, b * lo)

    return tuple(int(round(255 * _to_srgb(min(1.0, max(0.0, c))))) for c in rgb)


def hex_to_oklab(text: str) -> tuple[float, float, float]:
    match = _HEX.fullmatch(text.strip()) if isinstance(text, str) else None

    if not match:
        raise RecolorError(f"{text!r} is not a colour (#RRGGBB)")

    value = int(match.group(1), 16)
    return srgb8_to_oklab(value >> 16, (value >> 8) & 0xFF, value & 0xFF)


def lch(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    """(L, C, h in degrees 0-360)."""
    L, a, b = lab
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def wrap_degrees(d: float) -> float:
    """An angle difference in (-180, 180]."""
    d = (d + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


# --- the skin's colour and its target ----------------------------------------------------------------------------


@dataclass(frozen=True)
class SkinColour:
    L: float
    C: float
    h: float  # degrees
    pixels: int  # how many pixels it is the median of


def weighted_median(pairs: list[tuple[float, int]]) -> float:
    """The median of the multiset {value: count}: the middle value, or the mean of the two middle ones."""
    pairs = sorted(pairs)
    total = sum(n for _, n in pairs)
    lo_rank, hi_rank = (total - 1) // 2, total // 2
    lo = hi = None
    seen = 0

    for value, n in pairs:
        if lo is None and seen + n > lo_rank:
            lo = value

        if seen + n > hi_rank:
            hi = value
            break

        seen += n

    return (lo + hi) / 2


def stats(width: int, height: int, rgba: bytes, has_alpha: bool, settings: dict) -> SkinColour | None:
    """The skin colour of a decoded texture: the component-wise median of L, a and b over its opaque pixels (alpha >=
    stats_alpha_min when the texture has alpha) with L in [stats_lightness_min, stats_lightness_max]. None when no
    pixel qualifies."""
    alpha_min = settings["stats_alpha_min"]
    lo, hi = settings["stats_lightness_min"], settings["stats_lightness_max"]
    counts = Counter()

    for o in range(0, width * height * 4, 4):
        if has_alpha and rgba[o + 3] < alpha_min:
            continue

        counts[(rgba[o], rgba[o + 1], rgba[o + 2])] += 1

    labs = []

    for (r, g, b), n in counts.items():
        lab = srgb8_to_oklab(r, g, b)

        if lo <= lab[0] <= hi:
            labs.append((lab, n))

    if not labs:
        return None

    L, a, b = (weighted_median([(lab[i], n) for lab, n in labs]) for i in range(3))
    _, C, h = lch((L, a, b))
    return SkinColour(round(L, 6), round(C, 6), round(h, 4), sum(n for _, n in labs))


def sample(palette: list[tuple[float, float, float]], t: float) -> tuple[float, float, float]:
    """The palette (OKLab colours, lightest first) at t in [0, 1], linear in OKLab between neighbours."""
    if len(palette) == 1:
        return palette[0]

    x = min(1.0, max(0.0, t)) * (len(palette) - 1)
    i = min(int(x), len(palette) - 2)
    f = x - i
    return tuple(p + (q - p) * f for p, q in zip(palette[i], palette[i + 1]))


def targets(colours: dict[int, SkinColour], palette: list[tuple[float, float, float]]
            ) -> dict[int, tuple[float, float, float]]:
    """Each skin colour index's target (L, C, h): the colours are ranked by lightness (lightest first; equal ones by
    index) and colour rank r of n takes the palette at t = r / (n - 1), so the lightest gets the first entry and the
    darkest the last (one colour alone takes the middle of the palette). With as many colours as entries, each gets
    one entry as it is."""
    ranked = sorted(colours, key=lambda k: (-colours[k].L, k))
    n = len(ranked)
    out = {}

    for rank, k in enumerate(ranked):
        t = 0.5 if n == 1 else rank / (n - 1)
        L, C, h = lch(palette[rank] if n == len(palette) else sample(palette, t))
        out[k] = (round(L, 6), round(C, 6), round(h, 4))

    return out


def living_hue(colours: list[SkinColour], settings: dict) -> float | None:
    """The mean hue (on the circle) of the skin colours that are not nearly grey (chroma_floor), rounded; None when
    there is none."""
    hues = [math.radians(c.h) for c in colours if c.C >= settings["chroma_floor"]]

    if not hues:
        return None

    return round(math.degrees(math.atan2(sum(map(math.sin, hues)), sum(map(math.cos, hues)))) % 360, 4)


# --- the transform -----------------------------------------------------------------------------------------------


class Transform:
    """One skin colour's change: from its SkinColour to its target, with the settings of skins.json.

    living_hue: the hue of the race's skins of that sex that are not nearly grey (living_hue()). A nearly grey skin
    (a Death Knight's) has no hue of its own worth the name, so a colour on it counts as skin-hued when it is near
    either hue: its lips and blush, which sit near the living skin's hue, move with it, its green eyes do not."""

    def __init__(self, skin: SkinColour, target: tuple[float, float, float], settings: dict,
                 living_hue: float | None = None):
        self.skin = skin
        self.target = target
        self.settings = {k: settings[k] for k in DEFAULTS}
        s = self.settings
        grey = skin.C < s["chroma_floor"]
        self.living_hue = round(living_hue % 360, 4) if grey and living_hue is not None else None
        Lt, Ct, ht = target
        gamma = math.log(Lt) / math.log(skin.L) if 0 < skin.L < 1 and 0 < Lt < 1 else 1.0
        self.gamma = min(s["gamma_max"], max(s["gamma_min"], gamma))
        self.hm = skin.h
        self.Cm = skin.C
        self.Ct = Ct
        self.ht = ht
        self._rgb: dict[int, tuple[int, int, int]] = {}
        self._lut = [-1] * 65536

    def params(self) -> dict:
        """Everything the result depends on, as plain JSON values (skins.py hashes it into the textures' names)."""
        return {"algorithm": ALGORITHM_VERSION, "skin": [self.skin.L, self.skin.C, self.skin.h],
                "target": list(self.target), "settings": self.settings, "living_hue": self.living_hue}

    def hue_reliable(self, C: float) -> bool:
        """Whether a colour's hue means something next to the skin's: not when the colour is nearly grey (below
        chroma_floor), nor when it is much greyer than the skin. On a nearly grey skin, a clearly coloured colour (an
        eye) is weighed by its hue too, so it keeps its colour."""
        s = self.settings
        return C >= max(s["chroma_floor"], s["hue_unreliable_below"] * self.Cm)

    def reference(self, h: float) -> float:
        """The hue a colour of hue h is weighed against: the skin's, or on a nearly grey skin the nearer of the skin's
        and the living skin's."""
        if self.living_hue is not None and abs(wrap_degrees(h - self.living_hue)) < abs(wrap_degrees(h - self.hm)):
            return self.living_hue

        return self.hm

    def weight(self, C: float, h: float) -> float:
        s = self.settings

        if not self.hue_reliable(C):
            w_hue = 1.0
        else:
            d = abs(wrap_degrees(h - self.reference(h)))
            full, none = s["hue_full_within"], s["hue_none_beyond"]
            w_hue = 1.0 if d <= full else 0.0 if d >= none else (none - d) / (none - full)

        full, none = self.Cm + s["chroma_full_within"], self.Cm + s["chroma_none_beyond"]
        w_chroma = 1.0 if C <= full else 0.0 if C >= none else (none - C) / (none - full)
        return w_hue * w_chroma

    def lab(self, L: float, a: float, b: float) -> tuple[float, float, float] | None:
        """The colour's new OKLab value, or None when it does not move (weight 0)."""
        s = self.settings
        C = math.hypot(a, b)
        h = math.degrees(math.atan2(b, a))
        w = self.weight(C, h)

        if w <= 0.0:
            return None

        L2 = L ** self.gamma if L > 0 else 0.0
        floor = max(self.Cm, s["chroma_floor"])
        C2 = min(s["chroma_max"], self.Ct * ((C + floor - self.Cm) / floor) ** s["chroma_exponent"])
        spread = s["hue_spread"] * wrap_degrees(h - self.reference(h)) if self.hue_reliable(C) else 0.0
        h2 = math.radians(self.ht + spread)
        a2, b2 = C2 * math.cos(h2), C2 * math.sin(h2)
        return L + (L2 - L) * w, a + (a2 - a) * w, b + (b2 - b) * w

    def rgb(self, r: int, g: int, b: int) -> tuple[int, int, int]:
        """An 8-bit sRGB colour through the transform (a colour that does not move comes back as it was)."""
        key = (r << 16) | (g << 8) | b
        out = self._rgb.get(key)

        if out is None:
            moved = self.lab(*srgb8_to_oklab(r, g, b))
            out = (r, g, b) if moved is None else oklab_to_srgb8(*moved)
            self._rgb[key] = out

        return out

    def c565(self, value: int) -> int:
        """A DXT endpoint (RGB 5:6:5) through the transform: an entry of a 65536-entry table, filled when first
        needed. A colour that does not move keeps its exact value."""
        out = self._lut[value]

        if out < 0:
            r, g, b = (value >> 11) & 31, (value >> 5) & 63, value & 31
            r8, g8, b8 = (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)
            moved = self.lab(*srgb8_to_oklab(r8, g8, b8))

            if moved is None:
                out = value
            else:
                nr, ng, nb = oklab_to_srgb8(*moved)
                out = ((nr * 31 + 127) // 255) << 11 | ((ng * 63 + 127) // 255) << 5 | (nb * 31 + 127) // 255

            self._lut[value] = out

        return out


def settings_from(data: dict | None, where: str) -> dict:
    """skins.json's transform settings over DEFAULTS, checked."""
    out = dict(DEFAULTS)

    for key, value in (data or {}).items():
        if key in ("comment", "_readme"):
            continue

        if key not in DEFAULTS:
            raise RecolorError(f"{where}: unknown setting {key!r} (known: {', '.join(DEFAULTS)})")

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RecolorError(f"{where}.{key}: must be a number")

        out[key] = float(value) if isinstance(DEFAULTS[key], float) else int(value)

    if not 0 < out["gamma_min"] <= out["gamma_max"]:
        raise RecolorError(f"{where}: needs 0 < gamma_min <= gamma_max")

    if not 0 <= out["hue_full_within"] < out["hue_none_beyond"] <= 180:
        raise RecolorError(f"{where}: needs 0 <= hue_full_within < hue_none_beyond <= 180")

    if not out["chroma_floor"] > 0:
        raise RecolorError(f"{where}.chroma_floor: must be more than 0")

    if not 0 <= out["chroma_full_within"] < out["chroma_none_beyond"]:
        raise RecolorError(f"{where}: needs 0 <= chroma_full_within < chroma_none_beyond")

    if not 0 <= out["stats_lightness_min"] < out["stats_lightness_max"] <= 1:
        raise RecolorError(f"{where}: needs 0 <= stats_lightness_min < stats_lightness_max <= 1")

    if not 0 <= out["stats_alpha_min"] <= 255:
        raise RecolorError(f"{where}.stats_alpha_min: must be 0-255")

    return out
