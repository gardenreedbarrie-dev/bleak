r"""raceforge.py skins: new skin colours for a race the realm already has (High Elf: night-elf-like purple), without
touching the textures its template race shares.

The High Elf of the Bleakhold realm uses the Blood Elf's textures: its CharSections rows (race 15, from the realm's own
race patch) name the same files as the Blood Elf's (race 10). So the files are never changed. For every row of the
race in the sections of skins.json (0 skin and 1 face by default), each texture is recoloured into a new file,

    Character\BleakholdSkins\<ClientFileString>\<hash>\<the original path>

and only that row's texture name changes to it. The hash (10 hex digits of a SHA-1) covers the original's bytes, the
colour parameters and the algorithm version, so the same input always gives the same file. A row that already names
one of these files is read through it: the original path after the hash folder is the source. Running the tool again
on the updated realm therefore finds the same files and changes nothing ("already up to date"), and a change of the
palette gives new names (the old files go from every archive that is rebuilt).

The game's files are the launcher's: --client's Data folder (the 3.3.5a client) with --patches over it (a file of
--patches replaces the one of the same path). The client loads its base archives (s_archives in WoW/Source/Client.cpp,
earlier ones winning), then patch.MPQ and patch-<locale>.MPQ, then every patch-?.MPQ and <locale>\patch-<locale>-?.MPQ
above all of them (Tools/MapForge/dbc/patches.py). For every combination of the launcher's optional packs, the copy of
CharSections.dbc the client reads is forged (forge()), and placed (place()):

- the archive that holds that copy (always a patch: a base archive cannot hold the realm's race) gets the forged copy
  and the new textures, when every combination that reads it gets the same result;
- when a pack replaces a source texture under the same name (an HD pack's Blood Elf skin), its players get other
  colours from the same CharSections.dbc. The combination with the fewest packs keeps that archive; each other one
  needs an archive of a pack the first lacks, active for it, loading above that archive and read by no combination
  that needs other contents: the highest such one gets its own CharSections.dbc and textures, with a marker
  (COPY_MARKER) that names the copy. Without one, nothing is written.

Such a copy hides the CharSections.dbc below it from its players, so it must never go stale: a later run passes over
it (find_copies(), source_holder()) and makes it again from the archive below, so a change there (a new row of the
race patch) reaches those players too, and it removes the copy (and its textures) once no combination needs it.

Before anything is written, the client's view of every combination is worked out from the planned archives
(simulate()): the CharSections.dbc it reads must be its forged copy, and every texture name in it must resolve to the
expected bytes. After writing, the same check runs on the written archives, with the other rows (the race's other
sections, every other race) compared field for field and every new texture parsed and decoded.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import re
import shutil
from dataclasses import dataclass, field

from . import blp, install, recolor, schema_access, update
from .config import Config, RaceConfig
from .dbc import DbcError, DbcTable, to_signed
from .validate import Validation

patches = update.patch_tools()  # Tools/MapForge/dbc/patches.py (puts Tools/MpqPack and Tools/BlpConvert on sys.path)

import mpqpack  # noqa: E402  (Tools/MpqPack)

CHAR_SECTIONS = "DBFilesClient\\CharSections.dbc"
CHR_RACES = "DBFilesClient\\ChrRaces.dbc"
SKINS_FOLDER = "Character\\BleakholdSkins"
# Next to a CharSections.dbc that place() put into a pack archive for that pack's players: which copy it is (its SHA-1)
# and what it was made from. The client never reads it.
COPY_MARKER = SKINS_FOLDER + "\\CharSections-copy.json"
HASH_DIGITS = 10
MAX_NAME_BYTES = mpqpack.MAX_PATH_BYTES  # 259: the client hashes names into 260-byte buffers
SECTION_NAMES = {0: "skin", 1: "face", 2: "facial hair", 3: "hair", 4: "underwear"}
# The sections whose colour index is the skin colour: hair and facial hair count hair colours instead.
SKIN_COLOUR_SECTIONS = (0, 1, 4)
DEATH_KNIGHT = 0x4  # CharSections flag of the Death Knight rows (ComponentFlagsMatch)
SEXES = {0: "Male", 1: "Female"}
OUT_ENTRIES = ("client", "merged", "staging", "preview", "report.txt", "install.json")
SPACE_MARGIN = 256 * 1024 * 1024
PREVIEW_TILE = 96

# s_archives in WoW/Source/Client.cpp: (name, kind, availability). OpenArchives opens kind 3 (alternate.MPQ) above every
# patch and kind 4 only when streaming; every other one is a base archive, opened when its availability bits meet the
# client's (2 when Data\common.MPQ exists, else 1), with priorities from 63 down in this order: an earlier one wins.
# **** is the locale.
BASE_ARCHIVES = (
    ("alternate.MPQ", 3, 3),
    ("interface.MPQ", 1, 1),
    ("misc.MPQ", 1, 1),
    ("model.MPQ", 1, 1),
    ("texture.MPQ", 1, 1),
    ("terrain.MPQ", 1, 1),
    ("wmo.MPQ", 1, 1),
    ("sound.MPQ", 1, 1),
    ("fonts.MPQ", 1, 1),
    ("dbc.MPQ", 1, 1),
    ("speech.MPQ", 1, 1),
    ("expansionloc.MPQ", 2, 1),
    ("lichkingloc.MPQ", 2, 1),
    ("expansionspeech.MPQ", 2, 1),
    ("lichkingspeech.MPQ", 2, 1),
    ("expansion.MPQ", 2, 3),
    ("lichking.MPQ", 2, 3),
    ("common.MPQ", 1, 2),
    ("common-2.MPQ", 2, 2),
    ("****\\locale-****.MPQ", 1, 2),
    ("****\\speech-****.MPQ", 1, 2),
    ("****\\expansion-locale-****.MPQ", 2, 2),
    ("****\\lichking-locale-****.MPQ", 2, 2),
    ("****\\expansion-speech-****.MPQ", 2, 2),
    ("****\\lichking-speech-****.MPQ", 2, 2),
    ("development.MPQ", 2, 1),
    ("streaming.MPQ", 4, 1),
    ("streamingloc.MPQ", 4, 1),
)


class SkinsError(Exception):
    pass


# --- skins.json --------------------------------------------------------------------------------------------------


@dataclass
class SkinRace:
    race: RaceConfig  # races.json's race at its realm id (Config.for_realm())
    sections: list[int]
    palette: list[str]
    dk_palette: list[str]
    settings: dict
    comment: str = ""

    @property
    def name(self) -> str:
        return self.race.client_file_string

    @property
    def prefix(self) -> str:
        return f"{SKINS_FOLDER}\\{self.race.client_file_string}\\"

    def palette_lab(self, dk: bool) -> list[tuple[float, float, float]]:
        return [recolor.hex_to_oklab(c) for c in (self.dk_palette if dk else self.palette)]


def load(path: str, config: Config) -> list[SkinRace]:
    """skins.json, checked, with each race found in races.json (config) by its client_file_string."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise SkinsError(f"{path}: not valid JSON ({e})") from None

    return parse(data, config, path)


def parse(data: dict, config: Config, path: str = "skins.json") -> list[SkinRace]:
    if not isinstance(data, dict) or not isinstance(data.get("races"), list) or not data["races"]:
        raise SkinsError(f"{path}: needs a non-empty races list")

    unknown = set(data) - {"_readme", "races", "transform", "comment"}

    if unknown:
        raise SkinsError(f"{path}: unknown keys {sorted(unknown)}")

    try:
        recolor.settings_from(data.get("transform"), f"{path}: transform")
    except recolor.RecolorError as e:
        raise SkinsError(str(e)) from None

    by_file_string = {r.client_file_string.lower(): r for r in config.races}
    out = []

    for i, entry in enumerate(data["races"]):
        where = f"{path}: races[{i}]"

        if not isinstance(entry, dict):
            raise SkinsError(f"{where}: must be an object")

        unknown = set(entry) - {"client_file_string", "sections", "palette", "dk_palette", "transform", "comment"}

        if unknown:
            raise SkinsError(f"{where}: unknown keys {sorted(unknown)}")

        file_string = entry.get("client_file_string")
        race = by_file_string.get(str(file_string).lower()) if isinstance(file_string, str) else None

        if race is None:
            known = ", ".join(r.client_file_string for r in config.races)
            raise SkinsError(f"{where}: client_file_string {file_string!r} is no race of races.json ({known})")

        where = f"{where} ({race.client_file_string})"
        sections = entry.get("sections", [0, 1])

        if not isinstance(sections, list) or not all(isinstance(s, int) and not isinstance(s, bool) for s in sections):
            raise SkinsError(f"{where}: sections must be a list of section numbers")

        bad = [s for s in sections if s not in SKIN_COLOUR_SECTIONS]

        if bad or len(set(sections)) != len(sections):
            raise SkinsError(f"{where}: sections {sections}: give each of 0 (skin), 1 (face) and 4 (underwear) at most "
                             "once; hair and facial hair have colours of their own and are not recoloured")

        palettes = {}

        for key in ("palette", "dk_palette"):
            value = entry.get(key)

            if not isinstance(value, list) or not value:
                raise SkinsError(f"{where}: {key} must be a non-empty list of colours (#RRGGBB), lightest first")

            try:
                for colour in value:
                    recolor.hex_to_oklab(colour)
            except recolor.RecolorError as e:
                raise SkinsError(f"{where}: {key}: {e}") from None

            palettes[key] = [str(c).upper() if str(c).startswith("#") else "#" + str(c).upper() for c in value]

        try:
            race_settings = recolor.settings_from({**(data.get("transform") or {}), **(entry.get("transform") or {})},
                                                  f"{where}: transform")
        except recolor.RecolorError as e:
            raise SkinsError(str(e)) from None

        out.append(SkinRace(race, sorted(sections), palettes["palette"], palettes["dk_palette"], race_settings,
                            str(entry.get("comment") or "")))

    if len({r.name.lower() for r in out}) != len(out):
        raise SkinsError(f"{path}: a race is listed twice")

    return out


# --- the game's archives -----------------------------------------------------------------------------------------


@dataclass
class GameArchive(patches.Archive):
    origin: str = ""  # "patches" or "client": the folder the launcher takes the file from
    rel: str = ""  # its path in that folder (Patch-R.MPQ, enUS/patch-enUS-3.MPQ), also its place under --out/client
    base_index: int = -1  # its place in s_archives for a base archive; -1 for a patch
    size: int = 0  # as read (install.json)
    mtime_ns: int = 0

    @property
    def is_base(self) -> bool:
        return self.base_index >= 0

    def rank(self) -> tuple:
        # every base archive below patch.MPQ (group 0), an earlier one of s_archives above a later one
        return (-1, -self.base_index) if self.is_base else super().rank()

    def where(self) -> str:
        return f"{'--patches' if self.origin == 'patches' else '--client Data'}/{self.rel}"


@dataclass
class Game:
    patchset: patches.PatchSet
    client_data: str
    patches_dir: str
    locale: str
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    copies: dict[str, dict] = field(default_factory=dict)  # find_copies()

    @property
    def archives(self) -> list[GameArchive]:
        return self.patchset.archives

    def archive(self, client_path: str) -> GameArchive:
        return next(a for a in self.archives if a.client_path.lower() == client_path.lower())

    def close(self):
        self.patchset.close()


def find_entry(folder: str, name: str) -> str | None:
    """The entry of folder named name in any case (Windows sees one file)."""
    try:
        entries = sorted(os.listdir(folder))
    except OSError:
        return None

    for entry in entries:
        if entry.casefold() == name.casefold():
            return os.path.join(folder, entry)

    return None


def detect_locale(client_data: str, locale: str | None) -> str:
    """The client's locale: the one given, or the one folder of Data that holds its locale-<locale>.MPQ."""
    known = {code.casefold(): code for code in patches.LOCALES}

    if locale:
        if locale.casefold() not in known:
            raise SkinsError(f"--locale {locale}: not a locale of the 3.3.5a client ({', '.join(patches.LOCALES)})")

        return known[locale.casefold()]

    found = []

    for entry in sorted(os.listdir(client_data)):
        code = known.get(entry.casefold())

        folder = os.path.join(client_data, entry)

        if code and os.path.isdir(folder) and find_entry(folder, f"locale-{code}.MPQ"):
            found.append(code)

    if len(found) != 1:
        what = "none" if not found else ", ".join(found)
        raise SkinsError(f"{client_data}: the client's locale is not clear (Data/<locale>/locale-<locale>.MPQ: "
                         f"{what}); pass --locale")

    return found[0]


def overlay(client_data: str, patches_dir: str, locale: str, game: Game) -> dict[str, tuple[str, str, str, str]]:
    """The archives the launcher lays out: {casefolded client path: (client path, file, origin, path in its folder)}
    of every .MPQ in Data and Data\\<locale>, --patches over --client (the launcher's rule: patches/ wins over base/
    for the same path)."""
    files = {}

    for origin, top in (("client", client_data), ("patches", patches_dir)):
        seen = {}

        for entry in sorted(os.listdir(top)):
            path = os.path.join(top, entry)

            if os.path.isdir(path):
                if origin == "patches" and entry.casefold() == "data":
                    game.warnings.append(f"{path}: the launcher skips a Data folder in patches/ (patch files go "
                                         "straight into patches/), and so does this tool")
                    continue

                if entry.casefold() != locale.casefold():
                    if origin == "patches" and entry.casefold() in {c.casefold() for c in patches.LOCALES}:
                        game.notes.append(f"{path}: another locale than the client's ({locale}): not read")
                    continue

                children = [(f"{entry}/{sub}", os.path.join(path, sub), f"Data\\{entry}\\{sub}")
                            for sub in sorted(os.listdir(path))]
            else:
                children = [(entry, path, f"Data\\{entry}")]

            for rel, file_path, client_path in children:
                if not rel.casefold().endswith(".mpq") or not os.path.isfile(file_path):
                    continue

                key = client_path.casefold()

                if key in seen:
                    game.warnings.append(f"{file_path} and {seen[key]} differ only in upper/lower case: the launcher "
                                         "uses the first")
                    continue

                seen[key] = file_path
                files[key] = (client_path, file_path, origin, rel)

    return files


def game_archives(client_dir: str, patches_dir: str, packs: dict, locale: str | None = None) -> Game:
    """The archives the client loads from the launcher's game folder, in its order (lowest first)."""
    data = client_dir if find_entry(client_dir, "common.MPQ") else (find_entry(client_dir, "Data") or "")

    if not data or not os.path.isdir(data):
        raise SkinsError(f"--client {client_dir}: no Data folder (give the game folder the launcher ships, which holds "
                         "Data/common.MPQ)")

    if not os.path.isdir(patches_dir):
        raise SkinsError(f"--patches {patches_dir} is not a folder")

    locale = detect_locale(data, locale)
    game = Game(patches.PatchSet([], dict(packs or {}), patches_dir), data, patches_dir, locale)
    files = overlay(data, patches_dir, locale, game)
    availability = 2 if "data\\common.mpq" in files else 1

    if availability == 1:
        game.warnings.append(f"{data} has no common.MPQ: the client then takes the base archives of older clients")

    archives = []
    used = set()

    def add(key: str, group: int, base_index: int = -1):
        client_path, path, origin, rel = files[key]
        pack = patches.pack_of(client_path, game.patchset.packs)
        archive = GameArchive(path, client_path, group, pack, origin=origin, rel=rel, base_index=base_index)
        archives.append(archive)
        used.add(key)

    for index, (name, kind, flags) in enumerate(BASE_ARCHIVES):
        key = ("Data\\" + name.replace("****", locale)).casefold()

        if kind == 3:
            if key in files:
                game.warnings.append(f"{files[key][1]}: the client loads {name} above every patch, so a "
                                     "CharSections.dbc or texture in it would hide the new ones; this tool does not "
                                     "read it")
                used.add(key)
            continue

        if kind == 4 or not availability & flags:
            continue

        if key in files:
            add(key, -1, index)
        elif kind == 1:
            game.warnings.append(f"{data}: {name.replace('****', locale)} is missing (the client needs it to start)")

    single = re.compile(r"data\\patch-.\.mpq")
    locale_single = re.compile(rf"data\\{re.escape(locale.casefold())}\\patch-{re.escape(locale.casefold())}-.\.mpq")

    for key in sorted(files):
        if key in used:
            continue

        if single.fullmatch(key) or locale_single.fullmatch(key):
            add(key, 1)
        elif key in ("data\\patch.mpq", f"data\\{locale.casefold()}\\patch-{locale.casefold()}.mpq"):
            add(key, 0)
        elif files[key][2] == "patches":
            game.notes.append(f"{files[key][1]}: not an archive the client loads ({files[key][0]}): not read")

    for archive in archives:
        try:
            st = os.stat(archive.path)
            archive.size, archive.mtime_ns = st.st_size, st.st_mtime_ns
            archive.reader = patches.PatchArchive(archive.path)
        except (mpqpack.MpqError, OSError, ValueError) as e:
            archive.error = f"cannot be opened ({e})"

    archives.sort(key=lambda a: a.rank())
    game.patchset.archives = archives
    return game


# --- forging one combination -------------------------------------------------------------------------------------


@dataclass
class Colour:
    """One skin colour of a race and sex in one combination: where its numbers come from and where it goes."""
    race: str
    sex: int
    index: int
    dk: bool
    texture: str  # the source of the skin row's texture 0
    skin: recolor.SkinColour
    target: tuple[float, float, float]
    transform: recolor.Transform


@dataclass
class Forged:
    """One pack combination: the CharSections.dbc it reads and what the skins make of it."""
    label: str
    packs_on: frozenset
    holder: GameArchive
    original: bytes
    data: bytes  # the forged CharSections.dbc
    before: DbcTable
    after: DbcTable
    textures: dict[str, bytes] = field(default_factory=dict)  # new name -> recoloured texture
    sources: dict[str, str] = field(default_factory=dict)  # new name -> source path
    source_digests: dict[str, str] = field(default_factory=dict)  # source path -> SHA-1 of the bytes used
    source_sizes: dict[str, tuple[int, int]] = field(default_factory=dict)  # new name -> the source's width, height
    expected_names: dict[tuple[int, int], str] = field(default_factory=dict)  # (row index, slot) -> the race's name
    race_rows: set = field(default_factory=set)  # row indexes of the skinned races
    colours: list[Colour] = field(default_factory=list)
    rows_recoloured: int = 0
    rows_changed: int = 0  # rows whose texture names differ from the realm's copy
    rows_restored: int = 0
    previews: list = field(default_factory=list)  # (race, sex, colour, dk, [(label, source bytes, new bytes or None)])
    passed: list[str] = field(default_factory=list)  # archives above holder whose CharSections.dbc is skins' own copy

    def same_result(self, other: "Forged") -> bool:
        return self.data == other.data and self.textures == other.textures


def skins_name_source(name: str, race: SkinRace) -> str | None:
    """The original path of one of the race's new texture names (Character\\BleakholdSkins\\<race>\\<hash>\\<path>),
    else None."""
    normal = name.replace("/", "\\")

    if not normal.lower().startswith(race.prefix.lower()):
        return None

    rest = normal[len(race.prefix):]
    digest, _, original = rest.partition("\\")

    if not re.fullmatch(rf"[0-9a-fA-F]{{{HASH_DIGITS}}}", digest) or not original:
        raise SkinsError(f"{name} is in {race.prefix} but is no name skins gives (<{HASH_DIGITS} hex "
                         "digits>\\<original path>)")

    return original


def source_path(name: str, race: SkinRace) -> str:
    """The texture a row's name stands for: the name itself, or the original behind one of the race's new names."""
    seen = 0

    while True:
        original = skins_name_source(name, race)

        if original is None:
            return name

        name = original
        seen += 1

        if seen > 8:
            raise SkinsError(f"{name}: nested {race.prefix} names")


class Recolourer:
    """The work shared by every combination: the source files read, the skin colours and the recoloured textures."""

    def __init__(self, game: Game):
        self.game = game
        self.reads: dict[tuple[str, str], bytes] = {}
        self.stats: dict[tuple[str, str], recolor.SkinColour | None] = {}
        self.transforms: dict[str, recolor.Transform] = {}
        self.textures: dict[tuple[str, str], bytes] = {}

    def winner(self, name: str, packs_on: frozenset) -> tuple[GameArchive | None, bytes | None]:
        archive = self.game.patchset.top(name, packs_on)

        if archive is None:
            return None, None

        key = (archive.client_path.lower(), mpqpack.name_key(name).decode("latin-1"))

        if key not in self.reads:
            try:
                self.reads[key] = archive.read(name)
            except patches.PatchError as e:
                raise SkinsError(f"{name}: {e}") from None

        return archive, self.reads[key]

    def skin_colour(self, data: bytes, where: str, settings: dict) -> recolor.SkinColour:
        key = (hashlib.sha1(data).hexdigest(), json.dumps(settings, sort_keys=True))

        if key not in self.stats:
            try:
                info = blp.parse(data, where)
                width, height, rgba = blp.decode(data, where)
            except blp.BlpError as e:
                raise SkinsError(str(e)) from None

            self.stats[key] = recolor.stats(width, height, rgba, info.has_alpha, settings)

        skin = self.stats[key]

        if skin is None:
            raise SkinsError(f"{where}: no opaque pixel of mid lightness (OKLab L {settings['stats_lightness_min']} to "
                             f"{settings['stats_lightness_max']}), so its skin colour is unknown")

        return skin

    def transform(self, skin: recolor.SkinColour, target: tuple, settings: dict,
                  living_hue: float | None = None) -> recolor.Transform:
        candidate = recolor.Transform(skin, target, settings, living_hue)
        key = canonical(candidate.params())
        return self.transforms.setdefault(key, candidate)

    def recoloured(self, data: bytes, where: str, transform: recolor.Transform) -> tuple[str, bytes]:
        """(hash, recoloured texture) of a source texture."""
        params = canonical(transform.params())
        digest = hashlib.sha1()
        digest.update(recolor.ALGORITHM_VERSION.encode() + b"\0" + params.encode() + b"\0")
        digest.update(data)
        key = (digest.hexdigest(), params)

        if key not in self.textures:
            try:
                self.textures[key] = blp.recolour(data, transform, where)
            except blp.BlpError as e:
                raise SkinsError(str(e)) from None

        return digest.hexdigest()[:HASH_DIGITS], self.textures[key]


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def row_label(table: DbcTable, row: list[int]) -> str:
    section = table.get(row, "baseSection")
    sex = table.get(row, "sexID")
    return (f"row {to_signed(row[0])} (race {table.get(row, 'raceID')}, {SEXES.get(sex, sex)}, "
            f"{SECTION_NAMES.get(section, section)}, variation {table.get(row, 'variationIndex')}, "
            f"colour {table.get(row, 'colorIndex')})")


def find_copies(game: Game) -> dict[str, dict]:
    """The archives whose CharSections.dbc is a copy place() put there: {client path (lower case): its marker}. A
    CharSections.dbc that is no longer the copy its marker names (by SHA-1) is the realm's own again."""
    copies = {}

    for archive in game.archives:
        if archive.is_base or not archive.has(COPY_MARKER):
            continue

        try:
            marker = json.loads(archive.read(COPY_MARKER).decode("utf-8"))
            ours = (isinstance(marker, dict) and archive.has(CHAR_SECTIONS)
                    and marker.get("sha1") == hashlib.sha1(archive.read(CHAR_SECTIONS)).hexdigest())
        except (patches.PatchError, UnicodeDecodeError, json.JSONDecodeError):
            marker, ours = None, False

        if ours:
            copies[archive.client_path.lower()] = marker
        else:
            game.warnings.append(f"{archive.name} holds {COPY_MARKER}, but its {CHAR_SECTIONS} is not the copy skins "
                                 "put there (it changed since, or is gone): it is read as the realm's own")

    return copies


def source_holder(game: Game, packs_on: frozenset) -> tuple[GameArchive | None, list[GameArchive]]:
    """The archive a combination's CharSections.dbc is made from: the one the client reads it from, passing over the
    copies skins put above it (find_copies()), which are made again from what is below them. Also returns those."""
    passed = []

    for archive in reversed(game.patchset.holders(CHAR_SECTIONS, packs_on)):
        if archive.client_path.lower() not in game.copies:
            return archive, passed

        passed.append(archive)

    return None, passed


def forge(game: Game, label: str, packs_on: frozenset, races: list[SkinRace], work: Recolourer,
          base: bytes | None = None) -> Forged:
    """The CharSections.dbc the client reads in this combination (source_holder()), with each race's rows of its
    sections on recoloured textures (and its rows of other sections back on the originals).

    base: the bytes to change in place of that archive's CharSections.dbc, with the same rows: the forged copy of the
    combination that keeps the archive, for one that gets a copy of its own (place()). That copy then holds the same
    string block plus its own names, so a run on the installed realm, which reads the archive's forged copy, makes the
    same bytes again."""
    holder, passed = source_holder(game, packs_on)

    if holder is None:
        own = f" (besides skins' own copy in {', '.join(a.name for a in passed)})" if passed else ""
        raise SkinsError(f"no archive holds {CHAR_SECTIONS} for {label}{own}")

    if holder.is_base:
        names = ", ".join(r.race.name for r in races)
        raise SkinsError(f"{label}: the client reads {CHAR_SECTIONS} from the base archive {holder.name}, which "
                         f"cannot hold the realm's {names}; the realm's race patch must hold its own CharSections.dbc")

    schema = schema_access.get("CharSections")

    try:
        original = holder.read(CHAR_SECTIONS)
        before = DbcTable.from_bytes(original, schema, f"{holder.name}: CharSections.dbc")
        start = original if base is None else base
        after = DbcTable.from_bytes(start, schema, f"{holder.name}: CharSections.dbc")
    except (patches.PatchError, DbcError) as e:
        raise SkinsError(str(e)) from None

    if len(after.rows) != len(before.rows):
        raise SkinsError(f"{label}: the copy to change has {len(after.rows)} rows, {holder.name}'s CharSections.dbc "
                         f"{len(before.rows)}")

    unchanged = [list(row) for row in after.rows]
    forged = Forged(label, packs_on, holder, original, start, before, after, passed=[a.name for a in passed])

    for race in races:
        forge_race(forged, race, game, packs_on, label, work)

    if after.rows != unchanged:
        forged.data = after.to_bytes()

    return forged


def forge_race(forged: Forged, race: SkinRace, game: Game, packs_on: frozenset, label: str, work: Recolourer):
    table = forged.after
    rows = [(i, row) for i, row in enumerate(table.rows) if table.get(row, "raceID") == race.race.id]
    forged.race_rows.update(i for i, _ in rows)

    if not rows:
        raise SkinsError(f"{race.race.name}: {forged.holder.name}'s CharSections.dbc (for {label}) has no rows of race "
                         f"{race.race.id}")

    def read_source(name: str, row: list[int]) -> bytes:
        archive, data = work.winner(name, packs_on)

        if archive is None:
            raise SkinsError(f"{name}, the texture of {race.race.name}'s {row_label(table, row)}, is in no archive for "
                             f"{label}")

        forged.source_digests[name] = hashlib.sha1(data).hexdigest()
        return data

    # The skin colours: the skin row (section 0, variation 0) of each sex and colour index, the last one as
    # BuildComponentArray takes it.
    transforms: dict[tuple[int, int], recolor.Transform] = {}

    if race.sections:
        skin_rows = {}

        for _, row in rows:
            if table.get(row, "baseSection") == 0 and table.get(row, "variationIndex") == 0:
                skin_rows[(table.get(row, "sexID"), table.get(row, "colorIndex"))] = row

        for sex in sorted({sex for sex, _ in skin_rows}):
            found = {False: {}, True: {}}

            for (s, k), row in sorted(skin_rows.items()):
                if s != sex:
                    continue

                name = source_path(table.get_str(row, "textureName[0]"), race)

                if not name:
                    raise SkinsError(f"{race.race.name}: {row_label(table, row)} names no texture")

                skin = work.skin_colour(read_source(name, row), name, race.settings)
                found[bool(table.get(row, "flags") & DEATH_KNIGHT)][k] = (name, skin)

            # the hue a nearly grey skin's colours are also weighed against (recolor.Transform): the living skins'
            living = recolor.living_hue([skin for _, skin in found[False].values()], race.settings)

            for dk in (False, True):
                if not found[dk]:
                    continue

                goals = recolor.targets({k: skin for k, (_, skin) in found[dk].items()}, race.palette_lab(dk))

                for k, (name, skin) in found[dk].items():
                    transform = work.transform(skin, goals[k], race.settings, living)
                    transforms[(sex, k)] = transform
                    forged.colours.append(Colour(race.name, sex, k, dk, name, skin, goals[k], transform))

    for index, row in rows:
        section = table.get(row, "baseSection")
        sex, colour = table.get(row, "sexID"), table.get(row, "colorIndex")
        recoloured = section in race.sections
        changed = False

        for slot in range(3):
            column = f"textureName[{slot}]"
            name = table.get_str(row, column)

            if not name:
                continue

            source = source_path(name, race)

            if recoloured:
                transform = transforms.get((sex, colour))

                if transform is None:
                    raise SkinsError(f"{race.race.name}: {row_label(table, row)} has skin colour {colour}, but there "
                                     f"is no skin row (section 0, variation 0) of colour {colour} for "
                                     f"{SEXES.get(sex, sex)} to take its colours from")

                data = read_source(source, row)
                digest, texture = work.recoloured(data, source, transform)
                new_name = f"{race.prefix}{digest}\\{source}"

                if len(new_name.encode("utf-8")) > MAX_NAME_BYTES:
                    raise SkinsError(f"{new_name}: {len(new_name.encode('utf-8'))} bytes, longer than the "
                                     f"{MAX_NAME_BYTES} the client takes")

                forged.textures[new_name] = texture
                forged.sources[new_name] = source
                info = blp.parse(data, source)
                forged.source_sizes[new_name] = (info.width, info.height)
            else:
                new_name = source

            if new_name != name:
                table.set_str(row, column, new_name)

            if new_name != forged.before.get_str(forged.before.rows[index], column):
                changed = True

            forged.expected_names[(index, slot)] = new_name

        forged.rows_recoloured += int(recoloured)
        forged.rows_changed += int(changed)
        forged.rows_restored += int(changed and not recoloured)

    forged.previews += previews_of(forged, race, rows, work, packs_on)


def previews_of(forged: Forged, race: SkinRace, rows: list, work: Recolourer, packs_on: frozenset) -> list:
    """For the contact sheets: each skin colour's body texture and its first face's lower and upper textures, before and
    after."""
    if not race.sections:
        return []

    table = forged.after
    out = []

    for colour in [c for c in forged.colours if c.race == race.name]:
        tiles = []
        body = next((row for _, row in reversed(rows) if table.get(row, "baseSection") == 0
                     and table.get(row, "variationIndex") == 0 and table.get(row, "sexID") == colour.sex
                     and table.get(row, "colorIndex") == colour.index), None)
        faces = sorted((table.get(row, "variationIndex"), i) for i, row in rows if table.get(row, "baseSection") == 1
                       and table.get(row, "sexID") == colour.sex and table.get(row, "colorIndex") == colour.index)
        face = table.rows[faces[0][1]] if faces else None

        for label, row, slot in (("body", body, 0), ("face lower", face, 0), ("face upper", face, 1)):
            name = table.get_str(row, f"textureName[{slot}]") if row is not None else ""

            if not name:
                tiles.append((label, None, None))
                continue

            source = source_path(name, race)
            _, data = work.winner(source, packs_on)
            tiles.append((label, data, forged.textures.get(name)))

        out.append((race.name, colour.sex, colour.index, colour.dk, tiles))

    return out


# --- placement ---------------------------------------------------------------------------------------------------


@dataclass
class Target:
    """An archive the plan writes into: its planned files, and what of the race's folder it holds that no plan uses."""
    archive: GameArchive
    files: dict[str, bytes] = field(default_factory=dict)
    labels: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    copy_for: list[str] = field(default_factory=list)  # the combinations whose own CharSections.dbc it gets
    copy_from: list[str] = field(default_factory=list)  # the archives those copies are made from

    @property
    def changed(self) -> bool:
        return bool(self.stale or self.replaced or self.added)


def key_of(name: str) -> bytes:
    return mpqpack.name_key(name)


def owners_of(forged: list[Forged]) -> dict[str, Forged]:
    """For each archive that combinations read CharSections.dbc from (source_holder()): the combination that keeps it,
    the one with the fewest packs."""
    owners: dict[str, Forged] = {}

    def fewest(f: Forged) -> tuple:
        return len(f.packs_on), sorted(f.packs_on)

    for result in forged:
        key = result.holder.client_path.lower()

        if key not in owners or fewest(result) < fewest(owners[key]):
            owners[key] = result

    return owners


def needs_copy(result: Forged, owners: dict[str, Forged]) -> bool:
    owner = owners[result.holder.client_path.lower()]
    return result is not owner and not result.same_result(owner)


def copy_archive(game: Game, result: Forged, owner: Forged, forged: list[Forged]) -> GameArchive:
    """Where a combination whose skins differ from those of owner, which keeps their CharSections.dbc's archive, gets
    its own copy: an archive active for it, of a pack owner lacks, loading above that archive, and read by no
    combination that needs other contents (each combination that loads it and takes CharSections.dbc from below it
    would read the copy). The highest such archive; SkinsError when there is none."""
    holder = result.holder
    candidates = sorted((a for a in game.patchset.active(result.packs_on) if not a.is_base and a.pack is not None
                         and a.pack not in owner.packs_on and a.rank() > holder.rank()), key=lambda a: a.rank(),
                        reverse=True)
    clashes = []

    for archive in candidates:
        others = [f.label for f in forged if archive.pack in f.packs_on and f.holder.rank() < archive.rank()
                  and not f.same_result(result)]

        if not others:
            return archive

        clashes.append(f"{archive.name} (pack {archive.pack}) is loaded by {', '.join(others)} too")

    differing = sorted(p for p, d in result.source_digests.items() if owner.source_digests.get(p) != d)
    packs = sorted(result.packs_on - owner.packs_on)
    text = (f"{result.label} and {owner.label} read the same CharSections.dbc ({holder.name}), but their skins differ: "
            f"{', '.join(differing[:4]) or 'the source textures'}{' ...' if len(differing) > 4 else ''} "
            f"{'is' if len(differing) == 1 else 'are'} another file for {result.label}. The players of {result.label} "
            f"need their own CharSections.dbc and textures in an archive of the pack{'s' if len(packs) != 1 else ''} "
            f"{', '.join(packs) or '-'} that loads after {holder.name} (a Data\\patch-<letter>.MPQ of that pack that "
            "sorts after it)")

    if clashes:
        text += (f" and that no player with other skins loads, and there is none: {'; '.join(clashes)}, whose "
                 "skins differ, and would read that copy. Add an archive to a pack that only those players load")
    else:
        text += ", and there is none. Add such an archive to the pack"

    raise SkinsError(text + " (it may start empty), then run skins again. Nothing was written")


def marker_bytes(target: Target, races: list[SkinRace]) -> bytes:
    """COPY_MARKER for an archive that gets copies of CharSections.dbc (the same bytes on every run)."""
    data = {
        "_readme": "raceforge.py skins put DBFilesClient\\CharSections.dbc into this archive: the copy for the players "
                   "of 'for', made from the CharSections.dbc of 'from' with their own skin textures. Every run of "
                   "skins makes it again from 'from' and removes it when they no longer need it. sha1: the copy's.",
        "for": target.copy_for,
        "from": target.copy_from,
        "races": [r.name for r in races],
        "sha1": hashlib.sha1(target.files[CHAR_SECTIONS]).hexdigest(),
    }
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


def place(game: Game, forged: list[Forged], races: list[SkinRace]) -> dict[str, Target]:
    """Which archive gets which files (see the module's docstring); SkinsError when a combination has nowhere to go."""
    targets: dict[str, Target] = {}

    def put(archive: GameArchive, result: Forged, reason: str, labels: list[str]):
        target = targets.setdefault(archive.client_path.lower(), Target(archive))
        target.labels += labels
        target.reasons.append(reason)

        spelled = {key_of(n): n for n in target.files}

        for name, data in [(CHAR_SECTIONS, result.data)] + sorted(result.textures.items()):
            known = spelled.get(key_of(name))

            if known is not None and target.files[known] != data:
                raise SkinsError(f"{archive.name} would need two different copies of {name} (for "
                                 f"{', '.join(target.labels)})")

            target.files[known or name] = data

    owners = owners_of(forged)

    for key, owner in owners.items():
        group = [f for f in forged if f.holder.client_path.lower() == key]
        holder = owner.holder
        alike = [f.label for f in group if not needs_copy(f, owners)]
        put(holder, owner, f"holds the CharSections.dbc and textures of {', '.join(alike)}", alike)

        for result in group:
            if not needs_copy(result, owners):
                continue

            differing = sorted(p for p, d in result.source_digests.items() if owner.source_digests.get(p) != d)
            archive = copy_archive(game, result, owner, forged)
            more = " ..." if len(differing) > 3 else ""
            put(archive, result, f"holds {result.label}'s own CharSections.dbc and textures "
                                 f"({', '.join(differing[:3])}{more} differ from {owner.label}'s), above {holder.name}",
                [result.label])
            target = targets[archive.client_path.lower()]
            target.copy_for.append(result.label)

            if holder.client_path not in target.copy_from:
                target.copy_from.append(holder.client_path)

    for target in targets.values():
        if target.copy_for:
            target.files[COPY_MARKER] = marker_bytes(target, races)

    # a copy that no combination needs now goes, with its textures: its players read the CharSections.dbc below again
    for key, marker in sorted(game.copies.items()):
        if key not in targets:
            target = targets[key] = Target(game.archive(key))
            readers = ", ".join(f.label for f in forged if target.archive.name in f.passed) or "nobody"
            labels = ", ".join(map(str, marker.get("for") or []))
            target.reasons.append(f"loses skins' own copy of CharSections.dbc (for {labels}), which no combination "
                                  f"needs now: {readers} read the one below it again")

    prefixes = [r.prefix.lower() for r in races]

    for key, target in targets.items():
        archive = target.archive
        planned = {key_of(n) for n in target.files}
        own = {key_of(COPY_MARKER)} | ({key_of(CHAR_SECTIONS)} if key in game.copies else set())

        for name in archive.reader.names():
            normal = name.replace("/", "\\").lower()

            if (any(normal.startswith(p) for p in prefixes) or key_of(name) in own) and key_of(name) not in planned:
                target.stale.append(name)

        for name, data in sorted(target.files.items()):
            if not archive.has(name):
                target.added.append(name)
            elif archive.read(name) != data:
                target.replaced.append(name)
            else:
                target.unchanged.append(name)

    return targets


def leftovers(game: Game, targets: dict[str, Target], races: list[SkinRace]) -> list[str]:
    """Archives the plan does not write that hold files of the races' folders (an earlier run's): left as they are."""
    prefixes = [r.prefix.lower() for r in races]
    out = []

    for archive in game.archives:
        if archive.client_path.lower() in targets or archive.is_base or archive.reader is None:
            continue

        names = [n for n in archive.reader.names() if any(n.replace("/", "\\").lower().startswith(p) for p in prefixes)]

        if names:
            out.append(f"{archive.name} holds {len(names)} file(s) of {', '.join(r.prefix for r in races)} that "
                       "nothing uses now; left as they are (no plan writes that archive)")

    return out


# --- the client's view -------------------------------------------------------------------------------------------


class View:
    """What the client reads, file by file, when some archives hold other contents than the realm's: the planned ones
    (from targets) or the written ones (from readers)."""

    def __init__(self, game: Game, targets: dict[str, Target] | None = None,
                 readers: dict[str, patches.PatchArchive] | None = None):
        self.game = game
        self.planned = {}

        for key, target in (targets or {}).items():
            self.planned[key] = ({key_of(n): d for n, d in target.files.items()}, {key_of(n) for n in target.stale})

        self.readers = readers or {}

    def has(self, archive: GameArchive, name: str) -> bool:
        key = archive.client_path.lower()

        if key in self.readers:
            return self.readers[key].has_file(name)

        if key in self.planned:
            files, stale = self.planned[key]

            if key_of(name) in files:
                return True

            if key_of(name) in stale:
                return False

        return archive.has(name)

    def read(self, archive: GameArchive, name: str) -> bytes:
        key = archive.client_path.lower()

        if key in self.readers:
            return self.readers[key].read(name)

        if key in self.planned and key_of(name) in self.planned[key][0]:
            return self.planned[key][0][key_of(name)]

        return archive.read(name)

    def top(self, name: str, packs_on: frozenset) -> GameArchive | None:
        holders = [a for a in self.game.patchset.active(packs_on) if self.has(a, name)]
        return holders[-1] if holders else None


def view_problems(view: View, forged: list[Forged]) -> list[str]:
    """For every combination: the CharSections.dbc the client reads must be its forged copy, and each new texture
    name must resolve to the expected bytes."""
    problems = []

    for result in forged:
        holder = view.top(CHAR_SECTIONS, result.packs_on)

        if holder is None:
            problems.append(f"{result.label}: no archive holds {CHAR_SECTIONS}")
            continue

        if view.read(holder, CHAR_SECTIONS) != result.data:
            problems.append(f"{result.label}: the client would read {holder.name}'s {CHAR_SECTIONS}, which is not this "
                            "combination's forged copy")

        wrong = []

        for name, data in sorted(result.textures.items()):
            archive = view.top(name, result.packs_on)

            if archive is None or view.read(archive, name) != data:
                wrong.append(f"{name} ({'missing' if archive is None else f'{archive.name} holds other bytes'})")

        if wrong:
            problems.append(f"{result.label}: {len(wrong)} texture(s) do not resolve to the recoloured files: "
                            f"{'; '.join(wrong[:3])}")

    return problems


# --- the whole run -----------------------------------------------------------------------------------------------


@dataclass
class Plan:
    game: Game
    races: list[SkinRace]
    forged: list[Forged]
    targets: dict[str, Target]
    leftovers: list[str]

    @property
    def writes(self) -> list[Target]:
        return [t for t in sorted(self.targets.values(), key=lambda t: t.archive.rank()) if t.changed]


def make_plan(game: Game, config: Config, races: list[SkinRace]) -> Plan:
    """Everything decided, nothing written: SkinsError when the realm does not fit."""
    unreadable = [f"{a.name}: {a.error}" for a in game.archives if a.reader is None]

    if unreadable:
        # an archive the tool cannot read might hold a later copy of CharSections.dbc or a texture
        raise SkinsError("cannot read every archive the client loads, so the copies it reads are unknown: "
                         + "; ".join(unreadable))

    configurations = game.patchset.configurations()
    subset = dataclasses.replace(config, races=[r.race for r in races])
    problems = []

    for label, packs_on in configurations:
        holder = game.patchset.top(CHR_RACES, packs_on)

        if holder is None:
            problems.append(f"no archive holds {CHR_RACES} for {label}")
            continue

        try:
            table = DbcTable.from_bytes(holder.read(CHR_RACES), schema_access.get("ChrRaces"),
                                        f"{holder.name}: ChrRaces.dbc")
        except (patches.PatchError, DbcError) as e:
            raise SkinsError(str(e)) from None

        problems += update.race_problems(subset, table, f"{holder.name}, for {label}", "skins")

    if problems:
        raise SkinsError("; ".join(dict.fromkeys(problems)))

    game.copies = find_copies(game)
    work = Recolourer(game)
    forged = [forge(game, label, packs_on, races, work) for label, packs_on in configurations]
    owners = owners_of(forged)

    # a combination that gets a copy of its own: made from the forged copy of the one that keeps the archive (forge())
    for i, result in enumerate(forged):
        if needs_copy(result, owners):
            owner = owners[result.holder.client_path.lower()]
            forged[i] = forge(game, result.label, result.packs_on, races, work, base=owner.data)

    targets = place(game, forged, races)
    problems = view_problems(View(game, targets), forged)

    if problems:
        raise SkinsError("the planned archives would not give every player the new skins, so nothing is written: "
                         + "; ".join(problems))

    for target in targets.values():
        if target.changed:
            try:
                # refuses an archive that cannot be copied whole (no listfile, files it does not list)
                patches.archive_contents(target.archive.reader, target.archive.name)
            except patches.PatchError as e:
                raise SkinsError(str(e)) from None

    return Plan(game, races, forged, targets, leftovers(game, targets, races))


def space_needed(plan: Plan) -> int:
    """Bytes --out needs for the rebuilt archives: each written whole, plus the largest one's files unpacked while it is
    rebuilt (patches.rebuild stages them), plus a margin."""
    total, staging = SPACE_MARGIN, 0

    for target in plan.writes:
        reader = target.archive.reader
        total += target.archive.size + sum(len(d) for d in target.files.values())
        staging = max(staging, sum(b.file_size for b in reader.blocks if b.flags & mpqpack.FILE_EXISTS))

    return total + staging


def free_space(folder: str) -> int:
    path = os.path.abspath(folder)

    while not os.path.exists(path):
        path = os.path.dirname(path)

    return shutil.disk_usage(path).free


def entries_size(out_dir: str, entries: tuple[str, ...]) -> int:
    """Bytes of the earlier output --force removes (it frees that space before the archives are written)."""
    total = 0

    for entry in entries:
        path = os.path.join(out_dir, entry)

        if os.path.isfile(path):
            total += os.path.getsize(path)
        elif os.path.isdir(path):
            for root, _, files in os.walk(path):
                paths = [os.path.join(root, f) for f in files]
                total += sum(os.path.getsize(p) for p in paths if not os.path.islink(p))

    return total


def gb(n: int) -> str:
    return f"{n / 1e9:.1f} GB"


def write(plan: Plan, out_dir: str) -> dict[str, str]:
    """Rebuild every archive that changes into out/client, at its place in the folder it came from (client/enUS/ for a
    locale patch): {client path (lower case): written file}."""
    written = {}

    for target in plan.writes:
        archive = target.archive
        staging = os.path.join(out_dir, "merged", archive.name)
        replacements = {}

        for i, (name, data) in enumerate(sorted(target.files.items())):
            path = os.path.join(staging, f"{i:06d}")
            os.makedirs(staging, exist_ok=True)

            with open(path, "wb") as f:
                f.write(data)

            replacements[name] = path

        out_path = os.path.join(out_dir, "client", *archive.rel.split("/"))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        stale = {key_of(n) for n in target.stale}

        try:
            patches.rebuild(archive, replacements, out_path, os.path.join(out_dir, "staging"),
                            drop=lambda n: key_of(n) in stale)
        except patches.PatchError as e:
            raise SkinsError(str(e)) from None
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        written[archive.client_path.lower()] = out_path

    shutil.rmtree(os.path.join(out_dir, "merged"), ignore_errors=True)
    return written


def rows_problems(before: DbcTable, after: DbcTable, result: Forged) -> list[str]:
    """Every row as it was, field for field (strings as text), apart from the texture names of the skinned races'
    rows, which must be the planned ones."""
    if len(before.rows) != len(after.rows):
        return [f"{len(after.rows)} rows, the realm's copy has {len(before.rows)}"]

    problems = []
    columns = before.schema.columns

    for index, (old, new) in enumerate(zip(before.rows, after.rows)):
        for c, column in enumerate(columns):
            a = before.string_at(old[c]) if column.is_string else old[c]
            b = after.string_at(new[c]) if column.is_string else new[c]

            if index in result.race_rows and column.name.startswith("textureName["):
                slot = int(column.name[12])
                expected = result.expected_names.get((index, slot), a)

                if b != expected:
                    problems.append(f"{row_label(after, new)} {column.name} is {b!r}, not {expected!r}")
            elif a != b:
                problems.append(f"{row_label(after, new)} {column.name} changed")

    return problems


def check(plan: Plan, written: dict[str, str]) -> Validation:
    """Re-read what was written (or, when nothing was, the realm as it is) and check it."""
    result = Validation()
    readers = {}

    try:
        for key, path in sorted(written.items()):
            target = plan.targets[key]
            name = target.archive.name

            try:
                reader = patches.PatchArchive(path)
            except (mpqpack.MpqError, OSError) as e:
                result.add("FAIL", f"{name}: the written archive opens", str(e))
                continue

            readers[key] = reader
            report = reader.verify()
            result.expect(not report.problems, f"{name}: passes the client reader's checks",
                          "; ".join(report.problems[:5]))
            before = {key_of(n) for n in target.archive.reader.names()}
            after = {key_of(n) for n in reader.names()}
            stale = {key_of(n) for n in target.stale}
            planned = {key_of(n) for n in target.files}
            lost = before - stale - after
            extra = after - before - planned
            result.expect(not lost and not extra and not (after & stale),
                          f"{name}: every other file of the realm's archive is still there ({len(before)} before, "
                          f"{len(after)} after, {len(target.stale)} dropped, {len(target.added)} added)",
                          f"{len(lost)} lost, {len(extra)} unexpected, {len(after & stale)} not dropped")
            wrong = [n for n, d in target.files.items() if not reader.has_file(n) or reader.read(n) != d]
            result.expect(not wrong, f"{name}: holds the {len(target.files)} planned files byte for byte",
                          "; ".join(wrong[:3]))

        view = View(plan.game, readers=readers)

        for forged in plan.forged:
            label = forged.label
            holder = view.top(CHAR_SECTIONS, forged.packs_on)
            problems = view_problems(view, [forged])
            result.expect(not problems, f"{label}: the client reads the forged {CHAR_SECTIONS} (from "
                          f"{holder.name if holder else 'nowhere'}) and its {len(forged.textures)} new texture names "
                          "resolve to the recoloured files", "; ".join(problems))

            if holder is None:
                continue

            try:
                table = DbcTable.from_bytes(view.read(holder, CHAR_SECTIONS), schema_access.get("CharSections"))
            except DbcError as e:
                result.add("FAIL", f"{label}: {CHAR_SECTIONS} parses", str(e))
                continue

            problems = rows_problems(forged.before, table, forged)
            others = len(forged.before.rows) - len(forged.race_rows)
            names = ", ".join(r.race.name for r in plan.races)
            result.expect(not problems, f"{label}: {len(forged.before.rows)} CharSections rows in the same order; "
                          f"{others} rows of other races and the races' rows of other sections unchanged field for "
                          f"field; {forged.rows_recoloured} rows of {names} on recoloured textures",
                          "; ".join(problems[:5]))
            bad = []

            for name in sorted(forged.textures):
                archive = view.top(name, forged.packs_on)

                if archive is None:
                    continue  # reported by view_problems

                data = view.read(archive, name)
                bad += blp.check(data, name, *forged.source_sizes[name])

            result.expect(not bad, f"{label}: {len(forged.textures)} new textures parse as the client reads them, have "
                          "their source's size and decode", "; ".join(bad[:3]))
    finally:
        for reader in readers.values():
            reader.close()

    return result


# --- previews ----------------------------------------------------------------------------------------------------


def tile(data: bytes | None, where: str, size: int = PREVIEW_TILE):
    """A texture scaled into size x size (the smallest level at least that big, box-filtered), on grey; None: empty."""
    import blpconvert  # noqa: E402  (Tools/BlpConvert, on sys.path through Tools/MapForge/dbc)

    out = blpconvert.Image(size, size, bytearray(b"\x40\x40\x40\xff" * (size * size)))

    if data is None:
        return out

    try:
        info = blp.parse(data, where)
        level = 0

        while level + 1 < len(info.levels) and max(info.levels[level + 1].width, info.levels[level + 1].height) >= size:
            level += 1

        w, h, rgba = blp.decode(data, where, level)
    except blp.BlpError:
        return out

    scale = max(w, h) / size
    tw, th = max(1, round(w / scale)), max(1, round(h / scale))
    ox, oy = (size - tw) // 2, (size - th) // 2

    for y in range(th):
        y0, y1 = int(y * scale), max(int(y * scale) + 1, int((y + 1) * scale))

        for x in range(tw):
            x0, x1 = int(x * scale), max(int(x * scale) + 1, int((x + 1) * scale))
            acc = [0, 0, 0, 0]
            n = 0

            for sy in range(y0, min(y1, h)):
                for sx in range(x0, min(x1, w)):
                    o = 4 * (sy * w + sx)
                    a = rgba[o + 3]
                    acc[0] += rgba[o] * a
                    acc[1] += rgba[o + 1] * a
                    acc[2] += rgba[o + 2] * a
                    acc[3] += a
                    n += 1

            o = 4 * ((oy + y) * size + ox + x)
            alpha = acc[3] / max(1, n) / 255

            for c in range(3):
                colour = acc[c] / acc[3] if acc[3] else 0
                out.data[o + c] = int(round(colour * alpha + 0x40 * (1 - alpha)))

    return out


def contact_sheet(rows: list[list], path: str):
    """rows of tiles (blpconvert Images of one size) into one PNG, pairs of columns grouped."""
    import blpconvert  # noqa: E402

    if not rows:
        return

    size = rows[0][0].width
    pad, gap = 4, 12
    columns = len(rows[0])
    width = pad + columns * (size + pad) + (columns // 2 - 1) * gap
    height = pad + len(rows) * (size + pad)
    sheet = blpconvert.Image(width, height, bytearray(b"\x18\x18\x18\xff" * (width * height)))

    for r, tiles in enumerate(rows):
        for c, image in enumerate(tiles):
            x0 = pad + c * (size + pad) + (c // 2) * gap
            y0 = pad + r * (size + pad)

            for y in range(size):
                o = 4 * ((y0 + y) * width + x0)
                sheet.data[o:o + 4 * size] = image.data[4 * y * size:4 * (y + 1) * size]

    blpconvert.write_png(path, sheet)


def write_previews(plan: Plan, out_dir: str) -> list[str]:
    """preview/<race>-<sex>[-<combination>].png: per skin colour (a row, lightest skin first), the body texture and
    its first face's lower and upper textures, each before and after. One set per distinct result."""
    folder = os.path.join(out_dir, "preview")
    os.makedirs(folder, exist_ok=True)
    paths = []
    done = []

    for forged in plan.forged:
        if any(forged.same_result(other) for other in done):
            continue

        suffix = "" if not done else "-" + re.sub(r"[^A-Za-z0-9]+", "-", forged.label).strip("-")
        done.append(forged)
        by_sheet: dict[tuple[str, int], list] = {}

        for race, sex, index, dk, tiles in forged.previews:
            by_sheet.setdefault((race, sex), []).append((dk, index, tiles))

        for (race, sex), entries in sorted(by_sheet.items()):
            lightness = {(c.dk, c.index): c.skin.L for c in forged.colours if c.race == race and c.sex == sex}
            rows = []

            for dk, index, tiles in sorted(entries, key=lambda e: (e[0], -lightness.get((e[0], e[1]), 0), e[1])):
                row = []

                for label, before, after in tiles:
                    row.append(tile(before, label))
                    row.append(tile(after if after is not None else before, label))

                rows.append(row)

            path = os.path.join(folder, f"{race}-{SEXES.get(sex, sex)}{suffix}.png")
            contact_sheet(rows, path)
            paths.append(path)

    return paths


# --- the report ----------------------------------------------------------------------------------------------------


def colour_text(lch: tuple) -> str:
    L, C, h = lch
    return "#%02X%02X%02X" % recolor.oklab_to_srgb8(L, C * math.cos(math.radians(h)), C * math.sin(math.radians(h)))


def format_report(plan: Plan, args, written: dict[str, str], result: Validation, previews: list[str],
                  up_to_date: bool) -> str:
    game = plan.game
    lines = ["RaceForge skins report", "======================", ""]
    lines.append(f"Game folder (--client): {os.path.abspath(args.client)} (Data: {game.client_data}, "
                 f"locale {game.locale})")
    lines.append(f"Realm patches (--patches): {os.path.abspath(args.patches)}")
    lines.append(f"Config: {os.path.abspath(args.config)}; skins: {os.path.abspath(args.skins)}")
    lines.append(f"Pack combinations: {', '.join(f.label for f in plan.forged)}")
    lines.append("")
    lines.append("Archives the client loads (lowest first)")
    lines.append("----------------------------------------")

    for archive in game.archives:
        kind = "base" if archive.is_base else "patch"
        pack = f", pack {archive.pack}" if archive.pack else ""
        lines.append(f"{archive.client_path}: {kind}, {archive.where()}{pack}")

    lines.append("")
    lines.append("Races")
    lines.append("-----")

    for race in plan.races:
        sections = (", ".join(f"{s} {SECTION_NAMES[s]}" for s in race.sections)
                    or "none (every row back on its original textures)")
        lines.append(f"{race.race.name} (race {race.race.id}, {race.name}): sections {sections}")
        lines.append(f"  palette {' '.join(race.palette)}; Death Knights {' '.join(race.dk_palette)}")

    for forged in plan.forged:
        if any(forged.same_result(other) for other in plan.forged[:plan.forged.index(forged)]):
            continue

        lines.append(f"Skin colours for {forged.label} (OKLab L C h of the skin -> target, gamma):")

        for colour in sorted(forged.colours, key=lambda c: (c.race, c.sex, c.dk, c.index)):
            skin = colour.skin
            dk = " (Death Knight)" if colour.dk else ""
            L, C, h = colour.target
            living = colour.transform.living_hue
            grey = "" if living is None else f", nearly grey: also weighed against the living skins' hue {living:.1f}"
            lines.append(f"  {colour.race} {SEXES.get(colour.sex, colour.sex)} colour {colour.index}{dk}: "
                         f"{skin.L:.3f} {skin.C:.3f} {skin.h:.1f} ({colour_text((skin.L, skin.C, skin.h))}) -> "
                         f"{L:.3f} {C:.3f} {h:.1f} ({colour_text(colour.target)}), gamma {colour.transform.gamma:.2f}"
                         f"{grey}; {colour.texture}")

    lines.append("")
    lines.append("Combinations")
    lines.append("------------")

    for forged in plan.forged:
        lines.append(f"{forged.label}: {CHAR_SECTIONS} from {forged.holder.name} ({forged.holder.where()}); "
                     f"{forged.rows_recoloured} rows on {len(forged.textures)} recoloured textures, "
                     f"{forged.rows_changed} rows changed"
                     + (f" ({forged.rows_restored} back on their original textures)" if forged.rows_restored else ""))

        if forged.passed:
            lines.append(f"    passing over {', '.join(forged.passed)}: its {CHAR_SECTIONS} is skins' own copy, made "
                         f"again from {forged.holder.name}'s")

    lines.append("")
    lines.append("Where the files go")
    lines.append("------------------")

    for target in sorted(plan.targets.values(), key=lambda t: t.archive.rank()):
        state = "rebuilt" if target.changed else "already up to date"
        lines.append(f"{target.archive.name} ({target.archive.where()}): {state}")

        for reason in dict.fromkeys(target.reasons):
            lines.append(f"    {reason}")

        lines.append(f"    {len(target.added)} added, {len(target.replaced)} replaced, {len(target.unchanged)} already "
                     f"there, {len(target.stale)} dropped (files of the races' folders, and skins' own copy of "
                     "CharSections.dbc, that the plan no longer uses)")

        for name in target.replaced:
            lines.append(f"    replaced: {name}")

        for name in target.stale[:20]:
            lines.append(f"    dropped: {name}")

    warnings = game.warnings + plan.leftovers

    if game.notes:
        lines.append("")
        lines.append("Notes")
        lines.append("-----")
        lines.extend(f"- {n}" for n in game.notes)

    if warnings:
        lines.append("")
        lines.append("Warnings")
        lines.append("--------")
        lines.extend(f"- {w}" for w in warnings)

    lines.append("")
    lines.append("Checks")
    lines.append("------")

    for c in result.checks:
        lines.append(f"[{c.status}] {c.name}" + (f" -- {c.detail}" if c.detail and c.status != "PASS" else ""))

    lines.append("")
    lines.append(f"{len(result.checks)} checks, {len(result.failed)} failed")
    lines.append("")
    lines.append("Output")
    lines.append("------")

    if up_to_date:
        lines.append("Client archives: none, already up to date")

    for key, path in sorted(written.items()):
        lines.append(f"Client archive: {path}")

    for path in previews:
        lines.append(f"Preview: {path}")

    return "\n".join(lines) + "\n"


def summary(plan: Plan, out_dir: str, written: dict[str, str], result: Validation, up_to_date: bool) -> str:
    """The lines the owner pastes back."""
    lines = []

    for race in plan.races:
        sections = ", ".join(SECTION_NAMES[s] for s in race.sections) or "none"
        lines.append(f"{race.race.name} (race {race.race.id}): sections {sections}")

    for forged in plan.forged:
        target = next((t for t in plan.targets.values() if forged.label in t.labels), None)
        where = target.archive.name if target else forged.holder.name
        lines.append(f"  {forged.label}: CharSections.dbc from {forged.holder.name}; {forged.rows_recoloured} rows on "
                     f"{len(forged.textures)} recoloured textures ({forged.rows_changed} rows changed) -> {where}")

    if up_to_date:
        lines.append("already up to date: no archive needs to change")
    else:
        for key, path in sorted(written.items()):
            target = plan.targets[key]
            lines.append(f"  written: {path} ({gb(os.path.getsize(path))}; {len(target.added)} added, "
                         f"{len(target.replaced)} replaced, {len(target.stale)} dropped)")

    lines.append(f"{len(result.checks)} checks, {len(result.failed)} failed "
                 f"(report: {os.path.join(out_dir, 'report.txt')})")
    return "\n".join(lines)


def manifest_entries(plan: Plan, written: dict[str, str]) -> list[dict]:
    """install.json's archives: each written archive with the file it replaces as the tool read it."""
    entries = []

    for key, path in sorted(written.items()):
        archive = plan.targets[key].archive
        entries.append(install.entry(archive.rel, archive.client_path, archive.origin, archive.path, archive.size,
                                     archive.mtime_ns, path))

    return entries
