#!/usr/bin/env python3
"""Generates specs/crucible_v1.json: the terrain of Bleakhold: Crucible of Onyxia (map 902).

    python3 -I Tools/MapForge/specs/crucible_gen.py

It needs numpy, unlike the rest of MapForge (standard library only). That is fine because the build never runs it:
the build and the tests read the committed crucible_v1.json. Run it on a developer machine after changing the layout,
and commit both files.

The spec is generated because its geometry is path-driven: a winding canyon, a causeway through lava, pools that
follow the road, props placed along both, and a moated nest. Writing those coordinates by hand is how the first
version came out as a flat field with a straight road. The output is deterministic (fixed seed), so a rebuild is
byte-identical.

The map, walked from the entrance (Y runs along the route; X is across it):

  1. The Fire-Cult Chasm (Y +383..+40): a raised plateau with a steep-walled, winding canyon cut into it (the
     'river' feature carves to an absolute bed with a short bank, so the walls stand at ~70 degrees). It starts in
     an entrance plaza, passes a pocket off the canyon (the gate to the Ragefire interior), and ends at a mouth.
  2. The Molten Basin (Y +40..-590): a lava basin. A raised basalt causeway winds through it; lava pools follow
     the road on both sides (ribbon polygons offset from its centre line; a lake floods its whole shape, so the
     dry road is the ground OUTSIDE them), with rock pillars standing in the lava (lake islands) and spires on
     the shore.
  3. The Dragon's Nest (Y -590..-900): a plateau ringed by a moat of lava, crossed at one gap by the causeway. A
     raised altar, rings of giant bones, a brazier circle, and at the south rim the gate to the Onyxia interior.

An enclosing volcanic range (the 'mountains' feature) walls the whole map.

Every model path below was used by a spec that was built and validated on the VPS (royale_v1 / royale_v2 / their
demo), so it exists in the client; the radii are the ones those specs used. Textures are likewise only ones from
those specs. Volcanic textures (lava crust, ash) are not among them: the client's tileset names still have to be
listed (Tools/MpqPack/list_client_files.py) before they can be used.
"""
import json
import math
import os
import random
import sys

import numpy as np

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crucible_v1.json")
rng = random.Random(20261105)
nrng = np.random.default_rng(20261105)

# --------------------------------------------------------------------------------------------- models (verified)
W = "World\\"
MODELS = {
    # fire and light
    "brazier": (W + "Expansion02\\Doodads\\Generic\\ScarletOnslaught\\ScarletO_Brazier_Lit.M2", 2, 0),
    "brazier_orc": (W + "GENERIC\\ORC\\PASSIVE DOODADS\\BRAZIERS\\OrcBrazier_CampFire01.m2", 3, 0),
    "brazier_dark": (W + "GENERIC\\Human\\Passive Doodads\\Braziers\\HumanBrazierCorrupt.m2", 2, 0),
    "torch": (W + "GENERIC\\PASSIVEDOODADS\\LIGHTS\\FreestandingTorch01.M2", 2, 0),
    "bonfire": (W + "Expansion02\\Doodads\\Generic\\Bonfire\\BonfireNorthrend_01.M2", 4, 0),
    "lowfire": (W + "GENERIC\\PVP\\Fires\\LowPolyFire.m2", 3, 0),
    # atmosphere (particle emitters; the specs lifted them by z_offset)
    "embers": (W + "LORDAERON\\STRATHOLME\\PASSIVEDOODADS\\FX\\StratholmeFloatingEmbers.m2", 6, 3),
    "smoke": (W + "LORDAERON\\STRATHOLME\\PASSIVEDOODADS\\FX\\StratholmeSmokeEmitter.m2", 6, 7),
    # bones and cult dressing
    "skullpikes": (W + "Expansion02\\Doodads\\Generic\\Scourge\\SC_SkullPikes_01.M2", 3, 0),
    "bonespike": (W + "LORDAERON\\PLAGUELAND\\PASSIVEDOODADS\\BoneSpikes\\BoneSpike_01.m2", 2, 0),
    "skulltiki": (W + "GENERIC\\TROLL\\PASSIVE DOODADS\\SkulTikis\\skulltiki.m2", 2, 0),
    "bones": (W + "AZEROTH\\ELWYNN\\PASSIVEDOODADS\\Skeleton\\BattleGladebonesHumanDark.m2", 2, 0),
    "massgrave": (W + "LORDAERON\\TIRISFALGLADE\\PASSIVEDOODADS\\Bodies\\MassGrave.m2", 5, 0),
    "clanbanner": (W + "GENERIC\\ORC\\PASSIVE DOODADS\\BANNERS\\ClanBanner01.m2", 2, 0),
    "scbanner": (W + "Expansion02\\Doodads\\Generic\\Scourge\\SC_Banner.M2", 2, 0),
    # ruins
    "archway": (W + "Expansion02\\Doodads\\ZulDrak\\TrollRuins\\ZulDrak_Archway_01.M2", 6, 0),
    "archway_broken": (W + "Expansion02\\Doodads\\ZulDrak\\TrollRuins\\ZulDrak_Archway_Broken_02.M2", 6, 0),
    "stoneface": (W + "Expansion02\\Doodads\\ZulDrak\\TrollRuins\\ZulDrak_StoneFace_01.M2", 5, 0),
    "wallrubble": (W + "Expansion02\\Doodads\\ZulDrak\\TrollRuins\\ZulDrak_WallRubble_01.M2", 3.5, 0),
    "ruin": (W + "Expansion02\\Doodads\\ZulDrak\\TrollRuins\\ZulDrak_Ruin_04.M2", 3.5, 0),
    "pillar": (W + "Expansion02\\Doodads\\Generic\\Titan\\TI_BrokenPillar.M2", 3, 0),
    # rock and dead wood
    "cliffrock": (W + "KALIMDOR\\Durotar\\PassiveDoodads\\Rocks\\DurotarCliffRock01.m2", 10, 0),
    "rock_a": (W + "KALIMDOR\\Durotar\\PassiveDoodads\\Rocks\\DurotarRock03.m2", 4, 0),
    "rock_b": (W + "KALIMDOR\\UNGORO\\PASSIVEDOODADS\\Rocks\\UngoroRock06.m2", 5, 0),
    "rock_c": (W + "KALIMDOR\\UNGORO\\PASSIVEDOODADS\\Rocks\\UngoroRock08.m2", 4, 0),
    "boulder": (W + "LORDAERON\\ALTERACMOUNTAINS\\PASSIVEDOODADS\\Rocks\\AlteracBoulder01.m2", 5, 0),
    "rock_d": (W + "LORDAERON\\PLAGUELAND\\PASSIVEDOODADS\\rocks\\PlaguelandRock01.m2", 5, 0),
    "deadtree_a": (W + "LORDAERON\\Arathi\\PassiveDoodads\\Trees\\ArathiTree_dead_001.m2", 10, 0),
    "deadtree_b": (W + "LORDAERON\\Arathi\\PassiveDoodads\\Trees\\ArathiTree_dead_002.m2", 10, 0),
    "stump": (W + "LORDAERON\\Arathi\\PassiveDoodads\\Trees\\ArathiStump01.m2", 3, 0),
}


def D(key, x, y, z=None, facing=None, scale=None, label=None):
    path, radius, z_off = MODELS[key]
    pos = [round(float(x), 1), round(float(y), 1)]
    if z is not None:
        pos.append(round(float(z), 1))
    item = {"model": path, "position": pos, "radius": radius}
    if z_off:
        item["z_offset"] = z_off
    if facing is not None:
        item["facing"] = round(float(facing) % 360.0, 1)
    if scale is not None and abs(scale - 1.0) > 1e-6:
        item["scale"] = round(float(scale), 2)
    if label:
        item["label"] = label
    return item


def model_entry(key, weight=1, scale=None, body=None, radius=None):
    path, r, z_off = MODELS[key]
    e = {"model": path, "weight": weight, "radius": radius if radius else r}
    if body is not None:
        e["body"] = body
    if scale is not None:
        e["scale"] = list(scale)
    if z_off:
        e["z_offset"] = z_off
    return e


# ------------------------------------------------------------------------------------------------ path geometry
def catmull(ctrl, per=16):
    P = np.array(ctrl, float)
    P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, per, endpoint=False):
            out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2])
    return np.array(out)


def resample(pts, step):
    seg = np.hypot(*np.diff(pts, axis=0).T)
    d = np.r_[0, np.cumsum(seg)]
    n = max(2, int(round(d[-1] / step)) + 1)
    s = np.linspace(0, d[-1], n)
    return np.c_[np.interp(s, d, pts[:, 0]), np.interp(s, d, pts[:, 1])], s


def frames(pts):
    t = np.gradient(pts, axis=0)
    t /= np.linalg.norm(t, axis=1)[:, None]
    n = np.c_[-t[:, 1], t[:, 0]]
    return t, n


def heading(t):
    """The server's facing for a direction (0 = +X, counter-clockwise toward +Y)."""
    return math.degrees(math.atan2(t[1], t[0])) % 360.0


def smooth_noise(n, lo, hi, every=4):
    knots = nrng.uniform(lo, hi, size=n // every + 3)
    return np.interp(np.arange(n), np.arange(len(knots)) * every, knots)


def inside(poly, x, y):
    P = np.asarray(poly)
    c = False
    j = len(P) - 1
    for i in range(len(P)):
        xi, yi = P[i]
        xj, yj = P[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            c = not c
        j = i
    return c


def pts2(a):
    return [[round(float(x), 1), round(float(y), 1)] for x, y in a]


# --------------------------------------------------------------------------------------------------- the routes
# Canyon: from the entrance plaza (Y 330) to the mouth (Y 46). Floor z 14, walls up to the plateau at z 44.
CANYON = catmull([(0, 304), (26, 272), (62, 238), (42, 200), (-14, 170), (-62, 140), (-50, 100), (2, 70), (34, 46)])
CANYON, CANYON_S = resample(CANYON, 14)
CT, CN = frames(CANYON)

# Causeway through the basin, from the canyon mouth to the nest gap.
CAUSE = catmull([(46, 14), (80, -46), (54, -120), (-22, -188), (-84, -266), (-80, -350), (-20, -424), (46, -490),
                 (52, -548), (22, -596), (0, -640)])
CAUSE, CAUSE_S = resample(CAUSE, 14)
MT, MN = frames(CAUSE)
M_LEN = CAUSE_S[-1]

# The two real dungeon interiors (Ragefire's LavaDungeon, Onyxia's KL_OnyxiasLair_B) are sealed models with no door to
# the outside, and each is far larger than the leg it belongs to (519x384x126 and 282x312x146 yards). Placed in the
# map they cannot be walked into, and the part that is not buried shows through the ground; buried, they are
# invisible AND their footprints keep every scattered rock and bone out of the area above them (the canyon got 0 of
# 72 rocks, the nest 0 of 25). So they are left out of the surface map until the gates that lead to them (an
# areatrigger teleport to a start point inside, the standard way to enter a sealed interior) are designed in game.
INCLUDE_WMOS = False

NEST = (0.0, -715.0)     # centre of the dragon's nest
NEST_PLATEAU_R = 128.0
GAP = math.radians(9.5)  # the half-angle of the dry gap in the moat (the causeway comes through it)

# --------------------------------------------------------------------------------------------------- lava pools
LAKES = []
POOL_POLYS = []


def ribbon(pts, nrm, i0, i1, side, d_in, thick):
    idx = np.arange(i0, i1 + 1)
    t = (idx - i0) / max(1, (i1 - i0))
    env = np.sin(np.pi * t) ** 0.7
    # curvature: the offset toward the centre of curvature must stay inside the radius or the polygon folds
    ang = np.unwrap(np.arctan2(*np.gradient(pts, axis=0).T[::-1]))
    kappa = np.gradient(ang) / 14.0
    cap = np.where(side * np.sign(kappa) > 0, 0.72 / (np.abs(kappa) + 1e-9), 1e9)[idx]
    d_out = np.minimum(d_in + 6 + thick[idx] * env, np.maximum(cap, d_in + 7))
    inner = pts[idx] + side * nrm[idx] * d_in
    outer = pts[idx] + side * nrm[idx] * d_out[:, None]
    return np.vstack([inner, outer[::-1]]), idx, d_in, d_out


def add_pool(name, poly, islands):
    LAKES.append({"name": name, "liquid_type": 3, "level": -3, "shape": {"polygon": {"points": pts2(poly)}},
                  "depth": 14, "shelf": 38, "shore": 6, "freeboard": 1.2, "min_depth": 0.8,
                  "islands": [{"center": [round(c[0], 1), round(c[1], 1)], "radius": round(r, 1),
                               "height": round(h, 1)} for c, r, h in islands]})
    POOL_POLYS.append(poly)


n_m = len(CAUSE)
thick = smooth_noise(n_m, 30, 60, every=3)
pool_no = 0
for side, start in ((1, 3), (-1, 8)):
    i = start
    while i + 8 < n_m - 7:
        i1 = min(i + 9, n_m - 8)
        poly, idx, d_in, d_out = ribbon(CAUSE, MN, i, i1, side, 22.0, thick)
        mid = len(idx) // 2
        isl = []
        span = d_out[mid] - d_in
        if span > 34:
            c = CAUSE[idx[mid]] + side * MN[idx[mid]] * (d_in + span * rng.uniform(0.42, 0.62))
            isl.append(((c[0], c[1]), rng.uniform(7.5, 12.0), rng.uniform(7.0, 13.0)))
        if span > 46 and len(idx) > 6:
            c = CAUSE[idx[mid - 3]] + side * MN[idx[mid - 3]] * (d_in + span * rng.uniform(0.38, 0.55))
            isl.append(((c[0], c[1]), rng.uniform(5.5, 8.5), rng.uniform(5.0, 9.0)))
        pool_no += 1
        add_pool(f"lava_{'w' if side > 0 else 'e'}{pool_no:02d}", poly, isl)
        i += 11

# the moat around the nest: one C-shaped arc, open at the north where the causeway arrives
def moat(cx, cy, r_in, r_out, n=70):
    a0, a1 = GAP, 2 * math.pi - GAP
    angs = np.linspace(a0, a1, n)
    jo = smooth_noise(n, -9, 9, every=5)
    ji = smooth_noise(n, -6, 6, every=6)
    outer = [(cx + (r_out + jo[k]) * math.sin(a), cy + (r_out + jo[k]) * math.cos(a)) for k, a in enumerate(angs)]
    inner = [(cx + (r_in + ji[k]) * math.sin(a), cy + (r_in + ji[k]) * math.cos(a)) for k, a in enumerate(angs)]
    return np.array(outer + inner[::-1])


MOAT = moat(NEST[0], NEST[1], 146.0, 190.0)
add_pool("lava_moat", MOAT, [])

# --------------------------------------------------------------------------------------------------- the heightmap
F = []   # features, in order


def flat(shape, h, falloff, mode="set"):
    F.append({"type": "flatten", "shape": shape, "height": h, "falloff": falloff, "mode": mode})


def circle(x, y, r):
    return {"circle": {"center": [round(x, 1), round(y, 1)], "radius": r}}


def rect(x0, y0, x1, y1):
    return {"rect": {"min": [x0, y0], "max": [x1, y1]}}


def ramp(a, b, width, falloff):
    F.append({"type": "ramp", "from": [round(a[0], 1), round(a[1], 1), a[2]],
              "to": [round(b[0], 1), round(b[1], 1), b[2]], "width": width, "falloff": falloff})


def hill(x, y, r, h, shape):
    F.append({"type": "hill", "center": [round(x, 1), round(y, 1)], "radius": round(r, 1), "height": round(h, 1),
              "shape": shape})


# 1. the chasm plateau, with a rolling top so it is not a table
flat(rect(-400, 40, 400, 420), 44, 15)
for _ in range(16):
    hill(rng.uniform(-340, 340), rng.uniform(70, 360), rng.uniform(55, 120), rng.uniform(-5, 6), "smooth")
# the entrance plaza and the canyon, cut down to z 14
flat(circle(0, 306, 54), 14, 11, "lower")
F.append({"type": "river", "path": pts2(CANYON[::2]), "width": 26, "bank": 11, "bed": 14})
# the pocket off the canyon: the gate to the Ragefire interior
RFC_I = int(np.searchsorted(CANYON_S, 150.0))
RFC_GATE = CANYON[RFC_I] + CN[RFC_I] * 48.0
flat(circle(RFC_GATE[0], RFC_GATE[1], 25), 14, 9, "lower")
# the mouth: down out of the canyon onto the basin floor
ramp((CANYON[-1][0], CANYON[-1][1] + 6, 14), (CAUSE[0][0], CAUSE[0][1] + 6, 7), 30, 11)

# 2. the causeway: a raised basalt road, gently undulating, through the lava
for k in range(0, n_m - 1, 2):
    k2 = min(k + 2, n_m - 1)
    z0 = 7 + 1.8 * math.sin(2 * math.pi * CAUSE_S[k] / 250.0)
    z1 = 7 + 1.8 * math.sin(2 * math.pi * CAUSE_S[k2] / 250.0)
    ramp((CAUSE[k][0], CAUSE[k][1], round(z0, 2)), (CAUSE[k2][0], CAUSE[k2][1], round(z1, 2)), 21, 6)
# rock spires on the shore, standing off the road and out of the lava
SPIRES = []
tries = 0
allv = np.vstack(POOL_POLYS[:-1])
while len(SPIRES) < 22 and tries < 4000:
    tries += 1
    x, y = rng.uniform(-345, 345), rng.uniform(-565, 25)
    if np.min(np.hypot(CAUSE[:, 0] - x, CAUSE[:, 1] - y)) < 90:
        continue
    if np.min(np.hypot(allv[:, 0] - x, allv[:, 1] - y)) < 48 or any(inside(p, x, y) for p in POOL_POLYS[:-1]):
        continue
    if any(math.hypot(x - sx, y - sy) < 70 for sx, sy, _ in SPIRES):
        continue
    SPIRES.append((x, y, rng.uniform(15, 27)))
for x, y, r in SPIRES:
    h = rng.uniform(22, 42)
    hill(x, y, r * 2.3, h * 0.28, "smooth")                       # a mound for the cluster to stand on
    hill(x, y, r, h, "cone")                                      # the main spire
    for _ in range(rng.choice((2, 3, 3, 4))):                     # satellites: a jagged group, not a cone
        a, d = rng.uniform(0, 2 * math.pi), r * rng.uniform(0.55, 1.15)
        hill(x + d * math.cos(a), y + d * math.sin(a), r * rng.uniform(0.45, 0.8), h * rng.uniform(0.35, 0.85), "cone")
# ridge chains: long, low, broken walls that run beside the route, so the basin reads as a caldera floor with the
# causeway winding between ridges, instead of a field
def far_from_lava(x, y, margin=44):
    return not any(inside(p, x, y) for p in POOL_POLYS[:-1]) and \
        np.min(np.hypot(allv[:, 0] - x, allv[:, 1] - y)) > margin


chains = 0
tries = 0
while chains < 11 and tries < 400:
    tries += 1
    k = rng.randrange(6, n_m - 10)
    side = rng.choice((-1, 1))
    off = rng.uniform(118, 190)
    x0, y0 = CAUSE[k] + MN[k] * side * off
    ang = math.atan2(MT[k][1], MT[k][0]) + rng.uniform(-0.35, 0.35)
    nodes = []
    x, y = x0, y0
    ok = True
    for j in range(rng.randint(4, 7)):
        if not (-352 < x < 352 and -565 < y < 15) or not far_from_lava(x, y) or \
                np.min(np.hypot(CAUSE[:, 0] - x, CAUSE[:, 1] - y)) < 100:
            ok = False
            break
        nodes.append((x, y))
        ang += rng.uniform(-0.3, 0.3)
        step = rng.uniform(32, 44)
        x += step * math.cos(ang)
        y += step * math.sin(ang)
    if not ok or len(nodes) < 3:
        continue
    chains += 1
    for j, (x, y) in enumerate(nodes):
        hill(x, y, rng.uniform(32, 48), rng.uniform(11, 21), "smooth")
        if rng.random() < 0.55:
            hill(x + rng.uniform(-10, 10), y + rng.uniform(-10, 10), rng.uniform(10, 17), rng.uniform(14, 28), "cone")

# 3. the dragon's nest: a plateau, a raised altar, the approach
flat(circle(NEST[0], NEST[1], NEST_PLATEAU_R), 13, 36)
flat(circle(NEST[0], NEST[1], 24), 16.5, 8)
ramp((CAUSE[-8][0], CAUSE[-8][1], 8), (0, NEST[1] + NEST_PLATEAU_R + 4, 13), 46, 22)
F.append({"type": "mountains", "width": 150, "height": [72, 152], "cliff": {"height": 58, "width": 14},
          "layers": 4, "peak_scale": 150, "saddles": 0.45, "ledges": {"step": 18, "flat": 0.4, "coverage": 0.5},
          "jitter": 36, "jitter_scale": 200, "corner_radius": 180, "seed": 41})
F.append({"type": "clamp", "min": -16, "max": 195})

# ---------------------------------------------------------------------------------------------------- the props
DOODADS = []

# --- the entrance plaza: a ring of fire, banners, and the face that watches the canyon
for k in range(10):
    a = 2 * math.pi * k / 10
    DOODADS.append(D("brazier" if k % 2 else "torch", 0 + 36 * math.cos(a), 306 + 36 * math.sin(a)))
for sx in (-1, 1):
    DOODADS.append(D("clanbanner", sx * 20, 340, facing=270, scale=1.6))
    DOODADS.append(D("skullpikes", sx * 30, 322, facing=rng.uniform(0, 360)))
DOODADS.append(D("stoneface", 0, 348, facing=270, scale=1.8, label="the watcher at the entrance"))

# --- the canyon: fire on both walls, banners, skulls, and three ruined arches across the way
s_arch = (60.0, 170.0, 262.0)
for k in range(2, len(CANYON) - 2):
    s = CANYON_S[k]
    side = 1 if k % 2 else -1
    base = CANYON[k] + CN[k] * side * 10.5
    if k % 2 == 0:
        DOODADS.append(D("brazier" if (k // 2) % 2 else "torch", base[0], base[1]))
    if k % 6 == 3:
        DOODADS.append(D("clanbanner", *(CANYON[k] - CN[k] * side * 11.2), facing=heading(CT[k]) + 90 * side,
                         scale=1.5))
    if k % 11 == 5:
        DOODADS.append(D("skullpikes", base[0], base[1], facing=rng.uniform(0, 360)))
    if k % 9 == 7:
        DOODADS.append(D("wallrubble", *(CANYON[k] + CN[k] * side * 9), facing=rng.uniform(0, 360),
                         scale=rng.uniform(0.9, 1.5)))
for s in s_arch:
    k = int(np.searchsorted(CANYON_S, s))
    DOODADS.append(D("archway", CANYON[k][0], CANYON[k][1], facing=heading(CT[k]) + 90, scale=1.9,
                     label=f"canyon arch {int(s)}"))
for k in (int(np.searchsorted(CANYON_S, 110.0)), int(np.searchsorted(CANYON_S, 215.0))):
    DOODADS.append(D("archway_broken", CANYON[k][0], CANYON[k][1], facing=heading(CT[k]) + 90, scale=1.7))

# --- the pocket off the canyon: the gate to the Ragefire interior
gx, gy = RFC_GATE
face = math.degrees(math.atan2(CANYON[RFC_I][1] - gy, CANYON[RFC_I][0] - gx))
DOODADS.append(D("archway", gx - 6 * math.cos(math.radians(face)), gy - 6 * math.sin(math.radians(face)),
                 facing=face + 90, scale=2.2, label="gate to the Ragefire interior"))
DOODADS.append(D("stoneface", gx - 15 * math.cos(math.radians(face)), gy - 15 * math.sin(math.radians(face)),
                 facing=face, scale=1.7))
for k in range(8):
    a = 2 * math.pi * k / 8
    DOODADS.append(D("brazier_orc" if k % 2 else "brazier", gx + 19 * math.cos(a), gy + 19 * math.sin(a)))
for k in range(5):
    a = rng.uniform(0, 2 * math.pi)
    DOODADS.append(D("skullpikes", gx + 12 * math.cos(a), gy + 12 * math.sin(a), facing=rng.uniform(0, 360)))

# --- the causeway: braziers staggered along both edges, banners, skull pikes, broken pillars
for k in range(3, n_m - 6):
    side = 1 if k % 2 else -1
    base = CAUSE[k] + MN[k] * side * 8.4
    if k % 2 == 0:
        DOODADS.append(D(("brazier", "brazier_dark", "torch")[(k // 2) % 3], base[0], base[1]))
    if k % 7 == 2:
        DOODADS.append(D("scbanner", *(CAUSE[k] - MN[k] * side * 8.6), facing=heading(MT[k]) + 90 * side, scale=1.7))
    if k % 9 == 5:
        DOODADS.append(D("skullpikes", base[0], base[1], facing=rng.uniform(0, 360)))
    if k % 13 == 8:
        DOODADS.append(D("pillar", *(CAUSE[k] + MN[k] * side * 9.4), facing=rng.uniform(0, 360),
                         scale=rng.uniform(1.0, 1.6)))
# the watcher in the lava: a great stone face on an island, with torches, halfway across
mid_pool = len(POOL_POLYS) // 4
isl_c = LAKES[mid_pool]["islands"][0]["center"] if LAKES[mid_pool]["islands"] else None
if isl_c:
    DOODADS.append(D("stoneface", isl_c[0], isl_c[1], facing=0, scale=2.6, label="the watcher in the lava"))
# every other island carries a fire so the pillars read from far away
for lk in LAKES[:-1]:
    for isl in lk["islands"]:
        if rng.random() < 0.6:
            DOODADS.append(D(rng.choice(("bonfire", "lowfire", "brazier_dark")), isl["center"][0],
                             isl["center"][1]))

# --- the lava itself: embers rising over every pool, smoke at a few shores
def lava_embers(poly, spacing, name):
    P = np.asarray(poly)
    x0, y0 = P.min(axis=0)
    x1, y1 = P.max(axis=0)
    out = []
    x = x0 + spacing / 2
    while x < x1:
        y = y0 + spacing / 2
        while y < y1:
            jx, jy = x + rng.uniform(-9, 9), y + rng.uniform(-9, 9)
            if inside(P, jx, jy):
                out.append(D("embers", jx, jy, z=-2.2))
            y += spacing
        x += spacing
    return out


for poly in POOL_POLYS:
    DOODADS += lava_embers(poly, 40, "pool")
for poly in POOL_POLYS[:-1]:
    P = np.asarray(poly)
    for _ in range(2):
        p = P[rng.randrange(len(P))]
        DOODADS.append(D("smoke", p[0], p[1], z=-1.5))

# --- the dragon's nest
cx, cy = NEST
for k in range(14):                                   # the brazier circle around the altar
    a = 2 * math.pi * k / 14
    DOODADS.append(D("brazier" if k % 2 else "brazier_orc", cx + 40 * math.cos(a), cy + 40 * math.sin(a)))
for k in range(4):                                    # broken pillars and fires at the altar's corners
    a = math.pi / 4 + k * math.pi / 2
    DOODADS.append(D("pillar", cx + 21 * math.cos(a), cy + 21 * math.sin(a), facing=rng.uniform(0, 360), scale=1.5))
    DOODADS.append(D("lowfire", cx + 14 * math.cos(a), cy + 14 * math.sin(a)))
for ring_r, count, lo, hi in ((78, 14, 4.5, 6.0), (106, 18, 5.5, 7.5)):   # giant ribs: bone spikes, scaled up
    for k in range(count):
        a = 2 * math.pi * k / count + rng.uniform(-0.08, 0.08)
        if abs(math.cos(a)) > 0.80 and math.sin(a) > 0:   # leave the approach (toward +Y) clear
            continue
        DOODADS.append(D("bonespike", cx + ring_r * math.sin(a), cy + ring_r * math.cos(a), facing=rng.uniform(0, 360),
                         scale=rng.uniform(lo, hi)))
for _ in range(7):                                    # mass graves
    a, r = rng.uniform(0, 2 * math.pi), rng.uniform(45, 115)
    DOODADS.append(D("massgrave", cx + r * math.sin(a), cy + r * math.cos(a), facing=rng.uniform(0, 360),
                     scale=rng.uniform(1.0, 1.6)))
# the bridge into the nest: banners and skull pikes both sides
for k in range(6):
    yy = NEST[1] + NEST_PLATEAU_R + 8 + k * 20
    for sx in (-1, 1):
        DOODADS.append(D("clanbanner" if k % 2 else "scbanner", sx * 30, yy, facing=180 + 90 * sx, scale=2.0))
        if k % 2 == 0:
            DOODADS.append(D("skullpikes", sx * 24, yy + 8, facing=rng.uniform(0, 360)))
# the gate to the Onyxia interior, at the south rim of the nest
gy2 = cy - NEST_PLATEAU_R + 26
DOODADS.append(D("archway", cx, gy2, facing=0, scale=2.8, label="gate to the Onyxia interior"))
DOODADS.append(D("stoneface", cx, gy2 - 18, facing=0, scale=2.6))
for sx in (-1, 1):
    DOODADS.append(D("archway_broken", sx * 30, gy2 + 2, facing=0, scale=2.0))
    DOODADS.append(D("skulltiki", sx * 17, gy2 + 8, facing=0, scale=1.4))
    for k in range(3):
        DOODADS.append(D("brazier", sx * (13 + k * 11), gy2 + 22 + k * 4))

# --- scatter (random but seeded) -------------------------------------------------------------------------------
SCATTER = [
    {"_": "rocks across the lava basin, off the road, out of the lava", "name": "basin_rocks", "seed": 3,
     "density": 5.5, "min_spacing": 13, "shape": rect(-380, -590, 380, 36), "slope": {"max": 38},
     "clearance": {"roads": 16, "pois": 12, "placements": 5},
     "models": [model_entry("rock_a", 3, (0.9, 1.7)), model_entry("rock_b", 2, (1.0, 1.9)),
                model_entry("rock_c", 2, (0.9, 1.5)), model_entry("boulder", 1, (1.0, 2.1)),
                model_entry("rock_d", 1, (0.9, 1.7))]},
    {"_": "big outcrops, to break the skyline of the basin", "name": "basin_cliffrocks", "seed": 4, "density": 0.9,
     "min_spacing": 40, "shape": rect(-380, -590, 380, 36), "slope": {"max": 32},
     "clearance": {"roads": 26, "pois": 20, "placements": 10},
     "models": [model_entry("cliffrock", 1, (1.5, 3.0))]},
    {"_": "rubble and rock along the canyon floor edges", "name": "canyon_rocks", "seed": 5, "density": 34,
     "min_spacing": 5.5, "shape": {"polyline": {"points": pts2(CANYON[::2]), "width": 28}},
     "clearance": {"roads": 0.5, "pois": 6, "placements": 2.2},
     "models": [model_entry("rock_a", 3, (0.7, 1.3)), model_entry("rock_d", 2, (0.7, 1.2)),
                model_entry("wallrubble", 2, (0.8, 1.3))]},
    {"_": "scorched dead wood on the plateau top and the entrance terrace", "name": "plateau_deadwood", "seed": 6,
     "density": 0.6, "min_spacing": 34, "shape": rect(-370, 70, 370, 410), "slope": {"max": 22},
     "clearance": {"roads": 18, "pois": 16, "placements": 8},
     "models": [model_entry("deadtree_a", 2, (0.8, 1.15), body=2.5), model_entry("deadtree_b", 2, (0.8, 1.15),
                body=2.5), model_entry("stump", 2, (0.9, 1.4), body=1.2), model_entry("rock_b", 1, (1.0, 2.0))]},
    {"_": "bones and rubble across the nest", "name": "nest_bones", "seed": 7, "density": 6.5, "min_spacing": 8,
     "shape": circle(NEST[0], NEST[1], 122), "clearance": {"roads": 9, "pois": 12, "placements": 3.5},
     "models": [model_entry("bones", 4, (0.9, 1.4)), model_entry("rock_a", 2, (0.9, 1.8)),
                model_entry("rock_d", 1, (1.0, 2.0)), model_entry("bonespike", 1, (1.2, 2.4))]},
    {"_": "embers drifting over every stretch of dry ground", "name": "ember_land", "seed": 8, "density": 0.8,
     "min_spacing": 34, "shape": rect(-380, -905, 380, 380), "slope": {"max": 50},
     "clearance": {"placements": 3},
     "models": [model_entry("embers", 1)]},
]

# ------------------------------------------------------------------------------------------------- textures, roads
TEXTURES = [
    {"name": "rock", "path": "TILESET\\AraithiHighlands\\ArathiHighlandsRockBase.blp", "color": "#4d4a46"},
    {"name": "reddirt", "path": "TILESET\\Durotar\\DurotarIDirt03.blp", "color": "#70402b"},
    {"name": "darkrock", "path": "TILESET\\Stranglethorn\\StrangleThornRock05.blp", "color": "#2b2521"},
    {"name": "flagstone", "path": "TILESET\\EXPANSION02\\ZULDRAK\\ZD_FlagstonesA.blp", "color": "#6a6258"},
]
RULES = [
    {"_": "scorched red earth in broad patches across the flats (the base is grey volcanic rock)",
     "texture": "reddirt", "noise": {"scale": 70, "threshold": 0.05, "fade": 0.28, "seed": 9}, "strength": 0.85,
     "slope": {"min": 0, "max": 22}},
    {"_": "dark rock on steep faces: canyon walls, mountain faces, spires, the plateau cliff", "texture": "darkrock",
     "slope": {"min": 24, "max": 42}, "strength": 1.0},
    {"_": "cooled basalt right at the lava: the lowest ground", "texture": "darkrock",
     "height": {"min": -20, "max": 3.5, "fade": 3}, "strength": 0.9},
    {"_": "flagstones in the entrance plaza, the two gates and the altar", "texture": "flagstone", "fade": 6,
     "strength": 0.95, "shape": circle(0, 306, 50)},
    {"texture": "flagstone", "fade": 5, "strength": 0.95, "shape": circle(float(RFC_GATE[0]), float(RFC_GATE[1]), 21)},
    {"texture": "flagstone", "fade": 6, "strength": 0.95, "shape": circle(NEST[0], NEST[1], 30)},
    {"texture": "flagstone", "fade": 6, "strength": 0.9, "shape": circle(0, NEST[1] - NEST_PLATEAU_R + 26, 26)},
    {"_": "the roads paint their flagstone here", "roads": True},
]
ROADS = [
    {"name": "canyon_road", "points": pts2(CANYON[::3]), "width": 10, "fade": 3, "texture": "flagstone"},
    {"name": "causeway", "points": pts2(CAUSE[::2]), "width": 16, "fade": 4, "texture": "flagstone"},
    {"name": "nest_bridge", "points": [[0, round(float(CAUSE[-1][1]), 1)], [0, NEST[1] + 16]], "width": 16, "fade": 4,
     "texture": "flagstone"},
]

# ------------------------------------------------------------------------------------------------- wmos, pois, areas
WMOS = [
    {"_comment": ["Ragefire Chasm (client name: Orgrimmar Lava Dungeon). Real box from wmo_info.py: 519x384x126, 12",
                  "groups, ALL indoor: a sealed cave with no door to the outside. Buried so none of it can show through",
                  "the ground: its highest point (bbox z +59.4) is placed 25 yards below the deepest terrain (the lava",
                  "pool floors, ~-16). It is reached by a gate teleport, not by walking in (see crucible_gen.py)."],
     "model": "World\\wmo\\Dungeon\\KL_OrgrimmarLavaDungeon\\LavaDungeon.wmo", "position": [150, 240, -100],
     "facing": 270, "bounds": [[-102.956, -275.379, -66.191], [416.286, 108.501, 59.434]], "label": "RFC_INTERIOR"},
    {"_comment": ["Onyxia's Lair main hall (KL_OnyxiasLair_B). Real box: 282x312x146; group 0 is outdoor, the rest",
                  "indoor. Buried the same way (highest point bbox z +49.6 sits 25 yards under the terrain)."],
     "model": "World\\wmo\\Dungeon\\KL_OnyxiasLair\\KL_OnyxiasLair_B.wmo", "position": [-60, -560, -95],
     "facing": 0, "bounds": [[-63.246, -26.112, -96.475], [218.833, 286.464, 49.591]], "label": "ONY_INTERIOR"},
]
POIS = [
    {"name": "raid_entrance", "title": "Raid Entrance", "kind": "entrance", "position": [0, 322, 18], "facing": 270,
     "radius": 8, "weight": 1},
    {"name": "rfc_gate", "title": "Gate to the Ragefire Interior", "kind": "gate",
     "position": [round(float(RFC_GATE[0]), 1), round(float(RFC_GATE[1]), 1), 18], "facing": 0, "radius": 10,
     "weight": 1},
    {"name": "onyxia_gate", "title": "Gate to the Onyxia Interior", "kind": "gate",
     "position": [0, round(gy2, 1), 20], "facing": 180, "radius": 10, "weight": 1},
    {"name": "altar", "title": "The Altar", "kind": "altar", "position": [NEST[0], NEST[1], 20], "facing": 90,
     "radius": 24, "weight": 1},
]
AREAS = [
    {"_": "Dragon's Nest", "area_id": 5223, "shape": circle(NEST[0], NEST[1], 235)},
    {"_": "Molten Basin", "area_id": 5222, "shape": rect(-400, -600, 400, 40)},
    {"_": "Fire-Cult Chasm", "area_id": 5221, "shape": rect(-400, 40, 400, 400)},
]

SPEC = {
    "_comment": [
        "Bleakhold: Crucible of Onyxia (map 902). GENERATED by specs/crucible_gen.py: edit that, not this file.",
        "Axes (MapForge): a feature's [x, y] is world [X, Y]; tiles.x runs along world Y, tiles.y along X, so the",
        "block is X -533.33..533.33 by Y -1066.67..533.33; the route runs along Y from +345 to -905.",
        "Walked from the entrance: the Fire-Cult Chasm (a winding steep-walled canyon cut into a plateau), the Molten",
        "Basin (a causeway winding through lava, with pools that follow it, rock pillars in the lava and spires on the",
        "shore) and the Dragon's Nest (a plateau in a lava moat, an altar, giant bones, the gate to the Onyxia",
        "interior). A volcanic mountain range walls the map.",
        "The Ragefire and Onyxia interiors are real client models, sealed rooms with no door to the outside, so they",
        "are NOT placed in this surface map (INCLUDE_WMOS in the generator): the two gates (the pocket off the",
        "canyon, the south rim of the nest) are where an areatrigger teleport to them will go.",
        "Molten Core has no model: it is terrain on its own map, so its leg is the basin built here.",
    ],
    "format": "mapforge-terrain/1",
    "map": {"id": 902, "directory": "BleakholdCrucible", "tiles": {"x": [31, 33], "y": [31, 32]}},
    "seed": 20261105, "area_id": 5220, "uid_base": 320000,
    "areas": AREAS,
    "heightmap": {"base": 5,
                  "noise": [{"scale": 190, "amplitude": 7, "octaves": 4, "persistence": 0.52},
                            {"scale": 52, "amplitude": 2.6, "octaves": 3, "seed": 13},
                            {"scale": 17, "amplitude": 0.8, "octaves": 2, "seed": 31}],
                  "features": F},
    "lakes": LAKES,
    "textures": TEXTURES, "texture_rules": RULES, "roads": ROADS,
    "wmos": WMOS if INCLUDE_WMOS else [], "doodads": DOODADS, "scatter": SCATTER, "pois": POIS,
}


MAX_PROP_SLOPE = 36.0


def settle(spec_dict):
    """Build the height field (terrain only) and drop every unlabeled prop that would land on ground steeper than
    MAX_PROP_SLOPE degrees: a brazier on a cliff face looks tilted or half sunk. Particle emitters are exempt (they
    float on purpose). Labeled landmarks are never dropped silently: they are reported, so the layout is fixed."""
    import tempfile
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from terrain import build, coords
    from terrain.spec import load_spec

    bare = dict(spec_dict, doodads=[], scatter=[], wmos=[])
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "terrain_only.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bare, f)
        grid = build.Context(load_spec(path)).grid
    kept, dropped, labeled = [], 0, []
    for it in spec_dict["doodads"]:
        low = it["model"].lower()
        if "embers" in low or "smoke" in low:
            kept.append(it)
            continue
        x, y = it["position"][:2]
        r, c = coords.world_to_lattice(x, y)
        nz = grid.normal(int(round(r)), int(round(c)))[2]
        steep = math.degrees(math.acos(max(-1.0, min(1.0, nz)))) > MAX_PROP_SLOPE
        if steep and it.get("label"):
            labeled.append(it["label"])
        elif steep:
            dropped += 1
            continue
        kept.append(it)
    spec_dict["doodads"] = kept
    return dropped, labeled


def dump(o, indent=0, inline_depth=3):
    """JSON with one line per leaf-ish object, so a diff of a regenerated file stays readable."""
    pad = "  " * indent
    if isinstance(o, dict):
        flat_ = json.dumps(o, separators=(", ", ": "))
        if len(flat_) <= 150 and indent >= 1:
            return flat_
        items = [f'{pad}  {json.dumps(k)}: {dump(v, indent + 1)}' for k, v in o.items()]
        return "{\n" + ",\n".join(items) + f"\n{pad}}}"
    if isinstance(o, list):
        flat_ = json.dumps(o, separators=(", ", ": "))
        if len(flat_) <= 150 and indent >= 1:
            return flat_
        items = [f"{pad}  {dump(v, indent + 1)}" for v in o]
        return "[\n" + ",\n".join(items) + f"\n{pad}]"
    return json.dumps(o)


if __name__ == "__main__":
    dropped, steep_landmarks = settle(SPEC)
    text = dump(SPEC) + "\n"
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    if steep_landmarks:
        print("WARNING: labeled landmarks on steep ground (move them in the generator):", steep_landmarks)
    print(f"settled props: {dropped} dropped off cliff faces")
    print(f"wrote {OUT}: {len(SPEC['doodads'])} doodads, {len(LAKES)} lava bodies, {len(F)} terrain features, "
          f"{len(SCATTER)} scatter groups, causeway {M_LEN:.0f} yd, canyon {CANYON_S[-1]:.0f} yd")
