// Additional synthetic coverage for the production M4 helper. Included by the
// private test scaffold prepared from M3; no target instructions or assets.
static uint32_t g_cleanup_r31;
static void filter_rounding(PPCContext& ctx, uint8_t*) {
  ctx.fpscr.storeFromGuest(1); ctx.r3.s64 = -1;
}
static void cleanup_owner(PPCContext& ctx, uint8_t*) {
  EV(kFinA); g_cleanup_r31 = ctx.r31.u32;
}
static PPCFunc* ExtraResolve(uint32_t a, uint8_t* b) {
  if (a == 0x9300) return cleanup_owner;
  if (a == 0x9400) return filter_rounding;
  return Resolve(a, b);
}
static void unwind_callee(PPCContext& ctx, uint8_t*) {
  uint32_t frame = ctx.r4.u32, target = ctx.r5.u32;
  ctx.r31.u64 = 0xDEAD; ctx.r1.u32 -= 0x80;
  M4UnwindRequest req{frame, target, 0x1234};
  M4RequestUnwind(req);
}
static void unwind_owner(PPCContext& ctx, uint8_t* base) {
  static const M4Scope table[] = {
    {0xA010, 0xA020, FLT_CONST, 0xA030}, {0xA010, 0xA020, 0x9300, 0}};
  M4Frame eh; M4Init(eh, table, 2, ctx);
retry:
  __try { __try {
    uint32_t resume = eh.resume; eh.resume = 0; eh.resume_index = eh.count; eh.unwind = false;
    if (resume == 0xA040) goto target;
    if (resume) std::abort();
    M4_PROLOGUE(); ctx.r4.u64 = eh.establisher; ctx.r5.u64 = 0xA040;
    eh.pc = 0xA014; M4BeforeCall(eh, ctx); unwind_callee(ctx, base); eh.in_call = false;
    CHECK(false);
target:
    EV(kBodyB); CHECK(ctx.r31.u32 == eh.establisher - 96);
    CHECK(ctx.r1.u32 == eh.establisher - 96); CHECK(ctx.r3.u32 == 0x1234);
    M4_EPILOGUE(); eh.normal = true; return;
  } __finally { if (!eh.normal) M4SehUnwind(eh, ctx, base, ExtraResolve); }
  } __except (M4SehFilter(GetExceptionInformation(), eh, ctx, base, ExtraResolve)) {
    M4RestoreOwner(eh, ctx); if (eh.unwind) ctx.r3.u64 = eh.return_value; goto retry;
  }
}
static void host_fault_owner(PPCContext& ctx, uint8_t* base) {
  static const M4Scope table[] = {{0xA010, 0xA020, FLT_CONST, 0xA030}};
  M4Frame eh; M4Init(eh, table, 1, ctx); eh.pc = 0xA014;
  __try { volatile uint32_t* volatile host_null = nullptr; *host_null = 1; }
  __except (M4SehFilter(GetExceptionInformation(), eh, ctx, base, ExtraResolve)) { EV(kBodyB); }
}
static void mixed_nonlocal_owner(PPCContext& ctx, uint8_t* base) {
  static const M4Scope table[] = {{0xB010, 0xB030, FLT_CONST, 0xB040}};
  M4Frame eh; M4Init(eh, table, 1, ctx);
  __try { __try {
    M4_PROLOGUE(); PPCContext env = ctx;
    int rc = ppc_setjmp(0x500);
    if (rc) ctx = env;
    // Actual emitter resets its invocation marker on both setjmp returns.
    eh.in_call = false; eh.pc = 0xB010;
    if (!rc) {
      ctx.r3.u64 = kModeLongjmp; M4_CALL(0xB014, sub_A000); CHECK(false);
    }
    CHECK(rc == 7); CHECK(ctx.r1.u32 == 0x10000 - 96);
    CHECK(ctx.r31.u32 == 0x10000 - 96); CHECK(!eh.in_call);
    M4_EPILOGUE(); eh.normal = true; return;
  } __finally { if (!eh.normal) M4SehUnwind(eh, ctx, base, Resolve); }
  } __except (M4SehFilter(GetExceptionInformation(), eh, ctx, base, Resolve)) { CHECK(false); }
}
static void ExtraTests() {
  Test("M4 filter side call restores guest FPSCR bits in host CSR", [] {
    auto ctx = NewContext(); ctx.fpscr.InitHost(); uint32_t prior = ctx.fpscr.getcsr();
    ctx.fpscr.storeFromGuest(0); uint32_t expected = ctx.fpscr.getcsr() & PPCFPSCRRegister::GuestMask;
    M4Scope s{0xA000, 0xA100, 0x9400, 0xA110}; M4Frame f; M4Init(f, &s, 1, ctx); f.pc = 0xA010;
    M4GuestRecord rec{}; rec.code = kThreadName;
    EXCEPTION_RECORD native{}; native.ExceptionCode = kM4GuestRaise;
    native.NumberParameters = 1; native.ExceptionInformation[0] = uintptr_t(&rec);
    EXCEPTION_POINTERS ep{&native, nullptr};
    CHECK(M4SehFilter(&ep, f, ctx, g_mem, ExtraResolve) == EXCEPTION_CONTINUE_EXECUTION);
    CHECK((ctx.fpscr.getcsr() & PPCFPSCRRegister::GuestMask) == expected);
    ctx.fpscr.setcsr(prior);
  });
  Test("M4 setjmp owner with except scope, child cleanup, full restore", [] {
    auto ctx = NewContext(); CHECK(Run(mixed_nonlocal_owner, ctx) == 0);
    CHECK(Seq({kFinA})); CHECK(ctx.r1.u32 == 0x10000);
  });
  Test("M4 first-pass scratch stays below live callee stack", [] {
    auto ctx = NewContext(); M4Scope s{0xA000, 0xA100, FLT_THREAD, 0xA110};
    M4Frame f; M4Init(f, &s, 1, ctx); ctx.r1.u32 = 0xFFA0; M4BeforeCall(f, ctx);
    ctx.r1.u32 = 0xF000; ctx.r31.u32 = 0xDEAD;
    M4St32(g_mem, 0xFC20, 0xABCDEF01);
    f.pc = 0xA010; M4GuestRecord rec{}; rec.code = kThreadName;
    EXCEPTION_RECORD native{}; native.ExceptionCode = kM4GuestRaise;
    native.NumberParameters = 1; native.ExceptionInformation[0] = uintptr_t(&rec);
    EXCEPTION_POINTERS ep{&native, nullptr};
    CHECK(M4SehFilter(&ep, f, ctx, g_mem, Resolve) == EXCEPTION_CONTINUE_EXECUTION);
    CHECK(M4Ld32(g_mem, 0xFC20) == 0xABCDEF01); CHECK(ctx.r1.u32 == 0xF000);
    CHECK(ctx.r31.u32 == 0xDEAD); CHECK(f.in_call);
  });
  Test("M4 explicit unwind restores owner, runs cleanup, skips filters", [] {
    auto ctx = NewContext(); CHECK(Run(unwind_owner, ctx) == 0);
    CHECK(Seq({kFinA, kBodyB})); CHECK(g_cleanup_r31 == 0x10000 - 96);
    CHECK(ctx.r1.u32 == 0x10000);
  });
  Test("M4 native null fault propagates without guest filter/body", [] {
    auto ctx = NewContext(); CHECK(Run(host_fault_owner, ctx) == kAv); CHECK(Seq({}));
  });
  Test("M4 unwind retains enclosing scope containing destination", [] {
    auto ctx = NewContext(); M4Scope s{0xA000, 0xA100, FIN_A, 0};
    M4Frame f; M4Init(f, &s, 1, ctx); f.pc = 0xA010; f.resume = 0xA050; f.unwind = true;
    Reset(); M4SehUnwind(f, ctx, g_mem, Resolve); CHECK(Seq({}));
    f.resume = 0xA100; M4SehUnwind(f, ctx, g_mem, Resolve); CHECK(Seq({kFinA}));
  });
  Test("M4 rejects continuation of a noncontinuable guest record", [] {
    auto ctx = NewContext(); M4Scope s{0xA000, 0xA100, FLT_THREAD, 0xA110};
    M4Frame f; M4Init(f, &s, 1, ctx); f.pc = 0xA010;
    M4GuestRecord rec{}; rec.code = kThreadName; rec.flags = EXCEPTION_NONCONTINUABLE;
    EXCEPTION_RECORD native{}; native.ExceptionCode = kM4GuestRaise;
    native.NumberParameters = 1; native.ExceptionInformation[0] = uintptr_t(&rec);
    EXCEPTION_POINTERS ep{&native, nullptr};
    CHECK(M4SehFilter(&ep, f, ctx, g_mem, Resolve) == EXCEPTION_CONTINUE_SEARCH);
    CHECK(f.resume == 0); CHECK(ctx.r1.u32 == 0x10000);
  });
}
