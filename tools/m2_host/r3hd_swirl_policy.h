#pragma once
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>

namespace r3hd::swirl {
inline bool Enabled(const char* value) { return value && !std::strcmp(value, "restored"); }
inline bool Owns(uint32_t leaf_lr, uint32_t caller_lr, uint32_t kind = 0x3014) {
  return leaf_lr == 0x821E8688 && caller_lr == 0x8218CC90 && kind == 0x3014;
}
// Native texture headers encode an address carry in their high flags.
// Model the setter's address calculation rather than assuming page masking.
inline uint32_t TextureBase(uint32_t address) {
  const uint32_t rotated = (address << 12) | (address >> 20);
  return ((address & 0x1FFFFFFF) + (((rotated & 0xFFF) + 512) & 0x1000)) & 0xFFFFF000;
}
using Point = std::array<float, 3>;
using Quad = std::array<Point, 4>;
struct Basis { Point center, x, y; };
inline uint64_t ChangedGroups(const uint8_t* before, const uint8_t* after) {
  uint64_t mask=0;
  for(unsigned group=0;group<64;++group)
    if(std::memcmp(before+group*64,after+group*64,64)) mask|=uint64_t(1)<<(63-group);
  return mask;
}
// The native helix supplies parallelograms. Reject an unexpected contract rather
// than changing its shape or submitting another effect through this hook.
inline bool MakeBasis(const Quad& q, Basis& out) {
  for (unsigned axis = 0; axis < 3; ++axis) {
    for (const auto& p : q) if (!std::isfinite(p[axis])) return false;
    if (std::abs((q[0][axis] - q[1][axis]) - (q[3][axis] - q[2][axis])) > .001f) return false;
    out.center[axis] = (q[0][axis] + q[2][axis]) * .5f;
    out.x[axis] = (q[0][axis] - q[1][axis]) * .5f;
    out.y[axis] = (q[3][axis] - q[0][axis]) * .5f;
  }
  return true;
}
}  // namespace r3hd::swirl
