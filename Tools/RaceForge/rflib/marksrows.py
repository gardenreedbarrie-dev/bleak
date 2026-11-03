r"""The rows of the glowing marks (features byte) and eyes (face byte), from MarkForge's marks_manifest.json and
customize/catalogue.json (README.md, "Bleakhold appearance data contract").

- Features: value = look * B + base. For every look 1-12 and every base value, CharacterFacialHairStyles gets a row
  (geosets of the base value), and CharSections section 2 a row at every hair colour of the base row: its first two
  textures, the mark as the third, its flags. A race and sex without section-2 rows gets rows for its base values
  first (empty textures; 0x11, 0x5 or 0x8 by hair colour).
- Face: value = base + 40 * eye. Eyes 1-3 copy every face row a player (not a Death Knight) can pick at creation,
  flags without 0x10; eyes 4-5 every face row a Death Knight can pick, flags 0x5. The third texture is the sprite.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field

from . import appearance as ap
from . import blp
from .dbc import DbcTable


class MarksError(Exception):
    pass


# --- catalogue.json --------------------------------------------------------------------------------------------


@dataclass
class Entry:
    key: str
    name: str
    hex: str = ""
    glow: bool = False


@dataclass
class RaceCatalogue:
    race: str
    designs: list[Entry]
    colours: list[Entry]
    eyes: list[Entry]  # eyes 1-3

    def eye(self, eye: int, dk_eyes: list[Entry]) -> Entry:
        return self.eyes[eye - 1] if eye <= 3 else dk_eyes[eye - 4]


@dataclass
class Catalogue:
    path: str
    sha1: str
    races: dict[str, RaceCatalogue]
    dk_eyes: list[Entry]
    version: int | None = None

    def eye_names(self, race: str) -> list[str]:
        return [e.name for e in self.races[race].eyes] + [e.name for e in self.dk_eyes]


def _hex(value, where: str) -> str:
    text = str(value)

    if len(text) != 7 or text[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in text[1:]):
        raise MarksError(f"{where}: colour {value!r} is not #RRGGBB")

    return text.upper()


def _entries(value, count: int, where: str, kind: str) -> list[Entry]:
    if not isinstance(value, list) or len(value) != count:
        raise MarksError(f"{where}: needs exactly {count} {kind}")

    out = []

    for i, item in enumerate(value):
        w = f"{where}[{i}]"

        if not isinstance(item, dict) or not isinstance(item.get("key"), str) or not ap.KEY_RE.fullmatch(item["key"]):
            raise MarksError(f"{w}: needs a key of letters and digits")

        if not isinstance(item.get("name"), str) or not item["name"].strip() or '"' in item["name"] or "\\" in item["name"]:
            raise MarksError(f"{w}: needs a name (no quotes or backslashes)")

        out.append(Entry(item["key"], item["name"], _hex(item["hex"], w) if "hex" in item else "",
                         bool(item.get("glow", False))))

    if len({e.key for e in out}) != len(out):
        raise MarksError(f"{where}: a key is listed twice")

    return out


def parse_catalogue(data: dict, path: str = "catalogue.json", sha1: str = "") -> Catalogue:
    if not isinstance(data, dict) or not isinstance(data.get("races"), dict):
        raise MarksError(f"{path}: needs races")

    dk = data.get("death_knight_eyes")

    if not isinstance(dk, list) or [e.get("eye") for e in dk if isinstance(e, dict)] != list(ap.DK_EYES):
        raise MarksError(f"{path}: death_knight_eyes must hold eyes 4 and 5")

    races = {}

    for race, entry in data["races"].items():
        where = f"{path}: races.{race}"

        if race not in ap.RACE_FILES.values():
            raise MarksError(f"{where}: no such race file ({', '.join(ap.RACE_FILES.values())})")

        if not isinstance(entry, dict):
            raise MarksError(f"{where}: must be an object")

        colours = _entries(entry.get("colours"), ap.COLOURS, f"{where}.colours", "colours")

        if colours[-1].glow:
            raise MarksError(f"{where}.colours: colour 3 is the paint colour and never glows")

        races[race] = RaceCatalogue(race, _entries(entry.get("designs"), ap.DESIGNS, f"{where}.designs", "designs"),
                                    colours, _entries(entry.get("eyes"), 3, f"{where}.eyes", "eyes"))

    missing = [r for r in ap.RACE_FILES.values() if r not in races]

    if missing:
        raise MarksError(f"{path}: no entry for {', '.join(missing)}")

    return Catalogue(path, sha1, races, _entries(dk, 2, f"{path}: death_knight_eyes", "eyes"), data.get("version"))


def load_catalogue(path: str) -> Catalogue:
    try:
        with open(path, "rb") as f:
            raw = f.read()
        data = json.loads(raw.decode("utf-8"))
    except FileNotFoundError:
        raise MarksError(f"{path} is missing") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise MarksError(f"{path}: not valid JSON ({e})") from None

    return parse_catalogue(data, path, hashlib.sha1(raw).hexdigest())


# --- marks_manifest.json ---------------------------------------------------------------------------------------


@dataclass
class Look:
    look: int
    design: int
    colour: int
    texture: str
    file: str = ""  # on disk ("" for a simulated manifest)
    sha1: str = ""
    glow: str | None = None
    glow_file: str = ""
    glow_sha1: str = ""


@dataclass
class Eye:
    eye: int
    colour: str
    texture: str
    file: str = ""
    sha1: str = ""


@dataclass
class RaceSexMarks:
    race: str  # race file
    sex: int
    looks: dict[int, Look] = field(default_factory=dict)
    eyes: dict[int, Eye] = field(default_factory=dict)

    def files(self) -> list[tuple[str, str, str]]:
        """(archive name, file on disk, SHA-1) of every texture."""
        out = []

        for look in self.looks.values():
            out.append((look.texture, look.file, look.sha1))

            if look.glow:
                out.append((look.glow, look.glow_file, look.glow_sha1))

        for eye in self.eyes.values():
            out.append((eye.texture, eye.file, eye.sha1))

        return out


@dataclass
class Manifest:
    path: str
    entries: dict[tuple[str, int], RaceSexMarks]


def sha1_file(path: str) -> str:
    digest = hashlib.sha1()

    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _file(base: str, rel, where: str) -> str:
    if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel or ".." in rel.split("/") or ":" in rel:
        raise MarksError(f"{where}: file {rel!r} must be a relative path with / and no ..")

    return os.path.join(base, *rel.split("/"))


def check_mark_file(data: bytes, where: str) -> blp.BlpInfo:
    try:
        info = blp.parse(data, where)
    except blp.BlpError as e:
        raise MarksError(str(e)) from None

    if info.kind != "palette" or info.alpha_size != 8 or (info.width, info.height) != (512, 512):
        raise MarksError(f"{where}: {info.describe()}; a mark must be a 512x512 palette BLP with 8-bit alpha")

    if len(info.levels) != blp.level_count(512, 512) or info.missing:
        raise MarksError(f"{where}: {len(info.levels)} mip level(s); a mark needs all {blp.level_count(512, 512)}")

    return info


def alpha_bytes(data: bytes, info: blp.BlpInfo) -> list[bytes]:
    out = []

    for level in info.levels:
        pixels = level.width * level.height
        out.append(data[level.offset + pixels:level.offset + 2 * pixels])

    return out


def check_glow_file(mark: bytes, glow: bytes, where: str):
    info = check_mark_file(mark, where)
    glow_info = check_mark_file(glow, where + " (_Glow)")

    if [(lv.width, lv.height) for lv in info.levels] != [(lv.width, lv.height) for lv in glow_info.levels]:
        raise MarksError(f"{where}: the _Glow file's levels differ from the mark's")

    if alpha_bytes(mark, info) != alpha_bytes(glow, glow_info):
        raise MarksError(f"{where}: the _Glow file's alpha is not the mark's, byte for byte")


MARKFORGE_FORMAT = "bleakhold-marks/1"


def from_markforge(data: dict, path: str, catalogue: Catalogue) -> dict:
    """MarkForge's own form (format bleakhold-marks/1: race_sexes with marks and eyes, the files at
    files/<client path>) as the contract's format 1. MarkForge records the catalogue's version, not its SHA-1, so
    every key, name, hex value and glow flag it wrote is checked against the catalogue instead."""

    def same(where: str, field_name: str, have, want):
        if have != want:
            raise MarksError(f"{path}: {where}: {field_name} {have!r}, the catalogue has {want!r}: run MarkForge "
                             "again")

    if data.get("fixture"):
        raise MarksError(f"{path}: a MarkForge fixture (drawn on its test body, not the realm's models)")

    if not isinstance(data.get("gates"), dict) or data["gates"].get("passed") is not True:
        raise MarksError(f"{path}: MarkForge's gates did not pass")

    # a build from a package folder (a dev session) may not have read every skin's underwear: its marks could be
    # painted over the cloth. Only a build from the realm's own client and patches is shipped
    if data.get("source") != "game":
        raise MarksError(f"{path}: built from {data.get('source')!r}, not the realm's client and patches (\"game\"): "
                         "run markforge.py build --client ... --patches ... on the VPS")

    same("the manifest", "catalogue_version", data.get("catalogue_version"), catalogue.version)

    if not isinstance(data.get("race_sexes"), list):
        raise MarksError(f"{path}: needs race_sexes")

    def file_of(texture) -> str | None:
        return "files/" + texture.replace("\\", "/") if isinstance(texture, str) else None

    races = []

    for i, item in enumerate(data["race_sexes"]):
        if not isinstance(item, dict) or item.get("race_file") not in catalogue.races \
                or ap.SEXES.get(item.get("sex")) is None:
            raise MarksError(f"{path}: race_sexes[{i}]: needs a race_file of the catalogue and a sex (0, 1)")

        race, sex_name = item["race_file"], ap.SEXES[item["sex"]]
        where = f"{race} {sex_name}"
        cat = catalogue.races[race]
        same(where, "sex_name", item.get("sex_name", sex_name), sex_name)

        if item.get("garment_missing") != 0:
            raise MarksError(f"{path}: {where}: garment_missing {item.get('garment_missing')!r}: MarkForge did not "
                             "read the underwear of every visible skin colour (0 needed), so marks may be painted "
                             "over it")

        if ap.RACE_FILES.get(item.get("race")) != race:
            raise MarksError(f"{path}: {where}: race {item.get('race')!r} is not {race}'s id")

        looks = []

        for mark in item.get("marks") or []:
            if not isinstance(mark, dict) or mark.get("design") not in range(1, ap.DESIGNS + 1) \
                    or mark.get("colour") not in range(1, ap.COLOURS + 1):
                raise MarksError(f"{path}: {where}: a mark needs design 1-{ap.DESIGNS} and colour 1-{ap.COLOURS}")

            design, colour = cat.designs[mark["design"] - 1], cat.colours[mark["colour"] - 1]
            w = f"{where} look {mark.get('look')}"

            for field_name, want in (("design_key", design.key), ("design_name", design.name),
                                     ("colour_key", colour.key), ("colour_name", colour.name),
                                     ("hex", colour.hex), ("glow", colour.glow)):
                have = mark.get(field_name)
                same(w, field_name, have.upper() if field_name == "hex" and isinstance(have, str) else have, want)

            glow = mark.get("glow_texture") if colour.glow else None

            if not colour.glow and (mark.get("glow_texture") or mark.get("glow_sha1")):
                raise MarksError(f"{path}: {w} is the paint colour, which has no _Glow")

            looks.append({"look": mark.get("look"), "design": design.key, "colour": colour.key,
                          "texture": mark.get("texture"), "file": file_of(mark.get("texture")),
                          "sha1": mark.get("sha1"), "glow": glow, "glow_file": file_of(glow),
                          "glow_sha1": mark.get("glow_sha1") if colour.glow else None})

        eyes = []

        for eye in item.get("eyes") or []:
            if not isinstance(eye, dict) or eye.get("eye") not in range(1, ap.EYES + 1):
                raise MarksError(f"{path}: {where}: an eye needs eye 1-{ap.EYES}")

            entry = cat.eye(eye["eye"], catalogue.dk_eyes)
            w = f"{where} eye {eye['eye']}"

            for field_name, want in (("key", entry.key), ("name", entry.name), ("hex", entry.hex),
                                     ("dk_only", eye["eye"] in ap.DK_EYES)):
                have = eye.get(field_name)
                same(w, field_name, have.upper() if field_name == "hex" and isinstance(have, str) else have, want)

            eyes.append({"eye": eye["eye"], "colour": entry.key, "texture": eye.get("texture"),
                         "file": file_of(eye.get("texture")), "sha1": eye.get("sha1")})

        races.append({"race": race, "sex": sex_name, "looks": looks, "eyes": eyes})

    return {"format": 1, "tool": "markforge", "catalogue_sha1": catalogue.sha1, "races": races}


def coverage_problems(manifest: Manifest, catalogue: Catalogue) -> list[str]:
    """The race-sexes of the catalogue the manifest lacks, or has without all 12 looks and eyes 1-5: the picker data
    (full_manifest()) offers every one of them."""
    out = []

    for race in catalogue.races:
        for sex, sex_name in ap.SEXES.items():
            marks = manifest.entries.get((race, sex))

            if marks is None:
                out.append(f"{race} {sex_name}: missing")
            elif sorted(marks.looks) != list(range(1, ap.LOOKS + 1)) \
                    or sorted(marks.eyes) != list(range(1, ap.EYES + 1)):
                out.append(f"{race} {sex_name}: {len(marks.looks)} looks, eyes {sorted(marks.eyes)}")

    return out


def parse_manifest(data: dict, path: str, catalogue: Catalogue, check_files: bool = True,
                   partial: bool = False) -> Manifest:
    """partial: a dev run's manifest may lack race-sexes, looks or eyes (customize --marks-partial); without it the
    manifest must have every race-sex of the catalogue with all 12 looks and eyes 1-5."""
    base = os.path.dirname(os.path.abspath(path))

    if isinstance(data, dict) and data.get("format") == MARKFORGE_FORMAT:
        data = from_markforge(data, path, catalogue)

    if not isinstance(data, dict) or data.get("format") != 1 or not isinstance(data.get("races"), list):
        raise MarksError(f"{path}: not a marks_manifest.json of format 1 or {MARKFORGE_FORMAT}")

    if data.get("catalogue_sha1") != catalogue.sha1:
        raise MarksError(f"{path}: made from another catalogue.json (catalogue_sha1 {data.get('catalogue_sha1')}, "
                         f"{catalogue.path} is {catalogue.sha1}): run MarkForge again")

    entries: dict[tuple[str, int], RaceSexMarks] = {}

    for i, item in enumerate(data["races"]):
        where = f"{path}: races[{i}]"

        if not isinstance(item, dict) or item.get("race") not in catalogue.races or item.get("sex") not in ap.SEX_BY_NAME:
            raise MarksError(f"{where}: needs a race of the catalogue and a sex (Male, Female)")

        race, sex = item["race"], ap.SEX_BY_NAME[item["sex"]]
        cat = catalogue.races[race]
        where = f"{path}: {race} {item['sex']}"

        if (race, sex) in entries:
            raise MarksError(f"{where}: listed twice")

        marks = entries[(race, sex)] = RaceSexMarks(race, sex)
        looks = item.get("looks") or []

        if looks and len(looks) != ap.LOOKS:
            raise MarksError(f"{where}: {len(looks)} looks; a race and sex has all {ap.LOOKS} or none")

        for look_item in looks:
            if not isinstance(look_item, dict):
                raise MarksError(f"{where}: a look must be an object")

            keys = [d.key for d in cat.designs], [c.key for c in cat.colours]

            if look_item.get("design") not in keys[0] or look_item.get("colour") not in keys[1]:
                raise MarksError(f"{where}: look {look_item.get('look')}: design {look_item.get('design')!r} or colour "
                                 f"{look_item.get('colour')!r} is not in the catalogue")

            design, colour = keys[0].index(look_item["design"]) + 1, keys[1].index(look_item["colour"]) + 1
            number = ap.look_of(design, colour)

            if look_item.get("look") != number or number in marks.looks:
                raise MarksError(f"{where}: {look_item['design']}, {look_item['colour']} is look {number} "
                                 f"(3 x (design - 1) + colour), not {look_item.get('look')}, and once only")

            texture = ap.mark_name(race, sex, look_item["design"], look_item["colour"])

            if look_item.get("texture") != texture:
                raise MarksError(f"{where}: look {number}'s texture must be {texture}")

            glow = look_item.get("glow")

            if colour == ap.COLOURS and glow is not None:
                raise MarksError(f"{where}: look {number} is the paint colour, which has no _Glow")

            if glow is not None and glow != ap.glow_name(texture):
                raise MarksError(f"{where}: look {number}'s glow must be {ap.glow_name(texture)}")

            if glow is not None and not cat.colours[colour - 1].glow:
                raise MarksError(f"{where}: look {number}'s colour {cat.colours[colour - 1].key} does not glow in "
                                 "the catalogue")

            look = Look(number, design, colour, texture)

            if check_files:
                look.file = _file(base, look_item.get("file"), f"{where} look {number}")
                look.sha1 = str(look_item.get("sha1") or "")

                if glow is not None:
                    look.glow = glow
                    look.glow_file = _file(base, look_item.get("glow_file"), f"{where} look {number} glow")
                    look.glow_sha1 = str(look_item.get("glow_sha1") or "")
            else:
                look.glow = glow

            marks.looks[number] = look

        for eye_item in item.get("eyes") or []:
            if not isinstance(eye_item, dict) or eye_item.get("eye") not in range(1, ap.EYES + 1):
                raise MarksError(f"{where}: an eye must be an object with eye 1-{ap.EYES}")

            eye = eye_item["eye"]
            expected = cat.eye(eye, catalogue.dk_eyes)

            if eye_item.get("colour") != expected.key or eye in marks.eyes:
                raise MarksError(f"{where}: eye {eye} is {expected.key} in the catalogue, once")

            texture = ap.eye_name(race, sex, expected.key)

            if eye_item.get("texture") != texture:
                raise MarksError(f"{where}: eye {eye}'s texture must be {texture}")

            entry = Eye(eye, expected.key, texture)

            if check_files:
                entry.file = _file(base, eye_item.get("file"), f"{where} eye {eye}")
                entry.sha1 = str(eye_item.get("sha1") or "")

            marks.eyes[eye] = entry

    manifest = Manifest(path, entries)

    if not partial:
        missing = coverage_problems(manifest, catalogue)

        if missing:
            total = len(catalogue.races) * len(ap.SEXES)
            raise MarksError(f"{path}: {total - len(missing)} of {total} race-sexes have all {ap.LOOKS} looks and eyes "
                             f"1-{ap.EYES} ({'; '.join(missing[:4])}{'; ...' if len(missing) > 4 else ''}): the picker "
                             "data offers them on every race and sex, so customize --marks needs all of them "
                             "(--marks-partial for a dev run only)")

    if check_files:
        check_manifest_files(manifest)

    return manifest


def check_manifest_files(manifest: Manifest):
    for marks in manifest.entries.values():
        for name, path, digest in marks.files():
            if not os.path.isfile(path):
                raise MarksError(f"{manifest.path}: {name}: {path} is missing")

            if sha1_file(path) != digest:
                raise MarksError(f"{manifest.path}: {name}: {path} is not the file the manifest names (SHA-1)")

        for look in marks.looks.values():
            with open(look.file, "rb") as f:
                data = f.read()

            check_mark_file(data, look.texture)

            if look.glow:
                with open(look.glow_file, "rb") as f:
                    check_glow_file(data, f.read(), look.texture)

        for eye in marks.eyes.values():
            with open(eye.file, "rb") as f:
                try:
                    blp.parse(f.read(), eye.texture)
                except blp.BlpError as e:
                    raise MarksError(str(e)) from None


def load_manifest(path: str, catalogue: Catalogue, check_files: bool = True, partial: bool = False) -> Manifest:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise MarksError(f"{path} is missing") from None
    except json.JSONDecodeError as e:
        raise MarksError(f"{path}: not valid JSON ({e})") from None

    return parse_manifest(data, path, catalogue, check_files, partial)


def full_manifest(catalogue: Catalogue) -> Manifest:
    """Every race and sex with all 12 looks and eyes 1-5, under the contract's names, without files: the stage-2
    view picker-data describes."""
    entries = {}

    for race, cat in catalogue.races.items():
        for sex in ap.SEXES:
            marks = entries[(race, sex)] = RaceSexMarks(race, sex)

            for design, d in enumerate(cat.designs, 1):
                for colour, c in enumerate(cat.colours, 1):
                    look = ap.look_of(design, colour)
                    texture = ap.mark_name(race, sex, d.key, c.key)
                    marks.looks[look] = Look(look, design, colour, texture,
                                             glow=ap.glow_name(texture) if c.glow else None)

            for eye in range(1, ap.EYES + 1):
                key = cat.eye(eye, catalogue.dk_eyes).key
                marks.eyes[eye] = Eye(eye, key, ap.eye_name(race, sex, key))

    return Manifest("(the full catalogue)", entries)


# --- rows ------------------------------------------------------------------------------------------------------


@dataclass
class Added:
    features_values: int = 0
    feature_rows: int = 0
    base_rows: int = 0
    facial_styles: int = 0
    eye_rows: int = 0


def _new_row(cs: DbcTable, race: int, sex: int, section: int, variation: int, colour: int, flags: int,
             textures: tuple[str, str, str]) -> list[int]:
    row = [0] * len(cs.schema.columns)
    cs.set(row, "raceID", race)
    cs.set(row, "sexID", sex)
    cs.set(row, "baseSection", section)
    cs.set(row, "variationIndex", variation)
    cs.set(row, "colorIndex", colour)
    cs.set(row, "flags", flags)

    for slot, name in enumerate(textures):
        cs.set_str(row, f"textureName[{slot}]", name)

    return row


def hair_colour_flags(cs: DbcTable, race: int, sex: int) -> dict[int, int]:
    """Per hair colour of the race and sex's hair rows: 0x11 when a player can pick it, else 0x5 when a Death Knight
    can, else 0x8."""
    seen: dict[int, list[int]] = {}

    for row in cs.rows:
        if cs.get(row, "raceID") == race and cs.get(row, "sexID") == sex and cs.get(row, "baseSection") == ap.HAIR:
            seen.setdefault(cs.get(row, "colorIndex"), []).append(cs.get(row, "flags"))

    out = {}

    for colour, flags in seen.items():
        if any(ap.selectable(f, w, False) for f in flags for w in ap.WHERE):
            out[colour] = ap.PLAYER | ap.DK_TOO
        elif any(ap.selectable(f, w, True) for f in flags for w in ap.WHERE):
            out[colour] = ap.PLAYER | ap.DEATH_KNIGHT
        else:
            out[colour] = ap.HIDDEN

    return out


def base_count(cfhs: DbcTable, race: int, sex: int) -> int:
    return sum(1 for r in cfhs.rows if cfhs.get(r, "raceID") == race and cfhs.get(r, "sexID") == sex)


def add_marks(cs: DbcTable, cfhs: DbcTable, race: int, sex: int, b: int, looks: dict[int, Look]) -> Added:
    """The rows of one race and sex's marks (all 12 looks). cs and cfhs are changed; the caller sorts and numbers."""
    added = Added()

    if not looks:
        return added

    if sorted(looks) != list(range(1, ap.LOOKS + 1)):
        raise MarksError(f"race {race} sex {sex}: looks {sorted(looks)}; all {ap.LOOKS} or none")

    if b <= 0:
        raise MarksError(f"race {race} sex {sex}: no CharacterFacialHairStyles rows, so no base features for marks")

    if (ap.LOOKS + 1) * b - 1 > ap.MAX_VALUE:
        raise MarksError(f"race {race} sex {sex}: {b} base features x {ap.LOOKS + 1} looks needs values up to "
                         f"{(ap.LOOKS + 1) * b - 1}, above {ap.MAX_VALUE}")

    styles = [r for r in cfhs.rows if cfhs.get(r, "raceID") == race and cfhs.get(r, "sexID") == sex]
    by_value = {cfhs.get(r, "variationID"): r for r in styles}

    if sorted(by_value) != list(range(b)) or len(styles) != b:
        raise MarksError(f"race {race} sex {sex}: CharacterFacialHairStyles has values {sorted(by_value)}, not 0-{b - 1} "
                         "once each (marks are already there, or the table is not the package's)")

    base_rows = [r for r in cs.rows if cs.get(r, "raceID") == race and cs.get(r, "sexID") == sex
                 and cs.get(r, "baseSection") == ap.FEATURES]

    if any(cs.get(r, "variationIndex") >= b for r in base_rows):
        raise MarksError(f"race {race} sex {sex}: features rows at values {b} and up are already there")

    if not base_rows:
        for colour, flags in sorted(hair_colour_flags(cs, race, sex).items()):
            for value in range(b):
                row = _new_row(cs, race, sex, ap.FEATURES, value, colour, flags, ("", "", ""))
                cs.rows.append(row)
                base_rows.append(row)
                added.base_rows += 1

    for look in range(1, ap.LOOKS + 1):
        texture = looks[look].texture

        for base in base_rows:
            value = ap.features_value(look, cs.get(base, "variationIndex"), b)
            textures = (cs.get_str(base, "textureName[0]"), cs.get_str(base, "textureName[1]"), texture)
            cs.rows.append(_new_row(cs, race, sex, ap.FEATURES, value, cs.get(base, "colorIndex"),
                                    cs.get(base, "flags"), textures))
            added.feature_rows += 1

        for value in range(b):
            new = list(by_value[value])
            cfhs.set(new, "variationID", ap.features_value(look, value, b))
            cfhs.rows.append(new)
            added.facial_styles += 1

    added.features_values = ap.LOOKS * b
    return added


def add_eyes(cs: DbcTable, race: int, sex: int, eyes: dict[int, Eye]) -> Added:
    """The face rows of one race and sex's eyes."""
    added = Added()

    if not eyes:
        return added

    faces = [r for r in cs.rows if cs.get(r, "raceID") == race and cs.get(r, "sexID") == sex
             and cs.get(r, "baseSection") == ap.FACE]
    top = max((cs.get(r, "variationIndex") for r in faces), default=-1)

    if top >= ap.EYE_STRIDE:
        raise MarksError(f"race {race} sex {sex}: face variation {top} is {ap.EYE_STRIDE} or more (eye rows are "
                         "already there, or the package has more faces than the encoding allows)")

    for eye in sorted(eyes):
        dk = eye in ap.DK_EYES

        for base in faces:
            flags = cs.get(base, "flags")

            if not ap.selectable(flags, ap.CREATION, dk):
                continue

            new_flags = (ap.PLAYER | ap.DEATH_KNIGHT) if dk else flags & ~ap.DK_TOO
            textures = (cs.get_str(base, "textureName[0]"), cs.get_str(base, "textureName[1]"), eyes[eye].texture)
            cs.rows.append(_new_row(cs, race, sex, ap.FACE, ap.face_value(cs.get(base, "variationIndex"), eye),
                                    cs.get(base, "colorIndex"), new_flags, textures))
            added.eye_rows += 1

    return added


def features_problems(cs: DbcTable, cfhs: DbcTable, races: set[int]) -> list[str]:
    """For every race and sex with features rows: every CharacterFacialHairStyles value has a row at every hair colour
    a player or Death Knight can pick (stepping backwards onto a missing row reads a null pointer in old exes)."""
    problems = []
    counts: dict[tuple[int, int], int] = {}

    for r in cfhs.rows:
        key = (cfhs.get(r, "raceID"), cfhs.get(r, "sexID"))
        counts[key] = counts.get(key, 0) + 1

    have: dict[tuple[int, int], set[tuple[int, int]]] = {}
    pickable: dict[tuple[int, int], set[int]] = {}

    for row in cs.rows:
        key = (cs.get(row, "raceID"), cs.get(row, "sexID"))

        if key[0] not in races:
            continue

        section = cs.get(row, "baseSection")

        if section == ap.FEATURES:
            have.setdefault(key, set()).add((cs.get(row, "variationIndex"), cs.get(row, "colorIndex")))
        elif section == ap.HAIR and any(ap.selectable(cs.get(row, "flags"), w, dk) for w in ap.WHERE
                                        for dk in (False, True)):
            pickable.setdefault(key, set()).add(cs.get(row, "colorIndex"))

    for key, cells in sorted(have.items()):
        n = counts.get(key, 0)
        missing = [(v, c) for v in range(n) for c in sorted(pickable.get(key, ())) if (v, c) not in cells]

        if missing:
            problems.append(f"race {key[0]} sex {key[1]}: {len(missing)} features value(s) without a row at a hair "
                            f"colour players can pick (value, colour): {missing[:6]}")

    return problems
