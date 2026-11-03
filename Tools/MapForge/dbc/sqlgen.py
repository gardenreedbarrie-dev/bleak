"""AzerothCore world-database SQL for the map's rows, and the ids the server's SQL already uses.

AzerothCore loads Map.dbc, AreaTable.dbc, Light.dbc, WorldMapArea.dbc, BattlemasterList.dbc and PvpDifficulty.dbc
from data/dbc and then the rows of map_dbc, areatable_dbc, ... from the world database on top, by id
(LoadDBC -> DBCStorageBase::LoadFromDB -> DBCDatabaseLoader). A row the files do not have is added. So the server
needs no new DBC files: these rows are enough, and the realm's data/dbc stays as it is. The loader reads the SQL
columns by position (SELECT *), one per client column, so each INSERT lists every column in client order.
LoadingScreens.dbc is client-only; the server never loads it.

The rows are written exactly as they are in the client's files, so the client and the server agree. Every INSERT
follows a DELETE of the same ids (the repository's SQL convention), so a file can run again.
"""

from __future__ import annotations

import math
import os
import re

from . import layout
from .config import Config
from .forge import ForgeResult, bits_float

from rflib.dbc import DbcTable, to_signed  # noqa: E402

MARKER = "-- Written by MapForge"
SQL_TABLES = {layout.SERVER[name][0]: name for name in layout.SERVER}


def _text(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _float(value: float) -> str:
    text = f"{value:.9g}"
    return text if text != "-0" else "0"


def row_values(table: DbcTable, row: list[int]) -> list[str]:
    out = []

    for column, value in zip(table.schema.columns, row):
        if column.is_string:
            out.append(_text(table.string_at(value)))
        elif column.kind == "float":
            out.append(_float(bits_float(value)))
        elif column.kind == "locflags":
            out.append(str(value))
        else:
            out.append(str(to_signed(value)))

    return out


def _ids_clause(ids: list[int]) -> str:
    ids = sorted(ids)
    return f"= {ids[0]}" if len(ids) == 1 else "IN (" + ", ".join(str(i) for i in ids) + ")"


def table_sql(name: str, table: DbcTable, ids: list[int]) -> list[str]:
    sql_table, _, columns = layout.SERVER[name]
    rows = table.by_id()
    out = [f"DELETE FROM `{sql_table}` WHERE `{columns[0]}` {_ids_clause(ids)};"]
    names = ", ".join(f"`{c}`" for c in columns)
    values = [f"({', '.join(row_values(table, rows[i]))})" for i in sorted(ids)]
    out.append(f"INSERT INTO `{sql_table}` ({names}) VALUES\n" + ",\n".join(values) + ";")
    return out


def our_ids(name: str, table: DbcTable, config: Config) -> list[int]:
    """The rows of this map in a table."""
    m = config.map.id
    column = {"Map": None, "AreaTable": "continentID", "Light": "continentID", "WorldMapArea": "mapID",
              "BattlemasterList": "mapID[0]", "PvpDifficulty": "mapID"}[name]

    if column is None:
        return [m] if m in table.ids() else []

    return sorted(to_signed(r[0]) for r in table.rows if table.get(r, column) == m)


def build(tables: dict[str, DbcTable], config: Config, result: ForgeResult) -> dict[str, str]:
    """{file name: SQL text} for the install, the check and the removal."""
    m = config.map
    label = f"{m.name.name} (map {m.id}, {m.directory})"
    header = [f"{MARKER} for {label}: map {m.id} directory {m.directory}.", "--"]
    install = header + [
        "-- World database (acore_world). AzerothCore loads these rows over its data/dbc files by id, so the server",
        "-- needs no new DBC files. The client gets the same rows from the DBC patch; both must agree.",
        "-- Run bleakhold_royale_check.sql first: it lists rows with these ids that are already there.",
        "",
    ]
    remove = header + ["-- Removes what the install file adds.", ""]
    check = header + [
        "-- Read-only. Run on the world database before the install file. Every row listed here would be",
        "-- replaced by the install file: it must be one of this map's own rows (an earlier install) or nothing.",
        "",
    ]

    for name in layout.SERVER:
        if name not in tables or name not in result.changes:
            continue

        ids = our_ids(name, tables[name], config)
        sql_table, _, columns = layout.SERVER[name]

        if not ids:
            continue

        install.append(f"-- {layout.file_name(name)}")
        install += table_sql(name, tables[name], ids)
        install.append("")
        remove.append(f"DELETE FROM `{sql_table}` WHERE `{columns[0]}` {_ids_clause(ids)};")
        check.append(f"SELECT '{sql_table}' AS `table`, `{columns[0]}` AS `id` FROM `{sql_table}` "
                     f"WHERE `{columns[0]}` {_ids_clause(ids)};")

        if name == "AreaTable":
            bits = sorted(result.area_bits.values())
            check.append(f"SELECT 'areatable_dbc AreaBit' AS `table`, `ID` AS `id`, `AreaBit` FROM `areatable_dbc` "
                         f"WHERE `AreaBit` IN ({', '.join(map(str, bits))}) "
                         f"AND `ID` NOT IN ({', '.join(map(str, sorted(config.area_ids())))});")

    if m.instance_type in (1, 2):
        # MapInstanced::CreateInstance aborts the server for a dungeon or raid map without an instance_template row.
        install += ["-- instance_template: required for dungeon and raid maps (MapInstanced::CreateInstance)",
                    f"DELETE FROM `instance_template` WHERE `map` = {m.id};",
                    f"INSERT INTO `instance_template` (`map`, `parent`, `script`, `allowMount`) VALUES "
                    f"({m.id}, 0, '', 0);", ""]
        remove.append(f"DELETE FROM `instance_template` WHERE `map` = {m.id};")
        check.append(f"SELECT 'instance_template' AS `table`, `map` AS `id` FROM `instance_template` "
                     f"WHERE `map` = {m.id};")

    if m.instance_type == 3:
        install += ["-- The battleground itself (battleground_template with its start graveyards, the script) comes "
                    "with", "-- the server code that runs the match; BattlegroundMgr::LoadBattlegroundTemplates "
                    "needs the", "-- BattlemasterList row above for it.", ""]

    def finish(lines: list[str]) -> str:
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines) + "\n"

    return {"bleakhold_royale.sql": finish(install), "bleakhold_royale_check.sql": finish(check),
            "bleakhold_royale_remove.sql": finish(remove)}


# --- the ids the server's SQL already uses -----------------------------------------------------------------------

_INSERT = re.compile(r"\b(?:INSERT|REPLACE)\s+(?:IGNORE\s+)?INTO\s+`?(\w+)`?\s*(\([^)]*\))?\s*VALUES\s*", re.I)


def _tuples(text: str, start: int):
    """The value tuples of the INSERT whose VALUES ends at start, as lists of raw value strings."""
    i = start
    n = len(text)

    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1

        if i >= n or text[i] != "(":
            return

        i += 1
        values = []
        current = []
        quote = None

        while i < n:
            c = text[i]

            if quote:
                if c == "\\" and i + 1 < n:
                    current.append(text[i:i + 2])
                    i += 2
                    continue

                if c == quote:
                    if i + 1 < n and text[i + 1] == quote:
                        current.append(c * 2)
                        i += 2
                        continue
                    quote = None

                current.append(c)
            elif c in "'\"":
                quote = c
                current.append(c)
            elif c == ",":
                values.append("".join(current).strip())
                current = []
            elif c == ")":
                values.append("".join(current).strip())
                i += 1
                break
            else:
                current.append(c)

            i += 1

        yield values


def scan_server_sql(roots: list[str], skip_directory: str | None = None) -> dict[str, dict[int, str]]:
    """{table name: {id: file}} of the rows the .sql files under roots insert into map_dbc, areatable_dbc, ... .
    Files MapForge wrote for skip_directory (this map) are skipped: those rows are this map's own."""
    found: dict[str, dict[int, str]] = {}

    for root in roots:
        for folder, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))

            for filename in sorted(files):
                if not filename.lower().endswith(".sql"):
                    continue

                path = os.path.join(folder, filename)

                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except OSError:
                    continue

                if skip_directory and text.startswith(MARKER) and f"directory {skip_directory}." in text[:400]:
                    continue

                if not any(t in text for t in SQL_TABLES):
                    continue

                for match in _INSERT.finditer(text):
                    name = SQL_TABLES.get(match.group(1).lower())

                    if not name:
                        continue

                    for values in _tuples(text, match.end()):
                        try:
                            row_id = int(values[0])
                        except (ValueError, IndexError):
                            continue

                        found.setdefault(name, {}).setdefault(row_id, os.path.relpath(path, root))

    return found


# --- the server's POI table (bh_royale_poi) from the terrain's pois.json ------------------------------------------

POI_TABLE = "bh_royale_poi"
POI_COLUMNS = ("map", "id", "kind", "name", "x", "y", "z", "o", "radius", "weight", "param")
POI_FILE = "bh_royale_poi.sql"
POI_TABLE_FILE = "bh_royale_poi_table.sql"
# POI kinds the Royale server reads (terrain/spec.py POI_KINDS): allowed params, and whether a weight is required.
ROYALE_POI_KINDS = {
    "lobby": ((0,), False), "landmark": ((0,), False), "crate": ((1, 2), False), "orb_shadow": ((0,), False),
    "orb_buff": ((1, 2, 3), False), "supply_site": ((0,), False), "final_site": ((0,), True),
    "crossing": ((0,), False),
}
FINAL_SITE_MAX_DIST = 490.0  # Storm.FinalSiteMaxDist: the storm chain reaches 540 yd from the map centre


class PoiError(Exception):
    pass


def poi_table_sql() -> str:
    """CREATE TABLE for bh_royale_poi (world database). The server code owns the table; this is its layout."""
    return "\n".join([
        f"{MARKER}: the layout of `{POI_TABLE}` (world database), the Royale map points (pois.json).",
        f"CREATE TABLE IF NOT EXISTS `{POI_TABLE}` (",
        "    `map` SMALLINT UNSIGNED NOT NULL,",
        "    `id` INT UNSIGNED NOT NULL,",
        "    `kind` VARCHAR(32) NOT NULL,",
        "    `name` VARCHAR(64) NOT NULL DEFAULT '',",
        "    `x` FLOAT NOT NULL,",
        "    `y` FLOAT NOT NULL,",
        "    `z` FLOAT NOT NULL,",
        "    `o` FLOAT NOT NULL DEFAULT 0,",
        "    `radius` FLOAT NOT NULL DEFAULT 0,",
        "    `weight` INT UNSIGNED NOT NULL DEFAULT 0,",
        "    `param` INT NOT NULL DEFAULT 0,",
        "    PRIMARY KEY (`map`, `id`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
    ]) + "\n"


def _poi_float(value: float, digits: int) -> str:
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def poi_rows(doc: dict, map_id: int | None = None) -> list[tuple]:
    """(map, id, kind, name, x, y, z, o, radius, weight, param) per POI. name is the title players see (the POI name
    when it has none); o is the facing in radians, 0..2pi."""
    map_id = doc.get("map_id") if map_id is None else map_id

    if not isinstance(map_id, int) or not 0 < map_id <= 0xFFFF:
        raise PoiError("pois.json has no map id (set map.id in the terrain spec) and none was given")

    rows = []
    seen = set()

    for p in doc.get("pois", []):
        poi_id = p.get("id")

        if not isinstance(poi_id, int) or not 0 < poi_id <= 0x7FFFFFFF or poi_id in seen:
            raise PoiError(f"poi {p.get('name')!r}: id {poi_id!r} is missing, out of range or used twice")

        seen.add(poi_id)
        name = p.get("title") or p["name"]

        if len(name) > 64:
            raise PoiError(f"poi {p['name']!r}: name longer than 64 characters")

        o = math.radians(float(p.get("facing", 0.0)) % 360.0)
        rows.append((map_id, poi_id, p["kind"], name, float(p["x"]), float(p["y"]), float(p["z"]), o,
                     float(p.get("radius", 0.0)), int(p.get("weight", 0)), int(p.get("param", 0))))

    return sorted(rows, key=lambda r: r[1])


def poi_sql(doc: dict, map_id: int | None = None, label: str = "") -> str:
    """The rows of bh_royale_poi for one map: DELETE of the map's rows, then one INSERT (runs again safely)."""
    rows = poi_rows(doc, map_id)
    map_id = rows[0][0] if rows else (doc.get("map_id") if map_id is None else map_id)
    lines = [f"{MARKER}: `{POI_TABLE}` rows for {label or doc.get('map_directory', '')} (map {map_id}) from "
             "pois.json.",
             f"-- World database. Run {POI_TABLE_FILE} (or the server's own CREATE TABLE) first. z is the spawn",
             "-- height (the server snaps it to the floor below z + 2); o is in radians.",
             f"DELETE FROM `{POI_TABLE}` WHERE `map` = {map_id};"]

    if rows:
        names = ", ".join(f"`{c}`" for c in POI_COLUMNS)
        values = [f"({r[0]}, {r[1]}, {_text(r[2])}, {_text(r[3])}, {_poi_float(r[4], 3)}, {_poi_float(r[5], 3)}, "
                  f"{_poi_float(r[6], 3)}, {_poi_float(r[7], 4)}, {_poi_float(r[8], 2)}, {r[9]}, {r[10]})"
                  for r in rows]
        lines.append(f"INSERT INTO `{POI_TABLE}` ({names}) VALUES")
        lines.append(",\n".join(values) + ";")

    return "\n".join(lines) + "\n"


def royale_poi_problems(doc: dict) -> list[str]:
    """What the Royale server's startup validation (royale-spec.md 6.2, item 7) and the map rules would refuse:
    unknown params, 1 lobby, >= 3 landmarks, 2 Shadow Sight orbs, >= 44 common crate spots, >= 2 supply sites,
    >= 1 final site, and every final site at most 490 yd from the map centre."""
    problems = []
    pois = doc.get("pois", [])
    bounds = doc.get("world_bounds")

    if not bounds:
        return ["pois.json has no world_bounds (rebuild the terrain)"]

    cx = (bounds["min_x"] + bounds["max_x"]) * 0.5
    cy = (bounds["min_y"] + bounds["max_y"]) * 0.5
    count: dict[str, int] = {}

    for p in pois:
        kind = p["kind"]
        rule = ROYALE_POI_KINDS.get(kind)

        if rule is None:
            continue

        params, needs_weight = rule

        if p.get("param", 0) not in params:
            problems.append(f"poi {p['name']!r} ({kind}): param {p.get('param')} is not {params}")

        if needs_weight != (p.get("weight", 0) > 0):
            problems.append(f"poi {p['name']!r} ({kind}): weight {p.get('weight', 0)}")

        key = f"crate:{p.get('param')}" if kind == "crate" else kind
        count[key] = count.get(key, 0) + 1

        if kind == "final_site":
            dist = math.hypot(p["x"] - cx, p["y"] - cy)

            if dist > FINAL_SITE_MAX_DIST:
                problems.append(f"final site {p['name']!r} is {dist:.1f} yd from the centre ({cx:.2f}, {cy:.2f}); "
                                f"the storm reaches final sites up to {FINAL_SITE_MAX_DIST:g}")

    for key, low, high, what in (("lobby", 1, 1, "lobby"), ("landmark", 3, None, "landmarks"),
                                 ("orb_shadow", 2, 2, "Shadow Sight orbs"), ("crate:1", 44, None, "common crates"),
                                 ("supply_site", 2, None, "supply sites"), ("final_site", 1, None, "final sites")):
        n = count.get(key, 0)

        if n < low or (high is not None and n > high):
            want = f"{low}" if high == low else f"at least {low}"
            problems.append(f"{n} {what}, want {want}")

    return problems
