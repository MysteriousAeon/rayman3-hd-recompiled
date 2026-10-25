#pragma once
#include <atomic>
#include <cstring>
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
// One counter per macro expansion. First and power-of-two hits keep startup logs bounded.
#define M2_IMPORT_TRACE(name, stub) do { \
  if (__builtin_strcmp(name, "__imp__RtlRaiseException") == 0) M3RaiseTrace(ctx, base); \
  static std::atomic<unsigned long long> m2_count{0}; \
  auto m2_n = ++m2_count; \
  if ((m2_n & (m2_n - 1)) == 0) \
    REXKRNL_INFO("M2 import={} stub={} count={} caller={:08X} r3={:08X} r4={:08X} r5={:08X} r6={:08X}", \
      name, stub, m2_n, unsigned(ctx.lr) - 4, ctx.r3.u32, ctx.r4.u32, ctx.r5.u32, ctx.r6.u32); \
} while (0)
