// LGE replacement for the project's Windows-only tools/m2_host/m2_trace.h.
//
// The production generated prelude (r3hd_pch.h, used verbatim) ends with the
// M2 observational block, which includes "m2_trace.h" and redefines
// REX_FUNC_PROLOGUE() as `M2Enter(__func__, ctx); __builtin_assume(...)`.
// Production M2Enter only records the current function/context in host
// thread-locals (and logs when probes are enabled); it never touches guest
// memory or guest registers. This shim keeps that contract: lge_tests.cpp
// records the entered function names for the per-case call trace and nothing
// else. It is the only substituted dependency of the generated code.
#pragma once
#include <rex/ppc/context.h>

void M2Enter(const char* name, PPCContext& ctx);

// GCC does not provide Clang's __builtin_assume; the M2 prologue uses it
// unconditionally. This is exactly the pinned template's own GCC form of the
// same base-alignment assumption (pch_h.inja: if (!x) __builtin_unreachable()).
#if defined(__GNUC__) && !defined(__clang__)
#if !defined(__has_builtin) || !__has_builtin(__builtin_assume)
#define __builtin_assume(expr) \
  do {                         \
    if (!(expr)) __builtin_unreachable(); \
  } while (0)
#endif
#endif
