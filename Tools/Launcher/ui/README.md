# Launcher window (`ui/`)

The Bleakhold Launcher's window: plain HTML, CSS and JavaScript with no build step and no framework. The Tauri app
(`../app/`) embeds this folder as is. The page talks to the backend only through the commands, events, `State` and
phases in [`../DESIGN.md`](../DESIGN.md) (`window.__TAURI__.core.invoke` / `window.__TAURI__.event.listen`, with
`withGlobalTauri` on).

| file | what |
|---|---|
| `index.html` | the markup: title bar, art, news, realm card, bottom bar, settings drawer, install dialog |
| `app.css` | the styles (Bleakhold palette, Marcellus for titles, Inter for body text) |
| `app.js` | the logic: state, events, formatting, dialogs, toasts, embers |
| `mock.js` | a fake backend for browser previews; `app.js` loads it only when `window.__TAURI__` is missing |
| `assets/` | `background.webp` (the Bleakhold login painting, 1920x1080), `logo.webp` (the gold wordmark) |
| `fonts/` | Marcellus, Marcellus SC and Inter 400/500/600, each with its SIL OFL licence |

## Preview

Open `index.html` in Chromium or Edge (a `file://` URL works) and pick a state with `?scenario=`:

```
index.html                              full interactive run: loading, Install, download, verify, Play
index.html?scenario=first-run           new player, Install button
index.html?scenario=install-dialog      first-run dialog (also install-existing, install-low)
index.html?scenario=downloading         also paused, verifying (&installed=1: an update download)
index.html?scenario=update              update available
index.html?scenario=ready               also launching, playing
index.html?scenario=offline             server unreachable, Play still works (offline-new: not installed)
index.html?scenario=error&code=disk_full   error state and toast (codes from DESIGN.md; errors: three toasts)
index.html?scenario=settings            settings drawer
index.html?scenario=self-updating       the launcher updating itself
index.html?scenario=no-news             empty news
```

Extra parameters: `&realm=partial` (world server down) or `&realm=offline`, and `&warp=N` to speed up the fake
download. The fake commands log to the console (`[mock] open_url …`).

## Rules for changes

- Everything is local: the window's CSP allows only its own files, so no CDN, no inline `<script>` or `style=""`
  (setting `element.style` from JavaScript is fine), and backend text only goes through `textContent`.
- The layout is designed for a 1180x700 window. A smaller window shows the same layout scaled down.
- Animations (drift, portal glow, embers) stop while the window is hidden or the game runs, and are off under
  "reduce motion".
- The art comes from `Tools/BlpConvert/make_login_art.py --only background,logo --preview <dir>`:
  `LoginBackground.png` scaled back to 16:9 and saved as WebP (quality 90), `LoginLogo.png` trimmed to its
  visible pixels and saved as lossless WebP. Keep the whole folder small (it is embedded in the exe; now about
  0.6 MB).
