#!/usr/bin/env bash
# mod-bleakhold-ui: every test in one command (Linux; needs clang++ or g++, python3).
#
#   Server/mod-bleakhold-ui/tests/run_tests.sh [options]
#
#   --fuzz-iterations N     mutation fuzzer inputs (default 300000)
#   --fuzz-seconds S        libFuzzer run time when clang's libFuzzer is available (default 60, 0 = skip)
#   --azerothcore DIR       also compile the module against an AzerothCore checkout: DIR/azerothcore-wotlk
#                           with this module in modules/ and a configured build in DIR/build (see README)
#
# Steps:
#   1. the core-independent protocol sources compile cleanly on their own (-Wall -Wextra -Wconversion -Werror)
#   2. C++ unit tests, every example frame of docs/BleakholdProtocol.md           (ASan + UBSan)
#      and the café's rule tests, cpp/bh_cafe.cpp and cpp/bh_cafe_crowd.cpp, once they exist; they see src/ and, for a
#      core-free stand-in of an AzerothCore header (Position.h), cpp/stub/ when it exists
#   3. frames for every server message from the C++ encoders -> the addon's real Lua parser and state
#      (the client's own Lua 5.1 in wowlua, the WoW API mock of Tools/UiLint), at frame sizes 1000/251/64
#   4. every intent the addon sends (captured from the mock's SendAddonMessage) -> the C++ parser and
#      rate limiter, with the client's own timing                                  (ASan + UBSan)
#   5. fuzzing of the parser, the rate limiter and the encoders                    (ASan + UBSan)
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mod="$(cd "$here/.." && pwd)"
repo="$(cd "$mod/../.." && pwd)"
build="$here/build"
fuzzIterations=300000
fuzzSeconds=60
acDir=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fuzz-iterations) fuzzIterations="$2"; shift 2 ;;
        --fuzz-seconds) fuzzSeconds="$2"; shift 2 ;;
        --azerothcore) acDir="$2"; shift 2 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done

mkdir -p "$build"
if command -v clang++ > /dev/null; then CXX="${CXX:-clang++}"; else CXX="${CXX:-g++}"; fi
proto="$mod/src/protocol"
protoSrc=("$proto"/*.cpp)
san=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
flags=(-std=c++20 -g -O1 -Wall -Wextra -Wshadow -Werror -I"$proto" -I"$here/cpp")
export ASAN_OPTIONS="detect_leaks=1:abort_on_error=1"
export PYTHONDONTWRITEBYTECODE=1
export UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=1"

step() { echo; echo "== $*"; }

step "1. protocol sources compile on their own ($CXX)"
for f in "${protoSrc[@]}"; do
    extra=()
    [[ "$CXX" == *clang* ]] && extra=(-Wconversion -Wsign-conversion -Wpedantic)
    "$CXX" -std=c++17 -Wall -Wextra -Wshadow -Werror "${extra[@]}" -I"$proto" -c "$f" -o /dev/null
done
if command -v g++ > /dev/null && [[ "$CXX" != "g++" ]]; then
    for f in "${protoSrc[@]}"; do g++ -std=c++20 -Wall -Wextra -Wshadow -Werror -I"$proto" -c "$f" -o /dev/null; done
fi
echo "ok: ${#protoSrc[@]} files, no AzerothCore headers needed"

step "2. unit tests and the document's examples (ASan/UBSan)"
for t in bh_unit bh_gen bh_intents bh_fuzz; do
    "$CXX" "${flags[@]}" "${san[@]}" "$here/cpp/$t.cpp" "${protoSrc[@]}" -o "$build/$t"
done
"$build/bh_unit" "$repo"
cafeInc=(-I"$mod/src")
[[ -d "$here/cpp/stub" ]] && cafeInc+=(-I"$here/cpp/stub")
for t in bh_cafe bh_cafe_crowd; do
    if [[ -f "$here/cpp/$t.cpp" ]]; then
        "$CXX" "${flags[@]}" "${san[@]}" "${cafeInc[@]}" "$here/cpp/$t.cpp" "${protoSrc[@]}" -o "$build/$t"
        "$build/$t" "$repo"
    else
        echo "$t: cpp/$t.cpp not written yet, skipped"
    fi
done

step "3. C++ frames -> the addon's Lua parser (wowlua + Tools/UiLint mock)"
uilint="$build/uilint"
"$repo/Tools/UiLint/build_wowlua.sh" "$uilint" 2>&1 | grep -v "tmpnam" || true
test -x "$uilint/wowlua"
python3 -I "$repo/Tools/UiLint/extract_api.py" --root "$repo" --lua "$uilint/api.lua" > /dev/null
for size in 1000 251 64; do
    "$build/bh_gen" "$size" "$build/frames_$size.lua"
done
set +e
"$uilint/wowlua" "$repo/Tools/UiLint/testrunner.lua" "$repo" "$repo/Interface/AddOns/Bleakhold" "$uilint/api.lua" \
    "$here/lua/test_server_frames.lua" "$here/lua/test_capture_intents.lua" > "$build/lua.log" 2>&1
luaStatus=$?
set -e
grep -v "^BHC	" "$build/lua.log"
if [[ $luaStatus -ne 0 ]]; then
    echo "Lua tests failed" >&2
    exit 1
fi

step "4. every intent the addon sends -> the C++ parser and rate limiter (ASan/UBSan)"
grep "^BHC	" "$build/lua.log" > "$build/intents.txt"
"$build/bh_intents" "$build/intents.txt"

step "5. fuzzing (ASan/UBSan)"
"$build/bh_fuzz" "$fuzzIterations" 1 "$build/intents.txt"
if [[ "$fuzzSeconds" != "0" && "$CXX" == *clang* ]]; then
    if "$CXX" "${flags[@]}" -DBH_LIBFUZZER -fsanitize=fuzzer,address,undefined -fno-sanitize-recover=all \
        "$here/cpp/bh_fuzz.cpp" "${protoSrc[@]}" -o "$build/bh_libfuzzer" 2> "$build/libfuzzer_build.log"; then
        corpus="$build/corpus"
        rm -rf "$corpus" && mkdir -p "$corpus"
        i=0
        while IFS=$'\t' read -r _ _ body; do
            printf '%s' "$body" > "$corpus/intent_$i"
            i=$((i + 1))
        done < "$build/intents.txt"
        "$build/bh_libfuzzer" -max_total_time="$fuzzSeconds" -max_len=400 -print_final_stats=1 -artifact_prefix="$build/" "$corpus" 2>&1 \
            | grep -E "^(#[0-9]+.*DONE|stat::number_of_executed_units|stat::peak_rss_mb|==[0-9]+==ERROR|INFO: (Loaded|Running))" || true
        if ls "$build"/crash-* > /dev/null 2>&1; then
            echo "libFuzzer found a crash" >&2
            exit 1
        fi
        echo "libFuzzer: no crash in ${fuzzSeconds}s"
    else
        echo "libFuzzer not available ($CXX); skipped (see $build/libfuzzer_build.log)"
    fi
fi

if [[ -n "$acDir" ]]; then
    step "6. the module against AzerothCore ($acDir)"
    cmake "$acDir/build" > /dev/null
    cmake --build "$acDir/build" --target modules --parallel
    cmake --build "$acDir/build" --target worldserver --parallel
fi

echo
echo "all mod-bleakhold-ui tests passed"
