r"""The models the client loads must fit the tables (README.md, "Bleakhold appearance data contract").

For every race and sex, the model is the one ChrRaces' display id names (CreatureDisplayInfo -> CreatureModelData,
.mdx read as .m2, the client's rule), as the client finds it in a pack combination (the archive that sorts last). That
model must have

- every geoset a row a player or Death Knight can pick needs: each hair style's CharHairGeosets geoset, each
  features value's five CharacterFacialHairStyles geosets (groups 1, 3, 2, 16 and 17, SetBeardStyle), and 1703 when the
  race and sex has eye rows (a face row with a third texture);
- every .anim file it reads (a sequence without the in-file flag 0x20 and not an alias, 0x40:
  <model><id:04d>-<variation:02d>.anim): the copy the client finds must be the one of the model's own archive, byte
  for byte. An .anim of another model makes the client read past its bones, a crash rather than a glitch.

M2 version 264 (3.3.5a) only: the header, the sequences (64 bytes each), the textures and the .skin's submeshes
(48 bytes each) are read, nothing else.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Callable

from . import appearance as ap
from .dbc import DbcTable

M2_VERSION = 264
SEQUENCE_SIZE = 64
SUBMESH_SIZE = 48
IN_FILE = 0x20
ALIAS = 0x40
EYE_GEOSET = 1703
# CharacterFacialHairStyles geoset[i] -> geoset group (SetBeardStyle)
FACIAL_GROUPS = (100, 300, 200, 1600, 1700)


class ModelError(Exception):
    pass


@dataclass
class M2Info:
    version: int
    sequences: list[tuple[int, int, int]]  # (id, variation, flags)
    textures: list[tuple[int, str]]  # (type, file name for type 0)
    skin_profiles: int


def _array(data: bytes, offset: int, where: str) -> tuple[int, int]:
    if offset + 8 > len(data):
        raise ModelError(f"{where}: cut off")

    return struct.unpack_from("<II", data, offset)


def parse_m2(data: bytes, where: str) -> M2Info:
    if len(data) < 0x130 or data[:4] != b"MD20":
        raise ModelError(f"{where}: not an M2 (MD20) file")

    version = struct.unpack_from("<I", data, 4)[0]

    if version != M2_VERSION:
        raise ModelError(f"{where}: M2 version {version}, the 3.3.5a client reads {M2_VERSION}")

    count, offset = _array(data, 28, where)

    if offset + count * SEQUENCE_SIZE > len(data):
        raise ModelError(f"{where}: its sequences run past the end of the file")

    sequences = []

    for i in range(count):
        sid, variation, _, _, flags = struct.unpack_from("<HHIfI", data, offset + SEQUENCE_SIZE * i)
        sequences.append((sid, variation, flags))

    count, offset = _array(data, 80, where)

    if offset + 16 * count > len(data):
        raise ModelError(f"{where}: its textures run past the end of the file")

    textures = []

    for i in range(count):
        kind, _, n, at = struct.unpack_from("<IIII", data, offset + 16 * i)
        name = data[at:at + n].split(b"\0")[0].decode("latin-1") if kind == 0 and n and at + n <= len(data) else ""
        textures.append((kind, name))

    return M2Info(version, sequences, textures, struct.unpack_from("<I", data, 68)[0])


def parse_skin(data: bytes, where: str) -> set[int]:
    """The geoset (submesh) ids of a .skin file."""
    if len(data) < 48 or data[:4] != b"SKIN":
        raise ModelError(f"{where}: not a .skin file")

    count, offset = _array(data, 28, where)

    if offset + count * SUBMESH_SIZE > len(data):
        raise ModelError(f"{where}: its submeshes run past the end of the file")

    return {struct.unpack_from("<H", data, offset + SUBMESH_SIZE * i)[0] for i in range(count)}


def stem(model: str) -> str:
    """The model's path without .m2/.mdx."""
    name = ap.normal(model)
    lower = name.lower()

    for ext in (".m2", ".mdx", ".mdl"):
        if lower.endswith(ext):
            return name[:-len(ext)]

    return name


def m2_name(model: str) -> str:
    return stem(model) + ".m2"


def skin_name(model: str, profile: int = 0) -> str:
    return f"{stem(model)}{profile:02d}.skin"


def anim_names(model: str, info: M2Info) -> list[str]:
    return sorted({f"{stem(model)}{sid:04d}-{variation:02d}.anim" for sid, variation, flags in info.sequences
                   if not flags & (IN_FILE | ALIAS)})


def own_textures(info: M2Info) -> list[str]:
    """The texture files a model names itself (type 0): they keep their stock names and ship with the model."""
    return sorted({name for kind, name in info.textures if kind == 0 and name})


def model_paths(races: DbcTable, displays: DbcTable, models: DbcTable, race_ids) -> dict[tuple[int, int], str]:
    """(race, sex) -> the model path its ChrRaces display id names."""
    display_by_id, model_by_id = displays.by_id(), models.by_id()
    out = {}

    for race, row in races.by_id().items():
        if race not in race_ids:
            continue

        for sex, column in ((0, "maleDisplayID"), (1, "femaleDisplayID")):
            display = display_by_id.get(races.get(row, column))
            model = model_by_id.get(displays.get(display, "modelID")) if display is not None else None

            if model is not None:
                out[(race, sex)] = m2_name(models.get_str(model, "modelName"))

    return out


def required(cs: DbcTable, hair: DbcTable, facial: DbcTable, race: int, sex: int) -> dict[int, str]:
    """geoset id -> why, for the rows of one race and sex a player or Death Knight can pick."""
    out: dict[int, str] = {}
    styles: set[int] = set()
    eyes = False

    for row in cs.rows:
        if cs.get(row, "raceID") != race or cs.get(row, "sexID") != sex:
            continue

        if not ap.anyone(cs.get(row, "flags"), ap.CREATION) and not ap.anyone(cs.get(row, "flags"), ap.WORLD):
            continue

        section = cs.get(row, "baseSection")

        if section == ap.HAIR:
            styles.add(cs.get(row, "variationIndex"))
        elif section == ap.FACE and cs.get_str(row, "textureName[2]"):
            eyes = True

    for row in hair.rows:
        if hair.get(row, "raceID") == race and hair.get(row, "sexID") == sex and hair.get(row, "variationID") in styles:
            geoset = hair.get(row, "geosetID")

            if geoset:
                out.setdefault(geoset, f"hair style {hair.get(row, 'variationID')}")

    for row in facial.rows:
        if facial.get(row, "raceID") != race or facial.get(row, "sexID") != sex:
            continue

        for i, group in enumerate(FACIAL_GROUPS):
            value = facial.get(row, f"geoset[{i}]")

            if 0 < value < 100:
                out.setdefault(group + value, f"features value {facial.get(row, 'variationID')}")

    if eyes:
        out[EYE_GEOSET] = "eye rows"

    return out


@dataclass
class ModelCheck:
    race: int
    sex: int
    model: str
    archive: str = ""
    missing_geosets: dict[int, str] = field(default_factory=dict)
    bad_anims: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


# top(name) -> (archive name, bytes) of the copy the client reads in one pack combination, or None
Resolver = Callable[[str], "tuple[str, bytes] | None"]
# own(archive name, file name) -> bytes of that archive's copy, or None
OwnCopy = Callable[[str, str], "bytes | None"]


def check_model(race: int, sex: int, model: str, need: dict[int, str], top: Resolver, own: OwnCopy) -> ModelCheck:
    result = ModelCheck(race, sex, model)
    found = top(m2_name(model))

    if found is None:
        result.problems.append(f"{m2_name(model)} is in no archive")
        return result

    result.archive, data = found

    try:
        info = parse_m2(data, f"{result.archive}: {m2_name(model)}")
        skin = top(skin_name(model))

        if skin is None:
            result.problems.append(f"{skin_name(model)} is in no archive")
            return result

        geosets = parse_skin(skin[1], f"{skin[0]}: {skin_name(model)}")
    except ModelError as e:
        result.problems.append(str(e))
        return result

    if skin[0] != result.archive and own(result.archive, skin_name(model)) not in (None, skin[1]):
        result.problems.append(f"{skin_name(model)} comes from {skin[0]}, not from the model's {result.archive}")

    result.missing_geosets = {g: why for g, why in sorted(need.items()) if g not in geosets}

    for name in anim_names(model, info):
        copy = top(name)
        mine = own(result.archive, name)

        if copy is None:
            result.bad_anims.append(f"{name} (in no archive)")
        elif mine is None:
            result.bad_anims.append(f"{name} (not in the model's {result.archive}; {copy[0]} has one)")
        elif hashlib.sha1(copy[1]).digest() != hashlib.sha1(mine).digest():
            result.bad_anims.append(f"{name} ({copy[0]}'s copy is another model's)")

    return result


def describe(check: ModelCheck) -> list[str]:
    where = f"race {check.race} {ap.SEXES[check.sex]} ({check.model}, from {check.archive or '-'})"
    out = [f"{where}: {p}" for p in check.problems]

    if check.missing_geosets:
        items = ", ".join(f"{g} ({why})" for g, why in list(check.missing_geosets.items())[:8])
        out.append(f"{where}: no geoset {items}")

    if check.bad_anims:
        out.append(f"{where}: {len(check.bad_anims)} .anim file(s) would not be the model's: "
                   f"{'; '.join(check.bad_anims[:4])}")

    return out
