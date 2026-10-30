#!/usr/bin/env bash
# Renders a Bleakhold UI scene to a PNG, from the real addon code, with stock 3.3.5a art when you have it locally.
#
#   Tools/UiLint/preview/render.sh <scenes.lua> <scene> <out.png> [options]
#
#   --size WxH         window size in pixels (default 1920x1080)
#   --ui-scale S       the player's UI scale (useUiScale 1); default none: the client's own scale for the window
#   --stock DIR        stock 3.3.5a art laid out like Interface\ (DialogFrame/, Buttons/, ...; any case; PNG, BLP or
#                      TGA); default $BLEAKHOLD_STOCK_ART, else Tools/UiLint/preview/stock when it exists
#   --journal DIR      the Journal pictures (bg_<KEY>, btn_<KEY>); default $BLEAKHOLD_JOURNAL_ART, else
#                      Tools/UiLint/preview/journal when it exists; without one the pages fall back to the stock LFG
#                      pictures, as a client without them does
#   --bg KIND          flat (default) | black | ground | air | an image file (scaled to cover the window)
#   --hover all        light every frame's HIGHLIGHT layer (default: only frames the scene hovers or locks)
#   --crop X0,Y0,X1,Y1 crop the PNG (pixels)          --scale F   then resize it by F
#   --missing mark     draw textures whose file is missing in magenta (default: leave them out)
#   --strict           fail when a texture file is missing
#   --addon DIR        the addon folder (default <repo>/Interface/AddOns/Bleakhold)
#   --font NAME=FILE   a face for a client font (FRIZQT__.TTF=..., MORPHEUS.TTF=...); repeatable
#   --font-stretch F   width factor of the FRIZQT stand-in (default 1.09; 1 with a real FRIZQT__.TTF)
#   --keep DIR         keep the driver dumps and measurements in DIR
#
# Needs Tools/UiLint/build/wowlua and api.lua (Tools/UiLint/check.sh builds both) and python3 with numpy and Pillow.
# See README.md next to this file for the scene format and where the stock art comes from (never commit it).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../../.." && pwd)"
uilint="$repo/Tools/UiLint"

usage() { sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2; }
[ $# -ge 3 ] || usage
scenes="$1"; scene="$2"; out="$3"; shift 3

size=1920x1080; uiscale=0; stock="${BLEAKHOLD_STOCK_ART:-}"; journal="${BLEAKHOLD_JOURNAL_ART:-}"; bg=flat
hover=none; crop=""; scale=""; missing=skip; strict=0; addon="$repo/Interface/AddOns/Bleakhold"; keep=""
fonts=()
while [ $# -gt 0 ]; do
    case "$1" in
        --size) size="$2"; shift 2 ;;
        --ui-scale) uiscale="$2"; shift 2 ;;
        --stock) stock="$2"; shift 2 ;;
        --journal) journal="$2"; shift 2 ;;
        --bg) bg="$2"; shift 2 ;;
        --hover) hover="$2"; shift 2 ;;
        --crop) crop="$2"; shift 2 ;;
        --scale) scale="$2"; shift 2 ;;
        --missing) missing="$2"; shift 2 ;;
        --strict) strict=1; shift ;;
        --addon) addon="$2"; shift 2 ;;
        --font) fonts+=(--font "$2"); shift 2 ;;
        --font-stretch) fonts+=(--font-stretch "$2"); shift 2 ;;
        --keep) keep="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "render.sh: unknown option $1" >&2; usage ;;
    esac
done
if [ -z "$stock" ] && [ -d "$here/stock" ]; then stock="$here/stock"; fi
if [ -z "$journal" ] && [ -d "$here/journal" ]; then journal="$here/journal"; fi
[[ "$size" =~ ^([0-9]+)x([0-9]+)$ ]] || { echo "render.sh: --size wants WxH, got $size" >&2; exit 2; }
w="${BASH_REMATCH[1]}"; h="${BASH_REMATCH[2]}"
[ -f "$scenes" ] || { echo "render.sh: no scene file $scenes" >&2; exit 2; }
wowlua="$uilint/build/wowlua"; api="$uilint/build/api.lua"
if [ ! -x "$wowlua" ] || [ ! -f "$api" ]; then
    echo "render.sh: build wowlua and the API first: Tools/UiLint/check.sh (or build_wowlua.sh + extract_api.py)" >&2
    exit 2
fi
[ -n "$stock" ] || echo "render.sh: no --stock folder: stock WoW art will be missing (see README.md)" >&2

abs() { (cd "$(dirname "$1")" && echo "$(pwd)/$(basename "$1")"); }
scenes="$(abs "$scenes")"; out="$(abs "$out")"
if [ -n "$keep" ]; then
    mkdir -p "$keep"; work="$(cd "$keep" && pwd)"
else
    work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fi
roots=(--repo "$repo" --addon "$addon")
[ -n "$stock" ] && roots+=(--stock "$stock")
[ -n "$journal" ] && roots+=(--journal "$journal")
[ ${#fonts[@]} -gt 0 ] && roots+=("${fonts[@]}")

# no Journal pictures: the driver makes their files missing, so the addon falls back to the stock LFG art as a client
# without them does (instead of a picture that is "loaded" but never drawn)
journalflag=1
if [ -z "$journal" ] || [ ! -d "$journal" ]; then
    journalflag=0
    echo "render.sh: no --journal folder: the pages show the stock LFG pictures, as a client without them" >&2
fi
driver() {
    "$wowlua" "$here/driver.lua" "$repo" "$addon" "$api" "$scenes" "$scene" "$w" "$h" "$uiscale" "$1" "hover=$hover" \
        "journal=$journalflag"
}
# pass 1 lays out with estimates; render.py measures the real text and texture sizes; pass 2 lays out with them
driver "" > "$work/pass1.json"
python3 -I "$here/render.py" measure "$work/pass1.json" "$work/measure.lua" "${roots[@]}"
driver "$work/measure.lua" > "$work/pass2.json"
draw=(--bg "$bg" --missing "$missing" --strict "$strict")
[ -n "$crop" ] && draw+=(--crop "$crop")
[ -n "$scale" ] && draw+=(--scale "$scale")
python3 -I "$here/render.py" draw "$work/pass2.json" "$out" "${roots[@]}" "${draw[@]}"
