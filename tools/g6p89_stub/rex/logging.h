// G6-P89 host-test stub of <rex/logging.h>: the arithmetic in tools/g6p89_scale32.h is tested without the SDK.
#pragma once
#include <cstdio>
#define REXGPU_INFO(...) ((void)0)
#define REXGPU_WARN(...) ((void)0)
#define REXGPU_ERROR(...) (std::fprintf(stderr, "G6P89 REFUSE (stub log)\n"))
namespace rex {
inline void FlushLogging() { std::fflush(stderr); }
}  // namespace rex
