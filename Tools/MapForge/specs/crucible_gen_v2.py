#!/usr/bin/env python3
"""Generates specs/crucible_v2.json (+ crucible_v2_portals.json): Bleakhold: Crucible of Onyxia (map 902), v2.

    python3 -I Tools/MapForge/specs/crucible_gen_v2.py

Needs numpy (a developer tool, like crucible_gen.py; the build reads the committed JSON). Deterministic (fixed seed).

v1 was an outdoor lava field whose two "gates" led nowhere, dressed with props from all over the game (Zul'Drak troll
arches, Scarlet braziers, Scourge banners, Arathi trees) on non-volcanic ground. v2 is one raid route through four
parts, two outdoor and the three REAL dungeon interiors, joined by portals:

  1. Ragefire Canyon (outdoor, Y +340..+105): a narrow red-rock canyon cut into a high plateau, the Burning Blade's
     road into the mountain: torches every few yards, clan banners, three cult camps in wider clearings. It ends in
     a walled chamber at a lava shrine: the portal into Ragefire Chasm.
  2. Ragefire Chasm: the real interior (LavaDungeon.wmo), buried under the canyon. Its deep end has the portal out.
  3. The Molten Basin (outdoor, Y +60..-545): a caldera of ash and cooled lava under the face of Blackrock. A raised
     basalt causeway winds south between lava lakes (pillars standing in the lava, vents smoking at the shores),
     past three Dark Iron rune circles (Molten Core's runes) to the Gate of Blackrock: the huge Blackrock doors set
     into the cliff, statues pouring lava on both sides, and the portal into Molten Core.
  4. Molten Core (Blackrock_lower_guild.wmo, the map's own interior), buried under the Blackrock massif. From
     Ragnaros' lair a portal leads into
  5. Onyxia's Lair (KL_OnyxiasLair_B.wmo), buried under the canyon plateau, down to Onyxia's hall.

Every texture and model path below was read from the realm's own client archives (base/Data, every player has
them) with Tools/MpqPack/list_client_files.py on the VPS, or was used by a spec already built there.

The interiors are placed exactly as their own maps place them (rotation 0, which the client turns by 180 degrees:
local (x, y) -> world (-x, -y); checked against the three maps' entrance and boss coordinates, which all fall inside
the boxes only that way). So any coordinate of the original map (an entrance, a boss, a spawn) moves into this map
by adding the placement's offset: see INTERIORS and to_crucible().

Rules the layout keeps (and main() checks):
  - no liquid above any interior (the server would see a player in the cave as under the lake): every lava lake
    is in the basin, between the canyon's and the massif's interiors;
  - every interior's top is at least 20 yards under the lowest terrain above its box;
  - the route (plaza, canyon, causeway, platforms) never steeper than 30 degrees, and every lake keeps clear of it;
  - the canyon and the basin do not connect overland (the plateau walls are too steep to walk): only the portals
    lead on, in order.
"""
import json
import math
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "crucible_v2.json")
OUT_PORTALS = os.path.join(HERE, "crucible_v2_portals.json")
rng = random.Random(20261106)
nrng = np.random.default_rng(20261106)

# ---------------------------------------------------------------------------------------- map block and regions
# tiles x 31..34 run along world Y (533.33 .. -1600), tiles y 31..33 along world X (533.33 .. -1066.67). The third
# row (X -533..-1066) is solid Blackrock range: it only holds Molten Core's model origin, which its own map puts
# ~1000 yards from its rooms (MapForge keeps every placement's origin on the map's tiles).
X0, X1, Y0, Y1 = -1066.67, 533.33, -1600.0, 533.33
CANYON_FLOOR = 16.0
PLATEAU = 62.0
BASIN = 4.0
CAUSE_Z = 8.0
MASSIF = 150.0
LAVA_LEVEL = -2.0

# ------------------------------------------------------------------------------------------------ the interiors
# box: the WMO's MOHD box in model space (wdt_info.py / wmo_info.py on the VPS). offset: where the original map's
# origin lands in this map (new = old + offset). points: coordinates in the ORIGINAL map (areatrigger_teleport
# targets, creature spawns, boss script positions), each a floor a player stands on.
INTERIORS = {
    "rfc": {
        "model": "World\\wmo\\Dungeon\\KL_OrgrimmarLavaDungeon\\LavaDungeon.wmo", "map": 389,
        "box": [[-102.956, -275.379, -66.191], [416.286, 108.501, 59.434]],
        "offset": (-83.7, 228.5, -95.0), "entrance_facing": 4.39,
        "points": {"entrance": (3.8, -14.8, -17.8), "deep_end": (-385.1, 239.6, -4.8),
                   "deep_end_2": (-375.8, 256.3, -4.8)},
    },
    "mc": {
        "model": "World\\wmo\\Dungeon\\AZ_Blackrock\\Blackrock_lower_guild.wmo", "map": 409,
        "box": [[-1333.1, 271.3, -233.5], [-489.9, 1255.0, 72.9]],
        "offset": (-910.0, -335.0, -80.0), "entrance_facing": 3.142,
        "points": {"entrance": (1091.9, -467.0, -105.1), "ragnaros_lair": (848.933, -812.875, -229.601),
                   "ragnaros_lair_2": (830.964, -814.706, -228.973), "ragnaros": (838.308, -831.467, -232.185)},
    },
    "ony": {
        "model": "World\\wmo\\Dungeon\\KL_OnyxiasLair\\KL_OnyxiasLair_B.wmo", "map": 249,
        "box": [[-63.246, -26.112, -96.475], [218.833, 286.464, 49.591]],
        "offset": (368.8, 436.5, -95.0), "entrance_facing": 4.58,
        "points": {"entrance": (29.2, -71.3, -8.2), "onyxia": (-10.6, -219.4, -87.7)},
    },
}


def to_crucible(key, p):
    ox, oy, oz = INTERIORS[key]["offset"]
    return (round(p[0] + ox, 2), round(p[1] + oy, 2), round(p[2] + oz, 2))


def world_box(key):
    """The interior's box in this map's world coordinates (local (x, y) -> world (-x, -y), then the offset)."""
    (lx0, ly0, lz0), (lx1, ly1, lz1) = INTERIORS[key]["box"]
    ox, oy, oz = INTERIORS[key]["offset"]
    return (ox - lx1, ox - lx0, oy - ly1, oy - ly0, oz + lz0, oz + lz1)


# --------------------------------------------------------------------------------------------- models (verified)
W = "World\\"
BS = W + "AZEROTH\\BURNINGSTEPPES\\PASSIVEDOODADS\\"
BR = W + "KHAZMODAN\\BLACKROCK\\PASSIVEDOODADS\\"
DI = W + "GENERIC\\DARKIRONDWARF\\"
MODELS = {
    # Ragefire Canyon: the Burning Blade's orcish camp dressing on Durotar red rock (Ragefire is under Orgrimmar)
    "orc_brazier": (W + "GENERIC\\ORC\\PASSIVE DOODADS\\BRAZIERS\\OrcBrazier_CampFire01.m2", 3, 0),
    "torch": (W + "GENERIC\\PASSIVEDOODADS\\LIGHTS\\FreestandingTorch01.M2", 2, 0),
    "clanbanner": (W + "GENERIC\\ORC\\PASSIVE DOODADS\\BANNERS\\ClanBanner01.m2", 2, 0),
    "skulltiki": (W + "GENERIC\\TROLL\\PASSIVE DOODADS\\SkulTikis\\skulltiki.m2", 2, 0),
    "bonfire": (W + "Expansion02\\Doodads\\Generic\\Bonfire\\BonfireNorthrend_01.M2", 4, 0),
    "lowfire": (W + "GENERIC\\PVP\\Fires\\LowPolyFire.m2", 3, 0),
    "durotar_cliff": (W + "KALIMDOR\\Durotar\\PassiveDoodads\\Rocks\\DurotarCliffRock01.m2", 10, 0),
    "durotar_rock": (W + "KALIMDOR\\Durotar\\PassiveDoodads\\Rocks\\DurotarRock03.m2", 4, 0),
    # Burning Steppes: volcanic rock, lava pillars and shrines, vents
    "bs_cliff1": (BS + "CliffRocks\\BurningSteppsCliffRock01.m2", 10, 0),
    "bs_cliff2": (BS + "CliffRocks\\BurningSteppsCliffRock02.m2", 10, 0),
    "bs_cliff3": (BS + "CliffRocks\\BurningSteppsCliffRock03.m2", 10, 0),
    "bs_cliff4": (BS + "CliffRocks\\BurningSteppsCliffRock04.m2", 10, 0),
    "bs_boulder1": (BS + "Rocks\\BurningSteppesBoulders01.m2", 5, 0),
    "bs_boulder2": (BS + "Rocks\\BurningSteppesBoulders02.m2", 5, 0),
    "bs_boulder3": (BS + "Rocks\\BurningSteppesBoulders03.m2", 5, 0),
    "lavarock1": (BS + "Rocks\\LavaRock01.m2", 4, 0),
    "lavarock2": (BS + "Rocks\\LavaRock02.m2", 4, 0),
    "lavarock3": (BS + "Rocks\\LavaRock03.m2", 4, 0),
    "lavarock4": (BS + "Rocks\\LavaRock04.m2", 4, 0),
    "lavapillar1": (BS + "LavaPillar\\LavaPillar01.m2", 6, 0),
    "lavapillar2": (BS + "LavaPillar\\LavaPillar02.m2", 6, 0),
    "lavapillar3": (BS + "LavaPillar\\LavaPillar03.m2", 6, 0),
    "lavashrine": (BS + "LavaShrine\\LavaShrine01.m2", 6, 0),
    "lavashrine_sg": (BS + "LavaShrine\\SearingGorgeLavaShrine.m2", 6, 0),
    "vent_l": (BS + "VolcanicVents\\VolcanicVentLarge01.m2", 5, 0),
    "vent_m": (BS + "VolcanicVents\\VolcanicVentMed01.m2", 4, 0),
    "vent_s": (BS + "VolcanicVents\\VolcanicVentSmall01.m2", 3, 0),
    # Blackrock: the gate, lava flowing from statues, dragonkin nests, chains
    "br_doors": (BR + "Doors\\BlackRockHugeDoors.m2", 14, 0),
    "br_statueflow": (BR + "BlackrockLavaFlow\\BlackrockStatueLavaFlow.m2", 8, 0),
    "br_bubbles": (BR + "BlackrockLavaBubbles\\BlackrockStatueLavaBubbles.m2", 5, 0),
    "dk_nest1": (BR + "DragonKinNests\\DragonKinNest01.m2", 6, 0),
    "dk_nest2": (BR + "DragonKinNests\\DragonKinNest02.m2", 6, 0),
    "dk_clump": (BR + "DragonKinNests\\DragonKinNestclump01.m2", 8, 0),
    "golem_bust": (BR + "GolemParts\\CannonGolemBust.M2", 4, 0),
    "golem_arm": (BR + "GolemParts\\CannonGolemArm.m2", 3, 0),
    "golem_foot": (BR + "GolemParts\\CannonGolemFoot.m2", 3, 0),
    # Dark Iron: Molten Core's runes, the lights along the causeway, the fallen
    "rune_a": (DI + "Active Doodads\\Runes\\DarkIronDwarfRune_A.m2", 3, 0),
    "rune_b": (DI + "Active Doodads\\Runes\\DarkIronDwarfRune_B.m2", 3, 0),
    "rune_c": (DI + "Active Doodads\\Runes\\DarkIronDwarfRune_C.m2", 3, 0),
    "rune_e": (DI + "Active Doodads\\Runes\\DarkIronDwarfRune_E.m2", 3, 0),
    "rune_f": (DI + "Active Doodads\\Runes\\DarkIronDwarfRune_F.m2", 3, 0),
    "rune_g": (DI + "Active Doodads\\Runes\\DarkIronDwarfRune_G.m2", 3, 0),
    "di_light": (DI + "PASSIVE DOODADS\\Lights\\DarkIronLight01.M2", 2, 0),
    "di_light2": (DI + "PASSIVE DOODADS\\Lights\\DarkIronLight02.M2", 2, 0),
    "skel_lay1": (DI + "PASSIVE DOODADS\\Skeletons\\SkeletonLaying01.m2", 2, 0),
    "skel_lay2": (DI + "PASSIVE DOODADS\\Skeletons\\SkeletonLaying02.m2", 2, 0),
    "skel_sit": (DI + "PASSIVE DOODADS\\Skeletons\\SkeletonSitting01.m2", 2, 0),
    "di_corpse1": (DI + "PASSIVE DOODADS\\CORPSES\\DarkIronDwarfCorpse01.m2", 2, 0),
    "di_corpse2": (DI + "PASSIVE DOODADS\\CORPSES\\DarkIronDwarfCorpse02.m2", 2, 0),
    # Ironforge's forge steam, for the vents' smoke over the lava
    "lavasteam": (W + "KHAZMODAN\\IRONFORGE\\PASSIVEDOODADS\\LavaSteam\\LavaSteam.m2", 4, 0),
    # atmosphere (particle emitters, lifted by z_offset)
    "embers": (W + "LORDAERON\\STRATHOLME\\PASSIVEDOODADS\\FX\\StratholmeFloatingEmbers.m2", 6, 3),
    "smoke": (W + "LORDAERON\\STRATHOLME\\PASSIVEDOODADS\\FX\\StratholmeSmokeEmitter.m2", 6, 7),
}
# props meant to stand on or against a cliff, or to float: never dropped by settle() for the slope under them
SLOPE_EXEMPT = ("embers", "smoke", "lavasteam", "vent_", "br_statueflow", "br_doors")


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


def face_to(x, y, tx, ty):
    return math.degrees(math.atan2(ty - y, tx - x)) % 360.0


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


def at(path, s_arr, s):
    k = int(np.clip(np.searchsorted(s_arr, s), 0, len(path) - 1))
    return k


# --------------------------------------------------------------------------------------------------- the routes
# 1. Ragefire Canyon: from the entrance plaza (0, 340) to the shrine chamber (22, 140).
CANYON = catmull([(0, 330), (44, 302), (74, 266), (48, 232), (-22, 210), (-78, 184), (-64, 158), (-18, 144),
                  (22, 140)])
CANYON, CANYON_S = resample(CANYON, 12)
CT, CN = frames(CANYON)
PLAZA = (0.0, 344.0)
CHAMBER = (24.0, 136.0)
CAMPS_S = (95.0, 205.0, 300.0)        # three cult camps in wider clearings along the canyon

# 3. The Molten Basin: from the arrival ledge (0, 36) to the Gate of Blackrock (0, -505).
ARRIVAL = (0.0, 38.0)
GATE = (0.0, -506.0)
CAUSE = catmull([(0, 26), (34, -22), (66, -82), (40, -148), (-28, -196), (-82, -256), (-70, -326), (-12, -376),
                 (46, -424), (40, -468), (0, -494)])
CAUSE, CAUSE_S = resample(CAUSE, 12)
MT, MN = frames(CAUSE)
M_LEN = CAUSE_S[-1]
RUNES_S = (M_LEN * 0.22, M_LEN * 0.50, M_LEN * 0.78)   # the three rune circles on the causeway

# --------------------------------------------------------------------------------------------------- lava lakes
LAKES = []
POOL_POLYS = []


def ribbon(pts, nrm, i0, i1, side, d_in, thick):
    idx = np.arange(i0, i1 + 1)
    t = (idx - i0) / max(1, (i1 - i0))
    env = np.sin(np.pi * t) ** 0.7
    ang = np.unwrap(np.arctan2(*np.gradient(pts, axis=0).T[::-1]))
    kappa = np.gradient(ang) / 12.0
    cap = np.where(side * np.sign(kappa) > 0, 0.72 / (np.abs(kappa) + 1e-9), 1e9)[idx]
    d_out = np.minimum(d_in + 6 + thick[idx] * env, np.maximum(cap, d_in + 7))
    inner = pts[idx] + side * nrm[idx] * d_in
    outer = pts[idx] + side * nrm[idx] * d_out[:, None]
    return np.vstack([inner, outer[::-1]]), idx, d_in, d_out


def add_pool(name, poly, islands):
    LAKES.append({"name": name, "liquid_type": 3, "level": LAVA_LEVEL, "shape": {"polygon": {"points": pts2(poly)}},
                  "depth": 13, "shelf": 30, "shore": 6, "freeboard": 1.2, "min_depth": 0.8,
                  "islands": [{"center": [round(c[0], 1), round(c[1], 1)], "radius": round(r, 1),
                               "height": round(h, 1)} for c, r, h in islands]})
    POOL_POLYS.append(poly)


n_m = len(CAUSE)
thick = smooth_noise(n_m, 34, 70, every=3)
rune_idx = [at(CAUSE, CAUSE_S, s) for s in RUNES_S]
# pools on alternating sides, broken at the rune circles (each circle is a dry platform with lava on one side only)
segments = []
cuts = [3] + rune_idx + [n_m - 5]
for a, b in zip(cuts[:-1], cuts[1:]):
    a2, b2 = a + 2, b - 2          # a dry gap of two road steps either side of each rune platform
    if b2 - a2 >= 4:
        segments.append((a2, b2))
for si, (i0, i1) in enumerate(segments):
    for side in ((1, -1) if si % 2 == 0 else (-1, 1)):
        d_in = 20.0 if side == (1 if si % 2 == 0 else -1) else 26.0
        poly, idx, d_in, d_out = ribbon(CAUSE, MN, i0, i1, side, d_in, thick)
        mid = len(idx) // 2
        span = d_out[mid] - d_in
        isl = []
        if span > 32:
            c = CAUSE[idx[mid]] + side * MN[idx[mid]] * (d_in + span * rng.uniform(0.45, 0.6))
            isl.append(((c[0], c[1]), rng.uniform(7.0, 10.0), rng.uniform(6.0, 10.0)))
        add_pool(f"lava_{si}{'w' if side > 0 else 'e'}", poly, isl)

# --------------------------------------------------------------------------------------------------- the heightmap
F = []


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


# 1. the canyon plateau (over the Ragefire and Onyxia interiors), rolling on top, with the canyon cut into it
flat(rect(-540, 92, 540, 540), PLATEAU, 18)
for _ in range(14):
    hill(rng.uniform(-360, 360), rng.uniform(140, 380), rng.uniform(50, 110), rng.uniform(-4, 9), "smooth")
flat(circle(*PLAZA, 44), CANYON_FLOOR, 10, "lower")
F.append({"type": "river", "path": pts2(CANYON[::2]), "width": 22, "bank": 9, "bed": CANYON_FLOOR})
for s in CAMPS_S:
    k = at(CANYON, CANYON_S, s)
    flat(circle(CANYON[k][0], CANYON[k][1], 27), CANYON_FLOOR, 8, "lower")
flat(circle(*CHAMBER, 30), CANYON_FLOOR, 8, "lower")

# 2. the basin: a caldera floor under the plateau's south cliff and the massif's north face
# the rim first (a high ring all round), then the caldera floor carved into it: sealed whatever the border
# mountains do, and round, not a box
flat(rect(-545, -578, 545, 86), PLATEAU + 40, 10)
BASIN_C, BASIN_R = (0.0, -236.0), 300.0
_rj = smooth_noise(72, -26, 22, every=4)
BASIN_POLY = np.array([(BASIN_C[0] + (BASIN_R + _rj[k]) * math.cos(a) * 1.08,
                        BASIN_C[1] + (BASIN_R + _rj[k]) * math.sin(a))
                       for k, a in enumerate(np.linspace(0, 2 * math.pi, 72, endpoint=False))])
flat({"polygon": {"points": pts2(BASIN_POLY)}}, BASIN, 20)
for _ in range(18):
    hill(rng.uniform(-340, 340), rng.uniform(-520, 30), rng.uniform(40, 90), rng.uniform(-1.5, 3.0), "smooth")
flat(circle(*ARRIVAL, 24), CAUSE_Z + 1, 9)
for k in range(0, n_m - 1, 2):        # the causeway, gently rolling
    k2 = min(k + 2, n_m - 1)
    z0 = CAUSE_Z + 1.4 * math.sin(2 * math.pi * CAUSE_S[k] / 220.0)
    z1 = CAUSE_Z + 1.4 * math.sin(2 * math.pi * CAUSE_S[k2] / 220.0)
    ramp((CAUSE[k][0], CAUSE[k][1], round(z0, 2)), (CAUSE[k2][0], CAUSE[k2][1], round(z1, 2)), 19, 6)
for k in rune_idx:                    # the rune platforms
    flat(circle(CAUSE[k][0], CAUSE[k][1], 21), CAUSE_Z, 7)
flat(circle(*GATE, 40), CAUSE_Z, 10)
# rock spires on the shores, away from road and lava: the skyline of the caldera
allv = np.vstack(POOL_POLYS)
SPIRES = []
tries = 0
while len(SPIRES) < 10 and tries < 8000:
    tries += 1
    a = rng.uniform(0, 2 * math.pi)
    d = BASIN_R * rng.uniform(0.70, 0.86)
    x, y = BASIN_C[0] + d * math.cos(a) * 1.08, BASIN_C[1] + d * math.sin(a)
    if np.min(np.hypot(CAUSE[:, 0] - x, CAUSE[:, 1] - y)) < 110 or np.min(np.hypot(allv[:, 0] - x, allv[:, 1] - y)) < 45:
        continue
    if math.hypot(x - ARRIVAL[0], y - ARRIVAL[1]) < 120 or math.hypot(x - GATE[0], y - GATE[1]) < 120:
        continue
    if any(inside(p, x, y) for p in POOL_POLYS) or any(math.hypot(x - sx, y - sy) < 90 for sx, sy, _ in SPIRES):
        continue
    SPIRES.append((x, y, rng.uniform(14, 24)))
for x, y, r in SPIRES:
    h = rng.uniform(24, 46)
    hill(x, y, r * 2.2, h * 0.3, "smooth")
    hill(x, y, r, h, "cone")
    for _ in range(rng.choice((2, 3, 3))):
        a, d = rng.uniform(0, 2 * math.pi), r * rng.uniform(0.55, 1.1)
        hill(x + d * math.cos(a), y + d * math.sin(a), r * rng.uniform(0.45, 0.75), h * rng.uniform(0.4, 0.85), "cone")

# 3. the Blackrock massif (over Molten Core): a sheer north face behind the gate, a broken summit; and the
# Blackrock range filling the map's -X row, behind the canyon's and the basin's walls
flat(rect(-540, -1610, 540, -566), MASSIF, 12)
flat(rect(-1080, -1610, -545, 545), MASSIF - 20, 30)
for _ in range(16):
    hill(rng.uniform(-1000, -620), rng.uniform(-1500, 450), rng.uniform(70, 160), rng.uniform(-10, 45), "smooth")
for _ in range(22):
    hill(rng.uniform(-420, 420), rng.uniform(-1480, -640), rng.uniform(60, 150), rng.uniform(-10, 40), "smooth")
for _ in range(10):
    hill(rng.uniform(-380, 380), rng.uniform(-1400, -680), rng.uniform(25, 45), rng.uniform(30, 60), "cone")

F.append({"type": "mountains", "width": 150, "height": [80, 160], "cliff": {"height": 60, "width": 14},
          "layers": 4, "peak_scale": 150, "saddles": 0.4, "ledges": {"step": 18, "flat": 0.4, "coverage": 0.5},
          "jitter": 34, "jitter_scale": 200, "corner_radius": 180, "seed": 43})
F.append({"type": "clamp", "min": -15, "max": 245})

# ---------------------------------------------------------------------------------------------------- the props
DOODADS = []

# --- 1. Ragefire Canyon
# the entrance plaza: a ring of orc braziers, banners on the back wall, skull tikis at the canyon mouth
px, py = PLAZA
for k in range(10):
    a = 2 * math.pi * k / 10
    DOODADS.append(D("orc_brazier" if k % 2 else "torch", px + 34 * math.cos(a), py + 34 * math.sin(a)))
for sx in (-1, 1):
    DOODADS.append(D("clanbanner", px + sx * 18, py + 30, facing=270, scale=1.7))
    DOODADS.append(D("skulltiki", CANYON[1][0] + sx * 9, CANYON[1][1], facing=heading(CT[1]) + 180, scale=1.3))
DOODADS.append(D("bonfire", px, py + 4, label="entrance bonfire"))
# torches alternating along both walls, a banner every few yards: the road is lit and reads as one way
for k in range(2, len(CANYON) - 2):
    side = 1 if k % 2 else -1
    base = CANYON[k] + CN[k] * side * 9.5
    if k % 2 == 0:
        DOODADS.append(D("torch", base[0], base[1]))
    if k % 6 == 3:
        DOODADS.append(D("clanbanner", *(CANYON[k] - CN[k] * side * 10.0), facing=heading(CT[k]) + 90 * side,
                         scale=1.5))
    if k % 9 == 5:
        DOODADS.append(D("durotar_rock", *(CANYON[k] + CN[k] * side * 8.5), facing=rng.uniform(0, 360),
                         scale=rng.uniform(0.8, 1.3)))
# the three cult camps: a fire in the middle, braziers and banners around, skulls at the edge (a trash pull each)
for ci, s in enumerate(CAMPS_S):
    k = at(CANYON, CANYON_S, s)
    cx, cy = CANYON[k]
    DOODADS.append(D("bonfire", cx, cy, label=f"cult camp {ci + 1}"))
    for j in range(5):
        a = 2 * math.pi * j / 5 + 0.3
        DOODADS.append(D("orc_brazier", cx + 19 * math.cos(a), cy + 19 * math.sin(a)))
    for j in range(2):
        a = rng.uniform(0, 2 * math.pi)
        DOODADS.append(D("clanbanner", cx + 22 * math.cos(a), cy + 22 * math.sin(a), facing=face_to(
            cx + 22 * math.cos(a), cy + 22 * math.sin(a), cx, cy), scale=1.6))
        DOODADS.append(D("skulltiki", cx + 15 * math.cos(a + 1.4), cy + 15 * math.sin(a + 1.4),
                         facing=rng.uniform(0, 360)))
# the shrine chamber: a lava shrine at the back, braziers in a ring, vents smoking: the way into Ragefire
chx, chy = CHAMBER
back = math.atan2(chy - CANYON[-3][1], chx - CANYON[-3][0])
DOODADS.append(D("lavashrine", chx + 14 * math.cos(back), chy + 14 * math.sin(back),
                 facing=math.degrees(back) + 180, scale=1.6, label="the Ragefire shrine"))
for j in range(8):
    a = 2 * math.pi * j / 8
    DOODADS.append(D("orc_brazier" if j % 2 else "torch", chx + 22 * math.cos(a), chy + 22 * math.sin(a)))
for sgn in (-1, 1):
    a = back + sgn * 1.0
    DOODADS.append(D("vent_m", chx + 18 * math.cos(a), chy + 18 * math.sin(a)))
    DOODADS.append(D("smoke", chx + 18 * math.cos(a), chy + 18 * math.sin(a), z=CANYON_FLOOR))

# --- 3. The Molten Basin
ax, ay = ARRIVAL
for j in range(8):                     # the arrival ledge: a rune circle, the first sight of Blackrock
    a = 2 * math.pi * j / 8
    DOODADS.append(D(("rune_a", "rune_b", "rune_c", "rune_e")[j % 4], ax + 12 * math.cos(a), ay + 12 * math.sin(a),
                     facing=math.degrees(a) + 90))
for sgn in (-1, 1):
    DOODADS.append(D("di_light", ax + sgn * 20, ay - 6))
# Dark Iron lights in pairs along the causeway; golem wrecks and the fallen at its edge
for k in range(3, n_m - 4):
    if any(abs(k - r) < 3 for r in rune_idx):
        continue
    if k % 3 == 0:
        for sgn in (-1, 1):
            p = CAUSE[k] + MN[k] * sgn * 8.0
            DOODADS.append(D("di_light" if (k // 3) % 2 else "di_light2", p[0], p[1]))
    if k % 11 == 6:
        side = rng.choice((-1, 1))
        p = CAUSE[k] + MN[k] * side * 11.0
        DOODADS.append(D(rng.choice(("di_corpse1", "di_corpse2", "skel_lay1", "skel_lay2")), p[0], p[1],
                         facing=rng.uniform(0, 360)))
    if k % 17 == 9:
        side = rng.choice((-1, 1))
        p = CAUSE[k] + MN[k] * side * 12.5
        DOODADS.append(D(rng.choice(("golem_bust", "golem_arm", "golem_foot")), p[0], p[1], facing=rng.uniform(0, 360)))
# the three rune circles: Molten Core's runes on a round platform, lights at the four corners
for ri, k in enumerate(rune_idx):
    cx, cy = CAUSE[k]
    for j in range(8):
        a = 2 * math.pi * j / 8
        DOODADS.append(D(("rune_a", "rune_b", "rune_c", "rune_e", "rune_f", "rune_g")[(j + ri) % 6],
                         cx + 13 * math.cos(a), cy + 13 * math.sin(a), facing=math.degrees(a) + 90))
    for j in range(4):
        a = math.pi / 4 + j * math.pi / 2
        DOODADS.append(D("di_light", cx + 19 * math.cos(a), cy + 19 * math.sin(a)))
    DOODADS.append(D("lavashrine_sg", cx, cy, label=f"rune circle {ri + 1}"))
# the lava: pillars standing in it (on its islands), vents and steam at the shores, embers over every lake
for lk in LAKES:
    for isl in lk["islands"]:
        DOODADS.append(D(rng.choice(("lavapillar1", "lavapillar2", "lavapillar3")), isl["center"][0], isl["center"][1],
                         facing=rng.uniform(0, 360), scale=rng.uniform(1.2, 1.8)))


def lava_embers(poly, spacing):
    P = np.asarray(poly)
    x0, y0 = P.min(axis=0)
    x1, y1 = P.max(axis=0)
    out = []
    x = x0 + spacing / 2
    while x < x1:
        y = y0 + spacing / 2
        while y < y1:
            jx, jy = x + rng.uniform(-8, 8), y + rng.uniform(-8, 8)
            if inside(P, jx, jy):
                out.append(D("embers", jx, jy, z=LAVA_LEVEL - 0.2))
            y += spacing
        x += spacing
    return out


for poly in POOL_POLYS:
    DOODADS += lava_embers(poly, 42)
    P = np.asarray(poly)
    for _ in range(2):
        p = P[rng.randrange(len(P))]
        DOODADS.append(D("lavasteam", p[0], p[1], z=LAVA_LEVEL + 0.5))
# dragonkin nests under the plateau's south cliff: a first sign of Onyxia's brood
for j in range(5):
    x = rng.uniform(-300, 300)
    y = rng.uniform(32, 50)
    if abs(x - ARRIVAL[0]) < 60:
        continue
    DOODADS.append(D(rng.choice(("dk_nest1", "dk_nest2", "dk_clump")), x, y, facing=rng.uniform(0, 360),
                     scale=rng.uniform(1.0, 1.4)))
# the Gate of Blackrock: the huge doors set into the massif face, statues pouring lava on both sides
gx, gy = GATE
DOODADS.append(D("br_doors", gx, gy - 38, facing=90, label="the Gate of Blackrock"))
for sgn in (-1, 1):
    DOODADS.append(D("br_statueflow", gx + sgn * 30, gy - 32, facing=90, scale=1.2))
    DOODADS.append(D("br_bubbles", gx + sgn * 30, gy - 24))
    for j in range(3):
        DOODADS.append(D("di_light", gx + sgn * (12 + j * 9), gy + 6 + j * 8))
for j in range(6):
    a = math.pi + j * math.pi / 5
    DOODADS.append(D(("rune_a", "rune_c", "rune_e", "rune_f", "rune_g", "rune_b")[j], gx + 16 * math.cos(a),
                     gy + 6 + 16 * math.sin(a) * 0.6, facing=math.degrees(a) + 90))

# --- scatter (seeded) -----------------------------------------------------------------------------------------
SCATTER = [
    {"_": "red rock along the canyon floor's edges (the canyon is Durotar rock: Ragefire is under Orgrimmar)",
     "name": "canyon_rocks", "seed": 5, "density": 26, "min_spacing": 6,
     "shape": {"polyline": {"points": pts2(CANYON[::2]), "width": 24}},
     "clearance": {"roads": 0.0, "pois": 6, "placements": 2.5},
     "models": [model_entry("durotar_rock", 3, (0.6, 1.1)), model_entry("bs_boulder1", 1, (0.5, 0.9))]},
    {"_": "volcanic boulders and lava rock across the basin floor, off the road and out of the lava",
     "name": "basin_rocks", "seed": 3, "density": 4.5, "min_spacing": 14, "shape": {"polygon": {"points": pts2(BASIN_POLY)}},
     "slope": {"max": 36}, "clearance": {"roads": 15, "pois": 14, "placements": 6},
     "models": [model_entry("bs_boulder1", 2, (0.8, 1.5)), model_entry("bs_boulder2", 2, (0.8, 1.5)),
                model_entry("bs_boulder3", 1, (0.8, 1.4)), model_entry("lavarock1", 2, (0.9, 1.6)),
                model_entry("lavarock2", 2, (0.9, 1.6)), model_entry("lavarock3", 1, (0.9, 1.5)),
                model_entry("lavarock4", 1, (0.9, 1.5))]},
    {"_": "big Burning Steppes outcrops to break the caldera's skyline", "name": "basin_cliffrocks", "seed": 4,
     "density": 0.8, "min_spacing": 44, "shape": {"polygon": {"points": pts2(BASIN_POLY)}}, "slope": {"max": 32},
     "clearance": {"roads": 28, "pois": 24, "placements": 10},
     "models": [model_entry("bs_cliff1", 1, (1.2, 2.2)), model_entry("bs_cliff2", 1, (1.2, 2.2)),
                model_entry("bs_cliff3", 1, (1.2, 2.2)), model_entry("bs_cliff4", 1, (1.2, 2.2))]},
    {"_": "small vents smoking on the basin floor", "name": "basin_vents", "seed": 9, "density": 0.7,
     "min_spacing": 38, "shape": {"polygon": {"points": pts2(BASIN_POLY)}}, "slope": {"max": 20},
     "clearance": {"roads": 18, "pois": 16, "placements": 8},
     "models": [model_entry("vent_s", 2), model_entry("vent_m", 1)]},
    {"_": "embers drifting over all the dry ground", "name": "ember_land", "seed": 8, "density": 0.7,
     "min_spacing": 36, "shape": rect(-380, -540, 380, 360), "slope": {"max": 50}, "clearance": {"placements": 3},
     "models": [model_entry("embers", 1)]},
]

# ------------------------------------------------------------------------------------------------- textures, roads
TEXTURES = [
    {"name": "rock", "path": "TILESET\\BURNINGSTEPPS\\BurningSteppsRock02.blp", "color": "#3b3431"},
    {"name": "ash", "path": "TILESET\\BURNINGSTEPPS\\BurningSteppsAsh01.blp", "color": "#4c4641"},
    {"name": "lavarock", "path": "TILESET\\BURNINGSTEPPS\\BurningSteppsRockLava.blp", "color": "#6b2a14"},
    {"name": "road", "path": "TILESET\\BURNINGSTEPPS\\BurningSteppsSpireRoad01.blp", "color": "#5d5148"},
    {"name": "cliff", "path": "TILESET\\BURNINGSTEPPS\\BurningSteppsSpireRock02.blp", "color": "#2b2421"},
    {"name": "reddirt", "path": "TILESET\\Durotar\\DurotarIDirt03.blp", "color": "#70402b"},
    {"name": "charcoal", "path": "TILESET\\BURNINGSTEPPS\\BurningSteppsCharcoal01.blp", "color": "#211c1a"},
]
CANYON_BAND = {"polyline": {"points": pts2(CANYON[::2]), "width": 70}}
RULES = [
    {"_": "the canyon floor and its camps: Durotar red earth", "texture": "reddirt", "strength": 0.95, "fade": 6,
     "shape": CANYON_BAND, "slope": {"min": 0, "max": 20}},
    {"texture": "reddirt", "strength": 0.95, "fade": 6, "shape": circle(*PLAZA, 46)},
    {"texture": "reddirt", "strength": 0.9, "fade": 5, "shape": circle(*CHAMBER, 32)},
    {"_": "the basin: ash in broad drifts, cracked ash where it is thin", "texture": "ash",
     "shape": rect(-540, -566, 540, 72), "strength": 0.9, "slope": {"min": 0, "max": 24},
     "noise": {"scale": 80, "threshold": -0.1, "fade": 0.3, "seed": 11}},
    {"_": "glowing lava rock at the lakes' shores: the lowest ground of the basin", "texture": "lavarock",
     "height": {"min": -20, "max": 2.5, "fade": 2.5}, "strength": 1.0},
    {"_": "charcoal on the massif's summit and the plateau top", "texture": "charcoal",
     "shape": rect(-540, -1610, 540, -600), "strength": 0.7, "noise": {"scale": 70, "threshold": 0.0, "fade": 0.3,
                                                                   "seed": 13}},
    {"_": "dark spire rock on the steep faces above the basin floor (not the low lava islands: next to the road and the"
          " shore they would be a chunk's 5th layer)", "texture": "cliff", "slope": {"min": 30, "max": 44},
     "height": {"min": 14, "max": 400, "fade": 4}, "strength": 1.0},
    {"_": "the roads", "roads": True},
]
ROADS = [
    {"name": "canyon_road", "points": pts2(CANYON[::3]), "width": 9, "fade": 3, "texture": "road"},
    {"name": "causeway", "points": pts2(CAUSE[::2]), "width": 15, "fade": 4, "texture": "road"},
    {"name": "arrival", "points": [[ARRIVAL[0], ARRIVAL[1]], pts2(CAUSE[:1])[0]], "width": 15, "fade": 4,
     "texture": "road"},
    {"name": "gate", "points": [pts2(CAUSE[-1:])[0], [GATE[0], GATE[1] - 10]], "width": 18, "fade": 4,
     "texture": "road"},
]

# ------------------------------------------------------------------------------------------------- wmos, pois, areas
WMOS = []
for key, it in INTERIORS.items():
    ox, oy, oz = it["offset"]
    WMOS.append({"_comment": f"the real {key.upper()} interior, as map {it['map']} places it, moved by {it['offset']}",
                 "model": it["model"], "position": [ox, oy, oz], "facing": 180, "bounds": it["box"],
                 "buried": True, "label": f"{key.upper()}_INTERIOR"})

GATE_PORTAL_A = (CHAMBER[0], CHAMBER[1])                        # canyon chamber -> Ragefire
ARRIVAL_POINT = (ARRIVAL[0], ARRIVAL[1] + 6)                    # Ragefire's deep end -> here
GATE_PORTAL_C = (GATE[0], GATE[1] - 14)                         # the Gate of Blackrock -> Molten Core
POIS = [
    {"name": "raid_entrance", "title": "Raid Entrance", "kind": "entrance", "position": [PLAZA[0], PLAZA[1] - 8],
     "facing": 270, "radius": 8, "weight": 1},
    {"name": "portal_ragefire", "title": "Portal to Ragefire Chasm", "kind": "gate",
     "position": [GATE_PORTAL_A[0], GATE_PORTAL_A[1]], "facing": 0, "radius": 10, "weight": 1},
    {"name": "basin_arrival", "title": "The Molten Basin", "kind": "gate",
     "position": [ARRIVAL_POINT[0], ARRIVAL_POINT[1]], "facing": 270, "radius": 10, "weight": 1},
    {"name": "portal_molten_core", "title": "The Gate of Blackrock", "kind": "gate",
     "position": [GATE_PORTAL_C[0], GATE_PORTAL_C[1]], "facing": 270, "radius": 10, "weight": 1},
]
AREAS = [
    {"_": "The Blackrock Gate", "area_id": 5223, "shape": circle(GATE[0], GATE[1], 70)},
    {"_": "The Molten Basin", "area_id": 5222, "shape": rect(-540, -600, 540, 75)},
    {"_": "Ragefire Canyon", "area_id": 5221, "shape": rect(-540, 75, 540, 540)},
]

SPEC = {
    "_comment": [
        "Bleakhold: Crucible of Onyxia (map 902), v2. GENERATED by specs/crucible_gen_v2.py: edit that, not this.",
        "Axes (MapForge): a feature's [x, y] is world [X, Y]; tiles.x runs along world Y, tiles.y along X, so the",
        "block is X -1066.67..533.33 by Y -1600..533.33 (X below -540 is solid mountain, unreachable).",
        "Route: Ragefire Canyon (outdoor) -> portal -> Ragefire Chasm (real interior, under the canyon) -> portal ->",
        "the Molten Basin (outdoor) -> the Gate of Blackrock portal -> Molten Core (real interior, under the massif)",
        "-> from Ragnaros' lair a portal -> Onyxia's Lair (real interior, under the canyon plateau).",
        "The interiors are 'buried' WMOs: whole under the terrain, no liquid above them; the portals are server",
        "game objects (crucible_v2_portals.json -> the server SQL).",
    ],
    "format": "mapforge-terrain/1",
    "map": {"id": 902, "directory": "BleakholdCrucible", "tiles": {"x": [31, 34], "y": [31, 33]}},
    "seed": 20261106, "area_id": 5220, "uid_base": 330000,
    "areas": AREAS,
    "heightmap": {"base": 6,
                  "noise": [{"scale": 190, "amplitude": 6, "octaves": 4, "persistence": 0.52},
                            {"scale": 52, "amplitude": 2.2, "octaves": 3, "seed": 13},
                            {"scale": 17, "amplitude": 0.7, "octaves": 2, "seed": 31}],
                  "features": F},
    "lakes": LAKES,
    "textures": TEXTURES, "texture_rules": RULES, "roads": ROADS,
    "wmos": WMOS, "doodads": DOODADS, "scatter": SCATTER, "pois": POIS,
}

MAX_PROP_SLOPE = 34.0


def terrain_grid(spec_dict):
    import tempfile
    sys.path.insert(0, os.path.join(HERE, ".."))
    from terrain import build
    from terrain.spec import load_spec
    bare = dict(spec_dict, doodads=[], scatter=[], wmos=[])
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "terrain_only.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bare, f)
        return build.Context(load_spec(path)).grid


def ground(grid, x, y):
    from terrain import coords
    r, c = coords.world_to_lattice(x, y)
    return grid.get(int(round(r)), int(round(c)))


def slope_deg(grid, x, y):
    from terrain import coords
    r, c = coords.world_to_lattice(x, y)
    nz = grid.normal(int(round(r)), int(round(c)))[2]
    return math.degrees(math.acos(max(-1.0, min(1.0, nz))))


def settle(spec_dict, grid):
    """Drop every unlabeled prop on ground steeper than MAX_PROP_SLOPE (it would stand tilted or half sunk), except
    the ones meant for cliffs or the air. Labeled landmarks are reported, never dropped."""
    kept, dropped, labeled = [], 0, []
    for it in spec_dict["doodads"]:
        low = it["model"].lower()
        if any(MODELS[k][0].lower() == low for k in MODELS if k.startswith(SLOPE_EXEMPT)):
            kept.append(it)
            continue
        steep = slope_deg(grid, *it["position"][:2]) > MAX_PROP_SLOPE
        if steep and it.get("label"):
            labeled.append(it["label"])
        elif steep:
            dropped += 1
            continue
        kept.append(it)
    spec_dict["doodads"] = kept
    return dropped, labeled


def checks(grid):
    """The layout's rules (see the module docstring). Returns a list of problems; empty = all kept."""
    problems = []
    # every interior's top at least 20 yards under the lowest terrain over its box, and no lake above it
    for key in INTERIORS:
        x0, x1, y0, y1, z0, z1 = world_box(key)
        lowest = min(ground(grid, x, y) for x in np.linspace(x0, x1, 40) for y in np.linspace(y0, y1, 40))
        if lowest - z1 < 20:
            problems.append(f"{key}: top {z1:.0f} is only {lowest - z1:.0f} yd under the terrain ({lowest:.0f})")
        for lk in LAKES:
            P = np.asarray(lk["shape"]["polygon"]["points"])
            if P[:, 0].max() > x0 and P[:, 0].min() < x1 and P[:, 1].max() > y0 and P[:, 1].min() < y1:
                problems.append(f"{key}: the lake {lk['name']} lies over its box")
        if not (X0 < x0 and x1 < X1 and Y0 < y0 and y1 < Y1):
            problems.append(f"{key}: its box {x0:.0f}..{x1:.0f} x {y0:.0f}..{y1:.0f} leaves the map's tiles")
    keys = list(INTERIORS)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = world_box(keys[i]), world_box(keys[j])
            if a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3] and a[4] < b[5] and b[4] < a[5]:
                problems.append(f"{keys[i]} and {keys[j]} overlap")
    # the route: never steeper than 30 degrees, and clear of every lake by 8 yards
    route = [(float(x), float(y)) for x, y in CANYON] + [(float(x), float(y)) for x, y in CAUSE] + \
        [PLAZA, CHAMBER, ARRIVAL, GATE]
    steep = [(round(x), round(y), round(slope_deg(grid, x, y))) for x, y in route if slope_deg(grid, x, y) > 30]
    if steep:
        problems.append(f"route steeper than 30 degrees at {steep[:6]}{' ...' if len(steep) > 6 else ''}")
    for x, y in [(float(x), float(y)) for x, y in CAUSE]:
        for lk in LAKES:
            P = np.asarray(lk["shape"]["polygon"]["points"])
            if inside(P, x, y) or np.min(np.hypot(P[:, 0] - x, P[:, 1] - y)) < 8:
                problems.append(f"causeway at ({x:.0f}, {y:.0f}) is within 8 yd of {lk['name']}")
                break
    # walkability: flood from where a player starts across every step a player can climb (WALK_DEG); each outdoor
    # part must reach its own portal, must NOT reach the other part overland (the portals keep the order), and must
    # never reach the edge of the map's tiles (falling off the world)
    canyon = walkable(grid, PLAZA)
    basin = walkable(grid, ARRIVAL)
    if not reach(canyon, CHAMBER):
        problems.append("from the entrance the Ragefire portal chamber cannot be walked to")
    if reach(canyon, ARRIVAL) or reach(canyon, GATE):
        problems.append("the canyon connects overland to the basin (Ragefire Chasm could be skipped)")
    if not reach(basin, GATE):
        problems.append("from the basin's arrival ledge the Gate of Blackrock cannot be walked to")
    for name, region in (("canyon", canyon), ("basin", basin)):
        m = region[0]
        if m[0, :].any() or m[-1, :].any() or m[:, 0].any() or m[:, -1].any():
            problems.append(f"the {name} reaches the edge of the map's tiles (a player could walk off the world)")
    return problems


WALK_DEG = 50.0   # steeper than this the client slides a player back (the walkable-slope limit)


def walkable(grid, start):
    """(mask, grid) of the lattice points a player standing at start can walk to: 4-neighbour steps no steeper than
    WALK_DEG. Iterative dilation in numpy (no recursion, no scipy)."""
    from terrain import coords
    h = np.frombuffer(grid.h, dtype=np.float64).reshape(grid.rows, grid.cols)
    lim = math.tan(math.radians(WALK_DEG)) * coords.HALF_UNIT
    ok_down = np.abs(np.diff(h, axis=0)) <= lim     # between row r and r+1
    ok_right = np.abs(np.diff(h, axis=1)) <= lim    # between col c and c+1
    r, c = coords.world_to_lattice(*start)
    m = np.zeros_like(h, dtype=bool)
    m[int(round(r)) - grid.row0, int(round(c)) - grid.col0] = True
    while True:
        n = m.copy()
        n[1:, :] |= m[:-1, :] & ok_down
        n[:-1, :] |= m[1:, :] & ok_down
        n[:, 1:] |= m[:, :-1] & ok_right
        n[:, :-1] |= m[:, 1:] & ok_right
        if (n == m).all():
            return n, grid
        m = n


def reach(region, point):
    from terrain import coords
    m, grid = region
    r, c = coords.world_to_lattice(*point)
    return bool(m[int(round(r)) - grid.row0, int(round(c)) - grid.col0])


TRIGGER_BASE = 5901        # AreaTrigger ids: just above the realm's highest (5872), so the client's table stays dense
TRIGGER_RADIUS = 3.5       # yards: walk into the swirl
SWIRL_DISPLAY = 4396       # the mage-portal swirl (the realm's "Portal to Stormwind", gameobject_template 176296)
SWIRL_ENTRY = 902100
SWIRL_GUID = 9029001
BEHIND = 9.0               # a way back stands this far behind an arrival (where its tunnel came from)


def portals(grid):
    """The walk-in doorways: per doorway an AreaTrigger (client AreaTrigger.dbc + server areatrigger, from the
    config's area_triggers file), its teleport target, and a portal-swirl game object standing on it so it can be seen.
    Outdoor points sit on the ground; interior points are the original maps' floors moved into this map. Every
    arrival faces into the next area, and the way back stands BEHIND it (never on it: arriving inside a trigger would
    send the player straight back)."""
    def out(x, y, o=0.0):
        return (round(x, 2), round(y, 2), round(ground(grid, x, y) + 0.3, 2), round(o % (2 * math.pi), 3))

    def inn(key, name, o=None):
        x, y, z = to_crucible(key, INTERIORS[key]["points"][name])
        if o is None:
            o = INTERIORS[key]["entrance_facing"]
        return (x, y, round(z + 0.3, 2), round(o % (2 * math.pi), 3))

    def behind(p):
        x, y, z, o = p
        return (round(x - BEHIND * math.cos(o), 2), round(y - BEHIND * math.sin(o), 2), z, o)

    def toward(p, q):
        return math.atan2(q[1] - p[1], q[0] - p[0])

    south = math.radians(270)   # the server's orientation: 0 = +X, counter-clockwise toward +Y; the route runs -Y
    north = math.radians(90)
    # outdoor points
    chamber_in = out(*GATE_PORTAL_A, toward(CHAMBER, CANYON[-3]))   # each swirl faces the way players walk up
    chamber_back = out(CHAMBER[0] - 14 * math.cos(math.atan2(CHAMBER[1] - CANYON[-3][1], CHAMBER[0] - CANYON[-3][0])),
                       CHAMBER[1] - 14 * math.sin(math.atan2(CHAMBER[1] - CANYON[-3][1], CHAMBER[0] - CANYON[-3][0])))
    chamber_back = chamber_back[:3] + (round(toward(CHAMBER, CANYON[-3]) % (2 * math.pi), 3),)
    basin_arrive = out(ARRIVAL[0], ARRIVAL[1] - 8, south)
    basin_back = out(ARRIVAL[0], ARRIVAL[1] + 8, south)
    gate_in = out(*GATE_PORTAL_C, north)
    gate_arrive = out(GATE_PORTAL_C[0], GATE_PORTAL_C[1] + 22, north)
    # interior points
    rfc_arrive = inn("rfc", "entrance")
    mc_arrive = inn("mc", "entrance")
    ony_arrive = inn("ony", "entrance")
    rfc_end = inn("rfc", "deep_end", 0.0)
    rfc_end_arrive = inn("rfc", "deep_end_2", 0.0)
    rfc_end_arrive = rfc_end_arrive[:3] + (round(toward(rfc_end, rfc_end_arrive) % (2 * math.pi), 3),)
    rag_out = inn("mc", "ragnaros_lair_2", 0.0)
    rag_arrive = inn("mc", "ragnaros_lair", 4.046)          # Majordomo's own spot in the lair, his facing

    doorways = [
        ("Ragefire Chasm", chamber_in, rfc_arrive),
        ("Ragefire Canyon", behind(rfc_arrive), chamber_back),
        ("The Molten Basin", rfc_end, basin_arrive),
        ("Ragefire Chasm", basin_back, rfc_end_arrive),
        ("Molten Core", gate_in, mc_arrive),
        ("The Molten Basin", behind(mc_arrive), gate_arrive),
        ("Onyxia's Lair", rag_out, ony_arrive),
        ("Molten Core", behind(ony_arrive), rag_arrive),
    ]
    triggers, visuals = [], []
    for i, (name, at, to) in enumerate(doorways):
        # a doorway must never stand within reach of any arrival (that would bounce players back and forth)
        for _, _, other in doorways:
            gap = math.dist(at[:3], other[:3])
            if gap < TRIGGER_RADIUS + 4.0:
                raise SystemExit(f"doorway to {name} at {at[:3]} is only {gap:.1f} yd from an arrival {other[:3]}")
        triggers.append({"id": TRIGGER_BASE + i, "name": f"Crucible: to {name}", "position": [at[0], at[1], at[2]],
                         "radius": TRIGGER_RADIUS, "teleport": {"position": [to[0], to[1], to[2]],
                                                                "orientation": to[3]}})
        visuals.append({"guid": SWIRL_GUID + i, "name": f"to {name}", "x": at[0], "y": at[1], "z": round(at[2] - 0.3, 2),
                        "o": at[3]})
    return {
        "_comment": ["GENERATED by crucible_gen_v2.py. Map 902. area_triggers: read by bleakhold_crucible.json",
                     "(MapForge writes the client AreaTrigger.dbc rows and the server areatrigger/areatrigger_teleport",
                     "SQL from them). portal_visuals: the swirls standing on them (crucible_v2_portals.sql)."],
        "entrance": dict(zip("xyzo", out(PLAZA[0], PLAZA[1] - 8, south))),
        "area_triggers": triggers,
        "portal_visuals": visuals,
        "onyxia": dict(zip("xyz", to_crucible("ony", INTERIORS["ony"]["points"]["onyxia"]))),
        "ragnaros": dict(zip("xyz", to_crucible("mc", INTERIORS["mc"]["points"]["ragnaros"]))),
        "interior_boxes": {k: [round(v, 1) for v in world_box(k)] for k in INTERIORS},
    }


def sql_text(value):
    """A SQL string literal: backslashes and quotes escaped (\"Onyxia's Lair\" must not end the string early)."""
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def visuals_sql(doc):
    """The portal swirls (server game objects; the walk-in triggers themselves are MapForge's SQL)."""
    v = doc["portal_visuals"]
    guids = [p["guid"] for p in v]
    lines = [
        "-- Bleakhold: Crucible of Onyxia (map 902): the portal swirls that mark its walk-in doorways.",
        "-- GENERATED by Tools/MapForge/specs/crucible_gen_v2.py (bleak): edit that and generate again.",
        "-- Each stands on an AreaTrigger (the map's DBC SQL from MapForge's build: areatrigger + areatrigger_teleport);",
        "-- walking into it sends the player on. The swirl only shows where: it is a plain GENERIC object, not used.",
        f"DELETE FROM `gameobject_template` WHERE `entry` = {SWIRL_ENTRY};",
        "INSERT INTO `gameobject_template` (`entry`, `type`, `displayId`, `name`, `IconName`, `castBarCaption`, `unk1`, "
        "`size`, `Data0`, `Data1`, `Data2`, `Data3`, `Data4`, `Data5`, `Data6`, `Data7`, `Data8`, `Data9`, `Data10`, "
        "`Data11`, `Data12`, `Data13`, `Data14`, `Data15`, `Data16`, `Data17`, `Data18`, `Data19`, `Data20`, `Data21`, "
        "`Data22`, `Data23`, `AIName`, `ScriptName`, `VerifiedBuild`) VALUES",
        f"({SWIRL_ENTRY}, 5, {SWIRL_DISPLAY}, 'Crucible Doorway', '', '', '', 1.3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "
        "0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 0);",
        "",
        f"DELETE FROM `gameobject` WHERE `id` = {SWIRL_ENTRY} AND `guid` BETWEEN {min(guids)} AND {max(guids)};",
        "INSERT INTO `gameobject` (`guid`, `id`, `map`, `zoneId`, `areaId`, `spawnMask`, `phaseMask`, `position_x`, "
        "`position_y`, `position_z`, `orientation`, `rotation0`, `rotation1`, `rotation2`, `rotation3`, `spawntimesecs`, "
        "`animprogress`, `state`, `ScriptName`, `VerifiedBuild`, `Comment`) VALUES",
    ]
    rows = []
    for p in v:
        o = p["o"]
        rows.append(f"({p['guid']}, {SWIRL_ENTRY}, 902, 0, 0, 1, 1, {p['x']}, {p['y']}, {round(p['z'], 2)}, {o}, 0, 0, "
                    f"{round(math.sin(o / 2), 6)}, {round(math.cos(o / 2), 6)}, 300, 0, 1, '', 0, "
                    f"{sql_text('Crucible of Onyxia: doorway ' + p['name'])})")
    lines.append(",\n".join(rows) + ";")
    return "\n".join(lines) + "\n"


def dump(o, indent=0):
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
    grid = terrain_grid(SPEC)
    problems = checks(grid)
    dropped, steep_landmarks = settle(SPEC, grid)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(dump(SPEC) + "\n")
    doc = portals(grid)
    with open(OUT_PORTALS, "w", encoding="utf-8", newline="\n") as f:
        f.write(dump(doc) + "\n")
    with open(os.path.join(HERE, "crucible_v2_portals.sql"), "w", encoding="utf-8", newline="\n") as f:
        f.write(visuals_sql(doc))
    print(f"wrote {OUT}: {len(SPEC['doodads'])} doodads ({dropped} dropped off steep ground), {len(LAKES)} lava lakes,"
          f" {len(F)} terrain features, {len(SCATTER)} scatter groups; canyon {CANYON_S[-1]:.0f} yd, causeway"
          f" {M_LEN:.0f} yd")
    for key in INTERIORS:
        x0, x1, y0, y1, z0, z1 = world_box(key)
        print(f"  {key:3}: X {x0:7.1f}..{x1:7.1f}  Y {y0:7.1f}..{y1:7.1f}  Z {z0:7.1f}..{z1:7.1f}")
    if steep_landmarks:
        print("WARNING: labeled landmarks on steep ground:", steep_landmarks)
    if problems:
        print("LAYOUT PROBLEMS:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("layout checks: all kept")
