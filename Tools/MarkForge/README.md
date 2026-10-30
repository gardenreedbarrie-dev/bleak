# MarkForge

MarkForge draws the Bleakhold glowing body marks and the eye-colour sprites. It works from each race's own character
model and texture layout, so the marks follow the body: they line up across UV seams, stay out of the eyes and
mouth, and do not show through underwear. The appearance data contract in `Tools/RaceForge/README.md` ("Bleakhold
appearance data contract") says what the files are and how the realm's tables name them. This tool writes them.

The output comes from game files (models, skins, underwear, the eye glow sprite), so it is made **on the realm's
server at install time** and is never committed. Only the tool, its designs and colours, and its tests are in the
repository. `build` refuses to write inside a git checkout.

Needs Python 3.10 or later and **numpy** (Ubuntu: `apt install python3-numpy`). `markforge.py doctor` checks it.
The output is byte-identical on Python 3.12 with numpy 1.26 (Ubuntu 24.04) and on Python 3.13 with numpy 2.5 (a dev
build of 7 race-sexes made with one passes `--check` with the other). `--check` on the VPS compares the VPS's own
build, so that is what the gate needs; the charts avoid every choice that the last bit of a sum or a sort could flip
(stable sorts, no `einsum`, cell borders off the data), so the shapes do not depend on the numpy version. The
tool also uses `Tools/BlpConvert`, `Tools/RaceForge` (archives, DBCs, the catalogue) and `Tools/ModelForge`'s M2 reader.

## On the VPS

```sh
python3 -I Tools/MarkForge/markforge.py doctor
python3 -I Tools/MarkForge/markforge.py build --client /srv/bleakhold-launcher/base \
    --patches /srv/bleakhold-launcher/patches --out /root/markforge-staging
python3 -I Tools/MarkForge/markforge.py build --client /srv/bleakhold-launcher/base \
    --patches /srv/bleakhold-launcher/patches --out /root/markforge-staging --check
python3 -I Tools/MarkForge/markforge.py validate /root/markforge-staging
```

`raceforge.py customize --marks /root/markforge-staging/marks_manifest.json` then adds the rows and packs
`patch-K.MPQ` (see the RaceForge README). The game's files are read like `raceforge.py skins` reads them: `--client`
is the base folder, `--patches` lies over it, and `--config` (default: RaceForge's `races.json`, whose optional packs
are the launcher's) and `--locale` work the same. Every combination of the
launcher's optional packs must give the same model, skin and eye sprite (byte for byte), and the same values of the
tables MarkForge reads (CharSections' rows of the twelve playable races with their flags and texture names; ChrRaces,
CreatureDisplayInfo and CreatureModelData as far as they name those races' models; RaceForge writes one copy of a
table per archive, each with its own string block, so the bytes may differ), or the build stops. On the client's
archives a race's model always comes from those tables (High Elf and Eredar may have models of their own): when they
cannot be read, the build stops instead of taking the stock model.
`--combination LABEL` reads only one of them. A full build (12 races, 2 sexes, 12 looks and 5 eye sprites each)
takes about 4 minutes (about 10 s per race and sex) and about 340 MB of staging, about 18 MB once packed (estimated from
7 race-sexes).

| Command | What it does |
|---|---|
| `build ... --out STAGING [--races NightElf:Female,Orc,...] [--no-eyes] [--preview]` | Writes the marks, eye sprites, `marks_manifest.json` and `report.json`. Exits 1 if a gate fails. `--preview` also renders previews into `STAGING/previews` (game art: keep them off the repository) |
| `build ... --out STAGING --check` | Makes everything again in memory and compares it byte for byte with STAGING, stale files included |
| `preview ... --out DIR --look Race:Sex:Design:Colour [--skin N] [--eye Colour]` | One look: texture sheet, front, back and side views by day and by night, and a close-up of the head |
| `fixture --out DIR [--races Race:Sex,...] [--check]` | Synthetic files for the client team. No game data, see below |
| `validate STAGING` | Checks every file listed in a staging manifest against the contract's file rules and its SHA-1 |
| `doctor` | Checks numpy, the M2 reader, BlpConvert, RaceForge, and that the designs and colours match the catalogue |

Staging layout:

```
STAGING/files/Character/BleakholdMarks/<RaceFile>/<Sex>/<Design>_<Colour>.blp   (+ _Glow.blp, colours 1 and 2)
STAGING/files/Character/BleakholdEyes/<RaceFile>/<Sex>/Eye_<Colour>.blp         (eyes 1-5)
STAGING/marks_manifest.json   what customize --marks reads
STAGING/report.json           per race and sex: landmarks, keep-out, garment, seams; per design its seam numbers
```

## Manifest (`"format": "bleakhold-marks/1"`)

RaceForge reads this form (`rflib/marksrows.py`, `from_markforge`) and checks every key, name, hex value and glow
flag against the catalogue. It takes only a manifest with `gates.passed` true, `source` `game`, `garment_missing` 0
for every race-sex, and every race-sex of the catalogue with all 12 looks and eyes 1-5 (a `--races` subset or a
`--no-eyes` build is for previews and tests; `customize --marks-partial` takes it on a dev run). These fields are
part of the contract, so change them only together with RaceForge:

- top level: `format`, `markforge_version`, `catalogue_version` (must be `catalogue.json`'s `version`), `source`
  (`game`: `--client`/`--patches`; `folder`: `--package`), `races_requested` (the `--races` given, or `all`),
  `looks_per_design` (3), `designs_per_race` (4), `gates` {`passed`, `seam_max`, `seam_limit`, `keepout_ink`,
  `garment_ink`}, and `fixture: true` only in a fixture (RaceForge refuses it);
- `race_sexes[]`: `race` (id: High Elf 15, Eredar 19), `race_file`, `sex` (0/1), `sex_name`, `garment_missing` (the
  visible skin colours whose skin or underwear was not read: 0, or the build failed its gate), `model`,
  `model_sha1`, `skin_sha1`, `eye_geoset` (the model has geoset 1703), `eye_source` (the sprite it was recoloured
  from);
- `marks[]`: `look` (= 3 × (design − 1) + colour), `design`, `colour` (numbers), `design_key`, `design_name`,
  `colour_key`, `colour_name`, `hex`, `glow`, `texture`, `sha1`, `size`, `glow_texture` / `glow_sha1` (`null` for
  colour 3, the paint), `barber_name`, `sections` (which atlas sections have ink), `coverage_pct`;
- `eyes[]`: `eye` (1-5), `key`, `name`, `hex`, `dk_only` (4 Blood Red, 5 Unholy Green), `texture`, `sha1`, `size`.

## What a look is made of

- **Files.** A mark is a 512 × 512 palette BLP (`blpconvert.py --format pal8`: colorEncoding 1, alphaSize 8, all
  10 levels), the only encoding the character compositor pastes. A `_Glow` file has the mark's header, alpha bytes
  and palette indices, and its own palette holding the light it gives off. Colour 3 is plain paint with no `_Glow`.
  Texels outside the ten sections are alpha 0. An eye sprite has the width, height and encoding of the model's own
  `deathKnightEyeGlow.blp`, recoloured from it (its alpha is kept). Nothing of the original sprite is committed.
- **Charts from 3D, not from UV rows.** The model's skin triangles are drawn into the 512 atlas with their 3D
  positions and normals (`mflib/atlas.py`). Texels just outside triangles get extrapolated positions, so bilinear
  sampling at a seam reads the same design value on both sides. On arms and legs, the chart (`mflib/coords.py`)
  measures V as arc length along the limb's smoothed axis and U as the angle around that axis times the ring's
  length, both taken from 3D. A design is then continuous across the inner wrap seam, whichever way the UVs are cut.
  The torso is measured from the front midline. The face uses eye separations from the eye centres (geoset 1703).
- **Gates** (any one fails the build):
  - the glow and ink difference across every wrap seam is at most 0.1;
  - no ink inside a keep-out zone at the 512, 256 and 128 levels. The zones are an ellipsoid around each eye (lids,
    eyeballs, Night Elf glow orbs) and the lips around the mouth's 3D centre;
  - no ink inside the garment mask at the 512, 256 and 128 levels. The mask is the union, over every skin colour a
    player can pick, of the texels where the underwear texture differs from the bare skin by more than the skin
    copy's own noise (median + 4 MAD of the texels that look like skin, at least 22), whatever share of the section
    the cloth covers; a stock underwear with transparent texels is cloth wherever it is opaque. Ink fades out over the
    last few texels before a blocked zone, and a dead zone stops coarse mips from bleeding into it;
  - every underwear's mask covers at least half of the texels that differ from its skin by more than 22 above the
    copy's offset (`report.json`: `cover_pct` and `reference_pct` per colour): a mask that lost the cloth fails the
    build instead of passing the check above against itself;
  - every visible skin colour's skin, pelvis and torso texture was read (`report.json`: `skipped`; the manifest's
    `garment_missing`), and every race-sex has a visible skin colour: an underwear that is not in the mask could be
    painted over. A `--client` build stops at the first one; a `--package` build (a dev folder that may lack art)
    reads on and fails the gate, so it passes only with all the art there;
  - every file passes the contract's file rules, checked on the bytes before anything is written (a failure leaves
    `gates.passed` false in the manifest, which `customize --marks` refuses) and again on the written copy.
  - the glow difference across every cut seam the build fades is at most 0.1 too. Cut seams and open borders of the
    arms and the body (the neck, the wrists), and the cuts where the head meets another island (the chin, the neck,
    the temples where a body-island piece of the head starts), fade the design out in 3D on both sides (the head's
    side also over the few gutter texels next to the cut, measured in the atlas). The head's own cuts are left
    unfaded and only reported (`seam_head_cut_glow` in report.json); hand and finger seams are not gated.
- **Lines** have a minimum width of 2.5 texels at the texel's own scale. They are anti-aliased over one local texel,
  so they survive the client's 256 bake and stretched UVs.

## Designs and colours

`designs/<RaceFile>.json` holds 4 designs per race. Each one has its key and name from the catalogue, a lore line,
and a list of elements in the order they are drawn. `mflib/designs.py` describes the design language (charts `arm`,
`torso`, `leg` and `face`, and kinds such as `line`, `band`, `helix`, `vine`, `dip`, `constellation` and `claws`).
Every motif is our own. Runes, cracks and constellations come from fixed seeds, so a build is reproducible. A design
takes every count (a crack's steps, a band's repeats) from its own numbers, never from a model's metres: those can
differ in their last bit between numpy versions or CPUs, and that must not change a design's shape (it once added a
step to Dwarf female Ember Cracks).
`palettes.json` repeats the catalogue's colours (keys, names, hex, glow, in catalogue order) and adds MarkForge's
paint `opacity` and the eye sprites' `eye_core`. `build` refuses to run, and `doctor` fails, when it differs from
`Tools/RaceForge/customize/catalogue.json`.

High Elf uses the Blood Elf model and Eredar the Draenei model, unless the realm's tables give them their own.
Their garment masks are taken from their own skin rows.

## Fixture for the client team

`markforge.py fixture --out DIR` writes, with no game data:

- `Character\BleakholdMarks\Fixture\SectionGrid.blp` (+ `_Glow`): each of the ten sections framed, crossed and
  labelled in its own colour, to see that every section is pasted to its place at levels 7, 8 and 9;
- the real designs of `--races` (default `NightElf:Female`) drawn on MarkForge's synthetic tube body, under their
  real paths. They land in the right sections, but not on the right body parts of a real model;
- eye sprites recoloured from a synthetic 32 × 32 glow;
- `Character\BleakholdMarks\Fixture\Bad\*.blp`: broken files (DXT5, 384², 512 × 256, no mips, a missing 1 × 1
  level, alphaSize 2, truncated, and a `_Glow` whose alpha or size differs). The manifest's `bad_files` says why each
  one is bad and what the exe does with it (`expect`): the first seven are skipped and logged once, never hung on or
  painted green; the mark with a `_Glow` of other alpha bytes is pasted with its `_Glow` (the exe compares only size
  and alphaSize; `markforge.py validate` catches it), and the one with a 256² `_Glow` is pasted without it.
  `tests/test_marks_core.cpp` holds each `expect` against `BleakMarks.h` at both character texture sizes, from the
  files' facts in `tests/fixture_bad_facts.inc` (`tests/make_fixture_facts.py` writes it; a test checks it is
  current).

## Tests

`python3 -I Tools/MarkForge/tests/run_tests.py` (CI, the `checks` job). The tests use a synthetic tube-body humanoid
in the HD layout (`mflib/model.py`, `tube_body`), a minimal M2 writer (`tests/m2tiny.py`) and a synthetic package
(CharSections.dbc, two skin colours with different underwear, faces, an eye sprite), also packed into MPQs as a
client and a patches folder (with an HD pack that disagrees) to build through the archive overlay as the VPS does.
They cover pal8 packing and decoding, sources and CharSections reading, the atlas, seams, charts and keep-out zones,
every design kind (and a crack under a unit that differs in its last bit), the gates (a file breaking the file rules
fails the build), eyes, the garment union, and the CLI (`build`, `--check`, `validate`, `fixture`, the refusal to
write into a checkout). `tests/run_marks_core.sh` and `tests/test_marks_core.cpp` are the exe's mark-layer core
tests, which belong to the client code.
