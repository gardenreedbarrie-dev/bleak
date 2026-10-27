"""raceforge.py update: give a realm that already runs the races the racials of races.json.

`build` starts from stock DBCs and refuses tables that already hold the new races. A live realm has them in its
patches, often merged with other changes (custom spells, models), so the racials go in the way Tools/MapForge puts a
map's rows in: for every table that changes, and for every combination of the launcher's optional packs, the copy the
client reads today is found (the archive that sorts last among those holding it, Tools/MapForge/dbc/patches.py), the
change is forged into that copy, and that archive is rebuilt with every other file kept. Players with and without a
pack each keep the copy they load today, plus the change. A combination where no patch holds the table gets the
stock copy (from --dbc) with the change, in RaceForge's own archive (archives.own, patch-R.MPQ, in whatever case the
realm spells it); that is refused when archives.own would load over a pack archive's copy of the table, which the
players with that pack would then lose, or is itself in a pack, which the players without it would not load.

The changes:
- SkillRaceClassInfo, SkillLineAbility: the new race's bit is cleared on every row of a template racial skill line it
  drops (racials.drop_template_skill_lines);
- Spell: the rows of races.json's spells (the racials and the server-cast spells) are added, or replaced when the same
  id holds an earlier version of the same spell (same name). An id that holds any other spell stops the update.

The races are the realm's: each race of races.json at its realm_id (Config.for_realm(); the Bleakhold realm's own race
patch put High Elf and Eredar in the stock slots 15 and 19), and the realm's ChrRaces.dbc must hold it there, under
its client_file_string, for every pack combination; otherwise nothing is done.

Running it again on the realm's updated patches changes nothing. The server side is one SQL file, written from the
realm's own rows, never stock ones: the spell_dbc rows, the skillraceclassinfo_dbc / skilllineability_dbc rows of the
dropped skill lines as the client reads them without the races' bits (they override data/dbc by id, so data/dbc can
stay as it is; rows only the server's data/dbc has are overridden too), the races' bits cleared on any other
override row of those lines, the playercreateinfo rows, and the rows an earlier update wrote for races.json's build
ids when the realm has the races elsewhere; see racials_sql(). It can go straight into the server's generated-SQL
folder as a new rev file (write_rev()).
"""

from __future__ import annotations

import contextlib
import errno
import functools
import os
import re
import shutil
import sys
import textwrap
import time
from dataclasses import dataclass, field

from . import schema_access
from . import spells as spellmod
from .config import Config
from .dbc import DbcError, DbcTable, to_signed
from .forge import dropped_spells, find_dbc, is_dropped_row, spell_reference_problems

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAPFORGE_DIR = os.path.join(TOOLS_DIR, "MapForge")

SKILL_TABLES = ("SkillRaceClassInfo", "SkillLineAbility")
# The race mask of a row that only a race which drops its skill line had: the bit of race 32, which no race has (ids
# end at 31). Clearing the bit would leave 0, which SkillRaceClassInfo and SkillLineAbility read as every race.
NO_RACE_MASK = 0x80000000
SKILL_LINE_COLUMNS = {"SkillRaceClassInfo": "skillID", "SkillLineAbility": "skillLine"}
# The same columns in the world database's override tables.
SKILL_SQL = {"SkillRaceClassInfo": ("skillraceclassinfo_dbc", "SkillID"), "SkillLineAbility": ("skilllineability_dbc", "SkillLine")}
CHECK_TABLES = ("ChrRaces", "SpellIcon", "SpellVisual", "SpellDuration", "SpellRange", "SpellCastTimes")
SQL_FILE = "bleakhold_racials.sql"


class UpdateError(Exception):
    pass


def patch_tools():
    """Tools/MapForge/dbc/patches.py: the client's archive order and the archive rebuild."""
    if MAPFORGE_DIR not in sys.path:
        sys.path.append(MAPFORGE_DIR)

    from dbc import patches  # noqa: E402  (Tools/MapForge)

    return patches


def archive_file(name: str) -> str:
    return "DBFilesClient\\" + os.path.basename(schema_access.get(name).filename.replace("\\", "/"))


def changed_tables(config: Config) -> list[str]:
    tables = []

    if any(r.drop_skill_lines for r in config.races):
        tables += list(SKILL_TABLES)

    if config.spell_ids():
        tables.append("Spell")

    return tables


@dataclass
class Source:
    """One copy of a table that some players read: the winning archive's (archive) or the stock one (archive None)."""
    table: str
    archive: str | None
    labels: list[str]
    original: bytes
    forged: DbcTable
    notes: list[str] = field(default_factory=list)
    changed_ids: list[int] = field(default_factory=list)

    @functools.cached_property
    def data(self) -> bytes:
        """The forged copy as a file (the table is not changed after forge_copy)."""
        return self.forged.to_bytes()

    @property
    def changed(self) -> bool:
        return self.data != self.original

    def where(self) -> str:
        return self.archive or "no patch (the stock copy)"


def row_differences(table: DbcTable, row: list[int], other_table: DbcTable, other: list[int]) -> list[str]:
    out = []

    for i, column in enumerate(table.schema.columns):
        a = table.string_at(row[i]) if column.is_string else row[i]
        b = other_table.string_at(other[i]) if column.is_string else other[i]

        if a != b:
            out.append(column.name)

    return out


def forge_copy(name: str, table: DbcTable, config: Config) -> tuple[list[str], list[int]]:
    """Apply the racials to one copy of a table in place. Returns (notes, ids of the rows that changed)."""
    notes, changed = [], []

    if name in SKILL_TABLES:
        column = table.col("raceMask")

        for race in config.races:
            cleared, alone = [], []

            for row in table.rows:
                if has_dropped_bit(name, table, row, race):
                    # a mask of 0 would mean every race: a row of this race alone becomes a row of no race
                    if row[column] & 0xFFFFFFFF == race.bit:
                        row[column] = NO_RACE_MASK
                        alone.append(to_signed(row[0]))
                    else:
                        row[column] &= ~race.bit

                    cleared.append(to_signed(row[0]))

            changed += cleared

            if race.drop_skill_lines:
                notes.append(f"race {race.id}: bit 0x{race.bit:X} cleared on {len(cleared)} rows of skill lines {race.drop_skill_lines}"
                             + (f" (ids {', '.join(map(str, cleared))})" if cleared else " (already clear)")
                             + (f"; rows {', '.join(map(str, alone))} were the race's alone: mask 0x{NO_RACE_MASK:X}, no race" if alone else ""))

    elif name == "Spell":
        by_id = table.by_id()

        for spell_id in config.spell_ids():
            spell = config.spells[spell_id]
            scratch = DbcTable.empty(table.schema)
            expected = spellmod.build_row(scratch, spell)
            existing = by_id.get(spell_id)

            if existing is None:
                table.rows.append(spellmod.build_row(table, spell))
                notes.append(f"spell {spell_id} {spell.name}: added")
                changed.append(spell_id)
                continue

            differences = row_differences(table, existing, scratch, expected)

            if not differences:
                notes.append(f"spell {spell_id} {spell.name}: already there")
                continue

            current_name = table.get_str(existing, "name[0]")

            if current_name != spell.name:
                raise UpdateError(f"spell {spell_id} is taken by '{current_name}' in this copy of Spell.dbc; give {spell.name} a free id in "
                                  "races.json (and in the server's racial table)")

            existing[:] = spellmod.build_row(table, spell)
            notes.append(f"spell {spell_id} {spell.name}: updated ({', '.join(differences[:6])}{', ...' if len(differences) > 6 else ''})")
            changed.append(spell_id)

    return notes, changed


@dataclass
class UpdatePlan:
    sources: dict[str, list[Source]] = field(default_factory=dict)
    targets: dict[str, dict[str, bytes]] = field(default_factory=dict)  # archive name -> {archive file: bytes}
    server: dict[str, DbcTable] = field(default_factory=dict)  # table -> the copy for data/dbc (all packs on)
    checks: dict[str, DbcTable] = field(default_factory=dict)  # read-only tables for the checks
    notes: list[str] = field(default_factory=list)
    configurations: list[str] = field(default_factory=list)
    own: str = ""  # archives.own as the realm's patch folder spells it (the target of the stock copies)
    # SkillRaceClassInfo / SkillLineAbility of --dbc (the server's data/dbc), forged, when the server rows come from a
    # patch: (table, ids of its rows that give a race a dropped skill line and that the client's copy lacks)
    server_dbc: dict[str, tuple[DbcTable, list[int]]] = field(default_factory=dict)


def read_table(name: str, patchset, stock_dir: str, packs_on) -> tuple[DbcTable | None, str]:
    """The copy of a table the client reads with packs_on: (table, where it came from)."""
    schema = schema_access.get(name)
    top = patchset.top(archive_file(name), packs_on)

    if top is not None:
        return DbcTable.from_bytes(top.read(archive_file(name)), schema, f"{top.name}: {name}"), top.name

    path = find_dbc(stock_dir, name)

    if path is None:
        return None, ""

    return DbcTable.read(path, schema), "stock"


def make_plan(config: Config, patchset, stock_dir: str) -> UpdatePlan:
    plan = UpdatePlan()
    configurations = patchset.configurations()
    plan.configurations = [label for label, _ in configurations]
    all_on = configurations[0][1]
    # The client and PatchSet.find match archive names in any case: an existing Patch-R.MPQ is archives.own.
    own = patchset.find(config.archives.own)
    plan.own = own.name if own is not None else config.archives.own
    own_path = own.client_path if own is not None else "Data\\" + config.archives.own
    own_pack = patch_tools().pack_of(own_path, patchset.packs)

    for name in CHECK_TABLES:
        table, where = read_table(name, patchset, stock_dir, all_on)

        if table is not None:
            plan.checks[name] = table
            plan.notes.append(f"{name}.dbc (checks): from {where}")

    # The races must be where config says, for every player: a slot that holds another race would get these racials.
    copies: dict[str, tuple[DbcTable, list[str]]] = {}

    for label, packs_on in configurations:
        table, where = read_table("ChrRaces", patchset, stock_dir, packs_on)

        if table is None:
            raise UpdateError("ChrRaces.dbc is in no patch and not in --dbc")

        copies.setdefault(where, (table, []))[1].append(label)

    problems = []

    for where, (table, labels) in copies.items():
        source = f"{'--dbc' if where == 'stock' else where}, for {', '.join(labels)}"
        found = race_problems(config, table, source)
        problems += found

        if not found:
            plan.notes.append(f"ChrRaces.dbc ({source}): " + ", ".join(f"race {r.id} is {r.client_file_string}" for r in config.races))

    if problems:
        raise UpdateError("; ".join(problems))

    for name in changed_tables(config):
        by_winner: dict[str | None, list[str]] = {}
        winners = {}
        server_source = None

        for label, packs_on in configurations:
            top = patchset.top(archive_file(name), packs_on)
            by_winner.setdefault(top.name if top else None, []).append(label)

            if top is not None:
                winners[top.name] = top

        if None in by_winner:
            # Only pack archives hold the file (a holder every player loads would win everywhere). The stock copy
            # goes into archives.own, which every player must load: over a pack archive's copy it would hide that copy.
            if own_pack is not None:
                raise UpdateError(f"no patch holds {archive_file(name)} for {', '.join(by_winner[None])}, so its stock copy with the "
                                  f"change would go into {plan.own} (archives.own), which is in the optional pack {own_pack}: the "
                                  "players without that pack would not load it. Set archives.own to a patch outside every pack")

            hidden = sorted(w for w, archive in winners.items()
                            if w.lower() != plan.own.lower() and patch_tools().outranks(own_path, [archive]))

            if hidden:
                raise UpdateError(f"no patch holds {archive_file(name)} for {', '.join(by_winner[None])}, so its stock copy with the "
                                  f"change would go into {plan.own} (archives.own), which loads over {', '.join(hidden)}: the "
                                  f"players with that pack would lose its copy. Add {archive_file(name)} to a patch every player "
                                  f"loads, or set archives.own to a patch outside every pack that sorts below {', '.join(hidden)}, "
                                  "then run update again")

        sources = []

        for winner, labels in by_winner.items():
            if winner is None:
                path = find_dbc(stock_dir, name)

                if path is None:
                    raise UpdateError(f"no patch holds {archive_file(name)} for {', '.join(labels)}, and --dbc has no {name}.dbc to start from")

                with open(path, "rb") as f:
                    original = f.read()
            else:
                original = patchset.find(winner).read(archive_file(name))

            try:
                table = DbcTable.from_bytes(original, schema_access.get(name), f"{winner or 'stock'}: {name}")
            except DbcError as e:
                raise UpdateError(str(e)) from None

            notes, changed = forge_copy(name, table, config)
            source = Source(name, winner, labels, original, table, notes, changed)
            sources.append(source)

            if configurations[0][0] in labels:
                plan.server[name] = table
                server_source = source

        plan.sources[name] = sources

        if name in SKILL_TABLES and server_source is not None and server_source.archive is not None:
            add_server_dbc(plan, name, stock_dir, config, server_source)

        for source in sources:
            if not source.changed:
                continue

            target = source.archive or plan.own
            files = plan.targets.setdefault(target, {})

            if archive_file(name) in files and files[archive_file(name)] != source.data:
                raise UpdateError(f"{target} would need two different copies of {archive_file(name)}")

            files[archive_file(name)] = source.data

    return plan


def race_problems(config: Config, races: DbcTable, where: str) -> list[str]:
    """Each race must be the ChrRaces row of its id, under its client_file_string (which names its portraits, corpse
    skeletons and Lua race token): what is wrong, with where the race is instead."""
    file_strings = {to_signed(r[0]): races.get_str(r, "clientFileString") for r in races.rows}
    problems = []

    for race in config.races:
        actual = file_strings.get(race.id)

        if actual is not None and actual.lower() == race.client_file_string.lower():
            continue

        elsewhere = sorted(i for i, text in file_strings.items() if text.lower() == race.client_file_string.lower())
        what = f"has no race {race.id}" if actual is None else f"has {actual or '(no file string)'} as race {race.id}, not {race.client_file_string}"

        if elsewhere:
            hint = (f"{race.client_file_string} is race {elsewhere[0]} there: set realm_id {elsewhere[0]} for {race.name} in races.json "
                    "(and the realm's race settings of mod-bleakhold and mod-bleakhold-ui), then run update again")
        else:
            hint = "install the races first (raceforge.py build, or the realm's own race patch), then update"

        problems.append(f"{race.name}: the realm's ChrRaces.dbc ({where}) {what}; {hint}")

    return problems


def add_server_dbc(plan: UpdatePlan, name: str, stock_dir: str, config: Config, server_source: Source):
    """The server reads data/dbc and then the override rows. Where the client's copy of a skill table is a patch's,
    --dbc (the server's data/dbc) may have rows of a dropped skill line that copy lacks, still with a race's bit: the
    SQL overrides those too."""
    path = find_dbc(stock_dir, name)

    if path is None:
        return

    try:
        table = DbcTable.read(path, schema_access.get(name))
    except DbcError as e:
        raise UpdateError(str(e)) from None

    _, changed = forge_copy(name, table, config)
    client_ids = plan.server[name].ids()
    extra = sorted(i for i in changed if i not in client_ids)
    plan.server_dbc[name] = (table, extra)

    if extra:
        plan.notes.append(f"{name}.dbc of --dbc (the server's data/dbc): rows {extra} give a race a dropped skill line and are not in "
                          f"{server_source.where()}'s copy; the SQL overrides them too")


def server_rows(plan: UpdatePlan, name: str) -> dict[int, tuple[DbcTable, list[int]]]:
    """id -> (table, row) of every row the server SQL writes for a table, as racials_sql() picks them: the client's
    copy (all packs on) and the --dbc rows only the server has."""
    out = {}
    extra_table, extra_ids = plan.server_dbc.get(name, (None, []))

    if extra_table is not None:
        by_id = extra_table.by_id()
        out.update({i: (extra_table, by_id[i]) for i in extra_ids})

    table = plan.server.get(name)

    if table is not None:
        out.update({row_id: (table, row) for row_id, row in table.by_id().items()})

    return out


def has_dropped_bit(name: str, table: DbcTable, row: list[int], race) -> bool:
    """A SkillRaceClassInfo / SkillLineAbility row of a skill line the race drops that still has the race's bit (a mask
    of every race, 0xFFFFFFFF, is left as it is)."""
    mask = table.get(row, "raceMask") & 0xFFFFFFFF
    return is_dropped_row(name, table, row, race) and bool(mask & race.bit) and mask != 0xFFFFFFFF


def copy_problems(name: str, table: DbcTable, config: Config) -> list[str]:
    """What is still missing from one copy of a changed table: a dropped skill line row with a new race's bit, or a
    racial spell row that is not the one races.json describes."""
    problems = []

    if name in SKILL_TABLES:
        for race in config.races:
            rows = [to_signed(r[0]) for r in table.rows if has_dropped_bit(name, table, r, race)]

            if rows:
                problems.append(f"race {race.id} still has its bit on rows {rows[:5]}")
    elif name == "Spell":
        by_id = table.by_id()

        for spell_id in config.spell_ids():
            scratch = DbcTable.empty(table.schema)
            expected = spellmod.build_row(scratch, config.spells[spell_id])
            row = by_id.get(spell_id)

            if row is None:
                problems.append(f"spell {spell_id} is missing")
            elif row_differences(table, row, scratch, expected):
                problems.append(f"spell {spell_id} differs in {', '.join(row_differences(table, row, scratch, expected)[:5])}")

    return problems


def check_spells(plan: UpdatePlan, config: Config) -> tuple[list[str], list[str]]:
    """What the racial spells point at, in the copy the server gets: (problems, skipped)."""
    spells = plan.server.get("Spell")

    if spells is None:
        return [], []

    tables = dict(plan.checks)
    tables["Spell"] = spells
    problems, skipped = [], []
    by_id = spells.by_id()

    for spell_id in config.spell_ids():
        p, s = spell_reference_problems(config.spells[spell_id], by_id[spell_id], tables)
        problems += p
        skipped += s

    return problems, skipped


def write_archives(plan: UpdatePlan, patchset, out_dir: str) -> list[tuple[str, str, list[str]]]:
    """Rebuild every target archive into out/client, at its place in the patch folder (client/enUS/ for a locale
    patch): (archive name, path, replaced or added files)."""
    patches = patch_tools()
    import mpqpack  # noqa: E402  (Tools/MpqPack, on sys.path next to RaceForge)

    written = []
    client_dir = os.path.join(out_dir, "client")
    os.makedirs(client_dir, exist_ok=True)

    for target, files in sorted(plan.targets.items()):
        staging = os.path.join(out_dir, "merged", target)
        os.makedirs(os.path.join(staging, "DBFilesClient"), exist_ok=True)
        replacements = {}

        for archive_name, data in files.items():
            path = os.path.join(staging, archive_name.replace("\\", os.sep))

            with open(path, "wb") as f:
                f.write(data)

            replacements[archive_name] = path

        source = patchset.find(target)
        # at its place in the patch folder: a locale patch (Data\enUS\patch-enUS-8.MPQ) goes to client/enUS/
        place = source.client_path.split("\\")[1:] if source is not None else [target]
        out_path = os.path.join(client_dir, *place)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        try:
            if source is not None:
                patches.rebuild(source, replacements, out_path, os.path.join(out_dir, "staging"))
            else:
                mpqpack.write_archive(out_path, [(name, data) for name, data in files.items()])
        except (patches.PatchError, mpqpack.MpqError) as e:
            raise UpdateError(str(e)) from None

        written.append((target, out_path, sorted(files)))

    return written


def ids_clause(column: str, ids: list[int]) -> str:
    """`column` IN (...) for scattered ids, with BETWEEN for runs of 3 or more, joined by OR."""
    ids = sorted(set(ids))
    runs, start = [], 0

    for i in range(1, len(ids) + 1):
        if i == len(ids) or ids[i] != ids[i - 1] + 1:
            runs.append((ids[start], ids[i - 1]))
            start = i

    singles = [n for a, b in runs if b - a < 2 for n in range(a, b + 1)]
    parts = [(a, f"`{column}` BETWEEN {a} AND {b}") for a, b in runs if b - a >= 2]

    if singles:
        parts.append((singles[0], in_clause(column, singles)))

    return " OR ".join(text for _, text in sorted(parts))


def in_clause(column: str, values: list[int]) -> str:
    return f"`{column}` = {values[0]}" if len(values) == 1 else f"`{column}` IN ({', '.join(map(str, values))})"


def wrap_sql(text: str, width: int = 120) -> str:
    """A long statement broken after commas and before WHERE, AND and ELSE (continuation lines indented by 4). Only for
    statements that no INSERT follows: bleakserv's linter wants the line just before an INSERT to hold its DELETE."""
    if len(text) <= width:
        return text

    pieces = [p for p in re.split(r"(?<=, )|(?= WHERE )|(?= AND )|(?= ELSE )", text) if p]
    lines, line = [], ""

    for piece in pieces:
        if line.strip() and len(line.rstrip()) + len(piece.rstrip()) > width:
            lines.append(line.rstrip())
            line = "    " + piece.lstrip()
        else:
            line += piece

    lines.append(line.rstrip())
    return "\n".join(lines)


def comment(text: str) -> list[str]:
    """SQL comment lines of at most 120 columns."""
    return ["-- " + line for line in textwrap.wrap(text, 117)]


# The columns of the playercreateinfo tables whose primary key holds the race mask, the mask first.
KEYED_MASK_TABLES = {
    "playercreateinfo_skills": ("raceMask", "classMask", "skill", "rank", "comment"),
    "playercreateinfo_spell_custom": ("racemask", "classmask", "Spell", "Note"),
}


def mask_clear_sql(table: str, column: str, where: str, bit: int) -> list[str]:
    """Take a race's bit out of the rows `where` picks: a row of that race alone goes, a row of more races keeps the
    others (a mask never becomes 0, which means every race). Where the mask is part of the primary key, REPLACE writes
    the row with its new mask (taking the place of a row that already has it: the same class and skill or spell, which
    then covers the same races) and the DELETE takes the old one out; an UPDATE could hit that key."""
    keep = f"WHERE {where} AND (`{column}` & {bit}) <> 0 AND `{column}` <> {bit};"
    columns = KEYED_MASK_TABLES.get(table)

    if columns:
        names = ", ".join(f"`{c}`" for c in columns)
        values = ", ".join(f"`{c}` - {bit}" if c == column else f"`{c}`" for c in columns)
        lines = [f"REPLACE INTO `{table}` ({names})", f"SELECT {values} FROM `{table}`", wrap_sql(keep)]
    else:
        lines = [wrap_sql(f"UPDATE `{table}` SET `{column}` = `{column}` - {bit} {keep}")]

    return lines + [wrap_sql(f"DELETE FROM `{table}` WHERE {where} AND (`{column}` & {bit}) <> 0;")]


def racials_sql(config: Config, plan: UpdatePlan) -> str:
    """The world-database side of the update, from the realm's own rows: a rev file of the server's generated-SQL
    folder (or of bleakserv's pending_db_world)."""
    names = " and ".join(f"{r.name} (race {r.id})" for r in config.races)
    header = (f"Bleakhold racials (world database), written by RaceForge (raceforge.py update) from races.json and the realm's own "
              f"DBCs. {names}: the template races' racial skill lines go and the races' own racial spells come. The spell_dbc rows "
              "are the same rows as the client's Spell.dbc; the skillraceclassinfo_dbc and skilllineability_dbc rows are the realm's "
              "own rows without the races' bits, and override data/dbc by id. Every block deletes what it adds first, so the file "
              "can be run again.")
    out = comment(header)
    spells = plan.server.get("Spell")
    spell_ids = config.server_sql_spell_ids()

    if spells is not None and spell_ids:
        by_id = spells.by_id()
        out += [""] + comment("Spells (" + ", ".join(f"{i} {config.spells[i].name}" for i in spell_ids) + ")")
        out.append(spellmod.spell_sql(spells, [by_id[i] for i in spell_ids]))

    skills = sorted({s for race in config.races for s in race.drop_skill_lines})

    for name, columns in (("SkillRaceClassInfo", spellmod.SERVER_SKILL_RACE_CLASS_COLUMNS), ("SkillLineAbility", spellmod.SERVER_SKILL_LINE_ABILITY_COLUMNS)):
        if name not in plan.server:
            continue

        sql_table, sql_column = SKILL_SQL[name]
        extra_ids = set(plan.server_dbc.get(name, (None, []))[1])
        rows = server_rows(plan, name)
        columns = spellmod.server_columns(columns)

        for skill in skills:
            ids = sorted(i for i, (table, row) in rows.items() if table.get(row, SKILL_LINE_COLUMNS[name]) == skill)

            if not ids:
                continue

            server_only = [i for i in ids if i in extra_ids]
            out += [""] + comment(f"{name}: every row of the template racial skill line {skill}, without the races' bits"
                                  + (f" (rows {', '.join(map(str, server_only))}: the server's data/dbc only)" if server_only else ""))
            out.append(f"DELETE FROM `{sql_table}` WHERE {ids_clause('ID', ids)};")
            out.append(spellmod.insert_sql(sql_table, columns, [spellmod.sql_values(rows[i][0], rows[i][1], columns) for i in ids]))

        no_race = to_signed(NO_RACE_MASK)
        clears = [wrap_sql(f"UPDATE `{sql_table}` SET `RaceMask` = CASE WHEN `RaceMask` = {race.bit} THEN {no_race} ELSE `RaceMask` - {race.bit} END "
                           f"WHERE {in_clause(sql_column, race.drop_skill_lines)} AND `RaceMask` > 0 AND (`RaceMask` & {race.bit}) <> 0;")
                  for race in config.races if race.drop_skill_lines]

        if clears:
            out += [""] + comment(f"Other {sql_table} rows of those skill lines (earlier overrides in this database): without the races' "
                                  f"bits (a row of the race alone: {no_race}, no race)")
            out += clears

    abilities = [t for t in (plan.server.get("SkillLineAbility") or plan.checks.get("SkillLineAbility"),
                             plan.server_dbc.get("SkillLineAbility", (None, []))[0]) if t is not None]

    for race in config.races:
        r, bit = race.id, race.bit
        dropped = sorted({spell for table in abilities for spell in dropped_spells(table, race)})
        action = config.action_bar_spell(race)
        out += [""] + comment(f"{race.name} (race {r}): " + (f"no template racial skill lines {race.drop_skill_lines}" if race.drop_skill_lines
                                                            else "template racials kept")
                              + (f"; racials " + ", ".join(f"{s} {config.spells[s].name}" for s in race.racial_spells) if race.racial_spells else ""))

        if race.drop_skill_lines or dropped:
            out += comment("playercreateinfo_skills, _spell_custom and _cast_spell: a row of the race alone goes, a row of more races keeps them")

        if race.drop_skill_lines:
            out += mask_clear_sql("playercreateinfo_skills", "raceMask", in_clause("skill", race.drop_skill_lines), bit)

        if dropped:
            out += mask_clear_sql("playercreateinfo_spell_custom", "racemask", in_clause("Spell", dropped), bit)
            out += mask_clear_sql("playercreateinfo_cast_spell", "raceMask", in_clause("spell", dropped), bit)

            if action:
                # the race's own bar, as the realm made it: its template racial buttons, wherever they are, take the spell
                out += comment(f"The start action bars: the race's template racial buttons take {action} {config.spells[action].name}")
                out.append(wrap_sql(f"UPDATE `playercreateinfo_action` SET `action` = {action} WHERE `race` = {r} AND `type` = 0 AND {in_clause('action', dropped)};"))
            else:
                out += comment("The start action bars: the race's template racial buttons go")
                out.append(wrap_sql(f"DELETE FROM `playercreateinfo_action` WHERE `race` = {r} AND `type` = 0 AND {in_clause('action', dropped)};"))

        if race.racial_spells:
            out.append(f"DELETE FROM `playercreateinfo_spell_custom` WHERE `racemask` = {bit} AND {in_clause('Spell', race.racial_spells)};")
            out.append("INSERT INTO `playercreateinfo_spell_custom` (`racemask`, `classmask`, `Spell`, `Note`) VALUES")
            out.append(",\n".join(f"({bit}, 0, {s}, '{(race.name + ' - ' + config.spells[s].name).replace(chr(39), chr(39) * 2)}')"
                                  for s in race.racial_spells) + ";")

    out += leftover_sql(config)
    return "\n".join(out) + "\n"


def leftover_sql(config: Config) -> list[str]:
    """Where the realm has a race at another id than races.json's (realm_id), an earlier update for races.json's id
    gave that id the racials and Read Ley Line's start bar buttons: those rows go, so nothing points at a race the
    realm does not have."""
    realm_ids = {race.id for race in config.races}
    moved = [race for race in config.races if race.build_id and race.build_id != race.id and race.build_id not in realm_ids]
    lines = []

    for race in moved:
        old_bit = 1 << (race.build_id - 1)
        action = config.action_bar_spell(race)

        if race.racial_spells:
            lines.append(f"DELETE FROM `playercreateinfo_spell_custom` WHERE `racemask` = {old_bit} AND {in_clause('Spell', race.racial_spells)};")

        if action:
            lines.append(f"DELETE FROM `playercreateinfo_action` WHERE `race` = {race.build_id} AND `type` = 0 AND `action` = {action};")

    if not lines:
        return []

    olds = ", ".join(f"{race.name} {race.build_id}" for race in moved)
    news = ", ".join(f"{race.id}" for race in moved)
    note = (f"races.json's build ids ({olds}): rows an earlier update wrote for them go. This realm has the races at {news}, and "
            "nothing may point at a race it does not have.")
    return [""] + comment(note) + lines


def write_rev(target: str, text: str) -> tuple[str, bool]:
    """The server SQL as a world-database update file of its own: target is a folder (a new rev_<nanoseconds>.sql goes
    there, as create_sql.sh names them) or a .sql path. Never changes a file that is there (ac-db-import may have applied
    it): a file of other content at the path stops it, and a .sql file of the folder that already holds the same text is
    the one (nothing written). The file is there whole or not at all: update-bleakhold-ui.sh deploys every .sql file of
    the folder, and a cut-off one (disk full, Ctrl-C) would fail ac-db-import halfway. Returns (path, written)."""
    folder, path = (os.path.dirname(os.path.abspath(target)), target) if target.lower().endswith(".sql") else (target, None)

    if path is not None and os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as f:
            if f.read() == text:
                return path, False

        raise UpdateError(f"{path} exists with other content; it is never changed (ac-db-import may have applied it already). "
                          "Give a new rev file name, or the folder (a new rev_<nanoseconds>.sql goes there)")

    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            other = os.path.join(folder, name)

            if name.lower().endswith(".sql") and os.path.isfile(other):
                with open(other, encoding="utf-8", newline="") as f:
                    if f.read() == text:
                        return other, False

    os.makedirs(folder, exist_ok=True)
    named = path is not None

    while not named and (path is None or os.path.exists(path)):
        path = os.path.join(folder, f"rev_{time.time_ns()}.sql")

    # written as a dot file that is no .sql file (neither the deploy's *.sql nor the scan above takes it), then linked
    # to its name once complete, as build-royale.sh's put_rev does; the part file goes on any error, Ctrl-C included
    part = os.path.join(folder, f".{os.path.basename(path)}.part")

    try:
        with open(part, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())

        os.chmod(part, 0o644)

        while True:
            try:
                link_new(part, path)
                break
            except FileExistsError:
                if named:
                    raise UpdateError(f"{path} appeared while the rev file was written; it is never changed. Run it again") from None

                path = os.path.join(folder, f"rev_{time.time_ns()}.sql")
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(part)

    sync_folder(folder)
    return path, True


# os.link's errors on a filesystem without hard links (FAT, some network shares)
NO_HARD_LINKS = {getattr(errno, name) for name in ("EPERM", "EOPNOTSUPP", "ENOTSUP", "EMLINK", "ENOSYS") if hasattr(errno, name)}


def link_new(src: str, dst: str):
    """dst as a new name of the complete file src, never over a file that is there (FileExistsError). Where the
    filesystem has no hard links, src is renamed to dst once dst is checked not to be there."""
    try:
        os.link(src, dst)
    except FileExistsError:
        raise
    except OSError as e:
        if e.errno not in NO_HARD_LINKS:
            raise

        if os.path.lexists(dst):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), dst) from None

        os.replace(src, dst)


def sync_folder(folder: str):
    """The folder's entries on disk (the new name survives a power cut); a filesystem that cannot sync folders is left."""
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError:
        return

    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def compare_sql(generated: str, other: str, tables=("spell_dbc", "skillraceclassinfo_dbc", "skilllineability_dbc")) -> list[str]:
    """Rows of the DBC tables in `generated` that `other` lacks or holds differently (field for field)."""
    problems = []

    for table in tables:
        ours = spellmod.parse_sql_rows(generated, table)
        theirs = spellmod.parse_sql_rows(other, table)

        for row_id, row in sorted(ours.items()):
            if row_id not in theirs:
                problems.append(f"{table} {row_id}: missing")
                continue

            differences = [c for c in row if theirs[row_id].get(c) != row[c]]
            differences += [f"{c} (extra)" for c in theirs[row_id] if c not in row]

            if differences:
                problems.append(f"{table} {row_id}: {', '.join(differences[:6])} differ")

        extra = sorted(set(theirs) - set(ours))

        if extra:
            problems.append(f"{table}: rows {extra} are not RaceForge's")

    return problems


def clean_out_dir(out_dir: str, force: bool):
    entries = [e for e in ("client", "server", "merged", "staging", "report.txt") if os.path.exists(os.path.join(out_dir, e))]

    if entries and not force:
        raise UpdateError(f"{out_dir} already holds output ({', '.join(entries)}); use --force to replace it")

    for entry in entries:
        path = os.path.join(out_dir, entry)

        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)

    os.makedirs(out_dir, exist_ok=True)
