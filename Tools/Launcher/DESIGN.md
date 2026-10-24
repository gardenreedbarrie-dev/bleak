# Bleakhold Launcher: design

One file, `BleakholdLauncher.exe`, is everything a player needs. A friend runs it, picks a folder, and it downloads
the whole game (the 3.3.5a client, the realm's patches and the Bleakhold client files), creates shortcuts, sets the
realmlist and starts the game. Every later start checks for updates and downloads only what changed, and the
launcher updates itself first when a newer launcher is out.

This file is the contract between the parts:

- `core/` — Rust library: manifest, signature, paths, planner, downloader, local state, realmlist, self-update.
  No GUI; unit tests run on Linux (`cargo test` in `core/`).
- `app/` — the Tauri 2 application: window, commands, events; uses `core`. Built on Windows by CI.
- `ui/` — the window's HTML, CSS and JavaScript (no build step, no framework), its art and fonts. `ui/mock.js`
  stands in for the backend when the page is opened in a browser, so every screen can be previewed.
- The VPS side (manifest generator, signing, publishing, the file server) lives in the server repository,
  `deploy/launcher/`.

No Blizzard file is in this repository: the launcher downloads the game from the realm's own server.

## Hosting

The launcher knows one base URL (`launcher.json`, compiled in), default `http://185.217.124.41:8090/`. Under it:

| URL | What |
|---|---|
| `manifest.json` | the file list (below) |
| `manifest.json.sig` | base64 Ed25519 signature over the exact bytes of `manifest.json` |
| `objects/<h0h1>/<h>` | every file, stored by its SHA-256 `h` (lower-case hex; `h0h1` = its first two characters) |
| `BleakholdLauncher.exe` | the newest launcher, the link to give friends |

Content-addressed objects make publishing atomic: the publisher adds new objects, then replaces the manifest, and
removes unreferenced objects only later, so a player downloading during a publish never gets a mixed set.

A file may also name a mirror (`u`, below): another server with the same bytes, such as Reforged's own download
storage for Reforged's patches. The launcher tries the mirror first and the realm's object after it, so the
realm's `objects/` must hold every file, mirrored or not.

## Manifest (format 1)

UTF-8 JSON. Unknown fields are ignored (newer publishers may add some).

```json
{
  "format": 1,
  "product": "Bleakhold",
  "build": "2026-10-23 16:00 c74f1eb",
  "realmlist": "185.217.124.41",
  "exe": "Bleakhold.exe",
  "objects": "objects/",
  "cache_epoch": 1,
  "launcher": { "version": "1.0.0", "size": 8123456, "sha256": "…" },
  "files": [
    { "p": "Data/common.MPQ", "s": 2911342017, "h": "…" },
    { "p": "Data/patch-A.MPQ", "s": 2708937193, "h": "…", "u": "https://pub-….r2.dev/patch-A.mpq", "pack": "hd" },
    { "p": "WTF/Config.wtf", "s": 812, "h": "…", "once": true }
  ],
  "news": [ { "title": "…", "date": "2026-10-23", "body": "…", "url": "https://…" } ],
  "links": { "website": "https://…", "discord": "https://…", "register": "https://…" },
  "server": { "name": "Bleakhold", "host": "185.217.124.41", "auth_port": 3724, "world_port": 8085 },
  "packs": [ { "id": "hd", "name": "HD graphics", "about": "Reforged's HD models and textures", "default": true } ]
}
```

- `p`: path relative to the install folder, `/`-separated. The launcher rejects the whole manifest if any path is
  empty, absolute, has a drive letter, a `\`, a `..` or `.` component, an empty component, a control character, a
  character Windows forbids in names (`:` — which would also write an NTFS alternate data stream —, `<`, `>`, `"`,
  `|`, `?`, `*`), a component ending in a dot or a space (Windows drops those, so two names could be one file), a
  Windows reserved name (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`, with or without extension), a
  name the launcher keeps for itself (anything under `.bleakhold/`, a name ending in `.part`, `Bleakhold
  Launcher.exe`), or if two entries differ only by case, or one entry is a folder of another (`Data` and
  `Data/x`). A manifest without files is rejected too.
- `s`: size in bytes; `h`: SHA-256, 64 lower-case hex characters.
- `once`: install when missing, never overwrite or delete (settings files the player may change).
- `packs`: optional parts of the game a player may leave out (at most 16): `id` (1-32 of `a-z`, `0-9`, `-`,
  unique), `name` (1-60 characters), `about` (at most 300), `default` (on for a player who has not chosen; false
  when absent). No control characters anywhere.
- `pack`: the pack a file belongs to; it must be one of `packs`. Such a file is installed only while its pack is on.
  A `once` file and the `exe` cannot belong to a pack.
- `u`: optional mirror of the file, an absolute `http://` or `https://` URL of printable ASCII without spaces, at
  most 2048 characters (anything else rejects the manifest). It is fetched like an object and checked against `h`.
- `cache_epoch`: when it differs from the one stored locally, the launcher empties `Cache/` before the next start.
- `launcher`: the newest launcher; its object is `objects/<h0h1>/<sha256>` like any file.
- `exe`: a valid path ending in `.exe`. The launcher starts it only when it is among `files` (not `once`): Play
  checks the file against that entry's hash.
- `realmlist` and `server.host`: letters, digits, `.`, `-` and `:` only (they are written into `.wtf` files as is).
- The publisher never lists `WTF/` (except `once` defaults), `Cache/`, `Logs/`, `Errors/`, `Screenshots/`,
  `Data/<locale>/realmlist.wtf`, the launcher itself, `.bleakhold/` or `*.part` (the launcher's own state and
  partial downloads) among `files`.

Signature: Ed25519 (RFC 8032) over the manifest bytes as downloaded, base64 in `manifest.json.sig`; public key:
base64 of the raw 32 bytes, in `launcher.json`. The VPS signs with OpenSSL 3:
`openssl pkeyutl -sign -inkey manifest.key -rawin -in manifest.json -out sig.bin`, and prints the public key with
`openssl pkey -in manifest.key -pubout -outform DER | tail -c 32 | base64`. Whitespace and line breaks in the
`.sig` are ignored (plain `base64` wraps at 76 columns). A manifest whose signature does not verify is never used.
The two files are fetched one after the other and a publish replaces them one after the other, so on a mismatch the
launcher fetches both again once, about 2 s later, before reporting `signature`. `core/tests/vector/` holds a
manifest signed that way (its private key was thrown away). While `launcher.json` still holds the placeholder key
`REPLACE_WITH_VPS_PUBLIC_KEY`, the launcher trusts nothing: phase `error` (code `signature`) with a message saying
so, and `install` is refused.

## Local state

- Settings: `%APPDATA%\Bleakhold Launcher\settings.json` — `install_dir`, `parallel` (1-8, default 4),
  `limit_mbps` (megabytes per second, 1 MB = 10^6 bytes; the window sends a whole number 0-1000; 0 = no limit),
  `close_on_play` (default true), `shortcuts` (bool), `packs` (the player's choices, pack id → bool; a pack not
  listed follows its `default`), and `self_update_sha` (the launcher a self-update installed; see rule 2; not changed
  by the window).
- Install state: `<install>\.bleakhold\state.json` — for every file the launcher installed: `p`, `s`, `h`, and the
  file's size and modification time (`size`, `mtime` in ns) when it was verified, `once` for `once` files; plus
  `cache_epoch`, the last manifest `build`, `exe` and `realmlist` (for Play while offline), and `job` while a
  download is unfinished (`build`, `total_bytes`, `files_total` of the job when it began).
- The last verified manifest and its signature: `%APPDATA%\Bleakhold Launcher\manifest-cache\`; verified again
  before use, it gives news, links, the server and Play while offline.
- Log: `%APPDATA%\Bleakhold Launcher\launcher.log` (rotated at 1 MB, the previous one kept as `launcher.log.1`).

## Update rules

1. Fetch `manifest.json` and `.sig`; verify; validate. Unreachable: phase `offline` (Play stays possible if the
   game is installed; news, links and the server come from the last verified manifest). Bad signature or invalid:
   phase `error`, nothing changes.
2. If `launcher.version` is newer (semver) than the running launcher: download its object, verify the SHA-256,
   remember that SHA-256 (`self_update_sha`), rename the running exe to `<name>.old.exe`, move the new one into
   place, start it with the same arguments plus `--after-update <pid>` (it waits for the old process to end, which
   holds the single-instance lock), exit. Every start deletes a leftover `.old.exe`. Phase `self_updating`, its
   message naming the new version. Loop guard: a launcher that still finds itself older than the manifest's
   launcher while that launcher's SHA-256 is the remembered one (a mislabelled publish) does not update again and
   logs it; the mark is cleared once the running launcher is current. Installing copies the running launcher to
   `<install>\Bleakhold Launcher.exe` (the shortcuts point to it); a current launcher keeps that copy current.
3. Plan, over the files the player installs (every file outside a pack, and those of the packs that are on): a
   file needs downloading when it is missing, or its size differs, or (size equal, but size, mtime or hash in
   the state differ, or the state has no entry) its SHA-256 differs; a file found right by hash is adopted into the
   state, a wrong one dropped from it. "Repair" hashes every file. `once` files are only checked for presence.
4. Before downloading, the free space must hold what is left to download plus 64 MB (`disk_full`). Download
   `objects/<h0h1>/<h>` to `<path>.part`, resuming with `Range` when a `.part` exists; stream through SHA-256; a
   mismatch deletes the `.part` and retries (3 tries, then error `hash`; a network failure also gets 3 tries,
   keeping the `.part`). A resumed `.part` that turns out stale (from an older version of the file) starts over
   once without counting a try. Then rename over the target (replaces on Windows; a read-only target is made
   writable first). A target in use (the game is running) stops the update with error `game_running`; Update and
   Repair refuse to start while `Bleakhold.exe` runs. A file with a mirror (`u`) is fetched from the mirror first;
   when that try fails in any way (unreachable, an HTTP error, a cut connection, other bytes), the realm's object
   takes over for the normal tries, continuing a kept `.part`, and the mirror's failure is not counted as a try.
5. Delete files the state lists that the manifest no longer lists, or whose pack the player turned off (never
   `once` files, never files the launcher did
   not install: a player's own addons and screenshots are safe). Paths compare case-insensitively: a case-only
   rename never deletes the file just downloaded. Folders left empty are removed.
6. Save state after every file (at most every 0.5 s, and after every file of 8 MB or more; always when a download
   ends or stops), so a stop or crash resumes where it was. A launcher closed during a download starts in phase
   `paused` with the job's progress; Resume continues it.
7. Before Play: check `<exe>` is the verified file (size and mtime as in the state, else its SHA-256), write
   `set realmlist <realmlist>` to `Data/<xxYY>/realmlist.wtf` for every locale folder, set
   `SET realmList "<realmlist>"` in `WTF/Config.wtf` (create or replace that line only), empty `Cache/` when the
   epoch changed, start `<install>\<exe>` with the install folder as working directory.

Existing install: when the player points at a folder that already holds WoW 3.3.5a, the plan above simply finds
most files already right; matching files are adopted into the state, the rest is downloaded.

Install folder: `install` uses the chosen folder as it is, except that a whole drive (`D:\`), or a folder which
already holds other things (not empty, no WoW client — `Data/common.MPQ` or `Wow.exe` —, no Bleakhold install, not
itself named `Bleakhold`), gets a `Bleakhold` subfolder. `folder_info` answers for that final folder and returns it
as `path`. Before the first install, `State.install_dir` is the suggested folder: `C:\Games\Bleakhold` when it can
be created, else `%USERPROFILE%\Games\Bleakhold`. There is no command to move an install (1.0).

## Publishing

CI (`.github/workflows/build.yml`) keeps one rolling GitHub prerelease, tag `client-latest`, with these assets:

| asset | what |
|---|---|
| `bleakhold-client-x64.zip` | the player package: the build's `bleakhold-client-x64` artifact (entries under `Bleakhold/`) without the owner's `Tools/` (RaceForge) and without `INSTALL.txt`, which only the CI artifact keeps |
| `bleakhold-client.commit` | one line: the full commit SHA the package was built from (for the manifest's `build`) |
| `BleakholdLauncher.exe` | the launcher |
| `BleakholdLauncher.version` | the launcher's version, one line of semver text (`1.0.0`) |

Only pushes and manual runs on `main` and `claude/new-session-4tx7g2` publish. The assets are replaced in the order
above, the launcher before its version file, so a publisher that sees a new version also finds its exe. The
launcher alone is also the build artifact `bleakhold-launcher` (exe and version file). They download without a
GitHub account from
`https://github.com/gardenreedbarrie-dev/bleak/releases/download/client-latest/<asset>`. The VPS publisher (server
repository, `deploy/launcher/`) fetches them, lays the client package over the base client and the realm's patches,
writes and signs the manifest and serves it all.

## Building

- `core/`: `cargo test` (any OS; the Windows CI job runs it too). Everything that decides something lives here.
- `app/`: `cargo build --release` on Windows gives `target/release/BleakholdLauncher.exe` (portable, no bundle; the
  `custom-protocol` feature, on by default, embeds `ui/`). `launcher.json` next to its `Cargo.toml` is compiled in:
  before handing out a launcher, put the VPS public key (the `openssl pkey … | base64` line above) into
  `public_key`. The version is in `app/Cargo.toml` and `app/tauri.conf.json` (they must agree; CI checks).
- `app/icons/make_icon.py` (Pillow) draws the icons from the repository's Marcellus SC font.

## Window ↔ backend

Commands (`window.__TAURI__.core.invoke(name, args)`), all async. Arguments are snake_case exactly as written here
(the app's commands use `rename_all = "snake_case"`). A command that fails rejects with `{ code, message }` (codes
as for the `error` event): `install` (folder not usable or not writable, no key, launcher busy), `folder_info`
(not a full path), `play` (not ready), `save_settings` (cannot write), `open_folder` (not installed), `open_url`
(not `http(s)://`), `choose_folder` (dialog failure). The others ignore a request that does not fit the phase.

| command | args | returns |
|---|---|---|
| `get_state` | — | `State` (below) |
| `choose_folder` | — | path string or `null` (native folder dialog) |
| `folder_info` | `{ path }` | `{ path, free_bytes, needed_bytes, has_game, writable }` (`path`: the folder `install` will use) |
| `install` | `{ path, desktop_shortcut, start_menu }` | — (starts the download) |
| `check` | — | — (fetches the manifest again) |
| `update` | — | — |
| `pause` / `resume` / `cancel` | — | — (cancel goes back to `needs_install` or `needs_update`) |
| `repair` | — | — |
| `play` | — | — |
| `save_settings` | `{ settings }` | — (takes `parallel`, `limit_mbps`, `close_on_play`, `shortcuts`, `packs`; the limit applies at once; a changed pack choice changes the files to install at once — before installing, `total_bytes`, `pending_bytes` and `folder_info` follow; an installed game is checked again: `needs_update` to download a pack, or the pack's files are removed) |
| `open_folder` | — | — |
| `open_url` | `{ url }` | — (only `http(s)://`) |
| `clear_cache` | — | — |
| `minimize` / `close` | — | — |

`State`:
```json
{
  "launcher_version": "1.0.0",
  "phase": "ready",
  "message": "",
  "installed": true,
  "install_dir": "C:\\Games\\Bleakhold",
  "settings": { "parallel": 4, "limit_mbps": 0, "close_on_play": true, "shortcuts": true, "packs": { "hd": true } },
  "build": "2026-10-23 16:00 c74f1eb",
  "total_bytes": 17123456789,
  "pending_bytes": 0,
  "news": [], "links": {},
  "server": { "name": "Bleakhold", "online": true, "auth": true, "world": true, "ping_ms": 41 },
  "packs": [ { "id": "hd", "name": "HD graphics", "about": "…", "bytes": 21260000000, "on": true } ]
}
```

`total_bytes` counts the files the player installs (packs that are off left out); `packs` lists the manifest's
packs with their size and whether they are on (a box in the install dialog, a switch in the settings).
`install_dir` is the suggested folder until the game is installed (see "Install folder"); `server` is `null` until
the first probe, `ping_ms` `null` when the realm does not answer; `online` means both ports answer.

Events (`window.__TAURI__.event.listen(name, cb)`, payload in `e.payload`):

| event | payload |
|---|---|
| `phase` | `{ phase, message }` |
| `progress` | `{ done_bytes, total_bytes, speed_bps, eta_s, file, files_done, files_total }` (`eta_s` `null` while unknown) |
| `server` | `{ name, online, auth, world, ping_ms }` (every 30 s) |
| `error` | `{ code, message }` — codes: `network`, `signature`, `manifest`, `disk_full`, `game_running`, `hash`, `io`, `launch` |

One `progress` event follows right after a `downloading`, `verifying`, `self_updating` or `paused` phase begins
(also when a start goes straight to `paused`); while verifying, `files_done`/`files_total` count hashed files.
Download progress counts the whole job, also across a pause or a restart. The `error` event comes right before
`phase: error`. A Retry (`check`) after a failed download continues it.

Phases: `loading`, `offline`, `needs_install`, `needs_update`, `downloading`, `verifying`, `paused`, `ready`,
`launching`, `playing`, `self_updating`, `error`. The big button follows the phase: Install (needs_install), Update
(needs_update), Pause/Resume (downloading/paused), Play (ready, offline when installed), Playing (playing), Retry
(error).

The window: 1180x700 logical pixels, frameless, not resizable or maximizable, with the system shadow, centred; on a
work area smaller than that (e.g. 1080p at 150 %) it opens smaller at the same aspect ratio and the page scales
itself. `withGlobalTauri` is on; the CSP allows only the app's own files (images and fonts also `data:`), no inline
script or style attribute. The window may only listen to events, start dragging, minimize and close itself, open
a folder dialog and open `http(s)` links; everything else goes through the commands above.
