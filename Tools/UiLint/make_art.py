#!/usr/bin/env python3
# Generate the Bleakhold addon art (Interface/AddOns/Bleakhold/Art/*.tga) from vector shapes.
#
#   python3 -I Tools/UiLint/make_art.py [--out DIR] [--preview DIR]
#
# Everything is white with an alpha channel and tinted in game with SetVertexColor, so one file serves
# every colour of the palette. All files are power-of-two, 32-bit uncompressed TGA (image type 2,
# bottom-up rows), which the 3.3.5a client loads when no .blp of the same name exists
# (Engine/Source/Services/Texture.cpp, TextureCreate tries BLP, then TGA). The glyphs are the stroke
# icons of the Bleakhold UI designs (24x24 viewBox paths), rasterised with analytic anti-aliasing.
# --preview also writes PNG copies for a visual check.
import argparse
import math
import os
import re
import struct
import sys
import zlib

# ---------------------------------------------------------------------------------------------------
# SVG path subset: M L H V C S A Z (absolute and relative)
# ---------------------------------------------------------------------------------------------------
NUM_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


class PathReader:
    def __init__(self, d):
        self.d, self.i = d, 0

    def skip(self):
        while self.i < len(self.d) and self.d[self.i] in " ,\t\n":
            self.i += 1

    def peek_cmd(self):
        self.skip()
        if self.i < len(self.d) and self.d[self.i].isalpha():
            return self.d[self.i]
        return None

    def number(self):
        self.skip()
        m = NUM_RE.match(self.d, self.i)
        if not m:
            raise ValueError("number expected at %d in %r" % (self.i, self.d))
        self.i = m.end()
        return float(m.group(0))

    def flag(self):
        self.skip()
        c = self.d[self.i]
        if c not in "01":
            raise ValueError("flag expected at %d in %r" % (self.i, self.d))
        self.i += 1
        return c == "1"

    def more(self):
        self.skip()
        return self.i < len(self.d) and not self.d[self.i].isalpha()


def arc_points(x1, y1, rx, ry, phi, fa, fs, x2, y2, steps=24):
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    phi = math.radians(phi)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p = cp * dx + sp * dy
    y1p = -sp * dx + cp * dy
    rx, ry = abs(rx), abs(ry)
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if fa == fs:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    pts = []
    n = max(4, int(steps * abs(dt) / (2 * math.pi)) + 2)
    for k in range(1, n + 1):
        t = t1 + dt * k / n
        x = cx + rx * math.cos(t) * cp - ry * math.sin(t) * sp
        y = cy + rx * math.cos(t) * sp + ry * math.sin(t) * cp
        pts.append((x, y))
    return pts


def cubic_points(p0, p1, p2, p3, steps=16):
    pts = []
    for k in range(1, steps + 1):
        t = k / steps
        u = 1 - t
        x = u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0]
        y = u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]
        pts.append((x, y))
    return pts


def parse_path(d):
    r = PathReader(d)
    polys, cur = [], None
    x = y = sx = sy = 0.0
    last_ctrl = None
    cmd = None
    while True:
        c = r.peek_cmd()
        if c:
            cmd = c
            r.i += 1
        elif not r.more():
            break
        rel = cmd.islower()
        C = cmd.upper()
        if C == "Z":
            if cur is not None:
                cur.append((sx, sy))
            x, y = sx, sy
            cur = None
            last_ctrl = None
            continue
        if C == "M":
            nx, ny = r.number(), r.number()
            if rel:
                nx, ny = x + nx, y + ny
            x, y, sx, sy = nx, ny, nx, ny
            cur = [(x, y)]
            polys.append(cur)
            cmd = "l" if rel else "L"
            last_ctrl = None
            continue
        if cur is None:
            cur = [(x, y)]
            polys.append(cur)
        if C == "L":
            nx, ny = r.number(), r.number()
            if rel:
                nx, ny = x + nx, y + ny
            x, y = nx, ny
            cur.append((x, y))
            last_ctrl = None
        elif C == "H":
            nx = r.number()
            x = x + nx if rel else nx
            cur.append((x, y))
            last_ctrl = None
        elif C == "V":
            ny = r.number()
            y = y + ny if rel else ny
            cur.append((x, y))
            last_ctrl = None
        elif C in "CS":
            if C == "C":
                c1 = (r.number(), r.number())
                if rel:
                    c1 = (x + c1[0], y + c1[1])
            else:
                c1 = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1]) if last_ctrl else (x, y)
            c2 = (r.number(), r.number())
            e = (r.number(), r.number())
            if rel:
                c2 = (x + c2[0], y + c2[1])
                e = (x + e[0], y + e[1])
            cur.extend(cubic_points((x, y), c1, c2, e))
            last_ctrl = c2
            x, y = e
        elif C == "A":
            rx, ry, phi = r.number(), r.number(), r.number()
            fa, fs = r.flag(), r.flag()
            nx, ny = r.number(), r.number()
            if rel:
                nx, ny = x + nx, y + ny
            cur.extend(arc_points(x, y, rx, ry, phi, fa, fs, nx, ny))
            x, y = nx, ny
            last_ctrl = None
        else:
            raise ValueError("unsupported command %s in %r" % (cmd, d))
    return polys


def circle_path(cx, cy, rr):
    return "M%g %ga%g %g 0 1 0 %g 0a%g %g 0 1 0 %g 0" % (cx - rr, cy, rr, rr, 2 * rr, rr, rr, -2 * rr)


# ---------------------------------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------------------------------
class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.a = [0.0] * (w * h)

    def put(self, x, y, v):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = y * self.w + x
            if v > self.a[i]:
                self.a[i] = v

    def stroke(self, polys, scale, ox, oy, width):
        hw = width / 2.0
        for poly in polys:
            pts = [(ox + px * scale, oy + py * scale) for px, py in poly]
            if len(pts) == 1:
                pts = pts * 2
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                self.segment(ax, ay, bx, by, hw)

    def segment(self, ax, ay, bx, by, hw):
        x0 = int(math.floor(min(ax, bx) - hw - 1))
        x1 = int(math.ceil(max(ax, bx) + hw + 1))
        y0 = int(math.floor(min(ay, by) - hw - 1))
        y1 = int(math.ceil(max(ay, by) + hw + 1))
        dx, dy = bx - ax, by - ay
        ll = dx * dx + dy * dy
        for py in range(max(0, y0), min(self.h, y1 + 1)):
            cy = py + 0.5
            for px in range(max(0, x0), min(self.w, x1 + 1)):
                cx = px + 0.5
                if ll > 0:
                    t = ((cx - ax) * dx + (cy - ay) * dy) / ll
                    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
                else:
                    t = 0.0
                qx, qy = ax + t * dx - cx, ay + t * dy - cy
                d = math.sqrt(qx * qx + qy * qy)
                v = hw - d + 0.5
                if v > 0:
                    self.put(px, py, 1.0 if v > 1 else v)

    def disc(self, cx, cy, rr):
        for py in range(self.h):
            for px in range(self.w):
                d = math.hypot(px + 0.5 - cx, py + 0.5 - cy)
                v = rr - d + 0.5
                if v > 0:
                    self.put(px, py, 1.0 if v > 1 else v)

    def ring(self, cx, cy, rr, width):
        for py in range(self.h):
            for px in range(self.w):
                d = abs(math.hypot(px + 0.5 - cx, py + 0.5 - cy) - (rr - width / 2.0))
                v = width / 2.0 - d + 0.5
                if v > 0:
                    self.put(px, py, 1.0 if v > 1 else v)

    def rect(self, x0, y0, x1, y1):
        for py in range(max(0, y0), min(self.h, y1)):
            for px in range(max(0, x0), min(self.w, x1)):
                self.put(px, py, 1.0)

    def tga(self):
        # 32-bit BGRA, bottom-up rows, 8 alpha bits (descriptor 0x08)
        head = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, self.w, self.h, 32, 8)
        rows = []
        for y in range(self.h - 1, -1, -1):
            row = bytearray()
            for x in range(self.w):
                a = int(round(self.a[y * self.w + x] * 255))
                row += bytes((255, 255, 255, a))
            rows.append(bytes(row))
        return head + b"".join(rows)

    def png(self, bg=(21, 24, 29), fg=(229, 192, 123)):
        raw = bytearray()
        for y in range(self.h):
            raw.append(0)
            for x in range(self.w):
                a = self.a[y * self.w + x]
                raw += bytes(int(bg[i] + (fg[i] - bg[i]) * a) for i in range(3))

        def chunk(t, data):
            return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)

        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------------------------------
# Glyph atlas: 512x256, 8 columns x 4 rows of 64x64 cells. Order = cell index (0-based, row-major);
# Widgets.lua has the same list.
GLYPHS = [
    ("star", "M12 2l3 6 6 .9-4.5 4.2 1 6.4L12 16.6 6.5 19.5l1-6.4L3 8.9 9 8z"),
    ("layers", "M4 7l8-4 8 4-8 4zM4 12l8 4 8-4M4 17l8 4 8-4"),
    ("banner", "M5 21V4h11l-2 4 2 4H5"),
    ("trophy", "M8 21h8M12 17v4M7 4h10v5a5 5 0 01-10 0zM7 6H4v2a3 3 0 003 3M17 6h3v2a3 3 0 01-3 3"),
    ("dungeon", "M4 20V9l8-5 8 5v11M9 20v-6h6v6"),
    ("key", "M8 16a4 4 0 110-8 4 4 0 010 8zM12 12h9M18 12v3M21 12v2"),
    ("rift", "M12 4a8 8 0 100 16 8 8 0 000-16zM12 9a3 3 0 100 6 3 3 0 000-6z"),
    ("tasks", "M9 11l3 3 8-8M20 12v7a1 1 0 01-1 1H5a1 1 0 01-1-1V5a1 1 0 011-1h11"),
    ("check", "M5 12l5 5L19 7"),
    ("clock", circle_path(12, 12, 9) + "M12 7v5l3 2"),
    ("close", "M6 6l12 12M18 6L6 18"),
    ("flame", "M12 3c3 3 5 6 5 9a5 5 0 01-10 0c0-3 2-6 5-9zM12 13c1 1 1.5 2 1.5 3a1.5 1.5 0 01-3 0c0-1 .5-2 1.5-3z"),
    ("shield", "M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6z"),
    ("reward", circle_path(12, 12, 8) + "M12 8v8M8 12h8"),
    ("search", circle_path(11, 11, 7) + "M20 20l-3.5-3.5"),
    ("legacy", "M12 3l2.5 5 5.5.8-4 3.9.9 5.5L12 15.6 7.1 18.2 8 12.7 4 8.8l5.5-.8z"),
    ("shirt", "M6 4l6 3 6-3 2 6-3 1v9H7v-9L4 10z"),
    ("mount", "M4 16c2-6 6-9 10-9l3-3 1 4 2 1-2 2v5H6z"),
    ("skull", "M12 3a7 7 0 00-7 7v4l2 2v3h10v-3l2-2v-4a7 7 0 00-7-7zM9.5 11h.01M14.5 11h.01M10 19v-2M14 19v-2"),
    ("left", "M15 5l-7 7 7 7"),
    ("right", "M9 5l7 7-7 7"),
    ("group", "M9 11a3 3 0 100-6 3 3 0 000 6zM3 20c0-3 3-5 6-5s6 2 6 5M16 11a3 3 0 100-6M21 20c0-3-2-4.5-4-5"),
    ("solo", "M12 11a4 4 0 100-8 4 4 0 000 8zM5 21c0-4 3-6 7-6s7 2 7 6"),
    ("hourglass", "M7 3h10M7 21h10M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9s8 4 8 9"),
    ("chest", "M4 11h16v9H4zM4 11c0-4 3-6 8-6s8 2 8 6M12 13v3"),
    ("sword", "M14 4h6v6l-9 9-3-3zM5 16l3 3M4 20l2-2"),
    ("dot", circle_path(12, 12, 3)),
    ("down", "M5 9l7 7 7-7"),
    ("up", "M5 15l7-7 7 7"),
    ("info", circle_path(12, 12, 9) + "M12 11v6M12 7.5h.01"),
    ("bounty", "M12 3v4M12 17v4M3 12h4M17 12h4" + circle_path(12, 12, 5)),
    ("shards", "M12 3l4 6-4 12-4-12zM8 9h8"),
]

DIGITS = [
    "M12 4C5 4 4 14 4 20s1 16 8 16 8-10 8-16-1-16-8-16z",
    "M8 9l5-5v32M8 36h10",
    "M5 10c1-5 4-6 7-6 4 0 7 3 7 7 0 6-6 10-14 25h15",
    "M5 8c2-3 4-4 7-4 4 0 7 2.5 7 6.5 0 4.5-4 8.5-9 8.5 6 0 10 3 10 8.5S16 36 12 36c-4 0-6-1-8-4",
    "M16 36V4L4 26h17",
    "M19 4H7L6 18c2-1.5 4-2 6.5-2 4.5 0 7.5 3.5 7.5 9.5S16 36 11.5 36C8 36 6 35 4 33",
    "M18 6c-2-1.5-4-2-6-2C6 4 4 12 4 22c0 9 3 14 8 14s8-4 8-9c0-5.5-3.5-8.5-8-8.5-4 0-7 2.5-8 5.5",
    "M4 4h16L10 36",
    "M12 19c-5 0-7-3-7-7.5S8 4 12 4s7 3 7 7.5-2 7.5-7 7.5c-5.5 0-8 3.5-8 8.5s3.5 8.5 8 8.5 8-3.5 8-8.5-2.5-8.5-8-8.5z",
    "M20 16c-1 3-4 5.5-8 5.5-4.5 0-8-3-8-8.5C4 8 7 4 12 4c5 0 8 5 8 14 0 10-2 18-8 18-2 0-4-.5-6-2",
]


def make_glyphs():
    cols, rows, cell = 8, 4, 64
    cv = Canvas(cols * cell, rows * cell)
    for idx, (_, d) in enumerate(GLYPHS):
        cx, cy = (idx % cols) * cell, (idx // cols) * cell
        scale = cell / 24.0
        cv.stroke(parse_path(d), scale, cx, cy, 1.9 * scale)
    return cv


def make_digits():
    cell_w, h = 96, 256
    cv = Canvas(1024, h)
    for i, d in enumerate(DIGITS):
        scale = 4.0
        ox = i * cell_w
        oy = (h - 40 * scale) / 2.0
        cv.stroke(parse_path(d), scale, ox, oy, 3.4 * scale)
    return cv


def make_disc():
    cv = Canvas(64, 64)
    cv.disc(32, 32, 31)
    return cv


def make_ring():
    cv = Canvas(64, 64)
    cv.ring(32, 32, 31.5, 3.5)
    return cv


def make_dashed():
    cv = Canvas(64, 64)
    t = 3
    for start in range(2, 62, 10):
        end = min(start + 6, 62)
        cv.rect(start, 1, end, 1 + t)
        cv.rect(start, 63 - t, end, 63)
        cv.rect(1, start, 1 + t, end)
        cv.rect(63 - t, start, 63, end)
    return cv


def make_gradient():
    # vertical fade, opaque at the top: used for soft inner glows
    cv = Canvas(8, 64)
    for y in range(64):
        for x in range(8):
            cv.a[y * 8 + x] = (1.0 - y / 63.0) ** 2
    return cv


def make_white():
    cv = Canvas(8, 8)
    cv.a = [1.0] * 64
    return cv


ART = {
    "White": make_white,
    "Glyphs": make_glyphs,
    "Digits": make_digits,
    "Disc": make_disc,
    "Ring": make_ring,
    "Dashed": make_dashed,
    "Fade": make_gradient,
}


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.normpath(os.path.join(here, "..", "..", "Interface", "AddOns", "Bleakhold", "Art")))
    ap.add_argument("--preview")
    ap.add_argument("--list-glyphs", action="store_true")
    a = ap.parse_args()
    if a.list_glyphs:
        for i, (name, _) in enumerate(GLYPHS):
            print(i, name)
        return 0
    os.makedirs(a.out, exist_ok=True)
    if a.preview:
        os.makedirs(a.preview, exist_ok=True)
    for name, fn in ART.items():
        cv = fn()
        with open(os.path.join(a.out, name + ".tga"), "wb") as f:
            f.write(cv.tga())
        if a.preview:
            with open(os.path.join(a.preview, name + ".png"), "wb") as f:
                f.write(cv.png())
        print("wrote %s.tga %dx%d" % (name, cv.w, cv.h))
    return 0


if __name__ == "__main__":
    sys.exit(main())
