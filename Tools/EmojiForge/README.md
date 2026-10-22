# EmojiForge

Holds the catalogue of the Bleakhold emoji bubbles and makes everything that comes from it. A player picks an emoji
in the addon (Collections > Animations > Emojis, the emote wheel or `/bh emoji <name>`), the addon sends `EMOJI <id>`,
the server module answers with `SMSG_PLAY_SPELL_VISUAL` kit 900000 + id, and the Bleakhold client draws
`Interface\Bleakhold\Emoji\Emoji<id>.blp` over that character's head (`docs/BleakholdProtocol.md`, section 13).

`emojis.json` is the source of truth: the id, key, name and group of every emoji, and where its picture comes from,
either a Noto Emoji 3D image (`"noto": "1f602"`, the codepoints of `emoji_u1f602.png`) or a short text drawn with
the Bangers font (`"text": "GG"`). From it EmojiForge writes:

| File | What it is |
|---|---|
| `Interface/AddOns/Bleakhold/EmojiData.lua` | The addon's list (`Data.emojiGroups`, `Data.emojis`) |
| `Server/mod-bleakhold-ui/src/BleakholdEmoji.h` | The server module's count (`EmojiCatalogueCount`, ids above it are refused) and keys |
| `Interface/Bleakhold/Emoji/NOTICE.md` | The attribution: the source of every picture |
| `Interface/Bleakhold/Emoji/EmojiNNN.blp` | The art: 256x256 BLP2, DXT5 with all 9 mip levels |

Never edit the generated files by hand; change `emojis.json` and run the tool. It needs Python 3.10 or newer; `art`
also needs Pillow (`pip install Pillow`). The BLPs are written by `Tools/BlpConvert/blpconvert.py`. Run it with `-I`.

## Commands

```sh
python3 -I Tools/EmojiForge/emojiforge.py generate            # write EmojiData.lua, BleakholdEmoji.h, NOTICE.md
python3 -I Tools/EmojiForge/emojiforge.py generate --check    # exit 1 and name any stale file
python3 -I Tools/EmojiForge/emojiforge.py art --noto DIR      # draw every EmojiNNN.blp
python3 -I Tools/EmojiForge/emojiforge.py check               # catalogue, generated files and art; exit 0 = clean
python3 -I Tools/EmojiForge/emojiforge.py patterns            # sparse-checkout patterns for noto-emoji
python3 -I Tools/EmojiForge/tests/run_tests.py                # the tests
```

`art` options:

- `--noto DIR`: a checkout of noto-emoji (below). Needed whenever a selected emoji is a Noto image, and it must be
  at the commit `emojis.json` pins (`noto.commit`); `--allow-other-commit` accepts another one.
- `--only joy,gg`: draw only these emojis.
- `--preview DIR`: also write each picture as `NNN_key.png` and all of them as `sheet.png`, on a dark background.
  Look at the sheet before you commit new art.
- `--jobs N`: encoder processes (default: all cores).

Each Noto image (512x512) is scaled to 240x240 in the middle of a transparent 256x256 canvas. A text emote is drawn
at twice the size in `font.fill` with a `font.stroke` outline (one twelfth of the font size), as large as fits a
232 px square, and scaled down. Every BLP is checked the way the client reads it.

## Fetching Noto Emoji at the pinned commit

The art needs only 73 of the repository's files, so fetch it as a blobless sparse clone. Set the patterns before the
checkout; `DIR` is any folder outside this repository, `<commit>` is `noto.commit` from `emojis.json`:

```sh
git clone --filter=blob:none --no-checkout --sparse https://github.com/googlefonts/noto-emoji DIR
git -C DIR fetch --depth 1 origin <commit>
git -C DIR sparse-checkout set --no-cone $(python3 -I Tools/EmojiForge/emojiforge.py patterns)
git -C DIR checkout FETCH_HEAD
python3 -I Tools/EmojiForge/emojiforge.py art --noto DIR --preview /tmp/emoji-preview
```

The patterns are `/LICENSE` and `/README.md` (the licence statements, below) and one
`/3D/png/512/emoji_u<codepoints>.png` per Noto emoji. Run `sparse-checkout set` again with the new patterns after
adding an emoji.

## Adding an emoji

1. Append it to `emojis` in `emojis.json` with the next id, a new key (`[a-z][a-z0-9_]`, at most 24 characters,
   what `/bh emoji <key>` and saved wheels use), a name (at most 24 characters of letters, digits, spaces and
   `'!?.-`) and a group. `/bh emoji` also finds an emoji by its name, so no name may read as another emoji's key or
   name. Append the key to `FROZEN_KEYS` in `tests/test_catalogue.py`.
2. Run `generate`, then `art --noto DIR --only <key> --preview DIR` (fetch the new Noto file first), and look at
   the preview.
3. Rebuild the server module (it refuses ids at or above `EmojiCatalogueCount`) and repackage the client (the new
   BLP and `EmojiData.lua`). Players with an older package do not see the new emoji.

At most 256 emojis fit the protocol (`EMOJI 0` to `EMOJI 255`, kits 900000 to 900255).

## Ids are append-only

The id goes on the wire and saved emote wheels hold `emoji:<key>`. Never renumber, rename, reuse or remove an
emoji: a realm and a client from different versions would show the wrong picture, and saved wheels would lose their
slots. `tests/test_catalogue.py` holds the keys of every released id in `FROZEN_KEYS`, and fails when the
catalogue does not start with exactly that list; the list grows with each new emoji. To retire an emoji, keep its
entry.

## Licences

- Noto Emoji images: Copyright 2013 Google LLC, from https://github.com/googlefonts/noto-emoji (folder
  `3D/png/512`). The project's `LICENSE` file is the SIL Open Font License 1.1 and its README states that image
  resources are under the Apache License 2.0, so both texts ship with the art:
  `Interface/Bleakhold/Emoji/LICENSE-OFL-NotoEmoji.txt` (that `LICENSE` file) and `LICENSE-Apache-2.0.txt`.
  The images are modified (scaled, put on a larger canvas and converted to BLP); `NOTICE.md` says so and names the
  source file of every BLP.
- Bangers font (`fonts/Bangers-Regular.ttf`, drawn into the text emotes): Copyright 2010 The Bangers Project
  Authors, SIL Open Font License 1.1 (`fonts/OFL.txt`, shipped with the art as `LICENSE-OFL-Bangers.txt`). Its
  sha256 is pinned in `emojis.json` so the text emotes come out the same everywhere.
- Only emoji art and fonts under these licences go into the catalogue: no pictures of real people, memes or
  characters owned by others.
