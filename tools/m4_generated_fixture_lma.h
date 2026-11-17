// LM-A A3: backend-neutral harness for unmodified, privately extracted output of the real emitter (macro emission).
// The same checks as tools/m4_generated_fixture.h (the Windows-only M4 fixture), with one difference in the harness:
// instead of a host __except that accepts everything, the escaping guest exception is accepted by a harness owner
// written with the same emission macros and an accept-all filter, which is what that host handler did. A host marker
// (the terminating handler body) leaves as a C++ exception. Stubs replace dependencies only; the tested owners and
// filters are actual output. Built against both backends by tools/m4_real_owner_test.py.
#include "r3hd_pch.h"
#include <rex/m4_seh.h>
#include <cstdio>
#include <cstdlib>
thread_local const char* m2_current_function = nullptr;
thread_local PPCContext* m2_current_context = nullptr;
void M2Enter(const char*, PPCContext&) {}
DECLARE_REX_FUNC(sub_82821618);
DECLARE_REX_FUNC(sub_82821684);
DECLARE_REX_FUNC(sub_820E7CE0);
DECLARE_REX_FUNC(sub_820E7D2C);
DECLARE_REX_FUNC(sub_826D5BB0);
DECLARE_REX_FUNC(sub_826D5BF4);
static int mode, returned_raise, cleanup, body, failures, checks;
static uint32_t cleanup_r12, cleanup_r31, g_escaped;
static PPCFunc* g_invoke_fn;
alignas(32) static uint8_t memory[0x20000];
struct HostMarker { uint32_t code; };
#define GCHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL: %s\n", #c); } } while (0)
static void SyntheticWork(PPCContext& ctx, uint8_t*) {
  if (!mode) return;
  ctx.r1.u32 -= 0x80; ctx.r31.u64 = 0xDEAD;
  M4GuestRecord rec{}; rec.code = 0xC0000017; M4Raise(rec);
}
static void HarnessFilter(PPCContext& ctx, uint8_t* base) {  // accept everything, remember the code
  g_escaped = M4Ld32(base, M4Ld32(base, ctx.r3.u32)); ctx.r3.s64 = 1;
}
static PPCFunc* FixtureResolve(uint32_t a, uint8_t*) {
  if (a == 0x82821684) return sub_82821684;
  if (a == 0x820E7D2C) return sub_820E7D2C;
  if (a == 0x820E0000) return SyntheticWork;
  if (a == 0x826D5BF4) return sub_826D5BF4;
  if (a == 0x7000) return HarnessFilter;
  std::abort();
}
#undef REX_LOOKUP_FUNC
#define REX_LOOKUP_FUNC(b, a) FixtureResolve(a, b)
REX_FUNC(sub_822FFFA0) {
  M4GuestRecord rec{}; rec.code = mode == 1 ? 0x406D1388 : 0xC0000017;
  M4Raise(rec); ++returned_raise;
}
REX_FUNC(sub_820E7648) { ctx.r3.u64 = 0x1000; M4St32(base, 0x106C, 0x820E0000); }
REX_FUNC(__imp__KeBugCheck) {
  ++body; GCHECK(ctx.r31.u32 == 0x10000 - 96); GCHECK(ctx.r1.u32 == 0x10000 - 96);
  // This target's handler terminates instead of returning; a host marker verifies label entry instead.
  throw HostMarker{0xE04734AA};
}
REX_FUNC(sub_820E7C78) {}
REX_FUNC(sub_826D53E8) { SyntheticWork(ctx, base); }
REX_FUNC(sub_826D5BF4) { ++cleanup; cleanup_r12 = ctx.r12.u32; cleanup_r31 = ctx.r31.u32; }

static void HarnessOwner(PPCContext& ctx, uint8_t* base) {
  static const M4Scope m4scopes[] = {{0x100, 0x200, 0x7000, 0x300}};
  auto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* { return REX_LOOKUP_FUNC(b, a); };
  M4_FRAME(1)
m4_retry:
  M4_TRY_BEGIN
  uint32_t m4resume = m4.resume; m4.resume = 0; m4.resume_index = m4.count; m4.unwind = false;
  switch (m4resume) { case 0x300: goto loc_300; case 0: break; default: M4_FAIL(7); }
  m4.pc = 0x104; M4BeforeCall(m4, ctx); g_invoke_fn(ctx, base); m4.in_call = false;
  M4_RETURN
loc_300:
  M4_RETURN
  M4_TRY_END
}
static uint32_t Invoke(PPCFunc* fn, PPCContext& ctx) {
  g_escaped = 0; g_invoke_fn = fn;
  try { HarnessOwner(ctx, memory); } catch (const HostMarker& m) { return m.code; }
  return g_escaped;
}
static PPCContext Fresh() { PPCContext ctx{}; ctx.r1.u64 = 0x10000; ctx.r31.u64 = 0x31313131; ctx.lr = 0x12345678; return ctx; }
static int GeneratedTests() {
  mode = 1; auto ctx = Fresh(); GCHECK(Invoke(sub_82821618, ctx) == 0);
  GCHECK(returned_raise == 1); GCHECK(ctx.r1.u32 == 0x10000); GCHECK(ctx.r31.u32 == 0x31313131);
  mode = 2; ctx = Fresh(); GCHECK(Invoke(sub_82821618, ctx) == 0);
  GCHECK(returned_raise == 1); GCHECK(ctx.r1.u32 == 0x10000); GCHECK(ctx.r31.u32 == 0x31313131);
  mode = 1; ctx = Fresh(); GCHECK(Invoke(sub_820E7CE0, ctx) == 0xE04734AA); GCHECK(body == 1);
  mode = 0; ctx = Fresh(); GCHECK(Invoke(sub_826D5BB0, ctx) == 0);
  GCHECK(cleanup == 1); GCHECK(cleanup_r12 == 0x10000); GCHECK(ctx.r1.u32 == 0x10000);
  mode = 1; ctx = Fresh(); GCHECK(Invoke(sub_826D5BB0, ctx) == 0xC0000017);
  GCHECK(cleanup == 2); GCHECK(cleanup_r12 == 0x10000); GCHECK(cleanup_r31 == 0x10000 - 96);
#if !(defined(_WIN32) && !defined(R3HD_M4_PORTABLE))
  GCHECK(m4p::top == nullptr);  // every owner left the registry
#endif
  std::printf("M4_REAL_OWNER_TEST %s checks=%d failures=%d returned_raise=%d body=%d cleanup=%d cleanup_r12=%X "
              "cleanup_r31=%X\n", failures ? "FAIL" : "PASS", checks, failures, returned_raise, body, cleanup,
              cleanup_r12, cleanup_r31);
  std::fflush(stdout);
  return failures ? 1 : 0;
}
