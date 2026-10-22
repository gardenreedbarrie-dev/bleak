"""The DBC passes: add the configured races to the user's stock DBCs by cloning their template races."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import masks as maskrules
from . import schema_access
from .config import ALLIANCE_COLUMN, TEAM_LANGUAGE, Config, RaceConfig
from .dbc import DbcError, DbcTable, to_signed

# Without these the new races cannot be created or drawn: refuse to run when one is missing.
REQUIRED_TABLES = (
    "ChrRaces",
    "CharBaseInfo",
    "CharStartOutfit",
    "CharSections",
    "CharHairGeosets",
    "CharacterFacialHairStyles",
    "SkillRaceClassInfo",
    "SkillLineAbility",
    "Faction",
    "FactionTemplate",
    "FactionGroup",
)

# Patched when present; read-only ones are only used for checks.
OPTIONAL_TABLES = (
    "NameGen",
    "BarberShopStyle",
    "EmotesTextSound",
    "VocalUISounds",
    "TalentTab",
    "DanceMoves",
    "HelmetGeosetVisData",
    "ChrClasses",
    "CreatureDisplayInfo",
    "CreatureModelData",
    "ItemDisplayInfo",
    "SoundFilter",
)

READ_ONLY_TABLES = ("FactionTemplate", "FactionGroup", "ChrClasses", "CreatureDisplayInfo", "CreatureModelData", "ItemDisplayInfo", "SoundFilter")

# Tables keyed by race (column in RACE_COLUMN): each new race gets a copy of its template race's rows.
RACE_ROW_TABLES = (
    "CharStartOutfit",
    "CharSections",
    "CharHairGeosets",
    "CharacterFacialHairStyles",
    "NameGen",
    "BarberShopStyle",
    "EmotesTextSound",
    "VocalUISounds",
)

RACE_COLUMN = {
    "CharBaseInfo": "raceID",
    "CharStartOutfit": "raceID",
    "CharSections": "raceID",
    "CharHairGeosets": "raceID",
    "CharacterFacialHairStyles": "raceID",
    "NameGen": "raceID",
    "BarberShopStyle": "race",
    "EmotesTextSound": "raceID",
    "VocalUISounds": "raceID",
}

# (table, mask field) pairs tested with 1 << (race - 1) and the rule they follow.
SMART_MASKS = (
    ("SkillRaceClassInfo", "raceMask"),
    ("SkillLineAbility", "raceMask"),
    ("TalentTab", "raceMask"),
    ("DanceMoves", "racemask"),
)

CHAR_SECTIONS_KEY = ("raceID", "sexID", "baseSection", "variationIndex", "colorIndex")


class ForgeError(Exception):
    pass


@dataclass
class RaceSummary:
    race: RaceConfig
    classes: list[int] = field(default_factory=list)
    male_display: int = 0
    female_display: int = 0
    faction_template: int = 0
    start_outfit_items: list[int] = field(default_factory=list)


@dataclass
class TableChange:
    rows_added: int = 0
    values_changed: int = 0
    notes: list[str] = field(default_factory=list)


def find_dbc(input_dir: str, name: str) -> str | None:
    """<name>.dbc in input_dir or input_dir/DBFilesClient, ignoring case (extracted file names vary)."""
    wanted = f"{name}.dbc".lower()

    for folder in (input_dir, os.path.join(input_dir, "DBFilesClient")):
        if not os.path.isdir(folder):
            continue

        for entry in os.listdir(folder):
            if entry.lower() == wanted and os.path.isfile(os.path.join(folder, entry)):
                return os.path.join(folder, entry)

    return None


class Forge:
    def __init__(self, input_dir: str, config: Config, overrides: dict[str, DbcTable] | None = None):
        """overrides: tables to use instead of the files in input_dir (a merged customization package); they are
        always written, as they differ from the user's files."""
        self.input_dir = input_dir
        self.config = config
        self.overrides = overrides or {}
        self.tables: dict[str, DbcTable] = {}
        self.missing: list[str] = []
        self.warnings: list[str] = []
        self.changes: dict[str, TableChange] = {}
        self.summaries: dict[int, RaceSummary] = {}
        self.faction_masks: maskrules.FactionMasks | None = None

    # --- loading ---

    def load(self):
        for name in REQUIRED_TABLES + OPTIONAL_TABLES:
            if name in self.overrides:
                self.tables[name] = self.overrides[name]
                continue

            path = find_dbc(self.input_dir, name)

            if path is None:
                self.missing.append(name)
                continue

            try:
                table = DbcTable.read(path, schema_access.get(name))
            except DbcError as e:
                raise ForgeError(str(e)) from None

            self.tables[name] = table
            self.warnings.extend(table.warnings)

        missing_required = [n for n in REQUIRED_TABLES if n in self.missing]

        if missing_required:
            raise ForgeError(f"{self.input_dir}: missing {', '.join(n + '.dbc' for n in missing_required)} (point --dbc at the DBFilesClient folder of your 3.3.5a client)")

        for name in OPTIONAL_TABLES:
            if name in self.missing:
                self.warnings.append(f"{name}.dbc not found: {'not patched' if name not in READ_ONLY_TABLES else 'checks that need it are skipped'}")

    def table(self, name: str) -> DbcTable | None:
        return self.tables.get(name)

    def change(self, name: str) -> TableChange:
        return self.changes.setdefault(name, TableChange())

    # --- checks before anything is changed ---

    def check_inputs(self):
        races = self.tables["ChrRaces"]
        by_id = races.by_id()

        for race in self.config.races:
            label = f"{race.name} ({race.id})"

            if race.id in by_id:
                raise ForgeError(f"{label}: ChrRaces already has race {race.id}; run RaceForge on stock DBCs, not on its own output")

            for role, source in (("template_race", race.template_race), ("faction_race", race.faction_race)):
                row = by_id.get(source)

                if row is None:
                    raise ForgeError(f"{label}: {role} {source} is not in ChrRaces")

                if races.get(row, "flags") & 0x1:
                    raise ForgeError(f"{label}: {role} {source} is not a playable race")

            if self.faction_masks.race_faction.get(race.faction_race) != race.faction:
                raise ForgeError(f"{label}: faction_race {race.faction_race} is not on the {race.faction} side")

            for other in races.rows:
                if races.get_str(other, "clientFileString").lower() == race.client_file_string.lower():
                    raise ForgeError(f"{label}: client_file_string {race.client_file_string} is already used by race {to_signed(races.get(other, 'id'))}")

            if race.faction_template is not None:
                faction = maskrules.faction_of_template(race.faction_template, self.tables["FactionTemplate"], self.tables["FactionGroup"])

                if faction != race.faction:
                    raise ForgeError(f"{label}: faction_template {race.faction_template} is not on the {race.faction} side (its faction group says {faction or 'neither'})")

            template_classes = self.template_classes(race.template_race)

            if not template_classes:
                raise ForgeError(f"{label}: CharBaseInfo has no classes for template race {race.template_race}")

            if race.classes is not None:
                extra = sorted(set(race.classes) - set(template_classes))

                if extra:
                    raise ForgeError(f"{label}: classes {extra} are not playable by template race {race.template_race} (it has {template_classes}); RaceForge can only keep or drop the template's classes")

    def template_classes(self, template_race: int) -> list[int]:
        base = self.tables["CharBaseInfo"]
        return [base.get(row, "classID") for row in base.rows if base.get(row, "raceID") == template_race]

    # --- passes ---

    def run(self):
        self.faction_masks = maskrules.compute_faction_masks(self.tables["ChrRaces"], self.tables.get("FactionTemplate"), self.tables.get("FactionGroup"))
        self.check_inputs()

        for race in self.config.races:
            summary = RaceSummary(race)
            self.summaries[race.id] = summary
            self.add_chr_race(race, summary)
            self.add_char_base_info(race, summary)

            for name in RACE_ROW_TABLES:
                if name in self.tables:
                    self.clone_race_rows(name, race, summary)

        self.sort_char_sections()

        for race in self.config.races:
            self.add_mask_bits(race)

    def add_chr_race(self, race: RaceConfig, summary: RaceSummary):
        races = self.tables["ChrRaces"]
        by_id = races.by_id()
        template = by_id[race.template_race]
        row = list(template)

        races.set(row, "id", race.id)
        races.set(row, "flags", races.get(template, "flags") & ~0x1)

        # The three faction columns must agree: the client sorts races into Alliance/Horde by the FactionTemplate's
        # group, AzerothCore takes the team from BaseLanguage and its race masks from the Alliance column.
        faction_template = race.faction_template if race.faction_template is not None else races.get(by_id[race.faction_race], "factionID")
        races.set(row, "factionID", faction_template)
        races.set(row, "baseLanguage", TEAM_LANGUAGE[race.faction])
        races.set(row, "alliance", ALLIANCE_COLUMN[race.faction])

        # ClientPrefix stays the template's, so helmet models (<model>_<prefix><sex>.m2) are the template's.
        races.set_str(row, "clientFileString", race.client_file_string)
        races.set_loc(row, "name", race.localized_names("name"))

        for field_name in ("nameFemale", "nameMale"):
            configured = race.localized_names(field_name)

            if configured:
                races.set_loc(row, field_name, configured)
            else:
                # Gendered names exist only in some locales; where the template has one, use the race's name there.
                template_names = races.get_loc(template, field_name)
                names = race.localized_names("name")
                races.set_loc(row, field_name, [names[i] if text else "" for i, text in enumerate(template_names)])

        if race.male_display_id is not None:
            races.set(row, "maleDisplayID", race.male_display_id)

        if race.female_display_id is not None:
            races.set(row, "femaleDisplayID", race.female_display_id)

        races.set(row, "cinematicSequenceID", race.cinematic_sequence_id)
        expansion = race.required_expansion if race.required_expansion is not None else min(races.get(template, "requiredExpansion"), 2)
        races.set(row, "requiredExpansion", expansion)

        races.rows.append(row)
        summary.male_display = races.get(row, "maleDisplayID")
        summary.female_display = races.get(row, "femaleDisplayID")
        summary.faction_template = faction_template
        change = self.change("ChrRaces")
        change.rows_added += 1
        change.notes.append(f"race {race.id} {race.name}: from race {race.template_race}, {race.faction}, FactionTemplate {faction_template}, displays {summary.male_display}/{summary.female_display}")

    def add_char_base_info(self, race: RaceConfig, summary: RaceSummary):
        base = self.tables["CharBaseInfo"]
        classes = self.template_classes(race.template_race)

        if race.classes is not None:
            classes = [c for c in classes if c in race.classes]

        for class_id in classes:
            base.rows.append([race.id, class_id])

        summary.classes = classes
        change = self.change("CharBaseInfo")
        change.rows_added += len(classes)
        change.notes.append(f"race {race.id}: classes {classes}")

    def clone_race_rows(self, name: str, race: RaceConfig, summary: RaceSummary):
        table = self.tables[name]
        race_column = RACE_COLUMN[name]
        source_rows = [row for row in table.rows if table.get(row, race_column) == race.template_race]

        if name == "CharStartOutfit":
            source_rows = [row for row in source_rows if table.get(row, "classID") in summary.classes]

        if name == "NameGen":
            # LoadNames reads one contiguous run of rows per race and sex.
            source_rows = sorted(source_rows, key=lambda r: table.get(r, "sex"))

        next_id = table.max_id() + 1
        added = []

        for source in source_rows:
            row = list(source)
            table.set(row, race_column, race.id)

            if not table.schema.generated_id:
                table.set(row, "id", next_id)
                next_id += 1

            added.append(row)

        table.rows.extend(added)

        if name == "CharStartOutfit":
            for row in added:
                summary.start_outfit_items.extend(v for v in (table.get(row, f"itemID[{i}]") for i in range(24)) if 0 < v < 0x7FFFFFFF)

        change = self.change(name)
        change.rows_added += len(added)
        change.notes.append(f"race {race.id}: {len(added)} rows from race {race.template_race}")

        if not added:
            self.warnings.append(f"{name}: template race {race.template_race} has no rows, so race {race.id} has none either")

    def sort_char_sections(self):
        # BuildComponentArray sizes its arrays from runs of consecutive rows, so every (race, sex, section, variation)
        # must be one run. A stable sort keeps the order of duplicate keys (the last one wins in the client).
        sections = self.tables["CharSections"]
        columns = [sections.col(c) for c in CHAR_SECTIONS_KEY]

        def key(row):
            return tuple(to_signed(row[c]) for c in columns)

        keys = [key(r) for r in sections.rows]

        if all(keys[i] <= keys[i + 1] for i in range(len(keys) - 1)):
            return

        race_column = sections.col("raceID")
        new_races = {r.id for r in self.config.races}
        stock_before = [tuple(r) for r in sections.rows if r[race_column] not in new_races]
        sections.rows.sort(key=key)
        stock_after = [tuple(r) for r in sections.rows if r[race_column] not in new_races]

        if stock_before != stock_after:
            self.change("CharSections").notes.append("the stock rows were not in (race, sex, section, variation, color) order; the table was sorted")
        else:
            self.change("CharSections").notes.append("the new rows were moved into (race, sex, section, variation, color) order")

    def add_mask_bits(self, race: RaceConfig):
        policy = self.config.policy

        for name, field_name in SMART_MASKS:
            table = self.tables.get(name)

            if table is None:
                continue

            column = table.col(field_name)
            changed = 0

            for row in table.rows:
                if maskrules.wants_bit(row[column], race, self.faction_masks, race.template_race, policy.faction_wide_masks):
                    row[column] |= race.bit
                    changed += 1

            self.change(name).values_changed += changed
            self.change(name).notes.append(f"race {race.id}: bit 0x{race.bit:X} added to {changed} {field_name} masks")

        # Reputation: the new race starts with the reputations of the race named by the policy.
        faction = self.tables["Faction"]
        source = race.faction_race if policy.reputation_from == "faction_race" else race.template_race
        columns = faction.schema.field_columns("reputationRaceMask")
        changed = 0

        for row in faction.rows:
            for column in columns:
                mask = row[column]

                if mask and mask != 0xFFFFFFFF and not mask & race.bit and mask & maskrules.race_bit(source):
                    row[column] |= race.bit
                    changed += 1

        self.change("Faction").values_changed += changed
        self.change("Faction").notes.append(f"race {race.id}: reputation masks copied from race {source} ({changed} masks)")

        # Helmets hide exactly the template race's geosets for the new race; this table uses 1 << race. The bit is
        # copied both ways: masks like "every race but a few" can have the new race's bit set already.
        helmets = self.tables.get("HelmetGeosetVisData")

        if helmets is not None:
            columns = helmets.schema.field_columns("hideGeoset")
            new_bit = 1 << race.id
            template_bit = 1 << race.template_race
            added = cleared = 0

            for row in helmets.rows:
                for column in columns:
                    if row[column] & template_bit and not row[column] & new_bit:
                        row[column] |= new_bit
                        added += 1
                    elif not row[column] & template_bit and row[column] & new_bit:
                        row[column] &= ~new_bit
                        cleared += 1

            self.change("HelmetGeosetVisData").values_changed += added + cleared
            self.change("HelmetGeosetVisData").notes.append(f"race {race.id}: bit 1<<{race.id} copied from 1<<{race.template_race} ({added} set, {cleared} cleared)")

    # --- output ---

    def changed_tables(self) -> list[str]:
        return [name for name in self.tables if name not in READ_ONLY_TABLES and self.tables[name].is_modified()]

    def write(self, out_dir: str) -> dict[str, list[str]]:
        """Write every changed table to out/client/DBFilesClient and out/server/dbc (identical files)."""
        written = {"client": [], "server": []}

        for name in self.changed_tables():
            data = self.tables[name].to_bytes()
            base = os.path.basename(self.tables[name].schema.filename.replace("\\", "/"))

            for kind, folder in (("client", os.path.join(out_dir, "client", "DBFilesClient")), ("server", os.path.join(out_dir, "server", "dbc"))):
                os.makedirs(folder, exist_ok=True)
                path = os.path.join(folder, base)

                with open(path, "wb") as f:
                    f.write(data)

                written[kind].append(path)

        return written

