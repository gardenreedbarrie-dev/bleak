"""Race mask rules: which masks gain a new race's bit.

The client and AzerothCore test 1 << (race - 1) against these masks (SpellTableLookupInfo, SpellTableMatchRaceClass,
FactionHasReputationForPlayer, TalentInfo, DanceStudio; RaceMgr on the server); a mask of 0 means every race and is
left alone. HelmetGeosetVisData is the exception: CCharacterComponent::AddHelm tests 1 << race.

A new race normally gets its bit wherever its template race has one (Blood Elf for High Elf, Draenei for Eredar), so
it keeps the template's language and class skills (and its racials, unless races.json drops the template's racial
skill lines: forge.is_dropped_row). When the new race sits on the other faction than its template, masks that list
exactly every playable race of one faction (Language: Common, faction mounts, faction-wide spells) follow the new
race's faction instead: High Elf gets Common, not Orcish. Masks that list every playable race get the bit in any case.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import RaceConfig
from .dbc import DbcTable, to_signed

# Stock 3.3.5a playable races, used only when FactionTemplate/FactionGroup cannot tell the faction.
STOCK_ALLIANCE = (1, 3, 4, 7, 11)
STOCK_HORDE = (2, 5, 6, 8, 10)


@dataclass
class FactionMasks:
    alliance: int = 0
    horde: int = 0
    race_faction: dict[int, str] = field(default_factory=dict)
    source: str = ""

    @property
    def playable(self) -> int:
        return self.alliance | self.horde

    def of(self, faction: str) -> int:
        return self.alliance if faction == "alliance" else self.horde


def race_bit(race: int) -> int:
    return 1 << (race - 1)


def faction_of_template(faction_template_id: int, faction_templates: DbcTable | None, faction_groups: DbcTable | None) -> str | None:
    """The faction a FactionTemplate puts a race in, the way CCharacterCreation::Initialize decides it."""
    if faction_templates is None or faction_groups is None:
        return None

    template = faction_templates.by_id().get(faction_template_id)

    if template is None:
        return None

    group_mask = faction_templates.get(template, "factionGroup")
    found = None

    for group in faction_groups.rows:
        mask_id = faction_groups.get(group, "maskID")

        if not mask_id or mask_id >= 32 or not (1 << mask_id) & group_mask:
            continue

        internal = faction_groups.get_str(group, "internalName").lower()

        if internal in ("alliance", "horde"):
            if found and found != internal:
                return "both"
            found = internal

    return found


def compute_faction_masks(chr_races: DbcTable, faction_templates: DbcTable | None, faction_groups: DbcTable | None) -> FactionMasks:
    """Alliance and Horde masks of the playable races already in ChrRaces (before any new race is added)."""
    masks = FactionMasks()
    sources = set()

    for row in chr_races.rows:
        race = to_signed(chr_races.get(row, "id"))

        if chr_races.get(row, "flags") & 0x1 or not 1 <= race <= 32:
            continue

        faction = faction_of_template(chr_races.get(row, "factionID"), faction_templates, faction_groups)

        if faction in ("alliance", "horde"):
            sources.add("FactionTemplate/FactionGroup")
        else:
            language = chr_races.get(row, "baseLanguage")
            faction = {7: "alliance", 1: "horde"}.get(language)
            sources.add("ChrRaces.BaseLanguage")

        if faction == "alliance":
            masks.alliance |= race_bit(race)
        elif faction == "horde":
            masks.horde |= race_bit(race)

        if faction:
            masks.race_faction[race] = faction

    if not masks.alliance or not masks.horde:
        masks.alliance = sum(race_bit(r) for r in STOCK_ALLIANCE)
        masks.horde = sum(race_bit(r) for r in STOCK_HORDE)
        masks.race_faction = {**{r: "alliance" for r in STOCK_ALLIANCE}, **{r: "horde" for r in STOCK_HORDE}}
        sources = {"stock 3.3.5a defaults"}

    masks.source = ", ".join(sorted(sources))
    return masks


def wants_bit(mask: int, race: RaceConfig, masks: FactionMasks, source_race: int, faction_wide: bool) -> bool:
    """Should the new race's bit be added to this 1 << (race - 1) mask? mask is the raw unsigned value."""
    if mask == 0 or mask == 0xFFFFFFFF or mask & race.bit:
        return False

    playable = mask & masks.playable

    if faction_wide and playable:
        if playable == masks.playable:
            return True

        if playable == masks.alliance:
            return race.faction == "alliance"

        if playable == masks.horde:
            return race.faction == "horde"

    return bool(mask & race_bit(source_race))


def sql_condition(column: str, race: RaceConfig, masks: FactionMasks, source_race: int, faction_wide: bool) -> str:
    """The same rule as wants_bit, as a MySQL condition on an unsigned mask column (0 means every race)."""
    source = race_bit(source_race)
    playable = masks.playable
    own = masks.of(race.faction)
    other = masks.of("horde" if race.faction == "alliance" else "alliance")
    base = f"`{column}` <> 0 AND (`{column}` & {race.bit}) = 0"

    if not faction_wide:
        return f"{base} AND (`{column}` & {source}) <> 0"

    return (f"{base} AND ((`{column}` & {playable}) IN ({playable}, {own})"
            f" OR ((`{column}` & {playable}) NOT IN (0, {playable}, {own}, {other}) AND (`{column}` & {source}) <> 0))")
