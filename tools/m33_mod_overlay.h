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
//   end <file count> <range count>
//
// M36 (D-073): a `grow` record lets one file be longer for the guest than on disk: the size the guest is told (entry
// size: NtQueryFullAttributesFile, NtQueryInformationFile, NtQueryDirectoryFile) and the bytes it can read. Only a
// file named in kGrowNames may grow (the subtitle table, whose loader reads it sequentially and never asks its size,
// RE_NOTES "M35"), by at most kMaxGrowBytes; the record must precede that file's ranges, and the ranges must cover
// every byte past the file's end (no byte the plan does not define is ever served). A range's game-bytes hash covers
// only its part inside the file (a range wholly past the end hashes no bytes). Reads stop at the guest size with the
// host's own end-of-file result. Without a `grow` record nothing about a file's size changes; a runtime before M36
// refuses such a plan as a whole (unknown_record).
#pragma once
#include <algorithm>
#include <cctype>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
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
};
struct Plan {
  std::vector<std::string> mods;  // "id version"
  std::vector<Target> files;
  size_t range_count = 0;
  uint64_t bytes = 0;
  bool grown = false;  // M36: some file has guest_size > size
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
    } else if (kind == "grow") {
      std::string index_text, size_text, extra;
      ls >> index_text >> size_text >> extra;
      uint64_t index = 0, guest = 0;
      if (!ParseU64(index_text, index) || !ParseU64(size_text, guest) || !extra.empty()) return fail("bad_grow");
      if (index >= out.files.size()) return fail("grow_file");
      Target& t = out.files[size_t(index)];
      if (!GrowAllowed(t.path)) return fail("grow_not_allowed");
      if (t.guest_size != t.size || !t.ranges.empty()) return fail("grow_order");
      if (guest <= t.size || guest - t.size > kMaxGrowBytes) return fail("grow_bounds");
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
      if ((inside && !ReadAt(t.path, r.offset, inside, own)) || Fnv1a(own.data(), own.size()) != r.base)
        return fail("game_bytes_hash");
      r.mod = mod;
      t.ranges.push_back(std::move(r));
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
}

inline Target* Find(State& s, const std::filesystem::path& host_path) {
  auto it = s.lookup.find(host_path.native());
  if (it != s.lookup.end()) return it->second;
  Target* found = nullptr;
  for (auto& t : s.plan.files) {
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
