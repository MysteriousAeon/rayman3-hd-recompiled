// Linux Write-Watch Restart (LWR): bounded x86-64 scalar-store decoder.
//
// Pure computation over caller-supplied instruction bytes and a register
// snapshot: no calls, no globals, no allocation, no libc. It is used from
// signal context (lwr_restart.c) and from the ordinary self-tests on every
// platform, so both run the identical code.
//
// Admitted encodings (exactly the forms the pinned compilers emit for guest
// REX_STORE_U8/U32/U64 in the selected functions, plus the 16-bit form of the
// same opcode):
//   [66] [REX 40-4F] 88 /r   mov r/m8, r8          width 1 (no 66, no REX.W)
//   [66] [REX 40-4F] 89 /r   mov r/m16/32/64, r    width 2 (66), 4, 8 (REX.W)
// with a memory destination (ModRM.mod != 3), an explicit base register,
// optional SIB index and disp8/disp32. Everything else is rejected: other
// opcodes (immediate, string, SSE/AVX, RMW, xchg, movbe), lock/rep/segment/
// address-size prefixes, duplicate prefixes, RIP-relative and base-less
// addressing, 66 together with REX.W or with opcode 88.
#pragma once
#ifdef __cplusplus
#include <cstddef>
#include <cstdint>
extern "C" {
#else
#include <stddef.h>
#include <stdint.h>
#endif

// Register numbering is the x86-64 encoding order:
// 0 rax, 1 rcx, 2 rdx, 3 rbx, 4 rsp, 5 rbp, 6 rsi, 7 rdi, 8..15 r8..r15.
struct lwr_store {
  uint64_t effective;  // Effective (host) address of the first byte written.
  unsigned width;      // Bytes written: 1, 2, 4 or 8.
  unsigned length;     // Instruction length in bytes.
  unsigned base, index, scale;  // index == 16 when absent.
  int64_t displacement;
};

// Always inlined (also at -O0), so the signal-context caller contains no call.
#if defined(__GNUC__) || defined(__clang__)
#define LWR_ALWAYS_INLINE inline __attribute__((always_inline))
#else
#define LWR_ALWAYS_INLINE inline
#endif

// Returns 1 and fills *out when code[0..avail) starts with an admitted store;
// returns 0 otherwise (and *out is unspecified). Never reads code[avail..].
static LWR_ALWAYS_INLINE int lwr_decode_store(const unsigned char* code, size_t avail, const uint64_t regs[16],
                                   struct lwr_store* out) {
  size_t i = 0;
  unsigned opsize16 = 0, rex = 0;
  if (!code || !regs || !out || avail == 0) return 0;
  if (code[i] == 0x66) {
    opsize16 = 1;
    if (++i >= avail) return 0;
  }
  if ((code[i] & 0xF0u) == 0x40u) {
    rex = code[i];
    if (++i >= avail) return 0;
  }
  const unsigned char opcode = code[i];
  if (++i >= avail) return 0;
  const unsigned rex_w = (rex >> 3) & 1u, rex_r = (rex >> 2) & 1u, rex_x = (rex >> 1) & 1u,
                 rex_b = rex & 1u;
  (void)rex_r;  // The source register does not affect the destination.
  unsigned width;
  if (opcode == 0x88u) {
    if (opsize16 || rex_w) return 0;
    width = 1;
  } else if (opcode == 0x89u) {
    if (opsize16 && rex_w) return 0;
    width = rex_w ? 8u : (opsize16 ? 2u : 4u);
  } else {
    return 0;
  }
  const unsigned char modrm = code[i++];
  const unsigned mod = modrm >> 6, rm = modrm & 7u;
  if (mod == 3u) return 0;  // Register destination: not a store.
  unsigned base, index = 16, scale = 1;
  if (rm == 4u) {
    if (i >= avail) return 0;
    const unsigned char sib = code[i++];
    const unsigned sib_base = sib & 7u, sib_index = ((sib >> 3) & 7u) | (rex_x << 3);
    if (sib_base == 5u && mod == 0u) return 0;  // No base register (disp32 only).
    base = sib_base | (rex_b << 3);
    if (sib_index != 4u) {  // Index 4 without REX.X encodes "no index".
      index = sib_index;
      scale = 1u << (sib >> 6);
    }
  } else {
    if (rm == 5u && mod == 0u) return 0;  // RIP-relative.
    base = rm | (rex_b << 3);
  }
  int64_t displacement = 0;
  if (mod == 1u) {
    if (i + 1 > avail) return 0;
    displacement = (int8_t)code[i];
    i += 1;
  } else if (mod == 2u) {
    if (i + 4 > avail) return 0;
    const uint32_t raw = (uint32_t)code[i] | ((uint32_t)code[i + 1] << 8) |
                         ((uint32_t)code[i + 2] << 16) | ((uint32_t)code[i + 3] << 24);
    displacement = (int32_t)raw;
    i += 4;
  }
  uint64_t ea = regs[base] + (uint64_t)displacement;
  if (index != 16) ea += regs[index] * scale;
  out->effective = ea;
  out->width = width;
  out->length = (unsigned)i;
  out->base = base;
  out->index = index;
  out->scale = index == 16 ? 0u : scale;
  out->displacement = displacement;
  return 1;
}

#ifdef __cplusplus
}
#endif
