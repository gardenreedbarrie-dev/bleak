// Force-included into every Lua source file when building wowlua on Linux (see ../build_wowlua.sh).
// The client's Lua calls a few engine functions for profiling and pointer checks; the host gives them
// plain definitions so the unmodified client Lua sources compile with g++.
#ifndef UILINT_SHIM_H
#define UILINT_SHIM_H
#include <cstdint>
#include <ctime>
typedef long long __int64;
inline int64_t OsGetAsyncClocksPerSecond() { return CLOCKS_PER_SEC; }
#endif
