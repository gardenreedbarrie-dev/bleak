# ModelForge

Original procedural M2 props for the Bleakhold café (CAFE.SPEC.md section 5, workstream WS-G). Every model is
procedural geometry with procedurally painted textures: no Blizzard or third-party assets are read or written.
The lion head and tusk crest are original shapes defined in `mflib/emblem.py`, and both fonts are original and
defined in `mflib/font.py`.

Standard library only (Python 3.10+). Run it with `python3 -I`. The output is deterministic: the same sources give
byte-identical files, and the tests hold golden sha256 hashes for every model (the cube and EspressoSW at full
texture size, the others at the tests' `--tex-scale 0.125`).

```
python3 -I Tools/ModelForge/modelforge.py build --all --out /tmp/mf [--preview [--quick]] [--previews DIR]
                                                [--no-particles] [--no-bake] [--tex-scale F] [--only A,B] [--jobs N]
python3 -I Tools/ModelForge/modelforge.py check FILE.m2 [--parts DIR/parts/NAME.parts.json] [--client PATH]
python3 -I Tools/ModelForge/modelforge.py render FILE.m2 --root DIR/files --out x.png [--mode orbit|overlay|game]
python3 -I Tools/ModelForge/modelforge.py icons --out DIR [--models DIR] [--only A,B] [--previews DIR] [--jobs N]
python3 -I Tools/ModelForge/modelforge.py manifest --out DIR
python3 -I Tools/ModelForge/modelforge.py preview --scene sw|org --out DIR [--only A,B] [--quick] [--scene-only]
                                                  [--previews DIR]
python3 -I Tools/ModelForge/modelforge.py testpatch --out DIR [--only A,B] [--from BUILD_DIR] [--icons] [--jobs N]
python3 -I Tools/ModelForge/modelforge.py models
python3 -I Tools/ModelForge/tests/run_tests.py [--models A,B] [--jobs N] [--update-golden] [-v] [pattern ...]
```

Models are discovered: every `mflib/props/<snake_name>.py` that defines `NAME` and `build(opts)` is registered
(`mflib/props/__init__.py`), so a new model is one new file. The module is named after the model in snake case
(`GrinderOrg` -> `grinder_org.py`); a module that does not import is reported (`models`, `build`, the tests) without
hiding the others. `--quick` previews only the hero shot, two orbits, the 8 yd game view and the silhouette. Floor
pieces (counters, stations, parasols, chalkboards) are previewed on the floor, the rest on a back bar
(`sizes.KINDS`); an Orgrimmar piece's hero and game views are lit with `org_day`, the others with `sw_day`, and
every Orgrimmar piece also gets an `org_night` lighting view (its night check), and the hero camera backs off until
the whole model (a crest, a finial, a lid spike) is in frame. A full build of all 25 models takes about 4 minutes
with `--jobs 2`.

The commands:

- `build` writes the files, `DIR/manifest.json` and, with `--preview`, every model's previews, its contact sheet
  and the scene of section 5.6 (an `icons` run before it keeps its entries in the manifest).
- `icons` renders the 14 spell icons of section 5.7 (below) from the models built in `DIR` (or `--models DIR`;
  a missing model is built there first, at full size), writes them to `DIR/files/Interface/Icons/` and adds
  them to `DIR/manifest.json` (`"icons": [{"id": 19300, "path": "Interface\\Icons\\BH_Cafe_Grinder.blp"}]`).
  PNG previews of the shipped DXT1 level and `icons-sheet.png` go to `DIR/icons` (or `--previews`).
- `preview --scene sw|org` renders the previews of every model built in `DIR` and the café scene of that city;
  `--scene-only` renders only the scene: `scene_<city>.png` (the whole default layout, fitted from above the
  tables) and `scene_<city>_bar.png` (the bar, the kettle stove and the cold box close up), in the city's day
  light.
- `testpatch` writes `DIR/patch-4.MPQ` for the owner's in-game look (section 5.9): any set of models (`--only`;
  default every registered model, the lettered cube included), built at full size into `DIR/stage`, or packed
  from an existing build with `--from BUILD_DIR` (each model is checked again with m2check; nothing is
  rebuilt); `--icons` adds the icons. Models, textures and the `Bleakhold\Cafe\cafeforge.txt` marker that says
  `test`, no DBC rows. Copy it by hand into one Windows client's `Data\` folder (never the VPS patches folder)
  and remove it before the M6 install.

Output tree:

- `DIR/files/World/Bleakhold/Cafe/<Name>/BH_Cafe_<Name>.m2`, plus `BH_Cafe_<Name>00.skin`,
  `BH_Cafe_<Name>_Atlas.blp` and the model's own textures (`_Panels`, `_Top`, `_Under`, `_Face`, `_Back`);
- `DIR/files/World/Bleakhold/Cafe/Shared/BH_Cafe_{ChromeEnv,IronEnv,Steam,Fire}.blp`;
- `DIR/files/Interface/Icons/BH_Cafe_<Icon>.blp` (`icons`);
- `DIR/parts/<Name>.parts.json`: triangles per named part, read by `check --parts`. It is not shipped;
- `DIR/manifest.json`: the interface to CafeForge (section 5.9);
- `DIR/previews/*.png`, `index.html` and `<Name>-sheet.png` (the owner's contact sheet), with `--preview`;
- `DIR/icons/*.png` and `icons-sheet.png` (`icons`).

## The models

All 24 models of section 5.8 (`props/__init__.py` `CATALOGUE`) and the lettered test cube are built. Front (+X)
faces the barista, or the customers for the counters, chalkboards and tip jar. Sizes are W (Y) x D (X) x H in
yards as built (section 5.8 within 2 cm unless noted); every model passes m2check and the client's `M2Init`.

| Display | Model (module) | What it is | Tris / budget | Size | Textures, emitters |
|---|---|---|---|---|---|
| | Cube (`cube.py`) | The lettered 1 yd test cube for V30 (winding, UV origin) with a lit steam and an unlit ember emitter (V33). | 12 / 200 | 1 x 1 x 1 | atlas, Steam; 2 emitters |
| 19300 | EspressoSW, Royal Brass Engine (`espresso_sw.py`) | Two-group lever machine: cocked pull levers, walnut portafilters toward the barista, cups under the spouts, a slim brass boiler column with copper hoops and a gold lion finial, royal-blue enamel body, heraldic maker's plate, chrome wand and tap. | 3992 / 4000 | 1.30 x 0.89 x 0.91 | atlas 512, ChromeEnv, Steam; wand steam, boiler vent wisp |
| 19301 | EspressoOrg, Tusk-o-Matic 3000 (`espresso_org.py`) | Two-group lever machine on a low riveted iron boiler drum with red bands and ridge spikes: dark iron levers with red lacquer grips and bone spike caps, waisted copper group bells, hide-wrapped handles, cups on saucers, three goblin gauges with bright faces, crescent ivory tusks, the bone tusk crest on a bright red apron, a slab worn bright at its edges, a spiked exhaust stack with warm grey smoke. | 4378 / 4500 | 1.40 x 0.95 x 0.94 | atlas 512, IronEnv, Steam; wand steam, exhaust smoke |
| 19302 | GrinderSW (`grinder_sw.py`) | Hand-crank burr grinder: a glass hopper bulb of beans on a royal-blue box in a riveted brass frame, a 0.38 brass crank wheel with a crank arm out past its rim and a walnut grip at its end, a walnut grounds drawer, a gold lion medallion and a turned gold knob on the lid. | 1186 / 1200 | 0.51 x 0.52 x 0.87 | atlas 256 + glass section |
| 19303 | GrinderOrg (`grinder_org.py`) | A tall flared iron funnel (spiked rim 0.4 across, beans 0.05 over it) over a red-and-iron box: an L-shaped side crank (an iron arm 0.25 long, a bone knob) in front of a red saw-star gear guard, a chute pouring grounds into a timber catch tub, tusks, tusk crests, a goblin gauge, a plank base. | 1112 / 1200 | 0.55 x 0.55 x 0.90 | atlas 256 |
| 19304 | BlenderSW, Gnomish Whirligig (`blender_sw.py`) | Glass jar of pink shake with a froth crown on a copper-framed blue motor base with two knobs on cream dials, a walnut grip on brass straps, lion medallions and a toy propeller on the lid. | 784 / 800 | 0.36 x 0.36 x 0.72 | atlas 256 + glass |
| 19305 | BlenderOrg, Shake-Shredder (`blender_org.py`) | Clear glass jar of shake with a saw blade standing on its floor, half-buried, its teeth through the froth, on a spiked iron base, an ivory tusk handle in riveted clamps, a sooty brass exhaust trumpet, red buttons, a gauge and a plank board. | 882 / 900 | 0.41 x 0.41 x 0.75 | atlas 256 + glass |
| 19306 | KettleStoveSW, Bluefire Kettle (`kettle_stove_sw.py`) | A royal-blue enamel kettle steaming on a black iron stove with blue panels in brass frames, a barred arched fire door glowing inside, a stovepipe with brass collars and a rain cap, a brass rail, tea towel, thermometer and teacup. | 1577 / 1600 | 0.81 x 0.61 x 1.70 (pipe to 1.7) | atlas 256 (glow window), Steam; spout steam, fire glow |
| 19307 | KettleStoveOrg, Spirit-Fire Kettle (`kettle_stove_org.py`) | A spiked iron kettle with a bail handle and bone grip on a clawed iron tripod over a grey-brown stone hearth with an arched fire mouth, flames licking past its belly (cards faded at their edges), a red lacquer lintel with the bone crest over the mouth, two big tusks, a gauge; steam from the spout tip. | 1502 / 1600 | 0.85 x 0.66 x 1.00 | atlas 256 (glow mouth and flame cards), Steam; spout steam, embers |
| 19308 | ColdBoxSW (`cold_box_sw.py`) | Oak ice-cream cabinet (crisp planks) under a sloped glass top with a bold frost rim, in a polished brass frame (espresso_sw's brass, a value ramp and edge highlights): three scoops in porcelain tubs with blue bands, a waffle-cone crest with a cherry on the back rail, a SW plaque between gold lion medallions, icicles, frost mist sinking over the front lip. | 1182 / 1200 | 1.10 x 0.71 x 0.98 (crest; box 0.8) | atlas 256 + frosted glass, Steam; 2 frost mists |
| 19309 | ColdBoxOrg, Frost-Rune Cold Box (`cold_box_org.py`) | Crooked timber ice chest with a stone lining under a blue ice lid: three scoops (kodo cream, chocolate, cactus apple) in iron-hooped buckets, a big glowing frost-rune crystal (0.12 x 0.25) in an iron claw in the middle of the back rail, a cone crest at its end, a red war shield with the cone on the front, tusks and spiked posts, frost mist sinking over the front lip. | 1150 / 1200 | 1.11 x 0.75 x 0.96 (crest; box 0.85) | atlas 256 + glow rune + glass, Steam; 2 frost mists |
| 19310 | SyrupRackSW (`syrup_rack_sw.py`) | Two-tier walnut shelf on the back bar: eight labelled syrup bottles with brass pumps turned outward, on royal-blue enamel under a SYRUPS plate with lions, jars, cups and a saucer stack above. | 1594 / 1600 | 1.40 x 0.40 x 0.90 | atlas 256 + bottle glass |
| 19311 | SyrupRackOrg (`syrup_rack_org.py`) | Crooked timber rack: eight leaning syrups with goblin pumps and rawhide tags before a laced hide, a red SYRUPS sign between ivory tusks over a palisade, a crock, keg, mugs and a cream canister with a gauge. | 1598 / 1600 | 1.45 x 0.45 x 0.90 | atlas 256 |
| 19312 | CounterSW (`counter_sw.py`) | Long walnut counter with a warm veined marble slab, five raised blue panels with gold cups, pilasters with gold capitals, a brass foot rail, a service bell, a lion medallion and a cake stand. | 992 / 1000 | 5.00 x 0.81 x 1.42 (cake stand; slab 1.05) | panels 256x1024 + marble top 256x512 (wrapping tiles), atlas 256 |
| 19313 | CounterOrg (`counter_org.py`) | Rough timber counter with a crooked plank top, laced red hide bays with fang paint, iron straps, ivory tusks, a crest shield, a bronze bell in a bone yoke, corner spikes and a hessian bean sack. | 966 / 1000 | 5.00 x 0.86 x 1.47 (tusks) | panels 256x1024 + top 256x512 (tiles), atlas 256 |
| 19314 | BackBarSW (`back_bar_sw.py`) | Walnut back bar with drawers over raised blue doors, fluted pilasters, open cup shelves with gilt lips in the end bays, a marble slab, a blue-and-white tile backsplash with three lion medallions, a cup pyramid and a towel. | 886 / 900 | 6.00 x 0.81 x 1.36 (backsplash) | CounterSW's panels and top tiles (the same files), atlas 256 |
| 19315 | BackBarOrg (`back_bar_org.py`) | Timber back bar with a pointed palisade backsplash of 18 stakes (red ones, a rope lashing), red drawers over plank doors with iron strap hinges, open mug shelves, a red crest shield and a copper tank with a gauge and a red valve. | 654 / 900 | 6.00 x 0.85 x 1.46 (palisade) | CounterOrg's panels and top tiles (the same files), atlas 256 |
| 19316 | ParasolSW, Lion's Roast Parasol (`parasol_sw.py`) | Blue and cream striped canopy with a scalloped valance and gold tassels, lion medallions, a brass pole with turned collars on a blue enamel base, a gold ball finial; the lion prints through the cloth underneath. | 676 / 700 | 2.80 x 2.80 x 3.20 (rim 2.52) | atlas 256 + underside 256 (cutout valance) |
| 19317 | ParasolOrg, Grinding Tusk Canopy (`parasol_org.py`) | Two-tone red hide cone canopy (six sagging panels) with a rim of hanging hide strips and bone beads, six curling tusks, a spike crown on a rope-bound gather, a light warm underside with laced seams, on a tripod of three timber poles (feet 1.4 apart) lashed where they cross. | 791 / 800 | 2.80 x 2.80 x 3.31 (rim 2.905) | atlas 256 + underside 256 (cutout hem) |
| 19318 | ChalkboardSW (`chalkboard_sw.py`) | Walnut A-frame sandwich board: "The Lion's Roast" in chalk, the chalk lion and family icons, a gold lion medallion on a blue arched header, chalk on the ledge; "Welcome!" on the back. | 278 / 300 | 0.90 x 0.50 x 1.40 | face 512x1024, back 512, atlas 256 |
| 19319 | ChalkboardOrg (`chalkboard_org.py`) | Tarred plank board between timber posts on skids: "The Grinding Tusk" in chalk with chalk teeth, two ivory tusks round a red crest plaque, riveted iron straps, spikes, rope and war paint. | 286 / 300 | 0.95 x 0.49 x 1.44 | face 512x1024, atlas 256 |
| 19320 | CupSW (`cup_sw.py`) | Porcelain cup with a royal-blue band, gold rim and lion boss on a blue-rimmed saucer, a crisp latte heart in a darker crema ring close under the rim, and a small steam plume. | 196 / 200 | 0.23 x 0.22 x 0.15 | atlas 128, Steam; cup steam |
| 19321 | MugOrg (`mug_org.py`) | Clay tankard (12 sides) with long red glaze runs over a light clay band, a dark rim line round the brew, a riveted iron foot, a closed ivory tusk handle lashed with leather, the tusk crest. | 190 / 200 | 0.22 x 0.22 x 0.23 | atlas 128 |
| 19322 | ShakeGlass (`shake_glass.py`) | Fluted sundae glass of pink shake with a cream swirl, a cherry and a striped bendy straw (both cafés). | 287 / 300 | 0.16 x 0.15 x 0.49 | atlas 128 + glass |
| 19323 | TipJar (`tip_jar.py`) | Open mason jar of clear blue-grey glass with a thick white-lit rolled rim, half full: a bed of gold and silver coins and six chunky loose coins (gold D4A82A, silver C8CCD4) tilted on it, one more leaning on the rim over the mouth, a "TIPS" label in a dark border (both cafés). | 294 / 300 | 0.24 x 0.24 x 0.28 | atlas 128 + glass, cutout coins |

Shared helpers private to a pair live beside them: `props/_cold_box.py` (both cold boxes). The chalkboards share
the chalk-menu layout through `chalkboard_sw.py`.

## Icons (section 5.7)

`modelforge.py icons` (`mflib/icons.py`) writes the 64 x 64 DXT1 icons of the SpellIcon rows 19300-19313
(19314-19319 are spare), `Interface\Icons\BH_Cafe_<Icon>.blp`, full-bleed as the stock icons are: the object on a
radial background gradient, the important content inside the central 85 %, a 2 px darkened edge and no frame.
One icon serves both cafés, so the stations show their Stormwind piece. Each is drawn at 256 px (2 x
supersampled) and box-filtered to 64:

| SpellIcon | Icon | Drawn from |
|---|---|---|
| 19300 | Grinder | GrinderSW, front three-quarter (teal background, rim light) |
| 19301 | Espresso | EspressoSW, cropped on one group: its lever, the portafilter and the cup under the spout (royal-blue background, rim light) |
| 19302 | Kettle | KettleStoveSW, framed on the steaming kettle on the cooktop (warm orange background) |
| 19303 | ColdBox | ColdBoxSW |
| 19304 | Blender | BlenderSW |
| 19305 | Shelf | SyrupRackSW, framed on the middle bottles and pumps (plum background) |
| 19306 | Counter | CounterSW, framed on the service bell on the marble |
| 19307 | Coffee | CupSW with its steam (Lion's Roast / Tusk-Grind Buzz; cream background) |
| 19308 | Tea | a flat-coloured teacup of amber tea (kit.cup) with a painted tea leaf and steam (Calm) |
| 19309 | Shake | ShakeGlass (Sugar Rush / Stampede Sprint) |
| 19310 | Shift | a painted barista's apron (the On Shift aura) |
| 19311 | Tired | CupSW in night light without steam, with a sleepy "Zz" |
| 19312 | Crown | a painted gold crown with jewels (Best Barista) |
| 19313 | Speed | a painted golden bolt with motion streaks (Café Sprint) |

The model icons use the preview rasterizer and the models' baked atlases under a warm key light from the upper
left; the painted ones use the emblem relief shading with a colour per layer (`icons.relief`).

## Scenes (section 5.6 mode 4)

`preview.DEFAULT_LAYOUT` is the section 3.12.3 default layout (used when `Tools/CafeForge/cafe.json` is absent):
counter, tip jar, blender, back bar, espresso machine, grinder, syrup rack, kettle stove, cold box, chalkboard,
the four tables with their stools, both parasols, both keg tables, the counter cup over the pickup spot and
drinks on two tables; the Orgrimmar scene swaps every SW piece for its Org twin (`CupSW` for `MugOrg`). Stock
tables, stools and keg tables are grey proxies; gnome, human and tauren capsules stand at the work spots, in the
queue and at the tables. Between them the two scenes show all 24 café models.

## The core

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
| `mflib/render.py`, `preview.py` | Software rasterizer that follows the client's camera, cull, light and blend rules (particles too: an emitter without flag 0x1 is lit with the world-up normal, as the client's lit particle shader does), plus the five preview modes, the scene and the contact sheet. |
| `mflib/icons.py` | The section 5.7 spell icons: model renders and painted reliefs, 64 x 64 DXT1 with full mips. |
| `mflib/props/*.py` | One module per model (the table above), discovered by `mflib/props/__init__.py`. |

## The shared library

What more than one section 5.8.1 design needs, so each model is one file under `mflib/props/`:

| Module | Adds |
|---|---|
| `mflib/tex.py` | Generators `bone` (ivory, age cracks, a darker root), `planks` (rough boards, gaps, ragged ends, knots, nails), `slabs` (stone slabs), `slate` (chalk dust), `bottle_glass` (a liquid below a fill level), `frosted_glass`, `glaze` (clay with glaze drips), `rope`, `lacquer` (red lacquer, worn edges), `fire_glow` and `embers` (glow textures), `frost_rune`, `beans`, `shake`, `cream`, `coffee` (crema, latte heart), `silver`, `hammered_iron`; `hide` gains stitching, burnt edges and scuffs. The dark iron palette `IRON` and the wood kind `orgdark` keep their darkest painted value about 0.16-0.2 with bright worn edges, so the Orgrimmar pieces hold their shape at night (`IRON_DEEP` is the old near-black iron, for EspressoSW's baskets); `coffee` takes `outline` (a crisp heart in a dark crema ring). Paint helpers `edge_dist`, `rivet_dot`, `frame_rivets`, `rivet_lines`, `stitches`, `inset_panel`, `ramp`; `image_lowres` and `tile_image` (seamless tiles). |
| `mflib/emblem.py` | `tusk_crest` redrawn (tusks with a lit ridge and leather wraps, a cup on a saucer); the flavour glyphs of section 5.5.1 (`GLYPHS`: drop, flower, leaf, bean, berry, cinnamon, mint, swirl, cactus, cream) and the shelf order `SYRUPS` / `SYRUPS_ORG`; line art `LINE_ICONS` (coffee, tea, shake, lion_head, tusk_crest) and `line_mask`. |
| `mflib/font.py` | The vector lower case (x-height 62, descenders), `squeeze` for condensed titles, descender room only for texts that need it (caps-only masks are unchanged), `chalk_mask` (chalk-style compositing of any mask). |
| `mflib/paint2d.py` | `chalkboard_face` (slate, chalk title, line-art emblem, family icons, caption, menu lines; raises when a text does not fit), `label` (two-tone bands, cut-out glyph details, outline), `wrap_front` (a decal on a wrapping lathe chart keeps its aspect), `engraved_lines`, `paint_mask`, relief palettes `IRON_RELIEF`, `BONE_RELIEF`, `CARVED_WOOD`. |
| `mflib/geom.py` | `spike`, `spike_ring`, `spike_row`, `horn` (tusks, claws, bone tips), `wheel` (valve and crank wheels), `planks` (crooked boards), `gear_polygon`, `flutes`, `disc` (a decal-ready flat disc), `mat_disc_facing` / `mat_extrude_facing` (upright decals on any face), `bezier2_path`, collision hulls `hull_box`, `hull_gable` (sloped top), `hull_cylinder`, `merge_hulls`; `plank_edges` takes `z` and `inward`. |
| `mflib/kit.py` | Part kits: `cup`, `mug`, `bottle` (eight shapes with label bands), `jar`, `kettle`, `bell`, `canopy` (two shells, per-panel charts), `fringe`, `exhaust` (goblin stack with a spiked collar), `gauge`. |
| `mflib/emitters.py` | The section 5.2.7 presets: `steam`, `vent_wisp`, `kettle_steam` (born small at the spout tip in a narrow cone, growing as it rises), `cup_steam`, `exhaust_smoke`, `frost_mist`, `embers`. The shared Steam sprite fades smoothly to nothing at its edge. |
| `mflib/build.py` | Non-square own textures (`atlas = {"face": (512, 1024)}`), per-texture flags (`tex_flags`), repeating tiles (`tiles`: the counters' 256² wrap; a tile with an `owner` is that model's file, so the back bars load the counters' tiles), `render_size` / `collision_size`; decals raise the texel alpha (labels on glass). |
| `mflib/sizes.py` | `KINDS` (collision budget, hull, height limit and preview stance per kind of piece) and `size_problems`. |

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

`tests/run_tests.py` builds every registered model (the cube and EspressoSW with textures at full size, the
others at `--tex-scale 0.125`; `--models A,B` or `MF_MODELS=A,B` limits the run to some models, `--jobs N` or
`MF_JOBS` sets the worker processes, default 2) and runs the following:

- writer-to-checker round trips;
- every section 5.3 invariant violated on purpose (the particle `flags 0` case first);
- the native harness, both on built models and on violations;
- geometry winding and charts, and packing gutters;
- cutout coverage at mip 3 (within 15 % of mip 0), glass alpha kept when it shares an atlas with a cutout,
  and island separation at mip 2;
- text fit, glyph coverage and the emblems;
- the rasterizer's pixel checks (lighting, culling, glass blend, orientation);
- the registry (every module loads, snake-case file names, catalogue rows), triangle budgets, sizes (cafe.json
  `size` when present, else section 5.8, within 2 cm), the kind's collision rules, the readability rule, the
  sloped top, plume bounds, every decal rendered at full size (texts that do not fit fail) and golden hashes;
- the icons (`test_icons.py`: the section 5.7 table, 64 x 64 DXT1 with 7 mip levels, the object inside the
  central 85 %, the darkened edge, determinism, the manifest's icon list), the scene layout (every café model
  placed in its city's scene) and `testpatch --from` on built models;
- the shared library (`test_shared.py`).

A model without golden entries passes; a changed or missing golden file fails. After an intended art change,
`--update-golden` rewrites `tests/golden.json` (keeping the entries of models not tested in that run).
