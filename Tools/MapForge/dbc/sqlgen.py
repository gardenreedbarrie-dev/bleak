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
