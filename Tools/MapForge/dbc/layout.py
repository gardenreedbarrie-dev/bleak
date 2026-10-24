"""Table layouts: the client's (generated into dbc/schemas.py from WoW/Source/DB/Rec) and the server's.

The client aborts on a DBC whose column count or row size differs from its record class (WowClientDB_Common::Load),
so the Rec classes decide every layout MapForge writes. RaceForge's parser (rflib/recparse.py) reads them;
`package.py schemas --write` regenerates dbc/schemas.py, and tests/test_dbc_layout.py checks it against the Rec
folder whenever the decompilation is next to the tool.

The server side (AzerothCore) loads each of these tables from data/dbc and then from a world-database table of the
same columns (DBCDatabaseLoader: `SELECT * FROM <table>_dbc`, one SQL column per format character, so every client
column has an SQL column, in client order). SERVER holds the format string of DBCfmt.h and those SQL column names.
"""

from __future__ import annotations

import os

from . import schemas as _generated

from rflib import recparse  # noqa: E402  (Tools/RaceForge, added to sys.path by the package)

# Tables MapForge writes, or reads to check references. Order is the order of dbc/schemas.py.
TABLES = (
    "AreaTable",
    "BattlemasterList",
    "Light",
    "LightParams",
    "LightSkybox",
    "LoadingScreens",
    "Map",
    "MapDifficulty",
    "PvpDifficulty",
    "SoundAmbience",
    "WorldMapArea",
    "ZoneIntroMusicTable",
    "ZoneMusic",
)

# Locale slots of a 3.3.5a localized string, in file order (the client keeps slot s_locale; 9-15 are unused).
LOCALES = ("enUS", "koKR", "frFR", "deDE", "zhCN", "zhTW", "esES", "esMX", "ruRU")
LOCALE_SLOTS = 16

# The world database names the 16 slots after a later client's locale list; the loader reads them by position, so
# slot i is the i-th _Lang_ column whatever its name (slot 1, koKR, is in `..._Lang_enGB`).
SQL_LOCALE_SUFFIXES = ("enUS", "enGB", "koKR", "frFR", "deDE", "enCN", "zhCN", "enTW", "zhTW", "esES", "esMX",
                       "ruRU", "ptPT", "ptBR", "itIT", "Unk")


def _sql_columns(*spec) -> tuple[str, ...]:
    out = []

    for item in spec:
        if isinstance(item, tuple):
            out.extend(f"{item[0]}_Lang_{suffix}" for suffix in SQL_LOCALE_SUFFIXES)
            out.append(f"{item[0]}_Lang_Mask")
        else:
            out.append(item)

    return tuple(out)


# name: (world-database table, DBCfmt.h format, SQL columns). Format characters: n index, i int, f float, s string,
# x skipped, d sorted index; the SQL table has a column for every character, skipped ones included.
SERVER = {
    "Map": ("map_dbc", "nxiixssssssssssssssssxixxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxixiffxixi", _sql_columns(
        "ID", "Directory", "InstanceType", "Flags", "PVP", ("MapName",), "AreaTableID", ("MapDescription0",),
        ("MapDescription1",), "LoadingScreenID", "MinimapIconScale", "CorpseMapID", "CorpseX", "CorpseY",
        "TimeOfDayOverride", "ExpansionID", "RaidOffset", "MaxPlayers")),
    "AreaTable": ("areatable_dbc", "niiiixxxxxissssssssssssssssxiiiiixxx", _sql_columns(
        "ID", "ContinentID", "ParentAreaID", "AreaBit", "Flags", "SoundProviderPref", "SoundProviderPrefUnderwater",
        "AmbienceID", "ZoneMusic", "IntroSound", "ExplorationLevel", ("AreaName",), "FactionGroupMask",
        "LiquidTypeID_1", "LiquidTypeID_2", "LiquidTypeID_3", "LiquidTypeID_4", "MinElevation",
        "Ambient_Multiplier", "Lightid")),
    "Light": ("light_dbc", "nifffxxxxxxxxxx", _sql_columns(
        "ID", "ContinentID", "X", "Y", "Z", "FalloffStart", "FalloffEnd",
        *(f"LightParamsID_{i}" for i in range(1, 9)))),
    "WorldMapArea": ("worldmaparea_dbc", "xinxffffixx", _sql_columns(
        "ID", "MapID", "AreaID", "AreaName", "LocLeft", "LocRight", "LocTop", "LocBottom", "DisplayMapID",
        "DefaultDungeonFloor", "ParentWorldMapID")),
    "BattlemasterList": ("battlemasterlist_dbc", "niiiiiiiiixssssssssssssssssxiixx", _sql_columns(
        "ID", *(f"MapID_{i}" for i in range(1, 9)), "InstanceType", "GroupsAllowed", ("Name",), "MaxGroupSize",
        "HolidayWorldState", "Minlevel", "Maxlevel")),
    "PvpDifficulty": ("pvpdifficulty_dbc", "diiiii", _sql_columns(
        "ID", "MapID", "RangeIndex", "MinLevel", "MaxLevel", "Difficulty")),
}

_cache: dict[str, recparse.TableSchema] = {}


def get(name: str) -> recparse.TableSchema:
    """The client layout of a table, checked against its column count and row size."""
    if name not in _cache:
        filename, num_columns, row_size, generated_id, columns = _generated.SCHEMAS[name]
        schema = recparse.TableSchema(name, filename, num_columns, row_size, generated_id,
                                      [recparse.Column(*c) for c in columns])
        recparse.check_schema(schema)
        _cache[name] = schema

    return _cache[name]


def file_name(name: str) -> str:
    """Map.dbc for Map."""
    return get(name).filename.split("\\")[-1]


def archive_name(name: str) -> str:
    r"""DBFilesClient\Map.dbc for Map."""
    return get(name).filename


def default_rec_dir() -> str | None:
    """WoW/Source/DB/Rec of the checkout MapForge runs from, if it is there."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                        "WoW", "Source", "DB", "Rec")
    return path if os.path.isdir(path) else None


def emit_schemas_module(rec_dir: str) -> str:
    """Source text of dbc/schemas.py for TABLES."""
    lines = [
        '"""DBC layouts of the tables MapForge uses, generated from WoW/Source/DB/Rec by `package.py schemas --write`.',
        "",
        "Do not edit by hand: tests/test_dbc_layout.py regenerates this from the client's Rec classes and compares.",
        "Each entry: file name, s_numColumns, s_rowSize, s_generatedID, columns as (name, kind, size).",
        '"""',
        "",
        "SCHEMAS = {",
    ]

    for name in TABLES:
        schema = recparse.load_rec(rec_dir, name)
        lines.append(f"    {name!r}: ({schema.filename!r}, {schema.num_columns}, {schema.row_size}, "
                     f"{schema.generated_id}, (")

        for column in schema.columns:
            lines.append(f"        ({column.name!r}, {column.kind!r}, {column.size}),")

        lines.append("    )),")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)
