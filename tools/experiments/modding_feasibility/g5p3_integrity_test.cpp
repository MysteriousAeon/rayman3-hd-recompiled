// G5-P3 (D-246, E-479): deterministic adversarial test of the development-only level transaction's resource integrity
// (T1-T8 of the G5-P3 brief) on SYNTHETIC fixtures only (random bytes written by g5p3_integrity.py under
// private/work/e479/fixtures; never the game's files). Starts no game.
//
// usage: g5p3_integrity_test FIXTURES MODE      MODE = dev | prod | budget
//   FIXTURES/pristine: intro_10.lvl, intro_10.ptr, blobs, plan.txt, plan_badmeta.txt, plan_badid.txt (their paths
//   name FIXTURES/live); FIXTURES/v2: a second, same-size "version" of both members; FIXTURES/expect: the two guest
//   images. Before every scenario FIXTURES/live is rebuilt from pristine (only files this test made are deleted).
// The guest is emulated as HostPathFile / HostPathEntry do it: an open asks GuestSize with the size on disk (the last
// known size once the file is gone, as HostPathEntry::update keeps it), then reads 64 KiB chunks, each chunk a FRESH
// read of the file on disk at that moment (stricter than one open handle), through ExtendRead and AfterRead.
// Every scenario prints PASS|FAIL against the snapshot model; the reproduction (the G5-P2b header) is the same binary
// built without the snapshot, judged by g5p3_integrity.py against its pre-registered expectations.
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "m33_mod_overlay.h"

namespace fs = std::filesystem;
static std::vector<std::string> g_log;
static void LogLine(const char* line) { g_log.emplace_back(line); }
static fs::path g_root, g_live;
static std::map<std::string, size_t> g_last_size;

static std::vector<uint8_t> ReadAll(const fs::path& p) {
  std::ifstream f(p, std::ios::binary);
  return std::vector<uint8_t>((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
}
static void WriteAll(const fs::path& p, const std::vector<uint8_t>& b) {
  std::ofstream f(p, std::ios::binary | std::ios::trunc);
  f.write(reinterpret_cast<const char*>(b.data()), std::streamsize(b.size()));
}
static void SetEnv(const char* v) {
#ifdef _WIN32
  _putenv_s("R3HD_DEV_STRUCTURAL_TX", v ? v : "");
#else
  if (!v) unsetenv("R3HD_DEV_STRUCTURAL_TX"); else setenv("R3HD_DEV_STRUCTURAL_TX", v, 1);
#endif
}
static fs::path Lvl() { return g_live / "intro_10.lvl"; }
static fs::path Ptr() { return g_live / "intro_10.ptr"; }
static fs::path Plan(const char* name = "plan.txt") { return g_live / name; }

// live <- pristine (live holds only regular files this test copied)
static void Restore() {
  std::error_code ec;
  if (fs::exists(g_live)) {
    for (const auto& e : fs::recursive_directory_iterator(g_live))
      if (!e.is_regular_file() && !e.is_directory()) {
        std::cerr << "unexpected entry in live: " << e.path() << "\n";
        std::exit(3);
      }
    fs::remove_all(g_live);
  }
  fs::copy(g_root / "pristine", g_live, fs::copy_options::recursive);
  g_last_size.clear();
}

static uint64_t g_host_reads = 0;
// One guest open of `path`: its size, then every byte up to it, each chunk read from disk at that moment.
// `between(off)` runs before the chunk at `off` (to change files mid-read).
static std::pair<size_t, std::vector<uint8_t>> Open(const fs::path& path, const fs::path& plan,
                                                    const std::function<void(size_t)>& between = nullptr) {
  std::error_code ec;
  size_t disk = g_last_size.count(path.string()) ? g_last_size[path.string()] : 0;
  if (fs::exists(path, ec)) disk = size_t(fs::file_size(path, ec));
  g_last_size[path.string()] = disk;
  const size_t guest = m33mods::GuestSize(path, disk, &LogLine, &plan);
  std::vector<uint8_t> out;
  const size_t chunk = 65536;
  for (size_t off = 0; off < guest; off += chunk) {
    if (between) between(off);
    const size_t len = std::min(chunk, guest - off);
    std::vector<uint8_t> buf(len, 0xCD);
    size_t got = 0;
    {
      std::ifstream f(path, std::ios::binary);
      ++g_host_reads;
      if (f) {
        f.seekg(std::streamoff(off));
        f.read(reinterpret_cast<char*>(buf.data()), std::streamsize(len));
        got = size_t(f.gcount());
      }
    }
    const bool ok = m33mods::ExtendRead(path, off, buf.data(), len, got > 0, &got, &LogLine, &plan);
    if (!ok) break;
    m33mods::AfterRead(path, off, buf.data(), got, &plan);
    out.insert(out.end(), buf.begin(), buf.begin() + got);
    if (got < len) break;
  }
  return {guest, out};
}

static std::string State() {
  std::string st = "none";
  for (const auto& l : g_log) {
    if (l.rfind("M33 mods state=active", 0) == 0) st = "active";
    const auto at = l.find("state=refused reason=");
    if (at != std::string::npos) {
      const auto e = l.find('@', at);
      st = l.substr(at + 21, e == std::string::npos ? std::string::npos : e - at - 21);
    }
  }
  return st;
}

// Activation: what the guest's first call does (the size of the first file opened).
static void Activate(const fs::path& first, const fs::path& plan, const char* env = "intro_10") {
  m33mods::ResetForTest();
  g_log.clear();
  SetEnv(env);
  m33mods::state().log = &LogLine;
  std::error_code ec;
  const size_t disk = size_t(fs::file_size(first, ec));
  g_last_size[first.string()] = disk;
  m33mods::GuestSize(first, disk, &LogLine, &plan);
}

static void Flip(const fs::path& p, uint64_t off, size_t n = 4096) {
  std::fstream f(p, std::ios::binary | std::ios::in | std::ios::out);
  std::vector<char> b(n);
  f.seekg(std::streamoff(off));
  f.read(b.data(), std::streamsize(n));
  for (auto& c : b) c = char(c ^ 0x5A);
  f.seekp(std::streamoff(off));
  f.write(b.data(), std::streamsize(n));
}
static void Replace(const fs::path& p, const fs::path& src) {  // write a new file, then rename it over the old
  const fs::path tmp = p.string() + ".new";
  fs::copy_file(src, tmp, fs::copy_options::overwrite_existing);
  fs::rename(tmp, p);
}

static int g_total = 0, g_pass = 0;
static void Report(const std::string& name, bool ok, const std::string& why) {
  ++g_total;
  g_pass += ok;
  std::cout << (ok ? "PASS " : "FAIL ") << name << " (" << State() << ")" << (ok ? "" : " ::" + why) << "\n";
}

static std::vector<uint8_t> E_LVL, E_PTR;
// Both members as the guest would see them, in `order`, compared with the expected images.
static bool Views(const std::string& order, const fs::path& plan, std::string& why, bool expect_images = true,
                  const std::vector<uint8_t>* disk_lvl = nullptr, const std::vector<uint8_t>* disk_ptr = nullptr) {
  bool ok = true;
  for (char c : order) {
    const bool lvl = c == 'L';
    const auto [size, bytes] = Open(lvl ? Lvl() : Ptr(), plan);
    const std::vector<uint8_t>& want = expect_images ? (lvl ? E_LVL : E_PTR) : *(lvl ? disk_lvl : disk_ptr);
    if (size != want.size() || bytes != want) {
      ok = false;
      size_t diff = 0;
      while (diff < std::min(bytes.size(), want.size()) && bytes[diff] == want[diff]) ++diff;
      why += std::string(" ") + c + ":size=" + std::to_string(size) + "/" + std::to_string(want.size()) +
             ",got=" + std::to_string(bytes.size()) + ",first_diff=" + std::to_string(diff);
    }
  }
  return ok;
}

#ifdef R3HD_DEVTX_SNAPSHOT_BUDGET
static bool SnapshotInvariants(std::string& why) {
  auto& s = m33mods::state();
  uint64_t images = 0;
  int members = 0;
  for (const auto& t : s.plan.files) {
    if (t.tx_member < 0) continue;
    ++members;
    if (!t.tx_image) why += " no_image";
    if (t.tx_snapshot) why += " snapshot_kept";
    if (t.tx_image) images += t.tx_image->size();
  }
  if (members != 2) why += " members=" + std::to_string(members);
  if (images != E_LVL.size() + E_PTR.size()) why += " image_bytes=" + std::to_string(images);
  if (images > m33mods::devtx::kMaxSnapshotBytes) why += " over_budget";
  return why.empty();
}
#endif

static void Dev() {
  const char* orders[] = {"LP", "PL"};
  for (const char* o : orders) {
    const std::string sfx = std::string("_") + (o[0] == 'L' ? "lvl_first" : "ptr_first");
    const fs::path first = o[0] == 'L' ? Lvl() : Ptr();
    std::string why;
    // T0: baseline, repeated opens
    Restore();
#ifdef R3HD_DEVTX_SNAPSHOT_BUDGET
    const uint64_t reads0 = m33mods::devtx::MemberDiskReads();
#endif
    Activate(first, Plan());
    bool ok = State() == "active" && Views(std::string(o) + o + o, Plan(), why);
#ifdef R3HD_DEVTX_SNAPSHOT_BUDGET
    ok = ok && SnapshotInvariants(why);
    if (m33mods::devtx::MemberDiskReads() - reads0 != 2) {
      ok = false;
      why += " member_disk_reads=" + std::to_string(m33mods::devtx::MemberDiskReads() - reads0);
    }
#endif
    Report("T0_baseline_repeated" + sfx, ok, why);
    // T1: same-size mutation of bytes no range covers, after activation, then mid-read
    why.clear();
    Restore();
    Activate(first, Plan());
    ok = Views(o, Plan(), why);
    Flip(Lvl(), 2000000);
    Flip(Ptr(), 100000);
    ok = Views(std::string(o) + o, Plan(), why) && ok && State() == "active";
    Report("T1_same_size_after_activation" + sfx, ok, why);
    why.clear();
    Restore();
    Activate(first, Plan());
    {
      const auto [size, bytes] = Open(Lvl(), Plan(), [](size_t off) {
        if (off == 65536) Flip(Lvl(), 3000000);
      });
      ok = size == E_LVL.size() && bytes == E_LVL;
      if (!ok) why += " lvl mid-read mutation reached the guest";
    }
    ok = Views(o, Plan(), why) && ok;
    Report("T1_same_size_mid_read" + sfx, ok, why);
    // T2: truncation and extension
    why.clear();
    Restore();
    Activate(first, Plan());
    fs::resize_file(Lvl(), 1000000);
    fs::resize_file(Ptr(), E_PTR.size() + 5000);
    ok = Views(std::string(o) + o, Plan(), why);
    Report("T2_truncate_extend" + sfx, ok, why);
    // T3: atomic replacement by another version
    why.clear();
    Restore();
    Activate(first, Plan());
    Replace(Lvl(), g_root / "v2" / "intro_10.lvl");
    Replace(Ptr(), g_root / "v2" / "intro_10.ptr");
    ok = Views(std::string(o) + o, Plan(), why);
    Report("T3_atomic_replace" + sfx, ok, why);
    // T4: removal after activation (and after a first read)
    why.clear();
    Restore();
    Activate(first, Plan());
    ok = Views(o, Plan(), why);
    fs::remove(Ptr());
    fs::remove(Lvl());
    ok = Views(std::string(o) + o, Plan(), why) && ok;
    Report("T4_removed_after_activation" + sfx, ok, why);
    // T5: mixed versions. Before activation: the whole transaction is refused, nothing served, files untouched.
    why.clear();
    Restore();
    Replace(Ptr(), g_root / "v2" / "intro_10.ptr");
    {
      const auto dl = ReadAll(Lvl()), dp = ReadAll(Ptr());
      Activate(first, Plan());
      ok = State() == "tx_identity" && Views(std::string(o) + o, Plan(), why, false, &dl, &dp) &&
           ReadAll(Lvl()) == dl && ReadAll(Ptr()) == dp;
    }
    Report("T5_mixed_before_activation_refused" + sfx, ok, why);
    // ... after activation: one member swapped for the other version; both still the verified pair
    why.clear();
    Restore();
    Activate(first, Plan());
    Replace(o[0] == 'L' ? Ptr() : Lvl(), g_root / "v2" / (o[0] == 'L' ? "intro_10.ptr" : "intro_10.lvl"));
    ok = Views(std::string(o) + o, Plan(), why);
    Report("T5_mixed_after_activation" + sfx, ok, why);
    // T6: changed between verification and the first read
    why.clear();
    Restore();
    Activate(first, Plan());
    Flip(Lvl(), 1500000);
    fs::resize_file(Ptr(), 1000);
    ok = Views(o, Plan(), why);
    Report("T6_between_verify_and_first_read" + sfx, ok, why);
    // T7: changed between a close and a reopen of the same resource
    why.clear();
    Restore();
    Activate(first, Plan());
    ok = Views(std::string(1, o[0]), Plan(), why);
    Flip(first, o[0] == 'L' ? 5000000 : 150000);
    ok = Views(std::string(1, o[0]), Plan(), why) && ok;
    ok = Views(std::string(1, o[1]), Plan(), why) && ok;
    Replace(o[1] == 'L' ? Lvl() : Ptr(), g_root / "v2" / (o[1] == 'L' ? "intro_10.lvl" : "intro_10.ptr"));
    ok = Views(std::string(1, o[1]), Plan(), why) && ok;
    Report("T7_between_reopens" + sfx, ok, why);
    // T8: plan / replacement tampering. After activation: no effect. Before: the whole transaction is refused.
    why.clear();
    Restore();
    Activate(first, Plan());
    WriteAll(Plan(), std::vector<uint8_t>(64, 'x'));
    for (const auto& e : fs::directory_iterator(g_live / "blobs"))
      WriteAll(e.path(), std::vector<uint8_t>(size_t(e.file_size()), 0));
    ok = Views(std::string(o) + o, Plan(), why);
    Report("T8_tamper_after_activation" + sfx, ok, why);
    const char* pre[][2] = {{"blob", "blob_hash"}, {"plan_badmeta.txt", "tx_result_hash"},
                            {"plan_badid.txt", "tx_id"}};
    for (const auto& p : pre) {
      why.clear();
      Restore();
      fs::path plan = Plan();
      if (std::string(p[0]) == "blob") {
        Flip(g_live / "blobs" / "r0.bin", 0, 1);
      } else {
        plan = Plan(p[0]);
      }
      const auto dl = ReadAll(Lvl()), dp = ReadAll(Ptr());
      Activate(first, plan);
      ok = State() == p[1] && Views(std::string(o) + o, plan, why, false, &dl, &dp) && ReadAll(Lvl()) == dl &&
           ReadAll(Ptr()) == dp;
      Report(std::string("T8_tamper_before_activation_") + p[0] + sfx, ok, why);
    }
    // the development variable unset: refused as a whole
    why.clear();
    Restore();
    {
      const auto dl = ReadAll(Lvl()), dp = ReadAll(Ptr());
      Activate(first, Plan(), nullptr);
      ok = State() == "level_tx_not_enabled" && Views(std::string(o), Plan(), why, false, &dl, &dp);
    }
    Report("no_dev_variable_refused" + sfx, ok, why);
  }
#ifdef R3HD_DEVTX_SNAPSHOT_BUDGET
  // lifetime: the images live exactly as long as the plan that owns them
  {
    std::string why;
    Restore();
    Activate(Lvl(), Plan());
    std::vector<std::weak_ptr<const std::vector<uint8_t>>> held;
    for (const auto& t : m33mods::state().plan.files)
      if (t.tx_image) held.emplace_back(t.tx_image);
    const bool alive = held.size() == 2 && !held[0].expired() && !held[1].expired();
    m33mods::ResetForTest();
    const bool gone = held.size() == 2 && held[0].expired() && held[1].expired();
    Report("lifetime_images_owned_by_plan", alive && gone, alive ? " not released" : " missing");
  }
#endif
}

static void Perf() {
  using clk = std::chrono::steady_clock;
  auto ms = [](clk::duration d) { return std::chrono::duration<double, std::milli>(d).count(); };
  Restore();
  double load = 1e9, lvl = 1e9, ptr = 1e9;
  for (int i = 0; i < 5; ++i) {
    auto t0 = clk::now();
    Activate(Lvl(), Plan());
    load = std::min(load, ms(clk::now() - t0));
    t0 = clk::now();
    Open(Lvl(), Plan());
    lvl = std::min(lvl, ms(clk::now() - t0));
    t0 = clk::now();
    Open(Ptr(), Plan());
    ptr = std::min(ptr, ms(clk::now() - t0));
  }
  std::printf("PERF state=%s load_ms=%.2f open_lvl_ms=%.2f open_ptr_ms=%.2f (min of 5)\n", State().c_str(), load, lvl,
              ptr);
}

#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#include <psapi.h>
#pragma comment(lib, "psapi.lib")
// Host committed memory of this process: (current private bytes, peak).
static std::pair<uint64_t, uint64_t> Committed() {
  PROCESS_MEMORY_COUNTERS_EX c{};
  GetProcessMemoryInfo(GetCurrentProcess(), reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&c), sizeof(c));
  return {c.PrivateUsage, c.PeakPagefileUsage};
}
#else
static std::pair<uint64_t, uint64_t> Committed() { return {0, 0}; }
#endif

// One activation in a fresh process: committed memory before, after, and the peak in between.
static void Mem() {
  Restore();
  const auto before = Committed();
  Activate(Lvl(), Plan());
  const auto after = Committed();
  std::printf("MEM state=%s private_before=%llu private_after=%llu peak_before=%llu peak_after=%llu\n",
              State().c_str(), (unsigned long long)before.first, (unsigned long long)after.first,
              (unsigned long long)before.second, (unsigned long long)after.second);
  Report("mem_activation", State() == "active", "");
}

int main(int argc, char** argv) {
  if (argc < 3) {
    std::cerr << "usage: g5p3_integrity_test FIXTURES dev|prod|budget\n";
    return 2;
  }
  g_root = argv[1];
  g_live = g_root / "live";
  const std::string mode = argv[2];
  E_LVL = ReadAll(g_root / "expect" / "intro_10.lvl");
  E_PTR = ReadAll(g_root / "expect" / "intro_10.ptr");
  if (mode == "dev") {
    Dev();
    Perf();
  } else if (mode == "mem") {
    Mem();
  } else {
    for (const char* o : {"LP", "PL"}) {
      std::string why;
      Restore();
      const auto dl = ReadAll(Lvl()), dp = ReadAll(Ptr());
      Activate(o[0] == 'L' ? Lvl() : Ptr(), Plan());
      const std::string want = mode == "prod" ? "unknown_record" : "tx_snapshot_budget";
      const bool ok = State() == want && Views(std::string(o) + o, Plan(), why, false, &dl, &dp);
      Report(mode + "_refused_" + (o[0] == 'L' ? "lvl_first" : "ptr_first"), ok, why);
    }
  }
  if (fs::exists(g_live)) fs::remove_all(g_live);
  SetEnv(nullptr);
  std::cout << "G5P3_INTEGRITY_TEST " << (g_pass == g_total && g_total ? "PASS " : "FAIL ") << g_pass << "/"
            << g_total << " host_chunk_reads=" << g_host_reads << "\n";
  return g_pass == g_total && g_total ? 0 : 1;
}
