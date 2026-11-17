// Isolated M4 serialization model; not a production ABI implementation.
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

namespace lgf {
struct Record {
  uint32_t code{}, flags{}, chain{}, pc{}, count{};
  std::array<uint32_t, 15> info{};
};
// Stronger experimental policy: subtraction avoids base+size overflow.
constexpr bool contains(uintptr_t base, uint64_t size, uintptr_t address,
                        uint64_t width) {
  return size && size <= (uint64_t{1} << 32) && width && width <= size &&
         size - 1 <= UINTPTR_MAX - base && address >= base &&
         uint64_t(address - base) <= size - width;
}
inline void be32(std::span<uint8_t> mem, uint32_t offset, uint32_t value) {
  for (unsigned i = 0; i != 4; ++i)
    mem[offset + i] = uint8_t(value >> (24 - 8 * i));
}
// Extra bounds are experimental safeguards; M4 itself does not validate them.
// Fail before writing; caller supplies the *live callee* stack interval.
inline bool push(std::span<uint8_t> mem, uint32_t live_sp,
                 uint32_t stack_low, uint32_t stack_high, const Record& r,
                 uint32_t& scratch, uint32_t& pointers) {
  if (r.count > 15 || live_sp < 0x400 || live_sp > stack_high ||
      stack_low > stack_high) return false;
  const uint32_t sp = (live_sp - 0x400u) & ~0xfu;
  if (sp < stack_low || sp > stack_high || stack_high - sp < 0x400 ||
      sp > mem.size() || mem.size() - sp < 0x400) return false;
  const uint32_t record = sp + 0x80;
  be32(mem, sp + 0x70, record);
  be32(mem, sp + 0x74, 0); // Existing zero ContextRecord contract.
  be32(mem, record, r.code); be32(mem, record + 4, r.flags);
  be32(mem, record + 8, r.chain); be32(mem, record + 12, r.pc);
  be32(mem, record + 16, r.count);
  for (uint32_t i = 0; i < 15; ++i) be32(mem, record + 20 + 4*i, r.info[i]);
  scratch = sp; pointers = sp + 0x70;
  return true;
}
} // namespace lgf
