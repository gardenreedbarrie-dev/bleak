#!/usr/bin/env bash
# Runs every Bleakhold glue scenario (login screen, race buttons on the stock screen and on a realm patch's own, first
# and last names on the stock screen and on a realm patch's own two-names screen, the appearance rows) against the mock of the
# 3.3.5a glue API, with the client's own Lua (Tools/UiLint/build/wowlua, built by check.sh).
#   Tools/UiLint/glue/run.sh [wowlua]      (exit code 0 = every scenario passed)
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
wowlua="${1:-$here/../build/wowlua}"
glue="$root/Interface/Bleakhold/Glue"
rc=0
for s in login login-classic login-noart login-noscanevent login-stockignoresscan login-autoaccept races12 races12-female races10 races13 \
         races12-noart races12-nudged races12-scaled custom-chain custom-tplanchor custom-offsets custom-scaled custom-slots \
         custom-rows custom-parent custom-seven custom-full custom-template custom-template-stock \
         custom-ownlayout names names-off names-paid names-realm names-realm-odd names-realm-unnamed \
         names-realm-outside names-realm-hint names-realm-late \
         picker-stock picker-plain picker-stage0 picker-stage1 picker-marks picker-dk picker-stale \
         picker-paid picker-selftest picker-selftest-all picker-selftest-bad; do
    "$wowlua" "$here/tests.lua" "$here" "$glue" "$s" || rc=1
done
exit $rc
