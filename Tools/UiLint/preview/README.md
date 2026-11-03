# UI previews

Renders Bleakhold windows to PNG files from the real addon code, so a look can be judged before it ships. The addon
runs in the UiLint mock (`../mock/wowmock.lua`). `driver.lua` lays the frames out the way the 3.3.5a client does
and dumps every visible region. `render.py` then draws that dump with the stock WoW art, if you have it locally.

| File | What it does |
|---|---|
| `render.sh` | The command: scene in, PNG out |
| `driver.lua` | Loads the addon in the mock (not for a standalone scene), runs the scene, lays out, dumps JSON |
| `render.py` | Measures text and texture sizes (pass 1), then draws (pass 2) |
| `sheet.py` | Contact sheets: several PNGs or screenshots, cropped and labelled, side by side |
| `scenes/windows.lua` | Each Bleakhold window once, as demo mode opens it |
| `scenes/pages.lua` | The windows in their states, as the owner's previews show them: every Activities page (queued, in a run, no keystone, no Journal art, ...), War Mode, Transmog, the emote wheel, Collections' tabs, the Leaderboards' boards, the open dropdowns and the dialogs (ride, leave, old addons) |
| `scenes/kit.lua` | The widget kit on one sheet (Widgets.lua), and its dialogs, toast and case |
| `scenes/reference.lua` | The old BleakholdActivities window (the owner's reference look) rebuilt from stock textures |
| `scenes/royale_countdown.lua` | The Royale drop countdown (DBM style): T-15 to DROP!, cancelled, docked, with DBM |
| `scenes/hud.lua` | The small HUD frames: toast, key tracker, keystone countdown, camp, War Front, minimap buttons |

## Requirements

- `Tools/UiLint/build/wowlua` and `Tools/UiLint/build/api.lua`. `Tools/UiLint/check.sh` builds both, as do
  `build_wowlua.sh` and `extract_api.py`.
- python3 with numpy and Pillow.
- Stock 3.3.5a art and the Journal pictures, both kept local (see below). Without the stock art, those textures are
  left out and listed on stderr. Without the Journal pictures, the driver makes their files missing, so the pages
  fall back to the stock `UI-LFG-BACKGROUND-*` pictures, as a client without them does.

## Render

```
Tools/UiLint/preview/render.sh Tools/UiLint/preview/scenes/windows.lua activities /tmp/activities.png \
    --stock ~/wow-art/stock --journal ~/wow-art/journal
```

`render.sh` with no arguments prints every option. The ones used most:

- `--size 1920x1080`: the window size in pixels.
- `--ui-scale S`: the player's UI scale. Without it the client picks its own scale for the window size; at 1080p
  that is the 0.9 minimum, so one UI unit is 1.27 px, as in the owner's screenshots.
- `--crop X0,Y0,X1,Y1` and `--scale F`: cut out a window and zoom in.
- `--bg flat|black|ground|air|<image>`: the background.
- `--hover all`: light every HIGHLIGHT layer.
- `--missing mark`: draw missing art in magenta.
- `--keep DIR`: keep the intermediate files.

Run it from any folder: paths are resolved from the script's own location.

Side by side:

```
python3 -I Tools/UiLint/preview/sheet.py /tmp/cmp.png --cols 2 --scale 2 \
    "/path/owner-screenshot.png@300,30,1530,840=owner" "/tmp/old.png@340,107,1570,917=render"
```

## Stock art: local only, never committed

Blizzard's interface art is not ours to publish, and this repository is public. Keep it outside the repository, or
in `Tools/UiLint/preview/stock/`, which is gitignored and used when `--stock` and `$BLEAKHOLD_STOCK_ART` are both
unset.

The renderer looks a path such as `Interface\DialogFrame\UI-DialogBox-Border` up under the stock folder as
`DialogFrame/UI-DialogBox-Border.*`, or as `Interface/DialogFrame/...`. It ignores case, as the client does, and
tries `.blp`, then `.tga`, then `.png`.

**Option 1: the Gethe/wow-ui-textures exports.** These are PNG exports of the live client. They are the same
classic files and close enough for previews. Use a blobless clone and fetch only the files you need:

```
git clone --filter=blob:none --no-checkout --branch live https://github.com/Gethe/wow-ui-textures ~/wow-art/stock
cd ~/wow-art/stock
git ls-tree -r --name-only HEAD > ../stock-list.txt   # to find names (folders are in their own case)
git checkout HEAD -- DialogFrame/UI-DialogBox-Border.PNG Buttons/UI-Panel-Button-Up.PNG ...
```

The stock files the addon names, to fetch (the `Interface\...` paths in its Lua; the folders' case differs in
the export, so look each one up in the listing):

```
grep -rhoE '"Interface\\\\[A-Za-z]+\\\\[^"]+' Interface/AddOns/Bleakhold | grep -v AddOns | sort -u
```

Some paths are built at run time from a prefix, such as `Interface\Buttons\UI-Panel-Button-` + `Up`, `Down`,
`Disabled` and `Highlight`; the command prints the prefix, and `render.py` lists every file it could not find on
stderr. Also needed:

- `CHARACTERFRAME/TempPortraitAlphaMaskSmall`, the circle `SetPortraitToTexture` uses. Without it the renderer
  draws its own circle.
- `LFGFRAME/UI-LFG-BACKGROUND-*`, the stock dungeon pictures the pages fall back to without the Journal art.
- The `ICONS/` the addon names. To list them:

  ```
  grep -rhoE 'Interface\\\\Icons\\\\[A-Za-z0-9_]+' Interface/AddOns/Bleakhold
  ```

  Also the icons of the demo's items (`ITEM_ICONS` in `driver.lua`), for example
  `ICONS/Spell_Holy_ProclaimChampion_02`, and the icon names in the scenes.

**Option 2: your own 3.3.5a client.** Extract the `Interface\` folders from the client's MPQs as `.blp` files.
`Tools/BlpConvert` decodes them.

## The Journal pictures: local only, never committed

The dungeon pictures are the owner's Dungeon Journal art: `bg_<KEY>.tga` (512x512) and `btn_<KEY>.tga` (256x128).
They reach players through the launcher's `extra/` layer as `Interface\AddOns\Bleakhold\Art\Journal\`. They are
never in this repository: that folder is gitignored, and the addon probes for the files and falls back to stock LFG
art (`tests/test_static.lua` checks this).

For previews, take them from an installed client (`Interface\AddOns\Bleakhold\Art\Journal\`) or from the
launcher's `extra/` files. Pass that folder as `--journal`, set `$BLEAKHOLD_JOURNAL_ART`, or copy the files into
`Tools/UiLint/preview/journal/` (gitignored).

## Scenes

A scene file returns a table of scenes:

```lua
local S = {}
S.before = {}                -- optional: S.before.name = function(M, env, P) ... end, before the addon loads
S.standalone = { name = true } -- optional: do not load the addon (scenes built from scratch)
S.name = function(M, ns, RS, env, P)
    M.env.SlashCmdList.BLEAKHOLD("demo")   -- the demo fixtures (Demo.lua)
    M.Advance(1)
    ns.UI.Open("activities")
    P.hover(ns.SomeButton)                 -- cursor over a frame: its HIGHLIGHT layer shows, OnEnter runs
    return M.env.BleakholdActivitiesFrame  -- optional: only these frames (a frame or a list) are drawn
end
return S
```

- `M` is the mock, and `ns` is the addon's namespace (empty for a standalone scene).
- `RS` is `ns.RoyaleStyle`, and `env` holds the game's globals.
- `P.run(fn, ...)` runs `fn` with the game's globals as its environment, so code written like an addon
  (`CreateFrame`, `UIParent`, ...) works unchanged.
- Never `print` from a scene: stdout carries the dump. The addon's Lua errors are collected and printed by
  `render.py`.

## What it draws like the client

Each item follows the client's own code under `Engine/Source/Frame/`.

**Layout and draw order** (`CLayoutFrame`):
- Each edge comes from the first point that sets it (TOPLEFT, LEFT, BOTTOMLEFT for the left edge, and so on). A
  point set again replaces the old one.
- Strata and levels: a child sits one level above its parent. `SetFrameStrata` reaches every child, and
  `SetFrameLevel` shifts the children with it.
- Within a strata and level, each draw layer is one batch (`CFrameStrataNode`).
- Inside one batch the renderer keeps the order the regions were made in. The client does not:
  `CRenderBatch::Finish` sorts a layer's meshes by texture (`qsort` on the GPU texture pointer, not stable), so two
  textures of one layer that overlap may stack either way in game, and a frame's backdrop fill is one of its
  BACKGROUND textures. A preview cannot show that, so never let the look depend on it: overlapping pieces that must
  stack go in different layers (see the top of `Widgets.lua`).
- Scroll children follow the scroll offset and are clipped to their scroll frame.

**Backdrops** (`CBackdropGenerator`):
- The background sits inside the insets. With `tile`, it repeats every `tileSize` (u = frame width / tileSize);
  otherwise it is stretched.
- The edge file holds eight cells, each 1/8 of its width, in this order: left, right, top, bottom, then the
  top-left, top-right, bottom-left and bottom-right corners. The top and bottom cells are stored turned.
- Edges repeat every `edgeSize`, with a 1/16-cell inset on the texcoords. Corners are `edgeSize` square.
- `SetBackdropColor` tints the background, and `SetBackdropBorderColor` tints all eight pieces.

**Textures**:
- TexCoord (all four corners), vertex colour, `SetGradient` and `SetGradientAlpha`.
- Alpha, and the blend modes BLEND, ADD, MOD, ALPHAKEY and DISABLE.
- Desaturation.
- Solid colours from `SetTexture(r, g, b, a)`.
- Tiling when `SetTexture(file, true)`.
- A texture with no size shows at its file's size.

**Widgets**:
- `StatusBar`: the fill covers the value's share of min..max, from the left or the bottom, and is hidden at 0.
- `Slider`: the thumb sits at (length - thumb) × position.
- Buttons: the Normal, Pushed and Disabled textures follow the button state (`SetButtonState`,
  `Enable`/`Disable`). The highlight texture is ADD, and `LockHighlight` works.
- `CheckButton`: the checked textures.
- `SetPortraitToTexture`: the icon resampled to 64x64 inside the portrait circle.
- Model frames (`Model`, `PlayerModel`, `DressUpModel`, `TabardModel`): the 3D model itself is not drawn (see
  below). `driver.lua` sends each shown one with its frame type, and `render.py` marks its box so it does not read
  as missing content. A box that shows the player (a `DressUpModel` or `TabardModel`, or a model given
  `SetUnit("player")`) holds a faint standing figure, with the caption "3D model (shown in game)" under it. Any
  other box, such as a mount or a pet, holds only the caption, grey FRIZQT 11, in its centre. A box with the figure
  that is too narrow for the caption, such as a transmog card, shows only the figure. A box without the figure
  makes the caption smaller instead. The mark sits where the client draws the model, over the frame's own layers,
  and frames above it still cover it.

**Text**:
- `FRIZQT__.TTF` is not in the repository. The addon's Marcellus Regular stands in for it, 9% wider and a third of
  a pixel heavier, with lining digits from Liberation Serif. This was measured against the owner's screenshot of
  the old window: at the same height, Friz Quadrata runs 7-13% wider. `MORPHEUS.TTF` uses Marcellus as before.
  `--font FRIZQT__.TTF=/path/FRIZQT__.TTF` uses a real copy, unchanged.
- Lines wrap at the region's width and keep `|c` colours across the wrap. `SetSpacing` and `JustifyH`/`JustifyV`
  apply, a fixed-height box truncates with "...", and shadows and outlines are drawn.

**Not drawn**: 3D models (only marked, as above), cooldown swipes, GameTooltip contents, and mipmapping. The client
samples UI art bilinearly with no mipmaps, and so does this renderer.

## The mock pieces previews rely on

`wowmock.lua` records:
- `SetTexture` solids, `__wrap` and `__tried`.
- Gradients and blend modes.
- Button state, checked, bar and thumb textures.
- `SetPortraitToTexture`.
- `JustifyV` and spacing.

It also provides `M.Hover(frame)` and StaticPopup1..4. The mock's `StaticPopup_Show` builds the stock dialog look,
and `M.StaticPopupClick(which, 1|2)` presses its buttons.

The mock's `GetItemIcon` answers `INV_Misc_QuestionMark` for every item, and the tests rely on that. The client reads
the icon from `Item.dbc`, so `driver.lua` wraps `GetItemIcon` (and the icon `GetItemInfo` returns) with `ITEM_ICONS`:
each item the demo hands out shows its own icon. Any other item still gets the question mark. Add an entry there when
the demo hands out a new item. A scene can still replace either function.
