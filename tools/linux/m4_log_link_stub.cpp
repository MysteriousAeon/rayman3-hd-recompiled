// LM-A A3 (WSL/Linux test link only; never part of a game or SDK build): the two SDK logging entry points that the
// M4 headers' log macros reference, without the SDK runtime. GetLoggerRaw returns no logger, and every SDK log macro
// checks the pointer first, so logging is inert. Used by tools/m4_real_owner_test.py on a host without a Linux SDK.
#include <rex/logging/api.h>

#include <cstdio>
#include <cstdlib>
#include <rex/ppc/func.h>

namespace rex {
LogCategoryId RegisterLogCategory(const char*) { return LogCategoryId{0}; }
spdlog::logger* GetLoggerRaw(LogCategoryId) { return nullptr; }
namespace runtime {
// The fixture resolves every indirect target itself; reaching the SDK's global fallback is a test failure.
PPCFunc* ResolveIndirectFunction(uint32_t target) {
  std::fprintf(stderr, "m4_log_link_stub: unexpected ResolveIndirectFunction(%08X)\n", target);
  std::abort();
}
}  // namespace runtime
}  // namespace rex
