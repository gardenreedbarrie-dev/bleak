r"""raceforge.py customize: the Ascension Character Customization package on the Bleakhold realm, for races 1-11 and
their clones High Elf (15) and Eredar (19) (README.md, "The realm's appearance options" and "Bleakhold appearance data
contract").

The tables (merge(), no file access):

- CharSections, CharHairGeosets, CharacterFacialHairStyles, BarberShopStyle and HelmetGeosetVisData start from the
  saved base, the realm's copies from before the package (Base: /root/wowdata/customize-base/), so every run starts
  from the same place;
- the package's rows of races 1-11 replace the realm's (its rows of 12-21, Skeleton 15 and Taunka 19 among them, are
  never taken); a key the package repeats keeps its last row (the one the client uses);
- every package texture a row names is renamed to Character\Ascension\<its path>, which nothing else holds;
- the curation hides rows (curation.hide()), races 10 and 11 are copied to 15 and 19, then the race filters run;
- with a marks manifest, the mark rows (features) and eye rows (faces) are added (rflib/marksrows.py);
- HelmetGeosetVisData: the package's bits of races 1-11 by id, the realm's other bits, then bit 15 = bit 10 and
  bit 19 = bit 11;
- BarberShopStyle: hair and features rows of every race (clones included), a skin row for every skin a player or
  Death Knight can pick in the world, and a features row per mark value; ids from the ledger (BarberLedger), the
  server's price factors in costModifier;
- the gates: one row per CharSections key and the table sorted, every value at most 255, every features value at every
  hair colour players can pick, faces below 40, no third texture in the package's face and features rows, 15 and 19
  the copies of 10 and 11.

The realm (run()): the tables are forged for every combination of the launcher's packs into the archive the client
reads each from (a base archive's table goes into archives.own); the package's textures go into patch-6 (and patch-7),
its models into patch-~, the marks into patch-K; missing textures are rebuilt from the nearest one of the same style
(or their rows hidden); every texture a row names must paste at levels 7-9 and resolve, in every combination, to the
file planned for it; every model must have the geosets its rows need and its own .anim files (rflib/geosets.py).
Nothing is written into the patch folder: the archives go to --out/client with install.json, the server's copies to
--out/server/dbc, the remap of existing characters to --out/server/sql.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import struct
import time
from dataclasses import dataclass, field

from . import appearance as ap
from . import blp, curation as curmod, customize, geosets, install, marksrows, patchnames, recolor, remap, schema_access
from . import update
from .dbc import DbcError, DbcTable, to_signed

patches = update.patch_tools()

import mpqpack  # noqa: E402  (Tools/MpqPack)

MERGED = ("CharSections", "CharHairGeosets", "CharacterFacialHairStyles", "BarberShopStyle", "HelmetGeosetVisData")
# CreatureDisplayInfoExtra is not merged (the package's NPC looks and baked textures are not shipped): its NPC looks
# are only moved to the merged numbers (remap.remap_npcs()).
TABLES = MERGED + ("CreatureDisplayInfoExtra",)
CHECK_TABLES = ("ChrRaces", "CreatureDisplayInfo", "CreatureModelData")
OUT_ENTRIES = ("client", "server", "staging", "merged", "report.txt", "install.json", "summary.json")
# The server's price factors (Player::GetBarberShopCost): hair 1.0, facial hair 0.75, skin 0.75.
COST = {0: 1.0, 2: 0.75, 3: 0.75}
BARBER_TYPES = {0: "hair", 2: "features", 3: "skin"}
PACKAGE_ROWS_LIMIT = 20000  # a CharSections with more rows than this, and no Character\Ascension\ name, is the package
MARKER_FOLDER = "Bleakhold\\"  # files of our own archives the client never reads
SKIP_PACKAGE_FOLDERS = ("goblin", "goblinold", "naga_", "naga")
DEFAULT_ART = ("patch-6.MPQ", "patch-7.MPQ")
MODELS_ARCHIVE = "patch-~.MPQ"
MARKS_ARCHIVE = "patch-K.MPQ"
MOVED_ART_ARCHIVE = "patch-O.MPQ"
DEFAULT_ART_MAX_MB = 3500
TAKEN_PATCHES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), patchnames.TAKEN_FILE)


class CustomizeError(Exception):
    pass


def dbc_path(name: str) -> str:
    return "DBFilesClient\\" + os.path.basename(schema_access.get(name).filename.replace("\\", "/"))


# --- the barbershop id ledger ----------------------------------------------------------------------------------


@dataclass
class BarberLedger:
    """barber_ids.json: "race,sex,type,data" -> id, never given to another key; B per race and sex once marks exist."""
    ids: dict[str, int] = field(default_factory=dict)
    bases: dict[str, int] = field(default_factory=dict)  # "race,sex" -> B of a race-sex with marks
    path: str = ""
    added: list[str] = field(default_factory=list)

    @staticmethod
    def key(race: int, sex: int, kind: int, data: int) -> str:
        return f"{race},{sex},{kind},{data}"

    @classmethod
    def load(cls, path: str) -> "BarberLedger":
        if not os.path.exists(path):
            return cls(path=path)

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise CustomizeError(f"{path}: cannot be read ({e})") from None

        ids = data.get("ids") if isinstance(data, dict) else None

        if not isinstance(ids, dict) or not all(isinstance(v, int) and v > 0 for v in ids.values()):
            raise CustomizeError(f"{path}: not a barber id ledger")

        if len(set(ids.values())) != len(ids):
            raise CustomizeError(f"{path}: an id is given to two keys")

        return cls(dict(ids), dict(data.get("bases") or {}), path)

    def assign(self, keys: list[str], realm: dict[str, int], reserved: set[int]) -> dict[str, int]:
        """The id of every key: the realm's own (pre-package) id, else the ledger's, else a new one above every id in
        use, in key order. realm: every key of the realm's own table with its id (races 1-11, 15 and 19); reserved:
        the ids of the table's other rows (other races, kept as they are), which no key may take."""
        holders = {v: k for k, v in self.ids.items()}

        for key, value in sorted(realm.items()):
            if key in self.ids and self.ids[key] != value:
                raise CustomizeError(f"barber ledger: {key} is id {self.ids[key]} in the ledger but {value} in the "
                                     "realm's table")

            owner = holders.get(value)

            if owner is not None and owner != key:
                raise CustomizeError(f"barber ledger: the realm's id {value} ({key}) is {owner} in the ledger")

        out = {}

        for key in keys:
            if key in realm:
                out[key] = realm[key]

                if key not in self.ids:
                    self.ids[key] = realm[key]
            elif key in self.ids:
                out[key] = self.ids[key]

        for key, value in sorted(out.items()):
            if value in reserved:
                raise CustomizeError(f"barber ledger: id {value} ({key}) is held by another race's row in the realm's "
                                     "table")

        next_id = max(set(self.ids.values()) | set(realm.values()) | set(reserved), default=0) + 1

        for key in sorted(k for k in keys if k not in out):
            out[key] = self.ids[key] = next_id
            self.added.append(key)
            next_id += 1

        return out

    def check_bases(self, bases: dict[tuple[int, int], int]):
        for (race, sex), b in bases.items():
            old = self.bases.get(f"{race},{sex}")

            if old is not None and old != b:
                raise CustomizeError(f"race {race} sex {sex}: {b} base features now, {old} when its marks went live; "
                                     "the features byte (look x B + base) would mean other looks. Keep the package")

            self.bases[f"{race},{sex}"] = b

    def save(self, path: str | None = None):
        path = path or self.path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        install.write_json(path, {
            "_readme": "raceforge.py customize: the id of every BarberShopStyle key (race, sex, type, data), never "
                       "given to another key, and B (base features) of every race and sex with marks. Keep it with "
                       "the saved base; never edit it.",
            "ids": dict(sorted(self.ids.items(), key=lambda kv: kv[1])),
            "bases": dict(sorted(self.bases.items())),
        })


# --- the merge -------------------------------------------------------------------------------------------------


@dataclass
class Merged:
    tables: dict[str, DbcTable]
    notes: list[str] = field(default_factory=list)
    hidden: list[curmod.HiddenRow] = field(default_factory=list)
    duplicates: int = 0
    bases: dict[tuple[int, int], int] = field(default_factory=dict)  # B of the race-sexes that got marks
    marks_added: dict[tuple[int, int], marksrows.Added] = field(default_factory=dict)
    barber_added: list[str] = field(default_factory=list)
    barber_dropped: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # found while merging (gates() adds the rest)


def _copy(source: DbcTable, target: DbcTable, row: list[int]) -> list[int]:
    return customize.copy_row(source, target, row)


def _key(cs: DbcTable, row: list[int]) -> tuple:
    return tuple(to_signed(cs.get(row, c)) for c in ap.KEY)


def dedupe(cs: DbcTable) -> int:
    """Keep the last row of every key (BuildComponentArray keeps the last one). Returns the rows dropped."""
    last = {}

    for i, row in enumerate(cs.rows):
        last[_key(cs, row)] = i

    keep = sorted(last.values())
    dropped = len(cs.rows) - len(keep)
    cs.rows = [cs.rows[i] for i in keep]
    return dropped


def number(table: DbcTable, kept_ids: set[int]):
    """Ids for the rows that have none (0) or one in use: after every id, in row order."""
    used = set(kept_ids)
    next_id = max((to_signed(r[0]) for r in table.rows), default=0) + 1

    for row in table.rows:
        row_id = to_signed(row[0])

        if row_id <= 0 or row_id in used:
            table.set(row, "id", next_id)
            used.add(next_id)
            next_id += 1
        else:
            used.add(row_id)


def sort_sections(cs: DbcTable):
    cs.rows.sort(key=lambda r: _key(cs, r))


def section_problems(cs: DbcTable) -> list[str]:
    keys = [_key(cs, r) for r in cs.rows]
    problems = []

    if any(keys[i] > keys[i + 1] for i in range(len(keys) - 1)):
        problems.append("CharSections is not sorted by (race, sex, section, variation, colour)")

    if len(set(keys)) != len(keys):
        problems.append(f"CharSections has {len(keys) - len(set(keys))} repeated key(s)")

    ids = [to_signed(r[0]) for r in cs.rows]

    if len(set(ids)) != len(ids):
        problems.append("CharSections has repeated ids")

    for row in cs.rows:
        for column in ("variationIndex", "colorIndex"):
            if cs.get(row, column) > ap.MAX_VALUE:
                problems.append(f"CharSections row {row[0]}: {column} {cs.get(row, column)} is above 255")
                break

    return problems


class Renamer:
    r"""Package textures to Character\Ascension\<path>: the package's files by name key."""

    def __init__(self, files: dict[str, tuple[str, str, int]]):
        self.files = files  # name key -> (spelling, path on disk, size)

    def __call__(self, name: str) -> str:
        if not name:
            return name

        original = ap.original_name(name)
        return ap.ascension_name(original) if ap.name_key(original) in self.files else name


def merge(base: dict[str, DbcTable], package: dict[str, DbcTable], cur: curmod.Curation, ledger: BarberLedger,
          rename=None, marks: marksrows.Manifest | None = None, catalogue: marksrows.Catalogue | None = None,
          fixup=None) -> Merged:
    """The five tables of one pack combination (base: the saved copies; package: the package's tables). fixup(cs, out),
    if given, runs on CharSections after the clones and filters, before the marks (the missing textures)."""
    rename = rename or (lambda n: n)
    race_ids = {name: rid for rid, name in ap.RACE_FILES.items()}
    replaced = set(ap.TAKEN_RACES) | set(ap.CLONES)
    out = Merged({})

    for name in TABLES:
        if name not in base:
            raise CustomizeError(f"no {name}.dbc in the saved base")

    for name in MERGED:
        if name not in package:
            raise CustomizeError(f"the package has no {name}.dbc")

    # CharSections: the realm's rows of other races, then the package's rows of races 1-11 (last of each key).
    b_cs, p_cs = base["CharSections"], package["CharSections"]
    cs = DbcTable(b_cs.schema, [], bytes(b_cs.strings), b_cs.source)
    kept = [list(r) for r in b_cs.rows if b_cs.get(r, "raceID") not in replaced]
    kept_ids = {to_signed(r[0]) for r in kept}
    cs.rows.extend(kept)
    pkg = DbcTable(p_cs.schema, [list(r) for r in p_cs.rows if p_cs.get(r, "raceID") in ap.TAKEN_RACES],
                   bytes(p_cs.strings), p_cs.source)
    out.duplicates = dedupe(pkg)
    dropped_races = sorted({p_cs.get(r, "raceID") for r in p_cs.rows} - set(ap.TAKEN_RACES))
    out.notes.append(f"CharSections: {len(pkg.rows)} package rows of races 1-11 ({out.duplicates} repeated rows "
                     f"dropped, the last kept); package rows of races {dropped_races} left out; {len(kept)} rows of "
                     "the realm's other races kept")

    for slot_check in pkg.rows:
        if pkg.get(slot_check, "baseSection") in (ap.FACE, ap.FEATURES) and pkg.get_str(slot_check, "textureName[2]"):
            raise CustomizeError(f"package CharSections row {slot_check[0]} (section {pkg.get(slot_check, 'baseSection')}) "
                                 "has a third texture; the contract gives it a meaning of its own (marks, eyes)")

    top_face = max((pkg.get(r, "variationIndex") for r in pkg.rows if pkg.get(r, "baseSection") == ap.FACE), default=0)

    if top_face >= ap.EYE_STRIDE:
        raise CustomizeError(f"the package has face variation {top_face}; the face byte keeps 0-{ap.EYE_STRIDE - 1} for "
                             "faces (face = base + 40 x eye)")

    for row in pkg.rows:
        new = _copy(pkg, cs, row)

        for slot in range(3):
            column = f"textureName[{slot}]"
            text = cs.get_str(new, column)

            if text and rename(text) != text:
                cs.set_str(new, column, rename(text))

        cs.rows.append(new)

    out.hidden += curmod.hide(cs, cur, race_ids, set(ap.TAKEN_RACES))

    for clone, source in sorted(ap.CLONES.items()):
        copies = []

        for row in cs.rows:
            if cs.get(row, "raceID") == source:
                new = list(row)
                cs.set(new, "raceID", clone)
                cs.set(new, "id", 0)
                copies.append(new)

        cs.rows.extend(copies)
        out.notes.append(f"CharSections: race {clone} = the {len(copies)} rows of race {source}")

    out.hidden += curmod.filter_races(cs, cur, race_ids)

    if fixup is not None:
        fixup(cs, out)

    out.problems += clone_problems(cs)

    # CharacterFacialHairStyles (no ids) and CharHairGeosets: the realm's other races, the package's 1-11, the clones.
    tables = {"CharSections": cs}

    for name, race_col, key_cols in (("CharHairGeosets", "raceID", ("raceID", "sexID", "variationID")),
                                     ("CharacterFacialHairStyles", "raceID", ("raceID", "sexID", "variationID"))):
        b_t, p_t = base[name], package[name]
        table = DbcTable(b_t.schema, [list(r) for r in b_t.rows if b_t.get(r, race_col) not in replaced],
                         bytes(b_t.strings), b_t.source)
        own_ids = {to_signed(r[0]) for r in table.rows} if not table.schema.generated_id else set()
        rows = [_copy(p_t, table, r) for r in p_t.rows if p_t.get(r, race_col) in ap.TAKEN_RACES]

        for clone, source in sorted(ap.CLONES.items()):
            for row in [r for r in rows if table.get(r, race_col) == source]:
                new = list(row)
                table.set(new, race_col, clone)

                if not table.schema.generated_id:
                    table.set(new, "id", 0)

                rows.append(new)

        if not table.schema.generated_id:
            # a package id that a kept realm row has gets a new one; the clones get new ones
            for row in rows:
                if to_signed(row[0]) in own_ids:
                    table.set(row, "id", 0)

        table.rows.extend(rows)
        table.rows.sort(key=lambda r: tuple(to_signed(table.get(r, c)) for c in key_cols))

        if not table.schema.generated_id:
            number(table, set())

        seen = [tuple(table.get(r, c) for c in key_cols) for r in table.rows]

        if len(set(seen)) != len(seen):
            out.notes.append(f"{name}: {len(seen) - len(set(seen))} repeated (race, sex, variation) row(s) (as the "
                             "package has them)")

        tables[name] = table

    cfhs = tables["CharacterFacialHairStyles"]

    # marks and eyes
    if marks is not None:
        for (race_file, sex), entry in sorted(marks.entries.items()):
            race = race_ids[race_file]
            b = marksrows.base_count(cfhs, race, sex)

            if entry.looks:
                added = marksrows.add_marks(cs, cfhs, race, sex, b, entry.looks)
                out.bases[(race, sex)] = b
            else:
                added = marksrows.Added()

            eyes = marksrows.add_eyes(cs, race, sex, entry.eyes)
            added.eye_rows = eyes.eye_rows
            out.marks_added[(race, sex)] = added

        cfhs.rows.sort(key=lambda r: (cfhs.get(r, "raceID"), cfhs.get(r, "sexID"), cfhs.get(r, "variationID")))

    sort_sections(cs)
    number(cs, kept_ids)

    # HelmetGeosetVisData
    tables["HelmetGeosetVisData"] = merge_helmets(base["HelmetGeosetVisData"], package["HelmetGeosetVisData"], out)

    # BarberShopStyle
    tables["BarberShopStyle"] = merge_barber(base["BarberShopStyle"], package["BarberShopStyle"], cs, cfhs, ledger,
                                             out, marks, catalogue)

    # the NPC looks on the merged numbers
    tables["CreatureDisplayInfoExtra"], moved = remap.remap_npcs(base["CreatureDisplayInfoExtra"], b_cs, cs)
    out.notes.append(f"CreatureDisplayInfoExtra: {moved} NPC look(s) moved to the merged skin, face and hair colour "
                     "numbers (the table is not merged)")
    out.tables = tables
    return out


HELMET_COLUMNS = tuple(f"hideGeoset[{i}]" for i in range(7))
PACKAGE_BITS = sum(1 << r for r in ap.TAKEN_RACES)
CLONE_BITS = sum(1 << r for r in ap.CLONES)


def merge_helmets(base: DbcTable, package: DbcTable, out: Merged) -> DbcTable:
    table = DbcTable(base.schema, [], bytes(base.strings), base.source)
    b_rows, p_rows = base.by_id(), package.by_id()
    realm_bits = 0xFFFFFFFF & ~(PACKAGE_BITS | CLONE_BITS)
    changed = 0

    for row_id in sorted(set(b_rows) | set(p_rows)):
        b, p = b_rows.get(row_id), p_rows.get(row_id)
        row = list(b if b is not None else p)

        for column in HELMET_COLUMNS:
            pv = package.get(p, column) if p is not None else None
            bv = base.get(b, column) if b is not None else None
            value = (pv if pv is not None else bv) & PACKAGE_BITS
            # the realm's bits of every other race (Pandaren 20 and 21 among them); a new id: the package's, but not
            # for the slots the realm uses for its own races (15, 19, 20, 21)
            value |= (bv & realm_bits) if bv is not None else (pv & realm_bits & ~((1 << 20) | (1 << 21)))

            for clone, source in ap.CLONES.items():
                if value & (1 << source):
                    value |= 1 << clone
                else:
                    value &= ~(1 << clone)

            table.set(row, column, value)

        if b is None or row != list(b):
            changed += 1

        table.rows.append(row)

    out.notes.append(f"HelmetGeosetVisData: {len(table.rows)} rows, {changed} changed (races 1-11 from the package, "
                     "bit 15 = bit 10, bit 19 = bit 11, the realm's other bits kept)")
    return table


def merge_barber(base: DbcTable, package: DbcTable, cs: DbcTable, cfhs: DbcTable, ledger: BarberLedger, out: Merged,
                 marks: marksrows.Manifest | None, catalogue: marksrows.Catalogue | None) -> DbcTable:
    replaced = set(ap.TAKEN_RACES) | set(ap.CLONES)
    table = DbcTable(base.schema, [], bytes(base.strings), base.source)
    realm: dict[str, int] = {}
    others = []

    for row in base.rows:
        key = BarberLedger.key(base.get(row, "race"), base.get(row, "sex"), base.get(row, "type"), base.get(row, "data"))

        if base.get(row, "race") in replaced:
            if key in realm:
                raise CustomizeError(f"the realm's BarberShopStyle has {key} twice (ids {realm[key]} and {row[0]})")

            realm[key] = to_signed(row[0])
        else:
            others.append(list(row))

    template = next((r for r in package.rows if package.get(r, "type") == 0), None)

    if template is None:
        raise CustomizeError("the package's BarberShopStyle has no hair row to copy the layout of")

    wanted: dict[str, list[int]] = {}
    sources = [r for r in package.rows if package.get(r, "race") in ap.TAKEN_RACES]

    for row in sources:
        key = BarberLedger.key(package.get(row, "race"), package.get(row, "sex"), package.get(row, "type"),
                               package.get(row, "data"))
        wanted.setdefault(key, _copy(package, table, row))

    for clone, source in ap.CLONES.items():
        for key, row in list(wanted.items()):
            race, sex, kind, data = map(int, key.split(","))

            if race == source:
                new = list(row)
                table.set(new, "race", clone)
                wanted.setdefault(BarberLedger.key(clone, sex, kind, data), new)

    def named(text: str, race: int, sex: int, kind: int, data: int) -> list[int]:
        row = _copy(package, table, template)
        table.set(row, "type", kind)
        table.set(row, "race", race)
        table.set(row, "sex", sex)
        table.set(row, "data", data)
        table.set_loc(row, "displayName", [text] + [""] * 15)
        table.set_loc(row, "description", [""] * 16)
        return row

    # skin rows: every skin a player or Death Knight can pick in the world, not hidden
    skins: dict[tuple[int, int], list[int]] = {}

    for row in cs.rows:
        race = cs.get(row, "raceID")

        if race in replaced and cs.get(row, "baseSection") == ap.SKIN and cs.get(row, "variationIndex") == 0 \
                and ap.anyone(cs.get(row, "flags"), ap.WORLD):
            skins.setdefault((race, cs.get(row, "sexID")), []).append(cs.get(row, "colorIndex"))

    for (race, sex), colours in sorted(skins.items()):
        for n, colour in enumerate(sorted(set(colours)), 1):
            key = BarberLedger.key(race, sex, 3, colour)

            if key not in wanted:
                wanted[key] = named(f"Skin Color {n}", race, sex, 3, colour)
            elif not table.get_loc(wanted[key], "displayName")[0]:
                # a package skin row without a name (all of its Tauren rows): the barber would show a blank banner
                table.set_loc(wanted[key], "displayName", [f"Skin Color {n}"] + [""] * 15)

    # skin rows of skins nobody can pick any more (a curation hid them): not offered
    for key in [k for k in wanted if k.split(",")[2] == "3"]:
        race, sex, _, colour = map(int, key.split(","))

        if colour not in skins.get((race, sex), []):
            del wanted[key]

    if marks is not None and catalogue is not None:
        race_files = ap.RACE_FILES

        for (race, sex), b in sorted(out.bases.items()):
            cat = catalogue.races[race_files[race]]

            for look in range(1, ap.LOOKS + 1):
                design, colour = ap.design_colour(look)
                text = f"{cat.designs[design - 1].name}, {cat.colours[colour - 1].name}"

                for base_value in range(b):
                    value = ap.features_value(look, base_value, b)
                    wanted.setdefault(BarberLedger.key(race, sex, 2, value), named(text, race, sex, 2, value))

    for key in sorted(set(realm) - set(wanted)):
        out.barber_dropped.append(key)

    ids = ledger.assign(sorted(wanted), realm, {to_signed(r[0]) for r in others})
    rows = others

    for key, row in wanted.items():
        kind = int(key.split(",")[1 + 1])
        table.set(row, "id", ids[key])
        table.set(row, "costModifier", struct.unpack("<I", struct.pack("<f", COST[kind]))[0])
        rows.append(row)

    rows.sort(key=lambda r: to_signed(r[0]))
    table.rows = rows
    out.barber_added = [k for k in ledger.added]
    out.notes.append(f"BarberShopStyle: {len(rows)} rows ({len(wanted)} of races 1-11, 15 and 19; "
                     f"{len(ledger.added)} new id(s); {len(out.barber_dropped)} realm row(s) no longer offered)")
    return table


def gates(merged: Merged) -> list[str]:
    """Problems that stop the run."""
    cs = merged.tables["CharSections"]
    cfhs = merged.tables["CharacterFacialHairStyles"]
    problems = list(merged.problems) + section_problems(cs)
    problems += marksrows.features_problems(cs, cfhs, set(ap.TAKEN_RACES) | set(ap.CLONES))

    for row in cfhs.rows:
        if cfhs.get(row, "variationID") > ap.MAX_VALUE:
            problems.append(f"CharacterFacialHairStyles: value {cfhs.get(row, 'variationID')} is above 255")
            break

    barber = merged.tables["BarberShopStyle"]

    for row in barber.rows:
        if barber.get(row, "data") > ap.MAX_VALUE:
            problems.append(f"BarberShopStyle {row[0]}: data {barber.get(row, 'data')} is above 255")
            break

    # every style of the package's races and the clones has a name: the barber shows it on the step's banner
    replaced = set(ap.TAKEN_RACES) | set(ap.CLONES)
    unnamed = sorted(BarberLedger.key(barber.get(r, "race"), barber.get(r, "sex"), barber.get(r, "type"),
                                      barber.get(r, "data"))
                     for r in barber.rows if barber.get(r, "race") in replaced
                     and not barber.get_loc(r, "displayName")[0])

    if unnamed:
        problems.append(f"BarberShopStyle: {len(unnamed)} row(s) of races 1-11, 15 and 19 have no displayName "
                        f"(race,sex,type,data {', '.join(unnamed[:5])}{', ...' if len(unnamed) > 5 else ''})")

    # the server looks a style up by id, then checks its race and sex: a repeated id loses one of the two styles
    ids = [to_signed(r[0]) for r in barber.rows]

    if len(ids) != len(set(ids)):
        problems.append(f"BarberShopStyle has {len(ids) - len(set(ids))} repeated id(s)")

    return problems


def clone_problems(cs: DbcTable) -> list[str]:
    """15 and 19 are the rows of 10 and 11: the same keys, textures and flags but for the 0x8 of their filters."""
    problems = []
    by_race: dict[int, dict[tuple, tuple]] = {}

    for row in cs.rows:
        race = cs.get(row, "raceID")
        key = (cs.get(row, "sexID"), cs.get(row, "baseSection"), cs.get(row, "variationIndex"),
               cs.get(row, "colorIndex"))
        by_race.setdefault(race, {})[key] = (tuple(cs.get_str(row, f"textureName[{i}]") for i in range(3)),
                                             cs.get(row, "flags") & ~ap.HIDDEN)

    for clone, source in ap.CLONES.items():
        a, b = by_race.get(clone, {}), by_race.get(source, {})

        if a != b:
            diff = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
            problems.append(f"race {clone} is not the copy of race {source}: {len(diff)} row(s) differ, e.g. "
                            f"(sex, section, variation, colour) {sorted(diff)[:3]}")

    return problems


# --- server hashes (README: "Ids") ------------------------------------------------------------------------------


def charsections_hash(cs: DbcTable) -> str:
    digest = hashlib.sha1()

    for row in sorted(cs.rows, key=lambda r: r[0]):
        digest.update(struct.pack("<7I", row[0], cs.get(row, "raceID"), cs.get(row, "sexID"),
                                  cs.get(row, "baseSection"), cs.get(row, "flags"), cs.get(row, "variationIndex"),
                                  cs.get(row, "colorIndex")))

    return digest.hexdigest()


def barber_hash(table: DbcTable) -> str:
    digest = hashlib.sha1()

    for row in sorted(table.rows, key=lambda r: r[0]):
        digest.update(struct.pack("<5I", row[0], table.get(row, "type"), table.get(row, "race"), table.get(row, "sex"),
                                  table.get(row, "data")))

    return digest.hexdigest()


# --- the package on disk ---------------------------------------------------------------------------------------


def package_commit(package_dir: str) -> str | None:
    """The commit of a git checkout (HEAD, its ref, packed-refs), without running git."""
    git = os.path.join(package_dir, ".git")

    if os.path.isfile(git):
        with open(git, encoding="utf-8") as f:
            text = f.read().strip()

        if not text.startswith("gitdir:"):
            return None

        git = os.path.normpath(os.path.join(package_dir, text[7:].strip()))

    try:
        with open(os.path.join(git, "HEAD"), encoding="utf-8") as f:
            head = f.read().strip()
    except OSError:
        return None

    if not head.startswith("ref:"):
        return head.lower() if len(head) == 40 else None

    ref = head[4:].strip()

    for folder in (git, os.path.join(git, "..") if os.path.basename(git) != ".git" else git):
        path = os.path.join(folder, *ref.split("/"))

        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read().strip().lower()

    packed = os.path.join(git, "packed-refs")

    if os.path.isfile(packed):
        with open(packed, encoding="utf-8") as f:
            for line in f:
                parts = line.split()

                if len(parts) == 2 and parts[1] == ref:
                    return parts[0].lower()

    return None


def package_files(package_dir: str) -> dict[str, tuple[str, str, int]]:
    r"""The package's Character\ files of the model races (not Goblin, GoblinOld or Naga), by name key: (archive name,
    path on disk, size). Textures\BakedNPCTextures and the rest are not shipped."""
    char_dir = next((os.path.join(package_dir, e) for e in sorted(os.listdir(package_dir))
                     if e.lower() == "character" and os.path.isdir(os.path.join(package_dir, e))), None)
    out = {}

    if char_dir is None:
        return out

    for root, dirs, files in os.walk(char_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))

        if os.path.normpath(root) == os.path.normpath(char_dir):
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_PACKAGE_FOLDERS]

        for name in sorted(files):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, package_dir).replace(os.sep, "\\")
            key = ap.name_key(rel)

            if key in out:
                raise CustomizeError(f"{rel} and {out[key][0]} are the same file to the client")

            out[key] = (rel, path, os.path.getsize(path))

    return out


def header_info(data: bytes, where: str) -> tuple[int, int, int]:
    """(width, height, levels) from a BLP2 header: what the paste rule needs, without reading the pixels."""
    if len(data) < blp.HEADER.size or data[:4] != b"BLP2":
        raise CustomizeError(f"{where}: not a BLP2 texture")

    _, _, encoding, alpha, preferred, has_mips, width, height, *rest = blp.HEADER.unpack_from(data)
    sizes = rest[16:]
    count = blp.level_count(width, height) if has_mips & 0xF else 1
    levels = 0

    for i in range(min(count, 16)):
        if not sizes[i]:
            break

        levels += 1

    return width, height, levels


def read_head(path: str, n: int = blp.HEADER.size) -> bytes:
    with open(path, "rb") as f:
        return f.read(n)


def sha1_path(path: str) -> str:
    return marksrows.sha1_file(path)


# --- missing textures ------------------------------------------------------------------------------------------


@dataclass
class Rebuilt:
    name: str  # the new name rows get
    original: str
    data: bytes
    source: str
    reference: str


def rebuild_missing(cs: DbcTable, files: dict[str, tuple[str, str, int]], present, settings: dict | None = None
                    ) -> tuple[list[Rebuilt], list[str]]:
    r"""Textures rows name that neither the package nor the game has: made from the nearest texture of the same
    style (same race, sex, section, variation and slot, nearest colour), moved by the colour change of a sibling
    texture that exists at both colours (the row's other slot, the same slot of another variation, then the hair
    texture for features and scalps, the skin for faces). With no source the row's texture is dropped: a skin, face,
    scalp or underwear row is hidden, a features row keeps no paint. Returns the textures made and what was dropped.
    present(name) -> bool: the name resolves in the game."""
    settings = settings or recolor.settings_from(None, "rebuild")
    rows_by = {}

    for row in cs.rows:
        rows_by[_key(cs, row)] = row

    def exists(name: str) -> bool:
        if not name:
            return False

        if ap.normal(name).lower().startswith(ap.ASCENSION.lower()):
            return ap.name_key(ap.original_name(name)) in files

        return present(name)

    def data_of(name: str) -> bytes | None:
        entry = files.get(ap.name_key(ap.original_name(name)))

        if entry is None:
            return None

        with open(entry[1], "rb") as f:
            return f.read()

    made: dict[str, Rebuilt] = {}
    dropped = []

    for row in cs.rows:
        race, sex, section, variation, colour = _key(cs, row)

        if race not in set(ap.TAKEN_RACES) | set(ap.CLONES):
            continue

        for slot in range(3):
            column = f"textureName[{slot}]"
            name = cs.get_str(row, column)

            if not name or exists(name) or ap.is_ours(name):
                continue

            original = ap.original_name(name)
            done = next((m for m in made.values() if ap.name_key(m.original) == ap.name_key(original)), None)

            if done is not None:
                cs.set_str(row, column, done.name)
                continue

            result = _rebuild_one(rows_by, cs, (race, sex, section, variation, colour), slot, exists, data_of, settings)

            if result is None:
                if section == ap.FEATURES:
                    cs.set_str(row, column, "")
                    dropped.append(f"{name} (features row race {race} sex {sex} value {variation} colour {colour}: "
                                   "no paint)")
                else:
                    cs.set(row, "flags", cs.get(row, "flags") | ap.HIDDEN)
                    dropped.append(f"{name} (row race {race} sex {sex} {ap.SECTION_NAMES[section]} {variation} "
                                   f"colour {colour}: hidden, no source)")
                continue

            source, reference, data = result
            digest = hashlib.sha1(data).hexdigest()
            new_name = ap.rebuilt_name(digest, original)
            made[new_name] = Rebuilt(new_name, original, data, source, reference)
            cs.set_str(row, column, new_name)

    return list(made.values()), dropped


def _rebuild_one(rows_by, cs, key, slot, exists, data_of, settings):
    race, sex, section, variation, colour = key

    def tex(k, s):
        row = rows_by.get(k)
        return cs.get_str(row, f"textureName[{s}]") if row is not None else ""

    sources = sorted((abs(c - colour), c) for (r, x, sec, v, c) in rows_by
                     if (r, x, sec, v) == (race, sex, section, variation) and c != colour and exists(tex((r, x, sec, v, c), slot)))

    for _, src_colour in sources:
        source = tex((race, sex, section, variation, src_colour), slot)
        siblings = [(section, variation, s) for s in range(3) if s != slot]
        siblings += [(section, v, slot) for (r, x, sec, v, c) in sorted(rows_by)
                     if (r, x, sec) == (race, sex, section) and v != variation and c == colour]

        if section in (ap.FEATURES, ap.HAIR):
            siblings += [(ap.HAIR, v, 0) for (r, x, sec, v, c) in sorted(rows_by)
                         if (r, x, sec) == (race, sex, ap.HAIR) and c == colour]
        elif section in (ap.FACE, ap.UNDERWEAR):
            siblings.append((ap.SKIN, 0, 0))

        for sec, v, s in siblings:
            at_src, at_dst = tex((race, sex, sec, v, src_colour), s), tex((race, sex, sec, v, colour), s)

            if not (exists(at_src) and exists(at_dst)):
                continue

            a, b, src = data_of(at_src), data_of(at_dst), data_of(source)

            if a is None or b is None or src is None:
                continue

            try:
                ca = _colour(a, at_src, settings)
                cb = _colour(b, at_dst, settings)

                if ca is None or cb is None:
                    continue

                target = (cb.L, cb.C * math.cos(math.radians(cb.h)), cb.C * math.sin(math.radians(cb.h)))
                transform = recolor.Transform(ca, target, settings)
                return source, at_dst, blp.recolour(src, transform, source)
            except blp.BlpError:
                continue

    return None


def _colour(data: bytes, where: str, settings: dict):
    info = blp.parse(data, where)
    width, height, rgba = blp.decode(data, where)
    return recolor.stats(width, height, rgba, info.has_alpha, settings)


# --- the saved base --------------------------------------------------------------------------------------------


def looks_merged(name: str, data: bytes) -> str | None:
    """Why a table read from the realm is not one from before the package, or None."""
    if name != "CharSections":
        return None

    try:
        table = DbcTable.from_bytes(data, schema_access.get(name))
    except DbcError:
        return None

    asc = ap.ASCENSION.lower()

    for row in table.rows:
        for slot in range(3):
            if table.get_str(row, f"textureName[{slot}]").replace("/", "\\").lower().startswith(asc):
                return "it names Character\\Ascension\\ textures (an earlier customize run)"

    if len(table.rows) > PACKAGE_ROWS_LIMIT:
        return f"it has {len(table.rows)} rows (the package by hand)"

    return None


class Base:
    """/root/wowdata/customize-base: every table customize merges into, as the realm had it before the package, per
    archive it was read from, with its SHA-1 (base.json), and the barber id ledger."""

    def __init__(self, folder: str):
        self.folder = os.path.abspath(folder)
        self.index_path = os.path.join(self.folder, "base.json")
        self.records: dict[str, dict] = {}
        self.saved: list[str] = []

        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, encoding="utf-8") as f:
                    data = json.load(f)
                self.records = dict(data["tables"])
            except (OSError, KeyError, TypeError, json.JSONDecodeError) as e:
                raise CustomizeError(f"{self.index_path}: cannot be read ({e})") from None

    @staticmethod
    def key(client_path: str, table: str) -> str:
        return f"{client_path.lower()}|{table}"

    def get(self, client_path: str, table: str) -> bytes | None:
        record = self.records.get(self.key(client_path, table))

        if record is None:
            return None

        path = os.path.join(self.folder, record["file"])

        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            raise CustomizeError(f"saved base {path}: {e}") from None

        if hashlib.sha1(data).hexdigest() != record["sha1"]:
            raise CustomizeError(f"saved base {path} is not the file base.json names (SHA-1): it changed; restore it "
                                 "from a backup")

        return data

    def put(self, client_path: str, table: str, data: bytes, read_from: str = ""):
        key = self.key(client_path, table)

        if key in self.records:
            raise CustomizeError(f"saved base: {key} is there already")

        rel = os.path.join("tables", client_path.replace("\\", "_").replace("/", "_"), f"{table}.dbc")
        path = os.path.join(self.folder, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path + ".part", "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        os.replace(path + ".part", path)
        self.records[key] = {"archive": client_path, "read_from": read_from or client_path, "table": table,
                             "file": rel.replace(os.sep, "/"),
                             "sha1": hashlib.sha1(data).hexdigest(), "size": len(data), "saved": install.now()}
        self.saved.append(key)
        install.write_json(self.index_path, {
            "_readme": "raceforge.py customize: the realm's tables from before the Ascension package, per archive the "
                       "client read them from, saved by the first run. Every run merges from these. Never edit or "
                       "delete them while the merged tables are live.",
            "tables": dict(sorted(self.records.items())),
        })


# --- the realm -------------------------------------------------------------------------------------------------


@dataclass
class Options:
    package: str
    patches: str
    client: str
    out: str
    base: str
    curation: str
    catalogue: str
    marks: str | None = None
    marks_partial: bool = False  # a dev run: the manifest may lack race-sexes, looks or eyes
    server_dbc: str | None = None
    move_art: str | None = None
    art_names: tuple[str, ...] = DEFAULT_ART
    art_max_mb: int = DEFAULT_ART_MAX_MB
    models_archive: str = MODELS_ARCHIVE
    marks_archive: str = MARKS_ARCHIVE
    locale: str | None = None
    any_package: bool = False
    run_id: str = ""
    base_from: str | None = None  # a folder of the archives from before the package, for a missing saved base
    keep_free_gb: float = 5.0
    taken: str = TAKEN_PATCHES  # taken_patches.json: which archives the realm owns


@dataclass
class Combination:
    label: str
    packs_on: frozenset
    holders: dict[str, object] = field(default_factory=dict)  # table -> GameArchive the client reads it from
    targets: dict[str, object] = field(default_factory=dict)  # table -> GameArchive the forged copy goes into
    merged: Merged | None = None
    data: dict[str, bytes] = field(default_factory=dict)  # table -> forged bytes
    base_tables: dict[str, DbcTable] = field(default_factory=dict)
    models: dict[tuple[int, int], str] = field(default_factory=dict)


@dataclass
class NewArchive:
    """An archive customize writes whole: package art, models, marks or Patch-R's moved art."""
    role: str
    name: str  # patch-6.MPQ
    files: dict[str, str] = field(default_factory=dict)  # archive name -> file on disk
    blobs: dict[str, bytes] = field(default_factory=dict)  # archive name -> bytes (rebuilt textures, moved art)
    digests: dict[str, str] = field(default_factory=dict)  # name key -> SHA-1
    existing: object = None  # the GameArchive of that name, if the realm has one
    unchanged: bool = False

    @property
    def client_path(self) -> str:
        return "Data\\" + self.name

    def size(self) -> int:
        return sum(os.path.getsize(p) for p in self.files.values()) + sum(len(b) for b in self.blobs.values())

    def marker(self) -> bytes:
        listing = sorted((ap.name_key(n), d) for n, d in self.digests.items())
        contents = hashlib.sha1("\n".join(f"{n} {d}" for n, d in listing).encode()).hexdigest()
        return (json.dumps({"tool": "raceforge.py customize", "role": self.role, "files": len(listing),
                            "contents": contents}, indent=2, sort_keys=True) + "\n").encode()

    @property
    def marker_name(self) -> str:
        return f"{MARKER_FOLDER}customize-{self.role}.json"


@dataclass
class Plan:
    options: Options
    game: object
    cur: curmod.Curation
    catalogue: marksrows.Catalogue
    manifest: marksrows.Manifest | None
    package_tables: dict[str, DbcTable]
    files: dict[str, tuple[str, str, int]]
    combos: list[Combination]
    targets: dict[str, dict[str, bytes]] = field(default_factory=dict)  # archive client path lower -> {name: bytes}
    target_archives: dict[str, object] = field(default_factory=dict)
    new_archives: list[NewArchive] = field(default_factory=list)
    moved: list[str] = field(default_factory=list)  # Patch-R files moved to the moved-art archive
    rebuilt: dict[str, Rebuilt] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)
    ledger: BarberLedger | None = None
    base: Base | None = None
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    model_checks: list[str] = field(default_factory=list)
    mappings: dict = field(default_factory=dict)
    hashes: dict = field(default_factory=dict)
    realm_owned: set = field(default_factory=set)  # name keys (taken_patches.json) of the archives the realm owns
    foreign: dict = field(default_factory=dict)  # name key -> owner of the archives another project owns

    @property
    def server(self) -> Combination:
        """The combination the server's copies come from: no packs (every combination must agree anyway)."""
        return self.combos[-1]


def read_table(archive, name: str, where: str) -> bytes:
    try:
        return archive.read(dbc_path(name))
    except patches.PatchError as e:
        raise CustomizeError(f"{where}: {e}") from None


def load_package_tables(package_dir: str) -> dict[str, DbcTable]:
    try:
        tables = customize.load_package(package_dir)
    except customize.CustomizeError as e:
        raise CustomizeError(str(e)) from None

    missing = [n for n in MERGED if n not in tables]

    if missing:
        raise CustomizeError(f"{package_dir}: the package has no {', '.join(n + '.dbc' for n in missing)}")

    return tables


def archive_key(archive) -> str:
    """An archive's name as taken_patches.json lists it: its path below Data (enUS/patch-enUS-3.MPQ), any case."""
    rel = archive.rel or archive.client_path.split("\\", 1)[-1]
    return patchnames.name_key(rel)


def not_ours(archive, realm_owned: set, foreign: dict) -> str | None:
    """Why customize may not rebuild an archive the client reads a table from (None: it may): one of an optional pack
    that the realm does not own (a Reforged mirror patch, which the launcher serves from the partner's mirror), or
    one taken_patches.json gives to another project. A base archive's table goes into archives.own instead."""
    if archive.is_base:
        return None

    key = archive_key(archive)

    if key in realm_owned:
        return None

    if key in foreign:
        return f"{foreign[key]}{f', optional pack {archive.pack}' if archive.pack else ''}; not a realm archive"

    if archive.pack is not None:
        return f"optional pack {archive.pack}; not a realm archive"

    return None


def make_plan(opts: Options, config) -> Plan:
    from . import skins  # Tools/MapForge's archive code, the launcher's layout

    try:
        cur = curmod.load(opts.curation)
        catalogue = marksrows.load_catalogue(opts.catalogue)
        manifest = marksrows.load_manifest(opts.marks, catalogue, partial=opts.marks_partial) if opts.marks else None
    except (curmod.CurationError, marksrows.MarksError) as e:
        raise CustomizeError(str(e)) from None

    commit = package_commit(opts.package)

    if commit != cur.commit and not opts.any_package:
        raise CustomizeError(f"{opts.package} is at commit {commit or '(not a git checkout)'}, the curation is for "
                             f"{cur.commit[:12]} ({opts.curation}): check out that commit, or review the curation for "
                             "the new one (--any-package skips this check)")

    package_tables = load_package_tables(opts.package)
    files = package_files(opts.package)

    try:
        game = skins.game_archives(opts.client, opts.patches, config.archives.optional_packs, opts.locale)
    except skins.SkinsError as e:
        raise CustomizeError(str(e)) from None

    unreadable = [f"{a.name}: {a.error}" for a in game.archives if a.reader is None]

    if unreadable:
        game.close()
        raise CustomizeError("cannot read every archive the client loads: " + "; ".join(unreadable))

    plan = Plan(opts, game, cur, catalogue, manifest, package_tables, files,
                [Combination(label, packs_on) for label, packs_on in game.patchset.configurations()])
    plan.base = Base(opts.base)
    plan.ledger = BarberLedger.load(os.path.join(plan.base.folder, "barber_ids.json"))
    own = game.patchset.find(config.archives.own)

    if own is None:
        raise CustomizeError(f"the realm has no {config.archives.own} (archives.own): the race patch holds the realm's "
                             "tables")

    if own.pack is not None:
        raise CustomizeError(f"{own.name} (archives.own) is in the optional pack {own.pack}")

    try:
        groups = patchnames.load_groups(opts.taken)
        plan.realm_owned = patchnames.realm_owned(groups) | {archive_key(own)}
        plan.foreign = {k: v for k, v in patchnames.foreign(groups).items() if k not in plan.realm_owned}
    except patchnames.PatchNameError as e:
        raise CustomizeError(str(e)) from None

    # 1. where every combination reads the tables, and the realm's races
    for combo in plan.combos:
        for name in TABLES + CHECK_TABLES:
            holder = game.patchset.top(dbc_path(name), combo.packs_on)

            if holder is None:
                raise CustomizeError(f"no archive holds {dbc_path(name)} for {combo.label}")

            combo.holders[name] = holder

            if name in TABLES:
                why = not_ours(holder, plan.realm_owned, plan.foreign)

                if why:
                    # rebuilding it would put a copy of a mirror's archive on the VPS (served to every player of the
                    # pack instead of the mirror) that the next mirror refresh replaces, merge and all
                    raise CustomizeError(
                        f"{holder.name} ({why}) holds {name}.dbc over {own.name} for {combo.label}: customize never "
                        "rebuilds it; remove the table from that pack, or put the merged copy in a realm patch that "
                        "sorts above it")

                combo.targets[name] = own if holder.is_base else holder

        races = DbcTable.from_bytes(read_table(combo.holders["ChrRaces"], "ChrRaces", combo.label),
                                    schema_access.get("ChrRaces"))
        problems = update.race_problems(config, races, f"{combo.holders['ChrRaces'].name}, for {combo.label}",
                                        "customize")

        for race, file_string in ((15, "HighElf"), (19, "Eredar")):
            row = races.by_id().get(race)

            if row is None or races.get_str(row, "clientFileString").lower() != file_string.lower():
                problems.append(f"{combo.label}: ChrRaces race {race} is not {file_string}")

        if problems:
            raise CustomizeError("; ".join(dict.fromkeys(problems)))

        displays = DbcTable.from_bytes(read_table(combo.holders["CreatureDisplayInfo"], "CreatureDisplayInfo",
                                                  combo.label), schema_access.get("CreatureDisplayInfo"))
        models = DbcTable.from_bytes(read_table(combo.holders["CreatureModelData"], "CreatureModelData", combo.label),
                                     schema_access.get("CreatureModelData"))
        combo.models = geosets.model_paths(races, displays, models, set(ap.TAKEN_RACES) | set(ap.CLONES))

    # 2. the saved base
    for combo in plan.combos:
        merged_now = []

        for name in TABLES:
            holder = combo.holders[name]
            data = read_table(holder, name, combo.label)
            why = looks_merged(name, data)

            if why:
                merged_now.append(f"{name} of {holder.name} ({why})")

        for name in TABLES:
            holder = combo.holders[name]
            # keyed by the archive the forged copy goes into: a table read from a base archive goes into
            # archives.own, and the next run reads it from there
            target = combo.targets[name]
            saved = plan.base.get(target.client_path, name)

            if saved is None:
                if merged_now:
                    saved = old_table(opts.base_from, holder, name, plan.game, combo) if opts.base_from else None

                    if saved is None:
                        raise CustomizeError(
                            f"{combo.label}: the realm's tables are merged already ({'; '.join(merged_now)}) and the "
                            f"saved base {plan.base.folder} has no {name} of {holder.name}: give --base-from a folder "
                            "with the realm's archives from before the package (an install's old-patches, or the "
                            "launcher's www/objects copy put back under its name)")
                else:
                    saved = read_table(holder, name, combo.label)

                plan.base.put(target.client_path, name, saved, holder.client_path)
            elif not merged_now and plan.base.key(target.client_path, name) not in plan.base.saved:
                # the package is not live in this combination, so the client reads the realm's own table: it must
                # still be the saved one, or a re-forged Patch-R (new barber rows, a new race's rows, helmet bits)
                # would be merged from an outdated base and silently dropped
                data = read_table(holder, name, combo.label)

                if data != saved:
                    record = plan.base.records.get(plan.base.key(target.client_path, name), {})
                    raise CustomizeError(
                        f"{combo.label}: the realm's {name}.dbc of {holder.name} changed since the saved base "
                        f"{plan.base.folder} was made ({record.get('saved', 'date unknown')}); the package is not "
                        f"live, so move {os.path.join(plan.base.folder, 'tables')} and "
                        f"{plan.base.index_path} aside (keep barber_ids.json) and run again to save it afresh")

            combo.base_tables[name] = DbcTable.from_bytes(saved, schema_access.get(name),
                                                          f"saved base {holder.name}: {name}.dbc")

    # 3. the merge, for every combination
    renamer = Renamer(files)

    for combo in plan.combos:
        def present(name: str, packs_on=combo.packs_on) -> bool:
            return game.patchset.top(name, packs_on) is not None

        def fixup(cs: DbcTable, out: Merged):
            made, dropped = rebuild_missing(cs, files, present)

            for item in made:
                plan.rebuilt.setdefault(item.name, item)

            plan.dropped.extend(d for d in dropped if d not in plan.dropped)

        try:
            combo.merged = merge(combo.base_tables, package_tables, cur, plan.ledger, renamer, manifest, catalogue,
                                 fixup)
        except (marksrows.MarksError, curmod.CurationError) as e:
            raise CustomizeError(str(e)) from None

        plan.problems += [f"{combo.label}: {p}" for p in gates(combo.merged)]
        combo.data = {name: table.to_bytes() for name, table in combo.merged.tables.items()}

    if plan.manifest is not None:
        plan.ledger.check_bases(plan.server.merged.bases)

    # 4. where the forged copies go: one copy per archive
    for combo in plan.combos:
        for name in TABLES:
            target = combo.targets[name]
            files_there = plan.targets.setdefault(target.client_path.lower(), {})
            plan.target_archives[target.client_path.lower()] = target
            path = dbc_path(name)

            if path in files_there and files_there[path] != combo.data[name]:
                raise CustomizeError(f"{target.name} would need two different {name}.dbc (for {combo.label} and "
                                     "another combination): its base copies differ between the packs")

            files_there[path] = combo.data[name]

    plan_art(plan)
    check_textures(plan)
    check_models(plan)
    check_view(plan)
    server_checks(plan)

    base_cs = plan.server.base_tables["CharSections"]
    plan.problems += remap.clone_problems(base_cs)
    server = plan.server.merged.tables
    plan.mappings = remap.compute_all(base_cs, server["CharSections"],
                                      base_hair=plan.server.base_tables["CharHairGeosets"],
                                      merged_hair=server["CharHairGeosets"],
                                      base_facial=plan.server.base_tables["CharacterFacialHairStyles"],
                                      merged_facial=server["CharacterFacialHairStyles"])
    # a hair style or features value whose meaning changed: every character on it would silently get another look
    race_ids = {name: rid for rid, name in ap.RACE_FILES.items()}
    plan.problems += remap.meaning_problems(plan.mappings, cur.accepted_keys(race_ids))
    return plan


def old_table(folder: str, holder, name: str, game=None, combo=None) -> bytes | None:
    """The table from the realm's archive of before the package (folder/<its path in the patch folder>), checked. When
    that archive did not hold the table (customize put it there from a base archive), the copy below it today."""
    path = os.path.join(folder, *holder.rel.split("/")) if holder.rel else None

    if path is None or not os.path.isfile(path):
        return None

    reader = patches.PatchArchive(path)

    try:
        data = reader.read(dbc_path(name)) if reader.has_file(dbc_path(name)) else None
    finally:
        reader.close()

    if data is None and game is not None and combo is not None:
        below = [a for a in game.patchset.holders(dbc_path(name), combo.packs_on) if a.rank() < holder.rank()]

        if below:
            data = below[-1].read(dbc_path(name))

    if data is not None and looks_merged(name, data):
        raise CustomizeError(f"{path}: its {name}.dbc is merged too ({looks_merged(name, data)})")

    return data


def server_problems(server_dbc: str, plan: Plan) -> list[str]:
    """Warnings about the server's data/dbc today: the raw package (race 15 = Skeleton) or no barber rows of 15 and 19."""
    out = []
    cs_path = os.path.join(server_dbc, "CharSections.dbc")

    if os.path.isfile(cs_path):
        with open(cs_path, "rb") as f:
            data = f.read()

        try:
            table = DbcTable.from_bytes(data, schema_access.get("CharSections"))
        except DbcError as e:
            return [f"{cs_path}: {e}"]

        skeleton = [r for r in table.rows if table.get(r, "raceID") == 15 and "skeleton" in
                    table.get_str(r, "textureName[0]").lower()]

        if skeleton:
            out.append(f"{cs_path} holds {len(skeleton)} Skeleton rows as race 15: the package's DBCs were copied to "
                       "the server by hand; customize's server/dbc replaces them")

    barber_path = os.path.join(server_dbc, "BarberShopStyle.dbc")

    if os.path.isfile(barber_path):
        with open(barber_path, "rb") as f:
            table = DbcTable.from_bytes(f.read(), schema_access.get("BarberShopStyle"))

        missing = [r for r in (15, 19) if not any(table.get(row, "race") == r for row in table.rows)]

        if missing:
            out.append(f"{barber_path} has no rows of race(s) {missing}: their barbershop is refused today")

    return out


def stays_in_r(plan: Plan, holder, moved_name: str, name: str) -> bool:
    """A Patch-R file moving to the moved-art archive (which sorts below it) must not then lose to an archive between
    the two in any combination."""
    low, high = patches.sort_key("Data\\" + moved_name), patches.sort_key(holder.client_path)

    for combo in plan.combos:
        for archive in plan.game.patchset.active(combo.packs_on):
            if archive.is_base or archive.group != 1:
                continue

            key = patches.sort_key(archive.client_path)

            if low < key < high and archive.has(name):
                return True

    return False


def plan_art(plan: Plan):
    opts = plan.options
    referenced: set[str] = set()

    for combo in plan.combos:
        cs = combo.merged.tables["CharSections"]

        for row in cs.rows:
            if cs.get(row, "raceID") in set(ap.TAKEN_RACES) | set(ap.CLONES):
                for slot in range(3):
                    name = cs.get_str(row, f"textureName[{slot}]")

                    if name.replace("/", "\\").lower().startswith(ap.ASCENSION.lower()) and \
                            not name.replace("/", "\\").lower().startswith(ap.REBUILT.lower()):
                        referenced.add(ap.name_key(ap.original_name(name)))

    # package textures (named by rows), rebuilt ones, under Character\Ascension\
    items = []

    for key in sorted(referenced):
        spelling, path, size = plan.files[key]
        items.append((ap.ascension_name(spelling), path, size))

    blobs = [(item.name, item.data) for item in sorted(plan.rebuilt.values(), key=lambda r: r.name)]
    limit = opts.art_max_mb * 1024 * 1024
    art = [NewArchive("art", n) for n in opts.art_names]
    index, total = 0, 0

    for name, path, size in items:
        if total + size > limit and art[index].files:
            index += 1
            total = 0

            if index >= len(art):
                raise CustomizeError(f"the package's textures need more than {len(art)} archives of {opts.art_max_mb} "
                                     f"MB ({', '.join(opts.art_names)}): give more names")

        art[index].files[name] = path
        total += size

    for name, data in blobs:
        art[index].blobs[name] = data

    # the package's licence and what RaceForge changed (AGPL-3.0), with the art
    licence = next((os.path.join(opts.package, e) for e in sorted(os.listdir(opts.package))
                    if e.lower() in ("license", "license.txt", "license.md")), None)

    if licence is not None:
        with open(licence, "rb") as f:
            art[0].blobs[MARKER_FOLDER + "Ascension-LICENSE.txt"] = f.read()

    art[0].blobs[MARKER_FOLDER + "Ascension-NOTICE.txt"] = notice(plan).encode("utf-8")

    # models: the package's .m2, .skin and .anim of the model races and the textures they name themselves
    models = NewArchive("models", opts.models_archive)

    for key, (spelling, path, size) in sorted(plan.files.items()):
        if key.endswith((".m2", ".skin", ".anim")):
            models.files[spelling] = path

            if key.endswith(".m2"):
                with open(path, "rb") as f:
                    try:
                        info = geosets.parse_m2(f.read(), spelling)
                    except geosets.ModelError as e:
                        plan.problems.append(str(e))
                        continue

                for texture in geosets.own_textures(info):
                    entry = plan.files.get(ap.name_key(texture))

                    if entry is not None:
                        models.files[entry[0]] = entry[1]

    plan.new_archives = [a for a in art if a.files or a.blobs or a.role != "art" or a is art[0]] + [models]

    # archives of an earlier run that this plan leaves empty are written with their marker only (stale files go)
    for extra in art[1:]:
        if not extra.files and not extra.blobs and plan.game.patchset.find(extra.name) is not None:
            plan.new_archives.append(extra)

    if plan.manifest is not None:
        marks = NewArchive("marks", opts.marks_archive)

        for entry in plan.manifest.entries.values():
            for name, path, _ in entry.files():
                marks.files[name] = path

        plan.new_archives.append(marks)

    if opts.move_art:
        moved = NewArchive("moved-art", opts.move_art)
        own = plan.target_archives  # the table archives this plan rebuilds

        for key, holder in sorted(own.items()):
            if holder.pack is not None or holder.is_base:
                continue

            for name in patches.archive_contents(holder.reader, holder.name):
                lower = name.replace("/", "\\").lower()

                if lower.startswith("dbfilesclient\\") or lower.startswith(ap.SKINS_FOLDER.lower()) or \
                        lower.startswith(MARKER_FOLDER.lower()) or name in mpqpack.SPECIAL_FILES:
                    continue

                if stays_in_r(plan, holder, opts.move_art, name):
                    plan.notes.append(f"{name} stays in {holder.name}: an archive between {opts.move_art} and it holds "
                                      "the same name")
                    continue

                moved.blobs[name] = holder.read(name)
                plan.moved.append(f"{holder.client_path.lower()}|{name}")

        if moved.blobs:
            plan.new_archives.append(moved)

    for archive in plan.new_archives:
        for name, path in archive.files.items():
            archive.digests[name] = sha1_path(path)

        for name, data in archive.blobs.items():
            archive.digests[name] = hashlib.sha1(data).hexdigest()

        archive.existing = plan.game.patchset.find(archive.name)

        if archive.existing is not None:
            if archive.existing.pack is not None:
                raise CustomizeError(f"{archive.name} is in the optional pack {archive.existing.pack}")

            try:
                old = archive.existing.read(archive.marker_name) if archive.existing.has(archive.marker_name) else None
            except patches.PatchError:
                old = None

            if old is None:
                raise CustomizeError(f"{archive.name} is in the patch folder and is not customize's ({archive.role}): "
                                     "give another name")

            archive.unchanged = old == archive.marker()


def notice(plan: Plan) -> str:
    package = plan.cur.package
    return (f"This archive holds textures of {package.get('name', 'the package')} by {package.get('author', '?')} "
            f"({package.get('url', '')}), commit {plan.cur.commit}, licensed {package.get('licence', 'AGPL-3.0')} "
            "(Ascension-LICENSE.txt). " + str(package.get("credits", "")) + "\n\n"
            "Changed by Bleakhold's RaceForge (Tools/RaceForge in https://github.com/gardenreedbarrie-dev/bleak, "
            "raceforge.py customize): the files are the package's own, under Character\\Ascension\\<their path>; "
            "textures the package names but does not ship are rebuilt under Character\\Ascension\\Rebuilt\\ by "
            "recolouring the nearest texture of the same style; the package's tables are merged into the realm's "
            "(races 1-11, copied to High Elf 15 and Eredar 19, rows hidden by customize/curation.json).\n")


def texture_info(plan: Plan, combo: Combination, name: str) -> tuple[int, int, int] | None:
    lower = ap.normal(name).lower()

    if lower.startswith(ap.REBUILT.lower()):
        item = plan.rebuilt.get(name) or next((r for r in plan.rebuilt.values() if r.name.lower() == lower), None)
        return header_info(item.data, name) if item else None

    if lower.startswith(ap.ASCENSION.lower()):
        entry = plan.files.get(ap.name_key(ap.original_name(name)))
        return header_info(read_head(entry[1]), name) if entry else None

    if plan.manifest is not None:
        for entry in plan.manifest.entries.values():
            for texture, path, _ in entry.files():
                if ap.name_key(texture) == ap.name_key(name):
                    return header_info(read_head(path), name)

    archive = plan.game.patchset.top(name, combo.packs_on)

    if archive is None:
        return None

    return header_info(archive.read(name)[:blp.HEADER.size], f"{archive.name}: {name}")


def texture_source(plan: Plan, combo: Combination, name: str) -> str | None:
    """Which file texture_info() reads for a name in this combination: "" for a name that does not depend on it (a
    rebuilt texture, a Character\\Ascension\\ one, a mark of the manifest), else the archive that holds it (None:
    none does)."""
    lower = ap.normal(name).lower()

    if lower.startswith(ap.REBUILT.lower()) or lower.startswith(ap.ASCENSION.lower()):
        return ""

    if plan.manifest is not None:
        key = ap.name_key(name)

        for entry in plan.manifest.entries.values():
            for texture, _, _ in entry.files():
                if ap.name_key(texture) == key:
                    return ""

    archive = plan.game.patchset.top(name, combo.packs_on)
    return archive.name if archive is not None else None


def check_textures(plan: Plan):
    """Every texture a row names: it resolves, and it pastes at levels 7-9 (README: "File rules"), in every
    combination. A stock name can resolve to another archive in each (the HD pack's copy with every pack, a stock
    MPQ's without), so a name is checked once per file it reads, not once per name."""
    seen: dict[tuple[str | None, str, str], str | None] = {}
    races = set(ap.TAKEN_RACES) | set(ap.CLONES)

    for combo in plan.combos:
        cs = combo.merged.tables["CharSections"]

        for row in cs.rows:
            if cs.get(row, "raceID") not in races:
                continue

            section = cs.get(row, "baseSection")

            for slot in range(3):
                name = cs.get_str(row, f"textureName[{slot}]")
                target = ap.TARGETS.get((section, slot))

                if not name or target is None:
                    continue

                source = texture_source(plan, combo, name)
                # a missing stock name is keyed per combination, so each one that misses it is reported
                key = (source if source is not None else f"(missing) {combo.label}", ap.name_key(name), target)

                if key in seen:
                    continue

                try:
                    info = texture_info(plan, combo, name)
                except (CustomizeError, patches.PatchError, OSError) as e:
                    seen[key] = str(e)
                    plan.problems.append(f"{combo.label}: {e}")
                    continue

                if info is None:
                    seen[key] = "missing"
                    plan.problems.append(f"{combo.label}: {name} ({ap.SECTION_NAMES[section]} texture {slot}) is in "
                                         "no archive and was not rebuilt")
                    continue

                problem = ap.paste_problem(*info, target)
                seen[key] = problem

                if problem:
                    where = f" of {source}" if source else ""
                    plan.problems.append(f"{combo.label}: {name}{where}: {problem}")


class View:
    """The client's view of one combination with the planned archives: the rebuilt table archives and the new ones."""

    _index_cache: dict[int, tuple] = {}

    def __init__(self, plan: Plan, combo: Combination):
        self.plan, self.combo = plan, combo
        cached = View._index_cache.get(id(plan))

        if cached is None or cached[0] is not plan:
            new_index: dict[bytes, list] = {}

            for archive in plan.new_archives:
                rank = (1, patches.sort_key(archive.client_path))

                for n, path in archive.files.items():
                    new_index.setdefault(mpqpack.name_key(n), []).append((rank, archive.name, ("file", path)))

                for n, data in archive.blobs.items():
                    new_index.setdefault(mpqpack.name_key(n), []).append((rank, archive.name, ("bytes", data)))

            planned = {key: {mpqpack.name_key(n): d for n, d in files.items()} for key, files in plan.targets.items()}
            moved = {(k.split("|", 1)[0], mpqpack.name_key(k.split("|", 1)[1])) for k in plan.moved}
            cached = View._index_cache[id(plan)] = (plan, new_index, planned, moved)

        _, self.new_index, self.planned, self.moved = cached
        self.replaced = {a.name.lower() for a in plan.new_archives}
        self.active = [a for a in plan.game.patchset.active(combo.packs_on) if a.name.lower() not in self.replaced]

    def holders(self, name: str) -> list[tuple[tuple, str, object]]:
        key = mpqpack.name_key(name)
        out = []

        for archive in self.active:
            planned = self.planned.get(archive.client_path.lower(), {})

            if key in planned:
                out.append((archive.rank(), archive.name, ("bytes", planned[key])))
            elif (archive.client_path.lower(), key) not in self.moved and archive.has(name):
                out.append((archive.rank(), archive.name, ("archive", archive)))

        out += self.new_index.get(key, [])
        return sorted(out, key=lambda t: t[0])

    def top(self, name: str) -> tuple[str, bytes] | None:
        found = self.holders(name)

        if not found:
            return None

        _, archive_name, (kind, value) = found[-1]
        return archive_name, self._bytes(kind, value, name)

    @staticmethod
    def _bytes(kind, value, name):
        if kind == "bytes":
            return value

        if kind == "file":
            with open(value, "rb") as f:
                return f.read()

        return value.read(name)

    def own(self, archive_name: str, name: str) -> bytes | None:
        for _, a, (kind, value) in self.holders(name):
            if a == archive_name:
                return self._bytes(kind, value, name)

        return None


def check_view(plan: Plan):
    """In every combination the client reads the forged tables, and every Character\\Ascension\\ name resolves to
    the planned file."""
    for combo in plan.combos:
        view = View(plan, combo)

        for name in TABLES:
            found = view.top(dbc_path(name))

            if found is None or found[1] != combo.data[name]:
                plan.problems.append(f"{combo.label}: the client would not read the merged {name}.dbc "
                                     f"({found[0] if found else 'no archive'})")

        expected = {}

        for archive in plan.new_archives:
            for n in list(archive.files) + list(archive.blobs):
                expected[mpqpack.name_key(n)] = (archive.name, n)

        cs = combo.merged.tables["CharSections"]
        names = {cs.get_str(r, f"textureName[{s}]") for r in cs.rows for s in range(3)}

        for name in sorted(n for n in names if n.replace("/", "\\").lower().startswith(ap.ASCENSION.lower())):
            hits = view.holders(name)

            if not hits or hits[-1][1] != expected.get(mpqpack.name_key(name), ("", ""))[0]:
                plan.problems.append(f"{combo.label}: {name} would come from {hits[-1][1] if hits else 'no archive'}, "
                                     "not from the planned archive")


def check_models(plan: Plan):
    for combo in plan.combos:
        view = View(plan, combo)
        cs = combo.merged.tables["CharSections"]
        hair = combo.merged.tables["CharHairGeosets"]
        facial = combo.merged.tables["CharacterFacialHairStyles"]

        for (race, sex), model in sorted(combo.models.items()):
            need = geosets.required(cs, hair, facial, race, sex)
            result = geosets.check_model(race, sex, model, need, view.top, view.own)

            for line in geosets.describe(result):
                plan.problems.append(f"{combo.label}: {line}")

            plan.model_checks.append(f"{combo.label}: race {race} {ap.SEXES[sex]}: {geosets.m2_name(model)} from "
                                     f"{result.archive or '-'}, {len(need)} geoset(s) needed")


def server_checks(plan: Plan):
    cs_hashes = {c.label: charsections_hash(c.merged.tables["CharSections"]) for c in plan.combos}
    barber = {c.label: c.data["BarberShopStyle"] for c in plan.combos}

    if len(set(cs_hashes.values())) != 1:
        plan.problems.append(f"the combinations' CharSections differ in what the server reads (ids, races, flags, "
                             f"variations, colours): {cs_hashes}")

    if len(set(barber.values())) != 1:
        plan.problems.append("the combinations' BarberShopStyle.dbc differ: the server can match only one")

    server = plan.server.merged.tables
    plan.hashes = {
        "charsections": charsections_hash(server["CharSections"]),
        "barbershopstyle": barber_hash(server["BarberShopStyle"]),
        "barbershopstyle_file_sha1": hashlib.sha1(plan.server.data["BarberShopStyle"]).hexdigest(),
        "charsections_rows": len(server["CharSections"].rows),
        "barbershopstyle_rows": len(server["BarberShopStyle"].rows),
    }

    if plan.options.server_dbc:
        plan.warnings += server_problems(plan.options.server_dbc, plan)
        path = os.path.join(plan.options.server_dbc, "BarberShopStyle.dbc")

        if os.path.isfile(path):
            with open(path, "rb") as f:
                now = f.read()

            base_barber = plan.server.base_tables["BarberShopStyle"].to_bytes()

            if now not in (base_barber, plan.server.data["BarberShopStyle"]):
                plan.warnings.append(f"{path} is neither the client's BarberShopStyle.dbc of before the package nor "
                                     "the merged one: the server and client disagree today")


# --- writing ---------------------------------------------------------------------------------------------------


def space_needed(plan: Plan) -> int:
    """Bytes --out needs: every new archive's files (unpacked, an upper bound), every rebuilt archive whole and its
    files staged once, and a margin."""
    total = 256 * 1024 * 1024

    for archive in plan.new_archives:
        if not archive.unchanged:
            total += archive.size()

    for key in plan.targets:
        archive = plan.target_archives[key]
        total += 2 * (archive.size or 0)

    return total


def write(plan: Plan, out_dir: str) -> dict[str, str]:
    """Every archive to out/client, the server copies, the SQL. {client path lower: written file}."""
    written = {}
    moved = {}

    for item in plan.moved:
        key, name = item.split("|", 1)
        moved.setdefault(key, set()).add(mpqpack.name_key(name))

    refused = [f"{plan.target_archives[k].name} ({why})" for k in sorted(plan.targets)
               if (why := not_ours(plan.target_archives[k], plan.realm_owned, plan.foreign))]

    if refused:
        raise CustomizeError("customize never rebuilds an archive the realm does not own: " + "; ".join(refused))

    for key, files in sorted(plan.targets.items()):
        archive = plan.target_archives[key]
        staging = os.path.join(out_dir, "merged", archive.name)
        os.makedirs(staging, exist_ok=True)
        replacements = {}

        for i, (name, data) in enumerate(sorted(files.items())):
            path = os.path.join(staging, f"{i:06d}")

            with open(path, "wb") as f:
                f.write(data)

            replacements[name] = path

        out_path = os.path.join(out_dir, "client", *archive.rel.split("/"))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        drop = moved.get(key, set())

        try:
            patches.rebuild(archive, replacements, out_path, os.path.join(out_dir, "staging"),
                            drop=lambda n: mpqpack.name_key(n) in drop)
        except patches.PatchError as e:
            raise CustomizeError(str(e)) from None
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        written[key] = out_path

    for archive in plan.new_archives:
        if archive.unchanged:
            continue

        staging = os.path.join(out_dir, "merged", archive.name)
        os.makedirs(staging, exist_ok=True)
        items = sorted(archive.files.items())

        for i, (name, data) in enumerate(sorted(archive.blobs.items()) + [(archive.marker_name, archive.marker())]):
            path = os.path.join(staging, f"{i:06d}")

            with open(path, "wb") as f:
                f.write(data)

            items.append((name, path))

        out_path = os.path.join(out_dir, "client", archive.name)

        try:
            mpqpack.write_archive_streaming(out_path, items)
        except mpqpack.MpqError as e:
            raise CustomizeError(f"writing {out_path}: {e}") from None
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        written[archive.client_path.lower()] = out_path

    shutil.rmtree(os.path.join(out_dir, "merged"), ignore_errors=True)
    server = os.path.join(out_dir, "server", "dbc")
    os.makedirs(server, exist_ok=True)

    for name in TABLES:
        with open(os.path.join(server, f"{name}.dbc"), "wb") as f:
            f.write(plan.server.data[name])

    install.write_json(os.path.join(out_dir, "server", "appearance-hashes.json"), {
        "_readme": "The server-visible hashes of the merged tables (README.md, 'Bleakhold appearance data contract', "
                   "Ids). The world server logs the same numbers after its database overrides.",
        **plan.hashes})
    sql = os.path.join(out_dir, "server", "sql")
    os.makedirs(sql, exist_ok=True)
    run_id = plan.options.run_id or time.strftime("customize-%Y%m%d%H%M%S", time.gmtime())

    with open(os.path.join(sql, "remap_tables.sql"), "w", encoding="utf-8", newline="\n") as f:
        f.write(remap.tables_sql())

    # stage 2 (--marks) runs on the stage-1 tables: its mappings, from the saved base, are stage 1's moves, which
    # stage 1 already made (and characters made since stand on the stage-1 numbers), so its remap moves nobody
    with open(os.path.join(sql, "remap_characters.sql"), "w", encoding="utf-8", newline="\n") as f:
        text = remap.remap_sql(plan.mappings if plan.manifest is None else {}, run_id)

        if plan.manifest is not None:
            first, rest = text.split("\n", 1)
            text = (first + "\n-- Stage 2 (--marks): no character moves. The base-to-merged moves are stage 1's, "
                    "already made; stage 2 keeps every stage-1 value.\n" + rest)

        f.write(text)

    with open(os.path.join(sql, "restore_characters.sql"), "w", encoding="utf-8", newline="\n") as f:
        f.write(remap.restore_sql(run_id))

    # stage 2 (--marks) computes its mappings from the saved base too, so its accepted changes are stage 1's, whose
    # characters stage 1 already moved (and who may have picked the old number again since, where it is a valid
    # value): they are not counted then
    accepted = accepted_looks(plan.mappings) if plan.manifest is None else []

    with open(os.path.join(sql, "count_hidden.sql"), "w", encoding="utf-8", newline="\n") as f:
        f.write(remap.hidden_count_sql(hidden_looks(plan.server.merged.hidden), accepted))

    if plan.server.merged.bases:
        with open(os.path.join(sql, "marks_rollback.sql"), "w", encoding="utf-8", newline="\n") as f:
            f.write(remap.marks_rollback_sql(plan.server.merged.bases))

    return written


def hidden_looks(hidden: list[curmod.HiddenRow]) -> list[tuple[int, int, str, int, int]]:
    """count_hidden.sql's input: (race, sex, column, value, skin colour) of every hidden skin or face row. A face row
    is one face on one skin colour, so its colour goes with it: the face is hidden only on that skin."""
    out = []

    for h in hidden:
        if h.section == ap.SKIN:
            out.append((h.race, h.sex, "skin", h.colour, h.colour))
        elif h.section == ap.FACE:
            out.append((h.race, h.sex, "face", h.variation, h.colour))

    return out


def accepted_looks(mappings: dict) -> list[tuple[int, int, str, int, bool]]:
    """count_hidden.sql's accepted hair style and features changes: (race, sex, column, old value, Death Knight).

    Only a value the remap moved to another number (Mapping.styles / .features (new, False), new != old) is counted:
    right after the remap nobody of that kind is on it. A kept value (value, True) is not: its characters stay on it
    on purpose and get a customize. Nor is a value that another accepted change of the same race, sex and kind moves
    characters onto (a swap or a chain): its count is the moved characters."""
    out = set()

    for (race, sex, dk), m in mappings.items():
        for column, values in (("hairStyle", m.styles), ("facialStyle", m.features)):
            targets = {new for new, keep in values.values() if not keep}

            for value, (new, keep) in values.items():
                if not keep and new != value and value not in targets:
                    out.add((race, sex, column, value, bool(dk)))

    return sorted(out)


def manifest_entries(plan: Plan, written: dict[str, str]) -> list[dict]:
    entries = []

    for key, path in sorted(written.items()):
        archive = plan.target_archives.get(key)

        if archive is not None:
            entries.append(install.entry(archive.rel, archive.client_path, archive.origin, archive.path, archive.size,
                                         archive.mtime_ns, path))
            continue

        new = next(a for a in plan.new_archives if a.client_path.lower() == key)

        if new.existing is not None:
            entries.append(install.entry(new.existing.rel, new.existing.client_path, new.existing.origin,
                                         new.existing.path, new.existing.size, new.existing.mtime_ns, path))
        else:
            entries.append(install.entry(new.name, new.client_path, "new", "", None, None, path))

    return entries


def check_written(plan: Plan, written: dict[str, str]) -> list[str]:
    """Read every written table archive back: its tables are the planned bytes, every other file is still there."""
    problems = []

    for key, files in plan.targets.items():
        path = written.get(key)

        if path is None:
            continue

        reader = patches.PatchArchive(path)

        try:
            for name, data in files.items():
                if reader.read(name) != data:
                    problems.append(f"{path}: {name} is not the merged table")

            source = plan.target_archives[key]
            moved = {n.split("|", 1)[1] for n in plan.moved if n.startswith(key + "|")}

            for name in patches.archive_contents(source.reader, source.name):
                if name not in moved and not reader.has_file(name):
                    problems.append(f"{path}: lost {name}")
        finally:
            reader.close()

    for archive in plan.new_archives:
        path = written.get(archive.client_path.lower())

        if path is None:
            continue

        reader = patches.PatchArchive(path)

        try:
            if reader.read(archive.marker_name) != archive.marker():
                problems.append(f"{path}: its marker is not the planned one")

            for name, data in archive.blobs.items():
                if reader.read(name) != data:
                    problems.append(f"{path}: {name} differs")

            for name in archive.files:
                if not reader.has_file(name):
                    problems.append(f"{path}: {name} is missing")
                elif hashlib.sha1(reader.read(name)).hexdigest() != archive.digests[name]:
                    problems.append(f"{path}: {name} is not the planned file (SHA-1)")
        finally:
            reader.close()

    return problems


def summary(plan: Plan, written: dict[str, str], problems: list[str]) -> dict:
    server = plan.server.merged
    mappings = plan.mappings
    return {
        "checks_failed": len(problems),
        "charsections_rows": plan.hashes.get("charsections_rows"),
        "barbershopstyle_rows": plan.hashes.get("barbershopstyle_rows"),
        "hashes": plan.hashes,
        "hidden_rows": len(server.hidden),
        "repeated_rows_dropped": server.duplicates,
        "rebuilt_textures": len(plan.rebuilt),
        "dropped_textures": len(plan.dropped),
        "remap_pairs": sum(len(m.moved) for m in mappings.values()),
        "remap_customize_pairs": sum(1 for m in mappings.values() for v in m.moved.values() if not v[2]),
        "remap_hair_colours": sum(len(m.hair_colours) for m in mappings.values()),
        "changed_styles": meaning_changes(mappings, "style"),
        "changed_features": meaning_changes(mappings, "feature"),
        "marks": {f"{r},{s}": b for (r, s), b in sorted(server.bases.items())},
        "barber_new_ids": len(plan.ledger.added) if plan.ledger else 0,
        "archives": {a.name: {"role": a.role, "files": len(a.files) + len(a.blobs), "bytes": a.size(),
                              "unchanged": a.unchanged} for a in plan.new_archives},
        "written": {k: v for k, v in sorted(written.items())},
        "saved_base": plan.base.saved if plan.base else [],
    }


def meaning_changes(mappings: dict, kind: str) -> list[dict]:
    """summary.json: every hair style or features value whose meaning the merged table changed, and what the remap
    does with it (stop: not accepted; move: to the value meaning the same; customize: at the next login)."""
    out = []

    for (race, sex, dk), m in sorted(mappings.items()):
        changed, applied = (m.changed_styles, m.styles) if kind == "style" else (m.changed_features, m.features)

        for value, (why, same) in sorted(changed.items()):
            new, customize = applied.get(value, (None, False))
            out.append({"race": race, "sex": sex, "death_knight": dk, "value": value, "why": why, "same_as": same,
                        "action": "stop" if value not in applied else "customize" if customize else f"move to {new}"})

    return out


def format_report(plan: Plan, written: dict[str, str], problems: list[str]) -> str:
    lines = ["raceforge.py customize", "=" * 22, ""]
    opts = plan.options
    lines.append(f"package: {opts.package} (commit {package_commit(opts.package) or '?'}; curation pins "
                 f"{plan.cur.commit[:12]})")
    lines.append(f"saved base: {plan.base.folder}" + (f" (saved now: {', '.join(plan.base.saved)})" if plan.base.saved
                                                       else ""))
    lines.append(f"marks: {opts.marks or 'none (stage 1)'}")
    lines.append("")
    lines.append("Where the client reads the tables:")

    for combo in plan.combos:
        parts = [f"{n} {combo.holders[n].name}" + (f" -> {combo.targets[n].name}" if combo.targets[n] is not
                                                    combo.holders[n] else "") for n in TABLES]
        lines.append(f"  {combo.label}: " + "; ".join(parts))

    lines.append("")
    lines.append("Merge (server copy, " + plan.server.label + "):")
    lines += [f"  {n}" for n in plan.server.merged.notes]
    lines.append(f"  hidden rows: {len(plan.server.merged.hidden)}")
    reasons: dict[str, int] = {}

    for h in plan.server.merged.hidden:
        reasons[h.reason] = reasons.get(h.reason, 0) + 1

    lines += [f"    {count} x {reason}" for reason, count in sorted(reasons.items())]
    lines.append(f"  rebuilt textures: {len(plan.rebuilt)}")
    lines += [f"    {r.name} from {r.source} (colour of {r.reference})" for r in list(plan.rebuilt.values())[:50]]
    lines.append(f"  textures dropped: {len(plan.dropped)}")
    lines += [f"    {d}" for d in plan.dropped[:50]]

    for (race, sex), added in sorted(plan.server.merged.marks_added.items()):
        lines.append(f"  marks race {race} {ap.SEXES[sex]}: {added.features_values} features values, "
                     f"{added.feature_rows} rows ({added.base_rows} base), {added.eye_rows} eye rows")

    lines.append("")
    lines.append("Archives:")

    for archive in plan.new_archives:
        state = "unchanged" if archive.unchanged else ("replaces the realm's" if archive.existing else "new")
        lines.append(f"  {archive.name} ({archive.role}): {len(archive.files) + len(archive.blobs)} files, "
                     f"{archive.size() / 1e6:.1f} MB, {state}")

    for key, files in sorted(plan.targets.items()):
        lines.append(f"  {plan.target_archives[key].name}: rebuilt with {', '.join(sorted(files))}")

    if plan.moved:
        lines.append(f"  {len(plan.moved)} file(s) of the table archives move to {opts.move_art}")

    lines.append("")
    lines.append("Models:")
    lines += [f"  {m}" for m in plan.model_checks]
    lines.append("")
    mappings = plan.mappings
    lines.append(f"Existing characters: {sum(len(m.moved) for m in mappings.values())} (skin, face) pair(s) move, "
                 f"{sum(1 for m in mappings.values() for v in m.moved.values() if not v[2])} of them without an "
                 f"exact match (customize at the next login); {sum(len(m.hair_colours) for m in mappings.values())} "
                 "hair colour(s) move")

    for (race, sex, dk), m in sorted(mappings.items()):
        if m.moved or m.hair_colours:
            sample = ", ".join(f"{k}->{v[:2]}{'' if v[2] else '*'}" for k, v in list(sorted(m.moved.items()))[:6])
            lines.append(f"  race {race} {ap.SEXES[sex]}{' Death Knight' if dk else ''}: {sample}"
                         + (f"; hair {m.hair_colours}" if m.hair_colours else ""))

    changes = [(kind, c) for kind in ("style", "feature") for c in meaning_changes(mappings, kind)]
    lines.append(f"Hair styles and features that changed their meaning: {len(changes)}")

    for kind, c in changes:
        lines.append(f"  race {c['race']} {ap.SEXES[c['sex']]}{' Death Knight' if c['death_knight'] else ''}: "
                     f"{'hair style' if kind == 'style' else 'features value'} {c['value']}: {c['why']} -> "
                     f"{c['action']}")

    lines.append("")
    lines.append(f"Server: {json.dumps(plan.hashes, sort_keys=True)}")
    lines.append("")

    if plan.warnings:
        lines.append("Warnings:")
        lines += [f"  - {w}" for w in plan.warnings]
        lines.append("")

    lines.append(f"Checks: {len(problems)} failed")
    lines += [f"  [FAIL] {p}" for p in problems]
    lines.append("")
    lines.append("Written:")
    lines += [f"  {v}" for k, v in sorted(written.items())]
    return "\n".join(lines) + "\n"


def run(opts: Options, config) -> tuple[Plan, dict[str, str], list[str]]:
    out_dir = os.path.abspath(opts.out)

    for flag, folder in (("--patches", opts.patches), ("--client", opts.client)):
        real = os.path.realpath(folder)

        for what, path in (("--out", out_dir), ("--base", os.path.abspath(opts.base))):
            try:
                inside = os.path.commonpath([os.path.realpath(path), real]) == real
            except ValueError:
                inside = False

            if inside:
                raise CustomizeError(f"{what} {path} is inside {flag} {folder}: the launcher would publish it")

    plan = make_plan(opts, config)

    try:
        problems = list(dict.fromkeys(plan.problems))
        written: dict[str, str] = {}
        os.makedirs(out_dir, exist_ok=True)
        install.write_manifest(out_dir, "raceforge.py customize", plan.game.patches_dir, plan.game.client_data, [],
                               False)

        need = space_needed(plan)
        free = shutil.disk_usage(out_dir).free
        keep = int(opts.keep_free_gb * 1e9)

        if not problems and free - need < keep:
            problems.append(f"--out {out_dir} has {free / 1e9:.1f} GB free; the archives need {need / 1e9:.1f} GB and "
                            f"{opts.keep_free_gb:g} GB must stay free (--keep-free-gb)")

        if not problems:
            written = write(plan, out_dir)
            problems += check_written(plan, written)

        if not problems:
            plan.ledger.save()
            install.write_json(os.path.join(out_dir, "server", "barber_ids.json"),
                               {"ids": plan.ledger.ids, "bases": plan.ledger.bases})

        install.write_manifest(out_dir, "raceforge.py customize", plan.game.patches_dir, plan.game.client_data,
                               manifest_entries(plan, written), not problems)

        with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(format_report(plan, written, problems))

        install.write_json(os.path.join(out_dir, "summary.json"), summary(plan, written, problems))
    finally:
        plan.game.close()

    return plan, written, problems
