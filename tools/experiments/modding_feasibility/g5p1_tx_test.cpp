// G5-P1 (D-243, E-476): deterministic test of the development-only `level-tx` overlay (g5p1_dev_gate.py) and of the
// production overlay on the same plans. Starts no game. Built by g5p1_pilot.py `negtest` twice against rendered
// headers: the patched development header (R3HD_DEV_STRUCTURAL_TX defined) and tools/m33_mod_overlay.h unchanged.
//
// argv[1]: a cases file, one case per line, fields separated by TAB:
//   name, plan path, environment value of R3HD_DEV_STRUCTURAL_TX ("-" = unset), expectation ("active" or the
//   refusal reason before '@'), open order (a comma list of lvl / ptr, e.g. "ptr,lvl,lvl"; G5-P2b), lvl path, ptr path, expected lvl image path,
//   expected ptr image path ("-" = the original file: nothing may be served). G6-P1 (D-251): two optional fields,
//   the transit.lvl path and its expected image path; the open order may then name `transit`. G6-P1b (E-485): the
//   tokens flip_lvl / flip_ptr / flip_transit change one byte (offset 4096) of that file ON DISK at that point of the
//   order (host change; only for private copies of the files) and read nothing.
// Per case: the plan is loaded through the first call the guest would make (GuestSize of the first file in the open
// order), then every file is sized and read in 64 KiB host reads through ExtendRead / AfterRead exactly as
// HostPathFile does. The bytes and sizes the guest would see must equal the expected images; a refused plan must
// leave every file's size and bytes as on disk. Prints one line per case and G5P1_TX_TEST PASS|FAIL n/m.
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "m33_mod_overlay.h"

static std::vector<std::string> g_log;
static void LogLine(const char* line) { g_log.emplace_back(line); }

static std::vector<uint8_t> ReadAll(const std::string& p) {
  std::ifstream f(p, std::ios::binary);
  return std::vector<uint8_t>((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
}

static void SetEnv(const std::string& v) {
#ifdef _WIN32
  _putenv_s("R3HD_DEV_STRUCTURAL_TX", v == "-" ? "" : v.c_str());
#else
  if (v == "-") unsetenv("R3HD_DEV_STRUCTURAL_TX"); else setenv("R3HD_DEV_STRUCTURAL_TX", v.c_str(), 1);
#endif
}

// What the guest sees of one file: (size, bytes), through the overlay's three entry points.
static std::pair<size_t, std::vector<uint8_t>> GuestView(const std::filesystem::path& path,
                                                         const std::filesystem::path& plan) {
  const std::vector<uint8_t> host = ReadAll(path.string());
  const size_t guest = m33mods::GuestSize(path, host.size(), &LogLine, &plan);
  std::vector<uint8_t> out;
  const size_t chunk = 65536;
  for (size_t off = 0; off < guest; off += chunk) {
    const size_t len = std::min(chunk, guest - off);
    std::vector<uint8_t> buf(len, 0xCD);
    const size_t inside = off >= host.size() ? 0 : std::min(len, host.size() - off);
    std::memcpy(buf.data(), host.data() + off, inside);
    size_t got = inside;
    const bool ok = m33mods::ExtendRead(path, off, buf.data(), len, inside > 0, &got, &LogLine, &plan);
    if (!ok) break;
    m33mods::AfterRead(path, off, buf.data(), got, &plan);
    out.insert(out.end(), buf.begin(), buf.begin() + got);
    if (got < len) break;
  }
  return {guest, out};
}

int main(int argc, char** argv) {
  if (argc < 2) {
    std::cerr << "usage: g5p1_tx_test CASES\n";
    return 2;
  }
  std::ifstream cases(argv[1]);
  std::string line;
  int total = 0, passed = 0;
  while (std::getline(cases, line)) {
    if (line.empty() || line[0] == '#') continue;
    std::vector<std::string> f;
    std::stringstream ss(line);
    std::string x;
    while (std::getline(ss, x, '\t')) f.push_back(x);
    if (f.size() != 9 && f.size() != 11) {
      std::cout << "FAIL malformed case line\n";
      ++total;
      continue;
    }
    const std::string& name = f[0];
    const std::filesystem::path plan(f[1]);
    m33mods::ResetForTest();
    g_log.clear();
    SetEnv(f[2]);
    m33mods::state().log = &LogLine;
    // G5-P2b: the open order is a comma list of lvl / ptr, repeats allowed (the same resource opened again)
    const std::filesystem::path lvl(f[5]), ptr(f[6]);
    std::vector<std::pair<std::filesystem::path, std::string>> order;
    std::stringstream os_(f[4]);
    std::string tok;
    while (std::getline(os_, tok, ',')) {
      if (tok == "lvl") order.push_back({lvl, f[7]});
      else if (tok == "ptr") order.push_back({ptr, f[8]});
      else if (tok == "transit" && f.size() == 11) order.push_back({std::filesystem::path(f[9]), f[10]});
      else if (tok.rfind("flip_", 0) == 0) order.push_back({std::filesystem::path(), tok});
      else {
        order.clear();  // an unknown token: the case fails below
        break;
      }
    }
    bool ok = !order.empty();
    std::string why = ok ? "" : " bad open order";
    for (const auto& [path, expect_path] : order) {
      if (path.empty()) {  // G6-P1b: a host change between opens
        const std::string which = expect_path.substr(5);
        const std::string target = which == "lvl" ? f[5] : which == "ptr" ? f[6] : (f.size() == 11 ? f[9] : "");
        std::fstream h(target, std::ios::in | std::ios::out | std::ios::binary);
        char c = 0;
        if (!h || !h.seekg(4096).get(c) || !h.seekp(4096).put(char(c ^ 0x5A))) {
          ok = false;
          why += " flip failed:" + which;
        }
        continue;
      }
      const auto [size, bytes] = GuestView(path, plan);
      const std::vector<uint8_t> want = ReadAll(expect_path == "-" ? path.string() : expect_path);
      if (size != want.size() || bytes != want) {
        ok = false;
        why += " " + path.filename().string() + ":size=" + std::to_string(size) + "/want=" + std::to_string(want.size());
      }
    }
    std::string state = "none";
    for (const auto& l : g_log) {
      if (l.rfind("M33 mods state=active", 0) == 0) state = "active";
      const auto at = l.find("state=refused reason=");
      if (at != std::string::npos) state = l.substr(at + 21, l.find('@', at) == std::string::npos
                                                                  ? std::string::npos
                                                                  : l.find('@', at) - at - 21);
    }
    if (state != f[3]) {
      ok = false;
      why += " state=" + state + "/want=" + f[3];
    }
    ++total;
    passed += ok;
    std::cout << (ok ? "PASS " : "FAIL ") << name << " (" << state << ")" << (ok ? "" : " ::" + why) << "\n";
  }
  SetEnv("-");
  std::cout << "G5P1_TX_TEST " << (passed == total && total ? "PASS " : "FAIL ") << passed << "/" << total << "\n";
  return passed == total && total ? 0 : 1;
}
