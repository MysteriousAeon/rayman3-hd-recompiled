// M26 (D-058): optional orientation correction for texture pages that the Xbox 360 HD release stores the other
// way up from the meshes that use them. Installed as include/rex/m26_texture_orient.h by
// tools/m26_runtime_patch.py and used by the host file read path (HostPathFile::ReadSync) only.
//
// What the title has (RE_NOTES "M26"): its bundles store texture pages bottom row first and its meshes' v
// coordinates count on that. The four atlases of the Robo-Pirate statues in `fact_55` (`fac_sbire01..04`) are
// stored top row first, so every statue part samples the mirror cell of its page. That is the HD release's own
// data (class B: inherited content defect), so the default leaves it alone.
//
// With R3HD_TEXTURE_ORIENT=corrected a read of a listed bundle file returns the listed pages mirrored top to
// bottom: block rows reversed and the four texel rows inside each DXT5 block reversed, for the base level and for
// every mip level in the console's own mip layout. The operation is exact (no decode, no recompression) and is
// its own inverse. Nothing is written to disk, to guest memory outside the buffer the title asked to have filled,
// or to any other file. A page is corrected only when the file has the listed size and the page's stored bytes
// have the listed hash, and the result has the listed hash; otherwise the read is returned as it is.
// The table carries offsets, sizes and hashes only: no texel of the title is in this file.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>
#include <system_error>
#include <vector>

namespace m26tex {

// One mip level inside a blob: `n` x `n` blocks at block (x, y) of an area that is `pitch` blocks wide and
// starts at byte `base`. Blob 0 is the base level, blob 1 the mip chain.
struct Level {
  uint32_t blob, base, pitch, x, y, n;
};
// 512 x 512 DXT5 with a full chain, as the console lays it out: 256 and 128 at their own width, 64 and 32 in
// areas 32 blocks wide, then the packed tail (16, 8, 4 beside each other on the first block row; 2 and 1 below).
constexpr Level kPage512Dxt5[] = {
    {0, 0x00000, 128, 0, 0, 128}, {1, 0x00000, 64, 0, 0, 64}, {1, 0x10000, 32, 0, 0, 32}, {1, 0x14000, 32, 0, 0, 16},
    {1, 0x18000, 32, 0, 0, 8},    {1, 0x1C000, 32, 4, 0, 4},  {1, 0x1C000, 32, 2, 0, 2},  {1, 0x1C000, 32, 1, 0, 1},
    {1, 0x1C000, 32, 0, 2, 1},    {1, 0x1C000, 32, 0, 1, 1}};
constexpr size_t kPage512Dxt5Levels = sizeof(kPage512Dxt5) / sizeof(Level);
constexpr uint32_t kBlock = 16;

struct Page {
  const char* name;        // bundle entry (metadata only)
  uint64_t offset[2];      // base level, mip chain
  uint64_t size[2];
  uint64_t stored[2];      // FNV-1a 64 of the title's bytes
  uint64_t corrected[2];   // FNV-1a 64 after the mirror
};
struct Bundle {
  const char* file;        // file name, compared without case
  uint64_t size;
  const Page* pages;
  size_t page_count;
};

constexpr Page kFact55Pages[] = {
    {"fac_sbire03.dds", {0x444000, 0x484000}, {0x40000, 0x20000},
     {0x3115A19F686B76B5ull, 0xB22BD3B80BA3CC8Aull}, {0x9FAFE4C28197638Aull, 0xE1924228DB5D0B71ull}},
    {"fac_sbire02.dds", {0x4D4000, 0x514000}, {0x40000, 0x20000},
     {0xB68D2101D467809Bull, 0xFE98F6E748D38972ull}, {0x807BE6455D85B167ull, 0x9372588B5BC8EB36ull}},
    {"fac_sbire01.dds", {0x534000, 0x574000}, {0x40000, 0x20000},
     {0x22935B090232834Full, 0x42BA674A333D811Cull}, {0xFCF05EDB1EB419CAull, 0xEDB9BF1116208B7Bull}},
    {"fac_sbire04.dds", {0x594000, 0x5D4000}, {0x40000, 0x20000},
     {0x99DDC6F65C1A3480ull, 0x2988D42582897DAEull}, {0xB3384346D815F514ull, 0x7E2F5DF1E310F3C5ull}},
};
constexpr Bundle kBundles[] = {
    {"fact_55_2.btf", 12722176, kFact55Pages, sizeof(kFact55Pages) / sizeof(Page)},
};
constexpr size_t kBundleCount = sizeof(kBundles) / sizeof(Bundle);

// "corrected" selects the correction; anything else, or no variable, is the title's own data.
inline bool Selected(const char* value) { return value && std::strcmp(value, "corrected") == 0; }
inline bool Enabled() {
  static const bool on = Selected(std::getenv("R3HD_TEXTURE_ORIENT"));
  return on;
}

inline uint64_t Fnv1a(const uint8_t* data, size_t size) {
  uint64_t h = 0xCBF29CE484222325ull;
  for (size_t i = 0; i < size; ++i) h = (h ^ data[i]) * 0x100000001B3ull;
  return h;
}

// One DXT5 block as the bundle stores it (every 16-bit word byte-swapped), texel rows 0..3 -> 3..0.
inline void MirrorBlock(uint8_t* s) {
  auto at = [s](int i) -> uint8_t& { return s[i ^ 1]; };  // byte i of the little-endian block
  const uint32_t a = at(2) | (at(3) << 8) | (at(4) << 16);   // alpha index rows 0, 1 (12 bits each)
  const uint32_t c = at(5) | (at(6) << 8) | (at(7) << 16);   // alpha index rows 2, 3
  const uint32_t a2 = (c >> 12) | ((c & 0xFFF) << 12);
  const uint32_t c2 = (a >> 12) | ((a & 0xFFF) << 12);
  at(2) = uint8_t(a2), at(3) = uint8_t(a2 >> 8), at(4) = uint8_t(a2 >> 16);
  at(5) = uint8_t(c2), at(6) = uint8_t(c2 >> 8), at(7) = uint8_t(c2 >> 16);
  const uint8_t r0 = at(12), r1 = at(13), r2 = at(14), r3 = at(15);  // colour index rows
  at(12) = r3, at(13) = r2, at(14) = r1, at(15) = r0;
}

// False when the level does not lie inside the blob (nothing is changed then).
inline bool MirrorLevel(std::vector<uint8_t>& blob, const Level& l) {
  const uint64_t end = uint64_t(l.base) + (uint64_t(l.y + l.n - 1) * l.pitch + l.x + l.n) * kBlock;
  if (l.n == 0 || l.x + l.n > l.pitch || end > blob.size()) return false;
  auto row = [&](uint32_t j) { return blob.data() + l.base + (size_t(l.y + j) * l.pitch + l.x) * kBlock; };
  const size_t bytes = size_t(l.n) * kBlock;
  std::vector<uint8_t> tmp(bytes);
  for (uint32_t j = 0; j < l.n / 2; ++j) {
    std::memcpy(tmp.data(), row(j), bytes);
    std::memcpy(row(j), row(l.n - 1 - j), bytes);
    std::memcpy(row(l.n - 1 - j), tmp.data(), bytes);
  }
  for (uint32_t j = 0; j < l.n; ++j)
    for (uint32_t k = 0; k < l.n; ++k) MirrorBlock(row(j) + size_t(k) * kBlock);
  return true;
}

inline bool MirrorPage(std::vector<uint8_t> blobs[2], const Level* levels, size_t count) {
  for (size_t i = 0; i < count; ++i)
    if (levels[i].blob > 1 || !MirrorLevel(blobs[levels[i].blob], levels[i])) return false;
  return true;
}

// File name against a table name, without case and without converting the name to another encoding (a name
// outside the table's ASCII range simply does not match).
inline bool SameName(const std::filesystem::path::string_type& a, const char* b) {
  size_t i = 0;
  for (; i < a.size() && b[i]; ++i) {
    const auto x = a[i] >= 'A' && a[i] <= 'Z' ? a[i] + 32 : a[i];
    const auto y = b[i] >= 'A' && b[i] <= 'Z' ? b[i] + 32 : b[i];
    if (x != y) return false;
  }
  return i == a.size() && !b[i];
}
inline const Bundle* FindBundle(const std::filesystem::path& file_name) {
  for (size_t i = 0; i < kBundleCount; ++i)
    if (SameName(file_name.native(), kBundles[i].file)) return &kBundles[i];
  return nullptr;
}

// Lays the part of `data` (which starts at file offset `data_offset`) that falls inside the read
// [read_offset, read_offset + length) over `buffer`. Returns the bytes replaced.
inline size_t Overlay(uint8_t* buffer, uint64_t read_offset, size_t length, const uint8_t* data,
                      uint64_t data_offset, size_t data_size) {
  const uint64_t lo = read_offset > data_offset ? read_offset : data_offset;
  const uint64_t read_end = read_offset + length, data_end = data_offset + data_size;
  const uint64_t hi = read_end < data_end ? read_end : data_end;
  if (hi <= lo) return 0;
  std::memcpy(buffer + (lo - read_offset), data + (lo - data_offset), size_t(hi - lo));
  return size_t(hi - lo);
}

enum class PageState { kUnread, kCorrected, kRefusedSize, kRefusedRead, kRefusedStored, kRefusedResult };
inline const char* Name(PageState s) {
  switch (s) {
    case PageState::kCorrected: return "corrected";
    case PageState::kRefusedSize: return "refused_file_size";
    case PageState::kRefusedRead: return "refused_read";
    case PageState::kRefusedStored: return "refused_stored_hash";
    case PageState::kRefusedResult: return "refused_result_hash";
    default: return "unread";
  }
}

// The corrected bytes of one page, read from the host file itself. `out` is filled only for kCorrected.
inline PageState Prepare(const std::filesystem::path& host_path, const Bundle& bundle, const Page& page,
                         std::vector<uint8_t> out[2]) {
  std::error_code ec;
  if (std::filesystem::file_size(host_path, ec) != bundle.size || ec) return PageState::kRefusedSize;
  std::ifstream file(host_path, std::ios::binary);
  std::vector<uint8_t> blobs[2];
  for (int b = 0; b < 2; ++b) {
    blobs[b].resize(size_t(page.size[b]));
    file.seekg(std::streamoff(page.offset[b]));
    file.read(reinterpret_cast<char*>(blobs[b].data()), std::streamsize(blobs[b].size()));
    if (!file || size_t(file.gcount()) != blobs[b].size()) return PageState::kRefusedRead;
    if (Fnv1a(blobs[b].data(), blobs[b].size()) != page.stored[b]) return PageState::kRefusedStored;
  }
  if (!MirrorPage(blobs, kPage512Dxt5, kPage512Dxt5Levels)) return PageState::kRefusedResult;
  for (int b = 0; b < 2; ++b)
    if (Fnv1a(blobs[b].data(), blobs[b].size()) != page.corrected[b]) return PageState::kRefusedResult;
  out[0] = std::move(blobs[0]);
  out[1] = std::move(blobs[1]);
  return PageState::kCorrected;
}

struct State {
  std::mutex mutex;
  void (*log)(const char*) = nullptr;
  struct Slot {
    PageState state = PageState::kUnread;
    std::vector<uint8_t> data[2];
    uint64_t served = 0;
    bool complete_logged = false;
  };
  std::vector<std::vector<Slot>> slots;  // [bundle][page]
};
inline State& state() {
  static State s;
  return s;
}

// After a successful host read of `length` bytes at `offset` into `buffer`: replaces the bytes of listed pages.
// `force` is for the deterministic test (the environment switch is read once per process).
inline size_t AfterRead(const std::filesystem::path& host_path, uint64_t offset, uint8_t* buffer, size_t length,
                        bool force = false) {
  if (!(force || Enabled()) || !length) return 0;
  const Bundle* bundle = FindBundle(host_path.filename());
  if (!bundle) return 0;
  State& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  if (s.slots.empty()) {
    s.slots.resize(kBundleCount);
    for (size_t i = 0; i < kBundleCount; ++i) s.slots[i].resize(kBundles[i].page_count);
  }
  auto& slots = s.slots[size_t(bundle - kBundles)];
  size_t replaced = 0;
  for (size_t p = 0; p < bundle->page_count; ++p) {
    const Page& page = bundle->pages[p];
    bool touches = false;
    for (int b = 0; b < 2; ++b)
      touches |= offset < page.offset[b] + page.size[b] && page.offset[b] < offset + length;
    if (!touches) continue;
    auto& slot = slots[p];
    if (slot.state == PageState::kUnread) {
      slot.state = Prepare(host_path, *bundle, page, slot.data);
      if (s.log) {
        const std::string line = std::string("M26 texture_orient file=") + bundle->file + " page=" + page.name +
                                 " state=" + Name(slot.state);
        s.log(line.c_str());
      }
    }
    if (slot.state != PageState::kCorrected) continue;
    size_t here = 0;
    for (int b = 0; b < 2; ++b)
      here += Overlay(buffer, offset, length, slot.data[b].data(), page.offset[b], slot.data[b].size());
    slot.served += here;
    replaced += here;
    if (!slot.complete_logged && slot.served >= page.size[0] + page.size[1] && s.log) {
      slot.complete_logged = true;
      const std::string line = std::string("M26 texture_orient file=") + bundle->file + " page=" + page.name +
                               " served_bytes=" + std::to_string(slot.served);
      s.log(line.c_str());
    }
  }
  return replaced;
}

}  // namespace m26tex
