"""Checks on what RaceForge wrote, re-read from disk: the client's loader rules and the race data's consistency."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import masks as maskrules
from . import schema_access
from .config import ALLIANCE_COLUMN, LOCALES, MONK_CLASS_ID, PANDAREN_RACE_IDS, TEAM_LANGUAGE, Config
from .dbc import DbcError, DbcTable, to_signed
from .forge import CHAR_SECTIONS_KEY, RACE_COLUMN, RACE_ROW_TABLES, READ_ONLY_TABLES, SMART_MASKS, find_dbc

LANGUAGE_COMMON = 98
LANGUAGE_ORCISH = 109


@dataclass
class Check:
    status: str  # PASS, FAIL, WARN, SKIP
    name: str
    detail: str = ""


@dataclass
class Validation:
    checks: list[Check] = field(default_factory=list)

    def add(self, status: str, name: str, detail: str = ""):
        self.checks.append(Check(status, name, detail))

    def expect(self, condition: bool, name: str, detail: str = "", failure: str = "FAIL"):
        self.add("PASS" if condition else failure, name, detail)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status == "FAIL"]


def load_output(out_dir: str, stock_dir: str) -> tuple[dict[str, DbcTable], dict[str, DbcTable], list[str]]:
    """(stock tables, result tables, names written): result = the written file, else the stock one."""
    stock, result, written = {}, {}, []

    for name in schema_access.names():
        schema = schema_access.get(name)
        stock_path = find_dbc(stock_dir, name)

        if stock_path:
            stock[name] = DbcTable.read(stock_path, schema)

        base = os.path.basename(schema.filename.replace("\\", "/"))
        out_path = os.path.join(out_dir, "client", "DBFilesClient", base)

        if os.path.isfile(out_path):
            result[name] = DbcTable.read(out_path, schema)
            written.append(name)
        elif name in stock:
            result[name] = stock[name]

    return stock, result, written


def validate(out_dir: str, stock_dir: str, config: Config, mpq_path: str | None = None) -> Validation:
    v = Validation()

    # --- every written file loads with the client's layout, and the server copy is identical ---
    try:
        stock, result, written = load_output(out_dir, stock_dir)
    except DbcError as e:
        v.add("FAIL", "written DBCs load with the client's column count and row size", str(e))
        return v

    v.add("PASS", "written DBCs load with the client's column count and row size", ", ".join(sorted(written)))
    v.expect(bool(written), "RaceForge wrote DBC files")

    for name in written:
        schema = schema_access.get(name)
        base = os.path.basename(schema.filename.replace("\\", "/"))
        problems = []

        with open(os.path.join(out_dir, "client", "DBFilesClient", base), "rb") as f:
            client_bytes = f.read()

        server = os.path.join(out_dir, "server", "dbc", base)

        if not os.path.isfile(server):
            problems.append("no server copy")
        else:
            with open(server, "rb") as f:
                if f.read() != client_bytes:
                    problems.append("the server copy differs")

        table = result[name]
        problems.extend(w for w in table.warnings if "points past the string block" in w)

        if not schema.generated_id:
            ids = [to_signed(r[0]) for r in table.rows]

            if len(ids) != len(set(ids)):
                problems.append("duplicate ids")

        v.expect(not problems, f"{base}: {schema.num_columns} columns of {schema.row_size} bytes like {name}Rec, {len(table.rows)} rows, server copy identical, unique ids, string offsets valid",
                 "; ".join(problems))

    races = result["ChrRaces"]
    races_by_id = races.by_id()

    # --- stock rows are untouched, apart from the new races' bits ---
    for name in written:
        if name not in stock:
            continue

        problems = stock_rows_unchanged(name, stock[name], result[name], config)
        v.expect(not problems, f"{name}: stock rows are unchanged except for the new races' mask bits", "; ".join(problems[:5]))

    stock_masks = maskrules.compute_faction_masks(stock["ChrRaces"], stock.get("FactionTemplate"), stock.get("FactionGroup"))

    # --- per race ---
    for race in config.races:
        label = f"{race.name} ({race.id})"
        row = races_by_id.get(race.id)

        if row is None:
            v.add("FAIL", f"{label}: ChrRaces row exists")
            continue

        template = races_by_id.get(race.template_race)
        v.add("PASS", f"{label}: ChrRaces row exists")
        v.expect(not races.get(row, "flags") & 0x1, f"{label}: playable (ChrRaces flag 0x1 clear)")
        v.expect(race.id <= 31 and race.id not in PANDAREN_RACE_IDS, f"{label}: race id fits the client's 32-bit masks and is not a Pandaren id")

        faction = maskrules.faction_of_template(races.get(row, "factionID"), result.get("FactionTemplate"), result.get("FactionGroup"))
        language = races.get(row, "baseLanguage")
        alliance = races.get(row, "alliance")
        agree = faction == race.faction and language == TEAM_LANGUAGE[race.faction] and alliance == ALLIANCE_COLUMN[race.faction]
        v.expect(agree, f"{label}: FactionID, BaseLanguage and Alliance all say {race.faction}",
                 f"FactionTemplate {races.get(row, 'factionID')} -> {faction}, BaseLanguage {language}, Alliance {alliance}")

        names = races.get_loc(row, "name")
        v.expect(all(names[i] for i in range(len(LOCALES))), f"{label}: Name is set for every locale", ", ".join(f"{LOCALES[i]}={names[i]!r}" for i in range(len(LOCALES))))
        file_string = races.get_str(row, "clientFileString")
        v.expect(file_string == race.client_file_string and len(file_string) <= 13 and file_string.isalnum(), f"{label}: ClientFileString {file_string!r} (13 characters at most)")
        v.expect(races.get_str(row, "clientPrefix") == races.get_str(template, "clientPrefix"), f"{label}: ClientPrefix {races.get_str(row, 'clientPrefix')!r} is the template's (helmet models)")
        v.expect(races.get(row, "requiredExpansion") <= 2, f"{label}: RequiredExpansion {races.get(row, 'requiredExpansion')} is at most 2")
        v.expect(races.get(row, "cinematicSequenceID") == race.cinematic_sequence_id, f"{label}: CinematicSequenceID {races.get(row, 'cinematicSequenceID')}")

        check_displays(v, label, races, row, result)

        base = result["CharBaseInfo"]
        classes = [base.get(r, "classID") for r in base.rows if base.get(r, "raceID") == race.id]
        v.expect(bool(classes) and MONK_CLASS_ID not in classes, f"{label}: CharBaseInfo classes {classes}")

        if "ChrClasses" in result:
            known = result["ChrClasses"].ids()
            v.expect(all(c in known for c in classes), f"{label}: every class exists in ChrClasses")

        outfits = result["CharStartOutfit"]
        pairs = {(outfits.get(r, "classID"), outfits.get(r, "sexID")) for r in outfits.rows if outfits.get(r, "raceID") == race.id}
        template_pairs = {(outfits.get(r, "classID"), outfits.get(r, "sexID")) for r in outfits.rows if outfits.get(r, "raceID") == race.template_race and outfits.get(r, "classID") in classes}
        v.expect(pairs == template_pairs, f"{label}: CharStartOutfit has the template's class/sex outfits", f"{len(pairs)} outfits")

        if "ItemDisplayInfo" in result:
            displays = result["ItemDisplayInfo"].ids()
            missing = sorted({to_signed(outfits.get(r, f"displayItemID[{i}]")) for r in outfits.rows if outfits.get(r, "raceID") == race.id for i in range(24)}
                             - displays - {0, -1})
            v.expect(not missing, f"{label}: every start outfit display id exists in ItemDisplayInfo", f"missing {missing[:10]}")
        else:
            v.add("SKIP", f"{label}: start outfit display ids against ItemDisplayInfo", "ItemDisplayInfo.dbc not given")

        for name in RACE_ROW_TABLES:
            if name not in result:
                continue

            table = result[name]
            column = table.col(RACE_COLUMN[name])
            count = sum(1 for r in table.rows if r[column] == race.id)
            expected = sum(1 for r in table.rows if r[column] == race.template_race and (name != "CharStartOutfit" or table.get(r, "classID") in classes))
            v.expect(count == expected, f"{label}: {name} has as many rows as race {race.template_race}", f"{count} rows")

        sections = result["CharSections"]
        for sex in (0, 1):
            skins = [r for r in sections.rows if sections.get(r, "raceID") == race.id and sections.get(r, "sexID") == sex and sections.get(r, "baseSection") == 0]
            v.expect(bool(skins), f"{label}: CharSections has skins for sex {sex}")

        check_masks(v, label, race, result, stock_masks, config)

    # --- whole tables ---
    sections = result["CharSections"]
    columns = [sections.col(c) for c in CHAR_SECTIONS_KEY]
    keys = [tuple(to_signed(r[c]) for c in columns) for r in sections.rows]
    v.expect(all(keys[i] <= keys[i + 1] for i in range(len(keys) - 1)), "CharSections is sorted by race, sex, section, variation, color")

    if "NameGen" in result:
        v.expect(contiguous(result["NameGen"], ("raceID", "sex")), "NameGen rows are contiguous per race and sex")

    check_no_pandaren_or_monk(v, result)

    for name in written:
        if name in READ_ONLY_TABLES:
            v.add("FAIL", f"{name} was written although RaceForge only reads it")

    if mpq_path:
        check_mpq(v, mpq_path, out_dir, written)

    return v


def stock_rows_unchanged(name: str, stock: DbcTable, result: DbcTable, config: Config) -> list[str]:
    """Every stock row must still be there, identical except that mask columns may gain new-race bits."""
    problems = []
    allowed = {}  # column index -> bits that may be added
    new_bits = sum(r.bit for r in config.races)

    for table_name, field_name in SMART_MASKS:
        if table_name == name:
            allowed[result.col(field_name)] = new_bits

    if name == "Faction":
        for column in result.schema.field_columns("reputationRaceMask"):
            allowed[column] = new_bits

    if name == "HelmetGeosetVisData":
        for column in result.schema.field_columns("hideGeoset"):
            allowed[column] = sum(1 << r.id for r in config.races)

    if name == "CharSections" or result.schema.generated_id:
        # Sorted (CharSections) or keyed by position: compare as multisets / prefixes.
        if result.schema.generated_id:
            if [tuple(r) for r in result.rows[:len(stock.rows)]] != [tuple(r) for r in stock.rows]:
                problems.append("the stock rows changed or moved")
        else:
            remaining = {}

            for row in result.rows:
                remaining[tuple(row)] = remaining.get(tuple(row), 0) + 1

            for row in stock.rows:
                key = tuple(row)

                if not remaining.get(key):
                    problems.append(f"stock row id {to_signed(row[0])} changed")
                    break

                remaining[key] -= 1

        return problems

    result_by_id = result.by_id()

    for row in stock.rows:
        other = result_by_id.get(to_signed(row[0]))

        if other is None:
            problems.append(f"stock row {to_signed(row[0])} is missing")
            continue

        for i, (a, b) in enumerate(zip(row, other)):
            if a == b:
                continue

            bits = allowed.get(i)

            if bits is None or (b & ~bits) != a:
                problems.append(f"row {to_signed(row[0])} column {result.schema.columns[i].name}: {a} -> {b}")

    if len(result.rows) < len(stock.rows):
        problems.append("rows were removed")

    return problems


def check_displays(v: Validation, label: str, races: DbcTable, row: list[int], result: dict[str, DbcTable]):
    # Player_C logs a missing CreatureDisplayInfo row and then dereferences it: both displays must exist.
    displays = result.get("CreatureDisplayInfo")
    models = result.get("CreatureModelData")

    if displays is None:
        v.add("SKIP", f"{label}: display ids exist in CreatureDisplayInfo", "CreatureDisplayInfo.dbc not given")
        return

    by_id = displays.by_id()
    model_ids = models.ids() if models is not None else None

    for column in ("maleDisplayID", "femaleDisplayID"):
        display_id = races.get(row, column)
        display = by_id.get(display_id)

        if display is None:
            v.add("FAIL", f"{label}: {column} {display_id} exists in CreatureDisplayInfo")
            continue

        model_id = displays.get(display, "modelID")

        if model_ids is None:
            v.add("PASS", f"{label}: {column} {display_id} exists in CreatureDisplayInfo", "CreatureModelData.dbc not given")
        else:
            v.expect(model_id in model_ids, f"{label}: {column} {display_id} and its model {model_id} exist")


def check_masks(v: Validation, label: str, race, result: dict[str, DbcTable], stock_masks: maskrules.FactionMasks, config: Config):
    skills = result["SkillRaceClassInfo"]

    def has_skill(skill_id: int) -> bool | None:
        rows = [r for r in skills.rows if skills.get(r, "skillID") == skill_id]

        if not rows:
            return None

        return any(not skills.get(r, "raceMask") or skills.get(r, "raceMask") & race.bit for r in rows)

    v.expect(any(skills.get(r, "raceMask") & race.bit for r in skills.rows), f"{label}: SkillRaceClassInfo has rows for the race")
    common, orcish = has_skill(LANGUAGE_COMMON), has_skill(LANGUAGE_ORCISH)

    if common is None or orcish is None:
        v.add("SKIP", f"{label}: faction language", "Language: Common / Orcish rows not found")
    elif config.policy.faction_wide_masks:
        expected = (True, False) if race.faction == "alliance" else (False, True)
        v.expect((common, orcish) == expected, f"{label}: speaks {'Common' if race.faction == 'alliance' else 'Orcish'}, not the other faction's language",
                 f"Common {common}, Orcish {orcish}")

    for name, field_name in SMART_MASKS:
        table = result.get(name)

        if table is None:
            continue

        column = table.col(field_name)
        wrong = 0

        for row in table.rows:
            mask = row[column]
            before = mask & ~race.bit
            expected = maskrules.wants_bit(before, race, stock_masks, race.template_race, config.policy.faction_wide_masks) or (mask == 0xFFFFFFFF)

            if bool(mask & race.bit) != expected and mask:
                wrong += 1

        v.expect(wrong == 0, f"{label}: {name}.{field_name} bits follow the mask rule", f"{wrong} masks differ")

    helmets = result.get("HelmetGeosetVisData")

    if helmets is not None:
        columns = helmets.schema.field_columns("hideGeoset")
        mismatched = sum(1 for row in helmets.rows for c in columns if bool(row[c] & (1 << race.id)) != bool(row[c] & (1 << race.template_race)))
        v.expect(mismatched == 0, f"{label}: helmets hide the same geosets as race {race.template_race} (1 << race)", f"{mismatched} masks differ")

    faction = result["Faction"]
    source = race.faction_race if config.policy.reputation_from == "faction_race" else race.template_race
    columns = faction.schema.field_columns("reputationRaceMask")
    mismatched = sum(1 for row in faction.rows for c in columns
                     if row[c] not in (0, 0xFFFFFFFF) and bool(row[c] & race.bit) != bool(row[c] & maskrules.race_bit(source)))
    v.expect(mismatched == 0, f"{label}: starting reputations are those of race {source}", f"{mismatched} masks differ")


def contiguous(table: DbcTable, key_fields: tuple[str, ...]) -> bool:
    columns = [table.col(f) for f in key_fields]
    seen = set()
    previous = None

    for row in table.rows:
        key = tuple(row[c] for c in columns)

        if key != previous:
            if key in seen:
                return False

            seen.add(key)
            previous = key

    return True


def check_no_pandaren_or_monk(v: Validation, result: dict[str, DbcTable]):
    races = result["ChrRaces"]
    pandaren = [to_signed(races.get(r, "id")) for r in races.rows
                if to_signed(races.get(r, "id")) in PANDAREN_RACE_IDS or any("pandaren" in n.lower() for n in races.get_loc(r, "name"))
                or "pandaren" in races.get_str(r, "clientFileString").lower()]
    v.expect(not pandaren, "no Pandaren race in ChrRaces", f"rows {pandaren}")

    monk_rows = []

    for name, column in (("CharBaseInfo", "classID"), ("CharStartOutfit", "classID")):
        table = result[name]
        monk_rows += [name for r in table.rows if table.get(r, column) == MONK_CLASS_ID]

    if "ChrClasses" in result:
        classes = result["ChrClasses"]
        monk_rows += ["ChrClasses" for r in classes.rows if to_signed(r[0]) == MONK_CLASS_ID or any("monk" in n.lower() for n in classes.get_loc(r, "name"))]

    v.expect(not monk_rows, "no Monk class anywhere (class 10)", ", ".join(sorted(set(monk_rows))))


def check_mpq(v: Validation, mpq_path: str, out_dir: str, written: list[str]):
    try:
        import mpqpack
    except ImportError:
        v.add("SKIP", "MPQ check", "mpqpack not found")
        return

    archive = mpqpack.MpqArchive(mpq_path)
    report = archive.verify()
    v.expect(not report.problems, f"{os.path.basename(mpq_path)}: passes the client reader's checks", "; ".join(report.problems))
    v.expect(report.lookup_mode.startswith("listfile"), f"{os.path.basename(mpq_path)}: the client will use the listfile lookup", report.lookup_mode)

    for name in written:
        base = os.path.basename(schema_access.get(name).filename.replace("\\", "/"))

        with open(os.path.join(out_dir, "client", "DBFilesClient", base), "rb") as f:
            expected = f.read()

        archive_name = "DBFilesClient\\" + base

        try:
            same = archive.read(archive_name) == expected
        except mpqpack.MpqError:
            same = False

        v.expect(same, f"{os.path.basename(mpq_path)}: {archive_name} matches the written DBC")
