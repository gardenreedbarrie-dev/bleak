r"""Where MarkForge's inputs come from, and reading them.

Two sources give the same interface (read(name) -> bytes, has(name)):

    FolderSource  a plain folder holding the client's paths (case-insensitive, / or \): a package checkout in a dev
                  session (/tmp/.../ascust/repo), or files extracted for a test
    GameSource    the client's archive overlay exactly as RaceForge sees it (rflib.skins.game_archives: --client's
                  Data folder with --patches over it, every combination of the launcher's optional packs). A model,
                  skin or texture must resolve to the same bytes in every combination, a table to the same values
                  of what MarkForge reads of it (table(): RaceForge writes one copy of a table per archive, each
                  keeping that archive's own string block), or the run stops and names the combinations (one marks
                  archive serves all of them); --combination picks one when that is wanted

What is read: ChrRaces/CreatureDisplayInfo/CreatureModelData (each race and sex's model, so High Elf and Eredar use
whatever model the realm gives them), the model and its 00.skin, the model's own deathKnightEyeGlow (the eye sprite
layout), CharSections (every visible skin colour's skin and underwear, for the garment mask) and those textures.

BLP decoding here is numpy (palette with alpha 0/1/4/8, DXT1/3/5, BGRA), checked against RaceForge's decoder in
the tests.
"""

from __future__ import annotations

import hashlib
import os
import re
import struct

import numpy as np

from . import MarkForgeError

# The twelve playable races of the realm: id -> (clientFileString, fallback model race for a folder source)
RACES = {
    1: ("Human", "Human"), 2: ("Orc", "Orc"), 3: ("Dwarf", "Dwarf"), 4: ("NightElf", "NightElf"),
    5: ("Scourge", "Scourge"), 6: ("Tauren", "Tauren"), 7: ("Gnome", "Gnome"), 8: ("Troll", "Troll"),
    10: ("BloodElf", "BloodElf"), 11: ("Draenei", "Draenei"), 15: ("HighElf", "BloodElf"), 19: ("Eredar", "Draenei"),
}
TEMPLATE = {15: 10, 19: 11}  # High Elf and Eredar rows are clones of Blood Elf and Draenei (the contract)
SEXES = {0: "Male", 1: "Female"}
# raceforge.py's own default --config: its optional packs are the launcher's
DEFAULT_CONFIG = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "RaceForge",
                                               "races.json"))


def norm(name: str) -> str:
    return re.sub(r"[\\/]+", "\\\\", name.strip()).lstrip("\\")


# --- sources ------------------------------------------------------------------------------------------------------


class FolderSource:
    def __init__(self, root: str):
        if not os.path.isdir(root):
            raise MarkForgeError(f"{root}: not a folder")
        self.root = root
        self.kind = "folder"
        self._index = None

    def _build(self):
        idx = {}
        for dirpath, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d != ".git"]
            for f in files:
                full = os.path.join(dirpath, f)
                rel = os.path.relpath(full, self.root).replace(os.sep, "\\")
                idx.setdefault(rel.casefold(), full)
        self._index = idx

    def path(self, name: str) -> str | None:
        if self._index is None:
            self._build()
        return self._index.get(norm(name).casefold())

    def has(self, name: str) -> bool:
        return self.path(name) is not None

    def read(self, name: str) -> bytes:
        p = self.path(name)
        if p is None:
            raise MarkForgeError(f"{name}: not in {self.root}")
        with open(p, "rb") as f:
            return f.read()

    def where(self, name: str) -> str:
        return self.path(name) or "missing"


class GameSource:
    """The client's archives through RaceForge's overlay. Every combination of optional packs must read the same
    bytes for a file, unless one combination is chosen."""

    def __init__(self, client: str, patches: str, config: str | None = None, locale: str | None = None,
                 combination: str | None = None):
        try:
            from rflib import config as rfconfig, skins
        except ImportError as e:  # pragma: no cover - the repo always has RaceForge
            raise MarkForgeError(f"RaceForge (Tools/RaceForge) is needed to read the client's archives: {e}") from None
        # the launcher's optional packs come from RaceForge's races.json unless --config names another file, as for
        # raceforge.py itself (deploy/customize/customize.sh passes no --config)
        config = config or DEFAULT_CONFIG
        try:
            packs = rfconfig.load(config).archives.optional_packs
        except (OSError, rfconfig.ConfigError) as e:
            raise MarkForgeError(f"--config {config}: {e}") from None
        try:
            self.game = skins.game_archives(client, patches, packs, locale, alternate=True)
        except skins.SkinsError as e:
            raise MarkForgeError(str(e)) from None
        self.kind = "game"
        self.configs = list(self.game.patchset.configurations())
        if combination:
            pick = [c for c in self.configs if c[0] == combination]
            if not pick:
                raise MarkForgeError(f"--combination {combination}: the combinations are "
                                     f"{', '.join(c[0] for c in self.configs)}")
            self.configs = pick
        self._cache = {}

    def _winners(self, name):
        out = []
        for label, packs_on in self.configs:
            a = self.game.patchset.top(norm(name), packs_on)
            out.append((label, a))
        return out

    def has(self, name: str) -> bool:
        return any(a is not None for _, a in self._winners(name))

    def read(self, name: str) -> bytes:
        key = norm(name).casefold()
        if key in self._cache:
            return self._cache[key]
        datas = {}
        for label, a in self._winners(name):
            if a is None:
                raise MarkForgeError(f"{name}: no archive holds it in combination {label}")
            datas.setdefault(hashlib.sha1(a.read(norm(name))).hexdigest(), []).append((label, a.name))
        if len(datas) > 1:
            desc = "; ".join(f"{', '.join(l for l, _ in v)} read {v[0][1]}" for v in datas.values())
            raise MarkForgeError(f"{name} differs between pack combinations ({desc}): one marks archive serves all of "
                                 "them; make the combinations agree (the contract puts the models in patch-~) or pick "
                                 "one with --combination")
        label, a = self._winners(name)[0]
        data = a.read(norm(name))
        self._cache[key] = data
        return data

    def where(self, name: str) -> str:
        return ", ".join(f"{label}: {a.name if a else 'missing'}" for label, a in self._winners(name))

    def table(self, name: str):
        """A table (rflib DbcTable) as every combination reads it: each combination's winning copy parsed, and
        compared on what MarkForge uses of it (used_view()), not byte for byte. Raises naming the combinations
        when those values differ."""
        from rflib import schema_access
        from rflib.dbc import DbcError, DbcTable
        schema = schema_access.get(name)
        key = ("table", schema.filename.casefold())
        if key in self._cache:
            return self._cache[key]
        copies = {}
        for label, a in self._winners(schema.filename):
            if a is None:
                raise MarkForgeError(f"{schema.filename}: no archive holds it in combination {label}")
            data = a.read(norm(schema.filename))
            copies.setdefault(hashlib.sha1(data).hexdigest(), [data, []])[1].append((label, a.name))
        tables = []
        for data, labels in copies.values():
            try:
                tables.append((DbcTable.from_bytes(data, schema, f"{labels[0][1]}: {schema.filename}"), labels))
            except DbcError as e:
                raise MarkForgeError(str(e)) from None
        if len(tables) > 1:
            views = {}
            for table, labels in tables:
                views.setdefault(repr(used_view(self, name, table)), []).extend(labels)
            if len(views) > 1:
                desc = "; ".join(f"{', '.join(l for l, _ in v)} read {v[0][1]}" for v in views.values())
                raise MarkForgeError(f"{schema.filename}: what MarkForge reads of it differs between pack combinations "
                                     f"({desc}): one marks archive serves all of them; make the combinations agree "
                                     "or pick one with --combination")
        self._cache[key] = tables[0][0]
        return tables[0][0]

    def close(self):
        self.game.close()


def used_view(source, name: str, table) -> object:
    """What MarkForge reads of a table, comparable between pack combinations: CharSections' rows of the playable
    races (key, flags and texture names, the last of a repeated key winning, as the client), ChrRaces' rows of the
    playable races (clientFileString and display ids), the displays they name (modelID) and those models' names. Any
    other table: its rows and strings as they are."""
    if name == "CharSections":
        rows = {}
        for row in table.rows:
            race = table.get(row, "raceID")
            if race in RACES:
                k = tuple(table.get(row, c) for c in ("raceID", "sexID", "baseSection", "variationIndex", "colorIndex"))
                rows[k] = (table.get(row, "flags"), tuple(table.get_str(row, f"textureName[{i}]") for i in range(3)))
        return sorted(rows.items())
    if name == "ChrRaces":
        by_id = table.by_id()
        out = []
        for race in sorted(RACES):
            row = by_id.get(race)
            out.append((race, None) if row is None else (race, table.get_str(row, "clientFileString"),
                                                         table.get(row, "maleDisplayID"),
                                                         table.get(row, "femaleDisplayID")))
        return out
    if name == "CreatureDisplayInfo":
        chr_races = source.table("ChrRaces")
        races = chr_races.by_id()
        displays = sorted({chr_races.get(races[r], c) for r in RACES if r in races
                           for c in ("maleDisplayID", "femaleDisplayID")})
        by_id = table.by_id()
        return [(d, table.get(by_id[d], "modelID") if d in by_id else None) for d in displays]
    if name == "CreatureModelData":
        cdi = source.table("CreatureDisplayInfo")
        by_cdi = cdi.by_id()
        models = sorted({cdi.get(by_cdi[d], "modelID") for d, _ in used_view(source, "CreatureDisplayInfo", cdi)
                         if d in by_cdi})
        by_id = table.by_id()
        return [(m, table.get_str(by_id[m], "modelName") if m in by_id else None) for m in models]
    return ([list(r) for r in table.rows], bytes(table.strings))


# --- BLP decoding (numpy) -----------------------------------------------------------------------------------------

_HDR = struct.Struct("<4sIBBBBII16I16I")


def blp_info(data: bytes) -> dict:
    if len(data) < _HDR.size:
        raise MarkForgeError("too short for a BLP2 header")
    magic, ver, enc, asz, pref, mips, w, h, *rest = _HDR.unpack_from(data)
    if magic != b"BLP2" or ver != 1:
        raise MarkForgeError(f"not a BLP2 texture (magic {magic!r})")
    return {"encoding": enc, "alpha": asz, "preferred": pref, "mips": mips, "width": w, "height": h,
            "offsets": rest[:16], "sizes": rest[16:]}


def _expand565(c):
    r = (c >> 11) & 31
    g = (c >> 5) & 63
    b = c & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], -1).astype(np.int32)


def decode_blp(data: bytes, level: int = 0) -> np.ndarray:
    """(H, W, 4) uint8 RGBA of one level."""
    h = blp_info(data)
    w, hh = max(1, h["width"] >> level), max(1, h["height"] >> level)
    off, size = h["offsets"][level], h["sizes"][level]
    if not size or off + size > len(data):
        raise MarkForgeError(f"level {level} is missing or cut off")
    raw = np.frombuffer(data, np.uint8, size, off)
    n = w * hh
    if h["encoding"] == 1:
        pal = np.frombuffer(data, np.uint8, 1024, 0x94).reshape(256, 4)
        idx = raw[:n]
        rgb = pal[idx][:, [2, 1, 0]]
        a_sz = h["alpha"]
        ab = raw[n:]
        if a_sz == 8:
            a = ab[:n]
        elif a_sz == 4:
            a = (np.stack([ab & 15, ab >> 4], -1).reshape(-1)[:n] * 17).astype(np.uint8)
        elif a_sz == 1:
            a = (np.unpackbits(ab, bitorder="little")[:n] * 255).astype(np.uint8)
        else:
            a = np.full(n, 255, np.uint8)
        return np.concatenate([rgb, a[:, None]], 1).reshape(hh, w, 4).astype(np.uint8)
    if h["encoding"] == 3:
        px = raw[:n * 4].reshape(hh, w, 4)
        out = px[..., [2, 1, 0, 3]].copy()
        if not h["alpha"]:
            out[..., 3] = 255
        return out
    if h["encoding"] != 2:
        raise MarkForgeError(f"colorEncoding {h['encoding']} is not decoded")
    kind = {0: "DXT1", 1: "DXT3", 7: "DXT5"}.get(h["preferred"])
    if kind is None:
        raise MarkForgeError(f"DXT preferredFormat {h['preferred']} is not decoded")
    step = 8 if kind == "DXT1" else 16
    bw, bh = max(1, (w + 3) // 4), max(1, (hh + 3) // 4)
    blocks = raw[:bw * bh * step].reshape(bw * bh, step)
    col = blocks[:, -8:]
    c0 = col[:, 0].astype(np.int32) | (col[:, 1].astype(np.int32) << 8)
    c1 = col[:, 2].astype(np.int32) | (col[:, 3].astype(np.int32) << 8)
    bits = col[:, 4].astype(np.int64) | (col[:, 5].astype(np.int64) << 8) | (col[:, 6].astype(np.int64) << 16) | \
        (col[:, 7].astype(np.int64) << 24)
    p0, p1 = _expand565(c0), _expand565(c1)
    four = (c0 > c1) | (kind != "DXT1")
    p2 = np.where(four[:, None], (2 * p0 + p1) // 3, (p0 + p1) // 2)
    p3 = np.where(four[:, None], (p0 + 2 * p1) // 3, 0)
    pal = np.stack([p0, p1, p2, p3], 1)  # (B, 4, 3)
    pa = np.full((len(blocks), 4), 255, np.int32)
    pa[:, 3] = np.where(four, 255, 0)
    idx = (bits[:, None] >> (2 * np.arange(16))[None, :]) & 3  # (B, 16)
    rgb = np.take_along_axis(pal, idx[..., None].repeat(3, -1), 1)
    alpha = np.take_along_axis(pa, idx, 1)
    if kind == "DXT3":
        ab = blocks[:, :8]
        nib = np.stack([ab & 15, ab >> 4], -1).reshape(len(blocks), 16)
        alpha = nib.astype(np.int32) * 17
    elif kind == "DXT5":
        a0 = blocks[:, 0].astype(np.int32)
        a1 = blocks[:, 1].astype(np.int32)
        ab = np.zeros(len(blocks), np.int64)
        for k in range(6):
            ab |= blocks[:, 2 + k].astype(np.int64) << (8 * k)
        ai = (ab[:, None] >> (3 * np.arange(16))[None, :]) & 7
        tab = np.zeros((len(blocks), 8), np.int32)
        tab[:, 0], tab[:, 1] = a0, a1
        eight = a0 > a1
        for k in range(1, 7):
            tab[:, 1 + k] = np.where(eight, ((7 - k) * a0 + k * a1) // 7, tab[:, 1 + k])
        for k in range(1, 5):
            tab[:, 1 + k] = np.where(~eight, ((5 - k) * a0 + k * a1) // 5, tab[:, 1 + k])
        tab[:, 6] = np.where(~eight, 0, tab[:, 6])
        tab[:, 7] = np.where(~eight, 255, tab[:, 7])
        alpha = np.take_along_axis(tab, ai.astype(np.int64), 1)
    px = np.concatenate([rgb, alpha[..., None]], -1).reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4)
    return px.reshape(bh * 4, bw * 4, 4)[:hh, :w].astype(np.uint8)


# --- tables -------------------------------------------------------------------------------------------------------


def _table(source, name):
    if getattr(source, "kind", "folder") == "game":
        return source.table(name)
    from rflib import schema_access
    from rflib.dbc import DbcTable
    schema = schema_access.get(name)
    data = source.read(schema.filename)
    return DbcTable.from_bytes(data, schema, schema.filename)


def char_sections(source) -> list[dict]:
    t = _table(source, "CharSections")
    out = []
    names = [c.name for c in t.schema.columns]
    tex = [n for n in names if n.lower().startswith("texturename")]
    for row in t.rows:
        r = {n: t.get(row, n) for n in names if n not in tex}
        r["textures"] = [t.get_str(row, n) for n in tex]
        out.append(r)
    return out


def _col(r, *cands):
    for c in cands:
        if c in r:
            return r[c]
    raise MarkForgeError(f"CharSections has none of {cands}")


def visible_skins(rows, race: int, sex: int) -> list[dict]:
    """Skin colours a player or Death Knight can see on themselves: section 0 rows with 0x1 or 0x2 and no 0x8; each
    with its skin texture and its underwear row's pelvis and torso textures."""
    def key(r):
        return (_col(r, "raceID", "race"), _col(r, "sexID", "sex"), _col(r, "baseSection", "section"),
                _col(r, "variationIndex", "variation"), _col(r, "colorIndex", "colour", "color"))

    rows_k = {}
    for r in rows:
        rows_k[key(r)] = r  # the last of a repeated key wins, as the client
    out = []
    for (ra, sx, sec, var, col), r in sorted(rows_k.items()):
        if (ra, sx, sec) != (race, sex, 0):
            continue
        flags = _col(r, "flags")
        if flags & 0x8 or not flags & 0x3:
            continue
        uw = rows_k.get((race, sex, 4, 0, col))
        out.append({"colour": col, "variation": var, "skin": r["textures"][0],
                    "pelvis": uw["textures"][0] if uw else "", "torso": uw["textures"][1] if uw else "",
                    "flags": flags})
    return out


def model_paths(source, race: int, sex: int) -> tuple[str, str]:
    """The race and sex's model and 00.skin: from ChrRaces -> CreatureDisplayInfo -> CreatureModelData (the realm's
    own tables: High Elf and Eredar may have models of their own); a folder without those tables (a package checkout)
    gives the stock path of the race's model race, a game source never (it stops)."""
    try:
        chr_races = _table(source, "ChrRaces")
        cdi = _table(source, "CreatureDisplayInfo")
        cmd = _table(source, "CreatureModelData")
    except MarkForgeError as e:
        if getattr(source, "kind", "folder") != "folder":
            # the realm's own tables must say which model a race has (High Elf and Eredar may have their own): never
            # the stock path in their place
            raise MarkForgeError(f"race {race} sex {sex}: the client's model tables cannot be read: {e}") from None
        chr_races = None
    if chr_races is not None:
        row = chr_races.by_id().get(race)
        if row is None:
            raise MarkForgeError(f"ChrRaces has no race {race}")
        cfs = chr_races.get_str(row, "clientFileString")
        if cfs != RACES[race][0]:
            raise MarkForgeError(f"ChrRaces race {race} is {cfs!r}, not {RACES[race][0]}: not the realm's tables")
        disp = chr_races.get(row, "femaleDisplayID" if sex else "maleDisplayID")
        d = cdi.by_id().get(disp)
        if d is None:
            raise MarkForgeError(f"CreatureDisplayInfo has no display {disp} (race {race} sex {sex})")
        mrow = cmd.by_id().get(cdi.get(d, "modelID"))
        if mrow is None:
            raise MarkForgeError(f"CreatureModelData has no model {cdi.get(d, 'modelID')}")
        name = cmd.get_str(mrow, "modelName")
        base = re.sub(r"\.(mdx|mdl|m2)$", "", norm(name), flags=re.I)
    else:
        mr = RACES[race][1]
        base = f"Character\\{mr}\\{SEXES[sex]}\\{mr}{SEXES[sex]}"
    return base + ".m2", base + "00.skin"


def strip_skins_prefix(path: str) -> str:
    """Character\\BleakholdSkins\\<race>\\<10 hex>\\<original> -> <original> (the purple High Elf skins: their
    underwear is the Blood Elf's, so the garment is found against the original skin)."""
    m = re.match(r"(?i)^character\\bleakholdskins\\[^\\]+\\[0-9a-f]{10}\\(.+)$", norm(path))
    return m.group(1) if m else path


def strip_ascension_prefix(path: str) -> str:
    m = re.match(r"(?i)^character\\ascension\\(?:rebuilt\\[0-9a-f]{10}\\)?(character\\.+)$", norm(path))
    return m.group(1) if m else path


def rows_race(source, race: int) -> int:
    """The race whose CharSections rows stand for this one: on the realm (a game source) every race its own (High
    Elf and Eredar rows are the clones with their filters); in a folder (a package checkout) races 15 and 19 are
    the package's Skeleton and Taunka, so High Elf and Eredar read Blood Elf's and Draenei's rows."""
    if getattr(source, "kind", "folder") != "game" and race in TEMPLATE:
        return TEMPLATE[race]
    return race


def garment_union(source, rows, race: int, sex: int, log=None) -> tuple[np.ndarray, list[dict]]:
    """The union over every visible skin colour of where its underwear is cloth (atlas.garment_from), as a 512 atlas
    mask, and a per-colour report, each underwear compared with the skin it was painted for: the purple High Elf
    skin's Blood Elf original, and its underwear's original too (raceforge.py skins recolours an opaque underwear
    where it is bare skin, under the same Character\\BleakholdSkins\\ rule; the original is the Blood Elf skin with
    the garment painted in, so the cloth is found by the same pair either way)."""
    from .atlas import N, SECTIONS, garment_from, garment_reference_pct, place_section, section_of
    union = np.zeros((N, N), bool)
    report = []
    skins = visible_skins(rows, rows_race(source, race), sex)
    seen = set()
    for s in skins:
        key = (s["skin"].casefold(), s["pelvis"].casefold(), s["torso"].casefold())
        if key in seen:
            continue
        seen.add(key)
        skin_name = strip_skins_prefix(s["skin"])
        try:
            skin = decode_blp(source.read(skin_name))
        except MarkForgeError as e:
            report.append({"colour": s["colour"], "skipped": f"{skin_name}: {e}"})
            continue
        if skin.shape[0] != N:  # bring the skin to the 512 layout
            f = N // skin.shape[0]
            skin = np.repeat(np.repeat(skin, f, 0), f, 1) if f >= 1 else skin
        entry = {"colour": s["colour"], "skin": skin_name}
        for part, sec in (("pelvis", "LU"), ("torso", "TU")):
            name = strip_skins_prefix(s[part]) if s[part] else ""
            if not name:
                continue
            try:
                uw = decode_blp(source.read(name))
            except MarkForgeError as e:
                entry[part] = f"skipped: {e}"
                continue
            x, y, w, h = SECTIONS[sec]
            sk = section_of(sec, skin)
            if uw.shape[:2] != sk.shape[:2]:
                fy = uw.shape[0] / sk.shape[0]
                if fy > 1:
                    k = int(fy)
                    uw = uw[::k, ::k]
                else:
                    k = int(round(1 / fy))
                    uw = np.repeat(np.repeat(uw, k, 0), k, 1)
            g, thr = garment_from(uw, sk)
            union |= place_section(g, sec)
            cover, ref = 100 * float(g.mean()), garment_reference_pct(uw, sk)
            entry[part] = {"texture": name, "cover_pct": round(cover, 1), "threshold": round(thr, 1),
                           "reference_pct": round(ref, 1)}
            if cover < GARMENT_GATE * ref:
                # the mask lost the cloth: marks would be painted over the underwear (the gate's own check reads
                # the same mask, so only this comparison sees it)
                entry[part]["short"] = True
        report.append(entry)
    return union, report


GARMENT_GATE = 0.5  # a mask that covers less than this share of the texels that differ from the skin fails the build


def garment_problems(report: list[dict]) -> list[str]:
    """The garment gate: every visible skin colour whose skin or underwear could not be read (garment_union's
    "skipped": the mask does not cover it, so marks could be painted over its cloth), and every underwear whose mask
    is far below its reference (its "short")."""
    out = []
    for entry in report:
        if "skipped" in entry:
            out.append(f"colour {entry.get('colour')}: the skin was not read ({entry['skipped']}): its underwear is "
                       "not in the garment mask")
        for part in ("pelvis", "torso"):
            v = entry.get(part)
            if isinstance(v, str):
                out.append(f"colour {entry.get('colour')}: the {part} underwear was not read ({v}): it is not in the "
                           "garment mask")
            if isinstance(v, dict) and v.get("short"):
                out.append(f"colour {entry.get('colour')}: {v['texture']}: the garment mask covers {v['cover_pct']}% "
                           f"of the section, but {v['reference_pct']}% differs from the skin (threshold "
                           f"{v['threshold']}): the cloth was not found, marks would be painted over it")
    return out


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()
