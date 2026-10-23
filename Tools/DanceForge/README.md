# DanceForge

Makes the Bleakhold dances: the choreography, the catalogue and every file made from it. A player picks a dance in
the addon (Collections > Animations, the emote wheel, `/bh dance <name>` or the dance's own command), the addon sends
`DANCE <id>`, the server module sets the player's emote state to the stock dance and sends
`SMSG_PLAY_SPELL_VISUAL` kit 910000 + id to everyone nearby (and again at every loop), and Bleakhold.exe plays clip
`id` of `Interface\Bleakhold\Dances\Dances.bdc` on that character until the emote state goes
(`docs/BleakholdProtocol.md`, section 14).

## How a dance gets onto a character

A clip moves a canonical skeleton of 22 joints (`dflib/skeleton.py`): hips, three spine joints, neck, head,
clavicles, upper arms, forearms, hands, thighs, calves, feet and toes, in a T-pose measured in hip-joint heights, with
WoW's axes (+x forward, +y left, +z up). Each frame stores the hips position and every joint's world rotation
relative to that rest pose.

Character models have no bone names, so the client works out the mapping itself the first time a model dances
(`Engine/Source/Model2/BleakDance.cpp`, `BuildRig`): the key bones give Root, SpineLow, the head, the clavicles and
the upper arms; the hands are the common parent of the finger key bones; the forearm is the bone between; the
legs are the lowest animated chains on each side outside the upper body (digitigrade legs, ankle twins and helper
bones included); the spine and neck bones in between share the canonical spine's turn. Each mapped bone gets the
rotation that lines its bind pose up with the canonical rest pose, and in the bone loop the client sets every
mapped bone's local transform so it ends up with the clip's world rotation, whatever its parents and helper bones
do. Bones the rig does not map keep the animation underneath. A model the rig cannot map (no finger key bones,
no spine to the shoulders) keeps its own animation.

`dflib/retarget.py` is the reference of that code; `tests/run_tests.py` builds the C++ with g++ and checks that both
give the same rig and the same local transform for every bone and frame on made-up skeletons (`tests/synth.py`: a
human, a gnome, hunched and hoofed shapes, a tail instead of legs, and models that cannot dance). No game data is
in this folder.

## Commands

```sh
python3 -I Tools/DanceForge/danceforge.py generate            # DanceData.lua, BleakholdDance.h, the music README
python3 -I Tools/DanceForge/danceforge.py generate --check    # exit 1 and name any stale file
python3 -I Tools/DanceForge/danceforge.py pack [--out FILE]   # the clip pack (default Interface/Bleakhold/Dances/Dances.bdc)
python3 -I Tools/DanceForge/danceforge.py check               # catalogue, every dance, generated files, pack round trip
python3 -I Tools/DanceForge/danceforge.py list                # the dances with tempo and loop length
python3 -I Tools/DanceForge/tests/run_tests.py                # the tests
```

Standard library only (Python 3.10 or newer); the C++ half of the tests needs g++ or clang++. The CI package builds
the pack with `pack`; the pack is not in the repository (`.gitignore`).

| File | What it is |
|---|---|
| `Interface/AddOns/Bleakhold/DanceData.lua` | The addon's list (`Data.danceCategories`, `Data.dances`) |
| `Server/mod-bleakhold-ui/src/BleakholdDance.h` | The server module's count, loop lengths (for the loop kits) and keys |
| `Interface/Bleakhold/Dances/Music/README.txt` | How to add music, with every dance's key, tempo and loop length |
| `Interface/Bleakhold/Dances/Dances.bdc` | The clips (built by `pack`) |

## Choreography

A dance is a function in `dances/` returning a `dflib.choreo.Dance`: keyed poses on beats, eased between, plus
grooves and follow-through. Every control of `dflib/rig.py` is its own channel, so a key sets only the controls it
names, and channels loop:

```python
from dflib.choreo import Dance
from moves import arms_fk, feet, groove, hands, hips, merge, STANCE

def my_dance():
    d = Dance(bpm=120, beats=4)                      # one loop: four beats at 120 BPM
    d.key(0, **merge(hips(z=-0.06), hands((0.3, 0.25, 0.1), (0.3, -0.25, 0.1))))
    d.key(1, ease="snap", hand_l=(0.2, 0.3, 0.5))    # hit this pose on beat 1
    d.key(2, ease="pop", lift=0.15, foot_r=(0.2, -0.13, 0.105))   # step, the foot arcs up on the way
    d.key(0, **feet(STANCE))
    d.overlay(groove(depth=0.03))                    # the bounce every dance rides on
    d.follow("head_tilt", "spine_side", gain=0.5)    # the head lags the torso
    return d
```

Controls (angles in degrees, positions in hip heights): `hips` (x, y, z) and `hips_yaw/pitch/roll`;
`spine_bend/side/twist`; `head_nod/tilt/turn`; `clav_up/fwd_l/r`; arms either by hand position (`hand_l/r` in the
chest's frame and `elbow_l/r`, two-bone IK) or by angles (`arm_l/r` = swing, raise, bend, twist) with `ik_l/r`
blending the two; `wrist_l/r` (bend, side, twist); legs by ankle position (`foot_l/r`, ground at z = 0) with
`knee_l/r`, and `foot_yaw/pitch/roll_l/r`, `toe_l/r`. Eases: `smooth` (the default), `inout`, `in`, `out`, `snap`,
`pop`, `back`, `linear`, `hold` (`dflib/choreo.py`).

## Adding a dance

1. Write its function in a module of `dances/` and list it in that module's `DANCES`.
2. Append it to `dances` in `dances.json` with the next id, a new key (`[a-z][a-z0-9_]`, at most 32 characters; the
   music file and saved wheels use it), a name (at most 24 characters), a slash command that no stock emote or chat
   command uses, a category and the source (`module:function`). Append the key to `FROZEN_KEYS` in
   `tests/run_tests.py`.
3. Run `generate`, `check` and the tests.
4. Rebuild the server module (it refuses ids at or above `DanceCatalogueCount`) and repackage the client (the pack
   and `DanceData.lua`). Players with an older package do not have the new dance.

## Ids are append-only

The id goes on the wire, saved emote wheels hold `dance:<key>` and music files carry the key's name. Never renumber,
rename, reuse or remove a dance; `tests/run_tests.py` holds every released key in `FROZEN_KEYS`.

## Originality

The dances are Bleakhold's own choreography in the style of well-known social, party and street dances (a dance
style is free for anyone to dance). Do not copy animation data, names or music from games or other products into
this folder. Music for the dances is added by each server for its players (`Interface/Bleakhold/Dances/Music`), and
only music the server has the rights to belongs there.
