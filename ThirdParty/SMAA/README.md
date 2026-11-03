# SMAA

[SMAA: Subpixel Morphological Antialiasing](https://github.com/iryoku/smaa) by Jorge Jimenez, Jose I. Echevarria,
Belen Masia, Fernando Navarro and Diego Gutierrez, under the MIT license (`LICENSE.txt`).

| File | From the repository at commit `71c806a838bdd7d517df19192a20f0c61b3ca29d` (2013-11-06) |
|---|---|
| `SMAA.hlsl` | `SMAA.hlsl` |
| `AreaTex.h` | `Textures/AreaTex.h` |
| `SearchTex.h` | `Textures/SearchTex.h` |
| `LICENSE.txt` | `LICENSE.txt` |

The files are unchanged. BleakFx (`Engine/Source/BleakFx`) runs SMAA 1x with luma edge detection and the High
preset as its `bleakFxAA 2` anti-aliasing, compiled for Direct3D 9 shader model 3 (`Shaders/bh_smaa_*.hlsl`). Gx
has no A8L8 texture format, so the client stores the area and search textures as A8R8G8B8 with their data in red
and green, and the shaders select those channels (`SMAA_AREATEX_SELECT`, `SMAA_SEARCHTEX_SELECT`).
