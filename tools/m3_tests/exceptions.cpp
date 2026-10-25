// Milestone 3 synthetic exception regressions. No game bytes or translated game
// functions: every "guest function" below is hand-written in the generated-code
// idiom and every table is synthetic. The *shapes* are the ones measured in the
// Rayman 3 HD executable by tools/m3_eh_map.py (addresses name the real function
// whose structure a test mirrors; see RE_NOTES.md, Milestone 3).
#include "r3hd_pch.h"
#include "m3_guest_seh.h"
#include <cstdio>
#include <initializer_list>

thread_local const char* m2_current_function = nullptr;
thread_local PPCContext* m2_current_context = nullptr;
void M2Enter(const char*, PPCContext&) {}

// ---- harness ---------------------------------------------------------------
static uint8_t g_mem[0x20000];
static int g_events[128], g_event_count, g_failures, g_checks;
static uint32_t g_body_lookups;
enum Event { kFinA = 1, kFinB, kFilter, kBodyB, kBodyInner, kBodyMiddle, kBodyD, kBodyE, kRaiseReturned,
             kDtorX, kDtorY, kCatchInner, kCatchOuter, kAfterTry };
static void EV(int e) { if (g_event_count < 128) g_events[g_event_count++] = e; }
static void Reset() { g_event_count = 0; }
static bool Seq(std::initializer_list<int> want) {
  if (int(want.size()) != g_event_count) return false;
  int i = 0;
  for (int w : want) if (g_events[i++] != w) return false;
  return true;
}
#define CHECK(cond) do { ++g_checks; if (!(cond)) { ++g_failures; std::printf("    FAIL line %d: %s\n", __LINE__, #cond); } } while (0)

enum : uint32_t { kNoMem = 0xC0000017, kAv = 0xC0000005, kThreadName = 0x406D1388,
                  kModeHostAv = 0xAAAAAAAA, kModeLongjmp = 0xBBBBBBBB };
enum : uint32_t { FLT_CONST = 0x9000, FLT_NOMEM = 0x9010, FLT_AV = 0x9020, FLT_THREAD = 0x9030, FLT_FRAME = 0x9040,
                  FIN_A = 0x9100, FIN_B = 0x9110, DTOR_X = 0x9200, DTOR_Y = 0x9210,
                  CATCH_INNER = 0x10100, CATCH_OUTER = 0x11100 };
static volatile uint32_t* volatile g_null = nullptr;
static uint32_t g_fin_a_r12, g_fin_b_r12, g_fin_a_r3;
static bool g_inner_catch_rethrows;

// ---- synthetic funclets (each has its own .pdata entry in the target) -------
static uint32_t Code(PPCContext& ctx, uint8_t* base) { return M3Ld32(base, M3Ld32(base, ctx.r3.u32)); }
static void flt_const(PPCContext& ctx, uint8_t*) { EV(kFilter); ctx.r3.s64 = 1; }                         // li r3,1
static void flt_nomem(PPCContext& ctx, uint8_t* base) { EV(kFilter); ctx.r3.s64 = Code(ctx, base) == kNoMem; }  // 820E5C00
static void flt_av(PPCContext& ctx, uint8_t* base) { EV(kFilter); ctx.r3.s64 = Code(ctx, base) == kAv; }        // 824B2FE8
static void flt_thread(PPCContext& ctx, uint8_t* base) { EV(kFilter); ctx.r3.s64 = Code(ctx, base) == kThreadName ? -1 : 1; }  // 82821684
static void flt_frame(PPCContext& ctx, uint8_t* base) {                                                    // 826C2F18
  EV(kFilter);
  uint32_t r31 = ctx.r12.u32 - 0x60;
  ctx.r3.s64 = base[r31 + 0x7F] != 0;
}
static void fin_a(PPCContext& ctx, uint8_t*) { EV(kFinA); g_fin_a_r12 = ctx.r12.u32; g_fin_a_r3 = ctx.r3.u32; }
static void fin_b(PPCContext& ctx, uint8_t*) { EV(kFinB); g_fin_b_r12 = ctx.r12.u32; }
static void dtor_x(PPCContext&, uint8_t*) { EV(kDtorX); }
static void dtor_y(PPCContext&, uint8_t*) { EV(kDtorY); }
static void RaiseCode(uint32_t code) { M3GuestRecord rec{}; rec.code = code; M3Raise(rec); }
static void catch_inner(PPCContext& ctx, uint8_t*) {
  EV(kCatchInner);
  if (g_inner_catch_rethrows) RaiseCode(kCxxCode);  // catch (...) { throw; }
  ctx.r3.u64 = 0x10050;                              // continuation address
}
static void catch_outer(PPCContext& ctx, uint8_t*) { EV(kCatchOuter); ctx.r3.u64 = 0x11050; }

static PPCFunc* Resolve(uint32_t address) {
  switch (address) {
    case FLT_CONST: return flt_const; case FLT_NOMEM: return flt_nomem; case FLT_AV: return flt_av;
    case FLT_THREAD: return flt_thread; case FLT_FRAME: return flt_frame;
    case FIN_A: return fin_a; case FIN_B: return fin_b; case DTOR_X: return dtor_x; case DTOR_Y: return dtor_y;
    case CATCH_INNER: return catch_inner; case CATCH_OUTER: return catch_outer;
  }
  ++g_body_lookups;  // an inline __except body must never be looked up as a function
  std::abort();
}

#define M3_CALL(addr, fn) do { eh.pc = (addr); M3BeforeCall(eh, ctx); fn(ctx, base); eh.in_call = false; } while (0)
#define M3_RETURN do { eh.normal = true; return; } while (0)
// mflr/stw lr ; std r31,-16(r1) ; addi r31,r1,-96 ; stwu r1,-96(r1)  /  addi r1,r31,96 ; ld r31,-16(r1)
#define M3_PROLOGUE() do { M3St32(base, ctx.r1.u32 - 8, uint32_t(ctx.lr)); M3St32(base, ctx.r1.u32 - 12, ctx.r31.u32); \
                           ctx.r31.s64 = ctx.r1.s64 - 96; M3St32(base, ctx.r1.u32 - 96, ctx.r1.u32); ctx.r1.u32 -= 96; } while (0)
#define M3_EPILOGUE() do { ctx.r1.s64 = ctx.r31.s64 + 96; ctx.r31.u64 = M3Ld32(base, ctx.r1.u32 - 12); } while (0)
#define M3_SEH_OPEN(table, n) M3Frame eh; M3Init(eh, table, n, ctx); \
  m3_retry: __try { __try { uint32_t m3_resume = eh.resume; eh.resume = 0; eh.resume_index = eh.count; switch (m3_resume)
#define M3_SEH_CLOSE() } __finally { if (!eh.normal) M3SehUnwind(eh, ctx, base, Resolve); } } \
  __except (M3SehFilter(GetExceptionInformation(), eh, ctx, base, Resolve)) { M3RestoreOwner(eh, ctx); goto m3_retry; }

// Callee without unwind metadata of its own: clobbers the registers a real callee
// would save in its prologue, then faults/raises/jumps.
static void sub_work(PPCContext& ctx, uint8_t* base) {
  uint32_t mode = ctx.r3.u32;
  PPCRegister s31 = ctx.r31, s30 = ctx.r30, s14 = ctx.r14, sf = ctx.f31, s1 = ctx.r1;
  ctx.r1.u32 -= 0x80; ctx.r31.u64 = 0xDEAD0031; ctx.r30.u64 = 0xDEAD0030; ctx.r14.u64 = 0xDEAD0014; ctx.f31.f64 = -1.0;
  if (mode == kModeHostAv) *g_null = 1;
  else if (mode == kModeLongjmp) ppc_longjmp(0x500, 7);
  else if (mode) { RaiseCode(mode); EV(kRaiseReturned); }
  ctx.r31 = s31; ctx.r30 = s30; ctx.r14 = s14; ctx.f31 = sf; ctx.r1 = s1;
}

// Shape of 826D5BB0: one __finally scope, funclet also called inline on the normal path.
static void sub_A000(PPCContext& ctx, uint8_t* base) {
  static const M3Scope table[] = {{0xA010, 0xA014, FIN_A, 0}};
  M3_SEH_OPEN(table, 1) { default: break; }
    eh.pc = 0xA000; M3_PROLOGUE();
    M3_CALL(0xA010, sub_work);
    eh.pc = 0xA014;
    ctx.r12.s64 = ctx.r31.s64 + 96; ctx.r3.u64 = 0; fin_a(ctx, base);
    M3_EPILOGUE(); M3_RETURN;
  M3_SEH_CLOSE()
}

// Shape of 820E25D8: __except (depth 1) nested in a function-wide __finally.
static M3Scope g_table_b[] = {{0xB020, 0xB040, FLT_CONST, 0xB050}, {0xB010, 0xB060, FIN_B, 0}};
static void sub_B000(PPCContext& ctx, uint8_t* base) {
  M3_SEH_OPEN(g_table_b, 2) { case 0xB050: goto loc_B050; default: break; }
    eh.pc = 0xB000; M3_PROLOGUE();
    ctx.r30.u64 = 0x30303030; ctx.r14.u64 = 0x14141414; ctx.f31.f64 = 31.5;
    eh.pc = 0xB010;
    eh.pc = 0xB020;
    if (ctx.r4.u32 == 1) *g_null = 1;          // fault in the owner itself
    if (ctx.r4.u32 == 2) M3_CALL(0xB024, sub_work);  // direct callee
    else M3_CALL(0xB028, sub_A000);            // through a __finally-only frame
    eh.pc = 0xB040; ctx.r3.u64 = 0x1; goto loc_B058;
  loc_B050:                                    // inline __except body: a label, not a function
    eh.pc = 0xB050; EV(kBodyB); ctx.r3.u64 = 0xE;
  loc_B058:
    eh.pc = 0xB058;
    ctx.r29.u64 = (ctx.r30.u32 == 0x30303030 && ctx.r14.u32 == 0x14141414 && ctx.f31.f64 == 31.5 &&
                   ctx.r31.u32 + 96 == eh.establisher && ctx.r1.u32 == ctx.r31.u32);
    ctx.r28 = ctx.r3; ctx.r12.s64 = ctx.r31.s64 + 96; fin_b(ctx, base); ctx.r3 = ctx.r28;
    M3_EPILOGUE(); M3_RETURN;
  M3_SEH_CLOSE()
}

// Shape of 820E61F8: __except (depth 2) in __except (depth 1) in __finally (depth 0).
static void sub_C000(PPCContext& ctx, uint8_t* base) {
  static const M3Scope table[] = {{0xC030, 0xC040, FLT_CONST, 0xC050}, {0xC020, 0xC070, FLT_NOMEM, 0xC080},
                                  {0xC010, 0xC090, FIN_A, 0}};
  M3_SEH_OPEN(table, 3) { case 0xC050: goto loc_C050; case 0xC080: goto loc_C080; default: break; }
    eh.pc = 0xC000; M3_PROLOGUE();
    ctx.r26 = ctx.r3; ctx.r27 = ctx.r4; ctx.r28 = ctx.r5; ctx.r29.u64 = 0;
    eh.pc = 0xC010;
    ctx.r3 = ctx.r26; M3_CALL(0xC020, sub_work);
    ctx.r3 = ctx.r27; M3_CALL(0xC030, sub_work);
    eh.pc = 0xC040; goto loc_C058;
  loc_C050:
    eh.pc = 0xC050; EV(kBodyInner); ctx.r29.u64 |= 1;
  loc_C058:
    ctx.r3 = ctx.r28; M3_CALL(0xC058, sub_work);
    eh.pc = 0xC070; goto loc_C088;
  loc_C080:
    eh.pc = 0xC080; EV(kBodyMiddle); ctx.r29.u64 |= 2;
  loc_C088:
    eh.pc = 0xC088; ctx.r12.s64 = ctx.r31.s64 + 96; ctx.r3.u64 = 0; fin_a(ctx, base);
    ctx.r3 = ctx.r29; M3_EPILOGUE(); M3_RETURN;
  M3_SEH_CLOSE()
}

// Shape of 82821618 (RADCODE thread naming): filter returns CONTINUE_EXECUTION.
static void sub_D000(PPCContext& ctx, uint8_t* base) {
  static const M3Scope table[] = {{0xD010, 0xD020, FLT_THREAD, 0xD030}};
  M3_SEH_OPEN(table, 1) { case 0xD030: goto loc_D030; default: break; }
    eh.pc = 0xD000; M3_PROLOGUE();
    M3_CALL(0xD010, sub_work);
    eh.pc = 0xD020; ctx.r3.u64 = 0xC0; goto loc_D038;
  loc_D030:
    eh.pc = 0xD030; EV(kBodyD); ctx.r3.u64 = 0xB0;
  loc_D038:
    eh.pc = 0xD038; M3_EPILOGUE(); M3_RETURN;
  M3_SEH_CLOSE()
}

// Shape of 826C2E90: filter funclet reads the owner's frame through r12.
static void sub_E000(PPCContext& ctx, uint8_t* base) {
  static const M3Scope table[] = {{0xE010, 0xE020, FLT_FRAME, 0xE030}};
  M3_SEH_OPEN(table, 1) { case 0xE030: goto loc_E030; default: break; }
    eh.pc = 0xE000; M3_PROLOGUE();
    base[ctx.r31.u32 + 0x7F] = uint8_t(ctx.r4.u32);
    M3_CALL(0xE010, sub_work);
    eh.pc = 0xE020; ctx.r3.u64 = 0x1; goto loc_E038;
  loc_E030:
    eh.pc = 0xE030; EV(kBodyE); ctx.r3.u64 = 0xE;
  loc_E038:
    eh.pc = 0xE038; M3_EPILOGUE(); M3_RETURN;
  M3_SEH_CLOSE()
}

// Existing SDK setjmp/longjmp lowering, with a __finally-only frame in between.
static void sub_F000(PPCContext& ctx, uint8_t* base) {
  PPCContext env{}; PPCRegister temp{};
  ctx.r31.u64 = 0x31313131; ctx.r1.u32 -= 96;
  ctx.r3.u64 = 0x500;
  env = ctx;
  temp.s64 = ppc_setjmp(ctx.r3.u32);
  if (temp.s64 != 0) ctx = env;
  ctx.r3 = temp;
  if (ctx.r3.s32 == 0) { ctx.r3.u64 = kModeLongjmp; sub_A000(ctx, base); ctx.r3.u64 = 0xBAD; }
  ctx.r1.u32 += 96;
}

// C++ EH shape (FuncInfo 19930522; all catch handlers in the target are catch(...)).
// states: 0 = X alive, 1 = inside try, 2 = Y alive inside try, 3 = catch block running.
static const M3CxxIp kInnerIp[] = {{0x10000, -1}, {0x10010, 0}, {0x10020, 1}, {0x10030, 2}, {0x10040, 1},
                                   {0x10050, 0}, {0x10100, 3}};
static const M3CxxUnwindEntry kInnerUnwind[] = {{-1, DTOR_X}, {0, 0}, {1, DTOR_Y}, {0, 0}};
static const M3CxxTry kInnerTry[] = {{1, 2, 3, CATCH_INNER}};
static const M3CxxInfo kInner = {kInnerIp, 7, kInnerUnwind, 4, kInnerTry, 1};
static void sub_10000(PPCContext& ctx, uint8_t* base) {
  M3Frame eh; M3Init(eh, nullptr, 0, ctx);
m3_retry:
  __try { __try {
    uint32_t m3_resume = eh.resume; eh.resume = 0;
    switch (m3_resume) { case CATCH_INNER: goto run_catch; default: break; }
    eh.pc = 0x10000; M3_PROLOGUE(); ctx.r30 = ctx.r3;
    eh.pc = 0x10010; eh.pc = 0x10020;
    ctx.r3 = ctx.r30; M3_CALL(0x10030, sub_work);
    eh.pc = 0x10040; goto loc_10050;
  run_catch:
    M3_CALL(0x10100, catch_inner);
    switch (ctx.r3.u32) { case 0x10050: goto loc_10050; default: std::abort(); }
  loc_10050:
    eh.pc = 0x10050; EV(kAfterTry); ctx.r3.u64 = ctx.r31.u32 + 96 == eh.establisher ? 0x600D : 0xBAD;
    eh.pc = 0x10000; M3_EPILOGUE(); M3_RETURN;
  } __finally { if (!eh.normal) M3CxxUnwind(eh, kInner, ctx, base, Resolve); } }
  __except (M3CxxFilter(GetExceptionInformation(), eh, kInner)) { M3RestoreOwner(eh, ctx); goto m3_retry; }
}
static const M3CxxIp kOuterIp[] = {{0x11000, -1}, {0x11010, 0}, {0x11040, -1}, {0x11100, 1}};
static const M3CxxUnwindEntry kOuterUnwind[] = {{-1, 0}, {-1, 0}};
static const M3CxxTry kOuterTry[] = {{0, 0, 1, CATCH_OUTER}};
static const M3CxxInfo kOuter = {kOuterIp, 4, kOuterUnwind, 2, kOuterTry, 1};
static void sub_11000(PPCContext& ctx, uint8_t* base) {
  M3Frame eh; M3Init(eh, nullptr, 0, ctx);
m3_retry:
  __try { __try {
    uint32_t m3_resume = eh.resume; eh.resume = 0;
    switch (m3_resume) { case CATCH_OUTER: goto run_catch; default: break; }
    eh.pc = 0x11000; M3_PROLOGUE();
    M3_CALL(0x11010, sub_10000);
    eh.pc = 0x11040; goto loc_11050;
  run_catch:
    M3_CALL(0x11100, catch_outer);
    switch (ctx.r3.u32) { case 0x11050: ctx.r3.u64 = 0x77; goto loc_11050; default: std::abort(); }
  loc_11050:
    eh.pc = 0x11040; M3_EPILOGUE(); M3_RETURN;
  } __finally { if (!eh.normal) M3CxxUnwind(eh, kOuter, ctx, base, Resolve); } }
  __except (M3CxxFilter(GetExceptionInformation(), eh, kOuter)) { M3RestoreOwner(eh, ctx); goto m3_retry; }
}

// Characterization of what the pinned SDK emits today for an SEH function
// (function_graph.cpp: whole-function SEH_TRY, catch-all, finally calls, rethrow).
static void sub_P000(PPCContext& ctx, uint8_t* base) {
  SEH_TRY {
    M3_PROLOGUE();
    sub_work(ctx, base);
    ctx.r12.s64 = ctx.r31.s64 + 96; ctx.r3.u64 = 0; fin_a(ctx, base);
    M3_EPILOGUE();
    return;
  } SEH_CATCH_ALL {
    ctx.r12.s64 = ctx.r31.s64 + 96;  // Establisher frame pointer (as emitted)
    fin_a(ctx, base);                // __finally handler
    SEH_RETHROW;
  } SEH_END
}

// ---- driver ----------------------------------------------------------------
static PPCContext NewContext() {
  PPCContext ctx{};
  ctx.r1.u32 = 0x10000; ctx.r31.u64 = 0x1F1F1F1F; ctx.r30.u64 = 0x1E1E1E1E; ctx.r14.u64 = 0x0E0E0E0E;
  return ctx;
}
static int FilterEscape(EXCEPTION_POINTERS* ep, uint32_t* code) {
  M3GuestRecord rec;
  if (ep->ExceptionRecord->ExceptionCode == kM3GuestRaise) *code = reinterpret_cast<M3GuestRecord*>(ep->ExceptionRecord->ExceptionInformation[0])->code;
  else *code = ep->ExceptionRecord->ExceptionCode;
  (void)rec;
  return EXCEPTION_EXECUTE_HANDLER;
}
// Returns 0 if the guest function returned, otherwise the code that escaped it.
static uint32_t Run(PPCFunc* fn, PPCContext& ctx) {
  uint32_t escaped = 0;
  Reset();
  __try { fn(ctx, g_mem); } __except (FilterEscape(GetExceptionInformation(), &escaped)) {}
  return escaped;
}
static void Test(const char* name, void (*body)()) {
  int before = g_failures;
  body();
  std::printf("%-66s %s\n", name, g_failures == before ? "PASS" : "FAIL");
}

int main() {
  Test("1 normal exit runs __finally once (826D5BB0 shape)", [] {
    auto ctx = NewContext(); ctx.r3.u64 = 0;
    CHECK(Run(sub_A000, ctx) == 0); CHECK(Seq({kFinA})); CHECK(g_fin_a_r12 == 0x10000); CHECK(g_fin_a_r3 == 0);
    CHECK(ctx.r1.u32 == 0x10000);
  });
  Test("2 exception through __finally frame, unhandled: funclet runs, propagates", [] {
    auto ctx = NewContext(); ctx.r3.u64 = kNoMem;
    CHECK(Run(sub_A000, ctx) == kNoMem); CHECK(Seq({kFinA})); CHECK(g_fin_a_r12 == 0x10000); CHECK(g_fin_a_r3 == 1);
  });
  Test("3 filter rejects: body skipped, both __finally run inner-first", [] {
    g_table_b[0].filter = FLT_AV;
    auto ctx = NewContext(); ctx.r3.u64 = kNoMem; ctx.r4.u64 = 0;
    CHECK(Run(sub_B000, ctx) == kNoMem); CHECK(Seq({kFilter, kFinA, kFinB}));
    CHECK(g_fin_b_r12 == 0x10000); CHECK(g_fin_a_r12 == 0x10000 - 96);
  });
  Test("4 filter accepts: filter -> inner __finally -> inline body -> resume", [] {
    g_table_b[0].filter = FLT_NOMEM;
    auto ctx = NewContext(); ctx.r3.u64 = kNoMem; ctx.r4.u64 = 0;
    CHECK(Run(sub_B000, ctx) == 0); CHECK(Seq({kFilter, kFinA, kBodyB, kFinB}));
    CHECK(ctx.r3.u32 == 0xE); CHECK(ctx.r1.u32 == 0x10000);
  });
  Test("5 handler resumes after the guarded range; no exception takes normal path", [] {
    g_table_b[0].filter = FLT_CONST;
    auto ctx = NewContext(); ctx.r3.u64 = 0; ctx.r4.u64 = 0;
    CHECK(Run(sub_B000, ctx) == 0); CHECK(Seq({kFinA, kFinB})); CHECK(ctx.r3.u32 == 0x1); CHECK(ctx.r29.u32 == 1);
  });
  Test("6a nested: innermost constant filter wins (820E61F8 shape)", [] {
    auto ctx = NewContext(); ctx.r3.u64 = 0; ctx.r4.u64 = kAv; ctx.r5.u64 = 0;
    CHECK(Run(sub_C000, ctx) == 0); CHECK(Seq({kFilter, kBodyInner, kFinA})); CHECK(ctx.r3.u32 == 1);
  });
  Test("6b nested: raise outside inner range reaches middle filter only", [] {
    auto ctx = NewContext(); ctx.r3.u64 = kNoMem; ctx.r4.u64 = 0; ctx.r5.u64 = 0;
    CHECK(Run(sub_C000, ctx) == 0); CHECK(Seq({kFilter, kBodyMiddle, kFinA})); CHECK(ctx.r3.u32 == 2);
  });
  Test("6c nested: inner handles, later raise rejected by middle, __finally unwinds", [] {
    auto ctx = NewContext(); ctx.r3.u64 = 0; ctx.r4.u64 = kNoMem; ctx.r5.u64 = kAv;
    CHECK(Run(sub_C000, ctx) == kAv); CHECK(Seq({kFilter, kBodyInner, kFilter, kFinA})); CHECK(g_fin_a_r3 == 1);
  });
  Test("7 filter returns CONTINUE_EXECUTION: raise returns (82821618 shape)", [] {
    auto ctx = NewContext(); ctx.r3.u64 = kThreadName;
    CHECK(Run(sub_D000, ctx) == 0); CHECK(Seq({kFilter, kRaiseReturned})); CHECK(ctx.r3.u32 == 0xC0);
    CHECK(ctx.r31.u32 == 0x1F1F1F1F);
    ctx = NewContext(); ctx.r3.u64 = kNoMem;
    CHECK(Run(sub_D000, ctx) == 0); CHECK(Seq({kFilter, kBodyD})); CHECK(ctx.r3.u32 == 0xB0);
  });
  Test("8 longjmp across a __finally frame: funclet runs, ctx restored", [] {
    auto ctx = NewContext();
    CHECK(Run(sub_F000, ctx) == 0); CHECK(Seq({kFinA})); CHECK(g_fin_a_r3 == 1);
    CHECK(ctx.r3.u32 == 7); CHECK(ctx.r31.u32 == 0x31313131); CHECK(ctx.r1.u32 == 0x10000);
  });
  Test("9 owner non-volatile registers/SP restored at body entry", [] {
    g_table_b[0].filter = FLT_CONST;
    auto ctx = NewContext(); ctx.r3.u64 = kNoMem; ctx.r4.u64 = 2;   // callee clobbers r1/r14/r30/r31/f31
    CHECK(Run(sub_B000, ctx) == 0); CHECK(Seq({kFilter, kBodyB, kFinB})); CHECK(ctx.r29.u32 == 1); CHECK(ctx.r3.u32 == 0xE);
    ctx = NewContext(); ctx.r3.u64 = kNoMem; ctx.r4.u64 = 0;        // through an intermediate frame
    CHECK(Run(sub_B000, ctx) == 0); CHECK(ctx.r29.u32 == 1);
  });
  Test("10 inline body entered as label; never resolved as a function", [] {
    g_table_b[0].filter = FLT_CONST;
    auto ctx = NewContext(); ctx.r3.u64 = kAv; ctx.r4.u64 = 0;
    CHECK(Run(sub_B000, ctx) == 0); CHECK(g_body_lookups == 0); CHECK(Seq({kFilter, kFinA, kBodyB, kFinB}));
  });
  Test("11 host hardware fault (real AV) dispatched to guest filter/body", [] {
    g_table_b[0].filter = FLT_AV;
    auto ctx = NewContext(); ctx.r3.u64 = kModeHostAv; ctx.r4.u64 = 0;   // AV in a callee two frames down
    CHECK(Run(sub_B000, ctx) == 0); CHECK(Seq({kFilter, kFinA, kBodyB, kFinB})); CHECK(ctx.r29.u32 == 1);
    ctx = NewContext(); ctx.r3.u64 = 0; ctx.r4.u64 = 1;                  // AV in the owner itself
    CHECK(Run(sub_B000, ctx) == 0); CHECK(Seq({kFilter, kBodyB, kFinB})); CHECK(ctx.r29.u32 == 1);
  });
  Test("12 filter funclet reads owner frame through establisher (826C2E90 shape)", [] {
    auto ctx = NewContext(); ctx.r3.u64 = kAv; ctx.r4.u64 = 1;
    CHECK(Run(sub_E000, ctx) == 0); CHECK(Seq({kFilter, kBodyE})); CHECK(ctx.r3.u32 == 0xE);
    ctx = NewContext(); ctx.r3.u64 = kAv; ctx.r4.u64 = 0;
    CHECK(Run(sub_E000, ctx) == kAv); CHECK(Seq({kFilter}));
  });
  Test("13 C++ shape: throw -> state unwind -> catch(...) funclet -> continuation", [] {
    g_inner_catch_rethrows = false;
    auto ctx = NewContext(); ctx.r3.u64 = kCxxCode;
    CHECK(Run(sub_11000, ctx) == 0); CHECK(Seq({kDtorY, kCatchInner, kAfterTry})); CHECK(ctx.r3.u32 == 0x600D);
    ctx = NewContext(); ctx.r3.u64 = 0;
    CHECK(Run(sub_11000, ctx) == 0); CHECK(Seq({kAfterTry})); CHECK(ctx.r3.u32 == 0x600D);
  });
  Test("14 C++ shape: catch(...) { throw; } unwinds outer state, outer frame catches", [] {
    g_inner_catch_rethrows = true;
    auto ctx = NewContext(); ctx.r3.u64 = kCxxCode;
    CHECK(Run(sub_11000, ctx) == 0); CHECK(Seq({kDtorY, kCatchInner, kDtorX, kCatchOuter})); CHECK(ctx.r3.u32 == 0x77);
    CHECK(ctx.r1.u32 == 0x10000);
  });
  std::printf("-- characterization of the pinned SDK wrapper (expected current behavior) --\n");
  Test("P1 pinned: hardware fault runs __finally and rethrows", [] {
    auto ctx = NewContext(); ctx.r3.u64 = kModeHostAv;
    CHECK(Run(sub_P000, ctx) == kAv); CHECK(Seq({kFinA}));
  });
  Test("P2 pinned: establisher taken from callee-clobbered r31 (mismatch)", [] {
    auto ctx = NewContext(); ctx.r3.u64 = kModeHostAv;
    Run(sub_P000, ctx);
    CHECK(g_fin_a_r12 == 0xDEAD0031 + 96); CHECK(g_fin_a_r12 != 0x10000);
  });
  Test("P3 pinned: guest-raised code is not caught; __finally skipped (mismatch)", [] {
    auto ctx = NewContext(); ctx.r3.u64 = kNoMem;
    CHECK(Run(sub_P000, ctx) == kNoMem); CHECK(Seq({}));
  });
  std::printf("m3 exception regressions: %d checks, %d failures: %s\n", g_checks, g_failures, g_failures ? "FAIL" : "PASS");
  return g_failures ? 1 : 0;
}
