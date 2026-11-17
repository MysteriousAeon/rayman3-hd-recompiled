// LM-A A1: one synthetic suite for both M4 backends (tools/m4_portable_test.py builds and compares them).
//
// The owners below are written exactly as the emitter writes them (M4_FRAME / m4_retry / M4_TRY_BEGIN / resume
// switch / M4_RETURN / M4_TRY_END), so the same source exercises the Windows SEH backend (m4_seh.h, Windows) and the
// portable backend (m4_seh_portable.h: Linux, or Windows with R3HD_M4_PORTABLE). Every scenario records a trace;
// each backend must produce the expected trace, and the runner requires identical output from both backends.
// No game code, data or generated functions: addresses and tables are synthetic.
#include <rex/m4_seh.h>
#include <csetjmp>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>
#if defined(__linux__)
#include <pthread.h>
#include <unistd.h>
#include <atomic>
#endif

#if defined(_WIN32) && !defined(R3HD_M4_PORTABLE)
#define BACKEND "windows-seh"
static bool RegistryEmpty() { return true; }
#else
#define BACKEND "portable"
static bool RegistryEmpty() { return m4p::top == nullptr; }
#endif

alignas(16) static uint8_t g_mem[0x20000];
static std::string g_trace;
static int g_checks = 0, g_failures = 0;
static void Ev(const char* what) { g_trace += what; g_trace += ' '; }
static void EvHex(const char* what, uint32_t v) { char b[64]; std::snprintf(b, sizeof b, "%s=%X ", what, v); g_trace += b; }
#define CHECK(c) do { ++g_checks; if (!(c)) { ++g_failures; std::printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static PPCContext Fresh() { PPCContext ctx{}; ctx.r1.u64 = 0x10000; ctx.r31.u64 = 0x31313131; ctx.r14.u64 = 0x1414; return ctx; }

// ---- funclets (guest filter/finally stand-ins) and their dispositions -----------------------------------------
static int g_disp_inner = 0, g_disp_outer = 0;
static uint32_t RecordCode(PPCContext& ctx, uint8_t* base) {  // r3 = EXCEPTION_POINTERS, [0] = record, record[0] = code
  return M4Ld32(base, M4Ld32(base, ctx.r3.u32));
}
static void filter_inner(PPCContext& ctx, uint8_t* base) {
  EvHex("filter_inner", RecordCode(ctx, base)); CHECK(ctx.r4.u32 == ctx.r12.u32);
  ctx.r31.u64 = 0xBAD; ctx.r3.s64 = g_disp_inner;
}
static void filter_outer(PPCContext& ctx, uint8_t* base) {
  EvHex("filter_outer", RecordCode(ctx, base)); ctx.r3.s64 = g_disp_outer;
}
static void finally_inner(PPCContext& ctx, uint8_t*) { EvHex("finally_inner", ctx.r3.u32); ctx.r31.u64 = 0xBAD2; }
static void finally_outer(PPCContext& ctx, uint8_t*) { EvHex("finally_outer", ctx.r3.u32); }
static PPCFunc* Resolve(uint32_t a, uint8_t*) {
  switch (a) {
    case 0x9000: return filter_inner;
    case 0x9100: return filter_outer;
    case 0x9200: return finally_inner;
    case 0x9300: return finally_outer;
  }
  std::abort();
}

// ---- callees ------------------------------------------------------------------------------------------------------
static uint32_t g_raise_code = 0, g_raise_flags = 0;
static void callee_raise(PPCContext& ctx, uint8_t*) {
  ctx.r1.u32 -= 0x80; ctx.r31.u64 = 0xDEAD;
  M4GuestRecord rec{}; rec.code = g_raise_code; rec.flags = g_raise_flags; rec.address = 0x2000;
  M4Raise(rec);
  Ev("raise_returned"); ctx.r1.u32 += 0x80;
}
static uint32_t g_unwind_frame = 0, g_unwind_target = 0;
static void callee_unwind(PPCContext& ctx, uint8_t*) {
  ctx.r1.u32 -= 0x80; ctx.r31.u64 = 0xDEAD;
  M4UnwindRequest req{g_unwind_frame, g_unwind_target, 0x1234};
  M4RequestUnwind(req);
  Ev("unwind_returned");
}
static void callee_host_throw(PPCContext&, uint8_t*) { throw std::runtime_error("host"); }

// ---- guest setjmp/longjmp lowering, as the pch does it ---------------------------------------------------------
static jmp_buf g_jmp;
#if defined(_WIN32) && !defined(R3HD_M4_PORTABLE)
#define TEST_SETJMP(a) setjmp(g_jmp)
static void TestLongjmp(uint32_t, int v) { longjmp(g_jmp, v); }
#else
#define TEST_SETJMP(a) (M4NoteSetjmp(a), setjmp(g_jmp))
static void TestLongjmp(uint32_t a, int v) { M4LongjmpPrepare(a); longjmp(g_jmp, v); }
#endif
static void callee_longjmp(PPCContext&, uint8_t*) { Ev("longjmp"); TestLongjmp(0x500, 7); }

// ---- owners, written as the emitter writes them -------------------------------------------------------------------
// One except scope (filter 0x9100 -> label 0x1030) around a call; label checks owner restoration.
static void owner_single(PPCContext& ctx, uint8_t* base) {
  static const M4Scope m4scopes[] = {{0x1010, 0x1020, 0x9100, 0x1030}};
  auto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* { return Resolve(a, b); };
  M4_FRAME(1)
m4_retry:
  M4_TRY_BEGIN
  uint32_t m4resume = m4.resume; m4.resume = 0; m4.resume_index = m4.count; m4.unwind = false;
  switch (m4resume) { case 0x1030: goto loc_1030; case 0: break; default: M4_FAIL(7); }
  ctx.r1.u32 -= 0x60; ctx.r31.u64 = 0x3131; m4.pc = 0x1014;
  M4BeforeCall(m4, ctx); callee_raise(ctx, base); m4.in_call = false;
  Ev("after_call"); ctx.r1.u32 += 0x60;
  M4_RETURN
loc_1030:
  Ev("label"); CHECK(ctx.r31.u32 == 0x3131); CHECK(ctx.r1.u32 == 0x10000 - 0x60); ctx.r1.u32 += 0x60;
  M4_RETURN
  M4_TRY_END
}

// Inner owner: finally scope (0x9200) and except scope (0x9000 -> 0x2030) around the same call.
static void owner_inner(PPCContext& ctx, uint8_t* base) {
  static const M4Scope m4scopes[] = {{0x2010, 0x2020, 0x9000, 0x2030}, {0x2010, 0x2020, 0x9200, 0}};
  auto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* { return Resolve(a, b); };
  M4_FRAME(2)
m4_retry:
  M4_TRY_BEGIN
  uint32_t m4resume = m4.resume; m4.resume = 0; m4.resume_index = m4.count; m4.unwind = false;
  switch (m4resume) { case 0x2030: goto loc_2030; case 0: break; default: M4_FAIL(7); }
  ctx.r1.u32 -= 0x40; m4.pc = 0x2014;
  M4BeforeCall(m4, ctx); callee_raise(ctx, base); m4.in_call = false;
  Ev("inner_after_call"); ctx.r1.u32 += 0x40;
  M4_RETURN
loc_2030:
  Ev("inner_label"); ctx.r1.u32 += 0x40;
  M4_RETURN
  M4_TRY_END
}
// Outer owner: finally scope (0x9300) and except scope (0x9100 -> 0x3030) around the call to owner_inner.
static void owner_outer(PPCContext& ctx, uint8_t* base) {
  static const M4Scope m4scopes[] = {{0x3010, 0x3020, 0x9100, 0x3030}, {0x3010, 0x3020, 0x9300, 0}};
  auto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* { return Resolve(a, b); };
  M4_FRAME(2)
m4_retry:
  M4_TRY_BEGIN
  uint32_t m4resume = m4.resume; m4.resume = 0; m4.resume_index = m4.count; m4.unwind = false;
  switch (m4resume) { case 0x3030: goto loc_3030; case 0: break; default: M4_FAIL(7); }
  ctx.r1.u32 -= 0x20; ctx.r14.u64 = 0x4141; m4.pc = 0x3014;
  M4BeforeCall(m4, ctx); owner_inner(ctx, base); m4.in_call = false;
  Ev("outer_after_call"); ctx.r1.u32 += 0x20;
  M4_RETURN
loc_3030:
  Ev("outer_label"); CHECK(ctx.r14.u32 == 0x4141); CHECK(ctx.r1.u32 == 0x10000 - 0x20); ctx.r1.u32 += 0x20;
  M4_RETURN
  M4_TRY_END
}

// RtlUnwind target owner: finally scope 0x9200 [0x4010,0x4020) is left; finally 0x9300 [0x4010,0x4050) contains the
// destination 0x4040 and is retained. The unwind value arrives in r3.
static void owner_unwind(PPCContext& ctx, uint8_t* base) {
  static const M4Scope m4scopes[] = {{0x4010, 0x4020, 0x9200, 0}, {0x4010, 0x4050, 0x9300, 0}};
  auto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* { return Resolve(a, b); };
  M4_FRAME(2)
m4_retry:
  M4_TRY_BEGIN
  uint32_t m4resume = m4.resume; m4.resume = 0; m4.resume_index = m4.count; m4.unwind = false;
  switch (m4resume) { case 0x4040: goto loc_4040; case 0: break; default: M4_FAIL(7); }
  ctx.r1.u32 -= 0x60; ctx.r31.u64 = 0x3232; m4.pc = 0x4014;
  g_unwind_frame = m4.establisher; g_unwind_target = 0x4040;
  M4BeforeCall(m4, ctx); callee_unwind(ctx, base); m4.in_call = false;
  Ev("not_reached");
  M4_RETURN
loc_4040:
  EvHex("unwind_label_r3", ctx.r3.u32); CHECK(ctx.r31.u32 == 0x3232); ctx.r1.u32 += 0x60;
  M4_RETURN
  M4_TRY_END
}

// Finally scope only, around a call; used for the normal path and for host exceptions.
static PPCFunc* g_finally_callee = nullptr;
static void owner_finally(PPCContext& ctx, uint8_t* base) {
  static const M4Scope m4scopes[] = {{0x5010, 0x5020, 0x9200, 0}};
  auto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* { return Resolve(a, b); };
  M4_FRAME(1)
m4_retry:
  M4_TRY_BEGIN
  uint32_t m4resume = m4.resume; m4.resume = 0; m4.resume_index = m4.count; m4.unwind = false;
  switch (m4resume) { case 0: break; default: M4_FAIL(7); }
  m4.pc = 0x5014;
  M4BeforeCall(m4, ctx); g_finally_callee(ctx, base); m4.in_call = false;
  Ev("finally_owner_after_call");
  M4_RETURN
  M4_TRY_END
}

// setjmp owner (like sub_82559C48/DA8): setjmp, then a call through owner_finally whose callee longjmps back.
static void owner_setjmp(PPCContext& ctx, uint8_t* base) {
  static const M4Scope m4scopes[] = {{0x6010, 0x6030, 0x9300, 0}};
  auto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* { return Resolve(a, b); };
  M4_FRAME(1)
m4_retry:
  M4_TRY_BEGIN
  uint32_t m4resume = m4.resume; m4.resume = 0; m4.resume_index = m4.count; m4.unwind = false;
  switch (m4resume) { case 0: break; default: M4_FAIL(7); }
  {
    m4.pc = 0x6010;
    int rc = TEST_SETJMP(0x500);
    m4.in_call = false; m4.pc = 0x6010;  // as emitted after ppc_setjmp
    if (!rc) {
      g_finally_callee = callee_longjmp;
      m4.pc = 0x6014; M4BeforeCall(m4, ctx); owner_finally(ctx, base); m4.in_call = false;
      Ev("not_reached");
    }
    EvHex("setjmp_rc", uint32_t(rc));
  }
  M4_RETURN
  M4_TRY_END
}

// ---- harness ----------------------------------------------------------------------------------------------------------
static std::string Run(PPCFunc* fn, PPCContext& ctx, bool expect_host_exception = false) {
  g_trace.clear();
  bool host = false;
  try { fn(ctx, g_mem); } catch (const std::runtime_error&) { host = true; }
  if (host) Ev("host_exception_caught");
  CHECK(host == expect_host_exception);
  CHECK(RegistryEmpty());
  return g_trace;
}

static void Expect(const char* name, const std::string& got, const char* want) {
  ++g_checks;
  std::printf("TRACE %s: %s\n", name, got.c_str());
  if (got != want) { ++g_failures; std::printf("FAIL %s\n  want: %s\n", name, want); }
}

static void Scenarios() {
  PPCContext ctx;
  // S1 thread naming: the filter returns -1, the raise returns, execution continues in the callee.
  g_raise_code = 0x406D1388; g_raise_flags = 0; g_disp_outer = -1; ctx = Fresh();
  Expect("S1_continue", Run(owner_single, ctx), "filter_outer=406D1388 raise_returned after_call ");
  CHECK(ctx.r1.u32 == 0x10000); CHECK(ctx.r31.u32 == 0xDEAD);
  // S2 accept: the filter returns 1; the owner re-enters at its label with its own non-volatiles.
  g_raise_code = 0xC0000017; g_disp_outer = 1; ctx = Fresh();
  Expect("S2_accept", Run(owner_single, ctx), "filter_outer=C0000017 label ");
  CHECK(ctx.r1.u32 == 0x10000);
  // S3 nested: the inner filter continues the search (0), the outer accepts; the inner finally runs, then the label.
  g_disp_inner = 0; g_disp_outer = 1; ctx = Fresh();
  // The outer finally (table index 1) is not nested inside the accepting scope (index 0), so it does not run.
  Expect("S3_nested_outer_accepts", Run(owner_outer, ctx),
         "filter_inner=C0000017 filter_outer=C0000017 finally_inner=1 outer_label ");
  // S4 nested: the inner filter accepts; nothing above it runs.
  g_disp_inner = 1; ctx = Fresh();
  // The inner finally (index 1) is not nested inside the accepting inner scope (index 0).
  Expect("S4_nested_inner_accepts", Run(owner_outer, ctx),
         "filter_inner=C0000017 inner_label outer_after_call ");
  // S5 noncontinuable: the inner filter's -1 cannot continue, so the search goes on to the outer owner.
  g_raise_flags = 1; g_disp_inner = -1; g_disp_outer = 1; ctx = Fresh();
  Expect("S5_noncontinuable", Run(owner_outer, ctx),
         "filter_inner=C0000017 filter_outer=C0000017 finally_inner=1 outer_label ");
  g_raise_flags = 0;
  // S6 continuable -1 in the inner owner: execution continues in the callee; no cleanup.
  g_disp_inner = -1; ctx = Fresh();
  Expect("S6_inner_continue", Run(owner_outer, ctx),
         "filter_inner=C0000017 raise_returned inner_after_call outer_after_call ");
  // S7 RtlUnwind: no filters; the left finally runs, the retained one does not; the value arrives in r3.
  ctx = Fresh();
  Expect("S7_rtlunwind", Run(owner_unwind, ctx), "finally_inner=1 unwind_label_r3=1234 ");
  // S8 normal path: the finally scope is not run by the backend (normal translated cleanup is not duplicated).
  g_finally_callee = +[](PPCContext&, uint8_t*) { Ev("callee"); }; ctx = Fresh();
  Expect("S8_normal", Run(owner_finally, ctx), "callee finally_owner_after_call ");
  // S9 a host C++ exception leaving the owner runs its finally, then reaches the host.
  g_finally_callee = callee_host_throw; ctx = Fresh();
  Expect("S9_host_exception", Run(owner_finally, ctx, true), "finally_inner=1 host_exception_caught ");
  // S10 guest longjmp across an owner: the intervening owner's finally runs (MSVC longjmp unwind order); the setjmp
  // owner resumes with the value; its own scope is not left.
  ctx = Fresh();
  Expect("S10_longjmp", Run(owner_setjmp, ctx), "longjmp finally_inner=1 setjmp_rc=7 ");
  // S11 retry hygiene: an accepted owner runs again cleanly afterwards.
  g_raise_code = 0xC0000017; g_disp_outer = 1; ctx = Fresh();
  Run(owner_single, ctx);
  g_raise_code = 0x406D1388; g_disp_outer = -1; ctx = Fresh();
  Expect("S11_after_accept", Run(owner_single, ctx), "filter_outer=406D1388 raise_returned after_call ");
}

// ---- fail-fast children (run by the runner; each must terminate abnormally with a FAIL-FAST record) ------------
static int Child(const char* name) {
  PPCContext ctx = Fresh();
  std::string n = name;
  if (n == "unhandled") {  // no owner accepts: Windows crashes (unhandled exception), portable fails fast
    g_raise_code = 0xC0000017; g_disp_outer = 0;
    owner_single(ctx, g_mem);
  } else if (n == "unwind_unknown") {  // RtlUnwind to an establisher with no live owner
    M4UnwindRequest req{0x12345678, 0x4040, 0}; M4RequestUnwind(req);
  } else if (n == "bad_resume") {  // an invalid resume label in the switch
    static const M4Scope m4scopes[] = {{0, 0, 0, 0}};
    auto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* { return Resolve(a, b); };
    uint8_t* base = g_mem; (void)base; (void)m4resolve;
    M4_FRAME(1)
    m4.resume = 0x777;
    switch (m4.resume) { case 0: break; default: M4_FAIL(7); }
  }
#if !(defined(_WIN32) && !defined(R3HD_M4_PORTABLE))
  else if (n == "boundary_accept") {
    g_raise_code = 0xC0000017; g_disp_outer = 1;
    // owner_single accepts, but its callee is entered through a host boundary
    static PPCFunc* through = +[](PPCContext& c, uint8_t* b) {
      M4HostBoundary boundary("FunctionDispatcher::Execute(test)", 0x82000000);
      callee_raise(c, b);
    };
    struct Local {
      static void owner(PPCContext& ctx, uint8_t* base) {
        static const M4Scope m4scopes[] = {{0x1010, 0x1020, 0x9100, 0x1030}};
        auto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* { return Resolve(a, b); };
        M4_FRAME(1)
      m4_retry:
        M4_TRY_BEGIN
        uint32_t m4resume = m4.resume; m4.resume = 0; m4.resume_index = m4.count; m4.unwind = false;
        switch (m4resume) { case 0x1030: goto loc_1030; case 0: break; default: M4_FAIL(7); }
        m4.pc = 0x1014; M4BeforeCall(m4, ctx); through(ctx, base); m4.in_call = false;
        M4_RETURN
      loc_1030:
        Ev("label_must_not_run");
        M4_RETURN
        M4_TRY_END
      }
    };
    Local::owner(ctx, g_mem);
  } else if (n == "funclet_raise") {  // a raise inside a running filter funclet
    struct Local {
      static PPCFunc* Res(uint32_t, uint8_t*) { return +[](PPCContext&, uint8_t*) { M4GuestRecord r{}; r.code = 1; M4Raise(r); }; }
      static void owner(PPCContext& ctx, uint8_t* base) {
        static const M4Scope m4scopes[] = {{0x1010, 0x1020, 0x9100, 0x1030}};
        auto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* { return Res(a, b); };
        M4_FRAME(1)
      m4_retry:
        M4_TRY_BEGIN
        uint32_t m4resume = m4.resume; m4.resume = 0; m4.resume_index = m4.count; m4.unwind = false;
        switch (m4resume) { case 0x1030: goto loc_1030; case 0: break; default: M4_FAIL(7); }
        m4.pc = 0x1014; M4BeforeCall(m4, ctx); callee_raise(ctx, base); m4.in_call = false;
        M4_RETURN
      loc_1030:
        M4_RETURN
        M4_TRY_END
      }
    };
    Local::owner(ctx, g_mem);
  }
#endif
  else {
    std::printf("unknown child %s\n", name);
    return 3;
  }
  std::printf("CHILD %s returned (no fail-fast)\n", name);
  return 0;
}

#if defined(__linux__)
// ---- D3: POSIX cancellation through portable owner frames ----------------------------------------------------------
// The SDK makes every thread PTHREAD_CANCEL_ASYNCHRONOUS (threading_posix.cpp) and terminates guest threads with
// pthread_cancel. A forced unwind must pass through owners without running guest __finally (Windows thread
// termination runs none), without being swallowed, and without std::terminate.
static std::atomic<int> g_stage{0};
static volatile unsigned long g_sink = 0;
static void spin_callee(PPCContext&, uint8_t*) { g_stage = 1; for (;;) g_sink = g_sink + 1; }
static void sleep_callee(PPCContext&, uint8_t*) { g_stage = 1; for (;;) pause(); }  // cancellation point
static void finally_blocking(PPCContext& ctx, uint8_t*) { EvHex("finally_inner", ctx.r3.u32); g_stage = 2; for (;;) pause(); }
static PPCFunc* ResolveBlocking(uint32_t a, uint8_t* b) { return a == 0x9200 ? finally_blocking : Resolve(a, b); }
static void owner_blocking_finally(PPCContext& ctx, uint8_t* base) {  // finally funclet blocks during a transfer
  static const M4Scope m4scopes[] = {{0x5010, 0x5020, 0x9200, 0}};
  auto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* { return ResolveBlocking(a, b); };
  M4_FRAME(1)
m4_retry:
  M4_TRY_BEGIN
  uint32_t m4resume = m4.resume; m4.resume = 0; m4.resume_index = m4.count; m4.unwind = false;
  switch (m4resume) { case 0: break; default: M4_FAIL(7); }
  m4.pc = 0x5014; M4BeforeCall(m4, ctx); callee_raise(ctx, base); m4.in_call = false;
  M4_RETURN
  M4_TRY_END
}
static void owner_accepting_blocking(PPCContext& ctx, uint8_t* base) {
  static const M4Scope m4scopes[] = {{0x3010, 0x3020, 0x9100, 0x3030}};
  auto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* { return Resolve(a, b); };
  M4_FRAME(1)
m4_retry:
  M4_TRY_BEGIN
  uint32_t m4resume = m4.resume; m4.resume = 0; m4.resume_index = m4.count; m4.unwind = false;
  switch (m4resume) { case 0x3030: goto loc_3030; case 0: break; default: M4_FAIL(7); }
  m4.pc = 0x3014; M4BeforeCall(m4, ctx); owner_blocking_finally(ctx, base); m4.in_call = false;
  M4_RETURN
loc_3030:
  Ev("label_must_not_run");
  M4_RETURN
  M4_TRY_END
}

struct CancelCase { const char* name; int type; PPCFunc* owner; PPCFunc* callee; int stage; };
static void* CancelThread(void* p) {
  auto* c = static_cast<CancelCase*>(p);
  pthread_setcanceltype(c->type, nullptr);
  PPCContext ctx = Fresh();
  g_finally_callee = c->callee;
  try {
    c->owner(ctx, g_mem);
  } catch (const M4Transfer&) {
    Ev("token_escaped");
  }
  Ev("thread_returned");
  return nullptr;
}
static void CancelScenarios() {
  CancelCase cases[] = {
      {"C1_async_spin", PTHREAD_CANCEL_ASYNCHRONOUS, owner_finally, spin_callee, 1},
      {"C2_deferred_point", PTHREAD_CANCEL_DEFERRED, owner_finally, sleep_callee, 1},
      {"C3_async_point", PTHREAD_CANCEL_ASYNCHRONOUS, owner_finally, sleep_callee, 1},
      {"C4_during_transfer_finally", PTHREAD_CANCEL_ASYNCHRONOUS, owner_accepting_blocking, nullptr, 2},
  };
  for (auto& c : cases) {
    g_trace.clear(); g_stage = 0;
    g_raise_code = 0xC0000017; g_disp_outer = 1;
    pthread_t t;
    pthread_create(&t, nullptr, CancelThread, &c);
    while (g_stage < c.stage) usleep(1000);
    usleep(20000);
    pthread_cancel(t);
    void* rv = nullptr;
    pthread_join(t, &rv);
    g_trace += rv == PTHREAD_CANCELED ? "canceled " : "not_canceled ";
    // C4: the finally funclet itself was running (because of the transfer) when the cancel arrived; nothing else ran.
    Expect(c.name, g_trace, c.stage == 2 ? "filter_outer=C0000017 finally_inner=1 canceled " : "canceled ");
  }
  CHECK(RegistryEmpty());  // the main thread's registry is untouched by the cancelled threads
}
#endif

int main(int argc, char** argv) {
  if (argc > 2 && std::strcmp(argv[1], "--child") == 0) return Child(argv[2]);
  Scenarios();
#if defined(__linux__)
  CancelScenarios();
#endif
  std::printf("M4_PORTABLE_TEST %s backend=%s checks=%d failures=%d\n", g_failures ? "FAIL" : "PASS", BACKEND,
              g_checks, g_failures);
  return g_failures ? 1 : 0;
}
