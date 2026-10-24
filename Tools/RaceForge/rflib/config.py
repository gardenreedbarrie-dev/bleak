"""The races config (races.json): which races to add, which stock races they borrow from, and server settings."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# Locale slots of a localized DBC string, in the client's order (s_localeIds in WoW/Source/Client.cpp); slots 9-15
# are unused in 3.3.5a.
LOCALES = ("enUS", "koKR", "frFR", "deDE", "zhCN", "zhTW", "esES", "esMX", "ruRU")

# BLEAKHOLD_RACE_CAPACITY in WoW/Common/BleakholdRaces.h: the client holds race ids below 32.
MAX_RACE_ID = 31

# Later clients use these for Pandaren; Bleakhold has none, so they stay unused here too.
PANDAREN_RACE_IDS = (24, 25, 26)
MONK_CLASS_ID = 10

# ChrRaces BaseLanguage, which AzerothCore reads as the team (Player::TeamIdForRace): 7 Alliance, 1 Horde. The
# Alliance column (RaceMgr::LoadRaces) is 0 for Alliance and 1 for Horde.
TEAM_LANGUAGE = {"alliance": 7, "horde": 1}
ALLIANCE_COLUMN = {"alliance": 0, "horde": 1}


class ConfigError(Exception):
    pass


@dataclass
class Position:
    map: int
    zone: int
    x: float
    y: float
    z: float
    o: float
    comment: str = ""

    @classmethod
    def parse(cls, data: dict, where: str) -> "Position":
        try:
            return cls(int(data["map"]), int(data["zone"]), float(data["x"]), float(data["y"]), float(data["z"]), float(data.get("o", 0.0)), str(data.get("comment", "")))
        except (KeyError, TypeError, ValueError) as e:
            raise ConfigError(f"{where}: needs map, zone, x, y, z and o ({e})") from None


@dataclass
class RaceStats:
    strength: int
    agility: int
    stamina: int
    intellect: int
    spirit: int


@dataclass
class RaceConfig:
    id: int
    name: str
    client_file_string: str
    template_race: int
    faction: str
    faction_race: int
    names: dict[str, str] = field(default_factory=dict)
    name_female: str | None = None
    name_male: str | None = None
    faction_template: int | None = None
    classes: list[int] | None = None
    male_display_id: int | None = None
    female_display_id: int | None = None
    required_expansion: int | None = None
    cinematic_sequence_id: int = 0
    start: Position | None = None
    death_knight_start: Position | None = None
    stats: RaceStats | None = None

    @property
    def bit(self) -> int:
        """The race's bit in 1 << (race - 1) masks."""
        return 1 << (self.id - 1)

    def localized_names(self, field_name: str = "name") -> list[str]:
        """16 locale slots for Name (or NameFemale / NameMale when they are set)."""
        base = {"name": self.name, "nameFemale": self.name_female, "nameMale": self.name_male}[field_name]

        if base is None:
            return []

        slots = [base] * len(LOCALES) + [""] * (16 - len(LOCALES))

        if field_name == "name":
            for code, text in self.names.items():
                slots[LOCALES.index(code)] = text

        return slots


@dataclass
class Policy:
    # Masks equal to every playable race of one faction (Common, faction mounts, ...) follow the new race's faction
    # instead of its template race.
    faction_wide_masks: bool = True
    # Which race's bits Faction.dbc reputation masks copy: "faction_race" or "template_race".
    reputation_from: str = "faction_race"
    # Which race's bits the optional quest/item/spell_area/mail SQL copies.
    content_masks_from: str = "faction_race"


@dataclass
class Config:
    races: list[RaceConfig]
    policy: Policy
    path: str = ""


def _optional_int(data: dict, key: str, where: str) -> int | None:
    value = data.get(key)

    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{where}.{key}: must be a whole number or null")

    return value


def parse_race(data: dict, index: int) -> RaceConfig:
    where = f"races[{index}]"

    for key in ("id", "name", "client_file_string", "template_race", "faction", "faction_race"):
        if key not in data:
            raise ConfigError(f"{where}: missing {key}")

    race = RaceConfig(
        id=_optional_int(data, "id", where),
        name=str(data["name"]),
        client_file_string=str(data["client_file_string"]),
        template_race=_optional_int(data, "template_race", where),
        faction=str(data["faction"]).lower(),
        faction_race=_optional_int(data, "faction_race", where),
        names={str(k): str(v) for k, v in (data.get("names") or {}).items()},
        name_female=data.get("name_female"),
        name_male=data.get("name_male"),
        faction_template=_optional_int(data, "faction_template", where),
        classes=data.get("classes"),
        male_display_id=_optional_int(data, "male_display_id", where),
        female_display_id=_optional_int(data, "female_display_id", where),
        required_expansion=_optional_int(data, "required_expansion", where),
        cinematic_sequence_id=_optional_int(data, "cinematic_sequence_id", where) or 0,
        start=Position.parse(data["start"], f"{where}.start") if data.get("start") else None,
        death_knight_start=Position.parse(data["death_knight_start"], f"{where}.death_knight_start") if data.get("death_knight_start") else None,
    )

    if data.get("stats") is not None:
        stats = data["stats"]

        try:
            race.stats = RaceStats(*(int(stats[k]) for k in ("strength", "agility", "stamina", "intellect", "spirit")))
        except (KeyError, TypeError, ValueError):
            raise ConfigError(f"{where}.stats: needs strength, agility, stamina, intellect and spirit") from None

    where = f"{where} ({race.name})"

    if not 1 <= race.id <= MAX_RACE_ID:
        raise ConfigError(f"{where}: id must be between 1 and {MAX_RACE_ID} (the client keeps race ids in 32-bit masks)")

    if race.id in PANDAREN_RACE_IDS or "pandaren" in race.name.lower() or "pandaren" in race.client_file_string.lower():
        raise ConfigError(f"{where}: Bleakhold has no Pandaren (ids {PANDAREN_RACE_IDS} stay unused)")

    if not race.name.strip():
        raise ConfigError(f"{where}: name is empty")

    if not re.fullmatch(r"[A-Za-z0-9]{1,13}", race.client_file_string):
        # PortraitButton builds "Interface\CharacterFrame\TemporaryPortrait-Female-<ClientFileString>" in 64 bytes,
        # and the string also names files and Lua table keys.
        raise ConfigError(f"{where}: client_file_string must be 1-13 letters or digits")

    if race.faction not in TEAM_LANGUAGE:
        raise ConfigError(f"{where}: faction must be alliance or horde")

    for code in race.names:
        if code not in LOCALES:
            raise ConfigError(f"{where}: unknown locale {code!r} in names (use {', '.join(LOCALES)})")

    for key in ("name_female", "name_male"):
        value = getattr(race, key)

        if value is not None and not isinstance(value, str):
            raise ConfigError(f"{where}.{key}: must be text or null")

    if race.classes is not None:
        if not isinstance(race.classes, list) or not all(isinstance(c, int) and not isinstance(c, bool) for c in race.classes):
            raise ConfigError(f"{where}.classes: must be a list of class ids or null")

        if MONK_CLASS_ID in race.classes:
            raise ConfigError(f"{where}: class 10 (Monk) does not exist in 3.3.5a, and Bleakhold has no Monks")

    if race.required_expansion is not None and not 0 <= race.required_expansion <= 2:
        raise ConfigError(f"{where}: required_expansion must be 0, 1 or 2")

    return race


def load(path: str) -> Config:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path}: not valid JSON ({e})") from None

    return parse(data, path)


def parse(data: dict, path: str = "") -> Config:
    if not isinstance(data, dict) or not isinstance(data.get("races"), list) or not data["races"]:
        raise ConfigError(f"{path}: needs a non-empty races list")

    races = [parse_race(r, i) for i, r in enumerate(data["races"])]
    ids = [r.id for r in races]

    if len(set(ids)) != len(ids):
        raise ConfigError(f"{path}: two races have the same id")

    file_strings = [r.client_file_string.lower() for r in races]

    if len(set(file_strings)) != len(file_strings):
        raise ConfigError(f"{path}: two races have the same client_file_string")

    policy_data = data.get("policy") or {}
    policy = Policy(
        faction_wide_masks=bool(policy_data.get("faction_wide_masks", True)),
        reputation_from=str(policy_data.get("reputation_from", "faction_race")),
        content_masks_from=str(policy_data.get("content_masks_from", "faction_race")),
    )

    for key in ("reputation_from", "content_masks_from"):
        if getattr(policy, key) not in ("faction_race", "template_race"):
            raise ConfigError(f"{path}: policy.{key} must be faction_race or template_race")

    return Config(races, policy, path)
