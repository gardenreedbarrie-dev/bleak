"""AzerothCore world-database SQL for the new races.

AzerothCore builds its race list and race masks from ChrRaces at start-up (RaceMgr::LoadRaces), so the patched DBCs
in data/dbc carry most of the work. ObjectMgr::LoadPlayerInfo still needs, per race:

- playercreateinfo: one row per class, or the race/class pair cannot be created;
- player_race_stats: the race's stat modifiers;
- playercreateinfo_skills / _spell_custom / _cast_spell: rows by race mask (the server also checks each skill
  against SkillRaceClassInfo.dbc, so the DBC bits and these rows must agree; they use the same rule);
- playercreateinfo_action / _item: rows by race.

Totems (player_totem_model) and druid forms (player_shapeshift_model) are looked up by race too. Every statement
copies the template race's rows from the server's own database, so nothing here depends on Blizzard data, and each
block deletes what it adds first, so the file can be run again.

A race can drop the template's racial skill lines (races.json racials.drop_template_skill_lines): their skills and
spells are left out of the copies, and the start action bar buttons of those spells take the race's first active
racial spell instead. The race's own racial spells (racial_spells) get their spell_dbc rows here, built from the same
row as the Spell.dbc copy, and playercreateinfo_spell_custom rows (AzerothCore teaches those at creation only with
PlayerStart.CustomSpells = 1; a server module can teach them too).
"""

from __future__ import annotations

from . import masks as maskrules
from .config import Config, Position, RaceConfig

DEATH_KNIGHT = 6

HEADER = """-- Bleakhold races for AzerothCore (world database), written by RaceForge.
--
-- Before running this, copy every file from server/dbc/ over the server's data/dbc/ (keep a backup). Then run this
-- file on the world database and restart worldserver. It can be run again: each block removes what it adds first.
-- If the world database has rows in chrraces_dbc, charsections_dbc, skillraceclassinfo_dbc, ... they override the
-- DBC files by ID; RaceForge does not write those tables.
"""


def _q(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def _sql_text(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "''") + "'"


def _position_row(race: int, class_id: int, pos: Position) -> str:
    return f"({race}, {class_id}, {pos.map}, {pos.zone}, {_q(pos.x)}, {_q(pos.y)}, {_q(pos.z)}, {_q(pos.o)})"


def _not_in(column: str, values: list[int]) -> str:
    return f" AND `{column}` NOT IN ({', '.join(map(str, values))})" if values else ""


def race_sql(race: RaceConfig, classes: list[int], masks: maskrules.FactionMasks, faction_wide: bool,
             display_ids: tuple[int, int], template_display_ids: tuple[int, int], dropped_spells: list[int] | None = None,
             racial_spells: list[tuple[int, str]] | None = None, action_spell: int = 0) -> str:
    dropped_spells = dropped_spells or []
    racial_spells = racial_spells or []
    t = race.template_race
    r = race.id
    class_list = ", ".join(str(c) for c in classes)
    label = f"{race.name} ({r})"
    out = [f"-- ===== {label}: template race {t}, {race.faction} =====", ""]

    out.append("-- Stat modifiers")
    out.append(f"DELETE FROM `player_race_stats` WHERE `Race` = {r};")

    if race.stats:
        s = race.stats
        out.append(f"INSERT INTO `player_race_stats` (`Race`, `Strength`, `Agility`, `Stamina`, `Intellect`, `Spirit`) VALUES ({r}, {s.strength}, {s.agility}, {s.stamina}, {s.intellect}, {s.spirit});")
    else:
        out.append("INSERT INTO `player_race_stats` (`Race`, `Strength`, `Agility`, `Stamina`, `Intellect`, `Spirit`)")
        out.append(f"SELECT {r}, `Strength`, `Agility`, `Stamina`, `Intellect`, `Spirit` FROM `player_race_stats` WHERE `Race` = {t};")

    out.append("")
    out.append(f"-- Start positions for classes {class_list}")
    out.append(f"DELETE FROM `playercreateinfo` WHERE `race` = {r};")
    rows = []
    copy_dk = False

    for class_id in classes:
        if class_id == DEATH_KNIGHT:
            if race.death_knight_start:
                rows.append(_position_row(r, class_id, race.death_knight_start))
            else:
                copy_dk = True
        elif race.start:
            rows.append(_position_row(r, class_id, race.start))

    if rows:
        if race.start and race.start.comment:
            out.append(f"-- {race.start.comment}")
        if race.death_knight_start and race.death_knight_start.comment and DEATH_KNIGHT in classes:
            out.append(f"-- Death Knights: {race.death_knight_start.comment}")
        out.append("INSERT INTO `playercreateinfo` (`race`, `class`, `map`, `zone`, `position_x`, `position_y`, `position_z`, `orientation`) VALUES")
        out.append(",\n".join(rows) + ";")

    non_dk = [c for c in classes if c != DEATH_KNIGHT]

    if not race.start and non_dk:
        out.append("-- No start position configured: the template race's own start positions")
        out.append("INSERT INTO `playercreateinfo` (`race`, `class`, `map`, `zone`, `position_x`, `position_y`, `position_z`, `orientation`)")
        out.append(f"SELECT {r}, `class`, `map`, `zone`, `position_x`, `position_y`, `position_z`, `orientation` FROM `playercreateinfo` WHERE `race` = {t} AND `class` IN ({', '.join(map(str, non_dk))});")

    if copy_dk:
        out.append("INSERT INTO `playercreateinfo` (`race`, `class`, `map`, `zone`, `position_x`, `position_y`, `position_z`, `orientation`)")
        out.append(f"SELECT {r}, `class`, `map`, `zone`, `position_x`, `position_y`, `position_z`, `orientation` FROM `playercreateinfo` WHERE `race` = {t} AND `class` = {DEATH_KNIGHT};")

    out.append("")
    out.append("-- Action bars and extra start items of the template race")
    out.append(f"DELETE FROM `playercreateinfo_action` WHERE `race` = {r};")
    out.append("INSERT INTO `playercreateinfo_action` (`race`, `class`, `button`, `action`, `type`)")

    if dropped_spells:
        spell_list = ", ".join(map(str, dropped_spells))
        out.append(f"SELECT {r}, `class`, `button`, `action`, `type` FROM `playercreateinfo_action` WHERE `race` = {t} AND `class` IN ({class_list})"
                   f" AND NOT (`type` = 0 AND `action` IN ({spell_list}));")

        if action_spell:
            out.append(f"-- The template's racial buttons take the race's own racial {action_spell}")
            out.append("INSERT INTO `playercreateinfo_action` (`race`, `class`, `button`, `action`, `type`)")
            out.append(f"SELECT {r}, `class`, `button`, {action_spell}, 0 FROM `playercreateinfo_action` WHERE `race` = {t} AND `class` IN ({class_list})"
                       f" AND `type` = 0 AND `action` IN ({spell_list});")
    else:
        out.append(f"SELECT {r}, `class`, `button`, `action`, `type` FROM `playercreateinfo_action` WHERE `race` = {t} AND `class` IN ({class_list});")
    out.append(f"DELETE FROM `playercreateinfo_item` WHERE `race` = {r};")
    out.append("INSERT INTO `playercreateinfo_item` (`race`, `class`, `itemid`, `amount`, `Note`)")
    out.append(f"SELECT {r}, `class`, `itemid`, `amount`, `Note` FROM `playercreateinfo_item` WHERE `race` = {t} AND `class` IN ({class_list});")

    out.append("")
    out.append(f"-- Skills and spells by race mask, with the rule used for the DBC masks (bit {race.bit} = 1 << ({r} - 1))")
    if race.drop_skill_lines:
        out.append(f"-- Left out: the template's racial skill lines {race.drop_skill_lines} and their spells")

    condition = maskrules.sql_condition("raceMask", race, masks, t, faction_wide) + _not_in("skill", race.drop_skill_lines)
    out.append(f"DELETE FROM `playercreateinfo_skills` WHERE `raceMask` = {race.bit};")
    out.append("INSERT IGNORE INTO `playercreateinfo_skills` (`raceMask`, `classMask`, `skill`, `rank`, `comment`)")
    out.append(f"SELECT {race.bit}, `classMask`, `skill`, `rank`, LEFT(CONCAT({_sql_text(race.name + ': ')}, IFNULL(`comment`, '')), 255)")
    out.append(f"FROM `playercreateinfo_skills` WHERE {condition};")

    condition = maskrules.sql_condition("racemask", race, masks, t, faction_wide) + _not_in("Spell", dropped_spells)
    out.append(f"DELETE FROM `playercreateinfo_spell_custom` WHERE `racemask` = {race.bit};")
    out.append("INSERT IGNORE INTO `playercreateinfo_spell_custom` (`racemask`, `classmask`, `Spell`, `Note`)")
    out.append(f"SELECT {race.bit}, `classmask`, `Spell`, `Note` FROM `playercreateinfo_spell_custom` WHERE {condition};")

    if racial_spells:
        out.append(f"-- The race's own racials (taught at creation with PlayerStart.CustomSpells = 1, or by a server module)")
        out.append("INSERT IGNORE INTO `playercreateinfo_spell_custom` (`racemask`, `classmask`, `Spell`, `Note`) VALUES")
        out.append(",\n".join(f"({race.bit}, 0, {spell_id}, {_sql_text(race.name + ' - ' + name)})" for spell_id, name in racial_spells) + ";")

    condition = maskrules.sql_condition("raceMask", race, masks, t, faction_wide) + _not_in("spell", dropped_spells)
    out.append(f"DELETE FROM `playercreateinfo_cast_spell` WHERE `raceMask` = {race.bit};")
    out.append("INSERT INTO `playercreateinfo_cast_spell` (`raceMask`, `classMask`, `spell`, `note`)")
    out.append(f"SELECT DISTINCT {race.bit}, `classMask`, `spell`, `note` FROM `playercreateinfo_cast_spell` WHERE {condition};")

    out.append("")
    out.append("-- Totem and shapeshift models by race")
    out.append(f"DELETE FROM `player_totem_model` WHERE `RaceID` = {r};")
    out.append("INSERT INTO `player_totem_model` (`TotemID`, `RaceID`, `ModelID`)")
    out.append(f"SELECT `TotemID`, {r}, `ModelID` FROM `player_totem_model` WHERE `RaceID` = {t};")
    out.append(f"DELETE FROM `player_shapeshift_model` WHERE `RaceID` = {r};")
    out.append("INSERT INTO `player_shapeshift_model` (`ShapeshiftID`, `RaceID`, `CustomizationID`, `GenderID`, `ModelID`)")
    out.append(f"SELECT `ShapeshiftID`, {r}, `CustomizationID`, `GenderID`, `ModelID` FROM `player_shapeshift_model` WHERE `RaceID` = {t};")

    out.append("")
    new_displays = [(d, td) for d, td in zip(display_ids, template_display_ids) if d != td]

    if new_displays:
        out.append("-- creature_model_info for display ids the template race does not use (Unit::SetDisplayId reads the gender from it)")
        male, female = display_ids

        for display, template_display in new_displays:
            other = female if display == male else male
            out.append(f"DELETE FROM `creature_model_info` WHERE `DisplayID` = {display};")
            out.append("INSERT INTO `creature_model_info` (`DisplayID`, `BoundingRadius`, `CombatReach`, `Gender`, `DisplayID_Other_Gender`)")
            out.append(f"SELECT {display}, `BoundingRadius`, `CombatReach`, `Gender`, {other} FROM `creature_model_info` WHERE `DisplayID` = {template_display};")
    else:
        out.append(f"-- Display ids {display_ids[0]}/{display_ids[1]} are the template race's: creature_model_info already has them.")

    out.append("")
    return "\n".join(out)


def world_sql(config: Config, summaries: dict, masks: maskrules.FactionMasks, template_displays: dict[int, tuple[int, int]],
              spell_rows_sql: str = "") -> str:
    parts = [HEADER]

    if spell_rows_sql:
        parts.append("-- ===== Spells: the same rows as the Spell.dbc copies (client/DBFilesClient, server/dbc) =====")
        parts.append(spell_rows_sql)
        parts.append("")

    for race in config.races:
        summary = summaries[race.id]
        parts.append(race_sql(race, summary.classes, masks, config.policy.faction_wide_masks,
                              (summary.male_display, summary.female_display), template_displays[race.id],
                              summary.dropped_spells, [(s, config.spells[s].name) for s in race.racial_spells],
                              config.action_bar_spell(race)))

    return "\n".join(parts)


CONTENT_HEADER = """-- OPTIONAL: race masks of quests, items, area spells, conditions and level-up mail for the Bleakhold races.
--
-- Run after bleakhold_races.sql if the new races should be able to take the quests and use the items of the race
-- named below (by default the stock race of their own faction, whose start zone they share). Masks of 0 (every
-- race) and -1 are left alone; masks that hold every playable race of one faction follow the new race's faction.
-- Review it first: it changes rows other content may rely on. Undo: bleakhold_races_remove.sql.
"""


def content_sql(config: Config, summaries: dict, masks: maskrules.FactionMasks) -> str:
    parts = [CONTENT_HEADER]

    for race in config.races:
        source = race.faction_race if config.policy.content_masks_from == "faction_race" else race.template_race
        wide = config.policy.faction_wide_masks
        out = [f"-- ===== {race.name} ({race.id}): like race {source} =====", ""]

        for table, column in (("quest_template", "AllowableRaces"), ("item_template", "AllowableRace")):
            out.append(f"UPDATE `{table}` SET `{column}` = `{column}` | {race.bit} WHERE {maskrules.sql_condition(column, race, masks, source, wide)};")

        items = sorted(set(summaries[race.id].start_outfit_items))

        if items:
            out.append(f"-- The start outfit comes from race {race.template_race} (CharStartOutfit.dbc): let the race wear it")

            for i in range(0, len(items), 50):
                chunk = ", ".join(map(str, items[i:i + 50]))
                out.append(f"UPDATE `item_template` SET `AllowableRace` = `AllowableRace` | {race.bit} WHERE `entry` IN ({chunk}) AND `AllowableRace` <> -1 AND (`AllowableRace` & {race.bit}) = 0;")

        # These tables have the mask in their primary key; IGNORE skips a row whose new key already exists.
        out.append(f"UPDATE IGNORE `spell_area` SET `racemask` = `racemask` | {race.bit} WHERE {maskrules.sql_condition('racemask', race, masks, source, wide)};")
        out.append(f"UPDATE IGNORE `mail_level_reward` SET `raceMask` = `raceMask` | {race.bit} WHERE {maskrules.sql_condition('raceMask', race, masks, source, wide)};")
        out.append(f"UPDATE IGNORE `conditions` SET `ConditionValue1` = `ConditionValue1` | {race.bit} WHERE `ConditionTypeOrReference` = 16 AND {maskrules.sql_condition('ConditionValue1', race, masks, source, wide)};")
        out.append("")
        parts.append("\n".join(out))

    return "\n".join(parts)


def remove_sql(config: Config) -> str:
    out = ["-- Removes what bleakhold_races.sql and bleakhold_races_content_masks.sql added (world database).",
           "-- Put the stock DBCs back into data/dbc as well. Characters of these races must be deleted first.", ""]

    for race in config.races:
        r, bit = race.id, race.bit
        out.append(f"-- {race.name} ({r})")

        for table, column in (("player_race_stats", "Race"), ("playercreateinfo", "race"), ("playercreateinfo_action", "race"),
                              ("playercreateinfo_item", "race"), ("player_totem_model", "RaceID"), ("player_shapeshift_model", "RaceID")):
            out.append(f"DELETE FROM `{table}` WHERE `{column}` = {r};")

        for table, column in (("playercreateinfo_skills", "raceMask"), ("playercreateinfo_spell_custom", "racemask"), ("playercreateinfo_cast_spell", "raceMask")):
            out.append(f"DELETE FROM `{table}` WHERE `{column}` = {bit};")

        for table, column, extra in (("quest_template", "AllowableRaces", ""), ("item_template", "AllowableRace", ""),
                                     ("spell_area", "racemask", ""), ("mail_level_reward", "raceMask", ""),
                                     ("conditions", "ConditionValue1", "`ConditionTypeOrReference` = 16 AND ")):
            ignore = "IGNORE " if table in ("spell_area", "mail_level_reward", "conditions") else ""
            out.append(f"UPDATE {ignore}`{table}` SET `{column}` = `{column}` & ~{bit} WHERE {extra}(`{column}` & {bit}) <> 0 AND `{column}` <> -1 AND `{column}` <> 4294967295;")

        out.append("")

    spell_ids = config.server_sql_spell_ids()

    if spell_ids:
        out.append("-- Spells")
        out.append(f"DELETE FROM `spell_dbc` WHERE `ID` IN ({', '.join(map(str, spell_ids))});")
        out.append("")

    return "\n".join(out)
