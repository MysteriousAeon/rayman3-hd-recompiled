// M33 (D-070): data-only mods as a verified byte overlay on game-file reads. Installed as
// include/rex/m33_mod_overlay.h by tools/m33_runtime_patch.py and used by the host file read path
// (HostPathFile::ReadSync) only.
//
// tools/r3hd_mods.py validates installed mods (a manifest of declared texture and text overrides, nothing
// executable) and compiles the enabled ones, against the person's own extracted game files, into a plan: for each
// game file, byte ranges with the hash of the file's own bytes there and the hash of the replacement bytes (one
// replacement file per range, in the user's cache). play.ps1 names the plan in R3HD_MODS_PLAN; without the variable
// nothing changes and the cost is one flag test per read.
//
// The plan is verified as a whole before anything is served: header and end marker, every file's size, every
// range inside its file and apart from the others, every replacement's size and hash, and the hash of the game's
// own bytes in every range (read once from the file). Any failure leaves the whole plan unused (one
// `M33 mods state=refused reason=...` line): a partly applied mod is never shown. Nothing is written to disk, to
// guest memory outside the buffer the title asked to have filled, or to the game files. The bytes served are the
// replacement bytes only where a range overlaps the read; every other byte is the file's own.
//
// Plan format, UTF-8 text, one record per line (numbers decimal, hashes 16 hex digits of FNV-1a 64; a path is the
// rest of its line):
//   R3HD_MOD_PLAN 1
//   mod <id> <version>
//   file <size> <absolute path of a game file>
//   grow <file index from 0> <size the guest sees>                  (M36, D-073: VS.sub only, see below)
//   range <file index from 0> <offset> <length> <hash of the game's bytes> <hash of the new bytes> <mod id> <path>
//   gameplay <mod id>                                                (D-224: a listed mod changes game logic)
//   end <file count> <range count>
//
// D-224: r3hd_mods.py writes `gameplay <id>` for every applied mod whose validated overrides change game logic
// (script constants, D-223). GameplayModsActive() is true only while such a plan is verified and active; the title's
// achievement unlock path then awards nothing new (tools/m33_runtime_patch.py, KernelState::UnlockAchievement). The
// record names a mod of the plan, once; a runtime before D-224 refuses such a plan as a whole (unknown_record).
//
// M36 (D-073): a `grow` record lets one file be longer for the guest than on disk: the size the guest is told (entry
// size: NtQueryFullAttributesFile, NtQueryInformationFile, NtQueryDirectoryFile) and the bytes it can read. Only a
// file named in kGrowNames may grow (the subtitle table, whose loader reads it sequentially and never asks its size,
// RE_NOTES "M35"), by at most kMaxGrowBytes; the record must precede that file's ranges, and the ranges must cover
// every byte past the file's end (no byte the plan does not define is ever served). A range's game-bytes hash covers
// only its part inside the file (a range wholly past the end hashes no bytes). Reads stop at the guest size with the
// host's own end-of-file result. Without a `grow` record nothing about a file's size changes; a runtime before M36
// refuses such a plan as a whole (unknown_record).
//
// G5-P1 (D-243, DEVELOPMENT BUILDS ONLY): with R3HD_DEV_STRUCTURAL_TX defined at compile time (never in a production
// build: tools/experiments/modding_feasibility/g5p1_dev_gate.py adds the define to the SDK's installed copy for a
// private build) and the environment variable R3HD_DEV_STRUCTURAL_TX naming the level, a plan may carry one level
// transaction that lets an allow-listed level file and its pointer table grow together:
//   level-tx <version 1> <level> <mod id> <transaction id>
//   tx-file <file index> <lvl|ptr> <original sha256> <guest size> <sha256 of the guest image>   (after its `file`)
// Before anything is served: the level, the two files' names, sizes and SHA-256 (hashed here from the files) are the
// allow-listed ones; both members are present, each grown by its own `grow` within its bound; the pointer table is
// covered by one range of the transaction's mod; the image the guest will read (original + that mod's ranges) has
// the declared SHA-256; the identifier is the SHA-256 of the canonical transaction text. Any failure refuses the whole
// plan, as every other check does (so no member is ever served alone, whichever file the guest opens first). Without
// the define these records are unknown (`unknown_record`), so a production runtime refuses such a plan as a whole,
// and `.lvl` / `.ptr` growth stays refused (`grow_not_allowed`).
//
// G5-P3 (D-246, development builds only): each member is read from disk once, at plan load, into host memory; its
// SHA-256, its ranges' own-byte hashes and the declared image are checked on those bytes, and the guest image built
// from them (immutable, owned by the plan for the process's life) answers every size query and every read of the
// member: the host's own bytes are discarded, so a member changed, truncated, replaced or removed on disk after the
// plan was verified never reaches the guest, and the `.lvl` and `.ptr` the guest reads are always the verified pair.
// Snapshots and images together are bounded (kMaxSnapshotBytes, `tx_snapshot_budget`); the snapshots are released
// once the images are built.
// G6-P30 (D-286): PRODUCTION level transactions. This header carries the level-transaction code that development
// builds verified at run time (G5-P1 / G5-P3 / G6-P1 / G6-P3 / G6-P20 / G6-P23 / G6-P27), with three production rules:
// no environment authorization (nothing outside the plan enables it), only the intro_20 version-2 members, and the
// content policy (ProductionContent) on every member's declared image before anything is served. The comments below
// that say "development builds only" describe the history of this code. Development builds are rendered by
// tools/experiments/modding_feasibility/g5p1_dev_gate.py from the frozen pre-G6-P30 header, unchanged.
#pragma once
#define R3HD_LEVEL_TX 1  // G6-P30 (D-286): production level transactions
#include <algorithm>
#include <cctype>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <cmath>
#include <fstream>
#include <iterator>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <system_error>
#include <unordered_map>
#include <vector>

namespace m33mods {

constexpr size_t kMaxFiles = 4096;
constexpr size_t kMaxRanges = 65536;
constexpr uint64_t kMaxRangeBytes = 64ull << 20;
constexpr uint64_t kMaxTotalBytes = 512ull << 20;
constexpr size_t kMaxLine = 4096;
constexpr uint64_t kMaxGrowBytes = 1ull << 20;
constexpr const char* kGrowNames[] = {"VS.sub"};
constexpr size_t kMaxGrowLogLines = 64;

// The plan's path from R3HD_MODS_PLAN, read as UTF-16 on Windows (M33 review: the ANSI code page would turn a home
// folder with non-ASCII letters into an unreadable path). Empty = no plan.
inline std::filesystem::path PlanVariable() {
#ifdef _WIN32
  const wchar_t* v = _wgetenv(L"R3HD_MODS_PLAN");
  return v && *v ? std::filesystem::path(v) : std::filesystem::path();
#else
  const char* v = std::getenv("R3HD_MODS_PLAN");
  return v && *v ? std::filesystem::path(v) : std::filesystem::path();
#endif
}
inline bool Enabled() {
  static const bool on = !PlanVariable().empty();
  return on;
}

inline uint64_t Fnv1a(const uint8_t* data, size_t size, uint64_t h = 0xCBF29CE484222325ull) {
  for (size_t i = 0; i < size; ++i) h = (h ^ data[i]) * 0x100000001B3ull;
  return h;
}

#if defined(R3HD_LEVEL_TX)
// G5-P1 (D-243): development-only level transactions (see the top of this file).
namespace devtx {
struct Member {
  const char* level;
  const char* role;
  const char* name;
  uint64_t size;
  const char* sha256;
  uint64_t max_grow;  // G6-P1: 0 = a same-size member (never grown)
  unsigned versions;  // G6-P1: bit (v - 1) set when a version-v transaction of the level needs this member
};
constexpr Member kAllowed[] = {
    // G5-P4a (D-247, E-480): the second allow-listed level (one transaction per plan; the variable names the level)
    {"intro_20", "lvl", "intro_20.lvl", 6135684, "a21aa7691db4cedb3892e685e5395fd23b530b0bde4d64a09035dfb5f2d0b11f",
     4096, 2},
    {"intro_20", "ptr", "intro_20.ptr", 273540, "be90b58a3bfa78d19f3335489edcc79214442d52cbde04c6ad5a465f9fb17cb1",
     1024, 2},
    // G6-P3 (D-256, E-489): intro_20's transit.lvl, a same-size member of version 2 only (insert-fairy-on-graph)
    {"intro_20", "transit", "transit.lvl", 26140, "51c0fbf1239acd6188316a6d64507761903d5a087df1ea717426d5cb810e6aa8",
     0, 2},
};
// G6-P30 (D-286): production builds read no environment authorization; the content policy decides.
// G6-P1: the Member::versions bit of a transaction version (0 = unknown).
inline unsigned VersionBit(const std::string& v) { return v == "1" ? 1u : v == "2" ? 2u : 0u; }
inline std::string EnabledLevel() { return "intro_20"; }

class Sha256 {
 public:
  void Update(const uint8_t* p, size_t n) {
    total_ += n;
    while (n) {
      const size_t k = std::min(n, size_t(64) - used_);
      std::memcpy(buf_ + used_, p, k);
      used_ += k;
      p += k;
      n -= k;
      if (used_ == 64) {
        Block(buf_);
        used_ = 0;
      }
    }
  }
  std::string HexDigest() {
    const uint64_t bits = total_ * 8;
    const uint8_t one = 0x80, zero = 0;
    Update(&one, 1);
    while (used_ != 56) Update(&zero, 1);
    uint8_t len[8];
    for (int i = 0; i < 8; ++i) len[i] = uint8_t(bits >> (56 - 8 * i));
    Update(len, 8);
    static const char* hex = "0123456789abcdef";
    std::string out;
    for (uint32_t v : h_)
      for (int i = 28; i >= 0; i -= 4) out.push_back(hex[(v >> i) & 15]);
    return out;
  }

 private:
  static uint32_t Rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }
  void Block(const uint8_t* b) {
    static const uint32_t k[64] = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
    uint32_t w[64];
    for (int i = 0; i < 16; ++i)
      w[i] = uint32_t(b[4 * i]) << 24 | uint32_t(b[4 * i + 1]) << 16 | uint32_t(b[4 * i + 2]) << 8 | b[4 * i + 3];
    for (int i = 16; i < 64; ++i) {
      const uint32_t s0 = Rotr(w[i - 15], 7) ^ Rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      const uint32_t s1 = Rotr(w[i - 2], 17) ^ Rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h_[0], bb = h_[1], c = h_[2], d = h_[3], e = h_[4], f = h_[5], g = h_[6], h = h_[7];
    for (int i = 0; i < 64; ++i) {
      const uint32_t t1 = h + (Rotr(e, 6) ^ Rotr(e, 11) ^ Rotr(e, 25)) + ((e & f) ^ (~e & g)) + k[i] + w[i];
      const uint32_t t2 = (Rotr(a, 2) ^ Rotr(a, 13) ^ Rotr(a, 22)) + ((a & bb) ^ (a & c) ^ (bb & c));
      h = g;
      g = f;
      f = e;
      e = d + t1;
      d = c;
      c = bb;
      bb = a;
      a = t1 + t2;
    }
    h_[0] += a;
    h_[1] += bb;
    h_[2] += c;
    h_[3] += d;
    h_[4] += e;
    h_[5] += f;
    h_[6] += g;
    h_[7] += h;
  }
  uint32_t h_[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  uint8_t buf_[64] = {};
  size_t used_ = 0;
  uint64_t total_ = 0;
};
inline std::string Sha256Hex(const uint8_t* p, size_t n) {
  Sha256 s;
  s.Update(p, n);
  return s.HexDigest();
}
// The file name (ASCII letters without case) is exactly `name`.
inline bool NameIs(const std::filesystem::path& p, const char* name) {
  const auto x = p.filename().native();
  if (x.size() != std::strlen(name)) return false;
  for (size_t i = 0; i < x.size(); ++i) {
    auto c = x[i];
    if (c >= 'A' && c <= 'Z') c = c + 32;
    if (c != decltype(c)(name[i])) return false;
  }
  return true;
}
// G5-P3 (D-246): bound on the members' host copies during plan load (snapshots + images; afterwards images only).
#ifndef R3HD_DEVTX_SNAPSHOT_BUDGET
#define R3HD_DEVTX_SNAPSHOT_BUDGET (16ull << 20)
#endif
constexpr uint64_t kMaxSnapshotBytes = R3HD_DEVTX_SNAPSHOT_BUDGET;
// Whole-member reads from disk (for the deterministic test: one per member per plan load).
inline uint64_t& MemberDiskReads() {
  static uint64_t n = 0;
  return n;
}
inline bool Hex64(const std::string& s) {
  if (s.size() != 64) return false;
  for (char c : s)
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
  return true;
}

// G6-P30 (D-286): the production content policy of a level transaction. Exactly one composition is accepted: the
// intro_20 version-2 transaction of a start-floor terrain (regions start-floor-v1 / -v2, or the start-two-step-v1
// preset) + the FairyLight on graph A (tools/r3hd_mods.py level_patch_production). Derived and re-checked by
// tools/experiments/modding_feasibility/g6p30_production_policy.py over every start-floor group configuration: every
// such transaction has the same .ptr and transit.lvl results, and its .lvl image with the terrain windows below reset to
// the original bytes is one image (the FairyLight-A base); inside the windows every big-endian float word moves by at
// most kProdWordBound. Anything else (graph B, routes, intro_10, other terrain, any other byte) is refused.
struct Window {
  uint64_t offset, length;
};
constexpr uint64_t kProdLvlGuest = 6138576, kProdPtrGuest = 273948;
constexpr const char* kProdPtrResult = "40934d08eeed74d87eb0dd385d82a7382cce6e2c53166083741be16d5ee8979c";
constexpr const char* kProdTransitResult = "2be9a434eed49c9625efe0462a67510216813aff7edc3e75e4e083bff3a0a7e4";
constexpr const char* kProdLvlBase = "bda217f96f41107f4c53e326a9449937867614981dcf82858b57f1e7e57b8a51";
constexpr Window kProdTerrainWindows[] = {
    {0xC108, 4},
    {0xC180, 4},
    {0xC414, 4},
    {0xC474, 4},
    {0x221E8, 24},
    {0x22230, 24},
    {0x22260, 24},
    {0x22620, 24},
    {0x22644, 36},
    {0x4B424, 4},
    {0x4B43C, 4},
    {0x4B454, 4},
    {0x4B46C, 4},
    {0x53F78, 96},
    {0x53FE4, 36},
    {0x550B4, 204},
    {0x55198, 48},
    {0x5613C, 4},
    {0x56150, 4},
    {0x56164, 4},
    {0x56174, 4},
    {0x5617C, 4}};
constexpr float kProdWordBound = 0.3125f;
inline float BeFloat(const uint8_t* p) {
  const uint32_t u = uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3];
  float f;
  std::memcpy(&f, &u, 4);
  return f;
}
// "" when the declared image of member `a` meets the policy; `image` is restored before returning.
inline std::string ProductionContent(const Member& a, const std::vector<uint8_t>& orig, std::vector<uint8_t>& image,
                                     const std::string& result) {
  const std::string role = a.role;
  if (std::string(a.level) != "intro_20") return "tx_policy_level";
  if (role == "transit") return result == kProdTransitResult ? "" : "tx_policy_result";
  if (role == "ptr") return image.size() == kProdPtrGuest && result == kProdPtrResult ? "" : "tx_policy_result";
  if (role != "lvl" || image.size() != kProdLvlGuest) return "tx_policy_result";
  std::vector<uint8_t> saved;
  saved.reserve(1024);
  std::string why;
  for (const auto& w : kProdTerrainWindows) {
    if (w.offset % 4 || w.length % 4 || w.offset + w.length > orig.size()) return "tx_policy_terrain";
    for (uint64_t o = w.offset; o < w.offset + w.length && why.empty(); o += 4) {
      const float v0 = BeFloat(orig.data() + o), v1 = BeFloat(image.data() + o);
      if (!std::isfinite(v1) || !(std::fabs(v1 - v0) <= kProdWordBound)) why = "tx_policy_terrain";
    }
  }
  if (!why.empty()) return why;
  for (const auto& w : kProdTerrainWindows) {
    saved.insert(saved.end(), image.begin() + w.offset, image.begin() + w.offset + w.length);
    std::memcpy(image.data() + w.offset, orig.data() + w.offset, size_t(w.length));
  }
  const bool base = Sha256Hex(image.data(), image.size()) == kProdLvlBase;
  size_t k = 0;
  for (const auto& w : kProdTerrainWindows) {
    std::memcpy(image.data() + w.offset, saved.data() + k, size_t(w.length));
    k += size_t(w.length);
  }
  return base ? "" : "tx_policy_content";
}
}  // namespace devtx
#endif

struct Range {
  uint64_t offset = 0, length = 0, base = 0, result = 0;
  std::string mod;
  std::vector<uint8_t> data;
  uint64_t served = 0;
  bool logged = false;
};
struct Target {
  std::filesystem::path path;
  uint64_t size = 0;
  uint64_t guest_size = 0;    // M36: = size unless a `grow` record set it
  std::vector<Range> ranges;  // sorted by offset, disjoint
  uint64_t grow_reads = 0;    // M36: reads of a grown file seen (for the log)
  bool size_logged = false;
#if defined(R3HD_LEVEL_TX)
  int tx_member = -1;         // G5-P1: index into devtx::kAllowed when a `tx-file` names this file
  uint64_t tx_guest = 0;
  std::string tx_orig, tx_result;
  std::shared_ptr<const std::vector<uint8_t>> tx_snapshot;  // G5-P3: the original bytes, read once (load only)
  std::shared_ptr<const std::vector<uint8_t>> tx_image;     // G5-P3: the whole guest view, served for every read
  uint64_t tx_reads = 0, tx_passes = 0;  // G5-P3: reads served; reads at offset 0 (a guest pass from the start)
  bool tx_changed_logged = false;
#endif
};
struct Plan {
  std::vector<std::string> mods;  // "id version"
  std::vector<std::string> gameplay;  // D-224: ids of mods that change game logic
  std::vector<Target> files;
  size_t range_count = 0;
  uint64_t bytes = 0;
  bool grown = false;  // M36: some file has guest_size > size
#if defined(R3HD_LEVEL_TX)
  bool tx = false;  // G5-P1: a `level-tx` record was read
  std::string tx_level, tx_mod, tx_id;
  std::string tx_version;  // G6-P1: "1" (lvl + ptr) or "2" (lvl + ptr + transit)
#endif
};

// UTF-8 plan text -> path (the SDK is built without char8_t, so no u8string). Invalid UTF-8 gives an empty path,
// which every check then refuses.
inline std::filesystem::path FromUtf8(const std::string& s) {
  using Char = std::filesystem::path::value_type;
  if constexpr (sizeof(Char) == 1) {
    return std::filesystem::path(s);
  } else {
    std::basic_string<Char> w;
    for (size_t i = 0; i < s.size();) {
      const unsigned char c = static_cast<unsigned char>(s[i]);
      const int n = c < 0x80 ? 1 : (c >> 5) == 6 ? 2 : (c >> 4) == 14 ? 3 : (c >> 3) == 30 ? 4 : 0;
      if (!n || i + n > s.size()) return {};
      uint32_t cp = n == 1 ? c : c & (0x7F >> n);
      for (int k = 1; k < n; ++k) {
        const unsigned char d = static_cast<unsigned char>(s[i + k]);
        if ((d >> 6) != 2) return {};
        cp = cp << 6 | (d & 0x3F);
      }
      i += size_t(n);
      if (cp >= 0x10000) {
        cp -= 0x10000;
        w.push_back(Char(0xD800 + (cp >> 10)));
        w.push_back(Char(0xDC00 + (cp & 0x3FF)));
      } else {
        w.push_back(Char(cp));
      }
    }
    return std::filesystem::path(w);
  }
}
inline bool ParseHex64(const std::string& s, uint64_t& out) {
  if (s.size() != 16) return false;
  out = 0;
  for (char c : s) {
    int v = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
    if (v < 0) return false;
    out = out << 4 | uint64_t(v);
  }
  return true;
}
inline bool ParseU64(const std::string& s, uint64_t& out) {
  if (s.empty() || s.size() > 19) return false;
  out = 0;
  for (char c : s) {
    if (c < '0' || c > '9') return false;
    out = out * 10 + uint64_t(c - '0');
  }
  return true;
}
inline bool SafeToken(const std::string& s) {
  if (s.empty() || s.size() > 64) return false;
  for (unsigned char c : s)
    if (!(std::isalnum(c) || c == '.' || c == '_' || c == '-' || c == '+')) return false;
  return true;
}
// A plain existing file (no link): the plan only ever names files r3hd_mods.py wrote or the game's own files.
inline bool PlainFile(const std::filesystem::path& p, uint64_t* size) {
  std::error_code ec;
  const auto st = std::filesystem::symlink_status(p, ec);
  if (ec || st.type() != std::filesystem::file_type::regular) return false;
  const uint64_t n = std::filesystem::file_size(p, ec);
  if (ec) return false;
  if (size) *size = n;
  return true;
}
inline bool ReadAt(const std::filesystem::path& p, uint64_t offset, uint64_t length, std::vector<uint8_t>& out) {
  std::ifstream f(p, std::ios::binary);
  if (!f) return false;
  out.resize(size_t(length));
  f.seekg(std::streamoff(offset));
  f.read(reinterpret_cast<char*>(out.data()), std::streamsize(length));
  return f && uint64_t(f.gcount()) == length;
}

// M36: whether the file name (ASCII, without case) is one that a `grow` record may name.
inline bool GrowAllowed(const std::filesystem::path& p) {
  const auto name = p.filename().native();
  for (const char* allowed : kGrowNames) {
    const size_t n = std::strlen(allowed);
    bool same = name.size() == n;
    for (size_t i = 0; same && i < n; ++i) {
      auto c = name[i];
      if (c >= 'A' && c <= 'Z') c = c + 32;
      char a = allowed[i];
      if (a >= 'A' && a <= 'Z') a = char(a + 32);
      same = c == decltype(c)(a);
    }
    if (same) return true;
  }
  return false;
}

// Reads and verifies a plan. Returns an empty string on success, otherwise the reason (and `out` is unusable).
inline std::string Load(const std::filesystem::path& plan_path, Plan& out) {
  out = Plan{};
  uint64_t plan_size = 0;
  if (!PlainFile(plan_path, &plan_size) || plan_size > (64u << 20)) return "plan_unreadable";
  std::ifstream in(plan_path, std::ios::binary);
  std::string line;
  size_t n = 0;
  bool ended = false;
  auto fail = [&](const char* why) { return std::string(why) + "@line" + std::to_string(n); };
  while (std::getline(in, line)) {
    ++n;
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.size() > kMaxLine) return fail("line_too_long");
    if (ended) return fail("data_after_end");
    std::istringstream ls(line);
    std::string kind;
    ls >> kind;
    if (n == 1) {
      std::string version;
      ls >> version;
      if (kind != "R3HD_MOD_PLAN" || version != "1") return fail("bad_header");
      continue;
    }
    if (kind == "mod") {
      std::string id, version, extra;
      ls >> id >> version >> extra;
      if (!SafeToken(id) || !SafeToken(version) || !extra.empty()) return fail("bad_mod");
      for (const auto& m : out.mods)
        if (m.substr(0, m.find(' ')) == id) return fail("duplicate_mod");
      out.mods.push_back(id + " " + version);
    } else if (kind == "file") {
      std::string size_text, rest;
      ls >> size_text;
      std::getline(ls >> std::ws, rest);
      Target t;
      if (!ParseU64(size_text, t.size) || rest.empty()) return fail("bad_file");
      t.path = FromUtf8(rest);
      uint64_t actual = 0;
      if (!t.path.is_absolute() || !PlainFile(t.path, &actual)) return fail("file_missing");
      if (actual != t.size) return fail("file_size");
      t.guest_size = t.size;
      if (out.files.size() >= kMaxFiles) return fail("too_many_files");
      out.files.push_back(std::move(t));
#if defined(R3HD_LEVEL_TX)
    } else if (kind == "level-tx") {  // G5-P1 (D-243): development builds only
      const std::string enabled = devtx::EnabledLevel();
      std::string version, level, mod, id, extra;
      ls >> version >> level >> mod >> id >> extra;
      if (version != "2") return fail("tx_version");  // G6-P30: production accepts version 2 only
      if (out.tx) return fail("tx_count");
      if (level.empty() || !extra.empty() || id.size() != 16 || !SafeToken(mod)) return fail("bad_tx");
      bool allowed = false;
      for (const auto& a : devtx::kAllowed) allowed |= level == a.level && (a.versions & devtx::VersionBit(version));
      if (!allowed || level != enabled) return fail("tx_level");
      bool known = false;
      for (const auto& m : out.mods) known |= m.substr(0, m.find(' ')) == mod;
      if (!known) return fail("tx_mod");
      out.tx = true;
      out.tx_level = level;
      out.tx_mod = mod;
      out.tx_id = id;
      out.tx_version = version;
    } else if (kind == "tx-file") {
      std::string index_text, role, orig, guest_text, result, extra;
      ls >> index_text >> role >> orig >> guest_text >> result >> extra;
      uint64_t index = 0, guest = 0;
      if (!ParseU64(index_text, index) || !ParseU64(guest_text, guest) || !devtx::Hex64(orig) ||
          !devtx::Hex64(result) || !extra.empty())
        return fail("bad_tx_file");
      if (!out.tx) return fail("tx_order");
      if (index >= out.files.size()) return fail("tx_file");
      Target& t = out.files[size_t(index)];
      if (t.tx_member >= 0) return fail("tx_duplicate");
      if (t.guest_size != t.size || !t.ranges.empty()) return fail("tx_order");
      int member = -1;
      for (size_t i = 0; i < std::size(devtx::kAllowed); ++i)
        if (out.tx_level == devtx::kAllowed[i].level && role == devtx::kAllowed[i].role &&
            (devtx::kAllowed[i].versions & devtx::VersionBit(out.tx_version)))
          member = int(i);
      if (member < 0) return fail("tx_role");
      for (const auto& other : out.files)
        if (other.tx_member == member) return fail("tx_duplicate");
      const devtx::Member& a = devtx::kAllowed[size_t(member)];
      if (!devtx::NameIs(t.path, a.name) || t.size != a.size || orig != a.sha256)
        return fail("tx_identity");
      if (a.max_grow == 0 ? guest != t.size : (guest <= t.size || guest - t.size > a.max_grow))
        return fail("tx_bounds");
      // G5-P3: one physical read of the whole member; every later check and every guest read uses these bytes
      uint64_t held = 0;
      for (const auto& other : out.files)
        if (other.tx_snapshot) held += other.tx_snapshot->size() + other.tx_guest;
      if (held + t.size + guest > devtx::kMaxSnapshotBytes) return fail("tx_snapshot_budget");
      auto all = std::make_shared<std::vector<uint8_t>>();
      ++devtx::MemberDiskReads();
      if (!ReadAt(t.path, 0, t.size, *all) || devtx::Sha256Hex(all->data(), all->size()) != orig)
        return fail("tx_identity");
      t.tx_snapshot = std::move(all);
      t.tx_member = member;
      t.tx_guest = guest;
      t.tx_orig = orig;
      t.tx_result = result;
#endif
    } else if (kind == "grow") {
      std::string index_text, size_text, extra;
      ls >> index_text >> size_text >> extra;
      uint64_t index = 0, guest = 0;
      if (!ParseU64(index_text, index) || !ParseU64(size_text, guest) || !extra.empty()) return fail("bad_grow");
      if (index >= out.files.size()) return fail("grow_file");
      Target& t = out.files[size_t(index)];
#if defined(R3HD_LEVEL_TX)
      // G5-P1: a level transaction's member grows only to the size its `tx-file` declares (bounded there)
      const bool tx_grow = t.tx_member >= 0;
      if (tx_grow && guest != t.tx_guest) return fail("tx_bounds");
#else
      const bool tx_grow = false;
#endif
      if (!GrowAllowed(t.path) && !tx_grow) return fail("grow_not_allowed");
      if (t.guest_size != t.size || !t.ranges.empty()) return fail("grow_order");
      if (guest <= t.size || (!tx_grow && guest - t.size > kMaxGrowBytes)) return fail("grow_bounds");
      t.guest_size = guest;
      out.grown = true;
    } else if (kind == "range") {
      std::string index_text, offset_text, length_text, base_text, result_text, mod, rest;
      ls >> index_text >> offset_text >> length_text >> base_text >> result_text >> mod;
      std::getline(ls >> std::ws, rest);
      uint64_t index = 0;
      Range r;
      if (!ParseU64(index_text, index) || !ParseU64(offset_text, r.offset) || !ParseU64(length_text, r.length) ||
          !ParseHex64(base_text, r.base) || !ParseHex64(result_text, r.result) || rest.empty())
        return fail("bad_range");
      if (index >= out.files.size()) return fail("range_file");
      bool known = false;
      for (const auto& m : out.mods) known |= m.substr(0, m.find(' ')) == mod;
      if (!known) return fail("range_mod");
      Target& t = out.files[size_t(index)];
      if (r.length == 0 || r.length > kMaxRangeBytes || r.offset > t.guest_size ||
          r.length > t.guest_size - r.offset)
        return fail("range_bounds");
      if (++out.range_count > kMaxRanges) return fail("too_many_ranges");
      out.bytes += r.length;
      if (out.bytes > kMaxTotalBytes) return fail("too_many_bytes");
      const std::filesystem::path blob = FromUtf8(rest);
      uint64_t blob_size = 0;
      if (!blob.is_absolute() || !PlainFile(blob, &blob_size) || blob_size != r.length) return fail("blob_size");
      if (!ReadAt(blob, 0, r.length, r.data) || Fnv1a(r.data.data(), r.data.size()) != r.result)
        return fail("blob_hash");
      // M36: only the part inside the file has game bytes (none for a range wholly past its end).
      const uint64_t inside = r.offset >= t.size ? 0 : std::min(r.length, t.size - r.offset);
      std::vector<uint8_t> own;
#if defined(R3HD_LEVEL_TX)
      if (t.tx_snapshot && inside)  // G5-P3: a member's own bytes come from its snapshot, never from disk again
        own.assign(t.tx_snapshot->begin() + size_t(r.offset), t.tx_snapshot->begin() + size_t(r.offset + inside));
      else
#endif
      if (inside && !ReadAt(t.path, r.offset, inside, own)) return fail("game_bytes_hash");
      if (Fnv1a(own.data(), own.size()) != r.base) return fail("game_bytes_hash");
      r.mod = mod;
      t.ranges.push_back(std::move(r));
    } else if (kind == "gameplay") {
      std::string id, extra;
      ls >> id >> extra;
      if (!SafeToken(id) || !extra.empty()) return fail("bad_gameplay");
      bool known = false;
      for (const auto& m : out.mods) known |= m.substr(0, m.find(' ')) == id;
      if (!known) return fail("gameplay_mod");
      if (std::find(out.gameplay.begin(), out.gameplay.end(), id) != out.gameplay.end())
        return fail("duplicate_gameplay");
      out.gameplay.push_back(id);
    } else if (kind == "end") {
      uint64_t files = 0, ranges = 0;
      std::string a, b;
      ls >> a >> b;
      if (!ParseU64(a, files) || !ParseU64(b, ranges) || files != out.files.size() || ranges != out.range_count)
        return fail("bad_end");
      ended = true;
    } else if (!kind.empty() && kind[0] == '#') {
      continue;
    } else {
      return fail("unknown_record");
    }
  }
  if (n == 0) return "plan_empty";
  if (!ended) return "plan_truncated";
  for (auto& t : out.files) {
    std::sort(t.ranges.begin(), t.ranges.end(), [](const Range& a, const Range& b) { return a.offset < b.offset; });
    for (size_t i = 1; i < t.ranges.size(); ++i)
      if (t.ranges[i].offset < t.ranges[i - 1].offset + t.ranges[i - 1].length) return "ranges_overlap";
    if (t.guest_size > t.size) {  // M36: every byte past the file's end belongs to a range
      uint64_t covered = t.size;
      for (const auto& r : t.ranges) {
        if (r.offset + r.length <= covered) continue;
        if (r.offset > covered) break;
        covered = r.offset + r.length;
      }
      if (covered != t.guest_size) return "grow_uncovered";
    }
  }
#if defined(R3HD_LEVEL_TX)
  // G5-P1 (D-243): the transaction is complete and its image is the one declared, or the whole plan is refused.
  if (out.tx) {
    std::string canonical = "level-tx " + out.tx_version + " " + out.tx_level + " " + out.tx_mod + "\n";
    for (size_t i = 0; i < std::size(devtx::kAllowed); ++i) {
      const devtx::Member& a = devtx::kAllowed[i];
      if (out.tx_level != a.level || !(a.versions & devtx::VersionBit(out.tx_version))) continue;
      Target* t = nullptr;
      for (auto& f : out.files)
        if (f.tx_member == int(i)) t = &f;
      if (!t) return "tx_incomplete";
      if (t->guest_size != t->tx_guest) return "tx_incomplete";
      if (!t->tx_snapshot || t->tx_snapshot->size() != t->size) return "tx_identity";
      std::vector<uint8_t> image;  // G5-P3: the snapshot, not a second read from disk (one allocation)
      image.reserve(size_t(t->guest_size));
      image.assign(t->tx_snapshot->begin(), t->tx_snapshot->end());
      image.resize(size_t(t->guest_size), 0);
      size_t own = 0;
      for (const auto& r : t->ranges) {
        if (r.mod != out.tx_mod) continue;
        std::memcpy(image.data() + r.offset, r.data.data(), r.data.size());
        ++own;
      }
      if (!own) return "tx_incomplete";
      if (std::string(a.role) == "ptr" &&
          (t->ranges.size() != 1 || t->ranges[0].offset != 0 || t->ranges[0].length != t->guest_size))
        return "tx_ptr_cover";  // the rebuilt pointer table is one range of the transaction's mod
      if (devtx::Sha256Hex(image.data(), image.size()) != t->tx_result) return "tx_result_hash";
      {  // G6-P30 (D-286): the production content policy on the declared image (before any other mod's ranges)
        const std::string why = devtx::ProductionContent(a, *t->tx_snapshot, image, t->tx_result);
        if (!why.empty()) return why;
      }
      // G5-P3: the view the guest is served: the declared image plus any other mod's (disjoint, verified) ranges
      for (const auto& r : t->ranges)
        if (r.mod != out.tx_mod) std::memcpy(image.data() + r.offset, r.data.data(), r.data.size());
      t->tx_image = std::make_shared<const std::vector<uint8_t>>(std::move(image));
      canonical += std::string("tx-file ") + a.role + " " + a.name + " " + std::to_string(t->size) + " " +
                   t->tx_orig + " " + std::to_string(t->guest_size) + " " + t->tx_result + "\n";
    }
    for (const auto& f : out.files)
      if (f.tx_member < 0 && f.guest_size > f.size && !GrowAllowed(f.path)) return "tx_incomplete";
    const std::string id = devtx::Sha256Hex(reinterpret_cast<const uint8_t*>(canonical.data()), canonical.size());
    if (id.substr(0, 16) != out.tx_id) return "tx_id";
    for (auto& f : out.files) f.tx_snapshot.reset();  // G5-P3: the images hold every byte the guest can read
  }
#endif
  return {};
}

// Lays the part of `data` (file offset `data_offset`) inside the read [read_offset, +length) over `buffer`.
inline size_t Overlay(uint8_t* buffer, uint64_t read_offset, size_t length, const uint8_t* data, uint64_t data_offset,
                      size_t data_size) {
  const uint64_t lo = std::max(read_offset, data_offset);
  const uint64_t hi = std::min(read_offset + length, data_offset + data_size);
  if (hi <= lo) return 0;
  std::memcpy(buffer + (lo - read_offset), data + (lo - data_offset), size_t(hi - lo));
  return size_t(hi - lo);
}

// File name against file name, ASCII letters without case (the game's files have ASCII names).
inline bool SameFileName(const std::filesystem::path& a, const std::filesystem::path& b) {
  const auto x = a.filename().native(), y = b.filename().native();
  if (x.size() != y.size()) return false;
  for (size_t i = 0; i < x.size(); ++i) {
    auto p = x[i], q = y[i];
    if (p >= 'A' && p <= 'Z') p = p + 32;
    if (q >= 'A' && q <= 'Z') q = q + 32;
    if (p != q) return false;
  }
  return true;
}

struct State {
  std::mutex mutex;
  void (*log)(const char*) = nullptr;
  bool loaded = false, active = false;
  Plan plan;
  std::unordered_map<std::filesystem::path::string_type, Target*> lookup;  // host path -> target or nullptr
};
inline State& state() {
  static State s;
  return s;
}

inline void Log(State& s, const std::string& line) {
  if (s.log) s.log(line.c_str());
}

// Loads the plan named by `plan_path` once per process (or per test call with `force_plan`).
inline void EnsureLoaded(State& s, const std::filesystem::path& plan_path) {
  if (s.loaded) return;
  s.loaded = true;
  const std::string reason = Load(plan_path, s.plan);
  if (!reason.empty()) {
    s.plan = Plan{};
    Log(s, "M33 mods state=refused reason=" + reason);
    return;
  }
  s.active = true;
  Log(s, "M33 mods state=active mods=" + std::to_string(s.plan.mods.size()) + " files=" +
             std::to_string(s.plan.files.size()) + " ranges=" + std::to_string(s.plan.range_count) +
             " bytes=" + std::to_string(s.plan.bytes));
  for (const auto& t : s.plan.files)
    if (t.guest_size > t.size)
      Log(s, "M36 grow file=" + t.path.filename().string() + " host_size=" + std::to_string(t.size) +
                 " guest_size=" + std::to_string(t.guest_size));
  for (const auto& m : s.plan.mods) Log(s, "M33 mods mod=" + m.substr(0, m.find(' ')) + " version=" +
                                               m.substr(m.find(' ') + 1));
  for (const auto& id : s.plan.gameplay) Log(s, "M33 mods gameplay mod=" + id + " achievements=not_awarded");
#if defined(R3HD_LEVEL_TX)
  if (s.plan.tx && s.plan.tx_version != "1")
    Log(s, "M33 level-tx version=" + s.plan.tx_version + " members=lvl,ptr,transit (production policy D-286)");
  if (s.plan.tx)
    Log(s, "M33 level-tx active level=" + s.plan.tx_level + " mod=" + s.plan.tx_mod + " id=" + s.plan.tx_id +
               " (production policy D-286)");
  for (const auto& t : s.plan.files)
    if (t.tx_image)
      Log(s, "G5P3 tx snapshot file=" + t.path.filename().string() + " host_size=" + std::to_string(t.size) +
                 " image_bytes=" + std::to_string(t.tx_image->size()) + " disk_reads=" +
                 std::to_string(devtx::MemberDiskReads()));
#endif
}

// D-224: true while the verified, active plan names a mod that changes game logic. Loads the plan if no game file
// was read yet; false without R3HD_MODS_PLAN, for a refused plan and for a plan without `gameplay` records.
inline bool GameplayModsActive(const std::filesystem::path* force_plan = nullptr) {
  if (!(force_plan || Enabled())) return false;
  State& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  if (!s.loaded) EnsureLoaded(s, force_plan ? *force_plan : PlanVariable());
  return s.active && !s.plan.gameplay.empty();
}

inline Target* Find(State& s, const std::filesystem::path& host_path) {
  auto it = s.lookup.find(host_path.native());
  if (it != s.lookup.end()) return it->second;
  Target* found = nullptr;
#if defined(R3HD_LEVEL_TX)
  // G5-P3: a member is matched by its path too, so a replaced or removed file still maps to its image
  for (auto& t : s.plan.files)
    if (!found && t.tx_image && t.path.lexically_normal() == host_path.lexically_normal()) found = &t;
#endif
  for (auto& t : s.plan.files) {
    if (found) break;
    std::error_code ec;
    if (SameFileName(t.path, host_path) && std::filesystem::equivalent(t.path, host_path, ec) && !ec) {
      found = &t;
      break;
    }
  }
  if (s.lookup.size() < 16384) s.lookup.emplace(host_path.native(), found);
  return found;
}

// After a successful host read of `length` bytes at `offset` into `buffer`: serves the plan's bytes where its
// ranges overlap the read. Returns the bytes replaced. `force_plan` is for the deterministic test.
inline size_t AfterRead(const std::filesystem::path& host_path, uint64_t offset, uint8_t* buffer, size_t length,
                        const std::filesystem::path* force_plan = nullptr) {
  if (!length || !(force_plan || Enabled())) return 0;
  State& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  if (!s.loaded) EnsureLoaded(s, force_plan ? *force_plan : PlanVariable());
  if (!s.active) return 0;
  Target* t = Find(s, host_path);
  if (!t) return 0;
  size_t replaced = 0;
#if defined(R3HD_LEVEL_TX)
  if (t->tx_image)  // G5-P3: the read is the image's bytes (laid again so no earlier overlay can alter a member)
    Overlay(buffer, offset, length, t->tx_image->data(), 0, t->tx_image->size());
#endif
  for (auto& r : t->ranges) {
    if (r.offset >= offset + length) break;
    if (r.offset + r.length <= offset) continue;
    const size_t here = Overlay(buffer, offset, length, r.data.data(), r.offset, r.data.size());
    r.served += here;
    replaced += here;
    if (!r.logged) {
      r.logged = true;
      Log(s, "M33 mods served mod=" + r.mod + " file=" + t->path.filename().string() + " offset=" +
                 std::to_string(r.offset) + " length=" + std::to_string(r.length));
    }
  }
  return replaced;
}

// M36 (D-073): the size the guest is told for a game file whose entry is being created or refreshed (host size
// `size`). Unchanged unless the active plan grows that file and the file still has the size the plan was made for.
inline size_t GuestSize(const std::filesystem::path& host_path, size_t size, void (*log)(const char*) = nullptr,
                        const std::filesystem::path* force_plan = nullptr) {
  if (!(force_plan || Enabled())) return size;
  State& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  if (log) s.log = log;
  if (!s.loaded) EnsureLoaded(s, force_plan ? *force_plan : PlanVariable());
  if (!s.active || !s.plan.grown) return size;
  Target* t = Find(s, host_path);
#if defined(R3HD_LEVEL_TX)
  if (t && t->tx_image) {  // G5-P3: a member's guest size is its image's, whatever the file on disk became
    if (uint64_t(size) != t->size && !t->tx_changed_logged) {
      t->tx_changed_logged = true;
      Log(s, "G5P3 tx host_changed file=" + t->path.filename().string() + " host_size=" + std::to_string(size) +
                 " verified_size=" + std::to_string(t->size) + " served=image");
    }
    if (!t->size_logged) {
      t->size_logged = true;
      Log(s, "M36 grow size file=" + t->path.filename().string() + " host_size=" + std::to_string(t->size) +
                 " guest_size=" + std::to_string(t->guest_size));
    }
    return size_t(t->tx_image->size());
  }
#endif
  if (!t || t->guest_size == t->size || uint64_t(size) != t->size) return size;
  if (!t->size_logged) {
    t->size_logged = true;
    Log(s, "M36 grow size file=" + t->path.filename().string() + " host_size=" + std::to_string(t->size) +
               " guest_size=" + std::to_string(t->guest_size));
  }
  return size_t(t->guest_size);
}

// M36 (D-073): right after the host read of `length` bytes at `offset` (result `host_ok`, count in *bytes_read) of a
// file the plan grows: a read that reaches past the file's end is completed up to the guest size with zero bytes,
// which AfterRead then replaces by the plan's ranges (they cover the whole tail). Returns the read's result; never
// writes outside buffer[0, length). Any other file, a short or failed host read inside the file, and a read at or
// past the guest size keep the host's result.
inline bool ExtendRead(const std::filesystem::path& host_path, uint64_t offset, uint8_t* buffer, size_t length,
                       bool host_ok, size_t* bytes_read, void (*log)(const char*) = nullptr,
                       const std::filesystem::path* force_plan = nullptr) {
  if (!length || !bytes_read || !(force_plan || Enabled())) return host_ok;
  State& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  if (log) s.log = log;
  if (!s.loaded) EnsureLoaded(s, force_plan ? *force_plan : PlanVariable());
  if (!s.active || !s.plan.grown) return host_ok;
  Target* t = Find(s, host_path);
#if defined(R3HD_LEVEL_TX)
  if (t && t->tx_image) {  // G5-P3: every byte of a member comes from its image; the host's bytes are discarded
    const auto& img = *t->tx_image;
    const size_t n = offset >= img.size() ? 0 : size_t(std::min<uint64_t>(length, img.size() - offset));
    if (n) std::memcpy(buffer, img.data() + size_t(offset), n);
    const uint64_t host = host_ok ? *bytes_read : 0;
    *bytes_read = n;
    ++t->tx_reads;
    if (offset == 0 && ++t->tx_passes <= kMaxGrowLogLines)
      Log(s, "G5P3 tx pass file=" + t->path.filename().string() + " pass=" + std::to_string(t->tx_passes) +
                 " reads_before=" + std::to_string(t->tx_reads - 1) + " image_bytes=" + std::to_string(img.size()));
    if (t->tx_reads <= kMaxGrowLogLines)
      Log(s, "G5P3 tx read file=" + t->path.filename().string() + " offset=" + std::to_string(offset) + " length=" +
                 std::to_string(length) + " host=" + std::to_string(host) + " served=" + std::to_string(n) +
                 " kind=" + (n ? "image" : "end"));
    return n > 0;
  }
#endif
  if (!t || t->guest_size == t->size) return host_ok;
  const uint64_t got = host_ok ? *bytes_read : 0;
  size_t served = size_t(got);
  bool result = host_ok;
  const char* what = "host";
  if (offset >= t->guest_size) {
    what = "end";
  } else if (offset + length > t->size) {
    const uint64_t inside = offset >= t->size ? 0 : t->size - offset;
    if (got == inside && (host_ok || inside == 0)) {
      const uint64_t want = std::min<uint64_t>(length, t->guest_size - offset);
      std::memset(buffer + inside, 0, size_t(want - inside));
      *bytes_read = size_t(want);
      served = size_t(want);
      result = true;
      what = "tail";
    } else {
      what = "short";
    }
  }
  if (++t->grow_reads <= kMaxGrowLogLines)
    Log(s, "M36 grow read file=" + t->path.filename().string() + " offset=" + std::to_string(offset) + " length=" +
               std::to_string(length) + " host=" + std::to_string(got) + " served=" + std::to_string(served) +
               " kind=" + what);
  return result;
}

// Test only: forget the loaded plan.
inline void ResetForTest() {
  State& s = state();
  std::lock_guard<std::mutex> lock(s.mutex);
  s.loaded = s.active = false;
  s.plan = Plan{};
  s.lookup.clear();
}

}  // namespace m33mods
