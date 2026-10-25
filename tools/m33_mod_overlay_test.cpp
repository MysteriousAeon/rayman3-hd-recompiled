// M33 (D-070): the mod overlay, deterministic checks. Host-only; every file is synthetic and lives in a temporary
// folder. A plan is read through AfterRead exactly as HostPathFile::ReadSync does; every refusal must leave every
// read unchanged.
#include "m33_mod_overlay.h"
#include <cstdio>

static int checks = 0, failures = 0;
static void Check(bool ok, const char* what) {
  ++checks;
  if (!ok) {
    ++failures;
    std::printf("FAIL %s\n", what);
  }
}

namespace fs = std::filesystem;

static std::vector<uint8_t> Pattern(size_t size, uint32_t seed) {
  std::vector<uint8_t> v(size);
  for (size_t i = 0; i < size; ++i) {
    seed = seed * 1664525u + 1013904223u;
    v[i] = uint8_t(seed >> 24);
  }
  return v;
}
static void Write(const fs::path& p, const std::vector<uint8_t>& d) {
  std::ofstream f(p, std::ios::binary | std::ios::trunc);
  f.write(reinterpret_cast<const char*>(d.data()), std::streamsize(d.size()));
}
static void WriteText(const fs::path& p, const std::string& s) {
  std::ofstream f(p, std::ios::binary | std::ios::trunc);
  f << s;
}
static std::string Hex(uint64_t v) {
  char b[17];
  std::snprintf(b, sizeof b, "%016llx", static_cast<unsigned long long>(v));
  return b;
}
static std::string U8(const fs::path& p) {
  auto s = p.u8string();
  return std::string(s.begin(), s.end());
}

// Reads the whole file through the overlay in pieces of `step` bytes.
static std::vector<uint8_t> ReadThrough(const fs::path& file, const fs::path& plan, size_t step) {
  std::vector<uint8_t> all;
  std::ifstream f(file, std::ios::binary);
  std::vector<uint8_t> buf(step);
  uint64_t offset = 0;
  while (f) {
    f.read(reinterpret_cast<char*>(buf.data()), std::streamsize(step));
    const size_t got = size_t(f.gcount());
    if (!got) break;
    m33mods::AfterRead(file, offset, buf.data(), got, &plan);
    all.insert(all.end(), buf.begin(), buf.begin() + got);
    offset += got;
  }
  return all;
}

static std::vector<std::string> g_log;
static void Collect(const char* line) { g_log.emplace_back(line); }

// M36 (D-073): HostPathFile::ReadSync as patched: the host read (a Win32 ReadFile at an offset: false at or past the
// end, a short count across it), ExtendRead, then AfterRead over the count. Guard bytes after `length` must survive.
static bool SyncRead(const fs::path& file, const fs::path& plan, uint64_t offset, uint8_t* buffer, size_t length,
                     size_t* n) {
  *n = 0;
  std::error_code ec;
  const uint64_t size = fs::file_size(file, ec);
  bool ok = false;
  if (offset < size) {
    std::ifstream f(file, std::ios::binary);
    f.seekg(std::streamoff(offset));
    f.read(reinterpret_cast<char*>(buffer), std::streamsize(length));
    *n = size_t(f.gcount());
    ok = true;
  }
  ok = m33mods::ExtendRead(file, offset, buffer, length, ok, n, nullptr, &plan);
  if (ok) m33mods::AfterRead(file, offset, buffer, *n, &plan);
  return ok;
}
// The whole file as the guest's sequential reads see it (step bytes per read, until a failed or empty read).
static std::vector<uint8_t> GuestReadAll(const fs::path& file, const fs::path& plan, size_t step, bool* guards_ok) {
  std::vector<uint8_t> all, buf(step + 16);
  uint64_t offset = 0;
  *guards_ok = true;
  for (int i = 0; i < 100000; ++i) {
    std::fill(buf.begin(), buf.end(), uint8_t(0xA5));
    size_t n = 0;
    if (!SyncRead(file, plan, offset, buf.data(), step, &n) || !n) break;
    for (size_t k = step; k < buf.size(); ++k) *guards_ok &= buf[k] == 0xA5;
    *guards_ok &= n <= step;
    all.insert(all.end(), buf.begin(), buf.begin() + n);
    offset += n;
  }
  return all;
}

static void GrowTests(const fs::path& dir) {
  const fs::path sub = dir / "VS.sub", btf = dir / "GAME2.BTF", tail_blob = dir / "tail.bin", in_blob = dir / "in.bin",
                 plan = dir / "grow_plan.txt";
  const auto own = Pattern(1000, 11);
  Write(sub, own);
  Write(btf, own);
  const auto inner = Pattern(100, 12), tail = Pattern(700, 13);
  Write(in_blob, inner);
  Write(tail_blob, tail);
  const uint64_t empty = m33mods::Fnv1a(nullptr, 0);
  auto H = [](const std::vector<uint8_t>& v) { return Hex(m33mods::Fnv1a(v.data(), v.size())); };
  auto own_hash = [&](size_t off, size_t len) { return Hex(m33mods::Fnv1a(own.data() + off, len)); };
  // A range across the end (800 .. 1500: 200 bytes inside, hashed) and one inside (100 .. 200).
  auto plan_for = [&](const fs::path& file, const std::string& grow, const std::string& tail_range) {
    return "R3HD_MOD_PLAN 1\nmod sub.t 1\nfile 1000 " + U8(file) + "\n" + grow + "range 0 100 100 " +
           own_hash(100, 100) + " " + H(inner) + " sub.t " + U8(in_blob) + "\n" + tail_range + "end 1 2\n";
  };
  const std::string across = "range 0 800 700 " + own_hash(800, 200) + " " + H(tail) + " sub.t " + U8(tail_blob) + "\n";
  const std::string good = plan_for(sub, "grow 0 1500\n", across);
  auto expected = own;
  expected.resize(800);
  std::copy(inner.begin(), inner.end(), expected.begin() + 100);
  expected.insert(expected.end(), tail.begin(), tail.end());

  WriteText(plan, good);
  m33mods::state().log = &Collect;
  for (size_t step : {size_t(4096), size_t(512), size_t(999), size_t(1000), size_t(1001), size_t(7), size_t(1)}) {
    m33mods::ResetForTest();
    bool guards = false;
    Check(GuestReadAll(sub, plan, step, &guards) == expected && guards,
          "grow: sequential reads return the plan's 1500 bytes, then the end, never past the buffer");
  }
  {
    m33mods::ResetForTest();
    g_log.clear();
    Check(m33mods::GuestSize(sub, 1000, nullptr, &plan) == 1500, "grow: the guest is told the grown size");
    Check(m33mods::GuestSize(sub, 999, nullptr, &plan) == 999, "grow: a file of another size keeps its size");
    Check(m33mods::GuestSize(btf, 1000, nullptr, &plan) == 1000, "grow: any other file keeps its size");
    bool grow_line = false, size_line = false;
    for (const auto& l : g_log) {
      grow_line |= l == "M36 grow file=VS.sub host_size=1000 guest_size=1500";
      size_line |= l == "M36 grow size file=VS.sub host_size=1000 guest_size=1500";
    }
    Check(grow_line && size_line, "grow: the plan and the size are logged");
    std::vector<uint8_t> b(64, 0xA5);
    size_t n = 7;
    Check(!SyncRead(sub, plan, 1500, b.data(), 32, &n) && n == 0, "grow: a read at the grown end is the host's end of file");
    Check(!SyncRead(sub, plan, 4000, b.data(), 32, &n) && n == 0, "grow: a read past the grown end is the end of file");
    Check(SyncRead(sub, plan, 1490, b.data(), 32, &n) && n == 10 &&
              std::equal(b.begin(), b.begin() + 10, tail.end() - 10) && b[10] == 0xA5,
          "grow: a read across the grown end stops there");
    Check(SyncRead(sub, plan, 1200, b.data(), 32, &n) && n == 32 && std::equal(b.begin(), b.begin() + 32, tail.begin() + 400),
          "grow: a read wholly past the host end serves the plan's bytes (seek then read)");
    std::vector<uint8_t> o(32);
    Check(SyncRead(btf, plan, 990, o.data(), 32, &n) && n == 10, "grow: another file still ends at its own end");
  }
  // A tail range wholly past the end (its game hash covers no byte) beside a range inside.
  {
    const std::string split = "range 0 800 200 " + own_hash(800, 200) + " " +
                              H(std::vector<uint8_t>(tail.begin(), tail.begin() + 200)) + " sub.t " +
                              U8(dir / "t1.bin") + "\nrange 0 1000 500 " + Hex(empty) + " " +
                              H(std::vector<uint8_t>(tail.begin() + 200, tail.end())) + " sub.t " + U8(dir / "t2.bin") + "\n";
    Write(dir / "t1.bin", std::vector<uint8_t>(tail.begin(), tail.begin() + 200));
    Write(dir / "t2.bin", std::vector<uint8_t>(tail.begin() + 200, tail.end()));
    std::string text = plan_for(sub, "grow 0 1500\n", split);
    text = text.substr(0, text.rfind("end 1 2")) + "end 1 3\n";
    WriteText(plan, text);
    m33mods::ResetForTest();
    bool guards = false;
    Check(GuestReadAll(sub, plan, 333, &guards) == expected && guards, "grow: a range wholly past the end is served");
  }
  struct Bad {
    const char* what;
    std::string text;
    const char* reason;
  };
  auto replace = [](std::string s, const std::string& from, const std::string& to) {
    const size_t at = s.find(from);
    if (at != std::string::npos) s.replace(at, from.size(), to);
    return s;
  };
  std::vector<Bad> bad = {
      {"grow of another file", plan_for(btf, "grow 0 1500\n", across), "grow_not_allowed"},
      {"grow after a range", "", "grow_order"},  // text set below
      {"grow not larger", replace(good, "grow 0 1500", "grow 0 1000"), "grow_bounds"},
      {"grow too large", replace(good, "grow 0 1500", "grow 0 " + std::to_string(1000 + (1u << 20) + 1)), "grow_bounds"},
      {"grow twice", replace(good, "grow 0 1500\n", "grow 0 1500\ngrow 0 1500\n"), "grow_order"},
      {"grow syntax", replace(good, "grow 0 1500", "grow 0 1500 x"), "bad_grow"},
      {"grow file index", replace(good, "grow 0 1500", "grow 3 1500"), "grow_file"},
      {"tail not covered", replace(good, "grow 0 1500", "grow 0 1600"), "grow_uncovered"},
      {"range past the grown end", replace(good, "grow 0 1500", "grow 0 1400"), "range_bounds"},
      {"no grow record", replace(good, "grow 0 1500\n", ""), "range_bounds"},
      {"tail game hash", replace(good, own_hash(800, 200), own_hash(800, 199)), "game_bytes_hash"},
      {"tail bytes", replace(good, H(tail), Hex(5)), "blob_hash"},
  };
  // grow after the file's first range: move the record behind the ranges.
  bad[1].text = replace(good, "grow 0 1500\n", "");
  bad[1].text = replace(bad[1].text, "range 0 800", "grow 0 1500\nrange 0 800");
  for (const auto& b : bad) {
    WriteText(plan, b.text);
    m33mods::ResetForTest();
    g_log.clear();
    bool guards = false;
    const bool unchanged = GuestReadAll(sub, plan, 4096, &guards) == own && guards &&
                           m33mods::GuestSize(sub, 1000, nullptr, &plan) == 1000;
    bool refused = false;
    for (const auto& l : g_log) refused |= l.rfind(std::string("M33 mods state=refused reason=") + b.reason, 0) == 0;
    if (!unchanged || !refused) std::printf("  grow case: %s (%s)\n", b.what, g_log.empty() ? "" : g_log.back().c_str());
    Check(unchanged && refused, "grow: a damaged plan is refused as a whole; size and bytes stay the file's own");
  }
  // Without any plan nothing changes (the variable is not set in the test process).
  {
    m33mods::ResetForTest();
    std::vector<uint8_t> b(32);
    size_t n = 5;
    Check(!m33mods::ExtendRead(sub, 1000, b.data(), 32, false, &n) && n == 5 && m33mods::GuestSize(sub, 1000) == 1000,
          "grow: without a plan the read result and the size are the host's");
  }
}

int main() {
  // M33 review: a folder name with non-ASCII letters (a Turkish home folder), in the plan and in the files it names.
  const fs::path dir = fs::temp_directory_path() / (std::wstring(L"m33_overlay_test_\u00C7\u011F\u00FC_") +
                                                    std::to_wstring(reinterpret_cast<uintptr_t>(&checks) & 0xFFFF));
  fs::create_directories(dir);
  const fs::path game = dir / "GAME.BTF", other = dir / "other.lvl", blob_a = dir / "a.bin", blob_b = dir / "b.bin";
  const auto game_bytes = Pattern(100000, 1), other_bytes = Pattern(5000, 2);
  Write(game, game_bytes);
  Write(other, other_bytes);
  const auto new_a = Pattern(3000, 3), new_b = Pattern(17, 4);
  Write(blob_a, new_a);
  Write(blob_b, new_b);
  const uint64_t off_a = 4096, off_b = 70001;
  auto base = [&](uint64_t off, size_t len) { return m33mods::Fnv1a(game_bytes.data() + off, len); };
  const std::string good =
      "R3HD_MOD_PLAN 1\n# test\nmod test.a 1.0.0\nmod test.b 2.1\n"
      "file " + std::to_string(game_bytes.size()) + " " + U8(game) + "\n"
      "range 0 " + std::to_string(off_a) + " 3000 " + Hex(base(off_a, 3000)) + " " +
      Hex(m33mods::Fnv1a(new_a.data(), new_a.size())) + " test.a " + U8(blob_a) + "\n"
      "range 0 " + std::to_string(off_b) + " 17 " + Hex(base(off_b, 17)) + " " +
      Hex(m33mods::Fnv1a(new_b.data(), new_b.size())) + " test.b " + U8(blob_b) + "\n"
      "end 1 2\n";
  auto expected = game_bytes;
  std::copy(new_a.begin(), new_a.end(), expected.begin() + off_a);
  std::copy(new_b.begin(), new_b.end(), expected.begin() + off_b);

  const fs::path plan = dir / "plan.txt";
  WriteText(plan, good);
  m33mods::state().log = &Collect;
  for (size_t step : {size_t(1) << 20, size_t(4096), size_t(4093), size_t(7), size_t(3001)}) {
    m33mods::ResetForTest();
    Check(ReadThrough(game, plan, step) == expected, "the plan's bytes replace exactly its ranges (uneven reads)");
  }
  Check(ReadThrough(other, plan, 999) == other_bytes, "a file outside the plan is unchanged");
  bool active = false, served = false;
  for (const auto& l : g_log) {
    active |= l == "M33 mods state=active mods=2 files=1 ranges=2 bytes=3017";
    served |= l.rfind("M33 mods served mod=test.a file=GAME.BTF offset=4096 length=3000", 0) == 0;
  }
  Check(active && served, "log: active line and one served line per range");
  // The same file under another name of the same path (case) is found through the file system's identity.
  {
    m33mods::ResetForTest();
    std::vector<uint8_t> b(17);
    std::copy(game_bytes.begin() + off_b, game_bytes.begin() + off_b + 17, b.begin());
    fs::path upper = dir / "game.btf";
    m33mods::AfterRead(upper, off_b, b.data(), b.size(), &plan);
    Check(b == new_b, "the file is matched without case, by identity");
  }

  // Every refusal leaves every read unchanged.
  struct Bad {
    const char* what;
    std::string text;
    const char* reason;  // the refusal reason the log must give
  };
  auto replace = [&](std::string s, const std::string& from, const std::string& to) {
    const size_t at = s.find(from);
    if (at != std::string::npos) s.replace(at, from.size(), to);
    return s;
  };
  const std::string first_range = "range 0 " + std::to_string(off_a) + " 3000 " + Hex(base(off_a, 3000));
  std::vector<Bad> bad = {
      {"bad header", replace(good, "R3HD_MOD_PLAN 1", "R3HD_MOD_PLAN 2"), "bad_header"},
      {"truncated (no end)", replace(good, "end 1 2\n", ""), "plan_truncated"},
      {"end count", replace(good, "end 1 2", "end 1 3"), "bad_end"},
      {"data after end", good + "mod test.c 1\n", "data_after_end"},
      {"unknown record", replace(good, "# test", "exec calc.exe"), "unknown_record"},
      {"file size", replace(good, "file " + std::to_string(game_bytes.size()), "file 99999"), "file_size"},
      {"game bytes changed", replace(good, Hex(base(off_a, 3000)), Hex(base(off_a, 3000) ^ 1)), "game_bytes_hash"},
      {"replacement changed", replace(good, Hex(m33mods::Fnv1a(new_a.data(), new_a.size())), Hex(1)), "blob_hash"},
      {"range past the end", replace(good, "range 0 " + std::to_string(off_b) + " 17", "range 0 99990 17"),
       "range_bounds"},
      // the second range moved into the first, with the right hash of the game's bytes there (M33 review)
      {"overlap", replace(good, "range 0 " + std::to_string(off_b) + " 17 " + Hex(base(off_b, 17)),
                          "range 0 5000 17 " + Hex(base(5000, 17))), "ranges_overlap"},
      {"unknown mod", replace(good, "17 " + Hex(base(off_b, 17)) + " " + Hex(m33mods::Fnv1a(new_b.data(), 17)) +
                                        " test.b", "17 " + Hex(base(off_b, 17)) + " " +
                                        Hex(m33mods::Fnv1a(new_b.data(), 17)) + " test.z"), "range_mod"},
      {"relative path", replace(good, "file " + std::to_string(game_bytes.size()) + " " + U8(game),
                                "file " + std::to_string(game_bytes.size()) + " GAME.BTF"), "file_missing"},
      {"file index", replace(good, first_range, "range 7 " + std::to_string(off_a) + " 3000 " + Hex(base(off_a, 3000))),
       "range_file"},
  };
  for (const auto& b : bad) {
    WriteText(plan, b.text);
    m33mods::ResetForTest();
    g_log.clear();
    const bool unchanged = ReadThrough(game, plan, 4096) == game_bytes;
    bool refused = false;
    for (const auto& l : g_log) refused |= l.rfind(std::string("M33 mods state=refused reason=") + b.reason, 0) == 0;
    if (!unchanged || !refused) std::printf("  case: %s (%s)\n", b.what, g_log.empty() ? "" : g_log.back().c_str());
    Check(unchanged && refused, "a damaged or mismatching plan is refused as a whole, for its own reason");
  }
  {
    m33mods::ResetForTest();
    g_log.clear();
    const fs::path missing = dir / "none.txt";
    Check(ReadThrough(game, missing, 4096) == game_bytes && !g_log.empty() &&
              g_log.back() == "M33 mods state=refused reason=plan_unreadable", "a missing plan changes nothing");
  }
  {
    // A blob of the wrong size is refused even with the right hash in the plan.
    Write(blob_b, Pattern(18, 4));
    WriteText(plan, good);
    m33mods::ResetForTest();
    g_log.clear();
    Check(ReadThrough(game, plan, 4096) == game_bytes && !g_log.empty() &&
              g_log.back().rfind("M33 mods state=refused reason=blob_size", 0) == 0,
          "a replacement file of the wrong size is refused");
  }
  GrowTests(dir);
  std::error_code ec;
  fs::remove_all(dir, ec);
  std::printf("M33_OVERLAY_TEST %s %d/%d\n", failures ? "FAIL" : "PASS", checks - failures, checks);
  return failures ? 1 : 0;
}
