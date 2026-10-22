#!/usr/bin/env bash
# One command for everything UiLint checks:
#   1. build wowlua from the client's Lua 5.1 source (incremental)
#   2. extract the 3.3.5a API (functions, widget methods, events) from the client source
#   3. verify the committed art matches make_art.py
#   4. lint the addon, and self-test the linter on a broken addon
#   5. run the Lua unit tests against the WoW API mock
#
#   Tools/UiLint/check.sh            (exit code 0 = all clean)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
addon="$root/Interface/AddOns/Bleakhold"
build="$here/build"

echo "== build wowlua"
"$here/build_wowlua.sh" "$build" 2>&1 | grep -v "tmpnam" || true
test -x "$build/wowlua"

echo "== extract 3.3.5a API"
python3 -I "$here/extract_api.py" --lua "$build/api.lua" --summary | head -1

echo "== art"
rm -rf "$build/art-check"
python3 -I "$here/make_art.py" --out "$build/art-check" > /dev/null
for f in "$build/art-check"/*.tga; do
    if ! cmp -s "$f" "$addon/Art/$(basename "$f")"; then
        echo "art out of date: Art/$(basename "$f") (run python3 -I Tools/UiLint/make_art.py)"
        exit 1
    fi
done
echo "art matches make_art.py ($(ls "$build/art-check" | wc -l) files)"

echo "== lint"
python3 -I "$here/lint.py" --wowlua "$build/wowlua" "$addon"
python3 -I "$here/lint_selftest.py"

echo "== tests"
"$build/wowlua" "$here/testrunner.lua" "$root" "$addon" "$build/api.lua" "$here"/tests/test_*.lua
