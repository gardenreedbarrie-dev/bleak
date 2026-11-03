r"""Existing characters on the merged tables: the option numbers the package moved, and the SQL that moves the
characters once (README.md, "Bleakhold appearance data contract", "Existing characters").

The package keeps most stock numbers but moves some: the Death Knight skins went from Human 10-12 to 26-28 (the old
numbers now hold NPC-only skins), and those skins have three faces each. The old meaning of a number is the texture its
row names in the saved base (the tables from before the package); its new number is the row of the merged table that
names the same texture:

- skin and face as a pair: the skin's row texture, then the face's two textures on the new skin. A pair with no exact
  match keeps the new skin and takes the nearest face that a character of that kind (Death Knight or not) can have on
  it, and gets at_login | 8 (customize at the next login);
- hair colour by its rows' textures (the colour whose hair rows name the same files for the most styles);
- hair style and features keep their numbers (the package only adds), and that is checked: every hair style of the
  base keeps its CharHairGeosets geoset and showScalp and its section-3 rows' textures at every colour the character
  can pick, and every features value below the base's count keeps its five CharacterFacialHairStyles geosets and its
  section-2 rows' two textures at every hair colour. A style or value that is missing or differs is a changed_styles /
  changed_features entry, and customize stops on it unless the curation's accepted_changes lists it; an accepted one
  moves to the merged number whose rows mean the same (or keeps its number and gets at_login | 8 when none does);
- High Elf (15) takes Blood Elf's (10) mapping and Eredar (19) Draenei's (11): their rows are clones.

The SQL (characters database, the world server stopped) keeps every changed character in bh_appearance_backup with its
old and new values, then changes the five appearance columns (and the corpse's bytes1/bytes2, which pack the same
values, Player.cpp CreateCorpse) where they still hold the old values. The characters whose at_login | 8 the remap set
(they had no customize waiting) are noted in bh_appearance_set_customize. The restore sets back only those columns,
each only where it still holds the remapped value, and takes the 8 off again where the remap set it and it still
waits. Both run again safely. Their only MySQL-only syntax is DROP TEMPORARY TABLE (DROP TABLE to SQLite), so
the tests run them on SQLite.

remap_tables.sql (tables_sql()) creates the two tables; remap_characters.sql (remap_sql()) holds no statement that
commits in MySQL (only CREATE / DROP TEMPORARY TABLE besides the data), so it runs whole in one transaction after the
tables exist, together with whatever is run around it (customize.sh: the Appearance Artist's purchases).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import appearance as ap
from .dbc import DbcTable

AT_LOGIN_CUSTOMIZE = 0x8
BACKUP = "bh_appearance_backup"
# the characters of a run whose at_login | 8 the remap set (they had none): the restore takes it off again. Its own
# table, so a bh_appearance_backup of an earlier build (CREATE TABLE IF NOT EXISTS) needs no ALTER
SET_CUSTOMIZE = "bh_appearance_set_customize"


@dataclass
class Mapping:
    race: int
    sex: int
    dk: bool
    pairs: dict[tuple[int, int], tuple[int, int, bool]] = field(default_factory=dict)  # (skin, face) -> new, exact
    hair_colours: dict[int, int] = field(default_factory=dict)  # only the ones that move
    unmatched_skins: list[int] = field(default_factory=list)
    missing_styles: list[int] = field(default_factory=list)
    # a hair style / features value whose meaning changed: value -> (why, the merged value meaning the same or None)
    changed_styles: dict[int, tuple[str, int | None]] = field(default_factory=dict)
    changed_features: dict[int, tuple[str, int | None]] = field(default_factory=dict)
    # the accepted changes the remap applies: value -> (new value, customize at the next login)
    styles: dict[int, tuple[int, bool]] = field(default_factory=dict)
    features: dict[int, tuple[int, bool]] = field(default_factory=dict)

    def accept(self, kind: str, value: int):
        """Apply one accepted change ("style" or "feature"): to the merged value meaning the same, or keep the number
        and customize."""
        changed, out = (self.changed_styles, self.styles) if kind == "style" else (self.changed_features, self.features)
        _, same = changed[value]
        out[value] = (value, True) if same is None else (same, False)

    def copy(self, race: int) -> "Mapping":
        return Mapping(race, self.sex, self.dk, dict(self.pairs), dict(self.hair_colours), list(self.unmatched_skins),
                       list(self.missing_styles), dict(self.changed_styles), dict(self.changed_features),
                       dict(self.styles), dict(self.features))

    @property
    def moved(self) -> dict[tuple[int, int], tuple[int, int, bool]]:
        return {k: v for k, v in self.pairs.items() if (v[0], v[1]) != k or not v[2]}


def _last_rows(cs: DbcTable, race: int, sex: int) -> dict[tuple[int, int, int], list[int]]:
    out = {}

    for row in cs.rows:
        if cs.get(row, "raceID") == race and cs.get(row, "sexID") == sex:
            out[(cs.get(row, "baseSection"), cs.get(row, "variationIndex"), cs.get(row, "colorIndex"))] = row

    return out


def _tex(cs: DbcTable, row: list[int], slot: int) -> str:
    return ap.name_key(ap.original_name(cs.get_str(row, f"textureName[{slot}]")))


NPC = "npc"  # the kind of an NPC's look (CreatureDisplayInfoExtra): it may use any row


def _ok(cs: DbcTable, row: list[int], dk) -> bool:
    if dk == NPC:
        return True

    flags = cs.get(row, "flags")
    return ap.selectable(flags, ap.WORLD, dk) or ap.selectable(flags, ap.CREATION, dk)


def _pick(candidates: list[int], keep: int) -> int:
    return keep if keep in candidates else min(candidates)


def _geosets(table: DbcTable | None, race: int, sex: int, columns: tuple[str, ...]) -> dict[int, tuple] | None:
    """variationID -> the columns of the last row of a race and sex (CharHairGeosets, CharacterFacialHairStyles)."""
    if table is None:
        return None

    out = {}

    for row in table.rows:
        if table.get(row, "raceID") == race and table.get(row, "sexID") == sex:
            out[table.get(row, "variationID")] = tuple(table.get(row, c) for c in columns)

    return out


HAIR_COLUMNS = ("geosetID", "showscalp")
FACIAL_COLUMNS = tuple(f"geoset[{i}]" for i in range(5))


def _meaning_changes(old, new, base, merged, dk, section: int, slots: int, value: int, other: int,
                     hair_colours: dict[int, int], old_geo, new_geo) -> list[str]:
    """Why merged value `other` does not mean what base value `value` meant (empty: it does): the geosets, and the
    textures of the section's rows at every colour the character could pick (on the colour the remap moves it to)."""
    why = []

    if old_geo is not None and value in old_geo and (new_geo or {}).get(other) != old_geo[value]:
        why.append(f"geosets {old_geo[value]} -> {(new_geo or {}).get(other, 'none')}")

    for (s, v, colour), row in sorted(old.items()):
        if s != section or v != value or not _ok(base, row, dk):
            continue

        to = hair_colours.get(colour, colour)
        new_row = new.get((section, other, to))

        if new_row is None or not _ok(merged, new_row, dk):
            why.append(f"colour {colour}: no row a character can pick")
            continue

        for slot in range(slots):
            was, now = _tex(base, row, slot), _tex(merged, new_row, slot)

            if now != was:  # a blank slot that gets a texture changes the look too
                why.append(f"colour {colour}: texture {slot} {was or 'none'} -> {now or 'none'}")

    return why


def _check_meanings(m: Mapping, old, new, base, merged, dk, section: int, slots: int, old_geo, new_geo,
                    out: dict[int, tuple[str, int | None]]):
    values = {v for (s, v, c) in old if s == section} | set(old_geo or ())
    merged_values = sorted({v for (s, v, c) in new if s == section} | set(new_geo or ()))

    for value in sorted(values):
        why = _meaning_changes(old, new, base, merged, dk, section, slots, value, value, m.hair_colours, old_geo,
                               new_geo)

        if not why:
            continue

        same = next((v for v in merged_values if v != value and not _meaning_changes(
            old, new, base, merged, dk, section, slots, value, v, m.hair_colours, old_geo, new_geo)), None)
        missing = value not in merged_values
        out[value] = (("missing from the merged table" if missing else "; ".join(why[:3])
                       + (f" (+{len(why) - 3} more)" if len(why) > 3 else "")), same)


def compute(base: DbcTable, merged: DbcTable, race: int, sex: int, dk, base_hair: DbcTable | None = None,
            merged_hair: DbcTable | None = None, base_facial: DbcTable | None = None,
            merged_facial: DbcTable | None = None) -> Mapping:
    """One race, sex and kind: False (a player), True (a Death Knight) or NPC (CreatureDisplayInfoExtra, any row).
    With the CharHairGeosets and CharacterFacialHairStyles tables, the hair styles' and features' geosets are compared
    too (an NPC look has no hair style or features to check)."""
    m = Mapping(race, sex, dk)
    old = _last_rows(base, race, sex)
    new = _last_rows(merged, race, sex)
    new_skins = {c: r for (s, v, c), r in new.items() if s == ap.SKIN and v == 0 and _ok(merged, r, dk)}
    by_skin_tex: dict[str, list[int]] = {}

    for colour, row in new_skins.items():
        by_skin_tex.setdefault(_tex(merged, row, 0), []).append(colour)

    for (section, variation, colour), row in sorted(old.items()):
        # only the skins a character of this kind could have had
        if section != ap.SKIN or variation != 0 or not _ok(base, row, dk):
            continue

        key = _tex(base, row, 0)
        candidates = sorted(by_skin_tex.get(key, [])) if key else []
        skin_exact = bool(candidates)

        if candidates:
            new_skin = _pick(candidates, colour)
        elif colour in new_skins:
            new_skin = colour
        elif new_skins:
            new_skin = min(new_skins)
        else:
            continue

        if not skin_exact:
            m.unmatched_skins.append(colour)

        faces_here = {v: r for (s, v, c), r in new.items() if s == ap.FACE and c == new_skin and _ok(merged, r, dk)}

        for (s2, face, c2), face_row in sorted(old.items()):
            if s2 != ap.FACE or c2 != colour or not _ok(base, face_row, dk):
                continue

            want = (_tex(base, face_row, 0), _tex(base, face_row, 1))
            exact = sorted(v for v, r in faces_here.items() if (_tex(merged, r, 0), _tex(merged, r, 1)) == want)

            if exact and skin_exact:
                m.pairs[(colour, face)] = (new_skin, _pick(exact, face), True)
            elif faces_here:
                nearest = min(faces_here, key=lambda v: (abs(v - face), v))
                m.pairs[(colour, face)] = (new_skin, exact[0] if exact else nearest, False)

    # hair colours: the colour whose rows name the same textures for the most hair styles
    old_hair: dict[int, dict[int, str]] = {}
    new_hair: dict[int, dict[int, str]] = {}

    for source, table, out in ((old, base, old_hair), (new, merged, new_hair)):
        for (s, style, colour), row in source.items():
            if s == ap.HAIR and (source is old or _ok(table, row, dk)):
                out.setdefault(colour, {})[style] = _tex(table, row, 0)

    for colour, styles in sorted(old_hair.items()):
        scores = []

        for candidate, theirs in new_hair.items():
            score = sum(1 for st, t in styles.items() if t and theirs.get(st) == t)
            scores.append((score, candidate == colour, -candidate, candidate))

        if not scores:
            continue

        # the most matching styles; on a tie the colour keeps its number, else the lowest number
        best = max(scores)

        if best[0] > 0 and best[3] != colour:
            m.hair_colours[colour] = best[3]

    old_styles = {v for (s, v, c) in old if s == ap.HAIR}
    new_styles = {v for (s, v, c) in new if s == ap.HAIR}
    m.missing_styles = sorted(old_styles - new_styles)

    if dk != NPC:
        _check_meanings(m, old, new, base, merged, dk, ap.HAIR, 3,
                        _geosets(base_hair, race, sex, HAIR_COLUMNS), _geosets(merged_hair, race, sex, HAIR_COLUMNS)
                        if base_hair is not None else None, m.changed_styles)
        old_facial = _geosets(base_facial, race, sex, FACIAL_COLUMNS)
        new_facial = _geosets(merged_facial, race, sex, FACIAL_COLUMNS) if base_facial is not None else None
        _check_meanings(m, old, new, base, merged, dk, ap.FEATURES, 2, old_facial, new_facial, m.changed_features)

    for style in m.missing_styles:
        m.changed_styles.setdefault(style, ("missing from the merged table", None))

    return m


def meaning_problems(mappings: dict[tuple[int, int, bool], Mapping], accepted: set[tuple[int, int, str, int]]) -> \
        list[str]:
    """The changed hair styles and features no accepted change covers (each a plan problem), and the accepted ones
    applied. accepted: (race, sex, "style" or "feature", value); a clone's change is accepted by its source's."""
    problems = []

    for (race, sex, dk), m in sorted(mappings.items()):
        source = ap.CLONES.get(race, race)

        for kind, changed in (("style", m.changed_styles), ("feature", m.changed_features)):
            for value, (why, same) in sorted(changed.items()):
                if (race, sex, kind, value) in accepted or (source, sex, kind, value) in accepted:
                    m.accept(kind, value)
                    continue

                label = "hair style" if kind == "style" else "features value"
                problems.append(
                    f"race {race} {ap.SEXES[sex]}{' Death Knight' if dk else ''}: {label} {value} changed its meaning "
                    f"({why}); every character on it would get another look. Fix the package rows, or list it in "
                    f"the curation's accepted_changes (then it moves to "
                    f"{'value ' + str(same) if same is not None else 'a customize at the next login'})")

    return problems


def compute_all(base: DbcTable, merged: DbcTable, races=ap.PACKAGE_RACES,
                clones: dict[int, int] | None = None, base_hair: DbcTable | None = None,
                merged_hair: DbcTable | None = None, base_facial: DbcTable | None = None,
                merged_facial: DbcTable | None = None) -> dict[tuple[int, int, bool], Mapping]:
    """Every race of races (both sexes, both kinds), and each clone with its source's mapping. A clone's own rows
    are checked for changed hair styles and features too (its merged rows are its source's)."""
    out = {}
    tables = dict(base_hair=base_hair, merged_hair=merged_hair, base_facial=base_facial, merged_facial=merged_facial)

    for race in races:
        for sex in ap.SEXES:
            for dk in (False, True):
                out[(race, sex, dk)] = compute(base, merged, race, sex, dk, **tables)

    for clone, source in (ap.CLONES if clones is None else clones).items():
        for sex in ap.SEXES:
            for dk in (False, True):
                if (source, sex, dk) in out:
                    m = out[(clone, sex, dk)] = out[(source, sex, dk)].copy(clone)
                    own = compute(base, merged, clone, sex, dk, **tables)

                    for mine, theirs in ((m.changed_styles, own.changed_styles),
                                         (m.changed_features, own.changed_features)):
                        for value, change in theirs.items():
                            mine.setdefault(value, change)

    return out


def remap_npcs(cdie: DbcTable, base: DbcTable, merged: DbcTable, races=ap.PACKAGE_RACES,
               clones: dict[int, int] | None = None) -> tuple[DbcTable, int]:
    """CreatureDisplayInfoExtra on the merged numbers: an NPC look's skin and face, and hair colour, moved like a
    character's (by the textures their rows name, any row counting), so an NPC whose look names a skin the package
    moved keeps it (the HD head comes from the skin row). The table is not otherwise changed. Returns it and the rows
    changed."""
    out = DbcTable(cdie.schema, [list(r) for r in cdie.rows], bytes(cdie.strings), cdie.source, cdie.original)
    maps: dict[tuple[int, int], Mapping] = {}
    clones = ap.CLONES if clones is None else clones

    for race in races:
        for sex in ap.SEXES:
            maps[(race, sex)] = compute(base, merged, race, sex, NPC)

    for clone, source in clones.items():
        for sex in ap.SEXES:
            if (source, sex) in maps:
                maps[(clone, sex)] = maps[(source, sex)]

    changed = 0

    for row in out.rows:
        m = maps.get((out.get(row, "displayRaceID"), out.get(row, "displaySexID")))

        if m is None:
            continue

        before = list(row)
        pair = m.pairs.get((out.get(row, "skinID"), out.get(row, "faceID")))

        if pair is not None:
            out.set(row, "skinID", pair[0])
            out.set(row, "faceID", pair[1])

        colour = m.hair_colours.get(out.get(row, "hairColorID"))

        if colour is not None:
            out.set(row, "hairColorID", colour)

        changed += int(row != before)

    return out, changed


def clone_problems(base: DbcTable, clones: dict[int, int] | None = None) -> list[str]:
    """A clone takes its source's mapping only when its rows in the saved base have the same keys as the source's."""
    problems = []

    for clone, source in (ap.CLONES if clones is None else clones).items():
        for sex in ap.SEXES:
            a, b = set(_last_rows(base, clone, sex)), set(_last_rows(base, source, sex))

            if a and a != b:
                problems.append(f"race {clone} sex {sex}: its saved rows are not a clone of race {source}'s "
                                f"({len(a ^ b)} keys differ), so race {source}'s remap does not fit it")

    return problems


# --- SQL -------------------------------------------------------------------------------------------------------


def _run_id(run: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,40}", run):
        raise ValueError(f"run id {run!r}: letters, digits and _.:- only, at most 40")

    return run


def _values(rows: list[tuple]) -> list[str]:
    return ["(" + ", ".join(str(int(v)) for v in row) + ")" for row in rows]


def _insert(table: str, columns: str, rows: list[tuple], chunk: int = 400) -> list[str]:
    out = []
    values = _values(rows)

    for i in range(0, len(values), chunk):
        out.append(f"INSERT INTO `{table}` ({columns}) VALUES\n  " + ",\n  ".join(values[i:i + chunk]) + ";")

    return out


BACKUP_TABLE = f"""CREATE TABLE IF NOT EXISTS `{BACKUP}` (
  `run` VARCHAR(40) NOT NULL,
  `kind` TINYINT UNSIGNED NOT NULL,
  `guid` INT UNSIGNED NOT NULL,
  `old_skin` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `old_face` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `old_hairStyle` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `old_hairColor` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `old_facialStyle` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `new_skin` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `new_face` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `new_hairStyle` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `new_hairColor` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `new_facialStyle` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `old_bytes1` INT UNSIGNED NOT NULL DEFAULT 0,
  `old_bytes2` INT UNSIGNED NOT NULL DEFAULT 0,
  `new_bytes1` INT UNSIGNED NOT NULL DEFAULT 0,
  `new_bytes2` INT UNSIGNED NOT NULL DEFAULT 0,
  `customize` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `state` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`run`, `kind`, `guid`)
);"""

SET_CUSTOMIZE_TABLE = f"""CREATE TABLE IF NOT EXISTS `{SET_CUSTOMIZE}` (
  `run` VARCHAR(40) NOT NULL,
  `guid` INT UNSIGNED NOT NULL,
  PRIMARY KEY (`run`, `guid`)
);"""

COLUMNS = ("skin", "face", "hairStyle", "hairColor", "facialStyle")
REMAP_TABLES = ("bh_remap_pair", "bh_remap_hair", "bh_remap_style", "bh_remap_feature")


def tables_sql() -> str:
    """remap_tables.sql: the backup tables, created if missing (each CREATE commits in MySQL: run before the
    transaction of remap_characters.sql, never inside it)."""
    return "\n".join(["-- raceforge.py customize: the tables remap_characters.sql and restore_characters.sql use.",
                      "-- Characters database. Run before remap_characters.sql (on its own: it commits). Safe to run "
                      "again.", BACKUP_TABLE, SET_CUSTOMIZE_TABLE]) + "\n"


def remap_sql(mappings: dict[tuple[int, int, bool], Mapping], run: str) -> str:
    """remap_characters.sql: kind 0 rows of the backup are characters, kind 1 corpses (by the owner's guid)."""
    run = _run_id(run)
    pairs, hair, styles, features = [], [], [], []

    for (race, sex, dk), m in sorted(mappings.items()):
        for (skin, face), (new_skin, new_face, exact) in sorted(m.moved.items()):
            pairs.append((race, sex, int(dk), skin, face, new_skin, new_face, 0 if exact else 1))

        for colour, new_colour in sorted(m.hair_colours.items()):
            hair.append((race, sex, int(dk), colour, new_colour))

        # accepted hair style / features changes (Mapping.accept): to the value meaning the same, or a customize
        for style, (new_style, customize) in sorted(m.styles.items()):
            styles.append((race, sex, int(dk), style, new_style, int(customize)))

        for value, (new_value, customize) in sorted(m.features.items()):
            features.append((race, sex, int(dk), value, new_value, int(customize)))

    b = f"`{BACKUP}`"
    w = f"b.`run` = '{run}'"
    lines = [
        f"-- raceforge.py customize, run {run}: existing characters onto the merged appearance tables.",
        "-- Characters database (acore_characters), with the world server stopped. Safe to run again.",
        f"-- {len(pairs)} (skin, face) pair(s) and {len(hair)} hair colour(s) move "
        f"({sum(1 for p in pairs if p[7])} pair(s) without an exact match get customize at the next login); "
        f"{len(styles)} accepted hair style and {len(features)} accepted features change(s).",
        "-- Run remap_tables.sql first. Nothing here commits on its own (temporary tables only): one transaction.",
        "DROP TEMPORARY TABLE IF EXISTS `bh_remap_pair`;",
        "CREATE TEMPORARY TABLE `bh_remap_pair` (`race` TINYINT UNSIGNED NOT NULL, `gender` TINYINT UNSIGNED NOT NULL, "
        "`dk` TINYINT UNSIGNED NOT NULL, `skin` TINYINT UNSIGNED NOT NULL, `face` TINYINT UNSIGNED NOT NULL, "
        "`new_skin` TINYINT UNSIGNED NOT NULL, `new_face` TINYINT UNSIGNED NOT NULL, `customize` TINYINT UNSIGNED NOT "
        "NULL, PRIMARY KEY (`race`, `gender`, `dk`, `skin`, `face`));",
        "DROP TEMPORARY TABLE IF EXISTS `bh_remap_hair`;",
        "CREATE TEMPORARY TABLE `bh_remap_hair` (`race` TINYINT UNSIGNED NOT NULL, `gender` TINYINT UNSIGNED NOT NULL, "
        "`dk` TINYINT UNSIGNED NOT NULL, `color` TINYINT UNSIGNED NOT NULL, `new_color` TINYINT UNSIGNED NOT NULL, "
        "PRIMARY KEY (`race`, `gender`, `dk`, `color`));",
    ]

    for name, column in (("bh_remap_style", "hairStyle"), ("bh_remap_feature", "facialStyle")):
        lines.append(f"DROP TEMPORARY TABLE IF EXISTS `{name}`;")
        lines.append(f"CREATE TEMPORARY TABLE `{name}` (`race` TINYINT UNSIGNED NOT NULL, `gender` TINYINT UNSIGNED "
                     f"NOT NULL, `dk` TINYINT UNSIGNED NOT NULL, `{column}` TINYINT UNSIGNED NOT NULL, `new_value` "
                     "TINYINT UNSIGNED NOT NULL, `customize` TINYINT UNSIGNED NOT NULL, PRIMARY KEY (`race`, "
                     f"`gender`, `dk`, `{column}`));")

    lines += _insert("bh_remap_pair", "`race`, `gender`, `dk`, `skin`, `face`, `new_skin`, `new_face`, `customize`",
                     pairs)
    lines += _insert("bh_remap_hair", "`race`, `gender`, `dk`, `color`, `new_color`", hair)
    lines += _insert("bh_remap_style", "`race`, `gender`, `dk`, `hairStyle`, `new_value`, `customize`", styles)
    lines += _insert("bh_remap_feature", "`race`, `gender`, `dk`, `facialStyle`, `new_value`, `customize`", features)

    def joins(race: str, gender: str, dk: str, skin: str, face: str, colour: str, style: str, facial: str) -> str:
        return (f"LEFT JOIN `bh_remap_pair` p ON p.`race` = {race} AND p.`gender` = {gender} AND p.`dk` = {dk} "
                f"AND p.`skin` = {skin} AND p.`face` = {face}\n"
                f"LEFT JOIN `bh_remap_hair` h ON h.`race` = {race} AND h.`gender` = {gender} AND h.`dk` = {dk} "
                f"AND h.`color` = {colour}\n"
                f"LEFT JOIN `bh_remap_style` s ON s.`race` = {race} AND s.`gender` = {gender} AND s.`dk` = {dk} "
                f"AND s.`hairStyle` = {style}\n"
                f"LEFT JOIN `bh_remap_feature` f ON f.`race` = {race} AND f.`gender` = {gender} AND f.`dk` = {dk} "
                f"AND f.`facialStyle` = {facial}\n")

    any_row = "WHERE (p.`race` IS NOT NULL OR h.`race` IS NOT NULL OR s.`race` IS NOT NULL OR f.`race` IS NOT NULL)\n"
    customize = ("(CASE WHEN COALESCE(p.`customize`, 0) = 1 OR COALESCE(s.`customize`, 0) = 1 OR "
                 "COALESCE(f.`customize`, 0) = 1 THEN 1 ELSE 0 END)")

    lines.append(
        f"INSERT INTO {b} (`run`, `kind`, `guid`, `old_skin`, `old_face`, `old_hairStyle`, `old_hairColor`, "
        "`old_facialStyle`, `new_skin`, `new_face`, `new_hairStyle`, `new_hairColor`, `new_facialStyle`, `customize`)\n"
        f"SELECT '{run}', 0, c.`guid`, c.`skin`, c.`face`, c.`hairStyle`, c.`hairColor`, c.`facialStyle`,\n"
        "  COALESCE(p.`new_skin`, c.`skin`), COALESCE(p.`new_face`, c.`face`),\n"
        "  COALESCE(s.`new_value`, c.`hairStyle`),\n"
        f"  COALESCE(h.`new_color`, c.`hairColor`), COALESCE(f.`new_value`, c.`facialStyle`), {customize}\n"
        "FROM `characters` c\n"
        + joins("c.`race`", "c.`gender`", "(CASE WHEN c.`class` = 6 THEN 1 ELSE 0 END)", "c.`skin`", "c.`face`",
                "c.`hairColor`", "c.`hairStyle`", "c.`facialStyle`")
        + any_row
        + f"  AND NOT EXISTS (SELECT 1 FROM {b} x WHERE x.`run` = '{run}' AND x.`kind` = 0 AND x.`guid` = c.`guid`);")

    def column(name: str) -> str:
        sub = f"(SELECT b.`{{}}_{name}` FROM {b} b WHERE {w} AND b.`kind` = 0 AND b.`guid` = `characters`.`guid`)"
        return f"  `{name}` = CASE WHEN `{name}` = {sub.format('old')} THEN {sub.format('new')} ELSE `{name}` END"

    pending = f"(SELECT b.`guid` FROM {b} b WHERE {w} AND b.`kind` = 0 AND b.`state` = 0)"
    # before the bit is set, and only for rows still at state 0: a second run cannot note what the first one set
    lines.append(f"INSERT INTO `{SET_CUSTOMIZE}` (`run`, `guid`)\n"
                 f"SELECT '{run}', b.`guid` FROM {b} b WHERE {w} AND b.`kind` = 0 AND b.`state` = 0 AND "
                 f"b.`customize` = 1\n"
                 f"  AND b.`guid` IN (SELECT c.`guid` FROM `characters` c WHERE (c.`at_login` & {AT_LOGIN_CUSTOMIZE}) "
                 "= 0)\n"
                 f"  AND NOT EXISTS (SELECT 1 FROM `{SET_CUSTOMIZE}` x WHERE x.`run` = '{run}' AND x.`guid` = "
                 "b.`guid`);")
    lines.append("UPDATE `characters` SET\n" + ",\n".join(column(c) for c in COLUMNS) + ",\n"
                 f"  `at_login` = CASE WHEN (SELECT b.`customize` FROM {b} b WHERE {w} AND b.`kind` = 0 AND b.`guid` = "
                 f"`characters`.`guid`) = 1 THEN `at_login` | {AT_LOGIN_CUSTOMIZE} ELSE `at_login` END\n"
                 f"WHERE `guid` IN {pending};")
    lines.append(f"UPDATE {b} SET `state` = 1 WHERE `run` = '{run}' AND `kind` = 0 AND `state` = 0;")

    # corpses: bytes1 = race << 8 | gender << 16 | skin << 24; bytes2 = face | style << 8 | colour << 16 | facial << 24
    k_race, k_gender = "((k.`bytes1` >> 8) & 255)", "((k.`bytes1` >> 16) & 255)"
    k_skin, k_face, k_colour = "((k.`bytes1` >> 24) & 255)", "(k.`bytes2` & 255)", "((k.`bytes2` >> 16) & 255)"
    k_style, k_facial = "((k.`bytes2` >> 8) & 255)", "((k.`bytes2` >> 24) & 255)"
    lines.append(
        f"INSERT INTO {b} (`run`, `kind`, `guid`, `old_bytes1`, `old_bytes2`, `new_bytes1`, `new_bytes2`, `customize`)\n"
        f"SELECT '{run}', 1, k.`guid`, k.`bytes1`, k.`bytes2`,\n"
        f"  (k.`bytes1` & 16777215) | (COALESCE(p.`new_skin`, {k_skin}) << 24),\n"
        f"  COALESCE(p.`new_face`, {k_face}) | (COALESCE(s.`new_value`, {k_style}) << 8) | "
        f"(COALESCE(h.`new_color`, {k_colour}) << 16) | (COALESCE(f.`new_value`, {k_facial}) << 24), 0\n"
        "FROM `corpse` k\n"
        "LEFT JOIN `characters` c ON c.`guid` = k.`guid`\n"
        + joins(k_race, k_gender, "(CASE WHEN c.`class` = 6 THEN 1 ELSE 0 END)", k_skin, k_face, k_colour, k_style,
                k_facial)
        + any_row
        + f"  AND NOT EXISTS (SELECT 1 FROM {b} x WHERE x.`run` = '{run}' AND x.`kind` = 1 AND x.`guid` = k.`guid`);")

    def corpse(name: str) -> str:
        sub = f"(SELECT b.`{{}}_{name}` FROM {b} b WHERE {w} AND b.`kind` = 1 AND b.`guid` = `corpse`.`guid`)"
        return f"  `{name}` = CASE WHEN `{name}` = {sub.format('old')} THEN {sub.format('new')} ELSE `{name}` END"

    lines.append("UPDATE `corpse` SET\n" + ",\n".join(corpse(c) for c in ("bytes1", "bytes2")) + "\n"
                 f"WHERE `guid` IN (SELECT b.`guid` FROM {b} b WHERE {w} AND b.`kind` = 1 AND b.`state` = 0);")
    lines.append(f"UPDATE {b} SET `state` = 1 WHERE `run` = '{run}' AND `kind` = 1 AND `state` = 0;")
    for name in REMAP_TABLES:
        lines.append(f"DROP TEMPORARY TABLE IF EXISTS `{name}`;")

    return "\n".join(lines) + "\n"


def restore_sql(run: str) -> str:
    """restore_characters.sql: only the five columns (and the corpse bytes), only where they still hold the new
    value."""
    run = _run_id(run)
    b = f"`{BACKUP}`"
    w = f"b.`run` = '{run}'"

    def column(table: str, kind: int, name: str) -> str:
        sub = f"(SELECT b.`{{}}_{name}` FROM {b} b WHERE {w} AND b.`kind` = {kind} AND b.`guid` = `{table}`.`guid`)"
        return f"  `{name}` = CASE WHEN `{name}` = {sub.format('new')} THEN {sub.format('old')} ELSE `{name}` END"

    lines = [f"-- raceforge.py customize, run {run}: puts back the appearance the remap changed.",
             "-- Characters database, with the world server stopped. Safe to run again.",
             BACKUP_TABLE, SET_CUSTOMIZE_TABLE]

    for table, kind, cols in (("characters", 0, COLUMNS), ("corpse", 1, ("bytes1", "bytes2"))):
        lines.append(f"UPDATE `{table}` SET\n" + ",\n".join(column(table, kind, c) for c in cols) + "\n"
                     f"WHERE `guid` IN (SELECT b.`guid` FROM {b} b WHERE {w} AND b.`kind` = {kind} AND b.`state` = 1);")

        if kind == 0:
            # the customize the remap gave (the character had none waiting), while it still waits; before state 2.
            # "- 8" behind the bit test: the same on MySQL's unsigned column and on SQLite
            lines.append(f"UPDATE `characters` SET `at_login` = `at_login` - {AT_LOGIN_CUSTOMIZE}\n"
                         f"WHERE (`at_login` & {AT_LOGIN_CUSTOMIZE}) <> 0 AND `guid` IN (SELECT b.`guid` FROM {b} b "
                         f"WHERE {w} AND b.`kind` = 0 AND b.`state` = 1 AND b.`guid` IN (SELECT x.`guid` FROM "
                         f"`{SET_CUSTOMIZE}` x WHERE x.`run` = '{run}'));")

        lines.append(f"UPDATE {b} SET `state` = 2 WHERE `run` = '{run}' AND `kind` = {kind} AND `state` = 1;")

    return "\n".join(lines) + "\n"


def marks_rollback_sql(bases: dict[tuple[int, int], int]) -> str:
    """For a stage-2 rollback: every features value back to its base (value % B) and every face to its base (% 40),
    in characters and corpses. bases: (race, sex) -> B of the race-sexes that had marks."""
    lines = ["-- raceforge.py customize: marks and eyes off (stage 2 rolled back). Characters database, the world",
             "-- server stopped. Everyone keeps their base look; safe to run again."]

    for (race, sex), b in sorted(bases.items()):
        lines.append(f"UPDATE `characters` SET `facialStyle` = `facialStyle` % {b} WHERE `race` = {race} AND `gender` "
                     f"= {sex} AND `facialStyle` >= {b};")
        lines.append(f"UPDATE `corpse` SET `bytes2` = (`bytes2` & 16777215) | (((`bytes2` >> 24) % {b}) << 24) WHERE "
                     f"((`bytes1` >> 8) & 255) = {race} AND ((`bytes1` >> 16) & 255) = {sex} AND ((`bytes2` >> 24) & "
                     f"255) >= {b};")

    lines.append(f"UPDATE `characters` SET `face` = `face` % {ap.EYE_STRIDE} WHERE `face` >= {ap.EYE_STRIDE};")
    lines.append(f"UPDATE `corpse` SET `bytes2` = (`bytes2` & 4294967040) | ((`bytes2` & 255) % {ap.EYE_STRIDE}) "
                 f"WHERE (`bytes2` & 255) >= {ap.EYE_STRIDE};")
    return "\n".join(lines) + "\n"


def hidden_count_sql(hidden: list[tuple], changed: list[tuple] = ()) -> str:
    """count_hidden.sql (read only): characters on a hidden skin or face after the remap.

    hidden: (race, sex, "skin", colour) or (race, sex, "skin", colour, colour) for a skin row, and
    (race, sex, "face", variation, skin colour) for a face row. A face row is one face on one skin colour, so a face is
    counted only on the skin colours whose row of that face is hidden (the face byte is base + 40 x eye, so the base
    face is face % 40). A face without its skin colour is refused: counting it on every skin would count characters
    whose face is fine on their own skin.

    changed: (race, sex, "hairStyle" or "facialStyle", value, dk) of every accepted hair style or features change
    the remap moved off its number (realm_customize.accepted_looks()): the characters of that kind (dk: Death
    Knights, class 6, or the others) still on the old value right after the remap, which must be none. Without dk the
    count is of every class."""
    lines = ["-- raceforge.py customize: characters whose look uses a row the curation hid (read only).",
             "-- Every count must be 0, or the character is moved by remap_characters.sql or given a customize."]
    skins: set[tuple[int, int, int]] = set()
    faces: dict[tuple[int, int, int], set[int]] = {}

    for entry in hidden:
        race, sex, column, value = (int(entry[0]), int(entry[1]), entry[2], int(entry[3]))

        if column == "skin":
            if len(entry) > 4 and int(entry[4]) != value:
                raise ValueError(f"hidden skin row {entry}: its colour is its value")

            skins.add((race, sex, value))
        elif column == "face":
            if len(entry) < 5 or entry[4] is None:
                raise ValueError(f"hidden face row {entry}: needs its skin colour")

            if not 0 <= value < ap.EYE_STRIDE:
                raise ValueError(f"hidden face row {entry}: faces are below {ap.EYE_STRIDE}")

            faces.setdefault((race, sex, value), set()).add(int(entry[4]))
        else:
            raise ValueError(column)

    selects = []

    for race, sex, value in skins:
        selects.append(((race, sex, "skin", value),
                        f"SELECT {race} AS `race`, {sex} AS `gender`, 'skin' AS `column`, {value} AS `value`, "
                        f"COUNT(*) AS `characters` FROM `characters` WHERE `race` = {race} AND `gender` = {sex} AND "
                        f"`skin` = {value};"))

    for (race, sex, value), colours in faces.items():
        listed = ", ".join(str(c) for c in sorted(colours))
        selects.append(((race, sex, "face", value),
                        f"SELECT {race} AS `race`, {sex} AS `gender`, 'face' AS `column`, {value} AS `value`, "
                        f"COUNT(*) AS `characters` FROM `characters` WHERE `race` = {race} AND `gender` = {sex} AND "
                        f"`face` % {ap.EYE_STRIDE} = {value} AND `skin` IN ({listed});"))

    entries = set()

    for entry in changed:
        dk = None if len(entry) < 5 or entry[4] is None else bool(entry[4])
        entries.add((int(entry[0]), int(entry[1]), entry[2], int(entry[3]), dk))

    for race, sex, column, value, dk in sorted(entries, key=lambda e: (e[:4], -1 if e[4] is None else int(e[4]))):
        if column not in ("hairStyle", "facialStyle"):
            raise ValueError(column)

        kind = "" if dk is None else (" AND `class` = 6" if dk else " AND `class` <> 6")
        selects.append(((race, sex, column, value, -1 if dk is None else int(dk)),
                        f"SELECT {race} AS `race`, {sex} AS `gender`, '{column}' AS `column`, {value} AS `value`, "
                        f"COUNT(*) AS `characters` FROM `characters` WHERE `race` = {race} AND `gender` = {sex} AND "
                        f"`{column}` = {value}{kind};"))

    lines += [line for _, line in sorted(selects)]
    return "\n".join(lines) + "\n"
