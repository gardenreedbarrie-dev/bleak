# ModelForge

Original procedural M2 props for the Bleakhold café (CAFE.SPEC.md section 5, workstream WS-G). Every model is
procedural geometry with procedurally painted textures: no Blizzard or third-party assets are read or written.
The lion head and tusk crest are original shapes defined in `mflib/emblem.py`, and both fonts are original and
defined in `mflib/font.py`.

Standard library only (Python 3.10+). Run it with `python3 -I`. The output is deterministic: the same sources give
byte-identical files, and the tests hold golden sha256 hashes for the cube and EspressoSW.

```
python3 -I Tools/ModelForge/modelforge.py build --all --out /tmp/mf [--preview] [--previews DIR] [--no-particles]
                                                [--no-bake] [--tex-scale F] [--only Cube,EspressoSW] [--jobs N]
python3 -I Tools/ModelForge/modelforge.py check FILE.m2 [--parts DIR/parts/NAME.parts.json] [--client PATH]
python3 -I Tools/ModelForge/modelforge.py render FILE.m2 --root DIR/files --out x.png [--mode orbit|overlay|game]
python3 -I Tools/ModelForge/modelforge.py manifest --out DIR
python3 -I Tools/ModelForge/modelforge.py preview --scene sw|org --out DIR
python3 -I Tools/ModelForge/modelforge.py testpatch --only Cube,EspressoSW --out DIR
python3 -I Tools/ModelForge/tests/run_tests.py [--update-golden] [-v]
```

Output tree:

- `DIR/files/World/Bleakhold/Cafe/<Name>/BH_Cafe_<Name>.m2`, plus `BH_Cafe_<Name>00.skin` and
  `BH_Cafe_<Name>_Atlas.blp`;
- `DIR/files/World/Bleakhold/Cafe/Shared/BH_Cafe_{ChromeEnv,IronEnv,Steam,Fire}.blp`;
- `DIR/parts/<Name>.parts.json`: triangles per named part, read by `check --parts`. It is not shipped;
- `DIR/manifest.json`: the interface to CafeForge (section 5.9);
- `DIR/previews/*.png`, `index.html` and `<Name>-sheet.png` (the owner's contact sheet), with `--preview`.

## What M1 contains

| Module | Does |
|---|---|
| `mflib/m2write.py`, `skinwrite.py` | Write a static M2 v264 and one `.skin` with the exact values of section 5.2: 16-byte aligned arrays, data from 0x140, one-key tracks with loop 0xFFFF, an empty sequence hash, texture weight 0x7FFF, particles with head quads and twinkle 10/1/1. |
| `mflib/m2check.py` | Parse and validate independently of the writer. It mirrors the client's `M2Init`, skin init and particle setup, and covers every error in section 5.3. It also cross-checks with MapForge's `m2_dependencies` and `m2_bounds`. |
| `tests/native/m2init_harness.cpp` | Run the client's own `M2Init` templates, copied from `Engine/Source/Model2/M2Shared.cpp`, on every built model, compiled against `Engine/Source/Model2/M2Data.h`. The tests compile it whenever g++ exists. |
| `mflib/geom.py` | Mesh primitives (box with rounded bevels, cylinder, cone, lathe, torus, sphere, capsule, extrude, sweep, spokes), deformers and UV helpers. Every vertex lies on a chart measured in yards. |
| `mflib/atlas.py` | Pack the charts at one texel density, snapped to DXT blocks, with gutters of 8/4/2 px. |
| `mflib/tex.py`, `paint2d.py`, `font.py`, `emblem.py`, `raster2d.py` | Painted generators with baked light, decals (dial, maker's plate, grille), the vector capitals and the 7x9 pixel font, and the emblems. They rasterize with `Tools/UiLint/make_art.py`, imported read-only. |
| `mflib/bake.py` | Texture-space bake: 32-ray AO against the model and the floor, the gradient, the key light, curvature edge wear and contact darkening. |
| `mflib/mips.py` | Island-aware gutter dilation, coverage-preserving mips for cutouts (only over the cutout islands' texels, so glass or opaque parts sharing the atlas keep their alpha), and `blpconvert.write_blp`. |
| `mflib/render.py`, `preview.py` | Software rasterizer that follows the client's camera, cull, light and blend rules (particles too: an emitter without flag 0x1 is lit with the world-up normal, as the client's lit particle shader does), plus the five preview modes and the contact sheet. |
| `mflib/props/cube.py` | The lettered test cube for V30 (winding and UV origin), with a lit steam emitter and an unlit ember emitter (V33). |
| `mflib/props/espresso_sw.py` | 19300 EspressoSW, the Royal Brass Engine, as an M1 draft. |

The other 22 models of section 5.8 (`props/__init__.py` `CATALOGUE`) and the icons (section 5.7) are M5 work.
M5 starts after the owner's in-game look at the M2 art smoke test (section 7.4, M2).

## Validation against the client

`m2check` is written from `M2Data.h` and the decompiled loader:

- `M2Init` (`M2Shared.cpp:1541-1555`): `MD20`, version exactly 0x108, header size, and every array with the
  client's bounds test (`M2Shared.cpp:141`). A track with loop 0xFFFF is relocated with no bounds check, and
  `M2Init` indexes `m_sequences[i]` with no bound check (`M2Shared.cpp:174-232`), so m2check checks both itself.
- Skin profiles: `GetSkinProfileIndex` and `s_skinProfileBoneCounts` (`M2Shared.cpp:31, 1652-1660`). Section
  bone counts: `InitializeSkinProfile` divides by them (`M2Shared.cpp:1141-1145`). Index ranges: `SetIndices`
  (`M2Shared.cpp:340-388`). The high bits of the section id: `M2SkinSectionIndexStart` (`M2Modern.cpp:1032`).
- Particles: the emitter type (`M2Model.cpp:7298-7310`), `SetParticleStyle` (`M2Model.cpp:7410`,
  `ParticleSystem2.cpp:301-332`; with neither quad flag the draw divides by zero), `SetTextureDimensions`
  (`ParticleSystem2.cpp:281-285`), the texture index (`M2Model.cpp:7470`) and twinkle (`ParticleSystem2.cpp:875-909`).
  The colour, alpha and scale part tracks are sampled for every live particle (`ParticleSystem2.cpp:683-684`):
  an empty one sends `PartTrackSearch` to `times[0x7FFFFFFF]` (`ParticleSystem2.cpp:85-112`), and fewer values
  than times reads past the values (`PartTrackKeys`, `115-188`). Head and tail cell tracks are checked the same
  way when they have times (`689-697`). The writer refuses an empty or mismatched part track.
- Skin sections: `m_centerBoneIndex` must name a bone, because transparent or fading batches are depth sorted
  through `m_boneMatrices[m_centerBoneIndex]` with no bound check (`M2Scene.cpp:1890, 1894`; one matrix per
  bone, `M2Model.cpp:7084`).
- `FindSequenceIndex` (`M2Model.cpp:1154`): a hash table without a reachable 0xFFFF loops forever.
- Blend modes: `s_blendModes` (`M2Scene.cpp:30`). Material flags and alpha key: `CM2SceneRender.cpp:204, 296-311`.

## Conventions

1 unit = 1 yard. +X is the model's front, +Y its left, +Z up. The origin is the centre of the footprint at the
base. Faces are counter-clockwise from outside, and UV (0, 0) is the texture's top-left. Both are `[VERIFY V30]`
with the lettered cube in game.

## Tests

`tests/run_tests.py` builds the cube and EspressoSW in full and runs the following:

- writer-to-checker round trips;
- every section 5.3 invariant violated on purpose (the particle `flags 0` case first);
- the native harness, both on built models and on violations;
- geometry winding and charts, and packing gutters;
- cutout coverage at mip 3 (within 15 % of mip 0), glass alpha kept when it shares an atlas with a cutout,
  and island separation at mip 2;
- text fit, glyph coverage and the emblems;
- the rasterizer's pixel checks (lighting, culling, glass blend, orientation);
- triangle budgets, sizes (cafe.json `size` when present, else section 5.8, within 2 cm), the readability rule,
  the collision ratio and sloped top, plume bounds and golden hashes.

After an intended art change, `--update-golden` rewrites `tests/golden.json`.
