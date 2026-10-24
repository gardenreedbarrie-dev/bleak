"""Add the map's rows to the realm's current DBCs, and check the result.

Each new row starts as a copy of its template row (an existing row of the same table) and gets the values of the
config on top, so every column MapForge does not set keeps a value the client already uses: the localized string
flags, sound and music ids, liquid types, the minimap icon scale. Rows that are already in the input and belong to
this map (an earlier MapForge run, now part of the realm's DBCs) are rewritten in place; a row with one of the
config's ids that belongs to something else stops the build. No other row changes: the string block is kept and new
strings are appended (rflib.dbc), and check() compares every other row with the input.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import layout
from .config import AREA_FLAGS, EXPLORE_BITS, HARMLESS_TEMPLATE_FLAGS, Config, flag_names

from rflib.dbc import DbcError, DbcTable, to_signed  # noqa: E402

# Tables the build writes, and tables only read to check references.
WRITTEN = ("Map", "AreaTable", "LoadingScreens", "Light", "WorldMapArea", "BattlemasterList", "PvpDifficulty")
REFERENCE = ("LightParams", "SoundAmbience", "ZoneMusic", "ZoneIntroMusicTable")

# ADT tiles are 533.333 yards: tile (x, y) spans world Y from (32 - x) * TILE down by one tile, X likewise with y.
TILE = 1600.0 / 3.0
WORLD_MAP_ASPECT = 1002.0 / 668.0  # the world map frame's detail area


class ForgeError(Exception):
    pass


def float_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def bits_float(value: int) -> float:
    return struct.unpack("<f", struct.pack("<I", value))[0]


@dataclass
class TableChange:
    added: list[int] = field(default_factory=list)
    replaced: list[int] = field(default_factory=list)  # this map's rows from an earlier run, rewritten in place
    removed: list[int] = field(default_factory=list)  # this map's rows from an earlier run the config dropped

    def touched(self) -> set[int]:
        return set(self.added) | set(self.replaced) | set(self.removed)


@dataclass
class ForgeResult:
    changes: dict[str, TableChange] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    area_bits: dict[int, int] = field(default_factory=dict)
    loading_screen_id: int = 0
    light_params: list[int] = field(default_factory=list)
    world_map_bounds: tuple[float, float, float, float] | None = None
    bracket_ids: dict[int, int] = field(default_factory=dict)  # range index -> PvpDifficulty id
    light_id: int | None = None
    world_map_area_id: int | None = None


def tables_needed(config: Config) -> tuple[list[str], list[str]]:
    """(tables the build cannot do without, tables it writes or checks when they are given)."""
    required = ["Map", "AreaTable"]

    if config.loading_screen and config.loading_screen.reuse is None:
        required.append("LoadingScreens")

    if config.light:
        required.append("Light")

        if config.light.skybox is not None:
            required += ["LightParams", "LightSkybox"]

    if config.world_map_area:
        required.append("WorldMapArea")

    if config.battleground:
        required += ["BattlemasterList", "PvpDifficulty"]

    optional = [n for n in ("LoadingScreens",) + REFERENCE if n not in required]
    return required, optional


def world_map_bounds(tiles: set[tuple[int, int]]) -> tuple[float, float, float, float]:
    """WorldMapArea left, right, top, bottom (world Y, Y, X, X) around the WDT's tiles, widened to the world map's
    1002:668 frame so the picture is not stretched."""
    if not tiles:
        raise ForgeError("the WDT has no tiles")

    xs = [t[0] for t in tiles]
    ys = [t[1] for t in tiles]
    left, right = (32 - min(xs)) * TILE, (32 - max(xs) - 1) * TILE
    top, bottom = (32 - min(ys)) * TILE, (32 - max(ys) - 1) * TILE
    width, height = left - right, top - bottom

    if width / height < WORLD_MAP_ASPECT:
        grow = (height * WORLD_MAP_ASPECT - width) / 2
        left, right = left + grow, right - grow
    else:
        grow = (width / WORLD_MAP_ASPECT - height) / 2
        top, bottom = top + grow, bottom - grow

    return (round(left, 4), round(right, 4), round(top, 4), round(bottom, 4))


class Forge:
    def __init__(self, tables: dict[str, DbcTable], config: Config, reserved: dict[str, dict[int, str]] | None = None,
                 wdt_tiles: set[tuple[int, int]] | None = None):
        """tables: the realm's current tables (changed in place). reserved: ids the server's SQL already uses, by
        table ({"Map": {930: "data/sql/...sql"}}). wdt_tiles: the terrain's tiles, for WorldMapArea bounds."""
        self.tables = tables
        self.config = config
        self.reserved = reserved or {}
        self.wdt_tiles = wdt_tiles
        self.result = ForgeResult()

    # --- helpers ---

    def _table(self, name: str) -> DbcTable:
        if name not in self.tables:
            raise ForgeError(f"{layout.file_name(name)} is needed and was not given")

        return self.tables[name]

    def _change(self, name: str) -> TableChange:
        return self.result.changes.setdefault(name, TableChange())

    @staticmethod
    def _row(table: DbcTable, row_id: int) -> list[int] | None:
        for row in table.rows:
            if to_signed(row[0]) == row_id:
                return row

        return None

    def _template(self, name: str, row_id: int, what: str) -> list[int]:
        row = self._row(self._table(name), row_id)

        if row is None:
            raise ForgeError(f"{what}: template {row_id} is not in {layout.file_name(name)}")

        return list(row)

    def _place(self, name: str, row_id: int, row: list[int], ours) -> None:
        """Put row at id row_id: in place of this map's earlier row, or appended. ours(existing row) says whether a
        row already there belongs to this map."""
        table = self._table(name)
        change = self._change(name)

        for i, existing in enumerate(table.rows):
            if to_signed(existing[0]) == row_id:
                if not ours(existing):
                    raise ForgeError(f"{layout.file_name(name)} already has a row {row_id} that is not this map's; "
                                     "choose another id in the config")

                table.rows[i] = row
                change.replaced.append(row_id)
                return

        source = self.reserved.get(name, {}).get(row_id)

        if source:
            raise ForgeError(f"{layout.SERVER[name][0]} row {row_id} already exists in the server's SQL ({source}); "
                             "choose another id in the config")

        table.rows.append(row)
        change.added.append(row_id)

    def _remove_stale(self, name: str, keep: set[int], ours) -> None:
        table = self._table(name)
        stale = [to_signed(r[0]) for r in table.rows if ours(r) and to_signed(r[0]) not in keep]

        if stale:
            table.rows = [r for r in table.rows if not (ours(r) and to_signed(r[0]) not in keep)]
            self._change(name).removed.extend(stale)
            self.result.notes.append(f"{layout.file_name(name)}: removed this map's rows {stale} from an earlier run "
                                     "(no longer in the config)")

    def _set_text(self, table: DbcTable, row: list[int], field_name: str, slots: list[str]) -> None:
        table.set_loc(row, field_name, slots)

    def _next_id(self, name: str, exclude: set[int] = frozenset()) -> int:
        """The id after every id of the table, of the server's SQL rows for it and of exclude. Ids stay close to the
        table's own: the client keeps each table in an array indexed from its lowest to its highest id."""
        ids = [to_signed(r[0]) for r in self._table(name).rows]
        return max(ids + list(self.reserved.get(name, {})) + list(exclude) + [0]) + 1

    def _check_ref(self, name: str, row_id: int, what: str) -> None:
        if not row_id:
            return

        if name not in self.tables:
            self.result.notes.append(f"{what} {row_id}: not checked ({layout.file_name(name)} not given)")
        elif self._row(self.tables[name], row_id) is None:
            raise ForgeError(f"{what} {row_id} is not in {layout.file_name(name)}")

    # --- the build ---

    def run(self) -> ForgeResult:
        self._check_map_free()
        self._loading_screen()
        self._areas()
        self._map()
        self._light()
        self._world_map_area()
        self._battleground()
        return self.result

    def _check_map_free(self) -> None:
        m = self.config.map
        maps = self._table("Map")

        for row in maps.rows:
            directory = maps.get_str(row, "directory")

            if to_signed(row[0]) != m.id and directory.lower() == m.directory.lower():
                raise ForgeError(f"Map.dbc row {to_signed(row[0])} already uses the directory {directory}")

        if m.template == m.id:
            raise ForgeError("map.template must be an existing map, not the new one")

    def _map_is_ours(self, row: list[int]) -> bool:
        return self._table("Map").get_str(row, "directory").lower() == self.config.map.directory.lower()

    def _loading_screen(self) -> None:
        cfg = self.config.loading_screen
        maps = self._table("Map")
        template = self._template("Map", self.config.map.template, "map")

        if cfg is None:
            self.result.loading_screen_id = maps.get(template, "loadingScreenID")
            self._check_ref("LoadingScreens", self.result.loading_screen_id, "the template's loading screen")
            return

        if cfg.reuse is not None:
            self.result.loading_screen_id = cfg.reuse
            self._check_ref("LoadingScreens", cfg.reuse, "loading_screen")
            return

        screens = self._table("LoadingScreens")
        same_file = [to_signed(r[0]) for r in screens.rows
                     if screens.get_str(r, "fileName").lower() == cfg.file.lower()]
        row_id = cfg.id if cfg.id is not None else (same_file[0] if same_file else self._next_id("LoadingScreens"))

        row = [0] * len(screens.schema.columns)
        screens.set(row, "id", row_id)
        screens.set_str(row, "name", cfg.name)
        screens.set_str(row, "fileName", cfg.file)
        screens.set(row, "hasWideScreen", 1 if cfg.widescreen else 0)
        self._place("LoadingScreens", row_id, row,
                    lambda r: screens.get_str(r, "fileName").lower() == cfg.file.lower())
        self.result.loading_screen_id = row_id

    def _area_bits(self, areas: list[tuple[int, int | None]]) -> dict[int, int]:
        """Exploration bits: unique over the whole table (PLAYER_EXPLORED_ZONES), below 4096."""
        table = self._table("AreaTable")
        ours = set(self.config.area_ids())
        map_id = self.config.map.id
        used = {}
        previous = {}

        for row in table.rows:
            row_id = to_signed(row[0])

            if row_id in ours and table.get(row, "continentID") == map_id:
                previous[row_id] = table.get(row, "areaBit")
            else:
                used.setdefault(table.get(row, "areaBit"), row_id)

        out = {}

        for area_id, wanted in areas:
            if wanted is not None:
                if wanted in used:
                    raise ForgeError(f"area {area_id}: area_bit {wanted} is already used by area {used[wanted]}")
                bit = wanted
            elif area_id in previous and previous[area_id] not in used and previous[area_id] < EXPLORE_BITS:
                bit = previous[area_id]
            else:
                bit = max(list(used) + [0]) + 1

                if bit >= EXPLORE_BITS:
                    free = [b for b in range(1, EXPLORE_BITS) if b not in used]

                    if not free:
                        raise ForgeError("every exploration bit below 4096 is in use")
                    bit = free[0]

            used[bit] = area_id
            out[area_id] = bit

        return out

    def _areas(self) -> None:
        z = self.config.zone
        m = self.config.map
        table = self._table("AreaTable")
        template = self._template("AreaTable", z.template, "zone")

        if z.template in self.config.area_ids():
            raise ForgeError("zone.template must be an existing area, not one of the new ones")

        bits = self._area_bits([(z.id, z.area_bit)] + [(a.id, a.area_bit) for a in z.subzones])
        self.result.area_bits = bits

        def ours(row):
            return table.get(row, "continentID") == m.id

        zone = list(template)
        table.set(zone, "id", z.id)
        table.set(zone, "continentID", m.id)
        table.set(zone, "parentAreaID", 0)
        table.set(zone, "areaBit", bits[z.id])
        table.set(zone, "flags", (table.get(template, "flags") | z.set_flags) & ~z.clear_flags & 0xFFFFFFFF)
        table.set(zone, "explorationLevel", z.exploration_level)
        table.set(zone, "factionGroupMask", z.faction_group_mask)

        for column, value in (("ambienceID", z.ambience_id), ("zoneMusic", z.zone_music),
                              ("introSound", z.intro_sound)):
            if value is not None:
                table.set(zone, column, value)

        self._check_ref("SoundAmbience", table.get(zone, "ambienceID"), "zone ambienceID")
        self._check_ref("ZoneMusic", table.get(zone, "zoneMusic"), "zone zoneMusic")
        self._check_ref("ZoneIntroMusicTable", table.get(zone, "introSound"), "zone introSound")
        self._set_text(table, zone, "areaName", z.name.slots())
        self._place("AreaTable", z.id, zone, ours)

        for area in z.subzones:
            row = list(zone)
            table.set(row, "id", area.id)
            table.set(row, "parentAreaID", z.id)
            table.set(row, "areaBit", bits[area.id])
            self._set_text(table, row, "areaName", area.name.slots())
            self._place("AreaTable", area.id, row, ours)

        self._remove_stale("AreaTable", set(self.config.area_ids()), ours)
        flags = table.get(zone, "flags")
        inherited = flags & ~z.set_flags

        if not flags & AREA_FLAGS["ARENA"]:
            self.result.warnings.append("the zone has no ARENA flag (0x80): it is not free-for-all PvP")

        self.result.notes.append(
            f"zone {z.id} (and its {len(z.subzones)} subzones) flags 0x{flags:X}: "
            f"{' | '.join(flag_names(flags)) or 'none'}; set by the config: "
            f"{' | '.join(flag_names(flags & z.set_flags)) or 'none'}; kept from template {z.template}: "
            f"{' | '.join(flag_names(inherited)) or 'none'}")

    def _map(self) -> None:
        m = self.config.map
        table = self._table("Map")
        row = self._template("Map", m.template, "map")

        table.set(row, "id", m.id)
        table.set_str(row, "directory", m.directory)
        table.set(row, "instanceType", m.instance_type)

        if m.flags is not None:
            table.set(row, "flags", m.flags)

        if m.pvp is not None:
            table.set(row, "pvp", m.pvp)

        self._set_text(table, row, "mapName", m.name.slots())
        table.set(row, "areaTableID", self.config.zone.id)
        self._set_text(table, row, "mapDescription0", m.description_horde.slots())
        self._set_text(table, row, "mapDescription1", m.description_alliance.slots())
        table.set(row, "loadingScreenID", self.result.loading_screen_id)

        if m.minimap_icon_scale is not None:
            table.set(row, "minimapIconScale", float_bits(m.minimap_icon_scale))

        table.set(row, "corpseMapID", m.corpse_map)
        table.set(row, "corpse[0]", float_bits(m.corpse_x))
        table.set(row, "corpse[1]", float_bits(m.corpse_y))

        if m.time_of_day_override is not None:
            table.set(row, "timeOfDayOverride", m.time_of_day_override)

        table.set(row, "expansionID", m.expansion)

        if m.raid_offset is not None:
            table.set(row, "raidOffset", m.raid_offset)

        table.set(row, "maxPlayers", m.max_players)
        self._place("Map", m.id, row, self._map_is_ours)

    def _light(self) -> None:
        cfg = self.config.light

        if cfg is None:
            self.result.notes.append("no Light row: the client lights the map with Light 1, the default sky")
            return

        table = self._table("Light")
        map_id = self.config.map.id
        zero = float_bits(0.0)

        def is_default(row):
            return all(table.get(row, f"gameCoords[{i}]") in (0, 0x80000000) for i in range(3))

        if cfg.params is not None:
            params = list(cfg.params)
        elif cfg.skybox is not None:
            params = [self._params_for_skybox(cfg.skybox)] * 8
        elif cfg.params_from_light is not None:
            source = self._template("Light", cfg.params_from_light, "light.params_from_light")
            params = [table.get_signed(source, f"lightParamsID[{i}]") for i in range(8)]
        else:
            # DayNight::LightLoad: a map's default light is its row with game coordinates (0, 0, 0); the last one
            # counts when there are several.
            defaults = [r for r in table.rows if table.get(r, "continentID") == cfg.params_from_map and is_default(r)]

            if not defaults:
                raise ForgeError(f"light.params_from_map: map {cfg.params_from_map} has no default light (a Light "
                                 "row at 0, 0, 0)")

            params = [table.get_signed(defaults[-1], f"lightParamsID[{i}]") for i in range(8)]

        for i, param in enumerate(params):
            self._check_ref("LightParams", param, f"light lightParamsID[{i}]")

        mine = [to_signed(r[0]) for r in table.rows if table.get(r, "continentID") == map_id and is_default(r)]
        light_id = cfg.id if cfg.id is not None else (mine[0] if mine else self._next_id("Light"))
        others = [i for i in mine if i != light_id]

        if others:
            raise ForgeError(f"Light.dbc already has a default light for map {map_id} (row {others[0]})")

        row = [0] * len(table.schema.columns)
        table.set(row, "id", light_id)
        table.set(row, "continentID", map_id)

        for column in ("gameCoords[0]", "gameCoords[1]", "gameCoords[2]", "gameFalloffStart", "gameFalloffEnd"):
            table.set(row, column, zero)

        for i, param in enumerate(params):
            table.set(row, f"lightParamsID[{i}]", param)

        self._place("Light", light_id, row, lambda r: table.get(r, "continentID") == map_id)
        self.result.light_params = params
        self.result.light_id = light_id

    def _params_for_skybox(self, path: str) -> int:
        """The lowest stock LightParams id whose LightSkybox shows the M2 at path (skyboxes bind through Light ->
        LightParams -> LightSkybox, never through ADTs)."""
        skyboxes = self._table("LightSkybox")
        wanted = path.replace("/", "\\").lower()
        skybox_ids = {to_signed(r[0]) for r in skyboxes.rows if skyboxes.get_str(r, "name").lower() == wanted}

        if not skybox_ids:
            raise ForgeError(f"light.skybox: no LightSkybox row shows {path}; use params_from_light instead")

        params = self._table("LightParams")
        matches = sorted(to_signed(r[0]) for r in params.rows if params.get(r, "lightSkyboxID") in skybox_ids)

        if not matches:
            raise ForgeError(f"light.skybox: no LightParams row uses the LightSkybox of {path}; use "
                             "params_from_light instead")

        return matches[0]

    def _world_map_area(self) -> None:
        cfg = self.config.world_map_area

        if cfg is None:
            return

        table = self._table("WorldMapArea")
        map_id = self.config.map.id

        if cfg.bounds is not None:
            bounds = cfg.bounds
        elif self.wdt_tiles:
            bounds = world_map_bounds(self.wdt_tiles)
        else:
            raise ForgeError("world_map_area.bounds is \"auto\", which needs the terrain (--terrain) for its tiles")

        mine = [to_signed(r[0]) for r in table.rows if table.get(r, "mapID") == map_id]
        area_id = cfg.id if cfg.id is not None else (mine[0] if mine else self._next_id("WorldMapArea"))

        for row in table.rows:
            if to_signed(row[0]) != area_id and (table.get(row, "mapID") == map_id
                                                 or table.get_str(row, "areaName").lower() == cfg.name.lower()):
                raise ForgeError(f"WorldMapArea.dbc row {to_signed(row[0])} already covers map {map_id} or the "
                                 f"name {cfg.name}")

        row = [0] * len(table.schema.columns)
        table.set(row, "id", area_id)
        table.set(row, "mapID", map_id)
        table.set(row, "areaID", self.config.zone.id)
        table.set_str(row, "areaName", cfg.name)

        for column, value in zip(("locLeft", "locRight", "locTop", "locBottom"), bounds):
            table.set(row, column, float_bits(value))

        table.set(row, "displayMapID", -1)
        table.set(row, "defaultDungeonFloor", 0)
        table.set(row, "parentWorldMapID", -1)
        self._place("WorldMapArea", area_id, row, lambda r: table.get(r, "mapID") == map_id)
        self.result.world_map_bounds = bounds
        self.result.world_map_area_id = area_id

    def _battleground(self) -> None:
        cfg = self.config.battleground

        if cfg is None:
            return

        m = self.config.map
        bml = self._table("BattlemasterList")
        row = self._template("BattlemasterList", cfg.template, "battleground")

        if cfg.template == cfg.id:
            raise ForgeError("battleground.template must be an existing battleground, not the new one")

        bml.set(row, "id", cfg.id)

        for i in range(8):
            bml.set(row, f"mapID[{i}]", m.id if i == 0 else -1)

        bml.set(row, "instanceType", m.instance_type)
        bml.set(row, "groupsAllowed", cfg.groups_allowed)
        self._set_text(bml, row, "name", cfg.name.slots())
        bml.set(row, "maxGroupSize", cfg.max_group_size)
        bml.set(row, "holidayWorldState", 0)
        bml.set(row, "minLevel", cfg.min_level)
        bml.set(row, "maxLevel", cfg.max_level)
        self._place("BattlemasterList", cfg.id, row, lambda r: bml.get(r, "mapID[0]") == m.id)

        pvp = self._table("PvpDifficulty")

        def ours(r):
            return pvp.get(r, "mapID") == m.id

        taken = set()

        for bracket in cfg.brackets:
            existing = [to_signed(r[0]) for r in pvp.rows
                        if ours(r) and pvp.get(r, "rangeIndex") == bracket.range_index]
            row_id = bracket.id or (existing[0] if existing else self._next_id("PvpDifficulty", taken))
            taken.add(row_id)
            row = [0] * len(pvp.schema.columns)

            for column, value in (("id", row_id), ("mapID", m.id), ("rangeIndex", bracket.range_index),
                                  ("minLevel", bracket.min_level), ("maxLevel", bracket.max_level),
                                  ("difficulty", bracket.difficulty)):
                pvp.set(row, column, value)

            self._place("PvpDifficulty", row_id, row, ours)
            self.result.bracket_ids[bracket.range_index] = row_id

        self._remove_stale("PvpDifficulty", set(self.result.bracket_ids.values()), ours)


# --- checks ------------------------------------------------------------------------------------------------------


def check(base: dict[str, bytes], output: dict[str, bytes], config: Config, result: ForgeResult) -> list[str]:
    """Problems with the written tables: layouts, the input's rows unchanged, the new rows as configured."""
    problems = []
    tables = {}

    for name, data in output.items():
        try:
            table = DbcTable.from_bytes(data, layout.get(name), layout.file_name(name))
        except DbcError as e:
            problems.append(str(e))
            continue

        tables[name] = table
        problems += [w for w in table.warnings if "points past" in w]
        ids = [to_signed(r[0]) for r in table.rows]

        if len(ids) != len(set(ids)):
            problems.append(f"{layout.file_name(name)}: duplicate ids")

        if name not in base:
            continue

        before = DbcTable.from_bytes(base[name], layout.get(name))

        if bytes(table.strings[:len(before.strings)]) != bytes(before.strings):
            problems.append(f"{layout.file_name(name)}: the input's string block changed")

        touched = result.changes.get(name, TableChange()).touched()
        after = table.by_id()

        for row in before.rows:
            row_id = to_signed(row[0])

            if row_id not in touched and after.get(row_id) != row:
                problems.append(f"{layout.file_name(name)}: input row {row_id} changed")
                break

        for row_id in result.changes.get(name, TableChange()).removed:
            if row_id in after:
                problems.append(f"{layout.file_name(name)}: row {row_id} should have been removed")

    m = config.map
    z = config.zone

    if "Map" in tables and "AreaTable" in tables:
        maps, areas = tables["Map"], tables["AreaTable"]
        row = maps.by_id().get(m.id)

        if row is None:
            problems.append(f"Map.dbc: no row {m.id}")
        else:
            expect = {"instanceType": m.instance_type, "areaTableID": z.id, "expansionID": m.expansion,
                      "maxPlayers": m.max_players, "loadingScreenID": result.loading_screen_id}

            for column, value in expect.items():
                if maps.get(row, column) != value:
                    problems.append(f"Map.dbc row {m.id}: {column} is {maps.get(row, column)}, expected {value}")

            if maps.get_str(row, "directory") != m.directory:
                problems.append(f"Map.dbc row {m.id}: directory is not {m.directory}")

            if maps.get_loc(row, "mapName") != m.name.slots():
                problems.append(f"Map.dbc row {m.id}: the name is not in every locale")

        by_id = areas.by_id()
        bits = {}

        for area_id in config.area_ids():
            area = by_id.get(area_id)

            if area is None:
                problems.append(f"AreaTable.dbc: no row {area_id}")
                continue

            if areas.get(area, "continentID") != m.id:
                problems.append(f"AreaTable.dbc row {area_id}: continentID is not {m.id}")

            parent = 0 if area_id == z.id else z.id

            # A subzone whose parent has no row is a null dereference in the client (AreaList.cpp).
            if areas.get(area, "parentAreaID") != parent or (parent and parent not in by_id):
                problems.append(f"AreaTable.dbc row {area_id}: parentAreaID is not {parent}, or it has no row")

            flags = areas.get(area, "flags")

            if flags & z.set_flags != z.set_flags or flags & z.clear_flags:
                problems.append(f"AreaTable.dbc row {area_id}: flags 0x{flags:X} do not follow the config")

            # Bits AzerothCore has no name for are read by nothing, and no config can name them to clear them.
            harmful = flags & ~z.set_flags & ~HARMLESS_TEMPLATE_FLAGS & sum(AREA_FLAGS.values())

            if harmful:
                problems.append(f"AreaTable.dbc row {area_id}: keeps {' | '.join(flag_names(harmful))} from template "
                                f"{z.template}; add them to zone.clear_flags (or set_flags when they are wanted)")

            bits[area_id] = areas.get(area, "areaBit")

        all_bits = [areas.get(r, "areaBit") for r in areas.rows]

        for area_id, bit in bits.items():
            if bit >= EXPLORE_BITS or all_bits.count(bit) != 1:
                problems.append(f"AreaTable.dbc row {area_id}: area bit {bit} is not unique or not below 4096")

    if "LoadingScreens" in tables and result.loading_screen_id not in tables["LoadingScreens"].ids():
        problems.append(f"LoadingScreens.dbc: no row {result.loading_screen_id}")

    if config.light and "Light" in tables:
        light = tables["Light"].by_id().get(result.light_id)

        if light is None or tables["Light"].get(light, "continentID") != m.id:
            problems.append(f"Light.dbc: no default light {result.light_id} for map {m.id}")

    if config.battleground and "BattlemasterList" in tables and "PvpDifficulty" in tables:
        bml = tables["BattlemasterList"].by_id().get(config.battleground.id)

        if bml is None or tables["BattlemasterList"].get(bml, "mapID[0]") != m.id:
            problems.append(f"BattlemasterList.dbc: no row {config.battleground.id} for map {m.id}")

        pvp = tables["PvpDifficulty"]
        ranges = [pvp.get(r, "rangeIndex") for r in pvp.rows if pvp.get(r, "mapID") == m.id]

        if sorted(ranges) != sorted(b.range_index for b in config.battleground.brackets):
            problems.append(f"PvpDifficulty.dbc: the brackets of map {m.id} are not the config's")

    return problems
