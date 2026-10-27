#!/bin/bash
# Tests of the storm wall's maths and noise (Engine/Source/BleakFx/BleakStorm.cpp, BleakFxStormNoise.cpp): builds
# test_storm with the host's C++ compiler and runs it on circle_cases.csv, the cases the addon's R.Circle is checked
# against too (Tools/UiLint/tests/test_royale.lua).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
"${CXX:-c++}" -std=c++17 -O1 -Wall -Wextra -Werror -D_GLIBCXX_ASSERTIONS -I"$root" -o "$work/test_storm" \
    "$here/test_storm.cpp" "$root/Engine/Source/BleakFx/BleakStorm.cpp" "$root/Engine/Source/BleakFx/BleakFxStormNoise.cpp"
"$work/test_storm" "$here"
