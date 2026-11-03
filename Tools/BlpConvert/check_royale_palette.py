#!/usr/bin/env python3
"""Checks the Bleakhold Royale palette for colour-vision deficiencies (the Royale UX spec, section 1.3).

Usage: python3 -I check_royale_palette.py [--quiet]

For every pair of colours the HUD tells apart (the spec's table "Colour is never the only signal", plus the storm
over water and the storm edge over grass), this prints the CIEDE2000 colour difference for normal vision and for
protanopia, deuteranopia and tritanopia, simulated with the matrices of Machado, Oliveira and Fernandes (2009) at
severity 1.0, applied in linear sRGB. It fails (exit 1) when a pair marked colour-only (no shape, text or sound sets
the two apart) drops below dE 10 for any of the four; none is colour-only today, and this check keeps it so: mark a
new pair colour-only only after making sure it survives the simulation, or give it a second signal.

Standard library only. The palette is the one of RoyaleStyle.lua (RS.C) and make_royale_hud_art.py.
"""

import argparse
import math
import sys

PALETTE = {
    "ironTop": "1E2127", "ironBottom": "121418",
    "bronzeHi": "F3DDA4", "bronze": "C9A25A", "bronzeLo": "7A5A2C", "bronzeDeep": "3B2A14",
    "parchment": "F2E8D0", "ash": "BDB4A0", "smoke": "8A8273", "gold": "E5C07B",
    "storm": "A66BE0", "stormLight": "D7B6FF", "stormDeep": "4B2A6E", "safe": "FFFFFF",
    "ember": "FF7A3D", "blood": "E5604F", "beast": "8FD14F",
    # the map's own colours the storm is drawn over (make_royale_art.py, MapForge's grass texture colour)
    "waterDeep": "1C5E8A", "waterShallow": "4FC1C9", "grass": "6CB04A",
}

# (a, b, what the pair means, what else tells them apart; None = colour only)
PAIRS = [
    ("gold", "parchment", "own pin / pending pin", "banner-flag pin vs hollow pin; the place name"),
    ("storm", "safe", "storm edge / next circle", "solid line with a dark outline vs dashed line"),
    ("stormDeep", "waterDeep", "storm shade / deep water", "sparse diagonal hatch on the shade"),
    ("storm", "waterDeep", "storm edge / deep water", "the edge's dark outline; the hatch beside it"),
    ("storm", "waterShallow", "storm edge / shallow water", "the edge's dark outline"),
    ("storm", "grass", "storm edge / grass", "the edge's dark outline"),
    ("beast", "gold", "boss / supply and hoard", "horned skull vs crate-with-chute vs heaped chest"),
    ("beast", "ember", "boss / danger", "horned skull icon; danger is numerals and text"),
    ("ember", "gold", "last 3 s / earlier numerals", "bigger numerals, a second shock ring, the hammer sound"),
    ("ember", "bronzeHi", "lit notch, last 3 s / before", "the countdown's numerals and sound"),
    ("ember", "parchment", "in-storm damage / plain value", "storm icon and IN THE STORM in the tab"),
    ("gold", "ash", "own feed line / others", "the bar at the strip's right edge"),
    ("blood", "storm", "lobby ring / storm edge", "the lobby icon and its label"),
    ("safe", "parchment", "next circle / labels", "dashed ring vs text"),
]

# Machado, Oliveira, Fernandes 2009, "A physiologically-based model for simulation of color vision deficiency",
# severity 1.0 (linear RGB).
MACHADO = {
    "protan": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}
MIN_DE = 10.0


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
    c = min(1.0, max(0.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def simulate(rgb, kind):
    if kind == "normal":
        return rgb
    lin = [srgb_to_linear(c) for c in rgb]
    m = MACHADO[kind]
    out = [sum(m[r][k] * lin[k] for k in range(3)) for r in range(3)]
    return tuple(linear_to_srgb(c) for c in out)


def to_lab(rgb):
    """sRGB (0..1) -> CIE L*a*b* (D65)."""
    r, g, b = (srgb_to_linear(c) for c in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / 1.0
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def de2000(lab1, lab2):
    """CIEDE2000 colour difference (Sharma, Wu, Dalal 2005), kL = kC = kH = 1."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cm ** 7 / (Cm ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if C1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if C2p else 0.0
    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))
    Lpm = (L1 + L2) / 2
    Cpm = (C1p + C2p) / 2
    if C1p * C2p == 0:
        hpm = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hpm = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hpm = (h1p + h2p + 360) / 2
    else:
        hpm = (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hpm - 30)) + 0.24 * math.cos(math.radians(2 * hpm))
         + 0.32 * math.cos(math.radians(3 * hpm + 6)) - 0.20 * math.cos(math.radians(4 * hpm - 63)))
    dtheta = 30 * math.exp(-((hpm - 275) / 25) ** 2)
    Rc = 2 * math.sqrt(Cpm ** 7 / (Cpm ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lpm - 50) ** 2 / math.sqrt(20 + (Lpm - 50) ** 2)
    Sc = 1 + 0.045 * Cpm
    Sh = 1 + 0.015 * Cpm * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def selftest():
    """A few of Sharma's published CIEDE2000 test pairs, so a broken formula cannot pass silently."""
    cases = [((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
             ((50.0, 2.5, 0.0), (50.0, 0.0, -2.5), 4.3065),
             ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
             ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
             ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082)]
    for a, b, want in cases:
        got = de2000(a, b)
        if abs(got - want) > 1e-3:
            raise SystemExit("check_royale_palette: CIEDE2000 self-test failed (%r %r: %.4f, want %.4f)"
                             % (a, b, got, want))


def main():
    ap = argparse.ArgumentParser(description="Colour-vision check of the Royale palette.")
    ap.add_argument("--quiet", action="store_true", help="print only failures and the verdict")
    a = ap.parse_args()
    selftest()
    kinds = ("normal", "protan", "deutan", "tritan")
    failures = []
    if not a.quiet:
        print("%-28s %-18s %7s %7s %7s %7s   %s" % ("pair", "meaning", *kinds, "also told apart by"))
    for ca, cb, meaning, other in PAIRS:
        des = []
        for k in kinds:
            la = to_lab(simulate(hex_rgb(PALETTE[ca]), k))
            lb = to_lab(simulate(hex_rgb(PALETTE[cb]), k))
            des.append(de2000(la, lb))
        low = min(des)
        flag = ""
        if other is None and low < MIN_DE:
            failures.append("%s / %s (%s): dE %.1f < %.0f and nothing but colour tells them apart"
                            % (ca, cb, meaning, low, MIN_DE))
            flag = "  FAIL"
        elif low < MIN_DE:
            flag = "  (low; %s)" % ("redundant" if other else "")
        if not a.quiet:
            print("%-28s %-18s %7.1f %7.1f %7.1f %7.1f   %s%s" % (ca + " / " + cb, meaning[:18], *des,
                                                                 other or "COLOUR ONLY", flag))
    if failures:
        for f in failures:
            print("check_royale_palette: FAIL: " + f, file=sys.stderr)
        return 1
    print("check_royale_palette: ok (%d pairs; no colour-only pair under dE %.0f in normal, protan, deutan or "
          "tritan vision)" % (len(PAIRS), MIN_DE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
