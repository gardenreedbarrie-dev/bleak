# WarcraftXL modern-asset transforms

Code from [WarcraftXL](https://github.com/WarcraftXL), the modding framework for the 3.3.5a client, that
converts models, map objects, terrain and textures made for newer clients into the 3.3.5a formats. It is
licensed under the **GNU General Public License v3.0 or later** (see `LICENSE` and the header of every file).

The client runs these conversions on the files it opens (see `Engine/Source/ModernAssets`).

## Where it comes from

| Directory | Repository | Commit |
|---|---|---|
| `shared/`, `host/` | [WarcraftXL/wxl-modern-assets](https://github.com/WarcraftXL/wxl-modern-assets) | `eb7c7c66461bda2941c549943e6a8884a006f436` (2026-07-17) |
| `include/structure/m2/M2Format.hpp` | [WarcraftXL/wxl-core](https://github.com/WarcraftXL/wxl-core) (`v1.1`, `src/engine/assets/shared/models/m2/`) | `4f8f455b73d2b8eb556294dea0904bd0a98edab0` (2026-10-21) |
| `adt/` | [WarcraftXL/wxl-cold-converter](https://github.com/WarcraftXL/wxl-cold-converter) (`converter/src/models/adt/`) | `87f12cde27611f1ceb9fa19ca7a25b7decb10c7a` (2026-07-17) |

The M3 (Heroes of the Storm) and DDS pipelines of wxl-modern-assets are not included.

## What was changed

- `include/core/Logger.hpp`, `include/Host.hpp`, `include/mpq/MpqStore.hpp` are Bleakhold's: they stand in
  for the wxl-core and WarcraftXL host headers the sources include, and are implemented by
  `Engine/Source/ModernAssets`.
- `host/models/m2/EquipmentFixes.cpp`: three `offsetof` sums are narrowed to `uint32_t` explicitly; on x64
  `offsetof` is 64 bits wide and the braced initializers did not compile.
- `host/textures/blp/BlpHost.cpp`: on x64 the texture size caps are 2048 instead of 1024 (and 256/512 for
  world textures), because they exist for the 32-bit client's address space; and `MayTransformBlp` was
  added, which answers from a BLP header alone whether `TransformBlp` could change the file.

The live-engine half of wxl-modern-assets (`src/common/BoneBudget.cpp`, `src/models/m2/Skin.cpp`) is ported
onto the client's own model structures in `Engine/Source/Model2/M2Modern.cpp`, and the index-start widening
of wxl-core (`src/client/CM2Shared/WideIndices.cpp`) is done in the client's own index fills and draws.

The per-texture terrain tiling of wxl-modern-adt (`src/render/HeightBlend.cpp`, the tiling half) is ported
onto the client's own terrain draw in `WoW/Source/WorldClient/MapTerrainTiling.cpp`, reading each tile's own
ATSC table. Its height blend is not: the terrain shaders shipped with wxl-modern-adt read a different register
layout from the one its height-blend code uploads.
