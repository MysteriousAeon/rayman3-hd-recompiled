// LGE: GCC-compatible DEFINE_REX_FUNC, force-included before the verbatim
// generated prelude (r3hd_pch.h) for the generated object only.
//
// The pinned template (resources/templates/codegen/pch_h.inja, non-Apple branch)
// defines, under `#ifndef DEFINE_REX_FUNC`:
//   __attribute__((alias("__imp__" #name)))
//   __attribute__((weak, noinline)) extern "C" REX_FUNC(name);
//   REX_EXTERN(__imp__##name)
// GCC 16 rejects GNU attributes before a linkage specification ("attributes are
// not permitted in this position [-Wattributes]") and would IGNORE them, which
// drops the weak `name` alias. Native LGE attempt 2 failed exactly there, once
// per selected function. This is the same declaration with the same three
// attributes, placed after `extern "C"` where GCC's diagnostic says they may go,
// through the template's own `#ifndef DEFINE_REX_FUNC` extension point. The
// generated function bodies are unchanged. The gate's binary check requires
// every `name` to be a weak symbol at the address of its global `__imp__name`.
#pragma once
#include <rex/ppc/func.h>

#define DEFINE_REX_FUNC(name)                                                  \
  extern "C" __attribute__((alias("__imp__" #name), weak, noinline)) REX_FUNC(name); \
  REX_EXTERN(__imp__##name)
