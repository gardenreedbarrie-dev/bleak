"""The map's JSON config (bleakhold_royale.json): what goes into each table, and which archives carry it.

Every value the server reads is written in the config. Values left null are copied from the template row named
by `template` (an existing row of the same table: sounds, music, minimap scale, liquid types and the like), so
references to other tables point at rows the client already has.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .layout import LOCALES

# AreaTable flags (AzerothCore DBCEnums.h AREA_FLAG_*, client GameUI_Scripts.cpp Script_GetZonePVPInfo).
AREA_FLAGS = {
    "UNK0": 0x1, "UNK1": 0x2, "UNK2": 0x4, "SLAVE_CAPITAL": 0x8, "UNK3": 0x10, "SLAVE_CAPITAL2": 0x20,
    "ALLOW_DUELS": 0x40,
    # Free-for-all PvP: Player::UpdateArea sets IsInFFAPvPArea, UpdateFFAPvPState then UNIT_BYTE2_FLAG_FFA_PVP;
    # the client's GetZonePVPInfo() answers "arena".
    "ARENA": 0x80,
    "CAPITAL": 0x100, "CITY": 0x200,
    # The server reads this as "flyable" (AreaTableEntry::IsFlyable).
    "OUTLAND": 0x400,
    "SANCTUARY": 0x800, "NEED_FLY": 0x1000, "UNUSED1": 0x2000, "OUTLAND2": 0x4000, "OUTDOOR_PVP": 0x8000,
    "ARENA_INSTANCE": 0x10000, "UNUSED2": 0x20000, "CONTESTED_AREA": 0x40000, "UNK4": 0x80000, "LOWLEVEL": 0x100000,
    "TOWN": 0x200000, "REST_ZONE_HORDE": 0x400000, "REST_ZONE_ALLIANCE": 0x800000, "WINTERGRASP": 0x1000000,
    "INSIDE": 0x2000000, "OUTSIDE": 0x4000000, "WINTERGRASP_2": 0x8000000, "NO_FLY_ZONE": 0x20000000,
}

# Flags a zone may keep from its template row without being asked for: AzerothCore and the client read none of
# them for gameplay (unknown/unused bits, and OUTSIDE, which only keeps the zone outdoors: Map.cpp reads
# INSIDE | OUTSIDE for IsOutdoors). Every other inherited flag changes the rules (duels, rest, sanctuary, city
# chat, indoor-only spells, ghost revival, flying) and must be cleared or set on purpose: forge.check reports it.
HARMLESS_TEMPLATE_FLAGS = (AREA_FLAGS["UNK0"] | AREA_FLAGS["UNK1"] | AREA_FLAGS["UNK2"] | AREA_FLAGS["UNK3"]
                           | AREA_FLAGS["UNUSED1"] | AREA_FLAGS["UNUSED2"] | AREA_FLAGS["OUTSIDE"])


def flag_names(value: int) -> list[str]:
    """AREA_FLAG_* names of the bits in value (unnamed bits as hex)."""
    names = [name for name, bit in AREA_FLAGS.items() if value & bit]
    rest = value & ~sum(AREA_FLAGS.values()) & 0xFFFFFFFF
    return names + ([f"0x{rest:X}"] if rest else [])


# Map.dbc InstanceType (AzerothCore MapTypes, the client's IsInInstance tokens).
INSTANCE_TYPES = {0: "none (one shared world map)", 1: "party (dungeon)", 2: "raid", 3: "pvp (battleground)",
                  4: "arena"}

# The server keeps area ids in 16 bits in its .map files (map_extractor: uint16 area_ids) and in PLAYER_EXPLORED_ZONES
# 128 x 32 exploration bits.
MAX_AREA_ID = 0xFFFF
EXPLORE_BITS = 128 * 32

_DIRECTORY = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,47}")
PATCH_NAME = re.compile(r"(?i)patch-(.)\.mpq")
_INTERNAL_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,47}")
MARKER_PATH = re.compile(r"(?i)[A-Za-z][A-Za-z0-9_-]*(\\[A-Za-z0-9_-]+)+\.blp")


class ConfigError(Exception):
    pass


@dataclass
class Text:
    """A localized string: the name for every locale, single locales overridden by `names`."""

    name: str
    names: dict[str, str] = field(default_factory=dict)

    def slots(self) -> list[str]:
        slots = [self.name] * len(LOCALES) + [""] * (16 - len(LOCALES))

        for code, text in self.names.items():
            slots[LOCALES.index(code)] = text

        return slots


@dataclass
class MapConfig:
    id: int
    directory: str
    template: int
    name: Text
    instance_type: int
    pvp: int | None
    flags: int | None
    description_horde: Text
    description_alliance: Text
    minimap_icon_scale: float | None
    corpse_map: int
    corpse_x: float
    corpse_y: float
    time_of_day_override: int | None
    expansion: int
    raid_offset: int | None
    max_players: int


@dataclass
class AreaConfig:
    id: int
    name: Text
    area_bit: int | None


@dataclass
class ZoneConfig:
    id: int
    template: int
    name: Text
    area_bit: int | None
    set_flags: int
    clear_flags: int
    exploration_level: int
    faction_group_mask: int
    ambience_id: int | None
    zone_music: int | None
    intro_sound: int | None
    subzones: list[AreaConfig]


@dataclass
class LoadingScreenConfig:
    reuse: int | None = None  # an existing LoadingScreens id
    id: int | None = None  # a new row (None: the next free id)
    name: str = ""
    file: str = ""
    widescreen: bool = False
    image: str | None = None  # picture for the 4:3 screen (PNG/TGA; converted to BLP)
    wide_image: str | None = None  # picture for 16:10 screens


@dataclass
class LightConfig:
    id: int | None  # None: the next free id
    params: list[int] | None
    params_from_light: int | None
    params_from_map: int | None
    skybox: str | None  # an Environments\Stars M2 path; the stock LightParams row showing it is used for all slots


@dataclass
class WorldMapAreaConfig:
    id: int | None  # None: the next free id
    name: str
    bounds: tuple[float, float, float, float] | None  # left, right, top, bottom; None: from the WDT


@dataclass
class BracketConfig:
    id: int | None
    range_index: int
    min_level: int
    max_level: int
    difficulty: int


@dataclass
class BattlegroundConfig:
    id: int
    template: int
    name: Text
    groups_allowed: int
    max_group_size: int
    min_level: int
    max_level: int
    brackets: list[BracketConfig]


@dataclass
class ArchiveConfig:
    map_archive: str
    dbc: str  # "auto", "map" or "merge"
    merge_into: str | None  # for "merge"; None: the archive "auto" would pick
    optional_packs: dict[str, list[str]]
    reserved_letters: str  # patch letters MapForge never creates (other projects use them)
    marker_texture: str | None = None  # a generated BLP in the map archive (an addon tests it: patch installed)


@dataclass
class Config:
    path: str
    map: MapConfig
    zone: ZoneConfig
    loading_screen: LoadingScreenConfig | None
    light: LightConfig | None
    world_map_area: WorldMapAreaConfig | None
    battleground: BattlegroundConfig | None
    archives: ArchiveConfig
    warnings: list[str] = field(default_factory=list)

    def area_ids(self) -> list[int]:
        return [self.zone.id] + [a.id for a in self.zone.subzones]


# --- parsing ---------------------------------------------------------------------------------------------------


class _Reader:
    def __init__(self, data: dict, where: str):
        if not isinstance(data, dict):
            raise ConfigError(f"{where} must be an object")

        self.data = data
        self.where = where
        self.used: set[str] = set()

    def _get(self, key: str, default):
        self.used.add(key)
        return self.data.get(key, default)

    def int(self, key: str, default=..., low: int = -0x80000000, high: int = 0x7FFFFFFF, null: bool = False):
        value = self._get(key, default)

        if value is ...:
            raise ConfigError(f"{self.where}.{key} is missing")

        if value is None and null:
            return None

        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{self.where}.{key} must be a whole number")

        if not low <= value <= high:
            raise ConfigError(f"{self.where}.{key} must be between {low} and {high}")

        return value

    def float(self, key: str, default=..., null: bool = False):
        value = self._get(key, default)

        if value is ...:
            raise ConfigError(f"{self.where}.{key} is missing")

        if value is None and null:
            return None

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{self.where}.{key} must be a number")

        return float(value)

    def str(self, key: str, default=..., null: bool = False):
        value = self._get(key, default)

        if value is ...:
            raise ConfigError(f"{self.where}.{key} is missing")

        if value is None and null:
            return None

        if not isinstance(value, str):
            raise ConfigError(f"{self.where}.{key} must be a string")

        if "\0" in value:
            raise ConfigError(f"{self.where}.{key} contains a NUL character")

        return value

    def text(self, key: str, default: str | None = None) -> Text:
        name = self.str(key, default if default is not None else ...)
        names = self._get(f"{key}s" if key == "name" else f"{key}_locales", {}) or {}

        if not isinstance(names, dict):
            raise ConfigError(f"{self.where}.{key}s must be an object of locale: text")

        for code, text in names.items():
            if code not in LOCALES:
                raise ConfigError(f"{self.where}: unknown locale {code!r} (use one of {', '.join(LOCALES)})")

            if not isinstance(text, str) or "\0" in text:
                raise ConfigError(f"{self.where}: the {code} text must be a string without NUL")

        return Text(name, dict(names))

    def obj(self, key: str, null: bool = True):
        value = self._get(key, None)

        if value is None:
            if null:
                return None
            raise ConfigError(f"{self.where}.{key} is missing")

        return _Reader(value, f"{self.where}.{key}")

    def list(self, key: str, default=None):
        value = self._get(key, default)

        if value is None:
            return []

        if not isinstance(value, list):
            raise ConfigError(f"{self.where}.{key} must be a list")

        return value

    def raw(self, key: str, default=None):
        return self._get(key, default)

    def finish(self):
        unknown = sorted(k for k in self.data if k not in self.used and not k.startswith("_"))

        if unknown:
            raise ConfigError(f"{self.where}: unknown key(s) {', '.join(unknown)}")


def _flags(names, where: str) -> int:
    if names is None:
        return 0

    if not isinstance(names, list):
        raise ConfigError(f"{where} must be a list of flag names")

    value = 0

    for name in names:
        if name not in AREA_FLAGS:
            raise ConfigError(f"{where}: unknown flag {name!r} (known: {', '.join(AREA_FLAGS)})")
        value |= AREA_FLAGS[name]

    return value


def _time_of_day(value, where: str) -> int | None:
    """Map.dbc timeOfDayOverride: null copies the template, "off" (or -1) is the natural day cycle, 0-1440 a fixed
    time in minutes (WorldFrame: the client uses value / 1440 as the time of day)."""
    if value is None:
        return None

    if value == "off":
        return -1

    if isinstance(value, bool) or not isinstance(value, int) or not -1 <= value <= 1440:
        raise ConfigError(f"{where}: null (the template's), \"off\" or -1 (the natural day cycle), or minutes "
                          "0-1440 (a fixed time of day)")

    return value


def _map(r: _Reader) -> MapConfig:
    directory = r.str("directory")

    if not _DIRECTORY.fullmatch(directory):
        raise ConfigError(f"{r.where}.directory must be 1-48 letters, digits or _, starting with a letter "
                          "(it names World\\Maps\\<directory>\\<directory>_<x>_<y>.adt)")

    out = MapConfig(
        id=r.int("id", low=1, high=999),
        directory=directory,
        template=r.int("template", low=0),
        name=r.text("name"),
        instance_type=r.int("instance_type", low=0, high=4),
        pvp=r.int("pvp", None, low=0, high=1, null=True),
        flags=r.int("flags", None, low=0, null=True),
        description_horde=r.text("description_horde", ""),
        description_alliance=r.text("description_alliance", ""),
        minimap_icon_scale=r.float("minimap_icon_scale", None, null=True),
        corpse_map=r.int("corpse_map", -1),
        corpse_x=r.float("corpse_x", 0.0),
        corpse_y=r.float("corpse_y", 0.0),
        time_of_day_override=_time_of_day(r.raw("time_of_day_override"), f"{r.where}.time_of_day_override"),
        expansion=r.int("expansion", low=0, high=2),
        raid_offset=r.int("raid_offset", None, null=True),
        max_players=r.int("max_players", low=0, high=1000),
    )
    r.finish()
    return out


def _zone(r: _Reader) -> ZoneConfig:
    subzones = []

    for i, item in enumerate(r.list("subzones")):
        s = _Reader(item, f"{r.where}.subzones[{i}]")
        subzones.append(AreaConfig(s.int("id", low=1, high=MAX_AREA_ID), s.text("name"),
                                   s.int("area_bit", None, low=0, high=EXPLORE_BITS - 1, null=True)))
        s.finish()

    out = ZoneConfig(
        id=r.int("id", low=1, high=MAX_AREA_ID),
        template=r.int("template", low=1),
        name=r.text("name"),
        area_bit=r.int("area_bit", None, low=0, high=EXPLORE_BITS - 1, null=True),
        set_flags=_flags(r.raw("set_flags"), f"{r.where}.set_flags"),
        clear_flags=_flags(r.raw("clear_flags"), f"{r.where}.clear_flags"),
        exploration_level=r.int("exploration_level", 0, low=0, high=255),
        faction_group_mask=r.int("faction_group_mask", 0, low=0),
        ambience_id=r.int("ambience_id", None, low=0, null=True),
        zone_music=r.int("zone_music", None, low=0, null=True),
        intro_sound=r.int("intro_sound", None, low=0, null=True),
        subzones=subzones,
    )
    r.finish()

    if out.set_flags & out.clear_flags:
        raise ConfigError(f"{r.where}: set_flags and clear_flags name the same flag")

    ids = out.subzones and [out.id] + [a.id for a in out.subzones]

    if ids and len(set(ids)) != len(ids):
        raise ConfigError(f"{r.where}: the zone and its subzones need different ids")

    return out


def _loading_screen(value, where: str) -> LoadingScreenConfig | None:
    if value is None:
        return None

    if isinstance(value, int) and not isinstance(value, bool):
        return LoadingScreenConfig(reuse=value)

    r = _Reader(value, where)
    out = LoadingScreenConfig(
        id=r.int("id", None, low=1, null=True),
        name=r.str("name"),
        file=r.str("file"),
        widescreen=bool(r.raw("widescreen", False)),
        image=r.str("image", None, null=True),
        wide_image=r.str("wide_image", None, null=True),
    )
    r.finish()

    if not out.file.lower().endswith(".blp") or "/" in out.file or out.file.count(".") != 1:
        raise ConfigError(f"{where}.file must be an archive path with backslashes, ending in .blp and with no other "
                          "dot (the client cuts the name at the first dot to add Wide)")

    if out.wide_image and not out.widescreen:
        raise ConfigError(f"{where}: wide_image needs widescreen true (the client then loads <file>Wide.blp)")

    return out


def _light(r: _Reader | None) -> LightConfig | None:
    if r is None:
        return None

    params = r.raw("params")

    if params is not None and (not isinstance(params, list) or len(params) != 8
                               or not all(isinstance(p, int) and not isinstance(p, bool) for p in params)):
        raise ConfigError(f"{r.where}.params must be a list of 8 LightParams ids")

    out = LightConfig(r.int("id", None, low=1, null=True), params, r.int("params_from_light", None, low=1, null=True),
                      r.int("params_from_map", None, low=0, null=True), r.str("skybox", None, null=True))
    r.finish()

    if sum(x is not None for x in (out.params, out.params_from_light, out.params_from_map, out.skybox)) != 1:
        raise ConfigError(f"{r.where}: give exactly one of params, params_from_light, params_from_map, skybox")

    return out


def _world_map_area(r: _Reader | None) -> WorldMapAreaConfig | None:
    if r is None:
        return None

    name = r.str("name")

    if not _INTERNAL_NAME.fullmatch(name):
        raise ConfigError(f"{r.where}.name must be letters and digits (it names Interface\\WorldMap\\<name>\\)")

    bounds = r.raw("bounds", "auto")

    if bounds == "auto":
        bounds = None
    elif (not isinstance(bounds, list) or len(bounds) != 4
          or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bounds)):
        raise ConfigError(f"{r.where}.bounds must be \"auto\" or [left, right, top, bottom]")
    else:
        bounds = tuple(float(v) for v in bounds)

        if not (bounds[0] > bounds[1] and bounds[2] > bounds[3]):
            raise ConfigError(f"{r.where}.bounds: left must be above right and top above bottom (world coordinates)")

    out = WorldMapAreaConfig(r.int("id", None, low=1, null=True), name, bounds)
    r.finish()
    return out


def _battleground(r: _Reader | None) -> BattlegroundConfig | None:
    if r is None:
        return None

    brackets = []

    for i, item in enumerate(r.list("brackets")):
        b = _Reader(item, f"{r.where}.brackets[{i}]")
        brackets.append(BracketConfig(b.int("id", None, low=1, null=True), b.int("range_index", low=0, high=15),
                                      b.int("min_level", low=1, high=255), b.int("max_level", low=1, high=255),
                                      b.int("difficulty", 0, low=0, high=3)))
        b.finish()

        if brackets[-1].min_level > brackets[-1].max_level:
            raise ConfigError(f"{b.where}: min_level is above max_level")

    if not brackets:
        raise ConfigError(f"{r.where}.brackets: a battleground needs at least one PvpDifficulty bracket "
                          "(BattlegroundMgr finds none for the player's level otherwise)")

    if len({b.range_index for b in brackets}) != len(brackets):
        raise ConfigError(f"{r.where}.brackets: range_index values must differ")

    # BattlegroundTypeId is a uint8 below MAX_BATTLEGROUND_TYPE_ID (33) in AzerothCore's SharedDefines.h.
    out = BattlegroundConfig(r.int("id", low=1, high=32), r.int("template", low=1), r.text("name"),
                             r.int("groups_allowed", low=0, high=1), r.int("max_group_size", low=0, high=40),
                             r.int("min_level", low=1, high=255), r.int("max_level", low=1, high=255), brackets)
    r.finish()
    return out


def _archives(r: _Reader | None) -> ArchiveConfig:
    data = r or _Reader({}, "archives")
    packs = data.raw("optional_packs", {}) or {}

    if not isinstance(packs, dict) or not all(isinstance(v, list) and all(isinstance(p, str) for p in v)
                                              for v in packs.values()):
        raise ConfigError("archives.optional_packs must be {pack: [file patterns]}")

    if len(packs) > 6:
        raise ConfigError("archives.optional_packs: at most 6 packs")

    out = ArchiveConfig(data.str("map", "patch-Q.MPQ"), data.str("dbc", "auto"),
                        data.str("merge_into", None, null=True), {k: list(v) for k, v in packs.items()},
                        data.str("reserved_letters", "").upper(), data.str("marker_texture", None, null=True))
    data.finish()

    if out.marker_texture is not None:
        marker = out.marker_texture.replace("/", "\\")

        if not MARKER_PATH.fullmatch(marker) or marker.lower().startswith(("world\\", "dbfilesclient\\")):
            raise ConfigError("archives.marker_texture must be a client path like Interface\\Folder\\Name.blp "
                              "(letters, digits, '_', '-', backslashes; not under World or DBFilesClient)")

        out.marker_texture = marker

    names = [out.map_archive] + ([out.merge_into] if out.merge_into else [])

    if out.dbc not in ("auto", "map", "merge"):
        raise ConfigError("archives.dbc must be \"auto\", \"map\" or \"merge\"")

    for name in names:
        if not PATCH_NAME.fullmatch(name):
            raise ConfigError(f"archives: {name!r} is not a Data\\patch-<one character>.MPQ name the client loads")

    if out.map_archive.lower() == (out.merge_into or "").lower():
        raise ConfigError("archives: merge_into names the map archive (use \"dbc\": \"map\" for that)")

    letter = PATCH_NAME.fullmatch(out.map_archive).group(1).upper()

    if letter in out.reserved_letters:
        raise ConfigError(f"archives.map: {out.map_archive} uses a reserved letter ({out.reserved_letters})")

    return out


def load(path: str) -> Config:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise ConfigError(f"{path}: {e.strerror}") from None
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path}: line {e.lineno} column {e.colno}: {e.msg}") from None

    return parse(data, path)


def parse(data: dict, path: str = "<config>") -> Config:
    r = _Reader(data, "config")
    config = Config(
        path=path,
        map=_map(r.obj("map", null=False)),
        zone=_zone(r.obj("zone", null=False)),
        loading_screen=_loading_screen(r.raw("loading_screen"), "loading_screen"),
        light=_light(r.obj("light")),
        world_map_area=_world_map_area(r.obj("world_map_area")),
        battleground=_battleground(r.obj("battleground")),
        archives=_archives(r.obj("archives")),
    )
    r.finish()

    m = config.map

    if m.instance_type == 3 and config.battleground is None:
        config.warnings.append("instance_type 3 (battleground) without a battleground section: the server's "
                               "BattlegroundMgr needs a BattlemasterList row and PvpDifficulty brackets for the map")

    if m.instance_type != 3 and config.battleground is not None:
        raise ConfigError("battleground rows are only for instance_type 3")

    if m.id < 725:
        config.warnings.append(f"map id {m.id} is in the stock range (0-724); use an id well above it")

    if m.id >= 1000:
        # mmaps_generator's discoverTiles writes "%03u*.vmtile" into char filter[12] (MapBuilder.cpp), and the server
        # names its files with %03u: a 4-digit id overflows the one and breaks the naming of the other.
        raise ConfigError(f"map.id {m.id}: use an id below 1000 (mmaps_generator and the 3-digit map file names)")

    if config.zone.set_flags & AREA_FLAGS["SANCTUARY"]:
        config.warnings.append("zone.set_flags has SANCTUARY: nobody can attack anybody there")

    return config
