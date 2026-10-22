#!/bin/bash
# Tests of the grass wind shader patch (Engine/Source/Gx/BleakGrassWind.cpp): builds test_grasswind with the
# host's C++ compiler, checks the patcher on the stand-in shader and on made-up bytecode, then runs both shaders
# on test vertices (emulate.py, needs numpy) against a reference of the wind.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
"${CXX:-c++}" -std=c++17 -O1 -Wall -Wextra -Werror -I"$root" -o "$work/test_grasswind" \
    "$here/test_grasswind.cpp" "$root/Engine/Source/Gx/BleakGrassWind.cpp"
"$work/test_grasswind" "$here"
python3 -I "$here/emulate.py" "$here" "$work/test_grasswind"
