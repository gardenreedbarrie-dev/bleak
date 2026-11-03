"""The races config (races.json): which races to add, which stock races they borrow from, and server settings."""

from __future__ import annotations

import dataclasses
import json
import os
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
    # Racial skill lines of the template race this race does not get (SkillLine ids, such as 756 Racial - Blood Elf):
    # no bit in their SkillRaceClassInfo / SkillLineAbility masks, no playercreateinfo rows, no action bar buttons.
    drop_skill_lines: list[int] = field(default_factory=list)
    # Ids of the race's own racial spells (Config.spells): new Spell.dbc rows and spell_dbc rows.
    racial_spells: list[int] = field(default_factory=list)
    # The race's id on the realm `update` works on, when that realm's own race patch put it in another ChrRaces slot
    # (the Bleakhold realm reuses stock creature display slots: High Elf 15, Eredar 19). None: id. build always uses id.
    realm_id: int | None = None
    # Set by Config.for_realm() to races.json's id: an earlier update may have written rows for it (see update.py).
    build_id: int | None = None

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


# Spell.dbc string columns RaceForge fills from a SpellDef (every locale slot, like the race names).
SPELL_TEXT_FIELDS = {"name": "name", "subtext": "nameSubtext", "description": "description", "aura_description": "auraDescription"}
# Longest text AzerothCore's spell_dbc columns take (Name_Lang_* and NameSubtext_Lang_* varchar(100),
# AuraDescription_Lang_* varchar(550), Description_Lang_* text).
SPELL_TEXT_LIMITS = {"name": 100, "subtext": 100, "description": 4000, "aura_description": 550}
# Who gives a spell of races.json to the player: race (a racial a race lists, taught at creation and by
# mod-bleakhold), server (a module casts it on the player), module (a module teaches it; the player casts it).
CAST_BY = ("race", "server", "module")
CAST_BY_TEXT = {"race": "racial", "server": "server-cast", "module": "module-taught"}


@dataclass
class SpellDef:
    """A new Spell.dbc row: the texts, the icon and visual, and every other column by its client name.

    cast_by "race": a racial, listed by a race's racials.spells. cast_by "server": a spell no race learns (a server
    module casts it); it gets its Spell.dbc row only. cast_by "module": a spell a server module teaches and the player
    casts from the spellbook (Walk on Air's racial, mod-bleakhold-ui): like server, no race lists it and it gets no
    playercreateinfo row. server_row: the SQL file (relative to the repository root) that
    holds the spell_dbc row when another part of the project owns it; RaceForge then writes no spell_dbc row of its own
    and checks that file's row against the Spell.dbc row field for field. text_locales: the locale slots that get the
    texts (all nine by default, like the race names)."""
    id: int
    name: str
    subtext: str = ""
    description: str = ""
    aura_description: str = ""
    icon: int = 0
    icon_name: str = ""
    visual: int = 0
    fields: dict = field(default_factory=dict)
    comment: str = ""
    cast_by: str = "race"
    server_row: str = ""
    text_locales: list = field(default_factory=lambda: list(LOCALES))

    def text(self, key: str) -> str:
        return getattr(self, key)

    @property
    def passive(self) -> bool:
        return bool(int(self.fields.get("attributes", 0)) & 0x40)


@dataclass
class Archives:
    # RaceForge's own archive: it takes a modified table for the players whose patches hold no copy of it.
    own: str = "patch-R.MPQ"
    # The launcher's optional packs ({pack: [Data/... file patterns]}): the update works out the winning copy of each
    # table with and without every pack.
    optional_packs: dict = field(default_factory=dict)


@dataclass
class Config:
    races: list[RaceConfig]
    policy: Policy
    path: str = ""
    spells: dict = field(default_factory=dict)
    archives: Archives = field(default_factory=Archives)

    def racial_spell_ids(self) -> list[int]:
        """Every racial spell some race has, in id order."""
        return sorted({s for race in self.races for s in race.racial_spells})

    def spell_ids(self) -> list[int]:
        """Every spell that gets a Spell.dbc row (the racials and the server-cast spells), in id order."""
        return sorted(self.spells)

    def server_sql_spell_ids(self) -> list[int]:
        """The spells whose spell_dbc row RaceForge writes: those no other SQL file (server_row) holds."""
        return [s for s in self.spell_ids() if not self.spells[s].server_row]

    def for_realm(self) -> "Config":
        """The config as `update` sees the realm: every race at its realm_id (when set), build_id keeping races.json's
        id. Everything race-specific (the bits, the SQL) then follows from id as for a build."""
        races = [dataclasses.replace(r, id=r.realm_id or r.id, realm_id=None, build_id=r.id) for r in self.races]
        return dataclasses.replace(self, races=races)

    def action_bar_spell(self, race: RaceConfig) -> int:
        """The race's first active (not passive) racial: it takes the start action bar buttons of the template's
        dropped racials. 0 when the race has none."""
        for spell_id in race.racial_spells:
            if not self.spells[spell_id].passive:
                return spell_id

        return 0


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
        realm_id=_optional_int(data, "realm_id", where),
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

    if race.realm_id is not None:
        if not 1 <= race.realm_id <= MAX_RACE_ID:
            raise ConfigError(f"{where}: realm_id must be between 1 and {MAX_RACE_ID} (the client keeps race ids in 32-bit masks)")

        if race.realm_id in PANDAREN_RACE_IDS:
            raise ConfigError(f"{where}: realm_id {race.realm_id}: Bleakhold has no Pandaren (ids {PANDAREN_RACE_IDS} stay unused)")

        if race.realm_id in (race.template_race, race.faction_race):
            raise ConfigError(f"{where}: realm_id {race.realm_id} is the race's template_race or faction_race, a stock race of its own")

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

    racials = data.get("racials")

    if racials is not None:
        if not isinstance(racials, dict):
            raise ConfigError(f"{where}.racials: must be an object")

        unknown = set(racials) - {"drop_template_skill_lines", "spells", "comment"}

        if unknown:
            raise ConfigError(f"{where}.racials: unknown keys {sorted(unknown)}")

        race.drop_skill_lines = _id_list(racials.get("drop_template_skill_lines"), f"{where}.racials.drop_template_skill_lines")
        race.racial_spells = _id_list(racials.get("spells"), f"{where}.racials.spells")

    return race


def _id_list(value, where: str) -> list[int]:
    if value is None:
        return []

    if not isinstance(value, list) or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value):
        raise ConfigError(f"{where}: must be a list of positive ids")

    if len(set(value)) != len(value):
        raise ConfigError(f"{where}: lists an id twice")

    return list(value)


def parse_spell(data: dict, index: int) -> SpellDef:
    where = f"spells[{index}]"

    if not isinstance(data, dict):
        raise ConfigError(f"{where}: must be an object")

    unknown = set(data) - {"id", "name", "subtext", "description", "aura_description", "icon", "icon_name", "visual", "fields", "comment",
                           "cast_by", "server_row", "text_locales"}

    if unknown:
        raise ConfigError(f"{where}: unknown keys {sorted(unknown)}")

    spell_id = _optional_int(data, "id", where)

    # Spell ids are signed 32-bit in the client and in spell_dbc.
    if spell_id is None or not 1 <= spell_id <= 0x7FFFFFFF:
        raise ConfigError(f"{where}: id must be between 1 and 2147483647")

    spell = SpellDef(id=spell_id, name=str(data.get("name") or ""), subtext=str(data.get("subtext") or ""),
                     description=str(data.get("description") or ""), aura_description=str(data.get("aura_description") or ""),
                     icon=_optional_int(data, "icon", where) or 0, icon_name=str(data.get("icon_name") or ""),
                     visual=_optional_int(data, "visual", where) or 0, comment=str(data.get("comment") or ""),
                     cast_by=str(data.get("cast_by") or "race"), server_row=str(data.get("server_row") or ""))
    where = f"{where} ({spell.name or spell.id})"

    if spell.cast_by not in CAST_BY:
        raise ConfigError(f"{where}: cast_by must be race, server or module")

    if spell.server_row and (os.path.isabs(spell.server_row) or ".." in spell.server_row.replace("\\", "/").split("/")):
        raise ConfigError(f"{where}: server_row must be a path inside the repository, relative to its root")

    if "text_locales" in data:
        locales = data["text_locales"]

        if not isinstance(locales, list) or not locales or any(code not in LOCALES for code in locales):
            raise ConfigError(f"{where}: text_locales must list locales of {', '.join(LOCALES)}")

        spell.text_locales = list(locales)

    if not spell.name.strip():
        raise ConfigError(f"{where}: name is empty")

    for key, limit in SPELL_TEXT_LIMITS.items():
        if len(spell.text(key).encode("utf-8")) > limit:
            raise ConfigError(f"{where}: {key} is longer than the {limit} bytes AzerothCore's spell_dbc column holds")

    fields = data.get("fields") or {}

    if not isinstance(fields, dict):
        raise ConfigError(f"{where}.fields: must be an object of Spell.dbc column names and numbers")

    for key, value in fields.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{where}.fields.{key}: must be a number")

    spell.fields = dict(fields)
    return spell


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

    realm_ids = [r.realm_id or r.id for r in races]

    if len(set(realm_ids)) != len(realm_ids):
        raise ConfigError(f"{path}: two races have the same realm_id (or id)")

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

    spell_list = data.get("spells") or []

    if not isinstance(spell_list, list):
        raise ConfigError(f"{path}: spells must be a list")

    spells = {}

    for i, spell_data in enumerate(spell_list):
        spell = parse_spell(spell_data, i)

        if spell.id in spells:
            raise ConfigError(f"{path}: two spells have the id {spell.id}")

        spells[spell.id] = spell

    for race in races:
        missing = [s for s in race.racial_spells if s not in spells]

        if missing:
            raise ConfigError(f"{path}: {race.name} ({race.id}): racials.spells {missing} are not defined in spells")

        server_cast = [s for s in race.racial_spells if spells[s].cast_by != "race"]

        if server_cast:
            kinds = " or ".join(sorted({spells[s].cast_by for s in server_cast}))
            raise ConfigError(f"{path}: {race.name} ({race.id}): racials.spells {server_cast} are cast_by {kinds}, which no race learns")

    listed = {s for race in races for s in race.racial_spells}

    for spell in spells.values():
        if spell.cast_by == "race" and spell.id not in listed:
            raise ConfigError(f"{path}: spell {spell.id} ({spell.name}) is a racial no race lists; list it in a race's racials.spells, "
                              "or give it \"cast_by\": \"server\" (a module casts it) or \"module\" (a module teaches it)")

    archives_data = data.get("archives") or {}

    if not isinstance(archives_data, dict):
        raise ConfigError(f"{path}: archives must be an object")

    archives = Archives(own=str(archives_data.get("own") or "patch-R.MPQ"), optional_packs=archives_data.get("optional_packs") or {})

    if not re.fullmatch(r"(?i)patch-[a-z]\.mpq", archives.own):
        raise ConfigError(f"{path}: archives.own must be a patch-<letter>.MPQ name")

    packs = archives.optional_packs

    if not isinstance(packs, dict) or not all(isinstance(k, str) and isinstance(v, list) and all(isinstance(p, str) for p in v) for k, v in packs.items()):
        raise ConfigError(f"{path}: archives.optional_packs must be {{pack: [file patterns]}}")

    return Config(races, policy, path, spells, archives)
