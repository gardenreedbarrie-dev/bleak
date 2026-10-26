"""New Spell.dbc rows (the racial spells of races.json) and the matching AzerothCore world-database rows.

The client and AzerothCore read the same row: the client from DBFilesClient/Spell.dbc (234 columns, SpellRec), the
server from data/dbc and then from the world table spell_dbc, one SQL column per DBC column in client order
(DBCDatabaseLoader: `SELECT * FROM spell_dbc`, SpellEntryfmt). A row is built once, from its SpellDef, and both the
DBC file and the SQL are written from that one row; parse_sql_rows() reads the SQL back so the checks can compare the
two field for field.
"""

from __future__ import annotations

import os
import re
import struct

from .config import LOCALES, SPELL_TEXT_FIELDS, SpellDef
from .dbc import DbcError, DbcTable, to_signed

# Every new row starts from these, as Blizzard's rows do: a proc chance of 101 (always), no required item class (-1)
# and chain amplitudes of 1.0.
DEFAULTS = {
    "procChance": 101,
    "equippedItemClass": -1,
    "effectChainAmplitude[0]": 1.0,
    "effectChainAmplitude[1]": 1.0,
    "effectChainAmplitude[2]": 1.0,
}

# The localized-string flags column of every stock 3.3.5a Spell.dbc row: 0xFF01FE with text, 0xFF01FC without.
LOC_FLAGS_TEXT = 0xFF01FE
LOC_FLAGS_EMPTY = 0xFF01FC

SPELL_ATTR0_PASSIVE = 0x40

# Columns RaceForge fills itself from the SpellDef.
MANAGED = {"id", "spellIconID", "spellVisualID[0]"}

# AzerothCore's world table spell_dbc (data/sql/base/db_world/spell_dbc.sql), in client column order, with the SQL
# type: i int, u int unsigned, I bigint, U bigint unsigned, f float, s text. tests/test_racials.py checks this
# against a bleakserv checkout next to this repository.
SERVER_SPELL_COLUMNS = (
    ("ID", "i"), ("Category", "u"), ("DispelType", "u"), ("Mechanic", "u"), ("Attributes", "u"),
    ("AttributesEx", "u"), ("AttributesEx2", "u"), ("AttributesEx3", "u"), ("AttributesEx4", "u"),
    ("AttributesEx5", "u"), ("AttributesEx6", "u"), ("AttributesEx7", "u"), ("ShapeshiftMask", "U"),
    ("unk_320_2", "i"), ("ShapeshiftExclude", "U"), ("unk_320_3", "i"), ("Targets", "u"),
    ("TargetCreatureType", "u"), ("RequiresSpellFocus", "u"), ("FacingCasterFlags", "u"), ("CasterAuraState", "u"),
    ("TargetAuraState", "u"), ("ExcludeCasterAuraState", "u"), ("ExcludeTargetAuraState", "u"),
    ("CasterAuraSpell", "u"), ("TargetAuraSpell", "u"), ("ExcludeCasterAuraSpell", "u"),
    ("ExcludeTargetAuraSpell", "u"), ("CastingTimeIndex", "u"), ("RecoveryTime", "u"), ("CategoryRecoveryTime", "u"),
    ("InterruptFlags", "u"), ("AuraInterruptFlags", "u"), ("ChannelInterruptFlags", "u"), ("ProcTypeMask", "u"),
    ("ProcChance", "u"), ("ProcCharges", "u"), ("MaxLevel", "u"), ("BaseLevel", "u"), ("SpellLevel", "u"),
    ("DurationIndex", "u"), ("PowerType", "i"), ("ManaCost", "u"), ("ManaCostPerLevel", "u"), ("ManaPerSecond", "u"),
    ("ManaPerSecondPerLevel", "u"), ("RangeIndex", "u"), ("Speed", "f"), ("ModalNextSpell", "u"),
    ("CumulativeAura", "u"), ("Totem_1", "u"), ("Totem_2", "u"), ("Reagent_1", "i"), ("Reagent_2", "i"),
    ("Reagent_3", "i"), ("Reagent_4", "i"), ("Reagent_5", "i"), ("Reagent_6", "i"), ("Reagent_7", "i"),
    ("Reagent_8", "i"), ("ReagentCount_1", "i"), ("ReagentCount_2", "i"), ("ReagentCount_3", "i"),
    ("ReagentCount_4", "i"), ("ReagentCount_5", "i"), ("ReagentCount_6", "i"), ("ReagentCount_7", "i"),
    ("ReagentCount_8", "i"), ("EquippedItemClass", "i"), ("EquippedItemSubclass", "i"),
    ("EquippedItemInvTypes", "i"), ("Effect_1", "u"), ("Effect_2", "u"), ("Effect_3", "u"),
    ("EffectDieSides_1", "i"), ("EffectDieSides_2", "i"), ("EffectDieSides_3", "i"),
    ("EffectRealPointsPerLevel_1", "f"), ("EffectRealPointsPerLevel_2", "f"), ("EffectRealPointsPerLevel_3", "f"),
    ("EffectBasePoints_1", "i"), ("EffectBasePoints_2", "i"), ("EffectBasePoints_3", "i"), ("EffectMechanic_1", "u"),
    ("EffectMechanic_2", "u"), ("EffectMechanic_3", "u"), ("ImplicitTargetA_1", "u"), ("ImplicitTargetA_2", "u"),
    ("ImplicitTargetA_3", "u"), ("ImplicitTargetB_1", "u"), ("ImplicitTargetB_2", "u"), ("ImplicitTargetB_3", "u"),
    ("EffectRadiusIndex_1", "u"), ("EffectRadiusIndex_2", "u"), ("EffectRadiusIndex_3", "u"), ("EffectAura_1", "u"),
    ("EffectAura_2", "u"), ("EffectAura_3", "u"), ("EffectAuraPeriod_1", "u"), ("EffectAuraPeriod_2", "u"),
    ("EffectAuraPeriod_3", "u"), ("EffectMultipleValue_1", "f"), ("EffectMultipleValue_2", "f"),
    ("EffectMultipleValue_3", "f"), ("EffectChainTargets_1", "u"), ("EffectChainTargets_2", "u"),
    ("EffectChainTargets_3", "u"), ("EffectItemType_1", "u"), ("EffectItemType_2", "u"), ("EffectItemType_3", "u"),
    ("EffectMiscValue_1", "i"), ("EffectMiscValue_2", "i"), ("EffectMiscValue_3", "i"), ("EffectMiscValueB_1", "i"),
    ("EffectMiscValueB_2", "i"), ("EffectMiscValueB_3", "i"), ("EffectTriggerSpell_1", "u"),
    ("EffectTriggerSpell_2", "u"), ("EffectTriggerSpell_3", "u"), ("EffectPointsPerCombo_1", "f"),
    ("EffectPointsPerCombo_2", "f"), ("EffectPointsPerCombo_3", "f"), ("EffectSpellClassMaskA_1", "u"),
    ("EffectSpellClassMaskA_2", "u"), ("EffectSpellClassMaskA_3", "u"), ("EffectSpellClassMaskB_1", "u"),
    ("EffectSpellClassMaskB_2", "u"), ("EffectSpellClassMaskB_3", "u"), ("EffectSpellClassMaskC_1", "u"),
    ("EffectSpellClassMaskC_2", "u"), ("EffectSpellClassMaskC_3", "u"), ("SpellVisualID_1", "u"),
    ("SpellVisualID_2", "u"), ("SpellIconID", "u"), ("ActiveIconID", "u"), ("SpellPriority", "u"),
    ("Name_Lang_enUS", "s"), ("Name_Lang_enGB", "s"), ("Name_Lang_koKR", "s"), ("Name_Lang_frFR", "s"),
    ("Name_Lang_deDE", "s"), ("Name_Lang_enCN", "s"), ("Name_Lang_zhCN", "s"), ("Name_Lang_enTW", "s"),
    ("Name_Lang_zhTW", "s"), ("Name_Lang_esES", "s"), ("Name_Lang_esMX", "s"), ("Name_Lang_ruRU", "s"),
    ("Name_Lang_ptPT", "s"), ("Name_Lang_ptBR", "s"), ("Name_Lang_itIT", "s"), ("Name_Lang_Unk", "s"),
    ("Name_Lang_Mask", "u"), ("NameSubtext_Lang_enUS", "s"), ("NameSubtext_Lang_enGB", "s"),
    ("NameSubtext_Lang_koKR", "s"), ("NameSubtext_Lang_frFR", "s"), ("NameSubtext_Lang_deDE", "s"),
    ("NameSubtext_Lang_enCN", "s"), ("NameSubtext_Lang_zhCN", "s"), ("NameSubtext_Lang_enTW", "s"),
    ("NameSubtext_Lang_zhTW", "s"), ("NameSubtext_Lang_esES", "s"), ("NameSubtext_Lang_esMX", "s"),
    ("NameSubtext_Lang_ruRU", "s"), ("NameSubtext_Lang_ptPT", "s"), ("NameSubtext_Lang_ptBR", "s"),
    ("NameSubtext_Lang_itIT", "s"), ("NameSubtext_Lang_Unk", "s"), ("NameSubtext_Lang_Mask", "u"),
    ("Description_Lang_enUS", "s"), ("Description_Lang_enGB", "s"), ("Description_Lang_koKR", "s"),
    ("Description_Lang_frFR", "s"), ("Description_Lang_deDE", "s"), ("Description_Lang_enCN", "s"),
    ("Description_Lang_zhCN", "s"), ("Description_Lang_enTW", "s"), ("Description_Lang_zhTW", "s"),
    ("Description_Lang_esES", "s"), ("Description_Lang_esMX", "s"), ("Description_Lang_ruRU", "s"),
    ("Description_Lang_ptPT", "s"), ("Description_Lang_ptBR", "s"), ("Description_Lang_itIT", "s"),
    ("Description_Lang_Unk", "s"), ("Description_Lang_Mask", "u"), ("AuraDescription_Lang_enUS", "s"),
    ("AuraDescription_Lang_enGB", "s"), ("AuraDescription_Lang_koKR", "s"), ("AuraDescription_Lang_frFR", "s"),
    ("AuraDescription_Lang_deDE", "s"), ("AuraDescription_Lang_enCN", "s"), ("AuraDescription_Lang_zhCN", "s"),
    ("AuraDescription_Lang_enTW", "s"), ("AuraDescription_Lang_zhTW", "s"), ("AuraDescription_Lang_esES", "s"),
    ("AuraDescription_Lang_esMX", "s"), ("AuraDescription_Lang_ruRU", "s"), ("AuraDescription_Lang_ptPT", "s"),
    ("AuraDescription_Lang_ptBR", "s"), ("AuraDescription_Lang_itIT", "s"), ("AuraDescription_Lang_Unk", "s"),
    ("AuraDescription_Lang_Mask", "u"), ("ManaCostPct", "u"), ("StartRecoveryCategory", "u"),
    ("StartRecoveryTime", "u"), ("MaxTargetLevel", "u"), ("SpellClassSet", "u"), ("SpellClassMask_1", "u"),
    ("SpellClassMask_2", "u"), ("SpellClassMask_3", "u"), ("MaxTargets", "u"), ("DefenseType", "u"),
    ("PreventionType", "u"), ("StanceBarOrder", "u"), ("EffectChainAmplitude_1", "f"),
    ("EffectChainAmplitude_2", "f"), ("EffectChainAmplitude_3", "f"), ("MinFactionID", "u"), ("MinReputation", "u"),
    ("RequiredAuraVision", "u"), ("RequiredTotemCategoryID_1", "u"), ("RequiredTotemCategoryID_2", "u"),
    ("RequiredAreasID", "i"), ("SchoolMask", "u"), ("RuneCostID", "u"), ("SpellMissileID", "u"),
    ("PowerDisplayID", "i"), ("EffectBonusMultiplier_1", "f"), ("EffectBonusMultiplier_2", "f"),
    ("EffectBonusMultiplier_3", "f"), ("SpellDescriptionVariableID", "u"), ("SpellDifficultyID", "u"),
)

# skillraceclassinfo_dbc and skilllineability_dbc: every column `int` (signed), in client column order.
SERVER_SKILL_RACE_CLASS_COLUMNS = ("ID", "SkillID", "RaceMask", "ClassMask", "Flags", "MinLevel", "SkillTierID", "SkillCostIndex")
SERVER_SKILL_LINE_ABILITY_COLUMNS = ("ID", "SkillLine", "Spell", "RaceMask", "ClassMask", "ExcludeRace", "ExcludeClass",
                                     "MinSkillLineRank", "SupercededBySpell", "AcquireMethod", "TrivialSkillLineRankHigh",
                                     "TrivialSkillLineRankLow", "CharacterPoints_1", "CharacterPoints_2")


class SpellError(Exception):
    pass


def float_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", float(value)))[0]


def bits_float(value: int) -> float:
    return struct.unpack("<f", struct.pack("<I", value & 0xFFFFFFFF))[0]


def field_problems(table: DbcTable, spell: SpellDef) -> list[str]:
    """Problems with a SpellDef's fields against the client's Spell layout."""
    problems = []
    names = {c.name: c for c in table.schema.columns}

    for key, value in spell.fields.items():
        column = names.get(key)

        if column is None:
            problems.append(f"fields.{key}: Spell.dbc has no such column")
        elif key in MANAGED or column.is_string or column.kind == "locflags":
            problems.append(f"fields.{key}: set by RaceForge from the spell's own keys (id, name, subtext, description, aura_description, icon, visual)")
        elif column.kind != "float" and isinstance(value, float) and not value.is_integer():
            problems.append(f"fields.{key}: a whole number is needed")
        elif column.kind != "float" and not -0x80000000 <= int(value) <= 0xFFFFFFFF:
            problems.append(f"fields.{key}: {value} does not fit 32 bits")

    return problems


def build_row(table: DbcTable, spell: SpellDef) -> list[int]:
    """The Spell.dbc row of a SpellDef (its strings are added to the table's string block)."""
    problems = field_problems(table, spell)

    if problems:
        raise SpellError(f"racial spell {spell.id} ({spell.name}): " + "; ".join(problems))

    row = [0] * len(table.schema.columns)
    values = dict(DEFAULTS)
    values.update(spell.fields)
    values.update({"id": spell.id, "spellIconID": spell.icon, "spellVisualID[0]": spell.visual})

    for key, value in values.items():
        column = table.schema.columns[table.col(key)]

        if column.kind == "float":
            row[table.col(key)] = float_bits(value)
        else:
            table.set(row, key, int(value))

    for key, field_name in SPELL_TEXT_FIELDS.items():
        text = spell.text(key)
        table.set_loc(row, field_name, [text if code in spell.text_locales else "" for code in LOCALES] + [""] * (16 - len(LOCALES)))
        table.set(row, f"{field_name}_flags", LOC_FLAGS_TEXT if text else LOC_FLAGS_EMPTY)

    return row


# --- SQL ---------------------------------------------------------------------------------------------------------


def _sql_text(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "''") + "'"


def _sql_float(value: int) -> str:
    number = bits_float(value)
    text = repr(number)
    return text[:-2] if text.endswith(".0") else text


def sql_values(table: DbcTable, row: list[int], columns=SERVER_SPELL_COLUMNS) -> list[str]:
    """The row's values as SQL literals, in client column order, typed for the server column."""
    out = []

    for (name, kind), column, value in zip(columns, table.schema.columns, row):
        if column.is_string:
            out.append(_sql_text(table.string_at(value)))
        elif kind == "f" or column.kind == "float":
            out.append(_sql_float(value))
        elif kind in ("u", "U"):
            out.append(str(value & 0xFFFFFFFF))
        else:
            out.append(str(to_signed(value)))

    return out


def insert_sql(table_name: str, columns, rows: list[list[str]], comments: list[str] | None = None) -> str:
    """INSERT INTO table (columns) VALUES (row), ... with one row per line. columns: names or (name, kind) pairs."""
    names = [c if isinstance(c, str) else c[0] for c in columns]
    head = [f"INSERT INTO `{table_name}` ("]
    line = ""

    for i, name in enumerate(names):
        item = f"`{name}`" + (", " if i + 1 < len(names) else "")

        if len(line) + len(item) > 116:
            head.append(line.rstrip())
            line = ""

        line += item

    head.append(line + ") VALUES")
    body = []

    for i, values in enumerate(rows):
        comment = f" -- {comments[i]}" if comments and comments[i] else ""
        end = ")" + ("," if i + 1 < len(rows) else ";")
        body += wrap_tuple(values, end, comment)

    return "\n".join(head + body)


def wrap_tuple(values: list[str], end: str, comment: str = "", width: int = 120) -> list[str]:
    """One VALUES tuple, broken between values so that lines stay within width where a single value allows it
    (continuation lines are indented by 4). The comment goes on the first line."""
    lines, line = [], "(" if not comment else ""
    first = True

    for i, value in enumerate(values):
        piece = value + (", " if i + 1 < len(values) else end)
        prefix = "(" if first and comment else ""

        if line.strip() and len(line) + len(piece.rstrip()) > width:
            lines.append(line.rstrip())
            line = "    "

        line += prefix + piece
        first = False

    lines.append(line.rstrip())

    if comment:
        lines.insert(0, comment.strip())

    return lines


def spell_sql(table: DbcTable, rows: list[list[int]]) -> str:
    """DELETE + INSERT of spell_dbc rows built from Spell.dbc rows."""
    ids = [to_signed(r[0]) for r in rows]
    names = [table.get_str(r, "name[0]") for r in rows]
    out = [f"DELETE FROM `spell_dbc` WHERE `ID` IN ({', '.join(map(str, ids))});"]
    out.append(insert_sql("spell_dbc", SERVER_SPELL_COLUMNS, [sql_values(table, r) for r in rows], names))
    return "\n".join(out)


_INSERT_HEAD = re.compile(r"INSERT INTO `(\w+)` \((.*?)\) VALUES", re.S)


def _split_values(text: str, start: int) -> tuple[list[list[str]], int]:
    """The tuples of a VALUES list from text[start:] as lists of raw literals (strings keep their quotes), and the
    index after the ';' that ends the statement. Quotes, doubled quotes, backslash escapes and -- comments between
    the tuples are handled, so a ';' or ')' inside a string does not end anything."""
    rows, row, item, depth, quote, i = [], [], "", 0, False, start

    while i < len(text):
        ch = text[i]

        if quote:
            item += ch

            if ch == "\\" and i + 1 < len(text):
                item += text[i + 1]
                i += 1
            elif ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    item += "'"
                    i += 1
                else:
                    quote = False
        elif ch == "'":
            quote = True
            item += ch
        elif ch == "-" and text[i:i + 2] == "--" and depth == 0:
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue
        elif ch == ";" and depth == 0:
            return rows, i + 1
        elif ch == "(":
            depth += 1

            if depth == 1:
                row, item = [], ""
            else:
                item += ch
        elif ch == ")":
            depth -= 1

            if depth == 0:
                row.append(item.strip())
                rows.append(row)
            else:
                item += ch
        elif ch == "," and depth == 1:
            row.append(item.strip())
            item = ""
        elif depth >= 1:
            item += ch

        i += 1

    raise SpellError("an INSERT has no closing ';'")


def parse_sql_rows(sql: str, table_name: str) -> dict[int, dict[str, str]]:
    """Rows of every INSERT INTO table_name in an SQL text: {ID: {column: raw literal}}. A later row of the same id
    replaces an earlier one, as running the file would."""
    out = {}
    position = 0

    while True:
        match = _INSERT_HEAD.search(sql, position)

        if not match:
            return out

        rows, position = _split_values(sql, match.end())

        if match.group(1) != table_name:
            continue

        columns = [c.strip().strip("`") for c in match.group(2).replace("\n", " ").split(",")]

        for values in rows:
            if len(values) != len(columns):
                raise SpellError(f"{table_name}: a row has {len(values)} values for {len(columns)} columns")

            row = dict(zip(columns, values))
            out[int(row["ID"])] = row


def _literal_equal(sql_literal: str, expected: str, kind: str) -> bool:
    if kind == "s":
        return sql_literal == expected or (sql_literal.upper() == "NULL" and expected == "''")

    if kind == "f":
        try:
            return float_bits(float(sql_literal)) == float_bits(float(expected))
        except ValueError:
            return False

    try:
        return int(sql_literal) == int(expected)
    except ValueError:
        return False


def compare_row(table: DbcTable, row: list[int], sql_row: dict[str, str], columns=SERVER_SPELL_COLUMNS, missing_is_default: bool = False) -> list[str]:
    """Differences between a DBC row and an SQL row (raw literals by column name), as 'Column: dbc -> sql'. With
    missing_is_default, a column the INSERT leaves out has the table's default (0, or NULL for a text)."""
    differences = []

    for (name, kind), expected in zip(columns, sql_values(table, row, columns)):
        kind = "s" if expected.startswith("'") else ("f" if kind == "f" else "i")
        literal = sql_row.get(name)

        if literal is None and missing_is_default:
            literal = "NULL" if kind == "s" else "0"

        if literal is None:
            differences.append(f"{name}: missing in the SQL")
        elif not _literal_equal(literal, expected, kind):
            differences.append(f"{name}: {expected} in the DBC, {literal} in the SQL")

    extra = set(sql_row) - {c[0] if not isinstance(c, str) else c for c in columns}

    if extra:
        differences.append(f"the SQL has columns the DBC lacks: {sorted(extra)}")

    return differences


# The repository root: server_row paths of races.json are relative to it.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def server_row_check(table: DbcTable, row: list[int], spell: SpellDef, repo_root: str = REPO_ROOT) -> tuple[str, str]:
    """(status, detail) of the spell_dbc row another part of the project owns (spell.server_row) against the Spell.dbc
    row: PASS when every column is equal (columns the INSERT leaves out count as the table's defaults), SKIP when the
    file is not in this checkout, FAIL otherwise."""
    path = os.path.join(repo_root, spell.server_row.replace("\\", "/"))

    if not os.path.isfile(path):
        return "SKIP", f"{spell.server_row} not found"

    with open(path, encoding="utf-8") as f:
        sql_row = parse_sql_rows(f.read(), "spell_dbc").get(spell.id)

    if sql_row is None:
        return "FAIL", f"{spell.server_row} has no spell_dbc row {spell.id}"

    differences = compare_row(table, row, sql_row, missing_is_default=True)
    return ("FAIL", "; ".join(differences[:6])) if differences else ("PASS", "")


def server_columns(names) -> list[tuple[str, str]]:
    """(name, 'i') pairs for an all-signed-int server table."""
    return [(n, "i") for n in names]


__all__ = ["DEFAULTS", "SERVER_SPELL_COLUMNS", "SpellError", "build_row", "spell_sql", "parse_sql_rows", "compare_row",
           "sql_values", "insert_sql", "field_problems", "DbcError"]
