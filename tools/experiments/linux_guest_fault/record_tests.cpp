#include "record_contract.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <vector>
static unsigned checks;
static void check(bool ok) { ++checks; if (!ok) std::abort(); }
static uint32_t load(const std::vector<uint8_t>& m, uint32_t a) {
  return uint32_t(m[a]) << 24 | uint32_t(m[a+1]) << 16 |
         uint32_t(m[a+2]) << 8 | m[a+3];
}
int main() {
  check(lgf::contains(0x10000, 0x1000, 0x10000, 4));
  check(lgf::contains(0x10000, 0x1000, 0x10ffc, 4));
  check(!lgf::contains(0x10000, 0x1000, 0x10ffd, 4));
  check(!lgf::contains(0x10000, 0x1000, 0x11000, 1));
  check(!lgf::contains(0x10000, 0x1000, 0xffff, 1));
  check(!lgf::contains(UINTPTR_MAX - 3, 8, UINTPTR_MAX - 3, 4));
  check(!lgf::contains(1, 0, 1, 1));
  check(!lgf::contains(1, 8, 1, 0));
  check(!lgf::contains(1, (uint64_t{1} << 32) + 1, 1, 1));
  check(lgf::contains(0, uint64_t{1} << 32, UINT32_MAX, 1));
  std::vector<uint8_t> mem(0x4000, 0xa5);
  lgf::Record r{0xc0000005, 0, 0, 0x82001234, 2, {0, 0x12345678}};
  uint32_t sp = 0, ep = 0;
  check(lgf::push(mem, 0x3007, 0x1000, 0x4000, r, sp, ep));
  check(sp == 0x2c00 && ep == sp + 0x70 && !(sp & 15));
  check(load(mem, ep) == sp + 0x80 && load(mem, ep+4) == 0);
  const std::array<uint32_t, 5> fields{r.code, r.flags, r.chain, r.pc, r.count};
  for (unsigned i = 0; i < fields.size(); ++i) check(load(mem, sp+0x80+4*i) == fields[i]);
  for (unsigned i = 0; i < 15; ++i) check(load(mem, sp+0x94+4*i) == r.info[i]);
  for (size_t i = 0; i < mem.size(); ++i)
    if (!(i >= sp+0x70 && i < sp+0x78) && !(i >= sp+0x80 && i < sp+0xd0)) check(mem[i] == 0xa5);
  auto before = mem;
  for (uint32_t bad : {0u, 0x3ffu, 0x1000u, 0x5000u})
    check(!lgf::push(mem, bad, 0x1000, 0x4000, r, sp, ep));
  r.count = 16;
  check(!lgf::push(mem, 0x3000, 0x1000, 0x4000, r, sp, ep));
  check(mem == before);
  std::printf("RECORD_CONTRACT PASS checks=%u\n", checks);
}
