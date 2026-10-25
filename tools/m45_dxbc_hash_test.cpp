// M45 (D-083): regression test for tools/m45_dxbc_hash.h. Built and run by tools/m45_regression.py.
//
// 1. Known answers: 16 deterministic inputs (an LCG seeded by the length) whose expected hashes were computed by the
//    retired AMD DXBCChecksum routine at the SDK pin (offline, M45 differential test; the AMD code is not linked).
//    The lengths sit on both sides of the one-block / two-block boundary (hashed length mod 64 = 55 / 56).
// 2. Independent oracle: FXC-compiled containers shipped in the SDK (src/graphics/shaders/bytecode/d3d12_5_1) carry
//    the hash Microsoft's compiler wrote; the function must reproduce it (stages vs/ps/hs/cs, both block cases).
// 3. Invariance: the magic and the hash field are not hashed; the result does not depend on buffer alignment.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

#include "m45_dxbc_hash.h"

using BYTE = uint8_t;
#include "adaptive_quad_hs.h"
#include "apply_gamma_table_ps.h"
#include "clear_uint2_ps.h"
#include "continuous_triangle_3cp_hs.h"
#include "float24_truncate_ps.h"
#include "fullscreen_cw_vs.h"
#include "passthrough_position_xy_vs.h"
#include "resolve_full_16bpp_cs.h"

static int g_fail = 0;
static void Check(const char* what, bool ok) {
  if (!ok) {
    ++g_fail;
    std::printf("FAIL %s\n", what);
  }
}

struct Known {
  uint32_t len;
  uint32_t hash[4];
};
static const Known kKnown[] = {
    {20, {0xf6600d14, 0xbae275b7, 0xd4be4a4e, 0xa1e9b201}},
    {21, {0xc27d354c, 0x9b618aa6, 0x00420c7b, 0x37c7bcc2}},
    {24, {0x1ef081e0, 0x4dd9e8c0, 0x2087128a, 0x7ce54f40}},
    {75, {0xd93a3c37, 0xc8b105f1, 0xa56211b0, 0x3d2622e8}},
    {76, {0xc4e693b0, 0xa3fd2bf6, 0x1279a2cb, 0x177ba4e0}},
    {79, {0x3b29f677, 0x8bd71390, 0xb7ca2921, 0x7c3713ab}},
    {80, {0x6a7d05d6, 0x142259ae, 0x2adb20b7, 0x90b0ab96}},
    {83, {0x738a7f63, 0x3ed207d3, 0xd14a2358, 0x0d25d7b6}},
    {84, {0x20f45e03, 0xdc755409, 0xbe696db6, 0x5bd89b43}},
    {139, {0xf8a1ddcc, 0x6856d4a0, 0x0e10429b, 0x0be58fed}},
    {140, {0xb64d4377, 0xc6b8b44b, 0x1797f339, 0xfefa056d}},
    {147, {0x9506e959, 0x4611c260, 0xe6bab0a1, 0x7bb3b96e}},
    {148, {0x637a0d8b, 0x795fa72f, 0x871e323b, 0x25ee5151}},
    {1000, {0xd793a3f5, 0x88002f69, 0x70281003, 0x5aa97f54}},
    {4116, {0x3ff42129, 0x5e163c21, 0xd6dcdfe7, 0x9a4914f4}},
    {65557, {0x8c6c2082, 0xaa7edd91, 0xf460643a, 0x79c8de71}},
};

static std::vector<uint8_t> Lcg(uint32_t len) {
  std::vector<uint8_t> b(len);
  uint32_t x = len;
  for (auto& c : b) {
    x = x * 1103515245u + 12345u;
    c = uint8_t(x >> 16);
  }
  return b;
}

static void CheckFxc(const char* name, const BYTE* p, size_t size) {
  uint32_t h[4];
  m45dxbc::ContainerHash(p, uint32_t(size), h);
  Check(name, std::memcmp(p, "DXBC", 4) == 0 && std::memcmp(h, p + 4, 16) == 0);
}

int main() {
  for (const Known& k : kKnown) {
    std::vector<uint8_t> b = Lcg(k.len);
    uint32_t h[4];
    m45dxbc::ContainerHash(b.data(), k.len, h);
    char what[64];
    std::snprintf(what, sizeof(what), "known answer len=%u", k.len);
    Check(what, std::memcmp(h, k.hash, 16) == 0);
    // Magic and hash field changed, every misalignment: same result.
    for (uint32_t mis = 1; mis < 8; ++mis) {
      std::vector<uint8_t> m(k.len + 8);
      std::memcpy(m.data() + mis, b.data(), k.len);
      for (uint32_t i = 0; i < 20; ++i) m[mis + i] ^= uint8_t(0xA5 + i);
      uint32_t h2[4];
      m45dxbc::ContainerHash(m.data() + mis, k.len, h2);
      std::snprintf(what, sizeof(what), "invariance len=%u mis=%u", k.len, mis);
      Check(what, std::memcmp(h2, k.hash, 16) == 0);
    }
  }
  CheckFxc("fxc passthrough_position_xy_vs", passthrough_position_xy_vs, sizeof(passthrough_position_xy_vs));
  CheckFxc("fxc fullscreen_cw_vs", fullscreen_cw_vs, sizeof(fullscreen_cw_vs));
  CheckFxc("fxc clear_uint2_ps", clear_uint2_ps, sizeof(clear_uint2_ps));
  CheckFxc("fxc apply_gamma_table_ps", apply_gamma_table_ps, sizeof(apply_gamma_table_ps));
  CheckFxc("fxc float24_truncate_ps", float24_truncate_ps, sizeof(float24_truncate_ps));
  CheckFxc("fxc continuous_triangle_3cp_hs", continuous_triangle_3cp_hs, sizeof(continuous_triangle_3cp_hs));
  CheckFxc("fxc adaptive_quad_hs", adaptive_quad_hs, sizeof(adaptive_quad_hs));
  CheckFxc("fxc resolve_full_16bpp_cs", resolve_full_16bpp_cs, sizeof(resolve_full_16bpp_cs));
  // A size below the header's 20 bytes reads nothing past the buffer and hashes an empty payload.
  uint8_t tiny[20] = {};
  uint32_t e1[4], e2[4];
  m45dxbc::ContainerHash(tiny, 4, e1);
  m45dxbc::ContainerHash(tiny, 20, e2);
  Check("short size = empty payload", std::memcmp(e1, e2, 16) == 0);
  std::printf(g_fail ? "M45_HASH_TEST FAIL (%d)\n" : "M45_HASH_TEST PASS\n", g_fail);
  return g_fail ? 1 : 0;
}
