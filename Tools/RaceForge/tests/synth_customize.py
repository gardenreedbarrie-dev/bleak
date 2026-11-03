r"""A made-up Bleakhold realm and a made-up customization package for the customize tests (no Blizzard or Ascension
data: every row, name, pixel and model here is invented).

The realm (make_realm()) is laid out as the launcher's folders are:

- client/Data/common.MPQ: the stock textures and stock models of the races; client/Data/enUS/locale-enUS.MPQ: the
  stock tables (tests/synth.py's, with the appearance tables of stock_rows());
- patches/Patch-R.MPQ, the realm's race patch: ChrRaces with High Elf in slot 15 (the Blood Elf's row) and Eredar in
  slot 19 (the Draenei's), as on the live realm; CharSections, CharHairGeosets, CharacterFacialHairStyles and
  BarberShopStyle with races 15 and 19 copied from 10 and 11 (race 15's skin and face rows on
  Character\BleakholdSkins\HighElf\<hash>\ names, as skins left them); HelmetGeosetVisData with bit 15 = bit 10, bit
  19 = bit 11 and a Pandaren bit 20; one other art file and an old purple texture;
- patches/patch-A.MPQ, the HD pack's: its own Blood Elf female model and .anim under the stock names.

The package (make_package()) has DBFilesClient\*.dbc and Character\ art as Ascension's does: rows of races 1-11 that
move the Death Knight skins (old 4-6 to 8-10, an NPC-only skin at 4, three new skins), Death Knight skins with two
faces only, two more faces, a fourth hair style, new hair colours (Human female's colours 1 and 2 swapped), a repeated
features row; rows of the package's races 12-21 (Skeleton 15, Taunka 19) and Goblin (9) that must be dropped; a
missing scalp texture (rebuilt) and a features texture with no source; models with the geosets the rows need, an .anim
each and their own deathKnightEyeGlow.blp; a Goblin folder that is not shipped. Its .git/HEAD is COMMIT.
"""

from __future__ import annotations

import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from rflib import appearance as ap  # noqa: E402
from rflib import schema_access  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402
from tests import synth, synth_skins  # noqa: E402

COMMIT = "0123456789abcdef0123456789abcdef01234567"
RICH = (1, 10, 11)  # races with the full layout; the others have one of everything
SEX = ("Male", "Female")
TONES = [(246, 222, 206), (232, 192, 164), (210, 160, 128), (180, 130, 100), (214, 210, 214), (190, 150, 120),
         (160, 120, 90), (130, 100, 80)]
HAIR = [(40, 30, 20), (120, 80, 40), (200, 160, 90), (220, 220, 220), (90, 40, 30), (60, 60, 120)]
MISSING_SCALP = "Character\\BloodElf\\Female\\BloodElfFemaleScalpLowerHair00_05.blp"  # rebuilt from colour 4
NO_SOURCE = "HumanMaleFacialLowerHair02_"  # Human male features value 2: no package source, so no paint at 4 and 5
GEOSETS = [0, 1, 2, 3, 4, 101, 102, 103, 301, 401, 501, 1301, 1701, 1702, 1703, 2001]


def rf(race: int) -> str:
    return synth.FILE_STRINGS[race]


def tex(race: int, sex: int, what: str) -> str:
    return f"Character\\{rf(race)}\\{SEX[sex]}\\{rf(race)}{SEX[sex]}{what}.blp"


# --- rows ------------------------------------------------------------------------------------------------------


def appearance(race: int, sex: int, package: bool) -> dict:
    """{"cs": [(section, variation, colour, flags, (t0, t1, t2))], "cfhs": [(variation, geosets)], "chg": [(variation,
    geoset)], "barber": [(type, data, name)]} of one race and sex."""
    cs, cfhs, chg, barber = [], [], [], []
    normal = 0x11 if package else 0x1

    if race not in RICH:
        cs.append((0, 0, 0, normal, (tex(race, sex, "Skin00_00"), "", "")))
        cs.append((4, 0, 0, normal, (tex(race, sex, "NakedPelvisSkin00_00"), tex(race, sex, "NakedTorsoSkin00_00"), "")))
        cs.append((1, 0, 0, 0x1, (tex(race, sex, "FaceLower00_00"), tex(race, sex, "FaceUpper00_00"), "")))
        cs.append((3, 0, 0, normal, (f"Character\\{rf(race)}\\Hair00_00.blp", "", "")))
        cfhs.append((0, (0, 0, 0, 0, 0)))
        chg.append((0, 1))
        barber += [(0, 0, "Style 0"), (2, 0, "Feature 0")]

        if package and race == 6:
            barber.append((3, 0, ""))  # the real package's Tauren skin rows have no name

        return {"cs": cs, "cfhs": cfhs, "chg": chg, "barber": barber}

    # skins: (colour, tag, flags)
    if package:
        skins = [(c, f"{c:02d}", 0x11) for c in range(4)] + [(4, "100", 0x8)] + \
                [(5, "15", 0x11), (6, "16", 0x11), (7, "17", 0x11)] + [(8, "04", 0x5), (9, "05", 0x5), (10, "06", 0x5)]
    else:
        skins = [(c, f"{c:02d}", 0x1) for c in range(4)] + [(c, f"{c:02d}", 0x5) for c in range(4, 7)]

    for colour, tag, flags in skins:
        cs.append((0, 0, colour, flags, (tex(race, sex, f"Skin00_{tag}"), tex(race, sex, f"Skin00_{tag}_Extra")
                                         if package else "", "")))
        cs.append((4, 0, colour, flags, (tex(race, sex, f"NakedPelvisSkin00_{tag}"),
                                         tex(race, sex, f"NakedTorsoSkin00_{tag}"), "")))
        dk_skin = bool(flags & 0x4)

        if flags & 0x8:
            continue  # the package's NPC-only skins have no faces

        if package and dk_skin:
            faces = [(0, 0x5), (2, 0x5)]
        elif package:
            faces = [(v, 0x1) for v in range(4)] + [(4, 0x5), (5, 0x5)]
        else:
            faces = [(v, 0x5 if dk_skin else 0x1) for v in range(3)]

        for variation, face_flags in faces:
            cs.append((1, variation, colour, face_flags, (tex(race, sex, f"FaceLower{variation:02d}_{tag}"),
                                                          tex(race, sex, f"FaceUpper{variation:02d}_{tag}"), "")))

    # hair: (colour, flags, texture colour)
    if package:
        colours = [(0, 0x11, 0), (1, 0x11, 1), (2, 0x11, 2), (3, 0x5, 3), (4, 0x11, 4), (5, 0x11, 5)]

        if race == 1 and sex == 1:
            colours[1], colours[2] = (1, 0x11, 2), (2, 0x11, 1)  # the package swapped two colours
    else:
        colours = [(0, 0x1, 0), (1, 0x1, 1), (2, 0x1, 2), (3, 0x5, 3)]

    styles = 4 if package else 3

    for style in range(styles):
        for colour, flags, t in colours:
            cs.append((3, style, colour, flags, (f"Character\\{rf(race)}\\Hair00_{t:02d}.blp",
                                                 tex(race, sex, f"ScalpLowerHair{style:02d}_{t:02d}"),
                                                 tex(race, sex, f"ScalpUpperHair{style:02d}_{t:02d}"))))

        chg.append((style, style + 1))
        barber.append((0, style, f"Style {style}"))

    b = 3 if sex == 0 else 2

    for variation in range(b):
        cfhs.append((variation, (variation, 0, 0, 0, 2 if variation == 1 else 0)))
        barber.append((2, variation, f"Feature {variation}"))

        if sex == 0:
            for colour, flags, t in colours:
                cs.append((2, variation, colour, flags, (tex(race, sex, f"FacialLowerHair{variation:02d}_{t:02d}"),
                                                         tex(race, sex, f"FacialUpperHair{variation:02d}_{t:02d}"), "")))

    if package and race == 10 and sex == 0:
        # a repeated features row: the first is hidden, the last (the one the client uses) is not
        cs.insert(next(i for i, r in enumerate(cs) if r[0] == 2), (2, 1, 0, 0x8, ("", "", "")))

    return {"cs": cs, "cfhs": cfhs, "chg": chg, "barber": barber}


def tables(package: bool, realm: bool = False) -> dict[str, bytes]:
    """The appearance tables: the stock ones (the realm's base), the realm's race patch copies (realm=True: races 15 and
    19 copied from 10 and 11) or the package's."""
    cs = synth.Packer("CharSections")
    hair = synth.Packer("CharHairGeosets")
    facial = synth.Packer("CharacterFacialHairStyles")
    barber = synth.Packer("BarberShopStyle")
    ids = {"cs": 1, "hair": 1, "barber": 3}
    races = list(ap.PACKAGE_RACES)

    def add(race: int, source: int, prefix: str = ""):
        for sex in (0, 1):
            data = appearance(source, sex, package)

            for section, variation, colour, flags, textures in data["cs"]:
                names = [(f"{prefix}{t}" if prefix and t and section in (0, 1) else t) for t in textures]
                cs.add(id=ids["cs"], raceID=race, sexID=sex, baseSection=section, flags=flags, variationIndex=variation,
                       colorIndex=colour, **{f"textureName[{i}]": n for i, n in enumerate(names)})
                ids["cs"] += 1

            for variation, geosets in data["cfhs"]:
                facial.add(raceID=race, sexID=sex, variationID=variation, **{f"geoset[{g}]": v for g, v in
                                                                              enumerate(geosets)})

            for variation, geoset in data["chg"]:
                hair.add(id=ids["hair"], raceID=race, sexID=sex, variationID=variation, geosetID=geoset, showscalp=1)
                ids["hair"] += 1

            for kind, value, name in data["barber"]:
                barber.add(id=ids["barber"], type=kind, costModifier=1.0 if kind == 0 else 0.75, race=race, sex=sex,
                           data=value, **synth.loc("displayName", name), **synth.loc("description", ""))
                ids["barber"] += 1

    for race in races:
        add(race, race)

    if realm:
        add(15, 10, "Character\\BleakholdSkins\\HighElf\\0123456789\\")
        add(19, 11)

    # rows customize must never take: Goblin (9) and the package's NPC races (Skeleton 15, Taunka 19, ...)
    for race in (9, 15, 19, 21) if package else (9,):
        for sex in (0, 1):
            cs.add(id=ids["cs"], raceID=race, sexID=sex, baseSection=0, flags=0x1, variationIndex=0, colorIndex=0,
                   **{"textureName[0]": f"Character\\{'Goblin' if race == 9 else 'Skeleton'}\\{SEX[sex]}\\Npc{race}.blp"})
            ids["cs"] += 1
            hair.add(id=ids["hair"], raceID=race, sexID=sex, variationID=0, geosetID=0, showscalp=1)
            ids["hair"] += 1
            facial.add(raceID=race, sexID=sex, variationID=0)

    cs.rows.sort(key=lambda r: (r["raceID"], r["sexID"], r["baseSection"], r["variationIndex"], r["colorIndex"]))
    helmets = synth.Packer("HelmetGeosetVisData")

    if package:
        masks = [(1 << 10 | 1 << 20, 0, 0, 0, 0, 0, 0), (1 << 11 | 1 << 1, 1 << 11, 0, 0, 0, 0, 0),
                 (0x7FFFFFFE, 0, 0, 0, 0, 0, 0), (1 << 1, 0, 0, 0, 0, 0, 0), (1 << 4, 0, 0, 0, 0, 0, 0)]
    else:
        masks = [(1 << 10 | 1 << 15, 0, 0, 0, 0, 0, 0), (1 << 11 | 1 << 19, 1 << 11 | 1 << 19, 0, 0, 0, 0, 0),
                 (0x7FFFFFFE, 0, 0, 0, 0, 0, 0), (1 << 1 | 1 << 20, 0, 0, 0, 0, 0, 0)]

    for i, row in enumerate(masks):
        helmets.add(id=i + 1, **{f"hideGeoset[{g}]": m for g, m in enumerate(row)})

    return {"CharSections": cs.pack(), "CharHairGeosets": hair.pack(), "CharacterFacialHairStyles": facial.pack(),
            "BarberShopStyle": barber.pack(), "HelmetGeosetVisData": helmets.pack()}


NPC_LOOKS = [  # id, race, sex, skin, face, hair style, hair colour, facial hair
    (1, 10, 0, 4, 1, 0, 1, 0),  # a Blood Elf look on the old Death Knight skin 4: moves to 8 (face 1 is not there: 0)
    (2, 1, 1, 2, 1, 0, 1, 0),  # Human female hair colour 1: the package's 2
    (3, 2, 0, 0, 0, 0, 0, 0),  # unchanged
    (4, 12, 0, 3, 3, 3, 3, 3),  # a race customize does not touch
]


def npc_looks() -> bytes:
    cdie = synth.Packer("CreatureDisplayInfoExtra")

    for row_id, race, sex, skin, face, style, colour, facial in NPC_LOOKS:
        cdie.add(id=row_id, displayRaceID=race, displaySexID=sex, skinID=skin, faceID=face, hairStyleID=style,
                 hairColorID=colour, facialHairID=facial, bakeName=f"Npc{row_id}.blp")

    return cdie.pack()


def realm_races(stock: dict[str, bytes]) -> bytes:
    races = DbcTable.from_bytes(stock["ChrRaces"], schema_access.get("ChrRaces"))
    by_id = races.by_id()

    for slot, source, name in ((15, 10, "HighElf"), (19, 11, "Eredar")):
        row = list(by_id[source])
        races.set(row, "id", slot)
        races.set_str(row, "clientFileString", name)
        races.rows[races.rows.index(by_id[slot])] = row

    return races.to_bytes()


# --- files -----------------------------------------------------------------------------------------------------


_TEXTURES: dict[tuple, bytes] = {}


def texture(name: str, variant: int = 0) -> bytes:
    """A small palette texture for a name: its colour from the name's last number (skin tone or hair colour)."""
    lower = name.lower()
    digits = "".join(c for c in lower.rsplit("_", 1)[-1] if c.isdigit()) or "0"
    index = int(digits) % 100
    hairish = "hair" in lower
    tone = (HAIR if hairish else TONES)[index % (len(HAIR) if hairish else len(TONES))]

    if "skin00" in lower and "naked" not in lower:
        size = (16, 16)
    elif "upper" in lower or "torso" in lower:
        size = (16, 4)
    else:
        size = (16, 8)

    tone = tuple(min(255, c + 7 * variant) for c in tone)
    key = (tone, size)

    if key not in _TEXTURES:
        _TEXTURES[key] = synth_skins.blp_palette(*size, synth_skins.skin_texture(*size, tone), alpha_size=0)

    return _TEXTURES[key]


def m2(model: str, sequences: list[tuple[int, int, int]], textures: list[str]) -> bytes:
    """A made-up M2 v264: the header, its sequences (64 bytes each) and its textures (type 0 file names)."""
    header = bytearray(0x140)
    header[0:4] = b"MD20"
    struct.pack_into("<I", header, 4, 264)
    struct.pack_into("<I", header, 68, 1)  # one skin profile
    body = bytearray()
    seq_at = len(header)
    struct.pack_into("<II", header, 28, len(sequences), seq_at)

    for sid, variation, flags in sequences:
        body += struct.pack("<HHIfIhHIIIffffffIhH", sid, variation, 1000, 1.0, flags, 0, 0, 0, 0, 150,
                            0, 0, 0, 0, 0, 0, 0, -1, 0)

    tex_at = seq_at + len(body)
    names = bytearray()
    entries = bytearray()
    name_at = tex_at + 16 * len(textures)

    for name in textures:
        raw = name.encode() + b"\0"
        entries += struct.pack("<IIII", 0, 0, len(raw), name_at + len(names))
        names += raw

    struct.pack_into("<II", header, 80, len(textures), tex_at)
    return bytes(header + body + entries + names) + model.encode()


def skin(geosets: list[int]) -> bytes:
    data = bytearray(48)
    data[0:4] = b"SKIN"
    struct.pack_into("<II", data, 28, len(geosets), 48)

    for g in geosets:
        data += struct.pack("<H", g) + bytes(46)

    return bytes(data)


def model_files(race: int, sex: int, geosets: list[int] | None = None, anim: bytes = b"anim of the package",
                stock: bool = False) -> dict[str, str | bytes]:
    base = f"Character\\{rf(race)}\\{SEX[sex]}\\{rf(race)}{SEX[sex]}"
    eye = f"Character\\{rf(race)}\\{SEX[sex]}\\deathKnightEyeGlow.blp"
    data = {f"{base}.m2": m2(base + (" stock" if stock else ""), [(0, 0, 0x20), (4, 0, 0x0), (5, 0, 0x40)], [eye]),
            f"{base}00.skin": skin(GEOSETS if geosets is None else geosets),
            f"{base}0004-00.anim": anim}

    if not stock:
        data[eye] = synth_skins.blp_palette(8, 8, synth_skins.skin_texture(8, 8, (90, 200, 255)), alpha_size=8)

    return data


def package_rows_textures(package_tables: dict[str, bytes]) -> set[str]:
    table = DbcTable.from_bytes(package_tables["CharSections"], schema_access.get("CharSections"))
    return {table.get_str(r, f"textureName[{s}]") for r in table.rows for s in range(3)
            if table.get(r, "raceID") in ap.PACKAGE_RACES} - {""}


def make_package(root: str, models: dict | None = None, extra_rows=None) -> str:
    """root/package: DBFilesClient, Character art and models, a Goblin folder, LICENSE, .git/HEAD."""
    package = os.path.join(root, "package")
    data = tables(True)

    if extra_rows is not None:
        data = extra_rows(data)

    dbc = os.path.join(package, "DBFilesClient")
    os.makedirs(dbc, exist_ok=True)

    for name, blob in data.items():
        with open(os.path.join(dbc, f"{name}.dbc"), "wb") as f:
            f.write(blob)

    def put(name: str, blob: bytes):
        path = os.path.join(package, *name.split("\\"))
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "wb") as f:
            f.write(blob)

    for name in sorted(package_rows_textures(data)):
        if name == MISSING_SCALP or NO_SOURCE in name:
            continue

        # the package's own files of stock names are other (HD) bytes
        put(name, texture(name, variant=1))

    for race in ap.PACKAGE_RACES:
        for sex in (0, 1):
            files = (models or {}).get((race, sex)) or model_files(race, sex)

            for name, blob in files.items():
                put(name, blob)

    put("Character\\Goblin\\Male\\GoblinMale.m2", b"not shipped")
    put("Character\\Goblin\\Male\\Npc9.blp", b"not shipped")
    put("Textures\\BakedNPCTextures\\Baked1_HD.blp", b"not shipped")
    put("LICENSE", b"made-up licence")

    git = os.path.join(package, ".git")
    os.makedirs(git, exist_ok=True)

    with open(os.path.join(git, "HEAD"), "w", encoding="utf-8") as f:
        f.write(COMMIT + "\n")

    return package


def make_realm(root: str, hd_pack: bool = True) -> dict:
    """root/client (the launcher's base) and root/patches (the realm's patches). Returns the paths and tables."""
    stock = synth.build_tables()
    stock.update(tables(False))
    stock["CreatureDisplayInfoExtra"] = npc_looks()
    realm = tables(False, realm=True)
    realm["ChrRaces"] = realm_races(stock)
    data = os.path.join(root, "client", "Data")
    patches = os.path.join(root, "patches")
    os.makedirs(patches, exist_ok=True)
    stock_cs = DbcTable.from_bytes(stock["CharSections"], schema_access.get("CharSections"))
    common = {"Interface\\Glues\\Base.blp": b"made up"}

    for row in stock_cs.rows:
        for slot in range(3):
            name = stock_cs.get_str(row, f"textureName[{slot}]")

            if name:
                common[name] = texture(name)

    for race in ap.PACKAGE_RACES:
        for sex in (0, 1):
            common.update(model_files(race, sex, geosets=[0, 1, 2, 3, 101, 102, 1702], anim=b"stock anim", stock=True))

    synth_skins.write_mpq(os.path.join(data, "common.MPQ"), common)
    synth_skins.write_mpq(os.path.join(data, "enUS", "locale-enUS.MPQ"),
                          {f"DBFilesClient\\{n}.dbc": stock[n] for n in ("ChrRaces", "CreatureDisplayInfo",
                                                                          "CreatureModelData", "CharSections",
                                                                          "CharHairGeosets", "CharacterFacialHairStyles",
                                                                          "BarberShopStyle", "HelmetGeosetVisData",
                                                                          "CreatureDisplayInfoExtra")})
    realm_files = {f"DBFilesClient\\{n}.dbc": realm[n] for n in realm}
    realm_files["Interface\\Glues\\Custom.blp"] = b"the realm's own art"
    realm_files["Character\\BleakholdSkins\\HighElf\\0123456789\\Character\\BloodElf\\Male\\BloodElfMaleSkin00_00.blp"] = \
        texture("Skin00_00", 3)
    synth_skins.write_mpq(os.path.join(patches, "Patch-R.MPQ"), realm_files)

    if hd_pack:
        hd = model_files(10, 1, anim=b"the HD pack's anim", stock=True)
        synth_skins.write_mpq(os.path.join(patches, "patch-A.MPQ"), hd)

    return {"root": root, "client": os.path.join(root, "client"), "data": data, "patches": patches, "stock": stock,
            "realm": realm}


def write_curation(path: str, commit: str = COMMIT, **changes) -> str:
    """A curation for the made-up package: one broken skin hidden, the High Elf's skins 0-3 and 5-7, Draenei's skin 7
    fel (hidden on 11, kept on 19)."""
    data = {
        "version": 1,
        "package": {"name": "Made-up package", "commit": commit},
        "near_duplicate_delta_e": 2.0,
        "skin_groups": {"BloodElf": {"Female": {"marked": [6], "fel": [7]}}, "Draenei": {"Male": {"fel": [7]}}},
        "hidden": [{"race": "Human", "sex": "Female", "section": "skin", "colours": [6],
                    "reason": "painted clothing (made up)"}],
        "race_filters": {
            "HighElf": {"from": "BloodElf", "keep_skins": {"Male": [0, 1, 2, 3, 5, 6, 7], "Female": [0, 1, 2, 3, 5]},
                        "hide_groups": ["marked", "fel"], "reason": "the High Elf's plain tones (made up)"},
            "Draenei": {"hide_groups": ["fel"], "reason": "fel skins are the Eredar's (made up)"},
            "Eredar": {"from": "Draenei"},
        },
    }
    data.update(changes)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)

    return path


# --- MarkForge's output, made up -------------------------------------------------------------------------------


def mark_blp(seed: int = 1, glow: bool = False) -> bytes:
    """A 512x512 palette BLP with 8-bit alpha and every level: a band of ink (alpha 255) in each section's middle
    rows, nothing elsewhere. The _Glow copy has the same alpha and other colours."""
    levels = []
    size = 512

    while True:
        w = h = size
        indices = bytes([seed % 256]) * (w * h)
        alpha = bytearray(w * h)
        band = max(1, h // 64)

        for y in range(h // 2, min(h, h // 2 + band)):
            alpha[y * w:(y + 1) * w] = b"\xff" * w

        levels.append(indices + bytes(alpha))

        if size == 1:
            break

        size //= 2

    palette = b"".join(bytes((i if glow else 255 - i, (i * 3) % 256, (seed * 40) % 256, 0)) for i in range(256))
    return synth_skins.blp_file(1, 8, 2, 512, 512, levels, palette, mips=True)


def eye_blp(colour: tuple[int, int, int]) -> bytes:
    return synth_skins.blp_palette(32, 32, synth_skins.skin_texture(32, 32, colour), alpha_size=8)


def write_manifest(folder: str, catalogue, entries: dict[tuple[str, int], tuple[bool, list[int]]],
                   markforge_form: bool = False) -> str:
    """folder/marks_manifest.json and its files at files/<client path>. entries: (race file, sex) -> (with looks,
    eyes). The contract's format 1, or with markforge_form the form markforge.py build writes (bleakhold-marks/1)."""
    os.makedirs(folder, exist_ok=True)
    files_dir = os.path.join(folder, "files")
    mark, glow = mark_blp(3), mark_blp(3, glow=True)
    races = []

    def put(name: str, data: bytes) -> tuple[str, str]:
        rel = "files/" + name.replace("\\", "/")
        path = os.path.join(folder, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "wb") as f:
            f.write(data)

        import hashlib
        return rel, hashlib.sha1(data).hexdigest()

    for (race, sex), (with_looks, eyes) in sorted(entries.items()):
        cat = catalogue.races[race]
        looks = []

        if with_looks:
            for d, design in enumerate(cat.designs, 1):
                for c, colour in enumerate(cat.colours, 1):
                    texture = ap.mark_name(race, sex, design.key, colour.key)
                    rel, digest = put(texture, mark)
                    item = {"look": ap.look_of(d, c), "design": design.key, "colour": colour.key, "texture": texture,
                            "file": rel, "sha1": digest, "glow": None, "glow_file": None, "glow_sha1": None}

                    if colour.glow:
                        name = ap.glow_name(texture)
                        grel, gdigest = put(name, glow)
                        item.update(glow=name, glow_file=grel, glow_sha1=gdigest)

                    looks.append(item)

        eye_items = []

        for eye in eyes:
            key = cat.eye(eye, catalogue.dk_eyes).key
            texture = ap.eye_name(race, sex, key)
            rel, digest = put(texture, eye_blp((200, 40 * eye, 255 - 30 * eye)))
            eye_items.append({"eye": eye, "colour": key, "texture": texture, "file": rel, "sha1": digest})

        races.append({"race": race, "sex": SEX[sex], "looks": looks, "eyes": eye_items})

    data = {"format": 1, "tool": "markforge", "catalogue_sha1": catalogue.sha1, "races": races}

    if markforge_form:
        data = markforge_manifest(catalogue, races)

    path = os.path.join(folder, "marks_manifest.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)

    return path


def markforge_manifest(catalogue, races: list[dict]) -> dict:
    """The contract-form races as markforge.py build's manifest (Tools/MarkForge/markforge.py, make_looks and
    make_eyes): race ids and sex numbers, design and colour numbers with their keys and names, glow_texture."""
    ids = {name: race for race, name in ap.RACE_FILES.items()}
    out = []

    for item in races:
        cat = catalogue.races[item["race"]]
        marks = []

        for look in item["looks"]:
            d = [e.key for e in cat.designs].index(look["design"])
            c = [e.key for e in cat.colours].index(look["colour"])
            design, colour = cat.designs[d], cat.colours[c]
            marks.append({"look": look["look"], "design": d + 1, "design_key": design.key, "design_name": design.name,
                          "colour": c + 1, "colour_key": colour.key, "colour_name": colour.name, "hex": colour.hex,
                          "glow": colour.glow, "texture": look["texture"], "sha1": look["sha1"], "size": 0,
                          "glow_texture": look["glow"], "glow_sha1": look["glow_sha1"],
                          "barber_name": f"{design.name}, {colour.name}"})

        eyes = []

        for eye in item["eyes"]:
            entry = cat.eye(eye["eye"], catalogue.dk_eyes)
            eyes.append({"eye": eye["eye"], "key": entry.key, "name": entry.name, "hex": entry.hex,
                         "dk_only": eye["eye"] in ap.DK_EYES, "texture": eye["texture"], "sha1": eye["sha1"],
                         "size": 0})

        sex = SEX.index(item["sex"])
        out.append({"race": ids[item["race"]], "race_file": item["race"], "sex": sex, "sex_name": item["sex"],
                    "model": "", "eye_geoset": bool(eyes), "eye_source": None, "garment_missing": 0, "marks": marks,
                    "eyes": eyes})

    return {"format": "bleakhold-marks/1", "markforge_version": 1, "catalogue_version": catalogue.version,
            "source": "game", "races_requested": "all", "looks_per_design": 3, "designs_per_race": 4,
            "gates": {"passed": True, "seam_max": 0.0, "seam_limit": 0.1, "keepout_ink": 0, "garment_ink": 0},
            "race_sexes": out}
