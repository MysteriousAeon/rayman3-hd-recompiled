// G6-P89 host test of tools/g6p89_scale32.h (exact rational scale, model R, ranges, refusal exit).
// Build: clang++ -std=c++20 -O1 -I tools/g6p89_stub -I tools tools/g6p89_scale32_test.cpp (tools/g6p89_scale32_regression.py).
//   g6p89_scale32_test            all checks; prints `G6P89_HOST_TEST PASS checksum=<hex>` (checksum of R offsets over a
//                                 1280x720 4-byte surface, compared with the Python model by the regression)
//   g6p89_scale32_test refuse     calls Scale{3,3,2}.X(1281); must exit with code 137
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <set>
#include <vector>

#include "g6p89_scale32.h"

static int g_fail = 0;
#define CHECK(c)                                                       \
  do {                                                                 \
    if (!(c)) {                                                        \
      std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #c); \
      ++g_fail;                                                        \
    }                                                                  \
  } while (0)

static void IntegerIdentity() {
  const uint32_t values[] = {0u, 1u, 7u, 8u, 80u, 640u, 720u, 1024u, 1280u, 8192u, 0x7FFFFFFFu, 0xFFFFFFFFu};
  for (uint32_t s = 1; s <= 3; ++s) {
    g6p89::Scale sc{s, s, 1};
    CHECK(!sc.Rational());
    CHECK(sc.Scaled() == (s > 1));
    for (uint32_t v : values) {
      CHECK(sc.X(v) == v * s);  // the SDK's original uint32 expression, wrap included
      CHECK(sc.Y(v) == v * s);
      CHECK(sc.AreaBytes(v) == uint64_t(v) * (s * s));
      CHECK(sc.AddressExact(v) == uint64_t(v) * (s * s));
      CHECK(sc.InvX(v * s) == (v * s) / s);
      CHECK(sc.Xf() == float(s) && sc.InvXf() == 1.0f / float(s) && sc.MaxF() == float(s));
    }
    CHECK(sc.TileWidthSamples() == 80 * s && sc.TileHeightSamples() == 16 * s);
    CHECK(sc.IntegerArea() == s * s);
  }
  CHECK(g6p89::ActiveScale(2, 2).den == 1 && g6p89::ActiveScale(2, 2).x == 2);
}

static void RationalValues() {
  g6p89::Scale r{3, 3, 2};
  CHECK(r.Rational() && r.Scaled());
  CHECK(r.X(1280) == 1920 && r.Y(720) == 1080 && r.X(1024) == 1536 && r.Y(1024) == 1536);
  CHECK(r.X(640) == 960 && r.Y(360) == 540 && r.Y(736) == 1104 && r.X(8192) == 12288);
  CHECK(r.TileWidthSamples() == 120 && r.TileHeightSamples() == 24);
  CHECK((r.TileWidthSamples() >> 1) == 60 && (r.TileWidthSamples() >> 3) == 15);  // 64bpp at 4x / transfer halves
  CHECK(r.AreaBytes(10u << 20) == 23592960ull);                  // EDRAM buffer
  CHECK(r.AreaBytes(512ull << 20) == 1152ull << 20);             // scaled resolve address space
  CHECK(r.AreaBytes(80u * 16u) == 2880u);                        // 32bpp tile dwords
  CHECK(r.AddressExact(0) == 0 && r.AddressExact(64) == 144 && r.AddressExact(4096) == 9216);
  CHECK(r.InvX(1920) == 1280 && r.Xf() == 1.5f && r.InvXf() == 2.0f / 3.0f && r.MaxF() == 1.5f);
  uint64_t f, e;
  g6p89::Scale::RationalRange(0, 64, f, e);
  CHECK(f == 0 && e == 144);
  g6p89::Scale::RationalRange(65, 1, f, e);
  CHECK(f == 144 && e == 288);
  g6p89::Scale::RationalRange(4096, 3768320, f, e);
  CHECK(f == 9216 && e == 9216 + 3768320ull * 9 / 4);
}

struct Surface {
  uint32_t width, height, pitch, bpb_log2;
};

// Collision freedom, exact range (union of 144-byte group images), ownership, group-granular invalidation exactness.
static void ModelR(const Surface& s) {
  const uint32_t unit_log2 = (4u - s.bpb_log2) < 3u ? (4u - s.bpb_log2) : 3u;
  const uint32_t n = 1u << unit_log2;
  const uint32_t unit_bytes = n << s.bpb_log2;  // 16
  const uint32_t group_guest = 4 * unit_bytes;  // 64
  CHECK(unit_bytes == 16 && group_guest == g6p89::kGroupGuestBytes);
  std::set<uint64_t> seen;
  std::set<uint64_t> groups;
  uint32_t hw = s.width * 3 / 2, hh = s.height * 3 / 2;
  for (uint32_t hy = 0; hy < hh; ++hy) {
    for (uint32_t hx = 0; hx < hw; ++hx) {
      uint32_t a = g6p89::RationalScaledOffset2D(hx, hy, s.pitch, s.bpb_log2);
      for (uint32_t b = 0; b < (1u << s.bpb_log2); ++b) {
        CHECK(seen.insert(uint64_t(a) + b).second);
      }
      // Ownership: the guest pixel under the host pixel (3:2 nearest-left) belongs to the group this byte is in.
      uint32_t gx = hx * 2 / 3, gy = hy * 2 / 3;
      uint32_t guest = g6p89::TiledOffset2D(gx, gy, s.pitch, s.bpb_log2);
      CHECK(a / g6p89::kGroupHostBytes == guest / group_guest);
    }
  }
  for (uint32_t gy = 0; gy < s.height; gy += 2) {
    for (uint32_t gx = 0; gx < s.width; gx += 2 * n) {
      uint32_t g = g6p89::TiledOffset2D(gx, gy, s.pitch, s.bpb_log2);
      CHECK(g % group_guest == 0);
      // The 2N x 2 guest group is one contiguous 64-byte run.
      std::set<uint32_t> run;
      for (uint32_t y = gy; y < gy + 2; ++y)
        for (uint32_t x = gx; x < gx + 2 * n; ++x)
          for (uint32_t b = 0; b < (1u << s.bpb_log2); ++b) run.insert(g6p89::TiledOffset2D(x, y, s.pitch, s.bpb_log2) + b);
      CHECK(run.size() == group_guest && *run.begin() == g && *run.rbegin() == g + group_guest - 1);
      groups.insert(g / group_guest);
    }
  }
  std::set<uint64_t> expected;
  for (uint64_t g : groups)
    for (uint64_t b = g * g6p89::kGroupHostBytes; b < (g + 1) * g6p89::kGroupHostBytes; ++b) expected.insert(b);
  CHECK(seen == expected);
  // Invalidation: for guest byte ranges, [first, end) holds exactly the host bytes of the groups the range touches.
  const uint32_t starts[] = {0, 1, 63, 64, 100, 4095, 4096, 12345, 65536};
  const uint32_t lengths[] = {1, 63, 64, 65, 1000, 4096};
  for (uint32_t st : starts) {
    for (uint32_t len : lengths) {
      uint64_t f, e;
      g6p89::Scale::RationalRange(st, len, f, e);
      for (uint64_t g : groups) {
        bool touches = uint64_t(st) < (g + 1) * group_guest && g * group_guest < uint64_t(st) + len;
        bool inside = g * g6p89::kGroupHostBytes >= f && (g + 1) * g6p89::kGroupHostBytes <= e;
        bool disjoint = (g + 1) * g6p89::kGroupHostBytes <= f || g * g6p89::kGroupHostBytes >= e;
        CHECK(touches ? inside : disjoint);
      }
    }
  }
}

// Distinct guest surfaces (disjoint guest ranges) never share host bytes.
static void NoAliasing() {
  uint64_t f1, e1, f2, e2;
  g6p89::Scale::RationalRange(0x1E749000u, 3768320u, f1, e1);  // depth 1280x736 (census base)
  g6p89::Scale::RationalRange(0x1EAE1000u, 3768320u, f2, e2);  // colour 1280x736
  CHECK(e1 <= f2 || e2 <= f1);
  g6p89::Scale::RationalRange(0x1E349000u, 4194304u, f2, e2);  // shadow 1024x1024
  CHECK(e2 <= f1 || e1 <= f2);
}

// G6-P92: the 3:2 resolve extent rule and the dispatch it implies (GetCopyShader at 3:2: ceil(host / 64) x
// ceil(host / 4) groups of 64x4 host pixels; threads of 8 pixels with an X bound at (width_div_8 x 3) >> 1).
static void ResolveExtent() {
  CHECK(g6p89::kResolveGroupHeightLog2 == 2 && g6p89::kResolveThreadWidthPixels == 8);
  CHECK(g6p89::ResolveExtentExact(80, 45));                                     // 640x360 (knaar_10)
  CHECK(g6p89::ResolveExtentExact(80, 44) && g6p89::ResolveExtentExact(80, 46));  // 640x352 / 640x368
  CHECK(g6p89::ResolveExtentExact(160, 90) && g6p89::ResolveExtentExact(128, 128));  // 1280x720 / 1024x1024
  CHECK(!g6p89::ResolveExtentExact(81, 45) && !g6p89::ResolveExtentExact(81, 44) && !g6p89::ResolveExtentExact(1, 2));
  for (uint32_t w8 = 0; w8 <= 1024; ++w8) {
    for (uint32_t h8 = 0; h8 <= 1024; ++h8) {
      bool exact = g6p89::ResolveExtentExact(w8, h8);
      CHECK(exact == (w8 % 2 == 0));
      if (!exact) continue;
      g6p89::Scale r{3, 3, 2};
      uint32_t host_w = r.X(w8 * 8), host_h = r.Y(h8 * 8);
      uint32_t groups_x = (host_w + 63) >> 6;
      uint32_t groups_y = (host_h + 3) >> g6p89::kResolveGroupHeightLog2;
      // Rows dispatched = rows of the rectangle (no Y bound needed); threads past the X bound cover nothing, and the
      // threads inside it cover exactly the host width.
      CHECK((groups_y << g6p89::kResolveGroupHeightLog2) == host_h);
      CHECK(((w8 * 3) >> 1) * 8 == host_w && groups_x * 8 >= (w8 * 3) >> 1);
      // The SDK's 8-row groups would be exact here only for an even height_div_8 (G6-P89's old refusal).
      CHECK((((host_h + 7) >> 3) << 3 == host_h) == (h8 % 2 == 0));
    }
  }
}

static uint64_t Checksum() {
  uint64_t h = 1469598103934665603ull;
  for (uint32_t hy = 0; hy < 1080; ++hy)
    for (uint32_t hx = 0; hx < 1920; ++hx) {
      h ^= g6p89::RationalScaledOffset2D(hx, hy, 1280, 2);
      h *= 1099511628211ull;
    }
  return h;
}

static void EnableGate() {
  // Default: off.
  CHECK(!g6p89::ParseEnable(nullptr, nullptr, nullptr));
  CHECK(!g6p89::ParseEnable("", nullptr, nullptr));
  CHECK(!g6p89::ParseEnable(nullptr, "1", nullptr));
  // Primary development opt-in (R3HD_RENDER_SCALE_3_2=1): works with or without R3HD_NONINTRUSIVE.
  CHECK(g6p89::ParseEnable("1", nullptr, nullptr));
  CHECK(g6p89::ParseEnable("1", "1", nullptr));
  CHECK(g6p89::ParseEnable("1", "1", "0"));
  // Strict "1" only; explicit non-empty value overrides legacy test flag.
  CHECK(!g6p89::ParseEnable("0", "1", "1"));
  CHECK(!g6p89::ParseEnable("2", "1", "1"));
  CHECK(!g6p89::ParseEnable("true", "1", "1"));
  // Legacy hidden-test alias (R3HD_NONINTRUSIVE + R3HD_TEST_G6P89_SCALE_3_2=1) when primary is unset/empty.
  CHECK(g6p89::ParseEnable(nullptr, "1", "1"));
  CHECK(g6p89::ParseEnable("", "1", "1"));
  CHECK(!g6p89::ParseEnable(nullptr, nullptr, "1"));
  CHECK(!g6p89::ParseEnable(nullptr, "1", "0"));
}

int main(int argc, char** argv) {
  if (argc > 1 && std::strcmp(argv[1], "refuse") == 0) {
    g6p89::Scale r{3, 3, 2};
    volatile uint32_t odd = 1281;
    uint32_t v = r.X(odd);  // must not return
    std::printf("NOT REFUSED %u\n", v);
    return 0;
  }
  EnableGate();
  IntegerIdentity();
  RationalValues();
  ModelR({1280, 736, 1280, 2});
  ModelR({1024, 1024, 1024, 2});
  ModelR({640, 384, 640, 2});
  ModelR({640, 360, 640, 2});  // G6-P92: the knaar_10 640x360 destination (180 whole 2-row groups)
  ModelR({256, 64, 256, 3});
  ModelR({128, 64, 128, 4});
  NoAliasing();
  ResolveExtent();
  uint64_t c = Checksum();
  std::printf("G6P89_HOST_TEST %s checksum=%016llx failures=%d\n", g_fail ? "FAIL" : "PASS",
              (unsigned long long)c, g_fail);
  return g_fail ? 1 : 0;
}
