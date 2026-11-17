// LM-A A4: the two real setjmp owners (sub_82559C48, sub_82559DA8) and their real filter funclets, unmodified private
// extracts of the macro emission, against both M4 backends. Their callees are stubs that steer the real control flow:
// after setjmp returns 0 the owner calls 0x82559878, which here enters a synthetic intervening owner (finally scope)
// whose callee performs the guest longjmp back to the owner's setjmp. On Windows MSVC's longjmp unwinds through the
// intervening owner (its __finally runs); the portable backend must do the same before the host longjmp. After the
// longjmp the owner continues at its rc != 0 path (0x82559708). Scenario 1 also raises a guest exception there, inside
// the owner's except scope, which its real filter (li r3,1) accepts: the owner re-enters at its inline label.
// Built by tools/m4_real_owner_test.py; expected traces are asserted and must match across backends.
#include "r3hd_pch.h"
#include <rex/m4_seh.h>
#include <cstdio>
#include <cstdlib>
#include <string>
thread_local const char* m2_current_function = nullptr;
thread_local PPCContext* m2_current_context = nullptr;
void M2Enter(const char*, PPCContext&) {}
DECLARE_REX_FUNC(sub_82559C48);
DECLARE_REX_FUNC(sub_82559DA8);
DECLARE_REX_FUNC(sub_82559D90);
DECLARE_REX_FUNC(sub_82559EF0);
alignas(32) static uint8_t memory[0x20000];
static std::string g_trace;
static int scenario, failures, checks;
static void Ev(const char* e) { g_trace += e; g_trace += ' '; }
static void InterFinally(PPCContext& ctx, uint8_t*) { char b[32]; std::snprintf(b, sizeof b, "inter_finally=%u", ctx.r3.u32); Ev(b); }
static PPCFunc* FixtureResolve(uint32_t a, uint8_t*) {
  if (a == 0x82559D90) return sub_82559D90;
  if (a == 0x82559EF0) return sub_82559EF0;
  if (a == 0x7200) return InterFinally;
  std::abort();
}
#undef REX_LOOKUP_FUNC
#define REX_LOOKUP_FUNC(b, a) FixtureResolve(a, b)

static void InterCallee(PPCContext&, uint8_t*) {
  Ev("inter_longjmp");
  auto& jumps = get_jmp_buf_map();
  if (jumps.size() != 1) { std::printf("FAIL: %zu setjmp buffers\n", jumps.size()); std::abort(); }
  ppc_longjmp(jumps.begin()->first, 7);
}
// A synthetic owner with one finally scope around the call that longjmps, written as the emitter writes owners.
static void InterOwner(PPCContext& ctx, uint8_t* base) {
  static const M4Scope m4scopes[] = {{0x7010, 0x7020, 0x7200, 0}};
  auto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* { return REX_LOOKUP_FUNC(b, a); };
  M4_FRAME(1)
m4_retry:
  M4_TRY_BEGIN
  uint32_t m4resume = m4.resume; m4.resume = 0; m4.resume_index = m4.count; m4.unwind = false;
  switch (m4resume) { case 0: break; default: M4_FAIL(7); }
  m4.pc = 0x7014; M4BeforeCall(m4, ctx); InterCallee(ctx, base); m4.in_call = false;
  M4_RETURN
  M4_TRY_END
}
REX_FUNC(sub_82558768) { Ev("8768"); }
REX_FUNC(sub_825587A8) {  // returns 0: the owner goes on to its setjmp
  Ev("87A8"); ctx.r3.u64 = 0;
  if (scenario == 2) { M4GuestRecord rec{}; rec.code = 0xC0000017; M4Raise(rec); Ev("raise_returned"); }
}
REX_FUNC(sub_82559878) { Ev("9878"); if (scenario == 3) InterCallee(ctx, base); else InterOwner(ctx, base); }
REX_FUNC(sub_82559958) { Ev("9958"); }
REX_FUNC(sub_82559B40) { Ev("9B40"); }
REX_FUNC(sub_82559708) {  // the rc != 0 (after longjmp) path
  Ev("9708");
  if (scenario == 1 || scenario == 3) { M4GuestRecord rec{}; rec.code = 0xC0000017; M4Raise(rec); Ev("raise_returned"); }
  ctx.r3.u64 = 1;  // returns non-zero: the owner leaves its retry loop
}
REX_FUNC(sub_825597E8) { Ev("97E8"); }
REX_FUNC(sub_82558830) { Ev("8830"); }

static void Expect(const char* name, const char* want) {
  ++checks;
  std::printf("TRACE %s: %s\n", name, g_trace.c_str());
  if (g_trace != want) { ++failures; std::printf("FAIL %s want: %s\n", name, want); }
  std::fflush(stdout);
#if !(defined(_WIN32) && !defined(R3HD_M4_PORTABLE))
  ++checks;
  if (m4p::top != nullptr) { ++failures; std::printf("FAIL %s: owner registry not empty\n", name); }
#endif
}
static void Run(PPCFunc* owner, int s) {
  scenario = s; g_trace.clear(); get_jmp_buf_map().clear();
  PPCContext ctx{}; ctx.r1.u64 = 0x10000; ctx.r31.u64 = 0x10000;
  owner(ctx, memory);
}
// M4_SETJMP_SET=longjmp (default): the guest longjmp through an intervening owner; every backend must match.
// M4_SETJMP_SET=raise: guest raises inside these owners' except scopes (before any setjmp, after a direct longjmp,
// after a longjmp through an intervening owner). The portable backend must accept them at the owner's label (the
// real filter is li r3,1). The Windows SEH backend is recorded separately: in this harness its __except never reaches
// the owner's filter for these two owners and the raise ends the process unhandled (E-372; cause unknown).
static int SetjmpTests() {
  const char* set = std::getenv("M4_SETJMP_SET");
  if (set && std::string(set) == "raise") {
    Run(sub_82559C48, 2); Expect("C48_raise_before_setjmp", "8768 87A8 8830 97E8 ");
    Run(sub_82559C48, 3); Expect("C48_direct_longjmp_raise", "8768 87A8 9878 inter_longjmp 9708 8830 97E8 ");
    Run(sub_82559C48, 1); Expect("C48_longjmp_raise", "8768 87A8 9878 inter_longjmp inter_finally=1 9708 8830 97E8 ");
    Run(sub_82559DA8, 1); Expect("DA8_longjmp_raise", "8768 87A8 9878 inter_longjmp inter_finally=1 9708 8830 97E8 ");
  } else {
    Run(sub_82559C48, 0); Expect("C48_longjmp", "8768 87A8 9878 inter_longjmp inter_finally=1 9708 97E8 ");
    Run(sub_82559DA8, 0); Expect("DA8_longjmp", "8768 87A8 9878 inter_longjmp inter_finally=1 9708 97E8 ");
  }
  std::printf("M4_SETJMP_OWNER_TEST %s checks=%d failures=%d\n", failures ? "FAIL" : "PASS", checks, failures);
  std::fflush(stdout);
  return failures ? 1 : 0;
}
