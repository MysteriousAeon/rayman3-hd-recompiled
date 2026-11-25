// G6-P127 / G6-P128 (D-362, D-363, E-608, E-609): Fail-closed host `.lvl` read overlay for the Grand Minimus /
// Teensie King crown material (`charact\teensy_cour.dds`, layer-0 `blend_byte` at material `+0x6C`, `0x03 -> 0x08`).
//
// Installed as `include/rex/g6p127_crown_blend.h` by `tools/g6p127_crown_blend_patch.py` and called from
// `HostPathFile::ReadSync` strictly after M26 / D-219 beam / D-221 lock-on and strictly before M33 mods so any
// data-only mod still wins.
//
// Activation & precedence (D-363):
//   1. Production setting `R3HD_CROWN_CUTOUT` (`"original"` or `"cutout"`, set by Vanilla / HD+ / Custom via
//      `play.ps1` and `r3hd_play.py`) ALWAYS takes precedence when set to a non-empty value:
//        - `"cutout"`   -> enabled
//        - `"original"` -> disabled (never overridden by a stray diagnostic variable)
//        - any other non-empty value -> disabled (fail-closed)
//   2. Developer diagnostic fallback `R3HD_TEST_CROWN_BLEND` (G6-P127): consulted ONLY when `R3HD_CROWN_CUTOUT` is
//      absent or empty; exact `"cutout"` enables the overlay.
//   3. Otherwise disabled (original Xbox 360 HD `0x03` byte returned untouched).
//
// Scope: all 10 independently verified `charact\teensy_cour.dds` bundles (`menu_00` [G6-P127 human visually accepted]
// plus 9 resource-equivalent levels [`fact_40`, `fact_50`, `fact_55`, `knaar_10`, `knaar_20`, `knaar_30`, `knaar_45`,
// `knaar_70`, `staff` — visual acceptance pending]). Unrelated bundles such as `knaar_60.lvl` (`gum_crown.dds`) are
// absent from the table and never matched.
//
// Fail-closed validation per bundle:
//   1. Exact `.lvl` filename (case-insensitive, no substring matching) and exact host file size.
//   2. LVL 4-byte big-endian header at file offset 0.
//   3. Crown material record structural fields at `record_offset` (payload + 4):
//      - `flags` at `+0x00` == `0x4DDC43FF` (double-sided)
//      - `tex_record` at `+0x68` == per-bundle exact `charact\teensy_cour.tga` texture record offset
//      - `blend_byte` at `+0x6C` == `0x03`
//   4. Exact 64-bit FNV-1a hash of the 128-byte stored material record and of the single-byte patched record.
//   5. Caller read-buffer byte at `record_offset + 0x6C` is `0x03` (or already `0x08` on repeated idempotent calls).
//
// Nothing is written to disk, to generated code, or to guest memory outside the requested read buffer.
// No proprietary asset bytes are stored in this header (offsets, sizes, structural field constants, and hashes only).
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <string>
#include <system_error>
#include <vector>

namespace g6p127crown {

struct RecordSpec {
  const char* file;            // exact target filename, compared without case
  uint64_t file_size;          // exact expected host file size in bytes
  uint64_t header_offset;      // LVL header offset (0)
  uint32_t expected_header;    // big-endian u32 LVL header
  uint64_t record_offset;      // file offset of material record (payload + 4)
  size_t record_size;          // material record validation window (128 bytes)
  size_t flags_rel_offset;     // +0x00 within material record
  uint32_t expected_flags;     // big-endian u32 material flags
  size_t tex_rel_offset;       // +0x68 within material record
  uint32_t expected_tex;       // big-endian u32 texture record offset
  size_t blend_rel_offset;     // +0x6C within material record
  uint8_t orig_blend_byte;     // 0x03
  uint8_t patched_blend_byte;  // 0x08
  uint64_t stored_fnv1a;       // FNV-1a 64 of the stored 128-byte record
  uint64_t patched_fnv1a;      // FNV-1a 64 of the patched 128-byte record
};

// All 10 independently verified charact\teensy_cour.dds bundles (E-606, E-608, E-609).
// Index 0 (`menu_00.lvl`) is G6-P127 human visually accepted; indices 1..9 are resource-equivalent (visual pending).
constexpr RecordSpec kCrownRecords[] = {
    {"menu_00.lvl", 3326768ull, 0ull, 0x000000D8u, 0x15AF40ull, 0x80u, 0x00u, 0x4DDC43FFu, 0x68u, 0x000047F4u, 0x6Cu,
     0x03u, 0x08u, 0xFD84C53317B330C0ull, 0x2CBDE86231377E77ull},
    {"fact_40.lvl", 7407960ull, 0ull, 0x0000020Cu, 0x084D0Cull, 0x80u, 0x00u, 0x4DDC43FFu, 0x68u, 0x00006234u, 0x6Cu,
     0x03u, 0x08u, 0x2DFA792FA03CA0E1ull, 0x77F89E64D0C22EE6ull},
    {"fact_50.lvl", 6860968ull, 0ull, 0x00000169u, 0x22E430ull, 0x80u, 0x00u, 0x4DDC43FFu, 0x68u, 0x000079D4u, 0x6Cu,
     0x03u, 0x08u, 0x50D4B405096A093Eull, 0xE5F5089A4054AD29ull},
    {"fact_55.lvl", 5553080ull, 0ull, 0x000002EBu, 0x23AE0Cull, 0x80u, 0x00u, 0x4DDC43FFu, 0x68u, 0x00005E44u, 0x6Cu,
     0x03u, 0x08u, 0x246996406F2911BDull, 0x8F4941AB383E6DD2ull},
    {"knaar_10.lvl", 7112256ull, 0ull, 0x000001D8u, 0x3435F8ull, 0x80u, 0x00u, 0x4DDC43FFu, 0x68u, 0x00005904u, 0x6Cu,
     0x03u, 0x08u, 0x4B61555252D7134Eull, 0xE081A9E789C1B739ull},
    {"knaar_20.lvl", 3491284ull, 0ull, 0x00000107u, 0x0F6978ull, 0x80u, 0x00u, 0x4DDC43FFu, 0x68u, 0x00005A54u, 0x6Cu,
     0x03u, 0x08u, 0xF0C305D56BD21CB9ull, 0x5BA2B14034E778CEull},
    {"knaar_30.lvl", 4745252ull, 0ull, 0x0000014Cu, 0x2E2744ull, 0x80u, 0x00u, 0x4DDC43FFu, 0x68u, 0x00005E44u, 0x6Cu,
     0x03u, 0x08u, 0x246996406F2911BDull, 0x8F4941AB383E6DD2ull},
    {"knaar_45.lvl", 5673532ull, 0ull, 0x000001AAu, 0x314880ull, 0x80u, 0x00u, 0x4DDC43FFu, 0x68u, 0x00006F54u, 0x6Cu,
     0x03u, 0x08u, 0x5B9E6027D3A58D28ull, 0x680BC53469B24DCFull},
    {"knaar_70.lvl", 5295748ull, 0ull, 0x00000159u, 0x12ABC8ull, 0x80u, 0x00u, 0x4DDC43FFu, 0x68u, 0x000053C4u, 0x6Cu,
     0x03u, 0x08u, 0xE6F2AF6C86A18D6Cull, 0x162BD29BA025DB23ull},
    {"staff.lvl", 717884ull, 0ull, 0x00000076u, 0x0368ACull, 0x80u, 0x00u, 0x4DDC43FFu, 0x68u, 0x0000307Cu, 0x6Cu,
     0x03u, 0x08u, 0x09D7424BE148A503ull, 0xDA9E1F1CC7C4574Cull},
};
constexpr size_t kCrownRecordCount = sizeof(kCrownRecords) / sizeof(RecordSpec);
constexpr const RecordSpec& kMenu00CrownRecord = kCrownRecords[0];

// Exact "cutout" enables the overlay; anything else leaves all reads untouched.
inline bool Selected(const char* value) { return value && std::strcmp(value, "cutout") == 0; }

// Explicit precedence (D-363): non-empty production R3HD_CROWN_CUTOUT always wins over R3HD_TEST_CROWN_BLEND.
// Diagnostic R3HD_TEST_CROWN_BLEND=cutout applies only when R3HD_CROWN_CUTOUT is absent or empty.
inline bool ResolveEnabled(const char* prod_value, const char* diag_value) {
  if (prod_value && prod_value[0] != '\0') return Selected(prod_value);
  return Selected(diag_value);
}

inline bool Enabled() {
  static const bool on = ResolveEnabled(std::getenv("R3HD_CROWN_CUTOUT"), std::getenv("R3HD_TEST_CROWN_BLEND"));
  return on;
}

inline uint64_t Fnv1a(const uint8_t* data, size_t size) {
  uint64_t h = 0xCBF29CE484222325ull;
  for (size_t i = 0; i < size; ++i) h = (h ^ data[i]) * 0x100000001B3ull;
  return h;
}

inline uint32_t ReadBE32(const uint8_t* p) {
  return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | uint32_t(p[3]);
}

inline bool SameName(const std::filesystem::path::string_type& a, const char* b) {
  size_t i = 0;
  for (; i < a.size() && b[i]; ++i) {
    const auto x = a[i] >= 'A' && a[i] <= 'Z' ? a[i] + 32 : a[i];
    const auto y = b[i] >= 'A' && b[i] <= 'Z' ? b[i] + 32 : b[i];
    if (x != y) return false;
  }
  return i == a.size() && !b[i];
}

inline size_t FindRecordIndex(const std::filesystem::path& file_name) {
  const auto native = file_name.native();
  for (size_t i = 0; i < kCrownRecordCount; ++i) {
    if (SameName(native, kCrownRecords[i].file)) return i;
  }
  return kCrownRecordCount;
}

enum class CheckState {
  kUnread,
  kApplied,
  kRefusedSize,
  kRefusedRead,
  kRefusedHeader,
  kRefusedSignature,
  kRefusedSourceByte,
  kRefusedStoredHash,
  kRefusedResultHash,
};

inline const char* Name(CheckState s) {
  switch (s) {
    case CheckState::kApplied: return "applied";
    case CheckState::kRefusedSize: return "refused_file_size";
    case CheckState::kRefusedRead: return "refused_read";
    case CheckState::kRefusedHeader: return "refused_header";
    case CheckState::kRefusedSignature: return "refused_signature";
    case CheckState::kRefusedSourceByte: return "refused_source_byte";
    case CheckState::kRefusedStoredHash: return "refused_stored_hash";
    case CheckState::kRefusedResultHash: return "refused_result_hash";
    default: return "unread";
  }
}

inline CheckState ValidateFile(const std::filesystem::path& host_path,
                               const RecordSpec& spec = kMenu00CrownRecord) {
  std::error_code ec;
  if (std::filesystem::file_size(host_path, ec) != spec.file_size || ec) return CheckState::kRefusedSize;
  if (spec.record_size < spec.blend_rel_offset + 1 ||
      spec.record_size < spec.flags_rel_offset + 4 ||
      spec.record_size < spec.tex_rel_offset + 4 ||
      spec.record_offset + spec.record_size > spec.file_size ||
      spec.header_offset + 4 > spec.file_size) {
    return CheckState::kRefusedSignature;
  }
  std::ifstream file(host_path, std::ios::binary);
  if (!file) return CheckState::kRefusedRead;

  uint8_t hdr[4] = {};
  file.seekg(std::streamoff(spec.header_offset));
  file.read(reinterpret_cast<char*>(hdr), 4);
  if (!file || file.gcount() != 4) return CheckState::kRefusedRead;
  if (ReadBE32(hdr) != spec.expected_header) return CheckState::kRefusedHeader;

  std::vector<uint8_t> rec(spec.record_size);
  file.seekg(std::streamoff(spec.record_offset));
  file.read(reinterpret_cast<char*>(rec.data()), std::streamsize(rec.size()));
  if (!file || size_t(file.gcount()) != rec.size()) return CheckState::kRefusedRead;

  if (ReadBE32(rec.data() + spec.flags_rel_offset) != spec.expected_flags ||
      ReadBE32(rec.data() + spec.tex_rel_offset) != spec.expected_tex) {
    return CheckState::kRefusedSignature;
  }
  if (rec[spec.blend_rel_offset] != spec.orig_blend_byte) return CheckState::kRefusedSourceByte;
  if (Fnv1a(rec.data(), rec.size()) != spec.stored_fnv1a) return CheckState::kRefusedStoredHash;

  rec[spec.blend_rel_offset] = spec.patched_blend_byte;
  if (Fnv1a(rec.data(), rec.size()) != spec.patched_fnv1a) return CheckState::kRefusedResultHash;

  return CheckState::kApplied;
}

struct FileState {
  std::filesystem::path cached_path;
  CheckState state = CheckState::kUnread;
  uint64_t served = 0;
  bool complete_logged = false;
};

struct State {
  std::mutex mutex;
  void (*log)(const char*) = nullptr;
  std::array<FileState, kCrownRecordCount> files = {};
  FileState custom = {};  // used only by explicit single-spec test overloads
};

inline State& state() {
  static State s;
  return s;
}

inline void ResetForTest() {
  State& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  for (auto& f : s.files) f = FileState{};
  s.custom = FileState{};
}

inline size_t ApplyRecord(FileState& fs, void (*log_fn)(const char*), const std::filesystem::path& host_path,
                          uint64_t offset, uint8_t* buffer, size_t length, const RecordSpec& spec) {
  const uint64_t target_offset = spec.record_offset + spec.blend_rel_offset;
  if (offset > target_offset || target_offset - offset >= length) return 0;

  if (fs.state == CheckState::kUnread || fs.cached_path != host_path) {
    fs.cached_path = host_path;
    fs.state = ValidateFile(host_path, spec);
    fs.served = 0;
    fs.complete_logged = false;
    if (log_fn) {
      const std::string line =
          std::string("R3HD crown_cutout file=") + spec.file + " state=" + Name(fs.state);
      log_fn(line.c_str());
    }
  }
  if (fs.state != CheckState::kApplied) return 0;

  uint8_t& dst = buffer[size_t(target_offset - offset)];
  if (dst != spec.orig_blend_byte && dst != spec.patched_blend_byte) return 0;
  dst = spec.patched_blend_byte;
  ++fs.served;
  if (!fs.complete_logged && log_fn) {
    fs.complete_logged = true;
    char off_hex[32];
    std::snprintf(off_hex, sizeof(off_hex), "0x%llX", static_cast<unsigned long long>(target_offset));
    const std::string line = std::string("R3HD crown_cutout file=") + spec.file + " offset=" + off_hex +
                             " byte=0x03->0x08 served_bytes=1";
    log_fn(line.c_str());
  }
  return 1;
}

// Production entry point: looks up `host_path.filename()` in `kCrownRecords` (all 10 verified bundles).
// `force` is for deterministic offline tests (the environment variables are read once per process).
inline size_t AfterRead(const std::filesystem::path& host_path, uint64_t offset, uint8_t* buffer, size_t length,
                        bool force = false) {
  if (!(force || Enabled()) || !buffer || !length) return 0;
  const size_t idx = FindRecordIndex(host_path.filename());
  if (idx >= kCrownRecordCount) return 0;
  State& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  return ApplyRecord(s.files[idx], s.log, host_path, offset, buffer, length, kCrownRecords[idx]);
}

// Single-spec overload for synthetic offline tests with custom RecordSpec fixtures.
inline size_t AfterRead(const std::filesystem::path& host_path, uint64_t offset, uint8_t* buffer, size_t length,
                        bool force, const RecordSpec& spec) {
  if (!(force || Enabled()) || !buffer || !length) return 0;
  if (!SameName(host_path.filename().native(), spec.file)) return 0;
  State& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  return ApplyRecord(s.custom, s.log, host_path, offset, buffer, length, spec);
}

}  // namespace g6p127crown
