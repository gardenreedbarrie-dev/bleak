r"""raceforge.py picker-data: the numbers the glue picker and the barbershop hook compare with the exe's
(README.md, "Bleakhold appearance data contract", "Picker data").

- customize/package_counts.json holds the pinned package's CharSections rows of races 1-11 as numbers only (section,
  variation, flags, colour ranges; repeated rows already dropped as customize drops them) and B per race and sex.
  `picker-data --package <dir>` makes it from the package's tables; CI never needs the package.
- From those numbers, the curation and the catalogue, the same steps as customize (curation.hide, the clones 15 <- 10
  and 19 <- 11, the race filters, every race and sex with all 12 looks and eyes 1-5) give the stage-2 tables, and a
  model of the client's lists (Walk: the walks the skin and face arrows make, which depend on the face and on the
  skin the face loop starts from) gives the files:
  Interface/Bleakhold/Glue/BleakholdCustomizeData.lua (creation rules) and Interface/AddOns/Bleakhold/BarberData.lua
  (world rules). `--check` regenerates both and fails when a file differs.

Rows that customize hides on the server because a texture is missing (no source to rebuild it from) are not known
here; the glue then sees other counts and shows plain n/N.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter

from . import appearance as ap
from . import curation as curmod
from . import marksrows, schema_access
from .dbc import DbcTable

COUNTS_VERSION = 1
DATA_VERSION = 1
GLUE_FILE = os.path.join("Interface", "Bleakhold", "Glue", "BleakholdCustomizeData.lua")
BARBER_FILE = os.path.join("Interface", "AddOns", "Bleakhold", "BarberData.lua")


class PickerError(Exception):
    pass


# --- package_counts.json ---------------------------------------------------------------------------------------


def _ranges(values: list[int]) -> str:
    values = sorted(set(values))
    out, start = [], None

    for i, v in enumerate(values):
        if start is None:
            start = v

        if i + 1 == len(values) or values[i + 1] != v + 1:
            out.append(str(start) if start == v else f"{start}-{v}")
            start = None

    return ",".join(out)


def _expand(text: str) -> list[int]:
    out = []

    for part in text.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))

    return out


def counts_from_tables(cs: DbcTable, cfhs: DbcTable, commit: str) -> dict:
    """The package's rows of races 1-11 as numbers (the last row of a repeated key, as customize keeps)."""
    last = {}

    for row in cs.rows:
        race = cs.get(row, "raceID")

        if race in ap.TAKEN_RACES:
            key = (race, cs.get(row, "sexID"), cs.get(row, "baseSection"), cs.get(row, "variationIndex"),
                   cs.get(row, "colorIndex"))
            last[key] = cs.get(row, "flags")

    rows: dict[str, dict[str, list]] = {}
    groups: dict[tuple, list[int]] = {}

    for (race, sex, section, variation, colour), flags in last.items():
        groups.setdefault((race, sex, section, variation, flags), []).append(colour)

    for (race, sex, section, variation, flags), colours in sorted(groups.items()):
        rows.setdefault(f"{race},{sex}", {}).setdefault(str(section), []).append([variation, flags, _ranges(colours)])

    bases = Counter((cfhs.get(r, "raceID"), cfhs.get(r, "sexID")) for r in cfhs.rows)
    return {
        "_readme": "Numbers only, from the pinned Ascension Character Customization package's CharSections and "
                   "CharacterFacialHairStyles (races 1-11; a repeated key keeps its last row): per race,sex and "
                   "section, [variation, flags, colour ranges]; features: B per race,sex. Made by raceforge.py "
                   "picker-data --package; read by picker-data and its --check. No art, no names.",
        "version": COUNTS_VERSION,
        "package": commit,
        "features": {f"{r},{s}": n for (r, s), n in sorted(bases.items()) if r in ap.TAKEN_RACES},
        "rows": rows,
    }


def counts_text(counts: dict) -> str:
    """JSON with one row group per line (stable, diff-friendly)."""
    lines = ["{"]
    lines.append(f'  "_readme": {json.dumps(counts["_readme"])},')
    lines.append(f'  "version": {counts["version"]},')
    lines.append(f'  "package": {json.dumps(counts["package"])},')
    lines.append(f'  "features": {json.dumps(counts["features"], separators=(", ", ": "))},')
    lines.append('  "rows": {')
    keys = list(counts["rows"])

    for i, key in enumerate(keys):
        lines.append(f'    "{key}": {{')
        sections = list(counts["rows"][key])

        for j, section in enumerate(sections):
            items = counts["rows"][key][section]
            body = ", ".join(json.dumps(item, separators=(",", ":")) for item in items)
            lines.append(f'      "{section}": [{body}]' + ("," if j + 1 < len(sections) else ""))

        lines.append("    }" + ("," if i + 1 < len(keys) else ""))

    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def load_counts(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise PickerError(f"{path} is missing: make it with raceforge.py picker-data --package <the package>") from None
    except json.JSONDecodeError as e:
        raise PickerError(f"{path}: not valid JSON ({e})") from None

    if not isinstance(data, dict) or data.get("version") != COUNTS_VERSION or not isinstance(data.get("rows"), dict):
        raise PickerError(f"{path}: not a package_counts.json of version {COUNTS_VERSION}")

    return data


def tables_from_counts(counts: dict) -> tuple[DbcTable, DbcTable]:
    """A CharSections (no texture names) and a CharacterFacialHairStyles (B rows, no geosets) from the numbers."""
    cs = DbcTable.empty(schema_access.get("CharSections"))
    cfhs = DbcTable.empty(schema_access.get("CharacterFacialHairStyles"))
    next_id = 1

    for key, sections in counts["rows"].items():
        race, sex = map(int, key.split(","))

        for section, items in sections.items():
            for variation, flags, colours in items:
                for colour in _expand(colours):
                    row = [0] * len(cs.schema.columns)
                    row[0] = next_id
                    next_id += 1
                    cs.set(row, "raceID", race)
                    cs.set(row, "sexID", sex)
                    cs.set(row, "baseSection", int(section))
                    cs.set(row, "variationIndex", variation)
                    cs.set(row, "colorIndex", colour)
                    cs.set(row, "flags", flags)
                    cs.rows.append(row)

    for key, b in counts["features"].items():
        race, sex = map(int, key.split(","))

        for value in range(b):
            row = [0] * len(cfhs.schema.columns)
            cfhs.set(row, "raceID", race)
            cfhs.set(row, "sexID", sex)
            cfhs.set(row, "variationID", value)
            cfhs.rows.append(row)

    return cs, cfhs


def stage_two(counts: dict, cur: curmod.Curation, catalogue: marksrows.Catalogue,
              with_marks: bool = True) -> tuple[DbcTable, DbcTable]:
    """The tables customize makes in stage 2 (rows only): curation, clones, race filters, marks and eyes."""
    cs, cfhs = tables_from_counts(counts)
    race_ids = {name: rid for rid, name in ap.RACE_FILES.items()}
    curmod.hide(cs, cur, race_ids, set(ap.TAKEN_RACES))

    for clone, source in sorted(ap.CLONES.items()):
        cs.rows += [_with_race(cs, r, clone) for r in cs.rows if cs.get(r, "raceID") == source]
        cfhs.rows += [_with_race(cfhs, r, clone) for r in cfhs.rows if cfhs.get(r, "raceID") == source]

    curmod.filter_races(cs, cur, race_ids)

    if with_marks:
        manifest = marksrows.full_manifest(catalogue)

        for (race_file, sex), entry in sorted(manifest.entries.items()):
            race = race_ids[race_file]
            b = marksrows.base_count(cfhs, race, sex)

            if b:
                marksrows.add_marks(cs, cfhs, race, sex, b, entry.looks)

            marksrows.add_eyes(cs, race, sex, entry.eyes)

    cs.rows.sort(key=lambda r: tuple(cs.get(r, c) for c in ap.KEY))
    return cs, cfhs


def _with_race(table: DbcTable, row: list[int], race: int) -> list[int]:
    new = list(row)
    table.set(new, "raceID", race)
    return new


# --- the client's lists ----------------------------------------------------------------------------------------


def _count(values: dict[int, int]) -> int | dict:
    """A number when every value is the same, else {default = most common, [key] = other}."""
    if not values:
        return 0

    common = Counter(values.values()).most_common()
    default = max(common, key=lambda kv: (kv[1], kv[0]))[0]

    if len(common) == 1:
        return default

    out: dict = {"default": default}
    out.update({k: v for k, v in sorted(values.items()) if v != default})
    return out


def group_rows(cs: DbcTable) -> dict[tuple[int, int], dict[tuple[int, int, int], int]]:
    """(race, sex) -> {(section, variation, colour): flags}, the last row of each key."""
    out: dict[tuple[int, int], dict[tuple[int, int, int], int]] = {}
    race_c, sex_c, sec_c, var_c, col_c, flags_c = (cs.col(c) for c in ("raceID", "sexID", "baseSection",
                                                                      "variationIndex", "colorIndex", "flags"))

    for row in cs.rows:
        out.setdefault((row[race_c], row[sex_c]), {})[(row[sec_c], row[var_c], row[col_c])] = row[flags_c]

    return out


class Walk:
    """The skin and face arrows of one race, sex and flag rule (creation or the barbershop, Death Knight or not) on
    the client's option tables (WoW/Common/BleakholdCustomize.h, whose SkinFits and FaceFits copy
    CharacterComponent.cpp's SetNextSkin and SetNextFace).

    The tables as BuildComponentArray (ComponentUtils.cpp) makes them: a section's variations run to its highest
    variation and a variation's colours to its highest colour index, every row counting whatever its flags; a repeated
    key keeps its last row (rows: group_rows()). Both screens modelled here check the underwear row (only
    COMPONENT_CONTEXT_2, in the world, skips it)."""

    def __init__(self, rows: dict[tuple[int, int, int], int], where: str, dk: bool):
        self.rows, self.where, self.dk = rows, where, dk
        self.colours: dict[tuple[int, int], int] = {}
        self.variations: dict[int, int] = {}

        for section, variation, colour in rows:
            self.colours[(section, variation)] = max(self.colours.get((section, variation), 0), colour + 1)
            self.variations[section] = max(self.variations.get(section, 0), variation + 1)

        self._fits: dict[int, frozenset[int]] = {}
        self._from: dict[tuple[int, frozenset[int]], tuple[bool, ...]] = {}

    def num_colours(self, section: int, variation: int) -> int:
        return self.colours.get((section, variation), 0)

    def num_variations(self, section: int) -> int:
        return self.variations.get(section, 0)

    def ok(self, section: int, variation: int, colour: int) -> bool:
        flags = self.rows.get((section, variation, colour))
        return flags is not None and ap.selectable(flags, self.where, self.dk)

    def fits(self, face: int) -> frozenset[int]:
        """The skins with which face fits: SkinFits with that face (skin, face and underwear rows all selectable)."""
        if face not in self._fits:
            self._fits[face] = frozenset(s for s in range(self.num_colours(ap.FACE, face))
                                         if self.ok(ap.FACE, face, s) and self.ok(ap.SKIN, 0, s)
                                         and self.ok(ap.UNDERWEAR, 0, s))

        return self._fits[face]

    def face_fits(self, face: int, offset: int) -> bool:
        """FaceFits: SetNextFace's inner loop for face, which starts at colour offset (the glue passes
        m_prevSkinIndex, the last skin chosen with the skin row, the barbershop 0) and visits skin i + offset (mod the
        face's colour count), then i = that skin + 1, until i reaches the count. From offset 0 it visits every skin;
        from others it can visit a few only."""
        n = self.num_colours(ap.FACE, face)

        if n <= 0:
            return False

        fits = self.fits(face)
        key = (n, fits)

        if key not in self._from:
            reach = []

            for start in range(n):
                i, found = 0, False

                # the loop always ends: the skins it visits step by start + 1 (mod n) from start and so reach n - 1
                while i < n:
                    skin = (i + start) % n

                    if skin in fits:
                        found = True
                        break

                    i = skin + 1

                reach.append(found)

            self._from[key] = tuple(reach)

        return self._from[key][offset % n]

    def face_walk(self, offset: int) -> tuple[int, ...]:
        """The raw faces the face arrows reach when their loop starts at skin offset (List(ROW_FACE)), ascending."""
        return tuple(f for f in range(self.num_variations(ap.FACE)) if self.face_fits(f, offset))

    def skin_walk(self, face: int, keep=None) -> tuple[int, ...]:
        """The raw skins the skin arrows reach with face (List(ROW_SKIN)), ascending; keep(skin) filters them (the
        barbershop steps only onto skins with a BarberShopStyle row)."""
        fits = self.fits(face)
        return tuple(s for s in range(self.num_colours(ap.SKIN, 0)) if s in fits and (keep is None or keep(s)))


def _sets(values: dict[int, tuple[int, ...]]) -> tuple[list[list[int]], int | dict]:
    """The distinct non-empty lists (in the order of their first key) and the 1-based list of each key, as a count
    (_count: the most common list as the default)."""
    sets: list[list[int]] = []
    of: dict[int, int] = {}

    for key, value in sorted(values.items()):
        if not value:
            continue

        if list(value) not in sets:
            sets.append(list(value))

        of[key] = sets.index(list(value)) + 1

    return sets, _count(of)


def barber_skin_row(rows: dict[tuple[int, int, int], int], skin: int) -> bool:
    """Whether customize gives this skin a BarberShopStyle row (type 3): every skin a player or Death Knight can pick in
    the world (realm_customize.merge_barber)."""
    flags = rows.get((ap.SKIN, 0, skin))
    return flags is not None and ap.anyone(flags, ap.WORLD)


def lists(cs: DbcTable, cfhs: DbcTable, race: int, sex: int, dk: bool, where: str, grouped=None) -> dict:
    """One view's lists (README.md, "Picker data"): skins (every skin the skin arrows reach with some face),
    skinSets / skinSetOfFace (the skin walk with each face; at the barbershop only skins with a BarberShopStyle row),
    hairStyles, hairColors, features and, for creation, faceWalks / faceWalkOfSkin (the face walk from each start
    skin)."""
    rows = (grouped if grouped is not None else group_rows(cs)).get((race, sex), {})

    def ok(key) -> bool:
        return key in rows and ap.selectable(rows[key], where, dk)

    walk = Walk(rows, where, dk)
    keep = (lambda skin: barber_skin_row(rows, skin)) if where == ap.WORLD else None
    skin_sets, skin_set_of_face = _sets({f: walk.skin_walk(f, keep) for f in range(walk.num_variations(ap.FACE))})
    skins = sorted({s for skin_set in skin_sets for s in skin_set})

    hair_colours = sorted({c for (s, v, c) in rows if s == ap.HAIR})
    hair_styles = sorted({v for (s, v, c) in rows if s == ap.HAIR})
    styles_at = {c: sum(1 for v in hair_styles if ok((ap.HAIR, v, c))) for c in hair_colours}
    styles_at = {c: n for c, n in styles_at.items() if n}
    colours_of = {v: sum(1 for c in hair_colours if ok((ap.HAIR, v, c))) for v in hair_styles}
    colours_of = {v: n for v, n in colours_of.items() if n}
    b_total = sum(1 for r in cfhs.rows if cfhs.get(r, "raceID") == race and cfhs.get(r, "sexID") == sex)
    has_features = any(s == ap.FEATURES for (s, v, c) in rows)

    if has_features:
        features = {c: sum(1 for (s, v, cc) in rows if s == ap.FEATURES and cc == c and ok((s, v, cc)))
                    for c in styles_at}
    else:
        features = {c: b_total for c in styles_at}

    out = {"skins": skins, "hairStyles": _count(styles_at), "hairColors": _count(colours_of),
           "features": _count(features), "skinSets": skin_sets, "skinSetOfFace": skin_set_of_face}

    if where == ap.CREATION:
        walks, walk_of_skin = _sets({s: walk.face_walk(s) for s in range(walk.num_colours(ap.SKIN, 0))})
        out["faceWalks"] = walks
        out["faceWalkOfSkin"] = walk_of_skin

    return out


def model(counts: dict, cur: curmod.Curation, catalogue: marksrows.Catalogue, where: str, staged=None) -> dict:
    cs, cfhs = staged if staged is not None else stage_two(counts, cur, catalogue)
    grouped = group_rows(cs)
    base_cs, base_cfhs = tables_from_counts(counts)
    races = {}

    for race in sorted(set(ap.TAKEN_RACES) | set(ap.CLONES)):
        race_file = ap.RACE_FILES[race]
        cat = catalogue.races[race_file]
        source = ap.CLONES.get(race, race)
        per_sex = {}

        for sex in ap.SEXES:
            b = marksrows.base_count(base_cfhs, source, sex)
            groups = {}

            for (section, variation, colour), flags in sorted(grouped.get((race, sex), {}).items()):
                if section == ap.SKIN and variation == 0 and ap.anyone(flags, where):
                    groups[colour] = curmod.GROUP_CODES[cur.group(race_file, sex, colour, flags)]

            per_sex[sex] = {
                "B": b,
                "looks": ap.LOOKS + 1 if b else 1,
                "designs": [d.name for d in cat.designs],
                "colours": [c.name for c in cat.colours],
                "colourGlows": [c.glow for c in cat.colours],
                "eyes": catalogue.eye_names(race_file),
                "skinGroup": dict(sorted(groups.items())),
                "normal": lists(cs, cfhs, race, sex, False, where, grouped),
                "deathKnight": lists(cs, cfhs, race, sex, True, where, grouped),
            }

        races[race_file] = per_sex

    return races


# --- Lua -------------------------------------------------------------------------------------------------------


WIDTH = 120  # the repository's line limit (.editorconfig)


def _lua_key(k) -> str:
    if isinstance(k, int):
        return f"[{k}]"

    return k if k.isidentifier() else f'["{k}"]'


def _lua_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    raise PickerError(f"cannot write {value!r} as Lua")


def lua_value(value, indent: int, prefix_len: int = 0) -> str:
    """value as Lua; flat tables on one line when they fit WIDTH (with prefix_len characters before them), else their
    items packed onto as few lines as fit, one level deeper."""
    pad = " " * indent

    if not isinstance(value, (list, dict)):
        return _lua_scalar(value)

    if not value:
        return "{}"

    items = list(value.items()) if isinstance(value, dict) else [(None, v) for v in value]
    flat = all(not isinstance(v, (list, dict)) for _, v in items)

    def item(k, v, at: int) -> str:
        head = "" if k is None else f"{_lua_key(k)} = "
        return head + lua_value(v, at, at + len(head))

    if flat:
        parts = [item(k, v, 0) for k, v in items]
        one = "{ " + ", ".join(parts) + " }"

        if indent + prefix_len + len(one) <= WIDTH:
            return one

        lines, line = [], ""
        inner = pad + "    "

        for part in parts:
            candidate = f"{line} {part}," if line else f"{inner}{part},"

            if len(candidate) > WIDTH and line:
                lines.append(line)
                candidate = f"{inner}{part},"

            line = candidate

        lines.append(line)
        return "{\n" + "\n".join(lines) + "\n" + pad + "}"

    inner = " " * (indent + 4)
    body = ",\n".join(inner + item(k, v, indent + 4) for k, v in items)
    return "{\n" + body + ",\n" + pad + "}"


HEADER = """-- {title}.
-- Generated by Tools/RaceForge/raceforge.py picker-data from customize/curation.json, customize/catalogue.json and
-- customize/package_counts.json (numbers of the pinned package, no art); do not edit. The schema is
-- Tools/RaceForge/README.md, "Bleakhold appearance data contract", "Picker data".
"""


def render(counts: dict, cur: curmod.Curation, catalogue: marksrows.Catalogue, which: str, staged=None) -> str:
    where = ap.CREATION if which == "glue" else ap.WORLD
    races = model(counts, cur, catalogue, where, staged)

    if which == "barber":
        # the barbershop cannot read the face: its hook matches the skin walk against every list of skinSets
        for per_sex in races.values():
            for block in per_sex.values():
                for kind in ("normal", "deathKnight"):
                    block[kind].pop("skinSetOfFace", None)

    data = {
        "version": DATA_VERSION,
        "package": str(counts.get("package", ""))[:12],
        "eyeStride": ap.EYE_STRIDE,
        "looksPerDesign": ap.COLOURS,
        "groups": list(curmod.GROUPS),
        "races": races,
    }

    if which == "glue":
        return HEADER.format(title="Bleakhold glue: the character picker's numbers") + \
            "BleakholdCustomizeData = " + lua_value(data, 0, len("BleakholdCustomizeData = ")) + "\n"

    return HEADER.format(title="Bleakhold: the barbershop hook's numbers") + \
        "local ADDON, ns = ...\n\nns.BarberData = " + lua_value(data, 0, len("ns.BarberData = ")) + "\n"


def outputs(repo_root: str, counts: dict, cur: curmod.Curation, catalogue: marksrows.Catalogue) -> dict[str, str]:
    staged = stage_two(counts, cur, catalogue)
    return {os.path.join(repo_root, GLUE_FILE): render(counts, cur, catalogue, "glue", staged),
            os.path.join(repo_root, BARBER_FILE): render(counts, cur, catalogue, "barber", staged)}


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()
