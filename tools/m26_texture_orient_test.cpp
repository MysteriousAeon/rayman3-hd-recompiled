// M26 (D-058): the texture orientation correction, deterministic checks. Host-only; every buffer is synthetic.
// With one argument (the local `fact_55_2.btf`, private; passed by tools/m26_regression.py when the file exists)
// the whole file is also read through the overlay in uneven pieces and compared with the file itself.
#include "m26_texture_orient.h"
#include <cstdio>

static int checks = 0, failures = 0;
static void Check(bool ok, const char* what) {
  ++checks;
  if (!ok) {
    ++failures;
    std::printf("FAIL %s\n", what);
  }
}

// Alpha and colour index of each of the 16 texels of a stored block (index only: endpoints do not move).
static void Indices(const uint8_t* s, int alpha[16], int colour[16]) {
  uint8_t w[16];
  for (int i = 0; i < 16; ++i) w[i] = s[i ^ 1];
  uint64_t a = 0;
  for (int i = 0; i < 6; ++i) a |= uint64_t(w[2 + i]) << (8 * i);
  for (int t = 0; t < 16; ++t) {
    alpha[t] = int((a >> (3 * t)) & 7);
    colour[t] = (w[12 + t / 4] >> (2 * (t % 4))) & 3;
  }
}

static std::vector<uint8_t> Pattern(size_t size, uint32_t seed) {
  std::vector<uint8_t> v(size);
  for (size_t i = 0; i < size; ++i) {
    seed = seed * 1664525u + 1013904223u;
    v[i] = uint8_t(seed >> 24);
  }
  return v;
}

static std::vector<std::string> lines;
static void Collect(const char* line) { lines.emplace_back(line); }

int main(int argc, char** argv) {
  using namespace m26tex;
  Check(!Selected(nullptr) && !Selected("") && !Selected("original") && !Selected("1") && !Selected("Corrected"),
        "the title's data unless the value is exactly 'corrected'");
  Check(Selected("corrected"), "'corrected' selects the correction");

  // One block: texel rows reverse, endpoints stay, twice is the identity.
  std::vector<uint8_t> block = Pattern(16, 7);
  std::vector<uint8_t> mirrored = block;
  MirrorBlock(mirrored.data());
  int a0[16], c0[16], a1[16], c1[16];
  Indices(block.data(), a0, c0);
  Indices(mirrored.data(), a1, c1);
  bool rows = true;
  for (int t = 0; t < 16; ++t) rows &= a1[t] == a0[(3 - t / 4) * 4 + t % 4] && c1[t] == c0[(3 - t / 4) * 4 + t % 4];
  Check(rows, "block: every texel index moves to the mirrored row, same column");
  bool ends = true;
  for (int i : {0, 1, 8, 9, 10, 11}) ends &= mirrored[size_t(i)] == block[size_t(i)];
  Check(ends, "block: alpha and colour endpoints untouched");
  MirrorBlock(mirrored.data());
  Check(mirrored == block, "block: mirror twice is the identity");

  // One level inside a wider area: block rows reverse inside the level, nothing outside it changes.
  const Level level = {0, 0x40, 8, 2, 1, 4};
  std::vector<uint8_t> area = Pattern(0x40 + 8 * 6 * kBlock, 99);
  std::vector<uint8_t> blob = area;
  Check(MirrorLevel(blob, level), "level: accepted inside the blob");
  bool inside = true, outside = true;
  for (uint32_t j = 0; j < 6; ++j)
    for (uint32_t k = 0; k < 8; ++k) {
      const size_t at = 0x40 + (size_t(j) * 8 + k) * kBlock;
      const bool in = j >= 1 && j < 5 && k >= 2 && k < 6;
      if (!in) {
        outside &= std::memcmp(&blob[at], &area[at], kBlock) == 0;
        continue;
      }
      std::vector<uint8_t> expect(&area[0x40 + (size_t(1 + (4 - j)) * 8 + k) * kBlock],
                                  &area[0x40 + (size_t(1 + (4 - j)) * 8 + k) * kBlock] + kBlock);
      MirrorBlock(expect.data());
      inside &= std::memcmp(&blob[at], expect.data(), kBlock) == 0;
    }
  Check(inside, "level: block (x, y) holds the mirrored block of (x, n - 1 - y)");
  Check(outside && std::memcmp(blob.data(), area.data(), 0x40) == 0, "level: bytes outside the level untouched");
  MirrorLevel(blob, level);
  Check(blob == area, "level: mirror twice is the identity");
  std::vector<uint8_t> small_blob(0x40 + 8 * 4 * kBlock);
  Check(!MirrorLevel(small_blob, level), "level: refused when it does not fit the blob");
  Check(!MirrorLevel(blob, Level{0, 0, 4, 2, 0, 4}), "level: refused when wider than its area");

  // The page layout: ten levels 128 .. 1 blocks, inside the two blobs, no two levels sharing a block.
  uint32_t expect_n[] = {128, 64, 32, 16, 8, 4, 2, 1, 1, 1};
  bool sizes = kPage512Dxt5Levels == 10, fits = true, disjoint = true;
  std::vector<uint8_t> used[2] = {std::vector<uint8_t>(0x40000 / kBlock), std::vector<uint8_t>(0x20000 / kBlock)};
  for (size_t i = 0; i < kPage512Dxt5Levels && sizes; ++i) {
    const Level& l = kPage512Dxt5[i];
    sizes &= l.n == expect_n[i] && l.blob == (i ? 1u : 0u) && l.base % 0x1000 == 0;
    for (uint32_t j = 0; j < l.n; ++j)
      for (uint32_t k = 0; k < l.n; ++k) {
        const size_t b = l.base / kBlock + size_t(l.y + j) * l.pitch + l.x + k;
        if (b >= used[l.blob].size()) { fits = false; continue; }
        disjoint &= !used[l.blob][b];
        used[l.blob][b] = 1;
      }
  }
  Check(sizes, "layout: ten levels, 512 texels down to 1, level 0 alone in the first blob, 4K aligned areas");
  Check(fits && disjoint, "layout: every level inside its blob, no block in two levels");
  size_t whole = 0;
  for (uint8_t u : used[0]) whole += u;
  Check(whole == used[0].size(), "layout: the base level is the whole first blob");

  // A page mirrored twice is itself; mirrored once it differs in both blobs.
  std::vector<uint8_t> page[2] = {Pattern(0x40000, 1), Pattern(0x20000, 2)};
  const std::vector<uint8_t> original[2] = {page[0], page[1]};
  Check(MirrorPage(page, kPage512Dxt5, kPage512Dxt5Levels) && page[0] != original[0] && page[1] != original[1],
        "page: both blobs change");
  size_t untouched = 0;
  for (size_t b = 0; b < used[1].size(); ++b)
    if (!used[1][b]) untouched += std::memcmp(&page[1][b * kBlock], &original[1][b * kBlock], kBlock) == 0;
  size_t padding = 0;
  for (uint8_t u : used[1]) padding += !u;
  Check(untouched == padding, "page: padding between mip levels untouched");
  MirrorPage(page, kPage512Dxt5, kPage512Dxt5Levels);
  Check(page[0] == original[0] && page[1] == original[1], "page: mirror twice is the identity");
  std::vector<uint8_t> short_page[2] = {Pattern(0x40000, 1), Pattern(0x1C000, 2)};
  Check(!MirrorPage(short_page, kPage512Dxt5, kPage512Dxt5Levels), "page: refused when a blob is short");

  // Overlay arithmetic.
  std::vector<uint8_t> data(100, 0xAA), buffer(50, 0x11);
  Check(Overlay(buffer.data(), 1000, 50, data.data(), 2000, 100) == 0 && buffer[0] == 0x11, "overlay: disjoint read");
  Check(Overlay(buffer.data(), 1980, 50, data.data(), 2000, 100) == 30 && buffer[19] == 0x11 && buffer[20] == 0xAA &&
            buffer[49] == 0xAA, "overlay: read that ends inside the page");
  std::fill(buffer.begin(), buffer.end(), uint8_t(0x11));
  Check(Overlay(buffer.data(), 2080, 50, data.data(), 2000, 100) == 20 && buffer[19] == 0xAA && buffer[20] == 0x11,
        "overlay: read that starts inside the page");
  std::vector<uint8_t> big(300, 0x11);
  Check(Overlay(big.data(), 1900, 300, data.data(), 2000, 100) == 100 && big[99] == 0x11 && big[100] == 0xAA &&
            big[199] == 0xAA && big[200] == 0x11, "overlay: read that contains the page");

  // Table shape and the fail-closed path: a file with the listed name but other contents is returned as read.
  Check(kBundleCount == 1 && kBundles[0].page_count == 4, "table: one bundle, four pages");
  bool table = true;
  for (size_t p = 0; p < kBundles[0].page_count; ++p) {
    const Page& g = kBundles[0].pages[p];
    table &= g.size[0] == 0x40000 && g.size[1] == 0x20000 && g.offset[1] == g.offset[0] + g.size[0] &&
             g.offset[1] + g.size[1] <= kBundles[0].size && g.stored[0] != g.corrected[0] && g.stored[1] != g.corrected[1];
    for (size_t q = 0; q < p; ++q) table &= kBundles[0].pages[q].offset[0] != g.offset[0];
  }
  Check(table, "table: page ranges inside the file, distinct, stored and corrected hashes differ");
  Check(FindBundle("FACT_55_2.BTF") == &kBundles[0] && !FindBundle("fact_55_2.bhf") && !FindBundle("fact_50_2.btf") &&
            !FindBundle("xfact_55_2.btf"), "table: exact file name, any case");
  Check(!FindBundle(std::filesystem::path(L"fact_55_2.bt\u0192")) && !FindBundle(std::filesystem::path(L"\u00C7etin.btf")),
        "table: a name outside ASCII does not match and does not throw");
  Check(Fnv1a(reinterpret_cast<const uint8_t*>("a"), 1) == 0xAF63DC4C8601EC8Cull, "hash: FNV-1a 64 reference value");

  state().log = &Collect;
  const auto dir = std::filesystem::temp_directory_path() / "m26_texture_orient_test";
  std::filesystem::create_directories(dir);
  const auto fake = dir / "fact_55_2.btf";
  { std::ofstream f(fake, std::ios::binary); f.write("short", 5); }
  std::vector<uint8_t> read_buffer(0x1000, 0x5A);
  Check(AfterRead(fake, 0x444000, read_buffer.data(), read_buffer.size(), true) == 0 && read_buffer[0] == 0x5A &&
            read_buffer[0xFFF] == 0x5A, "read: a file of another size is returned as read");
  Check(AfterRead(dir / "other.btf", 0x444000, read_buffer.data(), read_buffer.size(), true) == 0, "read: other files ignored");
  Check(AfterRead(fake, 0, read_buffer.data(), read_buffer.size(), true) == 0, "read: ranges outside every page ignored");
  Check(AfterRead(fake, 0x444000, read_buffer.data(), read_buffer.size(), false) == 0, "read: nothing without the switch");
  bool refused = false;
  for (const auto& l : lines) refused |= l.find("page=fac_sbire03.dds state=refused_file_size") != std::string::npos;
  Check(refused && lines.size() == 1, "read: one log line for the refused page");
  std::error_code ec;
  std::filesystem::remove_all(dir, ec);

  if (argc > 1) {  // the local target file: whole-file read through the overlay, uneven pieces
    state().slots.clear();
    lines.clear();
    const std::filesystem::path real = argv[1];
    std::ifstream f(real, std::ios::binary);
    std::vector<uint8_t> file((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    Check(file.size() == kBundles[0].size, "target: file size as listed");
    std::vector<uint8_t> seen(file.size());
    size_t at = 0, piece = 0x7001, replaced = 0;
    while (at < file.size()) {
      const size_t n = std::min(piece, file.size() - at);
      std::memcpy(&seen[at], &file[at], n);
      replaced += AfterRead(real, at, &seen[at], n, true);
      at += n;
      piece = piece * 3 % 0x51003 + 0x333;
    }
    Check(replaced == 4 * 0x60000, "target: exactly the four pages' bytes replaced");
    size_t outside_diff = 0;
    bool hashes = true, back = true;
    std::vector<uint8_t> in_page(file.size());
    for (size_t p = 0; p < 4; ++p) {
      const Page& g = kBundles[0].pages[p];
      std::vector<uint8_t> again[2];
      for (int b = 0; b < 2; ++b) {
        std::fill(in_page.begin() + long(g.offset[b]), in_page.begin() + long(g.offset[b] + g.size[b]), uint8_t(1));
        hashes &= Fnv1a(&seen[g.offset[b]], size_t(g.size[b])) == g.corrected[b] &&
                  Fnv1a(&file[g.offset[b]], size_t(g.size[b])) == g.stored[b];
        again[b].assign(&seen[g.offset[b]], &seen[g.offset[b]] + g.size[b]);
      }
      MirrorPage(again, kPage512Dxt5, kPage512Dxt5Levels);
      for (int b = 0; b < 2; ++b) back &= std::memcmp(again[b].data(), &file[g.offset[b]], size_t(g.size[b])) == 0;
    }
    for (size_t i = 0; i < file.size(); ++i) outside_diff += !in_page[i] && seen[i] != file[i];
    Check(hashes, "target: stored and corrected hashes of the four pages as listed");
    Check(back, "target: mirroring the served bytes again gives the file's bytes");
    Check(outside_diff == 0, "target: every byte outside the four pages equals the file");
    size_t corrected = 0, served = 0;
    for (const auto& l : lines) {
      corrected += l.find("state=corrected") != std::string::npos;
      served += l.find("served_bytes=393216") != std::string::npos;
    }
    Check(corrected == 4 && served == 4 && lines.size() == 8, "target: one state line and one served line per page");
  }

  std::printf("M26_TEXTURE_ORIENT_TEST %s checks=%d failures=%d%s\n", failures ? "FAIL" : "PASS", checks, failures,
              argc > 1 ? " target=1" : "");
  return failures ? 1 : 0;
}
