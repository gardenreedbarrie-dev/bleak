#!/bin/bash
# Tests of the customization picker's model of the arrows' walk (WoW/Common/BleakholdCustomize.h), against a
# transliteration of the client's CharacterComponent.cpp option functions: builds test_customize_walk with the host's
# C++ compiler and runs it. Extra arguments go to the test (--dbc DIR runs it on a folder of DBC files as well).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
"${CXX:-c++}" -std=c++17 -O1 -Wall -Wextra -Werror -D_GLIBCXX_ASSERTIONS -I"$root" -o "$work/test_customize_walk" \
    "$here/test_customize_walk.cpp"
"$work/test_customize_walk" "$@"
