#!/bin/bash
# Tests of the glow pass's rules (Engine/Source/Model2/M2Glow.h, BLEAKHOLD(glow)): builds test_glow_draw with the
# host's C++ compiler and runs it on the repo, whose CharacterComponent.cpp section table and BleakFx bloom settings
# it checks the rules against.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
"${CXX:-c++}" -std=c++17 -O1 -Wall -Wextra -Werror -D_GLIBCXX_ASSERTIONS -I"$root" -o "$work/test_glow_draw" \
    "$here/test_glow_draw.cpp"
"$work/test_glow_draw" "$root"
