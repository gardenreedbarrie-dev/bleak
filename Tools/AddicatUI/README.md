# AddicatUI

Bleakhold's interface: action bars, unit frames, cast bars, minimap, micro menu, bags, chat, nameplates, world
map, spellbook, talents and more in a retail style, with an editor mode and profiles. It is a fork of
[DragonUI](https://github.com/NeticSoul/DragonUI) by NeticSoul and DragonUI's contributors (MIT licence), which
credits Dragonflight UI (Classic) by Karl-HeinzSchneider and the other projects listed in its
`THIRD_PARTY_NOTICES.md`. The addons are `Interface/AddOns/AddicatUI` and `Interface/AddOns/AddicatUI_Options`;
`/aui` (or `/addicatui`) opens the settings, `/aui edit` the editor mode.

## What is not in this repository

DragonUI ships World of Warcraft artwork (its textures are Blizzard's art, from the 3.3.5a, retail and Classic
clients and from WoW Forever), the Expressway font, whose licence asks for payment when it comes with software,
and tables made from the game's DBC files and AzerothCore's tables. None of that is published here
(`.gitignore`). `sync_dragonui.py art` puts it into a client's or a package's AddOns folder from a DragonUI
checkout:

- the textures and the font go into their own addon, `AddicatUI_Art`, which AddicatUI needs
  (`## Dependencies: AddicatUI_Art`): without the art the game does not load AddicatUI at all, instead of showing
  empty frames;
- the tables go into `AddicatUI`, whose namespace they fill.

The CI package builds the AddicatUI art package only when it is asked to (the workflow's
`addicatui_art` input): it fetches DragonUI at the commit in `UPSTREAM` and uploads `addicatui-art` as an artifact
of its own, so whether that art is handed to players stays the server owner's decision.

By hand, with Python 3:

```sh
git clone https://github.com/NeticSoul/DragonUI dragonui
git -C dragonui checkout c949e12fe544efc6236c71c96654f36bafbc50c6
python3 -I Tools/AddicatUI/sync_dragonui.py art dragonui "<WoW folder>/Interface/AddOns"
```

## The code

`sync_dragonui.py code <dragonui checkout>` made `Interface/AddOns/AddicatUI*` from DragonUI (the commit in
`UPSTREAM`): DragonUI is renamed AddicatUI in names, paths and text, `/dui` is `/aui`, the art's paths point into
`AddicatUI_Art`, and the licence texts are copied word for word. AddicatUI has changes of its own on top, so a newer
DragonUI comes in by running `code` on a branch that holds only the previous import and merging it.

Do not run DragonUI and AddicatUI together: both replace the same frames.
