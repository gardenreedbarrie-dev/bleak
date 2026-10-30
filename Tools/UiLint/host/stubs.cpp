// Engine functions the client's Lua links against, given host definitions for wowlua.
// sgetu8/sputu8 are not here: build_wowlua.sh copies them out of Engine/Source/Base/ConvertUTF.cpp at
// build time, so the host always uses the client's own UTF-8 code (string.upper/lower depend on it).
#include <cstdint>
#include <ctime>
uint64_t OsGetAsyncTimeClocks() { return static_cast<uint64_t>(clock()); }
void OsValidateFunctionPointer(const void*) {}
