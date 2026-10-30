"""customize/curation.json: what customize takes from the package and what it hides (README.md, "Bleakhold appearance
data contract").

Hiding sets flag 0x8 (appearance.HIDDEN) on the rows; rows and option numbers stay. The steps, in the order customize
runs them:

1. hide(): the "hidden" entries, on the package races (before the clones, so a broken Blood Elf row is hidden for the
   High Elf too);
2. the clones 15 <- 10 and 19 <- 11 copy every row with its flags (rflib/realm_customize.py);
3. filter_races(): the "race_filters" of every race, clones included (fel Draenei skins go from 11 and stay on 19; the
   High Elf keeps only its keep_skins).

A section-2 (features) row is never hidden (the client counts features by position, so a hole loses the last value),
and neither is a Death Knight skin by a filter (they have their own ramp in skins.json).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from . import appearance as ap
from .dbc import DbcTable

GROUPS = ("plain", "marked", "fel", "deathknight")  # picker group codes 1-4
GROUP_CODES = {g: i + 1 for i, g in enumerate(GROUPS)}
HIDE_SECTIONS = ("skin", "face", "hair", "underwear")


class CurationError(Exception):
    pass


@dataclass
class Hidden:
    race: str
    sexes: tuple[int, ...]
    section: int
    variations: tuple[int, ...] | None  # None: every one
    colours: tuple[int, ...] | None
    reason: str


@dataclass
class RaceFilter:
    race: str
    source: str  # the race whose skin groups apply (HighElf: BloodElf)
    hide_groups: tuple[str, ...] = ()
    keep_skins: dict[int, tuple[int, ...]] | None = None  # sex -> skins kept (Death Knight skins always stay)
    reason: str = ""


@dataclass
class Curation:
    path: str
    commit: str
    package: dict
    near_duplicate_delta_e: float
    groups: dict[tuple[str, int], dict[int, str]]  # (race file, sex) -> skin colour -> group
    hidden: list[Hidden]
    filters: dict[str, RaceFilter]
    raw: dict = field(default_factory=dict)
    # hair styles and features values whose meaning the package changed, accepted: (race file, sex, "style" or
    # "feature") -> values (remap.meaning_problems() stops on every other change)
    accepted: dict[tuple[str, int, str], tuple[int, ...]] = field(default_factory=dict)

    def accepted_keys(self, race_ids: dict[str, int]) -> set[tuple[int, int, str, int]]:
        return {(race_ids[race], sex, kind, value) for (race, sex, kind), values in self.accepted.items()
                for value in values if race in race_ids}

    def group(self, race_file: str, sex: int, colour: int, flags: int) -> str:
        if flags & ap.DEATH_KNIGHT:
            return "deathknight"

        source = self.filters[race_file].source if race_file in self.filters else race_file
        return self.groups.get((source, sex), {}).get(colour, "plain")


def _ints(value, where: str, allow_all: bool = True) -> tuple[int, ...] | None:
    if allow_all and value == "*":
        return None

    if not isinstance(value, list) or not value or not all(isinstance(v, int) and not isinstance(v, bool)
                                                           and 0 <= v <= ap.MAX_VALUE for v in value):
        raise CurationError(f"{where}: give a list of numbers 0-255" + (' or "*"' if allow_all else ""))

    if len(set(value)) != len(value):
        raise CurationError(f"{where}: a number is listed twice")

    return tuple(value)


def _sexes(value, where: str) -> tuple[int, ...]:
    if value == "*":
        return (0, 1)

    if value not in ap.SEX_BY_NAME:
        raise CurationError(f"{where}: sex must be Male, Female or \"*\"")

    return (ap.SEX_BY_NAME[value],)


def _race(value, where: str) -> str:
    if value not in ap.RACE_FILES.values():
        raise CurationError(f"{where}: race {value!r} is none of {', '.join(ap.RACE_FILES.values())}")

    return value


def parse(data: dict, path: str = "curation.json") -> Curation:
    if not isinstance(data, dict):
        raise CurationError(f"{path}: must be an object")

    unknown = set(data) - {"_readme", "version", "package", "near_duplicate_delta_e", "skin_groups", "hidden",
                           "race_filters", "accepted_changes", "notes"}

    if unknown:
        raise CurationError(f"{path}: unknown keys {sorted(unknown)}")

    package = data.get("package")
    commit = package.get("commit") if isinstance(package, dict) else None

    if not isinstance(commit, str) or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise CurationError(f"{path}: package.commit must be the pinned package commit (40 lower-case hex digits)")

    delta = data.get("near_duplicate_delta_e", 2.0)

    if not isinstance(delta, (int, float)) or isinstance(delta, bool) or not 0 < delta < 50:
        raise CurationError(f"{path}: near_duplicate_delta_e must be a number above 0")

    groups: dict[tuple[str, int], dict[int, str]] = {}

    for race, sexes in (data.get("skin_groups") or {}).items():
        _race(race, f"{path}: skin_groups")

        if not isinstance(sexes, dict):
            raise CurationError(f"{path}: skin_groups.{race} must be an object of sexes")

        for sex_name, by_group in sexes.items():
            sex = _sexes(sex_name, f"{path}: skin_groups.{race}")

            if len(sex) != 1 or not isinstance(by_group, dict):
                raise CurationError(f"{path}: skin_groups.{race}.{sex_name}: give Male or Female, each an object of "
                                    "groups")

            table = groups.setdefault((race, sex[0]), {})

            for group, colours in by_group.items():
                if group not in GROUPS[:3]:
                    raise CurationError(f"{path}: skin_groups.{race}.{sex_name}: group {group!r} is none of "
                                        f"{', '.join(GROUPS[:3])} (Death Knight skins are found by their flag)")

                for colour in _ints(colours, f"{path}: skin_groups.{race}.{sex_name}.{group}", False):
                    if colour in table:
                        raise CurationError(f"{path}: skin_groups.{race}.{sex_name}: skin {colour} is in "
                                            f"{table[colour]} and {group}")

                    table[colour] = group

    hidden = []

    for i, entry in enumerate(data.get("hidden") or []):
        where = f"{path}: hidden[{i}]"

        if not isinstance(entry, dict):
            raise CurationError(f"{where}: must be an object")

        unknown = set(entry) - {"race", "sex", "section", "variations", "colours", "reason"}

        if unknown:
            raise CurationError(f"{where}: unknown keys {sorted(unknown)}")

        reason = entry.get("reason")

        if not isinstance(reason, str) or not reason.strip():
            raise CurationError(f"{where}: every hidden row needs a reason")

        section = entry.get("section")

        if section == "features":
            raise CurationError(f"{where}: features rows are never hidden (the client counts them by position, so "
                                "a hole would lose the last value)")

        if section not in HIDE_SECTIONS:
            raise CurationError(f"{where}: section must be one of {', '.join(HIDE_SECTIONS)}")

        variations = _ints(entry.get("variations", "*"), f"{where}: variations")

        if section in ("skin", "underwear") and variations not in (None, (0,)):
            raise CurationError(f"{where}: {section} rows have variation 0 only")

        hidden.append(Hidden(_race(entry.get("race"), where), _sexes(entry.get("sex", "*"), where),
                             ap.SECTION_BY_NAME[section], variations, _ints(entry.get("colours", "*"),
                                                                            f"{where}: colours"), reason))

    filters = {}

    for race, entry in (data.get("race_filters") or {}).items():
        where = f"{path}: race_filters.{race}"
        _race(race, where)

        if not isinstance(entry, dict):
            raise CurationError(f"{where}: must be an object")

        unknown = set(entry) - {"from", "hide_groups", "keep_skins", "reason", "comment"}

        if unknown:
            raise CurationError(f"{where}: unknown keys {sorted(unknown)}")

        source = entry.get("from", race)
        _race(source, f"{where}.from")
        hide_groups = entry.get("hide_groups", [])

        if not isinstance(hide_groups, list) or any(g not in GROUPS[:3] for g in hide_groups):
            raise CurationError(f"{where}: hide_groups must list groups of {', '.join(GROUPS[:3])}")

        keep = None

        if "keep_skins" in entry:
            if not isinstance(entry["keep_skins"], dict):
                raise CurationError(f"{where}: keep_skins must be an object of sexes")

            keep = {}

            for sex_name, colours in entry["keep_skins"].items():
                sex = _sexes(sex_name, f"{where}.keep_skins")

                if len(sex) != 1:
                    raise CurationError(f"{where}.keep_skins: give Male and Female")

                keep[sex[0]] = _ints(colours, f"{where}.keep_skins.{sex_name}", False)

        if (hide_groups or keep is not None) and not str(entry.get("reason") or "").strip():
            raise CurationError(f"{where}: a filter that hides skins needs a reason")

        filters[race] = RaceFilter(race, source, tuple(hide_groups), keep, str(entry.get("reason") or ""))

    accepted: dict[tuple[str, int, str], tuple[int, ...]] = {}

    for i, entry in enumerate(data.get("accepted_changes") or []):
        where = f"{path}: accepted_changes[{i}]"

        if not isinstance(entry, dict):
            raise CurationError(f"{where}: must be an object")

        unknown = set(entry) - {"race", "sex", "kind", "values", "reason"}

        if unknown:
            raise CurationError(f"{where}: unknown keys {sorted(unknown)}")

        if not str(entry.get("reason") or "").strip():
            raise CurationError(f"{where}: every accepted change needs a reason")

        kind = entry.get("kind")

        if kind not in ("style", "feature"):
            raise CurationError(f"{where}: kind must be style (a hair style) or feature (a features value)")

        race = _race(entry.get("race"), where)
        values = _ints(entry.get("values"), f"{where}: values", False)

        for sex in _sexes(entry.get("sex", "*"), where):
            key = (race, sex, kind)
            accepted[key] = tuple(sorted(set(accepted.get(key, ())) | set(values)))

    return Curation(path, commit, package, float(delta), groups, hidden, filters, data, accepted)


def load(path: str) -> Curation:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise CurationError(f"{path} is missing") from None
    except json.JSONDecodeError as e:
        raise CurationError(f"{path}: not valid JSON ({e})") from None

    return parse(data, path)


# --- applying it -----------------------------------------------------------------------------------------------


@dataclass
class HiddenRow:
    """One row customize hid, and why."""
    race: int
    sex: int
    section: int
    variation: int
    colour: int
    reason: str


def _hide(table: DbcTable, row: list[int], reason: str, out: list[HiddenRow]):
    flags = table.get(row, "flags")

    if flags & ap.HIDDEN:
        return

    table.set(row, "flags", flags | ap.HIDDEN)
    out.append(HiddenRow(table.get(row, "raceID"), table.get(row, "sexID"), table.get(row, "baseSection"),
                         table.get(row, "variationIndex"), table.get(row, "colorIndex"), reason))


def hide(cs: DbcTable, cur: Curation, race_ids: dict[str, int], races: set[int]) -> list[HiddenRow]:
    """The "hidden" entries of the races given (ids). Returns the rows hidden now."""
    out: list[HiddenRow] = []
    rules = [(race_ids[h.race], h) for h in cur.hidden if race_ids.get(h.race) in races]

    for row in cs.rows:
        race = cs.get(row, "raceID")

        for rule_race, h in rules:
            if race != rule_race or cs.get(row, "sexID") not in h.sexes or cs.get(row, "baseSection") != h.section:
                continue

            if h.variations is not None and cs.get(row, "variationIndex") not in h.variations:
                continue

            if h.colours is not None and cs.get(row, "colorIndex") not in h.colours:
                continue

            _hide(cs, row, h.reason, out)

    return out


def filter_races(cs: DbcTable, cur: Curation, race_ids: dict[str, int]) -> list[HiddenRow]:
    """The "race_filters": skins of the filter's groups, and every living skin outside keep_skins, get 0x8."""
    out: list[HiddenRow] = []
    by_id = {race_ids[name]: f for name, f in cur.filters.items() if name in race_ids}

    for row in cs.rows:
        rf = by_id.get(cs.get(row, "raceID"))

        if rf is None or cs.get(row, "baseSection") != ap.SKIN or cs.get(row, "variationIndex") != 0:
            continue

        flags = cs.get(row, "flags")

        if flags & ap.DEATH_KNIGHT or flags & ap.HIDDEN:
            continue

        sex, colour = cs.get(row, "sexID"), cs.get(row, "colorIndex")
        group = cur.group(rf.race, sex, colour, flags)

        if rf.keep_skins is not None and sex in rf.keep_skins:
            if colour not in rf.keep_skins[sex]:
                _hide(cs, row, f"{rf.race}: not in keep_skins ({rf.reason})", out)
                continue

            # a skin listed in keep_skins stays whatever its group
            continue

        if group in rf.hide_groups:
            _hide(cs, row, f"{rf.race}: {group} skin ({rf.reason})", out)

    return out


# --- near-duplicates -------------------------------------------------------------------------------------------


def delta_e(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """OKLab distance on the usual 0-100 scale (100 x the Euclidean distance)."""
    return 100.0 * math.dist(a, b)


def near_duplicates(colours: dict[int, tuple[float, float, float]], threshold: float) -> list[tuple[int, int, float]]:
    """Pairs of skins (ascending) whose colours are less than threshold apart."""
    keys = sorted(colours)
    out = []

    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            d = delta_e(colours[a], colours[b])

            if d < threshold:
                out.append((a, b, round(d, 2)))

    return out


def thin(order: list[int], targets: dict[int, tuple[float, float, float]], threshold: float) -> list[int]:
    """A subset of order (lightest first) whose neighbouring targets are at least threshold apart, keeping the first
    and, where it can, the last: the skins to suggest for a race recoloured onto a ramp."""
    if not order:
        return []

    kept = [order[0]]

    for colour in order[1:]:
        if delta_e(targets[kept[-1]], targets[colour]) >= threshold:
            kept.append(colour)

    if order[-1] not in kept and len(kept) > 1 and delta_e(targets[kept[-2]], targets[order[-1]]) >= threshold:
        kept[-1] = order[-1]

    return kept
