"""Character customization packages: more faces, hair, skins, markings and HD models for the stock races.

A package (for example Ascension Character Customization) is a folder with DBFilesClient\\*.dbc in the client's
3.3.5a layouts next to its art folders (Character\\, Textures\\, ...). RaceForge merges its tables into the user's
DBCs before it adds the Bleakhold races, so the new races are cloned from the merged template races and get every
option too, and packs the art into patch archives.

Merge rules, per table:

- tables keyed by race (CharSections, CharHairGeosets, CharacterFacialHairStyles, BarberShopStyle,
  EmotesTextSound): for every race the package has rows for, the package's rows replace the user's; the rows of
  every other race (the user's own custom races) are kept. Rows for a race that is not in the user's ChrRaces, or for
  one of the races RaceForge is about to add, are left out;
- tables keyed by id (HelmetGeosetVisData, CreatureDisplayInfoExtra): the package's row replaces the user's row with
  the same id, new ids are added, the user's other rows are kept.

Strings are copied into the user's string block (offsets differ between files). Ids of race-keyed rows are kept
where they are free and renumbered after the highest id where they clash with a kept row: nothing in the client or
the server refers to these rows by id except BarberShopStyle, which both read from the same merged file.
CharSections is sorted by (race, sex, section, variation, color) because the client's BuildComponentArray groups
consecutive rows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import schema_access
from .dbc import DbcError, DbcTable, to_signed

RACE_TABLES = {
    "CharSections": "raceID",
    "CharHairGeosets": "raceID",
    "CharacterFacialHairStyles": "raceID",
    "BarberShopStyle": "race",
    "EmotesTextSound": "raceID",
}
ID_TABLES = ("HelmetGeosetVisData", "CreatureDisplayInfoExtra")
TABLES = tuple(RACE_TABLES) + ID_TABLES

CHAR_SECTIONS_KEY = ("raceID", "sexID", "baseSection", "variationIndex", "colorIndex")

# Folders of a package that are not art.
NOT_ART = ("dbfilesclient",)


class CustomizeError(Exception):
    pass


@dataclass
class MergeResult:
    tables: dict[str, DbcTable] = field(default_factory=dict)
    notes: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    package_races: dict[str, list[int]] = field(default_factory=dict)

    def note(self, table: str, text: str):
        self.notes.setdefault(table, []).append(text)


def find_package_dbc(package_dir: str, name: str) -> str | None:
    wanted = f"{name}.dbc".lower()

    for folder in (os.path.join(package_dir, "DBFilesClient"), package_dir):
        if not os.path.isdir(folder):
            continue

        for entry in os.listdir(folder):
            if entry.lower() == "dbfilesclient" and folder == package_dir:
                continue

            if entry.lower() == wanted and os.path.isfile(os.path.join(folder, entry)):
                return os.path.join(folder, entry)

    return None


def load_package(package_dir: str) -> dict[str, DbcTable]:
    if not os.path.isdir(package_dir):
        raise CustomizeError(f"{package_dir} is not a folder")

    tables = {}

    for name in TABLES:
        path = find_package_dbc(package_dir, name)

        if path:
            try:
                tables[name] = DbcTable.read(path, schema_access.get(name))
            except DbcError as e:
                raise CustomizeError(f"customization package: {e}") from None

    if not tables:
        raise CustomizeError(f"{package_dir}: no customization tables found ({', '.join(n + '.dbc' for n in TABLES)} in DBFilesClient)")

    return tables


def copy_row(source: DbcTable, target: DbcTable, row: list[int]) -> list[int]:
    """The row with its string columns moved into target's string block."""
    out = list(row)

    for i, column in enumerate(source.schema.columns):
        if column.is_string:
            out[i] = target.add_string(source.string_at(row[i]))

    return out


def sort_char_sections(table: DbcTable) -> bool:
    columns = [table.col(c) for c in CHAR_SECTIONS_KEY]

    def key(row):
        return tuple(to_signed(row[c]) for c in columns)

    keys = [key(r) for r in table.rows]

    if all(keys[i] <= keys[i + 1] for i in range(len(keys) - 1)):
        return False

    table.rows.sort(key=key)
    return True


def merge_race_table(name: str, base: DbcTable, package: DbcTable, races: set[int], result: MergeResult) -> DbcTable:
    race_column = RACE_TABLES[name]
    package_races = sorted({package.get(r, race_column) for r in package.rows})
    taken = [r for r in package_races if r in races]
    skipped = [r for r in package_races if r not in races]
    result.package_races[name] = taken

    if skipped:
        result.note(name, f"package rows for races {skipped} left out (not in ChrRaces, or added by RaceForge)")

    merged = DbcTable(base.schema, [], bytes(base.strings), base.source)
    kept = [list(r) for r in base.rows if base.get(r, race_column) not in taken]
    merged.rows.extend(kept)
    used = {to_signed(r[0]) for r in kept} if not base.schema.generated_id else set()
    next_id = max(used, default=0) + 1
    added = 0
    renumbered = 0
    pending = []

    for row in package.rows:
        if package.get(row, race_column) not in taken:
            continue

        new = copy_row(package, merged, row)

        if not base.schema.generated_id:
            row_id = to_signed(new[0])

            if row_id in used or row_id <= 0:
                pending.append(new)
                continue

            used.add(row_id)

        merged.rows.append(new)
        added += 1

    # Clashing ids get fresh ones after every id in use, so no id is given twice.
    if pending:
        next_id = max(next_id, max(used, default=0) + 1)

        for new in pending:
            merged.set(new, "id", next_id)
            used.add(next_id)
            next_id += 1
            merged.rows.append(new)
            added += 1
            renumbered += 1

    replaced = len(base.rows) - len(kept)
    result.note(name, f"races {taken}: {replaced} rows replaced by {added} package rows" + (f" ({renumbered} with new ids)" if renumbered else "")
                + f"; {len(kept)} rows of other races kept")

    if name == "CharSections" and sort_char_sections(merged):
        result.note(name, "sorted by (race, sex, section, variation, color)")

    return merged


def merge_id_table(name: str, base: DbcTable, package: DbcTable, result: MergeResult) -> DbcTable:
    merged = DbcTable(base.schema, [], bytes(base.strings), base.source)
    package_rows = {}

    for row in package.rows:
        package_rows[to_signed(row[0])] = row

    base_ids = {to_signed(r[0]) for r in base.rows}
    rows = {}

    for row in base.rows:
        row_id = to_signed(row[0])
        rows[row_id] = list(row) if row_id not in package_rows else copy_row(package, merged, package_rows[row_id])

    for row_id, row in package_rows.items():
        if row_id not in rows:
            rows[row_id] = copy_row(package, merged, row)

    merged.rows = [rows[i] for i in sorted(rows)]
    replaced = len(base_ids & set(package_rows))
    result.note(name, f"{replaced} rows replaced, {len(set(package_rows) - base_ids)} added, {len(base_ids - set(package_rows))} of yours kept")
    return merged


def merge(base_tables: dict[str, DbcTable], package_dir: str, new_races: set[int]) -> MergeResult:
    """Merge the package's tables into the user's (base_tables: name -> table, ChrRaces included). Returns the merged
    tables; base_tables is not changed."""
    package = load_package(package_dir)
    result = MergeResult()
    chr_races = base_tables.get("ChrRaces")

    if chr_races is None:
        raise CustomizeError("ChrRaces.dbc is needed to merge a customization package")

    races = {r for r in chr_races.ids() if r not in new_races}

    for name, table in package.items():
        result.warnings.extend(table.warnings)
        base = base_tables.get(name)

        if base is None:
            # The user has no copy of this table: the package's whole table is used.
            base = DbcTable.empty(schema_access.get(name))
            result.note(name, "not in your DBCs: the package's table is used")

        if name in RACE_TABLES:
            result.tables[name] = merge_race_table(name, base, table, races, result)
        else:
            result.tables[name] = merge_id_table(name, base, table, result)

    missing = [n for n in TABLES if n not in package]

    if missing:
        result.warnings.append(f"customization package has no {', '.join(n + '.dbc' for n in missing)}; yours are kept")

    return result


def check(merged_dir: str, user_dir: str, package_dir: str, new_races: set[int]) -> list[tuple[str, str, str]]:
    """Checks of a merged folder against the user's DBCs and the package: (status, name, detail)."""
    from .forge import find_dbc

    checks = []
    package = load_package(package_dir)
    user_races = DbcTable.read(find_dbc(user_dir, "ChrRaces"), schema_access.get("ChrRaces"))
    races = {r for r in user_races.ids() if r not in new_races}

    for name, pack in package.items():
        merged_path = find_dbc(merged_dir, name)

        if not merged_path:
            checks.append(("FAIL", f"customization: {name}.dbc merged", "missing from the merged DBCs"))
            continue

        merged = DbcTable.read(merged_path, schema_access.get(name))
        user_path = find_dbc(user_dir, name)
        user = DbcTable.read(user_path, schema_access.get(name)) if user_path else DbcTable.empty(schema_access.get(name))

        def content(table: DbcTable, row: list[int], skip_id: bool) -> tuple:
            values = []

            for i, column in enumerate(table.schema.columns):
                if i == 0 and skip_id and not table.schema.generated_id:
                    continue

                values.append(table.string_at(row[i]) if column.is_string else row[i])

            return tuple(values)

        def multiset(table: DbcTable, rows, skip_id: bool) -> dict:
            out = {}

            for row in rows:
                key = content(table, row, skip_id)
                out[key] = out.get(key, 0) + 1

            return out

        problems = []

        if name in RACE_TABLES:
            column = RACE_TABLES[name]
            taken = {pack.get(r, column) for r in pack.rows} & races
            want_pack = multiset(pack, [r for r in pack.rows if pack.get(r, column) in taken], True)
            want_user = multiset(user, [r for r in user.rows if user.get(r, column) not in taken], True)
            have_pack = multiset(merged, [r for r in merged.rows if merged.get(r, column) in taken], True)
            have_user = multiset(merged, [r for r in merged.rows if merged.get(r, column) not in taken], True)

            if have_pack != want_pack:
                problems.append(f"the rows of races {sorted(taken)} are not exactly the package's")

            if have_user != want_user:
                problems.append("the rows of the other races changed")

            detail = f"races {sorted(taken)} from the package"
        else:
            merged_by_id = merged.by_id()
            pack_by_id = pack.by_id()

            for row_id, row in pack_by_id.items():
                other = merged_by_id.get(row_id)

                if other is None or content(merged, other, False) != content(pack, row, False):
                    problems.append(f"row {row_id} is not the package's")
                    break

            for row in user.rows:
                row_id = to_signed(row[0])

                if row_id not in pack_by_id and (row_id not in merged_by_id or content(merged, merged_by_id[row_id], False) != content(user, row, False)):
                    problems.append(f"your row {row_id} changed")
                    break

            detail = f"{len(pack_by_id)} package rows"

        if not merged.schema.generated_id:
            ids = [to_signed(r[0]) for r in merged.rows]

            if len(ids) != len(set(ids)):
                problems.append("duplicate ids")

        checks.append(("FAIL" if problems else "PASS", f"customization: {name} merged ({detail})", "; ".join(problems)))

    return checks


def art_files(package_dir: str) -> list[tuple[str, str, int]]:
    """The package's art: every file under its subfolders except DBFilesClient and hidden folders, as (archive name,
    path, size). Files at the top of the package (README, LICENSE) are not art."""
    import mpqpack

    files = []

    for entry in sorted(os.listdir(package_dir)):
        path = os.path.join(package_dir, entry)

        if not os.path.isdir(path) or entry.startswith(".") or entry.lower() in NOT_ART:
            continue

        for name, file_path, size in mpqpack.list_folder(path):
            files.append((f"{entry}\\{name}", file_path, size))

    files.sort(key=lambda item: mpqpack.name_key(item[0]))
    seen = {}

    for name, _, _ in files:
        key = mpqpack.name_key(name)

        if key in seen:
            raise CustomizeError(f"{name} and {seen[key]} are the same file to the client (case and slashes are ignored)")

        seen[key] = name

    return files
