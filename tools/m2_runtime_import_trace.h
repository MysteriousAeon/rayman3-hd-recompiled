#pragma once
#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <set>
#include <string>
#include <tuple>
#include <rex/logging.h>
#include <rex/ppc/context.h>
// M3: guest RtlRaiseException record plus saved-LR words up the guest back chain.
// Uses the live ctx/base of the import wrapper; read-only.
inline void M3RaiseTrace(PPCContext& ctx, uint8_t* base) {
  auto load = [&](uint32_t a) { uint32_t v; std::memcpy(&v, base + a, 4); return __builtin_bswap32(v); };
  auto valid = [](uint32_t a) { return a >= 0x10000 && a < 0xA0000000 && !(a & 3); };
  uint32_t record = ctx.r3.u32, frame = ctx.r1.u32, chain[6] = {};
  for (int i = 0; i < 6 && valid(frame); ++i) {
    // Stay inside the current guest stack: frames grow upward by small steps and the
    // initial frame sits on the (unmapped) 64 KiB boundary at the top of the stack.
    uint32_t next = load(frame);
    if (!valid(next) || next <= frame || next - frame > 0x8000 || (next & 0xFFFF) == 0) break;
    frame = next;
    chain[i] = load(frame - 8);
  }
  if (!valid(record)) return;
  REXKRNL_INFO("M3 guest_raise code={:08X} flags={:08X} address={:08X} nparams={} info0={:08X} lr={:08X} sp={:08X} "
               "chain={:08X},{:08X},{:08X},{:08X},{:08X},{:08X}",
               load(record), load(record + 4), load(record + 12), load(record + 16), load(record + 20),
               unsigned(ctx.lr), ctx.r1.u32, chain[0], chain[1], chain[2], chain[3], chain[4], chain[5]);
}
// G6-P77 (test only, hidden runs): with R3HD_NONINTRUSIVE and R3HD_PROFILE_TRACE=1, the profile / save boundary
// imports (XamUser*, XamShow*, content enumeration and creator) log each distinct (import, caller, r3, result)
// once, with the arguments at entry and the result in r3 after the call. At most 256 lines per process; nothing is
// written to the guest. Without both variables this is one cached test per import call and logs nothing.
class G6P77ProfileTrace {
 public:
  G6P77ProfileTrace(const char* name, PPCContext& ctx)
      : name_(Wanted(name) ? name : nullptr), ctx_(ctx), caller_(unsigned(ctx.lr) - 4), r3_(ctx.r3.u32),
        r4_(ctx.r4.u32), r5_(ctx.r5.u32), r6_(ctx.r6.u32) {}
  ~G6P77ProfileTrace() {
    if (!name_) return;
    static std::mutex lock;
    static std::set<std::tuple<std::string, uint32_t, uint32_t, uint32_t>> seen;
    static unsigned lines = 0;
    const uint32_t result = ctx_.r3.u32;
    std::lock_guard<std::mutex> guard(lock);
    if (lines >= 256 || !seen.emplace(name_, caller_, r3_, result).second) return;
    ++lines;
    REXKRNL_INFO("G6P77 xam import={} caller={:08X} r3={:08X} r4={:08X} r5={:08X} r6={:08X} result={:08X} line={}",
                 name_, caller_, r3_, r4_, r5_, r6_, result, lines);
  }
  G6P77ProfileTrace(const G6P77ProfileTrace&) = delete;
  G6P77ProfileTrace& operator=(const G6P77ProfileTrace&) = delete;
  static bool Enabled() {
    static const bool enabled = [] {
      const char* trace = std::getenv("R3HD_PROFILE_TRACE");
      return std::getenv("R3HD_NONINTRUSIVE") != nullptr && trace && std::strcmp(trace, "1") == 0;
    }();
    return enabled;
  }
  static bool Wanted(const char* name) {
    if (!Enabled()) return false;
    for (const char* prefix : {"__imp__XamUser", "__imp__XamShow", "__imp__XamContentCreateEnumerator",
                               "__imp__XamContentGetCreator", "__imp__XamContentGetDeviceData", "__imp__XamEnumerate"})
      if (std::strncmp(name, prefix, std::strlen(prefix)) == 0) return true;
    return false;
  }

 private:
  const char* name_;
  PPCContext& ctx_;
  uint32_t caller_, r3_, r4_, r5_, r6_;
};
// Used only in the typed export wrapper (hook.h REX_HOOK, via m2_runtime_patch.py), never in raw hooks: the
// object lives to the end of the wrapper's body, after HostToGuestFunction has stored the result in r3.
#define G6P77_PROFILE_TRACE(name) G6P77ProfileTrace g6p77_profile_trace(name, ctx)
// One counter per macro expansion. First and power-of-two hits keep startup logs bounded.
#define M2_IMPORT_TRACE(name, stub) do { \
  if (__builtin_strcmp(name, "__imp__RtlRaiseException") == 0) M3RaiseTrace(ctx, base); \
  static std::atomic<unsigned long long> m2_count{0}; \
  auto m2_n = ++m2_count; \
  if ((m2_n & (m2_n - 1)) == 0) \
    REXKRNL_INFO("M2 import={} stub={} count={} caller={:08X} r3={:08X} r4={:08X} r5={:08X} r6={:08X}", \
      name, stub, m2_n, unsigned(ctx.lr) - 4, ctx.r3.u32, ctx.r4.u32, ctx.r5.u32, ctx.r6.u32); \
} while (0)
