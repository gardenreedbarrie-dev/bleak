r"""The Bleakhold appearance data contract in code (README.md, "Bleakhold appearance data contract").

Shared by customize (rflib/realm_customize.py), the curation, the mark and eye rows, the remap and picker-data: the
client's flag rules, the two encodings, the texture paths and the race file names. Nothing here reads a file.
"""

from __future__ import annotations

import re

# --- the client's flag rules (ComponentFlagsMatch, WoW/Common/ComponentCore/ComponentUtils.cpp) -------------------

PLAYER = 0x1
BARBER = 0x2
DEATH_KNIGHT = 0x4
HIDDEN = 0x8
DK_TOO = 0x10

CREATION = "creation"  # character creation and the customize screen (COMPONENT_SELECTION_0 / _1)
WORLD = "world"  # in the world and the barbershop (COMPONENT_SELECTION_2 / _3)
WHERE = (CREATION, WORLD)


def selectable(flags: int, where: str, death_knight: bool) -> bool:
    """Whether a row with these flags can be picked: ComponentFlagsMatch for the selection GetSelectionFromContext
    gives (creation or world, Death Knight or not)."""
    base = flags & PLAYER if where == CREATION else flags & (PLAYER | BARBER)

    if not base:
        return False

    if death_knight:
        return bool(flags & (DEATH_KNIGHT | DK_TOO)) and not flags & HIDDEN

    return not flags & (DEATH_KNIGHT | HIDDEN)


def anyone(flags: int, where: str = CREATION) -> bool:
    return selectable(flags, where, False) or selectable(flags, where, True)


# --- sections --------------------------------------------------------------------------------------------------

SKIN, FACE, FEATURES, HAIR, UNDERWEAR = 0, 1, 2, 3, 4
SECTION_NAMES = {SKIN: "skin", FACE: "face", FEATURES: "features", HAIR: "hair", UNDERWEAR: "underwear"}
SECTION_BY_NAME = {v: k for k, v in SECTION_NAMES.items()}
KEY = ("raceID", "sexID", "baseSection", "variationIndex", "colorIndex")

# --- encodings -------------------------------------------------------------------------------------------------

EYE_STRIDE = 40  # face value = base + 40 * eye
EYES = 5  # 1-3 the race's colours, 4-5 the Death Knight ones
DK_EYES = (4, 5)
DESIGNS = 4
COLOURS = 3  # colour 3 is the paint colour (no _Glow)
LOOKS = DESIGNS * COLOURS  # 12; look 0 is no mark
MAX_VALUE = 255


def look_of(design: int, colour: int) -> int:
    if not (1 <= design <= DESIGNS and 1 <= colour <= COLOURS):
        raise ValueError(f"design {design} colour {colour}: designs are 1-{DESIGNS}, colours 1-{COLOURS}")

    return COLOURS * (design - 1) + colour


def design_colour(look: int) -> tuple[int, int]:
    if not 1 <= look <= LOOKS:
        raise ValueError(f"look {look}: 1-{LOOKS}")

    return (look - 1) // COLOURS + 1, (look - 1) % COLOURS + 1


def features_value(look: int, base: int, b: int) -> int:
    if not 0 <= base < b:
        raise ValueError(f"base feature {base} of {b}")

    return look * b + base


def split_features(value: int, b: int) -> tuple[int, int]:
    """(look, base) of a features value."""
    return value // b, value % b


def face_value(base: int, eye: int) -> int:
    if not 0 <= base < EYE_STRIDE:
        raise ValueError(f"face {base}: faces must be below {EYE_STRIDE}")

    return base + EYE_STRIDE * eye


def split_face(value: int) -> tuple[int, int]:
    """(eye, base) of a face value."""
    return value // EYE_STRIDE, value % EYE_STRIDE


# --- races -----------------------------------------------------------------------------------------------------

RACE_FILES = {1: "Human", 2: "Orc", 3: "Dwarf", 4: "NightElf", 5: "Scourge", 6: "Tauren", 7: "Gnome", 8: "Troll",
              10: "BloodElf", 11: "Draenei", 15: "HighElf", 19: "Eredar"}
# The races whose package rows replace the realm's: the playable ones of 1-11. Goblin (9) keeps the realm's rows: it is
# not playable, and the package's Goblin art is not shipped. Package rows of 12-21 (Skeleton 15, Taunka 19, ...) are
# never taken.
PACKAGE_RACES = (1, 2, 3, 4, 5, 6, 7, 8, 10, 11)
TAKEN_RACES = PACKAGE_RACES
CLONES = {15: 10, 19: 11}  # High Elf from Blood Elf, Eredar from Draenei
SEXES = {0: "Male", 1: "Female"}
SEX_BY_NAME = {v: k for k, v in SEXES.items()}
DEATH_KNIGHT_CLASS = 6

# --- paths -----------------------------------------------------------------------------------------------------

ASCENSION = "Character\\Ascension\\"
REBUILT = ASCENSION + "Rebuilt\\"
MARKS = "Character\\BleakholdMarks\\"
EYES_FOLDER = "Character\\BleakholdEyes\\"
SKINS_FOLDER = "Character\\BleakholdSkins\\"
MAX_NAME_BYTES = 259
KEY_RE = re.compile(r"[A-Za-z0-9]{1,48}")
HASH_DIGITS = 10


def normal(name: str) -> str:
    return name.replace("/", "\\")


def ascension_name(original: str) -> str:
    return ASCENSION + normal(original)


def rebuilt_name(digest: str, original: str) -> str:
    return f"{REBUILT}{digest[:HASH_DIGITS]}\\{normal(original)}"


def mark_name(race_file: str, sex: int, design_key: str, colour_key: str) -> str:
    return f"{MARKS}{race_file}\\{SEXES[sex]}\\{design_key}_{colour_key}.blp"


def glow_name(texture: str) -> str:
    """The _Glow file the exe looks for next to a texture."""
    if not texture.lower().endswith(".blp"):
        raise ValueError(f"{texture}: not a .blp name")

    return texture[:-4] + "_Glow.blp"


def eye_name(race_file: str, sex: int, colour_key: str) -> str:
    return f"{EYES_FOLDER}{race_file}\\{SEXES[sex]}\\Eye_{colour_key}.blp"


def is_ours(name: str) -> bool:
    """A mark or eye texture (never recoloured by skins)."""
    lower = normal(name).lower()
    return lower.startswith(MARKS.lower()) or lower.startswith(EYES_FOLDER.lower())


def original_name(name: str) -> str:
    r"""The package's or the stock path behind a row's texture name: without Character\BleakholdSkins\<race>\<hash>\,
    Character\Ascension\Rebuilt\<hash>\ and Character\Ascension\ (in that order, as often as they nest)."""
    current = normal(name)

    for _ in range(8):
        lower = current.lower()

        if lower.startswith(SKINS_FOLDER.lower()):
            rest = current[len(SKINS_FOLDER):].split("\\", 2)

            if len(rest) == 3 and re.fullmatch(r"[0-9a-fA-F]+", rest[1]):
                current = rest[2]
                continue

        if lower.startswith(REBUILT.lower()):
            rest = current[len(REBUILT):].split("\\", 1)

            if len(rest) == 2 and re.fullmatch(r"[0-9a-fA-F]+", rest[0]):
                current = rest[1]
                continue

        if lower.startswith(ASCENSION.lower()):
            current = current[len(ASCENSION):]
            continue

        break

    return current


def name_key(name: str) -> str:
    """How the client compares texture names: case and slash direction ignored."""
    return normal(name).casefold()


# --- section sizes and the paste rule (PasteToSection, PasteFromSkin) ------------------------------------------

# s_sectionInfoRaw at the 512 layout: x, y, width, height
SECTION_RECTS = {
    "arm upper": (0, 0, 256, 128), "arm lower": (0, 128, 256, 128), "hand": (0, 256, 256, 64),
    "torso upper": (256, 0, 256, 128), "torso lower": (256, 128, 256, 64), "leg upper": (256, 192, 256, 128),
    "leg lower": (256, 320, 256, 128), "foot": (256, 448, 256, 64), "face upper": (0, 320, 256, 64),
    "face lower": (0, 384, 256, 128),
}
LEVELS = (7, 8, 9)  # componentTextureLevel: 7 (128), 8 (256, the default) and 9 (512)

# Where each texture of a row is pasted: (section, slot) -> target ("whole" is the full skin texture).
TARGETS = {
    (SKIN, 0): "whole",
    (FACE, 0): "face lower", (FACE, 1): "face upper",
    (FEATURES, 0): "face lower", (FEATURES, 1): "face upper",
    (HAIR, 1): "face lower", (HAIR, 2): "face upper",
    (UNDERWEAR, 0): "leg upper", (UNDERWEAR, 1): "torso upper",
}


def target_size(target: str, level: int) -> tuple[int, int]:
    shift = 9 - level
    width, height = (512, 512) if target == "whole" else SECTION_RECTS[target][2:]
    return width >> shift, height >> shift


def paste_problem(width: int, height: int, mips: int, target: str) -> str | None:
    """Why the client would hang (or read past the texture) pasting a texture of this size into target at some level
    7-9, or None. Smaller in both directions: scaled. Otherwise width = target width * 2^k and height = target height
    * 2^k with the same k, and at least k + 1 mip levels."""
    for level in LEVELS:
        tw, th = target_size(target, level)

        if width < tw and height < th:
            continue

        k, w = 0, width

        while w > tw and w % 2 == 0:
            w //= 2
            k += 1

        if w != tw:
            return f"{width}x{height} cannot be pasted into {target} ({tw}x{th} at level {level}): the width is not " \
                   f"{tw} x 2^k, so the client loops for ever"

        if height != th << k:
            return f"{width}x{height} cannot be pasted into {target} ({tw}x{th} at level {level}): the height is not " \
                   f"{th} x {1 << k}"

        if mips < k + 1:
            return f"{width}x{height} with {mips} mip level(s) cannot be pasted into {target} at level {level}: it " \
                   f"needs {k + 1}"

    return None
