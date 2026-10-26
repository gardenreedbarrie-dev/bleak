"""Synthetic 3.3.5a-shaped DBCs for the tests (no Blizzard data: every value here is made up).

The tables follow the client's layouts (rflib/schemas.py, checked against WoW/Source/DB/Rec) and the structure that
matters to RaceForge: races 1-21 with the stock playable set (Alliance 1, 3, 4, 7, 11; Horde 2, 5, 6, 8, 10; 9 and
12-21 not playable), faction templates that resolve through FactionGroup like the client does, CharSections sorted
by race/sex/section/variation/color, faction-wide and race-specific race masks, and so on. The ids, names and paths
are invented.

The files are packed here with struct directly instead of rflib.dbc, so the tests check RaceForge's reader against
an independent writer.
"""

from __future__ import annotations

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from rflib.schemas import SCHEMAS  # noqa: E402

ALLIANCE = (1, 3, 4, 7, 11)
HORDE = (2, 5, 6, 8, 10)
NPC = (9,) + tuple(range(12, 22))

ALLIANCE_MASK = sum(1 << (r - 1) for r in ALLIANCE)  # 1101
HORDE_MASK = sum(1 << (r - 1) for r in HORDE)  # 690
PLAYABLE_MASK = ALLIANCE_MASK | HORDE_MASK  # 1791

FILE_STRINGS = {
    1: "Human", 2: "Orc", 3: "Dwarf", 4: "NightElf", 5: "Scourge", 6: "Tauren", 7: "Gnome", 8: "Troll", 9: "Goblin",
    10: "BloodElf", 11: "Draenei", 12: "FelOrc", 13: "Naga", 14: "Broken", 15: "Skeleton", 16: "Vrykul", 17: "Tuskarr",
    18: "ForestTroll", 19: "Taunka", 20: "NorthSkeleton", 21: "IceTroll",
}
PREFIXES = {r: FILE_STRINGS[r][:2] for r in FILE_STRINGS}
PREFIXES.update({10: "Be", 11: "Dr", 13: "Na", 18: "Ft", 20: "Ns"})

CLASSES = {
    1: (1, 2, 4, 5, 6, 8, 9),
    2: (1, 3, 4, 6, 7, 9),
    3: (1, 2, 3, 4, 5, 6),
    4: (1, 3, 4, 5, 6, 11),
    5: (1, 4, 5, 6, 8, 9),
    6: (1, 3, 6, 7, 11),
    7: (1, 4, 6, 8, 9),
    8: (1, 3, 4, 5, 6, 7, 8),
    10: (2, 3, 4, 5, 6, 8, 9),
    11: (1, 2, 3, 5, 6, 7, 8),
}

# Skill and spell ids the validation knows (Language: Common 98, Language: Orcish 109); the rest are invented.
SKILL_COMMON = 98
SKILL_ORCISH = 109
SKILL_THALASSIAN = 137
SKILL_DRAENEI_LANGUAGE = 759
SKILL_RACIAL_BLOODELF = 756
SKILL_RACIAL_DRAENEI = 760
SKILL_RIDING = 762
SKILL_SWORDS = 43
SKILL_CROSSBOWS = 226
SKILL_NPC_ONLY = 900
SKILL_EVERYTHING = 901
SKILL_SHAMAN = 375


def faction_template_id(race: int) -> int:
    return 5000 + race


def display_ids(race: int) -> tuple[int, int]:
    return 7000 + 2 * race, 7001 + 2 * race


def is_playable(race: int) -> bool:
    return race in ALLIANCE or race in HORDE


class Packer:
    """Rows as dicts of column name -> value; strings are given as str and placed in the string block."""

    def __init__(self, name: str):
        self.name = name
        self.filename, self.num_columns, self.row_size, self.generated_id, self.columns = SCHEMAS[name]
        self.rows: list[dict] = []
        self.strings = bytearray(b"\0")
        self.offsets: dict[str, int] = {"": 0}

    def string(self, text: str) -> int:
        if text not in self.offsets:
            self.offsets[text] = len(self.strings)
            self.strings += text.encode("utf-8") + b"\0"
        return self.offsets[text]

    def add(self, **values):
        self.rows.append(values)

    def pack(self) -> bytes:
        out = bytearray(struct.pack("<4sIIII", b"WDBC", len(self.rows), self.num_columns, self.row_size, 0))
        row_data = bytearray()

        for row in self.rows:
            unknown = set(row) - {c[0] for c in self.columns}

            if unknown:
                raise KeyError(f"{self.name}: unknown columns {unknown}")

            for name, kind, size in self.columns:
                value = row.get(name, 0)

                if kind in ("str", "locstr"):
                    value = self.string(value or "")
                elif kind == "float":
                    value = struct.unpack("<I", struct.pack("<f", value))[0]

                row_data += struct.pack("<B" if size == 1 else "<I", value & (0xFF if size == 1 else 0xFFFFFFFF))

        out += row_data + self.strings
        struct.pack_into("<I", out, 16, len(self.strings))
        return bytes(out)


def loc(name: str, slot0: str, slots: dict[int, str] | None = None, flags: int = 0xFF01FE) -> dict:
    values = {f"{name}[0]": slot0, f"{name}_flags": flags}

    for slot, text in (slots or {}).items():
        values[f"{name}[{slot}]"] = text

    return values


def build_tables() -> dict[str, bytes]:
    tables = {}

    # --- factions ---
    groups = Packer("FactionGroup")
    for gid, mask_id, internal in ((1, 0, "Player"), (2, 1, "Alliance"), (3, 2, "Horde"), (4, 3, "Monster")):
        groups.add(id=gid, maskID=mask_id, internalName=internal, **loc("name", internal))
    tables["FactionGroup"] = groups.pack()

    templates = Packer("FactionTemplate")
    for race in range(1, 22):
        group = 1 | 2 if race in ALLIANCE else 1 | 4 if race in HORDE else 8
        templates.add(id=faction_template_id(race), faction=100 + race, factionGroup=group, friendGroup=group & 6, enemyGroup=6 & ~group)
    tables["FactionTemplate"] = templates.pack()

    # --- races ---
    races = Packer("ChrRaces")
    for race in range(1, 22):
        male, female = display_ids(race)
        playable = is_playable(race)
        values = dict(
            id=race, flags=0xC if playable else 0x1 | 0x4, factionID=faction_template_id(race), explorationSoundID=100 + race,
            maleDisplayID=male, femaleDisplayID=female, clientPrefix=PREFIXES[race],
            baseLanguage=7 if race in ALLIANCE else 1 if race in HORDE else 0, creatureType=7, resSicknessSpellID=15007,
            splashSoundID=200 + race, clientFileString=FILE_STRINGS[race], cinematicSequenceID=300 + race if playable else 0,
            alliance=0 if race in ALLIANCE else 1 if race in HORDE else 2, requiredExpansion=1 if race in (10, 11) else 0,
            **{"facialHairCustomization[0]": "NORMAL", "facialHairCustomization[1]": "HORNS" if race == 11 else "NORMAL", "hairCustomization": "NORMAL"},
            **loc("name", f"Synthetic {FILE_STRINGS[race]}", {3: f"Synthetisch {FILE_STRINGS[race]}"}),
        )

        if race == 10:
            # A gendered name in one locale, as German has: the new race must not inherit it.
            values.update(loc("nameFemale", "", {3: "Synthetische Blutelfe"}))
            values.update(loc("nameMale", "", {3: "Synthetischer Blutelf"}))

        races.add(**values)
    tables["ChrRaces"] = races.pack()

    classes = Packer("ChrClasses")
    for class_id in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11):
        classes.add(id=class_id, filename=f"CLASS{class_id}", **loc("name", f"Class {class_id}"))
    tables["ChrClasses"] = classes.pack()

    base = Packer("CharBaseInfo")
    for race, class_list in CLASSES.items():
        for class_id in class_list:
            base.add(raceID=race, classID=class_id)
    tables["CharBaseInfo"] = base.pack()

    # --- displays ---
    displays = Packer("CreatureDisplayInfo")
    models = Packer("CreatureModelData")
    for race in range(1, 22):
        for sex, display in enumerate(display_ids(race)):
            model = 8000 + 2 * race + sex
            displays.add(id=display, modelID=model, creatureModelScale=1.0, creatureModelAlpha=255)
            models.add(id=model, modelName=f"Character\\{FILE_STRINGS[race]}\\{('Male', 'Female')[sex]}\\{FILE_STRINGS[race]}{('Male', 'Female')[sex]}.mdx")
    tables["CreatureDisplayInfo"] = displays.pack()
    tables["CreatureModelData"] = models.pack()

    # --- start outfits and item displays ---
    outfits = Packer("CharStartOutfit")
    item_displays = Packer("ItemDisplayInfo")
    seen_displays = set()
    outfit_id = 1
    for race, class_list in CLASSES.items():
        for class_id in class_list:
            for sex in (0, 1):
                values = {"id": outfit_id, "raceID": race, "classID": class_id, "sexID": sex, "outfitID": 0}

                for slot in range(24):
                    if slot < 4:
                        item = 20000 + race * 100 + class_id * 10 + slot
                        display = 30000 + race * 10 + slot
                        values[f"itemID[{slot}]"] = item
                        values[f"displayItemID[{slot}]"] = display
                        values[f"inventoryType[{slot}]"] = (4, 7, 8, 21)[slot]

                        if display not in seen_displays:
                            seen_displays.add(display)
                            item_displays.add(id=display, **{"modelName[0]": f"Synthetic{display}.mdx"})
                    else:
                        values[f"itemID[{slot}]"] = -1
                        values[f"displayItemID[{slot}]"] = -1
                        values[f"inventoryType[{slot}]"] = -1

                outfits.add(**values)
                outfit_id += 1
    tables["CharStartOutfit"] = outfits.pack()
    tables["ItemDisplayInfo"] = item_displays.pack()

    # --- appearance ---
    sections = Packer("CharSections")
    hair = Packer("CharHairGeosets")
    facial = Packer("CharacterFacialHairStyles")
    section_id = hair_id = 1
    layout = {0: (1, 4), 1: (3, 4), 2: (3, 3), 3: (4, 3), 4: (1, 4)}  # section -> (variations, colors)
    for race in range(1, 22):
        name = FILE_STRINGS[race]

        for sex in (0, 1):
            sex_name = ("Male", "Female")[sex]

            for section, (variations, colors) in layout.items():
                for variation in range(variations):
                    for color in range(colors):
                        # The last skin color is a Death Knight one (flags 0x4 | 0x1).
                        flags = 0x5 if section == 0 and color == colors - 1 else 0x1
                        textures = [f"Character\\{name}\\{sex_name}\\{name}{sex_name}S{section}V{variation:02}C{color:02}_{t}.blp" if t < (2 if section in (0, 3) else 1) else "" for t in range(3)]
                        sections.add(id=section_id, raceID=race, sexID=sex, baseSection=section, flags=flags, variationIndex=variation, colorIndex=color,
                                     **{f"textureName[{t}]": textures[t] for t in range(3)})
                        section_id += 1

            for variation in range(4):
                hair.add(id=hair_id, raceID=race, sexID=sex, variationID=variation, geosetID=variation + 1 if variation else 0, showscalp=1 if variation == 0 else 0)
                hair_id += 1

            for variation in range(3):
                facial.add(raceID=race, sexID=sex, variationID=variation, **{f"geoset[{g}]": (variation + g) % 3 for g in range(5)})
    tables["CharSections"] = sections.pack()
    tables["CharHairGeosets"] = hair.pack()
    tables["CharacterFacialHairStyles"] = facial.pack()

    names = Packer("NameGen")
    barber = Packer("BarberShopStyle")
    emotes = Packer("EmotesTextSound")
    vocal = Packer("VocalUISounds")
    name_id = barber_id = emote_id = vocal_id = 1
    for race in sorted(CLASSES):
        for sex in (0, 1):
            for n in range(5):
                names.add(id=name_id, name=f"{FILE_STRINGS[race][:3]}{'mf'[sex]}{n}", raceID=race, sex=sex)
                name_id += 1

            for style_type, count in ((0, 4), (2, 3), (3, 2)):
                for data in range(count):
                    barber.add(id=barber_id, type=style_type, costModifier=1.0, race=race, sex=sex, data=data,
                               **loc("displayName", f"Style {style_type}-{data}"), **loc("description", ""))
                    barber_id += 1

            for emote in range(1, 6):
                emotes.add(id=emote_id, emotesTextID=emote, raceID=race, sexID=sex, soundID=10000 + race * 100 + emote * 2 + sex)
                emote_id += 1

        for enum in range(5):
            vocal.add(id=vocal_id, vocalUienum=enum, raceID=race, **{"normalSoundID[0]": 11000 + race * 10 + enum, "normalSoundID[1]": 11500 + race * 10 + enum})
            vocal_id += 1
    tables["NameGen"] = names.pack()
    tables["BarberShopStyle"] = barber.pack()
    tables["EmotesTextSound"] = emotes.pack()
    tables["VocalUISounds"] = vocal.pack()

    filters = Packer("SoundFilter")
    for i, race in enumerate(sorted(CLASSES)):
        filters.add(id=i + 1, name=f"Death Knight {FILE_STRINGS[race]} Male")
    tables["SoundFilter"] = filters.pack()

    # --- race masks ---
    skills = Packer("SkillRaceClassInfo")
    for i, (skill, mask, class_mask) in enumerate((
        (SKILL_COMMON, ALLIANCE_MASK, 0),
        (SKILL_ORCISH, HORDE_MASK, 0),
        (SKILL_THALASSIAN, 1 << 9, 0),
        (SKILL_DRAENEI_LANGUAGE, 1 << 10, 0),
        (SKILL_RACIAL_BLOODELF, 1 << 9, 0),
        (SKILL_RACIAL_DRAENEI, 1 << 10, 0),
        (SKILL_RIDING, 0, 0),
        (SKILL_SWORDS, PLAYABLE_MASK, 0x1 | 0x2),
        (SKILL_CROSSBOWS, (1 << 10) | (1 << 1), 0x1),
        (SKILL_NPC_ONLY, (1 << 11) | (1 << 12), 0),
        (SKILL_EVERYTHING, 0xFFFFFFFF, 0),
        (SKILL_SHAMAN, (1 << 1) | (1 << 5) | (1 << 7) | (1 << 10), 1 << 6),
    )):
        skills.add(id=i + 1, skillID=skill, raceMask=mask, classMask=class_mask, minLevel=1)
    tables["SkillRaceClassInfo"] = skills.pack()

    abilities = Packer("SkillLineAbility")
    for i, (skill, spell, mask, exclude) in enumerate((
        (SKILL_COMMON, 668, ALLIANCE_MASK, 0),
        (SKILL_ORCISH, 669, HORDE_MASK, 0),
        (SKILL_RACIAL_BLOODELF, 28730, 1 << 9, 0),
        (SKILL_RACIAL_DRAENEI, 28880, 1 << 10, 0),
        (SKILL_SHAMAN, 32182, ALLIANCE_MASK, 0),  # an Alliance-wide spell
        (SKILL_SHAMAN, 2825, HORDE_MASK, 0),  # its Horde-wide counterpart
        (SKILL_SHAMAN, 50000, HORDE_MASK, 1),  # every race except the Horde (excludeRace inverts the mask)
        (SKILL_SWORDS, 50001, 0, 0),
    )):
        abilities.add(id=i + 1, skillLine=skill, spell=spell, raceMask=mask, excludeRace=exclude)
    tables["SkillLineAbility"] = abilities.pack()

    talents = Packer("TalentTab")
    for i, mask in enumerate((0, 0, PLAYABLE_MASK, 1 << 9)):
        talents.add(id=i + 1, raceMask=mask, classMask=1 << i, backgroundFile=f"Tab{i}", **loc("name", f"Tab {i}"))
    tables["TalentTab"] = talents.pack()

    dances = Packer("DanceMoves")
    for i, mask in enumerate((0, PLAYABLE_MASK, 1 << 9, 1 << 10)):
        dances.add(id=i + 1, racemask=mask, internalName=f"Move{i}", **loc("name", f"Move {i}"))
    tables["DanceMoves"] = dances.pack()

    factions = Packer("Faction")
    for fid, masks in (
        (72, (1 << 0, ALLIANCE_MASK & ~1, HORDE_MASK, 0)),  # a Human city
        (911, (1 << 9, HORDE_MASK & ~(1 << 9), ALLIANCE_MASK, 0)),  # a Blood Elf city
        (930, (1 << 10, ALLIANCE_MASK & ~(1 << 10), HORDE_MASK, 0)),  # a Draenei city
        (76, (1 << 1, HORDE_MASK & ~2, ALLIANCE_MASK, 0)),  # an Orc city
        (469, (ALLIANCE_MASK, HORDE_MASK, 0, 0)),  # the Alliance
        (67, (HORDE_MASK, ALLIANCE_MASK, 0, 0)),  # the Horde
        (1, (0, 0, 0, 0)),
    ):
        values = {f"reputationRaceMask[{i}]": m for i, m in enumerate(masks)}
        values.update({f"reputationBase[{i}]": 1000 * (i + 1) for i in range(4)})
        factions.add(id=fid, reputationIndex=fid % 100, **values, **loc("name", f"Faction {fid}"), **loc("description", ""))
    tables["Faction"] = factions.pack()

    # --- spells (racial spells: Spell.dbc rows and what they point at) ---
    spells = Packer("Spell")
    for spell_id, name, subtext in ((668, "Language Common", ""), (669, "Language Orcish", ""), (28730, "Synthetic Torrent", "Racial"),
                                    (28880, "Synthetic Gift", "Racial"), (32182, "Synthetic Alliance Spell", ""), (2825, "Synthetic Horde Spell", ""),
                                    (50000, "Synthetic Excluded", ""), (50001, "Synthetic Swords", ""), (80000, "Synthetic Last", "")):
        spells.add(id=spell_id, attributes=0x40 if subtext.endswith("Passive") else 0, castingTimeIndex=1, durationIndex=21, rangeIndex=1,
                   procChance=101, equippedItemClass=-1, spellIconID=1, schoolMask=1, **{"effect[0]": 6, "effectAura[0]": 4, "effectDieSides[0]": 1},
                   **loc("name", name, flags=0xFF01FE), **loc("nameSubtext", subtext, flags=0xFF01FE if subtext else 0xFF01FC),
                   **loc("description", f"Synthetic description {spell_id}.", flags=0xFF01FE), **loc("auraDescription", "", flags=0xFF01FC))
    tables["Spell"] = spells.pack()

    icons = Packer("SpellIcon")
    for icon_id, name in ((1, "Synthetic"), (1931, "Spell_Nature_EyeOfTheStorm"), (2016, "Spell_Nature_ElementalAbsorption"), (2158, "Spell_Arcane_StudentOfMagic"),
                          (2837, "Ability_Druid_GaleWinds")):
        icons.add(id=icon_id, textureFilename=f"Interface\\Icons\\{name}")
    tables["SpellIcon"] = icons.pack()

    visuals = Packer("SpellVisual")
    for visual_id in (1, 4279, 7370):
        visuals.add(id=visual_id, castKit=visual_id + 1, stateKit=visual_id + 2)
    tables["SpellVisual"] = visuals.pack()

    durations = Packer("SpellDuration")
    for duration_id, ms in ((1, 10000), (4, 120000), (9, 30000), (21, -1)):
        durations.add(id=duration_id, duration=ms, maxDuration=ms)
    tables["SpellDuration"] = durations.pack()

    ranges = Packer("SpellRange")
    ranges.add(id=1, **loc("displayName", "Synthetic Self"), **loc("displayNameShort", "Self"))
    tables["SpellRange"] = ranges.pack()

    cast_times = Packer("SpellCastTimes")
    cast_times.add(id=1)
    tables["SpellCastTimes"] = cast_times.pack()

    helmets = Packer("HelmetGeosetVisData")
    for i, masks in enumerate((
        (1 << 10, 0, 0, 0, 0, 0, 0),  # hides hair for Blood Elves only
        (1 << 11, 1 << 11, 0, 0, 0, 0, 0),  # Draenei only
        (0x7FFFFFFE, 0, 0, 0, 0, 0, 0),  # every race
        (1 << 1, 0, 0, 0, 0, 0, 0),  # Human only
    )):
        helmets.add(id=i + 1, **{f"hideGeoset[{g}]": m for g, m in enumerate(masks)})
    tables["HelmetGeosetVisData"] = helmets.pack()

    return tables


def write_folder(path: str, skip: tuple[str, ...] = (), lower_case_names: bool = False) -> dict[str, str]:
    """Write the synthetic tables as <path>/<Name>.dbc; returns name -> file path."""
    os.makedirs(path, exist_ok=True)
    out = {}

    for name, data in build_tables().items():
        if name in skip:
            continue

        filename = f"{name}.dbc"
        filename = filename.lower() if lower_case_names else filename
        out[name] = os.path.join(path, filename)

        with open(out[name], "wb") as f:
            f.write(data)

    return out


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "synthetic-dbc"
    print("\n".join(write_folder(target).values()))
