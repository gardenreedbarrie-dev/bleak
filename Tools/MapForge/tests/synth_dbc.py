"""Synthetic 3.3.5a-shaped DBCs for the tests. No Blizzard data: every id, name and value here is made up.

The files follow the client's layouts (dbc/schemas.py, checked against WoW/Source/DB/Rec) but are packed with
struct directly, independently of rflib.dbc, so the tests check the tool's reader against a second writer. The
"realm" they sketch: a world map 0, a battleground 489 with zone 3277, a raid 532 with a dark light set, and the
rows those reference.
"""

from __future__ import annotations

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from dbc import config as configmod  # noqa: E402
from dbc import forge as forgemod  # noqa: E402
from dbc import layout  # noqa: E402

from rflib.dbc import DbcTable  # noqa: E402

LOC_FLAGS = 0xFF01FE  # what stock 3.3.5a files carry in the localized-string flags column


def _f(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", float(value)))[0]


class Packer:
    """Writes one WDBC file from rows of python values: ints, floats, str, or a 16-slot list for a localized
    string (the flags column is added by the packer)."""

    def __init__(self, name: str):
        self.schema = layout.get(name)
        self.rows: list[list[int]] = []
        self.strings = bytearray(b"\0")

    def _offset(self, text: str) -> int:
        if text == "":
            return 0

        data = text.encode("utf-8")
        offset = len(self.strings)
        self.strings += data + b"\0"
        return offset

    def row(self, *values):
        out = []
        columns = iter(self.schema.columns)

        for value in values:
            column = next(columns)

            if isinstance(value, list):  # a localized string: 16 texts, then the flags column
                if len(value) != 16 or column.kind != "locstr":
                    raise ValueError(f"{self.schema.name}.{column.name}: expected a localized string here")

                out.append(self._offset(value[0]))

                for text in value[1:]:
                    next(columns)
                    out.append(self._offset(text))

                flags = next(columns)

                if flags.kind != "locflags":
                    raise ValueError(f"{self.schema.name}: localized string not followed by its flags column")

                out.append(LOC_FLAGS)
            elif isinstance(value, str):
                if not column.is_string:
                    raise ValueError(f"{self.schema.name}.{column.name} is not a string column")

                out.append(self._offset(value))
            elif isinstance(value, float):
                out.append(_f(value))
            else:
                out.append(value & 0xFFFFFFFF)

        leftover = list(columns)

        if leftover:
            raise ValueError(f"{self.schema.name}: {len(leftover)} columns not filled ({leftover[0].name})")

        self.rows.append(out)
        return self

    def pack(self) -> bytes:
        fmt = struct.Struct("<" + "".join("B" if c.size == 1 else "I" for c in self.schema.columns))
        out = bytearray(struct.pack("<4sIIII", b"WDBC", len(self.rows), self.schema.num_columns,
                                    self.schema.row_size, len(self.strings)))

        for row in self.rows:
            out += fmt.pack(*row)

        out += self.strings
        return bytes(out)


def loc(text: str) -> list[str]:
    return [text] * 9 + [""] * 7


def build_tables() -> dict[str, bytes]:
    """{table name: file bytes} of the made-up realm."""
    out = {}

    maps = Packer("Map")
    #        id   dir           type flags pvp  name                     area  desc0     desc1      screen scale
    maps.row(0, "Azeroth", 0, 0, 0, loc("Azeroth"), 0, loc(""), loc(""), 10, 1.0,
             #  corpsemap cx   cy   tod  exp raid maxplayers
             -1 & 0xFFFFFFFF, 0.0, 0.0, -1 & 0xFFFFFFFF, 0, 0, 0)
    maps.row(489, "WarsongGulch", 3, 0, 1, loc("Warsong Gulch"), 3277, loc("The gulch."), loc("The gulch."), 10,
             1.0, 0, 1000.0, 2000.0, -1 & 0xFFFFFFFF, 0, 0, 10)
    maps.row(532, "Karazhan", 2, 0, 0, loc("Karazhan"), 3457, loc(""), loc(""), 11, 1.0,
             0, 100.0, 200.0, 0, 1, 0, 10)
    out["Map"] = maps.pack()

    areas = Packer("AreaTable")
    #         id continent parent bit flags sndPref sndPrefUw ambience music intro lvl name  faction liquid[4]
    areas.row(12, 0, 0, 3, 0x40, 2, 3, 40, 50, 60, 10, loc("Elwynn Fjord"), 0, 0, 0, 0, 0, -500.0, 0.0, 0)
    areas.row(3277, 489, 0, 15, 0x4000400, 2, 3, 40, 50, 60, 0, loc("Warsong Gulch"), 0, 0, 0, 0, 0, -500.0,
              0.0, 0)
    areas.row(3457, 532, 0, 16, 0x2000000, 2, 3, 41, 51, 0, 0, loc("Karazhan"), 0, 0, 0, 0, 0, -500.0, 0.0, 0)
    out["AreaTable"] = areas.pack()

    screens = Packer("LoadingScreens")
    screens.row(10, "WarsongGulch", "Interface\\Glues\\LoadingScreens\\LoadingScreenWarsong.blp", 1)
    screens.row(11, "Karazhan", "Interface\\Glues\\LoadingScreens\\LoadingScreenKarazhan.blp", 0)
    out["LoadingScreens"] = screens.pack()

    light = Packer("Light")
    light.row(1, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 10, 10, 10, 10, 10, 10, 10, 10)
    light.row(20, 532, 0.0, 0.0, 0.0, 0.0, 0.0, 55, 55, 55, 55, 60, 55, 55, 55)
    light.row(30, 489, 0.0, 0.0, 0.0, 0.0, 0.0, 10, 10, 10, 10, 10, 10, 10, 10)
    light.row(31, 489, 1000.0, 1000.0, 50.0, 100.0, 300.0, 60, 60, 60, 60, 60, 60, 60, 60)  # a zone light
    out["Light"] = light.pack()

    params = Packer("LightParams")
    params.row(10, 0, 0, 0, 0.5, 0.3, 0.9, 0.3, 0.9)
    params.row(55, 1, 7, 0, 0.5, 0.3, 0.9, 0.3, 0.9)  # shows the smoky sky
    params.row(60, 0, 8, 0, 0.5, 0.3, 0.9, 0.3, 0.9)  # shows the death sky
    out["LightParams"] = params.pack()

    skyboxes = Packer("LightSkybox")
    skyboxes.row(7, "Environments\\Stars\\WintergraspSmokySky.M2", 0)
    skyboxes.row(8, "Environments\\Stars\\DeathSkybox.M2", 0)
    out["LightSkybox"] = skyboxes.pack()

    wma = Packer("WorldMapArea")
    wma.row(400, 489, 3277, "WarsongGulch", 1500.0, 500.0, 2000.0, 500.0, -1 & 0xFFFFFFFF, 0, -1 & 0xFFFFFFFF)
    out["WorldMapArea"] = wma.pack()

    bml = Packer("BattlemasterList")
    neg = -1 & 0xFFFFFFFF
    bml.row(2, 489, neg, neg, neg, neg, neg, neg, neg, 3, 1, loc("Warsong Gulch"), 5, 0, 10, 80)
    out["BattlemasterList"] = bml.pack()

    pvp = Packer("PvpDifficulty")
    pvp.row(100, 489, 0, 10, 19, 0)
    pvp.row(101, 489, 7, 80, 80, 0)
    out["PvpDifficulty"] = pvp.pack()

    ambience = Packer("SoundAmbience")
    ambience.row(40, 7001, 7002)
    ambience.row(41, 7003, 7004)
    out["SoundAmbience"] = ambience.pack()

    music = Packer("ZoneMusic")
    music.row(50, "ZoneWarsong", 90000, 90000, 120000, 120000, 8001, 8002)
    music.row(51, "ZoneKara", 90000, 90000, 120000, 120000, 8003, 8004)
    out["ZoneMusic"] = music.pack()

    intro = Packer("ZoneIntroMusicTable")
    intro.row(60, "IntroWarsong", 8101, 1, 60)
    out["ZoneIntroMusicTable"] = intro.pack()

    return out


def write_tables(folder: str) -> dict[str, bytes]:
    tables = build_tables()
    os.makedirs(folder, exist_ok=True)

    for name, data in tables.items():
        with open(os.path.join(folder, layout.file_name(name)), "wb") as f:
            f.write(data)

    return tables


def default_config() -> dict:
    """A config like bleakhold_royale.json, with templates that exist in the synthetic tables."""
    return {
        "map": {
            "id": 901, "directory": "BleakholdRoyale", "template": 489, "name": "Bleakhold Royale",
            "instance_type": 3, "pvp": 1, "flags": 0, "corpse_map": -1, "expansion": 0, "max_players": 40,
        },
        "zone": {
            "id": 5100, "template": 3277, "name": "Bleakhold Royale",
            "set_flags": ["ARENA"], "subzones": [],
            # bleakhold_royale.json's list: every template flag that changes the rules (forge.check fails on any
            # that remains besides HARMLESS_TEMPLATE_FLAGS).
            "clear_flags": ["SANCTUARY", "OUTLAND", "OUTLAND2", "CAPITAL", "SLAVE_CAPITAL", "SLAVE_CAPITAL2", "CITY",
                            "TOWN", "REST_ZONE_HORDE", "REST_ZONE_ALLIANCE", "CONTESTED_AREA", "WINTERGRASP",
                            "WINTERGRASP_2", "ALLOW_DUELS", "NEED_FLY", "OUTDOOR_PVP", "ARENA_INSTANCE", "UNK4",
                            "LOWLEVEL", "INSIDE"],
        },
        "loading_screen": None,
        "light": {"skybox": "Environments\\Stars\\WintergraspSmokySky.M2"},
        "world_map_area": {"name": "BleakholdRoyale", "bounds": "auto"},
        "battleground": {
            "id": 12, "template": 2, "name": "Bleakhold Royale", "groups_allowed": 0, "max_group_size": 0,
            "min_level": 80, "max_level": 80,
            "brackets": [{"range_index": 7, "min_level": 80, "max_level": 80, "difficulty": 0}],
        },
        "archives": {
            "map": "patch-Q.MPQ", "dbc": "auto", "reserved_letters": "ABCDEGHIJLMNPRSTUVWXYZ",
            "optional_packs": {"hd": ["Data/patch-[ABCDEGIMNPSU].MPQ", "Data/Patch-Y.MPQ"]},
        },
    }


TILES = {(31, 31), (31, 32), (32, 31), (32, 32)}


def load_tables(raw: dict[str, bytes]) -> dict[str, DbcTable]:
    return {name: DbcTable.from_bytes(data, layout.get(name), name) for name, data in raw.items()}


def run_forge(cfg_data=None, reserved=None, tiles=TILES, raw=None):
    """Forge the default (or given) config over the synthetic tables: (config, tables, result, input bytes)."""
    raw = raw or build_tables()
    cfg = configmod.parse(cfg_data or default_config())
    tables = load_tables(raw)
    result = forgemod.Forge(tables, cfg, reserved, tiles).run()
    return cfg, tables, result, raw
