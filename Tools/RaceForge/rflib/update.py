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

Running it again on the realm's updated patches changes nothing. The server side is one SQL file: the spell_dbc rows,
the skillraceclassinfo_dbc / skilllineability_dbc rows without the bits (they override data/dbc by id, so data/dbc
can stay as it is), and the playercreateinfo rows; see racials_sql().
"""

from __future__ import annotations

import functools
import os
import shutil
import sys
import textwrap
from dataclasses import dataclass, field

from . import schema_access
from . import spells as spellmod
from .config import Config
from .dbc import DbcError, DbcTable, to_signed
from .forge import find_dbc, is_dropped_row, spell_reference_problems

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAPFORGE_DIR = os.path.join(TOOLS_DIR, "MapForge")

SKILL_TABLES = ("SkillRaceClassInfo", "SkillLineAbility")
SKILL_LINE_COLUMNS = {"SkillRaceClassInfo": "skillID", "SkillLineAbility": "skillLine"}
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
            cleared = []

            for row in table.rows:
                if is_dropped_row(name, table, row, race) and row[column] & race.bit and row[column] != 0xFFFFFFFF:
                    row[column] &= ~race.bit
                    cleared.append(to_signed(row[0]))

            changed += cleared

            if race.drop_skill_lines:
                notes.append(f"race {race.id}: bit 0x{race.bit:X} cleared on {len(cleared)} rows of skill lines {race.drop_skill_lines}"
                             + (f" (ids {', '.join(map(str, cleared))})" if cleared else " (already clear)"))

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

    races = plan.checks.get("ChrRaces")

    if races is None:
        raise UpdateError("ChrRaces.dbc is in no patch and not in --dbc")

    missing = [r.id for r in config.races if r.id not in races.ids()]

    if missing:
        raise UpdateError(f"the realm's ChrRaces.dbc has no race {missing}: install the races first (raceforge.py build), then update")

    for name in changed_tables(config):
        by_winner: dict[str | None, list[str]] = {}
        winners = {}

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

        plan.sources[name] = sources

        for source in sources:
            if not source.changed:
                continue

            target = source.archive or plan.own
            files = plan.targets.setdefault(target, {})

            if archive_file(name) in files and files[archive_file(name)] != source.data:
                raise UpdateError(f"{target} would need two different copies of {archive_file(name)}")

            files[archive_file(name)] = source.data

    return plan


def copy_problems(name: str, table: DbcTable, config: Config) -> list[str]:
    """What is still missing from one copy of a changed table: a dropped skill line row with a new race's bit, or a
    racial spell row that is not the one races.json describes."""
    problems = []

    if name in SKILL_TABLES:
        column = table.col("raceMask")

        for race in config.races:
            rows = [to_signed(r[0]) for r in table.rows if is_dropped_row(name, table, r, race) and r[column] & race.bit and r[column] != 0xFFFFFFFF]

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
    """Rebuild every target archive into out/client: (archive name, path, replaced or added files)."""
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

        out_path = os.path.join(client_dir, target)
        source = patchset.find(target)

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
    """A long statement broken after commas (continuation lines indented by 4). Only for statements that no INSERT
    follows: bleakserv's linter wants the line just before an INSERT to hold its DELETE."""
    if len(text) <= width:
        return text

    lines, line = [], ""

    for piece in text.split(", "):
        piece = piece + ", "

        if line.strip() and len(line) + len(piece.rstrip()) > width:
            lines.append(line.rstrip())
            line = "    "

        line += piece

    lines.append(line[:-2] if line.endswith(", ") else line)
    return "\n".join(lines)


def racials_sql(config: Config, plan: UpdatePlan) -> str:
    """The world-database side of the update: what bleakserv's pending_db_world file holds."""
    names = " and ".join(r.name for r in config.races)
    header = (f"Bleakhold racials (world database), written by RaceForge (raceforge.py update) from races.json. {names}: the "
              "template races' racial skill lines go and the races' own racial spells come. The spell_dbc rows are the same rows "
              "as the client's Spell.dbc; the skillraceclassinfo_dbc and skilllineability_dbc rows are the realm's own rows "
              "without the new races' bits, and override data/dbc by id. Every block deletes what it adds first, so the file can "
              "be run again.")
    out = ["-- " + line for line in textwrap.wrap(header, 117)]
    spells = plan.server.get("Spell")
    spell_ids = config.server_sql_spell_ids()

    if spells is not None and spell_ids:
        by_id = spells.by_id()
        out += ["", "-- Spells (" + ", ".join(f"{i} {config.spells[i].name}" for i in spell_ids) + ")"]
        out.append(spellmod.spell_sql(spells, [by_id[i] for i in spell_ids]))

    skills = sorted({s for race in config.races for s in race.drop_skill_lines})

    for name, sql_table, columns in (("SkillRaceClassInfo", "skillraceclassinfo_dbc", spellmod.SERVER_SKILL_RACE_CLASS_COLUMNS),
                                     ("SkillLineAbility", "skilllineability_dbc", spellmod.SERVER_SKILL_LINE_ABILITY_COLUMNS)):
        table = plan.server.get(name)

        if table is None:
            continue

        for skill in skills:
            rows = sorted((r for r in table.rows if table.get(r, SKILL_LINE_COLUMNS[name]) == skill), key=lambda r: to_signed(r[0]))

            if not rows:
                continue

            out += ["", f"-- {name}: every row of the template racial skill line {skill}, without the new races' bits"]
            out.append(f"DELETE FROM `{sql_table}` WHERE {ids_clause('ID', [to_signed(r[0]) for r in rows])};")
            out.append(spellmod.insert_sql(sql_table, spellmod.server_columns(columns),
                                           [spellmod.sql_values(table, r, spellmod.server_columns(columns)) for r in rows]))

    abilities = plan.server.get("SkillLineAbility") or plan.checks.get("SkillLineAbility")

    for race in config.races:
        r, bit, t = race.id, race.bit, race.template_race
        dropped = sorted({abilities.get(row, "spell") for row in abilities.rows if is_dropped_row("SkillLineAbility", abilities, row, race)}) if abilities else []
        action = config.action_bar_spell(race)
        out += ["", f"-- {race.name} ({r}): " + (f"no template racial skill lines {race.drop_skill_lines}" if race.drop_skill_lines else "template racials kept")
                + (f"; racials " + ", ".join(f"{s} {config.spells[s].name}" for s in race.racial_spells) if race.racial_spells else "")]

        if race.drop_skill_lines:
            out.append(f"DELETE FROM `playercreateinfo_skills` WHERE `raceMask` = {bit} AND {in_clause('skill', race.drop_skill_lines)};")

        if dropped:
            spell_list = ", ".join(map(str, dropped))
            out.append(wrap_sql(f"DELETE FROM `playercreateinfo_spell_custom` WHERE `racemask` = {bit} AND `Spell` IN ({spell_list});"))
            out.append(wrap_sql(f"DELETE FROM `playercreateinfo_cast_spell` WHERE `raceMask` = {bit} AND `spell` IN ({spell_list});"))
            out.append("-- The start action bars: the template's racial buttons " + (f"take {action} {config.spells[action].name}" if action else "go"))
            out.append(wrap_sql(f"DELETE FROM `playercreateinfo_action` WHERE `race` = {r} AND `type` = 0 AND `action` IN ({spell_list});"))

            if action:
                out.append(f"DELETE FROM `playercreateinfo_action` WHERE `race` = {r} AND `type` = 0 AND `action` = {action};")
                out.append("INSERT INTO `playercreateinfo_action` (`race`, `class`, `button`, `action`, `type`)")
                out.append(f"SELECT {r}, `class`, `button`, {action}, 0 FROM `playercreateinfo_action`")
                out.append(f"WHERE `race` = {t} AND `type` = 0 AND `class` IN (SELECT `class` FROM `playercreateinfo` WHERE `race` = {r})")
                out.append(wrap_sql(f"AND `action` IN ({spell_list});"))

        if race.racial_spells:
            out.append(f"DELETE FROM `playercreateinfo_spell_custom` WHERE `racemask` = {bit} AND {in_clause('Spell', race.racial_spells)};")
            out.append("INSERT INTO `playercreateinfo_spell_custom` (`racemask`, `classmask`, `Spell`, `Note`) VALUES")
            out.append(",\n".join(f"({bit}, 0, {s}, '{(race.name + ' - ' + config.spells[s].name).replace(chr(39), chr(39) * 2)}')"
                                  for s in race.racial_spells) + ";")

    return "\n".join(out) + "\n"


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
