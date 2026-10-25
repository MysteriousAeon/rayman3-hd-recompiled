// Milestone 4 runtime v1 (derived from the retained M3 prototype): table-driven guest exception dispatch for statically
// recompiled functions. One host function per guest function, PPCContext as
// the only register state, native host SEH as the transport. Nothing here is
// game code: tables in the tests are synthetic.
//
// Model (mirrors what the Xbox 360 kernel does with .pdata + scope tables):
//   pass 1  host __except filter -> M4SehFilter walks the scope table for the
//           guest pc marker, calls guest filter funclets (r3 = exception
//           pointers, r4/r12 = establisher frame).
//   pass 2  host __finally -> M4SehUnwind calls guest __finally funclets of
//           every scope being left (also runs for longjmp unwinds).
//   resume  host __except block restores the owner's non-volatile registers
//           and re-enters the try at the inline __except body *label*; the
//           body is never a callable function.
#pragma once
#include <windows.h>
#include <cstdint>
#include <cstring>
#include <rex/ppc/context.h>
#include <rex/logging.h>

// MSVC scope-table record. target == 0: __finally (filter holds the funclet).
struct M4Scope { uint32_t begin, end, filter, target; };
using M4Resolve = PPCFunc* (*)(uint32_t guest_address, uint8_t* base);

struct M4GuestRecord { uint32_t code, flags, record_chain, address, nparams, info[15]; };
constexpr DWORD kM4GuestRaise = 0xE0473458;  // host transport code for guest-raised records

struct M4NonVolatile {
  uint8_t regs[PPCContext::kNonVolatileSaveSize];
  PPCRegister r1, r2, r13;
};

struct M4Frame {
  const M4Scope* scopes; uint32_t count;
  uint32_t establisher;        // r1 on entry (what MSVC funclets receive in r12)
  volatile uint32_t pc;        // guest pc marker, updated at labels/scope edges
  volatile bool in_call;       // true while a callee of a guarded range runs
  volatile bool normal;        // set immediately before every ordinary return
  uint32_t resume; uint32_t resume_index;
  bool unwind; uint32_t return_value;
  M4NonVolatile snap;          // owner state at the last guarded call
};

inline void M4St32(uint8_t* base, uint32_t a, uint32_t v) { v = __builtin_bswap32(v); std::memcpy(base + a, &v, 4); }
inline uint32_t M4Ld32(uint8_t* base, uint32_t a) { uint32_t v; std::memcpy(&v, base + a, 4); return __builtin_bswap32(v); }

inline void M4Init(M4Frame& f, const M4Scope* scopes, uint32_t count, PPCContext& ctx) {
  f.scopes = scopes; f.count = count; f.establisher = ctx.r1.u32;
  f.unwind = false; f.return_value = 0; f.pc = 0; f.in_call = false; f.normal = false; f.resume = 0; f.resume_index = count;
}
inline void M4BeforeCall(M4Frame& f, PPCContext& ctx) {
  ctx.SaveNonVolatiles(f.snap.regs); f.snap.r1 = ctx.r1; f.snap.r2 = ctx.r2; f.snap.r13 = ctx.r13;
  f.in_call = true;
}
inline void M4RestoreOwner(M4Frame& f, PPCContext& ctx) {
  if (!f.in_call) return;  // fault was in the owner itself: ctx is already the owner's
  ctx.RestoreNonVolatiles(f.snap.regs); ctx.r1 = f.snap.r1; ctx.r2 = f.snap.r2; ctx.r13 = f.snap.r13;
  f.in_call = false;
}

// Guest RtlRaiseException equivalent: a continuable host exception carrying the record.
inline void M4Raise(M4GuestRecord& record) {
  ULONG_PTR arg = reinterpret_cast<ULONG_PTR>(&record);
  RaiseException(kM4GuestRaise, 0, 1, &arg);
}

// Explicit unwind is distinct from a guest exception: no filters are evaluated.
struct M4UnwindRequest { uint32_t frame, pc, value; };
constexpr DWORD kM4Unwind = 0xE0473459;
inline void M4RequestUnwind(M4UnwindRequest& req) {
  ULONG_PTR arg = reinterpret_cast<ULONG_PTR>(&req);
  RaiseException(kM4Unwind, EXCEPTION_NONCONTINUABLE, 1, &arg);
}

inline bool M4ToGuestRecord(EXCEPTION_POINTERS* ep, M4GuestRecord& out) {
  auto* r = ep->ExceptionRecord;
  if (r->ExceptionFlags & (EXCEPTION_UNWINDING | EXCEPTION_EXIT_UNWIND)) return false;
  if (r->ExceptionCode == kM4GuestRaise) { out = *reinterpret_cast<M4GuestRecord*>(r->ExceptionInformation[0]); return true; }
  // Native faults are handled below with guest arena provenance. Host faults
  // and host C++ exceptions must continue to the host failure boundary.
  return false;  // host-only exception: not a guest construct
}

// Writes EXCEPTION_POINTERS + record below the faulting guest frame, as the kernel does.
inline uint32_t M4PushRecord(PPCContext& ctx, uint8_t* base, const M4GuestRecord& rec) {
  uint32_t sp = (ctx.r1.u32 - 0x400) & ~0xFu;
  uint32_t rec_addr = sp + 0x80;
  M4St32(base, rec_addr + 0, rec.code); M4St32(base, rec_addr + 4, rec.flags);
  M4St32(base, rec_addr + 8, rec.record_chain); M4St32(base, rec_addr + 12, rec.address);
  M4St32(base, rec_addr + 16, rec.nparams);
  for (uint32_t i = 0; i < 15; ++i) M4St32(base, rec_addr + 20 + i * 4, rec.info[i]);
  M4St32(base, sp + 0x70, rec_addr); M4St32(base, sp + 0x74, 0);
  ctx.r1.u32 = sp;
  return sp + 0x70;
}

inline int M4SehFilter(EXCEPTION_POINTERS* ep, M4Frame& f, PPCContext& ctx, uint8_t* base, M4Resolve resolve) {
  M4GuestRecord rec;
  if (ep->ExceptionRecord->ExceptionCode == kM4Unwind) {
    auto& req = *reinterpret_cast<M4UnwindRequest*>(ep->ExceptionRecord->ExceptionInformation[0]);
    if (req.frame != f.establisher) return EXCEPTION_CONTINUE_SEARCH;
    f.resume = req.pc; f.resume_index = f.count; f.unwind = true; f.return_value = req.value;
    return EXCEPTION_EXECUTE_HANDLER;
  }
  if (!M4ToGuestRecord(ep, rec)) {
    auto* r = ep->ExceptionRecord;
    if ((r->ExceptionCode != EXCEPTION_ACCESS_VIOLATION && r->ExceptionCode != EXCEPTION_IN_PAGE_ERROR)
        || r->NumberParameters < 2 || r->ExceptionInformation[1] < uintptr_t(base)
        || r->ExceptionInformation[1] - uintptr_t(base) > UINT32_MAX)
      return EXCEPTION_CONTINUE_SEARCH;
    rec = {}; rec.code = r->ExceptionCode; rec.address = f.pc; rec.nparams = 2;
    rec.info[0] = uint32_t(r->ExceptionInformation[0]);
    rec.info[1] = uint32_t(r->ExceptionInformation[1] - uintptr_t(base));
  }
  uint32_t pc = f.pc;
  for (uint32_t i = 0; i < f.count; ++i) {  // table order is innermost first
    const M4Scope& s = f.scopes[i];
    if (!s.target || pc < s.begin || pc >= s.end) continue;
    PPCContext saved = ctx; bool was_in_call = f.in_call;
    M4RestoreOwner(f, ctx);
    // First pass may continue execution in the faulting callee. Scratch must
    // sit below its live stack, never overwrite frames below the owner.
    ctx.r1 = saved.r1;
    ctx.r3.u64 = M4PushRecord(ctx, base, rec);
    ctx.r4.u64 = f.establisher; ctx.r12.u64 = f.establisher;
    resolve(s.filter, base)(ctx, base);
    int32_t disposition = ctx.r3.s32;
    REXKRNL_INFO("M4 seh_filter pc={:08X} code={:08X} filter={:08X} disposition={} establisher={:08X}",
                 pc, rec.code, s.filter, disposition, f.establisher);
    ctx = saved; ctx.fpscr.restoreGuestBits(saved.fpscr.csr); f.in_call = was_in_call;
    if (disposition < 0) {
      if (rec.flags & EXCEPTION_NONCONTINUABLE) return EXCEPTION_CONTINUE_SEARCH;
      return EXCEPTION_CONTINUE_EXECUTION;
    }
    if (disposition > 0) { f.resume = s.target; f.resume_index = i; return EXCEPTION_EXECUTE_HANDLER; }
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

// Second pass. Runs the __finally funclets of scopes nested inside the accepting
// scope (or all active ones when the frame is merely being unwound through).
inline void M4SehUnwind(M4Frame& f, PPCContext& ctx, uint8_t* base, M4Resolve resolve) {
  uint32_t pc = f.pc, limit = f.resume ? f.resume_index : f.count;
  for (uint32_t i = 0; i < limit; ++i) {
    const M4Scope& s = f.scopes[i];
    if (s.target || pc < s.begin || pc >= s.end) continue;
    if (f.unwind && f.resume >= s.begin && f.resume < s.end) continue;
    PPCContext saved = ctx; bool was_in_call = f.in_call;
    M4RestoreOwner(f, ctx);
    ctx.r1.u32 = (ctx.r1.u32 - 0x400) & ~0xFu;
    ctx.r3.u64 = 1;  // AbnormalTermination
    ctx.r4.u64 = f.establisher; ctx.r12.u64 = f.establisher;
    resolve(s.filter, base)(ctx, base);
    REXKRNL_INFO("M4 seh_finally pc={:08X} funclet={:08X} establisher={:08X} unwind={}",
                 pc, s.filter, f.establisher, f.unwind);
    ctx = saved; ctx.fpscr.restoreGuestBits(saved.fpscr.csr); f.in_call = was_in_call;
  }
}
