// LM-A portable guest exception backend (Linux; on Windows only with R3HD_M4_PORTABLE, for differential tests).
//
// Same data model and the same guest-visible semantics as the Windows M4 backend in m4_seh.h, with a different
// host transport (reports/LINUX_LMA_ASSESSMENT_2026-11.md; maintainer decisions D1-D4, 2026-11-07):
//   * Every owner links its M4Frame into a thread-local list at M4_FRAME and unlinks it on every exit (normal
//     return, fall-through, exception, guest longjmp). No destructor is involved, so host longjmp across generated
//     frames stays well defined.
//   * Pass 1 (search) runs synchronously inside M4Raise / M4RequestUnwind, innermost owner first, with the exact
//     scope rules, filter calling convention and state restoration of M4SehFilter. -1 returns to the raiser
//     (continue execution); acceptance marks the owner and throws an M4Transfer token.
//   * Pass 2 (cleanup) is the C++ unwind of that token: every owner left runs M4SehUnwind exactly as the Windows
//     __finally does, and the accepting owner restores its non-volatiles and re-enters at the inline label.
//   * D2: hardware faults are not converted to guest exceptions (initial LM-A boundary; conversion stays OPEN).
//   * D3: POSIX forced unwinding (thread cancellation/exit) passes through untouched and runs no guest __finally,
//     as Windows thread termination runs none.
//   * D4: a transfer that would cross an SDK host->guest call boundary (FunctionDispatcher::Execute) fails fast.
//   * Everything unsupported fails fast with a record on stderr and the log: never silently.
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <unordered_map>
#include <rex/ppc/context.h>
#include <rex/logging.h>
#if defined(__GLIBCXX__) || defined(__GLIBC__)
#include <cxxabi.h>
#define M4_CATCH_FORCED_UNWIND catch (::abi::__forced_unwind&) { throw; }
#else
#define M4_CATCH_FORCED_UNWIND
#endif

struct M4Scope { uint32_t begin, end, filter, target; };
using M4Resolve = PPCFunc* (*)(uint32_t guest_address, uint8_t* base);

struct M4GuestRecord { uint32_t code, flags, record_chain, address, nparams, info[15]; };
struct M4UnwindRequest { uint32_t frame, pc, value; };
constexpr uint32_t kM4GuestNoncontinuable = 1;  // EXCEPTION_NONCONTINUABLE in the guest record flags

struct M4NonVolatile {
  uint8_t regs[PPCContext::kNonVolatileSaveSize];
  PPCRegister r1, r2, r13;
};

struct M4Frame {
  const M4Scope* scopes; uint32_t count;
  uint32_t establisher;
  volatile uint32_t pc;
  volatile bool in_call;
  volatile bool normal;
  uint32_t resume; uint32_t resume_index;
  bool unwind; uint32_t return_value;
  M4NonVolatile snap;
  // Portable transport only.
  PPCContext* ctx; uint8_t* base; M4Resolve resolve;
  M4Frame* next; bool linked; const char* boundary;  // boundary != nullptr: an SDK host->guest call, not an owner
};

struct M4Transfer { M4Frame* target; bool unwind; };

namespace m4p {
inline thread_local M4Frame* top = nullptr;
inline thread_local bool in_funclet = false;
inline thread_local std::unordered_map<uint32_t, M4Frame*> setjmp_tops;
inline bool any_owner = false;  // set once any owner ran in this process (a tree generated with exception handlers)

[[noreturn]] inline void Fail(const char* what, uint32_t a, uint32_t b, const char* detail = nullptr) {
  std::fprintf(stderr, "M4 portable: FAIL-FAST %s (0x%08X, 0x%08X)%s%s\n", what, a, b, detail ? ": " : "",
               detail ? detail : "");
  std::fflush(stderr);
  REXKRNL_INFO("M4 portable fail_fast what={} a={:08X} b={:08X} detail={}", what, a, b, detail ? detail : "");
  std::abort();
}

// D4: name the boundary (SDK call and the guest function it entered), the exception and the target owner.
[[noreturn]] inline void FailBoundary(const char* what, uint32_t code, uint32_t address, uint32_t owner,
                                      const M4Frame& boundary) {
  char detail[256];
  std::snprintf(detail, sizeof detail, "%s across SDK host->guest boundary %s(guest %08X); code %08X, address %08X, "
                "target owner establisher %08X", what, boundary.boundary, boundary.establisher, code, address, owner);
  Fail("transfer across an SDK host->guest boundary", code, owner, detail);
}

inline void Link(M4Frame& f) { f.next = top; top = &f; f.linked = true; }
inline void Unlink(M4Frame& f) {
  if (!f.linked) return;
  for (M4Frame** p = &top; *p; p = &(*p)->next) {
    if (*p == &f) { *p = f.next; f.linked = false; return; }
  }
  Fail("unlink of an owner that is not registered", f.establisher, f.pc);
}

struct FuncletGuard {
  explicit FuncletGuard(uint32_t funclet) {
    if (in_funclet) Fail("guest exception inside a running filter/finally funclet", funclet, 0);
    in_funclet = true;
  }
  ~FuncletGuard() { in_funclet = false; }
};
}  // namespace m4p

inline void M4St32(uint8_t* base, uint32_t a, uint32_t v) { v = __builtin_bswap32(v); std::memcpy(base + a, &v, 4); }
inline uint32_t M4Ld32(uint8_t* base, uint32_t a) { uint32_t v; std::memcpy(&v, base + a, 4); return __builtin_bswap32(v); }

inline void M4Init(M4Frame& f, const M4Scope* scopes, uint32_t count, PPCContext& ctx) {
  f.scopes = scopes; f.count = count; f.establisher = ctx.r1.u32;
  f.unwind = false; f.return_value = 0; f.pc = 0; f.in_call = false; f.normal = false; f.resume = 0; f.resume_index = count;
}
inline void M4PortableInit(M4Frame& f, const M4Scope* scopes, uint32_t count, PPCContext& ctx, uint8_t* base,
                           M4Resolve resolve) {
  M4Init(f, scopes, count, ctx);
  f.ctx = &ctx; f.base = base; f.resolve = resolve; f.boundary = nullptr; f.linked = false;
  m4p::any_owner = true;
  m4p::Link(f);
}
inline void M4Unlink(M4Frame& f) { m4p::Unlink(f); }
inline bool M4Accepts(const M4Transfer& t, const M4Frame& f) { return t.target == &f; }

inline void M4BeforeCall(M4Frame& f, PPCContext& ctx) {
  ctx.SaveNonVolatiles(f.snap.regs); f.snap.r1 = ctx.r1; f.snap.r2 = ctx.r2; f.snap.r13 = ctx.r13;
  f.in_call = true;
}
inline void M4RestoreOwner(M4Frame& f, PPCContext& ctx) {
  if (!f.in_call) return;
  ctx.RestoreNonVolatiles(f.snap.regs); ctx.r1 = f.snap.r1; ctx.r2 = f.snap.r2; ctx.r13 = f.snap.r13;
  f.in_call = false;
}

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

// Pass 1 for one owner: M4SehFilter's guest-raise branch, verbatim apart from the transport.
// Returns -1 (continue execution), 0 (continue search) or 1 (accepted: f.resume/f.resume_index set).
inline int M4PortableFilterOwner(const M4GuestRecord& rec, M4Frame& f) {
  PPCContext& ctx = *f.ctx; uint8_t* base = f.base;
  uint32_t pc = f.pc;
  for (uint32_t i = 0; i < f.count; ++i) {
    const M4Scope& s = f.scopes[i];
    if (!s.target || pc < s.begin || pc >= s.end) continue;
    PPCContext saved = ctx; bool was_in_call = f.in_call;
    M4RestoreOwner(f, ctx);
    ctx.r1 = saved.r1;
    ctx.r3.u64 = M4PushRecord(ctx, base, rec);
    ctx.r4.u64 = f.establisher; ctx.r12.u64 = f.establisher;
    {
      m4p::FuncletGuard guard(s.filter);
      f.resolve(s.filter, base)(ctx, base);
    }
    int32_t disposition = ctx.r3.s32;
    REXKRNL_INFO("M4 seh_filter pc={:08X} code={:08X} filter={:08X} disposition={} establisher={:08X}",
                 pc, rec.code, s.filter, disposition, f.establisher);
    ctx = saved; ctx.fpscr.restoreGuestBits(saved.fpscr.csr); f.in_call = was_in_call;
    if (disposition < 0) {
      if (rec.flags & kM4GuestNoncontinuable) return 0;
      return -1;
    }
    if (disposition > 0) { f.resume = s.target; f.resume_index = i; return 1; }
  }
  return 0;
}

// Guest RtlRaiseException: synchronous search, then continue (return) or transfer (throw).
inline void M4Raise(M4GuestRecord& record) {
  if (m4p::in_funclet) m4p::Fail("guest RtlRaiseException inside a running funclet", record.code, record.address);
  const M4Frame* crossed = nullptr;  // the innermost SDK host->guest boundary below the raise
  for (M4Frame* f = m4p::top; f; f = f->next) {
    if (f->boundary) { if (!crossed) crossed = f; continue; }
    int r = M4PortableFilterOwner(record, *f);
    if (r < 0) return;
    if (r > 0) {
      if (crossed)  // D4
        m4p::FailBoundary("guest exception transfer", record.code, record.address, f->establisher, *crossed);
      f->unwind = false;
      throw M4Transfer{f, false};
    }
  }
  // Diagnostic-tree compatibility only: in a tree generated without exception handlers no owner ever exists, and
  // the upstream SDK continues a thread-naming raise after its side effect. In an M4 tree every observed naming raise
  // is decided by a real owner filter (Windows would crash on an unhandled one), so this branch never applies there.
  if (!m4p::any_owner && record.code == 0x406D1388u) return;
  m4p::Fail("unhandled guest exception", record.code, record.address, crossed ? crossed->boundary : nullptr);
}

// Guest RtlUnwind: no filters; the owner whose establisher matches is the target (M4SehFilter's unwind branch).
inline void M4RequestUnwind(M4UnwindRequest& req) {
  if (m4p::in_funclet) m4p::Fail("guest RtlUnwind inside a running funclet", req.frame, req.pc);
  const M4Frame* crossed = nullptr;
  for (M4Frame* f = m4p::top; f; f = f->next) {
    if (f->boundary) { if (!crossed) crossed = f; continue; }
    if (req.frame != f->establisher) continue;
    if (crossed) m4p::FailBoundary("guest RtlUnwind", 0, req.pc, req.frame, *crossed);
    f->resume = req.pc; f->resume_index = f->count; f->unwind = true; f->return_value = req.value;
    throw M4Transfer{f, true};
  }
  m4p::Fail("guest RtlUnwind to an establisher with no live owner", req.frame, req.pc,
            crossed ? crossed->boundary : nullptr);
}

// Pass 2 for one owner: M4SehUnwind, verbatim apart from the funclet guard.
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
    {
      m4p::FuncletGuard guard(s.filter);
      resolve(s.filter, base)(ctx, base);
    }
    REXKRNL_INFO("M4 seh_finally pc={:08X} funclet={:08X} establisher={:08X} unwind={}",
                 pc, s.filter, f.establisher, f.unwind);
    ctx = saved; ctx.fpscr.restoreGuestBits(saved.fpscr.csr); f.in_call = was_in_call;
  }
}

// D4: an SDK host->guest call (FunctionDispatcher::Execute). Searches see it; transfers may not cross it.
struct M4HostBoundary {
  M4Frame node{};
  M4HostBoundary(const char* what, uint32_t guest_address) {
    node.boundary = what; node.establisher = guest_address; m4p::Link(node);
  }
  ~M4HostBoundary() { m4p::Unlink(node); }
  M4HostBoundary(const M4HostBoundary&) = delete;
  M4HostBoundary& operator=(const M4HostBoundary&) = delete;
};

// Guest setjmp/longjmp (pch ppc_setjmp/ppc_longjmp). MSVC longjmp unwinds through the intervening owners and runs
// their __finally (M4SehUnwind with normal == false); glibc longjmp runs nothing. Before the host longjmp, run the
// same cleanup for every owner registered after the setjmp, innermost first, and unlink them.
inline void M4NoteSetjmp(uint32_t guest_buf) {
  m4p::setjmp_tops[guest_buf] = m4p::top;
}
inline void M4LongjmpPrepare(uint32_t guest_buf) {
  if (m4p::in_funclet) m4p::Fail("guest longjmp inside a running funclet", guest_buf, 0);
  auto it = m4p::setjmp_tops.find(guest_buf);
  if (it == m4p::setjmp_tops.end()) return;  // no setjmp for this buffer on this thread: the caller aborts as before
  M4Frame* target = it->second;
  bool found = target == nullptr;
  for (M4Frame* f = m4p::top; f && !found; f = f->next) found = f == target;
  if (!found) m4p::Fail("guest longjmp to a setjmp whose owner frame is no longer live", guest_buf, 0);
  while (m4p::top != target) {
    M4Frame* f = m4p::top;
    if (f->boundary) m4p::FailBoundary("guest longjmp", 0, guest_buf, 0, *f);
    if (!f->normal) M4SehUnwind(*f, *f->ctx, f->base, f->resolve);
    m4p::Unlink(*f);
  }
}

// The hooks keep using __fastfail for a malformed record; generated owners use M4_FAIL.
#ifndef __fastfail
#define __fastfail(code) m4p::Fail("__fastfail", uint32_t(code), 0)
#endif

// LM-A (D1) emission macros, portable expansion. M4_TRY_END closes the owner's try regions: the inner handler is the
// Windows __finally (pass 2 cleanup of an owner being left), the outer handlers the Windows __except (accept the
// owner's own token and re-enter, otherwise unlink and keep unwinding). The trailing unlink covers fall-through.
#define M4_FRAME(count) M4Frame m4; M4PortableInit(m4, m4scopes, count, ctx, base, m4resolve);
#define M4_TRY_BEGIN try { try {
#define M4_FAIL(code) m4p::Fail("invalid owner resume label", uint32_t(code), m4.pc)
#define M4_RETURN { m4.normal = true; M4Unlink(m4); return; }
#define M4_TRY_END \
  } M4_CATCH_FORCED_UNWIND catch (...) { if (!m4.normal) M4SehUnwind(m4, ctx, base, m4resolve); throw; } \
  } catch (const M4Transfer& m4t) { \
    if (!M4Accepts(m4t, m4)) { M4Unlink(m4); throw; } \
    M4RestoreOwner(m4, ctx); if (m4.unwind) ctx.r3.u64 = m4.return_value; goto m4_retry; \
  } catch (...) { M4Unlink(m4); throw; } \
  M4Unlink(m4);
