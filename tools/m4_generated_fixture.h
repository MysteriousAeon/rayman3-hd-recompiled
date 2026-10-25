// Test harness for unmodified, privately extracted output of the real emitter.
// Stubs replace dependencies only; tested owners and filters are actual output.
#include "r3hd_pch.h"
#include <rex/m4_seh.h>
#include <cstdio>
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
static uint32_t cleanup_r12, cleanup_r31;
alignas(32) static uint8_t memory[0x20000];
#define GCHECK(c) do { ++checks; if (!(c)) { ++failures; std::printf("FAIL: %s\n", #c); } } while (0)
static void SyntheticWork(PPCContext& ctx, uint8_t*) {
  if (!mode) return;
  ctx.r1.u32 -= 0x80; ctx.r31.u64 = 0xDEAD;
  M4GuestRecord rec{}; rec.code = 0xC0000017; M4Raise(rec);
}
static PPCFunc* FixtureResolve(uint32_t a, uint8_t*) {
  if (a == 0x82821684) return sub_82821684;
  if (a == 0x820E7D2C) return sub_820E7D2C;
  if (a == 0x820E0000) return SyntheticWork;
  // Finally lookup must use the same dependency as the owner's normal call.
  if (a == 0x826D5BF4) return sub_826D5BF4;
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
  // This target's handler terminates instead of returning. Catch a test-only
  // host marker outside the owner to verify label entry without terminating.
  RaiseException(0xE04734AA, 0, 0, nullptr);
}
REX_FUNC(sub_820E7C78) {}
REX_FUNC(sub_826D53E8) { SyntheticWork(ctx, base); }
REX_FUNC(sub_826D5BF4) { ++cleanup; cleanup_r12 = ctx.r12.u32; cleanup_r31 = ctx.r31.u32; }
static int Catch(EXCEPTION_POINTERS* ep, uint32_t& escaped) {
  M4GuestRecord rec{};
  escaped = M4ToGuestRecord(ep, rec) ? rec.code : ep->ExceptionRecord->ExceptionCode;
  return EXCEPTION_EXECUTE_HANDLER;
}
static uint32_t Invoke(PPCFunc* fn, PPCContext& ctx) {
  uint32_t escaped = 0;
  __try { fn(ctx, memory); } __except (Catch(GetExceptionInformation(), escaped)) {}
  return escaped;
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
  std::printf("actual emitter execution: %d checks, %d failures: %s\n", checks, failures, failures ? "FAIL" : "PASS");
  return failures ? 1 : 0;
}
