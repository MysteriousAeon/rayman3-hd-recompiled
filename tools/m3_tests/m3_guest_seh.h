// Milestone 3 prototype: table-driven guest exception dispatch for statically
// recompiled functions. One host function per guest function, PPCContext as
// the only register state, native host SEH as the transport. Nothing here is
// game code: tables in the tests are synthetic.
//
// Model (mirrors what the Xbox 360 kernel does with .pdata + scope tables):
//   pass 1  host __except filter -> M3SehFilter walks the scope table for the
//           guest pc marker, calls guest filter funclets (r3 = exception
//           pointers, r4/r12 = establisher frame).
//   pass 2  host __finally -> M3SehUnwind calls guest __finally funclets of
//           every scope being left (also runs for longjmp unwinds).
//   resume  host __except block restores the owner's non-volatile registers
//           and re-enters the try at the inline __except body *label*; the
//           body is never a callable function.
#pragma once
#include <windows.h>
#include <cstdint>
#include <cstring>
#include <rex/ppc/context.h>

// MSVC scope-table record. target == 0: __finally (filter holds the funclet).
struct M3Scope { uint32_t begin, end, filter, target; };
using M3Resolve = PPCFunc* (*)(uint32_t guest_address);

struct M3GuestRecord { uint32_t code, flags, record_chain, address, nparams, info[15]; };
constexpr DWORD kM3GuestRaise = 0xE0473358;  // host transport code for guest-raised records

struct M3NonVolatile {
  uint8_t regs[PPCContext::kNonVolatileSaveSize];
  PPCRegister r1, r2, r13;
};

struct M3Frame {
  const M3Scope* scopes; uint32_t count;
  uint32_t establisher;        // r1 on entry (what MSVC funclets receive in r12)
  volatile uint32_t pc;        // guest pc marker, updated at labels/scope edges
  volatile bool in_call;       // true while a callee of a guarded range runs
  volatile bool normal;        // set immediately before every ordinary return
  uint32_t resume; uint32_t resume_index;
  M3NonVolatile snap;          // owner state at the last guarded call
};

inline void M3St32(uint8_t* base, uint32_t a, uint32_t v) { v = __builtin_bswap32(v); std::memcpy(base + a, &v, 4); }
inline uint32_t M3Ld32(uint8_t* base, uint32_t a) { uint32_t v; std::memcpy(&v, base + a, 4); return __builtin_bswap32(v); }

inline void M3Init(M3Frame& f, const M3Scope* scopes, uint32_t count, PPCContext& ctx) {
  f.scopes = scopes; f.count = count; f.establisher = ctx.r1.u32;
  f.pc = 0; f.in_call = false; f.normal = false; f.resume = 0; f.resume_index = count;
}
inline void M3BeforeCall(M3Frame& f, PPCContext& ctx) {
  ctx.SaveNonVolatiles(f.snap.regs); f.snap.r1 = ctx.r1; f.snap.r2 = ctx.r2; f.snap.r13 = ctx.r13;
  f.in_call = true;
}
inline void M3RestoreOwner(M3Frame& f, PPCContext& ctx) {
  if (!f.in_call) return;  // fault was in the owner itself: ctx is already the owner's
  ctx.RestoreNonVolatiles(f.snap.regs); ctx.r1 = f.snap.r1; ctx.r2 = f.snap.r2; ctx.r13 = f.snap.r13;
  f.in_call = false;
}

// Guest RtlRaiseException equivalent: a continuable host exception carrying the record.
inline void M3Raise(M3GuestRecord& record) {
  ULONG_PTR arg = reinterpret_cast<ULONG_PTR>(&record);
  RaiseException(kM3GuestRaise, 0, 1, &arg);
}

inline bool M3ToGuestRecord(EXCEPTION_POINTERS* ep, M3GuestRecord& out) {
  auto* r = ep->ExceptionRecord;
  if (r->ExceptionFlags & (EXCEPTION_UNWINDING | EXCEPTION_EXIT_UNWIND)) return false;
  if (r->ExceptionCode == kM3GuestRaise) { out = *reinterpret_cast<M3GuestRecord*>(r->ExceptionInformation[0]); return true; }
  switch (r->ExceptionCode) {  // hardware faults raised by translated code
    case EXCEPTION_ACCESS_VIOLATION: case EXCEPTION_IN_PAGE_ERROR: case EXCEPTION_INT_DIVIDE_BY_ZERO:
    case EXCEPTION_FLT_DIVIDE_BY_ZERO: case EXCEPTION_ILLEGAL_INSTRUCTION: case EXCEPTION_STACK_OVERFLOW:
      out = {}; out.code = r->ExceptionCode; return true;
  }
  return false;  // host-only exception: not a guest construct
}

// Writes EXCEPTION_POINTERS + record below the faulting guest frame, as the kernel does.
inline uint32_t M3PushRecord(PPCContext& ctx, uint8_t* base, const M3GuestRecord& rec) {
  uint32_t sp = (ctx.r1.u32 - 0x400) & ~0xFu;
  uint32_t rec_addr = sp + 0x80;
  M3St32(base, rec_addr + 0, rec.code); M3St32(base, rec_addr + 4, rec.flags);
  M3St32(base, rec_addr + 8, rec.record_chain); M3St32(base, rec_addr + 12, rec.address);
  M3St32(base, rec_addr + 16, rec.nparams);
  for (uint32_t i = 0; i < 15; ++i) M3St32(base, rec_addr + 20 + i * 4, rec.info[i]);
  M3St32(base, sp + 0x70, rec_addr); M3St32(base, sp + 0x74, 0);
  ctx.r1.u32 = sp;
  return sp + 0x70;
}

inline int M3SehFilter(EXCEPTION_POINTERS* ep, M3Frame& f, PPCContext& ctx, uint8_t* base, M3Resolve resolve) {
  M3GuestRecord rec;
  if (!M3ToGuestRecord(ep, rec)) return EXCEPTION_CONTINUE_SEARCH;
  uint32_t pc = f.pc;
  for (uint32_t i = 0; i < f.count; ++i) {  // table order is innermost first
    const M3Scope& s = f.scopes[i];
    if (!s.target || pc < s.begin || pc >= s.end) continue;
    PPCContext saved = ctx;
    ctx.r3.u64 = M3PushRecord(ctx, base, rec);
    ctx.r4.u64 = f.establisher; ctx.r12.u64 = f.establisher;
    resolve(s.filter)(ctx, base);
    int32_t disposition = ctx.r3.s32;
    ctx = saved;
    if (disposition < 0) return EXCEPTION_CONTINUE_EXECUTION;
    if (disposition > 0) { f.resume = s.target; f.resume_index = i; return EXCEPTION_EXECUTE_HANDLER; }
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

// Second pass. Runs the __finally funclets of scopes nested inside the accepting
// scope (or all active ones when the frame is merely being unwound through).
inline void M3SehUnwind(M3Frame& f, PPCContext& ctx, uint8_t* base, M3Resolve resolve) {
  uint32_t pc = f.pc, limit = f.resume ? f.resume_index : f.count;
  for (uint32_t i = 0; i < limit; ++i) {
    const M3Scope& s = f.scopes[i];
    if (s.target || pc < s.begin || pc >= s.end) continue;
    PPCContext saved = ctx;
    ctx.r1.u32 = (ctx.r1.u32 - 0x400) & ~0xFu;
    ctx.r3.u64 = 1;  // AbnormalTermination
    ctx.r4.u64 = f.establisher; ctx.r12.u64 = f.establisher;
    resolve(s.filter)(ctx, base);
    ctx = saved;
  }
}

// ---- C++ EH (FuncInfo 0x19930522) shaped tables ---------------------------
struct M3CxxIp { uint32_t ip; int32_t state; };
struct M3CxxUnwindEntry { int32_t to_state; uint32_t action; };
struct M3CxxTry { int32_t low, high, catch_high; uint32_t handler; };  // catch(...) only, as in the target
struct M3CxxInfo {
  const M3CxxIp* ip; uint32_t ip_count;
  const M3CxxUnwindEntry* unwind; uint32_t state_count;
  const M3CxxTry* tries; uint32_t try_count;
};
constexpr uint32_t kCxxCode = 0xE06D7363;

inline int32_t M3CxxState(const M3CxxInfo& info, uint32_t pc) {
  int32_t state = -1;
  for (uint32_t i = 0; i < info.ip_count && info.ip[i].ip <= pc; ++i) state = info.ip[i].state;
  return state;
}
inline int M3CxxFilter(EXCEPTION_POINTERS* ep, M3Frame& f, const M3CxxInfo& info) {
  M3GuestRecord rec;
  if (!M3ToGuestRecord(ep, rec) || rec.code != kCxxCode) return EXCEPTION_CONTINUE_SEARCH;
  int32_t state = M3CxxState(info, f.pc);
  for (uint32_t i = 0; i < info.try_count; ++i)
    if (state >= info.tries[i].low && state <= info.tries[i].high) {
      f.resume = info.tries[i].handler; f.resume_index = i; return EXCEPTION_EXECUTE_HANDLER;
    }
  return EXCEPTION_CONTINUE_SEARCH;
}
inline void M3CxxUnwind(M3Frame& f, const M3CxxInfo& info, PPCContext& ctx, uint8_t* base, M3Resolve resolve) {
  int32_t state = M3CxxState(info, f.pc);
  int32_t target = f.resume ? info.tries[f.resume_index].low : -1;
  while (state != target && state >= 0) {
    const auto& e = info.unwind[state];
    if (e.action) {
      PPCContext saved = ctx;
      ctx.r1.u32 = (ctx.r1.u32 - 0x400) & ~0xFu;
      ctx.r12.u64 = f.establisher;
      resolve(e.action)(ctx, base);
      ctx = saved;
    }
    state = e.to_state;
  }
}
