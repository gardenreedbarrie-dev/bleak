"""The fit check's verdicts and its report: spawn classification, the per-map and per-zone summary, the CSV of every
spawn that is not fine, and a PNG heatmap of the terrain change per map. Standard library only; the PNG is written
with zlib, and PIL (when it is installed) only adds the legend's words.
"""

from __future__ import annotations

import csv
import math
import struct
import zlib

import fitcheck_formats as ff

FINE = "fine"
SHIFTED = "shifted"
BROKEN = "broken"
NO_GROUND = "no-ground"
CLASSES = (BROKEN, SHIFTED, FINE, NO_GROUND)

# what a map's check came to (map_state)
CHANGED = "changed"
SAME = "same"
NOT_CHECKED = "not-checked"


class Thresholds:
    def __init__(self, fine: float = 1.5, broken: float = 4.0, floor_margin: float = 3.0):
        if not 0 < fine < broken:
            raise ValueError("thresholds must be 0 < fine < broken")
        self.fine = fine
        self.broken = broken
        self.floor_margin = floor_margin

    def grade(self, value: float) -> str:
        if value <= self.fine:
            return FINE
        if value <= self.broken:
            return SHIFTED
        return BROKEN


class Verdict:
    __slots__ = ("cls", "stance", "judged", "delta", "reason")

    def __init__(self, cls, stance, judged, delta, reason):
        self.cls, self.stance, self.judged, self.delta, self.reason = cls, stance, judged, delta, reason


def judge(old: float | None, new: float | None, z: float, t: Thresholds, new_tile: bool = True) -> Verdict:
    """One spawn. old/new: the server's ground under it now and after the new files (None: no ground there - no
    tile, or a hole). new_tile: whether the new files have the spawn's tile at all (False: no tile, or one that
    cannot be read).

    stance (decided from the spawn's z against the OLD ground, with t.floor_margin, default 3 yd):
      ground - |z - old| <= margin: it stands on the terrain, so it moves with it: judged by |new - old|.
      above  - z > old + margin: it stands on something else (a WMO floor, a bridge, a model), swims or flies. The
               terrain matters only if the new ground comes up through it: judged by new - z (how far the new
               ground is above its feet; a lower or slightly higher ground leaves it as it is).
      below  - z < old - margin: it is under the terrain (a cave or a building below ground). The terrain matters
               only if the new ground drops below it: judged by z - new.
      no-old-ground - the server has no ground there today (a hole or no tile): judged like "above", by new - z.
    The judged value is graded fine (<= t.fine, 1.5 yd), shifted (<= t.broken, 4 yd) or broken. No new ground
    where the server has ground today: broken when the new files have no tile there (the tile's models go with it),
    or when a new hole opens under a spawn on the ground; fine for one above or below the terrain (it stands on a
    floor, a bridge or a cave's model, which a hole in the terrain does not take away; the models are not
    compared). No ground in either is "no-ground" (not judged: WMO-only maps, holes, places off the terrain).
    """
    if old is None and new is None:
        return Verdict(NO_GROUND, "no-ground", None, None, "no terrain under it, now or with the new files")
    if new is None:
        stance = "ground" if abs(z - old) <= t.floor_margin else ("above" if z > old else "below")
        if not new_tile:
            return Verdict(BROKEN, stance, None, None,
                           "the new files have no tile here (or it cannot be read, see NOTE) where the server has "
                           "ground")
        if stance == "ground":
            return Verdict(BROKEN, stance, None, None, "the new files cut a hole in the ground it stands on")
        return Verdict(FINE, stance, None, None,
                       "the terrain " + ("under" if stance == "above" else "over") + " it is now a hole; it stands "
                       "on a model (floor, bridge, cave), which is not compared")
    if old is None:
        j = new - z
        return Verdict(t.grade(j), "no-old-ground", j, None,
                       "new ground where the server has none" + (" - above its feet" if j > t.fine else ""))
    d = new - old
    h = z - old
    if h > t.floor_margin:
        j = new - z
        return Verdict(t.grade(j), "above", j, d,
                       "stands above the ground (floor, bridge, flying, swimming)" +
                       ("; the new ground comes up through it" if j > t.fine else ""))
    if h < -t.floor_margin:
        j = z - new
        return Verdict(t.grade(j), "below", j, d,
                       "under the ground (cave)" + ("; the new ground drops below it" if j > t.fine else ""))
    j = abs(d)
    return Verdict(t.grade(j), "ground", j, d, "on the ground" + ("" if j <= t.fine else
                                                                    (" - the ground rose" if d > 0 else
                                                                     " - the ground sank")))


def map_state(res) -> tuple[str, str]:
    """(CHANGED, SAME or NOT_CHECKED, why) for one map. Changed: a ground point moved by more than the rounding of
    the server's file (fitcheck.compare_tile), a tile is lost or new, a chunk has other holes or another area id, or
    the water differs in a cell (all of it is in the server's .map files too), or the new files' Map.dbc drops the
    map. Same: tiles were compared and none of that. Not checked: no tile was compared at all. why says what
    changed, or why nothing was compared."""
    ts = res.terrain
    what = []
    lost_why = getattr(res, "lost_why", "")
    if lost_why:
        what.append(lost_why)
    if ts.get("changed_points"):
        what.append("heights")
    if res.old_only:
        what.append(f"{len(res.old_only)} tile(s) lost")
    if res.new_only:
        what.append(f"{len(res.new_only)} new tile(s)")
    if res.holes_changed:
        what.append(f"holes in {res.holes_changed} chunk(s)")
    if res.areas_changed:
        what.append(f"area ids of {res.areas_changed} chunk(s)")
    water = getattr(res, "water", None)
    if water and water["cells"]:
        what.append(f"water in {water['cells']} cell(s) of {len(water['tiles'])} tile(s)")
    if what:
        return CHANGED, ", ".join(what)
    if res.chunk_delta:
        return SAME, ""
    if getattr(res, "pack_empty", False):
        return NOT_CHECKED, ("the new files have no ADT and no WDT for this map, so nothing was compared (the base "
                             "client's files stay; is the map's folder name right?)")
    if getattr(res, "base_kept", None):
        return NOT_CHECKED, ("the new files have no ADT for any of this map's tiles, so nothing was compared (the "
                             "base client's ground stays)")
    return NOT_CHECKED, "no terrain on either side (WMO-only); its buildings are not compared"


# ----------------------------------------------------------------------------------------------- PNG

def write_png(path: str, width: int, height: int, rgb: bytearray) -> None:
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def _hex(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


BACKGROUND = _hex("#ffffff")
UNCHANGED = _hex("#e4e3df")
OLD_ONLY = _hex("#52514e")  # the server has ground, the new files have none
NEW_ONLY = _hex("#6250d6")  # the new files add ground the server does not have
NO_DATA = _hex("#a9a8a3")
WATER = _hex("#14a5a5")  # the water differs in the chunk (drawn as a square in its middle)
UP = [_hex(c) for c in ("#fbd3d0", "#f0928f", "#e34948", "#9e2525")]
DOWN = [_hex(c) for c in ("#cde2fb", "#86b6ef", "#2a78d6", "#104281")]
MARK_RING = _hex("#0b0b0b")
MARK_CORE = _hex("#fab219")


def delta_color(d: float, t: Thresholds) -> tuple[int, int, int]:
    if d != d:
        return NO_DATA
    a = abs(d)
    if a < 0.05:
        return UNCHANGED
    step = 0 if a <= t.fine else 1 if a <= t.broken else 2 if a <= 15.0 else 3
    return (UP if d > 0 else DOWN)[step]


def heatmap(path: str, res, t: Thresholds) -> str:
    """One pixel block per chunk: the chunk's largest change (signed, new - old), north at the top."""
    kept = getattr(res, "base_kept", set())
    tiles = set(res.chunk_delta) | res.old_only | res.new_only | kept
    if not tiles:
        return ""
    tx0 = min(t_[0] for t_ in tiles)
    tx1 = max(t_[0] for t_ in tiles)
    ty0 = min(t_[1] for t_ in tiles)
    ty1 = max(t_[1] for t_ in tiles)
    cols = (tx1 - tx0 + 1) * 16
    rows = (ty1 - ty0 + 1) * 16
    s = max(1, min(6, 2048 // max(cols, rows)))
    w, h = cols * s, rows * s
    img = bytearray(BACKGROUND * (w * h))

    def fill(c0, r0, size_c, size_r, color):
        for r in range(r0, min(h, r0 + size_r)):
            if r < 0:
                continue
            base = r * w
            for c in range(max(0, c0), min(w, c0 + size_c)):
                img[(base + c) * 3:(base + c) * 3 + 3] = bytes(color)

    for (tx, ty) in kept:  # not in the pack: the base client's ground stays
        fill((tx - tx0) * 16 * s, (ty - ty0) * 16 * s, 16 * s, 16 * s, UNCHANGED)
    for (tx, ty), vals in res.chunk_delta.items():
        for iy in range(16):
            for ix in range(16):
                fill(((tx - tx0) * 16 + ix) * s, ((ty - ty0) * 16 + iy) * s, s, s, delta_color(vals[iy * 16 + ix], t))
    inner = max(1, s // 2)
    for (tx, ty), chunks in getattr(res, "water_chunks", {}).items():
        for ci in chunks:
            iy, ix = divmod(ci, 16)
            c0 = ((tx - tx0) * 16 + ix) * s + (s - inner) // 2
            r0 = ((ty - ty0) * 16 + iy) * s + (s - inner) // 2
            fill(c0, r0, inner, inner, WATER)
    for (tx, ty) in res.old_only:
        fill((tx - tx0) * 16 * s, (ty - ty0) * 16 * s, 16 * s, 16 * s, OLD_ONLY)
    for (tx, ty) in res.new_only:
        fill((tx - tx0) * 16 * s, (ty - ty0) * 16 * s, 16 * s, 16 * s, NEW_ONLY)
    m = max(2, s)
    for row in res.spawns:
        if row["class"] != BROKEN:
            continue
        c = int(((ff.ZERO - row["y"]) / ff.CHUNK_SIZE - tx0 * 16) * s)
        r = int(((ff.ZERO - row["x"]) / ff.CHUNK_SIZE - ty0 * 16) * s)
        fill(c - m, r - m, 2 * m + 1, 2 * m + 1, MARK_RING)
        fill(c - m + 1, r - m + 1, 2 * m - 1, 2 * m - 1, MARK_CORE)
    try:
        from PIL import Image, ImageDraw  # optional: only the legend's words need it
    except ImportError:
        write_png(path, w, h, img)
        return path
    base = Image.frombytes("RGB", (w, h), bytes(img))
    legend_h = 172
    canvas = Image.new("RGB", (max(w, 560), h + legend_h), BACKGROUND)
    canvas.paste(base, (0, 0))
    dr = ImageDraw.Draw(canvas)
    y = h + 8
    dr.text((8, y), f"map {res.map_id} {res.name}: largest ground change per chunk (new - old), north up; "
                    f"tiles {tx0}-{tx1} x {ty0}-{ty1}", fill=(11, 11, 11))
    items = [(UNCHANGED, "same (< 0.05 yd), or kept")]
    labels = [f"<= {t.fine:g}", f"<= {t.broken:g}", "<= 15", "> 15"]
    for i in range(4):
        items.append((UP[i], f"up {labels[i]} yd"))
    for i in range(4):
        items.append((DOWN[i], f"down {labels[i]} yd"))
    items += [(OLD_ONLY, "server only (no new tile)"), (NEW_ONLY, "new tile only"), (MARK_CORE, "broken spawn"),
              (WATER, "water differs (dot)")]
    for i, (color, label) in enumerate(items):
        cx = 8 + (i % 4) * 138
        cy = y + 20 + (i // 4) * 22
        dr.rectangle([cx, cy, cx + 14, cy + 14], fill=color, outline=MARK_RING if color == MARK_CORE else None)
        dr.text((cx + 20, cy + 1), label, fill=(82, 81, 78))
    canvas.save(path)
    return path


# ----------------------------------------------------------------------------------------------- text

def _yd(v) -> str:
    return "-" if v is None else f"{v:+.2f}"


def _h(v) -> str:
    return "-" if v is None else f"{v:.2f}"


def _counts(counts: dict) -> str:
    return ", ".join(f"{counts.get(c, 0)} {c}" for c in CLASSES)


def _severity(row) -> tuple:
    order = {BROKEN: 0, SHIFTED: 1, FINE: 2, NO_GROUND: 3}
    j = row["judged"]
    return (order[row["class"]], -(j if j is not None else 1e9))


def map_summary(res, t: Thresholds, worst: int = 20) -> list[str]:
    L = []
    L.append("=" * 100)
    L.append(f"Map {res.map_id} {res.name} (folder '{res.folder}')")
    L.append("=" * 100)
    for n in res.notes:
        L.append(f"  NOTE: {n}")
    shared = len(res.chunk_delta)
    kept = len(getattr(res, "base_kept", ()))
    L.append(f"  Tiles: {shared} in both, {kept} not in the new files (the base client's stay: unchanged), "
             f"{len(res.old_only)} only on the server (no new tile: their ground would be gone), "
             f"{len(res.new_only)} only in the new files (new ground).")
    ts = res.terrain
    if ts["n"]:
        mean = ts["sum"] / ts["n"]
        L.append(f"  Ground over the shared tiles: moved {mean:.2f} yd on average; the largest change is "
                 f"{ts['max_signed']:+.2f} yd in the chunk around x {ts['max_at'][0]:.0f}, y {ts['max_at'][1]:.0f} "
                 f"(tile {ts['max_tile'][0]},{ts['max_tile'][1]}).")
        L.append(f"  {100.0 * ts['over_fine'] / ts['n']:.2f}% of the ground points moved more than {t.fine:g} yd, "
                 f"{100.0 * ts['over_broken'] / ts['n']:.2f}% more than {t.broken:g} yd; {ts['same_tiles']} of "
                 f"{shared} shared tiles are unchanged (every point within 0.01 yd, or within the rounding of the "
                 f"server's .map file: up to {ts.get('tolerance_max', 0.01):.4f} yd here).")
        if res.holes_changed or res.areas_changed:
            L.append(f"  Chunks with other holes: {res.holes_changed}; chunks with another area id: "
                     f"{res.areas_changed}.")
    w = getattr(res, "water", None)
    if w and w["cells"]:
        where = ""
        if w["max_at"]:
            (wtx, wty), (wx, wy) = w["max_at"]
            where = f" (around x {wx:.0f}, y {wy:.0f}, tile {wtx},{wty})"
        L.append(f"  Water: it differs in {w['cells']} cell(s) of {len(w['tiles'])} tile(s): {w['gained']} get water "
                 f"they did not have, {w['lost']} lose it, {w['other']} have another liquid or level"
                 + (f"; the level moved by up to {w['max_level']:.2f} yd{where}" if w["max_level"] else "") + ".")
    if w and w["unknown"]:
        L.append(f"  Water NOT compared on {len(w['unknown'])} tile(s): the water of split ADTs is not read.")
    if w and w["flags_unknown"]:
        L.append(f"  On {len(w['flags_unknown'])} tile(s) the water's flags were not compared (no LiquidType.dbc), "
                 f"only where it is, its liquid id and its level.")
    c = res.class_counts
    L.append(f"  Spawns: {len(res.spawns)} checked: {_counts(c)}.")
    ws = getattr(res, "water_spawns", [])
    if ws:
        L.append(f"  Spawns at or in water that differs: {len(ws)} (a swimmer may end up in the air, or a spawn on "
                 f"land under water; they are judged by the ground only): " +
                 ", ".join(f"{r['guid']} {r['name'] or r['kind']}" for r in ws[:worst]) +
                 (f" and {len(ws) - worst} more" if len(ws) > worst else "") + ".")
    state, why = map_state(res)
    water_unknown = bool(w and w["unknown"])
    if state == SAME and water_unknown:
        L.append(f"  VERDICT: the ground is the same (heights, holes, area ids) and no spawn moves, but the water of "
                 f"{len(w['unknown'])} tile(s) was NOT compared (split ADTs), so this does not say the server's .map "
                 f"files still fit. (vmaps/mmaps are not compared either.)")
    elif state == SAME:
        L.append("  VERDICT: the ground is the same (heights, holes, area ids and water). The server's .map files "
                 "still fit and no spawn moves; only the look changes (textures, models). (vmaps/mmaps are not "
                 "compared: models and buildings can still differ.)")
    elif state == CHANGED:
        L.append(f"  VERDICT: the ground changed ({why}). Before this ships the server's maps (and vmaps, mmaps) "
                 f"must be extracted again from the new files, and the {c.get(BROKEN, 0)} broken and "
                 f"{c.get(SHIFTED, 0)} shifted spawns need a look (new z, or moved)."
                 + (f" The water of {len(w['unknown'])} tile(s) was not compared (split ADTs)." if water_unknown
                    else ""))
    else:
        L.append(f"  VERDICT: NOT CHECKED - {why}.")
    if res.zones:
        L.append("")
        L.append("  By zone (most broken spawns first):")
        L.append(f"    {'zone':34} {'ground mean':>11} {'max':>8}  spawns")
        for z in sorted(res.zones.values(), key=lambda z: (-z["spawns"].get(BROKEN, 0), -z["spawns"].get(SHIFTED, 0),
                                                           -(z["max"] or 0), z["label"])):
            mean = f"{z['sum'] / z['n']:.2f}" if z["n"] else "-"
            mx = f"{z['max']:.2f}" if z["n"] else "-"
            L.append(f"    {z['label'][:34]:34} {mean:>11} {mx:>8}  {_counts(z['spawns'])}")
    bad = sorted([r for r in res.spawns if r["class"] in (BROKEN, SHIFTED)], key=_severity)[:worst]
    if bad:
        L.append("")
        L.append(f"  The worst {len(bad)} spawns:")
        L.append(f"    {'class':8} {'kind':8} {'guid':>9} {'entry':>8} {'name':28} {'x':>10} {'y':>10} {'z':>8} "
                 f"{'old':>8} {'new':>8} {'judged':>7}  why")
        for r in bad:
            L.append(f"    {r['class']:8} {r['kind']:8} {r['guid']:>9} {r['entry']:>8} {r['name'][:28]:28} "
                     f"{r['x']:10.2f} {r['y']:10.2f} {r['z']:8.2f} {_h(r['old']):>8} {_h(r['new']):>8} "
                     f"{_yd(r['judged']):>7}  {r['reason']} [{r['zone']}]")
    return L


CSV_FIELDS = ["map_id", "map", "class", "kind", "guid", "entry", "name", "x", "y", "z", "old_ground", "new_ground",
              "delta", "stance", "judged", "zone", "tile", "reason"]


def write_csv(path: str, results) -> int:
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_FIELDS)
        for res in results:
            for r in sorted(res.spawns, key=_severity):
                if r["class"] == FINE:
                    continue
                w.writerow([res.map_id, res.name, r["class"], r["kind"], r["guid"], r["entry"], r["name"],
                            f"{r['x']:.3f}", f"{r['y']:.3f}", f"{r['z']:.3f}", _num(r["old"]), _num(r["new"]),
                            _num(r["delta"]), r["stance"], _num(r["judged"]), r["zone"],
                            f"{r['tile'][0]}_{r['tile'][1]}", r["reason"]])
                n += 1
    return n


def _num(v) -> str:
    return "" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.3f}"


def method_lines(t: Thresholds) -> list[str]:
    return [
        "How to read this:",
        "  old ground = the server's ground today (its .map files, read and interpolated exactly as the world server",
        "  does); new ground = what the server would read after extracting the new files. delta = new - old.",
        f"  Each spawn: fine (moved <= {t.fine:g} yd), shifted ({t.fine:g}-{t.broken:g} yd: looks a little off, "
        "may float or sink in),",
        f"  broken (> {t.broken:g} yd, or no new ground where there was ground): floats in the air or sits under the "
        "ground.",
        f"  A spawn more than {t.floor_margin:g} yd above the old ground stands on a floor, bridge or model (or flies "
        "or swims): it",
        "  counts only if the new ground comes up through it (judged = new - z). One more than "
        f"{t.floor_margin:g} yd below it is in a cave: it",
        "  counts only if the new ground drops below it (judged = z - new). A new hole under either leaves it on",
        "  its model (fine); under a spawn on the ground it is broken. no-ground = no terrain there (WMO-only maps).",
        "  A tile the new files do not carry keeps the base client's ADT (unchanged), unless the new WDT drops it.",
        "  A ground point has moved when it is off by more than 0.01 yd and more than the rounding of the server's",
        "  .map file (half a step of its uint8/uint16 heights).",
        "  The water is compared cell by cell as the server reads it from the .map file (where it is, its liquid and",
        "  flags, its level within 0.01 yd); new ADTs give what map_extractor would write from their MH2O and MCLQ.",
        "  Water that differs makes the ground 'changed'; spawns are still judged by the ground only. The water of",
        "  split ADTs is not read: it is NOT CHECKED. A new ADT that map_extractor would refuse (or crash on) gives",
        "  the server no .map file: its tile is lost.",
    ]
