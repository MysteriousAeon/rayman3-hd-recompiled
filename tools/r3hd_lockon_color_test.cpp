// HD+ out-of-range lock-on colour restoration (D-221): deterministic checks of tools/r3hd_lockon_color.h. Host-only;
// synthetic buffers. With one argument (the local fix.btf, private; passed by tools/build_lockon_test.bat when
// available) the whole file is also read through the overlay in uneven pieces: outside the page every byte is the
// file's own, and the served page hashes to the table's restored values.
#include "r3hd_lockon_color.h"
#include <algorithm>
#include <cstdio>
#include <iterator>

static int checks = 0, failures = 0;
static void Check(bool ok, const char* what) {
  ++checks;
  if (!ok) {
    ++failures;
    std::printf("FAIL %s\n", what);
  }
}

struct Rgb { double r, g, b; bool transparent; };
static Rgb Colour(uint16_t c) { return {double(c >> 11), double((c >> 5) & 63), double(c & 31), false}; }
static Rgb Mix(Rgb a, Rgb b, double wa, double wb, double d) {
  return {(wa * a.r + wb * b.r) / d, (wa * a.g + wb * b.g) / d, (wa * a.b + wb * b.b) / d, false};
}
// Texel k of a stored block, as a decoder sees it (palette from the endpoint order).
static Rgb Texel(const uint8_t* s, int k, bool map_endpoints) {
  uint16_t c0 = uint16_t(s[0] << 8 | s[1]), c1 = uint16_t(s[2] << 8 | s[3]);
  const bool four = c0 > c1;
  if (map_endpoints) c0 = r3hdlockon::Map565(c0), c1 = r3hdlockon::Map565(c1);
  const Rgb a = Colour(c0), b = Colour(c1);
  const int i = (s[4 + k / 4] >> (2 * (k % 4))) & 3;
  if (i == 0) return a;
  if (i == 1) return b;
  if (four) return i == 2 ? Mix(a, b, 2, 1, 3) : Mix(a, b, 1, 2, 3);
  return i == 2 ? Mix(a, b, 1, 1, 2) : Rgb{0, 0, 0, true};
}
static bool Same(Rgb x, Rgb y) {
  return x.transparent == y.transparent && x.r == y.r && x.g == y.g && x.b == y.b;
}

int main(int argc, char** argv) {
  using namespace r3hdlockon;
  Check(!Selected(nullptr) && !Selected("") && !Selected("original") && !Selected("1") && !Selected("Restored"),
        "the title's data unless the value is exactly 'restored'");
  Check(Selected("restored"), "'restored' selects the restoration");
  Check(Map565(0) == 0 && Map565(0x07E0) == 0 && Map565(0x001F) == 0, "no red: black");
  // Reference values shared with tools/r3hd_lockon_color.py selftest: full red clamps blue, HD peak is blue-dominant.
  Check(Map565(0xF800) == uint16_t((((18 * 31 + 127) / 255) << 11) | (((184 * 63 + 127) / 255) << 5) | 31),
        "full red maps to the clamped ramp");
  const uint16_t peak = Map565(uint16_t(21 << 11));
  Check((peak & 31) == 31 && ((peak >> 5) & 63) >= 28 && ((peak >> 5) & 63) <= 32 && (peak >> 11) <= 2,
        "HD peak intensity lands on the PC blue core");
  bool monotonic = true, ignores = true;
  for (uint16_t r5 = 0; r5 < 32; ++r5) {
    for (uint16_t x : {uint16_t(0x7E0), uint16_t(0x1F), uint16_t(0x5A5)})
      ignores &= Map565(uint16_t(r5 << 11 | x)) == Map565(uint16_t(r5 << 11));
    if (r5) {
      const uint16_t a = Map565(uint16_t((r5 - 1) << 11)), b = Map565(uint16_t(r5 << 11));
      monotonic &= (a & 31) <= (b & 31) && ((a >> 5) & 63) <= ((b >> 5) & 63) && (a >> 11) <= (b >> 11);
    }
  }
  Check(monotonic, "ramp monotonic in red intensity");
  Check(ignores, "input green and blue carry no hue");

  // Every block keeps its mode, and every texel decodes to the mapped palette's texel (exact, no recompression).
  uint32_t seed = 54321;
  bool mode = true, texels = true, deterministic = true;
  int swapped = 0, equal = 0, three = 0;
  for (int n = 0; n < 200000; ++n) {
    uint8_t s[8], t[8];
    for (auto& x : s) seed = seed * 1664525u + 1013904223u, x = uint8_t(seed >> 24);
    if (n % 7 == 0) s[2] = s[0], s[3] = uint8_t(s[1] ^ (n & 1));  // near-equal endpoints
    std::memcpy(t, s, 8);
    RestoreBlock(t);
    const uint16_t c0 = uint16_t(s[0] << 8 | s[1]), c1 = uint16_t(s[2] << 8 | s[3]);
    const uint16_t n0 = uint16_t(t[0] << 8 | t[1]), n1 = uint16_t(t[2] << 8 | t[3]);
    const bool collapsed = Map565(c0) == Map565(c1);
    mode &= (c0 > c1) == (n0 > n1) || collapsed;
    swapped += n0 != Map565(c0);
    equal += collapsed;
    three += c0 <= c1;
    for (int k = 0; k < 16; ++k) texels &= Same(Texel(s, k, true), Texel(t, k, false));
    uint8_t u[8];
    std::memcpy(u, s, 8);
    RestoreBlock(u);
    deterministic &= std::memcmp(u, t, 8) == 0;
  }
  Check(mode, "block mode (four colours / three and transparent) kept");
  Check(texels, "every texel is the mapped palette's texel");
  Check(deterministic, "deterministic");
  // The map is monotonic in red, so endpoint order never reverses: the swap branch is a guard, never taken.
  Check(swapped == 0 && equal > 0 && three > 0, "no order swaps; covers collapsed endpoints and three-colour blocks");

  std::vector<uint8_t> odd(12);
  Check(!RestoreBlob(odd), "a blob that is not whole blocks is refused");

  // Table: the shared fix bundle with exactly the far-indicator page; the normal reticle pages are not listed.
  bool table = kBundleCount == 1 && std::strcmp(kBundles[0].file, "fix.btf") == 0 && kBundles[0].page_count == 1;
  const Page& pg = kBundles[0].pages[0];
  table &= std::strcmp(pg.name, "ago_targetfar.dds") == 0 && pg.size[0] == 0x2000 && pg.size[1] == 0x6000 &&
           pg.offset[0] + pg.size[0] <= pg.offset[1] && pg.offset[1] + pg.size[1] <= kBundles[0].size;
  Check(table, "table: fix.btf, ago_targetfar only, base 8 KiB + chain 24 KiB");
  Check(FindBundle("FIX.BTF") && !FindBundle("fix.bhf") && !FindBundle("menu_20_2.btf"),
        "file names compared without case; other files untouched");

  // Overlay: only the overlapping part of a read is replaced.
  std::vector<uint8_t> buf(16, 0xAA), data(8, 0x11);
  Check(Overlay(buf.data(), 100, 16, data.data(), 110, 8) == 6 && buf[9] == 0xAA && buf[10] == 0x11 && buf[15] == 0x11,
        "overlay: partial overlap at the end of a read");
  Check(Overlay(buf.data(), 100, 16, data.data(), 200, 8) == 0, "overlay: no overlap, nothing replaced");

  // A file of the wrong size is refused, the read stays as it is.
  {
    const auto tmp = std::filesystem::temp_directory_path() / "fix.btf";
    { std::ofstream f(tmp, std::ios::binary); f << "short"; }
    std::vector<uint8_t> read(0x10000, 0x5A), copy = read;
    const size_t got = AfterRead(tmp, pg.offset[0] & ~uint64_t(0xFFFF), read.data(), read.size(), true);
    Check(got == 0 && read == copy, "wrong file size: refused, read unchanged");
    std::filesystem::remove(tmp);
    state().slots.clear();
  }
  // Not enabled and not forced: nothing happens.
  {
    std::vector<uint8_t> read(64, 0x5A), copy = read;
    Check(AfterRead("fix.btf", pg.offset[0], read.data(), read.size()) == 0 && read == copy,
          "switch off: read unchanged");
  }

  if (argc > 1) {
    const std::filesystem::path path = argv[1];
    const Bundle* bundle = FindBundle(path.filename());
    Check(bundle != nullptr, "argument is a listed bundle");
    if (bundle) {
      std::ifstream f(path, std::ios::binary);
      std::vector<uint8_t> file((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
      std::vector<uint8_t> served(file.size());
      size_t replaced = 0;
      for (uint64_t at = 0, step = 4093; at < file.size(); at += step, step = step * 3 % 65521 + 1) {
        const size_t n = size_t(std::min<uint64_t>(step, file.size() - at));
        std::memcpy(served.data() + at, file.data() + at, n);
        replaced += AfterRead(path, at, served.data() + at, n, true);
      }
      bool outside = true, hashes = true;
      std::vector<bool> in(file.size());
      for (size_t p = 0; p < bundle->page_count; ++p)
        for (int b = 0; b < 2; ++b) {
          const Page& q = bundle->pages[p];
          for (uint64_t i = q.offset[b]; i < q.offset[b] + q.size[b]; ++i) in[size_t(i)] = true;
          hashes &= Fnv1a(served.data() + q.offset[b], size_t(q.size[b])) == q.restored[b];
          hashes &= Fnv1a(file.data() + q.offset[b], size_t(q.size[b])) == q.stored[b];
        }
      for (size_t i = 0; i < file.size(); ++i) outside &= in[i] || served[i] == file[i];
      Check(replaced == bundle->page_count * (0x2000 + 0x6000), "file: exactly the listed page served");
      Check(hashes, "file: stored and served page have the table hashes");
      Check(outside, "file: every other byte is the file's own");
    }
  }

  std::printf("R3HD_LOCKON_COLOR_TEST %s checks=%d failures=%d\n", failures ? "FAIL" : "PASS", checks, failures);
  return failures ? 1 : 0;
}
