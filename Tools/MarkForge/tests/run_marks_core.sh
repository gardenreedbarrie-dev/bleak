#!/bin/bash
# Tests of the client's glowing marks core (WoW/Common/ComponentCore/BleakMarks.h, BLEAKHOLD(glow)) and of the marks by
# player GUID (BleakMarkOwners.h, BLEAKHOLD(marks)): builds test_marks_core and test_mark_owners with the host's C++
# compiler (warnings as errors, sanitizers where the compiler has them) and runs them.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cxx="${CXX:-c++}"
sanitize=""

if echo 'int main(){}' | "$cxx" -x c++ -fsanitize=address,undefined -o "$work/probe" - >/dev/null 2>&1; then
    sanitize="-fsanitize=address,undefined -fno-sanitize-recover=all"
fi

for test in test_marks_core test_mark_owners; do
    # shellcheck disable=SC2086
    "$cxx" -std=c++17 -O1 -g -Wall -Wextra -Wconversion -Wno-sign-conversion -Werror -D_GLIBCXX_ASSERTIONS $sanitize \
        -I"$root" -o "$work/$test" "$here/$test.cpp"
    "$work/$test"
done
