// LM-1: GCC-only compatibility for the generated prelude, force-included (`-include`) by the Linux driver for GCC
// compiles of generated code only. Never used by Clang or by the Windows build.
//
// The production prelude (r3hd_pch.h, used verbatim) ends with the M2 block that redefines
// REX_FUNC_PROLOGUE() as `M2Enter(__func__, ctx); __builtin_assume(((size_t)base & 0x1F) == 0)`. GCC has no
// `__builtin_assume` (LM-1 retry 2: "error: '__builtin_assume' was not declared in this scope", r3hd_pch.h:369, in
// every selected function). This is the same assumption in the pinned codegen template's own GCC form
// (resources/templates/codegen/pch_h.inja: `if (!(x)) __builtin_unreachable()`), exactly as the audited LGE shim
// (tools/experiments/linux_guest_entry/m2_trace.h) defines it. The generated sources are not changed.
#pragma once
#if defined(__GNUC__) && !defined(__clang__)
#if !defined(__has_builtin) || !__has_builtin(__builtin_assume)
#define __builtin_assume(expr) \
  do {                         \
    if (!(expr)) __builtin_unreachable(); \
  } while (0)
#endif
#endif
